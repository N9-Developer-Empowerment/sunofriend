# Remix learning bridge

Status: evidence contracts, an exact MusicFM-FMA admission plan and static
checkpoint evidence are implemented. The Windows runtime plan now pins source
and direct wheel candidates, but the transitive dependency closure, runtime
admission and real training runner remain gated. No trained remix model is
admitted by this document.

## Decision

The first trained remix model should **not** generate or repaint audio. It
should be a small, owner-specific **controlled-delta comparison ranker** over
frozen features. Given the unchanged source and two deterministic,
single-variable gain-delta challengers, it predicts which comparison is most
worth hearing first. The existing deterministic renderer remains responsible
for audio, and the owner remains responsible for preference, identity and
product decisions.

This is real model training because optimisation changes the ranker's weights.
It is not a full remix generator, a source separator, a musical-identity oracle
or an automatic selector.

The narrow learner is useful even if later generative conditioning fails: it
can reduce audition time while each accepted remix remains reproducible from a
transparent delta recipe.

## What exists now

The current product slice is a sound deterministic foundation:

- `sunofriend.remix-identity-state.v0` binds one or more owner-named anchors to
  hash-identified separation estimates. Estimates remain estimates, not studio
  stems or ground truth.
- `sunofriend.bounded-remix-request.v0` permits exactly one attenuation-only
  gain envelope, from 0 to -12 dB, spanning the exact anchor and returning to
  unity at both edges.
- `sunofriend.remix-delta-comparison-plan.v0` binds the byte-exact source
  control and synchronized target estimate before rendering.
- `sunofriend.remix-delta-comparison-result.v0` binds the control, challenger,
  render recipe and private review page.
- `sunofriend.bounded-remix-review.v0` records explicit owner judgements for
  identity preservation and musical usefulness after both files were heard.

Those contracts correctly declare `model_used=false`, `training_used=false`,
`selected_for_product=false` and `training_eligible=false`. Playback creates no
decision. A single review must not be silently reinterpreted as a training
example.

There is not yet a private, owner-reviewed bounded remix comparison recorded in
this branch. The rejected ACE full-song outputs show that a generator can run;
they do not supply positive target labels or proof of source-preserving remix.

## Implemented evidence layer

`sunofriend.remix_learning_contract` now implements and validates:

- `sunofriend.remix-owner-anchor-registry.v0`;
- `sunofriend.remix-controlled-variant-set.v0`;
- `sunofriend.remix-pairwise-preference-label.v0`; and
- `sunofriend.remix-pairwise-training-snapshot.v0`.

The label is a new, explicit action. It binds the unchanged control, both full
request/result documents, distinct challenger identities, the owner registry,
the exact identity state and confirmation that control, left and right were
all heard. Local-training admission is separate from ordinary remix review.

The snapshot embeds and revalidates complete label, registry and variant-set
documents. Composition, group, Musical State and variant family are each
split-disjoint; reversed copies of the same unordered pair are rejected. Its
status remains `training_ineligible` and it grants no execution or checkpoint
promotion authority even if provisional count thresholds are reached.

`sunofriend.remix_feature_contract` also creates a reproducible transparent
metadata baseline directly from the exact gain-envelope recipes. It binds six
finite operation features per variant—duration, point count, minimum and mean
gain delta, absolute delta area and maximum slope—to the snapshot, request,
result and output-audio hashes. This uses no model and decodes no audio. Its
readiness document names the remaining real-model blockers without granting
execution authority.

`sunofriend.remix_musicfm_feature_plan` now binds the next learned-feature
boundary without opening audio or loading MusicFM. For every controlled
challenger it records the exact source control, separation estimate and
challenger identities, their shared audio clock, the owner anchor, a clamped
two-second context window and the composition-disjoint assignment. It fixes the
24 kHz mono, layer-7, 25 Hz, 1,024-dimensional float32 contract while leaving
feature-frame count explicitly unclaimed until the synthetic canary measures
it. The current plan remains blocked by the native Windows dependency closure,
isolated runtime, restricted load and synthetic feature-clock gates.

Once an exact training snapshot and transparent-operation manifest exist, the
no-write plan is printed with `scripts/plan-remix-musicfm-features.py`. It
requires every upstream evidence document plus the resolver report, so a hash
projection alone cannot silently substitute a provider, checkpoint or runtime.

## Remaining evidence and implementation

The smallest honest training run is blocked by evidence, not GPU capacity.
Sunofriend still does not yet have:

1. a real owner-reviewed controlled variant set—the implemented contracts have
   only synthetic test fixtures so far;
2. controlled challenger sets for multiple owner-authorised compositions;
3. owner-confirmed registry entries and explicit pairwise labels across those
   compositions;
4. an admitted frozen audio feature extractor and exact feature manifest (the
   transparent operation-feature baseline and MusicFM-FMA no-effects admission
   plan are now implemented; see `MUSICFM_FMA_FEATURE_ADMISSION.md`);
5. song- and composition-disjoint train, validation and test evidence that
   passes the provisional snapshot gate;
