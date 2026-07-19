# Phase 4: Cleanup and Neural Timbre Lab

Status on 18 July 2026: **in progress**.

Phase 4 asks a narrower question than “can a model make MIDI?”: can local,
reproducible processing make difficult bass and keyboard stems more useful in
a real GarageBand arrangement than Sunofriend's deterministic transcription
and sample/DSP path? A model must beat that simpler baseline by listening as
well as metrics. It never silently replaces it.

## First private golden

The first golden is a private, local-only 236-second song in B minor at a
measured 113.008 BPM. It has bass, keys, piano, lead, strings, wind, rhythm,
drum-family, vocal and residual stems plus a chord chart. The audio and every
source-derived sample remain under ignored `work/`; none are added to the
Apache-2.0 repository.

The chord chart confirms a predominantly Bm/Em/D/A progression with later B,
E, Em7, G#m7, Gmaj7, F#m and B7 material. GarageBand should be set to **113
BPM** and **B minor** for the current MIDI.

## Increment 1 hypothesis

MuScriptor may recover more bass and keyboard note boundaries than the
baseline. Its semantic instrument roles may also make an immediate General
MIDI audition less misleading, provided role-to-program mapping changes no
notes and is kept separate from instrument identification.

## Results so far

| Stem/candidate | Notes | Strong onset F1 | Timing p95 | Chroma | Mean pitch support | Octave | Contour | Mean polyphony |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Bass baseline | 145 | 0.070 | 36.65 ms | 0.773 | 0.650 | 0.559 | 0.521 | 0.479 |
| Bass MuScriptor | 695 | 0.324 | 35.28 ms | 0.790 | 0.645 | 0.574 | 0.693 | 0.722 |
| Keys baseline | 413 | 0.223 | 34.74 ms | 0.973 | 0.646 | 0.775 | 0.393 | 0.965 |
| Keys MuScriptor | 1,062 | 0.438 | 35.30 ms | 0.957 | 0.283 | 0.434 | 0.399 | 1.860 |

These are diagnostic signals, not listening scores. MuScriptor is a credible
bass challenger: it finds substantially more attacks and improves contour
while keeping similar pitch support. The combined keys candidate finds more
attacks but loses pitch/register support and almost doubles polyphony. Its
labels—acoustic piano, electric piano, organ, synth lead, synth pad and synth
strings—support the listening impression that the separated “keys” stem is a
mixture of layers rather than one instrument.

## Concrete defect fixed

Every melodic AI role was previously written to `candidate.mid` with General
MIDI program 0. Electric bass, electric piano, organ, pads and leads therefore
all auditioned as acoustic piano, making a valid transcription sound much
worse and obscuring the model's layer labels.

AI runs now publish `candidate.programs.json`. The conservative mapping uses
program 34 (zero-based 33) for electric bass, program 5 (zero-based 4) for
electric piano, program 17 for organ, program 51 for synth strings, program 82
for synth lead and program 90 for synth pad. Drums remain on channel 10. The
record explicitly states `notes_mutated: 0` and
`raw_candidate_mutated: false`; the programs are audition hints, not claimed
GarageBand patch matches.

`sunofriend preview` also accepts `--soundfont`, so the identical performance
can be rendered through a source-derived SF2 instead of the configured GM
bank. This makes transcription and timbre independently testable.

## Listening package

All paths below are intentionally ignored local evidence:

- baseline full arrangement:
  `work/ai-bakeoff/slayyyter-dance-phase4-baseline-v1/mode_repair/full_arrangement.mid`;
- role-aware AI bass:
  `work/ai-bakeoff/slayyyter-dance-phase4-muscriptor-bass-v3-programs/20260717T215246067047Z-muscriptor-28bd8c3d/candidate.mid`;
- role-aware multi-track AI keys:
  `work/ai-bakeoff/slayyyter-dance-phase4-muscriptor-keys-v2-programs/20260717T215325885491Z-muscriptor-9592c736/candidate.mid`;
