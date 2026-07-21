# Phase 5 local Studio learning and acceptance

Status: **Phase 5.9 tooling is ready; human evidence is pending.** A generated
page, an unanswered quiz or a successful ZIP integrity check is not an
acceptance pass.

This is the final local learning and human-check boundary before the first
read-only Phase 6 Clip Library increment. It is intentionally attached to one
exact downloaded GarageBand pack so that understanding, GarageBand behaviour
and usability evidence all refer to the same selected MIDI bytes.

## What the page does

Every successful Workbench **Build this exact pack** result now links to one
local, pack-pinned page. The sequence cannot be skipped:

1. **Interactive tutorial:** eight short screens explain Sunofriend's purpose,
   multi-process result space, human decisions, temporary audition controls,
   exact export basket, BPM/downbeat distinction, MIDI/instrument distinction,
   privacy boundary and Phase 6 boundary.
2. **Understanding quiz:** exactly 10 questions appear one at a time. No answer
   is selected initially. **Check answer** explains the choice, and all 10
   answers must be correct before the human checks unlock. The whole quiz can
   be retried; no clickstream, dwell time or failed-attempt telemetry is kept.
3. **Human check 1 of 2 — GarageBand pack:** set the exact displayed BPM,
   import every authoritative numbered MIDI file, choose playable patches,
   confirm drum/percussion routing where applicable, confirm the musical
   pickup/downbeat and listen at the beginning, middle and end for drift.
4. **Human check 2 of 2 — local usability:** explicitly confirm that the local
   project was intentionally chosen and authorised, then confirm that
   source/candidate comparison, explicit choice, arrangement audition,
   separate state, exact pack composition and restart behaviour are
   understandable without editing JSON.
5. **Private export:** download the reviewed JSON only after every item has an
   explicit `pass`, `issue` or `cannot_tell` answer and each check has the
   mechanically matching outcome.

The presentation teaches Sunofriend rather than a generic audio-to-MIDI app.
It explicitly preserves the product's main distinction: analytical,
specialist, AI and reviewed-repair processes remain separate alternatives,
and Sunofriend does not pretend that one score or model is a universal winner.

## Resolve the review

Keep the reviewed JSON and the ZIP local. Resolve the browser export against
the exact ZIP that was imported into GarageBand:

```bash
sunofriend garageband-pack-resolve \
  "/absolute/path/to/garageband_pack_acceptance.reviewed.json" \
  "/absolute/path/to/sunofriend-garageband-pack.zip" \
  --out "/absolute/fresh/path/phase5-acceptance-result.json"
```

For a previously downloaded pack that has no adjacent generated page, create
an equivalent fresh review first:

```bash
sunofriend garageband-pack-review \
  "/absolute/path/to/sunofriend-garageband-pack.zip" \
  --out-dir "/absolute/fresh/path/phase5-pack-review"
```

Open `garageband_pack_acceptance.html` in that directory, complete it, export
the reviewed JSON and use the resolve command above. Neither command requires
audio, ML, FluidSynth, a server or network access.

## What is verified automatically

The builder and resolver independently inspect the ZIP without extracting it.
They reject unsafe or duplicate archive paths, non-canonical generated names,
unexpected members or receipt fields, changed payload sizes or hashes,
inconsistent basket item identities, an inconsistent embedded receipt, missing
source opt-in, private paths or private notes in the embedded receipt, or a
claim that original MIDI was mutated. The resolver then rebuilds the neutral
review from those exact bytes, rejects any changed prompt or pinned evidence,
recomputes the 10/10 result and checks that both human outcomes match their
item answers. Inspect copied source/MIDI metadata and the README before sharing
outside the local workflow.

The path-free result has one of three statuses:

- `passed`: all 10 answers are correct and both human checks contain only
  explicit passes;
- `needs_changes`: at least one human item records an issue, even if another
  item is `cannot_tell`; otherwise
- `incomplete`: at least one human item records `cannot_tell`.

Free-text notes remain only in the private reviewed JSON. The result records
whether private notes existed but does not copy them or fingerprint the private
review file. Its `redacted_evidence_sha256` binds the choices after free-text
notes are blanked. The result remains local evidence, not publication consent.
`remaining_local_studio_acceptance_gates` describes only these two human
checks; the separate Phase 5.3 hybrid gates remain listed independently and
are never implied complete by this result.

## Downbeat boundary

Workbench starts all lanes at recorded zero, but recorded zero is not proof of
bar 1 beat 1. When the catalog has no confirmed downbeat, the reviewer must
still listen for the pickup/downbeat. A pass is then labelled
`reviewer-observation-only`; it does not create or pretend to verify a
hash-pinned downbeat value. A later explicit downbeat catalog contract can add
stronger machine-verifiable evidence without rewriting this review.

## Effects and phase boundary

Tutorial navigation, quiz answers, review items and resolution have zero
effect on MIDI, candidates, main/optional decisions, audition state, the Pack
Composer basket, rankings or defaults. Nothing is uploaded and no telemetry or
contribution event is recorded.

Only a resolver result with `status: "passed"` makes
`phase6_read_only_clip_entry_ready` true. It does not start Phase 6 code by
itself. It also leaves `explicit_hybrid_construction_ready` false: Phase 5.3
blind-choice and source-lineage evidence remain separate prerequisites for
hybrid construction, although they do not block read-only Clip browsing,
audition and exact export.
