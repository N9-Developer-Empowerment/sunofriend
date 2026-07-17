"""Evidence-based instrument matching and stem-derived sample packs.

The matcher has two deliberately separate evidence paths:

* installed GarageBand/Logic sample assets are compared with isolated,
  MIDI-aligned snippets from the source stem; and
* General MIDI programs are rendered with the configured FluidSynth
  SoundFont and compared with the complete, aligned stem performance.

Neither score claims access to GarageBand's private patch renderer. The result
is an audition shortlist with explicit evidence, not an automatic artistic
decision.
"""

from __future__ import annotations

import html
import hashlib
import json
import math
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Sequence

from .instrument_catalog import (
    GM_PROGRAM_NAMES,
    FactoryAsset,
    discover_factory_assets,
    inventory_instruments,
    program_candidates,
    role_name_fit,
)


FEATURE_NAMES: tuple[str, ...] = (
    "mfcc_1",
    "mfcc_2",
    "mfcc_3",
    "mfcc_4",
    "mfcc_5",
    "mfcc_6",
    "mfcc_7",
    "mfcc_8",
    "mfcc_9",
    "mfcc_10",
    "mfcc_11",
    "mfcc_12",
    "brightness",
    "bandwidth",
    "rolloff",
    "flatness_log",
    "zero_crossing",
    "attack_ratio",
    "decay_ratio",
    "crest_log",
)
DRUM_KINDS = frozenset(
    {"kick", "snare", "hat", "cymbals", "toms", "other_kit", "drums"}
)


@dataclass(frozen=True)
class FactoryInstrumentMatch:
    rank: int
    asset_name: str
    asset_source: str
    asset_root: str
    audio_similarity: float
    role_name_prior: float
    combined_score: float
    comparison: tuple[str, ...]
    profiled_sample_count: int
    representative_sample_files: tuple[str, ...]
    timbre_profile: tuple[float, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["timbre_profile"] = _named_profile(self.timbre_profile)
        return value


@dataclass(frozen=True)
class GmProgramMatch:
    rank: int
    program: int
    patch_number: int
    name: str
    combined_score: float
    spectral_shape_similarity: float
    dynamics_similarity: float
    attack_similarity: float
    midi: str | None = None
    preview_wav: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LearnedGmProgramMatch:
    rank: int
    program: int
    patch_number: int
    name: str
    embedding_similarity: float
    active_window_count: int
    p10_similarity: float
    p90_similarity: float
    midi: str | None = None
    preview_wav: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _SelectedSegment:
    note_index: int
    start_seconds: float
    end_seconds: float
    pitch: int
    velocity: int
    isolated: bool
    overlap_count: int
    rms: float
    samples: Any

    def evidence_dict(self) -> dict[str, Any]:
        return {
            "note_index": self.note_index,
            "start_seconds": round(self.start_seconds, 6),
            "end_seconds": round(self.end_seconds, 6),
            "pitch": self.pitch,
            "velocity": self.velocity,
            "isolated": self.isolated,
            "overlap_count": self.overlap_count,
            "rms": round(self.rms, 8),
        }


@dataclass(frozen=True)
class _PerformanceFingerprint:
    mel_shape: Any
    rms: Any
    onset: Any


def match_instruments(
    stem_path: str | Path,
    midi_path: str | Path,
    *,
    kind: str,
    out_dir: str | Path,
    top: int = 5,
    track_index: int | None = None,
    garageband_sampler_root: str | Path | None = None,
    logic_drum_root: str | Path | None = None,
    include_factory: bool = True,
    include_gm: bool = True,
    all_programs: bool = False,
    max_source_segments: int = 24,
    max_samples_per_asset: int = 8,
    embedding_model_path: str | Path | None = None,
) -> dict[str, Any]:
    """Rank installed factory assets and rendered GM proxies for one stem.

    The MIDI must still be aligned with the untreated source stem. A tempo- or
    downbeat-transformed copy should be compared with equivalently transformed
    audio, not the original stem.
    """

    stem = Path(stem_path).expanduser()
    midi = Path(midi_path).expanduser()
    destination = Path(out_dir).expanduser()
    normalized_kind = kind.strip().lower()
    if not stem.is_file():
        raise ValueError(f"Stem WAV not found: {stem}")
    if not midi.is_file():
        raise ValueError(f"MIDI file not found: {midi}")
    if top <= 0:
        raise ValueError("top must be positive")
    if max_source_segments <= 0 or max_samples_per_asset <= 0:
        raise ValueError("segment and sample limits must be positive")
    if destination.exists():
        raise ValueError(f"Output directory already exists: {destination}")

    clip, available_tracks, selected_track_index = _select_clip(midi, track_index)
    embedding_model = None
    if embedding_model_path is not None:
        from .instrument_embedding import OpenL3MusicEmbedding

        embedding_model = OpenL3MusicEmbedding(embedding_model_path)
    audio, sample_rate = _load_audio(stem, target_sample_rate=22_050)
    segments, selection_warning = _select_source_segments(
        audio,
        sample_rate,
        clip.notes,
        kind=normalized_kind,
        limit=max_source_segments,
        allow_polyphonic=True,
    )
    if not segments:
        raise ValueError("No audible MIDI-aligned source segments were found")
    source_vectors = [
        _timbre_vector(segment.samples, sample_rate) for segment in segments
    ]
    source_profile = _median_vector(source_vectors)
    target_pitch = _median([segment.pitch for segment in segments])
    from .instrument_cluster import (
        cluster_source_events,
        source_event_clusters_svg,
    )

    cluster_audio, cluster_sample_rate = _load_audio(stem, target_sample_rate=None)
    cluster_limit = (
        min(max(len(clip.notes), max_source_segments), 512)
        if normalized_kind in DRUM_KINDS
        else max_source_segments
    )
    cluster_segments, _ = _select_source_segments(
        cluster_audio,
        cluster_sample_rate,
        clip.notes,
        kind=normalized_kind,
        limit=cluster_limit,
        allow_polyphonic=True,
    )
    if cluster_segments:
        cluster_vectors = [
            _timbre_vector(segment.samples, cluster_sample_rate)
            for segment in cluster_segments
        ]
    else:
        cluster_segments = segments
        cluster_vectors = source_vectors
        cluster_sample_rate = sample_rate
    source_event_clusters = cluster_source_events(
        cluster_segments,
        cluster_vectors,
        sample_rate=cluster_sample_rate,
        source_path=stem,
        midi_path=midi,
        feature_names=FEATURE_NAMES,
        embedding_model=embedding_model,
    )
    from .instrument_dynamics import (
        analyze_source_event_dynamics,
        source_event_dynamics_svg,
    )

    source_event_dynamics = analyze_source_event_dynamics(source_event_clusters)

    destination.parent.mkdir(parents=True, exist_ok=True)
    work = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.building-", dir=destination.parent
        )
    )
    warnings: list[str] = []
    if selection_warning:
        warnings.append(selection_warning)
    try:
        factory_matches: list[FactoryInstrumentMatch] = []
        factory_profiles: list[
            tuple[FactoryAsset, tuple[float, ...], tuple[str, ...]]
        ] = []
        if include_factory:
            assets = discover_factory_assets(
                normalized_kind,
                garageband_sampler_root=garageband_sampler_root,
                logic_drum_root=logic_drum_root,
            )
            for asset in assets:
                selected_files = _select_asset_samples(
                    asset,
                    target_pitch=target_pitch,
                    limit=max_samples_per_asset,
                )
                vectors: list[tuple[float, ...]] = []
                usable_files: list[str] = []
                for sample in selected_files:
                    try:
                        values, asset_rate = _load_audio(
                            sample,
                            target_sample_rate=22_050,
                            max_seconds=3.0,
                        )
                        vectors.append(_timbre_vector(values, asset_rate))
                        usable_files.append(str(sample))
                    except (OSError, RuntimeError, ValueError):
                        continue
                if vectors:
                    factory_profiles.append(
                        (asset, _median_vector(vectors), tuple(usable_files))
                    )
            factory_matches = _rank_factory_profiles(
                source_profile,
                factory_profiles,
                kind=normalized_kind,
                top=top,
            )
            if not factory_matches:
                warnings.append(
                    "No readable installed GarageBand/Logic factory samples matched this role."
                )

        gm_matches: list[GmProgramMatch] = []
        learned_gm_matches: list[LearnedGmProgramMatch] = []
        embedding_evidence: dict[str, Any] | None = None
        drum_family_mapping: dict[str, Any] | None = None
        if (
            include_gm
            and normalized_kind not in DRUM_KINDS
            and clip.instrument.channel != 9
        ):
            try:
                gm_matches, learned_gm_matches, embedding_evidence = _rank_gm_programs(
                    stem_audio=audio,
                    stem_path=stem,
                    sample_rate=sample_rate,
                    clip=clip,
                    programs=program_candidates(
                        normalized_kind, all_programs=all_programs
                    ),
                    top=top,
                    work_dir=work,
                    embedding_model=embedding_model,
                )
            except Exception as exc:
                if embedding_model is not None:
                    raise
                warnings.append(
                    f"Rendered GM audition unavailable: {type(exc).__name__}: {exc}"
                )
        elif include_gm and normalized_kind in DRUM_KINDS:
            try:
                drum_family_mapping = _build_gm_drum_family_mapping(
                    stem_path=stem,
                    midi_path=midi,
                    clip=clip,
                    kind=normalized_kind,
                    source_event_clusters=source_event_clusters,
                    source_vectors=cluster_vectors,
                    sample_rate=cluster_sample_rate,
                    work_dir=work,
                )
            except Exception as exc:
                warnings.append(
                    f"GM drum-family proposal unavailable: {type(exc).__name__}: {exc}"
                )

        inventory = inventory_instruments(
            garageband_sampler_root=garageband_sampler_root,
            logic_drum_root=logic_drum_root,
        )
        report: dict[str, Any] = {
            "operation": "instrument-match",
            "status": (
                "complete"
                if factory_matches or gm_matches or drum_family_mapping
                else "no-match"
            ),
            "stem": str(stem.resolve()),
            "midi": str(midi.resolve()),
            "kind": normalized_kind,
            "track": {
                "selected_index": selected_track_index,
                "selected_title": clip.title,
                "available_titles": available_tracks,
                "note_count": len(clip.notes),
                "midi_program": clip.instrument.program,
                "midi_channel": clip.instrument.channel,
            },
            "source_evidence": {
                "sample_rate": sample_rate,
                "segments_used": len(segments),
                "isolated_segments": sum(segment.isolated for segment in segments),
                "median_midi_pitch": round(target_pitch, 3),
                "segments": [segment.evidence_dict() for segment in segments],
                "timbre_profile": _named_profile(source_profile),
                "event_clusters": source_event_clusters["summary"],
                "event_dynamics": source_event_dynamics["summary"],
            },
            "garageband_factory_matches": [
                _factory_match_dict(match, inventory.sampler_instrument_presets)
                for match in factory_matches
            ],
            "gm_rendered_matches": [match.to_dict() for match in gm_matches],
            "gm_learned_embedding_matches": [
                match.to_dict() for match in learned_gm_matches
            ],
            "gm_drum_family_mapping": (
                drum_family_mapping["summary"]
                if drum_family_mapping is not None
                else None
            ),
            "installed_audio_unit_instruments": [
                item.to_dict() for item in inventory.audio_unit_instruments
            ],
            "garageband": {
                "installed": inventory.garageband_installed,
                "version": inventory.garageband_version,
                "factory_sampler_asset_count": len(inventory.factory_sampler_assets),
                "drum_kit_asset_count": len(inventory.drum_kit_assets),
                "sampler_instrument_preset_count": len(
                    inventory.sampler_instrument_presets
                ),
            },
            "method": {
                "factory_assets": (
                    "MIDI-aligned source snippets are compared with installed factory "
                    "sample recordings. Audio similarity contributes 92% of the score; "
                    "a weak role/name prior contributes 8%."
                ),
                "gm_programs": (
                    "The complete MIDI performance is rendered through each candidate "
                    "General MIDI program. Aligned log-mel spectral shape contributes "
                    "70%, dynamics 15%, and attack envelope 15%."
                ),
                "gm_drum_notes": (
                    "For drum roles, each source-event timbre-family/existing-note "
                    "mapping unit is compared with role-appropriate GM channel-10 "
                    "one-shots. A separate review MIDI uses distinct notes where "
                    "guardrails permit; the supplied MIDI is never overwritten."
                    if drum_family_mapping is not None
                    else "Not available or not applicable to this role."
                ),
                "learned_embeddings": (
                    "When explicitly enabled, the same aligned source and rendered-GM "
                    "one-second windows are compared with a hash-pinned OpenL3 music "
                    "embedding. This creates a separate advisory ranking and never "
                    "changes the explainable GM score or order."
                    if embedding_evidence is not None
                    else (
                        "The explicitly supplied OpenL3 model contributed to source-event "
                        "timbre clustering only; learned GM ranking was unavailable or "
                        "disabled for this role."
                        if embedding_model is not None
                        else "Not requested; no learned model was loaded."
                    )
                ),
                "source_event_clusters": (
                    "Every MIDI-aligned source excerpt is grouped independently by "
                    "candidate timbre family and articulation shape. Robust outliers "
                    "are retained for review; no note, rank or sample selection changes."
                ),
                "source_event_dynamics": (
                    "Repeated events within the same timbre family, MIDI pitch "
                    "and articulation are checked for conservative source-RMS "
                    "layers and isolated alternate-sample candidates. Results "
                    "are advisory and do not change MIDI, samples or mappings."
                ),
                "ranking_scope": (
                    "Exploratory shortlist for audition, not proof that a patch is the "
                    "original instrument or an automatic production choice."
                ),
            },
            "warnings": [*inventory.warnings, *warnings],
            "garageband_handoff": [
                "Keep the GarageBand project at the MIDI's existing BPM and timeline origin.",
                "Search the Library for the top factory asset names; patch names can differ from sample asset names.",
                "Use the rendered GM results as timbral-family evidence, then choose the closest GarageBand or Audio Unit patch by ear.",
                *(
                    [
                        "Compare drum_family_mapping.proposed.mid and its WAV with the supplied MIDI; accept or edit the separated channel-10 notes only after auditioning the intended GarageBand kit."
                    ]
                    if drum_family_mapping is not None
                    else []
                ),
                "Audition at song level: an isolated timbre match can still occupy the wrong emotional or spectral space in the mix.",
            ],
            "artifacts": {
                "report": "instrument_matches.json",
                "audition_guide": "GARAGEBAND_AUDITION.md",
                "profile_graph": ("timbre_profiles.svg" if factory_matches else None),
                "embedding_evidence": (
                    "openl3_embedding_evidence.json"
                    if embedding_evidence is not None
                    else None
                ),
                "source_event_clusters": "source_event_clusters.json",
                "source_event_clusters_graph": "source_event_clusters.svg",
                "source_event_dynamics": "source_event_dynamics.json",
                "source_event_dynamics_graph": "source_event_dynamics.svg",
                "gm_drum_family_mapping": (
                    "gm_drum_family_mapping.json"
                    if drum_family_mapping is not None
                    else None
                ),
                "gm_drum_family_proposed_midi": (
                    "drum_family_mapping.proposed.mid"
                    if drum_family_mapping is not None
                    else None
                ),
                "gm_drum_family_proposed_wav": (
                    "drum_family_mapping.proposed.wav"
                    if drum_family_mapping is not None
                    else None
                ),
            },
        }
        _write_json(work / "source_event_clusters.json", source_event_clusters)
        (work / "source_event_clusters.svg").write_text(
            source_event_clusters_svg(source_event_clusters), encoding="utf-8"
        )
        _write_json(work / "source_event_dynamics.json", source_event_dynamics)
        (work / "source_event_dynamics.svg").write_text(
            source_event_dynamics_svg(source_event_dynamics), encoding="utf-8"
        )
        if embedding_evidence is not None:
            _write_json(work / "openl3_embedding_evidence.json", embedding_evidence)
        _write_json(work / "instrument_matches.json", report)
        (work / "GARAGEBAND_AUDITION.md").write_text(
            _audition_markdown(report), encoding="utf-8"
        )
        if factory_matches:
            (work / "timbre_profiles.svg").write_text(
                _profile_svg(source_profile, factory_matches[:3]),
                encoding="utf-8",
            )
        work.rename(destination)
        report["report"] = str(destination / "instrument_matches.json")
        report["audition_guide"] = str(destination / "GARAGEBAND_AUDITION.md")
        if factory_matches:
            report["profile_graph"] = str(destination / "timbre_profiles.svg")
        if embedding_evidence is not None:
            report["embedding_evidence"] = str(
                destination / "openl3_embedding_evidence.json"
            )
        report["source_event_clusters"] = str(
            destination / "source_event_clusters.json"
        )
        report["source_event_clusters_graph"] = str(
            destination / "source_event_clusters.svg"
        )
        report["source_event_dynamics"] = str(
            destination / "source_event_dynamics.json"
        )
        report["source_event_dynamics_graph"] = str(
            destination / "source_event_dynamics.svg"
        )
        if drum_family_mapping is not None:
            report["gm_drum_family_mapping_report"] = str(
                destination / "gm_drum_family_mapping.json"
            )
            report["gm_drum_family_proposed_midi"] = str(
                destination / "drum_family_mapping.proposed.mid"
            )
            report["gm_drum_family_proposed_wav"] = str(
                destination / "drum_family_mapping.proposed.wav"
            )
        return report
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


