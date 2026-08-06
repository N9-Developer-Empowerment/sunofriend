from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
import subprocess
from typing import Any
import wave
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from sunofriend.separation_demucs_mlx_worker import (
    PCM24_SCALE,
    _configured_segment_seconds,
    decode_pcm24,
    persist_core_four,
)
from sunofriend.separation_alpha import (
    _run_worker,
    _validate_core_four_worker_evidence,
    resolve_profile,
    separation_doctor,
)
from sunofriend.separation_profiles import (
    CORE_FOUR_FALLBACK_PROFILE_ID,
    CORE_FOUR_PROFILE_ID,
    DEMUCS_INFER_CHALLENGER_ID,
    PROFILE_STATUSES,
    SCNET_CANDIDATE_PROFILE_ID,
    SCNET_RELEASE_PROFILE_ID,
    profile_for_scope,
    separation_profile,
    separation_profile_registry,
)


ROOT = Path(__file__).resolve().parents[1]


def _write_executable(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\nset -eu\n" + body, encoding="utf-8")
    path.chmod(0o755)


def _fake_setup_environment(
    tmp_path: Path, *, hash_verification_succeeds: bool
) -> tuple[dict[str, str], Path]:
    tools = tmp_path / "fake-tools"
    tools.mkdir()
    download_log = tmp_path / "download.log"
    _write_executable(
        tools / "uname",
        'case "$1" in\n  -s) echo Darwin ;;\n  -m) echo arm64 ;;\n  *) exit 2 ;;\nesac\n',
    )
    _write_executable(tools / "xcode-select", 'echo "/fake/command-line-tools"\n')
    _write_executable(
        tools / "curl",
        f'''target=\nurl=\nwhile [ "$#" -gt 0 ]; do
    case "$1" in
        --output) shift; target=$1 ;;
        http*) url=$1 ;;
    esac
    shift
done
case "$url" in
    *htdemucs.safetensors) bytes=168005865 ;;
    *htdemucs_config.json) bytes=1892 ;;
    *README.md) bytes=3971 ;;
    *LICENSE) bytes=1117 ;;
    *pyproject.toml) bytes=1672 ;;
    *) exit 2 ;;
esac
echo "$url" >> "{download_log}"
/bin/dd if=/dev/zero of="$target" bs=1 count=0 seek="$bytes" 2>/dev/null
''',
    )
    _write_executable(
        tools / "shasum",
        "exit 0\n" if hash_verification_succeeds else "exit 1\n",
    )
    fake_python = tools / "python3.12"
    _write_executable(
        fake_python,
        '''if [ "${1:-}" = "-c" ]; then
    case "$2" in
        *sys.version_info*) echo 3.12 ;;
    esac
    exit 0
fi
if [ "${1:-}" = "-m" ] && [ "${2:-}" = "venv" ]; then
    /bin/mkdir -p "$3/bin"
    /bin/cp "$0" "$3/bin/python"
    /bin/chmod 0755 "$3/bin/python"
    exit 0
fi
exit 0
''',
    )
    environment = {
        **os.environ,
        "PATH": f"{tools}:/usr/bin:/bin",
        "SUNOFRIEND_SEPARATION_ROOT": str(tmp_path / "data"),
        "SUNOFRIEND_SEPARATION_PYTHON_BIN": str(fake_python),
    }
    return environment, download_log


def _fake_fallback_setup_environment(
    tmp_path: Path,
) -> tuple[dict[str, str], Path]:
    tools = tmp_path / "fake-fallback-tools"
    tools.mkdir()
    download_log = tmp_path / "fallback-download.log"
    _write_executable(
        tools / "uname",
        'case "$1" in\n  -s) echo Darwin ;;\n  -m) echo arm64 ;;\n  *) exit 2 ;;\nesac\n',
    )
    _write_executable(
        tools / "curl",
        f'''target=
url=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --output) shift; target=$1 ;;
        http*) url=$1 ;;
    esac
    shift
done
case "$url" in
    *955717e8-8726e21a.th) bytes=84141911 ;;
    *htdemucs.yaml) bytes=21 ;;
    *LICENSE) bytes=1400 ;;
    *README.md) bytes=23660 ;;
    *pyproject.toml) bytes=3560 ;;
    *checkpoints_provenance.json) bytes=7467 ;;
    *) exit 2 ;;
esac
echo "$url" >> "{download_log}"
/bin/dd if=/dev/zero of="$target" bs=1 count=0 seek="$bytes" 2>/dev/null
''',
    )
    _write_executable(tools / "shasum", "exit 0\n")
    fake_python = tools / "python3.13"
    _write_executable(
        fake_python,
        '''if [ "${1:-}" = "-c" ]; then
    case "$2" in
        *sys.version_info*) echo 3.13 ;;
    esac
    exit 0
fi
if [ "${1:-}" = "-m" ] && [ "${2:-}" = "venv" ]; then
    /bin/mkdir -p "$3/bin"
    /bin/cp "$0" "$3/bin/python"
    /bin/chmod 0755 "$3/bin/python"
    exit 0
fi
exit 0
''',
    )
    environment = {
        **os.environ,
        "PATH": f"{tools}:/usr/bin:/bin",
        "SUNOFRIEND_SEPARATION_ROOT": str(tmp_path / "fallback-data"),
        "SUNOFRIEND_SEPARATION_PYTHON_BIN": str(fake_python),
    }
    return environment, download_log


def _valid_core_worker_document(spec: Any) -> dict[str, Any]:
    frames = 2_646_000
    output_roles = {
        *spec.supported_roles,
        "source_reference",
        "reconstruction_check",
    }
    return {
        "schema": "sunofriend.experimental-core-four-worker.v1",
        "status": "complete_unreviewed",
        "profile_id": spec.profile_id,
        "roles": list(spec.supported_roles),
        "sample_rate": 44_100,
        "channels": 2,
        "frames": frames,
        "duration_seconds": 60.0,
        "inference": dict(spec.inference_settings),
        "runtime": {
            "backend": spec.backend,
            "source_revision": spec.runtime_source_revision,
            "wheel_sha256": spec.runtime_wheel_sha256,
            "packages": dict(spec.packages()),
            "system": "Darwin",
            "machine": "arm64",
            "device": "mlx-gpu",
            "pytorch_present": False,
            "network_denial_enforced": True,
            "network_used": False,
        },
        "model": {
            "model_id": spec.model_id,
            "weights_sha256": spec.artifact("weights").sha256,
            "config_sha256": spec.artifact("config").sha256,
            "model_revision": spec.model_revision,
            "source_order": ["drums", "bass", "other", "vocals"],
            "segment_config_value": "39/5",
            "auto_convert": False,
            "named_or_network_model_resolution": False,
        },
        "native_other_correction": {
            "rms": 0.1,
            "peak": 0.2,
            "used_for_separation_accuracy_claim": False,
        },
        "additive_accounting": {
            "passed": True,
            "maximum_absolute_error_lsb": 0,
        },
        "resources": {"peak_unified_memory_bytes": 8 * 1024**3},
        "elapsed_seconds": 60.0,
        "source_unchanged": True,
        "model_artifacts_unchanged": True,
        "outputs": {
            role: {
                "frames": frames,
                "channels": 2,
                "sample_rate": 44_100,
                "sample_width_bytes": 3,
            }
            for role in output_roles
        },
    }


def _valid_fallback_worker_document(spec: Any) -> dict[str, Any]:
    document = _valid_core_worker_document(spec)
    document["runtime"].update({"device": "cpu", "pytorch_present": True})
    document["model"].pop("segment_config_value")
    document["model"].pop("auto_convert")
    document["model"].update(
        {
            "native_segments": [7.8],
            "segment_verified_numeric": True,
            "segment_override": None,
            "explicit_local_repo": True,
        }
    )
    return document


def test_core_four_profile_is_immutable_and_exact() -> None:
    profile = separation_profile(CORE_FOUR_PROFILE_ID)

    assert profile.status == "blocked"
    assert profile.target_release_tier == "public_opt_in"
    assert profile.supported_roles == ("vocals", "drums", "bass", "other")
    assert profile.packages() == {
        "demucs-mlx": "1.4.4",
        "mlx": "0.31.2",
        "mlx-metal": "0.31.2",
        "mlx-audio-io": "1.3.11",
        "mlx-spectro": "0.7.0",
        "numpy": "2.3.5",
        "packaging": "25.0",
        "tqdm": "4.67.1",
        "safetensors": "0.6.2",
    }
    assert profile.artifact("weights").sha256 == (
        "339d267a7a6983a11eedbdc00413c602a65e9b9103f695fb5c2b2a481cd9d297"
    )
    assert profile.runtime_wheel_sha256 == (
        "dc40828b0a8591720082d2494696249790573d4ff6e5be72b16594e131b23e64"
    )
    assert dict(profile.inference_settings) == {
        "model": "htdemucs",
        "shifts": 1,
        "seed": 0,
        "overlap": 0.25,
        "batch_size": 1,
        "writer_count": 1,
        "segment_seconds": 7.8,
        "segment_source": "pinned_config_fraction_39_over_5",
        "auto_convert": False,
    }
    with pytest.raises(FrozenInstanceError):
        profile.status = "public_opt_in"  # type: ignore[misc]
    with pytest.raises(TypeError):
        profile.packages()["mlx"] = "changed"  # type: ignore[index]


def test_pinned_fractional_segment_is_parsed_numerically(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"kwargs": {"segment": "39/5"}}))

    assert _configured_segment_seconds(config) == 7.8

    config.write_text(json.dumps({"kwargs": {"segment": "7.8"}}))
    with pytest.raises(ValueError, match="configuration differs"):
        _configured_segment_seconds(config)


