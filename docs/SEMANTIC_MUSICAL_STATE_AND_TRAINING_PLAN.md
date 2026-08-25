# Sunofriend semantic musical-state and training plan

Prepared: 19 August 2026

The companion
[Semantic Musical State, vocal comping and training plan](SEMANTIC_MUSICAL_STATE_AND_VOCAL_COMPING_PLAN.md)
extends this programme with the audio-native vocal-comping architecture. Keep
the two documents aligned when their shared Musical State contract changes.

Status: proposed programme plan based on the complete repository history, the
current Windows/ACE-Step branch, the reference-conditioned generation trials,
the accompaniment-first listening results and the vocal-comping research.

This plan supersedes the assumption that either full-song generation or a
single monophonic MIDI melody is the next primary route. It does not erase the
existing product, separation, MIDI, Workbench, provenance or vocal-comping
work. Those systems become the experimental and delivery shell around a new
learned music-understanding layer.

## 1. Product goal

Given an owner-authorised rough song, target lyrics and a creative direction,
Sunofriend should preserve the musical identity the owner recognises while
allowing deliberate changes to style, affect, instrumentation and performance.
It should produce an editable arrangement that can be finished in a DAW and a
reviewed path to a human vocal. Generated audio may be used as a temporary
creative reference; the final export must truthfully disclose whether any
generated waveform remains.

For the current golden song, musical identity is not defined by the scratch
vocal. Owner listening established the following initial hierarchy:

1. grouped accompaniment/other: motifs, harmonic motion and register texture;
2. bass: recognisable harmonic and rhythmic identity;
3. drums: groove and section energy, with affect intentionally transformable;
4. scratch vocal: lyric, phrasing and structural evidence only when confidence
   supports it, not automatic melody authority.

The programme succeeds only when the owner hears a non-accidental connection
to the source and can continue production from the result. Model completion,
embedding similarity and MIDI/F0 self-agreement do not meet the goal.

## 2. What the existing work has established

### Assets to retain

- A mature local-first product contract for editable MIDI and a MIDI-derived
  song-interpretation WAV.
- Strong immutable-source, hash, lineage, rights, review and failure-receipt
  infrastructure.
- Public broad-vocal and core-four separation, plus bounded private six-role
  evidence and extensive separator qualification machinery.
- Multiple transcription, role-specific MIDI, correction, arrangement,
  Workbench and GarageBand handoff paths.
- A vocal-comping design that correctly separates authentic comping from
  generated-voice rendering and already exposes the need for lyric/phoneme
  alignment.
- A Windows RTX 4080 Laptop GPU development environment and a working
  ACE-Step 1.5 service/adapter.
- A rigorous reference-conditioned generation specification and listening
  gate that rejects technically valid but musically unrelated output.

### Negative results that now guide the architecture

- ACE-Step Base and Turbo produced technically valid full-song candidates but
  failed the source-identity gate on the current fixture.
- Track-level `extract`/`complete` did not produce a useful identity-preserving
  scaffold.
- Treating rough sung F0 as intended melody produced random, fragmented MIDI.
  The reported F0/MIDI agreement was circular evidence, not accuracy.
- Upper-voice extraction from grouped other did not preserve the recognised
  accompaniment. Bass transcription was useful; grouped-other identity appears
  polyphonic and octave-spanning.
- Better separation does not by itself solve musical understanding. It provides
  cleaner evidence for the new layer.

### Programme correction

The next core object is not `song -> MIDI` and not one universal embedding. It
is a structured, time-aligned **Musical State** that preserves several kinds of
evidence independently and can expose confidence and ambiguity.

## 3. Target architecture

```text
authorised audio + stems + lyrics + optional MIDI/notes
                         |
                         v
                 evidence encoders
                         |
                         v
              MUSICAL STATE (versioned)
              | acoustic/source evidence
              | beat, bar, phrase and section clock
              | harmony and bass motion
              | polyphonic motifs and register layers
              | groove and rhythmic relationships
              | lyric/phoneme/phrase alignment
              | vocal identity and performance evidence
              | style, timbre and production evidence
              | confidence, ambiguity and provenance
                         |
             +-----------+------------+
             |           |            |
             v           v            v
        comparison    editable MIDI   generative conditioning
        and review    and DAW state   or constrained rendering
             |           |            |
             +-----------+------------+
                         v
             owner-recognised arrangement
                         |
                         v
             human takes, comp and final audit
```

