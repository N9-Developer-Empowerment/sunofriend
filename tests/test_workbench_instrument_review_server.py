from __future__ import annotations

import hashlib
import http.client
import json
import sqlite3
import threading
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile

import sunofriend.workbench_server as workbench_server
from sunofriend.clip import read_midi_clips
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.midi_transform import _parse_midi
from sunofriend.models import NoteEvent
from sunofriend.workbench_catalog import build_workbench_catalog
from sunofriend.workbench_developer import (
    WorkbenchDeveloperTrace,
    developer_code_step_for_route,
    developer_operation_for_route,
    trace_response_facts,
)
from sunofriend.workbench_server import create_workbench_server


def _render_program(
    midi_path: str | Path,
    wav_path: str | Path,
    **kwargs: object,
) -> None:
    layout = _parse_midi(Path(midi_path).read_bytes())
    programs = [
        event.data[0]
        for track in layout.tracks
        for event in track.events
        if event.category == "channel" and event.event_type == 0xC0
    ]
    program = programs[-1]
    sample_rate = int(kwargs["sample_rate"])
    if "keys-coverage" in Path(midi_path).name:
        clips = read_midi_clips(midi_path)
        duration = (
            max(
                (
                    float(note.source_end_seconds)
                    for clip in clips
                    for note in clip.notes
                ),
                default=0.0,
            )
            + 0.1
        )
        audio = np.zeros(
            (int(np.ceil(duration * sample_rate)), 1),
            dtype="float32",
        )
        for clip in clips:
            for note in clip.notes:
                amplitude = 0.03 * int(note.velocity) / 127.0
                start = int(round(float(note.source_start_seconds) * sample_rate))
                end = int(round(float(note.source_end_seconds) * sample_rate))
                audio[start:end, 0] = amplitude
        soundfile.write(
            str(wav_path),
            audio,
            sample_rate,
            subtype="PCM_16",
        )
        return
    amplitude = {4: 0.12, 5: 0.18, 38: 0.1, 39: 0.2}[program]
    soundfile.write(
        str(wav_path),
        np.full((sample_rate * 2, 1), amplitude, dtype="float32"),
        sample_rate,
        subtype="PCM_16",
    )


def _render_keys_challenger_silent(
    midi_path: str | Path,
    wav_path: str | Path,
    **kwargs: object,
) -> None:
    _render_program(midi_path, wav_path, **kwargs)
    if "keys-coverage" not in Path(midi_path).name:
        return
    layout = _parse_midi(Path(midi_path).read_bytes())
    programs = [
        event.data[0]
        for track in layout.tracks
        for event in track.events
        if event.category == "channel" and event.event_type == 0xC0
    ]
    if programs[-1] != 5:
        return
    info = soundfile.info(str(wav_path))
    soundfile.write(
        str(wav_path),
        np.zeros((info.frames, info.channels), dtype="float32"),
        info.samplerate,
        subtype="PCM_16",
    )


