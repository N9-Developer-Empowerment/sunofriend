from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


CLIPS_PATH = Path("src/sunofriend/workbench_clips.js").resolve()


class WorkbenchVelocityUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.node = shutil.which("node")
        if not cls.node:
            raise unittest.SkipTest("Node.js is not installed")

    def run_node(self, body: str) -> dict[str, object]:
        script = rf"""
const clips = require({json.dumps(str(CLIPS_PATH))});
const pause = () => new Promise(resolve => setTimeout(resolve, 0));
function click(element) {{
  if (element && !element.disabled && typeof element.onclick === 'function') element.onclick();
}}
function submit(element) {{
  if (element && !element.disabled && typeof element.onsubmit === 'function') element.onsubmit({{preventDefault() {{}}}});
}}
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
      elements.set(id, {{
        id,
        value: tag.match(/value="([^"]*)"/)?.[1] || '',
        disabled: /\sdisabled(?:\s|>|=)/.test(tag),
        checked: /\schecked(?:\s|>|=)/.test(tag),
        textContent: id,
        isConnected: true,
        onclick: null,
        oninput: null,
        onsubmit: null,
        pause() {{}},
        focus() {{ this.focused = true; if (this.onfocus) this.onfocus(); }},
      }});
    }}
    return elements.get(id);
  }}
  const datasetSelectors = {{
    '[data-open-clip]': ['openClip', 'data-open-clip'],
    '[data-lineage-clip]': ['lineageClip', 'data-lineage-clip'],
    '[data-correction-note-ref]': ['correctionNoteRef', 'data-correction-note-ref'],
    '[data-correction-note-svg]': ['correctionNoteSvg', 'data-correction-note-svg'],
    '[data-correction-pitch-delta]': ['correctionPitchDelta', 'data-correction-pitch-delta'],
    '[data-correction-velocity-delta]': ['correctionVelocityDelta', 'data-correction-velocity-delta'],
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
      const pattern = new RegExp(`<[^>]+${{attribute}}="([^"]+)"[^>]*>`, 'g');
      const result = [];
      for (const match of html.matchAll(pattern)) {{
        const key = `${{selector}}:${{match[1]}}`;
        if (!dataElements.has(key)) dataElements.set(key, {{
          dataset: {{[datasetKey]: match[1]}},
          disabled: /\sdisabled(?:\s|>|=)/.test(match[0]),
          onclick: null,
          onfocus: null,
          focus() {{ this.focused = true; if (this.onfocus) this.onfocus(); }},
        }});
        result.push(dataElements.get(key));
      }}
      return result;
    }},
    element(id) {{ return elementForId(id); }},
    data(selector, value) {{ return dataElements.get(`${{selector}}:${{value}}`); }},
  }};
}}
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({{'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}}[character]));
const pitchEffectKeys = [
  'child_clip_created', 'chords_changed', 'correction_applied',
  'current_arrangement_changed', 'data_submitted', 'feedback_recorded',
  'hybrid_created', 'instrument_changed', 'key_changed', 'library_mutated',
  'note_count_changed', 'note_pitch_changed', 'note_timing_changed',
  'pack_changed', 'placement_changed', 'provenance_changed',
  'reuse_plan_changed', 'source_clip_mutated',
];
const velocityEffectKeys = [
  'child_clip_created', 'chords_changed', 'correction_applied',
  'current_arrangement_changed', 'data_submitted', 'feedback_recorded',
  'hybrid_created', 'instrument_changed', 'key_changed', 'library_mutated',
  'note_attack_velocity_changed', 'note_count_changed', 'note_pitch_changed',
  'note_timing_changed', 'pack_changed', 'placement_changed',
  'provenance_changed', 'release_velocity_changed', 'reuse_plan_changed',
  'source_clip_mutated',
];
const pitchEffects = Object.fromEntries(pitchEffectKeys.map(key => [key, false]));
const effects = Object.fromEntries(velocityEffectKeys.map(key => [key, false]));
const velocityCapability = {{
  enabled: true,
  actions: {{window: true, preview: true, create: true}},
  corrections: {{
    pitch_patch: {{enabled: true, drum_family: false}},
    attack_velocity_patch: {{enabled: true, drum_family: true}},
  }},
  limits: {{ticks_per_beat: 480, maximum_window_ticks: 15360, maximum_changes: 64, maximum_pitch_delta_semitones: 24, minimum_attack_velocity: 1, maximum_attack_velocity: 127}},
}};
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

    def test_pitched_clip_defaults_to_pitch_and_kind_switch_requires_reset(self) -> None:
        result = self.run_node(
            """
