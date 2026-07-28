"""Copyright-safe newcomer demo built through the production Simple workflow."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import sys
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .simple_create import create_simple_create_runner
from .simple_create_contract import (
    SimpleCreateProgress,
    SimpleCreateRequest,
    SimpleCreateResult,
    SimpleCreateRunner,
    simple_create_result_document,
)


DEMO_SCHEMA = "sunofriend.demo-result.v1"
DEMO_PROJECT_SCHEMA = "sunofriend.demo-project.v1"
DEMO_GENERATOR_POLICY = "fixed-synthetic-four-bar-arrangement-v1"
DEMO_SAMPLE_RATE = 44_100
DEMO_BPM = 120.0
DEMO_KEY = "C major"
DEMO_TUNING_HZ = 440.0
DEMO_DURATION_SECONDS = 8.0
_DEMO_TOTAL = 7
_STEM_ROLES = ("kick", "snare", "hat", "bass", "keys", "lead")


class DemoError(RuntimeError):
    """A newcomer demo could not be created safely."""


@dataclass(frozen=True)
class DemoProgress:
    """Bounded progress suitable for the CLI and future guided surfaces."""

    completed: int
    total: int
    phase: str
    message: str


DemoProgressCallback = Callable[[DemoProgress], None]


@dataclass(frozen=True)
class DemoProject:
    """One fixed synthetic source project retained beside its result."""

    root: Path
    stems: tuple[Path, ...]
    manifest_path: Path
    readme_path: Path


@dataclass(frozen=True)
class DemoResult:
    """Public paths and honest status for one demo run."""

    status: str
    output_dir: Path
    source_project: DemoProject
    simple_result: SimpleCreateResult

    @property
    def succeeded(self) -> bool:
        return self.simple_result.succeeded

    def as_dict(self) -> dict[str, Any]:
        document = simple_create_result_document(
            self.simple_result,
            project=self.source_project.root,
        )
        return {
            **document,
            "schema": DEMO_SCHEMA,
            "status": self.status,
            "demo_source": {
                "kind": "fixed synthetic audio; no recordings or samples",
                "generator_policy": DEMO_GENERATOR_POLICY,
                "project": str(self.source_project.root),
                "manifest": str(self.source_project.manifest_path),
                "stem_count": len(self.source_project.stems),
            },
        }


async def create_demo(
    output_dir: str | Path,
    *,
    state_dir: str | Path | None = None,
    soundfont_path: str | Path | None = None,
    simple_runner: SimpleCreateRunner | None = None,
    on_progress: DemoProgressCallback | None = None,
) -> DemoResult:
    """Create fixed local stems and run the normal automatic MIDI/WAV workflow."""

    destination = _fresh_output_path(output_dir)
    project_root = demo_project_path(destination)
    _validate_fresh_paths(destination, project_root)
    callback = on_progress or (lambda _progress: None)
    _emit(
        callback,
        0,
        "generate-demo",
        "Creating a four-bar synthetic song with drums, bass, keys and lead",
    )
    project = create_demo_project(destination)
    _emit(
        callback,
        1,
        "generate-demo",
        "Six copyright-safe WAV stems are ready; starting normal Simple mode",
    )
    runner = simple_runner or create_simple_create_runner()

    def simple_progress(progress: SimpleCreateProgress) -> None:
        _emit(
            callback,
            min(_DEMO_TOTAL, int(progress.completed) + 1),
            progress.phase,
            progress.message,
        )

    try:
        result = await runner.run(
            SimpleCreateRequest.create(
                project.root,
                destination,
                state_dir=state_dir,
                soundfont_path=soundfont_path,
            ),
            on_progress=simple_progress,
        )
    except Exception as exc:
        raise DemoError(
            "The synthetic demo stems were created, but the normal automatic "
            f"conversion did not complete. The stems remain at {project.root}: {exc}"
        ) from exc
    if result.succeeded:
        _verify_simple_result(destination, result)
    return DemoResult(
        status=result.status,
        output_dir=destination,
        source_project=project,
        simple_result=result,
    )


def demo_project_path(output_dir: str | Path) -> Path:
    """Return the fresh sibling source-project path for one demo output."""

    output = Path(output_dir).expanduser().resolve()
    return output.with_name(
        f"{output.name}-DEMO-STEMS-{DEMO_KEY}-{int(DEMO_BPM)}bpm-"
        f"{int(DEMO_TUNING_HZ)}hz"
    )


def create_demo_project(output_dir: str | Path) -> DemoProject:
    """Publish the deterministic synthetic stem project without making output."""

    destination = _fresh_output_path(output_dir)
    project_root = demo_project_path(destination)
    _validate_fresh_paths(destination, project_root)
    try:
        project_root.mkdir(mode=0o700, exist_ok=False)
        project_root.chmod(0o700)
    except FileExistsError as exc:
        raise DemoError(
            "The demo source folder already exists; choose a fresh output path"
        ) from exc
    except OSError as exc:
        raise DemoError("The demo source folder could not be created") from exc

    try:
        stems: list[Path] = []
        for role in _STEM_ROLES:
            stem = project_root / (
                f"Sunofriend-Demo-{role}-{DEMO_KEY}-{int(DEMO_BPM)}bpm-"
                f"{int(DEMO_TUNING_HZ)}hz.wav"
            )
            _write_demo_wav(stem, role)
            stems.append(stem)
        manifest = _demo_project_document(stems)
        manifest_path = project_root / "sunofriend-demo-project.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        readme_path = project_root / "START-HERE.txt"
        readme_path.write_text(_demo_readme(), encoding="utf-8")
    except Exception:
        shutil.rmtree(project_root, ignore_errors=True)
        raise

    return DemoProject(
        root=project_root,
        stems=tuple(stems),
        manifest_path=manifest_path,
        readme_path=readme_path,
    )


def _validate_fresh_paths(output: Path, project: Path) -> None:
    if not output.parent.is_dir():
        raise DemoError("The demo output parent folder does not exist")
    if os.path.lexists(output):
        raise DemoError(
            "The demo output already exists; choose a fresh path so nothing "
            "can be overwritten"
        )
    if os.path.lexists(project):
        raise DemoError(
            "The matching demo source folder already exists; choose a fresh "
            "output path so nothing can be overwritten"
        )


def _fresh_output_path(output_dir: str | Path) -> Path:
    entered = Path(output_dir).expanduser()
    if os.path.lexists(entered):
        raise DemoError(
            "The demo output already exists; choose a fresh path so nothing "
            "can be overwritten"
        )
    return entered.resolve()


def _write_demo_wav(path: Path, role: str) -> None:
    frames = int(round(DEMO_DURATION_SECONDS * DEMO_SAMPLE_RATE))
    samples = array(
        "h",
        (
            _to_pcm16(_stem_sample(role, index, index / DEMO_SAMPLE_RATE))
            for index in range(frames)
        ),
    )
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(DEMO_SAMPLE_RATE)
        handle.writeframes(samples.tobytes())


def _stem_sample(role: str, index: int, time_seconds: float) -> float:
    if role == "kick":
        local = time_seconds % 1.0
        if local >= 0.24:
            return 0.0
        phase = 2.0 * math.pi * (
            88.0 * local - 21.0 * local * local
        )
        return 0.80 * math.sin(phase) * math.exp(-17.0 * local)

    if role == "snare":
        local = (time_seconds - 0.5) % 1.0
        if local >= 0.16:
            return 0.0
        envelope = math.exp(-24.0 * local)
        noise = _deterministic_noise(index)
        tone = math.sin(2.0 * math.pi * 185.0 * local)
        return envelope * (0.48 * noise + 0.20 * tone)

    if role == "hat":
        local = time_seconds % 0.25
        if local >= 0.045:
            return 0.0
        high_noise = (
            _deterministic_noise(index)
            - _deterministic_noise(max(0, index - 1))
        ) * 0.5
        accent = 1.0 if int(time_seconds / 0.25) % 2 == 0 else 0.70
        return 0.25 * accent * high_noise * math.exp(-70.0 * local)

    if role == "bass":
        roots = (65.406, 48.999, 55.000, 43.654)
        local = time_seconds % 1.0
        frequency = roots[int(time_seconds) % len(roots)]
        envelope = _note_envelope(local, 0.98, attack=0.015, release=0.10)
        phase = 2.0 * math.pi * frequency * local
        return envelope * (
            0.38 * math.sin(phase)
            + 0.13 * math.sin(2.0 * phase)
            + 0.04 * math.sin(3.0 * phase)
        )

    if role == "keys":
        chords = (
            (261.626, 329.628, 391.995),
            (195.998, 246.942, 293.665),
            (220.000, 261.626, 329.628),
            (174.614, 220.000, 261.626),
        )
        chord = chords[int(time_seconds / 2.0) % len(chords)]
        local = time_seconds % 1.0
        envelope = _note_envelope(local, 0.82, attack=0.006, release=0.28)
        total = 0.0
        for frequency in chord:
            phase = 2.0 * math.pi * frequency * local
            total += (
                0.11 * math.sin(phase)
                + 0.045 * math.sin(2.0 * phase)
                + 0.018 * math.sin(3.0 * phase)
            )
        return envelope * total

    if role == "lead":
        melody = (
            523.251,
            659.255,
            783.991,
            659.255,
            587.330,
            493.883,
            391.995,
            587.330,
            659.255,
            880.000,
            1046.502,
            880.000,
            523.251,
            440.000,
            349.228,
            440.000,
        )
        local = time_seconds % 0.5
        frequency = melody[int(time_seconds / 0.5) % len(melody)]
        envelope = _note_envelope(local, 0.46, attack=0.02, release=0.07)
        phase = 2.0 * math.pi * frequency * local
        return envelope * (
            0.26 * math.sin(phase) + 0.055 * math.sin(2.0 * phase)
        )

    raise DemoError(f"unknown synthetic demo role: {role}")


def _note_envelope(
    local: float,
    duration: float,
    *,
    attack: float,
    release: float,
) -> float:
    if local < 0.0 or local >= duration:
        return 0.0
    attack_gain = min(1.0, local / max(attack, 1e-9))
    release_gain = min(1.0, (duration - local) / max(release, 1e-9))
    return max(0.0, min(attack_gain, release_gain))


def _deterministic_noise(index: int) -> float:
    value = (int(index) * 1_103_515_245 + 12_345) & 0x7FFFFFFF
    return (value / 1_073_741_823.5) - 1.0


def _to_pcm16(sample: float) -> int:
    bounded = max(-0.98, min(0.98, float(sample)))
    return int(round(bounded * 32_767.0))


def _demo_project_document(stems: list[Path]) -> dict[str, Any]:
    return {
        "schema": DEMO_PROJECT_SCHEMA,
        "generator_policy": DEMO_GENERATOR_POLICY,
        "source_kind": "fixed synthetic audio; no recordings or samples",
        "copyright_safety": {
            "third_party_recordings": False,
            "third_party_samples": False,
            "lyrics": False,
            "generated_from_fixed_mathematical_waveforms": True,
        },
        "project": {
            "bpm": DEMO_BPM,
            "key": DEMO_KEY,
            "tuning_hz": DEMO_TUNING_HZ,
            "duration_seconds": DEMO_DURATION_SECONDS,
            "sample_rate": DEMO_SAMPLE_RATE,
            "bars": 4,
            "beats_per_bar": 4,
        },
        "stems": [
            {
                "role": role,
                "file": stem.name,
                "bytes": stem.stat().st_size,
                "sha256": _sha256(stem),
            }
            for role, stem in zip(_STEM_ROLES, stems)
        ],
    }


def _demo_readme() -> str:
    return (
        "SUNOFRIEND SYNTHETIC DEMO STEMS\n"
        "================================\n\n"
        "These six WAV files were generated from fixed mathematical waveforms "
        "and deterministic noise. They contain no recordings, samples, lyrics "
        "or copied song.\n\n"
        "The project is four bars in C major at 120 BPM and A=440 Hz. It has "
        "kick, snare, hi-hat, bass, keys and lead stems. Sunofriend sends this "
        "folder through the same automatic Simple workflow used for a real "
        "authorised stem project.\n\n"
        "The result is deliberately labelled automatic and not reviewed. The "
        "MIDI-derived WAV is a creative interpretation, not a reconstruction "
        "of the source waveforms and not a release master.\n"
    )


def _verify_simple_result(
    destination: Path,
    result: SimpleCreateResult,
) -> None:
    if result.output_dir.resolve() != destination:
        raise DemoError("The Simple runner returned a different output root")
    required: Mapping[str, Path | None] = {
        "automatic result": result.result_root,
        "listening WAV": result.balanced_wav_path,
        "combined MIDI": result.combined_midi_path,
        "starter ZIP": result.zip_path,
        "result receipt": result.manifest_path,
    }
    for label, path in required.items():
        if path is None:
            raise DemoError(f"The completed demo has no verified {label}")
        resolved = path.resolve()
        try:
            resolved.relative_to(destination)
        except ValueError as exc:
            raise DemoError(f"The completed demo {label} escapes its output") from exc
        if label == "automatic result":
            if not resolved.is_dir():
                raise DemoError("The completed demo result directory is missing")
        elif not resolved.is_file() or resolved.stat().st_size <= 0:
            raise DemoError(f"The completed demo has no verified {label}")


def _emit(
    callback: DemoProgressCallback,
    completed: int,
    phase: str,
    message: str,
) -> None:
    try:
        callback(
            DemoProgress(
                completed=max(0, min(_DEMO_TOTAL, int(completed))),
                total=_DEMO_TOTAL,
                phase=str(phase),
                message=str(message)[:500],
            )
        )
    except Exception:
        return


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "DEMO_BPM",
    "DEMO_DURATION_SECONDS",
    "DEMO_GENERATOR_POLICY",
    "DEMO_KEY",
    "DEMO_PROJECT_SCHEMA",
    "DEMO_SAMPLE_RATE",
    "DEMO_SCHEMA",
    "DEMO_TUNING_HZ",
    "DemoError",
    "DemoProgress",
    "DemoProject",
    "DemoResult",
    "create_demo",
    "create_demo_project",
    "demo_project_path",
]
