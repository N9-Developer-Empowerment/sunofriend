# Contributing to Sunofriend

Sunofriend is currently proven most deeply with Suno/Moises exports and
GarageBand on macOS. Compatibility reports from other workflows are valuable
even when they reveal a failure: they turn assumptions about MIDI timing,
tempo, key, instruments and stem quality into reproducible requirements.
Contributions are accepted under the repository's
[Apache License 2.0](LICENSE).

## Test another DAW, music tool or AI workflow

You can use the committed
[`examples/the-aisle-at-lidl/`](examples/the-aisle-at-lidl/) MIDI pack without
sharing any audio, or convert stems that you own or are allowed to distribute.

Useful test targets include:

- Logic Pro, Ableton Live, FL Studio, REAPER, Cubase, Studio One, Pro Tools,
  Bitwig, Ardour, LMMS and mobile DAWs;
- software instruments, samplers, notation software, hardware synths and drum
  machines;
- other AI music generators;
- other separation/chord tools, including local or open-source separators;
- Windows and Linux MIDI import/playback as well as macOS.

### Minimal compatibility test

1. Import `examples/the-aisle-at-lidl/midi/repair/full-arrangement.mid` at
   119 BPM.
2. Confirm that the DAW imports nine note/instrument tracks and preserves the
   assigned channels. The Standard MIDI File contains ten track chunks because
   it also has a conductor/meta track. The six drum tracks intentionally share
   zero-based channel 9 (General MIDI channel 10).
3. Audition the deep/high kick, three bass choices and keys role files.
4. Import the reconstruct arrangement and check that melody plus pads does not
   duplicate the omitted strings harmony.
5. Record the software/version, operating system, import settings, observed
   tempo, first-note offset, end drift and any remapped instruments.

[`results.json`](examples/the-aisle-at-lidl/results.json) provides the exact
earliest note-on/latest note-end baselines. For the repair arrangement they are
0.197479 s and 234.451829 s; for reconstruct they are 0.222689 s and
234.451829 s. The reconstruct file contains four note/instrument tracks and
five Standard MIDI File track chunks including its conductor/meta track.
“Round-trip drift” means the difference after DAW import/export. “Source-audio
drift” means comparison with an authorised source stem and cannot be measured
from the bundled MIDI alone.

For a source-aligned test, compare the original stem and MIDI at the same
timeline origin with quantisation and audio stretching disabled. Never upload
music, stems, screenshots or project files unless you have permission.

## Raise an issue

Use the
**[DAW / AI compatibility report](https://github.com/N9-Developer-Empowerment/sunofriend/issues/new?template=daw-ai-compatibility.yml)**
for integration results. Include:

- DAW/music/AI/separation software and exact version;
- operating system and architecture;
- Sunofriend commit or version;
- source key/BPM and the GarageBand/DAW project tempo;
- the exact command and conversion mode when you ran a conversion, or the
  bundled example file you imported directly;
- expected versus observed behaviour;
- timing evidence in milliseconds where possible;
- a minimal MIDI or JSON report when redistribution is authorised.

Use a normal issue for code defects. Keep one independently reproducible
problem per issue.

## Code contributions

Before opening a pull request:

```bash
python -m pytest
python -m ruff check src tests
python -m sunofriend doctor --require convert
```

For conversion work, `doctor` must report `convert_ready` as true. Require
`playback` only for CoreMIDI changes.

Add a deterministic regression test for behaviour changes. Preserve existing
golden outputs unless the change is intentional and explained with updated
stem-to-MIDI metrics.
