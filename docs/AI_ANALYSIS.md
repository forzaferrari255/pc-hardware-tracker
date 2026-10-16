# AI 入手分析（DeepSeek）

本文说明：何时调用分析 API、离线行为、传给模型的 **system / user** 内容、payload 字段，以及相关环境变量。

提示词源码：[`app/llm/prompts.py`](../app/llm/prompts.py)  
客户端：[`app/llm/deepseek.py`](../app/llm/deepseek.py)  
Payload 组装：[`app/services.py`](../app/services.py) 中的 `build_analysis_payload`

---

## 何时调用

| 入口 | 说明 |
|------|------|
| `GET /api/analyze/{product_id}` | 对指定商品做「走势 + 是否降价 + 是否值得入手」分析 |
| 查询参数 | `method=sma\|ema\|linear`（默认 `ema`）、`horizon_days=1..90`（默认 14） |

单品页「AI 分析」按钮也会请求该接口。

调用前服务端会：

1. 拉取有效历史价并聚合成日 K；
2. 跑本地统计预测（SMA / EMA / 线性），得到 forecast；
3. 组装结构化 `payload`；
4. 若在线且配置了 `DEEPSEEK_API_KEY`，将 system + user 发给 DeepSeek Chat Completions。

无论 AI 是否成功，响应里都会带上 `forecast`（统计预测），便于离线时仍看本地外推。

---

## 离线行为

满足任一条件即视为「不可做 AI 分析」：

- 探测外网失败（连不上 `8.8.8.8:53` / `1.1.1.1:53`）；
- 环境变量 `FORCE_OFFLINE=1`；
- 未配置 `DEEPSEEK_API_KEY`。

此时接口返回例如：

```json
{
  "online": false,
  "analysis": null,
  "error": "当前离线（或 FORCE_OFFLINE=1），AI 预测分析不可用。本地历史价与图表仍可使用。",
  "forecast": { "...": "本地统计预测仍可用" }
}
```

**仍可用**：关注列表、历史价、日 K 图、SMA/EMA/线性预测。  
**不可用**：仅 DeepSeek 自然语言解读。

---

## System prompt（全文）

与 `app/llm/prompts.py` 中 `SYSTEM_PROMPT` 保持一致：

```
你是电脑硬件购入顾问，只根据用户消息中提供的结构化数据做分析，不得编造未提供的事实（例如未给出的官方 MSRP、未采集的促销、未提及的竞品价）。

请用中文简明回答，结构建议：
1) **近期走势**：涨 / 跌 / 横盘、波动大小；可引用 history_stats 与 recent_candles。
2) **是否可能继续降价**：结合 forecast（方法、horizon、summary、metrics、forecast_candles），说明这是统计外推而非真实盘口，并标明不确定性。
3) **是否值得入手**：给出「观望 / 可买 / 谨慎」三级之一，并简述理由；若有 target_price，对比 latest_price。
4) **数据注意**：尊重 notes 中关于 outlier 过滤的说明；样本少时明确说依据不足。

语气客观、简短；用短段落 + 要点。不要输出 JSON，不要虚构数据源或新闻。
```

要求摘要：

- **只基于给定数据**，不编造未提供事实；
- 分析走势、是否可能降价、是否值得入手（观望 / 可买 / 谨慎）；
- **标明不确定性**。

---

## User 消息格式

用户消息 = 一段中文说明 + ```json 数据块```。

说明文案（`USER_INTRO`）：

```
请根据下列硬件价格数据，分析走势、是否可能降价、以及是否值得入手。
数据已排除明显不合理报价（见 payload.notes）。请严格基于 JSON 内字段作答。
```

实际发送示例（结构示意）：

````markdown
请根据下列硬件价格数据，分析走势、是否可能降价、以及是否值得入手。
数据已排除明显不合理报价（见 payload.notes）。请严格基于 JSON 内字段作答。

