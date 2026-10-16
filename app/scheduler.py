"""APScheduler：周期性拉取关注商品价格。"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def _job_collect_watchlist():
    from app.db import SessionLocal
    from app.models import Product
    from app.services import collect_product, list_watch
    from sqlalchemy.orm import joinedload

    db = SessionLocal()
    try:
        for w in list_watch(db):
            product = (
                db.query(Product)
                .options(joinedload(Product.platform))
                .filter(Product.id == w.product_id)
                .first()
            )
            if not product or not product.platform:
                continue
            if product.platform.adapter in ("jd", "taobao", "pdd"):
                continue
            try:
                await collect_product(db, product)
            except Exception:
                logger.exception("collect failed product_id=%s", product.id)
    finally:
        db.close()


def start_scheduler() -> None:
    settings = get_settings()
    minutes = max(1, settings.collect_interval_minutes)
    if not scheduler.running:
        scheduler.add_job(
            _job_collect_watchlist,
            "interval",
            minutes=minutes,
            id="collect_watchlist",
            replace_existing=True,
        )
        scheduler.start()
        logger.info("scheduler started, interval=%s min", minutes)


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
