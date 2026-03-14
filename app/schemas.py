from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ReportType(str, Enum):
    PRE_MARKET = "pre_market"
    AUCTION = "auction"
    CLOSE = "close"


class ExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class GenerateRequest(BaseModel):
    trade_date: Optional[date] = Field(
        default=None,
        description="交易日期，默认取服务端时区的今天",
    )
    use_mock: Optional[bool] = Field(
        default=None,
        description="是否使用 mock 数据，默认由服务配置决定",
    )


class PricePoint(BaseModel):
    name: str
    value: Optional[float] = None
    change_pct: Optional[float] = None


class StockPoint(BaseModel):
    code: str
    name: str
    change_pct: Optional[float] = None
    turnover: Optional[float] = None


class SectorPoint(BaseModel):
    name: str
    change_pct: Optional[float] = None
    leading_stock: Optional[str] = None


class PreMarketSummaryData(BaseModel):
    index_futures: List[PricePoint] = Field(default_factory=list)
    overseas_market: List[PricePoint] = Field(default_factory=list)
    macro_events: List[str] = Field(default_factory=list)
    watchlist: List[str] = Field(default_factory=list)
    sentiment_score: Optional[float] = None


class AuctionSummaryData(BaseModel):
    index_auction: List[PricePoint] = Field(default_factory=list)
    top_gainers: List[StockPoint] = Field(default_factory=list)
    top_losers: List[StockPoint] = Field(default_factory=list)
    turnover_top: List[StockPoint] = Field(default_factory=list)
    limit_up_candidates: List[str] = Field(default_factory=list)
    auction_sentiment: Optional[float] = None


class CloseSummaryData(BaseModel):
    index_close: List[PricePoint] = Field(default_factory=list)
    sector_heatmap: List[SectorPoint] = Field(default_factory=list)
    northbound_flow: Dict[str, Optional[float]] = Field(default_factory=dict)
    market_breadth: Dict[str, Optional[int]] = Field(default_factory=dict)
    limit_up_stats: Dict[str, Optional[int]] = Field(default_factory=dict)
    turnover_summary: Dict[str, Any] = Field(default_factory=dict)


class ReportPayload(BaseModel):
    report_id: str
    report_type: ReportType
    trade_date: date
    generated_at: datetime
    summary_data: Dict[str, Any]
    raw_data: Dict[str, Any]
    warnings: List[str] = Field(default_factory=list)
    status: ExecutionStatus
    source: str


class ApiResponse(BaseModel):
    ok: bool
    data: Optional[ReportPayload] = None
    error: Optional[str] = None


class TodayReportsResponse(BaseModel):
    ok: bool
    data: List[Dict[str, Any]]


class FinalTextUpdateRequest(BaseModel):
    final_output_text: str
    status: ExecutionStatus = ExecutionStatus.SUCCESS


class FinalTextUpdateResponse(BaseModel):
    ok: bool
    report_id: str
    status: ExecutionStatus
