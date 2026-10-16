#!/usr/bin/env python3
"""写入演示数据（含日 OHLC K 线 + 故意脏数据以验证过滤）。"""
from __future__ import annotations

import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.collectors.mock import CATALOG  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import PricePoint, Product, WatchItem  # noqa: E402
from app.services import (  # noqa: E402
    add_price_point,
    ensure_default_platforms,
    get_or_create_product,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def synth_ohlc(base: float, days: int = 60) -> list[tuple[datetime, float, float, float, float]]:
    """生成日 K：返回 (day_noon, open, high, low, close)。"""
    out = []
    start = _utcnow() - timedelta(days=days)
    prev_close = base
    for i in range(days + 1):
        t = (start + timedelta(days=i)).replace(hour=12, minute=0, second=0, microsecond=0)
        trend = 1.0 - 0.08 * (i / max(days, 1))
        noise = 0.015 * math.sin(i / 3.2) + 0.01 * math.cos(i / 7.1)
        close = round(base * (trend + noise), 2)
        # 开盘贴近前收，带小跳空
        gap = (close - prev_close) * 0.4
        open_p = round(prev_close + gap, 2)
        body_hi = max(open_p, close)
        body_lo = min(open_p, close)
        # 影线：相对振幅约 1.2%~2.5%
        wick = abs(close) * (0.012 + 0.008 * abs(math.sin(i / 5.0)))
        high = round(body_hi + wick, 2)
        low = round(max(0.01, body_lo - wick), 2)
        out.append((t, open_p, high, low, close))
        prev_close = close
    return out


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        ensure_default_platforms(db)

        for item in CATALOG:
            prod = get_or_create_product(
                db,
                platform_code="mock",
                external_id=item["external_id"],
                name=item["name"],
                category=item["category"],
                brand=item["brand"],
                model=item["model"],
                url=f"https://example.local/mock/{item['external_id']}",
            )

            db.query(PricePoint).filter(PricePoint.product_id == prod.id).delete()
            db.commit()
            for t, o, h, l, c in synth_ohlc(item["base_price"], days=60):
                db.add(
                    PricePoint(
                        product_id=prod.id,
                        price=c,
                        open_price=o,
                        high_price=h,
                        low_price=l,
                        close_price=c,
                        collected_at=t,
                        source="seed",
                        is_outlier=False,
                        filter_reason=None,
                    )
                )
            db.commit()

            dirty = [
                (1.0, "one_yuan"),
                (0.01, "placeholder"),
                (9.9, "fake_promo"),
                (item["base_price"] * 0.05, "too_low_vs_median"),
                (item["base_price"] * 5.0, "too_high_vs_median"),
                (999999.0, "placeholder_max"),
            ]
            now = _utcnow()
            for price, tag in dirty:
                add_price_point(
                    db,
                    prod.id,
                    price,
                    source=f"seed_dirty:{tag}",
                    collected_at=now,
                    raw={"tag": tag},
                )

            watch_aliases = {
                "mock-rtx5080-16g": ("RTX 5080 16G", 8500.0),
                "mock-r7-9700x": ("R7 9700X", 2300.0),
                "mock-990pro-2t": ("990 PRO 2T", 999.0),
            }
            if item["external_id"] in watch_aliases:
                alias, target = watch_aliases[item["external_id"]]
                existing = db.query(WatchItem).filter(WatchItem.product_id == prod.id).first()
                if not existing:
                    db.add(
                        WatchItem(
                            product_id=prod.id,
                            alias=alias,
                            target_price=target,
                            notes="演示关注",
                        )
                    )
                else:
                    existing.active = True
                    existing.alias = alias
                    existing.target_price = target
            db.commit()

        total = db.query(PricePoint).count()
        outliers = db.query(PricePoint).filter(PricePoint.is_outlier.is_(True)).count()
        clean = total - outliers
        with_ohlc = (
            db.query(PricePoint)
            .filter(PricePoint.is_outlier.is_(False), PricePoint.open_price.isnot(None))
            .count()
        )
        watches = db.query(WatchItem).filter(WatchItem.active.is_(True)).count()
        products = db.query(Product).count()
        print(
            f"OK products={products} watchlist={watches} prices={total} "
            f"clean={clean} outliers={outliers} ohlc={with_ohlc}"
        )
        for s in (
            db.query(PricePoint)
            .filter(PricePoint.is_outlier.is_(True))
            .limit(8)
            .all()
        ):
            print(f"  outlier price={s.price} reason={s.filter_reason}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
