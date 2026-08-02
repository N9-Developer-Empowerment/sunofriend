# Lyric-aware, melody-aware vocal comping

Prepared: 1 August 2026

Repository baseline: `82e2548` (`main`)

Status: pre-implementation product and technical design; no command, model,
dependency or product route is enabled by this document.

## Decision

Sunofriend should pursue this feature.

The public description should be **lyric-aware, melody-aware automatic vocal
comping**. The engineering description is **unit-selection vocal comping with
global performance optimisation**.

The proposed product takes multiple complete performances by the same singer,
known lyrics, an intended melody and musical timing, then:

1. preserves every take as immutable source evidence;
2. aligns the performances to one canonical song timeline;
3. compares them by phrase using continuous pitch, target notes, timing,
   lyric delivery and recording-quality evidence;
4. suggests a low-edit composite using a global sequence optimiser;
5. lets the person audition, lock, replace or reject every choice;
6. renders a natural, reversible comp from the reviewed edit map;
7. identifies passages where no take is good enough and requests pickups; and
8. optionally creates a separately labelled gently corrected derivative.

This is credible and distinctive. Manual comping is an established studio
practice, but the complete combination above is not represented by a mature,
widely adopted open-source product. AI Vocal Comp is the closest direct public
prototype; it validates the workflow but does not yet provide target-melody,
known-lyric or global-continuity reasoning.

## Product promise and non-goals

The promise is not “make a bad singer perfect.” It is:

> Find the most convincing performance already present across your takes,
> preserve your voice and phrasing, show why each section was suggested, and
> tell you exactly what to sing again when the recordings do not contain a
> good answer.

Initial non-goals:

- voice cloning, singing synthesis or timbre replacement;
- inventing lyrics or melody notes absent from the supplied target;
- selecting at individual-word or phoneme granularity by default;
- automatic release approval or mastering;
- destructive editing of source takes;
- hiding alignment, lyric or target-melody uncertainty behind one score;
- using “in key” as a substitute for following the intended melody;
- interpreting technical accuracy as emotion, expression or preference;
- making a separator model a compulsory dependency for already isolated takes;
- exposing this through Simple mode before Studio review and listening gates
  have passed.

## Why it fits Sunofriend

Sunofriend already has the right product principles and much of the analytical
foundation:

- `vocal.py` retains continuous F0 evidence separately from MIDI notes;
- `vocal-trackers` keeps independent pYIN, Basic Pitch, RMVPE and optional GAME
  evidence rather than collapsing them into a hidden winner;
- `melody-review` creates bounded phrase units and requires explicit review;
- melody correction uses immutable inputs, fresh outputs and adjacent audits;
- Workbench separates audition state, proposals, human decisions and exports;
- source receipts, file hashes and fresh atomic publication establish the
  evidence pattern needed for non-destructive waveform work; and
- the current product already distinguishes automatic unreviewed output from
  human-reviewed Studio results.

The important missing capabilities are not “more MIDI.” They are:

- a project type in which several lead recordings are alternatives rather than
  simultaneous stems;
- canonical lyrics and their editable timing hierarchy;
- alignment of every take to a shared lyric-and-melody timeline;
- a transparent phrase quality model;
- a transition-aware global selector;
- a non-destructive waveform edit map and renderer; and
- a pickup planner.

## Separation dependency boundary

As of 2 August 2026, public finished-song separation is not enabled. The
private Kim Vocal 2 challenger has song-disjoint downstream MIDI observations
and its prepared listening reviews are complete, but lead/backing assignment,
remaining execution-path safety and product gates remain open. Sunofriend now
also preserves 17 private vocal candidates per tested excerpt: the unchanged
Kim primary, four register hypotheses and twelve provider-leaf adapter
primaries. That path-free inventory copies no MIDI or audio and selects,
merges, repairs and identifies no singer. It is evidence for a later explicit
audition contract, not a comping input or accepted separator. The repository
describes public Studio separation as Phase S4 and one-action Simple
separation as Phase S6.

Vocal comping should begin only after the requested public separation milestone
is closed, but its architecture should remain independent:

- dry, isolated takes need no separator;
- a target vocal extracted from a finished mix may come from an accepted
  separator, a provider export or the user;
- target melody MIDI may come from Sunofriend, a DAW or manual correction;
- separator provenance must flow into the target record, not into every take;
- comping must never reinterpret separator estimates as original multitracks;
  and
