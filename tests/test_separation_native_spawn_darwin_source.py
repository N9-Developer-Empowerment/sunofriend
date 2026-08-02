from __future__ import annotations

import re
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
SOURCE = REPOSITORY / "src" / "sunofriend" / "_separation_native_spawn_darwin.c"
PYPROJECT = REPOSITORY / "pyproject.toml"
MANIFEST = REPOSITORY / "MANIFEST.in"


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def _function_body(source: str, name: str, next_name: str) -> str:
    start = source.index(name)
    end = source.index(next_name, start)
    return source[start:end]


def test_native_launcher_is_packaged_as_source_but_not_registered_to_compile() -> None:
    source_name = SOURCE.name
    pyproject = PYPROJECT.read_text(encoding="utf-8")
    manifest = MANIFEST.read_text(encoding="utf-8")

    assert SOURCE.is_file()
    assert f'"{source_name}",' in pyproject
    assert f"include src/sunofriend/{source_name}" in manifest.splitlines()
    assert "[[tool.setuptools.ext-modules]]" not in pyproject
    assert "Extension(" not in pyproject


def test_source_is_mac_only_and_referenced_only_by_private_builder() -> None:
    source = _source()
    python_sources = list((REPOSITORY / "src" / "sunofriend").glob("*.py"))
    runtime_references = [
        path.name
        for path in python_sources
        if "_separation_native_spawn_darwin" in path.read_text(encoding="utf-8")
    ]

    assert "#if !defined(__APPLE__) || !defined(__MACH__)" in source
    assert (
        '#error "Sunofriend\'s native spawn boundary is supported only on macOS."'
        in source
    )
    assert "PyInit__separation_native_spawn_darwin" in source
    assert '"_spawn_bound_fake_worker"' in source
    assert sorted(runtime_references) == [
        "_separation_native_build_darwin.py",
        "_separation_native_session_darwin.py",
    ]
    assert "_separation_native_build_darwin" not in (
        REPOSITORY / "src" / "sunofriend" / "__init__.py"
    ).read_text(encoding="utf-8")
    assert "_separation_native_build_darwin" not in (
        REPOSITORY / "src" / "sunofriend" / "cli.py"
    ).read_text(encoding="utf-8")


def test_source_uses_only_direct_darwin_spawn_with_close_all_default() -> None:
    source = _source()

    assert source.count("status = posix_spawn(") == 1
    assert "POSIX_SPAWN_CLOEXEC_DEFAULT" in source
    assert "posix_spawnattr_setflags(attributes, flags)" in source
    assert "POSIX_SPAWN_SETSID" in source
    assert "POSIX_SPAWN_SETSIGDEF" in source
    assert "POSIX_SPAWN_SETSIGMASK" in source
    assert "posix_spawnattr_setpgroup" not in source
    assert "sigfillset(&default_signals)" in source
    assert "sigdelset(&default_signals, SIGKILL)" in source
    assert "sigdelset(&default_signals, SIGSTOP)" in source
    assert "sigemptyset(&empty_mask)" in source
    assert "posix_spawnattr_setsigdefault(attributes, &default_signals)" in source
    assert "posix_spawnattr_setsigmask(attributes, &empty_mask)" in source
    assert "Py_BEGIN_ALLOW_THREADS" not in source
    assert "Py_END_ALLOW_THREADS" not in source

    forbidden_calls = (
        "fork",
        "vfork",
        "system",
        "popen",
        "execl",
        "execle",
        "execlp",
        "execv",
        "execve",
        "execvp",
        "posix_spawnp",
        "posix_spawn_file_actions_addinherit_np",
    )
    for name in forbidden_calls:
        assert re.search(rf"\b{re.escape(name)}\s*\(", source) is None


def test_descriptor_changes_are_child_actions_and_parent_table_is_untouched() -> None:
    source = _source()
    actions = _function_body(
        source,
        "sunofriend_add_child_file_actions(",
        "sunofriend_configure_spawn_attributes(",
    )

    assert "posix_spawn_file_actions_adddup2(" in actions
    assert "posix_spawn_file_actions_addopen(" in actions
    assert "posix_spawn_file_actions_addclose(" in actions
    for direct_mutator in ("open", "close", "dup", "dup2", "pipe", "socket"):
        assert re.search(rf"\b{direct_mutator}\s*\(", source) is None
    assert "fcntl(source_fds[left], F_GETFD)" in source
    assert "fcntl(source_fds[left], F_GETFL)" in source
    for mutating_fcntl in ("F_DUPFD", "F_DUPFD_CLOEXEC", "F_SETFD", "F_SETFL"):
        assert mutating_fcntl not in source

    copy_to_scratch = actions.index(
        "source_fds[index],\n            scratch_fds[index]"
    )
    close_sources = actions.index(
        "posix_spawn_file_actions_addclose(actions, source_fds[index])"
    )
    map_to_target = actions.index(
        "scratch_fds[index],\n            sunofriend_target_fds[index]"
    )
    close_scratch = actions.rindex(
        "posix_spawn_file_actions_addclose(actions, scratch_fds[index])"
    )
    open_stdin = actions.index('SUNOFRIEND_STDIN_FD,\n        "/dev/null"')
    assert copy_to_scratch < close_sources < map_to_target < close_scratch < open_stdin


