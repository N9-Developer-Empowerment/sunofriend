<!-- sunofriend-interface-contract: 2026-08-01.1 -->

# Sunofriend advanced operations

This reference preserves Sunofriend's detailed operational contracts. Read it
completely before running an advanced, expert or developer workflow from the
main skill.

## Contents

- [Preflight](#preflight)
- [Choose the workflow](#choose-the-workflow)
- [Musical and data rules](#musical-and-data-rules)
- [Validate and hand off](#validate-and-hand-off)

**Listen deeper. Create further.** Sunofriend takes its name from the Hindi
**सुनो** (*suno*), “listen,” and is an independent Unsigned Media Ltd project,
not related to or affiliated with Suno Inc., the AI music company.

Keep the newcomer contract in the main skill authoritative. Use
`sunofriend demo --out-dir FRESH` for the copyright-safe no-stems route and
`sunofriend create PROJECT --out-dir FRESH` for an agent-led automatic real
stem result. Both call the same production Simple runner and remain automatic,
unreviewed and source-audio-free.

Prefer the packaged `sunofriend tui` Guided Local Studio when a person wants
to operate Sunofriend directly. It opens in **Simple / Make my song** mode:
one explicit action runs the production conversion, chooses only each exact
published primary, and creates separately labelled automatic, unreviewed MIDI,
a balanced MIDI-derived song-interpretation WAV and a starter ZIP. It writes no
human Workbench choice or feedback event. Use `sunofriend tui --mode studio`
to open immutable multi-method comparison first, or use the TUI's persistent
Simple/Studio switch (`F2`/`F3`) in either direction. Switching restores the
last Studio tab and changes only memory-only navigation: it starts no process
and changes no review, feedback, MIDI, selection, pack or export state. Use
Studio for explicit choices, feedback, technical inspection and a reviewed
GarageBand handoff. Use the packaged `sunofriend` CLI
as the deterministic audio and MIDI engine and the loopback Workbench as the
rich Studio comparison/decision/render/export surface. Here interpolation means
a creative interpretation of melody, harmony, rhythm and structure, not
waveform or production-effect reconstruction. Source stems supply timing,
horizon and level evidence but are not mixed into the WAV. Retain direct CLI
operation for expert, scripted and agent-led workflows. Do not reimplement
transcription, evaluation, MIDI transformation or the accepted mix policy in
ad-hoc scripts or TUI callbacks.

Read [the generated public interface contract](interface-contract.md)
before choosing a command. It is versioned with this skill and distinguishes
the current direct TUI actions from expert CLI commands that do not yet have
guided forms.

## Preflight

1. Work locally. Do not upload stems, vocals, MIDI, or chord files.
2. Resolve `sunofriend` from `PATH`. In the Sunofriend repository, fall back to
   `.venv/bin/sunofriend`.
3. Run `sunofriend --version`, `sunofriend --help`, and the selected command's
   `--help` before constructing a command.
4. Before an advanced workflow invokes one of Sunofriend's model setup
   scripts, resolve the separately installed application checkout as
   `SUNOFRIEND_APP_ROOT`. Prefer a user-supplied, explicitly approved checkout;
   otherwise use the current workspace only when it contains Sunofriend's
   `pyproject.toml` and `scripts/`, then try
   `~/.local/share/sunofriend/app`. Verify that it is a Git checkout of
   `https://github.com/N9-Developer-Empowerment/sunofriend`, report its exact
   commit, and obtain approval before any setup download or install. Never
   resolve these application resources relative to the separately installed
   skill directory, scan the whole home directory, or silently fetch, pull,
   reset, or switch the checkout.
5. Run the narrowest capability check:
   - `sunofriend tui` is the preferred human route. Its default **Make my
     song** tab accepts one top-level WAV stem folder and a fresh output path.
     One **Create MIDI + WAV** action runs production repair conversion with
     variants and vocals, consumes only the exact primary published by each
     bounded production summary, renders the existing balanced MIDI-only mix,
     and publishes `AUTOMATIC-SONG/` with individual MIDI, combined GM MIDI,
     WAV, receipt, start guide and ZIP. The result is always marked automatic,
     `not_reviewed` and `review_recommended`; ambiguous, missing, silent or
     diagnostic-only roles are omitted visibly. It never writes a Workbench
     human decision or feedback event and never calls the result a reviewed
     GarageBand pack or release master. Cancellation stops at a safe boundary,
     and every run requires a fresh output outside the source project.
     Use `sunofriend tui --mode studio`, the visible **Studio** switch or `F3`
     to load existing candidates, show key/BPM/tuning and
     stem/candidate/decision state,
     draw compact primary MIDI maps, run local diagnostics and open/stop the
     graphical Workbench. Studio also has one explicit **Convert all stems**
     operation. Its editable **Fresh conversion output**
     must not exist; `--conversion-output` only prefills the field and never
     starts work. After confirmation it runs production `listen-all` in repair
     mode with variant evaluation, then production `vocal-melody` separately
     for discovered lead and backing vocals. It discloses `wind` → `lead`,
     `rhythm` → `keys` and `other` → `synth` proxy engines and visible
     near-silent skips. Completion names skipped, failed and proxy roles plus
     bounded warnings, and reload verifies fresh-root coverage for every role
     reported converted. Progress is streamed; cancel preserves the partial
     root; success reloads the fresh root. That Studio conversion never
     overwrites or auto-selects.
     Relaunch without `--catalog` for conversion because an explicit catalog
     would ignore newly discovered automatic candidates.
     Its native **Master** tab can then create or reuse the separate
     fixed-policy Listening Master challenger after the current balanced
     selected-MIDI WAV has been explicitly created in Workbench. It exposes no
     mastering controls, records no preference, and leaves listening/download
     comparison plus the bounded blind quality review, explicit resolution and
     same-window identity-labelled native-level readiness review in Workbench.
     There is no durable conversion job ledger or automatic retry. Broader
     structured improvement feedback remains planned; the implemented master
     reviews record only their explicit, separate local responses. Workbench
     remains the rich visual listening, review,
     rendering and download surface. The TUI enables the read-only Developer
     Inspector by default.
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
     `"${SUNOFRIEND_APP_ROOT}/scripts/setup-game-model.sh"`; inference itself
     must remain offline.
   - `sunofriend ai-doctor --require rmvpe` before a standalone RMVPE F0
     bake-off. Its explicit setup command is
     `"${SUNOFRIEND_APP_ROOT}/scripts/setup-rmvpe-model.sh"`; inference must use
     the existing local ONNX file and remain offline.
   - `sunofriend ai-doctor --require pesto` before a standalone PESTO F0
     bake-off. Its explicit setup command is
     `"${SUNOFRIEND_APP_ROOT}/scripts/setup-pesto-model.sh"`; inference must use
     the hash-checked local `.ckpt` file and remain offline.
   - `sunofriend ai-doctor --require demucs` before the experimental learned
     `ai-cleanup` workflow. The explicit setup action is
     `SUNOFRIEND_ACCEPT_DEMUCS_PRIVATE_EVALUATION=1
     "${SUNOFRIEND_APP_ROOT}/scripts/setup-demucs-model.sh"`; keep the
     checkpoint external/private, verify its full hash and never download or
     select a model during inference.
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
     program/gain contract. `midi-ab-status` and `midi-ab-resolve` need no
     audio, ML or preview capability. Status verifies only public review
     evidence and never opens the answer key; resolution verifies one
     explicitly exported reviewed JSON against the separately supplied
     original unchanged package directory and then opens the sealed key.
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
   - `sunofriend listening-master` requires the `convert` audio runtime and an
     existing local FFmpeg executable with the `loudnorm` filter. The command
     verifies both before writing. Its input is an existing reviewed balanced
     MIDI WAV; both `--out` and `--report` must be fresh paths.
   - `sunofriend doctor --require convert` for factory-sample matching or
     stem-derived sample instruments. Also require `preview` for rendered GM
     matches and for sample instruments unless using `--no-preview`.
     Optional learned instrument evidence additionally needs the explicit,
     existing local OpenL3 path created by
     `"${SUNOFRIEND_APP_ROOT}/scripts/setup-openl3-model.sh"`; matching itself
     must remain offline and hash-check the model.
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
     explicit neutral-preview, dry selected-arrangement or
     GarageBand-handoff render actions. The MIDI-derived song-interpretation
     WAV also measures and mixes rendered MIDI audio with NumPy and SoundFile,
     so require `sunofriend doctor --require convert` before creating it.
     Before a fresh **Create Listening Master challenger** build, also require
     SoundFile and an existing local FFmpeg executable with the `loudnorm`
     filter. Workbench and the TUI **Master** tab apply only the fixed
     `ffmpeg-loudnorm-two-pass-fixed-horizon-v1` policy to the exact current
     balanced control. An exact verified cache hit may be reused without
     rerunning that dependency preflight. The TUI accepts no source path,
     output path, loudness target, filter or mastering parameter: it rereads
     the private event state, binds the current selection and balanced-control
     hashes, rechecks both after preparation, and promotes only if they still
     match. It must reread them once more immediately after promotion before
     reporting success; concurrent drift fails closed and the content-addressed
     artifact is not reported as current. It locks project changes, conversion
     and Workbench launch while the synchronous verified build runs. Do not
     claim immediate cancellation; TUI Quit is deferred while that operation
     remains active.
     Before a Workbench Stage 4 bass or keys instrument comparison, require
     `sunofriend doctor --require preview`, the current selected arrangement
     and its verified local SoundFont. The server owns the pair: bass uses
     zero-based GM programmes 38/39 and coverage `not_required`; keys uses
     programmes 4/5 and must privately render and pass both identities through
     the representative channel/pitch/soft-medium-strong velocity-bucket
     preflight before it publishes A/B media. Treat
     `functional_status: passed` only as measurable-response evidence and
     always require `quality_status: review_required` plus listening to the
     unchanged selected-MIDI A/B.
     `--developer-inspector` is an optional read-only
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
   - Phase 6 Increment 6.2a is complete and uses the same three gate inputs plus
     `--enable-clip-transforms`. Reject that flag without the complete gate and
     reject it together with `--enable-clip-reuse-plan`: reuse v1 pins the
     complete library state while a successful transform appends a new child.
     Previewing a same-mode key or musical/stem-locked BPM change needs no
     audio, ML or playback capability. Creation adds exactly one immutable
     Clip version. A later neutral audition needs `doctor --require preview`.
   - Phase 6 Increments 6.3a–e use those same three gate inputs plus the separate
     `--enable-clip-corrections` flag. Reject it without the complete gate and
     reject it together with reuse-plan or key/BPM-transform mode. It accepts
     exactly one user-selected pitch, attack-velocity, `note_delete_patch`,
     `note_onset_shift_patch` or `note_end_shift_patch` for 1–64 exact existing notes in one bounded
     480-TPQ phrase window. Velocity, deletion, onset and note-end shift are valid for
     drums; pitch is not. Deletion must
     retain at least one note and its eligibility must prove exact normalized
     parent-minus-named-interval topology with unchanged survivors and
     beat/export/source horizons. Onset shift must move Note On and Note Off by
     the same explicit non-zero delta of at most 480 ticks while preserving
     duration, pitch and expression. Do not infer notes, intensity, noise or
     preferred timing, snap to a key/chord/grid, normalize dynamics, apply a
     repeated-phrase repair, quantise or treat review as a preference. Preview has zero effects; creation
     appends one immutable child; an exact retry is a zero-effect replay. A
     Note-end shift must keep Note On fixed, move only Note Off by an explicit
     non-zero delta within ±480 ticks and retain at least one tick of duration.
     A later neutral audition needs `doctor --require preview`. Increments 6.3c
     through 6.3e are complete. For 6.3d require the capability to advertise
     `note_onset_shift_patch` and `maximum_onset_delta_ticks: 480`; generic
     `timing` deliberately remains false. For 6.3e require
     `note_end_shift_patch`, `maximum_note_end_delta_ticks: 480` and
     `minimum_note_duration_ticks: 1`.
5. Inventory the input directory read-only. Confirm files exist and identify
   stem roles, chord PDF, metronome, key, BPM, and tuning.
6. Use absolute, quoted paths and a fresh output outside the source folder.
   Never add `--overwrite` unless the user explicitly asks to replace output.
7. If the CLI or a dependency is missing, report the exact component. Install
   packages or download a SoundFont only when setup is within the request.

## Choose the workflow

- Human operator who wants a useful automatic starting arrangement: start with
  `sunofriend tui [PROJECT]`, review the suggested fresh sibling output, then
  press **Create MIDI + WAV** once. Do not reinterpret its automatic primaries
  as human-reviewed choices. Open the published WAV first, import the individual
  MIDI into GarageBand, and use Studio if any role needs comparison or repair.
- Human operator who wants detailed comparison and visible state: start with
  `sunofriend tui [PROJECT] --mode studio` and add the same narrow `--candidate-root`,
  optional `--catalog`, `--state-dir` and `--soundfont` inputs that should be
  passed to Workbench. Use its **Open visual studio** action for waveform/MIDI
  timelines, synchronized audition, explicit decisions, the MIDI-derived
  song-interpretation WAV, Inspector and exact GarageBand pack. TUI
  highlighting, maps, diagnostics and activity are zero-effect. Use
  `--no-developer-inspector` only when the extra read-only developer view is
  not wanted. See `docs/LOCAL_STUDIO_TUI.md`.
  When the project has not been converted, instead prefill a fresh path with
  `--conversion-output FRESH`, review the editable field, choose **Convert all
  stems** and explicitly confirm. The initial runner orchestrates only the
  fixed full-project repair/variant recipe described in Preflight. Cancellation
  leaves a partial root and cannot resume after restart; do not treat it as
  success or delete it automatically. After success the TUI reloads the root;
  open Workbench to compare and select, never to transcribe.
- Whole instrumental stem folder: use `listen-all`; default to
  `--conversion-mode repair` and leave evaluation enabled.
  For bass, retain all five claims separately: `raw_verified`,
  `contour_clean`, `octave_resolved`, `continuous_sustain` and `root_safe`.
  Repair mode still selects `contour_clean`. `octave_resolved` may shift only
  a one- or two-octave harmonic when pYIN is voiced across at least 70% of the
  note and one exact rounded pitch dominates at least 80% of those voiced
  frames. `continuous_sustain` starts from that candidate and may extend a
  note end only across a 35 ms–1.25 beat gap where source RMS activity, pYIN
  voicing and the same exact pitch each meet their configured evidence gate.
  Do not describe either challenger as a theory repair or automatic winner.
  MIDI note gates can represent continuous accompaniment but not the source
  waveform's buzzing texture; review contour/register, continuity/true rests
  and patch texture as separate questions.
- Existing source/MIDI/preview result space: use `workbench` with the original
  stem directory and only the narrow candidate roots intended for that song.
  It is a loopback-only presentation and explicit-decision boundary, not a
  transcriber. Preserve Sunofriend's multi-process identity: specialist,
  analytical, tracker-consensus, conditioned-AI and reviewed repair candidates
  are separate evidence, and a different process may be useful for each role
  or phrase. Never collapse them into one automatic winner or imply that a
  model label, score, preview count or visible default is preference. Prefer an
  explicit `sunofriend.workbench-catalog.v1` document
  when filenames cannot distinguish songs or audible roles. Automatic
  discovery must remain role-specific: reject arrangement-named MIDI, require
  one consistent inferred role across note-bearing Clips, prefer one
  unambiguous basename role over a bounded parent-name fallback, reject
  explicit BPM differences greater than
  `max(0.5 BPM, 0.5%)`, reject an explicit tonic/mode mismatch, and remove both
  byte-identical and neutral-audition-equivalent note geometry. An explicit
  catalog is the only route for intentionally including a combined,
  transformed or otherwise automatically ineligible candidate. Retain a
  malformed or note-free role-specific file only as an explicit
  unavailable/empty diagnostic lane. Treat at most
  three primary candidates as the normal result space, keep diagnostic files
  advanced, and do not infer preference from audition events, dwell time or
  unclicked defaults. Prefer the content-addressed role-neutral preview when an
  existing WAV is absent or uses a different sound. Require
  `role-neutral-general-midi-v3`; bass uses zero-based program 38, displayed as
  **GM 39 Synth Bass 1 proxy**, not a plucked finger-bass proxy. For precise per-stem
  listening, prepare a 0.5–15 second decoded loop: primary candidates are
  included by default, an advanced candidate requires explicit **Include in
  precise loop**, and no more than six candidates may be requested. Source and
  neutral MIDI clips share one decoded Web Audio clock with scheduled switches
  and one absolute playhead. They all begin at recorded zero; do not infer an
  alignment offset. Preparing, playing, switching, seeking, pausing or stopping
  must not append an event, change a selection, rank a process or mutate MIDI.
  The precise per-stem artifact must use
  `recorded-zero-source-frame-window-level-matched-v2` and
  `common-target-active-block-rms-v1`. Measure each decoded source/candidate
  independently by median active non-overlapping 400 ms block RMS with the
  −70 dBFS absolute and 10 dB relative gates, aim at −18 dBFS, bound target
  trim to −24…+12 dB and reduce it when required for −1 dBFS sample-peak room.
  Show every signed gain and apply it only through a Web Audio `GainNode`;
  never rewrite the source, preview WAV or MIDI. Call this gain-only comparison
  assistance, not LUFS, true-peak, compression, limiting, mastering or
  blinding. Neutral preview cards and the compatibility fallback remain at
  renderer gain.
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
  Keep the **Balanced MIDI-derived song interpretation** separate from all
  three playback contracts. It is available only in ordinary Workbench after
  explicit main/optional choices exist; there is no standalone balance CLI.
  POST only the current
  `sunofriend.workbench-arrangement-selection.v1` manifest hash to
  `/api/balanced-arrangement`; never supply or accept browser-defined tracks,
  roles or gains. Re-derive and verify the current selection before and after
  the build. Use each verified source stem only as a level reference for its
  verified neutral MIDI preview; never mix source audio into the balanced
  selected-MIDI WAV.
  Require policy `source-referenced-summed-group-balance-v3`. Measure median
  active non-overlapping 400 ms block RMS with the −70 dBFS absolute and 10 dB
  relative gates. Zero-pad a final partial block for analysis only without
  extending the written horizon. Clamp each source-match trim to −24…+6 dB. When multiple
  selected lanes share one source SHA-256, measure their actual provisionally
  matched waveform sum and calibrate the group towards one source reference.
  Do not assume the lanes are uncorrelated. If the source has no measurable
  active block, require the disclosed −6 dB drum or 0 dB non-drum fallback.
  Use the shared conservative token-aware role semantics for bus membership:
  canonical drum/percussion roles are drums, generic `rhythm` is non-drum and
  pitched `steel drums` remain melodic. Do not infer the bus from waveform
  loudness. When drum and non-drum
  buses have time-aligned active 400 ms windows, apply one common drum trim of
  at most −18 dB aiming for median drum level at least 2 dB below non-drums and
  p95 drum excess no more than 3 dB. Use a 30 dB per-bus relative overlap gate
  with the −70 dBFS absolute floor; if no windows overlap, apply 0 dB. Report
  required/applied gain and exact before/after differences on one fixed
  pre-guard qualifying-window cohort. Keep both reported gate fields at those
  selection thresholds, including the −70 dBFS floor; shift only the measured
  drum/non-drum differences. Report clamp state and target status. Target
  −18 dBFS median active-block RMS, cap only positive
  normalisation boost at +12 dB, allow attenuation without an artificial lower
  bound, and allow peak protection to attenuate further for a −1 dBFS
  sample-peak ceiling; report target error/status, visibly identify which
  limit prevented the target when unmet, and require zero full-scale samples.
  Fix the output horizon to the longest verified source stem across the whole
  project, including unselected/vocal stems. Record every source horizon,
  per-lane padding and any excluded neutral-preview tail; never let a renderer
  or transcription overrun silently extend the balanced source-song audition.
  Keep compression, limiter, EQ, saturation, reverb, chorus and stereo widening
  off. Require `mastered: false` and say this is gain-only audition
  normalisation/sample-peak protection, not LUFS, true-peak or final mastering.
  Preserve the prepared dry proxy and every precise unity-gain transport.
  Creating, caching, downloading or playing the balanced WAV/receipt/recipe
  must record no preference/event/feedback and change no source, MIDI,
  selection, ranking or default. The artifacts are not currently eligible for
  GarageBand Pack Composer v1; download the fader recipe separately and finish
  patch choice, automation, mixing and mastering in GarageBand.
  Bound the rebuildable balanced cache independently to eight entries and
  2 GiB. Before full or Range serving, copy and hash/size verify each balanced
  file into a per-request disk-backed anonymous snapshot; return 409 on drift
  and 503 when temporary snapshot storage is unavailable.
  Keep `sunofriend listening-master` as a separate challenger downstream of
  that unchanged gain-only control. The standalone command accepts fresh
  output paths, while ordinary Workbench and the Guided Local Studio
  **Master** tab expose an explicit **Create / reuse Listening Master** action
  only after the exact current balanced artifact exists. Workbench requests
  contain exactly the current selection-manifest hash and
  balanced-arrangement manifest hash; never accept browser-supplied audio
  paths, targets, filter graphs or policy choices. The TUI supplies neither
  hashes nor paths from editable widgets: its typed runner derives them from
  the loaded catalog and read-only event state, reusing the same artifact and
  mastering services.
  Recheck both identities before and after rendering, then publish a separate,
  owner-only, content-addressed WAV and receipt. Retain the balanced v3 player,
  downloads and required-product status unchanged. For the native TUI action,
  check the promoted cache first; on a miss run the path-free SoundFile,
  pinned-FFmpeg and `loudnorm` preflight, prepare privately, reread state,
  recheck both hashes and discard the exact pending token on drift before
  promotion. Reread once more after promotion and refuse a successful/current
  result if a separate local writer changed either identity in that final gap;
  an old content-addressed cache entry is harmless and must not be presented as
  current. Progress must stay bounded and path-free. There is deliberately no
  pseudo-cancel around the synchronous FFmpeg builder; defer Quit until its safe
  completion.
  Keep the Workbench blind control-versus-challenger review separate from
  creation and playback. It may prepare only one exact 0.5–15 second window
  bound to the current selection, balanced-control and Listening Master
  manifests. Require both inputs at or above −60 dBFS fixed-window sample RMS;
  attenuate only the louder crop, by at most 18 dB, and require final PCM16 A/B
  mismatch at or below 0.05 dB. Do not call this LUFS, true-peak or
  perceived-loudness matching and do not boost, limit, compress, equalise,
  resample, shift or stretch either review crop.
  Preparation may create only the private comparison session and rebuildable
  A/B audio cache; it must record no feedback/preference and change no
  Workbench decision or product state. Replay, switching, seeking and form
  drafts must write nothing. Do not persist or accept a raw reviewer key in
  browser storage or the HTTP request. The loopback server derives one stable
  project-scoped local reviewer key, and the review service stores only its
  domain-hashed identity. Canonicalise requested times to exact frame bounds
  before hashing the comparison, and let concurrent identical preparations
  reuse only a fully verified publication winner.
  Require explicit heard-A and heard-B confirmations plus exactly one of A, B,
  equivalent, neither or cannot-tell before completion. Bound allow-listed
  tags to eight per candidate and private notes to 2,000 characters. Completion
  alone appends the blind feedback revision. Identity resolution must be a
  separate explicit action that reveals and verifies the nonce-derived
  assignment. Neither action may alter Workbench decision events, MIDI,
  selection, ranking, defaults, either product artifact, product completion or
  GarageBand Pack state, and a resolved result must never imply promotion.
  Only after that latest blind response is complete and explicitly resolved
  may Workbench offer the separate identity-labelled native-level readiness
  review. Determine latest across every comparison window for that project
  and local reviewer, not only revisions within the submitted window. Bind it
  to the quality review ID/SHA, resolution SHA, current
  control/master manifests and the same exact canonical frame window. Do not
  accept new times, paths, gain values or processing parameters. Write private
  PCM24 Balanced control and Listening Master crops at linear scale `1.0` and
  applied gain `0.0 dB`; do not match, boost, attenuate, normalise, limit,
  compress, equalise, resample, shift or stretch them. Keep both browser
  volumes at unity and do not autoplay. On cache reuse and restart, re-read
  the freshly hash-verified exact source frames and require sample equality
  with each PCM24 crop; never trust a self-rehashed local crop manifest alone.
  Show identities honestly because A/B has already been resolved. Require
  explicit heard-control and heard-master confirmations plus exactly one of
  balanced control, Listening Master, equivalent, neither or cannot-tell.
  Reuse the bounded tags and private-note limits. Store the response in a
  separate owner-only immutable ledger: replay an exact retry, conflict on a
  changed retry, and expose export only as a read. Readiness evidence must not
  revise the blind quality choice, approve a release master, promote either
  file or change any Workbench/MIDI/product/default/pack state.
  Both routes use fixed policy
  `ffmpeg-loudnorm-two-pass-fixed-horizon-v1`: two-pass FFmpeg EBU R128
  analysis/rendering at −16 LUFS integrated, 11 LU loudness-range target and
  −1 dBTP true-peak ceiling, followed by resampling and an exact trim back to
  the input frame horizon, then an independent analysis of the encoded PCM24
  artifact. Require private workspaces and files to be owner-only from
  creation, plus device/inode-checked publication and rollback. Require a fresh
  PCM24 WAV and fresh path-free JSON receipt. Hash the source, output and
  FFmpeg executable; retain the source, render and encoded-artifact
  measurement sets and the exact target/processing/effect contract. Report
  `mastered: true` and `release_master: false`: it is a
  machine-produced comparative listening master, not human release approval.
  It may use dynamic loudness processing but no EQ, widening, reverb, chorus or
  saturation. It must not overwrite or replace the praised balanced control,
  change MIDI/source/selection/ranking/defaults, or imply a listening
  preference. Creating, caching, playing or downloading it must also have no
  review, event, pack or product-completion effect. Compare the control and
  challenger by ear before adopting any future default.
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
  share seconds but are not sample-accurate. Canonical arrangement/full-song
  and coarse-mixer source/MIDI levels are not normalised; this does not apply
  to the separately prepared, disclosed-gain precise per-stem loop.
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
  Add `--enable-clip-transforms` only when the user explicitly wants Increment
  6.2a. Keep it separate from reuse-plan mode. On exact Clip detail choose one
  operation: a target key with the same source major/minor mode and explicit
  nearest/up/down direction, or a finite target within both 20–400 BPM and
  0.25–4 times the source BPM, with explicit `musical` or `stem_locked`
  meaning. `musical` keeps beats and changes elapsed time; state that untreated
  audio will no longer align. `stem_locked` keeps source seconds and moves
  beats; state that this is not an audible speed-up.
  Require **Review temporary transform** before **Create immutable Clip
  version**. Any edit invalidates the projection. On conflict reload detail
  once, retain only the draft and never replay the POST automatically. One
  fresh action creates one child, so key plus BPM needs two visible lineage
  steps. Treat an exact create-request retry as an idempotent replay of the
  already-existing child: it appends nothing and every effect is false. At the
  accepted 10,000-Clip boundary disable review/create while retaining existing
  Clip inspection, audition and export.
  Confirm the parent, all other process alternatives, reuse storage,
  placements, decisions, current arrangement, pack, instruments, feedback and
  submission remain unchanged. Defer major/minor remapping, tuning, downbeat,
  register, note/phrase, batch and hybrid transforms.
  Add `--enable-clip-corrections` only when the user explicitly wants Increment
  6.3a, 6.3b, 6.3c, 6.3d or 6.3e and can recognise the wrong pitch, attack
  intensity, unwanted/extra MIDI note, exact onset or Note Off to move.
  Keep it separate from transform and reuse-plan mode. Load a half-open phrase
  window of at most 32 quarter-note beats and 15 rendered seconds. It uses
  integer 480-TPQ export ticks and does not quantise the Clip. Nothing is
  preselected. For pitch, choose at most 64 exact visible note references,
  keep every target from 0–127 and no more than 24 semitones from its source,
  then require **Review temporary pitch correction** before **Create immutable
  corrected Clip**. Any window or pitch edit invalidates review.
  Treat scale/chord labels as advisory and never choose a replacement from
  them automatically. Reject new same-pitch overlap/duplicate-onset ambiguity.
  On conflict reload detail/window once and never retry the write POST. A fresh
  action adds one deterministic child; exact replay adds nothing. Confirm
  timing, duration, source seconds, microtiming, velocity, key, chords,
  instrument, provenance, unaffected notes, decisions, arrangement, proposal,
  pack, feedback and submission remain unchanged. After restart, expose only
  the validated bounded correction summary, never arbitrary recipe parameters.
  Reject a parent before preview unless its complete preserved deterministic
  MIDI stream is encodable: at most 20,000 notes and 20,000 chords, four-byte
  variable-length note/chord/tempo ticks, three-byte tempo values,
  byte-encodable time signatures and bounded title/chord meta payloads.
  For attack velocity, choose **Attack loudness (MIDI velocity)** before
  loading the window. It accepts 1–64 exact target integers from 1–127 and is
  available for drum Clips. Reset before switching kind; never mix pitch and
  velocity in one draft or child. Focus/navigation and typing alone have zero
  effect; **Apply** changes the draft. Treat velocity as patch-dependent Note
  On intensity, not dB, track volume, release velocity, CC7/CC11 expression or
  a loudness guarantee. Block notes marked `duplicate-export-note-on` because
  they collapse to one exported event. Confirm pitch, timing, duration, source
  seconds, microtiming, release velocity, articulation and metadata remain
  unchanged.
  For exact removal, choose **Remove unwanted/extra MIDI notes** and require
  the advertised `note_delete_patch` capability plus retained
  `delete_clip_notes` operation from the isolated `workbench_deletion.py`
  policy. It is valid for pitched and drum Clips. Focus or note navigation is
  inspection only: require explicit **Mark for removal**,
  then **Review temporary note removal**, then **Create immutable corrected
  Clip**. Accept 1–64 unique exact existing refs and retain at least one note.
  Block duplicate/cascade-dependent export groups, any horizon-changing note
  and the only remaining note. Require normalized child MIDI to equal
  normalized parent MIDI minus exactly the named intervals; every survivor and
  beat/export/source horizon must remain exact. Keep pitch and velocity v1
  frozen and never mix kinds in one draft or child. Treat fresh-create effects
  as true only for `library_mutated`, `child_clip_created`,
  `correction_applied`, `note_count_changed` and `note_deleted`; preview,
  replay and restart audit have zero effects. Never
  classify noise, audition a draft, rank, select, place or export automatically.
  Increment 6.3c is complete.
  For bounded onset shift, choose **Move existing note earlier or later** and
  require explicit capability `note_onset_shift_patch` plus
  `maximum_onset_delta_ticks: 480`. Its isolated policy is
  `workbench_onset.py` and retained operation is `shift_note_onsets`. Accept
  1–64 unique exact existing pitched or drum note refs with exact integer
  `target_start_tick` values; every non-zero delta must be within ±480 and
  both source and target full intervals must fit the loaded half-open window.
  Focus/navigation/typing are zero-effect; require explicit Apply, zero-write
  review, then Create. Move normalized Note On and Note Off by the same delta,
  preserving duration ticks, pitch, attack/release velocity, articulation and
  note count. In musical mode add `delta / 480` to start beat, retain duration
  beats and both microtiming values, and recompute source seconds through the
  tempo map. In stem-locked mode require both microtiming fields exactly zero,
  shift source start/end by `delta * 60 / (export_bpm * 480)`, retain source
  duration and derive beats. Require exact tick round-trip and unchanged
  beat/export/source horizons. Use only `context-note-outside-window`,
  `duplicate-export-note-on`, `normalized-lifetime-dependent` and
  `unsupported-stem-locked-microtiming` as row block reasons. Reject target
  overlap/duplicate/cascade, window escape, negative/VLQ overflow and horizon
  changes. Never infer, snap, quantise, theory-repair or propagate timing.
  Fresh-create true effects are exactly `library_mutated`,
  `child_clip_created`, `correction_applied`, `note_onset_changed` and
  `note_timing_changed`; preview, replay and restart are all false. Keep prior
  schemas, hashes and recipes frozen and never mix correction kinds.
  For bounded note-end correction, choose **Change existing note length (MIDI
  Note Off)** and require explicit capability `note_end_shift_patch`,
  `maximum_note_end_delta_ticks: 480` and
  `minimum_note_duration_ticks: 1`. The isolated policy is
  `workbench_duration.py`, the retained operation is `shift_note_ends`, and
  the public schemas are
  `sunofriend.workbench-clip-note-end-window.v1`,
  `sunofriend.workbench-clip-note-end-preview.v1`,
  `sunofriend.workbench-clip-note-end-result.v1` and
  `sunofriend.workbench-clip-note-end-summary.v1`. Accept 1–64 unique exact
  existing pitched or drum refs with integer `target_end_tick` values. Require
  a non-zero delta within ±480, at least one tick of duration, and complete
  source and target intervals inside the loaded window. Focus and typing are
  zero-effect; require explicit Apply, Review, then Create. Keep Note On,
  pitch, attack/release velocity, articulation, note count and unaffected
  notes exact. In musical mode change duration beats by `delta / 480` and
  recompute source end through the tempo map. In stem-locked mode require zero
  microtiming, change source end at export BPM and derive duration beats.
  Require exact Note Off round-trip and unchanged beat/export/source horizons.
  Use the same four onset row block reasons; reject the next same-pitch onset,
  normalized lifetime cascade, window/MIDI escape and horizon movement. Never
  infer legato, phrasing, quantisation or musical correctness. Fresh-create
  true effects are exactly `library_mutated`, `child_clip_created`,
  `correction_applied`, `note_duration_changed` and `note_timing_changed`;
  preview, replay and restart are all false.
  Defer note insertion, release velocity, continuous
  expression, split/merge, quantise, hum/F0 guidance, repetition propagation
  and hybrids. Release velocity has no useful local non-zero golden and Note
  Off velocity support varies by GarageBand patch.
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
  `midi-ab-status --package-dir ORIGINAL_UNCHANGED_REVIEW_DIR --review FILE`
  to validate one explicit export without opening the answer key, or replace
  `--review FILE` with `--review-dir DIRECTORY` for a bounded, non-recursive
  search of browser-named exports. Status never reveals an assignment and is
  not the resolver's answer-key/source-input preflight. Then use
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
  `sunofriend midi-ab-status --package-dir
  ORIGINAL_UNCHANGED_REVIEW_DIR [--review REVIEWED.json | --review-dir
  DIRECTORY]` and
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
sunofriend tui "$INPUT"

sunofriend tui "$INPUT" \
  --mode studio \
  --candidate-root "$OUTPUT"

sunofriend tui "$INPUT" \
  --mode studio \
  --conversion-output "$FRESH_OUTPUT"

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
- The exact Kim Vocal 2 FP32/BF16 precision review is owner-only developer
  evidence, not a public Sunofriend command. The user heard the mixed source
  plus both anonymous candidates, exported a complete review and the verified
  resolver mapped the blind choice to `equivalent`; the developer did not open
  the answer key manually. This one-window result does not justify creating a
  roughly doubled FP32 MLX artifact. It also cannot enable or promote the BF16
  separator, change a default or justify a public route without the remaining
  cross-song MIDI and safety gates.
- The private vocal candidate inventory and its loopback audition are also
  owner-only developer evidence, not public Sunofriend commands. The audition
  requires the exact self-hashed inventory, MelRoFormer, vocal-leaf, phrase-
  completeness and authorised-excerpt reports plus one explicit one-line
  listening focus. It copies no media: a token-protected `127.0.0.1` server
  descriptor-opens and rehashes each existing source/reference WAV before
  serving it. Kim candidates use the mixed excerpt as reference; provider
  candidates use their exact vocal leaf. The candidate is a dry neutral MIDI
  render, not final instrumentation. Playback, seeking, looping and dwell are
  zero-write temporary state. Require explicit heard-reference and heard-
  candidate marks plus useful-for-focus, not-useful-for-focus or cannot-tell
  for every playable candidate; permit several useful candidates and never
  turn zero-note evidence into a choice. Only the browser export and separate
  exact verifier create evidence. A verified result remains focus-specific and
  cannot rank, select, merge, repair, promote, identify a singer or activate a
  source/Product/Studio/Simple route.
  A scoped audition may additionally bind one explicit 0.5–15 second window
  and an explicit non-empty subset of sealed candidate IDs. It must retain the
  complete inventory count, preserve canonical inventory order, disclose every
  omission and state that omission is neither rejection nor ranking. Reopen and
  rehash each included candidate's sealed note JSON, validate its note
  intervals and count only notes overlapping the explicit window. Report that
  scoped count beside the complete-excerpt count. A globally non-empty but
  locally silent candidate remains preserved yet unavailable for that scope;
  do not present its silent render as a listening choice. Playback starts and
  loops at the exact scope. Verification must reconstruct the same
  window and candidate subset; it cannot accept a wider, narrower or swapped
  browser export. Keep every omitted candidate unchanged in the sealed
  inventory and preserve all zero activation, selection, merge and singer-
  identity effects.
  When the private command explicitly uses `--classify-reference-line`, also
  require one separate human relationship for every playable reference:
  focus line, different line, mixed/overlapping lines or cannot tell. Keep that
  label separate from whether the MIDI is useful for the written focus. The
  label is focus-relative evidence only, not singer identity, sex, gender or
  demographics. Define the target by its musical job, such as principal lead,
  backing harmony or a named duet line. Do not substitute male/female or other
  demographic language for that musical role. Existing reviews without the
  flag retain their exact earlier shape.
- The latest authorised Kim Vocal 2 `Be Alone` worker observation binds the
  complete post-inference Python `sys.modules` closure for that exact run: 320
  modules, 277 independently reopened regular files, 18,067,782 aggregate
  bytes and zero unclassified modules. Its path-free closure evidence SHA-256
  is `1c071f0e3f5231280eade16949af9ed7c478751960c9b86061263cacbbe106c2`.
  A later authorised repeat also bound a bounded macOS kernel-Sandbox denial
  stream to the exact worker PID. It was ready before the worker, verified the
  final event count, observed the one deliberate outbound canary and zero other
  worker denials, then discarded raw records, PID and destinations. The exact
  6,730-byte worker was opened once without following links, hash-verified,
  rewound and executed through that same descriptor as Python standard input.
  Its worker-script pathname race is therefore closed for that observation.
  A model-free macOS canary then observed the exact inert-child PID and the
  python.org launcher's transition to its actual signed `Python.app` image. A
  later authorised `Be Alone` repeat attaches the same primitive to the exact
  model-worker PID. The final image's kernel CDHash matched the parent's strict
  static-code identity, `sandbox-exec` remained on a read-only filesystem, and
  provider, launcher and final-image full-file hashes were rechecked after
  completion. That v6 run retained 320 modules, 277 files, one deliberate
  denied outbound canary, zero other worker denials and one-LSB PCM24 additive
  closure. A separate model-free `libproc` canary now repeats byte-identically
  with two stable parent-owned snapshots of 13 file-backed executable mappings,
  all 13 files unchanged after exit and 12 strict signatures. A separate
  private v8 worker layer now pauses the exact Kim worker after inference and
  before quarantine through explicit bounded ready/release pipes, allowing the
  parent to attach the inventory without a guessed delay. Two fresh authorised
  runs repeated the same 33-file inventory with no unpathed executable region
  and 32 strict signatures; their GPU float-output hashes differed, so bitwise
  conversion parity remains false. A later model-free native canary matrix v2
  observes only FDs 0–2 at clean harness entry, an empty main-thread signal
  mask plus selected handler dispositions after CPython startup, and normal
  zero-status exact-reap termination for every fixed descriptor layout. Its
  matrix retains no raw PID, PGID or wait status. A later private live proof
  now binds equivalent facts to one exact deterministic transport-worker
  execution: self-hashed Result V2 carries the worker signal report, the native
  receipt binds normal zero exit and exact reap, and the self-hashed outer
  report observed only FDs 0–2 before Sunofriend imports or execution setup.
  It retains no PID or PGID and enables no product route. One later authorised
  Kim Vocal 2 run now binds its own outer FDs 0-2, expected post-CPython
  selected signal state, synchronous exact-child wait and normal exit 0 in a
  separate self-hashed v10 evidence layer. The post-CPython record still does
  not reconstruct the pre-exec signal instant, and native process-group and
  descendant supervision remain false. A still later model-free matrix v3
  proves the underlying native private-session owner against one deliberately
  surviving descendant: leader exit remains unreaped until a leader-only
  `libproc` census, group signal and exact reap complete. That owner is not
  integrated with the Kim path, so its real-worker flags remain false. The
  next validation-only contract fixes the required native terminal projection
  and rejects incomplete, lost, PID-bearing or unbound claims. It starts no
  worker and does not let the current subprocess route claim native ownership.
  A later model-free matrix v4 adds the first owner-bound observer: the opaque
  owner applies `proc_pidpath` and `csops` to its own exact live child and
  returns only a matched kernel CDHash and fixed state tag. Deliberately wrong
  path and CDHash values are rejected without changing ownership, after which
  the valid image and exact reap succeed. No PID, PGID or path is retained.
  A later model-free matrix v5 adds a factory-only single-use kernel-network
  broker. It starts the bounded log stream before spawn and submits each
  transient kernel-reported event PID to the opaque owner's boolean identity
  matcher; the owner exports no PID/PGID, and the result retains only counts.
  A fixed self-sandboxing worker produced one loopback denial, zero other owned
  denials, normal zero exit and exact reap; broker replay was rejected. A later
  model-free matrix v6 adds the owner-bound worker-ready executable-region
  primitive: a fixed worker emits a PID-free ready marker, the opaque owner
  supplies two stable snapshots without exporting PID/PGID, mapped files are
  remeasured after exact reap and final evidence retains no path. Model-free
  matrix v7 combines the three primitives around one fixed self-sandboxing
  worker and derives the terminal projection from that same opaque owner after
  normal zero exit, whole-group drain and exact reap. Its private result PID/
  PGID is consumed only through the owner's boolean matcher; the final report
  retains no process identifier, path or destination. No model, checkpoint or
  audio is opened. Model-free matrix v8 adds a fixed five-descriptor native
  entry point: data remain on 3/4/5 and the existing Kim ready/release pipes
  are mapped to 6/7. A stdlib-only worker emits a valid Kim readiness claim
  with dummy hashes, blocks through owner-bound process-image verification,
  accepts the exact release bytes, exits zero and is exact-reaped. This is
  still not Kim Vocal 2 execution. A pure follow-on contract now fixes the
  bounded canonical fd3 request and fd4 result frames. The request can contain
  private local paths but is not authority; it binds the exact Kim checkpoint,
  required observation policy, fresh nonce and descriptors 3–7. The result is
  path-free and carries PID/PGID only for the parent's opaque-owner boolean
  match. Model-free matrix v9 now exercises a fixed stdlib-only bootstrap under
  that owner. It hardens fd3–fd7 before its other imports, rejects a trailing
  request byte and tampered request self-hash before readiness, and consumes a
  valid fd3 request through the existing ready/release gate before emitting a
  parent-validated fd4 result. The parent submits the private PID/PGID to the
  opaque boolean matcher and discards them before retaining evidence. The
  bootstrap opens no request path, reads zero checkpoint bytes, imports no
  model, reads no audio and uses no network. It is not the real Kim worker, so
  native real-worker supervision is not claimed. Model-free matrix v10 adds a
  separate fixed native sandbox launch shape. The native boundary accepts only
  `/usr/bin/sandbox-exec`, builds the write allowlist around one validated
  staging tree and supplies a fixed offline environment. The same bootstrap
  then observes `EPERM` for deliberate loopback, `fork()` and outside-tree
  write canaries while fd3/fd4 validation, ready/release, opaque identity match,
  group drain and exact reap succeed. It still opens no checkpoint, model or
  audio and is not the real Kim worker. The audited bridge can now statically
  inspect and tensor-load the exact checkpoint through an inherited
  non-inheritable read-only descriptor without reopening its path. This fd5
  plumbing has synthetic unit evidence only. A private lease-to-start bridge
  now revalidates and cross-binds the reserved checkpoint, native request and
  fixed worker while holding the live lease lock, then passes that retained fd5
  only into the guarded start frame. It returns no descriptor and keeps the
  reservation active for later remeasurement and close. This bridge also has
  dependency-substituted evidence only: no accepted checkpoint, process, model
  or audio was opened. A fixed parent verifier now reopens the real worker's
  report-bound source, two PCM24 quarantine files, private closure claim and
  every claimed Python module, then repeats the mutable artifact checks. A
  separate one-use session transition accepts only normal zero exit, group
  drain, released ownership and exact reap from the exact retained opaque
  owner. Concrete observer, supervision, fd4/fd5, lease and terminal-receipt
  composition remains outstanding.
  The target parent lifecycle is now fixed by a second dependency-substituted
  exercise: prepare observers before spawn; capture ready state and release;
  drain fd4 while the owner is live; finish live observers; exact-reap the
  complete group; then remeasure and seal deferred observations and staging.
  This prevents waiting before a potentially blocking fd4 drain and prevents
  mutable mapped-file evidence from being finalized before reap. Seven
  adversarial cases prove ordering and cleanup only. A later fixed developer-
  only macOS adapter now applies that order to the real sandbox method and
  opaque native owner with the stdlib frame bootstrap: it prepares the kernel
  observer, binds ready/process-image/two stable executable-region snapshots,
  releases, drains bounded fd4, consumes the observer, exact-reaps, remeasures
  mapped files and verifies the three-entry staging tree. A wrong-CDHash case
  fails before release yet completes terminal cleanup. Its fd5 must be a small
  placeholder and checkpoint-sized inputs are rejected; no accepted
  checkpoint, model or audio was opened. A fixed private real-worker
  coordinator now composes the existing lease/start, live observers, bounded
  fd4 drain, exact reap, real staging verification and session/fd5/lease
  terminalization. Its initial tests substitute every effectful dependency,
  so they prove ordering and cleanup rather than live execution. The exact
  virtual-environment launcher is now preserved and repeatedly measured
  separately from the resolved process image; native `exec` receives the
  environment launcher and the staging verifier receives independently bound
  environment and base-runtime roots. This has portable and trusted-local
  static-session evidence only. Exact code-owned no-child starts and started
  owners that are completely drained and exactly reaped now have separate
  inert path-free receipts. Both preserve ordered safe cleanup stage codes
  without exception text; unproven start or incomplete reap has no receipt. A
  private one-shot wrapper now creates and removes the exact owner-only fd3/fd4
  transport files around that coordinator, including distinct writer/reader
  descriptions for one result inode. Its tests substitute the coordinator and
  do not open the checkpoint, model or audio. A dedicated private Kim lease now
  retains and rechecks the exact owner-only checkpoint descriptor against the
  canonical native request, author-hosted upstream evidence and descriptor-
  pinned Safetensors inspection. Its trusted-local static test opened and
  hashed the approved file but did not observe tensor values, import a model or
  read audio. This deliberately does not reuse the general lease's public
  bake-off acceptance authority. A single-use reservation now binds the exact
  observation and canonical request under the lease lock, remeasures before
  handoff, and passes fd5 only to an admission issued by the verified native
  session. The coordinator and one-shot wrapper no longer accept the general
  worker-V2 record. The complete private chain has since produced one clean
  authorised `Be Alone`
  v2 run. Its canonical path-free terminal receipt hashes to
  `950a20550278985381a32df9eb44c37e2b79204652be1fc739d2f306aa3535f7`;
  it records the fixed ready/release, live observer, exact group reap, staging
  verification, post-run checkpoint remeasurement, fd5 release, lease close
  and terminal session claims. Both 15-second outputs are 44.1 kHz stereo
  PCM24, and their integer sum is within one LSB of the authorised source.
  The attempt now also writes a path-free evidence envelope for those exact
  outputs. The unchanged downstream evaluator consumed it and produced the
  same byte-identical 14-note primary MIDI as both earlier Kim evaluations.
  The existing blind `Be Alone` Kim-versus-Moises review therefore already
  covers it and resolved to `equivalent`; no duplicate review was created.
  Treat this only as private execution and one-excerpt downstream-parity
  evidence. Fresh attempts now also emit a path/PID/timestamp-free monotonic
  timing receipt. The first timed repeat took 11.868113 seconds through output
  evidence, including 10.270401 seconds in the coarse native one-shot and
  1.175781 seconds opening the session; every other outer stage was below
  0.21 seconds. This is explicitly not a benchmark and does not split model
  inference from the one-shot's transport, observation, verification and
  cleanup. Cross-song execution and listening still precede any acceptance or
  integration decision, and no separator route is enabled.
  The disjoint `I am a Alien mashup` native repeat subsequently completed in
  11.299359 seconds and produced the same byte-identical 23-note primary MIDI
  as both earlier Kim runs for that excerpt. This clears only cross-song
  execution-to-MIDI reproducibility. Its existing blind review resolved to
  `neither` because the MIDI followed the female backing vocal rather than the
  intended male lead. Keep voice/line assignment as a quality blocker and do
  not activate Kim or infer singer identity from provider-control agreement.
  The
  evidence does not enumerate dyld
  shared-cache constituents, exclude all transient loads or prove mapped-memory
  bytes. None of these observations is full-file execution proof, dynamic-
  native-library closure, a packet monitor or a complete native-loader audit;
  the commands remain invoked by pathname and no product route is enabled.
- Both Kim-Vocal-2-versus-Moises MIDI reviews are complete. `Be Alone`
  resolved to `equivalent`; `I am a Alien mashup` resolved to `neither` because
  both candidates followed the female backing vocal rather than the male lead
  in the source reference. Treat this as a lead-versus-backing assignment
  quality failure, not permission to merge candidates or promote a separator.
  A later role-corrected private review of the exact 9.20–14.95 second window
  asked for the principal lead-vocal melody rather than a male voice. It marked
  Kim primary, Moises leaf 02, Suno A leaf 01 and Suno B leaf 01 as focus-line
  and useful, while Moises leaf 01 was a different line and not useful for that
  focus. Preserve the four useful alternatives and the different-line evidence;
  do not infer a winner, merge, singer identity, default or product route. The
  subsequent private geometry report found 16 exact-pitch onset matches in
  every pair at 80 ms, with 0 ms median onset error and at most 23.22 ms p95
  onset error. In this phrase the useful candidates are near-duplicates around
  one common melody backbone, so do not merge them in search of detail that
  the comparison did not find. A subsequent structured repeat asked separately
  about source line, focus-phrase completeness and MIDI usefulness. Its
  authoritative second pass marked Kim primary, both Moises lead adapters and
  Suno A leaf 01 substantially complete and useful, while Suno B leaf 01 was
  `cannot_tell` for all three questions. Moises leaf 01's reference remained a
  different line even though its MIDI was useful for the written focus. Treat
  the structured second pass as current coverage evidence, retain the first
  pass as superseded history and never infer one human label from another.
- The role-correct earlier-phrase repeat from 3.45 to 6.85 seconds is complete.
  Only Suno B leaf 01 was useful for the principal-lead focus, and the listener
  explicitly reported that it still misses notes. A fresh structured repeat
  confirmed it as `partially_complete`, not `substantially_complete`; none of
  the six candidates was substantially complete. Kim primary and Moises leaf
  01 had little or none of the focus line, while Kim lowest-line, Moises leaf
  02 and Suno A leaf 01 were partial but not useful for the exact focus. Treat
  Suno B as a useful partial candidate, not a winner, complete melody,
  automatic merge source, default or product route. The five other heard
  candidates remain preserved.
- `scripts/private-reviewed-vocal-geometry.py` is an owner-only diagnostic for
  two or more candidates already marked useful in one exact sealed review. It
  reconstructs that scope, verifies the note evidence and reports pairwise
  exact-pitch, chroma, onset, duration and timing observations. Pair order is
  review order, not preference. The report cannot select, merge, repair,
  activate or publish MIDI; agreement is not ground truth.
- `scripts/private-separation-evidence-index.py` creates a fresh owner-only,
  path-free integrity catalogue from at least four sealed private reports over
  at least two caller-declared track IDs and two method families. It verifies
  each report's exact file hash, document self-hash, private scope and inactive
  permissions, with a maximum of 256 entries. It copies no report body, audio,
  MIDI or path, and it does not normalize heterogeneous metrics, compare
  methods, rank a backend, accept a result or enable a product route. A
  catalogue is progress toward the cross-song corpus gate, not completion of
  that gate.
- `scripts/private-separation-corpus-coverage.py` verifies one exact evidence
  index and reports like-schema track/method cells, cross-song repeats,
  cross-method pairs and complete two-track/two-method rectangles. It reads no
  indexed report body and always keeps metric comparison false. A rectangle is
  topology evidence, not comparable quality data. The current six-entry index
  has two cross-song same-method groups, no same-schema cross-method pair and
  no complete rectangle. Licensing, human listening, hidden-set, offline and
  resource acceptance remain separate gates; the coverage report cannot rank,
  select, promote, activate or enable a product route.
- `scripts/private-separation-normalized-midi-agreement.py` recomputes one
  source-bound candidate/control MIDI metric across two or more songs. It
  verifies each candidate, control, role mapping and authorised excerpt chain,
  then preserves each song as a separate cell. Agreement with an estimated
  provider control is not score truth, melody accuracy or listening quality;
  never aggregate the cells into a winner or activate a separator from them.
- `scripts/private-separation-human-listening-coverage.py` binds completed
  focus-relative vocal review resolutions to those normalized song cells. It
  projects source-line classification and candidate usefulness separately,
  copies no listener notes and keeps usefulness distinct from completeness or
  accuracy. Private vocal auditions can opt into
  `--classify-focus-phrase-coverage`; this requires a separate structured label
  for substantially complete, partially complete, little/no focus line or
  cannot tell. The page title and exported filename identify this as a
  phrase-completeness review and include the exact millisecond window, so use
  that current export rather than a generic export from an older browser tab.
  The verifier, not the filename, authenticates the exact review seed. Do not
  infer that label from notes or usefulness. The current evidence covers three
  structured windows and 16 candidate auditions across both normalized songs.
  The complete 15-second `Be Alone` review found four focus-line candidates
  useful: Suno B leaf 01 was substantially complete, while Kim primary,
  Moises leaf 02 and Suno A leaf 01 were partial. Moises leaf 01 followed a
  different line and was not useful for the principal-lead focus. This clears
  only the bounded two-song cross-song listening-coverage item. Keep broader
  full-excerpt/full-song, hidden-set, licensing, offline and resource gates
  open, and do not select, merge or promote from these human labels.
- `scripts/private-separation-publication-readiness.py` verifies the exact
  normalized MIDI-agreement and human-listening coverage reports, requires the
  latter to be hash-bound to the former, and emits one owner-only path-free gate
  ledger. The current ledger passes three bounded milestones but leaves eight
  publication gates open, including separated-audio quality, full-song/broad
  role coverage, hidden-set, checkpoint terms, offline/resources and public
  product integration. Treat `publication_ready: false` as authoritative for
  this evidence scope. The command cannot accept a caller assertion, run a
  model, select a separator or enable Simple, Studio, CLI, TUI or source graph.
  Its optional `--separated-audio-quality` input accepts only the resolved v2
  blind result with the same complete track set and exact authorised-excerpt
  and role-mapping hashes as the normalized agreement. The predeclared minimum
  requires every Kim Vocal 2 excerpt to retain a substantially complete vocal
  with no severe bleed or artefacts. Provider preference is ignored. A weaker
  completed result leaves the gate open; a passing result closes only the
  bounded separated-audio gate and never selects or enables the separator.
  Its optional `--resource-benchmark-result` input accepts one complete
  controlled full-song result, verifies three to ten distinct serial
  repetitions plus their measurement, identity and machine-class contract,
  and records the development envelope without accepting it. The current
  36 GiB `Be Alone` result met its frozen development ceilings across three
  runs, but it cannot substitute for the separately required 16 GiB
  acceptance class. The resource gate, publication readiness and every
  product permission therefore remain open/false. A valid mixture of passing
  and failing repetition rows is retained as a failed aggregate threshold,
  not rejected merely because some individual runs passed.
  Its optional `--full-song-review-result` input accepts the verified resolved
  v1 complete-song and boundary review. The predeclared minimum requires all
  three complete generated roles to be useful and every role at every boundary
  to be clean. Listener notes are not copied and cannot affect the gate. The
  current `Be Alone` review verified exact duration and rated all three
  complete outputs useful, but vocals had audible joins at boundaries 11/12
  and the instrumental at 11/13. The duration/alignment gate therefore remains
  open. The review alone does not prove synchronized source-to-output alignment
  or accepted drift. Its optional `--full-song-alignment-result` accepts the
  separate self-hashed v1 timing result only when it is bound to the same
  stitch, plan, execution and clock. A matching review and alignment result can
  close only the duration/alignment milestone when both predeclared minima
  pass; neither can select or accept a separator.
  The optional `--full-song-join-remediation-review-result` input additionally
  requires a validated full-song review for the same exact raw stitch. It
  verifies that the original audible vocal/instrumental role-boundary set
  exactly matches the resolved remediation review units, then records it as
  supplementary directional A/B evidence. It does not
  replace any original boundary rating, alter the original clean-boundary
  counts or close the duration/alignment gate. A candidate-preferred answer is
  evidence of improvement relative to the raw stitch; an equivalent answer is
  not evidence that an originally audible join is now clean. In the current
  `Be Alone` result, improvement remains unevidenced for boundary 11 vocals and
  boundary 13 instrumental. The resulting v3 ledger target is
  `work/separation-bakeoff/separation-publication-readiness-v12/private-separation-publication-readiness.json`;
  it keeps `original_audible_joins_resolved`, publication readiness and every
  selection, acceptance and product-route permission false. Listener notes are
  not copied.
- `scripts/private-separated-audio-quality-review.py` creates a fresh
  owner-only blind review from two or more exact source-bound vocal-separation
  cases. Each case must bind one authorised mixed excerpt, one unchanged Kim
  Vocal 2 worker result and one provider broad-vocal control for the same
  window. The page keeps the source separate, sample-RMS matches only A and B,
  and requires independent vocal-retention, non-vocal-bleed and artefact
  ratings plus a separate preference. Use `--resolve REVIEWED_JSON
  --package-dir PACKAGE --out RESULT` after the browser export. Resolution
  verifies the immutable page, audio manifest and blind key and remains
  `complete_review_no_activation`; never infer acceptance from package
  creation or from one preferred candidate. The v2 result includes the exact
  path-free source-binding projection needed by the ledger but carries no new
  authority. The current two-song review is complete: Kim was preferred in
  both blind comparisons, but its `Be Alone` vocal was rated only partially
  complete while `I am a Alien mashup` was substantially complete. One of two
  cells therefore meets the predeclared minimum. Keep separated-audio quality
  open and do not turn preference into a default or model selection.
- When a completed separated-audio review names one exact missing vocal event,
  use `scripts/private-separated-vocal-focus-review.py` for a bounded challenger
  review instead of changing the quality threshold. Create mode requires one
  source-bound authorised excerpt, unchanged Kim evaluation, matching role map,
  one to five repeated `--provider` values, a 1–500 character `--focus` and a
  fresh `--out-dir`. It blinds and jointly sample-RMS matches Kim plus the
  provider broad-vocal estimates, keeps the mixed source unmodified and asks
  for independent focus retention, bleed, artefact and usefulness labels.
  Multiple candidates may be useful and there is no preference field. Resolve
  with `--resolve REVIEWED_JSON --package-dir PACKAGE --out RESULT`; the result
  is private diagnostic evidence only and cannot close publication readiness,
  choose a winner or enable a product route. The current `Be Alone` package at
  `work/separation-bakeoff/be-alone-held-vocal-focus-review-v1` compares Kim,
  Moises, Suno A and Suno B for the listener-reported extended robotic held
  note. Do not infer vocal retention from the preceding frame-activity
  disagreement; human listening remains required.
- For the private full-song duration/alignment precursor, use
  `scripts/private-separation-full-song-plan.py` with one authorised corpus,
  one exact track ID and a fresh output directory. It keeps the audited Kim
  worker at 661,500 frames/15 seconds, converts the complete source once to a
  canonical 44.1 kHz stereo clock and writes contiguous independently hashed
  chunk authorisations with no gap or overlap. It runs no model and cannot
  close duration/alignment, resources, quality, role, terms, offline or product
  gates. The current `Be Alone` plan has 11,578,896 frames in 18 equal
  643,272-frame chunks, zero end-clock error, plan file SHA-256
  `8eb63e00994482652059072d9c9f5ef034a1063478b2682e192723cd1004bc34`
  and document SHA-256
  `ee89785e095657c853427a6bc984248052cd1e28cf2e6893b294071ab5aca89d`.
  Resume the sealed plan with
  `scripts/private-separation-full-song-execute.py`. Run that coordinator under
  core `.venv` Python and pass `.venv-ai/bin/python` as the isolated worker's
  explicit `--runtime-launcher`; do not run the coordinator itself under the AI
  environment. The executor defaults to one next chunk and `--all` runs all
  remaining chunks. It preserves interrupted attempts and advances state only
  after the exact authorisation, checkpoint, terminal receipt, timing, role,
  hash and planned-frame checks pass. Then use
  `scripts/private-separation-full-song-stitch.py` to re-verify and concatenate
  the complete queue without crossfade, per-chunk gain or hidden repair.
  The current `Be Alone` execution completed all 18 chunks and the exact stitch
  produced 11,578,896-frame source, vocal, instrumental and reconstruction
  PCM24 WAVs. The current review page first presents all four complete-song
  tracks and then all 17 exact-boundary windows; both scopes must be rated.
  Use the fresh `be-alone-full-song-kim-stitch-v3-playable-review` package. The
  superseded `v2` page has an invalid JavaScript newline and therefore cannot
  render its audio controls; retain it only as defect evidence.
  The v3 review is complete and resolved. Vocals, instrumental and
  reconstruction were all rated useful. Reconstruction was clean at all 17
  joins; vocals had audible joins at 11/12 and the instrumental at 11/13. The
  result keeps full-song quality acceptance, separator selection, publication
  and every product route false. That full-song page is complete; the later
  targeted v2 join review documented below is also complete and passed, and
  older packages are superseded evidence.
  `scripts/private-separation-full-song-alignment.py` now measures the exact
  source against the diagnostic reconstruction in nine early-to-late windows.
  It uses gain-normalized log spectral-band timing features, searches only the
  declared plus/minus 100 ms interval and requires all windows active, no more
  than 20 ms absolute lag, no more than 20 ms lag spread and at least 0.90
  normalized correlation in every window. The current `Be Alone` result passed
  with nine eligible windows, 0 ms maximum lag, 0 ms spread and 1.0 minimum
  correlation. This is source-clock synchronization evidence only, not stem
  fidelity, bleed, artefact, musical-quality or separator-accuracy evidence.
  The human-reviewed vocal and instrumental joins still keep the combined
  duration/alignment milestone open.
  `scripts/private-separation-full-song-join-remediation-plan.py` verifies that
  exact stitch, resolved review and passing alignment result before proposing
  any repair. It derives targets only from explicit `audible_join` ratings,
  rejects an unexplained reconstruction join, copies no listener notes and
  writes no audio. The current `Be Alone` plan reduces four role defects to
  three unique 15-second source-clock worker windows: boundary 11 targets both
  vocals and instrumental, boundary 12 targets vocals, and boundary 13 targets
  instrumental. Each future candidate may patch only the named role for two
  seconds around the join with 100 ms equal-power transitions, while retaining
  the raw stitch as the unchanged control. Source windows may overlap; patch
  regions may not. Planning is not execution or repair success.
  `scripts/private-separation-full-song-join-remediation-execute.py` now
  resumes those sealed windows through the existing audited native worker,
  preserves incomplete attempts and creates candidates only after every
  authorisation and worker result verifies. The current execution completed
  all three windows. It created separate PCM24 vocals and instrumental
  candidates that are exact outside their four named patch regions, plus a
  diagnostic reconstruction. Role peaks remained below full scale and the
  reconstruction required no global attenuation. Raw stitch hashes remained
  unchanged. This is candidate integrity, not repair success.
  Use `scripts/private-separation-full-song-join-remediation-review.py` to
  create the fresh blind page. The current package has four raw-versus-
  candidate boundary-role pairs, all eight patch-edge pairs and three
  complete-song pairs. Short pairs use attenuation-only whole-window sample-
  RMS matching; complete songs remain unchanged. Do not open the separate
  answer key before review. Make the browser export owner-only with
  `chmod 600 REVIEWED`, then use
  `scripts/private-separation-full-song-join-remediation-review-result.py
  --status REVIEWED --review-package-dir REVIEW_PACKAGE --execution-dir
  EXECUTION --stitch-package-dir STITCH` first. Status re-verifies the public
  seed, unchanged execution/candidate/stitch evidence and all 30 audio
  references without reading the key or revealing A/B. For a v1 package it
  reconstructs the exact question, unit kinds, titles, focus text, windows and
  unordered raw/candidate PCM24 pairs from that evidence; it also rejects a
  browser export larger than 8 MiB before parsing. Seed, reviewed export and
  answer key are each read once through a bounded non-following descriptor;
  the exact parsed bytes supply the stored digest. Only after status succeeds,
  repeat the same explicit roots with `--resolve REVIEWED --out FRESH`.
  Resolution repeats the public checks before opening the sealed key, verifies
  its A/B identities and level facts against the audio, fsyncs a hidden private
  temporary file and hard-links the complete inode to the fresh name without
  overwriting an existing path. The self-hashed result is
  `complete_review_no_activation`. Terminal
  output is summary-only and does not print private per-unit notes. It maps the
  explicit choices but keeps join elimination unproven, every permission and
  effect false, separator selection/acceptance false and publication false. A
  separate readiness reassessment must interpret the result. No readiness,
  selection, acceptance or product route changes merely because the page was
  exported or resolved. The current review is complete: candidate remediation
  was preferred for two of four boundary-role pairs and equivalent for two,
  preferred for one of eight patch edges and equivalent for seven, and
  preferred for one of three complete-song roles and equivalent for two. No
  unit preferred raw, neither or cannot-tell. Because two originally audible
  joins were only equivalent rather than candidate-preferred, the resolved
  result keeps `original_audible_joins_resolved: false`; the combined
  duration/alignment milestone and every product/publication gate remain open.
  That v1 page has no remaining action; the targeted v2 page documented below
  is the current outstanding human review.
  The next bounded artifact is the v2 plan produced by
  `scripts/private-separation-full-song-join-remediation-plan-v2.py`. Bind the
  exact v3 stitch package, full-song review result, v1 plan, v1 execution and
  candidate reports, strengthened v4 resolved join review and readiness-v12
  ledger, then write the fixed
  `private-separation-full-song-join-remediation-plan-v2.json` name into a
  fresh owner-only directory. The current file SHA-256 is
  `dfdff09fbd7b6b79701f96075004493ba4726bf950a62b2425f031c030ef29c6`;
  its document SHA-256 is
  `3ca4ce793b569e3c0032051e90767796bf4147bafa658c5563ee94863a671a90`.
  It derives only boundary 11 vocals and boundary 13 instrumental from the two
  human-equivalent v1 outcomes, while preserving the candidate-preferred
  boundary 11 instrumental and boundary 12 vocals repairs. It starts from the
  verified v1 candidate and reuses worker-local `[242550, 418950)` for each
  target. The only signal-processing delta is widening each patch from one to
  two seconds per side; 100 ms equal-power edges and 15-second source windows
  remain unchanged. It runs zero models, writes no audio, selects nothing and
  closes no gate. A targeted v2 page now exists and its human review is
  outstanding. It requires two blind v1-versus-v2 comparisons with
  independent absolute cleanliness ratings and four v2 patch-edge checks.
  Never transfer v1 review or alignment decisions to the new candidate.
  Assemble that candidate with
  `scripts/private-separation-full-song-join-remediation-execute-v2.py`, the
  exact v2 plan and the same bound stitch/review/v1/readiness evidence chain,
  into a fresh `be-alone-full-song-join-remediation-execution-v2` root. The
  fixed completion marker is
  `private-separation-full-song-join-remediation-execution-v2.json`; its current
  file SHA-256 is
  `a4f4231f70fdac4991243b31c87b7efbb0503d547cd6e3731e4dd13ac3ef1bce`
  and document SHA-256 is
  `ba25d98198f47d8e957020efd69656442d290652a0ac43b25243c608e7aad906`.
  The model-free executor starts from verified v1 candidate PCM24 audio,
  repatches vocals `[6987792, 7164192)` and instrumental
  `[8274336, 8450736)` from worker-local `[242550, 418950)`, preserves exact
  v1 PCM24 samples everywhere else and reconstructs from the written role
  WAVs. It invokes no model or network, publishes fresh private outputs without
  overwrite and writes its report only after final input/output verification.
  This proves assembly integrity only. Selection, acceptance, readiness and
  publication remain false; the targeted two-pair/four-edge review and any
  later fresh full-song review/alignment are still mandatory.
  Generate the targeted package only under a fresh output directory whose
  existing parent is owner-only:

  ```bash
  PYTHONPATH=src ./.venv/bin/python \
    scripts/private-separation-full-song-join-remediation-review-v2.py \
    work/separation-bakeoff/be-alone-full-song-join-remediation-execution-v2 \
    --v2-plan \
      work/separation-bakeoff/be-alone-full-song-join-remediation-plan-v2/private-separation-full-song-join-remediation-plan-v2.json \
    --v1-execution-dir \
      work/separation-bakeoff/be-alone-full-song-join-remediation-execution-v1 \
    --full-song-review-result \
      work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-review-result-v1/private-separation-full-song-review-result.json \
    --v1-plan \
      work/separation-bakeoff/be-alone-full-song-join-remediation-plan-v1/private-separation-full-song-join-remediation-plan.json \
    --resolved-join-review-result \
      work/separation-bakeoff/be-alone-full-song-join-remediation-review-result-v4/private-separation-full-song-join-remediation-review-result.json \
    --publication-readiness \
      work/separation-bakeoff/separation-publication-readiness-v12/private-separation-publication-readiness.json \
    --package-dir \
      work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-playable-review \
    --out-dir \
      work/separation-bakeoff/be-alone-full-song-join-remediation-review-v2
  ```

  Open
  `work/separation-bakeoff/be-alone-full-song-join-remediation-review-v2/join_remediation_review_v2.html`.
  It contains exactly two blind boundary comparisons and four single-player
  v2 edge checks: six units and eight audio references. Each boundary requires
  heard A/B, an independent `clean`, `audible_join` or `cannot_tell` rating for
  A and B, and a relative `A`, `B`, `equivalent`, `neither` or `cannot_tell`
  choice. Each edge requires heard plus the same absolute cleanliness rating.
  Boundary pairs use attenuation-only sample-RMS matching; edge audio is exact
  v2 PCM24. The public report/page hide identities behind opaque commitments;
  the answer key is sealed.

  The report file/document SHA-256 values are respectively
  `e646043606b75c884fadc2bc22591868db72089f93b06b6d6db7f45d20befe1b` and
  `0d691805f4f8ecfda3e57f26a1f9b87f3d12858dd26f2ba156b79cd82a1b423a`.
  The HTML SHA-256 is
  `5b460af9293cc5825298f66df36a55f284a7ae93033dff9151fd11ab977e9fa2`.
  The sealed answer-key file/document SHA-256 values are respectively
  `e17a034eb7a220957952ad3657772c31918be4d1d54dd09ba10593fa547fb47c` and
  `6848541cc0b634937debf04397650dabe19e72c299065cd72e62c3b3d6a4f4f7`.
  The package commitment is
  `2bc140793f4b483b1aa3e9db8f619174aa564736dee726c09ad9fa2898f2974a`.
  After the listener exports `join_remediation_review_v2.reviewed.json`, make
  that file owner-only with `chmod 600 REVIEWED`. Use
  `scripts/private-separation-full-song-join-remediation-review-result-v2.py
  --status REVIEWED` first, with the exact unchanged `--review-package-dir`,
  `--v2-execution-dir`, `--v2-plan`, `--v1-execution-dir`, `--package-dir`,
  `--full-song-review-result`, `--v1-plan`,
  `--resolved-join-review-result` and `--publication-readiness` inputs used by
  the package. Status reconstructs all six units and eight PCM24 references,
  verifies the opaque source binding and leaves the key unopened. Only after
  status succeeds, repeat those inputs with `--resolve REVIEWED --out FRESH`.
  Resolution opens the sealed key, verifies its A/B identities and level facts
  against the audio and writes a fresh owner-only no-overwrite result. It keeps
  absolute cleanliness separate from comparative preference. A targeted pass
  requires both v2 target-boundary identities and all four v2 patch edges to
  be `clean`. Even then, `original_audible_joins_resolved`, selection,
  acceptance, readiness and publication remain false; the pass permits only
  later fresh candidate-bound full-song and alignment reviews. Keep every
  evidence tree quiescent because JSON and WAV descriptors are not held as one
  atomic snapshot across the whole operation.
  This review is complete and passed: both v1 and v2 were clean at both target
  joins and equivalent, and all four v2 patch edges were clean. Its resolved
  result permits only fresh candidate-bound three-role, 17-boundary full-song
  review and fresh nine-window alignment; it selects and accepts nothing,
  changes no readiness state and enables no product or publication route.
  The full-song package builder for that later gate has now run as
  `scripts/private-separation-candidate-full-song-review.py` from the exact
  passing v2 result. It re-verified the complete evidence chain and copied the
  unchanged source and exact v2 candidate roles into
  `work/separation-bakeoff/be-alone-v2-candidate-full-song-review-v1` with all
  17 original boundary windows. The current human review page is
  `BOUNDARY-REVIEW/separation_boundary_review.html`. It runs no model and
  selects, accepts, activates and publishes nothing. Never invent or hand-edit
  a passing result.
  After that page is genuinely completed, make the exported
  `separation-boundary-and-full-song.reviewed.json` owner-only and use
  `scripts/private-separation-candidate-full-song-review-result.py --status`
  with the exact builder evidence roots first. Repeat with `--resolve` and a
  fresh `--out` only after status succeeds. The resolver re-verifies the v2
  pass, copied full-song audio, immutable seed, 17 boundary units and every
  referenced clip. It records but does not reinterpret the listener's three
  full-song and 51 role-boundary ratings. Resolution selects and accepts
  nothing and keeps alignment, original-join resolution, readiness and
  publication false.
  That candidate-bound review is now complete and resolved. All three
  complete-song roles were useful and reconstruction was clean at all 17
  boundaries. Vocals had audible joins at boundaries 7, 8, 9, 10 and 17;
  instrumental had audible joins at boundaries 4, 7, 8, 10 and 12. Preserve
  those explicit ratings even though the complete reconstruction and automatic
  alignment passed; do not reinterpret one evidence type from another.
  The separate fresh alignment command
  `scripts/private-separation-candidate-full-song-alignment.py` has also run
  from the exact passing v2 result and complete evidence chain. All nine fixed
  early/middle/late windows were eligible, maximum lag and lag spread were 0
  ms, minimum correlation was 0.998685 and the gate passed. This automatic
  source-clock result is not a listening review and remains evidence only:
  selection, acceptance, full-song review, original-join resolution, readiness
  and publication stay false.
  After all three exact results exist, use
  `scripts/private-separation-candidate-readiness-reassessment.py` with
  `--v2-review-result`, `--candidate-review-result`,
  `--candidate-alignment-result`, the same complete v1/v2 evidence chain and a
  fresh owner-only `--out`. It verifies cross-result identity, derives the
  full-song cleanliness/usefulness claims again and reconstructs the fixed
  nine-window alignment summary. Passing prerequisites only makes a separate
  final human-acceptance review eligible. The reassessment does not add
  listening evidence and keeps original-join resolution, selection,
  acceptance, product activation and publication false.
  The current reassessment is complete and records
  `technical_and_listening_prerequisites_met: false` and
  `final_human_acceptance_review_eligible: false` because ten role-boundary
  ratings remain audible. Its next action is
  `remediate_failed_candidate_evidence`.
  The fresh bounded plan has now been derived with
  `scripts/private-separation-candidate-join-remediation-plan.py` and sealed at
  `work/separation-bakeoff/be-alone-v2-candidate-followup-remediation-plan-v1/private-separation-candidate-join-remediation-plan.json`.
  It maps the ten explicit audible role joins onto seven unique 15-second
  source windows, proposes seven future independent model calls and requires
  twenty future patch-edge checks. All ten role-boundary findings are outside
  the earlier v2 patch targets. Treat them as current human evidence, not as
  proof that v2 caused a regression. The planning step runs no model, creates
  no audio, copies no private review notes and cannot select or accept a
  separator.
  The matching owner-only executor is
  `scripts/private-separation-candidate-join-remediation-execute.py`. It must
  receive that exact plan plus the unchanged candidate review, alignment,
  reassessment and complete v1/v2 evidence roots. It re-derives every binding,
  runs only missing 15-second Kim worker windows, stops the reused worker
  executor before its old candidate builder, starts candidate assembly from
  exact v2 PCM24, patches only the named four-second role regions and publishes
  the candidate directory atomically. An exact rerun must report
  `windows_executed_this_invocation: 0`.
  The completed private run at
  `work/separation-bakeoff/be-alone-v2-candidate-followup-remediation-execution-v1`
  verified seven workers, ten role patches, unchanged v2 hashes and exact v2
  PCM24 outside every target. Its candidate report file/document SHA-256 values
  are
  `8dda4e13569db363378412c4c564b7bde36183eda90bb2a5f3c349832043ab21`
  and
  `e89fa4a26610e123bc34df8cc84574834caf7c4998157128d7259f59070d7a43`.
  This is not a listening result. The next owner-only builder is
  `scripts/private-separation-candidate-join-remediation-review.py`. It binds
  that exact execution and the immutable v2 control, randomises A/B separately
  for each unit and writes 10 targeted boundary pairs, 20 patch-edge pairs and
  three complete-song pairs. Short comparisons attenuate only the louder file
  to the quieter whole-window RMS. A patch edge below the audibility floor
  expands through fixed centred 2/4/6/8-second options and uses the first
  window where both versions are audible; the current two quiet vocal ends use
  six seconds. The completed unreviewed package is
  `work/separation-bakeoff/be-alone-v2-candidate-followup-remediation-review-v1`.
  Its report file/document SHA-256 values are
  `b35443e8fba1bb93a404467b058d4e7e9ef6c6404906bd899a5d05eeda202e45`
  and
  `4d39c7d15f6d3ebb33aa8ed2e660e39097c67ca7c380150f26733b1e94f8142c`.
  Open its `join_remediation_review.html`, hear and classify every A/B pair,
  and export only after all 33 units are complete. Do not inspect the separate
  sealed answer key first. This page does not select, accept or activate a
  separator. A separate resolver, fresh candidate-bound all-17-boundary review
  and fresh alignment are still required before reassessing readiness.
  On macOS 26.5.1, an exact sealed/read-only `/usr/bin/sandbox-exec`
  `CSSMERR_TP_NOT_TRUSTED` result is recorded as
  `sealed_read_only_system_provider_cdhash_trust_unavailable` with
  `strict_code_signature_valid: false`; never report it as strict validation.
  The runtime launcher and observed process image still require strict validity
  and matching static/kernel CDHashes. Use a private ignored Python 3.12 virtual
  environment backed by a valid local runtime rather than changing the system
  Python. The current review page is unreviewed; selection, acceptance,
  readiness and every product/publication permission remain false.
  Keep the execution, candidate and stitch trees quiescent during status and
  resolution. Their JSON and WAV descriptors are not held as one atomic
  snapshot across the whole operation; status and result record this explicit
  limitation.
  Never call exact input partitioning or exact output duration seamless or
  accepted separation.
  Fresh native attempts now retain two path-free resource projections inside
  the terminal receipt. The worker projection carries device, input frames,
  chunk count, model-call duration and peak MLX allocator bytes. The native
  owner separately captures Darwin `wait4` peak RSS and `proc_pid_rusage` V6
  lifetime physical/neural footprints only after exact reap and retains no
  PID. Each projection is self-hashed and request/result-bound. The full-song
  observer may call a field complete only when every selected attempt has its
  matching projection. Existing attempts remain valid but cannot be backfilled.
  Keep allocator, RSS and physical-footprint meanings separate.
  Before any controlled repeats, use
  `scripts/private-separation-full-song-resource-benchmark-plan.py` to bind one
  exact sealed full-song plan, the exact checkpoint and resolved runtime
  executable, the locally probed Mac class, three to ten fresh serial runs and
  fixed resource ceilings. The plan probes with bounded local commands, starts
  no model, contains no paths and rechecks runtime/checkpoint identities after
  probing. Its required measurements are parent full-song wall time, worker
  model-call time, peak process RSS, peak MLX allocator bytes, peak total
  unified memory, thermal state before/after and timeout/OOM outcome. All
  repeat slots begin `not_run`; the document is not a benchmark result and
  cannot accept or enable anything. A development Mac with more memory does
  not substitute for the separately required 16 GiB acceptance class.
  Run exactly one fresh slot per process with
  `scripts/private-separation-full-song-resource-benchmark-run.py`; use a new
  owner-only output root for each slot and preserve failed roots rather than
  reusing them. The runner re-verifies plan/runtime/checkpoint/machine identity,
  captures thermal state before and after, and records the complete
  execute/stitch/resource wall interval. After every frozen slot succeeds, pass
  every exact report to
  `scripts/private-separation-full-song-resource-benchmark-result.py`. The
  verifier rejects missing or duplicate slots, nonce reuse, overlap, identity
  drift, incomplete measurements and non-recomputable thresholds. A complete
  result may describe the 36 GiB development machine but must keep resource
  acceptance and all product/publication permissions false until the separate
  16 GiB acceptance-class run also exists. Do not manually fill slots or infer
  acceptance from the older coarse report.
  The completed `Be Alone` development run used three distinct, serial roots;
  one earlier pre-inference launcher-boundary failure is preserved separately.
  The three verified whole-pipeline times were 172.561330–173.454702 seconds,
  maximum wall time was 39.637729 seconds per audio minute, maximum peak RSS
  was 1,141,309,440 bytes, maximum MLX allocator peak was 2,324,039,502 bytes,
  and maximum Darwin physical footprint was 4,093,199,920 bytes (3.812089
  GiB). Thermal state remained nominal before and after every repetition; no
  timeout or OOM was observed. The result file SHA-256 is
  `9a2541d16009de4173076db0e3771026ae34167f4cdaf4c2a30c6957fbcbb7cf`
  and document SHA-256 is
  `a56216ca88fd4795e802d0b4ae01f5104d1dc60338373f33482b3c4ed3769ec9`.
  Development thresholds passed, but the 36 GiB machine does not satisfy the
  16 GiB acceptance-class gate; acceptance/publication remain false.
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
   or manufacturing a reviewed export. For `midi-ab-status`, report the
   unchanged package commitment and question, bounded candidate/match counts,
   matching reviewed-export hashes, and that the operation did not read the
   answer key, reveal A/B, infer a choice or complete resolver preflight. For
   `midi-ab-resolve`, require a
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
    previews matched `role-neutral-general-midi-v3`, the current SoundFont and
    disclosed role program; for bass report **GM 39 Synth Bass 1 proxy**.
    Require decoded-loop policy
    `recorded-zero-source-frame-window-level-matched-v2` and report each
    source/candidate's measured gated RMS, signed applied gain, any peak-room
    limit and `common-target-active-block-rms-v1` receipt. State that the gain
    exists only in the browser transport, with source/preview/MIDI bytes
    unchanged, and that this comparison is not blind. Confirm owner-only
    verified renderer/decode snapshots were deleted before publication. Report any
    `silence_padded_frames` as generated end silence, not missing transcription,
    plus the 2 GiB all-input (source, candidate MIDI, SoundFont and preview)
    bound with early pre-render rejection, the 64 MiB output bound and the
    32-entry/256 MiB rebuildable-cache policy. If an old loop was evicted,
    prepare it again
    without treating eviction as lost project work. If the compatibility
    fallback was needed, describe it as second-synchronised, not
    sample-accurate, and feedback/event-free.
    For a Stage 4 fixed-MIDI instrument review, require one active selected
    bass or keys lane and report the exact arrangement-selection and MIDI
    hashes, source reference window, verified SoundFont, dry renderer and
    server-owned pair: zero-based GM Synth Bass 1/2 programmes 38/39 or
    Electric Piano 1/2 programmes 4/5. Confirm both anonymous renders contain
    the identical note timing, duration, pitch and velocity performance and
    that the selected MIDI bytes remain unchanged. Require unambiguous GM bank
    zero, an effective target Program Change before every playable Note On
    including raw same-tick order, and non-zero effective CC7 volume and CC11
    expression. Report the 64 MiB/20-minute MIDI, 2 GiB source, 2 GiB
    SoundFont, 256 MiB renderer and 3 GiB aggregate preparation limits, plus
    exact-window-only source snapshotting.
    For bass require coverage status `not_required`. For keys require a private
    probe zone for every occupied channel, pitch and soft 1–42, medium 43–84
    or strong 85–127 velocity bucket, testing the minimum velocity actually
    observed there. Require CC120/CC123 guards around 0.20-second notes in
    0.35-second slots, at most 512 zones and 180 seconds. Before allowing A/B,
    both hidden identities must pass at least −72 dBFS RMS, −60 dBFS peak,
    3 dB active RMS above the pre-note guard and no more than a 24 dB
    velocity-normalised deficit from the channel/bucket median when peers
    exist. Reject playable keys notes on General MIDI channel 10 (zero-based
    channel 9). The synthetic MIDI must remain private and rebuildable. Raw
    probe audio must be deleted after measurement and remain reproducible from
    verified inputs; the loopback browser response must be blind and path-free.
    Confirm the source and both candidates are
    attenuated to the quietest fixed-window RMS with no boost, reject more than
    18 dB divergence, and apply one common attenuation-only −1 dBFS sample-peak
    guard with no limiter or compressor. Require all three source/A/B heard
    marks before accepting A, B, equivalent, neither usable or cannot tell;
    reveal the programme mapping only through the separate resolved result.
    State that preparation/playback are feedback-free and that
    completion/resolution affect only the owner-only instrument-review ledger,
    never MIDI decisions, roles, defaults, mixes, product readiness or
    GarageBand Pack membership, ranking or export.
    Always report `quality_status: review_required`. Do not call a functional
    pass pitch/octave correctness, every-velocity audibility, chord/polyphonic
    clarity, tone consistency or source similarity, GarageBand equivalence,
    or evidence for a winner, recommendation or default. Do not call either
    proxy a detected GarageBand patch or automatically apply the preference.
    For a precise decoded arrangement
    loop, report its context-neutral manifest hash, deduplicated source and
    distinct selected-MIDI counts, 24-track maximum, exact canonical group
    membership, pre/post-render stale-selection check and atomic one-clock
    switching. State that it is unity-gain, unlevelled/unlimited, recorded-zero
    and feedback-free. Do not imply that its four canonical presets make the
    coarse full-song/custom mixer sample-accurate.
    For the MIDI-derived song-interpretation WAV, report its
    selection-manifest hash, `source-referenced-summed-group-balance-v3`
    policy, lane count, source/preview/SoundFont verification, actual
    same-source waveform-sum calibration, every exact GarageBand Pack MIDI
    member/index and suggested track trim, time-aligned drum-bus guard and final
    output gain. Report −18 dBFS as median active-block audition
    normalisation and −1 dBFS as a sample-peak ceiling, never LUFS or true peak.
    Confirm PCM24 output has zero full-scale samples; compression, limiter, EQ,
    saturation, reverb, chorus and widening are false; `mastered` is false; and
    all source/MIDI/selection/feedback/event/ranking/default effects are false.
    Require the path-free provenance receipt to pin project/selection/BPM,
    every project source and selected lane, renderer/SoundFont, per-lane/output
    horizons, WAV/recipe hashes and the complete mix report. State that the dry
    unity control is unchanged and that the WAV/receipt/fader recipe are
    Workbench-only, not yet in the CLI or GarageBand Pack. Do not
    infer musical preference from trims or call the result final mastering.
    If a listening master was explicitly requested through the standalone
    command, Workbench action or native TUI **Master** tab, separately report its
    source/output/report hashes, fixed mastering policy, input/output
    integrated LUFS, output dBTP, normalization type and exact unchanged frame
    horizon. Call it a listening-master challenger with
    `release_master: false`; retain and name the original balanced WAV as the
    control. For Workbench or TUI, additionally confirm the selection and
    balanced manifest hashes were current, the receipt and PCM24 WAV are
    available through the local Workbench, and
    feedback/event/preference/selection/default/pack effects were false. For a
    TUI cache miss, report the SoundFile/FFmpeg/`loudnorm` preflight; for a
    cache hit, state that verified content-addressed reuse needed no fresh
    preflight. Do not imply that the optional challenger completes a required
    product output or that creating it is a listening preference.
    If the user explicitly completed the Workbench blind master review, report
    the exact window, attenuation-only RMS policy, both heard confirmations,
    blind outcome, bounded tags and whether private notes were recorded. Keep
    candidate identity hidden until the separate resolution exists. For a
    resolved review, report the auditable nonce/commitment mapping and resolved
    outcome, while stating that feedback/resolution changed no MIDI, selection,
    ranking, default, product completion, audio artifact or Pack state and did
    not promote a winner.
    For long-song visualization,
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
    Confirm the current Pack Composer v1 did not silently include a balanced
    audition WAV, report or fader recipe; those remain separate explicit
    Workbench downloads.
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
    For Phase 6 Increment 6.2a, confirm the transform flag is absent by default,
    requires the complete 6.0 gate and is mutually exclusive with reuse-plan
    mode. Confirm a projection adds no object/row and all effects are false.
    Report the exact parent Clip/object/library pins, operation, projection
    hash, before/after key/BPM/timing/duration/pitch facts and warnings. For a
    create, report the child Clip/object/lineage/revision and the before/after
    library states. For a fresh-created result, confirm the only true effects
    are library append, child creation and transform applied to that child. For
    an exact idempotent replay, confirm the existing child is returned, no row
    is appended and every effect is false. On stale evidence confirm
    one detail reload and no write retry. State explicitly whether BPM was
    musical or stem-locked and what that means for source-audio alignment.
    Treat the new child as an alternative, not a selection or winner; restart
    in reuse-plan mode before placing it.
    The completion golden used a copied accepted Lidl library: a 171-note
    B-major bass at about 119 BPM became a musical 125 BPM child and then a
    +1-semitone C-major child; all three versions survived restart, exact
    retries had zero effects, original rows/objects remained unchanged and the
    full suite passed with 910 tests.
    For Phase 6 Increment 6.3a, confirm correction mode is absent by default,
    requires the complete 6.0 gate and cannot be combined with reuse or
    transform mode. Confirm the loaded window uses half-open integer 480-TPQ
    ticks, stays within all beat/seconds/note/chord bounds and returns no paths.
    Report exact parent/object/library/window pins and duplicate-safe note refs.
    Confirm nothing is preselected and every canonical pitch change is a
    user-authored integer 0–127, within ±24 semitones, unique and editable.
    Projection must add no row/object and have all effects false. Fresh create
    must add exactly one deterministic child and set only the library/child/
    correction/pitch effects; replay must add nothing and have every effect
    false. Confirm restart re-derives the same bounded summary from the exact
    parent and recognized recipe. Verify timing, duration, source seconds,
    microtiming, expression, key/chords, instrument, provenance, unaffected
    notes, decisions, arrangement, proposal and pack are unchanged, and a new
    same-pitch overlap/collapse is rejected. On conflict confirm one reload and
    no POST retry. The completed Lidl copy exercise used a 1,727-note keys
    parent, exposed 22 editable notes, appended one explicit 59-to-61 child,
    replayed with zero effects, restored the same diff after restart and
    repeated deterministic MIDI at SHA-256
    `ce1edbc85f44b5c37cdb0576c89ef5cd2eee74afe7c9ee6f904ca248f866d4a8`;
    the complete suite passed with 943 tests.
    For Phase 6 Increment 6.3b, additionally confirm one exact
    `attack_velocity_patch`, targets 1–127, drum eligibility and blocked
    duplicate exported Note On groups. Projection is zero-effect; fresh create
    sets only library/child/correction/attack-velocity effects; replay is all
    false. Restart must recover the exact before/after velocity diff while
    pitch, timing, duration, release velocity and normalized MIDI topology stay
    unchanged. MIDI velocity is not a dB or preference claim. The completion
    golden used a copied Lidl Snare Clip, changed one channel-9 pitch-38 Note
    On from 101 to 89, retained exact source/parent bytes, replayed with zero
    effects and repeated deterministic MIDI at SHA-256
    `f8570c9af8636e3cfeb1605082616a3e1e72f0bdd546b764baf055bca9abbc4c`.
    Confirm the browser rejects a mismatched schema, pin, correction, diff,
    child identity or effect map; it must never synthesize absent server diff
    rows. Reapplying an unchanged draft/source value must preserve any valid
    projection and make no request or correction-state change.
    For completed Phase 6 Increment 6.3c, confirm the capability explicitly
    advertises `note_delete_patch` before using it. Require operation
    `delete_clip_notes`, 1–64 exact refs, pitched/drum eligibility and at least
    one survivor. Confirm focus alone is zero-effect and the explicit sequence
    is Mark, Review, Create. Projection is zero-effect; fresh create sets only
    `library_mutated`, `child_clip_created`, `correction_applied`,
    `note_count_changed` and `note_deleted`; replay and restart are zero-effect.
    Recompute normalized parent/child MIDI and require exactly the named
    intervals to disappear, every survivor and beat/export/source horizon to
    remain exact, and duplicate/cascade/horizon/only-note attempts to be
    blocked. Confirm pitch and velocity v1 are unchanged and there is no noise
    judgement, draft audition, ranking, selection, placement or export.
    The completion exercise used a fresh copy of the accepted 12-Clip Lidl
    library at `work/ai-bakeoff/lidl-phase6-deletion-smoke-v2`. Confirm the
    channel-9 Snare parent
    `0718458e900dbcdf7dff7332c77808054dfaadb6c517d2c22d7b967a28f50826`
    and object
    `65b140afecb84099abbdf9880ee4597d8eeb7c6caf5d470e62213654ee857ae5`,
    the one removed pitch-38 velocity-46 interval at ticks 140487–140573,
    and the resulting 249-to-248 Clip and normalized-MIDI note counts. The copy
    grew to 13 Clips; the child was
    `sf-correction-6914357fcfbca9f597fe09ca8912fda3516554226bbbdab1507295f9b309576c`
    with object
    `622f9e88616f3b9450a126e5b671aae557e1b2ac8e27f9de3103828f61e5f20b`.
    Confirm unchanged beat/export/source horizons, all-false replay, path-free
    restart summary and deterministic child MIDI SHA-256
    `1e3e20d607c62b7b6c06d210b9f3fa90c1f126166aadcf86d82d870d83f5535c`.
    The focused integrated suite passed 81 tests, the final independent audit
    passed 49 and the complete suite passed 970 tests. The single warning is
    the existing `resampy`/`pkg_resources` deprecation notice. Keep broader
    Phase 6 in progress.
    For Phase 6 Increment 6.3d, require explicit advertised
    `note_onset_shift_patch`, `maximum_onset_delta_ticks: 480`, generic
    `timing: false`, operation `shift_note_onsets` and 1–64 exact existing
    pitched or drum note refs. Report each before/after Note On and Note Off
    tick, held duration, signed tick/export-millisecond delta, beat start and
    source-second start. Confirm the complete old and new intervals are inside
    the half-open window, both events moved by one equal non-zero delta no
    greater than 480 ticks, and normalized MIDI duration, pitch,
    attack/release velocity, articulation, note count and unaffected notes are
    exact. For musical timing confirm duration beats and both microtiming fields
    were retained and source seconds were recomputed through the tempo map. For
    stem-locked timing confirm both microtiming values were zero, source
    start/end moved by `delta * 60 / (export_bpm * 480)`, source duration stayed
    exact and beat coordinates were derived. Require exact tick round-trip and
    unchanged beat/export/source horizons. Confirm only the four documented
    row block reasons are exposed and that overlap/duplicate/cascade, window,
    negative/VLQ and horizon attempts fail. Projection is all false; fresh
    create true effects are exactly library/child/correction/onset/timing;
    replay and restart are all false. Confirm no inference, snap, quantise,
    theory repair, repetition propagation, selection, placement, export or
    automatic audition. Increment 6.3d is complete on deterministic
    engineering evidence only. The accepted Lidl exercise at
    `work/ai-bakeoff/lidl-phase6-onset-smoke-v1` preserved the 12-Clip source
    and parent, grew only the copy to 13, and moved one channel-1 pitch-66
    interval in the 1,727-note Keys Clip from ticks 442–873 to 472–903. Require
    the exact +30-tick/+31.512625-ms delta, unchanged 431-tick duration and
    unchanged 462.6458333333333-beat, 222070-tick and
    233.26695445833332-second horizons. Parent
    `a6112b69031a233a54531128dca4925f32d5b3b32ce5552daaa6393d0138d8aa`
    (object
    `d37975c915e790e290650cf5b48e316c19318c28bd1a50c3de342e889180356a`)
    produced child
    `sf-correction-495e77ba31528090cc979465459d50acf9ad8f4e36f8a783e9f30398703d5727`
    (object
    `e70a297a01be3a086f5fa05e8dabb47975e6b634dd1adfc4e8c17565524932a2`).
    Parent/child MIDI SHA-256 values are
    `e741334f8dfc1421850618d088b382a5fc051fc1fada4797ac742a1dcd201036`
    and
    `20b1298550568bb51cdb98c4d8e342a4ac27e22b2cd58f5e03f48f062cad7d9b`.
    Fresh effects were exactly `library_mutated`, `child_clip_created`,
    `correction_applied`, `note_onset_changed` and `note_timing_changed`;
    replay/restart were all false. The focused suite passed 101 tests and the
    adversarial audit passed 17 onset plus 82 broader correction/server/UI
    tests. The complete repository suite passed 990 tests in 282.58 seconds
    with the one existing third-party `resampy`/`pkg_resources` deprecation
    warning. Do not
    turn that completion evidence into a human preference or musical-quality
    claim; no such listening result was recorded.
    For Phase 6 Increment 6.3e, require advertised
    `note_end_shift_patch`, `maximum_note_end_delta_ticks: 480`,
    `minimum_note_duration_ticks: 1`, generic `timing: false`, operation
    `shift_note_ends` and exact schemas
    `sunofriend.workbench-clip-note-end-window.v1`,
    `sunofriend.workbench-clip-note-end-preview.v1`,
    `sunofriend.workbench-clip-note-end-result.v1` and
    `sunofriend.workbench-clip-note-end-summary.v1`. Confirm 1–64 exact refs
    and integer `target_end_tick` values, a
    non-zero delta within ±480, at least one tick of duration and both source
    and target intervals in the half-open window. Confirm Note On, pitch,
    expression, count and unaffected notes are exact. Verify musical and
    stem-locked dual-time behavior, the same four row block reasons, exact
    Note Off round-trip, next same-pitch/lifetime-cascade rejection and fixed
    beat/export/source horizons. Projection is all false; fresh true effects
    are exactly library/child/correction/duration/timing; replay and restart
    are all false. Require explicit Apply, Review and Create, with no inferred
    legato, phrasing, correctness, preference or musical quality.
    Confirm the browser's restored note-end summary fails closed for malformed
    child, lineage, timing, diff or effect evidence; it must not reconstruct a
    plausible summary from current detail state.
    The ignored smoke at
    `work/ai-bakeoff/lidl-phase6-duration-smoke-v1` has report SHA-256
    `d0141814026c434c4702a9c7dcd00466fd6502921bb5e0fa1b437657d675bb77`.
    It preserved the 12-Clip source and grew only the copy to 13. Parent Keys
    Clip `a6112b69031a233a54531128dca4925f32d5b3b32ce5552daaa6393d0138d8aa`
    (object
    `d37975c915e790e290650cf5b48e316c19318c28bd1a50c3de342e889180356a`)
    produced child
    `sf-correction-067bbbfc65e112ba175da84648f2b74f40b5cb5137eabb5f91ff28f4af9f03f6`
    (object
    `14fee0a6ac7dbc29043199e30041adc93c59eda34fccd8a6a9a15d972846281f`).
    Both have 1,727 notes; channel-1 pitch 66 changed 442–873→442–903,
    +30 ticks/+31.512625 ms and duration 431→461 ticks, with horizons exact at
    462.6458333333333 beats, 222070 ticks and 233.26695445833332 seconds.
    Parent MIDI was
    `e741334f8dfc1421850618d088b382a5fc051fc1fada4797ac742a1dcd201036`;
    child and repeat were
    `27d5be64a4e992548c6a58139f8a7fb677e3d7f4cefc55ea4e2fc163b74fa918`.
    The focused integrated correction/UI suite passed 133 tests, the smoke
    passed and the complete repository suite passed 1009 tests with the one
    existing `resampy`/`pkg_resources` deprecation warning. Do not turn this
    into a human preference.
    Keep note insertion, release velocity/continuous
    expression, theory repair, repetition propagation and hybrids deferred.
    Release velocity currently has no useful non-zero local golden and
    GarageBand patch support varies.