- repeated vocal takes must not enter the ordinary stem catalog as parallel
  vocal layers, because automatic arrangements could otherwise mix them
  together.

## User journey

### First supported journey

1. **Create a vocal-take project** from 2–24 dry complete lead takes.
2. Supply a target melody MIDI, positive BPM, common recorded zero and lyrics
   with manually marked line or phrase boundaries.
3. Sunofriend verifies and analyses every take locally.
4. Choose or accept a suggested base take.
5. Review ranked alternatives phrase by phrase in Studio.
6. Ask Sunofriend for a low-edit comp suggestion.
7. Listen to the base take, suggested comp and selected alternatives in exact
   synchronized loops.
8. Explicitly save the comp decisions.
9. Render an uncorrected dry composite plus an edit map and report.
10. Review the pickup list for passages with no acceptable candidate.

### Later journey

After phrase-level evidence is trustworthy, add automatic word, syllable and
phoneme alignment, then optional word-level repair. The person-supplied lyric
text remains canonical; recognition may flag omissions, repetitions, ad-libs
or mismatches but must not silently rewrite it.

### User-facing modes

- **Natural:** strongly prefers one base take and phrase continuity.
- **Tight:** gives more weight to target melody and timing while retaining
  phrase-level cuts.
- **Raw:** permits very few switches and no correction.
- **Custom:** exposes bounded weights and hard constraints in Studio.

“Expressive” should not be an automatic profile until human-labelled evidence
shows that its measurable features predict the listener’s choices. Dynamics,
vibrato and phrase shape may be shown as descriptors before they are used as
selection scores.

No profile is a human decision. Every automatically generated comp is
`not_reviewed`, `review_recommended` and reversible.

## Input contract

The provisional v1 contract is deliberately narrow.

### Required

- 2–24 authorised, already isolated, dry lead-vocal WAV recordings;
- one exact target melody MIDI;
- known lyrics in UTF-8 text;
- manually confirmed phrase or line boundaries;
- positive BPM and explicit tuning;
- one common recorded-zero contract, or an explicit offset for every take;
- one fresh output outside all source folders; and
- rights category and local-only processing acknowledgement.

### Recommended

- identical microphone, room, position, preamp/gain and sample rate;
- no compression, reverb, pitch correction or noise reduction printed into
  individual takes;
- headphone monitoring to avoid backing-track bleed;
- an instrumental or guide mix for human listening context; and
- a count-in or slate retained in every take when common recorded zero is not
  provided by DAW export.

### Rejected or review-blocked in v1

- backing-vocal stacks or several singers;
- takes with different arrangements, lyrics, keys or tempos;
- a take whose claimed common origin conflicts with its file evidence;
- files that are clipped, silent, truncated or materially different in length
  without an explicit explanation;
- target MIDI with several competing lead tracks and no selected track;
- lyrics with unresolved repeated-section mapping; and
- lossy or already heavily tuned audio as the only benchmark evidence.

### Why explicit origin matters

A dry vocal recorded through headphones contains no backing-track waveform to
align against. “Align every take to the instrumental” is therefore impossible
unless bleed, a slate, timecode or DAW origin is present. The first version
must require common zero or explicit offsets. Melody/lyric alignment can refine
local performance timing, but it must not invent file origin.

## Canonical timeline

The central representation should be hierarchical and half-open at every time
boundary:

```text
Song
 ├── tempo/tuning/recorded-zero evidence
 ├── target melody notes and continuous target-pitch regions
 └── Section
      └── Line / phrase selection unit
           └── Word
                └── Syllable
                     ├── Phoneme
                     └── zero, one or several target notes
```

A syllable may span several notes (melisma), several syllables may share one
pitch, consonants may be unvoiced, and breaths are performance events rather
than empty space. The model must not force a one-word/one-note relationship.

V1 needs only song, phrase and target-note layers. The lower levels are added
without changing the identity of the source takes or earlier phrase evidence.

## Evidence and state planes

The feature should preserve six distinct planes:

1. **Immutable source:** original bytes, canonical PCM24 derivatives, hashes,
   rights category, origin and audio geometry.
2. **Analysis:** F0 frames, observed notes, target alignment, lyric alignment,
   quality measurements and uncertainty.
