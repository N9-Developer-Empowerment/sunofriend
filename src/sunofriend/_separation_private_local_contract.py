"""Immutable contract and installed profile for private local separation.

This module contains no workflow orchestration.  It centralises the status
vocabulary, product-permission boundary and the one accepted local backend
profile so the start and finish services cannot drift independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

from ._separation_private_backend_adapter_contract import (
    _load_verified_private_separation_backend_adapter_contract,
)


SCHEMA = "sunofriend.private-separation-local-start.v1"
DOCTOR_STATUS = "private_two_stem_local_profile_ready"
PREPARED_STATUS = "private_two_stem_request_ready_explicit_execution_required"
INCOMPLETE_STATUS = "private_two_stem_execution_incomplete_resume_required"
REVIEW_STATUS = "private_two_stem_review_ready_human_listening_required"
REPORT_NAME = "private-separation-local-start.json"
PLAN_DIRECTORY = "PLAN"
REQUEST_DIRECTORY = "REQUEST"
EXECUTION_DIRECTORY = "EXECUTION"
REVIEW_DIRECTORY = "REVIEW"
FINISH_DIRECTORY = "FINISH"
EQUIVALENCE_DIRECTORY = "EQUIVALENCE"
ASSESSMENT_DIRECTORY = "ASSESSMENT"
PROJECT_DIRECTORY = "PROJECT"
VALIDATION_DIRECTORY = "MIDI-WAV-ZIP"
IMPORTED_STATUS = "private_two_stem_stems_imported_inactive_confirmation_required"
PRESENT_STATUS = "private_two_stem_project_present_activation_verification_required"
ACTIVATED_STATUS = "private_two_stem_stems_active_midi_confirmation_required"
VALIDATED_STATUS = "private_two_stem_midi_wav_zip_created_listening_required"

# Keep this complete mapping in one module.  Every stage copies it into its
# response instead of sharing a mutable response object.
FALSE_PRODUCT_PERMISSIONS: Mapping[str, bool] = MappingProxyType({
    "automatic_selection": False,
    "private_output_import_permitted": False,
    "product_route_permitted": False,
    "publication_permitted": False,
    "simple_mode_available": False,
    "source_graph_activation": False,
    "studio_import_available": False,
    "tui_route_available": False,
})


@dataclass(frozen=True)
class PrivateSeparationLocalProfile:
    """Exact local evidence and runtime paths for the accepted private backend."""

    repository_root: Path
    adapter_report: Path
    design_report: Path
    coverage_report: Path
    runtime_launcher: Path
    source_root: Path
    checkpoint: Path
    companion_root: Path


ProfileChecker = Callable[[PrivateSeparationLocalProfile], Mapping[str, Any]]


def resolve_private_separation_local_profile(
    repository_root: str | Path,
) -> PrivateSeparationLocalProfile:
    """Resolve the one accepted local Kim profile without scanning the Mac."""

    root = Path(repository_root).expanduser().absolute()
    private_model = (
        Path.home() / ".local/share/sunofriend/private-evaluation/kim-vocal-2-mlx-v1"
    )
    return PrivateSeparationLocalProfile(
        repository_root=root,
        adapter_report=(
            root / "work/separation-bakeoff/"
            "private-separation-backend-adapter-contract-v2-py313/"
            "private-separation-backend-adapter-contract.json"
        ),
        design_report=(
            root / "work/separation-bakeoff/private-separation-route-design-v1/"
            "private-separation-route-design.json"
        ),
        coverage_report=(
            root / "work/separation-bakeoff/multi-song-private-pilot-coverage-v3/"
            "private-separation-multi-song-private-pilot-coverage.json"
        ),
        runtime_launcher=root / "work/private-runtime-python313/venv/bin/python",
        source_root=private_model / "mlx-audio-source",
        checkpoint=private_model / "model.safetensors",
        companion_root=private_model / "checkpoint-directory",
    )


def check_private_separation_local_profile(
    profile: PrivateSeparationLocalProfile,
    *,
    adapter_loader: Callable[..., Mapping[str, Any]] = (
        _load_verified_private_separation_backend_adapter_contract
    ),
) -> dict[str, Any]:
    """Deeply reverify the installed backend profile without writing files."""

    if not profile.repository_root.is_dir():
        raise FileNotFoundError(
            f"Sunofriend repository root is missing: {profile.repository_root}"
        )
    adapter = dict(
        adapter_loader(
            profile.adapter_report,
            design_report_path=profile.design_report,
            coverage_report_path=profile.coverage_report,
            repository_root=profile.repository_root,
            runtime_launcher_path=profile.runtime_launcher,
            source_root=profile.source_root,
            checkpoint_path=profile.checkpoint,
            companion_root=profile.companion_root,
        )
    )
    document = adapter["document"]
    backend = document["backend"]
    return {
        "schema": SCHEMA,
        "status": DOCTOR_STATUS,
        "candidate_id": backend["candidate_id"],
        "primary_roles": ["vocals", "instrumental"],
        "diagnostic_roles": ["reconstruction"],
        "adapter": {
            "sha256": adapter["sha256"],
            "document_sha256": document["document_sha256"],
        },
        "runtime": {
            "python": str(profile.runtime_launcher),
            "checkpoint": str(profile.checkpoint),
            "device_options": ["gpu", "cpu"],
        },
        "readiness": {
            "accepted_private_profile_verified": True,
            "offline_after_installed_profile_verified": True,
            "finished_mix_to_two_stem_execution_available": True,
            "human_review_required_before_downstream_use": True,
            "public_multi_stem_separator_available": False,
        },
        "permissions": dict(FALSE_PRODUCT_PERMISSIONS),
        "effects": {
            "filesystem_write": False,
            "model_run": False,
            "product_contract_mutated": False,
        },
    }


def private_separation_backend_kwargs(
    profile: PrivateSeparationLocalProfile,
) -> dict[str, Path]:
    """Return the shared verified-backend arguments for downstream services."""

    return {
        "design_report_path": profile.design_report,
        "coverage_report_path": profile.coverage_report,
        "repository_root": profile.repository_root,
        "runtime_launcher_path": profile.runtime_launcher,
        "source_root": profile.source_root,
        "checkpoint_path": profile.checkpoint,
        "companion_root": profile.companion_root,
    }


# Compatibility aliases for the existing developer script and focused tests.
# The legacy name remains a normal dict because callers historically deep-copy
# it; production responses still receive a new copy at every boundary.
_FALSE_PRODUCT_PERMISSIONS = dict(FALSE_PRODUCT_PERMISSIONS)
_resolve_private_separation_local_profile = resolve_private_separation_local_profile
_check_private_separation_local_profile = check_private_separation_local_profile
_backend_kwargs = private_separation_backend_kwargs


__all__ = [
    "ACTIVATED_STATUS",
    "ASSESSMENT_DIRECTORY",
    "DOCTOR_STATUS",
    "EQUIVALENCE_DIRECTORY",
    "EXECUTION_DIRECTORY",
    "FALSE_PRODUCT_PERMISSIONS",
    "FINISH_DIRECTORY",
    "IMPORTED_STATUS",
    "INCOMPLETE_STATUS",
    "PLAN_DIRECTORY",
    "PREPARED_STATUS",
    "PRESENT_STATUS",
    "PROJECT_DIRECTORY",
    "PrivateSeparationLocalProfile",
    "ProfileChecker",
    "REPORT_NAME",
    "REQUEST_DIRECTORY",
    "REVIEW_DIRECTORY",
    "REVIEW_STATUS",
    "SCHEMA",
    "VALIDATED_STATUS",
    "VALIDATION_DIRECTORY",
    "check_private_separation_local_profile",
    "private_separation_backend_kwargs",
    "resolve_private_separation_local_profile",
]
