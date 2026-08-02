from __future__ import annotations

import ast
import itertools
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests import _separation_native_spawn_canary_harness as harness


REPOSITORY = Path(__file__).resolve().parents[1]
WORKER = REPOSITORY / "tests" / "_separation_native_spawn_canary_worker.py"
HOLD_WORKER = REPOSITORY / "tests" / "_separation_native_spawn_hold_worker.py"
DESCENDANT_WORKER = (
    REPOSITORY / "tests" / "_separation_native_spawn_descendant_worker.py"
)
NETWORK_WORKER = (
    REPOSITORY / "tests" / "_separation_native_spawn_network_worker.py"
)
READY_WORKER = (
    REPOSITORY / "tests" / "_separation_native_spawn_ready_worker.py"
)
COMBINED_WORKER = (
    REPOSITORY / "tests" / "_separation_native_spawn_combined_worker.py"
)
HARNESS = REPOSITORY / "tests" / "_separation_native_spawn_canary_harness.py"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _called_name(node: ast.AST) -> str:
    if not isinstance(node, ast.Call):
        return ""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def test_canary_worker_hardens_fd345_before_protocol_or_checkpoint_reads() -> None:
    tree = _tree(WORKER)
    main = _function(tree, "main")
    first = main.body[0]

    assert isinstance(first, ast.Expr)
    assert _called_name(first.value) == "_harden_transport_descriptors"
    harden = _function(tree, "_harden_transport_descriptors")
    calls = [node for node in ast.walk(harden) if isinstance(node, ast.Call)]
    assert [_called_name(node) for node in calls] == ["set_inheritable"]
    assert not any(
        _called_name(node) in {"read", "pread", "fstat"}
        for node in ast.walk(harden)
        if isinstance(node, ast.Call)
    )


def test_canary_worker_is_fixed_stdlib_only_and_has_no_expansive_surface() -> None:
    tree = _tree(WORKER)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
    assert imports == {
        "__future__",
        "errno",
        "fcntl",
        "hashlib",
        "json",
        "os",
        "resource",
        "signal",
        "stat",
        "sys",
        "typing",
    }
    assert not imports & {
        "ctypes",
        "http",
        "onnxruntime",
        "pickle",
        "requests",
        "socket",
        "subprocess",
        "torch",
        "urllib",
    }
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    called = {_called_name(node) for node in calls}
    assert all(
        isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "re"
        for node in calls
        if _called_name(node) == "compile"
    )
    called.discard("compile")
    assert not called & {
        "compile",
        "connect",
        "eval",
        "exec",
        "fork",
        "popen",
        "system",
        "urlopen",
    }
    source = WORKER.read_text(encoding="utf-8")
    assert "http://" not in source
    assert "https://" not in source
    assert "os.pread(descriptor" in source
    assert "os.pwrite(descriptor" in source
    assert "signal.pthread_sigmask(signal.SIG_BLOCK, [])" in source
    assert "worker_main_after_cpython_startup" in source
    assert "os.read(" not in source
    assert "os.write(" not in source


def test_network_canary_worker_is_fixed_self_sandboxing_and_model_free() -> None:
    tree = _tree(NETWORK_WORKER)
    source = NETWORK_WORKER.read_text(encoding="utf-8")
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])

    assert imports == {
        "__future__",
        "errno",
        "fcntl",
        "json",
        "os",
        "pathlib",
        "resource",
        "socket",
        "sys",
        "time",
        "typing",
    }
    assert not imports & {
        "basic_pitch",
        "ctypes",
        "http",
        "onnxruntime",
        "requests",
        "subprocess",
        "torch",
        "urllib",
    }
    assert '_SANDBOX_EXEC = "/usr/bin/sandbox-exec"' in source
    assert "(deny network*)" in source
    assert "os.execve(" in source
    assert 'connect_ex(("127.0.0.1", 9))' in source
    assert '"external_destination_contacted": False' in source
    assert '"model_or_checkpoint_loaded": False' in source
    assert "os.getpid(" not in source
    assert "os.getpgrp(" not in source
    assert "_harden_transport_descriptors()" in source
    assert source.index("_harden_transport_descriptors()", source.index("def _run_denied_canary")) < source.index(
        "socket.socket(", source.index("def _run_denied_canary")
    )


