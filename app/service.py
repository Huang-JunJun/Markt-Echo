from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.config import DEFAULT_TIMEZONE, DEFAULT_USE_MOCK
from app.providers import MockProvider, RealAuctionProvider, RealCloseProvider, RealPreMarketProvider
from app.schemas import (
    AuctionSummaryData,
    CloseSummaryData,
    ExecutionStatus,
    FinalTextUpdateRequest,
    PreMarketSummaryData,
    ReportPayload,
    ReportType,
)
from app.storage import ReportStore


class DataService:
    def __init__(self, store: ReportStore):
        self.store = store
        self.mock_provider = MockProvider()
        self.real_pre_market_provider = RealPreMarketProvider()
        self.real_auction_provider = RealAuctionProvider()
        self.real_close_provider = RealCloseProvider()
        self.tz = ZoneInfo(DEFAULT_TIMEZONE)

    def _now(self) -> datetime:
        return datetime.now(self.tz)

    def _today(self) -> date:
        return self._now().date()

    def _stabilize_summary(
        self,
        report_type: ReportType,
        summary_data: Dict,
    ) -> Dict:
        if report_type == ReportType.PRE_MARKET:
            return PreMarketSummaryData.model_validate(summary_data).model_dump(mode="json")
        if report_type == ReportType.AUCTION:
            return AuctionSummaryData.model_validate(summary_data).model_dump(mode="json")
        if report_type == ReportType.CLOSE:
            return CloseSummaryData.model_validate(summary_data).model_dump(mode="json")
        raise ValueError(f"unsupported report type: {report_type}")

    def generate_report(
        self,
        report_type: ReportType,
        trade_date: Optional[date] = None,
        use_mock: Optional[bool] = None,
    ) -> ReportPayload:
        resolved_trade_date = trade_date or self._today()
        resolved_use_mock = DEFAULT_USE_MOCK if use_mock is None else use_mock
        generated_at = self._now()
        report_id = f"{report_type.value}-{resolved_trade_date.isoformat()}-{uuid4().hex[:10]}"

        warnings: List[str] = []

        provider = self.mock_provider
        if report_type == ReportType.PRE_MARKET and not resolved_use_mock:
            provider = self.real_pre_market_provider
        elif report_type == ReportType.AUCTION and not resolved_use_mock:
            provider = self.real_auction_provider
        elif report_type == ReportType.CLOSE and not resolved_use_mock:
            provider = self.real_close_provider
        elif not resolved_use_mock:
            # 未配置真实数据源的节点仍保持 mock。
            warnings.append("未配置真实数据源，已回退到 mock 数据")

        try:
            if report_type == ReportType.PRE_MARKET:
                provider_result = provider.get_pre_market(resolved_trade_date)
            elif report_type == ReportType.AUCTION:
                provider_result = provider.get_auction(resolved_trade_date)
            elif report_type == ReportType.CLOSE:
                provider_result = provider.get_close(resolved_trade_date)
            else:
                raise ValueError(f"unsupported report type: {report_type}")

            normalized_summary = self._stabilize_summary(
                report_type,
                provider_result.summary_data,
            )

            merged_warnings = list(dict.fromkeys(warnings + provider_result.warnings))
            status = (
                ExecutionStatus.PARTIAL
                if merged_warnings
                else ExecutionStatus.SUCCESS
            )

            payload = ReportPayload(
                report_id=report_id,
                report_type=report_type,
                trade_date=resolved_trade_date,
                generated_at=generated_at,
                summary_data=normalized_summary,
                raw_data=provider_result.raw_data,
                warnings=merged_warnings,
                status=status,
                source=provider_result.source,
            )
            self.store.save_report(payload)
            return payload
        except Exception as exc:
            self.store.save_failed_report(
                report_id=report_id,
                report_type=report_type,
                trade_date=resolved_trade_date,
                generated_at=generated_at,
                error_message=str(exc),
            )
            raise

    def list_today(self, report_type: Optional[ReportType] = None) -> List[Dict]:
        return self.store.list_today_reports(today=self._today(), report_type=report_type)

    def update_final_text(self, report_id: str, request: FinalTextUpdateRequest) -> bool:
        return self.store.update_final_output(
            report_id=report_id,
            final_output_text=request.final_output_text,
            status=request.status,
        )
