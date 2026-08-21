import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

async function render(path = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}-${path}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request(`http://localhost${path}`, {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

async function loadCleanRouteHandler() {
  const template = await readFile(
    new URL("../infra/site.yaml", import.meta.url),
    "utf8",
  );
  const block = template.match(
    /FunctionCode:(?: !Sub)? \|\n(?<code>(?: {8}.+(?:\n|$))+)/,
  );
  assert.ok(block?.groups?.code, "CloudFront function code was not found");
  const code = block.groups.code
    .split("\n")
    .map((line) => line.replace(/^ {8}/, ""))
    .join("\n")
    .replaceAll("${DomainName}", "sunofriend.com");
  const handler = vm.runInNewContext(`${code}\nhandler;`);
  assert.equal(typeof handler, "function");
  return handler;
}

function cloudFrontErrorBlock(template, errorCode) {
  const match = template.match(
    new RegExp(
      `^ {10}- ErrorCode: ${errorCode}\\n(?<settings>(?: {12}.+(?:\\n|$))+)`,
      "m",
    ),
  );
  assert.ok(match, `CloudFront ${errorCode} error response was not found`);
  return match[0];
}

test("rewrites clean website routes to their static index files", async () => {
  const handler = await loadCleanRouteHandler();
  const rewrite = (uri) => handler({ request: { uri } }).uri;

  assert.equal(rewrite("/"), "/index.html");
  assert.equal(rewrite("/demo"), "/demo/index.html");
  assert.equal(rewrite("/demo/"), "/demo/index.html");
  assert.equal(rewrite("/for-agents"), "/for-agents/index.html");
  assert.equal(rewrite("/for-agents/"), "/for-agents/index.html");
  assert.equal(
    rewrite("/research/separation/"),
    "/research/separation/index.html",
  );
  assert.equal(
    rewrite("/research/vocal-comping/"),
    "/research/vocal-comping/index.html",
  );
  assert.equal(rewrite("/stems"), "/stems/index.html");
  assert.equal(rewrite("/stems/"), "/stems/index.html");
  assert.equal(rewrite("/glossary"), "/glossary/index.html");
  assert.equal(rewrite("/glossary/"), "/glossary/index.html");
  assert.equal(rewrite("/contact"), "/contact/index.html");
  assert.equal(rewrite("/contact/"), "/contact/index.html");
  assert.equal(rewrite("/privacy"), "/privacy/index.html");
  assert.equal(rewrite("/privacy/"), "/privacy/index.html");
  assert.equal(rewrite("/llms.txt"), "/llms.txt");
  assert.equal(
    rewrite("/_next/static/chunks/app.js"),
    "/_next/static/chunks/app.js",
  );

  const wwwRedirect = handler({
    request: {
      uri: "/demo/",
      headers: { host: { value: "www.sunofriend.com" } },
      querystring: { a: { value: "b" } },
    },
  });
  assert.equal(wwwRedirect.statusCode, 301);
  assert.equal(
    wwwRedirect.headers.location.value,
    "https://sunofriend.com/demo/?a=b",
  );
  const apex = handler({
    request: { uri: "/stems", headers: { host: { value: "sunofriend.com" } } },
  });
  assert.equal(apex.uri, "/stems/index.html");
});

test("server-renders an approachable skill-first musician page", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(
    html,
    /<title>Sunofriend — Hear the song\. Change the parts\.<\/title>/i,
  );
  assert.match(html, /Let your agent guide the setup/);
  assert.match(html, /Start with the skill/);
  assert.match(html, /NEW · CORE-FOUR PREVIEW/);
  assert.match(html, /VOCALS · DRUMS · BASS · OTHER/);
  assert.match(html, /LOCAL OPT-IN SEPARATION/);
  assert.match(
    html,
    /href="\/research\/separation\/"[^>]*aria-label="New public opt-in preview: try local vocals, drums, bass and grouped-other stem separation"/,
  );
  assert.match(html, /ONE SKILL\. YOUR CHOICE OF AGENT/);
  assert.match(html, /plain-text Sunofriend skill tells a compatible local agent/);
  assert.match(
    html,
    /Example skills-aware agents\s*include Codex, Claude Code and Antigravity/,
  );
  assert.match(html, /Tested on a MacBook so far/);
  assert.match(html, /Windows and Linux are not verified yet/);
  assert.match(html, /Feedback from every Sunofriend user is welcome/);
  assert.match(html, /make SKILL\.md and the setup path more portable/);
  assert.match(html, /Send compatibility feedback/);
  assert.match(html, /TURN 1 \/ INSTALL THE SKILL/);
  assert.match(html, /Use \$skill-installer/);
  assert.match(html, /Do not install the Sunofriend app/);
  assert.match(html, /TURN 2 \/ USE SUNOFRIEND/);
  assert.match(html, /Use \$sunofriend/);
  assert.match(html, /Do not clone the repository first/);
  assert.match(html, /restart Codex once/);
  assert.match(html, /I HAVE STEMS/);
  assert.match(html, /I HAVE A FINISHED SONG/);
  assert.match(
    html,
    /public alpha estimates broad\s*vocals and complementary instrumental by default/,
  );
  assert.match(
    html,
    /explicit\s*SCNet core-four opt-in estimates vocals, drums, bass and grouped\s*other/,
  );
  assert.match(
    html,
    /Two broad stems by default; four grouped roles by explicit opt-in/,
  );
  assert.doesNotMatch(html, /Two broad stems, not individual instrument families/);
  assert.match(html, /I NEED OTHER STEM OPTIONS/);
  assert.match(html, /What stems are and where to get them/);
  assert.match(html, /Open the glossary/);
  assert.match(html, /I WANT THE DEMO/);
  assert.match(html, /Codex with local workspace access/);
  assert.match(html, /normal ChatGPT conversation/);
  assert.match(html, /automatic and unreviewed/);
  assert.match(html, /Hear Out of Place|Out of Place/);
  assert.match(html, /private, unregistered six-role research/);
  assert.match(html, /all 3\/3 cases useful and non-catastrophic/);
  assert.match(
    html,
    /synth and guitar were each useful in 2\/2\s*confirmed-present cases/,
  );
  assert.match(html, /resource and objective\s*qualification remain incomplete/);
  assert.match(html, /there is no public six-role\s*command/);
  assert.doesNotMatch(html, /currently non-executable research plan/);
  assert.match(html, /SoftwareApplication/);
  assert.match(html, /Unsigned Media Ltd/);
  assert.match(html, /not related to or affiliated/);
  assert.match(html, /hello@sunofriend\.com/);
  assert.match(html, /Vocal comping is taking shape/);
  assert.match(html, /Phrase recording \+ aligned pickups/);
  assert.match(html, /Automatic selection, joins or tuning/);
  assert.match(html, /href="\/research\/vocal-comping\/"/);
  assert.doesNotMatch(html, /brew install|git clone/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton|Starter Project/);
});

test("publishes clear contact, support, security and privacy routes", async () => {
  const contactResponse = await render("/contact/");
  assert.equal(contactResponse.status, 200);
  const contactHtml = await contactResponse.text();

  assert.match(contactHtml, /CONTACT SUNOFRIEND/);
  assert.match(contactHtml, /hello@sunofriend\.com/);
  assert.match(contactHtml, /up to two working days/);
  assert.match(contactHtml, /Do not send stems or private music/);
  assert.match(contactHtml, /Report a vulnerability privately/);
  assert.match(contactHtml, /security\/advisories\/new/);

  const privacyResponse = await render("/privacy/");
  assert.equal(privacyResponse.status, 200);
  const privacyHtml = await privacyResponse.text();

  assert.match(privacyHtml, /PRIVACY NOTICE/);
  assert.match(privacyHtml, /Unsigned Media Ltd/);
  assert.match(privacyHtml, /company number 17046305/);
  assert.match(privacyHtml, /Hover/);
  assert.match(privacyHtml, /Google Gmail/);
  assert.match(privacyHtml, /Amazon Web Services/);
  assert.match(privacyHtml, /do not sell contact information/);
  assert.match(privacyHtml, /process information outside the UK/);
  assert.match(privacyHtml, /Your right to object/);
  assert.match(privacyHtml, /Information Commissioner/);
});

test("publishes a canonical developer and agent integration page", async () => {
  const response = await render("/for-agents/");
  assert.equal(response.status, 200);
  const html = await response.text();

  assert.match(html, /AUTHORITATIVE AGENT ENTRY POINT/);
  assert.match(html, /One skill, not one agent/);
  assert.match(html, /plain-text operational guidance, not a Codex-only/);
  assert.match(html, /Codex, Claude Code, Antigravity/);
  assert.match(html, /Only a MacBook has been tested so far/);
  assert.match(html, /Windows\s*and Linux are unverified/);
  assert.match(html, /SKILL\.md and setup\s*guidance can be made more compatible/);
  assert.match(html, /Install and read the official skill/);
  assert.match(html, /Stop after confirming the skill is available/);
  assert.match(html, /\$skill-installer/);
  assert.match(html, /\$sunofriend/);
  assert.match(html, /standard ChatGPT conversation/i);
  assert.match(html, /Offer four human routes/);
  assert.match(html, /Use the focused beginner command/);
  assert.match(html, /exact 40-character commit/);
  assert.match(html, /Apply never fetches or switches it/);
  assert.match(html, /sunofriend create PROJECT --out-dir FRESH/);
  assert.match(html, /sunofriend demo --out-dir FRESH/);
  assert.match(html, /human preference/);
  assert.match(html, /stems provide timing/);
  assert.match(html, /\/llms\.txt/);
  assert.match(html, /\/agent-capabilities\.json/);
  assert.match(html, /raw\.githubusercontent\.com/);
  assert.match(html, /sunofriend source-doctor/);
  assert.match(
    html,
    /sunofriend source-import-folder SOURCE_FOLDER --out-dir FRESH/,
  );
  assert.match(html, /Execution replans current inputs/);
  assert.match(html, /accept-unconfirmed-origin/);
  assert.match(html, /does not shift, pad/);
  assert.match(html, /does not .*create\s+MIDI/s);
  assert.match(html, /not related to or affiliated/);
  assert.match(html, /Experimental separation status/);
  assert.match(html, /sunofriend-separate/);
  assert.match(html, /broad vocals/);
  assert.match(html, /Offer two stems by default or four by explicit opt-in/);
  assert.match(html, /core-four-stems-v1/);
  assert.match(html, /estimates vocals, drums, bass and grouped other/);
  assert.match(html, /Do not promise recovered studio multitracks or clean instrument isolation/);
  assert.match(html, /other-refinement-v1/);
  assert.match(html, /private, unregistered six-role research/);
  assert.match(html, /all 3\/3 cases useful and non-catastrophic/);
  assert.match(
    html,
    /synth and\s*guitar were each useful in 2\/2 confirmed-present cases/,
  );
  assert.match(
    html,
    /private_full_song_six_role_listening_evidence_recorded_resource_gate_incomplete/,
  );
  assert.match(html, /does not register either specialist/);
  assert.match(html, /there is no public six-role command/);
  assert.doesNotMatch(html, /remains\s*blocked and non-executable/);
  assert.match(html, /\/research\/separation\//);
});

test("publishes four honest public and private separation lanes", async () => {
  const response = await render("/research/separation/");
  assert.equal(response.status, 200);
  const html = await response.text();

  assert.match(html, /PUBLIC EXPERIMENTAL PREVIEW · AUDIO STAYS LOCAL/);
  assert.match(html, /Try two stems—or opt in to four/);
  assert.match(html, /Four lanes, two public/);
  assert.match(html, /PUBLIC DEFAULT/);
  assert.match(html, /Broad vocals and instrumental/);
  assert.match(html, /PUBLIC EXPLICIT OPT-IN/);
  assert.match(html, /SCNet core four/);
  assert.match(html, /scnet-large-musdb-release-v1/);
  assert.match(html, /core-four-stems-v1/);
  assert.match(html, /PRIVATE UNREGISTERED RESEARCH/);
  assert.match(html, /Six roles with synth and guitar/);
  assert.match(html, /no public six-role command/i);
  assert.match(html, /PRIVATE MODEL-FREE RECOVERED REVIEW/);
  assert.match(
    html,
    /private_review_package_recovered_model_free_resource_gate_incomplete/,
  );
  assert.match(html, /0 checkpoint loads/);
  assert.match(html, /0 model constructions/);
  assert.match(html, /0 model loads/);
  assert.match(html, /0 inference attempts/);
  assert.match(html, /0 model-worker subprocesses/);
  assert.match(html, /0 network attempts/);
  assert.match(html, /One parent sandbox re-exec/);
  assert.match(html, /21 retained private audio payloads/);
  assert.match(html, /24 new PCM24 review artifacts reconstruct within 0 LSB/);
  assert.match(html, /3 model loads and 9 completed inference attempts/);
  assert.match(html, /guitar worker result receipt and guard counters were not/);
  assert.match(html, /guitar peak-memory evidence is absent/);
  assert.match(html, /full objective qualification is false/);
  assert.match(html, /human_listening_complete_no_selection/);
  assert.match(html, /all 3\/3 songs were useful and non-catastrophic/i);
  assert.match(html, /core roles were useful in 3\/3/);
  assert.match(html, /synth and guitar were each useful in 2\/2/);
  assert.match(html, /Both specialists reported\s+some missing content in 2\/2 cases/);
  assert.match(
    html,
    /private_full_song_six_role_listening_evidence_recorded_resource_gate_incomplete/,
  );
  assert.match(
    html,
    /fa5d1d24627dce4cb1e27175055f1e3d5a3a70683b98e2376d92ee125bc2163c/,
  );
  assert.doesNotMatch(html, /Human listening of this recovered package is pending/);
  assert.match(
    html,
    /no automatic retry, public activation, source selection, MIDI/,
  );
  assert.match(html, /How to try the public alpha/);
  assert.match(html, /INSPECT SETUP/);
  assert.match(html, /sunofriend-separate doctor/);
  assert.match(html, /How the feature was developed/);
  assert.match(html, /Software checks evidence; people judge music/);
  assert.match(html, /Do not attach private audio/);
  assert.match(html, /Send a first-song report/);
  assert.match(html, /Send text-only compatibility feedback/);
  assert.doesNotMatch(
    html,
    /provider Synth|same-transcriber|source-visible local presence/i,
  );
  assert.doesNotMatch(html, /model\.safetensors|separation-bakeoff|\/Users\//);
});

test("publishes an honest vocal-comping pilot and whole-song GUI concept", async () => {
  const response = await render("/research/vocal-comping/");
  assert.equal(response.status, 200);
  const html = await response.text();

  assert.match(html, /PRIVATE RESEARCH PILOT · NOT A FINISHED PRODUCT/);
  assert.match(html, /Keep your voice\. Build the best performance/);
  assert.match(html, /A working phrase pilot—not automatic comping/);
  assert.match(html, /Phrase-by-phrase recording/);
  assert.match(html, /Complete takes, then repair gaps/);
  assert.match(html, /One base pass plus guided pickups/);
  assert.match(html, /The proposed whole-song workspace/);
  assert.match(html, /SONG MAP · 18 PHRASES/);
  assert.match(html, /Reveal analysis after listening/);
  assert.match(html, /From first phrase to export/);
  assert.match(html, /the public website does not record, upload or process audio/i);
  assert.match(html, /No acceptable take is a valid result/);
  assert.match(html, /Correction is optional and downstream/);
  assert.doesNotMatch(html, /\/Users\//);
});

test("explains stems, neutral providers, privacy and the current boundary", async () => {
  const response = await render("/stems/");
  assert.equal(response.status, 200);
  const html = await response.text();

  assert.match(html, /BEGINNER STEM GUIDE/);
  assert.match(html, /A stem is <strong>not necessarily one instrument/);
  assert.match(html, /Bring separate parts, or try local experimental separation/);
  assert.match(html, /sunofriend source-doctor/);
  assert.match(
    html,
    /sunofriend source-import-folder SOURCE_FOLDER --out-dir FRESH/,
  );
  assert.match(html, /does not shift, pad, stretch, normalize or align/);
  assert.match(html, /replans the current files/);
  assert.match(html, /accept-unconfirmed-origin/);
  assert.match(html, /Do not map an observed part to/);
  assert.match(html, /defaults to broad vocals and complementary/);
  assert.match(html, /Neutral provider starting points/);
  assert.match(html, /No current affiliate links/);
  assert.match(html, /receives no commission/);
  assert.match(html, /Cloud \+ local option/);
  assert.match(html, /Check before you process/);
  assert.match(html, /Is the song unreleased, confidential/);
  assert.match(html, /What to bring back/);
  assert.match(html, /Open the demo guide/);
  assert.match(html, /Start with the skill/);
  assert.match(
    html,
    /aria-label="Moises official site \(opens in a new tab\)"/,
  );
  assert.match(html, />Moises(?:<!-- -->)? official site ↗<\/a>/);
  assert.doesNotMatch(html, /rel="sponsored"/);
});

test("publishes shared plain-language stem and MIDI terminology", async () => {
  const response = await render("/glossary/");
  assert.equal(response.status, 200);
  const html = await response.text();

  assert.match(html, /PLAIN-LANGUAGE MUSIC GLOSSARY/);
  assert.match(html, /Finished mix/);
  assert.match(html, /Multitracks/);
  assert.match(html, /AI-separated stem/);
  assert.match(html, /Refined stem or sub-stem/);
  assert.match(html, /Bleed or leakage/);
  assert.match(html, /Residual or complement/);
  assert.match(html, /MIDI/);
  assert.match(html, /Instrument or sample bundle/);
  assert.match(html, /A stem can contain many sounds/);
  assert.match(html, /Where to get stems/);
});

test("publishes an executable copyright-safe synthetic demo", async () => {
  const response = await render("/demo/");
  assert.equal(response.status, 200);
  const html = await response.text();

  assert.match(html, /COPYRIGHT-SAFE BUILT-IN DEMO/);
  assert.match(html, /complete result without personal music/);
  assert.match(html, /TURN 1 \/ INSTALL THE SKILL/);
  assert.match(html, /TURN 2 \/ RUN THE DEMO/);
  assert.match(html, /Use \$skill-installer/);
  assert.match(html, /Use \$sunofriend/);
  assert.match(html, /Do not clone the repository first/);
  assert.match(html, /restart Codex once/);
  assert.match(html, /sunofriend demo --out-dir FRESH/);
  assert.match(html, /normal automatic MIDI\/WAV\/ZIP pipeline/);
  assert.match(html, /no optional AI model required/);
  assert.match(html, /Out of Place/);
  assert.match(html, /The Aisle at Lidl MIDI pack/);
  assert.match(html, /sunofriend create PROJECT --out-dir FRESH/);
  assert.match(html, /Learn how to get stems/);
  assert.doesNotMatch(html, /does not currently bundle redistributable raw WAV stems/);
});

test("publishes concise llms.txt discovery guidance", async () => {
  const text = await readFile(
    new URL("../public/llms.txt", import.meta.url),
    "utf8",
  );

  assert.match(text, /^# Sunofriend/m);
  assert.match(text, /skill is not tied to Codex/);
  assert.match(text, /Codex, Claude Code and Antigravity/);
  assert.match(text, /only been tested on a MacBook so far/);
  assert.match(text, /Windows and Linux are unverified/);
  assert.match(text, /feedback from every user is welcome/i);
  assert.match(text, /Install the official skill/);
  assert.match(text, /standard ChatGPT conversation/i);
  assert.match(text, /\$skill-installer/);
  assert.match(text, /Confirm the skill is available, then stop/);
  assert.match(text, /In a second turn, explicitly use the installed skill/);
  assert.match(text, /In Codex, invoke `\$sunofriend`/);
  assert.match(text, /two-stage bootstrap/);
  assert.match(text, /exact 40-character commit/);
  assert.match(text, /exact published production primary/);
  assert.match(text, /sunofriend create PROJECT --out-dir FRESH/);
  assert.match(text, /sunofriend demo --out-dir FRESH/);
  assert.match(text, /copyright-safe synthetic stems/);
  assert.match(text, /not exact waveform reconstruction/);
  assert.match(text, /Experimental finished-mix separation/);
  assert.match(text, /Public default lane/);
  assert.match(text, /Public explicit opt-in lane/);
  assert.match(text, /scnet-large-musdb-release-v1/);
  assert.match(text, /core-four-stems-v1/);
  assert.match(text, /Private unregistered research lane/);
  assert.match(text, /Private model-free recovery lane/);
  assert.match(
    text,
    /private_review_package_recovered_model_free_resource_gate_incomplete/,
  );
  assert.match(text, /0 checkpoint loads/);
  assert.match(text, /0 model constructions/);
  assert.match(text, /0 model loads/);
  assert.match(text, /0 inference attempts/);
  assert.match(text, /0 model-worker subprocesses/);
  assert.match(text, /0 network attempts/);
  assert.match(text, /one parent sandbox re-exec/i);
  assert.match(text, /persisted no guitar worker result receipt, guard counters/);
  assert.match(text, /peak-memory evidence/);
  assert.match(text, /full objective qualification is false/);
  assert.match(text, /human_listening_complete_no_selection/);
  assert.match(text, /all 3\/3 songs were useful and non-catastrophic/);
  assert.match(text, /synth and guitar were each useful in 2\/2/);
  assert.match(
    text,
    /private_full_song_six_role_listening_evidence_recorded_resource_gate_incomplete/,
  );
  assert.match(
    text,
    /fa5d1d24627dce4cb1e27175055f1e3d5a3a70683b98e2376d92ee125bc2163c/,
  );
  assert.doesNotMatch(text, /Human listening is pending/);
  assert.match(text, /sunofriend-separate doctor/);
  assert.match(text, /sunofriend-separate profiles --json/);
  assert.match(text, /FULL_STEM_SEPARATION_PLAN\.md/);
  assert.match(text, /Human listening decides usefulness/);
  assert.doesNotMatch(
    text,
    /source-visible local presence review|same-transcriber bottleneck|provider Synth estimates/,
  );
  assert.match(text, /A stem is a synchronized grouped submix/);
  assert.match(text, /no affiliate relationship/);
  assert.match(text, /sunofriend\.com\/stems/);
  assert.match(text, /sunofriend\.com\/glossary/);
  assert.match(text, /sunofriend source-doctor/);
  assert.match(
    text,
    /sunofriend source-import SOURCE --out-dir FRESH --plan/,
  );
  assert.match(
    text,
    /sunofriend source-import-folder SOURCE_FOLDER --out-dir FRESH/,
  );
  assert.match(text, /not a song-project importer/);
  assert.match(text, /does not prove alignment/);
  assert.match(text, /Composite `drums` is preserved pending S2/);
  assert.doesNotMatch(text, /No redistributable raw-stem conversion demo/);
});

test("publishes a versioned machine-readable capability contract", async () => {
  const data = JSON.parse(
    await readFile(
      new URL("../public/agent-capabilities.json", import.meta.url),
      "utf8",
    ),
  );

  assert.equal(data.schema, "sunofriend.agent-capabilities.v1");
  assert.equal(data.product.local_first, true);
  assert.equal(data.product.hosted_conversion_available, false);
  assert.deepEqual(data.platform_testing.verified, ["MacBook running macOS"]);
  assert.deepEqual(data.platform_testing.unverified, ["Windows", "Linux"]);
  assert.match(data.platform_testing.feedback_requested_from, /Every Sunofriend user/);
  assert.deepEqual(data.agent_entry.example_agents, [
    "Codex",
    "Claude Code",
    "Antigravity",
  ]);
  assert.equal(data.agent_entry.codex_specific_commands_required, false);
  assert.equal(data.agent_entry.raw_skill_url.includes("SKILL.md"), true);
  assert.equal(
    data.agent_entry.advanced_operations_url.includes("advanced-operations.md"),
    true,
  );
  assert.equal(data.agent_entry.two_turn_start.length, 2);
  assert.match(data.agent_entry.two_turn_start[0], /\$skill-installer/);
  assert.match(data.agent_entry.two_turn_start[1], /\$sunofriend/);
  assert.equal(
    data.agent_entry.installation_protocol.apply_fetches_or_switches_checkout,
    false,
  );
  assert.equal(data.modes.simple.human_preference_recorded, false);
  assert.equal(
    data.modes.agent_create.command,
    "sunofriend create PROJECT --out-dir FRESH",
  );
  assert.equal(data.modes.demo.uses_normal_automatic_pipeline, true);
  assert.equal(data.boundaries.stem_separation, true);
  assert.equal(
    data.experiments.finished_mix_separation.status,
    "public_experimental_local_alpha",
  );
  assert.equal(
    data.experiments.finished_mix_separation.public_product_route_available,
    true,
  );
  assert.equal(
    data.experiments.finished_mix_separation.human_listening_required,
    true,
  );
  assert.equal(
    data.experiments.vocal_comping.status,
    "private_phrase_pilot_whole_song_gui_in_design",
  );
  assert.equal(
    data.experiments.vocal_comping.public_product_route_available,
    false,
  );
  assert.equal(
    data.experiments.vocal_comping.current_effects.automatic_take_selection,
    false,
  );
  assert.equal(
    data.experiments.vocal_comping.current_effects.vocal_comp_rendering,
    false,
  );
  assert.equal(
    data.experiments.finished_mix_separation.read_only_doctor_loads_model,
    false,
  );
  assert.equal(
    data.experiments.finished_mix_separation.read_only_doctor_processes_audio,
    false,
  );
  assert.equal(
    data.experiments.finished_mix_separation.development_method.length,
    5,
  );
  assert.match(
    data.experiments.finished_mix_separation.developer_preview_url,
    /SEPARATION_DEVELOPER_PREVIEW\.md/,
  );
  assert.equal(
    data.experiments.finished_mix_separation.feedback_accepts_private_audio,
    false,
  );
  assert.equal(data.boundaries.rights_required, true);
  assert.equal(
    data.experiments.finished_mix_separation.core_four_stem_target.executable,
    true,
  );
  assert.equal(
    data.experiments.finished_mix_separation.core_four_stem_target
      .implementation_available,
    true,
  );
  assert.equal(
    data.experiments.finished_mix_separation.core_four_stem_target.status,
    "public_opt_in",
  );
  assert.equal(
    data.experiments.finished_mix_separation.core_four_stem_target
      .activation_retry_enabled,
    false,
  );
  assert.equal(
    data.experiments.finished_mix_separation.core_four_stem_target.profile_id,
    "scnet-large-musdb-release-v1",
  );
  assert.deepEqual(
    data.experiments.finished_mix_separation.core_four_stem_target.roles,
    ["vocals", "drums", "bass", "other"],
  );
  assert.equal(
    data.experiments.finished_mix_separation.core_four_stem_target
      .activation_requires.length,
    4,
  );
  assert.equal(
    data.experiments.finished_mix_separation.core_four_stem_target
      .minimum_usefulness_rating_for_activation,
    null,
  );
  assert.equal(
    data.experiments.finished_mix_separation.core_four_stem_target
      .checkpoint_bytes,
    168848417,
  );
  assert.equal(
    data.experiments.finished_mix_separation.core_four_stem_target
      .checkpoint_sha256,
    "719e5abb8ed920305dad546ac3cd6fb0b1e9c3092d14ce21827bfc0423af3070",
  );
  assert.equal(
    data.experiments.finished_mix_separation.core_four_stem_target
      .activation_requirements_complete,
    true,
  );
  assert.deepEqual(
    data.experiments.finished_mix_separation.core_four_stem_target
      .remaining_activation_blockers,
    [],
  );
  assert.equal(
    data.experiments.finished_mix_separation.core_four_stem_target
      .synthetic_canary.status,
    "objective_pass",
  );
  assert.equal(
    data.experiments.finished_mix_separation.core_four_stem_target
      .synthetic_canary.maximum_reconstruction_error_lsb,
    0,
  );
  assert.equal(
    data.experiments.finished_mix_separation.core_four_stem_target
      .full_song_canaries.catastrophic_defects_reported,
    0,
  );
  assert.equal(
    data.experiments.finished_mix_separation.core_four_stem_target
      .future_install_command_enabled,
    true,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement.scope_id,
    "other-refinement-v1",
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement.status,
    "studio_challenger",
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement.release_tier,
    "studio_challenger",
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement.executable,
    true,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .candidate_profile_id,
    "demucs-mlx-htdemucs-6s-other-refinement-v1",
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement.candidate_status,
    "studio_challenger",
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .candidate_setup_available,
    true,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .candidate_install_authorizes_inference,
    false,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement.parent_profile_id,
    "scnet-large-musdb-release-v1",
  );
  assert.deepEqual(
    data.experiments.finished_mix_separation.other_refinement.supported_targets,
    ["guitar", "keys"],
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement.feedback_evidence
      .valid_report_count,
    10,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement.feedback_evidence
      .conclusion,
    "technically_valid_musically_unsuccessful",
  );
  assert.deepEqual(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.targets,
    ["guitar", "keyboard_synth"],
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.executable,
    false,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.status,
    "reference_objective_pass_human_listening_musically_unsuccessful",
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.synthetic_plan_document_sha256,
    "0c2e83e0e55f40a8c38a6d103aae81a6443f1c935f5c1f08e35cdbb241426356",
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.forward_contract_document_sha256,
    "886a88dd511ac4075a90536360d91181338a81df58b51c86c7290d7c7d57e36c",
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.forward_contract_implemented,
    true,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.reference_query_result.not_useful_cases,
    8,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.synthetic_plan_run_limit,
    1,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.synthetic_plan_uses_private_audio,
    false,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.synthetic_report_contract_document_sha256,
    "81b11e5a85fc8fce656ba78657f359169930871daa824beb6d12595da1328ae5",
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.synthetic_report_accepts_objective_failure,
    true,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.synthetic_report_allows_subjective_feedback,
    false,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.synthetic_report_grants_retry_or_activation,
    false,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.required_passt_checkpoint.published_bytes,
    341546630,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.required_passt_checkpoint.sha256,
    "dc229428753176e8be0373d25887116fc15b490af86f671cecf9ed76a0f287da",
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.required_passt_checkpoint
      .evidence_only_download_authorized,
    true,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.required_passt_checkpoint.deserialized,
    true,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.runtime_wheel_evidence.package_count,
    28,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.runtime_wheel_evidence.wheel_bytes,
    99354620,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.runtime_wheel_evidence.requirements_sha256,
    "28249f5d6ab80d4b72a5f256ac435f3a2d150b1baa30d751754af44049c33b92",
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.runtime_wheel_evidence.dependency_installed,
    false,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.runtime_wheel_evidence.packages_imported,
    false,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.runtime_import_evidence.locked_package_count,
    28,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.runtime_import_evidence.network_attempts,
    0,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.runtime_import_evidence.checkpoint_loaded,
    false,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.restricted_model_load_evidence.report_sha256,
    "12c028e88afdb94a22aa4344b75fb63a23386fd4f2292d9bf9aac0405b12dced",
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.restricted_model_load_evidence
      .keys_shapes_and_dtypes_equal,
    true,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.restricted_model_load_evidence.inference_runs,
    0,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.reference_query_result.inference_attempts,
    9,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.reference_query_result
      .maximum_reconstruction_error_lsb,
    0,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.reference_query_result.human_listening_pending,
    false,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_query_challenger.reference_query_result.midi_authorized,
    false,
  );
  assert.deepEqual(
    data.experiments.finished_mix_separation.other_refinement
      .next_synth_challenger.priority,
    ["synth", "guitar", "wind"],
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_synth_challenger.first_target,
    "synth",
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_synth_challenger.checkpoint_declared_bytes,
    1368919887,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_synth_challenger.checkpoint_locally_verified,
    true,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_synth_challenger.inference_authorized,
    false,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_synth_challenger.plan_document_sha256,
    "68ddcbc763771ac4edc5190c75db3233606a5e97a364664f690df192628b9c9a",
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_synth_challenger.runtime_wheel_evidence.package_count,
    29,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_synth_challenger.runtime_wheel_evidence.installed,
    true,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_synth_challenger.runtime_import_evidence.locked_package_count,
    29,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_synth_challenger.runtime_import_evidence.python_network_attempts,
    0,
  );
  assert.deepEqual(
    data.experiments.finished_mix_separation.other_refinement
      .next_synth_challenger.runtime_import_evidence.local_bind_attempts,
    ["requests:socket.bind:('::1', 0)"],
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_synth_challenger.artifact_evidence_sha256,
    "d855138176807a7ca8738bd660141eb2b142676e41ccf56014be64e53f012a24",
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_synth_challenger.model_load_evidence.converted_parameter_keys,
    13571,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_synth_challenger.model_load_evidence.forward_calls,
    0,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_synth_challenger.model_load_evidence.chunk_alignment_valid_for_inference,
    false,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_synth_challenger.synthetic_forward_plan.document_sha256,
    "1ac15c7082223fcf2bdfd1d7443320f782cae87b8ac6e89cf991c19553da9903",
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_synth_challenger.synthetic_forward_plan.aligned_chunk_size,
    881664,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_synth_challenger.synthetic_forward_plan.aligned_step_size,
    440832,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_synth_challenger.synthetic_forward_plan.inference_authorized,
    false,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_synth_challenger.synthetic_forward_plan.result.authority_consumed,
    true,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .next_synth_challenger.synthetic_forward_plan.result.output_shape[1],
    53,
  );
  const downstreamMidi =
    data.experiments.finished_mix_separation.other_refinement
      .next_synth_challenger.six_role_integration_result
      .downstream_midi_canary_result;
  assert.equal(
    downstreamMidi.document_sha256,
    "5f3ebf50c0097ca5a0169b63ed1eb4f2efc010d54b525321e5bfd3f621668b09",
  );
  assert.equal(downstreamMidi.midi_transcription_attempts, 16);
  assert.equal(downstreamMidi.neutral_preview_audio_files_written, 16);
  assert.equal(downstreamMidi.network_attempts, 0);
  assert.equal(downstreamMidi.separator_inference_attempts, 0);
  assert.equal(downstreamMidi.automatic_source_choice, false);
  assert.equal(downstreamMidi.human_review_complete, true);
  assert.equal(
    downstreamMidi.human_review_document_sha256,
    "dc766790f97341521363f1705f90ab3dfa1456b1925b0e97e5e13d35e94c2103",
  );
  assert.equal(downstreamMidi.review_source_reference_present, false);
  assert.equal(downstreamMidi.repaired_review_source_reference_present, true);
  assert.equal(downstreamMidi.guitar_candidate_better_cases, 3);
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .parent_and_children_cannot_both_enter_midi,
    true,
  );
  assert.equal(
    data.experiments.finished_mix_separation.other_refinement
      .model_or_dependency_install_authorized,
    false,
  );
  assert.equal(
    data.experiments.finished_mix_separation.review_schema,
    "sunofriend.experimental-separation-review.v3",
  );
  assert.equal(data.interface_contract_version, "2026-08-16.1");
  const separation = data.experiments.finished_mix_separation;
  assert.equal(separation.public_six_role_available, false);
  assert.equal(data.boundaries.public_six_role_separation, false);
  assert.equal(separation.core_four_stem_target.status, "public_opt_in");
  assert.equal(separation.other_refinement.scope_id, "other-refinement-v1");

  assert.deepEqual(separation.lanes.public_default_two_stem.roles, [
    "vocals",
    "instrumental",
  ]);
  assert.equal(
    separation.lanes.public_default_two_stem.public_execution_available,
    true,
  );
  assert.equal(
    separation.lanes.public_default_two_stem.automatic_source_selection,
    false,
  );
  assert.equal(separation.lanes.public_default_two_stem.automatic_midi, false);

  const publicCoreFour = separation.lanes.public_scnet_core_four;
  assert.equal(publicCoreFour.status, "public_opt_in");
  assert.equal(publicCoreFour.scope_id, "core-four-stems-v1");
  assert.equal(publicCoreFour.profile_id, "scnet-large-musdb-release-v1");
  assert.deepEqual(publicCoreFour.roles, [
    "vocals",
    "drums",
    "bass",
    "grouped_other",
  ]);
  assert.equal(publicCoreFour.public_execution_available, true);
  assert.equal(publicCoreFour.automatic_source_selection, false);
  assert.equal(publicCoreFour.automatic_midi, false);

  const privateResearch =
    separation.lanes.private_unregistered_six_role_research;
  assert.equal(privateResearch.visibility, "private");
  assert.equal(privateResearch.registered, false);
  assert.equal(privateResearch.public_execution_available, false);
  assert.deepEqual(privateResearch.roles, [
    "vocals",
    "drums",
    "bass",
    "synth",
    "guitar",
    "residual_other",
  ]);
  assert.equal(privateResearch.public_six_role_support_established, false);

  const recoveredLane = separation.lanes.private_model_free_recovered_review;
  assert.equal(
    recoveredLane.status,
    "private_review_package_recovered_model_free_resource_gate_incomplete",
  );
  assert.equal(
    recoveredLane.human_listening_status,
    "human_listening_complete_no_selection",
  );
  assert.equal(
    recoveredLane.outcome_status,
    "private_full_song_six_role_listening_evidence_recorded_resource_gate_incomplete",
  );
  assert.equal(
    recoveredLane.outcome_document_sha256,
    "fa5d1d24627dce4cb1e27175055f1e3d5a3a70683b98e2376d92ee125bc2163c",
  );
  assert.equal(recoveredLane.public_execution_available, false);

  const fullSong = separation.private_fine_stem_full_song;
  assert.equal(
    fullSong.status,
    "private_review_package_recovered_model_free_resource_gate_incomplete",
  );
  assert.equal(fullSong.registered, false);
  assert.equal(fullSong.public_execution_available, false);
  assert.equal(
    fullSong.original_plan_sha256,
    "869ac229d5c95c9c3d5eb2c9eb38da368056f6fe3c644de9830cc593313efb7d",
  );
  assert.equal(fullSong.original_plan_authority_consumed, true);
  assert.equal(fullSong.automatic_retry_authorized, false);
  assert.deepEqual(fullSong.replacement_historical_effects, {
    model_loads: 3,
    completed_inference_attempts: 9,
    guitar_worker_result_receipt_persisted: false,
    guitar_guard_counters_persisted: false,
    guitar_peak_memory_bytes: null,
  });

  const recovery = fullSong.recovery;
  assert.equal(
    recovery.request_sha256,
    "686a47f09b2f2e95a670e621aa75582e27bb14cebc64035f5c56af3c77f3e60c",
  );
  assert.equal(
    recovery.report_sha256,
    "42500c2e9542aee5fc0e238697733923586ad1e37c54b1359a496cf832f330a0",
  );
  assert.equal(recovery.network_denied, true);
  assert.equal(recovery.retained_audio_payloads_read, 21);
  assert.equal(recovery.pcm24_audio_writes, 24);
  assert.equal(recovery.maximum_reconstruction_error_lsb, 0);
  assert.deepEqual(recovery.effects, {
    checkpoint_loads: 0,
    model_constructions: 0,
    model_loads: 0,
    inference_attempts: 0,
    canonicalisations: 0,
    model_worker_subprocesses: 0,
    network_attempts: 0,
    parent_sandbox_reexecs: 1,
  });
  assert.equal(
    recovery.missing_evidence.guitar_worker_result_receipt_persisted,
    false,
  );
  assert.equal(recovery.missing_evidence.guitar_guard_counters_persisted, false);
  assert.equal(recovery.missing_evidence.guitar_peak_memory_bytes, null);
  assert.equal(
    recovery.resource_qualification.guitar_resource_gate_complete,
    false,
  );
  assert.equal(
    recovery.resource_qualification.full_resource_gate_complete,
    false,
  );
  assert.equal(recovery.resource_qualification.within_known_ceilings, null);
  assert.equal(recovery.full_objective_qualification, false);
  assert.equal(recovery.human_listening_pending, false);
  assert.deepEqual(recovery.product_effects, {
    automatic_retry: false,
    public_activation: false,
    source_selection: false,
    midi: false,
    hosting: false,
    redistribution: false,
    audio_upload: false,
    model_download: false,
  });
  const listening = fullSong.listening_review;
  assert.equal(
    listening.schema,
    "sunofriend.fine-stem-full-song-six-role-listening.v1",
  );
  assert.equal(listening.status, "human_listening_complete_no_selection");
  assert.equal(
    listening.document_sha256,
    "093347845c41bb0c456a10564701961c627fea5737486a901627b0c4f5208a86",
  );
  assert.equal(listening.reviewed_song_count, 3);
  assert.equal(listening.played_item_count, 24);
  assert.equal(listening.confirmed_window_replay_count, 4);
  assert.equal(listening.no_catastrophic_defect_case_count, 3);
  assert.equal(listening.catastrophic_defect_case_count, 0);
  assert.equal(listening.overall_useful_case_count, 3);
  assert.deepEqual(listening.core_role_useful_case_counts, {
    vocals: 3,
    drums: 3,
    bass: 3,
    residual_other: 3,
  });
  assert.deepEqual(listening.confirmed_present_specialist_usefulness, {
    synth: { scored_case_count: 2, useful_case_count: 2 },
    guitar: { scored_case_count: 2, useful_case_count: 2 },
  });
  assert.deepEqual(listening.issues, {
    bleed_some_or_severe_role_case_count: 0,
    artefacts_some_or_severe_role_case_count: 0,
    timing_or_join_some_or_severe_role_case_count: 0,
    core_missing_content_some_or_severe_role_case_count: 0,
    synth_missing_content_some_case_count: 2,
    guitar_missing_content_some_case_count: 2,
    severe_issue_role_case_count: 0,
  });
  assert.equal(listening.cannot_tell_or_not_tested_rating_count, 0);
  assert.equal(listening.private_metadata_included, false);
  assert.equal(
    listening.musical_result,
    "positive_private_full_song_six_role_evidence_with_specialist_missing_content_reported",
  );
  assert.equal(listening.source_selected, false);
  assert.equal(listening.profile_qualified, false);
  assert.equal(listening.public_activation_authorized, false);
  assert.equal(listening.midi_authorized, false);
  assert.doesNotMatch(JSON.stringify(listening), /track_id|filename|path|notes/);
  const outcome = fullSong.recorded_outcome;
  assert.equal(
    outcome.schema,
    "sunofriend.fine-stem-full-song-six-role-outcome.v1",
  );
  assert.equal(
    outcome.status,
    "private_full_song_six_role_listening_evidence_recorded_resource_gate_incomplete",
  );
  assert.equal(
    outcome.document_sha256,
    "fa5d1d24627dce4cb1e27175055f1e3d5a3a70683b98e2376d92ee125bc2163c",
  );
  assert.equal(outcome.review_document_sha256, listening.document_sha256);
  assert.equal(outcome.private_metadata_included, false);
  assert.equal(outcome.full_objective_qualification, false);
  assert.equal(outcome.resource_qualification, false);
  assert.equal(outcome.profile_qualification, false);
  assert.equal(outcome.public_activation_authorized, false);
  assert.equal(outcome.source_selection_authorized, false);
  assert.equal(outcome.midi_authorized, false);
  assert.equal(outcome.hosting_authorized, false);
  assert.equal(outcome.redistribution_authorized, false);
  assert.equal(outcome.audio_upload_authorized, false);
  assert.equal(outcome.automatic_retry_authorized, false);
  assert.doesNotMatch(JSON.stringify(outcome), /track_id|filename|path|notes/);
  assert.match(
    fullSong.next_gate,
    /fresh objective-only repaired guitar-worker run.*missing receipt.*guard counters.*peak-memory evidence/,
  );
  assert.equal(
    separation.other_refinement.next_gate,
    fullSong.next_gate,
  );
  const historicalIntegration =
    separation.other_refinement.next_synth_challenger
      .six_role_integration_result;
  assert.equal(
    historicalIntegration.synth_bottleneck_request.status,
    "private_synth_midi_bottleneck_recorded_no_selection",
  );
  assert.notEqual(
    historicalIntegration.synth_bottleneck_request.status,
    "awaiting_four_provider_synth_or_keyboard_estimates",
  );
  assert.equal(
    historicalIntegration.synth_bottleneck_request.historical_document_status,
    "awaiting_four_provider_synth_or_keyboard_estimates",
  );
  assert.equal(
    historicalIntegration.synth_provider_qualification.status,
    "historical_presence_review_completed_private_evidence",
  );
  assert.notEqual(
    historicalIntegration.synth_provider_qualification.status,
    "provider_estimates_aligned_private_review_required",
  );
  assert.equal(
    historicalIntegration.synth_provider_qualification
      .historical_document_status,
    "provider_estimates_aligned_private_review_required",
  );
  assert.equal(
    historicalIntegration.synth_provider_qualification
      .human_target_presence_review_complete,
    true,
  );
  assert.equal(
    historicalIntegration.synth_bottleneck_request.completed_three_arm_outcome
      .result,
    "no_isolated_synth_midi_advantage_over_grouped_other",
  );
  const capabilityText = JSON.stringify(separation);
  assert.doesNotMatch(
    capabilityText,
    /awaiting[^"]*full.song|full.song[^"]*awaiting/i,
  );

  assert.equal(data.stem_inputs.built_in_full_mix_separation_available, true);
  assert.equal(
    data.stem_inputs.one_asset_multi_format_import_available,
    true,
  );
  assert.equal(
    data.stem_inputs.multi_format_song_project_import_available,
    true,
  );
  assert.equal(
    data.stem_inputs.multi_format_import_scope,
    "2–64 already-separated synchronized top-level supported audio parts per source-import-folder execution",
  );
  assert.equal(
    data.stem_inputs.source_import_plan_command,
    "sunofriend source-import SOURCE --out-dir FRESH --plan",
  );
  assert.equal(data.stem_inputs.source_import_creates_midi, false);
  assert.equal(data.stem_inputs.source_import_separates_audio, false);
  assert.equal(data.stem_inputs.folder_import_available, true);
  assert.match(
    data.stem_inputs.source_folder_import_plan_command,
    /source-import-folder/,
  );
  assert.equal(data.stem_inputs.source_folder_import_replans_on_execute, true);
  assert.equal(data.stem_inputs.source_folder_import_replays_saved_plan, false);
  assert.equal(data.stem_inputs.source_folder_import_minimum_parts, 2);
  assert.equal(data.stem_inputs.source_folder_import_maximum_parts, 64);
  assert.equal(data.stem_inputs.source_folder_import_recurses, false);
  assert.equal(data.stem_inputs.source_folder_import_separates_audio, false);
  assert.equal(
    data.stem_inputs.cross_file_origin_comparison_available,
    true,
  );
  assert.equal(
    data.stem_inputs.unconfirmed_origin_requires_explicit_acknowledgement,
    true,
  );
  assert.equal(data.stem_inputs.cross_file_alignment_available, false);
  assert.equal(
    data.stem_inputs.prepared_folder_directly_usable_by_create_and_tui,
    true,
  );
  assert.equal(data.stem_inputs.observed_pads_role_available, false);
  assert.equal(data.stem_inputs.composite_drums_conversion_available, false);
  assert.equal(
    data.stem_inputs.direct_non_wav_simple_or_studio_project_available,
    false,
  );
  assert.equal(data.stem_inputs.provider_links_are_affiliate_links, false);
  assert.equal(data.stem_inputs.cloud_privacy_check_required, true);
  assert.equal(data.canonical_pages.stems, "https://sunofriend.com/stems/");
  assert.equal(data.canonical_pages.glossary, "https://sunofriend.com/glossary/");
  assert.equal(
    data.canonical_pages.separation_research,
    "https://sunofriend.com/research/separation/",
  );
  assert.equal(
    data.canonical_pages.vocal_comping_research,
    "https://sunofriend.com/research/vocal-comping/",
  );
  assert.equal(data.canonical_pages.contact, "https://sunofriend.com/contact/");
  assert.equal(data.canonical_pages.privacy, "https://sunofriend.com/privacy/");
  assert.equal(data.contact.email, "hello@sunofriend.com");
  assert.equal(data.contact.accepts_audio_attachments, false);
  assert.equal(data.newcomer_routes.length, 4);
  assert.match(data.newcomer_routes[0].action, /sunofriend-separate/);
  assert.match(data.newcomer_routes[1].action, /sunofriend create/);
  assert.equal(data.advanced_capabilities.length >= 6, true);
});

test("keeps public discovery and the AWS boundary explicit", async () => {
  const [
    page,
    layout,
    template,
    domainTemplate,
    deployScript,
    robots,
    sitemap,
    missingPage,
    awsMissingPage,
  ] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../infra/site.yaml", import.meta.url), "utf8"),
    readFile(new URL("../infra/domain-zone.yaml", import.meta.url), "utf8"),
    readFile(new URL("../scripts/deploy-aws.sh", import.meta.url), "utf8"),
    readFile(new URL("../public/robots.txt", import.meta.url), "utf8"),
    readFile(new URL("../public/sitemap.xml", import.meta.url), "utf8"),
    readFile(new URL("../app/not-found.tsx", import.meta.url), "utf8"),
    readFile(new URL("../out/404.html", import.meta.url), "utf8"),
  ]);

  assert.match(page, /This website never/);
  assert.match(page, /public local alpha defaults to broad vocals/);
  assert.match(page, /not waveform reconstruction/);
  assert.match(page, /SoftwareApplication/);
  assert.match(layout, /publisher: "Unsigned Media Ltd"/);
  assert.match(layout, /openGraph/);
  assert.match(layout, /\/og\.(png|jpg)/);
  assert.match(layout, /icon: "\/favicon\.ico"/);
  assert.match(layout, /apple: "\/apple-touch-icon\.png"/);
  assert.match(robots, /Allow: \//);
  assert.match(robots, /sunofriend\.com\/sitemap\.xml/);
  assert.match(sitemap, /sunofriend\.com\/for-agents/);
  assert.match(sitemap, /sunofriend\.com\/research\/separation/);
  assert.match(sitemap, /sunofriend\.com\/research\/vocal-comping/);
  assert.match(sitemap, /sunofriend\.com\/stems/);
  assert.match(sitemap, /sunofriend\.com\/glossary/);
  assert.match(sitemap, /sunofriend\.com\/contact/);
  assert.match(sitemap, /sunofriend\.com\/privacy/);
  assert.match(sitemap, /sunofriend\.com\/llms\.txt/);
  assert.match(domainTemplate, /RootValidationRecordName/);
  assert.match(domainTemplate, /AlternateValidationRecordName/);
  assert.match(domainTemplate, /mx\.hover\.com\.cust\.hostedemail\.com/);
  assert.match(domainTemplate, /include:amazonses\.com/);
  assert.match(domainTemplate, /v=DMARC1; p=none/);
  assert.match(domainTemplate, /feedback-smtp\.eu-west-2\.amazonses\.com/);
  assert.match(domainTemplate, /_domainkey/);
  assert.match(template, /AWS::CloudFront::Distribution/);
  assert.match(template, /AWS::CloudFront::Function/);
  assert.match(template, /EventType: viewer-request/);
  assert.match(
    template,
    /CleanRouteFunction\.FunctionMetadata\.FunctionARN/,
  );
  assert.match(template, /AWS::CloudFront::OriginAccessControl/);
  assert.match(template, /statusCode: 301/);
  assert.match(template, /BlockPublicAcls: true/);
  assert.match(template, /SSEAlgorithm: AES256/);
  assert.match(template, /AlternateDomainName/);
  const forbiddenResponse = cloudFrontErrorBlock(template, 403);
  const missingResponse = cloudFrontErrorBlock(template, 404);
  assert.match(forbiddenResponse, /ResponseCode: 404/);
  assert.match(forbiddenResponse, /ResponsePagePath: \/404\.html/);
  assert.doesNotMatch(forbiddenResponse, /ErrorCode: 404/);
  assert.match(missingResponse, /ResponseCode: 404/);
  assert.match(missingResponse, /ResponsePagePath: \/404\.html/);
  assert.doesNotMatch(missingResponse, /ErrorCode: 403/);
  assert.match(missingPage, /This page is silent/);
  assert.match(missingPage, /href="\/stems\/"/);
  assert.match(awsMissingPage, /This page is silent/);
  assert.match(awsMissingPage, /SUNOFRIEND \/ 404/);
  assert.match(awsMissingPage, /class="not-found-page"/);
  assert.match(domainTemplate, /AWS::Route53::HostedZone/);
  assert.match(deployScript, /NEXT_PUBLIC_SITE_URL/);
  assert.match(deployScript, /out\/404\.html/);
  assert.ok(
    deployScript.indexOf("npm run build:aws") <
      deployScript.indexOf("aws cloudformation deploy"),
    "the static 404 must be built before CloudFormation enables its mapping",
  );
  assert.match(deployScript, /cloudfront create-invalidation/);
});
