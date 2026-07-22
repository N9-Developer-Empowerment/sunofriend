---
name: sunofriend
description: Use the local Sunofriend CLI to convert isolated Suno/Moises WAV stems and lead or backing vocals into evaluated GarageBand-ready MIDI; compare immutable AI transcription lanes, compare evidence-pinned specialist/full-mix/conditioned lead MIDI by phrase with explicit lineage limits and without creating a hybrid, benchmark verified fresh-process or bounded exact-repeat local AI runs, reuse and benchmark an explicit exact MuScriptor raw-result cache, partition model-reported labels exactly, and review existing source/MIDI alternatives; build blind exact-source-window, fixed-window sample-RMS-matched MIDI A/B reviews with explicit heard and choice evidence; render cached neutral previews, save explicit solo/full-mix choices, hear bounded or exact chunked canonical selected arrangements, export unchanged choices in a GarageBand handoff, and complete its guided tutorial, 10-question quiz and two human acceptance checks through the loopback-only Workbench; combine tracker consensus, phrase-by-phrase alternatives, repeated phrases, hummed guidance and local advisory review-history profiles; create short experimental MIDI-guided or pinned learned target/residual cleanup pairs, split reviewed mixed-role MIDI into separate body/pluck challengers, and compare complete, sampled and harmonic-plus-noise sounds on one fixed monophonic MIDI; inventory, sound-match, audition, build self-contained SF2 sample instruments, or package MIDI plus sound in Instrument Bundle v1; preview or play results; change MIDI key, BPM, tuning, and downbeat alignment; browse a gated read-only Clip v1 library; explicitly propose immutable Clip placements; or store and transform Clip v1 parts. Use for Sunofriend, stems-to-MIDI, vocal melody MIDI, GarageBand timing, MIDI mashups, instrument selection, stem sample instruments, tempo or transposition changes, explicit Clip reuse proposals, and stem-versus-MIDI accuracy. Do not use for generic stem separation, mastering, lyric writing, downloading third-party plug-ins, or editing a DAW GUI.
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
     worker. It reads at least two completed fresh controls and challengers for
     either the beam-size 1→2 or batch-size 1→2 contract. Run
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
   - `sunofriend hybrid-report` starts no model and needs
     `sunofriend doctor --require convert` for its local `StemSpectrum`
     evidence. Read `hybrid-report --help`; supply the exact source excerpt,
     matching lead phrase review, BPM and separately named S0/M1/M3 MIDI plus
     evidence. Version 1 accepts only `--role lead`. The output is diagnostic
     only and creates no MIDI. Its verifier cannot prove that M1's full mix was
     derived from the comparison song, nor verify M3's unsupplied original
     pre-projection MIDI; require both unverified statuses in the result.
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
     render actions. `--developer-inspector` is an optional read-only
     application operation/state explorer in the same token-protected loopback
     Workbench. It needs no extra dependency and must not be described as a
     Python line debugger, evaluator, shell, SQL console or filesystem browser.
   - `sunofriend garageband-pack-review` and
     `sunofriend garageband-pack-resolve` need no audio, ML, preview or playback
     capability. They verify one existing exact downloaded ZIP locally. The
     generated tutorial/quiz page and reviewed JSON are private; resolution
     starts no server, model or project action.
   - The completed Phase 6 Increment 6.0 read-only Clip entry uses
     `sunofriend workbench PROJECT --clip-library LIBRARY
     --phase6-acceptance RESULT --phase6-pack PACK`. All three flags are
     required together. Browse, detail, lineage and deterministic MIDI
     reconstruction need no audio/ML capability; require
     `sunofriend doctor --require preview` only before requesting the optional
     dry neutral audition. The supplied result must be `passed` and the pack
     must exactly match it. Do not discover any of the three inputs.
   - The completed Phase 6 Increment 6.1 proposal additionally requires
     `--enable-clip-reuse-plan`; reject it unless all three Increment 6.0 flags
     are present. It needs no audio, ML or preview capability. It adds only
     explicit whole-beat place/remove actions in a separate local proposal and
     has passed its focused/full and local restart/browser verification. Do
     not describe it as arrangement playback, a transform, an export or a
     completed wider Phase 6 feature.
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
  transcriber. Preserve Sunofriend's multi-process identity: specialist,
  analytical, tracker-consensus, conditioned-AI and reviewed repair candidates
  are separate evidence, and a different process may be useful for each role
  or phrase. Never collapse them into one automatic winner or imply that a
  model label, score, preview count or visible default is preference. Prefer an
  explicit `sunofriend.workbench-catalog.v1` document
  when filenames cannot distinguish songs or audible roles. Treat at most
  three primary candidates as the normal result space, keep diagnostic files
  advanced, and do not infer preference from audition events, dwell time or
  unclicked defaults. Prefer the content-addressed role-neutral preview when an
  existing WAV is absent or uses a different sound. For precise per-stem
  listening, prepare a 0.5–15 second decoded loop: primary candidates are
  included by default, an advanced candidate requires explicit **Include in
  precise loop**, and no more than six candidates may be requested. Source and
  neutral MIDI clips share one decoded Web Audio clock with scheduled switches
  and one absolute playhead. They all begin at recorded zero; do not infer an
  alignment offset. Preparing, playing, switching, seeking, pausing or stopping
  must not append an event, change a selection, rank a process or mutate MIDI.
  For a precise selected arrangement, prepare a separate 0.5–15 second decoded
  loop from the server-derived `sunofriend.workbench-arrangement-selection.v1`
  manifest. Byte-identical sources are one lane, current main/optional MIDI
  remains distinct, and only its source-only, selected-MIDI, hybrid and
  main-only groups may play. Never accept browser-supplied track IDs, roles,
  gains or arbitrary groups. Recheck the manifest after rendering before
  registering media, use one shared start/stop time for the whole group and
  leave the old group playing if a replacement cannot be scheduled. Allow at
  most 24 total tracks. Treat unity-gain playback as unlevelled and potentially
  clipping, not blind preference evidence. Invalidate an older pending preset
  resume when the user clicks a newer preset, Pause, Stop, changes the loop or
  leaves the view; abort and stale-guard preparation rather than publishing a
  partial browser transport.
  Keep the three arrangement playback contracts explicit: (1) the Phase 5.6
  precise 0.5–15 second canonical loop, (2) the Phase 5.7 precise canonical
  full-song preset, and (3) the coarse HTML-media full-song/custom mixer with
  arbitrary visibility, mute, solo and 0–100 attenuation. The full-song precise
  path accepts only the current selection-manifest hash plus `source-only`,
  `selected-midi`, `hybrid` or `main-only`; its chunk request accepts only an
  immutable stream hash and chunk index. Never accept browser-supplied track
  IDs, roles, groups or gains. The first source is the anchor rate, the longest
  source is the end, every track begins at recorded zero and input-rate scaling
  uses deterministic nearest integer frames with ties-to-even. Keep tracks as
  separate PCM16, disclose shorter-track silence padding and retain unity gain
  without matching or limiting.
  Prime up to the first two chunks and retain only current plus next decoded chunks
  on one Web Audio clock. Schedule a ready successor at the exact non-looping
  boundary and release old chunks. If the successor is not ready, stop
  truthfully at the verified boundary. A late completion enables explicit
  Play; missing or failed data requires Retry. Neither action auto-restarts,
  and seek pauses while preparing its chunk. Never silently start the coarse
  path. Changing preset creates a new immutable stream and resets its temporary
  playhead. Enforce 24 tracks, a 20-minute longest source, 2 GiB aggregate
  input across every catalog source needed for the song clock plus relevant
  selected MIDI, SoundFont and neutral previews, mono/stereo 8–96 kHz audio,
  chunks of at most five seconds, at most 480
  chunks, 32 MiB aggregate PCM16 per chunk and 192 MiB projected two-chunk
  decoded memory. Full-song chunks share the rebuildable 32-entry/256 MiB
  cache; per launch allow at most 16 active stream plans and 768 generated-media
  capabilities, and cap every POST body at 64 KiB. Treat an evicted 404 as
  recoverable by preparing again, never
  as lost durable work or permission for silent fallback.
  Keep immutable full-song input snapshots in their separate owner-only
  eight-stream/2 GiB disk LRU, retaining the current stream even if oversized.
  Fully hash-verify prepare/reprepare. A bounded eight-stream process cache may
  use regular-file identity/stat signatures for unchanged sequential chunks;
  any drift must invalidate it, return to full verification and fail closed on
  missing or altered evidence.
  The explicitly labelled compatibility fallback is synchronized in seconds,
  not sample-accurate, but its controls must also remain feedback- and
  event-free. Require every included preview to use the current SoundFont hash
  and neutral-renderer policy; a mismatch must fail closed. Renderer MIDI/
  SoundFont and decoder source/preview inputs must be read from owner-only,
  hash-and-size-verified snapshots created through one open handle and deleted
  before publication. Neutral preview rendering itself is limited to 20-minute
  MIDI. If the API reports `silence_padded_frames`, retain a visible warning,
  tell the user which track received generated end silence and never interpret
  it as a missing MIDI note. Treat decoded stem and arrangement loops as one
  rebuildable cache budget: at most 32 recent entries or 256 MiB are retained, and an evicted loop may be
  prepared again. Reject a request above 2 GiB across source audio, candidate
  MIDI, SoundFont and preview input before expensive rendering when declared
  sizes already exceed the cap, or above 64 MiB generated output. Completed
  AI runs expose path-free model/config, label, density, boundary and runtime
  diagnostics. For an application-cache hit, require the card to state that no
  AI model ran and interpret elapsed time/RTF as pipeline-not-inference. Do not
  confuse that raw-result cache with the role-neutral FluidSynth preview cache:
  Workbench populates only the latter and merely displays completed AI-cache
  provenance. For a bounded reused-model session, require Workbench to verify
  the complete closed parent session before display: request one is resident
  but not warm, while only request two and later are reused-model warm. Every
  execution state must say that it is provenance rather than musical agreement
  and that Workbench enabled no optimisation. Missing or changed parent/run,
  worker-response or performance evidence must fail closed. Treat severe
  decoder or zero-note candidates as
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
    contain absolute paths and private notes. The current Workbench has per-stem
    source/candidate switching, selected-arrangement listening and a
    source-audio-free exact-MIDI handoff. It opens through a default path-free
    Project Overview. Report its stem, decision-recorded, selected-part and
    arrangement-needed counts plus its one next step/action. That step must be
    derived only from explicit saved state; any offered action remains
    navigation. Never infer preference from the suggested destination.
    Interpret "decision recorded"
    as a current catalog candidate decision or an explicit stem outcome, never
    as accuracy or review completion. A saved pack may be called resumable only
    when its basket matches the current plan. Saved decisions and the
    separate pack basket, Project Overview state and URL-hash view/stem may
    survive a restart; prepared Web Audio, decoded chunks, playhead, loop,
    viewport/zoom/visibility, show, mute, solo and level must reset and remain
    zero-effect audition state.
    Retry/reconnect actions must not append feedback or change MIDI, audio or
    export state. Its read-only visual Result Explorer
  has two linked views: a hash-pinned per-stem source waveform with up to three
  primary MIDI lanes (advanced lanes load only on explicit request), and a
  hash-pinned full-song arrangement containing every unique project source
  plus only current explicit main/optional MIDI. The arrangement has temporary
  source-only, selected-MIDI, hybrid and main-MIDI presets plus show, mute, solo,
  attenuation, loop and zoom controls. These are browser-tab audition state:
  never treat them as preference, append a decision, persist them, include them
  in a cache key or imply that they change the handoff. Missing MIDI mixer sound
  must be prepared with the neutral renderer; never silently use an existing
  unnormalised preview. Both views start every artifact at recorded zero and
  infer no offset. Long-song views use a fixed Fit/4×/16× viewport with paging
  and playhead centring; paint only visible waveform bins/MIDI notes and bound
  the canvas to 480–1,600 CSS pixels, DPR 2 and a 12,000,000-pixel arrangement
  target. Enforce a 0.5-second minimum viewport, 0.25-second UI overscan with a
  5-second helper maximum, 720/320 default per-stem/arrangement waveform bins
  with an API range of 64–4,096 and a four-document memory-only per-stem cache,
  but state plainly that the full server-bounded timeline JSON is still
  downloaded, parsed and indexed. Enforce 20,000 notes/8 MiB per
  candidate, at most 12 candidates per timeline request and 24 source lanes,
  24 selected MIDI lanes/40,000 notes per arrangement. Abort stale requests.
  Retain a failed refresh's last verified visual only when it still matches the
  current selection, mark it stale and offer Retry; otherwise show explicit
  unavailability while audio/decisions/export remain usable. Treat canvas
  context loss/restoration similarly. Never silently substitute a coarse
  visualization. Per-stem comparison, bounded canonical arrangement presets
  and canonical exact full-song presets use separate decoded transports. Only
  the arbitrary full-song/custom mixer uses coarse HTML media elements that
  share seconds but are not sample-accurate. Source/MIDI levels are not
  normalised.
  The GarageBand Pack Composer has a
  separate persistent basket for exact current main/optional MIDI, the dry
  arrangement proxy and source audio behind an explicit opt-in. It must never
  infer inclusion from playback or mixer state, and its revisions must not
  become decisions, reviews or contribution data. Rejected, needs-correction,
  unreviewed and superseded candidates are ineligible. An explicit catalog may
  also link a lead-vocal S0/M1/M3 hybrid report to its exact existing
  phrase-review manifest. Require exact source, candidate, manifest,
  phrase-geometry and served-audio hashes; never auto-discover the link. Treat
  its ranked ranges only as places to listen. Setting a loop or opening
  `#phrase-N` must not play automatically, append a Workbench event, choose a
  candidate, create hybrid MIDI or enter a pack. The private phrase page may
  contain local paths, so serve only its pinned HTML and semantically
  allow-listed source, MIDI-only and overlay WAVs behind a per-launch loopback
  capability; do not expose its manifest, MIDI, correction seed, evaluations or
  sibling files. Alternative MIDI, Instrument Bundles and persistent/custom mix
  rendering remain planned; do not claim or attempt those later features yet.
  After building one exact GarageBand pack, open its generated guided
  acceptance page before the two human checks. Require all eight tutorial
  slides in order. The slides must teach the installed code architecture,
  execution paths, state planes, invariants, representative failures and code
  review prompts, and the acceptance seed must bind that curriculum to its
  packaged source manifest. Then require exactly 10 one-question-at-a-time quiz
  answers and a 10/10 score. Do not reveal or auto-fill answers, manufacture a
  reviewed export or infer understanding from clicks. The optional live
  Developer Inspector belongs only in Workbench: keep the frozen acceptance
  page offline. The Inspector may expose an allow-listed module/function map,
  bounded operation checkpoints, path-free current state, separate pack state,
  browser-only audition state and a replay through the production event reducer.
  It must be off by default, read-only and memory-bounded; it must exclude
  tokens, paths, URLs, request bodies, private notes, exception text and
  arbitrary evaluation, and its refresh/clear/scrub actions must append no
  event, save no basket, build no artifact and run no model. The first human
  check must use the exact
  downloaded ZIP in GarageBand and cover exact BPM, selected MIDI import,
  playable patches, drum routing where applicable, listened downbeat and
  start/middle/end drift. The second must explicitly confirm an authorised
  local project and usability without JSON editing. Resolve the user's export
  against the exact ZIP with `garageband-pack-resolve`; treat `needs_changes`
  and `incomplete` as valid evidence that leaves the gate open. A downbeat pass
  without catalog metadata is reviewer-observation-only, not a new hash-pinned
  downbeat. A `passed` result opens only read-only Phase 6 Clip entry and does
  not satisfy the separate Phase 5.3 hybrid gates.
  The verified private 22 July 2026 close-out passed all eight tutorial
  screens, scored 10/10 and passed both six-item human checks without an issue
  or `cannot_tell` answer. It verified five selected MIDI payloads, the dry
  proxy and no source audio with all project effects false; its downbeat
  remains `reviewer-observation-only`. That result authorises only the first
  read-only Clip entry, not a hybrid.
  For that Phase 6 entry, require `--clip-library`, `--phase6-acceptance` and
  `--phase6-pack` together. Open the existing Clip v1 catalog read-only and
  expose only bounded browse/search, path-free detail and lineage, optional dry
  neutral audition and deterministic Clip reconstruction. State that the
  reconstructed MIDI is not an original-MIDI byte copy. Do not transform,
  write, tag, version, place, piano-roll edit or hybridise a Clip, and do not
  let browsing or audition alter project decisions or the pack basket. See
  `docs/PHASE6_CREATIVE_ARRANGEMENT.md` for the completed Increment 6.0
  contract and deferred wider Phase 6 work.
  Add `--enable-clip-reuse-plan` only when the user explicitly wants Increment
  6.1. Keep **Browse Clips** and **Proposed reuse plan** distinct. A placement
  pins the exact `clip_id` and object hash and uses the fixed 4/4, 480-TPQ,
  whole-beat grid at recorded zero; it does not infer or apply a project
  downbeat or confirm a time signature. Existing project downbeat evidence must
  be reported as present but not applied. Multiple uses require multiple
  explicit placements. Changing a
  target means explicit removal then placement, not a hidden move or repeat.
  Treat compatibility warnings as facts, never a rank or transformation.
  Proposal state is append-only and separate from decisions, current
  arrangement and pack basket. On a conflict, reload once but never retry the
  mutation automatically. Do not claim a transform, MIDI/render/play/export,
  instrument, pack, feedback, submission or hybrid effect.
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
- One specialist/full-mix/conditioned phrase comparison: use `hybrid-report`
  with exact uppercase S0, M1 and M3 names. S0 must use the matching
  Sunofriend provenance whose `source_stem` resolves to the exact supplied
  source WAV, M1 its `ai-label-split.json`, and M3 its
  `phase5-review-projection.v1` record. The source, BPM, role and phrase
  geometry must describe the same zero-based lead excerpt. Treat 80 ms
  exact-pitch and cross-phrase matches, raw spectrum support, boundary/length
  disputes, octave-equivalent disputes, lane-only notes and duplicates as
  review evidence only. Cross-boundary matches contribute one reference to
  every phrase or review gap touched by an endpoint. Require the command's
  `lineage_status` to say M1's same-song derivation and M3's original MIDI
  payload are unverified; the supplied v1 artifacts cannot establish those
  relationships. Never use agreement as correctness, infer missing chord
  timing, create an H1 MIDI or update a Workbench choice from this report.
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
  `--challenger-run RUN_DIR` values. Select exactly one contract with
  `--setting beam-size` or `--setting batch-size`; beam size is the default.
  Beam mode requires `beam_size` 1→2 with derived strategy
  `greedy`→`beam-search`. Batch mode requires `batch_size` 1→2 while beam
  stays 1/greedy, sampling stays disabled and independent five-second chunks
  stay fixed. V1 requires current, sequential, cache-disabled fresh-process
  runs; source, actual excerpt, BPM, ordered roles, checkpoint/config/worker/
  runtime/device and every other request and execution field must match. Each
  arm must be exactly repeatable in raw/normalized
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
  In batch mode, do not compare `time_to_first_completed_chunk`: the first
  positive progress event represents one completed chunk for batch 1 but two
  for batch 2. Report that geometry explicitly. If the installed runtime does
  not expose MPS, keep the experiment CPU-only rather than claiming an MPS
  result.
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
  not imply decoded, sample-accurate playback in that standalone page. The
  Workbench has separate decoded, sample-scheduled per-stem, bounded canonical
  arrangement and exact chunked canonical full-song paths. Its arbitrary
  full-song/custom mixer remains shared-second HTML media.
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

