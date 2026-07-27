from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


class WorkbenchBalancedArrangementUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.page = Path("src/sunofriend/workbench.html").read_text(encoding="utf-8")
        cls.arrangement = cls.page.split("function renderArrangement()", 1)[1].split(
            "function packItems", 1
        )[0]
        cls.balanced_action = cls.arrangement.split(
            "const balancedButton=", 1
        )[1].split("document.querySelectorAll('[data-mix-decision]')", 1)[0]
        cls.dry_action = cls.arrangement.split(
            "const button=", 1
        )[1].split("const balancedButton=", 1)[0]

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
const document = {
  querySelector() { return null; },
  querySelectorAll() { return []; },
};
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
  requestAnimationFrame() { return 1; },
  cancelAnimationFrame() {},
  window: {SunofriendWorkbenchTransport: {}},
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

    def test_balanced_audition_is_explicit_and_separate_from_dry_control(self) -> None:
        self.assertIn("Prepared dry control mix", self.arrangement)
        self.assertIn("unity-gain GM proxy", self.arrangement)
        self.assertIn(
            "Balanced MIDI-derived song interpretation",
            self.arrangement,
        )
        self.assertIn("Create song-interpretation WAV", self.arrangement)
        self.assertIn("not mixed into the WAV", self.arrangement)
        self.assertIn("not mastered", self.arrangement)
        self.assertIn('id="arrangement-audio"', self.arrangement)
        self.assertIn('id="balanced-arrangement-audio"', self.arrangement)
        self.assertIn("Download exact balance receipt", self.arrangement)
        self.assertIn(
            "project.arrangement=response.arrangement",
            self.arrangement,
        )
        self.assertIn(
            "project.balanced_arrangement=response.balanced_arrangement",
            self.arrangement,
        )
        self.assertIn(
            "for(const id of ['#arrangement-audio','#balanced-arrangement-audio'])",
            self.arrangement,
        )
        self.assertEqual(
            self.arrangement.count('data-playback-mode="prepared-mix"'),
            2,
        )
        self.assertIn(
            'aria-label="Prepared dry selected-MIDI control mix"',
            self.arrangement,
        )
        self.assertIn(
            'aria-label="Balanced MIDI-derived song interpretation"',
            self.arrangement,
        )
        self.assertEqual(self.page.count("/api/balanced-arrangement"), 1)

    def test_stale_render_responses_cannot_patch_a_replaced_arrangement_view(
        self,
    ) -> None:
        for action, counter, button in (
            (self.dry_action, "preparedArrangementRequest", "button"),
            (
                self.balanced_action,
                "balancedArrangementRequest",
                "balancedButton",
            ),
        ):
            self.assertIn(f"const requestId=++{counter}", action)
            self.assertIn(f"requestId!=={counter}", action)
            self.assertIn("view!=='arrangement'", action)
            self.assertIn(f"!{button}.isConnected", action)
            self.assertGreaterEqual(action.count(f"requestId!=={counter}"), 2)

    def test_older_dry_response_cannot_replace_a_newer_project_result(self) -> None:
        result = self.run_ui_node(
            """
setupText=()=>''; workbenchIdentity=()=>''; arrangementExplorerPanel=()=>'';
overlapNotice=()=>''; wireArrangementExplorer=()=>{}; wireArrangementPlayer=()=>{};
stateFor=()=>({candidates:{}}); candidateLetter=()=>'A';
needsOverlapConfirmation=()=>false;
selectedRows=()=>[{
  stem:{stem_id:'stem-1',role:'keys'},
  candidate:{candidate_id:'candidate-1'},
  decision:'main',
}];
const main={innerHTML:''},buttons=[],holders=[];
let generation=0;
function addGeneration(){
  buttons.push({
    dry:{disabled:false,textContent:'',isConnected:true},
    balanced:{disabled:false,textContent:'',isConnected:true},
  });
  holders.push({
    dry:{innerHTML:''},
    balanced:{innerHTML:''},
  });
}
addGeneration();
document.querySelector=selector=>{
  if(selector==='#main')return main;
  if(selector==='#render-arrangement')return buttons[generation].dry;
  if(selector==='#render-balanced-arrangement')return buttons[generation].balanced;
  if(selector==='#arrangement-result')return holders[generation].dry;
  if(selector==='#balanced-arrangement-result')return holders[generation].balanced;
  return null;
};
document.querySelectorAll=()=>[];
const errors=[],requests=[];
showError=error=>errors.push(String(error?.message||error));
api=path=>new Promise((resolve,reject)=>requests.push({path,resolve,reject}));
project={
  decoded_arrangement_selection:{selection_manifest_sha256:'a'.repeat(64)},
  arrangement:null,
  balanced_arrangement:null,
};
view='arrangement';
renderArrangement();
const firstButton=buttons[0].dry,firstRequest=firstButton.onclick();
firstButton.isConnected=false;
buttons[0].balanced.isConnected=false;
generation=1;
addGeneration();
renderArrangement();
const secondRequest=buttons[1].dry.onclick();
requests[1].resolve({
  arrangement:{cache_key:'new',preview_url:'/new.wav',midi_url:'/new.mid'},
});
await secondRequest;
requests[0].resolve({
  arrangement:{cache_key:'old',preview_url:'/old.wav',midi_url:'/old.mid'},
});
await firstRequest;
return {
  projectCacheKey:project.arrangement?.cache_key,
  visibleHasNew:holders[1].dry.innerHTML.includes('/new.wav'),
  visibleHasOld:holders[1].dry.innerHTML.includes('/old.wav'),
  errors,
};
"""
        )

        self.assertEqual(result["projectCacheKey"], "new")
        self.assertTrue(result["visibleHasNew"])
        self.assertFalse(result["visibleHasOld"])
        self.assertEqual(result["errors"], [])

    def test_dry_response_is_ignored_after_selection_hash_changes(self) -> None:
        result = self.run_ui_node(
            """
setupText=()=>''; workbenchIdentity=()=>''; arrangementExplorerPanel=()=>'';
overlapNotice=()=>''; wireArrangementExplorer=()=>{}; wireArrangementPlayer=()=>{};
stateFor=()=>({candidates:{}}); candidateLetter=()=>'A';
needsOverlapConfirmation=()=>false;
selectedRows=()=>[{
  stem:{stem_id:'stem-1',role:'keys'},
  candidate:{candidate_id:'candidate-1'},
  decision:'main',
}];
const main={innerHTML:''};
const dryButton={disabled:false,textContent:'',isConnected:true};
const balancedButton={disabled:false,textContent:'',isConnected:true};
const dryHolder={innerHTML:'current selection'};
const balancedHolder={innerHTML:''};
document.querySelector=selector=>({
  '#main':main,
  '#render-arrangement':dryButton,
  '#render-balanced-arrangement':balancedButton,
  '#arrangement-result':dryHolder,
  '#balanced-arrangement-result':balancedHolder,
}[selector]||null);
document.querySelectorAll=()=>[];
const errors=[],requests=[];
showError=error=>errors.push(String(error?.message||error));
api=path=>new Promise((resolve,reject)=>requests.push({path,resolve,reject}));
project={
  decoded_arrangement_selection:{selection_manifest_sha256:'a'.repeat(64)},
  arrangement:{cache_key:'current'},
  balanced_arrangement:null,
};
view='arrangement';
renderArrangement();
const pending=dryButton.onclick();
project.decoded_arrangement_selection.selection_manifest_sha256='b'.repeat(64);
requests[0].resolve({
  arrangement:{cache_key:'stale',preview_url:'/stale.wav',midi_url:'/stale.mid'},
});
await pending;
return {
  projectCacheKey:project.arrangement?.cache_key,
  holder:dryHolder.innerHTML,
  errors,
};
"""
        )

        self.assertEqual(result["projectCacheKey"], "current")
        self.assertEqual(result["holder"], "current selection")
        self.assertEqual(result["errors"], [])

    def test_balanced_button_sends_only_selection_hash_and_records_no_feedback(
        self,
    ) -> None:
        self.assertIn(
            "balancedButton.onclick=async()=>",
            self.balanced_action,
        )
        self.assertIn(
            "api('/api/balanced-arrangement'",
            self.balanced_action,
        )
        self.assertIn(
            "JSON.stringify({selection_manifest_sha256:manifestSha})",
            self.balanced_action,
        )
        self.assertIn(
            "project?.decoded_arrangement_selection?.selection_manifest_sha256"
            "!==manifestSha",
            self.balanced_action,
        )
        self.assertNotIn("/api/events", self.balanced_action)
        self.assertNotIn("save(", self.balanced_action)
        self.assertNotIn("candidate_decision", self.balanced_action)
        self.assertNotIn("project.arrangement=", self.balanced_action)

    def test_balance_receipt_maps_each_fader_and_explains_horizon_and_guard(
        self,
    ) -> None:
        result = self.run_ui_node(
            """
const member='MIDI/01-keys-main.mid';
const html=balancedArrangementPlayer({
  cache_hit:false,
  preview_url:'/balanced.wav',
  report_url:'/receipt.json',
  recipe_url:'/recipe.md',
  render_horizon:{
    output_frames:16000,
    excluded_neutral_preview_tail_frames:1600,
    padded_output_frames:0,
    lanes:[{
      selection_index:1,
      garageband_pack_archive_member:member,
      preview_frames:17600,
      excluded_neutral_preview_tail_frames:1600,
      padded_output_frames:0,
    }],
  },
  mix_report:{
    sample_rate:16000,
    lanes:[{
      selection_index:1,
      garageband_pack_archive_member:member,
      role:'keys',
      decision:'main',
      garageband_track_trim_db:-3.25,
      fallback_reason:null,
      source_match_clamped:false,
    }],
    drum_bus:{
      target_applicable:true,
      target_met:false,
      guard_clamped:true,
      guard_gain_db:-18,
      required_guard_gain_db:-22,
    },
    limits:{
      audition_target_gated_rms_dbfs:-18,
      maximum_normalisation_boost_db:12,
      sample_peak_ceiling_dbfs:-1,
    },
    output:{
      master_output_gain_db:1.5,
      normalisation_target_met:true,
      post_master_target_error_db:0.02,
      normalisation_limit:null,
    },
  },
});
return {html};
"""
        )

        html = str(result["html"])
        self.assertIn("#1", html)
        self.assertIn("MIDI/01-keys-main.mid", html)
        self.assertIn("0.100 s neutral-render tail excluded", html)
        self.assertIn("fixed to the longest verified source stem", html)
        self.assertIn("Drum guard target not fully met", html)
        self.assertIn("clamped at -18.00 dB", html)
        self.assertIn("Audition normalisation target met", html)
        self.assertIn("post-output target error +0.02 dB", html)
        self.assertIn("limiting factor none recorded", html)

    def test_drum_guard_met_is_visibly_distinct(self) -> None:
        result = self.run_ui_node(
            """
return {
  met:balancedDrumGuardNotice({
    target_applicable:true,
    target_met:true,
    guard_clamped:false,
    guard_gain_db:-5,
    required_guard_gain_db:-5,
  }),
  unavailable:balancedDrumGuardNotice({
    target_applicable:false,
  }),
};
"""
        )

        self.assertIn("Drum guard target met", str(result["met"]))
        self.assertIn("not applicable", str(result["unavailable"]))

    def test_disjoint_audible_buses_explain_why_guard_is_inapplicable(
        self,
    ) -> None:
        result = self.run_ui_node(
            """
return {
  notice:balancedDrumGuardNotice({
    target_applicable:false,
    target_met:null,
    before_guard:{gated_rms_dbfs:-20},
    non_drum_reference:{gated_rms_dbfs:-22},
    before_guard_overlap:{overlap_block_count:0},
    guard_gain_db:0,
    required_guard_gain_db:0,
  }),
};
"""
        )

        notice = str(result["notice"])
        self.assertIn("no qualifying time-aligned 400 ms window", notice)
        self.assertIn("audible only at different times", notice)
        self.assertNotIn(
            "because both an audible drum bus and non-drum bus were not present",
            notice,
        )

    def test_output_normalisation_reports_met_and_both_limiting_failures(
        self,
    ) -> None:
        result = self.run_ui_node(
            """
const limits={
  audition_target_gated_rms_dbfs:-18,
  maximum_normalisation_boost_db:12,
  sample_peak_ceiling_dbfs:-1,
};
return {
  met:balancedOutputNormalisationNotice({
    normalisation_target_met:true,
    post_master_target_error_db:-0.04,
    normalisation_limit:null,
  },limits),
  boost:balancedOutputNormalisationNotice({
    normalisation_target_met:false,
    post_master_target_error_db:-4.5,
    normalisation_limit:'maximum_positive_boost',
  },limits),
  peak:balancedOutputNormalisationNotice({
    normalisation_target_met:false,
    post_master_target_error_db:-2.25,
    normalisation_limit:'sample_peak_ceiling',
  },limits),
};
"""
        )

        met = str(result["met"])
        boost = str(result["boost"])
        peak = str(result["peak"])
        self.assertIn("Audition normalisation target met", met)
        self.assertIn("post-output target error -0.04 dB", met)
        self.assertIn("limiting factor none recorded", met)
        self.assertIn("Audition normalisation target not met", boost)
        self.assertIn("maximum +12.00 dB boost prevented", boost)
        self.assertIn("post-output target error -4.50 dB", boost)
        self.assertIn(
            "limiting factor maximum +12.00 dB boost",
            boost,
        )
        self.assertIn("Audition normalisation target not met", peak)
        self.assertIn("-1.00 dBFS sample-peak ceiling prevented", peak)
        self.assertIn("post-output target error -2.25 dB", peak)
        self.assertIn(
            "limiting factor -1.00 dBFS sample-peak ceiling",
            peak,
        )

    def test_repeated_shared_audio_wiring_does_not_accumulate_listeners(
        self,
    ) -> None:
        result = self.run_ui_node(
            """
const listeners=[];
const audio={
  id:'balanced-arrangement-audio',
  currentTime:0,
  addEventListener(type,listener,options){
    listeners.push({type,listener,once:!!options?.once});
  },
};
bindSharedAudio(audio);
const firstPlay=audio.onplay,firstTimeUpdate=audio.ontimeupdate,firstEnded=audio.onended;
bindSharedAudio(audio);
return {
  listenerTypes:listeners.map(item=>item.type),
  pointerOnce:listeners.find(item=>item.type==='pointerdown')?.once,
  samePlay:firstPlay===audio.onplay,
  sameTimeUpdate:firstTimeUpdate===audio.ontimeupdate,
  sameEnded:firstEnded===audio.onended,
};
"""
        )

        self.assertEqual(result["listenerTypes"], ["pointerdown", "keydown"])
        self.assertTrue(result["pointerOnce"])
        self.assertTrue(result["samePlay"])
        self.assertTrue(result["sameTimeUpdate"])
        self.assertTrue(result["sameEnded"])

    def test_prepared_players_are_not_described_as_compatibility_fallbacks(
        self,
    ) -> None:
        result = self.run_ui_node(
            """
const messages=[];
setDecodedStatus=(message,kind)=>messages.push({message,kind});
function audio(dataset){
  return {
    dataset,
    currentTime:0,
    addEventListener(){},
  };
}
const prepared=audio({
  playbackMode:'prepared-mix',
  playbackLabel:'the balanced master-protected selected-MIDI audition',
});
bindSharedAudio(prepared);
prepared.onplay();
const fallback=audio({playbackLabel:'candidate A'});
bindSharedAudio(fallback);
fallback.onplay();
return {messages};
"""
        )

        self.assertIn(
            "from one prepared local WAV",
            result["messages"][0]["message"],
        )
        self.assertNotIn(
            "compatibility fallback",
            result["messages"][0]["message"],
        )
        self.assertIn(
            "time-synchronised compatibility fallback",
            result["messages"][1]["message"],
        )


if __name__ == "__main__":
    unittest.main()
