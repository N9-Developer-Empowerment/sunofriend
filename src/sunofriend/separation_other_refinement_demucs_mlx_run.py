"""Atomic coordinator for the installed six-source Studio challenger."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import uuid
from typing import Any, Mapping

from .audio_formats import file_sha256
from .separation_other_refinement import (
    build_other_refinement_plan,
    build_other_refinement_result,
    validate_other_refinement_plan,
    validate_other_refinement_result,
)
from .separation_other_refinement_demucs_mlx_candidate import MODEL_SOURCE_ORDER
from .separation_profiles import (
    OTHER_REFINEMENT_DEMUCS_MLX_PROFILE_ID,
    SCNET_RELEASE_PROFILE_ID,
    separation_profile,
)


WORKER_RESULT_NAME = "TECHNICAL/worker-result.json"
PLAN_NAME = "TECHNICAL/other-refinement-plan.json"
RESULT_NAME = "TECHNICAL/other-refinement-result.json"


def plan_installed_other_refinement(
    parent_root: str | Path,
    *,
    target_id: str,
    output: str | Path,
) -> dict[str, Any]:
    root = Path(parent_root).expanduser().absolute()
    destination = Path(output).expanduser().absolute()
    report_path = root / "TECHNICAL/separation-report.json"
    other_path = root / "STEMS/other.wav"
    if not root.is_dir() or root.is_symlink():
        raise ValueError("core-four parent root must be a real directory")
    if not report_path.is_file() or report_path.is_symlink():
        raise ValueError("core-four parent separation report is missing")
    if not other_path.is_file() or other_path.is_symlink():
        raise ValueError("core-four grouped-other stem is missing")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("document_sha256") != _document_sha256(report):
        raise ValueError("core-four parent report seal differs")
    separator = report.get("separator")
    rights = report.get("rights")
    if not isinstance(separator, Mapping) or not isinstance(rights, Mapping):
        raise ValueError("core-four parent report contract differs")
    if (
        separator.get("scope_id") != "core-four-stems-v1"
        or separator.get("profile_id") != SCNET_RELEASE_PROFILE_ID
        or separator.get("profile_status") != "public_opt_in"
        or rights.get("confirmed_before_execution") is not True
    ):
        raise ValueError("refinement requires an authorised verified SCNet core-four parent")
    worker = separator.get("worker")
    outputs = worker.get("outputs") if isinstance(worker, Mapping) else None
    parent_claim = outputs.get("other") if isinstance(outputs, Mapping) else None
    if not isinstance(parent_claim, Mapping):
        raise ValueError("core-four grouped-other worker claim is missing")
    parent_sha256 = file_sha256(other_path)
    if (
        parent_claim.get("sha256") != parent_sha256
        or parent_claim.get("bytes") != other_path.stat().st_size
    ):
        raise ValueError("core-four grouped-other artifact changed")
    frames = parent_claim.get("frames")
    if type(frames) is not int or frames <= 0:
        raise ValueError("core-four grouped-other frame count differs")
    geometry = {
        "sample_rate": parent_claim.get("sample_rate"),
        "channels": parent_claim.get("channels"),
        "frames": frames,
        "duration_seconds": frames / 44_100,
        "sample_width_bytes": parent_claim.get("sample_width_bytes"),
    }
    report_sha256 = file_sha256(report_path)
    parent_node_id = "node:" + hashlib.sha256(
        ("core-four-other-v1\0" + report_sha256 + "\0" + parent_sha256).encode("ascii")
    ).hexdigest()
    contract = build_other_refinement_plan(
        parent_profile_id=SCNET_RELEASE_PROFILE_ID,
        parent_report_sha256=report_sha256,
        parent_node_id=parent_node_id,
        parent_audio_sha256=parent_sha256,
        parent_geometry=geometry,
        target_id=target_id,
    )
    return {
        "schema": "sunofriend.other-refinement-installed-run-plan.v1",
        "status": "ready_plan_only_no_effects",
        "parent_root": str(root),
        "parent_audio": str(other_path),
        "parent_report": str(report_path),
        "output": str(destination),
        "target_id": target_id,
        "profile_id": OTHER_REFINEMENT_DEMUCS_MLX_PROFILE_ID,
        "rights_category": rights.get("category"),
        "contract": contract,
        "effects": {
            "model_loaded": False,
            "inference_run": False,
            "audio_created": False,
            "source_graph_mutated": False,
            "midi_created": False,
        },
    }


def execute_installed_other_refinement(
    plan: Mapping[str, Any],
    *,
    confirm_rights: bool,
    model_root: str | Path | None = None,
    runtime_python: str | Path | None = None,
) -> dict[str, Any]:
    value = dict(plan)
    if value.get("schema") != "sunofriend.other-refinement-installed-run-plan.v1":
        raise ValueError("unsupported installed refinement plan")
    if confirm_rights is not True:
        raise PermissionError("refinement execution requires --confirm-rights")
    contract = validate_other_refinement_plan(value.get("contract", {}))
    destination = Path(str(value["output"])).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"refinement output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(f".{destination.name}.building-{uuid.uuid4().hex}")
    staging.mkdir(mode=0o700)
    failed = destination.with_name(f"{destination.name}.failed-{uuid.uuid4().hex[:8]}")

    spec = separation_profile(OTHER_REFINEMENT_DEMUCS_MLX_PROFILE_ID)
    profile_root = Path(
        model_root
        or Path.home()
        / ".local/share/sunofriend/separation"
        / OTHER_REFINEMENT_DEMUCS_MLX_PROFILE_ID
    ).expanduser().absolute()
    python = Path(runtime_python or profile_root / "runtime/bin/python").expanduser().absolute()
    repository_root = Path(__file__).resolve().parents[2]
    worker_path = repository_root / spec.worker_script
    raw_result = staging / "worker-result.json"
    command = [
        "/usr/bin/sandbox-exec",
        "-p",
        "(version 1)(deny network*)(allow default)",
        str(python),
        "-B",
        str(worker_path),
        "--source",
        str(value["parent_audio"]),
        "--destination",
        str(staging),
        "--result",
        str(raw_result),
        "--model-root",
        str(profile_root / "model"),
        "--target",
        str(value["target_id"]),
        "--network-denial-enforced",
    ]
    environment = {
        **os.environ,
        "PYTHONPATH": str(repository_root / "src"),
        "PYTHONNOUSERSITE": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "NO_PROXY": "*",
        "no_proxy": "*",
        "PIP_NO_INDEX": "1",
    }
    duration = float(contract["parent"]["geometry"]["duration_seconds"])
    timeout = min(900.0, max(10.0, duration * 2.0))
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            env=environment,
        )
        if completed.returncode:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(
                f"offline refinement worker failed ({completed.returncode}): "
                f"{detail[:3000] or 'no diagnostic output'}"
            )
        worker = json.loads(raw_result.read_text(encoding="utf-8"))
        _validate_worker(worker, contract=contract, spec=spec, timeout=timeout)

        technical = staging / "TECHNICAL"
        technical.mkdir()
        shutil.move(str(raw_result), technical / "worker-result.json")
        _write_json(technical / "other-refinement-plan.json", contract)
        execution = {
            "kind": "candidate_backend",
            "profile_id": spec.profile_id,
            "backend_id": "demucs-mlx-htdemucs-6s-local-v1",
            "runtime_identity_sha256": _runtime_identity_sha256(worker),
            "model_identity_sha256": _model_identity_sha256(worker),
            "network_used": False,
            "model_executed": True,
            "installed_or_downloaded_during_contract_run": False,
        }
        result = build_other_refinement_result(
            contract,
            root=staging,
            parent_relative_path="PARENT/other.wav",
            target_relative_path=(
                "STEMS/guitar.wav" if value["target_id"] == "guitar" else "STEMS/keys.wav"
            ),
            residual_relative_path="STEMS/other-residual.wav",
            execution=execution,
        )
        _write_json(technical / "other-refinement-result.json", result)
        review = staging / "REVIEW"
        review.mkdir()
        (review / "other_refinement_review.html").write_text(
            _render_review(result), encoding="utf-8"
        )
        (staging / "START-HERE.txt").write_text(
            "Listen to PARENT/other.wav, the requested target and "
            "STEMS/other-residual.wav. Choose either the parent or both children "
            "later; Sunofriend selected and activated neither.\n",
            encoding="utf-8",
        )
        os.replace(staging, destination)
    except BaseException:
        if staging.exists():
            os.replace(staging, failed)
        raise
    validate_other_refinement_result(
        result,
        plan=contract,
        root=destination,
    )
    return {
        "status": result["status"],
        "root": str(destination),
        "target": str(destination / result["outputs"]["target"]["relative_path"]),
        "residual": str(destination / "STEMS/other-residual.wav"),
        "review_html": str(destination / "REVIEW/other_refinement_review.html"),
        "result": str(destination / RESULT_NAME),
        "worker": str(destination / WORKER_RESULT_NAME),
        "additive_accounting": result["additive_accounting"],
        "activation": {
            "source_graph_mutated": False,
            "midi_created": False,
            "candidate_selected": False,
        },
    }


def _validate_worker(
    worker: Mapping[str, Any], *, contract: Mapping[str, Any], spec: Any, timeout: float
) -> None:
    target_id = contract["request"]["target_id"]
    model = worker.get("model")
    runtime = worker.get("runtime")
    resources = worker.get("resources")
    outputs = worker.get("outputs")
    accounting = worker.get("additive_accounting")
    if (
        worker.get("schema") != "sunofriend.other-refinement-demucs-mlx-worker.v1"
        or worker.get("status") != "complete_unreviewed_no_activation"
        or worker.get("profile_id") != spec.profile_id
        or worker.get("target_id") != target_id
        or worker.get("roles") != list(MODEL_SOURCE_ORDER)
        or worker.get("inference") != dict(spec.inference_settings)
        or worker.get("sample_rate") != 44_100
        or worker.get("channels") != 2
        or worker.get("frames") != contract["parent"]["geometry"]["frames"]
        or not isinstance(model, Mapping)
        or model.get("weights", {}).get("sha256") != spec.artifact("weights").sha256
        or model.get("config", {}).get("sha256") != spec.artifact("config").sha256
        or model.get("source_order") != list(MODEL_SOURCE_ORDER)
        or model.get("source_segment_value") != "39/5"
        or model.get("normalized_segment_seconds") != 7.8
        or model.get("normalization_in_memory_only") is not True
        or model.get("source_artifact_unchanged") is not True
        or model.get("auto_convert") is not False
        or model.get("named_or_network_model_resolution") is not False
        or not isinstance(runtime, Mapping)
        or runtime.get("packages") != dict(spec.packages())
        or runtime.get("network_denial_enforced") is not True
        or runtime.get("network_used") is not False
        or runtime.get("pytorch_present") is not False
        or runtime.get("source_revision") != spec.runtime_source_revision
        or not isinstance(resources, Mapping)
        or not isinstance(outputs, Mapping)
        or set(outputs) != {"parent", "target", "residual"}
        or not isinstance(accounting, Mapping)
        or accounting.get("passed") is not True
        or accounting.get("maximum_absolute_error_lsb", 3) > 2
        or worker.get("activation")
        != {"candidate_selected": False, "midi_created": False, "source_graph_mutated": False}
    ):
        raise RuntimeError("refinement worker objective evidence contract differs")
    peak_memory = resources.get("peak_unified_memory_bytes")
    elapsed = worker.get("elapsed_seconds")
    if (
        type(peak_memory) is not int
        or not 0 <= peak_memory <= 12 * 1024**3
        or type(elapsed) not in (int, float)
        or not math.isfinite(float(elapsed))
        or float(elapsed) > timeout
    ):
        raise RuntimeError("refinement worker exceeded its resource ceiling")
    for output in outputs.values():
        if (
            output.get("frames") != contract["parent"]["geometry"]["frames"]
            or output.get("sample_rate") != 44_100
            or output.get("channels") != 2
            or output.get("sample_width_bytes") != 3
        ):
            raise RuntimeError("refinement worker output clock contract differs")


def _render_review(result: Mapping[str, Any]) -> str:
    target = result["outputs"]["target"]
    target_path = "../" + target["relative_path"]
    return f"""<!doctype html>
