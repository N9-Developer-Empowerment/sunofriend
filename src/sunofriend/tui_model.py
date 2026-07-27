"""Shared, deterministic projections for the Sunofriend terminal studio.

The TUI is an orchestration and visibility layer over the existing CLI and
Workbench.  This module deliberately contains no Textual widgets so project
discovery, workflow summaries, MIDI miniatures and command construction remain
easy to test without a terminal.
"""

from __future__ import annotations

import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .interface_contract import (
    DIRECT_TUI_COMMANDS,
    INTERFACE_CONTRACT_VERSION,
    PUBLIC_COMMANDS,
)
from .product_contract import product_contract_document
from .workbench_catalog import build_workbench_catalog, public_catalog
from .workbench_home import build_workbench_home
from .workbench_store import (
    default_workbench_state_dir,
    fold_workbench_events,
    read_workbench_events_read_only,
)
from .workbench_timeline import build_stem_timeline


TUI_PROJECT_SCHEMA = "sunofriend.tui-project.v2"
TUI_MIDI_MAP_SCHEMA = "sunofriend.tui-midi-map.v1"
_PITCH_BLOCKS = "▁▂▃▄▅▆▇█"
_DENSITY_BLOCKS = " ▁▂▃▄▅▆▇█"
_TOKEN_FRAGMENT = re.compile(r"([#?&]token=)[^&#\s]+", re.IGNORECASE)


@dataclass(frozen=True)
class TuiProjectConfig:
    """Exact local inputs used by both the TUI projection and Workbench."""

    project: Path
    candidate_roots: tuple[Path, ...] = ()
    catalog_path: Path | None = None
    state_dir: Path | None = None
    soundfont_path: Path | None = None
    developer_inspector: bool = True

    @classmethod
    def create(
        cls,
        project: str | Path,
        *,
        candidate_roots: Sequence[str | Path] = (),
        catalog_path: str | Path | None = None,
        state_dir: str | Path | None = None,
        soundfont_path: str | Path | None = None,
        developer_inspector: bool = True,
    ) -> "TuiProjectConfig":
        project_path = Path(project).expanduser().resolve()
        return cls(
            project=project_path,
            candidate_roots=tuple(
                Path(root).expanduser().resolve() for root in candidate_roots
            ),
            catalog_path=(
                Path(catalog_path).expanduser().resolve()
                if catalog_path is not None
                else None
            ),
            state_dir=(
                Path(state_dir).expanduser().resolve()
                if state_dir is not None
                else None
            ),
            soundfont_path=(
                Path(soundfont_path).expanduser().resolve()
                if soundfont_path is not None
                else None
            ),
            developer_inspector=bool(developer_inspector),
        )


@dataclass(frozen=True)
class TuiProjectSnapshot:
    """Private catalog plus its path-free user-facing TUI projection."""

    config: TuiProjectConfig
    catalog: dict[str, Any]
    public: dict[str, Any]
    home: dict[str, Any]
    document: dict[str, Any]
    decision_store_exists: bool


def parse_candidate_roots(value: str) -> tuple[str, ...]:
    """Parse the editable semicolon-separated candidate-root field."""

    return tuple(part.strip() for part in value.split(";") if part.strip())


def candidate_roots_field(roots: Sequence[str | Path]) -> str:
    """Return the reversible text shown in the editable TUI field."""

    return "; ".join(os.fspath(root) for root in roots)


def load_tui_project(config: TuiProjectConfig) -> TuiProjectSnapshot:
    """Discover one project and derive current explicit Workbench progress.

    Loading a project with no existing Workbench database remains read-only.
    The event store is opened only when the exact database already exists.
    """

    catalog = build_workbench_catalog(
        config.project,
        candidate_roots=config.candidate_roots,
        catalog_path=config.catalog_path,
    )
    state_root = config.state_dir or default_workbench_state_dir(catalog)
    database = state_root / "workbench.sqlite3"
    if database.is_file():
        current = fold_workbench_events(
            catalog,
            read_workbench_events_read_only(
                database,
                str(catalog["project_id"]),
            ),
        )
        store_exists = True
    else:
        current = fold_workbench_events(catalog, [])
        store_exists = False
    home = build_workbench_home(catalog, current)
    public = public_catalog(catalog)
    rows = _tui_stem_rows(public, home)
    document = {
        "schema": TUI_PROJECT_SCHEMA,
        "interface": {
            "contract_version": INTERFACE_CONTRACT_VERSION,
            "public_command_count": len(PUBLIC_COMMANDS),
            "direct_tui_commands": sorted(DIRECT_TUI_COMMANDS),
            "remaining_commands_available_in_cli": len(
                PUBLIC_COMMANDS - DIRECT_TUI_COMMANDS
            ),
        },
        "product_contract": product_contract_document(),
        "project": {
            "project_id": public["project_id"],
            "name": public["name"],
            "bpm": public.get("setup", {}).get("bpm"),
            "key": public.get("setup", {}).get("key"),
            "tuning_hz": public.get("setup", {}).get("tuning_hz"),
        },
        "counts": dict(home["counts"]),
        "review_scope": {
            "existing_results_only": True,
            "conversion_jobs_run": False,
            "conversion_available": True,
            "source_stem_count": home["counts"]["stem_count"],
            "midi_ready_stem_count": home["counts"]["midi_ready_stem_count"],
            "missing_midi_stem_count": home["counts"]["missing_midi_stem_count"],
        },
        "stems": rows,
        "next_step": dict(home["next_step"]),
        "decision_store": {
            "exists": store_exists,
            "created_by_project_load": False,
        },
        "privacy": {
            "local_only": True,
            "uploads_enabled": False,
            "telemetry_enabled": False,
            "paths_in_projection": False,
        },
        "effects": {
            "source_audio_mutated": False,
            "source_midi_mutated": False,
            "decision_recorded": False,
            "pack_selection_changed": False,
            "feedback_recorded": False,
        },
    }
    return TuiProjectSnapshot(
        config=config,
        catalog=catalog,
        public=public,
        home=home,
        document=document,
        decision_store_exists=store_exists,
    )


