#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
积分审计核心 v2 —— 体检 + 净省榜 + 止损凑单

纯标准库，零第三方依赖。可完全离线运行（读 data/sample/）。

设计红线：
  1. 积分与价格只认接口返回值，绝不推算。匹配不到的一律标 None，不猜。
  2. 金额统一用「元」，但内部累加用「分」的整数，避免浮点误差。
  3. 本模块只读，不做任何兑换动作。
  4. 时间基准用 data/sample/now_time_info.json 的数据快照时间，保证可复现。

v2 相对 v1 的口径变更（重要）：
  - 兑换价 pay 是「用户还要付的现金」，不是「获得的价值」。v1 把 pay 当收益率分子、
    又把 Σpay 当方案总价值，方向是反的。v2 引入：
        value    = 门店单点原价（匹配不到则退回 pay，并标 basis）
        net      = 原价 - pay（真金白银省下的钱，可为负）
        rate     = value  / point * 100   （货值率：每 100 分换到多少货）
        net_rate = net    / point * 100   （净省率：每 100 分省下多少钱）★主排序指标
  - 积分估值用 net_rate 中位数，而非 pay 口径 rate 中位数（后者系统性高估）。
  - 已过期积分不再按汇率估成「资产」，只给「本可值（机会成本）」。

用法:
    python scripts/points_auditor.py                       # 读 data/sample/，打印报告
    python scripts/points_auditor.py --json out.json       # 输出结构化结果
    python scripts/points_auditor.py --budget 500 --now 2026-10-23T13:24:51
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "data", "sample")

# 组合名 → 菜单单品名（用于还原「门店单点原价」）。缺的就不算，不猜。
# 注意：同一个组合只保留一个 key，避免「香芋派/菠萝派」这类名字被 dict 顺序决定命中项。
COMBO_PARTS = {
    "巨无霸可乐组合": ["巨无霸", "可乐"],
    "板烧可乐组合": ["板烧鸡腿堡", "可乐"],
    "麦辣可乐组合": ["麦辣鸡腿汉堡", "可乐"],
    "中薯麦乐鸡组合": ["薯条", "麦乐鸡"],          # v1 漏了「中薯」
    "可乐麦炫酷": ["阳光橙麦炫酷"],
    "香芋派/菠萝派": ["派"],                        # v1 拆成两条，靠 dict 顺序碰运气
    "2份麦辣鸡翅": ["麦辣鸡翅", "麦辣鸡翅"],
    "2份麦辣鸡腿堡": ["麦辣鸡腿汉堡", "麦辣鸡腿汉堡"],
    "2份板烧鸡腿堡": ["板烧鸡腿堡", "板烧鸡腿堡"],
}

# status: 1-仓库中 2-上架 3-售罄 4-下架 5-预热
STATUS_NAME = {1: "仓库中", 2: "上架", 3: "售罄", 4: "下架", 5: "预热"}
REDEEMABLE_STATUS = {2}


def _f(v, default=None):
    """接口返回的数值多是字符串，统一转 float。缺失返回 default（不再静默变 0）。"""
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _cents(v):
    """元 → 分（整数），用于精确累加。"""
    return None if v is None else int(round(float(v) * 100))


def _parse_time(s):
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def parse_pay_price(name):
    """从商品名解析兑换价：'21.9元巨无霸可乐组合' → 21.9。解析不到返回 None。"""
    if not name:
        return None
    m = re.search(r"([\d]+(?:\.[\d]+)?)\s*元", name)
    return float(m.group(1)) if m else None


# ---------- 载入 ----------

