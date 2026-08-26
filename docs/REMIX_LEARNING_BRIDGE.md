# Remix learning bridge

Status: the evidence contracts, isolated MusicFM-FMA Windows runtime and
synthetic frozen-feature canary are implemented and independently verified.
The pinned model produced two byte-identical `[1, 50, 1024]` float32 feature
arrays at 25 Hz from generated audio on the RTX machine. This verifies the
frozen extractor, not a remix model: private-audio extraction, real labels and
real remix-ranker training remain gated. No trained remix model is admitted by
this document.

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

### Synthetic remix-ranker canary

`sunofriend.remix_ranker_canary` now implements the first remix-specific
training request, checkpoint and result contracts over 192 deterministic
synthetic pairs. It compares an untrained constant baseline, a transparent
six-feature linear ranker, a fixed-hidden-feature MLP, the same MLP resumed
from a canonical JSON checkpoint and a shuffled-label control. The independent
`sunofriend.remix_ranker_verifier` recomputes the complete result rather than
trusting reported metrics.

This is technical pipeline evidence only. The fixed request refuses real
snapshots, audio, MusicFM, network access and downloads; the result and
verification cannot promote a checkpoint, rank a product candidate or render
a remix. Run the local reference with
`scripts/run-remix-ranker-canary.py`. This does not remove any real-data or
frozen-feature admission gate below.

### Commit-bound frozen-feature training bridge

`sunofriend.remix_ranker_training` now adds the real-shaped contract that the
first canary intentionally omitted:

- `sunofriend.remix-frozen-feature-manifest.v0` binds every snapshot variant
  to one canonical JSON feature artifact by filename, byte count, SHA-256,
  shape, dtype and finite-value check. It also binds the frozen extractor,
  checkpoint, source revision, licence, layer, clock, pooling and feature
  dimension. Symlinks, missing rows, duplicate variants and path escapes are
  rejected.
- `sunofriend.remix-ranker-training-request.v1` binds the exact snapshot,
  feature manifest, repository commit and dependency-contract hash. It records
  composition/group/Musical-State/variant-family-disjoint split counts,
  constant and deterministic baselines, clean/resumed/shuffled arms and hard
  example, feature, step, byte, time, network, download and audio ceilings.
- `sunofriend.remix-ranker-training-result.v1` records baseline, validation,
  test and per-composition metrics, strict checkpoints, predictions, exact
  resume, left/right swap error, shuffled-label control and the offline
  resource receipt.
- `sunofriend.remix_ranker_training_verifier` rehashes every document and
  feature artifact, revalidates the split and checkpoint shapes, and
  recomputes predictions and metrics from the retained weights without
  optimisation.

The runnable fixture is deliberately a new synthetic snapshot schema. Its
labels say `synthetic_fixture_only`; it cannot be confused with an explicit
owner label. The real snapshot path is also exercised, but remains
`blocked_insufficient_real_evidence` and the runner refuses it. Even after the
count gate is met, a real request remains
`blocked_pending_explicit_real_training_authority` until a new exact private
training authorization exists.

Run the complete CPU-only contract fixture from a clean commit with:

```bash
COMMIT="$(git rev-parse HEAD)"
python3 scripts/create-remix-ranker-synthetic-training-fixture.py \
  --out-dir /absolute/fresh/remix-ranker-fixture \
  --repository-commit "$COMMIT" \
  --dependency-contract pyproject.toml
python3 scripts/run-remix-ranker-training.py \
  /absolute/fresh/remix-ranker-fixture/request.json \
  /absolute/fresh/remix-ranker-fixture/snapshot.json \
  /absolute/fresh/remix-ranker-fixture/feature-manifest.json \
  --feature-root /absolute/fresh/remix-ranker-fixture/features \
  --out /absolute/fresh/remix-ranker-fixture/result.json
python3 scripts/verify-remix-ranker-training.py \
  /absolute/fresh/remix-ranker-fixture/request.json \
  /absolute/fresh/remix-ranker-fixture/snapshot.json \
  /absolute/fresh/remix-ranker-fixture/feature-manifest.json \
  /absolute/fresh/remix-ranker-fixture/result.json \
  --feature-root /absolute/fresh/remix-ranker-fixture/features \
  --out /absolute/fresh/remix-ranker-fixture/verification.json
```

This does not import MusicFM, read audio, download anything, use a real label,
promote a checkpoint or change product audition ordering.

