# Phase 3: Instrument Intelligence v2 close-out

Status on 17 July 2026: **complete**.

Phase 3 produces reproducible, reviewable instrument evidence without silently
changing the supplied MIDI, source samples or default sampler. It closed with
explicit GarageBand and loop-listening decisions rather than promoting an
automatic score or proxy render.

## What is implemented

| Goal | Implemented evidence and guardrail |
| --- | --- |
| Learned timbre evidence | Optional local, hash-pinned OpenL3 comparison kept separate from the explainable ranking |
| Fair source/candidate matching | Source and every FluidSynth candidate use the same aligned MIDI phrase and active windows |
| Instrument/articulation discovery | Deterministic source-event identity and articulation clusters with retained outliers, JSON and SVG |
| Drum families | Role-specific GM channel-10 proposals, assigned one-shot auditions and conservative score/margin guardrails |
| Dynamics and natural variation | Advisory velocity-layer and alternate-event groups inside one identity/pitch/articulation unit |
| Explicit sampler decisions | Neutral review page, exact one-shot plus source-context and role auditions, hash-checked apply, v2 rollback and real v3 A/B |
| Root, tuning and range | Measured root pitch, cents correction and bounded key ranges in self-contained SF2/SFZ instruments |
| Sustain loops | Advisory waveform/spectral boundary ranking, SVG and raw repeated auditions; no loop is enabled automatically |
| Feedback provenance | Explicit reviewed JSON, immutable source/review hashes and mutation audit |
| GarageBand handoff | AUSampler `.aupreset`, self-contained SF2, MIDI/WAV auditions and backward-compatible Instrument Bundle v1 fields |

Every automatic label is deliberately narrow. A cluster is a candidate timbre
family, not proof of a physical instrument. An outlier is retained evidence,
not noise. A lower loop-continuity score is a shortlist position, not an
accepted musical loop.

## Completed heard goldens

Two real Lidl percussion decisions have already exercised the complete review,
apply, rollback and reproducibility path:

- `other_kit`: the listener found events 13 and 25 audibly different and chose
  event 25 alone across velocity 0–127. The final challenger is
  `work/ai-bakeoff/lidl-drum-families-full-v1/lidl-other-kit-v3-single-upper-event25-v1`.
- kick: the listener chose event 17 alone for MIDI 36 and no alternates. The
  final challenger is
  `work/ai-bakeoff/lidl-drum-families-full-v1/lidl-kick-v3-reviewed-event17-v1`.

Both preserve their original v2 banks, change zero MIDI notes and velocities,
and reproduced their musical artifact hashes in fresh repeat builds.

## Completed drum decisions and v3 builds

All four neutral pages now have explicit decisions:

| Role | Result | Applied output |
| --- | --- | --- |
| Snare | Event 44 accepted at MIDI 40; three other units rejected | `work/ai-bakeoff/lidl-drum-families-full-v1/phase3-closeout-v3-reviewed-v1/snare` |
| Hats | Event 35 accepted at MIDI 42 and event 21 at MIDI 46 | `work/ai-bakeoff/lidl-drum-families-full-v1/phase3-closeout-v3-reviewed-v1/hat` |
| Cymbals | All three proposed units rejected | No v3: retain the unchanged v2 pack |
| Toms | Events 5/39 accepted as MIDI-45 velocity layers split at 107/108; event 9 at MIDI 48 and event 14 at MIDI 50 | `work/ai-bakeoff/lidl-drum-families-full-v1/phase3-closeout-v3-reviewed-v1/toms` |

No alternate event was accepted, so there is no round robin or GarageBand
alternate bank. Snare and hats retain two zones. Toms changes four v2 zones to
five v3 zones solely because MIDI 45 has two reviewed velocity ranges. All
source MIDI notes and velocities are unchanged, every v2 bank is embedded and
the main/repeat musical artifacts, sample trees and normalized reports match.
The cymbal apply guard correctly refused to make a misleading no-op v3.

## Completed blinded performance close-out

The final source/v2/v3 question was presented without revealing which candidate
was v2 or v3:

`work/ai-bakeoff/lidl-drum-families-full-v1/phase3-closeout-blind-ab-v2/sample_ab_review.html`

It contained three units—snare, hats and toms—and one additional tom velocity
sweep using the same hidden Candidate A/B assignment. The completed export
SHA-256 is
`573e23366f80ea4120ed54007c57ca558496ddea59ff3e3a51b6036d3cfec876`.
The resolver verified the key, every source v3 report and every copied WAV.

The resolved result is:

| Role | Blind choice | Revealed result | Decision |
| --- | --- | --- | --- |
| Snare | Candidate B | v3 | Take reviewed event-44 v3 to the final GarageBand comparison |
| Hats | Candidate B | v2 | Retain unchanged v2; do not promote the reviewed v3 |
| Toms | Candidate A | v2 | Retain unchanged v2; do not promote the reviewed velocity-layer v3 |

