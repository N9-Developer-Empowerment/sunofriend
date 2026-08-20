"""Versioned, audio-native Musical State foundation.

This module implements the first deliberately small slice of the semantic
Musical State programme.  It admits exact local vocal evidence, canonical
lyrics and a reviewed phrase timeline without requiring MIDI, running a
model, selecting a take, rendering a comp or creating a training label.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Mapping, Sequence

from .audio_formats import file_sha256
from .source_project import RIGHTS_CATEGORIES
from .source_receipt import canonical_json_bytes, document_sha256


MUSICAL_STATE_SCHEMA = "sunofriend.musical-state.v0"
VOCAL_PERFORMANCE_STATE_SCHEMA = "sunofriend.vocal-performance-state.v2"
VOCAL_PERFORMANCE_STATE_SCHEMA_V3 = "sunofriend.vocal-performance-state.v3"
VOCAL_COMP_TIMELINE_SCHEMA = "sunofriend.vocal-comp-timeline.v1"

METHOD_NATURES = frozenset({"D", "I", "T", "H"})

_AUDIO_SUFFIXES = frozenset({".wav"})
_PHRASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_MAX_TAKES = 24
_MAX_PHRASE_CAPTURES = 2048
_MAX_CAPTURES_PER_PHRASE = 16
_MAX_PHRASES = 128
_MAX_LYRICS_BYTES = 256 * 1024
_MAX_TIMELINE_BYTES = 512 * 1024
_MIN_PHRASE_SECONDS = 0.10
_MAX_PHRASE_SECONDS = 30.0


def plan_vocal_musical_state(
    take_dir: str | Path,
    *,
    lyrics: str | Path,
    phrase_timeline: str | Path,
    rights_category: str,
    processing_chain: str,
    reference_vocal: str | Path | None = None,
    bpm: float | None = None,
    tuning_hz: float = 440.0,
    confirm_common_recorded_zero: bool = False,
    confirm_timeline_reviewed: bool = False,
) -> dict[str, Any]:
    """Validate an audio-native state import without writing anything."""

    source_dir = _directory(take_dir, "take directory")
    take_paths = sorted(
        (
            path
            for path in source_dir.iterdir()
            if path.is_file() and path.suffix.casefold() in _AUDIO_SUFFIXES
        ),
        key=lambda path: path.name.casefold(),
    )
    if not 2 <= len(take_paths) <= _MAX_TAKES:
        raise ValueError("musical state requires 2-24 top-level WAV takes")
    if any(path.is_symlink() for path in take_paths):
        raise ValueError("vocal takes may not be symbolic links")
    inodes = {(path.stat().st_dev, path.stat().st_ino) for path in take_paths}
    if len(inodes) != len(take_paths):
        raise ValueError("duplicate or hard-linked vocal takes are not allowed")

    lyrics_path = _file(lyrics, "lyrics")
    timeline_path = _file(phrase_timeline, "phrase timeline")
    reference_path = (
        _file(reference_vocal, "reference vocal") if reference_vocal else None
    )
    if not confirm_common_recorded_zero:
        raise ValueError("confirm_common_recorded_zero is required")
    if not confirm_timeline_reviewed:
        raise ValueError("confirm_timeline_reviewed is required")
    if rights_category not in RIGHTS_CATEGORIES:
        raise ValueError(
            "rights_category must be one of: " + ", ".join(sorted(RIGHTS_CATEGORIES))
        )
    normalized_chain = str(processing_chain).strip().casefold().replace("-", "_")
    if normalized_chain not in {"dry", "same_gentle_chain"}:
        raise ValueError("processing_chain must be dry or same-gentle-chain")
    if bpm is not None and (not math.isfinite(float(bpm)) or float(bpm) <= 0):
        raise ValueError("bpm must be finite and positive when supplied")
    if not math.isfinite(float(tuning_hz)) or float(tuning_hz) <= 0:
        raise ValueError("tuning_hz must be finite and positive")

    lyrics_bytes = lyrics_path.read_bytes()
    if not lyrics_bytes or len(lyrics_bytes) > _MAX_LYRICS_BYTES:
        raise ValueError("lyrics must be non-empty and no larger than 256 KiB")
    try:
        canonical_lyrics = lyrics_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("lyrics must be UTF-8 text") from exc
    if not canonical_lyrics.strip():
        raise ValueError("lyrics must contain non-whitespace text")

    timeline = _load_reviewed_timeline(timeline_path, canonical_lyrics)
    take_records = [
        {
            "source_name": path.name,
            "source": _absolute_file_record(path),
            "audio": _audio_record(path),
        }
        for path in take_paths
    ]
    final_phrase_end = float(timeline["phrases"][-1]["end_seconds"])
    if (
        final_phrase_end
        > min(float(row["audio"]["duration_seconds"]) for row in take_records) + 1e-6
    ):
        raise ValueError("phrase timeline extends beyond a supplied vocal take")
    reference_audio = _audio_record(reference_path) if reference_path else None
    if (
        reference_audio
        and reference_audio["duration_seconds"] + 1e-6 < final_phrase_end
    ):
        raise ValueError("reference vocal ends before the reviewed phrase timeline")

    return {
        "schema": MUSICAL_STATE_SCHEMA,
        "operation": "plan",
        "status": "ready_no_midi_required",
        "source_directory": str(source_dir),
        "take_count": len(take_records),
        "takes": take_records,
        "lyrics": _absolute_file_record(lyrics_path),
        "phrase_timeline": {
            **_absolute_file_record(timeline_path),
            "phrase_count": len(timeline["phrases"]),
            "review_status": "reviewed",
        },
        "reference_vocal": (
            {**_absolute_file_record(reference_path), "audio": reference_audio}
            if reference_path
            else None
        ),
        "clock": {
            "origin": "common_recorded_song_zero",
            "bpm": float(bpm) if bpm is not None else None,
            "tuning_hz": float(tuning_hz),
        },
        "rights_category": rights_category,
        "processing_chain": normalized_chain,
        "method_natures": ["D", "H"],
        "midi_required": False,
        "network_used": False,
        "effects": _zero_effects(),
    }


def create_vocal_musical_state(
    take_dir: str | Path,
    *,
    out_dir: str | Path,
    lyrics: str | Path,
    phrase_timeline: str | Path,
    rights_category: str,
    processing_chain: str,
    reference_vocal: str | Path | None = None,
    bpm: float | None = None,
    tuning_hz: float = 440.0,
    confirm_common_recorded_zero: bool = False,
    confirm_timeline_reviewed: bool = False,
) -> dict[str, Any]:
    """Copy exact evidence into one fresh owner-only Musical State project."""

    plan = plan_vocal_musical_state(
        take_dir,
        lyrics=lyrics,
        phrase_timeline=phrase_timeline,
        rights_category=rights_category,
        processing_chain=processing_chain,
        reference_vocal=reference_vocal,
        bpm=bpm,
        tuning_hz=tuning_hz,
        confirm_common_recorded_zero=confirm_common_recorded_zero,
        confirm_timeline_reviewed=confirm_timeline_reviewed,
    )
    destination = Path(out_dir).expanduser().absolute()
    if destination.exists():
        raise ValueError(f"musical-state output already exists: {destination}")
    source_dir = Path(plan["source_directory"])
    if destination == source_dir or source_dir in destination.parents:
        raise ValueError("musical-state output must be outside the take directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent)
    )
    os.chmod(temporary, 0o700)
    try:
        takes_dir = temporary / "SOURCES" / "takes"
        reference_dir = temporary / "SOURCES" / "reference"
        lyrics_dir = temporary / "LYRICS"
        timeline_dir = temporary / "TIMELINE"
        for directory in (takes_dir, reference_dir, lyrics_dir, timeline_dir):
            directory.mkdir(parents=True, exist_ok=True)
            os.chmod(directory, 0o700)

        takes: list[dict[str, Any]] = []
        for index, row in enumerate(plan["takes"], 1):
            source = source_dir / row["source_name"]
            take_id = f"take-{index:03d}"
            copied = takes_dir / f"{take_id}.wav"
            _copy_private(source, copied)
            _verify_copy(copied, row["source"], row["source_name"])
            takes.append(
                {
                    "source_id": take_id,
                    "source_class": "human_vocal_take",
                    "label": row["source_name"],
                    "audio": _relative_file_record(copied, temporary),
                    "audio_properties": row["audio"],
                    "recorded_zero_offset_seconds": 0.0,
                    "review_status": "not_reviewed_in_this_state",
                }
            )

        copied_lyrics = lyrics_dir / "lyrics.txt"
        copied_timeline = timeline_dir / "reviewed-phrase-timeline.json"
        _copy_private(Path(lyrics).expanduser().absolute(), copied_lyrics)
        _copy_private(Path(phrase_timeline).expanduser().absolute(), copied_timeline)
        _verify_copy(copied_lyrics, plan["lyrics"], "lyrics")
        _verify_copy(copied_timeline, plan["phrase_timeline"], "phrase timeline")

        reference: dict[str, Any] | None = None
        if reference_vocal is not None:
            copied_reference = reference_dir / "reference-vocal.wav"
            _copy_private(
                Path(reference_vocal).expanduser().absolute(), copied_reference
            )
            _verify_copy(copied_reference, plan["reference_vocal"], "reference vocal")
            reference = {
                "source_id": "reference-vocal-001",
                "source_class": "reference_vocal",
                "audio": _relative_file_record(copied_reference, temporary),
                "audio_properties": plan["reference_vocal"]["audio"],
                "recorded_zero_offset_seconds": 0.0,
                "authority": "phrasing_and_contour_reference_only",
            }

        timeline_document = json.loads(copied_timeline.read_text(encoding="utf-8"))
        manifest: dict[str, Any] = {
            "schema": MUSICAL_STATE_SCHEMA,
            "status": "complete_unreviewed_no_selection",
            "state_scope": "audio_native_vocal_foundation",
            "method_natures": ["D", "H"],
            "clock": plan["clock"],
            "authorization": {
                "rights_category": plan["rights_category"],
                "rights_confirmed": True,
                "common_recorded_zero_confirmed": True,
            },
            "lyrics": {
                "canonical": _relative_file_record(copied_lyrics, temporary),
                "authority": "user_supplied_canonical",
                "automatic_rewrite_permitted": False,
            },
            "structure": {
                "phrase_timeline": _relative_file_record(copied_timeline, temporary),
                "phrase_timeline_schema": VOCAL_COMP_TIMELINE_SCHEMA,
                "review_status": "reviewed",
                "phrases": [
                    {
                        "phrase_id": row["phrase_id"],
                        "start_seconds": float(row["start_seconds"]),
                        "end_seconds": float(row["end_seconds"]),
                        "lyrics": row["lyrics"],
                    }
                    for row in timeline_document["phrases"]
                ],
            },
            "vocal_performance_state": {
                "schema": VOCAL_PERFORMANCE_STATE_SCHEMA,
                "processing_chain": plan["processing_chain"],
                "reference": reference,
                "takes": takes,
                "continuous_f0_evidence": [],
                "lyric_phoneme_evidence": [],
                "non_pitched_event_evidence": [],
                "signal_quality_evidence": [],
                "explicit_phrase_decisions": [],
                "edit_maps": [],
                "correction_derivatives": [],
                "selection_authority": "human_only",
            },
            "optional_derived_evidence": {
                "midi": [],
                "notes": [],
            },
            "training": {
                "explicit_labels": [],
                "training_eligible": False,
                "reason": "no explicit phrase comparison decision in this state",
            },
            "network_used": False,
            "effects": _zero_effects(),
        }
        manifest["document_sha256"] = document_sha256(manifest)
        manifest_path = temporary / "musical-state.json"
        _write_private_json(manifest_path, manifest)
        validate_musical_state(manifest_path, root=temporary)
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return validate_musical_state(destination / "musical-state.json", root=destination)


def admit_vocal_phrase_capture(
    base_manifest: str | Path,
    *,
    capture_wav: str | Path,
    capture_receipt: str | Path | Mapping[str, Any],
    out_dir: str | Path,
    label: str | None = None,
) -> dict[str, Any]:
    """Admit one bounded capture into a fresh immutable derived state.

    The parent state, its exact referenced artifacts, the capture receipt and
    microphone WAV are copied into a new owner-only project.  No existing
    state is changed and no phrase decision is migrated or created.
    """

    from .vocal_capture import VOCAL_CAPTURE_SCHEMA, validate_vocal_capture

    parent_path = _file(base_manifest, "base musical-state manifest")
    parent_root = parent_path.parent.resolve()
    parent = validate_musical_state(parent_path, root=parent_root)
    receipt_source: Path | None = None
    if isinstance(capture_receipt, Mapping):
        receipt_input = dict(capture_receipt)
    else:
        receipt_source = _file(capture_receipt, "vocal capture receipt")
        receipt_input = _read_json(receipt_source)
    receipt = validate_vocal_capture(receipt_input, parent)
    source_audio = _file(capture_wav, "vocal phrase capture")
    if source_audio.stat().st_size != receipt["audio"]["bytes"]:
        raise ValueError("vocal phrase capture byte count does not match receipt")
    if file_sha256(source_audio) != receipt["audio"]["sha256"]:
        raise ValueError("vocal phrase capture SHA-256 does not match receipt")
    properties = _audio_record(source_audio)
    expected_audio = receipt["audio"]
    if {
        "format": properties["format"],
        "subtype": properties["subtype"],
        "sample_rate": properties["sample_rate"],
        "channels": properties["channels"],
        "frames": properties["frames"],
    } != {
        "format": expected_audio["format"],
        "subtype": expected_audio["subtype"],
        "sample_rate": expected_audio["sample_rate"],
        "channels": expected_audio["channels"],
        "frames": expected_audio["frames"],
    }:
        raise ValueError("vocal phrase capture audio geometry does not match receipt")

    source_id = receipt["capture"]["source_id"]
    existing_ids = _vocal_source_ids(parent)
    if source_id in existing_ids:
        raise ValueError("vocal phrase capture source_id already exists")
    phrase_id = receipt["phrase"]["phrase_id"]
    prior_captures = list(parent["vocal_performance_state"].get("phrase_captures", []))
    if (
        sum(
            row.get("phrase", {}).get("phrase_id") == phrase_id
            for row in prior_captures
        )
        >= _MAX_CAPTURES_PER_PHRASE
    ):
        raise ValueError("vocal phrase capture limit reached for this phrase")
    if len(prior_captures) >= _MAX_PHRASE_CAPTURES:
        raise ValueError("vocal phrase capture limit reached for this state")

    capture_label = _capture_label(label, source_id)
    destination = Path(out_dir).expanduser().absolute()
    if destination.exists():
        raise ValueError(f"musical-state output already exists: {destination}")
    if destination == parent_root or parent_root in destination.parents:
        raise ValueError(
            "derived musical-state output must be outside the parent state"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent)
    )
    os.chmod(temporary, 0o700)
    try:
        _copy_manifest_artifacts(parent, parent_root, temporary)

        parent_copy = (
            temporary / "LINEAGE" / f"musical-state-{parent['document_sha256']}.json"
        )
        _private_parent(parent_copy, temporary)
        _copy_private(parent_path, parent_copy)
        _verify_copy(
            parent_copy,
            _absolute_file_record(parent_path),
            "parent musical-state manifest",
        )

        receipt_copy = (
            temporary / "RECEIPTS" / f"vocal-capture-{receipt['document_sha256']}.json"
        )
        _private_parent(receipt_copy, temporary)
        if receipt_source is None:
            _write_private_json(receipt_copy, receipt)
        else:
            _copy_private(receipt_source, receipt_copy)
            _verify_copy(
                receipt_copy,
                _absolute_file_record(receipt_source),
                "vocal capture receipt",
            )

        audio_copy = (
            temporary
            / "SOURCES"
            / "phrase-captures"
            / f"{source_id}-{receipt['audio']['sha256'][:12]}.wav"
        )
        _private_parent(audio_copy, temporary)
        _copy_private(source_audio, audio_copy)
        _verify_copy(
            audio_copy,
            _absolute_file_record(source_audio),
            "vocal phrase capture",
        )

        capture_row = {
            "source_id": source_id,
            "source_class": "human_vocal_phrase_capture",
            "label": capture_label,
            "audio": _relative_file_record(audio_copy, temporary),
            "audio_properties": properties,
            "capture_receipt": {
                "schema": VOCAL_CAPTURE_SCHEMA,
                "document_sha256": receipt["document_sha256"],
                "artifact": _relative_file_record(receipt_copy, temporary),
            },
            "phrase": dict(receipt["phrase"]),
            "placement": dict(receipt["placement"]),
            "review_status": "stored_unreviewed",
            "authority": dict(receipt["authority"]),
        }
        derived = json.loads(canonical_json_bytes(parent).decode("utf-8"))
        derived.pop("document_sha256", None)
        derived.pop("lineage", None)
        vocal = derived["vocal_performance_state"]
        vocal["schema"] = VOCAL_PERFORMANCE_STATE_SCHEMA_V3
        vocal["phrase_captures"] = [*prior_captures, capture_row]
        derived["lineage"] = {
            "operation": "admit_vocal_phrase_capture",
            "parent": {
                "schema": MUSICAL_STATE_SCHEMA,
                "document_sha256": parent["document_sha256"],
                "manifest": _relative_file_record(parent_copy, temporary),
            },
            "admitted_capture": {
                "schema": VOCAL_CAPTURE_SCHEMA,
                "document_sha256": receipt["document_sha256"],
                "audio_sha256": receipt["audio"]["sha256"],
            },
        }
        derived["document_sha256"] = document_sha256(derived)
        manifest_path = temporary / "musical-state.json"
        _write_private_json(manifest_path, derived)
        validate_musical_state(manifest_path, root=temporary)
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return validate_musical_state(destination / "musical-state.json", root=destination)


def validate_musical_state(
    manifest: str | Path | Mapping[str, Any],
    *,
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Validate the v0 contract and its project-local file identities."""

    if isinstance(manifest, Mapping):
        document = dict(manifest)
        manifest_path = None
    else:
        manifest_path = Path(manifest).expanduser().absolute()
        document = _read_json(manifest_path)
    if document.get("schema") != MUSICAL_STATE_SCHEMA:
        raise ValueError("unsupported musical-state schema")
    if document.get("status") != "complete_unreviewed_no_selection":
        raise ValueError("musical-state v0 must remain complete and unreviewed")
    expected = str(document.get("document_sha256", ""))
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if expected != document_sha256(unsigned):
        raise ValueError("musical-state document SHA-256 does not match")
    if document.get("method_natures") != ["D", "H"]:
        raise ValueError("v0 musical state must declare deterministic and human work")
    vocal = _mapping(document.get("vocal_performance_state"), "vocal state")
    vocal_schema = vocal.get("schema")
    if vocal_schema not in {
        VOCAL_PERFORMANCE_STATE_SCHEMA,
        VOCAL_PERFORMANCE_STATE_SCHEMA_V3,
    }:
        raise ValueError("unsupported vocal-performance-state schema")
    if vocal_schema == VOCAL_PERFORMANCE_STATE_SCHEMA:
        if "phrase_captures" in vocal or "lineage" in document:
            raise ValueError(
                "vocal-performance-state v2 cannot contain phrase captures"
            )
    else:
        _validate_phrase_capture_state(document, vocal)
    if vocal.get("selection_authority") != "human_only":
        raise ValueError("vocal selection authority must remain human_only")
    for key in (
        "continuous_f0_evidence",
        "lyric_phoneme_evidence",
        "non_pitched_event_evidence",
        "signal_quality_evidence",
        "explicit_phrase_decisions",
        "edit_maps",
        "correction_derivatives",
    ):
        if vocal.get(key) != []:
            if key == "explicit_phrase_decisions":
                raise ValueError(
                    "unreviewed musical state cannot contain an explicit phrase decision"
                )
            raise ValueError(f"unreviewed musical state cannot contain {key}")
    if document.get("network_used") is not False:
        raise ValueError("musical-state v0 must record network_used=false")
    if any(document.get("effects", {}).values()):
        raise ValueError("musical-state v0 cannot record a product effect")
    optional = _mapping(document.get("optional_derived_evidence"), "optional evidence")
    if optional.get("midi") != [] or optional.get("notes") != []:
        raise ValueError("musical-state v0 foundation must not require note evidence")
    training = _mapping(document.get("training"), "training")
    if training.get("training_eligible") is not False:
        raise ValueError("an unreviewed v0 state cannot be training eligible")

    _reject_absolute_paths(document)
    base = (
        Path(root).expanduser().absolute().resolve()
        if root is not None
        else manifest_path.parent.resolve()
        if manifest_path
        else None
    )
    if base is not None:
        for record in _file_records(document):
            relative = _safe_relative_path(record.get("path"))
            path = (base / Path(*relative.parts)).resolve()
            try:
                path.relative_to(base)
            except ValueError as exc:
                raise ValueError("musical-state artifact escapes project root") from exc
            if not path.is_file() or path.is_symlink():
                raise ValueError(
                    f"musical-state artifact is missing or unsafe: {relative}"
                )
            if path.stat().st_size != record.get("bytes"):
                raise ValueError(f"musical-state artifact size changed: {relative}")
            if file_sha256(path) != record.get("sha256"):
                raise ValueError(f"musical-state artifact hash changed: {relative}")
        if vocal_schema == VOCAL_PERFORMANCE_STATE_SCHEMA_V3:
            _validate_phrase_capture_lineage(document, base)
    return document


