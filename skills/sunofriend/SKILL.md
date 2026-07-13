---
name: sunofriend
description: Use the local Sunofriend CLI to convert isolated Suno/Moises WAV stems and lead or backing vocals into evaluated GarageBand-ready MIDI; preview or play results; change MIDI key, BPM, tuning, and downbeat alignment; and store or transform Clip v1 parts. Use for Sunofriend, stems-to-MIDI, vocal melody MIDI, GarageBand timing, MIDI mashups, tempo or transposition changes, and stem-versus-MIDI accuracy. Do not use for stem separation, mastering, lyric writing, or editing a DAW GUI.
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
- Lead or backing vocals: use `vocal-melody` separately. `listen-all` does not
  include vocals.
- Existing stem/MIDI comparison: use `evaluate`.
- BPM-only change preserving bars and ticks: use `midi-tempo`.
- Complete MIDI key, BPM, or recognised Sunofriend tuning change: use
  `midi-transform`.
- Shared starting downbeat while preserving groove and tempo wander: use
  `midi-anchor`.
- Fully straight 4/4 grid: use `midi-align` only after explaining its note-only
  data-loss contract.
- Reusable part storage and versioning: use the `clip-*` commands.
- Offline audition: use `preview`; live MIDI: use `midi-ports` then `play`.

Read the live command help for exact options. Typical command shapes are:

```bash
sunofriend listen-all "$INPUT" \
  --out-dir "$OUTPUT" \
  --conversion-mode repair

sunofriend vocal-melody "$VOCAL_STEM" \
  --role lead \
  --out-dir "$OUTPUT"

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

## Validate and hand off

1. Check the exit status and generated JSON summary. Treat partial or no-output
   status as incomplete.
2. Confirm every reported MIDI and JSON sidecar exists.
3. Inspect evaluation and provenance. Report note counts, onset precision,
   recall or F1, timing p95 and drift, pitch or octave evidence, and observed,
   repaired, inferred, possible, or uncertain counts where available. Do not
   invent universal pass thresholds.
4. For vocals, inspect contour coverage, pitch-error statistics, monophony, and
   the published variants.
5. For transformations, inspect the JSON audit for file count, embedded target
   tempo, transposed events, preserved drums, tuning cleanup, and anchor shift.
6. Render representative MIDI with `preview` when auditory validation is in
   scope and `render_ready` is true.
7. Hand off the exact GarageBand BPM, recommended MIDI, audition alternatives,
   instrument suggestions, warnings, and reproducible commands.