6. remix-specific deterministic, metadata-only, frozen-linear and shuffled
   baselines;
7. a bounded training request/result/checkpoint contract; or
8. an independent verifier that can reproduce split and metric claims without
   granting product authority.

The present `identity_relationship` and `musical_usefulness` fields are valuable
benchmark evidence, but they do not say that challenger A is preferred to
challenger B. They must remain unchanged.

## New evidence contracts

The following are proposed schemas. They should be implemented and tested
before any real remix label is declared training eligible.

### 1. Owner anchor registry

`sunofriend.remix-owner-anchor-registry.v0`

Each row binds:

- opaque `composition_id` and owner-confirmed composition relationship;
- opaque `group_id` for recordings, versions and derivatives that must never be
  split across partitions;
- exact Musical State document hash;
- exact source-control manifest hash;
- anchor ID, owner label and exact frame geometry;
- permitted change and identity invariants declared before comparison; and
- rights/privacy declaration for local training and, separately, cloud use.

One group belongs to exactly one composition. Alternate mixes, excerpts,
stems, remasters, covers derived from the same recording and deterministic
variants inherit that composition/group relationship; renaming is not a new
group.

### 2. Controlled variant manifest

`sunofriend.remix-controlled-variant-set.v0`

The manifest binds one unchanged control and at least two challengers. Every
challenger records:

- exact audio hash, byte count and geometry;
- comparison-plan, identity-state, request and result hashes;
- target estimate hash and estimated role;
- canonical attenuation envelope points;
- deterministic renderer name/version and source revision;
- `model_used=false`, `training_used=false`, and no automatic preference; and
- a `variant_family_id` shared only by variants of the same source, anchor and
  single permitted variable.

The first corpus should vary only envelope depth/shape over the same anchor.
EQ, timing, regeneration, pitch, separator choice and multiple-role changes
would confound the label and belong in later variant families.

### 3. Explicit pairwise label

`sunofriend.remix-pairwise-preference-label.v0`

This is a new explicit owner action, not a migration of an old review. It binds:

- registry, Musical State and variant-set document hashes;
- composition, group, anchor and variant-family IDs;
- unchanged control plus randomized left/right challenger audio hashes;
- confirmation that control, left and right were all heard;
- one outcome: `left`, `right`, `equivalent`, `neither` or `cannot_tell`;
- identity for each challenger: `preserved`, `partly_preserved`, `lost` or
  `cannot_tell`;
- reason codes such as `change_more_useful`, `identity_better_preserved`,
  `separation_artifact`, `change_inaudible`, `both_unusable` or
  `unable_to_compare`;
- optional path-free confidence bucket, never inferred from dwell/play count;
- explicit label authority and the randomization seed; and
- `selected_for_product=false` unless a separate product-selection action is
  later made.

`neither` and `cannot_tell` remain first-class outcomes. They must not be
coerced into a left/right label. A label may be reopened only by appending a
superseding decision that binds the prior label hash; history is never edited.

### 4. Dataset snapshot

`sunofriend.remix-pairwise-training-snapshot.v0`

The snapshot should embed and revalidate every full label document, not merely
copy projected outcomes. It binds:

- exact owner registry and controlled-variant-set manifests;
- exact Musical State manifests and source audio identities;
- composition/group/anchor/variant-family assignments;
- fixed `train`, `validation` and `test` partitions;
- an unordered-pair duplicate check;
- label and reason-code counts by partition;
- rights/privacy scope; and
- an evidence gate with no execution authority.

Composition, group, Musical State and variant family must each be disjoint
across partitions. All excerpts and deterministic variants of one composition
stay together. The registry, not filenames or automated similarity, is the
canonical source for this relationship.

For a first owner-specific pilot, use a transparent provisional evidence gate:

- at least 6 owner-authorised compositions;
- at least 12 groups;
- at least 4 train, 1 validation and 1 test composition; and
- enough explicit comparisons for every split and outcome reporting.

These are pipeline-entry minima, not evidence of generalisation. If only one
or two songs exist, continue collecting labels and run synthetic contract
canaries only.

### 5. Frozen feature manifest

`sunofriend.remix-frozen-feature-manifest.v0`

The learner must never load an unnamed feature array. For every item, bind:

- extractor name, exact weights/checkpoint hash, code revision and licence;
- layer/tensor name, sample rate and window/hop clock;
- preprocessing and channel policy;
- source-control, target-estimate and challenger audio hashes;
- feature file hash, shape, dtype and finite-value check;
- temporal crop/padding rules tied to the exact anchor frames; and
- `extractor_frozen=true` and `gradient_into_extractor=false`.

Start with one admitted independent audio/music encoder or an already-proven
ACE temporal tensor only after extraction is reproducible. Keep simple
deterministic features in parallel: delta-envelope statistics, anchor duration,
role, RMS/peak change, chroma/onset summaries and separation residual measures.
The feature choice is an evaluated boundary, not a permanent architecture
decision.

## First learner

Use a small pairwise logistic/MLP head in plain PyTorch on the 12 GB RTX laptop:

```text
score(variant) = head(
    pooled frozen source/anchor features,
    pooled target-estimate features,
    deterministic operation features,
    observed deterministic delta features
)

P(left preferred) = sigmoid(score(left) - score(right))
```

Train only on decisive `left`/`right` labels initially. Retain `equivalent`,
`neither` and `cannot_tell` for coverage, calibration and later abstention
heads; report their exclusion explicitly. Do not duplicate or flip examples in
a way that leaks the same pair across partitions.

The product effect, after promotion, is limited to **audition ordering**. The
model may say “hear B first”; it may not select B, alter audio, approve identity,
or authorize a comp/remix render.

## Required baselines and controls

Run every snapshot against:

1. constant/majority preference;
2. metadata-only operation features (depth, duration, role and envelope shape);
3. deterministic “smallest absolute change first” and “largest requested
   attenuation first” heuristics;
4. a frozen linear/logistic probe before any MLP;
5. the small learned head; and
6. a shuffled-label arm with the same split, steps and capacity.

Also test swapped left/right presentation. Predictions must invert without a
material metric change. Report per-composition outcomes and confidence
intervals; an aggregate score cannot hide one-song memorization.

The first technical canary should deliberately overfit a tiny synthetic set,
resume exactly from checkpoint and fail the shuffled control. It proves only
the machinery. The first real pilot should be retained as non-authoritative
unless the learned head beats constant, metadata, deterministic and frozen
linear baselines on the untouched test compositions and the clean-minus-
shuffled margin is positive under a predeclared threshold.

## Training request, result and verifier

### Request

`sunofriend.remix-ranker-training-request.v0` binds:

- dataset snapshot and feature-manifest hashes;
- repository revision and dependency-lock hash;
- architecture, seed, optimizer, loss, steps/epochs and resource ceilings;
- exact composition-disjoint split;
- clean and shuffled arms;
- checkpoint/resume schedule;
- network policy and allowed input/output roots; and
- output file names and maximum byte counts.

It grants bounded weight optimisation only. It grants no source mutation,
render, preference, selection, correction or product authority.

### Result

`sunofriend.remix-ranker-training-result.v0` binds:

- request, snapshot and feature-manifest hashes;
- clean/shuffled checkpoint and prediction hashes;
- uninterrupted/resumed parameter-equivalence evidence;
- loss curves and baseline metrics;
- validation/test and per-composition metrics;
- left/right swap test and excluded-outcome counts;
- runtime, peak resource and network-use receipt; and
- `product_admitted=false` by default.

### Independent verification

A separate CPU-capable verifier should:

- accept only the exact request/result/snapshot/manifests;
- re-hash all documents, features, checkpoints and predictions;
- rebuild the registry-based split and reject any overlap;
- load checkpoints weights-only with a strict architecture/shape allowlist;
- recompute all metrics and swapped-order checks;
- compare resumed and uninterrupted parameters; and
- write a path-free verification document without training or network access.

Verification proves the reported run; it does not make the ranker musically
useful or authorize product use.

## Delivery sequence alongside real music work

1. **Now, D+H:** render one owner-authorised bounded comparison, listen and
   retain its existing review unchanged.
2. **Next, D+H:** add a two-challenger randomized pairwise review and append one
   explicit label. Repeat as each new song is remixed; usable deterministic
   tracks continue to be delivered every few days.
3. **In parallel, D:** implement the registry, variant manifest, snapshot and
   feature-manifest validators with synthetic fixtures and tamper tests.
4. **In parallel, D+T:** run a synthetic clean/shuffled/resume canary locally
   and on the RTX worker. This is pipeline evidence only.
5. **After the evidence gate, D+I:** freeze and compare deterministic features,
   one admitted frozen encoder and a linear probe on song-disjoint labels.
6. **Then, D+T+I:** train the small comparison head and independently verify the
   returned evidence.
7. **Promotion, H:** expose audition ordering only after blind owner testing on
   untouched songs saves time without reducing identity preservation.
8. **Later research:** use the labelled benchmark to evaluate an identity
   representation or conditioner. Generator fine-tuning remains a separate,
   much later gate.

Cloud compute is unnecessary for this first learner. The laptop GPU is ample;
the hard resource is rights-cleared, composition-disjoint owner labels. Cloud
use should begin only if frozen feature extraction cannot fit locally and only
under a separate, explicit private-data approval and bounded request.

## Stop and rollback rules

- If the model does not beat metadata and deterministic controls, retain the
  deterministic product and improve evidence rather than scaling the model.
- If performance disappears on the held-out composition, treat it as
  memorization.
- If shuffled labels perform similarly, reject the objective or pipeline.
- If owner blind review finds audition ordering slower or less trustworthy,
  remove model ordering; no audio or owner decision needs rollback.
- If the registry is uncertain, the affected rows are training-ineligible.
- If a feature extractor licence, hash or preprocessing cannot be fixed, omit
  that feature rather than silently substituting it.

This bridge makes training real from the beginning while keeping each musical
deliverable useful without depending on the model research succeeding.
