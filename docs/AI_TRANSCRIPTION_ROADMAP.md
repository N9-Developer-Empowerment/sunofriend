# Sunofriend AI roadmap

Status: Phases 1 and 2 in progress
Started: 15 July 2026  
Scope: local-first AI assistance for transcription, review, instrument matching
and source-derived instruments

This is the working plan for a difficult, multi-week programme. It is intended
to make one measured piece of progress at a time without destabilising the
existing GarageBand-ready workflow. The roadmap is evidence-led: a model is
not integrated merely because it produces plausible MIDI. It must improve a
golden example, preserve timing and provenance, and remain useful in a
GarageBand A/B test.

## Programme goal

Make stems and vocals easier to turn into accurate, musical, editable MIDI and
useful playable instruments. AI supplies independent observations and ranked
alternatives. Sunofriend remains responsible for timing, evidence policy,
musical constraints, evaluation, provenance and handoff to GarageBand.

The intended flow is:

```text
source mix / stem / vocal
        |
        +--> existing Basic Pitch, pYIN and deterministic analysis
        +--> optional isolated AI backends
        |
        v
raw versioned candidates and confidence
        |
        v
beat, key, chord, repetition and source-evidence checks
        |
        v
ranked MIDI choices + uncertain passages + audible previews
        |
        v
human recognition/review in short phrases
        |
        v
GarageBand-ready MIDI, Instrument Bundle and durable provenance
```

## Principles and guardrails

- Work locally by default. No source audio is uploaded by an automatic command.
- Preserve the current `.venv` and deterministic CLI. Heavy models run through
  a separate Python 3.12 worker in `.venv-ai`.
- Never silently replace existing transcription evidence with model output.
- Retain raw candidates so consensus and later decoders can be reproduced.
- Keep `exact`, `repair` and `reconstruct` meanings intact.
- Model agreement increases confidence; it does not prove correctness.
- Keep model code licence, checkpoint licence and training-data notes separate.
- Do not bundle gated, non-commercial or custom-licensed weights in the
  Apache-2.0 repository.
- Make a model earn integration on golden clips before running it over every
  song.
- Treat GarageBand A/B listening as a required evaluation, not an anecdotal
  final check.

## Current programme status

| Phase | State | Outcome |
| --- | --- | --- |
| 1. AI Transcription Bake-off v1 | **In progress** | Independent local model candidates, common JSON, repeatable metrics and selection evidence |
| 2. Phrase Review v2 | **In progress** | Recognition-first correction using short candidates, hum/tap/contour guidance and repeated-phrase propagation |
| 3. Instrument Intelligence v2 | Planned | Learned sound matching, sample clustering, articulation and velocity layers, bleed rejection |
| 4. Cleanup and Neural Timbre Lab | Planned | Optional source cleanup and explicitly labelled neural timbre experiments |

## Phase 1: AI Transcription Bake-off v1

### Goals

1. Establish a modern local PyTorch runtime without changing the existing
   Basic Pitch environment.
2. Define one versioned, model-neutral candidate format for notes, confidence,
   instrument labels, warnings and raw artifacts.
3. Run each backend independently and preserve its untouched output.
4. Compare candidates with existing Sunofriend output and reviewed golden
   examples.
5. Decide separately whether a backend is useful for full mixes, individual
   pitched stems, drums, lead vocals or backing vocals.
6. Publish disagreement and uncertainty instead of forcing one answer.

### Non-goals

- Replacing `listen-all` or `vocal-melody` in one rewrite.
- Downloading every available checkpoint.
- Training a foundation model.
- Assuming a semantically plausible MIDI is accurately aligned.
- Uploading complete songs to an API.
- Making non-commercial model weights a required Sunofriend dependency.

### Candidate backends

| Backend | Initial purpose | Code licence | Checkpoint constraint | Phase 1 position |
| --- | --- | --- | --- | --- |
| Existing Sunofriend | Stable baseline | Apache-2.0 plus existing dependencies | Existing Basic Pitch model | Always run |
| MuScriptor | Full mix and per-instrument MIDI | MIT | CC-BY-NC-4.0, gated | First local challenger; optional personal/research worker |
| GAME | Vocal pitches and note boundaries | MIT | Official v1.0.3 small ONNX release; component hashes recorded | Implemented independent vocal challenger; local CPU worker |
| RMVPE | Vocal F0 under bleed/noise | MIT ONNX adapter; Apache-2.0 reference | MIT-labelled canonical ONNX at a pinned revision/hash | Implemented tracker, consensus evidence and boundary repair; retain as F0 oracle |
| PESTO | Lightweight vocal/instrument F0 | LGPL-3.0 | Pinned `mir-1k_g7` checkpoint/hash | Implemented independent optional worker; retain as vocal F0 oracle, reject for current bass golden |
| MT3 | Multi-instrument research comparison | Apache-2.0 | Large/brittle T5X environment | Rejected for Phase 1; MuScriptor covers the comparison without a second T5X stack |

### Deliverables

- Reproducible `.venv-ai` setup using `scripts/setup-ai-runtime.sh`.
- `sunofriend ai-doctor` JSON containing Python, PyTorch, MPS and backend
  readiness plus licence manifests.
- `sunofriend.ai-transcription-candidate.v1` request/note/candidate contract.
- One adapter per evaluated model, isolated from the core environment.
- Bake-off run directory containing configuration, raw model output, converted
  MIDI, evaluation, previews and exact model/checkpoint provenance.
- A comparison report covering objective metrics and GarageBand listening.
- A decision for each model: integrate, retain as optional oracle, investigate,
  or reject.

### Reproduce the isolated runtime

On Apple Silicon, install `uv` once and run the checked-in setup script:

```bash
brew install uv
scripts/setup-ai-runtime.sh
.venv/bin/sunofriend ai-doctor --require torch
.venv/bin/sunofriend ai-doctor --require muscriptor
scripts/setup-game-model.sh
.venv/bin/sunofriend ai-doctor --require game
scripts/setup-rmvpe-model.sh
.venv/bin/sunofriend ai-doctor --require rmvpe
scripts/setup-pesto-model.sh
.venv/bin/sunofriend ai-doctor --require pesto
```

