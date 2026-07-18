"""Installed-instrument discovery and stable General MIDI catalogues.

GarageBand's built-in patches are not published as a supported automation API.
Sunofriend therefore inventories only evidence that macOS exposes safely:

* factory sampler assets already installed on disk;
* drum-kit samples installed with the GarageBand/Logic sound library; and
* Audio Unit instruments reported by Apple's ``auval`` tool.

The matching engine in :mod:`sunofriend.instrument_match` consumes this
catalogue without modifying Apple content or private GarageBand project files.
"""

from __future__ import annotations

import plistlib
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


GARAGEBAND_SAMPLER_ROOT = Path(
    "/Library/Application Support/GarageBand/Instrument Library/Sampler/Sampler Files"
)
GARAGEBAND_SAMPLER_INSTRUMENT_ROOT = Path(
    "/Library/Application Support/GarageBand/Instrument Library/"
    "Sampler/Sampler Instruments"
)
LOGIC_DRUM_ROOT = Path("/Library/Application Support/Logic/Ultrabeat Samples")
LOGIC_SAMPLER_INSTRUMENT_ROOT = Path(
    "/Library/Application Support/Logic/Sampler Instruments"
)
GARAGEBAND_APP = Path("/Applications/GarageBand.app")
AUDIO_SUFFIXES = frozenset({".wav", ".aif", ".aiff", ".caf"})


# MIDI program numbers are zero based, matching the bytes written to a MIDI
# file. Display output also includes the conventional one-based patch number.
GM_PROGRAM_NAMES: tuple[str, ...] = (
    "Acoustic Grand Piano",
    "Bright Acoustic Piano",
    "Electric Grand Piano",
    "Honky-tonk Piano",
    "Electric Piano 1",
    "Electric Piano 2",
    "Harpsichord",
    "Clavinet",
    "Celesta",
    "Glockenspiel",
    "Music Box",
    "Vibraphone",
    "Marimba",
    "Xylophone",
    "Tubular Bells",
    "Dulcimer",
    "Drawbar Organ",
    "Percussive Organ",
    "Rock Organ",
    "Church Organ",
    "Reed Organ",
    "Accordion",
    "Harmonica",
    "Tango Accordion",
    "Acoustic Guitar (nylon)",
    "Acoustic Guitar (steel)",
    "Electric Guitar (jazz)",
    "Electric Guitar (clean)",
    "Electric Guitar (muted)",
    "Overdriven Guitar",
    "Distortion Guitar",
    "Guitar Harmonics",
    "Acoustic Bass",
    "Electric Bass (finger)",
    "Electric Bass (pick)",
    "Fretless Bass",
    "Slap Bass 1",
    "Slap Bass 2",
    "Synth Bass 1",
    "Synth Bass 2",
    "Violin",
    "Viola",
    "Cello",
    "Contrabass",
    "Tremolo Strings",
    "Pizzicato Strings",
    "Orchestral Harp",
    "Timpani",
    "String Ensemble 1",
    "String Ensemble 2",
    "Synth Strings 1",
    "Synth Strings 2",
    "Choir Aahs",
    "Voice Oohs",
    "Synth Voice",
    "Orchestra Hit",
    "Trumpet",
    "Trombone",
    "Tuba",
    "Muted Trumpet",
    "French Horn",
    "Brass Section",
    "Synth Brass 1",
    "Synth Brass 2",
    "Soprano Sax",
    "Alto Sax",
    "Tenor Sax",
    "Baritone Sax",
    "Oboe",
    "English Horn",
    "Bassoon",
    "Clarinet",
    "Piccolo",
    "Flute",
    "Recorder",
    "Pan Flute",
    "Blown Bottle",
    "Shakuhachi",
    "Whistle",
    "Ocarina",
    "Lead 1 (square)",
    "Lead 2 (sawtooth)",
    "Lead 3 (calliope)",
    "Lead 4 (chiff)",
    "Lead 5 (charang)",
    "Lead 6 (voice)",
    "Lead 7 (fifths)",
    "Lead 8 (bass + lead)",
    "Pad 1 (new age)",
    "Pad 2 (warm)",
    "Pad 3 (polysynth)",
    "Pad 4 (choir)",
    "Pad 5 (bowed)",
    "Pad 6 (metallic)",
    "Pad 7 (halo)",
    "Pad 8 (sweep)",
    "FX 1 (rain)",
    "FX 2 (soundtrack)",
    "FX 3 (crystal)",
    "FX 4 (atmosphere)",
    "FX 5 (brightness)",
    "FX 6 (goblins)",
    "FX 7 (echoes)",
    "FX 8 (sci-fi)",
    "Sitar",
    "Banjo",
    "Shamisen",
    "Koto",
    "Kalimba",
    "Bag Pipe",
    "Fiddle",
    "Shanai",
    "Tinkle Bell",
    "Agogo",
    "Steel Drums",
    "Woodblock",
    "Taiko Drum",
    "Melodic Tom",
    "Synth Drum",
    "Reverse Cymbal",
    "Guitar Fret Noise",
    "Breath Noise",
    "Seashore",
    "Bird Tweet",
    "Telephone Ring",
    "Helicopter",
    "Applause",
    "Gunshot",
)