def _validate_phrase_capture_state(
    document: Mapping[str, Any], vocal: Mapping[str, Any]
) -> None:
    captures = vocal.get("phrase_captures")
    if not isinstance(captures, list) or not 1 <= len(captures) <= _MAX_PHRASE_CAPTURES:
        raise ValueError("vocal-performance-state v3 requires bounded phrase captures")
    phrases = {
        row["phrase_id"]: row
        for row in _mapping(document.get("structure"), "structure").get("phrases", [])
    }
    source_ids = {
        row.get("source_id")
        for row in vocal.get("takes", [])
        if isinstance(row, Mapping)
    }
    reference = vocal.get("reference")
    if isinstance(reference, Mapping):
        source_ids.add(reference.get("source_id"))
    counts: dict[str, int] = {}
    for capture in captures:
        row = _mapping(capture, "phrase capture")
        if set(row) != {
            "source_id",
            "source_class",
            "label",
            "audio",
            "audio_properties",
            "capture_receipt",
            "phrase",
            "placement",
            "review_status",
            "authority",
        }:
            raise ValueError("phrase capture fields changed")
        source_id = str(row.get("source_id", ""))
        if not _PHRASE_ID.fullmatch(source_id) or source_id in source_ids:
            raise ValueError(
                "phrase capture source IDs must be unique safe identifiers"
            )
        source_ids.add(source_id)
        if row.get("source_class") != "human_vocal_phrase_capture":
            raise ValueError("phrase capture source class changed")
        _capture_label(row.get("label"), source_id)
        audio = _mapping(row.get("audio"), "phrase capture audio")
        if set(audio) != {"path", "bytes", "sha256"}:
            raise ValueError("phrase capture audio file record changed")
        _safe_relative_path(audio.get("path"))
        properties = _mapping(row.get("audio_properties"), "phrase capture audio")
        if set(properties) != {
            "format",
            "subtype",
            "sample_rate",
            "channels",
            "frames",
            "duration_seconds",
        }:
            raise ValueError("phrase capture audio properties changed")
        if (
            properties.get("format") != "WAV"
            or properties.get("subtype") != "PCM_24"
            or properties.get("channels") != 1
        ):
            raise ValueError("phrase capture audio must remain mono WAV PCM_24")
        sample_rate = _positive_int(properties.get("sample_rate"), "sample rate")
        frames = _positive_int(properties.get("frames"), "frame count")
        duration = _finite_number(properties.get("duration_seconds"), "duration")
        if abs(duration - frames / sample_rate) > 1e-9:
            raise ValueError("phrase capture duration does not match its frame clock")
        if audio.get("bytes") != 44 + frames * 3:
            raise ValueError("phrase capture byte count does not match PCM24 geometry")
        _sha256_text(audio.get("sha256"), "phrase capture audio")

        receipt = _mapping(row.get("capture_receipt"), "capture receipt")
        if set(receipt) != {"schema", "document_sha256", "artifact"}:
            raise ValueError("phrase capture receipt fields changed")
        if receipt.get("schema") != "sunofriend.browser-vocal-capture.v1":
            raise ValueError("phrase capture receipt schema changed")
        _sha256_text(receipt.get("document_sha256"), "capture receipt")
        receipt_artifact = _mapping(receipt.get("artifact"), "capture receipt artifact")
        if set(receipt_artifact) != {"path", "bytes", "sha256"}:
            raise ValueError("capture receipt artifact record changed")
        _safe_relative_path(receipt_artifact.get("path"))

        phrase_row = _mapping(row.get("phrase"), "capture phrase")
        phrase_id = str(phrase_row.get("phrase_id", ""))
        phrase = phrases.get(phrase_id)
        if phrase is None or phrase_row != {
            "phrase_id": phrase_id,
            "lyrics": phrase["lyrics"],
            "review_status": "reviewed",
        }:
            raise ValueError("phrase capture does not bind a reviewed phrase")
        counts[phrase_id] = counts.get(phrase_id, 0) + 1
        if counts[phrase_id] > _MAX_CAPTURES_PER_PHRASE:
            raise ValueError("too many phrase captures for one phrase")

        placement = _mapping(row.get("placement"), "capture placement")
        expected_placement_keys = {
            "source_phrase_start_frame",
            "source_phrase_end_frame",
            "pre_guard_frames",
            "post_guard_frames",
            "destination_start_seconds",
            "destination_end_seconds",
            "destination_start_frame",
            "destination_end_frame",
            "capture_song_start_seconds",
        }
        if set(placement) != expected_placement_keys:
            raise ValueError("phrase capture placement fields changed")
        start = _non_negative_int(
            placement.get("source_phrase_start_frame"), "source phrase start"
        )
        end = _positive_int(
            placement.get("source_phrase_end_frame"), "source phrase end"
        )
        before = _non_negative_int(
            placement.get("pre_guard_frames"), "pre guard frames"
        )
        after = _non_negative_int(
            placement.get("post_guard_frames"), "post guard frames"
        )
        if not 0 <= start < end <= frames or before != start or after != frames - end:
            raise ValueError("phrase capture source window or guards changed")
        if before + after <= 0 or before > sample_rate * 5 or after > sample_rate * 5:
            raise ValueError("phrase capture guards must remain short and bounded")
        destination_start = _finite_number(
            placement.get("destination_start_seconds"), "destination start"
        )
        destination_end = _finite_number(
            placement.get("destination_end_seconds"), "destination end"
        )
        tolerance = 0.5 / sample_rate + 1e-12
        if (
            abs(destination_start - float(phrase["start_seconds"])) > tolerance
            or abs(destination_end - float(phrase["end_seconds"])) > tolerance
            or abs((end - start) / sample_rate - (destination_end - destination_start))
            > tolerance
        ):
            raise ValueError("phrase capture destination no longer matches phrase")
        if placement.get("destination_start_frame") != round(
            destination_start * sample_rate
        ) or placement.get("destination_end_frame") != round(
            destination_end * sample_rate
        ):
            raise ValueError("phrase capture destination frame clock changed")
        capture_start = _finite_number(
            placement.get("capture_song_start_seconds"), "capture song start"
        )
        if abs(capture_start - (destination_start - start / sample_rate)) > tolerance:
            raise ValueError("phrase capture song placement changed")
        if row.get("review_status") != "stored_unreviewed" or row.get("authority") != {
            "review_status": "unreviewed",
            "selection_authority": "none",
            "phrase_decision_created": False,
            "source_map_admission": False,
        }:
            raise ValueError("phrase capture cannot claim selection authority")

    lineage = _mapping(document.get("lineage"), "phrase capture lineage")
    if set(lineage) != {"operation", "parent", "admitted_capture"}:
        raise ValueError("phrase capture lineage fields changed")
    if lineage.get("operation") != "admit_vocal_phrase_capture":
        raise ValueError("phrase capture lineage operation changed")
    parent = _mapping(lineage.get("parent"), "parent lineage")
    if set(parent) != {"schema", "document_sha256", "manifest"}:
        raise ValueError("parent lineage fields changed")
    if parent.get("schema") != MUSICAL_STATE_SCHEMA:
        raise ValueError("parent lineage schema changed")
    _sha256_text(parent.get("document_sha256"), "parent musical state")
    parent_manifest = _mapping(parent.get("manifest"), "parent manifest")
    if set(parent_manifest) != {"path", "bytes", "sha256"}:
        raise ValueError("parent manifest artifact record changed")
    admitted = _mapping(lineage.get("admitted_capture"), "admitted capture")
    if set(admitted) != {"schema", "document_sha256", "audio_sha256"}:
        raise ValueError("admitted capture lineage fields changed")
    if admitted.get("schema") != "sunofriend.browser-vocal-capture.v1":
        raise ValueError("admitted capture schema changed")
    _sha256_text(admitted.get("document_sha256"), "admitted capture")
    _sha256_text(admitted.get("audio_sha256"), "admitted capture audio")


