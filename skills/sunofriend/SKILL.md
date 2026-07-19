---
name: sunofriend
description: Use the local Sunofriend CLI to convert isolated Suno/Moises WAV stems and lead or backing vocals into evaluated GarageBand-ready MIDI; compare immutable AI transcription lanes, benchmark verified fresh-process or bounded exact-repeat local AI runs, reuse and benchmark an explicit exact MuScriptor raw-result cache, partition model-reported labels exactly, and review existing source/MIDI alternatives; build blind exact-source-window, fixed-window sample-RMS-matched MIDI A/B reviews with explicit heard and choice evidence; render cached neutral previews, save explicit solo/full-mix choices, hear the selected arrangement and export unchanged choices in a GarageBand handoff through the loopback-only Workbench; combine tracker consensus, phrase-by-phrase alternatives, repeated phrases, hummed guidance and local advisory review-history profiles; create short experimental MIDI-guided or pinned learned target/residual cleanup pairs, split reviewed mixed-role MIDI into separate body/pluck challengers, and compare complete, sampled and harmonic-plus-noise sounds on one fixed monophonic MIDI; inventory, sound-match, audition, build self-contained SF2 sample instruments, or package MIDI plus sound in Instrument Bundle v1; preview or play results; change MIDI key, BPM, tuning, and downbeat alignment; and store or transform Clip v1 parts. Use for Sunofriend, stems-to-MIDI, vocal melody MIDI, GarageBand timing, MIDI mashups, instrument selection, stem sample instruments, tempo or transposition changes, and stem-versus-MIDI accuracy. Do not use for generic stem separation, mastering, lyric writing, downloading third-party plug-ins, or editing a DAW GUI.
---

# Sunofriend

Use the packaged `sunofriend` CLI as the deterministic audio and MIDI engine.
Do not reimplement transcription, evaluation, or MIDI transformation in ad-hoc
scripts.

## Preflight

1. Work locally. Do not upload stems, vocals, MIDI, or chord files.
2. Resolve `sunofriend` from `PATH`. In the Sunofriend repository, fall back to
   `.venv/bin/sunofriend`.
3. Run `sunofriend --version`, `sunofriend --help`, and the selected command's
   `--help` before constructing a command.
4. Run the narrowest capability check:
   - `sunofriend doctor --require transcribe` for lead or backing vocals and
     short `melody-guide` pitch/contour guides.
   - `sunofriend ai-doctor --require muscriptor-checkpoint` before explicitly
     requesting the optional `vocal-melody --muscriptor` challenger.
   - `sunofriend ai-doctor --require muscriptor-checkpoint` before producing
     MuScriptor lanes for `ai-matrix`. The matrix command itself uses completed
     local runs and needs no model inference capability.
   - `sunofriend ai-benchmark` needs no model capability: it reads at least two
     completed comparable MuScriptor runs, verifies their immutable evidence
     and starts no worker. Run the MuScriptor checkpoint check only when making
     new repetitions first.
   - `sunofriend ai-setting-compare` needs no model capability and starts no
     worker. It reads at least two completed fresh beam-1 controls and two
     completed fresh beam-2 challengers. Run
     `sunofriend ai-doctor --require muscriptor-checkpoint` only when creating
     those runs first.
   - `sunofriend ai-transcribe-session` needs
     `sunofriend ai-doctor --require muscriptor-checkpoint`. Read both
     `ai-transcribe-session --help` and `ai-session-benchmark --help`. It runs
     2–20 exact serial copies of one fixed MuScriptor request through one
     loaded local model; use it only as a bounded diagnostic benchmark.
   - `sunofriend ai-session-benchmark` itself needs no model capability and
     starts no worker. It verifies one completed session. If direct
     fresh-process comparison is requested, require at least two completed
     exact comparable `ai-transcribe` runs through repeated `--fresh-run`.
   - `sunofriend ai-transcribe --application-cache-dir PRIVATE_DIR` needs the
     normal `sunofriend ai-doctor --require muscriptor-checkpoint` preflight.
     Read `ai-transcribe --help`; the cache is explicit, local, MuScriptor-only
     and disabled when the option is omitted. A verified hit still needs the
     existing checkpoint, worker and runtime so their identities can be
     rechecked, even though it starts no worker or model.
     Use a dedicated owner-only cache root (mode `0700`); the command rejects
     an existing root with any group or other permissions. Keep it outside
     every immutable run-output tree; the cache and output roots may not
     contain one another.
   - `sunofriend ai-cache-benchmark` needs no model capability and starts no
     worker. Read its help and supply one completed `miss-stored` run plus at
     least two completed `verified-hit` runs for the same immutable entry.
   - `sunofriend ai-label-split` needs no audio, model or preview capability.
     It verifies and partitions one completed immutable AI run.
   - `sunofriend ai-doctor --require game` before a standalone GAME vocal
     boundary/pitch bake-off. Its explicit setup command is
     `scripts/setup-game-model.sh`; inference itself must remain offline.
   - `sunofriend ai-doctor --require rmvpe` before a standalone RMVPE F0
     bake-off. Its explicit setup command is `scripts/setup-rmvpe-model.sh`;
     inference must use the existing local ONNX file and remain offline.
   - `sunofriend ai-doctor --require pesto` before a standalone PESTO F0
     bake-off. Its explicit setup command is `scripts/setup-pesto-model.sh`;
     inference must use the hash-checked local `.ckpt` file and remain offline.
   - `sunofriend ai-doctor --require demucs` before the experimental learned
     `ai-cleanup` workflow. The explicit setup action is
     `SUNOFRIEND_ACCEPT_DEMUCS_PRIVATE_EVALUATION=1 scripts/setup-demucs-model.sh`;
     keep the checkpoint external/private, verify its full hash and never
     download or select a model during inference.
   - `sunofriend doctor --require convert` for instrumental stem conversion.
   - `sunofriend doctor --require convert` for the short experimental
     `midi-mask` target/residual workflow.
   - `sunofriend doctor --require convert` and `preview` for the experimental
     `midi-role-split` listening package. `--no-preview` removes the preview
     requirement but still requires the hash-pinned cluster evidence.
   - `sunofriend midi-role-split-resolve` needs no audio, ML or preview
     capability check. It reads one explicit reviewed export and verifies the
     unchanged role-split evidence tree before copying a selected MIDI.
   - `sunofriend doctor --require preview` for `timbre-resynthesis`. Its
     complete-patch and optional source-SF2 controls require FluidSynth; the
     fitted harmonic-plus-noise candidate itself uses the normal audio runtime.
   - `sunofriend doctor --require preview` for `midi-ab-review`; it renders
     both unchanged MIDI candidates through one pinned dry FluidSynth/SF2/
     program/gain contract. `midi-ab-resolve` itself needs no audio, ML or
     preview capability: it verifies one explicitly exported reviewed JSON
     against the separately supplied original unchanged package directory.
   - `sunofriend doctor --require preview` for offline rendering, including
     `melody-review` and `melody-guide` MIDI-only and source-overlay
     alternatives.
   - `sunofriend melody-profile` itself needs no audio/ML capability check; it
     reads only the explicitly supplied reviewed correction JSON files.
   - `sunofriend doctor --require playback` for live MIDI.
   - `sunofriend instrument-inventory` needs no audio/ML capability check.
   - `sunofriend instrument-feedback` and `instrument-profile` need no audio/ML
     capability check. They read explicit local Bundle/review JSON and MIDI
     hashes only.
   - `sunofriend doctor --require convert` for factory-sample matching or
     stem-derived sample instruments. Also require `preview` for rendered GM
     matches and for sample instruments unless using `--no-preview`.
     Optional learned instrument evidence additionally needs the explicit,
     existing local OpenL3 path created by `scripts/setup-openl3-model.sh`;
     matching itself must remain offline and hash-check the model.
   - `sunofriend instrument-bundle` has the same requirements as both
     `instrument-match` and `sample-pack`. `--no-gm --no-preview` removes the
     FluidSynth requirement; `--no-source-instrument` removes sampling.
   - `sunofriend sample-pack-review` needs `convert` to extract local listening
     WAVs. `sample-pack-apply` also needs `convert`, plus `preview` unless
     `--no-preview` is used.
   - `sunofriend sample-pack-boundary-review` needs `preview` for its velocity
     ramps and constant-velocity repeated-beat comparison.
   - `sunofriend workbench PROJECT --inspect`,
     `sunofriend workbench PROJECT --export-review FRESH.json` and a Workbench
     using only existing preview WAVs need no audio, ML or playback capability.
     Inspect and private review export start no server or model. Run
     `sunofriend doctor --require preview` before using the site's
     explicit neutral-preview, selected-arrangement or GarageBand-handoff
     render actions.
5. Inventory the input directory read-only. Confirm files exist and identify
   stem roles, chord PDF, metronome, key, BPM, and tuning.
6. Use absolute, quoted paths and a fresh output outside the source folder.
   Never add `--overwrite` unless the user explicitly asks to replace output.
7. If the CLI or a dependency is missing, report the exact component. Install
   packages or download a SoundFont only when setup is within the request.

## Choose the workflow

- Whole instrumental stem folder: use `listen-all`; default to
  `--conversion-mode repair` and leave evaluation enabled.
