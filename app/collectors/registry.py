"""Adapter 注册表。"""
from __future__ import annotations

from app.collectors.base import CollectorAdapter

_REGISTRY: dict[str, CollectorAdapter] = {}


def register_adapter(adapter: CollectorAdapter) -> None:
    _REGISTRY[adapter.code] = adapter


def get_adapter(code: str) -> CollectorAdapter:
    if code not in _REGISTRY:
        raise KeyError(f"未知采集器: {code}，已注册: {list(_REGISTRY)}")
    return _REGISTRY[code]


def list_adapters() -> list[dict]:
    return [
        {
            "code": a.code,
            "display_name": a.display_name,
            "is_stub": a.is_stub,
            "compliance_note": a.compliance_note(),
        }
        for a in _REGISTRY.values()
    ]