The script uses Python 3.12 and installs the versions recorded in
`requirements-ai-macos.txt`. It installs MuScriptor's code but does not accept
its checkpoint licence, authenticate with Hugging Face or download model
weights. Those remain explicit, separately recorded steps before the first
audio experiment.

`scripts/setup-game-model.sh` is a separate, explicit network action. It pins
GAME tag `v1.0.3` at commit
`475a8ee781fe8cca980b3b12fbe6c80c768a813a`, verifies the official small ONNX
release ZIP SHA-256 and verifies all six extracted files. Normal diagnostics
and inference never download or update either the external checkout or model.

`scripts/setup-rmvpe-model.sh` separately downloads only the canonical
`rmvpe.onnx` from the pinned `lj1995/VoiceConversionWebUI` revision
`b2c8cae96e3b05de46d36c5ef9970ef6cbccafba` and verifies SHA-256
`5370e71ac80af8b4b7c793d27efd51fd8bf962de3a7ede0766dac0befa3660fd`.
The isolated package is pinned to `rmvpe-onnx==0.2.3`; normal inference rejects
URLs and receives the existing absolute model path.

Once the user has personally accepted a checkpoint's terms and placed it on
disk, the first challenger can be run without allowing an implicit download:

```bash
.venv/bin/sunofriend ai-doctor --require muscriptor-checkpoint
.venv/bin/sunofriend ai-transcribe \
  /absolute/path/to/excerpt.wav \
  --checkpoint /absolute/path/to/accepted/model.safetensors \
  --out-dir /absolute/path/to/work/ai-bakeoff/song-name \
  --bpm 119 \
  --start-seconds 30 \
  --end-seconds 45
```

The checkpoint must be an existing, absolute `.safetensors` path. Model names
and URLs are rejected before MuScriptor is imported. This preserves explicit
licence acceptance and ensures the checkpoint hash exists before inference.

### Bake-off artifact layout

The current Phase 1 runner creates a fresh, immutable directory per backend
invocation:

```text
work/ai-bakeoff/<song>/<run-id>/
├── run.started.json
├── run.json
├── request.json
├── candidate.raw.json
├── candidate.json
├── candidate.quality.json
├── candidate.mid
├── candidate.expression.json
├── candidate.expression.mid
├── rmvpe.frames.json              # RMVPE only: immutable 10 ms F0/confidence
├── worker.stdout.log
└── worker.stderr.log
```

`run.json` identifies operating system, Python, device, package versions,
model/checkpoint hash, licences, command, parameters, input hash, artifacts,
exit status and elapsed time. A failed or timed-out worker still produces the
final record and captured logs. Reusing a run ID is an error. Source paths may
be retained locally, but a later comparison report intended for Git must use
safe relative labels rather than private absolute paths. Preview, evaluation,
multi-backend comparison and listening-note layers can be added around these
per-backend records without changing the raw candidate.

### Golden material

Use short, representative, authorised excerpts before full songs:

- Lead vocal with obvious phrase boundaries and slides.
- Backing vocals with overlapping harmony.
- Walking or melodic bass.
- Layered keys containing melody and accompaniment.
- Kick/snare examples containing more than one timbre.
- Mixed `other_kit` or percussion with separator bleed.
- Sustained strings or pads.
- A deliberately quiet/no-evidence clip to measure false positives.

The existing Move Your Body and Lidl tests remain regression guards. Additional
private audio may be used as local golden material without being committed.

### Evaluation

Objective MIDI measures:

- note onset precision, recall and F1 at documented tolerances;
- pitch and pitch-class accuracy;
- octave-error rate;
- note-with-offset F1 and duration error;
- median and p95 absolute onset error;
- drift from the source over the complete excerpt;
- false positives during silence or non-target instrument activity;
- instrument-label leakage for multi-instrument output;
- tracker agreement, solo evidence and disputed duration.

Listening measures, scored per phrase:

- recognisable melody without the source vocal;
- correct rhythm and phrase start;
- source-like contour and octave;
- useful density rather than random detail;
- fit with the original stem in GarageBand;
- preference over the current Sunofriend result.

There is no universal pass threshold. A backend advances only when it improves
the relevant golden material without causing an unacceptable regression.

### Work sequence

#### Workstream A — runtime and contract

- [x] Preserve the Python 3.9 core environment.
- [x] Add isolated Python 3.12/PyTorch setup.
- [x] Add licence-aware backend manifests.
- [x] Add a versioned request/note/candidate contract.
- [x] Add runtime/backend diagnostics.
- [x] Add worker request/response invocation with timeouts and captured logs.
- [x] Add immutable run manifests and input/checkpoint hashing.

#### Workstream B — MuScriptor

- [x] Install code without downloading gated checkpoints.
- [x] Record explicit acceptance and checkpoint hash for the small model.
- [x] Test CPU and MPS support; do not assume MPS compatibility.
- [x] Adapt streamed note events into candidate v1 without adding velocity.
- [x] Test restricted instrument lists and isolated vocal/bass stems.
- [x] Test a full mix and quantify instrument-label leakage.
- [x] Recover velocity from source evidence after the raw candidate is saved.

#### Workstream C — vocal models

- [x] Install GAME in an external checkout and record its release bundle.
- [x] Adapt GAME pitches, boundaries and voiced/unvoiced evidence.
- [x] Test seeded GAME on lead and backing vocals and expose an opt-in variant.
- [x] Install/adapt RMVPE as a frame-level tracker.
- [x] Compare GAME, RMVPE, Basic Pitch and pYIN independently.
- [x] Add consensus only after raw per-model evaluation exists.
- [x] Test conservative Basic Pitch/GAME boundaries only on agreed pYIN/RMVPE F0.

#### Workstream D — evaluation and decisions

