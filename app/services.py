"""业务逻辑：关注、采价、图表、预测、日 K 聚合。"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean, median

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.cleaning.filters import PriceFilter
from app.config import get_settings
from app.collectors import get_adapter
from app.forecast.models import forecast as run_forecast
from app.models import Platform, PricePoint, Product, WatchItem


def ensure_default_platforms(db: Session) -> None:
    defaults = [
        ("mock", "Mock 演示", "mock"),
        ("manual_csv", "手动 CSV", "manual_csv"),
        ("http_json", "HTTP JSON", "http_json"),
        ("jd", "京东", "jd"),
        ("taobao", "淘宝/天猫", "taobao"),
        ("pdd", "拼多多", "pdd"),
    ]
    for code, name, adapter in defaults:
        exists = db.scalar(select(Platform).where(Platform.code == code))
        if not exists:
            db.add(Platform(code=code, name=name, adapter=adapter, enabled=True))
    db.commit()


def get_or_create_product(
    db: Session,
    *,
    platform_code: str,
    external_id: str,
    name: str,
    category: str = "other",
    brand: str | None = None,
    model: str | None = None,
    url: str | None = None,
) -> Product:
    plat = db.scalar(select(Platform).where(Platform.code == platform_code))
    if not plat:
        raise ValueError(f"未知平台 {platform_code}")
    prod = db.scalar(
        select(Product).where(Product.platform_id == plat.id, Product.external_id == external_id)
    )
    if prod:
        return prod
    prod = Product(
        platform_id=plat.id,
        external_id=external_id,
        name=name,
        category=category,
        brand=brand,
        model=model,
        url=url,
    )
    db.add(prod)
    db.commit()
    db.refresh(prod)
    return prod


def latest_clean_price(db: Session, product_id: int) -> tuple[float | None, datetime | None]:
    row = db.scalar(
        select(PricePoint)
        .where(PricePoint.product_id == product_id, PricePoint.is_outlier.is_(False))
        .order_by(PricePoint.collected_at.desc())
        .limit(1)
    )
    if not row:
        return None, None
    return row.price, row.collected_at


def list_watch(db: Session, active_only: bool = True) -> list[WatchItem]:
    q = select(WatchItem).options(joinedload(WatchItem.product).joinedload(Product.platform))
    if active_only:
        q = q.where(WatchItem.active.is_(True))
    return list(db.scalars(q).unique().all())


def add_price_point(
    db: Session,
    product_id: int,
    price: float,
    *,
    source: str = "collector",
    collected_at: datetime | None = None,
    raw: dict | None = None,
    open_price: float | None = None,
    high_price: float | None = None,
    low_price: float | None = None,
    close_price: float | None = None,
) -> PricePoint:
    hist_rows = db.scalars(
        select(PricePoint)
        .where(PricePoint.product_id == product_id, PricePoint.is_outlier.is_(False))
        .order_by(PricePoint.collected_at.asc())
    ).all()
    history = [r.price for r in hist_rows]
    fr = PriceFilter().check(price, history)
    close = close_price if close_price is not None else price
    pp = PricePoint(
        product_id=product_id,
        price=price,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close,
        collected_at=collected_at or datetime.now(timezone.utc).replace(tzinfo=None),
        source=source,
        is_outlier=not fr.accepted,
        filter_reason=fr.reason,
        raw_json=json.dumps(raw, ensure_ascii=False) if raw else None,
    )
    db.add(pp)
    db.commit()
    db.refresh(pp)
    return pp


async def collect_product(db: Session, product: Product) -> PricePoint | None:
    plat = product.platform or db.get(Platform, product.platform_id)
    if not plat:
        return None
    adapter = get_adapter(plat.adapter)
    if adapter.is_stub:
        return None
    snap = await adapter.get_price(product.external_id)
    if not snap:
        return None
    raw = snap.raw or {}
    return add_price_point(
        db,
        product.id,
        snap.price,
        source=adapter.code,
        collected_at=(snap.collected_at.replace(tzinfo=None) if snap.collected_at else None),
        raw=raw,
        open_price=raw.get("open") or raw.get("open_price"),
        high_price=raw.get("high") or raw.get("high_price"),
        low_price=raw.get("low") or raw.get("low_price"),
        close_price=raw.get("close") or raw.get("close_price") or snap.price,
    )


def _day_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def aggregate_daily_candles(rows: list[PricePoint]) -> list[dict]:
    """将价格点按日聚合成 OHLC；有字段则用字段，否则用当日多次价推导。"""
    buckets: dict[str, list[PricePoint]] = defaultdict(list)
    for r in rows:
        buckets[_day_key(r.collected_at)].append(r)

    candles: list[dict] = []
    for day in sorted(buckets.keys()):
        pts = sorted(buckets[day], key=lambda x: x.collected_at)
        closes = [(p.close_price if p.close_price is not None else p.price) for p in pts]
        opens_explicit = [p.open_price for p in pts if p.open_price is not None]
        highs_explicit = [p.high_price for p in pts if p.high_price is not None]
        lows_explicit = [p.low_price for p in pts if p.low_price is not None]
        prices = [p.price for p in pts]

        o = opens_explicit[0] if opens_explicit else prices[0]
        c = closes[-1]
        if highs_explicit:
            h = max(highs_explicit + [o, c])
        else:
            h = max(prices + [o, c])
        if lows_explicit:
            l = min(lows_explicit + [o, c])
        else:
            l = min(prices + [o, c])
        candles.append(
            {
                "t": day,
                "o": round(float(o), 2),
                "h": round(float(h), 2),
                "l": round(float(l), 2),
                "c": round(float(c), 2),
            }
        )
    return candles


def chart_data(
    db: Session,
    product_id: int,
    *,
    days: int | None = 90,
    include_outliers: bool = False,
    forecast_method: str = "ema",
    horizon_days: int = 14,
) -> dict:
    q = select(PricePoint).where(PricePoint.product_id == product_id)
    if not include_outliers:
        q = q.where(PricePoint.is_outlier.is_(False))
    if days:
        since = datetime.utcnow() - timedelta(days=days)
        q = q.where(PricePoint.collected_at >= since)
    rows = list(db.scalars(q.order_by(PricePoint.collected_at.asc())).all())
    product = db.get(Product, product_id)
    candles = aggregate_daily_candles(rows)
    closes = [c["c"] for c in candles]
    ts = [c["t"] for c in candles]
    ma7 = _moving_avg(closes, 7)
    ma30 = _moving_avg(closes, 30)

    from sqlalchemy import func

    n_out = db.scalar(
        select(func.count()).select_from(PricePoint).where(
            PricePoint.product_id == product_id, PricePoint.is_outlier.is_(True)
        )
    )

    fc_candles: list[dict] = []
    if closes:
        fc = build_forecast(
            db, product_id, method=forecast_method, horizon_days=horizon_days, days=days
        )
        fc_candles = [
            {
                "t": p.at.strftime("%Y-%m-%d"),
                "o": float(p.open if p.open is not None else p.price),
                "h": float(p.high if p.high is not None else p.price),
                "l": float(p.low if p.low is not None else p.price),
                "c": float(p.close if p.close is not None else p.price),
            }
            for p in fc.points
        ]

    return {
        "product_id": product_id,
        "name": product.name if product else "",
        "timestamps": ts,
        "prices": closes,
        "candles": candles,
        "forecast_candles": fc_candles,
        "ma7": ma7,
        "ma30": ma30,
        "outliers_excluded": int(n_out or 0),
    }


def _moving_avg(prices: list[float], window: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(prices)):
        if i + 1 < window:
            out.append(None)
        else:
            out.append(round(mean(prices[i + 1 - window : i + 1]), 2))
    return out


def history_summary(db: Session, product_id: int) -> str:
    rows = list(
        db.scalars(
            select(PricePoint)
            .where(PricePoint.product_id == product_id, PricePoint.is_outlier.is_(False))
            .order_by(PricePoint.collected_at.asc())
        ).all()
    )
    if not rows:
        return "无有效历史价格"
    candles = aggregate_daily_candles(rows)
    prices = [c["c"] for c in candles] or [r.price for r in rows]
    first, last = prices[0], prices[-1]
    chg = (last - first) / first * 100 if first else 0
    hi = max(c["h"] for c in candles) if candles else max(prices)
    lo = min(c["l"] for c in candles) if candles else min(prices)
    return (
        f"样本 {len(candles)} 日 K；区间低 {lo:.2f}–高 {hi:.2f}；"
        f"中位收盘 {median(prices):.2f}；首末变化 {chg:+.2f}%；"
        f"最新收盘 {last:.2f}（{candles[-1]['t'] if candles else rows[-1].collected_at.isoformat()}）"
    )


def build_forecast(
    db: Session,
    product_id: int,
    method: str = "ema",
    horizon_days: int = 14,
    days: int | None = None,
):
    q = select(PricePoint).where(
        PricePoint.product_id == product_id, PricePoint.is_outlier.is_(False)
    )
    if days:
        since = datetime.utcnow() - timedelta(days=days)
        q = q.where(PricePoint.collected_at >= since)
    rows = list(db.scalars(q.order_by(PricePoint.collected_at.asc())).all())
    candles = aggregate_daily_candles(rows)
    if candles:
        ts = [datetime.strptime(c["t"], "%Y-%m-%d") for c in candles]
        prices = [c["c"] for c in candles]
        highs = [c["h"] for c in candles]
        lows = [c["l"] for c in candles]
    else:
        ts = [r.collected_at for r in rows]
        prices = [r.price for r in rows]
        highs = lows = None
    result = run_forecast(
        ts, prices, method=method, horizon_days=horizon_days, highs=highs, lows=lows  # type: ignore[arg-type]
    )
    return result


def _pct_change(prices: list[float], lookback: int) -> float | None:
    """相对 lookback 日前收盘的涨跌幅（%）；样本不足返回 None。"""
    if len(prices) < 2:
        return None
    if lookback <= 0:
        return None
    if len(prices) <= lookback:
        base = prices[0]
    else:
        base = prices[-(lookback + 1)]
    last = prices[-1]
    if not base:
        return None
    return round((last - base) / base * 100.0, 2)


def build_history_stats(
    db: Session,
    product_id: int,
    *,
    candles: list[dict] | None = None,
) -> dict:
    """历史统计：天数、高低中位均价、近 7/30 日变化%、样本数、outlier 说明。"""
    from sqlalchemy import func

    clean_rows = list(
        db.scalars(
            select(PricePoint)
            .where(PricePoint.product_id == product_id, PricePoint.is_outlier.is_(False))
            .order_by(PricePoint.collected_at.asc())
        ).all()
    )
    n_outliers = db.scalar(
        select(func.count())
        .select_from(PricePoint)
        .where(PricePoint.product_id == product_id, PricePoint.is_outlier.is_(True))
    )
    n_raw = db.scalar(
        select(func.count()).select_from(PricePoint).where(PricePoint.product_id == product_id)
    )

    if candles is None:
        candles = aggregate_daily_candles(clean_rows)
    closes = [c["c"] for c in candles]
    settings = get_settings()

    if not closes:
        return {
            "days": 0,
            "sample_points": len(clean_rows),
            "raw_points": int(n_raw or 0),
            "outliers_excluded": int(n_outliers or 0),
            "min_close": None,
            "max_close": None,
            "min_low": None,
            "max_high": None,
            "median_close": None,
            "mean_close": None,
            "change_7d_pct": None,
            "change_30d_pct": None,
            "change_full_pct": None,
            "outlier_filter_note": (
                f"已排除 is_outlier=True 的报价；规则含占位价、绝对阈值"
                f"（{settings.filter_min_price}–{settings.filter_max_price}）、"
                f"相对中位数偏离>{settings.filter_median_deviation_ratio:.0%}、"
                f"Z-score>{settings.filter_zscore_threshold}。"
            ),
        }

    return {
        "days": len(candles),
        "sample_points": len(clean_rows),
        "raw_points": int(n_raw or 0),
        "outliers_excluded": int(n_outliers or 0),
        "min_close": round(min(closes), 2),
        "max_close": round(max(closes), 2),
        "min_low": round(min(c["l"] for c in candles), 2),
        "max_high": round(max(c["h"] for c in candles), 2),
        "median_close": round(float(median(closes)), 2),
        "mean_close": round(float(mean(closes)), 2),
        "change_7d_pct": _pct_change(closes, 7),
        "change_30d_pct": _pct_change(closes, 30),
        "change_full_pct": _pct_change(closes, max(len(closes) - 1, 1)),
        "first_date": candles[0]["t"],
        "last_date": candles[-1]["t"],
        "outlier_filter_note": (
            f"已排除 {int(n_outliers or 0)} 条明显不合理价（占位价、绝对阈值 "
            f"{settings.filter_min_price}–{settings.filter_max_price}、"
            f"相对中位数偏离>{settings.filter_median_deviation_ratio:.0%}、"
            f"Z-score>{settings.filter_zscore_threshold}）；统计仅用有效样本。"
        ),
    }


def build_analysis_payload(
    db: Session,
    product: Product,
    *,
    method: str = "ema",
    horizon_days: int = 14,
    recent_candle_days: int = 30,
    forecast_result=None,
    latest_price: float | None = None,
    target_price: float | None = None,
) -> dict:
    """组装传给 DeepSeek 的结构化 payload（见 docs/AI_ANALYSIS.md）。"""
    plat = product.platform or db.get(Platform, product.platform_id)
    platform_code = plat.code if plat else None
    platform_name = plat.name if plat else None

    clean_rows = list(
        db.scalars(
            select(PricePoint)
            .where(PricePoint.product_id == product.id, PricePoint.is_outlier.is_(False))
            .order_by(PricePoint.collected_at.asc())
        ).all()
    )
    all_candles = aggregate_daily_candles(clean_rows)
    history_stats = build_history_stats(db, product.id, candles=all_candles)

    recent = all_candles[-recent_candle_days:] if all_candles else []

    if forecast_result is None:
        forecast_result = build_forecast(
            db, product.id, method=method, horizon_days=horizon_days
        )

    fc_candles = [
        {
            "t": p.at.strftime("%Y-%m-%d"),
            "o": float(p.open if p.open is not None else p.price),
            "h": float(p.high if p.high is not None else p.price),
            "l": float(p.low if p.low is not None else p.price),
            "c": float(p.close if p.close is not None else p.price),
        }
        for p in forecast_result.points
    ]
    # 摘要：首/中/末 + 区间高低，避免 token 过长时仍保留关键信息
    fc_summary_candles: list[dict] = []
    if fc_candles:
        idxs = {0, len(fc_candles) // 2, len(fc_candles) - 1}
        fc_summary_candles = [fc_candles[i] for i in sorted(idxs)]
        fc_hi = max(c["h"] for c in fc_candles)
        fc_lo = min(c["l"] for c in fc_candles)
        fc_end = fc_candles[-1]["c"]
    else:
        fc_hi = fc_lo = fc_end = None

    if latest_price is None:
        latest_price, _ = latest_clean_price(db, product.id)

    return {
        "product": {
            "name": product.name,
            "category": product.category,
            "brand": product.brand,
            "model": product.model,
            "platform": platform_code,
            "platform_name": platform_name,
            "external_id": product.external_id,
        },
        "latest_price": latest_price,
        "target_price": target_price,
        "history_stats": history_stats,
        "recent_candles": recent,
        "forecast": {
            "method": forecast_result.method,
            "horizon_days": forecast_result.horizon_days,
            "summary": forecast_result.summary,
            "metrics": forecast_result.metrics,
            "forecast_candles_summary": {
                "count": len(fc_candles),
                "key_points": fc_summary_candles,
                "min_low": fc_lo,
                "max_high": fc_hi,
                "end_close": fc_end,
            },
            "forecast_candles": fc_candles,
        },
        "notes": [
            "数据已排除明显不合理报价（占位价、绝对阈值、中位数偏离、Z-score 等），见 history_stats.outlier_filter_note。",
            "forecast 为本地统计外推（SMA/EMA/线性），预测 K 线高低价按近期振幅合成，非真实盘口。",
            "请勿编造未出现在本 JSON 中的事实。",
        ],
    }
