"""Explicit review and application of source-event sampler candidates.

Sample Instrument v2 remains the immutable baseline.  This module creates a
local review page from its advisory dynamics evidence, then applies only a
fully reviewed document to a separate Sample Instrument v3 experiment.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import tempfile
from pathlib import Path
from typing import Any, Sequence


SAMPLE_PACK_REVIEW_SCHEMA = "sunofriend.sample-pack-review.v1"
SAMPLE_PACK_V3_SCHEMA = "sunofriend.sample-instrument-v3.v1"
SAMPLE_BOUNDARY_REVIEW_SCHEMA = "sunofriend.sample-boundary-review.v2"
SAMPLE_BOUNDARY_MANIFEST_SCHEMA = "sunofriend.sample-boundary-review-manifest.v2"


def create_sample_pack_review(
    sample_pack_dir: str | Path,
    *,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Create an unreviewed local page and event-audio evidence."""

    source_pack = Path(sample_pack_dir).expanduser().resolve()
    destination = Path(out_dir).expanduser()
    if not source_pack.is_dir():
        raise ValueError(f"Sample pack directory not found: {source_pack}")
    if destination.exists():
        raise ValueError(f"Output directory already exists: {destination}")
    report_path = source_pack / "sample_pack.json"
    dynamics_path = source_pack / "source_event_dynamics.json"
    clusters_path = source_pack / "source_event_clusters.json"
    for path in (report_path, dynamics_path, clusters_path):
        if not path.is_file():
            raise ValueError(
                f"Required Sample Instrument v2 evidence not found: {path}"
            )
    report = _read_json(report_path)
    dynamics = _read_json(dynamics_path)
    clusters = _read_json(clusters_path)
    if report.get("operation") != "sample-pack" or report.get("format_version") != 2:
        raise ValueError("Review requires an unchanged Sample Instrument v2 pack")
    if dynamics.get("schema") != "sunofriend.source-event-dynamics.v1":
        raise ValueError("Unsupported source-event dynamics evidence")
    _verify_source_evidence(dynamics)

    stem = Path(str(report["stem"])).expanduser().resolve()
    midi = Path(str(report["midi"])).expanduser().resolve()
    if stem != Path(str(dynamics["source"]["path"])).expanduser().resolve():
        raise ValueError("Sample-pack stem does not match its dynamics evidence")
    if midi != Path(str(dynamics["midi"]["path"])).expanduser().resolve():
        raise ValueError("Sample-pack MIDI does not match its dynamics evidence")
    baseline_soundfont = source_pack / str(report["artifacts"]["soundfont"])
    if not baseline_soundfont.is_file():
        raise ValueError(f"Baseline SoundFont not found: {baseline_soundfont}")

    cluster_events = {
        int(row["event_index"]): row for row in clusters.get("events", [])
    }
    review_units = _review_units(dynamics, cluster_events)
    if not review_units:
        raise ValueError("Dynamics evidence contains no layer or alternate-sample sets")

    from .instrument_match import (
        DRUM_KINDS,
        _fade_and_normalize,
        _load_audio,
        _write_wav,
    )

    audio, sample_rate = _load_audio(stem, target_sample_rate=None)
    kind = str(report.get("kind", "")).strip().lower()
    bpm = _initial_midi_bpm(midi)
    is_drums = kind in DRUM_KINDS
    role_mode = "repeated-beat" if is_drums else "pitched-phrase"
    role_label = "Repeated two-bar beat" if is_drums else "Short sampler pitch phrase"
    destination.parent.mkdir(parents=True, exist_ok=True)
    work = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.building-", dir=destination.parent
        )
    )
    try:
        review_audio = work / "review-audio"
        review_audio.mkdir()
        context_audio = review_audio / "context"
        context_audio.mkdir()
        event_paths: dict[int, str] = {}
        event_hashes: dict[int, str] = {}
        event_contexts: dict[int, dict[str, Any]] = {}
        manifest_files: list[dict[str, Any]] = []
        source_peak = _audio_peak(audio)
        for unit in review_units:
            for layer in unit["layers"]:
                for option in layer["event_options"]:
                    event_index = int(option["event_index"])
                    if event_index in event_paths:
                        option["audio"] = event_paths[event_index]
                        option["audio_sha256"] = event_hashes[event_index]
                        option["context_audio"] = event_contexts[event_index]
                        continue
                    event = cluster_events[event_index]
                    start = max(
                        0, int(round(float(event["start_seconds"]) * sample_rate))
                    )
                    end = min(
                        len(audio),
                        int(round(float(event["end_seconds"]) * sample_rate)),
                    )
                    if end <= start:
                        raise ValueError(
                            f"Source event {event_index} has no audio frames"
                        )
                    filename = (
                        f"event-{event_index:04d}-midi-{int(event['pitch']):03d}.wav"
                    )
                    relative = str(Path("review-audio") / filename)
                    isolated = _fade_and_normalize(audio[start:end], sample_rate)
                    _write_wav(
                        review_audio / filename,
                        isolated,
                        sample_rate,
                    )
                    event_paths[event_index] = relative
                    event_hashes[event_index] = _file_sha256(review_audio / filename)
                    option["audio"] = relative
                    option["audio_sha256"] = event_hashes[event_index]
                    manifest_files.append(
                        {
                            "event_index": event_index,
                            "purpose": "isolated-event",
                            "path": relative,
                            "sha256": event_hashes[event_index],
                        }
                    )

                    source_values, context_start, context_end = _source_context_audio(
                        audio,
                        sample_rate,
                        event_start_seconds=float(event["start_seconds"]),
                        bpm=bpm,
                        source_peak=source_peak,
                    )
                    source_name = (
                        f"event-{event_index:04d}-midi-{int(event['pitch']):03d}-"
                        "source-context.wav"
                    )
                    source_relative = str(
                        Path("review-audio") / "context" / source_name
                    )
                    source_path = context_audio / source_name
                    _write_wav(source_path, source_values, sample_rate)
                    source_hash = _file_sha256(source_path)
                    manifest_files.append(
                        {
                            "event_index": event_index,
                            "purpose": "source-context",
                            "path": source_relative,
                            "sha256": source_hash,
                        }
                    )

                    role_values = _role_audition_audio(
                        isolated,
                        sample_rate,
                        bpm=bpm,
                        is_drums=is_drums,
                    )
                    role_name = (
                        f"event-{event_index:04d}-midi-{int(event['pitch']):03d}-"
                        f"{role_mode}.wav"
                    )
                    role_relative = str(Path("review-audio") / "context" / role_name)
                    role_path = context_audio / role_name
                    _write_wav(role_path, role_values, sample_rate)
                    role_hash = _file_sha256(role_path)
                    manifest_files.append(
                        {
                            "event_index": event_index,
                            "purpose": role_mode,
                            "path": role_relative,
                            "sha256": role_hash,
                        }
                    )
                    event_contexts[event_index] = {
                        "source_context": {
                            "audio": source_relative,
                            "audio_sha256": source_hash,
                            "label": "Source rhythm and surrounding stem",
                            "start_seconds": context_start,
                            "end_seconds": context_end,
                            "target_offset_seconds": round(
                                float(event["start_seconds"]) - context_start, 6
                            ),
                            "level_policy": "shared stem peak; relative levels retained",
                        },
                        "role_audition": {
                            "audio": role_relative,
                            "audio_sha256": role_hash,
                            "label": role_label,
                            "mode": role_mode,
                            "bpm": bpm,
                            "level_policy": "per-event normalised for timbre comparison",
                        },
                    }
                    option["context_audio"] = event_contexts[event_index]

        baseline_samples = []
        for row in report.get("samples", []):
            sample_path = source_pack / str(row["file"])
            if not sample_path.is_file():
                raise ValueError(f"Baseline sample not found: {sample_path}")
            baseline_samples.append(
                {
                    "relative_path": str(row["file"]),
                    "path": str(sample_path.resolve()),
                    "sha256": _file_sha256(sample_path),
                }
            )

        source_record = {
            "path": str(source_pack),
            "report": str(report_path),
            "report_sha256": _file_sha256(report_path),
            "dynamics": str(dynamics_path),
            "dynamics_sha256": _file_sha256(dynamics_path),
            "clusters": str(clusters_path),
            "clusters_sha256": _file_sha256(clusters_path),
            "stem": str(stem),
            "stem_sha256": _file_sha256(stem),
            "midi": str(midi),
            "midi_sha256": _file_sha256(midi),
            "baseline_soundfont": str(baseline_soundfont),
            "baseline_soundfont_sha256": _file_sha256(baseline_soundfont),
            "baseline_samples": baseline_samples,
        }
        review_audio_manifest = {
            "schema": "sunofriend.sample-review-audio-manifest.v1",
            "source_stem_sha256": source_record["stem_sha256"],
            "context_policy": {
                "kind": kind,
                "bpm": bpm,
                "source_context_beats": 4.0,
                "source_context_target_offset_beats": 1.0,
                "role_audition_mode": role_mode,
                "role_audition_label": role_label,
                "selection_effect": "none",
            },
            "files": sorted(
                manifest_files,
                key=lambda row: (int(row["event_index"]), str(row["purpose"])),
            ),
        }
        manifest_build_path = work / "review_audio_manifest.json"
        _write_json(manifest_build_path, review_audio_manifest)
        seed = {
            "schema": SAMPLE_PACK_REVIEW_SCHEMA,
            "operation": "sample-pack-review",
            "status": "unreviewed",
            "review_required": True,
            "source_sample_pack": source_record,
            "policy": {
                "acceptance": (
                    "Every proposed unit must be explicitly accepted or rejected. "
                    "Accepted event indices must be members of the immutable candidate set."
                ),
                "one_accepted_unit_per_pitch": True,
                "sf2_round_robin_support": False,
                "garageband_alternates": (
                    "Accepted alternates become separate SF2/AUSampler A/B variants; "
                    "the portable SFZ can use true sequence round robin."
                ),
                "baseline_mutated": False,
            },
            "summary": {
                "review_unit_count": len(review_units),
                "velocity_layer_unit_count": sum(
                    bool(row["velocity_layer_candidate"]) for row in review_units
                ),
                "alternate_sample_set_count": sum(
                    layer["candidate_event_count"] >= 2
                    for row in review_units
                    for layer in row["layers"]
                ),
                "candidate_event_count": len(event_paths),
                "context_audio_file_count": len(event_paths) * 2,
                "accepted_unit_count": 0,
                "rejected_unit_count": 0,
            },
            "units": review_units,
            "review_evidence": {
                "directory": str(destination.resolve()),
                "manifest": str(destination.resolve() / "review_audio_manifest.json"),
                "manifest_sha256": _file_sha256(manifest_build_path),
                "audio_file_count": len(manifest_files),
                "isolated_audio_file_count": len(event_paths),
                "context_audio_file_count": len(event_paths) * 2,
                "context_policy": review_audio_manifest["context_policy"],
            },
            "effects": {
                "baseline_files_changed": 0,
                "midi_notes_changed": 0,
                "midi_velocities_changed": 0,
                "soundfont_zones_changed": 0,
            },
            "artifacts": {
                "seed": "sample_pack_review.seed.json",
                "html": "sample_pack_review.html",
                "source_event_dynamics": "source_event_dynamics.json",
                "source_event_dynamics_graph": "source_event_dynamics.svg",
                "review_audio": "review-audio",
                "context_audio": "review-audio/context",
                "review_audio_manifest": "review_audio_manifest.json",
            },
            "warnings": [
                "A source-level split can reflect bleed, phrase context or mixing rather than a real dynamic layer.",
                "Listening is required; this unreviewed seed cannot build an instrument.",
                "GarageBand/AUSampler receives separate alternate banks because portable SF2 has no round-robin opcode.",
                "Context auditions are listening evidence only and do not select, reject or remap a sample.",
            ],
        }
        _write_json(work / "sample_pack_review.seed.json", seed)
        (work / "sample_pack_review.html").write_text(
            _review_html(seed), encoding="utf-8"
        )
        shutil.copy2(dynamics_path, work / "source_event_dynamics.json")
        graph = source_pack / "source_event_dynamics.svg"
        if graph.is_file():
            shutil.copy2(graph, work / "source_event_dynamics.svg")
        work.rename(destination)
        return {
            **seed,
            "seed": str(destination / "sample_pack_review.seed.json"),
            "html": str(destination / "sample_pack_review.html"),
        }
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


