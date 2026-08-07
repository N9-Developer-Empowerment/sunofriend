from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import stat
import subprocess
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from sunofriend.separation_other_refinement import (
    create_other_refinement_synthetic_fixture,
)
from sunofriend.separation_other_refinement_corpus import (
    CORPUS_FEEDBACK_INDEX_SCHEMA,
    CORPUS_LISTENING_SCHEMA,
    CORPUS_REVIEW_INDEX_SCHEMA,
    _document_sha256,
    _render_review,
    build_other_refinement_corpus_review_server,
    load_other_refinement_corpus_definition,
    record_other_refinement_corpus_reviews,
    validate_other_refinement_corpus_authority,
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "stem_examples/other-refinement-evaluation-v1.json"


def test_tracked_corpus_is_fixed_authorised_and_capped_at_ten() -> None:
    definition = load_other_refinement_corpus_definition(DEFINITION)

    cases = [case for track in definition["tracks"] for case in track["cases"]]
    assert len(definition["tracks"]) == 5
    assert len(cases) == 10
    assert {case["target_id"] for case in cases} == {"guitar", "keys"}
    assert definition["policy"]["configuration_count"] == 1
    assert definition["policy"]["keys_semantics"] == (
        "piano_proxy_not_general_keyboards"
    )
    assert definition["policy"]["retry_policy"] == ("objective_execution_fault_only")
    assert definition["policy"]["poor_or_mixed_feedback_blocks_access"] is False
    assert not any(
        definition["permissions"][field]
        for field in (
            "audio_committed",
            "provider_audio_redistributed",
            "candidate_selected",
            "profile_promoted",
            "source_graph_mutated",
            "midi_created",
        )
    )
    authorities = validate_other_refinement_corpus_authority(
        definition, stem_root=ROOT / "stem_examples"
    )
    assert len(authorities) == 5
    assert {item["authority"] for item in authorities} == {
        "creator_and_copyright_holder",
        "user_authorised",
    }
    assert all(item["repository_distribution"] is False for item in authorities)


def test_corpus_validator_rejects_ground_truth_and_tuning_drift(
    tmp_path: Path,
) -> None:
    value = json.loads(DEFINITION.read_text(encoding="utf-8"))
    for change in (
        {"provider_stems_are_ground_truth": True},
        {"configuration_count": 2},
        {"retry_policy": "tune_until_listeners_like_it"},
    ):
        mutated = copy.deepcopy(value)
        mutated["policy"].update(change)
        path = tmp_path / (next(iter(change)) + ".json")
        path.write_text(json.dumps(mutated) + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="policy differs"):
            load_other_refinement_corpus_definition(path)


def test_rendered_review_javascript_parses_with_literal_newline_escapes() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    cases = []
    for index in range(10):
        target_id = "guitar" if index % 2 == 0 else "keys"
        cases.append(
            {
                "case_id": f"case-{index + 1:02d}-{target_id}",
                "target_id": target_id,
                "target_semantics": (
                    "direct_experimental_guitar"
                    if target_id == "guitar"
                    else "piano_proxy_not_general_keyboards"
                ),
                "display_name": f"Case {index + 1}",
                "window": {"start_seconds": 0.0, "end_seconds": 15.0},
                "objective": {"target_to_parent_rms_ratio": 0.01},
                "audio": [],
                "result_document_sha256": f"{index:064x}",
            }
        )
    index_document = {
        "schema": CORPUS_REVIEW_INDEX_SCHEMA,
        "cases": cases,
        "document_sha256": "a" * 64,
    }

    html = _render_review(index_document)
    script = html.split("<script>", 1)[1].split("</script>", 1)[0]
    assert "JSON.stringify(value,null,2)+'\\n'" in script
    assert "lines.join('\\n')" in script
    completed = subprocess.run(
        [
            node,
            "-e",
            "new Function(require('fs').readFileSync(0,'utf8'))",
        ],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_local_review_server_supports_audio_ranges_and_rejects_uploads(
    tmp_path: Path,
) -> None:
    import numpy as np
    import soundfile

    root = tmp_path / "review"
    audio = root / "AUDIO/case-01/target.wav"
    audio.parent.mkdir(parents=True)
    soundfile.write(
        audio,
        np.zeros((44_100, 2), dtype="float32"),
        44_100,
        subtype="PCM_24",
    )
    artifact = {
        "relative_path": "AUDIO/case-01/target.wav",
        "sha256": _sha256(audio),
        "bytes": audio.stat().st_size,
        "sample_rate": 44_100,
        "channels": 2,
        "frames": 44_100,
        "sample_width_bytes": 3,
    }
    index = {
        "schema": CORPUS_REVIEW_INDEX_SCHEMA,
        "cases": [
            {
                "case_id": "case-01",
                "audio": [
                    {
                        "route": "/audio/case-01/target.wav",
                        "artifact": artifact,
                    }
                ],
            }
        ],
    }
    index["document_sha256"] = _document_sha256(index)
    technical = root / "TECHNICAL"
    technical.mkdir()
    (technical / "corpus-review-index.json").write_text(
        json.dumps(index) + "\n", encoding="utf-8"
    )
    (root / "review.html").write_text("<!doctype html><p>review</p>", encoding="utf-8")

    server = build_other_refinement_corpus_review_server(root, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        request = Request(
            base + "/audio/case-01/target.wav", headers={"Range": "bytes=1-9"}
        )
        with urlopen(request, timeout=5) as response:
            assert response.status == 206
            assert response.headers["Content-Range"].startswith("bytes 1-9/")
            assert len(response.read()) == 9
        interrupted = urlopen(base + "/audio/case-01/target.wav", timeout=5)
        assert interrupted.read(32)
        interrupted.close()
        with pytest.raises(HTTPError) as posted:
            urlopen(Request(base + "/", data=b"private"), timeout=5)
        assert posted.value.code == 405
        with pytest.raises(HTTPError) as missing:
            urlopen(base + "/private-path", timeout=5)
        assert missing.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_ten_review_bundle_records_negative_feedback_without_activation(
    tmp_path: Path,
) -> None:
    execution = tmp_path / "execution"
    cases = []
    reviews = []
    for index in range(10):
        target_id = "guitar" if index % 2 == 0 else "keys"
        case_id = f"case-{index + 1:02d}-{target_id}"
        fixture = create_other_refinement_synthetic_fixture(
            execution / "REFINEMENTS" / case_id,
            target_id=target_id,
        )
        result = json.loads(Path(fixture["result"]).read_text(encoding="utf-8"))
        technical = Path(fixture["root"]) / "TECHNICAL"
        technical.mkdir()
        Path(fixture["plan"]).rename(technical / "other-refinement-plan.json")
        Path(fixture["result"]).rename(technical / "other-refinement-result.json")
        cases.append(
            {
                "case_id": case_id,
                "target_id": target_id,
                "result_document_sha256": result["document_sha256"],
            }
        )
        reviews.append(
            {
                "case_id": case_id,
                "review": {
                    "schema": "sunofriend.other-refinement-listening.v1",
                    "result_sha256": result["document_sha256"],
                    "target_id": target_id,
                    "listened": True,
                    "usefulness": "not_useful" if index == 0 else "mixed",
                    "bleed": "some",
                    "missing_content": "some",
                    "artefacts": "cannot_tell",
                    "timing_or_join_problems": "none",
                    "downstream_midi": "not_tested",
                    "notes": "Negative evidence remains available.",
                    "activation_choice": "none",
                    "exported_at": "2026-08-07T07:15:00Z",
                },
            }
        )
    review_root = tmp_path / "review"
    technical = review_root / "TECHNICAL"
    technical.mkdir(parents=True)
    index_document = {"schema": CORPUS_REVIEW_INDEX_SCHEMA, "cases": cases}
    index_document["document_sha256"] = _document_sha256(index_document)
    (technical / "corpus-review-index.json").write_text(
        json.dumps(index_document) + "\n", encoding="utf-8"
    )
    bundle = {
        "schema": CORPUS_LISTENING_SCHEMA,
        "review_index_sha256": index_document["document_sha256"],
        "reviews": reviews,
        "audio_included": False,
        "filenames_included": False,
        "browser_telemetry_included": False,
        "exported_at": "2026-08-07T07:16:00Z",
    }
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(bundle) + "\n", encoding="utf-8")

    result = record_other_refinement_corpus_reviews(
        execution,
        review_root,
        bundle_path,
        out=tmp_path / "feedback",
    )

    assert result["schema"] == CORPUS_FEEDBACK_INDEX_SCHEMA
    assert result["status"] == "ten_valid_reports_recorded_no_activation"
    assert result["valid_report_count"] == 10
    assert result["records"][0]["usefulness"] == "not_useful"
    assert not any(result["effects"].values())
    assert not any(result["feedback_policy"].values())
    for path in (tmp_path / "feedback").rglob("*.json"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()
