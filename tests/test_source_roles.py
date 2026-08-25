from __future__ import annotations

import unittest

from sunofriend.source_project import normalize_source_role
from sunofriend.source_roles import (
    SourceRole,
    SourceRolePolicy,
    canonical_source_role,
    composite_source_role_ids,
    context_source_role_ids,
    derived_source_role_ids,
    flat_v1_repeatable_source_role_ids,
    infer_source_roles,
    is_context_source_role,
    is_derived_source_role,
    is_prepared_source_role,
    iter_source_role_definitions,
    prepared_source_role_ids,
    source_role_definition,
    source_role_ids,
)


class SourceRoleRegistryTests(unittest.TestCase):
    def test_registry_iteration_and_enum_inputs_are_stable(self) -> None:
        definitions = tuple(iter_source_role_definitions())

        self.assertEqual(
            [definition.role for definition in definitions],
            list(SourceRole),
        )
        self.assertTrue(
            all(
                definition.aliases[0]
                == definition.role.value.replace("_", " ")
                for definition in definitions
            )
        )
        self.assertEqual(canonical_source_role(SourceRole.BASS), "bass")
        self.assertEqual(canonical_source_role(SourceRole.BACKING_VOCALS), "backing_vocals")
        self.assertEqual(infer_source_roles(SourceRole.BASS), {"bass"})

    def test_compounds_suppress_only_their_broad_components(self) -> None:
        cases = {
            "song-backing_vocals.wav": {"backing_vocals"},
            "song backing vocal.wav": {"backing_vocals"},
            "song-lead-vocals.wav": {"vocals"},
            "song lead vocal.wav": {"vocals"},
            "song-other_kit.wav": {"other_kit"},
            "song-other-drums.wav": {"other_kit"},
            "song-electric-piano.wav": {"keys"},
            "electric.piano": {"keys"},
            "/a/bass-folder/song-keys.wav": {"keys"},
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(infer_source_roles(value), expected)

        self.assertEqual(
            infer_source_roles("backing vocals and lead.wav"),
            {"backing_vocals", "lead"},
        )
        self.assertEqual(
            infer_source_roles("other kit and other.wav"),
            {"other_kit", "other"},
        )

    def test_drum_family_labels_do_not_become_ambiguous_composites(self) -> None:
        cases = {
            "drum-kick.wav": {"kick"},
            "kick-drum.wav": {"kick"},
            "bass-drum.wav": {"kick"},
            "drums-snare.wav": {"snare"},
            "drum-hi-hats.wav": {"hat"},
            "drum-toms.wav": {"toms"},
            "drum-cymbals.wav": {"cymbals"},
            "drum-percussion.wav": {"other_kit"},
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(infer_source_roles(value), expected)

    def test_production_aliases_resolve_to_canonical_prepared_roles(self) -> None:
        cases = {
            "hat": "hat",
            "hats": "hat",
            "hi-hats": "hat",
            "hihats": "hat",
            "guitar": "rhythm",
            "guitars": "rhythm",
            "rhythm": "rhythm",
            "keyboard": "keys",
            "brass": "wind",
            "percussion": "other_kit",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(canonical_source_role(value), expected)

    def test_aliases_are_token_aware(self) -> None:
        for value in ("kickoff.wav", "tomorrow.wav", "bassoon.wav"):
            with self.subTest(value=value):
                self.assertEqual(infer_source_roles(value), frozenset())
                with self.assertRaisesRegex(ValueError, "unrecognised"):
                    canonical_source_role(value)

    def test_ambiguity_is_retained_until_a_strict_boundary(self) -> None:
        self.assertEqual(
            infer_source_roles("song-bass-and-keys.wav"),
            {"bass", "keys"},
        )
        with self.assertRaisesRegex(
            ValueError, "ambiguous source role.*bass, keys"
        ):
            canonical_source_role("song-bass-and-keys.wav")
        self.assertEqual(
            canonical_source_role(
                "mystery-part.wav", allow_unclassified=True
            ),
            "unclassified",
        )

    def test_policies_are_mutually_exclusive_and_complete(self) -> None:
        prepared = {
            "backing_vocals",
            "bass",
            "cymbals",
            "drums",
            "hat",
            "keys",
            "kick",
            "lead",
            "other",
            "other_kit",
            "piano",
            "rhythm",
            "snare",
            "strings",
            "synth",
            "toms",
            "vocals",
            "wind",
        }
        self.assertEqual(prepared_source_role_ids(), prepared)
        self.assertEqual(
            context_source_role_ids(),
            {"mix", "metronome", "unclassified"},
        )
        self.assertEqual(derived_source_role_ids(), {"pads"})
        self.assertEqual(
            source_role_ids(),
            prepared
            | {"mix", "pads", "metronome", "unclassified"},
        )
        self.assertFalse(
            prepared_source_role_ids() & context_source_role_ids()
        )
        self.assertFalse(
            prepared_source_role_ids() & derived_source_role_ids()
        )
        self.assertFalse(
            context_source_role_ids() & derived_source_role_ids()
        )

        self.assertTrue(is_prepared_source_role("bass"))
        self.assertTrue(is_context_source_role("full mix"))
        self.assertTrue(is_context_source_role("click track"))
        self.assertTrue(is_derived_source_role("pad"))
        self.assertFalse(is_prepared_source_role("pads"))
        self.assertFalse(is_context_source_role("banana"))

    def test_definition_lookup_exposes_policy_and_flat_v1_contract(self) -> None:
        keys = source_role_definition("electric piano")
        self.assertEqual(keys.role, SourceRole.KEYS)
        self.assertEqual(keys.role_id, "keys")
        self.assertEqual(keys.policy, SourceRolePolicy.PREPARED_INPUT)
        self.assertTrue(keys.is_prepared)
        self.assertTrue(keys.accepts_prepared_input)
        self.assertFalse(keys.context_only)
        self.assertFalse(keys.derived_only)

        self.assertEqual(
            flat_v1_repeatable_source_role_ids(),
            {"backing_vocals", "vocals"},
        )
        self.assertEqual(
            composite_source_role_ids(),
            {"drums", "other", "vocals"},
        )

    def test_external_vocabularies_are_not_enum_members(self) -> None:
        values = {role.value for role in SourceRole}
        for external in (
            "electric_bass",
            "clean_electric_guitar",
            "synth_strings",
            "gm_program_33",
            "clip_role",
        ):
            with self.subTest(external=external):
                self.assertNotIn(external, values)

    def test_legacy_custom_source_role_remains_opaque_and_compatible(self) -> None:
        self.assertEqual(
            normalize_source_role(
                "Custom Provider Texture",
                fallback_from="ignored.wav",
            ),
            "custom_provider_texture",
        )
        self.assertNotIn("custom_provider_texture", source_role_ids())
        with self.assertRaisesRegex(ValueError, "unrecognised"):
            canonical_source_role("Custom Provider Texture")


if __name__ == "__main__":
    unittest.main()
