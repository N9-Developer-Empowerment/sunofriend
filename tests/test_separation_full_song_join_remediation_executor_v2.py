from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat

import numpy as np
import pytest
import soundfile

import sunofriend._separation_full_song_join_remediation_executor_v2 as executor_v2

from sunofriend._separation_authorised_excerpt import _document_sha256, _sha256
from sunofriend._separation_full_song_join_remediation_executor import _state_sha256
from sunofriend._separation_full_song_join_remediation_executor_v2 import (
    CANDIDATES_DIRECTORY,
    REPORT_NAME,
    SCHEMA,
    STATUS,
    _execute_private_separation_full_song_join_remediation_v2,
)
from sunofriend._separation_full_song_join_remediation_plan_v2 import (
    REPORT_NAME as PLAN_REPORT_NAME,
)
from tests.test_separation_full_song_join_remediation_plan_v2 import (
    _Evidence,
    _evidence,
    _file_claim,
    _read,
    _rewrite_hashed,
    _run_plan,
    _write_private_json,
)


def test_v2_executor_reuses_workers_and_preserves_v1_pcm24_base(
    tmp_path: Path,
) -> None:
    evidence, plan_path, plan = _prepared(tmp_path)
    before = _input_hashes(evidence)
    output = tmp_path / "v2-execution"

    result = _execute(evidence, plan_path, output)

    assert result["schema"] == SCHEMA
    assert result["status"] == STATUS
    assert result["summary"]["planned_model_call_count"] == 0
    assert result["summary"]["executed_model_call_count"] == 0
    assert result["summary"]["v1_candidate_is_assembly_base"] is True
    assert result["summary"]["v1_candidate_source_hashes_unchanged"] is True
    assert result["effects"]["model_run"] is False
    assert all(value is False for value in result["permissions"].values())
    assert _input_hashes(evidence) == before

    report_path = output / REPORT_NAME
    assert report_path.is_file()
    assert not list(output.glob(f".{REPORT_NAME}.*.tmp"))
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert stat.S_IMODE(report_path.stat().st_mode) == 0o600
    assert report_path.stat().st_nlink == 1
    for role in ("vocals", "instrumental", "reconstruction"):
        audio = output / CANDIDATES_DIRECTORY / f"{role}.wav"
        assert stat.S_IMODE(audio.stat().st_mode) == 0o600
        assert audio.stat().st_nlink == 1
    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    assert "report" not in persisted
    assert str(tmp_path) not in report_path.read_text(encoding="utf-8")
    assert persisted["document_sha256"] == _document_sha256(persisted)

    candidate = _read(evidence.candidate)
    base_root = evidence.execution_dir
    for role in ("vocals", "instrumental"):
        base, _ = soundfile.read(
            base_root / candidate["artifacts"][role]["path"],
            dtype="int32",
            always_2d=True,
        )
        rendered, _ = soundfile.read(
            output / CANDIDATES_DIRECTORY / f"{role}.wav",
            dtype="int32",
            always_2d=True,
        )
        mask = np.ones((len(base),), dtype=bool)
        for window in plan["windows"]:
            if window["patch_target_role"] == role:
                mask[window["patch_start_frame"] : window["patch_end_frame"]] = False
        assert np.array_equal(base[mask], rendered[mask])
        artifact = persisted["artifacts"][role]
        assert artifact["outside_v2_target_pcm24_samples_exact"] is True
        assert artifact["v1_candidate_base_sha256"] == _sha256(
            base_root / candidate["artifacts"][role]["path"]
        )
        assert all(
            check["pcm24_samples_exact"]
            for check in artifact["preserved_v1_patch_checks"]
        )

    reconstruction = persisted["artifacts"]["reconstruction"]
    assert reconstruction["geometry"] == {
        "sample_rate": 44_100,
        "channels": 2,
        "sample_width_bytes": 3,
        "frames": plan["clock"]["frames"],
    }
    assert reconstruction["attenuation_only"] is True
    assert 0.0 < reconstruction["global_gain"] <= 1.0
    assert reconstruction["canonical_pcm24_projection_verified"] is True
    assert reconstruction["source_role_sha256"] == {
        role: persisted["artifacts"][role]["sha256"]
        for role in ("vocals", "instrumental")
    }


