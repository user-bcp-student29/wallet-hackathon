from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from app import create_server  # noqa: E402
from reconciliation.human_reviews import HumanReviewStore  # noqa: E402
from reconciliation.service import ReconciliationService  # noqa: E402
from reconciliation.w6_group import W6PaymentGroup  # noqa: E402


@unittest.skipUnless(importlib.util.find_spec("mcp"), "MCP AI environment required")
class LocalMCPServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        service = ReconciliationService(ROOT / "fixtures", Path(self.temp_dir.name))
        store = HumanReviewStore(Path(self.temp_dir.name) / "reviews.sqlite3")
        self.server: ThreadingHTTPServer = create_server(
            service,
            W6PaymentGroup(),
            port=0,
            review_store=store,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def test_stdio_mcp_exposes_only_local_read_only_queries(self) -> None:
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        port = self.server.server_address[1]
        environment = os.environ.copy()
        environment["W6_API_PORT"] = str(port)
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-u", str(ROOT / "mcp_server.py")],
            env=environment,
            cwd=ROOT,
        )

        async def exercise_server() -> None:
            async with stdio_client(parameters) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    names = {tool.name for tool in result.tools}
                    self.assertEqual(
                        names,
                        {
                            "get_wallet_payments",
                            "get_settlements",
                            "get_ledger",
                            "get_reconciliation_incidents",
                        },
                    )
                    self.assertTrue(
                        all(
                            not tool.inputSchema.get("properties")
                            for tool in result.tools
                        )
                    )
                    self.assertFalse(
                        names
                        & {
                            "execute_payment",
                            "approve_payment",
                            "modify_balance",
                            "modify_ledger",
                        }
                    )
                    wallet_result = await session.call_tool("get_wallet_payments", {})
                    wallet_payload = json.loads(wallet_result.content[0].text)
                    self.assertEqual(wallet_payload[0]["paymentId"], "PAY-1500")
                    ledger_result = await session.call_tool("get_ledger", {})
                    ledger_payload = json.loads(ledger_result.content[0].text)
                    self.assertEqual(len(ledger_payload), 4)

        asyncio.run(exercise_server())

    def test_mcp_api_port_rejects_non_local_configuration(self) -> None:
        from mcp_server import _RejectRedirects, _api_port

        with patch.dict(os.environ, {"W6_API_PORT": "invalid"}):
            with self.assertRaisesRegex(ValueError, "must be an integer"):
                _api_port()
        with patch.dict(os.environ, {"W6_API_PORT": "65536"}):
            with self.assertRaisesRegex(ValueError, "between 1 and 65535"):
                _api_port()
        self.assertIsNone(_RejectRedirects().redirect_request(None, None, 302, "", {}, ""))


if __name__ == "__main__":
    unittest.main()
