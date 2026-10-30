from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Iterable

from .guardrails import validate_recommendation
from .models import ReconciliationResult, TransactionRecord


SOURCES = ("wallet", "provider", "ledger")
FIXTURE_FILES = {
    "wallet": "wallet_transactions.json",
    "provider": "provider_transactions.json",
    "ledger": "ledger_entries.json",
}
ALLOWED_STATUSES = {
    "PENDING",
    "PROCESSING",
    "TIMEOUT",
    "CONFIRMED",
    "DECLINED",
    "REVERSED",
    "POSTED",
}
TRANSACTION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
MAX_FIXTURE_BYTES = 1_000_000
MAX_RECORDS_PER_SOURCE = 10_000
MAX_REQUEST_BYTES = 16_384
MAX_AMOUNT_MINOR = 9_223_372_036_854_775_807
SECRET_PATTERN = re.compile(
    r"""(?i)(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:api[_-]?key|password|secret|access[_-]?token)["']?\s*[:=]\s*["']?\S+|sk-[A-Za-z0-9]{12,})"""
)


class InputValidationError(ValueError):
    pass


class ReconciliationService:
    def __init__(self, fixture_dir: Path, artifact_dir: Path) -> None:
        self.fixture_dir = fixture_dir.resolve()
        self.artifact_dir = artifact_dir.resolve()
        self._runs: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def create_run(self) -> dict[str, Any]:
        sources, fixture_hashes = self.load_sources()
        normalized = normalize_sources(sources)
        results = reconcile(normalized)
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        counts = Counter(result.reconciliation_status for result in results)
        run: dict[str, Any] = {
            "run_id": run_id,
            "created_at": created_at,
            "status": "COMPLETED",
            "summary": {
                "processed": len(results),
                "matched": counts["MATCHED"],
                "differences": sum(
                    result.reconciliation_status in {
                        "DIFFERENCE",
                        "HUMAN_REVIEW_REQUIRED",
                        "BLOCKED",
                    }
                    for result in results
                ),
                "pending": counts["PENDING_REVIEW"],
                "human_review": counts["HUMAN_REVIEW_REQUIRED"],
            },
            "fixture_hashes": fixture_hashes,
            "results": [result.as_dict() for result in results],
        }
        self.write_evidence(run)
        with self._lock:
            self._runs[run_id] = run
        return _json_clone(run)

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                _run_summary(run)
                for run in sorted(
                    self._runs.values(),
                    key=lambda item: item["created_at"],
                    reverse=True,
                )
            ]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            run = self._runs.get(run_id)
            return _json_clone(run) if run is not None else None

    def get_differences(self, run_id: str) -> list[dict[str, Any]] | None:
        run = self.get_run(run_id)
        if run is None:
            return None
        return [
            item
            for item in run["results"]
            if item["reconciliation_status"] != "MATCHED"
        ]

    def get_evidence(self, run_id: str) -> dict[str, Any] | None:
        run = self.get_run(run_id)
        if run is None:
            return None
        return {
            "run_id": run["run_id"],
            "created_at": run["created_at"],
            "fixture_hashes": run["fixture_hashes"],
            "summary": run["summary"],
            "result_count": len(run["results"]),
            "results": run["results"],
        }

    def load_sources(self) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
        sources: dict[str, list[dict[str, Any]]] = {}
        hashes: dict[str, str] = {}
        for source in SOURCES:
            path = (self.fixture_dir / FIXTURE_FILES[source]).resolve()
            if path.parent != self.fixture_dir:
                raise InputValidationError("fixture path escaped the configured directory")
            try:
                raw = path.read_bytes()
            except OSError as error:
                raise InputValidationError(f"could not load {source} fixture: {error}") from error
            if len(raw) > MAX_FIXTURE_BYTES:
                raise InputValidationError(f"{source} fixture exceeds {MAX_FIXTURE_BYTES} bytes")
            if SECRET_PATTERN.search(raw.decode("utf-8", errors="replace")):
                raise InputValidationError(f"{source} fixture contains a secret-like value")
            try:
                decoded = raw.decode("utf-8")
                records = json.loads(decoded, object_pairs_hook=_reject_duplicate_json_keys)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise InputValidationError(f"{source} fixture is not valid UTF-8 JSON") from error
            if not isinstance(records, list):
                raise InputValidationError(f"{source} fixture must contain a JSON array")
            if len(records) > MAX_RECORDS_PER_SOURCE:
                raise InputValidationError(
                    f"{source} fixture exceeds {MAX_RECORDS_PER_SOURCE} records"
                )
            sources[source] = records
            hashes[source] = hashlib.sha256(raw).hexdigest()
        return sources, hashes

    def write_evidence(self, run: dict[str, Any]) -> Path:
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        evidence = {
            "run_id": run["run_id"],
            "created_at": run["created_at"],
            "fixture_hashes": run["fixture_hashes"],
            "summary": run["summary"],
            "results": run["results"],
        }
        target = self.artifact_dir / f"{run['run_id']}.json"
        target.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return target


