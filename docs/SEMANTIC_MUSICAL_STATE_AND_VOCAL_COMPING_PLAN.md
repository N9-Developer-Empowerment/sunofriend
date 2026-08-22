# Semantic Musical State, vocal comping and training plan

Prepared: 19 August 2026

Status: canonical forward programme plan. It supersedes MIDI-first assumptions
in the earlier vocal-comping implementation plan without changing or erasing
the implemented v1 pilot. No model installation, training, cloud upload or
production feature is authorised by this document.

## Outcome

Sunofriend should add two durable product features beside its existing
track-to-MIDI workflow:

1. **Remix a track:** create an editable alternative arrangement or production
   that makes an intentional change while retaining musical relationships the
   owner recognises from the source.
2. **Replace an AI vocal partly or fully:** use repeated human recordings,
   canonical lyrics, reference phrasing and explicit listening decisions to
   produce a reviewed human/AI vocal stem, with optional gentle correction.

These are repeatable product capabilities, not a single-song project. A whole
song is one coverage milestone, not the programme goal.

Development proceeds through music made **in anger**. Every two to four days,
the current build should be used on an authorised real song or meaningful song
section, producing a playable artifact that can be taken into the next music
session. Listening feedback from that use selects the next smallest product
change. The same track may improve over several cycles, but multiple tracks
must be rotated so the system does not overfit one voice, mix or composition.

Success therefore means:

- new tracks or substantial track sections are created throughout development;
- each cycle leaves an audible remix, vocal replacement, edit map, comparison
  or honest retained failure that informs the next cycle;
- partial product value is available before model research is complete;
- repeated use across songs becomes easier and more musically useful; and
- MIDI conversion remains available as an independent feature and optional
  evidence source.

Technical model completion, embedding similarity and MIDI/F0 self-agreement do
not establish either new feature.

## Nature-of-work key

Every task, experiment, review screen and roadmap item must declare one or more
of these labels:

| Label | Nature | What it means in Sunofriend |
| --- | --- | --- |
| **D** | Deterministic analysis or editing | Fixed code and rules process audio, timing, lyrics, manifests, edit maps, similarity evidence or waveform assembly. No learned weights are consulted or changed. |
| **I** | Pretrained-model inference | Existing frozen model weights analyse or generate audio. Examples include separation, pitch/transcription models, forced alignment, MERT features or ACE inference. The model is **used**, not trained. |
| **T** | Model training | An optimisation job changes learned weights using Sunofriend-labelled data. This includes a ranker, adapter, conditioner, LoRA or broader encoder fine-tune. |
| **H** | Human musical review | The musician listens, records, chooses, rejects, identifies retained musical anchors or decides that no result is acceptable. This is the musical authority. |

Hybrid steps show every applicable label, for example **D+I+H**. Existing stem
separation and most transcription are **I**, even when they run locally. Fixed
alignment, edit-map assembly and crossfades are **D**. A job becomes **T** only
when weights are updated from data.

Bounded training starts on day one as a parallel experimental lane. It does
not wait for the deterministic product work to finish, and the product work
does not wait for a trained model. Early training proves the data, loader,
objective, split and checkpoint pipeline on deliberately small problems. A
trained checkpoint earns a product role only after it beats deterministic and
frozen-model controls on composition-disjoint real-song evidence.

The optional decision is therefore **promotion and scaling**, not whether to
begin learning experiments. Large encoder or generator training, paid cloud
work and private-audio upload remain separately gated.

## Direction decision

The next core object is a structured, time-aligned **Musical State**, not
`song -> MIDI`, one monophonic target melody or one universal embedding.

```text
authorised audio + stems + lyrics + optional MIDI/notes
                         |
                         v
                 independent evidence encoders
                         |
                         v
               MUSICAL STATE (versioned)
               | shared song clock and structure
               | harmony, bass, groove and motifs
               | lyric, phrase and phoneme evidence
               | Vocal Performance State subgraph
               | style, timbre and production evidence
               | confidence, ambiguity and provenance
                         |
             +-----------+------------+
             |           |            |
             v           v            v
         comparison   MIDI/DAW      bounded generation
         and review   adapters      or audio editing
             |           |            |
             +-----------+------------+
                         v
          editable remix or reviewed replacement vocal
                 repeatable across real songs
```