def build_tui_midi_map(
    snapshot: TuiProjectSnapshot,
    stem_id: str,
    *,
    width: int = 68,
) -> dict[str, Any]:
    """Build a compact, read-only contour and activity map for primary MIDI."""

    if not 24 <= int(width) <= 120:
        raise ValueError("MIDI map width must be between 24 and 120")
    stem = next(
        (
            row
            for row in snapshot.catalog.get("stems", [])
            if str(row.get("stem_id")) == str(stem_id)
        ),
        None,
    )
    if stem is None:
        raise ValueError("unknown TUI stem")
    primary_ids = [
        str(candidate["candidate_id"])
        for candidate in stem.get("candidates", [])
        if candidate.get("primary")
    ][:3]
    timeline = (
        build_stem_timeline(
            snapshot.catalog,
            str(stem_id),
            candidate_ids=primary_ids,
            include_source=False,
        )
        if primary_ids
        else {"candidates": []}
    )
    candidates_by_id = {
        str(candidate["candidate_id"]): candidate
        for candidate in stem.get("candidates", [])
    }
    lanes = []
    for index, lane in enumerate(timeline.get("candidates", [])):
        candidate = candidates_by_id.get(str(lane.get("candidate_id")), {})
        lanes.append(
            _midi_lane_map(
                lane,
                label=str(candidate.get("label") or f"Candidate {index + 1}"),
                process=_human_process(
                    str(candidate.get("process") or "unknown process")
                ),
                width=int(width),
            )
        )
    return {
        "schema": TUI_MIDI_MAP_SCHEMA,
        "project_id": snapshot.document["project"]["project_id"],
        "stem_id": str(stem_id),
        "role": str(stem.get("role") or "unclassified"),
        "label": str(stem.get("label") or stem.get("role") or "Stem"),
        "lane_count": len(lanes),
        "lanes": lanes,
        "alignment": (
            "Recorded zero and embedded MIDI tempo map; no additional alignment "
            "or preference is inferred."
        ),
        "effects": {
            "source_audio_mutated": False,
            "source_midi_mutated": False,
            "decision_recorded": False,
            "automatic_selection": False,
            "automatic_ranking": False,
        },
    }


def format_tui_midi_map(document: Mapping[str, Any]) -> str:
    """Render a compact terminal-friendly comparison without ANSI escapes."""

    lines = [
        f"{document.get('label', 'Stem')} · {document.get('role', 'unclassified')}",
        "Primary MIDI alternatives · contour above, note activity below",
        "",
    ]
    lanes = document.get("lanes", [])
    if not lanes:
        lines.append("No primary MIDI candidates are available for this stem.")
    for index, lane in enumerate(lanes):
        marker = chr(65 + index)
        status = str(lane.get("status") or "unavailable")
        if status != "available":
            lines.append(
                f"{marker}  {lane.get('label')} · {status}: "
                f"{lane.get('reason_code') or 'no note evidence'}"
            )
            continue
        pitch_range = lane.get("pitch_range")
        pitch_text = (
            f"{_midi_note_name(pitch_range[0])}–{_midi_note_name(pitch_range[1])}"
            if isinstance(pitch_range, list) and len(pitch_range) == 2
            else "no pitch"
        )
        lines.extend(
            [
                (
                    f"{marker}  {lane.get('label')} · {lane.get('process')} · "
                    f"{lane.get('note_count')} notes · {pitch_text}"
                ),
                f"   pitch    {lane.get('pitch_graph')}",
                f"   activity {lane.get('density_graph')}",
            ]
        )
    lines.extend(["", str(document.get("alignment") or "")])
    return "\n".join(lines)


