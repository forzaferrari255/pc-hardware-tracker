from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.llm.deepseek import DeepSeekClient, OfflineError, is_online
from app.models import Product, WatchItem
from app.schemas import AnalyzeOut, Candle, ForecastOut
from app.services import build_analysis_payload, build_forecast, latest_clean_price

router = APIRouter()


@router.get("/{product_id}", response_model=AnalyzeOut)
async def analyze_product(
    product_id: int,
    method: str = Query("ema", pattern="^(sma|ema|linear)$"),
    horizon_days: int = Query(14, ge=1, le=90),
    db: Session = Depends(get_db),
):
    product = db.query(Product).options(joinedload(Product.platform)).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(404, "商品不存在")

    fc = build_forecast(db, product_id, method=method, horizon_days=horizon_days)

    forecast_out = ForecastOut(
        method=fc.method,
        horizon_days=fc.horizon_days,
        summary=fc.summary,
        metrics=fc.metrics,
        timestamps=[p.at.isoformat() for p in fc.points],
        prices=[p.price for p in fc.points],
        candles=[
            Candle(
                t=p.at.strftime("%Y-%m-%d"),
                o=float(p.open if p.open is not None else p.price),
                h=float(p.high if p.high is not None else p.price),
                l=float(p.low if p.low is not None else p.price),
                c=float(p.close if p.close is not None else p.price),
            )
            for p in fc.points
        ],
    )

    online = is_online()
    client = DeepSeekClient()
    price, _ = latest_clean_price(db, product_id)
    watch = db.query(WatchItem).filter(WatchItem.product_id == product_id).first()
    target = watch.target_price if watch else None

    payload = build_analysis_payload(
        db,
        product,
        method=method,
        horizon_days=horizon_days,
        recent_candle_days=30,
        forecast_result=fc,
        latest_price=price,
        target_price=target,
    )

    try:
        text = await client.analyze_purchase(payload)
        return AnalyzeOut(online=True, analysis=text, forecast=forecast_out)
    except OfflineError as e:
        return AnalyzeOut(
            online=online and client.configured,
            analysis=None,
            error=str(e),
            forecast=forecast_out,
        )
    except Exception as e:
        return AnalyzeOut(
            online=online,
            analysis=None,
            error=f"AI 调用失败: {e}",
            forecast=forecast_out,
        )
