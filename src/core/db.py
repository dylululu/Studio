"""SQLite database storage for jobs, step payloads, error logs, and token usage."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.models import JobStatus, VideoJob


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Manages SQLite persistence for the studio pipeline."""

    def __init__(self, db_path: str | Path = "data/studio.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Create tables if they do not exist."""
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS step_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    step_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_payload TEXT,
                    output_payload TEXT,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id)
                );

                CREATE TABLE IF NOT EXISTS error_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT,
                    step_name TEXT,
                    error_message TEXT NOT NULL,
                    traceback_str TEXT,
                    timestamp TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS usage_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT,
                    step_name TEXT,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_tokens INTEGER DEFAULT 0,
                    candidate_tokens INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    estimated_cost_usd REAL DEFAULT 0.0,
                    timestamp TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
                CREATE INDEX IF NOT EXISTS idx_step_logs_job ON step_logs(job_id);
                CREATE INDEX IF NOT EXISTS idx_usage_logs_job ON usage_logs(job_id);
                """
            )
            conn.commit()

    def save_job(self, job: VideoJob) -> None:
        """Insert or update a VideoJob."""
        job.mark_updated()
        now = _utc_now()
        created_at = job.timestamps.get("created_at", now)
        updated_at = job.timestamps.get("updated_at", now)
        payload = job.model_dump_json()

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO jobs (id, status, data_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    data_json = excluded.data_json,
                    updated_at = excluded.updated_at
                """,
                (job.id, job.status.value, payload, created_at, updated_at),
            )
            conn.commit()

    def get_job(self, job_id: str) -> Optional[VideoJob]:
        """Fetch a job by ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT data_json FROM jobs WHERE id = ?",
                (job_id,),
            )
            row = cursor.fetchone()
            if row:
                return VideoJob.model_validate_json(row["data_json"])
        return None

    def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        limit: int = 50,
    ) -> List[VideoJob]:
        """List recent jobs, optionally filtered by status."""
        query = "SELECT data_json FROM jobs"
        params: List[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status.value)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [VideoJob.model_validate_json(r["data_json"]) for r in rows]

    def log_step(
        self,
        job_id: str,
        step_name: str,
        status: str,
        input_payload: Any = None,
        output_payload: Any = None,
    ) -> None:
        """Record input and output payload for an orchestration step."""
        in_str = (
            json.dumps(input_payload, default=str, ensure_ascii=False)
            if input_payload is not None
            else None
        )
        out_str = (
            json.dumps(output_payload, default=str, ensure_ascii=False)
            if output_payload is not None
            else None
        )
        now = _utc_now()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO step_logs (job_id, step_name, status, input_payload, output_payload, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, step_name, status, in_str, out_str, now),
            )
            conn.commit()

    def log_error(
        self,
        job_id: Optional[str],
        step_name: Optional[str],
        error_message: str,
        traceback_str: Optional[str] = None,
    ) -> None:
        """Record an error event."""
        now = _utc_now()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO error_logs (job_id, step_name, error_message, traceback_str, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, step_name, error_message, traceback_str, now),
            )
            conn.commit()

    def record_usage(
        self,
        job_id: Optional[str],
        step_name: Optional[str],
        provider: str,
        model: str,
        prompt_tokens: int = 0,
        candidate_tokens: int = 0,
        total_tokens: int = 0,
        estimated_cost_usd: float = 0.0,
    ) -> None:
        """Record token consumption and estimated cost."""
        now = _utc_now()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO usage_logs (
                    job_id, step_name, provider, model,
                    prompt_tokens, candidate_tokens, total_tokens, estimated_cost_usd, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    step_name,
                    provider,
                    model,
                    prompt_tokens,
                    candidate_tokens,
                    total_tokens,
                    estimated_cost_usd,
                    now,
                ),
            )
            conn.commit()

    def get_job_steps(self, job_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM step_logs WHERE job_id = ? ORDER BY id ASC",
                (job_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_job_usage(self, job_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM usage_logs WHERE job_id = ? ORDER BY id ASC",
                (job_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_total_usage(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) as total_requests,
                    COALESCE(SUM(total_tokens), 0) as total_tokens,
                    COALESCE(SUM(estimated_cost_usd), 0.0) as total_cost_usd
                FROM usage_logs
                """
            ).fetchone()
            return dict(row) if row else {"total_requests": 0, "total_tokens": 0, "total_cost_usd": 0.0}
