---
name: sunofriend
description: Use the local Sunofriend CLI to convert isolated Suno/Moises WAV stems and lead or backing vocals into evaluated GarageBand-ready MIDI; combine tracker consensus, phrase-by-phrase alternatives, repeated phrases, hummed guidance, explicit reviewed choices and local advisory review-history profiles; create short experimental MIDI-guided target/residual cleanup pairs; inventory, sound-match, audition, build self-contained SF2 sample instruments, or package MIDI plus sound in Instrument Bundle v1; preview or play results; change MIDI key, BPM, tuning, and downbeat alignment; and store or transform Clip v1 parts. Use for Sunofriend, stems-to-MIDI, vocal melody MIDI, GarageBand timing, MIDI mashups, instrument selection, stem sample instruments, tempo or transposition changes, and stem-versus-MIDI accuracy. Do not use for generic stem separation, mastering, lyric writing, downloading third-party plug-ins, or editing a DAW GUI.
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
   - `sunofriend ai-doctor --require game` before a standalone GAME vocal
     boundary/pitch bake-off. Its explicit setup command is
     `scripts/setup-game-model.sh`; inference itself must remain offline.
   - `sunofriend ai-doctor --require rmvpe` before a standalone RMVPE F0
     bake-off. Its explicit setup command is `scripts/setup-rmvpe-model.sh`;
     inference must use the existing local ONNX file and remain offline.
   - `sunofriend ai-doctor --require pesto` before a standalone PESTO F0
     bake-off. Its explicit setup command is `scripts/setup-pesto-model.sh`;
     inference must use the hash-checked local `.ckpt` file and remain offline.
   - `sunofriend doctor --require convert` for instrumental stem conversion.
   - `sunofriend doctor --require convert` for the short experimental
     `midi-mask` target/residual workflow.
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
5. Inventory the input directory read-only. Confirm files exist and identify
   stem roles, chord PDF, metronome, key, BPM, and tuning.
6. Use absolute, quoted paths and a fresh output outside the source folder.
   Never add `--overwrite` unless the user explicitly asks to replace output.
7. If the CLI or a dependency is missing, report the exact component. Install
   packages or download a SoundFont only when setup is within the request.

## Choose the workflow

- Whole instrumental stem folder: use `listen-all`; default to
  `--conversion-mode repair` and leave evaluation enabled.
- One instrumental stem: use `listen` with an explicit supported `--kind`.
- One proposed role inside a mixed pitched stem: use `midi-mask` only on a
  short excerpt with an aligned note-bearing MIDI track. Treat its harmonic
  target and waveform-defined residual as transparent challengers, not a
  physical source identification. Require an explicit `--track-index` for
  multi-track MIDI, preserve both outputs and never promote from reconstruction
  accuracy or metrics alone. A separately requested broadband transient window
  may improve attacks but can admit simultaneous instruments.
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

## Validate and hand off

1. Check the exit status and generated JSON summary. Treat partial or no-output
   status as incomplete.
2. Confirm every reported MIDI and JSON sidecar exists.
3. Inspect evaluation and provenance. Report note counts, onset precision,
   recall or F1, timing p95 and drift, pitch or octave evidence, and observed,
   repaired, inferred, possible, or uncertain counts where available. Do not
   invent universal pass thresholds.
   For `midi-mask`, additionally report source/MIDI hashes, selected track and
   role, excerpt bounds, intersecting notes/pitches, mask parameters, source/
   target/residual RMS, persisted PCM24 reconstruction error and threshold,
   repeat artifact hashes and all zero input-mutation effects. Re-transcribe
   source, target and residual separately. A target that improves pitch support
   but loses attacks is not a cleanup success.
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