- Existing source/MIDI/preview result space: use `workbench` with the original
  stem directory and only the narrow candidate roots intended for that song.
  It is a loopback-only presentation and explicit-decision boundary, not a
  transcriber. Prefer an explicit `sunofriend.workbench-catalog.v1` document
  when filenames cannot distinguish songs or audible roles. Treat at most
  three primary candidates as the normal result space, keep diagnostic files
  advanced, and do not infer preference from audition events, dwell time or
  unclicked defaults. Prefer the content-addressed role-neutral preview when an
  existing WAV is absent or uses a different sound. Its shared browser
  position is synchronized in seconds, not claimed sample-accurate. Completed
  AI runs expose path-free model/config, label, density, boundary and runtime
  diagnostics. For an application-cache hit, require the card to state that no
  AI model ran and interpret elapsed time/RTF as pipeline-not-inference. Do not
  confuse that raw-result cache with the role-neutral FluidSynth preview cache:
  Workbench populates only the latter and merely displays completed AI-cache
  provenance. Treat severe decoder or zero-note candidates as
  diagnostic-only; ordinary role leakage remains auditionable. The
  selected arrangement and handoff include only the latest active main and
  explicit optional choices; numbered MIDI files in the ZIP must remain exact
  copies, while the combined GM arrangement is only a proxy. Submission is
  absent in v1; the contribution preview is only an exact redacted-data
  disclosure. An explicit catalog may add one `review_question` and a short
  `listening_focus` list per stem; these prompts guide listening only and must
  not rank, preselect or promote a candidate. For selected pairs with the same
  candidate-origin source audio, inspect the exact-pitch/onset overlap
  diagnostic. AI MIDI uses the verified run source SHA-256; non-AI MIDI
  without that provenance falls back to the review-stem source SHA-256. Its
  fixed substantial-warning policy is at least eight greedy one-to-one matches
  within 80 ms and at least 80% coverage of each candidate. This is not an
  accuracy or separation score and must never deduplicate, merge, rank or alter
  MIDI. Keep the arrangement available for listening; a GarageBand handoff
  containing such a pair requires the latest decision for both candidates to
  be saved in `full_mix` context. Use
  `workbench PROJECT --export-review FRESH.json` to write the exact private
  review without a server. Reuse the original project, every candidate root,
  optional catalog and state directory so the command targets the same review
  identity; never overwrite an existing path and warn that the result may
  contain absolute paths and private notes.
- Several completed immutable MuScriptor lanes: use `ai-matrix` with explicit
  repeated `LANE=RUN_DIR` values and a fresh `--out` JSON. Include M0
  unconditioned full mix, M1 discovered-label conditioning, M2 known-label
  conditioning and M3/M4 role lanes only when each run actually exists. The
  command verifies source, checkpoint, model-config, candidate and MIDI hashes
  and reports per-instrument quality, label stability, five-second-boundary
  activity and cross-lane same-pitch/onset overlap. Never infer a winner from
  overlap or automated quality, and never omit a failed/no-evidence lane from
  the audit. The pinned MuScriptor 0.2.1 baseline is greedy, batch 1, beam 1,
  CFG 1.0 and independent five-second chunks; it does not support prelude
  forcing, so do not request or claim it.
- Repeated comparable MuScriptor runs: use `ai-benchmark` with at least two
  repeated `--run RUN_DIR` values and a fresh `--out`. Require identical source,
  excerpt, BPM, requested roles, effective device, checkpoint, config, worker
  and execution profile, path-free platform/Python/PyTorch/MuScriptor runtime
  identity and source-frame-derived actual processed duration. Require
  timezone-aware, sequential, non-overlapping repetition windows and nested
  pipeline/subprocess/worker timings. Report pipeline/subprocess/inclusive-
  transcription RTF, model-load and first-note latency, chunks, process peak
  RSS, boundary diagnostics and candidate/MIDI repeatability. Inclusive
  transcription includes MuScriptor preprocessing, condition construction and
  decoding. A current repetition uses a fresh process and
  reloads the model; the OS file cache is uncontrolled, so never call a later
  repetition warm-model evidence. The report is diagnostic and cannot promote
  a musical candidate.
  A pre-session/cache v1 manifest without the newer execution fields is valid
  only while all hash-pinned external evidence remains unchanged and when it
  has a successful non-empty subprocess command with no session or
  application-cache evidence; report its explicit legacy-evidence label. A
  historical run whose external worker changed cannot be re-verified.
- One-variable MuScriptor decoding diagnostic: use `ai-setting-compare` with at
  least two repeated `--control-run RUN_DIR` values and two repeated
  `--challenger-run RUN_DIR` values. V1 requires current, sequential,
  cache-disabled fresh-process runs and exactly `beam_size` 1→2 with the derived
  strategy `greedy`→`beam-search`; source, actual excerpt, BPM, ordered roles,
  checkpoint/config/worker/runtime/device and every other request and execution
  field must match. Each arm must be exactly repeatable in raw/normalized
  candidates, note payload, MIDI, tracked derived artifacts and note count.
  Reject legacy, session, cache, overlapping, non-repeatable or multi-setting
  evidence. Treat candidate-JSON differences as execution provenance unless
  note-payload or any auditionable MIDI hashes also differ. The path-free
  report remains potentially identifying through hashes/runtime identity and
  cannot rank, select, mutate or promote either arm. Timing is observed under an
  uncontrolled OS cache and non-randomized order. A same-patch preview at one
  configured gain is preliminary only. Require a source-aligned loop,
  same-renderer, same-patch and separately verified level-matched listening
  decision before changing a preset or default when musical output differs.
- Blind comparison of two completed MIDI candidates: use
  `midi-ab-review SOURCE FIRST.mid SECOND.mid` with a positive `--bpm`, a fresh
  `--out-dir`, required `--midi-time-at-source-start SECONDS` and one or more
  repeated `--interval START END "FOCUS"` values. Interpret bounds as exact
  reference-source seconds. Each interval must be non-overlapping, inside the
  source and 0.5–15 seconds long. The MIDI-time value pins the common candidate
  time that corresponds to source time zero and must land on a source sample
  frame. Use `0` only when the source WAV and both MIDI files share their excerpt origin;
  never infer alignment. Pin `--soundfont` when reproducibility matters;
  `--gm-program` is zero-based and defaults to 4. Both candidates use the same
  dry FluidSynth executable, SF2, program, gain and source sample rate. Only
  the louder candidate is attenuated to the quieter fixed-window sample RMS;
  both candidate windows must reach at least -60 dBFS RMS, and the source
  remains an unlevelled reference. Do not call this LUFS, true-peak or
  perceived-loudness matching. A secret random nonce assigns A/B per unit; only
  its public commitment may appear outside the answer key. Do not open the
  separate answer key before review. Audio auto-loops and the shared playhead
  is scoped to each unit. Require the reviewer to hear source/A/B, tick all
  three heard boxes, choose A/B/equivalent/neither/cannot tell for every loop,
  mark the review complete and export `midi_ab_review.reviewed.json`. Then use
  `midi-ab-resolve REVIEWED.json` with
  `--package-dir ORIGINAL_UNCHANGED_REVIEW_DIR` and `--out FRESH.json` to reveal
  the verified identity mapping. The resolver must allow only review
  status/count, heard, choice and notes changes and reject swapped A/B or
  cross-unit slots and changed timing, focus or geometry. Treat the result as
  listening evidence only: neither command edits MIDI, selects a Workbench candidate,
  promotes a preset or changes a default. Exact common source-frame windows do
  not imply decoded, sample-accurate browser switching; Workbench still
  switches at a shared position in seconds.
  The complete command shapes are:
  `sunofriend midi-ab-review SOURCE FIRST.mid SECOND.mid --interval START END
  "FOCUS" [--interval START END "FOCUS" ...] --bpm N
  --midi-time-at-source-start SECONDS [--gm-program 4] [--soundfont FILE]
  [--question TEXT] --out-dir FRESH` and
  `sunofriend midi-ab-resolve REVIEWED.json --package-dir
  ORIGINAL_UNCHANGED_REVIEW_DIR --out FRESH.json`.
- Bounded exact-repeat MuScriptor timing: use `ai-transcribe-session` only to
  repeat one byte-identical request template serially 2–20 times with one
  parent-owned loaded model. Keep source, ordered roles, excerpt, BPM,
  checkpoint, model config, device and decode options fixed. The inherited Unix
  socket pair opens no listening port and the worker exits at the declared
  bound. Do not present it as a multi-song/role service, daemon, production
  worker or content cache. Request 1 has a resident model but no earlier
  transcription and is not warm/cold evidence; only requests 2+ are
  reused-model warm. Startup/model load is separate, application cache hits
  are zero and the OS file cache is uncontrolled.
- Completed bounded session: use `ai-session-benchmark SESSION --out FRESH`
  for the path-free read-only report. To compare with fresh processes, provide
  at least two exact comparable completed runs using repeated `--fresh-run`.
  Require exact candidate JSON, MIDI and note-count repeatability. Do not feed
  session repetitions to fresh-only `ai-benchmark`; it must reject them. Keep
  the session tree private because it contains paths. Treat the path-free
  report as still potentially identifying through hashes and runtime identity,
  not as publication consent.
