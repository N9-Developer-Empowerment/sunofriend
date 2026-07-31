# Private stem-separation development

Sunofriend has started running a real local separator. This page describes the
developer-only bake-off, not a finished-song feature.

## Current result

The first real run completed on 31 July 2026 with the already-installed
Demucs 4.0.1 `htdemucs` checkpoint. One model application produced four broad
estimated stems:

- bass;
- drums;
- other; and
- vocals.

The input was Sunofriend's eight-second copyright-safe synthetic demo. It
contains fixed mathematical waveforms and deterministic noise, with no
recordings, samples, lyrics or third-party audio. Exact references are:

- drums = kick + snare + hat;
- bass = bass;
- other = keys + lead; and
- vocals = digital silence.

The hardened private run took 8.00 seconds in the parent report, including
6.82 seconds of model inference. The worker reported about 2.10 GB maximum
resident memory on this Mac. Geometry remained exactly 44.1 kHz stereo and
352,800 frames. No stem clipped.

Initial ground-truth observations were:

| Role | SI-SDR | Level difference | 10 ms envelope correlation | Lag/drift |
| --- | ---: | ---: | ---: | ---: |
| bass | 19.75 dB | +0.06 dB | 0.957 | 0 ms / 0 ms |
| drums | 4.13 dB | -2.22 dB | 0.910 | 0 ms / 0 ms |
| other | 14.01 dB | +0.14 dB | 0.959 | 0 ms / 0 ms |

The deliberately silent vocal reference produced a small false-positive
estimate at -62.95 dBFS, or -47.81 dB relative to the mixture. These are
observations from one synthetic fixture, not promotion thresholds or proof
of quality on real songs.

The same clean references and estimated stems were then passed through the
same existing Sunofriend seed-transcriber settings. This first MIDI
observation is retained as the pre-refinement baseline. At a 40 ms
event-onset tolerance matching the independent evaluator's default, it
observed:

| Role | Clean-reference MIDI | Estimated-stem MIDI | Main relative result |
| --- | ---: | ---: | --- |
| bass | 10 notes | 8 notes | exact-pitch/onset F1 0.556 |
| drums | 32 hits | 22 hits | onset F1 0.815; broad and articulation-family/onset F1 0.296 |
| other | 40 notes | 50 notes | exact-pitch/onset F1 0.889 |
| vocals | 0 notes | 1 note | one false positive against silence |

The drum difference is important: the separator preserved many event times,
but the current classifier often heard the resulting sound as a different
drum family. Broad family and exact articulation are recorded separately,
although both happened to score 0.296 on this fixture. The broad `other`
result contains keys plus lead and therefore does not prove ownership of
either instrument. Clean-reference transcription is a relative baseline, not
the original musical score.

The three broad roles supported by `refine_stem` have now also completed the
exact production repair loop, FluidSynth/GeneralUser GM rendering and the
independent stem-to-MIDI evaluator. Every primary and every generated variant
was rendered and retained. Vocals are not described as `refine_stem` parity:
their production melody path is separate and remains a later, explicit parity
increment.

| Role | Refined clean / estimate notes | Clean-to-estimate MIDI result | Independent clean / estimate observation |
| --- | ---: | --- | --- |
| bass | 8 / 8 | exact-pitch/onset F1 0.625 | strong-onset F1 0.092 / 0.121; chroma 0.705 / 0.726; supported-note ratio 1.000 / 1.000 |
| drums | 32 / 22 | onset F1 0.815; broad-family F1 0.296 | strong-onset F1 0.638 / 0.483; inclusive possible-onset F1 0.667 / 0.821 |
| other | 40 / 48 | exact-pitch/onset F1 0.909 | strong-onset F1 0.813 / 0.471; chroma 0.996 / 0.994; supported-note ratio 0.800 / 0.646 |

The loop's own score was higher on the estimated input for bass and `other`.
That is not evidence that separation improved those parts: the independent
onset/support evidence shows losses that a self-comparison score can miss.
Separator acceptance cannot use the refinement score alone. Broad `other`
retained pitch-class content especially well but added eight events and lost
onset/support evidence; drums retained event timing much better than
instrument-family identity; bass remains the weakest transcription. These are
observations, not thresholds.

