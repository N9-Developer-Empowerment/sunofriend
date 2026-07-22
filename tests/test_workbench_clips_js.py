from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


CLIPS_PATH = Path("src/sunofriend/workbench_clips.js").resolve()


class WorkbenchClipsJavaScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.node = shutil.which("node")
        if not cls.node:
            raise unittest.SkipTest("Node.js is not installed")

    def run_node(self, body: str) -> dict[str, object]:
        script = f"""
const clips = require({json.dumps(str(CLIPS_PATH))});
function createDynamicHost() {{
  let html = '';
  let elements = new Map();
  let dataElements = new Map();
  function tagForId(id) {{
    return html.match(new RegExp(`<[^>]+id="${{id}}"[^>]*>`))?.[0] || '';
  }}
  function elementForId(id) {{
    const tag = tagForId(id);
    if (!tag) return null;
    if (!elements.has(id)) {{
      const value = tag.match(/value="([^"]*)"/)?.[1] || '';
      elements.set(id, {{
        id, value, disabled: tag.includes(' disabled'), textContent: id,
        isConnected: true, onclick: null, oninput: null, onsubmit: null,
        pause() {{}}, focus() {{}},
      }});
    }}
    return elements.get(id);
  }}
  const datasetSelectors = {{
    '[data-open-clip]': ['openClip', 'data-open-clip'],
    '[data-lineage-clip]': ['lineageClip', 'data-lineage-clip'],
    '[data-plan-inspect-clip]': ['planInspectClip', 'data-plan-inspect-clip'],
    '[data-remove-placement]': ['removePlacement', 'data-remove-placement'],
  }};
  return {{
    get innerHTML() {{ return html; }},
    set innerHTML(value) {{
      for (const element of elements.values()) element.isConnected = false;
      html = String(value);
      elements = new Map();
      dataElements = new Map();
    }},
    querySelector(selector) {{
      return selector.startsWith('#') ? elementForId(selector.slice(1)) : null;
    }},
    querySelectorAll(selector) {{
      if (selector === 'audio') return [];
      const definition = datasetSelectors[selector];
      if (!definition) return [];
      const [datasetKey, attribute] = definition;
      const pattern = new RegExp(`${{attribute}}="([^"]+)"`, 'g');
      const result = [];
      for (const match of html.matchAll(pattern)) {{
        const key = `${{selector}}:${{match[1]}}`;
        if (!dataElements.has(key)) dataElements.set(key, {{dataset: {{[datasetKey]: match[1]}}, disabled: false, onclick: null}});
        result.push(dataElements.get(key));
      }}
      return result;
    }},
    element(id) {{ return elementForId(id); }},
    data(selector, value) {{ return dataElements.get(`${{selector}}:${{value}}`); }},
  }};
}}
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

    def test_exports_browser_factory_without_persistent_or_direct_network_state(self) -> None:
        source = CLIPS_PATH.read_text(encoding="utf-8")

        self.assertIn("createClipLibrary", source)
        self.assertNotIn("localStorage", source)
        self.assertNotIn("sessionStorage", source)
        self.assertNotIn("indexedDB", source)
        self.assertNotIn("WebSocket", source)
        self.assertNotIn("EventSource", source)

    def test_browse_uses_injected_api_and_explains_the_read_only_boundary(self) -> None:
        result = self.run_node(
            """
