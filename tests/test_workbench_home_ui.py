from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


class WorkbenchHomeUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.page = Path("src/sunofriend/workbench.html").read_text(encoding="utf-8")
        cls.home = cls.page.split("const homeOutcomeLabels", 1)[1].split(
            "function render(){", 1
        )[0]

    def test_project_overview_is_the_default_and_has_semantic_status(self) -> None:
        self.assertIn("view='home'", self.page)
        self.assertIn('id="project-nav"', self.page)
        self.assertIn("Project overview", self.home)
        self.assertIn("Recommended next workflow step", self.home)
        self.assertIn("Stem status", self.home)
        self.assertIn('<th scope="col">Heard role</th>', self.home)
        self.assertIn('<th scope="row">', self.home)
        self.assertIn('role="status" aria-live="polite"', self.page)
        self.assertIn("aria-current", self.page)

    def test_status_and_next_action_use_only_server_project_home(self) -> None:
        self.assertIn("const home=project.home", self.home)
        self.assertIn("home?.next_step", self.home)
        self.assertIn("home.stems.map", self.home)
        self.assertIn("candidate_count", self.home)
        self.assertIn("decision_counts", self.home)
        self.assertNotIn("ai_diagnostics", self.home)
        self.assertNotIn("quality_metrics", self.home)
        self.assertNotIn("candidate.label", self.home)
        self.assertNotIn("candidate.process", self.home)

    def test_home_navigation_has_no_feedback_or_midi_effect(self) -> None:
        self.assertIn(
            "It never ranks a candidate, changes a musical choice or records feedback",
            self.home,
        )
        self.assertIn("function navigate(nextView,stemId=null)", self.home)
        self.assertNotIn("/api/events", self.home)
        self.assertNotIn("candidate_decision", self.home)
        self.assertNotIn("midi-transform", self.home)
        self.assertNotIn("renderNeutralPreview", self.home)

    def test_reload_boundary_and_focus_recovery_are_explicit(self) -> None:
        self.assertIn("Saved decisions were restored from this local project", self.home)
        self.assertIn("Temporary audition controls start fresh after a reload", self.home)
        for item in ("playhead", "loop", "visibility", "mute", "solo", "level"):
            self.assertIn(item, self.home)
        self.assertIn("function focusMainHeading()", self.home)
        self.assertIn("stem:'#choose-midi-heading'", self.home)
        self.assertIn("arrangement:'#hear-arrangement-heading'", self.home)
        self.assertIn("export:'#compose-pack-heading'", self.home)
        self.assertIn("heading.setAttribute('tabindex','-1')", self.home)
        self.assertIn("heading.focus()", self.home)

    def test_advanced_candidate_audio_does_not_preload(self) -> None:
        self.assertIn("candidate.primary?`preload=", self.page)
        self.assertIn('preload="none" data-src=', self.page)
        self.assertIn("function hydrateAudio(audio)", self.page)
        self.assertIn("delete audio.dataset.src", self.page)
        self.assertIn("function waitForAudioMetadata(audio)", self.page)
        self.assertIn("played=await switchAudio(audio,button)", self.page)

    def test_deferred_audio_cannot_restart_after_stop_or_navigation(self) -> None:
        self.assertIn("audioSwitchRequest+=1", self.page)
        self.assertIn("const requestId=++audioSwitchRequest", self.page)
        self.assertIn("requestId!==audioSwitchRequest||!audio.isConnected", self.page)
        self.assertIn("audio.pause();return false", self.page)

    def test_initial_connection_failure_is_announced_and_retryable(self) -> None:
        self.assertIn("function renderProjectLoadFailure(error)", self.page)
        self.assertIn("Reconnect to the local Workbench", self.page)
        self.assertIn('role="alert"', self.page)
        self.assertIn('id="retry-project"', self.page)
        self.assertIn("Retry local connection", self.page)
        self.assertIn("use the newest local URL", self.page)
        self.assertIn("Nothing was changed", self.page)
        self.assertIn("initialiseProject({focusAfter:true})", self.page)

    def test_saved_pack_status_failure_does_not_block_the_project(self) -> None:
        self.assertIn("/api/garageband-pack-plan", self.home)
        self.assertIn("Saved pack status could not be checked", self.home)
        self.assertIn("project and MIDI decisions are still available", self.home)
        self.assertIn("nothing was changed", self.home)
        self.assertIn('id="retry-home-pack"', self.home)

    def test_navigation_and_private_export_are_inert_before_project_load(self) -> None:
        self.assertIn('id="project-nav" class="nav-button section-nav" disabled', self.page)
        self.assertIn('id="arrangement-nav" class="nav-button section-nav" disabled', self.page)
        self.assertIn('id="export-nav" class="nav-button section-nav" disabled', self.page)
        self.assertIn('id="review-export" aria-disabled="true" tabindex="-1"', self.page)
        self.assertIn("if(!project||event.currentTarget.getAttribute('aria-disabled')==='true')return", self.page)
        self.assertIn("if(!enabled)review.removeAttribute('href')", self.page)
        self.assertIn("setNavigationEnabled(false);", self.page)

    def test_async_pack_refresh_preserves_meaningful_keyboard_focus(self) -> None:
        self.assertIn("document.activeElement?.id==='compose-pack-heading'", self.page)
        self.assertIn("document.activeElement?.id==='retry-pack-plan'", self.page)
        self.assertIn("loadPackPlan({focusAfter:true})", self.page)
        self.assertIn("if(packLoadFailed)document.querySelector('#retry-pack-plan')?.focus()", self.page)
        self.assertIn("function captureHomeFocus()", self.page)
        self.assertIn("function restoreHomeFocus(identity)", self.page)
        self.assertIn("active?.dataset?.homeStem", self.page)
        self.assertIn("'home-next-action'", self.page)

    def test_role_change_invalidates_arrangement_and_pack_state(self) -> None:
        self.assertIn("event.event_type==='role_tag'", self.page)
        self.assertIn("homePackRequest+=1", self.page)
        self.assertIn("homePackLoading=false", self.page)
        self.assertIn("homePackStatus=null", self.page)

    def test_successful_pack_status_retry_clears_the_live_error(self) -> None:
        self.assertIn(
            "homePackStatus={saved:!!basket.saved,plan_current:basket.plan_current!==false",
            self.page,
        )
        self.assertIn(
            "setAppStatus('Local project connected. Saved decisions are available.','ready')",
            self.home,
        )
        self.assertIn("homePackRequest+=1;homePackLoading=false;homePackFailed=false", self.page)

    def test_saved_outcome_is_visible_even_with_selected_candidates(self) -> None:
        self.assertIn("if(row.outcome)choices.push", self.home)
        self.assertNotIn("if(!choices.length&&row.outcome)", self.home)

    def test_former_selection_blocked_by_diagnostics_is_explained(self) -> None:
        self.assertIn("row.blocked_selected_count", self.home)
        self.assertIn("former selection", self.home)
        self.assertIn("now blocked", self.home)

    def test_embedded_javascript_is_valid(self) -> None:
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is not installed")
        script = self.page.split("<script>", 1)[1].split("</script>", 1)[0]
        syntax = subprocess.run(
            [node, "--check"],
            input=script,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)


if __name__ == "__main__":
    unittest.main()
