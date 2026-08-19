# Musical State foundation

Status: implementation note for the first shared foundation slice. The
canonical product and research direction remains the semantic Musical State,
vocal-comping and training plan. This note explains what this branch provides,
what kind of work it is, and what it does not authorise.

## Destination

Sunofriend is adding two repeatable features alongside track-to-MIDI:

1. **Vocal comping and replacement:** record and compare human attempts,
   retain AI where needed, assemble a reviewed human/AI vocal, and optionally
   apply bounded gentle correction.
2. **Identity-preserving remixing:** make an intentional arrangement or
   production change while retaining musical relationships that the owner
   recognises from the source.

MIDI remains a useful editable output and optional evidence source. It is not
the canonical representation for either feature. The shared foundation is a
versioned, time-aligned **Musical State** with explicit provenance,
uncertainty and review decisions.

## Nature-of-work labels

Every experiment and product step must identify its nature. A step can carry
more than one label.

| Label | Nature | Meaning |
| --- | --- | --- |
| **D** | Deterministic analysis or editing | Fixed rules read, compare, align, hash, assemble or render evidence. Learned weights are neither used nor changed. |
| **I** | Pretrained-model inference | Frozen existing weights analyse or generate audio. The model is used, not trained. |
| **T** | Model training | Optimisation changes weights using authorised examples and explicit labels. |
| **H** | Human musical review | The musician listens, records, accepts, rejects or identifies what must be retained. This is the musical authority. |

Stem separation, frozen representation extraction, forced alignment and pitch
tracking are **I**. Hashing, source maps, deterministic crossfades and manifest
validation are **D**. A ranker or adapter is **T** only when a training job
updates its weights. Listening and explicit decisions are **H**.

## Current implementation slice

This branch begins at **D+H** and establishes the boundary needed for later
**I** and **T** work:

- `sunofriend.musical-state.v0` binds canonical lyrics, a reviewed phrase
  timeline, immutable vocal takes and an optional reference by content hash;
- `sunofriend.vocal-performance-state.v2` records source identities and shared
  song coordinates without requiring MIDI or discrete target notes;
- the builder plans before writing, copies sources unchanged into a fresh
  owner-only package, and validates that the package can be reopened without
  its original absolute paths;
- the state declares correction, training, automatic selection and rendering
  inactive rather than implying that they happened; and
- `sunofriend.gpu-worker-request.v1` and
  `sunofriend.gpu-worker-result.v1` define a hash-bound handoff between the Mac
  integration host and the Windows RTX worker.

The GPU documents can specify a commit, authorised asset hashes, model
identity, windows, expected outputs, resource ceilings and stop rules. A
worker result may report technical completion, hashes, shapes, timings and
resource use. It cannot choose a vocal take, promote a representation, accept
a remix or approve a comp.

This slice does **not** install a model, run model inference, train weights,
select a take, correct a vocal, assemble a final comp, generate a remix or add
a public product command. Those capabilities require their own gates and
listening evidence.

The branch also contains an executable **C0 synthetic training canary**. Its
request is tied to one repository commit and a deterministic, non-private,
composition-grouped fixture. The CUDA worker must run a clean arm, a
shuffled-label control and a checkpoint/resume arm within fixed time, memory,
step and output ceilings. The result can prove that the training machinery is
reproducible; it cannot claim that a musical model has been trained or
validated. It uses the worker's already approved PyTorch runtime and neither
downloads nor installs anything.
The request fixes the process-local deterministic CuBLAS workspace before
PyTorch starts so the checkpoint comparison is meaningful on CUDA.
Windows resource receipts use a typed 64-bit process handle and record peak
working-set bytes through the modern or legacy documented system entry point.

## Privacy and authority

- Private audio remains local unless a separate approval names the exact
  assets, provider, purpose and retention terms.
- Git contains code, schemas and path-free manifests, not audio, credentials,
  checkpoints, generated media or private working notes.
- Absolute source paths are execution details and are excluded from portable
  state and GPU request/result documents.
- Original recordings are immutable. Repairs, selections, comp renders and
  corrections are separate derivatives with their own hashes.
- Known lyrics remain canonical. Transcription is uncertain phonetic evidence
  and cannot silently rewrite them.
- Scores and models may order what the musician compares; they never make the
  final musical choice.
- Playback count, dwell time and recording count are not training labels.
  Only explicit decisions may become labels.

## Use-in-anger loop from day one

Development is driven by authorised music every two to four days, not by one
large all-or-nothing research bet:

1. Choose one real phrase or an 8-16 bar remix excerpt and declare its musical
   purpose.
