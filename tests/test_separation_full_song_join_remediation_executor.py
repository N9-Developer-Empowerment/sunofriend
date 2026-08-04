from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import runpy
import shlex
import stat
import subprocess
import sys
from typing import Any, Mapping
import wave

import numpy as np
import pytest
import soundfile

from sunofriend._separation_authorised_excerpt import _document_sha256, _sha256
from sunofriend._separation_checkpoint_canonical import canonical_json_bytes
from sunofriend._separation_full_song_join_remediation_executor import (
    CANDIDATE_REPORT_NAME,
    REPORT_NAME,
    SCHEMA,
    _apply_equal_power_patch,
    _execute_private_separation_full_song_join_remediation,
    _state_sha256,
)
from sunofriend._separation_full_song_join_remediation_plan import (
    POLICY_ID,
    REPORT_NAME as PLAN_NAME,
    SCHEMA as PLAN_SCHEMA,
    STATUS as PLAN_STATUS,
    _FALSE_EFFECTS as PLAN_FALSE_EFFECTS,
    _FALSE_PERMISSIONS as PLAN_FALSE_PERMISSIONS,
)
from sunofriend._separation_full_song_join_remediation_review import (
    ANSWER_KEY_NAME,
    HTML_NAME,
    REPORT_NAME as REVIEW_REPORT_NAME,
    _prepare_private_join_remediation_review,
    _review_instructions,
)
from sunofriend._separation_full_song_join_remediation_review_result import (
    _PrivateJsonSnapshotError,
    _load_private_json_snapshot,
    _resolve_private_join_remediation_review,
    _status_private_join_remediation_review,
    _verify_blind_audio_contract,
    _write_json_exclusive,
)
from sunofriend._separation_full_song_plan import (
    REPORT_NAME as SOURCE_PLAN_NAME,
    _prepare_private_separation_full_song_plan,
)
from sunofriend._separation_full_song_stitch import (
    REPORT_NAME as STITCH_NAME,
    SCHEMA as STITCH_SCHEMA,
    STATUS as STITCH_STATUS,
    _FALSE_PERMISSIONS as STITCH_FALSE_PERMISSIONS,
)
from sunofriend._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)


SAMPLE_RATE = 44_100
FRAMES = 20 * SAMPLE_RATE


def test_join_remediation_executor_resumes_and_preserves_raw_control(
    tmp_path: Path,
) -> None:
    remediation, package, source_plan = _inputs(tmp_path)
    runtime = _runtime_arguments(tmp_path)
    output = tmp_path / "execution"
    calls: list[int] = []

    first = _execute_private_separation_full_song_join_remediation(
        remediation,
        package_dir=package,
        source_plan_path=source_plan,
        out_dir=output,
        **runtime,
        maximum_windows=1,
        attempt_runner=_fake_runner(calls),
    )

    assert first["schema"] == SCHEMA
    assert first["summary"]["all_worker_runs_complete"] is True
    assert first["summary"]["candidate_audio_complete"] is True
    assert calls == [661_500]
    candidate = json.loads((output / CANDIDATE_REPORT_NAME).read_text())
    assert candidate["summary"]["patched_boundary_role_pair_count"] == 1
    assert candidate["artifacts"]["vocals"]["outside_patch_pcm24_samples_exact"] is True
    assert candidate["artifacts"]["instrumental"]["patch_count"] == 0
    assert candidate["readiness"]["candidate_review_complete"] is False
    assert all(value is False for value in candidate["permissions"].values())
    raw_vocal = package / "STEMS/vocals.wav"
    assert _sha256(raw_vocal) == candidate["bindings"]["raw_vocals_audio_sha256"]
    assert stat.S_IMODE((output / REPORT_NAME).stat().st_mode) == 0o600

    review_root = tmp_path / "review"
    review = _prepare_private_join_remediation_review(
        output,
        package_dir=package,
        out_dir=review_root,
    )
    assert review["expected_counts"] == {
        "boundary_role_pairs": 1,
        "patch_edge_pairs": 2,
        "complete_song_pairs": 3,
        "total_units": 6,
    }
    seed = json.loads((review_root / REVIEW_REPORT_NAME).read_text())
    answer = json.loads((review_root / ANSWER_KEY_NAME).read_text())
    page = (review_root / HTML_NAME).read_text()
    assert seed["bindings"]["answer_key_sha256"] == _sha256(
        review_root / ANSWER_KEY_NAME
    )
    assert answer["status"] == "sealed_do_not_open_before_review"
    assert '"assignment"' not in page
    assert "Export reviewed JSON" in page
    assert all(unit["choice"] is None for unit in seed["units"])
    assert all(not unit["heard"]["A"] for unit in seed["units"])
    assert seed["instructions"] == _review_instructions(1)
    assert _review_instructions(4)[1] == (
        "Complete the four boundary comparisons before judging patch edges."
    )

    repeated = _execute_private_separation_full_song_join_remediation(
        remediation,
        package_dir=package,
        source_plan_path=source_plan,
        out_dir=output,
        **runtime,
        maximum_windows=None,
        attempt_runner=_fake_runner(calls),
    )
    assert repeated["windows_executed_this_invocation"] == 0
    assert calls == [661_500]