The state retains temporal sequences and hierarchies. Song-level vectors may
support retrieval, but cannot replace bar-, phrase-, word-, phoneme-, motif-
and event-level evidence.

### Vocal Performance State

`sunofriend.vocal-performance-state.v2` is a vocal-specific subgraph containing:

- immutable waveform regions in common song coordinates;
- canonical lyrics and reviewed phrase hierarchy;
- editable word/phoneme timing with uncertainty;
- continuous log-F0, voiced confidence and tracker disagreement;
- consonants, breaths, guttural closures and other non-pitched events;
- timing, energy, phrase shape and held-vowel evidence;
- level, clipping, crackle/dropout, noise, room and timbre descriptors;
- optional learned temporal representations; and
- optional notes/MIDI as derived evidence.

There is deliberately no single truth layer. Known lyrics are canonical. An AI
reference may supply intended phrasing and continuous melodic-contour evidence,
but is not ground truth for timbre, breath, consonants, emotion or every pitch
tracker decision. Human listening remains the selection authority.

## Evidence already established

Retain:

- immutable sources, hashes, rights, lineage and failure receipts;
- public broad/core-four separation and bounded private research evidence;
- role-specific transcription, Workbench and GarageBand handoff;
- browser pickup recording and full-song coordinate receipts;
- reviewed phrase windows and canonical lyrics;
- continuous pYIN/RMVPE evidence and tracker disagreement;
- STT as uncertain phonetic evidence only;
- explicit `no_acceptable_candidate`, pickup and AI-fallback states; and
- separate source, suggestion, decision, render and correction artifacts.

Negative results guide the new plan:

- full-song ACE generation did not preserve the current remix fixture's source
  identity;
- `extract`/`complete` did not produce a useful identity scaffold;
- rough sung F0 produced fragmented MIDI and circular agreement evidence;
- grouped-other identity was polyphonic and octave-spanning even when bass
  transcription was useful;
- discrete vocal notes followed harmonics and percussive closures; and
- better separation alone did not create musical understanding.

For the current remix benchmark, owner listening places accompaniment motifs,
harmonic motion and register texture ahead of the scratch vocal as identity
evidence. Bass and groove remain important; the scratch vocal supplies lyric,
phrasing and structure only where evidence supports it. This hierarchy is
fixture-specific and must not become a universal rule.

## Programme priorities

Four tracks share the state schema but have independent delivery and research
gates:

1. **Vocal-comping product — D+I+H:** deliver useful partial and whole-song
   human/AI vocal replacements.
2. **Remix product — D+I+H:** deliver bounded, editable remix operations that
   preserve named source relationships.
3. **Analysis laboratory — D+I+H:** compare transparent analysis with frozen
   pretrained models against real musical decisions.
4. **Parallel learning — T+I+H:** train small, auditable challengers from day
   one while real-song use exposes better labels, bottlenecks and targets.

Both product tracks and the learning track begin immediately. Neither product
waits for a general Musical State encoder or generative fine-tune. Only
explicit decisions become labels: passive playback, recording count and dwell
time never become training data.

### Work classification at a glance

| Stage | Primary nature | Model status |
| --- | --- | --- |
| A0-A1 | D+H | No model required. |
| A2-A3 | D+I+H | Frozen alignment, pitch or representation models may advise; no training. |
| A4-A5 | D+H | Deterministic source-map assembly, browser workflow and listening. |
| A6 | D+I+H | Frozen analysis may define a bounded correction; no training required. |
| B0-B1 | D+H | Deterministic benchmarks and controlled variants. |
| B2 | D+I | Use frozen pretrained features; weights do not change. |
| B3 | D+H | Compare evidence with held-out musician decisions. |
| C0 | D+T+H | Day-one training scaffold, tiny-set overfit and explicit label contract. |
| C1-C3 | T+I+H | Weight-changing challengers run in parallel; product promotion and scaling are gated. |
| D0-D1 | D+I+H | Deliver the first remix controls with deterministic assembly and/or frozen models. |
| D2 | T+I+H | Optional learned conditioning after repeated bounded remix evidence. |
| D3 | D+I+H | Product and provenance boundary; generated audio remains a labelled source. |

## Track A - audio-native vocal comping

### A0 - freeze the v1 pilot and build the v0 state [D+H]

- Preserve all existing MIDI-first projects and decisions as historical v1
  evidence.
- Inventory the reviewed *The Heart Sees* phrases, AI reference, human takes,
  browser attempts and recorder-quality findings.
