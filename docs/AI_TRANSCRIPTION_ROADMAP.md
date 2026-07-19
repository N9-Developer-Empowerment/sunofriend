# Sunofriend AI roadmap

Status: Phase 1 and Phase 2 engineering complete; Phase 3 complete; Phase 4
fixed-MIDI review complete; Phase 5.1 private listening and the Phase 5.2
fresh-process small-CPU baseline complete
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
| 1. AI Transcription Bake-off v1 | **Engineering complete; listening gate pending** | Independent local model candidates, common JSON, repeatable metrics and selection evidence; see the close-out report |
| 2. Phrase Review v2 | **Engineering complete; listening calibration pending** | Recognition-first correction using short candidates, hum/tap/contour guidance, repeated-phrase propagation and advisory personal history |
| 3. Instrument Intelligence v2 | **Complete** | Reviewable sound matching, source-event and drum-family evidence, explicit sampler choices, blind A/B, DAW confirmation and advisory loop selection |
| 4. Cleanup and Neural Timbre Lab | **In progress; first fixed-MIDI listening gate complete** | Complete GM patch preferred; source-fitted resynthesis retained as useful, source sampler rejected; no generated sound beat the simple complete-patch control |
| 5. MuScriptor Full-Mix and Community Learning | **In progress: Phase 5.0/5.1 complete; Phase 5.2 fresh-process small-CPU baseline complete** | Local Workbench, immutable MuScriptor evidence, M0–M4 matrices, exact label partitions and a verified repeated-run performance report are implemented; persistent worker, cache, other devices and model-size comparisons remain |

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
- a small deterministic personal ranking/calibration signal learned from
  explicit choices;
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
- [x] merge note clusters into musical two-to-eight-bar review units;
- [x] add source-supported short hum/whistle/tap/single-note correction only
  for one explicitly unresolved review unit at a time;
- [x] suggest genuinely repeated absolute-pitch/rhythm units and propagate an
  alternative only after an explicit, audited user action;
- [x] learn a local advisory personal ranking only from explicit reviewed
  choices, without changing candidate order, defaults or review status.

## Phase 3: Instrument Intelligence v2

Status: **complete**. See [the Phase 3 close-out report](PHASE3_INSTRUMENT_INTELLIGENCE.md)
for the implemented evidence, reproducible goldens and final listening
decisions.

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

Implemented so far:

- [x] optional local, hash-pinned OpenL3 music embeddings beside the unchanged
  explainable spectral/dynamics/attack score;
- [x] compare the source and every FluidSynth candidate using the same aligned
  MIDI performance and active one-second windows;
- [x] retain separate learned MIDI/WAV auditions, complete evidence JSON and
  additive Instrument Bundle v1 fields without automatic score blending.
- [x] deterministically cluster MIDI-aligned source events into advisory
  candidate timbre families and independent articulation groups, retain robust
  outliers, and carry JSON/SVG evidence through matching, sample packs and
  Instrument Bundle v1 without changing selection.
- [x] turn drum/percussion mapping units into role-specific GM channel-10
  proposals with assigned one-shot auditions, existing-note guardrails,
  immutable input hashes and additive Instrument Bundle v1 handoff.
- [x] discover advisory velocity-layer and round-robin candidates only within
  one timbre-family/note/articulation unit, retain a visual/source-index audit,
  and apply zero MIDI, sample, SoundFont or drum-mapping changes.
- [x] require an explicit all-unit listening review before applying candidates
  to a separate Sample Instrument v3; pin every input/review excerpt, retain a
  self-contained v2 rollback, use real SF2 velocity layers, expose true SFZ
  round robin and honest separate GarageBand alternate banks.
- [x] retain every isolated candidate while adding hash-pinned source-context
  and role auditions: repeated two-bar beats for drums/percussion and short
  sampler pitch phrases for pitched instruments, with zero selection effect.
- [x] add a real-MIDI source/v2/v3 musical A/B and explicit velocity-boundary
  sweeps to reviewed v3 outputs without altering source MIDI or review choices.
- [x] rank advisory post-attack/pre-release loop boundaries using waveform and
  spectral continuity, render raw repeated-loop auditions, exclude percussive
  one-shots, and leave every SF2/SFZ zone unlooped until a human accepts one.
- [x] build neutral, context-rich and byte-reproducible close-out reviews for
  snare, hats, cymbals and toms without carrying earlier kick or `other_kit`
  choices into another role.
- [x] hide v2/v3 identity behind deterministic Candidate A/B performance and
  velocity-sweep audio, keep the answer key outside the HTML, and resolve only
  a complete hash-pinned user export with zero sampler or MIDI effects.
- [x] close the human gate with a GarageBand/AUSampler snare decision and an
  explicit pitched-loop candidate, while retaining v2 rollback and leaving the
  sampler loop disabled.

Phase 3 evaluation is complete. Its evidence showed that reviewed suggestions
can improve an isolated sample without consistently sounding closer in a full
performance; blind proxy and final DAW listening therefore remain mandatory
selection gates.

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

Implemented foundations:

- [x] add a short, transparent MIDI-informed harmonic-mask baseline with
  explicit note-bearing track selection;
- [x] persist source excerpt, target, residual and zero-based guide MIDI with
  hashes and source/MIDI zero-mutation effects;
- [x] measure persisted target-plus-residual reconstruction and refuse excerpts
  longer than 60 seconds;
- [x] make WAV evidence byte-reproducible with GarageBand-friendly PCM24 rather
  than timestamped float-WAV PEAK chunks;
- [x] compare harmonic-only and explicitly labelled broadband-transient
  challengers without promoting either; and
- [x] re-transcribe source, target and residual separately and publish a local
  listening page;
- [x] reject incomplete source samplers with an arrangement-aware playability
  gate before timbre matching; and
- [x] retain explicit full-mix/solo patch choices in a deterministic local
  advisory profile without changing rankings, defaults or playability.
- [x] add a hash-pinned, isolated Demucs target/residual challenger with
  deterministic short excerpts, failed-run preservation and no automatic
  promotion.
- [x] resolve an explicit multi-role listening review against its complete
  hash-pinned evidence tree without regenerating or silently merging MIDI.
- [x] add a native-44.1-kHz fixed-MIDI harmonic-plus-noise baseline, mandatory
  complete-patch control, optional source sampler and explicit listening page.

Phase 4 succeeds only if an experiment beats the simpler sample/DSP path in
listening tests and remains reproducible, attributable and safe to distribute.
The current foundations meet the reproducibility and safety requirements. The
first fixed-MIDI review found harmonic-plus-noise resynthesis useful but still
preferred the complete GM patch, while rejecting the source sampler; no cleanup
or neural-timbre challenger has yet beaten the simpler path. See the
[Phase 4 stabilization review](PHASE4_STABILIZATION_REVIEW.md) for the
goals-versus-execution matrix and the gate before the next experiment.

## Phase 5: MuScriptor Full-Mix and Community Learning

The converter identified from Mirelo's Audio-to-MIDI workflow is MuScriptor,
the same optional model already evaluated in Phase 1. Phase 5 therefore does
not begin with another installation. It asks whether unrestricted instrument
discovery, role-conditioned full-mix/stem passes, medium/large checkpoints and
Sunofriend's source-aware repair can outperform the current role-specific
workflow.

The phase also proposes a local-first web feedback contract. Private audio
stays local by default; a contributor may separately opt into submitting only
review JSON/MIDI edit diffs or donating a short rights-cleared golden excerpt.
Community feedback first improves scorecards, regression gates, candidate
ordering and instrument suggestions. It is not model-training data by default.
The website is primarily the product UI: project setup, per-stem source/MIDI
comparison, phrase correction, arrangement audition, instrument choice and
GarageBand export. Feedback is the durable record of decisions made during
normal work, not a survey that users must understand separately.

The complete research findings, licence boundary, benchmark matrix,
performance strategy, feedback schema, privacy design, increments and
promotion gates are in the
[Phase 5 MuScriptor and Community Learning plan](PHASE5_MUSCRIPTOR_COMMUNITY_PLAN.md).

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

### 2026-07-19 — Phase 5.2 fresh-process small-model baseline

- Goal: establish an honest, reproducible speed baseline before adding a
  persistent worker, cache, larger checkpoint or faster decoding setting.
- Change or experiment: added a separate hash-pinned
  `muscriptor.performance.json` to fresh MuScriptor runs, parent-observed worker
  subprocess timing, and `sunofriend ai-benchmark`. The report reuses the
  immutable matrix verifier, requires equal source/requested-and-actual-
  excerpt/BPM/roles/device/checkpoint/config/worker/execution/runtime evidence,
  source-frame-derived duration, nested timers and non-overlapping repetition
  windows; it is path-free and never launches a model or promotes a musical
  result.
- Inputs: two fresh sequential runs of the existing private 15-second Lidl M2
  full-mix golden at 119 BPM. The original source and all generated evidence
  remain under ignored `work/` paths.
- Model/runtime/checkpoint: MuScriptor 0.2.1 small on CPU; checkpoint
  `bbd482c786b895cf7d8f44185073d951adae2ebb8a66f82ca84cd1f84569549c`,
  config `3008fc481e4a1cd978e337eb3759260c270892204db5039235ac939e1f42aeb2`,
  greedy, batch 1, beam 1, CFG 1.0 and three independent five-second chunks.
  No checkpoint was downloaded.
- Evidence and metrics: both repetitions produced byte-identical 107-note
  candidate MIDI. Median pipeline wall time was `5.189138 s` (RTF `0.345943`),
  worker subprocess `5.114512 s` (RTF `0.340967`), inclusive transcription
  `3.654508 s` (RTF `0.243634`), model load `0.291326 s`, first note start
  `1.478891 s`, first completed note `1.580453 s`, first completed chunk
  `2.541311 s`, and peak process RSS `1,142,669,312` bytes (about `1.06 GiB`).
  First/later pipeline ratio was `1.117054`.
- Comparability: both runs used `macOS-26.5.1-arm64-arm-64bit`, Python 3.12.10,
  PyTorch 2.13.0 and MuScriptor 0.2.1. All RTFs use the 15-second duration
  verified from the pinned source frames and request bounds. Inclusive
  transcription is iteration of
  MuScriptor's lazy `model.transcribe` result, so it includes backend
  preprocessing, condition construction and decoding rather than only model
  forward time.
- Listening result: none required. This increment measures execution and exact
  output repeatability; it does not compare musical alternatives.
- Decision: keep the small CPU fresh-process measurements as the Phase 5.2
  baseline. The second process may benefit from an uncontrolled OS file cache,
  but both runs reload the model, so neither is called a warm-model run.
- Controls: the new candidate MIDI hash
  `9bc1ede96cf8be5704573456753f7892748c14ecbe1b1c294249afb0c45d4e05`
  matches the earlier M2 MIDI. The five-track Phase 5.1 selection hash remains
  `1dce19ce7595a72b8417225b8d23679e0fc92e53581807ccf9db6ea929d7709c`
  and the handoff ZIP remains
  `7824e25850037821287fd77337ae9e8ad2d61cea2cbd2ea57e3b2f92e0c532f8`.
- Problems/risks: process RSS excludes accelerator allocation; pipeline time
  includes local post-processing but ends before the final runtime snapshot and
  manifest write; two repetitions are a baseline, not a hardware distribution.
- Next smallest step: implement one persistent local small-model worker and
  compare true reused-model repetitions with this exact fresh-process control.

### 2026-07-19 — Safe-lane bass, keys and vocal review completed

- Goal: compare the decoder-safe small-model routes on musical usefulness
  without letting different preview patches or absolute timelines bias the
  result.
- Change or experiment: built a three-row private Workbench catalog for bass,
  keys and vocal melody. Each row compares the isolated-stem M3 result with
  two exact M1/M2 full-mix label partitions. M3 review copies were shifted
  from song seconds 30–45 to review seconds 0–15 without changing pitches,
  durations, velocities or note counts.
- Controls: all nine candidates are rendered locally through one fixed
  role-appropriate General MIDI program per row (bass 33, keys 4, vocal 73),
  using the same SoundFont and preview policy. Original candidate MIDI remains
  unchanged.
- Review question: choose by recognisable bass contour, useful keys theme or
  accompaniment, and recognisable sung contour. Model labels such as sax,
  flute or guitar are hypotheses, not physical source-instrument identities;
  `none usable` remains a valid outcome.
- Listening result: bass had a clear choice: the 34-note M2 metadata-
  conditioned full-mix partition is main; the 19-note isolated M3 result needs
  correction and the 13-note M1 full-mix partition is rejected. Keys also had
  a clear choice: the 181-note isolated M3 result is main and the 106-note M1
  piano-labelled partition is optional; the 14-note M2 clean-guitar-labelled
  subset needs correction. Vocal outcome was `equivalent`: the 39-note
  isolated M3 line is the arrangement main and the 38-note M1 sax-labelled
  line remains optional; the 44-note M2 flute-labelled line needs correction.
  No problem tags or written reasons were supplied, so none are inferred.
