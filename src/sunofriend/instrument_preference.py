"""Local advisory instrument preferences from explicit DAW listening choices."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


FEEDBACK_SCHEMA = "sunofriend.instrument-patch-feedback.v1"
PROFILE_SCHEMA = "sunofriend.personal-instrument-ranking.v1"
PROFILE_POLICY = "explicit-reviewed-daw-choice-v1"
DECISION_WEIGHTS = {
    "preferred": 1.0,
    "acceptable": 0.5,
    "rejected": -1.0,
}
CONTEXT_WEIGHTS = {
    "full-mix": 1.0,
    "solo": 0.5,
}
PATCH_SOURCES = frozenset(
    {
        "garageband-library",
        "audio-unit",
        "general-midi",
        "source-instrument",
        "other",
    }
)
_POLICY_INVARIANTS = {
    "name": PROFILE_POLICY,
    "training_source": "explicit-reviewed-daw-choices-only",
    "advisory_only": True,
    "automatic_selection": False,
    "match_ranking_changed": False,
    "default_selection_changed": False,
    "playability_gate_bypassed": False,
}
_FEEDBACK_EFFECTS = {
    "source_midi_changed": False,
    "bundle_changed": False,
    "match_ranking_changed": False,
    "automatic_patch_selection": False,
    "playability_gate_bypassed": False,
}
_PROFILE_EFFECTS = {
    "source_midi_changed": False,
    "bundles_changed": False,
    "match_rankings_changed": False,
    "automatic_patch_selection": False,
    "playability_gate_bypassed": False,
}
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


def record_instrument_patch_feedback(
    bundle_path: str | Path,
    *,
    patch_name: str,
    out_path: str | Path,
    patch_source: str = "garageband-library",
    decision: str = "preferred",
    listening_context: str = "full-mix",
    compared_with: Sequence[str] = (),
    notes: str | None = None,
) -> dict[str, Any]:
    """Record one explicit, reviewed patch decision against an immutable bundle."""

    output = _fresh_json_path(out_path, label="instrument feedback")
    patch = _nonempty(patch_name, label="patch name")
    source = str(patch_source).strip().lower()
    if source not in PATCH_SOURCES:
        raise ValueError(
            "patch source must be one of: " + ", ".join(sorted(PATCH_SOURCES))
        )
    normalized_decision = str(decision).strip().lower()
    if normalized_decision not in DECISION_WEIGHTS:
        raise ValueError(
            "decision must be one of: " + ", ".join(DECISION_WEIGHTS)
        )
    context = str(listening_context).strip().lower()
    if context not in CONTEXT_WEIGHTS:
        raise ValueError(
            "listening context must be one of: " + ", ".join(CONTEXT_WEIGHTS)
        )
    comparisons = _unique_nonempty(compared_with)
    note_text = str(notes).strip() if notes is not None else None
    if note_text == "":
        note_text = None

    bundle_dir, report_path = _bundle_report_path(bundle_path)
    report = _read_json(report_path, label="Instrument Bundle report")
    if (
        report.get("operation") != "instrument-bundle"
        or report.get("format") != "sunofriend-instrument-bundle-v1"
        or report.get("status") not in {"complete", "partial"}
    ):
        raise ValueError("unsupported or incomplete Instrument Bundle report")
    recipe_path = bundle_dir / "instrument_recipe.json"
    performance_path = bundle_dir / "performance.mid"
    recipe = _read_json(recipe_path, label="Instrument Bundle recipe")
    if recipe.get("format") != "sunofriend-instrument-bundle-v1":
        raise ValueError("unsupported Instrument Bundle recipe")
    if not performance_path.is_file():
        raise ValueError(f"Instrument Bundle performance MIDI not found: {performance_path}")
    kind = _nonempty(report.get("kind"), label="bundle kind").lower()
    if str(recipe.get("kind", "")).strip().lower() != kind:
        raise ValueError("Instrument Bundle report and recipe roles do not match")

    feedback = {
        "schema": FEEDBACK_SCHEMA,
        "status": "reviewed",
        "policy": dict(_POLICY_INVARIANTS),
        "bundle": {
            "directory": str(bundle_dir),
            "report": _file_record(report_path),
            "recipe": _file_record(recipe_path),
            "performance_midi": _file_record(performance_path),
            "stem": report.get("stem"),
            "midi": report.get("midi"),
            "kind": kind,
            "bundle_status": report.get("status"),
            "source_instrument_status": report.get("source_instrument_status"),
        },
        "choice": {
            "patch_name": patch,
            "normalized_patch_name": _normalize_patch_name(patch),
            "patch_source": source,
            "decision": normalized_decision,
            "listening_context": context,
            "compared_with": comparisons,
            "notes": note_text,
            "explicit": True,
            "reviewed": True,
        },
        "effects": dict(_FEEDBACK_EFFECTS),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, feedback)
    return {
        "status": "reviewed",
        "feedback": str(output),
        "feedback_sha256": _sha256(output),
        "kind": kind,
        "patch_name": patch,
        "patch_source": source,
        "decision": normalized_decision,
        "listening_context": context,
        "advisory_only": True,
        "automatic_selection": False,
        "source_midi_changed": False,
        "bundle_changed": False,
    }


def build_personal_instrument_profile(
    feedback_paths: Sequence[str | Path],
    *,
    out_path: str | Path,
) -> dict[str, Any]:
    """Build one fresh deterministic profile from explicit feedback files."""

    if not feedback_paths:
        raise ValueError("instrument-profile requires at least one feedback file")
    output = _fresh_json_path(out_path, label="instrument profile")
    loaded: list[tuple[dict[str, Any], dict[str, Any]]] = []
    hashes: set[str] = set()
    for value in feedback_paths:
        path = Path(value).expanduser().absolute()
        document = _read_json(path, label="instrument feedback")
        _validate_feedback(document)
        record = _file_record(path)
        if record["sha256"] in hashes:
            raise ValueError("instrument-profile inputs must be unique by hash")
        hashes.add(record["sha256"])
        loaded.append((document, record))
    loaded.sort(key=lambda item: (item[1]["sha256"], item[1]["path"]))

    inputs: list[dict[str, Any]] = []
    for document, record in loaded:
        choice = document["choice"]
        bundle = document["bundle"]
        kind = str(bundle["kind"])
        patch_source = str(choice["patch_source"])
        decision = str(choice["decision"])
        context = str(choice["listening_context"])
        inputs.append(
            {
                **record,
                "kind": kind,
                "patch_name": choice["patch_name"],
                "patch_source": patch_source,
                "decision": decision,
                "listening_context": context,
                "bundle_performance_midi_sha256": bundle["performance_midi"][
                    "sha256"
                ],
            }
        )

    role_rankings = _role_rankings_from_inputs(inputs)

    profile = {
        "schema": PROFILE_SCHEMA,
        "status": "complete",
        "policy": {
            **_POLICY_INVARIANTS,
            "decision_weights": DECISION_WEIGHTS,
            "listening_context_weights": CONTEXT_WEIGHTS,
        },
        "inputs": inputs,
        "input_count": len(inputs),
        "role_count": len(role_rankings),
        "role_rankings": dict(sorted(role_rankings.items())),
        "decision_counts": dict(
            sorted(Counter(item["decision"] for item in inputs).items())
        ),
        "effects": dict(_PROFILE_EFFECTS),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, profile)
    return {
        "status": "complete",
        "profile": str(output),
        "profile_sha256": _sha256(output),
        "input_count": len(inputs),
        "role_count": len(role_rankings),
        "role_rankings": profile["role_rankings"],
        "advisory_only": True,
        "automatic_selection": False,
        "bundles_changed": False,
    }


def load_personal_instrument_profile(
    profile_path: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load and validate a local immutable instrument-ranking profile."""

    path = Path(profile_path).expanduser().absolute()
    profile = _read_json(path, label="instrument profile")
    if profile.get("schema") != PROFILE_SCHEMA or profile.get("status") != "complete":
        raise ValueError("unsupported or incomplete instrument profile")
    policy = profile.get("policy")
    expected_policy = {
        **_POLICY_INVARIANTS,
        "decision_weights": DECISION_WEIGHTS,
        "listening_context_weights": CONTEXT_WEIGHTS,
    }
    if not isinstance(policy, Mapping) or any(
        policy.get(key) != value for key, value in _POLICY_INVARIANTS.items()
    ):
        raise ValueError("instrument profile policy is invalid")
    if policy != expected_policy:
        raise ValueError("instrument profile weights are invalid")
    inputs = profile.get("inputs")
    rankings = profile.get("role_rankings")
    if (
        not isinstance(inputs, list)
        or profile.get("input_count") != len(inputs)
        or not isinstance(rankings, Mapping)
        or profile.get("role_count") != len(rankings)
    ):
        raise ValueError("instrument profile summary is invalid")
    for item in inputs:
        if not isinstance(item, Mapping):
            raise ValueError("instrument profile input is invalid")
        _validate_file_record(item, label="instrument profile input")
        if (
            not _valid_sha256(item.get("bundle_performance_midi_sha256"))
            or item.get("patch_source") not in PATCH_SOURCES
            or item.get("decision") not in DECISION_WEIGHTS
            or item.get("listening_context") not in CONTEXT_WEIGHTS
        ):
            raise ValueError("instrument profile input is invalid")
        _nonempty(item.get("kind"), label="profile input kind")
        _nonempty(item.get("patch_name"), label="profile input patch")
    for kind, rows in rankings.items():
        if not isinstance(kind, str) or not kind or not isinstance(rows, list):
            raise ValueError("instrument profile role ranking is invalid")
        for expected_rank, row in enumerate(rows, 1):
            if not isinstance(row, Mapping) or row.get("rank") != expected_rank:
                raise ValueError("instrument profile role ranking is invalid")
            if row.get("kind") != kind or row.get("patch_source") not in PATCH_SOURCES:
                raise ValueError("instrument profile role ranking is invalid")
            score = row.get("weighted_score")
            if (
                not isinstance(score, (int, float))
                or isinstance(score, bool)
                or not math.isfinite(float(score))
            ):
                raise ValueError("instrument profile role ranking score is invalid")
            if row.get("normalized_patch_name") != _normalize_patch_name(
                row.get("patch_name")
            ):
                raise ValueError("instrument profile patch identity is invalid")
    expected_rankings = _role_rankings_from_inputs(inputs)
    if rankings != expected_rankings:
        raise ValueError("instrument profile role rankings do not match inputs")
    expected_decisions = dict(
        sorted(Counter(str(item["decision"]) for item in inputs).items())
    )
    if profile.get("decision_counts") != expected_decisions:
        raise ValueError("instrument profile decision counts do not match inputs")
    if profile.get("effects") != _PROFILE_EFFECTS:
        raise ValueError("instrument profile effects are invalid")
    return profile, _file_record(path)


