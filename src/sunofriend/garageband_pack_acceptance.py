"""Guided, hash-pinned Phase 5 GarageBand pack acceptance review.

The review is deliberately local and report-only.  It teaches the Workbench
contract, checks understanding with a retryable quiz, records two explicit
human checks and re-verifies the unchanged GarageBand ZIP before resolution.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import stat
import zipfile
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


GARAGEBAND_PACK_SCHEMA = "sunofriend.workbench-garageband-pack.v1"
GARAGEBAND_PACK_ACCEPTANCE_SCHEMA = "sunofriend.workbench-garageband-pack-acceptance.v1"
GARAGEBAND_PACK_ACCEPTANCE_RESULT_SCHEMA = (
    "sunofriend.workbench-garageband-pack-acceptance-result.v1"
)

_MANIFEST_NAME = "sunofriend-garageband-pack.json"
_README_NAME = "README.txt"
_MAX_ARCHIVE_MEMBERS = 1024
_MAX_ARCHIVE_UNCOMPRESSED_BYTES = 4 * 1024 * 1024 * 1024
_MAX_MANIFEST_BYTES = 2 * 1024 * 1024
_MAX_README_BYTES = 1024 * 1024
_MAX_REVIEW_ARTIFACT_BYTES = 4 * 1024 * 1024
_QUIZ_PASS_SCORE = 10
_CHECK_CHOICES = {"pass", "issue", "cannot_tell"}
_CHECK_OUTCOMES = {"passed", "needs_changes", "incomplete"}


_TUTORIAL_SLIDES: tuple[dict[str, Any], ...] = (
    {
        "slide_id": "purpose",
        "title": "Sunofriend is a result-space tool",
        "body": (
            "Sunofriend turns isolated stems into several evidence-backed MIDI "
            "alternatives. It helps you compare, choose and export; it is not a "
            "replacement for Suno, stem separation or GarageBand, and it does not "
            "choose the best melody automatically."
        ),
        "takeaway": "The goal is a useful, editable musical decision—not one magic score.",
    },
    {
        "slide_id": "workflow",
        "title": "The workflow keeps evidence visible",
        "body": (
            "A source stem and optional chord evidence lead to analytical, specialist, "
            "AI and reviewed-repair MIDI candidates. You compare each candidate with "
            "the source, save an explicit main or optional choice, hear the selected "
            "arrangement, then build an exact GarageBand pack."
        ),
        "takeaway": "Different methods may be useful for different roles or phrases.",
    },
    {
        "slide_id": "comparison",
        "title": "Several methods, no automatic winner",
        "body": (
            "Metrics, labels, overlap and visual alignment are listening evidence, not "
            "proof of musical accuracy. Main, optional, needs-correction, reject, none "
            "usable and cannot tell remain human decisions. Playing or looking at a "
            "candidate never silently promotes it."
        ),
        "takeaway": "Recognition and usefulness in context outrank a single automated score.",
    },
    {
        "slide_id": "state",
        "title": "Decisions, audition and export are separate",
        "body": (
            "Main/optional decisions define the musical arrangement. Play, loop, zoom, "
            "mute, solo, level and preset controls are temporary audition state. The "
            "Pack Composer basket independently chooses which eligible files enter one "
            "ZIP; changing a checkbox does not change the musical decision."
        ),
        "takeaway": "Listening controls and pack contents have zero feedback or MIDI effect.",
    },
    {
        "slide_id": "timing",
        "title": "BPM, recorded zero and downbeat are different facts",
        "body": (
            "Set GarageBand to the exact pack BPM before importing MIDI. Every Workbench "
            "lane begins at recorded zero, but recorded zero does not prove where the "
            "musical downbeat is. Confirm any pickup or downbeat by ear and check the "
            "beginning, middle and end for drift."
        ),
        "takeaway": "Correct tempo is necessary; musical alignment still needs listening.",
    },
    {
        "slide_id": "instruments",
        "title": "MIDI performance and instrument sound are separate",
        "body": (
            "The numbered MIDI files contain editable notes, timing, duration and "
            "expression. A neutral preview or dry arrangement proxy uses a consistent "
            "local sound only for comparison. In GarageBand, choose a playable patch for "
            "each Software Instrument track; the proxy is not the final instrument."
        ),
        "takeaway": "A good transcription can sound wrong through an unsuitable patch.",
    },
    {
        "slide_id": "pack",
        "title": "The pack is exact and privacy-first",
        "body": (
            "Active checked MIDI is copied byte-for-byte. Rejected, needs-correction, "
            "unreviewed and superseded MIDI stays out. Source audio is excluded by the "
            "safe default and enters only after a separate explicit local opt-in. The "
            "receipt is path-free, although copied source/MIDI may retain embedded metadata."
        ),
        "takeaway": "Inspect a pack before sharing it; ordinary use and review stay local.",
    },
    {
        "slide_id": "durability-and-phases",
        "title": "What survives, and what comes next",
        "body": (
            "Saved decisions, Overview state and the pack basket survive a restart. "
            "Prepared audio, playhead, loops, zoom and mixer controls reset. Passing this "
            "review opens the first read-only Phase 6 Clip Library slice; explicit hybrid "
            "construction still waits for separate Phase 5.3 lineage and blind-choice gates."
        ),
        "takeaway": "Phase 6 extends reviewed parts without erasing their sources or provenance.",
    },
)


_QUIZ_BANK: tuple[dict[str, Any], ...] = (
    {
        "question_id": "q01-purpose",
        "prompt": "What is Sunofriend's main job?",
        "options": (
            ("a", "Generate a finished song and choose every instrument automatically"),
            (
                "b",
                "Present evidence-backed MIDI alternatives so a person can choose and export editable parts",
            ),
            ("c", "Replace GarageBand's mixer and patch library"),
        ),
        "correct": "b",
        "explanation": "Sunofriend supports comparison and explicit decisions; GarageBand remains the final instrument and mixing environment.",
    },
    {
        "question_id": "q02-methods",
        "prompt": "Two processes produce different MIDI for the same stem. What should happen?",
        "options": (
            ("a", "Keep only the candidate with the highest automated score"),
            ("b", "Merge them automatically"),
            (
                "c",
                "Keep both as evidence and choose by listening for that role or phrase",
            ),
        ),
        "correct": "c",
        "explanation": "Scores and agreement guide listening but do not establish one universal winner.",
    },
    {
        "question_id": "q03-audition-state",
        "prompt": "What durable change is made by Play, loop, mute, solo, zoom or level controls?",
        "options": (
            ("a", "None; they are temporary audition/view state"),
            ("b", "The loudest candidate becomes main"),
            ("c", "The current mix is written into the MIDI"),
        ),
        "correct": "a",
        "explanation": "Temporary transport and view controls never record feedback, select MIDI or alter export state.",
    },
    {
        "question_id": "q04-selection-vs-basket",
        "prompt": "How does a main/optional decision differ from a Pack Composer checkbox?",
        "options": (
            ("a", "There is no difference"),
            (
                "b",
                "The decision defines the musical arrangement; the checkbox only controls files in one ZIP",
            ),
            ("c", "The checkbox retrains the transcription model"),
        ),
        "correct": "b",
        "explanation": "Musical choice and file inclusion are intentionally separate contracts.",
    },
    {
        "question_id": "q05-proxy",
        "prompt": "What does the dry selected-arrangement proxy prove?",
        "options": (
            ("a", "It identifies the original physical instruments"),
            ("b", "It is the final GarageBand production mix"),
            (
                "c",
                "It is a consistent convenience audition, not an authoritative instrument choice",
            ),
        ),
        "correct": "c",
        "explanation": "The proxy makes selected notes easy to hear through one local policy; final patches are chosen in GarageBand.",
    },
    {
        "question_id": "q06-timing",
        "prompt": "Which GarageBand timing check is correct?",
        "options": (
            (
                "a",
                "Set the exact BPM, confirm the musical downbeat, and check start/middle/end for drift",
            ),
            ("b", "Recorded zero always proves bar 1 beat 1"),
            ("c", "GarageBand can use any BPM because MIDI timing is absolute audio"),
        ),
        "correct": "a",
        "explanation": "Tempo, file origin and musical downbeat are separate; a full-song listening check is still required.",
    },
    {
        "question_id": "q07-source-privacy",
        "prompt": "When does original source audio enter a GarageBand pack?",
        "options": (
            ("a", "Whenever a source stem was played"),
            (
                "b",
                "Only after the separate explicit local source-audio opt-in and file selection",
            ),
            ("c", "Always, because MIDI needs it"),
        ),
        "correct": "b",
        "explanation": "Source audio is excluded by default; listening never checks it for export.",
    },
    {
        "question_id": "q08-instrument",
        "prompt": "Imported MIDI is quiet or sounds wrong. What is the first useful check?",
        "options": (
            ("a", "Delete the MIDI because transcription must have failed"),
            (
                "b",
                "Choose a playable, role-appropriate GarageBand patch and check its range",
            ),
            ("c", "Increase the project BPM until it becomes audible"),
        ),
        "correct": "b",
        "explanation": "MIDI performance and timbre are separate; patch playability and range materially affect what you hear.",
    },
    {
        "question_id": "q09-restart",
        "prompt": "What should a Workbench restart restore?",
        "options": (
            (
                "a",
                "Saved decisions and basket choices, while temporary playhead/mixer state resets",
            ),
            ("b", "Every playing audio buffer and exact playhead position"),
            ("c", "Nothing at all"),
        ),
        "correct": "a",
        "explanation": "Durable explicit work survives; decoded audio and audition controls are deliberately temporary.",
    },
    {
        "question_id": "q10-phase-boundary",
        "prompt": "What does a passed Phase 5 local acceptance review unlock first?",
        "options": (
            ("a", "Automatic hybrid MIDI and public telemetry"),
            (
                "b",
                "A read-only Phase 6 Clip Library slice; hybrid construction remains separately gated",
            ),
            ("c", "Automatic publication of source audio"),
        ),
        "correct": "b",
        "explanation": "Clip browsing/audition/export can start first; explicit hybrids still need the open lineage and blind-choice evidence.",
    },
)


def create_garageband_pack_acceptance_review(
    pack_path: str | Path,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Create one fresh guided local review for an exact GarageBand pack."""

    pack = Path(pack_path).expanduser().absolute()
    destination = Path(out_dir).expanduser().absolute()
    _require_regular_file(pack, "GarageBand pack")
    if os.path.lexists(destination):
        raise FileExistsError(
            f"GarageBand pack acceptance review exists: {destination}"
        )
    seed = _review_seed(pack)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.mkdir(mode=0o700)
        seed_path = destination / "garageband_pack_acceptance.json"
        html_path = destination / "garageband_pack_acceptance.html"
        _write_json(seed_path, seed)
        html_path.write_text(_review_html(seed), encoding="utf-8")
        seed_path.chmod(0o600)
        html_path.chmod(0o600)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    return {
        "schema": GARAGEBAND_PACK_ACCEPTANCE_SCHEMA,
        "status": "complete",
        "pack_sha256": seed["pack"]["sha256"],
        "quiz_question_count": len(_QUIZ_BANK),
        "quiz_pass_score": _QUIZ_PASS_SCORE,
        "acceptance_check_count": len(seed["acceptance_checks"]),
        "html": str(destination / "garageband_pack_acceptance.html"),
        "seed": str(destination / "garageband_pack_acceptance.json"),
        "effects": _zero_effects(),
    }


