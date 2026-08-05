"""Build independent final-acceptance reviews for every eligible variant.

This stage is deliberately downstream of the complete multi-variant human
review and alignment reassessment.  It re-derives that exact reassessment,
includes every eligible variant in canonical order and creates one independent
whole-song review for each.  It does not compare, rank, select or accept a
variant; those effects require a later verified browser export and resolver.
"""

from __future__ import annotations

import html
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping, Sequence

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_candidate_followup_variant_full_song_review import (
    REPORT_NAME as FULL_SONG_PACKAGE_REPORT_NAME,
    SCHEMA as FULL_SONG_PACKAGE_SCHEMA,
    STATUS as FULL_SONG_PACKAGE_STATUS,
    _verify_parent_package,
)
from ._separation_candidate_followup_variant_full_song_review_result import (
    RESULT_SCHEMA as FULL_SONG_RESULT_SCHEMA,
    RESULT_STATUS as FULL_SONG_RESULT_STATUS,
)
from ._separation_candidate_followup_variant_readiness_reassessment import (
    SCHEMA as READINESS_SCHEMA,
    STATUS as READINESS_STATUS,
    _FALSE_EFFECTS as READINESS_EFFECTS,
    _reassess_private_candidate_followup_variant_readiness,
)
from ._separation_full_song_executor import (
    _require_private_directory,
    _require_private_regular,
)
from ._separation_full_song_join_remediation_executor_v2 import (
    _FALSE_PERMISSIONS,
    _read_pcm24_snapshot,
    _require_output_disjoint_from_inputs,
)
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
    _write_json_exclusive,
)
from ._separation_full_song_stitch import _make_private_tree


SCHEMA = (
    "sunofriend.private-separation-candidate-followup-variant-"
    "final-acceptance-review-package.v1"
)
STATUS = "unreviewed_independent_final_acceptance_reviews"
REPORT_NAME = (
    "private-separation-candidate-followup-variant-final-acceptance-review-"
    "package.json"
)
REVIEW_SCHEMA = (
    "sunofriend.private-separation-candidate-followup-variant-"
    "final-acceptance-review.v1"
)
REVIEW_STATUS = "unreviewed"
REVIEW_SEED_NAME = "final_acceptance_review.json"
REVIEW_HTML_NAME = "final_acceptance_review.html"
_ROLES = ("source", "vocals", "instrumental", "reconstruction")
_QUESTION_SPECS = (
    {
        "id": "vocals_useful_for_melody_workflow",
        "prompt": (
            "Is the complete vocal output useful as input to Sunofriend's "
            "melody and MIDI workflow?"
        ),
        "choices": ("yes", "no", "cannot_tell"),
    },
    {
        "id": "instrumental_useful_for_midi_workflow",
        "prompt": (
            "Is the complete instrumental output useful as input to "
            "Sunofriend's MIDI and instrument workflow?"
        ),
        "choices": ("yes", "no", "cannot_tell"),
    },
    {
        "id": "reconstruction_continuous_and_synchronised",
        "prompt": (
            "Does the reconstruction remain continuous and synchronised with "
            "the source from start to finish?"
        ),
        "choices": ("yes", "no", "cannot_tell"),
    },
    {
        "id": "candidate_suitable_for_private_pilot",
        "prompt": (
            "Would you accept this exact candidate for a private Sunofriend "
            "stem-separation pilot?"
        ),
        "choices": ("accept_private_pilot", "needs_more_work", "cannot_tell"),
    },
)
_PACKAGE_EFFECTS = {
    "acceptance_record_created": False,
    "audio_created_or_mutated": False,
    "candidate_accepted": False,
    "candidate_selected": False,
    "private_review_audio_copied": True,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "source_graph_mutated": False,
}
_REVIEW_EFFECTS = {
    "acceptance_record_created": False,
    "audio_created_or_mutated": False,
    "candidate_accepted": False,
    "candidate_selected": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "source_graph_mutated": False,
}


