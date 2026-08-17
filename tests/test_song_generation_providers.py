from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

from sunofriend.cli import main
from sunofriend.song_generation_providers import (
    SONG_GENERATION_PROVIDERS_SCHEMA,
    provider_capability,
    registered_provider_ids,
    song_generation_providers_document,
)


class SongGenerationProviderTests(unittest.TestCase):
    def test_registry_is_secret_free_and_capability_gated(self) -> None:
        document = song_generation_providers_document()

        self.assertEqual(document["schema"], SONG_GENERATION_PROVIDERS_SCHEMA)
        self.assertEqual(document["default_provider"], "ace-step-api")
        self.assertEqual(registered_provider_ids(), ("ace-step-api",))
        self.assertTrue(document["selection_policy"]["registered_only"])
        self.assertTrue(
            document["selection_policy"]["cloud_requires_explicit_enablement"]
        )
        encoded = json.dumps(document, sort_keys=True)
        self.assertIn("SUNOFRIEND_TREBLO_API_KEY", encoded)
        self.assertNotIn("Bearer ", encoded)
        self.assertNotIn("api_key_value", encoded)

    def test_treblo_is_visible_but_not_registered_for_reference_conditioning(self) -> None:
        provider = provider_capability("treblo-v3-api")

        self.assertEqual(provider["provider_type"], "proprietary_cloud_byok")
        self.assertFalse(
            provider["registration"]["reference_conditioned_full_song"]
        )
        self.assertTrue(provider["capabilities"]["prompt_and_supplied_lyrics"])
        self.assertFalse(
            provider["capabilities"]["annotated_lyrics_semantics_verified"]
        )
        self.assertFalse(
            provider["capabilities"]["reference_audio_conditioning"]
        )
        self.assertFalse(
            provider["capabilities"]["independent_reference_strength"]
        )
        self.assertEqual(provider["capabilities"]["candidate_count_per_request"], 1)
        self.assertEqual(
            provider["privacy_and_access"]["remote_result_retention_hours"],
            168,
        )
        self.assertTrue(provider["privacy_and_access"]["attribution_required"])
        self.assertTrue(
            provider["integration_policy"][
                "polling_preferred_until_webhook_signing_is_documented"
            ]
        )

    def test_provider_cli_prints_the_same_read_only_inventory(self) -> None:
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            exit_code = main(["song-providers"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), song_generation_providers_document())

    def test_unknown_provider_lookup_is_bounded(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown song-generation provider"):
            provider_capability("unknown")


if __name__ == "__main__":
    unittest.main()