def test_registry_has_only_declared_statuses_and_keeps_challenger_blocked() -> None:
    document = separation_profile_registry()
    profiles = {item["profile_id"]: item for item in document["profiles"]}

    assert all(item["status"] in PROFILE_STATUSES for item in profiles.values())
    assert profiles[DEMUCS_INFER_CHALLENGER_ID]["status"] == "blocked"
    assert (
        profiles[DEMUCS_INFER_CHALLENGER_ID]["target_release_tier"]
        == "studio_challenger"
    )
    assert document["policy"]["subjective_feedback_blocks_preview"] is False


def test_fallback_profile_is_exact_blocked_and_superseded_for_core_four() -> None:
    profile = separation_profile(CORE_FOUR_FALLBACK_PROFILE_ID)

    assert profile.status == "blocked"
    assert profile.target_release_tier == "public_opt_in"
    assert profile.selection_priority > separation_profile(
        CORE_FOUR_PROFILE_ID
    ).selection_priority
    assert profile.selection_priority < separation_profile(
        SCNET_RELEASE_PROFILE_ID
    ).selection_priority
    assert profile_for_scope("core-four-stems-v1").profile_id == (
        SCNET_RELEASE_PROFILE_ID
    )
    assert profile.packages()["demucs-infer"] == "4.2.2"
    assert profile.packages()["torch"] == "2.8.0"
    assert profile.packages()["torchaudio"] == "2.8.0"
    assert profile.packages()["setuptools"] == "83.0.0"
    assert len(profile.packages()) == 20
    assert profile.artifact("weights").sha256 == (
        "8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4"
    )
    assert profile.artifact("weights").bytes == 84_141_911
    assert dict(profile.inference_settings) == {
        "model": "htdemucs",
        "signature": "955717e8",
        "shifts": 1,
        "seed": 0,
        "overlap": 0.25,
        "batch_size": 1,
        "writer_count": 1,
        "segment": "native_fraction_39_over_5_rejected",
        "device": "cpu",
        "explicit_local_repo": True,
    }


