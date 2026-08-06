"""Public, opt-in local alpha for broad vocal/instrumental separation.

The product boundary in this module is deliberately small.  It accepts one
authorised local audio file, decodes it to an exact clock, invokes the pinned
Kim Vocal 2 MLX worker in a separate Python 3.12/3.13 environment, and creates
two broad stems plus a reconstruction diagnostic and a local review page.

This is not a claim of ground-truth separation and it does not silently feed
the generated stems into MIDI conversion.  The musician listens first, then
decides whether the stems are useful enough for a separate Sunofriend run.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ._separation_melroformer_artifacts import (
    _inspect_companion_files,
    _inspect_local_checkpoint,
)
from ._separation_melroformer_runtime_evidence import (
    _verify_private_melroformer_source_tree,
)
from .audio_formats import (
    DEFAULT_AUDIO_IMPORT_LIMITS,
    AudioProbe,
    decoder_capability_report,
    file_sha256,
    probe_stable_audio,
    resolve_executable,
)
from .source_import import _ffmpeg_decode_arguments
from .source_project import RIGHTS_CATEGORIES


SCHEMA = "sunofriend.experimental-separation-alpha.v1"
PLAN_SCHEMA = "sunofriend.experimental-separation-plan.v1"
PROFILE_NAME = "kim-vocal-2-mlx-v1"
MODEL_ID = "mlx-community/mel-roformer-kim-vocal-2-mlx"
MODEL_REVISION = "64cbfcb004e39430e5f584552c05949440ec39ce"
FEEDBACK_URL = (
    "https://github.com/N9-Developer-Empowerment/sunofriend/issues/new"
    "?template=daw-ai-compatibility.yml"
)
MINIMUM_FREE_HEADROOM_BYTES = 1024**3


@dataclass(frozen=True)
class SeparationProfile:
    repository_root: Path
    runtime_python: Path
    model_root: Path
    source_root: Path
    checkpoint: Path
    companion_root: Path


@dataclass(frozen=True)
class SeparationPlan:
    source: Path
    output: Path
    source_sha256: str
    probe: AudioProbe
    ffmpeg: Path
    ffprobe: Path
    decoder: Mapping[str, Any]
    profile: SeparationProfile
    device: str
    rights_category: str
    required_free_bytes: int
    available_free_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PLAN_SCHEMA,
            "status": "ready_explicit_execution_required",
            "experimental": True,
            "source": {
                "name": self.source.name,
                "bytes": self.probe.source_bytes,
                "sha256": self.source_sha256,
                "probe": self.probe.to_dict(),
            },
            "output": str(self.output),
            "separator": {
                "model_id": MODEL_ID,
                "model_revision": MODEL_REVISION,
                "device": self.device,
                "roles": ["vocals", "instrumental"],
                "diagnostic": "reconstruction-check",
            },
            "rights": {
                "category": self.rights_category,
                "confirmation_required_for_execution": True,
            },
            "resources": {
                "required_free_bytes": self.required_free_bytes,
                "available_free_bytes": self.available_free_bytes,
            },
            "effects_if_executed": {
                "writes": [str(self.output)],
                "network": [],
                "installs": [],
                "uploads": [],
            },
            "limitations": [
                "This alpha produces broad vocals and broad instrumental only.",
                "The outputs are estimates and require human listening.",
                "Chunk joins can contain audible changes or artefacts.",
                "No stem, model or musical default is selected from feedback automatically.",
            ],
        }


WorkerRunner = Callable[[SeparationPlan, Path], Mapping[str, Any]]


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_profile(
    *,
    root: str | Path | None = None,
    runtime_python: str | Path | None = None,
    model_root: str | Path | None = None,
) -> SeparationProfile:
    repo = Path(root).expanduser().absolute() if root else repository_root()
    data_root = Path(
        os.environ.get(
            "SUNOFRIEND_SEPARATION_ROOT",
            str(Path.home() / ".local/share/sunofriend/separation"),
        )
    ).expanduser().absolute()
    model = Path(
        model_root
        or os.environ.get("SUNOFRIEND_SEPARATION_MODEL_ROOT", "")
        or data_root / PROFILE_NAME
    ).expanduser().absolute()
    runtime = Path(
        runtime_python
        or os.environ.get("SUNOFRIEND_SEPARATION_PYTHON", "")
        or model / "runtime/bin/python"
    ).expanduser().absolute()
    return SeparationProfile(
        repository_root=repo,
        runtime_python=runtime,
        model_root=model,
        source_root=model / "mlx-audio-source",
        checkpoint=model / "model.safetensors",
        companion_root=model / "checkpoint-directory",
    )


def separation_doctor(profile: SeparationProfile) -> dict[str, Any]:
    """Read-only verification of platform, runtime and exact local artifacts."""

    checks: dict[str, dict[str, Any]] = {}
    machine = platform.machine().casefold()
    system = platform.system()
    checks["platform"] = {
        "ready": system == "Darwin" and machine == "arm64",
        "system": system,
        "machine": machine,
        "required": "macOS on Apple silicon",
    }
    checks["repository"] = {
        "ready": (profile.repository_root / "pyproject.toml").is_file(),
    }
    checks["runtime"] = _runtime_check(profile.runtime_python)
    checks["source_overlay"] = _safe_check(
        lambda: _verify_private_melroformer_source_tree(profile.source_root)
    )
    checks["checkpoint"] = _safe_check(
        lambda: _require_verified_checkpoint(profile.checkpoint)
    )
    checks["companions"] = _safe_check(
        lambda: _require_verified_companions(profile.companion_root)
    )
    ready = all(bool(item.get("ready")) for item in checks.values())
    return {
        "schema": "sunofriend.experimental-separation-doctor.v1",
        "status": "ready" if ready else "setup_required",
        "ready": ready,
        "experimental": True,
        "checks": checks,
        "setup_command": "scripts/setup-separation-alpha-macos.sh --install --accept-model-terms",
        "effects": {
            "filesystem_write": False,
            "network_used": False,
            "model_loaded": False,
            "audio_processed": False,
        },
    }


def plan_separation(
    source: str | Path,
    output: str | Path,
    *,
    rights_category: str,
    device: str = "gpu",
    ffmpeg: str | Path = "ffmpeg",
    ffprobe: str | Path = "ffprobe",
    profile: SeparationProfile | None = None,
) -> SeparationPlan:
    if rights_category not in RIGHTS_CATEGORIES - {"unknown", "declined_to_state"}:
        raise ValueError(
            "separation requires one affirmative rights category: "
            "owned, licensed, authorised_private_use or statutory_exception"
        )
    if device not in {"gpu", "cpu"}:
        raise ValueError("separation device must be gpu or cpu")
    selected = profile or resolve_profile()
    doctor = separation_doctor(selected)
    if not doctor["ready"]:
        missing = ", ".join(
            name for name, item in doctor["checks"].items() if not item.get("ready")
        )
        raise RuntimeError(
            f"experimental separation setup is not ready ({missing}); run "
            f"{doctor['setup_command']}"
        )
    ffmpeg_path = resolve_executable(ffmpeg)
    ffprobe_path = resolve_executable(ffprobe)
    decoder = decoder_capability_report(ffmpeg=ffmpeg_path, ffprobe=ffprobe_path)
    if not decoder["policy"]["pcm24_encoder_available"]:
        raise RuntimeError("the selected FFmpeg build does not provide pcm_s24le")
    probe, digest = probe_stable_audio(source, ffprobe=ffprobe_path)
    destination = Path(output).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"separation output already exists: {destination}")
    parent = _nearest_existing_parent(destination.parent)
    available = shutil.disk_usage(parent).free
    frames = int(probe.duration_seconds * 44_100 + 0.999999)
    required = max(
        MINIMUM_FREE_HEADROOM_BYTES,
        probe.source_bytes + frames * 40,
    )
    if available < required:
        raise OSError(
            f"insufficient free space: need {required} bytes, found {available}"
        )
    return SeparationPlan(
        source=Path(source).expanduser().absolute().resolve(),
        output=destination,
        source_sha256=digest,
        probe=probe,
        ffmpeg=ffmpeg_path,
        ffprobe=ffprobe_path,
        decoder=decoder,
        profile=selected,
        device=device,
        rights_category=rights_category,
        required_free_bytes=required,
        available_free_bytes=available,
    )


def execute_separation(
    plan: SeparationPlan,
    *,
    confirm_rights: bool,
    worker_runner: WorkerRunner | None = None,
) -> dict[str, Any]:
    """Execute a verified plan into one fresh, atomically published folder."""

    if confirm_rights is not True:
        raise PermissionError(
            "execution requires --confirm-rights for audio you may process"
        )
    if os.path.lexists(plan.output):
        raise FileExistsError(f"separation output already exists: {plan.output}")
    if file_sha256(plan.source) != plan.source_sha256:
        raise ValueError("source audio changed after the separation plan")
    doctor = separation_doctor(plan.profile)
    if not doctor["ready"]:
        raise RuntimeError("experimental separation setup changed after planning")
    plan.output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{plan.output.name}.building-",
            dir=plan.output.parent,
        )
    )
    try:
        canonical = staging / "TEMP/source-44100-stereo-pcm24.wav"
        canonical.parent.mkdir(parents=True, exist_ok=False)
        arguments = _ffmpeg_decode_arguments(
            plan.source,
            canonical,
            duration_seconds=plan.probe.duration_seconds,
            maximum_output_bytes=DEFAULT_AUDIO_IMPORT_LIMITS.maximum_canonical_bytes,
        )
        _run_command(
            [str(plan.ffmpeg), *arguments],
            timeout=max(120.0, min(1800.0, plan.probe.duration_seconds * 4.0)),
            label="FFmpeg canonical decode",
        )
        run_worker = worker_runner or _run_worker
        worker = dict(run_worker(plan, staging))
        if worker.get("status") != "complete_unreviewed":
            raise RuntimeError("experimental separation worker did not complete")
        shutil.rmtree(staging / "TEMP", ignore_errors=True)
        report = _build_report(plan, worker=worker, doctor=doctor, root=staging)
        technical = staging / "TECHNICAL"
        technical.mkdir(exist_ok=True)
        _write_json(technical / "separation-report.json", report)
        (staging / "START-HERE.txt").write_text(
            _start_here(report), encoding="utf-8"
        )
        review_dir = staging / "REVIEW"
        review_dir.mkdir(exist_ok=True)
        (review_dir / "separation_review.html").write_text(
            _review_html(report), encoding="utf-8"
        )
        os.replace(staging, plan.output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        **report,
        "root": str(plan.output),
        "start_here": str(plan.output / "START-HERE.txt"),
        "review_html": str(plan.output / "REVIEW/separation_review.html"),
        "vocals": str(plan.output / "STEMS/vocals.wav"),
        "instrumental": str(plan.output / "STEMS/instrumental.wav"),
    }


def _run_worker(plan: SeparationPlan, staging: Path) -> Mapping[str, Any]:
    result = staging / "worker-result.json"
    command = [
        str(plan.profile.runtime_python),
        str(plan.profile.repository_root / "src/sunofriend/separation_worker.py"),
        "--source",
        str(staging / "TEMP/source-44100-stereo-pcm24.wav"),
        "--destination",
        str(staging),
        "--result",
        str(result),
        "--source-root",
        str(plan.profile.source_root),
        "--checkpoint",
        str(plan.profile.checkpoint),
        "--companion-root",
        str(plan.profile.companion_root),
        "--device",
        plan.device,
    ]
    environment = dict(os.environ)
    source_path = str(plan.profile.repository_root / "src")
    environment["PYTHONPATH"] = (
        source_path
        if not environment.get("PYTHONPATH")
        else source_path + os.pathsep + environment["PYTHONPATH"]
    )
    environment.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PYTHONNOUSERSITE": "1",
        }
    )
    _run_command(
        command,
        timeout=max(900.0, min(7200.0, plan.probe.duration_seconds * 30.0)),
        label="local separation worker",
        env=environment,
    )
    try:
        document = json.loads(result.read_text(encoding="utf-8"))
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("separation worker result is missing or invalid") from exc
    result.unlink()
    return document


def _build_report(
    plan: SeparationPlan,
    *,
    worker: Mapping[str, Any],
    doctor: Mapping[str, Any],
    root: Path,
) -> dict[str, Any]:
    outputs: dict[str, dict[str, Any]] = {}
    for role, relative in {
        "vocals": "STEMS/vocals.wav",
        "instrumental": "STEMS/instrumental.wav",
        "source_reference": "SOURCE/source-reference.wav",
        "reconstruction_check": "AUDIO/reconstruction-check.wav",
    }.items():
        path = root / relative
        if not path.is_file():
            raise RuntimeError(f"separation worker omitted {relative}")
        outputs[role] = {
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "complete_unreviewed",
        "review_status": "not_reviewed",
        "quality_status": "human_listening_required",
        "experimental": True,
        "local_only": True,
        "source": {
            "name": plan.source.name,
            "bytes": plan.probe.source_bytes,
            "sha256": plan.source_sha256,
            "duration_seconds": plan.probe.duration_seconds,
        },
        "rights": {
            "category": plan.rights_category,
            "confirmed_before_execution": True,
        },
        "separator": {
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "device": plan.device,
            "scope": "broad_vocals_plus_complementary_instrumental",
            "worker": worker,
        },
        "outputs": outputs,
        "doctor": {
            "status": doctor["status"],
            "exact_profile_verified": doctor["ready"],
        },
        "feedback": {
            "local_review": "REVIEW/separation_review.html",
            "public_report_url": FEEDBACK_URL,
            "audio_uploaded_automatically": False,
            "review_uploaded_automatically": False,
        },
        "next_steps": [
            "Open START-HERE.txt and listen in the local review page.",
            "Use the stems only if your listening review finds them useful.",
            "Put useful stems in a new folder before running Sunofriend create or Studio.",
            "Share text-only observations through the public feedback link if you choose.",
        ],
        "limitations": [
            "This alpha does not split drums, bass, keys or other instruments separately.",
            "A good reconstruction check proves additive accounting, not stem accuracy.",
            "Vocals can contain accompaniment; instrumental can contain vocal bleed.",
            "Chunk boundaries and model artefacts require human listening.",
            "Feedback is advisory and never silently changes a model or musical default.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)
    return document


def _start_here(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "SUNOFRIEND EXPERIMENTAL STEM SEPARATION",
            "",
            "1. Open REVIEW/separation_review.html in a normal browser.",
            "2. Compare SOURCE/source-reference.wav with both files in STEMS/.",
            "3. Judge usefulness, bleed, missing sound and joins with headphones if possible.",
            "4. AUDIO/reconstruction-check.wav should resemble the source; that checks accounting, not separation accuracy.",
            "5. If the stems are useful, copy them into a new folder and run Sunofriend on that folder.",
            "",
            "What this alpha made:",
            "- STEMS/vocals.wav: estimated broad vocal content",
            "- STEMS/instrumental.wav: source minus estimated vocals",
            "- SOURCE/source-reference.wav: level-managed local reference",
            "- AUDIO/reconstruction-check.wav: sum of the two persisted stems",
            "",
            "Important: these are unreviewed estimates, not ground truth. No audio was uploaded.",
            f"Optional text-only feedback: {report['feedback']['public_report_url']}",
            "Do not attach private music, stems or vocals to a public issue.",
            "",
        ]
    )


def _review_html(report: Mapping[str, Any]) -> str:
    source_name = html.escape(str(report["source"]["name"]))
    feedback = html.escape(str(report["feedback"]["public_report_url"]), quote=True)
    report_hash = html.escape(str(report["document_sha256"]), quote=True)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sunofriend separation review</title><style>
:root{{--bg:#07111d;--panel:#102030;--line:#29455d;--text:#eef7ff;--muted:#a8bfd0;--cyan:#35daf2;--yellow:#ffd24a}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:18px/1.5 system-ui,sans-serif}}main{{max-width:980px;margin:auto;padding:32px}}section{{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:24px;margin:18px 0}}h1{{font-size:clamp(2rem,6vw,4rem);line-height:1}}h2{{color:var(--cyan)}}audio{{width:100%}}label{{display:block;margin:12px 0}}textarea{{width:100%;min-height:120px;background:#071522;color:var(--text);border:1px solid var(--line);padding:12px}}button,a.button{{display:inline-block;background:#15658c;color:white;border:0;border-radius:8px;padding:12px 16px;margin:6px 6px 6px 0;text-decoration:none;cursor:pointer}}.warning{{border-left:5px solid var(--yellow);padding-left:14px}}.muted{{color:var(--muted)}}
</style></head><body><main><h1>Listen before you use the stems.</h1>
<p class="warning">This is a local experimental result for <b>{source_name}</b>. Good reconstruction does not prove accurate separation. Nothing on this page uploads audio or feedback.</p>
<section><h2>1. Source reference</h2><p>Remember the complete song and its balance.</p><audio controls preload="metadata" src="../SOURCE/source-reference.wav"></audio></section>
<section><h2>2. Broad vocals</h2><p>Listen for missing vocal phrases, accompaniment bleed, metallic texture and join changes.</p><audio controls preload="metadata" src="../STEMS/vocals.wav"></audio></section>
<section><h2>3. Broad instrumental</h2><p>Listen for remaining vocals, holes where vocals were removed, and whether the backing remains musically useful.</p><audio controls preload="metadata" src="../STEMS/instrumental.wav"></audio></section>
<section><h2>4. Reconstruction check</h2><p>This is the persisted vocals plus instrumental. It should closely resemble the level-managed source reference.</p><audio controls preload="metadata" src="../AUDIO/reconstruction-check.wav"></audio></section>
<section><h2>Record a private local review</h2>
<label><input id="heard" type="checkbox"> I heard all four tracks</label>
<label>Overall usefulness <select id="quality"><option value="">Choose…</option><option>good</option><option>good_enough</option><option>poor</option><option>cannot_tell</option></select></label>
<label>Vocals useful? <select id="vocals"><option value="">Choose…</option><option>yes</option><option>partly</option><option>no</option><option>cannot_tell</option></select></label>
<label>Instrumental useful? <select id="instrumental"><option value="">Choose…</option><option>yes</option><option>partly</option><option>no</option><option>cannot_tell</option></select></label>
<label>What did you hear?<textarea id="notes" placeholder="Bleed, missing sound, joins, artefacts, musical usefulness…"></textarea></label>
<button id="export">Export private review JSON</button><a class="button" href="{feedback}" target="_blank" rel="noreferrer">Share optional text-only feedback ↗</a>
<p class="muted">Review JSON stays in your Downloads folder unless you deliberately share it. Do not attach private audio to a public issue.</p></section>
<script>
document.getElementById('export').addEventListener('click',()=>{{
 const value={{schema:'sunofriend.experimental-separation-review.v1',separation_report_sha256:'{report_hash}',heard_all_tracks:document.getElementById('heard').checked,overall_usefulness:document.getElementById('quality').value,vocals_useful:document.getElementById('vocals').value,instrumental_useful:document.getElementById('instrumental').value,notes:document.getElementById('notes').value,exported_at:new Date().toISOString(),audio_included:false}};
 const blob=new Blob([JSON.stringify(value,null,2)+'\\n'],{{type:'application/json'}}); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='sunofriend-separation-review.json'; a.click(); setTimeout(()=>URL.revokeObjectURL(a.href),1000);
}});
</script></main></body></html>"""