```json
{
  "product": {
    "name": "NVIDIA GeForce RTX 5080 16G",
    "category": "gpu",
    "brand": "NVIDIA",
    "model": "RTX 5080 16G",
    "platform": "mock",
    "platform_name": "Mock 演示",
    "external_id": "gpu-rtx5080-16g"
  },
  "latest_price": 8999.0,
  "target_price": 8500.0,
  "history_stats": {
    "days": 60,
    "sample_points": 120,
    "raw_points": 125,
    "outliers_excluded": 5,
    "min_close": 8700.0,
    "max_close": 9800.0,
    "min_low": 8650.0,
    "max_high": 9900.0,
    "median_close": 9100.0,
    "mean_close": 9120.5,
    "change_7d_pct": -1.2,
    "change_30d_pct": -3.5,
    "change_full_pct": -5.0,
    "first_date": "2026-08-01",
    "last_date": "2026-10-15",
    "outlier_filter_note": "已排除 5 条明显离谱价（占位价、绝对阈值 …）；统计仅用有效样本。"
  },
  "recent_candles": [
    { "t": "2026-09-16", "o": 9200, "h": 9250, "l": 9150, "c": 9180 },
    { "t": "2026-10-15", "o": 9050, "h": 9100, "l": 8980, "c": 8999 }
  ],
  "forecast": {
    "method": "ema",
    "horizon_days": 14,
    "summary": "指数平滑…外推 14 天",
    "metrics": { "alpha": 0.25, "ema": 9050.0, "drift": -12.0, "forecast_range_ratio": 0.02 },
    "forecast_candles_summary": {
      "count": 14,
      "key_points": [ { "t": "…", "o": 0, "h": 0, "l": 0, "c": 0 } ],
      "min_low": 8800.0,
      "max_high": 9100.0,
      "end_close": 8850.0
    },
    "forecast_candles": [ { "t": "2026-10-16", "o": 8990, "h": 9050, "l": 8920, "c": 8980 } ]
  },
  "notes": [
    "数据已排除明显不合理报价…",
    "forecast 为本地统计外推…",
    "请勿编造未出现在本 JSON 中的事实。"
  ]
}
```
````

### 字段说明

| 字段 | 含义 |
|------|------|
| `product.name` | 商品名称 |
| `product.category` | 品类：`cpu` / `gpu` / `motherboard` / `ram` / `ssd` / `hdd` / `other` |
| `product.brand` / `model` | 品牌、型号（可空） |
| `product.platform` | 平台 code（如 `mock`、`jd`） |
| `product.platform_name` | 平台显示名 |
| `product.external_id` | 平台侧商品 ID |
| `latest_price` | 最新有效（非 outlier）价 |
| `target_price` | 关注目标价；未设则为 `null` |
| `history_stats.days` | 有效日 K 天数 |
| `history_stats.sample_points` | 有效采价点数 |
| `history_stats.raw_points` | 含 outlier 的原始点数 |
| `history_stats.outliers_excluded` | 已排除 outlier 条数 |
| `history_stats.min_close` / `max_close` | 收盘最低 / 最高 |
| `history_stats.min_low` / `max_high` | K 线最低 / 最高 |
| `history_stats.median_close` / `mean_close` | 收盘中位 / 均价 |
| `history_stats.change_7d_pct` / `change_30d_pct` | 近 7 / 30 日收盘涨跌幅（%） |
| `history_stats.change_full_pct` | 全样本首末涨跌幅（%） |
| `history_stats.outlier_filter_note` | 过滤规则说明 |
| `recent_candles` | 近 N 日（默认 30）OHLC：`t,o,h,l,c` |
| `forecast.method` | `sma` / `ema` / `linear` |
| `forecast.horizon_days` | 外推天数 |
| `forecast.summary` | 人类可读预测摘要 |
| `forecast.metrics` | 模型指标（窗口、斜率、α 等） |
| `forecast.forecast_candles` | 完整预测日 K |
| `forecast.forecast_candles_summary` | 预测段摘要（数量、关键点、高低、末日收盘） |
| `notes` | 给模型的约束说明（含「已排除离谱价」） |

组装函数：`build_analysis_payload(...)`；消息格式化：`format_user_message(payload)` / `build_messages(payload)`。

---

## 环境变量 `DEEPSEEK_*`

见项目根目录 `.env.example`：

| 变量 | 默认 | 说明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | （空） | API 密钥；**勿提交到仓库** |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | 兼容 OpenAI 的 Chat Completions 基址 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 模型名 |
| `FORCE_OFFLINE` | `0` | 设为 `1` 时强制跳过 LLM（测离线） |

请求路径：`{DEEPSEEK_BASE_URL}/v1/chat/completions`，`temperature=0.4`。

---

## 改提示词 / 改字段

1. 改文案 → 只编辑 `app/llm/prompts.py`，并同步更新本文「System prompt」与「User 消息」节。
2. 改传入字段 → 编辑 `build_analysis_payload`，并更新上表。
3. 本地验证 payload（无需联网）：

```python
from app.db import SessionLocal
from app.models import Product
from app.services import build_analysis_payload
from app.llm.prompts import format_user_message

db = SessionLocal()
p = db.get(Product, 1)
payload = build_analysis_payload(db, p)
print(format_user_message(payload))
```
