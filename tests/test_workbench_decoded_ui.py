from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


class WorkbenchDecodedComparisonUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.page = Path("src/sunofriend/workbench.html").read_text(encoding="utf-8")
        cls.decoded = cls.page.split("function decodedExtras", 1)[1].split(
            "function diagnosticDetails", 1
        )[0]
        cls.candidate_card = cls.page.split("function candidateCard", 1)[1].split(
            "function timelineVisibilityKey", 1
        )[0]
        cls.switch_audio = cls.page.split("async function switchAudio", 1)[1].split(
            "function wireStem", 1
        )[0]

    def test_precise_loop_is_primary_and_compatibility_fallback_is_explicit(self) -> None:
        self.assertIn("Precise short-loop comparison", self.page)
        self.assertIn("One decoded audio clock", self.page)
        self.assertIn("0.5–15 second window", self.page)
        self.assertIn("Prepare precise loop", self.page)
        self.assertIn('id="decoded-included-summary"', self.decoded)
        self.assertIn("function decodedIncludedText", self.decoded)
        self.assertIn(
            "Compatibility fallback — time-synchronised, not sample-accurate",
            self.page,
        )
        self.assertIn("startup and loop boundaries can drift", self.page)
        self.assertIn("fallback audition controls also record no review feedback", self.page)
        self.assertIn('id="compatibility-fallback"', self.page)

    def test_candidate_players_cannot_bypass_the_shared_controls(self) -> None:
        self.assertIn('<audio id="audio-${esc(candidate.candidate_id)}" hidden', self.page)
        self.assertNotIn('<audio id="audio-${esc(candidate.candidate_id)}" controls', self.page)
        self.assertIn('id="source-audio" hidden', self.decoded)
        self.assertNotIn('id="source-audio" controls', self.decoded)
        self.assertIn("Use the shared comparison transport above", self.page)

    def test_preparation_is_bounded_decoded_and_uses_one_transport(self) -> None:
        self.assertIn("/api/decoded-loop", self.decoded)
        self.assertIn("end-start<.5||end-start>15", self.decoded)
        self.assertIn("context.decodeAudioData", self.decoded)
        self.assertIn("new window.SunofriendWorkbenchTransport.DecodedLoopTransport", self.decoded)
        self.assertIn("decodedTransport.switchTo(key)", self.decoded)
        self.assertIn("decodedTransport.seek(playhead)", self.page)
        self.assertIn("decodedTransport.pause()", self.decoded)
        self.assertIn("decodedTransport.stop()", self.decoded)
        self.assertIn("recorded-zero timing, no inferred offset", self.decoded)
        self.assertIn("silence_padded_frames", self.decoded)
        self.assertIn("Precise loop only:", self.decoded)
        self.assertIn("Do not judge that silence as missing transcription", self.decoded)
        self.assertIn('id="decoded-padding-notice"', self.decoded)
        self.assertIn("setDecodedPaddingNotice(padding)", self.decoded)

    def test_primary_candidates_are_default_and_advanced_candidates_are_opt_in(self) -> None:
        self.assertIn("candidate.primary||extras.has(candidate.candidate_id)", self.decoded)
        self.assertIn(".slice(0,6)", self.decoded)
        self.assertIn('data-decoded-include="${esc(candidate.candidate_id)}"', self.candidate_card)
        self.assertIn("Include in precise loop", self.candidate_card)
        self.assertIn("function toggleDecodedExtra", self.decoded)
        self.assertIn("Candidate set changed", self.decoded)
        self.assertIn("updateDecodedCandidatePresentation(stem)", self.decoded)
        self.assertIn("decodedFallbackButtons(stem)", self.decoded)

    def test_changing_advanced_set_stops_fallback_before_rebuilding_controls(self) -> None:
        toggle = self.decoded.split("function toggleDecodedExtra", 1)[1]
        stop = toggle.index("stopOrdinaryAudioForDecoded()")
        status = toggle.index("clearDecodedComparison('Candidate set changed.")
        rebuild = toggle.index("updateDecodedCandidatePresentation(stem)")
        self.assertLess(stop, status)
        self.assertLess(status, rebuild)

    def test_decoded_listening_has_no_feedback_selection_or_pack_write(self) -> None:
        self.assertNotIn("/api/events", self.decoded)
        self.assertNotIn("candidate_decision", self.decoded)
        self.assertNotIn("candidate_auditioned", self.decoded)
        self.assertNotIn("candidate_auditioned", self.page)
        self.assertNotIn("garageband-pack", self.decoded)
        self.assertIn("No choice or review feedback was saved", self.decoded)
        self.assertIn("nothing was saved", self.decoded.lower())
        self.assertIn("fallback audition controls also record no review feedback", self.decoded)

    def test_failures_are_retryable_and_never_silently_downgrade(self) -> None:
        self.assertIn("function decodedFailure", self.decoded)
        self.assertIn("Precise comparison unavailable", self.decoded)
        self.assertIn("prepare.disabled=false", self.decoded)
        self.assertIn("fallback.open=true", self.decoded)
        self.assertIn("explicitly labelled compatibility fallback", self.decoded)
        self.assertIn("AbortController", self.decoded)
        self.assertIn("requestId!==decodedRequest", self.decoded)
        self.assertIn("prepare.disabled=!stem||!decodedCandidateIds(stem).length", self.decoded)

    def test_transport_ownership_and_accessible_active_state_are_explicit(self) -> None:
        self.assertIn("function stopOrdinaryAudioForDecoded", self.decoded)
        self.assertIn("stopOrdinaryAudioForDecoded();if(!wasPlaying", self.decoded)
        self.assertIn("if(decodedTransport)pauseDecodedComparison()", self.page)
        self.assertIn('role="group" aria-label="Precise decoded comparison controls"', self.decoded)
        self.assertIn('aria-pressed="false"', self.decoded)
        self.assertIn("button.setAttribute('aria-pressed',String(active))", self.decoded)
        self.assertIn("No choice or review feedback was saved", self.decoded)
        self.assertIn("decodedTransport.seek(resumeAt)", self.decoded)
        self.assertIn("function stopFallbackAudio", self.page)
        self.assertIn("prepared precise loop remains ready", self.page)

    def test_server_rendered_previews_refresh_without_destroying_the_loop(self) -> None:
        self.assertIn("function refreshPreparedCandidatePanels", self.decoded)
        self.assertIn("await api('/api/project')", self.decoded)
        self.assertIn("data-candidate-preview", self.page)
        self.assertIn("candidatePreviewHtml(existing||candidate)", self.decoded)
        self.assertIn("updateDecodedCandidatePresentation(stem)", self.decoded)

    def test_preview_refresh_guards_every_stale_view_dom_boundary(self) -> None:
        refresh = self.decoded.split(
            "async function refreshPreparedCandidatePanels", 1
        )[1].split("async function prepareDecodedComparison", 1)[0]
        guard = "if(!decodedRefreshIsCurrent(stem,requestId))return null"
        self.assertIn("function decodedRefreshIsCurrent", self.decoded)
        self.assertGreaterEqual(refresh.count(guard), 7)
        self.assertIn(f"{guard};document.querySelector('#review-export').href", refresh)
        self.assertIn(f"{guard};setAppStatus(", refresh)
        self.assertIn(f"{guard};holder.innerHTML", refresh)
        self.assertIn(f"{guard};holder.querySelectorAll('audio')", refresh)
        self.assertIn(f"{guard};holder.querySelectorAll('.render-preview')", refresh)
        self.assertIn(f"{guard};updateDecodedCandidatePresentation(stem)", refresh)
        self.assertIn(f"{guard};renderNav()", refresh)
        self.assertIn("view==='stem'", self.decoded)
        self.assertIn("activeStem===stem.stem_id", self.decoded)
        self.assertIn("refreshPreparedCandidatePanels(stem,requestId)", self.decoded)

    def test_failed_fallback_switch_clears_state_and_announces_stop(self) -> None:
        self.assertIn("currentAudio=null", self.switch_audio)
        self.assertIn("item.classList.remove('playing')", self.switch_audio)
        self.assertIn("item.setAttribute('aria-pressed','false')", self.switch_audio)
        self.assertIn("Compatibility playback stopped", self.switch_audio)
        self.assertIn("Nothing was saved", self.switch_audio)

    def test_transport_is_packaged_before_the_inline_application(self) -> None:
        external = '<script src="/workbench-transport.js"></script>'
        self.assertIn(external, self.page)
        self.assertLess(self.page.index(external), self.page.index("const token="))

    def test_embedded_application_javascript_remains_valid(self) -> None:
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