<html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\">
<title>Sunofriend other refinement review</title>
<style>body{{font:18px system-ui;max-width:900px;margin:3rem auto;padding:0 1rem;background:#071321;color:#f4f7fb}}section{{border:1px solid #31506a;border-radius:18px;padding:1.25rem;margin:1rem 0}}audio{{width:100%}}button{{padding:.8rem 1.1rem}}</style>
<h1>Listen before choosing</h1><p>This Studio challenger selected and activated nothing. Compare the grouped parent with the requested target and exact residual. Reconstruction proves accounting, not isolation quality.</p>
<section><h2>Grouped other parent</h2><audio controls preload=\"metadata\" src=\"../PARENT/other.wav\"></audio></section>
<section><h2>{target['declared_role'].title()} target</h2><audio controls preload=\"metadata\" src=\"{target_path}\"></audio></section>
<section><h2>Grouped other residual</h2><audio controls preload=\"metadata\" src=\"../STEMS/other-residual.wav\"></audio></section>
<label><input id=\"listened\" type=\"checkbox\"> I listened to the parent, target and residual.</label>
<p><label>Usefulness <select id=\"usefulness\"><option>cannot_tell</option><option>useful</option><option>mixed</option><option>not_useful</option></select></label></p>
<p><label>Bleed <select id=\"bleed\"><option>cannot_tell</option><option>none</option><option>some</option><option>severe</option></select></label></p>
<p><label>Missing target content <select id=\"missing\"><option>cannot_tell</option><option>none</option><option>some</option><option>severe</option></select></label></p>
<p><label>Artefacts <select id=\"artefacts\"><option>cannot_tell</option><option>none</option><option>some</option><option>severe</option></select></label></p>
<p><label>Timing or join problems <select id=\"timing\"><option>cannot_tell</option><option>none</option><option>some</option><option>severe</option></select></label></p>
<p><label>Did downstream MIDI improve? <select id=\"midi\"><option>not_tested</option><option>cannot_tell</option><option>improved</option><option>no_change</option><option>worse</option></select></label></p>
<p><label>Notes<br><textarea id=\"notes\" rows=\"5\" style=\"width:100%\"></textarea></label></p>
<button id=\"download\">Download listening JSON</button> <button id=\"copy\">Copy text-only feedback</button><p id=\"message\"></p>
<p>No audio, filenames, review JSON or telemetry is uploaded automatically. Paste copied text only if you choose to use the <a href=\"https://github.com/N9-Developer-Empowerment/sunofriend/issues/new?template=daw-ai-compatibility.yml\">compatibility form</a>.</p>
<script>const field=id=>document.getElementById(id).value;const data=()=>({{schema:'sunofriend.other-refinement-listening.v1',result_sha256:'{result['document_sha256']}',target_id:'{result['request']['target_id']}',listened:document.getElementById('listened').checked,usefulness:field('usefulness'),bleed:field('bleed'),missing_content:field('missing'),artefacts:field('artefacts'),timing_or_join_problems:field('timing'),downstream_midi:field('midi'),notes:field('notes'),activation_choice:'none'}});document.getElementById('download').onclick=()=>{{const blob=new Blob([JSON.stringify(data(),null,2)+'\\n'],{{type:'application/json'}});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='sunofriend-other-refinement-listening.json';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);document.getElementById('message').textContent='Download requested. If your browser blocks it, use its download menu.';}};document.getElementById('copy').onclick=async()=>{{const d=data();const text=`Sunofriend other refinement (${{d.target_id}}): usefulness=${{d.usefulness}}; bleed=${{d.bleed}}; missing=${{d.missing_content}}; artefacts=${{d.artefacts}}; timing/joins=${{d.timing_or_join_problems}}; downstream MIDI=${{d.downstream_midi}}; notes=${{d.notes||'none'}}`;await navigator.clipboard.writeText(text);document.getElementById('message').textContent='Text-only feedback copied. No audio or private metadata was included.';}};</script></html>"""


def _runtime_identity_sha256(worker: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(worker["runtime"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _model_identity_sha256(worker: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(worker["model"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _document_sha256(document: Mapping[str, Any]) -> str:
    value = dict(document)
    value.pop("document_sha256", None)
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


__all__ = ["execute_installed_other_refinement", "plan_installed_other_refinement"]
