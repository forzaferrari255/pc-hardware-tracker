from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.models import Product, WatchItem
from app.schemas import CollectResult
from app.services import collect_product, list_watch

router = APIRouter()


@router.post("/product/{product_id}", response_model=CollectResult)
async def collect_one(product_id: int, db: Session = Depends(get_db)):
    product = (
        db.query(Product)
        .options(joinedload(Product.platform))
        .filter(Product.id == product_id)
        .first()
    )
    if not product:
        raise HTTPException(404, "商品不存在")
    if product.platform and product.platform.adapter in ("jd", "taobao", "pdd"):
        raise HTTPException(501, "该平台 adapter 为 stub，请使用 mock / manual_csv / http_json")
    pp = await collect_product(db, product)
    if not pp:
        return CollectResult(product_id=product_id, price=None, accepted=False, reason="无快照")
    return CollectResult(
        product_id=product_id,
        price=pp.price,
        accepted=not pp.is_outlier,
        reason=pp.filter_reason,
    )


@router.post("/watchlist", response_model=list[CollectResult])
async def collect_watchlist(db: Session = Depends(get_db)):
    results: list[CollectResult] = []
    for w in list_watch(db):
        product = (
            db.query(Product)
            .options(joinedload(Product.platform))
            .filter(Product.id == w.product_id)
            .first()
        )
        if not product:
            continue
        if product.platform and product.platform.adapter in ("jd", "taobao", "pdd"):
            results.append(
                CollectResult(
                    product_id=product.id,
                    price=None,
                    accepted=False,
                    reason="stub 平台跳过",
                )
            )
            continue
        pp = await collect_product(db, product)
        if not pp:
            results.append(
                CollectResult(product_id=product.id, price=None, accepted=False, reason="无快照")
            )
        else:
            results.append(
                CollectResult(
                    product_id=product.id,
                    price=pp.price,
                    accepted=not pp.is_outlier,
                    reason=pp.filter_reason,
                )
            )
    return results
