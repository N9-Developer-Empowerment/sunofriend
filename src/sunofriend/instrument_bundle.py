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
            )
        except Exception as exc:
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
        best_gm = gm_matches[0] if gm_matches else None
        best_factory = factory_matches[0] if factory_matches else None
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
                "factory_candidates": factory_matches,
                "gm_candidates": gm_matches,
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
            },
            "garageband": {
                "steps": _garageband_steps(sample_report, best_factory, best_gm),
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


def _garageband_steps(
    sample_report: dict[str, Any] | None,
    best_factory: dict[str, Any] | None,
    best_gm: dict[str, Any] | None,
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