global.fetch = () => { throw new Error('direct fetch must not be used'); };
const calls = [];
const host = {
  innerHTML: '',
  querySelector() { return null; },
  querySelectorAll() { return []; },
};
const browser = clips.createClipLibrary({
  api: async (path, options) => {
    calls.push({path, method: options?.method || 'GET'});
    return {
      schema: 'sunofriend.workbench-clip-browse.v1',
      page: {offset: 0, limit: 24, total: 1, returned: 1, has_more: false},
      clips: [{
        clip_id: 'clip-1', object_sha256: 'a'.repeat(64), title: 'Golden bass',
        role: 'bass', key: 'B major', bpm: 119, revision: 1,
        note_count: 12, duration_seconds: 8, tags: ['reviewed'],
      }],
    };
  },
  escapeHtml: value => String(value),
});
browser.setCapability({
  enabled: true,
  acceptance: {status: 'passed', pack_sha256: 'b'.repeat(64)},
  library: {clip_count: 1, lineage_count: 1},
});
browser.renderInto(host);
setTimeout(() => console.log(JSON.stringify({calls, html: host.innerHTML})), 0);
"""
        )

        self.assertEqual(len(result["calls"]), 1)
        self.assertTrue(result["calls"][0]["path"].startswith("/api/clips?"))
        self.assertEqual(result["calls"][0]["method"], "GET")
        self.assertIn("Phase 6 read-only Clip Library", result["html"])
        self.assertIn("Golden bass", result["html"])
        self.assertIn("no transform, edit, tag change, hybrid", result["html"])
        self.assertNotIn("Proposed reuse plan", result["html"])
        self.assertNotIn("/api/clip-reuse-plan", json.dumps(result["calls"]))

    def test_real_detail_and_artifact_contract_drives_lineage_and_download_ui(self) -> None:
        result = self.run_node(
            """