def _validate_phrase_capture_lineage(document: Mapping[str, Any], base: Path) -> None:
    from .vocal_capture import validate_vocal_capture

    lineage = document["lineage"]
    parent_record = lineage["parent"]["manifest"]
    parent_path = _record_path(base, parent_record)
    parent = validate_musical_state(parent_path, root=base)
    if parent["document_sha256"] != lineage["parent"]["document_sha256"]:
        raise ValueError("parent musical-state lineage hash changed")

    current_vocal = document["vocal_performance_state"]
    parent_vocal = parent["vocal_performance_state"]
    for key in current_vocal:
        if key in {"schema", "phrase_captures"}:
            continue
        if current_vocal[key] != parent_vocal.get(key):
            raise ValueError("capture admission changed existing vocal evidence")
    if any(
        document.get(key) != parent.get(key)
        for key in (
            "schema",
            "status",
            "state_scope",
            "method_natures",
            "clock",
            "authorization",
            "lyrics",
            "structure",
            "optional_derived_evidence",
            "training",
            "network_used",
            "effects",
        )
    ):
        raise ValueError("capture admission changed parent musical-state evidence")
    parent_captures = list(parent_vocal.get("phrase_captures", []))
    current_captures = current_vocal["phrase_captures"]
    if current_captures[:-1] != parent_captures:
        raise ValueError("capture admission changed or reordered prior captures")
    admitted_row = current_captures[-1]
    admitted = lineage["admitted_capture"]
    if (
        admitted_row["capture_receipt"]["document_sha256"]
        != admitted["document_sha256"]
        or admitted_row["audio"]["sha256"] != admitted["audio_sha256"]
    ):
        raise ValueError("admitted capture lineage does not match capture roster")
    receipt_path = _record_path(base, admitted_row["capture_receipt"]["artifact"])
    receipt = _read_json(receipt_path)
    validate_vocal_capture(receipt, parent)
    if receipt["document_sha256"] != admitted["document_sha256"]:
        raise ValueError("capture receipt lineage hash changed")
    if receipt["capture"]["source_id"] != admitted_row["source_id"]:
        raise ValueError("capture receipt source identity changed")
    if receipt["audio"]["sha256"] != admitted_row["audio"]["sha256"]:
        raise ValueError("capture receipt audio identity changed")
    if admitted_row["phrase"] != receipt["phrase"]:
        raise ValueError("capture receipt phrase binding changed")
    if admitted_row["placement"] != receipt["placement"]:
        raise ValueError("capture receipt placement changed")
    if admitted_row["authority"] != receipt["authority"]:
        raise ValueError("capture receipt authority changed")


