from __future__ import annotations

from copy import deepcopy
import json

import pytest

from sunofriend.remix_musicfm_fma_runtime_resolution import (
    _CANDIDATE_WHEELS,
    MUSICFM_FMA_RUNTIME_RESOLUTION_SCHEMA,
    create_musicfm_fma_runtime_resolution,
    validate_musicfm_fma_runtime_resolution,
)
from sunofriend.source_receipt import document_sha256


def _runtime_plan() -> dict:
    return {"document_sha256": "a" * 64}


def _report() -> bytes:
    installs = []
    for name, version, filename, _bytes, sha256, requested in _CANDIDATE_WHEELS:
        installs.append(
            {
                "download_info": {
                    "url": f"https://example.invalid/{filename.replace('+', '%2B')}",
                    "archive_info": {"hashes": {"sha256": sha256}},
                },
                "is_direct": False,
                "is_yanked": False,
                "requested": requested,
                "metadata": {"name": name, "version": version},
            }
        )
    return json.dumps(
        {
            "version": "1",
            "pip_version": "25.3",
            "install": installs,
            "environment": {
                "platform_system": "Darwin",
                "platform_machine": "arm64",
                "python_version": "3.9",
                "sys_platform": "darwin",
            },
        },
        sort_keys=True,
    ).encode()


def test_partial_resolution_records_marker_blocker_and_no_authority() -> None:
    report = _report()
    resolution = create_musicfm_fma_runtime_resolution(
        _runtime_plan(), resolver_report_bytes=report, repository_commit="b" * 40
    )

    assert resolution["schema"] == MUSICFM_FMA_RUNTIME_RESOLUTION_SCHEMA
    assert resolution["status"].startswith("partial_candidate_resolution")
    assert resolution["candidate_wheels"]["count"] == 26
    assert resolution["candidate_wheels"]["observed_total_bytes"] == 3_319_356_874
    assert resolution["candidate_wheels"]["complete_transitive_closure"] is False
    assert resolution["marker_audit"]["native_windows_resolution_required"] is True
    assert resolution["next_gate"]["downloads_wheels"] is False
    assert all(value is False for value in resolution["authority"].values())
    assert all(value is False for value in resolution["effects"].values())
    assert (
        validate_musicfm_fma_runtime_resolution(
            resolution, _runtime_plan(), resolver_report_bytes=report
        )
        == resolution
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda row: row["candidate_wheels"].update(installable_lock=True),
        lambda row: row["gates"].update(
            native_windows_environment_markers_resolved=True
        ),
        lambda row: row["authority"].update(wheel_download_authorized=True),
        lambda row: row["effects"].update(dependency_installed=True),
        lambda row: row["marker_audit"].update(
            native_windows_resolution_required=False
        ),
    ],
)
def test_partial_resolution_rejects_rehashed_promotion(mutate) -> None:
    report = _report()
    resolution = create_musicfm_fma_runtime_resolution(
        _runtime_plan(), resolver_report_bytes=report, repository_commit="b" * 40
    )
    changed = deepcopy(resolution)
    mutate(changed)
    changed.pop("document_sha256")
    changed["document_sha256"] = document_sha256(changed)
    with pytest.raises(ValueError, match="evidence or authority"):
        validate_musicfm_fma_runtime_resolution(
            changed, _runtime_plan(), resolver_report_bytes=report
        )


def test_partial_resolution_rejects_changed_report_identity() -> None:
    report = _report()
    resolution = create_musicfm_fma_runtime_resolution(
        _runtime_plan(), resolver_report_bytes=report, repository_commit="b" * 40
    )
    changed_report = json.loads(report)
    changed_report["install"][0]["metadata"]["version"] = "9.9"
    with pytest.raises(ValueError, match="identity changed"):
        validate_musicfm_fma_runtime_resolution(
            resolution,
            _runtime_plan(),
            resolver_report_bytes=json.dumps(changed_report).encode(),
        )