def test_join_remediation_executor_preserves_failed_attempt(tmp_path: Path) -> None:
    remediation, package, source_plan = _inputs(tmp_path)
    runtime = _runtime_arguments(tmp_path)
    output = tmp_path / "execution"

    def fail(**kwargs: Any) -> Mapping[str, Any]:
        Path(kwargs["attempt_directory"]).mkdir(mode=0o700)
        raise RuntimeError("substituted interruption")

    with pytest.raises(RuntimeError, match="substituted interruption"):
        _execute_private_separation_full_song_join_remediation(
            remediation,
            package_dir=package,
            source_plan_path=source_plan,
            out_dir=output,
            **runtime,
            attempt_runner=fail,
        )
    state = json.loads((output / REPORT_NAME).read_text())
    assert state["windows"][0]["attempts"][0]["status"] == "preserved_incomplete"


def test_equal_power_patch_keeps_exact_outer_samples() -> None:
    destination = np.full((12, 2), 0.25, dtype=np.float32)
    replacement = np.full((8, 2), 0.75, dtype=np.float32)
    before = destination.copy()

    changed = _apply_equal_power_patch(
        destination,
        replacement,
        start=2,
        end=10,
        blend_frames=2,
        np=np,
    )

    assert changed > 0
    np.testing.assert_array_equal(destination[:2], before[:2])
    np.testing.assert_array_equal(destination[10:], before[10:])
    np.testing.assert_array_equal(destination[2], before[2])
    np.testing.assert_array_equal(destination[9], before[9])
    np.testing.assert_array_equal(destination[4:8], replacement[2:6])


def test_join_remediation_review_status_keeps_key_closed_then_resolves(
    tmp_path: Path,
) -> None:
    execution, package, review_root, reviewed_path = _completed_review(tmp_path)
    key_path = review_root / ANSWER_KEY_NAME
    key_bytes = key_path.read_bytes()
    key_path.write_text("deliberately unreadable during status\n", encoding="utf-8")

    status = _status_private_join_remediation_review(
        reviewed_path,
        review_package_dir=review_root,
        execution_dir=execution,
        stitch_package_dir=package,
    )

    assert status["status"] == "complete_review_verified_key_unopened"
    assert status["answer_key_opened"] is False
    assert status["identity_mapping_revealed"] is False
    assert status["reviewed_units"] == 6
    assert status["audio_references_verified"] == 12
    assert status["review_export_sha256"] == _sha256(reviewed_path)
    assert status["review_seed_sha256"] == _sha256(review_root / REVIEW_REPORT_NAME)
    assert status["document_sha256"] == _document_sha256(status)
    assert (
        status["verification_claims"][
            "review_seed_and_export_bounded_single_read_snapshots"
        ]
        is True
    )
    assert "bounded_single_read_json_snapshots" not in status["verification_claims"]
    assert (
        status["verification_claims"][
            "answer_key_bounded_single_read_snapshot_verified"
        ]
        is False
    )
    assert (
        status["verification_limitations"][
            "execution_candidate_and_stitch_json_snapshot_held"
        ]
        is False
    )
    assert (
        status["verification_limitations"][
            "wav_descriptors_snapshot_held_across_verification"
        ]
        is False
    )
    assert (
        status["verification_limitations"][
            "non_snapshot_private_inputs_assumed_quiescent"
        ]
        is True
    )
    assert all(value is False for value in status["effects"].values())

    key_path.write_bytes(key_bytes)
    key_path.chmod(0o600)
    answer = json.loads(key_bytes)
    result_path = tmp_path / "resolved-review.json"
    result = _resolve_private_join_remediation_review(
        reviewed_path,
        review_package_dir=review_root,
        execution_dir=execution,
        stitch_package_dir=package,
        out=result_path,
    )

    choices = json.loads(reviewed_path.read_text())["units"]
    expected = []
    for unit, answer_unit in zip(choices, answer["units"]):
        choice = unit["choice"]
        expected.append(
            f"{answer_unit['assignment'][choice]}_preferred"
            if choice in {"A", "B"}
            else choice
        )
    assert result["status"] == "complete_review_no_activation"
    assert [unit["resolved_choice"] for unit in result["units"]] == expected
    assert result["readiness_evidence"]["original_audible_joins_resolved"] is False
    assert result["readiness_evidence"]["publication_ready"] is False
    assert all(value is False for value in result["permissions"].values())
    assert all(value is False for value in result["effects"].values())
    assert (
        result["verification_claims"][
            "result_temp_fsynced_before_no_overwrite_publication"
        ]
        is True
    )
    assert (
        result["verification_claims"]["result_published_by_no_overwrite_hard_link"]
        is True
    )
    assert (
        result["verification_claims"][
            "answer_key_bounded_single_read_snapshot_verified"
        ]
        is True
    )
    assert (
        result["verification_limitations"][
            "execution_candidate_and_stitch_json_snapshot_held"
        ]
        is False
    )
    assert (
        result["verification_limitations"][
            "wav_descriptors_snapshot_held_across_verification"
        ]
        is False
    )
    stored = json.loads(result_path.read_text())
    assert stored["document_sha256"] == _document_sha256(stored)
    assert stat.S_IMODE(result_path.stat().st_mode) == 0o600
    stored_bytes = result_path.read_bytes()
    with pytest.raises(FileExistsError):
        _resolve_private_join_remediation_review(
            reviewed_path,
            review_package_dir=review_root,
            execution_dir=execution,
            stitch_package_dir=package,
            out=result_path,
        )
    assert result_path.read_bytes() == stored_bytes


