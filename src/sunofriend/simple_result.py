"""Publish an automatic, unreviewed MIDI and balanced-WAV starter bundle."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .automatic_selection import AutomaticSelectionPlan
from .midi import write_midi_file
from .simple_instruments import build_simple_instrument_handoff
from .workbench_artifacts import WorkbenchArtifacts, build_arrangement_tracks
from .workbench_mix import BALANCED_MIX_POLICY, build_balanced_midi_audition


SIMPLE_RESULT_SCHEMA = "sunofriend.simple-result.v1"
SIMPLE_RESULT_DIRECTORY = "AUTOMATIC-SONG"


class SimpleResultError(RuntimeError):
    """The automatic starter bundle could not be verified and published."""


@dataclass(frozen=True)
class SimpleResult:
    """Verified paths and public facts for one completed starter bundle."""

    root: Path
    zip_path: Path
    combined_midi_path: Path
    balanced_wav_path: Path
    manifest_path: Path
    selected_count: int
    omitted_count: int
    manifest_sha256: str
    instrument_plan_path: Path | None = None
    instrument_guide_path: Path | None = None


def build_simple_result(
    catalog: Mapping[str, Any],
    plan: AutomaticSelectionPlan,
    *,
    destination: str | Path,
    artifact_cache_root: str | Path,
    soundfont_path: str | Path | None = None,
) -> SimpleResult:
    """Build and atomically publish a separately labelled Simple result."""

    target = Path(destination).expanduser().resolve()
    if target.exists() or target.is_symlink():
        raise SimpleResultError(
            "the automatic result destination already exists; choose a fresh output"
        )
    if not target.parent.is_dir():
        raise SimpleResultError("the automatic result parent folder does not exist")
    bpm = _project_bpm(catalog)
    work = Path(
        tempfile.mkdtemp(prefix=f".{target.name}.building-", dir=target.parent)
    ).resolve()
    try:
        midi_root = work / "MIDI"
        audio_root = work / "AUDIO"
        technical_root = work / "TECHNICAL"
        midi_root.mkdir()
        audio_root.mkdir()
        technical_root.mkdir()

        musical_metadata_record: dict[str, Any] | None = None
        musical_metadata = catalog.get("setup", {}).get(
            "musical_metadata_analysis"
        )
        if isinstance(musical_metadata, Mapping):
            from .musical_metadata import validate_musical_metadata_analysis

            validate_musical_metadata_analysis(musical_metadata)
            musical_metadata_path = (
                technical_root / "automatic-musical-metadata.json"
            )
            _write_json(musical_metadata_path, musical_metadata)
            musical_metadata_record = _relative_record(
                musical_metadata_path, work
            )

        artifacts = WorkbenchArtifacts(
            artifact_cache_root,
            soundfont_path=soundfont_path,
        )
        lanes: list[dict[str, Any]] = []
        selected_files: list[dict[str, Any]] = []
        for item in plan.selected:
            _verify_selection_inputs(item)
            preview = artifacts.cached_candidate_preview(
                catalog,
                str(item["stem_id"]),
                str(item["candidate_id"]),
                role_override=str(item["role"]),
            )
            if preview is None:
                preview = artifacts.render_candidate_preview(
                    catalog,
                    str(item["stem_id"]),
                    str(item["candidate_id"]),
                    role_override=str(item["role"]),
                )
            preview_record = preview.get("preview")
            if not isinstance(preview_record, Mapping):
                raise SimpleResultError(
                    "the neutral automatic MIDI preview has no verified audio record"
                )
            preview_path = _verify_record(
                preview_record,
                label="neutral automatic MIDI preview",
            )
            archive_member = str(item["garageband_pack_archive_member"])
            output_midi = (work / archive_member).resolve()
            _require_within(output_midi, midi_root)
            _copy_verified(
                Path(item["midi_path"]),
                output_midi,
                expected=item["midi"],
                label="automatic primary MIDI",
            )
            selected_files.append(
                {
                    "selection_index": int(item["selection_index"]),
                    "stem_id": str(item["stem_id"]),
                    "candidate_id": str(item["candidate_id"]),
                    "role": str(item["role"]),
                    "process": item.get("process"),
                    "selection_basis": "automatic_primary",
                    "review_status": "not_reviewed",
                    "output": _relative_record(output_midi, work),
                }
            )
            lanes.append(
                {
                    "track_id": (
                        f"automatic-{int(item['selection_index']):02d}-"
                        f"{str(item['midi']['sha256'])[:16]}"
                    ),
                    "stem_id": str(item["stem_id"]),
                    "candidate_id": str(item["candidate_id"]),
                    "role": str(item["role"]),
                    "decision": "automatic-baseline",
                    "selection_index": int(item["selection_index"]),
                    "garageband_pack_archive_member": archive_member,
                    "source_path": str(item["source_path"]),
                    "source_sha256": str(item["source"]["sha256"]),
                    "source_bytes": int(item["source"]["bytes"]),
                    "source_midi_sha256": str(item["midi"]["sha256"]),
                    "preview_path": str(preview_path),
                    "preview_sha256": str(preview_record["sha256"]),
                    "preview_bytes": int(preview_record["bytes"]),
                    "neutral_preview_cache_key": str(preview["cache_key"]),
                }
            )

        combined_midi = midi_root / "combined-gm-interpretation.mid"
        tracks = build_arrangement_tracks(plan.selected)
        write_midi_file(combined_midi, tracks, bpm=bpm)
        combined_record = _relative_record(combined_midi, work)
        instrument_handoff = build_simple_instrument_handoff(
            plan.selected,
            lanes,
            tracks,
            root=work,
            bpm=bpm,
        )

        balanced_wav = audio_root / "balanced-midi-song-interpretation.wav"
        balanced_report = technical_root / "balanced-mix-report.json"
        mix_recipe = work / "garageband-mix-recipe.md"
        output_frames, project_source_horizons = _project_source_horizon(
            catalog,
            lanes,
        )
        mix_report = build_balanced_midi_audition(
            lanes,
            output_path=balanced_wav,
            report_path=balanced_report,
            recipe_path=mix_recipe,
            output_frames=output_frames,
        )
        for item in plan.selected:
            _verify_selection_inputs(item)

        output_records = {
            "combined_midi": combined_record,
            "balanced_wav": _relative_record(balanced_wav, work),
            "mix_report": _relative_record(balanced_report, work),
            "garageband_mix_recipe": _relative_record(mix_recipe, work),
            "instrument_plan": instrument_handoff["plan_record"],
            "instrument_guide": instrument_handoff["guide_record"],
        }
        if musical_metadata_record is not None:
            output_records["automatic_musical_metadata"] = (
                musical_metadata_record
            )
        manifest_payload = {
            "schema": SIMPLE_RESULT_SCHEMA,
            "workflow_status": "automatic_complete",
            "project_id": str(catalog.get("project_id") or ""),
            "project": {
                "name": catalog.get("name"),
                "bpm": bpm,
                "key": catalog.get("setup", {}).get("key"),
                "tuning_hz": catalog.get("setup", {}).get("tuning_hz"),
                "automatic_metadata_evidence_included": (
                    musical_metadata_record is not None
                ),
            },
            "selection": plan.receipt,
            "selected_midi": selected_files,
            "omitted": list(plan.omitted),
            "outputs": output_records,
            "instrument_handoff": {
                "schema": instrument_handoff["plan"]["schema"],
                "policy": instrument_handoff["plan"]["policy"],
                "automatic": True,
                "review_status": "not_reviewed",
                "review_recommended": True,
                "track_count": len(instrument_handoff["plan"]["tracks"]),
                "factory_patch_selected": False,
                "native_garageband_patch_embedded": False,
                "source_midi_mutated": False,
            },
            "mix": {
                "policy": BALANCED_MIX_POLICY,
                "report_schema": mix_report["schema"],
                "source_audio_mixed_into_wav": False,
                "mastered": False,
                "release_master": False,
                "quality_status": "review_recommended",
                "output_frames": output_frames,
                "output_sample_rate": project_source_horizons[0][
                    "output_sample_rate"
                ],
                "project_source_horizons": project_source_horizons,
            },
            "studio_review": {
                "status": "not_reviewed",
                "next_step": (
                    "Open the same source and result root in Studio to compare "
                    "alternatives and replace automatic defaults."
                ),
            },
            "path_free_receipt": True,
            "effects": {
                "automatic_selection": True,
                "automatic_ranking": False,
                "human_decision_events": 0,
                "workbench_state_changed": False,
                "feedback_recorded": False,
                "source_audio_mutated": False,
                "source_midi_mutated": False,
            },
        }
        manifest = {
            **manifest_payload,
            "manifest_sha256": _document_hash(manifest_payload),
        }
        manifest_path = work / "sunofriend-result.json"
        _write_json(manifest_path, manifest)
        (work / "START-HERE.txt").write_text(
            _start_here_text(manifest), encoding="utf-8"
        )

        zip_path = work / "sunofriend-automatic-midi-and-wav.zip"
        _write_deterministic_zip(zip_path, work)
        work.replace(target)
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise

    final_manifest = target / "sunofriend-result.json"
    document = json.loads(final_manifest.read_text(encoding="utf-8"))
    expected_manifest_sha256 = str(document.get("manifest_sha256") or "")
    if expected_manifest_sha256 != _document_hash(
        {key: value for key, value in document.items() if key != "manifest_sha256"}
    ):
        raise SimpleResultError("the published automatic result manifest is invalid")
    return SimpleResult(
        root=target,
        zip_path=target / "sunofriend-automatic-midi-and-wav.zip",
        combined_midi_path=target / "MIDI" / "combined-gm-interpretation.mid",
        balanced_wav_path=(
            target / "AUDIO" / "balanced-midi-song-interpretation.wav"
        ),
        manifest_path=final_manifest,
        selected_count=len(plan.selected),
        omitted_count=len(plan.omitted),
        manifest_sha256=expected_manifest_sha256,
        instrument_plan_path=(
            target / "SOUNDS" / "automatic-starter-instruments.json"
        ),
        instrument_guide_path=(
            target / "SOUNDS" / "INSTRUMENTS-START-HERE.md"
        ),
    )


def _project_bpm(catalog: Mapping[str, Any]) -> float:
    value = catalog.get("setup", {}).get("bpm")
    try:
        bpm = float(value)
    except (TypeError, ValueError) as exc:
        raise SimpleResultError(
            "Simple mode needs a BPM in the source folder name or catalog"
        ) from exc
    if not 1.0 <= bpm <= 1000.0:
        raise SimpleResultError("Simple mode BPM must be between 1 and 1000")
    return bpm


def _project_source_horizon(
    catalog: Mapping[str, Any],
    lanes: list[Mapping[str, Any]],
) -> tuple[int, list[dict[str, Any]]]:
    """Return the complete project horizon and path-free source evidence.

    Simple mode may deliberately omit an ambiguous, silent or unsupported
    source role from its automatic MIDI selection.  That omission must not
    shorten the song clock, so horizon evidence comes from every verified
    catalog source rather than only the selected rendering lanes.
    """

    try:
        import soundfile
    except (ImportError, OSError) as exc:
        raise SimpleResultError(
            "Simple mode WAV rendering requires the audio dependencies"
        ) from exc
    preview_info = soundfile.info(str(lanes[0]["preview_path"]))
    output_rate = int(preview_info.samplerate)
    if output_rate <= 0:
        raise SimpleResultError(
            "the neutral automatic MIDI preview has an invalid sample rate"
        )

    horizons: list[dict[str, Any]] = []
    for stem in catalog.get("stems", []):
        if not isinstance(stem, Mapping):
            raise SimpleResultError("the project catalog has an invalid source stem")
        source = stem.get("source")
        if not isinstance(source, Mapping):
            raise SimpleResultError(
                "a project source stem has no verified hash evidence"
            )
        source_path = _verify_record(source, label="project source stem")
        info = soundfile.info(str(source_path))
        source_rate = int(info.samplerate)
        source_frames = int(info.frames)
        if source_rate <= 0 or source_frames < 0:
            raise SimpleResultError("a project source stem has invalid audio geometry")
        output_frames = (
            source_frames * output_rate + source_rate - 1
        ) // source_rate
        horizons.append(
            {
                "stem_id": str(stem.get("stem_id") or ""),
                "role": str(stem.get("role") or "unclassified"),
                "source_sha256": str(source["sha256"]),
                "source_bytes": int(source["bytes"]),
                "source_sample_rate": source_rate,
                "source_frames": source_frames,
                "output_sample_rate": output_rate,
                "output_frames": output_frames,
            }
        )

    if not horizons or max(row["output_frames"] for row in horizons) <= 0:
        raise SimpleResultError("the source stems have no playable song horizon")
    return max(row["output_frames"] for row in horizons), horizons


def _verify_selection_inputs(item: Mapping[str, Any]) -> None:
    _verify_record(item["source"], label="source stem")
    _verify_record(item["midi"], label="automatic primary MIDI")


def _verify_record(record: Mapping[str, Any], *, label: str) -> Path:
    path = Path(str(record.get("path") or "")).expanduser().resolve()
    expected_bytes = record.get("bytes")
    expected_sha256 = record.get("sha256")
    if (
        isinstance(expected_bytes, bool)
        or not isinstance(expected_bytes, int)
        or expected_bytes < 0
        or not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
    ):
        raise SimpleResultError(f"{label} has invalid hash evidence")
    try:
        if not path.is_file() or path.stat().st_size != expected_bytes:
            raise SimpleResultError(f"{label} changed while Simple mode was running")
    except OSError as exc:
        raise SimpleResultError(
            f"{label} changed while Simple mode was running"
        ) from exc
    if _sha256(path) != expected_sha256:
        raise SimpleResultError(f"{label} changed while Simple mode was running")
    return path


def _copy_verified(
    source: Path,
    destination: Path,
    *,
    expected: Mapping[str, Any],
    label: str,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    verified = _verify_record(expected, label=label)
    if verified != source.resolve():
        raise SimpleResultError(f"{label} path changed before publishing")
    shutil.copy2(verified, destination)
    if (
        destination.stat().st_size != expected["bytes"]
        or _sha256(destination) != expected["sha256"]
    ):
        raise SimpleResultError(f"{label} copy failed verification")


def _relative_record(path: Path, root: Path) -> dict[str, Any]:
    resolved = path.resolve()
    _require_within(resolved, root)
    return {
        "archive_path": resolved.relative_to(root.resolve()).as_posix(),
        "sha256": _sha256(resolved),
        "bytes": resolved.stat().st_size,
    }


def _require_within(path: Path, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise SimpleResultError("an automatic result path escapes its output") from exc


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_deterministic_zip(path: Path, root: Path) -> None:
    members = sorted(
        candidate
        for candidate in root.rglob("*")
        if candidate.is_file() and candidate != path
    )
    with zipfile.ZipFile(path, mode="w") as archive:
        for member in members:
            name = member.relative_to(root).as_posix()
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, member.read_bytes())


def _start_here_text(manifest: Mapping[str, Any]) -> str:
    selected = len(manifest.get("selected_midi", []))
    omitted = len(manifest.get("omitted", []))
    outputs = manifest.get("outputs", {})
    analysis_line = (
        "Automatic key/BPM evidence: "
        "TECHNICAL/automatic-musical-metadata.json (not reviewed).\n"
        if isinstance(outputs, Mapping)
        and "automatic_musical_metadata" in outputs
        else ""
    )
    return (
        "SUNOFRIEND AUTOMATIC SONG\n"
        "========================\n\n"
        "Open AUDIO/balanced-midi-song-interpretation.wav to hear the first-pass "
        "MIDI interpretation.\n"
        "For an automatic sound-aware GarageBand setup, set the project BPM "
        f"to {manifest['project']['bpm']} and import "
        "MIDI/combined-gm-interpretation.mid, or import the separate files under "
        "SOUNDS/MIDI/.\n"
        f"Project key: {manifest['project'].get('key') or 'not confirmed'}.\n"
        f"{analysis_line}"
        "Open SOUNDS/INSTRUMENTS-START-HERE.md for every named starter instrument "
        "and its short audible preview. The original automatic-primary MIDI stays "
        "unchanged under MIDI/.\n\n"
        f"Automatic primary parts included: {selected}\n"
        f"Source roles without an automatic primary: {omitted}\n\n"
        "Important: these are automatic defaults, not human-reviewed winners. "
        "The WAV is balanced and gain-protected, but it is not a release master. "
        "Use Sunofriend Studio when you want to compare candidates, give feedback "
        "or build a reviewed GarageBand pack.\n\n"
        "Your source stems were measured for timing, song length and relative "
        "level. Their audio is not mixed into the interpretation WAV.\n"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _document_hash(document: Mapping[str, Any]) -> str:
    payload = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "SIMPLE_RESULT_DIRECTORY",
    "SIMPLE_RESULT_SCHEMA",
    "SimpleResult",
    "SimpleResultError",
    "build_simple_result",
]
