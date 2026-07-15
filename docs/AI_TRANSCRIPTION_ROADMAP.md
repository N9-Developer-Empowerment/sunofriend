# Sunofriend AI roadmap

Status: Phase 1 in progress  
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
| 2. Phrase Review v2 | Planned | Recognition-first correction using short candidates, hum/tap/contour guidance and repeated-phrase propagation |
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
| GAME | Vocal pitches and note boundaries | MIT | Record exact release/checkpoint terms | First vocal challenger; external checkout |
| RMVPE | Vocal F0 under bleed/noise | Apache-2.0 | Verify exact checkpoint | Additional vocal tracker |
| PESTO | Lightweight vocal/instrument F0 | LGPL-3.0 | Record checkpoint | Later optional tracker/subprocess |
| MT3 | Multi-instrument research comparison | Apache-2.0 | Large/brittle T5X environment | Benchmark only unless it clearly wins |

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
```

The script uses Python 3.12 and installs the versions recorded in
`requirements-ai-macos.txt`. It installs MuScriptor's code but does not accept
its checkpoint licence, authenticate with Hugging Face or download model
weights. Those remain explicit, separately recorded steps before the first
audio experiment.

### Bake-off artifact layout

The planned output is immutable per run:

```text
work/ai-bakeoff/<song>/<run-id>/
├── run.json
├── source.json
├── backends/
│   ├── sunofriend/
│   ├── muscriptor/
│   ├── game/
│   └── rmvpe/
│       ├── request.json
│       ├── raw/
│       ├── candidate.json
│       ├── candidate.mid
│       ├── preview.wav
│       └── evaluation.json
├── comparison.json
└── listening-notes.md
```

`run.json` must identify operating system, Python, device, package versions,
model name, checkpoint URL and hash, licences, command, parameters, input hash
and elapsed time. Source paths may be retained locally, but a report intended
for Git must contain safe relative labels rather than private absolute paths.

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
- [ ] Add worker request/response invocation with timeouts and captured logs.
- [ ] Add immutable run manifests and input/checkpoint hashing.

#### Workstream B — MuScriptor

- [x] Install code without downloading gated checkpoints.
- [ ] Record explicit acceptance and checkpoint hash for the small model.
- [ ] Test CPU and MPS support; do not assume MPS compatibility.
- [ ] Adapt streamed note events into candidate v1 without adding velocity.
- [ ] Test full mix, restricted instrument lists and isolated stems.
- [ ] Recover velocity from source evidence after the raw candidate is saved.

#### Workstream C — vocal models

- [ ] Install GAME in an external checkout and record its checkpoint.
- [ ] Adapt GAME pitches, boundaries and voiced/unvoiced evidence.
- [ ] Install/adapt RMVPE as a frame-level tracker.
- [ ] Compare GAME, RMVPE, Basic Pitch and pYIN independently.
- [ ] Add consensus only after raw per-model evaluation exists.

#### Workstream D — evaluation and decisions

- [ ] Create the bake-off runner and artifact layout.
- [ ] Add synthetic protocol and failure tests.
- [ ] Run the first 10–15-second vocal and bass clips.
- [ ] Render neutral-instrument previews.
- [ ] Capture GarageBand listening scores.
- [ ] Publish the first model decision record.

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
- Next smallest step: implement worker invocation/run manifests, then evaluate
  MuScriptor small on one authorised 10–15-second clip.

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