def workbench_command(config: TuiProjectConfig) -> tuple[str, ...]:
    """Construct the exact existing CLI command used by the visual studio."""

    command = [
        sys.executable,
        "-m",
        "sunofriend",
        "workbench",
        str(config.project),
    ]
    for root in config.candidate_roots:
        command.extend(("--candidate-root", str(root)))
    if config.catalog_path is not None:
        command.extend(("--catalog", str(config.catalog_path)))
    if config.state_dir is not None:
        command.extend(("--state-dir", str(config.state_dir)))
    if config.soundfont_path is not None:
        command.extend(("--soundfont", str(config.soundfont_path)))
    if config.developer_inspector:
        command.append("--developer-inspector")
    command.append("--open")
    return tuple(command)


def safe_activity_line(value: str) -> str:
    """Hide the per-launch browser token and private decision-store path."""

    line = _TOKEN_FRAGMENT.sub(r"\1<hidden>", str(value).strip())
    if line.startswith("Decisions:"):
        return "Decision store: local and private"
    return line


def _tui_stem_rows(
    public: Mapping[str, Any], home: Mapping[str, Any]
) -> list[dict[str, Any]]:
    home_rows = {
        str(row.get("stem_id")): row for row in home.get("stems", [])
    }
    result = []
    for stem in public.get("stems", []):
        stem_id = str(stem.get("stem_id"))
        progress = home_rows.get(stem_id, {})
        result.append(
            {
                "stem_id": stem_id,
                "label": stem.get("label") or stem.get("role") or "Stem",
                "role": stem.get("role") or "unclassified",
                "candidate_count": int(stem.get("candidate_count") or 0),
                "primary_candidate_count": int(
                    stem.get("primary_candidate_count") or 0
                ),
                "decision_recorded": bool(progress.get("decision_recorded")),
                "selected_part_count": int(progress.get("selected_part_count") or 0),
                "attention_code": str(
                    progress.get("attention_code") or "no-candidates"
                ),
            }
        )
    return result


def _midi_lane_map(
    lane: Mapping[str, Any], *, label: str, process: str, width: int
) -> dict[str, Any]:
    status = str(lane.get("status") or "unavailable")
    base = {
        "candidate_id": str(lane.get("candidate_id") or ""),
        "label": label,
        "process": process,
        "status": status,
        "reason_code": lane.get("reason_code"),
        "note_count": lane.get("note_count"),
        "pitch_range": lane.get("pitch_range"),
        "duration_seconds": lane.get("duration_seconds"),
    }
    if status not in {"available", "empty"}:
        return base
    notes = [
        note
        for track in lane.get("tracks", [])
        for note in track.get("notes", [])
        if isinstance(note, Mapping)
    ]
    if not notes:
        return {
            **base,
            "status": "empty",
            "pitch_graph": "·" * width,
            "density_graph": " " * width,
        }
    duration = max(
        float(lane.get("duration_seconds") or 0.0),
        max(float(note["end_seconds"]) for note in notes),
        1e-9,
    )
    pitch_bins: list[list[int]] = [[] for _ in range(width)]
    density = [0 for _ in range(width)]
    for note in notes:
        start = max(0.0, float(note["start_seconds"]))
        end = max(start, float(note["end_seconds"]))
        first = min(width - 1, int(math.floor(start / duration * width)))
        last = min(
            width - 1,
            max(first, int(math.ceil(end / duration * width) - 1)),
        )
        pitch = int(note["pitch"])
        for position in range(first, last + 1):
            pitch_bins[position].append(pitch)
            density[position] += 1
    pitches = [pitch for values in pitch_bins for pitch in values]
    low = min(pitches)
    high = max(pitches)
    pitch_graph = "".join(
        (
            "·"
            if not values
            else _PITCH_BLOCKS[
                _scaled_index(
                    sum(values) / len(values),
                    low,
                    high,
                    len(_PITCH_BLOCKS),
                )
            ]
        )
        for values in pitch_bins
    )
    maximum_density = max(density)
    density_graph = "".join(
        _DENSITY_BLOCKS[
            _scaled_index(value, 0, maximum_density, len(_DENSITY_BLOCKS))
        ]
        for value in density
    )
    return {
        **base,
        "status": "available",
        "pitch_graph": pitch_graph,
        "density_graph": density_graph,
    }


def _scaled_index(value: float, low: float, high: float, count: int) -> int:
    if count <= 1 or high <= low:
        return count - 1
    return min(
        count - 1,
        max(0, int(round((float(value) - low) / (high - low) * (count - 1)))),
    )


def _midi_note_name(pitch: Any) -> str:
    value = int(pitch)
    names = ("C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B")
    return f"{names[value % 12]}{value // 12 - 1}"


def _human_process(value: str) -> str:
    words = value.replace("_", " ").replace("-", " ").split()
    if not words:
        return "Unknown process"
    return " ".join([words[0].capitalize(), *words[1:]])


__all__ = [
    "TUI_MIDI_MAP_SCHEMA",
    "TUI_PROJECT_SCHEMA",
    "TuiProjectConfig",
    "TuiProjectSnapshot",
    "build_tui_midi_map",
    "candidate_roots_field",
    "format_tui_midi_map",
    "load_tui_project",
    "parse_candidate_roots",
    "safe_activity_line",
    "workbench_command",
]
