from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import ServiceContainer, router
from app.providers.base import ProviderResult
from app.schemas import ReportType
from app.service import DataService
from app.storage import ReportStore


def build_client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    store = ReportStore(tmp_path / "test.db")
    ServiceContainer.service = DataService(store)
    app.include_router(router)
    return TestClient(app)


def test_health(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


def test_generate_pre_market_and_list_today(tmp_path: Path) -> None:
    client = build_client(tmp_path)

    create_resp = client.post(
        "/v1/review/pre-market",
        json={"use_mock": True},
    )
    assert create_resp.status_code == 200

    payload = create_resp.json()["data"]
    assert payload["report_type"] == ReportType.PRE_MARKET.value
    assert "index_futures" in payload["summary_data"]
    assert "raw_data" in payload

    today_resp = client.get("/v1/reports/today", params={"report_type": "pre_market"})
    assert today_resp.status_code == 200
    items = today_resp.json()["data"]
    assert len(items) == 1
    assert items[0]["report_id"] == payload["report_id"]


def test_generate_pre_market_real_provider(tmp_path: Path) -> None:
    app = FastAPI()
    store = ReportStore(tmp_path / "test.db")
    service = DataService(store)

    class StubRealPreMarketProvider:
        def get_pre_market(self, trade_date):
            return ProviderResult(
                report_type=ReportType.PRE_MARKET,
                trade_date=trade_date,
                summary_data={
                    "index_futures": [{"name": "沪深300主连", "value": 4300.0, "change_pct": 0.2}],
                    "overseas_market": [{"name": "NASDAQ", "value": 20000.0, "change_pct": 0.8}],
                    "macro_events": ["09:30 居民消费价格指数月度报告"],
                    "watchlist": ["通胀敏感链，关注消费与利率预期方向"],
                    "sentiment_score": 58.0,
                },
                raw_data={
                    "field_sources": {
                        "overseas_market": "real:test",
                        "watchlist": "derived_from_real_market_and_macro",
                    }
                },
                warnings=["watchlist 当前为 derived：基于真实行情与宏观事件派生，不是外部板块热度直取"],
                source="real_partial",
            )

    service.real_pre_market_provider = StubRealPreMarketProvider()
    ServiceContainer.service = service
    app.include_router(router)
    client = TestClient(app)

    create_resp = client.post(
        "/v1/review/pre-market",
        json={"use_mock": False},
    )
    assert create_resp.status_code == 200

    payload = create_resp.json()["data"]
    assert payload["report_type"] == ReportType.PRE_MARKET.value
    assert payload["source"] == "real_partial"
    assert payload["source"] != "mock"
    assert payload["summary_data"]["overseas_market"][0]["name"] == "NASDAQ"
    assert payload["summary_data"]["watchlist"][0].startswith("通胀敏感链")
    assert payload["raw_data"]["field_sources"]["watchlist"] == "derived_from_real_market_and_macro"
    assert any("watchlist 当前为 derived" in w for w in payload["warnings"])


def test_generate_auction_real_provider(tmp_path: Path) -> None:
    app = FastAPI()
    store = ReportStore(tmp_path / "test.db")
    service = DataService(store)

    class StubRealAuctionProvider:
        def get_auction(self, trade_date):
            return ProviderResult(
                report_type=ReportType.AUCTION,
                trade_date=trade_date,
                summary_data={
                    "index_auction": [
                        {"name": "上证指数", "value": 3310.0, "change_pct": 0.42},
                        {"name": "创业板指", "value": 2198.0, "change_pct": 1.18},
                    ],
                    "top_gainers": [{"code": "SZ300308", "name": "中际旭创", "change_pct": 4.2, "turnover": 850000000.0}],
                    "top_losers": [{"code": "SH600519", "name": "贵州茅台", "change_pct": -1.3, "turnover": 320000000.0}],
                    "turnover_top": [{"code": "SZ300750", "name": "宁德时代", "change_pct": 0.9, "turnover": 1600000000.0}],
                    "limit_up_candidates": ["CPO概念", "新能源车"],
                    "auction_sentiment": 61.5,
                },
                raw_data={
                    "field_sources": {
                        "index_auction": "real:test",
                        "top_gainers": "real:test",
                        "limit_up_candidates": "derived_from_real_stock_rank_and_board_membership",
                        "auction_sentiment": "derived_from_real_index_and_stock_rank",
                    }
                },
                warnings=[
                    "limit_up_candidates 当前为 derived：基于真实竞价个股排行与所属板块派生，不是官方板块竞价榜单",
                    "auction_sentiment 当前为 derived：基于真实指数与个股竞价强弱派生，不是交易所官方情绪口径",
                ],
                source="real_partial",
            )

    service.real_auction_provider = StubRealAuctionProvider()
    ServiceContainer.service = service
    app.include_router(router)
    client = TestClient(app)

    resp = client.post(
        "/v1/review/auction",
        json={"use_mock": False},
    )
    assert resp.status_code == 200

    payload = resp.json()["data"]
    assert payload["report_type"] == ReportType.AUCTION.value
    assert payload["source"] == "real_partial"
    assert payload["source"] != "mock"
    assert payload["summary_data"]["index_auction"][0]["name"] == "上证指数"
    assert payload["summary_data"]["limit_up_candidates"][0] == "CPO概念"
    assert payload["raw_data"]["field_sources"]["limit_up_candidates"] == "derived_from_real_stock_rank_and_board_membership"
    assert any("当前为 derived" in w for w in payload["warnings"])


def test_generate_auction_mock_provider(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    resp = client.post(
        "/v1/review/auction",
        json={"use_mock": True},
    )
    assert resp.status_code == 200

    payload = resp.json()["data"]
    assert payload["report_type"] == ReportType.AUCTION.value
    assert payload["source"] == "mock"
    assert payload["summary_data"]["top_gainers"][0]["code"] == "SZ300308"
    assert payload["summary_data"]["turnover_top"][0]["name"] == "宁德时代"
    assert payload["warnings"] == []


def test_generate_close_mock_provider(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    resp = client.post(
        "/v1/review/close",
        json={"use_mock": True},
    )
    assert resp.status_code == 200

    payload = resp.json()["data"]
    assert payload["report_type"] == ReportType.CLOSE.value
    assert payload["source"] == "mock"
    assert payload["summary_data"]["index_close"][0]["name"] == "上证指数"
    assert payload["summary_data"]["sector_heatmap"][0]["name"] == "半导体"
    assert payload["warnings"] == []


def test_generate_close_real_provider(tmp_path: Path) -> None:
    app = FastAPI()
    store = ReportStore(tmp_path / "test.db")
    service = DataService(store)

    class StubRealCloseProvider:
        def get_close(self, trade_date):
            return ProviderResult(
                report_type=ReportType.CLOSE,
                trade_date=trade_date,
                summary_data={
                    "index_close": [
                        {"name": "上证指数", "value": 3300.0, "change_pct": 0.5},
                        {"name": "创业板指", "value": 2100.0, "change_pct": 1.2},
                    ],
                    "sector_heatmap": [{"name": "半导体", "change_pct": 2.8, "leading_stock": "中微公司"}],
                    "northbound_flow": {"net_inflow": 18.5, "shanghai": 8.2, "shenzhen": 10.3},
                    "market_breadth": {"up_count": 3200, "down_count": 1700, "flat_count": 120},
                    "limit_up_stats": {"limit_up_count": 75, "limit_down_count": 4},
                    "turnover_summary": {
                        "market_turnover_billion": 15670.0,
                        "turnover_proxy_current_billion": 1643.2,
                        "turnover_proxy_previous_billion": 1528.7,
                        "turnover_proxy_change_pct": 7.49,
                        "volume_stage": "放量",
                        "current_date": "2026-03-13",
                        "previous_date": "2026-03-12",
                    },
                },
                raw_data={
                    "field_sources": {
                        "index_close": "real:test",
                        "market_breadth": "derived_from_real_a_share_quotes",
                        "turnover_summary": "derived_from_real_quotes_and_index_trends",
                    }
                },
                warnings=[
                    "close 使用的最新可用真实收盘数据日期为 2026-03-13，当前请求日期为 2026-03-14",
                    "market_breadth / limit_up_stats / turnover_summary 当前为 derived，不是交易所官方情绪口径",
                ],
                source="real_partial",
            )

    service.real_close_provider = StubRealCloseProvider()
    ServiceContainer.service = service
    app.include_router(router)
    client = TestClient(app)

    create_resp = client.post(
        "/v1/review/close",
        json={"use_mock": False},
    )
    assert create_resp.status_code == 200

    payload = create_resp.json()["data"]
    assert payload["report_type"] == ReportType.CLOSE.value
    assert payload["source"] == "real_partial"
    assert payload["source"] != "mock"
    assert payload["summary_data"]["turnover_summary"]["volume_stage"] == "放量"
    assert payload["summary_data"]["northbound_flow"]["net_inflow"] == 18.5
    assert any("当前为 derived" in w for w in payload["warnings"])


def test_update_final_text(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    create_resp = client.post("/v1/review/close", json={})
    payload = create_resp.json()["data"]

    update_resp = client.post(
        f"/v1/reports/{payload['report_id']}/final-text",
        json={
            "final_output_text": "收盘复盘：指数震荡走高，资金回流半导体。",
            "status": "SUCCESS",
        },
    )
    assert update_resp.status_code == 200

    today_resp = client.get("/v1/reports/today", params={"report_type": "close"})
    assert today_resp.status_code == 200
    item = today_resp.json()["data"][0]
    assert item["final_output_text"] == "收盘复盘：指数震荡走高，资金回流半导体。"