ROLE_GM_PROGRAMS: dict[str, tuple[int, ...]] = {
    "bass": tuple(range(32, 40)),
    # A generic separated keys stem can contain layered synthesis, but a keys
    # audition still needs to behave like a keyboard instrument.  Programs
    # 80-95 are synth leads/pads and produced misleading sawtooth winners for
    # electric-piano material.  Use ``synth`` or ``pads`` when those families
    # are the intended role.
    "keys": tuple(range(0, 24)),
    "piano": tuple(range(0, 16)),
    "pads": tuple([*range(40, 56), *range(88, 96)]),
    "strings": tuple([*range(40, 56), 46, 47, 60, 61]),
    "lead": tuple([*range(8, 16), *range(24, 32), *range(56, 88)]),
    "synth": tuple([*range(38, 40), *range(80, 104)]),
    "vocal": tuple([*range(24, 32), *range(40, 88)]),
    "vocals": tuple([*range(24, 32), *range(40, 88)]),
    "backing": tuple([*range(40, 56), *range(64, 80), *range(88, 96)]),
    "backing_vocals": tuple([*range(40, 56), *range(64, 80), *range(88, 96)]),
}


ROLE_NAME_TOKENS: dict[str, tuple[str, ...]] = {
    "bass": ("bass", "contrabass", "tuba"),
    "keys": ("piano", "organ", "clav", "harpsi", "vibra", "glock", "marimba", "harp"),
    "piano": ("piano", "harpsi", "clav"),
    "pads": ("string", "choir", "organ", "horn", "ensemble"),
    "strings": ("string", "violin", "viola", "cello", "harp", "guitar"),
    "lead": (
        "sax",
        "flute",
        "clarinet",
        "oboe",
        "bassoon",
        "trumpet",
        "trombone",
        "horn",
        "guitar",
        "vibra",
        "glock",
        "marimba",
    ),
    "synth": ("synth", "organ", "string", "choir", "vibra", "glock"),
    "vocal": ("sax", "flute", "clarinet", "oboe", "trumpet", "horn", "guitar", "vibra"),
    "vocals": (
        "sax",
        "flute",
        "clarinet",
        "oboe",
        "trumpet",
        "horn",
        "guitar",
        "vibra",
    ),
    "backing": ("choir", "string", "horn", "organ", "ensemble"),
    "backing_vocals": ("choir", "string", "horn", "organ", "ensemble"),
}


