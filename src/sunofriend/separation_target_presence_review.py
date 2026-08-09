"""Prepare and serve a source-only fine-stem target-presence review."""

from __future__ import annotations

import copy
import hashlib
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import re
import tempfile
from typing import Any

import numpy as np

from .separation_target_presence_plan import (
    CORPUS_MANIFEST_SHA256,
    TARGET_PRESENCE_PACKAGE_NAME,
    build_target_presence_plan,
    validate_target_presence_plan,
)
from .separation_target_presence_addition_plan import (
    build_target_presence_addition_plan,
    validate_target_presence_addition_plan,
)
from .separation_target_presence_replacement_plan import (
    TARGET_PRESENCE_REPLACEMENT_PACKAGE_NAME,
    build_target_presence_replacement_plan,
    validate_target_presence_replacement_plan,
)


PRESENCE_MANIFEST_SCHEMA = "sunofriend.fine-stem-target-presence-package.v1"
PRESENCE_RESULT_SCHEMA = "sunofriend.fine-stem-target-presence-result.v1"
SAMPLE_RATE_HZ = 44_100
WINDOW_SECONDS = 15
WINDOW_FRAMES = SAMPLE_RATE_HZ * WINDOW_SECONDS
_DECISIONS = frozenset({"present", "absent", "cannot_tell"})


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def presence_document_sha256(value: dict[str, Any]) -> str:
    payload = {
        key: item
        for key, item in value.items()
        if key not in {"document_sha256", "saved_at"}
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def select_consensus_window(
    energy_by_hint: list[np.ndarray],
    *,
    source_duration_seconds: float,
    duration_seconds: int = WINDOW_SECONDS,
    margin_seconds: int = 5,
) -> tuple[int, float]:
    """Choose a fixed window from pre-model provider-hint energy only."""

    if not energy_by_hint:
        raise ValueError("target-presence selection needs at least one hint")
    limit = min(
        math.floor(source_duration_seconds), *(len(value) for value in energy_by_hint)
    )
    last_start = limit - margin_seconds - duration_seconds
    if last_start < margin_seconds:
        raise ValueError("target-presence source is too short")
    normalized: list[np.ndarray] = []
    for value in energy_by_hint:
        vector = np.asarray(value[:limit], dtype=np.float64)
        if vector.ndim != 1 or not np.isfinite(vector).all() or (vector < 0).any():
            raise ValueError("target-presence energy vector differs")
        scale = float(np.quantile(vector, 0.95))
        normalized.append(vector / scale if scale > 1e-12 else np.zeros_like(vector))
    best: tuple[float, int] | None = None
    for start in range(margin_seconds, last_start + 1):
        per_hint = []
        for vector in normalized:
            window = vector[start : start + duration_seconds]
            per_hint.append(float(0.6 * np.median(window) + 0.4 * np.mean(window)))
        score = float(np.median(per_hint))
        candidate = (score, -start)
        if best is None or candidate > best:
            best = candidate
    if best is None:
        raise RuntimeError("target-presence selection produced no window")
    return -best[1], best[0]


def _one_second_rms(path: Path) -> tuple[np.ndarray, float]:
    import soundfile as sf

    info = sf.info(path)
    if info.channels not in {1, 2} or info.frames <= 0 or info.samplerate <= 0:
        raise RuntimeError("target-presence hint geometry differs")
    values: list[float] = []
    with sf.SoundFile(path) as source:
        while True:
            block = source.read(info.samplerate, dtype="float32", always_2d=True)
            if not len(block):
                break
            values.append(float(np.sqrt(np.mean(np.square(block, dtype=np.float64)))))
    return np.asarray(values, dtype=np.float64), info.frames / info.samplerate


def _read_window(path: Path, *, start_seconds: int) -> np.ndarray:
    import soundfile as sf
    from scipy.signal import resample_poly

    info = sf.info(path)
    if info.channels not in {1, 2}:
        raise RuntimeError("target-presence audio must be mono or stereo")
    source_frames = info.samplerate * WINDOW_SECONDS
    start_frame = info.samplerate * start_seconds
    if start_frame < 0 or start_frame + source_frames > info.frames:
        raise RuntimeError("target-presence window exceeds its source")
    with sf.SoundFile(path) as source:
        source.seek(start_frame)
        value = source.read(source_frames, dtype="float32", always_2d=True)
    if value.shape != (source_frames, info.channels) or not np.isfinite(value).all():
        raise RuntimeError("target-presence decoded audio differs")
    if info.channels == 1:
        value = np.repeat(value, 2, axis=1)
    if info.samplerate != SAMPLE_RATE_HZ:
        divisor = math.gcd(info.samplerate, SAMPLE_RATE_HZ)
        value = resample_poly(
            value,
            SAMPLE_RATE_HZ // divisor,
            info.samplerate // divisor,
            axis=0,
        ).astype(np.float32, copy=False)
    if value.shape[0] < WINDOW_FRAMES:
        value = np.pad(value, ((0, WINDOW_FRAMES - value.shape[0]), (0, 0)))
    value = np.ascontiguousarray(value[:WINDOW_FRAMES], dtype=np.float32)
    if value.shape != (WINDOW_FRAMES, 2) or not np.isfinite(value).all():
        raise RuntimeError("target-presence canonical audio differs")
    return value


def _write_pcm24(path: Path, value: np.ndarray) -> None:
    import soundfile as sf

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    sf.write(path, value, SAMPLE_RATE_HZ, subtype="PCM_24", format="WAV")
    path.chmod(0o600)


def _audio_artifact(path: Path, *, root: Path) -> dict[str, Any]:
    import soundfile as sf

    info = sf.info(path)
    if (
        info.samplerate != SAMPLE_RATE_HZ
        or info.channels != 2
        or info.frames != WINDOW_FRAMES
        or info.subtype != "PCM_24"
    ):
        raise RuntimeError("target-presence persisted audio differs")
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "channels": 2,
        "frames": WINDOW_FRAMES,
        "subtype": "PCM_24",
    }