def rank_instrument_preferences(
    profile: Mapping[str, Any], kind: str
) -> dict[str, Any]:
    """Return advisory history for one role without selecting or reordering."""

    normalized_kind = _nonempty(kind, label="instrument kind").lower()
    rows = [dict(row) for row in profile["role_rankings"].get(normalized_kind, [])]
    positive = [row for row in rows if float(row["weighted_score"]) > 0.0]
    return {
        "kind": normalized_kind,
        "history_first": positive[0]["patch_name"] if positive else None,
        "history_first_source": positive[0]["patch_source"] if positive else None,
        "ranking": rows,
        "observation_count": sum(
            int(row["preferred_count"])
            + int(row["acceptable_count"])
            + int(row["rejected_count"])
            for row in rows
        ),
        "score_meaning": (
            "Relative local history from explicit DAW choices; not confidence, "
            "instrument identity or automatic selection."
        ),
        "advisory_only": True,
        "automatic_selection": False,
        "match_ranking_changed": False,
        "default_selection_changed": False,
        "playability_gate_bypassed": False,
    }


def _validate_feedback(document: Mapping[str, Any]) -> None:
    if document.get("schema") != FEEDBACK_SCHEMA or document.get("status") != "reviewed":
        raise ValueError("instrument feedback is not explicitly reviewed")
    policy = document.get("policy")
    if not isinstance(policy, Mapping) or policy != _POLICY_INVARIANTS:
        raise ValueError("instrument feedback policy is invalid")
    choice = document.get("choice")
    bundle = document.get("bundle")
    if not isinstance(choice, Mapping) or not isinstance(bundle, Mapping):
        raise ValueError("instrument feedback is invalid")
    patch = _nonempty(choice.get("patch_name"), label="feedback patch name")
    if choice.get("normalized_patch_name") != _normalize_patch_name(patch):
        raise ValueError("instrument feedback patch identity is invalid")
    if (
        choice.get("patch_source") not in PATCH_SOURCES
        or choice.get("decision") not in DECISION_WEIGHTS
        or choice.get("listening_context") not in CONTEXT_WEIGHTS
        or choice.get("explicit") is not True
        or choice.get("reviewed") is not True
    ):
        raise ValueError("instrument feedback choice is invalid")
    comparisons = choice.get("compared_with")
    if not isinstance(comparisons, list) or comparisons != _unique_nonempty(comparisons):
        raise ValueError("instrument feedback comparisons are invalid")
    if choice.get("notes") is not None and not isinstance(choice.get("notes"), str):
        raise ValueError("instrument feedback notes are invalid")
    _nonempty(bundle.get("kind"), label="feedback bundle kind")
    for key in ("report", "recipe", "performance_midi"):
        _validate_file_record(
            bundle.get(key), label=f"instrument feedback bundle {key}"
        )
    if document.get("effects") != _FEEDBACK_EFFECTS:
        raise ValueError("instrument feedback effects are invalid")