def build_sample_pack(
    stem_path: str | Path,
    midi_path: str | Path,
    *,
    kind: str,
    out_dir: str | Path,
    track_index: int | None = None,
    max_samples: int = 12,
    tail_ms: float = 120.0,
    allow_polyphonic: bool = False,
    instrument_name: str | None = None,
    render_preview: bool = True,
    max_transpose: int = 6,
    auto_tune: bool = True,
    embedding_model_path: str | Path | None = None,
) -> dict[str, Any]:
    """Extract samples and create a self-contained GarageBand-ready SF2 bank."""

    stem = Path(stem_path).expanduser()
    midi = Path(midi_path).expanduser()
    destination = Path(out_dir).expanduser()
    normalized_kind = kind.strip().lower()
    if not stem.is_file():
        raise ValueError(f"Stem WAV not found: {stem}")
    if not midi.is_file():
        raise ValueError(f"MIDI file not found: {midi}")
    if destination.exists():
        raise ValueError(f"Output directory already exists: {destination}")
    if max_samples <= 0:
        raise ValueError("max_samples must be positive")
    if tail_ms < 0 or not math.isfinite(tail_ms):
        raise ValueError("tail_ms must be finite and non-negative")
    if not isinstance(max_transpose, int) or not 0 <= max_transpose <= 24:
        raise ValueError("max_transpose must be an integer from 0 to 24")

    clip, available_tracks, selected_track_index = _select_clip(midi, track_index)
    embedding_model = None
    if embedding_model_path is not None:
        from .instrument_embedding import OpenL3MusicEmbedding

        embedding_model = OpenL3MusicEmbedding(embedding_model_path)
    audio, sample_rate = _load_audio(stem, target_sample_rate=None)
    segments, selection_warning = _select_source_segments(
        audio,
        sample_rate,
        clip.notes,
        kind=normalized_kind,
        limit=max(max_samples * 4, max_samples),
        tail_seconds=tail_ms / 1000.0,
        allow_polyphonic=allow_polyphonic,
    )
    if not segments:
        qualifier = "isolated " if not allow_polyphonic else ""
        raise ValueError(f"No audible {qualifier}MIDI-aligned samples were found")
    chosen = _choose_sample_pack_segments(
        segments, kind=normalized_kind, limit=max_samples
    )
    cluster_vectors = [
        _timbre_vector(segment.samples, sample_rate) for segment in segments
    ]
    from .instrument_cluster import (
        cluster_source_events,
        source_event_clusters_svg,
    )

    source_event_clusters = cluster_source_events(
        segments,
        cluster_vectors,
        sample_rate=sample_rate,
        source_path=stem,
        midi_path=midi,
        feature_names=FEATURE_NAMES,
        embedding_model=embedding_model,
        selected_note_indices=[segment.note_index for segment in chosen],
    )
    from .instrument_dynamics import (
        analyze_source_event_dynamics,
        source_event_dynamics_svg,
    )

    source_event_dynamics = analyze_source_event_dynamics(source_event_clusters)

    destination.parent.mkdir(parents=True, exist_ok=True)
    work = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.building-", dir=destination.parent
        )
    )
    try:
        samples_dir = work / "samples"
        samples_dir.mkdir()
        rows: list[dict[str, Any]] = []
        for index, segment in enumerate(sorted(chosen, key=lambda item: item.pitch), 1):
            filename = (
                f"{index:02d}-midi-{segment.pitch:03d}-"
                f"{segment.start_seconds:010.3f}s.wav"
            )
            output = samples_dir / filename
            values = _fade_and_normalize(segment.samples, sample_rate)
            _write_wav(output, values, sample_rate)
            row = segment.evidence_dict()
            row["file"] = str(Path("samples") / filename)
            row["tuning"] = _estimate_sample_tuning(
                values,
                sample_rate,
                segment.pitch,
                enabled=auto_tune and normalized_kind not in DRUM_KINDS,
            )
            rows.append(row)

        is_drums = normalized_kind in DRUM_KINDS
        rows = _with_zone_ranges(
            rows,
            drums=is_drums,
            max_transpose=max_transpose,
        )
        from .instrument_loops import (
            analyze_sample_loop_suggestions,
            sample_loop_suggestions_svg,
        )

        sample_loop_suggestions = analyze_sample_loop_suggestions(
            work,
            rows,
            kind=normalized_kind,
        )
        sfz = _sfz_text(rows)
        (work / "sunofriend-instrument.sfz").write_text(sfz, encoding="utf-8")

        from .soundfont import SoundFontZone, write_soundfont

        sf2_path = work / "sunofriend-instrument.sf2"
        soundfont_summary = write_soundfont(
            sf2_path,
            [
                SoundFontZone(
                    work / str(row["file"]),
                    root_key=int(row["pitch"]),
                    low_key=int(row["low_key"]),
                    high_key=int(row["high_key"]),
                    low_velocity=int(row["low_velocity"]),
                    high_velocity=int(row["high_velocity"]),
                    pitch_correction_cents=int(row["tuning"]["pitch_correction_cents"]),
                )
                for row in rows
            ],
            name=instrument_name or clip.title or normalized_kind.title(),
        ).to_dict()
        soundfont_summary["path"] = "sunofriend-instrument.sf2"

        ausampler_preset = None
        ausampler_preset_warning = None
        try:
            from .ausampler import AUSamplerPresetError, write_ausampler_preset

            ausampler_preset = write_ausampler_preset(
                sf2_path,
                work / "sunofriend-instrument.aupreset",
                referenced_soundfont_path=(
                    destination.resolve() / "sunofriend-instrument.sf2"
                ),
            )
        except AUSamplerPresetError as exc:
            ausampler_preset_warning = str(exc)

        audition_midi = work / "garageband-audition.mid"
        _write_sample_pack_audition(audition_midi, rows)
        audition_wav = work / "garageband-audition.wav"
        if render_preview:
            from .render import render_midi_to_wav

            render_midi_to_wav(
                audition_midi,
                audition_wav,
                soundfont_path=sf2_path,
            )
        warnings = [
            "Separator bleed, room sound, effects, vibrato, and note transitions in the stem become part of every extracted sample.",
            "The .aupreset is GarageBand's selectable wrapper; the referenced SF2 contains the samples and mapping. The SFZ remains an alternative for compatible third-party sampler Audio Units.",
            "Use only stems and recordings you own or have permission to sample.",
            "Sample Instrument v2 remains unlooped. For pitched samples, source_sample_loops.json and its raw-repeat auditions provide advisory boundaries that require listening before any later loop is applied.",
            "SoundFont stores embedded samples as mono PCM16 for broad sampler compatibility; the separate extracted WAVs remain PCM24.",
            "Source-event timbre families, articulation groups and outliers are advisory in v1; no candidate sample was removed automatically.",
        ]
        if not is_drums:
            warnings.append(
                f"Keys more than {max_transpose} semitones from an extracted root are intentionally left unmapped rather than heavily pitch-shifted."
            )
        if selection_warning:
            warnings.append(selection_warning)
        if ausampler_preset_warning:
            warnings.append(
                "GarageBand's preset chooser cannot select a raw SF2. "
                f"No .aupreset wrapper was created: {ausampler_preset_warning}"
            )
        if allow_polyphonic and any(not segment.isolated for segment in chosen):
            warnings.append(
                "Polyphonic extraction was explicitly enabled; some samples contain more than one source note."
            )
        tuning_statuses: dict[str, int] = {}
        for row in rows:
            status = str(row["tuning"]["status"])
            tuning_statuses[status] = tuning_statuses.get(status, 0) + 1
        report = {
            "operation": "sample-pack",
            "format_version": 2,
            "status": "complete",
            "stem": str(stem.resolve()),
            "midi": str(midi.resolve()),
            "kind": normalized_kind,
            "track": {
                "selected_index": selected_track_index,
                "selected_title": clip.title,
                "available_titles": available_tracks,
            },
            "sample_rate": sample_rate,
            "sample_count": len(rows),
            "allow_polyphonic": allow_polyphonic,
            "max_transpose_semitones": 0 if is_drums else max_transpose,
            "auto_tune": auto_tune and not is_drums,
            "tuning_statuses": tuning_statuses,
            "instrument_name": soundfont_summary["name"],
            "samples": rows,
            "source_event_clusters": source_event_clusters["summary"],
            "source_event_dynamics": source_event_dynamics["summary"],
            "sample_loop_suggestions": sample_loop_suggestions["summary"],
            "sfz": "sunofriend-instrument.sfz",
            "soundfont": soundfont_summary,
            "artifacts": {
                "report": "sample_pack.json",
                "readme": "README.md",
                "sfz": "sunofriend-instrument.sfz",
                "soundfont": "sunofriend-instrument.sf2",
                "ausampler_preset": (
                    "sunofriend-instrument.aupreset" if ausampler_preset else None
                ),
                "samples": "samples",
                "audition_midi": "garageband-audition.mid",
                "audition_wav": ("garageband-audition.wav" if render_preview else None),
                "source_event_clusters": "source_event_clusters.json",
                "source_event_clusters_graph": "source_event_clusters.svg",
                "source_event_dynamics": "source_event_dynamics.json",
                "source_event_dynamics_graph": "source_event_dynamics.svg",
                "sample_loop_suggestions": "source_sample_loops.json",
                "sample_loop_suggestions_graph": "source_sample_loops.svg",
                "sample_loop_auditions": (
                    "loop-auditions"
                    if sample_loop_suggestions["summary"]["suggested_loop_count"]
                    else None
                ),
            },
            "ausampler_preset": ausampler_preset,
            "garageband_import": (
                [
                    "Keep sunofriend-instrument.aupreset and sunofriend-instrument.sf2 in this output directory; the preset points to this exact SF2 path.",
                    "Drag garageband-audition.mid into the Tracks area, then select the new Software Instrument track.",
                    "Open Smart Controls and choose AU Instruments > Apple > AUSampler > Stereo as the instrument.",
                    "Open AUSampler's preset menu (it normally says Manual), choose its load/open setting command, and select sunofriend-instrument.aupreset — not the greyed-out .sf2 bank.",
                    "Play the audition region to verify every embedded zone, then replace it with the song MIDI.",
                    "Save the configured track as a custom GarageBand patch if you want it in future projects.",
                ]
                if ausampler_preset
                else [
                    "GarageBand's AUSampler preset chooser accepts .aupreset files, not raw .sf2 banks.",
                    "This Mac did not create the optional .aupreset wrapper; use the SF2 in another compatible sampler or regenerate the pack on macOS with the Swift command available.",
                    "The SF2 remains a valid, self-contained sound bank for compatible hosts and APIs.",
                ]
            ),
            "warnings": warnings,
        }
        _write_json(work / "source_event_clusters.json", source_event_clusters)
        (work / "source_event_clusters.svg").write_text(
            source_event_clusters_svg(source_event_clusters), encoding="utf-8"
        )
        _write_json(work / "source_event_dynamics.json", source_event_dynamics)
        (work / "source_event_dynamics.svg").write_text(
            source_event_dynamics_svg(source_event_dynamics), encoding="utf-8"
        )
        _write_json(work / "source_sample_loops.json", sample_loop_suggestions)
        (work / "source_sample_loops.svg").write_text(
            sample_loop_suggestions_svg(sample_loop_suggestions), encoding="utf-8"
        )
        _write_json(work / "sample_pack.json", report)
        (work / "README.md").write_text(_sample_pack_markdown(report), encoding="utf-8")
        work.rename(destination)
        report["report"] = str(destination / "sample_pack.json")
        report["readme"] = str(destination / "README.md")
        return report
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


