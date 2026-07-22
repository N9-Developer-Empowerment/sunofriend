from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


CLIPS_PATH = Path("src/sunofriend/workbench_clips.js").resolve()


class WorkbenchDeletionUiTests(unittest.TestCase):
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
  function tagForId(id) {{ return html.match(new RegExp(`<[^>]+id="${{id}}"[^>]*>`))?.[0] || ''; }}
  function elementForId(id) {{
    const tag = tagForId(id);
    if (!tag) return null;
    if (!elements.has(id)) elements.set(id, {{
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
    return elements.get(id);
  }}
  const selectors = {{
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
    querySelector(selector) {{ return selector.startsWith('#') ? elementForId(selector.slice(1)) : null; }},
    querySelectorAll(selector) {{
      if (selector === 'audio') return [];
      const definition = selectors[selector];
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
const deletionEffectKeys = [
  'library_mutated', 'child_clip_created', 'source_clip_mutated',
  'correction_applied', 'note_deleted', 'note_count_changed',
  'note_pitch_changed', 'note_attack_velocity_changed', 'note_timing_changed',
  'release_velocity_changed', 'key_changed', 'chords_changed',
  'instrument_changed', 'provenance_changed', 'reuse_plan_changed',
  'placement_changed', 'current_arrangement_changed', 'pack_changed',
  'hybrid_created', 'feedback_recorded', 'data_submitted',
];
const effects = Object.fromEntries(deletionEffectKeys.map(key => [key, false]));
const createdEffects = {{...effects, library_mutated: true, child_clip_created: true, correction_applied: true, note_deleted: true, note_count_changed: true}};
const unchanged = {{
  retained_note_payloads: true, normalized_midi_survivors: true,
  note_pitches: true, note_onsets: true, note_durations: true,
  source_seconds: true, microtiming: true, velocity: true,
  release_velocity: true, articulation: true, clip_horizon: true,
  tempo_map: true, timing_mode: true, key: true, chords: true,
  instrument: true, provenance: true,
}};
const deletionCapability = {{
  enabled: true,
  actions: {{window: true, preview: true, create: true}},
  corrections: {{
    pitch_patch: {{enabled: true, drum_family: false}},
    attack_velocity_patch: {{enabled: true, drum_family: true}},
    note_delete_patch: {{enabled: true, drum_family: true}},
    malicious_unknown_patch: {{enabled: true, drum_family: true}},
  }},
  limits: {{ticks_per_beat: 480, maximum_window_ticks: 15360, maximum_changes: 64, maximum_pitch_delta_semitones: 24}},
}};
function note(noteRef, overrides = {{}}) {{
  return {{
    note_ref: noteRef, editable: true, edit_block_reason: null,
    export_note_on_group_size: 1, channel: 0, pitch: 60, velocity: 90,
    release_velocity: 64, start_tick: 0, end_tick: 480,
    start_beat: 0, duration_beats: 1,
    source_start_seconds: 0, source_end_seconds: .5,
    articulation: null, ...overrides,
  }};
}}
function identity({{clipId = 'keys', objectHash, parentClipId = null, revision = 1, noteCount = 2, pitchRange = {{minimum: 60, maximum: 67}}}}) {{
  return {{clip_id: clipId, object_sha256: objectHash, parent_clip_id: parentClipId, lineage_id: 'lineage-1', revision, key: 'B minor', bpm: 113, role: 'keys', role_redacted: false, note_count: noteCount, chord_count: 0, pitch_range: pitchRange, duration_seconds: 4}};
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

    def test_deletion_is_explicit_inspection_only_and_blocked_state_is_accessible(self) -> None:
        result = self.run_node(
            """
(async () => {
  const calls = [];
  const host = createDynamicHost();
  const parentHash = 'a'.repeat(64), libraryHash = 'b'.repeat(64), windowHash = 'c'.repeat(64);
  const firstRef = '1'.repeat(64), blockedRef = '2'.repeat(64), secondRef = '3'.repeat(64);
  const notes = [
    note(firstRef),
    note(blockedRef, {editable: false, edit_block_reason: 'duplicate-export-note-on', export_note_on_group_size: 2, pitch: 62, start_tick: 480, end_tick: 720, start_beat: 1, duration_beats: .5, source_start_seconds: .5, source_end_seconds: .75}),
    note(secondRef, {pitch: 64, start_tick: 960, end_tick: 1440, start_beat: 2, source_start_seconds: 1, source_end_seconds: 1.5}),
  ];
  const windowDocument = {
    schema: 'sunofriend.workbench-clip-note-deletion-window.v1', operation: 'clip-note-deletion-window', correction_kind: 'note_delete_patch',
    library: {state_sha256: libraryHash}, parent: identity({objectHash: parentHash, noteCount: 4}),
    window: {start_tick: 0, end_tick: 3840, ticks_per_beat: 480, duration_seconds: 4, origin: 'recorded-zero'},
    timing: {resolved_mode: 'musical', export_bpm: 113}, notes,
    visible_note_count: 3, editable_note_count: 2, blocked_note_count: 1,
    blocked_reason_counts: {'context-note-on-outside-window': 0, 'duplicate-export-note-on': 1, 'retained-note-lifetime-would-change': 0, 'clip-horizon-would-change': 0, 'only-note-in-clip': 0},
    chords: [], policies: {correction_scope: 'exact existing note deletion only'}, effects, window_sha256: windowHash,
  };
  const api = async (path, options = {}) => {
    calls.push({path, body: options.body || null});
    if (path.startsWith('/api/clips?')) return {page: {offset: 0, total: 1, has_more: false}, clips: [{clip_id: 'keys', object_sha256: parentHash, title: 'Keys', role: 'keys', key: 'B minor', bpm: 113, revision: 1, note_count: 4, duration_seconds: 4, tags: []}]};
    if (path === '/api/clips/keys') return {library_state_sha256: libraryHash, clip: {clip_id: 'keys', object_sha256: parentHash, title: 'Keys', role: 'keys', key: 'B minor', bpm: 113, revision: 1, note_count: 4, chord_count: 0, pitch_range: {minimum: 60, maximum: 67}, duration: {export_seconds: 4}, timing_contract: {resolved_mode: 'musical', export_bpm: 113}, instrument: {program: 4, channel: 0}}, lineage: {versions: []}};
    if (path === '/api/clip-note-correction-window') return {window: windowDocument};
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml});
  browser.setCapability({enabled: true, acceptance: {pack_sha256: '9'.repeat(64)}, library: {clip_count: 1, state_sha256: libraryHash}}, null, null, deletionCapability);
  browser.renderInto(host);
  await pause(); click(host.querySelectorAll('[data-open-clip]')[0]); await pause();
  const defaultHtml = host.innerHTML;
  const defaults = {pitch: host.element('clip-correction-kind-pitch')?.checked, velocity: host.element('clip-correction-kind-velocity')?.checked, deletion: host.element('clip-correction-kind-delete')?.checked};
  click(host.element('clip-correction-kind-delete'));
  submit(host.element('clip-correction-window-form')); await pause();
  const loadedHtml = host.innerHTML;
  const callsBeforeInspect = calls.length;
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${firstRef}`)));
  const inspectedHtml = host.innerHTML;
  const reviewDisabledAfterInspect = host.element('clip-correction-review')?.disabled;
  const callsAfterInspect = calls.length;
  const blockedToken = encodeURIComponent(`value:${blockedRef}`);
  click(host.data('[data-correction-note-ref]', blockedToken));
  const blockedHtml = host.innerHTML;
  const blockedMarkDisabled = host.element('clip-correction-mark-delete')?.disabled;
  const blockedNativeDisabled = host.data('[data-correction-note-ref]', blockedToken)?.disabled;
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${firstRef}`)));
  click(host.element('clip-correction-mark-delete'));
  const markedHtml = host.innerHTML;
  console.log(JSON.stringify({calls, defaultHtml, defaults, loadedHtml, callsBeforeInspect, callsAfterInspect, inspectedHtml, reviewDisabledAfterInspect, blockedHtml, blockedMarkDisabled, blockedNativeDisabled, markedHtml}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )
        windows = [call for call in result["calls"] if call["path"] == "/api/clip-note-correction-window"]
        self.assertEqual(result["defaults"], {"pitch": True, "velocity": False, "deletion": False})
        self.assertIn("Remove unwanted notes", result["defaultHtml"])
        self.assertNotIn("malicious_unknown_patch", result["defaultHtml"])
        self.assertEqual(json.loads(windows[0]["body"])["correction_kind"], "note_delete_patch")
        self.assertIn("Mark selected note for removal", result["loadedHtml"])
        self.assertIn("Keep selected note", result["loadedHtml"])
        self.assertIn("Selecting, clicking or focusing a note only inspects it", result["loadedHtml"])
        self.assertEqual(result["callsBeforeInspect"], result["callsAfterInspect"])
        self.assertTrue(result["reviewDisabledAfterInspect"])
        self.assertIn("Review 0 note-removal changes", result["inspectedHtml"])
        self.assertNotIn("fill=\"#8f2d3b\"", result["inspectedHtml"])
        self.assertFalse(result["blockedNativeDisabled"])
        self.assertTrue(result["blockedMarkDisabled"])
        self.assertIn('aria-disabled="true"', result["blockedHtml"])
        self.assertIn("blocked: duplicate exported Note On", result["blockedHtml"])
        self.assertIn("amber dashed notes are blocked", result["blockedHtml"])
        self.assertIn("marked for removal", result["markedHtml"])
        self.assertIn("will be removed", result["markedHtml"])
        self.assertIn("#8f2d3b", result["markedHtml"])

    def test_exact_deletion_review_create_inspect_and_restored_summary(self) -> None:
        result = self.run_node(
            """
(async () => {
  const calls = [];
  const host = createDynamicHost();
  const parentHash = 'a'.repeat(64), libraryHash = 'b'.repeat(64), windowHash = 'c'.repeat(64), projectionHash = 'd'.repeat(64), childHash = 'e'.repeat(64), intentHash = '4'.repeat(64);
  const childId = `sf-correction-${intentHash}`, noteRef = '1'.repeat(64), otherRef = '2'.repeat(64);
  const first = note(noteRef, {start_beat: .125, duration_beats: .75});
  const second = note(otherRef, {pitch: 67, start_tick: 3360, end_tick: 3840, start_beat: 7, source_start_seconds: 3.5, source_end_seconds: 4});
  const windowDocument = {
    schema: 'sunofriend.workbench-clip-note-deletion-window.v1', operation: 'clip-note-deletion-window', correction_kind: 'note_delete_patch',
    library: {state_sha256: libraryHash}, parent: identity({objectHash: parentHash}),
    window: {start_tick: 0, end_tick: 3840, ticks_per_beat: 480, duration_seconds: 4, origin: 'recorded-zero'}, timing: {resolved_mode: 'musical', export_bpm: 113},
    notes: [first, second], visible_note_count: 2, editable_note_count: 2, blocked_note_count: 0,
    blocked_reason_counts: {'context-note-on-outside-window': 0, 'duplicate-export-note-on': 0, 'retained-note-lifetime-would-change': 0, 'clip-horizon-would-change': 0, 'only-note-in-clip': 0},
    chords: [], policies: {correction_scope: 'exact existing note deletion only'}, effects, window_sha256: windowHash,
  };
  const change = {note_ref: noteRef, channel: 0, start_tick: 0, end_tick: 480, start_beat: .125, duration_beats: .75, source_start_seconds: 0, source_end_seconds: .5, pitch: 60, velocity: 90, release_velocity: 64, articulation: null};
  const diff = {kind: 'note_delete_patch', changed_note_count: 1, changes: [change], note_count_before: 2, note_count_after: 1, normalized_midi_note_count_before: 2, normalized_midi_note_count_after: 1, pitch_range_before: {minimum: 60, maximum: 67}, pitch_range_after: {minimum: 67, maximum: 67}, duration_beats_before: 8, duration_beats_after: 8, duration_seconds_before: 4, duration_seconds_after: 4, retained_normalized_notes_changed: 0, unchanged};
  const correction = {kind: 'note_delete_patch', changes: [{note_ref: noteRef}]};
  const projection = {schema: 'sunofriend.workbench-clip-note-deletion-preview.v1', status: 'previewed', operation: 'clip-note-deletion-correction-preview', intent_sha256: intentHash, library: {state_sha256: libraryHash}, window: windowDocument.window, correction, parent: identity({objectHash: parentHash}), child: identity({clipId: childId, objectHash: childHash, parentClipId: 'keys', revision: 2, noteCount: 1, pitchRange: {minimum: 67, maximum: 67}}), diff, warnings: ['Check <img src=x onerror=bad()> & retain the phrase.'], effects, projection_sha256: projectionHash};
  const parentDetail = {library_state_sha256: libraryHash, clip: {clip_id: 'keys', object_sha256: parentHash, title: 'Keys', role: 'keys', key: 'B minor', bpm: 113, revision: 1, note_count: 2, chord_count: 0, pitch_range: {minimum: 60, maximum: 67}, duration: {export_seconds: 4}, timing_contract: {resolved_mode: 'musical', export_bpm: 113}, instrument: {program: 4, channel: 0}}, lineage: {versions: []}};
  const api = async (path, options = {}) => {
    calls.push({path, body: options.body || null});
    if (path.startsWith('/api/clips?')) return {page: {offset: 0, total: 1, has_more: false}, clips: [{clip_id: 'keys', object_sha256: parentHash, title: 'Keys', role: 'keys', key: 'B minor', bpm: 113, revision: 1, note_count: 2, duration_seconds: 4, tags: []}]};
    if (path === '/api/clips/keys') return parentDetail;
    if (path === '/api/clip-note-correction-window') return {window: windowDocument};
    if (path === '/api/clip-note-correction-projection') return {projection};
    if (path === '/api/clip-note-correction-action') return {result: {schema: 'sunofriend.workbench-clip-note-deletion-result.v1', status: 'created', operation: 'clip-note-deletion-correction-create', projection_sha256: projectionHash, replayed: false, window: projection.window, correction, parent: projection.parent, child: projection.child, diff, warnings: projection.warnings, library: {expected_state_sha256: libraryHash, previous_state_sha256: libraryHash, current_state_sha256: 'f'.repeat(64)}, effects: createdEffects}};
    if (path === `/api/clips/${childId}`) return {library_state_sha256: 'f'.repeat(64), clip: {clip_id: childId, object_sha256: childHash, title: 'Keys note removal', role: 'keys', key: 'B minor', bpm: 113, revision: 2, note_count: 1, chord_count: 0, pitch_range: {minimum: 67, maximum: 67}, duration: {export_seconds: 4}, timing_contract: {resolved_mode: 'musical', export_bpm: 113}, instrument: {program: 4, channel: 0}}, lineage: {versions: []}, correction_summary: {schema: 'sunofriend.workbench-clip-note-deletion-summary.v1', operation: 'delete_clip_notes', contract_version: 1, parent_clip_id: 'keys', parent_object_sha256: parentHash, child_clip_id: childId, child_object_sha256: childHash, window: projection.window, changed_note_count: 1, changes: [change], unchanged}};
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml});
  browser.setCapability({enabled: true, acceptance: {pack_sha256: '9'.repeat(64)}, library: {clip_count: 1, state_sha256: libraryHash}}, null, null, deletionCapability);
  browser.renderInto(host); await pause(); click(host.querySelectorAll('[data-open-clip]')[0]); await pause();
  click(host.element('clip-correction-kind-delete')); submit(host.element('clip-correction-window-form')); await pause();
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${noteRef}`)));
  const staleMark = host.element('clip-correction-mark-delete'); click(staleMark);
  click(host.element('clip-correction-review')); await pause();
  const reviewedHtml = host.innerHTML;
  const callsBeforeNoop = calls.length;
  staleMark.onclick();
  const noopHtml = host.innerHTML;
  const callsAfterNoop = calls.length;
  host.data('[data-correction-note-ref]', encodeURIComponent(`value:${otherRef}`)).focus();
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${otherRef}`)));
  const inspectedHtml = host.innerHTML;
  const callsAfterInspect = calls.length;
  host.element('clip-correction-keep-delete').onclick();
  const keptNoopHtml = host.innerHTML;
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${noteRef}`)));
  click(host.element('clip-correction-create')); await pause();
  const createdHtml = host.innerHTML;
  const childReadsBeforeInspect = calls.filter(call => call.path === `/api/clips/${childId}`).length;
  click(host.element('clip-correction-inspect-child')); await pause();
  console.log(JSON.stringify({calls, reviewedHtml, noopHtml, callsBeforeNoop, callsAfterNoop, inspectedHtml, callsAfterInspect, keptNoopHtml, createdHtml, childReadsBeforeInspect, childHtml: host.innerHTML}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )
        previews = [call for call in result["calls"] if call["path"] == "/api/clip-note-correction-projection"]
        actions = [call for call in result["calls"] if call["path"] == "/api/clip-note-correction-action"]
        self.assertEqual(len(previews), 1)
        request = json.loads(previews[0]["body"])
        self.assertEqual(request["correction"], {"kind": "note_delete_patch", "changes": [{"note_ref": "1" * 64}]})
        self.assertNotIn("correction_kind", request)
        self.assertIn("Exact temporary note-removal review", result["reviewedHtml"])
        self.assertIn("2 → 1", result["reviewedHtml"])
        self.assertIn("Retained normalized notes changed", result["reviewedHtml"])
        self.assertIn("&lt;img", result["reviewedHtml"])
        self.assertIn("&amp; retain", result["reviewedHtml"])
        self.assertNotIn("<img src=x", result["reviewedHtml"])
        self.assertEqual(result["callsBeforeNoop"], result["callsAfterNoop"])
        self.assertEqual(result["callsAfterNoop"], result["callsAfterInspect"])
        self.assertIn("Exact temporary note-removal review", result["noopHtml"])
        self.assertIn("already marked for removal", result["noopHtml"])
        self.assertIn("Exact temporary note-removal review", result["inspectedHtml"])
        self.assertIn("already kept", result["keptNoopHtml"])
        self.assertEqual(len(actions), 1)
        self.assertEqual(json.loads(actions[0]["body"])["correction"], request["correction"])
        self.assertEqual(result["childReadsBeforeInspect"], 0)
        self.assertIn("New note-removal alternative created", result["createdHtml"])
        self.assertIn("Saved note-removal correction", result["childHtml"])
        self.assertIn("Only the listed note events were removed", result["childHtml"])
        self.assertEqual(len([call for call in result["calls"] if call["path"] == "/api/clip-artifact"]), 0)

    def test_malformed_evidence_is_rejected_and_exact_replay_has_zero_effects(self) -> None:
        result = self.run_node(
            """
(async () => {
  const calls = [];
  const host = createDynamicHost();
  const parentHash = 'a'.repeat(64), libraryHash = 'b'.repeat(64), currentHash = 'f'.repeat(64), windowHash = 'c'.repeat(64), projectionHash = 'd'.repeat(64), childHash = 'e'.repeat(64), intentHash = '4'.repeat(64), noteRef = '1'.repeat(64);
  const source = note(noteRef);
  const windowDocument = {schema: 'sunofriend.workbench-clip-note-deletion-window.v1', operation: 'clip-note-deletion-window', correction_kind: 'note_delete_patch', library: {state_sha256: libraryHash}, parent: identity({objectHash: parentHash}), window: {start_tick: 0, end_tick: 3840, ticks_per_beat: 480, duration_seconds: 4, origin: 'recorded-zero'}, timing: {resolved_mode: 'musical', export_bpm: 113}, notes: [source], visible_note_count: 1, editable_note_count: 1, blocked_note_count: 0, blocked_reason_counts: {'context-note-on-outside-window': 0, 'duplicate-export-note-on': 0, 'retained-note-lifetime-would-change': 0, 'clip-horizon-would-change': 0, 'only-note-in-clip': 0}, chords: [], policies: {correction_scope: 'exact existing note deletion only'}, effects, window_sha256: windowHash};
  const change = {note_ref: noteRef, channel: 0, start_tick: 0, end_tick: 480, start_beat: 0, duration_beats: 1, source_start_seconds: 0, source_end_seconds: .5, pitch: 60, velocity: 90, release_velocity: 64, articulation: null};
  const correction = {kind: 'note_delete_patch', changes: [{note_ref: noteRef}]};
  const diff = {kind: 'note_delete_patch', changed_note_count: 1, changes: [change], note_count_before: 2, note_count_after: 1, normalized_midi_note_count_before: 2, normalized_midi_note_count_after: 1, pitch_range_before: {minimum: 60, maximum: 67}, pitch_range_after: {minimum: 67, maximum: 67}, duration_beats_before: 8, duration_beats_after: 8, duration_seconds_before: 4, duration_seconds_after: 4, retained_normalized_notes_changed: 0, unchanged};
  const projection = {schema: 'sunofriend.workbench-clip-note-deletion-preview.v1', status: 'previewed', operation: 'clip-note-deletion-correction-preview', intent_sha256: intentHash, library: {state_sha256: libraryHash}, window: windowDocument.window, correction, parent: identity({objectHash: parentHash}), child: identity({clipId: `sf-correction-${intentHash}`, objectHash: childHash, parentClipId: 'keys', revision: 2, noteCount: 1, pitchRange: {minimum: 67, maximum: 67}}), diff, warnings: [], effects, projection_sha256: projectionHash};
  let previewCount = 0, actionCount = 0;
  const api = async (path, options = {}) => {
    calls.push({path, body: options.body || null});
    if (path.startsWith('/api/clips?')) return {page: {offset: 0, total: 1, has_more: false}, clips: [{clip_id: 'keys', object_sha256: parentHash, title: 'Keys', role: 'keys', key: 'B minor', bpm: 113, revision: 1, note_count: 2, duration_seconds: 4, tags: []}]};
    if (path === '/api/clips/keys') return {library_state_sha256: libraryHash, clip: {clip_id: 'keys', object_sha256: parentHash, title: 'Keys', role: 'keys', key: 'B minor', bpm: 113, revision: 1, note_count: 2, chord_count: 0, pitch_range: {minimum: 60, maximum: 67}, duration: {export_seconds: 4}, timing_contract: {resolved_mode: 'musical', export_bpm: 113}, instrument: {program: 4, channel: 0}}, lineage: {versions: []}};
    if (path === '/api/clip-note-correction-window') return {window: windowDocument};
    if (path === '/api/clip-note-correction-projection') {
      previewCount += 1;
      if (previewCount === 1) return {projection: {...projection, schema: 'evil.schema'}};
      if (previewCount === 2) return {projection: {...projection, diff: {...diff, duration_beats_after: 7}}};
      if (previewCount === 3) return {projection: {...projection, diff: {...diff, changes: [{...change, velocity: 1}]}}};
      if (previewCount === 4) return {projection: {...projection, effects: {...effects, unexpected_effect: false}}};
      return {projection};
    }
    if (path === '/api/clip-note-correction-action') {
      actionCount += 1;
      const result = {schema: 'sunofriend.workbench-clip-note-deletion-result.v1', status: actionCount === 1 ? 'created' : 'replayed', operation: 'clip-note-deletion-correction-create', projection_sha256: projectionHash, replayed: actionCount !== 1, window: projection.window, correction, parent: projection.parent, child: projection.child, diff, warnings: [], library: {expected_state_sha256: libraryHash, previous_state_sha256: actionCount === 1 ? libraryHash : currentHash, current_state_sha256: currentHash}, effects};
      return {result};
    }
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml});
  browser.setCapability({enabled: true, acceptance: {pack_sha256: '9'.repeat(64)}, library: {clip_count: 1, state_sha256: libraryHash}}, null, null, deletionCapability);
  browser.renderInto(host); await pause(); click(host.querySelectorAll('[data-open-clip]')[0]); await pause(); click(host.element('clip-correction-kind-delete')); submit(host.element('clip-correction-window-form')); await pause(); click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${noteRef}`))); click(host.element('clip-correction-mark-delete'));
  const rejected = [];
  for (let index = 0; index < 4; index += 1) { click(host.element('clip-correction-review')); await pause(); rejected.push(host.innerHTML); }
  click(host.element('clip-correction-review')); await pause(); const accepted = host.innerHTML;
  click(host.element('clip-correction-create')); await pause(); const rejectedCreate = host.innerHTML;
  click(host.element('clip-correction-create')); await pause(); const replay = host.innerHTML;
  console.log(JSON.stringify({calls, rejected, accepted, rejectedCreate, replay}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )
        self.assertEqual(len([call for call in result["calls"] if call["path"] == "/api/clip-note-correction-projection"]), 5)
        for html in result["rejected"]:
            self.assertIn("invalid or mismatched zero-effect note-removal review", html)
            self.assertNotIn("Exact temporary note-removal review", html)
        self.assertIn("Exact temporary note-removal review", result["accepted"])
        self.assertIn("invalid or mismatched immutable note-removal result", result["rejectedCreate"])
        self.assertNotIn("New note-removal alternative", result["rejectedCreate"])
        self.assertIn("Existing note-removal alternative verified", result["replay"])
        self.assertIn("appended nothing", result["replay"])

    def test_malformed_deletion_windows_fail_closed_before_any_draft(self) -> None:
        result = self.run_node(
            """
(async () => {
  const calls = [];
  const host = createDynamicHost();
  const parentHash = 'a'.repeat(64), libraryHash = 'b'.repeat(64), windowHash = 'c'.repeat(64), noteRef = '1'.repeat(64);
  const source = note(noteRef, {start_beat: .125, duration_beats: .75});
  const valid = {schema: 'sunofriend.workbench-clip-note-deletion-window.v1', operation: 'clip-note-deletion-window', correction_kind: 'note_delete_patch', library: {state_sha256: libraryHash}, parent: identity({objectHash: parentHash}), window: {start_tick: 0, end_tick: 3840, ticks_per_beat: 480, duration_seconds: 4, origin: 'recorded-zero'}, timing: {resolved_mode: 'stem_locked', export_bpm: 113}, notes: [source], visible_note_count: 1, editable_note_count: 1, blocked_note_count: 0, blocked_reason_counts: {'context-note-on-outside-window': 0, 'duplicate-export-note-on': 0, 'retained-note-lifetime-would-change': 0, 'clip-horizon-would-change': 0, 'only-note-in-clip': 0}, chords: [], policies: {correction_scope: 'exact existing note deletion only'}, effects, window_sha256: windowHash};
  let windowCount = 0;
  const api = async (path, options = {}) => {
    calls.push({path, body: options.body || null});
    if (path.startsWith('/api/clips?')) return {page: {offset: 0, total: 1, has_more: false}, clips: [{clip_id: 'keys', object_sha256: parentHash, title: 'Keys', role: 'keys', key: 'B minor', bpm: 113, revision: 1, note_count: 2, duration_seconds: 4, tags: []}]};
    if (path === '/api/clips/keys') return {library_state_sha256: libraryHash, clip: {clip_id: 'keys', object_sha256: parentHash, title: 'Keys', role: 'keys', key: 'B minor', bpm: 113, revision: 1, note_count: 2, chord_count: 0, pitch_range: {minimum: 60, maximum: 67}, duration: {export_seconds: 4}, timing_contract: {resolved_mode: 'stem_locked', export_bpm: 113}, instrument: {program: 4, channel: 0}}, lineage: {versions: []}};
    if (path === '/api/clip-note-correction-window') {
      windowCount += 1;
      if (windowCount === 1) return {window: {...valid, operation: 'clip-correction-window'}};
      if (windowCount === 2) return {window: {...valid, notes: [{...source, edit_block_reason: 'invented-block'}]}};
      if (windowCount === 3) return {window: {...valid, editable_note_count: 0}};
      if (windowCount === 4) return {window: {...valid, effects: {...effects, surprise: false}}};
      return {window: valid};
    }
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml});
  browser.setCapability({enabled: true, acceptance: {pack_sha256: '9'.repeat(64)}, library: {clip_count: 1, state_sha256: libraryHash}}, null, null, deletionCapability);
  browser.renderInto(host); await pause(); click(host.querySelectorAll('[data-open-clip]')[0]); await pause(); click(host.element('clip-correction-kind-delete'));
  const rejected = [];
  for (let index = 0; index < 4; index += 1) { submit(host.element('clip-correction-window-form')); await pause(); rejected.push(host.innerHTML); }
  submit(host.element('clip-correction-window-form')); await pause();
  console.log(JSON.stringify({calls, rejected, accepted: host.innerHTML}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )
        for html in result["rejected"]:
            self.assertIn("invalid bounded note window", html)
            self.assertNotIn("Mark selected note for removal", html)
        self.assertIn("Mark selected note for removal", result["accepted"])
        self.assertIn("beat 0.125", result["accepted"])
        windows = [call for call in result["calls"] if call["path"] == "/api/clip-note-correction-window"]
        self.assertEqual(len(windows), 5)
        self.assertTrue(all(json.loads(call["body"])["correction_kind"] == "note_delete_patch" for call in windows))


if __name__ == "__main__":
    unittest.main()
