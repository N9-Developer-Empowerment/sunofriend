from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import numpy as np
import pytest
import soundfile

import sunofriend.listening_master as listening_master
from sunofriend.listening_master import (
    LISTENING_MASTER_EFFECTS,
    LISTENING_MASTER_POLICY,
    LISTENING_MASTER_PREFLIGHT_SCHEMA,
    LISTENING_MASTER_SCHEMA,
    LISTENING_MASTER_TARGETS,
    _parse_loudnorm_stats,
    _second_pass_filter,
    build_listening_master,
    check_listening_master_dependencies,
)
from sunofriend.listening_master_contract import (
    LISTENING_MASTER_VERIFICATION_SCHEMA,
    verify_listening_master_artifacts,
)


GOOD_STATS = {
    "input_i": "-18.40",
    "input_tp": "-2.20",
    "input_lra": "3.10",
    "input_thresh": "-28.50",
    "output_i": "-16.00",
    "output_tp": "-1.00",
    "output_lra": "3.20",
    "output_thresh": "-26.10",
    "normalization_type": "dynamic",
    "target_offset": "0.00",
}


def _source_wav(path: Path) -> None:
    sample_rate = 8_000
    seconds = np.arange(sample_rate, dtype=np.float64) / sample_rate
    values = np.column_stack(
        [
            0.1 * np.sin(2 * np.pi * 220 * seconds),
            0.1 * np.sin(2 * np.pi * 330 * seconds),
        ]
    )
    soundfile.write(path, values, sample_rate, subtype="PCM_24")


def _fake_ffmpeg(
    path: Path,
    *,
    render_output_i: str = "-16.00",
    verification_input_i: str = "-16.00",
    verification_input_tp: str = "-1.00",
    require_private_audio: bool = False,
    provide_loudnorm: bool = True,
) -> None:
    render_stats = {**GOOD_STATS, "output_i": render_output_i}
    verification_stats = {
        **GOOD_STATS,
        "input_i": verification_input_i,
        "input_tp": verification_input_tp,
    }
    script = f"""#!/usr/bin/env python3
import json
import os
import shutil
import stat
import sys

args = sys.argv[1:]
if "-version" in args:
    print("ffmpeg version sunofriend-test")
    raise SystemExit(0)
if "-filters" in args:
    print({"' .. loudnorm          A->A       EBU R128 scanner'" if provide_loudnorm else "' .. volume            A->A       Change input volume'"})
    raise SystemExit(0)
source = args[args.index("-i") + 1]
destination = args[-1]
audio_filter = args[args.index("-af") + 1]
if destination != "-":
    if {require_private_audio!r}:
        source_mode = stat.S_IMODE(os.fstat(int(source.rsplit("/", 1)[-1])).st_mode)
        destination_mode = stat.S_IMODE(
            os.fstat(int(destination.rsplit("/", 1)[-1])).st_mode
        )
        if source_mode != 0o600:
            raise SystemExit("source snapshot was not private during render")
        if destination_mode != 0o600:
            raise SystemExit("render target was not private during render")
    shutil.copyfile(source, destination)
if "dual_mono=false" in audio_filter:
    stats = {json.dumps(verification_stats)}
elif destination != "-":
    stats = {json.dumps(render_stats)}
else:
    stats = {json.dumps(GOOD_STATS)}
print(json.dumps(stats), file=sys.stderr)
"""
    path.write_text(script, encoding="utf-8")
    path.chmod(0o700)


def _contains_value(value: object, expected: str) -> bool:
    if isinstance(value, dict):
        return any(_contains_value(item, expected) for item in value.values())
    if isinstance(value, list):
        return any(_contains_value(item, expected) for item in value)
    return value == expected


