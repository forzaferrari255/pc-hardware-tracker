"""简单可解释预测：移动平均 / 指数平滑 / 线性趋势；输出点与预测 K 线。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal, Protocol

import numpy as np

Method = Literal["sma", "ema", "linear"]


@dataclass
class ForecastPoint:
    at: datetime
    price: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None


@dataclass
class ForecastResult:
    method: str
    horizon_days: int
    points: list[ForecastPoint]
    summary: str
    metrics: dict = field(default_factory=dict)


class Forecaster(Protocol):
    def predict(
        self,
        timestamps: list[datetime],
        prices: list[float],
        horizon_days: int,
    ) -> ForecastResult: ...


def forecast(
    timestamps: list[datetime],
    prices: list[float],
    method: Method = "ema",
    horizon_days: int = 14,
    window: int = 7,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> ForecastResult:
    if len(prices) < 2:
        last_t = timestamps[-1] if timestamps else datetime.utcnow()
        last_p = prices[-1] if prices else 0.0
        pts = [
            ForecastPoint(last_t + timedelta(days=i + 1), last_p) for i in range(horizon_days)
        ]
        result = ForecastResult(method, horizon_days, pts, "样本不足，沿用最近价", {"n": len(prices)})
        return _attach_ohlc(result, prices, highs, lows)

    if method == "sma":
        result = _sma(timestamps, prices, horizon_days, window)
    elif method == "linear":
        result = _linear(timestamps, prices, horizon_days)
    else:
        result = _ema(timestamps, prices, horizon_days, window)
    return _attach_ohlc(result, prices, highs, lows)


def _recent_range_ratio(
    prices: list[float],
    highs: list[float] | None,
    lows: list[float] | None,
    lookback: int = 14,
) -> float:
    """相对振幅：用于把中枢价扩成 high/low。"""
    n = len(prices)
    if n == 0:
        return 0.02
    lb = min(lookback, n)
    if highs is not None and lows is not None and len(highs) == n and len(lows) == n:
        ratios = []
        for i in range(n - lb, n):
            c = prices[i] or 1.0
            ratios.append(max(0.0, (highs[i] - lows[i]) / abs(c)))
        if ratios:
            return float(max(0.008, min(0.12, np.median(ratios))))
    # 退化为收盘价波动
    segment = prices[-lb:]
    if len(segment) < 2:
        return 0.02
    rets = np.diff(segment) / np.maximum(np.abs(segment[:-1]), 1e-6)
    vol = float(np.std(rets)) if len(rets) else 0.02
    return float(max(0.008, min(0.12, vol * 2.5)))


def _attach_ohlc(
    result: ForecastResult,
    hist_closes: list[float],
    highs: list[float] | None,
    lows: list[float] | None,
) -> ForecastResult:
    rng = _recent_range_ratio(hist_closes, highs, lows)
    prev_close = hist_closes[-1] if hist_closes else (result.points[0].price if result.points else 0.0)
    for p in result.points:
        c = float(p.price)
        # 开盘贴近前收，带轻微跳空
        gap = (c - prev_close) * 0.35
        o = round(prev_close + gap, 2)
        half = abs(c) * rng * 0.5
        body_hi = max(o, c)
        body_lo = min(o, c)
        h = round(body_hi + half, 2)
        l = round(max(0.01, body_lo - half), 2)
        if h < body_hi:
            h = round(body_hi, 2)
        if l > body_lo:
            l = round(body_lo, 2)
        p.open = o
        p.high = h
        p.low = l
        p.close = c
        p.price = c
        prev_close = c
    result.metrics = {**result.metrics, "forecast_range_ratio": rng}
    return result


def _sma(
    timestamps: list[datetime], prices: list[float], horizon_days: int, window: int
) -> ForecastResult:
    w = min(window, len(prices))
    avg = float(np.mean(prices[-w:]))
    last_t = timestamps[-1]
    if len(prices) >= w:
        slope = (prices[-1] - prices[-w]) / max(w, 1)
    else:
        slope = 0.0
    pts = []
    for i in range(1, horizon_days + 1):
        pts.append(ForecastPoint(last_t + timedelta(days=i), round(avg + slope * i * 0.3, 2)))
    trend = "上行" if slope > 0 else ("下行" if slope < 0 else "横盘")
    return ForecastResult(
        "sma",
        horizon_days,
        pts,
        f"简单移动平均(窗口={w})，近期{trend}，外推 {horizon_days} 天",
        {"window": w, "sma": avg, "slope_per_day": slope},
    )


def _ema(
    timestamps: list[datetime], prices: list[float], horizon_days: int, window: int
) -> ForecastResult:
    alpha = 2 / (min(window, len(prices)) + 1)
    ema = float(prices[0])
    for p in prices[1:]:
        ema = alpha * p + (1 - alpha) * ema
    drift = (prices[-1] - ema) * 0.15
    last_t = timestamps[-1]
    pts = []
    level = ema
    for i in range(1, horizon_days + 1):
        level = level + drift
        pts.append(ForecastPoint(last_t + timedelta(days=i), round(level, 2)))
    direction = "偏多/上行" if drift > 0 else ("偏空/下行" if drift < 0 else "中性")
    return ForecastResult(
        "ema",
        horizon_days,
        pts,
        f"指数平滑(α={alpha:.3f})，信号{direction}，外推 {horizon_days} 天",
        {"alpha": alpha, "ema": ema, "drift": drift},
    )


def _linear(
    timestamps: list[datetime], prices: list[float], horizon_days: int
) -> ForecastResult:
    t0 = timestamps[0].timestamp()
    xs = np.array([(t.timestamp() - t0) / 86400.0 for t in timestamps], dtype=float)
    ys = np.array(prices, dtype=float)
    b, a = np.polyfit(xs, ys, 1)
    last_t = timestamps[-1]
    last_x = xs[-1]
    pts = []
    for i in range(1, horizon_days + 1):
        x = last_x + i
        pts.append(ForecastPoint(last_t + timedelta(days=i), round(float(a + b * x), 2)))
    trend = "上涨" if b > 0 else ("下跌" if b < 0 else "走平")
    return ForecastResult(
        "linear",
        horizon_days,
        pts,
        f"线性趋势拟合，斜率 {b:.2f} 元/天（{trend}），外推 {horizon_days} 天",
        {"intercept": float(a), "slope_per_day": float(b)},
    )
