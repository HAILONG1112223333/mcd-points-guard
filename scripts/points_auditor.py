#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
积分审计核心 —— 体检 + 汇率榜 + 止损凑单

纯标准库，零第三方依赖。可完全离线运行（读 data/sample/）。

设计红线：
  1. 积分与价格只认接口返回值，绝不推算。匹配不到的一律标 None，不猜。
  2. 金额单位：mall-* 返回元（字符串），calculate-price 返回分（整数）。本模块统一用「元」。
  3. 本模块只读，不做任何兑换动作。

用法:
    python scripts/points_auditor.py                       # 读 data/sample/，打印报告
    python scripts/points_auditor.py --json out.json       # 输出结构化结果
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "data", "sample")

# 组合名 → 菜单单品名（用于计算「净省」口径）。缺的就不算，不猜。
COMBO_PARTS = {
    "巨无霸可乐组合": ["巨无霸", "可乐"],
    "板烧可乐组合": ["板烧鸡腿堡", "可乐"],
    "麦辣可乐组合": ["麦辣鸡腿汉堡", "可乐"],
    "中薯麦乐鸡组合": ["麦乐鸡"],
    "可乐麦炫酷": ["阳光橙麦炫酷"],
    "香芋派": ["派"],
    "菠萝派": ["派"],
}


def _f(v, default=0.0):
    """接口返回的数值多是字符串，统一转 float。"""
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _parse_time(s):
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
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
    """返回 {商品名: 现价(元)}，用于「净省」口径。"""
    d = load(path or os.path.join(SAMPLE, "meals.json"), {}) or {}
    data = d.get("data", d)
    pool = data.get("meals", {}) if isinstance(data, dict) else {}
    out = {}
    if isinstance(pool, dict):
        for item in pool.values():
            if isinstance(item, dict) and item.get("name"):
                out[item["name"]] = _f(item.get("currentPrice"))
    return out


# ---------- 过滤 ----------

def filter_redeemable(mall, now=None):
    """只保留：真·积分兑换(point>0) 且在有效期内。"""
    now = now or datetime.now()
    valid, expired = [], []
    for p in mall:
        if not isinstance(p, dict):
            continue
        point = _f(p.get("point"), 0)
        if point <= 0:
            continue                      # point=0 是现金商品（派对等），不是积分兑换
        up, dn = _parse_time(p.get("upTime")), _parse_time(p.get("downTime"))
        alive = (up is None or up <= now) and (dn is None or dn >= now)
        (valid if alive else expired).append(p)
    return valid, expired


# ---------- 汇率 ----------

def compute_rates(products, menu=None):
    """汇率 = 兑换价 / 积分 × 100 （元/100积分）。净省口径能匹配就补，不能就 None。"""
    menu = menu or {}
    rows = []
    for p in products:
        name = p.get("spuName", "")
        point = int(_f(p.get("point"), 0))
        pay = parse_pay_price(name)
        if point <= 0:
            continue
        rate = (pay / point * 100) if pay is not None else None

        # 净省口径：找菜单原价
        original, net_rate = None, None
        for key, parts in COMBO_PARTS.items():
            if key in name:
                prices = [menu.get(x) for x in parts]
                if all(v is not None for v in prices):
                    original = round(sum(prices), 2)
                    if pay is not None:
                        net = original - pay
                        net_rate = round(net / point * 100, 2) if net > 0 else 0.0
                break

        rows.append({
            "spuId": p.get("spuId"),
            "name": name,
            "point": point,
            "pay": pay,
            "rate": round(rate, 2) if rate is not None else None,   # 元/100积分
            "original": original,                                    # 门店原价（可空）
            "net_rate": net_rate,                                    # 净省 元/100积分（可空）
            "catName": p.get("catName", ""),
            "downTime": p.get("downTime", ""),
            "image": p.get("spuImage", ""),
        })
    rows.sort(key=lambda r: (r["rate"] is not None, r["rate"] or 0), reverse=True)
    return rows