def _input_receipt(path: Path, *, root: Path) -> dict[str, Any]:
    import soundfile as sf

    info = sf.info(path)
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
        "sample_rate_hz": info.samplerate,
        "channels": info.channels,
        "frames": info.frames,
    }


def _review_seed(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": PRESENCE_RESULT_SCHEMA,
        "document_sha256": "",
        "status": "presence_review_incomplete_no_model_inference",
        "manifest_sha256": manifest["document_sha256"],
        "cases": [
            {
                "case_id": case["case_id"],
                "track_id": case["track_id"],
                "target_id": case["target_id"],
                "window_seconds": case["window_seconds"],
                "played_items": [],
                "listened": False,
                "decision": "",
                "notes": "",
            }
            for case in manifest["cases"]
        ],
        "boundaries": {
            "provider_estimates_are_truth": False,
            "model_inference_started": False,
            "source_selected": False,
            "midi_created": False,
            "audio_uploaded": False,
            "telemetry": False,
        },
    }


def validate_presence_result(
    value: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, Any]:
    seed = _review_seed(manifest)
    if any(
        value.get(key) != seed[key]
        for key in ("schema", "manifest_sha256", "boundaries")
    ):
        raise ValueError("target-presence result binding differs")
    cases = value.get("cases")
    if not isinstance(cases, list) or len(cases) != len(seed["cases"]):
        raise ValueError("target-presence result cases differ")
    expected = {case["case_id"]: case for case in seed["cases"]}
    manifest_cases = {case["case_id"]: case for case in manifest["cases"]}
    seen: set[str] = set()
    complete = True
    for case in cases:
        if not isinstance(case, dict) or case.get("case_id") not in expected:
            raise ValueError("target-presence result case identity differs")
        expected_case = expected[case["case_id"]]
        if case["case_id"] in seen or any(
            case.get(key) != expected_case[key]
            for key in ("track_id", "target_id", "window_seconds")
        ):
            raise ValueError("target-presence result case binding differs")
        seen.add(case["case_id"])
        if not isinstance(case.get("listened"), bool):
            raise ValueError("target-presence listened value differs")
        hint_artifacts = (
            manifest_cases[case["case_id"]].get("artifacts", {}).get("hints", [])
        )
        if not isinstance(hint_artifacts, list):
            raise ValueError("target-presence hint artifacts differ")
        allowed_playback = [
            "source",
            *(f"hint-{index}" for index, _ in enumerate(hint_artifacts, start=1)),
        ]
        played_items = case.get(
            "played_items", allowed_playback if case["listened"] else []
        )
        if (
            not isinstance(played_items, list)
            or any(not isinstance(item, str) for item in played_items)
            or len(played_items) != len(set(played_items))
            or not set(played_items).issubset(allowed_playback)
            or case["listened"] != (set(played_items) == set(allowed_playback))
        ):
            raise ValueError("target-presence playback evidence differs")
        case["played_items"] = played_items
        decision = case.get("decision")
        if decision not in _DECISIONS | {""} or not isinstance(case.get("notes"), str):
            raise ValueError("target-presence decision differs")
        complete = complete and case["listened"] and decision in _DECISIONS
    expected_status = (
        "presence_review_complete_no_model_inference"
        if complete
        else "presence_review_incomplete_no_model_inference"
    )
    if value.get("status") != expected_status:
        raise ValueError("target-presence result status differs")
    document = dict(value)
    expected_hash = presence_document_sha256(document)
    supplied_hash = document.get("document_sha256")
    if supplied_hash not in {"", expected_hash}:
        raise ValueError("target-presence result hash differs")
    document["document_sha256"] = expected_hash
    return document