DRUM_SAMPLE_TOKENS: dict[str, tuple[str, ...]] = {
    "kick": ("kick", "_bd", "bd_", "bassdrum", "bass drum"),
    "snare": ("snare", "_sd", "sd_"),
    "hat": ("hat", "_hh", "hh_", "hho", "closed", "openhat", "ophat"),
    "cymbals": ("cym", "crash", "ride"),
    "toms": ("tom",),
    "other_kit": (
        "perc",
        "clap",
        "rim",
        "shaker",
        "maraca",
        "cowbell",
        "conga",
        "bongo",
        "cabasa",
        "clave",
        "woodblock",
        "tambourine",
    ),
    "drums": (),
}


@dataclass(frozen=True)
class AudioUnitInstrument:
    display_name: str
    manufacturer: str | None
    component_type: str
    subtype: str | None
    manufacturer_code: str | None
    built_in: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FactoryAsset:
    name: str
    source: str
    root: str
    sample_count: int
    sample_files: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "root": self.root,
            "sample_count": self.sample_count,
            "representative_sample_files": list(self.sample_files[:5]),
        }


@dataclass(frozen=True)
class SamplerInstrumentPreset:
    name: str
    category: str
    source: str
    path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InstrumentInventory:
    garageband_installed: bool
    garageband_version: str | None
    garageband_sampler_root: str
    logic_drum_root: str
    factory_sampler_assets: tuple[FactoryAsset, ...]
    drum_kit_assets: tuple[FactoryAsset, ...]
    sampler_instrument_presets: tuple[SamplerInstrumentPreset, ...]
    audio_unit_instruments: tuple[AudioUnitInstrument, ...]
    component_directories: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "garageband_installed": self.garageband_installed,
            "garageband_version": self.garageband_version,
            "garageband_sampler_root": self.garageband_sampler_root,
            "logic_drum_root": self.logic_drum_root,
            "factory_sampler_asset_count": len(self.factory_sampler_assets),
            "drum_kit_asset_count": len(self.drum_kit_assets),
            "sampler_instrument_preset_count": len(self.sampler_instrument_presets),
            "audio_unit_instrument_count": len(self.audio_unit_instruments),
            "factory_sampler_assets": [
                asset.to_dict() for asset in self.factory_sampler_assets
            ],
            "drum_kit_assets": [asset.to_dict() for asset in self.drum_kit_assets],
            "sampler_instrument_presets": [
                preset.to_dict() for preset in self.sampler_instrument_presets
            ],
            "audio_unit_instruments": [
                instrument.to_dict() for instrument in self.audio_unit_instruments
            ],
            "component_directories": list(self.component_directories),
            "warnings": list(self.warnings),
        }


def program_candidates(kind: str, *, all_programs: bool = False) -> tuple[int, ...]:
    """Return deterministic zero-based GM programs worth auditioning."""

    normalized = kind.strip().lower()
    if all_programs:
        return tuple(range(128))
    programs = ROLE_GM_PROGRAMS.get(normalized)
    if programs is None:
        return tuple(range(128))
    return tuple(dict.fromkeys(programs))


def role_name_fit(name: str, kind: str) -> float:
    """Return a deliberately weak name-based prior from zero to one."""

    normalized = kind.strip().lower()
    if normalized in DRUM_SAMPLE_TOKENS:
        return 1.0
    tokens = ROLE_NAME_TOKENS.get(normalized, ())
    text = name.casefold()
    if any(token in text for token in tokens):
        return 1.0
    return 0.35