def _select_clip(path: Path, track_index: int | None):
    from .clip import read_midi_clips

    clips = list(read_midi_clips(path))
    if not clips:
        raise ValueError("MIDI contains no note-bearing tracks")
    titles = [clip.title for clip in clips]
    if track_index is None:
        if len(clips) != 1:
            choices = ", ".join(
                f"{index}: {title}" for index, title in enumerate(titles)
            )
            raise ValueError(
                f"MIDI contains {len(clips)} note-bearing tracks; choose --track-index ({choices})"
            )
        return clips[0], titles, 0
    if not 0 <= track_index < len(clips):
        raise ValueError(f"track_index must be from 0 to {len(clips) - 1}")
    return clips[track_index], titles, track_index


def _load_audio(
    path: str | Path,
    *,
    target_sample_rate: int | None,
    max_seconds: float | None = None,
) -> tuple[Any, int]:
    import numpy as np
    import soundfile

    from .vocal import phase_safe_downmix

    with soundfile.SoundFile(str(path)) as handle:
        frames = len(handle)
        if max_seconds is not None:
            frames = min(frames, int(round(max_seconds * handle.samplerate)))
        values = handle.read(frames, dtype="float32", always_2d=True)
        sample_rate = int(handle.samplerate)
    mono = np.asarray(phase_safe_downmix(values), dtype=np.float32)
    mono = np.nan_to_num(mono, copy=False)
    if target_sample_rate and sample_rate != target_sample_rate and len(mono):
        import librosa

        mono = librosa.resample(
            mono,
            orig_sr=sample_rate,
            target_sr=target_sample_rate,
        ).astype(np.float32, copy=False)
        sample_rate = int(target_sample_rate)
    return mono, sample_rate


