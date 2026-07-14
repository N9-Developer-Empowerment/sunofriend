# Sunofriend architecture

Sunofriend has two user-facing layers:

1. The Python package and `sunofriend` command are the deterministic engine.
2. The portable Agent Skill selects commands, checks prerequisites and
   interprets reports. It must not duplicate audio or MIDI algorithms.

## Current execution flow

```text
stem folder / MIDI
        |
        v
CLI parsing (`cli.py`)
        |
        +--> folder orchestration (`listen_all.py`)
        +--> stem refinement (`loop.py`)
        +--> vocal extraction (`vocal.py`)
        +--> lossless MIDI transforms (`midi_tempo.py`, `midi_transform.py`,
        |                            `midi_anchor.py`)
        +--> creative grid rebuild (`midi_align.py`)
        +--> instrument discovery (`instrument_catalog.py`)
        +--> timbre matching/sample packs (`instrument_match.py`)
        +--> portable sound/match handoff (`instrument_bundle.py`)
        +--> hummed guidance and review artifacts (`melody_correction.py`)
        +--> self-contained SoundFont writing (`soundfont.py`)
        +--> reusable Clip v1 library (`clip.py`, `library.py`)
        |
        v
MIDI + provenance/evaluation JSON + optional WAV preview
```

Instrument matching deliberately has two adapters rather than a private DAW
integration: installed GarageBand/Logic sample assets are profiled directly,
while candidate MIDI programs are rendered through the existing FluidSynth
boundary. The output is an audition shortlist. Stem-derived sample instruments
write cleaned WAV/SFZ assets plus a narrow, self-contained SoundFont 2.01 bank
that Apple's public sampler interface and FluidSynth can load. They never
mutate Apple factory content, private patch files or GarageBand project bundles.

The CLI command names, exit codes, JSON reports, Clip v1 schema and generated
MIDI timing contracts are compatibility surfaces. Private helpers beginning
with `_` are implementation details and should not be called by agent skills or
third-party integrations.

## Change rules

- Preserve source audio and existing output by default. Require an explicit
  overwrite option for destructive replacement.
- Characterize MIDI byte/event behaviour before moving parsers. Running status,
  SysEx, tempo maps, controllers, drum channel 10 and pitch bends all matter.
- Keep `exact`, `repair` and `reconstruct` evidence policies distinct.
- Publish uncertainty and provenance rather than silently turning weak evidence
  into main-track notes.
- Keep optional audio, preview and playback dependencies lazy so pure MIDI and
  Clip operations work in a lightweight installation.
- Add a deterministic regression test before changing pitch, timing, note
  count, provenance or output layout.
- Keep instrument discovery read-only. Treat matching weights and report
  fields as evidence contracts, and retain the final patch choice as user
  feedback that can be stored through Clip v1.

## Incremental refactoring map

The safest next boundaries are:

1. Add typed application operations for folder conversion, one-stem conversion,
   vocal extraction and MIDI transformation; keep CLI handlers as adapters.
2. Centralize instrument roles, aliases, channels, GM programs and GarageBand
   suggestions in one immutable registry.
3. Introduce a lossless Standard MIDI File codec and shared batch/path-safety
   utilities, then migrate one command at a time against a common fixture set.
4. Share phase-safe audio loading and an explicit beat-grid to `TempoMap`
   adapter.
5. Split the large Clip and vocal modules only after compatibility re-exports
   and characterization tests exist.

Do not combine those moves into a single rewrite. The existing golden songs
and synthetic tests are the guardrail for each small migration.