def test_ready_worker_is_fixed_pid_free_and_model_free() -> None:
    tree = _tree(READY_WORKER)
    source = READY_WORKER.read_text(encoding="utf-8")
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])

    assert imports == {
        "__future__",
        "_bz2",
        "_ctypes",
        "_hashlib",
        "_lzma",
        "_sqlite3",
        "_ssl",
        "json",
        "os",
        "signal",
        "time",
        "typing",
        "zlib",
    }
    assert not imports & {
        "basic_pitch",
        "http",
        "mlx",
        "onnxruntime",
        "requests",
        "subprocess",
        "torch",
        "urllib",
    }
    assert '"phase": "fixed_native_modules_loaded"' in source
    assert '"pid_or_pgid_exported": False' in source
    assert '"model_or_checkpoint_loaded": False' in source
    assert '"audio_read": False' in source
    assert '"network_used": False' in source
    assert "os.getpid(" not in source
    assert "os.getpgrp(" not in source
    assert "socket." not in source
    assert "_harden_transport_descriptors()" in source
    assert source.index("_harden_transport_descriptors()", source.index("def main")) < source.index(
        "_write_result(", source.index("def main")
    )


def test_combined_worker_has_pid_free_ready_then_private_identity_result() -> None:
    tree = _tree(COMBINED_WORKER)
    source = COMBINED_WORKER.read_text(encoding="utf-8")
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])

    assert imports == {
        "__future__",
        "_bz2",
        "_ctypes",
        "_hashlib",
        "_lzma",
        "_sqlite3",
        "_ssl",
        "errno",
        "fcntl",
        "hashlib",
        "json",
        "os",
        "pathlib",
        "resource",
        "socket",
        "sys",
        "time",
        "typing",
        "zlib",
    }
    assert not imports & {
        "basic_pitch",
        "http",
        "mlx",
        "onnxruntime",
        "requests",
        "subprocess",
        "torch",
        "urllib",
    }
    assert '_SANDBOX_EXEC = "/usr/bin/sandbox-exec"' in source
    assert "(deny network*)" in source
    assert '"schema": "sunofriend.native-owner-combined-ready.v1"' in source
    assert '"pid_or_pgid_exported": False' in source
    assert '"schema": "sunofriend.native-owner-combined-result.v1"' in source
    assert '"private_process_identity"' in source
    ready_index = source.index("ready = {")
    ready_write_index = source.index("_write_result(ready_bytes)")
    canary_index = source.index("socket.socket(", ready_write_index)
    final_write_index = source.index("_write_result(_canonical_bytes(payload))")
    assert ready_index < ready_write_index < canary_index < final_write_index
    assert source.index("_harden_transport_descriptors()", source.index("def _run_combined_canary")) < ready_index
    assert 'connect_ex(("127.0.0.1", 9))' in source
    assert '"external_destination_contacted": False' in source
    assert '"model_or_checkpoint_loaded": False' in source
    assert '"audio_read": False' in source


def test_hold_worker_hardens_descriptors_then_only_blocks_for_owner_canary() -> None:
    tree = _tree(HOLD_WORKER)
    main = _function(tree, "main")
    first = main.body[0]

    assert isinstance(first, ast.Expr)
    assert _called_name(first.value) == "_harden_transport_descriptors"
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
    assert imports == {
        "__future__",
        "os",
        "signal",
        "time",
    }
    source = HOLD_WORKER.read_text(encoding="utf-8")
    assert "os.pwrite(4, marker, 0)" in source
    assert "os.ftruncate(4, len(marker))" in source
    assert "signal.SIGTERM, signal.SIG_IGN" in source
    assert not any(
        token in source
        for token in (
            "http://",
            "https://",
            "subprocess",
            "os.fork(",
            "os.posix_spawn(",
            "os.system(",
        )
    )