sunofriend garageband-pack-review "$DOWNLOADED_PACK" \
  --out-dir "$FRESH_ACCEPTANCE_REVIEW"

sunofriend garageband-pack-resolve "$REVIEWED_ACCEPTANCE_JSON" \
  "$DOWNLOADED_PACK" \
  --out "$FRESH_ACCEPTANCE_RESULT"

sunofriend workbench "$INPUT" \
  --candidate-root "$OUTPUT" \
  --catalog "$WORKBENCH_CATALOG" \
  --state-dir "$WORKBENCH_STATE" \
  --clip-library "$EXISTING_CLIP_LIBRARY" \
  --phase6-acceptance "$PASSED_ACCEPTANCE_RESULT" \
  --phase6-pack "$EXACT_ACCEPTED_PACK" \
  --open

sunofriend workbench "$INPUT" \
  --candidate-root "$OUTPUT" \
  --catalog "$WORKBENCH_CATALOG" \
  --state-dir "$WORKBENCH_STATE" \
  --clip-library "$EXISTING_CLIP_LIBRARY" \
  --phase6-acceptance "$PASSED_ACCEPTANCE_RESULT" \
  --phase6-pack "$EXACT_ACCEPTED_PACK" \
  --enable-clip-reuse-plan \
  --open

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

