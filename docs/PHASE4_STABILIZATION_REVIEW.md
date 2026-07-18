# Phase 4 stabilization review

Reviewed: 18 July 2026
Decision: **the Phase 4 foundations are stable enough to checkpoint, but the
Phase 4 musical outcome has not yet been achieved.**

This review separates three questions that are easy to conflate:

1. Did the commands run and preserve reproducible evidence?
2. Did the safeguards prevent a poor result from being recommended?
3. Did the experiment make better music than the simpler baseline?

For the current Slayyyter bass/keys golden, the answers are **yes**, **yes**
and **not yet**. The next Phase 4 experiment should therefore start only from
this stabilized checkpoint and should have one narrow, predeclared listening
goal.

## Goals compared with execution

| Phase 4 goal | What has actually run | Assessment |
| --- | --- | --- |
| Query- or prompt-based isolation for mixed stems | A transparent MIDI-informed harmonic mask and a separately labelled transient challenger | **Baseline complete; learned/query isolation not started.** The mask is a comparison target, not a separator. |
| Target plus residual reconstruction | Persisted PCM24 source, target and residual for a 16-second keys excerpt | **Achieved for the DSP baseline.** Maximum reconstruction error is `1.19209e-7` against a `1e-6` limit, with zero input mutations. |
| Cleanup that improves downstream transcription | Source, harmonic target/residual and transient target/residual were transcribed and reviewed | **Not achieved.** The unchanged-source MIDI carried the clearest tune. Harmonic-target MIDI was only a possible accompaniment; the other derivatives were rejected as musically unhelpful. |
| Neural denoise or de-reverb | No model has been integrated or promoted | **Not started.** This remains conditional on a measurable transcription and listening improvement. |
| Monophonic DDSP-style timbre model | No generated or resynthesized instrument has been produced | **Not started.** Bass MIDI should be chosen first so timbre is compared using one fixed performance. |
| Optional Audio Unit model hosting | GarageBand/AUSampler handoff exists, but no neural Audio Unit bridge | **Not started.** It is not required for the next experiment. |
| Generated missing samples marked separately | The policy is documented; all current samples are extracted source derivatives | **Policy ready; implementation not started.** |
| Never promote generated output as exact evidence | AI candidates, masks, OpenL3 rankings and personal history remain challengers or advisory evidence | **Achieved as a guardrail.** |
| Beat the simpler DSP/sample path in listening | Small Time Piano beat the source-derived keys sampler; unchanged-source MIDI beat the cleanup derivatives | **Phase 4 success criterion not met.** No neural cleanup or timbre result has yet beaten the simpler path. |

## What the current execution proved

### Transcription

- MuScriptor is a credible bass challenger on metrics: strong-onset F1 rose
  from `0.070` to `0.324` and contour accuracy from `0.521` to `0.693` with
  similar mean pitch support. It still needs a decisive full-mix GarageBand
  choice before becoming the preferred bass MIDI.
- The combined MuScriptor keys result is not a primary candidate. It increased
  note density and onset recall, but mean pitch support fell from `0.646` to
  `0.283` and mean polyphony rose from `0.965` to `1.860`.
- The keys mask moved guide harmonics into the target and reconstructed the
  source correctly, but it did not preserve the musical theme or attacks well
  enough. This is useful negative evidence, not a melody improvement.

### Instruments

- The source-derived keys bank is a valid SF2 artifact but not a complete
  instrument for the supplied performance. It maps `388/413` notes, supports
  an audible attack for `328/413`, and supports musical duration for `244/413`.
- MIDI pitches 35, 38, 40, 42, 88, 90, 93 and 95 are unmapped. The rendered
  usability audition independently exposed those silent pitches.
- Only one of twelve pitched zones has stable tuning evidence; the bank has no
  active sustain loops and contains two candidate timbre families. It remains
  useful only as optional source texture.
- The user's full-mix choice, **Small Time Piano**, is the correct current keys
  recommendation because it plays every note consistently. This listening
  result outranks the explainable GM order, the OpenL3 order and the
  source-similarity score.
