from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sunofriend.workbench_catalog import (
    _ai_candidate_diagnostics,
    _file_record,
    _validated_ai_execution_provenance,
)
from tests.test_ai_session import AISessionTests as _AISessionFixture


class WorkbenchAIExecutionProvenanceTests(unittest.TestCase):
    def _completed_session(self, root: Path) -> Path:
        fixture_builder = _AISessionFixture(methodName="runTest")
        fixture = fixture_builder._fixture(root)
        return fixture_builder._complete_session(
            root,
            fixture,
            name="keys-bounded-session",
            repetitions=2,
        )

    @staticmethod
    def _diagnostics(run_dir: Path) -> dict:
        midi = run_dir / "candidate.mid"
        diagnostics = _ai_candidate_diagnostics(midi, _file_record(midi))
        if diagnostics is None:
            raise AssertionError("completed session candidate had no diagnostics")
        return diagnostics

    def test_first_and_reused_requests_have_distinct_verified_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self._completed_session(Path(temporary))

            first = self._diagnostics(session / "repetition-001")[
                "execution_provenance"
            ]
            self.assertEqual(first["kind"], "bounded-session-first-request")
            self.assertEqual(first["application_cache_status"], "disabled")
            self.assertFalse(first["application_cache_hit"])
            self.assertFalse(first["optimisation_enabled_by_workbench"])
            self.assertFalse(first["musical_agreement_claimed"])
            self.assertEqual(first["bounded_session"]["request_sequence"], 1)
            self.assertEqual(first["bounded_session"]["request_count"], 2)
            self.assertFalse(first["bounded_session"]["warm_model_request"])
            self.assertFalse(
                first["bounded_session"]["model_reused_from_prior_request"]
            )
            self.assertTrue(first["bounded_session"]["model_loaded_once"])
            self.assertFalse(first["bounded_session"]["application_content_cache"])

            reused = self._diagnostics(session / "repetition-002")[
                "execution_provenance"
            ]
            self.assertEqual(reused["kind"], "bounded-session-reused-model")
            self.assertEqual(reused["bounded_session"]["request_sequence"], 2)
            self.assertEqual(reused["bounded_session"]["prior_completed_requests"], 1)
            self.assertTrue(reused["bounded_session"]["warm_model_request"])
            self.assertTrue(
                reused["bounded_session"]["model_reused_from_prior_request"]
            )
            self.assertTrue(reused["inference_executed_for_run"])
            self.assertFalse(reused["worker_process_started_for_run"])
            self.assertFalse(reused["model_loaded_for_run"])

            encoded = json.dumps(reused, sort_keys=True)
            self.assertNotIn(str(session), encoded)
            self.assertNotIn("worker_instance_id", encoded)
            self.assertNotIn("session_id", encoded)

    def test_missing_or_tampered_parent_session_fails_closed(self) -> None:
        for mutation in ("missing", "warm-flag"):
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as temporary,
            ):
                session = self._completed_session(Path(temporary))
                manifest = session / "session.json"
                if mutation == "missing":
                    manifest.rename(session / "session.hidden.json")
                    message = "parent manifest is missing"
                else:
                    document = json.loads(manifest.read_text(encoding="utf-8"))
                    document["runs"][1]["warm_model_request"] = False
                    manifest.write_text(json.dumps(document), encoding="utf-8")
                    message = "attempt evidence disagrees"
                with self.assertRaisesRegex(ValueError, message):
                    self._diagnostics(session / "repetition-002")

    def test_top_level_reuse_tamper_fails_even_with_valid_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self._completed_session(Path(temporary))
            run_dir = session / "repetition-002"
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["model_reused_from_prior_request"] = False
            run_path.write_text(json.dumps(run), encoding="utf-8")

            session_path = session / "session.json"
            parent = json.loads(session_path.read_text(encoding="utf-8"))
            changed_hash = _AISessionFixture._sha256(run_path)
            parent["runs"][1]["run_json_sha256"] = changed_hash
            parent["attempts"][1]["run_json_sha256"] = changed_hash
            session_path.write_text(json.dumps(parent), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "request provenance disagrees"):
                self._diagnostics(run_dir)

    def test_cache_and_bounded_session_evidence_are_mutually_exclusive(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot combine"):
            _validated_ai_execution_provenance(
                {
                    "worker_execution_mode": "persistent-session-request",
                    "worker_transport": {"mode": "bounded-persistent-session"},
                    "model_reused_from_prior_request": True,
                },
                run_root=Path("/not/read/after-regime-check"),
                cache={
                    "status": "verified-hit",
                    "hit": True,
                    "worker_process_started_for_run": False,
                    "inference_executed_for_run": False,
                    "model_loaded_for_run": False,
                },
            )

    def test_fresh_subprocess_requires_complete_execution_flags(self) -> None:
        run = {
            "worker_execution_mode": "fresh-subprocess",
            "worker_transport": None,
            "worker_process_started_for_run": True,
            "inference_executed_for_run": True,
            "model_loaded_for_run": True,
            "model_reused_from_prior_request": False,
            "application_cache": None,
            "command": ["python", "worker.py"],
            "exit_code": 0,
        }
        cache = {
            "status": "disabled",
            "hit": False,
            "worker_process_started_for_run": True,
            "inference_executed_for_run": True,
            "model_loaded_for_run": True,
        }
        provenance = _validated_ai_execution_provenance(
            run,
            run_root=Path("/not-read-for-fresh-process"),
            cache=cache,
        )
        self.assertEqual(provenance["kind"], "fresh-subprocess")
        self.assertFalse(provenance["application_cache_hit"])

        run["model_loaded_for_run"] = False
        with self.assertRaisesRegex(ValueError, "fresh-subprocess"):
            _validated_ai_execution_provenance(
                run,
                run_root=Path("/not-read-for-fresh-process"),
                cache=cache,
            )


if __name__ == "__main__":
    unittest.main()
