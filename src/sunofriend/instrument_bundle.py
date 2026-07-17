"""Portable instrument, sound, and audition handoff for one MIDI part.

Standard MIDI carries performance and program-selection messages, not the
sampled sound that ultimately plays them.  Instrument Bundle v1 keeps those
separate concerns together without pretending that a GarageBand factory patch
can be embedded in a ``.mid`` file or redistributed.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any


BUNDLE_FORMAT = "sunofriend-instrument-bundle-v1"


def build_instrument_bundle(
    stem_path: str | Path,
    midi_path: str | Path,
    *,
    kind: str,
    out_dir: str | Path,
    track_index: int | None = None,
    top: int = 5,
    garageband_sampler_root: str | Path | None = None,
    logic_drum_root: str | Path | None = None,
    include_factory: bool = True,
    include_gm: bool = True,
    include_source_audio: bool = True,
    build_source_instrument: bool = True,
    render_preview: bool = True,
    allow_polyphonic: bool = False,
    max_samples: int = 12,
    tail_ms: float = 120.0,
    max_transpose: int = 6,
    auto_tune: bool = True,
    instrument_name: str | None = None,
    embedding_model_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build one self-describing GarageBand instrument handoff directory.

    Matching and source-derived sampling are deliberately independent.  A
    noisy or polyphonic stem can still produce a useful match shortlist even
    when it cannot safely become a sample instrument.  Such a bundle is
    reported as ``partial`` with the exact failure retained in ``warnings``.
    """

    stem = Path(stem_path).expanduser()
    midi = Path(midi_path).expanduser()
    destination = Path(out_dir).expanduser()
    if not stem.is_file():
        raise ValueError(f"Stem WAV not found: {stem}")
    if not midi.is_file():
        raise ValueError(f"MIDI file not found: {midi}")
    if destination.exists():
        raise ValueError(f"Output directory already exists: {destination}")
    if top <= 0:
        raise ValueError("top must be positive")

    destination.mkdir(parents=True)
    warnings: list[str] = []
    try:
        performance_path = destination / "performance.mid"
        shutil.copy2(midi, performance_path)

        source_reference = None
        if include_source_audio:
            source_reference = destination / "source-reference.wav"
            shutil.copy2(stem, source_reference)

        match_report = None
        match_error = None
        matches_dir = destination / "matches"
        try:
            from .instrument_match import match_instruments

            match_report = match_instruments(
                stem,
                midi,
                kind=kind,
                out_dir=matches_dir,
                top=top,
                track_index=track_index,
                garageband_sampler_root=garageband_sampler_root,
                logic_drum_root=logic_drum_root,
                include_factory=include_factory,
                include_gm=include_gm,
                embedding_model_path=embedding_model_path,
            )
        except Exception as exc:
            if embedding_model_path is not None:
                raise
            match_error = f"{type(exc).__name__}: {exc}"
            warnings.append(f"Instrument matching was unavailable: {match_error}")

        sample_report = None
        sample_error = None
        source_instrument_dir = destination / "source-instrument"
        if build_source_instrument:
            try:
                from .instrument_match import build_sample_pack

                sample_report = build_sample_pack(
                    stem,
                    midi,
                    kind=kind,
                    out_dir=source_instrument_dir,
                    track_index=track_index,
                    max_samples=max_samples,
                    tail_ms=tail_ms,
                    allow_polyphonic=allow_polyphonic,
                    instrument_name=instrument_name,
                    render_preview=render_preview,
                    max_transpose=max_transpose,
                    auto_tune=auto_tune,
                    embedding_model_path=embedding_model_path,
                )
            except Exception as exc:
                sample_error = f"{type(exc).__name__}: {exc}"
                warnings.append(
                    "Source-derived instrument was unavailable: " + sample_error
                )

        previews_dir = destination / "previews"
        previews_dir.mkdir()
        source_performance_preview = None
        source_performance_midi = None
        if sample_report is not None and render_preview:
            try:
                from .clip import Instrument, read_midi_clips, write_clip_midi
                from .render import render_midi_to_wav

                clips = list(read_midi_clips(midi))
                selected_index = int(sample_report["track"]["selected_index"])
                clip = clips[selected_index]
                preview_clip = replace(
                    clip,
                    instrument=Instrument(
                        role=clip.instrument.role,
                        program=0,
                        channel=0,
                        suggestions=clip.instrument.suggestions,
                    ),
                )
                source_performance_midi = (
                    previews_dir / "source-derived-performance.mid"
                )
                write_clip_midi(source_performance_midi, preview_clip)
                source_performance_preview = (
                    previews_dir / "source-derived-performance.wav"
                )
                render_midi_to_wav(
                    source_performance_midi,
                    source_performance_preview,
                    soundfont_path=(
                        source_instrument_dir / "sunofriend-instrument.sf2"
                    ),
                )
            except Exception as exc:
                source_performance_preview = None
                if source_performance_midi is not None:
                    source_performance_midi.unlink(missing_ok=True)
                source_performance_midi = None
                warnings.append(
                    "Source-derived full-performance preview was unavailable: "
                    f"{type(exc).__name__}: {exc}"
                )

        best_gm_preview = _copy_best_gm_preview(
            match_report, matches_dir=matches_dir, previews_dir=previews_dir
        )
        best_embedding_preview = _copy_best_embedding_preview(
            match_report, matches_dir=matches_dir, previews_dir=previews_dir
        )
        drum_proposal_midi, drum_proposal_preview = _copy_drum_family_proposal(
            match_report, matches_dir=matches_dir, previews_dir=previews_dir
        )
        if not any(previews_dir.iterdir()):
            previews_dir.rmdir()

        factory_matches = (
            list(match_report.get("garageband_factory_matches", []))
            if match_report
            else []
        )
        gm_matches = (
            list(match_report.get("gm_rendered_matches", [])) if match_report else []
        )
        embedding_matches = (
            list(match_report.get("gm_learned_embedding_matches", []))
            if match_report
            else []
        )
        best_gm = gm_matches[0] if gm_matches else None
        best_embedding = embedding_matches[0] if embedding_matches else None
        best_factory = factory_matches[0] if factory_matches else None
        drum_family_mapping = (
            match_report.get("gm_drum_family_mapping") if match_report else None
        )
        recipe = {
            "format": BUNDLE_FORMAT,
            "format_version": 1,
            "kind": str(kind).strip().lower(),
            "performance": {
                "midi": "performance.mid",
                "source_midi": str(midi.resolve()),
                "portable_program_hint": (
                    {
                        "program_zero_based": best_gm["program"],
                        "patch_number": best_gm["patch_number"],
                        "name": best_gm["name"],
                    }
                    if best_gm
                    else None
                ),
                "review_drum_family_proposal": (
                    str(Path("matches") / "drum_family_mapping.proposed.mid")
                    if drum_family_mapping
                    else None
                ),
            },
            "sound": {
                "source_reference": (
                    source_reference.name if source_reference is not None else None
                ),
                "source_instrument": (
                    {
                        "directory": "source-instrument",
                        "ausampler_preset": sample_report["artifacts"].get(
                            "ausampler_preset"
                        ),
                        "soundfont": sample_report["artifacts"]["soundfont"],
                        "sfz": sample_report["artifacts"]["sfz"],
                        "sample_count": sample_report["sample_count"],
                        "source_event_clusters": sample_report["source_event_clusters"],
                        "source_event_dynamics": sample_report["source_event_dynamics"],
                        "source_event_dynamics_report": str(
                            Path("source-instrument") / "source_event_dynamics.json"
                        ),
                        "source_event_dynamics_graph": str(
                            Path("source-instrument") / "source_event_dynamics.svg"
                        ),
                        "sample_loop_suggestions": sample_report.get(
                            "sample_loop_suggestions"
                        ),
                        "sample_loop_suggestions_report": str(
                            Path("source-instrument") / "source_sample_loops.json"
                        ),
                        "sample_loop_suggestions_graph": str(
                            Path("source-instrument") / "source_sample_loops.svg"
                        ),
                        "sample_loop_auditions": (
                            str(Path("source-instrument") / "loop-auditions")
                            if sample_report["artifacts"].get(
                                "sample_loop_auditions"
                            )
                            else None
                        ),
                    }
                    if sample_report
                    else None
                ),
                "source_instrument_error": sample_error,
            },
            "match": {
                "directory": "matches" if match_report is not None else None,
                "best_garageband_factory_asset": best_factory,
                "best_rendered_gm_proxy": best_gm,
                "best_learned_embedding_proxy": best_embedding,
                "factory_candidates": factory_matches,
                "gm_candidates": gm_matches,
                "learned_embedding_candidates": embedding_matches,
                "learned_embedding_evidence": (
                    str(Path("matches") / "openl3_embedding_evidence.json")
                    if embedding_matches
                    else None
                ),
                "source_event_clusters": (
                    str(Path("matches") / "source_event_clusters.json")
                    if match_report
                    else None
                ),
                "source_event_clusters_graph": (
                    str(Path("matches") / "source_event_clusters.svg")
                    if match_report
                    else None
                ),
                "source_event_cluster_summary": (
                    match_report.get("source_evidence", {}).get("event_clusters")
                    if match_report
                    else None
                ),
                "source_event_dynamics": (
                    str(Path("matches") / "source_event_dynamics.json")
                    if match_report
                    else None
                ),
                "source_event_dynamics_graph": (
                    str(Path("matches") / "source_event_dynamics.svg")
                    if match_report
                    else None
                ),
                "source_event_dynamics_summary": (
                    match_report.get("source_evidence", {}).get("event_dynamics")
                    if match_report
                    else None
                ),
                "gm_drum_family_mapping": (
                    str(Path("matches") / "gm_drum_family_mapping.json")
                    if drum_family_mapping
                    else None
                ),
                "gm_drum_family_mapping_summary": drum_family_mapping,
                "error": match_error,
                "interpretation": (
                    "Relative audition evidence only; a factory asset name may not "
                    "equal the GarageBand Library patch name."
                ),
            },
            "previews": {
                "source_derived_midi": (
                    str(Path("previews") / source_performance_midi.name)
                    if source_performance_midi is not None
                    else None
                ),
                "source_derived_performance": (
                    str(Path("previews") / source_performance_preview.name)
                    if source_performance_preview is not None
                    else None
                ),
                "best_rendered_gm": (
                    str(Path("previews") / best_gm_preview.name)
                    if best_gm_preview is not None
                    else None
                ),
                "best_learned_embedding_gm": (
                    str(Path("previews") / best_embedding_preview.name)
                    if best_embedding_preview is not None
                    else None
                ),
                "gm_drum_family_proposed_midi": (
                    str(Path("previews") / drum_proposal_midi.name)
                    if drum_proposal_midi is not None
                    else None
                ),
                "gm_drum_family_proposed_wav": (
                    str(Path("previews") / drum_proposal_preview.name)
                    if drum_proposal_preview is not None
                    else None
                ),
            },
            "garageband": {
                "steps": _garageband_steps(
                    sample_report,
                    best_factory,
                    best_gm,
                    best_embedding,
                    drum_family_mapping,
                ),
                "factory_content_embedded": False,
                "reason": (
                    "Apple factory content is referenced as a recommendation, not copied. "
                    "The source-derived SF2 is the portable sound when it could be built."
                ),
            },
            "warnings": warnings,
        }
        recipe_path = destination / "instrument_recipe.json"
        _write_json(recipe_path, recipe)

        status = (
            "complete"
            if match_report is not None
            and (not build_source_instrument or sample_report is not None)
            else "partial"
        )
        report = {
            "operation": "instrument-bundle",
            "format": BUNDLE_FORMAT,
            "format_version": 1,
            "status": status,
            "stem": str(stem.resolve()),
            "midi": str(midi.resolve()),
            "kind": str(kind).strip().lower(),
            "artifacts": {
                "performance_midi": "performance.mid",
                "source_reference": (
                    source_reference.name if source_reference is not None else None
                ),
                "instrument_recipe": "instrument_recipe.json",
                "readme": "README.md",
                "matches": "matches" if match_report is not None else None,
                "source_instrument": (
                    "source-instrument" if sample_report is not None else None
                ),
                "previews": "previews" if previews_dir.exists() else None,
            },
            "match_status": (
                match_report.get("status") if match_report is not None else "error"
            ),
            "source_instrument_status": (
                "skipped"
                if not build_source_instrument
                else (
                    sample_report.get("status")
                    if sample_report is not None
                    else "error"
                )
            ),
            "warnings": warnings,
        }
        _write_json(destination / "instrument_bundle.json", report)
        (destination / "README.md").write_text(
            _bundle_markdown(report, recipe), encoding="utf-8"
        )
        report["report"] = str(destination / "instrument_bundle.json")
        report["recipe"] = str(recipe_path)
        return report
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def _copy_best_gm_preview(
    match_report: dict[str, Any] | None,
    *,
    matches_dir: Path,
    previews_dir: Path,
) -> Path | None:
    if not match_report:
        return None
    matches = list(match_report.get("gm_rendered_matches", []))
    if not matches:
        return None
    source = matches_dir / str(matches[0].get("preview_wav", ""))
    if not source.is_file():
        return None
    output = previews_dir / "best-matched-gm.wav"
    shutil.copy2(source, output)
    return output


