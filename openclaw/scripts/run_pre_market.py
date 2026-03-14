#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _build_opener() -> urllib.request.OpenerDirector:
    # Ignore host proxy env so 127.0.0.1 calls stay local.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _http_json(
    opener: urllib.request.OpenerDirector,
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url=url, method=method, headers=headers, data=data)
    try:
        with opener.open(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc.reason}") from exc


def fetch_pre_market(base_url: str, use_mock: bool) -> dict[str, Any]:
    opener = _build_opener()
    pre_market_url = f"{base_url.rstrip('/')}/v1/review/pre-market"
    api_response = _http_json(
        opener=opener,
        method="POST",
        url=pre_market_url,
        payload={"use_mock": use_mock},
    )
    if not api_response.get("ok"):
        raise RuntimeError(f"pre-market API returned not ok: {api_response}")

    data = api_response.get("data") or {}
    report_id = data.get("report_id")
    trade_date = str(data.get("trade_date") or "")
    summary_data = data.get("summary_data") or {}
    warnings = data.get("warnings") or []

    if not report_id:
        raise RuntimeError(f"missing report_id in response: {api_response}")
    if not trade_date:
        raise RuntimeError(f"missing trade_date in response: {api_response}")

    return {
        "report_id": report_id,
        "trade_date": trade_date,
        "summary_data": summary_data,
        "warnings": warnings,
        "pre_market_api_response": api_response,
    }


def _default_log_path() -> Path:
    # script: <project>/openclaw/scripts/run_pre_market.py
    # logs:   <project>/.data/pre_market_runs.jsonl
    project_root = Path(__file__).resolve().parents[2]
    return project_root / ".data" / "pre_market_runs.jsonl"


def _append_log(log_path: Path, entry: dict[str, Any]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def writeback_final_text(base_url: str, report_id: str, final_text: str) -> dict[str, Any]:
    opener = _build_opener()
    report_id_enc = urllib.parse.quote(str(report_id), safe="")
    writeback_url = f"{base_url.rstrip('/')}/v1/reports/{report_id_enc}/final-text"
    writeback_response = _http_json(
        opener=opener,
        method="POST",
        url=writeback_url,
        payload={"final_output_text": final_text, "status": "SUCCESS"},
    )
    return {
        "report_id": report_id,
        "writeback_response": writeback_response,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run pre_market fetch/writeback helpers.")
    parser.add_argument(
        "--mode",
        default="fetch",
        choices=["fetch", "writeback"],
        help="fetch: get structured data only; writeback: persist final_text",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Data service base URL",
    )
    parser.add_argument(
        "--use-mock",
        default="true",
        choices=["true", "false"],
        help="Whether to request mock mode from API",
    )
    parser.add_argument(
        "--output",
        default="json",
        choices=["text", "json"],
        help="Output format for stdout",
    )
    parser.add_argument(
        "--report-id",
        default="",
        help="Required when mode=writeback",
    )
    parser.add_argument(
        "--final-text-file",
        default="",
        help="UTF-8 text file path, required when mode=writeback",
    )
    parser.add_argument(
        "--log-path",
        default=str(_default_log_path()),
        help="Append full run payload to this JSONL file for troubleshooting",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    log_path = Path(args.log_path)
    use_mock = args.use_mock == "true"
    try:
        if args.mode == "fetch":
            result = fetch_pre_market(base_url=args.base_url, use_mock=use_mock)
        else:
            if not args.report_id:
                raise RuntimeError("missing --report-id for mode=writeback")
            if not args.final_text_file:
                raise RuntimeError("missing --final-text-file for mode=writeback")
            final_text = Path(args.final_text_file).read_text(encoding="utf-8")
            result = writeback_final_text(
                base_url=args.base_url,
                report_id=args.report_id,
                final_text=final_text,
            )

        try:
            _append_log(
                log_path=log_path,
                entry={
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "mode": args.mode,
                    "ok": True,
                    "base_url": args.base_url,
                    "use_mock": use_mock,
                    **result,
                },
            )
        except Exception as log_exc:  # noqa: BLE001
            print(f"pre_market log write failed: {log_exc}", file=sys.stderr)

        if args.output == "json":
            print(json.dumps(result, ensure_ascii=False))
        else:
            if args.mode == "fetch":
                print(
                    json.dumps(
                        {
                            "report_id": result["report_id"],
                            "trade_date": result["trade_date"],
                            "summary_data": result["summary_data"],
                            "warnings": result["warnings"],
                        },
                        ensure_ascii=False,
                    )
                )
            else:
                print(f"writeback_success: {result['report_id']}")
        return 0
    except Exception as exc:  # noqa: BLE001
        try:
            _append_log(
                log_path=log_path,
                entry={
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "mode": args.mode,
                    "ok": False,
                    "base_url": args.base_url,
                    "use_mock": use_mock,
                    "error": str(exc),
                },
            )
        except Exception:  # noqa: BLE001
            pass
        print(f"pre_market {args.mode} 执行失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
