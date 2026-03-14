from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, time
from typing import Any

from app.providers.base import BaseProvider, ProviderResult
from app.schemas import ReportType


SINA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.sina.com.cn",
}

SINA_RANK_URL = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
SINA_QUOTE_URL = "https://hq.sinajs.cn/list="
SINA_BOARD_URL = "https://vip.stock.finance.sina.com.cn/corp/go.php/vCI_CorpOtherInfo/stockid/{code}/menu_num/5.phtml"

INDEX_SYMBOLS = {
    "上证指数": "sh000001",
    "创业板指": "sz399006",
}

BOARD_CONCEPT_STOPWORDS = {
    "融资融券",
    "基金重仓",
    "MSCI中国",
    "深股通",
    "沪股通",
    "陆股通",
    "转融券标的",
    "百元股",
    "机构重仓",
    "社保重仓",
    "互联互通",
    "地方国资改革",
    "中央国资改革",
    "中盘",
    "大盘",
    "小盘",
    "中证500",
    "沪深300",
    "上证180",
    "深成500",
    "年度强势",
    "标准普尔",
    "富时罗素",
    "破净股",
    "高市净率",
    "高市盈率",
    "昨日涨停",
    "昨日连板",
    "增持回购",
    "股权激励",
    "业绩预降",
    "业绩预增",
    "预盈预增",
    "高送转",
    "送转填权",
    "国资改革",
    "分拆上市",
    "金融参股",
    "高校背景",
    "创投",
    "专精特新",
    "低价",
    "中字头",
    "小盘",
    "中盘",
    "大盘",
    "黄河三角",
    "皖江区域",
    "阿里概念",
    "谷歌概念",
}

QUOTE_LINE_RE = re.compile(r'var hq_str_(?P<symbol>[^=]+)="(?P<payload>.*)"\s*;')
BOARD_DIRECTION_PREFERRED_RE = re.compile(
    r"(AI|算力|机器人|半导体|芯片|通信|光|CPO|IDC|数据|云|5G|服务器|液冷|"
    r"新能源|储能|锂|电池|汽车|智驾|无人驾驶|医药|创新药|消费电子|军工|低空|"
    r"铜|稀土|黄金|煤炭|电力|风电|光伏)"
)


def _normalize_stock_code(code: str) -> str:
    normalized = code.strip().upper()
    if normalized.startswith(("SH", "SZ", "BJ")):
        return normalized
    if normalized.isdigit() and len(normalized) == 6:
        if normalized.startswith("6"):
            return f"SH{normalized}"
        if normalized.startswith(("8", "4", "9")):
            return f"BJ{normalized}"
        return f"SZ{normalized}"
    return normalized


def _symbol_to_normalized_code(symbol: str) -> str:
    normalized = symbol.strip().lower()
    if normalized.startswith(("sh", "sz", "bj")):
        return normalized[:2].upper() + normalized[2:]
    return _normalize_stock_code(normalized)


def _code_to_sina_symbol(code: str) -> str:
    normalized = _normalize_stock_code(code)
    if normalized.startswith(("SH", "SZ", "BJ")):
        return normalized.lower()
    return normalized.lower()