def _catalog(root: Path) -> tuple[dict, Path]:
    project = root / "Instrument Song-D minor-120bpm-440hz"
    candidates = root / "candidates"
    project.mkdir()
    candidates.mkdir()
    source = project / "Instrument Song-bass-D minor-120bpm-440hz.wav"
    soundfile.write(
        source,
        np.full((16_000, 1), 0.4, dtype="float32"),
        8_000,
        subtype="PCM_16",
    )
    midi = candidates / "bass.mid"
    write_midi_file(
        midi,
        [
            MidiTrack(
                "Bass",
                0,
                38,
                [
                    NoteEvent(0.0, 0.75, 40, 91),
                    NoteEvent(0.75, 2.0, 43, 86),
                ],
            )
        ],
        bpm=120.0,
    )
    keys_source = project / "Instrument Song-keys-D minor-120bpm-440hz.wav"
    soundfile.write(
        keys_source,
        np.full((16_000, 1), 0.35, dtype="float32"),
        8_000,
        subtype="PCM_16",
    )
    keys_midi = candidates / "keys.mid"
    write_midi_file(
        keys_midi,
        [
            MidiTrack(
                "Keys",
                0,
                4,
                [
                    NoteEvent(0.0, 0.25, 60, 31),
                    NoteEvent(0.25, 0.75, 60, 64),
                    NoteEvent(0.75, 1.25, 64, 100),
                ],
            )
        ],
        bpm=120.0,
    )
    catalog_path = root / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "schema": "sunofriend.workbench-catalog.v1",
                "stems": [
                    {
                        "source": str(source),
                        "role": "bass",
                        "candidates": [
                            {
                                "midi": str(midi),
                                "label": "Selected bass",
                            }
                        ],
                    },
                    {
                        "source": str(keys_source),
                        "role": "keys",
                        "candidates": [
                            {
                                "midi": str(keys_midi),
                                "label": "Selected keys",
                            }
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    soundfont = root / "review.sf2"
    soundfont.write_bytes(b"instrument-review-test-bank")
    return (
        build_workbench_catalog(
            project,
            candidate_roots=[candidates],
            catalog_path=catalog_path,
        ),
        soundfont,
    )


class _InstrumentHTTP:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.catalog, self.soundfont = _catalog(root)
        self.renderer = root / "fluidsynth"
        self.renderer.write_bytes(b"private-test-renderer")
        self.state_dir = root / "state"
        self.token = "instrument-review-server-token"
        self._renderer_patch = patch(
            "sunofriend.workbench_instrument_review.find_fluidsynth",
            return_value=str(self.renderer),
        )
        self._render_patch = patch(
            "sunofriend.workbench_instrument_review.render_midi_to_wav",
            side_effect=_render_program,
        )
        self._renderer_patch.start()
        self._render_mock = self._render_patch.start()
        self.server = self._server()
        for stem in self.catalog["stems"]:
            candidate = stem["candidates"][0]
            self.server.store.append(
                self.catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "decision": "main",
                    "context": "full_mix",
                    "problem_tags": [],
                    "notes": "private selection note",
                },
            )
        self._start()

    def _server(self):
        return create_workbench_server(
            self.catalog,
            state_dir=self.state_dir,
            token=self.token,
            soundfont_path=self.soundfont,
            developer_inspector=True,
        )

    def _start(self) -> None:
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self._render_patch.stop()
        self._renderer_patch.stop()

    def restart(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.server = self._server()
        self._start()

    def request(
        self,
        method: str,
        route: str,
        body: dict | None = None,
    ) -> tuple[int, dict, bytes]:
        connection = http.client.HTTPConnection(
            "127.0.0.1",
            self.server.server_port,
            timeout=10,
        )
        payload = json.dumps(body) if body is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        connection.request(method, route, body=payload, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        content_type = response.getheader("Content-Type", "")
        value = (
            json.loads(raw.decode("utf-8"))
            if content_type.startswith("application/json")
            else {}
        )
        status = response.status
        connection.close()
        return status, value, raw

    def json(
        self,
        method: str,
        route: str,
        body: dict | None = None,
    ) -> tuple[int, dict]:
        status, value, _raw = self.request(method, route, body)
        return status, value

    def plan(self) -> dict:
        status, payload = self.json(
            "GET",
            f"/api/instrument-review-plan?token={self.token}",
        )
        assert status == 200, payload
        return payload["plan"]

    def prepare(self, role: str = "bass") -> dict:
        lane = next(row for row in self.plan()["eligible_lanes"] if row["role"] == role)
        status, payload = self.json(
            "POST",
            f"/api/instrument-review/prepare?token={self.token}",
            {
                "selection_manifest_sha256": lane["selection_manifest_sha256"],
                "stem_id": lane["stem_id"],
                "candidate_id": lane["candidate_id"],
                "midi_sha256": lane["midi_sha256"],
                "start_seconds": 0,
                "end_seconds": 1,
            },
        )
        assert status == 200, payload
        return payload["comparison"]


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False


def _pack_event_count(database: Path) -> int:
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM pack_selection_events"
        ).fetchone()
    assert row is not None
    return int(row[0])


def test_plan_prepare_and_private_media_are_path_free_and_fixed(
    tmp_path: Path,
) -> None:
    fixture = _InstrumentHTTP(tmp_path)
    try:
        status, _value, source = fixture.request(
            "GET",
            "/workbench-instrument-review.js",
        )
        assert status == 200
        assert b"SunofriendWorkbenchInstrumentReview" in source
        plan = fixture.plan()
        assert plan["schema"] == "sunofriend.workbench-instrument-review-plan.v1"
        assert {row["role"] for row in plan["eligible_lanes"]} == {
            "bass",
            "keys",
        }
        markers = {
            row["role"]: row["coverage_preflight"] for row in plan["eligible_lanes"]
        }
        assert markers == {"bass": "not_required", "keys": "required"}
        pairs = {
            row["role"]: {
                row["pair"]["control"]["label"],
                row["pair"]["challenger"]["label"],
            }
            for row in plan["eligible_lanes"]
        }
        assert pairs == {
            "bass": {"Synth Bass 1", "Synth Bass 2"},
            "keys": {"Electric Piano 1", "Electric Piano 2"},
        }
        assert all(value is False for value in plan["effects"].values())
        assert not _contains_key(plan, "path")

        lane = next(row for row in plan["eligible_lanes"] if row["role"] == "bass")
        invalid = {
            "selection_manifest_sha256": lane["selection_manifest_sha256"],
            "stem_id": lane["stem_id"],
            "candidate_id": lane["candidate_id"],
            "midi_sha256": lane["midi_sha256"],
            "start_seconds": 0,
            "end_seconds": 1,
            "program": 39,
        }
        status, _payload = fixture.json(
            "POST",
            f"/api/instrument-review/prepare?token={fixture.token}",
            invalid,
        )
        assert status == 400

        event_count = fixture.server.store.current_state(fixture.catalog)["event_count"]
        comparison = fixture.prepare()
        assert comparison["schema"] == (
            "sunofriend.workbench-instrument-review.comparison.v1"
        )
        assert comparison["status"] == "unreviewed"
        assert comparison["role"] == "bass"
        assert comparison["review"] is None
        assert comparison["result"] is None
        assert not _contains_key(comparison, "path")
        assert "assignment" not in json.dumps(comparison, sort_keys=True)
        rows = {
            "source_reference": comparison["source_reference"],
            **comparison["candidates"],
        }
        assert set(rows) == {
            "source_reference",
            "candidate_a",
            "candidate_b",
        }
        assert all(-60.0 <= row["applied_gain_db"] <= 0.0 for row in rows.values())
        for row in rows.values():
            status, _value, raw = fixture.request("GET", row["audio_url"])
            assert status == 200
            assert raw[:4] == b"RIFF"
        status, snapshot = fixture.json(
            "GET",
            f"/api/developer-snapshot?token={fixture.token}",
        )
        assert status == 200
        operations = snapshot["runtime"]["trace"]["recent_operations"]
        plan_operation = next(
            row
            for row in reversed(operations)
            if row["operation"] == "instrument_review.plan"
            and row["http_status"] == 200
        )
        plan_facts = plan_operation["frames"][-1]["facts"]
        assert plan_facts["eligible_lane_count"] == 2
        assert plan_facts["eligible_bass_lane_count"] == 1
        assert plan_facts["eligible_keys_lane_count"] == 1
        assert plan_facts["coverage_required_lane_count"] == 1
        prepare = next(
            row
            for row in reversed(operations)
            if row["operation"] == "instrument_review.prepare"
            and row["http_status"] == 200
        )
        assert prepare["durable_effect_possible"] is True
        facts = next(
            frame["facts"]
            for frame in prepare["frames"]
            if frame["facts"].get("status") == "unreviewed"
        )
        assert facts["status"] == "unreviewed"
        assert facts["musical_selection_changed"] is False
        assert facts["midi_changed"] is False
        assert facts["instrument_default_changed"] is False
        assert facts["mix_changed"] is False
        assert facts["pack_changed"] is False
        assert (
            fixture.server.store.current_state(fixture.catalog)["event_count"]
            == event_count
        )
        fixture.server.store.append(
            fixture.catalog,
            {
                "event_type": "role_tag",
                "stem_id": lane["stem_id"],
                "role": "keys",
            },
        )
        changed_plan = fixture.plan()
        assert {row["role"] for row in changed_plan["eligible_lanes"]} == {"keys"}
        assert all(
            row["coverage_preflight"] == "required"
            for row in changed_plan["eligible_lanes"]
        )
    finally:
        fixture.close()


def test_complete_and_resolve_survive_restart_and_context_eviction(
    tmp_path: Path,
) -> None:
    fixture = _InstrumentHTTP(tmp_path)
    try:
        comparison = fixture.prepare()
        state_before = fixture.server.store.current_state(fixture.catalog)
        pack_events_before = _pack_event_count(fixture.server.store.path)
        fixture.restart()
        assert fixture.server.instrument_review_contexts == {}
        complete_request = {
            "comparison_sha256": comparison["comparison_sha256"],
            "expected_revision": 0,
            "heard": {
                "source_reference": True,
                "candidate_a": True,
                "candidate_b": True,
            },
            "choice": "none_usable",
            "problem_tags": {
                "candidate_a": ["too_plucky"],
                "candidate_b": [],
            },
            "notes": {
                "candidate_a": "too short",
                "candidate_b": "still not right",
            },
        }
        status, _payload = fixture.json(
            "POST",
            f"/api/instrument-review?token={fixture.token}",
            {**complete_request, "selection_manifest_sha256": "0" * 64},
        )
        assert status == 400
        status, payload = fixture.json(
            "POST",
            f"/api/instrument-review?token={fixture.token}",
            complete_request,
        )
        assert status == 200, payload
        reviewed = payload["comparison"]
        assert reviewed["status"] == "reviewed"
        assert reviewed["result"] is None
        assert reviewed["review"]["response"]["choice"] == "none_usable"
        assert "assignment" not in json.dumps(reviewed, sort_keys=True)

        review_url = reviewed["review"]["review_url"]
        status, exported = fixture.json("GET", review_url)
        assert status == 200
        assert exported["review_id"] == reviewed["review"]["review_id"]
        status, _payload = fixture.json("GET", review_url + "&extra=true")
        assert status == 400

        fixture.server.instrument_review_contexts.clear()
        status, _payload = fixture.json(
            "POST",
            f"/api/instrument-review/resolve?token={fixture.token}",
            {
                "comparison_sha256": reviewed["comparison_sha256"],
                "review_id": reviewed["review"]["review_id"],
            },
        )
        assert status == 400
        status, payload = fixture.json(
            "POST",
            f"/api/instrument-review/resolve?token={fixture.token}",
            {
                "comparison_sha256": reviewed["comparison_sha256"],
                "review_id": reviewed["review"]["review_id"],
                "review_sha256": reviewed["review"]["review_sha256"],
            },
        )
        assert status == 200, payload
        resolved = payload["comparison"]
        assert resolved["status"] == "resolved"
        assert {row["label"] for row in resolved["result"]["assignment"].values()} == {
            "Synth Bass 1",
            "Synth Bass 2",
        }
        assert resolved["result"]["resolved_choice"] == "none_usable"
        assert all(
            value is False
            for key, value in resolved["effects"].items()
            if key != "feedback_recorded"
        )

        status, result = fixture.json(
            "GET",
            resolved["result"]["result_url"],
        )
        assert status == 200
        assert result["review_id"] == reviewed["review"]["review_id"]
        assert fixture.server.store.current_state(fixture.catalog) == state_before
        assert _pack_event_count(fixture.server.store.path) == pack_events_before
    finally:
        fixture.close()


def test_keys_preflight_is_blind_and_survives_restart_and_resolution(
    tmp_path: Path,
) -> None:
    fixture = _InstrumentHTTP(tmp_path)
    try:
        plan = fixture.plan()
        lane = next(row for row in plan["eligible_lanes"] if row["role"] == "keys")
        status, _payload = fixture.json(
            "POST",
            f"/api/instrument-review/prepare?token={fixture.token}",
            {
                "selection_manifest_sha256": lane["selection_manifest_sha256"],
                "stem_id": lane["stem_id"],
                "candidate_id": lane["candidate_id"],
                "midi_sha256": lane["midi_sha256"],
                "start_seconds": 0,
                "end_seconds": 1,
                "role": "keys",
            },
        )
        assert status == 400

        state_before = fixture.server.store.current_state(fixture.catalog)
        pack_events_before = _pack_event_count(fixture.server.store.path)
        comparison = fixture.prepare("keys")
        assert comparison["role"] == "keys"
        assert comparison["blind"] is True
        coverage = comparison["coverage_preflight"]
        assert coverage["required"] is True
        assert coverage["status"] == "passed"
        assert coverage["functional_status"] == "passed"
        assert coverage["quality_status"] == "review_required"
        assert coverage["tested_zone_count"] == 3
        assert coverage["tested_pitch_count"] == 2
        assert coverage["failed_zone_count"] == 0
        assert {
            row["id"]: row["tested_zone_count"] for row in coverage["velocity_buckets"]
        } == {"soft": 1, "medium": 1, "strong": 1}
        assert set(coverage["candidates"]) == {
            "candidate_a",
            "candidate_b",
        }
        assert all(
            row["functional_status"] == "passed"
            and row["passed_zone_count"] == 3
            and row["failed_zone_count"] == 0
            for row in coverage["candidates"].values()
        )
        serialized = json.dumps(comparison, sort_keys=True)
        assert not _contains_key(comparison, "path")
        assert "Electric Piano" not in serialized
        assert '"control"' not in serialized
        assert '"challenger"' not in serialized
        assert '"program"' not in serialized
        assert "assignment" not in serialized
        for row in {
            "source_reference": comparison["source_reference"],
            **comparison["candidates"],
        }.values():
            status, _value, raw = fixture.request("GET", row["audio_url"])
            assert status == 200
            assert raw[:4] == b"RIFF"

        status, snapshot = fixture.json(
            "GET",
            f"/api/developer-snapshot?token={fixture.token}",
        )
        assert status == 200
        prepare = next(
            row
            for row in reversed(snapshot["runtime"]["trace"]["recent_operations"])
            if row["operation"] == "instrument_review.prepare"
            and row["http_status"] == 200
        )
        facts = prepare["frames"][-1]["facts"]
        assert facts["instrument_role"] == "keys"
        assert facts["coverage_preflight_status"] == "passed"
        assert facts["coverage_functional_status"] == "passed"
        assert facts["coverage_quality_status"] == "review_required"
        assert facts["coverage_required"] is True
        assert (
            "sunofriend.workbench_instrument_coverage.prepare_keys_coverage_preflight"
        ) in prepare["symbols"]

        fixture.restart()
        assert fixture.server.instrument_review_contexts == {}
        status, payload = fixture.json(
            "POST",
            f"/api/instrument-review?token={fixture.token}",
            {
                "comparison_sha256": comparison["comparison_sha256"],
                "expected_revision": 0,
                "heard": {
                    "source_reference": True,
                    "candidate_a": True,
                    "candidate_b": True,
                },
                "choice": "candidate_b",
                "problem_tags": {
                    "candidate_a": ["muddy"],
                    "candidate_b": [],
                },
                "notes": {
                    "candidate_a": "less clear",
                    "candidate_b": "clearer",
                },
            },
        )
        assert status == 200, payload
        reviewed = payload["comparison"]
        assert reviewed["status"] == "reviewed"
        assert reviewed["role"] == "keys"
        assert reviewed["coverage_preflight"] == coverage
        assert "Electric Piano" not in json.dumps(reviewed, sort_keys=True)

        fixture.server.instrument_review_contexts.clear()
        status, payload = fixture.json(
            "POST",
            f"/api/instrument-review/resolve?token={fixture.token}",
            {
                "comparison_sha256": reviewed["comparison_sha256"],
                "review_id": reviewed["review"]["review_id"],
                "review_sha256": reviewed["review"]["review_sha256"],
            },
        )
        assert status == 200, payload
        resolved = payload["comparison"]
        assert resolved["status"] == "resolved"
        assert {row["label"] for row in resolved["result"]["assignment"].values()} == {
            "Electric Piano 1",
            "Electric Piano 2",
        }
        assert fixture.server.store.current_state(fixture.catalog) == state_before
        assert _pack_event_count(fixture.server.store.path) == pack_events_before
    finally:
        fixture.close()


def test_keys_preflight_failure_publishes_no_blind_media(
    tmp_path: Path,
) -> None:
    fixture = _InstrumentHTTP(tmp_path)
    try:
        lane = next(
            row for row in fixture.plan()["eligible_lanes"] if row["role"] == "keys"
        )
        fixture._render_mock.side_effect = _render_keys_challenger_silent
        before_media = set(fixture.server.generated_media_ids)
        state_before = fixture.server.store.current_state(fixture.catalog)
        status, payload = fixture.json(
            "POST",
            f"/api/instrument-review/prepare?token={fixture.token}",
            {
                "selection_manifest_sha256": lane["selection_manifest_sha256"],
                "stem_id": lane["stem_id"],
                "candidate_id": lane["candidate_id"],
                "midi_sha256": lane["midi_sha256"],
                "start_seconds": 0,
                "end_seconds": 1,
            },
        )
        assert status == 400, payload
        assert "coverage" in payload["error"].lower()
        assert set(fixture.server.generated_media_ids) == before_media
        assert fixture.server.instrument_review_contexts == {}
        assert fixture.server.store.current_state(fixture.catalog) == state_before
        assert not [
            path
            for path in fixture.server.instrument_reviews.audio_root.iterdir()
            if path.is_dir()
        ]
    finally:
        fixture.close()


def test_instrument_media_is_frozen_after_verification(tmp_path: Path) -> None:
    fixture = _InstrumentHTTP(tmp_path)
    try:
        comparison = fixture.prepare()
        record = fixture.server.instrument_reviews.media_record(
            comparison["comparison_sha256"],
            "candidate_a",
        )
        original_bytes = Path(record["path"]).read_bytes()
        original_freeze = workbench_server._freeze_verified_immutable_file

        def freeze_then_mutate(handle: object, expected: dict):
            snapshot = original_freeze(handle, expected)
            Path(str(expected["path"])).write_bytes(b"changed-after-freeze")
            return snapshot

        with patch.object(
            workbench_server,
            "_freeze_verified_immutable_file",
            side_effect=freeze_then_mutate,
        ):
            status, _value, raw = fixture.request(
                "GET",
                comparison["candidates"]["candidate_a"]["audio_url"],
            )
        assert status == 200
        assert raw == original_bytes
        assert hashlib.sha256(raw).hexdigest() == record["sha256"]
    finally:
        fixture.close()


def test_prepare_rechecks_selection_before_registering_media(
    tmp_path: Path,
) -> None:
    fixture = _InstrumentHTTP(tmp_path)
    try:
        plan = fixture.plan()
        lane = next(row for row in plan["eligible_lanes"] if row["role"] == "bass")
        original = fixture.server.instrument_reviews.prepare
        before_media = set(fixture.server.generated_media_ids)

        def prepare_then_change_role(**kwargs: object) -> dict:
            prepared = original(**kwargs)
            fixture.server.store.append(
                fixture.catalog,
                {
                    "event_type": "role_tag",
                    "stem_id": lane["stem_id"],
                    "role": "keys",
                },
            )
            return prepared

        with patch.object(
            fixture.server.instrument_reviews,
            "prepare",
            side_effect=prepare_then_change_role,
        ):
            status, payload = fixture.json(
                "POST",
                f"/api/instrument-review/prepare?token={fixture.token}",
                {
                    "selection_manifest_sha256": lane["selection_manifest_sha256"],
                    "stem_id": lane["stem_id"],
                    "candidate_id": lane["candidate_id"],
                    "midi_sha256": lane["midi_sha256"],
                    "start_seconds": 0,
                    "end_seconds": 1,
                },
            )
        assert status == 409, payload
        assert set(fixture.server.generated_media_ids) == before_media
    finally:
        fixture.close()


def test_keys_prepare_rechecks_role_before_registering_media(
    tmp_path: Path,
) -> None:
    fixture = _InstrumentHTTP(tmp_path)
    try:
        lane = next(
            row for row in fixture.plan()["eligible_lanes"] if row["role"] == "keys"
        )
        original = fixture.server.instrument_reviews.prepare
        before_media = set(fixture.server.generated_media_ids)

        def prepare_then_change_role(**kwargs: object) -> dict:
            prepared = original(**kwargs)
            fixture.server.store.append(
                fixture.catalog,
                {
                    "event_type": "role_tag",
                    "stem_id": lane["stem_id"],
                    "role": "lead",
                },
            )
            return prepared

        with patch.object(
            fixture.server.instrument_reviews,
            "prepare",
            side_effect=prepare_then_change_role,
        ):
            status, payload = fixture.json(
                "POST",
                f"/api/instrument-review/prepare?token={fixture.token}",
                {
                    "selection_manifest_sha256": lane["selection_manifest_sha256"],
                    "stem_id": lane["stem_id"],
                    "candidate_id": lane["candidate_id"],
                    "midi_sha256": lane["midi_sha256"],
                    "start_seconds": 0,
                    "end_seconds": 1,
                },
            )
        assert status == 409, payload
        assert set(fixture.server.generated_media_ids) == before_media
    finally:
        fixture.close()


def test_shell_and_developer_inspector_expose_a_separate_stage_four() -> None:
    page = Path("src/sunofriend/workbench.html").read_text(encoding="utf-8")
    module = Path("src/sunofriend/workbench_instrument_review.js").read_text(
        encoding="utf-8"
    )
    assert "Choose instruments <span" not in page
    assert "Choose bass or keys instrument" in page
    assert 'id="step-instruments"' in page
    assert 'id="instrument-nav"' in page
    assert '<script src="/workbench-instrument-review.js"></script>' in page
    assert "view==='instruments'" in page
    assert "instrumentReview.stopAudio()" in page
    assert "resetInstrumentReviewPlan()" in page
    assert "api('/api/instrument-review-plan')" in page
    assert 'coverage_preflight:"required"' not in page
    assert "/api/events" not in module
    assert "/api/garageband" not in module
    assert "autoplay" not in module.lower()

    routes = {
        "/api/instrument-review-plan": "instrument_review.plan",
        "/api/instrument-review/prepare": "instrument_review.prepare",
        "/api/instrument-review": "instrument_review.complete",
        "/api/instrument-review/resolve": "instrument_review.resolve",
        "/api/instrument-review-export": "instrument_review.export",
    }
    for route, operation in routes.items():
        assert developer_operation_for_route(route) == operation
        assert developer_code_step_for_route(route) == operation
    trace = WorkbenchDeveloperTrace()
    prepare = trace.begin("POST", "instrument_review.prepare")
    trace.complete(
        prepare,
        200,
        trace_response_facts(
            "/api/instrument-review/prepare",
            {
                "comparison": {
                    "schema": ("sunofriend.workbench-instrument-review.comparison.v1"),
                    "status": "unreviewed",
                    "expected_revision": 0,
                    "role": "keys",
                    "coverage_preflight": {
                        "required": True,
                        "status": "passed",
                        "functional_status": "passed",
                        "quality_status": "review_required",
                    },
                }
            },
        ),
    )
    row = trace.snapshot()["recent_operations"][0]
    assert row["durable_effect_possible"] is True
    facts = row["frames"][-1]["facts"]
    assert facts["status"] == "unreviewed"
    assert facts["instrument_role"] == "keys"
    assert facts["coverage_preflight_status"] == "passed"
    assert facts["coverage_quality_status"] == "review_required"
    assert facts["musical_selection_changed"] is False
    assert facts["pack_changed"] is False
    assert (
        "sunofriend.workbench_instrument_coverage.prepare_keys_coverage_preflight"
    ) in row["symbols"]
