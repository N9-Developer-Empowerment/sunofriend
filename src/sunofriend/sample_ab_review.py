"""Blinded performance review for completed Sample Instrument v3 packs."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Sequence


SAMPLE_AB_REVIEW_SCHEMA = "sunofriend.sample-ab-review.v1"
SAMPLE_AB_ANSWER_KEY_SCHEMA = "sunofriend.sample-ab-answer-key.v1"
SAMPLE_AB_RESULT_SCHEMA = "sunofriend.sample-ab-result.v1"
SAMPLE_INSTRUMENT_V3_SCHEMA = "sunofriend.sample-instrument-v3.v1"
CHOICES = {"candidate_a", "candidate_b", "equivalent", "neither"}


def create_sample_ab_review(
    sample_pack_dirs: Sequence[str | Path],
    *,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Create one blinded v2/v3 performance page without changing a pack."""

    if not sample_pack_dirs:
        raise ValueError("At least one completed Sample Instrument v3 is required")
    sources = [Path(value).expanduser().resolve() for value in sample_pack_dirs]
    destination = Path(out_dir).expanduser()
    if destination.exists():
        raise ValueError(f"Output directory already exists: {destination}")
    records = [_read_source_pack(path) for path in sources]
    destination.parent.mkdir(parents=True, exist_ok=True)
    work = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.building-", dir=destination.parent
        )
    )
    try:
        audio_dir = work / "audio"
        audio_dir.mkdir()
        units: list[dict[str, Any]] = []
        answer_units: list[dict[str, Any]] = []
        manifest_files: list[dict[str, Any]] = []
        source_records: list[dict[str, Any]] = []
        used_ids: set[str] = set()
        for index, (source, report, report_hash) in enumerate(records, 1):
            kind = _slug(str(report.get("kind") or f"instrument-{index}"))
            unit_id = f"{index:02d}-{kind}"
            if unit_id in used_ids:
                raise ValueError(f"Duplicate blinded review unit: {unit_id}")
            used_ids.add(unit_id)
            performance = report.get("performance_audition") or {}
            mapping = _blind_mapping(report_hash, unit_id)
            copied = _copy_performance_audio(
                source,
                performance,
                audio_dir=audio_dir,
                unit_id=unit_id,
                mapping=mapping,
                manifest_files=manifest_files,
            )
            sweep = report.get("velocity_sweep") or None
            sweep_copy = (
                _copy_sweep_audio(
                    source,
                    sweep,
                    audio_dir=audio_dir,
                    unit_id=unit_id,
                    mapping=mapping,
                    manifest_files=manifest_files,
                )
                if sweep
                else None
            )
            units.append(
                {
                    "unit_id": unit_id,
                    "kind": str(report.get("kind") or "unknown"),
                    "instrument_name": str(
                        report.get("instrument_name") or source.name
                    ),
                    "source_reference": copied["source"],
                    "candidate_a": copied["candidate_a"],
                    "candidate_b": copied["candidate_b"],
                    "velocity_sweep": sweep_copy,
                    "performance": {
                        "bars": performance.get("bars"),
                        "bpm": performance.get("initial_bpm"),
                        "note_count": performance.get("note_count"),
                        "pitches": performance.get("selected_pitches"),
                        "velocity_range": [
                            performance.get("velocity_min"),
                            performance.get("velocity_max"),
                        ],
                    },
                    "choice": None,
                    "notes": "",
                }
            )
            answer_units.append(
                {
                    "unit_id": unit_id,
                    "candidate_a": mapping["candidate_a"],
                    "candidate_b": mapping["candidate_b"],
                    "v3_report_sha256": report_hash,
                }
            )
            source_records.append(
                {
                    "unit_id": unit_id,
                    "kind": str(report.get("kind") or "unknown"),
                    "path": str(source),
                    "report": str(source / "sample_pack_v3.json"),
                    "report_sha256": report_hash,
                    "review_sha256": (report.get("review") or {}).get("sha256"),
                    "source_midi_sha256": performance.get("source_midi_sha256"),
                    "source_midi_mutated": performance.get("source_midi_mutated"),
                }
            )

        answer_key = {
            "schema": SAMPLE_AB_ANSWER_KEY_SCHEMA,
            "operation": "sample-pack-ab-answer-key",
            "status": "complete",
            "policy": "One candidate is the immutable v2 bank and one is the explicitly reviewed v3 bank; the HTML does not embed this mapping.",
            "units": answer_units,
        }
        answer_path = work / "sample_ab_answer_key.json"
        _write_json(answer_path, answer_key)
        answer_hash = _file_sha256(answer_path)

        manifest = {
            "schema": "sunofriend.sample-ab-audio-manifest.v1",
            "operation": "sample-pack-ab-review-audio",
            "file_count": len(manifest_files),
            "files": manifest_files,
            "effects": {
                "source_files_changed": 0,
                "midi_notes_changed": 0,
                "sampler_zones_changed": 0,
            },
        }
        manifest_path = work / "sample_ab_audio_manifest.json"
        _write_json(manifest_path, manifest)
        manifest_hash = _file_sha256(manifest_path)

        seed = {
            "schema": SAMPLE_AB_REVIEW_SCHEMA,
            "operation": "sample-pack-ab-review",
            "status": "unreviewed",
            "review_required": True,
            "blind": True,
            "policy": {
                "question": "Which candidate is closer to the source or more musically useful?",
                "choices": sorted(CHOICES),
                "candidate_identity_hidden_in_html": True,
                "source_reference_is_not_a_candidate": True,
                "velocity_sweep_uses_same_candidate_mapping": True,
            },
            "source_packs": source_records,
            "review_evidence": {
                "directory": str(destination.resolve()),
                "manifest": str(
                    destination.resolve() / "sample_ab_audio_manifest.json"
                ),
                "manifest_sha256": manifest_hash,
                "audio_file_count": len(manifest_files),
            },
            "answer_key": {
                "path": str(destination.resolve() / "sample_ab_answer_key.json"),
                "sha256": answer_hash,
                "embedded_in_html": False,
            },
            "summary": {
                "unit_count": len(units),
                "reviewed_unit_count": 0,
                "velocity_sweep_unit_count": sum(
                    row["velocity_sweep"] is not None for row in units
                ),
            },
            "units": units,
            "effects": {
                "source_files_changed": 0,
                "midi_notes_changed": 0,
                "midi_velocities_changed": 0,
                "sampler_zones_changed": 0,
                "review_choices_inferred": 0,
            },
            "artifacts": {
                "html": "sample_ab_review.html",
                "seed": "sample_ab_review.seed.json",
                "answer_key": "sample_ab_answer_key.json",
                "audio_manifest": "sample_ab_audio_manifest.json",
                "audio": "audio",
            },
            "warnings": [
                "Candidate A/B identity is intentionally absent from the HTML; do not open the answer key before reviewing.",
                "FluidSynth renders are listening proxies for GarageBand/AUSampler, not replacements for a final DAW check.",
                "Equivalent, neither and rejection outcomes are valid Phase 3 evidence.",
            ],
        }
        _write_json(work / "sample_ab_review.seed.json", seed)
        (work / "sample_ab_review.html").write_text(
            _review_html(seed), encoding="utf-8"
        )
        work.replace(destination)
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise
    return {
        "status": "complete",
        "schema": SAMPLE_AB_REVIEW_SCHEMA,
        "out_dir": str(destination),
        "unit_count": len(units),
        "velocity_sweep_unit_count": seed["summary"]["velocity_sweep_unit_count"],
        "html": str(destination / "sample_ab_review.html"),
        "seed": str(destination / "sample_ab_review.seed.json"),
        "answer_key": str(destination / "sample_ab_answer_key.json"),
        "answer_key_sha256": answer_hash,
        "audio_manifest_sha256": manifest_hash,
        "effects": seed["effects"],
    }


