"""Read the public plist metadata stored inside a GarageBand ``.band`` bundle.

This deliberately does not parse or modify GarageBand's private ProjectData
format.  The result is useful as provenance for a Clip v1 golden reference and
captures which sampler families were present in a successful arrangement.
"""
from __future__ import annotations

import plistlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GarageBandProjectInfo:
    path: str
    garageband_version: str | None
    bpm: float | None
    key: str | None
    mode: str | None
    time_signature: str | None
    sample_rate: int | None
    track_count: int | None
    audio_files: tuple[str, ...]
    instrument_assets: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def inspect_project(path: str | Path) -> GarageBandProjectInfo:
    bundle = Path(path).expanduser()
    if not bundle.is_dir() or bundle.suffix.casefold() != ".band":
        raise ValueError(f"GarageBand .band bundle not found: {bundle}")

    info = _read_plist(bundle / "Resources" / "ProjectInformation.plist")
    metadata = _read_plist(bundle / "Alternatives" / "000" / "MetaData.plist")
    numerator = metadata.get("SongSignatureNumerator")
    denominator = metadata.get("SongSignatureDenominator")
    signature = f"{numerator}/{denominator}" if numerator and denominator else None

    audio_files = tuple(sorted(str(item) for item in metadata.get("AudioFiles", [])))
    assets = tuple(
        sorted({_instrument_asset_name(str(item)) for item in metadata.get("SamplerInstrumentsFiles", [])})
    )
    return GarageBandProjectInfo(
        path=str(bundle.resolve()),
        garageband_version=info.get("LastSavedFrom"),
        bpm=_optional_float(metadata.get("BeatsPerMinute")),
        key=metadata.get("SongKey"),
        mode=metadata.get("SongGenderKey"),
        time_signature=signature,
        sample_rate=_optional_int(metadata.get("SampleRate")),
        track_count=_optional_int(metadata.get("NumberOfTracks")),
        audio_files=audio_files,
        instrument_assets=assets,
    )


def _read_plist(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"GarageBand metadata is missing: {path}")
    with path.open("rb") as handle:
        value = plistlib.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"GarageBand metadata is not a dictionary: {path}")
    return value


def _instrument_asset_name(value: str) -> str:
    parts = Path(value).parts
    for preferred in ("Modern 909", "Upright Jazz Bass"):
        if preferred in parts or preferred in value:
            return preferred
    return Path(value).stem.replace("_consolidated", "")


def _optional_float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _optional_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int) else None


__all__ = ["GarageBandProjectInfo", "inspect_project"]
