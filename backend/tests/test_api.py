import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.workspace_context import get_workspace_root


class ApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health(self) -> None:
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["code"], 0)
        self.assertEqual(payload["data"]["status"], "up")

    def test_code_read_success(self) -> None:
        resp = self.client.post("/api/code/read", json={"path": "backend/app/main.py"})
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["code"], 0)
        self.assertIn("create_app", payload["data"]["content"])

    def test_code_read_security(self) -> None:
        resp = self.client.post(
            "/api/code/read",
            json={"path": "../../../Windows/System32/drivers/etc/hosts"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotEqual(resp.json()["code"], 0)

    def test_chat_and_replay(self) -> None:
        req = {
            "message": "请解释这段代码",
            "code_refs": [{"path": "backend/app/main.py"}],
            "model": "test-placeholder",
        }
        resp = self.client.post("/api/chat/ask", json=req)
        self.assertEqual(resp.status_code, 200)
        chunks = [line for line in resp.text.splitlines() if line.startswith("data: ")]
        self.assertGreater(len(chunks), 0)
        body = None
        for line in chunks:
            payload = line[6:]
            if '"type": "done"' in payload or '"type":"done"' in payload:
                import json

                body = json.loads(payload)["result"]
                break
        self.assertIsNotNone(body)
        body = body or {}
        self.assertTrue(len(body["answer"]) > 0)
        request_id = body["request_id"]
        self.assertIn("review", body)

        replay = self.client.get(f"/api/timeline/replay/{request_id}")
        replay_body = replay.json()["data"]
        self.assertEqual(replay_body["request_id"], request_id)
        self.assertGreater(len(replay_body["events"]), 0)

    def test_diff_preview(self) -> None:
        resp = self.client.post("/api/code/diff-preview", json={"before": "a\nb", "after": "a\nc"})
        self.assertEqual(resp.status_code, 200)
        lines = resp.json()["data"]["lines"]
        self.assertTrue(any(item["type"] == "del" for item in lines))
        self.assertTrue(any(item["type"] == "add" for item in lines))

    def test_review_snapshot_commit_and_rollback(self) -> None:
        workspace_root = get_workspace_root()
        workspace_file = workspace_root / ".review_rollback_test.py"
        workspace_file.write_text("a = 1\n", encoding="utf-8")
        try:
            snap = self.client.post(
                "/api/review/snapshot",
                json={"files": [str(workspace_file)]},
            )
            self.assertEqual(snap.status_code, 200)
            snapshot_id = snap.json()["data"]["snapshot_id"]

            workspace_file.write_text("a = 2\nb = 3\n", encoding="utf-8")
            commit = self.client.post("/api/review/commit", json={"snapshot_id": snapshot_id})
            self.assertEqual(commit.status_code, 200)
            review = commit.json()["data"]
            self.assertEqual(review["status"], "pending")
            self.assertEqual(len(review["files"]), 1)

            decision = self.client.post(
                "/api/review/decision",
                json={"review_ids": [review["review_id"]], "action": "rollback"},
            )
            self.assertEqual(decision.status_code, 200)
            self.assertIn(review["review_id"], decision.json()["data"]["review_ids"])
            self.assertEqual(workspace_file.read_text(encoding="utf-8"), "a = 1\n")
        finally:
            if workspace_file.exists():
                workspace_file.unlink()

    def test_review_snapshot_invalid_path(self) -> None:
        resp = self.client.post("/api/review/snapshot", json={"files": ["../../../bad.py"]})
        self.assertEqual(resp.status_code, 200)
        self.assertNotEqual(resp.json()["code"], 0)

    def test_review_decision_invalid_action(self) -> None:
        resp = self.client.post(
            "/api/review/decision",
            json={"review_ids": ["rev-none"], "action": "invalid"},
        )
        self.assertEqual(resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()
