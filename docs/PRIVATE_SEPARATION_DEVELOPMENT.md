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

Before attaching another real worker to the private transport, the actual
macOS process image can be observed without a model, checkpoint or audio:

```bash
.venv/bin/python scripts/private-macos-runtime-process-image.py \
  --runtime .venv-ai/bin/python \
  --out work/separation-bakeoff/macos-runtime-process-image-v2/runtime-process-image.json
```

This is not the same as hashing `.venv-ai/bin/python`. On the tested
python.org runtime that path resolves to a signed framework launcher, which
then becomes `Resources/Python.app/Contents/MacOS/Python`. The parent observes
the exact child PID with `proc_pidpath`, asks the kernel for its CDHash with
`csops`, and requires it to match the strictly validated static signature of
the expected final image. It also requires the exact `sandbox-exec` provider
to be on a read-only filesystem and rechecks all three full-file hashes after
the child exits.

The standalone evidence is owner-only and path-free. It deliberately says
`bound_to_model_worker: false`: that inert canary still creates no audio,
downloads nothing and enables no separator. The same prepared parent-PID
primitive is now separately attached to one authorised Kim Vocal 2 worker run,
as recorded below. Neither result establishes dynamic native-library closure
or complete byte-for-byte execution identity.

The next model-free canary inventories stable file-backed executable mappings
from an exact inert child after seven fixed standard-library native imports:

```bash
PYTHONPATH=src .venv-ai/bin/python \
  scripts/private-macos-native-image-inventory.py \
  --runtime .venv-ai/bin/python \
  --out work/separation-bakeoff/macos-native-image-inventory-v1/native-image-inventory.json
```

The child reports only readiness. The parent uses macOS `libproc`
`PROC_PIDREGIONPATHINFO`, takes two consecutive snapshots, requires their
complete internal mapping geometry to match, hashes every reported executable
file, waits for clean exit and rehashes every file. The evidence retains no
path or PID. Two fresh runs were byte-identical: each owner-only mode-`0600`
JSON was 9,411 bytes, self-hashed to
`be0a3601e7fddaabc68772fa15f4d5363f93fcaa448c691cbbd1bd9e7845714a`
and had file SHA-256
`c954dfbe615a5c4df6bc30c3e9a6b45d0c0334a91633d8b2a3e00a7327552b53`.
The stable inventory contained 13 executable file-backed regions across 13
files totalling 30,677,328 bytes. Twelve files passed strict static code
validation; one was retained explicitly as not strictly valid. All files
matched after the child exited.

This is still not a complete dyld or native-loader audit. Individual dyld
shared-cache constituents are not enumerated by this contract, transient loads
between snapshots are not excluded, and reopening a mapped file does not prove
that its current bytes are the bytes mapped in memory. It is not attached to
the model worker and enables no separator.

The same inventory primitive is now attached separately to the exact
authorised Kim Vocal 2 worker. This is an opt-in private-development mode, not
the model-free command above and not a public separator. The worker sends one
path-free readiness record through an explicitly inherited pipe only after
inference and before writing its PCM24 quarantine. It then blocks until the
parent has bound the signed process image, taken two stable executable-region
snapshots and sent the exact release record through a second pipe. Both waits
are bounded; failure closes the pipes and kills/reaps the child without
claiming completed evidence.

The private command requires all earlier evidence layers explicitly:

```bash
PYTHONPATH=src .venv-ai/bin/python \
  scripts/private-melroformer-authorised-worker.py \
  --repository-root "$PWD" \
  --runtime .venv-ai/bin/python \
  --source-root /owner-only/exact-kim-source \
  --checkpoint /owner-only/model.safetensors \
  --companion-root /owner-only/checkpoint-directory \
  --authorised-excerpt /owner-only/authorised-separation-excerpt.json \
  --authorisation-report-sha256 EXPECTED_SHA256 \
  --staging-directory /fresh/owner-only/staging \
  --device gpu \
  --bind-python-import-closure \
  --observe-outbound-attempts \
  --bind-native-image-inventory \
  --bind-real-worker-supervision
```

Two fresh `Be Alone` observations each found 33 executable file-backed regions
across 33 files, no unpathed executable region, and the exact main process
image once. The path-free inventories were identical between runs; all files
were unchanged after their child exited, 32 passed strict static-code
validation and one was explicitly retained as not strictly valid. The two GPU
float-output hashes differed, so bitwise conversion repeatability is not
claimed. A later opt-in run added `--bind-real-worker-supervision`. Before any
Sunofriend import, the private launcher observed exactly FDs 0-2. The real
worker then reported an empty main-thread mask and the expected post-CPython
selected handlers; the parent bound the result to synchronous exact-child
wait, normal exit 0 and reap. The 120,078-byte owner-only observation hashes to
`f00572017dfbef238a37e71ac07b7d01795a49fe9ff54f628d03bdc9d763043e`;
its self-hash is
`7bd289b9e55e38e5619b299ff42523f708bca41ff8f67ba161b1df758d6eca4e`.
This does not reconstruct pre-exec signal state, establish native
process-group or descendant supervision for this real worker, enumerate dyld
shared-cache constituents, exclude all transient loads, prove mapped bytes
equal reopened files, or enable any source-graph, automatic-selection, Simple,
Studio, product or publication route.

A later model-free native matrix v3 closes the underlying process-group state
machine only. It creates a private session, retains an exited leader unreaped,
observes one surviving descendant, signals and drains the group, then
exact-reaps the leader. The Kim command above still uses the synchronous
subprocess path and does not inherit that proof.

Model-free native matrix v4 now attaches one bounded observer directly to the
opaque owner. The owner internally applies `proc_pidpath` and `csops` to its
exact live child, compares a prepared signed process-image path and CDHash, and
returns no PID, PGID or path. The blocking canary first supplies a wrong path
and wrong CDHash, confirms both are rejected without changing ownership, then
proves the expected image and exact reap. This does not run Kim Vocal 2. The
current Kim path still uses its existing PID-consuming observers, and
runtime/process-image pathname TOCTOU is not closed.

Model-free native matrix v5 adds the second owner-bound primitive. A
factory-only single-use broker starts the bounded kernel Sandbox denial stream
before native spawn. It parses only the fixed log-event shape and asks the
opaque owner whether each transient kernel-reported event PID is its exact
private-session leader. The owner never returns its PID or PGID, and the
broker retains no event PID, destination or raw message. A fixed worker
replaces itself through `sandbox-exec`, attempts only loopback port 9 and stays
alive while the broker drains. The live matrix observed the one deliberate
denial, zero other owned denials, normal zero exit, group emptiness and exact
reap; replay was rejected. This remains model-free and is not attached to Kim.

Model-free native matrix v6 adds an owner-bound worker-ready executable-region
canary. The exact native owner calls `proc_pidinfo` for its internally retained
live child and returns no PID/PGID. A fixed model-free worker loads seven fixed
native modules, writes one PID-free ready marker and stays alive while the
parent takes two stable owner-bound snapshots. The parent measures every
file-backed mapping, requires the signed main Python process image exactly
once, terminates and exact-reaps the private group, then remeasures the mapped
files. The final report contains counts and an artifact-manifest hash, no path
or process identifier. Transient paths exist only inside the private observer;
dyld shared-cache coverage, transient-load exclusion, mapped-memory equality
and pathname TOCTOU remain unproven. This is not attached to Kim.

The following validation-only increment now fixes the evidence shape that a
future bridge would have to derive from the exact native owner. It requires
the bound native session, native execution and worker-result hashes, normal
zero exit, matched worker identity, observed leader exit, complete group drain,
exact leader reap and released ownership. It rejects timeout escalation,
ownership loss, raw PID/PGID retention and exposed signal authority. This is a
shape validator and blocked plan, not execution provenance: the current Kim
route cannot emit it, no model was run, and no separator route changed. The
process-image part of that engineering task now has a model-free owner-bound
primitive, matrix v5 supplies the equivalent kernel-network primitive and
matrix v6 supplies the worker-ready executable-region primitive. A combined
fixed-worker integration proof that derives the terminal projection from the
same live owner was the next required proof.

Model-free native matrix v7 now supplies that proof in one execution. A fixed
self-sandboxing worker emits a PID-free ready marker after loading its bounded
native-module set, then performs one deliberate loopback denial and writes a
private identity-bearing result. The same opaque owner binds the signed process
image, two stable executable-region snapshots, the single-use kernel-network
observation, the private worker-result identity, normal exit, complete group
drain and exact reap. The code-owned terminal projection consumes the private
PID/PGID only through the owner's boolean matcher and returns no process ID,
path or destination. No model, checkpoint or audio was opened. This closes the
combined fixed-worker prerequisite only: the real Kim worker still lacks a
native entry point with its explicit ready/release transport and remains on the
current subprocess supervisor.

