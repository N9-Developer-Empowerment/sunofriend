from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat

import numpy as np
import pytest
import soundfile

import sunofriend._separation_full_song_join_remediation_review_v2 as review_v2

from sunofriend._separation_authorised_excerpt import _document_sha256, _sha256
from sunofriend._separation_full_song_join_remediation_executor_v2 import (
    CANDIDATES_DIRECTORY,
    REPORT_NAME as EXECUTION_REPORT_NAME,
)
from sunofriend._separation_full_song_join_remediation_review_v2 import (
    ANSWER_KEY_NAME,
    AUDIO_DIRECTORY,
    HTML_NAME,
    POLICY_ID,
    REPORT_NAME,
    SCHEMA,
    STATUS,
    _prepare_private_join_remediation_review_v2,
)
from sunofriend._separation_publication_readiness import (
    _assess_join_remediation_review,
)
from tests.test_separation_full_song_join_remediation_executor_v2 import (
    _execute,
    _isolate_executor_evidence,
)
from tests.test_separation_full_song_join_remediation_plan_v2 import (
    REPORT_NAME as PLAN_REPORT_NAME,
    _evidence as _plan_evidence,
    _read,
    _rewrite_hashed,
    _run_plan,
)


def test_v2_review_builds_exact_targeted_blind_package(tmp_path: Path) -> None:
    evidence, v2_execution, review_root, result = _review_fixture(tmp_path)

    assert result["schema"] == SCHEMA
    assert result["status"] == STATUS
    assert result["policy_id"] == POLICY_ID
    assert result["expected_counts"] == {
        "boundary_comparison_units": 2,
        "v2_patch_edge_units": 4,
        "total_units": 6,
        "anonymous_boundary_audio_clips": 4,
        "v2_edge_audio_clips": 4,
        "total_audio_references": 8,
    }
    assert all(value is False for value in result["permissions"].values())
    assert all(value is False for value in result["readiness"].values())
    assert result["effects"]["candidate_audio_selected"] is False
    assert result["effects"]["separator_selected"] is False

    persisted = _read(review_root / REPORT_NAME)
    assert persisted["document_sha256"] == _document_sha256(persisted)
    assert set(persisted["bindings"]) == {
        "source_bindings_commitment",
        "audio_manifest_sha256",
        "answer_key_sha256",
        "answer_key_document_sha256",
    }
    boundary = [
        unit for unit in persisted["units"] if unit["kind"] == "boundary_candidate_pair"
    ]
    edges = [unit for unit in persisted["units"] if unit["kind"] == "v2_patch_edge"]
    assert len(boundary) == 2
    assert len(edges) == 4
    assert not any("complete_song" in unit["kind"] for unit in persisted["units"])
    for unit in boundary:
        assert set(unit["audio"]) == {"A", "B"}
        assert unit["heard"] == {"A": False, "B": False}
        assert unit["absolute_cleanliness"] == {"A": None, "B": None}
        assert unit["comparative_choice"] is None
        assert unit["level_policy"] == (
            "attenuate-louder-to-quieter-whole-window-sample-rms-v2"
        )
    for unit in edges:
        assert set(unit["audio"]) == {"clip"}
        assert unit["heard"] is False
        assert unit["absolute_cleanliness"] is None
        assert "comparative_choice" not in unit
        assert unit["level_policy"] == "unchanged-v2-pcm24-window-no-level-processing"

    key = _read(review_root / ANSWER_KEY_NAME)
    assert key["status"] == "sealed_do_not_open_before_review"
    assert key["document_sha256"] == _document_sha256(key)
    assert persisted["bindings"]["answer_key_sha256"] == _sha256(
        review_root / ANSWER_KEY_NAME
    )
    assert len(key["boundary_assignments"]) == 2
    for assignment in key["boundary_assignments"]:
        assert set(assignment["assignment"]) == {"A", "B"}
        assert set(assignment["assignment"].values()) == {
            "v1_candidate",
            "v2_candidate",
        }
        assert 0 < assignment["v1_candidate_gain"] <= 1
        assert 0 < assignment["v2_candidate_gain"] <= 1
        assert (
            max(assignment["v1_candidate_gain"], assignment["v2_candidate_gain"]) == 1
        )

    page = (review_root / HTML_NAME).read_text(encoding="utf-8")
    assert "How clean is A?" in page
    assert "How clean is B?" in page
    assert "How clean is this edge?" in page
    assert "which do you prefer?" in page
    assert 'value=\\"equivalent\\"' in page
    assert 'value=\\"neither\\"' in page
    assert "v1_candidate" not in page
    assert "v2_candidate" not in page
    assert "boundary_assignments" not in page
    assert ANSWER_KEY_NAME not in page

    assert set(path.name for path in review_root.iterdir()) == {
        AUDIO_DIRECTORY,
        ANSWER_KEY_NAME,
        HTML_NAME,
        REPORT_NAME,
    }
    assert stat.S_IMODE(review_root.stat().st_mode) == 0o700
    assert stat.S_IMODE((review_root / AUDIO_DIRECTORY).stat().st_mode) == 0o700
    for path in review_root.rglob("*"):
        if path.is_file():
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
            assert path.stat().st_nlink == 1
    assert not list(tmp_path.glob(f".{review_root.name}.*.building"))
    assert v2_execution.is_dir()
    assert evidence.package.is_dir()


