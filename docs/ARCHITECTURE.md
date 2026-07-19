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
        +--> short MIDI-guided cleanup evidence (`midi_mask.py`)
        +--> isolated learned cleanup challenger (`ai_cleanup.py`,
        |                                         `ai_cleanup_worker.py`)
        +--> immutable AI lane comparison (`ai_matrix.py`)
        +--> reviewed multi-role MIDI challenger (`midi_role_split.py`)
        +--> fixed-MIDI timbre baseline (`timbre_resynthesis.py`)
        +--> local decision workbench (`workbench_catalog.py`,
        |                              `workbench_store.py`,
        |                              `workbench_server.py`)
        +--> instrument discovery (`instrument_catalog.py`)
        +--> timbre matching/sample packs (`instrument_match.py`)
        +--> arrangement-aware sampler gate (`instrument_usability.py`)
        +--> explicit local patch preferences (`instrument_preference.py`)
        +--> portable sound/match handoff (`instrument_bundle.py`)
        +--> hummed guidance and review artifacts (`melody_correction.py`)
        +--> self-contained SoundFont writing (`soundfont.py`)
        +--> reusable Clip v1 library (`clip.py`, `library.py`)
        |
        v
MIDI + provenance/evaluation JSON + optional WAV preview
```

`midi_mask.py` is an experimental Phase 4 boundary, not a generic separator.
It accepts one explicit note-bearing MIDI track, limits work to a short audio
excerpt, and publishes source, harmonic target and waveform-defined residual
as deterministic PCM24. Persisted target-plus-residual reconstruction, hashes
and zero input-mutation effects are part of its report contract; listening and
re-transcription decide whether either derivative is useful.

`ai_cleanup.py` is the corresponding learned-model boundary. The deterministic
core extracts an immutable PCM24 excerpt, hard-verifies the pinned external
checkpoint, invokes `ai_cleanup_worker.py` in `.venv-ai`, validates the
float32 target, and defines the residual from persisted source minus persisted
target. The worker is CPU-only with zero random shifts and cannot download a
model or promote its output. Because the exact Demucs checkpoint uses PyTorch
pickle serialization, the worker permits `weights_only=False` only after the
complete official SHA-256 has matched. Failed and successful runs both retain
request, logs and hashes.

`midi_role_split.py` is the post-listening arrangement boundary. It consumes
one immutable note-bearing MIDI plus its matching source-event cluster report,
requires the retained body cluster explicitly and writes an exact body-plus-
complement partition. An optional independently transcribed residual becomes a
separate overlapping challenger rather than being silently merged. The module
copies source references into a fresh local review directory, renders
contrasting GM proxies and publishes an unreviewed export; it neither identifies
physical instruments nor promotes a split from clustering metrics.
Its resolver accepts only a complete user-exported review, verifies the entire
source evidence tree and treats the overall decision as authoritative. The
recommended MIDI is an exact copied artifact, never a regenerated or merged
track; useful component auditions remain evidence rather than implicit votes.

`timbre_resynthesis.py` is the fixed-performance sound boundary. It accepts one
short aligned reference and one monophonic constant-tempo MIDI, fits a single
harmonic distribution, sustain ratio and deterministic attack-noise amount,
and renders every note with that common profile. The identical note multiset is
also rendered through complete SoundFont controls. Candidates are level-matched
and checked note by note for functional silence before an unreviewed listening
page is published. The module trains no model, changes no MIDI and does not
claim that the resulting WAV is a GarageBand instrument.

The Phase 5 Workbench is a presentation and explicit-decision boundary, not a
new transcription engine. `workbench_catalog.py` hash-pins existing source,
MIDI and preview artifacts and limits the normal result space to three
non-diagnostic candidates. `workbench_store.py` records immutable events in a
local SQLite database and derives current state without updating old choices.
`workbench_artifacts.py` owns content-addressed role-neutral previews, selected
arrangement proxies and deterministic GarageBand handoff ZIPs. It reads notes
through Clip v1 and renders through the existing MIDI/FluidSynth boundaries;
discovered MIDI is never rewritten, and numbered handoff tracks are exact
copies of explicit main/optional choices. Rejected, needs-correction,
superseded and unreviewed candidates never enter the arrangement or ZIP.
`workbench_server.py` binds only to `127.0.0.1`, requires a per-launch token,
serves only catalogued or locally generated verified-cache files, supports byte
ranges for media seeking and loads no remote scripts. Its packaged HTML uses a
shared position for source/candidate switching and records explicit solo or
full-mix context. Its contribution preview excludes audio, MIDI, paths,
free-text notes, dwell time and play counts; there is no submission endpoint.

`ai_matrix.py` applies a model-neutral quality/report schema to already
completed immutable runs from one controlled backend, checkpoint, model config
worker, runtime version and execution profile. It verifies request, candidate,
raw artifacts, MIDI,
source, worker, checkpoint and model-config hashes, then publishes path-free
aggregate/per-instrument quality,
requested/detected-label differences, five-second-boundary activity, label
stability and cross-lane same-pitch/onset overlap. It reports zero raw/MIDI
mutations and cannot promote a candidate. `ai_bakeoff.py` owns the normalized
MuScriptor execution contract: the pinned 0.2.1 baseline is greedy, batch 1,
beam 1 and CFG 1.0 with independent five-second chunks. Because that runtime
does not expose prelude forcing, the manifest records it as unsupported and a
true request is rejected.

When a Workbench candidate is adjacent to a completed AI run,
`workbench_catalog.py` attaches the same path-free diagnostics. Severe decoder
codes and zero-note results are diagnostic-only and cannot be rendered or
selected as main/optional; ordinary label leakage remains reviewable.
`workbench_server.py` and `workbench_artifacts.py` reverify hashes at each
serve, render, arrangement and handoff boundary so catalog discovery cannot be
invalidated silently by a later file change. The pinned SoundFont is rechecked
before cached use for the same reason.
Automatic discovery resolves sources, MIDI and previews and rejects symlinks
outside the explicit project/candidate roots before adding them to the
token-protected media map. Stem state identifiers include source content, role
and filename so byte-identical stems do not share SQLite decisions.

Instrument matching deliberately has two adapters rather than a private DAW
integration: installed GarageBand/Logic sample assets are profiled directly,
while candidate MIDI programs are rendered through the existing FluidSynth
boundary. The output is an audition shortlist. Stem-derived sample instruments
write cleaned WAV/SFZ assets plus a narrow, self-contained SoundFont 2.01 bank
that Apple's public sampler interface and FluidSynth can load. They never
mutate Apple factory content, private patch files or GarageBand project bundles.

`instrument_usability.py` is the boundary between successful artifact creation
and a usable musical instrument. It tests the generated zones against the
actual selected MIDI track for key/velocity coverage and effective one-shot
duration. A failure demotes the bank to an optional texture layer in Instrument
Bundle v1; it does not modify notes, samples or mappings. Pitch estimates and
timbre clusters remain listening evidence rather than automatic rejection.

`instrument_preference.py` is a deliberately explicit feedback boundary. It
hash-pins one reviewed DAW patch choice to an Instrument Bundle, then builds a
deterministic profile only from paths named by the user. Bundle integration is
additive: it copies the profile and displays a history-first hint while leaving
factory/GM/OpenL3 ranking, defaults, MIDI and the usability gate unchanged.
There is no implicit file discovery, hidden preference database or automatic
patch selection.

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