def verify_garageband_pack_archive(pack_path: str | Path) -> dict[str, Any]:
    """Stream-verify one standalone Workbench pack without extracting it."""

    pack = Path(pack_path).expanduser().absolute()
    _require_regular_file(pack, "GarageBand pack")
    return _inspect_pack(pack)


def verify_garageband_pack_acceptance_artifacts(
    pack_path: str | Path,
    seed_path: str | Path,
    html_path: str | Path,
) -> dict[str, Any]:
    """Verify that cached neutral learning artifacts match one exact pack."""

    pack = Path(pack_path).expanduser().absolute()
    seed_file = Path(seed_path).expanduser().absolute()
    html_file = Path(html_path).expanduser().absolute()
    _require_regular_file(pack, "GarageBand pack")
    _require_regular_file(seed_file, "GarageBand acceptance seed")
    _require_regular_file(html_file, "GarageBand acceptance HTML")
    if (
        seed_file.stat().st_size > _MAX_REVIEW_ARTIFACT_BYTES
        or html_file.stat().st_size > _MAX_REVIEW_ARTIFACT_BYTES
    ):
        raise ValueError("GarageBand acceptance artifact is too large")
    expected_seed = _review_seed(pack)
    actual_seed = _read_json(seed_file)
    if not _browser_json_equal(actual_seed, expected_seed):
        raise ValueError("GarageBand acceptance seed does not match the exact pack")
    expected_html = _review_html(expected_seed).encode("utf-8")
    try:
        actual_html = html_file.read_bytes()
    except OSError as exc:
        raise ValueError("GarageBand acceptance HTML cannot be read") from exc
    if actual_html != expected_html:
        raise ValueError("GarageBand acceptance HTML does not match the exact pack")
    return {
        "pack_sha256": expected_seed["pack"]["sha256"],
        "seed": _file_record(seed_file),
        "html": _file_record(html_file),
    }