def test_scnet_candidate_is_exact_visible_and_cannot_replace_release() -> None:
    candidate = separation_profile(SCNET_CANDIDATE_PROFILE_ID)

    assert candidate.status == "blocked"
    assert candidate.target_release_tier == "public_opt_in"
    assert candidate.backend == "scnet-official-source-adapter"
    assert len(candidate.packages()) == 12
    assert candidate.packages()["torch"] == "2.8.0"
    assert candidate.artifact("weights").bytes == 168_848_417
    assert candidate.artifact("weights").sha256 == (
        "719e5abb8ed920305dad546ac3cd6fb0b1e9c3092d14ce21827bfc0423af3070"
    )
    assert candidate.artifact("config").bytes == 1_080
    assert candidate.artifact("config").sha256 == (
        "629a4901184bf1d3a75b0b13904f35974785aa042cad3c010fd576248cdce3f0"
    )
    assert candidate.selection_priority < separation_profile(
        CORE_FOUR_FALLBACK_PROFILE_ID
    ).selection_priority
    assert candidate.selection_priority < separation_profile(
        SCNET_RELEASE_PROFILE_ID
    ).selection_priority
    assert profile_for_scope("core-four-stems-v1").profile_id == (
        SCNET_RELEASE_PROFILE_ID
    )


