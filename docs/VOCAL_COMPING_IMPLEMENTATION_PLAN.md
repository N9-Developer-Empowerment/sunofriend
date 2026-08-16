# Vocal comping implementation and evaluation plan

Prepared: 1 August 2026

Status: VC1 admission and a bounded VC2 ranked-evidence pilot implemented;
human selection, assembly and correction have not started.

Companion documents:

- [Product and technical design](VOCAL_COMPING_DESIGN.md)
- [Research and dependency assessment](VOCAL_COMPING_RESEARCH.md)

## Start gate

Do not start feature code until the user opens implementation and the agreed
stem-separation milestone is complete.

The start checkpoint should record:

- exact Sunofriend commit and clean/dirty worktree state;
- public separation capability and acceptance status;
- selected first authorised benchmark project;
- target MIDI and lyric authority;
- common-origin/offset evidence for every take;
- explicit decision that the first increment is phrase-level and uncorrected;
  and
- no optional model/download approval unless a later experiment needs it.

Comping remains usable without separation for already isolated takes. The gate
is sequencing requested by the user, not a permanent runtime dependency.

## Implementation checkpoint — 12 August 2026

The first private, expert-CLI increment now provides:

- `vocal-comp-create`, with a read-only plan and fresh owner-only immutable
  project publication for 2–24 top-level vocal-only WAV takes;
- hash-bound canonical lyrics, reviewed monophonic target MIDI, reviewed
  musical-phrase timing, rights category, BPM, tuning, processing-chain and
  common-recorded-zero evidence;
- `vocal-comp-analyze`, preserving independent pYIN and Basic Pitch evidence
  plus optional separately completed, source-matched RMVPE evidence;
- fixed, transparent target-relative phrase scores, uncertainty and block
  reasons, with expression assigned zero weight in this uncalibrated pilot;
- top-three phrase auditions, `no_acceptable_candidate` outcomes and pickup
  instructions; and
- optional AI-reference auditions only when no human candidate clears the
  experimental evidence floor.
- a separate local draft-review page and strict resolver, so automatically
  extracted lyrics, phrase timing and target MIDI cannot acquire human-review
  status from playback or a visible default.

This checkpoint deliberately has no human decision store, global optimiser,
join boundary engine, crossfade renderer or pitch correction. It cannot create
a selected or finished comp. The Heart Sees material can be admitted only
after its target MIDI and phrase timeline have been explicitly reviewed; this
code does not manufacture either review decision.

## Implementation checkpoint — 13 August 2026

The first listening review rejected every automatic phrase. It established a
specific blocking failure rather than a vague quality concern: the AI singer
added an ad-lib, so vocal-energy segmentation shifted the lyric-to-phrase map.
Some early target-MIDI phrases were musically close, but that did not make the
word or phrase identity correct.

The implementation now records this unresolved review as immutable private
feedback with zero promotion effects. It also adds two deliberately auxiliary
evidence stages:

- `vocal-comp-stt` produces local unprompted OpenAI Whisper word timestamps
  from an exact existing checkpoint and interpreter. It cannot select a model
  name or download a checkpoint, does not prompt with the known lyrics, and
  remains `complete_unreviewed`;
- `vocal-comp-word-align` hash-binds each transcript to its AI/human vocal and
  globally aligns observed words to immutable canonical lyrics; and
- insertions, omissions and substitutions remain explicit review candidates.
  No STT result can rewrite lyrics, approve timing or create a comp.

This does not solve syllable timing. Dividing a word duration evenly would
create false precision, especially for melisma and held vowels, so the result
explicitly reports syllable alignment as unavailable. A separately qualified
singing-oriented phoneme aligner and human correction surface remain required
before word/syllable-scale edit boundaries can be used.

The immediate programme order is therefore revised: obtain and review
word-level evidence, correct phrase mapping, then resume phrase ranking. A
global optimiser or renderer built before that gate would optimise the wrong
units more confidently.

## Programme success criterion

The programme succeeds when a person can supply several complete vocal takes,
known lyrics and a target melody, then obtain a reviewed dry composite that:

- is audibly at least as useful as the best complete take;
- contains no unacceptable join;
- preserves source identity and edit provenance;
- requires less review/editing time than manual comping from scratch;
- does not over-correct or generate the singer’s voice; and
- truthfully recommends pickups where the available takes are insufficient.

Automated agreement metrics cannot close the programme by themselves.

## Phase VC0 — authorised golden and manual reference

Goal: make the evaluation answerable before building the engine.

