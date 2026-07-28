# Sunofriend launch site

This is the public, serverless launch site for Sunofriend. Its main page is a
plain-language route for musicians: install the official Sunofriend skill
first, let Codex guide local setup, then choose existing stems, help obtaining
stems or the no-private-audio worked demo. It links to listening examples and
asks for the feedback that will decide whether a hosted conversion pilot
should be built.

The public strapline is **Listen deeper. Create further.** The name is taken
from Hindi **सुनो** (*suno*), “listen.” Sunofriend is an independent Unsigned
Media Ltd project and is not related to or affiliated with Suno Inc. The
canonical copy and visual rules live in the repository
[`BRAND.md`](../BRAND.md).

The website and the music engine have deliberately different boundaries:

- this website is a static build served from private Amazon S3 through
  CloudFront;
- first-song and compatibility feedback goes to the repository's explicit
  GitHub issue forms; and
- Sunofriend audio processing remains local. The site has no stem upload,
  account, database or music-processing API.

Agent discovery has its own public surfaces so the musician page does not need
to carry every technical detail:

- `/for-agents` explains recognition, onboarding and the Simple/Studio boundary;
- `/llms.txt` is the concise text discovery document;
- `/agent-capabilities.json` is the versioned machine-readable contract;
- `/demo` explains how to run the copyright-safe synthetic stem demo through
  the normal automatic MIDI/WAV/ZIP path and includes a listening/worked-output
  tour; and
- `robots.txt`, `sitemap.xml` and JSON-LD metadata make those routes discoverable.

The agent pages explicitly distinguish Codex with local workspace access from a
standard ChatGPT conversation. They do not claim that a normal web chat can run
commands or inspect files on a Mac.

The newcomer copy uses a reliable two-turn handoff. Turn one explicitly invokes
`$skill-installer`, installs only the skill and stops. Turn two explicitly
invokes `$sunofriend`, then inspects the Mac and offers stems, stem help or the
built-in demo. A new app installation has two further change boundaries:
prepare only the source, then review its exact commit before separately
approving dependencies and audio assets for that unchanged commit.

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

## Deploy to AWS

The deployment uses CloudFormation to create:

- one encrypted, versioned, private S3 bucket;
- one CloudFront distribution with Origin Access Control;
- HTTPS, compression and security headers; and
- optional Route 53 records for a custom domain.

With AWS CLI credentials configured:

```bash
npm run deploy:aws
```

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
Hover mailbox MX record and both ACM validation CNAMEs for certificate renewal.
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
