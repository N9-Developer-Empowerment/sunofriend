"""Read-only browser audition plan for reversible vocal working choices.

The planner owns source selection and clock translation for phrase-local
captures.  It creates no audio, phrase decision, training label or canonical
Musical State change; the browser may only schedule the returned segments for
temporary listening.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .source_receipt import document_sha256


VOCAL_WORKING_AUDITION_SCHEMA = "sunofriend.vocal-working-audition.v2"
_SCOPES = {"phrase", "section", "song"}
_PHRASE_LOCAL_CLASSES = {
    "human_vocal_phrase_capture",
    "unreviewed_vocal_candidate",
}
_EDGE_FADE_SECONDS = 0.005


def create_vocal_working_audition(
    session: Mapping[str, Any],
    sources: Sequence[Mapping[str, Any]],
    working_choices: Mapping[str, Any] | None,
    *,
    active_phrase_id: str,
    scope: str,
    section_phrase_radius: int,
    song_start_seconds: float,
    song_end_seconds: float,
) -> dict[str, Any]:
    """Plan one phrase, section or song audition without rendering audio."""

    phrases = _phrases(session)
    active_index = _active_phrase_index(phrases, active_phrase_id)
    checked_scope = str(scope)
    if checked_scope not in _SCOPES:
        raise ValueError("working audition scope is not supported")
    selected, window = _scope_phrases(
        phrases,
        active_index=active_index,
        scope=checked_scope,
        section_phrase_radius=section_phrase_radius,
        song_start_seconds=song_start_seconds,
        song_end_seconds=song_end_seconds,
    )
    source_by_id = _sources(sources)
    reference = _original_reference(source_by_id.values())
    original_mix = _optional_source(
        source_by_id.values(), "authorised_original_mix"
    )
    backing = _optional_source(
        source_by_id.values(), "authorised_instrumental_backing"
    )
    _require_source_horizon(reference, float(window["end_seconds"]))
    if original_mix:
        _require_source_horizon(original_mix, float(window["end_seconds"]))
    if backing:
        _require_source_horizon(backing, float(window["end_seconds"]))
    choices = _choices(working_choices)
    vocal_segments = _continuous_vocal_segments(
        selected,
        window=window,
        source_by_id=source_by_id,
        reference=reference,
        choices=choices,
    )
    comparison_source = original_mix or reference
    document: dict[str, Any] = {
        "schema": VOCAL_WORKING_AUDITION_SCHEMA,
        "status": "planned_browser_audition_only",
        "scope": checked_scope,
        "active_phrase_id": active_phrase_id,
        "binding": {
            "musical_state_sha256": _musical_state_sha256(session),
            "working_choices_sha256": (
                working_choices.get("document_sha256") if working_choices else None
            ),
        },
        "window": window,
        "duration_seconds": window["end_seconds"] - window["start_seconds"],
        "original_comparison": {
            **_window_source(
                comparison_source,
                window=window,
                window_start=window["start_seconds"],
            ),
            "comparison_kind": "full_mix" if original_mix else "reference_vocal_only",
        },
        "working_mix": {
            "backing": (
                _window_source(
                    backing,
                    window=window,
                    window_start=window["start_seconds"],
                )
                if backing
                else None
            ),
            "vocal_segments": vocal_segments,
            "reference_context_preserved": True,
        },
        "join": {
            "policy": "browser_scheduled_phrase_boundaries",
            "edge_fade_seconds": _EDGE_FADE_SECONDS,
            "rendered_artifact": False,
            "join_reviewed": False,
        },
        "authority": "none",
        "effects": _zero_effects(),
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    return validate_vocal_working_audition(document)


def validate_vocal_working_audition(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a path-free, zero-authority working audition plan."""

    if not isinstance(value, Mapping):
        raise ValueError("working audition must be an object")
    document = dict(value)
    expected_keys = {
        "schema",
        "status",
        "scope",
        "active_phrase_id",
        "binding",
        "window",
        "duration_seconds",
        "original_comparison",
        "working_mix",
        "join",
        "authority",
        "effects",
        "network_used",
        "document_sha256",
    }
    if set(document) != expected_keys or document.get(
        "schema"
    ) != VOCAL_WORKING_AUDITION_SCHEMA:
        raise ValueError("working audition fields or schema changed")
    if document.get("status") != "planned_browser_audition_only":
        raise ValueError("working audition status changed")
    if document.get("scope") not in _SCOPES:
        raise ValueError("working audition scope is not supported")
    _safe_text(document.get("active_phrase_id"), "active phrase")
    _validate_binding(document.get("binding"))
    window = _window(document.get("window"))
    duration = _finite(document.get("duration_seconds"), "audition duration")
    if duration <= 0.0 or not math.isclose(
        duration,
        window["end_seconds"] - window["start_seconds"],
        abs_tol=1e-9,
    ):
        raise ValueError("working audition duration changed")
    _validate_original_comparison(document.get("original_comparison"), duration)
    segments = _validate_working_mix(document.get("working_mix"), duration)
    for segment in segments:
        _validate_segment(segment, duration=duration)
    _validate_continuous_destination(segments, duration=duration)
    _validate_join_and_authority(document)
    unhashed = dict(document)
    supplied_hash = unhashed.pop("document_sha256", None)
    if supplied_hash != document_sha256(unhashed):
        raise ValueError("working audition document hash changed")
    return document


