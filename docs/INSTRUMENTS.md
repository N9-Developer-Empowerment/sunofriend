# Instruments, sound matching and stem-derived sample packs

Instrument selection is an arrangement decision, not a final transcription
step. The same notes, timing and velocities can feel entirely different when
the patch changes its attack, decay, brightness, noise, articulation or
register. Sunofriend therefore produces audition evidence and keeps the final
choice with the musician.

## Instrument Bundle v1: sound and match together

A Standard MIDI file cannot contain the actual GarageBand patch audio.
`instrument-bundle` therefore packages the editable performance, a portable
source-derived sound where possible, the installed-sound shortlist and
listening references without conflating them:

```bash
sunofriend instrument-bundle \
  "/absolute/path/to/song-bass.wav" \
  "/absolute/path/to/bass_listened.mid" \
  --kind bass \
  --name "Song Walking Bass" \
  --out-dir work/instrument-bundles/song-bass
```

The default output is:

```text
work/instrument-bundles/song-bass/
├── performance.mid
├── source-reference.wav
├── instrument_bundle.json
├── instrument_recipe.json
├── preference-profile.json              # only with --preference-profile
├── README.md
├── matches/
│   ├── instrument_matches.json
│   ├── GARAGEBAND_AUDITION.md
│   ├── source_event_clusters.json
│   ├── source_event_clusters.svg
│   ├── source_event_dynamics.json       # advisory layers/alternate samples
│   ├── source_event_dynamics.svg        # source-level timeline review
│   ├── gm_drum_family_mapping.json       # drum roles when GM is enabled
│   ├── drum_family_mapping.proposed.mid  # review copy; original preserved
│   ├── drum_family_mapping.proposed.wav
│   ├── drum_note_auditions/...           # assigned channel-10 one-shots
│   ├── gm_auditions/...
│   ├── openl3_embedding_evidence.json # only with --embedding-model
│   └── gm_embedding_auditions/...     # only with --embedding-model
├── source-instrument/
│   ├── sunofriend-instrument.aupreset
│   ├── sunofriend-instrument.sf2
│   ├── sunofriend-instrument.sfz
│   ├── instrument_usability.json
│   ├── instrument-usability-audition.mid
│   ├── instrument-usability-audition.wav
│   └── samples/...
└── previews/
    ├── source-derived-performance.wav
    ├── best-matched-gm.wav
    ├── best-openl3-matched-gm.wav      # only with --embedding-model
    ├── gm-drum-family-proposal.mid     # drum roles when GM is enabled
    └── gm-drum-family-proposal.wav
```

`instrument_recipe.json` records the top local factory asset, ranked
alternatives, portable GM program hint, carried sample bank and exact
GarageBand handoff. Factory assets are recommendations only; Apple audio is
not copied. The source-derived instrument contains audio from the authorised
stem and remains subject to its licence and the bleed/effects warnings below.

The recipe separates build status from musical usability. A source bank can be
successfully built yet classified `texture-only`; in that case the bundle uses
a complete GarageBand/GM instrument as the primary strategy and retains the
source sampler only as an optional layer. `review-required` means that coverage
and duration checks passed, not that its tone has been accepted automatically.

A stem without isolated playable notes produces a `partial` bundle rather
than failing the whole handoff: MIDI, source reference and match evidence stay
available, while `source_instrument_error` explains why no SF2 was created.
Use `--no-source-audio` for a smaller non-portable bundle,
`--no-source-instrument` when sampling is not authorised, or `--no-gm` when
FluidSynth previews are unavailable.

## Local patch feedback and personal ranking

Sound matching cannot know whether a patch actually worked in the final mix.
Sunofriend can therefore retain an explicit GarageBand or other DAW decision
without silently learning from files or changing its deterministic evidence:

```bash
sunofriend instrument-feedback work/instrument-bundles/song-keys \
  --patch "Small Time Piano" \
  --patch-source garageband-library \
  --decision preferred \
  --context full-mix \
  --compared-with sunofriend-instrument \
  --notes "Consistent tone and every note audible" \
  --out work/instrument-feedback/song-keys-small-time-piano.json
```