- Exact unchanged MuScriptor rerun: add
  `--application-cache-dir PRIVATE_DIR` to `ai-transcribe` only when reusing a
  byte-identical deterministic request is intended. Keep source content,
  ordered roles, excerpt, BPM, decode options, checkpoint/config/worker and
  runtime/device identity fixed. The first request is a fresh miss; a verified
  hit must record an empty worker command and no worker, model load or
  inference. Every hit still creates a fresh immutable run and rebuilds current
  quality, expression and MIDI from the cached raw result. Never combine this
  regime with a bounded session or call a cache hit warm-model evidence. Use
  `ai-cache-benchmark --miss-run MISS --hit-run HIT1 --hit-run HIT2 --out FRESH`
  to verify timing and exact output without launching a model. Keep the cache
  private. The report omits paths and caller-supplied run IDs, but hashes,
  timestamps and runtime identity can still identify content or a machine.
  A concurrent losing producer is `miss-verified-existing`: it ran inference,
  verified the winning raw candidate as identical and kept its own timing, but
  it is not the required `miss-stored` benchmark control.
- Mixed-role M4 matrix: require every M4 lane to use the same source audio,
  excerpt and positive BPM, request exactly one role and use a distinct role
  from every other M4 lane. Inspect `m4_role_overlap` for possible duplicated
  or relabelled notes. Never call overlap accuracy, isolation or a winner.
- Exact AI label derivative: use `ai-label-split` only when one completed run
  reports both a wanted label and off-role labels. It writes an exact raw-event
  source-index partition plus deterministic requested/complement MIDI auditions
  without re-running the model. Keep both, retain the byte-identical full
  candidate as the mandatory control and report any MIDI pitch/tick
  quantisation, duplicate collapse or same-pitch truncation. Treat all outputs
  as listening evidence. Keep the byte-identical source-request/source-candidate
  JSON controls private: Workbench uses them to verify raw-event provenance,
  and the request may contain local paths. This is not source separation or
  physical-instrument identification. A zero-note
  requested label is blocked no-evidence; a non-empty split remains
  review-required and must never be promoted automatically.
- One instrumental stem: use `listen` with an explicit supported `--kind`.
- One proposed role inside a mixed pitched stem: use `midi-mask` only on a
  short excerpt with an aligned note-bearing MIDI track. Treat its harmonic
  target and waveform-defined residual as transparent challengers, not a
  physical source identification. Require an explicit `--track-index` for
  multi-track MIDI, preserve both outputs and never promote from reconstruction
  accuracy or metrics alone. A separately requested broadband transient window
  may improve attacks but can admit simultaneous instruments.
- Learned cleanup challenger: use `ai-cleanup` only on a focused mono/stereo
  44.1 kHz excerpt of at most 60 seconds and an existing pinned htdemucs
  checkpoint. Treat `bass`, `drums`, `other` and `vocals` as broad model source
  families, not instrument identities. Preserve the unchanged source, learned
  target, waveform residual and float32 model array. Re-transcribe all audio
  alternatives with the same strongest available transcriber and compare with
  `midi-mask`; never promote from energy, reconstruction or metrics alone.
- Two roles inside one reviewed pitched stem: use `midi-role-split` only after
  a listener identifies the roles and `instrument-match` publishes matching
  `source_event_clusters.json`. Require the body cluster explicitly. Preserve
  the unchanged primary, its exact body/complement partition and every outlier.
  An independently transcribed target/residual may be supplied as a separate
  overlapping challenger, but do not deduplicate, merge or promote it from
  cluster scores. Treat GM programs as contrasting audition proxies, never
  physical-instrument recognition.
- Completed two-role review: use `midi-role-split-resolve` with the user-exported
  reviewed JSON and the unchanged role-split directory. Require every choice
  to be reviewed. Follow the overall decision even when several components are
  useful; never infer a winner from the usefulness fields.
- Stable monophonic MIDI, sound question only: use `timbre-resynthesis` on one
  aligned excerpt of at most 60 seconds. Keep a complete GM patch as the
  mandatory control and supply the earlier source-derived SF2 when available.
  Require identical note signatures, level-match the candidates and treat the
  per-note silence threshold as a functional check only. The harmonic-plus-
  noise result is deterministic DSP, not a trained DDSP model or a playable
  GarageBand instrument. Hand off its review before packaging or promotion.
- Lead or backing vocals: use `vocal-melody` separately. It defaults to
  pYIN/Basic Pitch consensus, conservative repeated-phrase repair and a local
  correction HTML/JSON report. `listen-all` does not include vocals.
- Model-backed vocal alternative: after the user has accepted and installed a
  MuScriptor checkpoint, add `--muscriptor`. Keep the resulting model MIDI as
  an explicit challenger; it does not replace the deterministic primary. Its
  GarageBand variant may use a separately audited source-energy velocity layer
  while the raw model event velocity remains untouched. For backing vocals,
  retain both the MuScriptor line and Sunofriend harmony stack.
- Independent singing-specific evidence: use `ai-transcribe --backend game`
  on a short authorised vocal excerpt. After a golden check, add `--game` to
  `vocal-melody` to publish it as a separate challenger; it must not replace
  the deterministic primary. Use and report an explicit seed (default 0),
  because its D3PM boundary decoder is otherwise stochastic; preserve floating
  pitch in the raw candidate and use the expression MIDI for auditioning. For
  backing vocals, retain the harmony stack and treat GAME and MuScriptor as
  alternative monophonic lines.
- Independent frame-level pitch evidence: use `ai-transcribe --backend rmvpe`
  on the same short authorised vocal excerpt. Treat `rmvpe.frames.json` as the
  primary model evidence and `candidate.mid` as Sunofriend's deterministic
  frame-to-note draft. Do not infer that an upper pitch in backing vocals is
  automatically the intended dominant line.
- Lightweight second F0 opinion: use `ai-transcribe --backend pesto` on the
  same short excerpt. Treat `pesto.frames.json` and the raw
  `pesto.activations.npy` matrix as independent evidence. The frame-to-note
  MIDI is a deterministic review draft, not model-supplied boundaries. Do not
  add PESTO to consensus or promote it from aggregate chroma alone.
- Auditable tracker comparison: use `vocal-trackers` to publish pYIN and raw
  Basic Pitch evidence independently. Supply `--rmvpe-frames` only from a
  completed immutable run on the exact same WAV; the command verifies the
  source and checkpoint hashes before creating a three-way consensus. Supply
  `--game-candidate` with RMVPE to test GAME and Basic Pitch boundaries only
  where pYIN and RMVPE agree on pitch. Preserve all tracker records. Treat
  consensus and boundary-repair MIDI as `review-required` challengers, never
  as the normal `vocal-melody` primary. For backing vocals, retain the
  polyphonic Basic Pitch/harmony evidence rather than reducing the result to
  only a monophonic consensus or repair line.
- Recognition-first lead review: use `melody-review` on a completed
  `vocal-trackers` run with agreed-F0 boundary evidence. It verifies source and
  evidence hashes, requires a fresh output, merges consecutive note clusters
  into two-to-eight-bar units, presents the weakest units first and exports the
  existing correction format. Bar duration does not confirm a downbeat. Do not
  run it on backing vocals, do not choose from metrics alone, and do not call
  its seed reviewed. The user must select or explicitly accept every unit
  before `melody-apply` succeeds.
- Personal review-history hints: use `melody-profile` only on correction files
  the user actually exported as reviewed, then pass the resulting JSON through
  `melody-review --ranking-profile`. Build each profile at a fresh explicit path
  from the complete wanted input set; do not discover correction files, create
  a hidden store or mutate an existing profile. Treat the ranking as advisory
  history, not confidence. It must not reorder candidates, alter the combined
  default, mark a seed reviewed or select a melody. Manual choices have full
  weight and explicit repeated-unit propagation has half weight. Warn when
  legacy choices have only global counts.
- Repeated review units: treat the fixed repeat detector as a conservative
  suggestion, not a decision. It requires absolute pitch, contour, note-count,
  timing and duration agreement. Propagate only through the page's explicit
  button. This copies an alternative name while each target retains its own
  source-backed notes. Do not treat octave-equivalent phrases as accepted v1
  repeats, do not propagate a unit-specific guide, and retain the pair metrics,
  source unit and policy in the exported correction audit.
- Unresolved review unit: after the user marks **None are close**, use
  `melody-guide` with that one-based unit number and a short local WAV. Choose
  `hum`, `whistle` or `contour` for rhythm plus pitch direction, or
  `single-note`/`tap` for rhythm only. The guide may add a fourth alternative
  but its pitch must remain supported by the source pYIN frames. Require a
  fresh child output, verify every parent artifact and never replace the three
  automatic alternatives. A no-evidence guide stays zero-note and unresolved.
  v1 does not combine several guided review units; use repeatable
  `vocal-melody --guide-snippet` inputs for that existing workflow.
- Ambiguous intended vocal line: add a roughly time-aligned WAV with `--guide`;
  add `--prefer-guide` only when the user wants the source-supported guide as
  primary. Use `--guide-offset-seconds` when the recording offset is known.
- A full-song hum is difficult: use repeatable `--guide-snippet
  REFERENCE_WAV HUM_WAV START_SECONDS` inputs, preferably 10–15 seconds each.
  The start may be approximate within two seconds. `--prefer-guide` publishes
  the automatic full-song melody patched only where accepted snippets overlap.
