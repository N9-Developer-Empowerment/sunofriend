from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


class WorkbenchMasterReviewJavaScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module_path = Path("src/sunofriend/workbench_master_review.js")
        cls.source = cls.module_path.read_text(encoding="utf-8")
        cls.page = Path("src/sunofriend/workbench.html").read_text(encoding="utf-8")

    def run_node(self, body: str) -> dict[str, object]:
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is not installed")
        script = """
const review = require("./src/sunofriend/workbench_master_review.js");
Promise.resolve((async()=>{BODY})()).then(
  value => console.log(JSON.stringify(value)),
  error => { console.error(error.stack || error); process.exitCode = 1; }
);
""".replace("BODY", body)
        completed = subprocess.run(
            [node, "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_anonymous_prepared_projection_accepts_binding_hashes_only(self) -> None:
        result = self.run_node(
            """
const sha = letter => letter.repeat(64);
const value = {
  status: "unreviewed",
  comparison_sha256: sha("a"),
  selection_manifest_sha256: sha("b"),
  balanced_arrangement_manifest_sha256: sha("c"),
  listening_master_manifest_sha256: sha("d"),
  candidates: {
    candidate_a: {audio_url: "/media/a"},
    candidate_b: {audio_url: "/media/b"},
  },
};
const accepted = review.normalizeComparison(value);
let identityRejected = false;
try {
  review.normalizeComparison({
    ...value,
    candidates: {
      ...value.candidates,
      candidate_a: {
        ...value.candidates.candidate_a,
        identity: "listening_master",
      },
    },
  });
} catch { identityRejected = true; }
let levelRejected = false;
try {
  review.normalizeComparison({
    ...value,
    candidates: {
      ...value.candidates,
      candidate_b: {
        ...value.candidates.candidate_b,
        applied_gain_db: -2.5,
      },
    },
  });
} catch { levelRejected = true; }
return {
  accepted: accepted.comparison_sha256,
  identityRejected,
  levelRejected,
};
"""
        )

        self.assertEqual(result["accepted"], "a" * 64)
        self.assertTrue(result["identityRejected"])
        self.assertTrue(result["levelRejected"])

    def test_prepare_is_bounded_and_sends_only_explicit_review_inputs(self) -> None:
        result = self.run_node(
            """
const sha = letter => letter.repeat(64);
const artifacts = {
  selection_manifest_sha256: sha("a"),
  balanced_arrangement_manifest_sha256: sha("b"),
  listening_master_manifest_sha256: sha("c"),
};
const calls = [];
const prepared = {
  status: "unreviewed",
  comparison_sha256: sha("d"),
  ...artifacts,
  expected_revision: 0,
  window: {start_seconds: 2, end_seconds: 9},
  candidates: {
    candidate_a: {audio_url: "/media/a"},
    candidate_b: {audio_url: "/media/b"},
  },
};
const api = async(path, options) => {
  calls.push({path, method: options.method, body: JSON.parse(options.body)});
  return {comparison: prepared};
};
const button = {};
const fields = {
  "#prepare-master-review": button,
  "#master-review-start": {value: "2"},
  "#master-review-end": {value: "9"},
};
const holder = {
  innerHTML: "",
  querySelector(selector) { return fields[selector] || null; },
  querySelectorAll() { return []; },
};
let changed = null;
const controller = review.createMasterReview({
  api,
  onComparisonChange(value) { changed = value; },
});
controller.setArtifacts(artifacts).renderInto(holder);
await button.onclick();
return {
  calls,
  status: controller.snapshot().comparison_status,
  changed: changed?.comparison_sha256,
};
"""
        )

        self.assertEqual(
            result["calls"],
            [
                {
                    "path": "/api/listening-master-review/prepare",
                    "method": "POST",
                    "body": {
                        "selection_manifest_sha256": "a" * 64,
                        "balanced_arrangement_manifest_sha256": "b" * 64,
                        "listening_master_manifest_sha256": "c" * 64,
                        "start_seconds": 2,
                        "end_seconds": 9,
                    },
                }
            ],
        )
        self.assertEqual(result["status"], "unreviewed")
        self.assertEqual(result["changed"], "d" * 64)

    def test_workbench_mount_keeps_review_outside_decision_event_route(self) -> None:
        self.assertIn(
            '<script src="/workbench-master-review.js"></script>',
            self.page,
        )
        self.assertIn('id="listening-master-review-result"', self.page)
        self.assertIn("currentMasterReviewArtifacts()", self.page)
        self.assertIn(
            "project.listening_master_review=response.listening_master_review||null",
            self.page,
        )
        self.assertIn("masterReview.reset()", self.page)
        self.assertNotIn("/api/events", self.source)
        self.assertIn("Complete blind review", self.source)
        self.assertIn("Resolve A/B identities", self.source)
        self.assertIn("Playback alone records no feedback", self.source)
        self.assertNotIn("autoplay", self.source.lower())
        self.assertNotIn("localStorage", self.page)
        self.assertNotIn("reviewerSessionKey", self.source)

    def test_completion_requires_explicit_heard_evidence_and_resolve_is_separate(
        self,
    ) -> None:
        result = self.run_node(
            """
const sha = letter => letter.repeat(64);
const artifacts = {
  selection_manifest_sha256: sha("a"),
  balanced_arrangement_manifest_sha256: sha("b"),
  listening_master_manifest_sha256: sha("c"),
};
const prepared = {
  status: "unreviewed",
  comparison_sha256: sha("d"),
  ...artifacts,
  expected_revision: 0,
  window: {start_seconds: 2, end_seconds: 9},
  candidates: {
    candidate_a: {audio_url: "/media/a"},
    candidate_b: {audio_url: "/media/b"},
  },
  allowed_problem_tags: ["muddy"],
  maximum_problem_tags: 8,
  maximum_notes_characters: 2000,
};
const reviewed = {
  status: "reviewed",
  comparison_sha256: sha("d"),
  ...artifacts,
  expected_revision: 1,
  review: {
    review_id: sha("e"),
    review_sha256: sha("f"),
    revision: 1,
    choice: "candidate_a",
    response: {
      heard: {candidate_a: true, candidate_b: true},
      choice: "candidate_a",
      problem_tags: {candidate_a: [], candidate_b: []},
      notes: "clearer",
    },
  },
};
const resolved = {
  status: "resolved",
  comparison_sha256: sha("d"),
  ...artifacts,
  review: reviewed.review,
  result: {
    assignment: {
      candidate_a: "balanced_control",
      candidate_b: "listening_master",
    },
    resolved_choice: "balanced_control",
  },
};
const calls = [];
const api = async(path, options) => {
  calls.push({path, body: JSON.parse(options.body)});
  if (path.endsWith("/resolve")) return {comparison: resolved};
  return {comparison: reviewed};
};
const heardA = {checked: false, dataset: {masterReviewHeard: "candidate_a"}};
const heardB = {checked: false, dataset: {masterReviewHeard: "candidate_b"}};
const choice = {checked: false, value: "candidate_a"};
const complete = {disabled: true};
const resolve = {};
const notes = {value: "clearer"};
const position = {textContent: ""};
const draftStatus = {textContent: ""};
const audio = () => ({
  loop: false, volume: 0, currentTime: 0, duration: 7,
  pause() {}, play() { return Promise.resolve(); },
});
const audioA = audio(), audioB = audio();
const holder = {
  innerHTML: "",
  querySelector(selector) {
    return {
      "#master-review-audio-a": audioA,
      "#master-review-audio-b": audioB,
      "#complete-master-review": complete,
      "#resolve-master-review": resolve,
      "#master-review-notes": notes,
      "#master-review-position": position,
      "#master-review-draft-status": draftStatus,
    }[selector] || null;
  },
  querySelectorAll(selector) {
    if (selector === "[data-master-review-heard]") return [heardA, heardB];
    if (selector === 'input[name="master-review-choice"]') return [choice];
    return [];
  },
};
const controller = review.createMasterReview({api});
controller.setArtifacts(artifacts).setComparison(prepared).renderInto(holder);
const initiallyDisabled = complete.disabled;
heardA.checked = true; heardA.onchange();
heardB.checked = true; heardB.onchange();
choice.checked = true; choice.onchange();
notes.oninput();
const enabledAfterEvidence = !complete.disabled;
await complete.onclick();
await resolve.onclick();
return {
  initiallyDisabled,
  enabledAfterEvidence,
  calls,
  status: controller.snapshot().comparison_status,
  audioVolumes: [audioA.volume, audioB.volume],
};
"""
        )

        self.assertTrue(result["initiallyDisabled"])
        self.assertTrue(result["enabledAfterEvidence"])
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["audioVolumes"], [1, 1])
        self.assertEqual(
            result["calls"][0],
            {
                "path": "/api/listening-master-review",
                "body": {
                    "comparison_sha256": "d" * 64,
                    "expected_revision": 0,
                    "heard": {
                        "candidate_a": True,
                        "candidate_b": True,
                    },
                    "choice": "candidate_a",
                    "problem_tags": {
                        "candidate_a": [],
                        "candidate_b": [],
                    },
                    "notes": "clearer",
                },
            },
        )
        self.assertEqual(
            result["calls"][1],
            {
                "path": "/api/listening-master-review/resolve",
                "body": {
                    "comparison_sha256": "d" * 64,
                    "review_id": "e" * 64,
                    "review_sha256": "f" * 64,
                },
            },
        )

    def test_delayed_completion_cannot_be_submitted_twice(self) -> None:
        result = self.run_node(
            """
const sha = letter => letter.repeat(64);
const artifacts = {
  selection_manifest_sha256: sha("a"),
  balanced_arrangement_manifest_sha256: sha("b"),
  listening_master_manifest_sha256: sha("c"),
};
const prepared = {
  status: "unreviewed",
  comparison_sha256: sha("d"),
  ...artifacts,
  expected_revision: 0,
  window: {start_seconds: 2, end_seconds: 9},
  candidates: {
    candidate_a: {audio_url: "/media/a"},
    candidate_b: {audio_url: "/media/b"},
  },
  allowed_problem_tags: [],
};
const reviewed = {
  status: "reviewed",
  comparison_sha256: sha("d"),
  ...artifacts,
  expected_revision: 1,
  review: {
    review_id: sha("e"),
    review_sha256: sha("f"),
    revision: 1,
    choice: "candidate_a",
    response: {
      heard: {candidate_a: true, candidate_b: true},
      choice: "candidate_a",
      problem_tags: {candidate_a: [], candidate_b: []},
      notes: null,
    },
  },
};
let release;
const gate = new Promise(resolve => { release = resolve; });
let calls = 0;
const api = async() => {
  calls += 1;
  await gate;
  return {comparison: reviewed};
};
const heardA = {checked: false, dataset: {masterReviewHeard: "candidate_a"}};
const heardB = {checked: false, dataset: {masterReviewHeard: "candidate_b"}};
const choice = {checked: false, value: "candidate_a"};
const complete = {disabled: true};
const holder = {
  innerHTML: "",
  querySelector(selector) {
    return {
      "#complete-master-review": complete,
      "#master-review-notes": {value: ""},
      "#master-review-position": {textContent: ""},
      "#master-review-draft-status": {textContent: ""},
    }[selector] || null;
  },
  querySelectorAll(selector) {
    if (selector === "[data-master-review-heard]") return [heardA, heardB];
    if (selector === 'input[name="master-review-choice"]') return [choice];
    return [];
  },
};
const controller = review.createMasterReview({api});
controller.setArtifacts(artifacts).setComparison(prepared).renderInto(holder);
heardA.checked = true; heardA.onchange();
heardB.checked = true; heardB.onchange();
choice.checked = true; choice.onchange();
const submit = complete.onclick;
const first = submit();
const second = submit();
const disabledWhilePending = complete.disabled;
release();
await Promise.all([first, second]);
return {
  calls,
  disabledWhilePending,
  status: controller.snapshot().comparison_status,
};
"""
        )

        self.assertEqual(result["calls"], 1)
        self.assertTrue(result["disabledWhilePending"])
        self.assertEqual(result["status"], "reviewed")


if __name__ == "__main__":
    unittest.main()