- [x] Create the bake-off runner and artifact layout.
- [x] Add synthetic protocol and failure tests.
- [x] Run the first 10–15-second vocal and bass clips.
- [x] Render neutral-instrument previews.
- [ ] Capture GarageBand listening scores.
- [x] Write the first local model decision record; publish after listening.

Optional close-out improvements are complete: PESTO has a pinned local worker
and three-role comparison; MuScriptor has keys, kick and strings comparisons;
all four AI backends pass a digital-silence no-false-note check; and MT3 has an
explicit Phase 1 rejection decision. See
[the Phase 1 close-out report](PHASE1_TRANSCRIPTION_BAKEOFF.md).

### Phase 1 completion criteria

Phase 1 is complete when:

1. At least one multi-instrument model and one vocal-specific model can be run
   reproducibly through the common contract.
2. Every result contains raw output, MIDI, evaluation and model provenance.
3. Failures and missing checkpoints degrade safely without affecting existing
   commands.
4. At least three representative stem types and lead vocals have measured
   comparisons.
5. GarageBand A/B notes are recorded alongside quantitative metrics.
6. There is an explicit integrate/reject/retain decision for every evaluated
   backend.

## Phase 2: Phrase Review v2

The goal is to turn melody correction into recognition rather than singing
performance.

Planned features:

- automatic phrase segmentation into two-to-eight-bar review units;
- two to five rendered MIDI alternatives per uncertain phrase;
- synchronized source, waveform/pitch map, piano roll and chord lane;
- actions such as closest candidate, octave up/down, earlier/later, repeated
  note, split, merge and contour direction;
- optional two-to-five-second hum, whistle, tap or single-note guide;
- contour/time alignment that does not require the guide to be in the source
  key or octave;
- accepted correction propagation to repeated phrases;
- a small personal ranking/calibration model trained from explicit choices;
- untouched automatic and reviewed versions with complete audit history.

Phase 2 succeeds when a user who cannot hum a whole song can correct its main
melody phrase by phrase and prefers the reviewed neutral-instrument rendering
to the automatic candidate.

Implemented so far:

- [x] turn confidence-ranked agreed-F0 regions into three local alternatives;
- [x] render MIDI-only and source-plus-MIDI phrase auditions;
- [x] capture explicit choices in the existing correction JSON contract;
- [x] require completed review and matching source hash before MIDI export;
- [x] preserve every raw tracker artifact and refuse monophonic backing review;
- [ ] merge note clusters into musical two-to-eight-bar review units;
- [ ] add short hum/tap/contour correction only for unresolved regions;
- [ ] propagate accepted choices across genuinely repeated phrases;
- [ ] learn a personal ranking only from explicit reviewed choices.

## Phase 3: Instrument Intelligence v2

Planned features:

- learned audio embeddings alongside existing explainable spectral features;
- source-versus-rendered candidate matching using the same MIDI phrase;
- sample clustering by instrument identity, articulation and timbre;
- distinct kick, snare, tom and percussion families rather than one pitch/name;
- velocity-layer and round-robin discovery from repeated source events;
- root-note, tuning and usable-range estimation with confidence;
- bleed, transition and outlier rejection;
- loop-point suggestions with waveform and representation continuity;
- user accept/reject feedback stored as instrument-choice evidence;
- backward-compatible Instrument Bundle output and GarageBand audition steps.

Phase 3 succeeds when the top suggestions sound closer in blinded A/B tests and
source-derived instruments remain useful across several pitches and dynamics.

## Phase 4: Cleanup and Neural Timbre Lab

This remains an explicit experimental lane.

Planned experiments:

- query- or prompt-based isolation for mixed stems;
- target plus residual reconstruction checks;
- neural denoise/de-reverb only when it improves downstream transcription;
- monophonic DDSP-style timbre models for bass, wind, strings or vocal-like
  instruments;
- optional DAW hosting through a suitable Audio Unit bridge;
- generated missing samples marked separately from extracted samples;
- no generic image diffusion over spectrograms without an audio-valid decoder;
- no generated output promoted to `exact` evidence.

Phase 4 succeeds only if an experiment beats the simpler sample/DSP path in
listening tests and remains reproducible, attributable and safe to distribute.

## Daily progress routine

Each working day should aim for one narrow vertical improvement:

1. Choose one unchecked item or one clearly stated investigation.
2. Record the hypothesis and the golden clip before changing code.
3. Make the smallest implementation or experiment that can answer it.
4. Run focused tests and one relevant end-to-end comparison.
5. Save metrics, preview paths, warnings and unexpected findings.
6. Update the checklist and daily log.
7. Stop with the repository usable; do not leave the core workflow depending
   on an unfinished model installation.

### Daily log template

```markdown
### YYYY-MM-DD — short title

- Goal:
- Change or experiment:
- Inputs:
- Model/runtime/checkpoint:
- Evidence and metrics:
- Listening result:
- Decision:
- Problems/risks:
- Next smallest step:
```

## Daily log

### 2026-07-16 — Phase 1 optional close-out and PESTO F0 oracle

- Goal: finish every local Phase 1 engineering task and optional experiment,
  leaving only the listening decision that must be made by a person in
  GarageBand.
- Change or experiment: added a pinned, isolated PESTO 2.0.1 backend with raw
  frame and activation evidence; evaluated it on lead, backing and bass;
  extended the MuScriptor comparison to keys, kick and strings; ran all four
  optional AI backends on a deterministic silence fixture; assessed and
  rejected MT3 for this phase; and generated one local listening scorecard
  containing all required and optional A/B previews.
- Inputs: Lidl lead vocal 30–45 s, backing vocal 205–220 s, bass 200–215 s,
  keys 0–15 s, kick 200–215 s, strings 120–135 s and five seconds of digital
  silence. The private source audio and immutable outputs remain under
  `work/ai-bakeoff/`.
- Model/runtime/checkpoint: PESTO package 2.0.1 with the 534,664-byte
  `mir-1k_g7.ckpt`, SHA-256
  `16c32e06ddd950e3e4866dfa3c7f8a87c4988f8adf43e57977b189f031f26f3e`;
  the existing pinned MuScriptor, GAME and RMVPE environments were reused.
