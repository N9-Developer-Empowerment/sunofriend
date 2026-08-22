# Dry vocal comp renderer

Status: first deterministic product slice, covered by synthetic contract tests
and exercised with an owner-only, technically verified private excerpt. Private
audio and review artifacts are not retained in the repository.

## What it does

The renderer turns explicit human phrase choices into one playable dry WAV. It
also writes an exact frame edit/join map, a technical receipt and a local
review page. The result remains `complete_unreviewed_uncorrected`: opening or
playing the page is not a review decision.

It uses no model and performs no training. It does not resample, change channel
layout, tune pitch, move or stretch timing, trim gain, normalise or limit.
Sources and decisions are revalidated by their exact hashes before rendering.

Rendering accepts only `vocal-comp-source-map.v2`. It embeds every complete
canonical phrase-decision document and must exactly reproduce all projected
segments when revalidated against the Musical State. Existing v1 maps remain
valid non-rendering evidence, but cannot be promoted or silently interpreted
as render authority.

## Honest render scopes

`phrase_only` renders exactly one reviewed phrase window. Output frame zero is
the start of that window, while the edit map retains its original song-frame
start and end. This is the only honest route for the current one-phrase pilot;
it cannot create a mostly silent full-length file and call it a whole-song
comp.

`reviewed_phrase_excerpt` renders every phrase in a bounded reviewed Musical
State from the first phrase start through the last phrase end. It requires an
explicit source decision for every phrase, preserves reviewed gaps, and retains
the original song-frame origin in the edit map. It is an excerpt preview, never
a whole-song coverage claim. This is the honest scope for iterative verse or
multi-phrase work before the complete song roster exists.

`complete_state_timeline` additionally requires:

- the reviewed Musical State roster itself declares
  `reviewed_complete_intended_vocal_roster`;
- every phrase has one explicit `human_take` or `ai_fallback` source;
- no phrase is undecided, `record_again` or `no_acceptable_candidate`; and
- all selected sources share the exact output sample clock and channel layout.

Neither a rehashed roster field nor the source map grants that authority. A
separate `vocal-comp-dry-render-authorization.v0` owner artifact binds the exact
Musical State, source map, scope and optional phrase. Complete-timeline use must
explicitly confirm the complete intended roster. AI fallback needs a separate
confirmation in that same artifact because the base Musical State admits the
reference for phrasing and contour only, not for rendering.

The full horizon comes from the exact authorised reference vocal. Without a
reference, all admitted common-zero human takes must have identical geometry.
An AI fallback always resolves to that exact admitted reference.

## Join policy

The first policy is deliberately narrow:

- contiguous phrases from the same source continue at unity gain;
- a contiguous source switch is rejected until a separate reviewed join
  exists;
- a positive reviewed timeline gap remains explicit zero;
- bounded retained source handles may fade equal-power into and out of that
  zero region; and
- insufficient handles, overlaps, unsafe short gaps, non-finite audio or a
  full-scale peak fail closed.

The technical fades are not accepted joins. The review page labels them as
unreviewed, and playback creates no decision.

## Three-step local use

First create and retain the exact owner authorization. This example is
human-only; add `--confirm-authorised-ai-fallback-render` only when the exact
source map contains a deliberately chosen AI fallback:

```bash
PYTHONPATH=src python scripts/render-vocal-comp-dry.py \
  --musical-state /absolute/private/state/musical-state.json \
  --source-map /absolute/private/vocal-source-map.json \
  --render-scope phrase_only \
  --phrase-id phrase-001 \
  --authorize \
  --confirm-dry-uncorrected-scope \
  --authorization-out /absolute/private/dry-render-authorization.json
```

Then print and inspect the exact no-write plan:

```bash
PYTHONPATH=src python scripts/render-vocal-comp-dry.py \
  --musical-state /absolute/private/state/musical-state.json \
  --source-map /absolute/private/vocal-source-map.json \
  --render-authorization /absolute/private/dry-render-authorization.json \
  --render-scope phrase_only \
  --phrase-id phrase-001
```

Execution needs a fresh owner-only output parent, the exact plan SHA-256 and a
separate confirmation:

```bash
PYTHONPATH=src python scripts/render-vocal-comp-dry.py \
  --musical-state /absolute/private/state/musical-state.json \
  --source-map /absolute/private/vocal-source-map.json \
  --render-authorization /absolute/private/dry-render-authorization.json \
  --render-scope phrase_only \
  --phrase-id phrase-001 \
  --execute \
  --expected-plan-sha256 EXACT_HASH_FROM_PLAN \
  --confirm-dry-uncorrected-render \
  --out-dir /absolute/private/fresh-output
```

The package contains:

- `AUDIO/dry-vocal-phrase-preview.wav` for `phrase_only`;
- `AUDIO/dry-vocal-excerpt-preview.wav` for `reviewed_phrase_excerpt`; or
- `AUDIO/dry-vocal-comp.wav` for `complete_state_timeline`;
- `TECHNICAL/dry-vocal-edit-map.json`;
- `TECHNICAL/dry-vocal-render-receipt.json`; and
- `REVIEW/dry-vocal-comp-review.html`.

`verify_dry_vocal_comp_round_trip(output_dir, plan=..., result=...)` is the
read-only admission check for a returned package. It requires exactly those
four regular files under the fixed `AUDIO`, `TECHNICAL` and `REVIEW`
directories, rejects symlinks and undeclared files, and checks the actual file
sizes and SHA-256 values rather than trusting the receipt. It also decodes the
WAV to confirm PCM24 geometry, finite samples and no clipping, reparses and
reconstructs the edit map, and regenerates the exact review page. Its result is
technical verification only: it does not review the performance, accept a
join, select the comp for product use or create a training label.

## Tail comparison and usable-base review

If listening reveals a possible cut phrase tail, create a bounded A/B
comparison instead of silently changing the render. The `vocal_tail_review`
contract binds the canonical dry-render receipt, the exact control and
challenger audio hashes, the phrase and the frame-exact tail window. Candidate
A may be the unchanged dry excerpt; candidate A and B must still be different
audio identities.

An explicit tail choice requires the owner to have heard both A and B. A
separate usable-base review can then mark the chosen excerpt as suitable for
the next iteration. These review documents create no release, source
replacement, pitch or timing correction, training-label or model-promotion
authority. Playback alone creates nothing, and an ordinary usable-base choice
must never be imported as a pairwise ranker label.

## Current limitations

- There is no reviewed join-decision artifact yet, so contiguous source
  switches are blocked rather than guessed.
- Mono and stereo sources cannot be mixed in one render; silent channel
  duplication is still processing and is not inferred.
- Timeline gaps are treated as explicit non-phrase regions, not proven silence
  or breath classifications.
- The page records no review response yet.
- No pitch correction, timing correction, word-level splice, shared
  production processing, automatic selection or training label is created.

## Carrying a reviewed excerpt into the next phrase

`scripts/render-vocal-comp-continuation.py` is a narrower iterative bridge for
the case where an immutable multi-phrase excerpt is already explicitly marked
`usable_as_next_iteration_base`, while the newest Musical State contains one
new explicit browser-capture decision. It does not migrate the earlier phrase
decisions into the new state. Instead, its plan binds all of the following:

- the exact usable-base audio, review and render receipt;
- the newest recursively valid Musical State;
- the exact active phrase-decision document and selected capture hash;
- the reviewed phrase boundary and PCM frame geometry; and
- a no-fade boundary join that remains `not_reviewed`.

The plan is no-effect and cannot render. A separate owner authorization must
confirm one dry uncorrected preview, followed by a separate execution
confirmation bound to the exact plan SHA-256. The resulting local page exposes
the carried base, selected phrase and combined excerpt. Playback cannot accept
the join or update the usable base. The renderer performs exact PCM24 sample
concatenation only: no tuning, timing change, resampling, crossfade, gain
change, normalization, limiting, model inference or training.

After listening, `scripts/record-vocal-comp-continuation-review.py` binds an
explicit phrase-usability and join-quality decision to the exact plan, result
and continuation-audio hashes. Only the combination `phrase=usable` and
`join=natural` marks that exact dry excerpt usable as the next iteration base.
The review is written outside the immutable render package and grants no
release, correction, training-label or checkpoint-promotion authority.
