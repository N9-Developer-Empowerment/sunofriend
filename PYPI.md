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
clearly labelled proxy arrangement for GarageBand. It loads no remote scripts
and has no upload or submission endpoint. Completed AI runs add path-free
model/config, label, boundary and safety diagnostics; severe or zero-note
results remain diagnostic-only. `sunofriend ai-matrix` compares controlled
immutable lanes without changing raw candidates or MIDI.

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
