from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reconciliation.agent_tools import W6ReadOnlyTools  # noqa: E402
from reconciliation.agent_workflow import (  # noqa: E402
    AgentRuntimeUnavailable,
    W6AnalysisWorkflow,
)
from reconciliation.guardrails import validate_recommendation, validate_tool_name  # noqa: E402
from reconciliation.w6_group import W6PaymentGroup  # noqa: E402


class ReadOnlyToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.group = W6PaymentGroup()
        self.tools = W6ReadOnlyTools(self.group)

    def test_only_wired_read_only_tools_are_exposed(self) -> None:
        self.assertEqual(
            self.tools.names,
            [
                "get_ledger",
                "get_reconciliation_incidents",
                "get_settlements",
                "get_wallet_payments",
            ],
        )
        self.assertEqual(
            self.tools.invoke("get_wallet_payments"),
            [{"paymentId": "PAY-1500", "amountCents": 1500, "status": "CONFIRMED"}],
        )

    def test_unknown_write_tools_and_arguments_are_blocked(self) -> None:
        with self.assertRaises(PermissionError):
            self.tools.invoke("execute_payment")
        with self.assertRaises(PermissionError):
            self.tools.invoke("get_ledger", {"path": "outside-fixtures"})
        with self.assertRaises(PermissionError):
            self.tools.invoke("load_wallet_transactions")

    def test_guardrails_reject_invalid_names_and_recommendations(self) -> None:
        self.assertFalse(validate_tool_name("").passed)
        self.assertFalse(validate_tool_name(None).passed)
        self.assertFalse(validate_recommendation("").passed)
        self.assertFalse(validate_recommendation(None).passed)


@unittest.skipUnless(importlib.util.find_spec("langgraph"), "LangGraph AI environment required")
class LangGraphWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.group = W6PaymentGroup()

    def test_default_analysis_is_local_guarded_and_read_only(self) -> None:
        before = (
            self.group.get_wallet_payments(),
            self.group.get_settlements(),
            self.group.get_ledger(),
            self.group.get_incidents(),
        )
        with patch.dict(os.environ, {}, clear=True):
            result = W6AnalysisWorkflow(self.group).run()
        after = (
            self.group.get_wallet_payments(),
            self.group.get_settlements(),
            self.group.get_ledger(),
            self.group.get_incidents(),
        )

        self.assertEqual(before, after)
        self.assertEqual(result["workflow"], "LangGraph")
        self.assertEqual(result["crewai_status"], "DISABLED")
        self.assertEqual(result["execution_mode"], "deterministic_local")
        self.assertTrue(result["guardrail"]["passed"])
        self.assertEqual(result["snapshot"]["wallet_payments"], 1)

    def test_analysis_reports_existing_incidents_without_reconciling(self) -> None:
        self.group.control_settlement(
            {"paymentId": "PAY-1500", "mode": "AMOUNT", "amountCents": 1600}
        )
        self.group.reconcile()
        before = (self.group.get_ledger(), self.group.get_incidents())
        with patch.dict(os.environ, {}, clear=True):
            result = W6AnalysisWorkflow(self.group).run()

        self.assertEqual((self.group.get_ledger(), self.group.get_incidents()), before)
        self.assertEqual(result["snapshot"]["open_incidents"], 1)
        self.assertEqual(result["snapshot"]["open_incident_reasons"], ["AMOUNT_MISMATCH"])

    def test_crewai_requires_explicit_enablement_and_model(self) -> None:
        with patch.dict(os.environ, {"ENABLE_CREWAI": "true"}, clear=True):
            with self.assertRaisesRegex(
                AgentRuntimeUnavailable,
                "CREWAI_MODEL",
            ):
                W6AnalysisWorkflow(self.group).run()


if __name__ == "__main__":
    unittest.main()
