from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.workbench_artifacts import (
    GARAGEBAND_PACK_BASKET_SCHEMA,
    GARAGEBAND_PACK_PLAN_SCHEMA,
    GARAGEBAND_PACK_SCHEMA,
    WorkbenchArtifacts,
    WorkbenchPackConflictError,
    canonical_garageband_pack_basket,
)
from sunofriend.workbench_catalog import build_workbench_catalog


class WorkbenchPackPlanTests(unittest.TestCase):
    def test_plan_is_path_free_has_safe_defaults_and_separate_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _pack_catalog(root)
            current = _current_state(catalog, contexts=("solo", "solo"))
            artifacts = WorkbenchArtifacts(root / "state" / "artifacts")

            plan = artifacts.garageband_pack_plan(catalog, current)

            self.assertEqual(
                set(plan),
                {
                    "schema",
                    "project_id",
                    "selection_sha256",
                    "basket_scope_sha256",
                    "plan_sha256",
                    "items",
                    "default_basket",
                    "build_blocked",
                    "block_reasons",
                    "selected_midi_overlap",
                    "setup",
                    "policies",
                    "effects",
                },
            )
            self.assertEqual(plan["schema"], GARAGEBAND_PACK_PLAN_SCHEMA)
            self.assertFalse(plan["build_blocked"])
            self.assertEqual(plan["block_reasons"], [])
            self.assertNotIn(str(root), json.dumps(plan))
            self.assertNotIn("private", json.dumps(plan))
            kinds = [item["kind"] for item in plan["items"]]
            self.assertEqual(kinds.count("selected_midi"), 2)
            self.assertEqual(kinds.count("arrangement_proxy"), 1)
            self.assertEqual(kinds.count("source_audio"), 2)
            for item in plan["items"]:
                self.assertTrue(str(item["item_id"]).startswith("pack-item-"))
                self.assertNotIn("path", item)
                self.assertEqual(
                    item["default_included"], item["kind"] != "source_audio"
                )
            default = plan["default_basket"]
            self.assertEqual(default["schema"], GARAGEBAND_PACK_BASKET_SCHEMA)
            self.assertFalse(default["source_audio_opt_in"])
            self.assertEqual(len(default["included_item_ids"]), 3)

            changed = _current_state(catalog, contexts=("full_mix", "solo"))
            changed_plan = artifacts.garageband_pack_plan(catalog, changed)
            self.assertEqual(
                changed_plan["basket_scope_sha256"], plan["basket_scope_sha256"]
            )
            self.assertNotEqual(
                changed_plan["selection_sha256"], plan["selection_sha256"]
            )
            self.assertNotEqual(changed_plan["plan_sha256"], plan["plan_sha256"])

    def test_source_inventory_deduplicates_shared_audio(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _pack_catalog(root, shared_source=True, overlapping=False)
            current = _current_state(catalog, contexts=("solo", "solo"))

            plan = WorkbenchArtifacts(
                root / "state" / "artifacts"
            ).garageband_pack_plan(catalog, current)

            sources = [item for item in plan["items"] if item["kind"] == "source_audio"]
            self.assertEqual(len(sources), 1)
            self.assertEqual(set(sources[0]["roles"]), {"bass", "keys"})

    def test_basket_is_canonical_and_source_audio_needs_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _pack_catalog(root)
            plan = WorkbenchArtifacts(
                root / "state" / "artifacts"
            ).garageband_pack_plan(catalog, _current_state(catalog))
            midi_ids = [
                item["item_id"]
                for item in plan["items"]
                if item["kind"] == "selected_midi"
            ]
            source_id = next(
                item["item_id"]
                for item in plan["items"]
                if item["kind"] == "source_audio"
            )

            basket = canonical_garageband_pack_basket(
                plan,
                [source_id, midi_ids[1]],
                True,
            )
            self.assertEqual(
                basket["included_item_ids"], [midi_ids[1], source_id]
            )
            with self.assertRaisesRegex(ValueError, "at least one selected MIDI"):
                canonical_garageband_pack_basket(plan, [source_id], True)
            with self.assertRaisesRegex(ValueError, "separate explicit local"):
                canonical_garageband_pack_basket(
                    plan, [midi_ids[0], source_id], False
                )
            with self.assertRaisesRegex(ValueError, "unknown item"):
                canonical_garageband_pack_basket(
                    plan, [midi_ids[0], "pack-item-unknown"], False
                )
            with self.assertRaisesRegex(ValueError, "must not be repeated"):
                canonical_garageband_pack_basket(
                    plan, [midi_ids[0], midi_ids[0]], False
                )


class WorkbenchPackBuildTests(unittest.TestCase):
    def test_legacy_path_role_is_redacted_before_pack_names_and_proxy_midi(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _pack_catalog(root)
            current = _current_state(catalog, contexts=("full_mix", "full_mix"))
            first_stem = catalog["stems"][0]
            current["stems"][first_stem["stem_id"]]["role"] = (
                "Users/alice/ROLE_SENTINEL/private/song.wav"
            )
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"test-soundfont")
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )

            plan = artifacts.garageband_pack_plan(catalog, current)
            selected = [
                item for item in plan["items"] if item["kind"] == "selected_midi"
            ]

            self.assertEqual(selected[0]["role"], "custom role")
            self.assertEqual(selected[0]["label"], "Custom Role — main")
            self.assertEqual(
                selected[0]["archive_paths"], ["MIDI/01-custom-role-main.mid"]
            )
            public_plan = json.dumps(plan)
            for leaked in (
                "ROLE_SENTINEL",
                "usersalice",
                "Users/alice",
                "privatesong",
                "private-song",
            ):
                self.assertNotIn(leaked, public_plan)

            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_fake_render,
            ):
                pack = artifacts.build_garageband_pack(
                    catalog,
                    current,
                    plan["plan_sha256"],
                    plan["default_basket"],
                )

            with zipfile.ZipFile(pack["zip"]["path"]) as archive:
                names = archive.namelist()
                self.assertIn("MIDI/01-custom-role-main.mid", names)
                serialized_names = json.dumps(names)
                manifest = archive.read(
                    "sunofriend-garageband-pack.json"
                ).decode("utf-8")
                proxy = archive.read("MIDI/selected-arrangement-proxy.mid")
                self.assertIn(b"Neutral Custom Role (main)", proxy)
                for leaked in (
                    "ROLE_SENTINEL",
                    "usersalice",
                    "Users/alice",
                    "privatesong",
                    "private-song",
                ):
                    self.assertNotIn(leaked, serialized_names)
                    self.assertNotIn(leaked, manifest)
                    self.assertNotIn(leaked.encode("utf-8"), proxy)

    def test_cache_rejects_a_different_valid_pack_copied_into_its_directory(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _pack_catalog(root)
            current = _current_state(catalog)
            artifacts = WorkbenchArtifacts(root / "state" / "artifacts")
            plan = artifacts.garageband_pack_plan(catalog, current)
            midi_item = next(
                item for item in plan["items"] if item["kind"] == "selected_midi"
            )
            source_item = next(
                item for item in plan["items"] if item["kind"] == "source_audio"
            )
            midi_only = canonical_garageband_pack_basket(
                plan, [midi_item["item_id"]], False
            )
            with_source = canonical_garageband_pack_basket(
                plan, [midi_item["item_id"], source_item["item_id"]], True
            )

            safe_pack = artifacts.build_garageband_pack(
                catalog, current, plan["plan_sha256"], midi_only
            )
            source_pack = artifacts.build_garageband_pack(
                catalog, current, plan["plan_sha256"], with_source
            )
            safe_dir = Path(safe_pack["zip"]["path"]).parent
            source_dir = Path(source_pack["zip"]["path"]).parent
            shutil.copyfile(
                source_dir / "sunofriend-garageband-pack.zip",
                safe_dir / "sunofriend-garageband-pack.zip",
            )
            shutil.copyfile(
                source_dir / "manifest.json",
                safe_dir / "manifest.json",
            )

            rebuilt = artifacts.build_garageband_pack(
                catalog, current, plan["plan_sha256"], midi_only
            )

            self.assertFalse(rebuilt["cache_hit"])
            self.assertFalse(rebuilt["source_audio_included"])
            self.assertEqual(rebuilt["basket_sha256"], midi_only["basket_sha256"])
            with zipfile.ZipFile(rebuilt["zip"]["path"]) as archive:
                self.assertNotIn(source_item["archive_paths"][0], archive.namelist())

    def test_cache_rejects_self_consistent_rewritten_payload_and_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _pack_catalog(root)
            current = _current_state(catalog)
            artifacts = WorkbenchArtifacts(root / "state" / "artifacts")
            plan = artifacts.garageband_pack_plan(catalog, current)
            midi_item = next(
                item for item in plan["items"] if item["kind"] == "selected_midi"
            )
            basket = canonical_garageband_pack_basket(
                plan, [midi_item["item_id"]], False
            )
            pack = artifacts.build_garageband_pack(
                catalog, current, plan["plan_sha256"], basket
            )
            pack_path = Path(pack["zip"]["path"])
            pack_dir = pack_path.parent
            with zipfile.ZipFile(pack_path) as archive:
                members = {name: archive.read(name) for name in archive.namelist()}
            receipt_name = "sunofriend-garageband-pack.json"
            receipt = json.loads(members[receipt_name])
            selected = next(
                row for row in receipt["included_items"]
                if row["kind"] == "selected_midi"
            )
            changed_payload = b"self-consistent but not catalogued MIDI"
            members[selected["archive_path"]] = changed_payload
            selected["bytes"] = len(changed_payload)
            selected["sha256"] = hashlib.sha256(changed_payload).hexdigest()
            members[receipt_name] = (
                json.dumps(receipt, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            with zipfile.ZipFile(
                pack_path, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                for name, data in members.items():
                    archive.writestr(name, data)

            outer_path = pack_dir / "manifest.json"
            outer = json.loads(outer_path.read_text(encoding="utf-8"))
            outer["included_items"] = receipt["included_items"]
            outer["zip"]["bytes"] = pack_path.stat().st_size
            outer["zip"]["sha256"] = hashlib.sha256(
                pack_path.read_bytes()
            ).hexdigest()
            seed_path = pack_dir / outer["acceptance_seed"]["path"]
            seed = json.loads(seed_path.read_text(encoding="utf-8"))
            seed["pack"]["bytes"] = outer["zip"]["bytes"]
            seed["pack"]["sha256"] = outer["zip"]["sha256"]
            seed_path.write_text(
                json.dumps(seed, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            outer["acceptance_seed"]["bytes"] = seed_path.stat().st_size
            outer["acceptance_seed"]["sha256"] = hashlib.sha256(
                seed_path.read_bytes()
            ).hexdigest()
            outer_path.write_text(
                json.dumps(outer, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            rebuilt = artifacts.build_garageband_pack(
                catalog, current, plan["plan_sha256"], basket
            )

            self.assertFalse(rebuilt["cache_hit"])
            with zipfile.ZipFile(rebuilt["zip"]["path"]) as archive:
                self.assertEqual(
                    archive.read(midi_item["archive_paths"][0]),
                    _record_path(catalog, midi_item["content_sha256"]).read_bytes(),
                )
            rebuilt_seed = json.loads(
                Path(rebuilt["acceptance_seed"]["path"]).read_text(encoding="utf-8")
            )
            self.assertEqual(
                rebuilt_seed["pack"]["sha256"], rebuilt["zip"]["sha256"]
            )

    def test_cache_rejects_rewritten_acceptance_html(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _pack_catalog(root)
            current = _current_state(catalog)
            artifacts = WorkbenchArtifacts(root / "state" / "artifacts")
            plan = artifacts.garageband_pack_plan(catalog, current)
            midi_item = next(
                item for item in plan["items"] if item["kind"] == "selected_midi"
            )
            basket = canonical_garageband_pack_basket(
                plan, [midi_item["item_id"]], False
            )
            pack = artifacts.build_garageband_pack(
                catalog, current, plan["plan_sha256"], basket
            )
            pack_dir = Path(pack["zip"]["path"]).parent
            outer_path = pack_dir / "manifest.json"
            outer = json.loads(outer_path.read_text(encoding="utf-8"))
            review_path = pack_dir / outer["acceptance_review"]["path"]
            review_path.write_text("<html>changed</html>", encoding="utf-8")
            outer["acceptance_review"]["bytes"] = review_path.stat().st_size
            outer["acceptance_review"]["sha256"] = hashlib.sha256(
                review_path.read_bytes()
            ).hexdigest()
            outer_path.write_text(
                json.dumps(outer, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            rebuilt = artifacts.build_garageband_pack(
                catalog, current, plan["plan_sha256"], basket
            )

            self.assertFalse(rebuilt["cache_hit"])
            self.assertIn(
                "Understand Sunofriend, then test it",
                Path(rebuilt["acceptance_review"]["path"]).read_text(
                    encoding="utf-8"
                ),
            )

    def test_explicit_source_pack_uses_exact_bytes_without_rendering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _pack_catalog(root)
            current = _current_state(catalog)
            artifacts = WorkbenchArtifacts(root / "state" / "artifacts")
            plan = artifacts.garageband_pack_plan(catalog, current)
            midi_item = next(
                item for item in plan["items"] if item["kind"] == "selected_midi"
            )
            source_item = next(
                item for item in plan["items"] if item["kind"] == "source_audio"
            )
            basket = canonical_garageband_pack_basket(
                plan,
                [source_item["item_id"], midi_item["item_id"]],
                True,
            )

            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav"
            ) as renderer:
                pack = artifacts.build_garageband_pack(
                    catalog, current, plan["plan_sha256"], basket
                )
                repeated = artifacts.build_garageband_pack(
                    catalog, current, plan["plan_sha256"], basket
                )

            renderer.assert_not_called()
            self.assertEqual(pack["schema"], GARAGEBAND_PACK_SCHEMA)
            self.assertFalse(pack["cache_hit"])
            self.assertTrue(repeated["cache_hit"])
            self.assertEqual(pack["zip"]["sha256"], repeated["zip"]["sha256"])
            self.assertTrue(pack["source_audio_included"])
            self.assertFalse(pack["arrangement_proxy_included"])
            with zipfile.ZipFile(pack["zip"]["path"]) as archive:
                names = set(archive.namelist())
                midi_name = midi_item["archive_paths"][0]
                source_name = source_item["archive_paths"][0]
                self.assertIn(midi_name, names)
                self.assertIn(source_name, names)
                self.assertNotIn("MIDI/selected-arrangement-proxy.mid", names)
                self.assertEqual(
                    archive.read(midi_name),
                    _record_path(catalog, midi_item["content_sha256"]).read_bytes(),
                )
                self.assertEqual(
                    archive.read(source_name),
                    _record_path(catalog, source_item["content_sha256"]).read_bytes(),
                )
                manifest = archive.read("sunofriend-garageband-pack.json").decode()
                self.assertNotIn(str(root), manifest)
                self.assertNotIn("private bass note", manifest)
                self.assertIn('"source_audio_opt_in": true', manifest)
            source_path = _record_path(catalog, source_item["content_sha256"])
            source_path.write_bytes(source_path.read_bytes() + b"drift")
            with self.assertRaisesRegex(ValueError, "changed after it was catalogued"):
                artifacts.build_garageband_pack(
                    catalog, current, plan["plan_sha256"], basket
                )

    def test_default_pack_renders_proxy_once_and_preserves_all_selected_midi(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _pack_catalog(root)
            current = _current_state(catalog)
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"test-soundfont")
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            plan = artifacts.garageband_pack_plan(catalog, current)

            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_fake_render,
            ) as renderer:
                pack = artifacts.build_garageband_pack(
                    catalog,
                    current,
                    plan["plan_sha256"],
                    plan["default_basket"],
                )
                repeated = artifacts.build_garageband_pack(
                    catalog,
                    current,
                    plan["plan_sha256"],
                    plan["default_basket"],
                )

            self.assertEqual(renderer.call_count, 1)
            self.assertTrue(repeated["cache_hit"])
            self.assertTrue(Path(pack["acceptance_review"]["path"]).is_file())
            self.assertTrue(Path(pack["acceptance_seed"]["path"]).is_file())
            acceptance_seed = json.loads(
                Path(pack["acceptance_seed"]["path"]).read_text(encoding="utf-8")
            )
            self.assertEqual(acceptance_seed["status"], "unreviewed")
            self.assertEqual(acceptance_seed["quiz"]["question_count"], 10)
            self.assertEqual(
                acceptance_seed["pack"]["sha256"], pack["zip"]["sha256"]
            )
            with zipfile.ZipFile(pack["zip"]["path"]) as archive:
                self.assertIn("MIDI/selected-arrangement-proxy.mid", archive.namelist())
                self.assertIn(
                    "PREVIEW/selected-arrangement-proxy.wav", archive.namelist()
                )
                for item in plan["items"]:
                    if item["kind"] != "selected_midi":
                        continue
                    self.assertEqual(
                        archive.read(item["archive_paths"][0]),
                        _record_path(catalog, item["content_sha256"]).read_bytes(),
                    )

    def test_stale_plan_and_changed_source_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _pack_catalog(root)
            current = _current_state(catalog)
            artifacts = WorkbenchArtifacts(root / "state" / "artifacts")
            plan = artifacts.garageband_pack_plan(catalog, current)
            midi_id = next(
                item["item_id"]
                for item in plan["items"]
                if item["kind"] == "selected_midi"
            )
            source = next(
                item for item in plan["items"] if item["kind"] == "source_audio"
            )
            basket = canonical_garageband_pack_basket(
                plan, [midi_id, source["item_id"]], True
            )
            changed_current = _current_state(
                catalog, contexts=("full_mix", "solo")
            )
            with self.assertRaises(WorkbenchPackConflictError):
                artifacts.build_garageband_pack(
                    catalog, changed_current, plan["plan_sha256"], basket
                )

            source_path = _record_path(catalog, source["content_sha256"])
            source_path.write_bytes(source_path.read_bytes() + b"changed")
            with self.assertRaisesRegex(ValueError, "changed after it was catalogued"):
                artifacts.build_garageband_pack(
                    catalog, current, plan["plan_sha256"], basket
                )

    def test_overlap_gate_blocks_pack_until_both_decisions_are_full_mix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _pack_catalog(root, shared_source=True, overlapping=True)
            artifacts = WorkbenchArtifacts(root / "state" / "artifacts")
            solo = _current_state(catalog, contexts=("solo", "solo"))
            plan = artifacts.garageband_pack_plan(catalog, solo)

            self.assertTrue(plan["build_blocked"])
            self.assertIn(
                "selected-midi-overlap-needs-full-mix-confirmation",
                plan["block_reasons"],
            )
            with self.assertRaisesRegex(ValueError, "build is blocked"):
                artifacts.build_garageband_pack(
                    catalog, solo, plan["plan_sha256"], plan["default_basket"]
                )

            confirmed = _current_state(
                catalog, contexts=("full_mix", "full_mix")
            )
            confirmed_plan = artifacts.garageband_pack_plan(catalog, confirmed)
            self.assertFalse(confirmed_plan["build_blocked"])
            self.assertEqual(
                confirmed_plan["basket_scope_sha256"], plan["basket_scope_sha256"]
            )


def _pack_catalog(
    root: Path,
    *,
    shared_source: bool = False,
    overlapping: bool = False,
) -> dict[str, object]:
    project = root / "Pack Song-D minor-120bpm-440hz"
    candidates = root / "candidates"
    project.mkdir()
    candidates.mkdir()
    bass_source = project / "Pack Song-bass-D minor-120bpm-440hz.wav"
    keys_source = project / "Pack Song-keys-D minor-120bpm-440hz.wav"
    bass_source.write_bytes(b"RIFF-bass-source")
    keys_source.write_bytes(b"RIFF-keys-source")
    bass_midi = candidates / "bass.mid"
    keys_midi = candidates / "keys.mid"
    rejected_midi = candidates / "keys-rejected.mid"
    common = [
        NoteEvent(index * 0.25, index * 0.25 + 0.15, 48 + (index % 3), 90)
        for index in range(10)
    ]
    _write_midi(bass_midi, common if overlapping else common[:2], bpm=120.0)
    _write_midi(
        keys_midi,
        common if overlapping else [NoteEvent(0.5, 0.9, 64, 80)],
        bpm=120.0,
    )
    _write_midi(
        rejected_midi,
        [NoteEvent(0.25, 0.4, 72, 70)],
        bpm=120.0,
    )
    document = root / "catalog.json"
    document.write_text(
        json.dumps(
            {
                "schema": "sunofriend.workbench-catalog.v1",
                "stems": [
                    {
                        "source": str(bass_source),
                        "role": "bass",
                        "candidates": [{"midi": str(bass_midi)}],
                    },
                    {
                        "source": str(bass_source if shared_source else keys_source),
                        "role": "keys",
                        "candidates": [
                            {"midi": str(keys_midi)},
                            {"midi": str(rejected_midi)},
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return build_workbench_catalog(
        project,
        candidate_roots=[candidates],
        catalog_path=document,
    )


def _current_state(
    catalog: dict[str, object],
    *,
    contexts: tuple[str, str] = ("solo", "solo"),
) -> dict[str, object]:
    states: dict[str, object] = {}
    for index, stem in enumerate(catalog["stems"]):  # type: ignore[index]
        candidate = stem["candidates"][0]
        decision = "main" if index == 0 else "optional"
        decisions = {
            candidate["candidate_id"]: {
                "decision": decision,
                "context": contexts[index],
                "problem_tags": [],
                "notes": "private bass note" if index == 0 else None,
            }
        }
        if index == 1:
            rejected = stem["candidates"][1]
            decisions[rejected["candidate_id"]] = {
                "decision": "reject",
                "context": "full_mix",
                "problem_tags": ["extra_notes"],
                "notes": "private rejected note",
            }
        states[stem["stem_id"]] = {
            "role": stem["role"],
            "candidates": decisions,
            "main_candidate_id": (
                candidate["candidate_id"] if decision == "main" else None
            ),
        }
    return {"stems": states, "event_count": 3}


def _write_midi(path: Path, notes: list[NoteEvent], *, bpm: float) -> None:
    write_midi_file(path, [MidiTrack("Fixture", 0, 0, notes)], bpm=bpm)


def _fake_render(_midi: Path, output: Path, **_kwargs: object) -> None:
    output.write_bytes(b"RIFF" + (b"\0" * 2048))


def _record_path(catalog: dict[str, object], sha256: str) -> Path:
    for stem in catalog["stems"]:  # type: ignore[index]
        if stem["source"]["sha256"] == sha256:
            return Path(stem["source"]["path"])
        for candidate in stem["candidates"]:
            if candidate["midi"]["sha256"] == sha256:
                return Path(candidate["midi"]["path"])
    raise AssertionError(f"record not found: {sha256}")


if __name__ == "__main__":
    unittest.main()
