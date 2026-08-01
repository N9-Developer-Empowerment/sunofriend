from __future__ import annotations

import hashlib
import fcntl
import os
import platform
import stat
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import sunofriend
from sunofriend import _separation_native_build_darwin as native_build
from sunofriend._separation_checkpoint_canonical import (
    canonical_sha256,
    plain,
)


REPOSITORY = Path(__file__).resolve().parents[1]
NATIVE_SOURCE = REPOSITORY / "src" / "sunofriend" / "_separation_native_spawn_darwin.c"


def test_checked_in_source_and_build_contract_hashes_are_current() -> None:
    source = NATIVE_SOURCE.read_bytes()

    assert hashlib.sha256(source).hexdigest() == (native_build._EXPECTED_SOURCE_SHA256)
    assert canonical_sha256(plain(native_build._BUILD_CONTRACT)) == (
        native_build._EXPECTED_BUILD_CONTRACT_SHA256
    )
    assert "TO_BE_REPLACED" not in (
        REPOSITORY / "src" / "sunofriend" / "_separation_native_build_darwin.py"
    ).read_text(encoding="utf-8")


def test_native_source_requires_and_exposes_compiled_build_identities() -> None:
    source = NATIVE_SOURCE.read_text(encoding="utf-8")

    assert "#ifndef SUNOFRIEND_NATIVE_SOURCE_SHA256" in source
    assert "#ifndef SUNOFRIEND_NATIVE_BUILD_CONTRACT_SHA256" in source
    assert (
        '"_SUNOFRIEND_NATIVE_SOURCE_SHA256",\n'
        "            SUNOFRIEND_NATIVE_SOURCE_SHA256"
    ) in source
    assert (
        '"_SUNOFRIEND_NATIVE_BUILD_CONTRACT_SHA256",\n'
        "            SUNOFRIEND_NATIVE_BUILD_CONTRACT_SHA256"
    ) in source
    assert source.count("PyModule_AddStringConstant(") == 2


def test_build_module_is_private_and_not_exported_by_the_package() -> None:
    assert native_build.__all__ == ()
    assert not hasattr(sunofriend, "_build_native_launcher")
    assert not any(
        path.is_file()
        for path in (REPOSITORY / "src" / "sunofriend").glob(
            "_separation_native_spawn_darwin*.so"
        )
    )


def test_off_platform_failure_is_write_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = tmp_path / "must-not-exist"

    monkeypatch.setattr(native_build, "_darwin_host", lambda: False)

    def unexpected_read() -> bytes:
        raise AssertionError("off-platform build read the packaged source")

    monkeypatch.setattr(
        native_build,
        "_read_packaged_source_once",
        unexpected_read,
    )
    with pytest.raises(RuntimeError, match="only on macOS"):
        native_build._build_native_launcher(cache_root=cache)

    assert not cache.exists()


def test_source_tamper_fails_before_cache_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = tmp_path / "must-not-exist"

    monkeypatch.setattr(native_build, "_darwin_host", lambda: True)
    monkeypatch.setattr(
        native_build,
        "_read_packaged_source_once",
        lambda: b"tampered source",
    )
    with pytest.raises(RuntimeError, match="pinned identity"):
        native_build._build_native_launcher(cache_root=cache)

    assert not cache.exists()


def test_tool_discovery_failure_is_write_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = tmp_path / "must-not-exist"

    monkeypatch.setattr(native_build, "_darwin_host", lambda: True)

    def missing_tools(source: bytes) -> native_build._BuildContext:
        assert hashlib.sha256(source).hexdigest() == (
            native_build._EXPECTED_SOURCE_SHA256
        )
        raise RuntimeError("missing audited tool")

    monkeypatch.setattr(
        native_build,
        "_discover_build_context",
        missing_tools,
    )
    with pytest.raises(RuntimeError, match="missing audited tool"):
        native_build._build_native_launcher(cache_root=cache)

    assert not cache.exists()