def inventory_instruments(
    *,
    garageband_sampler_root: str | Path | None = None,
    logic_drum_root: str | Path | None = None,
    garageband_instrument_root: str | Path | None = None,
    logic_instrument_root: str | Path | None = None,
    include_audio_units: bool = True,
) -> InstrumentInventory:
    """Inventory local sampler assets and macOS Audio Unit instruments."""

    sampler_root = Path(garageband_sampler_root or GARAGEBAND_SAMPLER_ROOT).expanduser()
    drum_root = Path(logic_drum_root or LOGIC_DRUM_ROOT).expanduser()
    garageband_presets_root = Path(
        garageband_instrument_root or GARAGEBAND_SAMPLER_INSTRUMENT_ROOT
    ).expanduser()
    logic_presets_root = Path(
        logic_instrument_root or LOGIC_SAMPLER_INSTRUMENT_ROOT
    ).expanduser()
    warnings: list[str] = []
    sampler_assets = tuple(_discover_sampler_assets(sampler_root))
    drum_assets = tuple(_discover_drum_assets(drum_root, kind="drums"))
    sampler_presets = tuple(
        [
            *_discover_sampler_instruments(
                garageband_presets_root, source="garageband_sampler_instrument"
            ),
            *_discover_sampler_instruments(
                logic_presets_root, source="logic_sampler_instrument"
            ),
        ]
    )
    if not sampler_root.is_dir():
        warnings.append(f"GarageBand sampler library not found: {sampler_root}")
    if not drum_root.is_dir():
        warnings.append(f"GarageBand/Logic drum sample library not found: {drum_root}")
    if not garageband_presets_root.is_dir():
        warnings.append(
            f"GarageBand sampler instrument library not found: {garageband_presets_root}"
        )
    if not logic_presets_root.is_dir():
        warnings.append(
            f"Logic sampler instrument library not found: {logic_presets_root}"
        )

    audio_units: tuple[AudioUnitInstrument, ...] = ()
    if include_audio_units:
        try:
            audio_units = tuple(list_audio_unit_instruments())
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            warnings.append(f"Audio Unit inventory unavailable: {exc}")

    component_directories = tuple(
        str(path)
        for path in (
            Path("/Library/Audio/Plug-Ins/Components"),
            Path.home() / "Library/Audio/Plug-Ins/Components",
        )
        if path.is_dir()
    )
    return InstrumentInventory(
        garageband_installed=GARAGEBAND_APP.is_dir(),
        garageband_version=_garageband_version(GARAGEBAND_APP),
        garageband_sampler_root=str(sampler_root),
        logic_drum_root=str(drum_root),
        factory_sampler_assets=sampler_assets,
        drum_kit_assets=drum_assets,
        sampler_instrument_presets=sampler_presets,
        audio_unit_instruments=audio_units,
        component_directories=component_directories,
        warnings=tuple(warnings),
    )


def discover_factory_assets(
    kind: str,
    *,
    garageband_sampler_root: str | Path | None = None,
    logic_drum_root: str | Path | None = None,
) -> tuple[FactoryAsset, ...]:
    """Return installed assets suitable for one stem role."""

    normalized = kind.strip().lower()
    sampler_root = Path(garageband_sampler_root or GARAGEBAND_SAMPLER_ROOT).expanduser()
    drum_root = Path(logic_drum_root or LOGIC_DRUM_ROOT).expanduser()
    if normalized in DRUM_SAMPLE_TOKENS:
        assets = list(_discover_drum_assets(drum_root, normalized))
        assets.extend(
            asset
            for asset in _discover_sampler_assets(sampler_root, kind=normalized)
            if asset.sample_count
        )
        return tuple(
            sorted(assets, key=lambda item: (item.source, item.name.casefold()))
        )
    return tuple(_discover_sampler_assets(sampler_root))