The separately authorised native-Windows setup handoff is
`scripts/setup-remix-musicfm-fma-windows.ps1`. It requires the retained pip
report, runtime-resolution receipt and a hash/size/URL asset manifest. It
refuses an existing destination, verifies all 26 wheels and the pinned
1,316,802,154-byte checkpoint, inspects wheel METADATA licence fields, creates
a fresh Python 3.11 venv and installs only from the verified cache with
`--no-index --no-deps`. Setup never imports MusicFM or loads the checkpoint.
Restricted loading and the synthetic feature canary remain a separate gate.
The repository-owned
`scripts/build-remix-musicfm-windows-install-lock.py` generates the exact
commit-bound install lock and asset manifest from the retained native Windows
resolver evidence. The PowerShell handoff calls that builder once and receives
the validated documents as an in-memory bundle before creating its fresh
destination or making a network request. It retains the bundle inside the new
runtime for later verification. Callers must execute the handoff directly and
must not reproduce its schema checks externally.

The checkpoint loader and CUDA synthetic-feature execution now sit behind the
separate `sunofriend.remix_musicfm_canary` facade. Framework-specific model
construction, strict state loading, the two exact compatibility migrations,
offline socket/environment guard and fixed synthetic signal are hidden in one
private loader module. The caller supplies one path-free request plus an
existing isolated runtime and receives independently verifiable feature and
result artifacts. The facade never downloads, opens private audio or starts
training.

This re-entry makes the retained Windows result reproducible from repository
code; it does not claim that the RTX run was repeated on this Mac or that the
runtime is a portable product capability. The request/result validators retain
the qualified 2-second, layer-7, `[1, 50, 1024]` float32, 25 Hz and exact-repeat
contract. See
[`MUSICFM_FMA_SYNTHETIC_CANARY.md`](MUSICFM_FMA_SYNTHETIC_CANARY.md).
Private audio, training execution, checkpoint promotion and product ranking
remain unauthorized.

### Private anchor confirmation

The vocal Musical State contract must not be padded with invented lyrics or
takes for remix work. `sunofriend.remix_source_state` therefore binds an owned,
bounded source excerpt, exact audio clock and owner-local training permission
without any vocal fields. `sunofriend.remix_source_anchor` adds versioned v1
identity and registry documents while leaving every legacy v0 document
byte-for-byte unchanged.

`sunofriend.remix_anchor_session` and
`scripts/private-remix-anchor-session.py` implement the missing first owner
action before variants are made. The calm loopback page presents one exact
source control as the primary musical truth. Synchronized vocal, drum, bass and
grouped-accompaniment estimates are optional diagnostic views: they help locate
melody, rhythm, harmony and structure but are never treated as original studio
tracks or as definitions of those musical functions. The owner hears the full
mix, chooses the diagnostic view where one primary anchor is clearest, names the
melody or motif, bass movement, harmony, groove or structural relationship that
must remain recognisable, marks its exact time window, and presses a separate
confirmation button. The page explicitly presents melody-first, then rhythm,
then compatible harmony as a useful pop starting point rather than an automatic
rule.

Playback and dwell create no evidence. Confirmation produces an owner-only,
hash-bound preflight document, remix identity state, owner registry and receipt.
It does not render a remix, create an A/B label, start training, promote a
checkpoint or select audio for the product. The next deterministic variant
preparation and A/B review therefore remain distinct, reviewable steps.

```text
python scripts/create-remix-source-state.py \
  --source-control SOURCE_CONTROL.wav \
  --state-id SOURCE_STATE_ID \
  --composition-id COMPOSITION_ID \
  --group-id RECORDING_GROUP_ID \
  --source-start-seconds SOURCE_START \
  --source-end-seconds SOURCE_END \
  --rights-category owned \
  --confirm-owner-local-training \
  --out REMIX_SOURCE_STATE.json

python scripts/private-remix-anchor-session.py \
  --project-state REMIX_SOURCE_STATE.json \
  --source-control SOURCE_CONTROL.wav \
  --separation-estimate TARGET_ESTIMATE.wav \
  --source-estimate-id TARGET_ESTIMATE_ID \
  --estimated-role "grouped other estimate" \
  --diagnostic-vocals VOCALS_ESTIMATE.wav \
  --diagnostic-drums DRUMS_ESTIMATE.wav \
  --diagnostic-bass BASS_ESTIMATE.wav \
  --state-dir PRIVATE_ANCHOR_STATE \
  --identity-state-id IDENTITY_STATE_ID \
  --registry-id OWNER_REGISTRY_ID
```

