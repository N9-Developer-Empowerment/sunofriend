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
