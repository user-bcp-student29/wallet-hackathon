from __future__ import annotations

from typing import Any

from .guardrails import validate_tool_name
from .w6_group import W6PaymentGroup


class W6ReadOnlyTools:
    def __init__(self, group: W6PaymentGroup) -> None:
        self._handlers = {
            "get_wallet_payments": group.get_wallet_payments,
            "get_settlements": group.get_settlements,
            "get_ledger": group.get_ledger,
            "get_reconciliation_incidents": group.get_incidents,
        }

    @property
    def names(self) -> list[str]:
        return sorted(self._handlers)

    def invoke(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        guardrail = validate_tool_name(tool_name)
        if not guardrail.passed:
            raise PermissionError(guardrail.reason)
        if arguments not in (None, {}):
            raise PermissionError("Read-only W6 tools do not accept arguments.")
        handler = self._handlers.get(tool_name)
        if handler is None:
            raise PermissionError("Tool is allowlisted but not wired to the W6 runtime.")
        return handler()
