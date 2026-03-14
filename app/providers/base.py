from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.schemas import ReportType


@dataclass
class ProviderResult:
    report_type: ReportType
    trade_date: date
    summary_data: dict[str, Any]
    raw_data: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    source: str = "unknown"


class BaseProvider:
    def get_pre_market(self, trade_date: date) -> ProviderResult:
        raise NotImplementedError

    def get_auction(self, trade_date: date) -> ProviderResult:
        raise NotImplementedError

    def get_close(self, trade_date: date) -> ProviderResult:
        raise NotImplementedError
