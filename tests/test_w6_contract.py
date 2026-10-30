from __future__ import annotations

import json
import importlib.util
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from app import create_server  # noqa: E402
from reconciliation.human_reviews import HumanReviewStore  # noqa: E402
from reconciliation.service import ReconciliationService  # noqa: E402
from reconciliation.w6_group import LedgerEntry, W6PaymentGroup  # noqa: E402


class W6ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.group = W6PaymentGroup()
        service = ReconciliationService(ROOT / "fixtures", Path(self.temp_dir.name))
        review_store = HumanReviewStore(Path(self.temp_dir.name) / "reviews.sqlite3")
        self.server: ThreadingHTTPServer = create_server(
            service,
            self.group,
            port=0,
            review_store=review_store,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> tuple[int, object]:
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        request = Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            response = urlopen(request, timeout=15)
        except HTTPError as error:
            response = error
        with response:
            body = response.read()
            return response.status, json.loads(body) if body else None

    def test_seeded_payment_matches_and_get_endpoints_match_contract(self) -> None:
        status, result = self.request("POST", "/reconciliations")
        self.assertEqual(status, 200)
        self.assertEqual(result, {"status": "MATCHED", "differences": []})

        status, settlements = self.request("GET", "/settlements")
        self.assertEqual(status, 200)
        self.assertEqual(
            settlements,
            [{"id": "PAY-1500", "amount": 1500, "status": "CONFIRMED"}],
        )
        self.assertEqual(set(settlements[0]), {"id", "amount", "status"})

        status, ledger = self.request("GET", "/ledger")
        self.assertEqual(status, 200)
        self.assertEqual(len([row for row in ledger if row["operation"] == "FUNDING"]), 2)
        self.assertTrue(
            all(set(row) == {"id", "operation", "kind", "account", "amount"} for row in ledger)
        )

        status, incidents = self.request("GET", "/reconciliations/incidents")
        self.assertEqual(status, 200)
        self.assertEqual(incidents, [])

    def test_openapi_documents_w6_api_and_control_schema(self) -> None:
        status, openapi = self.request("GET", "/openapi.json")
        self.assertEqual(status, 200)
        paths = openapi["paths"]
        for path in (
            "/settlements",
            "/ledger",
            "/reconciliations/incidents",
            "/reconciliations",
            "/control/settlements",
            "/agent/analysis",
            "/reconciliation/reviews",
            "/reconciliations/incidents/{incident_id}/reviews",
            "/wallet/payments",
        ):
            self.assertIn(path, paths)
        control_schema = openapi["components"]["schemas"]["SettlementControl"]
        self.assertIn(
            "CALLBACK_UNDELIVERED",
            control_schema["properties"]["mode"]["enum"],
        )
        review_schema = openapi["components"]["schemas"]["HumanReviewRequest"]
        self.assertEqual(
            review_schema["properties"]["decision"]["enum"],
            ["CONFIRM_FINDING", "DISPUTE_FINDING"],
        )

    def test_agent_analysis_is_read_only_or_reports_missing_framework(self) -> None:
        before = (self.group.get_ledger(), self.group.get_incidents())
        status, result = self.request("GET", "/agent/analysis")
        self.assertEqual((self.group.get_ledger(), self.group.get_incidents()), before)
        if importlib.util.find_spec("langgraph") is None:
            self.assertEqual(status, 503)
            self.assertIn("LangGraph is not installed", result["error"])
        else:
            self.assertEqual(status, 200)
            self.assertEqual(result["workflow"], "LangGraph")
            self.assertTrue(result["guardrail"]["passed"])

    def test_amount_mismatch_reuses_incident_and_clear_resolves_it(self) -> None:
        ledger_before = self.group.get_ledger()
        settlements_before = self.group.get_settlements()
        status, control = self.request(
            "POST",
            "/control/settlements",
            {"paymentId": "PAY-1500", "mode": "AMOUNT", "amountCents": 1600},
        )
        self.assertEqual(status, 200)
        self.assertEqual(self.group.get_ledger(), ledger_before)
        self.assertEqual(self.group.payments["PAY-1500"].amount_cents, 1500)
        self.assertEqual(self.group.get_settlements()[0]["amount"], 1600)

        status, first = self.request("POST", "/reconciliations")
        self.assertEqual(status, 200)
        self.assertEqual(first["status"], "DIFFERENCES")
        self.assertEqual(first["differences"][0]["reason"], "AMOUNT_MISMATCH")
        incident_id = first["differences"][0]["id"]

        _, second = self.request("POST", "/reconciliations")
        self.assertEqual(second["differences"][0]["id"], incident_id)
        self.assertEqual(len(self.group.get_incidents()), 1)

        self.request(
            "POST", "/control/settlements", {"paymentId": "PAY-1500", "mode": "CLEAR"}
        )
        status, resolved = self.request("POST", "/reconciliations")
        self.assertEqual(status, 200)
        self.assertEqual(resolved, {"status": "MATCHED", "differences": []})
        status, incidents = self.request("GET", "/reconciliations/incidents")
        self.assertEqual(status, 200)
        self.assertEqual(incidents[0]["id"], incident_id)
        self.assertEqual(incidents[0]["status"], "RESOLVED")
        self.assertEqual(self.group.get_settlements(), settlements_before)

    def test_human_reviews_are_append_only_persistent_and_do_not_move_money(self) -> None:
        self.group.control_settlement(
            {"paymentId": "PAY-1500", "mode": "AMOUNT", "amountCents": 1600}
        )
        _, reconciliation = self.request("POST", "/reconciliations")
        incident = reconciliation["differences"][0]
        ledger_before = self.group.get_ledger()
        wallet_before = self.group.get_wallet_payments()

        payload = {
            "reviewer": "Operadora Demo",
            "decision": "CONFIRM_FINDING",
            "rationale": "El reporte del proveedor no coincide con la wallet.",
        }
        status, first = self.request(
            "POST",
            f"/reconciliations/incidents/{incident['id']}/reviews",
            payload,
        )
        self.assertEqual(status, 201)
        self.assertEqual(first["incident_id"], incident["id"])
        self.assertEqual(first["decision"], "CONFIRM_FINDING")

        reopened_store = HumanReviewStore(
            Path(self.temp_dir.name) / "reviews.sqlite3"
        )
        self.assertEqual(reopened_store.list_reviews(), [first])

        status, second = self.request(
            "POST",
            f"/reconciliations/incidents/{incident['id']}/reviews",
            {
                "reviewer": "Otro revisor",
                "decision": "DISPUTE_FINDING",
                "rationale": "Necesito validar el origen del reporte.",
            },
        )
        self.assertEqual(status, 201)
        status, reviews = self.request("GET", "/reconciliation/reviews")
        self.assertEqual(status, 200)
        self.assertEqual([item["id"] for item in reviews], [second["id"], first["id"]])
        self.assertEqual(self.group.get_ledger(), ledger_before)
        self.assertEqual(self.group.get_wallet_payments(), wallet_before)

        self.request(
            "POST",
            "/control/settlements",
            {"paymentId": "PAY-1500", "mode": "CLEAR"},
        )
        self.request("POST", "/reconciliations")
        status, error = self.request(
            "POST",
            f"/reconciliations/incidents/{incident['id']}/reviews",
            payload,
        )
        self.assertEqual(status, 409)
        self.assertIn("OPEN", error["error"])

    def test_human_review_rejects_unknown_incidents_and_invalid_payloads(self) -> None:
        status, error = self.request(
            "POST",
            "/reconciliations/incidents/INC-unknown-0001/reviews",
            {
                "reviewer": "Demo",
                "decision": "APPROVE_PAYMENT",
                "rationale": "No permitido.",
            },
        )
        self.assertEqual(status, 404)

        self.group.control_settlement(
            {"paymentId": "PAY-1500", "mode": "AMOUNT", "amountCents": 1600}
        )
        _, reconciliation = self.request("POST", "/reconciliations")
        incident_id = reconciliation["differences"][0]["id"]
        status, error = self.request(
            "POST",
            f"/reconciliations/incidents/{incident_id}/reviews",
            {
                "reviewer": " ",
                "decision": "APPROVE_PAYMENT",
                "rationale": " ",
            },
        )
        self.assertEqual(status, 400)
        self.assertIn("reviewer", error["error"])
        status, error = self.request(
            "POST",
            f"/reconciliations/incidents/{incident_id}/reviews",
            {
                "reviewer": "Demo",
                "decision": "APPROVE_PAYMENT",
                "rationale": "No se debe aprobar un pago.",
            },
        )
        self.assertEqual(status, 400)
        self.assertIn("decision must be", error["error"])

    def test_incident_ids_do_not_repeat_after_group_restart(self) -> None:
        ids = []
        for _ in range(2):
            group = W6PaymentGroup()
            group.control_settlement(
                {"paymentId": "PAY-1500", "mode": "AMOUNT", "amountCents": 1600}
            )
            ids.append(group.reconcile()["differences"][0]["id"])
        self.assertNotEqual(ids[0], ids[1])

    def test_missing_duplicate_orphan_and_callback_controls(self) -> None:
        cases = [
            ({"paymentId": "PAY-1500", "mode": "MISSING"}, "MISSING_SETTLEMENT"),
            ({"paymentId": "PAY-1500", "mode": "DUPLICATE"}, "DUPLICATE_SETTLEMENT"),
            (
                {"paymentId": "PAY-ORPHAN", "mode": "ORPHAN", "amountCents": 500},
                "ORPHAN_SETTLEMENT",
            ),
        ]
        for control, reason in cases:
            with self.subTest(mode=control["mode"]):
                group = W6PaymentGroup()
                group.control_settlement(control)
                result = group.reconcile()
                self.assertEqual(result["status"], "DIFFERENCES")
                self.assertIn(reason, {item["reason"] for item in result["differences"]})

        status, pending = self.request("POST", "/payments", {"amountCents": 1500})
        self.assertEqual(status, 201)
        payment_id = pending["paymentId"]
        self.assertEqual(pending["status"], "PENDING")
        ledger_before_callback = self.group.get_ledger()
        self.request(
            "POST",
            "/control/settlements",
            {"paymentId": payment_id, "mode": "CALLBACK_UNDELIVERED"},
        )
        self.assertEqual(self.group.payments[payment_id].status, "PENDING")
        self.assertEqual(self.group.get_ledger(), ledger_before_callback)
        status, callback_difference = self.request("POST", "/reconciliations")
        self.assertEqual(status, 200)
        callback_incident = next(
            item
            for item in callback_difference["differences"]
            if item["payment_id"] == payment_id and item["reason"] == "STATUS_MISMATCH"
        )

        status, confirmed = self.request("POST", f"/payments/{payment_id}/confirm")
        self.assertEqual(status, 200)
        self.assertEqual(confirmed["status"], "CONFIRMED")
        status, fixed = self.request("POST", "/reconciliations")
        self.assertEqual(status, 200)
        self.assertEqual(fixed["status"], "MATCHED")
        status, incidents = self.request("GET", "/reconciliations/incidents")
        self.assertEqual(status, 200)
        resolved_callback = next(
            item for item in incidents if item["payment_id"] == payment_id
        )
        self.assertEqual(resolved_callback["id"], callback_incident["id"])
        self.assertEqual(resolved_callback["status"], "RESOLVED")

    def test_control_validation_and_reconciliation_body(self) -> None:
        status, error = self.request(
            "POST",
            "/control/settlements",
            {"paymentId": "PAY-1500", "mode": "AMOUNT", "amountCents": True},
        )
        self.assertEqual(status, 400)
        self.assertIn("positive integer", error["error"])
        status, error = self.request(
            "POST",
            "/control/settlements",
            {"paymentId": "PAY-1500", "mode": "UNSAFE"},
        )
        self.assertEqual(status, 400)
        self.assertIn("mode must be", error["error"])
        status, error = self.request(
            "POST",
            "/reconciliations",
            {"unexpected": True},
        )
        self.assertEqual(status, 400)
        self.assertIn("do not accept", error["error"])

    def test_orphan_ledger_entry_is_detected(self) -> None:
        self.group.ledger.append(
            LedgerEntry("LED-ORPHAN", "PAY-UNKNOWN", "DEBIT", "wallet", 500)
        )
        result = self.group.reconcile()
        self.assertIn(
            ("PAY-UNKNOWN", "ORPHAN_LEDGER_ENTRIES"),
            {(item["payment_id"], item["reason"]) for item in result["differences"]},
        )

    def test_reconciliation_endpoint_returns_429_when_rate_limited(self) -> None:
        handler = self.server.RequestHandlerClass
        handler.MAX_RECONCILIATIONS_PER_MINUTE = 1
        try:
            status, _ = self.request("POST", "/reconciliations")
            self.assertEqual(status, 200)
            status, error = self.request("POST", "/reconciliations")
            self.assertEqual(status, 429)
            self.assertIn("rate limit", error["error"])
        finally:
            with handler._rate_lock:
                handler._reconciliation_requests.clear()
            handler.MAX_RECONCILIATIONS_PER_MINUTE = 60

    def test_w2_payment_create_confirm_updates_provider_and_ledger_once(self) -> None:
        status, payment = self.request("POST", "/payments", {"amountCents": 1500})
        self.assertEqual(status, 201)
        self.assertEqual(payment["status"], "PENDING")
        payment_id = payment["paymentId"]
        status, settlements = self.request("GET", "/settlements")
        settlement = next(item for item in settlements if item["id"] == payment_id)
        self.assertEqual(settlement["status"], "PENDING")

        status, confirmed = self.request("POST", f"/payments/{payment_id}/confirm")
        self.assertEqual(status, 200)
        self.assertEqual(confirmed["status"], "CONFIRMED")
        status, ledger = self.request("GET", "/ledger")
        payment_entries = [item for item in ledger if item["operation"] == payment_id]
        self.assertEqual(len(payment_entries), 2)
        self.assertEqual(
            {(item["kind"], item["account"], item["amount"]) for item in payment_entries},
            {("DEBIT", "wallet", 1500), ("CREDIT", "clearing", 1500)},
        )
        self.request("POST", f"/payments/{payment_id}/confirm")
        self.assertEqual(
            len([item for item in self.group.get_ledger() if item["operation"] == payment_id]),
            2,
        )
        self.assertEqual(self.group.reconcile()["status"], "MATCHED")


if __name__ == "__main__":
    unittest.main()