- OpenL3 remains useful as a separate shortlist, but it did not discover the
  user's chosen patch. It must stay advisory.

### Reproducibility and safety

- The reviewed patch feedback hash is
  `b4ba10f58ca5b5310a2041a9a888c45d2064124df2a0a1d7d9eac38fd2710089`.
- Three fresh personal-profile writes are byte-identical at
  `6ff152ecccde09ce214cf889e4e5f6ecdc9adb2e34f59df5c5a65548bbd90b53`.
- The unprofiled, profiled and stabilization bundles carry the same performance
  MIDI hash:
  `4c3171886544a56a2f470ce8b0df95a2334dcac6e223f0a8f9e51871c21db533`.
- Applying the personal profile changes no factory, GM or OpenL3 order, no
  portable program hint, no MIDI and no playability result.
- All private source audio, models and generated instruments remain under the
  ignored `work/` tree.

## Code review and cleanup

The Phase 4 behavior is separated into useful boundaries:

- `midi_mask.py` owns the experimental DSP and reconstruction contract;
- `instrument_usability.py` owns arrangement-aware functional checks;
- `instrument_preference.py` owns explicit, local reviewed choices; and
- `instrument_bundle.py` composes evidence without making a hidden selection.

The stabilization pass made the following maintenance and correctness changes:

- centralized the immutable profile policy and zero-effect contracts;
- made profile loading reject empty effect maps, malformed SHA-256 values and
  incomplete bundle evidence instead of accepting any all-false mapping;
- derived unique-pitch coverage from the exact mapped note/velocity results;
- extracted profile preparation from the main bundle orchestration;
- removed duplicate history-first GarageBand instructions; and
- stopped describing a failed source sampler as the bundle's portable primary
  sound.

A fresh no-preview bundle reproduced the earlier coverage and duration results
and now gives one unambiguous handoff: use Small Time Piano as the complete
primary sound and the source SF2 only as optional texture.

Verification at this checkpoint:

- `ruff check src tests`: passed;
- complete test suite: `368 passed, 1 warning`;
- conversion and preview capability checks: ready, using local FluidSynth and
  GeneralUser GS;
- source distribution and wheel: built successfully; and
- Twine metadata checks: both artifacts passed.

The one test warning comes from `resampy` importing the deprecated
`pkg_resources` API. It is dependency noise rather than a Phase 4 failure, but
it should be removed through a controlled dependency update rather than hidden.

## Remaining maintainability debt

The new policy boundaries are reasonably isolated, but three older
orchestrators remain too large:

- `cli.py`: about 3,500 lines; `build_parser` is about 1,500 lines;
- `instrument_match.py`: about 2,300 lines; its two main operations are about
  400 and 350 lines; and
- `instrument_bundle.py`: about 830 lines; its main operation is about 500
  lines.

These should be split incrementally behind characterization tests. A broad
rewrite now would mix refactoring with unresolved musical research and make
the golden evidence harder to trust. The next safe refactors are typed command
registration, a shared immutable role registry, and smaller bundle recipe,
preview and sampling stages.

## Gate before the next Phase 4 increment

Proceed only when all of the following are true:

1. Commit the stabilized Phase 4 foundations as a recoverable checkpoint.
2. Choose one role and one 10–20 second passage where the intended line is
   clearly audible. Do not use the accompaniment-like electric-piano guide as
   a melody target.
3. Declare the primary question in advance: either better MIDI boundaries and
   pitch, or better timbre for one fixed MIDI—not both at once.
4. Keep the unchanged source, current DSP mask and normal GarageBand patch as
   mandatory baselines.
5. Require target-plus-residual reconstruction for cleanup, and identical MIDI
   for timbre comparisons.
6. Promote nothing unless it wins a level-matched full-mix listening test and
   preserves reproducibility, provenance and licensing evidence.

The best next research increment is a learned separation challenger on a
clearly melody-carrying short passage. If no such keys passage exists, use the
more promising monophonic bass line instead. Neural timbre or DDSP work should
follow only after the MIDI choice is stable.
