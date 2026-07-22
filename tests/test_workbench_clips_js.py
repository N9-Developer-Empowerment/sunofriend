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
  let focusedId = '';
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
        pause() {{}}, focus() {{ focusedId = id; this.focused = true; }},
      }});
    }}
    return elements.get(id);
  }}
  const datasetSelectors = {{
    '[data-open-clip]': ['openClip', 'data-open-clip'],
    '[data-lineage-clip]': ['lineageClip', 'data-lineage-clip'],
    '[data-plan-inspect-clip]': ['planInspectClip', 'data-plan-inspect-clip'],
    '[data-remove-placement]': ['removePlacement', 'data-remove-placement'],
    '[data-correction-note-ref]': ['correctionNoteRef', 'data-correction-note-ref'],
    '[data-correction-note-svg]': ['correctionNoteSvg', 'data-correction-note-svg'],
    '[data-correction-pitch-delta]': ['correctionPitchDelta', 'data-correction-pitch-delta'],
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
        if (!dataElements.has(key)) dataElements.set(key, {{
          dataset: {{[datasetKey]: match[1]}}, disabled: false, onclick: null, onfocus: null,
          focus() {{ this.focused = true; if (this.onfocus) this.onfocus(); }},
        }});
        result.push(dataElements.get(key));
      }}
      return result;
    }},
    element(id) {{ return elementForId(id); }},
    data(selector, value) {{ return dataElements.get(`${{selector}}:${{value}}`); }},
    get focusedId() {{ return focusedId; }},
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
        self.assertNotIn("Create a transformed alternative", result["html"])
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
        self.assertIn("(viewing)", result["html"])
        self.assertNotIn("(current)", result["html"])
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

    def test_key_transform_requires_temporary_review_then_explicit_create(self) -> None:
        result = self.run_node(
            """
(async () => {
  const calls = [];
  const host = createDynamicHost();
  const libraryHash = 'b'.repeat(64);
  const projectionHash = 'c'.repeat(64);
  let created = false;
  const api = async (path, options = {}) => {
    calls.push({path, method: options.method || 'GET', body: options.body || null});
    if (path.startsWith('/api/clips?')) return {
      library_state_sha256: (created ? 'f' : 'b').repeat(64),
      page: {offset: 0, total: created ? 2 : 1, has_more: false},
      clips: [
        {clip_id: 'clip-parent', object_sha256: 'a'.repeat(64), title: 'Exact bass', role: 'bass', key: 'B major', bpm: 119, revision: 2, note_count: 4, duration_seconds: 4, tags: []},
        ...(created ? [{clip_id: 'clip-child', object_sha256: 'd'.repeat(64), title: 'Exact bass', role: 'bass', key: 'G major', bpm: 119, revision: 3, note_count: 4, duration_seconds: 4, tags: []}] : []),
      ],
    };
    if (path === '/api/clips/clip-parent') return {
      library_state_sha256: libraryHash,
      clip: {clip_id: 'clip-parent', object_sha256: 'a'.repeat(64), title: 'Exact bass', role: 'bass', key: 'B major', bpm: 119, revision: 2, note_count: 4, chord_count: 1, pitch_range: {minimum: 35, maximum: 47}, duration: {export_seconds: 4}, timing_contract: {resolved_mode: 'musical', export_bpm: 119}, instrument: {program: 38, channel: 0}},
      lineage: {versions: [{clip_id: 'clip-parent', title: 'Exact bass', revision: 2, bpm: 119}]},
    };
    if (path === '/api/clip-transform-projection') {
      const request = JSON.parse(options.body);
      return {projection: {
        projection_sha256: projectionHash,
        transform: request.transform,
        library: {state_sha256: libraryHash},
        parent: {clip_id: 'clip-parent', object_sha256: 'a'.repeat(64), lineage_id: 'lineage-1', revision: 2, key: 'B major', bpm: 119, duration_seconds: 4, note_count: 4, chord_count: 1, pitch_range: {minimum: 35, maximum: 47}},
        child: {clip_id: 'clip-child', object_sha256: 'd'.repeat(64), lineage_id: 'lineage-1', revision: 3, key: 'G major', bpm: 119, duration_seconds: 4, note_count: 4, chord_count: 1, pitch_range: {minimum: 43, maximum: 55}},
        diff: {kind: 'key', key_before: 'B major', key_after: 'G major', semitones: 8, note_pitches_changed: 4, chord_symbols_changed: 1, note_count_before: 4, note_count_after: 4, chord_count_before: 1, chord_count_after: 1, bpm_changed: false, timing_changed: false},
        warnings: [{message: '<unsafe warning>'}],
        effects: {library_mutated: false, clip_created: false, selection_changed: false, placement_changed: false, pack_changed: false},
      }};
    }
    if (path === '/api/clip-transform-action') {
      created = true;
      return {result: {
        status: 'created', replayed: false, projection_sha256: projectionHash,
        parent: {clip_id: 'clip-parent', object_sha256: 'a'.repeat(64), lineage_id: 'lineage-1', revision: 2},
        child: {clip_id: 'clip-child', parent_clip_id: 'clip-parent', object_sha256: 'd'.repeat(64), lineage_id: 'lineage-1', revision: 3, key: 'G major', bpm: 119},
        library: {expected_state_sha256: libraryHash, previous_state_sha256: libraryHash, current_state_sha256: 'f'.repeat(64)},
        effects: {library_mutated: true, child_clip_created: true, transform_applied: true, selection_changed: false, placement_changed: false, pack_changed: false},
      }};
    }
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api});
  browser.setCapability(
    {enabled: true, acceptance: {pack_sha256: 'e'.repeat(64)}, library: {clip_count: 1, state_sha256: libraryHash}},
    null,
    {enabled: true, transforms: {same_mode_key: {enabled: true}, bpm: {enabled: true}}, target_project: {key: 'G major', bpm: 125}, limits: {minimum_bpm: 20, maximum_bpm: 400}},
  );
  browser.renderInto(host);
  await new Promise(resolve => setTimeout(resolve, 0));
  host.querySelectorAll('[data-open-clip]')[0].onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  const initialHtml = host.innerHTML;
  host.element('clip-transform-operation-key').onclick();
  const focusAfterOperation = host.focusedId;
  host.element('clip-transform-target-key').value = 'G major';
  host.element('clip-transform-target-key').oninput();
  host.element('clip-transform-direction-up').onclick();
  host.element('clip-transform-form').onsubmit({preventDefault() {}});
  await new Promise(resolve => setTimeout(resolve, 0));
  const reviewedHtml = host.innerHTML;
  host.element('clip-transform-create').onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  const successHtml = host.innerHTML;
  host.element('clip-back').onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  await new Promise(resolve => setTimeout(resolve, 0));
  const projectionCall = calls.find(call => call.path === '/api/clip-transform-projection');
  const createCall = calls.find(call => call.path === '/api/clip-transform-action');
  console.log(JSON.stringify({
    calls,
    projectionBody: JSON.parse(projectionCall.body),
    createBody: JSON.parse(createCall.body),
    initialHtml,
    reviewedHtml,
    successHtml,
    browseHtml: host.innerHTML,
    focusAfterOperation,
  }));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )

        self.assertIn("Create a transformed alternative", result["initialHtml"])
        self.assertIn("Sunofriend preselects nothing", result["initialHtml"])
        self.assertNotIn('name="clip-transform-operation" type="radio" value="key" checked', result["initialHtml"])
        self.assertEqual(
            result["projectionBody"],
            {
                "parent_clip_id": "clip-parent",
                "parent_object_sha256": "a" * 64,
                "library_state_sha256": "b" * 64,
                "transform": {
                    "kind": "key",
                    "target_key": "G major",
                    "direction": "up",
                },
            },
        )
        self.assertEqual(
            result["createBody"],
            {
                "action": "create",
                "parent_clip_id": "clip-parent",
                "parent_object_sha256": "a" * 64,
                "library_state_sha256": "b" * 64,
                "projection_sha256": "c" * 64,
                "transform": {
                    "kind": "key",
                    "target_key": "G major",
                    "direction": "up",
                },
            },
        )
        self.assertIn("Temporary transform review", result["reviewedHtml"])
        self.assertIn("Effects: zero", result["reviewedHtml"])
        self.assertIn("B major → G major", result["reviewedHtml"])
        self.assertIn("+8", result["reviewedHtml"])
        self.assertIn("&lt;unsafe warning&gt;", result["reviewedHtml"])
        self.assertEqual(result["focusAfterOperation"], "clip-transform-target-key")
        self.assertIn("35–47 → 43–55", result["reviewedHtml"])
        self.assertIn("Exact projection evidence", result["reviewedHtml"])
        self.assertIn("a" * 64, result["reviewedHtml"])
        self.assertIn("b" * 64, result["reviewedHtml"])
        self.assertIn("New immutable alternative created", result["successHtml"])
        self.assertIn("not preferred, selected, placed or added", result["successHtml"])
        self.assertIn("lineage-1", result["successHtml"])
        self.assertIn("f" * 64, result["successHtml"])
        self.assertIn("clip-child", result["successHtml"])
        self.assertIn("2 immutable clips", result["successHtml"])
        self.assertNotIn("library changed", result["successHtml"])
        self.assertIn("Inspect created version", result["successHtml"])
        self.assertIn("Showing 1–2 of 2 matching clips", result["browseHtml"])
        self.assertIn("2 immutable clips", result["browseHtml"])
        self.assertIn("clip-child", result["browseHtml"])
        paths = [call["path"].split("?", 1)[0] for call in result["calls"]]
        self.assertNotIn("/api/events", paths)
        self.assertNotIn("/api/clip-reuse-action", paths)
        self.assertNotIn("/api/garageband-pack-basket", paths)
        self.assertNotIn("/api/clips/clip-child", paths)
        self.assertEqual(paths.count("/api/clips"), 2)

    def test_bpm_transform_input_change_invalidates_review_without_creating(self) -> None:
        result = self.run_node(
            """
(async () => {
  const calls = [];
  const host = createDynamicHost();
  const api = async (path, options = {}) => {
    calls.push({path, method: options.method || 'GET', body: options.body || null});
    if (path.startsWith('/api/clips?')) return {page: {offset: 0, total: 1, has_more: false}, clips: [{clip_id: 'clip-1', object_sha256: 'a'.repeat(64), title: 'Keys', role: 'keys', key: 'C minor', bpm: 113, revision: 1, note_count: 3, duration_seconds: 6, tags: []}]};
    if (path === '/api/clips/clip-1') return {library_state_sha256: 'b'.repeat(64), clip: {clip_id: 'clip-1', object_sha256: 'a'.repeat(64), title: 'Keys', role: 'keys', key: 'C minor', bpm: 113, revision: 1, note_count: 3, chord_count: 0, duration: {export_seconds: 6}, timing_contract: {resolved_mode: 'musical', export_bpm: 113}, instrument: {program: 4, channel: 0}}, lineage: {versions: [{clip_id: 'clip-1', title: 'Keys', revision: 1, bpm: 113}]}};
    if (path === '/api/clip-transform-projection') {
      const request = JSON.parse(options.body);
      return {projection: {projection_sha256: 'c'.repeat(64), transform: request.transform, parent: {key: 'C minor', bpm: 113, duration_seconds: 6}, child: {key: 'C minor', bpm: 125, duration_seconds: 5.424}, diff: {kind: 'bpm', bpm_before: 113, bpm_after: 125, ratio: 1.106, timing_mode: 'musical', beat_positions_changed: false, source_seconds_changed: true}, warnings: [], effects: {library_mutated: false, clip_created: false}}};
    }
    if (path === '/api/clip-transform-action') throw new Error('create must not be called');
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml: value => String(value)});
  browser.setCapability(
    {enabled: true, acceptance: {pack_sha256: 'e'.repeat(64)}, library: {clip_count: 1, state_sha256: 'b'.repeat(64)}},
    null,
    {enabled: true, transforms: {same_mode_key: {enabled: true}, bpm: {enabled: true}}, limits: {minimum_bpm: 20, maximum_bpm: 400}},
  );
  browser.renderInto(host);
  await new Promise(resolve => setTimeout(resolve, 0));
  host.querySelectorAll('[data-open-clip]')[0].onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  host.element('clip-transform-operation-bpm').onclick();
  const boundsHtml = host.innerHTML;
  const focusAfterOperation = host.focusedId;
  host.element('clip-transform-target-bpm').value = '25';
  host.element('clip-transform-target-bpm').oninput();
  host.element('clip-transform-timing-musical').onclick();
  host.element('clip-transform-form').onsubmit({preventDefault() {}});
  await new Promise(resolve => setTimeout(resolve, 0));
  const invalidBoundsHtml = host.innerHTML;
  host.element('clip-transform-target-bpm').value = '125';
  host.element('clip-transform-target-bpm').oninput();
  host.element('clip-transform-form').onsubmit({preventDefault() {}});
  const pendingHtml = host.innerHTML;
  const pendingFocus = host.focusedId;
  await new Promise(resolve => setTimeout(resolve, 0));
  const reviewedHtml = host.innerHTML;
  const reviewedFocus = host.focusedId;
  host.element('clip-transform-target-bpm').value = '126';
  host.element('clip-transform-target-bpm').oninput();
  const create = host.element('clip-transform-create');
  if (create.onclick) create.onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  console.log(JSON.stringify({calls, boundsHtml, invalidBoundsHtml, pendingHtml, pendingFocus, reviewedHtml, reviewedFocus, html: host.innerHTML, createDisabled: host.element('clip-transform-create').disabled, focusAfterOperation, focusAfterEdit: host.focusedId}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )

        projection_calls = [
            call for call in result["calls"] if call["path"] == "/api/clip-transform-projection"
        ]
        self.assertEqual(len(projection_calls), 1)
        self.assertEqual(
            json.loads(projection_calls[0]["body"])["transform"],
            {"kind": "bpm", "target_bpm": 125, "timing_mode": "musical"},
        )
        self.assertIn('min="28.25" max="400"', result["boundsHtml"])
        self.assertIn("0.25×–4×", result["boundsHtml"])
        self.assertIn("target BPM must be from 28.25 to 400", result["invalidBoundsHtml"])
        self.assertIn('aria-busy="true"', result["pendingHtml"])
        self.assertGreaterEqual(result["pendingHtml"].count("<fieldset disabled>"), 2)
        self.assertIn('id="clip-transform-review" class="primary" type="submit" disabled', result["pendingHtml"])
        self.assertEqual(result["pendingFocus"], "clip-transform-status")
        self.assertEqual(result["reviewedFocus"], "clip-transform-projection")
        self.assertEqual(result["focusAfterOperation"], "clip-transform-target-bpm")
        self.assertEqual(result["focusAfterEdit"], "clip-transform-target-bpm")
        self.assertIn("Temporary transform review", result["reviewedHtml"])
        self.assertNotIn("Temporary transform review", result["html"])
        self.assertIn("Draft changed. Review it again", result["html"])
        self.assertTrue(result["createDisabled"])
        self.assertEqual(
            [call for call in result["calls"] if call["path"] == "/api/clip-transform-action"],
            [],
        )

    def test_idempotent_transform_replay_is_not_presented_as_a_new_version(self) -> None:
        result = self.run_node(
            """
(async () => {
  const host = createDynamicHost();
  const calls = [];
  const libraryHash = 'b'.repeat(64);
  const projectionHash = 'c'.repeat(64);
  const api = async (path, options = {}) => {
    calls.push(path);
    if (path.startsWith('/api/clips?')) return {page: {offset: 0, total: 2, has_more: false}, clips: [{clip_id: 'clip-parent', object_sha256: 'a'.repeat(64), title: 'Bass', role: 'bass', key: 'B major', bpm: 119, revision: 1, note_count: 2, duration_seconds: 2, tags: []}]};
    if (path === '/api/clips/clip-parent') return {library_state_sha256: libraryHash, clip: {clip_id: 'clip-parent', object_sha256: 'a'.repeat(64), title: 'Bass', role: 'bass', key: 'B major', bpm: 119, revision: 1, note_count: 2, chord_count: 0, pitch_range: {minimum: 35, maximum: 47}, duration: {export_seconds: 2}, timing_contract: {resolved_mode: 'musical', export_bpm: 119}, instrument: {program: 38, channel: 0}}, lineage: {versions: [{clip_id: 'clip-parent', title: 'Bass', revision: 1, bpm: 119}]}};
    if (path === '/api/clip-transform-projection') {
      const transform = JSON.parse(options.body).transform;
      return {projection: {projection_sha256: projectionHash, transform, parent: {clip_id: 'clip-parent', object_sha256: 'a'.repeat(64), lineage_id: 'lineage-1', revision: 1, key: 'B major', bpm: 119, duration_seconds: 2}, child: {clip_id: 'clip-child', object_sha256: 'd'.repeat(64), lineage_id: 'lineage-1', revision: 2, key: 'G major', bpm: 119, duration_seconds: 2}, diff: {kind: 'key', key_before: 'B major', key_after: 'G major', semitones: -4}, warnings: [], effects: {library_mutated: false, clip_created: false}}};
    }
    if (path === '/api/clip-transform-action') return {result: {status: 'replayed', replayed: true, projection_sha256: projectionHash, parent: {clip_id: 'clip-parent', object_sha256: 'a'.repeat(64), lineage_id: 'lineage-1', revision: 1}, child: {clip_id: 'clip-child', parent_clip_id: 'clip-parent', object_sha256: 'd'.repeat(64), lineage_id: 'lineage-1', revision: 2, key: 'G major', bpm: 119}, library: {expected_state_sha256: libraryHash, previous_state_sha256: libraryHash, current_state_sha256: libraryHash}, effects: {library_mutated: false, child_clip_created: false, transform_applied: false, selection_changed: false, placement_changed: false, pack_changed: false}}};
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml: value => String(value)});
  browser.setCapability(
    {enabled: true, acceptance: {pack_sha256: 'e'.repeat(64)}, library: {clip_count: 2, state_sha256: libraryHash}},
    null,
    {enabled: true, actions: {preview: true, create: true}, transforms: {same_mode_key: {enabled: true}, bpm: {enabled: true}}, limits: {minimum_bpm: 20, maximum_bpm: 400, minimum_bpm_ratio: 0.25, maximum_bpm_ratio: 4}},
  );
  browser.renderInto(host);
  await new Promise(resolve => setTimeout(resolve, 0));
  host.querySelectorAll('[data-open-clip]')[0].onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  host.element('clip-transform-operation-key').onclick();
  host.element('clip-transform-target-key').value = 'G major';
  host.element('clip-transform-target-key').oninput();
  host.element('clip-transform-direction-nearest').onclick();
  host.element('clip-transform-form').onsubmit({preventDefault() {}});
  await new Promise(resolve => setTimeout(resolve, 0));
  host.element('clip-transform-create').onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  console.log(JSON.stringify({calls, html: host.innerHTML}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )

        self.assertIn("Existing immutable alternative verified", result["html"])
        self.assertIn("appended nothing additional", result["html"])
        self.assertIn("idempotent replay · effects zero", result["html"])
        self.assertIn("Inspect existing version", result["html"])
        self.assertIn("2 immutable clips", result["html"])
        self.assertNotIn("New immutable alternative created", result["html"])
        self.assertNotIn("Inspect new version", result["html"])

    def test_transform_actions_are_explained_and_disabled_at_library_capacity(self) -> None:
        result = self.run_node(
            """
(async () => {
  const host = createDynamicHost();
  const calls = [];
  const api = async path => {
    calls.push(path);
    if (path.startsWith('/api/clips?')) return {page: {offset: 0, total: 10000, has_more: true}, clips: [{clip_id: 'clip-1', object_sha256: 'a'.repeat(64), title: 'Keys', role: 'keys', key: 'C major', bpm: 120, revision: 1, note_count: 3, duration_seconds: 2, tags: []}]};
    if (path === '/api/clips/clip-1') return {library_state_sha256: 'b'.repeat(64), clip: {clip_id: 'clip-1', object_sha256: 'a'.repeat(64), title: 'Keys', role: 'keys', key: 'C major', bpm: 120, revision: 1, note_count: 3, chord_count: 0, duration: {export_seconds: 2}, timing_contract: {resolved_mode: 'musical', export_bpm: 120}, instrument: {program: 4, channel: 0}}, lineage: {versions: [{clip_id: 'clip-1', title: 'Keys', revision: 1, bpm: 120}]}};
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml: value => String(value)});
  browser.setCapability(
    {enabled: true, acceptance: {pack_sha256: 'e'.repeat(64)}, library: {clip_count: 10000, state_sha256: 'b'.repeat(64)}},
    null,
    {enabled: true, actions: {preview: false, create: false}, transforms: {same_mode_key: {enabled: true}, bpm: {enabled: true}}, limits: {minimum_bpm: 20, maximum_bpm: 400, minimum_bpm_ratio: 0.25, maximum_bpm_ratio: 4}},
  );
  browser.renderInto(host);
  await new Promise(resolve => setTimeout(resolve, 0));
  host.querySelectorAll('[data-open-clip]')[0].onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  host.element('clip-transform-form').onsubmit({preventDefault() {}});
  host.element('clip-transform-create').onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  console.log(JSON.stringify({calls, html: host.innerHTML, keyDisabled: host.element('clip-transform-operation-key').disabled, bpmDisabled: host.element('clip-transform-operation-bpm').disabled, reviewDisabled: host.element('clip-transform-review').disabled, createDisabled: host.element('clip-transform-create').disabled}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )

        self.assertTrue(result["keyDisabled"])
        self.assertTrue(result["bpmDisabled"])
        self.assertTrue(result["reviewDisabled"])
        self.assertTrue(result["createDisabled"])
        self.assertIn("accepted 10,000-Clip boundary has been reached", result["html"])
        self.assertIn("inspect, audition and export", result["html"])
        self.assertNotIn("/api/clip-transform-projection", result["calls"])
        self.assertNotIn("/api/clip-transform-action", result["calls"])

    def test_drum_family_disables_key_change_but_keeps_bpm_available(self) -> None:
        result = self.run_node(
            """
(async () => {
  const host = createDynamicHost();
  const api = async path => {
    if (path.startsWith('/api/clips?')) return {page: {offset: 0, total: 1, has_more: false}, clips: [{clip_id: 'clip-drums', object_sha256: 'a'.repeat(64), title: 'Other kit', role: 'other_kit', key: 'C major', bpm: 119, revision: 1, note_count: 3, duration_seconds: 4, tags: []}]};
    if (path === '/api/clips/clip-drums') return {library_state_sha256: 'b'.repeat(64), clip: {clip_id: 'clip-drums', object_sha256: 'a'.repeat(64), title: 'Other kit', role: 'other_kit', key: 'C major', bpm: 119, revision: 1, note_count: 3, chord_count: 0, duration: {export_seconds: 4}, timing_contract: {resolved_mode: 'musical', export_bpm: 119}, instrument: {program: 0, channel: 9, is_drums: true}}, lineage: {versions: [{clip_id: 'clip-drums', title: 'Other kit', revision: 1, bpm: 119}]}};
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml: value => String(value)});
  browser.setCapability(
    {enabled: true, acceptance: {pack_sha256: 'e'.repeat(64)}, library: {clip_count: 1, state_sha256: 'b'.repeat(64)}},
    null,
    {enabled: true, transforms: {same_mode_key: {enabled: true}, bpm: {enabled: true}}, limits: {minimum_bpm: 20, maximum_bpm: 400}},
    {enabled: true, actions: {window: true, preview: true, create: true}, limits: {ticks_per_beat: 480, maximum_changes: 64}},
  );
  browser.renderInto(host);
  await new Promise(resolve => setTimeout(resolve, 0));
  host.querySelectorAll('[data-open-clip]')[0].onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  console.log(JSON.stringify({html: host.innerHTML, keyDisabled: host.element('clip-transform-operation-key').disabled, bpmDisabled: host.element('clip-transform-operation-bpm').disabled}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )

        self.assertTrue(result["keyDisabled"])
        self.assertFalse(result["bpmDisabled"])
        self.assertIn(
            "Key change is unavailable because drum MIDI note numbers select kit pieces",
            result["html"],
        )
        self.assertNotIn("Correct note pitches in a new version", result["html"])

    def test_transform_create_conflict_reloads_once_retains_draft_and_never_retries(self) -> None:
        result = self.run_node(
            """
(async () => {
  const calls = [];
  const host = createDynamicHost();
  let detailReads = 0;
  const api = async (path, options = {}) => {
    calls.push({path, method: options.method || 'GET', body: options.body || null});
    if (path.startsWith('/api/clips?')) return {page: {offset: 0, total: 1, has_more: false}, clips: [{clip_id: 'clip-1', object_sha256: 'a'.repeat(64), title: 'Lead', role: 'lead', key: 'D minor', bpm: 146, revision: 1, note_count: 5, duration_seconds: 5, tags: []}]};
    if (path === '/api/clips/clip-1') {
      detailReads += 1;
      return {library_state_sha256: (detailReads === 1 ? 'b' : 'f').repeat(64), clip: {clip_id: 'clip-1', object_sha256: 'a'.repeat(64), title: 'Lead', role: 'lead', key: 'D minor', bpm: 146, revision: 1, note_count: 5, chord_count: 0, duration: {export_seconds: 5}, timing_contract: {resolved_mode: 'musical', export_bpm: 146}, instrument: {program: 81, channel: 0}}, lineage: {versions: [{clip_id: 'clip-1', title: 'Lead', revision: 1, bpm: 146}]}};
    }
    if (path === '/api/clip-transform-projection') {
      const request = JSON.parse(options.body);
      return {projection: {projection_sha256: 'c'.repeat(64), transform: request.transform, parent: {key: 'D minor', bpm: 146, duration_seconds: 5}, child: {key: 'D minor', bpm: 125, duration_seconds: 5}, diff: {kind: 'bpm', bpm_before: 146, bpm_after: 125, ratio: 0.856, timing_mode: 'stem_locked', beat_positions_changed: true, source_seconds_changed: false}, warnings: [], effects: {library_mutated: false, clip_created: false}}};
    }
    if (path === '/api/clip-transform-action') {
      const error = new Error('stale transform projection');
      error.status = 409;
      throw error;
    }
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml: value => String(value)});
  browser.setCapability(
    {enabled: true, acceptance: {pack_sha256: 'e'.repeat(64)}, library: {clip_count: 1, state_sha256: 'b'.repeat(64)}},
    null,
    {enabled: true, transforms: {same_mode_key: {enabled: true}, bpm: {enabled: true}}, limits: {minimum_bpm: 20, maximum_bpm: 400}},
  );
  browser.renderInto(host);
  await new Promise(resolve => setTimeout(resolve, 0));
  host.querySelectorAll('[data-open-clip]')[0].onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  host.element('clip-transform-operation-bpm').onclick();
  host.element('clip-transform-target-bpm').value = '125';
  host.element('clip-transform-target-bpm').oninput();
  host.element('clip-transform-timing-stem-locked').onclick();
  host.element('clip-transform-form').onsubmit({preventDefault() {}});
  await new Promise(resolve => setTimeout(resolve, 0));
  host.element('clip-transform-create').onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  await new Promise(resolve => setTimeout(resolve, 0));
  console.log(JSON.stringify({calls, detailReads, html: host.innerHTML}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )

        self.assertEqual(result["detailReads"], 2)
        self.assertEqual(
            len([call for call in result["calls"] if call["path"] == "/api/clip-transform-action"]),
            1,
        )
        self.assertEqual(
            len([call for call in result["calls"] if call["path"] == "/api/clip-transform-projection"]),
            1,
        )
        self.assertIn("No automatic retry was made", result["html"])
        self.assertIn("review this retained draft again", result["html"])
        self.assertIn('id="clip-transform-target-bpm" type="number" min="36.5" max="400" step="0.001" inputmode="decimal" value="125"', result["html"])
        self.assertIn('value="stem_locked" checked', result["html"])
        self.assertNotIn("Temporary transform review", result["html"])

    def test_pitch_correction_window_review_create_and_explicit_child_inspection(self) -> None:
        result = self.run_node(
            """
(async () => {
  const calls = [];
  const host = createDynamicHost();
  const parentHash = 'a'.repeat(64);
  const libraryHash = 'b'.repeat(64);
  const windowHash = 'c'.repeat(64);
  const projectionHash = 'd'.repeat(64);
  const childHash = 'e'.repeat(64);
  const intentHash = '4'.repeat(64);
  const childId = `sf-correction-${intentHash}`;
  const firstRef = '1'.repeat(64);
  const secondRef = '2'.repeat(64);
  const contextRef = '3'.repeat(64);
  const effects = {
    library_mutated: false, child_clip_created: false, source_clip_mutated: false,
    correction_applied: false, note_pitch_changed: false, note_timing_changed: false,
    note_count_changed: false, key_changed: false, chords_changed: false,
    instrument_changed: false, provenance_changed: false, reuse_plan_changed: false,
    placement_changed: false, current_arrangement_changed: false, pack_changed: false,
    hybrid_created: false, feedback_recorded: false, data_submitted: false,
  };
  const createdEffects = {...effects, library_mutated: true, child_clip_created: true, correction_applied: true, note_pitch_changed: true};
  const parentDetail = {
    library_state_sha256: libraryHash,
    clip: {clip_id: 'clip-parent', object_sha256: parentHash, title: 'Lead <unsafe>', role: 'lead', key: 'D minor', bpm: 146, revision: 1, note_count: 3, chord_count: 0, pitch_range: {minimum: 60, maximum: 64}, duration: {export_seconds: 6}, timing_contract: {resolved_mode: 'musical', export_bpm: 146}, instrument: {program: 81, channel: 0}},
    lineage: {versions: [{clip_id: 'clip-parent', title: 'Lead', revision: 1, bpm: 146}]},
  };
  const api = async (path, options = {}) => {
    calls.push({path, method: options.method || 'GET', body: options.body || null});
    if (path.startsWith('/api/clips?')) return {page: {offset: 0, total: 1, has_more: false}, clips: [{clip_id: 'clip-parent', object_sha256: parentHash, title: 'Lead', role: 'lead', key: 'D minor', bpm: 146, revision: 1, note_count: 3, duration_seconds: 6, tags: []}]};
    if (path === '/api/clips/clip-parent') return parentDetail;
    if (path === '/api/clip-note-correction-window') return {window: {
      schema: 'sunofriend.workbench-clip-correction-window.v1', operation: 'clip-correction-window',
      window_sha256: windowHash, window: {start_tick: 0, end_tick: 3840, ticks_per_beat: 480, duration_seconds: 3.287, origin: 'recorded-zero'},
      notes: [
        {note_ref: contextRef, editable: false, pitch: 59, velocity: 70, start_tick: 0, end_tick: 120, start_beat: -0.1, duration_beats: 0.35},
        {note_ref: firstRef, editable: true, pitch: 60, velocity: 90, start_tick: 240, end_tick: 720, start_beat: 0.5, duration_beats: 1},
        {note_ref: secondRef, editable: true, pitch: 64, velocity: 88, start_tick: 960, end_tick: 1440, start_beat: 2, duration_beats: 1},
      ],
      effects,
    }};
    if (path === '/api/clip-note-correction-projection') return {projection: {
      schema: 'sunofriend.workbench-clip-correction-preview.v1', status: 'previewed', operation: 'clip-correction-preview',
      intent_sha256: intentHash, projection_sha256: projectionHash, library: {state_sha256: libraryHash},
      window: {start_tick: 0, end_tick: 3840, ticks_per_beat: 480},
      correction: {kind: 'pitch_patch', changes: [{note_ref: firstRef, target_pitch: 61}]},
      parent: {clip_id: 'clip-parent', object_sha256: parentHash, lineage_id: 'lineage-1', revision: 1},
      child: {clip_id: childId, parent_clip_id: 'clip-parent', object_sha256: childHash, lineage_id: 'lineage-1', revision: 2},
      diff: {kind: 'pitch_patch', changed_note_count: 1, changes: [{note_ref: firstRef, before_pitch: 60, after_pitch: 61, semitones: 1}]},
      warnings: [{message: 'Check <img src=x onerror=bad()> against the stem.'}], effects,
    }};
    if (path === '/api/clip-note-correction-action') return {result: {
      schema: 'sunofriend.workbench-clip-correction-result.v1', status: 'created', replayed: false, operation: 'clip-correction-create', projection_sha256: projectionHash,
      window: {start_tick: 0, end_tick: 3840, ticks_per_beat: 480},
      correction: {kind: 'pitch_patch', changes: [{note_ref: firstRef, target_pitch: 61}]},
      parent: {clip_id: 'clip-parent', object_sha256: parentHash, lineage_id: 'lineage-1', revision: 1},
      child: {clip_id: childId, parent_clip_id: 'clip-parent', object_sha256: childHash, lineage_id: 'lineage-1', revision: 2},
      diff: {kind: 'pitch_patch', changed_note_count: 1, changes: [{note_ref: firstRef, before_pitch: 60, after_pitch: 61, semitones: 1}]},
      warnings: [{message: 'Check <img src=x onerror=bad()> against the stem.'}],
      library: {expected_state_sha256: libraryHash, previous_state_sha256: libraryHash, current_state_sha256: 'f'.repeat(64)}, effects: createdEffects,
    }};
    if (path === `/api/clips/${childId}`) return {
      library_state_sha256: 'f'.repeat(64),
      clip: {clip_id: childId, object_sha256: childHash, title: 'Lead correction', role: 'lead', key: 'D minor', bpm: 146, revision: 2, note_count: 3, chord_count: 0, pitch_range: {minimum: 59, maximum: 64}, duration: {export_seconds: 6}, timing_contract: {resolved_mode: 'musical', export_bpm: 146}, instrument: {program: 81, channel: 0}},
      lineage: {versions: [{clip_id: 'clip-parent', title: 'Lead', revision: 1, bpm: 146}, {clip_id: childId, title: 'Lead correction', revision: 2, bpm: 146}]},
      correction_summary: {schema: 'sunofriend.workbench-clip-correction-summary.v1', operation: 'correct_note_pitches', contract_version: 'clip-correction-v1', parent_clip_id: 'clip-parent', parent_object_sha256: parentHash, child_clip_id: childId, child_object_sha256: childHash, window: {start_tick: 0, end_tick: 3840, ticks_per_beat: 480}, changed_note_count: 1, changes: [{note_ref: firstRef, before_pitch: 60, after_pitch: 61}], effects},
    };
    throw new Error(`unexpected ${path}`);
  };
  const escapeHtml = value => String(value ?? '').replace(/[&<>\"']/g, character => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '\"': '&quot;', "'": '&#39;'}[character]));
  const browser = clips.createClipLibrary({api, escapeHtml});
  browser.setCapability(
    {enabled: true, acceptance: {pack_sha256: '9'.repeat(64)}, library: {clip_count: 1, state_sha256: libraryHash}},
    null,
    null,
    {enabled: true, actions: {window: true, preview: true, create: true}, limits: {ticks_per_beat: 480, maximum_window_ticks: 15360, maximum_changes: 64, maximum_pitch_delta_semitones: 24}},
  );
  browser.renderInto(host);
  await new Promise(resolve => setTimeout(resolve, 0));
  host.querySelectorAll('[data-open-clip]')[0].onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  const initialHtml = host.innerHTML;
  host.element('clip-correction-window-form').onsubmit({preventDefault() {}});
  const windowPendingHtml = host.innerHTML;
  await new Promise(resolve => setTimeout(resolve, 0));
  const loadedHtml = host.innerHTML;
  const contextToken = encodeURIComponent(`value:${contextRef}`);
  const firstToken = encodeURIComponent(`value:${firstRef}`);
  const secondToken = encodeURIComponent(`value:${secondRef}`);
  host.data('[data-correction-note-ref]', contextToken).focus();
  const afterContextFocusHtml = host.innerHTML;
  host.data('[data-correction-note-ref]', firstToken).onclick();
  host.data('[data-correction-pitch-delta]', '1').onclick();
  const editedHtml = host.innerHTML;
  host.element('clip-correction-exact-pitch').value = '85';
  host.element('clip-correction-exact-pitch').oninput();
  const boundedHtml = host.innerHTML;
  host.element('clip-correction-exact-pitch').value = '61';
  host.element('clip-correction-exact-pitch').oninput();
  host.element('clip-correction-review').onclick();
  const reviewPendingHtml = host.innerHTML;
  await new Promise(resolve => setTimeout(resolve, 0));
  const reviewedHtml = host.innerHTML;
  const callsBeforeFocus = calls.length;
  host.data('[data-correction-note-ref]', secondToken).focus();
  const focusedOnlyHtml = host.innerHTML;
  const callsAfterFocus = calls.length;
  host.data('[data-correction-note-ref]', secondToken).onclick();
  const navigatedHtml = host.innerHTML;
  const callsAfterNavigation = calls.length;
  host.data('[data-correction-pitch-delta]', '1').onclick();
  const invalidatedHtml = host.innerHTML;
  host.element('clip-correction-reset-note').onclick();
  host.data('[data-correction-note-ref]', firstToken).onclick();
  host.element('clip-correction-review').onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  host.element('clip-correction-create').onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  const createdHtml = host.innerHTML;
  const childReadsBeforeInspect = calls.filter(call => call.path === `/api/clips/${childId}`).length;
  host.element('clip-correction-inspect-child').onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  console.log(JSON.stringify({calls, initialHtml, windowPendingHtml, loadedHtml, afterContextFocusHtml, editedHtml, boundedHtml, reviewPendingHtml, reviewedHtml, focusedOnlyHtml, navigatedHtml, invalidatedHtml, callsBeforeFocus, callsAfterFocus, callsAfterNavigation, createdHtml, childReadsBeforeInspect, childHtml: host.innerHTML}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )

        window_calls = [
            call
            for call in result["calls"]
            if call["path"] == "/api/clip-note-correction-window"
        ]
        projection_calls = [
            call
            for call in result["calls"]
            if call["path"] == "/api/clip-note-correction-projection"
        ]
        action_calls = [
            call
            for call in result["calls"]
            if call["path"] == "/api/clip-note-correction-action"
        ]
        self.assertEqual(len(window_calls), 1)
        self.assertEqual(
            json.loads(window_calls[0]["body"]),
            {
                "parent_clip_id": "clip-parent",
                "parent_object_sha256": "a" * 64,
                "library_state_sha256": "b" * 64,
                "window": {"start_tick": 0, "end_tick": 3840},
            },
        )
        self.assertEqual(len(projection_calls), 2)
        projection_body = json.loads(projection_calls[-1]["body"])
        self.assertEqual(projection_body["window"], {"start_tick": 0, "end_tick": 3840})
        self.assertEqual(projection_body["window_sha256"], "c" * 64)
        self.assertEqual(
            projection_body["correction"],
            {
                "kind": "pitch_patch",
                "changes": [{"note_ref": "1" * 64, "target_pitch": 61}],
            },
        )
        self.assertEqual(len(action_calls), 1)
        action_body = json.loads(action_calls[0]["body"])
        self.assertEqual(action_body["action"], "create")
        self.assertEqual(action_body["projection_sha256"], "d" * 64)
        self.assertNotIn("ticks_per_beat", action_body["window"])
        self.assertIn("Correct note pitches in a new version", result["initialHtml"])
        self.assertIn("No note window is loaded", result["initialHtml"])
        self.assertIn('aria-busy="true"', result["windowPendingHtml"])
        self.assertIn("Loading exact notes", result["windowPendingHtml"])
        self.assertIn("No note selected", result["loadedHtml"])
        self.assertIn("context only", result["loadedHtml"])
        self.assertIn(
            '<ol class="clip-grid" id="clip-correction-note-list"',
            result["loadedHtml"],
        )
        self.assertIn("<li><button", result["loadedHtml"])
        self.assertNotIn('role="listitem"', result["loadedHtml"])
        self.assertIn('id="clip-correction-roll-heading" tabindex="-1"', result["loadedHtml"])
        self.assertIn("No note selected", result["afterContextFocusHtml"])
        self.assertIn("#ffc94a", result["editedHtml"])
        self.assertIn("1 changed note", result["editedHtml"])
        self.assertIn("within 24 semitones", result["boundedHtml"])
        self.assertIn('aria-busy="true"', result["reviewPendingHtml"])
        self.assertIn("Exact temporary pitch review", result["reviewedHtml"])
        self.assertIn("Check &lt;img", result["reviewedHtml"])
        self.assertNotIn("<img src=x", result["reviewedHtml"])
        self.assertEqual(result["callsBeforeFocus"], result["callsAfterFocus"])
        self.assertEqual(result["callsBeforeFocus"], result["callsAfterNavigation"])
        self.assertIn("Exact temporary pitch review", result["focusedOnlyHtml"])
        self.assertIn("Exact temporary pitch review", result["navigatedHtml"])
        self.assertIn(
            "Moving keyboard focus or inspecting another note does not change the draft",
            result["navigatedHtml"],
        )
        self.assertNotIn("Exact temporary pitch review", result["invalidatedHtml"])
        self.assertIn("Temporary pitch draft updated", result["invalidatedHtml"])
        self.assertIn("New pitch-corrected alternative created", result["createdHtml"])
        self.assertEqual(result["childReadsBeforeInspect"], 0)
        self.assertIn("Saved note-pitch correction", result["childHtml"])
        self.assertIn("This immutable Clip is a pitch-corrected child", result["childHtml"])
        self.assertIn("Reading this restored summary has zero effects", result["childHtml"])
        self.assertIn("earlier explicit create appended this child", result["childHtml"])
        self.assertEqual(
            len(
                [
                    call
                    for call in result["calls"]
                    if call["path"].startswith("/api/clips/sf-correction-")
                ]
            ),
            1,
        )
        self.assertFalse(
            any("audition" in call["path"] for call in result["calls"])
        )

    def test_pitch_correction_create_conflict_reloads_detail_and_window_once_without_write_retry(self) -> None:
        result = self.run_node(
            """
(async () => {
  const calls = [];
  const host = createDynamicHost();
  const parentHash = 'a'.repeat(64);
  const firstRef = '1'.repeat(64);
  const replacementRef = '2'.repeat(64);
  const intentHash = '4'.repeat(64);
  const childId = `sf-correction-${intentHash}`;
  const effects = {
    library_mutated: false, child_clip_created: false, source_clip_mutated: false,
    correction_applied: false, note_pitch_changed: false, note_timing_changed: false,
    note_count_changed: false, key_changed: false, chords_changed: false,
    instrument_changed: false, provenance_changed: false, reuse_plan_changed: false,
    placement_changed: false, current_arrangement_changed: false, pack_changed: false,
    hybrid_created: false, feedback_recorded: false, data_submitted: false,
  };
  let detailReads = 0;
  let windowReads = 0;
  const api = async (path, options = {}) => {
    calls.push({path, body: options.body || null});
    if (path.startsWith('/api/clips?')) return {page: {offset: 0, total: 1, has_more: false}, clips: [{clip_id: 'clip-parent', object_sha256: parentHash, title: 'Keys', role: 'keys', key: 'B minor', bpm: 113, revision: 1, note_count: 2, duration_seconds: 6, tags: []}]};
    if (path === '/api/clips/clip-parent') {
      detailReads += 1;
      return {library_state_sha256: (detailReads === 1 ? 'b' : 'f').repeat(64), clip: {clip_id: 'clip-parent', object_sha256: parentHash, title: 'Keys', role: 'keys', key: 'B minor', bpm: 113, revision: 1, note_count: 2, chord_count: 0, duration: {export_seconds: 6}, timing_contract: {resolved_mode: 'musical', export_bpm: 113}, instrument: {program: 4, channel: 0}}, lineage: {versions: [{clip_id: 'clip-parent', title: 'Keys', revision: 1, bpm: 113}]}};
    }
    if (path === '/api/clip-note-correction-window') {
      windowReads += 1;
      const noteRef = windowReads === 1 ? firstRef : replacementRef;
      return {window: {window_sha256: (windowReads === 1 ? 'c' : '9').repeat(64), window: {start_tick: 0, end_tick: 3840, ticks_per_beat: 480}, notes: [{note_ref: noteRef, editable: true, pitch: windowReads === 1 ? 60 : 67, velocity: 90, start_tick: 240, end_tick: 720, start_beat: 0.5, duration_beats: 1}], effects}};
    }
    if (path === '/api/clip-note-correction-projection') return {projection: {schema: 'sunofriend.workbench-clip-correction-preview.v1', status: 'previewed', operation: 'clip-correction-preview', intent_sha256: intentHash, projection_sha256: 'd'.repeat(64), library: {state_sha256: 'b'.repeat(64)}, window: {start_tick: 0, end_tick: 3840, ticks_per_beat: 480}, correction: {kind: 'pitch_patch', changes: [{note_ref: firstRef, target_pitch: 61}]}, parent: {clip_id: 'clip-parent', object_sha256: parentHash, lineage_id: 'lineage-1', revision: 1}, child: {clip_id: childId, parent_clip_id: 'clip-parent', object_sha256: 'e'.repeat(64), lineage_id: 'lineage-1', revision: 2}, diff: {kind: 'pitch_patch', changed_note_count: 1, changes: [{note_ref: firstRef, before_pitch: 60, after_pitch: 61, semitones: 1}]}, warnings: [], effects}};
    if (path === '/api/clip-note-correction-action') {
      const error = new Error('stale correction evidence');
      error.status = 409;
      throw error;
    }
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml: value => String(value)});
  browser.setCapability(
    {enabled: true, acceptance: {pack_sha256: '8'.repeat(64)}, library: {clip_count: 1, state_sha256: 'b'.repeat(64)}},
    null,
    null,
    {enabled: true, actions: {window: true, preview: true, create: true}, limits: {ticks_per_beat: 480, maximum_changes: 64, maximum_pitch_delta_semitones: 24}},
  );
  browser.renderInto(host);
  await new Promise(resolve => setTimeout(resolve, 0));
  host.querySelectorAll('[data-open-clip]')[0].onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  host.element('clip-correction-window-form').onsubmit({preventDefault() {}});
  await new Promise(resolve => setTimeout(resolve, 0));
  host.data('[data-correction-note-ref]', encodeURIComponent(`value:${firstRef}`)).onclick();
  host.data('[data-correction-pitch-delta]', '1').onclick();
  host.element('clip-correction-review').onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  host.element('clip-correction-create').onclick();
  await new Promise(resolve => setTimeout(resolve, 0));
  await new Promise(resolve => setTimeout(resolve, 0));
  await new Promise(resolve => setTimeout(resolve, 0));
  console.log(JSON.stringify({calls, detailReads, windowReads, html: host.innerHTML}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )

        self.assertEqual(result["detailReads"], 2)
        self.assertEqual(result["windowReads"], 2)
        self.assertEqual(
            len(
                [
                    call
                    for call in result["calls"]
                    if call["path"] == "/api/clip-note-correction-projection"
                ]
            ),
            1,
        )
        self.assertEqual(
            len(
                [
                    call
                    for call in result["calls"]
                    if call["path"] == "/api/clip-note-correction-action"
                ]
            ),
            1,
        )
        second_window = json.loads(
            [
                call
                for call in result["calls"]
                if call["path"] == "/api/clip-note-correction-window"
            ][1]["body"]
        )
        self.assertEqual(second_window["library_state_sha256"], "f" * 64)
        self.assertEqual(second_window["window"], {"start_tick": 0, "end_tick": 3840})
        self.assertIn("No write retry was made", result["html"])
        self.assertIn("Review 0 pitch changes", result["html"])
        self.assertIn("No note selected", result["html"])
        self.assertNotIn("#ffc94a", result["html"])
        self.assertNotIn("Exact temporary pitch review", result["html"])


if __name__ == "__main__":
    unittest.main()