def _copy_best_embedding_preview(
    match_report: dict[str, Any] | None,
    *,
    matches_dir: Path,
    previews_dir: Path,
) -> Path | None:
    if not match_report:
        return None
    matches = list(match_report.get("gm_learned_embedding_matches", []))
    if not matches:
        return None
    source = matches_dir / str(matches[0].get("preview_wav", ""))
    if not source.is_file():
        return None
    output = previews_dir / "best-openl3-matched-gm.wav"
    shutil.copy2(source, output)
    return output


def _copy_drum_family_proposal(
    match_report: dict[str, Any] | None,
    *,
    matches_dir: Path,
    previews_dir: Path,
) -> tuple[Path | None, Path | None]:
    if not match_report or not match_report.get("gm_drum_family_mapping"):
        return None, None
    source_midi = matches_dir / "drum_family_mapping.proposed.mid"
    source_wav = matches_dir / "drum_family_mapping.proposed.wav"
    if not source_midi.is_file() or not source_wav.is_file():
        return None, None
    output_midi = previews_dir / "gm-drum-family-proposal.mid"
    output_wav = previews_dir / "gm-drum-family-proposal.wav"
    shutil.copy2(source_midi, output_midi)
    shutil.copy2(source_wav, output_wav)
    return output_midi, output_wav