def load(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_account(path=None):
    d = load(path or os.path.join(SAMPLE, "account.json"), {}) or {}
    return d.get("data", d)


def load_mall(path=None):
    d = load(path or os.path.join(SAMPLE, "mall_products.json"), {}) or {}
    data = d.get("data", d)
    return data if isinstance(data, list) else []


def load_meals(path=None):
    """返回 {商品名: 现价(元)}，用于还原「门店单点原价」。"""
    d = load(path or os.path.join(SAMPLE, "meals.json"), {}) or {}
    data = d.get("data", d)
    pool = data.get("meals", {}) if isinstance(data, dict) else {}
    out = {}
    if isinstance(pool, dict):
        for item in pool.values():
            if isinstance(item, dict) and item.get("name"):
                price = _f(item.get("currentPrice"))
                if price is not None:
                    out[item["name"]] = price
    return out


def snapshot_now(path=None):
    """数据快照时间（now_time_info.json）。有了它，同一份样本任何时候跑结果都一样。"""
    d = load(path or os.path.join(SAMPLE, "now_time_info.json"), {}) or {}
    data = d.get("data", d)
    if isinstance(data, dict):
        for key in ("datetime", "formatted"):
            t = _parse_time(data.get(key))
            if t:
                return t
        ts = _f(data.get("timestamp"))
        if ts:
            return datetime.fromtimestamp(ts / 1000.0)
    return None


COMBO_MAP_PATH = os.path.join(ROOT, "data", "combo_map.json")


def load_combo_map(path=None):
    """手工补原价的入口（data/combo_map.json）。

    「指定小食任选」这类模糊商品名在门店菜单里匹配不到确定的单点原价，按红线不猜，
    只进「货值参考」区。人工确认过原价后写进这个文件，即可正常参与净省计算与优化。
    支持两种写法：
        {"bySpuId": {"17076": 14.5}, "byName": {"10.9元指定小食任选": 14.5}}
        {"10.9元指定小食任选": 14.5}          # 扁平写法，统一按名称处理
    bySpuId 优先，byName 兜底（名称精确匹配，不做模糊）。
    """
    d = load(path or COMBO_MAP_PATH, {}) or {}
    if not isinstance(d, dict):
        return {"bySpuId": {}, "byName": {}}
    by_id = {str(k): _f(v) for k, v in (d.get("bySpuId") or {}).items() if _f(v) is not None}
    by_name = {k: _f(v) for k, v in (d.get("byName") or {}).items() if _f(v) is not None}
    for k, v in d.items():
        if k.startswith("_") or k in ("bySpuId", "byName"):
            continue
        price = _f(v)
        if price is not None:
            by_name.setdefault(k, price)
    return {"bySpuId": by_id, "byName": by_name}


# ---------- 过滤 ----------

def filter_redeemable(mall, now=None):
    """返回 (可兑换, 已过期, 不可兑换)。

    v2 变更：除有效期外，还把 status 纳入判断 —— 售罄/下架/预热/仓库中 都不算「能换」。
    """
    now = now or snapshot_now() or datetime.now()
    valid, expired, blocked = [], [], []
    for p in mall:
        if not isinstance(p, dict):
            continue
        point = _f(p.get("point"), 0)
        if point is None or point <= 0:
            continue                        # point=0 是现金商品（派对等），不是积分兑换
        up, dn = _parse_time(p.get("upTime")), _parse_time(p.get("downTime"))
        alive = (up is None or up <= now) and (dn is None or dn >= now)
        if not alive:
            expired.append(p)
            continue
        status = int(_f(p.get("status"), 2))
        if status not in REDEEMABLE_STATUS:
            blocked.append(p)
            continue
        valid.append(p)
    return valid, expired, blocked


# ---------- 汇率 ----------

def _match_parts(name, menu):
    """按 COMBO_PARTS 还原组合的原价构成。返回 (原价, 缺失项列表, 命中key)。"""
    for key, parts in COMBO_PARTS.items():
        if key in name:
            prices = [menu.get(x) for x in parts]
            missing = [x for x, v in zip(parts, prices) if v is None]
            if missing:
                return None, missing, key
            return round(sum(prices), 2), [], key
    return None, [], None


def compute_rates(products, menu=None, combo_map=None):
    """算每档券的货值率 / 净省率。

    rate     = value / point * 100   货值率（元/100分）
    net_rate = (原价-兑换价) / point * 100   净省率（元/100分，可为负）
    排序以 net_rate 为主；净省未知的退回 rate（并在 score_basis 里标明）。

    原价来源优先级：combo_map 人工确认值 > 门店菜单单点价 > 无（标 None，不猜）
    """
    menu = menu or {}
    combo_map = combo_map or {}
    by_id = combo_map.get("bySpuId") or {}
    by_name = combo_map.get("byName") or {}
    rows = []
    for p in products:
        name = p.get("spuName", "")
        point_f = _f(p.get("point"))
        if point_f is None or point_f <= 0:
            continue
        point = int(round(point_f))
        pay = parse_pay_price(name)

        # 1) 人工补价优先（唯一允许人工输入的口径）
        sid = p.get("spuId")
        override = by_id.get(str(sid)) if sid is not None else None
        original_source = None
        missing, matched = [], None
        if override is not None:
            original, original_source = round(float(override), 2), "combo_map"
        elif name in by_name:
            original, original_source = round(float(by_name[name]), 2), "combo_map"
        else:
            # 2) 门店菜单还原
            original, missing, matched = _match_parts(name, menu)
            if original is not None:
                original_source = "menu"

        value = original if original is not None else pay
        net = round(original - pay, 2) if (original is not None and pay is not None) else None

        rate = round(value / point * 100, 2) if value is not None else None
        net_rate = round(net / point * 100, 2) if net is not None else None

        if net_rate is not None:
            score, basis = net_rate, "net"
        elif rate is not None:
            score, basis = rate, "gross"     # 原价未知，只能用货值下限（=兑换价）兜底
        else:
            score, basis = None, "none"

        rows.append({
            "spuId": p.get("spuId"),
            "name": name,
            "point": point,
            "pay": pay,                         # 兑换还要付的现金
            "value": value,                     # 货值（原价优先）
            "original": original,               # 门店单点原价（可空）
            "net": net,                         # 净省（可空，可为负）
            "rate": rate,                       # 货值率 元/100分
            "net_rate": net_rate,               # 净省率 元/100分 ★
            "score": score,                     # 排序分
            "score_basis": basis,               # net / gross / none
            "original_missing": missing,        # 缺哪几项菜单价，便于排查
            "original_source": original_source,  # combo_map（人工补）/ menu（门店菜单）/ None
            "matched_key": matched,
            "catName": p.get("catName", ""),
            "status": int(_f(p.get("status"), 2)),
            "downTime": p.get("downTime", ""),
            "image": p.get("spuImage", ""),
        })

    # 同名券（不同积分档）打个标记，避免榜单上两条一样的名字让人困惑
    seen = {}
    for r in rows:
        seen.setdefault(r["name"], []).append(r)
    for name, group in seen.items():
        if len(group) > 1:
            for r in group:
                r["dup"] = "同名券 %d 档（%s），按积分从低到高选" % (
                    len(group), "/".join(str(g["point"]) for g in sorted(group, key=lambda x: x["point"])))

    rows.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0)))
    return rows


