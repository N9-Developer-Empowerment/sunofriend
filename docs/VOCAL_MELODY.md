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
3. Estimate a frame-by-frame F0 contour with pYIN and project independent
   Basic Pitch note hypotheses onto the same timeline. Agreement contributes
   a consensus frame; a conflicting single-tracker result is downgraded rather
   than silently selected. `--tracker-mode pyin` retains the original path.
   Backing vocals also use range-limited polyphonic Basic Pitch candidates.
4. Convert Hz into fractional MIDI using the source's actual concert-A tuning.
5. Smooth within voiced regions and use hysteresis/persistence to prevent
   vibrato and slides becoming a chromatic staircase.
6. Use unvoiced gaps, pitch plateaus, dynamics and spectral attacks to decide
   note boundaries. Brief consonant gaps can be bridged; a supported same-pitch
   reattack remains a new note.
7. Compare repeated clean phrases. A lenient source note can be promoted only
   when at least three clean same-pitch anchors establish a repeated offset;
   the repair never creates a note from chords or key alone.
8. Publish several interpretations instead of hiding ambiguous decisions.
9. Keep per-note provenance, the full F0 contour and measured comparison
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
| `phrase_repaired` | Adds weak source-observed omissions supported by a repeated clean phrase; emitted only when a repair exists |
| `guide_assisted` | Optional hummed rhythm/contour aligned to the song and retained only where source F0 supports it |
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

## Independent tracker evidence and experimental consensus

The normal `vocal-melody` command is a creative workflow. Use
`vocal-trackers` when the question is which pitch tracker observed what:

```bash
.venv/bin/sunofriend vocal-trackers path/to/vocals.wav \
  --role lead --bpm 119 --tuning-hz 440 \
  --out-dir work/song-vocal-trackers
```

That command preserves separately scored `pyin.evidence.json` and
`basic-pitch.evidence.json` records plus their GarageBand-ready candidate
MIDI. Basic Pitch remains raw and may be polyphonic; pYIN keeps continuous F0
plus a named deterministic note decoder. A repeat never overwrites an existing
run.

After a standalone RMVPE run has produced `rmvpe.frames.json`, opt into a
three-way comparison:

```bash
.venv/bin/sunofriend vocal-trackers path/to/vocals.wav \
  --role lead --bpm 119 \
  --rmvpe-frames work/rmvpe-runs/RUN_ID/rmvpe.frames.json \
  --game-candidate work/game-runs/RUN_ID/candidate.json \
  --out-dir work/song-vocal-trackers
```

The RMVPE record must remain beside its `candidate.json` and `run.json`, and
the recorded source SHA-256 must exactly match the supplied WAV. Consensus is
time-aligned to pYIN frames, requires two agreeing pitched trackers within 70
cents, and retains every per-frame observation in `consensus.evidence.json`.
It can select Basic Pitch plus RMVPE when both disagree with pYIN; pYIN-only
evidence is retained below clean confidence, and unresolved conflicts are
explicit. `consensus.candidate.mid` is always `review-required`. Compare its
evaluation and listen to it, but do not assume voting is musically superior—
especially for polyphonic backing vocals where different trackers may follow
different genuine voices.

`--game-candidate` is optional and requires `--rmvpe-frames`. Sunofriend checks
the source and checkpoint SHA-256 values against both inputs' adjacent,
completed immutable run manifests. It then treats Basic Pitch and GAME only
as boundary proposals. A proposal is accepted when pYIN and RMVPE are voiced,
agree within 70 cents, cover enough of the note with stable pitch, and support
both edges. The output pitch is the equal midpoint of pYIN and RMVPE; their
unrelated confidence scales do not vote on pitch or provider selection.

The command publishes separate `boundary-basic-pitch.candidate.mid` and
`boundary-game.candidate.mid` variants plus a non-overlapping monophonic
`boundary-repair.candidate.mid`. `boundary-repair.evidence.json` preserves
every proposal, rejection reason, selected provider and confidence-ranked
phrase. All three are `review-required`. Raw Basic Pitch, pYIN, RMVPE and GAME
artifacts remain authoritative and unchanged. In particular, do not replace a
backing-vocal harmony stack with this monophonic experiment: the first backing
golden retained only six notes and no supported notes, while the lead result
provided a useful 23-note phrase-review candidate.

## Hummed guide and visual correction

When a stem contains competing voices, record a rough hum while listening from
the same song origin. It may start up to eight seconds early or late and may be
in another octave or comfortable register:

```bash
.venv/bin/sunofriend vocal-melody path/to/vocals.wav \
  --role lead --bpm 119 \
  --guide path/to/hummed-guide.wav \
  --prefer-guide \
  --out-dir work/song-vocals/guided-lead
```

