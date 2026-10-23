#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成在线试玩页 index.html —— 纯静态、零依赖、可交互。

路人打开就能玩：输入自己的积分数，立刻看到「怎么换最值」。
这是 GitHub Pages 的入口，也是拉 Star 的第一触点。

用法: python scripts/build_pages.py   →   index.html
"""

import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "sample", "audit_result.json")
OUT = os.path.join(ROOT, "index.html")

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>麦麦积分止损官 · 你的麦当劳积分正在过期</title>
<meta name="description" content="算出你的麦当劳积分有多少正在过期、每100积分值多少钱、怎样刚好花完不浪费。基于麦当劳官方 MCP 实时数据。">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#f5f5f7;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;color:#1d1d1f;line-height:1.6}
.wrap{max-width:760px;margin:0 auto;padding:0 16px 60px}
.hero{background:linear-gradient(135deg,#ffc72c,#ff9f0a);padding:38px 28px 32px;color:#3a2500;text-align:center}
.hero h1{font-size:26px;font-weight:800;margin-bottom:8px}
.hero p{font-size:14px;opacity:.8}
.hero .nums{display:flex;justify-content:center;gap:26px;margin-top:22px;flex-wrap:wrap}
.hero .n{font-size:24px;font-weight:800}
.hero .l{font-size:11px;opacity:.75}
.card{background:#fff;border-radius:18px;box-shadow:0 4px 24px rgba(0,0,0,.07);padding:24px;margin-top:20px}
.card h2{font-size:17px;font-weight:800;margin-bottom:4px}
.card .sub{font-size:12px;color:#86868b;margin-bottom:18px}
.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.cell{background:#f5f5f7;border-radius:12px;padding:14px 10px;text-align:center}
.cell .v{font-size:19px;font-weight:800}
.cell .v.red{color:#d70015}.cell .v.green{color:#007a33}
.cell .k{font-size:11px;color:#86868b;margin-top:3px}
.cell .m{font-size:11px;color:#ff9f0a;font-weight:600;margin-top:2px}
.alert{background:#fff2f2;border-left:4px solid #d70015;border-radius:8px;padding:13px 15px;font-size:13.5px;color:#5a0a10;margin-top:14px}
.alert b{color:#d70015;font-size:15px}
.alert.amber{background:#fffaf0;border-left-color:#ff9f0a;color:#5a3a00}
.alert.amber b{color:#c2410c}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;font-size:11px;color:#86868b;padding:8px 4px;border-bottom:1px solid #e5e5ea;font-weight:600}
td{padding:9px 4px;border-bottom:1px solid #f0f0f2}
.bar{height:7px;border-radius:4px;background:linear-gradient(90deg,#ff9f0a,#ffc72c);display:inline-block;vertical-align:middle}
.tag{font-size:10px;padding:2px 6px;border-radius:4px;font-weight:700;margin-left:4px}
.tag.hot{background:#fff0e0;color:#c2410c}.tag.bad{background:#f0f0f2;color:#86868b}
.calc{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.calc input{flex:1;min-width:160px;font-size:17px;font-weight:700;padding:12px 14px;border:2px solid #d2d2d7;border-radius:12px;outline:none}
.calc input:focus{border-color:#ff9f0a}
.calc button{background:#da291c;color:#fff;border:0;border-radius:12px;padding:13px 22px;font-size:15px;font-weight:800;cursor:pointer}
.calc button:hover{background:#b81f14}
.res{background:#f5f5f7;border-radius:14px;padding:18px;margin-top:16px}
.res .row{display:flex;justify-content:space-between;font-size:13.5px;padding:6px 0}
.res .tot{border-top:1px solid #d2d2d7;margin-top:10px;padding-top:12px;font-weight:800;font-size:15px}
.vs{display:flex;gap:12px;margin-top:14px}
.vs>div{flex:1;border-radius:12px;padding:14px;text-align:center}
.good{background:#eaf7ee}.bad{background:#eeeeef}
.vs .t{font-size:11px;color:#86868b}.vs .m{font-size:23px;font-weight:800;margin:5px 0}
.good .m{color:#007a33}.bad .m{color:#86868b}
.gain{text-align:center;font-size:15px;font-weight:800;color:#d70015;margin-top:12px}
pre{background:#1d1d1f;color:#e8e8ed;border-radius:10px;padding:14px;font-size:12px;overflow-x:auto;line-height:1.5}
.star{display:block;text-align:center;background:#ffc72c;color:#3a2500;border-radius:12px;padding:14px;font-weight:800;text-decoration:none;margin-top:18px;font-size:15px}
.star:hover{background:#ffb800}
.ft{text-align:center;font-size:11.5px;color:#86868b;padding:26px 16px 0;line-height:1.8}
@media(max-width:520px){.grid4{grid-template-columns:repeat(2,1fr)}.hero h1{font-size:21px}}
</style>
</head>
<body>
<div class="hero">
  <h1>🍟 麦麦积分止损官</h1>
  <p>你的麦当劳积分，正在悄悄过期</p>
  <div class="nums">
    <div><div class="n">51.3%</div><div class="l">积分已蒸发</div></div>
    <div><div class="n">70%</div><div class="l">商城商品换不了</div></div>
    <div><div class="n">2.44×</div><div class="l">会换 vs 不会换</div></div>
  </div>
</div>

<div class="wrap">

  <div class="card">
    <h2>实测体检（真实麦当劳账户）</h2>
    <div class="sub">数据来自麦当劳官方 MCP 接口，2026-10-23</div>
    <div class="grid4">
      <div class="cell"><div class="v green">__AVAIL__</div><div class="k">可用积分</div><div class="m">≈ ¥__AVAILV__</div></div>
      <div class="cell"><div class="v red">__EXPIRED__</div><div class="k">已过期</div><div class="m">≈ ¥__EXPIREDV__</div></div>
      <div class="cell"><div class="v">__ACCUM__</div><div class="k">累计获得</div></div>
      <div class="cell"><div class="v">__MONTH__</div><div class="k">本月将过期</div></div>
    </div>
    <div class="alert">累计获得的积分里，有 <b>__WASTE__%</b> 已经蒸发掉了 —— 相当于白丢了 <b>¥__EXPIREDV__</b>。</div>
    <div class="alert amber">积分商城列表共 <b>__TOTAL__</b> 个商品，其中 <b>__DEAD__</b> 个其实已过期换不了（__DEADPCT__%），真正能换的只有 <b>__VALID__</b> 个。</div>
  </div>

  <div class="card">
    <h2>积分汇率榜 · 每 100 积分值多少元</h2>
    <div class="sub">汇率 = 兑换价 ÷ 所需积分 × 100，越高越划算</div>
    <table>
      <tr><th style="width:42%">商品</th><th>积分</th><th>兑换价</th><th style="width:26%">汇率</th></tr>
      __ROWS__
    </table>
    <div class="alert amber">小面额兑换远优于大面额：50 分的商品汇率是 800 分的 <b>5 倍</b>。攒着换大的，恰恰最亏。<br>还有个坑：列表里有两个同名「10.9元指定小食任选」，一个 100 分一个 200 分，不比对积分根本看不出。</div>
  </div>

  <div class="card">
    <h2>试算：你的积分怎么换最值</h2>
    <div class="sub">输入积分数，用动态规划算出预算内总价值最高的组合</div>
    <div class="calc">
      <input type="number" id="pts" value="__AVAIL__" min="0" max="10000" step="1">
      <button onclick="run()">算一下</button>
    </div>
    <div class="res" id="out"></div>
  </div>

  <div class="card">
    <h2>数据是真的，不是编的</h2>
    <div class="sub">全部来自麦当劳中国官方 MCP，35 个工具中本工具用到 5 个</div>
    <pre>{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn/mcp-servers/mcd-mcp",
      "headers": { "Authorization": "Bearer ${MCD_MCP_TOKEN}" }
    }
  }
}</pre>
    <div style="font-size:13px;margin-top:14px;color:#515154">
      Token 在 <b>open.mcd.cn/mcp</b> 免费申请（手机号登录 → 控制台 → 激活）。<br>
      用到的工具：<code>now-time-info</code>、<code>query-my-account</code>、<code>query-nearby-stores</code>、<code>mall-points-products</code>、<code>query-meals</code>。
    </div>
    <a class="star" href="__REPO__">⭐ 觉得有用？给这个项目点个 Star</a>
  </div>

  <div class="ft">
    本工具为麦当劳程序员创意开发大赛（M-CODE）参赛作品，由参赛者独立开发，<b>非麦当劳官方产品</b>。<br>
    积分、价格、商品有效期均来自麦当劳官方 MCP 实时接口，仅供参考，请以麦当劳官方渠道结果为准。<br>
    汇率 = 兑换价 ÷ 所需积分 × 100；试算结果按每种商品最多 5 件估算，实际可兑换次数以麦当劳规则为准。
  </div>
</div>

<script>
var ITEMS = __DATA__;
var COPIES = 5, CAP = 10000;

function fmt(n){ return (Math.round(n*100)/100).toFixed(1); }

function run(){
  var budget = parseInt(document.getElementById('pts').value, 10);
  if(isNaN(budget) || budget < 0){ budget = 0; }
  if(budget > CAP){ budget = CAP; }

  var all = [];
  for(var i=0;i<ITEMS.length;i++){
    for(var c=0;c<COPIES;c++){ all.push(ITEMS[i]); }
  }

  var dp = new Float64Array(budget+1);
  var pick = new Array(budget+1);
  for(var b=0;b<=budget;b++){ pick[b] = []; }

  for(var k=0;k<all.length;k++){
    var it = all[k];
    for(var b=budget;b>=it.point;b--){
      var cand = dp[b-it.point] + it.pay;
      if(cand > dp[b] + 1e-9){
        dp[b] = cand;
        pick[b] = pick[b-it.point].concat([it]);
      }
    }
  }

  var best = 0;
  for(var b=1;b<=budget;b++){ if(dp[b] > dp[best] + 1e-9){ best = b; } }
  var chosen = pick[best];
  var spent = 0;
  for(var j=0;j<chosen.length;j++){ spent += chosen[j].point; }

  var naive = null;
  for(var i=0;i<ITEMS.length;i++){
    if(ITEMS[i].point <= budget && (!naive || ITEMS[i].point > naive.point)){ naive = ITEMS[i]; }
  }

  var h = '';
  if(chosen.length === 0){
    h = '<div class="row"><span>这点积分还换不了任何东西</span><span>再攒攒</span></div>';
  } else {
    h += '<div class="row" style="color:#86868b;font-size:12px"><span>最优组合</span><span>汇率排序</span></div>';
    for(var j=0;j<chosen.length;j++){
      h += '<div class="row"><span>' + chosen[j].name + '</span><span>' + chosen[j].point + ' 分 · ¥' + fmt(chosen[j].pay) + '</span></div>';
    }
    h += '<div class="row tot"><span>合计</span><span>' + spent + ' 分 → ¥' + fmt(dp[best]) + '（剩 ' + (budget-spent) + ' 分）</span></div>';
    if(naive && dp[best] > naive.pay + 1e-9){
      h += '<div class="vs">'
         + '<div class="good"><div class="t">会换</div><div class="m">¥' + fmt(dp[best]) + '</div><div class="t">' + spent + ' 分换出一桌</div></div>'
         + '<div class="bad"><div class="t">不会换（全押最大额）</div><div class="m">¥' + fmt(naive.pay) + '</div><div class="t">剩 ' + (budget-naive.point) + ' 分用不掉</div></div>'
         + '</div>'
         + '<div class="gain">同样的积分，差 ' + (dp[best]/naive.pay).toFixed(2) + ' 倍</div>';
    }
  }
  document.getElementById('out').innerHTML = h;
}

run();
</script>
</body>
</html>
"""