def _median(vals):
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    return round(s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0, 2)


# ---------- 体检 ----------

def audit(account, products, menu=None, now=None, combo_map=None):
    now = now or snapshot_now() or datetime.now()
    combo_map = combo_map if combo_map is not None else load_combo_map()
    valid, expired, blocked = filter_redeemable(products, now)
    rows = compute_rates(valid, menu, combo_map)

    avail = _f(account.get("availablePoint"))
    accum = _f(account.get("accumulativePoint"))
    exp = _f(account.get("expiredPoint"))
    cur_exp = _f(account.get("currentMouthExpirePoint"))
    frozen = _f(account.get("frozenPoint"))

    # 积分估值：优先用「净省率」中位数（真金白银），没有净省样本才退回货值率
    net_rates = [r["net_rate"] for r in rows if r["net_rate"] is not None]
    gross_rates = [r["rate"] for r in rows if r["rate"] is not None]
    if net_rates:
        mid, mid_basis = _median(net_rates), "net"
    else:
        mid, mid_basis = _median(gross_rates), "gross"

    def to_money(p):
        if p is None or mid is None:
            return None
        return round(p * mid / 100, 2)

    waste_ratio = round(exp / accum * 100, 1) if (exp is not None and accum) else None
    mall_dead_ratio = round((len(expired) + len(blocked)) / max(len(valid) + len(expired) + len(blocked), 1) * 100, 1)

    return {
        "generatedAt": now.strftime("%Y-%m-%d %H:%M:%S"),
        "dataSnapshot": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "account": {
            "availablePoint": avail, "accumulativePoint": accum,
            "expiredPoint": exp, "currentMouthExpirePoint": cur_exp,
            "frozenPoint": frozen, "usedPoint": _f(account.get("usedPoint")),
            "currency": account.get("currency", "麦享会积分"),
        },
        "valuation": {
            "medianRate": mid,                       # 元/100分
            "medianRateBasis": mid_basis,            # net=净省率 / gross=货值率
            "availableValue": to_money(avail),
            # 已过期积分没有任何变现路径，账面价值为 0；这里给的是「本可值」=机会成本
            "expiredValue": to_money(exp),
            "expiredValueRealizable": 0.0,
            "expiredValueLabel": "本可值（机会成本）",
            "currentMouthExpireValue": to_money(cur_exp),
            "wasteRatio": waste_ratio,               # 已过期 / 累计
            "mallDeadRatio": mall_dead_ratio,        # 商城换不了的商品占比
        },
        "market": {
            "total": len(valid) + len(expired) + len(blocked),
            "valid": len(valid), "expired": len(expired), "blocked": len(blocked),
        },
        "ranking": rows,
        "comboMapOverrides": sum(1 for r in rows if r.get("original_source") == "combo_map"),
        "expiredProducts": [
            {"name": p.get("spuName"), "point": int(_f(p.get("point"), 0)), "downTime": p.get("downTime")}
            for p in expired
        ],
        "blockedProducts": [
            {"name": p.get("spuName"), "point": int(_f(p.get("point"), 0)),
             "status": STATUS_NAME.get(int(_f(p.get("status"), 2)), "未知")}
            for p in blocked
        ],
    }