# ---------- 体检 ----------

def audit(account, products, menu=None, now=None):
    now = now or datetime.now()
    valid, expired = filter_redeemable(products, now)
    rows = compute_rates(valid, menu)

    avail = _f(account.get("availablePoint"))
    accum = _f(account.get("accumulativePoint"))
    exp = _f(account.get("expiredPoint"))
    cur_exp = _f(account.get("currentMouthExpirePoint"))
    frozen = _f(account.get("frozenPoint"))

    # 用中位数汇率把积分折算成等值人民币（中位数抗极值，比均值稳）
    rates = sorted(r["rate"] for r in rows if r["rate"] is not None)
    mid = rates[len(rates) // 2] if rates else None

    def to_money(p):
        return round(p * mid / 100, 2) if mid else None

    waste_ratio = round(exp / accum * 100, 1) if accum > 0 else None
    mall_dead_ratio = round(len(expired) / max(len(valid) + len(expired), 1) * 100, 1)

    return {
        "generatedAt": now.strftime("%Y-%m-%d %H:%M:%S"),
        "account": {
            "availablePoint": avail, "accumulativePoint": accum,
            "expiredPoint": exp, "currentMouthExpirePoint": cur_exp,
            "frozenPoint": frozen, "usedPoint": _f(account.get("usedPoint")),
            "currency": account.get("currency", "麦享会积分"),
        },
        "valuation": {
            "medianRate": mid,                       # 元/100积分
            "availableValue": to_money(avail),
            "expiredValue": to_money(exp),
            "currentMouthExpireValue": to_money(cur_exp),
            "wasteRatio": waste_ratio,               # 已过期 / 累计
            "mallDeadRatio": mall_dead_ratio,        # 商城过期商品占比
        },
        "market": {"total": len(valid) + len(expired), "valid": len(valid), "expired": len(expired)},
        "ranking": rows,
        "expiredProducts": [
            {"name": p.get("spuName"), "point": int(_f(p.get("point"))), "downTime": p.get("downTime")}
            for p in expired
        ],
    }


# ---------- 止损凑单：子集和 DP ----------

def optimize(rows, budget, limit_per_item=1):
    """在积分预算内最大化总兑换价值。返回最优组合。"""
    cands = []
    for r in rows:
        if r["pay"] is None or r["point"] <= 0:
            continue
        for _ in range(limit_per_item):
            cands.append({"name": r["name"], "point": r["point"], "pay": r["pay"],
                          "rate": r["rate"], "spuId": r["spuId"]})

    budget = int(budget)
    dp = [0.0] * (budget + 1)
    pick = [[] for _ in range(budget + 1)]
    for it in cands:
        for b in range(budget, it["point"] - 1, -1):
            cand = dp[b - it["point"]] + it["pay"]
            if cand > dp[b] + 1e-9:
                dp[b] = cand
                pick[b] = pick[b - it["point"]] + [it]

    best = max(range(budget + 1), key=lambda b: (dp[b], -b))
    chosen = pick[best]
    spent = sum(x["point"] for x in chosen)
    value = round(dp[best], 2)

    # 对照组：把预算全押在单个最贵的商品上（直觉做法）
    naive = max(rows, key=lambda r: r["point"]) if rows else None
    naive_value = round(naive["pay"], 2) if naive and naive["pay"] else None
    naive_spent = naive["point"] if naive else 0

    return {
        "budget": budget,
        "plan": sorted(chosen, key=lambda x: -(x["rate"] or 0)),
        "spent": spent, "value": value, "remain": budget - spent,
        "planRate": round(value / spent * 100, 2) if spent else None,
        "naive": {"name": naive["name"], "spent": naive_spent, "value": naive_value,
                  "remain": budget - naive_spent} if naive else None,
        "gainRatio": round(value / naive_value, 2) if naive_value else None,
    }


# ---------- 输出 ----------

def render(result, plan):
    a, v = result["account"], result["valuation"]
    L = []
    A = L.append
    A("=" * 64)
    A("  麦麦积分止损官 · 体检报告   %s" % result["generatedAt"])
    A("=" * 64)
    A("")
    A("  【积分体检】")
    A("    可用积分     %10s 分   ≈ ¥%s" % (a["availablePoint"], v["availableValue"]))
    A("    本月将过期   %10s 分   ≈ ¥%s" % (a["currentMouthExpirePoint"], v["currentMouthExpireValue"]))
    A("    已过期       %10s 分   ≈ ¥%s" % (a["expiredPoint"], v["expiredValue"]))
    A("    累计获得     %10s 分" % a["accumulativePoint"])
    if v["wasteRatio"] is not None:
        A("")
        A("    ⚠️  你累计获得的积分，有 %.1f%% 已经蒸发掉了" % v["wasteRatio"])
    A("")
    m = result["market"]
    A("  【积分商城】共 %d 个积分商品 → 可兑换 %d 个，已过期 %d 个（%.0f%% 换不了）"
      % (m["total"], m["valid"], m["expired"], v["mallDeadRatio"]))
    A("")
    A("  【积分汇率榜】每 100 积分能撬动多少元（越高越值）")
    for i, r in enumerate(result["ranking"], 1):
        if r["rate"] is None:
            A("    %2d.  %-30s %4d分   价格未知" % (i, r["name"][:30], r["point"]))
            continue
        tag = " 🔥血赚" if r["rate"] >= 10 else (" 💀血亏" if r["rate"] < 4 else "")
        net = ("   净省 ¥%.1f（%.2f/100分）" % (r["original"] - r["pay"], r["net_rate"])
               if r["net_rate"] is not None else "")
        A("    %2d.  %-30s %4d分 → ¥%-6.1f  %6.2f 元/100分%s%s"
          % (i, r["name"][:30], r["point"], r["pay"], r["rate"], tag, net))
    A("")
    A("  【止损方案】用掉 %d 分" % plan["budget"])
    for x in plan["plan"]:
        A("      · %-30s %4d分   ¥%.1f" % (x["name"][:30], x["point"], x["pay"]))
    A("    合计：%d 分 → ¥%.1f（剩余 %d 分）" % (plan["spent"], plan["value"], plan["remain"]))
    if plan["naive"]:
        n = plan["naive"]
        A("")
        A("    对照（直觉做法：全押最大额）")
        A("      · %-30s %4d分   ¥%.1f（剩 %d 分用不掉）"
          % (n["name"][:30], n["spent"], n["value"] or 0, n["remain"]))
        if plan["gainRatio"]:
            A("    ★ 同样的积分，会换 ¥%.1f vs 不会换 ¥%.1f —— 差 %.2f 倍"
              % (plan["value"], n["value"], plan["gainRatio"]))
    A("")
    A("  数据来源：麦当劳官方 MCP 实时接口。仅供参考，以麦当劳官方结果为准。")
    A("=" * 64)
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", default=os.path.join(SAMPLE, "account.json"))
    ap.add_argument("--mall", default=os.path.join(SAMPLE, "mall_products.json"))
    ap.add_argument("--menu", default=os.path.join(SAMPLE, "meals.json"))
    ap.add_argument("--budget", type=float, default=None, help="积分预算，默认用全部可用积分")
    ap.add_argument("--json", default=None, help="输出结构化 JSON 到指定路径")
    args = ap.parse_args()

    account = load_account(args.account)
    mall = load_mall(args.mall)
    menu = load_meals(args.menu)

    if not account:
        print("未找到积分账户数据：%s" % args.account, file=sys.stderr)
        sys.exit(2)

    result = audit(account, mall, menu)
    budget = args.budget if args.budget is not None else _f(account.get("availablePoint"))
    plan = optimize(result["ranking"], budget)
    result["plan"] = plan

    print(render(result, plan))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print("\n已输出 JSON → %s" % args.json)


if __name__ == "__main__":
    main()