def test_join_remediation_review_status_rejects_incomplete_or_changed_export(
    tmp_path: Path,
) -> None:
    execution, package, review_root, reviewed_path = _completed_review(tmp_path)
    reviewed = json.loads(reviewed_path.read_text())
    reviewed["units"][0]["title"] = "changed title"
    changed = tmp_path / "changed-review.json"
    _write_private_json(changed, reviewed)

    with pytest.raises(ValueError, match="changed immutable evidence"):
        _status_private_join_remediation_review(
            changed,
            review_package_dir=review_root,
            execution_dir=execution,
            stitch_package_dir=package,
        )

    reviewed = json.loads(reviewed_path.read_text())
    reviewed["units"][0]["heard"]["A"] = False
    incomplete = tmp_path / "incomplete-review.json"
    _write_private_json(incomplete, reviewed)
    with pytest.raises(ValueError, match="unit is incomplete"):
        _status_private_join_remediation_review(
            incomplete,
            review_package_dir=review_root,
            execution_dir=execution,
            stitch_package_dir=package,
        )


def test_join_remediation_review_resolver_rejects_changed_key(
    tmp_path: Path,
) -> None:
    execution, package, review_root, reviewed_path = _completed_review(tmp_path)
    key_path = review_root / ANSWER_KEY_NAME
    key_path.write_text("changed\n", encoding="utf-8")

    with pytest.raises(ValueError, match="answer key differs"):
        _resolve_private_join_remediation_review(
            reviewed_path,
            review_package_dir=review_root,
            execution_dir=execution,
            stitch_package_dir=package,
            out=tmp_path / "result.json",
        )


@pytest.mark.parametrize("rewrite", ("question", "kind", "window"))
def test_join_remediation_review_rejects_coherently_rewritten_public_semantics(
    tmp_path: Path,
    rewrite: str,
) -> None:
    execution, package, review_root, reviewed_path = _completed_review(tmp_path)
    seed_path = review_root / REVIEW_REPORT_NAME
    seed = json.loads(seed_path.read_text())
    reviewed = json.loads(reviewed_path.read_text())
    if rewrite == "question":
        seed["question"] = "A different but self-consistent review question"
        reviewed["question"] = seed["question"]
    elif rewrite == "kind":
        seed["units"][0]["kind"] = "patch_edge_pair"
        reviewed["units"][0]["kind"] = "patch_edge_pair"
        seed["expected_counts"]["boundary_role_pairs"] = 0
        seed["expected_counts"]["patch_edge_pairs"] = 3
        reviewed["expected_counts"] = dict(seed["expected_counts"])
    else:
        for document in (seed, reviewed):
            window = document["units"][0]["source_window"]
            window["start_frame"] += 1
            window["start_seconds"] = window["start_frame"] / SAMPLE_RATE
    seed["document_sha256"] = _document_sha256(seed)
    reviewed["document_sha256"] = seed["document_sha256"]
    _write_private_json(seed_path, seed)
    reviewed_path.write_text(json.dumps(reviewed), encoding="utf-8")

    with pytest.raises(ValueError, match="public semantics differ"):
        _status_private_join_remediation_review(
            reviewed_path,
            review_package_dir=review_root,
            execution_dir=execution,
            stitch_package_dir=package,
        )