The four model outputs differed additively from the source by -24.87 dB RMS.
Sunofriend separately persisted `source - estimated sum`; the float64 sum of
the four re-read persisted stem WAV arrays plus that accounting remainder
reconstructed the PCM source exactly in this run. The separately written sum
WAV is only an audition rendering and is not used for closure because PCM
clipping could hide oversummed samples. This proves arithmetic accounting
only. It does not prove that a model assigned sounds to the correct stems.

## Repeat the canary

This command uses only an existing local runtime and checkpoint. Every output
path must be fresh.

```bash
.venv/bin/python scripts/private-demucs-four-stem-canary.py \
  --fixture-out work/separation-bakeoff/demo-fixture-v2 \
  --run-out work/separation-bakeoff/demo-run-v2 \
  --evaluation-out work/separation-bakeoff/demo-evaluation-v2 \
  --checkpoint ~/.local/share/sunofriend/models/demucs-4.0.1-htdemucs/955717e8-8726e21a.th \
  --python .venv-ai/bin/python
```

The command never installs or downloads a model. It rejects a checkpoint
whose SHA-256 is not
`8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4`.

Run the downstream MIDI observation only after the two fresh reports above
exist:

```bash
.venv/bin/python scripts/private-demucs-downstream-midi-canary.py \
  --fixture work/separation-bakeoff/demo-fixture-v2/private-demucs-demo-fixture.json \
  --experiment work/separation-bakeoff/demo-run-v2/private-separation-experiment.json \
  --out work/separation-bakeoff/demo-midi-evaluation-v2
```

It writes inactive reference and estimate MIDI plus JSON note evidence under
`REFERENCE/` and `ESTIMATE/`. It does not add either side to a Sunofriend
project.

Run production-refinement parity only after the fixture and experiment exist,
again using a fresh output path:

```bash
.venv/bin/python scripts/private-demucs-production-refinement-canary.py \
  --fixture work/separation-bakeoff/demo-fixture-v2/private-demucs-demo-fixture.json \
  --experiment work/separation-bakeoff/demo-run-v2/private-separation-experiment.json \
  --out work/separation-bakeoff/demo-production-refinement-v2
```

This is deliberately slower than seed transcription. It writes private
primary/variant MIDI, note evidence, dry proxy WAV auditions, internal
iteration histories, independent evaluations and a self-hashed report. It
does not activate or select any result.

Run an excerpt already declared in the authorised corpus with a fresh output
path:

```bash
.venv/bin/python scripts/private-authorised-separation-excerpt.py \
  --corpus stem_examples/corpus.json \
  --track-id be-alone \
  --out work/separation-bakeoff/be-alone-authorised-191-206-v2 \
  --checkpoint ~/.local/share/sunofriend/models/demucs-4.0.1-htdemucs/955717e8-8726e21a.th \
  --python .venv-ai/bin/python
```

The command hashes every unchanged source, creates private PCM24 provider
excerpts, measures each provider pack sum against the native-rate original and
runs the local model only after those checks. A 48 kHz source is preserved at
48 kHz for provider comparison and given an explicit, recorded
`scipy.signal.resample_poly` 44.1 kHz derivative for the current Demucs
contract.

Build the four provisional provider groups and compare them with every local
HTDemucs role:

```bash
.venv/bin/python scripts/private-authorised-role-mapping.py \
  --excerpt-report work/separation-bakeoff/be-alone-authorised-191-206-v2/authorised-separation-excerpt.json \
  --out work/separation-bakeoff/be-alone-role-mapping-191-206-v2
```

Each non-metronome provider excerpt must match exactly one proposed group.
The command writes common-rate group WAVs, proves that the four groups close
to the provider sum, then ranks every provider group against every local role
using spectral shape, envelope and absolute waveform evidence. Names propose
the partition; they do not contribute to its audio score.

Inspect the individual provider leaves that were provisionally placed inside
the broad `other` group, again using a fresh private output path:

```bash
.venv/bin/python scripts/private-authorised-narrow-other.py \
  --role-mapping work/separation-bakeoff/be-alone-role-mapping-191-206-v1/authorised-role-mapping.json \
  --out work/separation-bakeoff/be-alone-narrow-other-191-206-v2
```

This writes common-rate leaf auditions and full pairwise audio rankings in
both directions. It also reports exact and semantic provider-label matches,
but names never contribute to similarity and are never accepted as ground
truth. The result cannot select a leaf, activate source lineage, create MIDI
or enter Studio/Simple mode.

Run the same production MIDI paths over every four-role pack only after the
mapping report has verified all proposed diagonal rankings:

```bash
.venv/bin/python scripts/private-authorised-midi-comparison.py \
  --role-mapping work/separation-bakeoff/be-alone-role-mapping-191-206-v1/authorised-role-mapping.json \
  --out work/separation-bakeoff/be-alone-midi-comparison-191-206-v1 \
  --bpm 136 \
  --tuning-hz 440
```

For bass, drums and `other`, this calls the existing production
`refine_stem(..., conversion_mode="repair")` path. Vocals use the separate
production pYIN dominant-contour path. Every primary and variant receives
JSON note evidence, independent evaluation and, when non-empty, MIDI plus a
dry FluidSynth audition. The local HTDemucs MIDI is a relative comparison
baseline, not score truth. The command cannot accept, select, activate or
import any result.

## Evidence produced

The private run keeps:

- the exact PCM24 source excerpt;
- one float32 model array and PCM24 estimated WAV per broad role;
- the model stem sum and source-minus-sum accounting remainder;
- request, worker-result, stdout and stderr evidence;
- source, request-bound excerpt, checkpoint, worker and resolved
  runtime-launcher identities and hashes;
- geometry, clipping, energy, reconstruction and resource observations; and
- a self-hashed, review-required experiment report.

The separate synthetic evaluations revalidate both reports and every stem
hash. The audio evaluator computes SI-SDR, level error, envelope lag,
quarter-to-quarter drift, silent-vocal leakage and energy ratios. The MIDI
evaluator runs identical existing seed-transcription APIs on each
clean/estimated pair, persists their exact settings and implementation/model
identities, then computes note and drum onset, pitch, register, duration,
family and silent-reference observations. Saved note times retain JSON
round-trip precision, and the drum evidence retains every hit time, family,
GM pitch, velocity, strength, tier and provenance so the reported pair
metrics can be recomputed from the hashed artifacts.

## Deliberate boundary

This private experiment:

- is not imported by CLI, TUI, Simple or Workbench;
- does not use or weaken the fake-only public separation runner;
- creates no source-graph node or active candidate;
- makes no automatic selection, acceptance or promotion;
- does not prove network denial, attempted-connection observation,
  outside-write confinement or complete descendant supervision; and
- keeps the checkpoint under Sunofriend's private-evaluation-only policy
  because separate official weight terms have not been established.

`REAL_SEPARATION_BACKENDS_SUPPORTED` and
`CHECKPOINT_DESCRIPTOR_LEASE_EXECUTION_SUPPORTED` remain `False`.

## Next evidence

The synthetic audio, resource, seed-transcriber and production-refinement
observations are complete. The first authorised real excerpt is also staged:
`Be Alone` 191–206 seconds. The three provider sums all measured zero 10 ms
envelope lag. Moises correlation at recorded zero was 0.9985 with a
gain-matched residual of -38.93 dBFS; Suno A/B correlations were 0.9305 and
0.9306 with residuals of -22.29 and -22.30 dBFS. These values establish usable
alignment, not stem correctness.

The pinned local HTDemucs run completed the 15-second 44.1 kHz derivative in
11.16 seconds of inference, reporting about 2.13 GB maximum resident memory.
None of its four broad outputs clipped; their raw sum differed from the source
by -32.62 dB RMS and the separately persisted accounting residual closed the
re-read PCM sum exactly. Again, arithmetic closure is not separation quality.

The first broad-role mapping observation is also complete. Every proposed
role ranked first against the matching local role, but remains unaccepted:

| Provider | Bass similarity / margin | Drums | Other | Vocals |
| --- | --- | --- | --- | --- |
| Moises | 0.992 / +0.472 | 0.998 / +0.491 | 0.922 / +0.534 | 0.974 / +0.609 |
| Suno A | 0.985 / +0.463 | 0.985 / +0.466 | 0.893 / +0.432 | 0.879 / +0.527 |
| Suno B | 0.982 / +0.459 | 0.987 / +0.472 | 0.863 / +0.397 | 0.871 / +0.502 |

Similarity is descriptive, not a calibrated probability. The diagonal result
shows that the provisional four-way partitions are coherent enough for an
inactive, identical downstream-MIDI comparison. It does not prove that a
group is clean, complete or preferable by ear.

That first identical-settings MIDI comparison is now complete. The local
HTDemucs groups produced 16 bass notes, 99 drum hits, 74 `other` notes and 13
vocal notes. Relative to that local MIDI, the provider results were:

| Provider | Bass exact/onset F1 | Drums onset / broad-family F1 | Other exact / chroma / onset F1 | Vocals exact/onset F1 |
| --- | ---: | ---: | ---: | ---: |
| Moises | 0.526 | 0.939 / 0.776 | 0.225 / 0.318 / 0.397 | 0.483 |
| Suno A | 0.545 | 0.890 / 0.716 | 0.252 / 0.326 / 0.533 | 0.417 |
| Suno B | 0.200 | 0.900 / 0.701 | 0.161 / 0.274 / 0.371 | 0.400 |

The provider note/hit counts were Moises 22/97/77/16, Suno A
17/119/61/11 and Suno B 14/112/50/12 in bass/drums/other/vocals order. This
does not rank a provider globally. It does show that event timing is most
stable for drums, while the composite `other` group is not a sufficiently
specific musical role for equivalent MIDI. Bass and dominant-vocal lines also
remain materially separator-dependent. The 15-second run retained 231 hashed
artifacts, occupied about 240 MB and left every permission false.

A first bounded human screen is ready under
`work/separation-bakeoff/be-alone-midi-listening-screen-v1`. It contains one
blind, pairwise level-matched 15-second review for each role. Each compares
the local primary with the provider primary having the highest relative match
metric for that role: Suno A for bass and `other`, Moises for drums and
vocals. This choice only reduces the first listening task to four decisions;
it does not assert that the comparison partner is the best-sounding or most
accurate provider. The unchanged original mix is the common, unlevelled
reference. Each page accepts candidate A, candidate B, equivalent, neither or
cannot tell, and cannot change a MIDI result or product default.

## Second authorised-song repeat

The same chain has completed on `I am a Alien mashup`, original seconds
219–234 at 114 BPM and A=440 Hz. The excerpt was selected with a deterministic
one-second group-energy scan over every bass, drums, other and vocal group in
all three provider packs. Of the eligible 15-second windows, 219–234 seconds
maximised 0.65 times the normalised-activity lower quartile plus 0.35 times its
median, with five seconds reserved at both song boundaries.

All provider sums had zero 10 ms envelope lag. Moises correlation at recorded
zero was 0.99952 with a gain-matched residual of -45.47 dBFS. Suno A/B
correlations were 0.92357 and 0.91953 with residuals of -23.63 and
-23.41 dBFS. These remain alignment observations, not role-quality scores.

Every proposed role again ranked first against the corresponding local
HTDemucs role. Bass, drums and vocals had clear margins. Broad `other` was
weaker: Moises similarity/margin was 0.605/+0.119, Suno A 0.531/+0.055 and
Suno B 0.609/+0.132. The identical production MIDI comparison then produced:

| Provider | Bass exact/onset F1 | Drums onset / broad-family F1 | Other exact / chroma / onset F1 | Vocals exact / onset F1 |
| --- | ---: | ---: | ---: | ---: |
| Moises | 0.462 | 0.861 / 0.672 | 0.243 / 0.340 / 0.495 | 0.844 / 0.933 |
| Suno A | 0.190 | 0.874 / 0.742 | 0.164 / 0.251 / 0.406 | 0.864 / 0.909 |
| Suno B | 0.273 | 0.819 / 0.597 | 0.188 / 0.257 / 0.406 | 0.791 / 0.884 |

The local groups produced 21 bass notes, 74 drum hits, 108 `other` notes and
22 vocal notes. The second run retained 204 hashed artifacts and occupied
about 230 MB. Across both songs, drum event timing is consistently the most
stable result and broad `other` is consistently unsuitable as a single
instrument role. Bass varies materially. Vocal stability is passage-dependent,
which is exactly why cross-song and human evidence must precede a default.

The next bounded development increment uses this evidence to:

1. compare the finished mix, broad estimates and any supplied stems without
   silently selecting a winner;
2. listen to the now-staged level-matched bass, drums, other and vocal groups;
3. listen to the completed MIDI and dry audition evidence rather than promote
   it from metrics alone;
4. retain the completed second-song repeat as cross-song evidence;
5. split broad `other` and, where useful, composite drums into narrower
   hypotheses before expecting instrument-specific MIDI; and
6. keep every result private and inactive before considering a Studio
   importer.

## Narrow `other` evidence

Leaf-level comparison is now complete on both authorised excerpts. It is
deliberately negative evidence against splitting by provider filename alone.

