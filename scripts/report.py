#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成可截图的 HTML 体检报告卡片（传播物料）。

用法:
    python scripts/report.py --input data/sample/audit_result.json --out assets/report.html
"""

import argparse, html, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#f5f5f7;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;padding:32px 16px;color:#1d1d1f}
.card{max-width:720px;margin:0 auto;background:#fff;border-radius:20px;box-shadow:0 8px 40px rgba(0,0,0,.10);overflow:hidden}
.hd{background:linear-gradient(135deg,#ffc72c,#ff9f0a);padding:26px 32px;color:#3a2500}
.hd h1{font-size:22px;font-weight:800}
.hd .sub{font-size:12px;opacity:.75;margin-top:6px}
.body{padding:26px 32px 32px}
.sec{margin-bottom:26px}
.sec-t{font-size:13px;font-weight:700;color:#86868b;letter-spacing:1px;margin-bottom:12px}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.cell{background:#f5f5f7;border-radius:12px;padding:14px 12px;text-align:center}
.cell .n{font-size:20px;font-weight:800}
.cell .n.warn{color:#d70015}.cell .n.ok{color:#007a33}
.cell .l{font-size:11px;color:#86868b;margin-top:4px}
.cell .v{font-size:11px;color:#ff9f0a;font-weight:600;margin-top:3px}
.alert{background:#fff2f2;border-left:4px solid #d70015;border-radius:8px;padding:14px 16px;font-size:14px;color:#5a0a10;line-height:1.7}
.alert.amber{background:#fffaf0;border-left-color:#ff9f0a;color:#5a3a00}
.alert b{color:#d70015;font-size:16px}
.alert.amber b{color:#c2410c}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;font-size:11px;color:#86868b;font-weight:600;padding:8px 6px;border-bottom:1px solid #e5e5ea}
td{padding:10px 6px;border-bottom:1px solid #f0f0f2;vertical-align:middle}
.bar{height:6px;border-radius:3px;background:linear-gradient(90deg,#ff9f0a,#ffc72c);display:inline-block}
.tag{display:inline-block;font-size:10px;padding:2px 6px;border-radius:4px;font-weight:700;margin-left:4px}
.tag.hot{background:#fff0e0;color:#c2410c}.tag.bad{background:#f0f0f2;color:#86868b}
.plan{background:#f5f5f7;border-radius:14px;padding:18px}
.plan .row{display:flex;justify-content:space-between;font-size:13px;padding:6px 0}
.plan .total{border-top:1px solid #d2d2d7;margin-top:10px;padding-top:12px;font-weight:800;font-size:15px}
.vs{display:flex;gap:12px;margin-top:14px}
.vs>div{flex:1;border-radius:12px;padding:14px;text-align:center}
.good{background:#eaf7ee}.bad{background:#eeeeef}
.vs .t{font-size:11px;color:#86868b}.vs .m{font-size:24px;font-weight:800;margin:6px 0}
.good .m{color:#007a33}.bad .m{color:#86868b}
.gain{text-align:center;font-size:15px;font-weight:800;color:#d70015;margin-top:14px}
.ft{padding:16px 32px 24px;font-size:11px;color:#86868b;line-height:1.7;border-top:1px solid #f0f0f2}
"""

def esc(s):
    return html.escape(str(s)) if s is not None else ""

