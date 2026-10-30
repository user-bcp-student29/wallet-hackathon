from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any
from uuid import uuid4

from .service import MAX_AMOUNT_MINOR


@dataclass
class WalletPayment:
    payment_id: str
    amount_cents: int
    status: str


@dataclass(frozen=True)
class Settlement:
    payment_id: str
    amount: int
    status: str

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.payment_id, "amount": self.amount, "status": self.status}


@dataclass(frozen=True)
class LedgerEntry:
    entry_id: str
    operation: str
    kind: str
    account: str
    amount: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.entry_id,
            "operation": self.operation,
            "kind": self.kind,
            "account": self.account,
            "amount": self.amount,
        }


class W6PaymentGroup:
    def __init__(self) -> None:
        self.payments: dict[str, WalletPayment] = {
            "PAY-1500": WalletPayment("PAY-1500", 1500, "CONFIRMED")
        }
        self.ledger: list[LedgerEntry] = [
            LedgerEntry("LED-001", "FUNDING", "DEBIT", "clearing", 50000),
            LedgerEntry("LED-002", "FUNDING", "CREDIT", "wallet", 50000),
            LedgerEntry("LED-003", "PAY-1500", "DEBIT", "wallet", 1500),
            LedgerEntry("LED-004", "PAY-1500", "CREDIT", "clearing", 1500),
        ]
        self._settlement_overrides: dict[str, tuple[str, int | str | None]] = {}
        self._orphan_settlements: dict[str, Settlement] = {}
        self._incidents: dict[tuple[str, str], dict[str, str]] = {}
        self._incident_namespace = uuid4().hex[:8]
        self._next_incident_number = 1
        self._next_payment_number = 1501
        self._lock = RLock()

    def create_payment(self, payload: dict[str, Any]) -> dict[str, Any]:
        if set(payload) != {"amountCents"}:
            raise ValueError("payment body must contain only amountCents")
        amount = _positive_integer(payload.get("amountCents"), "amountCents")
        with self._lock:
            payment_id = f"PAY-{self._next_payment_number}"
            self._next_payment_number += 1
            payment = WalletPayment(payment_id, amount, "PENDING")
            self.payments[payment_id] = payment
            return _payment_json(payment)

    def confirm_payment(self, payment_id: str) -> dict[str, Any]:
        with self._lock:
            payment = self.payments.get(payment_id)
            if payment is None:
                raise KeyError(f"unknown paymentId: {payment_id}")
            if payment.status == "CONFIRMED":
                return _payment_json(payment)
            if payment.status != "PENDING":
                raise ValueError(f"payment cannot be confirmed from status {payment.status}")
            if _wallet_balance(self.ledger) < payment.amount_cents:
                raise ValueError("insufficient simulated wallet balance")

            payment.status = "CONFIRMED"
            override = self._settlement_overrides.get(payment_id)
            if override is not None and override[0] == "CALLBACK_UNDELIVERED":
                self._settlement_overrides.pop(payment_id, None)
            self._append_payment_ledger(payment)
            return _payment_json(payment)

    def get_settlements(self) -> list[dict[str, Any]]:
        with self._lock:
            results: list[Settlement] = []
            for payment in self.payments.values():
                override = self._settlement_overrides.get(payment.payment_id)
                if override is not None and override[0] == "MISSING":
                    continue
                amount = payment.amount_cents
                status = payment.status
                if override is not None and override[0] == "AMOUNT":
                    amount = int(override[1])
                elif override is not None and override[0] == "DUPLICATE":
                    results.append(
                        Settlement(payment.payment_id, amount, status)
                    )
                elif override is not None and override[0] == "CALLBACK_UNDELIVERED":
                    status = "CONFIRMED"
                results.append(Settlement(payment.payment_id, amount, status))
            results.extend(self._orphan_settlements.values())
            return [settlement.as_dict() for settlement in results]

    def get_wallet_payments(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                _payment_json(payment)
                for payment in sorted(
                    self.payments.values(),
                    key=lambda item: item.payment_id,
                )
            ]

    def get_ledger(self) -> list[dict[str, Any]]:
        with self._lock:
            return [entry.as_dict() for entry in self.ledger]

    def get_incidents(self) -> list[dict[str, str]]:
        with self._lock:
            return [
                incident.copy()
                for incident in sorted(
                    self._incidents.values(),
                        key=lambda item: item["id"],
                )
            ]

    def control_settlement(self, payload: dict[str, Any]) -> dict[str, str]:
        payment_id = payload.get("paymentId")
        mode = payload.get("mode")
        if not isinstance(payment_id, str) or not payment_id.strip():
            raise ValueError("paymentId must be a non-empty string")
        if not isinstance(mode, str):
            raise ValueError("mode must be a string")
        payment_id = payment_id.strip()
        mode = mode.upper()

        with self._lock:
            if mode == "CLEAR":
                if set(payload) != {"paymentId", "mode"}:
                    raise ValueError("CLEAR accepts only paymentId and mode")
                self._settlement_overrides.pop(payment_id, None)
                self._orphan_settlements.pop(payment_id, None)
                return {"paymentId": payment_id, "mode": "CLEAR"}

            if mode == "ORPHAN":
                if set(payload) != {"paymentId", "mode", "amountCents"}:
                    raise ValueError("ORPHAN requires paymentId, mode, and amountCents")
                if payment_id in self.payments:
                    raise ValueError("ORPHAN paymentId must not exist in the wallet")
                amount = _positive_integer(payload.get("amountCents"), "amountCents")
                self._orphan_settlements[payment_id] = Settlement(
                    payment_id, amount, "CONFIRMED"
                )
                return {"paymentId": payment_id, "mode": "ORPHAN"}

            payment = self.payments.get(payment_id)
            if payment is None:
                raise ValueError(f"unknown paymentId: {payment_id}")
            if mode == "AMOUNT":
                if set(payload) != {"paymentId", "mode", "amountCents"}:
                    raise ValueError("AMOUNT requires paymentId, mode, and amountCents")
                amount = _positive_integer(payload.get("amountCents"), "amountCents")
                self._settlement_overrides[payment_id] = ("AMOUNT", amount)
            elif mode in {"MISSING", "DUPLICATE"}:
                if set(payload) != {"paymentId", "mode"}:
                    raise ValueError(f"{mode} accepts only paymentId and mode")
                self._settlement_overrides[payment_id] = (mode, None)
            elif mode == "CALLBACK_UNDELIVERED":
                if set(payload) != {"paymentId", "mode"}:
                    raise ValueError("CALLBACK_UNDELIVERED accepts only paymentId and mode")
                if payment.status != "PENDING":
                    raise ValueError("CALLBACK_UNDELIVERED requires a PENDING wallet payment")
                self._settlement_overrides[payment_id] = (mode, None)
            else:
                raise ValueError(
                    "mode must be AMOUNT, MISSING, DUPLICATE, ORPHAN, "
                    "CALLBACK_UNDELIVERED, or CLEAR"
                )
            return {"paymentId": payment_id, "mode": mode}

    def reconcile(self) -> dict[str, Any]:
        with self._lock:
            settlements = self.get_settlements()
            grouped_settlements: dict[str, list[dict[str, Any]]] = {}
            for settlement in settlements:
                grouped_settlements.setdefault(settlement["id"], []).append(settlement)

            discovered: set[tuple[str, str]] = set()
            for payment in self.payments.values():
                payment_settlements = grouped_settlements.get(payment.payment_id, [])
                if not payment_settlements:
                    discovered.add((payment.payment_id, "MISSING_SETTLEMENT"))
                elif len(payment_settlements) > 1:
                    discovered.add((payment.payment_id, "DUPLICATE_SETTLEMENT"))
                else:
                    settlement = payment_settlements[0]
                    if settlement["amount"] != payment.amount_cents:
                        discovered.add((payment.payment_id, "AMOUNT_MISMATCH"))
                    if settlement["status"] != payment.status:
                        discovered.add((payment.payment_id, "STATUS_MISMATCH"))

                self._check_payment_ledger(payment, discovered)

            for entry in self.ledger:
                if entry.operation != "FUNDING" and entry.operation not in self.payments:
                    discovered.add((entry.operation, "ORPHAN_LEDGER_ENTRIES"))

            for payment_id in grouped_settlements.keys() - self.payments.keys():
                discovered.add((payment_id, "ORPHAN_SETTLEMENT"))

            expected_balance = _expected_wallet_balance(self.payments.values())
            actual_balance = _wallet_balance(self.ledger)
            if expected_balance != actual_balance:
                discovered.add(("GROUP", "WALLET_BALANCE_MISMATCH"))
            if _ledger_is_unbalanced(self.ledger):
                discovered.add(("GROUP", "LEDGER_BALANCE_MISMATCH"))

            for key, incident in self._incidents.items():
                if key not in discovered:
                    incident["status"] = "RESOLVED"

            differences: list[dict[str, str]] = []
            for payment_id, reason in sorted(discovered):
                key = (payment_id, reason)
                incident = self._incidents.get(key)
                if incident is None:
                    incident = {
                        "id": (
                            f"INC-{self._incident_namespace}-"
                            f"{self._next_incident_number:04d}"
                        ),
                        "payment_id": payment_id,
                        "reason": reason,
                        "status": "OPEN",
                    }
                    self._incidents[key] = incident
                    self._next_incident_number += 1
                else:
                    incident["status"] = "OPEN"
                differences.append(incident.copy())

            return {
                "status": "MATCHED" if not differences else "DIFFERENCES",
                "differences": differences,
            }

    def _append_payment_ledger(self, payment: WalletPayment) -> None:
        self.ledger.extend(
            [
                LedgerEntry(
                    f"LED-{len(self.ledger) + 1:03d}",
                    payment.payment_id,
                    "DEBIT",
                    "wallet",
                    payment.amount_cents,
                ),
                LedgerEntry(
                    f"LED-{len(self.ledger) + 2:03d}",
                    payment.payment_id,
                    "CREDIT",
                    "clearing",
                    payment.amount_cents,
                ),
            ]
        )

    def _check_payment_ledger(
        self,
        payment: WalletPayment,
        discovered: set[tuple[str, str]],
    ) -> None:
        entries = [
            entry for entry in self.ledger
            if entry.operation == payment.payment_id
        ]
        if payment.status == "CONFIRMED":
            expected = {
                ("DEBIT", "wallet", payment.amount_cents),
                ("CREDIT", "clearing", payment.amount_cents),
            }
            actual = {
                (entry.kind, entry.account, entry.amount)
                for entry in entries
            }
            if not entries:
                discovered.add((payment.payment_id, "MISSING_LEDGER_ENTRIES"))
            elif actual != expected or len(entries) != 2:
                discovered.add((payment.payment_id, "LEDGER_ENTRY_MISMATCH"))
        elif entries:
            discovered.add((payment.payment_id, "UNEXPECTED_LEDGER_ENTRIES"))


