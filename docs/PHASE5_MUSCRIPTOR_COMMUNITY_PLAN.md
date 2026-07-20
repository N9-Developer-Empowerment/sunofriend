# Phase 5: Multi-Process MIDI Comparison and Local Result Explorer

Status: **Phase 5.0–5.2 are complete; the Phase 5.3 lead-only S0/M1/M3 diagnostic slice and Phase 5.4 explorer slice are complete, including hash-pinned comparison, full-song audition, GarageBand Pack Composer v1 and the explicit disputed-range phrase-review bridge; Phase 5.3 blind choice, lineage and role expansion remain open while Phase 5.5 local Studio hardening now includes Project Overview/Resume v1 plus decision-safety, path-free-role and restart verification; beam 1 and batch 1 remain the defaults and no public service or new checkpoint download is authorised**

Drafted: 19 July 2026
Scope: accurate stem/full-mix MIDI, several analytical and AI processes kept as
auditionable evidence, faster local inference, GarageBand-ready instrument
choices and an approachable local web workbench. Public feedback is deferred
to a later phase.

## Decision summary

The converter in the supplied video is **MuScriptor**, developed by Kyutai and
Mirelo. It is not a new model family for Sunofriend: the `muscriptor-small`
checkpoint is already installed as an optional, isolated Phase 1 challenger.
The upstream implementation used for this research was package `0.2.1` at
commit `302343e8992bdfc619f77f1988168374ed5d675d`.
What is new is the way the model is being presented and used:

- Mirelo Studio treats the complete mix as one instrument-labelled
  transcription problem;
- the current open-source runtime streams separate tracks and can either detect
  instruments or hard-condition decoding on a known instrument list;
- medium and large checkpoints provide a model-size comparison that Sunofriend
  has not yet run; and
- the simple browser workflow makes it possible to collect structured musical
  feedback at a much larger scale than a CLI-only workflow.

The next programme should therefore **not replace Sunofriend with MuScriptor**.
MuScriptor is one useful challenger among several analytical and AI processes.
Sunofriend should compare full-mix, stem-conditioned, specialist, consensus
and repair candidates on the same source; preserve each candidate and its
provenance; use timing, expression, chord, source-support and review evidence
to explain their differences; and learn only from explicit listening or note
edits. Different processes may be best for different roles or phrases. There
is no required global winner.

The intended end state is:

```text
authorised mix and/or separated stems
       |
       +--> Sunofriend specialist stem transcribers
       +--> MuScriptor discovery pass on the mix
       +--> MuScriptor conditioned passes on known stems/roles
       |
       v
immutable candidate tracks with explicit alignment status
       |
       +--> source support, chords, repetition, octave and timing checks
       +--> expression/velocity recovered from the source
       |
       v
blind phrase and full-mix reviews
       |
       +--> local correction and GarageBand handoff
       +--> optional consented feedback JSON or MIDI edit diff
       |
       v
explicit role-specific choices, repair rules and instrument suggestions
```

## Product identity and non-clone boundary

Sunofriend is not intended to clone Mirelo Studio or become a general-purpose
DAW. Mirelo demonstrates that audio-to-MIDI output can be made approachable
through a shared transport, a visual note overview, understandable track
controls and a direct export path. Those interaction principles are useful,
but Sunofriend's product is different:

- it compares several analytical and AI transcription processes rather than
  presenting one model output as the answer;
- it preserves untouched candidates, their process lineage, quality warnings
  and source evidence;
- it asks the listener to choose separately for each role and, where needed,
  each phrase;
- it retains `equivalent`, `neither`, `needs correction` and intentional
  layering as first-class outcomes; and
- it packages explicit choices for GarageBand while leaving final performance,
  patch design and mixing to the DAW.

The interface must make this evidence-led result space easier to understand,
not hide it behind a simplified automatic winner. Process names and metrics
belong in progressive technical detail; audible differences, musical roles and
the user's current choices belong in the primary view.

## What MuScriptor actually does