def resolve_garageband_pack_acceptance_review(
    review_path: str | Path,
    pack_path: str | Path,
    out: str | Path,
) -> dict[str, Any]:
    """Verify one reviewed export and exact pack, then write a zero-effect result."""

    review_file = Path(review_path).expanduser().absolute()
    pack = Path(pack_path).expanduser().absolute()
    output = Path(out).expanduser().absolute()
    _require_regular_file(review_file, "reviewed GarageBand acceptance JSON")
    _require_regular_file(pack, "GarageBand pack")
    if os.path.lexists(output):
        raise FileExistsError(f"GarageBand pack acceptance result exists: {output}")
    review = _read_json(review_file)
    seed = _review_seed(pack)
    if review.get("schema") != GARAGEBAND_PACK_ACCEPTANCE_SCHEMA:
        raise ValueError("Unsupported GarageBand pack acceptance review schema")
    if not _browser_json_equal(
        _immutable_review_document(review),
        _immutable_review_document(seed),
    ):
        raise ValueError("GarageBand acceptance review changed immutable evidence")
    if review.get("status") != "reviewed":
        raise ValueError("GarageBand pack acceptance review is not complete")
    if review.get("effects") != _zero_effects():
        raise ValueError("GarageBand acceptance review declares an automatic effect")

    tutorial = _validate_tutorial(review.get("tutorial"))
    quiz = _validate_quiz(review.get("quiz"))
    checks = _validate_acceptance_checks(review.get("acceptance_checks"), seed)
    expected_summary = _review_summary(tutorial, quiz, checks)
    if review.get("summary") != expected_summary:
        raise ValueError("GarageBand acceptance review summary is inconsistent")

    check_outcomes = {row["check_id"]: row["outcome"] for row in checks}
    gate_passed = quiz["passed"] and all(
        outcome == "passed" for outcome in check_outcomes.values()
    )
    if gate_passed:
        result_status = "passed"
    elif any(outcome == "needs_changes" for outcome in check_outcomes.values()):
        result_status = "needs_changes"
    else:
        result_status = "incomplete"
    result = {
        "schema": GARAGEBAND_PACK_ACCEPTANCE_RESULT_SCHEMA,
        "operation": "garageband-pack-acceptance-resolve",
        "status": result_status,
        "phase6_read_only_clip_entry_ready": gate_passed,
        "explicit_hybrid_construction_ready": False,
        "review": {
            "redacted_evidence_sha256": _document_hash(
                _redacted_review_document(review)
            ),
            "private_review_sha256_included": False,
            "notes_retained_only_in_private_review": True,
        },
        "pack": dict(seed["pack"]),
        "automatic_evidence": dict(seed["automatic_evidence"]),
        "tutorial": {
            "completed": tutorial["completed"],
            "slide_count": tutorial["slide_count"],
        },
        "quiz": {
            "question_count": quiz["question_count"],
            "score": quiz["score"],
            "pass_score": quiz["pass_score"],
            "passed": quiz["passed"],
        },
        "acceptance_checks": [
            {
                "check_id": row["check_id"],
                "outcome": row["outcome"],
                "pass_count": row["pass_count"],
                "issue_count": row["issue_count"],
                "cannot_tell_count": row["cannot_tell_count"],
                "private_notes_present": row["private_notes_present"],
                "downbeat_evidence": (
                    "reviewer-observation-only"
                    if row["check_id"] == "garageband-pack"
                    and seed["setup"].get("downbeat") is None
                    else "catalog-and-reviewer"
                    if row["check_id"] == "garageband-pack"
                    else None
                ),
            }
            for row in checks
        ],
        "remaining_local_studio_acceptance_gates": (
            []
            if gate_passed
            else [
                "garageband-pack-acceptance",
                "authorised-local-usability-acceptance",
            ]
        ),
        "separate_open_hybrid_gates": [
            "phase5.3-blind-choice",
            "phase5.3-source-lineage",
        ],
        "effects": _zero_effects(),
        "interpretation": (
            "Local learning and human acceptance evidence only. Resolution does "
            "not edit MIDI, change a Workbench decision or basket, promote a "
            "candidate, start Phase 6 code automatically or submit any data."
        ),
    }
    _write_json_atomic(output, result)
    return result


def _review_seed(pack: Path) -> dict[str, Any]:
    evidence = _inspect_pack(pack)
    quiz_questions = [
        {
            "question_id": row["question_id"],
            "prompt": row["prompt"],
            "options": [
                {"option_id": option_id, "label": label}
                for option_id, label in row["options"]
            ],
            "answer": None,
            "correct": None,
        }
        for row in _QUIZ_BANK
    ]
    setup = evidence["setup"]
    downbeat = setup.get("downbeat")
    downbeat_text = (
        str(downbeat)
        if downbeat is not None
        else "not confirmed — a formal pass must remain incomplete until checked by ear"
    )
    checks = [
        {
            "check_id": "garageband-pack",
            "title": "Human check 1 of 2 — GarageBand pack",
            "purpose": (
                "Confirm that the exact verified pack behaves correctly after import."
            ),
            "outcome": None,
            "notes": "",
            "items": [
                _check_item(
                    "exact-bpm",
                    f"I set GarageBand to exactly {setup.get('bpm')} BPM before importing MIDI.",
                ),
                _check_item(
                    "selected-midi-import",
                    "Every numbered authoritative MIDI file listed below imported on its own editable Software Instrument track, and the set matched what I intended.",
                ),
                _check_item(
                    "playable-patches",
                    "After choosing playable role-appropriate patches, every selected MIDI part produced audible notes across the song.",
                ),
                _check_item(
                    "drum-routing",
                    "Any selected drum or percussion MIDI used the intended GarageBand drum mapping and triggered the expected sound families; when no drum/percussion part was selected, I confirmed this check was not applicable to the pack.",
                ),
                _check_item(
                    "downbeat",
                    f"By listening, I confirmed the pickup/downbeat landed at the intended musical position ({downbeat_text}), or I recorded that I could not confirm it. When no catalog downbeat exists, a pass is reviewer-observation-only.",
                ),
                _check_item(
                    "full-song-alignment",
                    "At the beginning, middle and end, the MIDI stayed aligned with the intended song timing without audible drift.",
                ),
            ],
        },
        {
            "check_id": "local-usability",
            "title": "Human check 2 of 2 — local usability",
            "purpose": (
                "Confirm that the local multi-process workflow is understandable and usable without editing JSON."
            ),
            "outcome": None,
            "notes": "",
            "items": [
                _check_item(
                    "authorised-project",
                    "I intentionally chose this local project for the acceptance check and I am authorised to use its audio and MIDI here.",
                ),
                _check_item(
                    "compare-and-choose",
                    "I could move from Project Overview to source/candidate comparison and save an explicit choice without editing JSON.",
                ),
                _check_item(
                    "result-space-understood",
                    "It was clear that analytical and AI candidates are alternatives and Sunofriend did not choose an automatic winner.",
                ),
                _check_item(
                    "arrangement-audition",
                    "I could audition the selected arrangement and understand source-only, selected-MIDI, hybrid and main-only views.",
                ),
                _check_item(
                    "separate-state",
                    "It was clear that musical decisions, temporary playback/mixer controls and Pack Composer inclusion are separate.",
                ),
                _check_item(
                    "export-and-restart",
                    "I could choose exact pack contents, keep source audio excluded unless opted in, download the ZIP/receipt, and observe durable choices survive while temporary playback state reset.",
                ),
            ],
        },
    ]
    tutorial = {
        "slide_count": len(_TUTORIAL_SLIDES),
        "slides": [dict(row) for row in _TUTORIAL_SLIDES],
        "viewed_slide_ids": [],
        "completed": False,
    }
    quiz = {
        "question_count": len(quiz_questions),
        "pass_score": _QUIZ_PASS_SCORE,
        "answered_count": 0,
        "score": 0,
        "passed": False,
        "completed": False,
        "questions": quiz_questions,
    }
    seed = {
        "schema": GARAGEBAND_PACK_ACCEPTANCE_SCHEMA,
        "status": "unreviewed",
        "review_kind": "guided-phase5-local-studio-acceptance-v1",
        "review_identity_sha256": _document_hash(
            {
                "schema": GARAGEBAND_PACK_ACCEPTANCE_SCHEMA,
                "pack_sha256": evidence["pack"]["sha256"],
                "manifest_sha256": evidence["embedded_manifest"]["sha256"],
            }
        ),
        "pack": evidence["pack"],
        "setup": setup,
        "included_items": evidence["included_items"],
        "embedded_manifest": evidence["embedded_manifest"],
        "automatic_evidence": evidence["automatic_evidence"],
        "tutorial": tutorial,
        "quiz": quiz,
        "acceptance_checks": checks,
        "summary": {
            "tutorial_completed": False,
            "quiz_answered_count": 0,
            "quiz_score": 0,
            "quiz_passed": False,
            "acceptance_item_count": sum(len(row["items"]) for row in checks),
            "reviewed_acceptance_item_count": 0,
            "acceptance_check_count": len(checks),
            "reviewed_acceptance_check_count": 0,
        },
        "effects": _zero_effects(),
        "warnings": [
            "The tutorial and quiz are educational evidence, not a model score or musical preference.",
            "The ZIP integrity checks do not replace listening in GarageBand.",
            "When the catalog has no confirmed downbeat, a pass records reviewer observation only and does not invent hash-pinned downbeat metadata.",
            "The reviewed export can contain private notes; keep it local unless deliberately redacted.",
            "Passing this review does not satisfy the separate Phase 5.3 gates for explicit hybrid construction.",
        ],
    }
    return seed