### VC0.1 Benchmark manifest

Prepare one owner-only project with:

```text
instrumental-or-guide.wav
target-vocal-reference.wav          # optional and authorised
target-vocal.mid
lyrics.txt
phrase-timeline.json                # manually confirmed
take-01.wav ... take-N.wav
manual-base-take.txt
manual-comp.wav
manual-comp-edit-map.json
manual-pickup-notes.txt
```

Recommended first set: 8–12 complete dry takes of one 2–4 minute English song.
Include natural variation plus at least one deliberately difficult line, one
held vowel, one breath-led phrase and one repeated chorus.

### VC0.2 Ground-truth limits

The manual comp is preference evidence, not acoustic truth. Record:

- chosen region and source take;
- selection reason in bounded tags;
- approximate acceptable alternatives;
- rejected takes and reasons;
- join location and crossfade;
- whether correction would be desired; and
- time spent producing the manual result.

### VC0.3 Synthetic engineering fixture

Plan a copyright-safe deterministic fixture with several tone/noise “takes,”
known target notes, deliberate offsets, clipping, silence and join regions.
It tests hashes, alignment, scoring topology and renderer reconstruction. It is
not evidence for vocal naturalness.

### VC0 acceptance

- every source is authorised, immutable and hashed;
- exact origin/offset is known;
- target MIDI and phrase bounds are reviewed;
- the manual comp and edit map agree at sample-frame resolution; and
- the first listening questions and stop conditions are written before code.

## Phase VC1 — take-project admission

Goal: safely represent alternatives without treating them as simultaneous
stems.

### Work items

- Define and validate `vocal-comp-project.v1`.
- Accept 2–24 top-level WAV takes only.
- Reuse canonical PCM24 and source-receipt patterns without broadening ordinary
  source-folder import semantics.
- Bind lyrics, target MIDI, BPM, tuning and explicit origins/offsets.
- Reject output inside any source tree and publish atomically.
- Produce a read-only plan before import.
- Keep project creation independent of TUI loading.

### Tests

- duplicate files, duplicate labels and changed bytes;
- conflicting sample rates/origins/durations;
- traversal, symlink and hard-link boundaries;
- invalid lyrics encoding and target MIDI selection;
- one, 25 and oversized takes;
- output collisions and interruption before publication; and
- deterministic path-free receipt.

### Acceptance

No analysis or audio assembly occurs. Original hashes match before and after,
and repeated takes cannot appear as selected parallel vocal lanes in Simple or
Workbench arrangement output.

## Phase VC2 — deterministic phrase analysis

Goal: compare every manually bounded phrase with the target melody using the
existing non-model vocal stack.

### Work items

- Extract/reuse immutable `PitchFrame` and note evidence per take.
- Map target MIDI to the canonical timeline.
- Implement bounded target-relative note/F0 correspondence.
- Compute separated melody, timing and recording-quality evidence.
- Mark missing data as unknown, not zero.
- Publish phrase candidates with full block reasons.
- Add read-only CSV/HTML inspection before any ranking UI.

### First score dimensions

- exact target-note and octave-aware agreement;
- median and p90 pitch-centre error;
- contour/interval agreement;
- voiced coverage and missing/excess regions;
- note onset/offset and duration displacement;
- clipping, silence, dropout and level descriptors; and
- predicted correction magnitude, without applying it.

Expression stays descriptive and weight zero.

### Tests

- target note is E while take sings in-key G;
- octave-equivalent but wrong-register phrase;
- vibrato around the correct centre;
- scoop into the correct target;
- correct pitch with wrong onset/duration;
- consonant/unvoiced gaps;
- phrase with no voiced evidence;
- repeated phrase and target-MIDI ambiguity;
- changed target/take after analysis; and
- deterministic repeat evidence.

### VC2 acceptance

On the authorised golden, the report explains obvious good/bad phrases without
claiming emotion or preference. The user can identify at least one useful
target-relative distinction not available from existing take MIDI alone.

## Phase VC3 — base take, ranking and pickup prototype

Goal: turn evidence into transparent places to listen without rendering a
comp.

### Work items

- Whole-take and section-level base-take score.
- Per-phrase eligibility and ranking.
- Fixed Natural, Tight and Raw policy documents.
- `no_acceptable_candidate` outcome and pickup-plan generator.
- Offline report with base, alternatives, separated score dimensions and
  uncertainty.
- Explicit manual override in a local review seed; do not write reviewed state.

### Evaluation

