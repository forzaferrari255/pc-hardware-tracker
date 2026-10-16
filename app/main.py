"""FastAPI 入口：电脑硬件价格跟踪大盘。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api import api_router
from app.db import SessionLocal, init_db
from app.scheduler import start_scheduler, stop_scheduler
from app.services import ensure_default_platforms

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
TEMPLATES_DIR = ROOT / "templates"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        ensure_default_platforms(db)
    finally:
        db.close()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="电脑硬件价格大盘",
    description="关注硬件价格走势、预测与 AI 入手建议（合规可插拔采集）",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(api_router)
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/product/{product_id}", response_class=HTMLResponse)
def product_page(request: Request, product_id: int):
    return templates.TemplateResponse(
        request,
        "product.html",
        {"product_id": product_id},
    )
