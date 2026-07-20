from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


TRANSPORT_PATH = Path("src/sunofriend/workbench_transport.js").resolve()


class WorkbenchTransportJavaScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.node = shutil.which("node")
        if not cls.node:
            raise unittest.SkipTest("Node.js is not installed")

    def run_node(self, body: str) -> dict[str, object]:
        script = f"""
const transportModule = require({json.dumps(str(TRANSPORT_PATH))});

class FakeBuffer {{
  constructor(numberOfChannels, length, sampleRate, channels = null) {{
    this.numberOfChannels = numberOfChannels;
    this.length = length;
    this.sampleRate = sampleRate;
    this.duration = length / sampleRate;
    this.channels = channels || Array.from(
      {{length: numberOfChannels}},
      () => new Float32Array(length)
    );
  }}
  getChannelData(channel) {{ return this.channels[channel]; }}
}}

class FakeSource {{
  constructor(id, failStart = false) {{
    this.id = id;
    this.failStart = failStart;
    this.starts = [];
    this.stops = [];
    this.connections = [];
    this.disconnectCount = 0;
    this.onended = null;
  }}
  connect(destination) {{ this.connections.push(destination); }}
  disconnect() {{ this.disconnectCount += 1; }}
  start(when, offset) {{
    if (this.failStart) throw new Error(`start failed for source ${{this.id}}`);
    this.starts.push({{when, offset}});
  }}
  stop(when) {{ this.stops.push(when); }}
}}

class FakeContext {{
  constructor(sampleRate = 10) {{
    this.sampleRate = sampleRate;
    this.currentTime = 0;
    this.destination = {{name: "destination"}};
    this.sources = [];
    this.failStartIds = new Set();
  }}
  createBuffer(numberOfChannels, length, sampleRate) {{
    return new FakeBuffer(numberOfChannels, length, sampleRate);
  }}
  createBufferSource() {{
    const id = this.sources.length + 1;
    const source = new FakeSource(id, this.failStartIds.has(id));
    this.sources.push(source);
    return source;
  }}
}}

function decodedBuffer(sampleRate, values) {{
  return new FakeBuffer(1, values.length, sampleRate, [Float32Array.from(values)]);
}}

function close(left, right, tolerance = 1e-9) {{
  return Math.abs(left - right) <= tolerance;
}}

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

    def test_buffers_are_copied_to_one_context_rate_frame_count(self) -> None:
        result = self.run_node(
            """
const context = new FakeContext(10);
const originalShort = decodedBuffer(10, [1, 2, 3]);
const originalLong = decodedBuffer(10, [4, 5, 6, 7, 8, 9, 10]);
const transport = new transportModule.DecodedLoopTransport({
  audioContext: context,
  decodedBuffers: {
    short: originalShort,
    long: originalLong,
  },
  loopStartSeconds: 4,
  loopEndSeconds: 4.5,
  scheduleLeadSeconds: 0.05,
});
const short = transport.getBuffer("short");
const long = transport.getBuffer("long");
console.log(JSON.stringify({
  frameCount: transport.frameCount,
  shortLength: short.length,
  longLength: long.length,
  shortValues: Array.from(short.getChannelData(0)),
  longValues: Array.from(long.getChannelData(0)),
  shortRate: short.sampleRate,
  longRate: long.sampleRate,
  distinctCopies: short !== originalShort && long !== originalLong && short !== long,
}));
"""
        )

        self.assertEqual(result["frameCount"], 5)
        self.assertEqual(result["shortLength"], 5)
        self.assertEqual(result["longLength"], 5)
        self.assertEqual(result["shortValues"], [1, 2, 3, 0, 0])
        self.assertEqual(result["longValues"], [4, 5, 6, 7, 8])
        self.assertEqual(result["shortRate"], 10)
        self.assertEqual(result["longRate"], 10)
        self.assertTrue(result["distinctCopies"])

    def test_switch_and_seek_share_one_future_clock_time_and_fresh_sources(self) -> None:
        result = self.run_node(
            """