On `Be Alone`, the three Suno A/B same-label pairs each ranked first in both
directions, but only the `Synth` pair was a strong full signal match
(similarity 0.936). `Keyboard` ranked first largely by spectral shape at only
0.461 similarity, while the Moises `keys` leaf ranked the matching Suno
`Keyboard` leaf third in both packs and instead matched Suno `Synth` most
closely. A tidy label-level result inside one provider is therefore not an
instrument identity.

On `I am a Alien mashup`, only the Suno `Keyboard` pair ranked first in both
directions, at 0.937 similarity. Same-label `Guitar`, `Synth` and `Other`
failed the bidirectional rank-one test. Moises `keys` ranked Suno `Keyboard`
fourth/second for A and third/second for B; Moises `other` also did not align
with Suno `Other`. No observation was accepted or activated.

The next local candidate is consequently a private, pinned six-source Demucs
experiment limited to its added guitar and piano estimates plus residual
accounting. It must be compared on both exact windows against every supplied
leaf and its downstream MIDI, without assuming that a provider label is score
truth. The official six-source configuration is experimental and its piano
bleed warning remains part of the gate. Installation, exact checkpoint hash,
terms, offline behaviour and runtime evidence must be recorded before it runs.

The separate private registry and installer require explicit acceptance:

```bash
SUNOFRIEND_ACCEPT_DEMUCS_6S_PRIVATE_EVALUATION=1 \
  sh scripts/setup-demucs-6s-model.sh
```

The installer fetches the official 54,996,327-byte
`5c90dfd2-34c22ccb.th` file only when it is absent, then requires full SHA-256
`34c22ccb381c6f9fdbf324f04e1e2fe21aaaf293f5ded163a162697ff9a02ddd`
before publishing it with private permissions. The resolver never downloads,
the challenger is excluded from normal `ai-doctor --require all`, and model
installation alone enables no separator surface.

On 31 July 2026 the owner explicitly accepted the private-evaluation terms.
The installer downloaded that exact file to the external owner-only model
directory and both byte-count and full-hash checks passed. Before any
deserialisation, the bounded static inspector validated a 527-member stored
Torch ZIP with 525 tensor members, protocol-2 pickle, 17,488 opcodes, no
trailing bytes and the expected sole application global
`demucs.htdemucs.HTDemucs`. Sunofriend now recognizes only that exact
checkpoint hash plus exact globals/opcode profile as strong static package
evidence. Static inspection still authorizes neither loading nor execution;
the separately accepted private canary remains the only intended runner.

The private parent/worker contract is also prepared without a real model run.
It retains the existing four-source schemas unchanged and adds disjoint
six-source request, worker-result and experiment schemas. The worker requires
the exact `htdemucs_6s` signature, checkpoint hash, package version, CPU/zero-
shift settings and official source order; the parent accepts exactly bass,
drums, guitar, other, piano and vocals arrays. A complete fake-worker test
proves fresh owner-only output, per-array and PCM24 hashes, reconstruction
accounting, input revalidation and all-false activation/publication effects.
This is execution preparation, not evidence about the model's audio quality.
No CLI, TUI, Simple or Workbench route imports it.

After explicit acceptance and installation, the private-only entry point is:

```bash
SUNOFRIEND_ACCEPT_DEMUCS_6S_PRIVATE_EVALUATION=1 \
  .venv/bin/python scripts/private-demucs-six-source-canary.py \
  "/absolute/44.1-kHz-excerpt.wav" \
  --out "/absolute/fresh-private-six-source-run"
```

The script refuses to start without the same acceptance environment variable,
accepts only a fresh output, resolves the exact local checkpoint without a
download and publishes no candidate or source-graph operation.

The first authorised real-song development corpus is now available locally
under [`../stem_examples`](../stem_examples/README.md). It contains four
Ezzye originals, one detailed Moises export and two distinct Suno exports per
song. The 5.4 GB of WAV evidence is intentionally ignored by Git; the tracked
corpus index records permission, credit, geometry and readiness without
publishing provider-derived audio. `Be Alone` and `I am a Alien mashup` now
have staged and compared excerpts; one more song is ready for excerpt
selection. `In the way` remains blocked
because its 225.88-second original
does not share the roughly 160.5-second provider horizon.

Public Studio finished-song separation remains Phase S4. One-action Simple
separation remains Phase S6 and requires cross-song, licence, offline,
resource, downstream-MIDI and human listening acceptance.