# ---------- 止损凑单：0/1 背包 DP ----------

def optimize(rows, budget, limit_per_item=1, objective="net"):
    """在积分预算内最大化「净省」。

    v1 的三处硬伤在这里修掉：
      1. 目标函数：v1 用 Σ兑换价（pay）当价值 —— 那是用户自己掏的现金，越省积分反而
         越「值钱」，方向反了。v2 用 Σ净省（原价-兑换价），原价未知的券不猜、不纳入。
      2. 内存：v1 的 pick[b] 存整份列表、每次回溯都拷贝，O(budget×n×k)。v2 用前驱链表，
         只存 (候选下标, 前驱节点, 已花积分)，回溯 O(k)。
      3. 平局：v1 取「花更少积分」，与止损目标冲突。v2 在净省相同时优先多消耗积分。
    """
    budget = int(round(budget))
    exclude = []
    cands = []
    seen = set()
    for r in rows:
        sid = r.get("spuId")
        key = ("spu", sid) if sid is not None else ("name", r["name"])
        if key in seen:
            continue
        point = int(round(r.get("point") or 0))
        if point <= 0:
            continue
        if objective == "net":
            gain = r.get("net")
            if gain is None or gain <= 0:
                if gain is None:
                    exclude.append({"name": r["name"], "point": point,
                                    "reason": "门店原价未匹配，不猜 · 可在 data/combo_map.json 手工补"})
                continue
        else:
            gain = r.get("value")
            if gain is None or gain <= 0:
                continue
        if point > budget:
            exclude.append({"name": r["name"], "point": point,
                            "reason": "单件超过预算"})
            continue
        seen.add(key)
        for _ in range(max(1, int(limit_per_item))):
            cands.append({
                "name": r["name"], "point": point, "pay": r.get("pay"),
                "value": r.get("value"), "net": r.get("net"),
                "rate": r.get("rate"), "net_rate": r.get("net_rate"),
                "score": r.get("score"), "spuId": sid,
            })

    # dp[b] = 预算 b 内能拿到的最大净省；node[b] = (候选下标, 前驱节点, 已花积分)
    dp = [0.0] * (budget + 1)
    node = [None] * (budget + 1)
    for idx, it in enumerate(cands):
        pt, gain = it["point"], float(it["net"])
        if pt > budget:
            continue
        for b in range(budget, pt - 1, -1):
            prev = b - pt
            cand = dp[prev] + gain
            if cand > dp[b] + 1e-9:
                dp[b] = cand
                node[b] = (idx, node[prev], (node[prev][2] if node[prev] else 0) + pt)

    best_val = max(dp) if dp else 0.0
    best_b, best_spent = 0, 0
    for b in range(budget + 1):
        if dp[b] >= best_val - 1e-9:
            sp = node[b][2] if node[b] else 0
            if sp > best_spent:          # 净省相同 → 优先把快过期积分花掉
                best_b, best_spent = b, sp

    chosen = []
    cur = node[best_b] if best_b <= budget else None
    while cur:
        idx, prev_node, _spent = cur
        chosen.append(cands[idx])
        cur = prev_node
    chosen.reverse()

    spent = sum(x["point"] for x in chosen)
    value = round(best_val, 2)
    gross = round(sum((x["value"] or 0) for x in chosen), 2)
    cash = round(sum((x["pay"] or 0) for x in chosen), 2)

    # 对照组一：只按汇率贪心装（看得懂榜单但不会凑单，最常见的「聪明人做法」）
    greedy, g_spent = [], 0
    for it in sorted(cands, key=lambda x: -(x["score"] or 0)):
        if g_spent + it["point"] <= budget:
            greedy.append(it)
            g_spent += it["point"]
    g_value = round(sum(float(x["net"]) for x in greedy), 2)

    # 对照组二：全押单件最大积分（v1 的对照口径，留着做参考）
    maxp = max(cands, key=lambda x: x["point"]) if cands else None
    mp_value = round(float(maxp["net"]), 2) if maxp else None

    return {
        "budget": budget,
        "objective": objective,
        "plan": sorted(chosen, key=lambda x: -(x["net_rate"] or 0)),
        "spent": spent,
        "value": value,                                  # Σ净省（元）
        "gross": gross,                                  # Σ货值（元，原价口径）
        "cash": cash,                                    # Σ兑换付现（元）
        "remain": budget - spent,
        "planRate": round(value / spent * 100, 2) if spent else None,
        "naive": {                                        # 对照一：汇率贪心
            "kind": "greedy", "name": "按净省率贪心装",
            "spent": g_spent, "value": g_value, "remain": budget - g_spent,
            "items": [x["name"] for x in greedy],
        },
        "naiveMaxPoint": {                                # 对照二：全押最大额
            "kind": "maxpoint", "name": maxp["name"] if maxp else None,
            "spent": maxp["point"] if maxp else 0,
            "value": mp_value, "remain": budget - (maxp["point"] if maxp else 0),
        },
        "gainRatio": round(value / g_value, 2) if g_value else None,
        "gainRatioMaxPoint": round(value / mp_value, 2) if mp_value else None,
        "excluded": exclude,
    }