def test_v2_review_audio_has_equal_boundary_rms_and_exact_edge_pcm24(
    tmp_path: Path,
) -> None:
    _evidence, v2_execution, review_root, result = _review_fixture(tmp_path)
    execution = _read(v2_execution / EXECUTION_REPORT_NAME)

    for unit in result["units"]:
        if unit["kind"] == "boundary_candidate_pair":
            values = []
            for slot in ("A", "B"):
                samples, rate = soundfile.read(
                    review_root / unit["audio"][slot]["path"],
                    dtype="float64",
                    always_2d=True,
                )
                assert rate == 44_100
                values.append(float(np.sqrt(np.mean(np.square(samples)))))
            assert np.isclose(values[0], values[1], rtol=2e-6, atol=1e-9)
            assert (
                unit["source_window"]["end_frame"]
                - unit["source_window"]["start_frame"]
                == 4 * 44_100
            )
            continue

        parts = unit["unit_id"].split("-")
        boundary_index = int(parts[3])
        role = parts[4]
        edge_name = parts[5]
        window = next(
            row
            for row in execution["windows"]
            if row["boundary_index"] == boundary_index and row["role"] == role
        )
        source, _ = soundfile.read(
            v2_execution / CANDIDATES_DIRECTORY / f"{role}.wav",
            dtype="int32",
            always_2d=True,
        )
        centre = window[f"patch_{edge_name}_frame"]
        expected = source[centre - 44_100 : centre + 44_100]
        rendered, _ = soundfile.read(
            review_root / unit["audio"]["clip"]["path"],
            dtype="int32",
            always_2d=True,
        )
        assert np.array_equal(rendered, expected)