The state must retain temporal sequences and hierarchies. A song-level vector
may be included for retrieval, but it cannot replace bar-, phrase-, motif- and
note-level evidence. ACE VAE latents, semantic music encoders, lyric embeddings
and cross-attention states are candidate inputs, not automatically trusted
definitions of musical meaning.

## 4. Evaluation contract before training

Training must not begin until a fixed benchmark makes failure measurable.

### 4.1 Golden identity benchmark

Prepare owner-only, path-free manifests for at least:

- the current canonical rough song;
- 8-16 bar excerpts covering verse, chorus and a transition;
- source accompaniment, grouped other, bass, drums and any authorised original
  stems;
- target lyrics and section map;
- owner-marked identity anchors: motif, bass movement, harmonic event, groove
  or structural relationship, with approximate time ranges;
- deliberate invariances: what may change without losing identity; and
- hard negatives: musically plausible material of the same style that is not
  the source song.

Add more songs before making a generalisation claim. All train/validation/test
splits must be song- and composition-disjoint. Excerpts from one song cannot be
scattered across splits.

### 4.2 Controlled representation set

For each eligible source, create or collect authorised variants:

- level/EQ/codec change;
- stem balance change;
- pitch transposition;
- time stretch and tempo change;
- different singer over the same arrangement;
- different instrumentation preserving musical identity;
- cover or rearrangement preserving selected anchors;
- same genre but different composition;
- same chords but different motif/groove; and
- same motif with deliberately changed harmony or form.

Every transformation receives an immutable recipe and label identifying which
factors should remain close and which should change.

### 4.3 Primary measures

- owner blind source-identity judgement with the heard anchor named;
- identity-anchor retrieval against hard negatives;
- bar/phrase correspondence and motif retrieval;
- bass/harmony/groove probe accuracy on reviewed labels;
- invariance and sensitivity under the controlled variants;
- lyric/phrase alignment error where reviewed timing exists;
- usefulness of derived MIDI or arrangement state in GarageBand; and
- time required for the owner to reach a finishable arrangement.

No single cosine-distance threshold is a product acceptance gate. Automated
measures shortlist and diagnose; owner listening decides musical identity and
production usefulness.

## 5. Phased programme

### Phase 0 - consolidate the proven baseline

1. Review and merge or explicitly retain the current Windows/ACE-Step branch.
2. Freeze the rejected ACE runs, accompaniment-first results and register-bank
   listening decisions as benchmark evidence.
3. Publish a `musical-state.v0` schema containing only existing reviewed
   evidence, confidence and provenance; do not invent learned fields yet.
4. Add a benchmark ledger that can reference private audio by asset ID/hash
   without committing it.

Exit gate: one command can build the path-free benchmark manifest and reproduce
the existing baseline features without generation or training.

### Phase 1 - representation laboratory using frozen models

Instrument ACE-Step outside the Sunofriend core process and extract, where the
code genuinely exposes them:

- VAE latents for aligned windows;
- text/lyric conditioning vectors;
- DiT inputs and selected intermediate hidden states;
- cross-attention summaries rather than private raw prompt content; and
- source/reference conditioning tensors and masks.

Compare these with independent frozen music/audio encoders admitted under the
normal checkpoint and licence process. Evaluate temporal representations, not
only mean-pooled song vectors.

Build probes that answer concrete questions:

- Can the representation retrieve another version of the same motif?
- Does transposition remain recognisable while a different song with the same
  genre remains distant?
- Can a small linear or shallow temporal probe recover bass motion, chord
  changes, downbeats, phrase boundaries and owner anchor labels?
- Which layers preserve composition and which mostly preserve timbre or mix?

Exit gate: a written representation report identifies the best frozen features
for each Musical State field and demonstrates improvement over current chroma,
F0 and MIDI baselines on held-out excerpts.

Stop condition: if no frozen representation beats the deterministic baselines
or owner retrieval, do not purchase large training compute merely to scale an
undefined target. Improve labels, negatives and representation access first.

### Phase 2 - first learned Musical State adapters

Train small task-specific heads on frozen encoders:

- temporal projection into a common bar/phrase clock;
- contrastive identity-anchor retrieval;
- polyphonic motif and register-layer representation;
- bass/harmony/groove heads;
- factor confidence and ambiguity estimates; and
- lyric/phoneme alignment when suitable reviewed data exists.

Start with adapters, projection heads or a small temporal transformer. Do not
fine-tune the waveform generator. Use hard negatives deliberately: same genre,
same chord loop, similar instrumentation and adjacent sections from different
songs.