def _garageband_steps(
    sample_report: dict[str, Any] | None,
    best_factory: dict[str, Any] | None,
    best_gm: dict[str, Any] | None,
    best_embedding: dict[str, Any] | None,
    drum_family_mapping: dict[str, Any] | None,
) -> list[str]:
    steps = [
        "Drag performance.mid into the GarageBand Tracks area at the project origin.",
        "Set the project BPM to the value already embedded in the MIDI before comparing it with the untreated source stem.",
    ]
    if sample_report and sample_report["artifacts"].get("ausampler_preset"):
        steps.extend(
            [
                "For the carried source sound, choose AU Instruments > Apple > AUSampler > Stereo.",
                "From AUSampler's Manual preset menu load source-instrument/sunofriend-instrument.aupreset; keep it beside its SF2 bank.",
            ]
        )
    if best_factory:
        steps.append(
            "For the installed-sound match, search the GarageBand Library for or near "
            f"'{best_factory['asset_name']}', then audition it in the complete mix."
        )
    if best_gm:
        steps.append(
            "Use the portable GM fallback "
            f"'{best_gm['name']}' (program {best_gm['patch_number']}) as an audition hint, not an exact GarageBand patch."
        )
    if best_embedding:
        steps.append(
            "Also audition the independent OpenL3 hint "
            f"'{best_embedding['name']}' (program {best_embedding['patch_number']}); "
            "its learned score did not alter the explainable GM order."
        )
    if drum_family_mapping:
        steps.append(
            "For separated drum-hit families, audition "
            "previews/gm-drum-family-proposal.mid and its WAV against "
            "performance.mid. It is a review copy; accept or edit its channel-10 "
            "notes only after listening with the intended GarageBand kit."
        )
    steps.append(
        "Compare the source reference, source-derived preview, and matched preview at similar loudness before saving a custom GarageBand patch."
    )
    return steps


