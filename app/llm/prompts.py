"""DeepSeek / AI 入手分析：system 提示词与 user 消息模板。

完整说明见 docs/AI_ANALYSIS.md。改提示词只动本文件即可。
"""
from __future__ import annotations

import json
from typing import Any

# ---------------------------------------------------------------------------
# System prompt（完整正文亦写入 docs/AI_ANALYSIS.md，两边保持同步）
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """你是电脑硬件购入顾问，只根据用户消息中提供的结构化数据做分析，不得编造未提供的事实（例如未给出的官方 MSRP、未采集的促销、未提及的竞品价）。

请用中文简明回答，结构建议：
1) **近期走势**：涨 / 跌 / 横盘、波动大小；可引用 history_stats 与 recent_candles。
2) **是否可能继续降价**：结合 forecast（方法、horizon、summary、metrics、forecast_candles），说明这是统计外推而非真实盘口，并标明不确定性。
3) **是否值得入手**：给出「观望 / 可买 / 谨慎」三级之一，并简述理由；若有 target_price，对比 latest_price。
4) **数据注意**：尊重 notes 中关于 outlier 过滤的说明；样本少时明确说依据不足。

语气客观、简短；用短段落 + 要点。不要输出 JSON，不要虚构数据源或新闻。"""


USER_INTRO = """请根据下列硬件价格数据，分析走势、是否可能降价、以及是否值得入手。
数据已排除明显不合理报价（见 payload.notes）。请严格基于 JSON 内字段作答。"""


def format_user_message(payload: dict[str, Any]) -> str:
    """用户消息：中文说明 + JSON 数据块。"""
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return f"{USER_INTRO}\n\n```json\n{body}\n```\n"


def build_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    """组装 Chat Completions 的 messages 列表。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": format_user_message(payload)},
    ]


# 兼容旧名
ANALYSIS_SYSTEM = SYSTEM_PROMPT