def normalize_sources(
    sources: dict[str, list[dict[str, Any]]],
) -> dict[str, list[TransactionRecord]]:
    normalized: dict[str, list[TransactionRecord]] = {}
    for source in SOURCES:
        records = sources.get(source)
        if not isinstance(records, list):
            raise InputValidationError(f"{source} source must be a list")
        converted = []
        for index, record in enumerate(records):
            converted.append(normalize_record(source, record, index))
        normalized[source] = converted
    return normalized


def normalize_record(source: str, record: Any, index: int) -> TransactionRecord:
    label = f"{source}[{index}]"
    if source not in SOURCES:
        raise InputValidationError(f"{label}: unknown source")
    if not isinstance(record, dict):
        raise InputValidationError(f"{label}: record must be a JSON object")
    required = {
        "transaction_id",
        "idempotency_key",
        "external_reference",
        "amount_minor",
        "currency",
        "status",
        "created_at",
    }
    if source == "ledger":
        required.add("account")
    missing = required - record.keys()
    extra = record.keys() - required
    if missing:
        raise InputValidationError(f"{label}: missing fields: {', '.join(sorted(missing))}")
    if extra:
        raise InputValidationError(f"{label}: unexpected fields: {', '.join(sorted(extra))}")
    for field in ("transaction_id", "idempotency_key", "external_reference"):
        value = record[field]
        if not isinstance(value, str) or not TRANSACTION_ID_PATTERN.fullmatch(value):
            raise InputValidationError(f"{label}: {field} has an invalid format")
    amount = record["amount_minor"]
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise InputValidationError(f"{label}: amount_minor must be an integer")
    if source != "ledger" and amount < 0:
        raise InputValidationError(f"{label}: amount_minor cannot be negative for {source}")
    if source == "ledger" and amount == 0:
        raise InputValidationError(f"{label}: ledger amount_minor cannot be zero")
    if abs(amount) > MAX_AMOUNT_MINOR:
        raise InputValidationError(f"{label}: amount_minor exceeds the supported integer range")
    currency = record["currency"]
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        raise InputValidationError(f"{label}: currency must be a 3-letter uppercase code")
    status = record["status"]
    if not isinstance(status, str) or status not in ALLOWED_STATUSES:
        raise InputValidationError(f"{label}: status is not supported")
    if source == "ledger" and status != "POSTED":
        raise InputValidationError(f"{label}: ledger status must be POSTED")
    if source != "ledger" and status == "POSTED":
        raise InputValidationError(f"{label}: POSTED is reserved for ledger entries")
    created_at = record["created_at"]
    if not isinstance(created_at, str) or not _is_utc_timestamp(created_at):
        raise InputValidationError(f"{label}: created_at must be an ISO-8601 UTC timestamp")
    account: str | None = None
    if source == "ledger":
        account = record["account"]
        if not isinstance(account, str) or account not in {"wallet", "clearing"}:
            raise InputValidationError(f"{label}: ledger account must be wallet or clearing")
        if (account == "wallet" and amount > 0) or (account == "clearing" and amount < 0):
            raise InputValidationError(f"{label}: ledger account amount sign is inconsistent")
    return TransactionRecord(
        transaction_id=record["transaction_id"],
        idempotency_key=record["idempotency_key"],
        source=source,
        external_reference=record["external_reference"],
        amount_minor=amount,
        currency=currency,
        status=status,
        created_at=created_at,
        account=account,
    )


def reconcile(
    normalized: dict[str, list[TransactionRecord]],
) -> list[ReconciliationResult]:
    grouped = {
        source: _group_records(normalized.get(source, []))
        for source in SOURCES
    }
    duplicated_transactions: dict[str, set[str]] = {
        "wallet": _duplicate_idempotency_transaction_ids(normalized.get("wallet", [])),
        "provider": _duplicate_idempotency_transaction_ids(normalized.get("provider", [])),
        "ledger": set(),
    }
    transaction_ids = sorted(
        set().union(*(set(records) for records in grouped.values()))
    )
    results: list[ReconciliationResult] = []
    for transaction_id in transaction_ids:
        wallet_records = grouped["wallet"].get(transaction_id, [])
        provider_records = grouped["provider"].get(transaction_id, [])
        ledger_records = grouped["ledger"].get(transaction_id, [])
        result = _reconcile_one(
            transaction_id,
            wallet_records,
            provider_records,
            ledger_records,
            duplicated_transactions["wallet"] | duplicated_transactions["provider"],
        )
        results.append(result)
    return results