def attest_completed_presence_listening(
    value: dict[str, Any],
    manifest: dict[str, Any],
    *,
    recorded_at: str,
) -> dict[str, Any]:
    """Bind an explicit user completion statement without changing decisions."""

    document = validate_presence_result(copy.deepcopy(value), manifest)
    if not isinstance(recorded_at, str) or not recorded_at.strip():
        raise ValueError("target-presence listening attestation time differs")
    manifest_cases = {case["case_id"]: case for case in manifest["cases"]}
    if any(case.get("decision") not in _DECISIONS for case in document["cases"]):
        raise ValueError("target-presence decision is missing before attestation")
    for case in document["cases"]:
        hints = manifest_cases[case["case_id"]]["artifacts"].get("hints", [])
        case["played_items"] = [
            "source", *(f"hint-{index}" for index, _ in enumerate(hints, start=1))
        ]
        case["listened"] = True
    document["status"] = "presence_review_complete_no_model_inference"
    document["listen_attestation"] = {
        "all_samples_listened": True,
        "recorded_at": recorded_at,
        "source": "explicit_user_review_completion_statement",
        "ui_limitation_observed": (
            "review completed before per-player state was fully retained; "
            "decisions were re-entered without replay"
        ),
    }
    document["document_sha256"] = ""
    return validate_presence_result(document, manifest)


def render_presence_review(manifest: dict[str, Any]) -> str:
    seed = _review_seed(manifest)
    cards: list[str] = []
    target_specs = manifest["targets"]
    for index, case in enumerate(manifest["cases"]):
        target = target_specs[case["target_id"]]
        hints = "".join(
            f'<label>Provider attention hint {hint_index + 1}<audio controls preload="metadata" '
            f'data-player-id="hint-{hint_index + 1}" '
            f'src="/{html.escape(artifact["relative_path"])}"></audio></label>'
            for hint_index, artifact in enumerate(case["artifacts"]["hints"])
        )
        cards.append(
            f"""
<section class="case" data-index="{index}">
  <p class="eyebrow">{html.escape(target['label'])} · source-presence gate</p>
  <h2>{html.escape(case['title'])}</h2>
  <p>Frozen window: {case['window_seconds'][0]}–{case['window_seconds'][1]} seconds.</p>
  <p><strong>Listen for:</strong> {html.escape(target['definition'])}.</p>
  <div class="source"><label>Original source mix<audio controls preload="metadata" data-player-id="source" src="/{html.escape(case['artifacts']['source']['relative_path'])}"></audio></label></div>
  <details><summary>Provider attention hints — estimates, never truth</summary><div class="players">{hints}</div></details>
  <p class="playback" data-playback>Playback recorded automatically: 0 items played.</p>
  <fieldset><legend>Is the target audibly present in the original source window?</legend>
    <label><input type="radio" name="decision-{index}" value="present"> Present</label>
    <label><input type="radio" name="decision-{index}" value="absent"> Absent</label>
    <label><input type="radio" name="decision-{index}" value="cannot_tell"> Cannot tell</label>
  </fieldset>
  <label>Optional private note<textarea data-field="notes" rows="2"></textarea></label>
</section>"""
        )
    seed_json = json.dumps(seed, sort_keys=True).replace("</", "<\\/")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sunofriend target-presence review</title><style>
