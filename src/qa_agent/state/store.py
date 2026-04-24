"""
SQLite state store — tracks run history and per-requirement results.
Powers --only-failing and run comparisons.
"""
import json
import sqlite3
from pathlib import Path


_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    spec_path   TEXT NOT NULL,
    url         TEXT,
    environment TEXT,
    started_at  TEXT,
    total       INTEGER DEFAULT 0,
    passed      INTEGER DEFAULT 0,
    failed      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS results (
    run_id         TEXT NOT NULL,
    requirement_id TEXT NOT NULL,
    title          TEXT,
    status         TEXT NOT NULL,
    duration_ms    INTEGER,
    PRIMARY KEY (run_id, requirement_id),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_runs_spec ON runs(spec_path, started_at);
CREATE INDEX IF NOT EXISTS idx_results_run ON results(run_id);
"""


class StateStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def save_run(
        self,
        run_id: str,
        spec_path: str,
        url: str,
        environment: str,
        started_at: str,
        results: list[dict],
    ) -> None:
        passed = sum(1 for r in results if r.get("status") == "pass")
        failed = len(results) - passed

        self._conn.execute(
            "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?)",
            (run_id, str(spec_path), url, environment, started_at,
             len(results), passed, failed),
        )
        for r in results:
            self._conn.execute(
                "INSERT OR REPLACE INTO results VALUES (?,?,?,?,?)",
                (
                    run_id,
                    r.get("id", "unknown"),
                    r.get("title", ""),
                    r.get("status", "unknown"),
                    int(r.get("duration_s", 0) * 1000),
                ),
            )
        self._conn.commit()

    def last_run_id(self, spec_path: str) -> str | None:
        row = self._conn.execute(
            "SELECT run_id FROM runs WHERE spec_path=? ORDER BY started_at DESC LIMIT 1",
            (str(spec_path),),
        ).fetchone()
        return row["run_id"] if row else None

    def failing_ids(self, run_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT requirement_id FROM results WHERE run_id=? AND status != 'pass'",
            (run_id,),
        ).fetchall()
        return [r["requirement_id"] for r in rows]

    def get_results(self, run_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM results WHERE run_id=?", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def list_runs(self, spec_path: str | None = None) -> list[dict]:
        if spec_path:
            rows = self._conn.execute(
                "SELECT * FROM runs WHERE spec_path=? ORDER BY started_at DESC",
                (str(spec_path),),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM runs ORDER BY started_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._conn.close()