const context = new FakeContext(10);
const transport = new transportModule.DecodedLoopTransport({
  audioContext: context,
  decodedBuffers: {
    source: decodedBuffer(10, [1, 1, 1, 1, 1, 1, 1, 1, 1, 1]),
    candidate: decodedBuffer(10, [2, 2, 2, 2, 2, 2, 2, 2, 2, 2]),
  },
  loopStartSeconds: 10,
  loopEndSeconds: 11,
  scheduleLeadSeconds: 0.05,
});
transport.seek(10.2);
context.currentTime = 1;
const first = transport.play("source");
context.currentTime = 1.25;
const switched = transport.switchTo("candidate");
context.currentTime = 1.5;
const sought = transport.seek(10.8);
const firstNode = context.sources[0];
const secondNode = context.sources[1];
const thirdNode = context.sources[2];
console.log(JSON.stringify({
  first,
  switched,
  sought,
  firstStart: firstNode.starts[0],
  firstStop: firstNode.stops[0],
  secondStart: secondNode.starts[0],
  secondStop: secondNode.stops[0],
  thirdStart: thirdNode.starts[0],
  sourceIds: context.sources.map(source => source.id),
  sameSwitchTime: close(firstNode.stops[0], secondNode.starts[0].when),
  sameSeekTime: close(secondNode.stops[0], thirdNode.starts[0].when),
  serial: transport.sourceSerial,
}));
"""
        )

        self.assertAlmostEqual(result["firstStart"]["when"], 1.05)
        self.assertAlmostEqual(result["firstStart"]["offset"], 0.2)
        self.assertTrue(result["sameSwitchTime"])
        self.assertTrue(result["sameSeekTime"])
        self.assertAlmostEqual(result["switched"]["when"], 1.3)
        self.assertAlmostEqual(result["secondStart"]["offset"], 0.45)
        self.assertAlmostEqual(result["sought"]["when"], 1.55)
        self.assertAlmostEqual(result["thirdStart"]["offset"], 0.8)
        self.assertEqual(result["sourceIds"], [1, 2, 3])
        self.assertEqual(result["serial"], 3)

    def test_absolute_playhead_wrap_pause_resume_and_stop(self) -> None:
        result = self.run_node(
            """
const context = new FakeContext(10);
const transport = new transportModule.DecodedLoopTransport({
  audioContext: context,
  decodedBuffers: {
    source: decodedBuffer(10, [1, 1, 1, 1, 1, 1, 1, 1, 1, 1]),
  },
  loopStartSeconds: 10,
  loopEndSeconds: 11,
  scheduleLeadSeconds: 0.1,
});
transport.seek(10.7);
transport.play("source");
context.currentTime = 0.65;
const wrappedWhilePlaying = transport.playheadSeconds;
const paused = transport.pause();
const pausedNode = context.sources[0];
context.currentTime = 4;
const stillPaused = transport.playheadSeconds;
const resumed = transport.play();
const resumedNode = context.sources[1];
context.currentTime = 4.3;
const resumedPosition = transport.playheadSeconds;
const wrappedSeek = transport.seek(12.25);
const seekNode = context.sources[2];
const stopped = transport.stop();
console.log(JSON.stringify({
  wrappedWhilePlaying,
  paused,
  pausedStop: pausedNode.stops[0],
  stillPaused,
  resumed,
  resumedStart: resumedNode.starts[0],
  resumedPosition,
  wrappedSeek,
  seekStart: seekNode.starts[0],
  seekStop: seekNode.stops[0],
  stopped,
  snapshot: transport.snapshot(),
  sourceCount: context.sources.length,
}));
"""
        )

        self.assertAlmostEqual(result["wrappedWhilePlaying"], 10.25)
        self.assertAlmostEqual(result["paused"], 10.25)
        self.assertAlmostEqual(result["pausedStop"], 0.65)
        self.assertAlmostEqual(result["stillPaused"], 10.25)
        self.assertAlmostEqual(result["resumedStart"]["when"], 4.1)
        self.assertAlmostEqual(result["resumedStart"]["offset"], 0.25)
        self.assertAlmostEqual(result["resumedPosition"], 10.45)
        self.assertAlmostEqual(
            result["wrappedSeek"]["absolutePlayheadSeconds"], 10.25
        )
        self.assertAlmostEqual(result["seekStart"]["offset"], 0.25)
        self.assertAlmostEqual(result["seekStop"], 4.3)
        self.assertEqual(result["stopped"], 10)
        self.assertFalse(result["snapshot"]["playing"])
        self.assertEqual(result["snapshot"]["playheadSeconds"], 10)
        self.assertEqual(result["sourceCount"], 3)

    def test_invalid_rates_bounds_and_keys_fail_closed(self) -> None:
        result = self.run_node(
            """
