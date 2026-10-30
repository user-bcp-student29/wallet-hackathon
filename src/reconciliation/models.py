from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class TransactionRecord:
    transaction_id: str
    idempotency_key: str
    source: str
    external_reference: str
    amount_minor: int
    currency: str
    status: str
    created_at: str
    account: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReconciliationResult:
    transaction_id: str
    wallet_status: str | None
    provider_status: str | None
    ledger_status: str | None
    wallet_amount_minor: int | None
    provider_amount_minor: int | None
    ledger_amount_minor: int | None
    reconciliation_status: str
    difference_type: str | None
    difference_types: tuple[str, ...]
    severity: str
    recommended_action: str
    requires_human_review: bool
    guardrail_result: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["difference_types"] = list(self.difference_types)
        return result