def test_v2_review_refuses_existing_and_evidence_nested_output(tmp_path: Path) -> None:
    evidence, plan_path, _plan = _prepared_two_windows(tmp_path)
    v2_execution = tmp_path / "v2-execution"
    _execute(evidence, plan_path, v2_execution)
    existing = tmp_path / "existing-review"
    existing.mkdir(mode=0o700)
    marker = existing / "keep.txt"
    marker.write_text("keep\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="review exists"):
        _prepare_private_join_remediation_review_v2(
            v2_execution,
            v2_plan_path=plan_path,
            v1_execution_dir=evidence.execution_dir,
            stitch_package_dir=evidence.package,
            full_song_review_result_path=evidence.review,
            v1_plan_path=evidence.v1_plan,
            resolved_join_review_result_path=evidence.resolved_review,
            publication_readiness_path=evidence.readiness,
            out_dir=existing,
        )
    assert marker.read_text(encoding="utf-8") == "keep\n"

    nested = evidence.package / "nested-review"
    with pytest.raises(ValueError, match="outside input evidence roots"):
        _prepare_private_join_remediation_review_v2(
            v2_execution,
            v2_plan_path=plan_path,
            v1_execution_dir=evidence.execution_dir,
            stitch_package_dir=evidence.package,
            full_song_review_result_path=evidence.review,
            v1_plan_path=evidence.v1_plan,
            resolved_join_review_result_path=evidence.resolved_review,
            publication_readiness_path=evidence.readiness,
            out_dir=nested,
        )
    assert not nested.exists()

    nested_in_plan = plan_path.parent / "nested-review"
    with pytest.raises(ValueError, match="outside input evidence roots"):
        _prepare_private_join_remediation_review_v2(
            v2_execution,
            v2_plan_path=plan_path,
            v1_execution_dir=evidence.execution_dir,
            stitch_package_dir=evidence.package,
            full_song_review_result_path=evidence.review,
            v1_plan_path=evidence.v1_plan,
            resolved_join_review_result_path=evidence.resolved_review,
            publication_readiness_path=evidence.readiness,
            out_dir=nested_in_plan,
        )
    assert not nested_in_plan.exists()


@pytest.mark.parametrize(
    "mutation",
    (
        "publication_ready",
        "candidate_incomplete",
        "interior_unverified",
        "outside_unverified",
        "window_shift",
    ),
)
def test_v2_review_rejects_rehashed_v2_semantic_mutation(
    tmp_path: Path,
    mutation: str,
) -> None:
    evidence, plan_path, _plan = _prepared_two_windows(tmp_path)
    v2_execution = tmp_path / "v2-execution"
    _execute(evidence, plan_path, v2_execution)
    report = v2_execution / EXECUTION_REPORT_NAME
    mutated = _read(report)
    if mutation == "publication_ready":
        mutated["readiness"]["publication_ready"] = True
    elif mutation == "candidate_incomplete":
        mutated["readiness"]["v2_candidate_audio_complete"] = False
    elif mutation == "interior_unverified":
        mutated["windows"][0]["interior_pcm24_samples_match_worker"] = False
    elif mutation == "outside_unverified":
        mutated["windows"][0]["outside_target_pcm24_samples_match_v1_candidate"] = False
    elif mutation == "window_shift":
        mutated["windows"][0]["patch_start_frame"] += 44_100
        mutated["windows"][0]["patch_end_frame"] += 44_100
    else:  # pragma: no cover
        raise AssertionError(mutation)
    _rewrite_hashed(report, mutated)

    with pytest.raises(ValueError, match="not review-ready|review window differs"):
        _prepare_private_join_remediation_review_v2(
            v2_execution,
            v2_plan_path=plan_path,
            v1_execution_dir=evidence.execution_dir,
            stitch_package_dir=evidence.package,
            full_song_review_result_path=evidence.review,
            v1_plan_path=evidence.v1_plan,
            resolved_join_review_result_path=evidence.resolved_review,
            publication_readiness_path=evidence.readiness,
            out_dir=tmp_path / "review",
        )
    assert not (tmp_path / "review").exists()


def test_v2_review_rejects_rehashed_plan_not_bound_to_execution(
    tmp_path: Path,
) -> None:
    evidence, plan_path, _plan = _prepared_two_windows(tmp_path)
    v2_execution = tmp_path / "v2-execution"
    _execute(evidence, plan_path, v2_execution)
    plan = _read(plan_path)
    plan["limitations"][0] += " changed"
    _rewrite_hashed(plan_path, plan)

    with pytest.raises(ValueError, match="plan derivation differs|not review-ready"):
        _prepare_private_join_remediation_review_v2(
            v2_execution,
            v2_plan_path=plan_path,
            v1_execution_dir=evidence.execution_dir,
            stitch_package_dir=evidence.package,
            full_song_review_result_path=evidence.review,
            v1_plan_path=evidence.v1_plan,
            resolved_join_review_result_path=evidence.resolved_review,
            publication_readiness_path=evidence.readiness,
            out_dir=tmp_path / "review",
        )
    assert not (tmp_path / "review").exists()


def test_v2_review_rejects_jointly_rehashed_shifted_plan_and_execution(
    tmp_path: Path,
) -> None:
    evidence, plan_path, _plan = _prepared_two_windows(tmp_path)
    v2_execution = tmp_path / "v2-execution"
    _execute(evidence, plan_path, v2_execution)

    plan = _read(plan_path)
    planned = plan["windows"][0]
    for key in (
        "boundary_frame",
        "source_start_frame",
        "source_end_frame",
        "patch_start_frame",
        "patch_end_frame",
    ):
        planned[key] += 441
    for key in (
        "boundary_seconds",
        "source_start_seconds",
        "source_end_seconds",
        "patch_start_seconds",
        "patch_end_seconds",
    ):
        planned[key] += 0.01
    _rewrite_hashed(plan_path, plan)

    execution_path = v2_execution / EXECUTION_REPORT_NAME
    execution = _read(execution_path)
    execution["bindings"]["v2_plan_sha256"] = _sha256(plan_path)
    execution["bindings"]["v2_plan_document_sha256"] = plan["document_sha256"]
    window = execution["windows"][0]
    for key in (
        "source_start_frame",
        "source_end_frame",
        "patch_start_frame",
        "patch_end_frame",
    ):
        window[key] += 441
    _rewrite_hashed(execution_path, execution)

    with pytest.raises(ValueError, match="plan derivation differs"):
        _prepare_private_join_remediation_review_v2(
            v2_execution,
            v2_plan_path=plan_path,
            v1_execution_dir=evidence.execution_dir,
            stitch_package_dir=evidence.package,
            full_song_review_result_path=evidence.review,
            v1_plan_path=evidence.v1_plan,
            resolved_join_review_result_path=evidence.resolved_review,
            publication_readiness_path=evidence.readiness,
            out_dir=tmp_path / "review",
        )
    assert not (tmp_path / "review").exists()


def test_v2_review_same_size_staged_mutation_publishes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence, plan_path, _plan = _prepared_two_windows(tmp_path)
    v2_execution = tmp_path / "v2-execution"
    _execute(evidence, plan_path, v2_execution)
    output = tmp_path / "review"
    original = review_v2._verify_staged_package

    def verify_then_mutate_html(*args: object, **kwargs: object) -> None:
        original(*args, **kwargs)  # type: ignore[arg-type]
        page = args[0] / HTML_NAME  # type: ignore[operator]
        payload = bytearray(page.read_bytes())
        payload[-2] = payload[-2] ^ 1
        page.write_bytes(payload)
        page.chmod(0o600)

    monkeypatch.setattr(
        review_v2,
        "_verify_staged_package",
        verify_then_mutate_html,
    )
    with pytest.raises(ValueError, match="staged HTML differs"):
        _prepare_private_join_remediation_review_v2(
            v2_execution,
            v2_plan_path=plan_path,
            v1_execution_dir=evidence.execution_dir,
            stitch_package_dir=evidence.package,
            full_song_review_result_path=evidence.review,
            v1_plan_path=evidence.v1_plan,
            resolved_join_review_result_path=evidence.resolved_review,
            publication_readiness_path=evidence.readiness,
            out_dir=output,
        )
    assert not output.exists()
    assert not list(tmp_path.glob(f".{output.name}.*.building"))


def test_v2_review_post_rename_mutation_revokes_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence, plan_path, _plan = _prepared_two_windows(tmp_path)
    v2_execution = tmp_path / "v2-execution"
    _execute(evidence, plan_path, v2_execution)
    output = tmp_path / "review"
    original = review_v2._rename_directory_exclusive_at

    def mutate_audio_then_rename(
        parent_descriptor: int,
        source_name: str,
        destination_name: str,
    ) -> None:
        build = os.open(
            source_name,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            dir_fd=parent_descriptor,
        )
        audio = os.open(
            AUDIO_DIRECTORY,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            dir_fd=build,
        )
        try:
            name = sorted(os.listdir(audio))[0]
            descriptor = os.open(name, os.O_RDWR, dir_fd=audio)
            try:
                os.lseek(descriptor, -1, os.SEEK_END)
                value = os.read(descriptor, 1)
                os.lseek(descriptor, -1, os.SEEK_END)
                os.write(descriptor, bytes((value[0] ^ 1,)))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            os.close(audio)
            os.close(build)
        original(parent_descriptor, source_name, destination_name)

    monkeypatch.setattr(
        review_v2,
        "_rename_directory_exclusive_at",
        mutate_audio_then_rename,
    )
    with pytest.raises(ValueError):
        _prepare_private_join_remediation_review_v2(
            v2_execution,
            v2_plan_path=plan_path,
            v1_execution_dir=evidence.execution_dir,
            stitch_package_dir=evidence.package,
            full_song_review_result_path=evidence.review,
            v1_plan_path=evidence.v1_plan,
            resolved_join_review_result_path=evidence.resolved_review,
            publication_readiness_path=evidence.readiness,
            out_dir=output,
        )
    assert output.is_dir()
    assert not (output / REPORT_NAME).exists()
    assert (output / AUDIO_DIRECTORY).is_dir()
    assert not list(tmp_path.glob(f".{output.name}.*.building"))


def test_v2_review_post_rename_input_mutation_revokes_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence, plan_path, _plan = _prepared_two_windows(tmp_path)
    v2_execution = tmp_path / "v2-execution"
    _execute(evidence, plan_path, v2_execution)
    output = tmp_path / "review"
    input_audio = v2_execution / CANDIDATES_DIRECTORY / "vocals.wav"
    original = review_v2._rename_directory_exclusive_at

    def rename_then_mutate_input(
        parent_descriptor: int,
        source_name: str,
        destination_name: str,
    ) -> None:
        original(parent_descriptor, source_name, destination_name)
        payload = bytearray(input_audio.read_bytes())
        payload[-1] ^= 1
        input_audio.write_bytes(payload)
        input_audio.chmod(0o600)

    monkeypatch.setattr(
        review_v2,
        "_rename_directory_exclusive_at",
        rename_then_mutate_input,
    )
    with pytest.raises(ValueError, match="audio binding differs"):
        _prepare_private_join_remediation_review_v2(
            v2_execution,
            v2_plan_path=plan_path,
            v1_execution_dir=evidence.execution_dir,
            stitch_package_dir=evidence.package,
            full_song_review_result_path=evidence.review,
            v1_plan_path=evidence.v1_plan,
            resolved_join_review_result_path=evidence.resolved_review,
            publication_readiness_path=evidence.readiness,
            out_dir=output,
        )
    assert output.is_dir()
    assert not (output / REPORT_NAME).exists()
    assert (output / AUDIO_DIRECTORY).is_dir()
    assert not list(tmp_path.glob(f".{output.name}.*.building"))


@pytest.mark.parametrize("substitution", ("symlink", "hardlink"))
def test_v2_review_post_rename_candidate_rebinding_revokes_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    substitution: str,
) -> None:
    evidence, plan_path, _plan = _prepared_two_windows(tmp_path)
    v2_execution = tmp_path / "v2-execution"
    _execute(evidence, plan_path, v2_execution)
    output = tmp_path / "review"
    input_audio = v2_execution / CANDIDATES_DIRECTORY / "vocals.wav"
    identical = tmp_path / "identical-v2-vocals.wav"
    shutil.copyfile(input_audio, identical)
    identical.chmod(0o600)
    original = review_v2._rename_directory_exclusive_at

    def rename_then_rebind_input(
        parent_descriptor: int,
        source_name: str,
        destination_name: str,
    ) -> None:
        original(parent_descriptor, source_name, destination_name)
        input_audio.unlink()
        if substitution == "symlink":
            input_audio.symlink_to(identical)
        else:
            os.link(identical, input_audio)

    monkeypatch.setattr(
        review_v2,
        "_rename_directory_exclusive_at",
        rename_then_rebind_input,
    )
    with pytest.raises(ValueError, match="unavailable|single-link|owner-only regular"):
        _prepare_private_join_remediation_review_v2(
            v2_execution,
            v2_plan_path=plan_path,
            v1_execution_dir=evidence.execution_dir,
            stitch_package_dir=evidence.package,
            full_song_review_result_path=evidence.review,
            v1_plan_path=evidence.v1_plan,
            resolved_join_review_result_path=evidence.resolved_review,
            publication_readiness_path=evidence.readiness,
            out_dir=output,
        )
    assert output.is_dir()
    assert not (output / REPORT_NAME).exists()
    assert (output / AUDIO_DIRECTORY).is_dir()