- full GM and source-sampler WAV comparisons:
  `work/ai-bakeoff/slayyyter-dance-phase4-auditions-v1/`;
- complete baseline/AI bass and baseline/AI electric-piano bundles:
  `work/ai-bakeoff/slayyyter-dance-phase4-bundles-v1/`.

Each complete bundle contains `performance.mid`, `source-reference.wav`, a
`source-instrument/sunofriend-instrument.aupreset` plus its self-contained
SF2, match reports and rendered previews. The deliberately retained partial
`bass-muscriptor` bundle records that a multi-track AI file needs an explicit
track selection; `bass-muscriptor-role` is the corrected electric-bass bundle.

Listen in this order:

1. Compare `bass-baseline.wav` with
   `bass-muscriptor-role-programs.wav`. Judge recognizable line, missing
   attacks, false busy notes, register and groove—not only bass tone.
2. Compare the four `bass-*-midi-*-samples.wav` files. This 2×2 separates the
   MIDI decision from the source-sample-bank decision.
3. Compare `keys-baseline.wav` with
   `keys-muscriptor-role-programs.wav`, then mute/solo the separate MuScriptor
   tracks in GarageBand. Do not judge the layered file as one patch.
4. Compare `keys-baseline-midi-source-samples.wav` with
   `keys-muscriptor-midi-source-samples.wav`. Listen for baked-in chords,
   abrupt sample changes and whether the source-derived timbre remains useful
   outside its extraction note.
5. In GarageBand, repeat the comparison using the bundle `.aupreset` wrappers
   and normal Library patches. FluidSynth is only a proxy for the final DAW
   decision.

## Current decisions and risks

- Keep the deterministic full arrangement as the safe starting point.
- Promote neither AI keys nor its source sampler automatically.
- Treat AI bass as the strongest challenger, pending a full-mix GarageBand
  decision.
- Preserve separate keyboard roles. A cleanup or source-separation experiment
  should target one layer and verify target-plus-residual reconstruction before
  transcription.
- Most extracted pitched samples have no stable isolated fundamental. Several
  MuScriptor bass events are shorter than 0.65 seconds, so increased onset
  recall does not automatically create a better sustained instrument.
- Source-derived instruments are private derivatives of the authorised local
  test audio and are not distributable repository assets.

## Next experiments

1. Record the listener's baseline/AI and GM/source-sampler choices in the full
   GarageBand mix.
2. Choose one short keys passage where two layers are clearly audible; test
   query-based target/residual isolation and require reconstruction equality.
3. Re-run transcription on target and residual separately. Accept cleanup only
   if it improves boundaries or pitch support without audible loss.
4. Test a monophonic bass-timbre model or resynthesis only after the bass MIDI
   choice is stable. Compare it with the exact same MIDI through the baseline
   source sampler and a normal GarageBand bass.
5. Mark generated/missing samples separately from extracted samples and retain
   model, checkpoint, licence, seed and source hashes.

No neural timbre output is promoted yet. The first increment fixes misleading
audition instrumentation, makes source-bank rendering direct, and establishes
the reproducible bass/keys listening gate needed before a cleanup model earns
integration.

## Increment 2: MIDI-informed target/residual baseline

Before installing a neural separator, Phase 4 now has a transparent DSP
baseline that any model must beat. `sunofriend midi-mask` uses one selected
MIDI track as a short time-and-pitch query, retains narrow bands around its
fundamental and harmonics, reconstructs a proposed target, and defines the
residual as the source excerpt minus that target. It never edits the input WAV
or MIDI and never promotes the target automatically.

The private golden used seconds 200–216 of the mixed keys stem and MuScriptor's
electric-piano track 2:

- 88 guide notes spanning MIDI 61–71;
- eight harmonics with 55-cent Gaussian bands;
- 4,096-sample FFT and 512-sample hop;
- target RMS 4.82 dB below the source and residual RMS 2.71 dB below it; and
- persisted PCM24 target-plus-residual maximum error `1.19209e-7`, below the
  explicit `1e-6` reconstruction threshold.