def test_descendant_worker_is_fixed_model_free_group_lifetime_canary() -> None:
    tree = _tree(DESCENDANT_WORKER)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
    assert imports == {
        "__future__",
        "hashlib",
        "json",
        "os",
        "signal",
    }
    source = DESCENDANT_WORKER.read_text(encoding="utf-8")
    assert source.count("os.fork()") == 1
    assert "signal.pause()" in source
    assert "signal.SIGTERM, signal.SIG_IGN" in source
    assert "os.pread(3" in source
    assert "os.pread(5" in source
    assert "os.pwrite(4" in source
    assert not any(
        token in source
        for token in (
            "http://",
            "https://",
            "socket",
            "subprocess",
            "torch",
        )
    )


def test_harness_enumerates_target_and_representative_source_layouts() -> None:
    assert tuple(harness._exact_target_source_fd_permutations()) == tuple(
        itertools.permutations((3, 4, 5))
    )
    assert len(tuple(harness._exact_target_source_fd_permutations())) == 6
    layouts = tuple(harness._source_fd_layouts())
    assert layouts[:6] == tuple(
        ("exact_target_permutation", source_fds)
        for source_fds in itertools.permutations((3, 4, 5))
    )
    assert layouts[6:] == tuple(
        ("representative_physical_layout", source_fds)
        for source_fds in harness._REPRESENTATIVE_SOURCE_FD_LAYOUTS
    )
    assert harness._REPRESENTATIVE_SOURCE_FD_LAYOUTS == (
        (9, 10, 11),
        (11, 9, 10),
        (6, 7, 8),
        (6, 10, 5),
        (3, 9, 10),
        (9, 4, 10),
        (9, 10, 5),
        (3, 10, 5),
        (11, 4, 3),
        (64, 1_024, 4_092),
    )
    assert harness._LOW_CANARY_FDS == (6, 7, 8)
    assert harness._ALTERNATE_LOW_CANARY_FDS == (12, 13, 14)
    assert harness._CANARY_SOFT_LIMIT == 4_096
    assert harness._HIGH_CANARY_FDS == (4_093, 4_094, 4_095)
    assert set(harness._LOW_CANARY_FDS).isdisjoint({3, 4, 5})
    assert set(harness._HIGH_CANARY_FDS).isdisjoint({*harness._LOW_CANARY_FDS, 3, 4, 5})
    for _layout_class, source_fds in layouts:
        assert len(set(source_fds)) == 3
        low_canaries = harness._canary_fds_for_source_layout(source_fds)
        assert set(source_fds).isdisjoint({*low_canaries, *harness._HIGH_CANARY_FDS})
    source = HARNESS.read_text(encoding="utf-8")
    close = source.index("os.closerange(3, original_soft_limit)")
    lower = source.index("resource.setrlimit(")
    assert close < lower
    assert "_assert_descriptor_range_closed(3, original_soft_limit)" in source
    assert (
        "_assert_descriptor_range_closed(\n"
        "        _CANARY_SOFT_LIMIT,\n"
        "        original_soft_limit,"
    ) in source