def _load_reviewed_timeline(path: Path, canonical_lyrics: str) -> dict[str, Any]:
    if path.stat().st_size > _MAX_TIMELINE_BYTES:
        raise ValueError("phrase timeline must be no larger than 512 KiB")
    timeline = _read_json(path)
    if timeline.get("schema") != VOCAL_COMP_TIMELINE_SCHEMA:
        raise ValueError(f"phrase timeline schema must be {VOCAL_COMP_TIMELINE_SCHEMA}")
    if timeline.get("status") != "reviewed":
        raise ValueError("phrase timeline must have status reviewed")
    raw = timeline.get("phrases")
    if not isinstance(raw, list) or not 1 <= len(raw) <= _MAX_PHRASES:
        raise ValueError("phrase timeline requires 1-128 phrase rows")
    ids: set[str] = set()
    previous_end = 0.0
    canonical_words = _words(canonical_lyrics)
    lyric_position = 0
    for index, row in enumerate(raw):
        if not isinstance(row, Mapping):
            raise ValueError("each phrase row must be an object")
        phrase_id = str(row.get("phrase_id", ""))
        if not _PHRASE_ID.fullmatch(phrase_id) or phrase_id in ids:
            raise ValueError("phrase IDs must be unique safe identifiers")
        start = float(row.get("start_seconds", -1.0))
        end = float(row.get("end_seconds", -1.0))
        if not math.isfinite(start) or not math.isfinite(end) or start < 0:
            raise ValueError(f"phrase {phrase_id} has invalid bounds")
        if not _MIN_PHRASE_SECONDS <= end - start <= _MAX_PHRASE_SECONDS:
            raise ValueError(f"phrase {phrase_id} duration must be 0.1-30 seconds")
        if index and start < previous_end - 1e-9:
            raise ValueError("phrase rows must be chronological and non-overlapping")
        lyric_text = str(row.get("lyrics", "")).strip()
        phrase_words = _words(lyric_text)
        found = _find_words(canonical_words, phrase_words, lyric_position)
        if not phrase_words or found is None:
            raise ValueError(
                f"phrase {phrase_id} lyrics are not in canonical lyric order"
            )
        lyric_position = found + len(phrase_words)
        ids.add(phrase_id)
        previous_end = end
    return timeline


