---
name: sunofriend
description: Use the local Sunofriend CLI to convert isolated Suno/Moises WAV stems and lead or backing vocals into evaluated GarageBand-ready MIDI; combine tracker consensus, repeated phrases, hummed guidance and reviewed melody corrections; inventory, sound-match, audition, build self-contained SF2 sample instruments, or package MIDI plus sound in Instrument Bundle v1; preview or play results; change MIDI key, BPM, tuning, and downbeat alignment; and store or transform Clip v1 parts. Use for Sunofriend, stems-to-MIDI, vocal melody MIDI, GarageBand timing, MIDI mashups, instrument selection, stem sample instruments, tempo or transposition changes, and stem-versus-MIDI accuracy. Do not use for stem separation, mastering, lyric writing, downloading third-party plug-ins, or editing a DAW GUI.
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
   - `sunofriend doctor --require transcribe` for lead or backing vocals.
   - `sunofriend doctor --require convert` for instrumental stem conversion.
   - `sunofriend doctor --require preview` for offline rendering.
   - `sunofriend doctor --require playback` for live MIDI.
   - `sunofriend instrument-inventory` needs no audio/ML capability check.
   - `sunofriend doctor --require convert` for factory-sample matching or
     stem-derived sample instruments. Also require `preview` for rendered GM
     matches and for sample instruments unless using `--no-preview`.
   - `sunofriend instrument-bundle` has the same requirements as both
     `instrument-match` and `sample-pack`. `--no-gm --no-preview` removes the
     FluidSynth requirement; `--no-source-instrument` removes sampling.
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
- Lead or backing vocals: use `vocal-melody` separately. It defaults to
  pYIN/Basic Pitch consensus, conservative repeated-phrase repair and a local
  correction HTML/JSON report. `listen-all` does not include vocals.
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
  rendered-GM evidence unless the user requests one path.
- New instruments from authorised isolated source notes: use `sample-pack`.
  Treat `sunofriend-instrument.aupreset` as the GarageBand-selectable wrapper
  and `sunofriend-instrument.sf2` as its self-contained sound bank. GarageBand's
  preset chooser greys out raw SF2 files.
  Do not add `--allow-polyphonic` unless the user explicitly accepts chords or
  bleed baked into each sample.
- Normal combined MIDI/sound/match handoff: use `instrument-bundle`. It copies
  the source WAV by default, so use `--no-source-audio` when portability is not
  wanted. Use `--no-source-instrument` unless sampling is authorised. A
  `partial` bundle is valid only when its warnings explain the missing sound or
  match component.
- Offline audition: use `preview`; live MIDI: use `midi-ports` then `play`.

Read the live command help for exact options. Typical command shapes are:

```bash
sunofriend listen-all "$INPUT" \
  --out-dir "$OUTPUT" \
  --conversion-mode repair

sunofriend vocal-melody "$VOCAL_STEM" \
  --role lead \
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

sunofriend sample-pack "$STEM" "$ALIGNED_MIDI" \
  --kind "$ROLE" \
  --name "$INSTRUMENT_NAME" \
  --out-dir "$FRESH_OUTPUT"

sunofriend instrument-bundle "$STEM" "$ALIGNED_MIDI" \
  --kind "$ROLE" \
  --name "$INSTRUMENT_NAME" \
  --out-dir "$FRESH_OUTPUT"
```

## Musical and data rules

- Use `exact` for confident observed evidence, `repair` for conservative
  corrections, and `reconstruct` only for explicitly requested inference.
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
- Do not copy, edit or redistribute Apple factory samples. Do not claim that
  Sunofriend can headlessly render every private GarageBand patch.
- For sample packs, use only source audio the user owns or may sample. State
  that bleed, effects, vibrato and transitions become part of each sample and
  that Sample Instrument v2 has no inferred loops or velocity layers. Keep
  auto-tuning enabled unless the user asks to preserve the source's raw tuning;
  do not present `no-stable-pitch` or rejected tuning estimates as failures.
- Tracker consensus does not mean certainty. Inspect disputed/solo frame
  counts and keep `uncertain` separate. Repeated-phrase repair may promote only
  notes already present in the lenient source contour; a hummed guide may set
  intention and rhythm but must not bypass source-pitch support.
- For guide snippets, report every requested and chosen start time, per-snippet
  transpose, detected/accepted note count and warning. A failed snippet must
  not remove the automatic full-song melody.
- A correction JSON is a user-authored replacement note list. Apply it to a
  fresh MIDI path and retain the adjacent `.correction.json` audit.

## Validate and hand off

1. Check the exit status and generated JSON summary. Treat partial or no-output
   status as incomplete.
2. Confirm every reported MIDI and JSON sidecar exists.
3. Inspect evaluation and provenance. Report note counts, onset precision,
   recall or F1, timing p95 and drift, pitch or octave evidence, and observed,
   repaired, inferred, possible, or uncertain counts where available. Do not
   invent universal pass thresholds.
4. For vocals, inspect contour coverage, pitch-error statistics, monophony, and
   the published variants. Also report tracker sources, consensus frame count,
   repeated-phrase promotions, guide alignment/transpose and the correction
   HTML/JSON paths when present.
5. For transformations, inspect the JSON audit for file count, embedded target
   tempo, transposed events, preserved drums, tuning cleanup, and anchor shift.
6. Render representative MIDI with `preview` when auditory validation is in
   scope and `render_ready` is true.
7. Hand off the exact GarageBand BPM, recommended MIDI, audition alternatives,
   instrument suggestions, warnings, and reproducible commands.
8. For `instrument-match`, confirm the JSON, GarageBand audition guide, timbre
   graph when present, and retained top GM MIDI/WAV pairs. Report both evidence
   rankings and ask the user to choose in the full mix.
9. For `sample-pack`, confirm the optional macOS `.aupreset` wrapper, SF2, SFZ,
   audition MIDI, optional audition WAV, source WAVs and JSON exist. Report MIDI
   roots and key ranges, isolation, tuning status counts, maximum transposition
   and sustain limitations. Hand off the report's GarageBand steps: keep the
   preset and bank at their generated paths, put the audition MIDI on a
   software-instrument track, select Apple AUSampler, load the `.aupreset` from
   its **Manual** preset menu, audition every zone, then save the configured
   track as a custom patch if wanted.
10. For `instrument-bundle`, confirm `performance.mid`, recipe/report, source
    reference when requested, match directory, source instrument when safe,
    and retained previews. Explicitly distinguish an embedded authorised SF2
    from a non-embedded Apple factory recommendation.
