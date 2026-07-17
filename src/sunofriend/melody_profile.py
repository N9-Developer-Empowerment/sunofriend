"""Local advisory ranking learned only from explicit melody-review choices."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence


PROFILE_SCHEMA = "sunofriend.personal-melody-ranking.v1"
PROFILE_POLICY = "explicit-reviewed-choice-nearest-context-v1"
CORRECTION_FORMAT = "sunofriend-melody-corrections-v1"
PHRASE_REVIEW_FORMAT = "sunofriend.melody-phrase-review.v1"
ALTERNATIVE_NAMES = (
    "basic-pitch",
    "game-boundary",
    "combined",
    "guide-assisted",
)
CONTEXT_FEATURES = (
    "duration_bars",
    "mean_agreement_ratio",
    "mean_selection_score",
    "combined_note_density_per_bar",
)


def build_personal_melody_profile(
    corrections: Sequence[str | Path],
    *,
    out_path: str | Path,
) -> dict[str, Any]:
    """Build one fresh deterministic profile from reviewed correction files."""

    if not corrections:
        raise ValueError("melody-profile requires at least one reviewed correction")
    output = Path(out_path).expanduser().absolute()
    if output.exists():
        raise ValueError(f"melody profile output already exists: {output}")
    if output.suffix.lower() != ".json":
        raise ValueError("melody profile output must end in .json")

    loaded: list[tuple[dict[str, Any], dict[str, Any]]] = []
    hashes: set[str] = set()
    for value in corrections:
        path = Path(value).expanduser().absolute()
        document = _read_json(path, label="reviewed correction")
        record = _file_record(path)
        if record["sha256"] in hashes:
            raise ValueError("melody-profile correction inputs must be unique by hash")
        hashes.add(record["sha256"])
        loaded.append((document, record))
    loaded.sort(key=lambda item: (item[1]["sha256"], item[1]["path"]))

    inputs: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    counts = {
        name: {"choices": 0, "weighted_choices": 0.0}
        for name in ALTERNATIVE_NAMES
    }
    warnings: list[str] = []
    explicit_choice_count = 0
    for document, record in loaded:
        choices, review = _reviewed_choices(document)
        contextual = 0
        for choice in choices:
            selected = str(choice["selected"])
            propagated = "propagated_from_phrase_index" in choice
            weight = 0.5 if propagated else 1.0
            counts[selected]["choices"] += 1
            counts[selected]["weighted_choices"] += weight
            explicit_choice_count += 1
            context = choice.get("ranking_context")
            if not isinstance(context, Mapping):
                continue
            features = validate_ranking_context(context)
            available = context.get("alternative_names")
            if not isinstance(available, list) or selected not in available:
                raise ValueError(
                    "reviewed choice is not available in its ranking context"
                )
            observations.append(
                {
                    "correction_sha256": record["sha256"],
                    "phrase_index": int(choice["phrase_index"]),
                    "selected": selected,
                    "origin": "propagated" if propagated else "manual",
                    "weight": weight,
                    "features": features,
                }
            )
            contextual += 1
        if contextual < len(choices):
            warnings.append(
                f"{Path(record['path']).name}: {len(choices) - contextual} "
                "choice(s) predate contextual ranking evidence; global counts retained."
            )
        inputs.append(
            {
                **record,
                "source_stem_sha256": document.get("source_stem_sha256"),
                "tracker_run_sha256": review.get("tracker_run_sha256"),
                "explicit_choice_count": len(choices),
                "contextual_choice_count": contextual,
            }
        )
    if explicit_choice_count == 0:
        raise ValueError("melody-profile contains no explicit reviewed choices")
    for value in counts.values():
        value["weighted_choices"] = round(float(value["weighted_choices"]), 6)
    observations.sort(
        key=lambda value: (
            value["correction_sha256"],
            value["phrase_index"],
            value["selected"],
        )
    )
    profile = {
        "schema": PROFILE_SCHEMA,
        "status": "complete",
        "policy": {
            "name": PROFILE_POLICY,
            "training_source": "explicit-reviewed-choices-only",
            "manual_choice_weight": 1.0,
            "propagated_choice_weight": 0.5,
            "context_features": list(CONTEXT_FEATURES),
            "advisory_only": True,
            "automatic_selection": False,
            "candidate_order_changed": False,
            "default_selection_changed": False,
        },
        "inputs": inputs,
        "input_count": len(inputs),
        "explicit_choice_count": explicit_choice_count,
        "contextual_observation_count": len(observations),
        "alternative_counts": counts,
        "observations": observations,
        "warnings": warnings,
        "raw_candidates_mutated": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, profile)
    return {
        "status": "complete",
        "profile": str(output),
        "profile_sha256": _sha256(output),
        "input_count": len(inputs),
        "explicit_choice_count": explicit_choice_count,
        "contextual_observation_count": len(observations),
        "alternative_counts": counts,
        "warnings": warnings,
        "advisory_only": True,
        "automatic_selection": False,
        "raw_candidates_mutated": False,
    }


def load_personal_melody_profile(
    profile_path: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load and validate a local immutable personal-ranking profile."""

    path = Path(profile_path).expanduser().absolute()
    profile = _read_json(path, label="melody profile")
    if profile.get("schema") != PROFILE_SCHEMA or profile.get("status") != "complete":
        raise ValueError("unsupported or incomplete melody profile")
    policy = profile.get("policy")
    if (
        not isinstance(policy, Mapping)
        or policy.get("name") != PROFILE_POLICY
        or policy.get("training_source") != "explicit-reviewed-choices-only"
        or policy.get("advisory_only") is not True
        or policy.get("automatic_selection") is not False
        or policy.get("candidate_order_changed") is not False
        or policy.get("default_selection_changed") is not False
    ):
        raise ValueError("melody profile policy is invalid")
    observations = profile.get("observations")
    if not isinstance(observations, list):
        raise ValueError("melody profile observations are invalid")
    for observation in observations:
        if not isinstance(observation, Mapping):
            raise ValueError("melody profile observation is invalid")
        selected = observation.get("selected")
        weight = observation.get("weight")
        if selected not in ALTERNATIVE_NAMES or not isinstance(weight, (int, float)):
            raise ValueError("melody profile observation is invalid")
        if not math.isfinite(float(weight)) or not 0 < float(weight) <= 1:
            raise ValueError("melody profile observation weight is invalid")
        validate_ranking_context(observation.get("features"))
    inputs = profile.get("inputs")
    input_count = profile.get("input_count")
    explicit_count = profile.get("explicit_choice_count")
    contextual_count = profile.get("contextual_observation_count")
    if (
        not isinstance(inputs, list)
        or not isinstance(input_count, int)
        or isinstance(input_count, bool)
        or input_count != len(inputs)
        or not isinstance(explicit_count, int)
        or isinstance(explicit_count, bool)
        or explicit_count <= 0
        or not isinstance(contextual_count, int)
        or isinstance(contextual_count, bool)
        or contextual_count != len(observations)
        or profile.get("raw_candidates_mutated") is not False
    ):
        raise ValueError("melody profile summary is invalid")
    counts = profile.get("alternative_counts")
    if not isinstance(counts, Mapping):
        raise ValueError("melody profile alternative counts are invalid")
    for name in ALTERNATIVE_NAMES:
        value = counts.get(name)
        if not isinstance(value, Mapping):
            raise ValueError("melody profile alternative counts are invalid")
        choices = value.get("choices")
        weighted = value.get("weighted_choices")
        if (
            not isinstance(choices, int)
            or isinstance(choices, bool)
            or choices < 0
            or not isinstance(weighted, (int, float))
            or not math.isfinite(float(weighted))
            or float(weighted) < 0
        ):
            raise ValueError("melody profile alternative counts are invalid")
    if sum(int(counts[name]["choices"]) for name in ALTERNATIVE_NAMES) != (
        explicit_count
    ):
        raise ValueError("melody profile alternative counts do not match summary")
    return profile, _file_record(path)


