from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import sunofriend._separation_authorised_vocal_leaves as vocal_leaves
import sunofriend.evaluate as production_evaluate
import sunofriend.render as production_render
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS
from sunofriend.models import NoteEvent


def test_evaluates_every_vocal_leaf_with_both_adapters_and_stays_inactive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _input_bundle(tmp_path)
    monkeypatch.setattr(vocal_leaves, "_load_inputs", lambda *args: inputs)
    monkeypatch.setattr(vocal_leaves, "_reverify_inputs", lambda _: None)
    observed: list[tuple[str, str]] = []

    def transcribe(path: Path, *, config: object) -> object:
        observed.append((path.name, getattr(config, "role")))
        nonempty = (
            "backing-vocals" in path.name and getattr(config, "role") == "backing"
        ) or ("lead-vocals" in path.name and getattr(config, "role") == "lead")
        notes = [NoteEvent(0.1, 0.5, 64, 90)] if nonempty else []
        primary = (
            "contour_clean" if getattr(config, "role") == "lead" else "dominant_line"
        )
        return SimpleNamespace(
            primary_variant=primary,
            variants={primary: notes},
            diagnostics=SimpleNamespace(
                warnings=(),
                to_dict=lambda: {"role": getattr(config, "role"), "fixture": True},
            ),
            descriptions={primary: "fixture"},
        )

    monkeypatch.setattr(vocal_leaves, "transcribe_vocal_melody", transcribe)
    monkeypatch.setattr(
        production_evaluate,
        "evaluate_stem_midi",
        lambda *args, **kwargs: {"schema": "fixture-evaluation"},
    )

    def render(_midi: Path, output: Path) -> None:
        output.write_bytes(b"fixture-render")

    monkeypatch.setattr(production_render, "render_midi_to_wav", render)
    monkeypatch.setattr(
        vocal_leaves,
        "_production_component_identity",
        lambda: {"mode": "test_injected", "production_identity_captured": False},
    )

    result = vocal_leaves._evaluate_authorised_vocal_leaves(
        tmp_path / "mapping.json",
        tmp_path / "controls.json",
        tmp_path / "melroformer.json",
        out_dir=tmp_path / "result",
    )

    assert result["status"] == "complete_observation_not_acceptance"
    assert observed == [
        ("backing-vocals.wav", "lead"),
        ("backing-vocals.wav", "backing"),
        ("lead-vocals.wav", "lead"),
        ("lead-vocals.wav", "backing"),
    ]
    assert result["observations"]["primary_note_counts"] == {
        "moises/leaf-01/backing": 1,
        "moises/leaf-01/lead": 0,
        "moises/leaf-02/backing": 0,
        "moises/leaf-02/lead": 1,
    }
    assert result["observations"][
        "within_pack_broad_group_zero_but_leaf_nonempty"
    ] == {"moises": True}
    assert result["policy"]["provider_labels_select_adapter"] is False
    assert result["next"][
        "separate_vocal_leaf_candidates_in_future_separator_required"
    ] is True
    assert all(value is False for value in result["permissions"].values())
    assert result["effects"]["separator_rerun"] is False
    report = Path(result["report"])
    assert report.is_file()
    persisted = json.loads(report.read_text(encoding="utf-8"))
    assert persisted["document_sha256"] == vocal_leaves._document_sha256(persisted)


def test_rejects_an_existing_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        vocal_leaves, "_load_inputs", lambda *args: _input_bundle(tmp_path)
    )
    destination = tmp_path / "result"
    destination.mkdir()

    with pytest.raises(FileExistsError, match="already exists"):
        vocal_leaves._evaluate_authorised_vocal_leaves(
            tmp_path / "mapping.json",
            tmp_path / "controls.json",
            tmp_path / "melroformer.json",
            out_dir=destination,
        )


def test_private_vocal_leaf_evaluator_has_no_public_route() -> None:
    assert "private-authorised-vocal-leaf-midi-evaluation" not in PUBLIC_COMMANDS
    assert (
        "private-authorised-vocal-leaf-midi-evaluation" not in DIRECT_TUI_COMMANDS
    )
    assert vocal_leaves.__all__ == ()


