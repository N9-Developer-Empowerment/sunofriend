from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from sunofriend.workbench_catalog import build_workbench_catalog
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

    def test_restart_restores_decisions_home_and_non_default_pack_without_get_effects(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_catalog = _pack_catalog(root)
            state_dir = root / "restart-state"
            first_server = create_workbench_server(
                first_catalog,
                state_dir=state_dir,
                token="restart-old-token",
            )
            first_stem, second_stem = first_catalog["stems"]
            first_candidate = first_stem["candidates"][0]
            second_candidate = second_stem["candidates"][0]
            for request in (
                {
                    "event_type": "role_tag",
                    "stem_id": first_stem["stem_id"],
                    "role": "deep synth bass",
                },
                {
                    "event_type": "candidate_decision",
                    "stem_id": first_stem["stem_id"],
                    "candidate_id": first_candidate["candidate_id"],
                    "decision": "main",
                    "context": "full_mix",
                    "problem_tags": [],
                },
                {
                    "event_type": "candidate_decision",
                    "stem_id": second_stem["stem_id"],
                    "candidate_id": second_candidate["candidate_id"],
                    "decision": "optional",
                    "context": "full_mix",
                    "problem_tags": [],
                },
            ):
                first_server.store.append(first_catalog, request)
            first_thread = threading.Thread(
                target=first_server.serve_forever,
                daemon=True,
            )
            first_thread.start()
            try:
                status, first_project = _json_request(
                    first_server.server_port,
                    "GET",
                    "/api/project?token=restart-old-token",
                )
                self.assertEqual(status, 200)
                status, plan_response = _json_request(
                    first_server.server_port,
                    "GET",
                    "/api/garageband-pack-plan?token=restart-old-token",
                )
                self.assertEqual(status, 200)
                plan = plan_response["plan"]
                midi_items = [
                    item for item in plan["items"] if item["kind"] == "selected_midi"
                ]
                self.assertEqual(len(midi_items), 2)
                deliberately_small_basket = [midi_items[1]["item_id"]]
                status, saved_response = _json_request(
                    first_server.server_port,
                    "POST",
                    "/api/garageband-pack-basket?token=restart-old-token",
                    {
                        "plan_sha256": plan["plan_sha256"],
                        "basket_scope_sha256": plan["basket_scope_sha256"],
                        "expected_revision": 0,
                        "included_item_ids": deliberately_small_basket,
                        "source_audio_opt_in": False,
                    },
                )
                self.assertEqual(status, 200)
                saved = saved_response["basket"]
            finally:
                first_server.shutdown()
                first_server.server_close()
                first_thread.join(timeout=5)

            rebuilt_catalog = build_workbench_catalog(
                root / "Pack Song-D minor-120bpm-440hz",
                candidate_roots=[root / "candidates"],
                catalog_path=root / "catalog.json",
            )
            self.assertEqual(
                rebuilt_catalog["project_id"], first_catalog["project_id"]
            )
            self.assertEqual(
                [stem["stem_id"] for stem in rebuilt_catalog["stems"]],
                [stem["stem_id"] for stem in first_catalog["stems"]],
            )
            self.assertEqual(
                [
                    candidate["candidate_id"]
                    for stem in rebuilt_catalog["stems"]
                    for candidate in stem["candidates"]
                ],
                [
                    candidate["candidate_id"]
                    for stem in first_catalog["stems"]
                    for candidate in stem["candidates"]
                ],
            )

            second_server = create_workbench_server(
                rebuilt_catalog,
                state_dir=state_dir,
                token="restart-new-token",
            )
            second_thread = threading.Thread(
                target=second_server.serve_forever,
                daemon=True,
            )
            second_thread.start()
            try:
                before_review = second_server.store.export_review(rebuilt_catalog)
                status, forbidden = _json_request(
                    second_server.server_port,
                    "GET",
                    "/api/project?token=restart-old-token",
                )
                self.assertEqual(status, 403)
                self.assertIn("invalid workbench session token", forbidden["error"])

                status, restored = _json_request(
                    second_server.server_port,
                    "GET",
                    "/api/project?token=restart-new-token",
                )
                self.assertEqual(status, 200)
                self.assertEqual(restored["project_id"], first_project["project_id"])
                restored_first = restored["state"]["stems"][first_stem["stem_id"]]
                restored_second = restored["state"]["stems"][second_stem["stem_id"]]
                self.assertEqual(restored_first["role"], "deep synth bass")
                self.assertEqual(restored_first["main_candidate_id"], first_candidate["candidate_id"])
                self.assertEqual(
                    restored_first["candidates"][first_candidate["candidate_id"]][
                        "context"
                    ],
                    "full_mix",
                )
                self.assertEqual(
                    restored_second["candidates"][second_candidate["candidate_id"]][
                        "decision"
                    ],
                    "optional",
                )
                self.assertEqual(restored["state"]["event_count"], 3)
                home = restored["home"]
                self.assertEqual(home["counts"]["decision_recorded_stem_count"], 2)
                self.assertEqual(home["counts"]["selected_part_count"], 2)
                self.assertEqual(
                    home["counts"]["selected_needing_full_mix_count"], 0
                )
                self.assertEqual(home["next_step"]["action"], "compose-pack")
                self.assertFalse(home["temporary_state_restored"])
                self.assertEqual(
                    home["temporary_state_not_restored"],
                    [
                        "playhead",
                        "loop",
                        "mixer visibility",
                        "mute",
                        "solo",
                        "level",
                    ],
                )
                self.assertEqual(set(home["effects"].values()), {False})

                status, restored_plan_response = _json_request(
                    second_server.server_port,
                    "GET",
                    "/api/garageband-pack-plan?token=restart-new-token",
                )
                self.assertEqual(status, 200)
                restored_plan = restored_plan_response["plan"]
                restored_basket = restored_plan["basket"]
                self.assertEqual(
                    restored_plan["basket_restore_status"], "saved-current-plan"
                )
                self.assertTrue(restored_basket["saved"])
                self.assertTrue(restored_basket["plan_current"])
                for key in (
                    "revision",
                    "basket_sha256",
                    "included_item_ids",
                    "source_audio_opt_in",
                ):
                    self.assertEqual(restored_basket[key], saved[key])

                status, timeline = _json_request(
                    second_server.server_port,
                    "GET",
                    "/api/arrangement-timeline?token=restart-new-token",
                )
                self.assertEqual(status, 200)
                self.assertEqual(len(timeline["midi_lanes"]), 2)

                after_review = second_server.store.export_review(rebuilt_catalog)
                self.assertEqual(
                    after_review["current"]["event_count"],
                    before_review["current"]["event_count"],
                )
                self.assertEqual(after_review["events"], before_review["events"])
                status, final_plan_response = _json_request(
                    second_server.server_port,
                    "GET",
                    "/api/garageband-pack-plan?token=restart-new-token",
                )
                self.assertEqual(status, 200)
                self.assertEqual(
                    final_plan_response["plan"]["basket"]["revision"],
                    saved["revision"],
                )
            finally:
                second_server.shutdown()
                second_server.server_close()
                second_thread.join(timeout=5)

    def test_restart_keeps_terminal_outcome_as_no_selection_barrier(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _pack_catalog(root)
            state_dir = root / "terminal-restart-state"
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            first_server = create_workbench_server(
                catalog,
                state_dir=state_dir,
                token="terminal-old-token",
            )
            first_server.store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "decision": "main",
                    "context": "full_mix",
                    "problem_tags": [],
                },
            )
            first_server.store.append(
                catalog,
                {
                    "event_type": "stem_outcome",
                    "stem_id": stem["stem_id"],
                    "outcome": "none_usable",
                    "context": "full_mix",
                },
            )
            first_thread = threading.Thread(
                target=first_server.serve_forever,
                daemon=True,
            )
            first_thread.start()
            try:
                status, first_plan_response = _json_request(
                    first_server.server_port,
                    "GET",
                    "/api/garageband-pack-plan?token=terminal-old-token",
                )
                self.assertEqual(status, 200)
                self.assertEqual(
                    first_plan_response["plan"]["block_reasons"],
                    ["no-selected-midi"],
                )
            finally:
                first_server.shutdown()
                first_server.server_close()
                first_thread.join(timeout=5)

            rebuilt_catalog = build_workbench_catalog(
                root / "Pack Song-D minor-120bpm-440hz",
                candidate_roots=[root / "candidates"],
                catalog_path=root / "catalog.json",
            )
            second_server = create_workbench_server(
                rebuilt_catalog,
                state_dir=state_dir,
                token="terminal-new-token",
            )
            second_thread = threading.Thread(
                target=second_server.serve_forever,
                daemon=True,
            )
            second_thread.start()
            try:
                before = second_server.store.export_review(rebuilt_catalog)
                status, project = _json_request(
                    second_server.server_port,
                    "GET",
                    "/api/project?token=terminal-new-token",
                )
                self.assertEqual(status, 200)
                state = project["state"]["stems"][stem["stem_id"]]
                decision = state["candidates"][candidate["candidate_id"]]
                self.assertEqual(state["outcome"]["value"], "none_usable")
                self.assertIsNone(state["main_candidate_id"])
                self.assertEqual(decision["decision"], "main")
                self.assertFalse(decision["selection_active"])
                self.assertEqual(project["home"]["counts"]["selected_part_count"], 0)

                status, timeline = _json_request(
                    second_server.server_port,
                    "GET",
                    "/api/arrangement-timeline?token=terminal-new-token",
                )
                self.assertEqual(status, 200)
                self.assertEqual(timeline["midi_lanes"], [])
                status, plan_response = _json_request(
                    second_server.server_port,
                    "GET",
                    "/api/garageband-pack-plan?token=terminal-new-token",
                )
                self.assertEqual(status, 200)
                self.assertEqual(
                    plan_response["plan"]["block_reasons"],
                    ["no-selected-midi"],
                )
                after = second_server.store.export_review(rebuilt_catalog)
                self.assertEqual(after["events"], before["events"])
                self.assertEqual(after["current"]["event_count"], 2)
            finally:
                second_server.shutdown()
                second_server.server_close()
                second_thread.join(timeout=5)


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