# ---------- 输出 ----------

def _y(v, unit="¥"):
    return "—" if v is None else "%s%.2f" % (unit, v)


def render(result, plan):
    a, v, m = result["account"], result["valuation"], result["market"]
    L = []
    A = L.append
    A("=" * 68)
    A("  麦麦积分止损官 · 体检报告   %s" % result["generatedAt"])
    A("  数据快照：%s（离线样本，结果可复现）" % result.get("dataSnapshot", "-"))
    A("=" * 68)
    A("")
    A("  【积分体检】")
    A("    可用积分     %10s 分   ≈ ¥%s" % (a["availablePoint"], v["availableValue"]))
    A("    本月将过期   %10s 分   ≈ ¥%s" % (a["currentMouthExpirePoint"], v["currentMouthExpireValue"]))
    A("    已过期       %10s 分   本可值 %s（已归零，当前可变现 %s）"
      % (a["expiredPoint"], _y(v["expiredValue"]), _y(v["expiredValueRealizable"])))
    A("    累计获得     %10s 分" % a["accumulativePoint"])
    A("    估值口径     每 100 分 ≈ ¥%s（%s 中位数）"
      % (v["medianRate"], "净省率" if v.get("medianRateBasis") == "net" else "货值率"))
    if v["wasteRatio"] is not None:
        A("")
        A("    ⚠️  你累计获得的积分，有 %.1f%% 已经蒸发掉了" % v["wasteRatio"])
    A("")
    A("  【积分商城】共 %d 个积分商品 → 能换 %d 个（%.0f%% 换不了：过期 %d / 售罄下架 %d）"
      % (m["total"], m["valid"], v["mallDeadRatio"], m["expired"], m["blocked"]))
    A("")
    A("  【净省榜】每 100 积分真金白银省多少钱（原价已匹配，按净省率降序）")
    net_rows = [r for r in result["ranking"] if r["net"] is not None]
    ref_rows = [r for r in result["ranking"] if r["net"] is None and r["score"] is not None]
    none_rows = [r for r in result["ranking"] if r["score"] is None]
    for i, r in enumerate(net_rows, 1):
        tag = " 🔥血赚" if (r["net_rate"] or 0) >= 10 else (" 💀血亏" if (r["net_rate"] or 0) < 0 else "")
        src = " 〔原价人工补〕" if r.get("original_source") == "combo_map" else ""
        dup = "  ⚠︎" + r["dup"] if r.get("dup") else ""
        A("    %2d.  %-28s %4d分 付¥%-5.1f 省¥%-5.1f  %6.2f 元/100分（货值 %5.2f）%s%s%s"
          % (i, r["name"][:28], r["point"], r["pay"], r["net"], r["net_rate"], r["rate"], tag, src, dup))
    if not net_rows:
        A("    （本次没有能匹配到门店原价的券，无法计算净省）")
    if ref_rows or none_rows:
        A("")
        A("  【货值参考】原价匹配不到，算不出净省 —— 这里只列下限，不参与推荐")
        for i, r in enumerate(ref_rows + none_rows, 1):
            dup = "  ⚠︎" + r["dup"] if r.get("dup") else ""
            if r["pay"] is not None:
                A("    %2d.  %-28s %4d分 付¥%-5.1f 货值率 %6.2f 元/100分%s"
                  % (i, r["name"][:28], r["point"], r["pay"], r["rate"], dup))
            else:
                A("    %2d.  %-28s %4d分 价格未知%s" % (i, r["name"][:28], r["point"], dup))
    A("")
    A("  【止损方案】预算 %d 分，目标 = 最大化净省" % plan["budget"])
    for x in plan["plan"]:
        A("      · %-28s %4d分  付¥%-5.1f  省¥%.1f"
          % (x["name"][:28], x["point"], x["pay"] or 0, x["net"]))
    A("    合计：%d 分 → 净省 ¥%.2f（货值 ¥%.2f，付现 ¥%.2f，剩 %d 分）"
      % (plan["spent"], plan["value"], plan["gross"], plan["cash"], plan["remain"]))
    if plan["plan"] and plan["planRate"] is not None:
        A("    方案净省率：%.2f 元/100分" % plan["planRate"])
    if plan["excluded"]:
        agg = {}
        for e in plan["excluded"]:
            agg[(e["name"], e["reason"])] = agg.get((e["name"], e["reason"]), 0) + 1
        A("    未纳入优化：%s" % "；".join(
            "%s ×%d（%s）" % (n, c, r) if c > 1 else "%s（%s）" % (n, r)
            for (n, r), c in agg.items()))
    A("")
    if plan.get("naive"):
        n = plan["naive"]
        A("    对照 A｜按净省率贪心装：%d 分 → 净省 ¥%.2f（剩 %d 分）"
          % (n["spent"], n["value"], n["remain"]))
    if plan.get("naiveMaxPoint") and plan["naiveMaxPoint"].get("name"):
        n2 = plan["naiveMaxPoint"]
        A("    对照 B｜全押最大额 %s：%d 分 → 净省 ¥%.2f（剩 %d 分）"
          % (n2["name"][:20], n2["spent"], n2["value"] or 0, n2["remain"]))
    if plan.get("gainRatio"):
        A("    ★ 凑单 DP 比「贪心装」多省 %.2f 倍；比「全押最大额」多省 %s 倍"
          % (plan["gainRatio"], plan.get("gainRatioMaxPoint") or "—"))
    if plan["remain"] > 0 and a["currentMouthExpirePoint"]:
        A("    ⚠️  还剩 %d 分没花掉，其中 %s 分本月就到期" % (plan["remain"], a["currentMouthExpirePoint"]))
    A("")
    A("  数据来源：麦当劳官方 MCP 实时接口。仅供参考，以麦当劳官方结果为准。")
    A("  口径：净省 = 门店单点原价 − 兑换现金价；原价匹配不到就留空，不做估算。")
    A("=" * 68)
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", default=os.path.join(SAMPLE, "account.json"))
    ap.add_argument("--mall", default=os.path.join(SAMPLE, "mall_products.json"))
    ap.add_argument("--menu", default=os.path.join(SAMPLE, "meals.json"))
    ap.add_argument("--budget", type=float, default=None, help="积分预算，默认用全部可用积分")
    ap.add_argument("--now", default=None, help="基准时间（默认取 now_time_info.json 的快照时间）")
    ap.add_argument("--combo-map", default=None, help="手工补原价表，默认 data/combo_map.json")
    ap.add_argument("--json", default=None, help="输出结构化 JSON 到指定路径")
    args = ap.parse_args()

    account = load_account(args.account)
    mall = load_mall(args.mall)
    menu = load_meals(args.menu)
    combo_map = load_combo_map(args.combo_map)

    if not account:
        print("未找到积分账户数据：%s" % args.account, file=sys.stderr)
        sys.exit(2)

    now = _parse_time(args.now) if args.now else None
    result = audit(account, mall, menu, now=now, combo_map=combo_map)
    budget = args.budget if args.budget is not None else _f(account.get("availablePoint"), 0)
    plan = optimize(result["ranking"], budget)
    result["plan"] = plan

    print(render(result, plan))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print("\n已输出 JSON → %s" % args.json)


if __name__ == "__main__":
    main()