def _reconcile_one(
    transaction_id: str,
    wallet: list[TransactionRecord],
    provider: list[TransactionRecord],
    ledger: list[TransactionRecord],
    duplicated_transactions: set[str],
) -> ReconciliationResult:
    difference_types: list[str] = []
    if len(wallet) > 1 or len(provider) > 1 or transaction_id in duplicated_transactions:
        difference_types.append("DUPLICATE")
    if not wallet:
        difference_types.append("MISSING_IN_WALLET")
    if not provider:
        difference_types.append("MISSING_IN_PROVIDER")
    if not ledger:
        difference_types.append("MISSING_IN_LEDGER")

    wallet_record = wallet[0] if wallet else None
    provider_record = provider[0] if provider else None
    if wallet_record and provider_record:
        if wallet_record.currency != provider_record.currency:
            difference_types.append("CURRENCY_MISMATCH")
        if wallet_record.amount_minor != provider_record.amount_minor:
            difference_types.append("AMOUNT_MISMATCH")
        if wallet_record.status != provider_record.status:
            difference_types.append("STATUS_MISMATCH")
    if wallet_record and ledger:
        if sum(record.amount_minor for record in ledger) != 0:
            difference_types.append("LEDGER_IMBALANCE")
        ledger_currency = {record.currency for record in ledger}
        if ledger_currency != {wallet_record.currency}:
            difference_types.append("CURRENCY_MISMATCH")
        ledger_wallet_amount = sum(
            -record.amount_minor for record in ledger if record.account == "wallet"
        )
        if ledger_wallet_amount != wallet_record.amount_minor:
            difference_types.append("AMOUNT_MISMATCH")

    statuses = {
        record.status for record in [*wallet, *provider, *ledger]
    }
    if "TIMEOUT" in statuses:
        difference_types.append("TIMEOUT")
    if "PENDING" in statuses or "PROCESSING" in statuses:
        difference_types.append("PENDING")
    if "DECLINED" in statuses:
        difference_types.append("DECLINED")
    difference_types = list(dict.fromkeys(difference_types))

    if not difference_types:
        reconciliation_status = "MATCHED"
        severity = "NONE"
        action = "No action required."
        review_required = False
    elif "TIMEOUT" in difference_types:
        reconciliation_status = "HUMAN_REVIEW_REQUIRED"
        severity = "HIGH"
        action = "Verify the provider outcome before closing this operation."
        review_required = True
    elif (
        "DECLINED" in difference_types and ledger
    ) or any(
        reason in difference_types
        for reason in ("STATUS_MISMATCH", "DUPLICATE", "LEDGER_IMBALANCE")
    ):
        reconciliation_status = "HUMAN_REVIEW_REQUIRED"
        severity = (
            "CRITICAL"
            if "DECLINED" in difference_types and ledger
            else "HIGH"
        )
        action = "Compare source records and request an operational review."
        review_required = True
    elif "PENDING" in difference_types and not any(
        item in difference_types
        for item in ("DUPLICATE", "AMOUNT_MISMATCH", "STATUS_MISMATCH")
    ):
        reconciliation_status = "PENDING_REVIEW"
        severity = "LOW"
        action = "Wait for a final provider status and reconcile again."
        review_required = False
    else:
        reconciliation_status = "DIFFERENCE"
        severity = "HIGH" if "DUPLICATE" in difference_types else "MEDIUM"
        action = "Compare source records and request an operational review."
        review_required = severity in {"HIGH", "CRITICAL"}

    guardrail_result = validate_recommendation(action)
    if not guardrail_result.passed:
        reconciliation_status = "HUMAN_REVIEW_REQUIRED"
        severity = "HIGH"
        review_required = True
        action = "Compare source records and request an operational review."

    return ReconciliationResult(
        transaction_id=transaction_id,
        wallet_status=wallet_record.status if wallet_record else None,
        provider_status=provider_record.status if provider_record else None,
        ledger_status="POSTED" if ledger else None,
        wallet_amount_minor=wallet_record.amount_minor if wallet_record else None,
        provider_amount_minor=provider_record.amount_minor if provider_record else None,
        ledger_amount_minor=(
            sum(-record.amount_minor for record in ledger if record.account == "wallet")
            if ledger
            else None
        ),
        reconciliation_status=reconciliation_status,
        difference_type=difference_types[0] if difference_types else None,
        difference_types=tuple(difference_types),
        severity=severity,
        recommended_action=action,
        requires_human_review=review_required,
        guardrail_result=guardrail_result.as_dict(),
    )


def _group_records(
    records: Iterable[TransactionRecord],
) -> dict[str, list[TransactionRecord]]:
    grouped: dict[str, list[TransactionRecord]] = defaultdict(list)
    for record in records:
        grouped[record.transaction_id].append(record)
    return grouped


def _duplicate_idempotency_transaction_ids(
    records: Iterable[TransactionRecord],
) -> set[str]:
    transaction_ids_by_key: dict[str, set[str]] = defaultdict(set)
    for record in records:
        transaction_ids_by_key[record.idempotency_key].add(record.transaction_id)
    return {
        transaction_id
        for transaction_ids in transaction_ids_by_key.values()
        if len(transaction_ids) > 1
        for transaction_id in transaction_ids
    }


def _is_utc_timestamp(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed)


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _json_clone(value: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value))


def _run_summary(run: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in run.items()
        if key != "results"
    }