def test_scnet_release_profile_preserves_candidate_immutability() -> None:
    exploratory = separation_profile(SCNET_CANDIDATE_PROFILE_ID)
    release = separation_profile(SCNET_RELEASE_PROFILE_ID)

    assert exploratory.runtime_source_revision == (
        "5d95bf96b19c3eede63248d171efeca8e3abb948"
    )
    assert release.profile_id == "scnet-large-musdb-release-v1"
    assert release.runtime_source_revision == (
        "6236f8c559778dc271e1aea9baa3993ae655e905"
    )
    assert release.setup_script == (
        "scripts/setup-separation-core-four-scnet-macos.sh"
    )
    assert release.worker_script == "src/sunofriend/separation_scnet_worker.py"
    assert release.artifact("architecture_source").sha256 == (
        "5e77c363f7f0187432a984d8ae1aa511826295d732372f0c280e68e4fecd4550"
    )
    assert release.artifact("weights").sha256 == (
        exploratory.artifact("weights").sha256
    )
    assert release.status == "public_opt_in"
    assert release.blockers == ()
    assert profile_for_scope("core-four-stems-v1").profile_id == (
        SCNET_RELEASE_PROFILE_ID
    )


def test_scnet_proposed_runtime_lock_is_exact_and_install_free() -> None:
    text = (
        ROOT / "separation-core-four-scnet-runtime-requirements.txt"
    ).read_text()

    assert text.count("==") == 12
    assert text.count("--hash=sha256:") == 12
    assert text.startswith("--only-binary=:all:\n")
    assert "torch==2.8.0" in text
    assert "accelerate==" not in text
    assert "torchaudio==" not in text


def test_fallback_requirements_pin_the_resolved_apple_arm_closure() -> None:
    text = (
        ROOT / "separation-core-four-fallback-runtime-requirements.txt"
    ).read_text()

    assert text.count("==") == 20
    assert text.count("--hash=sha256:") == 20
    for requirement in (
        "demucs-infer==4.2.2",
        "torch==2.8.0",
        "torchaudio==2.8.0",
        "numpy==2.5.1",
        "setuptools==83.0.0",
        "soundfile==0.14.0",
    ):
        assert text.count(requirement) == 1


def test_core_four_requirements_pin_every_runtime_dependency_and_hash() -> None:
    text = (ROOT / "separation-core-four-runtime-requirements.txt").read_text()
    for requirement in (
        "demucs-mlx==1.4.4",
        "mlx==0.31.2",
        "mlx-metal==0.31.2",
        "mlx-audio-io==1.3.11",
        "mlx-spectro==0.7.0",
        "numpy==2.3.5",
        "packaging==25.0",
        "tqdm==4.67.1",
        "safetensors==0.6.2",
    ):
        assert text.count(requirement) == 1
    assert "dc40828b0a8591720082d2494696249790573d4ff6e5be72b16594e131b23e64" in text
    assert "--no-binary=mlx-audio-io" in text
    assert "torch" not in text.casefold()


