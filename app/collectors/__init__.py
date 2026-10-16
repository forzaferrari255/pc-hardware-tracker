"""可插拔采集器：按平台 code 注册 adapter。"""
from app.collectors.base import PriceSnapshot, SearchResult, CollectorAdapter
from app.collectors.registry import get_adapter, list_adapters, register_adapter

# 侧效导入：注册内置 adapter
from app.collectors import mock as _mock  # noqa: F401
from app.collectors import manual_csv as _manual  # noqa: F401
from app.collectors import http_json as _http  # noqa: F401
from app.collectors import stubs as _stubs  # noqa: F401

__all__ = [
    "PriceSnapshot",
    "SearchResult",
    "CollectorAdapter",
    "get_adapter",
    "list_adapters",
    "register_adapter",
]
