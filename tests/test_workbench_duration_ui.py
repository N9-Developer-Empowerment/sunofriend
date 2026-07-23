from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


CLIPS_PATH = Path("src/sunofriend/workbench_clips.js").resolve()


class WorkbenchDurationUiTests(unittest.TestCase):
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
    '[data-correction-note-end-delta]': ['correctionNoteEndDelta', 'data-correction-note-end-delta'],
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
  nextLibrary: '9'.repeat(64), firstRef: '1'.repeat(64),
  blockedRef: '2'.repeat(64), edgeRef: '3'.repeat(64),
};
const effectKeys = [
  'library_mutated', 'child_clip_created', 'source_clip_mutated',
  'correction_applied', 'note_onset_changed', 'note_timing_changed',
  'note_duration_changed', 'note_pitch_changed', 'note_attack_velocity_changed',
  'release_velocity_changed', 'note_count_changed', 'key_changed',
  'chords_changed', 'instrument_changed', 'provenance_changed',
  'reuse_plan_changed', 'placement_changed', 'current_arrangement_changed',
  'pack_changed', 'hybrid_created', 'feedback_recorded', 'data_submitted',
];
const effects = Object.fromEntries(effectKeys.map(key => [key, false]));
const createdEffects = {
  ...effects,
  library_mutated: true,
  child_clip_created: true,
  correction_applied: true,
  note_duration_changed: true,
  note_timing_changed: true,
};
const durationUnchanged = {
  note_count: true,
  unaffected_note_payloads: true,
  note_pitches: true,
  note_onsets: true,
  source_start_seconds: true,
  velocity: true,
  release_velocity: true,
  microtiming: true,
  articulation: true,
  clip_horizons: true,
  tempo_map: true,
  timing_mode: true,
  key: true,
  chords: true,
  instrument: true,
  provenance: true,
};
const durationCapability = {
  enabled: true,
  actions: {window: true, preview: true, create: true},
  corrections: {
    pitch_patch: {enabled: true, drum_family: false},
    attack_velocity_patch: {enabled: true, drum_family: true},
    note_delete_patch: {enabled: true, drum_family: true},
    note_onset_shift_patch: {enabled: true, drum_family: true},
    note_end_shift_patch: {enabled: true, drum_family: true},
    malicious_unknown_patch: {enabled: true, drum_family: true},
    timing: false,
  },
  limits: {
    ticks_per_beat: 480,
    maximum_window_beats: 32,
    maximum_changes: 64,
    maximum_pitch_delta_semitones: 24,
    maximum_onset_delta_ticks: 480,
    maximum_note_end_delta_ticks: 480,
    minimum_note_duration_ticks: 1,
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
function fixture({timingMode = 'musical'} = {}) {
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
      start_tick: 3360,
      end_tick: 3600,
      start_beat: 7,
      source_start_seconds: 3.5,
      source_end_seconds: 3.75,
    }),
  ];
  const windowDocument = {
    schema: 'sunofriend.workbench-clip-note-end-window.v1',
    operation: 'clip-note-end-window',
    correction_kind: 'note_end_shift_patch',
    library: {state_sha256: hashes.library},
    parent: identity(),
    window: {start_tick: 0, end_tick: 3840, ticks_per_beat: 480, duration_seconds: 4, origin: 'recorded-zero'},
    timing: {resolved_mode: timingMode, export_bpm: 120},
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
      editable_membership: 'unique exact normalized MIDI lifetime fully contained in the loaded half-open window',
      context_membership: 'export interval intersects the window but is not fully contained',
      correction_scope: 'bounded existing-note end shift only; stem-locked notes require zero microtiming',
      maximum_end_delta_ticks: 480,
      minimum_duration_ticks: 1,
      duplicate_export_note_on: 'same channel, start tick and pitch is visible but not editable',
      normalized_lifetime: 'notes whose own Note Off is changed by normalization are not editable',
    },
    effects,
    window_sha256: hashes.window,
  };
  const correction = {
    kind: 'note_end_shift_patch',
    changes: [{note_ref: hashes.firstRef, target_end_tick: 840}],
  };
  const diff = {
    kind: 'note_end_shift_patch',
    changed_note_count: 1,
    timing_mode: timingMode,
    export_bpm: 120,
    changes: [{
      note_ref: hashes.firstRef,
      channel: 0,
      pitch: 60,
      start_tick: 480,
      before_end_tick: 720,
      after_end_tick: 840,
      before_duration_ticks: 240,
      after_duration_ticks: 360,
      tick_delta: 120,
      milliseconds_delta: 125,
      start_beat: 1,
      before_duration_beats: .5,
      after_duration_beats: .75,
      source_start_seconds: .5,
      before_source_end_seconds: .75,
      after_source_end_seconds: .875,
    }],
  };
  const childId = `sf-correction-${hashes.intent}`;
  const projection = {
    schema: 'sunofriend.workbench-clip-note-end-preview.v1',
    status: 'previewed',
    operation: 'clip-note-end-correction-preview',
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
      duration: {beats: 8, source_end_seconds: 4, export_seconds: 4},
      timing_contract: {resolved_mode: timingMode, export_bpm: 120},
      instrument: {program: 4, channel: 0},
    },
    lineage: {lineage_id: 'lineage-1', versions: []},
  };
  const childDetail = {
    library_state_sha256: hashes.nextLibrary,
    clip: {
      ...detail.clip,
      clip_id: childId,
      object_sha256: hashes.child,
      parent_clip_id: 'keys',
      revision: 2,
      title: 'Keys note-end correction',
      transform: {
        operation: 'shift_note_ends',
        parameters_exposed: false,
        seed_exposed: false,
      },
    },
    lineage: {
      lineage_id: 'lineage-1',
      versions: [
        {
          clip_id: 'keys',
          title: 'Keys',
          title_redacted: false,
          revision: 1,
          parent_clip_id: null,
          key: 'B minor',
          bpm: 120,
          role: 'keys',
          role_redacted: false,
          object_sha256: hashes.parent,
          transform_operation: null,
          transform_parameters_exposed: false,
        },
        {
          clip_id: childId,
          title: 'Keys note-end correction',
          title_redacted: false,
          revision: 2,
          parent_clip_id: 'keys',
          key: 'B minor',
          bpm: 120,
          role: 'keys',
          role_redacted: false,
          object_sha256: hashes.child,
          transform_operation: 'shift_note_ends',
          transform_parameters_exposed: false,
        },
      ],
    },
    correction_summary: {
      schema: 'sunofriend.workbench-clip-note-end-summary.v1',
      operation: 'shift_note_ends',
      contract_version: 1,
      parent_clip_id: 'keys',
      parent_object_sha256: hashes.parent,
      child_clip_id: childId,
      child_object_sha256: hashes.child,
      window: {start_tick: 0, end_tick: 3840, ticks_per_beat: 480},
      changed_note_count: 1,
      timing_mode: timingMode,
      export_bpm: 120,
      changes: diff.changes,
      unchanged: durationUnchanged,
      library_state_sha256: hashes.nextLibrary,
      parent: identity(),
      child: identity({clipId: childId, objectHash: hashes.child, parentClipId: 'keys', revision: 2}),
      effects,
    },
  };
  return {notes, windowDocument, correction, diff, projection, detail, childDetail, childId};
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
function configure(browser, capability = durationCapability) {
  browser.setCapability({
    enabled: true,
    acceptance: {pack_sha256: '8'.repeat(64)},
    library: {clip_count: 1, state_sha256: hashes.library},
  }, null, null, capability);
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

    def test_note_end_is_explicit_bounded_accessible_and_capability_exact(self) -> None:
        result = self.run_node(
            r"""
async function supported(overrides = {}) {
  const f = fixture(), host = createDynamicHost();
  const capability = JSON.parse(JSON.stringify(durationCapability));
  if ('max' in overrides) capability.limits.maximum_note_end_delta_ticks = overrides.max;
  if (overrides.removeMax) delete capability.limits.maximum_note_end_delta_ticks;
  if ('min' in overrides) capability.limits.minimum_note_duration_ticks = overrides.min;
  if (overrides.removeMin) delete capability.limits.minimum_note_duration_ticks;
  if ('tpq' in overrides) capability.limits.ticks_per_beat = overrides.tpq;
  if ('timing' in overrides) capability.corrections.timing = overrides.timing;
  const api = async path => {
    if (path.startsWith('/api/clips?')) return listDocument();
    if (path === '/api/clips/keys') return f.detail;
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml});
  configure(browser, capability);
  browser.renderInto(host);
  await pause();
  click(host.querySelectorAll('[data-open-clip]')[0]);
  await pause();
  return !!host.element('clip-correction-kind-note-end');
}
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
  const initialHtml = host.innerHTML;
  click(host.element('clip-correction-kind-note-end'));
  submit(host.element('clip-correction-window-form'));
  await pause();
  const loadedHtml = host.innerHTML;
  const callsBeforeInspection = calls.length;
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${hashes.firstRef}`)));
  host.element('clip-correction-exact-note-end').value = '840';
  const afterTyping = {calls: calls.length, reviewDisabled: host.element('clip-correction-review')?.disabled, html: host.innerHTML};
  host.element('clip-correction-exact-note-end').value = '720';
  submit(host.element('clip-correction-note-end-form'));
  const noOpHtml = host.innerHTML;
  host.element('clip-correction-exact-note-end').value = '720.5';
  submit(host.element('clip-correction-note-end-form'));
  const fractionalHtml = host.innerHTML;
  host.element('clip-correction-exact-note-end').value = '480';
  submit(host.element('clip-correction-note-end-form'));
  const tooShortHtml = host.innerHTML;
  host.element('clip-correction-exact-note-end').value = '1300';
  submit(host.element('clip-correction-note-end-form'));
  const tooFarHtml = host.innerHTML;
  host.element('clip-correction-exact-note-end').value = '3900';
  submit(host.element('clip-correction-note-end-form'));
  const outsideHtml = host.innerHTML;
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${hashes.blockedRef}`)));
  const blockedDisabled = host.data('[data-correction-note-ref]', encodeURIComponent(`value:${hashes.blockedRef}`))?.disabled;
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${hashes.firstRef}`)));
  click(host.data('[data-correction-note-end-delta]', '120'));
  const draftedHtml = host.innerHTML;
  const pitchSwitchDisabled = host.element('clip-correction-kind-pitch')?.disabled;
  click(host.element('clip-correction-reset-all'));
  const resetHtml = host.innerHTML;
  console.log(JSON.stringify({
    calls, callsBeforeInspection, initialHtml, loadedHtml, afterTyping, noOpHtml,
    fractionalHtml, tooShortHtml, tooFarHtml, outsideHtml, blockedDisabled,
    draftedHtml, pitchSwitchDisabled, resetHtml,
    support: {
      exact: await supported(), missingMax: await supported({removeMax: true}),
      wrongMax: await supported({max: 479}), stringMax: await supported({max: '480'}),
      missingMin: await supported({removeMin: true}), wrongMin: await supported({min: 2}),
      wrongTpq: await supported({tpq: 960}), genericTiming: await supported({timing: true}),
    },
  }));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )
        windows = [
            call
            for call in result["calls"]
            if call["path"] == "/api/clip-note-correction-window"
        ]
        self.assertIn("Change existing note length (MIDI Note Off)", result["initialHtml"])
        self.assertNotIn("malicious_unknown_patch", result["initialHtml"])
        self.assertEqual(len(windows), 1)
        self.assertEqual(
            json.loads(windows[0]["body"])["correction_kind"],
            "note_end_shift_patch",
        )
        self.assertIn("MIDI Note On remains fixed", result["loadedHtml"])
        self.assertIn("one-shot and drum patches may ignore", result["loadedHtml"])
        self.assertEqual(result["callsBeforeInspection"], result["afterTyping"]["calls"])
        self.assertTrue(result["afterTyping"]["reviewDisabled"])
        self.assertIn("immutable parent end tick", result["noOpHtml"])
        self.assertIn("whole nonnegative integer", result["fractionalHtml"])
        self.assertIn("at least 1 tick after", result["tooShortHtml"])
        self.assertIn("within 480 ticks", result["tooFarHtml"])
        self.assertIn("stay inside this exact window", result["outsideHtml"])
        self.assertTrue(result["blockedDisabled"])
        self.assertIn("duplicate exported Note On", result["loadedHtml"])
        self.assertTrue(result["pitchSwitchDisabled"])
        self.assertIn("draft end tick 840", result["draftedHtml"])
        self.assertIn("draft length 360 ticks", result["draftedHtml"])
        self.assertIn("gold is the temporary note-duration draft", result["draftedHtml"])
        self.assertIn("All temporary note-end changes were reset", result["resetHtml"])
        self.assertEqual(
            result["support"],
            {
                "exact": True,
                "missingMax": False,
                "wrongMax": False,
                "stringMax": False,
                "missingMin": False,
                "wrongMin": False,
                "wrongTpq": False,
                "genericTiming": False,
            },
        )

    def test_exact_review_create_replay_and_restored_summary(self) -> None:
        result = self.run_node(
            r"""
async function runFlow(replayed) {
  const f = fixture(), calls = [], host = createDynamicHost();
  const result = {
    schema: 'sunofriend.workbench-clip-note-end-result.v1',
    status: replayed ? 'replayed' : 'created',
    operation: 'clip-note-end-correction-create',
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
    if (path === `/api/clips/${f.childId}`) return f.childDetail;
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
  click(host.element('clip-correction-kind-note-end'));
  submit(host.element('clip-correction-window-form'));
  await pause();
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${hashes.firstRef}`)));
  click(host.data('[data-correction-note-end-delta]', '120'));
  click(host.element('clip-correction-review'));
  await pause(); await pause();
  const reviewHtml = host.innerHTML;
  click(host.element('clip-correction-create'));
  await pause(); await pause();
  const resultHtml = host.innerHTML;
  click(host.element('clip-correction-inspect-child'));
  await pause(); await pause();
  return {calls, reviewHtml, resultHtml, summaryHtml: host.innerHTML};
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
                    "kind": "note_end_shift_patch",
                    "changes": [{"note_ref": "1" * 64, "target_end_tick": 840}],
                },
            )
            self.assertEqual(request["window_sha256"], "c" * 64)
            self.assertIn("Exact temporary note-end review", flow["reviewHtml"])
            self.assertIn("720 → 840", flow["reviewHtml"])
            self.assertIn("240 → 360 ticks", flow["reviewHtml"])
            self.assertIn("+120 ticks", flow["reviewHtml"])
            self.assertIn("125 ms", flow["reviewHtml"])
            self.assertIn("Every MIDI Note On stays fixed", flow["reviewHtml"])
            self.assertIn("Effects: zero", flow["reviewHtml"])
            self.assertIn("&lt;unsafe&gt;", flow["reviewHtml"])
            self.assertNotIn("<unsafe>", flow["reviewHtml"])
            self.assertEqual(len(actions), 1)
            action = json.loads(actions[0]["body"])
            self.assertEqual(action["action"], "create")
            self.assertEqual(action["projection_sha256"], "d" * 64)
            self.assertIn("Saved note-end correction", flow["summaryHtml"])
            self.assertIn("Note On stayed at tick 480", flow["summaryHtml"])
            self.assertIn("Clip horizon stayed exact", flow["summaryHtml"])
        self.assertIn(
            "New note-end-corrected alternative created",
            result["created"]["resultHtml"],
        )
        self.assertIn("created · one library append", result["created"]["resultHtml"])
        self.assertIn(
            "Existing note-end-corrected alternative verified",
            result["replayed"]["resultHtml"],
        )
        self.assertIn("idempotent replay · effects zero", result["replayed"]["resultHtml"])

    def test_forged_window_projection_and_result_fail_closed(self) -> None:
        result = self.run_node(
            r"""
(async () => {
  const f = fixture(), calls = [], host = createDynamicHost();
  let windowAttempt = 0, previewAttempt = 0;
  const api = async (path, options = {}) => {
    calls.push({path, body: options.body || null});
    if (path.startsWith('/api/clips?')) return listDocument();
    if (path === '/api/clips/keys') return f.detail;
    if (path === '/api/clip-note-correction-window') {
      windowAttempt += 1;
      const document = JSON.parse(JSON.stringify(f.windowDocument));
      if (windowAttempt === 1) document.unexpected = true;
      if (windowAttempt === 2) document.policies.maximum_end_delta_ticks = 479;
      return {window: document};
    }
    if (path === '/api/clip-note-correction-projection') {
      previewAttempt += 1;
      const projection = JSON.parse(JSON.stringify(f.projection));
      if (previewAttempt === 1) projection.diff.changes[0].start_tick = 481;
      if (previewAttempt === 2) projection.diff.changes[0].after_duration_beats = .74;
      if (previewAttempt === 3) projection.unexpected = true;
      return {projection};
    }
    if (path === '/api/clip-note-correction-action') {
      return {result: {
        schema: 'sunofriend.workbench-clip-note-end-result.v1',
        status: 'created', operation: 'clip-note-end-correction-create',
        projection_sha256: hashes.projection, replayed: false,
        window: f.projection.window, correction: f.correction,
        parent: f.projection.parent, child: f.projection.child,
        diff: f.diff, warnings: f.projection.warnings,
        library: {expected_state_sha256: hashes.library, previous_state_sha256: hashes.library, current_state_sha256: hashes.nextLibrary},
        effects: {...createdEffects, note_onset_changed: true},
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
  click(host.element('clip-correction-kind-note-end'));
  submit(host.element('clip-correction-window-form'));
  await pause(); await pause();
  const extraWindowHtml = host.innerHTML;
  submit(host.element('clip-correction-window-form'));
  await pause(); await pause();
  const policyHtml = host.innerHTML;
  submit(host.element('clip-correction-window-form'));
  await pause(); await pause();
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${hashes.firstRef}`)));
  click(host.data('[data-correction-note-end-delta]', '120'));
  const reviewHtml = [];
  for (let index = 0; index < 4; index += 1) {
    click(host.element('clip-correction-review'));
    await pause(); await pause();
    reviewHtml.push(host.innerHTML);
  }
  click(host.element('clip-correction-create'));
  await pause(); await pause();
  console.log(JSON.stringify({calls, extraWindowHtml, policyHtml, reviewHtml, resultHtml: host.innerHTML}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )
        self.assertIn("invalid bounded note window", result["extraWindowHtml"])
        self.assertIn("invalid bounded note window", result["policyHtml"])
        for html in result["reviewHtml"][:3]:
            self.assertIn("invalid or mismatched zero-effect", html)
        self.assertIn("Exact temporary note-end review", result["reviewHtml"][3])
        self.assertIn("invalid or mismatched immutable", result["resultHtml"])
        self.assertNotIn("New note-end-corrected alternative created", result["resultHtml"])
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

    def test_musical_warp_source_delta_need_not_equal_export_delta(self) -> None:
        result = self.run_node(
            r"""
(async () => {
  const f = fixture(), calls = [], host = createDynamicHost();
  f.projection.diff.changes[0].after_source_end_seconds = .95;
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
  click(host.element('clip-correction-kind-note-end'));
  submit(host.element('clip-correction-window-form'));
  await pause();
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${hashes.firstRef}`)));
  click(host.data('[data-correction-note-end-delta]', '120'));
  click(host.element('clip-correction-review'));
  await pause(); await pause();
  console.log(JSON.stringify({calls, reviewHtml: host.innerHTML}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )
        self.assertIn("Exact temporary note-end review", result["reviewHtml"])
        self.assertIn("125 ms", result["reviewHtml"])
        self.assertIn("0.75 → 0.95 s", result["reviewHtml"])
        self.assertNotIn("invalid or mismatched", result["reviewHtml"])

    def test_malformed_restart_summary_fails_closed(self) -> None:
        result = self.run_node(
            r"""
async function restored(mutator = null) {
  const f = fixture(), host = createDynamicHost();
  if (mutator) mutator(f.childDetail.correction_summary, f.childDetail);
  const listing = listDocument();
  listing.clips[0] = {
    ...listing.clips[0],
    clip_id: f.childId,
    object_sha256: hashes.child,
    revision: 2,
  };
  const api = async path => {
    if (path.startsWith('/api/clips?')) return listing;
    if (path === `/api/clips/${f.childId}`) return f.childDetail;
    throw new Error(`unexpected ${path}`);
  };
  const browser = clips.createClipLibrary({api, escapeHtml});
  configure(browser);
  browser.renderInto(host);
  await pause();
  click(host.querySelectorAll('[data-open-clip]')[0]);
  await pause();
  return host.innerHTML;
}
(async () => {
  console.log(JSON.stringify({
    valid: await restored(),
    extra: await restored(summary => { summary.unexpected = true; }),
    schema: await restored(summary => { summary.schema = 'sunofriend.workbench-clip-note-end-summary.v2'; }),
    childPin: await restored(summary => { summary.child_object_sha256 = '8'.repeat(64); }),
    detailPin: await restored(summary => { summary.child.object_sha256 = '8'.repeat(64); }),
    count: await restored(summary => { summary.changed_note_count = 2; }),
    row: await restored(summary => { summary.changes[0].after_duration_ticks = 359; }),
    unchanged: await restored(summary => { summary.unchanged.note_onsets = false; }),
    effects: await restored(summary => { summary.effects.note_duration_changed = true; }),
    tpq: await restored(summary => { summary.window.ticks_per_beat = 960; }),
    timing: await restored(summary => { summary.timing_mode = 'stem_locked'; }),
    bpm: await restored(summary => { summary.export_bpm = 999; }),
    duration: await restored(summary => {
      summary.parent.duration_seconds = 99;
      summary.child.duration_seconds = 99;
    }),
    channel: await restored(summary => { summary.changes[0].channel = 15; }),
    pitch: await restored(summary => { summary.changes[0].pitch = 10; }),
    parentPin: await restored(summary => {
      summary.parent_object_sha256 = '7'.repeat(64);
      summary.parent.object_sha256 = '7'.repeat(64);
    }),
    transform: await restored((_summary, detail) => {
      detail.clip.transform.operation = 'shift_note_onsets';
    }),
  }));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )
        self.assertIn("Saved note-end correction", result["valid"])
        self.assertNotIn("evidence unavailable", result["valid"])
        for name, html in result.items():
            if name == "valid":
                continue
            self.assertIn("Saved note-end correction evidence unavailable", html)
            self.assertNotIn(
                "<h3 id=\"clip-correction-summary-heading\">Saved note-end correction</h3>",
                html,
            )

    def test_stem_locked_exact_end_delta_and_microtiming_block(self) -> None:
        result = self.run_node(
            r"""
(async () => {
  const f = fixture({timingMode: 'stem_locked'}), calls = [], host = createDynamicHost();
  f.windowDocument.notes[1] = note(hashes.blockedRef, {
    editable: false,
    edit_block_reason: 'unsupported-stem-locked-microtiming',
    pitch: 62,
    start_tick: 960,
    end_tick: 1200,
    start_beat: 2,
    source_start_seconds: 1,
    source_end_seconds: 1.25,
    microtiming_seconds: .01,
  });
  f.windowDocument.blocked_reason_counts = {
    'context-note-outside-window': 0,
    'duplicate-export-note-on': 0,
    'normalized-lifetime-dependent': 0,
    'unsupported-stem-locked-microtiming': 1,
  };
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
  click(host.element('clip-correction-kind-note-end'));
  submit(host.element('clip-correction-window-form'));
  await pause();
  const loadedHtml = host.innerHTML;
  click(host.data('[data-correction-note-ref]', encodeURIComponent(`value:${hashes.firstRef}`)));
  click(host.data('[data-correction-note-end-delta]', '120'));
  click(host.element('clip-correction-review'));
  await pause(); await pause();
  console.log(JSON.stringify({calls, loadedHtml, reviewHtml: host.innerHTML}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )
        self.assertIn(
            "stem-locked note has microtiming that note-end correction",
            result["loadedHtml"],
        )
        self.assertIn("Exact temporary note-end review", result["reviewHtml"])
        self.assertIn("125 ms", result["reviewHtml"])
        self.assertNotIn("invalid or mismatched", result["reviewHtml"])


if __name__ == "__main__":
    unittest.main()
