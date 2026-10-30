from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from app import MAX_REQUEST_BYTES, create_server  # noqa: E402
from reconciliation.human_reviews import HumanReviewStore  # noqa: E402
from reconciliation.service import ReconciliationService  # noqa: E402


class ReconciliationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.service = ReconciliationService(ROOT / "fixtures", Path(self.temp_dir.name))
        review_store = HumanReviewStore(Path(self.temp_dir.name) / "reviews.sqlite3")
        self.server: ThreadingHTTPServer = create_server(
            self.service,
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
        body: bytes | None = None,
    ) -> tuple[int, object]:
        headers = {"Content-Type": "application/json"} if body is not None else {}
        request = Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            content = response.read()
            payload: object
            if response.headers.get_content_type() == "application/json":
                payload = json.loads(content)
            else:
                payload = content
            return response.status, payload

    def test_create_list_detail_differences_evidence_and_openapi(self) -> None:
        status, run = self.request("POST", "/reconciliation/runs", b"{}")
        self.assertEqual(status, 201)
        run_id = run["run_id"]
        self.assertEqual(run["summary"]["processed"], 10)
        self.assertGreater(run["summary"]["matched"], 0)
        self.assertEqual(set(run["fixture_hashes"]), {"wallet", "provider", "ledger"})

        status, runs = self.request("GET", "/reconciliation/runs")
        self.assertEqual(status, 200)
        self.assertEqual(runs["runs"][0]["run_id"], run_id)
        self.assertNotIn("results", runs["runs"][0])

        status, detail = self.request("GET", f"/reconciliation/runs/{run_id}")
        self.assertEqual(status, 200)
        self.assertEqual(detail["run_id"], run_id)

        status, differences = self.request(
            "GET", f"/reconciliation/runs/{run_id}/differences"
        )
        self.assertEqual(status, 200)
        self.assertTrue(differences)
        self.assertTrue(all(item["reconciliation_status"] != "MATCHED" for item in differences))

        status, evidence = self.request(
            "GET", f"/reconciliation/runs/{run_id}/evidence"
        )
        self.assertEqual(status, 200)
        self.assertEqual(evidence["fixture_hashes"], run["fixture_hashes"])
        self.assertTrue(
            (Path(self.temp_dir.name) / f"{run_id}.json").exists()
        )

        status, openapi = self.request("GET", "/openapi.json")
        self.assertEqual(status, 200)
        self.assertEqual(openapi["openapi"], "3.1.0")
        self.assertIn("/reconciliation/runs/{run_id}/evidence", openapi["paths"])

    def test_unknown_run_and_route_return_404(self) -> None:
        status, payload = self.request("GET", "/reconciliation/runs/does-not-exist")
        self.assertEqual(status, 404)
        self.assertEqual(payload, {"error": "run not found"})
        status, payload = self.request("GET", "/not-a-route")
        self.assertEqual(status, 404)
        self.assertEqual(payload, {"error": "not found"})

    def test_invalid_body_and_oversized_body_are_rejected(self) -> None:
        status, payload = self.request("POST", "/reconciliation/runs", b"{bad")
        self.assertEqual(status, 400)
        self.assertIn("valid JSON", payload["error"])

        status, payload = self.request("POST", "/reconciliation/runs", b'{"source":"arbitrary"}')
        self.assertEqual(status, 400)
        self.assertIn("do not accept", payload["error"])

        host, port = self.server.server_address
        connection = HTTPConnection(host, port, timeout=3)
        try:
            connection.putrequest("POST", "/reconciliation/runs")
            connection.putheader("Content-Length", str(MAX_REQUEST_BYTES + 1))
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(response.status, 413)
            response.read()
        finally:
            connection.close()

    def test_invalid_source_fails_closed_and_does_not_create_run(self) -> None:
        self.service.fixture_dir = Path(self.temp_dir.name).resolve()
        (self.service.fixture_dir / "wallet_transactions.json").write_text(
            '[{"transaction_id":"../outside"}]', encoding="utf-8"
        )
        (self.service.fixture_dir / "provider_transactions.json").write_text("[]", encoding="utf-8")
        (self.service.fixture_dir / "ledger_entries.json").write_text("[]", encoding="utf-8")
        status, payload = self.request("POST", "/reconciliation/runs")
        self.assertEqual(status, 400)
        self.assertIn("missing fields", payload["error"])
        self.assertEqual(self.service.list_runs(), [])


if __name__ == "__main__":
    unittest.main()