- Mark reviewed MIDI targets as optional historical evidence.
- Bind original and repaired recorder files separately.
- Represent crackle and periodic dropout as acquisition evidence, not musical
  failure.
- Publish `sunofriend.musical-state.v0` from existing reviewed evidence only;
  do not invent learned fields.

Exit gate: one path-free manifest reproduces the known phrase/reference/take
identities and can be evaluated with no MIDI file.

### A1 - audio-native phrase workspace [D+H]

Implement the next smallest useful vertical slice:

1. consume one reviewed phrase window, canonical lyric, reference audio and at
   least two human attempts;
2. require no MIDI;
3. show synchronized reference and attempt waveforms;
4. preserve continuous F0, voiced confidence, lyric/event timing and signal
   quality separately;
5. let the singer listen, choose, reject or record again;
6. export an explicit phrase decision and full-song-coordinate source map;
7. render no correction and make no automatic selection; and
8. use phrase one and phrase two first, with phrase three as the recorder-defect
   robustness case.

Exit gate: one phrase can be recorded, compared and chosen without MIDI, and
the result reopens with exact source identity.

### A2 - lyric, phoneme and vocal-event alignment [D+I+H]

- Use reviewed phrase bounds as hard outer anchors.
- Evaluate a singing-oriented forced aligner for word/phoneme proposals.
- Keep Whisper for possible insertions, omissions, substitutions, ad-libs and
  rough phonetic location; it cannot rewrite lyrics.
- Expose uncertain word/phoneme boundaries for listening and correction.
- Retain vowels, consonants, breaths, silence and non-lexical events.
- Prohibit word/phoneme cuts where alignment remains unresolved.

Exit gate: the AI ad-lib cannot shift later canonical phrases, and voiced and
unvoiced regions are both represented with reviewable uncertainty.

### A3 - transparent phrase comparison [D+I+H]

The deterministic baseline contains:

- continuous contour comparison in voiced vowel regions;
- pitch centre, interval direction and local stability;
- word/phoneme timing displacement and bounded time warp;
- phrase coverage, early/late endings and held-vowel strength;
- consonant, breath and unvoiced-event placement; and
- clipping, crackle/dropout, level, noise, room and timbre continuity.

Missing F0 during a consonant is not pitch error. Octave ambiguity remains
uncertainty. Vibrato, scoops and portamento remain contour evidence rather than
deviations to flatten. Dimensions remain separate and hidden until the singer
has listened. They order what to compare; they never select a take.

Exit gate: all reviewed phrases can be assessed without target MIDI, the
phrase-two `wants to` closure is not penalised as a missing note, and recorder
damage is visible separately from performance evidence.

### A4 - adjacent assembly and join review [D+H]

- Choose a broad human base where one exists.
- Substitute only explicitly selected phrase regions.
- Preserve pre/post handles and place cuts in reviewed low-risk regions.
- Predict joins from waveform, breath, level, room and timbre continuity.
- Provide previous/current/next and backing-mix auditions.
- Support boundary, crossfade and bridging-pickup repair.
- Render from an exact sample-frame edit map with zero source mutation.

Exit gate: two adjacent human/AI choices render with an accepted join and exact
provenance.

### A5 - whole-song web workflow [D+H]

The resumable page contains:

- a sectioned song map with prepare, attempts, choice, join and lock states;
- canonical lyrics with neighbouring context;
- backing, continuous reference/melody and metronome cues;
- microphone level check and repeat pickup recording;
- neutral attempt labels and phrase/context playback;
- explicit `use`, `record again`, `keep AI`, `defer` and
  `no acceptable take` actions; and
- analysis revealed only after listening.

Recording count, playback and dwell time are not labels.

Exit gate: every phrase can be recorded, deferred, selected or retained as a
labelled AI fallback across multiple sessions, and the source map reproduces a
complete dry comp at original song zero.

### A6 - optional gentle correction [D+I+H]

- Operate only on a reviewed dry comp or explicitly selected phrase.
- Derive a continuous target from reviewed reference contour and selected-take
  pitch centre, not automatic note segmentation.
- Mask consonants, breaths, unvoiced events and unresolved tracker regions.
- Preserve vibrato, scoops and transitions with bounded movement.
- Disclose pitch/time movement and affected regions.
- Render an immutable derivative beside the uncorrected comp.

