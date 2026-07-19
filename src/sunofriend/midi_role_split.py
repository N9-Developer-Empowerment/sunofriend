"""Reviewable MIDI role splits from immutable source-event evidence.

This module does not claim to identify physical instruments.  It partitions an
existing MIDI performance by an explicitly selected source-event cluster and
optionally combines the retained body with an independently transcribed
secondary audio stream.  The unchanged input, strict partition and independent
challenger are all preserved for listening.
"""

from __future__ import annotations

import hashlib
import html
import json
import shutil
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Sequence

from .clip import MidiClip, read_midi_clips
from .midi import MidiTrack, write_midi_file
from .models import NoteEvent


MIDI_ROLE_SPLIT_SCHEMA = "sunofriend.midi-role-split.v1"
MIDI_ROLE_SPLIT_REVIEW_SCHEMA = "sunofriend.midi-role-split-review.v1"
MIDI_ROLE_SPLIT_RESOLUTION_SCHEMA = "sunofriend.midi-role-split-resolution.v1"

_DECISION_ARTIFACTS = {
    "keep_primary": "primary-unchanged.mid",
    "strict_partition": "two-role-primary-partition.mid",
    "independent_pluck": "two-role-independent-pluck.mid",
    "none": None,
}
_ROLE_VALUES = {"deep_body", "pluck", "both", "fragments"}
_USEFULNESS_VALUES = {"main", "secondary", "diagnostic", "reject"}