def test_harness_asserts_parent_child_access_data_and_process_invariants() -> None:
    source = HARNESS.read_text(encoding="utf-8")

    assert "snapshot_parent_descriptors()" in source
    assert "_assert_parent_unchanged(before" in source
    assert source.count("_assert_parent_unchanged(before") == 12
    assert '"open_descriptors") != [0, 1, 2, 3, 4, 5]' in source
    assert '"descriptor_scan_soft_limit") != _CANARY_SOFT_LIMIT' in source
    assert '"request_write": errno.EBADF' in source
    assert '"result_read": errno.EBADF' in source
    assert '"checkpoint_write": errno.EBADF' in source
    assert '"stdio_observation"' in WORKER.read_text(encoding="utf-8")
    assert "child stdio is not the fixed null device" in source
    assert 'os.stat("/dev/null")' in source
    assert "native_owner.matches_pid_and_pgid(" in source
    assert '"request_sha256"' in source
    assert '"checkpoint_sha256"' in source
    assert "_measure_artifact(path)" in source
    assert "native extension changed across import" in source
    assert "_SUNOFRIEND_NATIVE_SOURCE_SHA256" in source
    assert "_SUNOFRIEND_NATIVE_BUILD_CONTRACT_SHA256" in source
    assert "importlib.machinery.ExtensionFileLoader" in source
    assert "module_spec.name != _MODULE_NAME" in source
    assert "not path.name.endswith(expected_suffix)" in source
    assert "_measure_runtime(runtime_path)" in source
    assert "_measure_worker(worker_path)" in source
    assert "bound runtime changed across canary matrix" in source
    assert "bound worker changed across canary matrix" in source
    assert "__CF_USER_TEXT_ENCODING" in source
    assert "_DARWIN_TEXT_ENCODING_RE.fullmatch(value)" in source
    assert "os.WIFEXITED(status)" in source
    assert "os.WEXITSTATUS(status) != 0" in source
    assert "deadline = time.monotonic() + 1.0" in source
    assert source.count("os.waitpid(") == 2
    assert "os.waitpid(worker_pid, os.WNOHANG)" in source
    assert "os.waitpid(worker_pid, 0)" in source
    assert "native_owner.ownership_lost is not True" in source
    assert "poisoned native owner retained wait authority" in source
    assert "os.killpg(" not in source
    assert "with _OwnedCanaryChild(native_owner) as child:" in source
    assert "native_owner = spawn(" in source
    assert "native_owner.wait_nohang()" in source
    assert "native_owner.signal_owned_group(signal.SIGKILL)" in source
    assert "status = child.wait()" in source
    assert '"spawn_attribute_claim_proven": False' in source
    assert "worker_main_after_cpython_startup" in source
    assert "post_cpython_state_does_not_reconstruct_the_pre_exec_instant" in source
    assert "extension_path_import_toctou_not_eliminated" in source
    assert "harness_entry_before_descriptor_cleanup" in source
    assert "no_unexpected_inherited_descriptors" in source
    assert '"arbitrary_source_descriptor_values_proven": False' in source
    assert '"scratch_candidate_collision"' in source
    assert '"opaque_f_getfl_bits_compared": False' in source
    assert "_run_descendant_group_canary(" in source
    assert "_run_owner_bound_network_canary(" in source
    assert "_prepare_owner_bound_network_observer()" in source
    assert "broker.finish(native_owner=native_owner)" in source
    assert '"broker_single_use_rejected_replay": True' in source
    assert '"raw_pid_or_pgid_retained": False' in source
    assert "_run_owner_bound_worker_ready_native_image_canary(" in source
    assert "_enumerate_owned_executable_regions(native_owner)" in source
    assert '"pid_free_worker_ready_marker_observed": True' in source
    assert '"raw_executable_paths_retained": False' in source
    assert "_run_combined_fixed_worker_bridge_canary(" in source
    assert "_derive_model_free_native_terminal_projection(" in source
    assert '"combined_fixed_worker_bridge_present": True' in source
    assert '"model_free_terminal_projection_from_live_owner_present": True' in source
    assert "native owner reaped before its group was empty" in source
    assert "native_owner.group_empty is not False" in source
    assert '"ownership_released_only_after_group_empty": True' in source


def test_harness_does_not_compile_fetch_model_or_run_separation() -> None:
    tree = _tree(HARNESS)
    source = HARNESS.read_text(encoding="utf-8")
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
    assert not imports & {
        "basic_pitch",
        "http",
        "onnxruntime",
        "requests",
        "subprocess",
        "torch",
        "urllib",
    }
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    called = {_called_name(node) for node in calls}
    assert all(
        isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "re"
        for node in calls
        if _called_name(node) == "compile"
    )
    called.discard("compile")
    assert not called & {
        "check_call",
        "check_output",
        "compile",
        "connect",
        "create_connection",
        "eval",
        "exec",
        "fork",
        "popen",
        "Popen",
        "system",
        "urlopen",
    }
    assert "http://" not in source
    assert "https://" not in source
    assert "_spawn_bound_fake_worker" in source
    assert "spec_from_file_location" in source
    assert "socket.socketpair()" in source