The input must be an existing Instrument Bundle v1 directory or its
`instrument_bundle.json`. The reviewed feedback pins the bundle report, recipe
and copied performance MIDI by SHA-256, records the exact role and listening
context, and declares zero bundle, MIDI, ranking, selection and usability-gate
effects. Use a fresh output. `preferred`, `acceptable` and `rejected` are all
valid explicit evidence; `full-mix` and `solo` remain distinct.

Build a profile only from the feedback files deliberately supplied on the
command line:

```bash
sunofriend instrument-profile \
  work/instrument-feedback/song-keys-small-time-piano.json \
  work/instrument-feedback/another-keys-choice.json \
  --out work/instrument-feedback/my-patch-profile.json
```

The deterministic profile gives preferred/acceptable/rejected counts and a
relative per-role history score. Full-mix evidence has weight 1, solo evidence
has weight 0.5; decisions have weights 1, 0.5 and −1 respectively. These are
transparent preference weights, not confidence or instrument recognition.
Duplicate input hashes, unreviewed feedback, mutated policies and existing
output files are rejected.

Pass the profile explicitly to a fresh bundle:

```bash
sunofriend instrument-bundle STEM.wav PART.mid \
  --kind keys \
  --preference-profile work/instrument-feedback/my-patch-profile.json \
  --out-dir work/instrument-bundles/song-keys-profiled
```

The exact profile is copied to `preference-profile.json` and its source path and
hash are recorded in `instrument_recipe.json`. A positive history-first patch
is shown before the generic shortlist in the GarageBand instructions. It does
not reorder factory, GM or OpenL3 matches, alter the portable program hint,
select a patch or bypass a `texture-only` decision. A complete playable patch
remains mandatory; the musician still confirms its musical fit.

## What is available on this Mac?

Run:

```bash
sunofriend instrument-inventory \
  --out work/instruments/installed.json
```

The report lists:

- GarageBand factory sampler assets already installed under the system sound
  library;
- GarageBand and Logic `.exs` sampler-instrument definitions, including their
  categories and searchable preset names;
- installed GarageBand/Logic drum sample groups;
- Apple and third-party Audio Unit music devices exposed by `auval`; and
- the GarageBand version and Audio Unit component directories.

It deliberately reports only representative factory sample paths rather than
thousands of internal files, while retaining the complete installed sampler
preset catalogue. Sunofriend reads those assets for local analysis; it does
not alter or redistribute them.

GarageBand can download more Apple content from **GarageBand > Sound Library >
Download All Available Sounds**. It also supports compatible 64-bit Audio Unit
plug-ins. Install third-party components only from a supplier you trust, follow
its licence, restart GarageBand, and enable the instrument in GarageBand's
Audio/MIDI settings if macOS has not validated it automatically.

Apple references:

- [Download additional sounds and loops for GarageBand](https://support.apple.com/en-euro/101959)
- [Use Audio Units plug-ins on Mac](https://support.apple.com/en-gb/102239)
- [GarageBand supports 64-bit Audio Units](https://support.apple.com/en-us/101846)
- [AVAudioUnitSampler loads DLS and SF2 sound banks](https://developer.apple.com/documentation/avfaudio/avaudiounitsampler/loadsoundbankinstrument%28at%3Aprogram%3Abankmsb%3Abanklsb%3A%29)

## Find instruments by sound

Given a source stem and the MIDI already aligned to it:

```bash
sunofriend instrument-match \
  "/absolute/path/to/song-bass.wav" \
  "/absolute/path/to/bass_listened.mid" \
  --kind bass \
  --out-dir work/instruments/bass
```

The command uses two default evidence paths and one optional learned path:

1. **Installed factory assets.** MIDI-aligned excerpts from the stem are
   compared with readable GarageBand/Logic sample recordings. Audio features
   contribute 92% of the ranking and a deliberately weak role/name prior
   contributes 8%.
2. **Rendered performance proxies.** For pitched parts, the complete MIDI is
   rendered with role-appropriate General MIDI programs through FluidSynth.
   Aligned spectral shape contributes 70%, dynamics 15% and attack activity
   15%. The best MIDI and WAV auditions are retained.
3. **Optional learned OpenL3 evidence.** When a local checkpoint is supplied,
   the unchanged stem and every rendered GM candidate are divided into the
   same aligned one-second windows. A music-audio embedding compares only
   windows active in both recordings and produces a separate audition order.
   It does not change, blend with or replace the explainable ranking above.

Outputs are:

```text
work/instruments/bass/
├── instrument_matches.json
├── GARAGEBAND_AUDITION.md
├── timbre_profiles.svg
├── source_event_clusters.json     # per-event families/articulation/outliers
├── source_event_clusters.svg      # pitch/timeline review
├── source_event_dynamics.json     # advisory layers/alternate samples
├── source_event_dynamics.svg      # source-level timeline review
├── gm_auditions/...
├── openl3_embedding_evidence.json # optional model/hash/window audit
└── gm_embedding_auditions/...     # optional learned shortlist
```

For `kick`, `snare`, `hat`, `cymbals`, `toms`, `other_kit` and `drums`, the
pitched GM-program directories are replaced by the drum-family artifacts
described below.

The scores rank only the candidates examined for that stem. They are not
probabilities, proof of the original instrument, or a guarantee that the
highest isolated-timbre match will sit best in the full mix. GarageBand does
not expose its complete patch renderer as a supported headless API, and patch
names do not always match underlying sample-asset names. Use the report as a
shortlist, then listen in the actual song.

Candidate family is a hard musical boundary before similarity scoring. In
particular, `keys` compares General MIDI pianos, chromatic percussion and
organs (programs 1–24), not synth leads or pads; use `synth` or `pads` when
those are the intended roles. Local OpenL3 ranking uses the same role-constrained
candidate set and cannot bypass the sample-instrument usability gate.

### Review source-event families and artefacts

Every match now retains an advisory review of the MIDI-aligned source events.
`source_event_clusters.json` contains:

- deterministic candidate timbre-family IDs based on robust spectral shape,
  brightness, noise and related explainable features;
- an independent articulation grouping using duration, peak timing, tail
  level, crest, RMS and MIDI velocity;
- rare-event flags based on robust nearest-neighbour distance; and
- medoid events, distances, pitch ranges, descriptors, source/MIDI hashes and
  explicit statements that nothing was removed or reordered.

`source_event_clusters.svg` places the coloured candidate families on the
MIDI pitch/timeline and labels articulation groups. Red events are retained
outliers, not automatic mistakes: a fill, slap, pickup, unusual note, bleed or
separator artefact can all look rare. The v1 report changes zero MIDI notes,
instrument rankings and sample selections.

Without a model the clustering uses only explainable timbre evidence. Supplying
`--embedding-model` adds 30% OpenL3 cosine distance to 70% explainable distance
and records that model/hash in the cluster report. Compare the two methods by
ear when they disagree; neither identifies a physical instrument with
certainty.

### Review dynamics and alternate-source candidates

`source_event_dynamics.json` uses the retained source-event report to ask a
narrower question: are there enough repetitions of the same candidate timbre
family, MIDI pitch and articulation to justify listening for distinct dynamic
layers or interchangeable samples?

A two-layer proposal requires at least eight events in that exact comparison
unit, at least four events and 20% of the unit on each side of the split, and
at least 3 dB between median source RMS levels. The threshold is the largest
adjacent RMS-dB gap, with deterministic balance tie-breaking. A round-robin
set requires at least three isolated events in a layer. It retains the
explainable-timbre medoid and up to two diverse central alternatives while
excluding the most distant 20% from selection.

`source_event_dynamics.svg` plots the source level over time. Cyan and yellow
show candidate layers, white rings show alternate-sample candidates and red
shows retained cluster outliers. These labels are not proof that a performer
or original sampler used separate recordings. Bleed, room sound, phrase
context and source-derived MIDI velocity can all produce apparent groups.
The report therefore records zero changes to MIDI notes and velocities,
sample selection, SoundFont zones and drum-family mapping.

### Separate distinct drum and percussion sounds

On General MIDI channel 10, note number selects a kit piece: it does not mean
the source sound was sung or played at that musical pitch. For a drum role,
the normal `instrument-match` command now:

1. analyses every MIDI-aligned hit up to a conservative 512-event ceiling;
2. splits each persistent timbre family by the existing MIDI note, so an audio
   cluster cannot collapse kit-piece distinctions the converter already made;
3. compares each mapping-unit median with role-appropriate GM one-shots
   rendered through the configured SoundFont;
4. proposes a different valid note only when it scores at least 55 and beats
   the existing note by at least eight relative score points; and
5. writes `drum_family_mapping.proposed.mid` and its WAV as a separate review
   copy.

```bash
.venv/bin/sunofriend instrument-match \
  "work/Lidl-B major-119bpm-440hz/Lidl-kick-B major-119bpm-440hz.wav" \
  examples/the-aisle-at-lidl/midi/repair/kick.mid \
  --kind kick \
  --out-dir work/instruments/lidl-kick-families
```

The original MIDI is never overwritten. Its SHA-256 is measured before and
after the proposal. Timing, duration and velocity are unchanged; only note
numbers in the proposed copy may differ, and it is explicitly moved to MIDI
channel 10. Robust outliers and events beyond the analysis ceiling retain
their original note. `gm_drum_family_mapping.json` records every candidate
score, assignment, changed index, retained outlier, input/SoundFont hash and
output hash. Assigned one-shots are in `drum_note_auditions/`.

The score-55/eight-point change rules are deliberately conservative policy
guardrails, not calibrated confidence. They prevent a mediocre SoundFont
proxy from replacing a valid existing note merely because it ranked first.

Candidate sets are deliberately role-specific: kick 35–36; snare 37–40; hats
42/44/46; toms 41/43/45/47/48/50; cymbals 49/51/52/53/55/57/59; and the full
GM percussion range 35–81 for mixed `other_kit`/`drums`. A cluster is only a
candidate sound family, and a high relative score is not confidence. A
coherent separator artefact can still receive a plausible kit note. Compare
the proposed WAV with the source, then audition the MIDI using the intended
GarageBand drum kit before accepting or editing it. `--no-gm` disables this
proposal as well as pitched GM auditions.

Each factory-family match also lists related installed sampler definitions
when their names overlap, turning a sample-family result such as `Picked
Electric Bass` into concrete local preset names such as `Picked Rock Bass`.

Useful controls:

```bash
# Factory assets only; useful without FluidSynth
sunofriend instrument-match STEM.wav PART.mid \
  --kind keys --out-dir work/instruments/keys --no-gm

# Render all 128 General MIDI programs instead of the role shortlist
sunofriend instrument-match STEM.wav PART.mid \
  --kind lead --out-dir work/instruments/lead-all --all-programs

# Select one note-bearing track from a multitrack MIDI
sunofriend instrument-match STEM.wav SONG.mid \
  --kind bass --track-index 2 --out-dir work/instruments/bass-track-2
```

### Optional local OpenL3 comparison

OpenL3 is an additional opinion for auditioning, not an automatic winner. Its
source code is MIT licensed and its original model weights are CC-BY-4.0; the
converted music/512-dimensional ONNX checkpoint is hosted in the official
Essentia model collection. See the [OpenL3 project](https://github.com/marl/openl3)
and [Essentia model catalogue](https://essentia.upf.edu/models.html).

Install the pinned checkpoint explicitly outside the repository:

```bash
scripts/setup-openl3-model.sh

OPENL3="$HOME/.local/share/sunofriend/models/openl3-music-mel128-emb512-3/openl3-music-mel128-emb512-3.onnx"

.venv/bin/sunofriend instrument-match STEM.wav PART.mid \
  --kind bass \
  --out-dir work/instruments/bass-openl3 \
  --embedding-model "$OPENL3"
```

Sunofriend never downloads this model during matching. It accepts only the
pinned SHA-256
`81c24c8a723054717fdea5c7448acb6023baaf70a0fc526deb030c2032db0ed3`,
runs ONNX inference on CPU, and fails before creating the requested output if
the file is missing, altered or has an unexpected input/output contract.
`openl3_embedding_evidence.json` records the model and SoundFont hashes,
preprocessing, source fingerprint summary, every GM candidate, active-window
scores and the separate learned shortlist. High absolute cosine values are
normal for related sounds and are not probabilities; compare candidates only
within the run and listen to both `gm_auditions/` and
`gm_embedding_auditions/` in the full mix.

The same option works with `instrument-bundle`; the bundle keeps the learned
evidence under `matches/` and copies its first audition into `previews/`:

```bash
.venv/bin/sunofriend instrument-bundle STEM.wav PART.mid \
  --kind bass \
  --out-dir work/instrument-bundles/bass-openl3 \
  --embedding-model "$OPENL3"
```

`listen-all` now puts name-based starting suggestions and an exact
`instrument_match_command` argument list beside every successful part in its
summary JSON.

## Make a new instrument from a stem

This is possible when the stem contains clean, isolated notes and you own or
have permission to sample the recording:

```bash
sunofriend sample-pack \
  "/absolute/path/to/song-bass.wav" \
  "/absolute/path/to/bass_listened.mid" \
  --kind bass \
  --name "Song Walking Bass" \
  --out-dir work/sample-packs/song-bass
```

Sample Instrument v2 uses the MIDI note boundaries as evidence, rejects
overlapping notes by default, keeps a short natural tail, applies small
click-removing fades, normalises conservatively, and chooses at most one strong
sample per MIDI pitch. The output is:

```text
work/sample-packs/song-bass/
├── sunofriend-instrument.aupreset # GarageBand-selectable AUSampler wrapper
├── sunofriend-instrument.sf2   # self-contained SoundFont sample bank
├── sunofriend-instrument.sfz   # mapping for compatible third-party samplers
├── garageband-audition.mid     # one note for every generated zone
├── garageband-audition.wav     # the exact SF2 rendered through FluidSynth
├── instrument-usability-audition.mid # every pitch in the supplied performance
├── instrument-usability-audition.wav # exact generated SF2, unless --no-preview
├── instrument_usability.json   # mapping/duration gate and zero-change evidence
├── sample_pack.json            # roots, ranges, tuning and source evidence
├── source_event_clusters.json  # every candidate event; selections marked
├── source_event_clusters.svg   # pitch/timeline family review
├── source_event_dynamics.json  # advisory layers/alternate samples
├── source_event_dynamics.svg   # source-level timeline review
├── README.md                   # instructions specific to this instrument
└── samples/                    # cleaned 24-bit source WAV zones
```

The SF2 embeds mono PCM16 copies for broad sound-bank compatibility, while the
separate extracted WAVs remain PCM24. Each melodic sample is mapped only to
nearby notes—six semitones by default—and a stable pitch estimate can add a
cents correction without modifying the source WAV. The report distinguishes
`applied`, `no-stable-pitch`, `rejected-unstable` and other tuning outcomes.
Keys outside all reported zones remain silent rather than being heavily
pitch-shifted.

### Instrument Usability Gate v1

The old question “was an SF2 written?” was too weak. A musical instrument also
has to respond to the actual performance. The gate therefore checks:

- every supplied MIDI note has a matching key and velocity zone;
- every mapped note has enough sample audio for an audible attack;
- pitched roles have enough effective, transposition-adjusted sample duration
  for the MIDI note, up to a conservative musical floor; and
- drum/percussion one-shots are assessed for attacks rather than pitched
  sustain.

`instrument-usability-audition.mid` plays every distinct pitch used by the
performance, followed by velocities 32, 64, 96 and 127 on a middle pitch. This
exposes missing ranges and dead velocity zones directly. The JSON records
mapped and unmapped counts, duration support, tuning/timbre review evidence and
explicitly states that it changed no MIDI, audio or SoundFont mapping.

A hard coverage or duration failure produces `status: texture-only`. Do not use
that sampler alone: put a consistent GarageBand or GM patch on the main track
and optionally mix the source sampler underneath for character. A functional
pass produces `review-required`, because consistent tone, tuning and musical fit
still need full-range and full-song listening. Inconclusive pitch tracking or
multiple candidate timbre families are warnings, not automatic deletion rules.

Sample Instrument v2 marks which reviewed source events were selected for the
bank. It still chooses samples using the existing isolation, strength and
pitch-diversity policy; a cluster or outlier never removes one automatically.
To add the optional learned opinion to this evidence:

```bash
sunofriend sample-pack STEM.wav PART.mid --kind bass \
  --embedding-model "$OPENL3" \
  --out-dir work/sample-packs/bass-openl3
```

### Reviewed Sample Instrument v3

Sample Instrument v2 remains the conservative default. A v3 experiment can
apply source-event dynamics only through two fresh, explicit steps:

```bash
sunofriend sample-pack-review work/sample-packs/song-bass \
  --out-dir work/sample-reviews/song-bass-v1

# Open sample_pack_review.html in a normal browser, listen, decide every unit,
# and export sample_pack_review.reviewed.json.

sunofriend sample-pack-apply \
  "$HOME/Downloads/sample_pack_review.reviewed.json" \
  --name "Song Walking Bass Reviewed" \
  --out-dir work/sample-packs/song-bass-v3
```

The review directory pins the v2 report, SoundFont, every source sample, stem,
MIDI, cluster/dynamics evidence and every WAV excerpt presented for listening.
Each candidate retains its exact isolated one-shot and adds two contextual
views. The source-context excerpt covers four beats with the target beginning
one beat in and uses one shared stem-level gain, preserving relative dynamics,
nearby rhythm and bleed. The role audition is normalised per event: drum and
percussion candidates use a repeated two-bar beat, while pitched candidates
use a short sampler-style pitch phrase. The initial MIDI tempo controls both.
All three WAVs are hash-pinned and have zero automatic selection effect.

The seed is deliberately `unreviewed`; apply requires a user-exported
`reviewed` document with an explicit accept/reject decision for every unit.
Accepted indices must be members of the immutable candidate set, and only one
candidate unit can be accepted for a MIDI pitch.

The v3 output is separate:

```text
work/sample-packs/song-bass-v3/
├── sample_pack_v3.json
├── reviewed_decisions.json
├── README.md
├── sunofriend-instrument.sf2       # reviewed primaries/layers when accepted
├── sunofriend-instrument.aupreset  # GarageBand/AUSampler wrapper
├── sunofriend-instrument.sfz       # round robin only for accepted alternates
├── garageband-ab-audition.mid      # same performance for every bank
├── garageband-ab-v3.wav            # optional exact v3 render
├── garageband-performance-ab.mid   # representative real source rhythm
├── garageband-performance-source.wav # matching source-stem excerpt
├── garageband-performance-v3.wav   # optional reviewed-bank performance
├── garageband-velocity-sweep.mid    # accepted boundary transition audit
├── garageband-velocity-sweep-v3.wav # optional reviewed-layer sweep
├── baseline-v2/
│   ├── sunofriend-instrument-v2.sf2
│   ├── sunofriend-instrument-v2.aupreset
│   ├── garageband-ab-v2.wav        # optional rollback zone render
│   ├── garageband-performance-v2.wav # optional rollback performance
│   └── garageband-velocity-sweep-v2.wav # optional one-sample sweep
├── garageband-alternates/          # separate accepted-event SF2/AU banks
└── samples/
    ├── baseline/
    └── reviewed/
```

SF2 supports velocity ranges but has no portable round-robin selection opcode.
The main GarageBand bank therefore uses the reviewed primary event for each
layer. Extra accepted events become separate GarageBand A/B banks. The SFZ can
use `seq_length`/`seq_position` for true round robin in compatible samplers.
If the review accepts no layers or alternates, the report correctly records
both features as absent rather than describing rejected proposals as active.
Neither command changes MIDI notes or velocities, and the complete v2 bank is
copied into `baseline-v2/` for immediate rollback.

The sequential `garageband-ab-audition.mid` checks every generated zone. The
separate `garageband-performance-ab.mid` asks the more musical question: how
does the rack behave with its real rhythm and velocities? Sunofriend searches
bar-aligned 8-, 12- and 16-bar windows, choosing the shortest window that
covers every source pitch when possible, then note density and the earliest
tie. It rebases that excerpt to bar 1 and channel 1 for the custom AUSampler
bank without changing pitch, velocity or rhythm. The adjacent source-stem,
v2-bank and v3-bank WAVs form one three-way comparison. This audition is a
derived copy; the pinned source MIDI is never edited.

For a bias-reduced final comparison, put completed v3 packs behind neutral
Candidate A/B labels:

```bash
sunofriend sample-pack-ab-review \
  work/sample-packs/song-snare-v3 \
  work/sample-packs/song-hats-v3 \
  work/sample-packs/song-toms-v3 \
  --out-dir work/sample-reviews/song-blind-ab

# Review sample_ab_review.html in a normal browser, then export the JSON.
sunofriend sample-pack-ab-resolve \
  "$HOME/Downloads/sample_ab_review.reviewed.json" \
  --out work/sample-reviews/song-blind-ab-result.json
```

The HTML contains the source reference and Candidate A/B audio but not their
v2/v3 identity. A separate hash-pinned answer key is used only by the resolver.
The tom/dynamics sweep, when present, follows the same hidden mapping. Every
role requires an explicit Candidate A, Candidate B, equivalent or neither
choice; none of those outcomes modifies a sampler.

If at least one velocity layer was accepted, the velocity-sweep MIDI plays
that pitch through a coarse dynamic range and dense steps at boundary −8, −4,
−2, −1, the boundary, +1, +2, +4 and +8, with valid MIDI limits and duplicates
removed. Compare the v2 render, which retains one source sample, with the v3
render, which exposes the exact reviewed switch. The sweep reports
`selection_effect: none`; it cannot move a boundary or replace a sample.

To make that decision explicitly, run a boundary review against the completed
v3 directory:

```bash
sunofriend sample-pack-boundary-review work/sample-packs/song-bass-v3 \
  --out-dir work/sample-reviews/song-bass-boundaries-v1

# Listen in sample_boundary_review.html and export the reviewed JSON.
sunofriend sample-pack-boundary-apply \
  "$HOME/Downloads/sample_boundary_review.reviewed.json" \
  --out-dir work/sample-packs/song-bass-boundary-reviewed-v3
```

The review first plays the lower and upper accepted events through one
constant-velocity repeated-beat MIDI. This makes pitch, tone, texture and
instrument identity easier to compare without confusing them with velocity
loudness. It then renders one common velocity ramp through complete candidate
mappings: lower event only, upper event only or both events at each proposed
boundary. It lists the actual source-MIDI velocity range and warns when the
lower or upper layer would never trigger in the song.

No candidate is selected by default; the current mapping must also be chosen
explicitly if it should remain. The review pins the completed v3 report, SF2,
SFZ, original reviewed decisions, source MIDI and cluster evidence, all
baseline/reviewed sample WAVs and every candidate MIDI/SF2/AUSampler/WAV
artifact. Apply validates them, then regenerates the whole pack from the
original reviewed sample JSON with only the selected mapping overridden. A
single-source choice deactivates one accepted event without modifying its WAV
or introducing a new sample. The source v3 and source MIDI are never edited.

### Direct GarageBand import

1. Drag `garageband-audition.mid` into the GarageBand Tracks area and select
   the new software-instrument track.
2. Open Smart Controls. In the instrument plug-in slot choose **AU Instruments
   > Apple > AUSampler > Stereo**.
3. Open AUSampler's preset menu (normally labelled **Manual**), choose its
   load/open setting command, and select `sunofriend-instrument.aupreset`.
   The `.sf2` is the referenced sound bank and is intentionally greyed out in
   GarageBand's plug-in-preset chooser.
4. First play `instrument-usability-audition.mid` to check every pitch used by
   the supplied song and the four velocity probes.
5. If the report says `texture-only`, keep a complete GarageBand instrument on
   the main MIDI track and use this sampler only as an optional quiet layer.
   Otherwise replace the audition with the song MIDI and listen end to end.
6. Save a custom patch only after the functional and musical checks pass.

The `.aupreset` is a public AUSampler state wrapper around Apple's documented
SF2 sound-bank support; it is not a private GarageBand project or patch. The
audio remains embedded in the SF2. Keep the preset and bank at their generated
paths; regenerate the preset after moving the sample-pack directory.

Useful controls:

```bash
# Restrict each source sample to three semitones of transposition
sunofriend sample-pack STEM.wav PART.mid --kind bass \
  --max-transpose 3 --out-dir work/sample-packs/tight-bass

# Preserve raw sample tuning and skip the FluidSynth audition WAV
sunofriend sample-pack STEM.wav PART.mid --kind lead \
  --no-auto-tune --no-preview --out-dir work/sample-packs/raw-lead
```

Use `--allow-polyphonic` only as an explicit experiment. Chords, separator
bleed, room sound, reverb, vibrato and transitions become baked into a sample
and then repeat on every played note. Sample Instrument v2 does not
automatically enable loop points, velocity layers or round-robin playback, so
a long held MIDI note still ends when its embedded sample ends. The dynamics
report identifies candidates for listening without adding zones or changing
velocity ranges.

For pitched samples, `source_sample_loops.json` and
`source_sample_loops.svg` rank possible forward-loop boundaries after the
attack and before the release. Up to three `loop-auditions/*.wav` files repeat
each raw candidate four times without a crossfade, deliberately exposing
clicks, level steps and timbre movement. Samples below the advisory duration
minimum are marked `too-short`; drums and percussion are `not-applicable`.
The report records zero changed sample files, sampler zones and MIDI notes.
Listen to every candidate and choose “none” whenever the repeated phrase,
vibrato, bleed or texture is audible: a lower continuity score is only a
shortlist, not an acceptance decision.

## Recommended listening loop

1. Convert and evaluate the stem-to-MIDI timing and pitch first.
2. Run `instrument-match` on the unchanged, aligned stem and main MIDI.
3. Audition the top factory families and retained GM WAVs in isolation.
4. Open `source_event_clusters.svg`, listen to cluster medoids and any red
   retained outliers, and decide whether they are real articulations or bleed.
5. Open `source_event_dynamics.svg`; when it proposes layers or alternates,
   compare those exact event indices before changing a sampler mapping.
6. For a pitched sample with `loop-auditions/`, compare every raw repeat and
   retain no loop unless one is musically stable as well as click-free.
7. Audition the instrument candidates again with the complete song; compare emotion, register,
   masking and articulation, not just spectral similarity.
8. Save the winning GarageBand patch on the reusable Clip v1 part:

   ```bash
   sunofriend clip-instrument CLIP_ID \
     --suggest "Stinger Bass" --suggest "Picked Electric Bass"
   ```

9. If no installed sound works and the source has isolated notes, build a
   `sample-pack` and audition it in AUSampler or an SFZ-compatible Audio Unit.

This workflow makes instrument choice repeatable without pretending that
emotion can be reduced to a single automatic score.
