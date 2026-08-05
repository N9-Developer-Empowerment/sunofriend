"""Stitch a verified private full-song queue on its exact canonical clock."""

from __future__ import annotations

import hashlib
import html
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_checkpoint_canonical import canonical_json_bytes
from ._separation_full_song_executor import (
    REPORT_NAME as EXECUTION_REPORT_NAME,
    SCHEMA as EXECUTION_SCHEMA,
    _load_verified_plan,
    _require_private_regular,
    _verify_completed_attempts,
    _verify_state_binding,
)


SCHEMA = "sunofriend.private-separation-full-song-stitch.v1"
STATUS = "exact_clock_stitch_complete_review_required"
REPORT_NAME = "private-separation-full-song-stitch.json"
REVIEW_SCHEMA = "sunofriend.private-separation-boundary-review.v1"
REVIEW_NAME = "separation_boundary_review.json"
REVIEW_HTML_NAME = "separation_boundary_review.html"
TARGET_SAMPLE_RATE = 44_100
REVIEW_HALF_WINDOW_FRAMES = 88_200
_ROLES = ("source", "vocals", "instrumental", "reconstruction")
_FALSE_PERMISSIONS = {
    "accepted": False,
    "automatic_selection": False,
    "source_graph_activation": False,
    "simple_mode_available": False,
    "studio_import_available": False,
    "product_route_permitted": False,
    "publication_permitted": False,
}