An early float-WAV build exposed a reproducibility flaw: libsndfile writes a
changing PEAK timestamp into that container. The implementation therefore uses
deterministic PCM24. Two fresh builds produced identical SHA-256 values for the
source excerpt, target, residual and excerpt MIDI.

### Transcription evidence

| Audio transcribed | Notes | Strong onset F1 | Pitch support | Supported notes | Octave | Contour | Mean polyphony |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Unchanged source excerpt | 62 | 0.294 | 0.644 | 0.806 | 0.710 | 0.383 | 1.253 |
| Harmonic target | 27 | 0.157 | 0.616 | 0.741 | 0.667 | 0.429 | 0.953 |
| 45 ms transient target | 21 | 0.163 | 0.594 | 0.810 | 0.667 | 0.526 | 1.034 |
| Harmonic residual | 46 | 0.175 | 0.703 | 0.826 | 0.739 | 0.500 | 0.652 |
| 45 ms transient residual | 46 | 0.172 | 0.689 | 0.826 | 0.717 | 0.500 | 0.694 |

The guide itself had mean pitch support `0.503` against the harmonic target
but only `0.026` against the residual, so the mask did move its tonal body into
the target. Onsets told the opposite story: guide strong-onset F1 was `0.330`
for the target and `0.439` for the residual. The harmonic mask therefore
separates pitched sustain more effectively than instrumental attacks.

A 45 ms broadband onset window modestly raised guide/target strong-onset F1 to
`0.348`, but it did not clearly solve the boundary problem and can admit other
simultaneous instruments. It remains a separately labelled challenger.

### Decision

Do not promote either target as a replacement keys stem. The experiment is
useful because it makes the failure legible: the tonal query and attack query
need different evidence. A later neural or learned cleanup method must retain
the target's pitch separation while improving attack identity, and must still
pass the exact target-plus-residual and GarageBand listening gates.

The first human listening review made the musical outcome clearer than the
metrics alone:

- the AI electric-piano guide sounded like accompaniment and lacked the
  passage's musical theme;
- MIDI transcribed from the unchanged source contained the clearest “bare
  bones” of the tune and remains the primary result;
- harmonic-target MIDI was less convincing and more accompaniment-like, but is
  retained as an optional secondary part because it contained some tune;
- transient-target MIDI had no real tune;
- harmonic-residual MIDI sounded jumbled and random; and
- transient-residual MIDI was not musically useful.

This is a failed melody-cleanup challenger, not a failed experiment. It proves
that spectral isolation and lower polyphony cannot substitute for recognition.
The reviewer's ear being drawn toward the tune is the intended listening gate,
not a bias to remove. No mask output changes the normal stem-to-MIDI default,
and the experiment is not required for every stem or instrument bundle.

The local listening page is:

`work/ai-bakeoff/slayyyter-dance-phase4-keys-midi-mask-review-v1/midi_mask_review.html`

It now explains the goal and optional scope, compares the source, AI guide,
harmonic and transient targets/residuals and the MIDI transcribed from every
audio version, and provides per-sound role/usefulness/notes controls plus an
explicit JSON export. Exporting records a decision but does not apply or
promote MIDI. The explicit six-part review from the conversation is preserved
beside it as `midi_mask_review.from-conversation.json`; unreviewed audio splits
remain marked open rather than inferred. All source-derived audio remains
ignored private work.

## Increment 3: playability before timbre similarity

The first real GarageBand keys test exposed a more basic failure than timbre
matching. The source-derived `sunofriend-instrument` omitted some performance
notes and many mapped one-shots ended too quickly. A built-in **Small Time
Piano** played the same MIDI consistently and was immediately more useful.
This is decisive listening evidence: a sampler that resembles the stem but
drops notes is not a main instrument.

