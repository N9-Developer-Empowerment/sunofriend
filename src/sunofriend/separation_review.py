"""Human-listening handoff and bound local review contract for separation."""

from __future__ import annotations

import html
import json
import re
from typing import Any, Mapping, Sequence


REVIEW_SCHEMA = "sunofriend.experimental-separation-review.v3"
USEFULNESS_VALUES = {
    "useful",
    "useful_with_limitations",
    "not_useful",
    "cannot_tell",
    "not_tested",
}
ISSUE_VALUES = {
    "bleed",
    "missing_content",
    "artefacts",
    "timing",
    "join_problem",
    "none_observed",
    "cannot_tell",
    "not_tested",
}
MIDI_VALUES = {"improved", "no_change", "worse", "cannot_tell", "not_tested"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def render_start_here(report: Mapping[str, Any]) -> str:
    roles = _role_details(report)
    truth = _activation_truth_details(report)
    lines = [
        "SUNOFRIEND EXPERIMENTAL STEM SEPARATION",
        "",
        "1. Open REVIEW/separation_review.html in a normal browser.",
        "2. Compare SOURCE/source-reference.wav with every file in STEMS/.",
        "3. Judge usefulness, bleed, missing sound, artefacts, timing and joins.",
        "4. AUDIO/reconstruction-check.wav checks accounting, not separation accuracy.",
        "5. Export a bound private review; cannot_tell and not_tested are valid.",
        "6. Only you decide whether useful stems enter a separate MIDI/Create run.",
        "",
        "What this preview made:",
    ]
    lines.extend(f"- {role['path']}: {role['summary']}" for role in roles)
    if truth:
        lines.append("- GROUND-TRUTH/: copyright-safe synthetic role references for this activation canary")
    lines.extend(
        [
            "- SOURCE/source-reference.wav: level-managed local reference",
            "- AUDIO/reconstruction-check.wav: sum of the persisted stems",
            "",
            "Important: these are unreviewed estimates, not ground truth. No audio was uploaded.",
            "Poor or mixed usefulness feedback is recorded; it does not silently disable the last functioning profile.",
            f"Optional text-only feedback: {report['feedback']['public_report_url']}",
            "Do not attach private music, stems, review JSON, filenames or metadata to a public issue.",
            "",
        ]
    )
    return "\n".join(lines)


def render_review_html(report: Mapping[str, Any]) -> str:
    roles = _role_details(report)
    truth = _activation_truth_details(report)
    binding = _report_binding(report)
    source_name = html.escape(str(report["source"]["name"]))
    feedback = html.escape(str(report["feedback"]["public_report_url"]), quote=True)
    truth_sections = "".join(
        _truth_role_section(index + 2, role, value)
        for index, (role, value) in enumerate(truth.items())
    )
    estimate_start = 2 + len(truth)
    role_sections = "".join(
        _role_section(index + estimate_start, role)
        for index, role in enumerate(roles)
    )
    reconstruction_number = len(roles) + estimate_start
    role_questions = "".join(_role_review_controls(role) for role in roles)
    role_ids_json = json.dumps(
        [str(role["id"]) for role in roles], ensure_ascii=False, separators=(",", ":")
    )
    binding_json = json.dumps(binding, ensure_ascii=False, separators=(",", ":"))
    heard_count = len(roles) + len(truth) + 2
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sunofriend separation review</title><style>
:root{{--bg:#07111d;--panel:#102030;--line:#29455d;--text:#eef7ff;--muted:#a8bfd0;--cyan:#35daf2;--yellow:#ffd24a}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:18px/1.5 system-ui,sans-serif}}main{{max-width:980px;margin:auto;padding:32px}}section{{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:24px;margin:18px 0}}h1{{font-size:clamp(2rem,6vw,4rem);line-height:1}}h2{{color:var(--cyan)}}audio{{width:100%}}label{{display:block;margin:12px 0}}fieldset{{border:1px solid var(--line);margin:12px 0}}textarea{{width:100%;min-height:120px;background:#071522;color:var(--text);border:1px solid var(--line);padding:12px}}button,a.button{{display:inline-block;background:#15658c;color:white;border:0;border-radius:8px;padding:12px 16px;margin:6px 6px 6px 0;text-decoration:none;cursor:pointer}}.warning{{border-left:5px solid var(--yellow);padding-left:14px}}.muted{{color:var(--muted)}}
</style></head><body><main><h1>Listen before you use the stems.</h1>
<p class="warning">This is a local experimental result for <b>{source_name}</b>. Good reconstruction does not prove accurate separation. Mixed or poor musical feedback is useful evidence, not a preview kill switch. Nothing on this page uploads audio or feedback.</p>
<section><h2>1. Source reference</h2><p>Remember the complete song and its balance.</p><audio controls preload="metadata" src="../SOURCE/source-reference.wav"></audio></section>
{truth_sections}{role_sections}<section><h2>{reconstruction_number}. Reconstruction check</h2><p>This is the sum of the persisted stems. It should closely resemble the level-managed source reference.</p><audio controls preload="metadata" src="../AUDIO/reconstruction-check.wav"></audio></section>
<section><h2>Record a private local review</h2>
<label><input id="heard" type="checkbox"> I heard all {heard_count} tracks</label>
<label>Overall usefulness {_usefulness_select('quality')}</label>
{role_questions}
<label>Did these stems improve downstream MIDI? <select id="midi"><option value="">Choose…</option><option value="improved">Improved</option><option value="no_change">No change</option><option value="worse">Worse</option><option value="cannot_tell">Cannot tell</option><option value="not_tested">Not tested</option></select></label>
<label>Private notes<textarea id="notes" placeholder="Bleed, missing sound, joins, artefacts, timing, musical usefulness…"></textarea></label>
<button id="export">Export private review JSON</button><button id="copy">Copy text-only feedback</button><a class="button" href="{feedback}" target="_blank" rel="noreferrer">Open compatibility form ↗</a>
<p id="copy-status" class="muted" aria-live="polite"></p><p class="muted">Review JSON and notes stay local unless you deliberately share them. Copy text-only feedback omits the source filename, private notes, telemetry and audio.</p></section>
<script>
const roleIds={role_ids_json}; const binding={binding_json};
function reviewValue(){{
 const stemUsefulness=Object.fromEntries(roleIds.map(id=>[id,document.getElementById('role-'+id).value]));
 const issues=Object.fromEntries(roleIds.map(id=>[id,[...document.querySelectorAll('input[data-role="'+id+'"]:checked')].map(item=>item.value)]));
 return {{schema:'{REVIEW_SCHEMA}',binding:binding,heard_all_tracks:document.getElementById('heard').checked,overall_usefulness:document.getElementById('quality').value,stem_usefulness:stemUsefulness,per_role_issues:issues,downstream_midi:document.getElementById('midi').value,notes:document.getElementById('notes').value,exported_at:new Date().toISOString(),audio_included:false,telemetry_included:false,filename_included:false}};
}}
document.getElementById('export').addEventListener('click',()=>{{const value=reviewValue(); const blob=new Blob([JSON.stringify(value,null,2)+'\\n'],{{type:'application/json'}}); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='sunofriend-separation-review.json'; a.click(); setTimeout(()=>URL.revokeObjectURL(a.href),1000);}});
document.getElementById('copy').addEventListener('click',async()=>{{const value=reviewValue(); const lines=['Sunofriend stem preview feedback','Scope: '+value.binding.scope_id,'Profile: '+value.binding.profile_id,'Report: '+value.binding.separation_report_sha256,'Overall: '+(value.overall_usefulness||'not_answered'),'Roles: '+roleIds.map(id=>id+'='+(value.stem_usefulness[id]||'not_answered')).join(', '),'Issues: '+roleIds.map(id=>id+'='+(value.per_role_issues[id].join('+')||'none_answered')).join(', '),'Downstream MIDI: '+(value.downstream_midi||'not_answered')]; await navigator.clipboard.writeText(lines.join('\\n')); document.getElementById('copy-status').textContent='Text-only feedback copied. Paste it into the compatibility form if you choose.';}});
</script></main></body></html>"""


def validate_review_document(
    document: Mapping[str, Any], *, report: Mapping[str, Any]
) -> dict[str, Any]:
    roles = [str(item["id"]) for item in _role_details(report)]
    expected_binding = _report_binding(report)
    if document.get("schema") != REVIEW_SCHEMA:
        raise ValueError("unsupported separation review schema")
    if document.get("binding") != expected_binding:
        raise ValueError("separation review binding differs from the exact report")
    if type(document.get("heard_all_tracks")) is not bool:
        raise ValueError("heard_all_tracks must be boolean")
    overall = document.get("overall_usefulness")
    if overall not in USEFULNESS_VALUES:
        raise ValueError("overall usefulness is missing or invalid")
    stem_usefulness = document.get("stem_usefulness")
    if (
        not isinstance(stem_usefulness, Mapping)
        or set(stem_usefulness) != set(roles)
        or any(value not in USEFULNESS_VALUES for value in stem_usefulness.values())
    ):
        raise ValueError("per-role usefulness is missing or invalid")
    issues = document.get("per_role_issues")
    if not isinstance(issues, Mapping) or set(issues) != set(roles):
        raise ValueError("per-role issues are missing or invalid")
    for role, values in issues.items():
        if (
            not isinstance(values, list)
            or len(values) != len(set(values))
            or any(value not in ISSUE_VALUES for value in values)
            or ({"none_observed", "cannot_tell", "not_tested"} & set(values) and len(values) > 1)
        ):
            raise ValueError(f"per-role issues are invalid for {role}")
    if document.get("downstream_midi") not in MIDI_VALUES:
        raise ValueError("downstream MIDI outcome is missing or invalid")
    notes = document.get("notes")
    if not isinstance(notes, str) or len(notes) > 5_000:
        raise ValueError("private review notes are invalid")
    for key in ("audio_included", "telemetry_included", "filename_included"):
        if document.get(key) is not False:
            raise ValueError(f"{key} must remain false")
    return dict(document)


def _report_binding(report: Mapping[str, Any]) -> dict[str, str]:
    separator = report.get("separator")
    if not isinstance(separator, Mapping):
        raise ValueError("separation report identity is missing")
    binding = {
        "scope_id": separator.get("scope_id"),
        "profile_id": separator.get("profile_id"),
        "separation_report_sha256": report.get("document_sha256"),
    }
    if (
        any(not isinstance(value, str) or not value for value in binding.values())
        or not _SHA256.fullmatch(binding["separation_report_sha256"])
    ):
        raise ValueError("separation report binding is invalid")
    return binding


def _role_details(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    separator = report.get("separator")
    roles = separator.get("role_details") if isinstance(separator, Mapping) else None
    if (
        not isinstance(roles, Sequence)
        or isinstance(roles, (str, bytes))
        or not roles
        or any(not isinstance(role, Mapping) for role in roles)
    ):
        raise ValueError("separation report role details are missing or invalid")
    required = {"id", "label", "path", "summary", "review_prompt"}
    if any(set(role) != required for role in roles):
        raise ValueError("separation report role detail contract differs")
    return list(roles)


def _role_section(number: int, role: Mapping[str, Any]) -> str:
    label = html.escape(str(role["label"]))
    prompt = html.escape(str(role["review_prompt"]))
    path = html.escape(f"../{role['path']}", quote=True)
    return (
        f"<section><h2>{number}. {label}</h2><p>{prompt}</p>"
        f'<audio controls preload="metadata" src="{path}"></audio></section>\n'
    )


def _truth_role_section(
    number: int, role: str, value: Mapping[str, Any]
) -> str:
    label = html.escape(role.replace("_", " ").title())
    path = html.escape(f"../{value['path']}", quote=True)
    return (
        f"<section><h2>{number}. Synthetic ground truth: {label}</h2>"
        "<p>Copyright-safe reference for catastrophic role and timing checks; "
        "it is not a required quality target.</p>"
        f'<audio controls preload="metadata" src="{path}"></audio></section>\n'
    )


def _activation_truth_details(
    report: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    separator = report.get("separator")
    worker = separator.get("worker") if isinstance(separator, Mapping) else None
    activation = (
        worker.get("activation_ground_truth") if isinstance(worker, Mapping) else None
    )
    roles = activation.get("roles") if isinstance(activation, Mapping) else None
    if roles is None:
        return {}
    if (
        not isinstance(roles, Mapping)
        or set(roles) != {"vocals", "drums", "bass", "other"}
        or any(
            not isinstance(value, Mapping)
            or set(value) != {"path", "bytes", "sha256"}
            for value in roles.values()
        )
    ):
        raise ValueError("activation ground-truth review contract differs")
    return {str(role): value for role, value in roles.items()}


def _role_review_controls(role: Mapping[str, Any]) -> str:
    role_id = html.escape(str(role["id"]), quote=True)
    label = html.escape(str(role["label"]))
    issues = "".join(
        f'<label><input type="checkbox" data-role="{role_id}" value="{value}"> {text}</label>'
        for value, text in (
            ("bleed", "Bleed"),
            ("missing_content", "Missing content"),
            ("artefacts", "Artefacts"),
            ("timing", "Timing problem"),
            ("join_problem", "Join problem"),
            ("none_observed", "None observed"),
            ("cannot_tell", "Cannot tell"),
            ("not_tested", "Not tested"),
        )
    )
    return (
        f"<fieldset><legend>{label}</legend><label>Usefulness "
        f"{_usefulness_select('role-' + role_id)}</label>{issues}</fieldset>"
    )


def _usefulness_select(identifier: str) -> str:
    return (
        f'<select id="{identifier}"><option value="">Choose…</option>'
        '<option value="useful">Useful</option>'
        '<option value="useful_with_limitations">Useful with limitations</option>'
        '<option value="not_useful">Not useful</option>'
        '<option value="cannot_tell">Cannot tell</option>'
        '<option value="not_tested">Not tested</option></select>'
    )


__all__ = [
    "ISSUE_VALUES",
    "MIDI_VALUES",
    "REVIEW_SCHEMA",
    "USEFULNESS_VALUES",
    "render_review_html",
    "render_start_here",
    "validate_review_document",
]
