"""Create GarageBand-selectable AUSampler presets for SoundFont banks.

GarageBand exposes AUSampler's plug-in preset chooser, but not the separate
``loadSoundBankInstrument`` API used by AVAudioUnitSampler.  Consequently a
valid ``.sf2`` bank is greyed out in GarageBand's ``Load Setting`` panel.  An
``.aupreset`` wrapper bridges that UI/API mismatch while keeping the SF2 as
the self-contained sample bank.
"""

from __future__ import annotations

import plistlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


class AUSamplerPresetError(RuntimeError):
    """Raised when a GarageBand AUSampler preset cannot be produced."""


_WRITE_PRESET_SWIFT = r"""
import Foundation
import AVFoundation
import AudioToolbox

let source = URL(fileURLWithPath: CommandLine.arguments[1])
let output = URL(fileURLWithPath: CommandLine.arguments[2])
let installedBank = URL(fileURLWithPath: CommandLine.arguments[3])
let sampler = AVAudioUnitSampler()

try sampler.loadSoundBankInstrument(
    at: source,
    program: 0,
    bankMSB: UInt8(kAUSampler_DefaultMelodicBankMSB),
    bankLSB: UInt8(kAUSampler_DefaultBankLSB)
)

guard var state = sampler.auAudioUnit.fullState else {
    throw NSError(
        domain: "Sunofriend.AUSampler",
        code: 1,
        userInfo: [NSLocalizedDescriptionKey: "AUSampler returned no full state"]
    )
}

guard var references = state["file-references"] as? [String: Any],
      !references.isEmpty else {
    throw NSError(
        domain: "Sunofriend.AUSampler",
        code: 2,
        userInfo: [NSLocalizedDescriptionKey: "AUSampler returned no bank reference"]
    )
}

for key in references.keys {
    references[key] = installedBank.path
}
state["file-references"] = references

let data = try PropertyListSerialization.data(
    fromPropertyList: state,
    format: .xml,
    options: 0
)
try data.write(to: output, options: .atomic)
print("created")
"""


def write_ausampler_preset(
    soundfont_path: str | Path,
    output_path: str | Path,
    *,
    referenced_soundfont_path: str | Path | None = None,
) -> dict[str, Any]:
    """Wrap one SF2 bank in a GarageBand-selectable ``.aupreset`` file.

    ``soundfont_path`` is the bank loaded while producing the preset.
    ``referenced_soundfont_path`` is the final, stable location GarageBand
    should open later; it may differ while a sample pack is assembled in a
    temporary directory.
    """

    source = Path(soundfont_path).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    reference = Path(referenced_soundfont_path or source).expanduser().resolve()
    if not source.is_file():
        raise AUSamplerPresetError(f"SoundFont file not found: {source}")
    if output.suffix.lower() != ".aupreset":
        raise AUSamplerPresetError("AUSampler preset must use the .aupreset extension")
    if sys.platform != "darwin":
        raise AUSamplerPresetError(
            "AUSampler preset generation requires macOS and Apple's sampler"
        )
    swift = shutil.which("swift")
    if not swift:
        raise AUSamplerPresetError(
            "AUSampler preset generation requires the macOS Swift command"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [
                swift,
                "-e",
                _WRITE_PRESET_SWIFT,
                str(source),
                str(output),
                str(reference),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        output.unlink(missing_ok=True)
        raise AUSamplerPresetError(
            f"Apple AUSampler preset generation could not run: {exc}"
        ) from exc
    if result.returncode != 0:
        output.unlink(missing_ok=True)
        detail = (result.stderr or result.stdout).strip()
        raise AUSamplerPresetError(
            "Apple AUSampler could not create the GarageBand preset"
            + (f": {detail}" if detail else "")
        )

    try:
        with output.open("rb") as handle:
            state = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException) as exc:
        output.unlink(missing_ok=True)
        raise AUSamplerPresetError(
            f"Generated AUSampler preset is not a valid property list: {exc}"
        ) from exc
    references = state.get("file-references")
    if not isinstance(references, dict) or str(reference) not in references.values():
        output.unlink(missing_ok=True)
        raise AUSamplerPresetError(
            "Generated AUSampler preset does not reference the final SoundFont"
        )
    return {
        "path": output.name,
        "soundfont_reference": str(reference),
        "byte_size": output.stat().st_size,
        "type": state.get("type"),
        "subtype": state.get("subtype"),
        "manufacturer": state.get("manufacturer"),
    }


__all__ = ["AUSamplerPresetError", "write_ausampler_preset"]