Sunofriend searches the guide offset and one constant semitone transposition.
It then takes timing and intended contour from the hum but measures pitch
again in the source stem. Guide notes with insufficient source voicing or more
than 1.5 semitones of disagreement are omitted. `guide_alignment` in
`vocal_summary.json` records the chosen offset, transposition and score.

### Short excerpt workflow

A full-song hum is not required. Short, repeated submissions are usually
easier and avoid tempo drift over several minutes. For every 10–15 second
section, keep:

1. a reference excerpt;
2. a hum, whistle, `oo`/`la` recording, or simple one-note-instrument version
   beginning at the same phrase boundary; and
3. the approximate start time of the excerpt in the full song.

The timestamp can come from GarageBand, QuickTime, or another player and only
needs to be within two seconds:

```bash
.venv/bin/sunofriend vocal-melody path/to/vocals.wav \
  --role lead --bpm 119 \
  --guide-snippet guides/verse-reference.wav guides/verse-hum.wav 42.5 \
  --guide-snippet guides/chorus-reference.wav guides/chorus-hum.wav 87.0 \
  --prefer-guide \
  --out-dir work/song-vocals/snippet-guided-lead
```

`--guide-snippet` is repeatable and takes `REFERENCE_WAV HUM_WAV START_SECONDS`.
Five to thirty seconds is accepted without a duration warning; 10–15 seconds
is the recommended working size. A vocal-stem excerpt is the clearest
reference, but a vocal-dominant song excerpt is still useful for the person
recording the guide because final pitch acceptance is measured against the
full vocal stem, not the excerpt.

Sunofriend searches ±2 seconds around each timestamp and estimates a separate
constant register change for every hum. It publishes:

- `snippet_guides`: only accepted notes from the submitted excerpts;
- `snippet_patched`: the automatic full-song melody with only overlapping
  automatic notes replaced by accepted snippet notes.

`--prefer-guide` selects `snippet_patched`, not the incomplete snippets-only
track. Failed snippets do not erase the automatic melody. Each snippet's file
paths, durations, requested start, chosen alignment, transposition, detected
notes, accepted notes and warnings are recorded under `guide_alignment` in
`vocal_summary.json` and in the correction JSON.

Practical recording guidance for non-singers:

- listen through headphones so the reference does not leak into the guide;
- use a close microphone and a steady `oo`, `la`, whistle, kazoo, or one-note
  keyboard/guitar line;
- sing in any comfortable octave—Sunofriend estimates the register difference;
- concentrate on note changes and rhythm rather than vocal tone or lyrics;
- submit the chorus and other repeated hooks first, then add difficult verses;
- leave sections without a clear melody to the automatic consensus and visual
  correction workflow.

Every normal run creates:

- `melody_correction.html`: a local waveform/F0/piano-roll view with pitch,
  timing, split, merge and delete controls;
- `melody_corrections.json`: the initial, directly applicable correction
  document.

Open the HTML file locally, audition the referenced stem, export the reviewed
JSON, and apply it without overwriting an existing MIDI:

```bash
.venv/bin/sunofriend melody-apply \
  path/to/melody-corrections-edited.json \
  --out work/song-vocals/reviewed-lead.mid
```

The correction document retains BPM, source tuning, role, channel and program,
so the result carries the same GarageBand fine-tuning bend. It also writes a
`.correction.json` audit beside the new MIDI. Use `--no-correction-report` only
when the HTML/JSON artifacts are not wanted.

### Phrase review from independent trackers

After `vocal-trackers` has published an agreed-F0 boundary repair, build a
fresh local recognition-first package:

```bash
.venv/bin/sunofriend melody-review \
  work/song-vocal-trackers/RUN_ID \
  --out-dir work/song-vocal-phrase-review
```

`melody-review` verifies the run, source WAV, Basic Pitch evidence, combined
MIDI and boundary evidence by SHA-256 before writing anything. It is lead-only
in v1; backing vocals retain their polyphonic Basic Pitch and harmony stack.
Each ranked region includes three explicit alternatives—raw Basic Pitch,
GAME boundaries over agreed pitch, and the combined repair—plus the source,
neutral MIDI, source-plus-MIDI audio, piano roll and phrase-local evaluation.
No-evidence alternatives remain visible as zero-note silence.

Open `melody_phrase_review.html`, review the weakest regions first, select one
alternative per phrase (or explicitly accept all current combined defaults),
then export `melody-corrections-reviewed.json`. Apply that file with
`melody-apply`. The adjacent unreviewed seed cannot be applied: the command
requires reviewed choices and a matching source hash, and carries those
choices into the final `.correction.json` audit. This is a human selection
layer; aggregate metrics never choose the melody automatically.

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

Diagnostics also list the tracker sources, number of consensus frames,
repeated-phrase promotions and whether a hummed guide was used.

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