def main():
    with open(SRC, encoding="utf-8") as f:
        r = json.load(f)

    a, v, m = r["account"], r["valuation"], r["market"]

    items = [{"name": x["name"], "point": x["point"], "pay": x["pay"], "rate": x["rate"]}
             for x in r["ranking"] if x.get("pay") is not None]

    rates = [i["rate"] for i in items if i["rate"]]
    mx = max(rates) if rates else 1
    rows = []
    for i in items:
        tag = ('<span class="tag hot">血赚</span>' if i["rate"] >= 10
               else ('<span class="tag bad">血亏</span>' if i["rate"] < 4 else ''))
        rows.append(
            '<tr><td>%s%s</td><td>%d</td><td>¥%s</td>'
            '<td><span class="bar" style="width:%.0fpx"></span> <b>%.2f</b></td></tr>'
            % (i["name"], tag, i["point"], i["pay"], max(i["rate"] / mx * 80, 8), i["rate"]))
    rows = "\n      ".join(rows)

    page = (TEMPLATE
            .replace("__DATA__", json.dumps(items, ensure_ascii=False))
            .replace("__ROWS__", rows)
            .replace("__AVAIL__", str(a["availablePoint"]))
            .replace("__AVAILV__", str(v["availableValue"]))
            .replace("__EXPIRED__", str(a["expiredPoint"]))
            .replace("__EXPIREDV__", str(v["expiredValue"]))
            .replace("__ACCUM__", str(a["accumulativePoint"]))
            .replace("__MONTH__", str(a["currentMouthExpirePoint"]))
            .replace("__WASTE__", str(v["wasteRatio"]))
            .replace("__TOTAL__", str(m["total"]))
            .replace("__DEAD__", str(m["expired"]))
            .replace("__DEADPCT__", str(int(v["mallDeadRatio"])))
            .replace("__VALID__", str(m["valid"]))
            .replace("__REPO__", "https://github.com/HAILONG1112223333/mcd-points-guard"))

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    print("试玩页已生成 → %s (%d 字节, %d 个商品)" % (OUT, len(page), len(items)))


if __name__ == "__main__":
    main()