def test_setup_plan_is_read_only_and_install_requires_explicit_terms(tmp_path: Path) -> None:
    script = ROOT / "scripts/setup-separation-core-four-macos.sh"
    environment = {
        **os.environ,
        "SUNOFRIEND_SEPARATION_ROOT": str(tmp_path / "data"),
    }
    planned = subprocess.run(
        [str(script), "--plan"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    refused = subprocess.run(
        [str(script), "--install"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert planned.returncode == 0
    assert "nothing was installed or downloaded" in planned.stdout
    assert refused.returncode == 2
    assert "Refusing a new install" in refused.stderr
    assert "objective remediation budget is exhausted" in planned.stdout
    assert not (tmp_path / "data").exists()


def test_fallback_setup_plan_is_read_only_and_reports_exhausted_failure(
    tmp_path: Path,
) -> None:
    script = ROOT / "scripts/setup-separation-core-four-fallback-macos.sh"
    environment = {
        **os.environ,
        "SUNOFRIEND_SEPARATION_ROOT": str(tmp_path / "data"),
    }

    planned = subprocess.run(
        [str(script), "--plan"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    refused = subprocess.run(
        [str(script), "--install"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert planned.returncode == 0
    assert "nothing was installed or downloaded" in planned.stdout
    assert "20 exact Apple-arm64/Python 3.13 wheels" in planned.stdout
    assert "setuptools 83.0.0, MIT, 1008090-byte wheel" in planned.stdout
    assert "one fallback remediation" in planned.stdout
    assert "no separate model-specific licence file" in planned.stdout
    assert refused.returncode == 2
    assert "objectively failed demucs-infer fallback" in refused.stderr
    assert not (tmp_path / "data").exists()


def test_fallback_setup_refuses_new_install_after_objective_failure(
    tmp_path: Path,
) -> None:
    script = ROOT / "scripts/setup-separation-core-four-fallback-macos.sh"
    environment, download_log = _fake_fallback_setup_environment(tmp_path)

    installed = subprocess.run(
        [str(script), "--install", "--accept-model-terms"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert installed.returncode == 2
    assert "objectively failed demucs-infer fallback" in installed.stderr
    assert not (tmp_path / "fallback-data").exists()
    assert not download_log.exists()


def test_explicit_setup_is_disabled_after_objective_remediation_is_exhausted(
    tmp_path: Path,
) -> None:
    script = ROOT / "scripts/setup-separation-core-four-macos.sh"
    environment, download_log = _fake_setup_environment(
        tmp_path, hash_verification_succeeds=True
    )

    installed = subprocess.run(
        [str(script), "--install", "--accept-model-terms"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert installed.returncode == 2
    assert "objectively failed demucs-mlx baseline" in installed.stderr
    assert not (tmp_path / "data/demucs-mlx-htdemucs-v1").exists()
    assert not download_log.exists()
    assert not list((tmp_path / "data").glob(".core-four.building.*"))


def test_disabled_setup_does_not_reach_hash_verification(
    tmp_path: Path,
) -> None:
    script = ROOT / "scripts/setup-separation-core-four-macos.sh"
    environment, download_log = _fake_setup_environment(
        tmp_path, hash_verification_succeeds=False
    )

    failed = subprocess.run(
        [str(script), "--install", "--accept-model-terms"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert failed.returncode != 0
    assert "objectively failed demucs-mlx baseline" in failed.stderr
    assert not download_log.exists()
    assert not (tmp_path / "data/demucs-mlx-htdemucs-v1").exists()
    assert not list((tmp_path / "data").glob(".core-four.building.*"))


def test_core_worker_launch_is_network_denied_and_identity_bound(tmp_path: Path) -> None:
    profile = resolve_profile(
        root=tmp_path,
        runtime_python=tmp_path / "runtime/bin/python",
        model_root=tmp_path / "profile",
        profile_id=CORE_FOUR_PROFILE_ID,
    )
    spec = separation_profile(CORE_FOUR_PROFILE_ID)
    plan = SimpleNamespace(profile=profile, probe=SimpleNamespace(duration_seconds=60.0))
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        captured["kwargs"] = kwargs
        document = _valid_core_worker_document(spec)
        (tmp_path / "worker-result.json").write_text(json.dumps(document))

    with patch("sunofriend.separation_alpha._run_command", side_effect=fake_run):
        result = _run_worker(plan, tmp_path)

    assert result["profile_id"] == CORE_FOUR_PROFILE_ID
    assert captured["command"][:3] == [
        "/usr/bin/sandbox-exec",
        "-p",
        "(version 1)(deny network*)(allow default)",
    ]
    assert "separation_demucs_mlx_worker.py" in " ".join(captured["command"])
    assert "--network-denial-enforced" in captured["command"]
    assert captured["kwargs"]["timeout"] == 120.0
    assert captured["kwargs"]["env"]["PIP_NO_INDEX"] == "1"


def test_core_worker_evidence_rejects_a_persisted_clock_mismatch(
    tmp_path: Path,
) -> None:
    profile = resolve_profile(
        root=tmp_path,
        runtime_python=tmp_path / "runtime/bin/python",
        model_root=tmp_path / "profile",
        profile_id=CORE_FOUR_PROFILE_ID,
    )
    spec = separation_profile(CORE_FOUR_PROFILE_ID)
    plan = SimpleNamespace(profile=profile, probe=SimpleNamespace(duration_seconds=60.0))
    worker = _valid_core_worker_document(spec)
    worker["outputs"]["bass"]["sample_rate"] = 48_000

    with pytest.raises(RuntimeError, match="persisted output clock contract"):
        _validate_core_four_worker_evidence(worker, plan=plan)


def test_fallback_worker_launch_and_evidence_are_local_repo_bound(
    tmp_path: Path,
) -> None:
    profile = resolve_profile(
        root=tmp_path,
        runtime_python=tmp_path / "runtime/bin/python",
        model_root=tmp_path / "profile",
        profile_id=CORE_FOUR_FALLBACK_PROFILE_ID,
    )
    spec = separation_profile(CORE_FOUR_FALLBACK_PROFILE_ID)
    plan = SimpleNamespace(profile=profile, probe=SimpleNamespace(duration_seconds=60.0))
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        captured["kwargs"] = kwargs
        (tmp_path / "worker-result.json").write_text(
            json.dumps(_valid_fallback_worker_document(spec))
        )

    with patch("sunofriend.separation_alpha._run_command", side_effect=fake_run):
        result = _run_worker(plan, tmp_path)

    assert result["profile_id"] == CORE_FOUR_FALLBACK_PROFILE_ID
    assert "separation_demucs_infer_worker.py" in " ".join(captured["command"])
    assert "--network-denial-enforced" in captured["command"]
    assert captured["kwargs"]["env"]["PIP_NO_INDEX"] == "1"


def test_only_the_16_gib_benchmark_class_is_marked_verified(tmp_path: Path) -> None:
    profile = resolve_profile(
        root=tmp_path,
        runtime_python=tmp_path / "missing-python",
        model_root=tmp_path / "missing-profile",
        profile_id=CORE_FOUR_PROFILE_ID,
    )
    with patch(
        "sunofriend.separation_alpha._system_memory_bytes",
        return_value=36 * 1024**3,
    ):
        result = separation_doctor(profile)

    machine = result["checks"]["machine_class"]
    assert machine["verified_16_gib_class"] is False
    assert machine["benchmark_memory_bytes"] == 16 * 1024**3
    assert "accessible but unverified" in machine["warning"]


def test_pcm24_persistence_makes_other_the_disclosed_exact_complement(
    tmp_path: Path,
) -> None:
    frames = 2_048
    time = np.arange(frames, dtype=np.float32) / 44_100
    source = np.column_stack(
        (
            0.4 * np.sin(2 * np.pi * 220 * time),
            0.35 * np.sin(2 * np.pi * 330 * time),
        )
    ).astype(np.float32)
    estimates = {
        "vocals": source * 0.31,
        "drums": source * 0.17,
        "bass": source * 0.13,
        "other": source * 0.25,
    }

    result = persist_core_four(source, estimates, tmp_path, np=np)

    assert set(result["outputs"]) == {
        "source_reference",
        "vocals",
        "drums",
        "bass",
        "other",
        "reconstruction_check",
    }
    assert result["additive_accounting"] == {
        "equation": "source_reference = vocals + drums + bass + other in PCM24",
        "maximum_absolute_error_lsb": 0,
        "tolerance_lsb": 2,
        "passed": True,
    }
    assert result["native_other_correction"]["rms"] > 0
    assert result["native_other_correction"]["used_for_separation_accuracy_claim"] is False

    arrays = {}
    for role in result["outputs"]:
        relative = {
            "source_reference": "SOURCE/source-reference.wav",
            "vocals": "STEMS/vocals.wav",
            "drums": "STEMS/drums.wav",
            "bass": "STEMS/bass.wav",
            "other": "STEMS/other.wav",
            "reconstruction_check": "AUDIO/reconstruction-check.wav",
        }[role]
        with wave.open(str(tmp_path / relative), "rb") as reader:
            arrays[role] = np.rint(
                decode_pcm24(reader.readframes(reader.getnframes()), np=np)
                * PCM24_SCALE
            ).astype(np.int64)
    reconstructed = sum(arrays[role] for role in ("vocals", "drums", "bass", "other"))
    assert np.array_equal(reconstructed, arrays["source_reference"])
    assert np.array_equal(arrays["reconstruction_check"], arrays["source_reference"])


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda values: values.pop("bass"), "roles differ"),
        (lambda values: values.__setitem__("extra", values["bass"]), "roles differ"),
        (
            lambda values: values["vocals"].__setitem__((0, 0), np.nan),
            "samples differ",
        ),
    ],
)
def test_core_four_persistence_rejects_broken_worker_roles(
    tmp_path: Path, mutation: Any, match: str
) -> None:
    source = np.full((128, 2), 0.2, dtype=np.float32)
    estimates = {role: source * 0.2 for role in ("drums", "bass", "other", "vocals")}
    mutation(estimates)

    with pytest.raises(ValueError, match=match):
        persist_core_four(source, estimates, tmp_path, np=np)