def test_v2_review_post_rename_stitch_directory_rebinding_revokes_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence, plan_path, _plan = _prepared_two_windows(tmp_path)
    v2_execution = tmp_path / "v2-execution"
    _execute(evidence, plan_path, v2_execution)
    output = tmp_path / "review"
    stems = evidence.package / "STEMS"
    moved = evidence.package / "STEMS-original"
    original = review_v2._rename_directory_exclusive_at

    def rename_then_rebind_stems(
        parent_descriptor: int,
        source_name: str,
        destination_name: str,
    ) -> None:
        original(parent_descriptor, source_name, destination_name)
        stems.rename(moved)
        stems.symlink_to(moved.name, target_is_directory=True)

    monkeypatch.setattr(
        review_v2,
        "_rename_directory_exclusive_at",
        rename_then_rebind_stems,
    )
    with pytest.raises((OSError, ValueError)):
        _prepare_private_join_remediation_review_v2(
            v2_execution,
            v2_plan_path=plan_path,
            v1_execution_dir=evidence.execution_dir,
            stitch_package_dir=evidence.package,
            full_song_review_result_path=evidence.review,
            v1_plan_path=evidence.v1_plan,
            resolved_join_review_result_path=evidence.resolved_review,
            publication_readiness_path=evidence.readiness,
            out_dir=output,
        )
    assert output.is_dir()
    assert not (output / REPORT_NAME).exists()
    assert (output / AUDIO_DIRECTORY).is_dir()
    assert stems.is_symlink()