def test_missing_basic_pitch_runtime_is_not_accepted_as_leaf_evidence() -> None:
    transcription = SimpleNamespace(
        diagnostics=SimpleNamespace(
            warnings=(
                "Polyphonic backing extraction unavailable: ModuleNotFoundError",
            )
        )
    )

    with pytest.raises(RuntimeError, match="requires the installed Basic Pitch"):
        vocal_leaves._require_backing_adapter_available(transcription)


def test_requires_exact_private_inactive_permissions() -> None:
    document = {
        "evidence_scope": "private_development_only",
        "permissions": dict(vocal_leaves._INACTIVE_PERMISSIONS),
    }
    vocal_leaves._require_private_inactive(document, "fixture")

    document["permissions"]["public_result"] = True
    with pytest.raises(ValueError, match="permissions differ"):
        vocal_leaves._require_private_inactive(document, "fixture")


@pytest.mark.parametrize(
    "schema",
    (
        "sunofriend.private-melroformer-downstream-vocal-midi-evaluation.v1",
        "sunofriend.private-melroformer-downstream-vocal-midi-evaluation.v2",
    ),
)
def test_accepts_exact_historical_and_current_melroformer_midi_schemas(
    schema: str,
) -> None:
    vocal_leaves._require_supported_melroformer_schema({"schema": schema})


def test_rejects_unknown_melroformer_midi_schema() -> None:
    with pytest.raises(ValueError, match="unsupported MelRoFormer"):
        vocal_leaves._require_supported_melroformer_schema(
            {
                "schema": (
                    "sunofriend.private-melroformer-downstream-vocal-midi-"
                    "evaluation.v3"
                )
            }
        )


def _input_bundle(root: Path) -> dict[str, object]:
    excerpt_root = root / "excerpt"
    excerpt_root.mkdir()
    items = []
    for name in (
        "backing-vocals.wav",
        "lead-vocals.wav",
        "song-bass.wav",
        "song-drums.wav",
        "song-other.wav",
    ):
        path = excerpt_root / name
        path.write_bytes(f"fixture-{name}".encode())
        items.append(
            {
                "source_path": f"/private/{name}",
                "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "excluded_from_pack_sum": False,
                "excerpt": {
                    "path": name,
                    "bytes": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                },
            }
        )
    report_paths = {}
    for name in ("mapping", "excerpt", "controls", "melroformer"):
        path = root / f"{name}.json"
        path.write_text(f'{{"fixture":"{name}"}}\n', encoding="utf-8")
        report_paths[name] = path
    inactive = dict(vocal_leaves._INACTIVE_PERMISSIONS)
    mapping = {
        "document_sha256": "a" * 64,
        "artifacts": {"fixture": {}},
        "permissions": inactive,
    }
    excerpt = {
        "document_sha256": "b" * 64,
        "artifacts": {"fixture": {}},
        "permissions": inactive,
    }
    control = {
        "document_sha256": "c" * 64,
        "artifacts": {"fixture": {}},
        "permissions": inactive,
    }
    melroformer = {
        "document_sha256": "d" * 64,
        "artifacts": {"fixture": {}},
        "permissions": inactive,
    }
    proposals = {
        "bass": ["-bass"],
        "drums": ["-drums"],
        "other": ["-other"],
        "vocals": ["vocals"],
    }
    return {
        "mapping_path": report_paths["mapping"],
        "mapping_root": root,
        "mapping_sha256": hashlib.sha256(
            report_paths["mapping"].read_bytes()
        ).hexdigest(),
        "mapping": mapping,
        "excerpt_path": report_paths["excerpt"],
        "excerpt_root": excerpt_root,
        "excerpt_sha256": hashlib.sha256(
            report_paths["excerpt"].read_bytes()
        ).hexdigest(),
        "excerpt": excerpt,
        "control_path": report_paths["controls"],
        "control_root": root,
        "control_sha256": hashlib.sha256(
            report_paths["controls"].read_bytes()
        ).hexdigest(),
        "control": control,
        "melroformer_path": report_paths["melroformer"],
        "melroformer_root": root,
        "melroformer_sha256": hashlib.sha256(
            report_paths["melroformer"].read_bytes()
        ).hexdigest(),
        "melroformer": melroformer,
        "bpm": 130.0,
        "tuning_hz": 440.0,
        "controls": {"local-htdemucs": (), "moises": ()},
        "kim_notes": (),
        "rights_authority": "user_authorised_private_local_evaluation",
        "provider_packs": {"moises": {"items": items}},
        "proposals": {"moises": proposals},
    }
