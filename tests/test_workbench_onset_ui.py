from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


CLIPS_PATH = Path("src/sunofriend/workbench_clips.js").resolve()


class WorkbenchOnsetUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.node = shutil.which("node")
        if not cls.node:
            raise unittest.SkipTest("Node.js is not installed")

    def run_node(self, body: str) -> dict[str, object]:
        template = r"""
const clips = require(__CLIPS_PATH__);
const pause = () => new Promise(resolve => setTimeout(resolve, 0));
function click(element) {
  if (element && !element.disabled && typeof element.onclick === 'function') element.onclick();
}
function submit(element) {
  if (element && !element.disabled && typeof element.onsubmit === 'function') element.onsubmit({preventDefault() {}});
}
function createDynamicHost() {
  let html = '';
  let elements = new Map();
  let dataElements = new Map();
  function tagForId(id) { return html.match(new RegExp(`<[^>]+id="${id}"[^>]*>`))?.[0] || ''; }
  function elementForId(id) {
    const tag = tagForId(id);
    if (!tag) return null;
    if (!elements.has(id)) elements.set(id, {
      id,
      value: tag.match(/value="([^"]*)"/)?.[1] || '',
      disabled: /\sdisabled(?:\s|>|=)/.test(tag),
      checked: /\schecked(?:\s|>|=)/.test(tag),
      textContent: id,
      isConnected: true,
      onclick: null,
      oninput: null,
      onsubmit: null,
      pause() {},
      focus() { this.focused = true; if (this.onfocus) this.onfocus(); },
    });
    return elements.get(id);
  }
  const selectors = {
    '[data-open-clip]': ['openClip', 'data-open-clip'],
    '[data-lineage-clip]': ['lineageClip', 'data-lineage-clip'],
    '[data-correction-note-ref]': ['correctionNoteRef', 'data-correction-note-ref'],
    '[data-correction-note-svg]': ['correctionNoteSvg', 'data-correction-note-svg'],
    '[data-correction-pitch-delta]': ['correctionPitchDelta', 'data-correction-pitch-delta'],
    '[data-correction-velocity-delta]': ['correctionVelocityDelta', 'data-correction-velocity-delta'],
    '[data-correction-onset-delta]': ['correctionOnsetDelta', 'data-correction-onset-delta'],
  };
  return {
    get innerHTML() { return html; },
    set innerHTML(value) {
      for (const element of elements.values()) element.isConnected = false;
      html = String(value);
      elements = new Map();
      dataElements = new Map();
    },
    querySelector(selector) { return selector.startsWith('#') ? elementForId(selector.slice(1)) : null; },
    querySelectorAll(selector) {
      if (selector === 'audio') return [];
      const definition = selectors[selector];
      if (!definition) return [];
      const [datasetKey, attribute] = definition;
      const pattern = new RegExp(`<[^>]+${attribute}="([^"]+)"[^>]*>`, 'g');
      const result = [];
      for (const match of html.matchAll(pattern)) {
        const key = `${selector}:${match[1]}`;
        if (!dataElements.has(key)) dataElements.set(key, {
          dataset: {[datasetKey]: match[1]},
          disabled: /\sdisabled(?:\s|>|=)/.test(match[0]),
          onclick: null,
          onfocus: null,
          focus() { this.focused = true; if (this.onfocus) this.onfocus(); },
        });
        result.push(dataElements.get(key));
      }
      return result;
    },
    element(id) { return elementForId(id); },
    data(selector, value) { return dataElements.get(`${selector}:${value}`); },
  };
}
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
const hashes = {
  parent: 'a'.repeat(64), library: 'b'.repeat(64), window: 'c'.repeat(64),
  projection: 'd'.repeat(64), child: 'e'.repeat(64), intent: 'f'.repeat(64),
  nextLibrary: '9'.repeat(64), firstRef: '1'.repeat(64), blockedRef: '2'.repeat(64),
  edgeRef: '3'.repeat(64),
};
const onsetEffectKeys = [
  'library_mutated', 'child_clip_created', 'source_clip_mutated',
  'correction_applied', 'note_onset_changed', 'note_timing_changed',
  'note_duration_changed', 'note_pitch_changed', 'note_attack_velocity_changed',
  'release_velocity_changed', 'note_count_changed', 'key_changed',
  'chords_changed', 'instrument_changed', 'provenance_changed',
  'reuse_plan_changed', 'placement_changed', 'current_arrangement_changed',
  'pack_changed', 'hybrid_created', 'feedback_recorded', 'data_submitted',
];
const effects = Object.fromEntries(onsetEffectKeys.map(key => [key, false]));
const createdEffects = {
  ...effects,
  library_mutated: true,
  child_clip_created: true,
  correction_applied: true,
  note_onset_changed: true,
  note_timing_changed: true,
};
const onsetCapability = {
  enabled: true,
  actions: {window: true, preview: true, create: true},
  corrections: {
    pitch_patch: {enabled: true, drum_family: false},
    attack_velocity_patch: {enabled: true, drum_family: true},
    note_delete_patch: {enabled: true, drum_family: true},
    note_onset_shift_patch: {enabled: true, drum_family: true},
    malicious_unknown_patch: {enabled: true, drum_family: true},
    timing: false,
  },
  limits: {
    ticks_per_beat: 480,
    maximum_window_beats: 32,
    maximum_changes: 64,
    maximum_pitch_delta_semitones: 24,
    maximum_onset_delta_ticks: 480,
  },
};
function note(noteRef, overrides = {}) {
  return {
    note_ref: noteRef,
    editable: true,
    edit_block_reason: null,
    export_note_on_group_size: 1,
    channel: 0,
    pitch: 60,
    velocity: 90,
    release_velocity: 0,
    start_tick: 480,
    end_tick: 720,
    duration_ticks: 240,
    start_beat: 1,
    duration_beats: .5,
    source_start_seconds: .5,
    source_end_seconds: .75,
    microtiming_seconds: 0,
    end_microtiming_seconds: 0,
    articulation: null,
    ...overrides,
  };
}
function identity({clipId = 'keys', objectHash = hashes.parent, parentClipId = null, revision = 1} = {}) {
  return {
    clip_id: clipId,
    object_sha256: objectHash,
    parent_clip_id: parentClipId,
    lineage_id: 'lineage-1',
    revision,
    key: 'B minor',
    bpm: 120,
    role: 'keys',
    role_redacted: false,
    note_count: 3,
    chord_count: 0,
    pitch_range: {minimum: 60, maximum: 64},
    duration_seconds: 4,
  };
}
function fixture() {
  const notes = [
    note(hashes.firstRef),
    note(hashes.blockedRef, {
      editable: false,
      edit_block_reason: 'duplicate-export-note-on',
      export_note_on_group_size: 2,
      pitch: 62,
      start_tick: 960,
      end_tick: 1200,
      start_beat: 2,
      source_start_seconds: 1,
      source_end_seconds: 1.25,
    }),
    note(hashes.edgeRef, {
      pitch: 64,
      start_tick: 3480,
      end_tick: 3720,
      start_beat: 7.25,
      source_start_seconds: 3.625,
      source_end_seconds: 3.875,
    }),
  ];
  const windowDocument = {
    schema: 'sunofriend.workbench-clip-note-onset-window.v1',
    operation: 'clip-note-onset-window',
    correction_kind: 'note_onset_shift_patch',
    library: {state_sha256: hashes.library},
    parent: identity(),
    window: {start_tick: 0, end_tick: 3840, ticks_per_beat: 480, duration_seconds: 4, origin: 'recorded-zero'},
    timing: {resolved_mode: 'musical', export_bpm: 120},
    notes,
    visible_note_count: 3,
    editable_note_count: 2,
    blocked_note_count: 1,
    blocked_reason_counts: {
      'context-note-outside-window': 0,
      'duplicate-export-note-on': 1,
      'normalized-lifetime-dependent': 0,
      'unsupported-stem-locked-microtiming': 0,
    },
    chords: [],
    policies: {
      editable_membership: 'full exact source interval inside the loaded window',
      context_membership: 'intersecting interval is visible context',
      correction_scope: 'bounded existing-note onset shift only',
      maximum_shift_ticks: 480,
      duplicate_export_note_on: 'duplicate Note On events are blocked',
      normalized_lifetime: 'normalization-dependent lifetimes are blocked',
    },
    effects,
    window_sha256: hashes.window,
  };
  const correction = {
    kind: 'note_onset_shift_patch',
    changes: [{note_ref: hashes.firstRef, target_start_tick: 600}],
  };
  const diff = {
    kind: 'note_onset_shift_patch',
    changed_note_count: 1,
    timing_mode: 'musical',
    export_bpm: 120,
    changes: [{
      note_ref: hashes.firstRef,
      channel: 0,
      pitch: 60,
      before_start_tick: 480,
      after_start_tick: 600,
      before_end_tick: 720,
      after_end_tick: 840,
      duration_ticks: 240,
      tick_delta: 120,
      milliseconds_delta: 125,
      before_start_beat: 1,
      after_start_beat: 1.25,
      before_source_start_seconds: .5,
      after_source_start_seconds: .65,
    }],
  };
  const childId = `sf-correction-${hashes.intent}`;
  const projection = {
    schema: 'sunofriend.workbench-clip-note-onset-preview.v1',
    status: 'previewed',
    operation: 'clip-note-onset-correction-preview',
    intent_sha256: hashes.intent,
    library: {state_sha256: hashes.library},
    window: windowDocument.window,
    correction,
    parent: identity(),
    child: identity({clipId: childId, objectHash: hashes.child, parentClipId: 'keys', revision: 2}),
    diff,
    warnings: ['Listen with the same <unsafe> patch & BPM.'],
    effects,
    projection_sha256: hashes.projection,
  };
  const detail = {
    library_state_sha256: hashes.library,
    clip: {
      clip_id: 'keys', object_sha256: hashes.parent, parent_clip_id: null,
      lineage_id: 'lineage-1', title: 'Keys', role: 'keys', role_redacted: false,
      key: 'B minor', bpm: 120, revision: 1, note_count: 3, chord_count: 0,
      pitch_range: {minimum: 60, maximum: 64}, duration_seconds: 4,
      duration: {export_seconds: 4},
      timing_contract: {resolved_mode: 'musical', export_bpm: 120},
      instrument: {program: 4, channel: 0},
    },
    lineage: {versions: []},
  };
  return {notes, windowDocument, correction, diff, projection, detail, childId};
}
function listDocument() {
  return {
    page: {offset: 0, total: 1, has_more: false},
    clips: [{
      clip_id: 'keys', object_sha256: hashes.parent, title: 'Keys', role: 'keys',
      key: 'B minor', bpm: 120, revision: 1, note_count: 3,
      duration_seconds: 4, tags: [],
    }],
  };
}
function configure(browser) {
  browser.setCapability({
    enabled: true,
    acceptance: {pack_sha256: '8'.repeat(64)},
    library: {clip_count: 1, state_sha256: hashes.library},
  }, null, null, onsetCapability);
}
__BODY__
"""
        script = template.replace("__CLIPS_PATH__", json.dumps(str(CLIPS_PATH))).replace(
            "__BODY__", body
        )
        result = subprocess.run(
            [self.node, "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_onset_is_explicit_bounded_and_accessible(self) -> None:
        result = self.run_node(
            r"""
(async () => {
  const f = fixture(), calls = [], host = createDynamicHost();
  const api = async (path, options = {}) => {
    calls.push({path, body: options.body || null});
    if (path.startsWith('/api/clips?')) return listDocument();
    if (path === '/api/clips/keys') return f.detail;
    if (path === '/api/clip-note-correction-window') return {window: f.windowDocument};
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml});
  configure(browser);
  browser.renderInto(host);
  await pause();
  click(host.querySelectorAll('[data-open-clip]')[0]);
  await pause();
  const defaultState = {
    pitch: host.element('clip-correction-kind-pitch')?.checked,
    onset: host.element('clip-correction-kind-onset')?.checked,
    html: host.innerHTML,
  };
  click(host.element('clip-correction-kind-onset'));
  submit(host.element('clip-correction-window-form'));
  await pause();
  const loadedHtml = host.innerHTML;
  const callsBeforeInspection = calls.length;
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${hashes.firstRef}`)));
  const input = host.element('clip-correction-exact-onset');
  input.value = '600';
  if (input.oninput) input.oninput();
  const afterTyping = {
    calls: calls.length,
    reviewDisabled: host.element('clip-correction-review')?.disabled,
    html: host.innerHTML,
  };

  host.element('clip-correction-exact-onset').value = '480';
  submit(host.element('clip-correction-onset-form'));
  const noOpHtml = host.innerHTML;
  host.element('clip-correction-exact-onset').value = '480.5';
  submit(host.element('clip-correction-onset-form'));
  const fractionalHtml = host.innerHTML;
  host.element('clip-correction-exact-onset').value = '1000';
  submit(host.element('clip-correction-onset-form'));
  const tooFarHtml = host.innerHTML;

  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${hashes.edgeRef}`)));
  host.element('clip-correction-exact-onset').value = '3720';
  submit(host.element('clip-correction-onset-form'));
  const outsideHtml = host.innerHTML;
  const selectedBeforeBlocked = host.innerHTML.match(/Selected note [^<]+/)?.[0] || '';
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${hashes.blockedRef}`)));
  const blockedHtml = host.innerHTML;
  const blockedDisabled = host.data('[data-correction-note-ref]', encodeURIComponent(`value:${hashes.blockedRef}`))?.disabled;

  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${hashes.firstRef}`)));
  click(host.data('[data-correction-onset-delta]', '120'));
  const draftedHtml = host.innerHTML;
  const reviewReady = !host.element('clip-correction-review')?.disabled;
  const pitchSwitchDisabled = host.element('clip-correction-kind-pitch')?.disabled;
  click(host.element('clip-correction-kind-pitch'));
  const stillOnset = host.element('clip-correction-kind-onset')?.checked;
  click(host.element('clip-correction-reset-all'));
  const resetHtml = host.innerHTML;
  const pitchSwitchAfterResetDisabled = host.element('clip-correction-kind-pitch')?.disabled;
  click(host.element('clip-correction-kind-pitch'));
  const pitchAfterReset = host.element('clip-correction-kind-pitch')?.checked;
  console.log(JSON.stringify({
    calls, defaultState, loadedHtml, callsBeforeInspection, afterTyping,
    noOpHtml, fractionalHtml, tooFarHtml, outsideHtml, selectedBeforeBlocked,
    blockedHtml, blockedDisabled, draftedHtml, reviewReady, pitchSwitchDisabled,
    stillOnset, resetHtml, pitchSwitchAfterResetDisabled, pitchAfterReset,
  }));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )
        window_calls = [
            call
            for call in result["calls"]
            if call["path"] == "/api/clip-note-correction-window"
        ]
        self.assertEqual(result["defaultState"]["pitch"], True)
        self.assertEqual(result["defaultState"]["onset"], False)
        self.assertIn("Move existing note earlier or later", result["defaultState"]["html"])
        self.assertNotIn("malicious_unknown_patch", result["defaultState"]["html"])
        self.assertEqual(len(window_calls), 1)
        self.assertEqual(
            json.loads(window_calls[0]["body"])["correction_kind"],
            "note_onset_shift_patch",
        )
        self.assertIn("Move the selected note earlier or later", result["loadedHtml"])
        self.assertIn("Typing alone does not edit the draft", result["loadedHtml"])
        self.assertIn("Note On and Note Off move by the same exact delta", result["loadedHtml"])
        self.assertIn("duplicate exported Note On", result["loadedHtml"])
        self.assertEqual(result["callsBeforeInspection"], result["afterTyping"]["calls"])
        self.assertTrue(result["afterTyping"]["reviewDisabled"])
        self.assertIn("immutable parent start tick", result["noOpHtml"])
        self.assertIn("whole nonnegative integer", result["fractionalHtml"])
        self.assertIn("within 480 ticks", result["tooFarHtml"])
        self.assertIn("complete shifted note must stay inside", result["outsideHtml"])
        self.assertTrue(result["blockedDisabled"])
        self.assertIn("duplicate exported Note On", result["blockedHtml"])
        self.assertTrue(result["reviewReady"])
        self.assertIn("draft start tick 600", result["draftedHtml"])
        self.assertIn("gold is the temporary onset-shift draft", result["draftedHtml"])
        self.assertTrue(result["pitchSwitchDisabled"])
        self.assertTrue(result["stillOnset"])
        self.assertIn("All temporary note-onset changes were reset", result["resetHtml"])
        self.assertIn("immutable parent was never changed", result["resetHtml"])
        self.assertFalse(result["pitchSwitchAfterResetDisabled"])
        self.assertTrue(result["pitchAfterReset"])

    def test_exact_onset_review_create_and_replay(self) -> None:
        result = self.run_node(
            r"""
async function runFlow(replayed) {
  const f = fixture(), calls = [], host = createDynamicHost();
  const result = {
    schema: 'sunofriend.workbench-clip-note-onset-result.v1',
    status: replayed ? 'replayed' : 'created',
    operation: 'clip-note-onset-correction-create',
    projection_sha256: hashes.projection,
    replayed,
    window: f.projection.window,
    correction: f.correction,
    parent: f.projection.parent,
    child: f.projection.child,
    diff: f.diff,
    warnings: f.projection.warnings,
    library: replayed
      ? {expected_state_sha256: hashes.library, previous_state_sha256: hashes.nextLibrary, current_state_sha256: hashes.nextLibrary}
      : {expected_state_sha256: hashes.library, previous_state_sha256: hashes.library, current_state_sha256: hashes.nextLibrary},
    effects: replayed ? effects : createdEffects,
  };
  const api = async (path, options = {}) => {
    calls.push({path, body: options.body || null});
    if (path.startsWith('/api/clips?')) return listDocument();
    if (path === '/api/clips/keys') return f.detail;
    if (path === '/api/clip-note-correction-window') return {window: f.windowDocument};
    if (path === '/api/clip-note-correction-projection') return {projection: f.projection};
    if (path === '/api/clip-note-correction-action') return {result};
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml});
  configure(browser);
  browser.renderInto(host);
  await pause();
  click(host.querySelectorAll('[data-open-clip]')[0]);
  await pause();
  click(host.element('clip-correction-kind-onset'));
  submit(host.element('clip-correction-window-form'));
  await pause();
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${hashes.firstRef}`)));
  click(host.data('[data-correction-onset-delta]', '120'));
  click(host.element('clip-correction-review'));
  await pause();
  await pause();
  const reviewHtml = host.innerHTML;
  const createReady = !host.element('clip-correction-create')?.disabled;
  const actionCallsBeforeCreate = calls.filter(call => call.path === '/api/clip-note-correction-action').length;
  click(host.element('clip-correction-create'));
  await pause();
  await pause();
  return {calls, reviewHtml, createReady, actionCallsBeforeCreate, resultHtml: host.innerHTML};
}
(async () => {
  console.log(JSON.stringify({created: await runFlow(false), replayed: await runFlow(true)}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )
        for name in ("created", "replayed"):
            flow = result[name]
            projections = [
                call
                for call in flow["calls"]
                if call["path"] == "/api/clip-note-correction-projection"
            ]
            actions = [
                call
                for call in flow["calls"]
                if call["path"] == "/api/clip-note-correction-action"
            ]
            self.assertEqual(len(projections), 1)
            request = json.loads(projections[0]["body"])
            self.assertEqual(
                request["correction"],
                {
                    "kind": "note_onset_shift_patch",
                    "changes": [
                        {"note_ref": "1" * 64, "target_start_tick": 600}
                    ],
                },
            )
            self.assertEqual(request["window_sha256"], "c" * 64)
            self.assertEqual(flow["actionCallsBeforeCreate"], 0)
            self.assertTrue(flow["createReady"])
            self.assertIn("Exact temporary note-onset review", flow["reviewHtml"])
            self.assertIn("480 → 600", flow["reviewHtml"])
            self.assertIn("720 → 840", flow["reviewHtml"])
            self.assertIn("+120 ticks", flow["reviewHtml"])
            self.assertIn("125 ms", flow["reviewHtml"])
            self.assertIn("Exact MIDI duration stays 240 ticks", flow["reviewHtml"])
            self.assertIn("Effects: zero", flow["reviewHtml"])
            self.assertIn("&lt;unsafe&gt;", flow["reviewHtml"])
            self.assertNotIn("<unsafe>", flow["reviewHtml"])
            self.assertEqual(len(actions), 1)
            action = json.loads(actions[0]["body"])
            self.assertEqual(action["action"], "create")
            self.assertEqual(action["projection_sha256"], "d" * 64)
        self.assertIn(
            "New note-onset-corrected alternative created",
            result["created"]["resultHtml"],
        )
        self.assertIn("created · one library append", result["created"]["resultHtml"])
        self.assertIn(
            "Existing note-onset-corrected alternative verified",
            result["replayed"]["resultHtml"],
        )
        self.assertIn("idempotent replay · effects zero", result["replayed"]["resultHtml"])

    def test_mismatched_projection_and_result_evidence_is_rejected(self) -> None:
        result = self.run_node(
            r"""
(async () => {
  const f = fixture(), calls = [], host = createDynamicHost();
  let previewAttempt = 0;
  const api = async (path, options = {}) => {
    calls.push({path, body: options.body || null});
    if (path.startsWith('/api/clips?')) return listDocument();
    if (path === '/api/clips/keys') return f.detail;
    if (path === '/api/clip-note-correction-window') return {window: f.windowDocument};
    if (path === '/api/clip-note-correction-projection') {
      previewAttempt += 1;
      const projection = JSON.parse(JSON.stringify(f.projection));
      if (previewAttempt === 1) projection.diff.changes[0].after_end_tick = 839;
      if (previewAttempt === 2) projection.unexpected = 'forged';
      if (previewAttempt === 3) projection.child.object_sha256 = hashes.parent;
      return {projection};
    }
    if (path === '/api/clip-note-correction-action') {
      return {result: {
        schema: 'sunofriend.workbench-clip-note-onset-result.v1',
        status: 'created', operation: 'clip-note-onset-correction-create',
        projection_sha256: hashes.projection, replayed: false,
        window: f.projection.window, correction: f.correction,
        parent: f.projection.parent, child: f.projection.child,
        diff: f.diff, warnings: f.projection.warnings,
        library: {expected_state_sha256: hashes.library, previous_state_sha256: hashes.library, current_state_sha256: hashes.nextLibrary},
        effects: {...createdEffects, note_duration_changed: true},
      }};
    }
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml});
  configure(browser);
  browser.renderInto(host);
  await pause();
  click(host.querySelectorAll('[data-open-clip]')[0]);
  await pause();
  click(host.element('clip-correction-kind-onset'));
  submit(host.element('clip-correction-window-form'));
  await pause();
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${hashes.firstRef}`)));
  click(host.data('[data-correction-onset-delta]', '120'));

  click(host.element('clip-correction-review'));
  await pause(); await pause();
  const badRowHtml = host.innerHTML;
  const createAfterBadRow = host.element('clip-correction-create')?.disabled;
  click(host.element('clip-correction-review'));
  await pause(); await pause();
  const extraTopHtml = host.innerHTML;
  const createAfterExtraTop = host.element('clip-correction-create')?.disabled;
  click(host.element('clip-correction-review'));
  await pause(); await pause();
  const sameObjectHtml = host.innerHTML;
  const createAfterSameObject = host.element('clip-correction-create')?.disabled;
  click(host.element('clip-correction-review'));
  await pause(); await pause();
  const validReviewHtml = host.innerHTML;
  const createAfterValid = host.element('clip-correction-create')?.disabled;
  click(host.element('clip-correction-create'));
  await pause(); await pause();
  const badResultHtml = host.innerHTML;
  console.log(JSON.stringify({
    calls, badRowHtml, createAfterBadRow, extraTopHtml, createAfterExtraTop,
    sameObjectHtml, createAfterSameObject, validReviewHtml, createAfterValid,
    badResultHtml,
  }));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )
        self.assertIn("invalid or mismatched zero-effect", result["badRowHtml"])
        self.assertTrue(result["createAfterBadRow"])
        self.assertIn("invalid or mismatched zero-effect", result["extraTopHtml"])
        self.assertTrue(result["createAfterExtraTop"])
        self.assertIn("invalid or mismatched zero-effect", result["sameObjectHtml"])
        self.assertTrue(result["createAfterSameObject"])
        self.assertIn("Exact temporary note-onset review", result["validReviewHtml"])
        self.assertFalse(result["createAfterValid"])
        self.assertIn("invalid or mismatched immutable", result["badResultHtml"])
        self.assertNotIn("New note-onset-corrected alternative created", result["badResultHtml"])
        self.assertEqual(
            len(
                [
                    call
                    for call in result["calls"]
                    if call["path"] == "/api/clip-note-correction-projection"
                ]
            ),
            4,
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

    def test_multi_note_requests_are_canonical_and_capability_limit_is_required(
        self,
    ) -> None:
        result = self.run_node(
            r"""
async function capabilitySupport(limitValue, removeLimit = false, ticksPerBeat = 480, timing = false) {
  const f = fixture(), host = createDynamicHost();
  const capability = JSON.parse(JSON.stringify(onsetCapability));
  if (removeLimit) delete capability.limits.maximum_onset_delta_ticks;
  else capability.limits.maximum_onset_delta_ticks = limitValue;
  capability.limits.ticks_per_beat = ticksPerBeat;
  capability.corrections.timing = timing;
  const api = async (path) => {
    if (path.startsWith('/api/clips?')) return listDocument();
    if (path === '/api/clips/keys') return f.detail;
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml});
  browser.setCapability({
    enabled: true,
    acceptance: {pack_sha256: '8'.repeat(64)},
    library: {clip_count: 1, state_sha256: hashes.library},
  }, null, null, capability);
  browser.renderInto(host);
  await pause();
  click(host.querySelectorAll('[data-open-clip]')[0]);
  await pause();
  return {
    pitch: !!host.element('clip-correction-kind-pitch'),
    onset: !!host.element('clip-correction-kind-onset'),
  };
}

async function multiNoteReview() {
  // Canonical note order is deliberately the reverse of lexical note-ref order.
  hashes.firstRef = 'f'.repeat(64);
  hashes.edgeRef = '0'.repeat(64);
  const f = fixture(), calls = [], host = createDynamicHost();
  f.correction = {
    kind: 'note_onset_shift_patch',
    changes: [
      {note_ref: hashes.edgeRef, target_start_tick: 3360},
      {note_ref: hashes.firstRef, target_start_tick: 600},
    ],
  };
  f.diff = {
    kind: 'note_onset_shift_patch',
    changed_note_count: 2,
    timing_mode: 'musical',
    export_bpm: 120,
    changes: [
      {
        note_ref: hashes.firstRef, channel: 0, pitch: 60,
        before_start_tick: 480, after_start_tick: 600,
        before_end_tick: 720, after_end_tick: 840,
        duration_ticks: 240, tick_delta: 120, milliseconds_delta: 125,
        before_start_beat: 1, after_start_beat: 1.25,
        before_source_start_seconds: .5, after_source_start_seconds: .65,
      },
      {
        note_ref: hashes.edgeRef, channel: 0, pitch: 64,
        before_start_tick: 3480, after_start_tick: 3360,
        before_end_tick: 3720, after_end_tick: 3600,
        duration_ticks: 240, tick_delta: -120, milliseconds_delta: -125,
        before_start_beat: 7.25, after_start_beat: 7,
        before_source_start_seconds: 3.625, after_source_start_seconds: 3.5,
      },
    ],
  };
  f.projection.correction = f.correction;
  f.projection.diff = f.diff;
  const api = async (path, options = {}) => {
    calls.push({path, body: options.body || null});
    if (path.startsWith('/api/clips?')) return listDocument();
    if (path === '/api/clips/keys') return f.detail;
    if (path === '/api/clip-note-correction-window') return {window: f.windowDocument};
    if (path === '/api/clip-note-correction-projection') return {projection: f.projection};
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml});
  configure(browser);
  browser.renderInto(host);
  await pause();
  click(host.querySelectorAll('[data-open-clip]')[0]);
  await pause();
  click(host.element('clip-correction-kind-onset'));
  submit(host.element('clip-correction-window-form'));
  await pause();
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${hashes.firstRef}`)));
  click(host.data('[data-correction-onset-delta]', '120'));
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${hashes.edgeRef}`)));
  click(host.data('[data-correction-onset-delta]', '-120'));
  click(host.element('clip-correction-review'));
  await pause(); await pause();
  const call = calls.find(item => item.path === '/api/clip-note-correction-projection');
  return {
    request: call ? JSON.parse(call.body) : null,
    createDisabled: host.element('clip-correction-create')?.disabled,
    html: host.innerHTML,
  };
}

(async () => {
  console.log(JSON.stringify({
    exact: await capabilitySupport(480),
    missing: await capabilitySupport(null, true),
    wrong: await capabilitySupport(479),
    stringValue: await capabilitySupport('480'),
    wrongTicksPerBeat: await capabilitySupport(480, false, 960),
    wrongTimingCapability: await capabilitySupport(480, false, 480, true),
    multi: await multiNoteReview(),
  }));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )
        self.assertTrue(result["exact"]["pitch"])
        self.assertTrue(result["exact"]["onset"])
        for name in (
            "missing",
            "wrong",
            "stringValue",
            "wrongTicksPerBeat",
            "wrongTimingCapability",
        ):
            self.assertTrue(result[name]["pitch"])
            self.assertFalse(result[name]["onset"])
        self.assertEqual(
            result["multi"]["request"]["correction"]["changes"],
            [
                {"note_ref": "0" * 64, "target_start_tick": 3360},
                {"note_ref": "f" * 64, "target_start_tick": 600},
            ],
        )
        self.assertFalse(result["multi"]["createDisabled"])
        self.assertIn("Exact temporary note-onset review", result["multi"]["html"])

    def test_stem_locked_roll_and_source_delta_use_exact_tick_contract(self) -> None:
        result = self.run_node(
            r"""
(async () => {
  const f = fixture(), calls = [], host = createDynamicHost();
  f.windowDocument.timing = {resolved_mode: 'stem_locked', export_bpm: 120};
  f.detail.clip.timing_contract = {resolved_mode: 'stem_locked', export_bpm: 120};
  f.windowDocument.notes[0].start_beat = 4;
  f.windowDocument.notes[0].duration_beats = 2;
  f.diff.timing_mode = 'stem_locked';
  f.diff.changes[0].before_start_beat = 4;
  f.diff.changes[0].after_start_beat = 4.25;
  f.diff.changes[0].before_source_start_seconds = .5;
  f.diff.changes[0].after_source_start_seconds = .9;
  f.projection.diff = f.diff;
  let previewAttempt = 0;
  const api = async (path, options = {}) => {
    calls.push({path, body: options.body || null});
    if (path.startsWith('/api/clips?')) return listDocument();
    if (path === '/api/clips/keys') return f.detail;
    if (path === '/api/clip-note-correction-window') return {window: f.windowDocument};
    if (path === '/api/clip-note-correction-projection') {
      previewAttempt += 1;
      const projection = JSON.parse(JSON.stringify(f.projection));
      if (previewAttempt === 2) {
        projection.diff.changes[0].after_source_start_seconds = .625;
      }
      return {projection};
    }
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml});
  configure(browser);
  browser.renderInto(host);
  await pause();
  click(host.querySelectorAll('[data-open-clip]')[0]);
  await pause();
  click(host.element('clip-correction-kind-onset'));
  submit(host.element('clip-correction-window-form'));
  await pause();
  const rollHtml = host.innerHTML;
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${hashes.firstRef}`)));
  click(host.data('[data-correction-onset-delta]', '120'));
  click(host.element('clip-correction-review'));
  await pause(); await pause();
  const forgedHtml = host.innerHTML;
  const createAfterForgery = host.element('clip-correction-create')?.disabled;
  click(host.element('clip-correction-review'));
  await pause(); await pause();
  console.log(JSON.stringify({
    calls, rollHtml, forgedHtml, createAfterForgery,
    validHtml: host.innerHTML,
    createAfterValid: host.element('clip-correction-create')?.disabled,
  }));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )
        self.assertIn('x="135.5"', result["rollHtml"])
        self.assertIn('width="43.75"', result["rollHtml"])
        self.assertNotIn('x="398"', result["rollHtml"])
        self.assertIn("invalid or mismatched zero-effect", result["forgedHtml"])
        self.assertTrue(result["createAfterForgery"])
        self.assertIn("Exact temporary note-onset review", result["validHtml"])
        self.assertFalse(result["createAfterValid"])

    def test_onset_window_rejects_forged_timing_and_parent_membership(self) -> None:
        result = self.run_node(
            r"""
async function rejectedWindow(kind) {
  const f = fixture(), host = createDynamicHost();
  if (kind === 'stem-editable-microtiming') {
    f.windowDocument.timing = {resolved_mode: 'stem_locked', export_bpm: 120};
    f.windowDocument.notes[0].microtiming_seconds = .01;
  } else if (kind === 'musical-unsupported-reason') {
    const row = f.windowDocument.notes[0];
    row.editable = false;
    row.edit_block_reason = 'unsupported-stem-locked-microtiming';
    row.microtiming_seconds = .01;
    f.windowDocument.editable_note_count = 1;
    f.windowDocument.blocked_note_count = 2;
    f.windowDocument.blocked_reason_counts['unsupported-stem-locked-microtiming'] = 1;
  } else if (kind === 'too-many-parent-rows') {
    f.windowDocument.notes.push(note('4'.repeat(64), {
      pitch: 63, start_tick: 3000, end_tick: 3240,
      start_beat: 6.25, source_start_seconds: 3.125,
      source_end_seconds: 3.375,
    }));
    f.windowDocument.visible_note_count = 4;
    f.windowDocument.editable_note_count = 3;
  } else if (kind === 'wrong-parent-channel') {
    f.windowDocument.notes[0].channel = 1;
  } else if (kind === 'outside-parent-pitch-range') {
    f.windowDocument.notes[0].pitch = 65;
  }
  const api = async (path) => {
    if (path.startsWith('/api/clips?')) return listDocument();
    if (path === '/api/clips/keys') return f.detail;
    if (path === '/api/clip-note-correction-window') return {window: f.windowDocument};
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml});
  configure(browser);
  browser.renderInto(host);
  await pause();
  click(host.querySelectorAll('[data-open-clip]')[0]);
  await pause();
  click(host.element('clip-correction-kind-onset'));
  submit(host.element('clip-correction-window-form'));
  await pause(); await pause();
  return {
    html: host.innerHTML,
    hasNoteList: !!host.element('clip-correction-note-list'),
  };
}
(async () => {
  const kinds = [
    'stem-editable-microtiming', 'musical-unsupported-reason',
    'too-many-parent-rows', 'wrong-parent-channel',
    'outside-parent-pitch-range',
  ];
  const results = {};
  for (const kind of kinds) results[kind] = await rejectedWindow(kind);
  console.log(JSON.stringify(results));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )
        for case in result.values():
            self.assertIn("invalid bounded note window", case["html"])
            self.assertFalse(case["hasNoteList"])

    def test_conflict_reloads_once_without_write_and_keeps_valid_draft(self) -> None:
        result = self.run_node(
            r"""
(async () => {
  const f = fixture(), calls = [], host = createDynamicHost();
  const api = async (path, options = {}) => {
    calls.push({path, body: options.body || null});
    if (path.startsWith('/api/clips?')) return listDocument();
    if (path === '/api/clips/keys') return f.detail;
    if (path === '/api/clip-note-correction-window') return {window: f.windowDocument};
    if (path === '/api/clip-note-correction-projection') {
      const error = new Error('simulated conflict');
      error.status = 409;
      throw error;
    }
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml});
  configure(browser);
  browser.renderInto(host);
  await pause();
  click(host.querySelectorAll('[data-open-clip]')[0]);
  await pause();
  click(host.element('clip-correction-kind-onset'));
  submit(host.element('clip-correction-window-form'));
  await pause();
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${hashes.firstRef}`)));
  click(host.data('[data-correction-onset-delta]', '120'));
  click(host.element('clip-correction-review'));
  await pause(); await pause(); await pause(); await pause();
  console.log(JSON.stringify({calls, html: host.innerHTML, reviewDisabled: host.element('clip-correction-review')?.disabled}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )
        paths = [call["path"] for call in result["calls"]]
        self.assertEqual(paths.count("/api/clips/keys"), 2)
        self.assertEqual(paths.count("/api/clip-note-correction-window"), 2)
        self.assertEqual(paths.count("/api/clip-note-correction-projection"), 1)
        self.assertEqual(paths.count("/api/clip-note-correction-action"), 0)
        self.assertIn("changed while reviewing", result["html"])
        self.assertIn("draft start tick 600", result["html"])
        self.assertFalse(result["reviewDisabled"])


if __name__ == "__main__":
    unittest.main()
