"""Role and readiness contracts for finished-mix separation scopes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .separation_profiles import (
    KIM_VOCAL_PROFILE_ID,
    SCNET_RELEASE_PROFILE_ID,
    profile_for_scope,
    separation_profile_registry,
)
from .separation_other_refinement import other_refinement_registry


CAPABILITIES_SCHEMA = "sunofriend.experimental-separation-capabilities.v1"
DEFAULT_SCOPE_ID = "broad-vocals-v1"
FULL_STEM_SCOPE_ID = "core-four-stems-v1"


@dataclass(frozen=True)
class StemRoleSpec:
    role_id: str
    label: str
    relative_path: str
    summary: str
    review_prompt: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.role_id,
            "label": self.label,
            "path": self.relative_path,
            "summary": self.summary,
            "review_prompt": self.review_prompt,
        }


@dataclass(frozen=True)
class SeparationScopeSpec:
    scope_id: str
    label: str
    status: str
    summary: str
    roles: tuple[StemRoleSpec, ...]
    executable: bool
    worker_profile_id: str | None
    model_id: str | None
    model_revision: str | None
    blockers: tuple[str, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.scope_id,
            "label": self.label,
            "status": self.status,
            "summary": self.summary,
            "roles": [role.to_dict() for role in self.roles],
            "executable": self.executable,
            "worker_profile_id": self.worker_profile_id,
            "model_id": self.model_id,
            "model_revision": self.model_revision,
            "blockers": list(self.blockers),
            "limitations": list(self.limitations),
        }


_VOCALS = StemRoleSpec(
    role_id="vocals",
    label="Broad vocals",
    relative_path="STEMS/vocals.wav",
    summary="estimated broad vocal content",
    review_prompt=(
        "Listen for missing vocal phrases, accompaniment bleed, metallic "
        "texture and join changes."
    ),
)
_INSTRUMENTAL = StemRoleSpec(
    role_id="instrumental",
    label="Broad instrumental",
    relative_path="STEMS/instrumental.wav",
    summary="source minus estimated broad vocals",
    review_prompt=(
        "Listen for remaining vocals, holes where vocals were removed, and "
        "whether the backing remains musically useful."
    ),
)
_DRUMS = StemRoleSpec(
    role_id="drums",
    label="Drums",
    relative_path="STEMS/drums.wav",
    summary="estimated composite drum kit and percussion",
    review_prompt=(
        "Listen for missing hits, pitched-instrument bleed, softened attacks "
        "and timing changes."
    ),
)
_BASS = StemRoleSpec(
    role_id="bass",
    label="Bass",
    relative_path="STEMS/bass.wav",
    summary="estimated bass content",
    review_prompt=(
        "Listen for missing fundamentals, kick or low-instrument bleed, and "
        "whether the bass line remains usable."
    ),
)
_OTHER = StemRoleSpec(
    role_id="other",
    label="Other instruments",
    relative_path="STEMS/other.wav",
    summary="remaining instruments as one broad grouped stem",
    review_prompt=(
        "Listen for holes, vocal or rhythm-section bleed, and remember that "
        "this is not a single-instrument track."
    ),
)


_SCOPES = {
    DEFAULT_SCOPE_ID: SeparationScopeSpec(
        scope_id=DEFAULT_SCOPE_ID,
        label="Broad vocals plus instrumental",
        status="public_experimental_alpha",
        summary=(
            "One broad vocal estimate plus its complementary instrumental "
            "from an authorised finished mix."
        ),
        roles=(_VOCALS, _INSTRUMENTAL),
        executable=True,
        worker_profile_id=KIM_VOCAL_PROFILE_ID,
        model_id="mlx-community/mel-roformer-kim-vocal-2-mlx",
        model_revision="64cbfcb004e39430e5f584552c05949440ec39ce",
        blockers=(),
        limitations=(
            "This scope produces broad vocals and broad instrumental only.",
            "The outputs are estimates and require human listening.",
            "Chunk joins can contain audible changes or artefacts.",
            "No stem, model or musical default is selected from feedback automatically.",
        ),
    ),
    FULL_STEM_SCOPE_ID: SeparationScopeSpec(
        scope_id=FULL_STEM_SCOPE_ID,
        label="Core four stems",
        status="public_opt_in_preview",
        summary=(
            "Opt-in local preview separation into vocals, drums, bass and broad "
            "other through the exact installed SCNet release profile."
        ),
        roles=(_VOCALS, _DRUMS, _BASS, _OTHER),
        executable=True,
        worker_profile_id=SCNET_RELEASE_PROFILE_ID,
        model_id="official SCNet-large MUSDB checkpoint",
        model_revision=(
            "google-drive:1s7QvQwn8ag9oVstGDBQ6KZvacJkvyK7t:"
            "sha256:719e5abb8ed920305dad546ac3cd6fb0b1e9c3092d14ce21827bfc0423af3070"
        ),
        blockers=(),
        limitations=(
            "Core four stems still group guitars, keys and other instruments together.",
            "Persisted other includes a disclosed correction so the four PCM24 stems reconstruct the reference.",
            "Reconstruction accounting is not separation accuracy.",
            "The first verified machine class is a 36 GB M3 Max; 16 GiB and other Apple-silicon Macs are accessible but unverified and remain supervised.",
            "Synthetic vocal isolation was weak, so every result still requires listening.",
            "Poor or mixed listening feedback does not disable the last objectively functioning public profile.",
        ),
    ),
}


def separation_scope(scope_id: str) -> SeparationScopeSpec:
    try:
        return _SCOPES[scope_id]
    except KeyError as exc:
        available = ", ".join(sorted(_SCOPES))
        raise ValueError(
            f"unknown separation scope {scope_id!r}; choose one of: {available}"
        ) from exc


def require_executable_scope(scope_id: str) -> SeparationScopeSpec:
    scope = separation_scope(scope_id)
    profile = profile_for_scope(scope_id)
    if not scope.executable or not profile.executable:
        reasons = "; ".join((*scope.blockers, *profile.blockers))
        raise RuntimeError(
            f"separation scope {scope.scope_id!r} is not executable: {reasons}"
        )
    return scope


def separation_capabilities() -> dict[str, Any]:
    scopes = []
    for scope in _SCOPES.values():
        value = scope.to_dict()
        profile = profile_for_scope(scope.scope_id)
        value["implementation_available"] = scope.executable
        value["executable"] = scope.executable and profile.executable
        value["profile_status"] = profile.status
        value["target_release_tier"] = profile.target_release_tier
        scopes.append(value)
    return {
        "schema": CAPABILITIES_SCHEMA,
        "default_scope_id": DEFAULT_SCOPE_ID,
        "scopes": scopes,
        "profile_registry": separation_profile_registry(),
        "refinement_registry": other_refinement_registry(),
        "policy": {
            "unavailable_scopes_fail_closed": True,
            "human_listening_required": True,
            "subjective_feedback_blocks_preview": False,
            "automatic_model_promotion": False,
            "automatic_midi_activation": False,
            "guitar_or_piano_target_in_core_four_stems": False,
            "detailed_other_refinement_is_public": False,
            "detailed_other_refinement_is_studio_only": True,
            "feedback_review_trigger": "30 days or 10 valid reports, whichever occurs first",
            "pre_release_baseline_configurations": 1,
            "maximum_pre_release_remediation_cycles": 1,
        },
    }


__all__ = [
    "CAPABILITIES_SCHEMA",
    "DEFAULT_SCOPE_ID",
    "FULL_STEM_SCOPE_ID",
    "SeparationScopeSpec",
    "StemRoleSpec",
    "require_executable_scope",
    "separation_capabilities",
    "separation_scope",
]
