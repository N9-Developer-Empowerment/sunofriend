from __future__ import annotations

import hashlib
import importlib.util
import json
import stat
import subprocess
import types
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import numpy as np
import pytest

import sunofriend._separation_melroformer_authorised_worker as worker
import sunofriend._separation_macos_sandbox_network_observer as network_observer
from sunofriend._separation_checkpoint_canonical import plain
from sunofriend._separation_melroformer_pcm24_quarantine import (
    _materialize_private_melroformer_pcm24_quarantine,
)
from sunofriend._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)
from sunofriend._separation_python_import_closure import (
    _capture_python_import_closure_claim,
    _mark_python_import_closure_stable,
    _verify_python_import_closure_claim,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS
from sunofriend.separation_contract import _canonical_json_bytes


@pytest.mark.parametrize(
    (
        "bind_python_import_closure",
        "observe_outbound_attempts",
        "shared_headroom",
    ),
    [
        (False, False, False),
        (True, False, False),
        (True, True, False),
        (True, True, True),
    ],
)
@pytest.mark.parametrize(
    "rights_authority",
    [
        "creator_and_copyright_holder",
        "user_authorised_private_local_evaluation",
    ],
)
def test_parent_binds_authorised_worker_denials_and_pcm24(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bind_python_import_closure: bool,
    observe_outbound_attempts: bool,
    shared_headroom: bool,
    rights_authority: str,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    worker_path = repository / worker.WORKER_RELATIVE_PATH
    worker_path.parent.mkdir()
    worker_source_bytes = b"# exact private worker fixture\n"
    worker_path.write_bytes(worker_source_bytes)
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
    if shared_headroom:
        source[0, 0] = np.float32(0.75)
        vocals[0, 0] = np.float32(-0.35)
        instrumental[0, 0] = np.float32(1.10)
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
        "rights_authority": rights_authority,
        "evidence_scope": "private_development_only",
        "audio_persisted_by_bridge": False,
    }
    artifacts = {
        "provider": _identity("provider"),
        "runtime": _identity("runtime"),
        "worker": worker._regular_non_symlink_file_identity(worker_path),
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
    verified_closure = _verified_import_closure(tmp_path / "closure-fixture")
    monkeypatch.setattr(
        worker,
        "_verify_python_import_closure_claim",
        lambda *_, **__: verified_closure,
    )
    monkeypatch.setattr(worker, "_verify_worker_import_identity", lambda *_, **__: None)

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command[command.index("-B") + 1] == "-"
        source_stream = kwargs["stdin"]
        assert source_stream.read() == worker_source_bytes
        output = Path(command[command.index("--destination") + 1])
        quarantine = _materialize_private_melroformer_pcm24_quarantine(
            destination=output,
            source=source,
            vocals=vocals,
            instrumental=instrumental,
            np=np,
            allow_shared_attenuation=True,
        )
        closure_requested = "--bind-python-import-closure" in command
        child = {
            "schema": (
                worker.IMPORT_CLOSURE_CHILD_SCHEMA
                if closure_requested
                else worker.CHILD_SCHEMA
            ),
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
                        "vocals": {
                            "sha256": "e" * 64,
                            "peak": float(np.max(np.abs(vocals))),
                        },
                        "instrumental": {
                            "sha256": "f" * 64,
                            "peak": float(np.max(np.abs(instrumental))),
                        },
                    },
                    "additive_accounting": {
                        "passed": True,
                        "maximum_absolute_error": 0.0,
                    },
                },
            },
            "quarantine": plain(quarantine),
        }
        if closure_requested:
            child["import_closure"] = {"fixture": True}
        return subprocess.CompletedProcess(command, 0, json.dumps(child), "")

    monkeypatch.setattr(worker.subprocess, "run", fake_run)

    def fake_observed_run(**kwargs: object) -> tuple[object, object]:
        command = kwargs["command"]
        assert isinstance(command, list)
        completed = fake_run(command, stdin=kwargs["stdin"])
        event = {
            "eventType": "logEvent",
            "senderImagePath": network_observer.SENDER_IMAGE_PATH,
            "eventMessage": (
                "Sandbox: Python(123) deny(1) network-outbound remote:*:9"
            ),
        }
        raw = (
            json.dumps(event)
            + "\n"
            + json.dumps({"count": 1, "finished": 1})
            + "\n"
        ).encode()
        observation = network_observer._build_observation(
            raw_stdout=raw,
            stdout_bytes=len(raw),
            target_pid=123,
            expected_canary_port=9,
            identity={
                "resolved_path": "/usr/bin/log",
                "bytes": 1_024,
                "sha256": "1" * 64,
            },
        )
        return completed, observation

    monkeypatch.setattr(
        worker,
        "_run_with_macos_sandbox_network_observer",
        fake_observed_run,
    )
    evidence = worker._run_private_melroformer_authorised_worker(
        repository_root=repository,
        runtime_path=runtime,
        source_root=source_root,
        checkpoint_path=checkpoint,
        companion_root=companions,
        authorisation_report_path=report,
        expected_authorisation_report_sha256="a" * 64,
        staging_directory=tmp_path / "staging",
        bind_python_import_closure=bind_python_import_closure,
        observe_outbound_attempts=observe_outbound_attempts,
    )

    assert evidence["status"] == "authorised_model_worker_complete_parent_verified"
    assert evidence["conclusion"]["network_denial_bound_to_model_worker"] is True
    assert evidence["conclusion"]["pcm24_quarantine_bound_to_model_worker"] is True
    assert evidence["quarantine"]["evidence_identical"] is True
    if shared_headroom:
        assert evidence["schema"] == worker.HEADROOM_WORKER_SCHEMA
        assert evidence["quarantine"]["level_management"]["applied"] is True
    assert all(value is False for value in evidence["permissions"].values())
    assert "/Users/" not in repr(evidence)
    assert evidence["artifacts"]["complete_python_import_closure_bound"] is (
        bind_python_import_closure
    )
    if observe_outbound_attempts:
        assert evidence["schema"] == (
            worker.HEADROOM_WORKER_SCHEMA
            if shared_headroom
            else worker.DESCRIPTOR_WORKER_SCHEMA
        )
        assert evidence["network_observation"]["observation"][
            "deliberate_canary_denial_count"
        ] == 1
        assert evidence["limitations"][
            "arbitrary_model_attempt_stream_observed"
        ] is True
    elif bind_python_import_closure:
        assert evidence["schema"] == worker.IMPORT_CLOSURE_SCHEMA
        assert evidence["import_closure"] == verified_closure
    else:
        assert evidence["schema"] == worker.SCHEMA
        assert "import_closure" not in evidence
    if observe_outbound_attempts:
        assert evidence["artifacts"][
            "worker_script_path_to_execution_toctou_closed"
        ] is True
        assert evidence["artifacts"][
            "provider_runtime_path_to_execution_toctou_closed"
        ] is False
    else:
        assert "worker_script_path_to_execution_toctou_closed" not in evidence[
            "artifacts"
        ]

    resigned = plain(evidence)
    resigned["permissions"]["publication_permitted"] = True
    unsigned = dict(resigned)
    unsigned.pop("evidence_sha256")
    resigned["evidence_sha256"] = hashlib.sha256(
        _canonical_json_bytes(unsigned)
    ).hexdigest()
    with pytest.raises(ValueError, match="grants a product permission"):
        worker._validate_private_melroformer_authorised_worker(resigned)