def _select_source_segments(
    audio: Any,
    sample_rate: int,
    notes: Sequence[Any],
    *,
    kind: str,
    limit: int,
    tail_seconds: float = 0.12,
    allow_polyphonic: bool,
) -> tuple[list[_SelectedSegment], str | None]:
    import numpy as np

    candidates: list[_SelectedSegment] = []
    note_ranges = [
        (float(note.source_start_seconds), float(note.source_end_seconds))
        for note in notes
    ]
    is_drums = kind in DRUM_KINDS
    for index, note in enumerate(notes):
        note_start = float(note.source_start_seconds)
        note_end = float(note.source_end_seconds)
        previous_ends = [
            other_end
            for other_index, (_, other_end) in enumerate(note_ranges)
            if other_index != index and other_end <= note_start
        ]
        start_seconds = max(0.0, note_start - 0.008)
        if previous_ends:
            start_seconds = max(start_seconds, max(previous_ends) + 0.003)
        maximum = 0.8 if is_drums else 3.0
        end_seconds = min(
            len(audio) / sample_rate,
            note_end + tail_seconds,
            start_seconds + maximum,
        )
        next_starts = [
            other_start
            for other_index, (other_start, _) in enumerate(note_ranges)
            if other_index != index and other_start >= note_end
        ]
        if next_starts:
            end_seconds = min(end_seconds, min(next_starts) - 0.003)
        if end_seconds - start_seconds < 0.055:
            continue
        overlap_count = sum(
            1
            for other_index, (other_start, other_end) in enumerate(note_ranges)
            if other_index != index
            and other_start < note_end
            and other_end > note_start
        )
        isolated = overlap_count == 0
        if not isolated and not allow_polyphonic:
            continue
        start = max(0, int(round(start_seconds * sample_rate)))
        end = min(len(audio), int(round(end_seconds * sample_rate)))
        values = np.asarray(audio[start:end], dtype=np.float32)
        if len(values) < 64:
            continue
        rms = math.sqrt(float(np.mean(values.astype(np.float64) ** 2)))
        if rms < 1e-5:
            continue
        candidates.append(
            _SelectedSegment(
                note_index=index,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                pitch=int(note.pitch),
                velocity=int(note.velocity),
                isolated=isolated,
                overlap_count=overlap_count,
                rms=rms,
                samples=values,
            )
        )
    if not candidates:
        return [], None

    ordered = sorted(
        candidates,
        key=lambda item: (
            not item.isolated,
            -item.rms,
            -item.velocity,
            item.start_seconds,
        ),
    )
    selected: list[_SelectedSegment] = []
    used_buckets: set[int] = set()
    for segment in ordered:
        bucket = segment.pitch // (1 if is_drums else 6)
        if bucket not in used_buckets:
            selected.append(segment)
            used_buckets.add(bucket)
        if len(selected) >= limit:
            break
    for segment in ordered:
        if len(selected) >= limit:
            break
        if segment not in selected:
            selected.append(segment)
    selected.sort(key=lambda item: item.start_seconds)
    warning = None
    if any(not item.isolated for item in selected):
        warning = (
            "Some timbre evidence windows are polyphonic; the ranking can describe a "
            "layer or accompaniment rather than one physical instrument."
        )
    return selected, warning


def _timbre_vector(values: Any, sample_rate: int) -> tuple[float, ...]:
    import librosa
    import numpy as np

    audio = np.asarray(values, dtype=np.float32)
    if not len(audio):
        raise ValueError("Cannot profile empty audio")
    peak = float(np.max(np.abs(audio)))
    if peak <= 1e-8:
        raise ValueError("Cannot profile silent audio")
    active = np.flatnonzero(np.abs(audio) >= peak * 0.008)
    if len(active):
        audio = audio[
            max(0, int(active[0]) - 64) : min(len(audio), int(active[-1]) + 65)
        ]
    audio = audio[: max(2048, int(sample_rate * 3.0))]
    audio = audio / max(float(np.max(np.abs(audio))), 1e-8)
    if len(audio) < 2048:
        audio = np.pad(audio, (0, 2048 - len(audio)))
    n_fft = 1024
    hop = 256
    spectrum = np.abs(librosa.stft(audio, n_fft=n_fft, hop_length=hop))
    power = spectrum**2
    mfcc = librosa.feature.mfcc(
        y=audio,
        sr=sample_rate,
        n_mfcc=13,
        n_fft=n_fft,
        hop_length=hop,
    )
    centroid = librosa.feature.spectral_centroid(S=power, sr=sample_rate)
    bandwidth = librosa.feature.spectral_bandwidth(S=power, sr=sample_rate)
    rolloff = librosa.feature.spectral_rolloff(
        S=power, sr=sample_rate, roll_percent=0.85
    )
    flatness = librosa.feature.spectral_flatness(S=power)
    zcr = librosa.feature.zero_crossing_rate(audio, frame_length=n_fft, hop_length=hop)
    rms = librosa.feature.rms(y=audio, frame_length=n_fft, hop_length=hop)[0]
    peak_frame = int(np.argmax(rms)) if len(rms) else 0
    attack_ratio = peak_frame / max(1, len(rms) - 1)
    tail = rms[max(0, int(len(rms) * 0.8)) :]
    decay_ratio = float(np.median(tail)) / max(float(np.max(rms)), 1e-8)
    crest = float(np.max(rms)) / max(float(np.mean(rms)), 1e-8)
    nyquist = sample_rate / 2.0
    vector = [
        *[float(np.median(row)) / 100.0 for row in mfcc[1:13]],
        float(np.median(centroid)) / nyquist,
        float(np.median(bandwidth)) / nyquist,
        float(np.median(rolloff)) / nyquist,
        math.log10(max(float(np.median(flatness)), 1e-10)) / 10.0,
        float(np.median(zcr)),
        float(attack_ratio),
        float(decay_ratio),
        math.log1p(crest) / 4.0,
    ]
    return tuple(float(np.nan_to_num(value)) for value in vector)


def _rank_factory_profiles(
    source_profile: tuple[float, ...],
    profiles: Sequence[tuple[FactoryAsset, tuple[float, ...], tuple[str, ...]]],
    *,
    kind: str,
    top: int,
) -> list[FactoryInstrumentMatch]:
    import numpy as np

    if not profiles:
        return []
    matrix = np.asarray([source_profile, *[profile for _, profile, _ in profiles]])
    scale = np.std(matrix, axis=0)
    scale = np.where(scale < 0.025, 0.025, scale)
    source = matrix[0]
    rows = []
    for index, (asset, profile, files) in enumerate(profiles, 1):
        distance = float(np.sqrt(np.mean(((matrix[index] - source) / scale) ** 2)))
        similarity = 1.0 / (1.0 + distance)
        prior = role_name_fit(asset.name, kind)
        combined = 0.92 * similarity + 0.08 * prior
        rows.append((combined, similarity, prior, asset, profile, files))
    rows.sort(key=lambda item: (-item[0], -item[1], item[3].name.casefold()))
    matches = []
    for rank, (combined, similarity, prior, asset, profile, files) in enumerate(
        rows[:top], 1
    ):
        matches.append(
            FactoryInstrumentMatch(
                rank=rank,
                asset_name=asset.name,
                asset_source=asset.source,
                asset_root=asset.root,
                audio_similarity=round(similarity * 100.0, 3),
                role_name_prior=round(prior * 100.0, 3),
                combined_score=round(combined * 100.0, 3),
                comparison=_comparison_phrases(source_profile, profile),
                profiled_sample_count=len(files),
                representative_sample_files=tuple(files[:4]),
                timbre_profile=profile,
            )
        )
    return matches