- Reviewed melody JSON exported by the local report: use `melody-apply`.
- Existing stem/MIDI comparison: use `evaluate`.
- BPM-only change preserving bars and ticks: use `midi-tempo`.
- Complete MIDI key, BPM, or recognised Sunofriend tuning change: use
  `midi-transform`.
- Shared starting downbeat while preserving groove and tempo wander: use
  `midi-anchor`.
- Fully straight 4/4 grid: use `midi-align` only after explaining its note-only
  data-loss contract.
- Reusable part storage and versioning: use the `clip-*` commands.
- Installed GarageBand and Audio Unit discovery: use `instrument-inventory`.
- Sound-based instrument shortlisting: use `instrument-match` with the
  unchanged source stem and its aligned MIDI. Keep both factory-asset and
  rendered-GM evidence unless the user requests one path. Add
  `--embedding-model` only when the user requests Phase 3 learned evidence or
  supplies an existing pinned OpenL3 model. Treat its separate order as an
  audition challenger; never merge it into or replace the explainable order.
  Treat `--kind` as a hard candidate-family boundary before ranking. For
  example, `keys` must not promote synth-lead/pad programs; use `synth` or
  `pads` only when that is the intended musical role.
  Always retain `source_event_clusters.json` and its SVG. Treat candidate
  timbre families, articulation groups and outliers as review evidence, not
  physical-instrument recognition. Never remove a rare event from MIDI or a
  sample pack solely because v1 marks it as an outlier.
  Also retain `source_event_dynamics.json` and its SVG. Treat its source-level
  layers and alternate-sample sets as listening candidates only; never call
  them valid velocity layers or round robins without comparing the indexed
  source events. They must not alter MIDI velocity, sample selection or
  sampler zones automatically.
  Also retain `source_sample_loops.json`, its SVG and any `loop-auditions/`
  WAVs. Treat ranked boundaries as advisory listening evidence only. Never
  infer acceptance from the continuity score, never call a raw repeat seamless,
  and confirm that the generated SF2/SFZ remain unlooped. Drum and percussion
  one-shots should be reported as not applicable.
  For `kick`, `snare`, `hat`, `cymbals`, `toms`, `other_kit` or `drums`, leave
  GM enabled to produce `gm_drum_family_mapping.json` plus a separate proposed
  channel-10 MIDI/WAV. The mapper splits an audio family by its existing note
  before scoring, preserves outliers, and changes a valid role note only after
  the documented score-55/eight-point guardrails. These thresholds are policy,
  not confidence. Never replace the source MIDI or call the proposed copy an
  accepted repair without listening with the intended kit.
- New instruments from authorised isolated source notes: use `sample-pack`.
  Treat `sunofriend-instrument.aupreset` as the GarageBand-selectable wrapper
  and `sunofriend-instrument.sf2` as its self-contained sound bank. GarageBand's
  preset chooser greys out raw SF2 files.
  Read `instrument_usability.json` before recommending the bank. A successful
  build with `status: texture-only` is not a main instrument: use a complete
  GarageBand/GM patch on the primary MIDI track and offer the sampler only as
  an optional quiet texture layer. `review-required` means mapping and duration
  gates passed, not that tone or tuning has been accepted. Play the usability
  audition, which covers every performance pitch and four velocity probes.
  Silence or abrupt endings are functional failures, not timbre preferences.
  Do not add `--allow-polyphonic` unless the user explicitly accepts chords or
  bleed baked into each sample.
  Use its source-event report to compare selected zones with unselected events;
  `selected_for_sample_pack` is an audit of the existing selector, not a
  cluster-driven decision. `--embedding-model` may add the OpenL3 opinion for
  drums or pitched sources even when GM auditions are disabled.
- Applying reviewed source dynamics: use `sample-pack-review` on an unchanged
  v2 directory, hand off its HTML, and wait for the user-exported reviewed JSON.
  Each event must retain the exact isolated evidence plus its pinned source
  context and role audition. Drum/percussion roles use a repeated beat; pitched
  roles use a short sampler pitch phrase. Explain that source context retains
  relative stem level, role auditions are normalised for timbre comparison,
  and neither makes a selection.
  Never mark a unit accepted/rejected or select a primary on the user's behalf.
  Use `sample-pack-apply` only on that reviewed export and always write a fresh
  v3 directory. It permits one accepted unit per MIDI pitch and validates all
  pinned source, MIDI, v2 sample/SF2, cluster/dynamics and review-audio hashes.
  Report only features actually accepted: SF2/AUSampler applies velocity
  layers only when the review accepted them; accepted alternates become
  separate GarageBand A/B banks and true SFZ sequence round robin. If neither
  was accepted, state that both features are absent. Keep `baseline-v2/` as
  the rollback. Use the zone audition to verify mappings, then the generated
  performance audition to compare the same representative source rhythm
  through the source stem, v2 bank and v3 bank. State its bar/beat/second
  window, pitch coverage, note and velocity range, channel-1 routing and that
  it is an audition-only derivative rather than a source-MIDI mutation.
  When velocity layers exist, also use the generated velocity sweep to compare
  the v2 single-sample response with the exact reviewed v3 transition. Report
  every boundary and transition pair, sweep velocities and hashes; never infer
  a better boundary or alter the reviewed mapping from the sweep alone.
  If the transition needs adjustment, use `sample-pack-boundary-review` on the
  unchanged completed v3, hand off its HTML and wait for the user's exported
  JSON. Never select even the current mapping for the user. Require a lower-
  event-only choice, upper-event-only choice and the candidate boundaries.
  Compare the two events first with identical constant-velocity repeated-beat
  MIDI, then compare every complete mapping with one common velocity ramp.
  Report the source MIDI's actual velocity range and warn when a layer is
  unreachable. Candidates may deactivate an accepted event but must not add a
  source event or alter sample audio. Use
  `sample-pack-boundary-apply` only on the explicitly reviewed, hash-pinned
  v2 export and write a fresh v3 directory; it may select one of the already
  accepted sources or a reviewed boundary, but must not change source MIDI.
- Blinded v2/v3 close-out: use `sample-pack-ab-review` with one or more
  completed, unchanged v3 directories. Hand off `sample_ab_review.html` and
  explicitly tell the user not to open its separate answer key first. Require
  Candidate A, Candidate B, equivalent or neither for every role. The source
  reference is not a candidate, and any velocity sweep uses the same hidden
  mapping. Use `sample-pack-ab-resolve` only on the user's reviewed export; it
  must verify every v3 report, copied WAV, manifest and answer-key hash. Never
  reveal or infer the v2/v3 mapping before review, and never turn the resolved
  preference into an automatic sampler change.
- Normal combined MIDI/sound/match handoff: use `instrument-bundle`. It copies
  the source WAV by default, so use `--no-source-audio` when portability is not
  wanted. Use `--no-source-instrument` unless sampling is authorised. A
  `partial` bundle is valid only when its warnings explain the missing sound or
  match component.
  A `complete` bundle may correctly contain a `texture-only` source instrument:
  the artifact build succeeded, but the recipe must make a complete patch
  primary. Report the separate bundle and source-instrument statuses.
- Explicit DAW patch choice: use `instrument-feedback` only after the user has
  stated the exact patch and listening result. Pin it to the unchanged Bundle
  v1 directory, record full-mix or solo context, comparisons and notes, and
  write a fresh reviewed JSON. Never infer preferences from match order, file
  presence or an unreviewed audition.
- Personal patch history: use `instrument-profile` only with the complete set
  of explicitly named reviewed feedback files, then pass it with
  `instrument-bundle --preference-profile`. Treat history-first as an advisory
  audition hint, not confidence or selection. It must not reorder factory, GM
  or OpenL3 evidence, change the portable program, select a patch or bypass the
  source-instrument usability status.
- Offline audition: use `preview`; live MIDI: use `midi-ports` then `play`.

Read the live command help for exact options. Typical command shapes are:

```bash
sunofriend listen-all "$INPUT" \
  --out-dir "$OUTPUT" \
  --conversion-mode repair

sunofriend workbench "$INPUT" \
  --candidate-root "$OUTPUT" \
  --open

sunofriend workbench "$INPUT" \
  --candidate-root "$OUTPUT" \
  --catalog "$WORKBENCH_CATALOG" \
  --state-dir "$WORKBENCH_STATE" \
  --export-review "$FRESH_PRIVATE_REVIEW"

sunofriend vocal-melody "$VOCAL_STEM" \
  --role lead \
  --out-dir "$OUTPUT"

sunofriend ai-transcribe "$VOCAL_STEM" \
  --backend game \
  --out-dir "$FRESH_OUTPUT" \
  --bpm "$BPM" \
  --instrument voice \
  --language en \
  --device cpu \
  --seed 0

sunofriend ai-transcribe "$VOCAL_STEM" \
  --backend rmvpe \
  --out-dir "$FRESH_OUTPUT" \
  --bpm "$BPM" \
  --instrument "lead vocal" \
  --device cpu

sunofriend midi-mask "$MIXED_PITCHED_STEM" "$ALIGNED_MULTI_TRACK_MIDI" \
  --track-index "$ZERO_BASED_ROLE_INDEX" \
  --start-seconds "$START" \
  --end-seconds "$END" \
  --out-dir "$FRESH_OUTPUT"

sunofriend ai-cleanup "$STEM" \
  --target bass \
  --start-seconds "$START" \
  --end-seconds "$END" \
  --out-dir "$FRESH_LEARNED_OUTPUT"

sunofriend midi-role-split "$PRIMARY_MIDI" "$SOURCE_EVENT_CLUSTERS" \
  --body-cluster "$EXPLICIT_CLUSTER" \
  --secondary-midi "$INDEPENDENT_RESIDUAL_MIDI" \
  --secondary-audio "$RESIDUAL_WAV" \
  --cleanup-review "$USER_EXPORTED_CLEANUP_REVIEW" \
  --out-dir "$FRESH_ROLE_SPLIT_REVIEW"

sunofriend midi-role-split-resolve \
  "$USER_EXPORTED_ROLE_SPLIT_REVIEW" \
  "$UNCHANGED_ROLE_SPLIT_DIRECTORY" \
  --out-dir "$FRESH_ROLE_SPLIT_RESOLUTION"

sunofriend timbre-resynthesis "$ALIGNED_SOURCE_EXCERPT" "$FIXED_MONO_MIDI" \
  --gm-program 39 \
  --source-soundfont "$EARLIER_SOURCE_SF2" \
  --source-soundfont-program 0 \
  --out-dir "$FRESH_TIMBRE_REVIEW"

sunofriend ai-transcribe "$VOCAL_STEM" \
  --backend pesto \
  --out-dir "$FRESH_OUTPUT" \
  --bpm "$BPM" \
  --instrument "lead vocal" \
  --device cpu

sunofriend vocal-trackers "$VOCAL_STEM" \
  --role lead \
  --bpm "$BPM" \
  --rmvpe-frames "$RMVPE_RUN/rmvpe.frames.json" \
  --game-candidate "$GAME_RUN/candidate.json" \
  --out-dir "$FRESH_OUTPUT"

sunofriend melody-review "$VOCAL_TRACKER_RUN" \
  --out-dir "$FRESH_PHRASE_REVIEW" \
  --minimum-bars 2 \
  --maximum-bars 8 \
  --beats-per-bar 4

sunofriend melody-profile \
  "$REVIEWED_CORRECTION_A" \
  "$REVIEWED_CORRECTION_B" \
  --out "$FRESH_MELODY_PROFILE"

sunofriend melody-review "$VOCAL_TRACKER_RUN" \
  --ranking-profile "$FRESH_MELODY_PROFILE" \
  --out-dir "$FRESH_PROFILED_REVIEW"

sunofriend melody-guide "$PHRASE_REVIEW" \
  --unit "$ONE_BASED_UNIT" \
  --guide "$SHORT_GUIDE_WAV" \
  --guide-kind hum \
  --search-seconds 0.75 \
  --out-dir "$FRESH_GUIDED_REVIEW"

sunofriend vocal-melody "$VOCAL_STEM" \
  --role lead \
  --muscriptor \
  --game \
  --game-language en \
  --game-seed 0 \
  --out-dir "$OUTPUT"

sunofriend vocal-melody "$VOCAL_STEM" \
  --role lead \
  --guide "$HUMMED_GUIDE" \
  --prefer-guide \
  --out-dir "$OUTPUT"

sunofriend vocal-melody "$VOCAL_STEM" \
  --role lead \
  --guide-snippet "$REFERENCE_EXCERPT" "$MATCHING_HUM" "$START_SECONDS" \
  --prefer-guide \
  --out-dir "$OUTPUT"

sunofriend melody-apply "$REVIEWED_CORRECTIONS_JSON" \
  --out "$CORRECTED_MIDI"

sunofriend midi-transform "$MIDI_OR_DIRECTORY" \
  --out "$OUTPUT" \
  --from-bpm "$SOURCE_BPM" \
  --to-bpm "$TARGET_BPM" \
  --semitones "$SEMITONES"

sunofriend midi-anchor "$MIDI_OR_DIRECTORY" \
  --out "$OUTPUT" \
  --source-downbeat-seconds "$DOWNBEAT_SECONDS" \
  --from-bpm "$SOURCE_BPM" \
  --to-bpm "$TARGET_BPM" \
  --target-downbeat-beat 4 \
  --semitones "$SEMITONES"

sunofriend instrument-match "$STEM" "$ALIGNED_MIDI" \
  --kind "$ROLE" \
  --out-dir "$FRESH_OUTPUT"

sunofriend instrument-match "$STEM" "$ALIGNED_MIDI" \
  --kind "$ROLE" \
  --out-dir "$FRESH_OUTPUT" \
  --embedding-model "$OPENL3_MODEL"

sunofriend sample-pack "$STEM" "$ALIGNED_MIDI" \
  --kind "$ROLE" \
  --name "$INSTRUMENT_NAME" \
  --out-dir "$FRESH_OUTPUT"

sunofriend sample-pack "$STEM" "$ALIGNED_MIDI" \
  --kind "$ROLE" \
  --name "$INSTRUMENT_NAME" \
  --out-dir "$FRESH_OUTPUT" \
  --embedding-model "$OPENL3_MODEL"

sunofriend sample-pack-review "$SAMPLE_PACK_V2" \
  --out-dir "$FRESH_REVIEW"

sunofriend sample-pack-apply "$USER_EXPORTED_REVIEWED_JSON" \
  --name "$INSTRUMENT_NAME Reviewed" \
  --out-dir "$FRESH_SAMPLE_PACK_V3"

sunofriend sample-pack-boundary-review "$SAMPLE_PACK_V3" \
  --out-dir "$FRESH_BOUNDARY_REVIEW"

sunofriend sample-pack-boundary-apply "$USER_EXPORTED_BOUNDARY_REVIEW" \
  --out-dir "$FRESH_BOUNDARY_REVIEWED_V3"

sunofriend sample-pack-ab-review "$V3_A" "$V3_B" \
  --out-dir "$FRESH_BLIND_REVIEW"

sunofriend sample-pack-ab-resolve "$USER_EXPORTED_BLIND_REVIEW" \
  --out "$FRESH_BLIND_RESULT_JSON"

sunofriend instrument-bundle "$STEM" "$ALIGNED_MIDI" \
  --kind "$ROLE" \
  --name "$INSTRUMENT_NAME" \
  --out-dir "$FRESH_OUTPUT"

sunofriend instrument-feedback "$INSTRUMENT_BUNDLE" \
  --patch "$EXACT_DAW_PATCH" \
  --decision preferred \
  --context full-mix \
  --out "$FRESH_FEEDBACK_JSON"

sunofriend instrument-profile "$REVIEWED_FEEDBACK_JSON" \
  --out "$FRESH_INSTRUMENT_PROFILE"

sunofriend instrument-bundle "$STEM" "$ALIGNED_MIDI" \
  --kind "$ROLE" \
  --preference-profile "$FRESH_INSTRUMENT_PROFILE" \
  --out-dir "$FRESH_PROFILED_BUNDLE"
```

## Musical and data rules

- Use `exact` for confident observed evidence, `repair` for conservative
  corrections, and `reconstruct` only for explicitly requested inference.
- `midi-mask` is a cleanup experiment, not `exact` transcription or generic
  source separation. Keep excerpts at 60 seconds or less, retain the original,
  target and residual together, and require persisted reconstruction plus
  listening. Shared harmonics can enter the target; attacks can stay in the
  residual. Use `--transient-ms` only as a separate labelled challenger.
- `ai-cleanup` is also an experimental challenger, not generic stem separation
  or `exact` evidence. Require the pinned external checkpoint SHA-256 before
  PyTorch deserialisation, CPU inference with zero random shifts, a fresh
  immutable directory and persisted target-plus-residual reconstruction.
  Demucs code is MIT, but its official repository does not state separate
  pretrained-checkpoint terms; keep the model and outputs private, do not
  vendor or redistribute them, and retain failed-run request/log evidence.
- `ai-transcribe-session` and `ai-session-benchmark` are execution diagnostics
  only. They must use the already accepted local MuScriptor checkpoint and must
  not download weights, accept or change licence terms, create a content cache,
  mutate raw candidates/MIDI, promote a lane or alter Workbench choices. Keep
  their measured output separate from musical evaluation.
- The MuScriptor application cache is also execution evidence, not musical
  consensus. Cache only `candidate.raw.json` and the original fresh-process
  performance artifact; rebuild current quality, GM mapping, expression and
  MIDI in every new run. A hit proves exact prior-result reuse, not independent
  model agreement, accuracy or a warm resident model. Invalid, linked or
  inconsistent entries must fail closed without an inference fallback. Never
  promote, rank or repair a candidate from cache status or speed.
- `midi-role-split` is an arrangement challenger, not source separation or
  instrument identification. Its strict partition must preserve the complete
  primary note multiset and must retain cluster outliers. Its independent
  secondary track may add simultaneous notes, but it remains a separate
  alternative because residual bleed and octave errors are possible. Never
  infer the body cluster from duration, pitch or silhouette alone, and never
  edit the unreviewed export seed on the user's behalf.
- `midi-role-split-resolve` must verify the review seed, report, source inputs
  and all reported artifacts. The overall decision is authoritative. Copy the
  selected MIDI exactly; do not merge retained components, re-transcribe, edit
  the source tree or delete alternatives.