def _audio_record(path: Path) -> dict[str, Any]:
    import soundfile

    info = soundfile.info(path)
    if info.format != "WAV":
        raise ValueError(f"vocal source must be a WAV file: {path.name}")
    if info.frames <= 0 or info.samplerate <= 0 or not 1 <= info.channels <= 2:
        raise ValueError(f"vocal source has unsupported audio geometry: {path.name}")
    return {
        "format": info.format,
        "subtype": info.subtype,
        "sample_rate": int(info.samplerate),
        "channels": int(info.channels),
        "frames": int(info.frames),
        "duration_seconds": round(info.frames / info.samplerate, 9),
    }


def _zero_effects() -> dict[str, bool]:
    return {
        "source_mutated": False,
        "lyrics_mutated": False,
        "selection_created": False,
        "human_decision_created": False,
        "audio_comp_rendered": False,
        "pitch_correction_applied": False,
        "training_started": False,
        "model_weights_changed": False,
        "remix_rendered": False,
    }


def _copy_private(source: Path, destination: Path) -> None:
    shutil.copyfile(source, destination)
    os.chmod(destination, 0o600)


def _copy_manifest_artifacts(
    manifest: Mapping[str, Any], source_root: Path, destination_root: Path
) -> None:
    seen: set[PurePosixPath] = set()
    for record in _file_records(manifest):
        relative = _safe_relative_path(record.get("path"))
        if relative in seen:
            continue
        seen.add(relative)
        source = (source_root / Path(*relative.parts)).resolve()
        try:
            source.relative_to(source_root)
        except ValueError as exc:
            raise ValueError("parent musical-state artifact escapes its root") from exc
        if not source.is_file() or source.is_symlink():
            raise ValueError("parent musical-state artifact is missing or unsafe")
        destination = destination_root / Path(*relative.parts)
        _private_parent(destination, destination_root)
        _copy_private(source, destination)
        _verify_copy(destination, record, str(relative))


