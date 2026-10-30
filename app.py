from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from reconciliation.service import (  # noqa: E402
    MAX_REQUEST_BYTES,
    InputValidationError,
    ReconciliationService,
)
from reconciliation.w6_group import W6PaymentGroup  # noqa: E402
from reconciliation.human_reviews import HumanReviewStore  # noqa: E402


OPENAPI = {
    "openapi": "3.1.0",
    "info": {
        "title": "Synthetic Wallet Reconciliation API",
        "version": "1.0.0",
        "description": "Local-only API over synthetic wallet, provider and ledger fixtures.",
    },
    "paths": {
        "/settlements": {
            "get": {
                "summary": "Get the simulated provider settlement report",
                "responses": {
                    "200": {
                        "description": "Settlement rows",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Settlement"},
                                }
                            }
                        },
                    }
                },
            }
        },
        "/ledger": {
            "get": {
                "summary": "Get group double-entry ledger rows",
                "responses": {
                    "200": {
                        "description": "Ledger rows",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/LedgerEntry"},
                                }
                            }
                        },
                    }
                },
            }
        },
        "/wallet/payments": {
            "get": {
                "summary": "Get synthetic wallet payments",
                "responses": {"200": {"description": "Wallet payments"}},
            }
        },
        "/reconciliations/incidents": {
            "get": {
                "summary": "Get open and resolved reconciliation incidents",
                "responses": {
                    "200": {
                        "description": "Reconciliation incidents",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Incident"},
                                }
                            }
                        },
                    }
                },
            }
        },
        "/reconciliation/reviews": {
            "get": {
                "summary": "Get the persistent human review audit log",
                "responses": {"200": {"description": "Human review decisions"}},
            }
        },
        "/reconciliations/incidents/{incident_id}/reviews": {
            "post": {
                "summary": "Record an append-only human review decision",
                "parameters": [
                    {
                        "name": "incident_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/HumanReviewRequest"}
                        }
                    },
                },
                "responses": {
                    "201": {"description": "Review decision persisted"},
                    "400": {"description": "Invalid review"},
                    "404": {"description": "Incident not found"},
                    "409": {"description": "Incident is no longer open"},
                },
            }
        },
        "/reconciliations": {
            "post": {
                "summary": "Reconcile all wallet payments against settlements and ledger",
                "responses": {
                    "200": {
                        "description": "MATCHED or DIFFERENCES result",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ReconciliationResponse"}
                            }
                        },
                    },
                    "400": {"description": "Invalid request"},
                    "413": {"description": "Request too large"},
                    "429": {"description": "Rate limit exceeded"},
                },
            }
        },
        "/agent/analysis": {
            "get": {
                "summary": "Run a read-only LangGraph analysis of the current W6 snapshot",
                "responses": {
                    "200": {"description": "Guarded local analysis"},
                    "502": {"description": "Agent output blocked by a guardrail"},
                    "503": {"description": "AI framework or model configuration unavailable"},
                },
            }
        },
        "/control/settlements": {
            "post": {
                "summary": "Apply a local-only provider settlement test control",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/SettlementControl"}
                        }
                    },
                },
                "responses": {
                    "200": {"description": "Control applied"},
                    "400": {"description": "Invalid control"},
                    "413": {"description": "Request too large"},
                },
            }
        },
        "/payments": {
            "post": {
                "summary": "Create a synthetic W2 wallet payment",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["amountCents"],
                                "additionalProperties": False,
                                "properties": {
                                    "amountCents": {"type": "integer", "minimum": 1}
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "201": {"description": "Pending payment"},
                    "400": {"description": "Invalid payment"},
                    "413": {"description": "Request too large"},
                },
            }
        },
        "/payments/{payment_id}/confirm": {
            "post": {
                "summary": "Confirm a synthetic W2 wallet payment",
                "parameters": [
                    {
                        "name": "payment_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {
                    "200": {"description": "Confirmed payment"},
                    "400": {"description": "Payment cannot be confirmed"},
                    "404": {"description": "Payment not found"},
                },
            }
        },
        "/reconciliation/runs": {
            "post": {
                "summary": "Create a reconciliation run from bounded local fixtures",
                "responses": {
                    "201": {"description": "Run completed"},
                    "400": {"description": "Invalid input"},
                    "413": {"description": "Request too large"},
                },
            },
            "get": {
                "summary": "List in-memory reconciliation runs",
                "responses": {"200": {"description": "Run summaries"}},
            },
        },
        "/reconciliation/runs/{run_id}": {
            "get": {
                "summary": "Get a reconciliation run and its results",
                "parameters": [
                    {
                        "name": "run_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {
                    "200": {"description": "Run detail"},
                    "404": {"description": "Run not found"},
                },
            }
        },
        "/reconciliation/runs/{run_id}/differences": {
            "get": {
                "summary": "Get non-matched results",
                "parameters": [
                    {
                        "name": "run_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {
                    "200": {"description": "Non-matched reconciliation results"},
                    "404": {"description": "Run not found"},
                },
            }
        },
        "/reconciliation/runs/{run_id}/evidence": {
            "get": {
                "summary": "Get run evidence and fixture hashes",
                "parameters": [
                    {
                        "name": "run_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {
                    "200": {"description": "Run evidence"},
                    "404": {"description": "Run not found"},
                },
            }
        },
    },
    "components": {
        "schemas": {
            "Settlement": {
                "type": "object",
                "required": ["id", "amount", "status"],
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "amount": {"type": "integer"},
                    "status": {"type": "string"},
                },
            },
            "LedgerEntry": {
                "type": "object",
                "required": ["id", "operation", "kind", "account", "amount"],
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "operation": {"type": "string"},
                    "kind": {"type": "string", "enum": ["DEBIT", "CREDIT"]},
                    "account": {"type": "string", "enum": ["wallet", "clearing"]},
                    "amount": {"type": "integer", "minimum": 1},
                },
            },
            "Incident": {
                "type": "object",
                "required": ["id", "payment_id", "reason", "status"],
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "payment_id": {"type": "string"},
                    "reason": {"type": "string"},
                    "status": {"type": "string", "enum": ["OPEN", "RESOLVED"]},
                },
            },
            "HumanReviewRequest": {
                "type": "object",
                "required": ["reviewer", "decision", "rationale"],
                "additionalProperties": False,
                "properties": {
                    "reviewer": {"type": "string", "minLength": 1, "maxLength": 80},
                    "decision": {
                        "type": "string",
                        "enum": ["CONFIRM_FINDING", "DISPUTE_FINDING"],
                    },
                    "rationale": {"type": "string", "minLength": 1, "maxLength": 1000},
                },
            },
            "HumanReview": {
                "type": "object",
                "required": [
                    "id",
                    "incident_id",
                    "payment_id",
                    "reason",
                    "reviewer",
                    "decision",
                    "rationale",
                    "created_at",
                ],
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "incident_id": {"type": "string"},
                    "payment_id": {"type": "string"},
                    "reason": {"type": "string"},
                    "reviewer": {"type": "string"},
                    "decision": {
                        "type": "string",
                        "enum": ["CONFIRM_FINDING", "DISPUTE_FINDING"],
                    },
                    "rationale": {"type": "string"},
                    "created_at": {"type": "string", "format": "date-time"},
                },
            },
            "ReconciliationResponse": {
                "type": "object",
                "required": ["status", "differences"],
                "additionalProperties": False,
                "properties": {
                    "status": {"type": "string", "enum": ["MATCHED", "DIFFERENCES"]},
                    "differences": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/Incident"},
                    },
                },
            },
            "SettlementControl": {
                "type": "object",
                "required": ["paymentId", "mode"],
                "additionalProperties": False,
                "properties": {
                    "paymentId": {"type": "string", "minLength": 1},
                    "mode": {
                        "type": "string",
                        "enum": [
                            "AMOUNT",
                            "MISSING",
                            "DUPLICATE",
                            "ORPHAN",
                            "CALLBACK_UNDELIVERED",
                            "CLEAR",
                        ],
                    },
                    "amountCents": {"type": "integer", "minimum": 1},
                },
            },
        }
    },
}


