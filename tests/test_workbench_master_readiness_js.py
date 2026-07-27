from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


FIXTURES = r"""
const sha = letter => letter.repeat(64);
function readinessEffects(feedbackRecorded = false) {
  return {
    feedback_recorded: feedbackRecorded,
    readiness_review_record_created: feedbackRecorded,
    quality_review_mutated: false,
    quality_resolution_mutated: false,
    source_audio_mutated: false,
    balanced_control_mutated: false,
    listening_master_mutated: false,
    midi_mutated: false,
    selection_changed: false,
    automatic_selection: false,
    automatic_ranking: false,
    default_selection_changed: false,
    pack_changed: false,
    product_completion_changed: false,
  };
}
function makeQuality(overrides = {}) {
  const selection = overrides.selection || "a";
  const balanced = overrides.balanced || "b";
  const master = overrides.master || "c";
  const comparison = overrides.comparison || "d";
  const reviewId = overrides.reviewId || "e";
  const reviewSha = overrides.reviewSha || "f";
  const resultSha = overrides.resultSha || "1";
  const outcome = overrides.outcome || "listening_master";
  return {
    status: "resolved",
    comparison_sha256: sha(comparison),
    selection_manifest_sha256: sha(selection),
    balanced_arrangement_manifest_sha256: sha(balanced),
    listening_master_manifest_sha256: sha(master),
    review: {
      review_id: sha(reviewId),
      review_sha256: sha(reviewSha),
      revision: 1,
      response: {
        heard: {candidate_a: true, candidate_b: true},
        choice: "candidate_b",
        problem_tags: {candidate_a: [], candidate_b: []},
        notes: "",
      },
    },
    result: {
      result_sha256: sha(resultSha),
      assignment: {
        candidate_a: "balanced_control",
        candidate_b: "listening_master",
      },
      resolved_choice: outcome,
      result_url: "/exports/quality.json",
    },
  };
}
function artifactsFor(quality) {
  return {
    selection_manifest_sha256: quality.selection_manifest_sha256,
    balanced_arrangement_manifest_sha256:
      quality.balanced_arrangement_manifest_sha256,
    listening_master_manifest_sha256:
      quality.listening_master_manifest_sha256,
  };
}
function makeReadiness(quality, overrides = {}) {
  return {
    schema:
      "sunofriend.workbench-listening-master-native-readiness-comparison.v1",
    status: "unreviewed",
    identity_labelled: true,
    native_level: true,
    comparison_sha256: sha(overrides.comparison || "2"),
    selection_manifest_sha256: quality.selection_manifest_sha256,
    balanced_arrangement_manifest_sha256:
      quality.balanced_arrangement_manifest_sha256,
    listening_master_manifest_sha256:
      quality.listening_master_manifest_sha256,
    quality_review: {
      quality_review_id: quality.review.review_id,
      quality_review_sha256: quality.review.review_sha256,
      quality_result_sha256: quality.result.result_sha256,
      quality_comparison_sha256: quality.comparison_sha256,
      quality_revision: quality.review.revision,
      resolved_choice: quality.result.resolved_choice,
      explicitly_resolved: true,
      latest_for_reviewer: true,
    },
    window: {
      start_frame: 96000,
      end_frame: 432000,
      frame_count: 336000,
      sample_rate: 48000,
      start_seconds: 2,
      end_seconds: 9,
      duration_seconds: 7,
      recorded_zero: true,
      alignment_inferred: false,
    },
    candidates: {
      balanced_control: {
        label: "Balanced control",
        audio_url: "/media/native-control",
        audio: {
          name: "balanced-control.wav",
          bytes: 100,
          sha256: sha("3"),
        },
        format: "WAV",
        subtype: "PCM_24",
        sample_rate: 48000,
        channels: 2,
        frames: 336000,
        applied_gain_db: 0,
        processing_applied: false,
      },
      listening_master: {
        label: "Listening Master",
        audio_url: "/media/native-master",
        audio: {
          name: "listening-master.wav",
          bytes: 100,
          sha256: sha("4"),
        },
        format: "WAV",
        subtype: "PCM_24",
        sample_rate: 48000,
        channels: 2,
        frames: 336000,
        applied_gain_db: 0,
        processing_applied: false,
      },
    },
    artifact_hashes: {
      balanced_control_preview_sha256: sha("7"),
      listening_master_wav_sha256: sha("8"),
      listening_master_receipt_sha256: sha("9"),
    },
    problem_tags: ["harsh", "pumping"],
    choices: [
      "balanced_control",
      "cannot_tell",
      "equivalent",
      "listening_master",
      "neither",
    ],
    limits: {
      maximum_problem_tags_per_identity: 8,
      maximum_notes_characters: 2000,
    },
    policy: {
      name: "identity-labelled-native-level-exact-window-pcm24-v1",
      audio: "exact-frame-native-level-zero-gain-pcm24-v1",
      identity_hidden: false,
      quality_review_resolved: true,
      quality_review_latest: true,
      exact_quality_frame_window_reused: true,
      native_level_unchanged: true,
      output_format: "WAV",
      output_subtype: "PCM_24",
      applied_gain_db: 0,
      gain_matching_used: false,
      resampling_used: false,
      limiter_used: false,
      compression_used: false,
      equalisation_used: false,
      time_shift_seconds: 0,
      time_stretch_ratio: 1,
    },
    review: null,
    effects: readinessEffects(false),
  };
}
function reviewedReadiness(readiness, overrides = {}) {
  const choice = overrides.choice || "listening_master";
  const controlTags = overrides.controlTags || [];
  const masterTags = overrides.masterTags || [];
  const notes = overrides.notes === undefined ? "native note" : overrides.notes;
  return {
    ...readiness,
    status: "reviewed",
    effects: readinessEffects(true),
    review: {
      readiness_review_id: sha("5"),
      readiness_review_sha256: sha("6"),
      response: {
        heard: {balanced_control: true, listening_master: true},
        choice,
        problem_tags: {
          balanced_control: controlTags,
          listening_master: masterTags,
        },
        notes,
      },
      choice,
      review_url: "/exports/readiness.json",
    },
  };
}
"""


class WorkbenchMasterReadinessJavaScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module_path = Path(
            "src/sunofriend/workbench_master_review.js"
        )
        cls.source = cls.module_path.read_text(encoding="utf-8")

    def run_node(self, body: str) -> dict[str, object]:
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is not installed")
        script = (
            """
const review = require("./src/sunofriend/workbench_master_review.js");
FIXTURES
Promise.resolve((async()=>{BODY})()).then(
  value => console.log(JSON.stringify(value)),
  error => { console.error(error.stack || error); process.exitCode = 1; }
);
"""
            .replace("FIXTURES", FIXTURES)
            .replace("BODY", body)
        )
        completed = subprocess.run(
            [node, "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_normalizer_allows_bound_readiness_only_after_resolution(
        self,
    ) -> None:
        result = self.run_node(
            r"""
const quality = makeQuality();
const readiness = makeReadiness(quality);
const accepted = review.normalizeComparison({...quality, readiness});
const blind = {
  status: "unreviewed",
  comparison_sha256: sha("7"),
  selection_manifest_sha256: quality.selection_manifest_sha256,
  balanced_arrangement_manifest_sha256:
    quality.balanced_arrangement_manifest_sha256,
  listening_master_manifest_sha256:
    quality.listening_master_manifest_sha256,
  candidates: {
    candidate_a: {audio_url: "/media/a"},
    candidate_b: {audio_url: "/media/b"},
  },
};
let beforeResolutionRejected = false;
try {
  review.normalizeComparison({...blind, readiness});
} catch { beforeResolutionRejected = true; }
let staleQualityRejected = false;
try {
  review.normalizeComparison({
    ...quality,
    readiness: {
      ...readiness,
      quality_review: {
        ...readiness.quality_review,
        quality_result_sha256: sha("8"),
      },
    },
  });
} catch { staleQualityRejected = true; }
let unknownTagRejected = false;
try {
  review.normalizeComparison({
    ...quality,
    readiness: reviewedReadiness(readiness, {
      controlTags: ["not_allowlisted"],
    }),
  });
} catch { unknownTagRejected = true; }
let genericReviewIdRejected = false;
try {
  const completed = reviewedReadiness(readiness);
  review.normalizeComparison({
    ...quality,
    readiness: {
      ...completed,
      review: {
        ...completed.review,
        review_id: completed.review.readiness_review_id,
      },
    },
  });
} catch { genericReviewIdRejected = true; }
return {
  acceptedStatus: accepted.readiness.status,
  beforeResolutionRejected,
  staleQualityRejected,
  unknownTagRejected,
  genericReviewIdRejected,
};
"""
        )

        self.assertEqual(result["acceptedStatus"], "unreviewed")
        self.assertTrue(result["beforeResolutionRejected"])
        self.assertTrue(result["staleQualityRejected"])
        self.assertTrue(result["unknownTagRejected"])
        self.assertTrue(result["genericReviewIdRejected"])

    def test_normalizer_rejects_malformed_native_audio_and_effect_evidence(
        self,
    ) -> None:
        result = self.run_node(
            r"""
const quality = makeQuality();
const cases = [
  ["artifact-hashes", readiness => {
    delete readiness.artifact_hashes.listening_master_receipt_sha256;
    readiness.artifact_hashes.listening_master = sha("9");
  }],
  ["frame-window", readiness => {
    readiness.window.end_frame += 1;
  }],
  ["pcm-subtype", readiness => {
    readiness.candidates.balanced_control.subtype = "PCM_16";
  }],
  ["audio-hash", readiness => {
    readiness.candidates.listening_master.audio.sha256 = "not-a-sha";
  }],
  ["processing-policy", readiness => {
    readiness.policy.compression_used = true;
  }],
  ["forbidden-effect", readiness => {
    readiness.effects.product_completion_changed = true;
  }],
  ["candidate-schema", readiness => {
    readiness.candidates.balanced_control.browser_gain = 1;
  }],
];
const rejected = [];
for (const [name, mutate] of cases) {
  const readiness = JSON.parse(JSON.stringify(makeReadiness(quality)));
  mutate(readiness);
  try {
    review.normalizeComparison({...quality, readiness});
  } catch {
    rejected.push(name);
  }
}
const restored = reviewedReadiness(makeReadiness(quality));
restored.effects = readinessEffects(false);
const restoredStatus = review.normalizeComparison({
  ...quality,
  readiness: restored,
}).readiness.status;
return {rejected, restoredStatus};
"""
        )

        self.assertEqual(
            result["rejected"],
            [
                "artifact-hashes",
                "frame-window",
                "pcm-subtype",
                "audio-hash",
                "processing-policy",
                "forbidden-effect",
                "candidate-schema",
            ],
        )
        self.assertEqual(result["restoredStatus"], "reviewed")

    def test_prepare_uses_only_resolved_quality_receipt_hashes(self) -> None:
        result = self.run_node(
            r"""
const quality = makeQuality();
const readiness = makeReadiness(quality);
const calls = [];
const api = async(path, options) => {
  calls.push({path, method: options.method, body: JSON.parse(options.body)});
  return {readiness};
};
const prepare = {};
const holder = {
  innerHTML: "",
  querySelector(selector) {
    return selector === "#prepare-master-readiness" ? prepare : null;
  },
  querySelectorAll() { return []; },
};
let changed = null;
const controller = review.createMasterReview({
  api,
  onComparisonChange(value) { changed = value; },
});
controller
  .setArtifacts(artifactsFor(quality))
  .setComparison(quality)
  .renderInto(holder);
await prepare.onclick();
return {
  calls,
  status: controller.snapshot().readiness_status,
  changed: changed?.readiness?.comparison_sha256,
  html: holder.innerHTML,
};
"""
        )

        self.assertEqual(
            result["calls"],
            [
                {
                    "path": "/api/listening-master-readiness/prepare",
                    "method": "POST",
                    "body": {
                        "quality_review_id": "e" * 64,
                        "quality_review_sha256": "f" * 64,
                        "quality_result_sha256": "1" * 64,
                    },
                }
            ],
        )
        self.assertEqual(result["status"], "unreviewed")
        self.assertEqual(result["changed"], "2" * 64)
        self.assertIn("Same read-only window", result["html"])
        self.assertNotIn('type="number"', result["html"])

    def test_unity_transport_heard_gate_and_exact_completion_request(
        self,
    ) -> None:
        result = self.run_node(
            r"""
const quality = makeQuality();
const readiness = makeReadiness(quality);
const completed = reviewedReadiness(readiness, {
  choice: "listening_master",
  controlTags: ["harsh"],
  notes: "native note",
});
const calls = [];
const api = async(path, options) => {
  calls.push({path, method: options.method, body: JSON.parse(options.body)});
  return {readiness: completed};
};
const makeAudio = () => ({
  loop: false,
  volume: 0,
  currentTime: 0,
  duration: 7,
  playCalls: 0,
  pauseCalls: 0,
  pause() { this.pauseCalls += 1; },
  play() { this.playCalls += 1; return Promise.resolve(); },
});
const controlAudio = makeAudio();
const masterAudio = makeAudio();
const playControl = {
  dataset: {masterReadinessPlay: "balanced_control"},
};
const playMaster = {
  dataset: {masterReadinessPlay: "listening_master"},
};
const heardControl = {
  checked: false,
  dataset: {masterReadinessHeard: "balanced_control"},
};
const heardMaster = {
  checked: false,
  dataset: {masterReadinessHeard: "listening_master"},
};
const choice = {checked: false, value: "listening_master"};
const tag = {
  checked: false,
  value: "harsh",
  dataset: {masterReadinessCandidate: "balanced_control"},
};
const complete = {disabled: true};
const notes = {value: "native note"};
const position = {textContent: ""};
const draftStatus = {textContent: ""};
const holder = {
  innerHTML: "",
  querySelector(selector) {
    return {
      "#master-readiness-audio-balanced-control": controlAudio,
      "#master-readiness-audio-listening-master": masterAudio,
      "#complete-master-readiness": complete,
      "#master-readiness-notes": notes,
      "#master-readiness-position": position,
      "#master-readiness-draft-status": draftStatus,
    }[selector] || null;
  },
  querySelectorAll(selector) {
    if (selector === "[data-master-review-audio]") {
      return [controlAudio, masterAudio];
    }
    if (selector === "[data-master-readiness-audio]") {
      return [controlAudio, masterAudio];
    }
    if (selector === "[data-master-readiness-play]") {
      return [playControl, playMaster];
    }
    if (selector === "[data-master-readiness-heard]") {
      return [heardControl, heardMaster];
    }
    if (selector === 'input[name="master-readiness-choice"]') {
      return [choice];
    }
    if (selector === "[data-master-readiness-tag]") return [tag];
    return [];
  },
};
let pauseOtherCalls = 0;
const controller = review.createMasterReview({
  api,
  pauseOtherAudio() { pauseOtherCalls += 1; },
});
controller
  .setArtifacts(artifactsFor(quality))
  .setComparison({...quality, readiness})
  .renderInto(holder);
const playCallsBeforeClick = [
  controlAudio.playCalls,
  masterAudio.playCalls,
];
const initiallyDisabled = complete.disabled;
heardControl.checked = true;
heardControl.onchange();
const disabledAfterOneHeard = complete.disabled;
heardMaster.checked = true;
heardMaster.onchange();
choice.checked = true;
choice.onchange();
tag.checked = true;
tag.onchange();
notes.oninput();
const enabledAfterEvidence = !complete.disabled;
await playControl.onclick();
controlAudio.currentTime = 3.25;
controlAudio.ontimeupdate();
await playMaster.onclick();
const sharedMasterPosition = masterAudio.currentTime;
await complete.onclick();
return {
  playCallsBeforeClick,
  initiallyDisabled,
  disabledAfterOneHeard,
  enabledAfterEvidence,
  volumes: [controlAudio.volume, masterAudio.volume],
  loops: [controlAudio.loop, masterAudio.loop],
  sharedMasterPosition,
  pauseOtherCalls,
  calls,
  status: controller.snapshot().readiness_status,
};
"""
        )

        self.assertEqual(result["playCallsBeforeClick"], [0, 0])
        self.assertTrue(result["initiallyDisabled"])
        self.assertTrue(result["disabledAfterOneHeard"])
        self.assertTrue(result["enabledAfterEvidence"])
        self.assertEqual(result["volumes"], [1, 1])
        self.assertEqual(result["loops"], [True, True])
        self.assertEqual(result["sharedMasterPosition"], 3.25)
        self.assertEqual(result["pauseOtherCalls"], 2)
        self.assertEqual(result["status"], "reviewed")
        self.assertEqual(
            result["calls"],
            [
                {
                    "path": "/api/listening-master-readiness",
                    "method": "POST",
                    "body": {
                        "comparison_sha256": "2" * 64,
                        "quality_review_id": "e" * 64,
                        "quality_review_sha256": "f" * 64,
                        "quality_result_sha256": "1" * 64,
                        "heard": {
                            "balanced_control": True,
                            "listening_master": True,
                        },
                        "choice": "listening_master",
                        "problem_tags": {
                            "balanced_control": ["harsh"],
                            "listening_master": [],
                        },
                        "notes": "native note",
                    },
                }
            ],
        )

    def test_delayed_readiness_completion_cannot_submit_twice(self) -> None:
        result = self.run_node(
            r"""
const quality = makeQuality();
const readiness = makeReadiness(quality);
const completed = reviewedReadiness(readiness);
let release;
const gate = new Promise(resolve => { release = resolve; });
let calls = 0;
const api = async() => {
  calls += 1;
  await gate;
  return {readiness: completed};
};
const heardControl = {
  checked: false,
  dataset: {masterReadinessHeard: "balanced_control"},
};
const heardMaster = {
  checked: false,
  dataset: {masterReadinessHeard: "listening_master"},
};
const choice = {checked: false, value: "listening_master"};
const complete = {disabled: true};
const holder = {
  innerHTML: "",
  querySelector(selector) {
    return {
      "#complete-master-readiness": complete,
      "#master-readiness-notes": {value: ""},
      "#master-readiness-position": {textContent: ""},
      "#master-readiness-draft-status": {textContent: ""},
    }[selector] || null;
  },
  querySelectorAll(selector) {
    if (selector === "[data-master-readiness-heard]") {
      return [heardControl, heardMaster];
    }
    if (selector === 'input[name="master-readiness-choice"]') {
      return [choice];
    }
    return [];
  },
};
const controller = review.createMasterReview({api});
controller
  .setArtifacts(artifactsFor(quality))
  .setComparison({...quality, readiness})
  .renderInto(holder);
heardControl.checked = true;
heardControl.onchange();
heardMaster.checked = true;
heardMaster.onchange();
choice.checked = true;
choice.onchange();
const submit = complete.onclick;
const first = submit();
const second = submit();
const disabledWhilePending = complete.disabled;
release();
await Promise.all([first, second]);
return {
  calls,
  disabledWhilePending,
  status: controller.snapshot().readiness_status,
};
"""
        )

        self.assertEqual(result["calls"], 1)
        self.assertTrue(result["disabledWhilePending"])
        self.assertEqual(result["status"], "reviewed")

    def test_stale_prepare_response_cannot_replace_new_artifacts(self) -> None:
        result = self.run_node(
            r"""
const quality = makeQuality();
const readiness = makeReadiness(quality);
const newerQuality = makeQuality({
  selection: "7",
  balanced: "8",
  master: "9",
  comparison: "0",
  reviewId: "a",
  reviewSha: "b",
  resultSha: "c",
  outcome: "balanced_control",
});
let release;
const gate = new Promise(resolve => { release = resolve; });
let calls = 0;
const api = async() => {
  calls += 1;
  await gate;
  return {readiness};
};
const prepare = {};
const holder = {
  innerHTML: "",
  querySelector(selector) {
    return selector === "#prepare-master-readiness" ? prepare : null;
  },
  querySelectorAll() { return []; },
};
let changes = 0;
const controller = review.createMasterReview({
  api,
  onComparisonChange() { changes += 1; },
});
controller
  .setArtifacts(artifactsFor(quality))
  .setComparison(quality)
  .renderInto(holder);
const pending = prepare.onclick();
controller
  .setArtifacts(artifactsFor(newerQuality))
  .setComparison(newerQuality)
  .renderInto(holder);
release();
await pending;
return {
  calls,
  changes,
  comparison: controller.snapshot().comparison_sha256,
  readinessStatus: controller.snapshot().readiness_status,
};
"""
        )

        self.assertEqual(result["calls"], 1)
        self.assertEqual(result["changes"], 0)
        self.assertEqual(result["comparison"], "0" * 64)
        self.assertIsNone(result["readinessStatus"])

    def test_completed_view_separates_outcomes_and_states_zero_effects(
        self,
    ) -> None:
        result = self.run_node(
            r"""
const quality = makeQuality();
const readiness = reviewedReadiness(makeReadiness(quality), {
  choice: "balanced_control",
});
const holder = {
  innerHTML: "",
  querySelector() { return null; },
  querySelectorAll() { return []; },
};
const controller = review.createMasterReview({api: async() => ({})});
controller
  .setArtifacts(artifactsFor(quality))
  .setComparison({...quality, readiness})
  .renderInto(holder);
return {html: holder.innerHTML};
"""
        )

        html = result["html"]
        self.assertIn("Level-matched quality outcome", html)
        self.assertIn("Native-level readiness outcome", html)
        self.assertIn("/exports/quality.json", html)
        self.assertIn("/exports/readiness.json", html)
        self.assertIn("zero added gain", html)
        self.assertIn("no level matching", html)
        self.assertIn("do not promote or select", html)
        self.assertIn("product", html)
        self.assertIn("completion", html)
        self.assertNotIn("autoplay", self.source.lower())
        self.assertNotIn("localStorage", self.source)


if __name__ == "__main__":
    unittest.main()
