from __future__ import annotations

from datetime import date

from app.providers.base import BaseProvider, ProviderResult
from app.schemas import ReportType


def _normalize_stock_code(code: str) -> str:
    code = code.strip().upper()
    if code.startswith(("SH", "SZ")):
        return code
    if code.isdigit() and len(code) == 6:
        return f"SH{code}" if code.startswith("6") else f"SZ{code}"
    return code


class MockProvider(BaseProvider):
    """V1 联调数据源：字段稳定、值可变。"""

    def get_pre_market(self, trade_date: date) -> ProviderResult:
        raw = {
            "index_futures": [
                {"name": "沪深300主连", "value": 3658.2, "change_pct": 0.34},
                {"name": "中证500主连", "value": 5661.7, "change_pct": -0.11},
            ],
            "overseas_market": [
                {"name": "NASDAQ", "value": 18420.7, "change_pct": 0.63},
                {"name": "S&P 500", "value": 5342.9, "change_pct": 0.39},
            ],
            "macro_events": [
                "今日 10:00 公布社融数据",
                "今晚 20:30 美国 CPI 数据",
            ],
            "watchlist": ["AI算力", "机器人", "低空经济", "机器人"],
            "sentiment_score": 63.0,
        }

        summary = {
            "index_futures": raw["index_futures"],
            "overseas_market": raw["overseas_market"],
            "macro_events": list(dict.fromkeys(raw["macro_events"])),
            "watchlist": list(dict.fromkeys(raw["watchlist"])),
            "sentiment_score": raw["sentiment_score"],
        }

        return ProviderResult(
            report_type=ReportType.PRE_MARKET,
            trade_date=trade_date,
            summary_data=summary,
            raw_data=raw,
            warnings=[],
            source="mock",
        )

    def get_auction(self, trade_date: date) -> ProviderResult:
        raw = {
            "top_gainers": [
                {
                    "code": "300308",
                    "name": "中际旭创",
                    "change_pct": 4.91,
                    "turnover": 3.2e8,
                },
                {
                    "code": "002371",
                    "name": "北方华创",
                    "change_pct": 3.88,
                    "turnover": 2.6e8,
                },
            ],
            "top_losers": [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "change_pct": -1.22,
                    "turnover": 1.4e8,
                }
            ],
            "turnover_top": [
                {
                    "code": "300750",
                    "name": "宁德时代",
                    "change_pct": 1.09,
                    "turnover": 4.8e8,
                },
                {
                    "code": "601318",
                    "name": "中国平安",
                    "change_pct": 0.72,
                    "turnover": 3.7e8,
                },
            ],
            "limit_up_candidates": ["机器人", "算力服务"],
            "auction_sentiment": 58.5,
        }

        def normalized_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
            normalized = []
            for row in rows:
                current = dict(row)
                current["code"] = _normalize_stock_code(str(current.get("code", "")))
                normalized.append(current)
            return normalized

        summary = {
            "top_gainers": normalized_rows(raw["top_gainers"]),
            "top_losers": normalized_rows(raw["top_losers"]),
            "turnover_top": normalized_rows(raw["turnover_top"]),
            "limit_up_candidates": list(dict.fromkeys(raw["limit_up_candidates"])),
            "auction_sentiment": raw["auction_sentiment"],
        }

        warnings = []
        if not summary["top_losers"]:
            warnings.append("top_losers 数据为空")

        return ProviderResult(
            report_type=ReportType.AUCTION,
            trade_date=trade_date,
            summary_data=summary,
            raw_data=raw,
            warnings=warnings,
            source="mock",
        )

    def get_close(self, trade_date: date) -> ProviderResult:
        raw = {
            "index_close": [
                {"name": "上证指数", "value": 3128.2, "change_pct": 0.31},
                {"name": "创业板指", "value": 1862.4, "change_pct": 0.77},
            ],
            "sector_heatmap": [
                {
                    "name": "半导体",
                    "change_pct": 2.93,
                    "leading_stock": "中微公司",
                },
                {
                    "name": "机器人",
                    "change_pct": 2.47,
                    "leading_stock": "埃斯顿",
                },
            ],
            "northbound_flow": {
                "net_inflow": 42.3,
                "shanghai": 20.1,
                "shenzhen": 22.2,
            },
            "market_breadth": {
                "up_count": 3520,
                "down_count": 1410,
                "flat_count": 132,
            },
            "limit_up_stats": {
                "limit_up_count": 68,
                "limit_down_count": 6,
            },
        }

        summary = {
            "index_close": raw["index_close"],
            "sector_heatmap": raw["sector_heatmap"],
            "northbound_flow": raw["northbound_flow"],
            "market_breadth": raw["market_breadth"],
            "limit_up_stats": raw["limit_up_stats"],
        }

        warnings = []
        if raw["northbound_flow"].get("net_inflow") is None:
            warnings.append("北向资金净流入缺失")

        return ProviderResult(
            report_type=ReportType.CLOSE,
            trade_date=trade_date,
            summary_data=summary,
            raw_data=raw,
            warnings=warnings,
            source="mock",
        )
