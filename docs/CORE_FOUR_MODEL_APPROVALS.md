# Core-four model approvals and permission boundaries

This is the operational approval ledger for local vocals, drums, bass and
grouped-other model work. It separates model-maker evidence, project-owner
approval, song rights and public-service decisions so an absent email cannot
silently become an endless research blocker.

This is an engineering and release-policy record, not legal advice.

## Use the local approval page

Create a fresh self-contained form and open it with the current synthetic
listening bundle attached:

```bash
.venv/bin/python scripts/create-core-four-approval-page.py \
  --out /tmp/sunofriend-core-four-approval.html \
  --synthetic-root /tmp/sunofriend-scnet-synthetic-20260806-repeat2 \
  --open
```

The page makes no network requests, stores no browser draft and reads none of
the song paths typed into it. **Download approval JSON** saves a local file via
the browser. An incomplete form downloads a clearly labelled draft; a complete
form records the exact profile, evidence, approvals, boundaries, remaining
objective work and any intentionally withheld publication authority. The JSON
contains local paths but no audio or browser telemetry, so do not attach it to
a public issue.

Before acting on a downloaded file, validate it locally:

```bash
.venv/bin/python scripts/create-core-four-approval-page.py \
  --validate /absolute/path/to/sunofriend-core-four-approval-approved.json
```

Saving JSON grants no authority beyond its explicit fields and does not itself
run models, change profile status, commit code or deploy anything.

## Working interpretation

Publishing files on GitHub shows an intention to make them accessible, but the
repository licence—not publication alone—states the permissions. The pinned
SCNet source includes the MIT grant to use, copy, modify, publish, distribute,
sublicense and sell copies, subject to retaining its notice. The same official
repository README links the SCNet-large MUSDB checkpoint and presents it for
inference. No checkpoint-specific terms or contradictory restriction was
found.

For this local, user-installed preview, Sunofriend therefore accepts the pinned
MIT record plus the official README-linked checkpoint, exact hashes and
provenance as sufficient provisional evidence. A bespoke permission email is
not required unless contradictory terms appear. This project decision does not
pretend that a separate weights licence was found.

Hosted conversion is a later, different decision. It adds uploaded-audio
rights, privacy, retention, security, service terms, operational capacity and
possibly model redistribution questions. Those issues do not block local
offline testing today.

## Approvals already granted

| Boundary | Recorded approval | Result |
| --- | --- | --- |
| Provisional model evidence | Treat the official repository MIT metadata plus README-linked checkpoint as sufficient for preview unless audit finds a contradiction | Accepted 2026-08-06 |
| Evidence download | One evidence-only checkpoint download, hard-capped at 1 GiB | 168,848,417 bytes; SHA-256 `719e5abb8ed920305dad546ac3cd6fb0b1e9c3092d14ce21827bfc0423af3070` |
| Runtime and model setup | `scripts/setup-separation-core-four-scnet-macos.sh --install --accept-model-terms --accept-checkpoint-use` | Exact runtime installed; weights-only strict compatibility passed under network denial after the one allowed official `best_state` wrapper remediation |
| Local model execution | Carry on and test models that their makers published for sharing | Covers bounded, offline tests on Sunofriend's copyright-safe generated fixture |

These approvals do not authorize uploading private audio, selecting a model
winner automatically, using stems in Create/MIDI automatically or deploying a
hosted conversion service. The later bound approval separately authorized the
verified repository publication and website deployment.

## No further approval needed now

No maintainer email and no new model-terms override are required for:

- rerunning the exact installed SCNet profile on the generated mathematical
  fixture into a fresh local evidence root;
- hash, integrity, timing, memory and reconstruction checks;
- local inspection or listening to those generated test artifacts; or
- recording poor or mixed musical results as known limitations.

The exact local synthetic command is:

```bash
.venv/bin/python scripts/run-separation-core-four-scnet-synthetic.py \
  --out FRESH \
  --execute --confirm-synthetic
```

