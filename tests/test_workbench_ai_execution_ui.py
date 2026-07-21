from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


class WorkbenchAIExecutionProvenanceUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.page = Path("src/sunofriend/workbench.html").read_text(encoding="utf-8")
        cls.details = cls.page.split("function executionProvenanceDetails", 1)[1].split(
            "function candidatePreviewHtml", 1
        )[0]

    def render_execution_states(self) -> dict[str, str]:
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is not installed")
        harness = r"""
const fs = require("fs");
const vm = require("vm");
const html = fs.readFileSync("src/sunofriend/workbench.html", "utf8");
const details = "function executionProvenanceDetails" + html
  .split("function executionProvenanceDetails", 2)[1]
  .split("function candidatePreviewHtml", 1)[0];
const context = {};
vm.createContext(context);
vm.runInContext(
  `function esc(value){return String(value ?? "").replace(/[&<>"']/g, "_");}\n${details}`,
  context,
);
const base = {
  playable: true,
  quality_status: "review-required",
  note_count: 12,
  quality_metrics: {},
  five_second_boundaries: {},
  detected_labels: ["keys"],
  requested_labels: ["keys"],
  elapsed_seconds: 1.25,
  real_time_factor: 0.1,
};
const states = {
  fresh: {
    ...base,
    worker_execution_mode: "fresh-subprocess",
    application_cache_status: "disabled",
    application_cache_hit: false,
    execution_provenance: {
      schema: "sunofriend.workbench-ai-execution-provenance.v1",
      kind: "fresh-subprocess",
    },
  },
  cacheMiss: {
    ...base,
    worker_execution_mode: "fresh-subprocess",
    application_cache_status: "miss-stored",
    application_cache_hit: false,
    execution_provenance: {
      schema: "sunofriend.workbench-ai-execution-provenance.v1",
      kind: "exact-result-cache-miss",
      application_cache_status: "miss-stored",
    },
  },
  cacheHit: {
    ...base,
    worker_execution_mode: "application-cache-hit",
    application_cache_status: "verified-hit",
    application_cache_hit: true,
    execution_provenance: {
      schema: "sunofriend.workbench-ai-execution-provenance.v1",
      kind: "exact-result-cache-hit",
      application_cache_status: "verified-hit",
    },
  },
  sessionFirst: {
    ...base,
    worker_execution_mode: "persistent-session-request",
    application_cache_status: "disabled",
    application_cache_hit: false,
    execution_provenance: {
      schema: "sunofriend.workbench-ai-execution-provenance.v1",
      kind: "bounded-session-first-request",
      bounded_session: {
        request_sequence: 1,
        request_count: 3,
        prior_completed_requests: 0,
        warm_model_request: false,
        model_reused_from_prior_request: false,
        model_loaded_once: true,
        application_content_cache: false,
      },
    },
  },
  sessionWarm: {
    ...base,
    worker_execution_mode: "persistent-session-request",
    application_cache_status: "disabled",
    application_cache_hit: false,
    execution_provenance: {
      schema: "sunofriend.workbench-ai-execution-provenance.v1",
      kind: "bounded-session-reused-model",
      bounded_session: {
        request_sequence: 2,
        request_count: 3,
        prior_completed_requests: 1,
        warm_model_request: true,
        model_reused_from_prior_request: true,
        model_loaded_once: true,
        application_content_cache: false,
      },
    },
  },
};
const rendered = Object.fromEntries(
  Object.entries(states).map(([name, value]) => [name, context.diagnosticDetails(value)]),
);
console.log(JSON.stringify(rendered));
"""
        completed = subprocess.run(
            [node, "-e", harness],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_each_execution_regime_is_explained_in_listener_language(self) -> None:
        rendered = {
            name: value.lower()
            for name, value in self.render_execution_states().items()
        }

        self.assertIn("fresh subprocess", rendered["fresh"])

        self.assertIn("exact-result cache miss", rendered["cacheMiss"])
        self.assertIn("fresh subprocess", rendered["cacheMiss"])

        self.assertIn("exact-result cache hit", rendered["cacheHit"])
        self.assertIn("no ai model ran", rendered["cacheHit"])

        self.assertIn("bounded", rendered["sessionFirst"])
        self.assertIn("session request 1", rendered["sessionFirst"])
        self.assertIn("resident", rendered["sessionFirst"])
        self.assertIn("not warm", rendered["sessionFirst"])

        self.assertIn("bounded", rendered["sessionWarm"])
        self.assertIn("session request 2", rendered["sessionWarm"])
        self.assertIn("reused-model warm", rendered["sessionWarm"])

    def test_execution_copy_cannot_be_read_as_a_musical_vote_or_optimisation(
        self,
    ) -> None:
        for name, rendered in self.render_execution_states().items():
            with self.subTest(state=name):
                copy = rendered.lower()
                self.assertIn("execution provenance", copy)
                self.assertIn("not musical agreement", copy)
                self.assertIn("no optimisation was enabled", copy)

    def test_diagnostics_are_presentational_and_keep_raw_machine_values_hidden(
        self,
    ) -> None:
        self.assertIn("execution_provenance", self.details)
        self.assertIn("bounded_session", self.details)
        self.assertIn("request_sequence", self.details)
        self.assertNotIn("fetch(", self.details)
        self.assertNotIn("api(", self.details)
        self.assertNotIn("/api/events", self.details)
        self.assertNotIn("candidate_decision", self.details)
        self.assertNotIn("automatic_selection", self.details)
        self.assertNotIn("promotion_allowed", self.details)

        rendered = self.render_execution_states()
        self.assertNotIn("persistent-session-request", rendered["sessionFirst"])
        self.assertNotIn("application-cache-hit", rendered["cacheHit"])
        self.assertNotIn("bounded-session-first-request", rendered["sessionFirst"])
        self.assertNotIn("bounded-session-reused-model", rendered["sessionWarm"])
        self.assertNotIn(
            "sunofriend.workbench-ai-execution-provenance.v1",
            "".join(rendered.values()),
        )


if __name__ == "__main__":
    unittest.main()