const context = new FakeContext(10);
const errors = [];
for (const operation of [
  () => transportModule.frameCountForLoop(10, 2, 2),
  () => transportModule.wrapAbsolutePlayhead(1, 2, 2),
  () => new transportModule.DecodedLoopTransport({
    audioContext: context,
    decodedBuffers: {wrongRate: decodedBuffer(20, [1, 2, 3])},
    loopStartSeconds: 0,
    loopEndSeconds: 1,
  }),
]) {
  try { operation(); } catch (error) { errors.push(error.message); }
}
const valid = new transportModule.DecodedLoopTransport({
  audioContext: context,
  decodedBuffers: {source: decodedBuffer(10, [1, 2, 3])},
  loopStartSeconds: 0,
  loopEndSeconds: 0.3,
});
try { valid.play("missing"); } catch (error) { errors.push(error.message); }
console.log(JSON.stringify({errors}));
"""
        )

        self.assertEqual(len(result["errors"]), 4)
        self.assertIn("loop end must be greater", result["errors"][0])
        self.assertIn("loop end must be greater", result["errors"][1])
        self.assertIn("must match the AudioContext", result["errors"][2])
        self.assertIn("unknown decoded buffer", result["errors"][3])

    def test_group_switch_uses_one_when_and_offset_without_drift(self) -> None:
        result = self.run_node(
            """
const context = new FakeContext(10);
const transport = new transportModule.DecodedGroupLoopTransport({
  audioContext: context,
  decodedBuffers: {
    sourceA: decodedBuffer(10, [1, 1, 1, 1, 1, 1, 1, 1, 1, 1]),
    sourceB: decodedBuffer(10, [2, 2, 2, 2, 2, 2, 2, 2, 2, 2]),
    midiA: decodedBuffer(10, [3, 3, 3, 3, 3, 3, 3, 3, 3, 3]),
  },
  loopStartSeconds: 10,
  loopEndSeconds: 11,
  scheduleLeadSeconds: 0.05,
});
transport.seek(10.2);
context.currentTime = 1;
const first = transport.play(new Set(["sourceA", "sourceB"]));
context.currentTime = 1.25;
const switched = transport.switchTo(new Set(["sourceA", "midiA"]));
const firstNodes = context.sources.slice(0, 2);
const secondNodes = context.sources.slice(2, 4);
console.log(JSON.stringify({
  first,
  switched,
  firstStarts: firstNodes.map(source => source.starts[0]),
  firstStops: firstNodes.map(source => source.stops[0]),
  secondStarts: secondNodes.map(source => source.starts[0]),
  activeKeys: transport.activeKeys,
  playing: transport.playing,
  snapshot: transport.snapshot(),
  sourceSerial: transport.sourceSerial,
}));
"""
        )

        self.assertEqual(result["first"]["keys"], ["sourceA", "sourceB"])
        self.assertEqual(result["switched"]["previousKeys"], ["sourceA", "sourceB"])
        self.assertEqual(result["activeKeys"], ["sourceA", "midiA"])
        self.assertTrue(result["playing"])
        self.assertEqual(result["sourceSerial"], 4)
        self.assertTrue(
            all(
                item["when"] == result["firstStarts"][0]["when"]
                and item["offset"] == result["firstStarts"][0]["offset"]
                for item in result["firstStarts"]
            )
        )
        self.assertAlmostEqual(result["firstStarts"][0]["when"], 1.05)
        self.assertAlmostEqual(result["firstStarts"][0]["offset"], 0.2)
        self.assertTrue(
            all(
                item["when"] == result["secondStarts"][0]["when"]
                and item["offset"] == result["secondStarts"][0]["offset"]
                for item in result["secondStarts"]
            )
        )
        self.assertAlmostEqual(result["secondStarts"][0]["when"], 1.3)
        self.assertAlmostEqual(result["secondStarts"][0]["offset"], 0.45)
        self.assertEqual(result["firstStops"], [1.3, 1.3])
        self.assertEqual(result["snapshot"]["activeKeys"], ["sourceA", "midiA"])

    def test_group_validates_every_key_before_touching_active_playback(self) -> None:
        result = self.run_node(
            """