def test_v2_review_close_failure_after_integrity_gates_does_not_report_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence, plan_path, _plan = _prepared_two_windows(tmp_path)
    v2_execution = tmp_path / "v2-execution"
    _execute(evidence, plan_path, v2_execution)
    output = tmp_path / "review"
    original_reverify = review_v2._reverify_inputs
    original_close = os.close
    state = {"reverify_calls": 0, "armed": False, "injected": False}

    def arm_after_post_rename_reverification(context: object) -> None:
        original_reverify(context)  # type: ignore[arg-type]
        state["reverify_calls"] += 1
        if state["reverify_calls"] == 2:
            state["armed"] = True

    def close_then_fail_once(descriptor: int) -> None:
        original_close(descriptor)
        if state["armed"] and not state["injected"]:
            state["injected"] = True
            raise OSError("injected close failure after publication gates")

    monkeypatch.setattr(
        review_v2, "_reverify_inputs", arm_after_post_rename_reverification
    )
    monkeypatch.setattr(review_v2.os, "close", close_then_fail_once)

    result = _prepare_private_join_remediation_review_v2(
        v2_execution,
        v2_plan_path=plan_path,
        v1_execution_dir=evidence.execution_dir,
        stitch_package_dir=evidence.package,
        full_song_review_result_path=evidence.review,
        v1_plan_path=evidence.v1_plan,
        resolved_join_review_result_path=evidence.resolved_review,
        publication_readiness_path=evidence.readiness,
        out_dir=output,
    )

    assert state == {"reverify_calls": 2, "armed": True, "injected": True}
    assert result["status"] == STATUS
    assert _read(output / REPORT_NAME)["document_sha256"] == result["document_sha256"]


