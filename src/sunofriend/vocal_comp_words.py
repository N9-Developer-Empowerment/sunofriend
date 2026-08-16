"""Canonical-word alignment for auxiliary local vocal transcripts.

Speech recognition is evidence about what may have been sung. It never
rewrites supplied lyrics. Insertions, omissions and substitutions remain
explicit, and syllable timing remains unavailable until a singing-oriented
phoneme aligner supplies it.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import tempfile
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Mapping, Sequence

from .vocal_comp import _document_sha256, _file, _sha256, _write_json


VOCAL_COMP_WORD_ALIGNMENT_SCHEMA = "sunofriend.vocal-comp-word-alignment.v2"
VOCAL_COMP_WORD_ALIGNMENT_POLICY = (
    "canonical-word-global-dp-unanchored-line-split-v2"
)
_SOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_WORD = re.compile(r"[\w]+(?:['’][\w]+)*", re.UNICODE)
_MAX_LYRICS_BYTES = 256 * 1024
_MAX_TRANSCRIPT_BYTES = 8 * 1024 * 1024


def align_vocal_comp_transcripts(
    lyrics: str | Path,
    *,
    transcripts: Mapping[str, str | Path],
    audio: Mapping[str, str | Path],
    out_dir: str | Path,
) -> dict[str, Any]:
    """Align timestamped STT candidates to immutable canonical lyric words."""

    lyrics_path = _file(lyrics, "canonical lyrics")
    if lyrics_path.stat().st_size > _MAX_LYRICS_BYTES:
        raise ValueError("canonical lyrics must be no larger than 256 KiB")
    canonical_text = lyrics_path.read_text(encoding="utf-8")
    canonical = _canonical_words(canonical_text)
    if not canonical:
        raise ValueError("canonical lyrics contain no words")
    if not 1 <= len(transcripts) <= 25:
        raise ValueError("word alignment requires 1-25 transcript sources")
    if set(transcripts) != set(audio):
        raise ValueError("transcript and audio source IDs must match exactly")
    for source_id in transcripts:
        if not _SOURCE_ID.fullmatch(source_id):
            raise ValueError(f"unsafe transcript source ID: {source_id}")

    destination = Path(out_dir).expanduser().absolute()
    if destination.exists():
        raise ValueError(f"word-alignment output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent)
    )
    os.chmod(temporary, 0o700)
    try:
        source_reports: dict[str, Any] = {}
        for source_id in sorted(transcripts):
            transcript_path = _file(transcripts[source_id], f"{source_id} transcript")
            audio_path = _file(audio[source_id], f"{source_id} audio")
            if transcript_path.stat().st_size > _MAX_TRANSCRIPT_BYTES:
                raise ValueError(f"{source_id} transcript exceeds 8 MiB")
            document = _read_transcript(transcript_path)
            observed = _timestamped_words(document)
            duration = _audio_duration(audio_path)
            if observed and observed[-1]["end_seconds"] > duration + 0.25:
                raise ValueError(f"{source_id} transcript extends beyond its audio")
            operations = align_word_sequences(canonical, observed)
            counts = _counts(row["operation"] for row in operations)
            matched = counts.get("match", 0)
            substituted = counts.get("substitution_candidate", 0)
            source_reports[source_id] = {
                "source_id": source_id,
                "audio": _identity(audio_path),
                "audio_duration_seconds": round(duration, 9),
                "transcript": _identity(transcript_path),
                "transcript_engine": _transcript_engine(document),
                "observed_word_count": len(observed),
                "operation_counts": counts,
                "exact_canonical_coverage": round(matched / len(canonical), 6),
                "candidate_canonical_coverage": round(
                    (matched + substituted) / len(canonical), 6
                ),
                "adlib_candidate_count": counts.get("insertion_adlib_candidate", 0),
                "omission_candidate_count": counts.get("omission_candidate", 0),
                "operations": operations,
                "canonical_text_mutated": False,
                "syllable_alignment": {
                    "status": "unavailable",
                    "reason": "requires_reviewed_singing_oriented_phoneme_alignment",
                    "timestamps_inferred_from_word_duration": False,
                },
                "review_required": True,
            }
            _write_json(temporary / f"{source_id}.word-alignment.json", source_reports[source_id])

        result = {
            "schema": VOCAL_COMP_WORD_ALIGNMENT_SCHEMA,
            "alignment_policy": VOCAL_COMP_WORD_ALIGNMENT_POLICY,
            "status": "complete_unreviewed",
            "canonical_lyrics": _identity(lyrics_path),
            "canonical_word_count": len(canonical),
            "canonical_words": canonical,
            "source_count": len(source_reports),
            "sources": source_reports,
            "interpretation": {
                "speech_recognition_is_auxiliary": True,
                "known_lyrics_are_canonical": True,
                "insertions_are_adlib_candidates_not_lyrics": True,
                "omissions_are_candidates_not_proof": True,
                "substitutions_are_candidates_not_rewrites": True,
                "syllable_timing_claimed": False,
            },
            "automatic_selection": False,
            "audio_comp_rendered": False,
            "pitch_correction_applied": False,
            "network_used": False,
        }
        result["alignment_sha256"] = _document_sha256(result)
        _write_json(temporary / "vocal-comp-word-alignment.json", result)
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        **result,
        "output_directory": str(destination),
        "alignment": str(destination / "vocal-comp-word-alignment.json"),
    }


def align_word_sequences(
    canonical: Sequence[Mapping[str, Any]],
    observed: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Globally align words while retaining every gap and low-confidence edit."""

    rows = len(canonical) + 1
    columns = len(observed) + 1
    costs = [[0.0] * columns for _ in range(rows)]
    moves = [[""] * columns for _ in range(rows)]
    for index in range(1, rows):
        costs[index][0] = costs[index - 1][0] + 1.0
        moves[index][0] = "delete"
    for index in range(1, columns):
        costs[0][index] = costs[0][index - 1] + 0.85
        moves[0][index] = "insert"
    for left in range(1, rows):
        for right in range(1, columns):
            similarity = _similarity(
                str(canonical[left - 1]["normalized"]),
                str(observed[right - 1]["normalized"]),
            )
            diagonal_cost = costs[left - 1][right - 1] + (1.0 - similarity) * 1.2
            candidates = (
                (diagonal_cost, "diagonal"),
                (costs[left - 1][right] + 1.0, "delete"),
                (costs[left][right - 1] + 0.85, "insert"),
            )
            costs[left][right], moves[left][right] = min(
                candidates, key=lambda value: (value[0], value[1])
            )

    operations: list[dict[str, Any]] = []
    left = len(canonical)
    right = len(observed)
    while left or right:
        move = moves[left][right]
        if move == "diagonal":
            expected = canonical[left - 1]
            heard = observed[right - 1]
            similarity = _similarity(
                str(expected["normalized"]), str(heard["normalized"])
            )
            exact = expected["normalized"] == heard["normalized"]
            operations.append(
                {
                    "operation": "match" if exact else "substitution_candidate",
                    "canonical": dict(expected),
                    "observed": dict(heard),
                    "text_similarity": round(similarity, 6),
                    "review_required": not exact,
                }
            )
            left -= 1
            right -= 1
        elif move == "delete":
            operations.append(
                {
                    "operation": "omission_candidate",
                    "canonical": dict(canonical[left - 1]),
                    "observed": None,
                    "text_similarity": None,
                    "review_required": True,
                }
            )
            left -= 1
        elif move == "insert":
            operations.append(
                {
                    "operation": "insertion_adlib_candidate",
                    "canonical": None,
                    "observed": dict(observed[right - 1]),
                    "text_similarity": None,
                    "review_required": True,
                }
            )
            right -= 1
        else:
            raise RuntimeError("word alignment backtrace is incomplete")
    operations.reverse()
    operations = _split_unanchored_canonical_lines(operations)
    for index, row in enumerate(operations, 1):
        row["operation_index"] = index
    return operations


