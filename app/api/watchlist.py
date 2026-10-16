from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import WatchItem
from app.schemas import WatchItemCreate, WatchItemOut, WatchItemUpdate
from app.services import get_or_create_product, latest_clean_price, list_watch

router = APIRouter()


def _to_out(db: Session, w: WatchItem) -> WatchItemOut:
    lp, lt = latest_clean_price(db, w.product_id)
    return WatchItemOut(
        id=w.id,
        product_id=w.product_id,
        alias=w.alias,
        notes=w.notes,
        target_price=w.target_price,
        active=w.active,
        created_at=w.created_at,
        product=w.product,
        latest_price=lp,
        latest_at=lt,
    )


@router.get("", response_model=list[WatchItemOut])
def get_watchlist(active_only: bool = True, db: Session = Depends(get_db)):
    items = list_watch(db, active_only=active_only)
    return [_to_out(db, w) for w in items]


@router.post("", response_model=WatchItemOut)
def create_watch(body: WatchItemCreate, db: Session = Depends(get_db)):
    if body.product_id:
        from app.models import Product

        prod = db.get(Product, body.product_id)
        if not prod:
            raise HTTPException(404, "商品不存在")
    else:
        if not body.external_id or not body.name:
            raise HTTPException(400, "需提供 product_id，或 external_id + name")
        prod = get_or_create_product(
            db,
            platform_code=body.platform_code,
            external_id=body.external_id,
            name=body.name,
            category=body.category,
            brand=body.brand,
            model=body.model,
        )
    existing = db.query(WatchItem).filter(WatchItem.product_id == prod.id).first()
    if existing:
        existing.active = True
        if body.alias is not None:
            existing.alias = body.alias
        if body.notes is not None:
            existing.notes = body.notes
        if body.target_price is not None:
            existing.target_price = body.target_price
        db.commit()
        db.refresh(existing)
        return _to_out(db, existing)
    w = WatchItem(
        product_id=prod.id,
        alias=body.alias,
        notes=body.notes,
        target_price=body.target_price,
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    w = db.query(WatchItem).filter(WatchItem.id == w.id).first()
    return _to_out(db, w)


@router.patch("/{watch_id}", response_model=WatchItemOut)
def update_watch(watch_id: int, body: WatchItemUpdate, db: Session = Depends(get_db)):
    w = db.get(WatchItem, watch_id)
    if not w:
        raise HTTPException(404, "关注项不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(w, k, v)
    db.commit()
    db.refresh(w)
    return _to_out(db, w)


@router.delete("/{watch_id}")
def delete_watch(watch_id: int, db: Session = Depends(get_db)):
    w = db.get(WatchItem, watch_id)
    if not w:
        raise HTTPException(404, "关注项不存在")
    w.active = False
    db.commit()
    return {"ok": True, "id": watch_id}
