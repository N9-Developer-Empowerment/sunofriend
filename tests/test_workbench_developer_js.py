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

    def test_server_snapshot_preserves_create_durability_and_append_symbols(self) -> None:
        result = self.run_node(
            """
(async () => {
  function snapshot(operation, durableEffect, serviceSymbol) {
    const [module, symbol] = serviceSymbol.split('::');
    return {
      code_flow: {code_map: {
        service: {module, symbol},
      }},
      runtime: {recent_operations: [{
        sequence: 1,
        operation,
        label: 'server label',
        method: 'POST',
        status: 'completed',
        http_status: 201,
        duration_ms: 4.5,
        durable_effect_possible: durableEffect,
        symbols: [
          `${module}.${symbol}`,
          'sunofriend.library.ClipLibrary.append_version_if_state',
        ],
        frames: [{stage: 'result', code_step: 'service', facts: {clip_version_appended: true}}],
      }], active_operations: []},
      privacy: {}, effects: {},
    };
  }

  async function rendered(value) {
    const host = {innerHTML: '', querySelector() { return null; }};
    const inspector = developer.createInspector({api: async path => {
      if (path !== '/api/developer-snapshot') throw new Error(`unexpected ${path}`);
      return value;
    }});
    inspector.setEnabled(true);
    inspector.renderInto(host);
    await new Promise(resolve => setTimeout(resolve, 0));
    return host.innerHTML;
  }

  const correction = await rendered(snapshot(
    'clip_correction.create',
    true,
    'sunofriend.workbench_correction::WorkbenchClipCorrectionService.create',
  ));
  const transform = await rendered(snapshot(
    'clip_transform.create',
    true,
    'sunofriend.workbench_transform::WorkbenchClipTransformService.create',
  ));
  const projectedFalse = await rendered(snapshot(
    'decision.append',
    false,
    'sunofriend.workbench_store::WorkbenchStore.append',
  ));
  console.log(JSON.stringify({correction, transform, projectedFalse}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )

        for key in ("correction", "transform"):
            html = result[key]
            self.assertIn(
                "Durable effect possible:</b> yes, only through this explicit production command",
                html,
            )
            self.assertIn(
                "<code>sunofriend.library.ClipLibrary.append_version_if_state</code>",
                html,
            )
        self.assertIn(
            "sunofriend.workbench_correction.WorkbenchClipCorrectionService.create",
            result["correction"],
        )
        self.assertIn(
            "sunofriend.workbench_transform.WorkbenchClipTransformService.create",
            result["transform"],
        )
        self.assertIn(
            "Durable effect possible:</b> no",
            result["projectedFalse"],
        )
        self.assertNotIn(
            "Durable effect possible:</b> yes",
            result["projectedFalse"],
        )

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

    def test_arrangement_routes_match_the_server_operation_catalog(self) -> None:
        result = self.run_node(
            """
console.log(JSON.stringify({
  dry: developer.routeDescriptor('/api/arrangement?token=secret'),
  balanced: developer.routeDescriptor(
    '/api/balanced-arrangement?token=secret'
  ),
  master: developer.routeDescriptor('/api/listening-master?token=secret'),
}));
"""
        )

        self.assertEqual(result["dry"]["operation"], "arrangement.render")
        self.assertEqual(
            result["dry"]["label"],
            "Render or reuse the selected arrangement proxy",
        )
        self.assertEqual(
            result["balanced"]["operation"],
            "arrangement.balance",
        )
        self.assertEqual(
            result["balanced"]["label"],
            "Render or reuse the balanced MIDI-derived song interpretation",
        )
        self.assertEqual(result["master"]["operation"], "arrangement.master")
        self.assertEqual(
            result["master"]["label"],
            "Render or reuse the comparative listening-master challenger",
        )
        self.assertFalse(result["dry"]["durableEffect"])
        self.assertFalse(result["balanced"]["durableEffect"])
        self.assertFalse(result["master"]["durableEffect"])

    def test_listening_master_review_routes_keep_feedback_separate_from_product_state(
        self,
    ) -> None:
        result = self.run_node(
            """
let time = 0;
const journal = developer.createOperationJournal({now: () => ++time});
const routes = [
  '/api/listening-master-review/prepare?token=secret',
  '/api/listening-master-review?token=secret',
  '/api/listening-master-review/resolve?token=secret',
];
for (const route of routes) {
  const operation = journal.start(route, 'POST');
  operation.complete({statusCode: 200});
}
console.log(JSON.stringify({
  descriptors: routes.map(route => developer.routeDescriptor(route)),
  records: journal.snapshot().records,
}));
"""
        )

        descriptors = result["descriptors"]
        self.assertEqual(
            [descriptor["operation"] for descriptor in descriptors],
            [
                "arrangement.master_review_prepare",
                "arrangement.master_review_complete",
                "arrangement.master_review_resolve",
            ],
        )
        self.assertEqual(
            [descriptor["durableEffect"] for descriptor in descriptors],
            [True, True, True],
        )
        self.assertIn(
            "WorkbenchMasterReviewService.prepare",
            descriptors[0]["symbols"][-1],
        )
        self.assertIn(
            "WorkbenchMasterReviewService.complete",
            descriptors[1]["symbols"][-1],
        )
        self.assertIn(
            "WorkbenchMasterReviewService.resolve",
            descriptors[2]["symbols"][-1],
        )
        self.assertIn("separate explicit", descriptors[1]["label"])
        self.assertIn("without promotion", descriptors[2]["label"])
        self.assertEqual(
            [
                record["durable_effect_possible"]
                for record in result["records"]
            ],
            [True, True, True],
        )
        self.assertNotIn("secret", json.dumps(result))

    def test_listening_master_review_inspector_explains_durable_scope(self) -> None:
        result = self.run_node(
            """
(async () => {
  async function rendered(operation) {
    const host = {innerHTML: '', querySelector() { return null; }};
    const inspector = developer.createInspector({api: async () => ({
      code_flow: {nodes: []},
      runtime: {recent_operations: [{
        sequence: 1,
        operation,
        method: 'POST',
        status: 'completed',
        http_status: 200,
        duration_ms: 1,
        durable_effect_possible: true,
        symbols: [
          'sunofriend.workbench_server._WorkbenchHandler.do_POST',
          `sunofriend.workbench_master_review.WorkbenchMasterReviewService.${
            operation.endsWith('prepare')
              ? 'prepare'
              : operation.endsWith('complete') ? 'complete' : 'resolve'
          }`,
        ],
        frames: [],
      }], active_operations: []},
      privacy: {},
      effects: {},
    })});
    inspector.setEnabled(true);
    inspector.renderInto(host);
    await new Promise(resolve => setTimeout(resolve, 0));
    return host.innerHTML;
  }
  console.log(JSON.stringify({
    prepare: await rendered('arrangement.master_review_prepare'),
    complete: await rendered('arrangement.master_review_complete'),
    resolve: await rendered('arrangement.master_review_resolve'),
  }));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )

        self.assertIn(
            "private comparison session and rebuildable A/B cache only; no feedback or product change",
            result["prepare"],
        )
        self.assertIn(
            "separate local feedback artifact only; no Workbench decision or product change",
            result["complete"],
        )
        self.assertIn(
            "separate local resolution artifact only; never a selection, default, promotion or product change",
            result["resolve"],
        )
        self.assertNotIn(
            "only through this explicit production command",
            result["complete"],
        )

    def test_listening_master_review_export_is_a_distinct_read_only_route(
        self,
    ) -> None:
        result = self.run_node(
            """
let time = 0;
const path = '/api/listening-master-review-export'
  + '?kind=review&review_id=private-identity&token=secret';
const descriptor = developer.routeDescriptor(path);
const journal = developer.createOperationJournal({now: () => ++time});
const operation = journal.start(path, 'GET');
operation.complete({statusCode: 200});
console.log(JSON.stringify({descriptor, snapshot: journal.snapshot()}));
"""
        )

        descriptor = result["descriptor"]
        self.assertEqual(
            descriptor["operation"],
            "arrangement.master_review_export",
        )
        self.assertFalse(descriptor["durableEffect"])
        self.assertIn(
            "sunofriend.workbench_master_review."
            "WorkbenchMasterReviewService.review",
            descriptor["symbols"],
        )
        self.assertIn(
            "sunofriend.workbench_master_review."
            "WorkbenchMasterReviewService.resolution",
            descriptor["symbols"],
        )
        record = result["snapshot"]["records"][0]
        self.assertEqual(record["method"], "GET")
        self.assertEqual(
            record["route"],
            "/api/listening-master-review-export",
        )
        self.assertFalse(record["durable_effect_possible"])
        encoded = json.dumps(result)
        self.assertNotIn("private-identity", encoded)
        self.assertNotIn("secret", encoded)


if __name__ == "__main__":
    unittest.main()