Instrument Usability Gate v1 now compares each generated bank with the exact
selected MIDI performance. It measures key/velocity coverage, audible-attack
support and effective sample duration after transposition. It publishes a
MIDI/WAV audition containing every distinct performance pitch and four velocity
probes, and records zero changes to source MIDI, sample audio or mappings.
Pitched banks that fail are labelled `texture-only`; a complete GarageBand/GM
patch becomes the primary strategy and the source bank is kept only as an
optional quiet layer. Passing banks remain `review-required`, never
automatically accepted.

The existing Slayyyter keys baseline explains the listening failure: its MIDI
spans 35–95 while the generated zones span only 44–87, leaving 25 of 413 notes
guaranteed silent. Many remaining one-shots are too short for their MIDI notes,
there are no active sustain loops and most samples lack a stable isolated pitch.
The electric-piano challenger is narrower still at 51–80 and leaves 55 of 413
notes silent. These banks may retain useful source texture, but neither should
replace a complete keyboard instrument.

The rendered SF2 usability audition independently confirmed the zone result:
MIDI pitches 35, 38, 40, 42, 88, 90, 93 and 95 were below −80 dB, exactly the
eight unique unmapped pitches reported by the gate. The original MIDI and the
bundle's copied `performance.mid` have identical SHA-256 values.

The immediate GarageBand choice for this arrangement is **Small Time Piano**,
with **Classic Electric Piano** or **Different Phases Clav** as brighter family
alternatives. This preference came from the user's full-arrangement A/B, not an
automatic similarity score. Local AI remains useful later for role-constrained
patch retrieval, effects suggestions, preference learning and resynthesis, but
only after deterministic coverage and duration checks pass.

The first gated run also exposed a role-catalogue error: generic `keys` still
allowed General MIDI synth-lead/pad programs, so raw similarity selected Lead 2
(sawtooth). The keys shortlist is now restricted to programs 1–24—piano,
chromatic keyboard and organ families. `synth` and `pads` retain their own
candidate sets. This is a deterministic musical prior that also constrains the
optional OpenL3 ranking; it does not claim to identify the original patch.

The corrected fresh bundle is under ignored local evidence at
`work/ai-bakeoff/slayyyter-dance-phase4-keys-playability-gate-v2-openl3/`.
The explainable order is Electric Piano 2, Drawbar Organ, Electric Grand Piano,
Acoustic Grand Piano and Church Organ. The independent OpenL3 order starts Rock
Organ, Percussive Organ and Celesta. These disagreements are useful shortlist
evidence, not a reason to override the real GarageBand preference for Small
Time Piano. The copied performance MIDI has the exact source SHA-256, and the
OpenL3 model/hash/evidence remain additive in the bundle.

## Increment 4: explicit patch preference history

The Small Time Piano decision is now durable local evidence rather than a note
that later runs can forget. `instrument-feedback` records the explicit patch,
source, preferred/acceptable/rejected decision, full-mix or solo context,
comparisons and listening note. It accepts only an existing Instrument Bundle
v1 and pins its report, recipe and performance MIDI hashes while declaring zero
changes to the bundle, MIDI, match order, selection and playability gate.

`instrument-profile` builds a fresh byte-deterministic profile only from the
reviewed feedback paths explicitly supplied. It has no hidden store or file
discovery. Full-mix decisions are weighted more than solo auditions, and
rejections remain negative evidence instead of disappearing. The profile ranks
history separately for each role.

`instrument-bundle --preference-profile` copies the exact profile into the
fresh bundle and shows a positive history-first patch in the GarageBand steps.
It leaves factory, GM and OpenL3 rankings and the portable program hint
unchanged, selects no patch, changes no MIDI and cannot bypass the Instrument
Usability Gate. For the current keys evidence, the advisory history-first patch
is Small Time Piano; the source sampler remains `texture-only`.