def test_scratch_descriptors_exclude_sources_targets_and_each_other() -> None:
    source = _source()
    selector = _function_body(
        source,
        "sunofriend_fd_is_reserved(",
        "sunofriend_add_child_file_actions(",
    )

    assert "int candidate = sunofriend_target_fds[transport_count - 1] + 1" in source
    assert "candidate == sunofriend_target_fds[index]" in selector
    assert "candidate == source_fds[index]" in selector
    assert "candidate == scratch_fds[index]" in selector
    assert "sunofriend_choose_scratch_fds(" in source
    assert "transport descriptors must be distinct" in source
    assert "transport descriptors must be at least 3" in source
    assert "transport descriptors must have distinct backing nodes" in source
    assert "data transports must be regular files and readiness" in source
    assert "&& !S_ISREG(backing_nodes[left].st_mode)" in source
    assert "&& !S_ISFIFO(backing_nodes[left].st_mode)" in source
    assert "fcntl(source_fds[left], F_GETFD) != FD_CLOEXEC" in source
    assert "(status_flags & O_ACCMODE) != required_access_modes[left]" in source
    assert "(status_flags & O_APPEND) != 0" in source
    assert "left != 2" in source
    assert "(status_flags & O_NONBLOCK) != 0" in source
    assert "sigaction(SIGCHLD, NULL, &disposition)" in source
    assert "disposition.sa_handler != SIG_DFL" in source
    assert "(disposition.sa_flags & SA_NOCLDWAIT) != 0" in source
    assert "sunofriend_validate_parent_sigchld() != 0" in source


def test_child_stdio_environment_and_transport_numbers_are_fixed() -> None:
    source = _source()
    environment = _function_body(
        source,
        "sunofriend_worker_environment[]",
        "sunofriend_contains_nul(",
    )

    assert source.count('"/dev/null"') == 3
    assert source.count('"/dev/null",\n        O_RDONLY') == 1
    assert source.count('"/dev/null",\n        O_WRONLY') == 2
    assert "SUNOFRIEND_REQUEST_FD = 3" in source
    assert "SUNOFRIEND_RESULT_FD = 4" in source
    assert "SUNOFRIEND_CHECKPOINT_FD = 5" in source
    assert "SUNOFRIEND_READY_FD = 6" in source
    assert "SUNOFRIEND_RELEASE_FD = 7" in source
    assert "worker must set FD_CLOEXEC on them as its first user-code action" in source
    assert "sunofriend_worker_environment" in source
    assert re.findall(r'^\s+"([^"]+)",$', environment, flags=re.MULTILINE) == [
        "LANG=C",
        "LC_ALL=C",
        "TZ=UTC",
    ]
    assert '"PATH=' not in source
    assert '"PYTHON' not in source
    assert re.search(r"\benviron\b", source) is None


def test_executable_and_worker_are_bounded_bytes_with_exact_argv_template() -> None:
    source = _source()

    assert "value[0] != '/'" in source
    assert "sunofriend_contains_nul" in source
    assert "PyBytes_CheckExact(path)" in source
    assert "char *native_arguments[6]" in source
    assert 'native_arguments[1] = "-I"' in source
    assert 'native_arguments[2] = "-B"' in source
    assert 'native_arguments[3] = "-S"' in source
    assert "native_arguments[4] = PyBytes_AS_STRING(bound_worker_entrypoint)" in source
    assert "native_arguments[5] = NULL" in source
    assert "PyBytes_AS_STRING(bound_executable)" in source


