from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from app.schemas import (
    ApiResponse,
    FinalTextUpdateRequest,
    FinalTextUpdateResponse,
    GenerateRequest,
    ReportType,
    TodayReportsResponse,
)
from app.service import DataService

router = APIRouter()


class ServiceContainer:
    service: Optional[DataService] = None


def get_service() -> DataService:
    if ServiceContainer.service is None:
        raise RuntimeError("service not initialized")
    return ServiceContainer.service


@router.get("/health")
def health() -> Dict[str, str]:
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@router.post("/v1/review/pre-market", response_model=ApiResponse)
def generate_pre_market(
    req: Optional[GenerateRequest] = Body(default=None),
    service: DataService = Depends(get_service),
) -> ApiResponse:
    request = req or GenerateRequest()
    try:
        payload = service.generate_report(
            report_type=ReportType.PRE_MARKET,
            trade_date=request.trade_date,
            use_mock=request.use_mock,
        )
        return ApiResponse(ok=True, data=payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"pre_market 生成失败: {exc}") from exc


@router.post("/v1/review/auction", response_model=ApiResponse)
def generate_auction(
    req: Optional[GenerateRequest] = Body(default=None),
    service: DataService = Depends(get_service),
) -> ApiResponse:
    request = req or GenerateRequest()
    try:
        payload = service.generate_report(
            report_type=ReportType.AUCTION,
            trade_date=request.trade_date,
            use_mock=request.use_mock,
        )
        return ApiResponse(ok=True, data=payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"auction 生成失败: {exc}") from exc


@router.post("/v1/review/close", response_model=ApiResponse)
def generate_close(
    req: Optional[GenerateRequest] = Body(default=None),
    service: DataService = Depends(get_service),
) -> ApiResponse:
    request = req or GenerateRequest()
    try:
        payload = service.generate_report(
            report_type=ReportType.CLOSE,
            trade_date=request.trade_date,
            use_mock=request.use_mock,
        )
        return ApiResponse(ok=True, data=payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"close 生成失败: {exc}") from exc


@router.get("/v1/reports/today", response_model=TodayReportsResponse)
def list_today_reports(
    report_type: Optional[ReportType] = None,
    service: DataService = Depends(get_service),
) -> TodayReportsResponse:
    items = service.list_today(report_type=report_type)
    return TodayReportsResponse(ok=True, data=items)


@router.post(
    "/v1/reports/{report_id}/final-text",
    response_model=FinalTextUpdateResponse,
)
def update_final_text(
    report_id: str,
    req: FinalTextUpdateRequest,
    service: DataService = Depends(get_service),
) -> FinalTextUpdateResponse:
    updated = service.update_final_text(report_id=report_id, request=req)
    if not updated:
        raise HTTPException(status_code=404, detail=f"report_id 不存在: {report_id}")
    return FinalTextUpdateResponse(ok=True, report_id=report_id, status=req.status)