def test_snapshot_detects_flags_inheritability_identity_and_offset(
    tmp_path: Path,
) -> None:
    path = tmp_path / "snapshot.bin"
    path.write_bytes(b"0123456789")
    descriptor = path.open("rb", buffering=0)
    try:
        descriptor.seek(4)
        before = harness._snapshot_descriptor(descriptor.fileno())
        assert before.offset == 4
        assert before.inheritable is False
        assert before.device > 0
        assert before.inode > 0
        assert before.descriptor_flags >= 0
        assert before.access_mode == 0
        assert before.append_enabled is False
        assert before.nonblocking_enabled is False
        assert before.async_enabled is False
        descriptor.seek(5)
        after = harness._snapshot_descriptor(descriptor.fileno())
        assert after != before
        assert after.offset == 5
        with pytest.raises(AssertionError, match="parent descriptor"):
            harness._assert_parent_unchanged((before,), (after,))
    finally:
        descriptor.close()


def test_artifact_measurement_binds_hash_and_full_stable_identity(
    tmp_path: Path,
) -> None:
    path = tmp_path / "native-extension.bundle"
    path.write_bytes(b"first artifact bytes")
    path.chmod(0o500)

    first = harness._measure_artifact(path)
    assert first.sha256
    assert first.bytes == len(b"first artifact bytes")
    assert first.links == 1

    path.chmod(0o700)
    path.write_bytes(b"changed artifact bytes")
    path.chmod(0o500)
    second = harness._measure_artifact(path)
    assert second != first
    alias = tmp_path / "native-extension-alias.bundle"
    os.link(path, alias)
    with pytest.raises(RuntimeError, match="bound regular file is invalid"):
        harness._measure_artifact(path)


@pytest.mark.trusted_local
def test_runtime_worker_and_outer_supervisor_contract_are_narrow() -> None:
    runtime = harness._measure_runtime(Path(sys.executable).resolve())
    worker = harness._measure_worker(WORKER)

    assert runtime.bytes > 0
    assert worker.bytes == WORKER.stat().st_size
    assert harness.supervised_harness_subprocess_policy() == {
        "close_fds": True,
        "pass_fds": (),
    }
    runtime_identity = harness._path_free_file_identity(runtime)
    worker_identity = harness._path_free_file_identity(worker)
    assert set(runtime_identity) == set(worker_identity)
    assert all(
        "/" not in str(value)
        for identity in (runtime_identity, worker_identity)
        for value in identity.values()
    )


def test_isolated_harness_closes_inherited_fd_above_new_limit() -> None:
    script = """
import errno
import fcntl
import json
import os
from tests import _separation_native_spawn_canary_harness as harness

target = 5000
source = os.open("/dev/null", os.O_RDONLY)
os.dup2(source, target, inheritable=True)
if source != target:
    os.close(source)
before = fcntl.fcntl(target, fcntl.F_GETFD)
original = harness._prepare_isolated_descriptor_limit()
try:
    fcntl.fcntl(target, fcntl.F_GETFD)
except OSError as error:
    closed = error.errno == errno.EBADF
else:
    closed = False
print(json.dumps({
    "before": before,
    "closed": closed,
    "original_soft_limit": original,
    "new_soft_limit": harness._soft_descriptor_limit(),
}))
"""
    process = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPOSITORY,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert process.returncode == 0, process.stderr
    report = json.loads(process.stdout)
    assert report["before"] >= 0
    assert report["closed"] is True
    assert report["original_soft_limit"] > 5_000
    assert report["new_soft_limit"] == 4_096


def test_owned_child_cleanup_reaps_before_propagating_failure() -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )

    class TestNativeOwner:
        def __init__(self) -> None:
            self.pid = process.pid
            self.leader_reaped = False
            self.ownership_released = False
            self.ownership_lost = False

        def signal_owned_group(self, signal_number: int) -> None:
            os.killpg(self.pid, signal_number)

        def wait_nohang(self) -> int | None:
            return_code = process.poll()
            if return_code is None:
                return None
            self.leader_reaped = True
            self.ownership_released = True
            return return_code

    native_owner = TestNativeOwner()
    try:
        with pytest.raises(RuntimeError, match="synthetic post-spawn failure"):
            with harness._OwnedCanaryChild(native_owner):
                raise RuntimeError("synthetic post-spawn failure")
        with pytest.raises(ChildProcessError):
            os.waitpid(process.pid, os.WNOHANG)
    finally:
        process.returncode = -9
