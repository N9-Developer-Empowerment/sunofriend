from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

from sunofriend.garageband_pack_acceptance import (
    DEVELOPER_EVIDENCE_SCHEMA,
    DEVELOPER_INSPECTOR_SCHEMA,
    DEVELOPER_SOURCE_MANIFEST_SCHEMA,
    DEVELOPER_TUTORIAL_SCHEMA,
    GARAGEBAND_PACK_ACCEPTANCE_RESULT_SCHEMA,
    GARAGEBAND_PACK_ACCEPTANCE_SCHEMA,
    _QUIZ_BANK,
    create_garageband_pack_acceptance_review,
    resolve_garageband_pack_acceptance_review,
    verify_garageband_pack_archive,
)
from sunofriend.cli import main


class GarageBandPackAcceptanceTests(unittest.TestCase):
    def test_seed_is_neutral_and_html_is_guided_and_local(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pack = _write_pack(root / "sunofriend-garageband-pack.zip")
            report = create_garageband_pack_acceptance_review(pack, root / "review")
            seed = json.loads(Path(report["seed"]).read_text(encoding="utf-8"))
            html = Path(report["html"]).read_text(encoding="utf-8")

            self.assertEqual(seed["schema"], GARAGEBAND_PACK_ACCEPTANCE_SCHEMA)
            self.assertEqual(seed["status"], "unreviewed")
            self.assertFalse(seed["tutorial"]["completed"])
            self.assertEqual(seed["tutorial"]["viewed_slide_ids"], [])
            self.assertEqual(seed["tutorial"]["schema"], DEVELOPER_TUTORIAL_SCHEMA)
            self.assertEqual(seed["tutorial"]["version"], 1)
            self.assertEqual(len(seed["tutorial"]["slides"]), 8)
            required_slide_fields = {
                "slide_id",
                "title",
                "intuition",
                "body",
                "call_path",
                "code_refs",
                "invariants",
                "failure_mode",
                "review_prompt",
                "takeaway",
            }
            self.assertTrue(
                all(
                    set(slide) == required_slide_fields
                    and slide["call_path"]
                    and slide["code_refs"]
                    and slide["invariants"]
                    for slide in seed["tutorial"]["slides"]
                )
            )
            developer = seed["developer_evidence"]
            self.assertEqual(developer["schema"], DEVELOPER_EVIDENCE_SCHEMA)
            self.assertEqual(
                developer["source_manifest"]["schema"],
                DEVELOPER_SOURCE_MANIFEST_SCHEMA,
            )
            self.assertEqual(
                developer["developer_inspector"]["schema"],
                DEVELOPER_INSPECTOR_SCHEMA,
            )
            self.assertEqual(
                seed["tutorial"]["content_sha256"],
                developer["tutorial_content_sha256"],
            )
            self.assertEqual(
                seed["tutorial"]["code_binding_sha256"],
                developer["code_binding_sha256"],
            )
            self.assertTrue(
                all(
                    len(developer[field]) == 64
                    for field in (
                        "tutorial_content_sha256",
                        "quiz_content_sha256",
                        "code_binding_sha256",
                    )
                )
            )
            source_manifest = developer["source_manifest"]
            unsigned_manifest = {
                key: value
                for key, value in source_manifest.items()
                if key != "manifest_sha256"
            }
            self.assertEqual(
                source_manifest["manifest_sha256"],
                _document_sha256(unsigned_manifest),
            )
            repository_root = Path(__file__).parents[1]
            for source in source_manifest["files"]:
                source_path = repository_root / source["source_path"]
                self.assertTrue(source_path.is_file(), source["source_path"])
                self.assertEqual(source["bytes"], source_path.stat().st_size)
                self.assertEqual(source["sha256"], _file_sha256(source_path))
            self.assertTrue(
                all(
                    value is False
                    for value in developer["developer_inspector"]["effects"].values()
                )
            )
            self.assertEqual(seed["quiz"]["question_count"], 10)
            self.assertEqual(seed["quiz"]["pass_score"], 10)
            self.assertEqual(len(seed["quiz"]["questions"]), 10)
            self.assertEqual(
                len({row["question_id"] for row in seed["quiz"]["questions"]}),
                10,
            )
            self.assertTrue(
                all(row["answer"] is None for row in seed["quiz"]["questions"])
            )
            self.assertTrue(
                all(row["correct"] is None for row in seed["quiz"]["questions"])
            )
            self.assertEqual(len(seed["acceptance_checks"]), 2)
            self.assertTrue(
                all(row["outcome"] is None for row in seed["acceptance_checks"])
            )
            self.assertNotIn(str(root), json.dumps(seed))

            self.assertIn('Question <span id="quiz-number"></span> of 10', html)
            self.assertIn("Check answer", html)
            self.assertIn("Retry all 10 questions", html)
            self.assertIn("Human check 1 of 2", html)
            self.assertIn("Human check 2 of 2", html)
            self.assertIn("garageband-pack-resolve", html)
            self.assertIn("10-question one-at-a-time quiz", html)
            self.assertIn("Execution path", html)
            self.assertIn("Invariants to preserve", html)
            self.assertIn("Code-review prompt", html)
            self.assertIn("Optional Developer Inspector", html)
            self.assertIn("Exact tutorial schema, version and code hashes", html)
            self.assertIn("fold_workbench_events", html)
            self.assertIn("developerBrowserState", html)
            self.assertIn('id="acceptance" hidden', html)
            self.assertNotIn("/api/events", html)
            self.assertNotIn("fetch(", html)
            self.assertNotIn("XMLHttpRequest", html)
            self.assertNotIn("localStorage", html)
            self.assertNotIn("sessionStorage", html)

    def test_generated_html_script_parses_in_node(self) -> None:
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is not installed")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pack = _write_pack(root / "pack.zip")
            report = create_garageband_pack_acceptance_review(pack, root / "review")
            html = Path(report["html"]).read_text(encoding="utf-8")
            script = html.split("<script>", 1)[1].split("</script>", 1)[0]
            script_path = root / "acceptance.js"
            script_path.write_text(script, encoding="utf-8")
            completed = subprocess.run(
                [node, "--check", str(script_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_generated_html_runtime_enforces_tutorial_quiz_and_two_checks(self) -> None:
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is not installed")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pack = _write_pack(root / "pack.zip")
            report = create_garageband_pack_acceptance_review(pack, root / "review")
            html = Path(report["html"]).read_text(encoding="utf-8")
            script = html.split("<script>", 1)[1].split("</script>", 1)[0]
            harness = r"""
const elements=new Map();
function makeElement(id){return {id,hidden:false,disabled:false,textContent:'',innerHTML:'',className:'',value:'',dataset:{},classList:{toggle(){}}};}
function element(id){if(!elements.has(id))elements.set(id,makeElement(id));return elements.get(id);}
for(const id of ['quiz','acceptance','export'])element(id).hidden=true;
const steps=['tutorial','quiz','garageband','usability','export'].map(name=>{const value=makeElement('step-'+name);value.dataset.step=name;return value});
let chosenValue=null;
globalThis.document={
  getElementById:element,
  querySelectorAll(selector){return selector==='.step'?steps:[]},
  querySelector(selector){
    if(selector==='input[name="quiz-answer"]:checked')return chosenValue===null?null:{value:chosenValue};
    const item=selector.match(/^input\[name="item-(\d+)"\]:checked$/);if(item)return {value:'pass'};
    if(selector==='input[name="check-outcome"]:checked')return {value:'passed'};
    if(selector.startsWith('[data-item-note='))return {value:''};
    return null;
  }
};
globalThis.scrollTo=()=>{};
globalThis.alert=message=>{throw new Error('unexpected alert: '+message)};
"""
            assertions = r"""
function requireValue(condition,message){if(!condition)throw new Error(message)}
requireValue(byId('acceptance').hidden,'acceptance started unlocked');
for(let index=0;index<review.tutorial.slide_count;index++)byId('slide-next').onclick();
requireValue(review.tutorial.completed,'tutorial did not complete');
requireValue(!byId('quiz').hidden&&byId('acceptance').hidden,'quiz did not precede acceptance');
const firstPrompt=byId('quiz-prompt').textContent;
for(let index=0;index<review.quiz.question_count;index++){
  const question=review.quiz.questions[quizIndex],correct=quizKey[question.question_id].correct;
  chosenValue=index===0?question.options.find(option=>option.option_id!==correct).option_id:correct;
  byId('check-answer').onclick();
  byId('quiz-next').onclick();
  if(index===0)requireValue(byId('quiz-prompt').textContent!==firstPrompt,'quiz did not advance one question');
}
requireValue(review.quiz.score===9&&!review.quiz.passed,'wrong answer did not fail the quiz');
requireValue(byId('start-garageband').disabled&&byId('acceptance').hidden,'failed quiz unlocked acceptance');
byId('retry-quiz').onclick();
requireValue(quizIndex===0&&review.quiz.questions.every(question=>question.answer===null),'retry did not reset all questions');
for(let index=0;index<review.quiz.question_count;index++){
  const question=review.quiz.questions[quizIndex];chosenValue=quizKey[question.question_id].correct;
  byId('check-answer').onclick();byId('quiz-next').onclick();
}
requireValue(review.quiz.score===10&&review.quiz.passed&&!byId('start-garageband').disabled,'10/10 did not unlock the check');
requireValue(byId('acceptance').hidden,'acceptance opened without explicit continue');
byId('start-garageband').onclick();
requireValue(!byId('acceptance').hidden&&byId('export').hidden,'first check did not precede export');
byId('save-check').onclick();
requireValue(checkIndex===1&&byId('export').hidden,'second check did not precede export');
byId('save-check').onclick();
requireValue(review.status==='reviewed'&&!byId('export').hidden,'two checks did not unlock export');
requireValue(review.acceptance_checks.every(check=>check.outcome==='passed'),'check outcomes were not saved');
"""
            runtime_path = root / "acceptance-runtime.js"
            runtime_path.write_text(
                harness + "\n" + script + "\n" + assertions,
                encoding="utf-8",
            )
            completed = subprocess.run(
                [node, str(runtime_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_complete_ten_of_ten_and_two_passes_resolve_the_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pack = _write_pack(root / "pack.zip", downbeat=None)
            report = create_garageband_pack_acceptance_review(pack, root / "review")
            reviewed = _completed_review(Path(report["seed"]))
            reviewed_path = root / "reviewed.json"
            reviewed_path.write_text(
                json.dumps(reviewed, indent=2) + "\n", encoding="utf-8"
            )

            result = resolve_garageband_pack_acceptance_review(
                reviewed_path, pack, root / "result.json"
            )

            self.assertEqual(result["schema"], GARAGEBAND_PACK_ACCEPTANCE_RESULT_SCHEMA)
            self.assertEqual(result["status"], "passed")
            self.assertTrue(result["phase6_read_only_clip_entry_ready"])
            self.assertFalse(result["explicit_hybrid_construction_ready"])
            self.assertEqual(result["quiz"]["score"], 10)
            self.assertEqual(
                result["developer_evidence"]["schema"],
                DEVELOPER_EVIDENCE_SCHEMA,
            )
            self.assertEqual(
                result["tutorial"]["schema"], DEVELOPER_TUTORIAL_SCHEMA
            )
            self.assertEqual(result["tutorial"]["version"], 1)
            self.assertEqual(
                result["tutorial"]["code_binding_sha256"],
                result["developer_evidence"]["code_binding_sha256"],
            )
            self.assertNotIn("attempt", result["quiz"])
            self.assertEqual(result["remaining_local_studio_acceptance_gates"], [])
            self.assertNotIn("sha256", result["review"])
            self.assertFalse(result["review"]["private_review_sha256_included"])
            self.assertEqual(len(result["review"]["redacted_evidence_sha256"]), 64)
            self.assertEqual(
                result["acceptance_checks"][0]["downbeat_evidence"],
                "reviewer-observation-only",
            )
            self.assertTrue(all(value is False for value in result["effects"].values()))
            self.assertNotIn(str(root), json.dumps(result))

    def test_known_issue_resolves_as_needs_changes_without_applying_anything(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pack = _write_pack(root / "pack.zip", downbeat="bar 1 beat 1")
            report = create_garageband_pack_acceptance_review(pack, root / "review")
            reviewed = _completed_review(Path(report["seed"]))
            reviewed["acceptance_checks"][0]["items"][5]["choice"] = "issue"
            reviewed["acceptance_checks"][0]["items"][5]["notes"] = "drift near end"
            reviewed["acceptance_checks"][0]["outcome"] = "needs_changes"
            reviewed_path = root / "reviewed.json"
            reviewed_path.write_text(json.dumps(reviewed), encoding="utf-8")

            result = resolve_garageband_pack_acceptance_review(
                reviewed_path, pack, root / "result.json"
            )

            self.assertEqual(result["status"], "needs_changes")
            self.assertFalse(result["phase6_read_only_clip_entry_ready"])
            self.assertEqual(result["acceptance_checks"][0]["issue_count"], 1)
            self.assertTrue(result["acceptance_checks"][0]["private_notes_present"])
            self.assertNotIn("drift near end", json.dumps(result))
            redacted_hash = result["review"]["redacted_evidence_sha256"]
            self.assertTrue(all(value is False for value in result["effects"].values()))

            reviewed["acceptance_checks"][0]["items"][5]["notes"] = (
                "different private wording"
            )
            second_reviewed_path = root / "reviewed-again.json"
            second_reviewed_path.write_text(json.dumps(reviewed), encoding="utf-8")
            second = resolve_garageband_pack_acceptance_review(
                second_reviewed_path, pack, root / "result-again.json"
            )
            self.assertEqual(
                second["review"]["redacted_evidence_sha256"], redacted_hash
            )

    def test_wrong_quiz_score_and_immutable_tampering_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pack = _write_pack(root / "pack.zip")
            report = create_garageband_pack_acceptance_review(pack, root / "review")
            reviewed = _completed_review(Path(report["seed"]))
            reviewed["quiz"]["questions"][0]["answer"] = "a"
            reviewed["quiz"]["questions"][0]["correct"] = False
            reviewed["quiz"]["score"] = 9
            reviewed["quiz"]["passed"] = False
            reviewed["summary"]["quiz_score"] = 9
            reviewed["summary"]["quiz_passed"] = False
            wrong_path = root / "wrong.json"
            wrong_path.write_text(json.dumps(reviewed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "at least 10/10"):
                resolve_garageband_pack_acceptance_review(
                    wrong_path, pack, root / "wrong-result.json"
                )

            tampered = _completed_review(Path(report["seed"]))
            tampered["quiz"]["questions"][0]["prompt"] = "Changed question"
            tampered_path = root / "tampered.json"
            tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "immutable evidence"):
                resolve_garageband_pack_acceptance_review(
                    tampered_path, pack, root / "tampered-result.json"
                )

            source_tampered = _completed_review(Path(report["seed"]))
            source_tampered["developer_evidence"]["source_manifest"]["files"][0][
                "sha256"
            ] = "0" * 64
            source_tampered_path = root / "source-tampered.json"
            source_tampered_path.write_text(
                json.dumps(source_tampered), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "immutable evidence"):
                resolve_garageband_pack_acceptance_review(
                    source_tampered_path,
                    pack,
                    root / "source-tampered-result.json",
                )

    def test_malformed_or_oversized_review_fails_as_validation_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pack = _write_pack(root / "pack.zip")
            report = create_garageband_pack_acceptance_review(pack, root / "review")

            for name, field, replacement in (
                ("questions", "quiz", None),
                ("checks", "acceptance_checks", None),
            ):
                malformed = _completed_review(Path(report["seed"]))
                if field == "quiz":
                    malformed["quiz"]["questions"] = replacement
                else:
                    malformed[field] = replacement
                malformed_path = root / f"{name}.json"
                malformed_path.write_text(json.dumps(malformed), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "immutable evidence"):
                    resolve_garageband_pack_acceptance_review(
                        malformed_path, pack, root / f"{name}-result.json"
                    )

            oversized = root / "oversized.json"
            oversized.write_bytes(b"{" + b" " * (4 * 1024 * 1024) + b"}")
            with self.assertRaisesRegex(ValueError, "too large"):
                resolve_garageband_pack_acceptance_review(
                    oversized, pack, root / "oversized-result.json"
                )

    def test_archive_verifier_rejects_changed_member_and_extra_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            changed = _write_pack(root / "changed.zip", midi_payload=b"expected")
            _rewrite_member(changed, "MIDI/01-keys-main.mid", b"changed!")
            with self.assertRaisesRegex(ValueError, "hash changed"):
                verify_garageband_pack_archive(changed)

            extra = _write_pack(root / "extra.zip")
            with zipfile.ZipFile(extra, "a") as archive:
                archive.writestr("../escape.txt", "no")
            with self.assertRaisesRegex(ValueError, "unsafe archive path"):
                verify_garageband_pack_archive(extra)

    def test_archive_verifier_rejects_receipt_identity_privacy_and_readme_drift(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wrong_ids = _write_pack(root / "wrong-ids.zip")
            _rewrite_receipt(
                wrong_ids,
                lambda receipt: receipt.update(
                    {
                        "included_item_ids": [
                            "pack-item-" + hashlib.sha256(b"other").hexdigest()
                        ]
                    }
                ),
            )
            with self.assertRaisesRegex(ValueError, "item IDs are inconsistent"):
                verify_garageband_pack_archive(wrong_ids)

            private_field = _write_pack(root / "private-field.zip")
            _rewrite_receipt(
                private_field,
                lambda receipt: receipt.update(
                    {"private_comment": "/Users/alice/private-song"}
                ),
            )
            with self.assertRaisesRegex(ValueError, "receipt fields are invalid"):
                verify_garageband_pack_archive(private_field)

            private_path = _write_pack(
                root / "private-path.zip",
                midi_path="Users/alice/private-song.mid",
            )
            with self.assertRaisesRegex(ValueError, "item 1 path is invalid"):
                verify_garageband_pack_archive(private_path)

            oversized_readme = _write_pack(root / "oversized-readme.zip")
            _rewrite_member(
                oversized_readme,
                "README.txt",
                b"x" * (1024 * 1024 + 1),
            )
            with self.assertRaisesRegex(ValueError, "README size is invalid"):
                verify_garageband_pack_archive(oversized_readme)

    def test_archive_verifier_rejects_invalid_counts_opt_in_and_setup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            boolean_count = _write_pack(root / "boolean-count.zip")
            _rewrite_receipt(
                boolean_count,
                lambda receipt: receipt.update({"selected_midi_count": True}),
            )
            with self.assertRaisesRegex(ValueError, "selected MIDI count"):
                verify_garageband_pack_archive(boolean_count)

            string_opt_in = _write_pack(root / "string-opt-in.zip")
            _rewrite_receipt(
                string_opt_in,
                lambda receipt: receipt.update({"source_audio_opt_in": "false"}),
            )
            with self.assertRaisesRegex(ValueError, "opt-in is invalid"):
                verify_garageband_pack_archive(string_opt_in)

            nonfinite_tuning = _write_pack(root / "nonfinite-tuning.zip")
            _rewrite_receipt(
                nonfinite_tuning,
                lambda receipt: receipt["setup"].update({"tuning_hz": float("nan")}),
            )
            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                verify_garageband_pack_archive(nonfinite_tuning)

            object_downbeat = _write_pack(root / "object-downbeat.zip")
            _rewrite_receipt(
                object_downbeat,
                lambda receipt: receipt["setup"].update({"downbeat": {"bar": 1}}),
            )
            with self.assertRaisesRegex(ValueError, "downbeat is invalid"):
                verify_garageband_pack_archive(object_downbeat)

    def test_fresh_output_contract_rejects_existing_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pack = _write_pack(root / "pack.zip")
            review_dir = root / "review"
            create_garageband_pack_acceptance_review(pack, review_dir)
            with self.assertRaises(FileExistsError):
                create_garageband_pack_acceptance_review(pack, review_dir)

            reviewed = _completed_review(review_dir / "garageband_pack_acceptance.json")
            reviewed_path = root / "reviewed.json"
            reviewed_path.write_text(json.dumps(reviewed), encoding="utf-8")
            output = root / "result.json"
            output.write_text("existing", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                resolve_garageband_pack_acceptance_review(reviewed_path, pack, output)

    def test_cli_builds_and_resolves_the_guided_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pack = _write_pack(root / "pack.zip")
            review_dir = root / "review"
            with redirect_stdout(io.StringIO()) as output:
                status = main(
                    [
                        "garageband-pack-review",
                        str(pack),
                        "--out-dir",
                        str(review_dir),
                    ]
                )
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.getvalue())["quiz_pass_score"], 10)

            reviewed = _completed_review(review_dir / "garageband_pack_acceptance.json")
            reviewed_path = root / "reviewed.json"
            reviewed_path.write_text(json.dumps(reviewed), encoding="utf-8")
            result_path = root / "result.json"
            with redirect_stdout(io.StringIO()) as output:
                status = main(
                    [
                        "garageband-pack-resolve",
                        str(reviewed_path),
                        str(pack),
                        "--out",
                        str(result_path),
                    ]
                )
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.getvalue())["status"], "passed")
            self.assertTrue(result_path.is_file())


def _document_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _completed_review(seed_path: Path) -> dict[str, object]:
    review = json.loads(seed_path.read_text(encoding="utf-8"))
    review["status"] = "reviewed"
    review["tutorial"]["viewed_slide_ids"] = [
        row["slide_id"] for row in review["tutorial"]["slides"]
    ]
    review["tutorial"]["completed"] = True
    answers = {row["question_id"]: row["correct"] for row in _QUIZ_BANK}
    for question in review["quiz"]["questions"]:
        question["answer"] = answers[question["question_id"]]
        question["correct"] = True
    review["quiz"].update(
        {
            "answered_count": 10,
            "score": 10,
            "passed": True,
            "completed": True,
        }
    )
    for check in review["acceptance_checks"]:
        check["outcome"] = "passed"
        for item in check["items"]:
            item["choice"] = "pass"
    item_count = sum(len(check["items"]) for check in review["acceptance_checks"])
    review["summary"].update(
        {
            "tutorial_completed": True,
            "quiz_answered_count": 10,
            "quiz_score": 10,
            "quiz_passed": True,
            "reviewed_acceptance_item_count": item_count,
            "reviewed_acceptance_check_count": 2,
        }
    )
    return review


def _write_pack(
    path: Path,
    *,
    midi_payload: bytes = b"MThd-fixture-midi",
    downbeat: object = "bar 1 beat 1",
    midi_path: str = "MIDI/01-keys-main.mid",
) -> Path:
    item_id = "pack-item-" + hashlib.sha256(b"item").hexdigest()
    included_item = {
        "item_id": item_id,
        "kind": "selected_midi",
        "archive_path": midi_path,
        "bytes": len(midi_payload),
        "sha256": hashlib.sha256(midi_payload).hexdigest(),
    }

    def digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    manifest = {
        "schema": "sunofriend.workbench-garageband-pack.v1",
        "project_id": digest("project")[:20],
        "selection_sha256": digest("selection"),
        "basket_scope_sha256": digest("scope"),
        "plan_sha256": digest("plan"),
        "basket_sha256": digest("basket"),
        "included_item_ids": [item_id],
        "cache_key": digest("cache"),
        "setup": {
            "bpm": 120.0,
            "key": "D minor",
            "tuning_hz": 440.0,
            "downbeat": downbeat,
        },
        "included_items": [included_item],
        "selected_midi_count": 1,
        "source_audio_count": 0,
        "source_audio_included": False,
        "source_audio_opt_in": False,
        "arrangement_proxy_included": False,
        "selected_midi_overlap": {"pair_count": 0},
        "selection_policy": (
            "the basket is explicit and separate from current musical "
            "main/optional decisions"
        ),
        "private_notes_included": False,
        "absolute_paths_included": False,
        "original_midi_mutated": False,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.txt", "Set GarageBand tempo to 120 BPM\n")
        archive.writestr(
            "sunofriend-garageband-pack.json",
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        )
        archive.writestr(midi_path, midi_payload)
    return path


def _rewrite_member(path: Path, member: str, payload: bytes) -> None:
    temporary = path.with_suffix(".rewritten.zip")
    with (
        zipfile.ZipFile(path) as source,
        zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as target,
    ):
        for info in source.infolist():
            target.writestr(
                info.filename, payload if info.filename == member else source.read(info)
            )
    temporary.replace(path)


def _rewrite_receipt(path: Path, update) -> None:
    with zipfile.ZipFile(path) as archive:
        receipt = json.loads(archive.read("sunofriend-garageband-pack.json"))
    update(receipt)
    _rewrite_member(
        path,
        "sunofriend-garageband-pack.json",
        (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


if __name__ == "__main__":
    unittest.main()