def test_v2_review_atomic_publish_does_not_populate_raced_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence, plan_path, _plan = _prepared_two_windows(tmp_path)
    v2_execution = tmp_path / "v2-execution"
    _execute(evidence, plan_path, v2_execution)
    output = tmp_path / "review"
    original = review_v2._rename_directory_exclusive_at

    def race(
        parent_descriptor: int,
        source_name: str,
        destination_name: str,
    ) -> None:
        os.mkdir(destination_name, mode=0o700, dir_fd=parent_descriptor)
        victim = os.open(
            destination_name,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            dir_fd=parent_descriptor,
        )
        try:
            marker = os.open(
                "victim.txt",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=victim,
            )
            os.write(marker, b"do-not-populate\n")
            os.close(marker)
        finally:
            os.close(victim)
        original(parent_descriptor, source_name, destination_name)

    monkeypatch.setattr(review_v2, "_rename_directory_exclusive_at", race)
    with pytest.raises(FileExistsError, match="review exists"):
        _prepare_private_join_remediation_review_v2(
            v2_execution,
            v2_plan_path=plan_path,
            v1_execution_dir=evidence.execution_dir,
            stitch_package_dir=evidence.package,
            full_song_review_result_path=evidence.review,
            v1_plan_path=evidence.v1_plan,
            resolved_join_review_result_path=evidence.resolved_review,
            publication_readiness_path=evidence.readiness,
            out_dir=output,
        )
    assert (output / "victim.txt").read_text(encoding="utf-8") == "do-not-populate\n"
    assert not (output / REPORT_NAME).exists()
    assert not (output / AUDIO_DIRECTORY).exists()
    assert not list(tmp_path.glob(f".{output.name}.*.building"))


