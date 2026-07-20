"""Validate explicit phrase-review links for the local Workbench.

This module is deliberately a projection layer, not discovery.  A caller must
name one completed hybrid report, its exact phrase-review manifest and the
already-built Workbench stem that owns all three MIDI candidates.  The result
contains a path-free public record plus a narrowly allow-listed server file
map; it never changes MIDI, review state or candidate selection.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


WORKBENCH_PHRASE_REVIEW_LINK_SCHEMA = "sunofriend.workbench-phrase-review-link.v1"
_HYBRID_REPORT_SCHEMA = "sunofriend.hybrid-candidate-report.v1"
_PHRASE_REVIEW_SCHEMA = "sunofriend.melody-phrase-review.v1"
_LANES = ("S0", "M1", "M3")
_PAIRWISE_LANES = {("S0", "M1"), ("S0", "M3"), ("M1", "M3")}
_SELECTION_POLICY = (
    "human phrase choice; raw Basic Pitch and agreed-F0 boundary candidates "
    "remain unchanged"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_REPORT_EFFECTS = {
    "ai_inference_runs": 0,
    "midi_files_created": 0,
    "midi_notes_mutated": 0,
    "source_audio_mutated": False,
    "raw_candidates_mutated": False,
    "automatic_selection": False,
    "automatic_promotion": False,
    "default_changed": False,
}
_LINEAGE_STATUSES = {
    "comparison_source": "hash-and-size-verified",
    "M1_full_mix_association": "caller-supplied-derivation-unverified",
    "M3_original_source_midi": "manifest-claimed-payload-unverified",
}
_INTERPRETATION_FLAGS = {
    "agreement_is_accuracy": False,
    "source_support_is_selection": False,
    "octave_equivalence_is_agreement": False,
    "ranking_is_preference": False,
    "review_required_before_hybrid_midi": True,
    "m1_same_song_derivation_verified": False,
    "m3_original_source_midi_payload_verified": False,
}


@dataclass(frozen=True)
class _Fingerprint:
    device: int
    inode: int
    size: int
    mtime_ns: int
    sha256: str


def build_workbench_phrase_review_link(
    stem: Mapping[str, Any],
    hybrid_report_path: str | Path,
    phrase_review_path: str | Path,
    *,
    allowed_candidate_roots: Sequence[str | Path],
) -> dict[str, Any]:
    """Return a verified phrase-review projection for one current stem.

    ``hybrid_report_path`` and ``phrase_review_path`` are explicit inputs and
    must both resolve beneath one of ``allowed_candidate_roots``.  The return
    value has the stable shape ``{public, entrypoint, files}``; only ``files``
    contains absolute paths, for local server registration.
    """

    roots = _allowed_roots(allowed_candidate_roots)
    report_path = _explicit_json_file(
        hybrid_report_path, roots=roots, label="hybrid report"
    )
    review_path = _explicit_json_file(
        phrase_review_path, roots=roots, label="phrase review"
    )
    fingerprints: dict[Path, _Fingerprint] = {}
    report, report_identity = _read_json_document(
        report_path, label="hybrid report", fingerprints=fingerprints
    )
    review, review_identity = _read_json_document(
        review_path, label="phrase review", fingerprints=fingerprints
    )

    _validate_hybrid_contract(report)
    _validate_phrase_review_contract(review)
    report_review = _mapping(report.get("phrase_review"), "hybrid phrase review")
    if (
        _identity(report_review, "hybrid phrase review") != review_identity
        or report_review.get("schema") != _PHRASE_REVIEW_SCHEMA
    ):
        raise ValueError("hybrid report does not pin the explicit phrase review")
    if _positive_number(report.get("bpm"), "hybrid BPM") != _positive_number(
        review.get("bpm"), "phrase-review BPM"
    ):
        raise ValueError("hybrid report and phrase-review BPM disagree")

    source_identity = _identity(
        _mapping(report.get("source"), "hybrid source"), "hybrid source"
    )
    if (
        _identity(
            _mapping(review.get("source"), "phrase-review source"),
            "phrase-review source",
        )
        != source_identity
    ):
        raise ValueError("hybrid report and phrase review source identities disagree")
    stem_id = _identifier(stem.get("stem_id"), "Workbench stem id")
    stem_source = _verified_catalog_file(
        stem.get("source"),
        stem.get("source_path"),
        label="Workbench stem source",
        fingerprints=fingerprints,
    )
    if stem_source != source_identity:
        raise ValueError("phrase-review source does not match the current stem")

    candidate_map = _map_candidates(
        stem,
        report,
        roots=roots,
        fingerprints=fingerprints,
    )
    review_phrases = _review_phrases(review)
    if _positive_integer(
        report_review.get("review_unit_count"), "hybrid review unit count"
    ) != len(review_phrases):
        raise ValueError("hybrid phrase-review unit count is inconsistent")
    report_phrases = _report_phrases(report, review_phrases)
    ranges = _ranked_ranges(report, report_phrases)
    files, entrypoint = _phrase_review_files(
        review_path,
        review,
        review_phrases,
        fingerprints=fingerprints,
    )

    public: dict[str, Any] = {
        "schema": WORKBENCH_PHRASE_REVIEW_LINK_SCHEMA,
        "status": "diagnostic-only",
        "stem_id": stem_id,
        "role": "lead",
        "bpm": _positive_number(report.get("bpm"), "hybrid BPM"),
        "report": report_identity,
        "phrase_review": {
            **review_identity,
            "review_unit_count": len(review_phrases),
            "alternative_names": list(review["alternative_names"]),
        },
        "source": source_identity,
        "candidate_map": candidate_map,
        "ranges": ranges,
        "lineage": dict(_LINEAGE_STATUSES),
        "effects": dict(_REPORT_EFFECTS),
    }
    public["link_sha256"] = _document_hash(public)
    _assert_unchanged(fingerprints)
    return {"public": public, "entrypoint": entrypoint, "files": files}


def _validate_hybrid_contract(document: Mapping[str, Any]) -> None:
    if document.get("schema") != _HYBRID_REPORT_SCHEMA:
        raise ValueError("unsupported hybrid report schema")
    if document.get("status") != "diagnostic-only":
        raise ValueError("hybrid report is not diagnostic-only")
    if document.get("role") != "lead":
        raise ValueError("Workbench phrase-review links support lead reports only")
    _positive_number(document.get("bpm"), "hybrid BPM")
    if not _exact_effects(document.get("effects")):
        raise ValueError("hybrid report mutation or selection effects are invalid")
    lineage = _mapping(document.get("lineage"), "hybrid lineage")
    for name, expected in _LINEAGE_STATUSES.items():
        record = _mapping(lineage.get(name), f"hybrid lineage {name}")
        if record.get("status") != expected:
            raise ValueError(f"hybrid lineage status is invalid: {name}")
    interpretation = _mapping(document.get("interpretation"), "hybrid interpretation")
    if any(
        interpretation.get(key) is not value
        for key, value in _INTERPRETATION_FLAGS.items()
    ):
        raise ValueError("hybrid report interpretation flags are invalid")


def _validate_phrase_review_contract(document: Mapping[str, Any]) -> None:
    if document.get("schema") != _PHRASE_REVIEW_SCHEMA:
        raise ValueError("unsupported phrase-review schema")
    if document.get("status") != "review-required":
        raise ValueError("phrase-review manifest is not review-required")
    if document.get("role") != "lead":
        raise ValueError("Workbench phrase-review links support lead reviews only")
    if document.get("selection_policy") != _SELECTION_POLICY:
        raise ValueError("phrase-review selection policy is unsupported")
    if document.get("raw_candidates_mutated") is not False:
        raise ValueError("phrase-review manifest does not preserve raw candidates")
    _positive_number(document.get("bpm"), "phrase-review BPM")


def _map_candidates(
    stem: Mapping[str, Any],
    report: Mapping[str, Any],
    *,
    roots: Sequence[Path],
    fingerprints: dict[Path, _Fingerprint],
) -> dict[str, Any]:
    rows = report.get("candidates")
    if not isinstance(rows, list) or [
        row.get("lane") if isinstance(row, Mapping) else None for row in rows
    ] != list(_LANES):
        raise ValueError("hybrid report must contain ordered S0, M1 and M3 candidates")
    current = stem.get("candidates")
    if not isinstance(current, list):
        raise ValueError("Workbench stem candidates must be a list")
    result: dict[str, Any] = {}
    seen_candidate_ids: set[str] = set()
    seen_identities: set[tuple[str, int]] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("hybrid candidate row is malformed")
        lane = str(row["lane"])
        identity = _identity(_mapping(row.get("midi"), f"{lane} MIDI"), f"{lane} MIDI")
        key = (identity["sha256"], identity["bytes"])
        if key in seen_identities:
            raise ValueError("hybrid lane MIDI identities must be distinct")
        seen_identities.add(key)
        matches = [
            candidate
            for candidate in current
            if isinstance(candidate, Mapping)
            and _identity_or_none(candidate.get("midi")) == identity
        ]
        if len(matches) != 1:
            raise ValueError(
                f"{lane} MIDI does not map uniquely to a current stem candidate"
            )
        candidate = matches[0]
        candidate_id = _identifier(
            candidate.get("candidate_id"), f"{lane} candidate id"
        )
        if candidate_id in seen_candidate_ids:
            raise ValueError("hybrid lanes map to the same current candidate")
        seen_candidate_ids.add(candidate_id)
        actual = _verified_catalog_file(
            candidate.get("midi"),
            candidate.get("midi_path"),
            label=f"{lane} current candidate MIDI",
            roots=roots,
            fingerprints=fingerprints,
        )
        if actual != identity:
            raise ValueError(f"{lane} current candidate MIDI changed")
        result[lane] = {
            "candidate_id": candidate_id,
            "midi": identity,
        }
    return result


def _review_phrases(document: Mapping[str, Any]) -> dict[int, dict[str, Any]]:
    rows = document.get("phrases")
    count = _positive_integer(document.get("review_unit_count"), "review unit count")
    if (
        not isinstance(rows, list)
        or len(rows) != count
        or _positive_integer(document.get("phrase_count"), "phrase count") != count
    ):
        raise ValueError("phrase-review unit counts are inconsistent")
    alternative_names = document.get("alternative_names")
    if not isinstance(alternative_names, list) or not alternative_names:
        raise ValueError("phrase-review alternative names are invalid")
    alternative_names = [
        _identifier(value, "phrase-review alternative name")
        for value in alternative_names
    ]
    if len(alternative_names) != len(set(alternative_names)):
        raise ValueError("phrase-review alternative names are invalid")
    result: dict[int, dict[str, Any]] = {}
    used_alternative_names: set[str] = set()
    previous_end = 0.0
    for position, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError("phrase-review phrase is not an object")
        index = _nonnegative_integer(row.get("phrase_index"), "phrase index")
        if index in result:
            raise ValueError("phrase-review phrase indices must be unique")
        start = _nonnegative_number(row.get("start_seconds"), "phrase start")
        end = _positive_number(row.get("end_seconds"), "phrase end")
        duration = _positive_number(row.get("duration_seconds"), "phrase duration")
        if end <= start or not math.isclose(duration, end - start, abs_tol=1e-6):
            raise ValueError("phrase-review phrase geometry is inconsistent")
        if position and start < previous_end:
            raise ValueError("phrase-review phrases overlap")
        previous_end = end
        window_start = _nonnegative_number(
            row.get("window_start_seconds"), "phrase window start"
        )
        window_end = _positive_number(
            row.get("window_end_seconds"), "phrase window end"
        )
        if window_start > start or window_end < end:
            raise ValueError("phrase-review window does not contain its phrase")
        row_names = row.get("alternative_names")
        if not isinstance(row_names, list) or not row_names:
            raise ValueError("phrase-review unit alternatives are invalid")
        row_names = [
            _identifier(value, "phrase-review unit alternative name")
            for value in row_names
        ]
        if len(row_names) != len(set(row_names)) or not set(row_names).issubset(
            alternative_names
        ):
            raise ValueError("phrase-review unit alternatives are invalid")
        used_alternative_names.update(row_names)
        alternatives = row.get("alternatives")
        if not isinstance(alternatives, Mapping) or set(alternatives) != set(row_names):
            raise ValueError("phrase-review alternative records are inconsistent")
        result[index] = {
            "phrase_index": index,
            "start_seconds": start,
            "end_seconds": end,
            "duration_seconds": duration,
            "source_audio": _relative_artifact(
                row.get("source_audio"), label="phrase source audio"
            ),
            "alternatives": dict(alternatives),
        }
    if set(result) != set(range(count)):
        raise ValueError("phrase-review phrase indices must be contiguous from zero")
    if used_alternative_names != set(alternative_names):
        raise ValueError("phrase-review declares unused alternatives")
    return result


def _report_phrases(
    document: Mapping[str, Any], review_phrases: Mapping[int, Mapping[str, Any]]
) -> dict[int, dict[str, Any]]:
    rows = document.get("phrases")
    if not isinstance(rows, list) or len(rows) != len(review_phrases):
        raise ValueError("hybrid phrase geometry count is inconsistent")
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("hybrid phrase geometry is malformed")
        index = _nonnegative_integer(row.get("phrase_index"), "hybrid phrase index")
        review = review_phrases.get(index)
        if review is None or index in result:
            raise ValueError("hybrid phrase geometry has an unknown or duplicate unit")
        expected = {
            "phrase_index": index,
            "start_seconds": _round9(review["start_seconds"]),
            "end_seconds": _round9(review["end_seconds"]),
            "duration_seconds": _round9(review["duration_seconds"]),
        }
        actual = {
            "phrase_index": index,
            "start_seconds": _finite_number(
                row.get("start_seconds"), "hybrid phrase start"
            ),
            "end_seconds": _finite_number(row.get("end_seconds"), "hybrid phrase end"),
            "duration_seconds": _finite_number(
                row.get("duration_seconds"), "hybrid phrase duration"
            ),
        }
        if actual != expected:
            raise ValueError("hybrid and phrase-review geometry disagree")
        result[index] = expected
    if set(result) != set(review_phrases):
        raise ValueError("hybrid phrase geometry does not cover every review unit")
    return result


def _ranked_ranges(
    document: Mapping[str, Any], phrases: Mapping[int, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    expected_counts = {index: 0 for index in phrases}
    pairwise = document.get("pairwise")
    if not isinstance(pairwise, list) or len(pairwise) != 3:
        raise ValueError("hybrid pairwise evidence is incomplete")
    seen_pairs: set[tuple[str, str]] = set()
    for pair in pairwise:
        if not isinstance(pair, Mapping):
            raise ValueError("hybrid pairwise evidence is malformed")
        lanes = (pair.get("left_lane"), pair.get("right_lane"))
        if lanes not in _PAIRWISE_LANES or lanes in seen_pairs:
            raise ValueError("hybrid pairwise lane identities are inconsistent")
        seen_pairs.add(lanes)
        rows = pair.get("per_phrase")
        if not isinstance(rows, list) or len(rows) != len(phrases):
            raise ValueError("hybrid pairwise phrase counts are incomplete")
        seen_indices: set[int] = set()
        for row in rows:
            if not isinstance(row, Mapping):
                raise ValueError("hybrid pairwise phrase count is malformed")
            index = _nonnegative_integer(
                row.get("phrase_index"), "pairwise phrase index"
            )
            if index not in phrases or index in seen_indices:
                raise ValueError("hybrid pairwise phrase index is inconsistent")
            seen_indices.add(index)
            count_fields = (
                "cross_phrase_boundary_matches",
                "same_pitch_boundary_duration_disputes",
                "octave_equivalent_onset_disputes",
                f"{lanes[0]}_only_notes",
                f"{lanes[1]}_only_notes",
            )
            expected_counts[index] += sum(
                _nonnegative_integer(row.get(name), f"pairwise {name}")
                for name in count_fields
            )
    if seen_pairs != _PAIRWISE_LANES:
        raise ValueError("hybrid pairwise lane pairs are incomplete")

    candidates = document.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("hybrid candidate evidence is malformed")
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            raise ValueError("hybrid candidate evidence is malformed")
        lane = str(candidate["lane"])
        duplicate = _mapping(candidate.get("duplicate_evidence"), f"{lane} duplicates")
        groups = duplicate.get("groups")
        if not isinstance(groups, list) or _nonnegative_integer(
            duplicate.get("group_count"), f"{lane} duplicate group count"
        ) != len(groups):
            raise ValueError("hybrid duplicate evidence is inconsistent")
        for group in groups:
            if not isinstance(group, Mapping):
                raise ValueError("hybrid duplicate group is malformed")
            index = group.get("phrase_index")
            if index is not None:
                index = _nonnegative_integer(index, "duplicate phrase index")
                if index not in phrases:
                    raise ValueError("hybrid duplicate refers to an unknown phrase")
                expected_counts[index] += 1

    ranked = document.get("ranked_disagreement_phrases")
    if not isinstance(ranked, list) or len(ranked) != len(phrases):
        raise ValueError("hybrid ranked disagreement rows are incomplete")
    output: list[dict[str, Any]] = []
    for row in ranked:
        if not isinstance(row, Mapping):
            raise ValueError("hybrid ranked disagreement row is malformed")
        index = _nonnegative_integer(row.get("phrase_index"), "ranked phrase index")
        geometry = phrases.get(index)
        if geometry is None or any(
            _finite_number(row.get(name), f"ranked {name}") != geometry[name]
            for name in ("start_seconds", "end_seconds", "duration_seconds")
        ):
            raise ValueError("ranked disagreement geometry is inconsistent")
        component_fields = (
            "cross_phrase_boundary_match_references",
            "same_pitch_boundary_duration_disputes",
            "octave_equivalent_onset_disputes",
            "lane_only_note_references",
            "duplicate_groups",
        )
        component_counts = {
            name: _nonnegative_integer(row.get(name), f"ranked {name}")
            for name in component_fields
        }
        components = sum(component_counts.values())
        total = _nonnegative_integer(
            row.get("disagreement_evidence_count"), "ranked disagreement count"
        )
        if total != components or total != expected_counts[index]:
            raise ValueError("ranked disagreement count is inconsistent")
        output.append(
            {
                **geometry,
                "diagnostic_reference_count": total,
                **component_counts,
            }
        )
    expected_order = sorted(
        output,
        key=lambda row: (-row["diagnostic_reference_count"], row["phrase_index"]),
    )
    if output != expected_order or len({row["phrase_index"] for row in output}) != len(
        output
    ):
        raise ValueError("ranked disagreement order is inconsistent")
    return output


def _phrase_review_files(
    review_path: Path,
    review: Mapping[str, Any],
    phrases: Mapping[int, Mapping[str, Any]],
    *,
    fingerprints: dict[Path, _Fingerprint],
) -> tuple[dict[str, Any], str]:
    root = review_path.parent.resolve()
    artifacts = review.get("artifacts")
    if not isinstance(artifacts, Mapping) or not artifacts:
        raise ValueError("phrase-review manifest has no artifact records")
    verified: dict[str, tuple[Path, dict[str, Any]]] = {}
    for raw_relative, raw_record in artifacts.items():
        relative = _relative_artifact(raw_relative, label="phrase-review artifact")
        if relative in verified:
            raise ValueError("phrase-review artifact paths are not unique")
        record = _mapping(raw_record, f"phrase-review artifact {relative}")
        if record.get("path") != relative:
            raise ValueError("phrase-review artifact record path is inconsistent")
        path = (root / PurePosixPath(relative)).resolve()
        _require_within(path, (root,), label=f"phrase-review artifact {relative}")
        if not path.is_file():
            raise ValueError(f"phrase-review artifact is missing: {relative}")
        fingerprint = _record_fingerprint(path, fingerprints)
        identity = _identity(record, f"phrase-review artifact {relative}")
        if identity != {"sha256": fingerprint.sha256, "bytes": fingerprint.size}:
            raise ValueError(f"phrase-review artifact changed: {relative}")
        verified[relative] = (path, identity)

    entrypoint = _relative_artifact(review.get("html"), label="phrase-review HTML")
    if entrypoint != "melody_phrase_review.html" or not entrypoint.endswith(".html"):
        raise ValueError("phrase-review entrypoint is unsupported")
    exposed: dict[str, str] = {entrypoint: "html"}
    for phrase in phrases.values():
        source = str(phrase["source_audio"])
        _require_suffix(source, ".wav", label="phrase source audio")
        if source not in verified:
            raise ValueError(f"phrase-review artifact is not pinned: {source}")
        exposed[source] = "audio"
        alternatives = phrase["alternatives"]
        assert isinstance(alternatives, Mapping)
        for name, raw_alternative in alternatives.items():
            alternative = _mapping(raw_alternative, f"phrase alternative {name}")
            _nonnegative_integer(
                alternative.get("note_count"), f"phrase alternative {name} note count"
            )
            if (
                not isinstance(alternative.get("label"), str)
                or not alternative["label"]
            ):
                raise ValueError("phrase alternative label is invalid")
            midi = _relative_artifact(
                alternative.get("midi"), label=f"phrase alternative {name} MIDI"
            )
            evaluation = _relative_artifact(
                alternative.get("evaluation"),
                label=f"phrase alternative {name} evaluation",
            )
            audio = _relative_artifact(
                alternative.get("audio"),
                label=f"phrase alternative {name} MIDI-only audio",
            )
            overlay = _relative_artifact(
                alternative.get("overlay_audio"),
                label=f"phrase alternative {name} overlay audio",
            )
            _require_suffix(midi, (".mid", ".midi"), label="phrase alternative MIDI")
            _require_suffix(evaluation, ".json", label="phrase alternative evaluation")
            _require_suffix(audio, ".wav", label="phrase alternative MIDI-only audio")
            _require_suffix(overlay, ".wav", label="phrase alternative overlay audio")
            for relative in (midi, evaluation, audio, overlay):
                if relative not in verified:
                    raise ValueError(
                        f"phrase-review artifact is not pinned: {relative}"
                    )
            exposed[audio] = "audio"
            exposed[overlay] = "audio"
    if entrypoint not in verified:
        raise ValueError("phrase-review HTML is not pinned")
    try:
        html_text = verified[entrypoint][0].read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError("phrase-review HTML is not valid UTF-8") from exc
    for phrase_index in phrases:
        anchor = re.compile(
            rf"\bid\s*=\s*(['\"])phrase-{phrase_index}\1",
            flags=re.IGNORECASE,
        )
        if anchor.search(html_text) is None:
            raise ValueError(f"phrase-review HTML has no phrase-{phrase_index} anchor")
    return (
        {
            relative: {
                "path": str(verified[relative][0]),
                "bytes": verified[relative][1]["bytes"],
                "sha256": verified[relative][1]["sha256"],
                "media_kind": kind,
            }
            for relative, kind in sorted(exposed.items())
        },
        entrypoint,
    )


def _allowed_roots(values: Sequence[str | Path]) -> tuple[Path, ...]:
    if isinstance(values, (str, bytes, Path)) or not values:
        raise ValueError("allowed candidate roots must be a non-empty sequence")
    roots = tuple(Path(value).expanduser().resolve() for value in values)
    if any(not root.is_dir() for root in roots):
        raise ValueError("every allowed candidate root must be a directory")
    return roots


def _explicit_json_file(
    value: str | Path, *, roots: Sequence[Path], label: str
) -> Path:
    path = Path(value).expanduser().resolve()
    _require_within(path, roots, label=label)
    if not path.is_file() or path.suffix.lower() != ".json":
        raise ValueError(f"{label} must be an existing JSON file")
    return path


def _verified_catalog_file(
    raw_record: Any,
    raw_path: Any,
    *,
    label: str,
    fingerprints: dict[Path, _Fingerprint],
    roots: Sequence[Path] | None = None,
) -> dict[str, Any]:
    record = _identity(_mapping(raw_record, label), label)
    if not isinstance(raw_path, (str, Path)) or not str(raw_path):
        raise ValueError(f"{label} path is missing")
    path = Path(raw_path).expanduser().resolve()
    if roots is not None:
        _require_within(path, roots, label=label)
    if not path.is_file():
        raise ValueError(f"{label} does not exist")
    fingerprint = _record_fingerprint(path, fingerprints)
    if record != {"sha256": fingerprint.sha256, "bytes": fingerprint.size}:
        raise ValueError(f"{label} changed after catalog construction")
    return record


def _read_json_document(
    path: Path,
    *,
    label: str,
    fingerprints: dict[Path, _Fingerprint],
) -> tuple[dict[str, Any], dict[str, Any]]:
    fingerprint = _record_fingerprint(path, fingerprints)
    try:
        document = json.loads(
            path.read_bytes(), parse_constant=lambda value: _reject_constant(value)
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid {label} JSON") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{label} JSON must be an object")
    if _fingerprint(path) != fingerprint:
        raise ValueError(f"{label} changed while it was read")
    return document, {"sha256": fingerprint.sha256, "bytes": fingerprint.size}


def _record_fingerprint(
    path: Path, fingerprints: dict[Path, _Fingerprint]
) -> _Fingerprint:
    path = path.resolve()
    fingerprint = _fingerprint(path)
    existing = fingerprints.get(path)
    if existing is not None and existing != fingerprint:
        raise ValueError("phrase-review input changed during verification")
    fingerprints[path] = fingerprint
    return fingerprint


def _fingerprint(path: Path) -> _Fingerprint:
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    after = path.stat()
    before_key = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_key = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_key != after_key:
        raise ValueError("phrase-review input changed while it was hashed")
    return _Fingerprint(*after_key, digest.hexdigest())


def _assert_unchanged(fingerprints: Mapping[Path, _Fingerprint]) -> None:
    for path, expected in fingerprints.items():
        if not path.is_file() or _fingerprint(path) != expected:
            raise ValueError("phrase-review input changed during verification")


def _identity(record: Mapping[str, Any], label: str) -> dict[str, Any]:
    sha256 = record.get("sha256")
    byte_count = record.get("bytes")
    if not isinstance(sha256, str) or not _SHA256.fullmatch(sha256):
        raise ValueError(f"{label} SHA-256 is invalid")
    if (
        isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or byte_count < 0
    ):
        raise ValueError(f"{label} byte count is invalid")
    return {"sha256": sha256, "bytes": byte_count}


def _identity_or_none(value: Any) -> dict[str, Any] | None:
    try:
        return _identity(_mapping(value, "candidate MIDI"), "candidate MIDI")
    except ValueError:
        return None


def _relative_artifact(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError(f"{label} path is invalid")
    if re.match(r"^[A-Za-z]:", value):
        raise ValueError(f"{label} path must be relative")
    parts = value.split("/")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"{label} path escapes its package")
    if pure.as_posix() != value:
        raise ValueError(f"{label} path is not canonical POSIX")
    return value


def _require_within(path: Path, roots: Sequence[Path], *, label: str) -> None:
    if not any(_is_relative_to(path, root) for root in roots):
        raise ValueError(f"{label} escapes the allowed candidate roots")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _require_suffix(value: str, suffix: str | tuple[str, ...], *, label: str) -> None:
    suffixes = (suffix,) if isinstance(suffix, str) else suffix
    if not value.lower().endswith(suffixes):
        raise ValueError(f"{label} has an unsupported file type")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _exact_effects(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != set(_REPORT_EFFECTS):
        return False
    for name, expected in _REPORT_EFFECTS.items():
        actual = value.get(name)
        if isinstance(expected, bool):
            if actual is not expected:
                return False
        elif (
            isinstance(actual, bool)
            or not isinstance(actual, int)
            or actual != expected
        ):
            return False
    return True


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} is invalid")
    return value


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result


def _positive_number(value: Any, label: str) -> float:
    result = _finite_number(value, label)
    if result <= 0:
        raise ValueError(f"{label} must be positive")
    return result


def _nonnegative_number(value: Any, label: str) -> float:
    result = _finite_number(value, label)
    if result < 0:
        raise ValueError(f"{label} must be non-negative")
    return result


def _nonnegative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _positive_integer(value: Any, label: str) -> int:
    result = _nonnegative_integer(value, label)
    if result == 0:
        raise ValueError(f"{label} must be positive")
    return result


def _round9(value: Any) -> float:
    return round(float(value), 9)


def _document_hash(document: Mapping[str, Any]) -> str:
    payload = json.dumps(
        document, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


__all__ = [
    "WORKBENCH_PHRASE_REVIEW_LINK_SCHEMA",
    "build_workbench_phrase_review_link",
]