@pytest.mark.parametrize(
    "mutation",
    (
        "local_start_plus_one",
        "patch_end_plus_one",
        "same_role_overlap",
        "protocol_model_call",
        "candidate_base_changed",
    ),
)
def test_v2_executor_rejects_rehashed_semantic_plan_mutation(
    tmp_path: Path,
    mutation: str,
) -> None:
    evidence, plan_path, _plan = _prepared(tmp_path)
    document = _read(plan_path)
    if mutation == "local_start_plus_one":
        document["windows"][0]["worker_local_patch_start_frame"] += 1
    elif mutation == "patch_end_plus_one":
        document["windows"][0]["patch_end_frame"] += 1
    elif mutation == "same_role_overlap":
        first, match = next(
            (left, right)
            for index, left in enumerate(document["windows"])
            for right in document["windows"][index + 1 :]
            if right["patch_target_role"] == left["patch_target_role"]
        )
        match["patch_start_frame"] = first["patch_start_frame"] + 1
    elif mutation == "protocol_model_call":
        document["protocol"]["model_invocation"] = "run a model"
    elif mutation == "candidate_base_changed":
        document["protocol_delta_from_v1"]["candidate_base"] = "raw_stitch"
    else:  # pragma: no cover
        raise AssertionError(mutation)
    _rewrite_hashed(plan_path, document)

    with pytest.raises(ValueError):
        _execute(evidence, plan_path, tmp_path / "v2-execution")
    assert not (tmp_path / "v2-execution").exists()


@pytest.mark.parametrize("mutation", ("duplicate", "missing"))
def test_v2_executor_recomputes_equivalent_review_units(
    tmp_path: Path,
    mutation: str,
) -> None:
    evidence, plan_path, _plan = _prepared(tmp_path)
    resolved = _read(evidence.resolved_review)
    equivalent = [
        unit
        for unit in resolved["units"]
        if unit["kind"] == "boundary_role_pair"
        and unit["resolved_choice"] == "equivalent"
    ]
    if mutation == "duplicate":
        resolved["units"].append(dict(equivalent[0]))
    else:
        resolved["units"].remove(equivalent[0])
    _rewrite_hashed(evidence.resolved_review, resolved)

    with pytest.raises(ValueError):
        _execute(evidence, plan_path, tmp_path / "v2-execution")
    assert not (tmp_path / "v2-execution").exists()