- top-1 and top-3 agreement with the manual edit map, reported per dimension;
- fraction of manual choices blocked incorrectly;
- fraction of manual rejects admitted incorrectly;
- calibration of “no candidate” against manual pickup notes; and
- score ablation: melody only, melody+timing, full transparent score.

Do not optimise the weights on the same song used for final listening evidence.
One song may develop the mechanism; a second authorised song is needed before
generalising a default.

### VC3 acceptance

The ranked report reduces audition effort and top-3 usually contains the user’s
choice on the golden, but no automatic winner or product route is enabled.
Predeclare the exact small-sample thresholds with the benchmark rather than
presenting them as universal product accuracy.

## Phase VC4 — global low-edit proposal

Goal: produce a complete edit-map suggestion without rendering audio.

### Work items

- Dynamic-programming optimiser over phrase candidates.
- Switch, base-departure, join-risk and correction-cost penalties.
- Locked/excluded choices.
- Breath ownership and minimum-run constraints.
- Switch budget and no-candidate gaps.
- Deterministic Natural/Tight/Raw proposals.
- Explain why a locally higher score was not selected when continuity wins.

### Characterisation cases

- one take is slightly worse locally but avoids two switches;
- a perfect word inside an otherwise poor phrase must not create a word cut;
- a breath and following phrase stay together;
- user lock forces the rest of the optimum to update;
- no safe candidate leaves an unresolved gap;
- equal-cost paths use documented deterministic tie-breaking; and
- changing one weight creates a new proposal identity without changing source
  or decisions.

### VC4 acceptance

The proposal edit map is complete or explicitly unresolved, deterministic and
auditable. It is `not_reviewed`; it mutates no source and records no preference.

## Phase VC5 — dry assembly renderer

Goal: render only explicitly reviewed phrase choices with natural joins.

### Work items

- Exact frame crop and destination mapping.
- Bounded local boundary search.
- Breath/unvoiced/low-energy join classification.
- Short fade and crossfade policies.
- Bounded whole-region offset translation; no stretch in the first slice.
- Local gain-trim evidence with conservative limits.
- Render horizon, clipping and reconstruction/accounting receipt.
- Source, base, proposal and reviewed comp exact listening package.

### Join test matrix

- silence to silence;
- breath into voiced onset;
- unvoiced consonant boundary;
- same vowel/pitch with room-tone difference;
- different vowel or note near the proposed cut;
- held vowel with no safe boundary;
- take with different DC offset or noise floor;
- shorter source region and horizon padding attempt; and
- changed source after edit-map review.

### Human review

Use fixed exact windows around every join plus start/middle/end full-mix loops.
Require choices such as seamless, acceptable, needs boundary change, wrong take
or cannot tell. Preparation and playback remain zero-effect.

### VC5 acceptance

- every source frame in the output is explained by the edit map or an explicit
  fade/gain operation;
- output is finite PCM24 with zero full-scale samples;
- source hashes are unchanged;
- no join is rated unacceptable in the reviewed final comp; and
- the complete dry comp is preferred or equivalent to the best full take in a
  blinded, level-controlled listening comparison.

## Phase VC6 — Studio Vocal Comp workspace

Goal: make VC1–VC5 usable without JSON editing.

### Work items

- Typed Vocal Comp launch/readiness contract.
- Project overview and one smallest next action derived from explicit state.
- Canonical lyric/target/comp timeline.
- Base/current/alternative exact one-clock audition.
- Separate score dimensions and block reasons.
- Explicit choose, lock, exclude, none-good and boundary actions.
- Append-only vocal-comp decision store and reducer.
- Review export, restart recovery and stale-evidence guards.
- Explicit reviewed dry-render action.

### State tests

- reload restores decisions but not playhead, loop, solo or temporary weights;
- audition never changes a choice;
- changed analysis creates a new review identity;
- none-good blocks rendering until resolved or deliberately retained as a gap;
- stale proposal cannot be saved;
- concurrent identical render reuses only a fully verified result; and
- private lyrics/paths/notes do not appear in path-free receipts.

### VC6 acceptance

The user can complete one authorised song without editing JSON, understands why
each phrase was suggested, can reverse every choice and receives an exact
GarageBand-ready dry vocal plus pickup plan.

## Phase VC7 — automatic lyric timeline

Goal: remove manual phrase timing without letting ASR rewrite the song.

### Bake-off before integration

Compare on the same authorised excerpts:

- manual phrase/word/phoneme timing;
- SOFA;
- MFA;
- optional STARS after separate checkpoint/runtime approval; and
- rough whisper.cpp recognition only for mismatch flags.