def _validate_file_record(value: Any, *, label: str) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} is invalid")
    if not str(value.get("path", "")).strip() or not _valid_sha256(
        value.get("sha256")
    ):
        raise ValueError(f"{label} is invalid")
    byte_size = value.get("byte_size")
    if not isinstance(byte_size, int) or isinstance(byte_size, bool) or byte_size < 0:
        raise ValueError(f"{label} is invalid")


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_PATTERN.fullmatch(value) is not None


def _role_rankings_from_inputs(
    inputs: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    aggregates: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in inputs:
        kind = str(item["kind"])
        patch_name = str(item["patch_name"])
        patch_source = str(item["patch_source"])
        normalized_name = _normalize_patch_name(patch_name)
        key = (kind, patch_source, normalized_name)
        row = aggregates.setdefault(
            key,
            {
                "kind": kind,
                "patch_name": patch_name,
                "normalized_patch_name": normalized_name,
                "patch_source": patch_source,
                "preferred_count": 0,
                "acceptable_count": 0,
                "rejected_count": 0,
                "full_mix_count": 0,
                "solo_count": 0,
                "weighted_score": 0.0,
                "feedback_sha256": [],
            },
        )
        decision = str(item["decision"])
        context = str(item["listening_context"])
        row[f"{decision}_count"] += 1
        row[f"{context.replace('-', '_')}_count"] += 1
        row["weighted_score"] += (
            DECISION_WEIGHTS[decision] * CONTEXT_WEIGHTS[context]
        )
        row["feedback_sha256"].append(str(item["sha256"]))

    role_rankings: dict[str, list[dict[str, Any]]] = {}
    for row in aggregates.values():
        row["weighted_score"] = round(float(row["weighted_score"]), 6)
        row["feedback_sha256"] = sorted(row["feedback_sha256"])
        role_rankings.setdefault(str(row["kind"]), []).append(row)
    for kind, rows in role_rankings.items():
        rows.sort(
            key=lambda row: (
                -float(row["weighted_score"]),
                -int(row["preferred_count"]),
                str(row["normalized_patch_name"]),
                str(row["patch_source"]),
            )
        )
        for rank, row in enumerate(rows, 1):
            row["rank"] = rank
        role_rankings[kind] = rows
    return dict(sorted(role_rankings.items()))


def _bundle_report_path(value: str | Path) -> tuple[Path, Path]:
    path = Path(value).expanduser().absolute()
    if path.is_dir():
        return path, path / "instrument_bundle.json"
    if path.name == "instrument_bundle.json":
        return path.parent, path
    raise ValueError(
        "instrument feedback input must be a bundle directory or instrument_bundle.json"
    )


def _fresh_json_path(value: str | Path, *, label: str) -> Path:
    output = Path(value).expanduser().absolute()
    if output.exists():
        raise ValueError(f"{label} output already exists: {output}")
    if output.suffix.lower() != ".json":
        raise ValueError(f"{label} output must end in .json")
    return output


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label} not found: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def _file_record(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path.absolute()),
        "sha256": _sha256(path),
        "byte_size": stat.st_size,
    }


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_patch_name(value: Any) -> str:
    return " ".join(_nonempty(value, label="patch name").casefold().split())


def _nonempty(value: Any, *, label: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"{label} is required")
    return text


def _unique_nonempty(values: Sequence[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        text = _nonempty(value, label="compared patch")
        key = _normalize_patch_name(text)
        if key not in seen:
            result.append(text)
            seen.add(key)
    return result


__all__ = [
    "FEEDBACK_SCHEMA",
    "PROFILE_POLICY",
    "PROFILE_SCHEMA",
    "build_personal_instrument_profile",
    "load_personal_instrument_profile",
    "rank_instrument_preferences",
    "record_instrument_patch_feedback",
]