@pytest.mark.parametrize(
    ("tamper", "message"),
    (
        ("short_assignment", "short answer binding differs"),
        ("short_level", "short answer binding differs"),
        ("complete_assignment", "complete-song answer binding differs"),
    ),
)
def test_join_remediation_review_resolver_binds_revealed_key_to_audio(
    tmp_path: Path,
    tamper: str,
    message: str,
) -> None:
    execution, package, review_root, reviewed_path = _completed_review(tmp_path)
    answer_path = review_root / ANSWER_KEY_NAME
    answer = json.loads(answer_path.read_text())
    if tamper == "short_assignment":
        assignment = answer["units"][0]["assignment"]
        assignment["A"], assignment["B"] = assignment["B"], assignment["A"]
    elif tamper == "short_level":
        answer["units"][0]["raw_rms"] = round(
            answer["units"][0]["raw_rms"] * 1.01,
            12,
        )
    else:
        assignment = answer["units"][-1]["assignment"]
        assignment["A"], assignment["B"] = assignment["B"], assignment["A"]
    _repin_answer_key_and_public_review(
        answer,
        answer_path=answer_path,
        seed_path=review_root / REVIEW_REPORT_NAME,
        reviewed_path=reviewed_path,
    )

    with pytest.raises(ValueError, match=message):
        _resolve_private_join_remediation_review(
            reviewed_path,
            review_package_dir=review_root,
            execution_dir=execution,
            stitch_package_dir=package,
            out=tmp_path / "resolved.json",
        )


def test_join_remediation_review_status_rejects_oversized_browser_export(
    tmp_path: Path,
) -> None:
    execution, package, review_root, reviewed_path = _completed_review(tmp_path)
    reviewed_path.write_bytes(
        reviewed_path.read_bytes()
        + b" " * (8 * 1024 * 1024 - reviewed_path.stat().st_size + 1)
    )

    with pytest.raises(ValueError, match="no larger than 8 MiB"):
        _status_private_join_remediation_review(
            reviewed_path,
            review_package_dir=review_root,
            execution_dir=execution,
            stitch_package_dir=package,
        )


def test_private_json_snapshot_requires_owner_only_mode_and_reads_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "private review with spaces.json"
    _write_private_json(path, {"value": 1})
    real_read = os.read
    calls = 0

    def counted_read(descriptor: int, maximum: int) -> bytes:
        nonlocal calls
        calls += 1
        return real_read(descriptor, maximum)

    monkeypatch.setattr(os, "read", counted_read)
    snapshot = _load_private_json_snapshot(path, "private test review")

    assert calls == 1
    assert snapshot["sha256"] == _sha256(path)
    assert snapshot["bytes"] == path.stat().st_size
    path.chmod(0o644)
    with pytest.raises(_PrivateJsonSnapshotError) as caught:
        _load_private_json_snapshot(path, "private test review")
    assert caught.value.chmod_recommended is True


