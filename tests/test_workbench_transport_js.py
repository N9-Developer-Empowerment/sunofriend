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
  constructor(id) {{
    this.id = id;
    this.starts = [];
    this.stops = [];
    this.connections = [];
    this.disconnectCount = 0;
    this.onended = null;
  }}
  connect(destination) {{ this.connections.push(destination); }}
  disconnect() {{ this.disconnectCount += 1; }}
  start(when, offset) {{ this.starts.push({{when, offset}}); }}
  stop(when) {{ this.stops.push(when); }}
}}

class FakeContext {{
  constructor(sampleRate = 10) {{
    this.sampleRate = sampleRate;
    this.currentTime = 0;
    this.destination = {{name: "destination"}};
    this.sources = [];
  }}
  createBuffer(numberOfChannels, length, sampleRate) {{
    return new FakeBuffer(numberOfChannels, length, sampleRate);
  }}
  createBufferSource() {{
    const source = new FakeSource(this.sources.length + 1);
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
        self.assertTrue(payload["same"])


if __name__ == "__main__":
    unittest.main()