def _inspect_pack(pack: Path) -> dict[str, Any]:
    try:
        return _inspect_pack_contents(pack)
    except ValueError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile, NotImplementedError) as exc:
        raise ValueError("GarageBand pack ZIP contents cannot be verified") from exc


def _inspect_pack_contents(pack: Path) -> dict[str, Any]:
    pack_record = _file_record(pack)
    try:
        archive = zipfile.ZipFile(pack)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError("GarageBand pack is not a readable ZIP") from exc
    with archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if not infos or len(infos) > _MAX_ARCHIVE_MEMBERS:
            raise ValueError("GarageBand pack member count is invalid")
        if len(set(names)) != len(names):
            raise ValueError("GarageBand pack contains duplicate archive paths")
        if any(
            not _safe_archive_path(name) or info.is_dir()
            for name, info in zip(names, infos)
        ):
            raise ValueError("GarageBand pack contains an unsafe archive path")
        total_uncompressed = sum(info.file_size for info in infos)
        if total_uncompressed > _MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise ValueError("GarageBand pack expands beyond the local review limit")
        if _MANIFEST_NAME not in names or _README_NAME not in names:
            raise ValueError("GarageBand pack is missing its receipt or README")
        manifest_info = archive.getinfo(_MANIFEST_NAME)
        if (
            manifest_info.file_size <= 0
            or manifest_info.file_size > _MAX_MANIFEST_BYTES
        ):
            raise ValueError("GarageBand pack receipt size is invalid")
        manifest_bytes = archive.read(manifest_info)
        try:
            manifest = json.loads(
                manifest_bytes.decode("utf-8"),
                parse_constant=_reject_json_constant,
            )
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError("GarageBand pack receipt is invalid JSON") from exc
        if (
            not isinstance(manifest, Mapping)
            or manifest.get("schema") != GARAGEBAND_PACK_SCHEMA
        ):
            raise ValueError("Unsupported GarageBand pack receipt schema")
        required_manifest_keys = {
            "schema",
            "project_id",
            "selection_sha256",
            "basket_scope_sha256",
            "plan_sha256",
            "basket_sha256",
            "included_item_ids",
            "cache_key",
            "setup",
            "included_items",
            "selected_midi_count",
            "source_audio_count",
            "source_audio_included",
            "source_audio_opt_in",
            "arrangement_proxy_included",
            "selected_midi_overlap",
            "selection_policy",
            "private_notes_included",
            "absolute_paths_included",
            "original_midi_mutated",
        }
        if not required_manifest_keys.issubset(manifest) or set(manifest) - (
            required_manifest_keys | {"arrangement_proxy"}
        ):
            raise ValueError("GarageBand pack receipt fields are invalid")
        rows = manifest.get("included_items")
        if not isinstance(rows, list) or not rows:
            raise ValueError("GarageBand pack receipt has no included items")
        expected_names = {_README_NAME, _MANIFEST_NAME}
        included_items: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, Mapping) or set(row) != {
                "item_id",
                "kind",
                "archive_path",
                "bytes",
                "sha256",
            }:
                raise ValueError(f"GarageBand pack item {index} is invalid")
            item_id = row.get("item_id")
            kind = row.get("kind")
            archive_path = row.get("archive_path")
            byte_count = row.get("bytes")
            sha256 = row.get("sha256")
            if not _is_pack_item_id(item_id) or kind not in {
                "selected_midi",
                "source_audio",
                "arrangement_proxy",
            }:
                raise ValueError(f"GarageBand pack item {index} identity is invalid")
            if (
                not isinstance(archive_path, str)
                or not _safe_archive_path(archive_path)
                or not _canonical_pack_archive_path(str(kind), archive_path)
            ):
                raise ValueError(f"GarageBand pack item {index} path is invalid")
            if archive_path in expected_names:
                raise ValueError("GarageBand pack receipt repeats an archive path")
            if (
                isinstance(byte_count, bool)
                or not isinstance(byte_count, int)
                or byte_count < 0
            ):
                raise ValueError(f"GarageBand pack item {index} size is invalid")
            if not _is_sha256(sha256):
                raise ValueError(f"GarageBand pack item {index} hash is invalid")
            try:
                info = archive.getinfo(archive_path)
            except KeyError as exc:
                raise ValueError(
                    f"GarageBand pack item is missing: {archive_path}"
                ) from exc
            if info.file_size != byte_count:
                raise ValueError(f"GarageBand pack item size changed: {archive_path}")
            digest = hashlib.sha256()
            with archive.open(info) as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != sha256:
                raise ValueError(f"GarageBand pack item hash changed: {archive_path}")
            expected_names.add(archive_path)
            included_items.append(
                {
                    "item_id": item_id,
                    "kind": kind,
                    "archive_path": archive_path,
                    "bytes": byte_count,
                    "sha256": sha256,
                }
            )
        if set(names) != expected_names:
            raise ValueError("GarageBand pack members do not exactly match its receipt")

        included_item_ids = manifest.get("included_item_ids")
        if (
            not isinstance(included_item_ids, list)
            or any(not _is_pack_item_id(value) for value in included_item_ids)
            or len(set(included_item_ids)) != len(included_item_ids)
        ):
            raise ValueError("GarageBand pack included item IDs are invalid")
        row_ids: list[str] = []
        for row in included_items:
            if row["item_id"] not in row_ids:
                row_ids.append(row["item_id"])
        if included_item_ids != row_ids:
            raise ValueError("GarageBand pack included item IDs are inconsistent")
        rows_by_id: dict[str, list[dict[str, Any]]] = {}
        for row in included_items:
            rows_by_id.setdefault(str(row["item_id"]), []).append(row)
        for item_rows in rows_by_id.values():
            kind = item_rows[0]["kind"]
            if any(row["kind"] != kind for row in item_rows):
                raise ValueError("GarageBand pack item ID spans different kinds")
            expected_rows = 2 if kind == "arrangement_proxy" else 1
            if len(item_rows) != expected_rows:
                raise ValueError("GarageBand pack item ID row count is invalid")

        selected_count = sum(row["kind"] == "selected_midi" for row in included_items)
        source_count = sum(row["kind"] == "source_audio" for row in included_items)
        proxy_present = any(
            row["kind"] == "arrangement_proxy" for row in included_items
        )
        declared_selected_count = manifest.get("selected_midi_count")
        if (
            selected_count < 1
            or isinstance(declared_selected_count, bool)
            or not isinstance(declared_selected_count, int)
            or declared_selected_count != selected_count
        ):
            raise ValueError("GarageBand pack selected MIDI count is inconsistent")
        declared_source_count = manifest.get("source_audio_count")
        if (
            isinstance(declared_source_count, bool)
            or not isinstance(declared_source_count, int)
            or declared_source_count != source_count
        ):
            raise ValueError("GarageBand pack source-audio count is inconsistent")
        if manifest.get("source_audio_included") is not (source_count > 0):
            raise ValueError("GarageBand pack source-audio inclusion is inconsistent")
        if type(manifest.get("source_audio_opt_in")) is not bool:
            raise ValueError("GarageBand pack source-audio opt-in is invalid")
        if source_count and manifest.get("source_audio_opt_in") is not True:
            raise ValueError("GarageBand pack source audio has no explicit opt-in")
        if manifest.get("arrangement_proxy_included") is not proxy_present:
            raise ValueError("GarageBand pack proxy inclusion is inconsistent")
        proxy_rows = [
            row for row in included_items if row["kind"] == "arrangement_proxy"
        ]
        proxy_record = manifest.get("arrangement_proxy")
        if proxy_present:
            if (
                not isinstance(proxy_record, Mapping)
                or set(proxy_record) != {"midi_sha256", "preview_sha256"}
                or proxy_record.get("midi_sha256")
                != next(
                    row["sha256"]
                    for row in proxy_rows
                    if row["archive_path"] == "MIDI/selected-arrangement-proxy.mid"
                )
                or proxy_record.get("preview_sha256")
                != next(
                    row["sha256"]
                    for row in proxy_rows
                    if row["archive_path"] == "PREVIEW/selected-arrangement-proxy.wav"
                )
            ):
                raise ValueError("GarageBand pack proxy receipt is inconsistent")
        elif "arrangement_proxy" in manifest:
            raise ValueError("GarageBand pack has an unexpected proxy receipt")
        project_id = manifest.get("project_id")
        if (
            not isinstance(project_id, str)
            or len(project_id) != 20
            or any(character not in "0123456789abcdef" for character in project_id)
        ):
            raise ValueError("GarageBand pack receipt has no valid project_id")
        for field in (
            "selection_sha256",
            "basket_scope_sha256",
            "plan_sha256",
            "basket_sha256",
            "cache_key",
        ):
            if not _is_sha256(manifest.get(field)):
                raise ValueError(f"GarageBand pack receipt has no valid {field}")
        setup = manifest.get("setup")
        if not isinstance(setup, Mapping) or set(setup) != {
            "bpm",
            "key",
            "tuning_hz",
            "downbeat",
        }:
            raise ValueError("GarageBand pack receipt has no setup")
        bpm = setup.get("bpm")
        if (
            isinstance(bpm, bool)
            or not isinstance(bpm, (int, float))
            or not math.isfinite(float(bpm))
            or bpm <= 0
        ):
            raise ValueError("GarageBand pack BPM is invalid")
        key = setup.get("key")
        if key is not None and (not isinstance(key, str) or not key.strip()):
            raise ValueError("GarageBand pack key is invalid")
        tuning_hz = setup.get("tuning_hz")
        if tuning_hz is not None and (
            isinstance(tuning_hz, bool)
            or not isinstance(tuning_hz, (int, float))
            or not math.isfinite(float(tuning_hz))
            or tuning_hz <= 0
        ):
            raise ValueError("GarageBand pack tuning is invalid")
        downbeat = setup.get("downbeat")
        if downbeat is not None and (
            isinstance(downbeat, bool)
            or not isinstance(downbeat, (str, int, float))
            or (isinstance(downbeat, str) and not downbeat.strip())
            or (
                isinstance(downbeat, (int, float))
                and not math.isfinite(float(downbeat))
            )
        ):
            raise ValueError("GarageBand pack downbeat is invalid")
        if manifest.get("private_notes_included") is not False:
            raise ValueError("GarageBand pack receipt declares private notes")
        if manifest.get("absolute_paths_included") is not False:
            raise ValueError("GarageBand pack receipt declares absolute paths")
        if manifest.get("original_midi_mutated") is not False:
            raise ValueError("GarageBand pack receipt declares MIDI mutation")
        if manifest.get("selection_policy") != (
            "the basket is explicit and separate from current musical "
            "main/optional decisions"
        ):
            raise ValueError("GarageBand pack selection policy is invalid")
        if _contains_private_path(manifest):
            raise ValueError("GarageBand pack receipt contains a private path")
        readme_info = archive.getinfo(_README_NAME)
        if readme_info.file_size <= 0 or readme_info.file_size > _MAX_README_BYTES:
            raise ValueError("GarageBand pack README size is invalid")
        readme_digest = hashlib.sha256()
        with archive.open(readme_info) as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                readme_digest.update(block)
        embedded_manifest = {
            "name": _MANIFEST_NAME,
            "bytes": len(manifest_bytes),
            "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "readme_sha256": readme_digest.hexdigest(),
        }
    return {
        "pack": pack_record,
        "setup": {
            "bpm": setup.get("bpm"),
            "key": setup.get("key"),
            "tuning_hz": setup.get("tuning_hz"),
            "downbeat": setup.get("downbeat"),
        },
        "included_items": included_items,
        "embedded_manifest": embedded_manifest,
        "automatic_evidence": {
            "zip_readable": True,
            "pack_schema_verified": True,
            "exact_member_set_verified": True,
            "included_payload_sizes_and_hashes_verified": True,
            "selected_midi_count_verified": selected_count,
            "source_audio_count_verified": source_count,
            "source_audio_opt_in_verified": source_count == 0
            or manifest.get("source_audio_opt_in") is True,
            "arrangement_proxy_present": proxy_present,
            "path_free_receipt_verified": True,
            "private_notes_absent_from_receipt": True,
            "builder_declares_original_midi_unchanged": True,
            "integrity_is_not_garageband_listening": True,
        },
        "receipt": dict(manifest),
    }