class RealAuctionProvider(BaseProvider):
    def _get_text(self, url: str, encoding: str = "utf-8") -> str:
        req = urllib.request.Request(url, headers=SINA_HEADERS)
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read()
        return body.decode(encoding, errors="ignore")

    @staticmethod
    def _as_float(value: Any, default: float = 0.0) -> float:
        if value in (None, "", "-", "--"):
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _fetch_rank_rows(self, sort: str, asc: int, limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        query = urllib.parse.urlencode(
            {
                "page": 1,
                "num": max(limit * 3, 20),
                "sort": sort,
                "asc": asc,
                "node": "hs_a",
                "symbol": "",
                "_s_r_a": "page",
            }
        )
        url = f"{SINA_RANK_URL}?{query}"
        rows = json.loads(self._get_text(url=url, encoding="gbk") or "[]")

        normalized_rows: list[dict[str, Any]] = []
        for row in rows:
            symbol = str(row.get("symbol") or "").lower()
            code = _normalize_stock_code(str(row.get("code") or ""))
            if not symbol.startswith(("sh", "sz")):
                continue
            normalized_rows.append(
                {
                    "code": code,
                    "symbol": symbol,
                    "name": str(row.get("name") or "").strip(),
                    "change_pct": round(self._as_float(row.get("changepercent")), 3),
                    "turnover": round(self._as_float(row.get("amount")), 2),
                    "trade": round(self._as_float(row.get("trade")), 3),
                    "ticktime": str(row.get("ticktime") or "").strip(),
                }
            )

        return normalized_rows[:limit], {
            "sort": sort,
            "asc": asc,
            "requested_limit": limit,
            "returned_count": len(normalized_rows[:limit]),
            "source_url": url,
        }

    def _fetch_index_auction(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        symbols = list(INDEX_SYMBOLS.values())
        url = f"{SINA_QUOTE_URL}{','.join(symbols)}"
        text = self._get_text(url=url, encoding="gbk")

        symbol_to_name = {symbol: name for name, symbol in INDEX_SYMBOLS.items()}
        points: list[dict[str, Any]] = []
        raw: dict[str, Any] = {"source_url": url, "quotes": {}}

        for line in text.splitlines():
            match = QUOTE_LINE_RE.search(line.strip())
            if not match:
                continue
            symbol = match.group("symbol")
            if symbol not in symbol_to_name:
                continue

            fields = match.group("payload").split(",")
            if len(fields) < 4:
                continue
            previous_close = self._as_float(fields[2]) if len(fields) > 2 else 0.0
            latest_value = self._as_float(fields[3]) if len(fields) > 3 else 0.0
            change_pct = ((latest_value - previous_close) / previous_close * 100.0) if previous_close else None

            points.append(
                {
                    "name": symbol_to_name[symbol],
                    "value": round(latest_value, 2),
                    "change_pct": round(change_pct, 2) if change_pct is not None else None,
                }
            )
            raw["quotes"][symbol] = {
                "display_name": fields[0] if fields else symbol_to_name[symbol],
                "open": self._as_float(fields[1]) if len(fields) > 1 else None,
                "previous_close": previous_close,
                "latest_value": latest_value,
                "high": self._as_float(fields[4]) if len(fields) > 4 else None,
                "low": self._as_float(fields[5]) if len(fields) > 5 else None,
                "snapshot_date": fields[30] if len(fields) > 30 else "",
                "snapshot_time": fields[31] if len(fields) > 31 else "",
            }

        if len(points) != len(INDEX_SYMBOLS):
            raise RuntimeError("index auction quotes are incomplete")
        return points, raw

    def _fetch_quote_snapshots(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        unique_symbols = []
        seen: set[str] = set()
        for symbol in symbols:
            current = symbol.lower()
            if current in seen:
                continue
            seen.add(current)
            unique_symbols.append(current)

        if not unique_symbols:
            return {}

        url = f"{SINA_QUOTE_URL}{','.join(unique_symbols)}"
        text = self._get_text(url=url, encoding="gbk")
        snapshots: dict[str, dict[str, Any]] = {}

        for line in text.splitlines():
            match = QUOTE_LINE_RE.search(line.strip())
            if not match:
                continue
            symbol = match.group("symbol").lower()
            fields = match.group("payload").split(",")
            snapshots[symbol] = {
                "symbol": symbol,
                "code": _symbol_to_normalized_code(symbol),
                "snapshot_date": fields[30] if len(fields) > 30 else "",
                "snapshot_time": fields[31] if len(fields) > 31 else "",
                "latest_value": self._as_float(fields[3]) if len(fields) > 3 else None,
                "change_pct": round(
                    ((self._as_float(fields[3]) - self._as_float(fields[2])) / self._as_float(fields[2]) * 100.0),
                    3,
                )
                if len(fields) > 3 and self._as_float(fields[2])
                else None,
            }
        return snapshots

    def _parse_board_page(self, code: str) -> tuple[dict[str, Any], dict[str, Any]]:
        normalized_code = _normalize_stock_code(code)
        stock_id = normalized_code[2:] if normalized_code.startswith(("SH", "SZ", "BJ")) else normalized_code
        url = SINA_BOARD_URL.format(code=stock_id)
        html = self._get_text(url=url, encoding="gbk")

        industry_match = re.search(
            r"所属行业板块</td>.*?同行业个股</td>\s*</tr>\s*<tr>\s*<td class=\"ct\" align=\"center\">([^<]+)</td>",
            html,
            re.S,
        )
        industry = industry_match.group(1).strip() if industry_match else None
        concepts = [
            item.strip()
            for item in re.findall(
                r"<td class=\"ct\" align=\"center\">([^<]+)</td>\s*<td class=\"ct\" align=\"center\"><a target=\"_blank\" href=\"http://vip\.stock\.finance\.sina\.com\.cn/mkt/#",
                html,
            )
            if item.strip()
        ]

        return (
            {
                "industry": industry,
                "concepts": concepts,
            },
            {
                "source_url": url,
                "industry": industry,
                "concept_count": len(concepts),
            },
        )

    def _collect_board_profiles(self, rows: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, Any], list[str]]:
        profiles: dict[str, dict[str, Any]] = {}
        raw: dict[str, Any] = {}
        warnings: list[str] = []

        for row in rows:
            code = str(row.get("code") or "")
            if not code or code in profiles:
                continue
            try:
                profiles[code], raw[code] = self._parse_board_page(code)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"{code} 板块归属获取失败: {exc}")
        return profiles, raw, warnings

    def _clean_concept_name(self, name: str) -> str | None:
        current = str(name or "").strip()
        if not current or current in BOARD_CONCEPT_STOPWORDS:
            return None
        if any(token in current for token in ("昨日", "重仓", "股通", "互通", "罗素", "标的")):
            return None
        return current

    def _derive_limit_up_candidates(
        self,
        top_gainers: list[dict[str, Any]],
        turnover_top: list[dict[str, Any]],
        board_profiles: dict[str, dict[str, Any]],
    ) -> tuple[list[str], list[dict[str, Any]], str]:
        scores: dict[str, float] = {}
        derivation: list[dict[str, Any]] = []

        def add_direction(direction: str, weight: float, basis: dict[str, Any]) -> None:
            scores[direction] = scores.get(direction, 0.0) + weight
            derivation.append(
                {
                    "direction": direction,
                    "weight": round(weight, 2),
                    "basis": basis,
                }
            )

        board_page_hit = False
        ranked_rows = [(top_gainers, 6.0, "top_gainers"), (turnover_top, 4.0, "turnover_top")]
        for rows, base_weight, source_name in ranked_rows:
            for idx, row in enumerate(rows):
                code = str(row.get("code") or "")
                profile = board_profiles.get(code) or {}
                weight = max(1.0, base_weight - idx)
                added = False
                concepts = [self._clean_concept_name(concept) for concept in profile.get("concepts") or []]
                concepts = [concept for concept in concepts if concept]
                preferred_concepts = [
                    concept for concept in concepts if BOARD_DIRECTION_PREFERRED_RE.search(concept)
                ]
                for concept in preferred_concepts or concepts:
                    add_direction(
                        concept,
                        weight,
                        {
                            "source": source_name,
                            "code": code,
                            "name": row.get("name"),
                            "board_type": "concept",
                        },
                    )
                    board_page_hit = True
                    added = True
                    break

                if added:
                    continue

                industry = str(profile.get("industry") or "").strip()
                if industry:
                    add_direction(
                        industry,
                        weight * 0.9,
                        {
                            "source": source_name,
                            "code": code,
                            "name": row.get("name"),
                            "board_type": "industry",
                        },
                    )
                    board_page_hit = True

        if not scores:
            growth_codes = sum(
                1
                for row in top_gainers[:4]
                if str(row.get("code") or "").startswith(("SZ300", "SH688", "SZ301"))
            )
            if growth_codes >= 2:
                scores["成长科技"] = 10.0
                derivation.append(
                    {
                        "direction": "成长科技",
                        "weight": 10.0,
                        "basis": {"source": "fallback", "reason": "growth_code_density"},
                    }
                )

            weight_codes = sum(
                1
                for row in turnover_top[:4]
                if str(row.get("code") or "").startswith(("SH600", "SH601", "SH603", "SZ000"))
            )
            if weight_codes >= 2:
                scores["权重承接"] = 8.0
                derivation.append(
                    {
                        "direction": "权重承接",
                        "weight": 8.0,
                        "basis": {"source": "fallback", "reason": "weight_code_density"},
                    }
                )

        ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        directions = [name for name, _ in ordered[:3]]
        mode = "derived_from_real_stock_rank_and_board_membership" if board_page_hit else "fallback:derived_from_real_stock_rank"
        return directions, derivation, mode

    def _derive_auction_sentiment(
        self,
        index_auction: list[dict[str, Any]],
        top_gainers: list[dict[str, Any]],
        top_losers: list[dict[str, Any]],
        turnover_top: list[dict[str, Any]],
    ) -> float | None:
        if not index_auction and not top_gainers and not turnover_top:
            return None

        index_avg = (
            sum(float(item.get("change_pct") or 0.0) for item in index_auction) / len(index_auction)
            if index_auction
            else 0.0
        )
        gainer_avg = (
            sum(float(item.get("change_pct") or 0.0) for item in top_gainers[:3]) / min(len(top_gainers), 3)
            if top_gainers
            else 0.0
        )
        loser_pressure = (
            sum(abs(float(item.get("change_pct") or 0.0)) for item in top_losers[:3]) / min(len(top_losers), 3)
            if top_losers
            else 0.0
        )
        turnover_pos_ratio = (
            sum(1 for item in turnover_top[:5] if float(item.get("change_pct") or 0.0) > 0) / min(len(turnover_top), 5)
            if turnover_top
            else 0.5
        )

        score = 50.0
        score += index_avg * 12.0
        score += min(gainer_avg, 10.0) * 1.6
        score -= min(loser_pressure, 10.0) * 1.1
        score += (turnover_pos_ratio - 0.5) * 18.0
        return round(max(0.0, min(100.0, score)), 1)

    def _derive_snapshot_meta(self, snapshots: dict[str, dict[str, Any]]) -> dict[str, Any]:
        dated = [item for item in snapshots.values() if item.get("snapshot_date")]
        if not dated:
            return {"latest_real_snapshot_date": None, "latest_real_snapshot_time": None}

        latest = max(
            dated,
            key=lambda item: f"{item.get('snapshot_date') or ''} {item.get('snapshot_time') or ''}",
        )
        return {
            "latest_real_snapshot_date": latest.get("snapshot_date"),
            "latest_real_snapshot_time": latest.get("snapshot_time"),
        }

    def _is_auction_window(self, now_ts: datetime | None = None) -> bool:
        current = now_ts or datetime.now()
        return time(9, 15) <= current.time() <= time(9, 26)

    def get_auction(self, trade_date: date) -> ProviderResult:
        warnings: list[str] = []
        raw_data: dict[str, Any] = {
            "field_sources": {
                "index_auction": "real:sina_index_quote",
                "top_gainers": "real:sina_hq_rank_changepercent_desc",
                "top_losers": "real:sina_hq_rank_changepercent_asc",
                "turnover_top": "real:sina_hq_rank_amount_desc",
                "limit_up_candidates": "derived_from_real_stock_rank_and_board_membership",
                "auction_sentiment": "derived_from_real_index_and_stock_rank",
            }
        }

        summary_data: dict[str, Any] = {
            "index_auction": [],
            "top_gainers": [],
            "top_losers": [],
            "turnover_top": [],
            "limit_up_candidates": [],
            "auction_sentiment": None,
        }

        try:
            summary_data["index_auction"], raw_data["index_auction"] = self._fetch_index_auction()
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"index_auction 获取失败: {exc}")

        try:
            summary_data["top_gainers"], raw_data["top_gainers"] = self._fetch_rank_rows(
                sort="changepercent",
                asc=0,
                limit=5,
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"top_gainers 获取失败: {exc}")

        try:
            summary_data["top_losers"], raw_data["top_losers"] = self._fetch_rank_rows(
                sort="changepercent",
                asc=1,
                limit=3,
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"top_losers 获取失败: {exc}")

        try:
            summary_data["turnover_top"], raw_data["turnover_top"] = self._fetch_rank_rows(
                sort="amount",
                asc=0,
                limit=5,
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"turnover_top 获取失败: {exc}")

        if not summary_data["index_auction"] and not summary_data["top_gainers"] and not summary_data["turnover_top"]:
            raise RuntimeError("auction 真实行情获取失败：指数、强势股与成交榜均为空")

        board_rows = summary_data["top_gainers"][:3] + summary_data["turnover_top"][:3]
        board_profiles: dict[str, dict[str, Any]] = {}
        if board_rows:
            board_profiles, raw_data["board_profiles"], board_warnings = self._collect_board_profiles(board_rows)
            warnings.extend(board_warnings)
        else:
            raw_data["board_profiles"] = {}

        directions, derivation, direction_mode = self._derive_limit_up_candidates(
            top_gainers=summary_data["top_gainers"],
            turnover_top=summary_data["turnover_top"],
            board_profiles=board_profiles,
        )
        summary_data["limit_up_candidates"] = directions
        raw_data["limit_up_candidate_derivation"] = derivation
        raw_data["field_sources"]["limit_up_candidates"] = direction_mode
        if not direction_mode.startswith("derived_from_real"):
            warnings.append("limit_up_candidates 直连板块归属不足，已回退到竞价个股风格聚合")
        else:
            warnings.append("limit_up_candidates 当前为 derived：基于真实竞价个股排行与所属板块派生，不是官方板块竞价榜单")

        summary_data["auction_sentiment"] = self._derive_auction_sentiment(
            index_auction=summary_data["index_auction"],
            top_gainers=summary_data["top_gainers"],
            top_losers=summary_data["top_losers"],
            turnover_top=summary_data["turnover_top"],
        )
        warnings.append("auction_sentiment 当前为 derived：基于真实指数与个股竞价强弱派生，不是交易所官方情绪口径")

        quote_symbols = list(INDEX_SYMBOLS.values())
        quote_symbols.extend(row["symbol"] for row in board_rows if row.get("symbol"))
        try:
            raw_data["quote_snapshots"] = self._fetch_quote_snapshots(quote_symbols)
            raw_data.update(self._derive_snapshot_meta(raw_data["quote_snapshots"]))
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"quote_snapshot 获取失败: {exc}")

        latest_snapshot_date = raw_data.get("latest_real_snapshot_date")
        latest_snapshot_time = raw_data.get("latest_real_snapshot_time")
        if latest_snapshot_date and latest_snapshot_date != trade_date.isoformat():
            warnings.append(
                f"auction 使用的最新可用真实快照日期为 {latest_snapshot_date}，当前请求日期为 {trade_date.isoformat()}"
            )
        if latest_snapshot_time and not self._is_auction_window():
            warnings.append(
                f"当前不在 09:15-09:26 竞价窗口，auction 使用的是最新可用实时快照（{latest_snapshot_date or '未知日期'} {latest_snapshot_time}）"
            )

        source = "real"
        for field_source in raw_data["field_sources"].values():
            if not str(field_source).startswith("real:"):
                source = "real_partial"
                break

        return ProviderResult(
            report_type=ReportType.AUCTION,
            trade_date=trade_date,
            summary_data=summary_data,
            raw_data=raw_data,
            warnings=list(dict.fromkeys(warnings)),
            source=source,
        )