2. Build or reopen the exact hash-bound state and declare each operation as
   **D**, **I**, **T** or **H**.
3. Produce the smallest playable comparison, edit map, replacement, remix or
   honest retained failure possible with the current build.
4. Listen in context and record an explicit decision, rejection reason or
   `cannot tell` result.
5. Take that artifact into the next music session.
6. Let the observed musical bottleneck select the next smallest code,
   analysis, UI or training change.

Tracks should rotate so that the system does not overfit one voice, mix or
composition. A whole song is a coverage milestone, not the programme goal.

## Parallel delivery tracks

### Vocal comping and replacement

- **D+H:** open a reviewed phrase without MIDI, compare at least two immutable
  attempts, choose/reject/record again/keep AI, and export a source map.
- **D+I+H:** add uncertain word, phoneme, vocal-event, contour and signal-quality
  proposals while keeping dimensions separate and reviewable.
- **D+H:** assemble adjacent chosen regions with handles and join review, then
  extend the resumable browser workflow across the song.
- **D+I+H:** offer correction only on an explicitly chosen dry source, with
  consonants, breaths and unresolved tracker regions protected.

### Identity-preserving remixing

- **D+H:** name source identity anchors, permitted changes and hard negatives
  for a short authorised excerpt.
- **D+I+H:** compare deterministic evidence with frozen temporal
  representations and try one bounded region or role edit.
- **T+I+H:** admit a learned conditioner only after the smaller baselines work
  and a matched zero-state control shows that owner-recognised anchors survive.

### Parallel learning

Training begins in parallel as **C0 D+T+H**, but it begins small. The first job
proves hash-bound loading, song-disjoint splits, a reproducible optimisation
step, checkpoint resume, shuffled-label control and a non-authoritative result
manifest. It may deliberately overfit a tiny development set to test the
pipeline. That is not evidence that the model should enter the product.

The first plausible useful learner is a personal comparison-ordering head for
vocal attempts on the 12 GB RTX laptop. It can suggest which two attempts to
hear first only after it beats deterministic and frozen controls on held-out
songs. It still cannot select the source.

## Next gates

1. **Foundation gate — D:** focused tests must prove exact source hashing,
   path-free reopening, schema validation, tamper detection and GPU
   request/result binding.
2. **First vocal gate — D+H:** package one reviewed *The Heart Sees* phrase,
   reopen it without MIDI and export one explicit listen/record/choose outcome
   in full-song coordinates.
3. **First training gate — D+T+H:** run a tiny local/RTX experiment with an
   explicit label contract and shuffled-label control. Retain it as pipeline
   evidence only.
4. **First remix gate — D+H, then D+I+H:** define identity anchors for one short
   excerpt, render one bounded deterministic or frozen-model-assisted change,
   and compare it with the source in a real music session.
5. **Representation admission gate — D+I+H:** a frozen representation must add
   held-out, time-local, human-relevant value beyond transparent baselines
   before it becomes part of Musical State.
6. **Promotion and scale gate — T+I+H:** a learned model must beat appropriate
   controls on composition-disjoint evidence before product use, larger cloud
   training or generator fine-tuning is considered.

The programme can therefore deliver useful recording, comparison, source-map
and bounded-remix artifacts while model research proceeds. Failure at a model
gate narrows that research lane; it does not erase the deterministic product
value already delivered.

## Cycle 1 evidence — 19 August 2026

The first foundation and training-pipeline gates are now exercised rather than
only specified:

- **D:** Musical State and GPU worker contracts reject path leakage, source
  mutation, decision authority, render authority and request/result identity
  drift.
- **D+T:** the Windows RTX canary completed the clean and shuffled-control arms,
  reproduced an interrupted/resumed run exactly and returned technical-only
  evidence. This proves the bounded pipeline, not musical usefulness.
- **D+H:** the existing explicit *The Heart Sees* phrase-2 choice was imported
  as a hash-bound `human_take` decision for `take-001` and projected into an
  unrendered vocal source map. No pairwise label, join, pitch correction or
  comp was inferred from that choice.

The next vocal increment is a dedicated loopback “Vocal Session” page with a
whole-song phrase map, immutable pickups, owner-only resumable drafts and
append-only explicit actions. It reuses the current listening and recorder
evidence but does not extend the MIDI-oriented Workbench state.

The next remix increment remains **D+H**. It first asks the musician to name and
confirm an identity anchor for an authorised short excerpt, then creates a
one-variable deterministic control/challenger. The first edit uses a declared
stem-estimate delta against the exact source, so separation error cannot be
mistaken for source identity preservation. Model inference and training are
both off for that comparison.
