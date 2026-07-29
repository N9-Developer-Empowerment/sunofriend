"""Resolve the audio sources that production is allowed to consume.

Legacy projects intentionally retain their lower-case, top-level ``.wav``
discovery.  Prepared projects instead use their immutable source manifest and
optional source-graph frontier as the authority.  That distinction prevents
inactive parents, undeclared files, or nested refined children from being
silently confused with one another.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .audio_formats import KNOWN_AUDIO_SUFFIXES
from .source_lineage import load_source_graph, resolve_active_sources
from .source_project import SOURCE_PROJECT_RELATIVE_PATH


@dataclass(frozen=True)
class ProjectAudioSource:
    """One resolved source eligible for conversion or review."""

    path: Path
    role: str | None
    node_id: str | None
    asset_id: str | None
    shape: str
    origin: str


@dataclass(frozen=True)
class ProjectAudioInventory:
    """Read-only source-audio inventory for legacy or prepared projects."""

    project: Path
    audio_files: tuple[Path, ...]
    canonical_wavs: tuple[Path, ...]
    unprepared_audio: tuple[Path, ...]
    sources: tuple[ProjectAudioSource, ...] = ()
    prepared_project: bool = False
    source_graph_id: str | None = None
    source_graph_revision: int | None = None


def inspect_project_audio_inputs(
    project: str | Path,
) -> ProjectAudioInventory:
    """Resolve prepared graph sources or classify legacy top-level audio."""

    root = Path(project).expanduser().resolve()
    if not root.is_dir():
        return ProjectAudioInventory(root, (), (), ())
    manifest = root.joinpath(*SOURCE_PROJECT_RELATIVE_PATH.parts)
    if manifest.exists() or manifest.is_symlink():
        graph = load_source_graph(root)
        pointer = root / "SOURCE-GRAPH" / "current.json"
        active = resolve_active_sources(
            graph,
            project_root=root if pointer.exists() or pointer.is_symlink() else None,
        )
        sources: list[ProjectAudioSource] = []
        for node in active:
            path = _prepared_canonical_path(
                root,
                PurePosixPath(node.asset.canonical_path),
            )
            if path.suffix != ".wav":
                raise ValueError(
                    "prepared source-graph canonical assets must use the "
                    "lower-case .wav suffix"
                )
            sources.append(
                ProjectAudioSource(
                    path=path.resolve(),
                    role=node.role,
                    node_id=node.node_id,
                    asset_id=node.asset.asset_id,
                    shape=node.shape,
                    origin=node.origin,
                )
            )
        canonical = tuple(source.path for source in sources)
        return ProjectAudioInventory(
            project=root,
            audio_files=canonical,
            canonical_wavs=canonical,
            unprepared_audio=(),
            sources=tuple(sources),
            prepared_project=True,
            source_graph_id=graph.graph_id,
            source_graph_revision=graph.revision,
        )

    audio = tuple(
        sorted(
            (
                path
                for path in root.iterdir()
                if path.suffix.casefold() in KNOWN_AUDIO_SUFFIXES
                and (path.is_file() or path.is_symlink())
            ),
            key=lambda path: (path.name.casefold(), path.name),
        )
    )
    canonical = tuple(
        path
        for path in audio
        if path.suffix == ".wav" and not path.is_symlink()
    )
    canonical_set = set(canonical)
    sources = tuple(
        ProjectAudioSource(
            path=path,
            role=None,
            node_id=None,
            asset_id=None,
            shape="unknown",
            origin="legacy",
        )
        for path in canonical
    )
    return ProjectAudioInventory(
        project=root,
        audio_files=audio,
        canonical_wavs=canonical,
        unprepared_audio=tuple(
            path for path in audio if path not in canonical_set
        ),
        sources=sources,
    )


def _prepared_canonical_path(
    root: Path,
    relative: PurePosixPath,
) -> Path:
    """Resolve one manifest-declared canonical source without following links."""

    path = root
    for part in relative.parts:
        path /= part
        if path.is_symlink():
            raise ValueError(
                "prepared source canonical path must not contain symbolic links"
            )
    if not path.is_file():
        raise ValueError("prepared source canonical asset does not exist")
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(
            "prepared source canonical path escapes the project"
        ) from exc
    return resolved


def prepared_project_input_problem(project: str | Path) -> str | None:
    """Explain why a folder is not yet safe for WAV-only conversion."""

    inventory = inspect_project_audio_inputs(project)
    if inventory.unprepared_audio:
        if len(inventory.audio_files) == 1:
            return (
                "This folder contains one source audio file, not a prepared "
                "top-level .wav stem project. First run `sunofriend "
                "source-import SOURCE --out-dir FRESH --plan`. That command "
                "prepares one file; it does not separate a finished mix into "
                "stems."
            )
        return (
            f"This folder contains {len(inventory.audio_files)} supported audio "
            f"parts, but {len(inventory.unprepared_audio)} are not prepared "
            "lower-case top-level .wav stems. Sunofriend will not silently "
            "ignore them. First run `sunofriend source-import-folder "
            "SOURCE_FOLDER --out-dir FRESH --plan`, then execute that reviewed "
            "plan and load the fresh prepared folder."
        )
    if not inventory.canonical_wavs:
        return "The stem project folder contains no top-level WAV stems."
    return None


__all__ = [
    "ProjectAudioInventory",
    "ProjectAudioSource",
    "inspect_project_audio_inputs",
    "prepared_project_input_problem",
]