3. **Proposal:** base-take recommendation, ranked phrase alternatives, global
   comp suggestions and pickup suggestions.
4. **Human decision:** explicit locks, exclusions, chosen take per unit,
   boundary edits and reviewed status.
5. **Render:** a waveform assembled only from the reviewed edit map, plus an
   independently verifiable receipt.
6. **Correction derivative:** optional pitch/time processing applied after the
   dry comp, never replacing it or its edit map.

Playback, solo, looping, weight drafts and audition count remain temporary and
must not enter the decision ledger.

## Per-take analysis

Every take should first pass non-musical eligibility checks:

- exact audio geometry and duration;
- finite samples;
- peak, RMS and silent-region evidence;
- clipping and full-scale sample counts;
- DC offset;
- discontinuities/dropouts;
- provisional noise and room-tone descriptors; and
- origin/offset consistency.

Sunofriend then reuses its existing lead-vocal pipeline to retain:

- frame-level F0 and voiced probability;
- observed MIDI interpretations;
- note-level evidence and provenance;
- attacks and unvoiced gaps;
- contour coverage, monophony and pitch-error statistics; and
- tracker disagreements.

New target-relative evidence should include:

- target note identity at each supported voiced frame;
- signed and absolute cents error around the target pitch centre;
- octave and wrong-note-class errors kept separate;
- onset and offset displacement;
- duration ratio;
- interval and contour agreement;
- missing and excess voiced regions;
- phrase-level timing warp required for comparison; and
- uncertainty from both target melody and observed take.

Vibrato, scoops and portamento must not be flattened into a per-frame “wrong
pitch” count. Measure pitch centre, stability, contour and target-note identity
separately.

## Lyric alignment policy

Known lyrics are authoritative text. The pipeline is:

```text
canonical lyrics
  -> grapheme-to-phoneme candidates
  -> singing-oriented forced alignment per take
  -> editable word/syllable/phoneme timing
  -> optional recognition mismatch evidence
```

Recognition may report:

- possible omitted word;
- possible repeated word;
- possible substituted word;
- ad-lib or non-lexical vocalisation; or
- alignment not reliable.

It must not replace, “correct” or republish the supplied lyrics. Low-confidence
regions remain visibly unresolved and cannot support a fine-grained automatic
cut.

## Phrase score

The scorer must be explainable and must keep dimensions separate. Before any
personal preference model exists, use transparent normalized components:

```text
eligible(take, phrase) = hard evidence gates

quality =
    w_melody  * target_melody_match
  + w_timing  * timing_match
  + w_lyrics  * lyric_delivery_match
  + w_audio   * recording_quality
  - w_edit    * predicted_correction_cost
```

Suggested component evidence:

| Dimension | Initial measurements | Must not imply |
| --- | --- | --- |
| Melody | target-note agreement, median/p90 cents error, contour and interval agreement, voiced coverage | emotion or “in key” correctness |
| Timing | note/phrase onset, duration, beat-relative displacement, bounded warp | a confirmed downbeat unless supplied |
| Lyrics | required-word coverage and alignment confidence; later phoneme boundaries | pronunciation quality from ASR confidence alone |
| Audio | clipping, dropout, level, noise/room descriptors | professional tone or preference |
| Correction | cents/time movement estimated to meet a bounded target | permission to process audio |

Expression descriptors—vibrato rate/extent, dynamics, phrase arc and breath
placement—should appear beside the score but have zero automatic weight in the
first accepted version.

Missing evidence is not zero quality. It is `unknown`, which can block that
dimension or the entire candidate.

## Base take and global optimisation

Independent “best word” selection would create an unstable result. The system
should first score whole-take and section continuity to nominate a base take,
then use dynamic programming over phrase units.

For phrase `s` and candidate take `t`:

```text
total cost =
    sum(-phrase_quality(t, s))
  + take_switch_penalty
  + audible_join_penalty
  + base_take_departure_penalty
  + correction_cost
  + unresolved_evidence_penalty
```

The optimiser state needs the current take, chosen source-frame interval,
boundary candidate and whether the preceding breath belongs to this phrase.

Hard constraints:

- use only eligible candidates;
- preserve lyric order and the canonical target timeline;
- respect user locks and exclusions;
- never cross an unresolved phrase boundary;
- do not split a held vowel in v1;
- attach a detected lead-in breath to the following phrase by default;
- enforce a minimum chosen run unless the user requests a surgical repair;
- cap the number of automatic switches; and
- return `no_acceptable_candidate` rather than filling every unit.

Three proposals may share the same evidence but different fixed policies:

- **Natural:** largest switch and base-departure penalties;
- **Tight:** larger melody/timing weights and bounded correction-cost budget;
- **Raw:** no correction and a very small switch budget.

Scores rank places to listen. They do not create review events or select a
rendered master.

## Natural join design

The renderer must consume only a reviewed, hash-pinned edit map. For every
join it should:

1. search within a bounded region around the reviewed boundary;
2. prefer silence, breath gaps, unvoiced consonants and low-energy room tone;
3. avoid held vowels, note attacks and the middle of vibrato cycles;
4. compare local level, spectral envelope and room/noise continuity;
5. keep the breath with the phrase it prepares unless explicitly changed;
6. translate a whole chosen region only within its reviewed alignment budget;
7. apply independent short fades and a bounded equal-power crossfade only
   where overlap cannot create a doubled voiced syllable; and
8. record the exact source and destination frame bounds and gain curves.

Zero crossings alone are insufficient. Two unrelated vocal takes can be at a
zero crossing yet differ in vowel, room sound, pitch and breath state.

If no safe join exists, keep the longer region from one take or mark the join
for review. The renderer must not silently time-stretch a phrase to make an
unsafe selection fit.

The uncorrected dry comp is always retained. Shared EQ, compression, de-essing,
reverb and mastering happen after comping and are outside the first feature.

## Optional gentle correction

Correction is a separate downstream challenger, not part of take selection.
It requires a correction plan, an unmodified dry comp and a new output.

Provisional experimental limits for the first listening bake-off—not final
product guarantees—are:

- pitch-centre movement normally no more than 35 cents and never more than 50
  cents automatically;
- no automatic note-class substitution;
- vibrato shape and unvoiced consonants retained;
- whole-region translation no more than 40 ms without explicit review;
- local stretch/compression no more than 3 percent; and
- any larger proposed change becomes a pickup recommendation.

These values need a predeclared listening experiment. The processing engine is
not selected. Rubber Band is technically relevant but GPL/commercial licensed,
so it must not become an Apache-distributed dependency without a deliberate
licensing decision. Proprietary DAW tools may remain an optional manual handoff.

Every result must expose:

- recorded versus processed regions;
- exact pitch/time movement;
- processing engine and version/hash;
- target and policy;
- dry-comp and corrected hashes; and
- `generated_voice: false`, because correction is not voice synthesis.

## Pickup coach

The system should refuse weak choices constructively. A pickup item contains:

- lyric line and phrase ID;
- exact bars/beats only when the downbeat is confirmed, otherwise seconds and
  relative beats;
- a lead-in and tail recording range;
- why every existing take was rejected or uncertain;
- target notes and approximate durations;
- the smallest actionable direction; and
- requested number of attempts.

Example:

```text
Record three pickups for chorus 1, line 3.
Begin two beats before “Now”.
All current takes miss the final E4 or lose voicing before 650 ms.
Keep the lead-in breath and hold E4 for about 720 ms.
```

This is evidence-backed coaching, not a diagnosis of the singer.

## Provisional data contracts

These names reserve boundaries; they are not implemented schemas.

| Document | Purpose |
| --- | --- |
| `sunofriend.vocal-comp-project.v1` | immutable take, target, lyric, timing and rights manifest |
| `sunofriend.vocal-take-analysis.v1` | one take’s audio, F0, note and quality evidence |
| `sunofriend.vocal-comp-timeline.v1` | canonical phrase/lyric/target hierarchy and uncertainty |
| `sunofriend.vocal-comp-candidates.v1` | per-phrase eligible alternatives and separated scores |
| `sunofriend.vocal-comp-suggestion.v1` | one automatic, unreviewed global proposal |
| `sunofriend.vocal-comp-review.v1` | explicit choices, boundaries, locks, exclusions and status |
| `sunofriend.vocal-comp-edit-map.v1` | exact source/destination frame assembly contract |
| `sunofriend.vocal-comp-render.v1` | dry composite receipt and zero-mutation evidence |
| `sunofriend.vocal-correction-plan.v1` | optional bounded processing request |
| `sunofriend.vocal-correction-result.v1` | corrected derivative and exact processing audit |
| `sunofriend.vocal-pickup-plan.v1` | unresolved units and recording instructions |