def _write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _bundle_markdown(report: dict[str, Any], recipe: dict[str, Any]) -> str:
    source_sound = recipe["sound"]["source_instrument"]
    best_factory = recipe["match"]["best_garageband_factory_asset"]
    best_gm = recipe["match"]["best_rendered_gm_proxy"]
    best_embedding = recipe["match"]["best_learned_embedding_proxy"]
    event_clusters = recipe["match"].get("source_event_cluster_summary") or {}
    event_dynamics = recipe["match"].get("source_event_dynamics_summary") or {}
    drum_mapping = recipe["match"].get("gm_drum_family_mapping_summary") or {}
    lines = [
        "# Sunofriend Instrument Bundle v1",
        "",
        f"Status: **{report['status']}**",
        f"Role: `{report['kind']}`",
        "",
        "This directory keeps editable MIDI, carried source sound, match evidence, and listening previews together. A MIDI file alone does not contain the sampler audio.",
        "",
        "## Included sound and matches",
        "",
        f"- Source-derived playable instrument: {'yes' if source_sound else 'not available'}",
        f"- Best installed GarageBand asset: {best_factory['asset_name'] if best_factory else 'no match retained'}",
        f"- Best rendered GM proxy: {best_gm['name'] if best_gm else 'no match retained'}",
        f"- Best optional OpenL3 proxy: {best_embedding['name'] if best_embedding else 'not requested'}",
        (
            "- Review-only GM drum-family proposal: "
            f"{drum_mapping.get('candidate_timbre_family_count', 0)} family/note units / "
            f"{drum_mapping.get('distinct_assigned_note_count', 0)} distinct notes / "
            f"{drum_mapping.get('proposed_note_change_count', 0)} proposed changes"
            if drum_mapping
            else "- Review-only GM drum-family proposal: not applicable"
        ),
        (
            "- Source-event review: "
            f"{event_clusters.get('identity_candidate_cluster_count', 0)} candidate "
            "timbre families, "
            f"{event_clusters.get('articulation_cluster_count', 0)} articulation groups, "
            f"{event_clusters.get('identity_outlier_count', 0)} retained outliers"
        ),
        (
            "- Candidate dynamics: "
            f"{event_dynamics.get('velocity_layer_candidate_unit_count', 0)} "
            "two-layer units, "
            f"{event_dynamics.get('round_robin_candidate_set_count', 0)} "
            "round-robin sets; advisory only"
        ),
        "- Apple factory samples embedded: no",
        "",
        "## GarageBand",
        "",
        *[
            f"{index}. {step}"
            for index, step in enumerate(recipe["garageband"]["steps"], 1)
        ],
        "",
        "## Warnings",
        "",
        *([f"- {item}" for item in report["warnings"]] or ["- None"]),
    ]
    return "\n".join(lines) + "\n"


__all__ = ["BUNDLE_FORMAT", "build_instrument_bundle"]