def test_v2_review_cli_is_targeted_and_has_no_model_interface() -> None:
    script = Path(
        "scripts/private-separation-full-song-join-remediation-review-v2.py"
    ).read_text(encoding="utf-8")
    assert "--v1-execution-dir" in script
    assert "--v2-plan" in script
    assert "--full-song-review-result" in script
    assert "--v1-plan" in script
    assert "--resolved-join-review-result" in script
    assert "--publication-readiness" in script
    assert "--package-dir" in script
    assert "--out-dir" in script
    assert "complete-song review" in script
    assert "--checkpoint" not in script
    assert "--runtime" not in script
    assert "--device" not in script


def _review_fixture(tmp_path: Path) -> tuple[object, Path, Path, dict[str, object]]:
    evidence, plan_path, _plan = _prepared_two_windows(tmp_path)
    v2_execution = tmp_path / "v2-execution"
    _execute(evidence, plan_path, v2_execution)
    review_root = tmp_path / "v2-review"
    result = _prepare_private_join_remediation_review_v2(
        v2_execution,
        v2_plan_path=plan_path,
        v1_execution_dir=evidence.execution_dir,
        stitch_package_dir=evidence.package,
        full_song_review_result_path=evidence.review,
        v1_plan_path=evidence.v1_plan,
        resolved_join_review_result_path=evidence.resolved_review,
        publication_readiness_path=evidence.readiness,
        out_dir=review_root,
    )
    return evidence, v2_execution, review_root, result


def _prepared_two_windows(tmp_path: Path) -> tuple[object, Path, dict[str, object]]:
    """Build semantically valid evidence with exactly two v2 target windows."""

    evidence = _plan_evidence(tmp_path)
    _isolate_executor_evidence(evidence, tmp_path)

    resolved = _read(evidence.resolved_review)
    demoted = next(
        unit
        for unit in resolved["units"]
        if unit["kind"] == "boundary_role_pair"
        and unit["resolved_choice"] == "equivalent"
    )
    demoted["blind_choice"] = "A"
    demoted["resolved_choice"] = "candidate_preferred"
    resolved["counts_by_kind_and_outcome"]["boundary_role_pair"]["equivalent"] -= 1
    resolved["counts_by_kind_and_outcome"]["boundary_role_pair"][
        "candidate_preferred"
    ] += 1
    resolved["overall_outcome_counts"]["equivalent"] -= 1
    resolved["overall_outcome_counts"]["candidate_preferred"] += 1
    _rewrite_hashed(evidence.resolved_review, resolved)

    readiness = _read(evidence.readiness)
    readiness["inputs"]["full_song_join_remediation_review_result_sha256"] = _sha256(
        evidence.resolved_review
    )
    readiness["inputs"]["full_song_join_remediation_review_result_document_sha256"] = (
        resolved["document_sha256"]
    )
    readiness["full_song_join_remediation_assessment"] = (
        _assess_join_remediation_review(resolved)
    )
    _rewrite_hashed(evidence.readiness, readiness)

    plan_root = tmp_path / "v2-plan"
    plan_root.mkdir(mode=0o700)
    plan_path = plan_root / PLAN_REPORT_NAME
    plan = _run_plan(evidence, plan_path)
    assert plan["summary"]["human_equivalent_boundary_role_pair_count"] == 2
    return evidence, plan_path, plan