def _contains_absolute_path(value: object) -> bool:
    if isinstance(value, dict):
        return any(_contains_absolute_path(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_absolute_path(item) for item in value)
    return isinstance(value, str) and os.path.isabs(value)


def test_dependency_preflight_returns_path_free_pinned_runtime_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = tmp_path / "ffmpeg"
    _fake_ffmpeg(fake)
    pinned: list[listening_master._PinnedExecutable] = []
    original_pin = listening_master._pin_ffmpeg

    def observed_pin(path: Path) -> listening_master._PinnedExecutable:
        executable = original_pin(path)
        pinned.append(executable)
        return executable

    monkeypatch.setattr(listening_master, "_pin_ffmpeg", observed_pin)

    result = check_listening_master_dependencies(fake)

    assert result["schema"] == LISTENING_MASTER_PREFLIGHT_SCHEMA
    assert result["ready"] is True
    assert result["soundfile"]["available"] is True
    assert result["soundfile"]["version"]
    assert result["ffmpeg"]["backend"] == "FFmpeg loudnorm"
    assert result["ffmpeg"]["version"] == "ffmpeg version sunofriend-test"
    assert result["ffmpeg"]["filter"] == "loudnorm"
    assert result["ffmpeg"]["policy"] == LISTENING_MASTER_POLICY
    assert result["ffmpeg"]["executable_sha256"] == hashlib.sha256(
        fake.read_bytes()
    ).hexdigest()
    assert not _contains_absolute_path(result)
    assert len(pinned) == 1
    with pytest.raises(OSError):
        os.fstat(pinned[0].fd)


def test_dependency_preflight_rejects_ffmpeg_without_loudnorm(
    tmp_path: Path,
) -> None:
    fake = tmp_path / "ffmpeg"
    _fake_ffmpeg(fake, provide_loudnorm=False)

    with pytest.raises(RuntimeError, match="required loudnorm filter"):
        check_listening_master_dependencies(fake)


def test_dependency_preflight_requires_soundfile_before_ffmpeg(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = tmp_path / "ffmpeg"
    _fake_ffmpeg(fake)
    pinned = False

    def missing_soundfile() -> object:
        raise RuntimeError("listening-master requires soundfile")

    def unexpected_pin(_path: Path) -> listening_master._PinnedExecutable:
        nonlocal pinned
        pinned = True
        raise AssertionError("FFmpeg must not be admitted without soundfile")

    monkeypatch.setattr(listening_master, "_soundfile_module", missing_soundfile)
    monkeypatch.setattr(listening_master, "_pin_ffmpeg", unexpected_pin)

    with pytest.raises(RuntimeError, match="requires soundfile"):
        check_listening_master_dependencies(fake)

    assert pinned is False


def test_parse_loudnorm_stats_uses_last_complete_json() -> None:
    earlier = {**GOOD_STATS, "input_i": "-30.00"}
    stderr = (
        "ordinary diagnostic\n"
        + json.dumps(earlier)
        + "\nmore diagnostic\n"
        + json.dumps(GOOD_STATS)
    )

    parsed = _parse_loudnorm_stats(stderr)

    assert parsed["input_i"] == -18.4
    assert parsed["output_i"] == -16.0
    assert parsed["normalization_type"] == "dynamic"


def test_second_pass_filter_pins_measurements_and_frame_horizon() -> None:
    parsed = _parse_loudnorm_stats(json.dumps(GOOD_STATS))

    value = _second_pass_filter(parsed, sample_rate=44_100, frames=123_456)

    assert "measured_I=-18.400000" in value
    assert "measured_LRA=3.100000" in value
    assert "measured_TP=-2.200000" in value
    assert "measured_thresh=-28.500000" in value
    assert "aresample=44100" in value
    assert "atrim=end_sample=123456" in value
    assert value.endswith("asetpts=N/SR/TB")


def test_build_listening_master_creates_fresh_private_hash_bound_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "balanced-control.wav"
    output = tmp_path / "listening-master.wav"
    report = tmp_path / "listening-master.json"
    fake = tmp_path / "ffmpeg"
    _source_wav(source)
    _fake_ffmpeg(fake)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    synced_directories: list[tuple[int, int]] = []
    original_fsync = os.fsync

    def observed_fsync(descriptor: int) -> None:
        metadata = os.fstat(descriptor)
        if stat.S_ISDIR(metadata.st_mode):
            synced_directories.append((metadata.st_dev, metadata.st_ino))
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", observed_fsync)

    result = build_listening_master(
        source,
        output_path=output,
        report_path=report,
        ffmpeg_path=fake,
    )

    assert result["mastered"] is True
    assert result["release_master"] is False
    assert result["source_audio_mutated"] is False
    assert result["midi_mutated"] is False
    assert result["selection_changed"] is False
    assert result["input_integrated_lufs"] == -18.4
    assert result["output_integrated_lufs"] == -16.0
    assert result["output_true_peak_dbtp"] == -1.0
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    assert hashlib.sha256(output.read_bytes()).hexdigest() == result["master_sha256"]
    assert oct(output.stat().st_mode & 0o777) == "0o600"
    assert oct(report.stat().st_mode & 0o777) == "0o600"

    document = json.loads(report.read_text(encoding="utf-8"))
    assert document["schema"] == LISTENING_MASTER_SCHEMA
    assert document["policy"] == LISTENING_MASTER_POLICY
    assert document["mastered"] is True
    assert document["release_master"] is False
    assert document["source"]["sha256"] == source_hash
    assert document["source"]["frames"] == document["output"]["frames"]
    assert document["timing"]["frame_horizon_changed"] is False
    assert document["processing"]["true_peak_limiting"] is True
    assert document["processing"]["encoded_artifact_verified"] is True
    assert (
        document["renderer"]["identity_verification"]
        == "stat-and-sha256-before-after-every-pass-v1"
    )
    assert document["verification_pass"]["input_i"] == -16.0
    assert document["verification_pass"]["input_tp"] == -1.0
    assert document["verification_pass"]["measured_artifact"] == "encoded_pcm24_output"
    assert document["effects"]["control_balance_replaced"] is False
    assert document["effects"]["listening_master_created"] is True
    assert not _contains_value(document, str(source))
    assert not _contains_value(document, str(output))
    unsigned = {
        key: value for key, value in document.items() if key != "receipt_sha256"
    }
    payload_hash = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert document["receipt_sha256"] == payload_hash
    destination_identity = (tmp_path.stat().st_dev, tmp_path.stat().st_ino)
    assert synced_directories.count(destination_identity) == 1


def test_public_contract_verifies_exact_artifacts_and_returns_no_paths(
    tmp_path: Path,
) -> None:
    source = tmp_path / "balanced-control.wav"
    output = tmp_path / "listening-master.wav"
    report = tmp_path / "listening-master.json"
    fake = tmp_path / "ffmpeg"
    _source_wav(source)
    _fake_ffmpeg(fake)
    build_listening_master(
        source,
        output_path=output,
        report_path=report,
        ffmpeg_path=fake,
    )

    verified = verify_listening_master_artifacts(source, output, report)

    assert verified["schema"] == LISTENING_MASTER_VERIFICATION_SCHEMA
    assert verified["status"] == "verified"
    assert verified["receipt_schema"] == LISTENING_MASTER_SCHEMA
    assert verified["policy"] == LISTENING_MASTER_POLICY
    assert verified["source"]["sha256"] == hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    assert verified["master"]["sha256"] == hashlib.sha256(
        output.read_bytes()
    ).hexdigest()
    assert verified["receipt_file"]["sha256"] == hashlib.sha256(
        report.read_bytes()
    ).hexdigest()
    assert verified["targets"] == dict(LISTENING_MASTER_TARGETS)
    assert verified["effects"] == dict(LISTENING_MASTER_EFFECTS)
    assert (
        verified["measurements"]["verification"]["measured_artifact"]
        == "encoded_pcm24_output"
    )
    assert not _contains_absolute_path(verified)
    with pytest.raises(TypeError):
        LISTENING_MASTER_TARGETS["integrated_lufs"] = -14.0  # type: ignore[index]
    with pytest.raises(TypeError):
        LISTENING_MASTER_EFFECTS["selection_changed"] = True  # type: ignore[index]


def test_build_listening_master_refuses_existing_output(tmp_path: Path) -> None:
    source = tmp_path / "balanced-control.wav"
    output = tmp_path / "listening-master.wav"
    report = tmp_path / "listening-master.json"
    fake = tmp_path / "ffmpeg"
    _source_wav(source)
    _fake_ffmpeg(fake)
    output.write_bytes(b"occupied")

    with pytest.raises(ValueError, match="already exists"):
        build_listening_master(
            source,
            output_path=output,
            report_path=report,
            ffmpeg_path=fake,
        )

    assert output.read_bytes() == b"occupied"
    assert not report.exists()


def test_build_listening_master_rejects_missed_loudness_target_and_cleans_up(
    tmp_path: Path,
) -> None:
    source = tmp_path / "balanced-control.wav"
    output = tmp_path / "listening-master.wav"
    report = tmp_path / "listening-master.json"
    fake = tmp_path / "ffmpeg"
    _source_wav(source)
    # The render log claims success, but the independent encoded-artifact
    # analysis exposes the miss.
    _fake_ffmpeg(
        fake,
        render_output_i="-16.00",
        verification_input_i="-15.20",
    )

    with pytest.raises(RuntimeError, match="integrated loudness"):
        build_listening_master(
            source,
            output_path=output,
            report_path=report,
            ffmpeg_path=fake,
        )

    assert not output.exists()
    assert not report.exists()
    assert not any(path.name.endswith(".tmp.wav") for path in tmp_path.iterdir())
    assert not any(path.name.endswith(".source.wav") for path in tmp_path.iterdir())


def test_build_listening_master_report_publish_refuses_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "balanced-control.wav"
    output = tmp_path / "listening-master.wav"
    report = tmp_path / "listening-master.json"
    fake = tmp_path / "ffmpeg"
    _source_wav(source)
    _fake_ffmpeg(fake)
    original_link = os.link
    original_fsync = os.fsync
    synced_directories: list[tuple[int, int]] = []

    def observed_fsync(descriptor: int) -> None:
        metadata = os.fstat(descriptor)
        if stat.S_ISDIR(metadata.st_mode):
            synced_directories.append((metadata.st_dev, metadata.st_ino))
        original_fsync(descriptor)

    def racing_link(
        source_path: object,
        destination_path: object,
        **kwargs: object,
    ) -> None:
        if destination_path == report.name:
            descriptor = os.open(
                report.name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=int(kwargs["dst_dir_fd"]),
            )
            os.write(descriptor, b"competitor")
            os.close(descriptor)
        original_link(source_path, destination_path, **kwargs)

    monkeypatch.setattr(os, "link", racing_link)
    monkeypatch.setattr(os, "fsync", observed_fsync)

    with pytest.raises((FileExistsError, ValueError)):
        build_listening_master(
            source,
            output_path=output,
            report_path=report,
            ffmpeg_path=fake,
        )

    # The competitor's file is never replaced; the new master is rolled back.
    assert report.read_text(encoding="utf-8") == "competitor"
    assert not output.exists()
    destination_identity = (tmp_path.stat().st_dev, tmp_path.stat().st_ino)
    assert synced_directories.count(destination_identity) == 1


def test_build_listening_master_interrupt_rolls_back_partial_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "balanced-control.wav"
    output = tmp_path / "listening-master.wav"
    report = tmp_path / "listening-master.json"
    fake = tmp_path / "ffmpeg"
    _source_wav(source)
    _fake_ffmpeg(fake)
    original_publish = listening_master._publish_private_file
    publish_count = 0

    def interrupt_before_report(*args: object, **kwargs: object) -> None:
        nonlocal publish_count
        publish_count += 1
        if publish_count == 2:
            raise KeyboardInterrupt
        original_publish(*args, **kwargs)

    monkeypatch.setattr(
        listening_master,
        "_publish_private_file",
        interrupt_before_report,
    )

    with pytest.raises(KeyboardInterrupt):
        build_listening_master(
            source,
            output_path=output,
            report_path=report,
            ffmpeg_path=fake,
        )

    assert publish_count == 2
    assert not output.exists()
    assert not report.exists()


def test_build_listening_master_fsyncs_each_distinct_destination_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "balanced-control.wav"
    output_parent = tmp_path / "audio"
    report_parent = tmp_path / "reports"
    output_parent.mkdir()
    report_parent.mkdir()
    output = output_parent / "listening-master.wav"
    report = report_parent / "listening-master.json"
    fake = tmp_path / "ffmpeg"
    _source_wav(source)
    _fake_ffmpeg(fake)
    original_fsync = os.fsync
    synced_directories: list[tuple[int, int]] = []

    def observed_fsync(descriptor: int) -> None:
        metadata = os.fstat(descriptor)
        if stat.S_ISDIR(metadata.st_mode):
            synced_directories.append((metadata.st_dev, metadata.st_ino))
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", observed_fsync)

    build_listening_master(
        source,
        output_path=output,
        report_path=report,
        ffmpeg_path=fake,
    )

    output_identity = (output_parent.stat().st_dev, output_parent.stat().st_ino)
    report_identity = (report_parent.stat().st_dev, report_parent.stat().st_ino)
    assert synced_directories.count(output_identity) == 1
    assert synced_directories.count(report_identity) == 1


def test_build_listening_master_fails_closed_if_ffmpeg_path_is_replaced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "balanced-control.wav"
    output = tmp_path / "listening-master.wav"
    report = tmp_path / "listening-master.json"
    fake = tmp_path / "ffmpeg"
    displaced = tmp_path / "ffmpeg-original"
    _source_wav(source)
    _fake_ffmpeg(fake)
    original_run = listening_master.subprocess.run
    attacked = False

    def replace_during_pass(*args: object, **kwargs: object) -> object:
        nonlocal attacked
        if not attacked:
            attacked = True
            fake.rename(displaced)
            fake.write_bytes(displaced.read_bytes())
            fake.chmod(0o700)
        return original_run(*args, **kwargs)

    monkeypatch.setattr(
        listening_master.subprocess,
        "run",
        replace_during_pass,
    )

    with pytest.raises(RuntimeError, match="FFmpeg executable changed identity"):
        build_listening_master(
            source,
            output_path=output,
            report_path=report,
            ffmpeg_path=fake,
        )

    assert attacked is True
    assert not output.exists()
    assert not report.exists()


def test_build_listening_master_reverifies_ffmpeg_before_and_after_all_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "balanced-control.wav"
    output = tmp_path / "listening-master.wav"
    report = tmp_path / "listening-master.json"
    fake = tmp_path / "ffmpeg"
    _source_wav(source)
    _fake_ffmpeg(fake)
    original_require = listening_master._require_pinned_ffmpeg
    observations = 0

    def observed_require(executable: object) -> None:
        nonlocal observations
        assert isinstance(executable, listening_master._PinnedExecutable)
        observations += 1
        original_require(executable)

    monkeypatch.setattr(
        listening_master,
        "_require_pinned_ffmpeg",
        observed_require,
    )

    build_listening_master(
        source,
        output_path=output,
        report_path=report,
        ffmpeg_path=fake,
    )

    # One admission check plus before/after checks for version, filters,
    # source analysis, render, and encoded-artifact verification.
    assert observations == 11


def test_build_listening_master_private_modes_exist_before_render_and_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "balanced-control.wav"
    output = tmp_path / "listening-master.wav"
    report = tmp_path / "listening-master.json"
    fake = tmp_path / "ffmpeg"
    _source_wav(source)
    _fake_ffmpeg(fake, require_private_audio=True)
    observed: list[tuple[str, int, int]] = []
    original_publish = listening_master._publish_private_file

    def inspected_publish(
        private_file: object,
        *,
        destination_parent_fd: int,
        destination_name: str,
    ) -> None:
        assert isinstance(private_file, listening_master._PrivateFile)
        observed.append(
            (
                private_file.name,
                stat.S_IMODE(os.fstat(private_file.fd).st_mode),
                stat.S_IMODE(os.fstat(private_file.directory.fd).st_mode),
            )
        )
        original_publish(
            private_file,
            destination_parent_fd=destination_parent_fd,
            destination_name=destination_name,
        )

    monkeypatch.setattr(
        listening_master,
        "_publish_private_file",
        inspected_publish,
    )

    build_listening_master(
        source,
        output_path=output,
        report_path=report,
        ffmpeg_path=fake,
    )

    assert {Path(name).suffix for name, _file_mode, _dir_mode in observed} == {
        ".wav",
        ".json",
    }
    assert all(file_mode == 0o600 for _name, file_mode, _dir_mode in observed)
    assert all(dir_mode == 0o700 for _name, _file_mode, dir_mode in observed)


def test_build_listening_master_does_not_hash_or_delete_replaced_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "balanced-control.wav"
    output = tmp_path / "listening-master.wav"
    report = tmp_path / "listening-master.json"
    fake = tmp_path / "ffmpeg"
    _source_wav(source)
    _fake_ffmpeg(fake)
    original_require = listening_master._require_private_file_identity
    attacked = False
    hashed_names: list[str] = []
    original_record = listening_master._file_record_fd

    def replace_before_validation(private_file: object) -> None:
        nonlocal attacked
        assert isinstance(private_file, listening_master._PrivateFile)
        if private_file.name.endswith(".tmp.wav") and not attacked:
            attacked = True
            os.unlink(private_file.name, dir_fd=private_file.directory.fd)
            competitor = os.open(
                private_file.name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=private_file.directory.fd,
            )
            os.write(competitor, b"competitor-render")
            os.close(competitor)
        original_require(private_file)

    def record_name(private_file: object) -> dict[str, object]:
        assert isinstance(private_file, listening_master._PrivateFile)
        hashed_names.append(private_file.name)
        return original_record(private_file)

    monkeypatch.setattr(
        listening_master,
        "_require_private_file_identity",
        replace_before_validation,
    )
    monkeypatch.setattr(listening_master, "_file_record_fd", record_name)

    with pytest.raises(RuntimeError, match="changed identity"):
        build_listening_master(
            source,
            output_path=output,
            report_path=report,
            ffmpeg_path=fake,
        )

    assert attacked is True
    assert not any(name.endswith(".tmp.wav") for name in hashed_names)
    assert not output.exists()
    assert not report.exists()
    workspaces = [path for path in tmp_path.iterdir() if path.name.endswith(".private")]
    assert len(workspaces) == 1
    competitors = list(workspaces[0].iterdir())
    assert len(competitors) == 1
    assert competitors[0].read_bytes() == b"competitor-render"
    competitors[0].unlink()
    workspaces[0].rmdir()


def test_build_listening_master_does_not_delete_replaced_publish_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "balanced-control.wav"
    output = tmp_path / "listening-master.wav"
    report = tmp_path / "listening-master.json"
    fake = tmp_path / "ffmpeg"
    _source_wav(source)
    _fake_ffmpeg(fake)
    original_link = os.link

    def replace_after_link(
        source_path: object,
        destination_path: object,
        **kwargs: object,
    ) -> None:
        original_link(source_path, destination_path, **kwargs)
        if destination_path == output.name:
            destination_fd = int(kwargs["dst_dir_fd"])
            os.unlink(output.name, dir_fd=destination_fd)
            competitor = os.open(
                output.name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o640,
                dir_fd=destination_fd,
            )
            os.write(competitor, b"competitor-output")
            os.close(competitor)

    monkeypatch.setattr(os, "link", replace_after_link)

    with pytest.raises(RuntimeError, match="changed identity"):
        build_listening_master(
            source,
            output_path=output,
            report_path=report,
            ffmpeg_path=fake,
        )

    assert output.read_bytes() == b"competitor-output"
    assert stat.S_IMODE(output.stat().st_mode) == 0o640
    assert not report.exists()
