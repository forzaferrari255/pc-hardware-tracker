from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Product
from app.schemas import Candle, ChartSeries, ForecastOut
from app.services import build_forecast, chart_data

router = APIRouter()


def _fc_to_out(result) -> ForecastOut:
    candles = [
        Candle(
            t=p.at.strftime("%Y-%m-%d"),
            o=float(p.open if p.open is not None else p.price),
            h=float(p.high if p.high is not None else p.price),
            l=float(p.low if p.low is not None else p.price),
            c=float(p.close if p.close is not None else p.price),
        )
        for p in result.points
    ]
    return ForecastOut(
        method=result.method,
        horizon_days=result.horizon_days,
        summary=result.summary,
        metrics=result.metrics,
        timestamps=[p.at.isoformat() for p in result.points],
        prices=[p.price for p in result.points],
        candles=candles,
    )


@router.get("/{product_id}", response_model=ChartSeries)
def get_chart(
    product_id: int,
    days: int | None = Query(90, ge=1, le=3650),
    include_outliers: bool = False,
    method: str = Query("ema", pattern="^(sma|ema|linear)$"),
    horizon_days: int = Query(14, ge=1, le=90),
    db: Session = Depends(get_db),
):
    if not db.get(Product, product_id):
        raise HTTPException(404, "商品不存在")
    data = chart_data(
        db,
        product_id,
        days=days,
        include_outliers=include_outliers,
        forecast_method=method,
        horizon_days=horizon_days,
    )
    return ChartSeries(**data)


@router.get("/{product_id}/forecast", response_model=ForecastOut)
def get_forecast(
    product_id: int,
    method: str = Query("ema", pattern="^(sma|ema|linear)$"),
    horizon_days: int = Query(14, ge=1, le=90),
    db: Session = Depends(get_db),
):
    if not db.get(Product, product_id):
        raise HTTPException(404, "商品不存在")
    result = build_forecast(db, product_id, method=method, horizon_days=horizon_days)
    return _fc_to_out(result)