def _validate_original_comparison(value: Any, duration: float) -> None:
    _validate_window_source(value, duration=duration)
    comparison_kind = value.get("comparison_kind")
    if comparison_kind not in {"full_mix", "reference_vocal_only"}:
        raise ValueError("working audition comparison kind changed")
    expected_class = (
        "authorised_original_mix"
        if comparison_kind == "full_mix"
        else "authorised_ai_vocal_reference"
    )
    if value.get("source_class") != expected_class:
        raise ValueError("working audition comparison source changed")


def _validate_working_mix(value: Any, duration: float) -> list[Mapping[str, Any]]:
    if not isinstance(value, Mapping) or set(value) != {
        "backing",
        "vocal_segments",
        "reference_context_preserved",
    }:
        raise ValueError("working audition mix fields changed")
    if value.get("reference_context_preserved") is not True:
        raise ValueError("working audition reference-context policy changed")
    backing = value.get("backing")
    if backing is not None:
        _validate_window_source(backing, duration=duration)
        if backing.get("source_class") != "authorised_instrumental_backing":
            raise ValueError("working audition backing class changed")
    segments = value.get("vocal_segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("working audition needs at least one segment")
    return segments


def _validate_join_and_authority(document: Mapping[str, Any]) -> None:
    if document.get("join") != {
        "policy": "browser_scheduled_phrase_boundaries",
        "edge_fade_seconds": _EDGE_FADE_SECONDS,
        "rendered_artifact": False,
        "join_reviewed": False,
    }:
        raise ValueError("working audition join policy changed")
    if (
        document.get("authority") != "none"
        or document.get("effects") != _zero_effects()
        or document.get("network_used") is not False
    ):
        raise ValueError("working audition authority or effects changed")


def _phrases(session: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = session.get("phrases") if isinstance(session, Mapping) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("working audition needs session phrases")
    phrases: list[Mapping[str, Any]] = []
    previous_end = -1.0
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("working audition phrase changed")
        _safe_text(row.get("phrase_id"), "phrase id")
        _safe_text(row.get("lyrics"), "phrase lyrics")
        start = _finite(row.get("start_seconds"), "phrase start")
        end = _finite(row.get("end_seconds"), "phrase end")
        if start < previous_end or end <= start:
            raise ValueError("working audition phrase clock changed")
        previous_end = end
        phrases.append(row)
    return phrases


def _active_phrase_index(
    phrases: Sequence[Mapping[str, Any]], active_phrase_id: str
) -> int:
    _safe_text(active_phrase_id, "active phrase")
    for index, phrase in enumerate(phrases):
        if phrase["phrase_id"] == active_phrase_id:
            return index
    raise ValueError("working audition active phrase is unknown")


def _scope_phrases(
    phrases: Sequence[Mapping[str, Any]],
    *,
    active_index: int,
    scope: str,
    section_phrase_radius: int,
    song_start_seconds: float,
    song_end_seconds: float,
) -> tuple[list[Mapping[str, Any]], dict[str, float]]:
    if isinstance(section_phrase_radius, bool) or not isinstance(
        section_phrase_radius, int
    ):
        raise ValueError("working audition section radius changed")
    if section_phrase_radius < 0 or section_phrase_radius > 20:
        raise ValueError("working audition section radius changed")
    if scope == "phrase":
        selected = [phrases[active_index]]
        start = float(selected[0]["start_seconds"])
        end = float(selected[0]["end_seconds"])
    elif scope == "section":
        selected = list(
            phrases[
                max(0, active_index - section_phrase_radius) : min(
                    len(phrases), active_index + section_phrase_radius + 1
                )
            ]
        )
        start = float(selected[0]["start_seconds"])
        end = float(selected[-1]["end_seconds"])
    else:
        selected = list(phrases)
        start = _finite(song_start_seconds, "song start")
        end = _finite(song_end_seconds, "song end")
        if start < 0.0 or end < float(selected[-1]["end_seconds"]):
            raise ValueError("working audition song window changed")
    return selected, {"start_seconds": start, "end_seconds": end}


def _sources(
    sources: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    if not isinstance(sources, Sequence) or isinstance(sources, (str, bytes)):
        raise ValueError("working audition sources changed")
    result: dict[str, Mapping[str, Any]] = {}
    for source in sources:
        if not isinstance(source, Mapping):
            raise ValueError("working audition source changed")
        source_id = _safe_text(source.get("source_id"), "source id")
        if source_id in result:
            raise ValueError("working audition source ids must be unique")
        _safe_text(source.get("source_class"), "source class")
        _safe_media_url(source.get("media_url"))
        result[source_id] = source
    return result


def _original_reference(
    sources: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    matches = [
        source
        for source in sources
        if source.get("source_class") == "authorised_ai_vocal_reference"
    ]
    if len(matches) != 1:
        raise ValueError("working audition needs one authorised reference")
    return matches[0]


def _optional_source(
    sources: Sequence[Mapping[str, Any]], source_class: str
) -> Mapping[str, Any] | None:
    matches = [source for source in sources if source.get("source_class") == source_class]
    if len(matches) > 1:
        raise ValueError(f"working audition has multiple {source_class} sources")
    return matches[0] if matches else None


def _choices(working_choices: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if working_choices is None:
        return {}
    choices = working_choices.get("choices")
    if not isinstance(choices, Mapping):
        raise ValueError("working audition choices changed")
    return choices


def _continuous_vocal_segments(
    phrases: Sequence[Mapping[str, Any]],
    *,
    window: Mapping[str, float],
    source_by_id: Mapping[str, Mapping[str, Any]],
    reference: Mapping[str, Any],
    choices: Mapping[str, Any],
) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    cursor = float(window["start_seconds"])
    for phrase in phrases:
        start = float(phrase["start_seconds"])
        if start > cursor:
            segments.append(
                _reference_context_segment(
                    reference,
                    start=cursor,
                    end=start,
                    window_start=float(window["start_seconds"]),
                )
            )
        segments.append(
            _phrase_segment(
                phrase,
                window_start=float(window["start_seconds"]),
                source_by_id=source_by_id,
                reference=reference,
                choices=choices,
            )
        )
        cursor = float(phrase["end_seconds"])
    if cursor < float(window["end_seconds"]):
        segments.append(
            _reference_context_segment(
                reference,
                start=cursor,
                end=float(window["end_seconds"]),
                window_start=float(window["start_seconds"]),
            )
        )
    return segments


def _phrase_segment(
    phrase: Mapping[str, Any],
    *,
    window_start: float,
    source_by_id: Mapping[str, Mapping[str, Any]],
    reference: Mapping[str, Any],
    choices: Mapping[str, Any],
) -> dict[str, Any]:
    phrase_id = str(phrase["phrase_id"])
    choice = choices.get(phrase_id)
    if choice is None:
        source = reference
        selection = "original_reference_fallback"
    else:
        if not isinstance(choice, Mapping):
            raise ValueError("working audition choice changed")
        source_id = _safe_text(choice.get("source_id"), "working source id")
        source = source_by_id.get(source_id)
        if source is None or source.get("bound_phrase_id") != phrase_id:
            raise ValueError("working audition choice is not bound to its phrase")
        selection = "reversible_working_choice"
    start = float(phrase["start_seconds"])
    end = float(phrase["end_seconds"])
    if source["source_class"] in _PHRASE_LOCAL_CLASSES:
        source_start = _finite(
            source.get("playback_start_seconds"), "local source start"
        )
        source_end = _finite(source.get("playback_end_seconds"), "local source end")
        if not math.isclose(source_end - source_start, end - start, abs_tol=1e-6):
            raise ValueError("working audition local source duration changed")
    else:
        source_start = start
        source_end = end
    return {
        "segment_kind": "phrase",
        "phrase_id": phrase_id,
        "lyrics": str(phrase["lyrics"]),
        "source_id": str(source["source_id"]),
        "source_class": str(source["source_class"]),
        "source_audio_sha256": _source_audio_sha256(source),
        "media_url": _safe_media_url(source.get("media_url")),
        "selection": selection,
        "source_start_seconds": source_start,
        "source_end_seconds": source_end,
        "destination_start_seconds": start - window_start,
        "destination_end_seconds": end - window_start,
    }


def _reference_context_segment(
    reference: Mapping[str, Any],
    *,
    start: float,
    end: float,
    window_start: float,
) -> dict[str, Any]:
    return {
        "segment_kind": "reference_context",
        "phrase_id": None,
        "lyrics": None,
        "source_id": str(reference["source_id"]),
        "source_class": str(reference["source_class"]),
        "source_audio_sha256": _source_audio_sha256(reference),
        "media_url": _safe_media_url(reference.get("media_url")),
        "selection": "reference_context_preserved",
        "source_start_seconds": start,
        "source_end_seconds": end,
        "destination_start_seconds": start - window_start,
        "destination_end_seconds": end - window_start,
    }


def _window_source(
    source: Mapping[str, Any],
    *,
    window: Mapping[str, float],
    window_start: float,
) -> dict[str, Any]:
    start = float(window["start_seconds"])
    end = float(window["end_seconds"])
    return {
        "source_id": str(source["source_id"]),
        "source_class": str(source["source_class"]),
        "source_audio_sha256": _source_audio_sha256(source),
        "media_url": _safe_media_url(source.get("media_url")),
        "source_start_seconds": start,
        "source_end_seconds": end,
        "destination_start_seconds": start - window_start,
        "destination_end_seconds": end - window_start,
    }


def _require_source_horizon(source: Mapping[str, Any], end_seconds: float) -> None:
    properties = source.get("audio_properties")
    if not isinstance(properties, Mapping):
        raise ValueError("working audition source audio properties changed")
    duration = _finite(properties.get("duration_seconds"), "source duration")
    if duration + 1e-9 < end_seconds:
        raise ValueError("working audition source is shorter than its context window")


def _musical_state_sha256(session: Mapping[str, Any]) -> str:
    binding = session.get("binding")
    if not isinstance(binding, Mapping):
        raise ValueError("working audition session binding changed")
    return _sha(binding.get("musical_state_sha256"), "musical state")


def _source_audio_sha256(source: Mapping[str, Any]) -> str:
    direct = source.get("audio_sha256")
    if direct is not None:
        return _sha(direct, "source audio")
    audio = source.get("audio")
    if not isinstance(audio, Mapping):
        raise ValueError("working audition source audio changed")
    return _sha(audio.get("sha256"), "source audio")


def _validate_binding(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "musical_state_sha256",
        "working_choices_sha256",
    }:
        raise ValueError("working audition binding changed")
    _sha(value.get("musical_state_sha256"), "musical state")
    if value.get("working_choices_sha256") is not None:
        _sha(value.get("working_choices_sha256"), "working choices")


def _window(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping) or set(value) != {
        "start_seconds",
        "end_seconds",
    }:
        raise ValueError("working audition window changed")
    start = _finite(value.get("start_seconds"), "window start")
    end = _finite(value.get("end_seconds"), "window end")
    if start < 0.0 or end <= start:
        raise ValueError("working audition window changed")
    return {"start_seconds": start, "end_seconds": end}


def _validate_segment(value: Any, *, duration: float) -> None:
    expected = {
        "segment_kind",
        "phrase_id",
        "lyrics",
        "source_id",
        "source_class",
        "source_audio_sha256",
        "media_url",
        "selection",
        "source_start_seconds",
        "source_end_seconds",
        "destination_start_seconds",
        "destination_end_seconds",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("working audition segment fields changed")
    _validate_segment_identity(value)
    _validate_segment_clock(value, duration)


def _validate_segment_identity(value: Mapping[str, Any]) -> None:
    segment_kind = value.get("segment_kind")
    if segment_kind not in {"phrase", "reference_context"}:
        raise ValueError("working audition segment kind changed")
    for key in ("source_id", "source_class"):
        _safe_text(value.get(key), key)
    if segment_kind == "phrase":
        _safe_text(value.get("phrase_id"), "phrase_id")
        _safe_text(value.get("lyrics"), "lyrics")
    elif value.get("phrase_id") is not None or value.get("lyrics") is not None:
        raise ValueError("working audition reference context changed")
    _sha(value.get("source_audio_sha256"), "source audio")
    _safe_media_url(value.get("media_url"))
    if value.get("selection") not in {
        "reversible_working_choice",
        "original_reference_fallback",
        "reference_context_preserved",
    }:
        raise ValueError("working audition segment selection changed")
    if segment_kind == "reference_context" and (
        value.get("selection") != "reference_context_preserved"
        or value.get("source_class") != "authorised_ai_vocal_reference"
    ):
        raise ValueError("working audition reference context changed")
    if segment_kind == "phrase" and (
        value.get("selection") == "reference_context_preserved"
        or (
            value.get("selection") == "original_reference_fallback"
            and value.get("source_class") != "authorised_ai_vocal_reference"
        )
    ):
        raise ValueError("working audition phrase selection changed")


def _validate_segment_clock(value: Mapping[str, Any], duration: float) -> None:
    source_start = _finite(value.get("source_start_seconds"), "source start")
    source_end = _finite(value.get("source_end_seconds"), "source end")
    destination_start = _finite(
        value.get("destination_start_seconds"), "destination start"
    )
    destination_end = _finite(
        value.get("destination_end_seconds"), "destination end"
    )
    if (
        source_start < 0.0
        or source_end <= source_start
        or destination_start < 0.0
        or destination_end <= destination_start
        or destination_end > duration + 1e-9
        or not math.isclose(
            source_end - source_start,
            destination_end - destination_start,
            abs_tol=1e-6,
        )
    ):
        raise ValueError("working audition segment clock changed")


def _validate_window_source(value: Any, *, duration: float) -> None:
    expected = {
        "source_id",
        "source_class",
        "source_audio_sha256",
        "media_url",
        "source_start_seconds",
        "source_end_seconds",
        "destination_start_seconds",
        "destination_end_seconds",
    }
    if not isinstance(value, Mapping):
        raise ValueError("working audition window source changed")
    extra = set(value) - expected
    if extra not in (set(), {"comparison_kind"}) or not expected.issubset(value):
        raise ValueError("working audition window source fields changed")
    for key in ("source_id", "source_class"):
        _safe_text(value.get(key), key)
    _sha(value.get("source_audio_sha256"), "source audio")
    _safe_media_url(value.get("media_url"))
    source_start = _finite(value.get("source_start_seconds"), "source start")
    source_end = _finite(value.get("source_end_seconds"), "source end")
    destination_start = _finite(
        value.get("destination_start_seconds"), "destination start"
    )
    destination_end = _finite(
        value.get("destination_end_seconds"), "destination end"
    )
    if (
        source_start < 0.0
        or source_end <= source_start
        or destination_start != 0.0
        or not math.isclose(destination_end, duration, abs_tol=1e-9)
        or not math.isclose(source_end - source_start, duration, abs_tol=1e-9)
    ):
        raise ValueError("working audition window source clock changed")


def _validate_continuous_destination(
    segments: Sequence[Mapping[str, Any]], *, duration: float
) -> None:
    cursor = 0.0
    for segment in segments:
        start = float(segment["destination_start_seconds"])
        end = float(segment["destination_end_seconds"])
        if not math.isclose(start, cursor, abs_tol=1e-9):
            raise ValueError("working audition vocal context is not continuous")
        cursor = end
    if not math.isclose(cursor, duration, abs_tol=1e-9):
        raise ValueError("working audition vocal context is not continuous")


def _safe_text(value: Any, label: str) -> str:
    text = str(value).strip()
    if not text or len(text) > 2_000:
        raise ValueError(f"{label} changed")
    return text


def _safe_media_url(value: Any) -> str:
    url = str(value)
    if not url.startswith("/media/") or "?" in url or "#" in url:
        raise ValueError("working audition media URL changed")
    return url


def _sha(value: Any, label: str) -> str:
    text = str(value)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{label} hash changed")
    return text


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} changed")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} changed")
    return number


def _zero_effects() -> dict[str, bool]:
    return {
        "audio_rendered": False,
        "source_mutated": False,
        "phrase_decision_created": False,
        "correction_applied": False,
        "training_label_created": False,
    }


__all__ = [
    "VOCAL_WORKING_AUDITION_SCHEMA",
    "create_vocal_working_audition",
    "validate_vocal_working_audition",
]
