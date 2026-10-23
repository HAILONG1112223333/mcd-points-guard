#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
零配置演示 —— 不需要 Token、不联网、零第三方依赖。

用的是项目录制的真实 MCP 响应（data/sample/），把「体检 → 汇率榜 → 止损凑单」
整条链路跑一遍。这是给路人看的第一眼，也是 GitHub Pages 试玩页的数据源。

    python demo.py
"""

import json, os, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from points_auditor import load_account, load_mall, load_meals, audit, optimize, render  # noqa: E402

def main():
    print()
    print("  🍟 麦麦积分止损官 · 零配置演示")
    print("  数据来源：data/sample/ —— 麦当劳官方 MCP 真实响应录制，已脱敏")
    print("  本演示不联网、不下单、不扣积分。")
    print()

    account = load_account()
    mall = load_mall()
    menu = load_meals()
    if not account or not mall:
        print("  ✗ 未找到 data/sample/ 下的样本数据。")
        sys.exit(1)

    result = audit(account, mall, menu)
    plan = optimize(result["ranking"], float(account.get("availablePoint", 0)))
    result["plan"] = plan

    print(render(result, plan))

    out = os.path.join(ROOT, "data", "sample", "audit_result.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("\n  结构化结果 → %s" % os.path.relpath(out, ROOT))
    print("  生成 HTML 报告卡片：python scripts/report.py\n")

if __name__ == "__main__":
    main()
