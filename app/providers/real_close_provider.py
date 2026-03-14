from __future__ import annotations

import json
import math
from datetime import date
from typing import Any
import urllib.parse

import httpx

from app.providers.base import BaseProvider, ProviderResult
from app.schemas import ReportType


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    )
}

INDEX_QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
INDUSTRY_RANK_URL = "https://push2.eastmoney.com/api/qt/clist/get"
A_SHARE_LIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
INDEX_TRENDS_URL = "https://push2his.eastmoney.com/api/qt/stock/trends2/get"
INDEX_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
MUTUAL_FLOW_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
LIMIT_UP_POOL_URL = "https://push2ex.eastmoney.com/getTopicZTPool"
LIMIT_DOWN_POOL_URL = "https://push2ex.eastmoney.com/getTopicDTPool"

INDEX_MAP = {
    "上证指数": "1.000001",
    "创业板指": "0.399006",
}
CSI_ALL_SHARE_SECID = "1.000985"

A_SHARE_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
INDUSTRY_FS = "m:90+t:2"


class RealCloseProvider(BaseProvider):
    @staticmethod
    def _as_float(value: Any, default: float = 0.0) -> float:
        if value in (None, "", "-"):
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        response = httpx.get(
            url,
            params=params,
            headers=DEFAULT_HEADERS,
            timeout=30.0,
            follow_redirects=True,
            trust_env=False,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _normalize_compact_date(value: Any) -> str | None:
        raw = str(value or "").strip()
        if len(raw) == 8 and raw.isdigit():
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        if len(raw) >= 10:
            return raw[:10]
        return None

    def _fetch_index_close(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        points: list[dict[str, Any]] = []
        raw: dict[str, Any] = {}
        for name, secid in INDEX_MAP.items():
            payload = self._get_json(
                url=INDEX_QUOTE_URL,
                params={
                    "secid": secid,
                    "fields": "f58,f43,f60,f170",
                },
            )
            data = payload.get("data") or {}
            current_value = self._as_float(data.get("f43")) / 100.0
            previous_close = self._as_float(data.get("f60")) / 100.0
            change_pct = self._as_float(data.get("f170")) / 100.0

            points.append(
                {
                    "name": name,
                    "value": round(current_value, 2),
                    "change_pct": round(change_pct, 2),
                }
            )
            raw[name] = {
                "secid": secid,
                "current_value": current_value,
                "previous_close": previous_close,
                "change_pct": change_pct,
                "source_url": (
                    f"{INDEX_QUOTE_URL}?{urllib.parse.urlencode({'secid': secid, 'fields': 'f58,f43,f60,f170'})}"
                ),
            }
        return points, raw

    def _fetch_index_trend_proxy(self) -> tuple[dict[str, Any], dict[str, Any]]:
        totals_by_date: dict[str, float] = {}
        raw: dict[str, Any] = {}

        for name, secid in INDEX_MAP.items():
            payload = self._get_json(
                url=INDEX_TRENDS_URL,
                params={
                    "secid": secid,
                    "fields1": "f1,f2,f3,f4",
                    "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
                    "ndays": 2,
                    "iscr": 0,
                    "iscca": 0,
                },
            )
            data = payload.get("data") or {}
            trends = data.get("trends") or []
            daily_totals: dict[str, float] = {}
            for row in trends:
                fields = str(row).split(",")
                if len(fields) < 7:
                    continue
                trade_day = fields[0][:10]
                amount = self._as_float(fields[6])
                daily_totals[trade_day] = daily_totals.get(trade_day, 0.0) + amount

            for trade_day, amount in daily_totals.items():
                totals_by_date[trade_day] = totals_by_date.get(trade_day, 0.0) + amount

            raw[name] = {
                "secid": secid,
                "daily_amounts": daily_totals,
                "source_url": (
                    f"{INDEX_TRENDS_URL}?{urllib.parse.urlencode({'secid': secid, 'fields1': 'f1,f2,f3,f4', 'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58', 'ndays': 2, 'iscr': 0, 'iscca': 0})}"
                ),
            }

        ordered_dates = sorted(totals_by_date.keys())
        if len(ordered_dates) < 2:
            raise RuntimeError("index trend proxy dates are insufficient")

        previous_date = ordered_dates[-2]
        current_date = ordered_dates[-1]
        current_amount = totals_by_date[current_date]
        previous_amount = totals_by_date[previous_date]
        change_pct = ((current_amount - previous_amount) / previous_amount * 100.0) if previous_amount else None

        if change_pct is None:
            volume_stage = "未知"
        elif change_pct >= 5.0:
            volume_stage = "放量"
        elif change_pct <= -5.0:
            volume_stage = "缩量"
        else:
            volume_stage = "量能持平"

        return (
            {
                "turnover_proxy_current_billion": round(current_amount / 100000000.0, 2),
                "turnover_proxy_previous_billion": round(previous_amount / 100000000.0, 2),
                "turnover_proxy_change_pct": round(change_pct, 2) if change_pct is not None else None,
                "volume_stage": volume_stage,
                "current_date": current_date,
                "previous_date": previous_date,
            },
            raw,
        )

    def _fetch_a_share_snapshot(self) -> tuple[dict[str, Any], dict[str, Any]]:
        first_page = self._get_json(
            url=A_SHARE_LIST_URL,
            params={
                "pn": 1,
                "pz": 100,
                "po": 1,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "fid": "f3",
                "fs": A_SHARE_FS,
                "fields": "f12,f14,f2,f3,f6",
            },
        )
        data = first_page.get("data") or {}
        total = int(data.get("total") or 0)
        page_count = max(1, math.ceil(total / 100))
        items = list(data.get("diff") or [])

        for page in range(2, page_count + 1):
            page_payload = self._get_json(
                url=A_SHARE_LIST_URL,
                params={
                    "pn": page,
                    "pz": 100,
                    "po": 1,
                    "np": 1,
                    "fltt": 2,
                    "invt": 2,
                    "fid": "f3",
                    "fs": A_SHARE_FS,
                    "fields": "f12,f14,f2,f3,f6",
                },
            )
            items.extend((page_payload.get("data") or {}).get("diff") or [])

        up_count = 0
        down_count = 0
        flat_count = 0
        valid_quote_count = 0
        excluded_unquoted_count = 0
        limit_up_count = 0
        limit_down_count = 0
        total_turnover = 0.0

        for item in items:
            last_price = self._as_float(item.get("f2"))
            change_pct = self._as_float(item.get("f3"))
            amount = self._as_float(item.get("f6"))
            code = str(item.get("f12") or "")
            name = str(item.get("f14") or "")

            if last_price <= 0:
                excluded_unquoted_count += 1
                continue

            valid_quote_count += 1
            total_turnover += amount
            if change_pct > 0:
                up_count += 1
            elif change_pct < 0:
                down_count += 1
            else:
                flat_count += 1

            upper_limit = 9.8
            lower_limit = -9.8
            if code.startswith(("300", "301", "688", "689")):
                upper_limit = 19.8
                lower_limit = -19.8
            elif code.startswith(("8", "4")):
                upper_limit = 29.8
                lower_limit = -29.8

            if "ST" in name.upper():
                upper_limit = 4.8
                lower_limit = -4.8

            if change_pct >= upper_limit:
                limit_up_count += 1
            if change_pct <= lower_limit:
                limit_down_count += 1

        return (
            {
                "market_breadth": {
                    "up_count": up_count,
                    "down_count": down_count,
                    "flat_count": flat_count,
                },
                "limit_up_stats_fallback": {
                    "limit_up_count": limit_up_count,
                    "limit_down_count": limit_down_count,
                },
                "market_turnover_billion_fallback": round(total_turnover / 100000000.0, 2),
                "valid_quote_count": valid_quote_count,
                "excluded_unquoted_count": excluded_unquoted_count,
            },
            {
                "total": total,
                "page_count": page_count,
                "valid_quote_count": valid_quote_count,
                "excluded_unquoted_count": excluded_unquoted_count,
                "source_url": (
                    f"{A_SHARE_LIST_URL}?{urllib.parse.urlencode({'pn': 1, 'pz': 100, 'po': 1, 'np': 1, 'fltt': 2, 'invt': 2, 'fid': 'f3', 'fs': A_SHARE_FS, 'fields': 'f12,f14,f2,f3,f6'})}"
                ),
            },
        )

    def _fetch_csi_all_share_turnover(self) -> tuple[dict[str, Any], dict[str, Any]]:
        payload = self._get_json(
            url=INDEX_KLINE_URL,
            params={
                "secid": CSI_ALL_SHARE_SECID,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": 101,
                "fqt": 0,
                "lmt": 2,
                "end": "20500101",
                "iscca": 1,
            },
        )
        data = payload.get("data") or {}
        name = str(data.get("name") or "中证全指")
        klines = data.get("klines") or []
        if len(klines) < 2:
            raise RuntimeError("csi all share kline rows are insufficient")

        def parse_row(row: Any) -> dict[str, Any]:
            fields = str(row).split(",")
            if len(fields) < 7:
                raise RuntimeError(f"invalid csi all share kline row: {row}")
            return {
                "trade_date": fields[0][:10],
                "amount": self._as_float(fields[6]),
            }

        previous_row = parse_row(klines[-2])
        current_row = parse_row(klines[-1])
        previous_amount = previous_row["amount"]
        current_amount = current_row["amount"]
        change_pct = ((current_amount - previous_amount) / previous_amount * 100.0) if previous_amount else None

        if change_pct is None:
            volume_stage = "未知"
        elif change_pct >= 5.0:
            volume_stage = "放量"
        elif change_pct <= -5.0:
            volume_stage = "缩量"
        else:
            volume_stage = "量能持平"

        return (
            {
                "market_turnover_billion": round(current_amount / 100000000.0, 2),
                "market_turnover_previous_billion": round(previous_amount / 100000000.0, 2),
                "market_turnover_change_pct": round(change_pct, 2) if change_pct is not None else None,
                "volume_stage": volume_stage,
                "current_date": current_row["trade_date"],
                "previous_date": previous_row["trade_date"],
                "turnover_reference": name,
            },
            {
                "name": name,
                "rows": [previous_row, current_row],
                "source_url": (
                    f"{INDEX_KLINE_URL}?{urllib.parse.urlencode({'secid': CSI_ALL_SHARE_SECID, 'fields1': 'f1,f2,f3,f4,f5,f6', 'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61', 'klt': 101, 'fqt': 0, 'lmt': 2, 'end': '20500101', 'iscca': 1})}"
                ),
            },
        )

    def _fetch_market_breadth(self) -> tuple[dict[str, Any], dict[str, Any]]:
        payload = self._get_json(
            url=INDEX_QUOTE_URL,
            params={
                "secid": CSI_ALL_SHARE_SECID,
                "fields": "f58,f113,f114,f115",
            },
        )
        data = payload.get("data") or {}
        name = str(data.get("f58") or "中证全指")
        return (
            {
                "up_count": int(data.get("f113") or 0),
                "down_count": int(data.get("f114") or 0),
                "flat_count": int(data.get("f115") or 0),
            },
            {
                "reference": name,
                "source_url": (
                    f"{INDEX_QUOTE_URL}?{urllib.parse.urlencode({'secid': CSI_ALL_SHARE_SECID, 'fields': 'f58,f113,f114,f115'})}"
                ),
            },
        )

    def _fetch_limit_pool_stats(self, trade_date: date) -> tuple[dict[str, Any], dict[str, Any]]:
        date_str = trade_date.strftime("%Y%m%d")
        common_params = {
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
            "dpt": "wz.ztzt",
            "Pageindex": 0,
            "pagesize": 1,
            "sort": "fbt:asc",
            "date": date_str,
            "_": "1",
        }
        limit_up_payload = self._get_json(url=LIMIT_UP_POOL_URL, params=common_params)
        limit_down_payload = self._get_json(url=LIMIT_DOWN_POOL_URL, params=common_params)

        limit_up_data = limit_up_payload.get("data") or {}
        limit_down_data = limit_down_payload.get("data") or {}
        limit_up_date = self._normalize_compact_date(limit_up_data.get("qdate"))
        limit_down_date = self._normalize_compact_date(limit_down_data.get("qdate"))

        return (
            {
                "limit_up_count": int(limit_up_data.get("tc") or 0),
                "limit_down_count": int(limit_down_data.get("tc") or 0),
            },
            {
                "requested_date": date_str,
                "limit_up_qdate": limit_up_date,
                "limit_down_qdate": limit_down_date,
                "limit_up_source_url": (
                    f"{LIMIT_UP_POOL_URL}?{urllib.parse.urlencode(common_params)}"
                ),
                "limit_down_source_url": (
                    f"{LIMIT_DOWN_POOL_URL}?{urllib.parse.urlencode(common_params)}"
                ),
            },
        )

    def _fetch_sector_heatmap(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        payload = self._get_json(
            url=INDUSTRY_RANK_URL,
            params={
                "pn": 1,
                "pz": 3,
                "po": 1,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "fid": "f3",
                "fs": INDUSTRY_FS,
                "fields": "f12,f14,f3,f128,f136",
            },
        )
        items = ((payload.get("data") or {}).get("diff") or [])[:3]
        sectors = [
            {
                "name": str(item.get("f14") or ""),
                "change_pct": round(self._as_float(item.get("f3")), 2),
                "leading_stock": str(item.get("f128") or "") or None,
            }
            for item in items
            if item.get("f14")
        ]
        return sectors, {
            "count": len(sectors),
            "items": [
                {
                    "sector_code": item.get("f12"),
                    "sector_name": item.get("f14"),
                    "change_pct": item.get("f3"),
                    "leading_stock": item.get("f128"),
                    "leading_stock_change_pct": item.get("f136"),
                }
                for item in items
            ],
            "source_url": (
                f"{INDUSTRY_RANK_URL}?{urllib.parse.urlencode({'pn': 1, 'pz': 3, 'po': 1, 'np': 1, 'fltt': 2, 'invt': 2, 'fid': 'f3', 'fs': INDUSTRY_FS, 'fields': 'f12,f14,f3,f128,f136'})}"
            ),
        }

    def _fetch_northbound_flow(self) -> tuple[dict[str, Any], dict[str, Any]]:
        payload = self._get_json(
            url=MUTUAL_FLOW_URL,
            params={
                "sortColumns": "TRADE_DATE",
                "sortTypes": -1,
                "pageSize": 20,
                "pageNumber": 1,
                "reportName": "RPT_MUTUAL_DEAL_HISTORY",
                "columns": "TRADE_DATE,MUTUAL_TYPE,NET_DEAL_AMT,BUY_AMT,SELL_AMT",
                "source": "WEB",
                "client": "WEB",
            },
        )
        rows = ((payload.get("result") or {}).get("data") or [])
        if not rows:
            raise RuntimeError("northbound flow rows are empty")

        latest_date = str(rows[0].get("TRADE_DATE") or "")[:10]
        latest_rows = [row for row in rows if str(row.get("TRADE_DATE") or "").startswith(latest_date)]
        type_map = {str(row.get("MUTUAL_TYPE")): row for row in latest_rows}

        shanghai_row = type_map.get("004")
        shenzhen_row = type_map.get("006")
        if not shanghai_row and not shenzhen_row:
            raise RuntimeError("northbound flow rows for 004/006 are missing")

        shanghai = self._as_float((shanghai_row or {}).get("NET_DEAL_AMT")) / 100.0
        shenzhen = self._as_float((shenzhen_row or {}).get("NET_DEAL_AMT")) / 100.0
        return (
            {
                "net_inflow": round(shanghai + shenzhen, 2),
                "shanghai": round(shanghai, 2),
                "shenzhen": round(shenzhen, 2),
            },
            {
                "trade_date": latest_date,
                "rows": latest_rows,
                "source_url": (
                    f"{MUTUAL_FLOW_URL}?{urllib.parse.urlencode({'sortColumns': 'TRADE_DATE', 'sortTypes': -1, 'pageSize': 20, 'pageNumber': 1, 'reportName': 'RPT_MUTUAL_DEAL_HISTORY', 'columns': 'TRADE_DATE,MUTUAL_TYPE,NET_DEAL_AMT,BUY_AMT,SELL_AMT', 'source': 'WEB', 'client': 'WEB'})}"
                ),
            },
        )

    def get_close(self, trade_date: date) -> ProviderResult:
        warnings: list[str] = []
        raw_data: dict[str, Any] = {
            "field_sources": {
                "index_close": "real:eastmoney_index_quote",
                "sector_heatmap": "real:eastmoney_industry_rank",
                "northbound_flow": "real:eastmoney_mutual_history",
                "market_breadth": "real:eastmoney_csi_all_share_quote",
                "limit_up_stats": "real:eastmoney_limit_up_down_pool",
                "turnover_summary": "real:eastmoney_csi_all_share_kline",
            }
        }

        summary_data: dict[str, Any] = {
            "index_close": [],
            "sector_heatmap": [],
            "northbound_flow": {},
            "market_breadth": {},
            "limit_up_stats": {},
            "turnover_summary": {},
        }

        as_of_dates: set[str] = set()
        breadth_summary: dict[str, Any] = {}
        breadth_reference = "中证全指"

        try:
            summary_data["index_close"], raw_data["index_close"] = self._fetch_index_close()
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"index_close 获取失败: {exc}")

        try:
            turnover_summary, raw_data["turnover_summary"] = self._fetch_csi_all_share_turnover()
            summary_data["turnover_summary"].update(turnover_summary)
            as_of_dates.add(str(turnover_summary.get("current_date") or ""))
        except Exception as exc:  # noqa: BLE001
            raw_data["field_sources"]["turnover_summary"] = "fallback:index_proxy_from_real_quotes"
            warnings.append(f"turnover_summary 直连获取失败，已回退到指数代理口径: {exc}")
            try:
                turnover_summary, raw_data["turnover_proxy"] = self._fetch_index_trend_proxy()
                summary_data["turnover_summary"].update(turnover_summary)
                as_of_dates.add(str(turnover_summary.get("current_date") or ""))
            except Exception as fallback_exc:  # noqa: BLE001
                warnings.append(f"turnover_summary fallback 获取失败: {fallback_exc}")

        try:
            summary_data["market_breadth"], raw_data["market_breadth"] = self._fetch_market_breadth()
            breadth_reference = str(raw_data["market_breadth"].get("reference") or breadth_reference)
        except Exception as exc:  # noqa: BLE001
            raw_data["field_sources"]["market_breadth"] = "derived_from_real_a_share_quotes_excluding_unquoted"
            warnings.append(f"market_breadth 直连获取失败，已回退到逐只聚合口径: {exc}")
            try:
                breadth_summary, raw_data["a_share_snapshot"] = self._fetch_a_share_snapshot()
                summary_data["market_breadth"] = breadth_summary["market_breadth"]
                if "market_turnover_billion" not in summary_data["turnover_summary"]:
                    summary_data["turnover_summary"]["market_turnover_billion"] = breadth_summary["market_turnover_billion_fallback"]
                    summary_data["turnover_summary"]["turnover_reference"] = "A股实时快照成交额汇总"
            except Exception as fallback_exc:  # noqa: BLE001
                warnings.append(f"market_breadth fallback 获取失败: {fallback_exc}")

        try:
            summary_data["sector_heatmap"], raw_data["sector_heatmap"] = self._fetch_sector_heatmap()
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"sector_heatmap 获取失败: {exc}")

        try:
            summary_data["northbound_flow"], raw_data["northbound_flow"] = self._fetch_northbound_flow()
            as_of_dates.add(str(raw_data["northbound_flow"].get("trade_date") or ""))
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"northbound_flow 获取失败: {exc}")

        try:
            summary_data["limit_up_stats"], raw_data["limit_up_stats"] = self._fetch_limit_pool_stats(trade_date)
            as_of_dates.add(str(raw_data["limit_up_stats"].get("limit_up_qdate") or ""))
            as_of_dates.add(str(raw_data["limit_up_stats"].get("limit_down_qdate") or ""))
        except Exception as exc:  # noqa: BLE001
            raw_data["field_sources"]["limit_up_stats"] = "fallback:threshold_from_real_a_share_quotes"
            warnings.append(f"limit_up_stats 直连获取失败，已回退到阈值统计口径: {exc}")
            if not breadth_summary:
                try:
                    breadth_summary, raw_data["a_share_snapshot"] = self._fetch_a_share_snapshot()
                except Exception as fallback_exc:  # noqa: BLE001
                    warnings.append(f"limit_up_stats fallback 获取失败: {fallback_exc}")
                    breadth_summary = {}
            if breadth_summary:
                summary_data["limit_up_stats"] = breadth_summary["limit_up_stats_fallback"]

        as_of_dates.discard("")
        latest_real_date = max(as_of_dates) if as_of_dates else ""
        raw_data["latest_real_trade_date"] = latest_real_date or None

        if latest_real_date and latest_real_date != trade_date.isoformat():
            warnings.append(
                f"close 使用的最新可用真实收盘数据日期为 {latest_real_date}，当前请求日期为 {trade_date.isoformat()}"
            )

        if not summary_data["index_close"]:
            raise RuntimeError("close 真实行情获取失败：index_close 为空")

        if raw_data["field_sources"]["market_breadth"].startswith("real:"):
            warnings.append(
                f"market_breadth 已优先使用 {breadth_reference} 的真实广度口径；limit_up_stats 与 turnover_summary 已优先使用更直接的真实口径"
            )
        else:
            warnings.append(
                "market_breadth 当前为 derived_from_real，已排除无效报价；limit_up_stats 与 turnover_summary 已优先使用更直接的真实口径"
            )

        source = "real"
        for field_source in raw_data["field_sources"].values():
            if not str(field_source).startswith("real:"):
                source = "real_partial"
                break

        return ProviderResult(
            report_type=ReportType.CLOSE,
            trade_date=trade_date,
            summary_data=summary_data,
            raw_data=raw_data,
            warnings=warnings,
            source=source,
        )