def _stitch_private_separation_full_song(
    plan_report_path: str | Path,
    execution_report_path: str | Path,
    *,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Create exact-length PCM24 roles and a boundary-listening package."""

    import numpy as np
    import soundfile

    plan_path, plan, plan_sha256 = _load_verified_plan(plan_report_path)
    execution_path = Path(execution_report_path).expanduser().absolute()
    if execution_path.name != EXECUTION_REPORT_NAME:
        raise ValueError("private full-song execution filename differs")
    _require_private_regular(execution_path, "private full-song execution report")
    execution_sha256 = _sha256(execution_path)
    try:
        execution = json.loads(execution_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("private full-song execution report differs") from error
    if (
        execution.get("schema") != EXECUTION_SCHEMA
        or execution.get("status")
        != "private_chunk_execution_complete_not_selected"
        or execution.get("summary", {}).get("all_worker_runs_complete") is not True
    ):
        raise ValueError("private full-song execution is incomplete")
    request_binding = execution.get("bindings", {}).get("private_pilot_request")
    if request_binding is not None and not isinstance(request_binding, Mapping):
        raise ValueError("private full-song stitch request binding differs")
    _verify_state_binding(
        execution,
        plan=plan,
        plan_sha256=plan_sha256,
        private_pilot_request_binding=request_binding,
    )
    _verify_completed_attempts(
        execution_path.parent,
        execution,
        plan,
        private_pilot_request_binding=request_binding,
    )

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"private full-song stitch already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.building-", dir=destination.parent)
    )
    temporary.chmod(0o700)
    try:
        stems = temporary / "STEMS"
        stems.mkdir(mode=0o700)
        sources = temporary / "SOURCE"
        sources.mkdir(mode=0o700)
        selected = _selected_attempt_roots(execution_path.parent, execution)
        role_inputs = {
            "source": [plan_path.parent / chunk["audio_artifact"]["path"] for chunk in plan["chunks"]],
            "vocals": [root / "staging/quarantine/STEMS/vocals.wav" for root in selected],
            "instrumental": [root / "staging/quarantine/STEMS/instrumental.wav" for root in selected],
        }
        artifacts: dict[str, Any] = {}
        source_out = sources / "source-44100.wav"
        artifacts["source"] = _concatenate_pcm24(
            role_inputs["source"], source_out, expected_frames=plan["canonical_clock"]["frames"], soundfile=soundfile
        )
        artifacts["source"]["path"] = "SOURCE/source-44100.wav"
        for role in ("vocals", "instrumental"):
            artifacts[role] = _concatenate_pcm24(
                role_inputs[role], stems / f"{role}.wav", expected_frames=plan["canonical_clock"]["frames"], soundfile=soundfile
            )
            artifacts[role]["path"] = f"STEMS/{role}.wav"
        reconstruction_out = stems / "reconstruction.wav"
        reconstruction_gain = _write_reconstruction(
            stems / "vocals.wav",
            stems / "instrumental.wav",
            reconstruction_out,
            soundfile=soundfile,
            np=np,
        )
        artifacts["reconstruction"] = _inspect_pcm24(
            reconstruction_out,
            expected_frames=plan["canonical_clock"]["frames"],
            soundfile=soundfile,
        )
        artifacts["reconstruction"]["path"] = "STEMS/reconstruction.wav"
        artifacts["reconstruction"]["global_gain"] = reconstruction_gain

        boundary_review = _write_boundary_review(
            temporary,
            title=str(plan["corpus"]["track_title"]),
            boundaries=[chunk["end_frame"] for chunk in plan["chunks"][:-1]],
            role_paths={
                "source": source_out,
                "vocals": stems / "vocals.wav",
                "instrumental": stems / "instrumental.wav",
                "reconstruction": reconstruction_out,
            },
            soundfile=soundfile,
            np=np,
        )
        document: dict[str, Any] = {
            "schema": SCHEMA,
            "status": STATUS,
            "evidence_scope": "private_development_only",
            "bindings": {
                "plan_report_sha256": plan_sha256,
                "plan_document_sha256": plan["document_sha256"],
                "execution_report_sha256": execution_sha256,
                "execution_state_sha256": execution["state_sha256"],
                "canonical_pcm24_int32_sequence_sha256": plan["canonical_clock"]["pcm24_int32_sequence_sha256"],
                **(
                    {"private_pilot_request": dict(request_binding)}
                    if request_binding is not None
                    else {}
                ),
            },
            "clock": {
                "sample_rate": TARGET_SAMPLE_RATE,
                "channels": 2,
                "frames": plan["canonical_clock"]["frames"],
                "duration_seconds": plan["canonical_clock"]["duration_seconds"],
                "chunk_count": len(plan["chunks"]),
                "boundary_count": len(plan["chunks"]) - 1,
                "gap_frames": 0,
                "overlap_frames": 0,
                "crossfade_frames": 0,
            },
            "artifacts": artifacts,
            "reconstruction": {
                "method": "sample-aligned vocals plus instrumental",
                "global_gain": reconstruction_gain,
                "per_chunk_gain_or_repair_applied_by_stitcher": False,
                "quality_established": False,
            },
            "boundary_review": boundary_review,
            "readiness": {
                "worker_runs_complete": True,
                "stitched_outputs_complete": True,
                "exact_duration_and_frame_count_verified": True,
                "boundary_listening_complete": False,
                "full_song_quality_accepted": False,
                "publication_ready": False,
            },
            "permissions": dict(_FALSE_PERMISSIONS),
            "effects": {
                "private_stitched_audio_created": True,
                "source_audio_mutated": False,
                "source_graph_mutated": False,
                "product_contract_mutated": False,
                "separator_selected": False,
            },
            "limitations": [
                "The stitch is exact-clock concatenation with no hidden repair or crossfade.",
                "Independent model invocations can change tone or level at chunk boundaries.",
                "A reconstruction is a diagnostic sum, not a mastered song or accepted separation.",
                "Human boundary and full-song listening are still required.",
            ],
        }
        document["document_sha256"] = _document_sha256(document)
        _write_json(temporary / REPORT_NAME, document)
        _make_private_tree(temporary)
        os.replace(temporary, destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    result = dict(document)
    result["report"] = str(destination / REPORT_NAME)
    result["review_html"] = str(destination / boundary_review["html"])
    result["output_directory"] = str(destination)
    return result


def _selected_attempt_roots(root: Path, execution: Mapping[str, Any]) -> list[Path]:
    selected: list[Path] = []
    for chunk in execution["chunks"]:
        number = chunk["selected_attempt"]
        matches = [
            item
            for item in chunk["attempts"]
            if item.get("attempt") == number and item.get("status") == "verified_complete"
        ]
        if len(matches) != 1:
            raise ValueError("private full-song selected attempt differs")
        selected.append(root / matches[0]["path"])
    return selected


def _concatenate_pcm24(
    inputs: list[Path],
    output: Path,
    *,
    expected_frames: int,
    soundfile: Any,
) -> dict[str, Any]:
    digest = hashlib.sha256()
    frames = 0
    with soundfile.SoundFile(
        output,
        mode="x",
        samplerate=TARGET_SAMPLE_RATE,
        channels=2,
        subtype="PCM_24",
        format="WAV",
    ) as writer:
        for path in inputs:
            audio, rate = soundfile.read(path, dtype="int32", always_2d=True)
            if int(rate) != TARGET_SAMPLE_RATE or audio.shape[1] != 2:
                raise ValueError("private full-song stitch input geometry differs")
            writer.write(audio)
            digest.update(audio.astype("<i4", copy=False).tobytes(order="C"))
            frames += len(audio)
    output.chmod(0o600)
    if frames != expected_frames:
        raise ValueError("private full-song stitch frame count differs")
    result = _inspect_pcm24(output, expected_frames=expected_frames, soundfile=soundfile)
    result["pcm24_int32_sequence_sha256"] = digest.hexdigest()
    return result


def _write_reconstruction(
    vocals: Path,
    instrumental: Path,
    output: Path,
    *,
    soundfile: Any,
    np: Any,
) -> float:
    vocal, vocal_rate = soundfile.read(vocals, dtype="float64", always_2d=True)
    music, music_rate = soundfile.read(instrumental, dtype="float64", always_2d=True)
    if vocal_rate != TARGET_SAMPLE_RATE or music_rate != TARGET_SAMPLE_RATE or vocal.shape != music.shape:
        raise ValueError("private full-song reconstruction geometry differs")
    summed = vocal + music
    peak = float(np.max(np.abs(summed))) if summed.size else 0.0
    gain = min(1.0, 0.98 / peak) if peak > 0 else 1.0
    soundfile.write(output, summed * gain, TARGET_SAMPLE_RATE, subtype="PCM_24")
    output.chmod(0o600)
    return round(gain, 9)


def _inspect_pcm24(path: Path, *, expected_frames: int, soundfile: Any) -> dict[str, Any]:
    info = soundfile.info(path)
    if (
        int(info.samplerate) != TARGET_SAMPLE_RATE
        or int(info.channels) != 2
        or int(info.frames) != expected_frames
        or info.subtype != "PCM_24"
    ):
        raise ValueError("private full-song stitched output geometry differs")
    return {
        "path": path.as_posix(),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "geometry": {
            "sample_rate": TARGET_SAMPLE_RATE,
            "channels": 2,
            "sample_width_bytes": 3,
            "frames": expected_frames,
        },
    }


def _write_boundary_review(
    root: Path,
    *,
    title: str,
    boundaries: list[int],
    role_paths: Mapping[str, Path],
    soundfile: Any,
    np: Any,
) -> dict[str, Any]:
    review_root = root / "BOUNDARY-REVIEW"
    audio_root = review_root / "audio"
    audio_root.mkdir(parents=True, mode=0o700)
    units = []
    total_frames = int(soundfile.info(role_paths["source"]).frames)
    for index, boundary in enumerate(boundaries, start=1):
        paths: dict[str, Any] = {}
        half_window = min(
            REVIEW_HALF_WINDOW_FRAMES,
            boundary,
            total_frames - boundary,
        )
        if half_window < 1:
            raise ValueError("private boundary review has no surrounding audio")
        start = boundary - half_window
        end = boundary + half_window
        for role in _ROLES:
            source, rate = soundfile.read(
                role_paths[role],
                start=start,
                stop=end,
                dtype="float32",
                always_2d=True,
            )
            if int(rate) != TARGET_SAMPLE_RATE or source.shape != (2 * half_window, 2):
                raise ValueError("private boundary review window differs")
            relative = f"audio/boundary-{index:02d}-{role}.wav"
            target = review_root / relative
            soundfile.write(target, source, TARGET_SAMPLE_RATE, subtype="PCM_24")
            target.chmod(0o600)
            paths[role] = {
                "path": relative,
                "sha256": _sha256(target),
                "bytes": target.stat().st_size,
            }
        units.append(
            {
                "boundary_index": index,
                "frame": boundary,
                "seconds": boundary / TARGET_SAMPLE_RATE,
                "window_seconds": [start / TARGET_SAMPLE_RATE, end / TARGET_SAMPLE_RATE],
                "join_at_window_seconds": half_window / TARGET_SAMPLE_RATE,
                "audio": paths,
                "heard_all": False,
                "ratings": {
                    "vocals": "unreviewed",
                    "instrumental": "unreviewed",
                    "reconstruction": "unreviewed",
                },
                "notes": "",
            }
        )
    full_song_paths = {
        "source": "../SOURCE/source-44100.wav",
        "vocals": "../STEMS/vocals.wav",
        "instrumental": "../STEMS/instrumental.wav",
        "reconstruction": "../STEMS/reconstruction.wav",
    }
    full_song_audio = {
        role: {
            "path": full_song_paths[role],
            "sha256": _sha256(role_paths[role]),
            "bytes": role_paths[role].stat().st_size,
        }
        for role in _ROLES
    }
    contract = {
        "schema": REVIEW_SCHEMA,
        "status": "unreviewed",
        "evidence_scope": "private_development_only",
        "title": title,
        "question": "Can you hear a click, cut, level jump or tone change at the centre join?",
        "policy": {
            "maximum_window_seconds": 4.0,
            "maximum_join_at_window_seconds": 2.0,
            "ratings": ["clean", "audible_join", "cannot_tell"],
            "review_every_boundary": True,
            "source_is_context_not_a_rated_separator_output": True,
            "full_song_ratings": [
                "useful",
                "noticeable_problems",
                "not_useful",
                "cannot_tell",
            ],
        },
        "full_song": {
            "audio": full_song_audio,
            "heard_all": False,
            "ratings": {
                "vocals": "unreviewed",
                "instrumental": "unreviewed",
                "reconstruction": "unreviewed",
            },
            "notes": "",
        },
        "units": units,
        "summary": {
            "full_song_reviewed": False,
            "reviewed_boundaries": 0,
            "boundary_count": len(units),
        },
        "permissions": dict(_FALSE_PERMISSIONS),
    }
    immutable = _immutable_review(contract)
    contract["package_commitment"] = hashlib.sha256(canonical_json_bytes(immutable)).hexdigest()
    _write_json(review_root / REVIEW_NAME, contract)
    html_text = _boundary_review_html(contract)
    (review_root / REVIEW_HTML_NAME).write_text(html_text, encoding="utf-8")
    (review_root / REVIEW_HTML_NAME).chmod(0o600)
    return {
        "status": "unreviewed",
        "seed": f"BOUNDARY-REVIEW/{REVIEW_NAME}",
        "seed_sha256": _sha256(review_root / REVIEW_NAME),
        "html": f"BOUNDARY-REVIEW/{REVIEW_HTML_NAME}",
        "html_sha256": _sha256(review_root / REVIEW_HTML_NAME),
        "package_commitment": contract["package_commitment"],
        "boundary_count": len(units),
    }


def _immutable_review(review: Mapping[str, Any]) -> dict[str, Any]:
    value = json.loads(json.dumps(review))
    value.pop("status", None)
    value.pop("summary", None)
    value.pop("package_commitment", None)
    value["full_song"].pop("heard_all", None)
    value["full_song"].pop("ratings", None)
    value["full_song"].pop("notes", None)
    for unit in value["units"]:
        unit.pop("heard_all", None)
        unit.pop("ratings", None)
        unit.pop("notes", None)
    return value


def _boundary_review_html(seed: Mapping[str, Any]) -> str:
    encoded = json.dumps(seed, ensure_ascii=False).replace("<", "\\u003c")
    safe_title = html.escape(str(seed["title"]))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sunofriend boundary review</title><style>
body{{margin:0;background:#08111b;color:#e9f2fa;font:17px system-ui,sans-serif}}main{{max-width:1000px;margin:auto;padding:32px}}section{{background:#111f2c;border:1px solid #294256;border-radius:16px;padding:22px;margin:18px 0}}h1{{font-size:42px}}h2{{color:#66ddff}}audio{{width:100%}}label{{display:block;margin:8px 0}}select,textarea,button{{font:inherit;background:#17344a;color:white;border:1px solid #4e819f;border-radius:8px;padding:9px}}textarea{{width:96%}}button{{background:#17658b;cursor:pointer}}.warn{{border-left:5px solid #ffc542;padding-left:14px}}.done{{color:#8df0ac}}
</style></head><body><main><h1>Full-song boundary review</h1><p>{safe_title}</p>
<section><h2>What to listen for</h2><p class="warn">First hear the complete song outputs and judge whether each is useful despite any audible problems. Then review every exact chunk join. Listen for a click, a cut-off note, a level jump, or a sudden change in tone. The source is context. Rate the three generated outputs independently. A clean join does not prove the separator is accurate.</p><p id="progress">Full song not reviewed; 0 of {len(seed['units'])} boundaries reviewed</p></section>
<section id="full"><h2>Complete song</h2><p>This is the broad musical check. It can reveal failures that four-second join windows miss.</p><div id="full-audio"></div><label><input type="checkbox" id="full-heard"> I heard all four complete-song tracks</label><div id="full-ratings"></div><label>Full-song notes<textarea id="full-notes"></textarea></label></section>
<div id="units"></div><section><button id="complete">Mark review complete and export JSON</button> <span id="message"></span></section>
<script>const review={encoded};const root=document.getElementById('units');
function render(){{document.getElementById('full-audio').innerHTML=['source','vocals','instrumental','reconstruction'].map(r=>`<label>${{r}}<audio controls preload="metadata" src="${{review.full_song.audio[r].path}}"></audio></label>`).join('');document.getElementById('full-ratings').innerHTML=['vocals','instrumental','reconstruction'].map(r=>`<label>${{r}} overall <select data-full-role="${{r}}"><option>unreviewed</option><option>useful</option><option>noticeable_problems</option><option>not_useful</option><option>cannot_tell</option></select></label>`).join('');review.units.forEach((u,i)=>{{const s=document.createElement('section');s.innerHTML=`<h2>Boundary ${{u.boundary_index}} at ${{u.seconds.toFixed(3)}}s</h2><p>Join is at ${{u.join_at_window_seconds.toFixed(3)}}s within each clip.</p>`+['source','vocals','instrumental','reconstruction'].map(r=>`<label>${{r}}<audio controls preload="metadata" src="${{u.audio[r].path}}"></audio></label>`).join('')+`<label><input type="checkbox" data-heard="${{i}}"> I heard all four clips</label>`+['vocals','instrumental','reconstruction'].map(r=>`<label>${{r}} join <select data-unit="${{i}}" data-role="${{r}}"><option>unreviewed</option><option>clean</option><option>audible_join</option><option>cannot_tell</option></select></label>`).join('')+`<label>Notes<textarea data-notes="${{i}}"></textarea></label>`;root.appendChild(s)}})}}
function sync(){{review.full_song.heard_all=document.getElementById('full-heard').checked;review.full_song.notes=document.getElementById('full-notes').value;document.querySelectorAll('[data-full-role]').forEach(x=>review.full_song.ratings[x.dataset.fullRole]=x.value);document.querySelectorAll('[data-heard]').forEach(x=>review.units[+x.dataset.heard].heard_all=x.checked);document.querySelectorAll('select[data-unit]').forEach(x=>review.units[+x.dataset.unit].ratings[x.dataset.role]=x.value);document.querySelectorAll('[data-notes]').forEach(x=>review.units[+x.dataset.notes].notes=x.value);const full=review.full_song.heard_all&&Object.values(review.full_song.ratings).every(v=>v!=='unreviewed');const n=review.units.filter(u=>u.heard_all&&Object.values(u.ratings).every(v=>v!=='unreviewed')).length;review.summary.full_song_reviewed=full;review.summary.reviewed_boundaries=n;document.getElementById('progress').textContent=`Full song ${{full?'reviewed':'not reviewed'}}; ${{n}} of ${{review.units.length}} boundaries reviewed`;return [full,n]}}
document.addEventListener('change',sync);document.getElementById('complete').onclick=()=>{{const [full,n]=sync();if(!full||n!==review.units.length){{document.getElementById('message').textContent='Please hear and rate the full song and every boundary first.';return}}review.status='reviewed';const blob=new Blob([JSON.stringify(review,null,2)+'\\n'],{{type:'application/json'}}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='separation-boundary-and-full-song.reviewed.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);document.getElementById('message').className='done';document.getElementById('message').textContent='Reviewed JSON exported.'}};render();</script></main></body></html>"""


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def _make_private_tree(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("private full-song stitch contains a symbolic link")
        path.chmod(0o700 if path.is_dir() else 0o600)
    root.chmod(0o700)


__all__: tuple[str, ...] = ()
