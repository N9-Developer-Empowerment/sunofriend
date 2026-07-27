from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

import sunofriend.mix_feedback as mix_feedback_module
from sunofriend.mix_feedback import (
    BALANCED_MIX_RECEIPT_SCHEMA,
    BALANCED_CONTROL_VARIANT,
    LISTENING_MASTER_VARIANT,
    MAX_NOTES_CHARACTERS,
    MAX_REVIEWER_SESSION_KEY_CHARACTERS,
    MIX_PROFILE_POLICY,
    MIX_PROFILE_SCHEMA,
    MIX_REVIEW_SCHEMA,
    advisory_mix_history,
    build_local_mix_profile,
    load_local_mix_profile,
    record_mix_feedback,
)
from sunofriend.listening_master import (
    FFMPEG_IDENTITY_POLICY,
    LISTENING_MASTER_POLICY,
    LISTENING_MASTER_SCHEMA,
)


class MixFeedbackTests(unittest.TestCase):
    def test_records_private_exact_evidence_with_zero_musical_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = _balanced_evidence(root, name="first")
            original_receipt = evidence["receipt"].read_bytes()
            original_preview = evidence["preview"].read_bytes()
            output = root / "reviews" / "first.json"

            result = record_mix_feedback(
                evidence["receipt"],
                evidence["preview"],
                reviewer_session_key="reviewer-one",
                project_id=evidence["project_id"],
                balanced_arrangement_cache_key=evidence["cache_key"],
                selection_manifest_sha256=evidence["selection_sha256"],
                overall_usefulness="excellent",
                midi_interpretation="good",
                instrumentation="mixed",
                balance="good",
                dynamics="mixed",
                mastering="cannot_tell",
                problem_tags=["wrong_instrument", "bass_too_quiet"],
                notes="The interpolation is useful, but the bass patch is generic.",
                out_path=output,
            )

            review = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(review["schema"], MIX_REVIEW_SCHEMA)
            self.assertEqual(review["status"], "reviewed")
            self.assertEqual(review["artifact_id"], result["artifact_id"])
            self.assertEqual(review["review_id"], result["review_id"])
            self.assertEqual(
                result["observation_id"], result["artifact_id"]
            )
            self.assertEqual(
                review["evidence"]["audition"]["variant"],
                BALANCED_CONTROL_VARIANT,
            )
            self.assertFalse(review["evidence"]["audition"]["mastered"])
            self.assertEqual(
                review["evidence"]["balanced_arrangement_cache_key"],
                evidence["cache_key"],
            )
            self.assertEqual(
                review["evidence"]["selection_manifest_sha256"],
                evidence["selection_sha256"],
            )
            self.assertEqual(
                review["evidence"]["control"]["receipt"]["sha256"],
                _sha256(evidence["receipt"]),
            )
            self.assertEqual(
                review["evidence"]["control"]["receipt"]["bytes"],
                evidence["receipt"].stat().st_size,
            )
            self.assertEqual(
                review["evidence"]["control"]["preview_wav"]["sha256"],
                _sha256(evidence["preview"]),
            )
            self.assertEqual(
                review["evidence"]["control"]["preview_wav"]["bytes"],
                evidence["preview"].stat().st_size,
            )
            self.assertEqual(
                review["evidence"]["audition"]["wav"],
                review["evidence"]["control"]["preview_wav"],
            )
            self.assertEqual(review["evidence"]["mix_policy"], evidence["mix_policy"])
            self.assertEqual(
                review["evidence"]["renderer_policy"],
                evidence["renderer_policy"],
            )
            self.assertEqual(
                set(review["ratings"]),
                {
                    "overall_usefulness",
                    "midi_interpretation",
                    "instrumentation",
                    "balance",
                    "dynamics",
                    "mastering",
                },
            )
            self.assertEqual(
                review["problem_tags"], ["bass_too_quiet", "wrong_instrument"]
            )
            self.assertTrue(review["effects"]["feedback_artifact_created"])
            self.assertTrue(
                all(
                    value is False
                    for key, value in review["effects"].items()
                    if key != "feedback_artifact_created"
                )
            )
            self.assertTrue(review["privacy"]["local_only"])
            self.assertFalse(review["privacy"]["reviewer_session_key_stored"])
            self.assertNotIn("reviewer-one", output.read_text(encoding="utf-8"))
            self.assertFalse(review["privacy"]["network_transmission"])
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertEqual(evidence["receipt"].read_bytes(), original_receipt)
            self.assertEqual(evidence["preview"].read_bytes(), original_preview)

    def test_rejects_mismatched_scope_invalid_categories_and_unbounded_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = _balanced_evidence(root, name="bounds")
            kwargs = _review_kwargs(evidence, root / "review.json")

            with self.assertRaisesRegex(ValueError, "cache key does not match"):
                record_mix_feedback(
                    evidence["receipt"],
                    evidence["preview"],
                    **{
                        **kwargs,
                        "balanced_arrangement_cache_key": _digest("wrong-cache"),
                    },
                )
            with self.assertRaisesRegex(ValueError, "overall_usefulness"):
                record_mix_feedback(
                    evidence["receipt"],
                    evidence["preview"],
                    **{**kwargs, "overall_usefulness": "amazing"},
                )
            with self.assertRaisesRegex(ValueError, "bounded vocabulary"):
                record_mix_feedback(
                    evidence["receipt"],
                    evidence["preview"],
                    **{**kwargs, "problem_tags": ["surprising_custom_tag"]},
                )
            with self.assertRaisesRegex(ValueError, "limited"):
                record_mix_feedback(
                    evidence["receipt"],
                    evidence["preview"],
                    **{**kwargs, "notes": "x" * (MAX_NOTES_CHARACTERS + 1)},
                )
            with self.assertRaisesRegex(ValueError, "mastering must be cannot_tell"):
                record_mix_feedback(
                    evidence["receipt"],
                    evidence["preview"],
                    **{**kwargs, "mastering": "good"},
                )
            with self.assertRaisesRegex(ValueError, "reviewer/session key"):
                record_mix_feedback(
                    evidence["receipt"],
                    evidence["preview"],
                    **{
                        **kwargs,
                        "reviewer_session_key": (
                            "x" * (MAX_REVIEWER_SESSION_KEY_CHARACTERS + 1)
                        ),
                    },
                )

    def test_atomic_no_overwrite_rejects_symlinks_and_leaves_no_temporary_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = _balanced_evidence(root, name="atomic")
            output = root / "private" / "review.json"
            kwargs = _review_kwargs(evidence, output)
            record_mix_feedback(
                evidence["receipt"], evidence["preview"], **kwargs
            )
            first = output.read_bytes()

            with self.assertRaisesRegex(FileExistsError, "already exists"):
                record_mix_feedback(
                    evidence["receipt"], evidence["preview"], **kwargs
                )
            self.assertEqual(output.read_bytes(), first)
            self.assertEqual(list(output.parent.glob(".review.json.*.tmp")), [])

            linked_preview = root / "preview-link.wav"
            linked_preview.symlink_to(evidence["preview"])
            with self.assertRaisesRegex(ValueError, "must not be a symlink"):
                record_mix_feedback(
                    evidence["receipt"],
                    linked_preview,
                    **{**kwargs, "out_path": root / "linked-review.json"},
                )

    def test_publish_race_preserves_unrelated_competitor_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = _balanced_evidence(root, name="publish-race")
            output = root / "private" / "review.json"
            output.parent.mkdir(parents=True)
            competitor = output.parent / "competitor.json"
            competitor_payload = b'{"owned":"by-another-writer"}\n'
            competitor.write_bytes(competitor_payload)
            competitor.chmod(0o644)

            def replace_published_entry(
                _directory_fd: int,
                _name: str,
                _identity: tuple[int, int],
                *,
                label: str,
            ) -> None:
                self.assertIn("published mix feedback", label)
                os.replace(competitor, output)
                raise RuntimeError("simulated post-publish identity race")

            with mock.patch.object(
                mix_feedback_module,
                "_require_entry_identity",
                side_effect=replace_published_entry,
            ):
                with self.assertRaisesRegex(RuntimeError, "identity race"):
                    record_mix_feedback(
                        evidence["receipt"],
                        evidence["preview"],
                        **_review_kwargs(evidence, output),
                    )

            self.assertEqual(output.read_bytes(), competitor_payload)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o644)
            self.assertEqual(list(output.parent.glob(".review.json.*.tmp")), [])

    def test_profile_is_deterministic_advisory_and_contextual(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_evidence = _balanced_evidence(root, name="one")
            second_evidence = _balanced_evidence(root, name="two")
            first_review = root / "review-one.json"
            second_review = root / "review-two.json"
            record_mix_feedback(
                first_evidence["receipt"],
                first_evidence["preview"],
                **{
                    **_review_kwargs(first_evidence, first_review),
                    "overall_usefulness": "excellent",
                    "midi_interpretation": "good",
                    "instrumentation": "mixed",
                    "balance": "good",
                    "dynamics": "good",
                    "mastering": "cannot_tell",
                    "problem_tags": ["wrong_instrument"],
                },
            )
            record_mix_feedback(
                second_evidence["receipt"],
                second_evidence["preview"],
                **{
                    **_review_kwargs(second_evidence, second_review),
                    "overall_usefulness": "good",
                    "midi_interpretation": "mixed",
                    "instrumentation": "poor",
                    "balance": "cannot_tell",
                    "dynamics": "mixed",
                    "mastering": "cannot_tell",
                    "problem_tags": ["wrong_instrument", "melody_masked"],
                },
            )
            first_profile = root / "profile-first.json"
            second_profile = root / "profile-second.json"

            result = build_local_mix_profile(
                [first_review, second_review],
                out_path=first_profile,
            )
            build_local_mix_profile(
                [second_review, first_review],
                out_path=second_profile,
            )
            profile, record = load_local_mix_profile(first_profile)
            advisory = advisory_mix_history(
                profile,
                mix_policy=first_evidence["mix_policy"],
                renderer_policy=first_evidence["renderer_policy"],
            )

            self.assertEqual(profile["schema"], MIX_PROFILE_SCHEMA)
            self.assertEqual(profile["policy"]["name"], MIX_PROFILE_POLICY)
            self.assertEqual(first_profile.read_bytes(), second_profile.read_bytes())
            self.assertEqual(result["profile"]["sha256"], record["sha256"])
            self.assertEqual(profile["observation_count"], 2)
            self.assertEqual(profile["review_count"], 2)
            self.assertEqual(profile["artifact_count"], 2)
            self.assertEqual(
                profile["axis_summaries"]["instrumentation"]["mean_score"], -0.5
            )
            self.assertEqual(
                profile["axis_summaries"]["balance"]["cannot_tell_count"], 1
            )
            self.assertEqual(
                profile["axis_summaries"]["mastering"]["mean_score"], None
            )
            self.assertEqual(profile["problem_tag_counts"]["wrong_instrument"], 2)
            self.assertTrue(advisory["context_match"])
            self.assertEqual(advisory["observation_count"], 2)
            self.assertTrue(
                all(value is False for value in advisory["effects"].values())
            )
            self.assertIn("not a candidate ranking", advisory["meaning"])
            advisory["axis_summaries"]["balance"]["mean_score"] = 99
            self.assertNotEqual(
                profile["axis_summaries"]["balance"]["mean_score"], 99
            )
            self.assertFalse(profile["policy"]["automatic_selection"])
            self.assertFalse(profile["policy"]["candidate_order_changed"])
            self.assertFalse(profile["policy"]["default_selection_changed"])
            self.assertEqual(stat.S_IMODE(first_profile.stat().st_mode), 0o600)

    def test_advisory_never_falls_back_to_unrelated_policy_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            control = _balanced_evidence(root, name="context-control")
            unrelated = _balanced_evidence(
                root,
                name="context-unrelated",
                mix_policy="unrelated-balance-policy",
                renderer_policy="unrelated-renderer-policy",
            )
            master = _listening_master_evidence(
                root,
                evidence=control,
                name="context-master",
            )
            control_review = root / "control.json"
            master_review = root / "master.json"
            unrelated_review = root / "unrelated.json"
            record_mix_feedback(
                control["receipt"],
                control["preview"],
                **{
                    **_review_kwargs(control, control_review),
                    "overall_usefulness": "excellent",
                },
            )
            record_mix_feedback(
                control["receipt"],
                control["preview"],
                **{
                    **_review_kwargs(control, master_review),
                    "reviewer_session_key": "master-listener",
                    "overall_usefulness": "poor",
                    "mastering": "good",
                    "listening_master_receipt_path": master["receipt"],
                    "listening_master_wav_path": master["wav"],
                },
            )
            record_mix_feedback(
                unrelated["receipt"],
                unrelated["preview"],
                **{
                    **_review_kwargs(unrelated, unrelated_review),
                    "overall_usefulness": "unusable",
                },
            )
            profile_path = root / "profile.json"
            build_local_mix_profile(
                [control_review, master_review, unrelated_review],
                out_path=profile_path,
            )
            profile, _record = load_local_mix_profile(profile_path)

            combined = advisory_mix_history(
                profile,
                mix_policy=control["mix_policy"],
                renderer_policy=control["renderer_policy"],
            )
            self.assertEqual(combined["observation_count"], 2)
            self.assertEqual(
                combined["matching_variants"],
                [BALANCED_CONTROL_VARIANT, LISTENING_MASTER_VARIANT],
            )
            self.assertEqual(
                combined["axis_summaries"]["overall_usefulness"]["mean_score"],
                0.5,
            )
            exact_master = advisory_mix_history(
                profile,
                mix_policy=control["mix_policy"],
                renderer_policy=control["renderer_policy"],
                artifact_variant=LISTENING_MASTER_VARIANT,
            )
            self.assertEqual(exact_master["observation_count"], 1)
            self.assertEqual(
                exact_master["axis_summaries"]["overall_usefulness"]["mean_score"],
                -1.0,
            )
            missing = advisory_mix_history(
                profile,
                mix_policy="missing-policy",
                renderer_policy="missing-renderer",
            )
            self.assertEqual(missing["status"], "no_history")
            self.assertFalse(missing["context_match"])
            self.assertEqual(missing["observation_count"], 0)
            self.assertEqual(missing["problem_tag_counts"], {})
            self.assertTrue(
                all(
                    summary["observation_count"] == 0
                    for summary in missing["axis_summaries"].values()
                )
            )

    def test_records_exact_listening_master_bound_to_exact_control(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = _balanced_evidence(root, name="mastered")
            master = _listening_master_evidence(
                root,
                evidence=evidence,
                name="mastered",
            )
            output = root / "master-review.json"

            result = record_mix_feedback(
                evidence["receipt"],
                evidence["preview"],
                **{
                    **_review_kwargs(evidence, output),
                    "mastering": "excellent",
                    "listening_master_receipt_path": master["receipt"],
                    "listening_master_wav_path": master["wav"],
                },
            )

            review = json.loads(output.read_text(encoding="utf-8"))
            audition = review["evidence"]["audition"]
            self.assertEqual(result["artifact_variant"], LISTENING_MASTER_VARIANT)
            self.assertEqual(audition["variant"], LISTENING_MASTER_VARIANT)
            self.assertTrue(audition["mastered"])
            self.assertEqual(audition["policy"], LISTENING_MASTER_POLICY)
            self.assertEqual(audition["wav"]["sha256"], _sha256(master["wav"]))
            self.assertEqual(
                review["evidence"]["control"]["preview_wav"]["sha256"],
                _sha256(evidence["preview"]),
            )
            report = json.loads(master["receipt"].read_text(encoding="utf-8"))
            self.assertEqual(
                report["source"]["sha256"],
                review["evidence"]["control"]["preview_wav"]["sha256"],
            )
            self.assertNotEqual(
                review["artifact_id"],
                _control_artifact_id(root, evidence=evidence),
            )

    def test_listening_master_requires_pair_and_exact_control_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = _balanced_evidence(root, name="master-bounds")
            master = _listening_master_evidence(
                root,
                evidence=evidence,
                name="master-bounds",
            )
            kwargs = {
                **_review_kwargs(evidence, root / "review.json"),
                "mastering": "good",
            }
            with self.assertRaisesRegex(ValueError, "supplied together"):
                record_mix_feedback(
                    evidence["receipt"],
                    evidence["preview"],
                    **{
                        **kwargs,
                        "listening_master_receipt_path": master["receipt"],
                    },
                )

            report = json.loads(master["receipt"].read_text(encoding="utf-8"))
            report["source"]["sha256"] = _digest("different-control")
            report["receipt_sha256"] = _document_hash(
                {
                    key: value
                    for key, value in report.items()
                    if key != "receipt_sha256"
                }
            )
            master["receipt"].write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "exact balanced control"):
                record_mix_feedback(
                    evidence["receipt"],
                    evidence["preview"],
                    **{
                        **kwargs,
                        "listening_master_receipt_path": master["receipt"],
                        "listening_master_wav_path": master["wav"],
                    },
                )

    def test_rejects_incomplete_fabricated_or_mismeasured_master_evidence(
        self,
    ) -> None:
        cases = (
            ("legacy schema", "unsupported listening-master", "legacy_schema"),
            ("missing verification", "unsupported listening-master", "missing"),
            ("non audio", "readable audio", "non_audio"),
            ("wrong geometry", "geometry", "geometry"),
            ("missed target", "missed its receipt targets", "target"),
            ("unverified processing", "processing contract", "processing"),
            ("unpinned renderer", "renderer is invalid", "renderer"),
        )
        for name, message, mutation in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                evidence = _balanced_evidence(root, name=f"strict-{mutation}")
                master = _listening_master_evidence(
                    root,
                    evidence=evidence,
                    name=f"strict-{mutation}",
                )
                report = json.loads(master["receipt"].read_text(encoding="utf-8"))
                if mutation == "legacy_schema":
                    report["schema"] = "sunofriend.listening-master.v1"
                elif mutation == "missing":
                    report.pop("verification_pass")
                elif mutation == "non_audio":
                    master["wav"].write_bytes(b"this is not audio")
                    report["output"]["bytes"] = master["wav"].stat().st_size
                    report["output"]["sha256"] = _sha256(master["wav"])
                elif mutation == "geometry":
                    _write_pcm24_wav(master["wav"], seed=91, frames=900)
                    report["output"]["bytes"] = master["wav"].stat().st_size
                    report["output"]["sha256"] = _sha256(master["wav"])
                elif mutation == "target":
                    report["verification_pass"]["input_i"] = -12.0
                elif mutation == "processing":
                    report["processing"]["encoded_artifact_verified"] = False
                elif mutation == "renderer":
                    report["renderer"]["identity_verification"] = "unchecked"
                report["receipt_sha256"] = _document_hash(
                    {
                        key: value
                        for key, value in report.items()
                        if key != "receipt_sha256"
                    }
                )
                master["receipt"].write_text(
                    json.dumps(report, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ValueError, message):
                    record_mix_feedback(
                        evidence["receipt"],
                        evidence["preview"],
                        **{
                            **_review_kwargs(evidence, root / "review.json"),
                            "mastering": "good",
                            "listening_master_receipt_path": master["receipt"],
                            "listening_master_wav_path": master["wav"],
                        },
                    )

    def test_profile_reverifies_listening_master_receipt_and_wav(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = _balanced_evidence(root, name="master-drift")
            master = _listening_master_evidence(
                root,
                evidence=evidence,
                name="master-drift",
            )
            review = root / "review.json"
            record_mix_feedback(
                evidence["receipt"],
                evidence["preview"],
                **{
                    **_review_kwargs(evidence, review),
                    "mastering": "good",
                    "listening_master_receipt_path": master["receipt"],
                    "listening_master_wav_path": master["wav"],
                },
            )
            master["wav"].write_bytes(b"RIFF changed listening master")
            with self.assertRaisesRegex(ValueError, "master WAV changed"):
                build_local_mix_profile(
                    [review],
                    out_path=root / "drift-profile.json",
                )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = _balanced_evidence(root, name="master-receipt-drift")
            master = _listening_master_evidence(
                root,
                evidence=evidence,
                name="master-receipt-drift",
            )
            review = root / "review.json"
            record_mix_feedback(
                evidence["receipt"],
                evidence["preview"],
                **{
                    **_review_kwargs(evidence, review),
                    "mastering": "good",
                    "listening_master_receipt_path": master["receipt"],
                    "listening_master_wav_path": master["wav"],
                },
            )
            master["receipt"].write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "master receipt changed"):
                build_local_mix_profile(
                    [review],
                    out_path=root / "receipt-drift-profile.json",
                )

    def test_profile_aggregates_independent_reviews_of_same_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = _balanced_evidence(root, name="multi-review")
            first = root / "first.json"
            second = root / "second.json"
            duplicate = root / "duplicate.json"
            first_result = record_mix_feedback(
                evidence["receipt"],
                evidence["preview"],
                **{
                    **_review_kwargs(evidence, first),
                    "reviewer_session_key": "listener-a/session-1",
                    "overall_usefulness": "excellent",
                },
            )
            second_result = record_mix_feedback(
                evidence["receipt"],
                evidence["preview"],
                **{
                    **_review_kwargs(evidence, second),
                    "reviewer_session_key": "listener-b/session-1",
                    "overall_usefulness": "good",
                },
            )
            duplicate_result = record_mix_feedback(
                evidence["receipt"],
                evidence["preview"],
                **{
                    **_review_kwargs(evidence, duplicate),
                    "reviewer_session_key": "listener-a/session-1",
                    "overall_usefulness": "poor",
                },
            )

            self.assertEqual(
                first_result["artifact_id"], second_result["artifact_id"]
            )
            self.assertNotEqual(first_result["review_id"], second_result["review_id"])
            self.assertEqual(first_result["review_id"], duplicate_result["review_id"])
            profile_path = root / "profile.json"
            build_local_mix_profile([first, second], out_path=profile_path)
            profile, _record = load_local_mix_profile(profile_path)
            self.assertEqual(profile["review_count"], 2)
            self.assertEqual(profile["artifact_count"], 1)
            self.assertEqual(
                profile["axis_summaries"]["overall_usefulness"]["mean_score"],
                1.5,
            )
            with self.assertRaisesRegex(
                ValueError, "unique per reviewer and artifact"
            ):
                build_local_mix_profile(
                    [first, duplicate],
                    out_path=root / "duplicate-profile.json",
                )

    def test_profile_rejects_semantic_duplicate_and_changed_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = _balanced_evidence(root, name="duplicate")
            review = root / "review.json"
            record_mix_feedback(
                evidence["receipt"],
                evidence["preview"],
                **_review_kwargs(evidence, review),
            )
            copied_review = root / "copied-review.json"
            copied_review.write_bytes(review.read_bytes())

            with self.assertRaisesRegex(ValueError, "review IDs must be unique"):
                build_local_mix_profile(
                    [review, copied_review],
                    out_path=root / "duplicate-profile.json",
                )

            evidence["preview"].write_bytes(b"RIFF changed preview evidence")
            with self.assertRaisesRegex(ValueError, "preview WAV changed"):
                build_local_mix_profile(
                    [review],
                    out_path=root / "changed-evidence-profile.json",
                )

    def test_profile_load_rejects_tampering_and_later_receipt_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = _balanced_evidence(root, name="load")
            review = root / "review.json"
            profile_path = root / "profile.json"
            record_mix_feedback(
                evidence["receipt"],
                evidence["preview"],
                **_review_kwargs(evidence, review),
            )
            build_local_mix_profile([review], out_path=profile_path)

            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["policy"]["automatic_selection"] = True
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "summary does not match"):
                load_local_mix_profile(profile_path)

            profile_path.unlink()
            build_local_mix_profile([review], out_path=profile_path)
            receipt = json.loads(evidence["receipt"].read_text(encoding="utf-8"))
            receipt["mastered"] = True
            receipt["receipt_sha256"] = _document_hash(
                {
                    key: value
                    for key, value in receipt.items()
                    if key != "receipt_sha256"
                }
            )
            evidence["receipt"].write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "receipt changed"):
                load_local_mix_profile(profile_path)