- Full-mix check: all five selected main/optional tracks were explicitly saved
  in `full_mix` context. Three selected pairs share the verified full-mix AI
  origin, but none meets the substantial-overlap threshold. Their exact-
  pitch/onset match counts are 21, 0 and 11; the corresponding coverage pairs
  are 61.8%/19.8%, 0%/0% and 10.4%/28.9%.
- Decision: there is no universal lane winner. For this private golden, M2 is
  the reviewed bass route and isolated M3 is the reviewed keys route. The
  vocal row has an `equivalent` outcome, with M3 main and M1 optional; the
  saved data does not state a more specific equivalence claim. Keep raw lanes
  and role-labelled partitions; use the result as role-specific routing
  evidence, not automatic promotion across songs. The zero-note M3 drum lane
  and severe M0 decoder burst remain diagnostic-only.
- Handoff: a five-track, 119 BPM, B-major GarageBand ZIP contains exact copies
  of the reviewed main/optional MIDI and a dry neutral proxy. Source audio,
  private notes and every rejected/needs-correction candidate are excluded.
- Next smallest step: begin Phase 5.2 with a reproducible small-model runtime
  and cache benchmark; require separate authorisation before acquiring any
  medium or large checkpoint.

### 2026-07-19 — M4 listening rejects label isolation but keeps both full contours

- Goal: decide whether the bass-conditioned pass, clean-guitar-conditioned
  pass or exact label partition gives useful separate body/pluck MIDI.
- Listening result: the 41-note bass-conditioned full candidate and 43-note
  clean-guitar-conditioned full candidate were both chosen as main and
  confirmed together in full-mix context. The earlier 30-note body control was
  marked needs-correction; the earlier 11-note pluck and 14-note exact
  clean-guitar label derivative were rejected. No written problem tags or
  private notes were supplied, so no more specific reason is inferred.
- Evidence: the two accepted full candidates match on 40 notes at the declared
  80 ms exact-pitch/onset tolerance. The label derivative is concentrated in
  roughly the final five-second chunk and all 14 of its notes overlap the bass
  pass. The result supports useful contrasting performances or timbral layers,
  not successful source-role separation.
- Decision: retain both unchanged full candidates as the user's private
  arrangement choices; do not promote the model-label partition and do not
  deduplicate the two mains automatically. Add an overlap-aware full-mix
  finalisation warning before using this pattern in broader reviews.
- Handoff: a verified two-track GarageBand ZIP was built at 113 BPM in B minor;
  its numbered MIDI files are exact selected copies and its dry GM proxy is
  only an audition aid. Private media and review state remain ignored.
- Product follow-through: the Workbench now reports substantial overlap for
  selected candidates with the same candidate-origin source audio (verified AI
  run source, with review-stem fallback for non-AI MIDI), leaves the
  arrangement audible, requires the latest `full_mix` confirmation on both
  members before GarageBand handoff, and can export an exact private review to
  a fresh path without starting a server.
- Next smallest step: present the safe M1/M2/M3 Lidl lanes for explicit
  listening.

### 2026-07-19 — Strict M4 mixed-role evidence and label partition

- Goal: test whether one-role conditioning can separate the reviewed deep-body
  and plucked lines in one private mixed-role bass excerpt.
- Change or experiment: made M4 matrices require one distinct role per lane on
  the same source, excerpt and BPM; added M4 peer-overlap diagnostics,
  `ai-label-split`, and optional Workbench `review_question`/`listening_focus`
  prompts. Focused prompt hashes are pinned to review identity and private
  events, while prompt text is excluded from contribution preview. Label
  splitting preserves the unchanged full candidate and exact complement; it is
  not audio separation or instrument identification.
- Inputs: the private reviewed 16-second Slayyyter learned bass target at
  `113.000096` BPM and its earlier body/pluck listening controls. Audio and
  complete artifacts remain under ignored `work/` paths.
- Model/runtime/checkpoint: MuScriptor 0.2.1 small with the already accepted
  checkpoint/config; CPU, greedy, batch 1, beam 1, CFG 1.0 and independent
  five-second chunks.
- Evidence and metrics: the body pass produced 41 `electric_bass` notes. The
  clean-guitar-requested pluck pass produced 43 notes—14 requested
  `clean_electric_guitar` plus 29 off-role `electric_bass`. Forty notes matched,
  covering 40/41 of the body pass and 40/43 of the pluck pass. The exact label
  derivative contains 14 notes and its exhaustive complement contains 29;
  the raw-event partition deletes and duplicates nothing. Its deterministic
  MIDI auditions record integer-pitch/tick quantisation and same-pitch lifetime
  normalisation separately instead of claiming a lossless MIDI encoding.
- Listening result: pending. The private Workbench asks separate body and
  pluck questions and names leakage, missing/extra notes, octave, timing and
  duration as listening focuses; prompts make no selection.
- Decision: engineering evidence suggests substantial role collapse or
  relabelling, not successful two-source separation. Keep both full passes,
  the exact label partition, complement and earlier controls; promote nothing
  automatically.
- Problems/risks: model labels are broad semantic evidence. High overlap is
  not an accuracy score, and a 14-note label partition may still follow the
  wrong audible line.
- Next smallest step: complete the private bass/pluck listening review, then
  decide whether a separate keys melody/accompaniment M4 golden is warranted.

### 2026-07-19 — Explicit MuScriptor manifests and first small-model matrix

- Goal: make Phase 5 AI alternatives reproducible and keep demonstrably broken
  output out of normal Workbench decisions.
- Change or experiment: pinned the installed MuScriptor 0.2.1 execution
  contract, added `sunofriend ai-matrix`, attached its path-free quality/runtime
  evidence to Workbench candidates and reverified every served or handed-off
  artifact at the point of use.
- Inputs: the existing private 15-second reconstructed Lidl golden, its matching
  bass, keys, voice and mixed-percussion stems, and fresh immutable M0–M3 runs.
- Model/runtime/checkpoint: MuScriptor 0.2.1 small; checkpoint
  `bbd482c786b895cf7d8f44185073d951adae2ebb8a66f82ca84cd1f84569549c`;
  adjacent model config
  `3008fc481e4a1cd978e337eb3759260c270892204db5039235ac939e1f42aeb2`;
  greedy, batch 1, beam 1, CFG 1.0, independent five-second chunks. The pinned
  runtime does not expose prelude forcing, which is now recorded explicitly.
- Evidence and metrics: M0 reproduced the rejected 1,912-note result with 1,818
  drum-labelled notes and severe duplicate/onset/polyphony burst metrics.
  Conditioning on its discovered labels (M1)
  produced 169 notes without a severe decoder gate; metadata-conditioned M2
  produced 107 but substituted an unrequested clean-guitar label. Isolated M3
  bass/keys/voice produced 19/181/39 notes; M3 mixed percussion produced no
  notes. M0 is blocked, no-evidence is diagnostic-only, and raw candidate/MIDI
  mutation counts remain zero.
- Listening result: none yet. Cross-lane overlap supplies role-allocation clues,
  not correctness; no M1/M2/M3 lane has been promoted.
- Decision: Phase 5.0 is complete. Keep severe/no-evidence artifacts available
  for diagnosis and download but prevent main/optional selection. Ordinary role
  leakage remains auditionable because the listener may recognise the line.
- Problems/risks: label conditioning is not an output guarantee; the M3
  percussion lane needs a role/input review; browser switching is still
  second-synchronised rather than sample-accurate.
- Next smallest step: completed by the strict M4 entry above; listening of M4
  and the safe M1/M2/M3 alternatives remains before any medium/large model
  download or speed preset.

### 2026-07-19 — Cached comparisons, selected arrangement and GarageBand handoff

- Goal: make the Phase 5 Workbench useful when candidates do not already have
  preview WAVs and carry explicit choices into a listenable/exportable result.
- Change or experiment: added content-addressed neutral candidate rendering,
  shared-second source/A/B/C switching, an arrangement made only from active
  main/optional decisions, explicit `full_mix` confirmation and a deterministic
  GarageBand handoff ZIP containing unchanged selected MIDI.
- Inputs: synthetic cache/exclusion fixtures and the private Slayyyter Phase 4
  keys, kick, snare and bass artifacts.
- Model/runtime/checkpoint: no model. Existing FluidSynth and GeneralUser-GS
  render the role-neutral audition proxies.
- Evidence and metrics: repeated renders reuse verified SHA-256 caches; tests
  prove rejected/unreviewed MIDI is absent, private notes/paths are absent from
  the ZIP manifest and numbered selected MIDI bytes are unchanged. A real keys
  proxy rendered to `40,525,868` bytes; a four-choice real arrangement produced
  three proxy tracks (combined drums, bass and keys), and the verified handoff
  ZIP was `24,666,200` bytes.
- Listening result: implementation/packaging exercise only; no candidate was
  promoted from the render.
- Decision: keep neutral previews and the arrangement clearly labelled GM
  audition proxies. The selected numbered MIDI remains the authoritative DAW
  handoff.
- Problems/risks: HTML media elements synchronize by seconds, not samples;
  existing previews are not comparable; the instrument-choice view is still
  pending. A public blind review still needs decoded, level-matched short-loop
  switching.
- Next smallest step: completed by the explicit-manifest/matrix increment above.

### 2026-07-19 — Phase 5 local Workbench vertical slice started

- Goal: make existing source/MIDI comparisons understandable in one useful
  local site and retain genuine user decisions across launches.
- Change or experiment: added `sunofriend workbench PROJECT`, deterministic
  automatic or explicit cataloguing, a token-protected loopback HTTP server,
  project/stem pages, shared loop positions, bounded A/B/C candidate cards,
  role/outcome/problem decisions, append-only SQLite storage, JSON export and
  a metadata-only contribution preview with no submission endpoint.
- Inputs: synthetic test fixtures plus a read-only discovery run over the
  private Slayyyter source folder and its Phase 4 specialist MIDI directory.
- Model/runtime/checkpoint: none; the first slice consumes existing immutable
  artifacts and starts no AI worker.
- Evidence and metrics: the real project correctly inferred `113 BPM`,
  `B minor`, `440 Hz` and the chord PDF. Normal candidates are capped at three;
  `possible` and `uncertain` variants are diagnostic-only. Focused catalog,
  persistence, redaction, HTTP token, range-serving and CLI tests pass.
- Listening result: not yet a musical comparison. Many Phase 4 MIDI files do
  not carry a neutral preview WAV, and existing previews are explicitly not
  claimed to be level-matched.
- Decision: keep this UI as a presentation/decision boundary over the existing
  CLI. Do not interpret audition events, dwell time or defaults as preference;
  do not enable public submission.
- Problems/risks: automatic filename discovery can only infer roles, not user
  intent. Use an explicit catalog for ambiguous multi-role material. On-demand
  neutral rendering and whole-arrangement playback remain necessary before the
  site becomes the primary end-to-end workflow.
- Next smallest step: completed by the subsequent cached-preview/arrangement
  and explicit-manifest/matrix increments above.

### 2026-07-19 — MuScriptor full-mix research and Phase 5 draft

- Goal: investigate Mirelo's newly presented Audio-to-MIDI method and plan a
  fair comparison, faster local workflow and contributor feedback loop.
- Change or experiment: identified the converter as the already integrated
  MuScriptor model; inspected the current paper, model cards, official runtime
  and web client; drafted the separate Phase 5 plan.
- Inputs: existing Phase 1 MuScriptor small evidence, official upstream sources
  and the completed fixed-MIDI bass timbre review.
- Model/runtime/checkpoint: no new download or inference. Current local
  `muscriptor-small` 0.2.1 remains optional, hash-pinned and CC-BY-NC-4.0.
- Evidence and metrics: the published method uses a five-second mel-spectrogram
  prefix and a decoder-only Transformer trained with 1.45M synthetic MIDIs,
  more than 11,000 hours of aligned real music and reinforcement-learning
  post-training on 300 verified pieces. The official open UI records consented
  usage analytics, but its source contains no correctness rating or note-edit
  feedback path.
- Listening result: the completed timbre export preferred General MIDI Synth
  Bass 2 overall. GM and harmonic-plus-noise resynthesis were both marked
  ballpark/main; the source sampler was marked far/reject with missing
  consistency.
- Decision: use Phase 5 to compare full-mix discovery with conditioned stem and
  specialist candidates. Keep public feedback opt-in and metadata-first; do not
  host non-commercial model inference or upload arbitrary songs.
- Problems/risks: Mirelo Studio uses a separately trained larger-data model, so
  hosted results are not reproducible evidence for the released checkpoints.
  MuScriptor still lacks velocity and same-pitch overlapping-note support.
- Next smallest step: implement the Phase 5.0 local Workbench vertical slice on
  existing artifacts, then record prelude/batch/beam settings and build one
  immutable full-mix/conditioned/stem review matrix before accepting larger
  checkpoints or enabling public submission.