Exit gate: A/B review finds improvement without unacceptable robotic, formant,
articulation or identity change. `No safe correction` requests another pickup.

## Track B - representation laboratory

### B0 - fixed benchmarks and holdouts from day one [D+H]

Prepare owner-only, path-free manifests for:

- several composition-disjoint songs;
- 8-16 bar remix excerpts and reviewed vocal phrases;
- source stems, lyrics, section maps and source-coordinate windows;
- owner-marked identity anchors and permitted invariances;
- explicit phrase choices and rejection reasons; and
- hard negatives: same style, chords, singer or production without the same
  phrase/composition identity.

All splits are song- and composition-disjoint. Excerpts from one song cannot be
distributed across train and test.

### B1 - controlled variants [D]

Bind deterministic recipes for gain/EQ/codec, compression/microphone colour,
stem balance, pitch transpose, time stretch, alternate singer,
instrumentation, wrong lyric, wrong melody, same chords/different motif and
truncated or damaged endings.

Every variant states which factors should remain close and which should change.

### B2 - frozen representation bake-off [D+I]

Start with genuinely exposed and reproducible features:

1. F0 + phoneme + timing deterministic baseline;
2. chroma/bass/groove and existing MIDI baselines where relevant;
3. MERT temporal/layer-pooled representations;
4. mHuBERT or other singing/speech representations after licence audit;
5. ACE-Step 5 Hz semantic audio codes;
6. ACE VAE/source-audio latents; and
7. acoustic/timbre features used only for join continuity.

ACE DiT hidden states, cross-attention summaries and text-conditioning vectors
are a later instrumentation experiment, not the first dependency. Cover and
repaint paths do not prove that one accessible joint text/audio space is fit for
phrase alignment.

Preserve model, checkpoint, layer, pooling, frame rate, source hash and
extraction settings. Do not average all challengers into one score.

### B3 - admission gate [D+H]

Evaluate:

- controlled same/different retrieval;
- temporal localisation of changed regions;
- invariance to irrelevant production changes;
- sensitivity to wrong lyric, melody, timing and endings;
- motif/bar/phrase retrieval against hard negatives;
- agreement with explicit held-out human choices;
- incremental value beyond deterministic evidence; and
- runtime, VRAM, storage, licence and privacy.

A representation enters Musical State only when it improves a held-out
human-relevant task, remains time-local enough, reports uncertainty and stays
independently visible/removable. Plausible clusters and cosine thresholds alone
are insufficient.

If no frozen challenger beats the transparent baseline, do not purchase large
training compute. Small diagnostic heads may continue locally to test whether
the objective or representation can learn at all, but they remain research
challengers and cannot enter product ranking or conditioning.

## Track C - training strategy

### C0 - day-one training scaffold and label contract [D+T+H]

Begin with the reviewed decisions already available, then add labels through
useful work. The first job is intentionally small and may overfit a tiny
development set. Its purpose is to prove:

- deterministic, hash-bound example loading;
- song- and composition-disjoint split enforcement;
- one reproducible training step and decreasing development loss;
- checkpoint save, resume and inference;
- a shuffled-label corruption control;
- comparison with a fixed heuristic or frozen-feature baseline; and
- a result manifest that never claims musical authority.

Training on too little data is allowed as a pipeline and learning-curve test;
trusting or promoting that model is not.

Persist only explicit decisions:

Persist only explicit decisions:

- pairwise phrase comparison;
- base / usable alternative / reject / cannot tell;
- bounded rejection reason;
- pickup request and result;
- join accepted/rejected and adjustment;
- correction preferred/equivalent/rejected; and
- remix identity anchor retained/lost/uncertain.

Private notes, absolute paths and filenames are excluded from training exports
by default.

### C1 - rolling personal vocal ranker [T+I+H]

Train the first provisional ranker as soon as the day-one scaffold is sound,
using whatever explicit reviewed comparisons are available. Publish a learning
curve and uncertainty warning, not a quality claim. Retrain at fixed snapshots
as new real-song decisions arrive; never update silently during a review.

The model predicts which two attempts deserve comparison first; it does not
choose the source. It may enter a private comparison-ordering experiment only
after it beats the deterministic and frozen controls on a song-disjoint holdout.
A stronger promotion gate remains a provisional minimum of 200 explicit
pairwise comparisons across at least five authorised songs, with one whole
song held out, adequate class balance and repeated-choice consistency. Revisit
that threshold from observed learning curves rather than lowering it to make a
checkpoint pass.