- `timbre-resynthesis` is a fixed-performance sound experiment. It must reject
  polyphonic or variable-tempo MIDI in v1, preserve source hashes and publish
  zero note/pitch/onset/duration/velocity changes. Do not call the fitted WAV
  AI, a physical-instrument match or a GarageBand instrument. All-notes-audible
  is not proof of realism or musical usefulness; only the explicit listening
  export can choose among complete patch, source sampler and resynthesis.
- Do not describe a major-to-minor or minor-to-major change as simple
  transposition. Same-mode key changes are mechanical semitone shifts, but
  register and instrument range still require auditioning.
- Do not treat the first metronome click as a downbeat without musical
  confirmation.
- State that BPM- or pitch-transformed MIDI no longer matches untreated audio.
- Use `--concert-pitch` only for a recognised Sunofriend tuning setup. It is
  not a general third-party pitch-bend remover.
- Prefer `midi-anchor` for mashups. Before `midi-align`, state that it discards
  controllers, sustain, later program changes, pitch bend, aftertouch, SysEx,
  release velocity, markers, lyrics, and chord or key metadata.
- Preserve separate output directories for source modes and transformed copies.
- Treat instrument-match scores as relative shortlist evidence, never
  confidence percentages or proof of the original patch. GarageBand patch
  names can differ from installed sample-asset names.
- Instrument preference feedback must come from an explicit user listening
  decision against a hash-pinned Bundle. Profiles stay local, discover no files
  automatically and preserve preferred, acceptable and rejected choices plus
  full-mix/solo context. A history score is not confidence, instrument identity
  or permission to bypass playability.
- Do not copy, edit or redistribute Apple factory samples. Do not claim that
  Sunofriend can headlessly render every private GarageBand patch.
- For sample packs, use only source audio the user owns or may sample. State
  that bleed, effects, vibrato and transitions become part of each sample and
  that Sample Instrument v2 does not automatically enable loops, velocity
  layers or round-robin playback. Its loop and dynamics reports are advisory
  and do not add zones. Keep
  auto-tuning enabled unless the user asks to preserve the source's raw tuning;
  do not present `no-stable-pitch` or rejected tuning estimates as failures.
- Never apply a Sample Instrument v3 review from an unreviewed seed or infer
  acceptance from scores. Do not accept conflicting units at one MIDI pitch.
  Do not call separate SF2 alternate banks automatic round robin.
- Never inspect or reveal a Sample Instrument blind-review answer key before
  the user exports a complete review. Candidate equivalence, neither and v2
  preference are valid results; a resolved preference changes no sampler.
- Tracker consensus does not mean certainty. Inspect disputed/solo frame
  counts and keep `uncertain` separate. In a `vocal-trackers` run also inspect
  agreement, no-agreement, selected-source counts and all independent
  evaluations; a majority may follow a harmonic or another real backing
  voice. A boundary repair may borrow Basic Pitch or GAME timing only when
  pYIN and RMVPE agree on pitch; it must retain every rejected proposal and
  must not replace backing harmony. Repeated-phrase repair may promote only
  notes already present in the lenient source contour; a hummed guide may set
  intention and rhythm but must not bypass source-pitch support.
- For guide snippets, report every requested and chosen start time, per-snippet
  transpose, detected/accepted note count and warning. A failed snippet must
  not remove the automatic full-song melody.
- A correction JSON is a user-authored replacement note list. Apply it to a
  fresh MIDI path and retain the adjacent `.correction.json` audit.
- A phrase-review seed is deliberately unreviewed. Never edit its status on
  the user's behalf. Hand off `melody_phrase_review.html`; after the user
  exports a reviewed document, ensure every choice is explicit and retain the
  selected alternatives in the correction audit.
- A personal ranking profile is learned only from the user's explicitly
  reviewed files and stays local. Its scores are relative history rankings,
  not calibrated probabilities. Preserve its input/profile hashes and never
  let it change candidate order, default selection or review state.

### Controlled Phase 5 matrix example

Use quoted lane values because song paths commonly contain spaces:

```bash
sunofriend ai-matrix \
  --lane "M0=$M0_RUN" \
  --lane "M1=$M1_RUN" \
  --lane "M2=$M2_RUN" \
  --lane "M3-bass=$M3_BASS_RUN" \
  --out "$FRESH_MATRIX_JSON"

sunofriend ai-benchmark \
  --run "$SMALL_CPU_REPEAT_1" \
  --run "$SMALL_CPU_REPEAT_2" \
  --out "$FRESH_PERFORMANCE_JSON"

sunofriend ai-setting-compare \
  --control-run "$BEAM1_REPEAT_1" \
  --control-run "$BEAM1_REPEAT_2" \
  --challenger-run "$BEAM2_REPEAT_1" \
  --challenger-run "$BEAM2_REPEAT_2" \
  --out "$FRESH_BEAM_COMPARISON_JSON"

sunofriend ai-transcribe-session "$FIXED_SOURCE_WAV" \
  --checkpoint "$LOCAL_MUSCRIPTOR_CHECKPOINT" \
  --out-dir "$FRESH_SESSION_DIR" \
  --bpm "$BPM" \
  --instrument "$EXACT_ROLE_1" \
  --instrument "$EXACT_ROLE_2" \
  --start-seconds "$START" \
  --end-seconds "$END" \
  --device cpu \
  --beam-size 1 \
  --batch-size 1 \
  --cfg-coef 1.0 \
  --model-size small \
  --repetitions 3

sunofriend ai-session-benchmark "$FRESH_SESSION_DIR" \
  --fresh-run "$EXACT_FRESH_RUN_1" \
  --fresh-run "$EXACT_FRESH_RUN_2" \
  --out "$FRESH_SESSION_BENCHMARK_JSON"

sunofriend ai-transcribe "$FIXED_SOURCE_WAV" \
  --checkpoint "$LOCAL_MUSCRIPTOR_CHECKPOINT" \
  --out-dir "$FRESH_CACHE_MISS_PARENT" \
  --application-cache-dir "$PRIVATE_AI_CACHE" \
  --bpm "$BPM" \
  --instrument "$EXACT_ROLE_1" \
  --instrument "$EXACT_ROLE_2" \
  --start-seconds "$START" --end-seconds "$END" \
  --device cpu --beam-size 1 --batch-size 1 --cfg-coef 1.0 \
  --model-size small

sunofriend ai-transcribe "$FIXED_SOURCE_WAV" \
  --checkpoint "$LOCAL_MUSCRIPTOR_CHECKPOINT" \
  --out-dir "$FRESH_CACHE_HIT_1_PARENT" \
  --application-cache-dir "$PRIVATE_AI_CACHE" \
  --bpm "$BPM" \
  --instrument "$EXACT_ROLE_1" \
  --instrument "$EXACT_ROLE_2" \
  --start-seconds "$START" --end-seconds "$END" \
  --device cpu --beam-size 1 --batch-size 1 --cfg-coef 1.0 \
  --model-size small

sunofriend ai-transcribe "$FIXED_SOURCE_WAV" \
  --checkpoint "$LOCAL_MUSCRIPTOR_CHECKPOINT" \
  --out-dir "$FRESH_CACHE_HIT_2_PARENT" \
  --application-cache-dir "$PRIVATE_AI_CACHE" \
  --bpm "$BPM" \
  --instrument "$EXACT_ROLE_1" \
  --instrument "$EXACT_ROLE_2" \
  --start-seconds "$START" --end-seconds "$END" \
  --device cpu --beam-size 1 --batch-size 1 --cfg-coef 1.0 \
  --model-size small

sunofriend ai-cache-benchmark \
  --miss-run "$COMPLETED_CACHE_MISS_RUN" \
  --hit-run "$COMPLETED_CACHE_HIT_1_RUN" \
  --hit-run "$COMPLETED_CACHE_HIT_2_RUN" \
  --out "$FRESH_CACHE_BENCHMARK_JSON"

sunofriend ai-label-split "$COMPLETED_M4_RUN" \
  --label clean_electric_guitar \
  --out-dir "$FRESH_LABEL_SPLIT"
```

## Validate and hand off

1. Check the exit status and generated JSON summary. Treat partial or no-output
   status as incomplete.
