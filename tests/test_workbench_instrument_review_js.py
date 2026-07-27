from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


FIXTURES = r"""
const sha = character => character.repeat(64);

function bassCoverage() {
  return {
    schema: "sunofriend.workbench-instrument-review.keys-coverage.v1",
    required: false,
    status: "not_required",
    functional_status: "not_required",
    quality_status: "review_required",
    actual_review_midi_changed: false,
  };
}

function keysCoverage() {
  const candidate = {
    functional_status: "passed",
    tested_zone_count: 4,
    passed_zone_count: 4,
    failed_zone_count: 0,
    minimum_rms_dbfs: -30,
    minimum_peak_dbfs: -20,
    minimum_active_above_pre_guard_db: 4,
    maximum_normalized_rms_deficit_db: 2,
  };
  return {
    schema: "sunofriend.workbench-instrument-review.keys-coverage.v1",
    required: true,
    status: "passed",
    functional_status: "passed",
    quality_status: "review_required",
    policy: "deterministic-observed-pitch-velocity-bucket-probe-v1",
    claim: "representative-used-pitch-velocity-bucket-coverage",
    zone_definition: "one zone per observed channel, pitch and velocity bucket; the minimum velocity actually observed in that zone is tested",
    safe_pass_text: "Both complete keyboard proxies produced measurable responses for each representative pitch and used velocity bucket tested from this selected MIDI. Tone, musical fit, chord clarity, every exact velocity, pitch correctness and GarageBand equivalence still require listening.",
    non_claims: [
      "not every exact used velocity is tested",
      "pitch correctness and octave mapping are not proven",
      "polyphonic chord and per-voice clarity are not proven",
      "tone, musical fit and GarageBand equivalence are not proven",
    ],
    velocity_buckets: [
      {id: "soft", minimum: 1, maximum: 42, tested_zone_count: 1, status: "passed"},
      {id: "medium", minimum: 43, maximum: 84, tested_zone_count: 2, status: "passed"},
      {id: "strong", minimum: 85, maximum: 127, tested_zone_count: 1, status: "passed"},
    ],
    tested_zone_count: 4,
    tested_pitch_count: 3,
    failed_zone_count: 0,
    limits: {
      maximum_zones: 512,
      maximum_probe_seconds: 180,
      probe_note_seconds: 0.2,
      probe_slot_seconds: 0.35,
    },
    thresholds: {
      both_absolute_gates_required: true,
      minimum_rms_dbfs: -72,
      minimum_peak_dbfs: -60,
      minimum_active_above_pre_guard_db: 3,
      maximum_velocity_normalized_rms_deficit_db: 24,
      singleton_channel_bucket_uses_absolute_gates_only: true,
    },
    candidates: {
      candidate_a: {...candidate},
      candidate_b: {...candidate, minimum_rms_dbfs: -28},
    },
    candidate_identities_hidden: true,
    actual_review_midi_changed: false,
  };
}

function plan(overrides = {}) {
  const selection = overrides.selection || "a";
  const role = overrides.role || "bass";
  return {
    schema: "sunofriend.workbench-instrument-review-plan.v1",
    selection_manifest_sha256: sha(selection),
    eligible_lanes: [{
      selection_manifest_sha256: sha(selection),
      stem_id: overrides.stemId || "stem-bass",
      candidate_id: overrides.candidateId || "candidate-bass",
      midi_sha256: sha(overrides.midi || "b"),
      role,
      label: `Selected ${role}`,
      coverage_preflight:
        overrides.coverage || (role === "keys" ? "required" : "not_required"),
      pair: {
        description: role === "keys"
          ? "Electric Piano 1 versus Electric Piano 2"
          : "Synth Bass 1 versus Synth Bass 2",
        control: {
          label: role === "keys"
            ? "Electric Piano 1"
            : "Synth Bass 1",
        },
        challenger: {
          label: role === "keys"
            ? "Electric Piano 2"
            : "Synth Bass 2",
        },
      },
    }],
    effects: {
      midi_changed: false,
      instrument_default_changed: false,
      pack_changed: false,
      mix_changed: false,
      feedback_recorded: false,
    },
  };
}

function comparison(overrides = {}) {
  const status = overrides.status || "unreviewed";
  const role = overrides.role || "bass";
  const value = {
    schema: "sunofriend.workbench-instrument-review.comparison.v1",
    status,
    blind: status !== "resolved",
    comparison_sha256: sha(overrides.comparison || "c"),
    selection_manifest_sha256: sha(overrides.selection || "a"),
    stem_id: overrides.stemId || "stem-bass",
    candidate_id: overrides.candidateId || "candidate-bass",
    midi_sha256: sha(overrides.midi || "b"),
    role,
    coverage_preflight:
      role === "keys" ? keysCoverage() : bassCoverage(),
    expected_revision: status === "unreviewed" ? 0 : 1,
    window: {start_seconds: 2, end_seconds: 9},
    source_reference: {
      audio_url: "/media/source?token=private",
      applied_gain_db: -2,
    },
    candidates: {
      candidate_a: {
        audio_url: "/media/a?token=private",
        applied_gain_db: -1,
      },
      candidate_b: {
        audio_url: "/media/b?token=private",
        applied_gain_db: 0,
      },
    },
    allowed_problem_tags: ["missing_or_silent_notes", "uneven_tone"],
    limits: {
      maximum_problem_tags_per_candidate: 4,
      maximum_notes_characters_per_candidate: 120,
    },
    effects: {
      midi_changed: false,
      instrument_default_changed: false,
      pack_changed: false,
      mix_changed: false,
      feedback_recorded: status !== "unreviewed",
    },
  };
  if (status === "reviewed" || status === "resolved") {
    value.review = {
      review_id: sha("d"),
      review_sha256: sha("e"),
      revision: 1,
      review_url: "/api/instrument-review-export?kind=review",
      response: {
        heard: {
          source_reference: true,
          candidate_a: true,
          candidate_b: true,
        },
        choice: "candidate_b",
        problem_tags: {
          candidate_a: ["uneven_tone"],
          candidate_b: [],
        },
        notes: {
          candidate_a: "less consistent",
          candidate_b: "clearer",
        },
      },
    };
  }
  if (status === "resolved") {
    value.result = {
      assignment: {
        candidate_a: "GM 39 Synth Bass 1",
        candidate_b: "GM 40 Synth Bass 2",
      },
      resolved_choice: "GM 40 Synth Bass 2",
      result_url: "/api/instrument-review-export?kind=result",
    };
  }
  return value;
}
"""


class WorkbenchInstrumentReviewJavaScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module_path = Path("src/sunofriend/workbench_instrument_review.js")
        cls.source = cls.module_path.read_text(encoding="utf-8")

    def run_node(self, body: str) -> dict[str, object]:
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is not installed")
        script = """
const review = require("./src/sunofriend/workbench_instrument_review.js");
FIXTURES
Promise.resolve((async()=>{BODY})()).then(
  value => console.log(JSON.stringify(value)),
  error => { console.error(error.stack || error); process.exitCode = 1; }
);
""".replace("FIXTURES", FIXTURES).replace("BODY", body)
        completed = subprocess.run(
            [node, "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_plan_and_blind_comparison_reject_scope_or_identity_leaks(
        self,
    ) -> None:
        result = self.run_node(
            """
const accepted = review.normalizePlan({plan: plan()});
const prepared = review.normalizeComparison(comparison());
const keysAccepted = review.normalizePlan(plan({role: "keys"}));
let coverageMarkerRejected = false;
try {
  review.normalizePlan(plan({role: "keys", coverage: "not_required"}));
} catch { coverageMarkerRejected = true; }
let clientProgramRejected = false;
try {
  const leaked = plan({role: "keys"});
  leaked.eligible_lanes[0].program = 5;
  review.normalizePlan(leaked);
} catch { clientProgramRejected = true; }
let assignmentRejected = false;
try {
  const leaked = plan();
  leaked.eligible_lanes[0].pair.assignment = {
    candidate_a: "control",
    candidate_b: "challenger",
  };
  review.normalizePlan(leaked);
} catch { assignmentRejected = true; }
let identityRejected = false;
try {
  const leaked = comparison();
  leaked.candidates.candidate_a.program = 38;
  review.normalizeComparison(leaked);
} catch { identityRejected = true; }
return {
  planSchema: accepted.schema,
  laneCount: accepted.eligible_lanes.length,
  keysRole: keysAccepted.eligible_lanes[0].role,
  comparisonSha: prepared.comparison_sha256,
  coverageMarkerRejected,
  clientProgramRejected,
  assignmentRejected,
  identityRejected,
};
"""
        )

        self.assertEqual(
            result["planSchema"],
            "sunofriend.workbench-instrument-review-plan.v1",
        )
        self.assertEqual(result["laneCount"], 1)
        self.assertEqual(result["keysRole"], "keys")
        self.assertEqual(result["comparisonSha"], "c" * 64)
        self.assertTrue(result["coverageMarkerRejected"])
        self.assertTrue(result["clientProgramRejected"])
        self.assertTrue(result["assignmentRejected"])
        self.assertTrue(result["identityRejected"])

    def test_comparison_requires_exact_status_blind_and_effect_contract(
        self,
    ) -> None:
        result = self.run_node(
            """
function rejected(status, mutate) {
  const value = comparison({status});
  mutate(value);
  try {
    review.normalizeComparison(value);
    return false;
  } catch {
    return true;
  }
}
const accepted = ["unreviewed", "reviewed", "resolved"].map(status => {
  const value = review.normalizeComparison(comparison({status}));
  return {
    status: value.status,
    blind: value.blind,
    feedback: value.effects.feedback_recorded,
  };
});
const productKeys = [
  "midi_changed",
  "instrument_default_changed",
  "pack_changed",
  "mix_changed",
];
return {
  accepted,
  missingBlind: rejected("unreviewed", value => { delete value.blind; }),
  blindDrift: ["unreviewed", "reviewed", "resolved"].every(status =>
    rejected(status, value => { value.blind = !value.blind; })
  ),
  missingEffects: rejected("unreviewed", value => { delete value.effects; }),
  missingEffectKey: rejected("unreviewed", value => {
    delete value.effects.pack_changed;
  }),
  extraEffectKey: rejected("unreviewed", value => {
    value.effects.selection_changed = false;
  }),
  productEffectDrift: productKeys.every(key =>
    rejected("reviewed", value => { value.effects[key] = true; })
  ),
  feedbackDrift: ["unreviewed", "reviewed", "resolved"].every(status =>
    rejected(status, value => {
      value.effects.feedback_recorded =
        !value.effects.feedback_recorded;
    })
  ),
};
"""
        )

        self.assertEqual(
            result["accepted"],
            [
                {
                    "status": "unreviewed",
                    "blind": True,
                    "feedback": False,
                },
                {
                    "status": "reviewed",
                    "blind": True,
                    "feedback": True,
                },
                {
                    "status": "resolved",
                    "blind": False,
                    "feedback": True,
                },
            ],
        )
        for key in (
            "missingBlind",
            "blindDrift",
            "missingEffects",
            "missingEffectKey",
            "extraEffectKey",
            "productEffectDrift",
            "feedbackDrift",
        ):
            self.assertTrue(result[key], key)

    def test_keys_coverage_is_exact_anonymous_and_fail_closed(self) -> None:
        result = self.run_node(
            """
function rejected(mutate) {
  const value = comparison({role: "keys"});
  mutate(value);
  try {
    review.normalizeComparison(value);
    return false;
  } catch {
    return true;
  }
}
const holder = {
  innerHTML: "",
  querySelector() { return null; },
  querySelectorAll() { return []; },
};
const controller = review.createInstrumentReview({api: async() => ({})});
controller
  .setPlan(plan({role: "keys"}))
  .setComparison(comparison({role: "keys"}))
  .renderInto(holder);
return {
  snapshot: controller.snapshot(),
  html: holder.innerHTML,
  missingCoverage: rejected(value => {
    delete value.coverage_preflight;
  }),
  functionalDrift: rejected(value => {
    value.coverage_preflight.functional_status = "required";
  }),
  qualityDrift: rejected(value => {
    value.coverage_preflight.quality_status = "passed";
  }),
  thresholdDrift: rejected(value => {
    value.coverage_preflight.thresholds.minimum_active_above_pre_guard_db = 2.9;
  }),
  countDrift: rejected(value => {
    value.coverage_preflight.candidates.candidate_a.passed_zone_count = 3;
  }),
  oneCandidate: rejected(value => {
    delete value.coverage_preflight.candidates.candidate_b;
  }),
  identityLeak: rejected(value => {
    value.coverage_preflight.candidates.candidate_a.program = 4;
  }),
  bassMeasurementRejected: (() => {
    const value = comparison();
    value.coverage_preflight = keysCoverage();
    try {
      review.normalizeComparison(value);
      return false;
    } catch {
      return true;
    }
  })(),
};
"""
        )

        self.assertEqual(result["snapshot"]["coverage_preflight_status"], "passed")
        self.assertEqual(
            result["snapshot"]["coverage_quality_status"],
            "review_required",
        )
        self.assertIn("minimum velocity", result["html"])
        self.assertIn("actually observed", result["html"])
        self.assertIn("Candidate A", result["html"])
        self.assertNotIn("Electric Piano", result["html"])
        for key in (
            "missingCoverage",
            "functionalDrift",
            "qualityDrift",
            "thresholdDrift",
            "countDrift",
            "oneCandidate",
            "identityLeak",
            "bassMeasurementRejected",
        ):
            self.assertTrue(result[key], key)

    def test_prepare_posts_only_exact_lane_and_window_anchors(self) -> None:
        result = self.run_node(
            """
const calls = [];
const api = async(path, options) => {
  calls.push({path, method: options.method, body: JSON.parse(options.body)});
  return {comparison: comparison({role: "keys"})};
};
const button = {};
const fields = {
  "#prepare-instrument-review": button,
  "#instrument-review-start": {value: "2"},
  "#instrument-review-end": {value: "9"},
};
const holder = {
  innerHTML: "",
  querySelector(selector) { return fields[selector] || null; },
  querySelectorAll() { return []; },
};
const controller = review.createInstrumentReview({api});
controller.setPlan({plan: plan({role: "keys"})}).renderInto(holder);
await button.onclick();
return {calls, snapshot: controller.snapshot()};
"""
        )

        self.assertEqual(
            result["calls"],
            [
                {
                    "path": "/api/instrument-review/prepare",
                    "method": "POST",
                    "body": {
                        "selection_manifest_sha256": "a" * 64,
                        "stem_id": "stem-bass",
                        "candidate_id": "candidate-bass",
                        "midi_sha256": "b" * 64,
                        "start_seconds": 2,
                        "end_seconds": 9,
                    },
                }
            ],
        )
        self.assertEqual(result["snapshot"]["comparison_status"], "unreviewed")
        self.assertFalse(result["snapshot"]["feedback_persisted"])

    def test_one_clock_transport_and_three_heard_completion_contract(
        self,
    ) -> None:
        result = self.run_node(
            """
const fetches = [];
globalThis.fetch = async(url, options) => {
  fetches.push({url, cache: options.cache, credentials: options.credentials});
  return {
    ok: true,
    status: 200,
    async arrayBuffer() { return new Uint8Array([1, 2, 3]).buffer; },
  };
};
class FakeAudioContext {
  constructor() {
    this.sampleRate = 48000;
    this.currentTime = 0;
    this.state = "running";
  }
  async decodeAudioData() {
    return {duration: 7, sampleRate: 48000, numberOfChannels: 2, length: 336000};
  }
}
class FakeTransport {
  constructor(options) {
    this.options = options;
    this.activeKey = null;
    this.playing = false;
    globalThis.transportOptions = options;
  }
  switchTo(key) { this.activeKey = key; this.playing = true; }
  pause() { this.playing = false; return 1.25; }
  stop() { this.playing = false; this.activeKey = null; return 0; }
  snapshot() {
    return {
      activeKey: this.activeKey,
      playing: this.playing,
      playheadSeconds: this.playing ? 1.25 : 0,
    };
  }
}
globalThis.AudioContext = FakeAudioContext;
globalThis.SunofriendWorkbenchTransport = {
  DecodedLoopTransport: FakeTransport,
};

const calls = [];
const api = async(path, options) => {
  calls.push({path, method: options.method, body: JSON.parse(options.body)});
  return {comparison: comparison({status: "reviewed"})};
};
const load = {};
const complete = {disabled: true};
const heardSource = {
  checked: false,
  dataset: {instrumentReviewHeard: "source_reference"},
};
const heardA = {
  checked: false,
  dataset: {instrumentReviewHeard: "candidate_a"},
};
const heardB = {
  checked: false,
  dataset: {instrumentReviewHeard: "candidate_b"},
};
const choice = {checked: false, value: "candidate_b"};
const tag = {
  checked: false,
  value: "uneven_tone",
  dataset: {instrumentReviewCandidate: "candidate_a"},
};
const noteA = {
  value: "less consistent",
  dataset: {instrumentReviewNotes: "candidate_a"},
};
const noteB = {
  value: "clearer",
  dataset: {instrumentReviewNotes: "candidate_b"},
};
const playButtons = ["source_reference", "candidate_a", "candidate_b"].map(
  key => ({
    disabled: true,
    dataset: {instrumentReviewPlay: key},
    setAttribute() {},
    classList: {toggle() {}},
  }),
);
const fields = {
  "#load-instrument-review-audio": load,
  "#complete-instrument-review": complete,
  "#pause-instrument-review": {disabled: true},
  "#stop-instrument-review": {disabled: true},
  "#instrument-review-position": {textContent: ""},
  "#instrument-review-draft-status": {textContent: ""},
  "#instrument-review-audio-status": {textContent: "", className: ""},
  "#instrument-review-status": {textContent: "", className: ""},
};
const holder = {
  innerHTML: "",
  querySelector(selector) { return fields[selector] || null; },
  querySelectorAll(selector) {
    if (selector === "[data-instrument-review-play]") return playButtons;
    if (selector === "[data-instrument-review-heard]") {
      return [heardSource, heardA, heardB];
    }
    if (selector === 'input[name="instrument-review-choice"]') return [choice];
    if (selector === "[data-instrument-review-tag]") return [tag];
    if (selector === "[data-instrument-review-notes]") return [noteA, noteB];
    return [];
  },
};
let pausedOtherAudio = 0;
const controller = review.createInstrumentReview({
  api,
  pauseOtherAudio() { pausedOtherAudio += 1; },
});
controller.setPlan(plan()).setComparison(comparison()).renderInto(holder);
await load.onclick();
await playButtons[2].onclick();
const sharedTransport = {
  loopStart: globalThis.transportOptions.loopStartSeconds,
  loopEnd: globalThis.transportOptions.loopEndSeconds,
  gains: [...globalThis.transportOptions.gainDbByKey.entries()],
  keys: [...globalThis.transportOptions.decodedBuffers.keys()],
};
heardA.checked = true; heardA.onchange();
heardB.checked = true; heardB.onchange();
choice.checked = true; choice.onchange();
const disabledWithoutSource = complete.disabled;
heardSource.checked = true; heardSource.onchange();
tag.checked = true; tag.onchange();
noteA.oninput(); noteB.oninput();
const enabledWithAllEvidence = !complete.disabled;
await complete.onclick();
return {
  fetches,
  calls,
  pausedOtherAudio,
  disabledWithoutSource,
  enabledWithAllEvidence,
  sharedTransport,
  snapshot: controller.snapshot(),
};
"""
        )

        self.assertEqual(
            [entry["url"] for entry in result["fetches"]],
            [
                "/media/source?token=private",
                "/media/a?token=private",
                "/media/b?token=private",
            ],
        )
        self.assertEqual(result["pausedOtherAudio"], 1)
        self.assertTrue(result["disabledWithoutSource"])
        self.assertTrue(result["enabledWithAllEvidence"])
        self.assertEqual(result["sharedTransport"]["loopStart"], 0)
        self.assertEqual(result["sharedTransport"]["loopEnd"], 7)
        self.assertEqual(
            result["sharedTransport"]["keys"],
            ["source_reference", "candidate_a", "candidate_b"],
        )
        self.assertEqual(
            result["sharedTransport"]["gains"],
            [
                ["source_reference", 0],
                ["candidate_a", 0],
                ["candidate_b", 0],
            ],
        )
        self.assertEqual(
            result["calls"],
            [
                {
                    "path": "/api/instrument-review",
                    "method": "POST",
                    "body": {
                        "comparison_sha256": "c" * 64,
                        "expected_revision": 0,
                        "heard": {
                            "source_reference": True,
                            "candidate_a": True,
                            "candidate_b": True,
                        },
                        "choice": "candidate_b",
                        "problem_tags": {
                            "candidate_a": ["uneven_tone"],
                            "candidate_b": [],
                        },
                        "notes": {
                            "candidate_a": "less consistent",
                            "candidate_b": "clearer",
                        },
                    },
                }
            ],
        )
        self.assertEqual(result["snapshot"]["comparison_status"], "reviewed")
        self.assertTrue(result["snapshot"]["feedback_persisted"])

    def test_resolution_is_separate_and_renders_both_export_links(self) -> None:
        result = self.run_node(
            """
const calls = [];
const api = async(path, options) => {
  calls.push({path, method: options.method, body: JSON.parse(options.body)});
  return {comparison: comparison({status: "resolved"})};
};
const resolve = {};
const holder = {
  innerHTML: "",
  querySelector(selector) {
    return selector === "#resolve-instrument-review" ? resolve : null;
  },
  querySelectorAll() { return []; },
};
const controller = review.createInstrumentReview({api});
controller
  .setPlan(plan())
  .setComparison(comparison({status: "reviewed"}))
  .renderInto(holder);
await resolve.onclick();
return {
  calls,
  html: holder.innerHTML,
  snapshot: controller.snapshot(),
};
"""
        )

        self.assertEqual(
            result["calls"],
            [
                {
                    "path": "/api/instrument-review/resolve",
                    "method": "POST",
                    "body": {
                        "comparison_sha256": "c" * 64,
                        "review_id": "d" * 64,
                        "review_sha256": "e" * 64,
                    },
                }
            ],
        )
        self.assertIn("/api/instrument-review-export?kind=review", result["html"])
        self.assertIn("/api/instrument-review-export?kind=result", result["html"])
        self.assertIn("GM 40 Synth Bass 2", result["html"])
        self.assertEqual(result["snapshot"]["comparison_status"], "resolved")

    def test_delayed_completion_is_single_submit_and_stale_prepare_is_ignored(
        self,
    ) -> None:
        result = self.run_node(
            """
let completionRelease;
const completionGate = new Promise(resolve => { completionRelease = resolve; });
let completionCalls = 0;
const reviewed = comparison({status: "reviewed"});
const completionApi = async() => {
  completionCalls += 1;
  await completionGate;
  return {comparison: reviewed};
};
const heard = ["source_reference", "candidate_a", "candidate_b"].map(key => ({
  checked: false,
  dataset: {instrumentReviewHeard: key},
}));
const choice = {checked: false, value: "candidate_a"};
const complete = {disabled: true};
const holder = {
  innerHTML: "",
  querySelector(selector) {
    return {
      "#complete-instrument-review": complete,
      "#instrument-review-draft-status": {textContent: ""},
      "#instrument-review-status": {textContent: "", className: ""},
      "#instrument-review-position": {textContent: ""},
    }[selector] || null;
  },
  querySelectorAll(selector) {
    if (selector === "[data-instrument-review-heard]") return heard;
    if (selector === 'input[name="instrument-review-choice"]') return [choice];
    return [];
  },
};
const completionController = review.createInstrumentReview({api: completionApi});
completionController
  .setPlan(plan())
  .setComparison(comparison())
  .renderInto(holder);
for (const input of heard) { input.checked = true; input.onchange(); }
choice.checked = true; choice.onchange();
const submit = complete.onclick;
const first = submit();
const second = submit();
const disabledPending = complete.disabled;
completionRelease();
await Promise.all([first, second]);

let prepareRelease;
const prepareGate = new Promise(resolve => { prepareRelease = resolve; });
const staleApi = async() => {
  await prepareGate;
  return {comparison: comparison()};
};
const prepareButton = {};
const prepareHolder = {
  innerHTML: "",
  querySelector(selector) {
    return {
      "#prepare-instrument-review": prepareButton,
      "#instrument-review-start": {value: "2"},
      "#instrument-review-end": {value: "9"},
    }[selector] || null;
  },
  querySelectorAll() { return []; },
};
const staleController = review.createInstrumentReview({api: staleApi});
staleController.setPlan(plan()).renderInto(prepareHolder);
const pendingPrepare = prepareButton.onclick();
staleController.setPlan(plan({selection: "f", midi: "9"}));
prepareRelease();
await pendingPrepare;
return {
  completionCalls,
  disabledPending,
  completionStatus: completionController.snapshot().comparison_status,
  staleStatus: staleController.snapshot().comparison_status,
  staleSelection:
    staleController.snapshot().active_lane?.stem_id || null,
};
"""
        )

        self.assertEqual(result["completionCalls"], 1)
        self.assertTrue(result["disabledPending"])
        self.assertEqual(result["completionStatus"], "reviewed")
        self.assertIsNone(result["staleStatus"])
        self.assertEqual(result["staleSelection"], "stem-bass")

    def test_module_has_no_drifting_player_or_product_mutation_surface(
        self,
    ) -> None:
        self.assertIn("DecodedLoopTransport", self.source)
        self.assertIn(
            "Independent drifting players are intentionally not provided",
            self.source,
        )
        self.assertIn("source_reference", self.source)
        self.assertIn("instrument default", self.source)
        self.assertIn("selected MIDI", self.source)
        self.assertIn("GarageBand", self.source)
        self.assertNotIn("<audio", self.source.lower())
        self.assertNotIn("autoplay", self.source.lower())
        self.assertNotIn("localStorage", self.source)
        self.assertNotIn("/api/events", self.source)
        self.assertNotIn("/api/garageband-pack", self.source)
        self.assertNotIn("/api/balanced-arrangement", self.source)


if __name__ == "__main__":
    unittest.main()