def test_private_json_snapshot_rejects_symbolic_and_hard_links(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.json"
    _write_private_json(source, {"value": 1})
    symbolic = tmp_path / "symbolic.json"
    symbolic.symlink_to(source)
    with pytest.raises(_PrivateJsonSnapshotError, match="regular non-link"):
        _load_private_json_snapshot(symbolic, "private test review")

    hard = tmp_path / "hard.json"
    os.link(source, hard)
    with pytest.raises(_PrivateJsonSnapshotError, match="exactly one filesystem link"):
        _load_private_json_snapshot(source, "private test review")


def test_private_json_snapshot_rejects_short_or_changed_reads_and_closes_fd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "private.json"
    _write_private_json(path, {"value": 1})
    real_read = os.read

    with monkeypatch.context() as patch:
        patch.setattr(os, "read", lambda fd, maximum: real_read(fd, maximum)[:-1])
        with pytest.raises(_PrivateJsonSnapshotError, match="changed while"):
            _load_private_json_snapshot(path, "private test review")

    real_fstat = os.fstat
    fstat_calls = 0

    def changed_fstat(descriptor: int) -> os.stat_result:
        nonlocal fstat_calls
        current = real_fstat(descriptor)
        fstat_calls += 1
        if fstat_calls == 2:
            values = list(current)
            values[6] += 1
            return os.stat_result(values)
        return current

    with monkeypatch.context() as patch:
        patch.setattr(os, "fstat", changed_fstat)
        with pytest.raises(_PrivateJsonSnapshotError, match="changed while"):
            _load_private_json_snapshot(path, "private test review")

    path.write_text("not json", encoding="utf-8")
    path.chmod(0o600)
    real_open = os.open
    descriptors: list[int] = []

    def recorded_open(open_path: os.PathLike[str], flags: int) -> int:
        descriptor = real_open(open_path, flags)
        descriptors.append(descriptor)
        return descriptor

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", recorded_open)
        with pytest.raises(_PrivateJsonSnapshotError, match="differs"):
            _load_private_json_snapshot(path, "private test review")
    assert len(descriptors) == 1
    with pytest.raises(OSError):
        os.fstat(descriptors[0])


@pytest.mark.parametrize("failure", ["write", "fsync"])
def test_exclusive_result_write_removes_its_partial_inode_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    path = tmp_path / f"failed-{failure}.json"
    target = os.write if failure == "write" else os.fsync

    def fail(*_args: object) -> None:
        raise OSError(f"injected {failure} failure")

    monkeypatch.setattr(os, failure, fail)
    with pytest.raises(OSError, match=f"injected {failure} failure"):
        _write_json_exclusive(path, {"value": 1})
    assert not path.exists()
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []

    monkeypatch.setattr(os, failure, target)
    _write_json_exclusive(path, {"value": 2})
    assert json.loads(path.read_text()) == {"value": 2}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []


def test_exclusive_result_is_invisible_until_complete_temp_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "published-result.json"
    real_link = os.link
    observed_publication = False

    def checked_link(
        source: os.PathLike[str],
        destination: os.PathLike[str],
        *,
        follow_symlinks: bool = True,
    ) -> None:
        nonlocal observed_publication
        assert Path(destination) == path
        assert not path.exists()
        assert json.loads(Path(source).read_text()) == {"value": 1}
        assert stat.S_IMODE(Path(source).stat().st_mode) == 0o600
        observed_publication = True
        real_link(source, destination, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(os, "link", checked_link)
    _write_json_exclusive(path, {"value": 1})

    assert observed_publication is True
    assert json.loads(path.read_text()) == {"value": 1}
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []


def test_exclusive_result_write_preserves_interposed_race_winner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "raced-result.json"
    sentinel = b"race winner must remain unchanged\n"
    real_link = os.link
    interposed = False

    def interposed_link(
        source: os.PathLike[str],
        destination: os.PathLike[str],
        *,
        follow_symlinks: bool = True,
    ) -> None:
        nonlocal interposed
        if Path(destination) == path and not interposed:
            interposed = True
            path.write_bytes(sentinel)
            path.chmod(0o600)
        real_link(source, destination, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(os, "link", interposed_link)
    with pytest.raises(FileExistsError):
        _write_json_exclusive(path, {"value": "must not replace sentinel"})
    assert interposed is True
    assert path.read_bytes() == sentinel
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []


def test_join_remediation_review_rejects_pcm24_identical_short_pair(
    tmp_path: Path,
) -> None:
    audio = np.full((SAMPLE_RATE, 2), 0.125, dtype=np.float64)
    raw = tmp_path / "raw.wav"
    candidate = tmp_path / "candidate.wav"
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    for path in (raw, candidate, first, second):
        soundfile.write(path, audio, SAMPLE_RATE, subtype="PCM_24")
    review = {
        "units": [
            {
                "unit_id": "boundary-01-vocals",
                "kind": "boundary_role_pair",
            }
        ]
    }
    reconstructed = {
        "units": [
            {
                "public": {
                    "unit_id": "boundary-01-vocals",
                    "source_window": {
                        "start_frame": 0,
                        "end_frame": SAMPLE_RATE,
                    },
                },
                "raw_path": raw,
                "candidate_path": candidate,
            }
        ]
    }

    with pytest.raises(ValueError, match="PCM24-identical"):
        _verify_blind_audio_contract(
            review,
            reconstructed=reconstructed,
            audio_paths={
                "boundary-01-vocals": {"A": first, "B": second},
            },
        )


def test_join_remediation_review_generator_rejects_duplicate_patch_identity(
    tmp_path: Path,
) -> None:
    remediation, package, source_plan = _inputs(tmp_path)
    execution = tmp_path / "execution"
    _execute_private_separation_full_song_join_remediation(
        remediation,
        package_dir=package,
        source_plan_path=source_plan,
        out_dir=execution,
        **_runtime_arguments(tmp_path),
        maximum_windows=None,
        attempt_runner=_fake_runner([]),
    )
    candidate_path = execution / CANDIDATE_REPORT_NAME
    candidate = json.loads(candidate_path.read_text())
    candidate["patches"].append(dict(candidate["patches"][0]))
    candidate["summary"]["patched_boundary_role_pair_count"] = 2
    candidate["document_sha256"] = _document_sha256(candidate)
    _write_private_json(candidate_path, candidate)
    state_path = execution / REPORT_NAME
    state = json.loads(state_path.read_text())
    state["candidate_report"] = {
        "path": CANDIDATE_REPORT_NAME,
        "sha256": _sha256(candidate_path),
        "document_sha256": candidate["document_sha256"],
        "bytes": candidate_path.stat().st_size,
    }
    state["state_sha256"] = _state_sha256(state)
    _write_private_json(state_path, state)

    with pytest.raises(ValueError, match="patch identity is duplicated"):
        _prepare_private_join_remediation_review(
            execution,
            package_dir=package,
            out_dir=tmp_path / "duplicate-review",
        )


def test_join_remediation_review_cli_exposes_only_summary_and_safe_chmod(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    namespace = runpy.run_path(
        str(
            Path(__file__).parents[1]
            / "scripts/private-separation-full-song-join-remediation-review-result.py"
        )
    )
    summary = namespace["_cli_resolution_summary"](
        {
            "status": "complete_review_no_activation",
            "report": "/private/result.json",
            "reviewed_unit_count": 1,
            "counts_by_kind_and_outcome": {},
            "overall_outcome_counts": {},
            "readiness_evidence": {},
            "verification_claims": {},
            "verification_limitations": {},
            "document_sha256": "0" * 64,
            "units": [{"notes": "PRIVATE NOTE MUST NOT PRINT"}],
        }
    )
    encoded = json.dumps(summary)
    assert "units" not in summary
    assert "PRIVATE NOTE MUST NOT PRINT" not in encoded
    unsafe_path = tmp_path / "review with spaces;$(touch SHOULD_NOT_EXIST).json"
    unsafe_path.write_text("{}")
    unsafe_path.chmod(0o644)
    error = _PrivateJsonSnapshotError(
        "private mode required",
        path=unsafe_path,
        chmod_recommended=True,
    )
    message = namespace["_snapshot_error_message"]("review-tool", error)
    command = message.splitlines()[-1].strip()
    assert command == shlex.join(["chmod", "600", str(unsafe_path)])
    completed = subprocess.run(
        command,
        cwd=tmp_path,
        shell=True,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert stat.S_IMODE(unsafe_path.stat().st_mode) == 0o600
    assert not (tmp_path / "SHOULD_NOT_EXIST").exists()

    main = namespace["main"]
    main.__globals__["_status_private_join_remediation_review"] = lambda *_a, **_k: {
        "status": "complete_review_verified_key_unopened",
        "reviewed_units": 1,
        "counts_by_kind": {},
        "audio_references_verified": 2,
        "effects": {},
        "answer_key_opened": False,
        "identity_mapping_revealed": False,
        "verification_claims": {},
        "verification_limitations": {},
        "document_sha256": "0" * 64,
        "units": [{"notes": "PRIVATE NOTE MUST NOT PRINT"}],
    }
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "review-tool",
            "--status",
            str(tmp_path / "review.json"),
            "--review-package-dir",
            str(tmp_path / "review-package"),
            "--execution-dir",
            str(tmp_path / "execution"),
            "--stitch-package-dir",
            str(tmp_path / "stitch"),
        ],
    )
    assert main() == 0
    captured = capsys.readouterr()
    assert "PRIVATE NOTE MUST NOT PRINT" not in captured.out
    assert '"status": "complete_review_verified_key_unopened"' in captured.out


def _repin_answer_key_and_public_review(
    answer: dict[str, Any],
    *,
    answer_path: Path,
    seed_path: Path,
    reviewed_path: Path,
) -> None:
    answer["document_sha256"] = _document_sha256(answer)
    _write_private_json(answer_path, answer)
    seed = json.loads(seed_path.read_text())
    seed["bindings"]["answer_key_sha256"] = _sha256(answer_path)
    seed["bindings"]["answer_key_document_sha256"] = answer["document_sha256"]
    seed["package_commitment"] = hashlib.sha256(
        (
            f"{seed['bindings']['answer_key_sha256']}:"
            f"{seed['bindings']['answer_key_document_sha256']}:"
            f"{seed['bindings']['audio_manifest_sha256']}"
        ).encode("ascii")
    ).hexdigest()
    seed["document_sha256"] = _document_sha256(seed)
    _write_private_json(seed_path, seed)
    reviewed = json.loads(reviewed_path.read_text())
    reviewed["bindings"] = dict(seed["bindings"])
    reviewed["package_commitment"] = seed["package_commitment"]
    reviewed["document_sha256"] = seed["document_sha256"]
    reviewed_path.write_text(json.dumps(reviewed), encoding="utf-8")


def _completed_review(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    remediation, package, source_plan = _inputs(tmp_path)
    execution = tmp_path / "execution"
    _execute_private_separation_full_song_join_remediation(
        remediation,
        package_dir=package,
        source_plan_path=source_plan,
        out_dir=execution,
        **_runtime_arguments(tmp_path),
        maximum_windows=None,
        attempt_runner=_fake_runner([]),
    )
    review_root = tmp_path / "review"
    _prepare_private_join_remediation_review(
        execution,
        package_dir=package,
        out_dir=review_root,
    )
    reviewed = json.loads((review_root / REVIEW_REPORT_NAME).read_text())
    choices = ("A", "B", "equivalent", "neither", "cannot_tell", "A")
    for unit, choice in zip(reviewed["units"], choices):
        unit["heard"] = {"A": True, "B": True}
        unit["choice"] = choice
        unit["notes"] = f"private note for {unit['unit_id']}"
    reviewed["status"] = "reviewed"
    reviewed["summary"] = {
        "reviewed_units": len(reviewed["units"]),
        "total_units": len(reviewed["units"]),
        "complete": True,
    }
    reviewed_path = tmp_path / "join_remediation_review.reviewed.json"
    _write_private_json(reviewed_path, reviewed)
    return execution, package, review_root, reviewed_path


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    corpus_root = tmp_path / "corpus"
    original = corpus_root / "song" / "ORIGINAL" / "song.wav"
    original.parent.mkdir(parents=True)
    time = np.arange(FRAMES, dtype=np.float64) / SAMPLE_RATE
    mono = (0.12 * np.sin(2 * np.pi * 220 * time)).astype("float32")
    source = np.column_stack((mono, mono))
    soundfile.write(original, source, SAMPLE_RATE, subtype="PCM_24")
    corpus = {
        "schema": "sunofriend.authorised-separation-corpus.v1",
        "artist": {
            "name": "Owner",
            "soundcloud_profile": "https://example.test/owner",
        },
        "permission": {
            "authority": "creator_and_copyright_holder",
            "scope": "test fixture",
            "allowed_use": "download, study, transform and reuse",
            "condition": "credit Owner",
            "recorded_on": "2026-08-04",
        },
        "tracks": [
            {
                "id": "song",
                "title": "Song",
                "directory": "song",
                "evaluation_state": "ready_for_excerpt_selection",
            }
        ],
    }
    corpus_path = corpus_root / "corpus.json"
    corpus_path.write_text(json.dumps(corpus) + "\n", encoding="utf-8")
    source_plan_root = tmp_path / "source-plan"
    _prepare_private_separation_full_song_plan(
        corpus_path,
        "song",
        out_dir=source_plan_root,
    )
    source_plan_path = source_plan_root / SOURCE_PLAN_NAME
    source_plan = json.loads(source_plan_path.read_text())

    package = tmp_path / "stitch"
    source_dir = package / "SOURCE"
    stems_dir = package / "STEMS"
    source_dir.mkdir(parents=True, mode=0o700)
    stems_dir.mkdir(mode=0o700)
    paths = {
        "source": source_dir / "source-44100.wav",
        "vocals": stems_dir / "vocals.wav",
        "instrumental": stems_dir / "instrumental.wav",
        "reconstruction": stems_dir / "reconstruction.wav",
    }
    arrays = {
        "source": source,
        "vocals": 0.35 * source,
        "instrumental": 0.65 * source,
        "reconstruction": source,
    }
    artifacts: dict[str, Any] = {}
    for role, path in paths.items():
        soundfile.write(path, arrays[role], SAMPLE_RATE, subtype="PCM_24")
        path.chmod(0o600)
        value, _ = soundfile.read(path, dtype="int32", always_2d=True)
        artifacts[role] = {
            "path": path.relative_to(package).as_posix(),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
            "geometry": {
                "sample_rate": SAMPLE_RATE,
                "channels": 2,
                "sample_width_bytes": 3,
                "frames": FRAMES,
            },
        }
        if role in {"source", "vocals", "instrumental"}:
            artifacts[role]["pcm24_int32_sequence_sha256"] = hashlib.sha256(
                value.astype("<i4", copy=False).tobytes(order="C")
            ).hexdigest()
    artifacts["reconstruction"]["global_gain"] = 1.0
    clock = {
        "sample_rate": SAMPLE_RATE,
        "channels": 2,
        "frames": FRAMES,
        "duration_seconds": FRAMES / SAMPLE_RATE,
        "chunk_count": len(source_plan["chunks"]),
        "boundary_count": 1,
        "gap_frames": 0,
        "overlap_frames": 0,
        "crossfade_frames": 0,
    }
    stitch = {
        "schema": STITCH_SCHEMA,
        "status": STITCH_STATUS,
        "evidence_scope": "private_development_only",
        "bindings": {
            "plan_report_sha256": _sha256(source_plan_path),
            "plan_document_sha256": source_plan["document_sha256"],
            "execution_state_sha256": hashlib.sha256(b"execution").hexdigest(),
        },
        "clock": clock,
        "artifacts": artifacts,
        "boundary_review": {"boundary_count": 1},
        "permissions": dict(STITCH_FALSE_PERMISSIONS),
    }
    stitch["document_sha256"] = _document_sha256(stitch)
    stitch_path = package / STITCH_NAME
    _write_private_json(stitch_path, stitch)
    package.chmod(0o700)

    boundary = 10 * SAMPLE_RATE
    window_start = boundary - 661_500 // 2
    remediation = {
        "schema": PLAN_SCHEMA,
        "status": PLAN_STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            "stitch_report_sha256": _sha256(stitch_path),
            "stitch_document_sha256": stitch["document_sha256"],
            "source_audio_sha256": artifacts["source"]["sha256"],
            "raw_vocals_audio_sha256": artifacts["vocals"]["sha256"],
            "raw_instrumental_audio_sha256": artifacts["instrumental"]["sha256"],
            "raw_reconstruction_audio_sha256": artifacts["reconstruction"]["sha256"],
            "plan_document_sha256": source_plan["document_sha256"],
        },
        "clock": clock,
        "protocol": {
            "source_window_frames": 661_500,
            "source_window_seconds": 15.0,
            "patch_half_frames": SAMPLE_RATE,
            "patch_duration_frames": 2 * SAMPLE_RATE,
            "patch_duration_seconds": 2.0,
            "edge_blend_frames": 4_410,
            "edge_blend_seconds": 0.1,
            "edge_blend_shape": "equal_power_old_to_new_then_new_to_old",
            "model_invocation": "test exact window",
            "candidate_policy": "test candidate only",
            "raw_stitch_is_control": True,
            "source_windows_may_overlap": True,
            "patch_regions_must_not_overlap": True,
        },
        "windows": [
            {
                "window_index": 1,
                "boundary_index": 1,
                "source_start_frame": window_start,
                "source_end_frame": window_start + 661_500,
                "patch_start_frame": boundary - SAMPLE_RATE,
                "patch_end_frame": boundary + SAMPLE_RATE,
                "patch_target_roles": ["vocals"],
            }
        ],
        "permissions": dict(PLAN_FALSE_PERMISSIONS),
        "effects": dict(PLAN_FALSE_EFFECTS),
    }
    remediation["document_sha256"] = _document_sha256(remediation)
    remediation_path = tmp_path / PLAN_NAME
    _write_private_json(remediation_path, remediation)
    return remediation_path, package, source_plan_path


def _runtime_arguments(tmp_path: Path) -> dict[str, Path]:
    values = {
        "repository_root": tmp_path / "repository",
        "runtime_launcher_path": tmp_path / "python",
        "source_root": tmp_path / "source",
        "checkpoint_path": tmp_path / "model.safetensors",
        "companion_root": tmp_path / "companions",
    }
    for key in ("repository_root", "source_root", "companion_root"):
        values[key].mkdir()
    values["runtime_launcher_path"].write_text("runtime", encoding="utf-8")
    values["checkpoint_path"].write_text("checkpoint", encoding="utf-8")
    return values


def _fake_runner(calls: list[int]):
    def run(**kwargs: Any) -> Mapping[str, Any]:
        report = json.loads(Path(kwargs["authorisation_report_path"]).read_text())
        frames = report["original"]["local_model_input"]["geometry"]["frames"]
        attempt = Path(kwargs["attempt_directory"])
        attempt.mkdir(mode=0o700)
        outputs = []
        for role, level in (("instrumental", 0.70), ("vocals", 0.30)):
            path = attempt / "staging/quarantine/STEMS" / f"{role}.wav"
            path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            with wave.open(str(path), "wb") as writer:
                writer.setnchannels(2)
                writer.setsampwidth(3)
                writer.setframerate(SAMPLE_RATE)
                sample = int(level * 8_388_607).to_bytes(3, "little", signed=True)
                writer.writeframes(sample * 2 * frames)
            path.chmod(0o600)
            outputs.append(
                {
                    "role": role,
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                    "geometry": {
                        "sample_rate": SAMPLE_RATE,
                        "channels": 2,
                        "sample_width_bytes": 3,
                        "frames": frames,
                    },
                }
            )
        request_sha = hashlib.sha256(kwargs["run_nonce"].encode()).hexdigest()
        receipt = _hash_document(
            {
                "schema": "sunofriend.private-melroformer-native-coordinator.v1",
                "status": "private_native_worker_complete_and_terminal",
                "request_sha256": request_sha,
                "permissions": {"product_route_permitted": False},
            },
            "receipt_sha256",
        )
        evidence = _hash_document(
            {
                "schema": "sunofriend.private-kim-native-attempt-evidence.v1",
                "status": "private_native_attempt_verified_not_selected",
                "bindings": {
                    "request_sha256": request_sha,
                    "terminal_receipt_sha256": receipt["receipt_sha256"],
                    "authorisation_report_sha256": kwargs[
                        "authorisation_report_sha256"
                    ],
                    "checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
                    "checkpoint_bytes": CONVERSION_CHECKPOINT_BYTES,
                },
                "outputs": outputs,
                "permissions": {"accepted": False},
            },
            "evidence_sha256",
        )
        timing = _hash_document(
            {
                "schema": "sunofriend.private-kim-native-attempt-timing.v1",
                "bindings": {
                    "request_sha256": request_sha,
                    "terminal_receipt_sha256": receipt["receipt_sha256"],
                    "output_evidence_sha256": evidence["evidence_sha256"],
                },
                "permissions": {"benchmark_claim": False},
            },
            "timing_sha256",
        )
        _write_private_json(attempt / "native-attempt-receipt.json", receipt)
        _write_private_json(attempt / "native-attempt-evidence.json", evidence)
        _write_private_json(attempt / "native-attempt-timing.json", timing)
        calls.append(frames)
        return receipt

    return run


def _hash_document(document: dict[str, Any], key: str) -> dict[str, Any]:
    payload = dict(document)
    payload.pop(key, None)
    document[key] = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return document


def _write_private_json(path: Path, document: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(document, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)