sunofriend hybrid-report "$EXACT_SOURCE_EXCERPT" \
  --role lead \
  --bpm "$BPM" \
  --candidate "S0=$SPECIALIST_MIDI" \
  --evidence "S0=$SPECIALIST_PROVENANCE" \
  --candidate "M1=$FULL_MIX_LABEL_MIDI" \
  --evidence "M1=$LABEL_SPLIT_JSON" \
  --candidate "M3=$CONDITIONED_STEM_MIDI" \
  --evidence "M3=$REVIEW_PROJECTION_JSON" \
  --phrase-review "$PHRASE_REVIEW_JSON" \
  --out "$FRESH_HYBRID_REPORT_JSON"

sunofriend ai-benchmark \
  --run "$SMALL_CPU_REPEAT_1" \
  --run "$SMALL_CPU_REPEAT_2" \
  --out "$FRESH_PERFORMANCE_JSON"

sunofriend ai-setting-compare \
  --setting beam-size \
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
   For `hybrid-report`, confirm exactly three distinct MIDI contents named S0,
   M1 and M3; matching lead-review/evidence schemas and every payload hash the
   supplied contracts can verify; one exact source/phrase review/BPM/timeline;
   and valid projected-stem geometry. Require the path-free report and visible
   lineage statuses `caller-supplied-derivation-unverified` for M1 and
   `manifest-claimed-payload-unverified` for M3—do not claim their missing
   source relationships were verified. Report per-lane note counts, every
   pair's exact/cross-phrase/boundary/octave/lane-only counts, duplicate
   evidence, outside-phrase counts and ranked disagreement phrases. State that
   cross-boundary rows are represented in each touched phrase or gap, source
   support, agreement and ranking are not accuracy or preference, octave
   equivalence remains a dispute, and chords are unavailable when no exact
   timeline is pinned. Confirm zero inference, MIDI creation/mutation,
   selection, promotion and default-change effects. Do not manufacture a
   review, H1 candidate or Workbench choice.
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
   and non-overlapping, and the requested setting is the only semantic change.
   In beam mode require beam 1→2 with its derived strategy change. In batch mode
   require batch 1→2, beam 1/greedy and fixed independent five-second chunks;
   do not directly compare the first progress timestamps because they represent
   one versus two completed chunks. Require exact within-arm raw/normalized
   candidate, note-payload, MIDI, derived-artifact and note-count repeatability.
   Keep candidate-provenance equality separate from musical-output equality.
   Report label, automated quality, boundary, timing and memory differences
   without calling either arm more accurate or faster because of them. Confirm
   selection/promotion/raw/MIDI effects are zero, state that the OS cache and
   order are uncontrolled, and
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
   Treat an exactly equal finite JSON number rewritten by the browser, such as
   `0.0` to `0`, as unchanged. Still reject boolean or string substitutions,
   different numeric values, key/list changes and non-finite numbers.
   Report per-loop resolved identities and preference counts and retain all zero
   effects. Do not turn the listening result into an automatic preset change.
   For the completed private Phase 5.2 beam review, record two equivalent loops,
   a marginal beam-1 preference on 3.50–7.50 seconds, no beam-2 wins and zero
   effects. Keep beam 1 as the default; an equivalent result is not directional
   evidence and does not authorize a merge.
   For the completed private Phase 5.2 batch comparison, record exact 107-note
   and auditionable-MIDI equality across batch 1 and 2, observed batch-2
   pipeline/transcription/RSS ratios of `1.664603×`, `1.845612×` and
   `1.334427×`, unavailable MPS and fixed five-second chunks. No listening
   review is required when musical output is identical. Keep batch 1 as the
   default and preserve every zero effect.
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
    Also report the Project Overview counts and next state/action, confirm the home
    projection contains no paths, private notes or process metrics and confirm
    any offered action is navigation from explicit saved state rather than a
    rank or automatic choice. On a restart/retry check, distinguish restored
    decisions, Overview state, pack choices and URL-hash view/stem from
    intentionally fresh prepared audio/chunks, playhead, loop,
    viewport/zoom/visibility, show, mute, solo and level controls; all temporary
    controls must have zero musical, feedback and export effects.
    Treat `none_usable` and `cannot_tell` as terminal no-selection barriers:
    retain their earlier candidate events as private history, but report zero
    active/exportable MIDI until a later explicit main or optional decision.
    That later decision must not resurrect optional choices from before the
    barrier. Reject or needs-correction alone must not clear the barrier.
    Musical role tags must be one-line path-free descriptions of at most 80
    characters. Reject a new path-like role; for legacy history confirm that
    browser state, contribution preview, timelines, pack names and generated
    proxy-MIDI track metadata use `custom role` while the private raw review is
    unchanged.
    Confirm every declared `effects` field is false, initial connection and
    lazy pack-status failures are retryable, and opening/following the home
    action calls no event, transform or render endpoint.
    When an explicit catalog supplies `review_question` or `listening_focus`,
    report the displayed prompt, confirm its hash is pinned to the review row
    and saved events, and confirm that it caused no selection or ranking
    effect. A changed prompt must create a fresh row rather than restore an old
    choice; prompt text must stay out of the contribution preview.
    Confirm the server binds to `127.0.0.1`, uses a per-launch token, serves
    only catalogued or content-addressed local files, restores choices after
    restart and has no upload/submission endpoint. When rendering, report the
    role-neutral policy, SoundFont identity/hash, cache hit/miss and that the
    original MIDI was not mutated. For an adjacent completed AI run, report
    whether execution was a fresh subprocess, exact-result cache miss, verified
    cache hit, first bounded-session request or reused-model warm request.
    Confirm the application-cache/session evidence was independently verified,
    Workbench enabled neither mechanism, request one was not called warm, a
    cache hit ran no model, and reuse was not interpreted as musical agreement.
    For a precise decoded stem loop, report the
    0.5–15 second recorded-zero range, primary and explicitly opted-in advanced
    candidate counts (six maximum), verified private content-addressed clips,
    one-clock scheduled switching and all false selection/event/ranking/MIDI
    mutation effects. State that no alignment was inferred, that renderer
    previews matched the current SoundFont/policy and that owner-only verified
    renderer/decode snapshots were deleted before publication. Report any
    `silence_padded_frames` as generated end silence, not missing transcription,
    plus the 2 GiB all-input (source, candidate MIDI, SoundFont and preview)
    bound with early pre-render rejection, the 64 MiB output bound and the
    32-entry/256 MiB rebuildable-cache policy. If an old loop was evicted,
    prepare it again
    without treating eviction as lost project work. If the compatibility
    fallback was needed, describe it as second-synchronised, not
    sample-accurate, and feedback/event-free. For a precise decoded arrangement
    loop, report its context-neutral manifest hash, deduplicated source and
    distinct selected-MIDI counts, 24-track maximum, exact canonical group
    membership, pre/post-render stale-selection check and atomic one-clock
    switching. State that it is unity-gain, unlevelled/unlimited, recorded-zero
    and feedback-free. Do not imply that its four canonical presets make the
    coarse full-song/custom mixer sample-accurate. For long-song visualization,
    report Fit/4×/16× fixed-window culling and bounded canvases, but disclose
    that the complete server-bounded JSON is still downloaded, parsed and
    indexed. Report 20,000 notes/8 MiB per candidate, 12 candidates per request
    and arrangement limits of 24 source lanes, 24 selected MIDI lanes and
    40,000 notes. Confirm stale fetches cannot replace current evidence; a
    compatible last verified visual is marked stale with Retry, otherwise the
    visual is explicitly unavailable. Confirm no coarse visual fallback.
    For an exact full-song canonical preset, report the immutable stream hash,
    exact roster, anchor sample rate, longest-source end, recorded-zero start,
    integer-frame/ties-even boundaries, separate PCM16 tracks, silence padding,
    unity gain and current-plus-next decoded retention. Report that a not-ready
    next chunk stops at the verified boundary, late completion enables explicit
    Play, and absent or failed data requires Retry; neither auto-restarts;
    confirm no coarse playback starts silently. Report the 24-track, 20-minute,
    2 GiB, mono/stereo 8–96 kHz, five-second, 480-chunk, 32 MiB PCM16, 192 MiB
    two-decoded-chunk, 16 active-plan, 768 media-capability and shared
    32-entry/256 MiB cache bounds. For an arrangement/handoff,
    report exact selected main/optional counts, proxy
    track count, BPM policy and ZIP path;
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
    For every handoff, confirm rejected/needs-correction/unreviewed files are
    excluded, Workbench-generated names/manifests contain no private review
    notes or absolute paths, and numbered selected MIDI bytes are unchanged.
    State whether source audio stayed excluded through the safe default or was
    separately opted into a custom pack. Exact copied MIDI/source payloads are
    not metadata-scrubbed and may retain embedded producer metadata. Exported
    local JSON may contain absolute paths and private notes; the separate
    contribution preview must contain neither.
    For the Phase 5.9 guided acceptance page, confirm that eight tutorial
    slides contain the technical code-map fields and a source-manifest/code-
    binding hash before exactly 10 one-at-a-time questions. Confirm a wrong
    answer leaves the two checks locked, retry resets the full quiz, and only
    10/10 enables the explicit GarageBand then authorised-usability sequence.
    When `--developer-inspector` is enabled, confirm its endpoint is GET-only,
    token protected, absent by default, path/note/token free, replaying the same
    production reducer, and zero-effect under refresh and scrubbing. Report the exact
    downloaded pack hash, quiz score, both check outcomes and whether downbeat
    evidence was catalog-and-reviewer or reviewer-observation-only. For
    `garageband-pack-resolve`, confirm the resolver reverified strict receipt
    fields, canonical member identities and payload hashes, omitted private
    note text, wrote a fresh path-free result and declared every effect false.
    `passed` may make only `phase6_read_only_clip_entry_ready` true;
    `explicit_hybrid_construction_ready` must remain false until the Phase 5.3
    gates close.
    For Phase 6 Increment 6.0 Clip entry, confirm the server accepted all
    three explicit inputs, reverified the passed result and exact pack before
    opening the existing library, and exposed no Clip capability when the
    flags were absent. Report Clip/library state hashes, bounded result counts,
    path-free detail and lineage, reconstruction timing/BPM and optional dry
    renderer identity. State that the MIDI is a deterministic Clip
    reconstruction, not the original MIDI bytes. Confirm library/Clip/source/
    project-decision/basket/feedback/submission effects are false and that no
    transform, write, piano roll, placement or hybrid route exists.
    The verified local completion exposed 73 Clips/51 lineages and exercised
    browse/detail, deterministic MIDI, a dry FluidSynth proxy, a repeat cache
    hit, path-free byte-range serving and Developer Inspector tracing with zero
    musical/library mutations. Do not interpret that slice as completion of
    broader Phase 6.
    For Phase 6 Increment 6.1, confirm all four launch flags, the separate
    proposal capability and the absence of proposal routes when its flag is
    omitted. Confirm an empty read creates no database, the first explicit
    action creates owner-only `STATE_DIR/phase6-reuse/reuse.sqlite3`, and an
    exact restart restores only the same project/setup/source,
    acceptance/pack, complete-library, policy and grid binding. Report each
    pinned Clip/object hash and explicit whole-beat target. Confirm the fixed
    4/4, 480-TPQ recorded-zero grid does not assert a musical downbeat or time
    signature. Report the 64-active-placement, 512-event, 20,000-notes-per-Clip,
    40,000-active-note-instance and 20-minute bounds. Treat key/BPM/timing,
    overlap and instrument warnings as descriptive compatibility only. On a
    stale plan, confirm one reload and no automatic POST retry. Confirm the
    proposal changes no Clip/library, MIDI, transform, decision, current
    arrangement, pack, render/play/export, instrument, feedback or submission
    state. The verified completion exercise placed and removed one real Clip,
    recovered both revisions across restarts and confirmed unchanged
    decision/library/pack inputs. Describe Increment 6.1 as complete while
    keeping broader Phase 6 in progress.