Metrics:

- phrase/word/phone boundary median and p90 absolute error;
- catastrophic line-crossing rate;
- missing/repeated lyric detection;
- melisma and long-vowel behaviour;
- Mac elapsed time, memory and model footprint; and
- deterministic repeatability.

### Work items after a winner exists

- Canonical lyric parser and repeated-section mapping.
- Grapheme-to-phoneme alternatives with user-editable pronunciation.
- Singing-aligner adapter and immutable model evidence.
- Editable alignment review.
- Word/syllable/phoneme hierarchy linked to target notes.
- Fine-grained cuts allowed only in reviewed high-confidence regions.

### VC7 acceptance

The chosen alignment path reduces manual timing work without increasing
unacceptable joins or silently changing lyric text. Phrase-level manual timing
remains a complete fallback.

## Phase VC8 — bounded correction challenger

Goal: test whether very small post-comp corrections improve the reviewed dry
comp while preserving voice character.

### Prerequisites

- VC5 dry comp has already passed without correction;
- correction engine, exact version, licence and distribution decision are
  approved separately;
- fixed limits and listening questions are declared before processing; and
- every proposed correction is tied to target and source evidence.

### Experiments

- no correction control;
- pitch-centre only, normally <=35 cents and hard-capped at 50 cents;
- timing translation only, <=40 ms;
- optional local stretch/compression <=3 percent; and
- combined bounded correction.

Retain vibrato/unvoiced content and reject note-class changes. Compare exact
same windows at controlled level and include neither/equivalent/cannot-tell.

### VC8 acceptance

Correction remains optional unless it wins across more than one authorised
song without unacceptable artifacts. The dry comp remains primary control and
is always shipped beside the corrected challenger.

## Phase VC9 — personal preference hints

Goal: learn useful audition ordering from explicit local decisions.

Start with interpretable pairwise or logistic ranking. Inputs may include
chosen/rejected alternatives, score deltas, boundary moves and review context.
Do not infer labels from playback, dwell time or proposal acceptance by
default.

The profile:

- is created only from explicitly named complete reviewed files;
- stores input hashes and bounded aggregate features;
- remains local;
- reorders places to listen only;
- cannot mark a choice reviewed, change the optimiser’s fixed baseline policy
  or bypass eligibility; and
- can be removed without changing source, historical decisions or renders.

Deep learning is deferred until there is enough authorised, meaningful data
and a distinct benefit over transparent ranking.

## Deferred programme

- backing-vocal and multi-singer comping;
- automatic word/syllable replacement outside reviewed high-confidence regions;
- pickup recording directly inside Sunofriend;
- live low-latency take capture;
- de-click, de-plosive, de-ess, denoise or de-reverb processing;
- generative voice repair, singing synthesis or voice conversion;
- cloud processing or shared training data;
- automatic mix/master processing; and
- Simple-mode one-action output.

## Proposed module boundaries

Names are planning placeholders:

```text
vocal_comp_project.py       admission, immutable manifests and receipts
vocal_comp_timeline.py      phrase/lyric/target hierarchy
vocal_take_analysis.py      existing F0 plus target-relative evidence
vocal_comp_scoring.py       separated transparent dimensions and gates
vocal_comp_optimizer.py     deterministic global sequence proposals
vocal_comp_boundaries.py    breath/unvoiced/join candidates
vocal_comp_render.py        reviewed edit-map waveform assembly
vocal_comp_pickups.py       no-candidate recording plan
vocal_comp_store.py         append-only decisions and reducer
vocal_comp_contract.py      typed public capability and zero-effect maps
```

Optional aligners and correction engines belong behind separate worker/admission
boundaries. None should be imported into the normal CLI merely because its
adapter exists.

## Verification ladder

For every implementation increment:

1. focused unit and adversarial tests;
2. deterministic repeat on synthetic evidence;
3. full test suite and lint;
4. owner-only authorised short excerpt;
5. exact artifact/hash/restart audit;
6. level-controlled human listening when audio changes;
7. second-song validation before changing a default; and
8. public interface/skill/docs update only when the route is genuinely ready.

## First implementation slice when authorised

The smallest useful slice is VC0–VC2:

> Admit a fresh project of common-origin dry takes, known phrase boundaries and
> target MIDI; retain existing F0 evidence; publish target-relative phrase
> measurements and block reasons; render nothing and select nothing.

It isolates the genuinely new evidence problem, carries low product risk and
creates the foundation for ranking, pickup coaching and later global comping.