The server rechecks exact bytes before every playback, requires a same-origin
token for confirmation and refuses a second confirmation in the same session.

### Private A/B label collection

`sunofriend.remix_pairwise_session` and
`scripts/private-remix-pairwise-session.py` implement the first efficient
owner-label collection surface. The loopback-only page presents the unchanged
control and two challengers as neutral A/B versions. Their display order is
derived from a bound presentation seed; the saved label maps the display order
back to the exact request, result and audio hashes.

Playback and dwell create no evidence. Saving requires a separate explicit
confirmation that control, A and B were heard, an outcome, identity judgement
for both challengers, one to four bounded reasons, and explicit admission for
owner-local training. The resulting label is immutable and owner-only, but it
still has `training_eligible=false`, `selected_for_product=false` and no
training, checkpoint or release authority. The server verifies exact audio
bytes before every playback, accepts writes only from the same localhost
origin, and refuses a duplicate label for the same pair.

This interface removes a major collection bottleneck, but it does not fabricate
the missing corpus. A real session can open only after an owner registry,
controlled variant set, unchanged control and two exact challenger WAVs exist.
The launcher therefore requires the complete Musical State, owner registry,
identity state and variant set rather than trusting loose audio filenames:

```text
python scripts/private-remix-pairwise-session.py \
  --musical-state MUSICAL_STATE.json \
  --owner-registry OWNER_REGISTRY.json \
  --identity-state REMIX_IDENTITY.json \
  --variant-set CONTROLLED_VARIANTS.json \
  --control-audio SOURCE_CONTROL.wav \
  --variant-audio VARIANT_ID_A=CHALLENGER_A.wav \
  --variant-audio VARIANT_ID_B=CHALLENGER_B.wav \
  --state-dir PRIVATE_REVIEW_STATE
```

All documents and audio are revalidated before the page opens. The displayed
names remain only `Version A` and `Version B`; underlying variant IDs and
recipes are retained in evidence but do not bias the listening screen.

`sunofriend.remix_feature_contract` also creates a reproducible transparent
metadata baseline directly from the exact gain-envelope recipes. It binds six
finite operation features per variant—duration, point count, minimum and mean
gain delta, absolute delta area and maximum slope—to the snapshot, request,
result and output-audio hashes. This uses no model and decodes no audio. Its
readiness document names the remaining real-model blockers without granting
execution authority.

`sunofriend.remix_musicfm_feature_plan` binds the next learned-feature
boundary without opening audio or loading MusicFM. For every controlled
challenger it records the exact source control, separation estimate and
challenger identities, their shared audio clock, the owner anchor, a clamped
two-second context window and the composition-disjoint assignment. It fixes the
24 kHz mono, layer-7, 25 Hz, 1,024-dimensional float32 contract. Its v0
no-effects document deliberately still reports the feature-frame and runtime
gates as unclaimed: the qualified synthetic canary is separate evidence and
must be joined through a new admission artifact rather than silently changing
an older plan. The canary has measured 50 frames for its exact 2-second signal;
real case windows may have different frame counts and must bind their own
arrays.

Once an exact training snapshot and transparent-operation manifest exist, the
no-write plan is printed with `scripts/plan-remix-musicfm-features.py`. It
requires every upstream evidence document plus the resolver report, so a hash
projection alone cannot silently substitute a provider, checkpoint or runtime.

### Real dataset preparation facade

`sunofriend.remix_training_dataset` and
`scripts/prepare-remix-training-dataset.py` now remove the error-prone manual
assignment step. The caller supplies only the exact registries, controlled
variant sets, explicitly admitted owner labels and one `train`, `validation`
or `test` choice per opaque composition ID. The facade derives group,
Musical-State and variant-family identities from the sealed evidence, then
delegates to the canonical snapshot validator. Missing and unused composition
assignments fail closed.

The output embeds the canonical path-free snapshot and an exact shortfall
report for every provisional evidence threshold. It reads JSON only, writes
one fresh owner-only file and keeps private-audio extraction, training,
checkpoint promotion and product ordering unauthorized. It therefore makes a
growing real corpus mechanically ready for the later frozen-feature gate; it
does not make a short corpus trainable.

