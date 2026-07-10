# Sunofriend

Sunofriend generates cleaner GarageBand-ready MIDI remakes from Moises/Suno export folders.

## listen-all: whole export folder in one command

```bash
PYTHONPATH=src python -m sunofriend.cli listen-all \
  "path/to/Suno Export Folder" --out-dir work/mysong
```

Finds every stem, the chords PDF, and the metronome automatically; infers
BPM/key from the folder name. Produces one `<part>_listened.mid` per stem and
a combined `full_arrangement.mid` (set GarageBand's tempo to the *true* BPM
printed by the command — derived from the metronome clicks, it is often not
exactly the nominal BPM).

What each part gets:

- **kick/snare/hat/cymbals/toms/other_kit** — onset transcription + refine loop.
- **bass/lead** — "imagine" mode: transcription evidence cleaned by music
  theory (metronome-true grid, key scale, chord chart) so every note is
  on-grid and in-key.
- **pads** — chord-mode built from the keys stem: chart voicings with the
  boundaries aligned to the audio (chroma DP), dynamics from the stem. Use
  this OR the `keys` transcription track, whichever sounds better.
- Near-silent stems (separation bleed) are detected and skipped.

## Listen mode (new)

`listen` transcribes a single stem by actually listening to it, then iteratively
refines the result:

1. **Transcribe** — drums via onset detection (~6 ms resolution, velocity from hit
   energy, closed/open hat and tom pitch classification); keys/synth/bass via
   Spotify basic-pitch (polyphonic ML transcription with octave-ghost filtering).
2. **Render** — the candidate MIDI is played back headlessly through FluidSynth +
   a GM SoundFont (the "proxy instrument" — no GarageBand involved).
3. **Compare** — rendered audio vs. the original stem in *feature space* (onset
   times for drums, chroma + onsets for pitched), never raw waveforms, so the
   SoundFont/GarageBand timbre difference doesn't matter.
4. **Adjust** — missed hits are added, phantom hits removed, mistimed notes
   shifted, inaudible notes boosted; then repeat until the score plateaus.

```bash
PYTHONPATH=src python -m sunofriend.cli listen path/to/hats.wav \
  --kind hat --bpm 150 --out-dir work/listened
```

`--kind` is one of: `kick snare hat cymbals toms other_kit keys piano synth lead pads bass`.

Outputs: `<kind>_listened.mid` (drag into GarageBand) and `<kind>_iterations.json`
(score per iteration). The printed per-iteration log shows F-measure / chroma
similarity, missed/extra counts, and mean timing error.

### Listen-mode setup (macOS)

```bash
brew install fluidsynth
pip install -e '.[listen]'    # numpy, librosa, soundfile, basic-pitch
# any GM SoundFont works, e.g. FluidR3_GM.sf2:
export SUNOFRIEND_SF2=/path/to/FluidR3_GM.sf2
```

`SUNOFRIEND_FLUIDSYNTH` overrides the fluidsynth binary path if it's not on PATH.

### Playing the result on a real GarageBand instrument

The final `.mid` is the deliverable: drag it into a GarageBand track and pick the
instrument. For live playback from code, enable the IAC Driver in Audio MIDI
Setup and send MIDI to it — GarageBand receives on the armed track. (GarageBand
cannot be automated for offline rendering, which is why the refine loop uses the
FluidSynth proxy instead.)

## Legacy remake mode

The current workflow is designed for EDM, hip-hop, and club tracks where drums and bass matter most. It does not try to perfectly recover the original AI-generated performance. Instead, it uses separated stems as timing guides and Moises chords as harmonic structure:

- Kick, snare, hats, cymbals, toms, and other kit stems are detected, quantized, and exported as clean drum MIDI.
- Bass MIDI follows bass/kick rhythmic activity and uses the current chord root.
- Pad/chord MIDI is generated from the Moises chord PDF using smooth voicings.
- A full multitrack MIDI file combines drums, bass, and pads.

## Usage

From the project folder:

```bash
PYTHONPATH=src python -m sunofriend.cli \
  "$HOME/Downloads/Get This Party Start_reference_24bit_44hz_target-14-G major-150bpm-440hz" \
  --out-dir work/get-this-party-start-remake \
  --style edm
```

Outputs:

- `kick_clean.mid`
- `snare_clean.mid`
- `hats_clean.mid`
- `cymbals_clean.mid`
- `toms_clean.mid`
- `other_kit_clean.mid`
- `drums_clean.mid`
- `bass_clean.mid`
- `pads_chords.mid`
- `full_arrangement.mid`
- `chords_extracted.csv`
- `quality_report.json`

Set the GarageBand project tempo to the BPM in `quality_report.json`, then import either `full_arrangement.mid` or the separate MIDI files.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```
