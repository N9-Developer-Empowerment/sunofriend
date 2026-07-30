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
  assert.match(html, /Let Codex guide the setup/);
  assert.match(html, /Start with the skill/);
  assert.match(html, /INSTALL THE GUIDE BEFORE THE TOOL/);
  assert.match(html, /TURN 1 \/ INSTALL THE SKILL/);
  assert.match(html, /Use \$skill-installer/);
  assert.match(html, /Do not install the Sunofriend app/);
  assert.match(html, /TURN 2 \/ USE SUNOFRIEND/);
  assert.match(html, /Use \$sunofriend/);
  assert.match(html, /Do not clone the repository first/);
  assert.match(html, /restart Codex once/);
  assert.match(html, /I HAVE STEMS/);
  assert.match(html, /I NEED STEMS/);
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
  assert.match(html, /Install and read the official skill/);
  assert.match(html, /Stop after confirming the skill is available/);
  assert.match(html, /\$skill-installer/);
  assert.match(html, /\$sunofriend/);
  assert.match(html, /standard ChatGPT conversation/i);
  assert.match(html, /Offer three human routes/);
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
});

test("explains stems, neutral providers, privacy and the current boundary", async () => {
  const response = await render("/stems/");
  assert.equal(response.status, 200);
  const html = await response.text();

  assert.match(html, /BEGINNER STEM GUIDE/);
  assert.match(html, /A stem is <strong>not necessarily one instrument/);
  assert.match(html, /Bring separate audio parts/);
  assert.match(html, /sunofriend source-doctor/);
  assert.match(
    html,
    /sunofriend source-import-folder SOURCE_FOLDER --out-dir FRESH/,
  );
  assert.match(html, /does not shift, pad, stretch, normalize or align/);
  assert.match(html, /replans the current files/);
  assert.match(html, /accept-unconfirmed-origin/);
  assert.match(html, /Do not map an observed part to/);
  assert.match(html, /does not yet separate one finished song into stems/);
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
  assert.match(text, /Install the official skill/);
  assert.match(text, /standard ChatGPT conversation/i);
  assert.match(text, /\$skill-installer/);
  assert.match(text, /Confirm the skill is available, then stop/);
  assert.match(text, /In a second turn, explicitly use `\$sunofriend`/);
  assert.match(text, /two-stage bootstrap/);
  assert.match(text, /exact 40-character commit/);
  assert.match(text, /exact published production primary/);
  assert.match(text, /sunofriend create PROJECT --out-dir FRESH/);
  assert.match(text, /sunofriend demo --out-dir FRESH/);
  assert.match(text, /copyright-safe synthetic stems/);
  assert.match(text, /not exact waveform reconstruction/);
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
  assert.equal(data.boundaries.stem_separation, false);
  assert.equal(data.boundaries.rights_required, true);
  assert.equal(data.stem_inputs.built_in_full_mix_separation_available, false);
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
  assert.equal(data.canonical_pages.contact, "https://sunofriend.com/contact/");
  assert.equal(data.canonical_pages.privacy, "https://sunofriend.com/privacy/");
  assert.equal(data.contact.email, "hello@sunofriend.com");
  assert.equal(data.contact.accepts_audio_attachments, false);
  assert.equal(data.newcomer_routes.length, 3);
  assert.match(data.newcomer_routes[0].action, /sunofriend create/);
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
  assert.match(page, /does not (?:yet )?separate/);
  assert.match(page, /not waveform reconstruction/);
  assert.match(page, /SoftwareApplication/);
  assert.match(layout, /publisher: "Unsigned Media Ltd"/);
  assert.match(layout, /openGraph/);
  assert.match(layout, /\/og\.png/);
  assert.match(robots, /Allow: \//);
  assert.match(robots, /sunofriend\.com\/sitemap\.xml/);
  assert.match(sitemap, /sunofriend\.com\/for-agents/);
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
