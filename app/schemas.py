"""Pydantic API schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PlatformOut(BaseModel):
    id: int
    code: str
    name: str
    adapter: str
    enabled: bool

    model_config = {"from_attributes": True}


class ProductOut(BaseModel):
    id: int
    platform_id: int
    external_id: str
    name: str
    category: str
    brand: str | None = None
    model: str | None = None
    url: str | None = None

    model_config = {"from_attributes": True}


class WatchItemCreate(BaseModel):
    product_id: int | None = None
    platform_code: str = "mock"
    external_id: str | None = None
    name: str | None = None
    category: str = "other"
    brand: str | None = None
    model: str | None = None
    alias: str | None = None
    notes: str | None = None
    target_price: float | None = None


class WatchItemUpdate(BaseModel):
    alias: str | None = None
    notes: str | None = None
    target_price: float | None = None
    active: bool | None = None


class WatchItemOut(BaseModel):
    id: int
    product_id: int
    alias: str | None
    notes: str | None
    target_price: float | None
    active: bool
    created_at: datetime
    product: ProductOut
    latest_price: float | None = None
    latest_at: datetime | None = None

    model_config = {"from_attributes": True}


class PricePointOut(BaseModel):
    id: int
    price: float
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    close_price: float | None = None
    collected_at: datetime
    is_outlier: bool
    filter_reason: str | None = None
    source: str

    model_config = {"from_attributes": True}


class Candle(BaseModel):
    """日 K：t 为日期字符串 YYYY-MM-DD；o/h/l/c 开高低收。"""

    t: str
    o: float
    h: float
    l: float
    c: float


class ChartSeries(BaseModel):
    product_id: int
    name: str
    timestamps: list[str]
    prices: list[float]
    candles: list[Candle] = Field(default_factory=list)
    forecast_candles: list[Candle] = Field(default_factory=list)
    ma7: list[float | None] = Field(default_factory=list)
    ma30: list[float | None] = Field(default_factory=list)
    outliers_excluded: int = 0


class ForecastOut(BaseModel):
    method: str
    horizon_days: int
    summary: str
    metrics: dict[str, Any]
    timestamps: list[str]
    prices: list[float]
    candles: list[Candle] = Field(default_factory=list)


class AnalyzeOut(BaseModel):
    online: bool
    analysis: str | None = None
    error: str | None = None
    forecast: ForecastOut | None = None


class HealthOut(BaseModel):
    status: str
    online: bool
    deepseek_configured: bool
    adapters: list[dict]


class SearchHit(BaseModel):
    platform: str
    external_id: str
    name: str
    price: float | None
    category: str | None = None
    brand: str | None = None
    model: str | None = None
    url: str | None = None


class CollectResult(BaseModel):
    product_id: int
    price: float | None
    accepted: bool
    reason: str | None = None