def _review_kwargs(evidence: dict[str, object], out_path: Path) -> dict[str, object]:
    return {
        "reviewer_session_key": "reviewer-one",
        "project_id": evidence["project_id"],
        "balanced_arrangement_cache_key": evidence["cache_key"],
        "selection_manifest_sha256": evidence["selection_sha256"],
        "overall_usefulness": "good",
        "midi_interpretation": "good",
        "instrumentation": "good",
        "balance": "good",
        "dynamics": "good",
        "mastering": "cannot_tell",
        "problem_tags": [],
        "out_path": out_path,
    }


def _balanced_evidence(
    root: Path,
    *,
    name: str,
    mix_policy: str = "source-referenced-summed-group-balance-v3",
    renderer_policy: str = "role-neutral-general-midi-v3",
) -> dict[str, object]:
    cache_key = _digest(f"{name}-cache")
    cache = root / "balanced-arrangements" / cache_key
    cache.mkdir(parents=True)
    preview = cache / "balanced-selected-midi-preview.wav"
    _write_pcm24_wav(preview, seed=len(name))
    project_id = _digest(f"{name}-project")[:20]
    selection_sha256 = _digest(f"{name}-selection")
    receipt = {
        "schema": BALANCED_MIX_RECEIPT_SCHEMA,
        "project_id": project_id,
        "selection_manifest_sha256": selection_sha256,
        "policy": mix_policy,
        "renderer": {
            "policy": renderer_policy,
            "backend": "FluidSynth neutral-preview render",
            "soundfont_sha256": _digest(f"{name}-soundfont"),
            "soundfont_bytes": 123,
        },
        "preview": {
            "filename": preview.name,
            "bytes": preview.stat().st_size,
            "sha256": _sha256(preview),
        },
        "mastered": False,
    }
    receipt["receipt_sha256"] = _document_hash(receipt)
    receipt_path = cache / "balanced-mix-receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "cache_key": cache_key,
        "project_id": project_id,
        "selection_sha256": selection_sha256,
        "mix_policy": mix_policy,
        "renderer_policy": renderer_policy,
        "receipt": receipt_path,
        "preview": preview,
    }