The listener described the chosen snare and hats candidates as useful but less
rich than the source. The subsequent GarageBand/AUSampler comparison selected
snare v2, overriding the FluidSynth proxy result. Result SHA-256 is
`95cc52ab61e8aa5d4a3e6a24d67625a539cc8c6a9287df2c78497166f59f4e91`;
a second resolve produced the same bytes. All source, MIDI and sampler effects
remain zero. The answer-key and audio-manifest hashes remain
`b8b6e241dd8c2ac2757cd4096cc9d87d855c614e9d45f32b85519733c3748d23`
and `46272b4b6604188049703adab20b369a46e089a40c8e36f23c132b55fa1e867e`.

## Reviewed pitched-loop suggestion

The real Lidl bass golden is:

`work/ai-bakeoff/lidl-bass-200-215/phase3-loop-suggestions-v1`

Five samples were analysed. Four are shorter than the 0.65-second advisory
minimum. The 1.002396-second MIDI-30 sample produced these raw repeated-loop
auditions:

| Candidate | Loop boundary | Continuity score | Audition |
| --- | --- | ---: | --- |
| 1 | 0.304438–0.902167 s | 0.116972 | `loop-auditions/02-midi-030-000013.112s-candidate-01.wav` |
| 2 | 0.283646–0.881479 s | 0.122931 | `loop-auditions/02-midi-030-000013.112s-candidate-02.wav` |
| 3 | 0.283646–0.902167 s | 0.123169 | `loop-auditions/02-midi-030-000013.112s-candidate-03.wav` |

The listener selected **candidate 1**. Its 0.304438–0.902167-second boundary is
therefore the accepted advisory suggestion for MIDI 30. The auditions use four
raw repeats and no crossfade, so the boundary is not flattered. This decision
does not silently enable a sampler loop: the current SF2 and SFZ remain
unlooped and have zero looped zones.

## Final Phase 3 decisions

The two final listener responses were `snare v2` and `loop 1`. They close the
human gate as follows:

| Role or feature | Final result | Consequence |
| --- | --- | --- |
| Snare | v2 | The DAW result overrides the blind FluidSynth v3 preference |
| Hats | v2 | The blind full-performance result outweighs the isolated accepted events |
| Cymbals | v2 | Every proposed v3 unit was rejected |
| Toms | v2 | The blind full-performance result outweighs the isolated velocity-layer choice |
| Bass sustain loop | Candidate 1 | Retain the exact boundary as reviewed evidence; do not enable it automatically |

The kick event-17 and `other_kit` event-25 v3 packs remain useful reviewed
experiments; they are not silently promoted into the cross-role close-out. The
mixed result is important evidence: a cleaner isolated hit or mapping can be
useful without producing the best full-performance instrument in a DAW. No
automatic score, cluster or test substitutes for these listening decisions.

The machine-readable decision record is
`work/ai-bakeoff/lidl-drum-families-full-v1/phase3-instrument-intelligence-closeout-v1.json`
(SHA-256
`31332e2b076367d697fbc7a7f3acf9141b85003e59e7d42d16af2c1db28e0ebe`).

## Engineering validation

The close-out work passed:

- `ruff check src tests scripts`;
- 351 repository tests, with one existing `resampy` warning about the
  deprecated `pkg_resources` API;
- focused loop, sample-pack, blind-review and Instrument Bundle tests;
- `git diff --check`;
- wheel and source-archive builds for Sunofriend 0.4.0;
- `twine check` for both archives; and
- a clean wheel install and CLI/import smoke test under supported Python 3.9.

An attempted clean install under the machine's unrelated Python 3.12 was
correctly refused by the declared `>=3.9,<3.12` compatibility boundary.

## Reproduce the neutral review batch

The exact source and MIDI hashes are stored in each output. From the repository
root, a representative role can be rebuilt with:

```bash
.venv/bin/sunofriend sample-pack \
  "work/Lidl-B major-119bpm-440hz/Lidl-snare-B major-119bpm-440hz.wav" \
  work/ai-bakeoff/lidl-drum-families-full-v1/baseline/mode_repair/selected_cymbals-hat-other-kit-snare-toms/snare_listened.mid \
  --kind snare \
  --name "Lidl Snare Phase 3 Close-out" \
  --out-dir work/sample-packs/lidl-snare-phase3

.venv/bin/sunofriend sample-pack-review \
  work/sample-packs/lidl-snare-phase3 \
  --out-dir work/sample-reviews/lidl-snare-phase3
```

After a user export, apply it only to a fresh path:

```bash
.venv/bin/sunofriend sample-pack-apply \
  "$HOME/Downloads/sample_pack_review.reviewed.json" \
  --name "Lidl Snare Reviewed" \
  --out-dir work/sample-packs/lidl-snare-phase3-v3
```

The command must refuse an unreviewed document, changed evidence, unknown event,
missing primary or conflicting accepted units at one MIDI pitch.