The ignored local evidence is under
`work/ai-bakeoff/slayyyter-dance-phase4-instrument-feedback-v1/`; the reviewed
feedback SHA-256 is
`b4ba10f58ca5b5310a2041a9a888c45d2064124df2a0a1d7d9eac38fd2710089`
and two independently written profiles are byte-identical at SHA-256
`6ff152ecccde09ce214cf889e4e5f6ecdc9adb2e34f59df5c5a65548bbd90b53`.
The profiled bundle is
`work/ai-bakeoff/slayyyter-dance-phase4-keys-playability-gate-v3-profiled-openl3/`.
Its copied profile and performance MIDI match their sources exactly. Factory,
GM and OpenL3 ranking arrays, the Electric Piano 2 portable hint and the
complete source-usability report are identical to the unprofiled v2 bundle.

## Stabilization decision before Increment 5

The foundations now reproduce safely, but the musical success condition has
not been met: unchanged-source MIDI remains better than the cleanup derivatives
and Small Time Piano remains better than the source-derived keys bank. The
[Phase 4 stabilization review](PHASE4_STABILIZATION_REVIEW.md) compares every
planned goal with actual execution, records the code cleanup and defines the
gate for the next learned-separation or timbre experiment.

## Increment 5: pinned learned bass cleanup challenger

The first post-stabilization experiment deliberately moved away from layered
keys. Seconds 192–208 of the private Slayyyter bass stem contain a clear,
high-energy bass line and give cleanup a fairer monophonic target. The success
test was declared before implementation: learned cleanup must be reproducible,
reconstruct the input with its residual, improve the strongest available MIDI
transcriber rather than only the Basic Pitch baseline, and then win by ear.

`sunofriend ai-cleanup` now provides the isolated learned boundary. It uses
`demucs==4.0.1`, official `htdemucs` signature `955717e8`, CPU inference,
zero random shifts and split overlap `0.25`. The external checkpoint is accepted
only at full SHA-256
`8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4`.
The worker opts into PyTorch pickle deserialisation only after that exact hash
passes. Code is MIT; no separate pretrained-weight licence was identified in
the official repository, so the checkpoint and outputs remain private and are
never vendored or redistributed.

### Reconstruction and repeatability

- Source excerpt RMS: `0.249457120792`.
- Learned bass target RMS: `0.243379136914` (`-0.214 dB` from source).
- Residual RMS: `0.045995822551` (`-14.686 dB` from source).
- Persisted PCM24 target-plus-residual maximum error: `0.0` against threshold
  `1e-6`.
- Clipped target samples: `0`.
- Two independent runs produced identical source-excerpt, float32 target-array,
  target-WAV and residual-WAV hashes.
- The source and checkpoint hashes were unchanged after both runs; automatic
  promotion remained false.

### Same-source transcription comparison

Every metric below evaluates the candidate MIDI against the same unchanged
16-second source excerpt. Full-song MuScriptor has surrounding context, while
the other MuScriptor candidates receive only the excerpt.

| Candidate | Notes | Chroma | Pitch support | Supported | Octave | Contour | Strong onset F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MuScriptor unchanged source, full context | 44 | 0.826 | 0.659 | 0.795 | 0.545 | 0.814 | 0.170 |
| MuScriptor unchanged 16-second source | 39 | 0.821 | 0.656 | 0.744 | 0.564 | 0.868 | 0.122 |
| MuScriptor learned target | 41 | 0.818 | 0.656 | 0.805 | 0.585 | 0.700 | 0.121 |
| MuScriptor MIDI-mask DSP target | 8 | 0.705 | 0.518 | 0.500 | 0.625 | 0.167 | 0.024 |
| Basic Pitch unchanged source | 25 | 0.816 | 0.506 | 0.640 | 0.400 | 0.708 | 0.121 |
| Basic Pitch learned target | 24 | 0.812 | 0.549 | 0.708 | 0.417 | 0.652 | 0.137 |
| Basic Pitch MIDI-mask DSP target | 22 | 0.827 | 0.581 | 0.727 | 0.500 | 0.619 | 0.123 |