def build_body(result):
    a, v, m = result["account"], result["valuation"], result["market"]
    plan = result.get("plan") or {}
    P = ['<div class="card">']
    P.append('<div class="hd"><h1>🍟 麦麦积分止损官 · 体检报告</h1>'
             '<div class="sub">%s · 数据源：麦当劳官方 MCP 实时接口</div></div>' % esc(result.get("generatedAt", "")))
    P.append('<div class="body">')

    # 积分体检
    P.append('<div class="sec"><div class="sec-t">积分体检</div><div class="grid">')
    P.append('<div class="cell"><div class="n ok">%s</div><div class="l">可用积分</div><div class="v">≈ ¥%s</div></div>'
             % (esc(a["availablePoint"]), esc(v["availableValue"])))
    P.append('<div class="cell"><div class="n warn">%s</div><div class="l">已过期</div><div class="v">≈ ¥%s</div></div>'
             % (esc(a["expiredPoint"]), esc(v["expiredValue"])))
    P.append('<div class="cell"><div class="n">%s</div><div class="l">累计获得</div></div>' % esc(a["accumulativePoint"]))
    P.append('<div class="cell"><div class="n">%s</div><div class="l">本月将过期</div></div>' % esc(a["currentMouthExpirePoint"]))
    P.append('</div>')
    if v.get("wasteRatio") is not None:
        P.append('<div class="alert" style="margin-top:14px">你累计获得的积分，有 <b>%.1f%%</b> 已经蒸发掉了 —— 相当于白丢了 <b>¥%s</b>。</div>'
                 % (v["wasteRatio"], esc(v["expiredValue"])))
    P.append('</div>')

    # 商城现状
    P.append('<div class="sec"><div class="sec-t">积分商城现状</div>'
             '<div class="alert amber">列表里共 <b>%d</b> 个积分商品，其中 <b>%d</b> 个已经过期换不了（%.0f%%），真正能换的只有 <b>%d</b> 个。</div></div>'
             % (m["total"], m["expired"], v["mallDeadRatio"], m["valid"]))

    # 汇率榜
    rates = [r["rate"] for r in result["ranking"] if r["rate"] is not None]
    mx = max(rates) if rates else 1
    P.append('<div class="sec"><div class="sec-t">积分汇率榜 · 每 100 积分值多少元</div><table>')
    P.append('<tr><th style="width:40%">商品</th><th>积分</th><th>兑换价</th><th style="width:28%">汇率</th></tr>')
    for r in result["ranking"]:
        rate = r["rate"]
        if rate is None:
            P.append('<tr><td>%s</td><td>%d</td><td colspan="2">价格未知</td></tr>' % (esc(r["name"]), r["point"]))
            continue
        tag = '<span class="tag hot">血赚</span>' if rate >= 10 else ('<span class="tag bad">血亏</span>' if rate < 4 else '')
        P.append('<tr><td>%s%s</td><td>%d</td><td>¥%s</td>'
                 '<td><span class="bar" style="width:%.0fpx"></span> <b>%.2f</b></td></tr>'
                 % (esc(r["name"]), tag, r["point"], esc(r["pay"]), max(rate / mx * 80, 8), rate))
    P.append('</table></div>')

    # 止损方案
    if plan.get("plan"):
        P.append('<div class="sec"><div class="sec-t">止损方案 · 用掉 %d 分</div><div class="plan">' % plan["budget"])
        for x in plan["plan"]:
            P.append('<div class="row"><span>%s</span><span>%d 分 · ¥%.1f</span></div>' % (esc(x["name"]), x["point"], x["pay"]))
        P.append('<div class="row total"><span>合计</span><span>%d 分 → ¥%.1f（剩 %d）</span></div>' % (plan["spent"], plan["value"], plan["remain"]))
        n = plan.get("naive")
        if n and plan.get("gainRatio"):
            P.append('<div class="vs"><div class="good"><div class="t">会换</div><div class="m">¥%.1f</div>'
                     '<div class="t">%d 分换出一桌</div></div>'
                     '<div class="bad"><div class="t">不会换（全押最大额）</div><div class="m">¥%.1f</div>'
                     '<div class="t">剩 %d 分烂在手里</div></div></div>'
                     % (plan["value"], plan["spent"], n["value"] or 0, n["remain"]))
            P.append('<div class="gain">同样的积分，会换和不会换差 %.2f 倍</div>' % plan["gainRatio"])
        P.append('</div></div>')

    P.append('</div>')
    P.append('<div class="ft">本工具为麦当劳程序员创意开发大赛参赛作品，非麦当劳官方产品。<br>'
             '积分、价格、商品有效期均来自麦当劳官方 MCP 实时接口，仅供参考，请以麦当劳官方渠道结果为准。<br>'
             '汇率 = 兑换价 ÷ 所需积分 × 100；「净省」仅在能匹配到门店菜单原价时给出，匹配不到即留空，不做估算。</div>')
    P.append('</div>')
    return "".join(P)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=os.path.join(ROOT, "data", "sample", "audit_result.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "assets", "report.html"))
    args = ap.parse_args()
    result = json.load(open(args.input, encoding="utf-8"))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    page = ("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>麦麦积分止损官 · 体检报告</title><style>%s</style></head><body>%s</body></html>"
            % (CSS, build_body(result)))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(page)
    print("报告已生成 → %s (%d 字节)" % (args.out, len(page)))

if __name__ == "__main__":
    main()