def _check_item(item_id: str, prompt: str) -> dict[str, Any]:
    return {"item_id": item_id, "prompt": prompt, "choice": None, "notes": ""}


def _validate_tutorial(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("GarageBand acceptance tutorial is invalid")
    slide_ids = [row["slide_id"] for row in _TUTORIAL_SLIDES]
    viewed = value.get("viewed_slide_ids")
    if value.get("completed") is not True or viewed != slide_ids:
        raise ValueError("Every Sunofriend tutorial slide must be viewed in order")
    return {"completed": True, "slide_count": len(slide_ids)}


def _validate_quiz(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("GarageBand acceptance quiz is invalid")
    questions = value.get("questions")
    if not isinstance(questions, list) or len(questions) != len(_QUIZ_BANK):
        raise ValueError("GarageBand acceptance quiz question count is invalid")
    score = 0
    for question, expected in zip(questions, _QUIZ_BANK):
        options = {option_id for option_id, _label in expected["options"]}
        answer = question.get("answer")
        correct = answer == expected["correct"]
        if answer not in options or question.get("correct") is not correct:
            raise ValueError(f"Quiz answer is invalid for {expected['question_id']}")
        score += int(correct)
    passed = score >= _QUIZ_PASS_SCORE
    expected_fields = {
        "question_count": len(_QUIZ_BANK),
        "pass_score": _QUIZ_PASS_SCORE,
        "answered_count": len(_QUIZ_BANK),
        "score": score,
        "passed": passed,
        "completed": True,
    }
    if any(value.get(key) != expected for key, expected in expected_fields.items()):
        raise ValueError("GarageBand acceptance quiz summary is inconsistent")
    if not passed:
        raise ValueError(
            f"GarageBand acceptance quiz needs at least {_QUIZ_PASS_SCORE}/10"
        )
    return expected_fields


def _validate_acceptance_checks(
    value: Any, seed: Mapping[str, Any]
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("GarageBand acceptance needs exactly two human checks")
    results = []
    seed_checks = seed["acceptance_checks"]
    for check, expected in zip(value, seed_checks):
        if (
            not isinstance(check, Mapping)
            or check.get("check_id") != expected["check_id"]
        ):
            raise ValueError("GarageBand acceptance check identity changed")
        items = check.get("items")
        if not isinstance(items, list) or len(items) != len(expected["items"]):
            raise ValueError("GarageBand acceptance check items changed")
        choices = []
        private_notes_present = bool(str(check.get("notes") or ""))
        if not isinstance(check.get("notes"), str):
            raise ValueError("GarageBand acceptance check notes must be text")
        for item, expected_item in zip(items, expected["items"]):
            if (
                not isinstance(item, Mapping)
                or item.get("item_id") != expected_item["item_id"]
            ):
                raise ValueError("GarageBand acceptance item identity changed")
            choice = item.get("choice")
            if choice not in _CHECK_CHOICES:
                raise ValueError(
                    f"Acceptance item {item.get('item_id')} has no valid answer"
                )
            if not isinstance(item.get("notes"), str):
                raise ValueError("GarageBand acceptance item notes must be text")
            private_notes_present = private_notes_present or bool(item.get("notes"))
            choices.append(str(choice))
        expected_outcome = _expected_check_outcome(choices)
        outcome = check.get("outcome")
        if outcome not in _CHECK_OUTCOMES or outcome != expected_outcome:
            raise ValueError(
                f"Acceptance outcome for {check.get('check_id')} must be {expected_outcome}"
            )
        results.append(
            {
                "check_id": check["check_id"],
                "outcome": outcome,
                "pass_count": choices.count("pass"),
                "issue_count": choices.count("issue"),
                "cannot_tell_count": choices.count("cannot_tell"),
                "private_notes_present": private_notes_present,
            }
        )
    return results


def _review_summary(
    tutorial: Mapping[str, Any],
    quiz: Mapping[str, Any],
    checks: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    item_count = sum(
        int(row["pass_count"]) + int(row["issue_count"]) + int(row["cannot_tell_count"])
        for row in checks
    )
    return {
        "tutorial_completed": tutorial["completed"],
        "quiz_answered_count": quiz["answered_count"],
        "quiz_score": quiz["score"],
        "quiz_passed": quiz["passed"],
        "acceptance_item_count": item_count,
        "reviewed_acceptance_item_count": item_count,
        "acceptance_check_count": len(checks),
        "reviewed_acceptance_check_count": len(checks),
    }


def _expected_check_outcome(choices: Sequence[str]) -> str:
    if "issue" in choices:
        return "needs_changes"
    if "cannot_tell" in choices:
        return "incomplete"
    return "passed"


def _immutable_review_document(value: Mapping[str, Any]) -> dict[str, Any]:
    document = deepcopy(value)
    document["status"] = "unreviewed"
    tutorial = document.get("tutorial")
    if isinstance(tutorial, dict):
        tutorial["viewed_slide_ids"] = []
        tutorial["completed"] = False
    quiz = document.get("quiz")
    if isinstance(quiz, dict):
        quiz.update(
            {
                "answered_count": 0,
                "score": 0,
                "passed": False,
                "completed": False,
            }
        )
        questions = quiz.get("questions")
        if isinstance(questions, list):
            for question in questions:
                if isinstance(question, dict):
                    question["answer"] = None
                    question["correct"] = None
    checks = document.get("acceptance_checks")
    for check in checks if isinstance(checks, list) else []:
        if not isinstance(check, dict):
            continue
        check["outcome"] = None
        check["notes"] = ""
        items = check.get("items")
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict):
                item["choice"] = None
                item["notes"] = ""
    summary = document.get("summary")
    if isinstance(summary, dict):
        summary.update(
            {
                "tutorial_completed": False,
                "quiz_answered_count": 0,
                "quiz_score": 0,
                "quiz_passed": False,
                "reviewed_acceptance_item_count": 0,
                "reviewed_acceptance_check_count": 0,
            }
        )
    return document


def _redacted_review_document(value: Mapping[str, Any]) -> dict[str, Any]:
    """Keep resolved choices while removing private free-text evidence."""

    document = deepcopy(value)
    checks = document.get("acceptance_checks")
    for check in checks if isinstance(checks, list) else []:
        if not isinstance(check, dict):
            continue
        check["notes"] = ""
        items = check.get("items")
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict):
                item["notes"] = ""
    return document


def _browser_json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, Mapping) or isinstance(right, Mapping):
        return (
            isinstance(left, Mapping)
            and isinstance(right, Mapping)
            and set(left) == set(right)
            and all(_browser_json_equal(left[key], right[key]) for key in left)
        )
    if isinstance(left, list) or isinstance(right, list):
        return (
            isinstance(left, list)
            and isinstance(right, list)
            and len(left) == len(right)
            and all(_browser_json_equal(a, b) for a, b in zip(left, right))
        )
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is bool and type(right) is bool and left is right
    if isinstance(left, (int, float)) or isinstance(right, (int, float)):
        if (
            isinstance(left, bool)
            or isinstance(right, bool)
            or not isinstance(left, (int, float))
            or not isinstance(right, (int, float))
            or not math.isfinite(float(left))
            or not math.isfinite(float(right))
        ):
            return False
        return float(left) == float(right)
    return type(left) is type(right) and left == right


def _safe_archive_path(value: str) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and all(
        part not in {"", ".", ".."} for part in path.parts
    )


def _canonical_pack_archive_path(kind: str, value: str) -> bool:
    token = r"[^\W_]+(?:-[^\W_]+)*"
    if kind == "selected_midi":
        return (
            re.fullmatch(rf"MIDI/[0-9]{{2}}-{token}-(?:main|optional)\.mid", value)
            is not None
        )
    if kind == "source_audio":
        return (
            re.fullmatch(rf"STEMS/[0-9]{{2}}-{token}-source\.[A-Za-z0-9]+", value)
            is not None
        )
    if kind == "arrangement_proxy":
        return value in {
            "MIDI/selected-arrangement-proxy.mid",
            "PREVIEW/selected-arrangement-proxy.wav",
        }
    return False


def _contains_private_path(value: Any, *, key: str = "") -> bool:
    if isinstance(value, Mapping):
        return any(
            _contains_private_path(item, key=str(name)) for name, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_private_path(item, key=key) for item in value)
    if not isinstance(value, str) or key == "archive_path":
        return False
    lowered = value.lower()
    return (
        value.startswith("/")
        or lowered.startswith("file://")
        or (len(value) >= 3 and value[0].isalpha() and value[1:3] in {":/", ":\\"})
        or "/users/" in lowered
        or "/home/" in lowered
    )


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_pack_item_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("pack-item-")
        and _is_sha256(value[len("pack-item-") :])
    )