def _listening_master_evidence(
    root: Path,
    *,
    evidence: dict[str, object],
    name: str,
) -> dict[str, Path]:
    directory = root / "listening-masters" / name
    directory.mkdir(parents=True)
    wav = directory / "balanced-selected-midi-listening-master-v1.wav"
    _write_pcm24_wav(wav, seed=len(name) + 100)
    control = Path(evidence["preview"])
    stats = {
        "input_i": -16.0,
        "input_tp": -1.0,
        "input_lra": 4.0,
        "input_thresh": -26.0,
        "output_i": -16.0,
        "output_tp": -1.0,
        "output_lra": 4.0,
        "output_thresh": -26.0,
        "normalization_type": "dynamic",
        "target_offset": 0.0,
    }
    report = {
        "schema": LISTENING_MASTER_SCHEMA,
        "status": "complete",
        "policy": LISTENING_MASTER_POLICY,
        "label": "Balanced MIDI listening master challenger",
        "mastered": True,
        "release_master": False,
        "mastering_scope": (
            "two-pass integrated-loudness normalisation and true-peak "
            "limiting for comparative listening; not a human-approved "
            "release master"
        ),
        "source": {
            "sha256": _sha256(control),
            "bytes": control.stat().st_size,
            "format": "WAV",
            "subtype": "PCM_24",
            "sample_rate": 44_100,
            "channels": 2,
            "frames": 1_000,
            "duration_seconds": 0.022676,
        },
        "targets": {
            "integrated_lufs": -16.0,
            "loudness_range_lu": 11.0,
            "true_peak_ceiling_dbtp": -1.0,
            "integrated_loudness_tolerance_lu": 0.2,
            "true_peak_tolerance_db": 0.05,
        },
        "analysis_pass": dict(stats),
        "render_pass": dict(stats),
        "verification_pass": {
            **stats,
            "measured_artifact": "encoded_pcm24_output",
        },
        "renderer": {
            "backend": "FFmpeg loudnorm",
            "executable_sha256": _digest("ffmpeg"),
            "version": "ffmpeg version test",
            "filter": "loudnorm",
            "policy": LISTENING_MASTER_POLICY,
            "identity_verification": FFMPEG_IDENTITY_POLICY,
        },
        "output": {
            "name": wav.name,
            "sha256": _sha256(wav),
            "bytes": wav.stat().st_size,
            "format": "WAV",
            "subtype": "PCM_24",
            "sample_rate": 44_100,
            "channels": 2,
            "frames": 1_000,
            "duration_seconds": 0.022676,
        },
        "timing": {
            "policy": "retain-input-frame-horizon-v1",
            "input_frames": 1_000,
            "output_frames": 1_000,
            "sample_rate": 44_100,
            "frame_horizon_changed": False,
            "time_shift_applied": False,
            "time_stretch_applied": False,
        },
        "processing": {
            "integrated_loudness_normalisation": True,
            "true_peak_limiting": True,
            "normalization_type": "dynamic",
            "encoded_artifact_verified": True,
            "equalisation": False,
            "stereo_widening": False,
            "reverb": False,
            "chorus": False,
            "saturation": False,
        },
        "effects": {
            "source_audio_mutated": False,
            "source_audio_overwritten": False,
            "midi_mutated": False,
            "selection_changed": False,
            "feedback_recorded": False,
            "automatic_selection": False,
            "automatic_ranking": False,
            "default_selection_changed": False,
            "control_balance_replaced": False,
            "listening_master_created": True,
        },
    }
    report["receipt_sha256"] = _document_hash(report)
    receipt = directory / "listening-master-receipt.json"
    receipt.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"receipt": receipt, "wav": wav}


def _write_pcm24_wav(
    path: Path,
    *,
    seed: int,
    frames: int = 1_000,
    sample_rate: int = 44_100,
    channels: int = 2,
) -> None:
    sample = int(seed % 4_096).to_bytes(3, "little", signed=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(3)
        output.setframerate(sample_rate)
        output.writeframes(sample * channels * frames)


def _control_artifact_id(
    root: Path,
    *,
    evidence: dict[str, object],
) -> str:
    result = record_mix_feedback(
        Path(evidence["receipt"]),
        Path(evidence["preview"]),
        **_review_kwargs(evidence, root / "control-review.json"),
    )
    return str(result["artifact_id"])


def _document_hash(value: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