This small head is the correct first useful training task for the 12 GB RTX
laptop.

### C2 - Musical State adapters [T+I+H]

After frozen features pass B3, train small task-specific heads:

- temporal projection to a shared beat/bar/phrase clock;
- identity-anchor retrieval;
- polyphonic motif/register representation;
- bass/harmony/groove probes;
- lyric/phoneme alignment; and
- confidence/ambiguity calibration.

Use hard negatives deliberately and require ablations. Do not fine-tune a
waveform generator at this stage.

### C3 - broader encoder or generative adapter [T+I+H]

Only after small adapters succeed should the project fine-tune a
multi-resolution encoder or an ACE conditioning/generation adapter. A public
scorer requires opt-in, rights-cleared recordings from multiple singers and
song/singer-disjoint tests. A model trained on one singer is personal, not a
general singing-quality model.

An ordinary style LoRA is not accepted as source-identity conditioning or take
selection. Any generative adapter must beat a prompt-, lyric-, reference- and
seed-matched zero-state control.

### C4 - lawful data and recording programme [D+H]

One deeply annotated song is sufficient to debug schemas and evaluation, but
not to support a general model claim. A pilot needs several
composition-disjoint songs, multiple authorised versions and hundreds of
reviewed windows. Broader training requires owner-created, commissioned,
explicitly licensed or partnered material whose terms permit the intended use.

For each new owner-created song, retain where available:

- rough and polished accompaniment, stems and source MIDI;
- alternate instrumentation, tempo and key variants;
- guide, intentionally imperfect and improved vocals;
- several complete takes plus browser phrase pickups;
- canonical lyrics, section map and production intention;
- owner-marked identity anchors and permitted invariances; and
- deliberately non-matching hard negatives.

This factorised recording protocol is more valuable than an unstructured
collection of finished mixes. It creates pairs that expose what stayed the
same, what changed and what the owner actually preferred. Private recordings
remain local unless a separate cloud/training approval names the exact assets,
provider, retention and purpose.

## Track D - identity-preserving remix and generation

### D0 - remix identity state [D+H]

For each benchmark excerpt retain:

- accompaniment motifs and register layers;
- bass/harmony motion;
- groove and section-energy relationships;
- lyric/phrase/structure evidence;
- owner-named identity anchors; and
- factors explicitly allowed to change.

### D1 - smallest bounded operation [D+I+H]

Use the state first for retrieval, MIDI/Clip assembly or one role/region edit.
Do not repeat an unconstrained full-song bake-off.

### D2 - learned conditioning challenger [T+I+H]

In increasing cost/risk:

1. retrieve and assemble reviewed MIDI/Clip material;
2. map admitted state features into an existing ACE conditioning channel;
3. train a lightweight cross-attention or side conditioner while freezing ACE;
4. parameter-efficiently tune selected ACE blocks; and
5. consider a larger generator only with a sufficiently large lawful paired
   dataset.

Each experiment renders matched zero-state and current-reference controls and
fails if every owner-recognised anchor is lost.

### D3 - generated vocal/duet boundary [D+I+H]

Authentic comp and generated performance remain separate lanes. Generated
audio is a distinct source class with consent, training provenance and visible
edit-map labelling. A human/AI duet is valid when chosen by the user, but is not
described as a fully human vocal.

## Compute plan

### One programme, two execution hosts

This task owns the programme and its decisions. The Mac and Windows checkouts
are execution surfaces, not separate projects or competing roadmaps.

- The Mac checkout is the integration, private source-of-truth, listening,
  review, edit-map and final-render host.
- The Windows RTX checkout is a bounded GPU worker for ACE, frozen encoders,
  feature extraction and approved training jobs.
- Source, model and result identities cross machines through Git commits plus
  path-free manifests and hashes, never by assuming the same absolute path.
- Private audio, checkpoints, generated media, credentials and training caches
  stay outside Git.
- A Windows result has no musical authority until its manifest and artifacts
  are verified and heard through the integration workflow.
- There is one canonical plan in Git. Host-specific notes may describe setup
  or execution but cannot redefine product gates.

#### Migration checkpoint - 19 August 2026

- The earlier Windows remix task and its complete substantive discussion have
  been reviewed and incorporated into this plan.