- Evidence and metrics: PESTO lead/backing/bass strong-onset F1 was
  0.103/0.333/0.182 and chroma similarity was 0.936/0.858/0.444. The existing
  specialised kick path scored 1.000 strong-onset F1 versus MuScriptor 0.985;
  MuScriptor improved keys attack F1 but reduced chroma and contour evidence,
  and was clearly worse for strings. Every optional backend emitted zero notes
  on digital silence. The repeated PESTO lead artifacts were byte-identical.
- Listening result: the prior human verdict that MuScriptor is substantially
  better than the lead baseline is recorded. Bass, backing-vocal and
  expression decisions remain deliberately unfilled in
  `work/ai-bakeoff/PHASE1_LISTENING_REVIEW.html`; optional keys, kick and
  strings checks are also available there.
- Decision: retain PESTO only as independent vocal F0 evidence and reject it
  for the current bass golden. Keep specialised kick and strings paths. Keep
  MuScriptor keys as an optional A/B candidate. Reject MT3 for Phase 1 because
  its official T5X/Colab inference stack adds substantial complexity without
  an identified advantage over the integrated MuScriptor comparison.
- Problems/risks: objective source agreement cannot decide whether a MIDI
  rendering sounds musically better, and a software agent cannot honestly
  manufacture GarageBand A/B judgments. The human review therefore remains a
  completion criterion rather than being silently waived.
- Next smallest step: complete the required rows in the local listening page,
  export `sunofriend-phase1-listening-review.json`, and record its decisions in
  this roadmap. No further model installation or engineering is required to
  close Phase 1. The close-out build passed all 300 tests, Ruff, all-backend
  diagnostics, package build and `twine check`; all 28 review audio links were
  also verified locally.

### 2026-07-16 — Recognition-first phrase review v1

- Goal: make melody correction possible by recognizing short alternatives
  instead of requiring a whole-song hum or trusting one aggregate score.
- Change or experiment: added `melody-review`; verified the completed tracker
  run, source, Basic Pitch, combined MIDI and boundary evidence hashes; ranked
  the weakest agreed-F0 regions first; rendered raw Basic Pitch, GAME-boundary
  and combined MIDI plus source overlays; added small piano rolls, explicit
  per-phrase radio choices and reviewed JSON export. `melody-apply` now refuses
  an unreviewed/incomplete phrase document or source-hash mismatch and records
  the choices in its audit. Backing runs are refused rather than collapsed.
- Inputs: the local Lidl lead-vocal seconds 30–45 golden, B major, 119 BPM,
  A=440, using the final boundary-repair v2 tracker run.
- Model/runtime/checkpoint: no new model. The package uses the existing hashed
  Basic Pitch 0.4.0, seeded GAME v1.0.3 and agreed pYIN/RMVPE evidence; neutral
  previews use the configured local FluidSynth/SoundFont.
- Evidence and metrics: nine regions each received three alternatives. The
  package contains 120 files: nine source excerpts and 27 each of MIDI,
  MIDI-only WAV, source-overlay WAV and evaluation JSON, plus the HTML,
  correction seed and manifest. GAME honestly has zero notes in three regions.
  Objective preference varies by region: for example, the 7.09–7.87 s region
  scores strong-onset F1 0.667/1.000/0.800 for raw Basic Pitch/GAME/combined,
  while raw Basic Pitch is often denser and has higher chroma. All 120 final
  v2 files were byte-identical in a fresh repeat and contain no temporary
  build paths.
- Listening result: every alternative has both isolated neutral MIDI and a
  source-plus-MIDI overlay ready in the local HTML. Actual human choices and
  GarageBand A/B preference are pending; the unreviewed seed is not presented
  as a reviewed melody.
- Decision: integrate `melody-review` as an explicit lead-only review layer,
  defaulting visually to combined but never treating it as chosen until the
  user reviews all nine regions. Keep raw evidence immutable and keep backing
  harmony outside this monophonic workflow.
- Problems/risks: several ranked regions are sub-second note clusters rather
  than musical two-to-eight-bar phrases; Basic Pitch may sound busy because it
  is raw/polyphonic; GAME has no accepted boundary in three regions; browser
  file pages must be opened locally by the user, so interaction QA is covered
  by generated-contract tests rather than uploading private audio.
- Next smallest step: collect the user's nine exported choices and GarageBand
  preference, evaluate that reviewed MIDI against the source, then use the
  explicit decisions to design repeated-region propagation and optional short
  hum/tap correction only where none of the three choices is close.

### 2026-07-15 — Agreed-F0 phrase boundary repair v1

- Goal: turn the saved independent trackers into phrase-sized melody options
  without allowing a boundary model to invent pitch or erase raw evidence.
- Change or experiment: added source- and checkpoint-hash-checked GAME input to
  `vocal-trackers`; treated raw Basic Pitch and GAME notes only as boundary
  proposals; required voiced pYIN/RMVPE pitch agreement within 70 cents,
  minimum coverage, stable pitch and supported edges; used their equal pitch
  midpoint because model confidence scales are uncalibrated. Published
  provider-specific and combined monophonic MIDI, every rejection reason and
  confidence-ranked phrases. Added hash-failure, selection, immutability and
  byte-repeat tests.
- Inputs: the same local Lidl lead seconds 30–45 and backing seconds 205–220
  goldens, B major, 119 BPM, A=440, plus their pinned RMVPE v2 frames and
  seeded GAME candidates.
- Model/runtime/checkpoint: librosa pYIN 0.11.0; Basic Pitch 0.4.0 packaged
  ICASSP 2022 ONNX SHA-256
  `2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec`;
  pinned RMVPE 0.2.3 ONNX and GAME v1.0.3 small ONNX bundle. Inference and
  repair stayed local.
