from __future__ import annotations

import itertools
import json
import os
import platform
import re
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
from sunofriend import _separation_macos_process_image as process_image
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


@pytest.mark.trusted_local
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
    runtime_path = Path(sys.executable).resolve(strict=True)
    expected_process_image_path = process_image._expected_python_process_image(
        runtime_path
    )
    expected_process_image_cdhash = process_image._static_code_identity(
        expected_process_image_path
    )["cdhash"]
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
        str(expected_process_image_path),
        expected_process_image_cdhash,
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
            expected_process_image_path,
        ),
    )

    assert report["schema"] == ("sunofriend.native-spawn-canary-matrix.v10")
    expected_layouts = {
        *itertools.permutations((3, 4, 5)),
        *harness._REPRESENTATIVE_SOURCE_FD_LAYOUTS,
    }
    assert report["case_count"] == len(expected_layouts)
    assert report["all_source_fd_permutations_exercised"] is True
    assert report["all_representative_source_fd_layouts_exercised"] is True
    assert {tuple(case["source_fds"]) for case in report["cases"]} == (expected_layouts)
    for case in report["cases"]:
        assert case["native_owner_pid_pgid_match_observed"] is True
        assert "pid" not in case
        assert "pgid" not in case
        assert case["open_descriptors"] == [0, 1, 2, 3, 4, 5]
        assert case["native_owner_leader_exit_observed"] is True
        assert case["native_owner_leader_reaped"] is True
        assert case["native_owner_group_empty"] is True
        assert case["native_owner_ownership_released"] is True
        assert case["native_owner_ownership_lost"] is False
        assert case["native_owner_cached_wait_stable"] is True
        assert case["native_owner_post_reap_signal_rejected"] is True
        assert case["native_owner_normal_exit_observed"] is True
        assert case["native_owner_signal_termination_observed"] is False
        assert case["native_owner_exit_status_zero"] is True
        assert case["post_cpython_signal_state_observed"] is True
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
        "runtime_process_image_identity",
        "fixed_sandbox_provider_identity",
        "fixed_worker_identity",
        "fixed_hold_worker_identity",
        "fixed_descendant_worker_identity",
        "fixed_network_worker_identity",
        "fixed_ready_worker_identity",
        "fixed_combined_worker_identity",
        "fixed_ready_release_worker_identity",
        "fixed_frame_bootstrap_worker_identity",
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
        "observed_from_inside_harness": True,
        "observation_point": "harness_entry_before_descriptor_cleanup",
        "harness_entry_open_descriptors": [0, 1, 2],
        "no_unexpected_inherited_descriptors": True,
        "clean_outer_process_dependency_resolved": True,
    }
    assert report["signal_state_canary"] == {
        "observed": True,
        "observation_point": "worker_main_after_cpython_startup",
        "main_thread_mask_empty": True,
        "termination_signals_default": True,
        "sigchld_default": True,
        "cpython_runtime_adjustments_observed": True,
        "spawn_attribute_claim_proven": False,
        "reason": ("post_cpython_state_does_not_reconstruct_the_pre_exec_instant"),
    }
    assert set(report["unresolved_boundaries"]) == {
        "extension_path_import_toctou_not_eliminated",
        "runtime_executable_path_exec_toctou_not_eliminated",
        "worker_script_path_open_toctou_not_eliminated",
        "pre_exec_signal_state_not_reconstructed_after_cpython_startup",
        "owner_bound_worker_ready_observer_not_attached_to_real_worker",
        "combined_fixed_worker_bridge_is_not_a_real_model_worker",
        "native_ready_release_transport_is_not_attached_to_real_worker",
        "native_frame_bootstrap_is_model_free_not_real_kim_worker",
        "native_sandbox_frame_bootstrap_is_model_free_not_real_kim_worker",
        "real_model_worker_not_under_native_owner",
    }
    assert report["extension_path_serialized"] is False
    assert report["worker_path_serialized"] is False
    assert report["native_owner_type_qualification"] == {
        "direct_construction_rejected": True,
        "raw_pid_not_exposed": True,
        "copy_and_pickle_rejected": True,
        "fork_clone_destructor_guard_present": True,
        "owner_bound_process_image_observer_present": True,
        "owner_bound_network_observation_broker_present": True,
        "network_broker_single_use": True,
        "owner_bound_worker_ready_native_image_observer_present": True,
        "combined_fixed_worker_bridge_present": True,
        "model_free_terminal_projection_from_live_owner_present": True,
        "fixed_native_ready_release_transport_present": True,
        "existing_kim_ready_schema_exercised_model_free": True,
        "fixed_model_free_frame_bootstrap_present": True,
        "private_request_result_frames_consumed_model_free": True,
        "fixed_native_kim_sandbox_launch_shape_present": True,
        "native_kim_sandbox_denials_exercised_model_free": True,
        "observer_exports_pid_or_pgid": False,
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
    assert report["owner_bound_process_image_canary"] == {
        "wrong_process_image_rejected": True,
        "wrong_cdhash_rejected": True,
        "rejection_preserved_ownership": True,
        "expected_process_image_matched": True,
        "kernel_cdhash_matched_static_identity": True,
        "raw_pid_or_pgid_retained": False,
        "exact_reap_after_observation": True,
        "parent_descriptors_unchanged": True,
    }
    network_canary = report["owner_bound_network_canary"]
    assert set(network_canary) == {
        "observer_ready_before_native_spawn",
        "native_owner_bound",
        "deliberate_canary_denial_observed",
        "other_owned_network_denial_count",
        "broker_single_use_rejected_replay",
        "raw_pid_or_pgid_retained",
        "raw_destination_retained",
        "normal_zero_exit_observed",
        "group_empty_before_exact_reap",
        "exact_reap_after_observation",
        "evidence_sha256",
        "parent_descriptors_unchanged",
    }
    assert network_canary["observer_ready_before_native_spawn"] is True
    assert network_canary["native_owner_bound"] is True
    assert network_canary["deliberate_canary_denial_observed"] is True
    assert network_canary["other_owned_network_denial_count"] == 0
    assert network_canary["broker_single_use_rejected_replay"] is True
    assert network_canary["raw_pid_or_pgid_retained"] is False
    assert network_canary["raw_destination_retained"] is False
    assert network_canary["normal_zero_exit_observed"] is True
    assert network_canary["group_empty_before_exact_reap"] is True
    assert network_canary["exact_reap_after_observation"] is True
    assert re.fullmatch(r"[0-9a-f]{64}", network_canary["evidence_sha256"])
    assert network_canary["parent_descriptors_unchanged"] is True
    ready_image_canary = report["owner_bound_worker_ready_native_image_canary"]
    assert set(ready_image_canary) == {
        "pid_free_worker_ready_marker_observed",
        "native_owner_bound",
        "stable_consecutive_snapshots",
        "executable_region_count",
        "file_backed_executable_region_count",
        "unpathed_executable_region_count",
        "mapped_file_count",
        "main_process_image_present_once",
        "mapped_artifact_manifest_sha256",
        "raw_pid_or_pgid_retained",
        "raw_executable_paths_retained",
        "model_or_checkpoint_loaded",
        "audio_read",
        "network_used",
        "exact_reap_after_observation",
        "parent_descriptors_unchanged",
    }
    assert ready_image_canary["pid_free_worker_ready_marker_observed"] is True
    assert ready_image_canary["native_owner_bound"] is True
    assert ready_image_canary["stable_consecutive_snapshots"] is True
    assert ready_image_canary["executable_region_count"] >= 1
    assert ready_image_canary["file_backed_executable_region_count"] >= 1
    assert ready_image_canary["unpathed_executable_region_count"] >= 0
    assert ready_image_canary["mapped_file_count"] >= 1
    assert ready_image_canary["main_process_image_present_once"] is True
    assert re.fullmatch(
        r"[0-9a-f]{64}", ready_image_canary["mapped_artifact_manifest_sha256"]
    )
    assert ready_image_canary["raw_pid_or_pgid_retained"] is False
    assert ready_image_canary["raw_executable_paths_retained"] is False
    assert ready_image_canary["model_or_checkpoint_loaded"] is False
    assert ready_image_canary["audio_read"] is False
    assert ready_image_canary["network_used"] is False
    assert ready_image_canary["exact_reap_after_observation"] is True
    assert ready_image_canary["parent_descriptors_unchanged"] is True
    combined = report["combined_fixed_worker_bridge_canary"]
    assert set(combined) == {
        "observer_ready_before_native_spawn",
        "pid_free_ready_marker_observed",
        "process_image_matched",
        "stable_consecutive_executable_region_snapshots",
        "mapped_artifact_manifest_sha256",
        "deliberate_network_denial_observed",
        "other_owned_network_denial_count",
        "network_observation_sha256",
        "worker_result_sha256",
        "terminal_projection",
        "raw_pid_or_pgid_retained",
        "raw_executable_paths_retained",
        "raw_network_destination_retained",
        "model_or_checkpoint_loaded",
        "audio_read",
        "normal_zero_exit_observed",
        "group_empty_before_exact_reap",
        "exact_reap_observed",
        "parent_descriptors_unchanged",
    }
    assert combined["observer_ready_before_native_spawn"] is True
    assert combined["pid_free_ready_marker_observed"] is True
    assert combined["process_image_matched"] is True
    assert combined["stable_consecutive_executable_region_snapshots"] is True
    assert re.fullmatch(
        r"[0-9a-f]{64}", combined["mapped_artifact_manifest_sha256"]
    )
    assert combined["deliberate_network_denial_observed"] is True
    assert combined["other_owned_network_denial_count"] == 0
    assert re.fullmatch(
        r"[0-9a-f]{64}", combined["network_observation_sha256"]
    )
    assert re.fullmatch(r"[0-9a-f]{64}", combined["worker_result_sha256"])
    assert combined["terminal_projection"] == {
        "schema": "sunofriend.private-melroformer-native-terminal-projection.v1",
        "native_session_observation_sha256": combined["terminal_projection"][
            "native_session_observation_sha256"
        ],
        "native_execution_observation_sha256": combined["terminal_projection"][
            "native_execution_observation_sha256"
        ],
        "worker_result_sha256": combined["worker_result_sha256"],
        "start_state": "started_owned",
        "wait": {
            "kind": "exited",
            "exit_code": 0,
            "signal": None,
            "core_dumped": False,
        },
        "timed_out": False,
        "term_sent": False,
        "kill_sent": False,
        "worker_reported_identity_matched": True,
        "leader_exit_observed": True,
        "leader_reaped": True,
        "group_empty": True,
        "ownership_released": True,
        "ownership_lost": False,
        "raw_pid_retained": False,
        "raw_pgid_retained": False,
        "signal_authority_exposed": False,
    }
    assert re.fullmatch(
        r"[0-9a-f]{64}",
        combined["terminal_projection"]["native_session_observation_sha256"],
    )
    assert re.fullmatch(
        r"[0-9a-f]{64}",
        combined["terminal_projection"]["native_execution_observation_sha256"],
    )
    assert combined["raw_pid_or_pgid_retained"] is False
    assert combined["raw_executable_paths_retained"] is False
    assert combined["raw_network_destination_retained"] is False
    assert combined["model_or_checkpoint_loaded"] is False
    assert combined["audio_read"] is False
    assert combined["normal_zero_exit_observed"] is True
    assert combined["group_empty_before_exact_reap"] is True
    assert combined["exact_reap_observed"] is True
    assert combined["parent_descriptors_unchanged"] is True
    assert report["native_ready_release_transport_canary"] == {
        "fixed_descriptor_targets": [3, 4, 5, 6, 7],
        "wrong_pipe_access_rejected_before_spawn": True,
        "existing_kim_ready_schema_validated": True,
        "worker_blocked_until_parent_release": True,
        "process_image_matched_while_blocked": True,
        "normal_zero_exit_after_release": True,
        "group_empty_before_exact_reap": True,
        "exact_reap_observed": True,
        "parent_descriptors_unchanged_by_spawn": True,
        "temporary_pipe_descriptors_closed": True,
        "raw_pid_or_pgid_retained": False,
        "model_or_checkpoint_loaded": False,
        "audio_read": False,
        "network_used": False,
    }
    invalid_bootstrap = report["invalid_native_frame_bootstrap_canary"]
    assert invalid_bootstrap == {
        "case_count": 2,
        "all_invalid_requests_rejected_before_ready": True,
        "no_result_frame_written": True,
        "all_owned_groups_drained_and_exact_reaped": True,
        "raw_pid_or_pgid_retained": False,
        "cases": [
            {
                "case": "trailing_frame_byte",
                "rejected_before_ready": True,
                "result_frame_written": False,
                "normal_zero_exit_observed": False,
                "group_empty_before_exact_reap": True,
                "exact_reap_observed": True,
            },
            {
                "case": "tampered_request_hash",
                "rejected_before_ready": True,
                "result_frame_written": False,
                "normal_zero_exit_observed": False,
                "group_empty_before_exact_reap": True,
                "exact_reap_observed": True,
            },
        ],
    }
    bootstrap = report["native_frame_bootstrap_canary"]
    assert set(bootstrap) == {
        "request_frame_validated_by_worker",
        "result_frame_validated_by_parent",
        "request_sha256",
        "result_sha256",
        "child_result_sha256",
        "private_process_identity_matched_then_discarded",
        "worker_blocked_until_parent_release",
        "process_image_matched_while_blocked",
        "request_paths_opened",
        "request_paths_retained",
        "checkpoint_descriptor_bytes_read",
        "model_or_checkpoint_loaded",
        "audio_read",
        "network_used",
        "normal_zero_exit_after_release",
        "group_empty_before_exact_reap",
        "exact_reap_observed",
        "raw_pid_or_pgid_retained",
        "parent_descriptors_unchanged_by_spawn",
        "temporary_pipe_descriptors_closed",
        "fixed_native_sandbox_launch_shape",
        "network_fork_and_outside_write_denied",
    }
    assert bootstrap["request_frame_validated_by_worker"] is True
    assert bootstrap["result_frame_validated_by_parent"] is True
    assert re.fullmatch(r"[0-9a-f]{64}", bootstrap["request_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", bootstrap["result_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", bootstrap["child_result_sha256"])
    assert bootstrap["private_process_identity_matched_then_discarded"] is True
    assert bootstrap["worker_blocked_until_parent_release"] is True
    assert bootstrap["process_image_matched_while_blocked"] is True
    assert bootstrap["request_paths_opened"] is False
    assert bootstrap["request_paths_retained"] is False
    assert bootstrap["checkpoint_descriptor_bytes_read"] == 0
    assert bootstrap["model_or_checkpoint_loaded"] is False
    assert bootstrap["audio_read"] is False
    assert bootstrap["network_used"] is False
    assert bootstrap["normal_zero_exit_after_release"] is True
    assert bootstrap["group_empty_before_exact_reap"] is True
    assert bootstrap["exact_reap_observed"] is True
    assert bootstrap["raw_pid_or_pgid_retained"] is False
    assert bootstrap["parent_descriptors_unchanged_by_spawn"] is True
    assert bootstrap["temporary_pipe_descriptors_closed"] is True
    assert bootstrap["fixed_native_sandbox_launch_shape"] is False
    assert bootstrap["network_fork_and_outside_write_denied"] is False
    sandbox_bootstrap = report["native_sandbox_frame_bootstrap_canary"]
    assert sandbox_bootstrap["fixed_native_sandbox_launch_shape"] is True
    assert sandbox_bootstrap["network_fork_and_outside_write_denied"] is True
    assert sandbox_bootstrap["request_frame_validated_by_worker"] is True
    assert sandbox_bootstrap["result_frame_validated_by_parent"] is True
    assert sandbox_bootstrap[
        "private_process_identity_matched_then_discarded"
    ] is True
    assert sandbox_bootstrap["normal_zero_exit_after_release"] is True
    assert sandbox_bootstrap["group_empty_before_exact_reap"] is True
    assert sandbox_bootstrap["exact_reap_observed"] is True
    assert report["descendant_group_canary"] == {
        "leader_exit_observed_without_reap": True,
        "live_descendant_prevented_ownership_release": True,
        "whole_owned_group_signalled": True,
        "group_empty_before_exact_leader_reap": True,
        "leader_exact_reaped": True,
        "ownership_released_only_after_group_empty": True,
        "raw_pid_or_pgid_retained": False,
        "parent_descriptors_unchanged": True,
    }

    _assert_nondefault_sigchld_rejected(
        artifact_path=build.artifact_path,
        probe_root=tmp_path / "custom-sigchld-probe",
    )


@pytest.mark.trusted_local
@pytest.mark.skipif(
    sys.platform != "darwin" or platform.system() != "Darwin",
    reason="live native sandbox frame canary is macOS-only",
)
def test_fresh_private_native_build_passes_sandbox_frame_bootstrap(
    tmp_path: Path,
) -> None:
    build_root = tmp_path / r"private sandbox frame build $edge\root"
    build = native_build._build_native_launcher(cache_root=build_root)
    receipt = build.receipt.to_dict()
    runtime_path = Path(sys.executable).resolve(strict=True)
    expected_process_image_path = process_image._expected_python_process_image(
        runtime_path
    )
    expected_process_image_cdhash = process_image._static_code_identity(
        expected_process_image_path
    )["cdhash"]
    harness_root = tmp_path / "sandbox-frame-canary"
    harness_root.mkdir(mode=0o700)
    command = [
        sys.executable,
        "-I",
        "-B",
        "-S",
        str(HARNESS),
        "--sandbox-frame-only",
        str(build.artifact_path),
        str(harness_root),
        receipt["artifact"]["sha256"],
        receipt["build_input"]["source"]["sha256"],
        receipt["build_input"]["build_contract_sha256"],
        str(expected_process_image_path),
        expected_process_image_cdhash,
    ]

    return_code, stdout, stderr = _run_bounded_harness(command)

    assert return_code == 0, stderr.decode("utf-8", errors="replace")
    assert stderr == b""
    report = _decode_one_canonical_report(stdout)
    _assert_path_free_report(
        stdout,
        forbidden_paths=(
            tmp_path,
            build_root,
            build.artifact_path,
            harness_root,
            REPOSITORY,
            HARNESS,
            expected_process_image_path,
        ),
    )
    assert report["schema"] == "sunofriend.native-kim-sandbox-frame-canary.v1"
    assert report["status"] == "model_free_native_sandbox_launch_proved"
    assert report["real_model_worker_executed"] is False
    assert report["checkpoint_opened"] is False
    assert report["audio_opened"] is False
    assert report["product_authority_granted"] is False
    canary = report["canary"]
    assert canary["fixed_native_sandbox_launch_shape"] is True
    assert canary["network_fork_and_outside_write_denied"] is True
    assert canary["request_frame_validated_by_worker"] is True
    assert canary["result_frame_validated_by_parent"] is True
    assert canary["private_process_identity_matched_then_discarded"] is True
    assert canary["normal_zero_exit_after_release"] is True
    assert canary["group_empty_before_exact_reap"] is True
    assert canary["exact_reap_observed"] is True


@pytest.mark.trusted_local
@pytest.mark.skipif(
    sys.platform != "darwin" or platform.system() != "Darwin",
    reason="fixed model-free native parent adapter is macOS-only",
)
def test_fresh_private_native_build_passes_fixed_model_free_parent_adapter(
    tmp_path: Path,
) -> None:
    build_root = tmp_path / r"private fixed parent build $edge\root"
    build = native_build._build_native_launcher(cache_root=build_root)
    receipt = build.receipt.to_dict()
    runtime_path = Path(sys.executable).resolve(strict=True)
    expected_process_image_path = process_image._expected_python_process_image(
        runtime_path
    )
    expected_process_image_cdhash = process_image._static_code_identity(
        expected_process_image_path
    )["cdhash"]
    harness_root = tmp_path / "fixed-parent-adapter-canary"
    harness_root.mkdir(mode=0o700)
    command = [
        sys.executable,
        "-I",
        "-B",
        "-S",
        str(HARNESS),
        "--fixed-parent-adapter-only",
        str(build.artifact_path),
        str(harness_root),
        receipt["artifact"]["sha256"],
        receipt["build_input"]["source"]["sha256"],
        receipt["build_input"]["build_contract_sha256"],
        str(expected_process_image_path),
        expected_process_image_cdhash,
    ]

    return_code, stdout, stderr = _run_bounded_harness(command)

    assert return_code == 0, stderr.decode("utf-8", errors="replace")
    assert stderr == b""
    report = _decode_one_canonical_report(stdout)
    _assert_path_free_report(
        stdout,
        forbidden_paths=(
            tmp_path,
            build_root,
            build.artifact_path,
            harness_root,
            REPOSITORY,
            HARNESS,
            expected_process_image_path,
        ),
    )
    assert report["schema"] == (
        "sunofriend.native-model-free-parent-adapter-canary.v1"
    )
    assert report["status"] == (
        "fixed_model_free_parent_adapter_and_cleanup_proved"
    )
    evidence = report["adapter_evidence"]
    assert evidence["schema"] == (
        "sunofriend.private-melroformer-native-model-free-adapter.v1"
    )
    assert evidence["live_observation"]["ready_release_completed"] is True
    assert evidence["live_observation"]["deliberate_network_denial_count"] >= 1
    assert evidence["live_observation"]["other_owned_network_denial_count"] == 0
    assert evidence["staging_verification"]["worker_inputs_unchanged"] is True
    assert evidence["staging_verification"]["only_result_frame_changed"] is True
    assert evidence["terminal_projection"]["leader_reaped"] is True
    assert evidence["terminal_projection"]["group_empty"] is True
    assert evidence["terminal_projection"]["ownership_released"] is True
    assert evidence["terminal_projection"]["worker_reported_identity_matched"] is True
    assert evidence["effects"] == {
        "native_process_started": True,
        "model_free_worker_started": True,
        "accepted_checkpoint_opened": False,
        "checkpoint_descriptor_bytes_read_by_worker": 0,
        "model_imported": False,
        "audio_read": False,
        "network_used": False,
        "denied_network_canary_attempted": True,
        "staged_result_frame_written": True,
    }
    assert all(value is False for value in evidence["permissions"].values())
    assert report["adversarial_cleanup"] == {
        "case": "wrong_process_image_cdhash",
        "rejected_before_worker_release": True,
        "terminal_cleanup_complete": True,
        "cleanup_error_count": 0,
        "real_model_worker_started": False,
        "checkpoint_opened": False,
        "audio_opened": False,
    }
    assert report["real_model_worker_executed"] is False
    assert report["accepted_checkpoint_opened"] is False
    assert report["audio_opened"] is False
    assert report["product_authority_granted"] is False
    assert re.fullmatch(r"[0-9a-f]{64}", report["report_sha256"])
