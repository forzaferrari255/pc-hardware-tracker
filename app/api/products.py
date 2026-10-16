from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors import get_adapter
from app.db import get_db
from app.models import PricePoint, Product
from app.schemas import PricePointOut, ProductOut, SearchHit
from app.services import latest_clean_price

router = APIRouter()


@router.get("/search", response_model=list[SearchHit])
async def search_products(
    q: str = Query(..., min_length=1),
    platform: str = "mock",
    category: str | None = None,
    limit: int = 20,
):
    adapter = get_adapter(platform)
    if adapter.is_stub:
        raise HTTPException(
            501,
            detail=f"平台 {platform} 为 stub，未实现真实采集。{adapter.compliance_note()}",
        )
    hits = await adapter.search(q, category=category, limit=limit)
    return [
        SearchHit(
            platform=platform,
            external_id=h.external_id,
            name=h.name,
            price=h.price,
            category=h.category,
            brand=h.brand,
            model=h.model,
            url=h.url,
        )
        for h in hits
    ]


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "商品不存在")
    return p


@router.get("/{product_id}/prices", response_model=list[PricePointOut])
def get_prices(
    product_id: int,
    include_outliers: bool = False,
    db: Session = Depends(get_db),
):
    if not db.get(Product, product_id):
        raise HTTPException(404, "商品不存在")
    q = select(PricePoint).where(PricePoint.product_id == product_id)
    if not include_outliers:
        q = q.where(PricePoint.is_outlier.is_(False))
    rows = db.scalars(q.order_by(PricePoint.collected_at.asc())).all()
    return list(rows)


@router.get("/{product_id}/latest")
def get_latest(product_id: int, db: Session = Depends(get_db)):
    if not db.get(Product, product_id):
        raise HTTPException(404, "商品不存在")
    price, at = latest_clean_price(db, product_id)
    return {"product_id": product_id, "price": price, "collected_at": at}
