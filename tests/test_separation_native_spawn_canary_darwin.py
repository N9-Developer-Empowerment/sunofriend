from __future__ import annotations

import itertools
import json
import os
import platform
import selectors
import signal
import stat
import subprocess
import sys
import sysconfig
import time
from pathlib import Path
from typing import Any

import pytest

from sunofriend import _separation_native_build_darwin as native_build
from tests import _separation_native_spawn_canary_harness as harness


REPOSITORY = Path(__file__).resolve().parents[1]
HARNESS = REPOSITORY / "tests" / "_separation_native_spawn_canary_harness.py"
WORKER = REPOSITORY / "tests" / "_separation_native_spawn_canary_worker.py"
_MAXIMUM_STREAM_BYTES = 262_144
_HARNESS_TIMEOUT_SECONDS = 30.0


def _kill_and_reap(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        process.kill()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("canary supervisor could not reap its process") from error


def _run_bounded_harness(command: list[str]) -> tuple[int, bytes, bytes]:
    policy = harness.supervised_harness_subprocess_policy()
    assert policy == {"close_fds": True, "pass_fds": ()}
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd="/",
        env={
            "LANG": "C",
            "LC_ALL": "C",
            "TZ": "UTC",
        },
        start_new_session=True,
        **policy,
    )
    if process.stdout is None or process.stderr is None:
        _kill_and_reap(process)
        raise AssertionError("canary supervisor pipes are unavailable")
    streams = {
        process.stdout.fileno(): bytearray(),
        process.stderr.fileno(): bytearray(),
    }
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    selector.register(process.stderr, selectors.EVENT_READ)
    deadline = time.monotonic() + _HARNESS_TIMEOUT_SECONDS
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("native canary harness timed out")
            for key, _events in selector.select(min(0.1, remaining)):
                try:
                    chunk = os.read(key.fd, 65_536)
                except InterruptedError:
                    continue
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                target = streams[key.fd]
                target.extend(chunk)
                if len(target) > _MAXIMUM_STREAM_BYTES:
                    raise RuntimeError("native canary harness output is too large")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("native canary harness did not exit in time")
        return_code = process.wait(timeout=remaining)
        return (
            return_code,
            bytes(streams[process.stdout.fileno()]),
            bytes(streams[process.stderr.fileno()]),
        )
    finally:
        selector.close()
        _kill_and_reap(process)
        process.stdout.close()
        process.stderr.close()


