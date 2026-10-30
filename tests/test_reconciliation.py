from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reconciliation.guardrails import validate_recommendation, validate_tool_name  # noqa: E402
from reconciliation.models import TransactionRecord  # noqa: E402
from reconciliation.service import (  # noqa: E402
    InputValidationError,
    ReconciliationService,
    normalize_record,
    normalize_sources,
    reconcile,
)


def source_record(
    transaction_id: str,
    amount_minor: int,
    status: str = "CONFIRMED",
) -> dict[str, object]:
    return {
        "transaction_id": transaction_id,
        "idempotency_key": f"idem-{transaction_id.lower()}",
        "external_reference": f"ref-{transaction_id.lower()}",
        "amount_minor": amount_minor,
        "currency": "PEN",
        "status": status,
        "created_at": "2026-10-30T09:00:00Z",
    }


def normalized_sources(
    wallet: list[dict[str, object]] | None = None,
    provider: list[dict[str, object]] | None = None,
    ledger: list[dict[str, object]] | None = None,
) -> dict[str, list[TransactionRecord]]:
    return normalize_sources(
        {
            "wallet": wallet or [],
            "provider": provider or [],
            "ledger": ledger or [],
        }
    )


def ledger_pair(transaction_id: str, amount_minor: int) -> list[dict[str, object]]:
    debit = source_record(transaction_id, -amount_minor)
    debit["account"] = "wallet"
    debit["status"] = "POSTED"
    credit = source_record(transaction_id, amount_minor)
    credit["account"] = "clearing"
    credit["status"] = "POSTED"
    return [debit, credit]


class NormalizationTests(unittest.TestCase):
    def test_normalizes_required_common_record_fields(self) -> None:
        record = normalize_record("wallet", source_record("TX-1", 1550), 0)
        self.assertEqual(record.transaction_id, "TX-1")
        self.assertEqual(record.amount_minor, 1550)
        self.assertEqual(record.currency, "PEN")
        self.assertEqual(record.source, "wallet")
        self.assertIsNone(record.account)

    def test_rejects_float_amount(self) -> None:
        record = source_record("TX-FLOAT", 100)
        record["amount_minor"] = 1.5
        with self.assertRaisesRegex(InputValidationError, "must be an integer"):
            normalize_record("wallet", record, 0)

    def test_rejects_unknown_fields_and_invalid_currency(self) -> None:
        record = source_record("TX-EXTRA", 100)
        record["untrusted_path"] = ".."
        with self.assertRaisesRegex(InputValidationError, "unexpected fields"):
            normalize_record("wallet", record, 0)
        record = source_record("TX-CURRENCY", 100)
        record["currency"] = "pen"
        with self.assertRaisesRegex(InputValidationError, "uppercase code"):
            normalize_record("wallet", record, 0)

    def test_fixture_loader_blocks_secret_like_values(self) -> None:
        with TemporaryDirectory() as directory:
            fixture_dir = Path(directory)
            (fixture_dir / "wallet_transactions.json").write_text(
                '[{"access_token":"secret-value"}]', encoding="utf-8"
            )
            (fixture_dir / "provider_transactions.json").write_text("[]", encoding="utf-8")
            (fixture_dir / "ledger_entries.json").write_text("[]", encoding="utf-8")
            service = ReconciliationService(fixture_dir, fixture_dir / "artifacts")
            with self.assertRaisesRegex(InputValidationError, "secret-like"):
                service.load_sources()

    def test_fixture_loader_rejects_oversized_source(self) -> None:
        with TemporaryDirectory() as directory:
            fixture_dir = Path(directory)
            (fixture_dir / "wallet_transactions.json").write_bytes(
                b" " * 1_000_001
            )
            (fixture_dir / "provider_transactions.json").write_text("[]", encoding="utf-8")
            (fixture_dir / "ledger_entries.json").write_text("[]", encoding="utf-8")
            service = ReconciliationService(fixture_dir, fixture_dir / "artifacts")
            with self.assertRaisesRegex(InputValidationError, "exceeds 1000000 bytes"):
                service.load_sources()

    def test_fixture_loader_rejects_duplicate_json_keys(self) -> None:
        with TemporaryDirectory() as directory:
            fixture_dir = Path(directory)
            (fixture_dir / "wallet_transactions.json").write_text(
                '[{"transaction_id":"TX-1","transaction_id":"TX-2"}]',
                encoding="utf-8",
            )
            (fixture_dir / "provider_transactions.json").write_text("[]", encoding="utf-8")
            (fixture_dir / "ledger_entries.json").write_text("[]", encoding="utf-8")
            service = ReconciliationService(fixture_dir, fixture_dir / "artifacts")
            with self.assertRaisesRegex(InputValidationError, "duplicate JSON key"):
                service.load_sources()