2. Confirm every reported MIDI and JSON sidecar exists.
3. Inspect evaluation and provenance. Report note counts, onset precision,
   recall or F1, timing p95 and drift, pitch or octave evidence, and observed,
   repaired, inferred, possible, or uncertain counts where available. Do not
   invent universal pass thresholds.
   For `ai-matrix`, additionally confirm one backend/checkpoint/config/worker/
   runtime/execution profile across all lanes; report M0/M1 label stability,
   every lane's requested and
   detected labels, note count, severe/no-evidence block reasons,
   per-instrument quality, five-second boundaries, real-time factor and
   cross-lane overlap. For M4 also confirm same source/excerpt/BPM, one
   distinct requested role per lane, requested/off-role counts and every peer
   overlap ratio. Confirm all source, worker, raw artifact, candidate,
   MIDI, checkpoint and config hashes verified and both mutation totals are
   zero. Retain failed lanes and never turn overlap or quality into a winner.
   For `ai-benchmark`, confirm the cache regime says fresh process, no reused
   model, no application cache, uncontrolled OS cache and no cold-start claim.
   Report exact-output repeatability and keep pipeline, subprocess and
   inclusive-transcription timings distinct. Verify the same runtime profile,
   source-frame-derived actual processed duration and non-overlapping execution
   windows across repetitions. Process RSS excludes
   accelerator allocation. Do not infer a warm-model speedup or a musical
   promotion from the timing report.
   For `ai-setting-compare`, confirm both arms contain at least two current
   explicit fresh-inference runs, all combined execution windows are sequential
   and non-overlapping, and the only semantic change is beam size 1→2 (strategy
   is derived). Require exact within-arm raw/normalized candidate, note-payload,
   MIDI, derived-artifact and note-count repeatability. Keep candidate-provenance
   equality separate from musical-output equality. Report label, automated
   quality, boundary, timing and memory differences without calling either arm
   more accurate or faster because of them. Confirm selection/promotion/raw/MIDI
   effects are zero, state that the OS cache and order are uncontrolled, and
   require an explicit source-aligned, same-renderer, same-patch, separately
   verified level-matched listening decision before changing a preset or
   default when note payload or MIDI differs.
   For `midi-ab-review`, report the source/MIDI/SoundFont/FluidSynth hashes,
   zero-based program, sample rate, gain, required MIDI-time-at-source-start,
   its exact source-frame offset, exact seconds/frame bounds and that every
   interval is non-overlapping and 0.5–15 seconds. Confirm the common alignment
   was explicit rather than inferred; source/A/B frame geometry matches; both
   candidate windows meet the -60 dBFS RMS floor; only the louder candidate was
   attenuated to the quieter fixed-window sample RMS; and the source stayed
   unlevelled. Confirm a secret random per-unit nonce is present only in the
   answer key, its commitment is public, the key is absent from HTML, audio is
   auto-looped with one shared playhead per unit, and all heard flags plus
   choices begin incomplete. State explicitly that this is not LUFS, true-peak
   or perceived-loudness matching and that MIDI edits, selection, promotion and
   default changes are zero. Hand off the HTML without opening the answer key
   or manufacturing a reviewed export. For `midi-ab-resolve`, require a
   user-exported complete review and the separately named original unchanged
   `--package-dir`; reverify the seed, audio manifest, answer key and original
   inputs. Confirm only status/reviewed count, heard, choice and notes changed,
   while A/B slots, unit membership, timing, focus and geometry stayed fixed.
   Report per-loop resolved identities and preference counts and retain all zero
   effects. Do not turn the listening result into an automatic preset change.
   For `ai-transcribe-session`, confirm the private root was fresh and contains
   `session.request-template.json`, started/ready/closed lifecycle records,
   worker logs, `session.json` and exactly the declared contiguous
   `repetition-NNN` run directories. Verify one worker instance/model load, one
   exact source/ordered-role/excerpt/request template, serial non-overlapping
   requests, zero application-cache hits and uncontrolled OS-cache status.
   Confirm request 1 is explicitly not warm and requests 2+ are explicitly
   reused-model warm. Confirm final source, checkpoint, model-config, worker and
   template hashes and all zero promotion/selection/raw/MIDI mutation effects.
   Do not publish the tree: it contains absolute paths and logs.
   For `ai-session-benchmark`, confirm the report is path-free, request count
   is 2–20, warm count is request count minus one, startup/model-load evidence
   is separate, every request performance window nests correctly, RSS is
   cumulative process high-water evidence and exact candidate JSON/MIDI/note
   repeatability passed. When fresh controls are present, require status
   `verified`, at least two exact comparable fresh-process repetitions and
   unchanged candidate/MIDI hashes before reporting warm-to-fresh ratios. State
   that content hashes and runtime identity may still identify material or a
   machine. Do not claim anonymity, a cold start, a production cache/service,
   a causal speed-up from the observed warm/fresh ratio, or musical promotion.
   For the application cache, confirm the ordered status sequence is one
   `miss-stored` followed by at least two `verified-hit` runs and that every
   run uses one cache key and entry-manifest hash. On hits require an empty
   command, null exit status and explicit false worker-process, model-load,
   inference and resident-model-reuse fields. Confirm
   `cache.performance.json` contains current lookup/materialisation/
   post-processing/pipeline timing while copied `muscriptor.performance.json`
   is labelled original fresh-inference evidence only. Require exact raw
   candidate, normalised candidate, base/expression MIDI, expression JSON,
   quality, program mapping and note-count repeatability and zero
   promotion/raw/MIDI mutation claims. Treat the report as path-free but not
   anonymous or publication consent. Use the original fresh miss, never a hit,
   for `ai-matrix`; never feed any cache-enabled run to fresh-only
   `ai-benchmark`. Keep this separate from resident-model reuse, Workbench
   preview caching and the uncontrolled OS file cache.
   For `ai-label-split`, additionally confirm the source run and artifact
   hashes, exact requested label, detected-label counts, selected/complement
   source indices, disjoint/exhaustive raw-event partition and all-zero source
   event deletion/duplication. Confirm the full-candidate control is
   byte-identical; verify the private request/candidate controls and confirm
   every partition row equals the pinned candidate note at that source index.
   Then report each audition MIDI's rendered note count,
   pitch/tick quantisation, duplicate collapse and same-pitch truncation; do not
   claim that MIDI encoding is lossless. Hand off the unchanged full candidate,
   requested-label MIDI and complement together.
   Report zero-note selected output as blocked no-evidence; do not infer
   separation or promote a non-empty derivative without listening.
   For `midi-mask`, additionally report source/MIDI hashes, selected track and
   role, excerpt bounds, intersecting notes/pitches, mask parameters, source/
   target/residual RMS, persisted PCM24 reconstruction error and threshold,
   repeat artifact hashes and all zero input-mutation effects. Re-transcribe
   source, target and residual separately. A target that improves pitch support
   but loses attacks is not a cleanup success.
   For `ai-cleanup`, additionally report source/checkpoint hashes, backend
   version/signature, excerpt bounds, fixed inference settings, source/target/
   residual RMS, clipping counts, persisted PCM24 reconstruction, repeat
   artifact hashes, zero input-mutation effects and the private-checkpoint
   notice. Compare unchanged, learned-target and residual MIDI against the same
   source using the same transcriber. Improvements in supported notes or octave
   accuracy do not override worse contour/onsets or the listening gate.
   For `midi-role-split`, additionally report the reviewed-cleanup hash when
   supplied, source-cluster/OpenL3 summary, explicit body cluster, body,
   complement, outlier and secondary note counts, secondary maximum polyphony,
   unchanged-primary hash, exact strict-partition zero-change effects and every
   MIDI/WAV review artifact. State that the secondary is independently
   transcribed and can overlap, while both cluster roles and GM programs remain
   hypotheses. Hand off `midi_role_split_review.html`; do not select an overall
   decision or mark any sound reviewed.
   For `midi-role-split-resolve`, report every reviewed role/usefulness choice,
   overall decision, review and selected-MIDI hashes, source artifact selected,
   and all zero-mutation effects. State explicitly when useful split components
   were retained but did not replace the primary.
   For `timbre-resynthesis`, report source and fixed-MIDI hashes, BPM, note and
   pitch counts, harmonic/noise/envelope parameters, candidate level matching,
   every per-candidate audible/silent note count, SoundFont hashes, repeat
   determinism and all zero MIDI effects. Hand off
   `timbre_resynthesis_review.html`; do not fill its fields or infer a winner
   from functional audibility.
4. For vocals, inspect contour coverage, pitch-error statistics, monophony, and
   the published variants. Also report tracker sources, consensus frame count,
   repeated-phrase promotions, guide alignment/transpose and the correction
   HTML/JSON paths when present.
   When `--muscriptor` is used, also report the checkpoint hash, immutable run
   manifest, raw candidate, `candidate.quality.json`,
   `candidate.programs.json`, source-expression JSON and MIDI, velocity range,
   model-backed GarageBand MIDI and the fact that it remains a separately
   auditionable challenger. Confirm role-aware GM programs changed zero notes
   and are audition hints rather than GarageBand patch identifications. Do not
   render, play or recommend an AI candidate marked `review-required` until
   its density, duplicate, polyphony or label warnings have been understood.
   For GAME, additionally report its six-component bundle hash, language,
   boundary/presence thresholds, D3PM schedule, seed, voiced/total region
   counts and CPU provider. Compare its timing and contour evidence with the
   existing candidate; do not call it better solely from one aggregate metric.
   For RMVPE, report adapter and checkpoint versions/hashes, frame count, raw
   voiced-frame count, decoder policy/parameters, note count, quality status,
   `rmvpe.frames.json`, raw and expression MIDI, repeat determinism and CPU
   provider. Compare contour and boundary metrics separately: RMVPE supplies
   frame F0, not note boundaries.
   For PESTO, report package/checkpoint versions and hashes, step size,
   reduction, frame and note counts, activation artifact/shape, repeat
   determinism and device. Do not call its decoded note boundaries model
   evidence.
   For `vocal-trackers`, additionally report
   pYIN/Basic Pitch/consensus note counts and metrics, input evidence hashes,
   agreement/disputed/solo/no-agreement counts, boundary proposal acceptance
   and rejection reasons, provider-specific/combined note and phrase counts,
   ranked phrase paths, repeat determinism and that consensus/repair remain
   experimental. Never discard the raw candidates.
   For `melody-review`, confirm lead role, matching input hashes, source-cluster
   and review-unit counts, duration bars/status, grouping configuration,
   alternative counts, source/MIDI/overlay/evaluation paths, any zero-note
   alternatives, evaluated/accepted repeat-pair counts, rejection reasons,
   repeat groups, byte-repeat result and `raw_candidates_mutated: false`.
   Hand off the HTML, not the unreviewed seed. After user review, report each
   selected alternative, any explicitly propagated choices with their canonical
   pair evidence, and evaluate the newly applied MIDI against the source.
   When `--ranking-profile` is used, additionally report the profile hash,
   explicit/contextual choice counts, warnings and history-first candidate per
   unit. Confirm `automatic_selection`, `candidate_order_changed` and
   `default_selection_changed` are all false, the seed is still unreviewed and
   a second fresh build is byte-identical. For `melody-profile`, also confirm
   unique input hashes, manual/propagated weights, choice totals and that no raw
   candidate was mutated.
   For `melody-guide`, also confirm parent-review artifact count/hash, pYIN and
   guide hashes, one-based unit, guide kind/duration, detected and accepted note
   counts, alignment offset/score, source-pitch support, warnings, zero-note
   status, byte-repeat result and that parent/raw candidates remain unchanged.