def resolve_sample_ab_review(
    review_path: str | Path,
    *,
    out: str | Path,
) -> dict[str, Any]:
    """Resolve a completed blind export against its separate pinned key."""

    review_file = Path(review_path).expanduser().resolve()
    output = Path(out).expanduser()
    if output.exists():
        raise ValueError(f"Output file already exists: {output}")
    review = _read_json(review_file)
    if review.get("schema") != SAMPLE_AB_REVIEW_SCHEMA:
        raise ValueError("Unsupported sample A/B review schema")
    if review.get("status") != "reviewed":
        raise ValueError("Sample A/B review is not complete")
    if review.get("blind") is not True:
        raise ValueError("Sample A/B review no longer records a blind comparison")
    units = list(review.get("units") or [])
    if not units or len(units) != int(
        (review.get("summary") or {}).get("unit_count", -1)
    ):
        raise ValueError("Sample A/B review unit count is invalid")
    if int((review.get("summary") or {}).get("reviewed_unit_count", -1)) != len(units):
        raise ValueError("Sample A/B review is not marked complete for every unit")
    unit_ids = [str(row.get("unit_id")) for row in units]
    if len(set(unit_ids)) != len(unit_ids):
        raise ValueError("Sample A/B review contains duplicate units")
    for row in units:
        if row.get("choice") not in CHOICES:
            raise ValueError(
                f"Sample A/B unit {row.get('unit_id')} has no valid choice"
            )
    effects = review.get("effects") or {}
    if any(int(value) != 0 for value in effects.values()):
        raise ValueError("Sample A/B review declares an automatic effect")
    source_hashes = _verify_review_sources(review, expected_unit_ids=set(unit_ids))
    _verify_review_audio(review)
    key_record = review.get("answer_key") or {}
    key_path = Path(str(key_record.get("path", ""))).expanduser().resolve()
    if not key_path.is_file() or _file_sha256(key_path) != key_record.get("sha256"):
        raise ValueError("Sample A/B answer key changed or is missing")
    key = _read_json(key_path)
    if (
        key.get("schema") != SAMPLE_AB_ANSWER_KEY_SCHEMA
        or key.get("status") != "complete"
    ):
        raise ValueError("Unsupported sample A/B answer key")
    key_units = {str(row["unit_id"]): row for row in key.get("units", [])}
    if set(key_units) != set(unit_ids):
        raise ValueError("Sample A/B answer key units do not match the review")
    for unit_id, row in key_units.items():
        if {row.get("candidate_a"), row.get("candidate_b")} != {"v2", "v3"}:
            raise ValueError(f"Sample A/B answer mapping is invalid for {unit_id}")
        if row.get("v3_report_sha256") != source_hashes[unit_id]:
            raise ValueError(f"Sample A/B answer key source changed for {unit_id}")
    resolved: list[dict[str, Any]] = []
    counts = {"v2": 0, "v3": 0, "equivalent": 0, "neither": 0}
    for row in units:
        unit_id = str(row["unit_id"])
        choice = str(row["choice"])
        key_row = key_units[unit_id]
        if choice == "candidate_a":
            outcome = str(key_row["candidate_a"])
        elif choice == "candidate_b":
            outcome = str(key_row["candidate_b"])
        else:
            outcome = choice
        if outcome not in counts:
            raise ValueError(f"Invalid resolved A/B outcome for {unit_id}: {outcome}")
        counts[outcome] += 1
        resolved.append(
            {
                "unit_id": unit_id,
                "kind": row.get("kind"),
                "choice": choice,
                "outcome": outcome,
                "notes": str(row.get("notes") or ""),
                "v3_preferred": outcome == "v3",
                "v2_preferred": outcome == "v2",
            }
        )
    result = {
        "schema": SAMPLE_AB_RESULT_SCHEMA,
        "operation": "sample-pack-ab-resolve",
        "status": "complete",
        "blind_review": True,
        "review": {
            "path": str(review_file),
            "sha256": _file_sha256(review_file),
        },
        "answer_key": {
            "path": str(key_path),
            "sha256": _file_sha256(key_path),
        },
        "summary": {
            "unit_count": len(resolved),
            "v2_preferred_count": counts["v2"],
            "v3_preferred_count": counts["v3"],
            "equivalent_count": counts["equivalent"],
            "neither_count": counts["neither"],
        },
        "units": resolved,
        "effects": {
            "source_files_changed": 0,
            "midi_notes_changed": 0,
            "midi_velocities_changed": 0,
            "sampler_zones_changed": 0,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, result)
    return result


def _read_source_pack(path: Path) -> tuple[Path, dict[str, Any], str]:
    if not path.is_dir():
        raise ValueError(f"Sample Instrument v3 directory not found: {path}")
    report_path = path / "sample_pack_v3.json"
    if not report_path.is_file():
        raise ValueError(f"Sample Instrument v3 report not found: {report_path}")
    report = _read_json(report_path)
    if (
        report.get("schema") != SAMPLE_INSTRUMENT_V3_SCHEMA
        or report.get("status") != "complete"
    ):
        raise ValueError(f"Completed Sample Instrument v3 required: {path}")
    performance = report.get("performance_audition") or {}
    required = {
        "source_reference_wav": "source_reference_sha256",
        "v2_preview_wav": "v2_preview_sha256",
        "v3_preview_wav": "v3_preview_sha256",
    }
    for path_key, hash_key in required.items():
        artifact = path / str(performance.get(path_key, ""))
        if not artifact.is_file() or _file_sha256(artifact) != performance.get(
            hash_key
        ):
            raise ValueError(
                f"Sample Instrument v3 performance evidence changed: {artifact}"
            )
    if performance.get("source_midi_mutated") is not False:
        raise ValueError(
            f"Sample Instrument v3 does not prove immutable source MIDI: {path}"
        )
    return path, report, _file_sha256(report_path)


def _blind_mapping(report_hash: str, unit_id: str) -> dict[str, str]:
    value = hashlib.sha256(f"{report_hash}:{unit_id}:phase3-ab-v1".encode()).digest()[0]
    if value % 2:
        return {"candidate_a": "v3", "candidate_b": "v2"}
    return {"candidate_a": "v2", "candidate_b": "v3"}


def _copy_performance_audio(
    root: Path,
    performance: dict[str, Any],
    *,
    audio_dir: Path,
    unit_id: str,
    mapping: dict[str, str],
    manifest_files: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    versions = {
        "v2": (
            str(performance["v2_preview_wav"]),
            str(performance["v2_preview_sha256"]),
        ),
        "v3": (
            str(performance["v3_preview_wav"]),
            str(performance["v3_preview_sha256"]),
        ),
    }
    result: dict[str, dict[str, Any]] = {}
    result["source"] = _copy_audio(
        root / str(performance["source_reference_wav"]),
        audio_dir / f"{unit_id}-source.wav",
        expected_hash=str(performance["source_reference_sha256"]),
        purpose="source-reference",
        manifest_files=manifest_files,
    )
    for label in ("candidate_a", "candidate_b"):
        relative, expected = versions[mapping[label]]
        result[label] = _copy_audio(
            root / relative,
            audio_dir / f"{unit_id}-{label[-1]}.wav",
            expected_hash=expected,
            purpose=f"blinded-{label}",
            manifest_files=manifest_files,
        )
    return result


def _copy_sweep_audio(
    root: Path,
    sweep: dict[str, Any],
    *,
    audio_dir: Path,
    unit_id: str,
    mapping: dict[str, str],
    manifest_files: list[dict[str, Any]],
) -> dict[str, Any]:
    versions = {
        "v2": (str(sweep["v2_preview_wav"]), str(sweep["v2_preview_sha256"])),
        "v3": (str(sweep["v3_preview_wav"]), str(sweep["v3_preview_sha256"])),
    }
    result: dict[str, Any] = {
        "label": "Velocity sweep using the same hidden Candidate A/B mapping",
        "boundary_units": sweep.get("units"),
    }
    for label in ("candidate_a", "candidate_b"):
        relative, expected = versions[mapping[label]]
        result[label] = _copy_audio(
            root / relative,
            audio_dir / f"{unit_id}-sweep-{label[-1]}.wav",
            expected_hash=expected,
            purpose=f"blinded-sweep-{label}",
            manifest_files=manifest_files,
        )
    return result


def _copy_audio(
    source: Path,
    destination: Path,
    *,
    expected_hash: str,
    purpose: str,
    manifest_files: list[dict[str, Any]],
) -> dict[str, Any]:
    if not source.is_file() or _file_sha256(source) != expected_hash:
        raise ValueError(f"Pinned A/B source audio changed: {source}")
    shutil.copy2(source, destination)
    digest = _file_sha256(destination)
    relative = str(Path("audio") / destination.name)
    manifest_files.append({"path": relative, "sha256": digest, "purpose": purpose})
    return {"audio": relative, "sha256": digest}


def _verify_review_sources(
    review: dict[str, Any], *, expected_unit_ids: set[str]
) -> dict[str, str]:
    rows = list(review.get("source_packs") or [])
    unit_ids = [str(row.get("unit_id")) for row in rows]
    if set(unit_ids) != expected_unit_ids or len(unit_ids) != len(set(unit_ids)):
        raise ValueError("Reviewed Sample Instrument v3 units do not match")
    hashes: dict[str, str] = {}
    for row in rows:
        report = Path(str(row.get("report", ""))).expanduser().resolve()
        if not report.is_file() or _file_sha256(report) != row.get("report_sha256"):
            raise ValueError(f"Reviewed Sample Instrument v3 changed: {report}")
        if row.get("source_midi_mutated") is not False:
            raise ValueError(f"Reviewed source MIDI is not immutable: {report}")
        hashes[str(row["unit_id"])] = str(row["report_sha256"])
    return hashes


def _verify_review_audio(review: dict[str, Any]) -> None:
    evidence = review.get("review_evidence") or {}
    directory = Path(str(evidence.get("directory", ""))).expanduser().resolve()
    manifest_path = Path(str(evidence.get("manifest", ""))).expanduser().resolve()
    if not manifest_path.is_file() or _file_sha256(manifest_path) != evidence.get(
        "manifest_sha256"
    ):
        raise ValueError("Sample A/B audio manifest changed or is missing")
    manifest = _read_json(manifest_path)
    files = list(manifest.get("files") or [])
    if len(files) != int(evidence.get("audio_file_count", -1)):
        raise ValueError("Sample A/B audio count does not match its manifest")
    manifest_rows = {str(row.get("path")): row for row in files}
    if len(manifest_rows) != len(files):
        raise ValueError("Sample A/B audio manifest contains duplicate paths")
    for row in files:
        path = directory / str(row.get("path", ""))
        if not path.is_file() or _file_sha256(path) != row.get("sha256"):
            raise ValueError(f"Sample A/B review audio changed: {path}")
    referenced: set[str] = set()
    for unit in review.get("units", []):
        records = [
            unit.get("source_reference") or {},
            unit.get("candidate_a") or {},
            unit.get("candidate_b") or {},
        ]
        sweep = unit.get("velocity_sweep") or None
        if sweep:
            records.extend(
                [sweep.get("candidate_a") or {}, sweep.get("candidate_b") or {}]
            )
        for record in records:
            relative = str(record.get("audio", ""))
            expected = manifest_rows.get(relative)
            if expected is None or record.get("sha256") != expected.get("sha256"):
                raise ValueError("Sample A/B page audio references changed")
            referenced.add(relative)
    if referenced != set(manifest_rows):
        raise ValueError("Sample A/B page audio references do not match the manifest")


def _review_html(seed: dict[str, Any]) -> str:
    payload = json.dumps(seed, sort_keys=True).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sunofriend blinded instrument review</title>
<style>
body{{font-family:system-ui,sans-serif;background:#101820;color:#edf4f8;margin:0;padding:2rem;line-height:1.45}}main{{max-width:1050px;margin:auto}}.card{{background:#192631;border:1px solid #405565;border-radius:16px;padding:1.3rem;margin:1rem 0}}.players{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1rem}}audio{{width:100%}}label{{display:block;margin:.5rem 0}}button{{font-size:1rem;padding:.75rem 1rem;margin:.4rem;border-radius:9px;border:0;background:#2d638c;color:white}}textarea{{width:100%;min-height:4rem;background:#0e1720;color:white;border:1px solid #60798c;border-radius:8px}}code{{color:#8fd3ff}}.status{{color:#ffd166;font-size:1.2rem}}.sweep{{border-top:1px solid #405565;margin-top:1rem;padding-top:1rem}}</style>
</head><body><main><h1>Sunofriend blinded instrument review</h1>
<p>Use the source only as a reference. One candidate is the unchanged v2 bank and one is the explicitly reviewed v3 bank; their identities are hidden. Compare musical usefulness, attack, body, texture and consistency—not loudness alone. Equivalent and neither are valid outcomes.</p>
<p class="status" id="status">Reviewed 0 of {len(seed["units"])} instruments</p><div id="units"></div>
<button id="mark">Mark all choices reviewed</button><button id="export">Export reviewed JSON</button>
<p>The separate answer key is hash-pinned but intentionally not shown on this page.</p>
<script>
const review={payload};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const root=document.getElementById('units');
review.units.forEach((u,i)=>{{const card=document.createElement('section');card.className='card';card.dataset.i=i;const sweep=u.velocity_sweep?`<div class="sweep"><h3>Velocity sweep</h3><div class="players"><div><b>Candidate A sweep</b><audio controls preload="none" src="${{esc(u.velocity_sweep.candidate_a.audio)}}"></audio></div><div><b>Candidate B sweep</b><audio controls preload="none" src="${{esc(u.velocity_sweep.candidate_b.audio)}}"></audio></div></div></div>`:'';card.innerHTML=`<h2>${{esc(u.kind)}} — ${{esc(u.instrument_name)}}</h2><p>${{u.performance.note_count}} notes; pitches ${{esc((u.performance.pitches||[]).join(', '))}}; velocities ${{esc((u.performance.velocity_range||[]).join('–'))}}</p><div class="players"><div><b>Source reference</b><audio controls preload="none" src="${{esc(u.source_reference.audio)}}"></audio></div><div><b>Candidate A</b><audio controls preload="none" src="${{esc(u.candidate_a.audio)}}"></audio></div><div><b>Candidate B</b><audio controls preload="none" src="${{esc(u.candidate_b.audio)}}"></audio></div></div>${{sweep}}<h3>Which is closer or more musically useful?</h3><label><input type="radio" name="choice-${{i}}" value="candidate_a"> Candidate A</label><label><input type="radio" name="choice-${{i}}" value="candidate_b"> Candidate B</label><label><input type="radio" name="choice-${{i}}" value="equivalent"> Equivalent / no clear preference</label><label><input type="radio" name="choice-${{i}}" value="neither"> Neither is useful</label><label>Optional listening note<textarea></textarea></label>`;root.appendChild(card);}});
function sync(){{review.units.forEach((u,i)=>{{const card=root.querySelector(`[data-i="${{i}}"]`);const chosen=card.querySelector('input[type=radio]:checked');u.choice=chosen?chosen.value:null;u.notes=card.querySelector('textarea').value;}});review.summary.reviewed_unit_count=review.units.filter(u=>u.choice).length;document.getElementById('status').textContent=`Reviewed ${{review.summary.reviewed_unit_count}} of ${{review.summary.unit_count}} instruments`;}}
root.addEventListener('change',sync);root.addEventListener('input',sync);
document.getElementById('mark').addEventListener('click',()=>{{sync();if(review.summary.reviewed_unit_count!==review.summary.unit_count){{alert('Choose one outcome for every instrument.');return;}}review.status='reviewed';document.getElementById('status').textContent=`Reviewed all ${{review.summary.unit_count}} instruments`;}});
document.getElementById('export').addEventListener('click',()=>{{sync();if(review.status!=='reviewed'){{alert('Mark all choices reviewed before exporting.');return;}}const blob=new Blob([JSON.stringify(review,null,2)+'\\n'],{{type:'application/json'}});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='sample_ab_review.reviewed.json';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);}});
</script></main></body></html>"""


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return result or "instrument"


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


__all__ = [
    "SAMPLE_AB_ANSWER_KEY_SCHEMA",
    "SAMPLE_AB_RESULT_SCHEMA",
    "SAMPLE_AB_REVIEW_SCHEMA",
    "create_sample_ab_review",
    "resolve_sample_ab_review",
]