Model-free native matrices v8 and v9 then fix the future real-worker transport
without granting execution authority to data. The native owner maps private
request, result and checkpoint files plus ready and release pipes to descriptors
3 through 7. A bounded canonical JSON contract rejects duplicate keys, trailing
frames, stale nonces and altered bootstrap identity before readiness. The valid
bootstrap consumes the request, deliberately reads no checkpoint bytes, waits
for the exact release record and emits a path-free result whose private PID and
PGID are used only by the owner's boolean matcher. No model, checkpoint or audio
is opened, and the existing Kim subprocess route is unchanged.

Model-free native matrix v10 adds the fixed launch envelope that will surround
that transport. The C boundary accepts only `/usr/bin/sandbox-exec`, constructs
the sandbox profile itself around one validated private staging directory and
supplies a fixed offline environment. The sandboxed bootstrap receives the same
descriptor mapping and ready/release lifecycle while deliberate loopback,
`fork()` and outside-staging write canaries each fail with `EPERM`. This proves
the launch shape only. The next increment must replace the model-free bootstrap
with the fixed Kim worker adapter, load the accepted checkpoint exclusively from
fd5, and bind one previously authorised excerpt to the same opaque-owner
terminal projection before any route can be promoted.

The real bridge now has the checkpoint-side plumbing required by that next
step. Its Safetensors inspector can consume an already-open non-inheritable,
read-only descriptor with positioned reads, returning path-free static evidence
without moving the caller's offset. The model loader can then give MLX a
non-inheritable duplicate of that exact descriptor and records that it did not
reopen the checkpoint path. Unit tests use small synthetic containers only; the
accepted Kim checkpoint and authorised audio were not opened. This plumbing is
not yet connected to a real native worker, so it grants no new route or result.

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

The private parent/worker contract retains the existing four-source schemas
unchanged and adds disjoint six-source request, worker-result and experiment
schemas. The worker requires the exact `htdemucs_6s` signature, checkpoint
hash, package version, CPU/zero-shift settings and official source order;
the parent accepts exactly bass, drums, guitar, other, piano and vocals
arrays. A complete fake-worker test proves fresh owner-only output, per-array
and PCM24 hashes, reconstruction accounting, input revalidation and all-false
activation/publication effects. No CLI, TUI, Simple or Workbench route imports
it.

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

The real checkpoint was then run once on each fixed 15-second authorised
window. Both runs produced all six expected 44.1 kHz stereo estimates from one
model application. `Be Alone` finished in about 15.6 seconds and recorded a
raw model-sum error of -21.26 dB to the source; `I am a Alien mashup` finished
in about 16.1 seconds and recorded -24.28 dB. The separately persisted
source-minus-estimate residual closed the re-read PCM24 accounting sum exactly
on both runs. This closure proves accounting, not separation accuracy.

An additional private evaluator now hash-binds each six-source run to its
authorised model input and existing provider-leaf evidence. It transcribes
`guitar`, `piano`, `other`, residual and every provider leaf with the same
neutral Basic Pitch settings, creates same-patch MIDI previews and writes a
self-contained listening page. Labels do not contribute to the ranking and
all selection, activation, production and publication permissions remain
false.

The two-window evidence does not support promoting the six-source challenger.
On `Be Alone`, guitar RMS was 0.01595 and piano RMS only 0.000364; guitar's
nearest audio leaf was Moises `keys`, piano's was Moises `other`, and their
nearest MIDI leaves also differed. The broad `other` estimate was the strong
match to a Suno `Synth` leaf (audio similarity 0.933). On `I am a Alien
mashup`, guitar and piano were both near-silent at RMS 0.000563 and 0.000494,
while broad `other` matched Moises `keys` most closely (audio similarity
0.857). These are descriptive comparisons against imperfect provider outputs,
not ground truth, but they show that the new lanes did not reliably isolate
the musical material needed by downstream MIDI. Human listening remains
available in each local `six_source_provider_midi_review.html`; no listening
choice has been recorded.

The next bounded experiment is same-checkpoint Demucs-MLX parity, followed by
one exact licence-audited RoFormer challenger if the quality gap remains.
Runtime parity must not be mistaken for model-quality improvement.

The parity plan and runner are now implemented without installing MLX. The
read-only plan is:

```bash
.venv/bin/python scripts/private-demucs-mlx-parity.py --plan \
  --checkpoint ~/.local/share/sunofriend/models/demucs-4.0.1-htdemucs-6s/5c90dfd2-34c22ccb.th \
  --python .venv-ai/bin/python
```

It requires the already-accepted 54,996,327-byte checkpoint at the same full
SHA-256 and reports exactly five missing MIT-licensed packages:
`demucs-mlx==1.4.4`, `mlx==0.31.2`, `mlx-metal==0.31.2`,
`mlx-audio-io==1.3.11` and `mlx-spectro==0.7.0`. Installation is deliberately
separate from the ordinary AI runtime and required explicit approval. The plan
names PyPI/files.pythonhosted.org plus a possibly varying PyPI mirror/CDN as
setup network destinations and changes only `.venv-ai`; it installs no model
and no system package.

The eventual worker does not use demucs-mlx's named-model loader, first-run
download or model cache. It verifies the caller-supplied `.th` bytes first,
deserialises that exact checkpoint, converts it to MLX in memory once and runs
1–8 sealed reference excerpts. It records conversion and per-excerpt timing,
compares every float32 sample for all six roles, and writes private listening
WAVs. The harness keeps selection, promotion, source-graph activation, Simple,
Studio and publication false. The user approved the five exact packages on
31 July 2026; they were installed into `.venv-ai` with no model or system
package change.

After installation, `--plan` reported every exact package and checkpoint match.
The two fixed-window comparison then ran as:

```bash
SUNOFRIEND_ACCEPT_DEMUCS_MLX_PRIVATE_EVALUATION=1 \
  .venv/bin/python scripts/private-demucs-mlx-parity.py \
  --reference-run work/separation-bakeoff/be-alone-six-source-191-206-v2 \
  --reference-run work/separation-bakeoff/i-am-a-alien-six-source-219-234-v1 \
  --checkpoint ~/.local/share/sunofriend/models/demucs-4.0.1-htdemucs-6s/5c90dfd2-34c22ccb.th \
  --python .venv-ai/bin/python \
  --out work/separation-bakeoff/demucs-mlx-six-source-parity-v1
```

The `1e-4` relative-maximum threshold shown in the report is the upstream
converter's direct random-input verification reference. Sunofriend applies it
descriptively to split full-pipeline output; it is not an automatic acceptance
gate. First-case compilation and later process-local reuse are reported
separately so a warm result cannot be presented as an ordinary first run.

The real result is `complete_review_required`, not parity acceptance. MLX took
5.106 seconds on its first 15-second case versus the sealed PyTorch CPU run's
9.905 seconds (1.94x observed), then 0.623 seconds versus 10.423 seconds on the
second process-local case (16.72x observed). Reported peak resident memory was
about 604 MB for the MLX process versus 2.10–2.14 GB in the two historical
PyTorch processes. Bass and drums correlated 0.99994–0.99999 with the PyTorch
arrays, but low-energy guitar fell to 0.743 on one case and piano was only
0.363–0.376. No role met the borrowed `1e-4` relative-maximum reference and the
worst relative maximum was 3.4146. The runtime port is therefore fast evidence,
not a safe drop-in replacement. It remains private and inactive while the
conversion/full-pipeline difference is investigated.

### First track-specific private-reference repeat

The authorised-excerpt bridge now also accepts a FLAC original from the
private-reference manifest, but only when the selected track contains an exact
`user_authorised` / `private_local_evaluation_only` record with repository and
public-demo permission both false. Directory presence is still rejected as
authority. Tests cover the positive FLAC path and rejection before the model
runner when that track record is absent.

The corrected `Mauvais djo - Pilé` pack was exercised at seconds 33–48 using
the pinned PyTorch four-source checkpoint. The deterministic activity scan,
not song recognition, selected the window. The original and non-metronome
Moises sum had 0.994250 recorded-zero sample correlation, 0 ms best envelope
lag and 0.997934 envelope correlation. HTDemucs inference took 10.15 seconds
with about 2.12 GB reported peak resident memory; source, checkpoint, launcher
and worker identities remained unchanged and PCM accounting closure passed.

