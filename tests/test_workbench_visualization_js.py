from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


VISUALIZATION_PATH = Path(
    "src/sunofriend/workbench_visualization.js"
).resolve()


class WorkbenchVisualizationJavaScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.node = shutil.which("node")
        if not cls.node:
            raise unittest.SkipTest("Node.js is not installed")

    def run_node(self, body: str) -> dict[str, object]:
        script = f"""
const visualization = require({json.dumps(str(VISUALIZATION_PATH))});
{body}
"""
        result = subprocess.run(
            [self.node, "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_long_song_viewports_clamp_centre_and_page_without_growth(self) -> None:
        result = self.run_node(
            """
const fit = visualization.clampViewport(21600, 0.25, -300);
const right = visualization.clampViewport(21600, 12, 99999);
const centred = visualization.centreViewport(right, 10800);
const firstPage = visualization.pageViewport(centred, -100);
const lastPage = visualization.pageViewport(centred, 100);
const samePage = visualization.pageViewport(centred, 0);
const veryClose = visualization.clampViewport(21600, 1e12, 100);
const empty = visualization.clampViewport(0, 4, 99);
console.log(JSON.stringify({
  fit,
  right,
  centred,
  firstPage,
  lastPage,
  samePage,
  veryClose,
  empty,
  frozen: [fit, right, centred, firstPage, lastPage].every(Object.isFrozen),
}));
"""
        )

        self.assertEqual(result["fit"]["zoom"], 1)
        self.assertEqual(result["fit"]["startSeconds"], 0)
        self.assertEqual(result["fit"]["endSeconds"], 21600)
        self.assertEqual(result["right"]["durationSeconds"], 1800)
        self.assertEqual(result["right"]["startSeconds"], 19800)
        self.assertEqual(result["right"]["endSeconds"], 21600)
        self.assertEqual(result["centred"]["startSeconds"], 9900)
        self.assertEqual(result["centred"]["endSeconds"], 11700)
        self.assertEqual(result["firstPage"]["startSeconds"], 0)
        self.assertEqual(result["lastPage"]["startSeconds"], 19800)
        self.assertEqual(result["samePage"]["startSeconds"], 9900)
        self.assertEqual(result["veryClose"]["durationSeconds"], 0.5)
        self.assertEqual(result["empty"]["durationSeconds"], 0)
        self.assertTrue(result["frozen"])

    def test_ticks_are_song_anchored_bounded_and_deterministic(self) -> None:
        result = self.run_node(
            """
const viewport = visualization.clampViewport(21600, 6, 5400);
const first = visualization.buildViewportTicks(viewport, 6);
const second = visualization.buildViewportTicks(viewport, 6);
const offsetViewport = visualization.clampViewport(100, 4, 3.125);
const offset = visualization.buildViewportTicks(offsetViewport, 6);
console.log(JSON.stringify({
  first,
  repeated: JSON.stringify(first) === JSON.stringify(second),
  firstFrozen: Object.isFrozen(first) && first.every(Object.isFrozen),
  offset,
}));
"""
        )

        self.assertTrue(result["repeated"])
        self.assertTrue(result["firstFrozen"])
        self.assertEqual(
            [tick["seconds"] for tick in result["first"]],
            [5400, 6000, 6600, 7200, 7800, 8400, 9000],
        )
        self.assertTrue(all(tick["stepSeconds"] == 600 for tick in result["first"]))
        self.assertEqual(result["first"][0]["ratio"], 0)
        self.assertEqual(result["first"][-1]["ratio"], 1)
        self.assertEqual(result["offset"][0]["seconds"], 3.125)
        self.assertEqual(result["offset"][-1]["seconds"], 28.125)
        self.assertTrue(result["offset"][0]["edge"])
        self.assertTrue(result["offset"][-1]["edge"])
        self.assertLessEqual(len(result["offset"]), 9)

    def test_interval_index_finds_crossing_notes_with_stable_order(self) -> None:
        result = self.run_node(
            """
const notes = [
  {id: "right-edge", start_seconds: 16, end_seconds: 17, pitch: 65},
  {id: "cross-left", start_seconds: 10, end_seconds: 20, pitch: 60},
  {id: "ends-at-left", start_seconds: 14, end_seconds: 15, pitch: 61},
  {id: "same-start-first", start_seconds: 15, end_seconds: 16, pitch: 62},
  {id: "zero", start_seconds: 15, end_seconds: 15, pitch: 63},
  {id: "same-start-second", start_seconds: 15, end_seconds: 16, pitch: 64},
  {id: "cross-right", start_seconds: 15.5, end_seconds: 30, pitch: 67},
];
const before = JSON.stringify(notes);
const index = visualization.buildNoteIntervalIndex(notes);
const exact = visualization.queryNoteIntervalIndex(index, 15, 16);
const overscan = visualization.queryNoteIntervalIndex(index, 15, 16, 0.1);
const emptyIndex = visualization.buildNoteIntervalIndex([]);
const empty = visualization.queryNoteIntervalIndex(emptyIndex, 1, 2);
console.log(JSON.stringify({
  exact: exact.map(note => note.id),
  overscan: overscan.map(note => note.id),
  empty,
  inputUnchanged: before === JSON.stringify(notes),
  copied: index.entries.every(entry => entry.note !== notes[entry.sourceIndex]),
  frozen: Object.isFrozen(index) && Object.isFrozen(index.entries) &&
    Object.isFrozen(index.prefixMaximumEndSeconds) && exact.every(Object.isFrozen),
  sorted: index.entries.map(entry => entry.note.id),
}));
"""
        )

        self.assertEqual(
            result["exact"],
            ["cross-left", "same-start-first", "same-start-second", "cross-right"],
        )
        self.assertEqual(
            result["overscan"],
            [
                "cross-left",
                "ends-at-left",
                "same-start-first",
                "same-start-second",
                "cross-right",
                "right-edge",
            ],
        )
        self.assertEqual(result["empty"], [])
        self.assertTrue(result["inputUnchanged"])
        self.assertTrue(result["copied"])
        self.assertTrue(result["frozen"])
        self.assertEqual(result["sorted"][:2], ["cross-left", "ends-at-left"])
        self.assertLess(
            result["sorted"].index("same-start-first"),
            result["sorted"].index("same-start-second"),
        )

    def test_waveform_slice_retains_absolute_positions_and_is_bounded(self) -> None:
        result = self.run_node(
            """
const bins = Array.from({length: 10000}, (_, index) => [
  -(index + 1) / 10000,
  (index + 1) / 10000,
]);
const beforeStart = JSON.stringify(bins.slice(1995, 2016));
const viewport = visualization.clampViewport(10000, 1000, 2000);
const exact = visualization.sliceWaveformBins(bins, 10000, viewport);
const overscan = visualization.sliceWaveformBins(bins, 10000, viewport, 0.25);
const finalViewport = visualization.clampViewport(10000, 1000, 99999);
const finalSlice = visualization.sliceWaveformBins(bins, 10000, finalViewport);
const empty = visualization.sliceWaveformBins(
  [],
  10000,
  visualization.clampViewport(10000, 1, 0)
);
const shorterViewport = visualization.clampViewport(20, 4, 15);
const shorter = visualization.sliceWaveformBins(
  Array.from({length: 10}, (_, index) => [-index / 10, index / 10]),
  10,
  shorterViewport
);
console.log(JSON.stringify({
  exact,
  overscanCount: overscan.bins.length,
  overscanFirst: overscan.bins[0],
  overscanLast: overscan.bins[overscan.bins.length - 1],
  finalStart: finalSlice.startIndex,
  finalEnd: finalSlice.endIndexExclusive,
  empty,
  shorter,
  inputUnchanged: beforeStart === JSON.stringify(bins.slice(1995, 2016)),
  frozen: Object.isFrozen(exact) && Object.isFrozen(exact.bins) &&
    exact.bins.every(Object.isFrozen),
}));
"""
        )

        exact = result["exact"]
        self.assertEqual(exact["startIndex"], 2000)
        self.assertEqual(exact["endIndexExclusive"], 2010)
        self.assertEqual(len(exact["bins"]), 10)
        self.assertEqual(exact["bins"][0]["binIndex"], 2000)
        self.assertEqual(exact["bins"][0]["startSeconds"], 2000)
        self.assertEqual(exact["bins"][-1]["endSeconds"], 2010)
        self.assertEqual(exact["bins"][0]["fullSongStartRatio"], 0.2)
        self.assertEqual(result["overscanCount"], 12)
        self.assertEqual(result["overscanFirst"]["binIndex"], 1999)
        self.assertEqual(result["overscanLast"]["binIndex"], 2010)
        self.assertEqual(result["finalStart"], 9990)
        self.assertEqual(result["finalEnd"], 10000)
        self.assertEqual(result["empty"]["bins"], [])
        self.assertEqual(result["shorter"]["bins"], [])
        self.assertEqual(result["shorter"]["visibleStartSeconds"], 15)
        self.assertEqual(result["shorter"]["visibleEndSeconds"], 20)
        self.assertEqual(result["shorter"]["sliceStartSeconds"], 10)
        self.assertEqual(result["shorter"]["sliceEndSeconds"], 10)
        self.assertTrue(result["inputUnchanged"])
        self.assertTrue(result["frozen"])

    def test_malformed_and_non_finite_inputs_fail_closed(self) -> None:
        result = self.run_node(
            """
const validViewport = visualization.clampViewport(10, 2, 0);
const validIndex = visualization.buildNoteIntervalIndex([
  {start_seconds: 0, end_seconds: 1},
]);
const operations = [
  () => visualization.clampViewport("10", 1, 0),
  () => visualization.clampViewport(10, 0, 0),
  () => visualization.clampViewport(10, 1, Infinity),
  () => visualization.centreViewport({startSeconds: 0}, 1),
  () => visualization.pageViewport(validViewport, 1.5),
  () => visualization.buildViewportTicks(validViewport, 1),
  () => visualization.buildNoteIntervalIndex(null),
  () => visualization.buildNoteIntervalIndex([
    {start_seconds: "0", end_seconds: 1},
  ]),
  () => visualization.buildNoteIntervalIndex([
    {start_seconds: 2, end_seconds: 1},
  ]),
  () => visualization.queryNoteIntervalIndex({}, 0, 1),
  () => visualization.queryNoteIntervalIndex(validIndex, 1, 1),
  () => visualization.queryNoteIntervalIndex(validIndex, 0, 1, 5.1),
  () => visualization.sliceWaveformBins(null, 10, validViewport),
  () => visualization.sliceWaveformBins([[1]], 10, validViewport),
  () => visualization.sliceWaveformBins([[1, -1]], 10, validViewport),
  () => visualization.sliceWaveformBins([[0, 1]], 11, validViewport),
];
const errors = operations.map(operation => {
  try {
    operation();
    return null;
  } catch (error) {
    return {name: error.name, message: error.message};
  }
});
console.log(JSON.stringify({errors}));
"""
        )

        self.assertEqual(len(result["errors"]), 16)
        self.assertTrue(all(error is not None for error in result["errors"]))
        self.assertTrue(
            all(error["name"] in {"TypeError", "RangeError"} for error in result["errors"])
        )
        self.assertIn("finite number", result["errors"][0]["message"])
        self.assertIn("must come from", result["errors"][9]["message"])
        self.assertIn("must not exceed", result["errors"][11]["message"])

    def test_module_publishes_browser_global_without_browser_dependencies(self) -> None:
        source = VISUALIZATION_PATH.read_text(encoding="utf-8")
        for forbidden in (
            "document.",
            "fetch(",
            "localStorage",
            "sessionStorage",
            "addEventListener",
            "dispatchEvent",
        ):
            self.assertNotIn(forbidden, source)

        result = self.run_node(
            f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({json.dumps(str(VISUALIZATION_PATH))}, "utf8");
const context = {{}};
vm.createContext(context);
vm.runInContext(source, context);
console.log(JSON.stringify({{
  globalName: typeof context.SunofriendWorkbenchVisualization,
  exports: Object.keys(context.SunofriendWorkbenchVisualization).sort(),
}}));
"""
        )

        self.assertEqual(result["globalName"], "object")
        self.assertEqual(
            result["exports"],
            sorted(
                [
                    "MINIMUM_VIEWPORT_SECONDS",
                    "MAXIMUM_OVERSCAN_SECONDS",
                    "clampViewport",
                    "centreViewport",
                    "pageViewport",
                    "buildViewportTicks",
                    "buildNoteIntervalIndex",
                    "queryNoteIntervalIndex",
                    "sliceWaveformBins",
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