def create_midi_role_split(
    primary_midi_path: str | Path,
    cluster_report_path: str | Path,
    *,
    out_dir: str | Path,
    body_cluster: str,
    secondary_midi_path: str | Path | None = None,
    secondary_audio_path: str | Path | None = None,
    cleanup_review_path: str | Path | None = None,
    body_name: str = "Synth Bass Body",
    body_program: int = 39,
    pluck_name: str = "Plucked Bass Challenger",
    pluck_program: int = 28,
    render_preview: bool = True,
) -> dict[str, Any]:
    """Create strict and independent two-role MIDI challengers.

    ``body_cluster`` is deliberately explicit.  Sunofriend never selects the
    musical role from a silhouette score, duration or pitch range alone.
    """

    primary_midi = _required_file(primary_midi_path, "Primary MIDI")
    cluster_path = _required_file(cluster_report_path, "Cluster report")
    secondary_midi = (
        _required_file(secondary_midi_path, "Secondary MIDI")
        if secondary_midi_path is not None
        else None
    )
    secondary_audio = (
        _required_file(secondary_audio_path, "Secondary audio")
        if secondary_audio_path is not None
        else None
    )
    cleanup_review = (
        _required_file(cleanup_review_path, "Cleanup review")
        if cleanup_review_path is not None
        else None
    )
    destination = Path(out_dir).expanduser()
    if destination.exists():
        raise FileExistsError(f"Output directory already exists: {destination}")
    if not 0 <= int(body_program) <= 127 or not 0 <= int(pluck_program) <= 127:
        raise ValueError("MIDI programs must be from 0 to 127")
    if not str(body_name).strip() or not str(pluck_name).strip():
        raise ValueError("Role names must not be empty")

    clusters = json.loads(cluster_path.read_text(encoding="utf-8"))
    if clusters.get("schema") != "sunofriend.source-event-clusters.v1":
        raise ValueError("Unsupported source-event cluster report schema")
    if clusters.get("status") != "complete":
        raise ValueError("Source-event cluster report is not complete")
    expected_midi_hash = (clusters.get("midi") or {}).get("sha256")
    if expected_midi_hash != _sha256(primary_midi):
        raise ValueError("Primary MIDI hash does not match the cluster report")

    available_clusters = {
        str(row.get("cluster_id"))
        for row in clusters.get("identity_candidate_clusters", [])
    }
    selected_cluster = str(body_cluster).strip().upper()
    if selected_cluster not in available_clusters:
        choices = ", ".join(sorted(available_clusters)) or "none"
        raise ValueError(
            f"body_cluster {selected_cluster!r} is unavailable; choose from {choices}"
        )

    primary_clips = read_midi_clips(primary_midi)
    if len(primary_clips) != 1:
        raise ValueError("Primary MIDI must contain exactly one note-bearing track")
    primary_clip = primary_clips[0]
    _require_constant_tempo(primary_clip, "Primary MIDI")
    primary_notes = list(primary_clip.notes)

    clustered_indices = {
        int(row["note_index"])
        for row in clusters.get("events", [])
        if row.get("identity_candidate_cluster") == selected_cluster
    }
    if not clustered_indices:
        raise ValueError("Selected body cluster contains no MIDI notes")
    invalid_indices = sorted(
        index for index in clustered_indices if not 0 <= index < len(primary_notes)
    )
    if invalid_indices:
        raise ValueError(
            "Cluster report contains note indices outside the primary MIDI: "
            + ", ".join(str(value) for value in invalid_indices)
        )

    body_notes = [note for index, note in enumerate(primary_notes) if index in clustered_indices]
    complement_notes = [
        note for index, note in enumerate(primary_notes) if index not in clustered_indices
    ]
    if not complement_notes:
        raise ValueError("Selected body cluster leaves no contrast notes to review")

    secondary_clip = None
    secondary_notes: list[Any] = []
    if secondary_midi is not None:
        secondary_clips = read_midi_clips(secondary_midi)
        if len(secondary_clips) != 1:
            raise ValueError("Secondary MIDI must contain exactly one note-bearing track")
        secondary_clip = secondary_clips[0]
        _require_constant_tempo(secondary_clip, "Secondary MIDI")
        if abs(secondary_clip.bpm - primary_clip.bpm) > 1e-6:
            raise ValueError("Primary and secondary MIDI must have the same BPM")
        secondary_notes = list(secondary_clip.notes)

    cluster_source = _required_file(
        (clusters.get("source") or {}).get("path"), "Cluster source audio"
    )
    if (clusters.get("source") or {}).get("sha256") != _sha256(cluster_source):
        raise ValueError("Cluster source audio hash does not match the report")

    reviewed_cleanup = None
    if cleanup_review is not None:
        reviewed_cleanup = _validate_cleanup_review(cleanup_review, cluster_source)

    work = destination.with_name(
        f".{destination.name}.building-{uuid.uuid4().hex}"
    )
    work.parent.mkdir(parents=True, exist_ok=True)
    work.mkdir()
    try:
        shutil.copyfile(primary_midi, work / "primary-unchanged.mid")
        shutil.copyfile(cluster_source, work / "reference-primary.wav")
        if secondary_audio is not None:
            shutil.copyfile(secondary_audio, work / "reference-secondary.wav")

        bpm = float(primary_clip.bpm)
        body_events = _note_events(body_notes)
        complement_events = _note_events(complement_notes)
        secondary_events = _note_events(secondary_notes)
        write_midi_file(
            work / "body.mid",
            [MidiTrack(str(body_name), 0, int(body_program), body_events)],
            bpm=bpm,
        )
        write_midi_file(
            work / "primary-pluck-candidate.mid",
            [MidiTrack(str(pluck_name), 1, int(pluck_program), complement_events)],
            bpm=bpm,
        )
        write_midi_file(
            work / "two-role-primary-partition.mid",
            [
                MidiTrack(str(body_name), 0, int(body_program), body_events),
                MidiTrack(str(pluck_name), 1, int(pluck_program), complement_events),
            ],
            bpm=bpm,
        )
        if secondary_events:
            write_midi_file(
                work / "secondary-pluck-candidate.mid",
                [MidiTrack(str(pluck_name), 1, int(pluck_program), secondary_events)],
                bpm=bpm,
            )
            write_midi_file(
                work / "two-role-independent-pluck.mid",
                [
                    MidiTrack(str(body_name), 0, int(body_program), body_events),
                    MidiTrack(str(pluck_name), 1, int(pluck_program), secondary_events),
                ],
                bpm=bpm,
            )

        midi_names = [
            "primary-unchanged.mid",
            "body.mid",
            "primary-pluck-candidate.mid",
            "two-role-primary-partition.mid",
        ]
        if secondary_events:
            midi_names.extend(
                ["secondary-pluck-candidate.mid", "two-role-independent-pluck.mid"]
            )
        preview_names: dict[str, str] = {}
        if render_preview:
            from .render import render_midi_to_wav

            for midi_name in midi_names:
                wav_name = Path(midi_name).with_suffix(".wav").name
                render_midi_to_wav(work / midi_name, work / wav_name)
                preview_names[midi_name] = wav_name

        original_signatures = _note_signatures(primary_notes)
        strict_signatures = _note_signatures(body_notes) + _note_signatures(
            complement_notes
        )
        if original_signatures != strict_signatures:
            raise RuntimeError("Strict role partition did not preserve the primary notes")
        written_strict_signatures = _clip_note_signatures(
            read_midi_clips(work / "two-role-primary-partition.mid")
        )
        if original_signatures != written_strict_signatures:
            raise RuntimeError(
                "Written strict role partition changed primary note timing or values"
            )
        if secondary_notes:
            written_secondary_signatures = _clip_note_signatures(
                read_midi_clips(work / "secondary-pluck-candidate.mid")
            )
            if _note_signatures(secondary_notes) != written_secondary_signatures:
                raise RuntimeError(
                    "Written independent pluck candidate changed secondary notes"
                )

        event_by_index = {
            int(row["note_index"]): row for row in clusters.get("events", [])
        }
        body_cluster_summary = next(
            row
            for row in clusters.get("identity_candidate_clusters", [])
            if row.get("cluster_id") == selected_cluster
        )
        complement_cluster_counts: dict[str, int] = {}
        outlier_count = 0
        unprofiled_count = 0
        for index in range(len(primary_notes)):
            if index in clustered_indices:
                continue
            row = event_by_index.get(index)
            if row is None:
                unprofiled_count += 1
            elif row.get("identity_outlier"):
                outlier_count += 1
            else:
                cluster_id = str(row.get("identity_candidate_cluster"))
                complement_cluster_counts[cluster_id] = (
                    complement_cluster_counts.get(cluster_id, 0) + 1
                )

        report: dict[str, Any] = {
            "schema": MIDI_ROLE_SPLIT_SCHEMA,
            "operation": "midi-role-split",
            "status": "review-required",
            "advisory_only": True,
            "automatic_promotion": False,
            "physical_instrument_identified": False,
            "bpm": bpm,
            "inputs": {
                "primary_midi": _file_record(primary_midi),
                "cluster_report": _file_record(cluster_path),
                "cluster_source_audio": _file_record(cluster_source),
                "secondary_midi": (
                    _file_record(secondary_midi) if secondary_midi else None
                ),
                "secondary_audio": (
                    _file_record(secondary_audio) if secondary_audio else None
                ),
                "cleanup_review": (
                    _file_record(cleanup_review) if cleanup_review else None
                ),
            },
            "reviewed_cleanup": reviewed_cleanup,
            "policy": {
                "body_cluster": selected_cluster,
                "body_cluster_selection": "explicit command-line choice backed by user listening",
                "body_name": str(body_name),
                "body_program": int(body_program),
                "pluck_name": str(pluck_name),
                "pluck_program": int(pluck_program),
                "strict_pluck": "every primary note outside the explicit body cluster, including retained outliers and unprofiled notes",
                "independent_pluck": "all notes from the explicitly supplied secondary MIDI; no deduplication or automatic merge",
            },
            "evidence": {
                "cluster_summary": clusters.get("summary"),
                "body_cluster_summary": body_cluster_summary,
                "body_note_count": len(body_notes),
                "primary_complement_note_count": len(complement_notes),
                "primary_complement_cluster_counts": complement_cluster_counts,
                "primary_complement_outlier_count": outlier_count,
                "primary_complement_unprofiled_count": unprofiled_count,
                "secondary_note_count": len(secondary_notes),
                "secondary_maximum_simultaneous_notes": (
                    _maximum_simultaneous_notes(secondary_notes)
                    if secondary_notes
                    else 0
                ),
            },
            "effects": {
                "input_files_mutated": False,
                "primary_notes_changed_in_strict_partition": 0,
                "primary_pitches_changed": 0,
                "primary_onsets_changed": 0,
                "primary_durations_changed": 0,
                "primary_velocities_changed": 0,
                "secondary_notes_changed": 0,
                "automatic_role_selection": False,
                "automatic_instrument_selection": False,
            },
            "artifacts": {},
            "warnings": [
                "Candidate timbre clusters are listening evidence, not proof of physical instruments.",
                "The strict partition preserves every primary note but may divide articulations rather than performers.",
                "The independent pluck challenger can overlap the body and can also contain residual bleed or octave errors.",
                "General MIDI programs are contrasting audition proxies; select GarageBand patches separately by ear.",
            ],
        }
        for name in [
            "primary-unchanged.mid",
            "reference-primary.wav",
            *(["reference-secondary.wav"] if secondary_audio is not None else []),
            *midi_names[1:],
            *preview_names.values(),
        ]:
            report["artifacts"][name] = _relative_file_record(work / name, work)

        review_seed = _review_seed(report, preview_names, secondary_audio is not None)
        _write_json(work / "midi_role_split_review.json", review_seed)
        (work / "midi_role_split_review.html").write_text(
            _review_html(review_seed), encoding="utf-8"
        )
        report["artifacts"]["midi_role_split_review.json"] = _relative_file_record(
            work / "midi_role_split_review.json", work
        )
        report["artifacts"]["midi_role_split_review.html"] = _relative_file_record(
            work / "midi_role_split_review.html", work
        )
        _write_json(work / "midi_role_split.json", report)
        work.rename(destination)
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise

    final = json.loads(
        (destination / "midi_role_split.json").read_text(encoding="utf-8")
    )
    final["report"] = str(destination / "midi_role_split.json")
    final["review_html"] = str(destination / "midi_role_split_review.html")
    return final


