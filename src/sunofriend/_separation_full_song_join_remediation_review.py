"""Create a blind owner-only review for targeted full-song join candidates."""

from __future__ import annotations

import hashlib
import html
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import tempfile
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_checkpoint_canonical import canonical_json_bytes
from ._separation_full_song_executor import (
    _require_private_directory,
    _require_private_regular,
)
from ._separation_full_song_join_remediation_executor import (
    CANDIDATE_REPORT_NAME,
    REPORT_NAME as EXECUTION_REPORT_NAME,
    SCHEMA as EXECUTION_SCHEMA,
    STATUS_COMPLETE as EXECUTION_STATUS,
    _FALSE_PERMISSIONS,
    _state_sha256,
    _verify_candidate_report,
)
from ._separation_full_song_review import (
    _load_stitch_report,
    _verify_stitch_audio,
)
from ._separation_full_song_stitch import REPORT_NAME as STITCH_REPORT_NAME


SCHEMA = "sunofriend.private-separation-full-song-join-remediation-review.v1"
STATUS = "unreviewed"
POLICY_ID = "blind-raw-versus-targeted-remediation-listening-v1"
REPORT_NAME = "private-separation-full-song-join-remediation-review.json"
HTML_NAME = "join_remediation_review.html"
ANSWER_KEY_NAME = "private-separation-full-song-join-remediation-answer-key.json"
AUDIO_DIRECTORY = "audio"
TARGET_SAMPLE_RATE = 44_100
_PAIR_CHOICES = ("A", "B", "equivalent", "neither", "cannot_tell")
_PATCH_ROLES = frozenset({"vocals", "instrumental"})
_FALSE_EFFECTS = {
    "candidate_audio_mutated": False,
    "preference_inferred": False,
    "publication_state_mutated": False,
    "raw_stitch_mutated": False,
    "separator_accepted": False,
    "separator_selected": False,
    "source_graph_mutated": False,
}


def _review_instructions(boundary_role_pair_count: int) -> list[str]:
    if (
        not isinstance(boundary_role_pair_count, int)
        or isinstance(boundary_role_pair_count, bool)
        or boundary_role_pair_count < 0
    ):
        raise ValueError("private remediation review comparison count differs")
    words = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four"}
    count = words.get(boundary_role_pair_count, str(boundary_role_pair_count))
    noun = (
        "boundary comparison"
        if boundary_role_pair_count == 1
        else "boundary comparisons"
    )
    return [
        "Review A and B by listening; neither letter is a recommendation.",
        f"Complete the {count} {noun} before judging patch edges.",
        "Then hear all three complete-song pairs for broader side effects.",
        "Equivalent, neither and cannot tell are valid outcomes.",
        "Do not open the separate answer key before exporting the review.",
    ]


def _validated_grouped_patches(
    candidate: Mapping[str, Any],
    *,
    total_frames: int,
    boundary_count: int,
) -> dict[tuple[int, str], Mapping[str, Any]]:
    patches = candidate.get("patches")
    summary = candidate.get("summary")
    if (
        not isinstance(total_frames, int)
        or isinstance(total_frames, bool)
        or total_frames < 1
        or not isinstance(boundary_count, int)
        or isinstance(boundary_count, bool)
        or boundary_count < 1
        or not isinstance(patches, list)
        or not isinstance(summary, Mapping)
        or not isinstance(summary.get("patched_boundary_role_pair_count"), int)
        or isinstance(summary.get("patched_boundary_role_pair_count"), bool)
        or summary["patched_boundary_role_pair_count"] != len(patches)
    ):
        raise ValueError("private remediation review patch inventory differs")
    grouped: dict[tuple[int, str], Mapping[str, Any]] = {}
    for patch in patches:
        if not isinstance(patch, Mapping):
            raise ValueError("private remediation review patch inventory differs")
        boundary_index = patch.get("boundary_index")
        role = patch.get("role")
        start_frame = patch.get("start_frame")
        end_frame = patch.get("end_frame")
        edge_blend_frames = patch.get("edge_blend_frames")
        if (
            not isinstance(boundary_index, int)
            or isinstance(boundary_index, bool)
            or not 1 <= boundary_index <= boundary_count
            or not isinstance(role, str)
            or role not in _PATCH_ROLES
            or not isinstance(start_frame, int)
            or isinstance(start_frame, bool)
            or not isinstance(end_frame, int)
            or isinstance(end_frame, bool)
            or not 0 <= start_frame < end_frame <= total_frames
            or not isinstance(edge_blend_frames, int)
            or isinstance(edge_blend_frames, bool)
            or edge_blend_frames < 1
            or 2 * edge_blend_frames >= end_frame - start_frame
        ):
            raise ValueError("private remediation review patch bounds differ")
        key = (boundary_index, role)
        if key in grouped:
            raise ValueError("private remediation review patch identity is duplicated")
        grouped[key] = patch
    return grouped