const context = new FakeContext(10);
const transport = new transportModule.DecodedGroupLoopTransport({
  audioContext: context,
  decodedBuffers: {
    source: decodedBuffer(10, [1, 1, 1, 1, 1]),
    midi: decodedBuffer(10, [2, 2, 2, 2, 2]),
  },
  loopStartSeconds: 2,
  loopEndSeconds: 2.5,
  scheduleLeadSeconds: 0.05,
});
transport.play(["source"]);
const errors = [];
for (const keys of [[], ["source", "source"], ["midi", "missing"], "source"]) {
  try { transport.switchTo(keys); } catch (error) { errors.push(error.message); }
}
const activeCopy = transport.activeKeys;
activeCopy.push("midi");
const snapshot = transport.snapshot();
snapshot.activeKeys.push("midi");
console.log(JSON.stringify({
  errors,
  sourceCount: context.sources.length,
  activeStops: context.sources[0].stops,
  activeKeys: transport.activeKeys,
  playing: transport.playing,
  snapshotAfterMutation: transport.snapshot(),
}));
"""
        )

        self.assertEqual(len(result["errors"]), 4)
        self.assertIn("at least one", result["errors"][0])
        self.assertIn("duplicated", result["errors"][1])
        self.assertIn("unknown decoded buffer", result["errors"][2])
        self.assertIn("non-empty iterable", result["errors"][3])
        self.assertEqual(result["sourceCount"], 1)
        self.assertEqual(result["activeStops"], [])
        self.assertEqual(result["activeKeys"], ["source"])
        self.assertTrue(result["playing"])
        self.assertEqual(result["snapshotAfterMutation"]["activeKeys"], ["source"])

    def test_group_start_failure_rolls_back_every_new_node_and_keeps_old_group(self) -> None:
        result = self.run_node(
            """
const context = new FakeContext(10);
const transport = new transportModule.DecodedGroupLoopTransport({
  audioContext: context,
  decodedBuffers: {
    oldA: decodedBuffer(10, [1, 1, 1, 1, 1]),
    oldB: decodedBuffer(10, [2, 2, 2, 2, 2]),
    newA: decodedBuffer(10, [3, 3, 3, 3, 3]),
    newB: decodedBuffer(10, [4, 4, 4, 4, 4]),
    newC: decodedBuffer(10, [5, 5, 5, 5, 5]),
  },
  loopStartSeconds: 5,
  loopEndSeconds: 5.5,
  scheduleLeadSeconds: 0.1,
});
transport.play(["oldA", "oldB"]);
context.currentTime = 0.2;
const before = transport.snapshot();
context.failStartIds.add(4);
let error = null;
try {
  transport.switchTo(["newA", "newB", "newC"]);
} catch (caught) {
  error = caught.message;
}
const oldNodes = context.sources.slice(0, 2);
const failedNodes = context.sources.slice(2);
console.log(JSON.stringify({
  error,
  before,
  after: transport.snapshot(),
  oldStops: oldNodes.map(source => source.stops),
  oldDisconnects: oldNodes.map(source => source.disconnectCount),
  failedStarts: failedNodes.map(source => source.starts),
  failedStops: failedNodes.map(source => source.stops),
  failedDisconnects: failedNodes.map(source => source.disconnectCount),
}));
"""
        )

        self.assertIn("start failed for source 4", result["error"])
        self.assertEqual(result["after"]["activeKeys"], ["oldA", "oldB"])
        self.assertTrue(result["after"]["playing"])
        self.assertEqual(result["oldStops"], [[], []])
        self.assertEqual(result["oldDisconnects"], [0, 0])
        self.assertEqual(len(result["failedStarts"][0]), 1)
        self.assertEqual(result["failedStarts"][1], [])
        self.assertEqual(result["failedStarts"][2], [])
        self.assertTrue(
            all(
                len(stops) == 1 and abs(stops[0] - 0.3) < 1e-9
                for stops in result["failedStops"]
            )
        )
        self.assertEqual(result["failedDisconnects"], [1, 1, 1])
        self.assertEqual(result["before"]["groupSerial"], result["after"]["groupSerial"])

    def test_group_seek_pause_resume_and_stop_preserve_one_clock(self) -> None:
        result = self.run_node(
            """
