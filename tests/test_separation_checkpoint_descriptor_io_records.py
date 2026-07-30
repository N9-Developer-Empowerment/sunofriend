from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Mapping

from sunofriend._separation_checkpoint_lease_records import (
    expected_acquisition_evidence,
)
from tests._separation_checkpoint_fixtures import (
    canonical_sha256 as _canonical_sha256,
)
from tests._separation_checkpoint_fixtures import (
    checkpoint_fixture as _checkpoint_fixture,
)
from tests._separation_checkpoint_fixtures import (
    inspect_checkpoint as _inspect_checkpoint,
)
from tests._separation_checkpoint_fixtures import torch_zip as _torch_zip


_SOURCE_ROOT = Path(__file__).parents[1] / "src" / "sunofriend"


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def test_descriptor_io_module_has_only_the_bounded_io_surface() -> None:
    source = (
        _SOURCE_ROOT / "_separation_checkpoint_descriptor_io.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_modules: list[tuple[str, int, tuple[str, ...]]] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported_modules.extend(
                ("", 0, (alias.name,)) for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            imported_modules.append(
                (
                    node.module or "",
                    node.level,
                    tuple(alias.name for alias in node.names),
                )
            )
    assert imported_modules == [
        ("", 0, ("hashlib",)),
        ("", 0, ("os",)),
        ("separation_checkpoint_inspection", 1, ("MAX_CHECKPOINT_BYTES",)),
    ]
    assert [
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    ] == [
        "_hash_descriptor",
        "_file_identity",
        "_file_identity_document",
        "_close_if_owned",
    ]

    os_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "os"
    }
    assert os_calls == {"close", "fstat", "lseek", "pread"}
    assert not {
        "dup",
        "dup2",
        "execve",
        "fork",
        "open",
        "posix_spawn",
        "set_inheritable",
    } & os_calls


def test_pure_acquisition_evidence_matches_an_independent_oracle(
    tmp_path: Path,
) -> None:
    fixture = _checkpoint_fixture(tmp_path, _torch_zip())
    inspection = _plain(_inspect_checkpoint(fixture))
    request = fixture["trusted_request"]
    identity = inspection["checkpoint"]["file_identity"]

    assert expected_acquisition_evidence(
        file_identity=identity,
        request=request,
        trusted_inspection=inspection,
    ) == {
        "bindings": {
            "worker_request_sha256": request.request_sha256,
            "preflight_sha256": request.preflight_sha256,
            "acceptance_artifact_sha256": request.acceptance_artifact_sha256,
            "trusted_checkpoint_inspection_sha256": inspection[
                "inspection_sha256"
            ],
            "checkpoint_sha256": request.checkpoint_sha256,
            "checkpoint_bytes": request.checkpoint_bytes,
            "checkpoint_file_identity_sha256": _canonical_sha256(identity),
            "classification_evidence_sha256": inspection["classification"][
                "classification_evidence_sha256"
            ],
            "archive_evidence_sha256": _canonical_sha256(
                inspection["archive"]
            ),
            "pickle_evidence_sha256": _canonical_sha256(
                inspection["pickle"]
            ),
        },
        "classification": {
            "container_kind": inspection["classification"]["container_kind"],
            "confidence": inspection["classification"]["confidence"],
            "evidence_equal_to_trusted_inspection": True,
        },
        "archive_metadata_parsed": inspection["archive"][
            "archive_metadata_parsed"
        ],
        "pickle_opcodes_parsed": inspection["archive"][
            "pickle_metadata_parsed"
        ],
    }