def _private_parent(path: Path, root: Path) -> None:
    relative_parent = path.parent.relative_to(root)
    current = root
    for part in relative_parent.parts:
        current = current / part
        current.mkdir(exist_ok=True)
        os.chmod(current, 0o700)


def _verify_copy(copied: Path, source_record: Mapping[str, Any], label: str) -> None:
    if copied.stat().st_size != source_record.get("bytes"):
        raise ValueError(f"{label} changed during import")
    if file_sha256(copied) != source_record.get("sha256"):
        raise ValueError(f"{label} changed during import")


def _record_path(base: Path, record: Mapping[str, Any]) -> Path:
    relative = _safe_relative_path(record.get("path"))
    path = (base / Path(*relative.parts)).resolve()
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise ValueError("musical-state artifact escapes project root") from exc
    return path


def _absolute_file_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def _relative_file_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def _write_private_json(path: Path, document: Mapping[str, Any]) -> None:
    with path.open("xb") as handle:
        handle.write(canonical_json_bytes(document))
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(path, 0o600)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON document: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return value


def _file_records(value: Any) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    if isinstance(value, Mapping):
        if {"path", "bytes", "sha256"}.issubset(value):
            records.append(value)
        for item in value.values():
            records.extend(_file_records(item))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            records.extend(_file_records(item))
    return records