- Evidence and metrics: lead received 114 proposals, accepted 42 before
  overlap selection and published 23 combined notes in nine phrases. Compared
  with the 35-note consensus, strong-onset F1 rose from 0.1481 to 0.3810;
  possible-onset F1 was 0.3396, timing p50/p95 21.73/37.50 ms, chroma 0.8872
  and supported-note ratio 0.4348. Fifteen selected lead boundaries came from
  GAME and eight from Basic Pitch. Backing received 73 proposals, accepted 14
  before selection and retained only six combined notes in two phrases;
  strong/possible onset F1 was 0.1111/0.1081 and supported-note ratio was zero.
  Sixteen evidence, MIDI and evaluation files per role were byte-identical in
  fresh repeat runs.
- Listening result: isolated variants, source overlays and 75-second source,
  raw Basic Pitch, consensus, GAME-boundary and combined sequences are ready
  for both roles. User GarageBand preference is pending.
- Decision: retain the lead combined result as an optional phrase-review
  challenger because it materially improves strong boundary matching over the
  first consensus. Do not promote it to the automatic primary. Treat the
  backing result as a negative experiment and retain raw polyphonic Basic
  Pitch, GAME/MuScriptor alternatives and the normal harmony stack.
- Problems/risks: accepted boundaries can still divide one expressive syllable
  into several notes; objective onset scores do not decide musical phrasing;
  equal pYIN/RMVPE agreement may still follow a harmonic; sparse rules lose
  too much genuine backing harmony.
- Next smallest step: expose the ranked lead phrases in the existing visual
  correction workflow with side-by-side raw Basic Pitch, GAME-boundary and
  combined auditions, then capture the user's selections as reviewed edits.

### 2026-07-15 — Independent core trackers and consensus v1

- Goal: expose pYIN and Basic Pitch on the same immutable evidence contract,
  then test whether a first time-aligned pYIN/Basic Pitch/RMVPE consensus adds
  useful melody evidence without erasing any tracker result.
- Change or experiment: added `vocal-trackers`; versioned and hashed raw pYIN
  frames and decoded notes; retained raw Basic Pitch events and its exact ONNX
  hash; required RMVPE's adjacent completed run and matching source SHA-256;
  recorded every aligned observation, agreement, solo, dispute and
  no-agreement decision; emitted separate MIDI/evaluation files and an
  experimental consensus. Added three-tracker, source-hash, immutability and
  byte-repeat tests.
- Inputs: the same local Lidl lead seconds 30–45 and backing seconds 205–220
  goldens, B major, 119 BPM, A=440, plus their existing RMVPE v2 frames.
- Model/runtime/checkpoint: librosa pYIN 0.11.0; Basic Pitch 0.4.0 packaged
  ICASSP 2022 ONNX SHA-256
  `2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec`;
  the previously pinned RMVPE 0.2.3 ONNX and hash. All inference stayed local.
- Evidence and metrics: lead pYIN/Basic Pitch/consensus produced 12/71/35
  notes. Their possible-onset F1 was 0.0211/0.4058/0.2542, chroma was
  0.8477/0.9323/0.9253, and supported-note ratio was
  0.2500/0.6197/0.3714. Lead consensus contained 631 agreement, 299
  no-agreement, one solo and 361 unvoiced frames. Backing produced 16/52/14
  notes; strong-onset F1 was 0.2609/0.3733/0.2727, while consensus pitch
  support collapsed to zero supported notes. Backing consensus contained 487
  agreement, 119 disputed, 103 no-agreement, 37 solo and 546 unvoiced frames.
  All nine evidence, MIDI and evaluation artifacts per role were byte-identical
  in fresh repeat runs.
- Listening result: isolated previews, source overlays and source-then-pYIN-
  then-Basic-Pitch-then-consensus auditions are ready for both roles.
- Decision: preserve raw Basic Pitch as the strongest evidence candidate on
  both goldens. Keep pYIN as the continuous baseline and RMVPE as an
  independent contour/alternate-voice oracle. Keep consensus v1 explicitly
  `review-required`; do not add it to the automatic vocal workflow. A single
  monophonic vote is particularly unsuitable for the backing harmony stack.
- Problems/risks: raw Basic Pitch can be polyphonic and dense, so its stronger
  objective score does not prove the best playable lead abstraction. Tracker
  confidence values are not calibrated to each other. A majority can follow a
  harmonic or a different real backing voice.
- Next smallest step: use the saved alignment to rank phrase-sized consensus
  regions and test a conservative repair that only borrows Basic Pitch/GAME
  note boundaries where pYIN and RMVPE agree on pitch; never replace the raw
  candidates or the polyphonic backing stack.

### 2026-07-15 — RMVPE immutable F0 challenger

- Goal: add a genuinely independent frame-level vocal pitch tracker on the
  same lead and backing goldens before attempting multi-model consensus.
- Change or experiment: pinned `rmvpe-onnx==0.2.3`; added a separate,
  hash-verifying model setup action; made `ai-doctor --require rmvpe` check
  both software and the exact checkpoint; added offline worker inference,
  path-confined `rmvpe.frames.json` evidence, and a deterministic
  frame-to-note v1 adapter with confidence, smoothing, short-gap, pitch-change
  and minimum-duration controls. Added immutable-artifact security tests,
  synthetic vibrato/rest decoder tests and standalone CLI routing.
- Inputs: local Lidl lead-vocal fixture from original song seconds 30–45 and
  backing-vocal fixture from seconds 205–220, B major, 119 BPM, A=440.
- Model/runtime/checkpoint: MIT `rmvpe-onnx` 0.2.3 adapter on ONNX Runtime
  1.27.0 CPU; MIT-labelled `lj1995/VoiceConversionWebUI` checkpoint revision
  `b2c8cae96e3b05de46d36c5ef9970ef6cbccafba`, SHA-256
  `5370e71ac80af8b4b7c793d27efd51fd8bf962de3a7ede0766dac0befa3660fd`;
  authors' reference implementation Apache-2.0. The 361,688,443-byte model is
  external and inference rejects URLs.