Exit gate: held-out song retrieval and owner-blind ranking improve materially
over every frozen baseline, with ablations showing which input evidence caused
the improvement.

### Phase 3 - train the semantic Musical State encoder

Only after Phase 2 succeeds, train or fine-tune a multi-resolution encoder that
produces:

- frame/window features for alignment;
- beat/bar features for harmony, bass and groove;
- phrase/section features for motifs and form; and
- a song-level index for retrieval and project navigation.

Training pairs should combine:

1. authorised real alternate performances, stems and arrangements;
2. controlled deterministic augmentations;
3. synthetic negative/counterfactual mixtures; and
4. owner or musician comparisons identifying which musical relationship was
   preserved.

Self-supervised or contrastive pretraining can use more audio than the labelled
set, but labels and evaluation must remain composition-disjoint. Confidence
calibration is required so the system can present alternatives instead of
claiming one intended melody.

Exit gate: the encoder passes the frozen held-out identity suite and improves a
real downstream task: accompaniment reconstruction, motif-guided editing or
phrase selection.

### Phase 4 - constrained generation, not another blind full-song bake-off

Use the learned state to condition the smallest useful creative operation:

1. preserve an accepted scaffold;
2. change one bounded role or region;
3. render multiple disclosed alternatives;
4. compare against a matched no-state and current ACE reference baseline; and
5. reject any candidate that loses every recognised anchor.

Possible engineering routes, in increasing cost and risk:

- retrieve and assemble reviewed MIDI/Clip material from the Musical State;
- map Musical State features into an existing ACE conditioning channel;
- train a lightweight cross-attention adapter or side conditioner while
  freezing ACE;
- fine-tune selected ACE blocks with parameter-efficient training; and
- train a larger conditional generator only if every smaller route fails and a
  sufficiently large, lawful paired dataset exists.

An ordinary style LoRA is not accepted as an identity-conditioning solution.
The experiment must prove that non-zero Musical State conditioning is more
source-connected than a seed-, lyric- and prompt-matched zero-state control.

Exit gate: at least one bounded output is owner-recognisable, musically useful
and editable without destroying its parent or relying on a filename/model cue.

### Phase 5 - vocal intention and authentic comping

Keep two separate lanes:

- **Authentic comp:** original recorded regions, explicit selections and
  disclosed bounded correction.
- **Generated performance:** model-rendered audio with voice consent, training
  provenance and unmistakable UI labelling.

Resume the existing vocal-comp programme after phrase/word alignment is
repaired. Use the Musical State's accompaniment clock, lyrics and harmonic
context as evidence, but never force rough-vocal F0 to be the target melody.
Where intention is ambiguous, present alternatives or request a pickup.

Exit gate: a reviewed human comp is at least as useful as the best complete
take, contains no unacceptable join and requires less owner time than manual
comping from scratch.

### Phase 6 - product integration and final goal

- Make Musical State a versioned project artifact with immutable lineage.
- Add Workbench views for identity anchors, confidence, alternatives and the
  exact evidence behind a proposed edit.
- Retain existing MIDI corrections, arrangement selection, balanced audition
  WAV and GarageBand handoff.
- Add an export audit distinguishing human/source audio, deterministic MIDI
  rendering and generated waveform content.
- Measure success across multiple owner-authorised songs before promoting any
  default.

Programme completion requires at least one complete song the owner wants to
finish, not merely improved benchmark scores.

## 6. Data programme

### Minimum development data

- One deeply annotated golden song is enough to build the schema and debug the
  laboratory, but not to train a general model.
- A small pilot should contain several composition-disjoint songs with multiple
  stems/versions and hundreds of reviewed identity-anchor windows.
- A serious encoder needs a substantially broader lawful corpus. Acquire it
  through owner-created material, commissioned performances, explicitly
  licensed datasets or partnerships; do not assume public availability grants
  training rights.

### Priority recordings to create

For each new owner-created song, retain:

- rough and polished accompaniment;
- individual stems and MIDI when available;
- alternate instrumentation and tempo/key variants;
- guide and intentionally imperfect vocals;
- several complete human vocal takes;
- lyrics, section map and production intent;
- owner identity-anchor annotations; and
- one or more deliberately non-matching hard negatives.

This recording protocol is more valuable than collecting unstructured finished
mixes because it supplies the factorised pairs the model must learn.

## 7. Compute and cloud purchasing gates

