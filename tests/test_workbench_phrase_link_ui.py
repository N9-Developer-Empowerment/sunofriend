from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


class WorkbenchPhraseLinkUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.page = Path("src/sunofriend/workbench.html").read_text(encoding="utf-8")
        cls.phrase_ui = cls.page.split("function phraseRanges", 1)[1].split(
            "function timelinePanel", 1
        )[0]

    def test_panel_is_inserted_below_timeline_only_when_ranges_exist(self) -> None:
        self.assertIn("stem?.phrase_review_link?.ranges", self.phrase_ui)
        self.assertIn("if(!link||!ranges.length)return''", self.phrase_ui)
        self.assertIn("timeline.insertAdjacentHTML('afterend',html)", self.phrase_ui)
        self.assertIn("renderStem();renderPhraseRanges()", self.page)
        self.assertIn("Disputed phrase ranges", self.phrase_ui)
        self.assertIn("Review unit", self.phrase_ui)

    def test_copy_explains_the_diagnostic_boundary(self) -> None:
        self.assertIn("where transcription methods disagree", self.phrase_ui)
        self.assertIn(
            "They do not say which result is accurate or preferred", self.phrase_ui
        )
        self.assertIn("phrase_review?.alternative_names", self.phrase_ui)
        self.assertIn("guide-assisted appears only when", self.phrase_ui)
        self.assertIn(
            "does not compare the Workbench S0/M1/M3 candidates directly",
            self.phrase_ui,
        )
        self.assertIn("cannot choose a candidate", self.phrase_ui)
        self.assertIn("create hybrid MIDI", self.phrase_ui)
        self.assertIn("append a Workbench event", self.phrase_ui)

    def test_loop_shortcut_only_changes_temporary_listening_state(self) -> None:
        self.assertIn("Set compare loop", self.phrase_ui)
        self.assertIn("startInput.value=String(start)", self.phrase_ui)
        self.assertIn("endInput.value=String(end)", self.phrase_ui)
        self.assertIn("setSharedPlayhead(start,duration)", self.phrase_ui)
        self.assertIn("drawActiveTimeline()", self.phrase_ui)
        self.assertIn("Playback has not started and nothing was saved", self.phrase_ui)
        self.assertNotIn("/api/events", self.phrase_ui)
        self.assertNotIn("save(", self.phrase_ui)
        self.assertNotIn(".play(", self.phrase_ui)
        self.assertNotIn("decision", self.phrase_ui.lower())
        self.assertNotIn("midi edit", self.phrase_ui.lower())

    def test_phrase_review_link_targets_the_matching_existing_phrase(self) -> None:
        self.assertIn("Open existing phrase review", self.phrase_ui)
        self.assertIn(
            "#phrase-${encodeURIComponent(range.phrase_index)}", self.phrase_ui
        )
        self.assertIn('target="_blank"', self.phrase_ui)
        self.assertIn('rel="noopener noreferrer"', self.phrase_ui)

    def test_reference_count_and_optional_breakdown_are_explanatory(self) -> None:
        self.assertIn("diagnostic_reference_count", self.phrase_ui)
        self.assertIn("the count is not a quality score", self.phrase_ui)
        for field in (
            "cross_phrase_boundary_match_references",
            "same_pitch_boundary_duration_disputes",
            "octave_equivalent_onset_disputes",
            "lane_only_note_references",
            "duplicate_groups",
        ):
            self.assertIn(field, self.phrase_ui)

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
