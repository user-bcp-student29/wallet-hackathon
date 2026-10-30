from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REVIEW_DECISIONS = {"CONFIRM_FINDING", "DISPUTE_FINDING"}
MAX_REVIEWER_LENGTH = 80
MAX_RATIONALE_LENGTH = 1000


class HumanReviewStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS human_reviews (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        incident_id TEXT NOT NULL,
                        payment_id TEXT NOT NULL,
                        incident_reason TEXT NOT NULL,
                        reviewer TEXT NOT NULL,
                        decision TEXT NOT NULL CHECK (
                            decision IN ('CONFIRM_FINDING', 'DISPUTE_FINDING')
                        ),
                        rationale TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS human_reviews_incident_id_idx
                    ON human_reviews (incident_id, id DESC)
                    """
                )

    def record_review(
        self,
        incident: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, str]:
        reviewer = _validated_text(payload.get("reviewer"), "reviewer", MAX_REVIEWER_LENGTH)
        decision = payload.get("decision")
        if not isinstance(decision, str) or decision not in REVIEW_DECISIONS:
            raise ValueError(
                "decision must be CONFIRM_FINDING or DISPUTE_FINDING"
            )
        rationale = _validated_text(
            payload.get("rationale"),
            "rationale",
            MAX_RATIONALE_LENGTH,
        )
        if set(payload) != {"reviewer", "decision", "rationale"}:
            raise ValueError(
                "review body must contain only reviewer, decision, and rationale"
            )
        created_at = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO human_reviews (
                        incident_id,
                        payment_id,
                        incident_reason,
                        reviewer,
                        decision,
                        rationale,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        incident["id"],
                        incident["payment_id"],
                        incident["reason"],
                        reviewer,
                        decision,
                        rationale,
                        created_at,
                    ),
                )
                review_number = cursor.lastrowid
        if review_number is None:
            raise RuntimeError("SQLite did not return the saved review ID")
        return {
            "id": f"HR-{review_number:08d}",
            "incident_id": incident["id"],
            "payment_id": incident["payment_id"],
            "reason": incident["reason"],
            "reviewer": reviewer,
            "decision": decision,
            "rationale": rationale,
            "created_at": created_at,
        }

    def list_reviews(self) -> list[dict[str, str]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    incident_id,
                    payment_id,
                    incident_reason,
                    reviewer,
                    decision,
                    rationale,
                    created_at
                FROM human_reviews
                ORDER BY id DESC
                """
            ).fetchall()
        return [
            {
                "id": f"HR-{row[0]:08d}",
                "incident_id": row[1],
                "payment_id": row[2],
                "reason": row[3],
                "reviewer": row[4],
                "decision": row[5],
                "rationale": row[6],
                "created_at": row[7],
            }
            for row in rows
        ]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection


def _validated_text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must not be empty")
    if len(normalized) > maximum:
        raise ValueError(f"{field} must be at most {maximum} characters")
    return normalized
