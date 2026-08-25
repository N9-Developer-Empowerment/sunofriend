"""One-variable deterministic remix comparison packages.

The challenger is the exact source mix plus a bounded gain delta from one
hash-bound separation estimate.  The unchanged source bytes remain the
control.  This module performs no model inference, training, selection or
automatic review.
"""

from __future__ import annotations

import html
import json
import math
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .audio_formats import file_sha256
from .remix_identity import (
    REMIX_IDENTITY_STATE_SCHEMA,
    REMIX_REQUEST_SCHEMA,
    create_remix_review,
    create_remix_result,
    validate_remix_request,
)
from .source_receipt import canonical_json_bytes, document_sha256


REMIX_COMPARISON_PLAN_SCHEMA = "sunofriend.remix-delta-comparison-plan.v0"
REMIX_COMPARISON_RESULT_SCHEMA = "sunofriend.remix-delta-comparison-result.v0"
REMIX_COMPARISON_REVIEW_SEED_SCHEMA = "sunofriend.remix-delta-review-seed.v0"

_MAX_AUDIO_BYTES = 2 * 1024 * 1024 * 1024
_MAX_FRAMES = 96_000 * 60 * 20


def inspect_remix_audio(path: str | Path) -> dict[str, Any]:
    """Return a path-free identity and geometry record for one local WAV."""

    source = _regular_file(path, "remix audio")
    if source.stat().st_size > _MAX_AUDIO_BYTES:
        raise ValueError("remix audio exceeds the 2 GiB bound")
    soundfile, _ = _audio_dependencies()
    with soundfile.SoundFile(source) as handle:
        if handle.format != "WAV":
            raise ValueError("bounded remix audio must be WAV")
        geometry = {
            "sample_rate_hz": int(handle.samplerate),
            "channels": int(handle.channels),
            "frames": int(handle.frames),
        }
    _validate_geometry(geometry)
    return {
        "audio_sha256": file_sha256(source),
        "audio_bytes": source.stat().st_size,
        "geometry": geometry,
    }


