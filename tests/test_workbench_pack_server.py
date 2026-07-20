from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from sunofriend.workbench_server import create_workbench_server

from tests.test_workbench_pack_artifacts import (
    _fake_render,
    _pack_catalog,
)


class WorkbenchPackServerTests(unittest.TestCase):
    def test_plan_save_build_and_legacy_handoff_remain_separate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _pack_catalog(root)
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"test-soundfont")
            server = create_workbench_server(
                catalog,
                state_dir=root / "state",
                token="pack-token",
                soundfont_path=soundfont,
            )
            for index, stem in enumerate(catalog["stems"]):
                candidate = stem["candidates"][0]
                server.store.append(
                    catalog,
                    {
                        "event_type": "candidate_decision",
                        "stem_id": stem["stem_id"],
                        "candidate_id": candidate["candidate_id"],
                        "decision": "main" if index == 0 else "optional",
                        "context": "full_mix",
                        "problem_tags": [],
                    },
                )
            decision_count = server.store.current_state(catalog)["event_count"]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                status, plan_response = _json_request(
                    server.server_port,
                    "GET",
                    "/api/garageband-pack-plan?token=pack-token",
                )
                self.assertEqual(status, 200)
                plan = plan_response["plan"]
                self.assertEqual(
                    plan["schema"],
                    "sunofriend.workbench-garageband-pack-plan.v1",
                )
                self.assertFalse(plan["basket"]["saved"])
                self.assertEqual(plan["basket"]["revision"], 0)
                self.assertNotIn(str(root), json.dumps(plan))
                midi_item = next(
                    item for item in plan["items"] if item["kind"] == "selected_midi"
                )
                source_item = next(
                    item for item in plan["items"] if item["kind"] == "source_audio"
                )
                included = [midi_item["item_id"], source_item["item_id"]]

                status, stale = _json_request(
                    server.server_port,
                    "POST",
                    "/api/garageband-pack-basket?token=pack-token",
                    {
                        "plan_sha256": "0" * 64,
                        "basket_scope_sha256": plan["basket_scope_sha256"],
                        "expected_revision": 0,
                        "included_item_ids": included,
                        "source_audio_opt_in": True,
                    },
                )
                self.assertEqual(status, 409)
                self.assertIn("plan changed", stale["error"])

                status, invalid = _json_request(
                    server.server_port,
                    "POST",
                    "/api/garageband-pack-basket?token=pack-token",
                    {
                        "plan_sha256": plan["plan_sha256"],
                        "basket_scope_sha256": plan["basket_scope_sha256"],
                        "expected_revision": 0,
                        "included_item_ids": included,
                        "source_audio_opt_in": False,
                    },
                )
                self.assertEqual(status, 400)
                self.assertIn("source audio requires", invalid["error"])

                status, saved_response = _json_request(
                    server.server_port,
                    "POST",
                    "/api/garageband-pack-basket?token=pack-token",
                    {
                        "plan_sha256": plan["plan_sha256"],
                        "basket_scope_sha256": plan["basket_scope_sha256"],
                        "expected_revision": 0,
                        "included_item_ids": included,
                        "source_audio_opt_in": True,
                    },
                )
                self.assertEqual(status, 200, saved_response)
                basket = saved_response["basket"]
                self.assertTrue(basket["saved"])
                self.assertTrue(basket["plan_current"])
                self.assertEqual(basket["revision"], 1)

                status, conflict = _json_request(
                    server.server_port,
                    "POST",
                    "/api/garageband-pack-basket?token=pack-token",
                    {
                        "plan_sha256": plan["plan_sha256"],
                        "basket_scope_sha256": plan["basket_scope_sha256"],
                        "expected_revision": 0,
                        "included_item_ids": included,
                        "source_audio_opt_in": True,
                    },
                )
                self.assertEqual(status, 409)
                self.assertIn("revision conflict", conflict["error"])

                status, stale_build = _json_request(
                    server.server_port,
                    "POST",
                    "/api/garageband-pack?token=pack-token",
                    {
                        "plan_sha256": plan["plan_sha256"],
                        "basket_sha256": "f" * 64,
                    },
                )
                self.assertEqual(status, 409)
                self.assertIn("contents changed", stale_build["error"])

                with patch(
                    "sunofriend.workbench_artifacts.render_midi_to_wav",
                    side_effect=_fake_render,
                ) as renderer:
                    status, built = _json_request(
                        server.server_port,
                        "POST",
                        "/api/garageband-pack?token=pack-token",
                        {
                            "plan_sha256": plan["plan_sha256"],
                            "basket_sha256": basket["basket_sha256"],
                        },
                    )
                    self.assertEqual(status, 200)
                    pack = built["pack"]
                    self.assertEqual(
                        pack["schema"], "sunofriend.workbench-garageband-pack.v1"
                    )
                    self.assertTrue(pack["source_audio_included"])
                    self.assertFalse(pack["arrangement_proxy_included"])
                    self.assertIn("zip_url", pack)
                    renderer.assert_not_called()

                    status, legacy = _json_request(
                        server.server_port,
                        "POST",
                        "/api/garageband-export?token=pack-token",
                        {},
                    )
                    self.assertEqual(status, 200)
                    self.assertEqual(
                        legacy["handoff"]["schema"],
                        "sunofriend.workbench-garageband-handoff.v1",
                    )
                    self.assertFalse(legacy["handoff"]["source_audio_included"])
                    self.assertEqual(renderer.call_count, 1)

                self.assertEqual(
                    server.store.current_state(catalog)["event_count"],
                    decision_count,
                )
                self.assertEqual(
                    len(server.store.export_review(catalog)["events"]),
                    decision_count,
                )
                status, forbidden = _json_request(
                    server.server_port,
                    "GET",
                    "/api/garageband-pack-plan?token=wrong",
                )
                self.assertEqual(status, 403)
                self.assertIn("invalid workbench session token", forbidden["error"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


def _json_request(
    port: int,
    method: str,
    path: str,
    body: dict[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    payload = None if body is None else json.dumps(body)
    headers = {} if payload is None else {"Content-Type": "application/json"}
    connection.request(method, path, body=payload, headers=headers)
    response = connection.getresponse()
    status = response.status
    document = json.loads(response.read().decode("utf-8"))
    connection.close()
    return status, document


if __name__ == "__main__":
    unittest.main()