def _rank_gm_programs(
    *,
    stem_audio: Any,
    stem_path: Path,
    sample_rate: int,
    clip: Any,
    programs: Sequence[int],
    top: int,
    work_dir: Path,
    embedding_model: Any | None = None,
) -> tuple[list[GmProgramMatch], list[LearnedGmProgramMatch], dict[str, Any] | None]:
    from .clip import Instrument, write_clip_midi
    from .render import find_soundfont, render_midi_to_wav

    from .instrument_embedding import compare_embedding_fingerprints

    source = _performance_fingerprint(stem_audio, sample_rate)
    source_embedding = (
        embedding_model.fingerprint(stem_audio, sample_rate)
        if embedding_model is not None
        else None
    )
    soundfont = Path(find_soundfont()).expanduser().resolve()
    audition_dir = work_dir / "gm_auditions"
    audition_dir.mkdir(exist_ok=True)
    embedding_audition_dir = work_dir / "gm_embedding_auditions"
    if embedding_model is not None:
        embedding_audition_dir.mkdir(exist_ok=True)
    temporary_dir = work_dir / ".gm_work"
    temporary_dir.mkdir(exist_ok=True)
    scored: list[tuple[float, float, float, float, int, Path]] = []
    embedding_rows: list[dict[str, Any]] = []
    for program in programs:
        name = GM_PROGRAM_NAMES[program]
        candidate = replace(
            clip,
            instrument=Instrument(
                role=clip.instrument.role,
                program=program,
                channel=clip.instrument.channel,
                suggestions=(name,),
            ),
        )
        midi_path = temporary_dir / f"program-{program:03d}.mid"
        wav_path = temporary_dir / f"program-{program:03d}.wav"
        write_clip_midi(midi_path, candidate)
        render_midi_to_wav(midi_path, wav_path, soundfont_path=soundfont)
        rendered, rendered_rate = _load_audio(wav_path, target_sample_rate=sample_rate)
        fingerprint = _performance_fingerprint(rendered, rendered_rate)
        spectral, dynamics, attack = _performance_similarity(source, fingerprint)
        combined = 0.70 * spectral + 0.15 * dynamics + 0.15 * attack
        scored.append((combined, spectral, dynamics, attack, program, midi_path))
        if embedding_model is not None and source_embedding is not None:
            candidate_embedding = embedding_model.fingerprint(rendered, rendered_rate)
            comparison = compare_embedding_fingerprints(
                source_embedding, candidate_embedding
            )
            embedding_rows.append(
                {
                    "program": program,
                    "patch_number": program + 1,
                    "name": name,
                    "midi_sha256": _file_sha256(midi_path),
                    "rendered_wav_sha256": _file_sha256(wav_path),
                    "candidate_fingerprint": candidate_embedding.summary(),
                    "embedding_comparison": comparison,
                    "explainable_comparison": {
                        "combined_score": round(combined * 100.0, 3),
                        "spectral_shape_similarity": round(spectral * 100.0, 3),
                        "dynamics_similarity": round(dynamics * 100.0, 3),
                        "attack_similarity": round(attack * 100.0, 3),
                    },
                    "temporary_midi": midi_path,
                }
            )
        wav_path.unlink(missing_ok=True)
    scored.sort(key=lambda item: (-item[0], item[4]))

    matches: list[GmProgramMatch] = []
    for rank, (combined, spectral, dynamics, attack, program, midi_path) in enumerate(
        scored[:top], 1
    ):
        token = _safe_token(GM_PROGRAM_NAMES[program])
        output_midi = audition_dir / f"{rank:02d}-{program:03d}-{token}.mid"
        output_wav = audition_dir / f"{rank:02d}-{program:03d}-{token}.wav"
        shutil.copyfile(midi_path, output_midi)
        render_midi_to_wav(output_midi, output_wav, soundfont_path=soundfont)
        matches.append(
            GmProgramMatch(
                rank=rank,
                program=program,
                patch_number=program + 1,
                name=GM_PROGRAM_NAMES[program],
                combined_score=round(combined * 100.0, 3),
                spectral_shape_similarity=round(spectral * 100.0, 3),
                dynamics_similarity=round(dynamics * 100.0, 3),
                attack_similarity=round(attack * 100.0, 3),
                midi=str(Path("gm_auditions") / output_midi.name),
                preview_wav=str(Path("gm_auditions") / output_wav.name),
            )
        )

    learned_matches: list[LearnedGmProgramMatch] = []
    embedding_evidence = None
    if embedding_model is not None and source_embedding is not None:
        ranked_embeddings = sorted(
            embedding_rows,
            key=lambda row: (
                -float(row["embedding_comparison"]["similarity_score"]),
                int(row["program"]),
            ),
        )
        for rank, row in enumerate(ranked_embeddings[:top], 1):
            program = int(row["program"])
            token = _safe_token(str(row["name"]))
            output_midi = (
                embedding_audition_dir / f"{rank:02d}-{program:03d}-{token}.mid"
            )
            output_wav = (
                embedding_audition_dir / f"{rank:02d}-{program:03d}-{token}.wav"
            )
            shutil.copyfile(Path(row["temporary_midi"]), output_midi)
            render_midi_to_wav(output_midi, output_wav, soundfont_path=soundfont)
            comparison = row["embedding_comparison"]
            percentiles = comparison["similarity_percentiles"]
            learned_matches.append(
                LearnedGmProgramMatch(
                    rank=rank,
                    program=program,
                    patch_number=program + 1,
                    name=str(row["name"]),
                    embedding_similarity=float(comparison["similarity_score"]),
                    active_window_count=int(comparison["active_window_count"]),
                    p10_similarity=float(percentiles["p10"]),
                    p90_similarity=float(percentiles["p90"]),
                    midi=str(Path("gm_embedding_auditions") / output_midi.name),
                    preview_wav=str(Path("gm_embedding_auditions") / output_wav.name),
                )
            )
        evidence_candidates = []
        for row in sorted(embedding_rows, key=lambda item: int(item["program"])):
            evidence_candidates.append(
                {key: value for key, value in row.items() if key != "temporary_midi"}
            )
        embedding_evidence = {
            "schema": "sunofriend.instrument-embedding-evidence.v1",
            "operation": "instrument-match",
            "status": "complete",
            "advisory_only": True,
            "ranking_effect": (
                "none; gm_rendered_matches retains the existing explainable "
                "spectral/dynamics/attack score and order"
            ),
            "model": embedding_model.model_record(),
            "preprocessing": embedding_model.preprocessing_record(),
            "source": {
                "path": str(stem_path.resolve()),
                "sha256": _file_sha256(stem_path),
                "fingerprint": source_embedding.summary(),
            },
            "renderer": {
                "name": "FluidSynth",
                "soundfont_path": str(soundfont),
                "soundfont_sha256": _file_sha256(soundfont),
                "reverb": False,
                "chorus": False,
            },
            "candidate_programs": [int(value) for value in programs],
            "candidates": evidence_candidates,
            "learned_ranking": [match.to_dict() for match in learned_matches],
            "interpretation": (
                "Relative cosine similarity for aligned active windows within this "
                "candidate set. Scores are not confidence or proof of instrument identity."
            ),
        }
    shutil.rmtree(temporary_dir, ignore_errors=True)
    return matches, learned_matches, embedding_evidence


