# Vocal melody extraction

Vocal pitch is continuous; MIDI notes are discrete. Sunofriend treats vocal
MIDI as a documented musical interpretation of measured pitch, not a claim
that a sung waveform contains perfectly rectangular notes.

## What the audio contains

A vocal waveform shows air-pressure amplitude oscillating thousands of times
per second. It is useful for level and attack timing, but note names are much
clearer in a fundamental-frequency (F0) contour or spectrogram:

- Voiced vowels contain a fundamental plus harmonics shaped by the mouth and
  throat.
- Consonants and breaths are often noisy or unpitched. They can mark an
  articulation without supplying a note pitch.
- Vibrato moves continuously around a target pitch.
- Scoops and portamento move between targets without an objective instant at
  which one note becomes the next.
- A syllable may contain several notes, while several syllables may repeat one
  pitch.

Starting a MIDI instrument on the same pitch can produce audible fusion,
chorusing or beating, but it does not guarantee physical resonance. The voice
has different harmonics, expressive intonation and timing. If the recording is
not tuned to A=440, the MIDI instrument must also be detuned to match.

## Sunofriend's process

`vocal-melody` keeps the continuous evidence and the discrete interpretation
separate:

1. Gate the original signal at its real level. A noise-floor stem is reported
   as `no-evidence`; it is never normalised into invented notes.
2. Load stereo phase-safely so opposite-polarity material does not disappear
   during mono analysis.
3. Estimate a frame-by-frame F0 contour with pYIN for a lead vocal. Backing
   vocals also use range-limited polyphonic Basic Pitch candidates.
4. Convert Hz into fractional MIDI using the source's actual concert-A tuning.
5. Smooth within voiced regions and use hysteresis/persistence to prevent
   vibrato and slides becoming a chromatic staircase.
6. Use unvoiced gaps, pitch plateaus, dynamics and spectral attacks to decide
   note boundaries. Brief consonant gaps can be bridged; a supported same-pitch
   reattack remains a new note.
7. Publish several interpretations instead of hiding ambiguous decisions.
8. Keep per-note provenance, the full F0 contour and measured comparison
   statistics for subsequent listening and adjustment.

Lyrics are not encoded. Consonants affect articulation evidence only; words do
not decide pitch.

## Output choices

For a lead vocal:

| Variant | Purpose |
| --- | --- |
| `contour_clean` | Recommended stable melody with original expressive timing |
| `observed_strict` | Only high-voicing-confidence pitch evidence |
| `instrument_simple` | Removes short ornaments for guitar, sax, clarinet, trumpet or mallet instruments |
| `gentle_quantized` | Moves only boundaries already close to the warped beat subdivision |
| `uncertain` | Low-confidence voiced fragments kept outside the main melody |
| `concert_pitch` | Main notes at ordinary A=440, without the source-tuning bend |

For backing vocals:

| Variant | Purpose |
| --- | --- |
| `dominant_line` | Strongest continuous monophonic backing voice |
| `top_line` | Highest coherent voice |
| `harmony_stack` | All supported simultaneous backing notes |
| `uncertain` | Weak, excess or likely harmonic-ghost candidates |
| `concert_pitch` | Dominant line without source-tuning compensation |

The main MIDI and normal variants carry a channel-wide tuning bend. The
concert-pitch variant deliberately does not. GarageBand patch choice remains a
creative decision after import.

## Command

Metadata is inferred from the parent-folder name when possible:

```bash
.venv/bin/sunofriend vocal-melody \
  "/path/to/My Song-vocals-G major-93bpm-441hz.wav" \
  --role lead \
  --out-dir work/my-song-vocals/lead

.venv/bin/sunofriend vocal-melody \
  "/path/to/My Song-backing_vocals-G major-93bpm-441hz.wav" \
  --role backing \
  --out-dir work/my-song-vocals/backing
```

Use explicit values when the folder is not named with metadata:

```bash
.venv/bin/sunofriend vocal-melody path/to/vocals.wav \
  --role lead --bpm 85 --tuning-hz 429 --key "C major" \
  --metronome path/to/metronome.wav \
  --chords-pdf path/to/chords.pdf \
  --out-dir work/song-vocals/lead
```

The chord chart is recorded for audit, but v1 does not force observed vocal
notes onto an untimed chart. This protects chromatic melody notes and avoids
turning uncertain harmony timing into confident pitch changes.

## Tuning and GarageBand

MIDI note 69 normally means A=440. A recording at A=429 is about 43.83 cents
flat. Sunofriend therefore emits the stem-aligned MIDI with an explicit
channel pitch bend and also emits a concert-pitch alternative.

For the stem-aligned file:

1. Set GarageBand to the BPM reported in `vocal_summary.json`.
2. Import the MIDI and audio at the same project origin.
3. Leave quantisation off for `contour_clean`.
4. Confirm the chosen software instrument honours imported pitch-bend data.
5. If a patch ignores it, use GarageBand's fine-tune control with the cents
   value from `garageband_fine_tune_cents`.

## Evaluating and iterating

`vocal_analysis.json` reports, per variant:

- voiced-contour coverage;
- precision of MIDI-active frames against voiced frames;
- median and 90th-percentile pitch error in cents;
- proportion of covered contour within 50 cents;
- pitch range, note count and total note duration;
- whether a melody variant is monophonic.

These metrics detect omissions, hallucinated notes, mistuning and excessive
fragmentation, but they do not decide the best musical abstraction. Iterate in
this order:

1. Compare `contour_clean` with the isolated vocal at the same origin.
2. Check pitch mistakes before changing timing.
3. Check merged/split notes and repeated same-pitch articulations.
4. Compare `instrument_simple` for recognisability with the vocal muted.
5. Compare exact and gentle timing in GarageBand.
6. For backing vocals, audition dominant, top and full harmony separately.
7. Keep a short manually annotated golden passage for future regression tests.

An external or manually played reference MIDI can be useful as a scoring aid,
especially for selecting a backing voice. It should not silently supply notes
that are absent from the stem; any such repair must be labelled inferred.