(async () => {
  const calls = [];
  const elements = {};
  const openButton = {dataset: {openClip: 'clip-1'}, onclick: null};
  const host = {
    innerHTML: '',
    querySelector(selector) {
      if (!selector.startsWith('#')) return null;
      const id = selector.slice(1);
      if (!this.innerHTML.includes(`id="${id}"`)) return null;
      if (!elements[id]) elements[id] = {
        id, disabled: false, textContent: id, isConnected: true, onclick: null,
      };
      return elements[id];
    },
    querySelectorAll(selector) {
      if (selector === 'audio') return [];
      if (selector === '[data-open-clip]' && this.innerHTML.includes('data-open-clip="clip-1"')) return [openButton];
      return [];
    },
  };
  const api = async (path, options = {}) => {
    calls.push({path, method: options.method || 'GET', body: options.body || null});
    if (path.startsWith('/api/clips?')) return {
      schema: 'sunofriend.workbench-clip-browse.v1',
      page: {offset: 0, limit: 24, total: 1, returned: 1, has_more: false},
      clips: [{
        clip_id: 'clip-1', object_sha256: 'a'.repeat(64), title: 'Golden bass',
        role: 'bass', key: 'B major', bpm: 119, revision: 1,
        note_count: 12, chord_count: 0, duration_seconds: 8, tags: ['reviewed'],
      }],
    };
    if (path === '/api/clips/clip-1') return {
      schema: 'sunofriend.workbench-clip-detail.v1',
      clip: {
        clip_id: 'clip-1', object_sha256: 'a'.repeat(64), title: 'Golden bass',
        role: 'bass', key: 'B major', bpm: 119, revision: 1,
        note_count: 12, chord_count: 0, pitch_range: {minimum: 35, maximum: 47},
        duration: {export_seconds: 8},
        timing_contract: {resolved_mode: 'stem_locked', export_bpm: 119},
        instrument: {program: 38, channel: 0},
      },
      lineage: {versions: [{clip_id: 'clip-1', title: 'Golden bass', revision: 1, bpm: 119}]},
    };
    if (path === '/api/clip-artifact') return {
      artifact: {
        schema: 'sunofriend.workbench-clip-artifact.v1', cache_hit: false,
        clip: {clip_id: 'clip-1'},
        timing_contract: {resolved_mode: 'stem_locked', export_bpm: 119},
        midi: {name: 'clip.mid', sha256: 'c'.repeat(64), url: '/media/clip-midi?token=secret'},
        preview: null,
        effects: {library_mutated: false, clip_mutated: false},
      },
    };
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml: value => String(value)});
  browser.setCapability({
    enabled: true,
    acceptance: {status: 'passed', pack_sha256: 'b'.repeat(64)},
    library: {clip_count: 1, lineage_count: 1},
  });
  browser.renderInto(host);
  await new Promise(resolve => setTimeout(resolve, 0));
  openButton.onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  await elements['clip-midi'].onclick();
  console.log(JSON.stringify({calls, html: host.innerHTML}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )

        self.assertEqual(
            [call["path"].split("?", 1)[0] for call in result["calls"]],
            ["/api/clips", "/api/clips/clip-1", "/api/clip-artifact"],
        )
        self.assertEqual(
            json.loads(result["calls"][-1]["body"]),
            {"clip_id": "clip-1", "include_preview": False},
        )
        self.assertIn("Version lineage", result["html"])
        self.assertIn("stem_locked", result["html"])
        self.assertIn("Download deterministic MIDI", result["html"])
        self.assertIn("Library and project effects: zero", result["html"])
        self.assertNotIn("undefined", result["html"])

    def test_explicit_place_uses_only_immutable_ids_position_and_plan_guard(self) -> None:
        result = self.run_node(
            """
(async () => {
  const calls = [];
  const host = createDynamicHost();
  const initialPlan = {
    schema: 'sunofriend.workbench-clip-reuse-plan.v1', plan_id: 'reuse-plan-1',
    plan_sha256: 'd'.repeat(64), revision: 0, restore_status: 'empty-current-binding',
    placement_count: 0, placements: [],
    target_project: {key: 'B minor', bpm: 113},
    target_grid: {beats_per_bar: 4, ticks_per_beat: 480, origin: 'recorded-zero', downbeat_status: 'unconfirmed'},
  };
  const api = async (path, options = {}) => {
    calls.push({path, method: options.method || 'GET', body: options.body || null});
    if (path.startsWith('/api/clips?')) return {
      page: {offset: 0, limit: 24, total: 1, returned: 1, has_more: false},
      clips: [{clip_id: 'clip-1', object_sha256: 'a'.repeat(64), title: 'Golden bass', role: 'bass', key: 'B major', bpm: 119, revision: 1, note_count: 12, duration_seconds: 8, tags: []}],
    };
    if (path === '/api/clip-reuse-plan') return {plan: initialPlan};
    if (path === '/api/clips/clip-1') return {
      clip: {
        clip_id: 'clip-1', object_sha256: 'a'.repeat(64), title: 'Golden bass', role: 'bass', key: 'B major', bpm: 119, revision: 1,
        note_count: 12, chord_count: 0, duration: {export_seconds: 8}, timing_contract: {resolved_mode: 'stem_locked', export_bpm: 119}, instrument: {program: 38, channel: 0},
      },
      lineage: {versions: [{clip_id: 'clip-1', title: 'Golden bass', revision: 1, bpm: 119}]},
      reuse_compatibility: {
        proposal_enabled: true, placement_ready: true,
        target_project: {key: 'B minor', bpm: 113},
        target_grid: {beats_per_bar: 4, ticks_per_beat: 480, origin: 'recorded-zero', downbeat_status: 'unconfirmed'},
        clip: {clip_id: 'clip-1', object_sha256: 'a'.repeat(64), key: 'B major', bpm: 119},
        comparison: {key_status: 'different', bpm_status: 'different'},
        warnings: [
          {code: 'key-mismatch', message: 'Clip key B major differs from project key B minor.'},
          {code: 'bpm-mismatch', message: 'Clip BPM 119 differs from project BPM 113.'},
        ],
        transform_applied: false,
      },
    };
    if (path === '/api/clip-reuse-action') {
      return {
        operation: 'place', effects: {reuse_plan_changed: true, feedback_recorded: false},
        plan: {
          ...initialPlan, revision: 1, plan_sha256: 'e'.repeat(64), placement_count: 1,
          placements: [{
            placement_id: 'placement-1', placed_revision: 1,
            clip: {clip_id: 'clip-1', object_sha256: 'a'.repeat(64), lineage_id: 'lineage-1', revision: 1, title: 'Golden bass', role: 'bass', key: 'B major', bpm: 119, note_count: 12, duration_beats: 8},
            target: {bar: 3, beat: 2, tick_in_beat: 0, start_tick: 4320, start_beat: 9, nominal_end_tick: 8160, nominal_end_beat: 17},
            compatibility: {comparison: {key_status: 'different', bpm_status: 'different'}, warnings: [{code: 'bpm-mismatch', message: 'Clip BPM 119 differs from project BPM 113.'}], transform_applied: false, render_ready: false},
          }],
        },
      };
    }
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml: value => String(value)});
  browser.setCapability(
    {enabled: true, acceptance: {pack_sha256: 'b'.repeat(64)}, library: {clip_count: 1}},
    {enabled: true, target_project: {key: 'B minor', bpm: 113}, target_grid: {beats_per_bar: 4, ticks_per_beat: 480, origin: 'recorded-zero', downbeat_status: 'unconfirmed'}, actions: {place: true, remove: true}, limits: {maximum_placements: 64}},
  );
  browser.renderInto(host);
  await new Promise(resolve => setTimeout(resolve, 0));
  host.querySelectorAll('[data-open-clip]')[0].onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  const detailHtml = host.innerHTML;
  host.element('clip-start-bar').value = '3';
  host.element('clip-start-beat').value = '2';
  host.element('clip-place-form').onsubmit({preventDefault() {}});
  await new Promise(resolve => setTimeout(resolve, 0));
  const action = calls.find(call => call.path === '/api/clip-reuse-action');
  console.log(JSON.stringify({calls, actionBody: JSON.parse(action.body), detailHtml, html: host.innerHTML}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )

        body = result["actionBody"]
        self.assertEqual(
            body,
            {
                "action": "place",
                "plan_id": "reuse-plan-1",
                "plan_sha256": "d" * 64,
                "expected_revision": 0,
                "clip_id": "clip-1",
                "clip_object_sha256": "a" * 64,
                "target": {"bar": 3, "beat": 2, "tick_in_beat": 0},
            },
        )
        for forbidden in ["title", "role", "key", "bpm", "warnings", "duration"]:
            self.assertNotIn(forbidden, body)
        paths = [call["path"].split("?", 1)[0] for call in result["calls"]]
        self.assertNotIn("/api/events", paths)
        self.assertNotIn("/api/arrangement", paths)
        self.assertNotIn("/api/garageband-pack-basket", paths)
        self.assertIn("Clip key B major differs from project key B minor", result["detailHtml"])
        self.assertIn("No transpose, tempo conversion, stretch, merge, render", result["detailHtml"])
        self.assertIn("planning coordinates, not confirmed musical bars", result["detailHtml"])
        self.assertIn("Proposed Clip arrangement", result["html"])
        self.assertIn("current arrangement and GarageBand Pack were not changed", result["html"])
        self.assertIn("Clip BPM 119 differs from project BPM 113", result["html"])

    def test_neutral_audition_records_no_reuse_or_preference_action(self) -> None:
        result = self.run_node(
            """
(async () => {
  const calls = [];
  const host = createDynamicHost();
  const plan = {plan_id: 'reuse-plan-1', plan_sha256: 'd'.repeat(64), revision: 4, placement_count: 0, placements: [], target_project: {key: 'B minor', bpm: 113}, target_grid: {beats_per_bar: 4, ticks_per_beat: 480, origin: 'recorded-zero', downbeat_status: 'unconfirmed'}};
  const api = async (path, options = {}) => {
    calls.push({path, method: options.method || 'GET', body: options.body || null});
    if (path.startsWith('/api/clips?')) return {page: {offset: 0, total: 1, has_more: false}, clips: [{clip_id: 'clip-1', object_sha256: 'a'.repeat(64), title: 'Bass', role: 'bass', key: 'B minor', bpm: 113, revision: 1, note_count: 2, duration_seconds: 2, tags: []}]};
    if (path === '/api/clip-reuse-plan') return {plan};
    if (path === '/api/clips/clip-1') return {
      clip: {clip_id: 'clip-1', object_sha256: 'a'.repeat(64), title: 'Bass', role: 'bass', key: 'B minor', bpm: 113, revision: 1, note_count: 2, chord_count: 0, duration: {export_seconds: 2}, timing_contract: {resolved_mode: 'musical', export_bpm: 113}, instrument: {program: 38, channel: 0}},
      lineage: {versions: [{clip_id: 'clip-1', title: 'Bass', revision: 1, bpm: 113}]},
      reuse_compatibility: {proposal_enabled: true, placement_ready: true, target_project: {key: 'B minor', bpm: 113}, target_grid: plan.target_grid, clip: {clip_id: 'clip-1', object_sha256: 'a'.repeat(64), key: 'B minor', bpm: 113}, comparison: {key_status: 'matched', bpm_status: 'matched'}, warnings: [], transform_applied: false},
    };
    if (path === '/api/clip-artifact') return {artifact: {clip: {clip_id: 'clip-1'}, cache_hit: true, timing_contract: {resolved_mode: 'musical', export_bpm: 113}, midi: {name: 'clip.mid', sha256: 'c'.repeat(64), url: '/media/midi'}, preview: {name: 'preview.wav', sha256: 'f'.repeat(64), url: '/media/wav'}}};
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml: value => String(value)});
  browser.setCapability(
    {enabled: true, acceptance: {pack_sha256: 'b'.repeat(64)}, library: {clip_count: 1}},
    {enabled: true, target_project: plan.target_project, target_grid: plan.target_grid, actions: {place: true, remove: true}},
  );
  browser.renderInto(host);
  await new Promise(resolve => setTimeout(resolve, 0));
  host.querySelectorAll('[data-open-clip]')[0].onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  await host.element('clip-preview').onclick();
  console.log(JSON.stringify({calls, html: host.innerHTML}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )

        action_calls = [
            call for call in result["calls"] if call["path"] == "/api/clip-reuse-action"
        ]
        self.assertEqual(action_calls, [])
        artifact = next(
            call for call in result["calls"] if call["path"] == "/api/clip-artifact"
        )
        self.assertEqual(
            json.loads(artifact["body"]),
            {"clip_id": "clip-1", "include_preview": True},
        )
        self.assertIn("Nothing was preferred, placed or saved", result["html"])
        self.assertIn("Listening and downloading do not record a preference", result["html"])

    def test_restored_plan_removal_uses_only_plan_guard_and_placement_id(self) -> None:
        result = self.run_node(
            """
(async () => {
  const calls = [];
  const host = createDynamicHost();
  const placement = {
    placement_id: 'placement-7', placed_revision: 7,
    clip: {clip_id: 'clip-7', object_sha256: 'a'.repeat(64), lineage_id: 'lineage-7', revision: 2, title: 'Restored keys', role: 'keys', key: 'A minor', bpm: 120, note_count: 8, duration_beats: 4},
    target: {bar: 2, beat: 1, tick_in_beat: 0, start_tick: 1920, start_beat: 4, nominal_end_tick: 3840, nominal_end_beat: 8},
    compatibility: {comparison: {key_status: 'matched', bpm_status: 'matched'}, warnings: [], transform_applied: false, render_ready: false},
  };
  const restored = {schema: 'sunofriend.workbench-clip-reuse-plan.v1', plan_id: 'reuse-plan-restored', plan_sha256: 'd'.repeat(64), revision: 7, restore_status: 'saved-current-binding-restored', placement_count: 1, placements: [placement], target_project: {key: 'A minor', bpm: 120}, target_grid: {beats_per_bar: 4, ticks_per_beat: 480, origin: 'recorded-zero', downbeat_status: 'unconfirmed'}};
  const api = async (path, options = {}) => {
    calls.push({path, method: options.method || 'GET', body: options.body || null});
    if (path.startsWith('/api/clips?')) return {page: {offset: 0, total: 0, has_more: false}, clips: []};
    if (path === '/api/clip-reuse-plan') return {plan: restored};
    if (path === '/api/clip-reuse-action') return {operation: 'remove', effects: {reuse_plan_changed: true}, plan: {...restored, plan_sha256: 'e'.repeat(64), revision: 8, placement_count: 0, placements: []}};
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml: value => String(value)});
  browser.setCapability(
    {enabled: true, acceptance: {pack_sha256: 'b'.repeat(64)}, library: {clip_count: 1}},
    {enabled: true, target_project: restored.target_project, target_grid: restored.target_grid, actions: {place: true, remove: true}},
  );
  browser.renderInto(host);
  await new Promise(resolve => setTimeout(resolve, 0));
  host.element('clip-plan-view').onclick();
  host.querySelectorAll('[data-remove-placement]')[0].onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  const action = calls.find(call => call.path === '/api/clip-reuse-action');
  console.log(JSON.stringify({calls, actionBody: JSON.parse(action.body), html: host.innerHTML}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )

        self.assertEqual(
            result["actionBody"],
            {
                "action": "remove",
                "plan_id": "reuse-plan-restored",
                "plan_sha256": "d" * 64,
                "expected_revision": 7,
                "placement_id": "placement-7",
            },
        )
        self.assertEqual(
            len(
                [
                    call
                    for call in result["calls"]
                    if call["path"] == "/api/clip-reuse-plan"
                ]
            ),
            1,
        )
        self.assertIn("append-only local history", result["html"])
        self.assertIn("No Clips are in this proposal", result["html"])

    def test_revision_conflict_reloads_once_without_retrying_and_keeps_draft(self) -> None:
        result = self.run_node(
            """
(async () => {
  const calls = [];
  const host = createDynamicHost();
  let planReads = 0;
  const grid = {beats_per_bar: 4, ticks_per_beat: 480, origin: 'recorded-zero', downbeat_status: 'unconfirmed'};
  const basePlan = {plan_id: 'reuse-plan-1', plan_sha256: 'd'.repeat(64), revision: 1, placement_count: 0, placements: [], target_project: {key: 'C major', bpm: 100}, target_grid: grid};
  const api = async (path, options = {}) => {
    calls.push({path, method: options.method || 'GET', body: options.body || null});
    if (path.startsWith('/api/clips?')) return {page: {offset: 0, total: 1, has_more: false}, clips: [{clip_id: 'clip-1', object_sha256: 'a'.repeat(64), title: 'Lead', role: 'lead', key: 'C major', bpm: 100, revision: 1, note_count: 4, duration_seconds: 4, tags: []}]};
    if (path === '/api/clip-reuse-plan') {
      planReads += 1;
      return {plan: planReads === 1 ? basePlan : {...basePlan, revision: 2, plan_sha256: 'e'.repeat(64)}};
    }
    if (path === '/api/clips/clip-1') return {
      clip: {clip_id: 'clip-1', object_sha256: 'a'.repeat(64), title: 'Lead', role: 'lead', key: 'C major', bpm: 100, revision: 1, note_count: 4, chord_count: 0, duration: {export_seconds: 4}, timing_contract: {resolved_mode: 'musical', export_bpm: 100}, instrument: {program: 80, channel: 0}},
      lineage: {versions: [{clip_id: 'clip-1', title: 'Lead', revision: 1, bpm: 100}]},
      reuse_compatibility: {proposal_enabled: true, placement_ready: true, target_project: basePlan.target_project, target_grid: grid, clip: {clip_id: 'clip-1', object_sha256: 'a'.repeat(64), key: 'C major', bpm: 100}, comparison: {key_status: 'matched', bpm_status: 'matched'}, warnings: [], transform_applied: false},
    };
    if (path === '/api/clip-reuse-action') {
      const error = new Error('reuse proposal revision conflict');
      error.status = 409;
      throw error;
    }
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml: value => String(value)});
  browser.setCapability(
    {enabled: true, acceptance: {pack_sha256: 'b'.repeat(64)}, library: {clip_count: 1}},
    {enabled: true, target_project: basePlan.target_project, target_grid: grid, actions: {place: true, remove: true}},
  );
  browser.renderInto(host);
  await new Promise(resolve => setTimeout(resolve, 0));
  host.querySelectorAll('[data-open-clip]')[0].onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  host.element('clip-start-bar').value = '3';
  host.element('clip-start-beat').value = '4';
  host.element('clip-place-form').onsubmit({preventDefault() {}});
  await new Promise(resolve => setTimeout(resolve, 0));
  await new Promise(resolve => setTimeout(resolve, 0));
  console.log(JSON.stringify({calls, planReads, html: host.innerHTML}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )

        self.assertEqual(result["planReads"], 2)
        self.assertEqual(
            len(
                [
                    call
                    for call in result["calls"]
                    if call["path"] == "/api/clip-reuse-action"
                ]
            ),
            1,
        )
        self.assertIn("No automatic retry was attempted", result["html"])
        self.assertIn("earlier save may already have completed", result["html"])
        self.assertIn('id="clip-start-bar" name="bar" type="number" min="1" step="1" value="3"', result["html"])
        self.assertIn('id="clip-start-beat" name="beat" type="number" min="1" max="4" step="1" value="4"', result["html"])


if __name__ == "__main__":
    unittest.main()