The local RTX 4080 Laptop GPU remains the development machine for extraction,
probes, small adapters, short-window training, debugging and reproducibility.
Cloud compute is justified only by a written experiment that has already passed
locally at reduced scale.

### Gate C0 - no paid compute

Use local hardware for Phase 0, most of Phase 1 and tiny Phase 2 overfit tests.
Required evidence: deterministic dataset loader, loss decreases on a tiny set,
checkpoint/resume works and evaluation detects deliberate label corruption.

### Gate C1 - single-GPU pilot

Rent one modern 24-48 GB GPU for a bounded adapter/probe run when memory or
iteration time blocks the local machine. Cap the first purchase by GPU-hours,
storage and egress, not by an open-ended monthly account.

Required before purchase:

- exact container/environment and model hashes;
- dataset manifest and upload/privacy approval;
- maximum steps, wall time and automatic shutdown;
- expected checkpoints and evaluation command;
- local tiny-run receipt; and
- a stop rule if validation does not beat the baseline.

### Gate C2 - larger encoder training

Use a 48-80 GB GPU, or a small multi-GPU job, only after a Phase 2 adapter
proves the labels and objective. Run a short learning-rate/batch-size pilot,
then one selected main run. Do not fund a broad hyperparameter sweep until the
held-out identity metric correlates with owner judgement.

### Gate C3 - generator adaptation

This is the expensive gate. It requires:

- Phase 3 success;
- a lawful paired dataset large enough for the selected trainable parameter
  count;
- a zero-state counterfactual evaluation;
- a parameter-efficient conditioning experiment first;
- checkpoint and sample review at fixed intervals; and
- a predefined total budget and shutdown threshold.

Never place private audio, credentials or provider keys in a machine image or
training log. Encrypt storage, minimise retained cloud data, download and hash
results, and delete the remote job data according to a recorded retention
decision.

## 8. First twelve-week execution sequence

### Weeks 1-2: freeze the question

- Consolidate the current branch and evidence.
- Define `musical-state.v0` and identity-anchor schemas.
- Create the golden benchmark manifest and controlled-variant recipes.
- Record the owner's invariances and hard negatives before seeing new results.

### Weeks 3-4: ACE representation access

- Add a separate representation-extraction tool to the ACE service.
- Extract aligned VAE, text-conditioning and selected DiT features from short
  windows.
- Verify determinism, tensor identities, resource use and temporal alignment.

### Weeks 5-6: frozen representation bake-off

- Add independent admitted encoder baselines.
- Run retrieval, invariance and shallow-probe tests.
- Produce owner-blind listening/retrieval pages using existing review patterns.
- Select features per Musical State field; do not force one winner for all.

### Weeks 7-8: local learned-adapter pilot

- Train small temporal/contrastive heads locally.
- Add song-disjoint splits, hard negatives, ablations and confidence checks.
- Decide whether the first paid single-GPU run is justified.

### Weeks 9-10: bounded cloud pilot if Gate C1 passes

- Run one selected adapter experiment.
- Download checkpoints and evaluation artifacts immediately.
- Compare with frozen and deterministic baselines before any second purchase.

### Weeks 11-12: first downstream proof

- Use the best state to retrieve or construct one accompaniment scaffold or
  guide one bounded ACE operation.
- Conduct matched zero-state and current-reference controls.
- Ask the owner to identify the preserved musical relationship blindly.
- Continue, revise the objective or stop based on that result.

## 9. Decision rules

Continue to larger training only when all are true:

1. the task and labels are composition-disjoint and reproducible;
2. the learned representation beats deterministic and frozen baselines;
3. improvement survives hard negatives and ablation;
4. automatic scores correlate with owner identity judgements;
5. the downstream result reduces work toward a finishable song; and
6. rights, model terms, privacy and compute budget are recorded.

Stop or reframe when:

- the model learns singer, loudness, mix or genre instead of composition;
- random train/test excerpts from the same song inflate results;
- a larger model improves benchmark numbers but not owner recognition;
- conditioning is indistinguishable from a zero-state control;
- the dataset cannot lawfully support the intended use; or
- cloud spending is compensating for an undefined representation or target.

## 10. Immediate next deliverable

Implement the Phase 0 schemas and a no-model benchmark builder. The first new
technical experiment after that is the controlled ACE representation bake-off,
not another full-song generation run and not a large training purchase.

This sequencing accepts that training is likely necessary to meet the goal,
while ensuring that paid compute trains the missing musical-intelligence layer
rather than repeating an already rejected end-to-end generation strategy.