It performs no install, network model resolution, audio upload, public
activation, profile promotion or MIDI conversion.

## Remaining approvals and human actions

### Full-song canaries

For each of the three complete-song canaries, supply one local source path and
confirm one valid Sunofriend rights category: `owned`, `licensed`,
`authorised_private_use` or a documented applicable exception. This is song
rights confirmation, not a model-maker permission email. Keep every file local.

The three sources must be song-disjoint and cover vocal-forward,
dense/electronic and acoustic-or-mixed material. The project owner may approve
all three in one explicit instruction that names the paths and rights category.

### Internal catastrophic listen

One person must listen completely to each canary's source, four outputs and
reconstruction check, then record only whether output is mislabelled, corrupt,
silent across all roles or grossly mistimed. This is a review action, not a
minimum-quality approval. `cannot_tell` remains valid where applicable.

### Public opt-in activation

After the objective canaries pass, changing the immutable profile status from
`blocked` to `public_opt_in` is a project release decision. Poor usefulness,
bleed or artefacts must be disclosed but cannot veto the last technically
functioning profile. Publishing code, pushing a branch, opening a PR or
deploying the website still requires the normal requested Git/publication
scope; model-maker email is not a standing prerequisite.

### Downstream MIDI/Create use

Using a separated result in MIDI/Create requires a separate explicit user
choice after listening. Preview activation never opts a song into transcription
automatically.

### Hosted online conversion

Before offering uploads or server-side inference, perform a fresh legal,
privacy, security and operations review. Decide audio licences and consent,
retention/deletion, data location, subprocess isolation, abuse handling, model
redistribution versus server-only loading, attribution/notices, service terms
and capacity. This is the point where counsel or maintainer clarification may
be prudent; it is not needed to keep testing the local preview.

## When an email becomes necessary

No email is currently required. Pause and seek clarification only if a static
or later provenance audit finds a licence/hash contradiction, a separate
checkpoint restriction, revoked access, an attribution conflict, or a proposed
hosted/redistributed use not covered confidently by the evidence.

If that happens, ask the SCNet maintainer narrowly:

> Subject: SCNet-large checkpoint usage clarification for Sunofriend
>
> The official SCNet repository is MIT licensed and its README links the
> SCNet-large MUSDB checkpoint. Could you confirm whether that checkpoint is
> intended to be usable by end users for local inference under the repository's
> MIT terms, with the MIT notice retained? Separately, may an open-source app
> redistribute the exact checkpoint, and may a hosted service run inference
> without redistributing it? Please identify any checkpoint-specific terms or
> required attribution.

Do not wait for this optional broader clarification to continue exact local
user-installed testing while the pinned evidence remains non-contradictory.

## Current evidence state

Three identical-configuration full synthetic SCNet runs passed every technical
gate on the current 36 GB M3 Max development Mac:

- 60.0 seconds of stereo 44.1 kHz PCM24 input;
- 69.97, 70.20 and 71.18 seconds worker elapsed time;
- 6,581,846,016 to 6,719,586,304-byte peak RSS, below the 12 GiB ceiling;
- eight sequential 11-second forward passes, one seed-0 shift and 0.25 overlap;
- exact vocals, drums, bass and other files with matching clocks;
- identical hashes for all six persisted audio artifacts on every run;
- zero-LSB persisted reconstruction error on every run; and
- no network model resolution or audio upload.

Reference diagnostics also showed the synthetic vocal estimate was extremely
quiet and much of the vocal reference remained in grouped other. That is now a
known musical limitation. It does not reverse the technical pass or start a
tuning loop. The project owner approved this 36 GB M3 Max as the first verified
machine class. Three authorised song-disjoint canaries subsequently passed
every objective gate, and the required complete listens reported no
catastrophic defect. Other Apple-silicon classes, including 16 GiB machines,
remain accessible but unverified and resource-supervised.