def test_v2_executor_refuses_existing_and_raced_output(tmp_path: Path) -> None:
    evidence, plan_path, _plan = _prepared(tmp_path)
    existing = tmp_path / "existing"
    existing.mkdir(mode=0o700)
    marker = existing / "keep.txt"
    marker.write_text("keep\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="output exists"):
        _execute(evidence, plan_path, existing)
    assert marker.read_text(encoding="utf-8") == "keep\n"

    raced = tmp_path / "raced"
    original = executor_v2._publish_verified_candidate

    def create_race(*args: object, **kwargs: object) -> None:
        raced.mkdir(mode=0o700)
        original(*args, **kwargs)  # type: ignore[arg-type]

    executor_v2._publish_verified_candidate = create_race
    try:
        with pytest.raises(FileExistsError, match="output exists"):
            _execute(evidence, plan_path, raced)
    finally:
        executor_v2._publish_verified_candidate = original
    assert not (raced / REPORT_NAME).exists()


@pytest.mark.parametrize("root_name", ("execution", "package"))
def test_v2_executor_rejects_output_inside_input_evidence_tree(
    tmp_path: Path,
    root_name: str,
) -> None:
    evidence, plan_path, _plan = _prepared(tmp_path)
    root = evidence.execution_dir if root_name == "execution" else evidence.package
    before = _tree_inventory(root)
    output = root / "nested-v2-output"

    with pytest.raises(ValueError, match="outside input evidence roots"):
        _execute(evidence, plan_path, output)

    assert not output.exists()
    assert _tree_inventory(root) == before


def test_v2_executor_rejects_output_inside_json_evidence_root(
    tmp_path: Path,
) -> None:
    evidence, plan_path, _plan = _prepared(tmp_path)
    root = plan_path.parent
    before = _tree_inventory(root)
    output = root / "nested-v2-output"

    with pytest.raises(ValueError, match="outside input evidence roots"):
        _execute(evidence, plan_path, output)

    assert not output.exists()
    assert _tree_inventory(root) == before


def test_v2_executor_publishes_nothing_when_staging_verification_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence, plan_path, _plan = _prepared(tmp_path)
    output = tmp_path / "v2-execution"

    def fail(*_args: object, **_kwargs: object) -> None:
        raise ValueError("forced staged verification failure")

    monkeypatch.setattr(executor_v2, "_verify_staged_candidate", fail)
    with pytest.raises(ValueError, match="forced staged"):
        _execute(evidence, plan_path, output)
    assert not output.exists()


def test_v2_executor_rejects_overlap_with_preserved_same_role_patch(
    tmp_path: Path,
) -> None:
    evidence, plan_path, plan = _prepared(tmp_path)
    inputs = executor_v2._load_execution_inputs(
        plan,
        package_dir=evidence.package,
        v1_plan_path=evidence.v1_plan,
        v1_execution_report_path=evidence.execution,
        v1_candidate_report_path=evidence.candidate,
    )
    target = plan["windows"][0]
    preserved_key = (999, target["patch_target_role"])
    patch = dict(next(iter(inputs["patch_inventory"].values())))
    inputs["patch_inventory"][preserved_key] = patch
    patch["start_frame"] = target["patch_start_frame"] + 1
    patch["end_frame"] = target["patch_end_frame"] - 1

    with pytest.raises(ValueError, match="overlaps a preserved"):
        executor_v2._require_execution_geometry(plan, inputs)


def test_v2_executor_rechecks_inputs_after_audio_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence, plan_path, _plan = _prepared(tmp_path)
    output = tmp_path / "v2-execution"
    worker = next(
        evidence.execution_dir.glob("ATTEMPTS/*/staging/quarantine/STEMS/vocals.wav")
    )
    original = executor_v2._publish_verified_candidate

    def mutate_after_publish(*args: object, **kwargs: object) -> dict[str, int]:
        published = original(*args, **kwargs)  # type: ignore[arg-type]
        worker.write_bytes(worker.read_bytes() + b"changed-after-publish")
        return published

    monkeypatch.setattr(
        executor_v2, "_publish_verified_candidate", mutate_after_publish
    )
    with pytest.raises(ValueError):
        _execute(evidence, plan_path, output)
    assert (output / CANDIDATES_DIRECTORY / "vocals.wav").is_file()
    assert not (output / REPORT_NAME).exists()


def test_v2_executor_reverify_rejects_stitch_intermediate_symlink_rebinding(
    tmp_path: Path,
) -> None:
    evidence, plan_path, plan = _prepared(tmp_path)
    inputs = executor_v2._load_execution_inputs(
        plan,
        package_dir=evidence.package,
        v1_plan_path=evidence.v1_plan,
        v1_execution_report_path=evidence.execution,
        v1_candidate_report_path=evidence.candidate,
    )
    stems = evidence.package / "STEMS"
    original = evidence.package / "STEMS-original"
    stems.rename(original)
    stems.symlink_to(original.name, target_is_directory=True)

    with pytest.raises((OSError, ValueError)):
        executor_v2._reverify_input_audio(inputs)
    assert stems.is_symlink()
    assert plan_path.is_file()


def test_v2_executor_rechecks_published_audio_after_final_input_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence, plan_path, _plan = _prepared(tmp_path)
    output = tmp_path / "v2-execution"
    original = executor_v2._reverify_input_audio
    calls = 0

    def mutate_output_on_final_check(inputs: object) -> None:
        nonlocal calls
        original(inputs)  # type: ignore[arg-type]
        calls += 1
        if calls == 2:
            vocals = output / CANDIDATES_DIRECTORY / "vocals.wav"
            vocals.write_bytes(vocals.read_bytes() + b"changed-after-final-input-check")

    monkeypatch.setattr(
        executor_v2, "_reverify_input_audio", mutate_output_on_final_check
    )
    with pytest.raises(ValueError):
        _execute(evidence, plan_path, output)
    assert calls == 2
    assert not (output / REPORT_NAME).exists()


def test_v2_executor_rejects_rehashed_forged_edge_blend_sample(
    tmp_path: Path,
) -> None:
    evidence, plan_path, _plan = _prepared(tmp_path)
    output = tmp_path / "v2-execution"
    _execute(evidence, plan_path, output)

    report_path = output / REPORT_NAME
    report = _read(report_path)
    target = next(row for row in report["windows"] if row["role"] == "vocals")
    edge_frame = int(target["patch_start_frame"]) + 10
    candidate_root = output / CANDIDATES_DIRECTORY
    vocals_path = candidate_root / "vocals.wav"
    instrumental_path = candidate_root / "instrumental.wav"
    reconstruction_path = candidate_root / "reconstruction.wav"

    vocals, rate = soundfile.read(vocals_path, dtype="int32", always_2d=True)
    instrumental, _ = soundfile.read(
        instrumental_path,
        dtype="int32",
        always_2d=True,
    )
    vocals[edge_frame, 0] += 256
    soundfile.write(
        vocals_path,
        vocals.astype("float64") / 2_147_483_648.0,
        rate,
        subtype="PCM_24",
    )
    vocals_path.chmod(0o600)

    reconstruction_float = (
        vocals.astype("float64") + instrumental.astype("float64")
    ) / 2_147_483_648.0
    peak = float(np.max(np.abs(reconstruction_float)))
    gain = min(1.0, 0.98 / peak) if peak else 1.0
    reconstruction = executor_v2._quantize_float_to_pcm24_int32(
        reconstruction_float * gain,
        np=np,
    )
    soundfile.write(
        reconstruction_path,
        reconstruction.astype("float64") / 2_147_483_648.0,
        rate,
        subtype="PCM_24",
    )
    reconstruction_path.chmod(0o600)

    for role, path in (
        ("vocals", vocals_path),
        ("reconstruction", reconstruction_path),
    ):
        snapshot = executor_v2._read_pcm24_snapshot(
            path,
            None,
            expected_frames=int(report["clock"]["frames"]),
            label=f"forged private v2 {role}",
        )
        report["artifacts"][role]["sha256"] = snapshot["sha256"]
        report["artifacts"][role]["bytes"] = snapshot["bytes"]
        report["artifacts"][role]["pcm24_int32_sequence_sha256"] = snapshot[
            "pcm24_int32_sequence_sha256"
        ]
    report["artifacts"]["reconstruction"]["global_gain"] = round(gain, 9)
    _rewrite_hashed(report_path, report)

    inputs = executor_v2._load_execution_inputs(
        _read(plan_path),
        package_dir=evidence.package,
        v1_plan_path=evidence.v1_plan,
        v1_execution_report_path=evidence.execution,
        v1_candidate_report_path=evidence.candidate,
    )
    with pytest.raises(ValueError, match="published patched role differs"):
        executor_v2._verify_published_candidate(output, report, inputs=inputs)


def test_v2_executor_revokes_report_when_audio_changes_during_report_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence, plan_path, _plan = _prepared(tmp_path)
    output = tmp_path / "v2-execution"
    original = executor_v2._write_json_exclusive

    def write_then_mutate_audio(*args: object, **kwargs: object) -> tuple[int, ...]:
        identity = original(*args, **kwargs)  # type: ignore[arg-type]
        vocals = output / CANDIDATES_DIRECTORY / "vocals.wav"
        vocals.write_bytes(vocals.read_bytes() + b"changed-during-report-write")
        return identity

    monkeypatch.setattr(
        executor_v2,
        "_write_json_exclusive",
        write_then_mutate_audio,
    )
    with pytest.raises(ValueError):
        _execute(evidence, plan_path, output)

    assert (output / CANDIDATES_DIRECTORY / "vocals.wav").is_file()
    assert not (output / REPORT_NAME).exists()
    assert not list(output.glob(f".{REPORT_NAME}.*.tmp"))


def test_report_writer_rolls_back_its_inode_after_post_link_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "private-report-output"
    output.mkdir(mode=0o700)
    descriptor = os.open(
        output,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    original = executor_v2._inode_identity
    calls = 0

    def mismatch_final_link(value: os.stat_result) -> tuple[int, int]:
        nonlocal calls
        calls += 1
        identity = original(value)
        if calls == 4:
            return (identity[0], identity[1] + 1)
        return identity

    monkeypatch.setattr(executor_v2, "_inode_identity", mismatch_final_link)
    try:
        with pytest.raises(RuntimeError, match="published report identity changed"):
            executor_v2._write_json_exclusive(
                descriptor,
                REPORT_NAME,
                {"status": "test"},
            )
    finally:
        os.close(descriptor)

    assert not (output / REPORT_NAME).exists()
    assert not list(output.glob(f".{REPORT_NAME}.*.tmp"))


def test_report_writer_rolls_back_after_temp_unlink_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "private-report-output"
    output.mkdir(mode=0o700)
    descriptor = os.open(
        output,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    original = os.unlink
    injected = False

    def fail_first_temp_unlink(path: object, *args: object, **kwargs: object) -> None:
        nonlocal injected
        if not injected and str(path).endswith(".tmp"):
            injected = True
            raise OSError("injected temp cleanup failure")
        original(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "unlink", fail_first_temp_unlink)
    try:
        with pytest.raises(OSError, match="injected temp cleanup failure"):
            executor_v2._write_json_exclusive(
                descriptor,
                REPORT_NAME,
                {"status": "test"},
            )
    finally:
        os.close(descriptor)

    assert injected is True
    assert not (output / REPORT_NAME).exists()
    assert not list(output.glob(f".{REPORT_NAME}.*.tmp"))


def test_report_writer_rolls_back_after_final_nlink_validation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "private-report-output"
    output.mkdir(mode=0o700)
    descriptor = os.open(
        output,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    original = executor_v2._unlink_name_if_inode_at
    injected = False

    def add_extra_link_after_temp_cleanup(
        directory_descriptor: int,
        name: str,
        *,
        expected_inode: tuple[int, int],
    ) -> bool:
        nonlocal injected
        removed = original(
            directory_descriptor,
            name,
            expected_inode=expected_inode,
        )
        if removed and name.endswith(".tmp") and not injected:
            injected = True
            os.link(
                REPORT_NAME,
                "extra-report-link",
                src_dir_fd=directory_descriptor,
                dst_dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
        return removed

    monkeypatch.setattr(
        executor_v2,
        "_unlink_name_if_inode_at",
        add_extra_link_after_temp_cleanup,
    )
    try:
        with pytest.raises(RuntimeError, match="published report is not owner-only"):
            executor_v2._write_json_exclusive(
                descriptor,
                REPORT_NAME,
                {"status": "test"},
            )
    finally:
        os.close(descriptor)

    assert injected is True
    assert not (output / REPORT_NAME).exists()
    assert not list(output.glob(f".{REPORT_NAME}.*.tmp"))
    assert (output / "extra-report-link").is_file()


def test_report_writer_closes_and_removes_temp_when_initial_fstat_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "private-report-output"
    output.mkdir(mode=0o700)
    descriptor = os.open(
        output,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    original = os.fstat
    injected = False

    def fail_first_fstat(file_descriptor: int) -> os.stat_result:
        nonlocal injected
        if not injected:
            injected = True
            raise OSError("injected initial fstat failure")
        return original(file_descriptor)

    monkeypatch.setattr(os, "fstat", fail_first_fstat)
    try:
        with pytest.raises(OSError, match="injected initial fstat failure"):
            executor_v2._write_json_exclusive(
                descriptor,
                REPORT_NAME,
                {"status": "test"},
            )
    finally:
        os.close(descriptor)

    assert injected is True
    assert not (output / REPORT_NAME).exists()
    assert not list(output.glob(f".{REPORT_NAME}.*.tmp"))


def test_report_writer_never_removes_a_raced_report(tmp_path: Path) -> None:
    output = tmp_path / "private-report-output"
    output.mkdir(mode=0o700)
    report = output / REPORT_NAME
    report.write_bytes(b"raced-report\n")
    report.chmod(0o600)
    descriptor = os.open(
        output,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        with pytest.raises(FileExistsError):
            executor_v2._write_json_exclusive(
                descriptor,
                REPORT_NAME,
                {"status": "test"},
            )
    finally:
        os.close(descriptor)

    assert report.read_bytes() == b"raced-report\n"
    assert not list(output.glob(f".{REPORT_NAME}.*.tmp"))


def test_v2_executor_parent_symlink_swap_cannot_redirect_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence, plan_path, _plan = _prepared(tmp_path)
    safe_parent = tmp_path / "safe-output-parent"
    safe_parent.mkdir(mode=0o700)
    moved_parent = tmp_path / "held-safe-output-parent"
    output = safe_parent / "v2-execution"
    evidence_before = _tree_inventory(evidence.package)
    original = executor_v2._publish_verified_candidate

    def swap_parent_then_publish(*args: object, **kwargs: object) -> dict[str, int]:
        safe_parent.rename(moved_parent)
        safe_parent.symlink_to(evidence.package, target_is_directory=True)
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        executor_v2,
        "_publish_verified_candidate",
        swap_parent_then_publish,
    )
    with pytest.raises(RuntimeError, match="visible output binding changed"):
        _execute(evidence, plan_path, output)

    assert _tree_inventory(evidence.package) == evidence_before
    assert not (evidence.package / output.name).exists()
    assert (moved_parent / output.name / CANDIDATES_DIRECTORY / "vocals.wav").is_file()
    assert not (moved_parent / output.name / REPORT_NAME).exists()


def test_v2_executor_atomic_publish_never_populates_raced_final_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence, plan_path, _plan = _prepared(tmp_path)
    output_parent = tmp_path / "exclusive-output-parent"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "v2-execution"
    original = executor_v2._rename_directory_exclusive_at

    def install_victim_then_rename(
        parent_descriptor: int,
        source_name: str,
        destination_name: str,
    ) -> None:
        os.mkdir(destination_name, mode=0o700, dir_fd=parent_descriptor)
        victim_descriptor = os.open(
            destination_name,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            dir_fd=parent_descriptor,
        )
        try:
            marker_descriptor = os.open(
                "victim.txt",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=victim_descriptor,
            )
            os.write(marker_descriptor, b"do-not-populate\n")
            os.close(marker_descriptor)
        finally:
            os.close(victim_descriptor)
        original(parent_descriptor, source_name, destination_name)

    monkeypatch.setattr(
        executor_v2,
        "_rename_directory_exclusive_at",
        install_victim_then_rename,
    )
    with pytest.raises(FileExistsError, match="output exists"):
        _execute(evidence, plan_path, output)

    assert (output / "victim.txt").read_text(encoding="utf-8") == "do-not-populate\n"
    assert not (output / CANDIDATES_DIRECTORY).exists()
    assert not (output / REPORT_NAME).exists()
    assert not list(output_parent.glob(f".{output.name}.*.building"))


def test_v2_executor_rejects_hidden_build_directory_substitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence, plan_path, _plan = _prepared(tmp_path)
    output_parent = tmp_path / "build-substitution-parent"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "v2-execution"
    original = executor_v2._open_directory_at

    def substitute_before_open(
        parent_descriptor: int,
        name: str,
        label: str,
        **kwargs: object,
    ) -> int:
        if label == "private v2 remediation build root":
            os.rename(
                name,
                f"{name}.held",
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            os.mkdir(name, mode=0o700, dir_fd=parent_descriptor)
            victim_descriptor = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
                dir_fd=parent_descriptor,
            )
            marker_descriptor = os.open(
                "victim.txt",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=victim_descriptor,
            )
            os.write(marker_descriptor, b"not-an-output\n")
            os.close(marker_descriptor)
            os.close(victim_descriptor)
        return original(parent_descriptor, name, label, **kwargs)

    monkeypatch.setattr(executor_v2, "_open_directory_at", substitute_before_open)
    with pytest.raises(ValueError, match="not an owner-only directory"):
        _execute(evidence, plan_path, output)

    victims = [
        path
        for path in output_parent.glob(f".{output.name}.*.building")
        if (path / "victim.txt").is_file()
    ]
    assert len(victims) == 1
    assert (victims[0] / "victim.txt").read_text(encoding="utf-8") == (
        "not-an-output\n"
    )
    assert not (victims[0] / CANDIDATES_DIRECTORY).exists()
    assert not output.exists()


def test_v2_executor_rejects_hidden_candidates_directory_substitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence, plan_path, _plan = _prepared(tmp_path)
    output_parent = tmp_path / "candidate-substitution-parent"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "v2-execution"
    original = executor_v2._open_directory_at

    def substitute_before_open(
        parent_descriptor: int,
        name: str,
        label: str,
        **kwargs: object,
    ) -> int:
        if label == "private v2 candidate root":
            os.rename(
                name,
                f"{name}-held",
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            os.mkdir(name, mode=0o700, dir_fd=parent_descriptor)
            victim_descriptor = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
                dir_fd=parent_descriptor,
            )
            marker_descriptor = os.open(
                "victim.txt",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=victim_descriptor,
            )
            os.write(marker_descriptor, b"not-a-candidate-root\n")
            os.close(marker_descriptor)
            os.close(victim_descriptor)
        return original(parent_descriptor, name, label, **kwargs)

    monkeypatch.setattr(executor_v2, "_open_directory_at", substitute_before_open)
    with pytest.raises(ValueError, match="not an owner-only directory"):
        _execute(evidence, plan_path, output)

    builds = list(output_parent.glob(f".{output.name}.*.building"))
    assert len(builds) == 1
    assert (builds[0] / CANDIDATES_DIRECTORY / "victim.txt").read_text(
        encoding="utf-8"
    ) == "not-a-candidate-root\n"
    assert not list((builds[0] / CANDIDATES_DIRECTORY).glob("*.wav"))
    assert not output.exists()


def test_v2_executor_checks_atomic_rename_support_before_output_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence, plan_path, _plan = _prepared(tmp_path)
    output_parent = tmp_path / "unsupported-publication-parent"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "v2-execution"

    def unsupported() -> None:
        raise RuntimeError("atomic exclusive rename unavailable")

    monkeypatch.setattr(
        executor_v2,
        "_require_exclusive_directory_rename_available",
        unsupported,
    )
    with pytest.raises(RuntimeError, match="rename unavailable"):
        _execute(evidence, plan_path, output)

    assert list(output_parent.iterdir()) == []


def test_v2_executor_requires_preexisting_output_parent(tmp_path: Path) -> None:
    evidence, plan_path, _plan = _prepared(tmp_path)
    missing_parent = tmp_path / "missing-parent"

    with pytest.raises(ValueError, match="must already exist"):
        _execute(evidence, plan_path, missing_parent / "v2-execution")

    assert not missing_parent.exists()


def test_v2_executor_rejects_symlinked_output_parent_component(
    tmp_path: Path,
) -> None:
    evidence, plan_path, _plan = _prepared(tmp_path)
    real_parent = tmp_path / "real-output-parent"
    real_parent.mkdir(mode=0o700)
    alias = tmp_path / "output-parent-alias"
    alias.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(ValueError, match="without symbolic links"):
        _execute(evidence, plan_path, alias / "v2-execution")

    assert not (real_parent / "v2-execution").exists()


def test_v2_executor_rejects_group_or_world_writable_output_parent(
    tmp_path: Path,
) -> None:
    evidence, plan_path, _plan = _prepared(tmp_path)
    unsafe_parent = tmp_path / "unsafe-output-parent"
    unsafe_parent.mkdir(mode=0o700)
    unsafe_parent.chmod(0o722)

    with pytest.raises(RuntimeError, match="not safely bound"):
        _execute(evidence, plan_path, unsafe_parent / "v2-execution")

    assert not (unsafe_parent / "v2-execution").exists()


def test_v2_executor_revokes_report_when_visible_candidates_directory_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence, plan_path, _plan = _prepared(tmp_path)
    output = tmp_path / "v2-execution"
    original = executor_v2._write_json_exclusive

    def write_then_replace_candidates(
        *args: object, **kwargs: object
    ) -> tuple[int, ...]:
        identity = original(*args, **kwargs)  # type: ignore[arg-type]
        candidates = output / CANDIDATES_DIRECTORY
        candidates.rename(output / "CANDIDATES-held-original")
        candidates.mkdir(mode=0o700)
        return identity

    monkeypatch.setattr(
        executor_v2,
        "_write_json_exclusive",
        write_then_replace_candidates,
    )
    with pytest.raises(RuntimeError, match="visible output binding changed"):
        _execute(evidence, plan_path, output)

    assert not (output / REPORT_NAME).exists()
    assert not list(output.glob(f".{REPORT_NAME}.*.tmp"))
    assert (output / "CANDIDATES-held-original" / "vocals.wav").is_file()
    assert list((output / CANDIDATES_DIRECTORY).iterdir()) == []


def test_v2_executor_revokes_report_when_final_directory_fsync_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence, plan_path, _plan = _prepared(tmp_path)
    output = tmp_path / "v2-execution"
    original_binding = executor_v2._require_visible_output_binding
    original_fsync = os.fsync
    binding_calls = 0
    armed = False
    injected = False

    def arm_after_post_report_binding(*args: object, **kwargs: object) -> None:
        nonlocal binding_calls, armed
        original_binding(*args, **kwargs)  # type: ignore[arg-type]
        binding_calls += 1
        if binding_calls == 2:
            armed = True

    def fail_first_final_fsync(descriptor: int) -> None:
        nonlocal armed, injected
        if armed and not injected:
            armed = False
            injected = True
            raise OSError("injected final directory fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(
        executor_v2,
        "_require_visible_output_binding",
        arm_after_post_report_binding,
    )
    monkeypatch.setattr(os, "fsync", fail_first_final_fsync)
    with pytest.raises(OSError, match="injected final directory fsync failure"):
        _execute(evidence, plan_path, output)

    assert binding_calls == 2
    assert injected is True
    assert not (output / REPORT_NAME).exists()
    assert not list(output.glob(f".{REPORT_NAME}.*.tmp"))


@pytest.mark.parametrize("collision", ("symlink", "hardlink"))
def test_pcm24_staging_write_refuses_existing_link_without_touching_victim(
    tmp_path: Path,
    collision: str,
) -> None:
    victim = tmp_path / "victim.wav"
    victim.write_bytes(b"do-not-change")
    victim.chmod(0o600)
    target = tmp_path / "target.wav"
    if collision == "symlink":
        target.symlink_to(victim.name)
    else:
        os.link(victim, target)
    before = victim.read_bytes()

    with pytest.raises(FileExistsError):
        executor_v2._write_pcm24_exclusive(
            target,
            np.zeros((32, 2), dtype=np.float64),
        )

    assert victim.read_bytes() == before


@pytest.mark.parametrize("kind", ("group_readable", "hard_link", "symlink"))
def test_v2_executor_rejects_unsafe_candidate_audio(
    tmp_path: Path,
    kind: str,
) -> None:
    evidence = _evidence(tmp_path)
    candidate = _read(evidence.candidate)
    path = evidence.execution_dir / candidate["artifacts"]["vocals"]["path"]
    if kind == "group_readable":
        path.chmod(0o640)
    elif kind == "hard_link":
        os.link(path, path.with_name("linked-vocals.wav"))
    else:
        original = path.with_name("original-vocals.wav")
        path.rename(original)
        path.symlink_to(original.name)

    plan_root = tmp_path / "v2-plan"
    plan_root.mkdir(mode=0o700)
    with pytest.raises(ValueError):
        _run_plan(evidence, plan_root / PLAN_REPORT_NAME)


def test_v2_executor_rejects_worker_mutation_after_plan(tmp_path: Path) -> None:
    evidence, plan_path, _plan = _prepared(tmp_path)
    worker = next(
        evidence.execution_dir.glob("ATTEMPTS/*/staging/quarantine/STEMS/vocals.wav")
    )
    worker.write_bytes(worker.read_bytes() + b"changed")

    with pytest.raises(ValueError):
        _execute(evidence, plan_path, tmp_path / "v2-execution")
    assert not (tmp_path / "v2-execution").exists()


def test_v2_executor_preserves_distinct_v1_candidate_sentinel(
    tmp_path: Path,
) -> None:
    evidence = _evidence(tmp_path)
    _isolate_executor_evidence(evidence, tmp_path)
    candidate = _read(evidence.candidate)
    role = "instrumental"
    path = evidence.execution_dir / candidate["artifacts"][role]["path"]
    samples, rate = soundfile.read(path, dtype="int32", always_2d=True)
    sentinel_frame = 100
    samples[sentinel_frame] = np.array([123_456 << 8, -234_567 << 8], dtype=np.int32)
    soundfile.write(path, samples, rate, subtype="PCM_24")
    path.chmod(0o600)
    _refresh_candidate_chain(evidence)

    plan_root = tmp_path / "v2-plan"
    plan_root.mkdir(mode=0o700)
    plan_path = plan_root / PLAN_REPORT_NAME
    plan = _run_plan(evidence, plan_path)
    assert all(
        not (
            item["patch_target_role"] == role
            and item["patch_start_frame"] <= sentinel_frame < item["patch_end_frame"]
        )
        for item in plan["windows"]
    )

    output = tmp_path / "v2-execution"
    _execute(evidence, plan_path, output)
    rendered, _ = soundfile.read(
        output / CANDIDATES_DIRECTORY / f"{role}.wav",
        dtype="int32",
        always_2d=True,
    )
    assert np.array_equal(rendered[sentinel_frame], samples[sentinel_frame])


def test_v2_executor_rejects_pcm24_noop_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence, plan_path, _plan = _prepared(tmp_path)
    original = executor_v2._apply_equal_power_patch

    def no_op(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(executor_v2, "_apply_equal_power_patch", no_op)
    with pytest.raises(ValueError, match="no PCM24 sample change"):
        _execute(evidence, plan_path, tmp_path / "v2-execution")
    monkeypatch.setattr(executor_v2, "_apply_equal_power_patch", original)
    assert not (tmp_path / "v2-execution").exists()


def test_v2_executor_cli_has_no_model_runtime_or_device_interface() -> None:
    script = Path(
        "scripts/private-separation-full-song-join-remediation-execute-v2.py"
    ).read_text(encoding="utf-8")
    assert "attempt_runner" not in script
    assert "--checkpoint" not in script
    assert "--runtime" not in script
    assert "--device" not in script
    assert 'model_run": False' in Path(executor_v2.__file__).read_text(encoding="utf-8")


def _prepared(tmp_path: Path) -> tuple[_Evidence, Path, dict[str, object]]:
    evidence = _evidence(tmp_path)
    _isolate_executor_evidence(evidence, tmp_path)
    plan_root = tmp_path / "v2-plan"
    plan_root.mkdir(mode=0o700)
    plan_path = plan_root / PLAN_REPORT_NAME
    plan = _run_plan(evidence, plan_path)
    return evidence, plan_path, plan


def _isolate_executor_evidence(evidence: _Evidence, tmp_path: Path) -> None:
    """Give standalone JSON inputs dedicated roots like the real evidence."""

    for attribute in ("review", "resolved_review", "readiness"):
        source = getattr(evidence, attribute)
        if source.parent != tmp_path:
            continue
        root = tmp_path / f"{attribute.replace('_', '-')}-root"
        root.mkdir(mode=0o700)
        destination = root / source.name
        shutil.move(source, destination)
        destination.chmod(0o600)
        setattr(evidence, attribute, destination)


def _execute(evidence: _Evidence, plan: Path, output: Path) -> dict[str, object]:
    return _execute_private_separation_full_song_join_remediation_v2(
        plan,
        package_dir=evidence.package,
        full_song_review_result_path=evidence.review,
        v1_plan_path=evidence.v1_plan,
        v1_execution_report_path=evidence.execution,
        v1_candidate_report_path=evidence.candidate,
        resolved_join_review_result_path=evidence.resolved_review,
        publication_readiness_path=evidence.readiness,
        out_dir=output,
    )


def _input_hashes(evidence: _Evidence) -> dict[str, str]:
    paths = [
        evidence.package / "private-separation-full-song-stitch.json",
        evidence.v1_plan,
        evidence.execution,
        evidence.candidate,
        evidence.resolved_review,
        evidence.readiness,
        *evidence.package.rglob("*.wav"),
        *evidence.execution_dir.glob("CANDIDATES/*.wav"),
        *evidence.execution_dir.glob("ATTEMPTS/*/staging/quarantine/STEMS/*.wav"),
    ]
    return {path.as_posix(): _sha256(path) for path in sorted(paths)}


def _tree_inventory(root: Path) -> list[tuple[str, str, int, str | None]]:
    result: list[tuple[str, str, int, str | None]] = []
    for path in sorted((root, *root.rglob("*"))):
        state = path.lstat()
        relative = "." if path == root else path.relative_to(root).as_posix()
        kind = "directory" if stat.S_ISDIR(state.st_mode) else "file"
        digest = _sha256(path) if kind == "file" and not path.is_symlink() else None
        result.append((relative, kind, stat.S_IMODE(state.st_mode), digest))
    return result


def _refresh_candidate_chain(evidence: _Evidence) -> None:
    candidate = _read(evidence.candidate)
    for role in ("vocals", "instrumental", "reconstruction"):
        artifact_path = evidence.execution_dir / candidate["artifacts"][role]["path"]
        candidate["artifacts"][role]["sha256"] = _sha256(artifact_path)
        candidate["artifacts"][role]["bytes"] = artifact_path.stat().st_size
    _rewrite_hashed(evidence.candidate, candidate)

    execution = _read(evidence.execution)
    execution["candidate_report"] = _file_claim(evidence.candidate)
    execution["state_sha256"] = _state_sha256(execution)
    _write_private_json(evidence.execution, execution)

    resolved = _read(evidence.resolved_review)
    resolved["bindings"].update(
        {
            "candidate_report_sha256": _sha256(evidence.candidate),
            "candidate_document_sha256": candidate["document_sha256"],
            "execution_report_sha256": _sha256(evidence.execution),
            "execution_state_sha256": execution["state_sha256"],
        }
    )
    _rewrite_hashed(evidence.resolved_review, resolved)

    readiness = _read(evidence.readiness)
    readiness["inputs"].update(
        {
            "full_song_join_remediation_review_result_sha256": _sha256(
                evidence.resolved_review
            ),
            "full_song_join_remediation_review_result_document_sha256": resolved[
                "document_sha256"
            ],
        }
    )
    _rewrite_hashed(evidence.readiness, readiness)
