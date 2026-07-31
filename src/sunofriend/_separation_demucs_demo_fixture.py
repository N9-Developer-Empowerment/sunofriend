"""Copyright-safe four-role fixture for the private Demucs bake-off."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

from .demo import create_demo_project
from .separation_quality import inspect_pcm_wav


PRIVATE_DEMUCS_DEMO_SCHEMA = "sunofriend.private-demucs-demo-fixture.v1"
PRIVATE_DEMUCS_DEMO_POLICY = "fixed-demo-to-four-broad-roles-v1"
_REFERENCE_ROLES = ("bass", "drums", "other", "vocals")


def _create_private_demucs_demo_fixture(out_dir: str | Path) -> dict[str, Any]:
    """Create an 8-second stereo mixture with exact broad-role references."""

    import numpy as np
    import soundfile

    destination = Path(out_dir).expanduser().resolve()
    if os.path.lexists(destination):
        raise FileExistsError(
            f"Private Demucs demo fixture already exists: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(mode=0o700)
    destination.chmod(0o700)
    try:
        demo = create_demo_project(destination / "unused-product-output")
        source_manifest = json.loads(demo.manifest_path.read_text(encoding="utf-8"))
        by_role = {
            item["role"]: demo.root / item["file"] for item in source_manifest["stems"]
        }
        arrays: dict[str, Any] = {}
        sample_rate: int | None = None
        frames: int | None = None
        for role in ("kick", "snare", "hat", "bass", "keys", "lead"):
            value, rate = soundfile.read(by_role[role], dtype="float32", always_2d=True)
            if value.shape[1] != 1:
                raise ValueError("synthetic demo stems must remain mono")
            if sample_rate is None:
                sample_rate = int(rate)
                frames = int(value.shape[0])
            if rate != sample_rate or value.shape[0] != frames:
                raise ValueError("synthetic demo stem geometry changed")
            arrays[role] = value[:, 0].astype("float64")
        assert sample_rate is not None
        assert frames is not None

        scale = 0.5
        drums_mono = scale * (arrays["kick"] + arrays["snare"] + arrays["hat"])
        bass_mono = scale * arrays["bass"]
        references = {
            "drums": np.column_stack((drums_mono, drums_mono)),
            "bass": np.column_stack((bass_mono, bass_mono)),
            "other": scale
            * np.column_stack(
                (
                    arrays["keys"] + 0.75 * arrays["lead"],
                    0.75 * arrays["keys"] + arrays["lead"],
                )
            ),
            "vocals": np.zeros((frames, 2), dtype="float64"),
        }
        reference_dir = destination / "GROUND-TRUTH"
        reference_dir.mkdir(mode=0o700)
        reference_dir.chmod(0o700)
        persisted: dict[str, Any] = {}
        reference_evidence: dict[str, Any] = {}
        for role in _REFERENCE_ROLES:
            value = references[role]
            if int(np.count_nonzero(np.abs(value) > 1.0)):
                raise ValueError(f"synthetic {role} reference would clip")
            path = reference_dir / f"{role}.wav"
            soundfile.write(path, value, sample_rate, subtype="PCM_24")
            reopened, rate = soundfile.read(path, dtype="float32", always_2d=True)
            if rate != sample_rate or reopened.shape != (frames, 2):
                raise ValueError(f"persisted {role} reference geometry changed")
            persisted[role] = reopened
            inspection = inspect_pcm_wav(path)
            reference_evidence[role] = {
                "path": str(path.relative_to(destination)),
                "sha256": inspection.sha256,
                "geometry": inspection.geometry.to_dict(),
                "peak": inspection.peak,
                "rms": inspection.rms,
                "silence_fraction": inspection.silence_fraction,
                "clipped_samples": inspection.clipped_samples,
            }

        mixture = np.zeros((frames, 2), dtype="float32")
        for role in _REFERENCE_ROLES:
            mixture += persisted[role]
        if int(np.count_nonzero(np.abs(mixture) > 1.0)):
            raise ValueError("synthetic broad-role mixture would clip")
        mixture_path = destination / "private-demo-mix.wav"
        soundfile.write(mixture_path, mixture, sample_rate, subtype="PCM_24")
        mixture_inspection = inspect_pcm_wav(mixture_path)
        document: dict[str, Any] = {
            "schema": PRIVATE_DEMUCS_DEMO_SCHEMA,
            "policy_id": PRIVATE_DEMUCS_DEMO_POLICY,
            "source_kind": (
                "fixed mathematical waveforms and deterministic noise; "
                "no recordings, samples, lyrics or third-party audio"
            ),
            "geometry": {
                "sample_rate": sample_rate,
                "channels": 2,
                "frames": frames,
                "duration_seconds": frames / sample_rate,
            },
            "mapping": {
                "drums": ["kick", "snare", "hat"],
                "bass": ["bass"],
                "other": ["keys", "lead"],
                "vocals": [],
            },
            "stereo_policy": {
                "global_scale": scale,
                "drums": "centred",
                "bass": "centred",
                "other_left": "keys + 0.75 * lead",
                "other_right": "0.75 * keys + lead",
                "vocals": "exact digital silence",
            },
            "mixture": {
                "path": str(mixture_path.relative_to(destination)),
                "sha256": mixture_inspection.sha256,
                "peak": mixture_inspection.peak,
                "rms": mixture_inspection.rms,
                "clipped_samples": mixture_inspection.clipped_samples,
            },
            "references": reference_evidence,
            "source_demo": {
                "manifest": str(demo.manifest_path.relative_to(destination)),
                "manifest_sha256": _sha256(demo.manifest_path),
                "generator_policy": source_manifest["generator_policy"],
            },
            "permissions": {
                "private_model_evaluation": True,
                "quality_acceptance": False,
                "automatic_promotion": False,
                "public_result": False,
            },
        }
        document["document_sha256"] = _document_sha256(document)
        manifest_path = destination / "private-demucs-demo-fixture.json"
        _write_json(manifest_path, document)
        document["root"] = str(destination)
        document["manifest"] = str(manifest_path)
        document["mixture_path"] = str(mixture_path)
        document["reference_paths"] = {
            role: str(reference_dir / f"{role}.wav") for role in _REFERENCE_ROLES
        }
        return document
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def _document_sha256(document: dict[str, Any]) -> str:
    canonical = dict(document)
    canonical.pop("document_sha256", None)
    payload = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, document: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            document,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


__all__: tuple[str, ...] = ()