- Evidence and metrics: both lead and backing repeats produced byte-identical
  raw frames, candidates and MIDI. Lead produced 1,501 frames, 1,096 raw voiced
  frames and 44 notes; it passed the quality gate and scored strong/possible
  onset F1 0.2222/0.3622, timing p50/p95 25.04/37.03 ms, chroma 0.9339, mean
  pitch support 0.3089, supported-note ratio 0.4091, octave accuracy 0.2500,
  contour direction 0.7209 and contour correlation 0.1674. Backing produced
  1,501 frames, 782 raw voiced frames and 21 notes; its corresponding values
  were 0.2353/0.2022, 20.34/32.06 ms, 0.8591, 0.0723, 0.0952, 0.0476, 0.6500
  and 0.4353. It selected upper MIDI 70, 71 and 75 in addition to the shared
  dominant-line vocabulary, which may represent another backing voice or a
  harmonic.
- Listening result: source-plus-RMVPE overlays and source, MuScriptor, GAME,
  RMVPE sequential auditions were rendered for both goldens; preference is
  pending.
- Decision: retain RMVPE as an independent contour and alternate-voice oracle.
  Its lead chroma and contour direction are valuable, but its v1 decoded
  boundaries are not competitive; the backing result is not a replacement for
  either dominant line or the polyphonic harmony stack. Do not add a normal
  vocal-workflow flag or consensus yet.
- Problems/risks: RMVPE estimates F0, not notes; any MIDI boundary is therefore
  adapter policy. Polyphonic backing material can make it jump between voices
  or harmonics. The first parallel cold start took about 25.5 seconds, while
  warm repeats took about 2.65 seconds. The package's audio dependencies need
  explicit Python-3.12-compatible NumPy/Numba pins.
- Next smallest step: publish Basic Pitch and pYIN as separately evaluated raw
  candidates on these clips, then design a time-aligned consensus that uses
  RMVPE frames without erasing any model's independent evidence.

### 2026-07-15 — Backing-vocal GAME trial and opt-in integration

- Goal: determine whether GAME generalises beyond the lead-vocal golden and,
  if it does, make it usable without displacing the deterministic melody,
  MuScriptor or the polyphonic harmony stack.
- Change or experiment: ran two seeded GAME trials on the existing backing
  fixture, evaluated them against all three existing candidates, regenerated
  the identical MuScriptor MIDI with source-derived expression, prepared fair
  overlays and sequential auditions, refactored the model publication path,
  and added `vocal-melody --game` with language, seed, threshold, radius,
  D3PM-step, model, Python and timeout controls.
- Inputs: local Lidl backing-vocal fixture from original song seconds 205–220,
  B major, 119 BPM, A=440.
- Model/runtime/checkpoint: GAME v1.0.3 small ONNX on CPU, bundle SHA-256
  `0d1d57f0bdae5764d8bcff59561ecd26d93bc654548979bc20ac2a8aad0f38b9`,
  English language ID, official thresholds, eight D3PM steps and seed 0.
- Evidence and metrics: both runs produced byte-identical raw JSON and MIDI.
  GAME emitted 21 voiced notes from 23 regions, passed the quality gate and
  used the same four rounded pitches as MuScriptor. GAME scored strong/possible
  onset F1 0.5098/0.4045 versus MuScriptor 0.2439/0.2025 and the harmony stack
  0.3273/0.2796. MuScriptor retained better timing p50/p95 (11.45/24.77 ms
  versus GAME 16.25/34.98 ms), chroma (0.9023 versus 0.8753), contour direction
  (0.9000 versus 0.6500) and contour correlation (0.9085 versus 0.4955). The
  integrated command reproduced GAME's 21 notes, recorded all 21 as observed
  policy-confidence events, retained floating source pitch in provenance and
  recovered 14 distinct velocities from 42 to 116.
- Listening result: source-plus-model overlays, a 31-second
  MuScriptor-expression-then-GAME-expression A/B and a 79-second source,
  dominant, harmony, MuScriptor, GAME sequence are ready; preference remains
  pending.
- Decision: expose GAME as an opt-in monophonic vocal challenger because it
  materially improves boundary coverage on a second vocal role. Keep
  MuScriptor as a separate contour/timing alternative and keep the harmony
  stack as the only polyphonic backing-vocal representation. Never merge or
  promote these automatically.
- Problems/risks: backing-vocal harmonics still make absolute pitch/octave
  support unreliable; GAME may over-segment a phrase that MuScriptor expresses
  as one sustained note; the best boundary choice remains a listening decision.
- Next smallest step: install and evaluate RMVPE as an independent frame-level
  F0 tracker on the same two vocal goldens before designing any multi-model
  consensus.

### 2026-07-15 — GAME vocal boundary and pitch challenger

- Goal: add the first independent singing-specific note tracker so vocal
  boundaries and floating pitch can be compared with MuScriptor and the
  deterministic contour pipeline.
- Change or experiment: pinned GAME v1.0.3 and its official small ONNX release;
  added ONNX Runtime and Soxr to the isolated worker; implemented explicit
  local-bundle resolution, per-component hashing, English/universal language
  hints, D3PM boundary controls, voiced/unvoiced adaptation, floating-pitch
  candidates, seed recording, quality checks and source-expression MIDI.
- Inputs: the same local 15-second Lidl lead-vocal fixture from original song
  seconds 30–45, B major, 119 BPM, A=440.
- Model/runtime/checkpoint: GAME v1.0.3 small ONNX on CPU; bundle SHA-256
  `0d1d57f0bdae5764d8bcff59561ecd26d93bc654548979bc20ac2a8aad0f38b9`;
  ONNX Runtime 1.27.0; Soxr 1.1.0; English language ID; official thresholds;
  eight D3PM steps; seed 0.