(async () => {
  const calls = [];
  const host = createDynamicHost();
  const parentHash = 'a'.repeat(64);
  const libraryHash = 'b'.repeat(64);
  const windowHash = 'c'.repeat(64);
  const projectionHash = 'd'.repeat(64);
  const intentHash = '4'.repeat(64);
  const childId = `sf-correction-${intentHash}`;
  const noteRef = '1'.repeat(64);
  const api = async (path, options = {}) => {
    calls.push({path, body: options.body || null});
    if (path.startsWith('/api/clips?')) return {page: {offset: 0, total: 1, has_more: false}, clips: [{clip_id: 'keys', object_sha256: parentHash, title: 'Keys', role: 'keys', key: 'B minor', bpm: 113, revision: 1, note_count: 1, duration_seconds: 4, tags: []}]};
    if (path === '/api/clips/keys') return {library_state_sha256: libraryHash, clip: {clip_id: 'keys', object_sha256: parentHash, title: 'Keys', role: 'keys', key: 'B minor', bpm: 113, revision: 1, note_count: 1, chord_count: 0, pitch_range: {minimum: 60, maximum: 60}, duration: {export_seconds: 4}, timing_contract: {resolved_mode: 'musical', export_bpm: 113}, instrument: {program: 4, channel: 0}}, lineage: {versions: []}};
    if (path === '/api/clip-note-correction-window') return {window: {window_sha256: windowHash, window: {start_tick: 0, end_tick: 3840, ticks_per_beat: 480}, notes: [{note_ref: noteRef, editable: true, edit_block_reason: null, pitch: 60, velocity: 90, start_tick: 0, end_tick: 480, start_beat: 0, duration_beats: 1}], effects}};
    if (path === '/api/clip-note-correction-projection') return {projection: {schema: 'sunofriend.workbench-clip-correction-preview.v1', status: 'previewed', operation: 'clip-correction-preview', intent_sha256: intentHash, projection_sha256: projectionHash, library: {state_sha256: libraryHash}, window: {start_tick: 0, end_tick: 3840, ticks_per_beat: 480}, correction: {kind: 'pitch_patch', changes: [{note_ref: noteRef, target_pitch: 61}]}, parent: {clip_id: 'keys', object_sha256: parentHash, lineage_id: 'lineage-1', revision: 1}, child: {clip_id: childId, parent_clip_id: 'keys', object_sha256: 'e'.repeat(64), lineage_id: 'lineage-1', revision: 2}, diff: {kind: 'pitch_patch', changed_note_count: 1, changes: [{note_ref: noteRef, before_pitch: 60, after_pitch: 61, semitones: 1}]}, warnings: [], effects: pitchEffects}};
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml});
  browser.setCapability({enabled: true, acceptance: {pack_sha256: '9'.repeat(64)}, library: {clip_count: 1, state_sha256: libraryHash}}, null, null, velocityCapability);
  browser.renderInto(host);
  await pause();
  click(host.querySelectorAll('[data-open-clip]')[0]);
  await pause();
  const initialHtml = host.innerHTML;
  const initialPitchChecked = host.element('clip-correction-kind-pitch')?.checked;
  const initialVelocityChecked = host.element('clip-correction-kind-velocity')?.checked;
  submit(host.element('clip-correction-window-form'));
  await pause();
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${noteRef}`)));
  click(host.data('[data-correction-pitch-delta]', '1'));
  const velocityDisabledWithDraft = host.element('clip-correction-kind-velocity')?.disabled;
  click(host.element('clip-correction-kind-velocity'));
  click(host.element('clip-correction-review'));
  await pause();
  const reviewedHtml = host.innerHTML;
  click(host.element('clip-correction-reset-all'));
  const velocityUnlocked = !host.element('clip-correction-kind-velocity')?.disabled;
  click(host.element('clip-correction-kind-velocity'));
  const switchedHtml = host.innerHTML;
  console.log(JSON.stringify({calls, initialHtml, initialPitchChecked, initialVelocityChecked, velocityDisabledWithDraft, velocityUnlocked, reviewedHtml, switchedHtml}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )

        windows = [call for call in result["calls"] if call["path"] == "/api/clip-note-correction-window"]
        previews = [call for call in result["calls"] if call["path"] == "/api/clip-note-correction-projection"]
        self.assertTrue(result["initialPitchChecked"])
        self.assertFalse(result["initialVelocityChecked"])
        self.assertIn("Choose exactly one correction kind", result["initialHtml"])
        self.assertTrue(result["velocityDisabledWithDraft"])
        self.assertTrue(result["velocityUnlocked"])
        self.assertNotIn("correction_kind", json.loads(windows[0]["body"]))
        self.assertEqual(
            json.loads(previews[0]["body"])["correction"],
            {"kind": "pitch_patch", "changes": [{"note_ref": "1" * 64, "target_pitch": 61}]},
        )
        self.assertIn("Exact temporary pitch review", result["reviewedHtml"])
        self.assertIn("Correct note attack velocities", result["switchedHtml"])
        self.assertIn("No note window is loaded", result["switchedHtml"])

    def test_drum_velocity_bounds_typing_and_duplicate_note_block(self) -> None:
        result = self.run_node(
            """
(async () => {
  const calls = [];
  const host = createDynamicHost();
  const parentHash = 'a'.repeat(64);
  const libraryHash = 'b'.repeat(64);
  const windowHash = 'c'.repeat(64);
  const firstRef = '1'.repeat(64);
  const secondRef = '2'.repeat(64);
  const blockedRef = '3'.repeat(64);
  const intentHash = '4'.repeat(64);
  const api = async (path, options = {}) => {
    calls.push({path, body: options.body || null});
    if (path.startsWith('/api/clips?')) return {page: {offset: 0, total: 1, has_more: false}, clips: [{clip_id: 'kick', object_sha256: parentHash, title: 'Kick', role: 'kick', key: '', bpm: 113, revision: 1, note_count: 3, duration_seconds: 4, tags: []}]};
    if (path === '/api/clips/kick') return {library_state_sha256: libraryHash, clip: {clip_id: 'kick', object_sha256: parentHash, title: 'Kick', role: 'kick', key: '', bpm: 113, revision: 1, note_count: 3, chord_count: 0, pitch_range: {minimum: 36, maximum: 36}, duration: {export_seconds: 4}, timing_contract: {resolved_mode: 'musical', export_bpm: 113}, instrument: {program: 0, channel: 9, is_drums: true}}, lineage: {versions: []}};
    if (path === '/api/clip-note-correction-window') return {window: {window_sha256: windowHash, correction_kind: 'attack_velocity_patch', window: {start_tick: 0, end_tick: 3840, ticks_per_beat: 480}, notes: [
      {note_ref: firstRef, editable: true, edit_block_reason: null, pitch: 36, velocity: 90, start_tick: 0, end_tick: 120, start_beat: 0, duration_beats: .25},
      {note_ref: secondRef, editable: true, edit_block_reason: null, pitch: 36, velocity: 64, start_tick: 480, end_tick: 600, start_beat: 1, duration_beats: .25},
      {note_ref: blockedRef, editable: false, edit_block_reason: 'duplicate-export-note-on', export_note_on_group_size: 2, pitch: 36, velocity: 80, start_tick: 960, end_tick: 1080, start_beat: 2, duration_beats: .25},
    ], effects}};
    if (path === '/api/clip-note-correction-projection') return {projection: {schema: 'sunofriend.workbench-clip-attack-velocity-preview.v1', status: 'previewed', operation: 'clip-attack-velocity-correction-preview', intent_sha256: intentHash, projection_sha256: 'd'.repeat(64), library: {state_sha256: libraryHash}, window: {start_tick: 0, end_tick: 3840, ticks_per_beat: 480}, correction: {kind: 'attack_velocity_patch', changes: [{note_ref: firstRef, target_velocity: 1}, {note_ref: secondRef, target_velocity: 127}]}, parent: {clip_id: 'kick', object_sha256: parentHash, lineage_id: 'lineage-1', revision: 1}, child: {clip_id: `sf-correction-${intentHash}`, parent_clip_id: 'kick', object_sha256: 'e'.repeat(64), lineage_id: 'lineage-1', revision: 2}, diff: {kind: 'attack_velocity_patch', changed_note_count: 2, changes: [
      {note_ref: firstRef, channel: 9, start_tick: 0, end_tick: 120, start_beat: 0, duration_beats: .25, pitch: 36, before_velocity: 90, after_velocity: 1, velocity_delta: -89},
      {note_ref: secondRef, channel: 9, start_tick: 480, end_tick: 600, start_beat: 1, duration_beats: .25, pitch: 36, before_velocity: 64, after_velocity: 127, velocity_delta: 63},
    ]}, warnings: [], effects}};
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml});
  browser.setCapability({enabled: true, acceptance: {pack_sha256: '9'.repeat(64)}, library: {clip_count: 1, state_sha256: libraryHash}}, null, null, velocityCapability);
  browser.renderInto(host);
  await pause();
  click(host.querySelectorAll('[data-open-clip]')[0]);
  await pause();
  const initialHtml = host.innerHTML;
  const velocityChecked = host.element('clip-correction-kind-velocity')?.checked;
  const pitchPresent = !!host.element('clip-correction-kind-pitch');
  submit(host.element('clip-correction-window-form'));
  await pause();
  const loadedHtml = host.innerHTML;
  const blockedToken = encodeURIComponent(`value:${blockedRef}`);
  const blockedDisabled = host.data('[data-correction-note-ref]', blockedToken)?.disabled;
  click(host.data('[data-correction-note-ref]', blockedToken));
  const afterBlockedHtml = host.innerHTML;
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${firstRef}`)));
  const callsBeforeTyping = calls.length;
  host.element('clip-correction-exact-velocity').value = '72';
  if (host.element('clip-correction-exact-velocity').oninput) host.element('clip-correction-exact-velocity').oninput();
  const callsAfterTyping = calls.length;
  const typedHtml = host.innerHTML;
  const invalidMessages = [];
  for (const value of ['0', '128', '1.5']) {
    host.element('clip-correction-exact-velocity').value = value;
    submit(host.element('clip-correction-velocity-form'));
    invalidMessages.push(host.innerHTML);
  }
  host.element('clip-correction-exact-velocity').value = '1';
  submit(host.element('clip-correction-velocity-form'));
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${secondRef}`)));
  host.element('clip-correction-exact-velocity').value = '127';
  submit(host.element('clip-correction-velocity-form'));
  const draftedHtml = host.innerHTML;
  click(host.element('clip-correction-review'));
  await pause();
  console.log(JSON.stringify({calls, initialHtml, velocityChecked, pitchPresent, loadedHtml, blockedDisabled, afterBlockedHtml, callsBeforeTyping, callsAfterTyping, typedHtml, invalidMessages, draftedHtml}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )

        windows = [call for call in result["calls"] if call["path"] == "/api/clip-note-correction-window"]
        previews = [call for call in result["calls"] if call["path"] == "/api/clip-note-correction-projection"]
        self.assertTrue(result["velocityChecked"])
        self.assertFalse(result["pitchPresent"])
        self.assertIn("Correct note attack velocities", result["initialHtml"])
        self.assertIn('data-correction-velocity-delta="-10"', result["loadedHtml"])
        self.assertIn('data-correction-velocity-delta="10"', result["loadedHtml"])
        self.assertIn("Typing alone does not edit the draft", result["loadedHtml"])
        self.assertTrue(result["blockedDisabled"])
        self.assertIn("blocked: duplicate exported Note On", result["loadedHtml"])
        self.assertIn("No note selected", result["afterBlockedHtml"])
        self.assertEqual(result["callsBeforeTyping"], result["callsAfterTyping"])
        self.assertNotIn("draft attack 72", result["typedHtml"])
        for html in result["invalidMessages"]:
            self.assertIn("whole number from 1 to 127", html)
            self.assertIn("not clamped", html)
        self.assertIn("draft attack 1", result["draftedHtml"])
        self.assertIn("draft attack 127", result["draftedHtml"])
        self.assertEqual(
            json.loads(windows[0]["body"])["correction_kind"],
            "attack_velocity_patch",
        )
        preview = json.loads(previews[0]["body"])
        self.assertNotIn("correction_kind", preview)
        self.assertEqual(
            preview["correction"],
            {
                "kind": "attack_velocity_patch",
                "changes": [
                    {"note_ref": "1" * 64, "target_velocity": 1},
                    {"note_ref": "2" * 64, "target_velocity": 127},
                ],
            },
        )
        self.assertNotIn("target_pitch", json.dumps(preview))

    def test_velocity_review_create_inspect_and_restored_summary(self) -> None:
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
  const noteRef = '1'.repeat(64);
  const otherRef = '2'.repeat(64);
  const windowDocument = {window_sha256: windowHash, correction_kind: 'attack_velocity_patch', window: {start_tick: 0, end_tick: 3840, ticks_per_beat: 480}, notes: [
    {note_ref: noteRef, editable: true, edit_block_reason: null, pitch: 36, velocity: 90, start_tick: 0, end_tick: 120, start_beat: 0, duration_beats: .25},
    {note_ref: otherRef, editable: true, edit_block_reason: null, pitch: 38, velocity: 64, start_tick: 480, end_tick: 600, start_beat: 1, duration_beats: .25},
  ], effects};
  const velocityChange = {note_ref: noteRef, channel: 9, start_tick: 0, end_tick: 120, start_beat: 0, duration_beats: .25, pitch: 36, before_velocity: 90, after_velocity: 72, velocity_delta: -18};
  const projection = {schema: 'sunofriend.workbench-clip-attack-velocity-preview.v1', status: 'previewed', operation: 'clip-attack-velocity-correction-preview', intent_sha256: intentHash, projection_sha256: projectionHash, library: {state_sha256: libraryHash}, window: {start_tick: 0, end_tick: 3840, ticks_per_beat: 480}, correction: {kind: 'attack_velocity_patch', changes: [{note_ref: noteRef, target_velocity: 72}]}, parent: {clip_id: 'kick', object_sha256: parentHash, lineage_id: 'lineage-1', revision: 1}, child: {clip_id: childId, parent_clip_id: 'kick', object_sha256: childHash, lineage_id: 'lineage-1', revision: 2}, diff: {kind: 'attack_velocity_patch', changed_note_count: 1, changes: [velocityChange]}, warnings: ['Check <img src=x onerror=bad()> & compare patch.'], effects};
  const createdEffects = {...effects, library_mutated: true, child_clip_created: true, correction_applied: true, note_attack_velocity_changed: true};
  const parentDetail = {library_state_sha256: libraryHash, clip: {clip_id: 'kick', object_sha256: parentHash, title: 'Kick', role: 'kick', key: '', bpm: 113, revision: 1, note_count: 2, chord_count: 0, pitch_range: {minimum: 36, maximum: 38}, duration: {export_seconds: 4}, timing_contract: {resolved_mode: 'musical', export_bpm: 113}, instrument: {program: 0, channel: 9, is_drums: true}}, lineage: {versions: []}};
  const api = async (path, options = {}) => {
    calls.push({path, body: options.body || null});
    if (path.startsWith('/api/clips?')) return {page: {offset: 0, total: 1, has_more: false}, clips: [{clip_id: 'kick', object_sha256: parentHash, title: 'Kick', role: 'kick', key: '', bpm: 113, revision: 1, note_count: 2, duration_seconds: 4, tags: []}]};
    if (path === '/api/clips/kick') return parentDetail;
    if (path === '/api/clip-note-correction-window') return {window: windowDocument};
    if (path === '/api/clip-note-correction-projection') return {projection};
    if (path === '/api/clip-note-correction-action') return {result: {schema: 'sunofriend.workbench-clip-attack-velocity-result.v1', status: 'created', replayed: false, operation: 'clip-attack-velocity-correction-create', projection_sha256: projectionHash, window: projection.window, correction: projection.correction, parent: projection.parent, child: projection.child, diff: projection.diff, warnings: projection.warnings, library: {expected_state_sha256: libraryHash, previous_state_sha256: libraryHash, current_state_sha256: 'f'.repeat(64)}, effects: createdEffects}};
    if (path === `/api/clips/${childId}`) return {library_state_sha256: 'f'.repeat(64), clip: {clip_id: childId, object_sha256: childHash, title: 'Kick velocity correction', role: 'kick', key: '', bpm: 113, revision: 2, note_count: 2, chord_count: 0, pitch_range: {minimum: 36, maximum: 38}, duration: {export_seconds: 4}, timing_contract: {resolved_mode: 'musical', export_bpm: 113}, instrument: {program: 0, channel: 9, is_drums: true}}, lineage: {versions: []}, correction_summary: {schema: 'sunofriend.workbench-clip-attack-velocity-summary.v1', operation: 'correct_note_attack_velocities', contract_version: 1, parent_clip_id: 'kick', parent_object_sha256: parentHash, child_clip_id: childId, child_object_sha256: childHash, window: {start_tick: 0, end_tick: 3840, ticks_per_beat: 480}, changed_note_count: 1, changes: [velocityChange], effects}};
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml});
  browser.setCapability({enabled: true, acceptance: {pack_sha256: '9'.repeat(64)}, library: {clip_count: 1, state_sha256: libraryHash}}, null, null, velocityCapability);
  browser.renderInto(host);
  await pause();
  click(host.querySelectorAll('[data-open-clip]')[0]);
  await pause();
  submit(host.element('clip-correction-window-form'));
  await pause();
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${noteRef}`)));
  host.element('clip-correction-exact-velocity').value = '72';
  submit(host.element('clip-correction-velocity-form'));
  click(host.element('clip-correction-review'));
  await pause();
  const reviewedHtml = host.innerHTML;
  const callsBeforeNoop = calls.length;
  host.element('clip-correction-exact-velocity').value = '72';
  submit(host.element('clip-correction-velocity-form'));
  const sameDraftHtml = host.innerHTML;
  const callsAfterSameDraft = calls.length;
  host.data('[data-correction-note-ref]', encodeURIComponent(`value:${otherRef}`)).focus();
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${otherRef}`)));
  host.element('clip-correction-exact-velocity').value = '64';
  submit(host.element('clip-correction-velocity-form'));
  const sourceNoopHtml = host.innerHTML;
  const callsAfterSourceNoop = calls.length;
  const navigatedHtml = host.innerHTML;
  click(host.data('[data-correction-velocity-delta]', '1'));
  const invalidatedHtml = host.innerHTML;
  click(host.element('clip-correction-reset-note'));
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${noteRef}`)));
  click(host.element('clip-correction-review'));
  await pause();
  click(host.element('clip-correction-create'));
  await pause();
  const createdHtml = host.innerHTML;
  const childReadsBeforeInspect = calls.filter(call => call.path === `/api/clips/${childId}`).length;
  const artifactCallsBeforeInspect = calls.filter(call => call.path === '/api/clip-artifact').length;
  click(host.element('clip-correction-inspect-child'));
  await pause();
  console.log(JSON.stringify({calls, reviewedHtml, sameDraftHtml, sourceNoopHtml, navigatedHtml, invalidatedHtml, callsBeforeNoop, callsAfterSameDraft, callsAfterSourceNoop, createdHtml, childReadsBeforeInspect, artifactCallsBeforeInspect, childHtml: host.innerHTML}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )

        previews = [call for call in result["calls"] if call["path"] == "/api/clip-note-correction-projection"]
        actions = [call for call in result["calls"] if call["path"] == "/api/clip-note-correction-action"]
        self.assertIn("Exact temporary attack-velocity review", result["reviewedHtml"])
        self.assertIn("90 → 72", result["reviewedHtml"])
        self.assertIn("−18 · lower", result["reviewedHtml"])
        self.assertIn("pitch / beat context", result["reviewedHtml"].lower())
        self.assertIn("not dB or track volume", result["reviewedHtml"])
        self.assertIn("different sample layer", result["reviewedHtml"])
        self.assertIn("&lt;img", result["reviewedHtml"])
        self.assertIn("&amp; compare", result["reviewedHtml"])
        self.assertNotIn("<img src=x", result["reviewedHtml"])
        self.assertEqual(result["callsBeforeNoop"], result["callsAfterSameDraft"])
        self.assertEqual(result["callsBeforeNoop"], result["callsAfterSourceNoop"])
        self.assertIn("Exact temporary attack-velocity review", result["sameDraftHtml"])
        self.assertIn("already the current draft value", result["sameDraftHtml"])
        self.assertIn("Exact temporary attack-velocity review", result["sourceNoopHtml"])
        self.assertIn("already the current draft value", result["sourceNoopHtml"])
        self.assertIn("Exact temporary attack-velocity review", result["navigatedHtml"])
        self.assertNotIn("Exact temporary attack-velocity review", result["invalidatedHtml"])
        self.assertIn("Temporary attack-velocity draft updated", result["invalidatedHtml"])
        self.assertEqual(len(previews), 2)
        preview_body = json.loads(previews[-1]["body"])
        action_body = json.loads(actions[0]["body"])
        self.assertEqual(action_body["correction"], preview_body["correction"])
        self.assertEqual(action_body["action"], "create")
        self.assertEqual(action_body["projection_sha256"], "d" * 64)
        self.assertEqual(result["childReadsBeforeInspect"], 0)
        self.assertEqual(result["artifactCallsBeforeInspect"], 0)
        self.assertIn("New attack-velocity-corrected alternative created", result["createdHtml"])
        self.assertIn("not preferred, ranked, selected, placed, auditioned", result["createdHtml"])
        self.assertIn("Saved note attack-velocity correction", result["childHtml"])
        self.assertIn("90 → 72 (−18 · lower)", result["childHtml"])
        self.assertIn("not dB or track volume", result["childHtml"])
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
        self.assertEqual(
            len([call for call in result["calls"] if call["path"] == "/api/clip-artifact"]),
            0,
        )

    def test_velocity_rejects_mismatched_evidence_then_accepts_exact_replay(self) -> None:
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
  const currentHash = 'f'.repeat(64);
  const intentHash = '4'.repeat(64);
  const childId = `sf-correction-${intentHash}`;
  const noteRef = '1'.repeat(64);
  let previewCount = 0;
  let actionCount = 0;
  const change = {note_ref: noteRef, channel: 9, start_tick: 0, end_tick: 120, start_beat: 0, duration_beats: .25, pitch: 36, before_velocity: 90, after_velocity: 72, velocity_delta: -18};
  const projection = {
    schema: 'sunofriend.workbench-clip-attack-velocity-preview.v1', status: 'previewed', operation: 'clip-attack-velocity-correction-preview',
    intent_sha256: intentHash, projection_sha256: projectionHash,
    library: {state_sha256: libraryHash}, window: {start_tick: 0, end_tick: 3840, ticks_per_beat: 480},
    correction: {kind: 'attack_velocity_patch', changes: [{note_ref: noteRef, target_velocity: 72}]},
    parent: {clip_id: 'kick', object_sha256: parentHash, lineage_id: 'lineage-1', revision: 1},
    child: {clip_id: childId, parent_clip_id: 'kick', object_sha256: childHash, lineage_id: 'lineage-1', revision: 2},
    diff: {kind: 'attack_velocity_patch', changed_note_count: 1, changes: [change]}, warnings: [], effects,
  };
  const api = async (path, options = {}) => {
    calls.push({path, body: options.body || null});
    if (path.startsWith('/api/clips?')) return {page: {offset: 0, total: 1, has_more: false}, clips: [{clip_id: 'kick', object_sha256: parentHash, title: 'Kick', role: 'kick', key: '', bpm: 113, revision: 1, note_count: 1, duration_seconds: 4, tags: []}]};
    if (path === '/api/clips/kick') return {library_state_sha256: libraryHash, clip: {clip_id: 'kick', object_sha256: parentHash, title: 'Kick', role: 'kick', key: '', bpm: 113, revision: 1, note_count: 1, chord_count: 0, pitch_range: {minimum: 36, maximum: 36}, duration: {export_seconds: 4}, timing_contract: {resolved_mode: 'musical', export_bpm: 113}, instrument: {program: 0, channel: 9, is_drums: true}}, lineage: {versions: []}};
    if (path === '/api/clip-note-correction-window') return {window: {window_sha256: windowHash, correction_kind: 'attack_velocity_patch', window: {start_tick: 0, end_tick: 3840, ticks_per_beat: 480}, notes: [{note_ref: noteRef, editable: true, edit_block_reason: null, pitch: 36, velocity: 90, start_tick: 0, end_tick: 120, start_beat: 0, duration_beats: .25}], effects}};
    if (path === '/api/clip-note-correction-projection') {
      previewCount += 1;
      return {projection: previewCount === 1 ? {...projection, diff: {...projection.diff, changes: []}} : projection};
    }
    if (path === '/api/clip-note-correction-action') {
      actionCount += 1;
      const base = {schema: 'sunofriend.workbench-clip-attack-velocity-result.v1', status: actionCount === 1 ? 'created' : 'replayed', replayed: actionCount !== 1, operation: 'clip-attack-velocity-correction-create', projection_sha256: projectionHash, window: projection.window, correction: projection.correction, parent: projection.parent, child: projection.child, diff: projection.diff, warnings: projection.warnings, library: {expected_state_sha256: libraryHash, previous_state_sha256: actionCount === 1 ? libraryHash : currentHash, current_state_sha256: currentHash}, effects};
      return {result: base};
    }
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml});
  browser.setCapability({enabled: true, acceptance: {pack_sha256: '9'.repeat(64)}, library: {clip_count: 1, state_sha256: libraryHash}}, null, null, velocityCapability);
  browser.renderInto(host);
  await pause();
  click(host.querySelectorAll('[data-open-clip]')[0]);
  await pause();
  submit(host.element('clip-correction-window-form'));
  await pause();
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${noteRef}`)));
  host.element('clip-correction-exact-velocity').value = '72';
  submit(host.element('clip-correction-velocity-form'));
  click(host.element('clip-correction-review'));
  await pause();
  const rejectedProjectionHtml = host.innerHTML;
  click(host.element('clip-correction-review'));
  await pause();
  const acceptedProjectionHtml = host.innerHTML;
  click(host.element('clip-correction-create'));
  await pause();
  const rejectedCreatedHtml = host.innerHTML;
  click(host.element('clip-correction-create'));
  await pause();
  const acceptedReplayHtml = host.innerHTML;
  console.log(JSON.stringify({calls, rejectedProjectionHtml, acceptedProjectionHtml, rejectedCreatedHtml, acceptedReplayHtml}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )

        previews = [
            call
            for call in result["calls"]
            if call["path"] == "/api/clip-note-correction-projection"
        ]
        actions = [
            call
            for call in result["calls"]
            if call["path"] == "/api/clip-note-correction-action"
        ]
        self.assertEqual(len(previews), 2)
        self.assertEqual(len(actions), 2)
        self.assertIn("invalid or mismatched zero-effect", result["rejectedProjectionHtml"])
        self.assertNotIn("Exact temporary attack-velocity review", result["rejectedProjectionHtml"])
        self.assertIn("Exact temporary attack-velocity review", result["acceptedProjectionHtml"])
        self.assertIn("invalid or mismatched immutable", result["rejectedCreatedHtml"])
        self.assertNotIn("New attack-velocity-corrected alternative", result["rejectedCreatedHtml"])
        self.assertIn("Existing attack-velocity-corrected alternative verified", result["acceptedReplayHtml"])
        self.assertIn("appended nothing", result["acceptedReplayHtml"])
        self.assertEqual(
            json.loads(actions[0]["body"])["correction"],
            json.loads(actions[1]["body"])["correction"],
        )


if __name__ == "__main__":
    unittest.main()
