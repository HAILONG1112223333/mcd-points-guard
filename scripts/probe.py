#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据探测脚本 —— 拿到真实接口返回，导出到 data/sample/

这一步决定了后面所有解析器能不能写对，务必先跑通它。

用法:
    export MCD_MCP_TOKEN='你的token'
    python scripts/probe.py                 # 全量探测
    python scripts/probe.py --addr 常州市新北区  # 指定定位地址

产物:
    data/sample/tools.json           全部工具清单
    data/sample/account.json         账户积分
    data/sample/stores.json          附近门店
    data/sample/meals.json           门店菜单
    data/sample/mall_products.json   积分商城商品
    data/sample/mall_detail.json     积分商品详情
    data/sample/coupons.json         优惠券（辅助）
    data/sample/raw/                 逐条原始响应（排错用）
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_client import McpClient  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "data", "sample")
RAW = os.path.join(SAMPLE, "raw")

os.makedirs(RAW, exist_ok=True)


def dump(name, obj):
    path = os.path.join(SAMPLE, name + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    print("  ✓ data/sample/%s.json" % name)


def dump_raw(name, obj):
    with open(os.path.join(RAW, name + ".json"), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def brief(obj, limit=260):
    s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    return (s[:limit] + " …") if len(s) > limit else s


def walk_keys(obj, prefix="", depth=0, out=None, maxdepth=3):
    """把返回结构的所有字段路径打出来，用于设计解析器。"""
    if out is None:
        out = []
    if depth > maxdepth:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(prefix + "." + k if prefix else k)
            walk_keys(v, (prefix + "." + k) if prefix else k, depth + 1, out, maxdepth)
    elif isinstance(obj, list) and obj:
        walk_keys(obj[0], prefix + "[]", depth + 1, out, maxdepth)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--addr", default=os.environ.get("MCD_ADDR", "江苏省常州市新北区万达广场"),
                    help="定位用地址关键词")
    ap.add_argument("--slow", action="store_true", help="每次调用间隔 1.2s，避免限流")
    args = ap.parse_args()

    c = McpClient()

    def pace():
        if args.slow:
            time.sleep(1.2)

    print("\n[1/7] tools/list —— 工具清单")
    tools = c.list_tools()
    dump("tools", tools)
    names = [t.get("name") for t in tools]
    print("  共 %d 个工具" % len(names))
    pace()

    print("\n[2/7] now-time-info —— 当前时间与餐段")
    r = c.safe_call("now-time-info")
    dump_raw("now_time_info", r)
    print("  " + brief(r.get("data") if r["ok"] else r.get("error")))
    pace()

    print("\n[3/7] query-my-account —— 账户积分（本项目核心）")
    r = c.safe_call("query-my-account")
    dump_raw("account", r)
    if r["ok"]:
        dump("account", r["data"])
        print("  字段路径: %s" % ", ".join(walk_keys(r["data"])[:18]))
    else:
        print("  ✗ " + str(r["error"]))
    pace()

    print("\n[4/7] query-nearby-stores —— 附近门店")
    r = c.safe_call("query-nearby-stores", {"address": args.addr})
    dump_raw("stores", r)
    if r["ok"]:
        dump("stores", r["data"])
        print("  字段路径: %s" % ", ".join(walk_keys(r["data"])[:18]))
        store_code = None
        # 尽力提取第一个门店编码，供后续调用使用
        def find_code(o):
            if isinstance(o, dict):
                for k in ("storeCode", "store_code", "code", "storeId"):
                    if k in o and o[k]:
                        return o[k]
                for v in o.values():
                    got = find_code(v)
                    if got:
                        return got
            elif isinstance(o, list):
                for v in o:
                    got = find_code(v)
                    if got:
                        return got
            return None
        store_code = find_code(r["data"])
        print("  首个门店编码: %s" % store_code)
    else:
        print("  ✗ " + str(r["error"]))
        store_code = None
    pace()

    print("\n[5/7] mall-points-products —— 积分商城可兑换商品（本项目核心）")
    r = c.safe_call("mall-points-products")
    dump_raw("mall_products", r)
    if r["ok"]:
        dump("mall_products", r["data"])
        print("  字段路径: %s" % ", ".join(walk_keys(r["data"])[:22]))
    else:
        print("  ✗ " + str(r["error"]))
    pace()

    print("\n[6/7] query-meals —— 门店菜单（用于算积分汇率）")
    if store_code:
        r = c.safe_call("query-meals", {"storeCode": str(store_code)})
        dump_raw("meals", r)
        if r["ok"]:
            dump("meals", r["data"])
            print("  字段路径: %s" % ", ".join(walk_keys(r["data"])[:22]))
        else:
            print("  ✗ " + str(r["error"]))
    else:
        print("  (跳过：未拿到门店编码)")
    pace()

    print("\n[7/7] query-my-coupons —— 我的优惠券（辅助模块）")
    r = c.safe_call("query-my-coupons")
    dump_raw("coupons", r)
    if r["ok"]:
        dump("coupons", r["data"])
    else:
        print("  ✗ " + str(r["error"]))

    print("\n" + "=" * 60)
    print("探测完成。产物在 data/sample/")
    print("=" * 60)
    print("\n下一步：把下面 4 个文件的【开头 60 行】贴给我，我来写解析器：")
    for n in ("account", "stores", "mall_products", "meals"):
        p = os.path.join(SAMPLE, n + ".json")
        if os.path.exists(p):
            print("   - " + p)
    print("\n⚠ 贴之前请检查是否含手机号/地址等隐私，可用 scripts/sanitize.py 脱敏。")


if __name__ == "__main__":
    main()
