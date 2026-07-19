# Sunofriend

Sunofriend converts separated music stems and vocal performances into editable,
timing-aware MIDI for GarageBand and other DAWs. It can evaluate stem-to-MIDI
accuracy, publish conservative or reconstructed variants, change MIDI key and
tempo, preserve or straighten groove, and store reusable Clip v1 parts.
It can also inventory installed GarageBand/Audio Unit instruments, create
sound-based audition shortlists, and extract authorised isolated stem notes as
self-contained SF2 sample instruments with GarageBand-selectable Apple
AUSampler preset wrappers, with WAV/SFZ sources and pitch-mapping evidence
retained.
Instrument Bundle v1 keeps the MIDI, authorised carried sound, local factory
and General MIDI match evidence, source reference, and A/B previews together.
An arrangement-aware usability gate demotes incomplete source samplers to
optional texture layers. Explicit DAW choices can be hash-pinned with
`instrument-feedback`, combined into a deterministic local advisory profile,
and shown in later bundles without automatic patch selection or match
reordering.
Vocal melody extraction adds pYIN/Basic Pitch consensus, conservative repeated
phrase repair, an optional hummed guide, and a local visual correction report
whose reviewed JSON can be converted back into tuned MIDI.
An optional isolated AI runtime can also test pinned local learned cleanup on
short stem excerpts. Its target/residual evidence is reconstructable and never
replaces the normal MIDI path without an explicit listening decision.
Reviewed event-cluster evidence can then produce non-destructive multi-role
MIDI A/Bs, including a separately transcribed residual layer for overlapping
parts, without claiming automatic instrument recognition.
A completed role review can be resolved into an exact hash-verified copy of
the user-selected MIDI; component usefulness never silently overrides the
overall arrangement decision.
That fixed monophonic MIDI can then drive a level-matched timbre review that
compares complete, extracted-sample and deterministic harmonic-plus-noise
sounds while checking every note for functional audibility.
The loopback-only Workbench presents existing source/MIDI alternatives in a
normal browser, saves append-only solo/full-mix choices, renders missing MIDI
through a verified local neutral-preview cache, auditions only explicit
main/optional parts together, and packages unchanged selected MIDI plus a
clearly labelled proxy arrangement for GarageBand. Selected candidates with
the same candidate-origin source receive a diagnostic doubled-line warning
when exact-pitch attacks substantially overlap. AI candidates use the verified
run source hash; non-AI MIDI falls back to the review-stem source hash. The
arrangement remains audible, no MIDI is deduplicated, and GarageBand handoff
waits for explicit full-mix confirmation only when a selected same-origin pair
reaches that substantial-overlap threshold.
The exact private review can also be archived atomically from the CLI without
starting a server. The Workbench loads no remote scripts and has no upload or
submission endpoint. Completed AI runs add path-free
model/config, label, boundary and safety diagnostics; severe or zero-note
results remain diagnostic-only. `sunofriend ai-matrix` compares controlled
immutable lanes without changing raw candidates or MIDI. Its M4 contract
compares distinct one-role passes only when source, excerpt and BPM match and
reports possible role collapse as diagnostic overlap. `ai-label-split` can
then create an exact raw-event label partition plus deterministic requested and
complement MIDI auditions while retaining a byte-identical full-candidate
control. MIDI quantisation/normalisation effects are reported explicitly; this
is not source separation and never promotes a result automatically. Explicit
Workbench catalogs may add a focused
listening question and checklist without turning either into a score or choice.

Sunofriend complements AI music generators, stem separators, and DAWs rather
than replacing them. The current supported production workflow is macOS-first,
using Python 3.9–3.11, FluidSynth for offline preview, and CoreMIDI for optional
live playback.

See the [full documentation, worked examples, and agent-skill setup](https://github.com/N9-Developer-Empowerment/sunofriend#readme).

After a package release, install the full tool with:

```bash
brew install fluid-synth
uv tool install --python 3.11 'sunofriend[all]'
sunofriend doctor --require convert
```

The repository also contains a portable Agent Skills workflow for Codex and
Claude Code. Agent discovery links are installed by cloning or linking the
repository; they are not written by the Python wheel. The skill orchestrates
the packaged CLI without uploading audio or replacing the deterministic
conversion engine.

Sunofriend is distributed under the Apache License 2.0.