All four proposed Moises groups ranked first against their matching local role.
Bass, drums and vocals had similarities 0.978, 0.997 and 0.942. Broad `other`
was only 0.597 with a +0.075 margin over vocals, so it remains an especially
important target for narrower separation. The identical inactive production
MIDI comparison produced local/Moises note counts of 25/19 for bass, 48/46 for
drums and 127/109 for `other`. Drum onset F1 was 0.872, bass exact-pitch/onset
F1 0.545 and `other` exact-pitch/onset F1 0.407. Both broad vocal inputs yielded
zero notes through the current dominant-contour path. That result does not
show that the source is silent; it identifies a transcription failure to
address. No result was accepted, selected, imported, published or exposed in
Simple/Studio mode.

The same window has now exercised the isolated Kim Vocal 2 worker without
weakening that conclusion. The bridge accepts this second, track-specific
authority form only when the private-reference manifest records
`user_authorised` / `private_local_evaluation_only`, a non-empty recorded date,
and both repository-distribution and public-demo permission as false. The
worker's default PCM24 quarantine remains strict. This input's additive
instrumental residual reached a raw peak of `1.0516957`, so the explicitly
enabled worker-only headroom path applied one shared linear gain of
`0.9413369246` to source, vocal and instrumental before PCM24 persistence.
That is common attenuation, not independent stem normalization. Re-read
vocal plus instrumental audio reconstructed the equally attenuated source
within two PCM24 least-significant bits.

The run retained verified-open-descriptor worker-script execution, the
complete Python import closure and the kernel-Sandbox denial observation. Its
path-free evidence SHA-256 is
`92bcc2e3ebd631398177cbc7e71795928b10e37328e055634a616e3f71f635f3`;
the owner-only observation file hashes to
`733b3e03b5fa1e365aad6fcb972018e098b3140cacce2aa4cd979aeeb03ed1ea`.
The unchanged 130 BPM, A=440 Hz production pYIN contour again produced zero
notes. The existing polyphonic vocal path also produced no register
hypotheses. The self-hashed inactive MIDI-evaluation document is
`6491f749e1e2ad3311c24fefa2f60e42858c24d460a095c3a800f0aa9cd99615`.
Kim therefore did not recover this excerpt's vocal MIDI; the next bounded
diagnostic keeps production thresholds unchanged and tests the already
separate vocal leaves before changing a tracker or promoting a separator.

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

Five additional source-plus-Moises folders are now indexed separately in
[`../stem_examples/private-reference-corpus.json`](../stem_examples/private-reference-corpus.json).
They add 90 stereo 44.1 kHz audio files (about 3.02 GB) but no Suno packs.
Their artist-labelled directory names are not treated as ownership or reuse
claims, and the runner rejects any track without exact track-specific private
authority. All five now have exact original/musical-stem horizons and can
become private robustness evidence only after that authority is recorded. The
redone `Mauvais djo - Pilé` original and 16 musical stems share an exact
6,882,992-frame horizon, their sum has 0.997537 recorded-zero correlation and
its best 10 ms envelope lag is 0.00 seconds. This removes the former
geometry/clock blocker. The user then authorised that one track for private
local evaluation on 31 July 2026; repository distribution and public-demo use
remain false. `Monkey Man` declares A=446 Hz and also requires an explicit
tuning plan before downstream MIDI comparison.

### Exact BS-RoFormer challenger registration

The independent-architecture step now names one exact candidate rather than a
model family or runner catalogue: ZFTurbo's four-stem BS-RoFormer MUSDB18HQ
[release `v1.0.12`](https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/tag/v1.0.12), source revision
`aef04b2e52fb3beaf25e333199f5a7236e628e7b`. The release contains a
527,385,512-byte checkpoint and a 4,566-byte configuration; Sunofriend records
the configuration's independently observed SHA-256 as
`d8afb980318d0c08b9c2e24a7adc00d4f3150320c127a7e4de861800d1321939`.
The proposed comparison is bounded to the existing two 15-second sealed
excerpts and must improve composite `other` and downstream MIDI without harming
drum timing or inferring a winner from SDR alone.

Inspect the static plan with:

```bash
.venv/bin/python scripts/private-roformer-challenger.py --plan
```

The command performs no network access, installation, download, model import,
deserialisation or worker launch. An optional `--checkpoint /absolute/path`
only hashes an already-present non-symlink regular file; because the upstream
release has no published checkpoint SHA-256, that observation can never make
the candidate eligible by itself.

The plan remains `blocked`/`not_run`. The repository's MIT licence covers its
software and associated documentation, but the release does not state
checkpoint-specific terms and Sunofriend does not project the code licence
onto the weights. A 1 August 2026 recheck of the official GitHub release API
still returned a null asset digest. Apple-silicon resource behaviour is
unmeasured, the actual checkpoint has not passed the existing static
inspection contract, and a bounded RoFormer worker does not exist. No package
or checkpoint was installed, no new approval was inferred, and no CLI, TUI,
Simple, Studio, source-graph or public route was added.

That recheck is now reproducible evidence rather than prose alone.
`private-separation-roformer-upstream-evidence.json` retains a bounded subset
of the official release API, tag-ref API and pinned-revision licence evidence
at SHA-256
`7767d27d2b4e75f0780560e1510ca835af35a0f5600c200add5654b9cf875bd8`.
It records that tag `v1.0.12` resolves to
`aef04b2e52fb3beaf25e333199f5a7236e628e7b`, the release body only identifies
the MUSDB18HQ model, and both release asset `digest` fields are null. Capturing
the observation used the public GitHub network endpoints but downloaded
neither release asset. Verify the already-tracked snapshot locally with:

```bash
PYTHONPATH=src .venv/bin/python \
  scripts/private-roformer-upstream-evidence.py \
  --repository-root /absolute/path/to/Sunofriend
```

The verifier is descriptor-pinned, path-free and read-only. It performs no
network request, asset open, installation, model import, deserialisation or
process launch. It returns `verified_no_checkpoint_authority`, not approval:
absence of terms is not permission, a null digest is not checkpoint identity,
and the repository code licence remains scoped separately from the weights.

The exact source import audit also found that upstream's broad inference
utility imports configuration and metric dependencies that the BS-RoFormer
model itself does not need. Its pinned OmegaConf path requires an sdist-only
ANTLR runtime, while the full requirements also include training, GUI,
experiment-tracking and unrelated architecture packages. Sunofriend therefore
does not use that requirements file as an installation plan.

`requirements-private-separation-roformer-macos.in` now describes a future
bounded adapter around only `attend.py` and `bs_roformer.py`. It must load those
files through an isolated synthetic package rather than execute upstream's
`models/bs_roformer/__init__.py`, whose unrelated MelBand import was the only
reason librosa appeared. Canonical PCM WAV I/O will use Python's standard
library, so SoundFile and its bundled LGPL media libraries are also outside the
runtime. This reduces the resolution from 38 packages to 15.

A wheel-only `uv` resolution for CPython 3.12.10 on this Darwin arm64 Mac
produced the fully pinned, hash-required
`requirements-private-separation-roformer-macos.txt` lock at SHA-256
`7b8ade3828d75cca47cacc447dfa90e733c9425eccd0e341d5a6ba220a81ba65`.
The exact-version audit in
`requirements-private-separation-roformer-macos.licenses.json` accounts for
all 15 packages and is bound to that lock at SHA-256
`ecc5b6a012e5c8e1c97dba0426b6f0f172e17b765c94382e14477f005766e4d8`.
Their primary terms allow private local evaluation. NumPy and PyTorch binary
component notices still need retention review before runtime redistribution;
the audit is not legal advice and does not cover the checkpoint. A dry run
resolved successfully and changed no environment. The lock must target a fresh
`.venv-roformer-private`, never the existing `.venv-ai`; it is still not
approved for installation. The selected PyTorch wheel requires macOS 14 or
later.

The next execution boundary is also defined without making the candidate
runnable. `_separation_roformer_contract_plan.py` binds a future adapter to the
existing `separation_checkpoint_inspection` and `separation_worker_contract`
schemas. Static inspection must hash a descriptor-pinned checkpoint, validate
the bounded stored-only Torch ZIP inventory and parse pickle opcodes without
deserialisation. It cannot authorise loading. A later worker request is limited
to two 15-second canonical PCM24 excerpts, the four exact roles, a fresh
private quarantine, denied network and child processes, and parent-verified
WAV hashes, geometry and source horizon. The static/checkpoint contract has not
been applied to this checkpoint, and the executable RoFormer worker does not
exist.