@pytest.mark.parametrize("architecture", ("arm64", "x86_64"))
def test_fixed_recipe_supports_only_the_two_audited_architectures(
    architecture: str,
) -> None:
    arguments = native_build._compile_arguments(
        compiler_path=Path("/audited/clang"),
        architecture=architecture,
        sdk_path=Path("/audited/MacOSX.sdk"),
        include_path=Path("/audited/python/include"),
        source_path="$SOURCE",
        object_path="$OBJECT",
        dependency_path="$DEPFILE",
    )
    link_arguments = native_build._link_arguments(
        linker_path=Path("/audited/bin/ld"),
        architecture=architecture,
        sdk_path=Path("/audited/MacOSX.sdk"),
        sdk_version="26.5",
        object_path="$OBJECT",
        direct_linker_input_path=Path("/audited/MacOSX.sdk/usr/lib/libSystem.B.tbd"),
        output_path="$OUTPUT",
    )

    assert arguments[0] == "/audited/clang"
    assert arguments[1] == "-c"
    assert arguments[arguments.index("-arch") + 1] == architecture
    assert "-mmacosx-version-min=12.0" in arguments
    assert "-Wl,-no_uuid" not in arguments
    assert "-bundle" not in arguments
    assert "/audited/MacOSX.sdk/usr/lib/libSystem.B.tbd" not in arguments
    assert (
        f'-DSUNOFRIEND_NATIVE_SOURCE_SHA256="{native_build._EXPECTED_SOURCE_SHA256}"'
    ) in arguments
    assert (
        "-DSUNOFRIEND_NATIVE_BUILD_CONTRACT_SHA256="
        f'"{native_build._EXPECTED_BUILD_CONTRACT_SHA256}"'
    ) in arguments
    assert arguments[-3:] == ("$SOURCE", "-o", "$OBJECT")
    assert link_arguments == (
        "/audited/bin/ld",
        "-arch",
        architecture,
        "-bundle",
        "-undefined",
        "dynamic_lookup",
        "-platform_version",
        "macos",
        "12.0",
        "26.5",
        "-syslibroot",
        "/audited/MacOSX.sdk",
        "-o",
        "$OUTPUT",
        "$OBJECT",
        "/audited/MacOSX.sdk/usr/lib/libSystem.B.tbd",
    )


def test_fixed_recipe_rejects_every_other_architecture() -> None:
    with pytest.raises(RuntimeError, match="unsupported"):
        native_build._compile_arguments(
            compiler_path=Path("/audited/clang"),
            architecture="universal2",
            sdk_path=Path("/audited/MacOSX.sdk"),
            include_path=Path("/audited/python/include"),
            source_path="$SOURCE",
            object_path="$OBJECT",
            dependency_path="$DEPFILE",
        )
    with pytest.raises(RuntimeError, match="unsupported"):
        native_build._link_arguments(
            linker_path=Path("/audited/bin/ld"),
            architecture="universal2",
            sdk_path=Path("/audited/MacOSX.sdk"),
            sdk_version="26.5",
            object_path="$OBJECT",
            direct_linker_input_path=Path(
                "/audited/MacOSX.sdk/usr/lib/libSystem.B.tbd"
            ),
            output_path="$OUTPUT",
        )


def test_receipt_decoder_rejects_duplicates_and_noncanonical_bytes() -> None:
    with pytest.raises(RuntimeError, match="duplicate"):
        native_build._decode_canonical_receipt(b'{"schema":1,"schema":2}')
    with pytest.raises(RuntimeError, match="canonical"):
        native_build._decode_canonical_receipt(b'{"schema": 1}')
    with pytest.raises(RuntimeError, match="canonical"):
        native_build._decode_canonical_receipt(b'{"schema":1}\\n')


def test_dependency_parser_preserves_make_escaped_path_characters(
    tmp_path: Path,
) -> None:
    dependencies = (
        tmp_path / "part space.h",
        tmp_path / "part\\slash.h",
        tmp_path / "part$dollar.h",
    )
    for dependency in dependencies:
        dependency.write_bytes(b"measured dependency")
    encoded = [
        str(dependency).replace("\\", "\\\\").replace(" ", "\\ ").replace("$", "$$")
        for dependency in dependencies
    ]
    depfile = tmp_path / "dependencies.d"
    depfile.write_text(
        f"sunofriend-native-output: {' '.join(encoded)}\n",
        encoding="utf-8",
    )
    depfile.chmod(0o600)

    parsed = native_build._parse_dependency_file(depfile)

    assert parsed == tuple(sorted(dependencies, key=str))


