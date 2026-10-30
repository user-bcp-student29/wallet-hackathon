from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


ALLOWED_READ_ONLY_TOOLS = {
    "get_wallet_payments",
    "get_settlements",
    "get_ledger",
    "get_reconciliation_incidents",
    "load_wallet_transactions",
    "load_provider_transactions",
    "load_ledger_entries",
    "find_transaction",
    "validate_amounts",
    "validate_status",
    "detect_duplicates",
    "generate_reconciliation_report",
}
FORBIDDEN_TOOL_ACTIONS = {
    "approve_payment",
    "delete_transaction",
    "execute_payment",
    "modify_balance",
    "modify_ledger",
    "reverse_payment",
}
ALLOWED_RECOMMENDATIONS = {
    "No action required.",
    "Wait for a final provider status and reconcile again.",
    "Verify the provider outcome before closing this operation.",
    "Review the declined operation and its ledger posting.",
    "Compare source records and request an operational review.",
    "Run POST /reconciliations to refresh the incident state.",
}
FINANCIAL_ACTION_MARKERS = {
    "adjust balance",
    "alter balance",
    "alter ledger",
    "approve the payment",
    "approve payment",
    "borrar transacción",
    "change the balance",
    "create payment",
    "delete transaction",
    "eliminar transacción",
    "execute a payment",
    "execute payment",
    "increase balance",
    "initiate a refund",
    "move money",
    "move funds",
    "modify balance",
    "modify ledger",
    "modificar saldo",
    "mover dinero",
    "reverse transaction",
    "reverse payment",
    "reversar pago",
    "send money",
    "transfer funds",
    "transfer money",
    "transferir dinero",
    "update balance",
}


@dataclass(frozen=True)
class GuardrailResult:
    passed: bool
    decision: str
    reason: str
    violations: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["violations"] = list(self.violations)
        return result


def validate_tool_name(tool_name: str) -> GuardrailResult:
    if not isinstance(tool_name, str) or not tool_name.strip():
        return GuardrailResult(
            False,
            "BLOCK",
            "Tool name must be a non-empty string.",
            ("invalid_tool_name",),
        )
    if tool_name in ALLOWED_READ_ONLY_TOOLS:
        return GuardrailResult(True, "PASS", "Read-only tool is allowed.", ())
    if tool_name in FORBIDDEN_TOOL_ACTIONS:
        return GuardrailResult(
            False,
            "BLOCK",
            "Financial or destructive tools are prohibited.",
            (tool_name,),
        )
    return GuardrailResult(False, "BLOCK", "Tool is not allowlisted.", (tool_name,))


def validate_recommendation(recommendation: str) -> GuardrailResult:
    if not isinstance(recommendation, str) or not recommendation.strip():
        return GuardrailResult(
            False,
            "BLOCK",
            "Recommendation must be a non-empty string.",
            ("invalid_recommendation",),
        )
    normalized = recommendation.casefold()
    markers = tuple(
        sorted(marker for marker in FINANCIAL_ACTION_MARKERS if marker in normalized)
    )
    if markers:
        return GuardrailResult(
            False,
            "BLOCK",
            "Recommendations cannot initiate or approve financial actions.",
            markers,
        )
    if recommendation not in ALLOWED_RECOMMENDATIONS:
        return GuardrailResult(
            False,
            "ESCALATE",
            "Recommendation is not in the deterministic allowlist.",
            ("unapproved_recommendation",),
        )
    return GuardrailResult(True, "PASS", "Recommendation is allowlisted.", ())