def _reject_absolute_paths(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key) == "path":
                text = str(item)
                if (
                    PurePosixPath(text).is_absolute()
                    or PureWindowsPath(text).is_absolute()
                ):
                    raise ValueError("musical-state manifest contains an absolute path")
            _reject_absolute_paths(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _reject_absolute_paths(item)


def _safe_relative_path(value: Any) -> PurePosixPath:
    text = str(value or "")
    path = PurePosixPath(text)
    if (
        not text
        or "\\" in text
        or path.is_absolute()
        or PureWindowsPath(text).is_absolute()
        or ".." in path.parts
    ):
        raise ValueError("musical-state artifact path must be safe and relative")
    return path


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _non_negative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be finite")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _sha256_text(value: Any, label: str) -> str:
    text = str(value or "")
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return text


def _capture_label(value: Any, fallback: str) -> str:
    text = fallback if value is None else str(value).strip()
    if (
        not text
        or len(text) > 120
        or "\n" in text
        or "\r" in text
        or "/" in text
        or "\\" in text
    ):
        raise ValueError("vocal phrase capture label must be short path-free text")
    return text


def _vocal_source_ids(state: Mapping[str, Any]) -> set[str]:
    vocal = _mapping(state.get("vocal_performance_state"), "vocal state")
    result = {
        str(row.get("source_id"))
        for row in vocal.get("takes", [])
        if isinstance(row, Mapping)
    }
    reference = vocal.get("reference")
    if isinstance(reference, Mapping):
        result.add(str(reference.get("source_id")))
    result.update(
        str(row.get("source_id"))
        for row in vocal.get("phrase_captures", [])
        if isinstance(row, Mapping)
    )
    return result


def _file(value: str | Path | None, label: str) -> Path:
    path = Path(str(value)).expanduser().absolute()
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} does not exist or is linked: {path}")
    return path


def _directory(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser().absolute()
    if not path.is_dir() or path.is_symlink():
        raise ValueError(f"{label} does not exist or is linked: {path}")
    return path


def _words(value: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)?", value.casefold())


def _find_words(
    haystack: Sequence[str], needle: Sequence[str], start: int
) -> int | None:
    maximum = len(haystack) - len(needle)
    for index in range(start, maximum + 1):
        if list(haystack[index : index + len(needle)]) == list(needle):
            return index
    return None


__all__ = [
    "METHOD_NATURES",
    "MUSICAL_STATE_SCHEMA",
    "VOCAL_COMP_TIMELINE_SCHEMA",
    "VOCAL_PERFORMANCE_STATE_SCHEMA",
    "VOCAL_PERFORMANCE_STATE_SCHEMA_V3",
    "admit_vocal_phrase_capture",
    "create_vocal_musical_state",
    "plan_vocal_musical_state",
    "validate_musical_state",
]