def rank_melody_alternatives(
    profile: Mapping[str, Any],
    context: Mapping[str, Any],
    alternative_names: Sequence[str],
) -> dict[str, Any]:
    """Rank available candidates as an advisory hint without selecting one."""

    features = validate_ranking_context(context)
    available = [str(name) for name in alternative_names]
    if (
        not available
        or len(available) != len(set(available))
        or any(name not in ALTERNATIVE_NAMES for name in available)
    ):
        raise ValueError("personal ranking alternatives are invalid")
    counts = profile["alternative_counts"]
    smoothing = 0.5
    global_total = sum(float(counts[name]["weighted_choices"]) for name in available)
    global_scores = {
        name: (float(counts[name]["weighted_choices"]) + smoothing)
        / (global_total + smoothing * len(available))
        for name in available
    }
    observations = [
        value
        for value in profile.get("observations", [])
        if value.get("selected") in available
    ]
    contextual_support = {name: 0.0 for name in available}
    contextual_counts = {name: 0 for name in available}
    nearest = {name: 0.0 for name in available}
    for observation in observations:
        selected = str(observation["selected"])
        similarity = _context_similarity(features, observation["features"])
        contribution = float(observation["weight"]) * similarity
        contextual_support[selected] += contribution
        contextual_counts[selected] += 1
        nearest[selected] = max(nearest[selected], similarity)
    if observations:
        contextual_total = sum(contextual_support.values())
        contextual_scores = {
            name: (contextual_support[name] + 0.1)
            / (contextual_total + 0.1 * len(available))
            for name in available
        }
        combined = {
            name: 0.35 * global_scores[name] + 0.65 * contextual_scores[name]
            for name in available
        }
    else:
        combined = global_scores
    order = {name: index for index, name in enumerate(available)}
    ranking = sorted(
        available,
        key=lambda name: (
            -combined[name],
            -float(counts[name]["weighted_choices"]),
            order[name],
        ),
    )
    rows = [
        {
            "rank": index + 1,
            "name": name,
            "score": round(combined[name], 6),
            "global_choices": int(counts[name]["choices"]),
            "global_weighted_choices": round(
                float(counts[name]["weighted_choices"]), 6
            ),
            "contextual_observations": contextual_counts[name],
            "weighted_context_support": round(contextual_support[name], 6),
            "nearest_context_similarity": round(nearest[name], 6),
        }
        for index, name in enumerate(ranking)
    ]
    return {
        "status": "advisory",
        "policy": PROFILE_POLICY,
        "history_first": ranking[0],
        "ranking": rows,
        "score_meaning": "relative personal-history ranking; not confidence",
        "automatic_selection": False,
        "candidate_order_changed": False,
        "default_selection_changed": False,
    }