:root{{color-scheme:dark;background:#06101e;color:#f6f7fb;font:17px system-ui,sans-serif}}body{{max-width:1180px;margin:auto;padding:30px}}h1{{font-size:2.3rem}}.notice,.case{{background:#102033;border:1px solid #31516e;border-radius:18px;padding:22px;margin:20px 0}}.players{{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:14px}}label{{display:grid;gap:7px;margin:12px 0;font-weight:650}}audio,textarea{{width:100%}}audio{{height:54px}}textarea{{font:inherit;padding:10px}}button,a.button{{display:inline-block;font:inherit;font-weight:750;border:0;border-radius:999px;padding:14px 22px;margin:8px;background:#53d7e8;color:#06101e;text-decoration:none}}button.secondary,a.secondary{{background:#2a5576;color:white}}fieldset{{border:1px solid #31516e;border-radius:12px}}fieldset label{{display:block}}.eyebrow{{color:#53d7e8;font-weight:800;text-transform:uppercase;letter-spacing:.08em}}.playback{{color:#82e7b3;font-weight:700}}#fallback{{min-height:180px;font:13px ui-monospace,monospace}}#status{{min-height:1.5em;color:#82e7b3}}
</style></head><body><p>Sunofriend · local private preflight</p><h1>Confirm the instruments before testing the models</h1>
<div class="notice"><strong>No separator output exists in this page.</strong> Decide presence from the original source. Provider files only help direct attention and may be wrong. An absent or cannot-tell result excludes or replaces the song before inference; it is not a model failure.</div>
{''.join(cards)}
<section class="case"><h2>Save locally</h2><p>This writes only your decisions and notes beside the private review. It uploads nothing and starts no model.</p><button id="save">Save presence decisions locally</button><a class="button secondary" id="download" href="/download-presence">Download saved JSON backup</a><p id="status"></p><label>JSON fallback<textarea id="fallback" readonly></textarea></label></section>
<script id="seed" type="application/json">{seed_json}</script><script>
const seed=JSON.parse(document.getElementById('seed').textContent),cards=[...document.querySelectorAll('.case[data-index]')],storageKey=`sunofriend-presence-${{seed.manifest_sha256}}`;let base=structuredClone(seed);
let ready=false,saveTimer=null,saveRunning=false,saveQueued=false;
function playbackState(card){{const players=[...card.querySelectorAll('audio')],played=players.filter(player=>player.dataset.played==='true').map(player=>player.dataset.playerId);card.querySelector('[data-playback]').textContent=played.length===players.length?`Playback recorded automatically: all ${{players.length}} items played.`:`Playback recorded automatically: ${{played.length}} of ${{players.length}} items played.`;return{{played,complete:players.length>0&&played.length===players.length}};}}
function collect(){{const out=structuredClone(base);cards.forEach((card,i)=>{{const row=out.cases[i],decision=card.querySelector('input[type=radio]:checked'),playback=playbackState(card);row.played_items=playback.played;row.listened=playback.complete;row.decision=decision?decision.value:'';row.notes=card.querySelector('[data-field=notes]').value;}});out.status=out.cases.every(x=>x.listened&&x.decision)?'presence_review_complete_no_model_inference':'presence_review_incomplete_no_model_inference';out.document_sha256='';out.saved_at=new Date().toISOString();document.getElementById('fallback').value=JSON.stringify(out,null,2)+'\\n';try{{localStorage.setItem(storageKey,JSON.stringify(out));}}catch(error){{}}return out;}}
function hydrate(out){{if(!out||!Array.isArray(out.cases))return;base=structuredClone(out);out.cases.forEach((row,i)=>{{const card=cards[i];if(!card||card.dataset.index!=i)return;const players=[...card.querySelectorAll('audio')],played=new Set(row.listened?players.map(player=>player.dataset.playerId):(row.played_items||[]));players.forEach(player=>player.dataset.played=played.has(player.dataset.playerId)?'true':'false');const radio=card.querySelector(`input[value="${{row.decision}}"]`);if(radio)radio.checked=true;card.querySelector('[data-field=notes]').value=row.notes||'';}});collect();}}
async function saveNow(){{if(!ready)return;if(saveRunning){{saveQueued=true;return;}}saveRunning=true;const status=document.getElementById('status');status.textContent='Saving locally…';try{{const response=await fetch('/save-presence',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(collect())}});const value=await response.json();if(!response.ok)throw new Error(value.error||'save failed');base=structuredClone(value);status.textContent=value.status==='presence_review_complete_no_model_inference'?'Saved locally. All presence decisions are complete.':'Progress saved locally automatically; play every item and make every decision before model inference.';}}catch(error){{status.textContent=`Automatic save failed: ${{error.message}}. The same JSON remains below.`;}}finally{{saveRunning=false;if(saveQueued){{saveQueued=false;saveNow();}}}}}}
function scheduleSave(){{if(!ready)return;clearTimeout(saveTimer);saveTimer=setTimeout(saveNow,400);}}
cards.forEach(card=>card.querySelectorAll('audio').forEach(player=>player.addEventListener('play',()=>{{player.dataset.played='true';collect();scheduleSave();}})));
document.addEventListener('input',()=>{{collect();scheduleSave();}});collect();
let localValue=null;try{{localValue=JSON.parse(localStorage.getItem(storageKey));}}catch(error){{}}if(localValue)hydrate(localValue);
fetch('/saved-result',{{cache:'no-store'}}).then(r=>r.ok?r.json():null).then(value=>{{if(value)hydrate(value);}}).catch(()=>{{}}).finally(()=>{{ready=true;collect();scheduleSave();}});
document.getElementById('save').addEventListener('click',saveNow);
</script></body></html>"""


def prepare_presence_review(*, stem_root: Path, out: Path) -> dict[str, Any]:
    plan = validate_target_presence_plan(build_target_presence_plan())
    root = stem_root.resolve(strict=True)
    destination = out.resolve()
    if destination.name != TARGET_PRESENCE_PACKAGE_NAME or destination.exists():
        raise RuntimeError("fresh exact target-presence output is required")
    corpus = root / plan["corpus"]["manifest"]
    if file_sha256(corpus) != CORPUS_MANIFEST_SHA256:
        raise RuntimeError("authorised corpus manifest differs")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(tempfile.mkdtemp(prefix=".presence-staging-", dir=destination.parent))
    staging.chmod(0o700)
    cases: list[dict[str, Any]] = []
    inputs: dict[str, dict[str, Any]] = {}
    try:
        for track in plan["tracks"]:
            source = (root / track["source"]).resolve(strict=True)
            if root not in source.parents:
                raise RuntimeError("target-presence source escapes the corpus")
            inputs.setdefault(track["source"], _input_receipt(source, root=root))
            import soundfile as sf

            source_info = sf.info(source)
            source_duration = source_info.frames / source_info.samplerate
            for target_id, hint_names in track["hints"].items():
                hints = [(root / name).resolve(strict=True) for name in hint_names]
                if any(root not in path.parents for path in hints):
                    raise RuntimeError("target-presence hint escapes the corpus")
                energies: list[np.ndarray] = []
                for name, path in zip(hint_names, hints):
                    energy, _duration = _one_second_rms(path)
                    energies.append(energy)
                    inputs.setdefault(name, _input_receipt(path, root=root))
                start, score = select_consensus_window(
                    energies, source_duration_seconds=source_duration
                )
                case_id = f"{track['track_id']}--{target_id}"
                case_root = staging / "CASES" / case_id
                source_out = case_root / "source.wav"
                _write_pcm24(source_out, _read_window(source, start_seconds=start))
                hint_artifacts = []
                for index, path in enumerate(hints, start=1):
                    hint_out = case_root / f"provider-hint-{index}.wav"
                    _write_pcm24(hint_out, _read_window(path, start_seconds=start))
                    hint_artifacts.append(_audio_artifact(hint_out, root=staging))
                cases.append(
                    {
                        "case_id": case_id,
                        "track_id": track["track_id"],
                        "title": track["title"],
                        "target_id": target_id,
                        "window_seconds": [start, start + WINDOW_SECONDS],
                        "selection_score": score,
                        "selection_used_separator_output": False,
                        "provider_estimates_are_truth": False,
                        "source_input": inputs[track["source"]],
                        "hint_inputs": [inputs[name] for name in hint_names],
                        "artifacts": {
                            "source": _audio_artifact(source_out, root=staging),
                            "hints": hint_artifacts,
                        },
                    }
                )
        manifest: dict[str, Any] = {
            "schema": PRESENCE_MANIFEST_SCHEMA,
            "document_sha256": "",
            "status": "source_presence_pending_no_model_inference",
            "plan_sha256": plan["document_sha256"],
            "targets": plan["targets"],
            "cases": cases,
            "input_count": len(inputs),
            "effects": plan["effects"],
        }
        manifest["document_sha256"] = presence_document_sha256(manifest)
        technical = staging / "TECHNICAL"
        review = staging / "REVIEW"
        technical.mkdir(mode=0o700)
        review.mkdir(mode=0o700)
        (technical / "PRESENCE-MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        (technical / "PRESENCE-MANIFEST.json").chmod(0o600)
        (review / "presence.html").write_text(
            render_presence_review(manifest), encoding="utf-8"
        )
        (review / "presence.html").chmod(0o600)
        staging.rename(destination)
        return manifest
    except BaseException:
        failed = destination.with_name(destination.name + "-FAILED")
        if not failed.exists():
            staging.rename(failed)
        raise


def _prepare_frozen_presence_review(
    *, plan: dict[str, Any], stem_root: Path, out: Path
) -> dict[str, Any]:
    """Persist one exact frozen source-only plan for human presence review."""

    root = stem_root.resolve(strict=True)
    destination = out.resolve()
    if destination.name != plan["package_name"] or destination.exists():
        raise RuntimeError("fresh exact frozen-presence output is required")
    for manifest_name, evidence in plan.get("corpora", {}).items():
        manifest_path = (root / manifest_name).resolve(strict=True)
        if root not in manifest_path.parents:
            raise RuntimeError("presence corpus manifest escapes its root")
        if file_sha256(manifest_path) != evidence["manifest_sha256"]:
            raise RuntimeError("presence corpus manifest differs")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(tempfile.mkdtemp(prefix=".presence-frozen-staging-", dir=destination.parent))
    staging.chmod(0o700)
    cases: list[dict[str, Any]] = []
    inputs: dict[str, dict[str, Any]] = {}
    try:
        for case in plan["cases"]:
            source = (root / case["source"]).resolve(strict=True)
            hints = [(root / value).resolve(strict=True) for value in case["hints"]]
            if root not in source.parents or any(root not in path.parents for path in hints):
                raise RuntimeError("frozen presence input escapes its root")
            inputs.setdefault(case["source"], _input_receipt(source, root=root))
            for name, path in zip(case["hints"], hints):
                inputs.setdefault(name, _input_receipt(path, root=root))
            if case.get("source_sha256") not in {
                None,
                inputs[case["source"]]["sha256"],
            }:
                raise RuntimeError("frozen presence source hash differs")
            expected_hint_hashes = case.get("hint_sha256")
            if expected_hint_hashes is not None and expected_hint_hashes != [
                inputs[name]["sha256"] for name in case["hints"]
            ]:
                raise RuntimeError("frozen presence hint hash differs")
            start = int(case["window_seconds"][0])
            case_root = staging / "CASES" / case["case_id"]
            source_out = case_root / "source.wav"
            _write_pcm24(source_out, _read_window(source, start_seconds=start))
            hint_artifacts = []
            for index, path in enumerate(hints, start=1):
                hint_out = case_root / f"provider-hint-{index}.wav"
                _write_pcm24(hint_out, _read_window(path, start_seconds=start))
                hint_artifacts.append(_audio_artifact(hint_out, root=staging))
            packaged_case = {
                "case_id": case["case_id"],
                "track_id": case["track_id"],
                "title": case["title"],
                "target_id": case["target_id"],
                "window_seconds": case["window_seconds"],
                "selection_score": case["selection_score"],
                "selection_used_separator_output": False,
                "provider_estimates_are_truth": False,
                "rights_category": case["rights_category"],
                "source_input": inputs[case["source"]],
                "hint_inputs": [inputs[name] for name in case["hints"]],
                "artifacts": {
                    "source": _audio_artifact(source_out, root=staging),
                    "hints": hint_artifacts,
                },
            }
            for field in (
                "corpus_manifest",
                "public_notes_url",
                "public_notes_summary",
            ):
                if field in case:
                    packaged_case[field] = case[field]
            cases.append(packaged_case)
        manifest: dict[str, Any] = {
            "schema": PRESENCE_MANIFEST_SCHEMA,
            "document_sha256": "",
            "status": "source_presence_pending_no_model_inference",
            "plan_sha256": plan["document_sha256"],
            "targets": plan["targets"],
            "cases": cases,
            "input_count": len(inputs),
            "effects": plan["effects"],
        }
        for field in ("replaces_manifest_sha256", "prior_presence", "authority"):
            if field in plan:
                manifest[field] = plan[field]
        manifest["document_sha256"] = presence_document_sha256(manifest)
        technical = staging / "TECHNICAL"
        review = staging / "REVIEW"
        technical.mkdir(mode=0o700)
        review.mkdir(mode=0o700)
        (technical / "PRESENCE-PLAN.json").write_text(
            json.dumps(plan, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        (technical / "PRESENCE-MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        (review / "presence.html").write_text(
            render_presence_review(manifest), encoding="utf-8"
        )
        for path in (
            technical / "PRESENCE-PLAN.json",
            technical / "PRESENCE-MANIFEST.json",
            review / "presence.html",
        ):
            path.chmod(0o600)
        staging.rename(destination)
        return manifest
    except BaseException:
        failed = destination.with_name(destination.name + "-FAILED")
        if not failed.exists():
            staging.rename(failed)
        raise


def prepare_replacement_presence_review(
    *, stem_root: Path, out: Path
) -> dict[str, Any]:
    """Persist the exact source-only replacement cohort for human presence review."""

    plan = validate_target_presence_replacement_plan(
        build_target_presence_replacement_plan()
    )
    if plan["package_name"] != TARGET_PRESENCE_REPLACEMENT_PACKAGE_NAME:
        raise RuntimeError("replacement presence package identity differs")
    return _prepare_frozen_presence_review(plan=plan, stem_root=stem_root, out=out)


def prepare_addition_presence_review(
    *, source_root: Path, out: Path
) -> dict[str, Any]:
    """Persist the two source-only cases needed to complete the canary cohort."""

    plan = validate_target_presence_addition_plan(build_target_presence_addition_plan())
    return _prepare_frozen_presence_review(plan=plan, stem_root=source_root, out=out)


def load_presence_manifest(root: Path) -> dict[str, Any]:
    manifest = json.loads(
        (root / "TECHNICAL/PRESENCE-MANIFEST.json").read_text(encoding="utf-8")
    )
    if manifest.get("schema") != PRESENCE_MANIFEST_SCHEMA:
        raise ValueError("target-presence manifest schema differs")
    if manifest.get("document_sha256") != presence_document_sha256(manifest):
        raise ValueError("target-presence manifest hash differs")
    if manifest.get("status") != "source_presence_pending_no_model_inference":
        raise ValueError("target-presence manifest status differs")
    return manifest


def build_presence_review_server(
    root: Path, *, host: str = "127.0.0.1", port: int = 8768
) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("target-presence server must bind to localhost")
    package = root.resolve(strict=True)
    manifest = load_presence_manifest(package)
    # Render from the validated manifest so a repaired local server never serves a
    # stale review script embedded when the evidence package was first created.
    page = render_presence_review(manifest).encode("utf-8")
    result_path = package / "PRESENCE-RESULT.json"
    routes: dict[str, Path] = {}
    for case in manifest["cases"]:
        artifacts = [case["artifacts"]["source"], *case["artifacts"]["hints"]]
        for artifact in artifacts:
            path = (package / artifact["relative_path"]).resolve(strict=True)
            if (
                package not in path.parents
                or path.stat().st_size != artifact["bytes"]
                or file_sha256(path) != artifact["sha256"]
            ):
                raise ValueError("target-presence audio identity differs")
            routes["/" + artifact["relative_path"]] = path

    class Handler(BaseHTTPRequestHandler):
        server_version = "SunofriendTargetPresence/1"

        def do_GET(self) -> None:  # noqa: N802
            route = self.path.partition("?")[0]
            if route in {"/", "/REVIEW/presence.html"}:
                self._send(200, "text/html; charset=utf-8", page)
            elif route == "/healthz":
                self._send(200, "application/json", b'{"status":"ok"}\n')
            elif route == "/saved-result":
                if result_path.exists():
                    self._send(200, "application/json", result_path.read_bytes())
                else:
                    self.send_error(404)
            elif route == "/download-presence":
                if not result_path.exists():
                    self.send_error(404, "Save decisions first")
                    return
                body = result_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header(
                    "Content-Disposition",
                    'attachment; filename="fine-stem-target-presence.json"',
                )
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            elif route in routes:
                self._audio(routes[route])
            else:
                self.send_error(404)

        def do_HEAD(self) -> None:  # noqa: N802
            route = self.path.partition("?")[0]
            if route in routes:
                self._audio(routes[route], body=False)
            else:
                self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/save-presence":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 1_000_000:
                self.send_error(413)
                return
            try:
                raw = json.loads(self.rfile.read(length))
                if not isinstance(raw, dict):
                    raise ValueError("result must be an object")
                value = validate_presence_result(raw, manifest)
                payload = (
                    json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
                ).encode("utf-8")
                temporary = result_path.with_suffix(".json.tmp")
                temporary.write_bytes(payload)
                temporary.chmod(0o600)
                temporary.replace(result_path)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
                self._send(
                    400,
                    "application/json",
                    json.dumps({"error": str(error)}).encode("utf-8"),
                )
                return
            self._send(200, "application/json", payload)

        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _audio(self, path: Path, *, body: bool = True) -> None:
            size = path.stat().st_size
            start, end, status = 0, size - 1, 200
            header = self.headers.get("Range")
            if header:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
                if match is None or (not match.group(1) and not match.group(2)):
                    self.send_error(416)
                    return
                if match.group(1):
                    start = int(match.group(1))
                    end = int(match.group(2)) if match.group(2) else end
                else:
                    start = max(0, size - int(match.group(2)))
                if start >= size or end < start:
                    self.send_error(416)
                    return
                end, status = min(end, size - 1), 206
            length = end - start + 1
            self.send_response(status)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if body:
                with path.open("rb") as handle:
                    handle.seek(start)
                    remaining = length
                    while remaining:
                        block = handle.read(min(1024 * 1024, remaining))
                        if not block:
                            break
                        self.wfile.write(block)
                        remaining -= len(block)

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


__all__ = [
    "PRESENCE_MANIFEST_SCHEMA",
    "PRESENCE_RESULT_SCHEMA",
    "build_presence_review_server",
    "attest_completed_presence_listening",
    "load_presence_manifest",
    "prepare_addition_presence_review",
    "prepare_presence_review",
    "prepare_replacement_presence_review",
    "presence_document_sha256",
    "render_presence_review",
    "select_consensus_window",
    "validate_presence_result",
]