def _decode_one_canonical_report(payload: bytes) -> dict[str, Any]:
    if (
        not payload
        or len(payload) > _MAXIMUM_STREAM_BYTES
        or not payload.endswith(b"\n")
        or payload.count(b"\n") != 1
    ):
        raise AssertionError("canary report framing is invalid")

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise AssertionError("canary report has duplicate fields")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise AssertionError(f"canary report contains {value}")

    document = json.loads(
        payload.decode("ascii"),
        object_pairs_hook=pairs,
        parse_constant=invalid_constant,
    )
    if not isinstance(document, dict):
        raise AssertionError("canary report must be an object")
    canonical = (
        json.dumps(
            document,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
    if canonical != payload:
        raise AssertionError("canary report is not canonical JSON")
    return document


def _assert_path_free_report(
    report_bytes: bytes,
    *,
    forbidden_paths: tuple[Path, ...],
) -> None:
    text = report_bytes.decode("ascii")
    for path in forbidden_paths:
        assert str(path) not in text


def _assert_nondefault_sigchld_rejected(
    *,
    artifact_path: Path,
    probe_root: Path,
) -> None:
    probe_root.mkdir(mode=0o700)
    program = r"""
import importlib.util
import ctypes
import json
import os
import signal
import sys
import time
from pathlib import Path

module_name = "_separation_native_spawn_darwin"
artifact = Path(sys.argv[1])
root = Path(sys.argv[2])
worker = Path(sys.argv[3])
mode = sys.argv[4]
spec = importlib.util.spec_from_file_location(module_name, artifact)
if spec is None or spec.loader is None:
    raise SystemExit(10)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
request_path = root / "request.bin"
result_path = root / "result.bin"
checkpoint_path = root / "checkpoint.bin"
request_path.write_bytes(b"request\n")
result_path.write_bytes(b"")
checkpoint_path.write_bytes(b"checkpoint\n")
descriptors = (
    os.open(request_path, os.O_RDONLY),
    os.open(result_path, os.O_WRONLY),
    os.open(checkpoint_path, os.O_RDONLY),
)
if descriptors != (3, 4, 5):
    raise SystemExit(11)
if mode == "custom_handler":
    def custom_sigchld(_number, _frame):
        return None
    signal.signal(signal.SIGCHLD, custom_sigchld)
    def restore_sigchld():
        signal.signal(signal.SIGCHLD, signal.SIG_DFL)
elif mode == "sa_nocldwait":
    class Sigaction(ctypes.Structure):
        _fields_ = [
            ("handler", ctypes.c_void_p),
            ("mask", ctypes.c_uint32),
            ("flags", ctypes.c_int),
        ]
    libc = ctypes.CDLL(None, use_errno=True)
    sigaction = libc.sigaction
    sigaction.argtypes = (
        ctypes.c_int,
        ctypes.POINTER(Sigaction),
        ctypes.POINTER(Sigaction),
    )
    sigaction.restype = ctypes.c_int
    original = Sigaction()
    changed = Sigaction()
    if sigaction(signal.SIGCHLD, None, ctypes.byref(original)) != 0:
        raise SystemExit(13)
    ctypes.memmove(
        ctypes.byref(changed),
        ctypes.byref(original),
        ctypes.sizeof(Sigaction),
    )
    changed.flags |= 0x20
    if sigaction(signal.SIGCHLD, ctypes.byref(changed), None) != 0:
        raise SystemExit(14)
    def restore_sigchld():
        if sigaction(
            signal.SIGCHLD,
            ctypes.byref(original),
            None,
        ) != 0:
            raise SystemExit(15)
else:
    raise SystemExit(16)
owner = None
try:
    owner = module._spawn_bound_fake_worker(
        os.fsencode(Path(sys.executable).resolve()),
        os.fsencode(worker),
        *descriptors,
    )
except ValueError as error:
    rejected = "parent SIGCHLD must be default" in str(error)
finally:
    restore_sigchld()
if owner is not None:
    owner.signal_owned_group(signal.SIGKILL)
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        status = owner.wait_nohang()
        if status is not None:
            break
        time.sleep(0.005)
    else:
        raise SystemExit(17)
    rejected = False
process_started = owner is not None
for descriptor in descriptors:
    os.close(descriptor)
payload = {
    "mode": mode,
    "nondefault_sigchld_rejected": rejected,
    "process_started": process_started,
}
sys.stdout.write(json.dumps(
    payload,
    ensure_ascii=True,
    allow_nan=False,
    separators=(",", ":"),
    sort_keys=True,
) + "\n")
raise SystemExit(0 if rejected else 12)
"""
    for mode in ("custom_handler", "sa_nocldwait"):
        mode_root = probe_root / mode
        mode_root.mkdir(mode=0o700)
        command = [
            sys.executable,
            "-I",
            "-B",
            "-S",
            "-c",
            program,
            str(artifact_path),
            str(mode_root),
            str(WORKER),
            mode,
        ]
        return_code, stdout, stderr = _run_bounded_harness(command)
        assert return_code == 0, stderr.decode("utf-8", errors="replace")
        assert stderr == b""
        assert _decode_one_canonical_report(stdout) == {
            "mode": mode,
            "nondefault_sigchld_rejected": True,
            "process_started": False,
        }


@pytest.mark.skipif(
    sys.platform != "darwin" or platform.system() != "Darwin",
    reason="live native spawn canary is macOS-only",
)
def test_fresh_private_native_build_passes_isolated_descriptor_canary(
    tmp_path: Path,
) -> None:
    private_build_root = tmp_path / r"private build $edge\root"
    build = native_build._build_native_launcher(cache_root=private_build_root)
    receipt = build.receipt.to_dict()
    artifact = receipt["artifact"]
    source_sha256 = receipt["build_input"]["source"]["sha256"]
    build_contract_sha256 = receipt["build_input"]["build_contract_sha256"]
    harness_root = tmp_path / "isolated-canary"
    harness_root.mkdir(mode=0o700)
    command = [
        sys.executable,
        "-I",
        "-B",
        "-S",
        str(HARNESS),
        str(build.artifact_path),
        str(harness_root),
        artifact["sha256"],
        source_sha256,
        build_contract_sha256,
    ]

    return_code, stdout, stderr = _run_bounded_harness(command)

    assert return_code == 0, stderr.decode("utf-8", errors="replace")
    assert stderr == b""
    report = _decode_one_canonical_report(stdout)
    _assert_path_free_report(
        stdout,
        forbidden_paths=(
            tmp_path,
            private_build_root,
            build.artifact_path,
            harness_root,
            REPOSITORY,
            HARNESS,
        ),
    )

    assert report["schema"] == ("sunofriend.native-spawn-canary-matrix.v1")
    expected_layouts = {
        *itertools.permutations((3, 4, 5)),
        *harness._REPRESENTATIVE_SOURCE_FD_LAYOUTS,
    }
    assert report["case_count"] == len(expected_layouts)
    assert report["all_source_fd_permutations_exercised"] is True
    assert report["all_representative_source_fd_layouts_exercised"] is True
    assert {tuple(case["source_fds"]) for case in report["cases"]} == (expected_layouts)
    assert len({case["pid"] for case in report["cases"]}) == len(expected_layouts)
    for case in report["cases"]:
        assert case["pid"] == case["pgid"]
        assert case["open_descriptors"] == [0, 1, 2, 3, 4, 5]
        assert case["native_owner_leader_reaped"] is True
        assert case["native_owner_ownership_released"] is True
        assert case["native_owner_ownership_lost"] is False
        assert case["native_owner_cached_wait_stable"] is True
        assert case["native_owner_post_reap_signal_rejected"] is True
        assert case["parent_offsets_unchanged_after_spawn"] is True
        assert case["parent_offsets_unchanged_after_reap"] is True

    expected_artifact_identity = {
        "sha256": artifact["sha256"],
        "file_type": stat.S_IFREG,
        **artifact["stat_identity"],
    }
    assert report["artifact_sha256"] == artifact["sha256"]
    assert report["native_artifact_identity"] == (expected_artifact_identity)
    assert report["native_source_sha256"] == source_sha256
    assert report["native_build_contract_sha256"] == (build_contract_sha256)
    assert report["extension_loader"] == {
        "kind": "ExtensionFileLoader",
        "module_name": "_separation_native_spawn_darwin",
        "module_spec_name": "_separation_native_spawn_darwin",
        "expected_suffix": sysconfig.get_config_var("EXT_SUFFIX"),
        "identity_checks_passed": True,
    }
    for key in (
        "runtime_executable_identity",
        "fixed_worker_identity",
        "fixed_hold_worker_identity",
    ):
        identity = report[key]
        assert set(identity) == {
            "sha256",
            "device",
            "inode",
            "mode",
            "file_type",
            "links",
            "owner",
            "group",
            "bytes",
            "modified_ns",
            "changed_ns",
        }
        assert identity["sha256"]
        assert identity["file_type"] == stat.S_IFREG
        assert identity["links"] == 1
        assert identity["bytes"] > 0

    assert report["stdio_qualification"] == {
        "fixed_null_device_identity_verified": True,
        "all_three_same_identity_verified": True,
        "stdin_access": "read_only",
        "stdout_access": "write_only",
        "stderr_access": "write_only",
    }
    assert report["complete_descriptor_scan_soft_limit"] == 4_096
    assert report["source_descriptor_scope"] == {
        "exact_physical_descriptors": [3, 4, 5],
        "all_six_permutations_proven": True,
        "representative_physical_layouts": [
            list(source_fds) for source_fds in harness._REPRESENTATIVE_SOURCE_FD_LAYOUTS
        ],
        "representative_layout_classes": [
            "ordinary_low_non_target",
            "scratch_candidate_collision",
            "mixed_fixed_target_collision",
            "near_fixed_scan_limit",
        ],
        "arbitrary_source_descriptor_values_proven": False,
    }
    assert report["parent_status_flag_claim"] == {
        "compared_bits": [
            "O_ACCMODE",
            "O_APPEND",
            "O_NONBLOCK",
            "O_ASYNC",
        ],
        "opaque_f_getfl_bits_compared": False,
    }
    assert report["outer_supervisor_qualification"] == {
        "close_fds_required": True,
        "pass_fds_required": [],
        "observed_from_inside_harness": False,
        "clean_outer_process_dependency_resolved": False,
    }
    assert report["signal_state_canary"] == {
        "observed": False,
        "spawn_attribute_claim_proven": False,
        "reason": ("cpython_startup_can_change_signal_state_before_worker_user_code"),
    }
    assert set(report["unresolved_boundaries"]) == {
        "extension_path_import_toctou_not_eliminated",
        "runtime_executable_path_exec_toctou_not_eliminated",
        "worker_script_path_open_toctou_not_eliminated",
        "clean_outer_supervisor_not_proven_inside_harness",
    }
    assert report["extension_path_serialized"] is False
    assert report["worker_path_serialized"] is False
    assert report["native_owner_type_qualification"] == {
        "direct_construction_rejected": True,
        "raw_pid_not_exposed": True,
        "copy_and_pickle_rejected": True,
        "fork_clone_destructor_guard_present": True,
    }
    assert report["post_spawn_owner_drop_canary"] == {
        "worker_pid_reported_by_child": True,
        "owner_identity_confirmed": True,
        "raw_pid_not_exposed": True,
        "copy_and_pickle_rejected": True,
        "drop_forced_exact_reap": True,
        "parent_descriptors_unchanged": True,
    }
    assert report["external_reap_poison_canary"] == {
        "external_exact_reap_observed": True,
        "owner_transitioned_to_lost": True,
        "direct_stale_signal_rejected": True,
        "poisoned_wait_rejected": True,
        "drop_after_loss_did_not_touch_parent_descriptors": True,
    }

    _assert_nondefault_sigchld_rejected(
        artifact_path=build.artifact_path,
        probe_root=tmp_path / "custom-sigchld-probe",
    )
