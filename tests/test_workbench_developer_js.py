from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


DEVELOPER_PATH = Path("src/sunofriend/workbench_developer.js").resolve()


class WorkbenchDeveloperJavaScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.node = shutil.which("node")
        if not cls.node:
            raise unittest.SkipTest("Node.js is not installed")

    def run_node(self, body: str) -> dict[str, object]:
        script = f"""
const developer = require({json.dumps(str(DEVELOPER_PATH))});
{body}
"""
        result = subprocess.run(
            [self.node, "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_route_map_strips_queries_and_never_records_inspector_polling(self) -> None:
        result = self.run_node(
            """
let time = 0;
const journal = developer.createOperationJournal({now: () => time, limit: 4});
const project = journal.start('/api/project?token=do-not-record', 'GET');
time = 12.5;
project.complete({statusCode: 200});
journal.start('/api/developer-snapshot?token=secret', 'GET').complete({statusCode: 200});
journal.start('/unknown?token=secret', 'POST').complete({statusCode: 404});
console.log(JSON.stringify({
  route: developer.routePath('/api/project?token=secret#fragment'),
  descriptor: developer.routeDescriptor('/api/project?token=secret').operation,
  clipDescriptor: developer.routeDescriptor('/api/clips/clip-1?token=secret').operation,
  snapshot: journal.snapshot(),
}));
"""
        )

        self.assertEqual(result["route"], "/api/project")
        self.assertEqual(result["descriptor"], "project.load")
        self.assertEqual(result["clipDescriptor"], "clip_library.detail")
        records = result["snapshot"]["records"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["route"], "/api/project")
        self.assertEqual(records[0]["duration_ms"], 12.5)
        self.assertNotIn("secret", json.dumps(result))

    def test_operation_journal_is_bounded_and_contains_no_payloads(self) -> None:
        result = self.run_node(
            """
let time = 100;
const journal = developer.createOperationJournal({now: () => ++time, limit: 2});
for (const [path, method, status] of [
  ['/api/project', 'GET', 200],
  ['/api/events', 'POST', 201],
  ['/api/garageband-pack', 'POST', 409],
]) {
  const operation = journal.start(path, method);
  operation.complete({statusCode: status, errorClass: status === 409 ? 'conflict' : ''});
}
console.log(JSON.stringify(journal.snapshot()));
"""
        )

        self.assertEqual(result["dropped_count"], 1)
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(
            [record["operation"] for record in result["records"]],
            ["decision.append", "pack.build"],
        )
        self.assertEqual(result["records"][-1]["status"], "conflict")
        encoded = json.dumps(result)
        for forbidden in [
            "request_body",
            "response_body",
            '"headers":',
            "do-not-record",
            "secret-session-value",
        ]:
            self.assertNotIn(forbidden, encoded)

    def test_clip_reuse_read_is_non_durable_and_change_is_explicitly_durable(
        self,
    ) -> None:
        result = self.run_node(
            """
let time = 0;
const journal = developer.createOperationJournal({now: () => ++time});
const readDescriptor = developer.routeDescriptor('/api/clip-reuse-plan?token=secret');
const changeDescriptor = developer.routeDescriptor('/api/clip-reuse-action?token=secret');
const read = journal.start('/api/clip-reuse-plan?token=secret', 'GET');
read.complete({statusCode: 200});
const change = journal.start('/api/clip-reuse-action?token=secret', 'POST');
change.complete({statusCode: 201});
console.log(JSON.stringify({
  readDescriptor,
  changeDescriptor,
  snapshot: journal.snapshot(),
}));
"""
        )

        self.assertEqual(result["readDescriptor"]["operation"], "clip_reuse.read")
        self.assertFalse(result["readDescriptor"]["durableEffect"])
        self.assertEqual(
            result["changeDescriptor"]["operation"],
            "clip_reuse.change",
        )
        self.assertTrue(result["changeDescriptor"]["durableEffect"])
        records = result["snapshot"]["records"]
        self.assertEqual(
            [record["durable_effect_possible"] for record in records],
            [False, True],
        )
        self.assertIn(
            "sunofriend.workbench_reuse.WorkbenchClipReuseService.plan",
            records[0]["symbols"],
        )
        self.assertIn(
            "sunofriend.workbench_reuse.WorkbenchClipReuseService.apply",
            records[1]["symbols"],
        )
        self.assertNotIn("secret", json.dumps(result))

    def test_clip_transform_preview_is_non_durable_and_create_is_one_append(
        self,
    ) -> None:
        result = self.run_node(
            """
let time = 0;
const journal = developer.createOperationJournal({now: () => ++time});
const previewDescriptor = developer.routeDescriptor('/api/clip-transform-projection?token=secret');
const createDescriptor = developer.routeDescriptor('/api/clip-transform-action?token=secret');
const preview = journal.start('/api/clip-transform-projection?token=secret', 'POST');
preview.complete({statusCode: 200});
const create = journal.start('/api/clip-transform-action?token=secret', 'POST');
create.complete({statusCode: 201});
console.log(JSON.stringify({
  previewDescriptor,
  createDescriptor,
  snapshot: journal.snapshot(),
}));
"""
        )

        self.assertEqual(
            result["previewDescriptor"]["operation"],
            "clip_transform.preview",
        )
        self.assertFalse(result["previewDescriptor"]["durableEffect"])
        self.assertEqual(
            result["createDescriptor"]["operation"],
            "clip_transform.create",
        )
        self.assertTrue(result["createDescriptor"]["durableEffect"])
        records = result["snapshot"]["records"]
        self.assertEqual(
            [record["durable_effect_possible"] for record in records],
            [False, True],
        )
        self.assertIn(
            "sunofriend.library.ClipLibrary.append_version_if_state",
            records[1]["symbols"],
        )
        self.assertNotIn(
            "sunofriend.library.ClipLibrary.append_version_if_state",
            records[0]["symbols"],
        )
        self.assertNotIn("secret", json.dumps(result))

    def test_browser_state_is_an_explicit_non_persistent_allowlist(self) -> None:
        result = self.run_node(
            """
const state = developer.safeBrowserState({
  view: 'arrangement',
  active_stem_id: 'stem-1',
  playhead_seconds: 14.25,
  selected_midi_count: 3,
  mixer_preset: 'hybrid',
  mixer_playing: true,
  precise_stem_loop_prepared: true,
  precise_arrangement_loop_prepared: false,
  full_song_stream_prepared: true,
  token: 'must-not-escape',
  notes: 'private listening note',
  source_path: '/Users/example/private.wav',
  caches: {
    timeline_entries: 2,
    decoded_extra_stems: 1,
    mixer_tracks: 9,
    cache_keys: ['private'],
  },
});
console.log(JSON.stringify(state));
"""
        )

        self.assertEqual(result["view"], "arrangement")
        self.assertEqual(result["selected_midi_count"], 3)
        self.assertEqual(result["caches"]["mixer_tracks"], 9)
        self.assertFalse(result["persisted"])
        encoded = json.dumps(result)
        for forbidden in ["must-not-escape", "private listening note", "/Users/"]:
            self.assertNotIn(forbidden, encoded)

    def test_all_route_symbols_are_static_import_or_repo_references(self) -> None:
        result = self.run_node(
            """
const rows = Object.entries(developer.ROUTES).map(([route, descriptor]) => ({
  route,
  symbolCount: descriptor.symbols.length,
  symbolsStatic: descriptor.symbols.every(symbol =>
    symbol.startsWith('sunofriend.') || symbol.startsWith('src/sunofriend/')
  ),
}));
console.log(JSON.stringify({rows}));
"""
        )

        self.assertGreaterEqual(len(result["rows"]), 10)
        self.assertTrue(all(row["symbolCount"] for row in result["rows"]))
        self.assertTrue(all(row["symbolsStatic"] for row in result["rows"]))


if __name__ == "__main__":
    unittest.main()