The request/result boundary is now concrete rather than only prose.
`_separation_roformer_worker_protocol.py` builds a self-hashed, immutable,
path-free protocol for one or two cases. Each case must be a distinct canonical
stereo 44.1 kHz PCM24 WAV identity of at most 661,500 frames, 15 seconds and
4 MiB. The protocol fixes the generic worker schemas, source revision and
manifest, configuration and dependency-lock hashes, checkpoint asset identity,
serial fresh-worker/fresh-quarantine lifecycle, seed 0, canonical sorted roles
`bass`, `drums`, `other`, `vocals` and the corresponding `STEMS/*.wav`
allowlist. Result geometry must have the exact source frame horizon and every
hash and geometry must be parent-verified. The validator rejects extra fields,
path-like IDs, duplicate or unsorted cases, repeated canonical audio, invalid
or oversized geometry, permission changes and hash tampering. It performs no
filesystem, network or process operation and has no CLI/TUI route. This is
protocol validation only: request materialisation, checkpoint access,
deserialisation, model import, worker start, inference, selection, publication
and product routing all remain explicitly forbidden.

The future isolated loader also has an exact source manifest rather than a
trust-on-path boundary. `private-separation-roformer-source-manifest.json`
records the sizes, SHA-256 values and direct imports of only `attend.py` and
`bs_roformer.py`, plus the exact MIT licence bytes at the pinned release
revision. Inspect an already-present source checkout with:

```bash
PYTHONPATH=src .venv/bin/python scripts/private-roformer-source.py \
  --source-tree /absolute/path/to/exact-v1.0.12-checkout
```

The verifier walks only fixed directory components with non-following,
non-inheritable descriptors and hashes three regular files. The two Python
modules are capped at 64 KiB each and parsed with the standard-library AST
without execution. Their direct import roots must exactly match the manifest;
relative imports, wildcard imports, dynamic-import calls and runtime code
generation calls fail closed. The verification report records the observed
empty unsafe-call surfaces. It does not invoke Git, trust a mutable revision
label, execute `__init__.py`, import the model or write a report. It passed
against the temporary exact release checkout used for the source audit. The
future runtime must independently pass it again.

The source and tracked runtime planning evidence can now be checked together:

```bash
PYTHONPATH=src .venv/bin/python scripts/private-roformer-admission.py \
  --repository-root /absolute/path/to/Sunofriend \
  --source-tree /absolute/path/to/exact-v1.0.12-checkout
```

This read-only command descriptor-pins and verifies the source manifest,
six-package input, 15-package hash lock, exact-version licence audit and exact
official upstream-evidence snapshot. It
also checks that every direct package is in the lock, every locked package is
covered by the licence evidence, the audit did not perform or authorise an
installation, and checkpoint terms remain outside its scope. The upstream
subreport confirms the official snapshot but keeps digest, terms, allowed use,
identity and private-evaluation readiness false. The self-hashed
report deliberately omits both supplied absolute paths. A successful evidence
check still returns `blocked`: it verifies only that the code and runtime plan
are intact. It does not inspect or open a checkpoint, install the runtime,
import model code, start a worker or make private evaluation eligible.

### Exact MelBand-RoFormer vocal challenger registration

