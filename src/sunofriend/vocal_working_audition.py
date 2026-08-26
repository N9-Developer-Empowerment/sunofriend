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


VOCAL_WORKING_AUDITION_SCHEMA = "sunofriend.vocal-working-audition.v1"
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
    original = _original_reference(source_by_id.values())
    choices = _choices(working_choices)
    segments = [
        _segment(
            phrase,
            window_start=window["start_seconds"],
            source_by_id=source_by_id,
            original=original,
            choices=choices,
        )
        for phrase in selected
    ]
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
        "segments": segments,
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
        "segments",
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
    segments = document.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("working audition needs at least one segment")
    for segment in segments:
        _validate_segment(segment, duration=duration)
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
    unhashed = dict(document)
    supplied_hash = unhashed.pop("document_sha256", None)
    if supplied_hash != document_sha256(unhashed):
        raise ValueError("working audition document hash changed")
    return document


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


def _choices(working_choices: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if working_choices is None:
        return {}
    choices = working_choices.get("choices")
    if not isinstance(choices, Mapping):
        raise ValueError("working audition choices changed")
    return choices


def _segment(
    phrase: Mapping[str, Any],
    *,
    window_start: float,
    source_by_id: Mapping[str, Mapping[str, Any]],
    original: Mapping[str, Any],
    choices: Mapping[str, Any],
) -> dict[str, Any]:
    phrase_id = str(phrase["phrase_id"])
    choice = choices.get(phrase_id)
    if choice is None:
        source = original
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
    for key in ("phrase_id", "lyrics", "source_id", "source_class"):
        _safe_text(value.get(key), key)
    _sha(value.get("source_audio_sha256"), "source audio")
    _safe_media_url(value.get("media_url"))
    if value.get("selection") not in {
        "reversible_working_choice",
        "original_reference_fallback",
    }:
        raise ValueError("working audition segment selection changed")
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