### 2026-07-19 — Fixed-MIDI timbre review completed

- Goal: decide whether the source sampler or fitted harmonic-plus-noise sound
  beats a complete patch while every candidate plays the identical bass MIDI.
- Change or experiment: validated the user's reviewed export against the
  unchanged seed and all five pinned source/MIDI/candidate hashes.
- Inputs: private Slayyyter bass source excerpt and unchanged 41-note MuScriptor
  performance at `113.000096` BPM.
- Model/runtime/checkpoint: no model; deterministic resynthesis and FluidSynth
  controls only.
- Evidence and metrics: reviewed JSON SHA-256
  `8c9d388e13bbbe1740890a5d6fb73046cb856e609309a126ef609a09b30374ac`;
  source SHA-256 `2bda5f30ac164bf93ec27829a8c740364fe8562b720a46ee006e6d0157f85a1b`;
  fixed MIDI SHA-256
  `540634d7578c1941a7dd8dd6eedb5ddd1f8ab0bcfcfa453f5c535c0cc48f1b14`.
- Listening result: GM Synth Bass 2 was ballpark/main but somewhat uneven; the
  source sampler was far/rejected and missing notes or consistency; fitted
  resynthesis was ballpark/main and complete, with a consistently different
  tone. Overall decision: `prefer_gm`, nearest tone and consistent.
- Decision: retain resynthesis as an optional listening layer, do not package
  it as the recommended generated instrument, and keep the complete GM patch as
  the next model's control.
- Problems/risks: passing the automated 41/41 audibility test did not guarantee
  perceived note-to-note consistency. Functional and musical gates must remain
  separate.
- Next smallest step: use the outcome in the Phase 5 instrument policy and do
  not invest further in the rejected source-sampler primary for this song.

### 2026-07-18 — Fixed-MIDI timbre baseline

- Goal: test sound generation separately from transcription now that the bass
  MIDI is stable.
- Change or experiment: added `timbre-resynthesis`. It fits one shared harmonic
  distribution, sustain ratio and deterministic attack-noise amount from an
  aligned monophonic reference, while rendering the exact same notes through a
  complete GM patch and an optional earlier source SF2.
- Inputs: accepted 16-second learned bass target; unchanged 41-note MuScriptor
  primary at `113.000096` BPM; earlier nine-zone source-derived bass SF2.
- Model/runtime/checkpoint: no model or checkpoint. Native NumPy/soundfile DSP
  at 44.1 kHz. Magenta DDSP and MIDI-DDSP code are Apache-2.0, but direct
  MIDI-DDSP use was deferred because the official repository is archived and
  documents an incompatible TensorFlow 2.7/Python 3.8/M1 installation path.
- Evidence and metrics: fixed MIDI SHA-256
  `540634d7578c1941a7dd8dd6eedb5ddd1f8ab0bcfcfa453f5c535c0cc48f1b14`;
  41 fitted notes; 16 harmonics; noise mix `0.040092`; sustain ratio `1.0`;
  all three candidates functionally audible on 41/41 notes; all MIDI-change
  and automatic-promotion effects zero.
- Listening result: pending in
  `work/ai-bakeoff/slayyyter-dance-phase4-fixed-midi-timbre-review-v2/timbre_resynthesis_review.html`.
- Decision: no candidate promoted. Functional audibility is necessary but is
  not a tone, realism or full-mix musical-quality verdict.
- Next smallest step: complete the timbre review. Package the synthesized
  profile as a playable generated instrument only if listening justifies it;
  otherwise retain the preferred complete patch as the control for a later
  local neural challenger.

### 2026-07-18 — Bass role review resolved without changing the MIDI

- Goal: turn the completed body/pluck listening review into one reproducible
  arrangement choice while retaining all useful alternatives.
- Listening result: the source and unchanged primary contained both roles.
  The strict body/complement split was useful, but the independently
  transcribed residual MIDI was diagnostic rather than an improvement.
- Change or experiment: added `midi-role-split-resolve`. It requires a complete
  user export, verifies the seed, source report, inputs and every artifact, and
  follows the overall decision rather than inferring a winner from component
  usefulness.
- Evidence and metrics: decision `keep_primary`; review SHA-256
  `e0fc94ad9b6236c194ffcc11d4235feb6ee4071d265c28595244015501166833`;
  recommended MIDI SHA-256
  `540634d7578c1941a7dd8dd6eedb5ddd1f8ab0bcfcfa453f5c535c0cc48f1b14`;
  zero notes changed, zero source mutations and zero alternatives deleted.
- Decision: use the unchanged 41-note primary bass MIDI. Retain the body and
  primary-pluck tracks as optional creative resources and the independent
  residual challenger as diagnostic evidence.
- Next smallest step: completed by the fixed-MIDI timbre entry above.

### 2026-07-18 — Reviewed bass cleanup and two-role MIDI challenger

- Goal: act on the listener's consistent observation that the bass stem carries
  both a deep synth-bass line and a shorter plucked synth/guitar-like line.
- Listening result: the completed 12-sound cleanup review selected the learned
  target as the main cleanup and described two roles throughout. The learned
  target was convincing overall but slightly weakened the pluck; the learned
  residual remained musical and retained it. The reviewed JSON SHA-256 is
  `442d242f825bf921cbd7ae328d791ad30495dddca8715cf487c5f70ab414bb45`.
- Evidence: note-aligned OpenL3 plus explainable features found a 30-note body
  cluster with median duration `0.504478` seconds and pitch range 28–40, and a
  nine-note transient cluster with median duration `0.134487` seconds and pitch
  range 33–54; two further transient events remained explicit outliers.
- Change or experiment: added `midi-role-split`. It requires an explicit body
  cluster, preserves every primary note in a strict two-track partition and can
  add a separately transcribed residual MIDI as an overlapping pluck challenger.
  It writes contrasting GM auditions and an unreviewed local export page.
- Independent evidence: MuScriptor found 13 notes in the learned residual,
  including octave pairs at common onsets, so the independent challenger can
  represent overlap that the 41-note monophonic target candidate cannot.
- Decision: keep body cluster `I1` as an explicit listening-backed hypothesis,
  not instrument identification. Compare the exact 30+11 partition with the
  30+13 residual challenger; neither is promoted automatically.
- Next smallest step: completed by the role-resolution entry above. Do not
  generalise multi-role splitting yet; use the unchanged primary for the next
  controlled timbre experiment.

### 2026-07-18 — Phase 4 pinned learned bass cleanup

- Goal: determine whether a local learned separator improves a clearly audible
  bass passage and downstream MIDI more than the unchanged source or transparent
  MIDI-mask baseline.
- Change or experiment: added `ai-cleanup`, an isolated Demucs worker, hard
  checkpoint verification, deterministic PCM24 source/target/residual evidence,
  external model setup, diagnostics, failure records and focused tests. Ran a
  predeclared 192–208 second bass golden and built an explicit 12-sound review.
- Inputs: private Slayyyter bass stem; existing 44-note full-song MuScriptor
  excerpt guide; existing MIDI-mask bass target/residual; fresh same-input
  Basic Pitch and MuScriptor transcriptions.
- Model/runtime/checkpoint: `demucs==4.0.1`, `htdemucs` signature `955717e8`,
  CPU, shifts `0`, overlap `0.25`; external checkpoint SHA-256
  `8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4`.
  Code is MIT; checkpoint terms are not separately stated, so private local
  evaluation only and no vendoring or redistribution.
- Evidence and metrics: two runs produced identical source, target-array,
  target and residual hashes. Target RMS was `-0.214 dB` and residual RMS
  `-14.686 dB` relative to source; persisted reconstruction error was `0.0`.
  Against the same source, short-input MuScriptor learned cleanup improved
  supported notes from `0.744` to `0.805` and octave accuracy from `0.564` to
  `0.585`, but reduced chroma `0.821` to `0.818`, contour direction `0.868` to
  `0.700` and strong onset F1 `0.122` to `0.121`. The DSP target yielded only
  eight MuScriptor notes. Full-context unchanged MuScriptor remained strongest.
- Listening result: completed. The listener selected the learned target as the
  main cleanup, called it convincing overall, and consistently heard a deep
  bass role plus a separate plucked role across the useful alternatives.
- Decision: Demucs is the preferred broad cleanup for this excerpt, but it does
  not solve intra-stem role separation. Preserve the full-context source MIDI,
  target, residual and every cleanup alternative.
- Problems/risks: PyTorch checkpoint deserialisation requires trusted pickle;
  the worker permits it only after exact hash verification. Model source roles
  are broad families. The in-app browser blocks new local `file://` navigation.
- Next smallest step: test an explicit two-role MIDI challenger without
  rewriting or discarding the accepted cleanup evidence.

### 2026-07-18 — Phase 4 stabilization review

- Goal: compare delivered behavior with the original Phase 4 goals and remove
  maintainability or handoff ambiguity before another model experiment.
- Change or experiment: audited the full uncommitted Phase 4 diff and private
  Slayyyter evidence; tightened instrument feedback/profile validation,
  centralized policy contracts, simplified coverage accounting and clarified
  texture-only Bundle instructions.
- Inputs: the existing 16-second keys mask golden, the 413-note keys MIDI,
  source-derived keys bank, reviewed Small Time Piano decision and profiled
  OpenL3 bundle. No new musical challenger was introduced.
- Model/runtime/checkpoint: no model; local deterministic JSON, MIDI, SF2 and
  PCM24 evidence only.
- Evidence and metrics: the stabilization rebuild retained 388/413 mapped
  notes, 328/413 attack-supported notes and 244/413 musical-duration-supported
  notes. The profile repeated byte-for-byte at SHA-256
  `6ff152ecccde09ce214cf889e4e5f6ecdc9adb2e34f59df5c5a65548bbd90b53`;
  the copied performance MIDI remained
  `4c3171886544a56a2f470ce8b0df95a2334dcac6e223f0a8f9e51871c21db533`.
- Listening result: unchanged. Small Time Piano remains the usable primary
  keys patch; the source sampler remains optional texture; unchanged-source
  MIDI remains the best keys melody transcription.
- Decision: the guardrails are stable enough to checkpoint, but Phase 4's
  musical success criterion is not met. Begin no new model work until the
  stabilized code is committed and one clearly audible target passage has a
  predeclared listening test.
- Problems/risks: the CLI and instrument orchestration functions remain large;
  split them incrementally behind characterization tests rather than mixing a
  broad rewrite with research.
- Next smallest step: after checkpointing, test one learned-separation
  challenger on a clearly melody-carrying short passage, or use the more
  promising monophonic bass line if no suitable keys passage exists.

### 2026-07-18 — Explicit GarageBand patch preference profile

- Goal: learn from the successful Small Time Piano full-mix decision without
  turning personal history into an automatic or hidden selector.
- Change or experiment: added `instrument-feedback` to hash-pin one explicit
  DAW choice to a Bundle v1 report/recipe/performance, `instrument-profile` to
  aggregate only named reviewed files, and additive `instrument-bundle
  --preference-profile` guidance.
- Inputs: the private Slayyyter keys playability-gated bundle and the explicit
  full-mix preference for Small Time Piano over the incomplete source sampler.
- Model/runtime/checkpoint: no model. Local deterministic JSON and SHA-256
  evidence only; OpenL3 and explainable match orders remain separate.
- Evidence and metrics: preferred/acceptable/rejected decision weights are
  1/0.5/−1; full-mix/solo context weights are 1/0.5. Duplicate hashes,
  unreviewed feedback, policy mutations and existing outputs are refused. The
  reviewed feedback hash is `b4ba10f58ca5b5310a2041a9a888c45d2064124df2a0a1d7d9eac38fd2710089`;
  two profile builds are byte-identical at
  `6ff152ecccde09ce214cf889e4e5f6ecdc9adb2e34f59df5c5a65548bbd90b53`.
- Listening result: Small Time Piano remains the user's current keys choice
  because it played every note with a consistent usable tone.
- Decision: show a positive history-first patch in future same-role bundle
  instructions, but never reorder factory/GM/OpenL3 evidence, change the MIDI,
  auto-select a patch or bypass a `texture-only` result. The profiled golden
  confirms all three ranking arrays, portable program hint and usability report
  are exactly unchanged.
- Problems/risks: one song is not enough to generalise a universal keys patch;
  profiles therefore preserve counts, negative feedback and listening context.
- Next smallest step: add further decisions only after real full-mix listening
  on new songs, then assess whether context beyond role is justified by data.

### 2026-07-18 — Source-instrument playability gate

- Goal: stop successfully built but incomplete samplers from being recommended
  as primary GarageBand instruments.
- Change or experiment: added Instrument Usability Gate v1, every-performance-
  pitch and velocity-probe auditions, additive Bundle v1 selection evidence and
  an explicit complete-patch fallback. The gate changes no MIDI, samples or
  SoundFont zones.