def _split_unanchored_canonical_lines(
    operations: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Avoid claiming word substitutions when a whole lyric line has no anchor.

    A short non-canonical phrase can otherwise be paired word-for-word with an
    omitted canonical line merely because substitution is cheaper than two
    gaps. With no exact word anywhere in that lyric line, retaining the heard
    words as insertion/ad-lib candidates and the canonical words as omissions
    is the safer, reviewable representation.
    """

    line_stats: dict[int, dict[str, int]] = {}
    for row in operations:
        canonical = row.get("canonical")
        if not isinstance(canonical, Mapping):
            continue
        line_index = int(canonical["line_index"])
        stats = line_stats.setdefault(line_index, {"matches": 0, "substitutions": 0})
        if row.get("operation") == "match":
            stats["matches"] += 1
        elif row.get("operation") == "substitution_candidate":
            stats["substitutions"] += 1
    unanchored = {
        line_index
        for line_index, stats in line_stats.items()
        if stats["matches"] == 0 and stats["substitutions"] > 0
    }
    if not unanchored:
        return [dict(row) for row in operations]

    spans: dict[int, tuple[int, int]] = {}
    for line_index in unanchored:
        indices = [
            index
            for index, row in enumerate(operations)
            if isinstance(row.get("canonical"), Mapping)
            and int(row["canonical"]["line_index"]) == line_index
        ]
        spans[line_index] = (min(indices), max(indices))

    result: list[dict[str, Any]] = []
    index = 0
    while index < len(operations):
        line_index = next(
            (
                candidate
                for candidate, (start, _end) in spans.items()
                if start == index
            ),
            None,
        )
        if line_index is None:
            result.append(dict(operations[index]))
            index += 1
            continue
        _start, end = spans[line_index]
        span = operations[index : end + 1]
        observed = sorted(
            (
                dict(row["observed"])
                for row in span
                if isinstance(row.get("observed"), Mapping)
            ),
            key=lambda row: int(row["observed_index"]),
        )
        canonical = sorted(
            (
                dict(row["canonical"])
                for row in span
                if isinstance(row.get("canonical"), Mapping)
                and int(row["canonical"]["line_index"]) == line_index
            ),
            key=lambda row: int(row["canonical_index"]),
        )
        for heard in observed:
            result.append(
                {
                    "operation": "insertion_adlib_candidate",
                    "canonical": None,
                    "observed": heard,
                    "text_similarity": None,
                    "review_required": True,
                    "alignment_reason": "canonical_line_has_no_exact_word_anchor",
                }
            )
        for expected in canonical:
            result.append(
                {
                    "operation": "omission_candidate",
                    "canonical": expected,
                    "observed": None,
                    "text_similarity": None,
                    "review_required": True,
                    "alignment_reason": "canonical_line_has_no_exact_word_anchor",
                }
            )
        index = end + 1
    return result


def _canonical_words(text: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    lyric_line = 0
    for physical_line, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line or (line.startswith("[") and line.endswith("]")):
            continue
        lyric_line += 1
        for word_index, match in enumerate(_WORD.finditer(line), 1):
            text_value = match.group(0)
            result.append(
                {
                    "canonical_index": len(result) + 1,
                    "line_index": lyric_line,
                    "physical_line_index": physical_line,
                    "word_index_in_line": word_index,
                    "text": text_value,
                    "normalized": _normalize(text_value),
                }
            )
    return result


def _timestamped_words(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_words: list[Mapping[str, Any]] = []
    if isinstance(document.get("words"), list):
        raw_words.extend(row for row in document["words"] if isinstance(row, Mapping))
    for segment in document.get("segments", []):
        if isinstance(segment, Mapping) and isinstance(segment.get("words"), list):
            raw_words.extend(
                row for row in segment["words"] if isinstance(row, Mapping)
            )
    if not raw_words:
        raise ValueError("transcript must contain word-level timestamps")
    result: list[dict[str, Any]] = []
    previous_start = -1.0
    for index, row in enumerate(raw_words, 1):
        text = str(row.get("word", row.get("text", ""))).strip()
        start = float(row.get("start", row.get("start_seconds", -1.0)))
        end = float(row.get("end", row.get("end_seconds", -1.0)))
        probability = row.get("probability", row.get("confidence"))
        if not text or not math.isfinite(start) or not math.isfinite(end):
            raise ValueError("transcript words require finite text/start/end")
        if start < 0 or end <= start or start < previous_start:
            raise ValueError("transcript word timestamps must be chronological")
        normalized = _normalize(text)
        if not normalized:
            continue
        probability_value = None if probability is None else float(probability)
        if probability_value is not None and not 0.0 <= probability_value <= 1.0:
            raise ValueError("transcript word probability must be between zero and one")
        result.append(
            {
                "observed_index": index,
                "text": text,
                "normalized": normalized,
                "start_seconds": round(start, 6),
                "end_seconds": round(end, 6),
                "probability": (
                    round(probability_value, 6)
                    if probability_value is not None
                    else None
                ),
            }
        )
        previous_start = start
    return result


def _read_transcript(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid transcript JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError("transcript JSON must be an object")
    return value


def _transcript_engine(document: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": str(document.get("engine", document.get("backend", "unknown"))),
        "model": str(document.get("model", document.get("model_version", "unknown"))),
        "language": document.get("language"),
        "word_timestamps": True,
        "canonical_lyrics_prompted": document.get("canonical_lyrics_prompted"),
    }


def _normalize(value: str) -> str:
    return "".join(character for character in value.casefold().replace("’", "'") if character.isalnum() or character == "'")


def _similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    return SequenceMatcher(None, left, right, autojunk=False).ratio()


def _counts(values: Sequence[str] | Any) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return dict(sorted(result.items()))


def _identity(path: Path) -> dict[str, Any]:
    return {"bytes": path.stat().st_size, "sha256": _sha256(path)}


def _audio_duration(path: Path) -> float:
    import soundfile

    info = soundfile.info(path)
    if info.frames <= 0 or info.samplerate <= 0:
        raise ValueError(f"audio contains no samples: {path.name}")
    return info.frames / info.samplerate


__all__ = [
    "VOCAL_COMP_WORD_ALIGNMENT_POLICY",
    "VOCAL_COMP_WORD_ALIGNMENT_SCHEMA",
    "align_vocal_comp_transcripts",
    "align_word_sequences",
]
