from __future__ import annotations

from fastapi import FastAPI

from app.api import ServiceContainer, router
from app.config import DB_PATH
from app.service import DataService
from app.storage import ReportStore


def create_app() -> FastAPI:
    app = FastAPI(
        title="Market-Echo Data Service",
        version="0.1.0",
        description="OpenClaw 交易复盘助手 V1 数据服务",
    )

    store = ReportStore(DB_PATH)
    ServiceContainer.service = DataService(store=store)
    app.include_router(router)
    return app


app = create_app()