def test_child_owner_is_allocated_before_spawn_and_retains_lifecycle() -> None:
    source = _source()
    spawn = _function_body(
        source,
        "sunofriend_spawn_bound_worker(",
        "sunofriend_spawn_bound_fake_worker(",
    )
    allocation = spawn.index("owned_child = PyObject_New(")
    native_spawn = spawn.index("status = posix_spawn(")
    bind_pid = spawn.index("owned_child->pid = child_pid")
    returned = spawn.index("return (PyObject *)owned_child")

    assert allocation < native_spawn < bind_pid < returned
    assert "PyLong_FromLong((long)child_pid)" not in spawn
    assert "owned_child->spawned = true" in spawn
    assert "Py_DECREF(owned_child)" not in spawn
    assert '"_OwnedSpawnChild"' in source
    assert ".tp_new" not in source
    assert "PyType_Ready(&SunofriendOwnedSpawnChildType)" in source


def test_no_start_is_a_code_tagged_nonconstructible_owner_not_an_exception() -> None:
    source = _source()
    spawn = _function_body(
        source,
        "sunofriend_spawn_bound_worker(",
        "sunofriend_spawn_bound_fake_worker(",
    )
    getters = _function_body(
        source,
        "sunofriend_owned_child_get_start_state(",
        "sunofriend_owned_child_get_leader_reaped(",
    )
    failure_tail = spawn[spawn.index("fail:") :]

    assert "SUNOFRIEND_NO_START_FILE_ACTIONS_INIT" in source
    assert "SUNOFRIEND_NO_START_FILE_ACTIONS" in source
    assert "SUNOFRIEND_NO_START_ATTRIBUTES_INIT" in source
    assert "SUNOFRIEND_NO_START_ATTRIBUTES" in source
    assert "SUNOFRIEND_NO_START_POSIX_SPAWN" in source
    assert '"started_owned"' in getters
    assert '"not_started"' in getters
    assert '"invalid"' in getters
    assert '"file_actions_init"' in getters
    assert '"file_actions"' in getters
    assert '"attributes_init"' in getters
    assert '"attributes"' in getters
    assert '"posix_spawn"' in getters
    assert '"start_state"' in source
    assert '"no_start_stage"' in source
    assert '"native_status"' in source
    assert "owned_child->no_start_stage = no_start_stage" in failure_tail
    assert "owned_child->native_status = status" in failure_tail
    assert "return (PyObject *)owned_child" in failure_tail
    assert "PyErr_" not in failure_tail
    assert "Py_DECREF(owned_child)" not in failure_tail
    assert "SpawnNotStarted" not in source
    assert ".tp_new" not in source

    for enum_name in (
        "SUNOFRIEND_NO_START_FILE_ACTIONS_INIT",
        "SUNOFRIEND_NO_START_FILE_ACTIONS",
        "SUNOFRIEND_NO_START_ATTRIBUTES_INIT",
        "SUNOFRIEND_NO_START_ATTRIBUTES",
        "SUNOFRIEND_NO_START_POSIX_SPAWN",
    ):
        assert (
            f"if (status != 0) {{\n"
            f"        no_start_stage = {enum_name};\n"
            "        goto fail;\n"
            "    }"
        ) in spawn

    status_check = spawn.index("if (status != 0)", spawn.index("status = posix_spawn("))
    bind_pid = spawn.index("owned_child->pid = child_pid")
    bind_spawned = spawn.index("owned_child->spawned = true")
    assert status_check < bind_pid < bind_spawned


def test_ready_release_entrypoint_is_fixed_and_reuses_exact_owner_boundary() -> None:
    source = _source()
    wrapper = _function_body(
        source,
        "sunofriend_spawn_bound_fake_worker_with_ready_release(",
        "sunofriend_spawn_methods[]",
    )

    assert '"O!O!iiiii:_spawn_bound_fake_worker_with_ready_release"' in wrapper
    assert "SUNOFRIEND_READY_RELEASE_TRANSPORT_COUNT" in wrapper
    assert "sunofriend_spawn_bound_worker(" in wrapper
    assert source.count("status = posix_spawn(") == 1
    assert '"Private fixed ready/release canary boundary; production worker "' in source
    assert '"integration remains unavailable."' in source