def _file_record(path: Path) -> dict[str, Any]:
    return {
        "name": path.name,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _document_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > _MAX_REVIEW_ARTIFACT_BYTES:
            raise ValueError(f"JSON document is too large: {path}")
    except OSError as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return value


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        _write_json(temporary, value)
        temporary.chmod(0o600)
        temporary.replace(path)
    except Exception:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def _require_regular_file(path: Path, label: str) -> None:
    try:
        mode = path.stat().st_mode
    except OSError as exc:
        raise ValueError(f"{label} does not exist: {path}") from exc
    if not stat.S_ISREG(mode) or path.is_symlink():
        raise ValueError(f"{label} must be a regular file: {path}")


def _zero_effects() -> dict[str, bool]:
    return {
        "tutorial_changed_project": False,
        "quiz_selected_candidate": False,
        "feedback_recorded": False,
        "musical_selection_changed": False,
        "pack_basket_changed": False,
        "midi_mutated": False,
        "candidate_promoted": False,
        "default_changed": False,
        "data_submitted": False,
        "phase6_started_automatically": False,
    }


def _html(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _review_html(seed: Mapping[str, Any]) -> str:
    payload = json.dumps(seed, sort_keys=True).replace("</", "<\\/")
    quiz_key = {
        row["question_id"]: {
            "correct": row["correct"],
            "explanation": row["explanation"],
        }
        for row in _QUIZ_BANK
    }
    key_payload = json.dumps(quiz_key, sort_keys=True).replace("</", "<\\/")
    item_rows = "".join(
        f"<li><code>{_html(row['archive_path'])}</code> · {_html(row['kind'])} · "
        f"{_html(row['sha256'][:16])}…</li>"
        for row in seed["included_items"]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sunofriend guided Phase 5 acceptance</title>
<style>
:root{{--bg:#081018;--panel:#111d28;--line:#294056;--text:#edf5fb;--muted:#a9bdca;--gold:#ffd45c;--green:#69d69b;--red:#ff8b8b;--blue:#8fd3ff}}
*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(135deg,#081018,#0d1721 55%,#102239);color:var(--text);font:17px/1.5 system-ui,-apple-system,sans-serif}}main{{max-width:960px;margin:auto;padding:2rem 1rem 5rem}}h1{{font-size:clamp(2rem,5vw,3.7rem);line-height:1.05;margin:.25rem 0}}h2{{margin-top:0}}button{{font:inherit;border:1px solid #47708f;background:#183149;color:var(--text);border-radius:9px;padding:.7rem 1rem;cursor:pointer}}button.primary{{background:#2d6087}}button:disabled{{opacity:.45;cursor:not-allowed}}code{{color:var(--blue)}}.eyebrow{{color:var(--gold);text-transform:uppercase;letter-spacing:.12em;font-weight:750}}.muted{{color:var(--muted)}}.panel{{background:rgba(17,29,40,.96);border:1px solid var(--line);border-radius:18px;padding:clamp(1rem,4vw,2rem);box-shadow:0 18px 55px #0007}}.stepper{{display:grid;grid-template-columns:repeat(5,1fr);gap:.35rem;margin:1.5rem 0}}.step{{padding:.55rem .3rem;border-bottom:4px solid #314555;color:var(--muted);text-align:center;font-size:.82rem}}.step.active{{border-color:var(--gold);color:var(--text)}}.step.done{{border-color:var(--green);color:var(--green)}}.slide{{min-height:320px;display:grid;align-content:center}}.slide-count{{color:var(--gold)}}.takeaway{{border-left:4px solid var(--green);padding:.8rem 1rem;background:#10291f}}.actions{{display:flex;gap:.7rem;flex-wrap:wrap;margin-top:1.2rem}}.flow{{display:flex;gap:.4rem;flex-wrap:wrap;margin:1rem 0}}.flow span{{background:#152b3d;border:1px solid #35516a;border-radius:999px;padding:.4rem .7rem}}.quiz-option,.answer-row{{display:block;border:1px solid var(--line);border-radius:10px;padding:.7rem;margin:.55rem 0;background:#0d1721}}.quiz-option input,.answer-row input{{margin-right:.6rem}}.feedback{{padding:.8rem 1rem;border-radius:10px;margin:1rem 0}}.correct{{background:#123426;border-left:4px solid var(--green)}}.wrong{{background:#3a2020;border-left:4px solid var(--red)}}.score{{font-size:1.35rem;color:var(--gold)}}.evidence{{max-height:240px;overflow:auto;background:#081018;border-radius:10px;padding:.7rem 1rem}}fieldset{{border:1px solid var(--line);border-radius:12px;margin:1rem 0;padding:1rem}}legend{{font-weight:750;padding:0 .3rem}}textarea{{width:100%;min-height:70px;background:#081018;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:.6rem}}.status{{padding:.8rem 1rem;border-radius:10px;background:#10291f}}.warning{{padding:.8rem 1rem;border-left:4px solid var(--gold);background:#2b2514}}[hidden]{{display:none!important}}@media(max-width:650px){{.stepper{{grid-template-columns:1fr}}.step{{text-align:left}}}}
</style></head><body><main>
<p class="eyebrow">Local · private · zero effect</p><h1>Understand Sunofriend, then test it</h1>
<p class="muted">One guided presentation, a 10-question one-at-a-time quiz, then two short human checks tied to one exact verified GarageBand pack.</p>
<div class="stepper" aria-label="Review progress"><div class="step active" data-step="tutorial">1 Learn</div><div class="step" data-step="quiz">2 Quiz</div><div class="step" data-step="garageband">3 GarageBand</div><div class="step" data-step="usability">4 Usability</div><div class="step" data-step="export">5 Export</div></div>
<section class="panel" id="tutorial"><p class="slide-count" id="slide-count"></p><div class="slide"><h2 id="slide-title"></h2><p id="slide-body"></p><p class="takeaway" id="slide-takeaway"></p><div class="flow" id="flow" hidden><span>Stems + chords</span><span>Several MIDI methods</span><span>Listen + choose</span><span>Arrangement</span><span>Exact pack</span><span>GarageBand patches</span></div></div><div class="actions"><button id="slide-back">Back</button><button class="primary" id="slide-next">Next</button></div></section>
<section class="panel" id="quiz" hidden><p class="eyebrow">Understanding check</p><h2>Question <span id="quiz-number"></span> of 10</h2><p id="quiz-prompt"></p><div id="quiz-options"></div><div id="quiz-feedback" hidden></div><div class="actions"><button class="primary" id="check-answer">Check answer</button><button id="quiz-next" hidden>Next question</button></div><div id="quiz-finish" hidden><p class="score" id="quiz-score"></p><p id="quiz-result"></p><div class="actions"><button id="retry-quiz">Retry all 10 questions</button><button class="primary" id="start-garageband">Continue to GarageBand check</button></div></div></section>
<section class="panel" id="acceptance" hidden><p class="eyebrow" id="check-eyebrow"></p><h2 id="check-title"></h2><p id="check-purpose"></p><p class="warning" id="check-warning"></p><div id="check-items"></div><fieldset><legend>Explicit check outcome</legend><label class="answer-row"><input type="radio" name="check-outcome" value="passed">Passed</label><label class="answer-row"><input type="radio" name="check-outcome" value="needs_changes">Needs changes</label><label class="answer-row"><input type="radio" name="check-outcome" value="incomplete">Incomplete / cannot tell</label></fieldset><label>Private notes for this check<textarea id="check-notes" placeholder="Optional; retained only in the private reviewed export"></textarea></label><div class="actions"><button class="primary" id="save-check">Review this check and continue</button></div></section>
<section class="panel" id="export" hidden><p class="eyebrow">Review ready</p><h2>Export the evidence</h2><p id="final-summary" class="status"></p><p>The reviewed JSON is private and can contain your notes. Resolve it against the exact ZIP with:</p><pre><code>sunofriend garageband-pack-resolve REVIEWED.json sunofriend-garageband-pack.zip --out phase5-acceptance-result.json</code></pre><div class="actions"><button class="primary" id="export-json">Export reviewed JSON</button></div><details><summary>Automatically verified pack evidence</summary><p>ZIP SHA-256 <code>{_html(seed["pack"]["sha256"])}</code></p><ul class="evidence">{item_rows}</ul></details><p class="muted">This page records no Workbench event and has no upload or submission action.</p></section>
<script>
const review={payload};const quizKey={key_payload};let slideIndex=0,quizIndex=0,checkIndex=0;
const byId=id=>document.getElementById(id);const esc=value=>String(value).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
function showStage(name){{for(const id of ['tutorial','quiz','acceptance','export'])byId(id).hidden=id!==(name==='garageband'||name==='usability'?'acceptance':name);document.querySelectorAll('.step').forEach(step=>{{const order=['tutorial','quiz','garageband','usability','export'],current=order.indexOf(name),index=order.indexOf(step.dataset.step);step.classList.toggle('active',index===current);step.classList.toggle('done',index<current)}});scrollTo({{top:0,behavior:'smooth'}})}}
function renderSlide(){{const slide=review.tutorial.slides[slideIndex];if(!review.tutorial.viewed_slide_ids.includes(slide.slide_id))review.tutorial.viewed_slide_ids.push(slide.slide_id);byId('slide-count').textContent=`Slide ${{slideIndex+1}} of ${{review.tutorial.slide_count}}`;byId('slide-title').textContent=slide.title;byId('slide-body').textContent=slide.body;byId('slide-takeaway').innerHTML='<b>Remember:</b> '+esc(slide.takeaway);byId('flow').hidden=slide.slide_id!=='workflow';byId('slide-back').disabled=slideIndex===0;byId('slide-next').textContent=slideIndex===review.tutorial.slide_count-1?'Start the quiz':'Next'}}
byId('slide-back').onclick=()=>{{slideIndex--;renderSlide()}};byId('slide-next').onclick=()=>{{if(slideIndex<review.tutorial.slide_count-1){{slideIndex++;renderSlide();return}}review.tutorial.completed=true;showStage('quiz');renderQuiz()}};
function renderQuiz(){{const question=review.quiz.questions[quizIndex];byId('quiz-number').textContent=quizIndex+1;byId('quiz-prompt').textContent=question.prompt;byId('quiz-options').innerHTML=question.options.map(option=>`<label class="quiz-option"><input type="radio" name="quiz-answer" value="${{esc(option.option_id)}}" ${{question.answer===option.option_id?'checked':''}} ${{question.answer?'disabled':''}}>${{esc(option.label)}}</label>`).join('');const feedback=byId('quiz-feedback');if(question.answer){{const key=quizKey[question.question_id];feedback.hidden=false;feedback.className='feedback '+(question.correct?'correct':'wrong');feedback.innerHTML=`<b>${{question.correct?'Correct':'Not quite'}}.</b> ${{esc(key.explanation)}}`;byId('check-answer').hidden=true;byId('quiz-next').hidden=false;byId('quiz-next').textContent=quizIndex===review.quiz.question_count-1?'See my score':'Next question'}}else{{feedback.hidden=true;byId('check-answer').hidden=false;byId('quiz-next').hidden=true}}byId('quiz-finish').hidden=true}}
byId('check-answer').onclick=()=>{{const chosen=document.querySelector('input[name="quiz-answer"]:checked');if(!chosen){{alert('Choose one answer first.');return}}const question=review.quiz.questions[quizIndex],key=quizKey[question.question_id];question.answer=chosen.value;question.correct=chosen.value===key.correct;renderQuiz()}};
byId('quiz-next').onclick=()=>{{if(quizIndex<review.quiz.question_count-1){{quizIndex++;renderQuiz();return}}finishQuiz()}};
function finishQuiz(){{review.quiz.answered_count=review.quiz.questions.filter(q=>q.answer).length;review.quiz.score=review.quiz.questions.filter(q=>q.correct).length;review.quiz.completed=review.quiz.answered_count===review.quiz.question_count;review.quiz.passed=review.quiz.completed&&review.quiz.score>=review.quiz.pass_score;byId('quiz-feedback').hidden=true;byId('check-answer').hidden=true;byId('quiz-next').hidden=true;byId('quiz-finish').hidden=false;byId('quiz-score').textContent=`Score: ${{review.quiz.score}} / ${{review.quiz.question_count}}`;byId('quiz-result').textContent=review.quiz.passed?'Understanding check passed. You can continue to the two human checks.':`Review the explanations and retry; at least ${{review.quiz.pass_score}}/10 is required before acceptance.`;byId('start-garageband').disabled=!review.quiz.passed}}
byId('retry-quiz').onclick=()=>{{review.quiz.questions.forEach(q=>{{q.answer=null;q.correct=null}});review.quiz.answered_count=0;review.quiz.score=0;review.quiz.completed=false;review.quiz.passed=false;quizIndex=0;renderQuiz()}};byId('start-garageband').onclick=()=>{{if(!review.quiz.passed)return;checkIndex=0;showStage('garageband');renderCheck()}};
function renderCheck(){{const check=review.acceptance_checks[checkIndex],isGarage=check.check_id==='garageband-pack';byId('check-eyebrow').textContent=isGarage?'Acceptance check 1 of 2':'Acceptance check 2 of 2';byId('check-title').textContent=check.title;byId('check-purpose').textContent=check.purpose;byId('check-warning').textContent=isGarage?`Expected setup: ${{review.setup.bpm}} BPM · ${{review.setup.key||'key not inferred'}} · downbeat ${{review.setup.downbeat??'not confirmed'}}. Integrity is verified automatically, but only you can verify GarageBand playback.`:'Judge whether the workflow was understandable and usable, not whether every transcription was musically perfect.';byId('check-items').innerHTML=check.items.map((item,index)=>`<fieldset data-check-item="${{index}}"><legend>${{index+1}}. ${{esc(item.prompt)}}</legend>${{[['pass','Pass'],['issue','Issue'],['cannot_tell','Cannot tell / not tested']].map(([value,label])=>`<label class="answer-row"><input type="radio" name="item-${{index}}" value="${{value}}" ${{item.choice===value?'checked':''}}>${{label}}</label>`).join('')}}<label>Private note<textarea data-item-note="${{index}}">${{esc(item.notes||'')}}</textarea></label></fieldset>`).join('');document.querySelectorAll('input[name="check-outcome"]').forEach(input=>input.checked=input.value===check.outcome);byId('check-notes').value=check.notes||'';byId('save-check').textContent=isGarage?'Review GarageBand check and continue':'Review usability check and finish'}}
function readCheck(){{const check=review.acceptance_checks[checkIndex];for(let index=0;index<check.items.length;index++){{const choice=document.querySelector(`input[name="item-${{index}}"]:checked`);if(!choice)throw new Error(`Answer item ${{index+1}} before continuing.`);check.items[index].choice=choice.value;check.items[index].notes=document.querySelector(`[data-item-note="${{index}}"]`).value}}const outcome=document.querySelector('input[name="check-outcome"]:checked');if(!outcome)throw new Error('Choose an explicit outcome for this check.');check.outcome=outcome.value;check.notes=byId('check-notes').value;const choices=check.items.map(item=>item.choice),expected=choices.includes('issue')?'needs_changes':choices.includes('cannot_tell')?'incomplete':'passed';if(check.outcome!==expected)throw new Error(`These answers require the outcome “${{expected.replace('_',' ')}}”. Nothing was changed; select that outcome or revise the item answers.`)}}
byId('save-check').onclick=()=>{{try{{readCheck()}}catch(error){{alert(error.message);return}}if(checkIndex===0){{checkIndex=1;showStage('usability');renderCheck();return}}finishReview()}};
function finishReview(){{review.status='reviewed';const items=review.acceptance_checks.flatMap(check=>check.items);review.summary={{tutorial_completed:review.tutorial.completed,quiz_answered_count:review.quiz.answered_count,quiz_score:review.quiz.score,quiz_passed:review.quiz.passed,acceptance_item_count:items.length,reviewed_acceptance_item_count:items.filter(item=>item.choice).length,acceptance_check_count:review.acceptance_checks.length,reviewed_acceptance_check_count:review.acceptance_checks.filter(check=>check.outcome).length}};const passed=review.acceptance_checks.every(check=>check.outcome==='passed');byId('final-summary').textContent=passed?`Tutorial complete, quiz ${{review.quiz.score}}/10, and both checks passed. Resolve the export against the exact ZIP to verify the Phase 6 Clip entry gate.`:`Tutorial complete and quiz ${{review.quiz.score}}/10. The human checks recorded issues or incomplete evidence, so the gate remains open.`;showStage('export')}}
byId('export-json').onclick=()=>{{const blob=new Blob([JSON.stringify(review,null,2)+'\\n'],{{type:'application/json'}}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='garageband_pack_acceptance.reviewed.json';document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)}};
renderSlide();
</script></main></body></html>"""


__all__ = [
    "GARAGEBAND_PACK_ACCEPTANCE_RESULT_SCHEMA",
    "GARAGEBAND_PACK_ACCEPTANCE_SCHEMA",
    "create_garageband_pack_acceptance_review",
    "resolve_garageband_pack_acceptance_review",
    "verify_garageband_pack_acceptance_artifacts",
    "verify_garageband_pack_archive",
]