- Inputs: the private Slayyyter keys baseline and electric-piano sampler, plus
  synthetic coverage, duration, pitched and drum regressions.
- Model/runtime/checkpoint: no new model; deterministic MIDI/SoundFont evidence.
- Evidence and metrics: the baseline MIDI spans 35–95 but the source bank spans
  44–87, leaving 25/413 notes silent; the electric-piano bank spans 51–80 and
  leaves 55/413 silent. Both use short unlooped one-shots and fail as main
  pitched instruments.
- Listening result: GarageBand's Small Time Piano played the full keys MIDI
  consistently and was “night and day” more useful than the source sampler.
- Decision: playability precedes similarity. Demote failing source banks to
  `texture-only`, keep a complete GarageBand/GM patch primary, and require
  listening even after a functional pass. Keys matching now excludes GM synth
  leads/pads, which had produced a musically inappropriate sawtooth winner.
- Problems/risks: pitch detection and timbre clustering cannot establish
  instrument consistency; they remain review evidence. A complete factory
  patch still needs arrangement-level selection by ear.
- Next smallest step: retain Small Time Piano as the current human preference,
  then capture future full-mix patch choices as local advisory ranking feedback.
  Do not let similarity bypass functional checks.

### 2026-07-18 — MIDI-informed keys cleanup baseline

- Goal: determine whether an AI-labelled electric-piano role can separate a
  cleaner transcription target from one short mixed keys passage.
- Change or experiment: added `midi-mask`, a deterministic harmonic target and
  waveform-defined residual with an optional short broadband-onset window.
  It writes a cropped guide MIDI, PCM24 audio, hashes, reconstruction evidence
  and zero input-mutation effects to a fresh directory.
- Inputs: seconds 200–216 of the private B-minor keys stem and MuScriptor's
  electric-piano track 2 with 88 intersecting notes.
- Model/runtime/checkpoint: no new model. The already preserved MuScriptor
  candidate supplies only the guide; librosa STFT/ISTFT supplies the transparent
  DSP baseline.
- Evidence and metrics: persisted reconstruction maximum error is
  `1.19209e-7`. The guide's mean pitch support was `0.503` against the harmonic
  target and `0.026` against the residual, but strong-onset F1 remained higher
  against the residual (`0.439`) than target (`0.330`). The transient target
  raised guide strong-onset F1 only to `0.348`.
- Listening result: the AI electric-piano guide sounded like accompaniment and
  lacked the musical theme. The unchanged-source transcription contained the
  clearest bare bones of the tune. The harmonic target was less convincing and
  more accompaniment-like; the transient target had no real tune; the harmonic
  residual was jumbled/random; and the transient residual was not useful.
- Decision: keep unchanged-source MIDI as the primary result, retain harmonic-
  target MIDI only as an optional accompaniment candidate, and reject the
  remaining masked transcriptions for music-making. The mask is not promoted
  as melody cleanup. Recognition and musical usefulness override favourable
  isolation or polyphony metrics.
- Problems/risks: shared harmonics can leak into the target; a broadband onset
  window can admit simultaneous non-target attacks. Float WAV initially broke
  byte reproducibility through a changing PEAK timestamp, so final evidence is
  deterministic PCM24.
- Next smallest step: do not force this accompaniment-like keys role to become
  the melody. Test a learned separator only on a passage with a clearly audible
  target role, and compare it against unchanged-source MIDI plus this exact DSP
  baseline. Separately improve role selection so a melody experiment starts
  from a guide that actually carries the theme.

### 2026-07-17 — Phase 4 bass/keys golden and honest auditions

- Goal: determine whether local AI improves difficult bass and layered keys,
  and make transcription/timbre comparisons independently audible.
- Change or experiment: built the deterministic 113 BPM full arrangement,
  ran full-song MuScriptor bass and keys challengers, fixed role-blind General
  MIDI program assignment, added custom-SF2 previewing and packaged baseline
  and challenger Instrument Bundle v1 outputs.
- Inputs: one private 236-second B-minor song with 17 local stems, metronome
  and chord chart. No source audio or extracted sample is checked into Git.
- Model/runtime/checkpoint: local MuScriptor small checkpoint under its
  accepted CC-BY-NC-4.0 terms; stable Sunofriend CLI and FluidSynth comparison
  path. Full hashes remain in each immutable run.
- Evidence and metrics: bass strong-onset F1 rose from 0.070 to 0.324 and
  contour accuracy from 0.521 to 0.693 with similar mean pitch support. Keys
  strong-onset F1 rose from 0.223 to 0.438, but mean pitch support fell from
  0.646 to 0.283 and mean polyphony rose from 0.965 to 1.860.
- Listening result: pending GarageBand full-mix review. Source/GM and 2×2
  MIDI/sample-bank auditions are ready under ignored `work/`.
- Decision: retain the baseline arrangement; treat AI bass as a challenger and
  split AI keys by role. Do not promote the combined AI keys candidate.
- Problems/risks: model roles were previously all rendered as program-0 piano;
  that defect changed timbre but not model notes. Short bass events and mixed
  keyboard layers still limit source-derived sampler quality.
- Next smallest step: review the prepared bass and keys comparisons in
  GarageBand, then select one short mixed-keys passage for a target/residual
  cleanup experiment.

### 2026-07-17 — Phase 3 completed

- Goal: close the final GarageBand and pitched-loop listening gates without
  converting either decision into an unreviewed sampler mutation.
- Change or experiment: recorded the listener's explicit `snare v2` and
  `loop 1` decisions in a versioned close-out document and reconciled them
  with the earlier blinded FluidSynth result.
- Inputs: the reviewed snare v2/v3 GarageBand instruments; the three raw Lidl
  bass loop auditions; the hash-pinned blind A/B result and loop report.
- Model/runtime/checkpoint: no model. Human DAW listening and local immutable
  evidence only.
- Evidence and metrics: GarageBand preferred snare v2, overriding the blind
  proxy preference for v3. Candidate 1 for the 1.002396-second MIDI-30 bass
  sample spans 0.304438–0.902167 seconds, lasts 0.597729 seconds and has
  continuity score 0.116972. Its audition SHA-256 is
  `cdf639ff05b43ec5bc66680fc91372c0d250cdb89fdd514d28746c39d43bf6d8`.
- Listening result: final cross-role selections are v2 for snare, hats,
  cymbals and toms. Bass loop candidate 1 is the reviewed suggestion. Earlier
  kick event-17 and `other_kit` event-25 v3 packs remain experiments.
- Decision: mark Phase 3 complete. Do not promote the reviewed cross-role v3
  packs, and do not enable candidate 1 in SF2/SFZ automatically. The
  machine-readable close-out SHA-256 is
  `31332e2b076367d697fbc7a7f3acf9141b85003e59e7d42d16af2c1db28e0ebe`.
- Problems/risks: a good isolated sample does not guarantee the best musical
  result in a full DAW performance. The selected loop remains advisory because
  automatic loop application and crossfade tuning are deliberately outside
  this phase.
- Next smallest step: begin Phase 4 only when explicitly requested; no Phase 3
  engineering or human-review task remains open.

### 2026-07-17 — Blinded v2/v3 performance result resolved

- Goal: reveal v2/v3 identity only after the listener completed every neutral
  Candidate A/B choice, then retain the musical result without altering a
  sampler automatically.
- Change or experiment: validated reviewed export SHA-256
  `573e23366f80ea4120ed54007c57ca558496ddea59ff3e3a51b6036d3cfec876`
  against three unchanged v3 reports, every copied WAV, manifest SHA-256
  `46272b4b6604188049703adab20b369a46e089a40c8e36f23c132b55fa1e867e`
  and answer-key SHA-256
  `b8b6e241dd8c2ac2757cd4096cc9d87d855c614e9d45f32b85519733c3748d23`.
  Resolved it twice at fresh result paths.
- Inputs: the completed three-unit blind export; the reviewed snare, hats and
  toms v3 packs and embedded v2 baselines.
- Model/runtime/checkpoint: no model. Local JSON/hash validation only.
- Evidence and metrics: Candidate B was selected for snare and hats; Candidate
  A for toms. The answer key revealed snare B as v3, hats B as v2 and toms A as
  v2. The listener noted that selected snare and hats candidates were useful
  but not as rich as the source. Result SHA-256 is
  `95cc52ab61e8aa5d4a3e6a24d67625a539cc8c6a9287df2c78497166f59f4e91`;
  the repeat result is byte-identical. Summary: one v3 preference, two v2
  preferences, zero equivalent/neither and zero sampler/MIDI effects.
- Listening result: retain snare v3 as the only cross-role challenger. Retain
  unchanged v2 for hats and toms; the full-performance result outweighs their
  accepted isolated source-event choices. Cymbals already remain v2 because
  every proposal was rejected.
- Decision: do not promote the reviewed hats v3 or the tom velocity-layer v3.
  Keep them as evidence and rollback experiments. Take only snare v3 to the
  final GarageBand comparison.
- Problems/risks: FluidSynth is still a proxy and the selected snare remains
  less rich than the source stem. An eight-bar excerpt may not expose every mix
  context.
- Next smallest step: confirm snare v3 against its v2 rollback in
  GarageBand/AUSampler using the supplied real-performance MIDI, and record a
  candidate-or-none bass loop decision before closing Phase 3.

### 2026-07-17 — Reviewed cross-role v3 and blinded close-out gate

- Goal: apply the completed snare, hats, cymbals and toms reviews exactly, then
  test the resulting challengers without revealing v2/v3 identity.
- Change or experiment: validated four new exports against all pinned source
  evidence. Built and repeated separate reviewed snare, hats and toms v3 packs.
  The all-rejected cymbal export correctly produced no no-op v3. Added a
  blinded multi-pack page with copied source reference, Candidate A/B
  performance audio, the tom velocity sweep, a separate answer key and a
  hash-checking resolver.
- Inputs: reviewed export SHA-256 values: snare
  `8e5c99e9bb220951c877b66d2cd4c674fd077eb1b23b0d19c13b421ef2f60572`,
  hats `0baf25457f9048cebe6d159fd0b1f69ef3a141aed11c044d47533ca51660f6cf`,
  cymbals `d2a6d33db92e18105feec1cb5e8328b8fb2444c8dcdec4d45c956f7654043c3a`
  and toms `b9aace5ef10baaec91b15c62c4eeb582c7143f05c408e6d2b3513da6500698fb`.
- Model/runtime/checkpoint: no model. Deterministic source-event extraction,
  SF2/SFZ generation, FluidSynth rendering and local HTML/JSON only.
- Evidence and metrics: snare accepted event 44 at MIDI 40; hats accepted event
  35 at MIDI 42 and event 21 at MIDI 46; cymbals rejected all three units;
  toms accepted events 5/39 as MIDI-45 velocity layers split at 107/108 plus
  event 9 at MIDI 48 and event 14 at MIDI 50. No alternates were accepted.
  The v3 SoundFont hashes are snare
  `ccc891b7619ebdf9d3e368e41c2d26032944d4db1118d4cc10ac3626471af0df`,
  hats `6d09775e2f3e1ea50d1db5c5fb9a6ad87240173461483cb8483f3598f7c84739`
  and toms `c4c592df360facffc0c68b68b3b79dd780a8e44f6114a37abdc160ff698dae4c`.
  Main/repeat musical artifacts, sample trees and normalized reports match.
  The blind page contains three neutral units and one tom sweep; answer-key
  SHA-256 is
  `b8b6e241dd8c2ac2757cd4096cc9d87d855c614e9d45f32b85519733c3748d23`
  and audio-manifest SHA-256 is
  `46272b4b6604188049703adab20b369a46e089a40c8e36f23c132b55fa1e867e`.
  The complete repository suite passes with 351 tests.
- Listening result: source-event choices are complete; blinded v2/v3 preference
  remains open. The listener must not inspect the separate answer key first.
- Decision: retain the three reviewed challengers and the unchanged cymbal v2.
  Do not call any challenger better until the blinded export is resolved. Keep
  the tom boundary at 107/108 unless its sweep motivates a separate reviewed
  boundary workflow.
- Problems/risks: FluidSynth remains a proxy for GarageBand/AUSampler and a
  short 8-bar excerpt may not expose every arrangement context. Blinding hides
  version identity, not audible extraction artefacts.
- Next smallest step: review and export the three-unit blinded page, resolve it
  against the pinned answer key, record the bass loop candidate-or-none result,
  and confirm any preferred v3 once in GarageBand before closing Phase 3.

### 2026-07-17 — Phase 3 engineering close-out and sustain-loop evidence

- Goal: resolve the final unchecked Phase 3 engineering feature and prepare a
  cross-role listening gate without manufacturing any musical decisions.
- Change or experiment: added deterministic advisory loop-boundary analysis for
  pitched sample packs, with waveform/spectral continuity metrics, an SVG and
  click-revealing raw-repeat WAVs. Built fresh neutral Sample Instrument v2
  packs and review pages for Lidl snare, hats, cymbals and toms, then repeated
  the whole batch at independent output paths.