def validate_ranking_context(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise ValueError("melody ranking context is missing or invalid")
    features: dict[str, float] = {}
    limits = {
        "duration_bars": (0.0, 32.0),
        "mean_agreement_ratio": (0.0, 1.0),
        "mean_selection_score": (0.0, 1.0),
        "combined_note_density_per_bar": (0.0, 128.0),
    }
    for name, (minimum, maximum) in limits.items():
        try:
            number = float(value[name])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("melody ranking context is missing or invalid") from exc
        if not math.isfinite(number) or not minimum <= number <= maximum:
            raise ValueError("melody ranking context contains invalid values")
        if name == "duration_bars" and number <= 0:
            raise ValueError("melody ranking context contains invalid values")
        features[name] = round(number, 6)
    return features


def _reviewed_choices(
    document: Mapping[str, Any],
) -> tuple[list[Mapping[str, Any]], Mapping[str, Any]]:
    if document.get("format") != CORRECTION_FORMAT:
        raise ValueError("melody-profile input is not a Sunofriend correction")
    review = document.get("review")
    if (
        not isinstance(review, Mapping)
        or review.get("format") != PHRASE_REVIEW_FORMAT
        or review.get("status") != "reviewed"
    ):
        raise ValueError("melody-profile requires an explicitly reviewed correction")
    choices = review.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("reviewed correction contains no explicit choices")
    result: list[Mapping[str, Any]] = []
    indices: set[int] = set()
    for choice in choices:
        if not isinstance(choice, Mapping) or choice.get("reviewed") is not True:
            raise ValueError("reviewed correction contains an incomplete choice")
        selected = choice.get("selected")
        phrase_index = choice.get("phrase_index")
        if (
            selected not in ALTERNATIVE_NAMES
            or not isinstance(phrase_index, int)
            or isinstance(phrase_index, bool)
            or phrase_index < 0
            or phrase_index in indices
        ):
            raise ValueError("reviewed correction contains an invalid choice")
        indices.add(phrase_index)
        if "propagated_from_phrase_index" in choice:
            source_index = choice["propagated_from_phrase_index"]
            if (
                not isinstance(source_index, int)
                or isinstance(source_index, bool)
                or source_index < 0
                or source_index == phrase_index
            ):
                raise ValueError(
                    "reviewed correction contains an invalid propagated choice"
                )
        result.append(choice)
    by_index = {int(choice["phrase_index"]): choice for choice in result}
    for choice in result:
        if "propagated_from_phrase_index" not in choice:
            continue
        source = by_index.get(int(choice["propagated_from_phrase_index"]))
        if source is None or source.get("selected") != choice.get("selected"):
            raise ValueError(
                "reviewed correction propagated choice does not match its source"
            )
    return result, review


def _context_similarity(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> float:
    left_features = validate_ranking_context(left)
    right_features = validate_ranking_context(right)
    distance = (
        0.15
        * abs(left_features["duration_bars"] - right_features["duration_bars"])
        / 8.0
        + 0.30
        * abs(
            left_features["mean_agreement_ratio"]
            - right_features["mean_agreement_ratio"]
        )
        + 0.25
        * abs(
            left_features["mean_selection_score"]
            - right_features["mean_selection_score"]
        )
        + 0.30
        * abs(
            left_features["combined_note_density_per_bar"]
            - right_features["combined_note_density_per_bar"]
        )
        / 12.0
    )
    return max(0.0, min(1.0, 1.0 / (1.0 + 4.0 * distance)))


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label} not found: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid {label}: {path}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return document


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _file_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


__all__ = [
    "PROFILE_POLICY",
    "PROFILE_SCHEMA",
    "build_personal_melody_profile",
    "load_personal_melody_profile",
    "rank_melody_alternatives",
    "validate_ranking_context",
]
