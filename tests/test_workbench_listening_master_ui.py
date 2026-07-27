from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


class WorkbenchListeningMasterUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.page = Path("src/sunofriend/workbench.html").read_text(encoding="utf-8")
        cls.arrangement = cls.page.split("function renderArrangement()", 1)[1].split(
            "function packItems", 1
        )[0]
        cls.master_action = cls.arrangement.split(
            "const listeningMasterButton=", 1
        )[1].split("document.querySelectorAll('[data-mix-decision]')", 1)[0]
        cls.master_renderer = cls.arrangement.split(
            "function listeningMasterPlayer", 1
        )[1].split("function refreshListeningMasterPanel", 1)[0]

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

    def test_master_button_requires_an_exact_current_balanced_control(self) -> None:
        result = self.run_ui_node(
            """
setupText=()=>''; workbenchIdentity=()=>''; arrangementExplorerPanel=()=>'';
overlapNotice=()=>''; wireArrangementExplorer=()=>{}; wireArrangementPlayer=()=>{};
stateFor=()=>({candidates:{}}); candidateLetter=()=>'A';
needsOverlapConfirmation=()=>false; selectedRows=()=>[];
const main={innerHTML:''};
const dryButton={disabled:true,isConnected:true};
const balancedButton={disabled:true,isConnected:true};
const masterButton={disabled:true,isConnected:true};
document.querySelector=selector=>({
  '#main':main,
  '#render-arrangement':dryButton,
  '#render-balanced-arrangement':balancedButton,
  '#render-listening-master':masterButton,
}[selector]||null);
document.querySelectorAll=()=>[];
const selection='a'.repeat(64);
function renderedMasterButton(){
  return main.innerHTML.match(/<button id="render-listening-master"[^>]*>/)?.[0]||'';
}
project={
  decoded_arrangement_selection:{selection_manifest_sha256:selection},
  arrangement:null,
  balanced_arrangement:null,
  listening_master:null,
};
view='arrangement';
renderArrangement();
const withoutControl=renderedMasterButton();
project.balanced_arrangement={
  selection_manifest_sha256:selection,
  manifest_sha256:'b'.repeat(64),
};
renderArrangement();
const withCurrentControl=renderedMasterButton();
project.balanced_arrangement.selection_manifest_sha256='c'.repeat(64);
renderArrangement();
const withStaleControl=renderedMasterButton();
return {withoutControl,withCurrentControl,withStaleControl};
"""
        )

        self.assertIn(" disabled", result["withoutControl"])
        self.assertNotIn(" disabled", result["withCurrentControl"])
        self.assertIn(" disabled", result["withStaleControl"])

    def test_control_and_challenger_have_separate_players_and_downloads(self) -> None:
        result = self.run_ui_node(
            """
const control=balancedArrangementPlayer({
  cache_hit:false,
  preview_url:'/gain-only-control.wav',
  report_url:'/gain-only-receipt.json',
  recipe_url:'/gain-only-recipe.md',
  render_horizon:{output_frames:48000,lanes:[]},
  mix_report:{sample_rate:48000,lanes:[]},
});
const challenger=listeningMasterPlayer({
  manifest_sha256:'m'.repeat(64),
  selection_manifest_sha256:'s'.repeat(64),
  balanced_arrangement_manifest_sha256:'b'.repeat(64),
  master_url:'/listening-master.wav',
  receipt_url:'/listening-master-receipt.json',
  summary:{
    input_integrated_lufs:-20.125,
    output_integrated_lufs:-16.02,
    output_true_peak_dbtp:-1.04,
  },
  mastered:true,
  release_master:false,
  cache_hit:false,
});
return {control,challenger};
"""
        )

        control = str(result["control"])
        challenger = str(result["challenger"])
        self.assertIn('id="balanced-arrangement-audio"', control)
        self.assertIn("/gain-only-control.wav", control)
        self.assertIn("Download exact balance receipt", control)
        self.assertNotIn("listening-master-audio", control)
        self.assertIn('id="listening-master-audio"', challenger)
        self.assertIn("/listening-master.wav", challenger)
        self.assertIn("Download Listening Master WAV", challenger)
        self.assertIn("Download Listening Master receipt", challenger)
        self.assertNotIn("balanced-arrangement-audio", challenger)
        self.assertIn("mastered: true", challenger)
        self.assertIn("release_master: false", challenger)
        self.assertIn("-20.13 LUFS integrated", challenger)
        self.assertIn("-16.02 LUFS integrated", challenger)
        self.assertIn("-1.04 dBTP", challenger)
        self.assertIn("unchanged gain-only control", challenger)

    def test_master_post_sends_only_both_current_identities_and_patches_outputs(
        self,
    ) -> None:
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
const masterButton={disabled:false,textContent:'',isConnected:true};
const masterHolder={innerHTML:''};
document.querySelector=selector=>({
  '#main':main,
  '#render-arrangement':dryButton,
  '#render-balanced-arrangement':balancedButton,
  '#render-listening-master':masterButton,
  '#listening-master-result':masterHolder,
}[selector]||null);
document.querySelectorAll=()=>[];
showError=error=>{throw error};
const selection='a'.repeat(64),controlManifest='b'.repeat(64);
const artifact={
  manifest_sha256:'c'.repeat(64),
  selection_manifest_sha256:selection,
  balanced_arrangement_manifest_sha256:controlManifest,
  master_url:'/master.wav',
  receipt_url:'/master.json',
  summary:{
    input_integrated_lufs:-21,
    output_integrated_lufs:-16,
    output_true_peak_dbtp:-1,
  },
  mastered:true,
  release_master:false,
  cache_hit:false,
};
const calls=[];
api=async(path,options)=>{
  calls.push({path,method:options.method,body:JSON.parse(options.body)});
  return {listening_master:artifact,product_outputs:{marker:'updated'}};
};
project={
  decoded_arrangement_selection:{selection_manifest_sha256:selection},
  arrangement:null,
  balanced_arrangement:{
    selection_manifest_sha256:selection,
    manifest_sha256:controlManifest,
  },
  listening_master:null,
  product_outputs:{marker:'old'},
};
view='arrangement';
renderArrangement();
await masterButton.onclick();
return {
  calls,
  masterManifest:project.listening_master?.manifest_sha256,
  productMarker:project.product_outputs?.marker,
  rendered:masterHolder.innerHTML,
};
"""
        )

        self.assertEqual(
            result["calls"],
            [
                {
                    "path": "/api/listening-master",
                    "method": "POST",
                    "body": {
                        "selection_manifest_sha256": "a" * 64,
                        "balanced_arrangement_manifest_sha256": "b" * 64,
                    },
                }
            ],
        )
        self.assertEqual(result["masterManifest"], "c" * 64)
        self.assertEqual(result["productMarker"], "updated")
        self.assertIn("/master.wav", result["rendered"])

    def test_stale_selection_or_balanced_control_response_is_ignored(self) -> None:
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
const masterButton={disabled:false,textContent:'',isConnected:true};
const masterHolder={innerHTML:'unchanged'};
document.querySelector=selector=>({
  '#main':main,
  '#render-arrangement':dryButton,
  '#render-balanced-arrangement':balancedButton,
  '#render-listening-master':masterButton,
  '#listening-master-result':masterHolder,
}[selector]||null);
document.querySelectorAll=()=>[];
const errors=[],requests=[];
showError=error=>errors.push(String(error?.message||error));
api=path=>new Promise((resolve,reject)=>requests.push({path,resolve,reject}));
const selection='a'.repeat(64),controlA='b'.repeat(64),controlB='d'.repeat(64);
function artifact(control){
  return {
    manifest_sha256:'c'.repeat(64),
    selection_manifest_sha256:selection,
    balanced_arrangement_manifest_sha256:control,
    master_url:'/stale.wav',
    receipt_url:'/stale.json',
    summary:{},
    mastered:true,
    release_master:false,
    cache_hit:false,
  };
}
project={
  decoded_arrangement_selection:{selection_manifest_sha256:selection},
  arrangement:null,
  balanced_arrangement:{
    selection_manifest_sha256:selection,
    manifest_sha256:controlA,
  },
  listening_master:null,
  product_outputs:{marker:'original'},
};
view='arrangement';
renderArrangement();
const selectionPending=masterButton.onclick();
project.decoded_arrangement_selection.selection_manifest_sha256='e'.repeat(64);
requests[0].resolve({
  listening_master:artifact(controlA),
  product_outputs:{marker:'stale-selection'},
});
await selectionPending;
const selectionIgnored=project.listening_master===null
  && project.product_outputs.marker==='original'
  && masterHolder.innerHTML==='unchanged';

project.decoded_arrangement_selection.selection_manifest_sha256=selection;
project.balanced_arrangement={
  selection_manifest_sha256:selection,
  manifest_sha256:controlA,
};
masterButton.disabled=false;
renderArrangement();
masterHolder.innerHTML='unchanged-again';
const controlPending=masterButton.onclick();
project.balanced_arrangement.manifest_sha256=controlB;
requests[1].resolve({
  listening_master:artifact(controlA),
  product_outputs:{marker:'stale-control'},
});
await controlPending;
const controlIgnored=project.listening_master===null
  && project.product_outputs.marker==='original'
  && masterHolder.innerHTML==='unchanged-again';
return {selectionIgnored,controlIgnored,errors};
"""
        )

        self.assertTrue(result["selectionIgnored"])
        self.assertTrue(result["controlIgnored"])
        self.assertEqual(result["errors"], [])

    def test_master_ui_has_no_event_feedback_or_automatic_choice_effect(self) -> None:
        self.assertIn("records no event or feedback", self.arrangement)
        self.assertIn("never replaces or automatically promotes", self.arrangement)
        self.assertIn("changes no MIDI choice, selection, ranking or default", self.arrangement)
        self.assertNotIn("/api/events", self.master_action)
        self.assertNotIn("/api/feedback", self.master_action)
        self.assertNotIn("save(", self.master_action)
        self.assertNotIn("candidate_decision", self.master_action)
        self.assertNotIn("project.balanced_arrangement=", self.master_action)
        self.assertNotIn("/api/events", self.master_renderer)
        self.assertNotIn("/api/feedback", self.master_renderer)
        for promotional_claim in (
            "recommended",
            "winner",
            "better version",
            "new default",
            "preferred version",
        ):
            self.assertNotIn(promotional_claim, self.master_renderer.lower())

    def test_shared_audio_binding_treats_master_as_a_prepared_local_wav(self) -> None:
        result = self.run_ui_node(
            """
const messages=[];
setDecodedStatus=(message,kind)=>messages.push({message,kind});
const audio={
  id:'listening-master-audio',
  dataset:{
    playbackMode:'listening-master',
    playbackLabel:'the separate Listening Master challenger',
  },
  currentTime:0,
  addEventListener(){},
};
bindSharedAudio(audio);
audio.onplay();
return {
  messages,
  wiring:wireArrangementPlayer.toString(),
};
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
        self.assertIn("#listening-master-audio", result["wiring"])


if __name__ == "__main__":
    unittest.main()