Every durable document is self-hashed, path-free when public, and bound to
the complete upstream identity chain. Private manifests may contain local
paths and lyrics and must remain owner-only.

## Workbench design

Add a separate **Vocal Comp** Studio workspace only after the engine contracts
are stable. It should show:

- canonical lyrics and target notes across the top;
- one aligned waveform/F0 lane per take;
- current base take and comp lane;
- phrase score cards with separate dimensions and block reasons;
- exact source/base/proposal switching on one audio clock;
- visible joins, breaths and correction estimates;
- lock, exclude, choose alternative and “none are good” actions;
- a pickup queue; and
- an explicit reviewed-render action.

Suggested does not mean selected. Loading, playing, switching, seeking,
looping, soloing, expanding score details or editing unsaved weights has zero
effect. A decision requires an explicit save action.

The first UI need not display 24 full-resolution waveforms simultaneously.
Show the base, current choice and a bounded number of alternatives; load other
takes on explicit request while retaining the complete server-side evidence.

## Output contract

A reviewed first release should produce:

```text
VOCAL-COMP/
  START-HERE.txt
  AUDIO/
    reviewed-dry-vocal-comp.wav
    base-take-reference.wav            # optional exact copy or link manifest
  EDITS/
    reviewed-comp-edit-map.json
    reviewed-comp-decisions.json
  ANALYSIS/
    phrase-candidate-report.json
    pickup-plan.json
  TECHNICAL/
    vocal-comp-result.json
    source-and-render-verification.json
  vocal-comp-garageband-handoff.zip
```

Optional correction adds a separate file such as
`reviewed-dry-vocal-comp-gently-corrected.wav` and never replaces the dry comp.

The handoff states the exact BPM, recorded zero, sample rate, bit depth,
whether source audio is copied, every join, and whether correction is absent or
present. It is not a release master.

## Safety, privacy and rights

- Work locally; no vocal, lyric, edit-map or preference upload.
- Require authority to process every take and any reference vocal.
- Treat a singer’s raw voice and lyrics as sensitive private material.
- Do not train a general model or contribute examples from project data.
- Personal selection history is explicit, local and opt-in.
- Never install or download an aligner, acoustic model or checkpoint without a
  separately approved plan, exact licence evidence and hash.
- Preserve source bytes and reject linked, changed or replaced evidence.
- Generated or voice-converted regions, if ever added, require a distinct
  product mode and per-region provenance.

## Architectural insertion points

Reuse rather than broaden these components:

- `source_import.py`, `source_receipt.py` and audio-format helpers for canonical
  evidence patterns;
- `vocal.py` for deterministic F0 and note evidence;
- `vocal_trackers.py` for optional independent model evidence;
- `phrase_review.py` for bounded phrase packaging concepts, not its current
  three-alternative schema;
- `note_alignment.py` for note-event comparison primitives after verifying
  that its greedy policies meet target-relative requirements;
- `melody_correction.py` for reviewed/fresh-output patterns, not waveform
  correction; and
- `workbench_store.py` for a separate vocal-comp event namespace and reducer.

Do not put the orchestration into the already large `cli.py`. The eventual
feature should have isolated modules for project admission, timeline,
take analysis, scoring, global optimisation, joins, rendering, review and
pickup planning, with typed CLI registration added only at the product gate.

## Open decisions that require evidence

1. Which manually produced song and take set will be the first authorised
   golden?
2. Is phrase origin supplied from DAW export, a count-in, or explicit offsets?
3. Which target MIDI is authoritative: separator vocal, corrected Sunofriend
   output or DAW MIDI?
4. Does the first lyric-alignment bake-off focus on English only?
5. What minimum phrase unit best preserves this singer’s breath and expression?
6. Which join policy wins when a technically better take has different room
   tone or microphone distance?
7. Do the provisional correction limits sound natural on the user’s voice?
8. Which engine and licence can support correction without compromising the
   Apache distribution?
9. When is personal preference evidence sufficient to influence ranking?
10. What completed separator milestone constitutes the formal start gate?

These are experiment questions, not reasons to delay the non-model phrase-level
foundation once the user opens implementation.