```bash
python3 scripts/prepare-remix-training-dataset.py \
  --snapshot-id OWNER_PILOT_ID \
  --owner-registry REGISTRY.json \
  --variant-set VARIANTS.json \
  --label LABEL.json \
  --split COMPOSITION_ID=train \
  --out FRESH_PRIVATE_PREPARATION.json
```

## Remaining evidence and implementation

The smallest honest training run is blocked by evidence, not GPU capacity.
Sunofriend still does not yet have:

1. a real owner-reviewed controlled variant set—the implemented contracts have
   only synthetic test fixtures so far; the new source-state/anchor v1 bridge
   deliberately stops before a v1 request or render;
2. controlled challenger sets for multiple owner-authorised compositions;
3. owner-confirmed registry entries and explicit pairwise labels across those
   compositions;
4. an exact real-audio feature manifest—the frozen MusicFM-FMA extractor has
   passed its synthetic Windows canary, but private owner audio has not yet been
   admitted or processed;
5. song- and composition-disjoint train, validation and test evidence that
   passes the provisional snapshot gate;
6. remix-specific baseline results over real held-out labels (the constant,
   deterministic heuristics, operation probe, frozen-feature probe, shuffled
   and resume controls currently run only on synthetic fixtures);
7. a separately reviewed real-data execution request: the v1 request validates
   and binds an explicit snapshot plus admitted feature manifest, but stays
   non-executable while the evidence gate is short and still requires fresh
   explicit authority after that gate passes; or
8. retained real-data checkpoints and predictions for the independent verifier
   to inspect. The verifier path exists, but current verified evidence remains
   synthetic and unpromoted.

The present `identity_relationship` and `musical_usefulness` fields are valuable
benchmark evidence, but they do not say that challenger A is preferred to
challenger B. They must remain unchanged.

### Review-only controlled comparison

`sunofriend.remix_comparison_session` provides a separate owner-only localhost
surface for the first source-state/anchor v1 controlled comparison. It accepts
the exact source state, anchor preflight, identity state, owner registry and
anchor confirmation without projecting them into the legacy Musical State v0
renderer. The original context and two exact candidate files are checked by
audio SHA-256, byte count, geometry and a stable owner-only hidden A/B mapping.

The musician hears the original, A and B through one shared playhead, then
explicitly records whether each was heard, the pairwise result, identity
retention, goal usefulness and one to four bounded reasons. A draft can be
resumed. Saved review revisions and reopen events are append-only. Neither
playback nor a saved review creates a pairwise training label, selects a product
result, authorises a render or starts training. Admitting review evidence to the
learning contracts remains a later, separate and explicit action.

The local launch surface is `scripts/private-remix-comparison-session.py`. The
current tests use generated tones only; the module does not render or discover
private audio.

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

`sunofriend.remix-ranker-training-request.v1` binds:

- dataset snapshot and feature-manifest hashes;
- repository revision and exact dependency/runtime-contract hash;
- architecture, seed, optimizer, loss, steps/epochs and resource ceilings;
- exact composition-disjoint split;
- clean and shuffled arms;
- checkpoint/resume schedule;
- network policy and allowed input/output roots; and
- output file names and maximum byte counts.

It grants bounded weight optimisation only. It grants no source mutation,
render, preference, selection, correction or product authority.

### Result

`sunofriend.remix-ranker-training-result.v1` binds:

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
3. **In parallel, D:** keep using the implemented registry, variant manifest,
   snapshot, real-dataset preparation and feature-manifest validators with
   synthetic fixtures and tamper tests.
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

## First audio-native real comparison

`sunofriend.remix_source_delta` bridges the dedicated remix source/anchor v1
evidence into a deterministic two-challenger listening experiment. The first
bounded operation edits only one exact drums estimate, treated explicitly as a
rhythm estimate rather than ground truth. The separately confirmed melodic
anchor estimate is not the direct edit target. Separator bleed may still make
the decomposition imperfect, so the owner must judge identity retention from
the complete mix.

Each challenger uses the transparent formula
`source + (gain - 1) * drums_estimate`. The source control remains a byte-exact
copy. Both variants share one frame clock and differ only in the declared gain
envelope. The renderer refuses clipping instead of hiding it with independent
normalization or limiting.

Planning has no audio effect. One exact private A/B render needs separate owner
authorization and a separate execution confirmation. Rendering produces no
review, preference, label, training authority, product selection or model
change. The existing review-only comparison page can then present original,
anonymous A and anonymous B on one playhead. A later explicit training label
remains a separate admission action.
