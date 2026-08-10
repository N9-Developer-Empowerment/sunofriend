"""Pure contract for private six-role Studio evidence packages."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping

from .separation_fine_stem_integration_outcome import QUALIFIED_STATUS
from .separation_fine_stem_integration_plan import PERSISTED_ROLES
from .workbench_catalog import WORKBENCH_CATALOG_SCHEMA


PACKAGE_SCHEMA = "sunofriend.fine-stem-private-studio-package.v1"
PACKAGE_STATUS = "private_studio_audio_package_ready_no_selection"
PACKAGE_DIRECTORY_NAME = "fine-stem-private-studio-package-v1"
PACKAGE_MANIFEST_NAME = "PRIVATE-STUDIO-PACKAGE.json"
SIX_ROLE_CATALOG_NAME = "SIX-ROLE-STUDIO-CATALOG.json"
MIDI_CONTROL_CATALOG_NAME = "GROUPED-OTHER-MIDI-CONTROL-CATALOG.json"
GUIDE_NAME = "START-HERE.txt"


def studio_package_document_sha256(value: Mapping[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "document_sha256"}
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def six_role_catalog() -> dict[str, Any]:
    labels = {
        "vocals": "Vocals estimate",
        "drums": "Drums estimate",
        "bass": "Bass estimate",
        "synth": "Synth estimate",
        "guitar": "Guitar estimate",
        "other": "Residual other estimate",
    }
    roles = {
        "vocals": "vocals",
        "drums": "drums",
        "bass": "bass",
        "synth": "synth",
        "guitar": "guitar",
        "other": "residual other",
    }
    return {
        "schema": WORKBENCH_CATALOG_SCHEMA,
        "stems": [
            {
                "source": f"STEMS/{role}.wav",
                "label": labels[role],
                "role": roles[role],
                "review_question": (
                    "Audition this reviewed private estimate before any explicit "
                    "MIDI or source decision."
                ),
                "listening_focus": [
                    "musical usefulness",
                    "missing content or bleed",
                    "artefacts and timing",
                ],
                "candidates": [],
            }
            for role in PERSISTED_ROLES
        ],
    }


def midi_control_catalog() -> dict[str, Any]:
    return {
        "schema": WORKBENCH_CATALOG_SCHEMA,
        "stems": [
            {
                "source": "MIDI-CONTROL/grouped-other.wav",
                "label": "Grouped other MIDI control",
                "role": "grouped other",
                "review_question": (
                    "Audition grouped other as the retained MIDI control; do not "
                    "combine it with synth, guitar and residual other."
                ),
                "listening_focus": [
                    "recognisable pitched content",
                    "editability after transcription",
                    "mixed non-synth and non-guitar content",
                ],
                "candidates": [],
            }
        ],
    }


def package_guide(case_ids: list[str]) -> str:
    lines = [
        "Sunofriend private six-role Studio evaluation package",
        "",
        "This package contains eight reviewed 15-second development cases.",
        "It is not a full-song separator, public profile, source selection, or MIDI choice.",
        "",
        "For a six-role audio audition, run from this package directory:",
        '  sunofriend tui "CASES/CASE_ID" --mode studio --catalog "CASES/CASE_ID/SIX-ROLE-STUDIO-CATALOG.json"',
        "",
        "For the separate grouped-other MIDI control:",
        '  sunofriend tui "CASES/CASE_ID" --mode studio --catalog "CASES/CASE_ID/GROUPED-OTHER-MIDI-CONTROL-CATALOG.json"',
        "",
        "Never load both catalogs as one source set: grouped other equals synth + guitar + residual other.",
        "The catalogs contain audio sources only. Any later MIDI conversion needs a fresh output and an explicit user decision.",
        "",
        "Available CASE_ID values:",
        *[f"  - {case_id}" for case_id in case_ids],
        "",
    ]
    return "\n".join(lines)


def cross_validate_evidence(
    *,
    report: Mapping[str, Any],
    review: Mapping[str, Any],
    outcome: Mapping[str, Any],
    midi_report: Mapping[str, Any],
    midi_outcome: Mapping[str, Any],
    provider_midi_outcome: Mapping[str, Any],
) -> None:
    if (
        outcome["status"] != QUALIFIED_STATUS
        or outcome["qualified_for_private_six_role_integration"] is not True
        or outcome["report_sha256"] != report["report_sha256"]
        or outcome["review_document_sha256"] != review["document_sha256"]
    ):
        raise ValueError("private Studio integration qualification binding differs")
    if (
        midi_report.get("integration", {}).get("report_sha256")
        != report["report_sha256"]
    ):
        raise ValueError("private Studio MIDI/report binding differs")
    if (
        midi_outcome["canary_document_sha256"] != midi_report["document_sha256"]
        or midi_outcome["plan_document_sha256"]
        != midi_report["plan"]["document_sha256"]
    ):
        raise ValueError("private Studio MIDI outcome binding differs")

    report_roles = {
        str(case["case_id"]): str(case["reused_primary_role"])
        for case in report["cases"]
    }
    midi_roles = {
        str(case["case_id"]): str(case["confirmed_present_target_role"])
        for case in midi_report["cases"]
    }
    if midi_roles != report_roles:
        raise ValueError("private Studio MIDI case cohort differs")
    outcome_roles = {
        str(target["target_role"]): set(target["case_ids"])
        for target in midi_outcome["targets"]
    }
    for role in ("synth", "guitar"):
        expected = {case_id for case_id, value in report_roles.items() if value == role}
        if outcome_roles.get(role) != expected:
            raise ValueError("private Studio MIDI outcome cohort differs")
    synth_cases = {case_id for case_id, role in report_roles.items() if role == "synth"}
    if {case["case_id"] for case in provider_midi_outcome["cases"]} != synth_cases:
        raise ValueError("private Studio provider synth cohort differs")
    decisions = provider_midi_outcome.get("decisions", {})
    if (
        decisions.get("audio_stem_evidence", {}).get("status")
        != "retain_private_six_role_audio_evidence"
        or decisions.get("midi", {}).get("status")
        != "retain_grouped_other_control_no_automatic_choice"
        or decisions.get("next_step", {}).get("status")
        != "separate_audio_stem_admission_from_midi_method_choice"
    ):
        raise ValueError("private Studio provider MIDI decision differs")


def validate_private_studio_package_document(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    document = copy.deepcopy(dict(value))
    if (
        document.get("schema") != PACKAGE_SCHEMA
        or document.get("status") != PACKAGE_STATUS
        or document.get("document_sha256") != studio_package_document_sha256(document)
    ):
        raise ValueError("private Studio package identity differs")
    cases = document.get("cases")
    if (
        not isinstance(cases, list)
        or len(cases) != 8
        or len({case.get("case_id") for case in cases}) != 8
    ):
        raise ValueError("private Studio package cases differ")
    for case in cases:
        if set(case.get("six_role_stems", {})) != set(PERSISTED_ROLES):
            raise ValueError("private Studio six-role set differs")
        if case.get("studio", {}).get("initial_source_selection") is not None:
            raise ValueError("private Studio package selected a source")
        if case.get("studio", {}).get("initial_midi_selection") is not None:
            raise ValueError("private Studio package selected MIDI")
    policy = document.get("policy", {})
    if (
        policy.get("catalogs_are_mutually_exclusive") is not True
        or policy.get("midi_control") != "grouped_other_retained_no_automatic_choice"
        or policy.get("automatic_winner_selection") is not False
    ):
        raise ValueError("private Studio package policy differs")
    boundaries = document.get("boundaries", {})
    if boundaries.get("private_studio_audio_only") is not True or any(
        boundaries.get(key) is not False
        for key in (
            "public_activation",
            "source_selection",
            "midi_selection",
            "midi_created",
            "separator_model_loaded",
            "transcriber_run",
            "network_access",
            "hosting",
            "redistribution",
            "audio_upload",
        )
    ):
        raise ValueError("private Studio package grants permission")
    effects = document.get("effects", {})
    expected_copy_count = len(cases) * 9
    if (
        effects.get("private_audio_files_read") != expected_copy_count
        or effects.get("private_audio_files_copied") != expected_copy_count
        or effects.get("studio_catalogs_written") != len(cases) * 2
        or effects.get("guide_files_written") != 1
        or any(
            effects.get(key) != 0
            for key in (
                "checkpoint_loads",
                "model_constructions",
                "separator_inference_attempts",
                "midi_transcription_attempts",
                "midi_files_written",
                "network_attempts",
                "source_selections",
                "public_activations",
            )
        )
    ):
        raise ValueError("private Studio package effects differ")
    return document


def package_records(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = [document["guide"]]
    for case in document["cases"]:
        records.extend(case["six_role_stems"].values())
        records.extend(
            (
                case["reference"],
                case["reconstruction_diagnostic"],
                case["grouped_other_midi_control"],
            )
        )
        records.extend(case["catalogs"].values())
    return records


__all__ = [
    "GUIDE_NAME",
    "MIDI_CONTROL_CATALOG_NAME",
    "PACKAGE_DIRECTORY_NAME",
    "PACKAGE_MANIFEST_NAME",
    "PACKAGE_SCHEMA",
    "PACKAGE_STATUS",
    "SIX_ROLE_CATALOG_NAME",
    "cross_validate_evidence",
    "midi_control_catalog",
    "package_guide",
    "package_records",
    "six_role_catalog",
    "studio_package_document_sha256",
    "validate_private_studio_package_document",
]
