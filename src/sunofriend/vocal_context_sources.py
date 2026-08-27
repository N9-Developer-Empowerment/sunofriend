"""Explicit local context-audio admission for Vocal Session playback.

This module owns the distinction between a complete original mix and an
instrumental backing.  Callers provide exact files; nothing is discovered,
copied, rendered, selected or added to the Musical State.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
from typing import Any, Mapping

import soundfile


_MAXIMUM_AUDIO_BYTES = 2 * 1024 * 1024 * 1024
_MAXIMUM_DURATION_SECONDS = 20 * 60
_ROLES = {
    "original_mix": "authorised_original_mix",
    "instrumental_backing": "authorised_instrumental_backing",
}


@dataclass(frozen=True)
class VocalContextSource:
    """One exact local context source with a path-free public identity."""

    role: str
    source_id: str
    source_class: str
    private_path: Path
    audio_bytes: int
    audio_sha256: str
    sample_rate: int
    frames: int
    channels: int
    duration_seconds: float

    def media_record(self) -> dict[str, Any]:
        """Return the server-private media record."""

        return {
            "source_id": self.source_id,
            "audio_bytes": self.audio_bytes,
            "audio_sha256": self.audio_sha256,
            "private_path": str(self.private_path),
        }

    def browser_source(self, media_url: str) -> dict[str, Any]:
        """Return the path-free, zero-authority browser projection."""

        if not media_url.startswith("/media/"):
            raise ValueError("vocal context media URL changed")
        return {
            "source_id": self.source_id,
            "source_class": self.source_class,
            "display_label": (
                "Original full mix"
                if self.role == "original_mix"
                else "Instrumental backing"
            ),
            "audio_sha256": self.audio_sha256,
            "audio_bytes": self.audio_bytes,
            "audio_properties": {
                "sample_rate": self.sample_rate,
                "frames": self.frames,
                "channels": self.channels,
                "duration_seconds": self.duration_seconds,
            },
            "media_url": media_url,
            "authority": "audition_only",
        }


@dataclass(frozen=True)
class VocalContextSources:
    """The optional exact full-mix and backing sources for one server."""

    original_mix: VocalContextSource | None
    instrumental_backing: VocalContextSource | None

    def media_records(self) -> dict[str, dict[str, Any]]:
        return {
            source.source_id: source.media_record()
            for source in self._present_sources()
        }

    def browser_sources(
        self, capability_by_source: Mapping[str, str]
    ) -> list[dict[str, Any]]:
        return [
            source.browser_source(f"/media/{capability_by_source[source.source_id]}")
            for source in self._present_sources()
        ]

    def _present_sources(self) -> tuple[VocalContextSource, ...]:
        return tuple(
            source
            for source in (self.original_mix, self.instrumental_backing)
            if source is not None
        )


def admit_vocal_context_sources(
    *,
    original_mix_audio: str | Path | None,
    backing_audio: str | Path | None,
) -> VocalContextSources:
    """Admit only the exact optional files named by the caller."""

    original = _admit("original_mix", original_mix_audio)
    backing = _admit("instrumental_backing", backing_audio)
    if (
        original is not None
        and backing is not None
        and original.audio_sha256 == backing.audio_sha256
    ):
        raise ValueError("original mix and instrumental backing must be distinct audio")
    return VocalContextSources(
        original_mix=original,
        instrumental_backing=backing,
    )


def _admit(role: str, value: str | Path | None) -> VocalContextSource | None:
    if value is None:
        return None
    supplied = Path(value).expanduser().absolute()
    if supplied.is_symlink():
        raise ValueError(f"vocal context {role} must be one ordinary file")
    path = supplied.resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"vocal context {role} must be one ordinary file")
    size = path.stat().st_size
    if size <= 0 or size > _MAXIMUM_AUDIO_BYTES:
        raise ValueError(f"vocal context {role} size is outside the safe bound")
    try:
        info = soundfile.info(str(path))
    except (RuntimeError, TypeError, ValueError) as exc:
        raise ValueError(f"vocal context {role} must be readable audio") from exc
    duration = float(info.duration)
    if (
        info.samplerate <= 0
        or info.frames <= 0
        or info.channels not in {1, 2}
        or not math.isfinite(duration)
        or duration <= 0.0
        or duration > _MAXIMUM_DURATION_SECONDS
    ):
        raise ValueError(f"vocal context {role} audio geometry is outside the safe bound")
    digest = _file_sha256(path)
    return VocalContextSource(
        role=role,
        source_id=f"vocal-context-{role}-{digest[:16]}",
        source_class=_ROLES[role],
        private_path=path,
        audio_bytes=size,
        audio_sha256=digest,
        sample_rate=int(info.samplerate),
        frames=int(info.frames),
        channels=int(info.channels),
        duration_seconds=duration,
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "VocalContextSource",
    "VocalContextSources",
    "admit_vocal_context_sources",
]