class ReconciliationTests(unittest.TestCase):
    def result_for(self, sources: dict[str, list[TransactionRecord]], transaction_id: str) -> dict[str, object]:
        return next(item.as_dict() for item in reconcile(sources) if item.transaction_id == transaction_id)

    def test_exact_match(self) -> None:
        sources = normalized_sources(
            wallet=[source_record("TX-MATCH", 1550)],
            provider=[source_record("TX-MATCH", 1550)],
            ledger=ledger_pair("TX-MATCH", 1550),
        )
        result = self.result_for(sources, "TX-MATCH")
        self.assertEqual(result["reconciliation_status"], "MATCHED")
        self.assertEqual(result["difference_types"], [])

    def test_amount_mismatch(self) -> None:
        sources = normalized_sources(
            wallet=[source_record("TX-AMOUNT", 10000)],
            provider=[source_record("TX-AMOUNT", 9000)],
            ledger=ledger_pair("TX-AMOUNT", 10000),
        )
        result = self.result_for(sources, "TX-AMOUNT")
        self.assertIn("AMOUNT_MISMATCH", result["difference_types"])
        self.assertEqual(result["wallet_amount_minor"], 10000)
        self.assertEqual(result["provider_amount_minor"], 9000)

    def test_status_mismatch(self) -> None:
        sources = normalized_sources(
            wallet=[source_record("TX-STATUS", 1000, "CONFIRMED")],
            provider=[source_record("TX-STATUS", 1000, "DECLINED")],
            ledger=ledger_pair("TX-STATUS", 1000),
        )
        result = self.result_for(sources, "TX-STATUS")
        self.assertIn("STATUS_MISMATCH", result["difference_types"])
        self.assertEqual(result["reconciliation_status"], "HUMAN_REVIEW_REQUIRED")
        self.assertTrue(result["requires_human_review"])

    def test_missing_wallet_transaction(self) -> None:
        sources = normalized_sources(
            provider=[source_record("TX-NO-WALLET", 1000)],
            ledger=ledger_pair("TX-NO-WALLET", 1000),
        )
        result = self.result_for(sources, "TX-NO-WALLET")
        self.assertIn("MISSING_IN_WALLET", result["difference_types"])

    def test_missing_provider_transaction(self) -> None:
        sources = normalized_sources(
            wallet=[source_record("TX-NO-PROVIDER", 1000)],
            ledger=ledger_pair("TX-NO-PROVIDER", 1000),
        )
        result = self.result_for(sources, "TX-NO-PROVIDER")
        self.assertIn("MISSING_IN_PROVIDER", result["difference_types"])

    def test_missing_ledger_transaction(self) -> None:
        sources = normalized_sources(
            wallet=[source_record("TX-NO-LEDGER", 1000)],
            provider=[source_record("TX-NO-LEDGER", 1000)],
        )
        result = self.result_for(sources, "TX-NO-LEDGER")
        self.assertIn("MISSING_IN_LEDGER", result["difference_types"])

    def test_duplicate_transaction(self) -> None:
        record = source_record("TX-DUP", 1000)
        duplicate = source_record("TX-DUP", 1000)
        duplicate["external_reference"] = "another-ref"
        sources = normalized_sources(
            wallet=[record],
            provider=[record, duplicate],
            ledger=ledger_pair("TX-DUP", 1000),
        )
        result = self.result_for(sources, "TX-DUP")
        self.assertIn("DUPLICATE", result["difference_types"])
        self.assertTrue(result["requires_human_review"])

    def test_reused_idempotency_key_across_wallet_transactions_is_duplicate(self) -> None:
        first = source_record("TX-IDEM-1", 1000)
        second = source_record("TX-IDEM-2", 1000)
        second["idempotency_key"] = first["idempotency_key"]
        sources = normalized_sources(
            wallet=[first, second],
            provider=[first, second],
            ledger=ledger_pair("TX-IDEM-1", 1000) + ledger_pair("TX-IDEM-2", 1000),
        )
        by_id = {result.transaction_id: result for result in reconcile(sources)}
        self.assertIn("DUPLICATE", by_id["TX-IDEM-1"].difference_types)
        self.assertIn("DUPLICATE", by_id["TX-IDEM-2"].difference_types)

    def test_unbalanced_ledger_is_classified(self) -> None:
        ledger = ledger_pair("TX-UNBALANCED", 1000)
        ledger[1]["amount_minor"] = 900
        sources = normalized_sources(
            wallet=[source_record("TX-UNBALANCED", 1000)],
            provider=[source_record("TX-UNBALANCED", 1000)],
            ledger=ledger,
        )
        result = self.result_for(sources, "TX-UNBALANCED")
        self.assertIn("LEDGER_IMBALANCE", result["difference_types"])

    def test_pending_transaction_waits_for_final_provider_status(self) -> None:
        sources = normalized_sources(
            wallet=[source_record("TX-PENDING", 1000, "PENDING")],
            provider=[source_record("TX-PENDING", 1000, "PENDING")],
        )
        result = self.result_for(sources, "TX-PENDING")
        self.assertEqual(result["reconciliation_status"], "PENDING_REVIEW")
        self.assertIn("PENDING", result["difference_types"])

    def test_timeout_transaction_requires_human_review(self) -> None:
        sources = normalized_sources(
            wallet=[source_record("TX-TIMEOUT", 1000, "PROCESSING")],
            provider=[source_record("TX-TIMEOUT", 1000, "TIMEOUT")],
        )
        result = self.result_for(sources, "TX-TIMEOUT")
        self.assertEqual(result["reconciliation_status"], "HUMAN_REVIEW_REQUIRED")
        self.assertIn("TIMEOUT", result["difference_types"])

    def test_declined_transaction_is_classified_without_ledger_movement(self) -> None:
        sources = normalized_sources(
            wallet=[source_record("TX-DECLINED", 1000, "DECLINED")],
            provider=[source_record("TX-DECLINED", 1000, "DECLINED")],
        )
        result = self.result_for(sources, "TX-DECLINED")
        self.assertIn("DECLINED", result["difference_types"])
        self.assertEqual(result["reconciliation_status"], "DIFFERENCE")

    def test_integration_fixtures_cover_expected_scenarios(self) -> None:
        service = ReconciliationService(ROOT / "fixtures", ROOT / "artifacts")
        sources, hashes = service.load_sources()
        results = reconcile(normalize_sources(sources))
        by_id = {result.transaction_id: result for result in results}
        self.assertEqual(len(hashes), 3)
        self.assertEqual(by_id["TX-MATCH"].reconciliation_status, "MATCHED")
        self.assertIn("AMOUNT_MISMATCH", by_id["TX-AMOUNT"].difference_types)
        self.assertIn("STATUS_MISMATCH", by_id["TX-STATUS"].difference_types)
        self.assertIn("MISSING_IN_PROVIDER", by_id["TX-MISSING-PROVIDER"].difference_types)
        self.assertIn("MISSING_IN_WALLET", by_id["TX-MISSING-WALLET"].difference_types)
        self.assertIn("MISSING_IN_LEDGER", by_id["TX-MISSING-LEDGER"].difference_types)
        self.assertIn("DUPLICATE", by_id["TX-DUPLICATE"].difference_types)
        self.assertEqual(by_id["TX-PENDING"].reconciliation_status, "PENDING_REVIEW")
        self.assertIn("TIMEOUT", by_id["TX-TIMEOUT"].difference_types)
        self.assertIn("DECLINED", by_id["TX-DECLINED"].difference_types)

    def test_reconciliation_does_not_mutate_source_records_or_amounts(self) -> None:
        wallet = source_record("TX-IMMUTABLE", 1200)
        provider = source_record("TX-IMMUTABLE", 1200)
        ledger = ledger_pair("TX-IMMUTABLE", 1200)
        before = json.dumps([wallet, provider, ledger], sort_keys=True)
        reconcile(normalize_sources({"wallet": [wallet], "provider": [provider], "ledger": ledger}))
        self.assertEqual(json.dumps([wallet, provider, ledger], sort_keys=True), before)


class GuardrailTests(unittest.TestCase):
    def test_guardrail_blocks_financial_action(self) -> None:
        result = validate_tool_name("execute_payment")
        self.assertFalse(result.passed)
        self.assertEqual(result.decision, "BLOCK")

    def test_guardrail_blocks_unsafe_recommendation(self) -> None:
        result = validate_recommendation("Approve payment and move money now.")
        self.assertFalse(result.passed)
        self.assertEqual(result.decision, "BLOCK")

    def test_read_only_tool_and_allowlisted_recommendation_pass(self) -> None:
        self.assertTrue(validate_tool_name("find_transaction").passed)
        self.assertTrue(validate_recommendation("No action required.").passed)


if __name__ == "__main__":
    unittest.main()