- Inputs: the permanent authorised Lidl stems and listened repair MIDI; the
  existing Lidl bass 200–215-second fixture for pitched loop evidence. Source
  and MIDI hashes are pinned in each generated report.
- Model/runtime/checkpoint: no new learned model. Loop ranking uses deterministic
  PCM waveform, log-spectrum, centroid and within-loop level evidence. The
  existing optional OpenL3 path remains separate and unchanged.
- Evidence and metrics: the bass pack contains five zones. Four source samples
  are below the 0.65-second advisory minimum; MIDI 30 is 1.002396 seconds and
  produced 791 evaluated boundary pairs plus three review candidates. The first
  candidate spans 0.304438–0.902167 seconds with continuity score 0.116972.
  The generated SF2/SFZ contain zero looped zones. The drum batch exposes 12
  review units and 42 exact candidate events: snare 4/15, hats 2/6, cymbals
  3/9 and toms 3/12. Snare and toms each have one possible velocity split.
  Every seed remains unreviewed, every primary starts blank and all effects are
  zero. Main/repeat SF2, SFZ, MIDI, WAV, sample, analysis and review-audio
  hashes match after output-path provenance is normalised. The repository's
  348 tests pass; wheel/source builds, `twine check` and a supported-Python
  clean-install CLI smoke test also pass.
- Listening result: open. A continuity score cannot decide whether a loop
  repeats phrase motion, vibrato, bleed or an effect. Likewise, source-event
  clustering cannot establish that two drum hits are the same instrument.
- Decision: mark Phase 3 engineering complete but keep Phase 3 itself open at
  its explicit listening gate. Apply no loop, drum-family, velocity-layer or
  alternate-sample choice automatically.
- Problems/risks: raw loop auditions intentionally reveal discontinuities and
  do not preview a crossfade. Short extracted notes cannot sustain indefinitely.
  FluidSynth and extracted stem context remain proxies for GarageBand/AUSampler
  use in a full arrangement.
- Next smallest step: the listener reviews the four neutral drum pages and the
  three bass loop auditions. Apply accepted drum choices to fresh v3 outputs,
  retain rejected roles unchanged, and record whether any loop candidate is
  musically usable before declaring the Phase 3 listening gate closed.

### 2026-07-17 — Reviewed Lidl kick event 17 applied

- Goal: apply the listener's explicit Lidl kick review while preserving the
  source MIDI, v2 instrument and every unselected source event as evidence.
- Change or experiment: validated the exported review against its pinned stem,
  MIDI, v2 report/SF2, cluster/dynamics reports and nine review WAVs. Built a
  fresh Sample Instrument v3 in which MIDI 36 uses reviewed event 17; MIDI 35
  retains its v2 zone. Repeated the complete apply at a second fresh path.
- Inputs: reviewed JSON SHA-256
  `1e4767b7a03137e6230840ceb902176a40dd512f731a9acbe9ab12ee016dd88c`;
  source v2 report SHA-256
  `bb3d0bfb623f6fc33f94e4fea52ff4df6af37f72963944975a2cbebab30b219b`;
  source repair MIDI SHA-256
  `91a1ed0a573cfed46300c1567db3344f32c81d0db36d063112231dc9ea5e689a`.
- Model/runtime/checkpoint: no learned model. Reviewed source extraction,
  deterministic SF2/SFZ construction and FluidSynth A/B rendering only.
- Evidence and metrics: one unit was accepted at MIDI 36 with event 17 as its
  sole primary; events 42 and 6 were not accepted as alternates. The v3 has two
  zones, one reviewed replacement, no velocity layer, no round robin and no
  GarageBand alternate bank. It changed zero MIDI pitches and velocities and
  left the source v2 tree unchanged. SF2 SHA-256 is
  `0237587bf6ea22440e5e721c7c09a426a91c24494fa1cc3859a518b31b34fd4b`.
  The eight-bar performance A/B contains 35 notes, both source pitches 35/36,
  velocities 103–120, and source beats 396–428 (199.664–215.798 seconds).
  Performance MIDI SHA-256 is
  `74a6a7c5e649680671085fd20f77f13da0ec53a0864c722de3605c33a0a46481`;
  the new v3 preview SHA-256 is
  `80fc15ed92525fa91183b3ccab8c8b4fc48e38cd06e49d2b1608999e61b7135d`.
  The repeat build reproduced every musical artifact and sample-tree hash.
- Listening result: the reviewer explicitly accepted event 17 as primary and
  selected no alternates. No textual reason was supplied, so none is inferred.
- Decision: retain event 17 as the sole reviewed MIDI-36 replacement in this
  experimental v3. Do not claim round robin or a velocity layer. Keep the
  embedded v2 bank as the authoritative rollback.
- Problems/risks: event 17 still contains the source stem's separation,
  processing and room context. FluidSynth preview is a proxy for AUSampler;
  the event choice still needs source/v2/v3 listening in GarageBand context.
- Next smallest step: compare the shared eight-bar source, v2 and v3 renders;
  if event 17 remains preferable in context, retain this pack and prepare the
  next clean drum role for the same explicit review workflow.

### 2026-07-17 — Lidl kick alternate-sample review v1

- Goal: test the Phase 3 dynamics workflow on a cleaner, single-role drum stem
  after rejecting an unlike `other_kit` velocity pair, without carrying that
  earlier listening decision into a different instrument.
- Change or experiment: built a fresh two-zone Sample Instrument v2 from the
  user-written Lidl kick stem and its unchanged repair MIDI, then generated a
  context-rich, unreviewed sample review. Each candidate has an isolated hit,
  a source-rhythm excerpt and the same normalized repeated two-bar audition.
  Final handoff QA also removed the review page's visual first-primary default:
  every primary now starts blank, and an accepted layer cannot be marked
  reviewed until the listener explicitly chooses one.
- Inputs: `Lidl-kick-B major-119bpm-440hz.wav` SHA-256
  `6070f98d222eac1d19a78b529e71a8b10d09581483f9c83833766079aef16022`;
  published repair `kick.mid` SHA-256
  `91a1ed0a573cfed46300c1567db3344f32c81d0db36d063112231dc9ea5e689a`.
- Model/runtime/checkpoint: no learned model. Existing explainable event
  features, deterministic clustering/dynamics policy, PCM extraction, SF2
  construction and FluidSynth preview only.
- Evidence and metrics: the broad match experiment had profiled 240 events
  with polyphonic windows permitted and proposed one velocity-layer unit. The
  sample-pack path instead profiled its default 48 isolated candidate windows;
  no velocity-layer unit survived that safer scope. It retained one MIDI-36
  alternate set containing events 42, 6 and 17 at velocities 120, 111 and 115
  and RMS levels -12.340, -12.763 and -12.911 dB. The v2 bank has two zones;
  SF2 SHA-256 is
  `b83604899a91d3aa12b41164342292ec16ac1efa730eef439b0b79cbb77532d5`.
  The review pins nine WAVs, six of them contextual, under manifest SHA-256
  `057a7245e22dfb85d363d74289154b76a0f103b318d0085259b62521e7398895`.
  A second clean run reproduced every SF2, SFZ, MIDI, WAV, sample-tree and
  review-audio hash. The corrected v2 review retains the same pinned manifest
  because the listening audio is unchanged; only the decision UI changed.
- Listening result: open. The review must establish whether the three events
  retain the same kick pitch, attack/body balance and decay, with only useful
  natural variation; it must not assume similarity from cluster membership.
- Decision: expose one alternate-sample review only. Supersede the first page
  with the explicit-primary v2 page, keep the seed unreviewed, accept no
  velocity layer and make no MIDI, sample-selection, baseline or SoundFont-zone
  change.
- Problems/risks: the 48-event cap is a deterministic evidence subset rather
  than every isolated event in the song. Normalized repeated beats reveal
  timbre but not original level; source-context excerpts retain relative level
  but also contain musical context and possible separator residue.
- Next smallest step: collect the explicit review export. If events are judged
  one identity, build a fresh v3 with one primary and only the explicitly
  checked alternates; otherwise reject the proposal and retain v2 unchanged.

### 2026-07-17 — Reviewed single-upper mapping applied

- Goal: resolve the audible MIDI-35 identity change using the listener's
  explicit v2 mapping choice, while preserving the source MIDI, source sample
  audio and earlier v3 pack.
- Change or experiment: validated the hash-pinned reviewed export and applied
  `single-high`. The fresh v3 maps upper source event 25 across velocities
  0–127, deactivates lower event 13 and removes the former boundary at 116.
  A second clean build was made only to test deterministic output.
- Inputs: unchanged Lidl `other_kit` context-reviewed v3; reviewed schema v2
  export; MIDI 35 events 13 and 25; original source MIDI SHA-256
  `de5926a88993b1e0af29724363b924e9c42c275249662403131765d980fd3155`.
- Model/runtime/checkpoint: no learned model. Deterministic MIDI/SF2 generation,
  FluidSynth rendering and SHA-256 validation only.
- Evidence and metrics: the final SF2 has 11 zones, four reviewed primary
  replacements and no velocity layer, round robin or alternate bank. The
  boundary apply changed zero MIDI notes and zero velocities, introduced zero
  source events, modified zero source sample files and removed one active
  event. SF2 SHA-256 is
  `2301d36e54e010fa5d1a33ee0b8de922de47674a9d896667836aa8a84eda9dde`;
  the 12-bar performance MIDI remains
  `49a676dbfb643079a6eb8d3afcfc2c0ae8883a37966fc88e6b0033679bdb05d9`;
  its new v3 preview is
  `7e6b943cf31d5de1d28b438836b51f91134070158b4b9ccdb3a8556bf7ddad34`.
  A repeat build produced identical SF2, SFZ, MIDI, preview-WAV, decision and
  sample-tree hashes. The original v3 tree remained byte-for-byte unchanged.
- Listening result: the reviewer heard lower event 13 and upper event 25 as
  different sounds. Event 25 alone retained the same tone at every velocity,
  so the reviewer explicitly selected the upper event only.
- Decision: accept event 25 as the sole MIDI-35 source in this experimental v3.
  Do not retain event 13 as a velocity layer. Keep the embedded v2 baseline and
  the earlier context-reviewed v3 available for rollback and comparison.
- Problems/risks: one sample preserves identity but cannot reproduce true
  acoustic velocity-dependent timbre; FluidSynth remains a proxy for final
  GarageBand/AUSampler listening. Stem bleed and room/effect character remain
  baked into the extracted event.
- Next smallest step: compare source, v2 and single-event v3 performance renders
  in context, then repeat this explicit identity-versus-dynamics review only
  for another accepted layer candidate with genuinely similar timbre.

### 2026-07-17 — Velocity-layer mapping review v2

- Goal: represent the listener's real decision—whether two samples belong in
  one velocity-layered instrument at all—instead of forcing every answer to be
  a numeric boundary.
- Change or experiment: upgraded the boundary-review schema to v2. Every unit
  now offers lower event only, upper event only and the existing layered
  boundaries. A fixed-velocity repeated two-bar beat renders both individual
  events at identical pitch, velocity and rhythm before one common velocity
  ramp tests every complete mapping. The page reports actual source-MIDI
  velocities and flags a lower or upper zone that the song cannot trigger.
  Apply may deactivate one already accepted event, but cannot introduce a new
  event, modify sample audio or edit source MIDI. Legacy v1 exports are refused.
- Inputs: the unchanged Lidl `other_kit` context-reviewed v3; MIDI 35; lower
  event 13, upper event 25, current split 116 and user feedback that pitch,
  tone and texture changed between the two sources.
- Model/runtime/checkpoint: no learned model. Deterministic MIDI/SF2 generation,
  FluidSynth rendering and SHA-256 validation only.
- Evidence and metrics: source MIDI 35 uses velocities 102, 107, 109, 110, 111,
  112, 114, 116, 119 and 120. The old boundary-124 choice therefore made the
  125–127 upper zone unreachable and acted implicitly like lower-event-only.
  v2 presents ten mappings and 34 pinned files. Both tone previews use velocity
  111; repeated-beat MIDI SHA-256 is
  `f78e1be6225610f5c2c710f42385bf2c5736eb9cbd9c68dcc3040adee2d621a7`.
  Lower/upper tone WAV hashes are
  `51a85006afe92da375b7afc736341caf3e401a29bd5abfdb027acc556050140e`
  and `4bfe51b380701a4bfafa145b64132d2ffa9160fa8a8b9b10cf64081e8c0fc904`.
  The complete manifest SHA-256 is
  `2d62857062aeeadedb768ca9b968921273d1e7a661cf83ea61e352f56e7405b5`.
- Listening result: the first review found the two events perceptually unlike;
  choosing the final boundary was a sensible way to minimise the switch, but
  it exposed that “no layer” was missing from the decision surface.
