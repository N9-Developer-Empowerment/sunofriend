from __future__ import annotations

import json
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
        cls.decoded_arrangement = cls.page.split(
            "const decodedArrangementPresetLabels", 1
        )[1].split("function toggleDecodedExtra", 1)[0]

    def run_ui_node(self, body: str) -> dict[str, object]:
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is not installed")
        harness = r"""
const fs = require("fs");
const vm = require("vm");
const html = fs.readFileSync("src/sunofriend/workbench.html", "utf8");
let source = html.split("<script>", 2)[1].split("</script>", 1)[0];
source = source.split("document.querySelector('#project-nav').onclick", 1)[0];
const status = {
  textContent: "",
  classList: {
    values: new Set(),
    add(...names) { for (const name of names) this.values.add(name); },
    remove(...names) { for (const name of names) this.values.delete(name); },
    toggle(name, force) {
      if (force === undefined ? !this.values.has(name) : force) this.values.add(name);
      else this.values.delete(name);
    },
  },
};
const document = {
  querySelector(selector) {
    return selector === "#decoded-arrangement-status" ? status : null;
  },
  querySelectorAll() { return []; },
};
let frame = 0;
const context = {
  AbortController,
  AbortSignal,
  Blob,
  URL,
  URLSearchParams,
  console,
  document,
  fetch,
  location: {search: ""},
  requestAnimationFrame() { frame += 1; return frame; },
  cancelAnimationFrame() {},
  window: {SunofriendWorkbenchTransport: {}},
  __status: status,
};
vm.createContext(context);
vm.runInContext(source, context);
const body = BODY_SOURCE;
Promise.resolve(vm.runInContext(`(async()=>{${body}})()`, context)).then(
  result => console.log(JSON.stringify(result)),
  error => { console.error(error.stack || error); process.exitCode = 1; }
);
""".replace("BODY_SOURCE", json.dumps(body))
        completed = subprocess.run(
            [node, "-e", harness],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

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

    def test_precise_arrangement_uses_only_server_owned_canonical_groups(self) -> None:
        self.assertIn("Precise short arrangement loop", self.page)
        self.assertIn("One decoded audio clock", self.page)
        self.assertIn("/api/decoded-arrangement-loop", self.decoded_arrangement)
        self.assertIn("selection_manifest_sha256:manifestSha", self.decoded_arrangement)
        self.assertNotIn("candidate_ids", self.decoded_arrangement)
        self.assertNotIn("track_ids", self.decoded_arrangement)
        self.assertNotIn("gain:", self.decoded_arrangement)
        for preset in ("source-only", "selected-midi", "hybrid", "main-only"):
            self.assertIn(f"'{preset}'", self.decoded_arrangement)
        self.assertIn(
            "new window.SunofriendWorkbenchTransport.DecodedGroupLoopTransport",
            self.decoded_arrangement,
        )
        self.assertIn("transport.switchTo(group)", self.decoded_arrangement)
        self.assertIn("transport.play(group)", self.decoded_arrangement)

    def test_precise_arrangement_discloses_scope_and_keeps_coarse_custom_fallback(self) -> None:
        self.assertIn("every track starts at recorded zero", self.page)
        self.assertIn("No source/MIDI offset or downbeat is inferred", self.page)
        self.assertIn("fixed unity gain and are not level-matched", self.page)
        self.assertIn("a dense hybrid can clip", self.page)
        self.assertIn("not a blind or loudness-matched preference test", self.page)
        self.assertIn("full-song mixer below remains the coarse compatibility/custom path", self.page)
        self.assertIn("Coarse full-song/custom mixer", self.page)
        self.assertIn("Play coarse full-song mix", self.page)
        self.assertIn("second-synchronised, not sample-accurate", self.page)
        self.assertIn('role="group" aria-label="Precise decoded arrangement presets"', self.page)
        self.assertIn("silence_padded_frames", self.decoded_arrangement)
        self.assertIn("Do not judge that silence as a missing transcription", self.decoded_arrangement)

    def test_precise_arrangement_is_feedback_free_cancelled_and_stale_guarded(self) -> None:
        self.assertNotIn("/api/events", self.decoded_arrangement)
        self.assertNotIn("candidate_decision", self.decoded_arrangement)
        self.assertNotIn("garageband-pack", self.decoded_arrangement)
        self.assertNotIn("save(", self.decoded_arrangement)
        self.assertIn("AbortController", self.decoded_arrangement)
        self.assertIn("decodedArrangementAbortController?.abort()", self.decoded_arrangement)
        self.assertIn("decodedArrangementIsCurrent(requestId,manifestSha)", self.decoded_arrangement)
        self.assertGreaterEqual(
            self.decoded_arrangement.count(
                "if(!decodedArrangementIsCurrent(requestId,manifestSha))return"
            ),
            3,
        )
        self.assertIn("clearDecodedArrangement();", self.page.split("function stopAudio", 1)[1].split("function stopFallbackAudio", 1)[0])
        self.assertIn("nothing was saved", self.decoded_arrangement.lower())

    def test_failed_precise_preset_switch_keeps_previous_group_playing(self) -> None:
        result = self.run_ui_node(
            """
view='arrangement';
project={stems:[],state:{stems:{}}};
decodedArrangementLoop={groups:{hybrid:['new-a','new-b']}};
let stopCount=0,apiCalls=0;
const transport={
  playing:true,
  activeKeys:['old-a','old-b'],
  loopStartSeconds:0,
  loopEndSeconds:1,
  switchTo(){throw new Error('replacement start failed')},
  play(){throw new Error('unexpected play')},
  stop(){stopCount+=1;return 0},
};
decodedArrangementTransport=transport;
decodedAudioContext={resume:()=>Promise.resolve(),currentTime:0};
api=async()=>{apiCalls+=1;return {}};
playhead=.25;
await playDecodedArrangementPreset('hybrid');
return {
  sameTransport:decodedArrangementTransport===transport,
  sameLoop:decodedArrangementLoop.groups.hybrid.length===2,
  playing:transport.playing,
  activeKeys:transport.activeKeys,
  stopCount,
  apiCalls,
  status:__status.textContent,
};
"""
        )

        self.assertTrue(result["sameTransport"])
        self.assertTrue(result["sameLoop"])
        self.assertTrue(result["playing"])
        self.assertEqual(result["activeKeys"], ["old-a", "old-b"])
        self.assertEqual(result["stopCount"], 0)
        self.assertEqual(result["apiCalls"], 0)
        self.assertIn("previous preset keeps playing", result["status"])
        self.assertIn("Nothing was saved", result["status"])

    def test_pending_precise_play_cannot_override_a_later_pause(self) -> None:
        result = self.run_ui_node(
            """
view='arrangement';
project={stems:[],state:{stems:{}}};
decodedArrangementLoop={groups:{hybrid:['next']}};
let releaseResume,playCount=0,switchCount=0,pauseCount=0;
const waiting=new Promise(resolve=>{releaseResume=resolve});
const transport={
  playing:false,
  activeKeys:['old'],
  loopStartSeconds:0,
  loopEndSeconds:1,
  seek(){},
  switchTo(){switchCount+=1},
  play(){playCount+=1},
  pause(){pauseCount+=1;this.playing=false;return .4},
};
decodedArrangementTransport=transport;
decodedAudioContext={resume:()=>waiting,currentTime:0};
playhead=.4;
const pending=playDecodedArrangementPreset('hybrid');
pauseDecodedArrangement(false);
releaseResume();
await pending;
return {playCount,switchCount,pauseCount,playing:transport.playing};
"""
        )

        self.assertEqual(result["playCount"], 0)
        self.assertEqual(result["switchCount"], 0)
        self.assertEqual(result["pauseCount"], 1)
        self.assertFalse(result["playing"])

    def test_precise_prepare_passes_and_invalidates_the_abort_signal(self) -> None:
        result = self.run_ui_node(
            """
view='arrangement';
project={decoded_arrangement_selection:{selection_manifest_sha256:'a'.repeat(64)}};
selectedRows=()=>[{candidate:{},stem:{}}];
arrangementTracks=()=>[{kind:'midi',url:'ready'}];
loopBounds=()=>({start:0,end:1});
stopOrdinaryAudioForDecoded=()=>{};
let captured=null;
api=(path,options)=>new Promise((resolve,reject)=>{
  captured={path,options};
  options.signal.addEventListener('abort',()=>{
    const error=new Error('cancelled');error.name='AbortError';reject(error);
  },{once:true});
});
const button={disabled:false,textContent:'Prepare'};
const pending=prepareDecodedArrangement(button);
await Promise.resolve();
const signal=captured.options.signal;
clearDecodedArrangement();
await pending;
return {
  path:captured.path,
  signalWasPassed:signal instanceof AbortSignal,
  aborted:signal.aborted,
  transportCleared:decodedArrangementTransport===null,
};
"""
        )

        self.assertEqual(result["path"], "/api/decoded-arrangement-loop")
        self.assertTrue(result["signalWasPassed"])
        self.assertTrue(result["aborted"])
        self.assertTrue(result["transportCleared"])

    def test_ordinary_audio_takeover_pauses_and_announces_precise_transport(self) -> None:
        result = self.run_ui_node(
            """
view='arrangement';
project={stems:[],state:{stems:{}}};
let pauses=0;
decodedArrangementTransport={
  playing:true,
  activeKeys:['source'],
  pause(){pauses+=1;this.playing=false;return .3},
};
const audio={
  id:'proxy',currentTime:0,
  addEventListener(){},pause(){},
};
bindSharedAudio(audio);
audio.onplay();
return {pauses,playing:decodedArrangementTransport.playing,status:__status.textContent};
"""
        )

        self.assertEqual(result["pauses"], 1)
        self.assertFalse(result["playing"])
        self.assertIn("paused because another audio player took control", result["status"])

    def test_padding_labels_disambiguate_duplicate_roles(self) -> None:
        result = self.run_ui_node(
            """
project={stems:[
  {stem_id:'keys-a',candidates:[{candidate_id:'one',label:'Tracker one'}]},
  {stem_id:'keys-b',candidates:[{candidate_id:'two',label:'Tracker two'}]},
]};
return {
  firstSource:decodedArrangementTrackLabel({kind:'source',roles:['keys'],labels:['Bright keys stem'],stem_ids:['keys-a']}),
  secondSource:decodedArrangementTrackLabel({kind:'source',roles:['keys'],labels:['Dark keys stem'],stem_ids:['keys-b']}),
  firstMidi:decodedArrangementTrackLabel({kind:'selected_midi',role:'keys',decision:'optional',stem_id:'keys-a',candidate_id:'one'}),
  secondMidi:decodedArrangementTrackLabel({kind:'selected_midi',role:'keys',decision:'optional',stem_id:'keys-b',candidate_id:'two'}),
};
"""
        )

        self.assertNotEqual(result["firstSource"], result["secondSource"])
        self.assertNotEqual(result["firstMidi"], result["secondMidi"])
        self.assertIn("Bright keys stem", result["firstSource"])
        self.assertIn("Tracker one", result["firstMidi"])

    def test_generated_silence_warning_is_announced(self) -> None:
        self.assertIn(
            'id="decoded-arrangement-padding" class="notice" role="status" '
            'aria-live="polite" hidden',
            self.page,
        )

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