5. For transformations, inspect the JSON audit for file count, embedded target
   tempo, transposed events, preserved drums, tuning cleanup, and anchor shift.
6. Render representative MIDI with `preview` when auditory validation is in
   scope and `render_ready` is true. Use `preview --soundfont PATH` to compare
   the same performance through an authorised source-derived SF2; do not call
   that render a factory-patch or transcription improvement.
7. Hand off the exact GarageBand BPM, recommended MIDI, audition alternatives,
   instrument suggestions, warnings, and reproducible commands.
8. For `instrument-match`, confirm the JSON, GarageBand audition guide, timbre
   graph when present, and retained top GM MIDI/WAV pairs. Report both evidence
   rankings and ask the user to choose in the full mix. When OpenL3 was
   explicitly enabled, also confirm `openl3_embedding_evidence.json`, its
   checkpoint/SoundFont hashes, and `gm_embedding_auditions/`; state that the
   learned ranking did not alter the explainable ranking.
   Also confirm `source_event_clusters.json` and its SVG, event/family/
   articulation/outlier counts, medoids, method weights and zero-change
   effects. Never call a cluster a confirmed instrument or an outlier noise
   without listening.
   Confirm `source_event_dynamics.json` and its SVG, exact comparison-unit
   rules, candidate layer/set/event and retained-outlier counts, and all-zero
   effects. Never call a layer or alternate valid from source level alone.
   For drum roles, also confirm `gm_drum_family_mapping.json`, the separate
   proposed MIDI/WAV, original before/after hash equality, mapping-unit and
   changed-note counts, guardrail decisions, retained outliers and assigned
   one-shot auditions. Compare source MIDI and proposal by ear; do not accept
   a mixed-kit reassignment from its score alone.
9. For `sample-pack`, confirm the optional macOS `.aupreset` wrapper, SF2, SFZ,
   audition MIDI, optional audition WAV, usability JSON/MIDI/WAV, source WAVs
   and JSON exist. Report MIDI
   roots and key ranges, isolation, tuning status counts, maximum transposition
   and sustain limitations. Report mapped/unmapped performance notes, attack
   and musical-duration support, functional status and recommended use. Never
   recommend a `texture-only` bank as the sole instrument. Hand off the report's
   GarageBand steps: keep the
   preset and bank at their generated paths, put the audition MIDI on a
   software-instrument track, select Apple AUSampler, load the `.aupreset` from
   its **Manual** preset menu, play the every-performance-pitch usability
   audition, then the whole song. Save a custom patch only if both checks pass.
   Also report source-event family/articulation/outlier counts and whether any
   selected sample is a review outlier; v1 must report zero automatic removals.
   Report dynamics candidate counts separately and confirm they did not add a
   zone, change a velocity range or enable round-robin playback.
   Report loop candidate/sample counts separately, confirm all loop effects are
   zero and hand off every raw repeated audition. For pitched samples, ask the
   user to choose a candidate or none by listening; for drum/percussion roles,
   confirm the report is not applicable. Never edit the SoundFont/SFZ or claim
   an accepted sustain loop from the numeric order alone.
   For `sample-pack-review`, confirm the seed is `unreviewed`, all source and
   review-audio hashes are pinned, the HTML and every reported excerpt exist,
   candidate unit/layer/set/event counts match and all effects are zero. Also
   report the initial audition BPM, role mode, isolated/context file counts and
   confirm the source-context, repeated-beat or pitched-phrase WAVs have no
   selection effect. Hand off the HTML and do not manufacture a reviewed file.
   For `sample-pack-apply`, require the user's reviewed export; report accepted
   and rejected units, exact event indices, reviewed pitch/boundary, extracted
   event and zone counts, review/output hashes, baseline hash equality, A/B
   MIDI/WAVs and alternate banks. Confirm MIDI changes are zero, v2 is embedded
   under `baseline-v2/`, and the applied-feature counts match the review. When
   alternates were accepted, confirm SF2 alternates are manual A/B and only SFZ
   claims true sequence round robin; otherwise confirm neither is reported.
   Also confirm the performance source/v2/v3 WAVs share one excerpt MIDI,
   pitches and velocities are unchanged, the source and output channel are
   explicit, the source MIDI hash is unchanged and a fresh build repeats.
   For a velocity sweep, confirm its MIDI/v2/v3 files, accepted boundary,
   adjacent transition velocities, audit-only status, zero mapping/sample
   changes and repeat hashes.
   For `sample-pack-boundary-review`, confirm no candidate is preselected,
   single-lower/single-upper/layered choices exist, the two source events share
   one fixed-velocity repeated beat, all complete mappings share one velocity
   ramp, actual source-MIDI velocities and unreachable layers are reported,
   every source/candidate hash is pinned, and the source v3 tree is unchanged.
   Hand off the HTML; do not manufacture the reviewed export. For
   `sample-pack-boundary-apply`, validate the user export, report every
   before/after mapping and changed/kept decision, active events removed, new
   events introduced, sample-audio modifications and source-MIDI changes, and
   verify that a fresh output regenerates all A/B, performance and sweep
   artifacts consistently.
   For `sample-pack-ab-review`, confirm every source v3 and performance hash,
   copied audio-manifest hash, answer-key hash, neutral null choices, absent
   answer mapping in the HTML, same hidden assignment for performance/sweep,
   zero effects and byte-repeat output. Hand off the HTML without reading the
   key. For `sample-pack-ab-resolve`, require the reviewed export and report
   v2, v3, equivalent and neither counts plus notes, while confirming all
   sampler/MIDI effects remain zero.
10. For `instrument-bundle`, confirm `performance.mid`, recipe/report, source
    reference when requested, match directory, source instrument when safe,
    and retained previews. Explicitly distinguish an embedded authorised SF2
    from a non-embedded Apple factory recommendation.
    When `--preference-profile` is supplied, also confirm the copied profile and
    hash, role observation count, history-first patch and all false selection,
    ranking/default and playability-bypass effects. Verify factory/GM/OpenL3
    orders and the portable program hint were not changed by history.
11. For `instrument-feedback`, report the exact patch/source/decision/context,
    bundle report/recipe/performance hashes and all zero effects. For
    `instrument-profile`, confirm unique reviewed input hashes, per-role
    decision counts/weights, deterministic repeat output and that automatic
    selection, match reordering, default change and playability bypass are all
    false.
12. For `workbench`, report the inferred BPM/key/tuning, stem and candidate
    counts, primary-versus-diagnostic split, SQLite path and loopback URL.
    When an explicit catalog supplies `review_question` or `listening_focus`,
    report the displayed prompt, confirm its hash is pinned to the review row
    and saved events, and confirm that it caused no selection or ranking
    effect. A changed prompt must create a fresh row rather than restore an old
    choice; prompt text must stay out of the contribution preview.
    Confirm the server binds to `127.0.0.1`, uses a per-launch token, serves
    only catalogued or content-addressed local files, restores choices after
    restart and has no upload/submission endpoint. When rendering, report the
    role-neutral policy, SoundFont identity/hash, cache hit/miss and that the
    original MIDI was not mutated. For an arrangement/handoff, report exact
    selected main/optional counts, proxy track count, BPM policy and ZIP path;
    report every selected same-candidate-origin overlap pair, including whether
    its source SHA-256 came from verified AI provenance or the non-AI
    review-stem fallback, plus the 80 ms exact-pitch greedy-match policy,
    matched count and both coverage ratios. Treat the
    eight-match/80%-each warning only as a doubled-line listening diagnostic,
    not accuracy, separation or preference. Confirm it changed no selection or
    MIDI and that arrangement listening remained available. Before handing off
    a substantial pair, confirm the latest saved decision for both candidates
    has `full_mix` context; do not deduplicate or merge them automatically.
    When using `--export-review`, confirm the destination was fresh, the write
    completed without starting a server and the artifact is private because it
    can contain absolute paths and notes.
    For every handoff,
    confirm rejected/needs-correction/unreviewed files, source audio, private
    notes and absolute paths are excluded, and numbered selected MIDI bytes are
    unchanged. Exported local JSON may contain absolute paths and private
    notes; the separate contribution preview must contain neither.