- Evidence and metrics: two fresh seeded runs produced byte-identical raw JSON
  and MIDI. The selected 1.71-second run emitted 43 monophonic voiced notes
  from 48 regions and passed the quality gate. Against the source it scored
  strong-onset F1 0.4839, possible-onset F1 0.4762, timing p50/p95 22.25/36.34
  ms, chroma 0.9204, mean pitch support 0.3111, supported-note ratio 0.4884,
  octave accuracy 0.3256, contour-direction accuracy 0.6905 and contour pitch
  correlation 0.2781. MuScriptor's corresponding values were 0.4828, 0.5246,
  9.69/28.74 ms, 0.9084, 0.2978, 0.4615, 0.3333, 0.6579 and 0.2184.
- Listening result: source-expression preview, vocal mix and sequential
  MuScriptor-then-GAME audition prepared; user preference is pending.
- Decision: retain GAME as a reproducible independent vocal challenger. It
  improves chroma, pitch support and contour evidence on this clip while
  MuScriptor retains better possible-onset coverage and timing. Do not merge or
  automatically promote either candidate before listening and cross-role
  evidence.
- Problems/risks: GAME's D3PM boundary model was non-deterministic until an
  explicit ONNX seed was set; CPU is the only exposed execution provider;
  voiced presence is a boolean threshold result rather than a probability;
  source harmonics make the objective pitch evaluator comparative, not ground
  truth.
- Next smallest step: backing-vocal evaluation and opt-in integration are
  completed in the increment above; capture the outstanding listening
  preference while RMVPE becomes the next independent frame-level F0 increment.

### 2026-07-15 — Source expression and full-mix safety gate

- Goal: add usable dynamics without changing raw MuScriptor evidence, then
  measure whether the small model is safe and semantically reliable on a full
  mix rather than an isolated stem.
- Change or experiment: added note-local attack/body energy measurement,
  per-instrument robust velocity normalisation, separate expression JSON/MIDI,
  a model-neutral density/duplicate/polyphony/label quality gate, vocal
  integration and neutral-versus-expression auditions. Reconstructed a local
  15-second full mix from the user-written Lidl stems and ran unrestricted
  MuScriptor.
- Inputs: Lidl lead vocal seconds 30–45 and a 16-stem reconstruction of the
  same passage; metronome excluded; B major, 119 BPM, A=440.
- Model/runtime/checkpoint: MuScriptor 0.2.1 small on CPU with the previously
  recorded CC-BY-NC-4.0 checkpoint hash.
- Evidence and metrics: the accepted 39-note vocal candidate retained the
  exact raw MIDI SHA-256 `c02cc842bcde4235285b1983a9c2c05fa0c2a9b2cdfa28488b8d47c8d2ef0117`.
  Its separate source-expression MIDI used 26 distinct velocities from 42 to
  116 (median 89) and passed the new quality gate. The unrestricted full mix
  emitted 1,912 notes: 1,818 drums, 65 acoustic piano, 21 flutes, seven
  soprano/alto sax and one electric bass. Quality metrics were 127.47 notes/s,
  95.14% notes at 20ms or shorter, 93.62% duplicate signatures, 1,805 onsets
  in one 20ms bucket and maximum simultaneous polyphony of 1,806. Seventeen of
  28 flute/sax events matched the isolated voice's exact pitch and onset within
  80ms, demonstrating substantial vocal-to-wind label leakage.
- Listening result: source/neutral/expression vocal audition prepared; user
  preference pending. The full-mix MIDI was deliberately not rendered because
  its extreme event burst should not be sent to a synth.
- Decision: use source-derived expression for the opt-in GarageBand vocal
  challenger while preserving neutral/raw evidence. Reject automatic promotion
  of unrestricted MuScriptor-small full mixes. Prefer isolated, role-restricted
  stems and require `candidate.quality.json` to pass before promotion.
- Problems/risks: source energy is a relative velocity proxy, not a recovered
  MIDI performance controller. Full-mix instrument identity is unreliable and
  the model produced a severe short-note duplicate burst. The quality gate
  detects but does not rewrite the raw pathology.
- Next smallest step: add the first independent vocal-specific tracker (GAME
  or RMVPE) so note-boundary and F0 evidence can be compared with MuScriptor
  without relying on unrestricted full-mix semantics.

### 2026-07-15 — Cross-role evidence and explicit vocal integration

- Goal: decide whether the user's preferred MuScriptor lead-vocal result also
  generalises to melodic bass and overlapping backing vocals, then make the
  proven improvement usable without replacing existing evidence.
- Change or experiment: recorded the user's lead-vocal preference; created
  permanent local 15-second bass and backing-vocal fixtures; ran electric,
  acoustic, unrestricted and voice restrictions; evaluated and rendered the
  candidates; added `vocal-melody --muscriptor` as an explicit isolated
  challenger with tuned MIDI, note provenance and immutable run artifacts.
- Inputs: user-written Lidl song, bass seconds 200–215 and backing-vocal
  seconds 205–220, B major, 119 BPM, A=440.
- Model/runtime/checkpoint: the same MuScriptor 0.2.1 small checkpoint and hash
  recorded below, using CPU greedy decoding.
- Evidence and metrics: unrestricted MuScriptor increased the bass baseline's
  possible-onset F1 from 0.2152 to 0.3077, strong-onset F1 from 0.2456 to
  0.3235, contour correlation from 0.6581 to 0.7582 and notes from 20 to 31;
  timing p50 regressed from 7.10ms to 18.98ms. On backing vocals, MuScriptor's
  11-note voice line improved the deterministic dominant line's strong-onset
  F1 from 0.1905 to 0.2439, timing p50 from 27.31ms to 11.45ms, chroma from
  0.7098 to 0.9023 and contour correlation from 0.3846 to 0.9085. The existing
  26-note harmony stack still had higher onset coverage, confirming that a
  dominant line and a polyphonic harmony track must remain separate outputs.
- Listening result: the user states, “MuScriptor MIDI is substantially better
  than Sunofriend baseline” for the lead-vocal golden clip. Bass and backing
  A/B listening notes remain open beside their local auditions.
- Decision: integrate MuScriptor as an opt-in vocal challenger and retain the
  deterministic result as independent evidence and fallback. Do not
  automatically merge or promote it to primary yet. Preserve the existing
  backing harmony stack even when MuScriptor supplies the dominant line.
