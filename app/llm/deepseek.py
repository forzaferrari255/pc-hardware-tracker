"""DeepSeek Chat Completions（OpenAI 兼容）+ 离线检测。"""
from __future__ import annotations

import socket
from typing import Any

import httpx

from app.config import get_settings
from app.llm.prompts import SYSTEM_PROMPT, build_messages, format_user_message


class OfflineError(RuntimeError):
    """无网或强制离线时抛出。"""


def is_online(timeout: float = 2.0) -> bool:
    """探测是否可访问外网；FORCE_OFFLINE=1 时恒为 False。"""
    settings = get_settings()
    if settings.force_offline:
        return False
    try:
        socket.setdefaulttimeout(timeout)
        with socket.create_connection(("8.8.8.8", 53), timeout=timeout):
            return True
    except OSError:
        try:
            with socket.create_connection(("1.1.1.1", 53), timeout=timeout):
                return True
        except OSError:
            return False


class DeepSeekClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.deepseek_api_key)

    async def analyze_purchase(self, payload: dict[str, Any]) -> str:
        """用结构化 payload 调用 DeepSeek；提示词见 app.llm.prompts。"""
        if not is_online():
            raise OfflineError(
                "当前离线（或 FORCE_OFFLINE=1），AI 预测分析不可用。本地历史价与图表仍可使用。"
            )
        if not self.configured:
            raise OfflineError("未配置 DEEPSEEK_API_KEY，无法调用 AI 分析。请在 .env 中设置。")

        messages = build_messages(payload)
        return await self.chat_messages(messages)

    async def chat(self, system: str, user: str) -> str:
        return await self.chat_messages(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        )

    async def chat_messages(self, messages: list[dict[str, str]]) -> str:
        if not is_online():
            raise OfflineError("当前离线，AI 功能不可用。")
        if not self.configured:
            raise OfflineError("未配置 DEEPSEEK_API_KEY。")

        url = self.settings.deepseek_base_url.rstrip("/") + "/v1/chat/completions"
        body: dict[str, Any] = {
            "model": self.settings.deepseek_model,
            "messages": messages,
            "temperature": 0.4,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, json=body, headers=headers)
            r.raise_for_status()
            data = r.json()
        return data["choices"][0]["message"]["content"]


# 再导出，便于文档/测试引用
__all__ = [
    "DeepSeekClient",
    "OfflineError",
    "is_online",
    "SYSTEM_PROMPT",
    "format_user_message",
]