def apply_sample_pack_review(
    review_path: str | Path,
    *,
    out_dir: str | Path,
    render_preview: bool = True,
    instrument_name: str | None = None,
    _mapping_overrides: dict[str, dict[str, Any]] | None = None,
    _boundary_review_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a separate v3 experiment from an explicitly reviewed document."""

    review_file = Path(review_path).expanduser().resolve()
    destination = Path(out_dir).expanduser()
    if not review_file.is_file():
        raise ValueError(f"Reviewed sample-pack JSON not found: {review_file}")
    if destination.exists():
        raise ValueError(f"Output directory already exists: {destination}")
    review = _read_json(review_file)
    if review.get("schema") != SAMPLE_PACK_REVIEW_SCHEMA:
        raise ValueError("Unsupported sample-pack review schema")
    if review.get("status") != "reviewed":
        raise ValueError("Sample-pack review must have status 'reviewed'")
    source_record = dict(review.get("source_sample_pack") or {})
    source_pack = Path(str(source_record.get("path", ""))).expanduser().resolve()
    _verify_review_sources(source_record)
    _verify_review_audio(review)
    report_path = Path(str(source_record["report"]))
    dynamics_path = Path(str(source_record["dynamics"]))
    clusters_path = Path(str(source_record["clusters"]))
    baseline_report = _read_json(report_path)
    dynamics = _read_json(dynamics_path)
    clusters = _read_json(clusters_path)
    accepted = _validate_review_choices(review, dynamics)
    if not accepted:
        raise ValueError("Reviewed document accepts no sampler changes")
    original_accepted = json.loads(json.dumps(accepted))
    if _mapping_overrides:
        accepted = _apply_mapping_overrides(accepted, _mapping_overrides)

    baseline_rows = [dict(row) for row in baseline_report.get("samples", [])]
    baseline_by_pitch = {int(row["pitch"]): row for row in baseline_rows}
    missing_pitches = sorted(
        int(unit["pitch"])
        for unit in accepted
        if int(unit["pitch"]) not in baseline_by_pitch
    )
    if missing_pitches:
        joined = ", ".join(str(value) for value in missing_pitches)
        raise ValueError(
            "Accepted units must have an existing Sample Instrument v2 root; "
            f"missing MIDI pitches: {joined}"
        )

    stem = Path(str(source_record["stem"]))
    cluster_events = {
        int(row["event_index"]): row for row in clusters.get("events", [])
    }
    from .instrument_match import (
        DRUM_KINDS,
        _estimate_sample_tuning,
        _fade_and_normalize,
        _load_audio,
        _write_wav,
    )

    audio, sample_rate = _load_audio(stem, target_sample_rate=None)
    destination.parent.mkdir(parents=True, exist_ok=True)
    work = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.building-", dir=destination.parent
        )
    )
    try:
        samples_base = work / "samples" / "baseline"
        samples_reviewed = work / "samples" / "reviewed"
        samples_base.mkdir(parents=True)
        samples_reviewed.mkdir(parents=True)
        accepted_by_pitch = {int(row["pitch"]): row for row in accepted}
        output_base_rows = []
        for row in baseline_rows:
            source = source_pack / str(row["file"])
            if not source.is_file():
                raise ValueError(f"Baseline sample not found: {source}")
            target = samples_base / source.name
            shutil.copy2(source, target)
            output_base_rows.append(
                {**row, "file": str(Path("samples/baseline") / source.name)}
            )

        extracted: dict[int, dict[str, Any]] = {}
        auto_tune = bool(baseline_report.get("auto_tune"))
        kind = str(baseline_report.get("kind", ""))
        for unit in accepted:
            pitch = int(unit["pitch"])
            base = baseline_by_pitch[pitch]
            for layer in unit["layers"]:
                for event_index in layer["accepted_event_indices"]:
                    event_index = int(event_index)
                    if event_index in extracted:
                        continue
                    event = cluster_events[event_index]
                    start = max(
                        0, int(round(float(event["start_seconds"]) * sample_rate))
                    )
                    end = min(
                        len(audio),
                        int(round(float(event["end_seconds"]) * sample_rate)),
                    )
                    values = _fade_and_normalize(audio[start:end], sample_rate)
                    filename = (
                        f"event-{event_index:04d}-midi-{pitch:03d}-"
                        f"{float(event['start_seconds']):010.3f}s.wav"
                    )
                    target = samples_reviewed / filename
                    _write_wav(target, values, sample_rate)
                    extracted[event_index] = {
                        "event_index": event_index,
                        "note_index": int(event["note_index"]),
                        "pitch": pitch,
                        "start_seconds": float(event["start_seconds"]),
                        "end_seconds": float(event["end_seconds"]),
                        "rms": float(event["rms"]),
                        "velocity": int(event["velocity"]),
                        "file": str(Path("samples/reviewed") / filename),
                        "low_key": int(base["low_key"]),
                        "high_key": int(base["high_key"]),
                        "tuning": _estimate_sample_tuning(
                            values,
                            sample_rate,
                            pitch,
                            enabled=auto_tune and kind not in DRUM_KINDS,
                        ),
                    }

        main_rows = _variant_rows(output_base_rows, accepted, extracted, variant=0)
        name = instrument_name or f"{baseline_report['instrument_name']} v3"
        soundfont = _write_v3_soundfont(
            work / "sunofriend-instrument.sf2", main_rows, name=name
        )
        (work / "sunofriend-instrument.sfz").write_text(
            _v3_sfz_text(output_base_rows, accepted, extracted), encoding="utf-8"
        )
        main_preset = _write_preset(
            work / "sunofriend-instrument.sf2",
            work / "sunofriend-instrument.aupreset",
            destination.resolve() / "sunofriend-instrument.sf2",
        )

        baseline_dir = work / "baseline-v2"
        baseline_dir.mkdir()
        baseline_sf2 = baseline_dir / "sunofriend-instrument-v2.sf2"
        shutil.copy2(Path(str(source_record["baseline_soundfont"])), baseline_sf2)
        baseline_preset = _write_preset(
            baseline_sf2,
            baseline_dir / "sunofriend-instrument-v2.aupreset",
            destination.resolve() / "baseline-v2/sunofriend-instrument-v2.sf2",
        )

        audition = work / "garageband-ab-audition.mid"
        _write_v3_audition(audition, main_rows)
        performance_audition = work / "garageband-performance-ab.mid"
        performance = _write_performance_audition(
            Path(str(source_record["midi"])),
            performance_audition,
            track_index=int(
                (baseline_report.get("track") or {}).get("selected_index", 0)
            ),
            kind=kind,
        )
        performance_source = work / "garageband-performance-source.wav"
        performance_source_values = _performance_source_audio(
            audio,
            sample_rate,
            start_seconds=float(performance["source_start_seconds"]),
            end_seconds=float(performance["source_end_seconds"]),
        )
        _write_wav(performance_source, performance_source_values, sample_rate)
        velocity_sweep_path = work / "garageband-velocity-sweep.mid"
        velocity_sweep = _write_velocity_sweep(
            velocity_sweep_path,
            accepted,
            bpm=float(performance["initial_bpm"]),
        )
        preview = None
        baseline_preview = None
        performance_preview = None
        baseline_performance_preview = None
        velocity_sweep_preview = None
        baseline_velocity_sweep_preview = None
        if render_preview:
            from .render import render_midi_to_wav

            preview = work / "garageband-ab-v3.wav"
            baseline_preview = baseline_dir / "garageband-ab-v2.wav"
            render_midi_to_wav(
                audition, preview, soundfont_path=work / "sunofriend-instrument.sf2"
            )
            render_midi_to_wav(audition, baseline_preview, soundfont_path=baseline_sf2)
            performance_preview = work / "garageband-performance-v3.wav"
            baseline_performance_preview = (
                baseline_dir / "garageband-performance-v2.wav"
            )
            render_midi_to_wav(
                performance_audition,
                performance_preview,
                soundfont_path=work / "sunofriend-instrument.sf2",
            )
            render_midi_to_wav(
                performance_audition,
                baseline_performance_preview,
                soundfont_path=baseline_sf2,
            )
            if velocity_sweep:
                velocity_sweep_preview = work / "garageband-velocity-sweep-v3.wav"
                baseline_velocity_sweep_preview = (
                    baseline_dir / "garageband-velocity-sweep-v2.wav"
                )
                render_midi_to_wav(
                    velocity_sweep_path,
                    velocity_sweep_preview,
                    soundfont_path=work / "sunofriend-instrument.sf2",
                )
                render_midi_to_wav(
                    velocity_sweep_path,
                    baseline_velocity_sweep_preview,
                    soundfont_path=baseline_sf2,
                )
        performance.update(
            {
                "midi": "garageband-performance-ab.mid",
                "midi_sha256": _file_sha256(performance_audition),
                "source_reference_wav": "garageband-performance-source.wav",
                "source_reference_sha256": _file_sha256(performance_source),
                "source_reference_level_policy": (
                    "normalised once for the selected source excerpt; internal "
                    "dynamics and rhythm retained"
                ),
                "v3_preview_wav": (
                    "garageband-performance-v3.wav" if performance_preview else None
                ),
                "v3_preview_sha256": (
                    _file_sha256(performance_preview) if performance_preview else None
                ),
                "v2_preview_wav": (
                    "baseline-v2/garageband-performance-v2.wav"
                    if baseline_performance_preview
                    else None
                ),
                "v2_preview_sha256": (
                    _file_sha256(baseline_performance_preview)
                    if baseline_performance_preview
                    else None
                ),
            }
        )
        if velocity_sweep:
            velocity_sweep.update(
                {
                    "midi": "garageband-velocity-sweep.mid",
                    "midi_sha256": _file_sha256(velocity_sweep_path),
                    "v3_preview_wav": (
                        "garageband-velocity-sweep-v3.wav"
                        if velocity_sweep_preview
                        else None
                    ),
                    "v3_preview_sha256": (
                        _file_sha256(velocity_sweep_preview)
                        if velocity_sweep_preview
                        else None
                    ),
                    "v2_preview_wav": (
                        "baseline-v2/garageband-velocity-sweep-v2.wav"
                        if baseline_velocity_sweep_preview
                        else None
                    ),
                    "v2_preview_sha256": (
                        _file_sha256(baseline_velocity_sweep_preview)
                        if baseline_velocity_sweep_preview
                        else None
                    ),
                }
            )

        variant_count = max(
            len(layer["accepted_event_indices"])
            for unit in accepted
            for layer in unit["layers"]
        )
        variants = []
        if variant_count > 1:
            variants_dir = work / "garageband-alternates"
            variants_dir.mkdir()
            for variant in range(1, variant_count):
                rows = _variant_rows(
                    output_base_rows, accepted, extracted, variant=variant
                )
                sf2_name = f"alternate-{variant + 1:02d}.sf2"
                preset_name = f"alternate-{variant + 1:02d}.aupreset"
                sf2_path = variants_dir / sf2_name
                summary = _write_v3_soundfont(
                    sf2_path,
                    rows,
                    name=f"{name} A{variant + 1}",
                    sample_root=work,
                )
                preset = _write_preset(
                    sf2_path,
                    variants_dir / preset_name,
                    destination.resolve() / "garageband-alternates" / sf2_name,
                )
                preview_path = None
                if render_preview:
                    from .render import render_midi_to_wav

                    preview_path = variants_dir / f"alternate-{variant + 1:02d}.wav"
                    render_midi_to_wav(audition, preview_path, soundfont_path=sf2_path)
                variants.append(
                    {
                        "variant": variant + 1,
                        "soundfont": str(Path("garageband-alternates") / sf2_name),
                        "soundfont_sha256": _file_sha256(sf2_path),
                        "ausampler_preset": (
                            str(Path("garageband-alternates") / preset_name)
                            if preset
                            else None
                        ),
                        "preview_wav": (
                            str(Path("garageband-alternates") / preview_path.name)
                            if preview_path
                            else None
                        ),
                        "zone_count": summary["zone_count"],
                        "reviewed_event_selections": [
                            {
                                "unit_id": unit["unit_id"],
                                "layer_id": layer["layer_id"],
                                "event_index": layer["accepted_event_indices"][
                                    variant % len(layer["accepted_event_indices"])
                                ],
                            }
                            for unit in accepted
                            for layer in unit["layers"]
                        ],
                    }
                )

        review_hash = _file_sha256(review_file)
        changed_pitches = sorted(accepted_by_pitch)
        v2_zone_count = int(baseline_report["soundfont"]["zone_count"])
        applied_features = _application_features(accepted, variants)
        velocity_layer_unit_count = applied_features["velocity_layer_unit_count"]
        round_robin_layer_count = applied_features["round_robin_layer_count"]
        warnings = [
            "This is a review-derived Sample Instrument v3 experiment; the v2 baseline remains authoritative and embedded for rollback.",
            "Bleed, room sound, effects and phrase transitions remain baked into every accepted source sample.",
            (
                f"The {performance['bars']}-bar performance A/B is an audition-only "
                "excerpt shifted to bar 1 and MIDI channel 1; the source MIDI is unchanged."
            ),
        ]
        if velocity_layer_unit_count:
            warnings.append(
                "The main SF2 applies reviewed velocity layers with one accepted primary source event per layer."
            )
            warnings.append(
                "The velocity sweep audits the accepted boundary from both sides; it does not change the boundary or source selections."
            )
        else:
            warnings.append(
                "No velocity layer was accepted; the main SF2 applies only the reviewed primary-sample replacement."
            )
        if round_robin_layer_count:
            warnings.append(
                "The SFZ uses sequence round robin; GarageBand alternates are separate A/B banks and do not switch automatically."
            )
        else:
            warnings.append(
                "No alternate source event was accepted; no round robin or GarageBand alternate bank was generated."
            )
        if _boundary_review_record:
            warnings.append(
                "Velocity-layer mappings came only from the separately reviewed, hash-pinned export; no new source sample, source-audio edit or source-MIDI change was introduced."
            )
        original_by_id = {
            str(unit["unit_id"]): unit for unit in original_accepted
        }
        boundary_change_count = sum(
            bool(unit.get("velocity_layers_applied"))
            and bool(original_by_id[str(unit["unit_id"])].get("velocity_layers_applied"))
            and original_by_id[str(unit["unit_id"])].get("velocity_boundary")
            != unit.get("velocity_boundary")
            for unit in accepted
        )
        velocity_layers_removed = sum(
            bool(original_by_id[str(unit["unit_id"])].get("velocity_layers_applied"))
            and not bool(unit.get("velocity_layers_applied"))
            for unit in accepted
        )
        original_events = {
            event_index
            for unit in original_accepted
            for layer in unit["layers"]
            for event_index in layer["accepted_event_indices"]
        }
        applied_events = {
            event_index
            for unit in accepted
            for layer in unit["layers"]
            for event_index in layer["accepted_event_indices"]
        }
        report = {
            "schema": SAMPLE_PACK_V3_SCHEMA,
            "operation": (
                "sample-pack-boundary-apply"
                if _boundary_review_record
                else "sample-pack-apply"
            ),
            "format_version": 3,
            "status": "complete",
            "experimental": True,
            "review": {
                "path": str(review_file),
                "sha256": review_hash,
                "status": "reviewed",
                "accepted_unit_count": len(accepted),
                "rejected_unit_count": sum(
                    row.get("decision") == "reject" for row in review["units"]
                ),
            },
            "boundary_review": _boundary_review_record,
            "baseline": {
                "sample_pack": str(source_pack),
                "report_sha256": source_record["report_sha256"],
                "soundfont": "baseline-v2/sunofriend-instrument-v2.sf2",
                "soundfont_sha256": source_record["baseline_soundfont_sha256"],
                "ausampler_preset": (
                    "baseline-v2/sunofriend-instrument-v2.aupreset"
                    if baseline_preset
                    else None
                ),
                "mutated": False,
            },
            "instrument_name": soundfont["name"],
            "kind": kind,
            "sample_rate": sample_rate,
            "accepted_units": accepted,
            "applied_features": applied_features,
            "extracted_event_samples": [extracted[key] for key in sorted(extracted)],
            "soundfont": {
                **soundfont,
                "path": "sunofriend-instrument.sf2",
                "sha256": _file_sha256(work / "sunofriend-instrument.sf2"),
                "round_robin": False,
                "velocity_layers": bool(velocity_layer_unit_count),
            },
            "sfz": {
                "path": "sunofriend-instrument.sfz",
                "sha256": _file_sha256(work / "sunofriend-instrument.sfz"),
                "round_robin": bool(round_robin_layer_count),
            },
            "ausampler_preset": main_preset,
            "garageband_alternates": variants,
            "performance_audition": performance,
            "velocity_sweep": velocity_sweep,
            "effects": {
                "baseline_files_changed": 0,
                "midi_notes_changed": 0,
                "midi_velocities_changed": 0,
                "accepted_source_events_added": len(extracted),
                "reviewed_root_pitches": changed_pitches,
                "soundfont_zone_count_before": v2_zone_count,
                "soundfont_zone_count_after": int(soundfont["zone_count"]),
                "soundfont_zone_delta": int(soundfont["zone_count"]) - v2_zone_count,
                "velocity_boundaries_changed": boundary_change_count,
                "velocity_layers_removed": velocity_layers_removed,
                "active_source_events_removed": len(original_events - applied_events),
                "new_source_events_introduced": len(applied_events - original_events),
                "source_sample_audio_files_modified": 0,
                "source_samples_changed_by_boundary_review": 0,
            },
            "artifacts": {
                "report": "sample_pack_v3.json",
                "readme": "README.md",
                "boundary_review": (
                    "reviewed_boundary_decisions.json"
                    if _boundary_review_record
                    else None
                ),
                "soundfont": "sunofriend-instrument.sf2",
                "sfz": "sunofriend-instrument.sfz",
                "ausampler_preset": (
                    "sunofriend-instrument.aupreset" if main_preset else None
                ),
                "audition_midi": "garageband-ab-audition.mid",
                "audition_v3_wav": "garageband-ab-v3.wav" if preview else None,
                "audition_v2_wav": (
                    "baseline-v2/garageband-ab-v2.wav" if baseline_preview else None
                ),
                "performance_audition_midi": "garageband-performance-ab.mid",
                "performance_source_wav": "garageband-performance-source.wav",
                "performance_audition_v3_wav": (
                    "garageband-performance-v3.wav" if performance_preview else None
                ),
                "performance_audition_v2_wav": (
                    "baseline-v2/garageband-performance-v2.wav"
                    if baseline_performance_preview
                    else None
                ),
                "velocity_sweep_midi": (
                    "garageband-velocity-sweep.mid" if velocity_sweep else None
                ),
                "velocity_sweep_v3_wav": (
                    "garageband-velocity-sweep-v3.wav"
                    if velocity_sweep_preview
                    else None
                ),
                "velocity_sweep_v2_wav": (
                    "baseline-v2/garageband-velocity-sweep-v2.wav"
                    if baseline_velocity_sweep_preview
                    else None
                ),
                "baseline": "baseline-v2",
                "alternates": "garageband-alternates" if variants else None,
                "samples": "samples",
            },
            "warnings": warnings,
        }
        _write_json(work / "sample_pack_v3.json", report)
        (work / "README.md").write_text(_v3_readme(report), encoding="utf-8")
        shutil.copy2(review_file, work / "reviewed_decisions.json")
        if _boundary_review_record:
            shutil.copy2(
                Path(str(_boundary_review_record["path"])),
                work / "reviewed_boundary_decisions.json",
            )
        work.rename(destination)
        return {
            **report,
            "report": str(destination / "sample_pack_v3.json"),
            "readme": str(destination / "README.md"),
        }
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


def create_sample_boundary_review(
    sample_pack_v3_dir: str | Path,
    *,
    out_dir: str | Path,
    render_preview: bool = True,
) -> dict[str, Any]:
    """Create an explicit A/B review for accepted v3 layer mappings."""

    source_pack = Path(sample_pack_v3_dir).expanduser().resolve()
    destination = Path(out_dir).expanduser()
    if not source_pack.is_dir():
        raise ValueError(f"Sample Instrument v3 directory not found: {source_pack}")
    if destination.exists():
        raise ValueError(f"Output directory already exists: {destination}")
    report_path = source_pack / "sample_pack_v3.json"
    if not report_path.is_file():
        raise ValueError(f"Sample Instrument v3 report not found: {report_path}")
    report = _read_json(report_path)
    if report.get("schema") != SAMPLE_PACK_V3_SCHEMA or report.get(
        "format_version"
    ) != 3:
        raise ValueError("Boundary review requires a completed Sample Instrument v3")
    if report.get("status") != "complete":
        raise ValueError("Boundary review requires a completed Sample Instrument v3")
    accepted = [dict(unit) for unit in report.get("accepted_units", [])]
    layered = [
        unit
        for unit in accepted
        if bool(unit.get("velocity_layers_applied"))
        and len(unit.get("layers", [])) == 2
        and unit.get("velocity_boundary") is not None
    ]
    if not layered:
        raise ValueError("Sample Instrument v3 has no accepted two-layer boundaries")

    source_record = _boundary_source_record(source_pack, report_path, report)
    base_rows, extracted = _v3_source_rows(source_pack, report)
    bpm = float(
        (report.get("velocity_sweep") or {}).get("bpm")
        or (report.get("performance_audition") or {}).get("initial_bpm")
        or 120.0
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    work = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.building-", dir=destination.parent
        )
    )
    try:
        manifest_files: list[dict[str, Any]] = []
        review_units = []
        for unit in sorted(layered, key=lambda row: int(row["pitch"])):
            unit_id = str(unit["unit_id"])
            pitch = int(unit["pitch"])
            current = int(unit["velocity_boundary"])
            boundaries = _boundary_candidate_values(current)
            source_velocities = _source_pitch_velocities(source_record, pitch)
            source_velocity_range = [min(source_velocities), max(source_velocities)]
            mapping_specs = _mapping_candidate_specs(
                unit,
                boundaries=boundaries,
                source_velocity_range=source_velocity_range,
            )
            token = _safe_token(f"{unit_id}-midi-{pitch:03d}")
            unit_dir = work / "units" / token
            unit_dir.mkdir(parents=True)
            sweep_path = unit_dir / "velocity-ramp.mid"
            sweep = _write_boundary_review_sweep(
                sweep_path,
                pitch=pitch,
                boundaries=boundaries,
                bpm=bpm,
            )
            sweep_relative = str(sweep_path.relative_to(work))
            manifest_files.append(
                {
                    "purpose": "shared-boundary-sweep-midi",
                    "unit_id": unit_id,
                    "path": sweep_relative,
                    "sha256": _file_sha256(sweep_path),
                }
            )
            tone_midi_path = unit_dir / "constant-velocity-repeated-beat.mid"
            tone_velocity = int(round(sum(source_velocity_range) / 2.0))
            tone = _write_constant_velocity_audition(
                tone_midi_path,
                pitch=pitch,
                velocity=tone_velocity,
                bpm=bpm,
            )
            tone_midi_relative = str(tone_midi_path.relative_to(work))
            manifest_files.append(
                {
                    "purpose": "shared-constant-velocity-midi",
                    "unit_id": unit_id,
                    "path": tone_midi_relative,
                    "sha256": _file_sha256(tone_midi_path),
                }
            )
            candidates = []
            for mapping in mapping_specs:
                mapping_id = str(mapping["mapping_id"])
                candidate_dir = unit_dir / _safe_token(mapping_id)
                candidate_dir.mkdir()
                overridden = _apply_mapping_overrides(
                    accepted,
                    {
                        unit_id: {
                            "mode": mapping["mode"],
                            "boundary": mapping.get("boundary"),
                        }
                    },
                )
                rows = _variant_rows(base_rows, overridden, extracted, variant=0)
                sf2_path = candidate_dir / "sunofriend-instrument.sf2"
                summary = _write_v3_soundfont(
                    sf2_path,
                    rows,
                    name=f"{report['instrument_name']} {mapping_id}",
                    sample_root=source_pack,
                )
                sf2_relative = str(sf2_path.relative_to(work))
                preset_path = candidate_dir / "sunofriend-instrument.aupreset"
                preset = _write_preset(
                    sf2_path,
                    preset_path,
                    destination.resolve() / sf2_relative,
                )
                preview_path = None
                tone_preview_path = None
                if render_preview:
                    from .render import render_midi_to_wav

                    preview_path = candidate_dir / "velocity-ramp.wav"
                    render_midi_to_wav(
                        sweep_path, preview_path, soundfont_path=sf2_path
                    )
                    if mapping["mode"] in {"single-low", "single-high"}:
                        tone_preview_path = (
                            candidate_dir / "constant-velocity-repeated-beat.wav"
                        )
                        render_midi_to_wav(
                            tone_midi_path,
                            tone_preview_path,
                            soundfont_path=sf2_path,
                        )
                candidate = {
                    **mapping,
                    "soundfont": sf2_relative,
                    "soundfont_sha256": _file_sha256(sf2_path),
                    "ausampler_preset": (
                        str(preset_path.relative_to(work)) if preset else None
                    ),
                    "ausampler_preset_sha256": (
                        _file_sha256(preset_path) if preset else None
                    ),
                    "preview_wav": (
                        str(preview_path.relative_to(work)) if preview_path else None
                    ),
                    "preview_sha256": (
                        _file_sha256(preview_path) if preview_path else None
                    ),
                    "constant_tone_wav": (
                        str(tone_preview_path.relative_to(work))
                        if tone_preview_path
                        else None
                    ),
                    "constant_tone_sha256": (
                        _file_sha256(tone_preview_path) if tone_preview_path else None
                    ),
                    "zone_count": int(summary["zone_count"]),
                }
                candidates.append(candidate)
                for purpose, path_key, hash_key in (
                    ("candidate-soundfont", "soundfont", "soundfont_sha256"),
                    (
                        "candidate-ausampler-preset",
                        "ausampler_preset",
                        "ausampler_preset_sha256",
                    ),
                    ("candidate-preview", "preview_wav", "preview_sha256"),
                    (
                        "constant-velocity-tone-preview",
                        "constant_tone_wav",
                        "constant_tone_sha256",
                    ),
                ):
                    if candidate[path_key]:
                        manifest_files.append(
                            {
                                "purpose": purpose,
                                "unit_id": unit_id,
                                "mapping_id": mapping_id,
                                "path": candidate[path_key],
                                "sha256": candidate[hash_key],
                            }
                        )
            tone_by_mode = {candidate["mode"]: candidate for candidate in candidates}
            review_units.append(
                {
                    "unit_id": unit_id,
                    "pitch": pitch,
                    "current_boundary": current,
                    "current_mapping_id": f"layered-{current:03d}",
                    "selected_mapping_id": None,
                    "source_midi_velocity_range": source_velocity_range,
                    "source_midi_velocities": source_velocities,
                    "sweep_midi": sweep_relative,
                    "sweep_midi_sha256": _file_sha256(sweep_path),
                    "sweep_velocities": sweep["velocities"],
                    "tone_comparison": {
                        "midi": tone_midi_relative,
                        "midi_sha256": _file_sha256(tone_midi_path),
                        "velocity": tone_velocity,
                        "pattern": tone["pattern"],
                        "lower_event_index": int(
                            unit["layers"][0]["primary_event_index"]
                        ),
                        "lower_preview_wav": tone_by_mode["single-low"][
                            "constant_tone_wav"
                        ],
                        "lower_preview_sha256": tone_by_mode["single-low"][
                            "constant_tone_sha256"
                        ],
                        "upper_event_index": int(
                            unit["layers"][1]["primary_event_index"]
                        ),
                        "upper_preview_wav": tone_by_mode["single-high"][
                            "constant_tone_wav"
                        ],
                        "upper_preview_sha256": tone_by_mode["single-high"][
                            "constant_tone_sha256"
                        ],
                    },
                    "candidates": candidates,
                }
            )

        manifest = {
            "schema": SAMPLE_BOUNDARY_MANIFEST_SCHEMA,
            "source_sample_pack_v3": source_record,
            "units": review_units,
            "files": sorted(
                manifest_files,
                key=lambda row: (
                    str(row.get("unit_id")),
                    str(row.get("mapping_id", "")),
                    str(row["purpose"]),
                ),
            ),
        }
        manifest_path = work / "boundary_review_manifest.json"
        _write_json(manifest_path, manifest)
        seed = {
            "schema": SAMPLE_BOUNDARY_REVIEW_SCHEMA,
            "operation": "sample-pack-boundary-review",
            "status": "unreviewed",
            "review_required": True,
            "source_sample_pack_v3": source_record,
            "policy": {
                "selection": "Exactly one explicit single-sample or layered mapping per reviewed unit",
                "new_source_samples_allowed": False,
                "source_sample_audio_modified": False,
                "source_midi_changed": False,
                "source_v3_mutated": False,
                "candidate_ordering": "single lower source, ascending layered boundaries, single upper source; no default selection",
            },
            "summary": {
                "review_unit_count": len(review_units),
                "reviewed_unit_count": 0,
                "candidate_count": sum(
                    len(unit["candidates"]) for unit in review_units
                ),
            },
            "units": review_units,
            "review_evidence": {
                "directory": str(destination.resolve()),
                "manifest": str(
                    destination.resolve() / "boundary_review_manifest.json"
                ),
                "manifest_sha256": _file_sha256(manifest_path),
                "file_count": len(manifest_files),
            },
            "effects": {
                "source_v3_files_changed": 0,
                "source_samples_changed": 0,
                "source_midi_notes_changed": 0,
                "source_midi_velocities_changed": 0,
                "boundaries_changed": 0,
                "layer_mappings_changed": 0,
            },
            "artifacts": {
                "seed": "sample_boundary_review.seed.json",
                "html": "sample_boundary_review.html",
                "manifest": "boundary_review_manifest.json",
                "units": "units",
            },
            "warnings": [
                "The current mapping is only labelled, never preselected; keeping it also requires an explicit choice.",
                "Candidates introduce no new samples: they use the lower accepted event, upper accepted event or both with a reviewed boundary.",
                "The constant-velocity repeated beat separates tone and texture from MIDI loudness; the velocity ramp tests the complete mapping.",
                "The review does not mutate the source v3 pack and cannot apply itself.",
            ],
        }
        _write_json(work / "sample_boundary_review.seed.json", seed)
        (work / "sample_boundary_review.html").write_text(
            _boundary_review_html(seed), encoding="utf-8"
        )
        work.rename(destination)
        return {
            **seed,
            "seed": str(destination / "sample_boundary_review.seed.json"),
            "html": str(destination / "sample_boundary_review.html"),
        }
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


def apply_sample_boundary_review(
    review_path: str | Path,
    *,
    out_dir: str | Path,
    render_preview: bool = True,
    instrument_name: str | None = None,
) -> dict[str, Any]:
    """Apply only explicit, hash-pinned velocity-layer mapping selections."""

    review_file = Path(review_path).expanduser().resolve()
    if not review_file.is_file():
        raise ValueError(f"Reviewed boundary JSON not found: {review_file}")
    review = _read_json(review_file)
    if review.get("schema") != SAMPLE_BOUNDARY_REVIEW_SCHEMA:
        raise ValueError("Unsupported sample-boundary review schema")
    if review.get("status") != "reviewed":
        raise ValueError("Sample-boundary review must have status 'reviewed'")
    source_record, source_report = _verify_boundary_review(review)
    source_units = {
        str(unit["unit_id"]): unit
        for unit in source_report.get("accepted_units", [])
    }
    overrides: dict[str, dict[str, Any]] = {}
    changes = []
    for unit in review["units"]:
        unit_id = str(unit["unit_id"])
        selected = unit.get("selected_mapping_id")
        candidates = {
            str(row["mapping_id"]): row for row in unit["candidates"]
        }
        if selected is None or str(selected) not in candidates:
            raise ValueError(
                f"Boundary review unit {unit_id} needs one proposed mapping"
            )
        selected = str(selected)
        candidate = candidates[selected]
        source_unit = source_units.get(unit_id)
        if source_unit is None:
            raise ValueError(f"Boundary review references unknown v3 unit {unit_id}")
        current = int(source_unit["velocity_boundary"])
        if int(unit["current_boundary"]) != current:
            raise ValueError(f"Boundary review source changed for unit {unit_id}")
        overrides[unit_id] = {
            "mode": str(candidate["mode"]),
            "boundary": candidate.get("boundary"),
        }
        before = _unit_mapping_snapshot(source_unit)
        after_units = _apply_mapping_overrides(
            [source_unit], {unit_id: overrides[unit_id]}
        )
        after = _unit_mapping_snapshot(after_units[0])
        changes.append(
            {
                "unit_id": unit_id,
                "pitch": int(source_unit["pitch"]),
                "selected_mapping_id": selected,
                "before": before,
                "after": after,
                "changed": before != after,
            }
        )
    original_review = Path(str(source_record["reviewed_decisions"]))
    boundary_record = {
        "path": str(review_file),
        "sha256": _file_sha256(review_file),
        "status": "reviewed",
        "source_sample_pack_v3": str(source_record["path"]),
        "source_report_sha256": source_record["report_sha256"],
        "selected_unit_count": len(changes),
        "changed_unit_count": sum(row["changed"] for row in changes),
        "velocity_layers_removed": sum(
            row["before"]["mode"] == "layered"
            and row["after"]["mode"] != "layered"
            for row in changes
        ),
        "changes": changes,
        "new_source_samples_introduced": False,
        "source_sample_audio_modified": False,
        "source_midi_changed": False,
    }
    return apply_sample_pack_review(
        original_review,
        out_dir=out_dir,
        render_preview=render_preview,
        instrument_name=instrument_name or str(source_report["instrument_name"]),
        _mapping_overrides=overrides,
        _boundary_review_record=boundary_record,
    )


def _boundary_source_record(
    source_pack: Path, report_path: Path, report: dict[str, Any]
) -> dict[str, Any]:
    soundfont = source_pack / str(report["soundfont"]["path"])
    sfz = source_pack / str(report["sfz"]["path"])
    reviewed = source_pack / "reviewed_decisions.json"
    checks = (
        (soundfont, report["soundfont"]["sha256"], "v3 SoundFont"),
        (sfz, report["sfz"]["sha256"], "v3 SFZ"),
        (reviewed, report["review"]["sha256"], "reviewed sample decisions"),
    )
    for path, expected, label in checks:
        if not path.is_file() or _file_sha256(path) != expected:
            raise ValueError(f"Sample Instrument v3 {label} changed: {path}")
    reviewed_document = _read_json(reviewed)
    reviewed_source = dict(reviewed_document.get("source_sample_pack") or {})
    source_midi = Path(str(reviewed_source.get("midi", ""))).expanduser().resolve()
    source_clusters = Path(
        str(reviewed_source.get("clusters", ""))
    ).expanduser().resolve()
    for path, expected, label in (
        (source_midi, reviewed_source.get("midi_sha256"), "source MIDI"),
        (
            source_clusters,
            reviewed_source.get("clusters_sha256"),
            "source event clusters",
        ),
    ):
        if not path.is_file() or _file_sha256(path) != expected:
            raise ValueError(f"Sample Instrument v3 {label} changed: {path}")
    baseline_pack = Path(str(report["baseline"]["sample_pack"])).expanduser().resolve()
    baseline_report_path = baseline_pack / "sample_pack.json"
    if (
        not baseline_report_path.is_file()
        or _file_sha256(baseline_report_path)
        != report["baseline"]["report_sha256"]
    ):
        raise ValueError(
            f"Sample Instrument v3 baseline report changed: {baseline_report_path}"
        )
    baseline_report = _read_json(baseline_report_path)
    sample_files = []
    for row in baseline_report.get("samples", []):
        path = source_pack / "samples" / "baseline" / Path(str(row["file"])).name
        if not path.is_file():
            raise ValueError(f"Sample Instrument v3 baseline sample missing: {path}")
        sample_files.append(
            {
                "purpose": "baseline-sample",
                "path": str(path.resolve()),
                "sha256": _file_sha256(path),
            }
        )
    for row in report.get("extracted_event_samples", []):
        path = source_pack / str(row["file"])
        if not path.is_file():
            raise ValueError(f"Sample Instrument v3 reviewed sample missing: {path}")
        sample_files.append(
            {
                "purpose": "reviewed-event-sample",
                "event_index": int(row["event_index"]),
                "path": str(path.resolve()),
                "sha256": _file_sha256(path),
            }
        )
    return {
        "path": str(source_pack),
        "report": str(report_path.resolve()),
        "report_sha256": _file_sha256(report_path),
        "soundfont": str(soundfont.resolve()),
        "soundfont_sha256": _file_sha256(soundfont),
        "sfz": str(sfz.resolve()),
        "sfz_sha256": _file_sha256(sfz),
        "reviewed_decisions": str(reviewed.resolve()),
        "reviewed_decisions_sha256": _file_sha256(reviewed),
        "baseline_report": str(baseline_report_path.resolve()),
        "baseline_report_sha256": _file_sha256(baseline_report_path),
        "source_midi": str(source_midi),
        "source_midi_sha256": _file_sha256(source_midi),
        "source_clusters": str(source_clusters),
        "source_clusters_sha256": _file_sha256(source_clusters),
        "sample_files": sorted(sample_files, key=lambda row: str(row["path"])),
    }


def _v3_source_rows(
    source_pack: Path, report: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    baseline_report = _read_json(
        Path(str(report["baseline"]["sample_pack"])).expanduser().resolve()
        / "sample_pack.json"
    )
    base_rows = [
        {
            **row,
            "file": str(Path("samples/baseline") / Path(str(row["file"])).name),
        }
        for row in baseline_report.get("samples", [])
    ]
    extracted = {
        int(row["event_index"]): dict(row)
        for row in report.get("extracted_event_samples", [])
    }
    for row in [*base_rows, *extracted.values()]:
        path = source_pack / str(row["file"])
        if not path.is_file():
            raise ValueError(f"Sample Instrument v3 source sample missing: {path}")
    return base_rows, extracted


def _boundary_candidate_values(current: int) -> list[int]:
    return sorted(
        {
            max(1, min(126, current + offset))
            for offset in (-20, -16, -12, -8, -4, 0, 4, 8)
        }
    )


def _source_pitch_velocities(source_record: dict[str, Any], pitch: int) -> list[int]:
    clusters = _read_json(Path(str(source_record["source_clusters"])))
    velocities = sorted(
        {
            int(event["velocity"])
            for event in clusters.get("events", [])
            if int(event["pitch"]) == pitch
        }
    )
    if not velocities:
        raise ValueError(f"Source event evidence has no velocities for MIDI {pitch}")
    return velocities


def _mapping_candidate_specs(
    unit: dict[str, Any],
    *,
    boundaries: Sequence[int],
    source_velocity_range: Sequence[int],
) -> list[dict[str, Any]]:
    low_event = int(unit["layers"][0]["primary_event_index"])
    high_event = int(unit["layers"][1]["primary_event_index"])
    current = int(unit["velocity_boundary"])
    minimum, maximum = (int(value) for value in source_velocity_range)
    rows = [
        {
            "mapping_id": "single-low",
            "mode": "single-low",
            "label": f"Lower source event {low_event} at every velocity",
            "boundary": None,
            "is_current": False,
            "active_event_indices": [low_event],
            "low_velocity_range": [0, 127],
            "high_velocity_range": None,
            "source_midi_triggered_layers": ["single"],
            "source_midi_warning": None,
        }
    ]
    for boundary in boundaries:
        triggered = []
        if minimum <= boundary:
            triggered.append("lower")
        if maximum >= boundary + 1:
            triggered.append("upper")
        inactive = [name for name in ("lower", "upper") if name not in triggered]
        warning = None
        if inactive:
            joined = " and ".join(inactive)
            warning = (
                f"The {joined} layer is never triggered by this source MIDI's "
                f"velocity range {minimum}–{maximum}."
            )
        rows.append(
            {
                "mapping_id": f"layered-{boundary:03d}",
                "mode": "layered",
                "label": f"Two samples split at velocity {boundary}",
                "boundary": boundary,
                "is_current": boundary == current,
                "active_event_indices": [low_event, high_event],
                "low_velocity_range": [0, boundary],
                "high_velocity_range": [boundary + 1, 127],
                "source_midi_triggered_layers": triggered,
                "source_midi_warning": warning,
            }
        )
    rows.append(
        {
            "mapping_id": "single-high",
            "mode": "single-high",
            "label": f"Upper source event {high_event} at every velocity",
            "boundary": None,
            "is_current": False,
            "active_event_indices": [high_event],
            "low_velocity_range": [0, 127],
            "high_velocity_range": None,
            "source_midi_triggered_layers": ["single"],
            "source_midi_warning": None,
        }
    )
    return rows


def _safe_token(value: str) -> str:
    token = "".join(char.lower() if char.isalnum() else "-" for char in value)
    return "-".join(part for part in token.split("-") if part) or "unit"


def _write_boundary_review_sweep(
    path: Path,
    *,
    pitch: int,
    boundaries: Sequence[int],
    bpm: float,
) -> dict[str, Any]:
    from .midi import MidiTrack, write_midi_file
    from .models import NoteEvent

    velocities = sorted(
        {
            32,
            48,
            64,
            80,
            96,
            104,
            112,
            120,
            127,
            *(
                boundary + offset
                for boundary in boundaries
                for offset in (-1, 0, 1)
            ),
        }
    )
    velocities = [max(1, min(127, value)) for value in velocities]
    velocities = sorted(set(velocities))
    beat_seconds = 60.0 / bpm
    notes = [
        NoteEvent(
            start=index * 0.75 * beat_seconds,
            end=(index * 0.75 + 0.4) * beat_seconds,
            pitch=pitch,
            velocity=velocity,
        )
        for index, velocity in enumerate(velocities)
    ]
    write_midi_file(
        path,
        [
            MidiTrack(
                "Sample Instrument boundary review sweep",
                channel=0,
                program=0,
                notes=notes,
            )
        ],
        bpm=bpm,
    )
    return {
        "pitch": pitch,
        "bpm": bpm,
        "velocities": velocities,
        "note_count": len(notes),
        "pitch_changes": 0,
        "source_samples_changed": False,
    }


def _write_constant_velocity_audition(
    path: Path,
    *,
    pitch: int,
    velocity: int,
    bpm: float,
) -> dict[str, Any]:
    from .midi import MidiTrack, write_midi_file
    from .models import NoteEvent

    positions = (0.0, 1.0, 2.0, 3.0, 4.0, 4.5, 5.5, 6.0, 6.75, 7.5)
    beat_seconds = 60.0 / bpm
    notes = [
        NoteEvent(
            start=position * beat_seconds,
            end=(position + 0.35) * beat_seconds,
            pitch=pitch,
            velocity=velocity,
        )
        for position in positions
    ]
    write_midi_file(
        path,
        [
            MidiTrack(
                "Sample Instrument constant-velocity repeated beat",
                channel=0,
                program=0,
                notes=notes,
            )
        ],
        bpm=bpm,
    )
    return {
        "pitch": pitch,
        "velocity": velocity,
        "bpm": bpm,
        "note_count": len(notes),
        "pattern": "repeated two-bar beat; one fixed MIDI pitch and velocity",
    }


def _verify_boundary_review(
    review: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    evidence = dict(review.get("review_evidence") or {})
    directory = Path(str(evidence.get("directory", ""))).expanduser().resolve()
    manifest_path = Path(str(evidence.get("manifest", ""))).expanduser().resolve()
    if not manifest_path.is_file() or _file_sha256(manifest_path) != evidence.get(
        "manifest_sha256"
    ):
        raise ValueError(f"Reviewed boundary manifest changed: {manifest_path}")
    manifest = _read_json(manifest_path)
    if manifest.get("schema") != SAMPLE_BOUNDARY_MANIFEST_SCHEMA:
        raise ValueError("Unsupported sample-boundary review manifest")
    source_record = dict(review.get("source_sample_pack_v3") or {})
    if source_record != manifest.get("source_sample_pack_v3"):
        raise ValueError("Reviewed boundary source record differs from its manifest")
    immutable_review_units = json.loads(json.dumps(review.get("units", [])))
    for unit in immutable_review_units:
        unit["selected_mapping_id"] = None
    if immutable_review_units != manifest.get("units"):
        raise ValueError("Reviewed boundary candidates differ from their manifest")
    files = list(manifest.get("files") or [])
    if len(files) != int(evidence.get("file_count", -1)):
        raise ValueError("Reviewed boundary file count differs from its manifest")
    paths = [str(row.get("path", "")) for row in files]
    if len(paths) != len(set(paths)):
        raise ValueError("Reviewed boundary manifest contains duplicate files")
    for row in files:
        path = directory / str(row["path"])
        if not path.is_file() or _file_sha256(path) != row.get("sha256"):
            raise ValueError(f"Reviewed boundary evidence changed: {path}")
    _verify_boundary_source_record(source_record)
    report = _read_json(Path(str(source_record["report"])))
    if report.get("schema") != SAMPLE_PACK_V3_SCHEMA:
        raise ValueError("Boundary review source is not Sample Instrument v3")
    if len(review.get("units", [])) != int(
        review.get("summary", {}).get("review_unit_count", -1)
    ):
        raise ValueError("Reviewed boundary unit count is inconsistent")
    if len(review.get("units", [])) != int(
        review.get("summary", {}).get("reviewed_unit_count", -1)
    ):
        raise ValueError("Every boundary unit must be explicitly reviewed")
    return source_record, report


def _verify_boundary_source_record(record: dict[str, Any]) -> None:
    checks = (
        ("report", "report_sha256"),
        ("soundfont", "soundfont_sha256"),
        ("sfz", "sfz_sha256"),
        ("reviewed_decisions", "reviewed_decisions_sha256"),
        ("baseline_report", "baseline_report_sha256"),
        ("source_midi", "source_midi_sha256"),
        ("source_clusters", "source_clusters_sha256"),
    )
    for path_key, hash_key in checks:
        path = Path(str(record.get(path_key, ""))).expanduser().resolve()
        if not path.is_file() or _file_sha256(path) != record.get(hash_key):
            raise ValueError(f"Boundary review source artifact changed: {path}")
    samples = list(record.get("sample_files") or [])
    if not samples:
        raise ValueError("Boundary review source record contains no samples")
    for row in samples:
        path = Path(str(row.get("path", ""))).expanduser().resolve()
        if not path.is_file() or _file_sha256(path) != row.get("sha256"):
            raise ValueError(f"Boundary review source sample changed: {path}")


def _initial_midi_bpm(path: Path) -> float:
    try:
        import mido
    except ImportError as exc:  # pragma: no cover - convert installs mido
        raise RuntimeError("Sample review requires the 'mido' package") from exc

    midi = mido.MidiFile(str(path))
    tempo_events = []
    for track_index, track in enumerate(midi.tracks):
        tick = 0
        for message_index, message in enumerate(track):
            tick += int(message.time)
            if message.type == "set_tempo":
                tempo_events.append(
                    (tick, track_index, message_index, int(message.tempo))
                )
    tempo = min(tempo_events)[3] if tempo_events else 500_000
    return round(float(mido.tempo2bpm(tempo)), 3)


def _audio_peak(values: Any) -> float:
    import numpy as np

    audio = np.asarray(values, dtype=np.float32)
    return float(np.max(np.abs(audio))) if len(audio) else 0.0


def _source_context_audio(
    audio: Any,
    sample_rate: int,
    *,
    event_start_seconds: float,
    bpm: float,
    source_peak: float,
) -> tuple[Any, float, float]:
    import numpy as np

    beat_seconds = 60.0 / bpm
    start_seconds = max(0.0, event_start_seconds - beat_seconds)
    end_seconds = min(len(audio) / sample_rate, event_start_seconds + 3 * beat_seconds)
    start = int(round(start_seconds * sample_rate))
    end = int(round(end_seconds * sample_rate))
    values = np.asarray(audio[start:end], dtype=np.float32).copy()
    fade = min(len(values) // 2, max(1, int(round(sample_rate * 0.01))))
    if fade:
        values[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
        values[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    if source_peak > 1e-8:
        values *= 0.89 / source_peak
    return (
        np.clip(values, -1.0, 1.0),
        round(start_seconds, 6),
        round(end_seconds, 6),
    )


def _performance_source_audio(
    audio: Any,
    sample_rate: int,
    *,
    start_seconds: float,
    end_seconds: float,
) -> Any:
    import numpy as np

    start = max(0, int(round(start_seconds * sample_rate)))
    end = min(len(audio), int(round(end_seconds * sample_rate)))
    if end <= start:
        raise ValueError("Performance source excerpt has no audio frames")
    values = np.asarray(audio[start:end], dtype=np.float32).copy()
    fade = min(len(values) // 2, max(1, int(round(sample_rate * 0.01))))
    if fade:
        values[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
        values[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    peak = _audio_peak(values)
    if peak > 1e-8:
        values *= 0.89 / peak
    return np.clip(values, -1.0, 1.0)


def _role_audition_audio(
    isolated: Any,
    sample_rate: int,
    *,
    bpm: float,
    is_drums: bool,
) -> Any:
    import numpy as np

    source = np.asarray(isolated, dtype=np.float32)
    beat_frames = max(1, int(round(sample_rate * 60.0 / bpm)))
    if is_drums:
        positions = (0.0, 1.0, 2.0, 3.0, 4.0, 4.5, 5.5, 6.0, 6.75, 7.5)
        gains = (1.0, 0.72, 0.86, 0.68, 1.0, 0.62, 0.82, 0.7, 0.9, 0.65)
        sample = source[: max(1, round(beat_frames * 1.5))]
        duration = round(beat_frames * 8.0) + len(sample)
        output = np.zeros(duration, dtype=np.float32)
        for position, gain in zip(positions, gains):
            _mix_audio(output, sample, round(position * beat_frames), gain)
    else:
        intervals = (0, 2, 3, 5, 7, 5, 3, 2, 0)
        gains = (0.9, 0.72, 0.78, 0.7, 0.9, 0.72, 0.78, 0.7, 0.9)
        maximum = max(1, round(beat_frames * 0.9))
        duration = round(beat_frames * 5.0) + maximum
        output = np.zeros(duration, dtype=np.float32)
        for index, (interval, gain) in enumerate(zip(intervals, gains)):
            shifted = _sampler_pitch_shift(source, interval)[:maximum]
            _mix_audio(output, shifted, round(index * beat_frames * 0.5), gain)
    peak = _audio_peak(output)
    if peak > 0.95:
        output *= 0.95 / peak
    return np.clip(output, -1.0, 1.0)


def _sampler_pitch_shift(values: Any, semitones: int) -> Any:
    import numpy as np

    audio = np.asarray(values, dtype=np.float32)
    if not len(audio) or semitones == 0:
        return audio.copy()
    rate = 2.0 ** (float(semitones) / 12.0)
    length = max(1, int(round(len(audio) / rate)))
    positions = np.arange(length, dtype=np.float64) * rate
    shifted = np.interp(
        positions,
        np.arange(len(audio), dtype=np.float64),
        audio,
        left=0.0,
        right=0.0,
    )
    return shifted.astype(np.float32)


def _mix_audio(target: Any, source: Any, start: int, gain: float) -> None:
    end = min(len(target), start + len(source))
    if end > start:
        target[start:end] += source[: end - start] * float(gain)


def _review_units(
    dynamics: dict[str, Any], cluster_events: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    rows = []
    for unit in dynamics.get("units", []):
        layers = []
        has_alternates = False
        for layer in unit.get("layers", []):
            candidates = [
                int(value)
                for value in layer.get("round_robin", {}).get(
                    "candidate_event_indices", []
                )
            ]
            if len(candidates) >= 2:
                has_alternates = True
            options = []
            for event_index in candidates:
                event = cluster_events.get(event_index)
                if event is None:
                    raise ValueError(
                        f"Dynamics evidence references missing source event {event_index}"
                    )
                options.append(
                    {
                        "event_index": event_index,
                        "note_index": int(event["note_index"]),
                        "start_seconds": float(event["start_seconds"]),
                        "end_seconds": float(event["end_seconds"]),
                        "rms_db": _rms_db(event),
                        "velocity": int(event["velocity"]),
                        "identity_distance_to_medoid": float(
                            event["identity_distance_to_medoid"]
                        ),
                        "audio": None,
                    }
                )
            layers.append(
                {
                    "layer_id": str(layer["layer_id"]),
                    "event_count": int(layer["event_count"]),
                    "median_rms_db": float(layer["median_rms_db"]),
                    "velocity_range": list(layer["velocity_range"]),
                    "candidate_event_count": len(candidates),
                    "candidate_event_indices": candidates,
                    "event_options": options,
                    "primary_event_index": None,
                    "accepted_event_indices": [],
                }
            )
        if not bool(unit.get("velocity_layer_candidate")) and not has_alternates:
            continue
        rows.append(
            {
                "unit_id": str(unit["unit_id"]),
                "pitch": int(unit["pitch"]),
                "identity_candidate_cluster": str(unit["identity_candidate_cluster"]),
                "articulation_cluster": str(unit["articulation_cluster"]),
                "velocity_layer_candidate": bool(unit["velocity_layer_candidate"]),
                "suggested_velocity_boundary": (
                    int(unit["velocity_split"]["suggested_velocity_boundary"])
                    if unit.get("velocity_split")
                    else None
                ),
                "decision": "unreviewed",
                "layers": layers,
            }
        )
    return rows


def _application_features(
    accepted: Sequence[dict[str, Any]], variants: Sequence[dict[str, Any]]
) -> dict[str, int]:
    return {
        "reviewed_sample_replacement_count": len(accepted),
        "velocity_layer_unit_count": sum(
            bool(unit["velocity_layers_applied"]) for unit in accepted
        ),
        "round_robin_layer_count": sum(
            len(layer["accepted_event_indices"]) > 1
            for unit in accepted
            for layer in unit["layers"]
        ),
        "garageband_alternate_bank_count": len(variants),
    }


def _unit_mapping_snapshot(unit: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": (
            "layered" if bool(unit.get("velocity_layers_applied")) else "single"
        ),
        "velocity_boundary": unit.get("velocity_boundary"),
        "active_event_indices": [
            int(event_index)
            for layer in unit["layers"]
            for event_index in layer["accepted_event_indices"]
        ],
    }


def _mapping_snapshot_label(snapshot: dict[str, Any]) -> str:
    events = ", ".join(str(value) for value in snapshot["active_event_indices"])
    if snapshot["mode"] == "layered":
        return f"events {events} split at {snapshot['velocity_boundary']}"
    return f"event {events} across velocities 0–127"


def _apply_mapping_overrides(
    accepted: Sequence[dict[str, Any]],
    overrides: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Apply reviewed mappings using only already accepted layer sources."""

    by_id = {str(unit["unit_id"]): unit for unit in accepted}
    unknown = sorted(set(overrides) - set(by_id))
    if unknown:
        raise ValueError(f"Boundary review references unknown accepted units: {unknown}")
    output = []
    for source in accepted:
        unit = {**source, "layers": [dict(layer) for layer in source["layers"]]}
        unit_id = str(unit["unit_id"])
        if unit_id in overrides:
            if not unit.get("velocity_layers_applied") or len(unit["layers"]) != 2:
                raise ValueError(
                    f"Boundary review unit {unit_id} is not an accepted two-layer unit"
                )
            mapping = overrides[unit_id]
            mode = str(mapping.get("mode"))
            if mode == "layered":
                boundary = int(mapping["boundary"])
                if not 1 <= boundary <= 126:
                    raise ValueError(
                        f"Boundary review unit {unit_id} must select a value from 1 to 126"
                    )
                unit["velocity_boundary"] = boundary
            elif mode in {"single-low", "single-high"}:
                layer_index = 0 if mode == "single-low" else 1
                unit["layers"] = [unit["layers"][layer_index]]
                unit["velocity_layers_applied"] = False
                unit["velocity_boundary"] = None
            else:
                raise ValueError(
                    f"Boundary review unit {unit_id} has unsupported mapping mode {mode}"
                )
        output.append(unit)
    return output


def _validate_review_choices(
    review: dict[str, Any], dynamics: dict[str, Any]
) -> list[dict[str, Any]]:
    expected = {
        str(unit["unit_id"]): unit
        for unit in dynamics.get("units", [])
        if bool(unit.get("velocity_layer_candidate"))
        or any(
            len(layer.get("round_robin", {}).get("candidate_event_indices", [])) >= 2
            for layer in unit.get("layers", [])
        )
    }
    supplied = {str(unit.get("unit_id")): unit for unit in review.get("units", [])}
    if set(supplied) != set(expected):
        raise ValueError(
            "Reviewed units do not exactly match the immutable dynamics evidence"
        )
    accepted = []
    accepted_pitches: set[int] = set()
    for unit_id in sorted(expected):
        proposal = expected[unit_id]
        choice = supplied[unit_id]
        decision = choice.get("decision")
        if decision not in {"accept", "reject"}:
            raise ValueError(
                f"Review unit {unit_id} is not explicitly accepted or rejected"
            )
        if decision == "reject":
            continue
        pitch = int(proposal["pitch"])
        if pitch in accepted_pitches:
            raise ValueError(
                f"Only one accepted review unit is allowed for MIDI pitch {pitch}"
            )
        accepted_pitches.add(pitch)
        proposal_layers = {
            str(layer["layer_id"]): layer for layer in proposal.get("layers", [])
        }
        choice_layers = {
            str(layer.get("layer_id")): layer for layer in choice.get("layers", [])
        }
        if set(choice_layers) != set(proposal_layers):
            raise ValueError(
                f"Review unit {unit_id} does not contain the proposed layers"
            )
        applied_layers = []
        for layer_id in sorted(proposal_layers):
            proposed_events = [
                int(value)
                for value in proposal_layers[layer_id]
                .get("round_robin", {})
                .get("candidate_event_indices", [])
            ]
            selected = choice_layers[layer_id]
            primary = selected.get("primary_event_index")
            accepted_events = [
                int(value) for value in selected.get("accepted_event_indices", [])
            ]
            if not proposed_events:
                raise ValueError(
                    f"Accepted unit {unit_id}/{layer_id} has no isolated source candidates"
                )
            if primary is None:
                raise ValueError(
                    f"Accepted unit {unit_id}/{layer_id} needs a primary event"
                )
            primary = int(primary)
            if primary not in proposed_events:
                raise ValueError(
                    f"Primary event {primary} is not proposed for {unit_id}/{layer_id}"
                )
            if primary not in accepted_events:
                accepted_events.insert(0, primary)
            accepted_events = list(dict.fromkeys(accepted_events))
            if not set(accepted_events) <= set(proposed_events):
                raise ValueError(
                    f"Accepted events for {unit_id}/{layer_id} exceed the proposal"
                )
            ordered_events = [primary] + [
                value for value in accepted_events if value != primary
            ]
            applied_layers.append(
                {
                    "layer_id": layer_id,
                    "primary_event_index": primary,
                    "accepted_event_indices": ordered_events,
                    "source_event_count": int(proposal_layers[layer_id]["event_count"]),
                }
            )
        split = proposal.get("velocity_split")
        accepted.append(
            {
                "unit_id": unit_id,
                "pitch": pitch,
                "identity_candidate_cluster": str(
                    proposal["identity_candidate_cluster"]
                ),
                "articulation_cluster": str(proposal["articulation_cluster"]),
                "velocity_layers_applied": bool(
                    proposal.get("velocity_layer_candidate")
                ),
                "velocity_boundary": (
                    int(split["suggested_velocity_boundary"]) if split else None
                ),
                "layers": applied_layers,
            }
        )
    return accepted


def _variant_rows(
    base_rows: Sequence[dict[str, Any]],
    accepted: Sequence[dict[str, Any]],
    extracted: dict[int, dict[str, Any]],
    *,
    variant: int,
) -> list[dict[str, Any]]:
    accepted_by_pitch = {int(row["pitch"]): row for row in accepted}
    output = []
    for base in sorted(base_rows, key=lambda row: int(row["pitch"])):
        pitch = int(base["pitch"])
        unit = accepted_by_pitch.get(pitch)
        if unit is None:
            output.append(dict(base))
            continue
        boundary = unit.get("velocity_boundary")
        for layer_index, layer in enumerate(unit["layers"]):
            events = list(layer["accepted_event_indices"])
            chosen = events[variant % len(events)]
            row = dict(extracted[int(chosen)])
            row["low_key"] = int(base["low_key"])
            row["high_key"] = int(base["high_key"])
            if len(unit["layers"]) == 2 and boundary is not None:
                if layer_index == 0:
                    row["low_velocity"] = 0
                    row["high_velocity"] = int(boundary)
                else:
                    row["low_velocity"] = int(boundary) + 1
                    row["high_velocity"] = 127
            else:
                row["low_velocity"] = 0
                row["high_velocity"] = 127
            output.append(row)
    return output


def _v3_sfz_text(
    base_rows: Sequence[dict[str, Any]],
    accepted: Sequence[dict[str, Any]],
    extracted: dict[int, dict[str, Any]],
) -> str:
    accepted_by_pitch = {int(row["pitch"]): row for row in accepted}
    lines = [
        "// Sunofriend Sample Instrument v3 reviewed experiment",
        "// Velocity layers plus SFZ sequence round robin; source audio requires permission.",
        "<group> ampeg_attack=0.005 ampeg_release=0.15",
    ]
    for base in sorted(base_rows, key=lambda row: int(row["pitch"])):
        pitch = int(base["pitch"])
        unit = accepted_by_pitch.get(pitch)
        if unit is None:
            lines.append(_sfz_region(base))
            continue
        boundary = unit.get("velocity_boundary")
        for layer_index, layer in enumerate(unit["layers"]):
            events = list(layer["accepted_event_indices"])
            for sequence_index, event_index in enumerate(events, 1):
                row = {
                    **extracted[int(event_index)],
                    "low_key": int(base["low_key"]),
                    "high_key": int(base["high_key"]),
                    "low_velocity": (
                        0
                        if len(unit["layers"]) != 2 or layer_index == 0
                        else int(boundary) + 1
                    ),
                    "high_velocity": (
                        int(boundary)
                        if len(unit["layers"]) == 2 and layer_index == 0
                        else 127
                    ),
                }
                suffix = (
                    f" seq_length={len(events)} seq_position={sequence_index}"
                    if len(events) > 1
                    else ""
                )
                lines.append(_sfz_region(row) + suffix)
    return "\n".join(lines) + "\n"


def _sfz_region(row: dict[str, Any]) -> str:
    sample = str(row["file"]).replace("\\", "/")
    correction = int(row["tuning"]["pitch_correction_cents"])
    return (
        f"<region> sample={sample} pitch_keycenter={int(row['pitch'])} "
        f"lokey={int(row['low_key'])} hikey={int(row['high_key'])} "
        f"lovel={int(row['low_velocity'])} hivel={int(row['high_velocity'])} "
        f"tune={correction}"
    )


def _write_v3_soundfont(
    path: Path,
    rows: Sequence[dict[str, Any]],
    *,
    name: str,
    sample_root: Path | None = None,
) -> dict[str, Any]:
    from .soundfont import SoundFontZone, write_soundfont

    summary = write_soundfont(
        path,
        [
            SoundFontZone(
                (sample_root or path.parent) / str(row["file"]),
                root_key=int(row["pitch"]),
                low_key=int(row["low_key"]),
                high_key=int(row["high_key"]),
                low_velocity=int(row["low_velocity"]),
                high_velocity=int(row["high_velocity"]),
                pitch_correction_cents=int(row["tuning"]["pitch_correction_cents"]),
            )
            for row in rows
        ],
        name=name,
        software="Sunofriend Sample Instrument v3",
    ).to_dict()
    return summary


def _write_preset(
    soundfont: Path, preset: Path, final_soundfont: Path
) -> dict[str, Any] | None:
    try:
        from .ausampler import AUSamplerPresetError, write_ausampler_preset

        return write_ausampler_preset(
            soundfont,
            preset,
            referenced_soundfont_path=final_soundfont,
        )
    except AUSamplerPresetError:
        return None


def _write_performance_audition(
    source_midi: Path,
    path: Path,
    *,
    track_index: int,
    kind: str,
) -> dict[str, Any]:
    from .clip import (
        ClipNote,
        Instrument,
        MidiClip,
        Provenance,
        TempoMap,
        TempoPoint,
        read_midi_clips,
        write_clip_midi,
    )

    clips = read_midi_clips(source_midi)
    if not clips:
        raise ValueError("Performance audition source MIDI contains no notes")
    if not 0 <= track_index < len(clips):
        raise ValueError(
            f"Performance audition track index must be from 0 to {len(clips) - 1}"
        )
    clip = clips[track_index]
    start_beat, end_beat, bars, selected = _performance_window(clip)
    tempo_points = [
        TempoPoint(0.0, clip.tempo_map.bpm_at(start_beat)),
        *(
            TempoPoint(point.beat - start_beat, point.bpm)
            for point in clip.tempo_map.tempo_points
            if start_beat < point.beat < end_beat
        ),
    ]
    excerpt_notes = tuple(
        ClipNote(
            start_beat=note.start_beat - start_beat,
            duration_beats=min(note.end_beat, end_beat) - note.start_beat,
            pitch=note.pitch,
            velocity=note.velocity,
            source_start_seconds=note.source_start_seconds,
            source_end_seconds=note.source_end_seconds,
            microtiming_seconds=note.microtiming_seconds,
            end_microtiming_seconds=note.end_microtiming_seconds,
            release_velocity=note.release_velocity,
            articulation=note.articulation,
        )
        for note in selected
    )
    digest = hashlib.sha256(
        (
            f"{_file_sha256(source_midi)}:{track_index}:"
            f"{start_beat:.9f}:{end_beat:.9f}:channel-0"
        ).encode("utf-8")
    ).hexdigest()
    excerpt = MidiClip(
        title="Sample Instrument v3 performance A/B",
        tempo_map=TempoMap(tuple(tempo_points)),
        time_signature=clip.time_signature,
        instrument=Instrument(kind or clip.instrument.role, program=0, channel=0),
        notes=excerpt_notes,
        key=clip.key,
        provenance=Provenance(
            source_uri=str(source_midi.resolve()),
            converter="sunofriend.sample-performance-audition-v1",
            details={
                "source_track_index": track_index,
                "source_channel": clip.instrument.channel,
                "output_channel": 0,
                "source_start_beat": start_beat,
                "source_end_beat": end_beat,
                "selection_effect": "audition-only",
            },
        ),
        clip_id=digest,
    )
    write_clip_midi(path, excerpt, timing_mode="musical")
    selected_pitches = sorted({note.pitch for note in selected})
    source_pitches = sorted({note.pitch for note in clip.notes})
    velocities = [note.velocity for note in selected]
    return {
        "schema": "sunofriend.sample-performance-audition.v1",
        "selection_policy": (
            "shortest bar-aligned window in 8, 12 or 16 bars that covers every "
            "source pitch; otherwise maximum pitch coverage, then note density, "
            "then earliest window"
        ),
        "source_midi": str(source_midi.resolve()),
        "source_midi_sha256": _file_sha256(source_midi),
        "source_track_index": track_index,
        "source_track_title": clip.title,
        "source_channel": clip.instrument.channel,
        "output_channel": 0,
        "channel_change_reason": (
            "AUSampler custom SF2 presets use a melodic bank on MIDI channel 1; "
            "the source performance remains unchanged"
        ),
        "bars": bars,
        "beats_per_bar": (
            clip.time_signature.numerator * 4.0 / clip.time_signature.denominator
        ),
        "source_start_beat": round(start_beat, 6),
        "source_end_beat": round(end_beat, 6),
        "source_start_seconds": round(clip.tempo_map.musical_seconds_at(start_beat), 6),
        "source_end_seconds": round(clip.tempo_map.musical_seconds_at(end_beat), 6),
        "initial_bpm": round(excerpt.tempo_map.bpm, 3),
        "note_count": len(selected),
        "source_pitch_count": len(source_pitches),
        "selected_pitch_count": len(selected_pitches),
        "source_pitches": source_pitches,
        "selected_pitches": selected_pitches,
        "velocity_min": min(velocities),
        "velocity_max": max(velocities),
        "pitch_changes": 0,
        "velocity_changes": 0,
        "source_midi_mutated": False,
    }


def _performance_window(clip: Any) -> tuple[float, float, int, list[Any]]:
    if not clip.notes:
        raise ValueError("Performance audition source clip contains no notes")
    beats_per_bar = (
        clip.time_signature.numerator * 4.0 / clip.time_signature.denominator
    )
    first_bar = math.floor(min(note.start_beat for note in clip.notes) / beats_per_bar)
    last_bar = math.floor(max(note.start_beat for note in clip.notes) / beats_per_bar)
    source_pitch_count = len({note.pitch for note in clip.notes})
    longest_best = None
    for bars in (8, 12, 16):
        window_beats = bars * beats_per_bar
        best = None
        for bar in range(first_bar, last_bar + 1):
            start = bar * beats_per_bar
            end = start + window_beats
            notes = [note for note in clip.notes if start <= note.start_beat < end]
            if not notes:
                continue
            score = (len({note.pitch for note in notes}), len(notes), -start)
            row = (score, start, end, notes)
            if best is None or row[0] > best[0]:
                best = row
        if best is None:
            continue
        longest_best = (best[1], best[2], bars, best[3])
        if best[0][0] == source_pitch_count:
            return longest_best
    if longest_best is None:  # pragma: no cover - guarded by clip.notes
        raise ValueError("Could not select a performance audition window")
    return longest_best


def _write_velocity_sweep(
    path: Path,
    accepted: Sequence[dict[str, Any]],
    *,
    bpm: float,
) -> dict[str, Any] | None:
    from .midi import MidiTrack, write_midi_file
    from .models import NoteEvent

    layered = [
        unit
        for unit in accepted
        if bool(unit.get("velocity_layers_applied"))
        and len(unit.get("layers", [])) == 2
        and unit.get("velocity_boundary") is not None
    ]
    if not layered:
        return None
    notes = []
    units = []
    beat_seconds = 60.0 / bpm
    beat_cursor = 0.0
    for unit in sorted(layered, key=lambda row: int(row["pitch"])):
        pitch = int(unit["pitch"])
        boundary = int(unit["velocity_boundary"])
        velocities = _velocity_sweep_values(boundary)
        start_note_index = len(notes)
        for velocity in velocities:
            start = beat_cursor * beat_seconds
            notes.append(
                NoteEvent(
                    start=start,
                    end=start + 0.4 * beat_seconds,
                    pitch=pitch,
                    velocity=velocity,
                )
            )
            beat_cursor += 0.75
        units.append(
            {
                "unit_id": str(unit["unit_id"]),
                "pitch": pitch,
                "accepted_boundary": boundary,
                "low_velocity_range": [0, boundary],
                "high_velocity_range": [boundary + 1, 127],
                "velocities": velocities,
                "transition_pair": [boundary, boundary + 1],
                "start_note_index": start_note_index,
                "note_count": len(velocities),
                "boundary_changed": False,
            }
        )
        beat_cursor += 1.25
    write_midi_file(
        path,
        [
            MidiTrack(
                "Sample Instrument v3 velocity sweep",
                channel=0,
                program=0,
                notes=notes,
            )
        ],
        bpm=bpm,
    )
    return {
        "schema": "sunofriend.sample-velocity-sweep.v1",
        "status": "audition-only",
        "selection_effect": "none",
        "mapping_changed": False,
        "source_samples_changed": False,
        "bpm": bpm,
        "output_channel": 0,
        "note_count": len(notes),
        "unit_count": len(units),
        "units": units,
    }


def _velocity_sweep_values(boundary: int) -> list[int]:
    values = {
        32,
        48,
        64,
        80,
        96,
        104,
        112,
        120,
        127,
        *(boundary + offset for offset in (-8, -4, -2, -1, 0, 1, 2, 4, 8)),
    }
    return sorted({max(1, min(127, int(value))) for value in values})


def _write_v3_audition(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    from .midi import MidiTrack, write_midi_file
    from .models import NoteEvent

    pairs = []
    for row in rows:
        velocity = (int(row["low_velocity"]) + int(row["high_velocity"])) // 2
        pairs.append((int(row["pitch"]), max(1, velocity)))
    notes = []
    for index, (pitch, velocity) in enumerate(sorted(set(pairs))):
        start = index * 0.75
        notes.append(NoteEvent(start, start + 0.5, pitch, velocity))
    write_midi_file(
        path,
        [MidiTrack("Sample Instrument v3 A/B", channel=0, program=0, notes=notes)],
        bpm=120.0,
    )


def _review_html(seed: dict[str, Any]) -> str:
    embedded = json.dumps(seed, sort_keys=True).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sunofriend sample instrument review</title>
<style>
:root {{ color-scheme: dark; font-family: system-ui, sans-serif; }}
body {{ margin: 0 auto; max-width: 1120px; padding: 32px; background: #101820; color: #eef4f8; }}
h1 {{ font-size: 2.4rem; margin-bottom: .3rem; }}
.summary,.unit {{ background:#192630; border:1px solid #3a5265; border-radius:16px; padding:20px; margin:18px 0; }}
.unit.accept {{ border-color:#2bc48a; }} .unit.reject {{ border-color:#ff6b6b; }}
.layer {{ background:#132029; border-radius:12px; padding:14px; margin:12px 0; }}
.event {{ display:grid; grid-template-columns:9rem minmax(320px,1fr) auto auto; gap:12px; align-items:center; margin:14px 0; }}
.auditions {{ display:grid; grid-template-columns:11rem minmax(260px,1fr); gap:8px 12px; align-items:center; }}
.audition-label {{ color:#b8cbd8; font-size:.9rem; }}
audio {{ width:100%; min-width:260px; }} button {{ padding:12px 18px; border-radius:10px; border:1px solid #76c7ff; background:#275d82; color:white; font-size:1rem; cursor:pointer; }}
select {{ padding:9px; border-radius:8px; font-size:1rem; }} code {{ color:#8ed8ff; }}
.warning {{ color:#ffd166; }} .actions {{ display:flex; gap:12px; flex-wrap:wrap; position:sticky; top:0; background:#101820ee; padding:14px 0; }}
</style>
</head>
<body>
<h1>Sunofriend Sample Instrument v3 review</h1>
<p>Listen to each exact isolated source event, its surrounding source rhythm, and its role-aware audition. Drum/percussion candidates use a repeated two-bar beat; pitched candidates use a short sampler pitch phrase. Accept only a unit that sounds useful and choose one primary per layer. Extra checked events become SFZ round-robin candidates and separate GarageBand A/B banks.</p>
<p>The isolated and role auditions are normalised to make timbre easier to compare. Source-context excerpts share one stem-level gain, so their original relative level and nearby bleed remain audible.</p>
<p class="warning">Nothing on this page changes the v2 instrument. The exported JSON must be explicitly reviewed before apply will run. If several units share a MIDI pitch, accept at most one of them.</p>
<div class="actions"><button id="mark">Mark all current choices reviewed</button><button id="export">Export review JSON</button><strong id="status">Unreviewed</strong></div>
<div class="summary">{seed["summary"]["review_unit_count"]} units; {seed["summary"]["velocity_layer_unit_count"]} possible velocity-layer units; {seed["summary"]["candidate_event_count"]} candidate events; {seed["summary"].get("context_audio_file_count", 0)} contextual auditions.</div>
<main id="units"></main>
<script>
const review = {embedded};
const root = document.getElementById('units');
function esc(value) {{ return String(value).replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c])); }}
function render() {{
  root.innerHTML = review.units.map((unit, ui) => `
    <section class="unit" data-ui="${{ui}}">
      <h2>${{esc(unit.unit_id)}} · MIDI ${{unit.pitch}}</h2>
      <p>${{unit.velocity_layer_candidate ? `Suggested velocity boundary: <code>${{unit.suggested_velocity_boundary}}</code>` : 'One source-level layer; alternate-sample review only.'}}</p>
      <label>Decision <select class="decision"><option value="unreviewed">Choose…</option><option value="accept">Accept reviewed sources</option><option value="reject">Reject proposal</option></select></label>
      ${{unit.layers.map((layer, li) => `
        <div class="layer" data-li="${{li}}"><h3>${{esc(layer.layer_id)}} · median ${{layer.median_rms_db}} dB</h3>
        ${{layer.event_options.map(event => `
          <div class="event"><span>Event ${{event.event_index}}<br>${{event.start_seconds.toFixed(3)}} s</span><div class="auditions"><span class="audition-label">Isolated one-shot</span><audio controls preload="none" src="${{esc(event.audio)}}"></audio>${{event.context_audio ? `<span class="audition-label">${{esc(event.context_audio.source_context.label)}}</span><audio controls preload="none" src="${{esc(event.context_audio.source_context.audio)}}"></audio><span class="audition-label">${{esc(event.context_audio.role_audition.label)}}</span><audio controls preload="none" src="${{esc(event.context_audio.role_audition.audio)}}"></audio>` : ''}}</div><label><input type="radio" name="primary-${{ui}}-${{li}}" value="${{event.event_index}}"> primary</label><label><input class="alternate" type="checkbox" value="${{event.event_index}}"> alternate</label></div>`).join('')}}
        </div>`).join('')}}
    </section>`).join('');
  root.querySelectorAll('.decision').forEach(select => select.addEventListener('change', e => {{ const card=e.target.closest('.unit'); card.classList.remove('accept','reject'); if(e.target.value !== 'unreviewed') card.classList.add(e.target.value); review.status='unreviewed'; document.getElementById('status').textContent='Unreviewed changes'; }}));
  root.querySelectorAll('input').forEach(input => input.addEventListener('change', () => {{ review.status='unreviewed'; document.getElementById('status').textContent='Unreviewed changes'; }}));
}}
function sync() {{
  review.units.forEach((unit, ui) => {{
    const card=root.querySelector(`[data-ui="${{ui}}"]`); unit.decision=card.querySelector('.decision').value;
    unit.layers.forEach((layer, li) => {{ const box=card.querySelector(`[data-li="${{li}}"]`); const primary=box.querySelector('input[type=radio]:checked'); layer.primary_event_index=primary ? Number(primary.value) : null; const extras=[...box.querySelectorAll('.alternate:checked')].map(x=>Number(x.value)); layer.accepted_event_indices=[...new Set([layer.primary_event_index, ...extras].filter(x=>x!==null))]; }});
  }});
  review.summary.accepted_unit_count=review.units.filter(x=>x.decision==='accept').length;
  review.summary.rejected_unit_count=review.units.filter(x=>x.decision==='reject').length;
}}
document.getElementById('mark').addEventListener('click', () => {{ sync(); const open=review.units.filter(x=>x.decision==='unreviewed'); if(open.length) {{ alert(`${{open.length}} unit(s) still need an explicit Accept or Reject decision.`); return; }} const missingPrimary=review.units.some(unit=>unit.decision==='accept' && unit.layers.some(layer=>layer.primary_event_index===null)); if(missingPrimary) {{ alert('Choose one primary source for every layer you accept.'); return; }} const pitches=review.units.filter(x=>x.decision==='accept').map(x=>x.pitch); const duplicate=pitches.find((pitch,index)=>pitches.indexOf(pitch)!==index); if(duplicate!==undefined) {{ alert(`Only one unit may be accepted for MIDI pitch ${{duplicate}}.`); return; }} review.status='reviewed'; document.getElementById('status').textContent=`Reviewed: ${{review.summary.accepted_unit_count}} accepted, ${{review.summary.rejected_unit_count}} rejected`; }});
document.getElementById('export').addEventListener('click', () => {{ sync(); if(review.status!=='reviewed') {{ alert('Use “Mark all current choices reviewed” after deciding every unit.'); return; }} const blob=new Blob([JSON.stringify(review,null,2)+'\\n'],{{type:'application/json'}}); const link=document.createElement('a'); link.href=URL.createObjectURL(blob); link.download='sample_pack_review.reviewed.json'; link.click(); setTimeout(()=>URL.revokeObjectURL(link.href),1000); }});
render();
</script>
</body>
</html>
"""


def _boundary_review_html(seed: dict[str, Any]) -> str:
    embedded = json.dumps(seed, sort_keys=True).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sunofriend velocity-layer mapping review</title>
<style>
:root {{ color-scheme: dark; font-family: system-ui, sans-serif; }}
body {{ margin:0 auto; max-width:1120px; padding:32px; background:#101820; color:#eef4f8; }}
h1 {{ font-size:2.4rem; margin-bottom:.3rem; }}
.summary,.unit,.tone {{ background:#192630; border:1px solid #3a5265; border-radius:16px; padding:20px; margin:18px 0; }}
.candidate {{ display:grid; grid-template-columns:18rem minmax(320px,1fr); gap:12px; align-items:center; background:#132029; border:1px solid #2b4050; border-radius:12px; padding:14px; margin:12px 0; }}
.candidate:has(input:checked) {{ border-color:#2bc48a; }}
.tone-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
.tone-card {{ background:#132029; border-radius:12px; padding:14px; }}
.current,.warning {{ color:#ffd166; }} .safe {{ color:#7fe0b3; }} audio {{ width:100%; }} code {{ color:#8ed8ff; }}
button {{ padding:12px 18px; border-radius:10px; border:1px solid #76c7ff; background:#275d82; color:white; font-size:1rem; cursor:pointer; }}
.actions {{ display:flex; gap:12px; flex-wrap:wrap; position:sticky; top:0; background:#101820ee; padding:14px 0; z-index:2; }}
a {{ color:#8ed8ff; }} small {{ line-height:1.4; }}
</style>
</head>
<body>
<h1>Sunofriend velocity-layer mapping review</h1>
<p>A convincing layer should sound like the same instrument played with a different strength. A little attack or brightness change can be natural; a new pitch, object or texture usually means one source sample should cover the whole velocity range.</p>
<p>First compare the two equal-velocity repeated beats. This separates sample identity from MIDI loudness. Then compare each complete velocity ramp and choose either one source for every velocity or a two-source boundary.</p>
<p class="warning">The current mapping is labelled but deliberately not selected. This page introduces no new sample and changes no source audio, notes or MIDI velocities.</p>
<div class="actions"><button id="mark">Mark all mapping choices reviewed</button><button id="export">Export mapping review JSON</button><strong id="status">Unreviewed</strong></div>
<div class="summary">{seed["summary"]["review_unit_count"]} layered unit(s); {seed["summary"]["candidate_count"]} candidate mapping(s).</div>
<main id="units"></main>
<script>
const review={embedded};
const root=document.getElementById('units');
function esc(value) {{ return String(value).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c])); }}
function render() {{
  root.innerHTML=review.units.map((unit,ui)=>`
    <section class="unit" data-ui="${{ui}}"><h2>${{esc(unit.unit_id)}} · MIDI ${{unit.pitch}}</h2>
    <p>Actual source-MIDI velocities for this key: <strong>${{unit.source_midi_velocity_range[0]}}–${{unit.source_midi_velocity_range[1]}}</strong> (${{unit.source_midi_velocities.join(', ')}}). MIDI ${{unit.pitch}} is a sampler mapping key; for percussion it is not proof of a stable musical pitch.</p>
    <div class="tone"><h3>1. Same velocity, same repeated beat: compare identity</h3><p>Both use velocity ${{unit.tone_comparison.velocity}} and identical timing. If these sound like different objects, prefer one of the single-source mappings.</p>
      <div class="tone-grid"><div class="tone-card"><strong>Lower event ${{unit.tone_comparison.lower_event_index}}</strong>${{unit.tone_comparison.lower_preview_wav?`<audio controls preload="none" src="${{esc(unit.tone_comparison.lower_preview_wav)}}"></audio>`:'<p>Preview not rendered.</p>'}}</div>
      <div class="tone-card"><strong>Upper event ${{unit.tone_comparison.upper_event_index}}</strong>${{unit.tone_comparison.upper_preview_wav?`<audio controls preload="none" src="${{esc(unit.tone_comparison.upper_preview_wav)}}"></audio>`:'<p>Preview not rendered.</p>'}}</div></div>
      <p><a href="${{esc(unit.tone_comparison.midi)}}">Open constant-velocity repeated-beat MIDI</a></p></div>
    <h3>2. Complete mapping: compare velocity response</h3>
    <p>Every row uses the same ramp: ${{unit.sweep_velocities.join(', ')}}. <a href="${{esc(unit.sweep_midi)}}">Open velocity-ramp MIDI</a></p>
    ${{unit.candidates.map(candidate=>`
      <label class="candidate"><span><input type="radio" name="mapping-${{ui}}" value="${{esc(candidate.mapping_id)}}"> <strong>${{esc(candidate.label)}}</strong><br><small>Active source event(s): ${{candidate.active_event_indices.join(', ')}}${{candidate.mode==='layered'?`<br>lower ${{candidate.low_velocity_range[0]}}–${{candidate.low_velocity_range[1]}} · upper ${{candidate.high_velocity_range[0]}}–${{candidate.high_velocity_range[1]}}`: '<br>one sample responds across 0–127'}}</small>${{candidate.is_current?'<br><span class="current">current v3 mapping</span>':''}}${{candidate.source_midi_warning?`<br><span class="warning">${{esc(candidate.source_midi_warning)}}</span>`:'<br><span class="safe">All intended mapping zones are reachable by the source MIDI.</span>'}}</span>
      ${{candidate.preview_wav?`<audio controls preload="none" src="${{esc(candidate.preview_wav)}}"></audio>`:`<span>Preview was not rendered. Use the shared MIDI with <a href="${{esc(candidate.ausampler_preset || candidate.soundfont)}}">this candidate bank</a>.</span>`}}</label>`).join('')}}
    </section>`).join('');
  root.querySelectorAll('input').forEach(input=>input.addEventListener('change',()=>{{ review.status='unreviewed'; document.getElementById('status').textContent='Unreviewed changes'; }}));
}}
function sync() {{
  review.units.forEach((unit,ui)=>{{ const selected=root.querySelector(`[data-ui="${{ui}}"] input:checked`); unit.selected_mapping_id=selected?selected.value:null; }});
  review.summary.reviewed_unit_count=review.units.filter(unit=>unit.selected_mapping_id!==null).length;
  review.effects.layer_mappings_changed=review.units.filter(unit=>unit.selected_mapping_id!==null && unit.selected_mapping_id!==unit.current_mapping_id).length;
  review.effects.boundaries_changed=review.units.filter(unit=>unit.selected_mapping_id?.startsWith('layered-') && unit.selected_mapping_id!==unit.current_mapping_id).length;
}}
document.getElementById('mark').addEventListener('click',()=>{{ sync(); const open=review.units.filter(unit=>unit.selected_mapping_id===null); if(open.length){{ alert(`${{open.length}} unit(s) still need one explicit mapping choice.`); return; }} review.status='reviewed'; document.getElementById('status').textContent=`Reviewed: ${{review.summary.reviewed_unit_count}} choice(s), ${{review.effects.layer_mappings_changed}} changed`; }});
document.getElementById('export').addEventListener('click',()=>{{ sync(); if(review.status!=='reviewed'){{ alert('Use “Mark all mapping choices reviewed” after choosing every unit.'); return; }} const blob=new Blob([JSON.stringify(review,null,2)+'\\n'],{{type:'application/json'}}); const link=document.createElement('a'); link.href=URL.createObjectURL(blob); link.download='sample_boundary_review.reviewed.json'; link.click(); setTimeout(()=>URL.revokeObjectURL(link.href),1000); }});
render();
</script>
</body>
</html>
"""


def _v3_readme(report: dict[str, Any]) -> str:
    effects = report["effects"]
    features = report["applied_features"]
    performance = report["performance_audition"]
    sweep = report.get("velocity_sweep")
    boundary_review = report.get("boundary_review")
    if features["velocity_layer_unit_count"]:
        main_description = (
            "This main v3 bank applies the accepted velocity layers and one "
            "reviewed primary per layer."
        )
    else:
        main_description = (
            "This main v3 bank applies the reviewed primary-sample replacement; "
            "no velocity layer was accepted."
        )
    if features["garageband_alternate_bank_count"]:
        alternate_step = """4. Load each preset in `garageband-alternates/` to compare accepted alternate
   source events. SF2/AUSampler does not switch them automatically.
5. Keep the version that works in the full song. Return to `baseline-v2/` at
   any time; no baseline file was mutated."""
    else:
        alternate_step = """4. Keep the version that works in the full song. Return to `baseline-v2/` at
   any time; no baseline file was mutated. No alternate bank was generated."""
    if features["round_robin_layer_count"]:
        sfz_description = (
            "The portable `sunofriend-instrument.sfz` uses true sequence round "
            "robin for accepted alternates in SFZ-compatible samplers."
        )
    else:
        sfz_description = (
            "No alternate source event was accepted, so the SFZ contains no "
            "round-robin sequence."
        )
    if sweep:
        sweep_units = "\n".join(
            f"- MIDI {unit['pitch']}: accepted boundary {unit['accepted_boundary']} "
            f"(transition {unit['transition_pair'][0]} → {unit['transition_pair'][1]})"
            for unit in sweep["units"]
        )
        sweep_section = f"""
## Velocity-layer transition A/B

`garageband-velocity-sweep.mid` plays each accepted layered pitch from quiet
to loud, with dense steps immediately below and above its reviewed boundary.
Compare `baseline-v2/garageband-velocity-sweep-v2.wav` with
`garageband-velocity-sweep-v3.wav`, then replay the MIDI while swapping the two
AUSampler presets. This is an audition only: no boundary or source sample was
changed.

{sweep_units}
"""
    else:
        sweep_section = ""
    if boundary_review:
        boundary_rows = "\n".join(
            f"- MIDI {row['pitch']} ({row['unit_id']}): "
            f"{_mapping_snapshot_label(row['before'])} → "
            f"{_mapping_snapshot_label(row['after'])} "
            f"({'changed' if row['changed'] else 'explicitly kept'})"
            for row in boundary_review["changes"]
        )
        boundary_section = f"""
## Explicit boundary decision

This bank was regenerated from a hash-pinned velocity-layer mapping review.
Only the listed accepted-event mapping(s) were eligible to change. No new
source event was introduced; source-sample audio, source MIDI notes and source
MIDI velocities were retained.

{boundary_rows}
"""
    else:
        boundary_section = ""
    return f"""# {report["instrument_name"]} — reviewed Sample Instrument v3

This is a separate, review-derived experiment. The original Sample Instrument
v2 is unchanged and copied into `baseline-v2/` for immediate rollback.

## GarageBand A/B

1. Drag `garageband-ab-audition.mid` into a Software Instrument track.
2. Load `baseline-v2/sunofriend-instrument-v2.aupreset` in Apple AUSampler and
   listen to the v2 baseline.
3. Load `sunofriend-instrument.aupreset` and replay the same MIDI.
   {main_description}
{alternate_step}

{sfz_description}

## Musical performance A/B

`garageband-performance-ab.mid` is a {performance["bars"]}-bar excerpt from the
real source MIDI, selected for pitch coverage and note density. It contains
{performance["note_count"]} notes across {performance["selected_pitch_count"]}
of {performance["source_pitch_count"]} source pitches, beginning at source beat
{performance["source_start_beat"]} ({performance["source_start_seconds"]} s).
The excerpt is shifted to bar 1 and routed to MIDI channel 1 so AUSampler can
play the custom melodic-bank SF2. Pitches, velocities and rhythm are unchanged.

First hear `garageband-performance-source.wav`, the normalised source-stem
excerpt with its internal dynamics intact. Then use the same preset swap
described above. When previews were requested, compare
`baseline-v2/garageband-performance-v2.wav` with
`garageband-performance-v3.wav` before judging the instrument in the full song.
{sweep_section}
{boundary_section}

## Audit

- Reviewed units applied: {report["review"]["accepted_unit_count"]}
- Source events extracted: {effects["accepted_source_events_added"]}
- Velocity-layer units: {features["velocity_layer_unit_count"]}
- Round-robin layers: {features["round_robin_layer_count"]}
- GarageBand alternate banks: {features["garageband_alternate_bank_count"]}
- SF2 zones: {effects["soundfont_zone_count_before"]} → {effects["soundfont_zone_count_after"]}
- Baseline files changed: {effects["baseline_files_changed"]}
- MIDI notes/velocities changed: {effects["midi_notes_changed"]}/{effects["midi_velocities_changed"]}
- Performance excerpt pitch/velocity changes: {performance["pitch_changes"]}/{performance["velocity_changes"]}
- Source performance MIDI mutated: {performance["source_midi_mutated"]}
- Review SHA-256: `{report["review"]["sha256"]}`
{f'- Boundary review SHA-256: `{boundary_review["sha256"]}`' if boundary_review else ''}

Bleed, effects, room sound and phrase transitions can still be embedded in an
accepted event. Judge every bank in the song, not from the evidence score.
"""


def _verify_review_sources(record: dict[str, Any]) -> None:
    checks = (
        ("report", "report_sha256"),
        ("dynamics", "dynamics_sha256"),
        ("clusters", "clusters_sha256"),
        ("stem", "stem_sha256"),
        ("midi", "midi_sha256"),
        ("baseline_soundfont", "baseline_soundfont_sha256"),
    )
    for path_key, hash_key in checks:
        path = Path(str(record.get(path_key, ""))).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"Reviewed source artifact not found: {path}")
        if _file_sha256(path) != record.get(hash_key):
            raise ValueError(f"Reviewed source artifact changed: {path}")
    baseline_samples = list(record.get("baseline_samples") or [])
    if not baseline_samples:
        raise ValueError("Reviewed source record contains no pinned baseline samples")
    for row in baseline_samples:
        path = Path(str(row.get("path", ""))).expanduser().resolve()
        if not path.is_file() or _file_sha256(path) != row.get("sha256"):
            raise ValueError(f"Reviewed baseline sample changed: {path}")


def _verify_review_audio(review: dict[str, Any]) -> None:
    evidence = review.get("review_evidence") or {}
    directory = Path(str(evidence.get("directory", ""))).expanduser().resolve()
    manifest_path = Path(str(evidence.get("manifest", ""))).expanduser().resolve()
    if not manifest_path.is_file() or _file_sha256(manifest_path) != evidence.get(
        "manifest_sha256"
    ):
        raise ValueError(f"Reviewed event-audio manifest changed: {manifest_path}")
    manifest = _read_json(manifest_path)
    if manifest.get("schema") != "sunofriend.sample-review-audio-manifest.v1":
        raise ValueError("Unsupported review-audio manifest")
    files = list(manifest.get("files") or [])
    manifest_paths = [str(row.get("path", "")) for row in files]
    if len(set(manifest_paths)) != len(manifest_paths):
        raise ValueError("Reviewed event-audio manifest contains duplicate paths")
    for row in files:
        path = directory / str(row.get("path", ""))
        if not path.is_file() or _file_sha256(path) != row.get("sha256"):
            raise ValueError(f"Reviewed event audio changed: {path}")
    if len(files) != int(evidence.get("audio_file_count", -1)):
        raise ValueError(
            "Reviewed event-audio count does not match its pinned evidence"
        )
    referenced_paths = set()
    for unit in review.get("units", []):
        for layer in unit.get("layers", []):
            for option in layer.get("event_options", []):
                if option.get("audio"):
                    referenced_paths.add(str(option["audio"]))
                context = option.get("context_audio") or {}
                for name in ("source_context", "role_audition"):
                    record = context.get(name) or {}
                    if record.get("audio"):
                        referenced_paths.add(str(record["audio"]))
    if referenced_paths != set(manifest_paths):
        raise ValueError(
            "Reviewed page audio references do not match the pinned manifest"
        )


def _verify_source_evidence(dynamics: dict[str, Any]) -> None:
    for name in ("source", "midi"):
        record = dynamics.get(name) or {}
        path = Path(str(record.get("path", ""))).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"Dynamics {name} artifact not found: {path}")
        if _file_sha256(path) != record.get("sha256"):
            raise ValueError(f"Dynamics {name} artifact hash mismatch: {path}")


def _rms_db(event: dict[str, Any]) -> float:
    return round(20.0 * math.log10(max(float(event["rms"]), 1e-12)), 3)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


__all__ = [
    "SAMPLE_BOUNDARY_REVIEW_SCHEMA",
    "SAMPLE_PACK_REVIEW_SCHEMA",
    "SAMPLE_PACK_V3_SCHEMA",
    "apply_sample_boundary_review",
    "apply_sample_pack_review",
    "create_sample_boundary_review",
    "create_sample_pack_review",
]
