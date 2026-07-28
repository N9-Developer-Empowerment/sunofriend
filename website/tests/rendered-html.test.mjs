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

test("rewrites clean website routes to their static index files", async () => {
  const handler = await loadCleanRouteHandler();
  const rewrite = (uri) => handler({ request: { uri } }).uri;

  assert.equal(rewrite("/"), "/index.html");
  assert.equal(rewrite("/demo"), "/demo/index.html");
  assert.equal(rewrite("/demo/"), "/demo/index.html");
  assert.equal(rewrite("/for-agents"), "/for-agents/index.html");
  assert.equal(rewrite("/for-agents/"), "/for-agents/index.html");
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
  assert.match(html, /I WANT THE DEMO/);
  assert.match(html, /Codex with local workspace access/);
  assert.match(html, /normal ChatGPT conversation/);
  assert.match(html, /automatic and unreviewed/);
  assert.match(html, /Hear Out of Place|Out of Place/);
  assert.match(html, /SoftwareApplication/);
  assert.match(html, /Unsigned Media Ltd/);
  assert.match(html, /not related to or affiliated/);
  assert.doesNotMatch(html, /brew install|git clone/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton|Starter Project/);
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
  assert.match(html, /not related to or affiliated/);
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
  ] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../infra/site.yaml", import.meta.url), "utf8"),
    readFile(new URL("../infra/domain-zone.yaml", import.meta.url), "utf8"),
    readFile(new URL("../scripts/deploy-aws.sh", import.meta.url), "utf8"),
    readFile(new URL("../public/robots.txt", import.meta.url), "utf8"),
    readFile(new URL("../public/sitemap.xml", import.meta.url), "utf8"),
  ]);

  assert.match(page, /This website never/);
  assert.match(page, /does not separate/);
  assert.match(page, /not waveform reconstruction/);
  assert.match(page, /SoftwareApplication/);
  assert.match(layout, /publisher: "Unsigned Media Ltd"/);
  assert.match(layout, /openGraph/);
  assert.match(layout, /\/og\.png/);
  assert.match(robots, /Allow: \//);
  assert.match(robots, /sunofriend\.com\/sitemap\.xml/);
  assert.match(sitemap, /sunofriend\.com\/for-agents/);
  assert.match(sitemap, /sunofriend\.com\/llms\.txt/);
  assert.match(domainTemplate, /RootValidationRecordName/);
  assert.match(domainTemplate, /AlternateValidationRecordName/);
  assert.match(domainTemplate, /mx\.hover\.com\.cust\.hostedemail\.com/);
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
  assert.match(domainTemplate, /AWS::Route53::HostedZone/);
  assert.match(deployScript, /NEXT_PUBLIC_SITE_URL/);
  assert.match(deployScript, /cloudfront create-invalidation/);
});
