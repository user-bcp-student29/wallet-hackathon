from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.request import HTTPRedirectHandler, build_opener

from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from reconciliation.guardrails import validate_tool_name


_READ_ROUTES = {
    "get_wallet_payments": "/wallet/payments",
    "get_settlements": "/settlements",
    "get_ledger": "/ledger",
    "get_reconciliation_incidents": "/reconciliations/incidents",
}


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_LOCAL_API_OPENER = build_opener(_RejectRedirects())


def _api_port() -> int:
    value = os.environ.get("W6_API_PORT", "8000")
    try:
        port = int(value)
    except ValueError as error:
        raise ValueError("W6_API_PORT must be an integer") from error
    if not 1 <= port <= 65535:
        raise ValueError("W6_API_PORT must be between 1 and 65535")
    return port


def _read_from_local_api(tool_name: str) -> str:
    guardrail = validate_tool_name(tool_name)
    if not guardrail.passed:
        raise PermissionError(guardrail.reason)
    route = _READ_ROUTES.get(tool_name)
    if route is None:
        raise PermissionError("MCP tool is not wired to a read-only API route.")
    url = f"http://127.0.0.1:{_api_port()}{route}"
    with _LOCAL_API_OPENER.open(url, timeout=5) as response:
        if response.status != 200:
            raise RuntimeError(f"Local W6 API returned HTTP {response.status}")
        payload: Any = json.loads(response.read())
    return json.dumps(payload, ensure_ascii=False)


mcp = FastMCP("W6 Reconciliation Read Only")


@mcp.tool()
def get_wallet_payments() -> str:
    """Read synthetic wallet payments from the local W6 API."""
    return _read_from_local_api("get_wallet_payments")


@mcp.tool()
def get_settlements() -> str:
    """Read provider settlement rows from the local W6 API."""
    return _read_from_local_api("get_settlements")


@mcp.tool()
def get_ledger() -> str:
    """Read accounting ledger entries from the local W6 API."""
    return _read_from_local_api("get_ledger")


@mcp.tool()
def get_reconciliation_incidents() -> str:
    """Read the latest reconciliation incident states from the local W6 API."""
    return _read_from_local_api("get_reconciliation_incidents")


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
