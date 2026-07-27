"""Versioned product goal shared by Sunofriend's human interfaces.

The transcription and rendering pipelines already have stricter, independent
contracts.  This module does not reinterpret their receipts.  It describes how
those accepted artifacts combine into the product users are trying to make.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .listening_master import LISTENING_MASTER_POLICY, LISTENING_MASTER_SCHEMA
from .workbench_balanced_contract import BALANCED_MIX_CONTRACT


PRODUCT_CONTRACT_SCHEMA = "sunofriend.product-contract.v1"
PRODUCT_CONTRACT_VERSION = "2026-07-27.1"
PRODUCT_OUTPUT_STATUS_SCHEMA = "sunofriend.product-output-status.v1"
PRODUCT_SUMMARY = (
    "Create reviewed, editable MIDI plus a balanced MIDI-derived "
    "song-interpretation WAV from separated music stems."
)


@dataclass(frozen=True)
class ProductOutput:
    """One immutable output definition in the paired product goal."""

    output_id: str
    label: str
    media_type: str
    editable: bool
    required: bool
    artifact_schema: str | None
    policy: str | None
    source_audio_mixed: bool

    def document(self) -> dict[str, Any]:
        """Return a fresh JSON-safe representation."""

        return {
            "output_id": self.output_id,
            "label": self.label,
            "media_type": self.media_type,
            "editable": self.editable,
            "required": self.required,
            "artifact_schema": self.artifact_schema,
            "policy": self.policy,
            "source_audio_mixed": self.source_audio_mixed,
        }


@dataclass(frozen=True)
class ProductContract:
    """Stable, reviewable definition of Sunofriend's paired result."""

    schema: str
    version: str
    goal: str
    required_outputs: tuple[ProductOutput, ...]
    optional_outputs: tuple[ProductOutput, ...]

    def document(self) -> dict[str, Any]:
        """Return a fresh, path-free product contract document."""

        return {
            "schema": self.schema,
            "version": self.version,
            "goal": self.goal,
            "terminology": {
                "interpolation": (
                    "a creative MIDI interpretation of the source melody, "
                    "harmony, rhythm and structure; not waveform reconstruction "
                    "or recreation of the source production effects"
                ),
                "song_interpretation_wav": (
                    "audio rendered only from the explicitly selected MIDI"
                ),
            },
            "required_outputs": [
                output.document() for output in self.required_outputs
            ],
            "optional_outputs": [
                output.document() for output in self.optional_outputs
            ],
            "source_evidence": {
                "used_for": ["timing", "render horizon", "level evidence"],
                "mixed_into_song_interpretation_wav": False,
            },
            "decision_boundary": {
                "playback_implies_preference": False,
                "metrics_imply_preference": False,
                "visible_defaults_imply_preference": False,
                "rendering_changes_selected_midi": False,
                "automatic_promotion_enabled": False,
            },
            "garageband_pack": {
                "song_interpretation_wav_included_automatically": False,
                "reason": (
                    "GarageBand Pack v1 remains an exact selected-MIDI handoff"
                ),
            },
        }


PRODUCT_CONTRACT = ProductContract(
    schema=PRODUCT_CONTRACT_SCHEMA,
    version=PRODUCT_CONTRACT_VERSION,
    goal="reviewed-midi-plus-midi-derived-song-interpretation-wav",
    required_outputs=(
        ProductOutput(
            output_id="evaluated_editable_midi",
            label="Reviewed editable MIDI",
            media_type="audio/midi",
            editable=True,
            required=True,
            artifact_schema=None,
            policy="explicit-human-selection-from-immutable-candidates",
            source_audio_mixed=False,
        ),
        ProductOutput(
            output_id="midi_derived_song_interpretation_wav",
            label="MIDI-derived song-interpretation WAV",
            media_type="audio/wav",
            editable=False,
            required=True,
            artifact_schema=BALANCED_MIX_CONTRACT.arrangement_schema,
            policy=BALANCED_MIX_CONTRACT.policy,
            source_audio_mixed=False,
        ),
    ),
    optional_outputs=(
        ProductOutput(
            output_id="comparative_listening_master",
            label="Comparative listening master",
            media_type="audio/wav",
            editable=False,
            required=False,
            artifact_schema=LISTENING_MASTER_SCHEMA,
            policy=LISTENING_MASTER_POLICY,
            source_audio_mixed=False,
        ),
    ),
)


def product_contract_document() -> dict[str, Any]:
    """Return the canonical product contract as a fresh document."""

    return PRODUCT_CONTRACT.document()


def build_product_output_status(
    selection_manifest: Mapping[str, Any] | None,
    song_interpretation: Mapping[str, Any] | None,
    *,
    full_mix_review_complete: bool,
) -> dict[str, Any]:
    """Project readiness for the two required outputs without changing state."""

    selection = (
        selection_manifest if isinstance(selection_manifest, Mapping) else {}
    )
    entries = selection.get("selected_midi", [])
    if not isinstance(entries, list):
        entries = []
    selection_sha256 = selection.get("selection_manifest_sha256")
    midi_ready = bool(entries and isinstance(selection_sha256, str))

    artifact = (
        song_interpretation if isinstance(song_interpretation, Mapping) else {}
    )
    interpretation_ready = bool(
        midi_ready
        and artifact.get("schema") == BALANCED_MIX_CONTRACT.arrangement_schema
        and artifact.get("policy") == BALANCED_MIX_CONTRACT.policy
        and artifact.get("selection_manifest_sha256") == selection_sha256
        and artifact.get("mastered") is False
    )

    return {
        "schema": PRODUCT_OUTPUT_STATUS_SCHEMA,
        "contract_version": PRODUCT_CONTRACT_VERSION,
        "complete": (
            midi_ready
            and bool(full_mix_review_complete)
            and interpretation_ready
        ),
        "required_outputs": {
            "evaluated_editable_midi": {
                "ready": midi_ready,
                "selected_part_count": len(entries),
                "selection_manifest_sha256": (
                    selection_sha256 if midi_ready else None
                ),
                "editable": True,
                "full_mix_review_complete": bool(
                    midi_ready and full_mix_review_complete
                ),
            },
            "midi_derived_song_interpretation_wav": {
                "ready": interpretation_ready,
                "selection_manifest_sha256": (
                    selection_sha256 if interpretation_ready else None
                ),
                "artifact_schema": BALANCED_MIX_CONTRACT.arrangement_schema,
                "policy": BALANCED_MIX_CONTRACT.policy,
                "mastered": False,
                "release_master": False,
                "source_audio_mixed": False,
            },
        },
        "optional_outputs": {
            "comparative_listening_master": {
                "available_through_cli": True,
                "ready": False,
                "artifact_schema": LISTENING_MASTER_SCHEMA,
                "policy": LISTENING_MASTER_POLICY,
                "release_master": False,
            }
        },
        "effects": {
            "feedback_recorded": False,
            "musical_selection_changed": False,
            "midi_mutated": False,
            "audio_rendered": False,
        },
    }


__all__ = [
    "PRODUCT_CONTRACT",
    "PRODUCT_CONTRACT_SCHEMA",
    "PRODUCT_CONTRACT_VERSION",
    "PRODUCT_OUTPUT_STATUS_SCHEMA",
    "PRODUCT_SUMMARY",
    "ProductContract",
    "ProductOutput",
    "build_product_output_status",
    "product_contract_document",
]