def create_remix_comparison_plan(
    remix_request: Mapping[str, Any],
    identity_state: Mapping[str, Any],
    *,
    source_control: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind an unchanged source control before any derivative is rendered."""

    request = validate_remix_request(remix_request, identity_state)
    if (
        not isinstance(identity_state.get("owner_anchors"), list)
        or len(identity_state["owner_anchors"]) != 1
    ):
        raise ValueError(
            "first bounded remix comparison requires exactly one owner anchor"
        )
    source = _validate_audio_record(source_control, "source control")
    target = _target_record(identity_state, request)
    if source["geometry"] != target["geometry"]:
        raise ValueError(
            "source control and target estimate must share exact synchronized geometry"
        )
    document: dict[str, Any] = {
        "schema": REMIX_COMPARISON_PLAN_SCHEMA,
        "status": "planned_exact_source_control_one_target_delta",
        "binding": {
            "identity_state_schema": REMIX_IDENTITY_STATE_SCHEMA,
            "identity_state_sha256": identity_state["document_sha256"],
            "remix_request_schema": REMIX_REQUEST_SCHEMA,
            "remix_request_sha256": request["document_sha256"],
        },
        "method_natures": ["D", "H"],
        "source_control": source,
        "target_estimate": target,
        "render_policy": {
            "name": "exact-source-plus-target-estimate-gain-delta-v0",
            "formula": "source + (envelope_linear_gain - 1) * target_estimate",
            "source_control_copy": "byte_exact",
            "challenger_encoding": "WAV_PCM_24",
            "normalisation": False,
            "limiting": False,
            "clipping_permitted": False,
        },
        "review_policy": {
            "owner_anchor_required": True,
            "playback_creates_decision": False,
            "automatic_preference": False,
            "selection_created": False,
            "training_label_created": False,
        },
        "model_used": False,
        "training_used": False,
        "network_used": False,
        "effects": {
            "source_mutated": False,
            "target_estimate_mutated": False,
            "audio_derivative_rendered": False,
            "human_review_created": False,
            "selection_created": False,
            "training_label_created": False,
        },
    }
    document["document_sha256"] = document_sha256(document)
    return validate_remix_comparison_plan(document, request, identity_state)


def validate_remix_comparison_plan(
    plan: Mapping[str, Any],
    remix_request: Mapping[str, Any],
    identity_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate an exact-source comparison plan without opening audio."""

    request = validate_remix_request(remix_request, identity_state)
    document = dict(plan)
    _verify_document(document, REMIX_COMPARISON_PLAN_SCHEMA, "comparison plan")
    if document.get("status") != "planned_exact_source_control_one_target_delta":
        raise ValueError("bounded remix comparison plan status is unsupported")
    _validate_comparison_owner_anchor(identity_state)
    _validate_comparison_plan_binding(document, request, identity_state)
    _validate_comparison_plan_audio(document, request, identity_state)
    _validate_comparison_plan_policy(document)
    _reject_paths(document)
    return document


def _validate_comparison_owner_anchor(identity_state: Mapping[str, Any]) -> None:
    """Require the single human anchor supported by the first comparison."""

    if (
        not isinstance(identity_state.get("owner_anchors"), list)
        or len(identity_state["owner_anchors"]) != 1
    ):
        raise ValueError(
            "first bounded remix comparison requires exactly one owner anchor"
        )


def _validate_comparison_plan_binding(
    document: Mapping[str, Any],
    request: Mapping[str, Any],
    identity_state: Mapping[str, Any],
) -> None:
    """Own exact identity-state and request binding for a comparison plan."""

    if document.get("binding") != {
        "identity_state_schema": REMIX_IDENTITY_STATE_SCHEMA,
        "identity_state_sha256": identity_state["document_sha256"],
        "remix_request_schema": REMIX_REQUEST_SCHEMA,
        "remix_request_sha256": request["document_sha256"],
    }:
        raise ValueError("bounded remix comparison plan binding changed")


def _validate_comparison_plan_audio(
    document: Mapping[str, Any],
    request: Mapping[str, Any],
    identity_state: Mapping[str, Any],
) -> None:
    """Validate source and target identities plus synchronized geometry."""

    source = _validate_audio_record(document.get("source_control"), "source control")
    target = _target_record(identity_state, request)
    if document.get("target_estimate") != target:
        raise ValueError("bounded remix target estimate identity changed")
    if source["geometry"] != target["geometry"]:
        raise ValueError("source control and target estimate geometry changed")


def _validate_comparison_plan_policy(document: Mapping[str, Any]) -> None:
    """Keep rendering, review and side-effect authority at planned limits."""

    expected_render = {
        "name": "exact-source-plus-target-estimate-gain-delta-v0",
        "formula": "source + (envelope_linear_gain - 1) * target_estimate",
        "source_control_copy": "byte_exact",
        "challenger_encoding": "WAV_PCM_24",
        "normalisation": False,
        "limiting": False,
        "clipping_permitted": False,
    }
    expected_review = {
        "owner_anchor_required": True,
        "playback_creates_decision": False,
        "automatic_preference": False,
        "selection_created": False,
        "training_label_created": False,
    }
    if (
        document.get("method_natures") != ["D", "H"]
        or document.get("render_policy") != expected_render
        or document.get("review_policy") != expected_review
        or document.get("model_used") is not False
        or document.get("training_used") is not False
        or document.get("network_used") is not False
    ):
        raise ValueError("bounded remix comparison authority expanded")
    if document.get("effects") != {
        "source_mutated": False,
        "target_estimate_mutated": False,
        "audio_derivative_rendered": False,
        "human_review_created": False,
        "selection_created": False,
        "training_label_created": False,
    }:
        raise ValueError("comparison plan cannot claim product effects")


def render_remix_comparison(
    plan: Mapping[str, Any],
    remix_request: Mapping[str, Any],
    identity_state: Mapping[str, Any],
    *,
    source_audio: str | Path,
    target_estimate_audio: str | Path,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Render a fresh private source/challenger/review package offline."""

    checked_plan = validate_remix_comparison_plan(plan, remix_request, identity_state)
    request = validate_remix_request(remix_request, identity_state)
    source_path = _regular_file(source_audio, "source control")
    target_path = _regular_file(target_estimate_audio, "target estimate")
    if inspect_remix_audio(source_path) != checked_plan["source_control"]:
        raise ValueError("source control does not match the exact bound audio")
    target_observed = inspect_remix_audio(target_path)
    if target_observed != {
        key: checked_plan["target_estimate"][key]
        for key in ("audio_sha256", "audio_bytes", "geometry")
    }:
        raise ValueError("target estimate does not match the exact bound audio")

    destination = Path(out_dir).absolute()
    if destination.exists():
        raise FileExistsError(f"remix comparison output already exists: {destination}")
    parent = destination.parent
    if not parent.is_dir():
        raise ValueError("remix comparison output parent must already exist")
    if stat.S_IMODE(parent.stat().st_mode) & 0o077:
        raise PermissionError("remix comparison output parent must be owner-only")

    soundfile, numpy = _audio_dependencies()
    source, source_rate = soundfile.read(source_path, always_2d=True, dtype="float64")
    target, target_rate = soundfile.read(target_path, always_2d=True, dtype="float64")
    if (
        inspect_remix_audio(source_path) != checked_plan["source_control"]
        or inspect_remix_audio(target_path) != target_observed
    ):
        raise ValueError("source control or target estimate changed during decoding")
    if source_rate != target_rate or source.shape != target.shape:
        raise ValueError("source control and target estimate decoded geometry changed")
    operation = request["operations"][0]
    frames = numpy.arange(source.shape[0], dtype=numpy.float64)
    point_frames = numpy.asarray(
        [row["frame"] for row in operation["points"]], dtype=numpy.float64
    )
    point_db = numpy.asarray(
        [row["delta_db"] for row in operation["points"]], dtype=numpy.float64
    )
    delta_db = numpy.zeros(source.shape[0], dtype=numpy.float64)
    start = int(operation["start_frame"])
    end = int(operation["end_frame"])
    delta_db[start:end] = numpy.interp(frames[start:end], point_frames, point_db)
    gain = numpy.power(10.0, delta_db / 20.0)[:, None]
    challenger = source + ((gain - 1.0) * target)
    if not numpy.isfinite(challenger).all():
        raise ValueError("remix challenger contains non-finite samples")
    peak = float(numpy.max(numpy.abs(challenger), initial=0.0))
    if peak >= 1.0:
        raise ValueError("remix challenger would clip; use a smaller negative delta")

    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=parent))
    staging.chmod(0o700)
    try:
        audio_dir = staging / "AUDIO"
        review_dir = staging / "REVIEW"
        technical_dir = staging / "TECHNICAL"
        for directory in (audio_dir, review_dir, technical_dir):
            directory.mkdir(mode=0o700)
        control_output = audio_dir / "source-control.wav"
        challenger_output = audio_dir / "delta-challenger.wav"
        shutil.copyfile(source_path, control_output)
        control_output.chmod(0o600)
        if inspect_remix_audio(control_output) != checked_plan["source_control"]:
            raise ValueError("source control changed before exact publication")
        soundfile.write(
            challenger_output,
            challenger,
            source_rate,
            format="WAV",
            subtype="PCM_24",
        )
        challenger_output.chmod(0o600)

        challenger_record = inspect_remix_audio(challenger_output)
        remix_result = create_remix_result(
            request,
            identity_state,
            output_audio_sha256=challenger_record["audio_sha256"],
            output_audio_bytes=challenger_record["audio_bytes"],
            output_geometry=challenger_record["geometry"],
        )
        package_binding = document_sha256(
            {
                "comparison_plan_sha256": checked_plan["document_sha256"],
                "remix_result_sha256": remix_result["document_sha256"],
                "source_control_sha256": checked_plan["source_control"]["audio_sha256"],
                "challenger_sha256": challenger_record["audio_sha256"],
            }
        )
        review_seed = _review_seed(
            package_binding, identity_state, request, remix_result
        )
        seed_path = review_dir / "remix-review.seed.json"
        _write_private(seed_path, canonical_json_bytes(review_seed))
        html_path = review_dir / "remix-review.html"
        _write_private(html_path, _review_html(review_seed).encode("utf-8"))

        result: dict[str, Any] = {
            "schema": REMIX_COMPARISON_RESULT_SCHEMA,
            "status": "complete_unreviewed_deterministic_comparison",
            "binding": {
                "comparison_plan_sha256": checked_plan["document_sha256"],
                "identity_state_sha256": identity_state["document_sha256"],
                "remix_request_sha256": request["document_sha256"],
                "remix_result_sha256": remix_result["document_sha256"],
                "package_binding_sha256": package_binding,
            },
            "artifacts": {
                "source_control": {
                    **checked_plan["source_control"],
                    "relative_path": "AUDIO/source-control.wav",
                    "copy_policy": "byte_exact",
                },
                "challenger": {
                    **challenger_record,
                    "relative_path": "AUDIO/delta-challenger.wav",
                    "encoding": "WAV_PCM_24",
                },
                "review_seed": _file_record(seed_path, staging),
                "review_html": _file_record(html_path, staging),
            },
            "signal": {
                "challenger_sample_peak": peak,
                "normalised": False,
                "limited": False,
                "clipped": False,
            },
            "review_status": "not_reviewed",
            "owner_identity_preserved": None,
            "selected_for_product": False,
            "model_used": False,
            "training_used": False,
            "network_used": False,
            "effects": {
                "source_mutated": False,
                "target_estimate_mutated": False,
                "audio_derivative_rendered": True,
                "review_page_created": True,
                "human_review_created": False,
                "selection_created": False,
                "training_label_created": False,
                "model_weights_changed": False,
            },
        }
        result["document_sha256"] = document_sha256(result)
        validate_remix_comparison_result(result, checked_plan, request, identity_state)
        _write_private(
            technical_dir / "remix-comparison.json", canonical_json_bytes(result)
        )
        os.rename(staging, destination)
        return result
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def validate_remix_comparison_result(
    result: Mapping[str, Any],
    plan: Mapping[str, Any],
    remix_request: Mapping[str, Any],
    identity_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a comparison result contract without opening its package."""

    checked_plan = validate_remix_comparison_plan(plan, remix_request, identity_state)
    request = validate_remix_request(remix_request, identity_state)
    document = dict(result)
    _verify_document(document, REMIX_COMPARISON_RESULT_SCHEMA, "comparison result")
    binding = _validate_comparison_result_binding(
        document,
        checked_plan=checked_plan,
        request=request,
        identity_state=identity_state,
    )
    challenger = _validate_comparison_result_artifacts(
        document, checked_plan=checked_plan
    )
    _validate_comparison_result_derivative_binding(
        binding=binding,
        challenger=challenger,
        checked_plan=checked_plan,
        request=request,
        identity_state=identity_state,
    )
    _validate_comparison_result_signal(document)
    _validate_comparison_result_authority(document)
    _reject_paths(document)
    return document


def _validate_comparison_result_binding(
    document: Mapping[str, Any],
    *,
    checked_plan: Mapping[str, Any],
    request: Mapping[str, Any],
    identity_state: Mapping[str, Any],
) -> Mapping[str, Any]:
    binding = document.get("binding")
    if not isinstance(binding, Mapping) or set(binding) != {
        "comparison_plan_sha256",
        "identity_state_sha256",
        "remix_request_sha256",
        "remix_result_sha256",
        "package_binding_sha256",
    }:
        raise ValueError("comparison result binding fields changed")
    if binding.get("comparison_plan_sha256") != checked_plan["document_sha256"]:
        raise ValueError("comparison result plan binding changed")
    if binding.get("identity_state_sha256") != identity_state["document_sha256"]:
        raise ValueError("comparison result identity binding changed")
    if binding.get("remix_request_sha256") != request["document_sha256"]:
        raise ValueError("comparison result request binding changed")
    if document.get("status") != "complete_unreviewed_deterministic_comparison":
        raise ValueError("comparison result must remain unreviewed")
    return binding


def _validate_comparison_result_artifacts(
    document: Mapping[str, Any], *, checked_plan: Mapping[str, Any]
) -> Mapping[str, Any]:
    artifacts = document.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("comparison result artifacts are required")
    control = artifacts.get("source_control")
    if (
        not isinstance(control, Mapping)
        or {
            key: control.get(key) for key in ("audio_sha256", "audio_bytes", "geometry")
        }
        != checked_plan["source_control"]
    ):
        raise ValueError("comparison source control identity changed")
    if (
        control.get("relative_path") != "AUDIO/source-control.wav"
        or control.get("copy_policy") != "byte_exact"
    ):
        raise ValueError("comparison source control is not an exact copy")
    challenger = artifacts.get("challenger")
    if not isinstance(challenger, Mapping):
        raise ValueError("comparison challenger is required")
    _validate_audio_record(challenger, "challenger", allow_artifact_fields=True)
    if challenger.get("geometry") != checked_plan["source_control"]["geometry"]:
        raise ValueError("comparison challenger geometry changed")
    if (
        challenger.get("relative_path") != "AUDIO/delta-challenger.wav"
        or challenger.get("encoding") != "WAV_PCM_24"
    ):
        raise ValueError("comparison challenger artifact contract changed")
    for key, path in (
        ("review_seed", "REVIEW/remix-review.seed.json"),
        ("review_html", "REVIEW/remix-review.html"),
    ):
        _validate_relative_file_record(artifacts.get(key), path)
    return challenger


def _validate_comparison_result_derivative_binding(
    *,
    binding: Mapping[str, Any],
    challenger: Mapping[str, Any],
    checked_plan: Mapping[str, Any],
    request: Mapping[str, Any],
    identity_state: Mapping[str, Any],
) -> None:
    expected_remix_result = create_remix_result(
        request,
        identity_state,
        output_audio_sha256=challenger["audio_sha256"],
        output_audio_bytes=challenger["audio_bytes"],
        output_geometry=challenger["geometry"],
    )
    expected_package_binding = document_sha256(
        {
            "comparison_plan_sha256": checked_plan["document_sha256"],
            "remix_result_sha256": expected_remix_result["document_sha256"],
            "source_control_sha256": checked_plan["source_control"]["audio_sha256"],
            "challenger_sha256": challenger["audio_sha256"],
        }
    )
    if (
        binding.get("remix_result_sha256") != expected_remix_result["document_sha256"]
        or binding.get("package_binding_sha256") != expected_package_binding
    ):
        raise ValueError("comparison result derivative binding changed")


def _validate_comparison_result_signal(document: Mapping[str, Any]) -> None:
    signal = document.get("signal")
    if not isinstance(signal, Mapping) or set(signal) != {
        "challenger_sample_peak",
        "normalised",
        "limited",
        "clipped",
    }:
        raise ValueError("comparison signal evidence changed")
    peak = signal.get("challenger_sample_peak")
    if (
        isinstance(peak, bool)
        or not isinstance(peak, (int, float))
        or not math.isfinite(float(peak))
        or not 0.0 <= float(peak) < 1.0
        or signal.get("normalised") is not False
        or signal.get("limited") is not False
        or signal.get("clipped") is not False
    ):
        raise ValueError("comparison signal evidence is invalid")


def _validate_comparison_result_authority(document: Mapping[str, Any]) -> None:
    if (
        document.get("review_status") != "not_reviewed"
        or document.get("owner_identity_preserved") is not None
        or document.get("selected_for_product") is not False
        or document.get("model_used") is not False
        or document.get("training_used") is not False
        or document.get("network_used") is not False
    ):
        raise ValueError("unreviewed comparison cannot claim authority")
    if document.get("effects") != {
        "source_mutated": False,
        "target_estimate_mutated": False,
        "audio_derivative_rendered": True,
        "review_page_created": True,
        "human_review_created": False,
        "selection_created": False,
        "training_label_created": False,
        "model_weights_changed": False,
    }:
        raise ValueError("comparison result effects changed")


def resolve_remix_comparison_review(
    reviewed_export: Mapping[str, Any],
    comparison_result: Mapping[str, Any],
    plan: Mapping[str, Any],
    remix_request: Mapping[str, Any],
    identity_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify one explicit page export and create the existing review contract."""

    result = validate_remix_comparison_result(
        comparison_result, plan, remix_request, identity_state
    )
    request = validate_remix_request(remix_request, identity_state)
    export = dict(reviewed_export)
    _validate_review_export_fields(export)
    anchor = _comparison_anchor(identity_state, request)
    _validate_review_export_binding(export, result, anchor)
    questions = _validate_review_export_questions(export)
    _validate_review_export_authority(export)
    remix_result = _reconstruct_reviewed_remix_result(result, request, identity_state)
    return create_remix_review(
        remix_result,
        request,
        identity_state,
        owner_anchor_labels=[
            {
                "anchor_id": anchor["anchor_id"],
                "heard": True,
                "identity_relationship": questions["identity_relationship"],
                "musical_usefulness": questions["musical_usefulness"],
            }
        ],
    )


def _validate_review_export_fields(export: Mapping[str, Any]) -> None:
    """Own the exact browser-export field roster."""

    if set(export) != {
        "schema",
        "status",
        "package_binding_sha256",
        "remix_result_sha256",
        "anchor",
        "questions",
        "playback_creates_decision",
        "automatic_preference",
        "selection_created",
        "training_label_created",
        "label_authority",
        "selected_for_product",
        "training_eligible",
    }:
        raise ValueError("review export fields are unsupported")


def _comparison_anchor(
    identity_state: Mapping[str, Any], request: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Resolve the request's already-validated human anchor."""

    operation = request["operations"][0]
    return next(
        row
        for row in identity_state["owner_anchors"]
        if row["anchor_id"] == operation["anchor_id"]
    )


def _validate_review_export_binding(
    export: Mapping[str, Any],
    result: Mapping[str, Any],
    anchor: Mapping[str, Any],
) -> None:
    """Bind the explicit export to this package, derivative and anchor."""

    if (
        export.get("schema") != REMIX_COMPARISON_REVIEW_SEED_SCHEMA
        or export.get("status") != "complete_explicit_owner_review_no_selection"
        or export.get("package_binding_sha256")
        != result["binding"]["package_binding_sha256"]
        or export.get("remix_result_sha256") != result["binding"]["remix_result_sha256"]
        or export.get("anchor")
        != {"anchor_id": anchor["anchor_id"], "owner_label": anchor["owner_label"]}
    ):
        raise ValueError("review export does not bind this exact comparison")


def _validate_review_export_questions(
    export: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Require both auditions and bounded owner comparison labels."""

    questions = export.get("questions")
    if not isinstance(questions, Mapping) or set(questions) != {
        "heard_source_control",
        "heard_delta_challenger",
        "identity_relationship",
        "musical_usefulness",
    }:
        raise ValueError("review export questions are incomplete")
    if (
        questions.get("heard_source_control") is not True
        or questions.get("heard_delta_challenger") is not True
    ):
        raise ValueError("explicitly hearing both comparison artifacts is required")
    if questions.get("identity_relationship") not in {
        "preserved",
        "partly_preserved",
        "lost",
        "cannot_tell",
    } or questions.get("musical_usefulness") not in {
        "useful",
        "not_useful",
        "equivalent",
        "cannot_tell",
    }:
        raise ValueError("explicit owner comparison labels are incomplete")
    return questions


def _validate_review_export_authority(export: Mapping[str, Any]) -> None:
    """Prevent playback or one review from implying product/training authority."""

    if (
        export.get("playback_creates_decision") is not False
        or export.get("automatic_preference") is not False
        or export.get("selection_created") is not False
        or export.get("training_label_created") is not False
        or export.get("label_authority") != "explicit_owner_listening_decision"
        or export.get("selected_for_product") is not False
        or export.get("training_eligible") is not False
    ):
        raise ValueError("review authority cannot be inferred or expanded")


def _reconstruct_reviewed_remix_result(
    result: Mapping[str, Any],
    request: Mapping[str, Any],
    identity_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Reconstruct and verify the exact remix result named by the export."""

    challenger = result["artifacts"]["challenger"]
    remix_result = create_remix_result(
        request,
        identity_state,
        output_audio_sha256=challenger["audio_sha256"],
        output_audio_bytes=challenger["audio_bytes"],
        output_geometry=challenger["geometry"],
    )
    if remix_result["document_sha256"] != result["binding"]["remix_result_sha256"]:
        raise ValueError("comparison remix result cannot be reconstructed exactly")
    return remix_result


def _target_record(
    identity_state: Mapping[str, Any], request: Mapping[str, Any]
) -> dict[str, Any]:
    operation = request["operations"][0]
    estimate_id = operation["source_estimate_id"]
    rows = identity_state.get("separation_estimates")
    if not isinstance(rows, list):
        raise ValueError("identity state separation estimates are required")
    for row in rows:
        if isinstance(row, Mapping) and row.get("source_estimate_id") == estimate_id:
            return {
                "source_estimate_id": estimate_id,
                "audio_sha256": row["audio_sha256"],
                "audio_bytes": row["audio_bytes"],
                "geometry": dict(row["geometry"]),
                "role_interpretation": "estimate_not_ground_truth",
            }
    raise ValueError("request target estimate is unavailable")


def _review_seed(
    package_binding: str,
    identity_state: Mapping[str, Any],
    request: Mapping[str, Any],
    remix_result: Mapping[str, Any],
) -> dict[str, Any]:
    anchor_id = request["operations"][0]["anchor_id"]
    anchor = next(
        row for row in identity_state["owner_anchors"] if row["anchor_id"] == anchor_id
    )
    seed: dict[str, Any] = {
        "schema": REMIX_COMPARISON_REVIEW_SEED_SCHEMA,
        "status": "unreviewed",
        "package_binding_sha256": package_binding,
        "remix_result_sha256": remix_result["document_sha256"],
        "anchor": {
            "anchor_id": anchor_id,
            "owner_label": anchor["owner_label"],
        },
        "questions": {
            "heard_source_control": False,
            "heard_delta_challenger": False,
            "identity_relationship": None,
            "musical_usefulness": None,
        },
        "playback_creates_decision": False,
        "automatic_preference": False,
        "selection_created": False,
        "training_label_created": False,
    }
    seed["document_sha256"] = document_sha256(seed)
    return seed


def _review_html(seed: Mapping[str, Any]) -> str:
    seed_json = json.dumps(seed, ensure_ascii=False, sort_keys=True).replace(
        "</", "<\\/"
    )
    label = html.escape(str(seed["anchor"]["owner_label"]))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sunofriend bounded remix review</title>
<style>body{{font:16px system-ui;max-width:760px;margin:2rem auto;padding:0 1rem;background:#111;color:#eee}}fieldset{{margin:1rem 0;padding:1rem}}audio{{width:100%}}button{{padding:.7rem 1rem}}.note{{color:#bbb}}</style></head>
<body><h1>Bounded remix review</h1>
<p><strong>Owner anchor:</strong> {label}</p>
<p class="note">This compares the unchanged source with one target-estimate gain delta. Playback saves nothing and creates no preference.</p>
<h2>Unchanged source control</h2><audio controls src="../AUDIO/source-control.wav"></audio>
<label><input id="heard-source" type="checkbox"> I heard the source control</label>
<h2>Delta challenger</h2><audio controls src="../AUDIO/delta-challenger.wav"></audio>
<label><input id="heard-challenger" type="checkbox"> I heard the challenger</label>
<fieldset><legend>Was the named identity relationship preserved?</legend>
<select id="identity"><option value="">Choose explicitly</option><option value="preserved">Preserved</option><option value="partly_preserved">Partly preserved</option><option value="lost">Lost</option><option value="cannot_tell">Cannot tell</option></select></fieldset>
<fieldset><legend>Is the change musically useful?</legend>
<select id="usefulness"><option value="">Choose explicitly</option><option value="useful">Useful</option><option value="not_useful">Not useful</option><option value="equivalent">Equivalent</option><option value="cannot_tell">Cannot tell</option></select></fieldset>
<button id="export" disabled>Export explicit review JSON</button>
<script id="seed" type="application/json">{seed_json}</script><script>
const seed=JSON.parse(document.getElementById('seed').textContent);const ids=['heard-source','heard-challenger','identity','usefulness'];const ready=()=>{{document.getElementById('export').disabled=!(document.getElementById('heard-source').checked&&document.getElementById('heard-challenger').checked&&document.getElementById('identity').value&&document.getElementById('usefulness').value)}};ids.forEach(id=>document.getElementById(id).addEventListener('change',ready));document.getElementById('export').addEventListener('click',()=>{{const out={{...seed,status:'complete_explicit_owner_review_no_selection',questions:{{heard_source_control:true,heard_delta_challenger:true,identity_relationship:document.getElementById('identity').value,musical_usefulness:document.getElementById('usefulness').value}},label_authority:'explicit_owner_listening_decision',selected_for_product:false,training_eligible:false}};delete out.document_sha256;const blob=new Blob([JSON.stringify(out,null,2)+'\\n'],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='remix-review.reviewed.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}});
</script></body></html>"""


def _validate_audio_record(
    value: Any, label: str, *, allow_artifact_fields: bool = False
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} record is required")
    keys = {"audio_sha256", "audio_bytes", "geometry"}
    if allow_artifact_fields:
        keys |= {"relative_path", "encoding"}
    if set(value) != keys:
        raise ValueError(f"{label} record fields are unsupported")
    sha = value.get("audio_sha256")
    byte_count = value.get("audio_bytes")
    if (
        not isinstance(sha, str)
        or len(sha) != 64
        or any(char not in "0123456789abcdef" for char in sha)
    ):
        raise ValueError(f"{label} SHA-256 is invalid")
    if (
        isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or not 0 < byte_count <= _MAX_AUDIO_BYTES
    ):
        raise ValueError(f"{label} byte count is invalid")
    result = {
        "audio_sha256": sha,
        "audio_bytes": byte_count,
        "geometry": _validate_geometry(value.get("geometry")),
    }
    if allow_artifact_fields:
        result.update(
            relative_path=value.get("relative_path"), encoding=value.get("encoding")
        )
    return result


def _validate_geometry(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != {
        "sample_rate_hz",
        "channels",
        "frames",
    }:
        raise ValueError("remix audio geometry fields are invalid")
    geometry = dict(value)
    if (
        any(isinstance(geometry[key], bool) for key in geometry)
        or not all(isinstance(geometry[key], int) for key in geometry)
        or not 8_000 <= geometry["sample_rate_hz"] <= 96_000
        or not 1 <= geometry["channels"] <= 2
        or not 0 < geometry["frames"] <= _MAX_FRAMES
    ):
        raise ValueError("remix audio geometry is outside the bounded policy")
    return geometry


def _validate_relative_file_record(value: Any, expected_path: str) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "relative_path",
        "sha256",
        "bytes",
    }:
        raise ValueError("comparison file record is invalid")
    if value.get("relative_path") != expected_path:
        raise ValueError("comparison file path changed")
    if not isinstance(value.get("sha256"), str) or len(value["sha256"]) != 64:
        raise ValueError("comparison file hash is invalid")
    if not isinstance(value.get("bytes"), int) or value["bytes"] <= 0:
        raise ValueError("comparison file byte count is invalid")


def _file_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "sha256": file_sha256(path),
        "bytes": path.stat().st_size,
    }


def _regular_file(path: str | Path, label: str) -> Path:
    value = Path(path).absolute()
    if not value.is_file() or value.is_symlink():
        raise ValueError(f"{label} must be an existing regular file")
    return value


def _audio_dependencies() -> tuple[Any, Any]:
    try:
        import numpy
        import soundfile
    except ImportError as error:  # pragma: no cover - install boundary
        raise RuntimeError(
            "bounded remix rendering requires the convert extras"
        ) from error
    return soundfile, numpy


def _write_private(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)


def _verify_document(document: Mapping[str, Any], schema: str, label: str) -> None:
    if document.get("schema") != schema:
        raise ValueError(f"unsupported {label} schema")
    unsigned = dict(document)
    expected = unsigned.pop("document_sha256", None)
    if expected != document_sha256(unsigned):
        raise ValueError(f"{label} document SHA-256 does not match")


def _reject_paths(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in {"path", "source_path", "output_path", "absolute_path"}:
                raise ValueError("remix comparison contracts must be path-free")
            _reject_paths(item)
    elif isinstance(value, list):
        for item in value:
            _reject_paths(item)
    elif isinstance(value, str) and (
        value.startswith(("/", "\\\\"))
        or (len(value) >= 3 and value[1:3] in {":/", ":\\"})
    ):
        raise ValueError("remix comparison contracts must be path-free")


__all__ = [
    "REMIX_COMPARISON_PLAN_SCHEMA",
    "REMIX_COMPARISON_RESULT_SCHEMA",
    "REMIX_COMPARISON_REVIEW_SEED_SCHEMA",
    "create_remix_comparison_plan",
    "inspect_remix_audio",
    "render_remix_comparison",
    "resolve_remix_comparison_review",
    "validate_remix_comparison_plan",
    "validate_remix_comparison_result",
]
