"""Prepare an exact full-song queue for the bounded private Kim worker.

The audited Kim Vocal 2 worker deliberately accepts no more than fifteen
seconds per invocation.  This owner-only preparation layer keeps that ceiling
unchanged.  It decodes one authorised original, converts the complete song to
the worker's fixed 44.1 kHz stereo clock, partitions that clock without gaps or
overlaps, and writes one independently hash-bound authorisation package per
chunk.  It never runs a model or enables a product route.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from ._separation_authorised_excerpt import (
    AUTHORISED_EXCERPT_SCHEMA,
    _authorised_corpus_evidence,
    _document_sha256,
    _inside,
    _original_audio_files,
    _regular_json,
    _sha256,
    _track,
)
from ._separation_melroformer_real_bridge import (
    MAXIMUM_EXCERPT_FRAMES,
    MINIMUM_PROBE_FRAMES,
)


SCHEMA = "sunofriend.private-separation-full-song-plan.v1"
STATUS = "prepared_chunk_authorisations_no_model_run"
POLICY_ID = "contiguous-canonical-44100-worker-chunks-v1"
REPORT_NAME = "private-separation-full-song-plan.json"
CHUNK_REPORT_NAME = "authorised-separation-excerpt.json"
TARGET_SAMPLE_RATE = 44_100
MAXIMUM_SOURCE_BYTES = 2 * 1024 * 1024 * 1024
MAXIMUM_SONG_SECONDS = 20 * 60
MINIMUM_SOURCE_RATE = 8_000
MAXIMUM_SOURCE_RATE = 96_000
_CORPUS_SCHEMAS = frozenset(
    {
        "sunofriend.authorised-separation-corpus.v1",
        "sunofriend.private-reference-separation-corpus.v1",
    }
)
_FALSE_PERMISSIONS = {
    "accepted": False,
    "automatic_promotion": False,
    "automatic_selection": False,
    "production_eligible": False,
    "public_result": False,
    "simple_mode_available": False,
    "source_graph_activation": False,
    "studio_import_available": False,
}


def _prepare_private_separation_full_song_plan(
    corpus_manifest_path: str | Path,
    track_id: str,
    *,
    out_dir: str | Path,
    maximum_chunk_frames: int = MAXIMUM_EXCERPT_FRAMES,
) -> dict[str, Any]:
    """Write a fresh, model-free queue of worker-compatible song chunks."""

    import numpy as np
    import soundfile

    maximum_frames = _maximum_chunk_frames(maximum_chunk_frames)
    manifest = _regular_json(corpus_manifest_path, "corpus manifest")
    manifest_sha256 = _sha256(manifest)
    try:
        corpus = json.loads(manifest.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("corpus manifest is not valid JSON") from error
    if not isinstance(corpus, dict) or corpus.get("schema") not in _CORPUS_SCHEMAS:
        raise ValueError("unsupported authorised separation corpus schema")
    track = _track(corpus, track_id)
    corpus_evidence = _authorised_corpus_evidence(
        corpus,
        track,
        manifest_path=manifest,
        manifest_sha256=manifest_sha256,
    )
    corpus_evidence.pop("manifest_path", None)
    track_root = _inside(
        manifest.parent,
        str(track.get("directory", "")),
        "track directory",
        require_directory=True,
    )
    originals = _original_audio_files(track_root / "ORIGINAL")
    if len(originals) != 1:
        raise ValueError("track must contain exactly one supported ORIGINAL audio file")
    source = originals[0]
    source_state = source.lstat()
    if source_state.st_size > MAXIMUM_SOURCE_BYTES:
        raise ValueError("full-song source exceeds the private two-GiB bound")
    source_sha256 = _sha256(source)
    source_info = soundfile.info(source)
    source_geometry = _source_geometry(source_info)

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(
            f"Private full-song plan output already exists: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.building-",
            dir=destination.parent,
        )
    )
    temporary.chmod(0o700)
    try:
        decoded, decoded_rate = soundfile.read(
            source,
            dtype="float32",
            always_2d=True,
        )
        if int(decoded_rate) != source_geometry["sample_rate"] or decoded.shape != (
            source_geometry["frames"],
            source_geometry["channels"],
        ):
            raise ValueError("decoded full-song geometry differs from source metadata")
        canonical, derivation = _canonical_audio(
            decoded,
            source_rate=source_geometry["sample_rate"],
            np=np,
        )
        boundaries = _chunk_boundaries(len(canonical), maximum_frames)
        chunks: list[dict[str, Any]] = []
        canonical_digest = hashlib.sha256()
        for index, (start_frame, end_frame) in enumerate(boundaries):
            chunk = _write_chunk_package(
                temporary,
                index=index,
                start_frame=start_frame,
                end_frame=end_frame,
                canonical=canonical,
                corpus_evidence=corpus_evidence,
                source_identity={
                    "sha256": source_sha256,
                    "bytes": source_state.st_size,
                    "extension": source.suffix.lower(),
                    "geometry": source_geometry,
                },
                derivation=derivation,
                soundfile=soundfile,
            )
            chunks.append(chunk)
            canonical_digest.update(
                _pcm24_int32_bytes(
                    temporary / chunk["audio_artifact"]["path"],
                    soundfile=soundfile,
                )
            )

        canonical_frames = len(canonical)
        source_end_seconds = source_geometry["frames"] / source_geometry["sample_rate"]
        canonical_end_seconds = canonical_frames / TARGET_SAMPLE_RATE
        document: dict[str, Any] = {
            "schema": SCHEMA,
            "status": STATUS,
            "policy_id": POLICY_ID,
            "evidence_scope": "private_development_only",
            "corpus": {
                "manifest_schema": corpus_evidence["manifest_schema"],
                "manifest_sha256": manifest_sha256,
                "track_id": corpus_evidence["track_id"],
                "track_title": corpus_evidence["track_title"],
                "rights_authority": _rights_authority(corpus_evidence),
            },
            "source": {
                "sha256": source_sha256,
                "bytes": source_state.st_size,
                "extension": source.suffix.lower(),
                "geometry": source_geometry,
            },
            "canonical_clock": {
                "sample_rate": TARGET_SAMPLE_RATE,
                "channels": 2,
                "frames": canonical_frames,
                "duration_seconds": canonical_end_seconds,
                "source_end_seconds": source_end_seconds,
                "end_error_seconds": canonical_end_seconds - source_end_seconds,
                "pcm24_int32_sequence_sha256": canonical_digest.hexdigest(),
                "derivation": derivation,
            },
            "chunking": {
                "maximum_chunk_frames": maximum_frames,
                "maximum_chunk_seconds": maximum_frames / TARGET_SAMPLE_RATE,
                "chunk_count": len(chunks),
                "coverage_start_frame": 0,
                "coverage_end_frame": canonical_frames,
                "gap_frames": 0,
                "overlap_frames": 0,
                "contiguous_exact_frame_coverage": True,
                "independent_worker_invocations_required": len(chunks),
                "stitching_not_yet_run": True,
            },
            "chunks": chunks,
            "readiness": {
                "chunk_authorisations_ready": True,
                "worker_runs_complete": False,
                "stitched_outputs_complete": False,
                "boundary_listening_complete": False,
                "full_song_duration_and_alignment_gate_passed": False,
                "resource_envelope_gate_passed": False,
                "publication_ready": False,
            },
            "permissions": dict(_FALSE_PERMISSIONS),
            "effects": {
                "authorisation_chunks_created": True,
                "canonical_chunk_audio_created": True,
                "model_run": False,
                "separator_output_created": False,
                "source_audio_mutated": False,
                "source_graph_mutated": False,
                "product_contract_mutated": False,
            },
            "limitations": [
                "This plan proves only exact source-clock partitioning; it contains no separator result.",
                "Independent chunk inference can create audible boundary differences and requires a later stitch-and-review contract.",
                "Preparing the queue does not close duration/alignment, resource, quality, role, licensing, offline or product-route gates.",
                "No downbeat, tempo or musical alignment is inferred from recorded zero.",
            ],
        }
        document["document_sha256"] = _document_sha256(document)
        _write_json(temporary / REPORT_NAME, document)
        _make_private_tree(temporary)
        _require_hash(manifest, manifest_sha256, "corpus manifest")
        _require_hash(source, source_sha256, "full-song source")
        _verify_plan_tree(temporary, document, soundfile=soundfile)
        os.replace(temporary, destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    document["report"] = str(destination / REPORT_NAME)
    document["output_directory"] = str(destination)
    return document


def _maximum_chunk_frames(value: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 2 * MINIMUM_PROBE_FRAMES
        or value > MAXIMUM_EXCERPT_FRAMES
    ):
        raise ValueError("maximum chunk frames are outside the audited worker bound")
    return value


def _rights_authority(corpus_evidence: Mapping[str, Any]) -> str:
    permission = corpus_evidence.get("permission")
    if not isinstance(permission, Mapping):
        raise ValueError("full-song corpus permission differs")
    if corpus_evidence.get("manifest_schema") == "sunofriend.authorised-separation-corpus.v1":
        if (
            permission.get("authority") != "creator_and_copyright_holder"
            or permission.get("allowed_use")
            != "download, study, transform and reuse"
        ):
            raise ValueError("full-song creator authority differs")
        return "creator_and_copyright_holder"
    if (
        corpus_evidence.get("manifest_schema")
        == "sunofriend.private-reference-separation-corpus.v1"
        and permission.get("status") == "user_authorised"
        and permission.get("scope") == "private_local_evaluation_only"
    ):
        return "user_authorised_private_local_evaluation"
    raise ValueError("full-song rights authority differs")


def _source_geometry(info: Any) -> dict[str, Any]:
    sample_rate = int(info.samplerate)
    channels = int(info.channels)
    frames = int(info.frames)
    if not MINIMUM_SOURCE_RATE <= sample_rate <= MAXIMUM_SOURCE_RATE:
        raise ValueError("full-song source sample rate is outside 8-96 kHz")
    if channels not in {1, 2}:
        raise ValueError("full-song source must be mono or stereo")
    if frames < MINIMUM_PROBE_FRAMES:
        raise ValueError("full-song source is too short for the private worker")
    duration = frames / sample_rate
    if duration > MAXIMUM_SONG_SECONDS:
        raise ValueError("full-song source exceeds the private 20-minute bound")
    return {
        "sample_rate": sample_rate,
        "channels": channels,
        "frames": frames,
        "duration_seconds": duration,
    }


def _canonical_audio(value: Any, *, source_rate: int, np: Any) -> tuple[Any, dict[str, Any]]:
    if value.ndim != 2 or value.shape[1] not in {1, 2}:
        raise ValueError("decoded full-song channel geometry differs")
    if not bool(np.isfinite(value).all()) or float(np.max(np.abs(value))) > 1.0:
        raise ValueError("decoded full-song samples are outside finite PCM bounds")
    if value.shape[1] == 1:
        stereo = np.repeat(value, 2, axis=1)
        channel_policy = "mono duplicated to left and right"
    else:
        stereo = value
        channel_policy = "stereo channels preserved"
    expected_frames = int(round(len(stereo) * TARGET_SAMPLE_RATE / source_rate))
    if source_rate == TARGET_SAMPLE_RATE:
        resampled = stereo.astype("float64")
        algorithm = "identity"
        scipy_version = None
    else:
        from scipy.signal import resample_poly

        divisor = math.gcd(source_rate, TARGET_SAMPLE_RATE)
        up = TARGET_SAMPLE_RATE // divisor
        down = source_rate // divisor
        resampled = resample_poly(
            stereo.astype("float64"),
            up,
            down,
            axis=0,
            padtype="constant",
        )
        if len(resampled) > expected_frames:
            resampled = resampled[:expected_frames]
        elif len(resampled) < expected_frames:
            resampled = np.concatenate(
                (
                    resampled,
                    np.zeros((expected_frames - len(resampled), 2), dtype="float64"),
                ),
                axis=0,
            )
        algorithm = (
            f"scipy.signal.resample_poly(up={up},down={down},padtype=constant)"
        )
        scipy_version = importlib.metadata.version("scipy")
    clipping_count = int(np.count_nonzero(np.abs(resampled) > 1.0))
    pre_clip_peak = float(np.max(np.abs(resampled))) if resampled.size else 0.0
    if clipping_count:
        resampled = np.clip(resampled, -1.0, 1.0)
    canonical = np.ascontiguousarray(resampled, dtype="float32")
    if len(canonical) != expected_frames or canonical.shape[1] != 2:
        raise ValueError("canonical full-song geometry differs")
    return canonical, {
        "source_sample_rate": source_rate,
        "target_sample_rate": TARGET_SAMPLE_RATE,
        "algorithm": algorithm,
        "scipy_version": scipy_version,
        "channel_policy": channel_policy,
        "pcm_subtype": "PCM_24",
        "expected_target_frames_policy": "round(source_frames*44100/source_rate)",
        "clipping": {
            "required": bool(clipping_count),
            "sample_count": clipping_count,
            "pre_clip_peak": round(pre_clip_peak, 9) if clipping_count else None,
        },
    }


def _chunk_boundaries(total_frames: int, maximum_frames: int) -> tuple[tuple[int, int], ...]:
    if total_frames < MINIMUM_PROBE_FRAMES:
        raise ValueError("canonical song is too short")
    count = max(1, math.ceil(total_frames / maximum_frames))
    boundaries = tuple(
        (
            (index * total_frames) // count,
            ((index + 1) * total_frames) // count,
        )
        for index in range(count)
    )
    if (
        boundaries[0][0] != 0
        or boundaries[-1][1] != total_frames
        or any(end - start < MINIMUM_PROBE_FRAMES for start, end in boundaries)
        or any(end - start > maximum_frames for start, end in boundaries)
        or any(left[1] != right[0] for left, right in zip(boundaries, boundaries[1:]))
    ):
        raise ValueError("canonical song cannot be partitioned inside worker bounds")
    return boundaries


def _write_chunk_package(
    root: Path,
    *,
    index: int,
    start_frame: int,
    end_frame: int,
    canonical: Any,
    corpus_evidence: Mapping[str, Any],
    source_identity: Mapping[str, Any],
    derivation: Mapping[str, Any],
    soundfile: Any,
) -> dict[str, Any]:
    chunk_name = f"chunk-{index:04d}"
    chunk_root = root / "CHUNKS" / chunk_name
    audio = chunk_root / "LOCAL-MODEL-INPUT" / "source-44100.wav"
    audio.parent.mkdir(parents=True, exist_ok=False)
    soundfile.write(
        audio,
        canonical[start_frame:end_frame],
        TARGET_SAMPLE_RATE,
        subtype="PCM_24",
    )
    reopened, reopened_rate = soundfile.read(audio, dtype="float32", always_2d=True)
    frames = end_frame - start_frame
    if int(reopened_rate) != TARGET_SAMPLE_RATE or reopened.shape != (frames, 2):
        raise ValueError("persisted full-song chunk geometry differs")
    relative_audio = audio.relative_to(chunk_root).as_posix()
    audio_artifact = {
        "path": relative_audio,
        "sha256": _sha256(audio),
        "bytes": audio.stat().st_size,
    }
    geometry = {
        "sample_rate": TARGET_SAMPLE_RATE,
        "channels": 2,
        "frames": frames,
        "duration_seconds": frames / TARGET_SAMPLE_RATE,
    }
    report: dict[str, Any] = {
        "schema": AUTHORISED_EXCERPT_SCHEMA,
        "status": "complete_review_required",
        "evidence_scope": "private_development_only",
        "corpus": dict(corpus_evidence),
        "excerpt": {
            "start_seconds": start_frame / TARGET_SAMPLE_RATE,
            "end_seconds": end_frame / TARGET_SAMPLE_RATE,
            "selection_policy": POLICY_ID,
            "full_song_chunk_index": index,
            "canonical_start_frame": start_frame,
            "canonical_end_frame": end_frame,
        },
        "original": {
            "source": dict(source_identity),
            "local_model_input": {
                "artifact": audio_artifact,
                "geometry": geometry,
                "derivation": dict(derivation),
            },
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": {
            "local_excerpt_created": True,
            "model_run": False,
            "source_audio_mutated": False,
            "source_graph_mutated": False,
        },
        "limitations": [
            "This is one exact clock partition from a complete-song queue.",
            "The worker must run this package independently; no separator output exists yet.",
        ],
    }
    report["document_sha256"] = _document_sha256(report)
    report_path = chunk_root / CHUNK_REPORT_NAME
    _write_json(report_path, report)
    return {
        "index": index,
        "start_frame": start_frame,
        "end_frame": end_frame,
        "frames": frames,
        "start_seconds": start_frame / TARGET_SAMPLE_RATE,
        "end_seconds": end_frame / TARGET_SAMPLE_RATE,
        "authorisation_report": {
            "path": report_path.relative_to(root).as_posix(),
            "sha256": _sha256(report_path),
            "document_sha256": report["document_sha256"],
            "bytes": report_path.stat().st_size,
        },
        "audio_artifact": {
            "path": audio.relative_to(root).as_posix(),
            "sha256": audio_artifact["sha256"],
            "bytes": audio_artifact["bytes"],
        },
        "worker_status": "not_run",
    }


def _pcm24_int32_bytes(path: Path, *, soundfile: Any) -> bytes:
    value, rate = soundfile.read(path, dtype="int32", always_2d=True)
    if int(rate) != TARGET_SAMPLE_RATE or value.ndim != 2 or value.shape[1] != 2:
        raise ValueError("PCM24 sequence evidence geometry differs")
    return value.astype("<i4", copy=False).tobytes(order="C")


def _verify_plan_tree(root: Path, document: Mapping[str, Any], *, soundfile: Any) -> None:
    if document.get("document_sha256") != _document_sha256(document):
        raise ValueError("private full-song plan self-hash differs")
    report_path = root / REPORT_NAME
    if _sha256(report_path) == "0" * 64:
        raise ValueError("private full-song plan report hash differs")
    expected_start = 0
    digest = hashlib.sha256()
    for chunk in document["chunks"]:
        if chunk["start_frame"] != expected_start or chunk["end_frame"] <= expected_start:
            raise ValueError("private full-song chunk coverage differs")
        expected_start = chunk["end_frame"]
        report = root / chunk["authorisation_report"]["path"]
        audio = root / chunk["audio_artifact"]["path"]
        if (
            _sha256(report) != chunk["authorisation_report"]["sha256"]
            or _sha256(audio) != chunk["audio_artifact"]["sha256"]
        ):
            raise ValueError("private full-song chunk artifact hash differs")
        chunk_document = json.loads(report.read_text(encoding="utf-8"))
        if (
            chunk_document.get("document_sha256")
            != chunk["authorisation_report"]["document_sha256"]
            or chunk_document.get("document_sha256")
            != _document_sha256(chunk_document)
        ):
            raise ValueError("private full-song chunk report self-hash differs")
        digest.update(_pcm24_int32_bytes(audio, soundfile=soundfile))
    if (
        expected_start != document["canonical_clock"]["frames"]
        or digest.hexdigest()
        != document["canonical_clock"]["pcm24_int32_sequence_sha256"]
    ):
        raise ValueError("private full-song canonical sequence differs")


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    payload = (
        json.dumps(
            document,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        os.set_inheritable(descriptor, False)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise RuntimeError("private full-song JSON write made no progress")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _make_private_tree(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("private full-song plan contains a symbolic link")
        path.chmod(0o700 if path.is_dir() else 0o600)
    root.chmod(0o700)


def _require_hash(path: Path, expected: str, label: str) -> None:
    if _sha256(path) != expected:
        raise ValueError(f"{label} changed during full-song preparation")


__all__: tuple[str, ...] = ()