- Problems/risks: MuScriptor has no velocity evidence; the non-commercial
  checkpoint remains optional; backing-vocal absolute-octave evaluation is
  unreliable under harmonics/polyphony and needs listening; full-mix label
  leakage is still unmeasured.
- Next smallest step: collect bass/backing listening preferences, add source-
  evidence velocity recovery after the untouched raw candidate, and test one
  short full-mix passage before deciding on automatic role-specific ranking.

### 2026-07-15 — First real MuScriptor vocal bake-off

- Goal: measure whether a local open model adds useful melody evidence beyond
  the current pYIN/Basic Pitch vocal pipeline.
- Change or experiment: the user accepted the gated model terms; downloaded
  MuScriptor small locally; added checkpoint discovery/hashing diagnostics;
  ran identical CPU and MPS trials; evaluated and rendered A/B auditions.
- Inputs: locally extracted 15-second lead-vocal passage from the user-written
  Lidl song, original song seconds 30–45, B major, 119 BPM, A=440.
- Model/runtime/checkpoint: MuScriptor 0.2.1 small (103M), revision
  `8c127f603b807520fa465c838e9bfee8a91ada4e`, checkpoint SHA-256
  `bbd482c786b895cf7d8f44185073d951adae2ebb8a66f82ca84cd1f84569549c`.
- Evidence and metrics: CPU and MPS produced byte-identical 39-note MIDI. CPU
  completed in 3.30s versus MPS 5.37s. MuScriptor improved strong-onset F1
  from 0.0000 to 0.4828, possible-onset F1 from 0.0377 to 0.5246, chroma
  similarity from 0.8758 to 0.9084, supported-note ratio from 0.3913 to
  0.4615, and contour-direction accuracy from 0.4091 to 0.6579. Timing p95
  increased from 18.69ms to 28.74ms. The local comparison record preserves
  the complete metrics and paths. The full suite passes (265 tests), Ruff
  passes, both distributions build, and Twine validates both packages.
- Listening result: the user subsequently reported that MuScriptor MIDI is
  substantially better than the Sunofriend baseline.
- Decision: advance MuScriptor small as the preferred lead-vocal challenger;
  retain the current contour pipeline as independent evidence and fallback.
  Prefer CPU for this model/clip size because it was faster with identical
  output.
- Problems/risks: MuScriptor is much denser (39 notes/12.23 note-seconds versus
  23 notes/2.94 note-seconds), so listening must distinguish improved phrase
  continuity from syllable over-segmentation or over-sustain. The vocal
  evaluator's apparent polyphony is influenced by harmonics.
- Next smallest step: completed in the cross-role increment above; collect
  the remaining bass/backing listening scores before automatic ranking.

### 2026-07-15 — Isolated worker and immutable run records

- Goal: make the first optional model runnable without weakening licence,
  provenance or failure boundaries.
- Change or experiment: added `ai-transcribe`, a standalone MuScriptor event
  adapter, excerpt support, raw/validated candidate separation, neutral MIDI
  export, worker timeout/log capture and immutable per-run manifests.
- Inputs: synthetic audio/checkpoint bytes and fake success/failure workers;
  no song audio and no gated checkpoint.
- Model/runtime/checkpoint: core tests use fake workers; the real adapter
  requires an existing local `.safetensors` checkpoint and rejects aliases and
  URLs before importing MuScriptor.
- Evidence and metrics: synthetic tests cover success, event/schema parsing,
  raw candidate preservation, MIDI generation, source/checkpoint SHA-256,
  worker failure, timeout, collision/no-overwrite and no-download rejection.
  The complete suite passes (263 tests), Ruff passes, both distributions build,
  and Twine validates the wheel and source archive.
- Listening result: not applicable; no real checkpoint inference yet.
- Decision: retain raw notes with null model velocity and create a separate
  neutral-velocity MIDI; do not mix repairs into the model evidence.
- Problems/risks: MuScriptor MPS compatibility and instrument-name behaviour
  remain unmeasured; CC-BY-NC-4.0 acceptance must be explicit.
- Next smallest step: after explicit checkpoint acceptance, run CPU and MPS on
  one authorised 10–15-second clip and compare timing/pitch against the current
  Sunofriend transcription.

### 2026-07-15 — Phase 1 foundation

- Goal: begin the bake-off without destabilising the existing audio stack.
- Change or experiment: added the isolated Python 3.12 runtime definition,
  PyTorch/MuScriptor package setup, licence manifests, candidate v1 contract
  and `ai-doctor` design.
- Inputs: environment and synthetic protocol validation only; no song audio.
- Model/runtime/checkpoint: Python 3.12, pinned PyTorch and MuScriptor package;
  no gated model checkpoint downloaded.
- Evidence and metrics: Python 3.12.10, PyTorch 2.13.0, MPS built/available,
  MuScriptor 0.2.1 code installed; both `ai-doctor --require torch` and
  `ai-doctor --require muscriptor` pass. The complete existing suite plus new
  protocol tests passes (257 tests), Ruff passes, and the wheel/sdist build
  succeeds with `ai_runtime.py` included.
- Listening result: not applicable; model inference has not started.
- Decision: keep AI inference isolated and checkpoint downloads explicit.
- Problems/risks: MuScriptor weights are non-commercial and gated; GAME and
  RMVPE need external-checkout adapters and checkpoint manifests.
- Next smallest step: implement worker invocation/run manifests (completed in
  the following increment), then evaluate MuScriptor small on one authorised
  10–15-second clip after explicit checkpoint acceptance.

## Decision record template

Every backend decision should state:

- backend and exact model/checkpoint;
- task and golden clips;
- objective result relative to current Sunofriend;
- listening preference and reviewer;
- hardware/runtime cost;
- failure modes;
- code, weight and data-licence status;
- decision: integrate, optional oracle, investigate, or reject;
- conditions for revisiting the decision.