def test_dependency_parser_rejects_trailing_make_escape(
    tmp_path: Path,
) -> None:
    depfile = tmp_path / "dependencies.d"
    depfile.write_bytes(b"sunofriend-native-output: /private/tmp/header\\")
    depfile.chmod(0o600)

    with pytest.raises(RuntimeError, match="escaping is invalid"):
        native_build._parse_dependency_file(depfile)


def test_tool_timeout_kills_descendant_that_keeps_output_pipes_open() -> None:
    started = time.monotonic()

    with pytest.raises(RuntimeError, match="fixed build timeout"):
        native_build._run_tool(
            Path("/bin/sh"),
            ("-c", "/bin/sleep 30 & exit 0"),
            timeout=0.25,
        )

    assert time.monotonic() - started < 3.0


def test_tool_output_limit_kills_and_reaps_the_process_group() -> None:
    started = time.monotonic()

    with pytest.raises(RuntimeError, match="excessive build output"):
        native_build._run_tool(
            Path("/usr/bin/yes"),
            (),
            timeout=5.0,
        )

    assert time.monotonic() - started < 3.0


def test_tool_cleanup_uses_exact_pid_when_group_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_kill = os.kill
    exact_kills: list[tuple[int, int]] = []

    def missing_group(process_group: int, signal_number: int) -> None:
        del process_group, signal_number
        raise ProcessLookupError

    def record_exact(process_id: int, signal_number: int) -> None:
        exact_kills.append((process_id, signal_number))
        real_kill(process_id, signal_number)

    monkeypatch.setattr(native_build.os, "killpg", missing_group)
    monkeypatch.setattr(native_build.os, "kill", record_exact)

    with pytest.raises(RuntimeError, match="fixed build timeout"):
        native_build._run_tool(
            Path("/bin/sleep"),
            ("30",),
            timeout=0.1,
        )

    assert len(exact_kills) == 1
    assert exact_kills[0][0] > 0
    assert exact_kills[0][1] == native_build.signal.SIGKILL


def test_tool_launch_closes_an_unlisted_inheritable_descriptor() -> None:
    source_descriptor = os.open("/dev/null", os.O_RDONLY)
    inherited_candidate = fcntl.fcntl(
        source_descriptor,
        fcntl.F_DUPFD,
        200,
    )
    try:
        os.set_inheritable(inherited_candidate, True)
        program = (
            "import os,sys\n"
            "try:\n"
            " os.fstat(int(sys.argv[1]))\n"
            "except OSError:\n"
            " raise SystemExit(0)\n"
            "raise SystemExit(9)\n"
        )
        result = native_build._run_tool(
            Path(sys.executable),
            (
                "-I",
                "-S",
                "-c",
                program,
                str(inherited_candidate),
            ),
            timeout=3.0,
        )
    finally:
        os.close(inherited_candidate)
        os.close(source_descriptor)

    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""


@pytest.mark.skipif(
    sys.platform != "darwin",
    reason="Darwin sigaction layout is macOS-specific",
)
def test_tool_spawn_rejects_ignored_sigchld_in_isolated_parent() -> None:
    program = """
import signal
from pathlib import Path
from sunofriend._separation_native_build_darwin import _run_tool
signal.signal(signal.SIGCHLD, signal.SIG_IGN)
try:
    _run_tool(Path("/usr/bin/false"), (), timeout=1.0)
except RuntimeError as exc:
    raise SystemExit(0 if "default SIGCHLD" in str(exc) else 3)
raise SystemExit(4)
"""
    result = subprocess.run(
        (sys.executable, "-c", program),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        close_fds=True,
        check=False,
        timeout=5.0,
        cwd=REPOSITORY,
    )

    assert result.returncode == 0, result.stderr.decode(errors="replace")


