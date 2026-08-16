"""Fresh immutable local STT evidence for vocal comping."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .vocal_comp import _document_sha256, _file, _sha256, _write_json


VOCAL_COMP_STT_RUN_SCHEMA = "sunofriend.vocal-comp-stt-run.v1"


def run_vocal_comp_stt(
    audio: str | Path,
    *,
    checkpoint: str | Path,
    python: str | Path,
    model_label: str,
    source_id: str,
    out_dir: str | Path,
    timeout_seconds: float = 1800.0,
) -> dict[str, Any]:
    """Run unprompted local Whisper; never download or rewrite canonical lyrics."""

    audio_path = _file(audio, "vocal audio")
    checkpoint_path = _file(checkpoint, "Whisper checkpoint")
    try:
        python_path = Path(python).expanduser().absolute().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("Whisper Python interpreter does not exist") from exc
    if not python_path.is_file():
        raise ValueError("Whisper Python interpreter is not a file")
    if not os.access(python_path, os.X_OK):
        raise ValueError("Whisper Python interpreter is not executable")
    if not source_id or any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        for character in source_id
    ):
        raise ValueError("source_id must be a safe identifier")
    if not model_label.strip() or len(model_label) > 64:
        raise ValueError("model_label must be 1-64 characters")
    if not 1.0 <= float(timeout_seconds) <= 7200.0:
        raise ValueError("timeout_seconds must be between 1 and 7200")
    destination = Path(out_dir).expanduser().absolute()
    if destination.exists():
        raise ValueError(f"STT output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_sha256 = _sha256(audio_path)
    checkpoint_sha256 = _sha256(checkpoint_path)
    python_sha256 = _sha256(python_path.resolve())
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent)
    )
    os.chmod(temporary, 0o700)
    try:
        transcript_path = temporary / "transcript.words.json"
        worker = Path(__file__).with_name("_vocal_comp_whisper_worker.py")
        command = [
            str(python_path),
            "-I",
            "-B",
            str(worker),
            "--audio",
            str(audio_path),
            "--checkpoint",
            str(checkpoint_path),
            "--model-label",
            model_label,
            "--out",
            str(transcript_path),
        ]
        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"}
        }
        environment.update(
            {
                "PYTHONNOUSERSITE": "1",
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
            }
        )
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=float(timeout_seconds),
            env=environment,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "local Whisper worker failed: "
                + (completed.stderr or completed.stdout)[-1000:]
            )
        if not transcript_path.is_file() or transcript_path.stat().st_size == 0:
            raise RuntimeError("local Whisper worker produced no transcript")
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
        if (
            transcript.get("schema") != "sunofriend.vocal-comp-stt-candidate.v1"
            or transcript.get("status") != "complete_unreviewed"
            or transcript.get("canonical_lyrics_prompted") is not False
            or transcript.get("word_timestamps") is not True
        ):
            raise RuntimeError("local Whisper worker returned an unsupported document")
        if _sha256(audio_path) != source_sha256:
            raise RuntimeError("vocal audio changed during STT")
        if _sha256(checkpoint_path) != checkpoint_sha256:
            raise RuntimeError("Whisper checkpoint changed during STT")
        word_count = sum(
            len(segment.get("words", [])) for segment in transcript.get("segments", [])
        )
        run = {
            "schema": VOCAL_COMP_STT_RUN_SCHEMA,
            "status": "complete_unreviewed",
            "source_id": source_id,
            "audio": {
                "bytes": audio_path.stat().st_size,
                "sha256": source_sha256,
            },
            "checkpoint": {
                "bytes": checkpoint_path.stat().st_size,
                "sha256": checkpoint_sha256,
                "model_label": model_label,
            },
            "runtime": {
                "python_sha256": python_sha256,
                "worker_sha256": _sha256(worker),
            },
            "transcript": {
                "path": "transcript.words.json",
                "bytes": transcript_path.stat().st_size,
                "sha256": _sha256(transcript_path),
                "word_count": word_count,
            },
            "canonical_lyrics_prompted": False,
            "review_required": True,
            "automatic_selection": False,
            "audio_comp_rendered": False,
            "pitch_correction_applied": False,
            "network_used": False,
        }
        run["run_sha256"] = _document_sha256(run)
        _write_json(temporary / "run.json", run)
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        **run,
        "output_directory": str(destination),
        "run": str(destination / "run.json"),
        "transcript_path": str(destination / "transcript.words.json"),
    }


__all__ = ["VOCAL_COMP_STT_RUN_SCHEMA", "run_vocal_comp_stt"]