- That task reported no application-code change; its only uncommitted change
  was the original semantic musical-state training plan.
- The shared GitHub remote currently exposes no ACE/remix/semantic-state
  branch, so no claim is made that other Windows checkout changes have been
  transferred.
- The Windows host is not currently exposed as a saved project to this Mac
  task. Any additional local-only ACE work must pass the branch transfer gate
  below before implementation resumes.

This task is the programme and decision owner. The earlier task is historical
context, not a second roadmap.

#### Windows branch transfer gate

Before new RTX implementation begins, preserve the earlier ACE work:

1. record the Windows checkout's current branch, HEAD, remote and dirty files;
2. keep user audio, checkpoints, caches and outputs untracked;
3. place intended source, documentation and tests on a dedicated
   `codex/semantic-musical-state-rtx` branch;
4. push that branch to the shared GitHub remote;
5. inspect its commits and diff from the Mac integration checkout;
6. merge or cherry-pick only after tests, provenance and model boundaries are
   understood; and
7. retain rejected ACE runs as private benchmark evidence rather than Git
   artifacts.

If the Windows work is still uncommitted, do not recreate it from memory or
copy the entire checkout. Commit only the intended code/docs/tests on the
Windows branch, then transfer it through Git. If it is already committed under
a different local branch, push that exact branch first and rename only after
its history is visible.

#### GPU worker request/result contract

Every cross-machine experiment should eventually use two small versioned
documents:

- `sunofriend.gpu-worker-request.v1`: repository commit, experiment ID,
  authorised asset hashes, model/checkpoint identities, feature layers,
  window coordinates, expected outputs, resource ceilings and stop rules;
- `sunofriend.gpu-worker-result.v1`: request hash, worker environment, model
  hashes, output hashes/shapes, timings, peak GPU/RAM use, warnings and exact
  completion/failure status.

Neither manifest contains absolute private paths, credentials, raw prompts with
private content or audio. A result can report technical completion but cannot
select a representation, vocal take, remix or comp.

### Local Mac

- source store, recording, orchestration, listening and decisions;
- final edit maps, waveform assembly and GarageBand handoff;
- lightweight already-qualified runtimes; and
- review of every RTX/cloud result before it gains authority.

### RTX 4080 Laptop GPU with 12 GB VRAM

- frozen-model inference and batch representation extraction;
- controlled benchmarks and short-window experiments;
- small ranking/projection/temporal heads;
- ACE-Step non-XL inference; and
- reduced-scale reproducibility before paid compute.

The worker consumes path-free manifests and returns hash-bound results. It is
never the only copy of source or review evidence.

The official ACE-Step built-in LoRA guide currently states 16 GB VRAM minimum
and 20 GB recommended. Do not promise official-style ACE training on 12 GB.
Low-VRAM community training paths require a separate code/licence/runtime audit.

### Cloud gates

Cloud compute is research capacity, not a prerequisite for either product
feature. Local C0 training starts immediately. Cloud C1-C3 are separate
authorisations for larger training or unusually large inference experiments;
they are never unlocked merely because a deadline has arrived.

**C0 - no paid compute:** use local hardware for schemas, frozen extraction,
small heads, deliberate tiny-set overfit tests and rolling provisional
checkpoints.

**C1 - bounded 24-48 GB single GPU:** only when a local reduced-scale run has a
deterministic loader, decreasing loss, checkpoint/resume, corruption test and
held-out baseline. Fix model/container hashes, maximum steps, wall time,
storage, egress, cost ceiling, automatic shutdown and stop rule.

**C2 - 48-80 GB or multi-GPU encoder:** only after a small adapter proves the
labels/objective and the held-out metric correlates with owner judgement.

**C3 - generator adaptation:** only after Musical State succeeds, a lawful
paired dataset exists, a parameter-efficient route is tested first and a
zero-state counterfactual is defined.

Cloud availability is not permission to upload private audio. Each job requires
explicit provider, region, dataset, retention, deletion and budget approval.
Encrypt storage, minimise uploads, download/hash outputs and record deletion.

## Twelve-week rolling delivery programme

Twelve weeks is a planning horizon, not an all-or-nothing punt and not a march
toward one showcase song. The unit of progress is a short real-song cycle.

### Standard two-to-four-day cycle

1. **Choose real musical work [H]:** select one authorised track and one
   immediate creative aim: replace a phrase, improve a join, retain a motif,
   change one instrument or make one bounded remix.