Demucs is a credible challenger, not a metric winner. It improves MuScriptor's
short-input supported-note ratio and octave accuracy, while slightly reducing
chroma, contour direction and onset F1. The DSP target helps several Basic
Pitch metrics but collapses MuScriptor to eight notes. The full-context
unchanged-source MuScriptor guide remains the technical leader overall.

The listening page is:

`work/ai-bakeoff/slayyyter-dance-phase4-demucs-bass-review-v1/ai_cleanup_review.html`

It explains the goal, compares source/target/residual audio, gives the decisive
MuScriptor and supporting Basic Pitch MIDI A/Bs, and exports an explicit
12-sound review. The in-app browser blocks new local `file://` navigation, so
open it in a normal browser. Static validation confirms all 12 audio links,
feedback controls and export JavaScript are present. No Phase 4 primary changes
until that listening review is complete.

## Increment 6: one bass stem, two audible roles

The completed cleanup review resolved the first listening gate. The listener
selected the learned target as the main cleanup and described the same musical
structure throughout the useful alternatives: a deep synth-bass/keyboard body
and a shorter plucked synth/guitar-like line. The learned target retained both
but softened the pluck; the learned residual was still musical and exposed the
pluck more clearly. This is stronger evidence than a model family label, but it
still does not prove the original physical instruments.

### Note-level evidence

`instrument-match` profiled the 41-note learned-target MuScriptor candidate
against the accepted target audio with the pinned OpenL3 model plus the existing
explainable timbre features. On this focused excerpt it found two candidate
timbre groups:

- body candidate `I1`: 30 notes, median duration `0.504478` seconds, pitch
  range 28–40;
- transient candidate `I2`: nine notes, median duration `0.134487` seconds,
  pitch range 33–54; and
- two retained transient outliers.

Those groups are consistent with the listening description. They are not an
automatic role decision: cluster `I1` is supplied explicitly to the new command
and the complement retains `I2`, both outliers and any unprofiled notes.

MuScriptor was also run independently on the learned residual. It produced 13
notes and passed the existing candidate-quality gate. Several onsets contain
two simultaneous pitches an octave apart. This matters because the main target
candidate is effectively monophonic; dividing it can assign different sounds
but cannot recover genuinely overlapping lines.

### Reviewable outputs

`sunofriend midi-role-split` now writes two different hypotheses:

1. a strict 30+11 partition of the 41-note primary. Its union preserves every
   pitch, onset, duration and velocity exactly;
2. a 30+13 body-plus-independent-residual challenger that can express overlap
   but may contain bleed or octave errors.

It also preserves the unchanged primary, body-only, both pluck-only candidates,
source audio references, a hash-pinned report and a local review export. The
rendered programs—Synth Bass 2 for the body and Muted Guitar for the
pluck—are deliberately contrasting proxies. They are not claimed patch matches,
and the user should choose normal complete GarageBand patches after deciding
which notes belong to each role.

The listening page was:

`work/ai-bakeoff/slayyyter-dance-phase4-bass-two-role-review-v3/midi_role_split_review.html`

The completed review heard both roles in the original target, marked the
body-only, primary complement and strict partition as useful main evidence,
and kept the learned residual audio as secondary evidence. The independently
transcribed residual MIDI and its combined challenger were diagnostic only.
The overall decision was therefore `keep_primary`: component separation was
informative, but it did not improve the arrangement enough to replace the
unchanged 41-note MuScriptor line.

`midi-role-split-resolve` verified every reviewed choice and every pinned input
and artifact, then copied `primary-unchanged.mid` byte-for-byte to:

`work/ai-bakeoff/slayyyter-dance-phase4-bass-two-role-resolution-v1/recommended.mid`

