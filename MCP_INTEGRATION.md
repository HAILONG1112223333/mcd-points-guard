# MCP 集成说明

> 说明本项目实际使用的麦当劳 MCP Server、Tool、调用流程与业务价值。

## 一、MCP Server

| 项 | 值 |
|---|---|
| 名称 | `mcd-mcp`（麦当劳中国官方 MCP 服务） |
| 端点 | `https://mcp.mcd.cn/mcp-servers/mcd-mcp` |
| 协议 | MCP Streamable HTTP（JSON-RPC 2.0），协议版本 `2025-06-18` |
| 鉴权 | `Authorization: Bearer ${MCD_MCP_TOKEN}` |
| 限流 | 600 次 / 分钟（超限返回 429） |
| 工具总数 | 35 |
| 申请 | [open.mcd.cn/mcp](https://open.mcd.cn/mcp) 手机号登录 → 控制台 → 激活 |

配置模板见 `mcp-config.example.json`，**只含环境变量占位符，不含真实凭证**。

## 二、实际使用的 Tool

本项目使用其中 5 个（其中 4 个为冷门工具，赛道内少有人用）：

| Tool | 用途 | 为什么需要 |
|---|---|---|
| `now-time-info` | 当前时间与日期 | 判断积分商城商品是否在有效期内 |
| `query-my-account` | 可用 / 累计 / 冻结 / **已过期** / **本月将过期** 积分 | 整个项目的数据基石 |
| `query-nearby-stores` | 附近门店 `storeCode` | 价格随门店变化，汇率需绑定门店 |
| `mall-points-products` | 积分商城可兑换商品（名称 / 所需积分 / 上下架时间） | 汇率榜的数据源 |
| `query-meals` | 门店在售菜单与现价 | 「净省」口径的价格锚定 |

**未使用**：`mall-create-order`（真实扣积分，默认不调用，需用户明确授权并二次确认）、
`mall-product-detail`、`mall-order-list`，以及点餐 / 派对 / 抽奖等与本主题无关的工具。

## 三、调用流程

```
now-time-info ─────────────► now
        │
        ▼
query-my-account ──────────► 可用 / 累计 / 已过期 / 本月将过期
        │
        ▼
query-nearby-stores {address} ─► storeCode
        │                            │
        │                            ▼
        │                     query-meals {storeCode} ─► 菜单现价
        ▼
mall-points-products ───────► 商品列表（spuName / point / upTime / downTime）
        │
        ▼
  ┌────────────────── 本地计算（纯 Python 标准库）──────────────────┐
  │  filter_redeemable()  point>0 且 upTime ≤ now ≤ downTime       │
  │  compute_rates()      rate = pay / point × 100                 │
  │  optimize()           子集和 DP，预算内最大化总价值              │
  └────────────────────────────────────────────────────────────────┘
        │
        ▼
  体检报告（终端 / HTML）
```

**顺序不可调整**：`now` 决定商品是否有效；`storeCode` 决定查哪家门店的菜单。

## 四、业务价值

1. **把「积分余额」翻译成「人民币」** —— 用户看到"1025 分"无感，看到"≈ ¥55.9"才有决策依据
2. **暴露积分商城的有效性问题** —— 实测 23 个积分商品中 16 个已过期，列表不过滤
3. **给出可执行的兑换排序** —— 汇率榜 + 止损凑单，直接告诉用户先换哪个
4. **只读、不打扰** —— 默认不触发任何写操作与扣款

## 五、实测字段与坑位

以下均来自真实调用（2026-10-23），官方文档未写明：

| 坑 | 说明 |
|---|---|
| **单位方向不一致** | `calculate-price` 返回整数**分**；`mall-*` 与 `order-list` 返回**元**（字符串）。混用必错 |
| **数值多为字符串** | `availablePoint` / `point` / `currentPrice` 全是字符串，需显式转 float |
| **`point=0` 不是免费** | 表示**现金商品**（派对 / 品鉴会），不是积分兑换，必须过滤 |
| **`mall-points-products` 返回过期商品** | 需自行按 `upTime` / `downTime` 过滤，接口不区分上下架 |
| **同名不同分** | 存在两个「10.9元指定小食任选」，一个 100 分一个 200 分，需用 `spuId` 区分 |
| **`query-my-account` 字段命名** | `currentMouthExpirePoint`（注意是 Mouth 不是 Month）、`expiredPoint` |
| **`query-my-coupons` 可能返回纯文本** | 无券时返回「暂无可用优惠券」，不是 JSON，需容错 |
| **价格随门店变化** | 每次会话需先确定门店上下文，不能跨店套用 |
| **限流 429** | 600 次/分钟，探测时建议加间隔 |

## 六、错误处理

| 错误码 | 处理 |
|---|---|
| 401 | Token 无效 / 过期，提示重新激活 |
| 429 | 触发限流，降低请求频率 |
| 网络错误 | 端点回退：`.../mcp-servers/mcd-mcp` ↔ `https://mcp.mcd.cn` |

响应可能是裸 JSON 也可能是 SSE 流，客户端两种都做了解析。