class ReconciliationRequestHandler(BaseHTTPRequestHandler):
    service: ReconciliationService
    w6_group: W6PaymentGroup
    review_store: HumanReviewStore
    _review_lock = Lock()
    _rate_lock = Lock()
    _reconciliation_requests: dict[str, deque[float]] = {}
    MAX_RECONCILIATIONS_PER_MINUTE = 60

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/settlements":
            self._send_json(200, self.w6_group.get_settlements())
            return
        if path == "/ledger":
            self._send_json(200, self.w6_group.get_ledger())
            return
        if path == "/wallet/payments":
            self._send_json(200, self.w6_group.get_wallet_payments())
            return
        if path == "/reconciliations/incidents":
            self._send_json(200, self.w6_group.get_incidents())
            return
        if path == "/reconciliation/reviews":
            try:
                reviews = self.review_store.list_reviews()
            except sqlite3.Error as error:
                self.log_error("human review storage failed: %s", error)
                self._send_json(500, {"error": "human review storage is unavailable"})
                return
            self._send_json(200, reviews)
            return
        if path == "/agent/analysis":
            from reconciliation.agent_workflow import (
                AgentRuntimeUnavailable,
                AgentWorkflowError,
                W6AnalysisWorkflow,
            )

            try:
                result = W6AnalysisWorkflow(self.w6_group).run()
            except AgentRuntimeUnavailable as error:
                self._send_json(503, {"error": str(error)})
                return
            except (AgentWorkflowError, PermissionError) as error:
                self._send_json(502, {"error": str(error)})
                return
            self._send_json(200, result)
            return
        if path == "/openapi.json":
            self._send_json(200, OPENAPI)
            return
        if path == "/":
            self._send_file(ROOT / "index.html", "text/html; charset=utf-8")
            return
        if path == "/reconciliation/runs":
            self._send_json(200, {"runs": self.service.list_runs()})
            return
        if not path.startswith("/reconciliation/runs/"):
            self._send_json(404, {"error": "not found"})
            return

        parts = path.strip("/").split("/")
        if len(parts) not in {3, 4} or not parts[2]:
            self._send_json(404, {"error": "not found"})
            return
        run_id = parts[2]
        if len(parts) == 3:
            result = self.service.get_run(run_id)
        elif parts[3] == "differences":
            result = self.service.get_differences(run_id)
        elif parts[3] == "evidence":
            result = self.service.get_evidence(run_id)
        else:
            self._send_json(404, {"error": "not found"})
            return
        if result is None:
            self._send_json(404, {"error": "run not found"})
        else:
            self._send_json(200, result)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        parts = path.strip("/").split("/")
        if (
            len(parts) == 4
            and parts[0] == "reconciliations"
            and parts[1] == "incidents"
            and parts[2]
            and parts[3] == "reviews"
        ):
            try:
                payload = self._read_json_object()
            except OverflowError as error:
                self._send_json(413, {"error": str(error)})
                return
            except (InputValidationError, ValueError) as error:
                self._send_json(400, {"error": str(error)})
                return
            with self._review_lock:
                incident = next(
                    (
                        item
                        for item in self.w6_group.get_incidents()
                        if item["id"] == parts[2]
                    ),
                    None,
                )
                if incident is None:
                    self._send_json(404, {"error": "incident not found"})
                    return
                if incident["status"] != "OPEN":
                    self._send_json(
                        409,
                        {"error": "only OPEN incidents can be reviewed"},
                    )
                    return
                try:
                    review = self.review_store.record_review(incident, payload)
                except ValueError as error:
                    self._send_json(400, {"error": str(error)})
                    return
                except sqlite3.Error as error:
                    self.log_error("human review persistence failed: %s", error)
                    self._send_json(
                        500,
                        {"error": "human review could not be persisted"},
                    )
                    return
            self._send_json(201, review)
            return

        if path == "/reconciliations":
            if not self._allow_reconciliation_request():
                self._send_json(429, {"error": "reconciliation rate limit exceeded"})
                return
            try:
                self._validate_empty_or_empty_object_body()
                with self._review_lock:
                    result = self.w6_group.reconcile()
            except OverflowError as error:
                self._send_json(413, {"error": str(error)})
                return
            except (InputValidationError, ValueError) as error:
                self._send_json(400, {"error": str(error)})
                return
            self._send_json(200, result)
            return

        if path == "/control/settlements":
            try:
                payload = self._read_json_object()
                result = self.w6_group.control_settlement(payload)
            except OverflowError as error:
                self._send_json(413, {"error": str(error)})
                return
            except (InputValidationError, ValueError) as error:
                self._send_json(400, {"error": str(error)})
                return
            self._send_json(200, result)
            return

        if path == "/payments":
            try:
                payload = self._read_json_object()
                result = self.w6_group.create_payment(payload)
            except OverflowError as error:
                self._send_json(413, {"error": str(error)})
                return
            except (InputValidationError, ValueError) as error:
                self._send_json(400, {"error": str(error)})
                return
            self._send_json(201, result)
            return

        if path.startswith("/payments/") and path.endswith("/confirm"):
            payment_id = path.removeprefix("/payments/").removesuffix("/confirm").strip("/")
            if not payment_id or "/" in payment_id:
                self._send_json(404, {"error": "payment not found"})
                return
            try:
                result = self.w6_group.confirm_payment(payment_id)
            except KeyError as error:
                self._send_json(404, {"error": str(error).strip("'")})
                return
            except ValueError as error:
                self._send_json(400, {"error": str(error)})
                return
            self._send_json(200, result)
            return

        if path != "/reconciliation/runs":
            self._send_json(404, {"error": "not found"})
            return
        try:
            self._validate_empty_or_empty_object_body()
            run = self.service.create_run()
        except OverflowError as error:
            self._send_json(413, {"error": str(error)})
            return
        except (InputValidationError, ValueError) as error:
            self._send_json(400, {"error": str(error)})
            return
        except OSError as error:
            self._send_json(500, {"error": f"could not write run evidence: {error}"})
            return
        self._send_json(201, run)

    def _allow_reconciliation_request(self) -> bool:
        now = time.monotonic()
        client = self.client_address[0]
        with self._rate_lock:
            requests = self._reconciliation_requests.setdefault(client, deque())
            while requests and now - requests[0] >= 60:
                requests.popleft()
            if len(requests) >= self.MAX_RECONCILIATIONS_PER_MINUTE:
                return False
            requests.append(now)
            return True

    def _validate_empty_or_empty_object_body(self) -> None:
        self._read_json_object(allow_empty=True)

    def _read_json_object(self, *, allow_empty: bool = False) -> dict[str, Any]:
        value = self.headers.get("Content-Length")
        if value is None:
            if allow_empty:
                return {}
            raise InputValidationError("request body must be a JSON object")
        try:
            length = int(value)
        except ValueError as error:
            raise InputValidationError("Content-Length must be an integer") from error
        if length < 0:
            raise InputValidationError("Content-Length cannot be negative")
        if length > MAX_REQUEST_BYTES:
            raise OverflowError(f"request body exceeds {MAX_REQUEST_BYTES} bytes")
        if length == 0:
            if allow_empty:
                return {}
            raise InputValidationError("request body must be a JSON object")
        raw_body = self.rfile.read(length)
        try:
            payload = json.loads(raw_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InputValidationError("request body must be valid JSON") from error
        if payload != {}:
            if allow_empty:
                raise InputValidationError("reconciliation endpoints do not accept a request body")
        if not isinstance(payload, dict):
            raise InputValidationError("request body must be a JSON object")
        return payload

    def _send_file(self, path: Path, content_type: str) -> None:
        try:
            body = path.read_bytes()
        except OSError as error:
            self._send_json(500, {"error": f"could not read dashboard: {error}"})
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format_string % args}")


def create_server(
    service: ReconciliationService | None = None,
    w6_group: W6PaymentGroup | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    review_store: HumanReviewStore | None = None,
) -> ThreadingHTTPServer:
    if host != "127.0.0.1":
        raise ValueError("the demo server must bind to 127.0.0.1")
    if service is None:
        service = ReconciliationService(ROOT / "fixtures", ROOT / "artifacts")
    if review_store is None:
        review_store = HumanReviewStore(ROOT / "artifacts" / "human_reviews.sqlite3")
    handler = type(
        "ConfiguredReconciliationRequestHandler",
        (ReconciliationRequestHandler,),
        {
            "service": service,
            "w6_group": w6_group or W6PaymentGroup(),
            "review_store": review_store,
            "_review_lock": Lock(),
            "_rate_lock": Lock(),
            "_reconciliation_requests": {},
        },
    )
    return ThreadingHTTPServer((host, port), handler)


def main() -> None:
    host = "127.0.0.1"
    port = int(os.environ.get("PORT", "8000"))
    server = create_server(host=host, port=port)
    print(f"W6 reconciliation API: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping W6 reconciliation API")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