def _prepare_private_join_remediation_review(
    execution_dir: str | Path,
    *,
    package_dir: str | Path,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Write a fresh blind review without copying the complete-song WAVs."""

    import numpy as np
    import soundfile

    execution = Path(execution_dir).expanduser().absolute()
    package = Path(package_dir).expanduser().absolute()
    _require_private_directory(execution, "private remediation execution root")
    _require_private_directory(package, "private stitch package")
    execution_path = execution / EXECUTION_REPORT_NAME
    _require_private_regular(execution_path, "private remediation execution report")
    state = json.loads(execution_path.read_text(encoding="utf-8"))
    if (
        state.get("schema") != EXECUTION_SCHEMA
        or state.get("status") != EXECUTION_STATUS
        or state.get("state_sha256") != _state_sha256(state)
        or state.get("permissions") != _FALSE_PERMISSIONS
        or state.get("summary", {}).get("candidate_audio_complete") is not True
        or state.get("summary", {}).get("human_candidate_review_complete") is not False
    ):
        raise ValueError("private remediation execution is not review-ready")
    stitch_path = package / STITCH_REPORT_NAME
    stitch = _load_stitch_report(stitch_path)
    _verify_stitch_audio(package, stitch)
    candidate = _verify_candidate_report(execution, state, stitch=stitch)
    if candidate.get("readiness", {}).get("candidate_review_complete") is not False:
        raise ValueError("private remediation candidate review state differs")

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"private join-remediation review exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.building-",
            dir=destination.parent,
        )
    )
    temporary.chmod(0o700)
    try:
        audio_root = temporary / AUDIO_DIRECTORY
        audio_root.mkdir(mode=0o700)
        raw_paths = {
            role: package / stitch["artifacts"][role]["path"]
            for role in ("vocals", "instrumental", "reconstruction")
        }
        candidate_paths = {
            role: execution / candidate["artifacts"][role]["path"]
            for role in ("vocals", "instrumental", "reconstruction")
        }
        for role in raw_paths:
            _require_private_regular(raw_paths[role], "private raw review audio")
            _require_private_regular(
                candidate_paths[role], "private candidate review audio"
            )

        answer_units: list[dict[str, Any]] = []
        public_units: list[dict[str, Any]] = []
        grouped_patches = _validated_grouped_patches(
            candidate,
            total_frames=stitch["clock"]["frames"],
            boundary_count=stitch["clock"]["boundary_count"],
        )
        for boundary_index, role in sorted(grouped_patches):
            patch = grouped_patches[(boundary_index, role)]
            boundary_frame = (int(patch["start_frame"]) + int(patch["end_frame"])) // 2
            unit_id = f"boundary-{boundary_index:02d}-{role}"
            unit, answer = _clip_pair_unit(
                unit_id,
                kind="boundary_role_pair",
                title=f"Boundary {boundary_index}: {role}",
                focus=(
                    "Which version has the less audible join while preserving the "
                    f"musical continuity of the {role}?"
                ),
                raw_path=raw_paths[role],
                candidate_path=candidate_paths[role],
                centre_frame=boundary_frame,
                half_frames=2 * TARGET_SAMPLE_RATE,
                audio_root=audio_root,
                package_root=temporary,
                soundfile=soundfile,
                np=np,
            )
            public_units.append(unit)
            answer_units.append(answer)
            for edge_name, edge_frame in (
                ("start", int(patch["start_frame"])),
                ("end", int(patch["end_frame"])),
            ):
                edge_id = f"edge-{boundary_index:02d}-{role}-{edge_name}"
                edge_unit, edge_answer = _clip_pair_unit(
                    edge_id,
                    kind="patch_edge_pair",
                    title=f"Boundary {boundary_index}: {role} patch {edge_name} edge",
                    focus=(
                        "Which version has the cleaner transition at this patch edge? "
                        "Listen for a click, level jump, cut-off sound or sudden tone change."
                    ),
                    raw_path=raw_paths[role],
                    candidate_path=candidate_paths[role],
                    centre_frame=edge_frame,
                    half_frames=TARGET_SAMPLE_RATE,
                    audio_root=audio_root,
                    package_root=temporary,
                    soundfile=soundfile,
                    np=np,
                )
                public_units.append(edge_unit)
                answer_units.append(edge_answer)

        for role in ("vocals", "instrumental", "reconstruction"):
            unit_id = f"complete-song-{role}"
            unit, answer = _external_pair_unit(
                unit_id,
                role=role,
                raw_path=raw_paths[role],
                candidate_path=candidate_paths[role],
                review_root=temporary,
            )
            public_units.append(unit)
            answer_units.append(answer)

        expected_counts = {
            "boundary_role_pairs": len(grouped_patches),
            "patch_edge_pairs": 2 * len(grouped_patches),
            "complete_song_pairs": 3,
            "total_units": 3 * len(grouped_patches) + 3,
        }
        if len(public_units) != expected_counts["total_units"]:
            raise ValueError("private remediation review unit count differs")
        audio_manifest = {
            "schema": "sunofriend.private-separation-full-song-join-remediation-audio.v1",
            "units": [
                {
                    "unit_id": unit["unit_id"],
                    "audio": unit["audio"],
                }
                for unit in public_units
            ],
        }
        audio_manifest_sha256 = hashlib.sha256(
            canonical_json_bytes(audio_manifest)
        ).hexdigest()
        answer_key: dict[str, Any] = {
            "schema": "sunofriend.private-separation-full-song-join-remediation-answer-key.v1",
            "status": "sealed_do_not_open_before_review",
            "nonce": secrets.token_hex(32),
            "bindings": {
                "execution_report_sha256": _sha256(execution_path),
                "execution_state_sha256": state["state_sha256"],
                "candidate_report_sha256": _sha256(execution / CANDIDATE_REPORT_NAME),
                "candidate_document_sha256": candidate["document_sha256"],
                "stitch_report_sha256": _sha256(stitch_path),
                "stitch_document_sha256": stitch["document_sha256"],
                "audio_manifest_sha256": audio_manifest_sha256,
            },
            "units": answer_units,
            "permissions": dict(_FALSE_PERMISSIONS),
        }
        answer_key["document_sha256"] = _document_sha256(answer_key)
        _write_json_exclusive(temporary / ANSWER_KEY_NAME, answer_key)
        answer_key_sha256 = _sha256(temporary / ANSWER_KEY_NAME)
        commitment = hashlib.sha256(
            (
                f"{answer_key_sha256}:{answer_key['document_sha256']}:"
                f"{audio_manifest_sha256}"
            ).encode("ascii")
        ).hexdigest()
        document: dict[str, Any] = {
            "schema": SCHEMA,
            "status": STATUS,
            "evidence_scope": "private_development_only",
            "policy_id": POLICY_ID,
            "package_commitment": commitment,
            "question": (
                "Did targeted overlap re-inference reduce the reviewed joins without "
                "creating worse patch edges or complete-song problems?"
            ),
            "instructions": _review_instructions(len(grouped_patches)),
            "bindings": {
                "execution_report_sha256": _sha256(execution_path),
                "execution_state_sha256": state["state_sha256"],
                "candidate_report_sha256": _sha256(execution / CANDIDATE_REPORT_NAME),
                "candidate_document_sha256": candidate["document_sha256"],
                "stitch_report_sha256": _sha256(stitch_path),
                "stitch_document_sha256": stitch["document_sha256"],
                "audio_manifest_sha256": audio_manifest_sha256,
                "answer_key_sha256": answer_key_sha256,
                "answer_key_document_sha256": answer_key["document_sha256"],
            },
            "expected_counts": expected_counts,
            "units": public_units,
            "summary": {
                "reviewed_units": 0,
                "total_units": len(public_units),
                "complete": False,
            },
            "permissions": dict(_FALSE_PERMISSIONS),
            "effects": dict(_FALSE_EFFECTS),
            "limitations": [
                "Short-loop sample-RMS matching attenuates only the louder clip and is not LUFS matching.",
                "Complete-song A/B files are unchanged external controls and candidates, not copied into this package.",
                "A listening preference does not select, accept or publish a separator.",
            ],
        }
        document["document_sha256"] = _document_sha256(document)
        _write_json_exclusive(temporary / REPORT_NAME, document)
        (temporary / HTML_NAME).write_text(_review_html(document), encoding="utf-8")
        (temporary / HTML_NAME).chmod(0o600)
        _make_private_tree(temporary)
        os.replace(temporary, destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        **document,
        "report": str(destination / REPORT_NAME),
        "review_html": str(destination / HTML_NAME),
        "output_directory": str(destination),
    }


def _clip_pair_unit(
    unit_id: str,
    *,
    kind: str,
    title: str,
    focus: str,
    raw_path: Path,
    candidate_path: Path,
    centre_frame: int,
    half_frames: int,
    audio_root: Path,
    package_root: Path,
    soundfile: Any,
    np: Any,
    left_identity: str = "raw",
    right_identity: str = "candidate",
) -> tuple[dict[str, Any], dict[str, Any]]:
    total_frames = int(soundfile.info(raw_path).frames)
    start = max(0, centre_frame - half_frames)
    end = min(total_frames, centre_frame + half_frames)
    if end - start < TARGET_SAMPLE_RATE:
        raise ValueError("private remediation review clip is too short")
    raw, raw_rate = soundfile.read(
        raw_path, start=start, stop=end, dtype="float64", always_2d=True
    )
    candidate, candidate_rate = soundfile.read(
        candidate_path, start=start, stop=end, dtype="float64", always_2d=True
    )
    if (
        int(raw_rate) != TARGET_SAMPLE_RATE
        or int(candidate_rate) != TARGET_SAMPLE_RATE
        or raw.shape != candidate.shape
        or raw.shape[1] != 2
    ):
        raise ValueError("private remediation review clip geometry differs")
    raw_rms = _rms(raw, np=np)
    candidate_rms = _rms(candidate, np=np)
    target_rms = min(raw_rms, candidate_rms)
    if target_rms <= 10 ** (-60 / 20):
        raise ValueError("private remediation review clip is too quiet")
    raw_gain = target_rms / raw_rms
    candidate_gain = target_rms / candidate_rms
    if (
        not isinstance(left_identity, str)
        or not left_identity
        or not isinstance(right_identity, str)
        or not right_identity
        or left_identity == right_identity
    ):
        raise ValueError("private remediation review identities differ")
    sources = {
        left_identity: raw * raw_gain,
        right_identity: candidate * candidate_gain,
    }
    assignment = _assignment(left_identity, right_identity)
    audio: dict[str, Any] = {}
    for slot in ("A", "B"):
        identity = assignment[slot]
        path = audio_root / f"{unit_id}-{slot}.wav"
        soundfile.write(path, sources[identity], TARGET_SAMPLE_RATE, subtype="PCM_24")
        path.chmod(0o600)
        audio[slot] = {
            "path": path.relative_to(package_root).as_posix(),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }
    public = {
        "unit_id": unit_id,
        "kind": kind,
        "title": title,
        "focus": focus,
        "source_window": {
            "start_frame": start,
            "end_frame": end,
            "start_seconds": start / TARGET_SAMPLE_RATE,
            "end_seconds": end / TARGET_SAMPLE_RATE,
        },
        "level_policy": "attenuate-louder-to-quieter-whole-window-sample-rms-v1",
        "audio": audio,
        "heard": {"A": False, "B": False},
        "choice": None,
        "notes": "",
    }
    answer = {
        "unit_id": unit_id,
        "assignment": assignment,
        "raw_gain": round(raw_gain, 12),
        "candidate_gain": round(candidate_gain, 12),
        "raw_rms": round(raw_rms, 12),
        "candidate_rms": round(candidate_rms, 12),
    }
    return public, answer


def _external_pair_unit(
    unit_id: str,
    *,
    role: str,
    raw_path: Path,
    candidate_path: Path,
    review_root: Path,
    left_identity: str = "raw",
    right_identity: str = "candidate",
) -> tuple[dict[str, Any], dict[str, Any]]:
    if (
        not isinstance(left_identity, str)
        or not left_identity
        or not isinstance(right_identity, str)
        or not right_identity
        or left_identity == right_identity
    ):
        raise ValueError("private remediation review identities differ")
    assignment = _assignment(left_identity, right_identity)
    identities = {left_identity: raw_path, right_identity: candidate_path}
    audio = {}
    for slot in ("A", "B"):
        path = identities[assignment[slot]]
        audio[slot] = {
            "path": os.path.relpath(path, review_root),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }
    public = {
        "unit_id": unit_id,
        "kind": "complete_song_pair",
        "title": f"Complete song: {role}",
        "focus": (
            "Hear both complete tracks. Which remains useful overall and avoids new "
            "clicks, cut-offs, level jumps or sudden tone changes?"
        ),
        "source_window": None,
        "level_policy": "unchanged-full-song-files-no-level-processing",
        "audio": audio,
        "heard": {"A": False, "B": False},
        "choice": None,
        "notes": "",
    }
    return public, {"unit_id": unit_id, "assignment": assignment}


def _assignment(
    left_identity: str = "raw", right_identity: str = "candidate"
) -> dict[str, str]:
    if left_identity == right_identity:
        raise ValueError("private remediation review identities differ")
    if secrets.randbelow(2):
        return {"A": left_identity, "B": right_identity}
    return {"A": right_identity, "B": left_identity}


def _rms(value: Any, *, np: Any) -> float:
    result = float(np.sqrt(np.mean(np.square(value, dtype="float64"))))
    if not math.isfinite(result) or result <= 0:
        raise ValueError("private remediation review RMS differs")
    return result


def _review_html(document: Mapping[str, Any]) -> str:
    seed = json.dumps(document, ensure_ascii=False).replace("</", "<\\/")
    choices = "".join(
        f'<label><input type="radio" name="choice-TEMPLATE" value="{value}"> '
        f"{html.escape(value.replace('_', ' '))}</label>"
        for value in _PAIR_CHOICES
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sunofriend join-remediation review</title>
<style>
body{{margin:0;background:#08111d;color:#e8f1ff;font:18px/1.45 system-ui,sans-serif}}main{{max-width:1120px;margin:auto;padding:32px}}
.privacy{{background:#104a32;padding:12px 24px;font-weight:700}}.card{{background:#101e2c;border:1px solid #29435b;border-radius:18px;padding:24px;margin:22px 0}}
h1{{font-size:42px}}h2{{color:#63d7ff}}audio{{width:100%;margin:8px 0 14px}}label{{display:inline-block;margin:7px 16px 7px 0}}textarea{{width:100%;min-height:80px;background:#0a1724;color:#fff;border:1px solid #3b607d;border-radius:8px}}
button{{background:#1d789c;color:#fff;border:0;border-radius:9px;padding:14px 20px;font-size:17px;margin-right:10px}}button:disabled{{opacity:.45}}.status{{color:#ffd253;font-weight:700}}code{{color:#8edcff}}
</style></head><body><div class="privacy">Private local developer review — no audio or review is uploaded</div><main>
<div class="card"><h1>Targeted join-remediation review</h1><p>{html.escape(document["question"])}</p>
<p>There are <strong>{document["expected_counts"]["boundary_role_pairs"]} boundary comparisons</strong>, <strong>{document["expected_counts"]["patch_edge_pairs"]} edge comparisons</strong> and <strong>{document["expected_counts"]["complete_song_pairs"]} complete-song comparisons</strong>. A and B are randomised independently. Equivalent, neither and cannot tell are valid.</p>
<p><strong>Do not open the separate answer key before exporting this review.</strong></p><p class="status" id="progress">Reviewed 0 of {len(document["units"])} units</p></div>
<div id="units"></div>
<div class="card"><button id="complete">Mark review complete</button><button id="export" disabled>Export reviewed JSON</button><p id="message"></p></div>
<script id="seed" type="application/json">{seed}</script><script>
const review=JSON.parse(document.getElementById('seed').textContent); const host=document.getElementById('units');
const choiceTemplate={json.dumps(choices)};
function render(){{review.units.forEach((u,i)=>{{const c=document.createElement('section');c.className='card';
c.innerHTML=`<h2>${{i+1}}. ${{u.title}}</h2><p>${{u.focus}}</p><h3>Candidate A</h3><audio controls preload="metadata" src="${{u.audio.A.path}}"></audio><label><input type="checkbox" data-heard="A"> I heard A</label><h3>Candidate B</h3><audio controls preload="metadata" src="${{u.audio.B.path}}"></audio><label><input type="checkbox" data-heard="B"> I heard B</label><div class="choices">${{choiceTemplate.replaceAll('choice-TEMPLATE','choice-'+i)}}</div><p>Optional private notes</p><textarea maxlength="1000"></textarea>`;
c.querySelectorAll('[data-heard]').forEach(x=>x.onchange=()=>{{u.heard[x.dataset.heard]=x.checked;update();}}); c.querySelectorAll('input[type=radio]').forEach(x=>x.onchange=()=>{{u.choice=x.value;update();}}); c.querySelector('textarea').oninput=e=>u.notes=e.target.value;host.appendChild(c);}});}}
function update(){{const done=review.units.filter(u=>u.heard.A&&u.heard.B&&u.choice).length;review.summary.reviewed_units=done;document.getElementById('progress').textContent=`Reviewed ${{done}} of ${{review.units.length}} units`;}}
document.getElementById('complete').onclick=()=>{{update();if(review.summary.reviewed_units!==review.units.length){{document.getElementById('message').textContent='Hear A and B and choose one outcome for every unit first.';return;}}review.status='reviewed';review.summary.complete=true;document.getElementById('export').disabled=false;document.getElementById('message').textContent='Complete. Export the reviewed JSON.';}};
document.getElementById('export').onclick=()=>{{const blob=new Blob([JSON.stringify(review,null,2)+'\\n'],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='join_remediation_review.reviewed.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}};render();update();
</script></main></body></html>"""


def _write_json_exclusive(path: Path, document: Mapping[str, Any]) -> None:
    payload = (
        json.dumps(
            document, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
        )
        + "\n"
    ).encode("utf-8")
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        os.set_inheritable(descriptor, False)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise RuntimeError("private remediation review write made no progress")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _make_private_tree(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("private remediation review contains a symbolic link")
        path.chmod(0o700 if path.is_dir() else 0o600)
    root.chmod(0o700)


__all__: tuple[str, ...] = ()