- Decision: supersede the un-applied v1 export with a fresh unreviewed v2 page.
  Do not infer lower-event-only; let the user choose it explicitly after the
  equal-velocity comparison.
- Problems/risks: both extracted events are individually peak-normalised, so
  the equal-velocity test deliberately emphasises timbre/envelope identity.
  A real acoustic velocity layer can become brighter or harder, but an obvious
  instrument or pitch-identity change still argues for one source event.
- Next smallest step: collect the v2 mapping export and rebuild a fresh v3. If
  lower-event-only is selected, verify one MIDI-35 zone, no velocity sweep,
  one deactivated accepted event and unchanged source MIDI/sample WAV hashes.

### 2026-07-17 — Explicit sampler boundary review v1

- Goal: turn an audible velocity-layer transition question into a deliberate
  listening decision without treating “carry on” as approval to move the
  reviewed MIDI-35 boundary or replace either accepted sample.
- Change or experiment: added `sample-pack-boundary-review` and
  `sample-pack-boundary-apply`. Review rebuilds candidate SF2/AUSampler banks
  around each accepted two-layer split and renders one identical unit-specific
  velocity sweep through every bank. It labels but never preselects the current
  boundary. Apply accepts only a complete user export, validates its manifest
  and regenerates the full v3 pack from the original reviewed sample choices
  with only the chosen boundary overrides.
- Inputs: unchanged Lidl `other_kit` context-reviewed v3; MIDI 35; accepted
  low event 13, high event 25 and current boundary 116.
- Model/runtime/checkpoint: no learned model. Deterministic MIDI/SF2 generation,
  FluidSynth listening renders and SHA-256 evidence only.
- Evidence and metrics: the review offers boundaries 96, 100, 104, 108, 112,
  116, 120 and 124. Every candidate uses the same 29-hit MIDI velocities 32,
  48, 64, 80, 95–97, 99–101, 103–105, 107–109, 111–113, 115–117,
  119–121, 123–125 and 127. The seed is `unreviewed`, selected boundary is
  null, effects are all zero and 25 candidate MIDI/SF2/AUSampler/WAV artifacts
  are pinned by manifest SHA-256
  `8cafd80b6e8976c8deed5bfe1229c074533979a793e83823bfde1bd39133f84e`.
  Source v3 report SHA-256 remains
  `b183861f3bdd8eb44c1ec74506a3f7f90e8572a1c03b1d76e2a5cc7458b63005`;
  its reviewed sample decision SHA-256 remains
  `686b7ec1aec40b4058362f57dfe67f9a55c20134e9476a9e1165f0204d17b9da`.
- Listening result: open. The reviewer should prefer a candidate whose quiet-
  to-loud sweep changes naturally in level and timbre, and may explicitly keep
  116 if it remains best.
- Decision: hand off the unreviewed HTML. Do not build a boundary-adjusted v3
  until the user exports `sample_boundary_review.reviewed.json`.
- Problems/risks: velocity controls both sample selection and playback level,
  so boundary choice remains perceptual. FluidSynth is a proxy; the generated
  `.aupreset` plus shared MIDI supports a final AUSampler comparison.
- Next smallest step: collect the explicit boundary export, apply it to a fresh
  v3 pack and compare source/v2/new-v3 real-performance and sweep artifacts.

### 2026-07-17 — Reviewed velocity-layer sweep v1

- Goal: expose whether the accepted Lidl MIDI-35 sample switch at velocity 116
  sounds natural, without automatically moving the boundary or replacing
  either user-selected event.
- Change or experiment: `sample-pack-apply` now creates an audit-only velocity
  sweep whenever a review accepts a two-layer unit. It plays coarse dynamics
  plus dense steps at boundary −8/−4/−2/−1, the exact boundary, and
  +1/+2/+4/+8, clamps to valid MIDI values and removes duplicates. The same
  MIDI is rendered through the v2 one-sample bank and reviewed v3 bank.
- Inputs: context-reviewed Lidl `other_kit`; MIDI pitch 35; accepted events 13
  and 25; reviewed low/high ranges 0–116 and 117–127.
- Model/runtime/checkpoint: no learned model. Deterministic MIDI generation and
  the existing FluidSynth/SF2 A/B renderer only.
- Evidence and metrics: the 119 BPM sweep contains 16 hits at velocities 32,
  48, 64, 80, 96, 104, 108, 112, 114, 115, 116, 117, 118, 120, 124 and 127.
  Both renders are 7.885 seconds. The sweep MIDI SHA-256 is
  `b542f1f9d7f4cc0467aece91bb06e670d65c31a6005f31c569ee6029dd29c4c4`;
  v2 WAV is
  `68a275fb982062bce4057021deb81aa9e62054ed287b3a4e6bf6e41a2a985740`;
  v3 WAV is
  `b1fbd95195b4fee5bae3097dd88b07a89a3ad6a6b7672159263a8a008cbdbe50`.
  Independent builds reproduced these and all preceding performance artifacts
  byte-for-byte. Mapping and source-sample change counts remain zero.
- Listening result: open. The critical adjacent hits are velocity 116 on event
  13 followed by velocity 117 on event 25.
- Decision: ship the sweep as an audit artifact only. Preserve the reviewed
  116 boundary until the user explicitly reports that another transition is
  musically preferable.
- Problems/risks: MIDI velocity simultaneously changes playback level and
  selects the sample, so a perceived jump can combine loudness and timbre.
  FluidSynth is a proxy for AUSampler, making the GarageBand preset comparison
  the final decision surface.
- Next smallest step: collect the v2/v3 transition preference. If 116→117 is
  unnatural, implement a separate hash-pinned boundary-choice review and apply
  workflow rather than silently tuning a threshold.

### 2026-07-17 — Real-performance sampler A/B v1

- Goal: judge a reviewed percussion rack with musical evidence rather than
  relying on isolated events or a sequential note-per-zone test.
- Change or experiment: `sample-pack-apply` now retains the zone audit and
  additionally selects a representative real-MIDI excerpt. It searches
  bar-aligned 8-, 12- and 16-bar windows, stops at the shortest window covering
  every source pitch, and otherwise maximises pitch coverage, note density and
  then earliest position. The excerpt is shifted to bar 1 and channel 1 for
  AUSampler without pitch, velocity or rhythm edits. It publishes one source
  stem reference and identical v2/v3-bank renders.
- Inputs: the context-reviewed Lidl `other_kit` v3 decision, its 194-note
  source MIDI and authorised source stem.
- Model/runtime/checkpoint: no learned model. Clip v1 performs deterministic
  MIDI import/export; FluidSynth renders the two local sample banks.
- Evidence and metrics: the shortest complete-palette window is 12 bars,
  source beats 112–160 or 56.470624–80.672320 seconds at 119 BPM. It contains
  50 notes, all 11 rack pitches and velocities 52–120. Source channel 10 is
  changed only in the audition copy to channel 1 for the custom bank. The
  source MIDI reports zero pitch/velocity mutations and retains SHA-256
  `de5926a88993b1e0af29724363b924e9c42c275249662403131765d980fd3155`.
  Source, v2 and v3 WAV durations are 24.202, 26.124 and 26.124 seconds; the
  latter include sampler release tails. Independent builds produced identical
  source WAV (`a5b5b860678a6a38cae7eb651cd87b691de8c3be4e993b215d7f8f54be6adeb1`),
  MIDI (`49a676dbfb643079a6eb8d3afcfc2c0ae8883a37966fc88e6b0033679bdb05d9`),
  v2 WAV (`d8d819ddc88abe0b8509a9a748b450975aa6ef546e7bec4d8adf548415341651`)
  and v3 WAV (`e6bdac6aa05161f91c8b3bcd075db8e5d2d99c1ec0cdb3f089f0bb37d6effeae`).
- Listening result: open. The three files are the first direct source-versus-
  conservative-bank-versus-reviewed-bank musical comparison.
- Decision: add this performance comparison to every reviewed v3 output while
  retaining the sequential zone audit. It is an audition artifact only and
  cannot promote v3, edit the original MIDI or imply that all source timbre is
  captured by one sample per zone.
- Problems/risks: a 12-bar density/coverage window is representative of the
  MIDI pitch palette, not necessarily the song's most recognisable section.
  Source and sampler levels differ, and rendered banks have longer release
  tails. Channel 1 is required because the generated SF2 is a melodic bank,
  even for a percussion rack.
- Next smallest step: collect the user's source/v2/v3 preference and whether
  the velocity-116 layer transition is natural. If not, add a reviewed boundary
  adjustment rather than changing it automatically.

### 2026-07-16 — Context-reviewed Lidl percussion rack v3

- Goal: apply the first user decision made with isolated, source-context and
  repeated-beat evidence, without changing the conservative v2 bank or
  inventing alternates the reviewer did not select.
- Change or experiment: validated the exported v6 review against all 63 pinned
  WAVs and applied its exact choices to a fresh Sample Instrument v3 with a
  common GarageBand audition, v2/v3 renders and embedded v2 rollback.
- Inputs: authorised user-written Lidl `other_kit` pack; reviewed export
  SHA-256
  `686b7ec1aec40b4058362f57dfe67f9a55c20134e9476a9e1165f0204d17b9da`;
  contextual manifest SHA-256
  `4a18bb8c8b186c98f0300cd712734833219d46d4cba4816ea2c38ce076a1d7a0`.
- Model/runtime/checkpoint: no learned model. Selection is entirely the user's
  explicit local listening review; rendering uses the existing FluidSynth
  path only for A/B previews.
- Evidence and metrics: four units were accepted and two rejected. MIDI 35
  uses event 13 for velocities 0–116 and event 25 for 117–127. MIDI 40 uses
  event 44, MIDI 42 uses event 39, and MIDI 50 uses event 12. The competing
  MIDI-42 family and MIDI 48 were rejected. Five reviewed events replaced four
  v2 roots; zones changed 11→12 solely because of the accepted velocity split.
  MIDI notes and velocities changed by zero, no alternate event was accepted,
  and no round robin or GarageBand alternate bank was generated. The reviewed
  SF2 SHA-256 is
  `abd7131c27bf7d29828ddcaaaa8e3b0cd7c6a4f29b7e88c8e63aa6ce56e2bbeb`;
  the embedded baseline remains
  `55085be93289608810cceb33d02b7d1ef49c85e1caa963b8529663fb6c01a8b2`.
  Independent builds produced byte-identical SF2, SFZ, audition MIDI, v2/v3
  preview WAVs and all five extracted source WAVs.
- Listening result: the explicit review accepted a broader four-note
  percussion palette than the earlier one-event review and selected the only
  proposed two-level unit. The user's reasons are represented by the choices;
  no automatic interpretation or relabelling was added.
- Decision: publish this as a separate context-reviewed challenger. Keep v2
  embedded and authoritative until the user compares the two presets in the
  full song. Do not add round robin because no alternate checkbox was accepted.
- Problems/risks: the velocity boundary of 116 gives the louder sample a
  narrow 117–127 trigger range; that is the reviewed proposal but may need a
  later musical boundary review in GarageBand. Samples still contain any
  source bleed, effects and transitions present in their 0.208-second events.
- Next smallest step: compare the common audition and then the real
  `other_kit` MIDI through the v2 and context-reviewed AUSampler presets. Record
  whether the MIDI-35 layer transition and the four replacements improve the
  full percussion rack before changing a default or threshold.

### 2026-07-16 — Role-aware contextual sample auditions v1

- Goal: make advisory sampler candidates recognisable to a listener who cannot
  reliably distinguish similar 0.13–0.21-second one-shots in isolation.
- Change or experiment: retained the exact normalised event WAV and added two
  pinned views per candidate. A four-beat source excerpt uses one shared
  stem-level gain to retain relative dynamics, nearby rhythm and bleed. A
  normalised role audition uses a repeated two-bar beat for drum/percussion
  roles or a short sampler-resampling pitch phrase for pitched roles. The HTML
  labels all three, and apply verifies their manifest before accepting a
  reviewed document.
- Inputs: authorised user-written Lidl `other_kit` Sample Instrument v2, its
  119 BPM aligned MIDI and the same six-unit/21-event review set used for the
  first heard v3 decision.
- Model/runtime/checkpoint: no learned model and no external renderer. Context
  audio is deterministic local PCM24; pitched phrases emulate sampler playback
  through deterministic resampling.
- Evidence and metrics: the fresh page contains 21 isolated one-shots, 21
  source-context excerpts and 21 repeated-beat auditions (63 pinned WAVs,
  about 19 MB). Source contexts are 2.017 seconds; repeated beats are
  4.172–4.243 seconds. Original-level context peaks span 0.1887–0.8900 while
  isolated/role auditions use a 0.8900 comparison peak. Two independent builds
  produced byte-identical WAVs and manifest SHA-256
  `4a18bb8c8b186c98f0300cd712734833219d46d4cba4816ea2c38ce076a1d7a0`.
  JavaScript syntax, focused tests and the unchanged zero-effect audit pass.