const context = new FakeContext(10);
const transport = new transportModule.DecodedGroupLoopTransport({
  audioContext: context,
  decodedBuffers: {
    one: decodedBuffer(10, [1, 1, 1, 1, 1, 1, 1, 1, 1, 1]),
    two: decodedBuffer(10, [2, 2, 2, 2, 2, 2, 2, 2, 2, 2]),
  },
  loopStartSeconds: 10,
  loopEndSeconds: 11,
  scheduleLeadSeconds: 0.1,
});
transport.seek(10.7);
transport.play(["one", "two"]);
context.currentTime = 0.65;
const wrappedWhilePlaying = transport.playheadSeconds;
const paused = transport.pause();
const pausedNodes = context.sources.slice(0, 2);
context.currentTime = 4;
const stillPaused = transport.playheadSeconds;
const resumed = transport.play();
const resumedNodes = context.sources.slice(2, 4);
context.currentTime = 4.3;
const resumedPosition = transport.playheadSeconds;
const sought = transport.seek(12.25);
const seekNodes = context.sources.slice(4, 6);
const stopped = transport.stop();
console.log(JSON.stringify({
  wrappedWhilePlaying,
  paused,
  pausedStops: pausedNodes.map(source => source.stops[0]),
  stillPaused,
  resumed,
  resumedStarts: resumedNodes.map(source => source.starts[0]),
  resumedStops: resumedNodes.map(source => source.stops[0]),
  resumedPosition,
  sought,
  seekStarts: seekNodes.map(source => source.starts[0]),
  seekStops: seekNodes.map(source => source.stops[0]),
  stopped,
  snapshot: transport.snapshot(),
  sourceCount: context.sources.length,
}));
"""
        )

        self.assertAlmostEqual(result["wrappedWhilePlaying"], 10.25)
        self.assertAlmostEqual(result["paused"], 10.25)
        self.assertEqual(result["pausedStops"], [0.65, 0.65])
        self.assertAlmostEqual(result["stillPaused"], 10.25)
        self.assertEqual(result["resumed"]["keys"], ["one", "two"])
        self.assertTrue(
            all(start == {"when": 4.1, "offset": 0.25} for start in result["resumedStarts"])
        )
        self.assertAlmostEqual(result["resumedPosition"], 10.45)
        self.assertAlmostEqual(result["sought"]["absolutePlayheadSeconds"], 10.25)
        self.assertTrue(
            all(abs(stopped_at - 4.4) < 1e-9 for stopped_at in result["resumedStops"])
        )
        self.assertTrue(
            all(
                abs(start["when"] - 4.4) < 1e-9
                and abs(start["offset"] - 0.25) < 1e-9
                for start in result["seekStarts"]
            )
        )
        self.assertEqual(result["seekStops"], [4.3, 4.3])
        self.assertEqual(result["stopped"], 10)
        self.assertFalse(result["snapshot"]["playing"])
        self.assertEqual(result["snapshot"]["activeKeys"], ["one", "two"])
        self.assertEqual(result["snapshot"]["playheadSeconds"], 10)
        self.assertEqual(result["sourceCount"], 6)

    def test_module_has_no_network_persistence_or_feedback_surface(self) -> None:
        source = TRANSPORT_PATH.read_text(encoding="utf-8")

        for forbidden in (
            "fetch(",
            "XMLHttpRequest",
            "WebSocket",
            "localStorage",
            "sessionStorage",
            "indexedDB",
            "sendBeacon",
            "/api/events",
            "candidate_decision",
        ):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("document.", source)

    def test_browser_global_is_published_even_with_commonjs_shim(self) -> None:
        script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({json.dumps(str(TRANSPORT_PATH))}, "utf8");
const page = {{module: {{exports: {{}}}}}};
page.globalThis = page;
vm.runInNewContext(source, page);
console.log(JSON.stringify({{
  commonjs: typeof page.module.exports.DecodedLoopTransport,
  browser: typeof page.SunofriendWorkbenchTransport.DecodedLoopTransport,
  groupCommonjs: typeof page.module.exports.DecodedGroupLoopTransport,
  groupBrowser: typeof page.SunofriendWorkbenchTransport.DecodedGroupLoopTransport,
  same: page.module.exports === page.SunofriendWorkbenchTransport,
}}));
"""
        result = subprocess.run(
            [self.node, "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["commonjs"], "function")
        self.assertEqual(payload["browser"], "function")
        self.assertEqual(payload["groupCommonjs"], "function")
        self.assertEqual(payload["groupBrowser"], "function")
        self.assertTrue(payload["same"])


if __name__ == "__main__":
    unittest.main()
