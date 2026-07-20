from __future__ import annotations

import unittest
from pathlib import Path


class WorkbenchPackComposerUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.page = Path("src/sunofriend/workbench.html").read_text(encoding="utf-8")
        cls.composer = cls.page.split("function packItems", 1)[1].split(
            "async function save(event", 1
        )[0]

    def test_navigation_and_copy_keep_music_and_export_separate(self) -> None:
        self.assertIn("Compose GarageBand pack", self.page)
        self.assertIn("Musical choices and export choices are separate.", self.page)
        self.assertIn(
            "They never change a candidate's main, optional, correction or reject decision",
            self.page,
        )
        self.assertIn("Authoritative selected MIDI", self.page)
        self.assertIn("Convenience audition", self.page)
        self.assertIn("Original source stems", self.page)
        self.assertIn("Rejected, needs-correction, superseded and unreviewed", self.page)

    def test_composer_uses_only_the_pack_api_contract(self) -> None:
        self.assertIn("/api/garageband-pack-plan", self.composer)
        self.assertIn("/api/garageband-pack-basket", self.composer)
        self.assertIn("/api/garageband-pack", self.composer)
        self.assertIn("plan_sha256:packPlan.plan_sha256", self.composer)
        self.assertIn("basket_scope_sha256:packPlan.basket_scope_sha256", self.composer)
        self.assertIn("expected_revision:Number(packBasket?.revision||0)", self.composer)
        self.assertIn("included_item_ids:packDraftIds()", self.composer)
        self.assertIn("source_audio_opt_in:!!packDraft.source_audio_opt_in", self.composer)
        self.assertIn("basket_sha256:basket.basket_sha256", self.composer)
        self.assertNotIn("/api/garageband-export", self.page)
        self.assertIn("error.status=response.status", self.page)

    def test_inclusion_is_not_derived_from_audition_or_review_state(self) -> None:
        self.assertNotIn("/api/events", self.composer)
        self.assertNotIn("mixerState", self.composer)
        self.assertNotIn("timelineVisibility", self.composer)
        self.assertNotIn("mixerSelection", self.composer)
        self.assertNotIn("playAudio", self.composer)
        self.assertIn(
            "never follow playback, mute, solo, visibility or level controls",
            self.composer,
        )

    def test_source_audio_requires_a_separate_explicit_opt_in(self) -> None:
        self.assertIn('id="source-audio-opt-in"', self.composer)
        self.assertIn("source&&!packDraft?.source_audio_opt_in", self.composer)
        self.assertIn(
            "if(!consent.checked)for(const item of packItems('source_audio'))",
            self.composer,
        )
        self.assertIn(
            "Original source audio needs the separate local source-audio opt-in.",
            self.composer,
        )
        self.assertIn(
            "Listening to or displaying a stem never checks it.", self.composer
        )

    def test_safe_default_reset_and_minimum_midi_validation_are_visible(self) -> None:
        self.assertIn("function packDefaultBasket()", self.composer)
        self.assertIn("Reset to safe default", self.composer)
        self.assertIn(
            "Safe default restored: selected MIDI and the proxy are included; source audio is excluded.",
            self.composer,
        )
        self.assertIn(
            "Keep at least one authoritative selected MIDI track in the GarageBand pack.",
            self.composer,
        )
        self.assertIn("buildProblem||overlapBlocked?'disabled'", self.composer)

    def test_save_then_build_and_receipt_are_explicit(self) -> None:
        self.assertIn("Save pack choices", self.composer)
        self.assertIn("Build this exact pack", self.composer)
        self.assertIn(
            "packNeedsSave()?await savePackChoices({rerender:false}):packBasket",
            self.composer,
        )
        self.assertIn("Download GarageBand pack ZIP", self.composer)
        self.assertIn("Download path-free pack receipt", self.composer)
        self.assertIn("Pack choices saved locally", self.composer)
        self.assertIn("No local path is accepted from this page.", self.composer)
        self.assertIn("packBasket?.plan_current===false", self.composer)
        self.assertIn(
            "Saved choices restored from an earlier plan; review and save them for the current plan",
            self.composer,
        )

    def test_stale_plan_is_reloaded_visibly(self) -> None:
        self.assertIn("async function reloadPackAfterConflict(error)", self.composer)
        self.assertGreaterEqual(self.composer.count("error.status===409"), 2)
        self.assertIn(
            "The pack plan changed and was reloaded safely.", self.composer
        )
        self.assertIn("Review the current boxes before saving or building.", self.composer)

    def test_permanent_plan_failure_waits_for_an_explicit_retry(self) -> None:
        self.assertIn("packLoadFailed=true", self.composer)
        self.assertIn('id="retry-pack-plan"', self.composer)
        self.assertIn("Retry loading pack contents", self.composer)
        self.assertIn("if(packLoadFailed)", self.composer)
        self.assertIn("packLoadFailed=false;packMessage=''", self.composer)
        self.assertIn("else if(!packLoading)loadPackPlan()", self.composer)


if __name__ == "__main__":
    unittest.main()