2. **Run the current product [D and/or I]:** use only capabilities that exist at
   the start of the cycle. Produce an audible artifact, not just metrics.
3. **Use it in the music session [H]:** hear it against the track, take it into
   GarageBand where useful and record what helped, failed or created more work.
4. **Train or update one bounded challenger [T]:** use only the frozen label
   snapshot available at the start of the experiment. A no-change checkpoint
   or failed learning curve is valid evidence.
5. **Compare three ways [D+I+T+H]:** where applicable, hear the deterministic
   control, frozen-model challenger and trained challenger without letting any
   score select the music.
6. **Make one bounded product improvement [D or I]:** fix the smallest repeated
   bottleneck exposed by the listening evidence; integrate a trained component
   only if its promotion gate has passed.
7. **Render again and retain evidence [D+H]:** compare before/after, preserve the
   source map and failure evidence, and select the next track or section.

At least one playable track artifact or honest retained failure should emerge
every few days. Cycles alternate between vocal comping and remixing, while the
existing MIDI route remains available whenever it helps the music.

### Weeks 1-2 - establish the cadence and the training baseline

- **Cycle 1, vocal [D+H]:** one no-MIDI phrase decision, browser pickup and
  exact source map on the current song.
- **Cycle 2, remix [D+I+H]:** one bounded 8-16 bar change using deterministic
  scaffold/retrieval and an existing frozen model only where useful.
- **Cycle 3, transfer [D+H]:** repeat the more useful operation on a different
  authorised track and record where assumptions fail.
- Define `musical-state.v0`, `vocal-performance-state.v2`, the method labels and
  the rolling delivery ledger from evidence these cycles actually require.
- **Training lane [D+T]:** freeze song-disjoint splits, run the tiny-set overfit,
  shuffled-label and checkpoint/resume tests, then train the first provisional
  vocal ranker and remix-anchor probe from existing explicit decisions.
- Keep every trained output marked `research_challenger`; nothing selects a
  take, edit or remix.

### Weeks 3-4 - add alignment and repeatable controls

- Deliver two or more further song cycles, alternating the two features.
- Add reviewed word/phoneme/non-pitched-event proposals [D+I+H].
- Add one reusable bounded remix control such as structure-aware replacement,
  role substitution, Clip/MIDI assembly or region-level regeneration [D/I].
- Compare every new method with the previous playable artifact, not only with
  an abstract benchmark.
- Retrain the small challengers on a fixed new label snapshot [T], evaluate on
  an untouched song and publish the learning curve, control comparison and
  failure reasons.

### Weeks 5-6 - assemble longer regions and test frozen models

- Deliver adjacent vocal assembly and join review on real songs [D+H].
- Extend the remix operation to a longer section while retaining named musical
  anchors [D+I+H].
- Run the frozen-representation bake-off [D+I] alongside product use; admit a
  feature only when it explains or improves repeated human decisions.
- Train small projection, ranking and join-risk heads on admitted and baseline
  features [T]; keep prior checkpoints as controls rather than overwriting
  them.
- Stop a representation experiment without stopping either product lane.

### Weeks 7-8 - move from sections toward song-scale workflows

- Extend the vocal page into a resumable multi-section workflow [D+H].
- Add remix history, comparison, rollback and editable handoff [D+H].
- Continue producing tracks every few days and collect explicit labels only
  from deliberate decisions [D+H].
- Decide whether any trained ranker or probe has earned a private advisory role
  [T+H]. If not, it remains a challenger while training and product delivery
  continue.

### Weeks 9-10 - improve continuity and scale only what has earned it

- Produce longer dry comps and remix assemblies with exact edit maps [D+H].
- Use pickups, boundary repair and deterministic crossfades before training a
  model to hide correctable joins [D+H].
- Continue bounded local training [T]. If one challenger repeatedly beats the
  controls, run one pre-approved larger adapter experiment locally or on a
  capped cloud GPU and use it only as a challenger in the next real-song cycle.
- A failed scaled experiment returns that model family to the local research
  lane; it does not suspend product delivery or erase earlier checkpoints.

### Weeks 11-12 - demonstrate repeatability, not a single grand finale

- Show both features working at useful partial or full-song scope across more
  than one authorised track.
- Deliver a reviewed human/AI vocal replacement workflow with labelled fallback
  and optional bounded correction [D+I+H].