The official [MuScriptor paper](https://arxiv.org/pdf/2607.08168) describes a
decoder-only Transformer that receives a 16 kHz mono mel spectrogram for each
five-second audio segment and autoregressively emits MT3-like timing, pitch and
instrument tokens. The 128 General MIDI programs are collapsed into 36
`MT3_FULL_PLUS` instrument groups. The model can work without an instrument
list or can be conditioned on the expected groups.

The published training recipe is more important than a novel architecture:

1. pre-train on roughly 1.45 million MIDI files, rendered on the fly with
   symbolic augmentation, more than 250 SoundFonts and random detuning;
2. fine-tune on an internal set of 170,000 real recordings (more than 11,000
   hours) aligned to symbolic notes; and
3. reinforcement-learning post-train on 300 manually verified, high-quality
   transcriptions using onset, frame and offset F1 as the reward.

On the authors' 372-track held-out set, their fully trained 1.3B model reports
onset/frame/offset/drum/multi-instrument F1 of
`60.4/73.3/49.0/50.2/48.2`. These results are useful evidence, not a promise for
Suno or Moises stems: the paper also shows substantial variation by dataset,
and some onset scores are worse than the YourMT3+ baseline even where frame
activity is much better.

The current [official repository](https://github.com/muscriptor/muscriptor)
publishes three checkpoints:

| Variant | Parameters | Approximate F32 weights | Intended use |
| --- | ---: | ---: | --- |
| small | 103M | 0.4 GB | CPU/lower-resource preview |
| medium | 307M | 1.2 GB | default speed/quality balance |
| large | 1.3–1.4B | 5.5 GB | best published quality; GPU strongly preferred |

All three use the same representation and therefore share important limits:

- no velocity or dynamics;
- drum hits have onsets but no meaningful duration;
- two overlapping notes with the same pitch and instrument cannot be
  represented;
- labels stop at 36 broad groups rather than identifying an exact patch;
- unusual timbres, dense mixes and heavily processed audio remain difficult;
  and
- five-second chunking creates a quality/throughput trade-off at boundaries.

The paper and later upstream designs describe sustained-note preludes between
sequential chunks, but Sunofriend's pinned `muscriptor==0.2.1` runtime exposes
no prelude/teacher-forcing control and transcribes independent five-second
chunks. Sunofriend therefore records `prelude_forcing: false` and
`prelude_forcing_supported: false` and rejects a request to enable it rather
than pretending the protection ran. The pinned API does expose beam size,
batch size and classifier-free guidance. Those controls must be benchmarked
rather than assumed to help.

### Open model versus Mirelo Studio

The [Mirelo Audio-to-MIDI page](https://mirelo.ai/models/audio-to-midi) states
that its hosted Studio uses a separately trained version with a larger dataset.
Its results are therefore an external comparator, not a reproducible score for
the published checkpoints. Sunofriend may import a Studio-generated MIDI for a
manual, authorised A/B, but it must label the service, version/date and upload
boundary and must never send audio there automatically.

At the inspected upstream commit, the open web client has consent-gated Google
Analytics for transcription start/completion/error, instrument/note counts,
timing and downloads. Local/self-hosted builds disable it. The source contains
no musical-correctness rating, piano-roll correction submission or training
feedback endpoint. That is an inference from the published client, not a claim
about Mirelo's private Studio systems. It means Sunofriend's proposed review
loop is a complementary feature rather than something that can simply be
copied from MuScriptor.

### Licensing boundary

MuScriptor code is MIT, but its model weights are gated under CC-BY-NC-4.0.
The [model conditions](https://huggingface.co/MuScriptor/muscriptor-medium)
also require users to have the necessary rights for input music and its
transcription. Consequently:

- MuScriptor remains an optional personal/research worker, never an Apache-2.0
  dependency or bundled checkpoint;
- a hosted public MuScriptor inference service is out of scope until the
  licence and operating model receive a separate review or permission;
- medium or large checkpoints require an explicit setup decision and their own
  pinned manifests before use; and
- public benchmark audio must be owned, commissioned, public-domain or supplied
  under a compatible explicit licence.

## What the existing Sunofriend evidence says

Sunofriend already has a stronger starting position than the video suggests:

- `muscriptor-small` 0.2.1 is installed in the isolated Python 3.12/PyTorch
  runtime and its local checkpoint is hash-pinned;
- the adapter already retains separate instrument-labelled tracks and accepts
  repeated instrument constraints;
- a 15-second lead-vocal test produced byte-identical CPU and MPS MIDI, with
  CPU faster on this Apple Silicon machine (`3.30 s` versus `5.37 s`);
- the user judged MuScriptor's lead-vocal MIDI substantially better than the
  original Sunofriend baseline;
- conditioned bass and keys candidates have been useful, while specialist
  Sunofriend kick and strings candidates won their current goldens; and
- an unrestricted 15-second Lidl full-mix pass took `50.22 s` and produced a
  rejected 1,912-note burst, including 1,818 drum notes and vocal-to-wind label
  leakage.

This does not disprove MuScriptor's full-mix method. It shows that model size,
conditioning, current chunk decoding and role-specific quality gates matter,
and that one global winner would be unsafe.

The latest fixed-MIDI timbre review reinforces a second boundary. General MIDI
Synth Bass 2 and source-fitted harmonic-plus-noise resynthesis were both useful
main sounds, but the complete GM patch won overall as the nearest consistent
tone. The earlier source sampler was rejected as missing/inconsistent and far
from the source. Accurate notes and a usable complete instrument must remain
separate goals.

## Questions Phase 5 must answer

1. Does medium or large improve bass, keys, vocals and full-mix instrument
   allocation enough to justify its runtime and memory?
2. Is an unrestricted discovery pass useful when it is followed by
   instrument-conditioned passes, even if its raw MIDI is not usable?
3. Is the best input the complete mix, the separated stem, or consensus between
   both?
4. Can multiple conditioned passes recover the two audible roles in a single
   bass or keys stem without producing duplicate or unsupported notes?
5. Which corrections can be safely automated from source evidence, chords and
   repeated phrases, and which require recognition by a listener?
6. Can a fast preview/full-quality cascade reduce waiting without changing the
   final musical decision?
7. Which feedback improves Sunofriend selection and repair immediately, and
   which is sufficiently licensed and precise to support later model training?
8. Can instrument feedback recommend a complete, playable GarageBand patch in
   the right family without trying to clone an inconsistent stem sample?

## The primary product: a local Sunofriend Workbench

The web page should not be designed as a survey wrapped around model output.
It should be the most understandable way to use Sunofriend. The CLI remains the
reproducible engine and the agent skill remains the conversational entry point,
but both should be able to launch or prepare the same local workbench:

```bash
sunofriend workbench "/path/to/song-stems" --open
```

It binds to `127.0.0.1`, opens the normal browser, loads no third-party scripts
and sends nothing to a server by default. A prominent **Local — nothing is
being uploaded** indicator should remain visible.

The existing Workbench already supplies per-stem source/candidate listening,
explicit decisions, a selected-arrangement proxy and an exact-MIDI GarageBand
handoff. Phase 5.4 builds on those contracts. Its first per-stem visual
waveform/MIDI-note compare timeline and its full-song selected-arrangement
timeline are now implemented. The latter adds an audition-only live source/MIDI
mixer while preserving the same explicit choices. The user-composed export
basket and its exact local ZIP builder are implemented. Phase 5.5 now adds a
default Project Overview derived only from explicit saved state.

### Organise the site around musical decisions

The user should never have to understand model names before hearing useful
results. The primary navigation is:

```text
Project
  1. Check song setup      BPM, key, tuning, downbeat, stem inventory
  2. Explore MIDI results  compare analytical and AI evidence per stem/role
  3. Hear the arrangement  audition stems, choices and useful combinations
  4. Choose instruments    complete/playable sounds first, similarity second
  5. Compose export pack   explicit GarageBand contents and decision report
```

The implemented Project Overview shows every stem as one status row:

| Heard role | Candidates | Current choice | Needs attention | Open |
| --- | ---: | --- | --- | --- |
| body + pluck | 3 | no decision recorded | compare candidates | compare |
| melody + accompaniment | 3 | main A · one needs correction | hear in arrangement | compare |
| kick family | 0 | not applicable | no MIDI result yet | no result |

This makes progress and unresolved decisions visible without exposing a wall
of metrics. Its one recommended workflow step comes deterministically from
saved state; any offered action is navigation, never an inferred musical
preference. The home hides process complexity
only for navigation; the per-stem view retains each separate analytical and AI
candidate, provenance and explicit human decision.

### Two complementary explorer views

A single piano roll containing every candidate would hide the distinction
between alternative processes and intentional simultaneous parts. Phase 5.4
therefore uses two linked views:

1. **Arrangement view** shows one current main choice per musical role plus
   explicit optional layers. A single transport controls the selected stems,
   MIDI and prepared mix previews. Waveform and piano-roll lanes share the same
   time axis, while visibility, mute, solo and gain affect audition only.
2. **Compare-role view** focuses on one stem or heard role. It keeps the source
   waveform visible and presents the small primary family of specialist,
   conditioned AI and genuinely distinct consensus/repair candidates as
   alternatives. The listener can switch between source-only, candidate-only
   and source-plus-candidate playback and inspect why the processes differ.

The two views share one append-only decision state, but they do not collapse
several candidates into an unexplained recommendation. A main result may come
from one process for bass and another for keys; a later phrase choice may use a
third. The interface should explain that diversity as the normal Sunofriend
workflow.

### One stem workspace

Each workspace answers four questions in order:

1. **What does the source sound like?** A loopable source player with waveform,
   bars/beats and optional source spectrogram.
2. **What musical parts are audible?** Plain-language role tags such as
   `bass body`, `pluck`, `melody`, `accompaniment` or `mixed percussion`, which
   the user can correct.
3. **Which MIDI result is useful?** At most three primary candidates, using the
   same neutral instrument and loudness for fair switching.
4. **What should the project use?** `Use as main`, `Keep as optional layer`,
   `Needs correction` or `Reject`.

Candidate cards lead with musical descriptions rather than processes:

- **Closest to the detected notes** — conservative specialist transcription;
- **Clearer attacks** — learned conditioned candidate;
- **Melody-focused combination** — source-supported hybrid; and
- **Show technical details** — model, checkpoint, metrics, provenance and
  warnings for users who want them.

During the first blind listen, candidates can be called A/B/C to avoid model
bias. Reveal the descriptive and technical labels after the user records an
initial judgement. Always offer `equivalent`, `none are usable` and `I cannot
tell`. Never preselect the highest-scoring candidate.

### Keep the result space useful rather than huge

“Explore the result space” should not mean exposing every model parameter or
the Cartesian product of all processes. The normal view contains a deliberately
small candidate family:

1. current specialist baseline;
2. strongest role-conditioned learned candidate;
3. source-supported hybrid only when it is genuinely different; and
4. an **Advanced alternatives** drawer for other models/settings and rejected
   diagnostic evidence.

Candidates that are byte-identical or musically equivalent should be grouped.
Candidates that fail silence, duplicate-burst, timing or playability gates stay
under diagnostics rather than competing as normal choices. A user can request
another candidate for a specific problem—`missing attacks`, `wrong octave`,
`too many accompaniment notes`—instead of generating every variation in
advance.

### Phrase correction without music-theory expertise

When a whole stem is not good enough, jump directly to the weakest or disputed
phrase. Show source, current MIDI and two alternatives in a short loop. Provide
plain actions:

- missing note;
- extra note;
- wrong pitch or octave;
- starts too early/late;
- ends too early/late;
- melody and accompaniment are mixed; and
- none sound like what I hear.

Phase 5.4 now links a disputed timeline range to the exact existing short
phrase review. That page retains its hum/tap guide workflow. Direct piano-roll
note editing, GarageBand edit-diff import and phrase recombination belong to the later creative
arrangement/reuse phase. Every route must keep the untouched model candidate.
Musical terms and note names remain optional details, not prerequisites.

### Arrangement and instrument views

The arrangement page plays all current per-stem choices together and makes it
easy to solo the source, MIDI, or both. A choice that sounded good alone may be
changed after full-mix listening; both decisions and contexts are retained.

Instrument selection comes after MIDI selection. Each role begins with one
complete portable control and a few installed GarageBand family suggestions.
The page first checks that every required pitch is audible and sustained, then
asks about tone and full-mix fit. Source samplers and resynthesis appear as
optional textures unless they pass the complete-instrument and listening gates.

### GarageBand pack composer

Musical choice and file export are related but separate decisions. **Use as
main** and **Keep optional** say what belongs in the current arrangement. The
implemented v1 Pack Composer now shows exactly what will be copied into the ZIP
and lets the user include only explicit, eligible artifacts:

- unchanged selected MIDI tracks, which remain authoritative;
- the prepared dry arrangement proxy;
- selected source stems only after a separate local opt-in, deduplicated by
  exact content hash; and
- a path-free manifest with BPM, key, tuning, downbeat and GarageBand import
  instructions.

The basket is append-only, project-local state with its own optimistic revision
and scope hash. It does not enter musical decisions, private review events or
contribution previews. Plan and basket hashes reject stale builds, and exact
input bytes are checked before deterministic ZIP construction. Rejected,
needs-correction, unreviewed and superseded candidates are ineligible.

Later explicitly gated composer increments may add:

- explicitly requested alternative MIDI tracks;
- prepared stem-only, MIDI-only, hybrid or current custom-mix auditions;
- eligible Instrument Bundles, SF2 banks and `.aupreset` wrappers; and
- a path-free manifest with BPM, key, tuning, downbeat and GarageBand import
  instructions for those new artifact kinds.

The original handoff remains the smallest safe compatibility path: selected
MIDI plus its dry proxy, with source audio excluded. Pack Composer v1 preserves
that default and never infers ZIP inclusion from a play, a visible track or an
unclicked candidate card.

### Local evidence is a by-product of normal work

The current Workbench appends explicit main/optional/reject/correction choices,
problem tags, private notes and solo/full-mix context. It does not treat
playback, dwell time, play count or an unclicked default as a preference.
Later phases may add equally explicit heard confirmations, phrase edit diffs,
chosen GarageBand patches and an “export actually used” event, but those are
not inferred from current browser activity and do not yet reorder candidates.

This durable state already lets the user resume a project and audit changed
choices. Public contribution is not part of Phase 5.4 or 5.5; a later,
separately authorised phase may add a **Contribute this review** step that
previews the exact fields that would leave the machine and requires opt-in.

If later Phase 7 aggregate data is shown, “most popular” must be contextual,
for example: “12 of 18 reviewed bass-body passages preferred this process for
attacks.” It must never be presented as a universal accuracy percentage. Show
the number of reviews, role, source type, model/version and how many listeners
selected `equivalent` or `neither`.

### Local technical shape

- The current small Python HTTP API owns project discovery, immutable artifacts,
  SQLite decisions and the existing preview/arrangement/handoff operations.
- The current bundled browser page uses media elements with a shared-second
  position for time-synchronised A/B loops and loads no remote scripts.
- Phase 5.4 now has local static waveform/piano-roll rendering over the
  versioned `sunofriend.workbench-timeline.v1` contract for one stem. Primary
  candidates load by default and advanced lanes load explicitly. It consumes
  completed outputs and requires no persistent model process. Any later
  inference worker remains isolated and separately enabled.
- The authenticated read-only `/api/arrangement-timeline` route returns
  `sunofriend.workbench-arrangement-timeline.v1`. The server derives its current
  main/optional selection rather than accepting browser candidate IDs, groups
  byte-identical source audio while retaining all role labels, never
  deduplicates selected MIDI and exposes no local paths. It caps the projection
  at 24 distinct sources, 24 selected MIDI lanes and 40,000 rendered notes.
- Arrangement visibility, mute, solo, 0–100 attenuation, presets, loop and
  playhead live only in browser memory. They never append a review event or
  change selection, overlap evidence, cache identity or handoff bytes. Missing
  MIDI sound is prepared explicitly through the neutral renderer; source/MIDI
  levels are not normalised and the shared-second media players are not
  sample-accurate.
- The standalone `midi-ab-review` package supplies blind, explicitly aligned
  exact-source-time, fixed-window sample-RMS-matched comparison files. Its audio
  auto-loops and its shared playhead is scoped per review unit, but it still
  uses browser media elements. Decoded, sample-accurate switching inside the
  Workbench remains a deferred Phase 5.5 gate.
- Every operation is content-addressed and resumable. Closing the browser does
  not lose a completed transcription or review.
- The server uses a per-launch token, accepts local files only through explicit
  project roots and binds to loopback unless a future, separately secured
  collaboration mode is deliberately enabled.
- The existing static review JSON remains exportable so CLI, skill and web
  workflows share one contract rather than creating a hidden web-only store.

The completed Phase 5.4 Workbench slices consume existing outputs. They did not
need a new model, public account system, cloud database or arbitrary upload
endpoint to prove that this interaction is clearer than separate HTML pages.

## Benchmark design

### Golden material

Maintain two strictly separated sets:

- **Private personal goldens:** the existing Lidl, Slayyyter and other
  authorised local songs. Audio and full review artifacts stay under ignored
  `work/`; only aggregate findings may be documented.
- **Public contributor goldens:** short owned, commissioned, public-domain or
  explicitly licensed excerpts with aligned reference MIDI and permission for
  web listening and evaluation.

Every golden must record role, genre, BPM, key/tuning, source type, stem
separator, audible bleed/artifacts, polyphony, expected instruments, rights
status and the exact reference/candidate hashes.

Start with 10–20 second passages. Include at least:

- monophonic and two-role bass;
- melody plus accompaniment keys;
- lead and backing vocals;
- kick/snare/hats plus mixed `other_kit` percussion;
- sustained strings/pads;
- one clean full mix and one separator-damaged full mix; and
- silence/near-silence, repeated notes and a five-second-boundary stress case.

### Candidate matrix

Run the same excerpt through the following lanes without overwriting any raw
candidate:

| Lane | Input | MuScriptor condition | Purpose |
| --- | --- | --- | --- |
| S0 | isolated stem | none | current Sunofriend specialist baseline |
| M0 | full mix | none | discover instrument labels; never auto-promote |
| M1 | full mix | discovered labels | test stable multi-track reconstruction |
| M2 | full mix | known chord/stem metadata labels | test informed conditioning |
| M3 | each isolated stem | expected role only | compare learned and specialist stem transcription |
| M4 | mixed-role stem | one role per pass | expose bass-body/pluck or keys-melody/accompaniment alternatives |
| H1 | mix plus stems | consensus/repair after all raw passes | Sunofriend hybrid candidate |
| E1 | hosted Mirelo Studio export | user-initiated only | labelled external comparator when authorised |

The current `ai-matrix` command implements the shared quality/report schema for
completed M0–M4 AI bake-off runs from one backend, checkpoint, model config,
worker, model/runtime version and execution profile at a time. S0/H1/E1 and
cross-model-size comparison require a later outer comparison layer; they are
not silently treated as MuScriptor runs.

M4 additionally requires the same source hash, excerpt bounds and positive BPM
for every lane, exactly one requested role per pass and distinct requested
roles. Its peer-overlap report records same-pitch/onset matches and requested
versus off-role counts. This can expose role collapse or relabelling but cannot
identify a correct line or prove source separation.

`ai-label-split` may partition one completed run into the exact raw source
events carrying one model-reported label and the exhaustive complement. Its
deterministic MIDI auditions declare integer-pitch/tick quantisation and
same-pitch lifetime normalisation separately. Both derivatives and the
byte-identical full-candidate control must be retained. It is reversible label
evidence, not a new transcription, audio separation or physical-instrument
result; a zero-note requested label is blocked as no-evidence and every
non-empty split still requires listening.

The split directory also retains byte-identical request/candidate JSON controls
so Workbench can verify raw-event provenance without relying on a mutable
manifest. These controls remain private because the request can name absolute
local audio, model and configuration paths; only redacted diagnostics belong in
the browser catalog or any future contribution preview.

For M0–M4, compare small, medium and large only after their checkpoints are
explicitly accepted and pinned. For the installed 0.2.1 runtime, use the
truthfully recorded safe baseline of greedy decoding, batch size 1, beam size
1, CFG 1.0 and independent five-second chunks. Test beam search, batching and
other CFG values only as separate labelled challengers. A future runtime with
verified prelude support must use a new manifest value and separate lane.

### Evaluation dimensions

Objective evidence:

- onset, frame and offset precision/recall/F1;
- drum onset F1 and role/instrument-label correctness;
- pitch-class/chroma, absolute pitch and octave accuracy;
- contour direction, mean source support and chord-tone/non-chord-tone
  preservation;
- duplicate bursts, same-pitch overlaps, note density and maximum polyphony;
- timing p50/p95, whole-song drift and five-second-boundary errors;
- detected versus expected instruments; and
- note/pitch mutations introduced by every repair stage.

Listening evidence must be separated by question:

- **transcription:** recognisable line, missing notes, extra notes, pitch,
  octave, onset, duration, groove and phrase continuity;
- **role allocation:** correct instrument family, mixed roles kept separate,
  accompaniment versus melody and bleed/phantom notes;
- **instrument:** every note audible, consistent tone, useful register,
  ballpark source character and fit in the full mix; and
- **GarageBand handoff:** exact BPM/downbeat, no drift, correct drum routing,
  editable tracks and a named installed patch that works in context.

Automated scores are diagnostic. A candidate is promoted only after a blind
listening win on the declared question and a GarageBand check where relevant.

## Hybrid improvement strategy

### 1. Use MuScriptor as semantic evidence, not a final authority

An unrestricted pass may say that a passage contains voice, synth pad and
electric bass even when its raw notes are too dense. Retain those labels as a
proposal, then re-run only plausible groups and compare each result with its
stem and source support.

### 2. Recover the information MuScriptor cannot encode

Sunofriend should add, without altering the raw model candidate:

- source-derived velocity/expression;
- known BPM, downbeat, tuning and GarageBand tempo metadata;
- repeated-phrase evidence;
- chord/key evidence that flags rather than deletes expressive non-chord tones;
- octave/range checks by musical role; and
- specialist drum-family and stem-artifact handling.

### 3. Build role-specific consensus

Do not average all notes. Align candidates into short phrases and classify
events as:

- agreed and source-supported;
- model-only but source-supported;
- specialist-only but source-supported;
- disputed pitch/octave/boundary;
- unsupported/duplicate; or
- unresolved intended role.

The review page should show the smallest disputed musical unit first. A bass
policy may favour MuScriptor attacks while retaining Sunofriend durations; a
kick policy may do the reverse. Learn these policies per role and context, not
as a universal model ranking.

### 4. Separate sound selection from note selection

MuScriptor supplies a broad instrument family, not a GarageBand patch match.
For the selected MIDI, Sunofriend should offer:

1. one complete, dependable portable/GM control;
2. two or three installed GarageBand family candidates informed by explicit
   local full-mix history;
3. an authorised source sampler only if every performance pitch and duration
   passes the playability gate; and
4. source-fitted resynthesis as an optional layer until it beats a complete
   patch in blind listening.

No public server will copy or render Apple factory samples. Users report exact
patch names, GarageBand version, role, register and full-mix decision from their
own installation.

## Performance and speed plan

Measure cold and warm runs separately on every supported device. Record model
load time, time to first notes, total wall time, real-time factor, peak memory,
chunk count, note count and boundary warnings.

Optimisations must be introduced one at a time:

1. **Persistent local worker:** load one checkpoint once instead of starting a
   new Python process and rebuilding the model for every role.
2. **Content-addressed application cache:** key exact deterministic MuScriptor
   raw output by source content/audio layout, ordered roles, excerpt, BPM,
   decode settings, checkpoint/config/worker hashes and runtime/device identity.
   Cache only the raw candidate and its original inference-performance evidence;
   rebuild converted MIDI and every current Sunofriend post-processing artifact
   on each run.
3. **Preview/full cascade:** run small first; send only disputed roles or
   phrases to medium/large. Never call the preview the final result.
4. **Shared preprocessing:** investigate a small upstream adapter/fork that
   reuses 16 kHz audio and mel features across conditioned passes. Keep this
   behind equivalence tests because the public API does not currently expose a
   feature cache.
5. **Safe stem scheduling:** process independent stems concurrently only up to
   a measured memory limit; preserve deterministic ordering in the report.
6. **Progressive results:** stream each five-second chunk into a reviewable
   piano roll while the rest continues.
7. **Boundary-aware batching:** retain batch size 1 for the pinned 0.2.1
   baseline and report five-second boundaries explicitly. The controlled
   `batch_size=2` CPU golden preserved every auditionable MIDI but was slower
   and used more memory, so do not advance to a larger batch without a new
   separately justified experiment. Fixed five-second chunks are not a
   supported setting-comparison variable. Re-evaluate this policy if a later
   pinned runtime genuinely exposes prelude forcing.
8. **Selective beam search:** use it only on high-disagreement phrases after it
   proves a gain; never pay the full-song cost by default.

Initial targets remain relative, because the complete hardware and model-size
matrices are not yet measured: cut warm repeated-work wall time by at least
50%, avoid re-running unchanged roles, and make the small preview available
before the full-quality pass. A cross-device real-time-factor target should be
set only after the first complete hardware matrix.

The first measurable baseline is now implemented without adding a checkpoint.
Each fresh MuScriptor process writes a separate hash-pinned
`muscriptor.performance.json` so nondeterministic timing never enters the raw or
normalised candidate JSON. `sunofriend ai-benchmark` verifies comparable
completed runs and records pipeline/subprocess/inclusive-transcription RTF,
model load, first-note and first-chunk latency, chunk counts, process peak RSS,
boundary diagnostics and exact candidate/MIDI repeatability. Its cache
declaration is deliberately conservative: the worker and model are fresh per
repetition,
there is no application cache, the operating-system file cache is uncontrolled
and no cold-start or warm-model claim is made.

The first reuse boundary is now implemented separately. The
`sunofriend ai-transcribe-session` command owns one bounded worker over an
inherited Unix socket pair, loads one existing local checkpoint, executes 2–20
serial copies of one fixed source/roles/excerpt/request and exits. It opens no
listening port and is not a multi-song service, role queue, daemon or content
cache. Startup/model load is session-level evidence. Request 1 already has a
resident model but no prior transcription to reuse, so it is not labelled warm
or cold; only requests 2 and later are reused-model warm. Application cache
hits remain zero and the OS file cache remains uncontrolled.

`sunofriend ai-session-benchmark` re-verifies the private path-bearing session
tree and writes a path-free diagnostic report. A direct fresh-process comparison
is optional, but requires at least two exact comparable, repeatable fresh runs;
the existing `ai-benchmark` rejects session repetitions so the two timing
contracts cannot be mixed. Final worker shutdown re-hashes the fixed source,
checkpoint and model config; each request is byte-matched to the startup
template, and the read-only verifier rechecks the pinned worker and template.
Neither command runs a
selection, promotion, mutation, download or licence-acceptance step. The report
still exposes content hashes and detailed runtime identity, so path-free does
not imply anonymous or cleared for publication.

The bounded-session golden now passes and remains separate from application
caching. The next execution boundary is also implemented explicitly:
`ai-transcribe --application-cache-dir PRIVATE_DIR` performs a read-through
lookup for one deterministic MuScriptor request. A miss runs a fresh subprocess
and atomically stores only the verified raw candidate and its original
fresh-process performance artifact. A verified hit creates a new immutable
run, copies those artifacts without hard links, starts no worker, loads no
model, executes no inference and reruns current Sunofriend quality, expression
and MIDI derivation. A corrupt or inconsistent entry fails closed; it never
silently falls back to inference. The dedicated cache root is owner-only mode
`0700` and must sit outside every immutable run-output tree. Concurrent
identical misses publish one winner; a loser is `miss-verified-existing`, which
retains its own inference timing but is not the `miss-stored` benchmark control.

`sunofriend ai-cache-benchmark` verifies one `miss-stored` run and at least two
serial `verified-hit` runs without launching a model. Its path-free report
keeps current lookup/materialisation/post-processing/pipeline timing separate
from the copied origin-inference timing. This is neither resident-model reuse
nor the Workbench FluidSynth preview cache, and the operating-system file cache
remains uncontrolled. The private 15-second Lidl M2 gate now passes: one
`miss-stored` run took `6.295317 s`, while two true no-worker/no-model/
no-inference hits had a `1.077984 s` median pipeline time (RTF `0.071866`) and
an observed hit/miss ratio of `0.171236`. All 107-note raw, normalized, base
MIDI, expression, quality and program artifacts were identical. These are
end-to-end observations on one machine under an uncontrolled OS cache, not an
accuracy improvement or a general speed guarantee.

## Deferred Phase 7 community feedback system

“Feedback from all web users” must mean **feedback from every user who freely
chooses to contribute**, not silent collection from every visitor.

This section remains the design boundary for a later opt-in phase. Phase 5.4
and 5.5 are local-only and add no account, public upload, review-ingestion or
telemetry endpoint. Building an interface that is useful for the individual
musician comes before collecting community data.

### Three contribution levels

| Level | Sent to Sunofriend | Default | Use |
| --- | --- | --- | --- |
| Local only | nothing | yes | private songs, personal profile and corrections |
| Review telemetry | candidate/artifact hashes, blind choices, error tags, edit diff, timing and optional DAW/hardware metadata | explicit opt-in per submission | aggregate comparison and regression gates |
| Golden donation | approved 10–15 s audio/MIDI excerpt, rights/licence declaration and the same review data | separate explicit consent | public benchmark or later training after moderation |

Raw filenames, paths, account email, lyrics and full songs are excluded from
ordinary review telemetry. A hash is not automatically anonymous: rare content
or a linked account may still make a record identifiable. Pseudonymous records
must therefore be treated as personal data and kept separately from account
details, following the ICO's current
[pseudonymisation](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-sharing/anonymisation/pseudonymisation/)
and [data-minimisation](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-protection-principles/a-guide-to-the-data-protection-principles/data-minimisation/)
guidance.

Before a public beta, publish a plain-language privacy notice, purposes,
retention periods, deletion/export route, processor list and contact. Complete
a DPIA/security review when the concrete hosting design is known. This plan is
an engineering boundary, not legal advice.

### Review experience

Use one clear task per page and randomise candidate identities. The source is a
reference, not a candidate. Include a dependable hidden control and, where
appropriate, a deliberately weak anchor. This follows the useful structure of
the ITU's [MUSHRA subjective-audio method](https://www.itu.int/dms_pubrec/itu-r/rec/bs/R-REC-BS.1534-1-200301-S%21%21PDF-E.pdf),
adapted for musical correctness rather than codec quality.

Required controls:

- sample-accurate, level-matched switching and looped 5–15 second excerpts;
- repeated-beat audition for drums and a role-appropriate phrase for pitched
  instruments;
- source-only, candidate-only and full-mix views;
- plain explanations of what the listener should judge;
- explicit `equivalent`, `neither`, `cannot tell` and `not my expertise`
  choices;
- free text plus structured error tags;
- a final review summary before submission; and
- a downloadable signed JSON copy for the contributor.

The browser can ask for optional experience level, listening device, DAW and
software version, but it should not require unnecessary identity or demographic
data. Repeat a small number of controls to estimate within-listener consistency.
Do not discard novice feedback: report cohorts separately when expertise makes
a material difference.

### Minimum feedback schema

Each append-only review event should contain:

- schema, review ID, created time and consent version;
- public golden ID or local content-derived candidate IDs;
- source/candidate/model/checkpoint/config hashes and licence lane;
- task type, role, excerpt duration, BPM/key/tuning and source quality tags;
- randomised presentation order and control/anchor policy;
- all candidate ratings, pairwise choice, confidence and error tags;
- optional corrected MIDI hash and note-level add/delete/move/resize/velocity
  diff;
- optional GarageBand/DAW, patch, OS, hardware and listening context;
- processing timings and warning counts; and
- an immutable zero-effects section proving that submission changed no local
  audio, MIDI or model artifacts.

### Storage and service boundary

- Keep local personal profiles in SQLite/JSON under an explicit user-selected
  directory.
- Use a small authenticated append-only API and relational database for public
  review events; relational queries suit candidates, roles, users/consent and
  repeated ratings better than DynamoDB at this stage.
- Use S3-compatible object storage only for separately consented golden audio,
  MIDI and rendered controls; encrypt it, use short-lived signed URLs and keep
  licences/retention beside each object.
- Store public benchmark assets separately from private/pending donations.
- Never accept a browser path, arbitrary server-side URL or executable sampler
  preset as a feedback upload.

Start with GitHub-hosted static cleared reviews plus a narrow review-ingestion
API. Do not start with arbitrary public song upload or hosted model inference.

### How feedback changes the product

Feedback is not training data by default. Apply it in this order:

1. publish aggregate, role-stratified scorecards and failure examples;
2. detect regressions between Sunofriend versions and model/config variants;
3. rank which candidate a user should audition first, while retaining all raw
   alternatives;
4. learn local/global role-specific patch and repair preferences from explicit
   choices;
5. use disagreement and low confidence for active selection of the next review
   excerpt; and
6. only after rights, quality and consent checks, build a versioned correction
   dataset for a small selector/error-correction model.

Because the published MuScriptor training dataset and training pipeline are not
released and its weights are non-commercial, the first learned Sunofriend
component should be a small independent candidate selector or note-error
classifier trained on rights-cleared corrections—not an untracked fine-tune of
MuScriptor. Any trained artifact needs its own data card, licence, held-out
goldens and no-participant leakage test.

## Phase 4 carry-forward register

Phase 4's negative listening results are evidence, not unfinished bugs. Its
remaining ideas are carried forward only where a later increment can give them
a narrow question and a human listening gate:

| Phase 4 item | Later home | Gate before work |
| --- | --- | --- |
| Query/learned isolation for mixed stems | 5.1 discovery and 5.3 hybrid consensus | One clearly audible 10–20 second role target; unchanged source and specialist MIDI remain controls |
| Neural denoise or de-reverb | Optional 5.3 challenger | Must improve downstream pitch/boundary evidence and blind musical recognition, not just source energy |
| Neural/DDSP timbre | Phase 6 creative arrangement, then Phase 7 only if justified | MIDI fixed first; complete playable patch mandatory; identical performance and full-mix listening |
| Audio Unit model hosting | Optional Phase 7 cross-DAW work | Only after a distributable sound wins; it is not required for model research |
| Generated missing samples | Phase 6/7 instrument experiment | Generated zones labelled separately, rights/licence recorded and every required pitch audibly checked |
| `pkg_resources`/resampy warning | 5.2 controlled runtime benchmark | Resolve through a measured dependency update; never hide the warning |
| Oversized CLI/match/bundle orchestrators | Incremental maintenance across Phases 5–7 | Characterization tests first; typed workbench operation now starts the separation, shared role registry comes before 5.1, bundle/match stages precede cross-DAW work |

The rejected source sampler is not scheduled for more automatic refinement on
the same performance. The preferred complete patch and unchanged-source MIDI
remain the mandatory controls for later work.

## Delivery increments

### 5.0 — Local Workbench vertical slice and shared contract

- Add `sunofriend workbench PROJECT --open`, bound to loopback and offline by
  default.
- Build one project home, one stem workspace, time-synchronised
  source/candidate loops and explicit main/optional/correct/reject choices
  using existing artifacts only.
- Store decisions in append-only local SQLite and export the existing reviewed
  JSON contract; display exactly what an optional contribution would contain.
- Pin the current upstream MuScriptor behaviour and extend the shared manifest
  with prelude-forcing, batch, beam, CFG and model-size fields.
- Success: a user can understand and select one stem result without model
  knowledge, file-URL restrictions or network access; a second launch restores
  the complete project state.

Started 19 July 2026:

- [x] add the loopback-only `workbench` command, per-launch token and visible
  local/no-upload state;
- [x] discover hash-pinned existing artifacts or accept an explicit catalog,
  cap the normal view at three and demote `possible`/`uncertain` variants;
- [x] add project setup, one workspace per stem, shared loop positions,
  candidate/outcome/problem choices and MIDI download;
- [x] append decisions to local SQLite, restore them after restart and export a
  complete local review plus an exact path/audio/MIDI/note-free contribution
  preview with submission disabled;
- [x] validate the first slice against the real private Slayyyter Phase 4
  artifact layout without copying private media; and
- [x] add content-addressed role-neutral preview rendering, synchronized
  source/A/B/C switching at a shared second position, explicit-selection
  whole-arrangement audition and a selected-MIDI GarageBand handoff ZIP;
- [x] extend the shared AI manifest with validated batch, beam, CFG, model-size,
  model-config hash and explicit unsupported-prelude fields;
- [x] attach path-free AI quality, label, boundary and runtime diagnostics to
  discovered candidates and block no-evidence or severe decoder failures from
  selection while retaining their raw evidence;
- [x] reverify source, MIDI, generated media and SoundFont hashes at the point
  of serving, rendering and handoff rather than trusting startup discovery.

Deferred local-Studio quality gate, targeted for Phase 5.5 rather than the
completed Phase 5.0 slice:

- [ ] upgrade Workbench playback from media-element time synchronization to
  decoded, sample-accurate switching. Generic blind exact-window,
  fixed-window sample-RMS-matched packages now exist through
  `midi-ab-review`; this deferred item is specifically the Workbench playback
  engine.

### 5.1 — Full-mix/conditioned bake-off

- [x] Add a model-neutral quality/report schema for one controlled
  backend/checkpoint matrix and a per-track gate through `sunofriend ai-matrix`.
- [x] Run M0–M3 with the current small model on one immutable private golden.
- [x] Compare discovery labels with stem names and role-conditioned stem lanes.
- [x] Add duplicate-burst, instrument-leakage and five-second-boundary reports.
- [x] Add strict M4 one-role-per-pass lanes and same-source role-overlap
  diagnostics for a reviewed mixed-role bass excerpt.
- [x] Add an exact model-label partition with an exhaustive complement and
  unchanged full-candidate control.
- [x] Complete the private M4 listening gate; no engineering result is a
  promotion.
- [x] Prepare the private bass/keys/vocal safe-lane page with three candidates
  per role, zero-based 15-second timing and one neutral renderer per row.
- [x] Complete the private safe-lane listening gate and record explicit
  role-by-role decisions; `none usable` remains a valid result.
- Success: the review explains whether full-mix discovery provides useful
  labels even when raw notes are rejected.

First matrix, 19 July 2026:

- source: private, reconstructed 15-second Lidl full-mix golden already used in
  Phase 1; all generated evidence remains under ignored `work/` paths;
- runtime: `muscriptor-small` 0.2.1, checkpoint
  `bbd482c786b895cf7d8f44185073d951adae2ebb8a66f82ca84cd1f84569549c`,
  config `3008fc481e4a1cd978e337eb3759260c270892204db5039235ac939e1f42aeb2`;
- M0 repeated the known 1,912-note failure, including 1,818 drum-labelled notes
  plus severe duplicate/onset/polyphony burst metrics, and is correctly blocked
  from audition/selection;
- M1, conditioned on discovered labels, reduced the result to 169 notes with
  no severe decoder code; four of five discovered label families remained;
- M2 produced 107 notes but substituted clean electric guitar for expected
  labels, so label conditioning is guidance rather than a guaranteed output
  schema;
- isolated M3 bass, keys and voice lanes produced 19, 181 and 39 notes without
  a severe gate; the `other_kit`/drums lane produced zero notes and is retained
  as diagnostic no-evidence; and
- same-pitch/onset overlap offers useful role-allocation clues—for example M1
  piano overlaps 61/106 notes with M3 keys and M1 sax overlaps 28/38 with M3
  voice—but is explicitly not an accuracy score or automatic winner.

This establishes that conditioning can rescue this excerpt from a decoder
burst, not that M1 is musically correct. Promotion still requires listening.

Private safe-lane listening result, 19 July 2026:

- bass: M2 metadata-conditioned `electric_bass` (34 notes) is main; isolated
  M3 (19) needs correction and M1 `electric_bass` (13) is rejected;
- keys: isolated M3 (181) is main and M1 `acoustic_piano` (106) is optional;
  the M2 `clean_electric_guitar` subset (14) needs correction;
- vocal melody: the row outcome is `equivalent`, with isolated M3 (39) main
  and M1 sax-labelled melody (38) optional in the arrangement; the saved data
  does not identify a narrower equivalence claim, and the M2 flute-labelled
  line (44) needs correction;
- every selected candidate was explicitly confirmed in full-mix context. The
  three selected same-AI-origin comparisons have 21, 0 and 11 exact-pitch
  onset matches, but zero pair covers at least 80% of both tracks, so none is a
  substantial doubled-line warning; and
- the five-track GarageBand handoff preserves every selected MIDI byte and
  excludes source audio, review notes and rejected/correction candidates.

The saved routing is role-specific: the M2 bass partition is main, isolated M3
is main for keys and vocals, and M1 remains optional for keys and vocals. The
vocal row outcome is `equivalent`, but the saved data does not identify a
pair. No single M1/M2/M3 route becomes a global default. Carry these five
saved selections into Phase 5.2 and 5.3 as controls, not defaults: runtime,
cache or later checkpoint results cannot replace them without the same
role-stratified listening gate.

First M4 mixed-role matrix, 19 July 2026:

- source: the private 16-second Slayyyter bass/pluck learned target retained
  from the reviewed Phase 4 cleanup; audio and full artifacts remain ignored;
- controls: small MuScriptor 0.2.1 with the same checkpoint/config, worker,
  greedy batch-1/beam-1/CFG-1 execution, source, excerpt and `113.000096` BPM;
- the `electric_bass` body pass produced 41 requested-label notes and no
  off-role label;
- the clean-guitar-requested pluck pass produced 43 notes: 14 requested
  `clean_electric_guitar` and 29 off-role `electric_bass` notes;
- the two complete passes matched 40 notes within the 80 ms same-pitch/onset
  tolerance—40/41 of the body pass and 40/43 of the pluck pass—so conditioning
  largely relabelled or reproduced one line rather than demonstrating two
  isolated roles; and
- the exact guitar-label derivative retains 14 notes and an exhaustive 29-note
  complement. The unchanged 43-note pass remains the full control;
- private listening selected the complete 41-note bass-conditioned pass as the
  bass main and the complete 43-note clean-guitar-conditioned pass as the
  rhythm/pluck main, and confirmed both together in the dry full-mix proxy;
- the earlier 30-note Phase 4 body partition was marked needs-correction, while
  the 11-note Phase 4 pluck partition and 14-note label derivative were
  rejected. The advanced 29-note complement was retained without a decision;
- the two selected mains still match on 40 notes. The review therefore says
  the complete conditioned contours are musically useful with contrasting
  sounds, not that MuScriptor separated bass body and pluck. The rejected
  14-note label derivative occupied roughly the final five-second chunk, so
  model labels must not be treated as role-isolation evidence; and
- the verified GarageBand handoff contains exact copies of the two selected
  MIDI files plus a dry GM proxy. It is a private 16-second golden handoff, not
  a full-song or complete-instrument deliverable.

The immediate product consequence is now implemented as an overlap-aware
finalisation check. When two selected tracks from one source substantially
share pitch/onset events, the Workbench shows the counts and requires both
choices to be confirmed in full-mix context before handoff. It preserves both
files and allows intentional layering; overlap remains a warning, never an
accuracy score or an automatic deduplication rule. The same increment adds a
fresh-path, browser-free private review archive without starting an HTTP
server.

### 5.2 — Model-size and performance bake-off

- [x] Add a hash-pinned fresh-process performance artifact with separate audio
  preparation, model load, inclusive transcription, first-note, first-chunk,
  chunk-count and process-RSS evidence; keep it outside deterministic candidate
  JSON. Inclusive transcription covers iteration of MuScriptor's lazy result,
  including backend preprocessing, condition construction and decoding.
- [x] Add `ai-benchmark` as a read-only, path-free comparator over at least two
  immutable runs with strict source/requested-and-actual-excerpt/BPM/roles/
  device/checkpoint/config/worker/execution/runtime equality and exact
  candidate/MIDI repeatability. Require source-frame-derived duration, nested
  pipeline/subprocess/worker timing and non-overlapping repetition windows.
- [x] Run the existing small MuScriptor 0.2.1 CPU M2 golden twice. Both runs
  produced byte-identical 107-note MIDI. Median pipeline time was `5.189 s`
  (RTF `0.346`), worker subprocess time `5.115 s`, inclusive transcription
  `3.655 s` (RTF `0.244`), model load `0.291 s`, first completed note `1.580 s`,
  first completed chunk `2.541 s`, and median peak process RSS
  `1,142,669,312` bytes (about `1.06 GiB`). The first/later wall ratio was
  `1.117` under an uncontrolled OS file cache.
- [x] Reverify that the five Phase 5.1 selection hash
  `1dce19ce7595a72b8417225b8d23679e0fc92e53581807ccf9db6ea929d7709c`
  and handoff ZIP hash
  `7824e25850037821287fd77337ae9e8ad2d61cea2cbd2ea57e3b2f92e0c532f8`
  remain unchanged; the new full-candidate MIDI also matches the earlier M2
  byte for byte.
- [x] Add a bounded parent-owned exact-repeat worker and
  `ai-transcribe-session`. It permits only one fixed
  source/roles/excerpt/request, 2–20 serial requests, one inherited Unix socket
  pair and one model load before exit; it is not a production multi-song
  service or content cache.
- [x] Add `ai-session-benchmark` to reverify session lifecycle, hashes,
  one-model reuse, serial timings, cumulative RSS and exact candidate/MIDI
  repeatability. Request 1 is resident-model but not warm/cold evidence; only
  requests 2+ are reused-model warm. Optional comparison requires at least two
  exact comparable fresh-process controls. `ai-benchmark` remains
  fresh-process-only and rejects session repetitions.
- [x] Run the existing 15-second small-CPU M2 golden through three bounded
  requests and two new final-worker fresh controls. All five produced the same
  107-note candidate JSON and byte-identical MIDI. Model load was `0.279 s`,
  request-1 pipeline `3.983 s`, warm pipeline median `3.681 s` (RTF `0.245`),
  warm request median `3.651 s`, and warm inclusive-transcription median
  `3.641 s`. Fresh pipeline and transcription medians were `5.193 s` and
  `3.731 s`, for observed warm/fresh ratios `0.709` and `0.976`. Final process
  RSS high-water was `1,157,365,760` bytes. These are end-to-end observations
  under an uncontrolled OS cache, not proof that model reuse alone caused the
  difference; cumulative RSS is not per-request allocation or leak proof.
- [x] Add an explicit content-addressed MuScriptor application cache after the
  reuse golden passes. One deterministic miss runs fresh and stores only the
  verified raw candidate plus origin performance; hits run no worker/model/
  inference and rebuild current MIDI. Invalid entries fail closed. Cache timing
  is separate from model reuse, Workbench preview rendering and the OS cache.
- [x] Run the existing private 15-second M2 golden as one `miss-stored` run and
  at least two `verified-hit` runs, write a path-free `ai-cache-benchmark`, and
  reverify the five reviewed selections and GarageBand handoff before broader
  integration. The miss was `6.295317 s`; hit median was `1.077984 s` (RTF
  `0.071866`; hit/miss ratio `0.171236`). All 107-note raw and derived controls
  matched. Selection and handoff hashes remain
  `1dce19ce7595a72b8417225b8d23679e0fc92e53581807ccf9db6ea929d7709c`
  and `7824e25850037821287fd77337ae9e8ad2d61cea2cbd2ea57e3b2f92e0c532f8`.
- [ ] Benchmark MPS only when the installed runtime exposes it, and CPU/CUDA on
  separately identified contributed hardware.
- [ ] After separate explicit checkpoint acceptance, pin medium and large one
  at a time; neither is authorised by this baseline.
- [x] Add `ai-setting-compare` as a read-only, fresh-process-only one-variable
  diagnostic. V1 accepts repeatable current beam-size 1→2 or batch-size 1→2
  arms under their explicit contracts and rejects session/cache/legacy
  evidence, overlapping windows, every extra setting difference and every
  automatic promotion.
- [x] Run beam 1 and beam 2 sequentially on the same private small-CPU golden,
  retaining exact timing, memory, chunk, boundary, label, note-payload, MIDI and
  derived-artifact evidence under an uncontrolled operating-system file cache.
  Both two-run arms were exact. Beam 1 produced 107 notes; beam 2 produced 124,
  with 90 same-pitch/same-label onset matches within 80 ms. The ordered runs
  observed a beam-2 pipeline median of `32.787408 s` versus `5.282282 s`
  (`6.207054×`), inclusive transcription of `31.177499 s` versus `3.824411 s`
  (`8.152235×`) and peak RSS of `1,489,354,752` versus `1,173,610,496` bytes
  (`1.269037×`). Both candidates remain `review-required`; performance and
  overlap do not select a winner. The hardened v2 path-free report also treats
  expression MIDI as auditionable output; its SHA-256 is
  `8177d3245856d97a26d0c1e5c289a0bb5eddbb257579fdb414456cd9f0db2fb0`.
- [x] Add generic `midi-ab-review`/`midi-ab-resolve` tooling for one or more
  exact source-time, non-overlapping 0.5–15 second loops. Both candidates use
  the same hash-pinned dry FluidSynth executable, SF2, zero-based GM program,
  sample rate and gain. The required `--midi-time-at-source-start` pins the
  common candidate-to-source origin on a source sample frame; no alignment is
  inferred. Only the louder candidate is attenuated to the quieter fixed-window
  sample RMS, both windows must reach -60 dBFS RMS, and the source stays
  unlevelled. A secret random per-loop nonce remains only in the answer key,
  with a public commitment in the seed. The auto-looping page scopes its shared
  playhead per unit and requires source/A/B heard checkboxes plus an explicit
  outcome. Resolution requires the original unchanged package and accepts only
  review status/count, heard, choice and notes changes, rejecting swapped slots
  or altered timing/focus/geometry. Neither command edits MIDI, selects a
  winner, promotes a preset or changes a default. This is sample RMS, not LUFS,
  true peak or perceived loudness.
- [x] Generate and verify the private beam-1/beam-2 package under ignored
  `work/ai-bakeoff/lidl-phase5-beam-rms-review-v4/`. Commitment
  `b5e3556f70560c86cbe79fbcc4bb7d9a8362c67824beed203bffa0675162dd10`
  covers three exact 48 kHz windows: 0.20–3.50, 3.50–7.50 and 11.60–15.00
  seconds, with explicit origin `0`, GeneralUser-GS program 4/SF2 hash
  `9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe`
  and FluidSynth 2.5.6 hash
  `93589cfaf73a5aaaaf37dd313be4d815fb2ced8f0e8ae641b0e1d0026e546911`.
  All final A/B PCM RMS pairs match to six decimals and are unclipped.
- [x] Run and resolve the private beam-1/beam-2 listening review before
  selecting any preset. The 0.20–3.50 and 11.60–15.00 second loops were judged
  equivalent; 3.50–7.50 seconds marginally preferred beam 1. Beam 2 won zero
  loops. The resolver reported zero MIDI edits, source mutations, selection
  changes, promotions and default changes. Beam 1 therefore remains the
  conservative default.
- [x] Add and run `ai-setting-compare --setting batch-size` as a strict batch
  1→2 fresh-process comparison with beam fixed at 1/greedy, sampling disabled
  and the independent five-second chunk policy fixed. Both repetitions in each
  arm were exact. Both settings produced the same 107-note payload, base MIDI,
  expression MIDI and every auditionable MIDI, with 107/107 onset overlap;
  candidate JSON/raw changes were execution/progress provenance only. No
  listening review is required because the musical output is identical. The
  ignored private comparator report has SHA-256
  `ef221cf6908ecf49f08c69286e4eaf0808f589daf35d869b34c84267a8639483`.
- [x] Record the batch experiment's bounded CPU resource evidence. In the
  ordered runs, batch 2 pipeline median was `8.792904 s` versus `5.282282 s`
  (`1.664603×`), inclusive transcription `7.058380 s` versus `3.824411 s`
  (`1.845612×`) and peak RSS `1,566,097,408` versus `1,173,610,496` bytes
  (`1.334427×`). The first progress event represents one completed chunk for
  batch 1 and two for batch 2, so its timing is not directly compared. MPS is
  unavailable in the installed runtime, and fixed five-second chunks are not a
  supported comparison variable. The report records zero mutations,
  selections and promotions; retain batch 1 as default.
- Success: choose `preview`, `balanced` and `best` presets from measured Pareto
  results; do not make large the default merely because its paper score is
  higher.

### 5.3 — Hybrid phrase consensus

- [x] Share one deterministic one-to-one note-alignment primitive across the
  matrix, setting comparator, Workbench overlap diagnostic and hybrid report.
- [x] Align distinct S0 specialist, M1 full-mix-label and M3 conditioned-stem
  vocal candidates on the exact 15-second Lidl excerpt. Hash-check every
  supplied payload and state the missing lineage explicitly: M1's full mix is
  caller-associated with the song but its derivation is unverified; M3's
  original pre-projection MIDI is named but not supplied for payload checking.
- [x] Publish raw source support, role, boundary/duration, octave, repetition,
  cross-phrase, lane-only and duplicate evidence without creating or selecting
  MIDI. Project only schema-owned path-free phrase evidence, reject contradictory
  mutation/status/policy records, recompute segmentation/repetition geometry,
  and record chord evidence as unavailable rather than inferring an unpinned
  timeline.
- [ ] Build blind phrase reviews from ranked disagreements and apply only
  explicit choices.
- [ ] Define a reproducible source-lineage manifest that pins all mix inputs,
  excerpt geometry, filter graph, gain, codec and output before upgrading M1's
  same-song relationship from caller-supplied to verified.
- [ ] Add an exact hash-pinned chord timeline when one is available for the
  same excerpt; do not derive it from the full-song PDF by assumption.
- [ ] Repeat the evidence/report slice for bass and keys before constructing
  a role-specific H1 challenger.
- Success: bass, keys and vocal hybrid candidates beat their current primary
  on predeclared listening questions without worse timing drift or duplicate
  leakage.

### 5.4 — Interactive Result Explorer and GarageBand Pack Composer

Status: **complete; the per-stem compare timeline, full-song
selected-arrangement explorer/mixer, GarageBand Pack Composer v1 and explicit
disputed-range phrase-review bridge are implemented**.

Build this as an evolution of the completed 5.0 Workbench rather than a second
application:

1. [x] define a versioned, hash-pinned per-stem timeline projection derived
   from existing source and candidate artifacts, including source duration,
   explicit alignment limits, bounded waveform display data and per-track MIDI
   note geometry; project-level BPM, key, tuning and downbeat remain in the
   existing project payload;
2. [x] add the first read-only compare-role view with one shared playhead,
   source waveform, coloured MIDI lanes, loop shading and progressive
   provenance detail;
3. [x] add a read-only selected-arrangement timeline, then zoom and arrangement
   navigation without changing the selected source or MIDI artifacts;
4. [x] add audition-only visibility, mute, solo and gain plus source-only,
   selected-MIDI, hybrid and main-MIDI presets; manual changes form an unsaved
   custom audition rather than a persisted custom-mix preset;
5. [x] preserve the existing explicit main/optional/correct/reject decision state
   and make clear that no metric, process or visible default selects a winner;
6. [x] add a persistent GarageBand basket whose checked contents are separate
   from the musical decision, keeping the existing source-audio-free exact-MIDI
   ZIP as the safe default; and
7. [x] link disputed timeline ranges to the existing phrase-review pages without
   adding direct MIDI editing in this increment.

The first vertical slice uses one private golden plus portable synthetic
fixtures. It consumes already completed outputs and does not require a new
checkpoint, persistent inference daemon or public account.

Success means a user can hear every displayed source and MIDI candidate through
one understandable timeline, compare several processes for one role, assemble
and audition an explicit arrangement, see exactly what will enter the ZIP and
import the unchanged selected MIDI into GarageBand. Reloading restores choices;
source audio remains excluded unless separately requested; no automatic winner
or network operation is introduced.

### 5.5 — Local Studio hardening and private beta

After the 5.4 vertical slice is musically useful:

- [x] add Project Overview/Resume v1 with path-free per-stem progress, one
  explicit-state-derived next action, restart-state boundaries, focus recovery,
  retryable connection/pack-status errors and lazy advanced audio metadata;
- [x] make `none usable`/`cannot tell` deterministic no-selection barriers,
  centralise path-free role projection across browser, timeline and pack
  surfaces, add an empty-pack recovery path, and verify decisions plus a
  non-default basket across two real loopback server launches;

- replace shared-second media switching with decoded Web Audio buffers for the
  review paths that require tighter changes, while keeping the exact standalone
  blind A/B contract for promoted comparisons;
- harden long-song rendering, waveform/piano-roll virtualization, keyboard and
  accessibility controls, browser restart recovery and progress/error states;
- verify stem-only, MIDI-only, hybrid and custom mixes against one canonical
  selection manifest;
- test the pack composer repeatedly in GarageBand, including BPM, downbeat,
  selected-file hashes and optional eligible Instrument Bundles;
- display completed exact-result-cache and reused-model provenance without
  silently enabling either optimisation; and
- conduct a small private, local-only usability beta using authorised projects.

The checked Project Overview and decision-safety items are the first two
hardening increments. They do not complete decoded Web Audio, long-song
virtualization, canonical custom mixes, GarageBand/Instrument Bundle checks,
cache-provenance display or the private beta.

Success means a non-expert can complete source comparison, candidate choice,
arrangement audition and GarageBand export without editing JSON or losing work.
Phase 5.5 still has no public upload, telemetry, account or community ranking.

## Later phases

### Phase 6 — Creative arrangement and reusable MIDI

Build on the trusted explorer rather than turning Phase 5 into a DAW rewrite:

- direct piano-roll correction with a minimal, reversible edit diff;
- phrase alternatives, explicit hybrid construction and repeated-phrase reuse;
- key, BPM, tuning and downbeat transformations with alignment warnings;
- Clip v1 browsing, tagging, audition and reuse across projects;
- stem/MIDI combinations and mashup preparation; and
- instrument-choice and eligible Instrument Bundle attachment to reusable
  parts.

Success means a user can make a new arrangement from reviewed parts while the
original sources and every process candidate remain reproducible. GarageBand
continues to own final performance, patch editing and mixing.

### Phase 7 — Cross-DAW and opt-in community learning

Only after the local workflow is useful and stable:

- present complete portable controls and role-appropriate local DAW patches;
- invite compatibility testing in Logic, Ableton, FL Studio, Reaper and other
  DAWs without treating patch names as portable identities;
- publish owned/licensed goldens and randomised blind reviews with appropriate
  controls;
- add separately consented review JSON or rights-cleared excerpt submission,
  privacy/export/deletion controls and contextual public scorecards; and
- after a rights-qualified immutable dataset exists, test the smallest
  independent role-specific selector or error classifier against deterministic
  and personal-history baselines.

Success requires complete playable instrument recommendations, useful
cross-DAW imports, adequate independent reviews for each declared comparison,
no private audio in ordinary telemetry and no hidden automatic promotion.

## Promotion gates

A new MIDI path may become recommended for one role only when:

1. its raw candidate, model/config and inputs are hash-pinned;
2. silence, density, duplicate, role-leakage and timing checks pass;
3. it wins the declared blind recognition/usefulness comparison, with
   `equivalent` and `neither` retained as valid outcomes;
4. a GarageBand import preserves BPM, downbeat and full-song timing;
5. the recommended instrument plays every required note consistently; and
6. licence and rights permit the intended private, public or commercial lane.

Community majority never overrides a user's personal composition choice.
Public results should show sample counts, uncertainty and cohort/context rather
than a single unexplained percentage.

## Current implementation boundary

The usable 5.0 Workbench slice now covers project/stem decisions, cached neutral
previews, full-mix confirmation and a selected GarageBand handoff. It keeps
original MIDI unchanged and still has no upload or submission endpoint.
Phase 5.5 adds the path-free
`sunofriend.workbench-home.v1` Project Overview as the default resume surface.
Its progress, attention codes and one next workflow step come only from catalogued
candidates and explicit saved decisions/outcomes. It excludes paths, private
notes and process metrics; navigation/retry changes no selection, pack, MIDI,
audio or feedback. Decisions and the separate current pack basket survive a
restart, while playhead, loop, visibility, mute, solo and level deliberately
reset.
Its second slice makes terminal `none_usable`/`cannot_tell` outcomes selection
barriers while retaining append-only history; only a later main/optional event
reactivates exportable selection for that stem, without resurrecting older
options. A shared privacy guard
rejects new path-like role tags and substitutes `custom role` for legacy values
before browser state, contribution preview, timelines, archive names and proxy
MIDI metadata are produced. A two-launch loopback test verifies that decisions
and a non-default pack basket survive a new token while GET requests remain
effect-free. An empty composer now routes back to Overview.
Phase 5.4 now adds canonical, path-free per-stem and selected-arrangement
timelines with zero automatic selection/ranking effects. The arrangement view
shows every unique source stem and only current explicit main/optional MIDI,
with temporary source-only, selected-MIDI, hybrid and main-MIDI audition
presets. Its visibility, mute, solo, attenuation, loop and playhead state is not
persisted and never changes review events, overlap evidence, cache identity or
handoff bytes. Pack Composer v1 adds a separate persistent, revision-guarded
basket for unchanged current selected MIDI, the dry arrangement proxy and
explicitly opted-in source audio. It uses path-free hash-pinned contracts,
rejects stale builds and leaves the original selection ZIP compatible.
The explicit phrase-review bridge separately verifies the lead S0/M1/M3
diagnostic, source, candidates, review package and ranked geometry, then offers
temporary loop shortcuts and a private capability-scoped link to the matching
review unit. It creates no decision, candidate ranking, hybrid MIDI, pack item
or contribution field.
MuScriptor execution settings and checkpoint/config hashes are now explicit,
and immutable M0–M4 small-model matrices publish per-role quality,
five-second-boundary, label-stability, cross-lane and strict M4 peer-overlap
diagnostics. Exact model-label partitions retain their unchanged control and
complement.
Workbench discovery attaches the same path-free evidence and prevents severe
or zero-note candidates from becoming main/optional choices.

The private M4 bass/pluck gate, Workbench overlap/archive follow-through and
three-row M1/M2/M3 bass/keys/vocal review are complete. The evidence supports
role-specific routing and retained alternatives, not a universal model winner.
The Phase 5.2 fresh-process, bounded exact-repeat, one-variable beam and
one-variable batch measurement gates are complete. Three resident-model
requests and two new fresh
controls reproduced the same candidate JSON, 107-note count and MIDI byte for
byte; only requests 2+ are true reused-model warm requests. The measured
warm/fresh ratios are
observations rather than causal proof, and the harness is still not a
production multi-song service. The separate opt-in application content cache
and its private golden are complete; broader integration remains pending. The
cache must not be conflated with resident-model reuse, the Workbench
preview cache or the uncontrolled OS cache. Medium or large checkpoints, other
devices and any public contribution remain later, separately authorised work.
Beam 2 changed the private golden's musical output. In these ordered runs it had
substantially longer observed timings and a higher observed peak RSS; its
generic same-renderer, same-patch, fixed-window sample-RMS-matched review
builder and resolver are now complete. The hardened three-window private
package is generated, verified and resolved. Two loops were equivalent and the
middle 3.50–7.50 second loop marginally preferred beam 1; beam 2 won no loop
and the resolver reported no effects. Beam 1 stays the conservative default.
This review policy does not claim LUFS, true-peak or perceived-loudness equality
and leaves the source reference unlevelled.

Batch size 2 did not change the private golden's canonical note payload or any
auditionable MIDI, so it needs no listening review. It was slower and used more
memory than batch 1 in the ordered CPU comparison. The first progress events
represent different completed-chunk counts and are deliberately not compared.
The installed runtime exposes no MPS device, fixed five-second chunks remain
unchanged, and batch 1 stays the default.

Keep sample-accurate level-matched short-loop review as a requirement before a
promoted comparison. The current media-element switching is deliberately
described as time-synchronised, not sample-accurate. The standalone blind A/B
package uses exact common source-frame windows, but does not yet replace
Workbench media elements with decoded sample-accurate switching.

Project Overview/Resume v1 and decision/restart/privacy hardening are the first
completed local-Studio slices. A private Slayyyter fixture correctly failed
closed when its adjacent AI worker no longer matched the completed run, so the
restart contract was verified with a portable two-server fixture rather than
weakening provenance. The immediate next engineering work is tighter decoded
playback and the next authorised private usability pass. The
explicit disputed-range bridge now
opens the exact existing short phrase review without selecting or editing MIDI.
Pack Composer v1 keeps checked file contents
separate from musical main/optional choices and preserves the source-audio-free
safe default. The next slice must keep the core Sunofriend result-space
contract: several analytical and AI candidates, no automatic winner, immutable
provenance, explicit human choices and exact selected-MIDI export.

## Primary sources

- [MuScriptor paper](https://arxiv.org/pdf/2607.08168)
- [Official MuScriptor code and runtime](https://github.com/muscriptor/muscriptor)
- [MuScriptor medium model card, terms and limitations](https://huggingface.co/MuScriptor/muscriptor-medium)
- [Mirelo Audio-to-MIDI product description](https://mirelo.ai/models/audio-to-midi)
- [MuScriptor's consent-gated analytics implementation](https://github.com/muscriptor/muscriptor/blob/302343e8992bdfc619f77f1988168374ed5d675d/web/src/analytics.ts)
- [ITU-R BS.1534 MUSHRA recommendation](https://www.itu.int/dms_pubrec/itu-r/rec/bs/R-REC-BS.1534-1-200301-S%21%21PDF-E.pdf)
- [ICO pseudonymisation guidance](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-sharing/anonymisation/pseudonymisation/)
- [ICO data-minimisation guidance](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-protection-principles/a-guide-to-the-data-protection-principles/data-minimisation/)
