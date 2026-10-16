from fastapi import APIRouter

from app.api import analyze, chart, collect, health, products, watchlist

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(watchlist.router, prefix="/watchlist", tags=["watchlist"])
api_router.include_router(products.router, prefix="/products", tags=["products"])
api_router.include_router(chart.router, prefix="/chart", tags=["chart"])
api_router.include_router(analyze.router, prefix="/analyze", tags=["analyze"])
api_router.include_router(collect.router, prefix="/collect", tags=["collect"])