def test_child_owner_exact_wait_signal_release_and_emergency_cleanup() -> None:
    source = _source()
    cleanup = _function_body(
        source,
        "sunofriend_emergency_kill_and_reap(",
        "sunofriend_owned_child_dealloc(",
    )
    wait = _function_body(
        source,
        "sunofriend_owned_child_wait_nohang(",
        "sunofriend_owned_child_signal_group(",
    )
    assert "kill(-child->pid, SIGKILL)" in cleanup
    assert "kill(child->pid, SIGKILL)" not in cleanup
    assert "sunofriend_poll_owned_terminal(child, &terminal)" in cleanup
    assert "waitpid(child->pid, &observed_wait_status, 0)" not in cleanup
    assert "SUNOFRIEND_EMERGENCY_REAP_ATTEMPTS" in cleanup
    assert "nanosleep(&remaining_pause, &remaining_pause)" in cleanup
    assert "unbounded wait" in cleanup
    assert cleanup.index("sunofriend_poll_owned_terminal(") < cleanup.index(
        "kill(-child->pid, SIGKILL)"
    )
    terminal = _function_body(
        source,
        "sunofriend_poll_owned_terminal(",
        "sunofriend_emergency_kill_and_reap(",
    )
    assert "waitid(" in terminal
    assert "WEXITED | WNOHANG | WNOWAIT" in terminal
    assert "proc_listpgrppids(" in terminal
    assert "group_member_count != 1" in terminal
    assert "group_members[0] != child->pid" in terminal
    assert terminal.index("proc_listpgrppids(") < terminal.index("waitpid(")
    assert "child->leader_exit_observed = true" in terminal
    assert "child->leader_reaped = true" in terminal
    assert "child->group_empty = true" in terminal
    assert "child->ownership_released = true" in terminal
    assert "sunofriend_poll_owned_terminal(child, &terminal)" in wait
    assert "native child ownership was lost before exact group terminality" in wait
    assert "signal_number != SIGTERM && signal_number != SIGKILL" in source
    signal_group = _function_body(
        source,
        "sunofriend_owned_child_signal_group(",
        "sunofriend_owned_child_matches_identity(",
    )
    assert "sunofriend_poll_owned_terminal(child, &terminal)" in signal_group
    assert signal_group.index("sunofriend_poll_owned_terminal(") < signal_group.index(
        "kill(-child->pid, signal_number)"
    )
    assert "native child ownership was lost before group signal" in signal_group
    assert "kill(-child->pid, 0)" not in source
    assert "POSIX_SPAWN_SETSID makes pid the exact private session" in cleanup
    assert "child->ownership_released = true" in terminal
    assert "child->ownership_lost = true" in terminal
    assert '"leader_exit_observed"' in source
    assert '"group_empty"' in source
    assert "|| child->ownership_lost" in source
    assert "child->owner_pid == getpid()" in source
    assert "owned_child->owner_pid = getpid()" in source
    assert source.count("child->owner_pid != getpid()") >= 3


def test_child_owner_observes_process_image_without_exporting_authority() -> None:
    source = _source()
    observer = _function_body(
        source,
        "sunofriend_owned_child_observe_process_image(",
        "sunofriend_owned_child_snapshot_executable_regions(",
    )

    assert '"observe_owned_process_image"' in source
    assert "proc_pidpath(" in observer
    assert "csops(" in observer
    assert "SUNOFRIEND_CS_OPS_CDHASH" in observer
    assert "clock_gettime(CLOCK_MONOTONIC" in observer
    assert "SUNOFRIEND_PROCESS_IMAGE_OBSERVATION_SECONDS" in observer
    assert "nanosleep(&remaining_pause, &remaining_pause)" in observer
    assert "strcmp(current_path, expected_path)" in observer
    assert "strcmp(current_path, launcher_path)" in observer
    assert "native child process image path differs" in observer
    assert "native child process image CDHash differs" in observer
    assert '"matched_expected_process_image"' in observer
    assert "child->owner_pid != getpid()" in observer
    assert "child->ownership_released" in observer
    assert "child->ownership_lost" in observer
    getset = _function_body(
        source,
        "sunofriend_owned_child_getset[]",
        "SunofriendOwnedSpawnChildType =",
    )
    assert '"pid"' not in getset
    assert '"pgid"' not in getset


def test_child_owner_snapshots_executable_regions_without_exporting_pid() -> None:
    source = _source()
    observer = _function_body(
        source,
        "sunofriend_owned_child_snapshot_executable_regions(",
        "sunofriend_owned_child_methods[]",
    )

    assert '"snapshot_owned_executable_regions"' in source
    assert "proc_pidinfo(" in observer
    assert "PROC_PIDREGIONPATHINFO" in observer
    assert "SUNOFRIEND_EXECUTABLE_REGION_LIMIT" in observer
    assert "SUNOFRIEND_VM_PROT_EXECUTE" in observer
    assert "child->owner_pid != getpid()" in observer
    assert "child->ownership_released" in observer
    assert "child->ownership_lost" in observer
    assert "sunofriend_poll_owned_terminal(child, &terminal)" in observer
    assert "native child exited during executable-region snapshot" in observer
    assert "PyBytes_FromStringAndSize(" in observer
    assert '"(OKKKI)"' in observer
    assert "PyLong_FromLong((long)child->pid)" not in observer
    assert "PyLong_FromLong((long)child->pid)" not in source
