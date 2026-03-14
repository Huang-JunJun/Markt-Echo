from __future__ import annotations

import csv
import io
import json
import re
from datetime import date
from typing import Any

import httpx

from app.providers.base import BaseProvider, ProviderResult
from app.schemas import ReportType


STOOQ_INDEX_URLS = {
    "NASDAQ": "https://stooq.com/q/d/l/?s=%5Endq&i=d",
    "S&P 500": "https://stooq.com/q/d/l/?s=%5Espx&i=d",
}

SINA_FUTURES_URL = "https://hq.sinajs.cn/list=nf_IF0,nf_IC0"
STATS_GOV_CALENDAR_URL = "https://data.stats.gov.cn/"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    )
}

SINA_HEADERS = {
    **DEFAULT_HEADERS,
    "Referer": "https://finance.sina.com.cn",
}

NUMERIC_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")
DATE_DATA_RE = re.compile(r"var\s+dateData\s*=\s*(\[\[.*?\]\]);", re.S)
SINA_LINE_RE = re.compile(r'var hq_str_(?P<symbol>[^=]+)="(?P<payload>.*)"\s*;')


class RealPreMarketProvider(BaseProvider):
    def _get_text(self, url: str, headers: dict[str, str] | None = None, encoding: str | None = None) -> str:
        response = httpx.get(
            url,
            headers=headers or DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=20.0,
            trust_env=False,
        )
        response.raise_for_status()
        if encoding:
            return response.content.decode(encoding, errors="ignore")
        return response.text

    def _fetch_stooq_index(self, name: str, url: str) -> tuple[dict[str, Any], dict[str, Any]]:
        text = self._get_text(url=url)
        rows = list(csv.DictReader(io.StringIO(text)))
        if len(rows) < 2:
            raise RuntimeError(f"{name} returned insufficient rows")

        latest = rows[-1]
        previous = rows[-2]
        latest_close = float(latest["Close"])
        previous_close = float(previous["Close"])
        change_pct = ((latest_close - previous_close) / previous_close * 100.0) if previous_close else None

        return (
            {
                "name": name,
                "value": round(latest_close, 2),
                "change_pct": round(change_pct, 2) if change_pct is not None else None,
            },
            {
                "as_of_date": latest["Date"],
                "previous_date": previous["Date"],
                "latest_close": latest_close,
                "previous_close": previous_close,
                "source_url": url,
            },
        )

    def _fetch_overseas_market(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        points: list[dict[str, Any]] = []
        raw: dict[str, Any] = {}
        for name, url in STOOQ_INDEX_URLS.items():
            point, point_raw = self._fetch_stooq_index(name=name, url=url)
            points.append(point)
            raw[name] = point_raw
        return points, raw

    def _extract_last_numeric(self, values: list[str]) -> float | None:
        for value in reversed(values):
            if NUMERIC_RE.match(value):
                return float(value)
        return None

    def _fetch_index_futures(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        text = self._get_text(url=SINA_FUTURES_URL, headers=SINA_HEADERS, encoding="gbk")
        alias_map = {
            "nf_IF0": "沪深300主连",
            "nf_IC0": "中证500主连",
        }

        points: list[dict[str, Any]] = []
        raw: dict[str, Any] = {}
        for line in text.splitlines():
            match = SINA_LINE_RE.search(line.strip())
            if not match:
                continue
            symbol = match.group("symbol")
            if symbol not in alias_map:
                continue

            fields = match.group("payload").split(",")
            if len(fields) < 4:
                raise RuntimeError(f"{symbol} quote payload is incomplete")

            latest_value = float(fields[3])
            previous_close = self._extract_last_numeric(fields[:-1])
            if previous_close in (None, 0):
                change_pct = None
            else:
                change_pct = (latest_value - previous_close) / previous_close * 100.0

            as_of_date = next((field for field in fields if DATE_RE.match(field)), None)
            as_of_time = next((field for field in fields if TIME_RE.match(field)), None)

            points.append(
                {
                    "name": alias_map[symbol],
                    "value": round(latest_value, 2),
                    "change_pct": round(change_pct, 2) if change_pct is not None else None,
                }
            )
            raw[symbol] = {
                "name": alias_map[symbol],
                "as_of_date": as_of_date,
                "as_of_time": as_of_time,
                "latest_value": latest_value,
                "previous_close": previous_close,
                "source_url": SINA_FUTURES_URL,
            }

        if len(points) != 2:
            raise RuntimeError("index futures quotes are incomplete")
        return points, raw

    def _fetch_macro_events(self, trade_date: date) -> tuple[list[str], dict[str, Any]]:
        text = self._get_text(url=STATS_GOV_CALENDAR_URL)
        match = DATE_DATA_RE.search(text)
        if not match:
            raise RuntimeError("stats.gov schedule payload not found")

        date_data = json.loads(match.group(1))
        calendar_rows = date_data[3] if len(date_data) > 3 else []
        target_date = trade_date.isoformat()

        matched_events = [
            item
            for item in calendar_rows
            if isinstance(item, dict) and str(item.get("ym", "")).startswith(target_date)
        ]
        matched_events.sort(key=lambda item: str(item.get("ym", "")))

        events = []
        for item in matched_events:
            ts = str(item.get("ym", ""))
            title = str(item.get("ctitle", "")).strip()
            if not title:
                continue
            events.append(f"{ts[11:16]} {title}")

        server_time = None
        if date_data and date_data[0] and isinstance(date_data[0][0], dict):
            server_time = date_data[0][0].get("serverTime")

        return events, {
            "server_time": server_time,
            "matched_count": len(events),
            "source_url": STATS_GOV_CALENDAR_URL,
        }

    def _derive_sentiment_score(
        self,
        overseas_market: list[dict[str, Any]],
        index_futures: list[dict[str, Any]],
    ) -> float | None:
        changes: list[float] = []
        for item in overseas_market + index_futures:
            change_pct = item.get("change_pct")
            if change_pct is None:
                continue
            changes.append(float(change_pct))

        if not changes:
            return None

        average_change = sum(changes) / len(changes)
        score = 50.0 + average_change * 20.0
        return round(max(0.0, min(100.0, score)), 1)

    def _find_item(self, items: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
        return next((item for item in items if item.get("name") == name), None)

    def _format_change_pct(self, value: float | None) -> str:
        if value is None:
            return "变动未知"
        return f"{value:+.2f}%"

    def _derive_macro_watch(self, macro_events: list[str]) -> tuple[str | None, list[str]]:
        keyword_map = [
            ("采购经理", "制造业景气链，关注数据公布前后的预期交易"),
            ("居民消费价格", "通胀敏感链，关注消费与利率预期方向"),
            ("工业生产者", "价格传导链，观察上游资源与中游成本线索"),
            ("固定资产投资", "稳增长链，关注基建与顺周期承接"),
            ("房地产", "地产链，关注政策敏感方向的反馈"),
            ("社会消费品零售", "内需消费链，观察消费修复强弱"),
            ("能源", "资源能源链，关注供给与价格驱动方向"),
            ("国民经济运行", "宏观总量链，关注指数对总量数据的反馈"),
        ]
        for event in macro_events:
            for keyword, direction in keyword_map:
                if keyword in event:
                    return direction, [f"macro_event={event}"]
        if macro_events:
            return "临近宏观数据窗口，关注预期差驱动的方向选择", [f"macro_event={macro_events[0]}"]
        return None, []

    def _derive_watchlist(
        self,
        overseas_market: list[dict[str, Any]],
        index_futures: list[dict[str, Any]],
        macro_events: list[str],
        sentiment_score: float | None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        watchlist: list[str] = []
        derivation: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add(direction: str, basis: list[str], mode: str = "derived") -> None:
            if direction in seen:
                return
            seen.add(direction)
            watchlist.append(direction)
            derivation.append({"direction": direction, "basis": basis, "mode": mode})

        nasdaq = self._find_item(overseas_market, "NASDAQ")
        spx = self._find_item(overseas_market, "S&P 500")
        if_contract = self._find_item(index_futures, "沪深300主连")
        ic_contract = self._find_item(index_futures, "中证500主连")

        nasdaq_change = nasdaq.get("change_pct") if nasdaq else None
        spx_change = spx.get("change_pct") if spx else None
        if_change = if_contract.get("change_pct") if if_contract else None
        ic_change = ic_contract.get("change_pct") if ic_contract else None

        if nasdaq_change is not None:
            if nasdaq_change <= -0.5:
                add(
                    f"高估值成长承压，先看海外科技映射修复（纳指{self._format_change_pct(float(nasdaq_change))}）",
                    [f"NASDAQ.change_pct={nasdaq_change}"],
                )
            elif nasdaq_change >= 0.5:
                add(
                    f"海外科技映射偏暖，留意成长弹性承接（纳指{self._format_change_pct(float(nasdaq_change))}）",
                    [f"NASDAQ.change_pct={nasdaq_change}"],
                )

        if if_change is not None and ic_change is not None:
            spread = float(if_change) - float(ic_change)
            if spread >= 0.3:
                add(
                    (
                        "大盘权重相对占优，观察权重与红利能否稳住指数"
                        f"（IF{self._format_change_pct(float(if_change))}，IC{self._format_change_pct(float(ic_change))}）"
                    ),
                    [f"IF.change_pct={if_change}", f"IC.change_pct={ic_change}", f"spread={spread:.2f}"],
                )
            elif spread <= -0.3:
                add(
                    (
                        "中小盘弹性更强，观察题材修复能否获得期指确认"
                        f"（IF{self._format_change_pct(float(if_change))}，IC{self._format_change_pct(float(ic_change))}）"
                    ),
                    [f"IF.change_pct={if_change}", f"IC.change_pct={ic_change}", f"spread={spread:.2f}"],
                )
            elif float(if_change) < 0 and float(ic_change) < 0:
                add(
                    (
                        "期指同步承压，盘初先看止跌后的承接强弱"
                        f"（IF{self._format_change_pct(float(if_change))}，IC{self._format_change_pct(float(ic_change))}）"
                    ),
                    [f"IF.change_pct={if_change}", f"IC.change_pct={ic_change}"],
                )
            elif float(if_change) > 0 and float(ic_change) > 0:
                add(
                    (
                        "期指同步偏强，关注共振后的主线扩散"
                        f"（IF{self._format_change_pct(float(if_change))}，IC{self._format_change_pct(float(ic_change))}）"
                    ),
                    [f"IF.change_pct={if_change}", f"IC.change_pct={ic_change}"],
                )

        macro_direction, macro_basis = self._derive_macro_watch(macro_events=macro_events)
        if macro_direction:
            add(macro_direction, macro_basis)
        else:
            add(
                "今日无新增宏观定时扰动，优先观察指数与期指共振后的主线确认",
                ["macro_events=empty"],
                mode="fallback",
            )

        if len(watchlist) < 3 and spx_change is not None:
            if float(spx_change) <= -0.5:
                add(
                    f"风险偏好偏弱，先看防御与低波动承接（标普{self._format_change_pct(float(spx_change))}）",
                    [f"S&P500.change_pct={spx_change}"],
                )
            elif float(spx_change) >= 0.5:
                add(
                    f"风险偏好修复，关注高开后的量能跟随（标普{self._format_change_pct(float(spx_change))}）",
                    [f"S&P500.change_pct={spx_change}"],
                )

        if len(watchlist) < 3 and sentiment_score is not None:
            if sentiment_score <= 45:
                add(
                    f"盘初先验证情绪止跌，再决定是否跟随进攻（情绪分 {sentiment_score:.1f}）",
                    [f"sentiment_score={sentiment_score}"],
                    mode="fallback",
                )
            elif sentiment_score >= 55:
                add(
                    f"若竞价与指数共振转强，可优先跟随先放量方向（情绪分 {sentiment_score:.1f}）",
                    [f"sentiment_score={sentiment_score}"],
                    mode="fallback",
                )
            else:
                add(
                    f"情绪中性，优先跟踪最先获得指数共振的方向（情绪分 {sentiment_score:.1f}）",
                    [f"sentiment_score={sentiment_score}"],
                    mode="fallback",
                )

        while len(watchlist) < 3:
            add(
                f"盘初先看指数方向确认，再决定题材跟随强度（观察位 {len(watchlist) + 1}）",
                ["real_signals=insufficient"],
                mode="fallback",
            )

        return watchlist[:3], derivation[:3]

    def get_pre_market(self, trade_date: date) -> ProviderResult:
        warnings: list[str] = []
        raw_data: dict[str, Any] = {
            "field_sources": {
                "overseas_market": "real:stooq",
                "index_futures": "real:sina_finance",
                "macro_events": "real:stats_gov_schedule",
                "watchlist": "derived_from_real_market_and_macro",
                "sentiment_score": "derived_from_real",
            }
        }

        overseas_market: list[dict[str, Any]] = []
        index_futures: list[dict[str, Any]] = []
        macro_events: list[str] = []

        try:
            overseas_market, raw_data["overseas_market"] = self._fetch_overseas_market()
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"overseas_market 获取失败: {exc}")

        try:
            index_futures, raw_data["index_futures"] = self._fetch_index_futures()
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"index_futures 获取失败: {exc}")

        try:
            macro_events, raw_data["macro_events"] = self._fetch_macro_events(trade_date=trade_date)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"macro_events 获取失败: {exc}")

        if not overseas_market and not index_futures:
            raise RuntimeError("pre_market 真实行情获取失败：海外市场与期指均为空")

        sentiment_score = self._derive_sentiment_score(
            overseas_market=overseas_market,
            index_futures=index_futures,
        )
        watchlist, raw_data["watchlist_derivation"] = self._derive_watchlist(
            overseas_market=overseas_market,
            index_futures=index_futures,
            macro_events=macro_events,
            sentiment_score=sentiment_score,
        )
        warnings.append("watchlist 当前为 derived：基于真实行情与宏观事件派生，不是外部板块热度直取")

        return ProviderResult(
            report_type=ReportType.PRE_MARKET,
            trade_date=trade_date,
            summary_data={
                "index_futures": index_futures,
                "overseas_market": overseas_market,
                "macro_events": macro_events,
                "watchlist": watchlist,
                "sentiment_score": sentiment_score,
            },
            raw_data=raw_data,
            warnings=warnings,
            source="real_partial",
        )