- Listening result: the user reported hearing many different percussion
  sounds and judged that variety potentially representative of `other_kit`.
  This supports treating the stem as a multi-sound percussion palette rather
  than forcing every mapped note to resemble one physical instrument.
- Decision: preserve timbral diversity and make musical usefulness the review
  question. Do not merge families, relabel MIDI pitch as acoustic pitch or
  infer acceptance from the new auditions.
- Problems/risks: a repeated beat repeats one candidate recording and is not a
  reconstruction of the surrounding source performance. The source-context
  player identifies the target by its recorded offset rather than adding an
  audible marker. Pitched resampling changes sample duration like a basic
  sampler and does not model a sophisticated instrument.
- Next smallest step: collect listening feedback from the new Lidl page. If
  individual sounds remain difficult to place, add a separate post-build
  multi-pitch percussion-rack groove without changing the source-event review
  contract.

### 2026-07-16 — First heard Lidl Sample Instrument v3

- Goal: apply the user's completed `other_kit` listening review without
  inferring any additional musical choices, then prove that the resulting
  instrument and rollback are reproducible.
- Change or experiment: applied the exported reviewed JSON to a fresh v3
  directory, corrected v3 reporting so proposed-but-rejected velocity layers
  and alternates are not described as active, and added a regression test for
  the one-primary/no-layer/no-alternate case.
- Inputs: the authorised user-written Lidl `other_kit` Sample Instrument v2
  and reviewed export SHA-256
  `4a5d336209efb9a8ea477fbbf809ba4eb57686d29a48ee6fe337496e75c151fa`.
- Model/runtime/checkpoint: no learned model. This remains an explicit human
  listening gate over deterministic source-event evidence.
- Evidence and metrics: the user accepted only unit `I1-P050-A1`, primary
  event 10 at MIDI pitch 50, and rejected the other five units. The build
  extracted one 0.209-second source event, retained 11 SF2 zones before and
  after, changed zero MIDI notes or velocities, produced zero velocity-layer
  units, zero round-robin layers and zero GarageBand alternate banks, and
  embedded the unchanged baseline SF2 SHA-256
  `55085be93289608810cceb33d02b7d1ef49c85e1caa963b8529663fb6c01a8b2`.
  Two fresh builds produced byte-identical reviewed SF2, SFZ, audition MIDI,
  v2/v3 WAV previews and extracted event WAV. The reviewed SF2 SHA-256 is
  `4ad6450d7275fea863a72cc7c6f83ef867baa8926a4b15d487208d111c7bd448`.
- Listening result: the reviewer found the isolated 0.13–0.21-second drum
  excerpts difficult to distinguish because they sounded like similar short
  thuds. One source event was recognisably useful; the remainder were rejected.
- Decision: preserve that exact choice as a one-sample replacement. Do not
  apply the proposed two-level unit, alternates or any inferred instrument
  identity. A feature is now reported as active only when the reviewed choices
  actually activate it.
- Problems/risks: isolated one-shots hide rhythmic role, consistency and bleed
  in musical context. A mixed residual `other_kit` stem is not one physical
  instrument, and MIDI pitch 50 is a sampler mapping rather than proof of a
  high tom.
- Next smallest step: add role-aware contextual review auditions: repeated
  beats and source-rhythm comparisons for drum/percussion units, and short
  scale/phrase auditions for pitched instruments, while retaining the exact
  one-shot evidence and explicit review gate.

### 2026-07-16 — Phase 3 reviewed Sample Instrument v3 gate

- Goal: let heard and explicitly accepted source-event candidates improve a
  sampler without silently promoting advisory level groups or making the v2
  instrument difficult to recover.
- Change or experiment: added `sample-pack-review`, which extracts exact local
  listening WAVs and an unreviewed HTML/JSON decision page, plus
  `sample-pack-apply`, which accepts only a complete reviewed document. Apply
  creates a separate velocity-layered SF2/AUSampler bank, sequence-round-robin
  SFZ, separate alternate SF2/AUSampler A/B banks, shared audition MIDI/WAVs,
  mutation audit and embedded v2 rollback. Portable SF2's lack of round-robin
  selection is recorded rather than hidden.
- Inputs: a deterministic synthetic two-dynamic/16-event kick fixture for apply
  tests, plus the authorised user-written Lidl `other_kit` Sample Instrument v2
  for the real unreviewed listening handoff.
- Model/runtime/checkpoint: no learned model. The gate consumes the existing
  explainable source-event cluster and dynamics evidence.
- Evidence and metrics: the Lidl page contains six review units, one possible
  two-layer unit, seven alternate sets and 21 pinned event-audio excerpts. It
  records zero baseline, MIDI or SoundFont changes because no musical choice
  has yet been made. Two fresh Lidl review builds produced byte-identical 21
  WAV evidence sets and manifest SHA-256
  `aefccc3f2c15394b37e52bdf211c856597f5a29606968d21c34f6dd42ef06973`.
  The synthetic accepted fixture produced two SF2 velocity
  zones from one v2 zone, four reviewed event WAVs, true two-event SFZ sequence
  round robin, one alternate GarageBand bank and byte-identical main SF2/SFZ
  hashes on a fresh repeat.
- Listening result: intentionally open. No Lidl unit was accepted or rejected
  by the implementation; the page is the handoff for user judgement.
- Decision: keep v2 as the default. Refuse unreviewed/incomplete choices,
  unknown event indices, multiple accepted units at one pitch and any changed
  source, MIDI, v2 report/sample/SF2, cluster/dynamics or review-audio file.
- Problems/risks: source excerpts can still contain bleed, effects or phrase
  transitions; a level split can still reflect mixing; and AUSampler requires
  separate A/B banks instead of automatic round robin.
- Next smallest step: listen to the six Lidl units, export a reviewed document
  and build the first real v3 A/B only if at least one proposal is recognisably
  useful. Use that listening result before changing thresholds or defaults.

### 2026-07-16 — Phase 3 advisory dynamics and alternate samples v1

- Goal: identify repeated source events worth auditioning as quiet/loud layers
  or round-robin alternatives without letting a source-level split rewrite MIDI
  expression or silently expand a sample instrument.
- Change or experiment: added deterministic analysis within the intersection of
  candidate timbre family, existing MIDI pitch and articulation. A two-layer
  unit needs at least eight events, at least four and 20% of the unit per
  layer, and at least 3 dB median RMS separation. An alternate set needs three
  isolated events; it selects the medoid plus diverse central examples while
  excluding the most distant 20%. Matching, Sample Instrument v2 and
  Instrument Bundle v1 retain JSON and SVG evidence with explicit all-zero
  mutation effects.
- Inputs: the authorised user-written full Lidl `other_kit` stem and its
  194-note listened repair MIDI. The sample-pack handoff used its existing
  conservative 48-event analysis ceiling; the bundle handoff used the Lidl
  kick fixture.
- Model/runtime/checkpoint: no learned model. The analysis uses the existing
  explainable source-event timbre, articulation, RMS and isolation evidence.
- Evidence and metrics: the full mixed-kit run produced 28 comparable units,
  five two-layer candidates, 20 alternate-sample sets, 60 candidate events and
  two retained/unassigned outliers among 194 events. The real sample pack kept
  its existing 11 single-velocity zones while retaining one layer candidate
  and seven alternate sets from the 48 analyzed events. The kick Instrument
  Bundle recipe carries its match-side dynamics report and graph. Two fresh
  full mixed-kit runs produced byte-identical dynamics JSON SHA-256
  `afdec6f5b32074adbcbc65273c63a66677fe88e2601ef4e378ecf04aabc05b90`
  and SVG SHA-256
  `4edc60014fd76790439ee65c18db863bb381a6e3c0ad1ccc723ca2b13921ef74`.
- Listening result: open. The timeline clearly exposes candidate groups and
  exact source-event indices; it deliberately does not assert that apparent
  level groups are real separately recorded dynamics.
- Decision: ship discovery only as additive review evidence. Record zero MIDI
  note/velocity changes, zero sample additions/removals, zero SoundFont-zone
  changes and no drum-family change. Do not call a candidate a valid layer or
  round robin until its indexed excerpts have been compared by ear.
- Problems/risks: MIDI velocity already uses source energy and is therefore not
  independent evidence; bleed, room sound, phrase context or section-level mix
  changes can create a false split; and alternate events can preserve unwanted
  transitions even after centrality filtering.
- Next smallest step: add an explicit reviewed-sampler experiment that applies
  only user-accepted event indices to a new Sample Instrument v3 copy, with an
  A/B audition and rollback path. Do not alter the v2 default.

### 2026-07-16 — Phase 3 conservative GM drum-family proposals v1

- Goal: distinguish real kick, snare, hat, cymbal, tom and mixed-percussion
  sounds without treating MIDI pitch as acoustic pitch or silently replacing
  a repair that already classified the kit well.
- Change or experiment: added role-specific GM percussion candidates rendered
  through the configured SoundFont, explainable 80% timbre/20% articulation
  scoring, deterministic distinct-candidate assignment, assigned one-shot
  auditions and a separate channel-10 MIDI/WAV. Mapping units are the
  intersection of source timbre family and existing MIDI note, preventing a
  broad cluster from collapsing useful kit-piece labels. A valid existing role
  note changes only when a candidate scores at least 55 and leads by at least
  eight relative points. Original MIDI hashes are checked before and after.
- Inputs: authorised user-written Lidl full snare, hat, cymbals, toms and
  `other_kit` stems with newly generated repair MIDI, plus the permanent Lidl
  kick seconds 200–215 fixture and its existing 33-note repair MIDI.
- Model/runtime/checkpoint: no learned model. FluidSynth rendered the installed
  GeneralUser-GS SoundFont; every report records its path and SHA-256.
- Evidence and metrics: kick retained one persistent unit, four rare hits and
  all existing notes. Snare retained 249/249 notes across four mapping units;
  hats 484/484 across four units (15 outliers and one ceiling-retained event);
  cymbals 18/18 across three units; and toms 90/90 across eight units. Mixed
  `other_kit` retained all existing labels except two guarded experiments: 34
  note-42 events mapped to side stick and seven note-49 events mapped to cabasa,
  for 41 proposed changes among 194 notes, with two outliers retained. Every
  input MIDI before/after hash matched. Two fresh `other_kit` runs produced
  byte-identical report SHA-256
  `62d553a8e873b26bad3a43131f2d4a09df2627c9021e6d904155b5619b19a58a`,
  MIDI SHA-256
  `9bfeac77a0f9714484c078808c8728c75b62fc268fb32f39124fa0fbd169f10d`
  and WAV SHA-256
  `4439fbc9375f9757a39cd4ba5322ab4e5f266b5daab685981a6228d82fa45e9e`.
- Listening result: open. The unchanged role-specific proposals are a useful
  no-regression result. The two mixed-kit reassignments require source/proposal
  and intended-GarageBand-kit A/B before either is accepted.
- Decision: integrate only as review-required additive evidence. Keep
  `performance.mid` and the supplied MIDI authoritative; put the proposal and
  its WAV in `matches/` and bundle `previews/`. Call 55/eight-point rules policy
  guardrails rather than confidence calibration.
- Problems/risks: SoundFont kit pieces differ from GarageBand kits; separator
  bleed can form coherent families; the 512-event ceiling can leave a small
  number of hits unanalyzed; and mixed-kit candidates remain especially easy
  to mislabel even when their relative feature score is strong.
- Next smallest step: listen to the retained mixed-kit A/B in GarageBand. If
  useful, add velocity-layer and round-robin evidence inside an accepted drum
  mapping unit without changing its note assignment automatically.

### 2026-07-16 — Phase 3 source-event clustering v1

- Goal: expose when one nominal stem contains several timbres, articulations or
  separator artefacts without automatically deleting musically useful events.
- Change or experiment: added deterministic robust-distance/k-medoids candidate
  timbre families, independent articulation grouping, retained nearest-neighbour
  outliers, per-event/medoid JSON and an SVG pitch/timeline. Matching uses
  source-rate excerpts; sample packs mark selected events. Instrument Bundle v1
  carries both reports. Optional OpenL3 contributes 30% identity distance while
  explainable features retain 70%.
- Inputs: a 13-event synthetic two-family/two-articulation fixture with one
  deliberate outlier, plus the authorised user-written Lidl bass seconds
  200–215 and its aligned 20-note repair MIDI.
- Model/runtime/checkpoint: default clustering is model-free. The learned golden
  used the same pinned OpenL3 ONNX CPU checkpoint and hash recorded in the next
  log entry.
