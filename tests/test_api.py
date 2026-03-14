from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import ServiceContainer, router
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


def test_generate_auction_fallback_warning(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    resp = client.post(
        "/v1/review/auction",
        json={"use_mock": False},
    )
    assert resp.status_code == 200

    payload = resp.json()["data"]
    assert payload["report_type"] == ReportType.AUCTION.value
    assert payload["status"] == "PARTIAL"
    assert any("回退到 mock" in w for w in payload["warnings"])


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
