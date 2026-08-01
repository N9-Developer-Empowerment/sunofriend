from __future__ import annotations

import hashlib
import importlib.util
import json
import stat
import subprocess
from pathlib import Path

import numpy as np
import pytest

import sunofriend._separation_melroformer_authorised_worker as worker
from sunofriend._separation_checkpoint_canonical import plain
from sunofriend._separation_melroformer_pcm24_quarantine import (
    _materialize_private_melroformer_pcm24_quarantine,
)
from sunofriend._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS
from sunofriend.separation_contract import _canonical_json_bytes


def test_parent_binds_authorised_worker_denials_and_pcm24(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    runtime = tmp_path / "python"
    source_root = tmp_path / "source"
    checkpoint = tmp_path / "model.safetensors"
    companions = tmp_path / "companions"
    report = tmp_path / "report.json"
    for path in (runtime, checkpoint, report):
        path.write_bytes(b"fixture")
    source_root.mkdir()
    companions.mkdir()

    source, vocals, instrumental = _arrays()
    authorisation = {
        "schema": "sunofriend.private-melroformer-authorised-input.v1",
        "track_id": "owned-example",
        "track_title": "Owned example",
        "report_sha256": "a" * 64,
        "audio_sha256": "b" * 64,
        "source_start_seconds": 0.0,
        "source_end_seconds": len(source) / 44_100,
        "sample_rate": 44_100,
        "channels": 2,
        "frames": len(source),
        "rights_authority": "creator_and_copyright_holder",
        "evidence_scope": "private_development_only",
        "audio_persisted_by_bridge": False,
    }
    artifacts = {
        "provider": _identity("provider"),
        "runtime": _identity("runtime"),
        "worker": _identity("worker"),
        "checkpoint": {
            **_identity("checkpoint"),
            "bytes": CONVERSION_CHECKPOINT_BYTES,
            "sha256": CONVERSION_CHECKPOINT_SHA256,
        },
        "source": {"status": "verified_not_imported"},
        "companions": {
            "LICENSE": {"bytes": 10, "sha256": "c" * 64},
            "config.json": {"bytes": 10, "sha256": "d" * 64},
        },
    }
    monkeypatch.setattr(worker.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(worker, "_observe_artifacts", lambda **_: artifacts)
    monkeypatch.setattr(
        worker,
        "_load_private_authorised_excerpt_pcm24",
        lambda *_, **__: (source, authorisation),
    )

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        output = Path(command[command.index("--destination") + 1])
        quarantine = _materialize_private_melroformer_pcm24_quarantine(
            destination=output,
            source=source,
            vocals=vocals,
            instrumental=instrumental,
            np=np,
        )
        child = {
            "schema": worker.CHILD_SCHEMA,
            "status": "complete",
            "canaries": {
                "network_connect_ex": 1,
                "network_errno_name": "EPERM",
                "process_fork_errno": 1,
                "process_fork_errno_name": "EPERM",
                "outside_write_errno": 1,
                "outside_write_errno_name": "EPERM",
            },
            "model": {
                "authorisation": authorisation,
                "bridge": {
                    "candidate_id": "mlx-melroformer-kim-vocal-2",
                    "runtime": {"mlx_device": "gpu"},
                    "checkpoint": {
                        "bytes": CONVERSION_CHECKPOINT_BYTES,
                        "sha256": CONVERSION_CHECKPOINT_SHA256,
                        "static_tensor_count": 708,
                    },
                    "source": {
                        "manifest_sha256": worker.SOURCE_MANIFEST_SHA256,
                        "upstream_from_pretrained_called": False,
                    },
                    "weight_coverage": {"complete": True},
                },
                "inference": {
                    "status": "private_real_single_chunk_validated_not_persisted",
                    "geometry": {"frames": len(source)},
                    "transport": {"chunk_count": 1},
                    "measurement": {
                        "inference_seconds": 1.0,
                        "peak_memory_bytes": 1_000,
                    },
                    "outputs": {
                        "vocals": {"sha256": "e" * 64},
                        "instrumental": {"sha256": "f" * 64},
                    },
                    "additive_accounting": {
                        "passed": True,
                        "maximum_absolute_error": 0.0,
                    },
                },
            },
            "quarantine": plain(quarantine),
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(child), "")

    monkeypatch.setattr(worker.subprocess, "run", fake_run)
    evidence = worker._run_private_melroformer_authorised_worker(
        repository_root=repository,
        runtime_path=runtime,
        source_root=source_root,
        checkpoint_path=checkpoint,
        companion_root=companions,
        authorisation_report_path=report,
        expected_authorisation_report_sha256="a" * 64,
        staging_directory=tmp_path / "staging",
    )

    assert evidence["status"] == "authorised_model_worker_complete_parent_verified"
    assert evidence["conclusion"]["network_denial_bound_to_model_worker"] is True
    assert evidence["conclusion"]["pcm24_quarantine_bound_to_model_worker"] is True
    assert evidence["quarantine"]["evidence_identical"] is True
    assert all(value is False for value in evidence["permissions"].values())
    assert "/Users/" not in repr(evidence)

    resigned = plain(evidence)
    resigned["permissions"]["publication_permitted"] = True
    unsigned = dict(resigned)
    unsigned.pop("evidence_sha256")
    resigned["evidence_sha256"] = hashlib.sha256(
        _canonical_json_bytes(unsigned)
    ).hexdigest()
    with pytest.raises(ValueError, match="grants a product permission"):
        worker._validate_private_melroformer_authorised_worker(resigned)


def test_authorised_worker_has_no_public_route() -> None:
    assert "private-melroformer-authorised-worker" not in PUBLIC_COMMANDS
    assert "private-melroformer-authorised-worker" not in DIRECT_TUI_COMMANDS


def test_authorised_worker_script_persists_exclusive_owner_only_observation(
    tmp_path: Path,
) -> None:
    script = (
        Path(__file__).parents[1]
        / "scripts"
        / "private-melroformer-authorised-worker.py"
    )
    specification = importlib.util.spec_from_file_location(
        "private_melroformer_authorised_worker_script",
        script,
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    observation = tmp_path / "authorised-worker-observation.json"

    module._write_private_observation(observation, {"status": "fixture"})

    assert stat.S_IMODE(observation.stat().st_mode) == 0o600
    assert json.loads(observation.read_text(encoding="utf-8")) == {
        "status": "fixture"
    }
    with pytest.raises(FileExistsError):
        module._write_private_observation(observation, {"status": "replaced"})


def _arrays() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    timeline = np.arange(4_096, dtype=np.float32) / np.float32(44_100.0)
    source = np.stack(
        [
            0.2 * np.sin(2 * np.pi * 220 * timeline),
            0.2 * np.sin(2 * np.pi * 330 * timeline),
        ],
        axis=1,
    ).astype(np.float32)
    vocals = (source * np.float32(0.4)).astype(np.float32)
    return source, vocals, (source - vocals).astype(np.float32)


def _identity(label: str) -> dict[str, object]:
    return {
        "resolved_path": f"/{label}",
        "bytes": len(label),
        "sha256": hashlib.sha256(label.encode()).hexdigest(),
    }
