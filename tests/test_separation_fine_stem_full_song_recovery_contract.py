from __future__ import annotations

import ast
from pathlib import Path

import sunofriend.separation_fine_stem_full_song_recovery as recovery
import sunofriend.separation_fine_stem_full_song_recovery_contract as contract


def test_recovery_public_surface_remains_on_execution_facade() -> None:
    assert recovery.validate_recovery_request.__module__ == recovery.__name__
    assert recovery.validate_recovery_report.__module__ == recovery.__name__
    assert recovery.recovery_request_sha256.__module__ == recovery.__name__
    assert recovery.recovery_report_sha256.__module__ == recovery.__name__
    assert recovery.RECOVERY_REQUEST_SCHEMA == contract.RECOVERY_REQUEST_SCHEMA
    assert recovery.RECOVERY_REQUEST_STATUS == contract.RECOVERY_REQUEST_STATUS
    assert recovery.RECOVERY_REPORT_SCHEMA == contract.RECOVERY_REPORT_SCHEMA
    assert recovery.RECOVERY_REPORT_STATUS == contract.RECOVERY_REPORT_STATUS


def test_recovery_contract_does_not_import_execution_dependencies() -> None:
    source = Path(contract.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    relative_imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.level
    }

    assert imported_roots.isdisjoint({"numpy", "resource", "stat", "tempfile", "time"})
    assert relative_imports == {
        "_private_verified_audio_inputs",
        "separation_fine_stem_full_song_execution_contract",
        "separation_fine_stem_full_song_plan_contract",
    }
    assert contract.__all__ == [
        "RECOVERY_REPORT_SCHEMA",
        "RECOVERY_REPORT_STATUS",
        "RECOVERY_REQUEST_SCHEMA",
        "RECOVERY_REQUEST_STATUS",
        "recovery_report_sha256",
        "recovery_request_sha256",
        "validate_recovery_report",
        "validate_recovery_request",
    ]