def _positive_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer in minor units")
    if value > MAX_AMOUNT_MINOR:
        raise ValueError(f"{field} exceeds the supported integer range")
    return value


def _payment_json(payment: WalletPayment) -> dict[str, Any]:
    return {
        "paymentId": payment.payment_id,
        "amountCents": payment.amount_cents,
        "status": payment.status,
    }


def _wallet_balance(ledger: list[LedgerEntry]) -> int:
    balance = 0
    for entry in ledger:
        if entry.account != "wallet":
            continue
        if entry.kind == "CREDIT":
            balance += entry.amount
        elif entry.kind == "DEBIT":
            balance -= entry.amount
    return balance


def _expected_wallet_balance(payments: Any) -> int:
    funded = 50000
    spent = sum(
        payment.amount_cents
        for payment in payments
        if payment.status == "CONFIRMED"
    )
    return funded - spent


def _ledger_is_unbalanced(ledger: list[LedgerEntry]) -> bool:
    operations: dict[str, dict[str, int]] = {}
    for entry in ledger:
        totals = operations.setdefault(entry.operation, {"DEBIT": 0, "CREDIT": 0})
        totals[entry.kind] = totals.get(entry.kind, 0) + entry.amount
    return any(totals["DEBIT"] != totals["CREDIT"] for totals in operations.values())
