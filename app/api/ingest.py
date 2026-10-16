"""本机采集端推送报价：POST /api/ingest/prices。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.schemas import IngestItemResult, IngestPriceItem, IngestResponse
from app.services import ingest_prices

router = APIRouter()


def _extract_token(
    authorization: str | None,
    x_ingest_token: str | None,
) -> str | None:
    if x_ingest_token:
        return x_ingest_token.strip()
    if authorization:
        parts = authorization.strip().split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        return authorization.strip()
    return None


def verify_ingest_token(
    authorization: str | None = Header(None),
    x_ingest_token: str | None = Header(None, alias="X-Ingest-Token"),
) -> None:
    settings = get_settings()
    expected = (settings.ingest_token or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="未配置 INGEST_TOKEN：请在 .env 中设置后重启服务",
        )
    got = _extract_token(authorization, x_ingest_token)
    if not got or got != expected:
        raise HTTPException(status_code=401, detail="无效的 ingest token")


@router.post(
    "/prices",
    response_model=IngestResponse,
    dependencies=[Depends(verify_ingest_token)],
)
def ingest_price_endpoint(
    body: IngestPriceItem | list[IngestPriceItem],
    db: Session = Depends(get_db),
):
    """接收单条或列表报价，入库并可选自动关注。"""
    items_models = body if isinstance(body, list) else [body]
    if not items_models:
        raise HTTPException(400, "请求体不能为空")
    if len(items_models) > 200:
        raise HTTPException(400, "单次最多 200 条")

    payload = []
    for m in items_models:
        d = m.model_dump(by_alias=False)
        # 保留 o/h/l/c 别名字段（model_dump 已落到 open/high/low/close）
        payload.append(d)

    results_raw = ingest_prices(db, payload)
    results = [IngestItemResult(**r) for r in results_raw]
    return IngestResponse(ok=True, count=len(results), results=results)