def _build_gm_drum_family_mapping(
    *,
    stem_path: Path,
    midi_path: Path,
    clip: Any,
    kind: str,
    source_event_clusters: dict[str, Any],
    source_vectors: Sequence[Sequence[float]],
    sample_rate: int,
    work_dir: Path,
) -> dict[str, Any]:
    """Render, score and export a review-only GM drum-note proposal."""

    from .clip import write_clip_midi
    from .drum_mapping import (
        GM_DRUM_NOTE_NAMES,
        drum_note_candidates,
        propose_drum_family_mapping,
    )
    from .midi import MidiTrack, write_midi_file
    from .models import NoteEvent
    from .render import find_soundfont, render_midi_to_wav

    source_hash_before = _file_sha256(midi_path)
    soundfont = Path(find_soundfont()).expanduser().resolve()
    temporary_dir = work_dir / ".gm_drum_work"
    temporary_dir.mkdir(exist_ok=True)
    candidate_vectors: dict[int, tuple[float, ...]] = {}
    candidate_paths: dict[int, tuple[Path, Path]] = {}
    try:
        for note in drum_note_candidates(kind):
            token = _safe_token(GM_DRUM_NOTE_NAMES[note])
            candidate_midi = temporary_dir / f"note-{note:03d}-{token}.mid"
            candidate_wav = temporary_dir / f"note-{note:03d}-{token}.wav"
            write_midi_file(
                candidate_midi,
                [
                    MidiTrack(
                        "GM drum-note audition",
                        channel=9,
                        program=0,
                        notes=[NoteEvent(0.05, 0.85, note, 104)],
                    )
                ],
                bpm=120.0,
            )
            render_midi_to_wav(
                candidate_midi,
                candidate_wav,
                sample_rate=sample_rate,
                soundfont_path=soundfont,
            )
            candidate_audio, candidate_rate = _load_audio(
                candidate_wav, target_sample_rate=sample_rate
            )
            candidate_vectors[note] = _timbre_vector(candidate_audio, candidate_rate)
            candidate_paths[note] = (candidate_midi, candidate_wav)

        proposed_clip, evidence = propose_drum_family_mapping(
            kind=kind,
            clip=clip,
            source_event_clusters=source_event_clusters,
            source_vectors=source_vectors,
            candidate_vectors=candidate_vectors,
        )
        proposed_midi = work_dir / "drum_family_mapping.proposed.mid"
        proposed_wav = work_dir / "drum_family_mapping.proposed.wav"
        write_clip_midi(proposed_midi, proposed_clip)
        render_midi_to_wav(
            proposed_midi,
            proposed_wav,
            sample_rate=sample_rate,
            soundfont_path=soundfont,
        )

        audition_dir = work_dir / "drum_note_auditions"
        audition_dir.mkdir(exist_ok=True)
        audition_rows = []
        assigned_notes = sorted(
            {int(row["assigned_note"]) for row in evidence["family_mappings"]}
        )
        for note in assigned_notes:
            token = _safe_token(GM_DRUM_NOTE_NAMES[note])
            output_midi = audition_dir / f"note-{note:03d}-{token}.mid"
            output_wav = audition_dir / f"note-{note:03d}-{token}.wav"
            shutil.copy2(candidate_paths[note][0], output_midi)
            shutil.copy2(candidate_paths[note][1], output_wav)
            audition_rows.append(
                {
                    "note": note,
                    "name": GM_DRUM_NOTE_NAMES[note],
                    "midi": str(Path("drum_note_auditions") / output_midi.name),
                    "preview_wav": str(Path("drum_note_auditions") / output_wav.name),
                }
            )

        source_hash_after = _file_sha256(midi_path)
        if source_hash_after != source_hash_before:
            raise RuntimeError("The supplied MIDI changed while building the proposal")
        evidence.update(
            {
                "source": {
                    "stem_path": str(stem_path.resolve()),
                    "stem_sha256": _file_sha256(stem_path),
                    "midi_path": str(midi_path.resolve()),
                    "midi_sha256_before": source_hash_before,
                    "midi_sha256_after": source_hash_after,
                },
                "renderer": {
                    "name": "FluidSynth",
                    "soundfont_path": str(soundfont),
                    "soundfont_sha256": _file_sha256(soundfont),
                    "sample_rate": sample_rate,
                    "reverb": False,
                    "chorus": False,
                },
                "auditions": audition_rows,
                "artifacts": {
                    "source_event_clusters": "source_event_clusters.json",
                    "mapping_report": "gm_drum_family_mapping.json",
                    "proposed_midi": proposed_midi.name,
                    "proposed_wav": proposed_wav.name,
                    "assigned_note_auditions": "drum_note_auditions",
                },
            }
        )
        evidence["effects"].update(
            {
                "source_midi_sha256_before": source_hash_before,
                "source_midi_sha256_after": source_hash_after,
                "proposed_midi_sha256": _file_sha256(proposed_midi),
                "proposed_wav_sha256": _file_sha256(proposed_wav),
            }
        )
        _write_json(work_dir / "gm_drum_family_mapping.json", evidence)
        return evidence
    finally:
        shutil.rmtree(temporary_dir, ignore_errors=True)


def _performance_fingerprint(values: Any, sample_rate: int) -> _PerformanceFingerprint:
    import librosa
    import numpy as np

    audio = np.asarray(values, dtype=np.float32)
    hop = 512
    mel = librosa.feature.melspectrogram(
        y=audio,
        sr=sample_rate,
        n_fft=2048,
        hop_length=hop,
        n_mels=64,
        power=2.0,
    )
    log_mel = np.log1p(20.0 * mel)
    norms = np.linalg.norm(log_mel, axis=0, keepdims=True)
    mel_shape = log_mel / np.maximum(norms, 1e-8)
    rms = librosa.feature.rms(y=audio, frame_length=2048, hop_length=hop)[0]
    onset = librosa.onset.onset_strength(y=audio, sr=sample_rate, hop_length=hop)
    return _PerformanceFingerprint(mel_shape=mel_shape, rms=rms, onset=onset)


def _performance_similarity(
    source: _PerformanceFingerprint,
    candidate: _PerformanceFingerprint,
) -> tuple[float, float, float]:
    import numpy as np

    frames = min(
        source.mel_shape.shape[1],
        candidate.mel_shape.shape[1],
        len(source.rms),
        len(candidate.rms),
    )
    if frames <= 2:
        return 0.0, 0.0, 0.0
    source_rms = source.rms[:frames]
    candidate_rms = candidate.rms[:frames]
    active = (source_rms > max(float(np.max(source_rms)) * 0.01, 1e-7)) & (
        candidate_rms > max(float(np.max(candidate_rms)) * 0.01, 1e-7)
    )
    if not np.any(active):
        return 0.0, 0.0, 0.0
    cosine = np.sum(
        source.mel_shape[:, :frames] * candidate.mel_shape[:, :frames], axis=0
    )
    spectral = float(np.clip(np.median(cosine[active]), 0.0, 1.0))
    dynamics = _correlation_similarity(source_rms[active], candidate_rms[active])
    onset_frames = min(len(source.onset), len(candidate.onset), frames)
    attack = _correlation_similarity(
        source.onset[:onset_frames], candidate.onset[:onset_frames]
    )
    return spectral, dynamics, attack


def _correlation_similarity(left: Any, right: Any) -> float:
    import numpy as np

    if len(left) < 3 or len(right) < 3:
        return 0.5
    left_std = float(np.std(left))
    right_std = float(np.std(right))
    if left_std < 1e-10 or right_std < 1e-10:
        return 0.5
    correlation = float(np.corrcoef(left, right)[0, 1])
    if not math.isfinite(correlation):
        return 0.5
    return float(np.clip((correlation + 1.0) / 2.0, 0.0, 1.0))


def _select_asset_samples(
    asset: FactoryAsset,
    *,
    target_pitch: float,
    limit: int,
) -> list[Path]:
    files = [Path(value) for value in asset.sample_files]
    pitched = [(path, _pitch_from_filename(path.name)) for path in files]
    with_pitch = [(path, pitch) for path, pitch in pitched if pitch is not None]
    selected: list[Path] = []
    if with_pitch:
        with_pitch.sort(
            key=lambda item: (
                abs(float(item[1]) - target_pitch),
                str(item[0]).casefold(),
            )
        )
        selected.extend(path for path, _ in with_pitch[:limit])
    if len(selected) < limit:
        remaining = [path for path in files if path not in selected]
        if remaining:
            stride = max(1, len(remaining) // max(1, limit - len(selected)))
            selected.extend(remaining[::stride][: limit - len(selected)])
    return selected[:limit]


def _pitch_from_filename(name: str) -> int | None:
    numeric = re.search(r"(?i)(?:^|[^a-z])n(\d{2,3})(?:[^0-9]|$)", name)
    if numeric:
        value = int(numeric.group(1))
        return value if 0 <= value <= 127 else None
    matches = list(re.finditer(r"(?i)([a-g])([#b]?)(-?\d)", name))
    if not matches:
        return None
    match = matches[-1]
    pitch_class = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}[
        match.group(1).casefold()
    ]
    accidental = match.group(2)
    if accidental == "#":
        pitch_class += 1
    elif accidental.casefold() == "b":
        pitch_class -= 1
    value = (int(match.group(3)) + 1) * 12 + pitch_class
    return value if 0 <= value <= 127 else None


def _comparison_phrases(
    source: Sequence[float], candidate: Sequence[float]
) -> tuple[str, ...]:
    phrases = []
    phrases.append(
        _relative_phrase(source[12], candidate[12], "brightness", "brighter", "darker")
    )
    phrases.append(
        _relative_phrase(
            source[15], candidate[15], "noise/flatness", "noisier", "more tonal"
        )
    )
    phrases.append(
        _relative_phrase(
            source[17], candidate[17], "attack", "slower attack", "faster attack"
        )
    )
    phrases.append(
        _relative_phrase(
            source[18], candidate[18], "tail", "more sustained", "shorter decay"
        )
    )
    return tuple(phrases)


def _factory_match_dict(
    match: FactoryInstrumentMatch, presets: Sequence[Any]
) -> dict[str, Any]:
    value = match.to_dict()
    value["related_installed_sampler_presets"] = _related_sampler_presets(
        match.asset_name, presets
    )
    return value


def _related_sampler_presets(
    asset_name: str, presets: Sequence[Any]
) -> list[dict[str, Any]]:
    generic = {
        "acoustic",
        "bass",
        "choir",
        "drum",
        "electric",
        "ensemble",
        "instrument",
        "kit",
        "sampler",
        "solo",
        "string",
        "strings",
    }
    asset_text = asset_name.casefold()
    asset_tokens = set(re.findall(r"[a-z0-9]+", asset_text))
    distinctive = asset_tokens - generic
    scored = []
    for preset in presets:
        preset_text = str(preset.name).casefold()
        preset_tokens = set(re.findall(r"[a-z0-9]+", preset_text))
        context_tokens = preset_tokens | set(
            re.findall(r"[a-z0-9]+", str(preset.category).casefold())
        )
        if "bass" in asset_tokens and "bass" not in context_tokens:
            continue
        overlap = asset_tokens & preset_tokens
        exact = preset_text == asset_text
        distinctive_overlap = distinctive & preset_tokens
        if not exact and not distinctive_overlap and len(overlap) < 2:
            continue
        union = asset_tokens | preset_tokens
        score = (
            (3.0 if exact else 0.0)
            + len(distinctive_overlap)
            + (len(overlap) / max(1, len(union)))
        )
        scored.append((score, preset))
    scored.sort(
        key=lambda item: (
            -item[0],
            str(item[1].name).casefold(),
            not str(item[1].source).startswith("garageband"),
            str(item[1].category).casefold(),
        )
    )
    selected = []
    seen_names = set()
    for _, preset in scored:
        normalized_name = str(preset.name).casefold()
        if normalized_name in seen_names:
            continue
        selected.append(preset.to_dict())
        seen_names.add(normalized_name)
        if len(selected) >= 5:
            break
    return selected


