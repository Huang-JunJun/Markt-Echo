from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.schemas import ExecutionStatus, ReportPayload, ReportType


class ReportStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                report_id TEXT PRIMARY KEY,
                report_type TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                summary_data TEXT NOT NULL,
                raw_data TEXT NOT NULL,
                warnings TEXT NOT NULL,
                source TEXT NOT NULL,
                final_output_text TEXT,
                execution_status TEXT NOT NULL,
                error_message TEXT
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_reports_trade_date_type
            ON reports(trade_date, report_type)
            """
        )
        self._conn.commit()

    def save_report(self, payload: ReportPayload, error_message: Optional[str] = None) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO reports(
                report_id,
                report_type,
                trade_date,
                generated_at,
                summary_data,
                raw_data,
                warnings,
                source,
                final_output_text,
                execution_status,
                error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.report_id,
                payload.report_type.value,
                payload.trade_date.isoformat(),
                payload.generated_at.isoformat(),
                json.dumps(payload.summary_data, ensure_ascii=False),
                json.dumps(payload.raw_data, ensure_ascii=False),
                json.dumps(payload.warnings, ensure_ascii=False),
                payload.source,
                None,
                payload.status.value,
                error_message,
            ),
        )
        self._conn.commit()

    def save_failed_report(
        self,
        report_id: str,
        report_type: ReportType,
        trade_date: date,
        generated_at: datetime,
        error_message: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO reports(
                report_id,
                report_type,
                trade_date,
                generated_at,
                summary_data,
                raw_data,
                warnings,
                source,
                final_output_text,
                execution_status,
                error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                report_type.value,
                trade_date.isoformat(),
                generated_at.isoformat(),
                json.dumps({}, ensure_ascii=False),
                json.dumps({}, ensure_ascii=False),
                json.dumps(["生成失败"], ensure_ascii=False),
                "internal",
                None,
                ExecutionStatus.FAILED.value,
                error_message,
            ),
        )
        self._conn.commit()

    def update_final_output(
        self,
        report_id: str,
        final_output_text: str,
        status: ExecutionStatus,
    ) -> bool:
        cursor = self._conn.execute(
            """
            UPDATE reports
            SET final_output_text = ?, execution_status = ?
            WHERE report_id = ?
            """,
            (final_output_text, status.value, report_id),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def list_today_reports(
        self,
        today: date,
        report_type: Optional[ReportType] = None,
    ) -> List[Dict[str, Any]]:
        params: List[Any] = [today.isoformat()]
        sql = """
            SELECT * FROM reports
            WHERE trade_date = ?
        """
        if report_type is not None:
            sql += " AND report_type = ?"
            params.append(report_type.value)
        sql += " ORDER BY generated_at DESC"

        rows = self._conn.execute(sql, params).fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "report_id": row["report_id"],
                    "report_type": row["report_type"],
                    "trade_date": row["trade_date"],
                    "generated_at": row["generated_at"],
                    "summary_data": json.loads(row["summary_data"]),
                    "raw_data": json.loads(row["raw_data"]),
                    "warnings": json.loads(row["warnings"]),
                    "source": row["source"],
                    "final_output_text": row["final_output_text"],
                    "execution_status": row["execution_status"],
                    "error_message": row["error_message"],
                }
            )
        return result
