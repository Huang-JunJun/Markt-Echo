from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

TRADE_DATE = "2026-03-11"
GENERATED_AT = "2026-03-11T08:40:00+08:00"
REPORT_ID = "pre_market-2026-03-11-demo000001"

SUMMARY_DATA = {
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
    "watchlist": ["AI算力", "机器人", "低空经济"],
    "sentiment_score": 63.0,
}

RAW_DATA = {
    "provider": "mock",
    "captured_at": datetime.now().isoformat(timespec="seconds"),
    "payload": SUMMARY_DATA,
}

WARNINGS: list[str] = []


def _pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def render_pre_market_text(trade_date: str, summary_data: dict, warnings: list[str]) -> str:
    futures = summary_data["index_futures"]
    overseas = summary_data["overseas_market"]
    events = summary_data["macro_events"]
    watchlist = summary_data["watchlist"][:3]

    lines: list[str] = []
    lines.append(f"# 盘前复盘（{trade_date}）")
    lines.append("")

    lines.append("## 1) 海内外与期指信号")
    lines.append(
        f"- 期指分化：{futures[0]['name']} {futures[0]['value']}（{_pct(futures[0]['change_pct'])}），"
        f"{futures[1]['name']} {futures[1]['value']}（{_pct(futures[1]['change_pct'])}）。"
    )
    lines.append(
        f"- 隔夜海外偏强：{overseas[0]['name']} {overseas[0]['value']}（{_pct(overseas[0]['change_pct'])}），"
        f"{overseas[1]['name']} {overseas[1]['value']}（{_pct(overseas[1]['change_pct'])}）。"
    )
    lines.append("- 综合信号：盘前情绪中性偏强，预计开盘资金更偏向景气成长方向。")
    lines.append("")

    lines.append("## 2) 今日关键事件")
    for event in events:
        lines.append(f"- {event}")
    lines.append("")

    lines.append("## 3) 重点观察方向")
    lines.append(f"- {watchlist[0]}：观察开盘 15 分钟成交放大是否延续。")
    lines.append(f"- {watchlist[1]}：观察高开后是否出现一致性追价。")
    lines.append(f"- {watchlist[2]}：观察分支轮动强度与龙头封单质量。")
    lines.append("")

    lines.append("## 4) 开盘前执行清单")
    lines.append("- 先看 9:30-9:35 成交结构，确认资金是否集中在核心方向。")
    lines.append("- 对昨日强势股只做分时转强后的跟随，不做弱转强预判。")
    lines.append("- 若指数冲高回落且量能不配合，降低追涨仓位。")
    lines.append("- 开盘 30 分钟内完成一次持仓风险检查与止损位确认。")
    lines.append("")

    lines.append("## 数据提示")
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- 无")

    return "\n".join(lines)


def main() -> None:
    api_response = {
        "ok": True,
        "data": {
            "report_id": REPORT_ID,
            "report_type": "pre_market",
            "trade_date": TRADE_DATE,
            "generated_at": GENERATED_AT,
            "summary_data": SUMMARY_DATA,
            "raw_data": RAW_DATA,
            "warnings": WARNINGS,
            "status": "SUCCESS",
            "source": "mock",
        },
        "error": None,
    }

    final_text = render_pre_market_text(
        trade_date=TRADE_DATE,
        summary_data=SUMMARY_DATA,
        warnings=WARNINGS,
    )

    base_dir = Path(__file__).resolve().parent
    json_path = base_dir / "pre_market_api_response_sample.json"
    md_path = base_dir / "pre_market_final_text_sample.md"

    json_path.write_text(
        json.dumps(api_response, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(final_text + "\n", encoding="utf-8")

    print(f"Wrote: {json_path}")
    print(f"Wrote: {md_path}")


if __name__ == "__main__":
    main()
