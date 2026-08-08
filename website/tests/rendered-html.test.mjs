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
    /FunctionCode: \|\n(?<code>(?: {8}.+(?:\n|$))+)/,
  );
  assert.ok(block?.groups?.code, "CloudFront function code was not found");
  const code = block.groups.code
    .split("\n")
    .map((line) => line.replace(/^ {8}/, ""))
    .join("\n");
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
  assert.match(html, /I NEED OTHER STEM OPTIONS/);
  assert.match(html, /What stems are and where to get them/);
  assert.match(html, /Open the glossary/);
  assert.match(html, /I WANT THE DEMO/);
  assert.match(html, /Codex with local workspace access/);
  assert.match(html, /normal ChatGPT conversation/);
  assert.match(html, /automatic and unreviewed/);
  assert.match(html, /Hear Out of Place|Out of Place/);
  assert.match(html, /SoftwareApplication/);
  assert.match(html, /Unsigned Media Ltd/);
  assert.match(html, /not related to or affiliated/);
  assert.match(html, /hello@sunofriend\.com/);
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
  assert.match(html, /\/research\/separation\//);
});

test("publishes honest separation research and existing feedback routes", async () => {
  const response = await render("/research/separation/");
  assert.equal(response.status, 200);
  const html = await response.text();

  assert.match(html, /PUBLIC EXPERIMENTAL PREVIEW · AUDIO STAYS LOCAL/);
  assert.match(html, /Try two stems—or opt in to four/);
  assert.match(html, /Finished mix to two broad stems/);
  assert.match(html, /not individual bass, keys, drums or guitar/);
  assert.match(html, /installed SCNet-large profile adds an explicit local vocals, drums, bass and grouped-other public opt-in preview/);
  assert.match(html, /complete listening checks reported no catastrophic defect/);
  assert.match(html, /Software checks evidence; people judge music/);
  assert.match(html, /How the feature was developed/);
  assert.match(html, /state one narrow musical or engineering question/);
  assert.match(html, /How to try the public alpha/);
  assert.match(html, /INSPECT SETUP/);
  assert.match(html, /sunofriend-separate doctor/);
  assert.match(html, /Four roles, one immutable profile, no hidden tuning loop/);
  assert.match(html, /OPT-IN STUDIO CHALLENGER/);
  assert.match(html, /other-refinement-v1/);
  assert.match(html, /Negative result retained; broader query next/);
  assert.match(html, /Apple-native htdemucs_6s MLX/);
  assert.match(html, /normalization passed under network denial/);
  assert.match(html, /five-song, ten-report review demonstrated neither/);
  assert.match(html, /keyboard_synth/);
  assert.match(html, /99,354,620 bytes/);
  assert.match(html, /Eight relevant modules/);
  assert.match(html, /zero network attempts/);
  assert.match(html, /strict weights-only loading/);
  assert.match(html, /separately approved synthetic inference plan/);
  assert.match(html, /local noncommercial research/);
  assert.match(html, /30 days or 10 valid submissions/);
  assert.match(html, /Help improve the next public slice/);
  assert.match(html, /SEPARATION_DEVELOPER_PREVIEW\.md/);
  assert.match(html, /rather than a Simple\/TUI button/);
  assert.match(html, /Do not attach private audio/);
  assert.match(html, /Send a first-song report/);
  assert.match(html, /Send text-only compatibility feedback/);
  assert.doesNotMatch(html, /model\.safetensors|separation-bakeoff|\/Users\//);
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
  assert.match(text, /public local alpha defaults to broad vocals/);
  assert.match(text, /sunofriend-separate doctor/);
  assert.match(text, /sunofriend-separate profiles --json/);
  assert.match(text, /immutable `demucs-mlx-htdemucs-v1` baseline/);
  assert.match(text, /FULL_STEM_SEPARATION_PLAN\.md/);
  assert.match(text, /Human listening decides usefulness/);
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
    "blocked_pending_separately_approved_synthetic_inference_plan",
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
  assert.match(layout, /\/og\.png/);
  assert.match(robots, /Allow: \//);
  assert.match(robots, /sunofriend\.com\/sitemap\.xml/);
  assert.match(sitemap, /sunofriend\.com\/for-agents/);
  assert.match(sitemap, /sunofriend\.com\/research\/separation/);
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