- Evidence and metrics: the synthetic fixture recovered both six-event timbre
  families, both articulation groups and the one retained outlier. On Lidl,
  explainable-only evidence found two candidate families, one articulation
  group and retained the short MIDI-39 event beginning at 8.941586s as an
  outlier. OpenL3-assisted evidence instead retained all events and found three
  candidate families of 11, 4 and 5 events with identity silhouette 0.302704.
  Two fresh learned runs produced byte-identical cluster JSON SHA-256
  `f5c151811743aed20ffc11470253005b38e6edfd602db3ae00a7b52721914f4e`,
  SVG SHA-256
  `462d5dada8bc27623304a6e2faa1c6ed2d0e8ed46040175c73ee27b38ed3bf86`
  and complete match report SHA-256
  `f8bff7cbbfd830673ab33c6cbc5162c116e66d9375d8d807f0c96cb8769330ca`.
- Listening result: open. The explainable/OpenL3 disagreement is preserved for
  review; no method is promoted from clustering metrics alone.
- Decision: integrate the report and visual as advisory evidence. Keep every
  event eligible for MIDI, matching and sampling; a rare articulation must not
  be called noise or removed without listening.
- Problems/risks: normal phrase, pitch, intensity or source-rate differences can
  create a candidate family even when one physical instrument played all notes.
  A single articulation cluster means the conservative selector found no stable
  multi-event split, not that every attack is identical.
- Next smallest step: completed by the conservative GM drum-family proposal
  increment above; continue only after listening to the mixed-kit A/B.

### 2026-07-16 — Phase 3 optional OpenL3 instrument evidence v1

- Goal: test whether a small local learned music representation can add useful
  timbre evidence without weakening the existing explainable matcher.
- Change or experiment: added an opt-in OpenL3 music/mel128/embedding-512 ONNX
  path, an explicit hash-verifying setup script, aligned one-second source and
  rendered-candidate fingerprints, a separate learned shortlist and auditions,
  complete candidate/window evidence, and additive Instrument Bundle v1 fields.
  The default ranking and behavior remain unchanged.
- Inputs: the authorised user-written Lidl bass fixture, original song seconds
  200–215, and its aligned 20-note Sunofriend repair MIDI; eight role-specific
  General MIDI bass programs rendered through the configured local SoundFont.
- Model/runtime/checkpoint: OpenL3 music mel128 embedding-512 ONNX on
  ONNX Runtime CPU; original weights CC-BY-4.0; checkpoint SHA-256
  `81c24c8a723054717fdea5c7448acb6023baaf70a0fc526deb030c2032db0ed3`.
- Evidence and metrics: all eight candidates had 15 aligned active windows.
  OpenL3 ranked Fretless Bass first at 97.589 relative cosine similarity,
  followed by Acoustic Bass at 97.511; the existing explainable score instead
  ranked Acoustic Bass first at 86.521 and Fretless Bass fifth at 82.334. Two
  fresh complete runs produced byte-identical evidence JSON SHA-256
  `83c955b6545bb1c9951e9a83b2458f8082b264965211baf963acc49dfa0d7d9a`
  and report SHA-256
  `4f169110b04333032f24839c37026a2226a91a2be93f8e9641984110c2ad59cf`.
- Listening result: open. The separate Fretless and Acoustic Bass auditions are
  retained specifically for blinded/full-mix comparison; no preference is
  inferred from the scores.
- Decision: integrate OpenL3 as optional advisory evidence only. Never download
  it during matching, accept an altered checkpoint, call cosine similarity
  confidence, blend it into the explainable score, or change the default order.
- Problems/risks: related music embeddings produce a narrow high-score range;
  the General MIDI SoundFont remains only a proxy for GarageBand patches; a
  strong timbre embedding can still miss articulation, emotion and mix fit.
- Next smallest step: listen to the retained Lidl bass A/B candidates, then add
  source-event clustering for identity/articulation/outlier evidence before
  attempting velocity layers or round robins.

### 2026-07-16 — Phase 2 explicit-choice personal ranking v1

- Goal: reduce repeated comparison effort by showing which alternative the user
  chose in similar past review units, without turning preference history into
  an automatic melody decision.
- Change or experiment: the new `melody-profile` command builds one fresh,
  deterministic local profile only from complete explicitly reviewed correction
  files. `melody-review --ranking-profile` adds a separate history panel based
  on review-unit duration, tracker agreement, selection score and combined-note
  density. Manual decisions have weight 1.0 and explicitly propagated repeated
  choices have weight 0.5. Guided child reviews inherit and hash-check the same
  profile.
- Inputs: deterministic test corrections plus a clearly labelled synthetic
  three-choice technical calibration fixture matched to the private Lidl
  30–45 second lead-vocal golden. The fixture is not a user review, listening
  result or statement of musical preference.
- Model/runtime/checkpoint: no model, checkpoint, network call or hidden
  preference store. Ranking is a deterministic nearest-context calculation over
  explicit local JSON inputs.
- Evidence and metrics: the profile contains one input, three explicit choices
  and three contextual observations, one per automatic alternative. On the
  three Lidl units, the matching artificial choices appeared history-first as
  GAME boundary, combined and Basic Pitch respectively. Two profile builds had
  identical SHA-256 `f1ef178ddd0357b04bdb032369f3daf16546c515f31f3870fbadb6129954ab39`.
  Two fresh review packages were byte-identical across 42 files. All three
  candidate orders remained `basic-pitch`, `game-boundary`, `combined`; all
  correction seeds remained unreviewed and selected `combined`; raw candidates
  remained unmodified.
- Listening result: deliberately not claimed. The synthetic fixture proves the
  immutable advisory mechanism, not that any hint matches the user's taste.
  Real calibration begins only after the user supplies actual reviewed choices.
- Decision: integrate the advisory panel and explicit profile builder. Call its
  score a relative personal-history ranking, never confidence. Reject incomplete
  reviews, duplicate input hashes, invalid propagation, changed profile hashes
  and existing output paths. Never scan for or silently update preference data.
- Problems/risks: sparse or stylistically narrow history can rank an irrelevant
  choice first, context features are deliberately small and propagated choices
  are not independent decisions. Candidate order and the combined default stay
  fixed so a misleading hint cannot silently change output.
- Next smallest step: collect genuine reviewed choices and record whether the
  history panel reduces review time or improves the final GarageBand A/B. Then
  begin Phase 3 Instrument Intelligence v2 without treating Phase 2 listening
  calibration as complete evidence.

### 2026-07-16 — Phase 2 explicit repeated-unit propagation v1

- Goal: reduce repeated listening decisions without allowing similarity scores
  to make musical choices automatically.
- Change or experiment: `melody-review` now compares every unit pair using a
  fixed conservative policy: at least three notes, exact note-count equality,
  matching absolute pitches and contour intervals, similar unit/content
  duration and onset timing within a quarter beat at p90. Accepted pairs expose
  an explicit browser button that copies only the selected alternative name;
  the target retains its own notes, timing and source evidence. The correction
  audit records the source unit, canonical pair and policy, and
  `melody-apply` rejects tampering or mismatched choices.
- Inputs: the private Lidl 30–45 second lead-vocal golden and deterministic
  synthetic positive/rejection fixtures covering exact repeats, octave
  transposition, sparse units and unequal note counts.
- Model/runtime/checkpoint: no model or checkpoint. This is a deterministic
  review-layer comparison over the immutable combined agreed-F0 MIDI.
- Evidence and metrics: the three Lidl units produced three evaluated pairs and
  zero accepted pairs; all had unequal note counts and therefore could not be
  treated as repeats. The exact synthetic repeat scored 1.000 for overall,
  pitch, interval and timing evidence. Its octave-transposed counterpart was
  rejected despite interval similarity 1.000. Two fresh Lidl packages were
  byte identical across 42 files, with 41 recorded artifacts and
  `raw_candidates_mutated: false`.
- Listening result: no Lidl selection changed because no strong repeat existed.
  Positive UI behaviour is regression-tested with synthetic repeated phrases;
  a future longer authorised golden is still needed for human A/B assessment.
- Decision: integrate pairwise suggestions and explicit propagation. Do not
  infer octave-equivalent or approximate note-count repeats in v1, do not copy
  notes between units, and invalidate dependent propagation after a manual
  source change.
- Problems/risks: the initial policy favours precision over recall and will miss
  repeated phrases with ornaments, omissions or deliberate octave changes.
  Connected repeat groups remain informational; every propagation action is
  still pairwise and explicit.
- Next smallest step: learn a local personal ranking/calibration signal only
  from explicit reviewed choices, without changing automatic candidates.

### 2026-07-16 — Phase 2 unresolved-unit short guides v1

- Goal: let a user reject all automatic melodies for one manageable review
  unit and add guidance without having to hum a complete song.
- Change or experiment: the review page now has an explicit unresolved choice.
  `melody-guide` verifies the complete parent review and tracker evidence, then
  adds a fourth alternative to one numbered unit from a short hum, whistle,
  contour, single-note rhythm or tapped rhythm. Hum-like guides contribute
  rhythm and contour; single-note and tap inputs contribute rhythm only. Every
  accepted pitch is still measured from the immutable source pYIN frames.
- Inputs: the private Lidl 30–45 second lead-vocal golden, its three-unit Phase
  2 review, and a 4.371-second unit-2 source excerpt used only as a technical
  self-guide ceiling fixture. This is not presented as a realistic humming
  result or as training data.
- Model/runtime/checkpoint: existing local pYIN/Basic Pitch stack and
  FluidSynth preview; no new model, network call or checkpoint.
- Evidence and metrics: all 41 parent artifacts were hash-verified. The guide
  detector proposed three notes and source gating accepted three at MIDI
  pitches 63, 63 and 64. Alignment offset was 5.238668 seconds, transposition
  zero and alignment score 0.988569. Only unit 2 gained `guide-assisted`; units
  1 and 3 retained exactly three alternatives. The child package contains 46
  recorded artifacts plus its manifest, and two independent builds were byte
  identical across all 47 files. The guide evaluation reported chroma 0.787
  and supported-note ratio 0.333, reinforcing that its label is not an
  automatic recommendation.
- Listening result: human recognition review remains pending. The ceiling
  fixture proves timing, evidence gating, rendering and audit flow, but cannot
  establish that an imperfect human hum will be preferable.
- Decision: integrate unresolved export and `melody-guide`; accept one guide
  and one unit per fresh run, preserve every automatic candidate, and refuse
  `melody-apply` while any exported choice remains unresolved. No-source
  evidence and tap/single-note pitch-ignoring paths have regression tests.
- Problems/risks: a guide can improve segmentation yet still be a worse
  musical abstraction, and weak pYIN regions cannot be repaired by this path.
  v1 evaluates one guide for one unit and does not yet combine guided units.
- Next smallest step: identify genuinely repeated review units and offer
  explicit propagation of an accepted choice without modifying unrelated
  phrases.

### 2026-07-16 — Phase 2 musical-length review units v1

- Goal: replace the nine short note-cluster cards in the recognition-first
  review with a smaller number of musical-scale decisions.
- Change or experiment: `melody-review` now groups consecutive immutable
  boundary clusters into configurable review units, defaulting to two-to-eight
  bars at four beats per bar. Each unit retains its original cluster indices,
  weighted agreement/selection evidence, providers, duration status and all
  three alternatives. Bar duration is derived from BPM; the implementation
  explicitly does not claim that an excerpt starts on a confirmed downbeat.
- Inputs: the private Lidl lead-vocal 30–45 second golden, B major, 119 BPM,
  A=440, and its completed boundary-repair v2 tracker run.
- Model/runtime/checkpoint: no new model. The increment is a deterministic
  review-layer transformation over the existing hashed Basic Pitch, GAME,
  pYIN and RMVPE evidence.
- Evidence and metrics: nine source clusters became three review units covering
  clusters 0–2, 3–5 and 6–8. Their content spans are 2.091, 2.167 and 2.005
  bars; none is below the two-bar preference or above the eight-bar maximum.
  Each unit retains raw Basic Pitch, GAME-boundary and combined MIDI, neutral
  audio, source overlay and evaluation. For example, unit 3 strong-onset F1
  was 0.333/0.462/0.400 respectively, while chroma was
  0.963/0.935/0.937—useful evidence that one metric still cannot choose the
  intended melody.
- Listening result: the new local page presents three longer recognition
  choices instead of nine fragmented decisions. Human selection remains
  pending. The in-app browser security policy does not permit automated
  navigation to local `file://` pages, so the page is handed off for local
  review rather than bypassing that restriction.
- Decision: integrate musical-length grouping as the `melody-review` default,
  expose `--minimum-bars`, `--maximum-bars` and `--beats-per-bar`, retain
  `phrase_count` for compatibility, and add explicit source-cluster and
  review-unit counts to the manifest and correction audit.
- Problems/risks: duration in bars is not the same as downbeat-aligned musical
  form; a confirmed downbeat is unavailable for this excerpt. Short sources or
  widely isolated clusters remain visible with an explicit warning instead of
  being stretched or joined across more than the configured maximum.
- Next smallest step: add a short hum/tap/contour guide only to a review unit
  the user marks unresolved, retaining the three automatic alternatives and
  source-pitch support rules.

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