Both files have SHA-256
`540634d7578c1941a7dd8dd6eedb5ddd1f8ab0bcfcfa453f5c535c0cc48f1b14`.
The resolution changes no notes and deletes no alternatives. This increment
changes Phase 4's framing: broad learned cleanup, intra-stem role analysis and
the final arrangement choice are separate tasks. With the bass MIDI fixed, the
next experiment can compare timbre or resynthesis on identical notes instead
of confounding sound quality with another transcription.

## Increment 7: fixed-MIDI harmonic-plus-noise baseline

The reviewed role decision satisfies the timbre gate: the performance is now
the unchanged 41-note MuScriptor primary at `113.000096` BPM, SHA-256
`540634d7578c1941a7dd8dd6eedb5ddd1f8ab0bcfcfa453f5c535c0cc48f1b14`.
`timbre-resynthesis` changes no pitch, onset, duration or velocity and compares
three sound-generation strategies on that exact performance:

1. General MIDI Synth Bass 2 as a dependable complete-patch control;
2. the earlier nine-zone source-derived bass SF2; and
3. one source-fitted harmonic-plus-noise resynthesis profile.

The third candidate is deliberately a transparent DSP baseline, not a neural
claim. It follows the interpretable harmonic-plus-filtered-noise structure used
by [DDSP](https://github.com/magenta/ddsp), but works at the source's native
44.1 kHz in the existing lightweight runtime. The official Apache-2.0
[MIDI-DDSP](https://github.com/magenta/midi-ddsp) project is relevant future
evidence: it accepts monophonic MIDI and includes a double-bass model. Direct
integration is not the next safe step because its repository is archived, targets
TensorFlow 2.7/Python 3.8 and explicitly reports that installation on an M1 Mac
does not work. A current local neural adapter must therefore be evaluated
separately rather than silently introducing that legacy stack.

### Slayyyter bass result and listening decision

The fitted profile used all 41 notes across MIDI pitches 28–54. Its 16-harmonic
distribution is dominated by the first two partials (`0.319829`, `0.331503`),
with harmonic brightness `3.010815`, noise mix `0.040092` and fitted sustain
ratio `1.0`. These are synthesis parameters, not instrument-identity scores.

All three candidates passed the explicit `-60 dBFS` functional silence check
on all 41 notes:

| Candidate | Audible notes | Minimum note RMS | Level-match caveat |
| --- | ---: | ---: | --- |
| Synth Bass 2 complete patch | 41/41 | -16.203 dBFS | Peak-limited; active RMS remains below source |
| Earlier source sampler | 41/41 | -15.788 dBFS | Peak-limited; active RMS remains below source |
| Harmonic-plus-noise resynthesis | 41/41 | -12.445 dBFS | Exact active-RMS match; no peak limiting |

This functional test established playability and a fair listening level, but
did not show that any candidate sounded realistic or musically better. The
local review page was:

`work/ai-bakeoff/slayyyter-dance-phase4-fixed-midi-timbre-review-v2/timbre_resynthesis_review.html`

The completed, hash-consistent review export has SHA-256
`8c9d388e13bbbe1740890a5d6fb73046cb856e609309a126ef609a09b30374ac`.
It recorded:

| Candidate | Tone | Consistency | Use | Listener note |
| --- | --- | --- | --- | --- |
| Synth Bass 2 complete patch | ballpark | uneven | main | Slightly different melody impression and tone |
| Earlier source sampler | far | missing | reject | Very different |
| Harmonic-plus-noise resynthesis | ballpark | complete | main | Different, but consistently different |

The overall decision was `prefer_gm`: Synth Bass 2 had the nearest tone and was
consistent enough to remain the main control. Harmonic-plus-noise resynthesis
is retained as a useful alternative/layer, but it did not beat the complete
patch and is not promoted to a generated GarageBand instrument. The earlier
source sampler is rejected as a main instrument for this performance.

This result exposes why the two gates must stay separate: all three renders
passed the numeric 41/41 audibility check, yet the listener still perceived the
GM response as uneven and the sampler as missing/inconsistent. A later neural
method must beat the same fixed-MIDI complete patch in listening, not merely
cross a silence threshold.