def resolve_midi_role_split(
    review_path: str | Path,
    role_split_dir: str | Path,
    *,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Resolve one complete user export without changing any source artifact."""

    review_file = _required_file(review_path, "Reviewed role-split JSON")
    source_dir = Path(role_split_dir).expanduser().resolve()
    if not source_dir.is_dir():
        raise ValueError(f"Role-split directory not found: {source_dir}")
    report_path = _required_file(source_dir / "midi_role_split.json", "Role-split report")
    seed_path = _required_file(
        source_dir / "midi_role_split_review.json", "Role-split review seed"
    )
    destination = Path(out_dir).expanduser()
    if destination.exists():
        raise FileExistsError(f"Output directory already exists: {destination}")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    review = json.loads(review_file.read_text(encoding="utf-8"))
    if report.get("schema") != MIDI_ROLE_SPLIT_SCHEMA:
        raise ValueError("Unsupported role-split report schema")
    if report.get("status") != "review-required":
        raise ValueError("Role-split report is not reviewable")
    if seed.get("schema") != MIDI_ROLE_SPLIT_REVIEW_SCHEMA:
        raise ValueError("Unsupported role-split review seed schema")
    if seed.get("status") != "unreviewed":
        raise ValueError("Role-split review seed was unexpectedly modified")
    if review.get("schema") != MIDI_ROLE_SPLIT_REVIEW_SCHEMA:
        raise ValueError("Unsupported reviewed role-split schema")
    if review.get("status") != "reviewed":
        raise ValueError("Role-split review must be explicitly reviewed")
    if review.get("experiment") != seed.get("experiment"):
        raise ValueError("Reviewed experiment hashes do not match the source seed")
    if review.get("automatic_promotion") is not False:
        raise ValueError("Reviewed role split must retain automatic_promotion=false")

    decision = str(review.get("overall_decision") or "")
    if decision not in _DECISION_ARTIFACTS:
        raise ValueError("Reviewed role split has no valid overall decision")
    _validate_review_choices(seed.get("choices", []), review.get("choices", []))
    _validate_report_artifacts(report, source_dir)
    _validate_report_inputs(report)

    selected_name = _DECISION_ARTIFACTS[decision]
    selected_path = source_dir / selected_name if selected_name else None
    if selected_path is not None and not selected_path.is_file():
        raise ValueError(f"Selected MIDI artifact is missing: {selected_path}")
    if selected_path is not None:
        selected_hash = _sha256(selected_path)
        experiment = review["experiment"]
        if selected_name == "primary-unchanged.mid":
            expected_selected_hash = experiment.get("primary_midi_sha256")
        else:
            expected_selected_hash = (
                experiment.get("candidate_midi_sha256") or {}
            ).get(selected_name)
        if not expected_selected_hash:
            raise ValueError(
                "Reviewed export does not pin the selected challenger MIDI; "
                "create a fresh role-split review"
            )
        if selected_hash != expected_selected_hash:
            raise ValueError("Selected MIDI hash does not match the reviewed export")

    work = destination.with_name(
        f".{destination.name}.building-{uuid.uuid4().hex}"
    )
    work.parent.mkdir(parents=True, exist_ok=True)
    work.mkdir()
    try:
        shutil.copyfile(review_file, work / "reviewed-role-split.json")
        shutil.copyfile(report_path, work / "source-role-split-report.json")
        shutil.copyfile(seed_path, work / "source-review-seed.json")
        recommended = None
        if selected_path is not None:
            shutil.copyfile(selected_path, work / "recommended.mid")
            if _sha256(work / "recommended.mid") != _sha256(selected_path):
                raise RuntimeError("Resolved MIDI copy does not match the reviewed source")
            recommended = _relative_file_record(work / "recommended.mid", work)

        main_choice_ids = [
            str(row["id"])
            for row in review["choices"]
            if row.get("usefulness") == "main"
        ]
        resolution: dict[str, Any] = {
            "schema": MIDI_ROLE_SPLIT_RESOLUTION_SCHEMA,
            "operation": "midi-role-split-resolve",
            "status": "complete" if selected_path is not None else "no-selection",
            "selection_source": "explicit-user-review",
            "automatic_promotion": False,
            "decision": decision,
            "overall_notes": str(review.get("overall_notes") or ""),
            "reviewed_at": review.get("reviewed_at"),
            "bpm": report.get("bpm"),
            "recommended_source_artifact": selected_name,
            "recommended": recommended,
            "review": _file_record(review_file),
            "source": {
                "directory": str(source_dir),
                "report": _file_record(report_path),
                "seed": _file_record(seed_path),
            },
            "choice_summary": {
                "main": main_choice_ids,
                "secondary": [
                    str(row["id"])
                    for row in review["choices"]
                    if row.get("usefulness") == "secondary"
                ],
                "diagnostic": [
                    str(row["id"])
                    for row in review["choices"]
                    if row.get("usefulness") == "diagnostic"
                ],
                "rejected": [
                    str(row["id"])
                    for row in review["choices"]
                    if row.get("usefulness") == "reject"
                ],
            },
            "choices": review["choices"],
            "effects": {
                "source_tree_mutated": False,
                "source_midi_mutated": False,
                "recommended_midi_notes_changed": 0,
                "instrument_selected": False,
                "alternatives_deleted": 0,
                "automatic_promotion": False,
            },
            "warnings": [
                "The overall decision controls the recommendation even when individual component auditions were useful.",
                "A retained component is not a selected physical instrument or GarageBand patch.",
            ],
        }
        _write_json(work / "midi_role_split_resolution.json", resolution)
        (work / "RECOMMENDATION.md").write_text(
            _resolution_markdown(resolution), encoding="utf-8"
        )
        work.rename(destination)
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise

    final = json.loads(
        (destination / "midi_role_split_resolution.json").read_text(
            encoding="utf-8"
        )
    )
    final["report"] = str(destination / "midi_role_split_resolution.json")
    final["recommendation"] = str(destination / "RECOMMENDATION.md")
    if selected_path is not None:
        final["recommended_midi"] = str(destination / "recommended.mid")
    return final


def _validate_cleanup_review(review_path: Path, cluster_source: Path) -> dict[str, Any]:
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if review.get("schema") != "sunofriend.ai-cleanup-review.v1":
        raise ValueError("Unsupported cleanup review schema")
    if review.get("status") != "reviewed":
        raise ValueError("Cleanup review must be explicitly reviewed")
    if any(not bool(row.get("reviewed")) for row in review.get("choices", [])):
        raise ValueError("Cleanup review contains unreviewed choices")
    cleanup_report = cluster_source.parent / "ai_cleanup.json"
    experiment = review.get("experiment") or {}
    expected_hash = experiment.get("cleanup_report_sha256")
    if expected_hash is not None:
        if not cleanup_report.is_file():
            raise ValueError("Cleanup review pins a report that is missing beside the source")
        if _sha256(cleanup_report) != expected_hash:
            raise ValueError("Cleanup report hash does not match the reviewed evidence")
    return {
        "schema": review["schema"],
        "status": review["status"],
        "overall_decision": review.get("overall_decision"),
        "overall_notes": review.get("overall_notes"),
        "reviewed_at": review.get("reviewed_at"),
        "review_sha256": _sha256(review_path),
        "cleanup_report_sha256": expected_hash,
    }


def _validate_review_choices(
    seed_choices: Sequence[dict[str, Any]], reviewed_choices: Sequence[dict[str, Any]]
) -> None:
    seed_by_id = {str(row.get("id")): row for row in seed_choices}
    reviewed_by_id = {str(row.get("id")): row for row in reviewed_choices}
    if len(seed_by_id) != len(seed_choices) or len(reviewed_by_id) != len(
        reviewed_choices
    ):
        raise ValueError("Role-split review contains duplicate choice IDs")
    if seed_by_id.keys() != reviewed_by_id.keys():
        raise ValueError("Reviewed role-split choices do not match the source seed")
    for identifier, seed in seed_by_id.items():
        reviewed = reviewed_by_id[identifier]
        for field in ("id", "title", "audio", "purpose"):
            if reviewed.get(field) != seed.get(field):
                raise ValueError(
                    f"Reviewed choice {identifier!r} changed pinned field {field!r}"
                )
        if reviewed.get("reviewed") is not True:
            raise ValueError(f"Role-split choice {identifier!r} is not reviewed")
        if reviewed.get("role") not in _ROLE_VALUES:
            raise ValueError(f"Role-split choice {identifier!r} has no valid role")
        if reviewed.get("usefulness") not in _USEFULNESS_VALUES:
            raise ValueError(
                f"Role-split choice {identifier!r} has no valid usefulness"
            )


def _validate_report_artifacts(report: dict[str, Any], source_dir: Path) -> None:
    artifacts = report.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise ValueError("Role-split report contains no artifact manifest")
    for name, record in artifacts.items():
        if not isinstance(record, dict):
            raise ValueError(f"Invalid artifact record: {name}")
        relative = Path(str(record.get("path") or ""))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Unsafe artifact path: {relative}")
        if str(relative) != str(name):
            raise ValueError(f"Artifact manifest path does not match its name: {name}")
        artifact = _required_file(source_dir / relative, f"Role-split artifact {name}")
        if artifact.stat().st_size != int(record.get("bytes", -1)):
            raise ValueError(f"Role-split artifact size changed: {name}")
        if _sha256(artifact) != record.get("sha256"):
            raise ValueError(f"Role-split artifact hash changed: {name}")


def _validate_report_inputs(report: dict[str, Any]) -> None:
    inputs = report.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("Role-split report contains no input manifest")
    for name, record in inputs.items():
        if record is None:
            continue
        if not isinstance(record, dict):
            raise ValueError(f"Invalid role-split input record: {name}")
        path = _required_file(record.get("path"), f"Role-split input {name}")
        if path.stat().st_size != int(record.get("bytes", -1)):
            raise ValueError(f"Role-split input size changed: {name}")
        if _sha256(path) != record.get("sha256"):
            raise ValueError(f"Role-split input hash changed: {name}")


def _resolution_markdown(resolution: dict[str, Any]) -> str:
    decision = resolution["decision"]
    descriptions = {
        "keep_primary": (
            "Use `recommended.mid`, an exact copy of the unchanged primary MIDI. "
            "The strict body/pluck components remain useful optional resources, "
            "but the residual-derived overlap is diagnostic only."
        ),
        "strict_partition": (
            "Use `recommended.mid`, the exact primary note set divided between "
            "the reviewed body and pluck tracks."
        ),
        "independent_pluck": (
            "Use `recommended.mid`, the reviewed body plus independently "
            "transcribed residual-pluck challenger."
        ),
        "none": "No MIDI was selected. Return to the preserved source alternatives.",
    }
    recommended = (
        "`recommended.mid`" if resolution.get("recommended") else "no MIDI file"
    )
    return (
        "# MIDI role-split resolution\n\n"
        f"Decision: **{decision}**. Recommended artifact: {recommended}.\n\n"
        f"{descriptions[decision]}\n\n"
        f"GarageBand tempo: **{float(resolution['bpm']):.6f} BPM**. "
        "The embedded GM program is an audition hint only; choose the final "
        "GarageBand patch by ear. No source MIDI, alternative or instrument "
        "selection was changed automatically.\n"
    )


def _review_seed(
    report: dict[str, Any], previews: dict[str, str], has_secondary_audio: bool
) -> dict[str, Any]:
    choices = [
        _review_choice(
            "reference_primary",
            "Accepted learned bass target audio",
            "reference-primary.wav",
            "Listen for the deep body and the plucked articulation together.",
        ),
        _review_choice(
            "primary_unchanged_midi",
            "Unchanged primary MIDI",
            previews.get("primary-unchanged.mid"),
            "The current one-track MuScriptor result through its original bass proxy.",
        ),
        _review_choice(
            "body_only",
            "Explicit body cluster only",
            previews.get("body.mid"),
            "Longer/lower source-event cluster, played as a synth-bass proxy.",
        ),
        _review_choice(
            "primary_pluck_only",
            "Primary complement only",
            previews.get("primary-pluck-candidate.mid"),
            "Every primary note outside the body cluster, including outliers.",
        ),
        _review_choice(
            "strict_two_role",
            "Strict two-role partition",
            previews.get("two-role-primary-partition.mid"),
            "The exact primary notes divided between synth-bass and muted-guitar proxies.",
        ),
    ]
    if report["evidence"]["secondary_note_count"]:
        if has_secondary_audio:
            choices.append(
                _review_choice(
                    "reference_secondary",
                    "Musical residual audio",
                    "reference-secondary.wav",
                    "The residual you identified as containing a clearer pluck.",
                )
            )
        choices.extend(
            [
                _review_choice(
                    "independent_pluck_only",
                    "Residual-transcribed pluck only",
                    previews.get("secondary-pluck-candidate.mid"),
                    "Independent MuScriptor notes from the residual, including octave pairs.",
                ),
                _review_choice(
                    "independent_two_role",
                    "Body plus independent residual pluck",
                    previews.get("two-role-independent-pluck.mid"),
                    "The body cluster plus a separately transcribed overlapping pluck challenger.",
                ),
            ]
        )
    return {
        "schema": MIDI_ROLE_SPLIT_REVIEW_SCHEMA,
        "status": "unreviewed",
        "automatic_promotion": False,
        "experiment": {
            "primary_midi_sha256": report["inputs"]["primary_midi"]["sha256"],
            "cluster_report_sha256": report["inputs"]["cluster_report"]["sha256"],
            "secondary_midi_sha256": (
                report["inputs"]["secondary_midi"]["sha256"]
                if report["inputs"]["secondary_midi"]
                else None
            ),
            "body_cluster": report["policy"]["body_cluster"],
            "bpm": report["bpm"],
            "candidate_midi_sha256": {
                name: report["artifacts"][name]["sha256"]
                for name in _DECISION_ARTIFACTS.values()
                if name is not None and name in report["artifacts"]
            },
        },
        "overall_decision": None,
        "overall_notes": "",
        "choices": choices,
    }


def _review_choice(identifier: str, title: str, audio: str | None, purpose: str):
    return {
        "id": identifier,
        "title": title,
        "audio": audio,
        "purpose": purpose,
        "role": "",
        "usefulness": "",
        "notes": "",
        "reviewed": False,
    }


def _review_html(seed: dict[str, Any]) -> str:
    cards = []
    for choice in seed["choices"]:
        audio = (
            f'<audio controls preload="metadata" src="{html.escape(choice["audio"])}"></audio>'
            if choice.get("audio")
            else '<p class="missing">No rendered preview; import the adjacent MIDI into GarageBand.</p>'
        )
        cards.append(
            f"""
<section class="card" data-choice="{html.escape(choice['id'])}">
  <h2>{html.escape(choice['title'])}</h2>
  <p>{html.escape(choice['purpose'])}</p>
  {audio}
  <div class="grid">
    <label>What do you hear?
      <select class="role"><option value="">Choose…</option><option value="deep_body">Deep synth-bass body</option><option value="pluck">Plucked line</option><option value="both">Both roles</option><option value="fragments">Fragments / artefacts</option></select>
    </label>
    <label>Usefulness
      <select class="usefulness"><option value="">Choose…</option><option value="main">Main part</option><option value="secondary">Secondary layer</option><option value="diagnostic">Diagnostic only</option><option value="reject">Reject</option></select>
    </label>
  </div>
  <label>Notes<textarea class="notes" rows="3" placeholder="Recognition, missing notes, false notes, tone, overlap…"></textarea></label>
  <label class="reviewed"><input type="checkbox" class="reviewed-box"> Reviewed this sound</label>
</section>"""
        )
    seed_json = json.dumps(seed, sort_keys=True).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sunofriend MIDI role-split review</title>
<style>
body{{margin:0;background:#0f151c;color:#edf4fb;font:17px/1.45 system-ui,sans-serif}}main{{max-width:1050px;margin:auto;padding:36px 24px 80px}}h1{{font-size:clamp(2.2rem,6vw,4rem);margin:.1em 0}}.intro,.controls,.card{{background:#18232e;border:1px solid #385064;border-radius:18px;padding:24px;margin:22px 0}}.card h2{{margin-top:0}}audio{{width:100%;margin:10px 0 18px}}label{{display:block;font-weight:650}}select,textarea{{box-sizing:border-box;width:100%;margin-top:7px;background:#0f151c;color:#edf4fb;border:1px solid #56748b;border-radius:8px;padding:10px;font:inherit}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}button{{background:#2f6288;color:white;border:1px solid #7ab9e8;border-radius:10px;padding:12px 18px;font:inherit;margin:5px}}.reviewed{{margin-top:15px}}.reviewed input{{width:auto}}.count{{color:#ffd166;font-size:1.2rem}}.missing{{color:#ffd166}}code{{color:#9bdcff}}@media(max-width:700px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><main>
<h1>Sunofriend MIDI role-split review</h1>
<div class="intro"><p><strong>Goal:</strong> test your observation that this bass stem contains a deep synth-bass body and a separate plucked line. This is not instrument recognition. The strict split preserves every primary note; the independent split may recover overlapping pluck notes from the residual.</p><p>Judge recognition and musical usefulness first. The synth-bass and muted-guitar sounds are contrasting GM proxies; choose final GarageBand patches later.</p></div>
<div class="controls"><p class="count" id="count">Reviewed 0 of {len(seed['choices'])} sounds</p><button id="mark">Mark all current choices reviewed</button><button id="export">Export review JSON</button><label>Overall decision<select id="decision"><option value="">Choose…</option><option value="keep_primary">Keep unchanged primary MIDI</option><option value="strict_partition">Use strict two-role partition</option><option value="independent_pluck">Use body plus independent residual pluck</option><option value="none">None are ready</option></select></label><label>Overall notes<textarea id="overall" rows="4"></textarea></label></div>
{''.join(cards)}
<script>
const seed={seed_json};
const cards=[...document.querySelectorAll('.card')];
function update(){{const n=cards.filter(c=>c.querySelector('.reviewed-box').checked).length;document.getElementById('count').textContent=`Reviewed ${{n}} of ${{cards.length}} sounds`;}}
cards.forEach(c=>c.querySelector('.reviewed-box').addEventListener('change',update));
document.getElementById('mark').onclick=()=>{{cards.forEach(c=>c.querySelector('.reviewed-box').checked=true);update();}};
document.getElementById('export').onclick=()=>{{
 const choices=cards.map(c=>{{const old=seed.choices.find(x=>x.id===c.dataset.choice);return{{...old,role:c.querySelector('.role').value,usefulness:c.querySelector('.usefulness').value,notes:c.querySelector('.notes').value.trim(),reviewed:c.querySelector('.reviewed-box').checked}};}});
 const decision=document.getElementById('decision').value;
 if(!decision||choices.some(c=>!c.reviewed||!c.role||!c.usefulness)){{alert('Choose a role and usefulness, mark every sound reviewed, and select an overall decision.');return;}}
 const output={{...seed,status:'reviewed',reviewed_at:new Date().toISOString(),overall_decision:decision,overall_notes:document.getElementById('overall').value.trim(),choices}};
 const blob=new Blob([JSON.stringify(output,null,2)+'\\n'],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='midi_role_split_review.reviewed.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);
}};
</script></main></body></html>"""


def _note_events(notes: Iterable[Any]) -> list[NoteEvent]:
    return [
        NoteEvent(
            start=float(note.source_start_seconds),
            end=float(note.source_end_seconds),
            pitch=int(note.pitch),
            velocity=int(note.velocity),
        )
        for note in notes
    ]


def _note_signatures(
    notes: Iterable[Any],
) -> Counter[tuple[float, float, int, int]]:
    return Counter(
        (
            round(float(note.start_beat), 9),
            round(float(note.duration_beats), 9),
            int(note.pitch),
            int(note.velocity),
        )
        for note in notes
    )


def _clip_note_signatures(clips: Sequence[MidiClip]):
    result: Counter[tuple[float, float, int, int]] = Counter()
    for clip in clips:
        result += _note_signatures(clip.notes)
    return result


def _maximum_simultaneous_notes(notes: Sequence[Any]) -> int:
    events = []
    for note in notes:
        events.append((float(note.start_beat), 1))
        events.append((float(note.end_beat), -1))
    active = maximum = 0
    for _, delta in sorted(events, key=lambda item: (item[0], item[1])):
        active += delta
        maximum = max(maximum, active)
    return maximum


def _require_constant_tempo(clip: MidiClip, label: str) -> None:
    if len(clip.tempo_map.tempo_points) != 1:
        raise ValueError(f"{label} must use one constant tempo for role-split v1")


def _required_file(path: str | Path | None, label: str) -> Path:
    if path is None:
        raise ValueError(f"{label} path is missing")
    candidate = Path(path).expanduser()
    if not candidate.is_file():
        raise ValueError(f"{label} not found: {candidate}")
    return candidate.resolve()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _file_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _relative_file_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(root)),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


__all__ = [
    "MIDI_ROLE_SPLIT_REVIEW_SCHEMA",
    "MIDI_ROLE_SPLIT_RESOLUTION_SCHEMA",
    "MIDI_ROLE_SPLIT_SCHEMA",
    "create_midi_role_split",
    "resolve_midi_role_split",
]
