"""演示用 Mock 采集器：确定性伪随机价格，便于无真实爬虫演示。"""
from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone

from app.collectors.base import CollectorAdapter, PriceSnapshot, SearchResult
from app.collectors.registry import register_adapter

# 演示商品目录
CATALOG: list[dict] = [
    {
        "external_id": "mock-rtx5080-16g",
        "name": "NVIDIA GeForce RTX 5080 16G 公版/同规格",
        "category": "gpu",
        "brand": "NVIDIA",
        "model": "RTX 5080 16G",
        "base_price": 8999.0,
    },
    {
        "external_id": "mock-rtx5070ti-16g",
        "name": "NVIDIA GeForce RTX 5070 Ti 16G",
        "category": "gpu",
        "brand": "NVIDIA",
        "model": "RTX 5070 Ti 16G",
        "base_price": 6499.0,
    },
    {
        "external_id": "mock-r7-9700x",
        "name": "AMD Ryzen 7 9700X",
        "category": "cpu",
        "brand": "AMD",
        "model": "R7 9700X",
        "base_price": 2499.0,
    },
    {
        "external_id": "mock-i7-14700k",
        "name": "Intel Core i7-14700K",
        "category": "cpu",
        "brand": "Intel",
        "model": "i7-14700K",
        "base_price": 2699.0,
    },
    {
        "external_id": "mock-b650-tomahawk",
        "name": "MSI MAG B650 TOMAHAWK WIFI",
        "category": "motherboard",
        "brand": "MSI",
        "model": "B650 TOMAHAWK",
        "base_price": 1599.0,
    },
    {
        "external_id": "mock-ddr5-6000-32g",
        "name": "金士顿 FURY Beast DDR5 6000 32GB(16Gx2)",
        "category": "ram",
        "brand": "Kingston",
        "model": "DDR5-6000 32G",
        "base_price": 699.0,
    },
    {
        "external_id": "mock-990pro-2t",
        "name": "三星 990 PRO 2TB NVMe SSD",
        "category": "ssd",
        "brand": "Samsung",
        "model": "990 PRO 2TB",
        "base_price": 1099.0,
    },
    {
        "external_id": "mock-wd-red-8t",
        "name": "西数红盘 Plus 8TB HDD",
        "category": "hdd",
        "brand": "WD",
        "model": "Red Plus 8TB",
        "base_price": 1299.0,
    },
]


def _day_seed(external_id: str, day_offset: int = 0) -> float:
    raw = f"{external_id}:{day_offset}".encode()
    h = int(hashlib.md5(raw).hexdigest()[:8], 16)
    return (h % 10000) / 10000.0


class MockAdapter(CollectorAdapter):
    code = "mock"
    display_name = "Mock 演示数据"
    is_stub = False

    async def search(self, query: str, category: str | None = None, limit: int = 20) -> list[SearchResult]:
        q = query.lower()
        out: list[SearchResult] = []
        for item in CATALOG:
            if category and item["category"] != category:
                continue
            hay = f"{item['name']} {item['model']} {item['brand']}".lower()
            if q not in hay and not all(t in hay for t in q.split()):
                # 宽松：任一关键词命中
                if not any(t in hay for t in q.split() if len(t) > 1):
                    continue
            price = self._price_now(item)
            out.append(
                SearchResult(
                    external_id=item["external_id"],
                    name=item["name"],
                    price=price,
                    url=f"https://example.local/mock/{item['external_id']}",
                    brand=item["brand"],
                    model=item["model"],
                    category=item["category"],
                )
            )
            if len(out) >= limit:
                break
        return out

    async def get_price(self, external_id: str) -> PriceSnapshot | None:
        item = next((x for x in CATALOG if x["external_id"] == external_id), None)
        if not item:
            return None
        close = self._price_now(item)
        # 单次采样也给出当日近似 OHLC，便于聚合成 K 线
        wick = close * 0.012
        o = round(close * (1 - 0.003), 2)
        h = round(max(o, close) + wick, 2)
        l = round(min(o, close) - wick, 2)
        return PriceSnapshot(
            external_id=external_id,
            price=close,
            collected_at=datetime.now(timezone.utc),
            title=item["name"],
            raw={
                "source": "mock",
                "base": item["base_price"],
                "open": o,
                "high": h,
                "low": l,
                "close": close,
            },
        )

    def _price_now(self, item: dict) -> float:
        # 轻微日波动 + 缓降趋势
        r = _day_seed(item["external_id"], 0)
        drift = -0.02 * math.sin(r * math.pi * 2)
        noise = (r - 0.5) * 0.04
        return round(item["base_price"] * (1 + drift + noise), 2)

    def compliance_note(self) -> str:
        return "本地合成演示数据，不访问真实电商平台。"


register_adapter(MockAdapter())
