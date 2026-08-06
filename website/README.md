# Sunofriend launch site

This is the public, serverless launch site for Sunofriend. Its main page is a
plain-language route for musicians: install the official Sunofriend skill
first, let a skills-aware local coding agent guide setup, then choose existing
stems, help obtaining stems or the no-private-audio worked demo. Codex has the
copy-ready route, while Claude Code, Antigravity and other capable agents can
use their native skill mechanism or read SKILL.md directly. It links to
listening examples and asks every user for feedback.

The public strapline is **Listen deeper. Create further.** The name is taken
from Hindi **सुनो** (*suno*), “listen.” Sunofriend is an independent Unsigned
Media Ltd project and is not related to or affiliated with Suno Inc. The
canonical copy and visual rules live in the repository
[`BRAND.md`](../BRAND.md).

The website and the music engine have deliberately different boundaries:

- this website is a static build served from private Amazon S3 through
  CloudFront;
- private contact arrives at `hello@sunofriend.com` through Hover forwarding,
  and authenticated replies are sent through Amazon SES from Gmail;
- first-song and compatibility feedback goes to the repository's explicit
  GitHub issue forms; and
- Sunofriend audio processing remains local. The site has no stem upload,
  account, database or music-processing API.

The application has only been tested on a MacBook so far. The public copy does
not claim verified Windows or Linux support; it explicitly asks people who try
either platform to share what worked or failed through the existing
compatibility form so SKILL.md and the setup guidance can be improved.

Agent discovery has its own public surfaces so the musician page does not need
to carry every technical detail:

- `/for-agents` explains recognition, onboarding and the Simple/Studio boundary;
- `/llms.txt` is the concise text discovery document;
- `/agent-capabilities.json` is the versioned machine-readable contract;
- `/research/separation/` publishes the bounded private experiment status,
  open gates and existing feedback routes without exposing audio or a product
  separator;
- `/demo` explains how to run the copyright-safe synthetic stem demo through
  the normal automatic MIDI/WAV/ZIP path and includes a listening/worked-output
  tour; and
- `/stems` explains what stems are, why one stem can contain several
  instruments, where authorised parts may come from, and the privacy and rights
  boundaries of independent local and cloud providers;
- `/glossary` shares the plain-language definitions used by the musician and
  agent pages;
- `robots.txt`, `sitemap.xml` and JSON-LD metadata make those routes discoverable.

Provider links are currently neutral ordinary links. There is no current
affiliate relationship, no provider is ranked as best for downstream MIDI, and
the site keeps the current product boundary explicit: synchronized top-level
WAV stems remain the input to complete song conversion. The local
`source-import-folder` CLI can inspect and prepare 2–64 already-separated
supported audio parts as one fresh canonical WAV project for Create, Simple or
Studio. It compares available recorded-origin evidence but does not separate,
shift, pad, stretch, normalize or align audio, prove a downbeat or create MIDI.
The narrower `source-import` command preserves one standalone asset.

The agent pages explicitly distinguish a coding agent with local workspace
access from a standard ChatGPT conversation. They do not claim that a normal
web chat can run commands or inspect local files.

The newcomer copy uses a two-turn handoff. The copy-ready Codex route invokes
`$skill-installer`, installs only the skill and stops, then invokes
`$sunofriend` in turn two. Other agents should perform the same boundaries
through their native skill mechanism. A new app installation has two further
change boundaries: prepare only the source, then review its exact commit before
separately approving dependencies and audio assets for that unchanged commit.

## Local preview

```bash
npm install
npm run dev
```

Open `http://localhost:3000`.

## Validate both builds

```bash
npm run build
npm run build:aws
npm test
```

`npm run build` validates the normal Sites-compatible worker build.
`npm run build:aws` creates the static export in `out/`.
The test command validates both builds, including the generated `out/404.html`.

## Deploy to AWS

The deployment uses CloudFormation to create:

- one encrypted, versioned, private S3 bucket;
- one CloudFront distribution with Origin Access Control;
- one viewer-request function that maps clean routes such as `/demo/` to their
  generated static `index.html` files;
- a branded `/404.html` response for missing or inaccessible objects, retaining
  an HTTP 404 status rather than silently serving the homepage;
- HTTPS, compression and security headers; and
- optional Route 53 records for a custom domain.

With AWS CLI credentials configured:

```bash
npm run deploy:aws
```

The deployment script completes and validates the static export, including its
branded `404.html`, before it updates the CloudFront error mapping. If a new
CloudFront-only URL is allocated, it rebuilds metadata for that final URL before
uploading the same validated export.

The default stack name is `sunofriend-site` in `eu-west-2`. Override them when
needed:

```bash
STACK_NAME=sunofriend-launch \
AWS_REGION=eu-west-2 \
npm run deploy:aws
```

For a custom domain, create or import its ACM certificate in `us-east-1`, then
provide both the root and `www` names:

```bash
DOMAIN_NAME=sunofriend.example.com \
ALTERNATE_DOMAIN_NAME=www.sunofriend.example.com \
CERTIFICATE_ARN=arn:aws:acm:us-east-1:000000000000:certificate/example \
npm run deploy:aws
```

`infra/domain-zone.yaml` is the optional Route 53 authority for an apex domain.
It creates A and AAAA alias records for the root and `www` while preserving the
Hover inbound-mail MX record and both ACM validation CNAMEs for certificate
renewal.
After the validation CNAMEs have been added at the current DNS provider and the
certificate is issued:

```bash
CERTIFICATE_ARN=arn:aws:acm:us-east-1:000000000000:certificate/example \
npm run activate:domain
```

The command updates CloudFront first, then creates the ready-to-switch Route 53
zone and prints its four authoritative name servers. Change the registrar's
name servers only after checking that complete output.

The stack retains the S3 bucket if the CloudFormation stack is deleted, so a
mistaken teardown does not erase the published files. AWS charges for stored
objects, CloudFront delivery, DNS and certificate-related services according
to the account's plan and traffic.