def _runtime_check(path: Path) -> dict[str, Any]:
    if not path.is_file() or not os.access(path, os.X_OK):
        return {"ready": False, "reason": "runtime Python is missing"}
    try:
        completed = subprocess.run(
            [str(path), "-c", "import sys; print('.'.join(map(str,sys.version_info[:3])))"],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            env={**os.environ, "PYTHONNOUSERSITE": "1"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ready": False, "reason": type(exc).__name__}
    version = completed.stdout.strip()
    ready = completed.returncode == 0 and version.startswith(("3.12.", "3.13."))
    return {"ready": ready, "version": version, "returncode": completed.returncode}


def _require_verified_checkpoint(path: Path) -> Mapping[str, Any]:
    value = _inspect_local_checkpoint(path)
    if not value["cryptographic_identity_verified"]:
        raise ValueError("checkpoint identity differs")
    return value


def _require_verified_companions(path: Path) -> Mapping[str, Any]:
    value = _inspect_companion_files(path)
    if not value["all_cryptographic_identities_verified"]:
        raise ValueError("companion identities differ")
    return value


def _safe_check(operation: Callable[[], Mapping[str, Any]]) -> dict[str, Any]:
    try:
        value = operation()
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        return {"ready": False, "reason": str(exc)}
    return {"ready": True, "verified": True, "status": value.get("status")}


def _run_command(
    command: Sequence[str],
    *,
    timeout: float,
    label: str,
    env: Mapping[str, str] | None = None,
) -> None:
    completed = subprocess.run(
        list(command),
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        env=dict(env) if env is not None else None,
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(
            f"{label} failed with exit code {completed.returncode}: "
            f"{detail[:2000] or 'no diagnostic output'}"
        )


def _nearest_existing_parent(path: Path) -> Path:
    current = path
    while not current.exists():
        if current.parent == current:
            raise FileNotFoundError(f"no existing parent for {path}")
        current = current.parent
    return current


def _document_sha256(document: Mapping[str, Any]) -> str:
    value = dict(document)
    value.pop("document_sha256", None)
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sunofriend-separate",
        description="Experimental local broad vocal/instrumental separation.",
    )
    parser.add_argument("--runtime-python")
    parser.add_argument("--model-root")
    subparsers = parser.add_subparsers(dest="command", required=True)
    doctor = subparsers.add_parser("doctor", help="check setup without loading a model")
    doctor.add_argument("--json", action="store_true")
    separate = subparsers.add_parser("separate", help="plan or run local separation")
    separate.add_argument("source")
    separate.add_argument("--out", required=True)
    separate.add_argument(
        "--rights-category",
        required=True,
        choices=sorted(RIGHTS_CATEGORIES - {"unknown", "declined_to_state"}),
    )
    separate.add_argument("--device", choices=("gpu", "cpu"), default="gpu")
    separate.add_argument("--ffmpeg", default="ffmpeg")
    separate.add_argument("--ffprobe", default="ffprobe")
    separate.add_argument("--execute", action="store_true")
    separate.add_argument("--confirm-rights", action="store_true")
    separate.add_argument("--open-review", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    profile = resolve_profile(
        runtime_python=args.runtime_python,
        model_root=args.model_root,
    )
    if args.command == "doctor":
        result = separation_doctor(profile)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Experimental separation: {result['status']}")
            for name, check in result["checks"].items():
                state = "ready" if check.get("ready") else "needs attention"
                print(f"- {name}: {state}")
            if not result["ready"]:
                print(f"Next: {result['setup_command']}")
        return 0 if result["ready"] else 2
    try:
        plan = plan_separation(
            args.source,
            args.out,
            rights_category=args.rights_category,
            device=args.device,
            ffmpeg=args.ffmpeg,
            ffprobe=args.ffprobe,
            profile=profile,
        )
        if not args.execute:
            print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
            print("\nPlan only. Repeat with --execute --confirm-rights to process locally.")
            return 0
        print(
            "Running the local experimental separator. The model is loaded offline; "
            "a full song can take several minutes."
        )
        result = execute_separation(plan, confirm_rights=args.confirm_rights)
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        print(f"sunofriend-separate: {exc}", file=sys.stderr)
        return 2
    print(f"Complete: {result['root']}")
    print(f"Listen first: {result['review_html']}")
    print("Result is experimental and unreviewed; no audio was uploaded.")
    if args.open_review:
        webbrowser.open(Path(result["review_html"]).as_uri())
    return 0


__all__ = [
    "PLAN_SCHEMA",
    "PROFILE_NAME",
    "SCHEMA",
    "SeparationPlan",
    "SeparationProfile",
    "build_parser",
    "execute_separation",
    "main",
    "plan_separation",
    "resolve_profile",
    "separation_doctor",
]


if __name__ == "__main__":
    raise SystemExit(main())