def _build_private_candidate_followup_variant_final_acceptance_reviews(
    readiness_result_path: str | Path,
    *,
    full_song_review_result_path: str | Path,
    alignment_package_dir: str | Path,
    full_song_review_export_paths: Sequence[str | Path],
    full_song_review_package_dir: str | Path,
    variant_review_result_path: str | Path,
    variant_reviewed_export_path: str | Path,
    variant_review_package_dir: str | Path,
    plan_path: str | Path,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
    variant_execution_dir: str | Path,
    stitch_package_dir: str | Path,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Create one independent whole-song acceptance page per eligible variant."""

    import soundfile

    if isinstance(full_song_review_export_paths, (str, bytes, Path)):
        raise TypeError(
            "full_song_review_export_paths must be the complete review sequence"
        )
    reviewed_exports = list(full_song_review_export_paths)
    if not reviewed_exports:
        raise ValueError("no eligible-variant full-song reviews supplied")

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(
            f"private final acceptance review package exists: {destination}"
        )
    _require_private_directory(
        destination.parent, "private final acceptance review package parent"
    )
    full_song_root = Path(full_song_review_package_dir).expanduser().absolute()
    alignment_root = Path(alignment_package_dir).expanduser().absolute()
    variant_review_root = Path(variant_review_package_dir).expanduser().absolute()
    for root, label in (
        (full_song_root, "private eligible-variant full-song review package"),
        (alignment_root, "private eligible-variant alignment package"),
        (variant_review_root, "private follow-up variant review package"),
    ):
        _require_private_directory(root, label)

    reassessment_kwargs = {
        "alignment_package_dir": alignment_root,
        "full_song_review_export_paths": reviewed_exports,
        "full_song_review_package_dir": full_song_root,
        "variant_review_result_path": variant_review_result_path,
        "variant_reviewed_export_path": variant_reviewed_export_path,
        "variant_review_package_dir": variant_review_root,
        "plan_path": plan_path,
        "execution_dir": execution_dir,
        "v2_execution_dir": v2_execution_dir,
        "variant_execution_dir": variant_execution_dir,
        "stitch_package_dir": stitch_package_dir,
    }
    readiness_snapshot, readiness = _verified_exact_readiness(
        readiness_result_path,
        full_song_review_result_path=full_song_review_result_path,
        reassessment_kwargs=reassessment_kwargs,
    )
    eligible_ids = _eligible_variant_ids(readiness)
    full_song_result_snapshot, full_song_result = _verified_full_song_result(
        full_song_review_result_path, readiness=readiness
    )
    package_snapshot, full_song_package = _verified_full_song_package(
        full_song_root,
        readiness=readiness,
        full_song_result=full_song_result,
        soundfile=soundfile,
    )

    evidence_roots = (
        alignment_root,
        full_song_root,
        variant_review_root,
        Path(execution_dir).expanduser().absolute(),
        Path(v2_execution_dir).expanduser().absolute(),
        Path(variant_execution_dir).expanduser().absolute(),
        Path(stitch_package_dir).expanduser().absolute(),
    )
    evidence_paths = (
        readiness_snapshot["path"],
        full_song_result_snapshot["path"],
        package_snapshot["path"],
        Path(variant_review_result_path).expanduser().absolute(),
        Path(variant_reviewed_export_path).expanduser().absolute(),
        Path(plan_path).expanduser().absolute(),
        *(Path(path).expanduser().absolute() for path in reviewed_exports),
    )
    _require_output_disjoint_from_inputs(
        destination,
        evidence_roots=evidence_roots,
        evidence_paths=evidence_paths,
    )

    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.building-", dir=destination.parent)
    )
    temporary.chmod(0o700)
    try:
        reviews: list[dict[str, Any]] = []
        packages_by_variant = {
            item["variant_id"]: item
            for item in full_song_package["variant_packages"]
        }
        for index, variant_id in enumerate(eligible_ids, start=1):
            review_root = temporary / f"candidate-{index:02d}"
            review_root.mkdir(mode=0o700)
            audio_root = review_root / "audio"
            audio_root.mkdir(mode=0o700)
            source_package = full_song_root / packages_by_variant[variant_id]["directory"]
            audio = _copy_exact_audio(
                source_package,
                packages_by_variant[variant_id]["artifacts"],
                review_root=review_root,
                expected_frames=int(full_song_package["clock"]["frames"]),
            )
            seed = _review_seed(
                review_id=f"final-acceptance-{index:02d}",
                candidate_label=f"Candidate {index} of {len(eligible_ids)}",
                audio=audio,
                bindings={
                    "readiness_result_sha256": readiness_snapshot["sha256"],
                    "readiness_result_document_sha256": readiness["document_sha256"],
                    "full_song_review_package_sha256": package_snapshot["sha256"],
                    "full_song_review_package_document_sha256": full_song_package[
                        "document_sha256"
                    ],
                    "variant_full_song_review_result_sha256": readiness["bindings"][
                        "variant_full_song_review_result_sha256"
                    ],
                    "variant_alignment_package_sha256": readiness["bindings"][
                        "variant_alignment_package_sha256"
                    ],
                },
            )
            seed_path = review_root / REVIEW_SEED_NAME
            html_path = review_root / REVIEW_HTML_NAME
            _write_json_exclusive(seed_path, seed)
            _write_text_exclusive(html_path, _review_html(seed))
            reviews.append(
                {
                    "review_id": seed["review_id"],
                    "variant_id": variant_id,
                    "candidate_label": seed["candidate_label"],
                    "directory": review_root.relative_to(temporary).as_posix(),
                    "seed": {
                        "path": REVIEW_SEED_NAME,
                        "sha256": _sha256(seed_path),
                        "bytes": seed_path.stat().st_size,
                        "document_sha256": seed["document_sha256"],
                        "package_commitment": seed["package_commitment"],
                    },
                    "html": {
                        "path": REVIEW_HTML_NAME,
                        "sha256": _sha256(html_path),
                        "bytes": html_path.stat().st_size,
                    },
                    "audio": audio,
                    "readiness": {
                        "independent_final_acceptance_review_complete": False,
                        "selected": False,
                        "accepted": False,
                        "product_route_enabled": False,
                        "publication_ready": False,
                    },
                }
            )

        current_readiness_snapshot, current_readiness = _verified_exact_readiness(
            readiness_result_path,
            full_song_review_result_path=full_song_review_result_path,
            reassessment_kwargs=reassessment_kwargs,
        )
        current_full_song_result_snapshot, current_full_song_result = (
            _verified_full_song_result(
                full_song_review_result_path, readiness=current_readiness
            )
        )
        current_package_snapshot, current_full_song_package = (
            _verified_full_song_package(
                full_song_root,
                readiness=current_readiness,
                full_song_result=current_full_song_result,
                soundfile=soundfile,
            )
        )
        if (
            current_readiness_snapshot["sha256"] != readiness_snapshot["sha256"]
            or current_readiness != readiness
            or current_full_song_result_snapshot["sha256"]
            != full_song_result_snapshot["sha256"]
            or current_full_song_result != full_song_result
            or current_package_snapshot["sha256"] != package_snapshot["sha256"]
            or current_full_song_package != full_song_package
        ):
            raise ValueError("private final acceptance review evidence changed")

        document: dict[str, Any] = {
            "schema": SCHEMA,
            "status": STATUS,
            "evidence_scope": "private_development_only",
            "bindings": {
                "readiness_result_sha256": readiness_snapshot["sha256"],
                "readiness_result_document_sha256": readiness["document_sha256"],
                "variant_full_song_review_result_sha256": readiness["bindings"][
                    "variant_full_song_review_result_sha256"
                ],
                "variant_alignment_package_sha256": readiness["bindings"][
                    "variant_alignment_package_sha256"
                ],
                "full_song_review_package_sha256": package_snapshot["sha256"],
                "full_song_review_package_document_sha256": full_song_package[
                    "document_sha256"
                ],
            },
            "clock": dict(readiness["clock"]),
            "eligible_variant_ids": eligible_ids,
            "eligible_variant_count": len(eligible_ids),
            "required_review_count": len(eligible_ids),
            "reviews": reviews,
            "readiness": {
                "final_human_acceptance_review_package_complete": True,
                "final_human_acceptance_reviews_complete": False,
                "variant_selected": False,
                "separator_accepted": False,
                "original_audible_joins_resolved": False,
                "product_route_enabled": False,
                "publication_ready": False,
            },
            "next_action": "complete_every_independent_final_acceptance_review",
            "interpretation": {
                "every_eligible_variant_included": True,
                "reviews_are_independent_not_comparative": True,
                "package_order_is_preference": False,
                "automatic_winner_selected": False,
                "package_creation_is_acceptance": False,
            },
            "permissions": dict(_FALSE_PERMISSIONS),
            "effects": dict(_PACKAGE_EFFECTS),
            "limitations": [
                "Each eligible variant is reviewed independently; this package is not a ranking exercise.",
                "The source and candidate audio are exact private copies of previously verified PCM24 evidence.",
                "Package creation records no human answer and accepts or selects no variant.",
                "Even a later private-pilot acceptance cannot by itself enable a product route or publication.",
                "Keep every evidence tree quiescent because JSON and WAV inputs are not one atomic snapshot.",
            ],
        }
        document["document_sha256"] = _document_sha256(document)
        _write_json_exclusive(temporary / REPORT_NAME, document)
        _verify_written_package(temporary, document)
        _make_private_tree(temporary)
        os.replace(temporary, destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return {
        **document,
        "report": str(destination / REPORT_NAME),
        "review_html": [
            str(destination / item["directory"] / item["html"]["path"])
            for item in reviews
        ],
        "output_directory": str(destination),
    }


def _verified_exact_readiness(
    readiness_result_path: str | Path,
    *,
    full_song_review_result_path: str | Path,
    reassessment_kwargs: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot = _load_private_json_snapshot(
        readiness_result_path, "private multi-variant readiness reassessment"
    )
    with tempfile.TemporaryDirectory(
        prefix="sunofriend-variant-final-acceptance-readiness-gate-"
    ) as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        derived = _reassess_private_candidate_followup_variant_readiness(
            full_song_review_result_path,
            out=root / "readiness.json",
            **reassessment_kwargs,
        )
        derived.pop("report", None)
    document = snapshot["document"]
    if (
        document != derived
        or document.get("schema") != READINESS_SCHEMA
        or document.get("status") != READINESS_STATUS
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("permissions") != _FALSE_PERMISSIONS
        or document.get("effects") != READINESS_EFFECTS
        or document.get("readiness", {}).get("variant_selected") is not False
        or document.get("readiness", {}).get("separator_accepted") is not False
    ):
        raise ValueError("private multi-variant readiness reassessment differs")
    return snapshot, document


def _eligible_variant_ids(readiness: Mapping[str, Any]) -> list[str]:
    reviewed = readiness.get("reviewed_variant_ids")
    summary = readiness.get("readiness")
    evidence = readiness.get("variant_evidence")
    if (
        not isinstance(reviewed, list)
        or not reviewed
        or len(reviewed) != len(set(reviewed))
        or not isinstance(summary, Mapping)
        or not isinstance(evidence, list)
        or len(evidence) != len(reviewed)
    ):
        raise ValueError("private final acceptance variant inventory differs")
    raw = summary.get("final_human_acceptance_review_eligible_variant_ids")
    if (
        not isinstance(raw, list)
        or not raw
        or len(raw) != len(set(raw))
        or summary.get("final_human_acceptance_review_eligible_variant_count")
        != len(raw)
        or summary.get("final_human_acceptance_review_complete") is not False
        or summary.get("variant_selected") is not False
        or summary.get("separator_accepted") is not False
        or summary.get("original_audible_joins_resolved") is not False
        or summary.get("product_route_enabled") is not False
        or summary.get("publication_ready") is not False
    ):
        raise ValueError("no variant is eligible for final human acceptance review")
    ordered = [variant_id for variant_id in reviewed if variant_id in raw]
    if ordered != raw:
        raise ValueError("private final acceptance eligible order differs")
    evidence_by_id = {item.get("variant_id"): item for item in evidence if isinstance(item, Mapping)}
    if list(evidence_by_id) != reviewed:
        raise ValueError("private final acceptance evidence inventory differs")
    for variant_id in reviewed:
        item = evidence_by_id[variant_id]
        expected = variant_id in ordered
        if (
            item.get("evidence", {}).get(
                "technical_and_listening_prerequisites_met"
            )
            is not expected
            or item.get("readiness", {}).get(
                "final_human_acceptance_review_eligible"
            )
            is not expected
            or item.get("readiness", {}).get("selected") is not False
            or item.get("readiness", {}).get("accepted") is not False
        ):
            raise ValueError("private final acceptance eligibility evidence differs")
    return ordered


def _verified_full_song_package(
    root: Path,
    *,
    readiness: Mapping[str, Any],
    full_song_result: Mapping[str, Any],
    soundfile: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot = _load_private_json_snapshot(
        root / FULL_SONG_PACKAGE_REPORT_NAME,
        "private eligible-variant full-song review package",
    )
    document = snapshot["document"]
    if (
        document.get("schema") != FULL_SONG_PACKAGE_SCHEMA
        or document.get("status") != FULL_SONG_PACKAGE_STATUS
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("eligible_variant_ids") != readiness.get("reviewed_variant_ids")
        or document.get("eligible_variant_count")
        != len(readiness.get("reviewed_variant_ids", []))
        or document.get("bindings", {}).get("variant_review_result_sha256")
        != full_song_result.get("bindings", {}).get("variant_review_result_sha256")
        or document.get("bindings", {}).get(
            "variant_review_result_document_sha256"
        )
        != full_song_result.get("bindings", {}).get(
            "variant_review_result_document_sha256"
        )
        or document.get("document_sha256")
        != full_song_result.get("bindings", {}).get(
            "variant_full_song_review_package_document_sha256"
        )
        or snapshot["sha256"]
        != full_song_result.get("bindings", {}).get(
            "variant_full_song_review_package_report_sha256"
        )
        or document.get("permissions") != _FALSE_PERMISSIONS
        or document.get("effects", {}).get("candidate_selected") is not False
        or document.get("effects", {}).get("candidate_accepted") is not False
        or any(
            item.get("readiness", {}).get("selected") is not False
            or item.get("readiness", {}).get("accepted") is not False
            for item in document.get("variant_packages", [])
        )
    ):
        raise ValueError("private eligible-variant full-song package differs")
    _verify_parent_package(root, document, soundfile=soundfile)
    return snapshot, document


def _verified_full_song_result(
    path: str | Path, *, readiness: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot = _load_private_json_snapshot(
        path, "private eligible-variant full-song review result"
    )
    document = snapshot["document"]
    if (
        document.get("schema") != FULL_SONG_RESULT_SCHEMA
        or document.get("status") != FULL_SONG_RESULT_STATUS
        or document.get("document_sha256") != _document_sha256(document)
        or snapshot["sha256"]
        != readiness.get("bindings", {}).get(
            "variant_full_song_review_result_sha256"
        )
        or document.get("document_sha256")
        != readiness.get("bindings", {}).get(
            "variant_full_song_review_result_document_sha256"
        )
        or document.get("reviewed_variant_ids")
        != readiness.get("reviewed_variant_ids")
        or document.get("permissions") != _FALSE_PERMISSIONS
        or document.get("readiness_evidence", {}).get("variant_selected") is not False
    ):
        raise ValueError("private eligible-variant full-song review result differs")
    return snapshot, document


def _copy_exact_audio(
    source_root: Path,
    artifacts: Mapping[str, Any],
    *,
    review_root: Path,
    expected_frames: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for role in _ROLES:
        record = artifacts.get(role)
        if not isinstance(record, Mapping):
            raise ValueError("private final acceptance audio inventory differs")
        source = source_root / str(record.get("path", ""))
        _require_private_regular(source, f"private final acceptance {role} source")
        _read_pcm24_snapshot(
            source,
            record,
            expected_frames=expected_frames,
            label=f"private final acceptance {role} source",
        )
        target = review_root / f"audio/{role}.wav"
        with source.open("rb") as reader, target.open("xb") as writer:
            shutil.copyfileobj(reader, writer, length=1024 * 1024)
            writer.flush()
            os.fsync(writer.fileno())
        target.chmod(0o600)
        observed = _read_pcm24_snapshot(
            target,
            record,
            expected_frames=expected_frames,
            label=f"private final acceptance copied {role} audio",
        )
        result[role] = {
            "path": f"audio/{role}.wav",
            "sha256": observed["sha256"],
            "bytes": observed["bytes"],
            "geometry": dict(record["geometry"]),
            "pcm24_int32_sequence_sha256": observed[
                "pcm24_int32_sequence_sha256"
            ],
        }
    return result


def _review_seed(
    *,
    review_id: str,
    candidate_label: str,
    audio: Mapping[str, Any],
    bindings: Mapping[str, Any],
) -> dict[str, Any]:
    immutable = {
        "schema": REVIEW_SCHEMA,
        "review_id": review_id,
        "candidate_label": candidate_label,
        "question": (
            "After hearing the complete source and all three outputs, is this "
            "exact candidate suitable for a private Sunofriend pilot?"
        ),
        "instructions": [
            "Listen from the beginning, middle and end of every complete track.",
            "Judge this candidate independently; do not rank it against another page.",
            "Cannot tell and needs more work are valid outcomes.",
            "This review does not publish or enable the separator.",
        ],
        "questions": [dict(item) for item in _QUESTION_SPECS],
        "audio": {role: dict(audio[role]) for role in _ROLES},
        "bindings": dict(bindings),
    }
    package_commitment = _document_sha256(immutable)
    document: dict[str, Any] = {
        **immutable,
        "package_commitment": package_commitment,
        "status": REVIEW_STATUS,
        "heard": {role: False for role in _ROLES},
        "ratings": {item["id"]: None for item in _QUESTION_SPECS},
        "notes": "",
        "summary": {"complete": False, "answered_questions": 0},
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_REVIEW_EFFECTS),
    }
    document["document_sha256"] = _document_sha256(document)
    return document


def _review_html(document: Mapping[str, Any]) -> str:
    seed = json.dumps(document, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sunofriend final stem-separation acceptance review</title><style>
body{{margin:0;background:#08111d;color:#e8f1ff;font:18px/1.5 system-ui,sans-serif}}main{{max-width:1080px;margin:auto;padding:32px}}
.privacy{{background:#104a32;padding:12px 24px;font-weight:700}}.card{{background:#101e2c;border:1px solid #29435b;border-radius:18px;padding:24px;margin:22px 0}}
h1{{font-size:42px}}h2{{color:#63d7ff}}audio{{width:100%;margin:8px 0 10px}}label{{display:block;margin:9px 0}}textarea{{width:100%;min-height:100px;background:#0a1724;color:#fff;border:1px solid #3b607d;border-radius:8px}}
button{{background:#1d789c;color:#fff;border:0;border-radius:9px;padding:14px 20px;font-size:17px;margin-right:10px}}button:disabled{{opacity:.45}}.status{{color:#ffd253;font-weight:700}}.hint{{color:#b7c9da}}
</style></head><body><div class="privacy">Private local developer review - no audio or review is uploaded</div><main>
<section class="card"><h1>Final stem-separation acceptance review</h1><h2>{html.escape(str(document['candidate_label']))}</h2><p>{html.escape(str(document['question']))}</p>
<p>This page is independent, not a comparison or ranking. Listen to the beginning, middle and end. A negative or uncertain answer is useful evidence.</p><p class="status" id="progress">Not complete</p></section>
<section class="card"><h2>1. Hear all complete tracks</h2><div id="audio"></div></section>
<section class="card"><h2>2. Answer four acceptance questions</h2><div id="questions"></div><p>Optional private notes</p><textarea id="notes" maxlength="2000"></textarea></section>
<section class="card"><button id="complete">Mark review complete</button><button id="export" disabled>Export reviewed JSON</button><p id="message"></p></section>
<script id="seed" type="application/json">{seed}</script><script>
const review=JSON.parse(document.getElementById('seed').textContent);const audio=document.getElementById('audio');const questions=document.getElementById('questions');
for(const role of ['source','vocals','instrumental','reconstruction']){{const box=document.createElement('div');box.innerHTML=`<h3>${{role.replace('_',' ')}}</h3><audio controls preload="metadata" src="${{review.audio[role].path}}"></audio><label><input type="checkbox" data-heard="${{role}}"> I heard the complete ${{role.replace('_',' ')}} track</label>`;box.querySelector('input').onchange=e=>{{review.heard[role]=e.target.checked;update();}};audio.appendChild(box);}}
review.questions.forEach((question,index)=>{{const box=document.createElement('div');box.innerHTML=`<h3>${{index+1}}. ${{question.prompt}}</h3>`;for(const choice of question.choices){{const label=document.createElement('label');label.innerHTML=`<input type="radio" name="question-${{index}}" value="${{choice}}"> ${{choice.replaceAll('_',' ')}}`;label.querySelector('input').onchange=e=>{{review.ratings[question.id]=e.target.value;update();}};box.appendChild(label);}}questions.appendChild(box);}});
document.getElementById('notes').oninput=e=>review.notes=e.target.value;
function update(){{const heard=Object.values(review.heard).every(Boolean);const answered=Object.values(review.ratings).filter(Boolean).length;review.summary.answered_questions=answered;document.getElementById('progress').textContent=`Heard ${{Object.values(review.heard).filter(Boolean).length}} of 4 tracks; answered ${{answered}} of 4 questions`;return heard&&answered===4;}}
document.getElementById('complete').onclick=()=>{{if(!update()){{document.getElementById('message').textContent='Hear every complete track and answer all four questions first.';return;}}review.status='reviewed';review.summary.complete=true;document.getElementById('export').disabled=false;document.getElementById('message').textContent='Complete. Export this reviewed JSON.';}};
document.getElementById('export').onclick=()=>{{if(review.status!=='reviewed')return;const blob=new Blob([JSON.stringify(review,null,2)+'\\n'],{{type:'application/json'}});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='final_acceptance_review.reviewed.json';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);}};update();
</script></main></body></html>"""


def _write_text_exclusive(path: Path, value: str) -> None:
    payload = value.encode("utf-8")
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
                raise RuntimeError("private final acceptance write made no progress")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _verify_written_package(root: Path, document: Mapping[str, Any]) -> None:
    report = root / REPORT_NAME
    _require_private_regular(report, "private final acceptance package report")
    if json.loads(report.read_text(encoding="utf-8")) != document:
        raise ValueError("private final acceptance package report differs")
    if (
        len(document["reviews"]) != document["required_review_count"]
        or [item["variant_id"] for item in document["reviews"]]
        != document["eligible_variant_ids"]
    ):
        raise ValueError("private final acceptance review inventory differs")
    for item in document["reviews"]:
        review_root = root / item["directory"]
        seed_path = review_root / item["seed"]["path"]
        html_path = review_root / item["html"]["path"]
        for path, record in ((seed_path, item["seed"]), (html_path, item["html"])):
            _require_private_regular(path, "private final acceptance review artifact")
            if _sha256(path) != record["sha256"] or path.stat().st_size != record["bytes"]:
                raise ValueError("private final acceptance review artifact differs")
        seed = json.loads(seed_path.read_text(encoding="utf-8"))
        if (
            seed.get("schema") != REVIEW_SCHEMA
            or seed.get("status") != REVIEW_STATUS
            or seed.get("document_sha256") != _document_sha256(seed)
            or seed.get("package_commitment") != item["seed"]["package_commitment"]
            or seed.get("permissions") != _FALSE_PERMISSIONS
            or seed.get("effects") != _REVIEW_EFFECTS
            or item["variant_id"] in html_path.read_text(encoding="utf-8")
        ):
            raise ValueError("private final acceptance review seed differs")
        for role, record in item["audio"].items():
            path = review_root / record["path"]
            _read_pcm24_snapshot(
                path,
                record,
                expected_frames=int(document["clock"]["frames"]),
                label=f"private final acceptance packaged {role} audio",
            )


__all__: tuple[str, ...] = ()