def list_audio_unit_instruments() -> list[AudioUnitInstrument]:
    """Return Audio Unit music devices (``aumu``) reported by ``auval``."""

    executable = shutil.which("auval")
    if executable is None:
        return []
    result = subprocess.run(
        [executable, "-a"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"auval -a failed with exit {result.returncode}")
    instruments: list[AudioUnitInstrument] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped.startswith("aumu ") or " - " not in stripped:
            continue
        identity, display = stripped.split(" - ", 1)
        fields = identity.split()
        subtype = fields[1] if len(fields) > 1 else None
        manufacturer_code = fields[2] if len(fields) > 2 else None
        manufacturer = None
        name = display.strip()
        if ":" in name:
            manufacturer, name = (part.strip() for part in name.split(":", 1))
        built_in = manufacturer_code == "appl" or manufacturer == "Apple"
        instruments.append(
            AudioUnitInstrument(
                display_name=name,
                manufacturer=manufacturer,
                component_type="aumu",
                subtype=subtype,
                manufacturer_code=manufacturer_code,
                built_in=built_in,
            )
        )
    return sorted(
        instruments,
        key=lambda item: (
            not item.built_in,
            (item.manufacturer or "").casefold(),
            item.display_name.casefold(),
        ),
    )


def _discover_sampler_assets(
    root: Path,
    *,
    kind: str | None = None,
) -> Iterable[FactoryAsset]:
    if not root.is_dir():
        return ()
    assets: list[FactoryAsset] = []
    for folder in sorted(root.iterdir(), key=lambda path: path.name.casefold()):
        if not folder.is_dir():
            continue
        files = _audio_files(folder)
        if kind in DRUM_SAMPLE_TOKENS:
            files = [path for path in files if drum_sample_matches(path.name, kind)]
        if files:
            assets.append(
                FactoryAsset(
                    name=folder.name,
                    source="garageband_factory_sampler",
                    root=str(folder),
                    sample_count=len(files),
                    sample_files=tuple(str(path) for path in files),
                )
            )
    return assets


def _discover_drum_assets(root: Path, kind: str) -> Iterable[FactoryAsset]:
    if not root.is_dir():
        return ()
    assets: list[FactoryAsset] = []
    for folder in sorted(root.iterdir(), key=lambda path: path.name.casefold()):
        if not folder.is_dir():
            continue
        files = _audio_files(folder)
        if kind != "drums":
            files = [path for path in files if drum_sample_matches(path.name, kind)]
        if files:
            assets.append(
                FactoryAsset(
                    name=folder.name,
                    source="garageband_logic_drum_kit",
                    root=str(folder),
                    sample_count=len(files),
                    sample_files=tuple(str(path) for path in files),
                )
            )
    return assets


def _discover_sampler_instruments(
    root: Path,
    *,
    source: str,
) -> Iterable[SamplerInstrumentPreset]:
    if not root.is_dir():
        return ()
    presets = []
    for path in sorted(root.rglob("*.exs"), key=lambda item: str(item).casefold()):
        relative_parent = path.parent.relative_to(root)
        category = str(relative_parent) if relative_parent.parts else "Uncategorised"
        presets.append(
            SamplerInstrumentPreset(
                name=path.stem,
                category=category,
                source=source,
                path=str(path),
            )
        )
    return presets


def drum_sample_matches(name: str, kind: str) -> bool:
    normalized = kind.strip().lower()
    tokens = DRUM_SAMPLE_TOKENS.get(normalized)
    if tokens is None or not tokens:
        return True
    text = name.casefold().replace("-", "_")
    return any(token in text for token in tokens)


def _audio_files(root: Path) -> list[Path]:
    return [
        path
        for path in sorted(root.rglob("*"), key=lambda item: str(item).casefold())
        if path.is_file()
        and (path.suffix.casefold() in AUDIO_SUFFIXES or not path.suffix)
    ]


def _garageband_version(app: Path) -> str | None:
    plist = app / "Contents/Info.plist"
    if not plist.is_file():
        return None
    try:
        with plist.open("rb") as handle:
            info = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException):
        return None
    value = info.get("CFBundleShortVersionString")
    return str(value) if value is not None else None


__all__ = [
    "AUDIO_SUFFIXES",
    "AudioUnitInstrument",
    "FactoryAsset",
    "GARAGEBAND_SAMPLER_INSTRUMENT_ROOT",
    "GARAGEBAND_SAMPLER_ROOT",
    "GM_PROGRAM_NAMES",
    "InstrumentInventory",
    "LOGIC_DRUM_ROOT",
    "LOGIC_SAMPLER_INSTRUMENT_ROOT",
    "SamplerInstrumentPreset",
    "discover_factory_assets",
    "drum_sample_matches",
    "inventory_instruments",
    "list_audio_unit_instruments",
    "program_candidates",
    "role_name_fit",
]
