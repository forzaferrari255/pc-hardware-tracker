"""用户配置的合规 HTTP JSON 数据源。

期望响应示例（GET）：
  {"external_id":"x","price":8999.0,"currency":"CNY","title":"..."}
或列表：
  [{"external_id":"x","price":8999.0}, ...]

环境 / 平台 config_json 可存：
  {"base_url":"https://your-api.example/prices","search_path":"/search","price_path":"/item/{id}"}
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx

from app.collectors.base import CollectorAdapter, PriceSnapshot, SearchResult
from app.collectors.registry import register_adapter


class HttpJsonAdapter(CollectorAdapter):
    code = "http_json"
    display_name = "自定义 HTTP JSON"
    is_stub = False

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    def with_config(self, config: dict[str, Any]) -> "HttpJsonAdapter":
        return HttpJsonAdapter(config)

    async def search(self, query: str, category: str | None = None, limit: int = 20) -> list[SearchResult]:
        base = self.config.get("base_url")
        path = self.config.get("search_path", "/search")
        if not base:
            return []
        params: dict[str, Any] = {"q": query, "limit": limit}
        if category:
            params["category"] = category
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(f"{base.rstrip('/')}{path}", params=params)
            r.raise_for_status()
            data = r.json()
        items = data if isinstance(data, list) else data.get("items", [])
        out: list[SearchResult] = []
        for it in items[:limit]:
            out.append(
                SearchResult(
                    external_id=str(it.get("external_id") or it.get("id")),
                    name=it.get("name") or it.get("title") or "",
                    price=_as_float(it.get("price")),
                    url=it.get("url"),
                    brand=it.get("brand"),
                    model=it.get("model"),
                    category=it.get("category") or category,
                    extra=it if isinstance(it, dict) else {},
                )
            )
        return out

    async def get_price(self, external_id: str) -> PriceSnapshot | None:
        base = self.config.get("base_url")
        path_tpl = self.config.get("price_path", "/item/{id}")
        if not base:
            return None
        path = path_tpl.format(id=external_id)
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(f"{base.rstrip('/')}{path}")
            if r.status_code == 404:
                return None
            r.raise_for_status()
            data = r.json()
        if isinstance(data, list):
            data = next((x for x in data if str(x.get("external_id") or x.get("id")) == external_id), None)
            if not data:
                return None
        price = _as_float(data.get("price"))
        if price is None:
            return None
        return PriceSnapshot(
            external_id=external_id,
            price=price,
            currency=data.get("currency") or "CNY",
            collected_at=datetime.now(timezone.utc),
            title=data.get("title") or data.get("name"),
            raw=data if isinstance(data, dict) else {"raw": data},
        )

    def compliance_note(self) -> str:
        return "仅请求用户明确授权的 JSON API；勿指向需登录绕过的页面。"


def _as_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


register_adapter(HttpJsonAdapter())