- Deliver a bounded editable remix workflow that retains owner-named anchors
  [D+I+H].
- Summarise which deterministic methods, frozen models and trained components
  earned product, advisory-only or research-only status through real musical
  work.

The twelve-week outcome is a stronger pair of repeatable features plus a body
of newly created music. It is acceptable for the precise technical route to
change as long as the destination, provenance and listening authority remain
stable.

## Evaluation ladder

| Gate | Required outcome |
| --- | --- |
| A [D+H] | One phrase is recorded, compared and chosen with no MIDI input. |
| B [D+H] | Two adjacent choices render with an accepted join and exact edit map. |
| C [D+H] | A resumable page covers multiple song sections and explicit AI fallback decisions. |
| D [D+H] | A partial or complete dry comp is useful in a real music session. |
| E [D+I+H] | Gentle correction improves selected regions without identity damage. |
| F [D+I+H] | A deterministic or frozen-model feature improves a held-out human-relevant task. |
| G [D+I+H] | A bounded remix retains a named owner identity anchor and is editable. |
| H [T+I+H] | A trained challenger beats deterministic, frozen and zero-state controls without obscuring provenance. |

Gates are cumulative product increments, not one final pass/fail event. Each
useful increment may ship into the next real-song cycle. A result on one track
does not establish generality, so gates are revisited across new songs. Gates
F-H cannot delay delivery through A-D or the deterministic/frozen remix lane.

## Decision rules

Continue to larger training only when:

1. labels and splits are composition-disjoint and reproducible;
2. learned evidence beats deterministic/frozen baselines;
3. improvement survives hard negatives and ablation;
4. metrics correlate with owner decisions;
5. the downstream result repeatedly reduces work on real music sessions; and
6. rights, terms, privacy and budget are recorded.

Stop or reframe when:

- the model learns singer, microphone, loudness, mix or genre instead of the
  intended musical/performance relationship;
- same-song split leakage inflates results;
- a larger model improves metrics but not owner recognition or comp choices;
- conditioning is indistinguishable from a zero-state control;
- alignment cannot localise the phrase safely;
- correction damages consonants, formants, vibrato or identity;
- cloud spending compensates for an undefined task; or
- recording another browser pickup is the faster and better musical answer.

## Immediate next three delivery cycles

### Cycle 1 - vocal replacement on the current track [D+H]

- implement the minimum no-MIDI phrase decision and exact source map;
- record one or more fresh browser pickups;
- render a playable replacement phrase against the backing; and
- record the musical and workflow feedback before adding analysis.
- In parallel [D+T], freeze the first label snapshot, prove tiny-set overfit,
  checkpoint/resume and shuffled-label failure, then train a provisional
  pairwise ranker that cannot select a take.

### Cycle 2 - bounded remix on one current track [D+I+H]

- name the musical identity anchor and the one permitted change;
- create one deterministic control and, only where it helps, one frozen-model
  challenger;
- train one small identity-anchor retrieval/projection challenger [T] on the
  frozen development split;
- render an editable comparison for real musical use; and
- retain the accepted result or exact reason neither is useful.

### Cycle 3 - transfer to another track [D+H]

- repeat whichever feature exposed the most useful next bottleneck;
- test whether the workflow survives a different voice, arrangement and mix;
- evaluate both trained challengers on the untouched track, against the
  deterministic, frozen and previous-checkpoint controls;
- improve one bounded product problem; and
- publish the next playable artifact and source/provenance record.

In parallel, formalise `musical-state.v0`, `vocal-performance-state.v2`, the
method labels and rolling delivery ledger from these cycles. Small local
training [T] begins with Cycle 1, but every checkpoint remains a challenger
until held-out real-song evidence earns promotion. Large training, paid cloud
jobs, private-audio upload and unconstrained full-song generation remain
unapproved by this plan.

## Current primary references

- [ACE-Step 1.5 official repository](https://github.com/ace-step/ACE-Step-1.5)
- [ACE-Step 1.5 official inference documentation](https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/INFERENCE.md)
- [ACE-Step 1.5 official LoRA training tutorial](https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/LoRA_Training_Tutorial.md)
- [ACE-Step 1.5 technical report](https://arxiv.org/abs/2602.00744)
- [MERT technical paper](https://arxiv.org/abs/2306.00107)
- [SOFA singing-oriented forced aligner](https://github.com/qiuqiao/SOFA)
