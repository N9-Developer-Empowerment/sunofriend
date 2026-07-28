import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
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

test("server-renders the complete Sunofriend launch page", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>Sunofriend — Listen deeper\. Create further\.<\/title>/i);
  assert.match(html, /सुनो/);
  assert.match(html, /SUNO = LISTEN/);
  assert.match(html, /not related/);
  assert.match(html, /not affiliated/);
  assert.match(html, /Suno Inc\./);
  assert.match(html, /Your song has/);
  assert.match(html, /more than one answer/);
  assert.match(html, /Hear “Out of Place”/);
  assert.match(html, /Three moves\. One new version\./);
  assert.match(html, /If enough musicians bang on the door/);
  assert.match(html, /beginner-first-song\.yml/);
  assert.match(html, /daw-ai-compatibility\.yml/);
  assert.match(html, /Unsigned Media Ltd/);
  assert.match(html, /Company No\. 17046305/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton|Starter Project/);
});

test("keeps the public claims and AWS boundary explicit", async () => {
  const [page, layout, template, domainTemplate, deployScript] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../infra/site.yaml", import.meta.url), "utf8"),
    readFile(new URL("../infra/domain-zone.yaml", import.meta.url), "utf8"),
    readFile(new URL("../scripts/deploy-aws.sh", import.meta.url), "utf8"),
  ]);

  assert.match(page, /The current app processes your stems/);
  assert.match(page, /The music engine is still local/);
  assert.match(page, /does not promise exact waveform/);
  assert.match(page, /Unsigned Media Ltd/);
  assert.match(page, /Listen deeper/);
  assert.match(page, /Hindi imperative/);
  assert.match(page, /not related/);
  assert.match(page, /not affiliated/i);
  assert.match(layout, /publisher: "Unsigned Media Ltd"/);
  assert.match(layout, /openGraph/);
  assert.match(domainTemplate, /RootValidationRecordName/);
  assert.match(domainTemplate, /AlternateValidationRecordName/);
  assert.match(domainTemplate, /mx\.hover\.com\.cust\.hostedemail\.com/);
  assert.match(layout, /\/og\.png/);
  assert.match(template, /AWS::CloudFront::Distribution/);
  assert.match(template, /AWS::CloudFront::OriginAccessControl/);
  assert.match(template, /BlockPublicAcls: true/);
  assert.match(template, /SSEAlgorithm: AES256/);
  assert.match(template, /AlternateDomainName/);
  assert.match(domainTemplate, /mx\.hover\.com\.cust\.hostedemail\.com/);
  assert.match(domainTemplate, /AWS::Route53::HostedZone/);
  assert.match(deployScript, /NEXT_PUBLIC_SITE_URL/);
  assert.match(deployScript, /cloudfront create-invalidation/);
});
