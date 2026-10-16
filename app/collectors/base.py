"""采集器抽象接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SearchResult:
    external_id: str
    name: str
    price: float | None
    url: str | None = None
    brand: str | None = None
    model: str | None = None
    category: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class PriceSnapshot:
    external_id: str
    price: float
    currency: str = "CNY"
    collected_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    title: str | None = None


class CollectorAdapter(ABC):
    """每个平台一个 adapter：search / get_price。"""

    code: str = "base"
    display_name: str = "Base"
    is_stub: bool = False

    @abstractmethod
    async def search(self, query: str, category: str | None = None, limit: int = 20) -> list[SearchResult]:
        ...

    @abstractmethod
    async def get_price(self, external_id: str) -> PriceSnapshot | None:
        ...

    def compliance_note(self) -> str:
        return "请遵守平台服务条款与当地法律，仅使用授权数据源。"