The first candidate with both checkpoint-specific terms and published content
identity is now registered separately from the blocked broad model. It is
[`mlx-community/mel-roformer-kim-vocal-2-mlx`](https://huggingface.co/mlx-community/mel-roformer-kim-vocal-2-mlx)
at revision `64cbfcb004e39430e5f584552c05949440ec39ce`: a 456,483,463-byte
BF16 Safetensors conversion with published SHA-256
`312c38e5b698f8dfaa4d6064e8f79010744825828917871a9d22673a43eb7fe5`.
It is a **vocal-only** MelBand-RoFormer, not a broad replacement for Demucs.
The instrumental output would be the exact mixture-minus-vocals residual.

The source checkpoint is Kimberley Jensen's author-hosted Kim Vocal 2 at
revision `ac9b0614ab3cd7f77219e18ba494dfd93956c348`. Its 913,106,900-byte
LFS object has SHA-256
`87201f4d31afb5bc79993230fc49446918425574db48c01c405e44f365c7559e`.
The owner first granted broad use permission in the repository discussion,
then assigned GPL-3.0, and later changed that exact repository metadata from
GPL-3.0 to MIT in the verified 22 April 2026 commit. The conversion repository
also includes a full MIT licence naming both the conversion and original
weights. Two independent Hugging Face file records reproduce the source size
and SHA-256. This is sufficient checkpoint-specific evidence for planning a
private local evaluation; it is not legal advice and does not approve a run.

A user-supplied 8,405-byte RoFormer evidence pack at SHA-256
`8f0e06928eea399648e0b30df5e41f415b72b411aecf96a5e1f017c223d3924f`
was reviewed only as a secondary lead. It contained no model bytes. Its
optional download helper was read but not executed. Primary Hugging Face file
metadata independently corroborated its Kim checkpoint identity and the byte
identities of two ViperX alternatives. Those ViperX candidates remain
inadmissible because repeated hashes prove integrity, not creator-authorised
terms.

Inspect the new static plan and tracked evidence with:

```bash
.venv/bin/python scripts/private-melroformer-challenger.py --plan

PYTHONPATH=src .venv/bin/python \
  scripts/private-melroformer-upstream-evidence.py \
  --repository-root /absolute/path/to/Sunofriend
```

Both commands are read-only and have no public CLI/TUI route. Explicit approval
for the exact Kim Vocal 2 checkpoint's private local evaluation was recorded on
1 August 2026. The exact checkpoint, `config.json`, `LICENSE` and audited
MLX-Audio source slice were then materialised under an owner-only cache outside
the repository. Their published byte counts and SHA-256 identities all match.
The checkpoint is not redistributed and Simple, Studio and the source graph
remain unchanged.

The exact 913,106,900-byte author-hosted source checkpoint was then downloaded
to the private cache and verified at SHA-256
`87201f4d31afb5bc79993230fc49446918425574db48c01c405e44f365c7559e`.
Sunofriend loaded it only through PyTorch's restricted `weights_only=True`
path and reproduced the pinned converter at revision `8380ab8`: all 684
retained source tensors account for all 708 converted tensors, including 12
packed Q/K/V splits. Every tensor name, shape and BF16 payload was bit-exact.
The path-free observation is retained in
`private-separation-melroformer-weight-conversion-parity.json`; its report
SHA-256 is
`7386eaa1d6e93f6b638e60780a589597737ffd3d7bcd48db5586ce93d8080a4c`.
This closes weight-conversion parity only. It does not establish identical
PyTorch-versus-MLX inference output, separator quality or product eligibility.

The next CPU-only, single-chunk comparison used the exact first eight seconds
of the authorised `Be Alone` excerpt. PyTorch `bs_roformer==0.3.10` with the
source weights rounded through BF16 and the published MLX BF16 model reached
117.70 dB SDR, comfortably above the 40 dB implementation-parity gate. The
original FP32 PyTorch checkpoint versus published BF16 MLX reached only 29.14
dB; original FP32 versus BF16-rounded PyTorch was also 29.14 dB. This localises
the observed difference to publication precision rather than the MLX port.
It does not reproduce the upstream 66.08 dB claim because Sunofriend does not
have the upstream test audio and deliberately used a different authorised
song. The path-free observation is in
`private-separation-melroformer-inference-parity.json`, SHA-256
`a85939af317bdff203de02116b8d2e773bb9e1f392f49b601d3bb2ff1233b389`.
No output audio was retained and this gate measures implementation fidelity,
not separator quality.

The required listening gate at
`work/separation-bakeoff/be-alone-kim-fp32-vs-bf16-vocal-review-v1/`
repeats the original FP32 PyTorch and published BF16 MLX inference on the
same authorised 191–199 second frames, keeps the mixed source as an unlevelled
reference and attenuates only the louder candidate before applying any shared
sample-peak guard. Both final PCM24 candidates measure `-21.093168` dBFS
fixed-window sample RMS with zero reported mismatch. The audio-manifest
SHA-256 is
`202b5e6d91478321b40f276e90ae25f2c7dc8449c1071a2d42d11462932c97d9`.
The answer key remained separate, owner-only and absent from the HTML until
the user's complete export was passed to the verified resolver. The blind
choice was `equivalent`: candidate A was original FP32 PyTorch and candidate B
was published BF16 MLX. The reviewed export SHA-256 is
`aa95d0dc6df8a698864aae34c1c345bddf299b56d82117da0612bb8924693d3c`.
This one-window result does not justify maintaining a roughly doubled FP32 MLX
artifact. It also does not enable, select or promote the BF16 separator.

The exact non-executable runtime boundary is now defined. MLX-Audio `v0.4.3`
resolves to source revision
`41092c02db18efd5b9d8281b2fcc41d84801757a`; the five required source/runtime
files plus licence and package metadata are individually size/hash pinned in
`private-separation-melroformer-source-manifest.json`. The minimal Python 3.12
macOS arm64 runtime is separately locked to `mlx==0.31.2`,
`mlx-metal==0.31.2` and `numpy==2.3.5`, including exact wheel sizes, SHA-256
values and permissive licence findings. It deliberately does not install the
full `mlx-audio` distribution or its unrelated dependencies. The upstream
`from_pretrained` convenience path is forbidden because it can convert a
non-local string into a Hugging Face download. A future adapter must construct
the fixed Kim Vocal 2 configuration and load only an already-open,
hash-verified local checkpoint.
Because the upstream conversion uses non-strict weight loading, the future
adapter must also prove complete post-sanitisation model-key coverage and
reject every missing or unexpected key before inference.

The source audit also found a stale `config.py` comment that calls Kim Vocal 2
GPL-3.0 even though the checkpoint owner had already published the immutable
MIT relicense before MLX-Audio `v0.4.3` was released. It is recorded as stale
runtime documentation; it is not used as the source of checkpoint terms.

`_separation_safetensors_inspection.py` implements a pure-standard-library,
descriptor-pinned inspection contract. It bounds and parses only the UTF-8
JSON header, rejects duplicate keys, unsupported metadata, invalid dtype/shape
geometry, holes, overlaps, trailing polyglot bytes, symlinks and hash changes,
then hashes tensor data as opaque bytes. It never imports Safetensors, NumPy,
MLX or a model and never interprets tensor values. The real checkpoint passed:
its 77,111-byte header indexes 708 BF16 tensors and 456,406,344 opaque data
bytes, with tensor-name-set SHA-256
`2b55335e7522351a36feda283dedb8b44deb7f51a932b289e68a816c11328d59`.
Its converter wrote `__metadata__: null`, which is not the Safetensors
string-to-string-map form. The inspector accepts only that one null-as-empty
compatibility case and reports `metadata_spec_conformant: false`; it continues
to reject every other unsupported metadata shape.

Reproduce the private, non-deserialising artifact preflight with:

```bash
PYTHONPATH=src .venv/bin/python scripts/private-melroformer-challenger.py \
  --plan \
  --checkpoint /absolute/private/cache/model.safetensors \
  --source-root /absolute/private/cache/mlx-audio-source \
  --companion-root /absolute/private/cache/checkpoint-directory
```

The current v15 plan has `artifact_preflight_complete: true` while retaining
`worker_start_permitted: false`.

`_separation_melroformer_worker_protocol.py` fixes one or two path-free,
canonical stereo 44.1 kHz PCM24 excerpts of at most 15 seconds, serial
single-case execution, and exactly two outputs: `vocals.wav` and the
mixture-minus-vocals `instrumental.wav`. Reconstruction within PCM tolerance
is a required result check. Every install, download, checkpoint, import,
process, inference, publication, automatic-selection and product-route
permission remains false; this is a protocol, not a worker.

The model-independent adapter core is now executable only as a synthetic
contract test. `_separation_melroformer_adapter_contract.py` accepts a
precomputed result labelled `synthetic_test_double`; it does not accept or
invoke a callable engine. It validates exact 44.1 kHz stereo geometry, the
15-second frame bound, finite/bounded samples, complete post-sanitisation
model-key coverage and the one permitted upstream dropped-key suffix
`.rotary_embed.freqs`. It then derives `instrumental = source - vocals`,
records deterministic float32 hashes and proves
`source = vocals + instrumental` within a fixed numerical tolerance. It does
not persist PCM24 audio, so persisted reconstruction remains explicitly
unverified. Any claimed file, network, package, checkpoint, tensor, model or
process effect is rejected. This tests the future bridge's validation logic;
it is not the real bridge, a model call or a worker.

Verify the tracked source/runtime records with:

```bash
PYTHONPATH=src .venv/bin/python \
  scripts/private-melroformer-runtime-evidence.py \
  --repository-root /absolute/path/to/Sunofriend
```

The isolated real-model loader bridge is now implemented and has passed one
private probe. It reverified source and checkpoint immediately before import,
bypassed every upstream package initializer and the network-capable convenience
loader, loaded through a descriptor-pinned stream, and reproduced every
sanitizer transformation independently. The real checkpoint contained 708
BF16 keys; 12 permitted rotary-frequency keys were dropped and the remaining
mapping exactly covered 696 model parameters with no missing, unexpected or
shape-mismatched tensors. Model construction plus binding took about 0.42
seconds and MLX reported approximately 458 MB peak memory. No audio inference
or file output occurred in that loader-only probe.

Reproduce that private probe only in the pinned `.venv-ai` runtime:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONNOUSERSITE=1 PYTHONPATH=src \
  .venv-ai/bin/python scripts/private-melroformer-bridge.py \
  --probe \
  --source-root /absolute/private/cache/mlx-audio-source \
  --checkpoint /absolute/private/cache/model.safetensors \
  --companion-root /absolute/private/cache/checkpoint-directory
```

Bounded in-memory inference now passes from one through eight seconds per model
call. The maintained full-excerpt transport divides a maximum 15-second input
into eight-second chunks with a four-second hop, then performs normalized
weighted overlap-add. A 15-second synthetic smoke used three chunks, completed
in about 2.6 seconds and reported about 2.42 GB peak MLX memory. It returned
exactly 661,500 finite frames and proved additive reconstruction with maximum
float32 error about `7.45e-9`. No audio was persisted.

Run the no-output single-chunk smoke by replacing `--probe` above with
`--synthetic-smoke`. Add `--synthetic-seconds 15` to exercise the overlap
transport.

The first report-bound authorised input also passed. The private bridge
verified the self-hashed `Be Alone` 191–206 second receipt, creator authority,
exact PCM24 SHA-256 and 44.1 kHz stereo geometry before inference. Kim Vocal 2
returned active vocal and instrumental arrays over all 661,500 frames in about
2.78 seconds with the same approximately 2.42 GB peak. Its maximum additive
reconstruction error was `2.98e-8`. The bridge persisted no output and returned
only path-free hashes and measurements. This proves transport and accounting,
not separation quality.

The private receipt-bound route requires the exact report-byte SHA-256:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONNOUSERSITE=1 PYTHONPATH=src \
  .venv-ai/bin/python scripts/private-melroformer-bridge.py \
  --authorised-excerpt /absolute/private/authorised-separation-excerpt.json \
  --authorisation-report-sha256 <exact-report-sha256> \
  --control-report /absolute/private/authorised-role-mapping.json \
  --control-report-sha256 <exact-control-report-sha256> \
  --device gpu \
  --source-root /absolute/private/cache/mlx-audio-source \
  --checkpoint /absolute/private/cache/model.safetensors \
  --companion-root /absolute/private/cache/checkpoint-directory
```

The no-output comparison against the sealed controls now passes. Kim Vocal 2's
descriptive evidence similarity was `0.9948` to Moises, `0.9736` to local
HTDemucs, `0.9263` to Suno A and `0.9215` to Suno B. The controls also differed
from one another. These scores establish that the candidate is within the
existing vocal-estimate family; they do not make any control ground truth or
select a winner. Names did not contribute to the scores.

MLX device choice is explicit. `--device gpu` is the private default and took
about 2.8 seconds for the authorised 15-second case at about 2.42 GB peak.
Repeated GPU inference varied by at most `8.94e-8` float32, which projected to
one PCM24 least-significant bit in about 1.19% of samples. `--device cpu` is an
optional repeatable mode: two separate 15-second synthetic runs produced
byte-identical vocals and instrumental hashes, but each took about 23.4 seconds
and peaked at about 3.58 GB. The future writer must hash every actual artifact;
GPU mode cannot promise cross-run byte identity.

The fixed two-role worker has now passed a sequence of authorised observations.
The parent remeasured the exact runtime, worker, source manifest, checkpoint,
companions, authorisation report and source PCM24 before and after the run. It
launched the worker through the exact hashed macOS `sandbox-exec` provider with
network access, child forks and every write outside one fresh private staging
tree denied. Deliberate network, fork and outside-write attempts each returned
`EPERM` in the same process that deserialized Kim Vocal 2 and inferred the
authorised 15-second excerpt.

The latest worker run wrote exactly `STEMS/vocals.wav` and
`STEMS/instrumental.wav` as 44.1 kHz stereo PCM24. Each file is 3,969,044
bytes. The child verified the fresh owner-only quarantine; the parent reopened
the files read-only, verified their hashes and geometry, and reproduced the
same quarantine evidence SHA-256
`83e31cad81cd61e7c6860054dce55b311a2e76b98fdb1f4e9d38e0f1e85b0ed1`.
The persisted vocals-plus-instrumental reconstruction differed from the source
projection by no more than one PCM24 least-significant bit. The complete
path-free worker observation has SHA-256
`ff086359cce141f906a090b5b5edbc21d102a909660b189399bc50a18ce457b0`.
It is retained inside the owner-only quarantine as
`authorised-worker-observation.json`; the exact file SHA-256 is
`f41977a3c18f73a60dabd74162f78ca7abe13598d72cf18c7003cf740cd7dcfa`.
The actual vocal and instrumental files are respectively bound as
`f7ec73ead74de5e008489eab098c75d1a541b0f0e0af068c4d6c7e5e1de5e2cc`
and `af34d208bc10e59fd3fb174c69c68508c43305c2093ddd8f8cbd6a91f4f04386`.
GPU output is allowed to vary only under the measured per-run reconstruction
policy, so every run records its actual hashes.

This closes the earlier model-worker network-denial, outside-write and PCM24
binding blockers. A later run of the same authorised `Be Alone` excerpt also
bound the complete post-inference Python `sys.modules` closure for that exact
worker execution. It classified 320 modules, independently reopened and
rehashed all 277 file-backed modules totalling 18,067,576 bytes, and found zero
unclassified modules. Its path-free closure evidence SHA-256 is
`ce187b7b154269cc3dd7c542db2573bce7194a142aecd3796193d7fb0db2c74f`;
the complete worker evidence is
`3de1b71ef552cd46d1bff1784c4843b7709eeaf945cf3778e53737ca08f350a8`.
The persisted owner-only observation file is 92,670 bytes and hashes to
`230aa5b873e3b81e110bff187ed71d86a7859bec843b9eb71a28f3ca1d0328e6`.

This Python binding is deliberately narrower than a complete executable-image
proof. It does not bind native libraries loaded outside `sys.modules`, close
hash-before-exec path TOCTOU or complete human listening. Exact
PyTorch-versus-MLX runtime parity is now verified separately. Ordinary private
output files can also change after the parent's final observation. Every
Simple, Studio, source-graph, selection and publication permission remains
false.

The third `Be Alone` observation adds a bounded macOS kernel-Sandbox denial
stream around the same real model execution. `/usr/bin/log stream` was hashed
and ready before the worker began. The observer accepted only NDJSON events
from the kernel Sandbox extension, verified the final stream count, filtered
the exact worker PID in memory and then discarded every raw event, PID and
destination. It saw exactly one worker denial: the deliberate
`network-outbound` port-9 canary. It saw zero other worker denials and zero
unrelated denials. The path-free network evidence SHA-256 is
`393bc04ec7247c415dd83d1732cbd84f47f5b5cb99b98c35206a2b6bc891ce5c`;
the complete worker evidence is
`11e10ca1dbb372e63f785c4a935a554d1c036232b539cf66552e6e4c53f6c534`.
The owner-only observation file is 94,545 bytes and hashes to
`f623c2e1a99dabfbe3c2f9be16f5116ac8555c2dc89300dff9f6a017381336dd`.
This records sandbox-denied `network-*` acquisitions, not successful traffic
or packet capture. Unified logging is not described as a packet monitor. The
executable path-to-execution race and native non-module load closure remain
open blockers.

A fourth authorised `Be Alone` observation closes only the worker-script part
of that race. The parent opens the exact non-symlink, single-link worker once,
verifies its 6,730 bytes and SHA-256
`372ef11b14898726b578cd9bbe0088ce5db5fde12e13934afb63b3b95e286a35`,
rewinds the same file description and gives it to Python as the standard-input
script. A pathname replacement after that open cannot change the executed
bytes. The import closure independently reopens the repository path and binds
`__main__` to the same identity. The path-free worker evidence is
`e074e3da5bc836fe2da104095d375f0ed626a49e133c6438b0ffb14e8a5a34ca`;
the owner-only 94,873-byte file hashes to
`5d59bfa00272b173cb71e34ad4b951f4640807ba155a51bdc6bdbef896101909`.
It retained 320 modules, 277 files, 18,067,782 bytes and the same one denied
network canary with zero other worker denials. `/usr/bin/sandbox-exec` and the
Python virtual-environment runtime remain pathname-launched, so complete
path-to-execution TOCTOU is not closed.

A fifth authorised `Be Alone` observation now attaches the parent-PID runtime
image check to the real model worker rather than an inert canary. The network
observer is ready first; the parent then starts the descriptor-executed worker,
observes that exact PID's transition from the signed python.org launcher to
the signed `Python.app` image before waiting for completion, and requires the
kernel CDHash to match the parent's strict static-code identity. After the
worker finishes, provider, launcher and image full-file hashes are remeasured.
The exact `sandbox-exec` provider must remain on its read-only filesystem.

The new path-free v6 evidence self-hashes to
`fd9ee6dd9a75896e87f6a01e01709ca3f161ca0d60ca6a2845d20041c2644249`;
its nested runtime binding hashes to
`1d13892eb87d3709b6b975e363e14f743d6adcacbeb37c6afa5d4bb07b55c798`.
The owner-only 97,617-byte observation file hashes to
`4de792916963efb020c739af1c048d1399b09f742df617ba00fe5be1db5747cb`.
It retained 320 modules, 277 files and 18,075,137 bytes with zero unclassified
modules, saw one deliberate denied outbound canary and no other worker denial,
and reproduced both 3,969,044-byte PCM24 outputs within one integer LSB. The
current worker was 6,790 bytes and executed through its verified descriptor.

This closes only the earlier “process-image canary is not bound to the model
worker” gap. CDHash is signed code-directory identity, not a claim that every
measured executable byte or dynamically loaded native library was the byte
executed. Post-observation image mutability, complete native loaded-image
closure and the wider outer-supervisor/signal-state gate remain open. The later
model-free executable-region canary proves that a stable parent-owned snapshot
is possible, but it is not attached to this model run and does not enumerate
dyld shared-cache constituents. No MIDI, review, source graph, Simple, Studio,
product or publication state changed.

The development-only command is:

```bash
PYTHONPATH=src .venv-ai/bin/python \
  scripts/private-melroformer-authorised-worker.py \
  --repository-root /absolute/path/to/Sunofriend \
  --runtime /absolute/path/to/Sunofriend/.venv-ai/bin/python \
  --source-root /absolute/private/cache/mlx-audio-source \
  --checkpoint /absolute/private/cache/model.safetensors \
  --companion-root /absolute/private/cache/checkpoint-directory \
  --authorised-excerpt /absolute/private/authorised-separation-excerpt.json \
  --authorisation-report-sha256 <exact-report-sha256> \
  --staging-directory /absolute/fresh/private-output \
  --bind-python-import-closure \
  --observe-outbound-attempts \
  --device gpu
```

Three unchanged downstream production vocal-MIDI observations are complete.
For `Be Alone`, the production pYIN dominant-contour path, lead role, phrase
repair, 136 BPM and A=440 Hz produced 14 notes from the quarantined Kim Vocal
2 output. At a 40 ms onset tolerance its exact-pitch/onset F1 against the
existing estimated controls was 0.600 for Moises, 0.560 for Suno A, 0.519 for
local HTDemucs and 0.462 for Suno B. The inactive report is self-hashed as
`e2ae906d872d55369d4dc658e63669b63e6a310f0498e0a000991db7facb3a0c`;
the candidate MIDI is bound as
`65111b1dadbc9daaa7ea015a542a256510bd1b8f3ecbb88a36f55dc63dd5dcc1`.

The identical sealed-settings contract was then repeated on `I am a Alien
mashup`, original seconds 219–234, at its own authorised 114 BPM and A=440 Hz.
Kim Vocal 2 produced 23 notes. Exact-pitch/onset F1 was 0.913 against Moises,
0.889 against local HTDemucs, 0.844 against Suno A and 0.773 against Suno B.
Its inactive report is self-hashed as
`36599d2b139320ea4d48a0805630ca5e7acf619746aec39fbfcd77cca7098f18`;
the candidate MIDI is bound as
`776a07c43bdddbde585736e039f202ab8df13ed50d54750e6e83969aa39747e5`.
These controls are not score truth, and all values are agreement measurements
rather than rankings.

The third observation used the independently authorised `Mauvais djo - Pilé`
33–48 second window and the two controls present in its sealed comparison:
local HTDemucs and Moises. The evaluator now accepts two to four known control
packs in canonical order, requires local HTDemucs plus at least one provider,
and still rejects unknown or single-control sets. Local HTDemucs, Moises and
Kim Vocal 2 each produced zero primary notes on this window, and Kim produced
no polyphonic register hypothesis. This is a cross-song failure observation,
not an agreement score or evidence of silence.

The follow-up leaf evaluation explains where usable evidence was lost. It ran
both unchanged production vocal adapters on each of the two Moises leaves;
provider filenames were retained for review but did not select an adapter.
The complete Basic Pitch runtime was required rather than silently accepting
an environment-degraded pYIN fallback. The leaf named backing vocals produced
25 notes through the backing adapter and zero through the lead adapter. The
leaf named vocals produced 23 backing-adapter notes and 15 lead-adapter notes.
Thus the same Moises pack has a zero-note broad vocal sum while each separate
vocal leaf has a non-empty primary candidate. This does not prove every note
or provider label correct, but it does show that summing lead and backing
before transcription can discard usable melody evidence on this window.

All 52 MIDI/note/render artifacts remain inactive in
`work/separation-bakeoff/mauvais-djo-pile-vocal-leaves-33-48-v4`. The report's
canonical document SHA-256 is
`f323c020690de4cac0f00594dd6eb6f25b69a47e6195a726f640961205dd87ed`;
the owner-only report file hashes to
`102a1bdaefe3130228a4f75144ac0f915a370b2bd06b742da8cd8e004660ccb1`.
The next separator design must preserve separately auditionable lead/backing
candidate leaves when available; it must not force them into one broad vocal
source before MIDI conversion.

That observation has now been repeated on two disjoint authorised excerpts.
On `I am a Alien mashup`, all three provider packs retained non-empty broad
vocal MIDI, and all six separate provider leaves produced a non-empty primary
candidate through at least one unchanged adapter. Primary counts ranged from
3 to 30 notes; the largest count did not establish correctness or identify a
singer. On `Be Alone`, every broad vocal control was also non-empty. Four of
six leaves produced candidates, while the two additional Suno leaves produced
zero notes through both adapters. The useful cross-song result is therefore
narrow: preserving leaves prevents a demonstrated loss on `Pilé`, but leaf
separation alone neither guarantees a complete melody nor defines a safe
lead/backing rule. Production tracker thresholds remain unchanged.

The `I am a Alien mashup` leaf report contains 170 inactive artifacts. Its
canonical document SHA-256 is
`1ed12395799ae28bc70ab04ba6895a05ab2eb0d175dcda48e0d108ba7d880b3d`
and its report file hashes to
`885b5cd5ee2d1f35d553d37849ec6f9dfc52209304b8bccee2d6bcd6f6e0c9c1`.
The `Be Alone` report contains 136 inactive artifacts. Its canonical document
SHA-256 is
`c1b2c1d3cff8278494eff52bd418e627fd0171b97d24d2b3a896147d4b951509`
and its report file hashes to
`ec62d7ab576c1a83cc02cdd8fc88f75fd8914887b6c4b6aebb5c8def79214835`.
The evaluator accepts the exact historical v1 and current v2 Kim downstream
MIDI schemas so already-sealed evidence need not be regenerated; every other
schema remains rejected.

Reproduce this private diagnostic with the full audio environment, not the
minimal model environment:

```bash
PYTHONPATH=src .venv/bin/python \
  scripts/private-authorised-vocal-leaf-midi-evaluation.py \
  --role-mapping /absolute/private/authorised-role-mapping.json \
  --control-comparison /absolute/private/authorised-midi-comparison.json \
  --melroformer-evaluation /absolute/private/private-melroformer-vocal-midi-evaluation.json \
  --out /absolute/fresh/private-vocal-leaf-evaluation
```

The command changes no source audio, active candidate, source graph, Simple or
Studio route. It fails if Basic Pitch is unavailable, writes only to a fresh
owner-only output, and makes no winner or singer-identity claim.

Equal-level blind Kim-Vocal-2-versus-Moises MIDI reviews were prepared for both
songs with each original mixed excerpt as the source, identical General MIDI
program and SoundFont for both candidates, explicit zero alignment and a
0–15 second window. Their audio-manifest SHA-256 values are
`11a05fad5752c44025c018603ed4c21dd9003f7a201118ab0a716d95dadb794c`
and
`dab62596f47a13f05a10a96db1e06b8ab39c98b43899f5978b52ad32348655d8`.
The completed `Be Alone` review resolved to `equivalent`; its reviewed export
SHA-256 is
`8146d04d963b2bd2405a665915bf849e4b75158d591006d2f20237f3ec99d96c`.
The completed `I am a Alien mashup` review export hashes to
`b289ec5d097aea43d4fae22f1a0a6f29069e9ee788f61a58e55d5516d752b167`;
its verified result hashes to
`62320a755caa1057da3be16210398db3ed3fdf8496ac0fed1dbeb7574368e83e`
and resolved to `neither`. The user heard a male lead and female backing vocal
in the source, while both candidate MIDIs mainly captured the female backing.
The developer has not opened either MIDI answer key manually. Cross-song
downstream MIDI, exact weight-conversion parity and human review are complete,
but lead-versus-backing assignment quality, remaining runtime/provider
execution safety and every public route remain blocked.

The completed bounded experiment kept the unchanged 23-note primary candidate
and added four audition-only hypotheses from the existing polyphonic vocal path:
lowest line (16 notes), dominant line (28), top line (22) and the complete
harmony stack (80). Their exact inactive evaluation is retained at
`work/separation-bakeoff/i-am-a-alien-kim-vocal-register-hypotheses-219-234-v1`.
No register is called a singer identity: a lane may switch singer or harmony
inside the excerpt, and low pitch does not by itself establish the male lead.
The control comparisons remain estimated-reference agreement only.

The subsequent one-unit blind primary-versus-lowest review was corrected after
the listener recognised that its stated focus was specifically the male lead.
The final browser export preferred anonymous candidate B and noted that it was
useful for the male lead. Resolver-only disclosure identified B as the 16-note
lowest-register hypothesis and A as the unchanged 23-note primary contour.
The corrected export hashes to
`ced9ec0a6a7475deebe9c9bb27d2cc38deb58b314e74440084d0bed661159859`;
the corrected resolved evidence file hashes to
`ac7be09e2a9589ad1dde9661fab01e3fee305a4def8d1a5c29cbdd3e7d666eea`.
Earlier exports made before the listening focus was understood are superseded
and are not the final result. This supports retaining a lowest-register
hypothesis for audition on this excerpt, not a universal singer-identity or
automatic-selection rule. No default, MIDI, selection or promotion changed.

The next inactive diagnostic now measures **time activity only** against four
distinct provider groups. Each group receives at most one vote: its broad
vocal primary and every separately preserved leaf primary are unioned before
voting. A consensus interval requires activity from at least two groups. This
does not claim that the groups are statistically independent, that their pitch
is correct or that agreement is score truth. On the same 15-second `I am a
Alien mashup` excerpt, the provider consensus contains 8.206970 seconds across
24 intervals and five phrase groups. The unchanged 23-note primary covers
4.473693 seconds (54.51%) across three phrases; 97.31% of its own activity lies
inside the consensus. The 16-note lowest line covers 1.615071 seconds (19.68%)
across two phrases. Importantly, it contributes 1.533801 seconds in seven
reportable spans that the primary misses, while the primary contributes
4.392423 seconds that the lowest line misses. Together they still omit
2.199476 seconds of consensus activity.

That result agrees with the corrected listening observation in a narrow way:
the lower line contains complementary male-lead evidence, but it is not a
replacement for the broader primary contour. The diagnostic creates no MIDI,
audio, review, merge, ranking or selection. Its canonical document SHA-256 is
`34507e2650c038baf8cbbecb0e870eff570969d5f1015c96749e58c45e6849df`;
the report file hashes to
`a01a974538699e5c5f011cfaad7d76d7224767d0fc92a7935f307aa38f479410`.
Reproduce it only from the three exact private evidence reports and a fresh
owner-only output directory:

```bash
PYTHONPATH=src .venv/bin/python \
  scripts/private-vocal-phrase-completeness.py \
  --control-comparison /absolute/private/authorised-midi-comparison.json \
  --melroformer-evaluation /absolute/private/private-melroformer-vocal-midi-evaluation.json \
  --vocal-leaf-evaluation /absolute/private/authorised-vocal-leaf-midi-evaluation.json \
  --out /absolute/fresh/private-vocal-phrase-completeness
```

The song-disjoint repeat is now complete on `Be Alone`. To preserve exact
cross-binding, its downstream MIDI was regenerated from the latest already
sealed Kim worker output; separation and model inference were not rerun. The
unchanged primary again contains 14 notes. The new report also retains 2
lowest-line, 17 dominant-line, 1 top-line and 20 harmony-stack notes. Its
primary note sequence is identical and its MIDI is byte-identical to the
earlier 14-note observation; the note-evidence envelope differs because it
correctly binds the newer sealed vocal-output SHA-256. Its
canonical document SHA-256 is
`a450d866490c66c822949668956e6454b7d9685621173b550a24e171609f66d1`;
the report file hashes to
`1e072a15afd7898112b88c44a21353293f3ab33cfbcb366f4c596ec8528e4695`.
The six provider vocal leaves were then re-evaluated unchanged against that
exact MIDI report. Its canonical document SHA-256 is
`e2896f70e1e641d27f25a936f4bec67076cab35797bb4e7cdcfcd5f541443489`;
the report file hashes to
`b212bc85031a9088c9a77daa4780c4681e287e9a7f24be61490ab3f70a8ed90b`.

The `Be Alone` provider consensus contains 5.980367 seconds across 15
intervals and six phrase groups. The 14-note primary covers 3.360474 seconds
(56.19%) across three phrases, with 97.79% of its own activity inside the
consensus. The two-note lowest line covers only 0.197370 seconds and adds just
0.099299 seconds in one reportable span beyond the primary. The primary adds
3.262404 seconds beyond the lowest line, and together they still omit
2.520594 seconds. This is materially different from the 1.533801-second lower-
line contribution on `I am a Alien mashup`: a useful lower-register line does
not generalise across these songs. The diagnostic's canonical document
SHA-256 is
`a8af9952a11cba24aef43463c58877ed7d9ad0727c3ca271a742c3419d458551`;
the report file hashes to
`1dba6c352bf13166fe7aeae259ec61f477da14f2449c1bbc57bbdfe69ed110a2`.
No focused review is warranted from activity coverage alone, and no merge,
register rule, singer identity, default or product route changed.

The next preservation increment turns those sealed alternatives into one
path-free, self-hashed **candidate inventory** per excerpt. It deliberately
copies no MIDI, note JSON or audio. Every entry retains only its stable musical
hypothesis and verified byte/hash identities, including zero-note observations.
The inventory contains the unchanged Kim primary, all four Kim register
hypotheses and both unchanged lead/backing primary adapters for each of the six
provider vocal leaves: 17 candidates in total. `I am a Alien mashup` has 16
auditionable candidates and one `no_note_evidence` entry; `Be Alone` has 13 and
four respectively. Both inventories retain four Moises, four Suno A and four
Suno B leaf candidates.

The `I am a Alien mashup` inventory's canonical document SHA-256 is
`01779801b7ac3be0a922d525a8cf8b082b240b784279631339c8b0926863d2e4`;
the report file hashes to
`947559a94f22bf3e1c80ce3b015da671ccdf5599bac322c0dfe5806ade72dea1`.
The `Be Alone` inventory's canonical document SHA-256 is
`0b8b026652f7a5b2dea078dc7e8a008e45dcb7a83cc6bc0b671d3e4096e174f4`;
the report file hashes to
`89a25dea76fb9f26b7bb376b59f626b702614db2915b00096714a30804b94e0b`.
Both output directories and reports are owner-only. The builder reopens and
hashes every referenced candidate artifact, validates all three reports'
self-hashes and exact cross-bindings, and refuses an existing destination.

```bash
PYTHONPATH=src .venv/bin/python \
  scripts/private-vocal-candidate-set.py \
  --melroformer-evaluation /absolute/private/private-melroformer-vocal-midi-evaluation.json \
  --vocal-leaf-evaluation /absolute/private/authorised-vocal-leaf-midi-evaluation.json \
  --phrase-completeness /absolute/private/vocal-phrase-completeness.json \
  --out /absolute/fresh/private-vocal-candidate-set
```

The separate private loopback audition now resolves that path-free inventory
back to its already sealed evidence without copying audio or MIDI. It rechecks
the exact inventory, MelRoFormer, vocal-leaf, phrase-completeness and authorised
excerpt reports; opens every WAV through a no-follow descriptor walk; hashes it
before serving; and exposes only opaque per-launch media capabilities on
`127.0.0.1`. Kim hypotheses are heard beside the exact mixed excerpt. Provider
leaf hypotheses are heard beside the exact corresponding vocal leaf. The
candidate is always a dry neutral MIDI render, so the page explicitly asks for
melody/phrase usefulness rather than final instrument tone.

Playback, seeking, looping and dwell time stay in the browser and write
nothing. A review is valid only after the listener explicitly confirms hearing
both reference and candidate and chooses **useful for this focus**, **not useful
for this focus** or **cannot tell** for every playable candidate. Several
candidates may be useful. Zero-note candidates stay visible but cannot be
turned into choices. Browser export is the only review write, and the separate
verifier requires the exact focus and complete sealed input chain before it
publishes a fresh owner-only, path-free resolution.

```bash
PYTHONPATH=src .venv/bin/python \
  scripts/private-vocal-candidate-audition.py \
  --candidate-set /absolute/private/vocal-candidate-set.json \
  --melroformer-evaluation /absolute/private/private-melroformer-vocal-midi-evaluation.json \
  --vocal-leaf-evaluation /absolute/private/authorised-vocal-leaf-midi-evaluation.json \
  --phrase-completeness /absolute/private/vocal-phrase-completeness.json \
  --authorised-excerpt /absolute/private/authorised-separation-excerpt.json \
  --focus "Which candidates follow the intended lead-vocal melody?" \
  --open

PYTHONPATH=src .venv/bin/python \
  scripts/private-vocal-candidate-audition.py \
  --candidate-set /absolute/private/vocal-candidate-set.json \
  --melroformer-evaluation /absolute/private/private-melroformer-vocal-midi-evaluation.json \
  --vocal-leaf-evaluation /absolute/private/authorised-vocal-leaf-midi-evaluation.json \
  --phrase-completeness /absolute/private/vocal-phrase-completeness.json \
  --authorised-excerpt /absolute/private/authorised-separation-excerpt.json \
  --focus "Which candidates follow the intended lead-vocal melody?" \
  --review /absolute/downloads/vocal_candidate_review.reviewed.json \
  --out /absolute/fresh/private-vocal-candidate-review-resolution.json
```

This private adapter creates no ranking, winner, merge, repair, singer
identity, default, Studio import, Simple result or source-graph change. A
verified `useful` disposition is evidence for the exact written focus, not
permission to promote or activate that candidate.

Public Studio finished-song separation remains Phase S4. One-action Simple
separation remains Phase S6 and requires cross-song, licence, offline,
resource, downstream-MIDI and human listening acceptance.

### Current private human-review queue

As of 2 August 2026, there is no outstanding prepared private review. The new
loopback tool is available, but no listening focus has been opened as a current
acceptance gate. The
corrected primary-versus-lowest review preferred the lowest-register
hypothesis for the male lead; its answer key was opened only by the resolver
after the complete matching browser export was found.
The FP32/BF16 precision review and `Be Alone` Kim-versus-Moises MIDI review both
resolved to `equivalent`; the earlier `I am a Alien mashup` comparison resolved
to `neither`. The user also confirmed
listening to the current `Be Alone` six-source diagnostic page. That page is a
static evidence browser with no export form, so no further action is required
from it. Historical `be-alone-midi-listening-screen-v1` and earlier
six-source-v1 pages are superseded diagnostics, not current acceptance gates.