def test_worker_import_identity_must_match_the_descriptor_source() -> None:
    expected = {"bytes": 12, "sha256": "a" * 64}
    closure = {
        "files": [
            {
                "root_id": "repository",
                "relative_path": worker.WORKER_RELATIVE_PATH,
                "bytes": 12,
                "sha256": "a" * 64,
                "module_names": ["__main__"],
            }
        ]
    }
    worker._verify_worker_import_identity(closure, expected_identity=expected)

    closure["files"][0]["sha256"] = "b" * 64
    with pytest.raises(ValueError, match="executed worker import identity"):
        worker._verify_worker_import_identity(closure, expected_identity=expected)



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


def _verified_import_closure(root: Path) -> object:
    root.mkdir()
    root_ids = (
        "source_overlay",
        "runtime_environment",
        "repository",
        "base_runtime",
        "system_library",
        "system_usr_lib",
    )
    roots = {}
    for name in root_ids:
        directory = root / name
        directory.mkdir()
        roots[name] = directory
    checked_roots = MappingProxyType(roots)
    module_path = roots["repository"] / "worker_module.py"
    module_path.write_text("VALUE = 1\n", encoding="utf-8")
    file_module = types.ModuleType("fixture.file")
    file_module.__file__ = str(module_path)
    built_in = types.ModuleType("fixture_builtin")
    built_in.__spec__ = SimpleNamespace(origin="built-in")
    modules = {"fixture.file": file_module, "fixture_builtin": built_in}
    claim = _capture_python_import_closure_claim(
        roots=checked_roots, modules=modules
    )
    stable = _mark_python_import_closure_stable(claim, modules=modules)
    return _verify_python_import_closure_claim(stable, roots=checked_roots)