def _relative_phrase(
    source: float,
    candidate: float,
    label: str,
    higher: str,
    lower: str,
) -> str:
    delta = candidate - source
    if abs(delta) <= 0.04:
        return f"similar {label}"
    return higher if delta > 0 else lower


def _choose_sample_pack_segments(
    segments: Sequence[_SelectedSegment],
    *,
    kind: str,
    limit: int,
) -> list[_SelectedSegment]:
    ordered = sorted(
        segments,
        key=lambda item: (not item.isolated, -item.rms, -item.velocity),
    )
    chosen: list[_SelectedSegment] = []
    seen_pitch: set[int] = set()
    for segment in ordered:
        if segment.pitch in seen_pitch:
            continue
        chosen.append(segment)
        seen_pitch.add(segment.pitch)
        if len(chosen) >= limit:
            break
    return chosen


def _fade_and_normalize(values: Any, sample_rate: int) -> Any:
    import numpy as np

    audio = np.asarray(values, dtype=np.float32).copy()
    fade = min(len(audio) // 2, max(1, int(round(sample_rate * 0.006))))
    if fade:
        audio[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
        audio[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if peak > 1e-8:
        audio *= 0.89 / peak
    return np.clip(audio, -1.0, 1.0)


def _write_wav(path: Path, values: Any, sample_rate: int) -> None:
    import soundfile

    soundfile.write(str(path), values, sample_rate, subtype="PCM_24")


def _estimate_sample_tuning(
    values: Any,
    sample_rate: int,
    midi_pitch: int,
    *,
    enabled: bool,
) -> dict[str, Any]:
    if not enabled:
        return {
            "status": "disabled",
            "target_hz": round(440.0 * 2.0 ** ((midi_pitch - 69) / 12.0), 6),
            "detected_hz": None,
            "offset_cents": None,
            "pitch_correction_cents": 0,
            "confidence": None,
        }
    import librosa
    import numpy as np

    target_hz = 440.0 * 2.0 ** ((midi_pitch - 69) / 12.0)
    fmin = max(20.0, target_hz * 2.0 ** (-7.0 / 12.0))
    fmax = min(sample_rate / 2.0 - 1.0, target_hz * 2.0 ** (7.0 / 12.0))
    if fmax <= fmin:
        return {
            "status": "unavailable",
            "target_hz": round(target_hz, 6),
            "detected_hz": None,
            "offset_cents": None,
            "pitch_correction_cents": 0,
            "confidence": None,
            "detail": "Target pitch is above the audio sample rate's usable range",
        }
    frame_length = 2048
    required = int(math.ceil(sample_rate / fmin * 3.0))
    while frame_length < required and frame_length < 16_384:
        frame_length *= 2
    try:
        f0, voiced, probability = librosa.pyin(
            np.asarray(values, dtype=np.float32),
            fmin=fmin,
            fmax=fmax,
            sr=sample_rate,
            frame_length=frame_length,
            hop_length=max(128, frame_length // 8),
        )
    except (ValueError, RuntimeError) as exc:
        return {
            "status": "unavailable",
            "target_hz": round(target_hz, 6),
            "detected_hz": None,
            "offset_cents": None,
            "pitch_correction_cents": 0,
            "confidence": None,
            "detail": str(exc),
        }
    valid = voiced & np.isfinite(f0) & (probability >= 0.65)
    if np.count_nonzero(valid) < 2:
        return {
            "status": "no-stable-pitch",
            "target_hz": round(target_hz, 6),
            "detected_hz": None,
            "offset_cents": None,
            "pitch_correction_cents": 0,
            "confidence": round(float(np.nanmax(probability)), 4)
            if len(probability) and np.any(np.isfinite(probability))
            else None,
        }
    frequencies = f0[valid]
    detected_hz = float(np.median(frequencies))
    cents_values = 1200.0 * np.log2(frequencies / target_hz)
    offset_cents = float(np.median(cents_values))
    deviation = float(np.median(np.abs(cents_values - offset_cents)))
    confidence = float(np.median(probability[valid]))
    if abs(offset_cents) > 99.0:
        status = "rejected-out-of-range"
        correction = 0
    elif deviation > 30.0:
        status = "rejected-unstable"
        correction = 0
    else:
        status = "applied"
        correction = int(round(-offset_cents))
    return {
        "status": status,
        "target_hz": round(target_hz, 6),
        "detected_hz": round(detected_hz, 6),
        "offset_cents": round(offset_cents, 3),
        "pitch_correction_cents": correction,
        "confidence": round(confidence, 4),
        "deviation_cents_mad": round(deviation, 3),
    }


def _with_zone_ranges(
    rows: Sequence[dict[str, Any]], *, drums: bool, max_transpose: int
) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda item: int(item["pitch"]))
    pitches = [int(row["pitch"]) for row in ordered]
    mapped = []
    for index, row in enumerate(ordered):
        pitch = int(row["pitch"])
        if drums:
            low = high = pitch
        else:
            midpoint_low = (
                pitch - max_transpose
                if index == 0
                else (pitches[index - 1] + pitch) // 2 + 1
            )
            midpoint_high = (
                pitch + max_transpose
                if index == len(pitches) - 1
                else (pitch + pitches[index + 1]) // 2
            )
            low = max(0, pitch - max_transpose, midpoint_low)
            high = min(127, pitch + max_transpose, midpoint_high)
        mapped.append(
            {
                **row,
                "low_key": low,
                "high_key": high,
                "low_velocity": 0,
                "high_velocity": 127,
            }
        )
    return mapped


def _sfz_text(rows: Sequence[dict[str, Any]]) -> str:
    ordered = sorted(rows, key=lambda item: int(item["pitch"]))
    lines = [
        "// Sunofriend Sample Instrument v2",
        "// Relative WAV paths; use only source audio you have permission to sample.",
        "<group> ampeg_attack=0.005 ampeg_release=0.15",
    ]
    for row in ordered:
        pitch = int(row["pitch"])
        sample = str(row["file"]).replace("\\", "/")
        correction = int(row["tuning"]["pitch_correction_cents"])
        lines.append(
            f"<region> sample={sample} pitch_keycenter={pitch} "
            f"lokey={row['low_key']} hikey={row['high_key']} "
            f"lovel={row['low_velocity']} hivel={row['high_velocity']} "
            f"tune={correction}"
        )
    return "\n".join(lines) + "\n"


def _write_sample_pack_audition(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    from .midi import MidiTrack, write_midi_file
    from .models import NoteEvent

    notes = []
    for index, row in enumerate(sorted(rows, key=lambda item: int(item["pitch"]))):
        start = index * 0.75
        notes.append(
            NoteEvent(
                start=start,
                end=start + 0.5,
                pitch=int(row["pitch"]),
                velocity=100,
            )
        )
    write_midi_file(
        path,
        [MidiTrack("Sunofriend Sample Instrument Audition", 0, 0, notes)],
        bpm=120.0,
    )


def _audition_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# GarageBand instrument audition",
        "",
        f"Stem: `{report['stem']}`",
        f"MIDI: `{report['midi']}`",
        f"Role: `{report['kind']}`",
        "",
        "## Source-event cluster review",
        "",
        (
            f"{report['source_evidence']['event_clusters']['source_event_count']} "
            "MIDI-aligned events produced "
            f"{report['source_evidence']['event_clusters']['identity_candidate_cluster_count']} "
            "candidate timbre families, "
            f"{report['source_evidence']['event_clusters']['articulation_cluster_count']} "
            "articulation groups and "
            f"{report['source_evidence']['event_clusters']['identity_outlier_count']} "
            "retained outliers."
        ),
        "",
        "Open `source_event_clusters.svg` for the pitch/timeline view and `source_event_clusters.json` for per-event evidence. Clusters and outliers are advisory; no MIDI note or ranking changed.",
        "",
        "## Velocity-layer and alternate-sample review",
        "",
        (
            f"{report['source_evidence']['event_dynamics']['velocity_layer_candidate_unit_count']} "
            "comparable units have a two-layer source-loudness candidate; "
            f"{report['source_evidence']['event_dynamics']['round_robin_candidate_set_count']} "
            "layers have isolated round-robin candidates."
        ),
        "",
        "Open `source_event_dynamics.svg` for the source-RMS timeline and `source_event_dynamics.json` for event indices and thresholds. No MIDI velocity, sample, SoundFont zone or drum mapping changed.",
        "",
        "## Installed GarageBand factory-sample matches",
        "",
        "| Rank | Asset | Audio | Role prior | Combined | Evidence |",
        "| ---: | --- | ---: | ---: | ---: | --- |",
    ]
    for row in report["garageband_factory_matches"]:
        lines.append(
            f"| {row['rank']} | {row['asset_name']} | {row['audio_similarity']:.1f} | "
            f"{row['role_name_prior']:.1f} | {row['combined_score']:.1f} | "
            f"{'; '.join(row['comparison'])} |"
        )
    if not report["garageband_factory_matches"]:
        lines.append("| — | No readable factory-sample match | — | — | — | — |")
    lines.extend(
        [
            "",
            "## Rendered General MIDI proxy matches",
            "",
            "| Rank | Program | Instrument | Score | Spectral | Dynamics | Attack |",
            "| ---: | ---: | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in report["gm_rendered_matches"]:
        lines.append(
            f"| {row['rank']} | {row['patch_number']} | {row['name']} | "
            f"{row['combined_score']:.1f} | {row['spectral_shape_similarity']:.1f} | "
            f"{row['dynamics_similarity']:.1f} | {row['attack_similarity']:.1f} |"
        )
    if not report["gm_rendered_matches"]:
        lines.append("| — | — | No rendered proxy match | — | — | — | — |")
    lines.extend(
        [
            "",
            "## Optional learned OpenL3 proxy matches",
            "",
            "| Rank | Program | Instrument | Embedding | Active windows | p10 | p90 |",
            "| ---: | ---: | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in report["gm_learned_embedding_matches"]:
        lines.append(
            f"| {row['rank']} | {row['patch_number']} | {row['name']} | "
            f"{row['embedding_similarity']:.1f} | {row['active_window_count']} | "
            f"{row['p10_similarity']:.1f} | {row['p90_similarity']:.1f} |"
        )
    if not report["gm_learned_embedding_matches"]:
        lines.append("| — | — | Not requested | — | — | — | — |")
    drum_mapping = report.get("gm_drum_family_mapping")
    if drum_mapping:
        lines.extend(
            [
                "",
                "## Review-only GM drum-family proposal",
                "",
                (
                    f"{drum_mapping['candidate_timbre_family_count']} family/note "
                    "mapping units from "
                    f"{drum_mapping['source_identity_cluster_count']} source "
                    "timbre families were scored. The proposal uses "
                    f"{drum_mapping['distinct_assigned_note_count']} distinct GM "
                    "drum notes. "
                    f"{drum_mapping['proposed_note_change_count']} note pitches "
                    "differ in the proposed copy."
                ),
                "",
                "Listen to `drum_family_mapping.proposed.wav`, then drag `drum_family_mapping.proposed.mid` into GarageBand only if the separated kit pieces are useful. The supplied MIDI was not overwritten; outliers and unanalyzed events retain their original notes.",
                "",
                "Open `gm_drum_family_mapping.json` for every candidate score and `drum_note_auditions/` for the assigned one-shots.",
            ]
        )
    lines.extend(
        [
            "",
            "## Installed Audio Unit instruments",
            "",
        ]
    )
    for item in report["installed_audio_unit_instruments"]:
        manufacturer = item.get("manufacturer") or "Unknown manufacturer"
        lines.append(f"- {manufacturer}: {item['display_name']}")
    lines.extend(
        [
            "",
            "## How to audition",
            "",
            *[
                f"{index}. {value}"
                for index, value in enumerate(report["garageband_handoff"], 1)
            ],
            "",
            "The scores are relative evidence for this stem and candidate set. They are not percentages of certainty.",
        ]
    )
    return "\n".join(lines) + "\n"


def _sample_pack_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Sunofriend Sample Instrument v2",
        "",
        f"Source stem: `{report['stem']}`",
        f"Aligned MIDI: `{report['midi']}`",
        f"Samples: {report['sample_count']}",
        f"GarageBand-selectable preset: `{report['artifacts']['ausampler_preset'] or 'not created on this system'}`",
        f"Self-contained SoundFont bank: `{report['artifacts']['soundfont']}`",
        "",
        "## Direct GarageBand import",
        "",
        *[
            f"{index}. {step}"
            for index, step in enumerate(report["garageband_import"], 1)
        ],
        "",
        "GarageBand's AUSampler preset chooser filters for `.aupreset`; it does not directly select the `.sf2` bank.",
        "The preset is a small wrapper that points AUSampler to the SF2. Keep both at their generated paths.",
        "The SF2 is self-contained: its PCM16 audio, MIDI root keys, keyboard zones and velocity ranges are embedded in one file.",
        "The separate PCM24 WAV files and SFZ mapping are retained for editing or other samplers.",
        "",
        "## Source-event review",
        "",
        (
            f"{report['source_event_clusters']['source_event_count']} candidate events "
            f"produced {report['source_event_clusters']['identity_candidate_cluster_count']} "
            "candidate timbre families, "
            f"{report['source_event_clusters']['articulation_cluster_count']} articulation "
            f"groups and {report['source_event_clusters']['identity_outlier_count']} retained outliers."
        ),
        "",
        "Open `source_event_clusters.svg` for the timeline and `source_event_clusters.json` before deciding whether a rare event is a useful articulation, bleed or an artefact. v1 did not remove any sample automatically.",
        "",
        "## Candidate dynamics and alternates",
        "",
        (
            f"{report['source_event_dynamics']['velocity_layer_candidate_unit_count']} "
            "comparable units have a two-layer source-loudness candidate; "
            f"{report['source_event_dynamics']['round_robin_candidate_set_count']} "
            "layers have isolated round-robin candidates."
        ),
        "",
        "Open `source_event_dynamics.svg` and `source_event_dynamics.json` to review them. Sample Instrument v2 did not add these events or alter any velocity range automatically.",
        "",
        "## Advisory sustain loops",
        "",
        (
            f"{report['sample_loop_suggestions']['candidate_sample_count']} samples "
            f"have {report['sample_loop_suggestions']['suggested_loop_count']} "
            "ranked boundary suggestions."
        ),
        "",
        "Open `source_sample_loops.svg` and `source_sample_loops.json`, then listen to any `loop-auditions/` WAVs. The auditions repeat raw boundaries without a crossfade so clicks and timbre changes remain audible. No loop was added to the SF2 or SFZ.",
        "",
        "## Zones and tuning",
        "",
        "| Root | Keys | Source | Tuning status | SF2 correction |",
        "| ---: | --- | --- | --- | ---: |",
        *[
            f"| {row['pitch']} | {row['low_key']}–{row['high_key']} | `{row['file']}` | "
            f"{row['tuning']['status']} | {row['tuning']['pitch_correction_cents']:+d} cents |"
            for row in report["samples"]
        ],
        "",
        "## Warnings",
        "",
        *[f"- {warning}" for warning in report["warnings"]],
    ]
    return "\n".join(lines) + "\n"


def _profile_svg(
    source: tuple[float, ...],
    matches: Sequence[FactoryInstrumentMatch],
) -> str:
    import numpy as np

    series = [
        ("Source stem", source),
        *[(row.asset_name, row.timbre_profile) for row in matches],
    ]
    matrix = np.asarray([values for _, values in series], dtype=float)
    mean = np.mean(matrix, axis=0)
    scale = np.std(matrix, axis=0)
    scale = np.where(scale < 0.025, 0.025, scale)
    standardized = np.clip((matrix - mean) / scale, -2.5, 2.5)
    width, height = 1200, 520
    left, right, top, bottom = 70, 30, 50, 155
    plot_width = width - left - right
    plot_height = height - top - bottom
    colors = ("#ff6b6b", "#23c9ff", "#ffd166", "#8ce99a")
    chunks = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#101820"/>',
        '<text x="70" y="28" fill="#ffffff" font-family="sans-serif" font-size="18">Relative timbre profile (z-score within this shortlist)</text>',
    ]
    for grid in range(6):
        y = top + grid * plot_height / 5
        chunks.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="#34495e" stroke-width="1"/>'
        )
    for feature_index, name in enumerate(FEATURE_NAMES):
        x = left + feature_index * plot_width / max(1, len(FEATURE_NAMES) - 1)
        chunks.append(
            f'<text x="{x:.1f}" y="{height - bottom + 18}" fill="#b8c4ce" font-family="sans-serif" font-size="10" transform="rotate(55 {x:.1f} {height - bottom + 18})">{html.escape(name)}</text>'
        )
    for series_index, ((label, _), values) in enumerate(zip(series, standardized)):
        points = []
        for feature_index, value in enumerate(values):
            x = left + feature_index * plot_width / max(1, len(FEATURE_NAMES) - 1)
            y = top + (2.5 - float(value)) / 5.0 * plot_height
            points.append(f"{x:.1f},{y:.1f}")
        color = colors[series_index % len(colors)]
        chunks.append(
            f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="2.5"/>'
        )
        legend_y = height - 18 - series_index * 20
        chunks.append(
            f'<line x1="{left}" y1="{legend_y}" x2="{left + 24}" y2="{legend_y}" stroke="{color}" stroke-width="3"/>'
        )
        chunks.append(
            f'<text x="{left + 32}" y="{legend_y + 4}" fill="#ffffff" font-family="sans-serif" font-size="12">{html.escape(label)}</text>'
        )
    chunks.append("</svg>")
    return "\n".join(chunks) + "\n"


def _named_profile(values: Sequence[float]) -> dict[str, float]:
    return {name: round(float(value), 8) for name, value in zip(FEATURE_NAMES, values)}


def _median_vector(vectors: Sequence[Sequence[float]]) -> tuple[float, ...]:
    import numpy as np

    if not vectors:
        raise ValueError("At least one timbre vector is required")
    return tuple(float(value) for value in np.median(np.asarray(vectors), axis=0))


def _median(values: Iterable[int | float]) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("At least one value is required")
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_token(value: str) -> str:
    cleaned = "".join(
        character if character.isalnum() else "-" for character in value.casefold()
    )
    return "-".join(part for part in cleaned.split("-") if part) or "instrument"


__all__ = [
    "FEATURE_NAMES",
    "FactoryInstrumentMatch",
    "GmProgramMatch",
    "LearnedGmProgramMatch",
    "build_sample_pack",
    "match_instruments",
]