@pytest.mark.skipif(
    sys.platform != "darwin",
    reason="Darwin sigaction layout is macOS-specific",
)
def test_tool_spawn_rejects_sa_nocldwait_in_isolated_parent() -> None:
    program = """
import ctypes
import signal
from pathlib import Path
from sunofriend._separation_native_build_darwin import _run_tool
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
current = Sigaction()
if sigaction(signal.SIGCHLD, None, ctypes.byref(current)) != 0:
    raise SystemExit(5)
current.flags |= 0x20
if sigaction(signal.SIGCHLD, ctypes.byref(current), None) != 0:
    raise SystemExit(6)
try:
    _run_tool(Path("/usr/bin/false"), (), timeout=1.0)
except RuntimeError as exc:
    raise SystemExit(0 if "SA_NOCLDWAIT" in str(exc) else 3)
raise SystemExit(4)
"""
    result = subprocess.run(
        (sys.executable, "-c", program),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        close_fds=True,
        check=False,
        timeout=5.0,
        cwd=REPOSITORY,
    )

    assert result.returncode == 0, result.stderr.decode(errors="replace")


@pytest.mark.trusted_local
@pytest.mark.skipif(
    sys.platform != "darwin" or platform.system() != "Darwin",
    reason="live native launcher build is macOS-only",
)
def test_live_build_is_signed_path_private_and_reused(tmp_path: Path) -> None:
    cache = tmp_path / "private-native-cache"
    first = native_build._build_native_launcher(cache_root=cache)
    document = first.receipt.to_dict()

    assert first.artifact_path.is_file()
    assert first.receipt_sha256 == first.receipt.sha256
    assert stat.S_IMODE(cache.stat().st_mode) == 0o700
    assert stat.S_IMODE(first.artifact_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(first.artifact_path.stat().st_mode) == 0o500
    receipt_path = first.artifact_path.parent / "build-receipt.json"
    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600
    assert receipt_path.read_bytes() == first.receipt.canonical_bytes()

    assert document["build_input"]["source"]["sha256"] == (
        native_build._EXPECTED_SOURCE_SHA256
    )
    assert document["build_input"]["build_contract_sha256"] == (
        native_build._EXPECTED_BUILD_CONTRACT_SHA256
    )
    assert len(document["prebuild_recipe_sha256"]) == 64
    assert len(document["recorded_artifact_input_provenance_sha256"]) == 64
    assert document["provenance_scope"] == {
        "recorded_inputs": (
            "prebuild_recipe_header_closure_compiled_object_explicit_sdk_libSystem_tbd"
        ),
        "dynamic_build_tool_runtime_closure_recorded": False,
    }
    compiled_object = document["build_invocation"]["compiled_object"]
    assert compiled_object["filename"] == "launcher-object.o"
    assert compiled_object["mode"] == 0o600
    assert len(compiled_object["sha256"]) == 64
    assert compiled_object["bytes"] > 0
    explicit_sdk_linker_inputs = document["build_invocation"][
        "explicit_sdk_linker_inputs"
    ]
    assert explicit_sdk_linker_inputs == [
        {
            "requested_logical_path": "$SDK/usr/lib/libSystem.tbd",
            "logical_path": "$SDK/usr/lib/libSystem.B.tbd",
            "sha256": document["build_input"]["toolchain"]["explicit_sdk_linker_input"][
                "sha256"
            ],
            "bytes": document["build_input"]["toolchain"]["explicit_sdk_linker_input"][
                "stat_identity"
            ]["bytes"],
        }
    ]
    assert document["recorded_artifact_input_provenance_sha256"] == (
        native_build._recorded_artifact_input_provenance_sha256(
            prebuild_recipe_sha256=document["prebuild_recipe_sha256"],
            header_closure=document["build_invocation"]["header_closure"],
            compiled_object=compiled_object,
            explicit_sdk_linker_inputs=explicit_sdk_linker_inputs,
        )
    )
    assert document["artifact"]["mach_o"]["architecture"] == platform.machine()
    assert document["artifact"]["mach_o"]["file_type_name"] == "MH_BUNDLE"
    assert document["artifact"]["mach_o"]["rpaths"] == []
    assert document["artifact"]["mach_o"]["linked_dylibs"] == [
        "/usr/lib/libSystem.B.dylib"
    ]
    assert document["artifact"]["mach_o"]["build_version"]["minimum"] == (
        native_build._packed_mach_version("12.0")
    )
    assert document["artifact"]["mach_o"]["code_signature"]["data_bytes"] > 0
    assert len(document["artifact"]["mach_o"]["uuid"]) == 32
    assert set(document["artifact"]["mach_o"]["uuid"]) <= set("0123456789abcdef")
    assert document["artifact"]["signing"]["kind"] == "adhoc"
    assert document["artifact"]["signing"]["verified_strict"] is True
    assert document["capabilities"]["native_artifact_imported"] is False
    assert document["capabilities"]["worker_started"] is False
    assert document["capabilities"]["separation_started"] is False

    receipt_text = first.receipt.canonical_bytes().decode("ascii")
    assert str(cache) not in receipt_text
    assert ".build-" not in receipt_text
    assert document["build_invocation"]["transient_paths_serialized"] is False
    assert "$SOURCE" in document["build_invocation"]["logical_compile_arguments"]
    assert "$OBJECT" in document["build_invocation"]["logical_compile_arguments"]
    assert "$OUTPUT" not in document["build_invocation"]["logical_compile_arguments"]
    assert (
        document["build_invocation"]["logical_link_arguments"][0]
        == (document["build_input"]["toolchain"]["linker"]["path"])
    )
    assert "$OBJECT" in document["build_invocation"]["logical_link_arguments"]
    assert "$OUTPUT" in document["build_invocation"]["logical_link_arguments"]
    artifact_bytes = first.artifact_path.read_bytes()
    assert native_build._EXPECTED_SOURCE_SHA256.encode("ascii") in artifact_bytes
    assert (
        native_build._EXPECTED_BUILD_CONTRACT_SHA256.encode("ascii") in artifact_bytes
    )
    assert native_build._NATIVE_MODULE_NAME not in sys.modules

    second = native_build._build_native_launcher(cache_root=cache)

    assert second.artifact_path != first.artifact_path
    assert second.artifact_path.read_bytes() == artifact_bytes
    assert (second.artifact_path.parent / native_build._OBJECT_NAME).read_bytes() == (
        first.artifact_path.parent / native_build._OBJECT_NAME
    ).read_bytes()
    assert (
        second.receipt.to_dict()["artifact"]["sha256"]
        == (document["artifact"]["sha256"])
    )
    assert (
        second.receipt.to_dict()["artifact"]["mach_o"]["uuid"]
        == (document["artifact"]["mach_o"]["uuid"])
    )
    assert (
        second.receipt.to_dict()["prebuild_recipe_sha256"]
        == (document["prebuild_recipe_sha256"])
    )
    assert (
        second.receipt.to_dict()["recorded_artifact_input_provenance_sha256"]
        == (document["recorded_artifact_input_provenance_sha256"])
    )
    assert (
        second.receipt.to_dict()["build_invocation"]["compiled_object"]["sha256"]
        == compiled_object["sha256"]
    )
    assert (
        len([path for path in cache.iterdir() if path.name.startswith(".fresh-build-")])
        == 2
    )


@pytest.mark.trusted_local
@pytest.mark.skipif(
    sys.platform != "darwin" or platform.system() != "Darwin",
    reason="live native launcher build is macOS-only",
)
def test_fresh_build_never_trusts_a_tampered_previous_artifact(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "private-native-cache"
    built = native_build._build_native_launcher(cache_root=cache)
    payload = built.artifact_path.read_bytes()
    os.chmod(built.artifact_path, 0o700)
    built.artifact_path.write_bytes(payload[:-1] + bytes([payload[-1] ^ 1]))
    os.chmod(built.artifact_path, 0o500)

    fresh = native_build._build_native_launcher(cache_root=cache)

    assert fresh.artifact_path != built.artifact_path
    assert (
        fresh.receipt.to_dict()["artifact"]["sha256"]
        != hashlib.sha256(built.artifact_path.read_bytes()).hexdigest()
    )


@pytest.mark.trusted_local
@pytest.mark.skipif(
    sys.platform != "darwin" or platform.system() != "Darwin",
    reason="live native launcher build is macOS-only",
)
def test_concurrent_builds_remain_distinct_and_reproducible(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "private-native-cache"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: native_build._build_native_launcher(cache_root=cache),
                range(2),
            )
        )

    assert len({result.artifact_path for result in results}) == 2
    assert (
        len({result.receipt.to_dict()["artifact"]["sha256"] for result in results}) == 1
    )
    assert (
        len([path for path in cache.iterdir() if path.name.startswith(".fresh-build-")])
        == 2
    )
