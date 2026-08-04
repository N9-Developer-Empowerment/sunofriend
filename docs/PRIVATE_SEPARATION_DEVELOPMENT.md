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
accepted Kim checkpoint and authorised audio were not opened.

A fixed real native adapter is now implemented in source. Its tiny bootstrap
hardens fd3–fd7 before importing project code and derives the package root from
its parent-bound script location rather than request data. Its core validates
fd3, binds the fixed worker/source/companion identities, passes only fd5 to the
descriptor-native checkpoint loader, retains the existing fd6/fd7 observation
gate, confines quarantine and a private path-bearing Python-closure claim to
the staging tree, and emits a path-free fd4 result with every product authority
false. Synthetic dependency-substituted tests exercise that wiring; no model,
checkpoint or audio was opened. A fixed parent staging verifier now validates
the real child contract and fd5-only checkpoint claim, reopens the authorised
source, both PCM24 outputs, the private Python-closure claim and every claimed
module, and repeats the mutable checks before emitting path-free evidence. It
does not attach the three opaque-owner observers, supervise the process or
remeasure the checkpoint lease. The real worker adapter has therefore still
not been launched, the active Kim path remains subprocess-based and no product
route is enabled.

The corresponding parent lifecycle order is now executable only through an
explicit dependency-substituted exercise. It requires the exact opaque owner,
runs owner-bound observation/release before synchronous supervision, accepts
only normal zero exit with complete group drain and exact reap, decodes the fd4
result against its fd3 request, requires independent path-free staging
verification and consumes the private PID/PGID only through the owner's boolean
matcher. Invalid observer evidence still runs terminal supervision before the
exercise fails. This proves orchestration and cleanup behavior only: all
operations are injected, no native extension/process/checkpoint/model/audio or
staging path is opened and every product permission remains false. A later
fixed model-free macOS adapter now owns that concrete observer, fd4, supervisor,
exact-reap, mapped-file and staging order for the stdlib bootstrap. It rejects
checkpoint-sized fd5 inputs and is not the real Kim coordinator.

The next private prerequisite now exists and has one live static canary. An
opaque Kim session wraps a freshly built verified launcher, binds and remeasures
the fixed real-worker script, Python runtime and `/usr/bin/sandbox-exec`, and
retains the exact native spawn method plus nonconstructible owner type only in
private registry state. A separate opaque admission binds that exact session to
the canonical request hash, nonce, repository and worker SHA, permits only one
outstanding admission and is single-use. The trusted-local canary built and
imported the native extension and rechecked all static bindings; it did not call
the spawn method or open a checkpoint, model, source, audio or staging tree.
A guarded fd3–fd7 start boundary and lease-to-start bridge now consume the
admission immediately around the sole native spawn call while retaining fd5
with the lease owner. The session now also has a one-use terminal transition:
only the exact retained owner with normal zero exit, group drain, released
ownership and exact reap may move it from running to terminal, after another
session-binding remeasurement. A separate transition now clears a failed but
fully group-drained and exactly reaped exact owner without making an execution-
success claim.

The fixed real coordinator is now implemented as private source. It composes
that measured session and live lease-to-start bridge with the ready/release,
network, process-image and executable-region observers; bounded fd4 drain;
whole-group supervision and exact reap; real staging verification; post-run
checkpoint remeasurement; opaque owner identity consumption; and fd5/session/
lease terminalization. Dependency-substituted success and pre-release failure
tests prove the fixed order and cleanup only. They did not start the native
worker or open a checkpoint, model, source, audio or staging tree.

The session now binds the exact virtual-environment launcher separately from
its resolved process image and base-runtime root, and the coordinator emits
disjoint path-free receipts for a proved no-child outcome versus a started,
completely drained and exactly reaped owner. A private one-shot transport owner
now supplies the exact fd3 request file and paired fd4 writer/reader around
that coordinator. It uses a separate fresh owner-only transport directory,
removes it after success or failure and never deletes the output staging tree.
The wrapper's tests substitute the coordinator, so no checkpoint, model, audio
or native process was opened. A dedicated private Kim checkpoint lease now
binds the canonical native request, author-hosted upstream evidence, an
owner-only non-inheritable descriptor and the existing descriptor-pinned
Safetensors inspection. Its trusted-local static check rehashed and rechecked
the exact 456,483,463-byte approved checkpoint without reading tensor values,
importing the model or touching audio. This deliberately does not reuse the
general separator lease, whose authority depends on a genuine public bake-off
acceptance corpus. A single-use private fd5 reservation now retains that exact
observation and request under the lease lock, remeasures immediately before
handoff, and passes the raw descriptor only into an admission issued by the
verified native session. The fixed coordinator and one-shot wrapper use this
private boundary directly and no longer accept the general worker-V2 record.
The full one-run authority chain described next composes these parts. None of
this changes the active subprocess route or enables a product route.

That private chain has now run successfully end to end. A developer-only
attempt owner measures the exact worker, source, companions and authorisation
report, creates a fresh owner-only attempt tree, opens the verified native
session, acquires/reserves the dedicated Kim descriptor lease and invokes the
one-shot coordinator. The clean `Be Alone` repeat is under
`work/separation-bakeoff/be-alone-kim-fixed-native-v2/`. Its owner-only canonical
receipt self-verifies as
`950a20550278985381a32df9eb44c37e2b79204652be1fc739d2f306aa3535f7`
and records successful ready/release, live observers, exact group reap,
post-run staging/checkpoint remeasurement, fd5 release, lease close and native
session terminalisation. Both 15-second outputs are 44.1 kHz stereo PCM24 and
their integer sum differs from the authorised input by at most one LSB. This is
working private execution provenance, not listening acceptance, source-graph
activation, automatic selection or a public separator.

The attempt owner now also persists `native-attempt-evidence.json`. This
path-free, self-hashed document binds the canonical request, terminal receipt,
checkpoint, authorisation, worker/source/companion identities and exact hash,
size and geometry of both fixed-location PCM24 outputs. Its evidence self-hash
is `ef418783b15c9a64f188b5f7be9b0612ba491c537c3e2b669021b073f48b6d8c`;
the evidence file hashes to
`9497d0af8b626c1a3ce043be831e25714de1b20216d91fa8ef54e01acc2f3669`.
It explicitly records that listening quality is not established and grants no
selection, source-graph, Simple, Studio, product or publication permission.

The unchanged private vocal-MIDI evaluator now accepts that stricter native
evidence as an alternative to the legacy worker observation, reopens and
remeasures both outputs before and after transcription, and normalises only the
existing provenance fields. On the same `Be Alone` excerpt it produced the
same 14-note primary and the same 2/17/1/20-note lowest/dominant/top/harmony
hypotheses. The primary MIDI SHA-256 is
`65111b1dadbc9daaa7ea015a542a256510bd1b8f3ecbb88a36f55dc63dd5dcc1`,
byte-identical to both earlier Kim evaluations. The new evaluation's canonical
document SHA-256 is
`b901a672c65276cf09514d05056cc912555df241693f1cde864bca4d7cea042a`;
the report file hashes to
`28b60fbe3166feb24f2edd1adb1a1388cd5d4091b4ef104e0230bf5ddeaa58a0`.
No duplicate blind review is required because the audition MIDI is unchanged;
the existing `Be Alone` Kim-versus-Moises review already resolved this MIDI as
`equivalent`. This proves downstream parity for the exact excerpt, not score
truth or separator acceptance.

A separate coarse timing receipt is now part of each successful fresh attempt.
It uses `time.monotonic`, records elapsed durations rather than timestamps and
contains no path, PID, process identity or wall-clock field. The first timed
v3 repeat completed through output evidence in 11.868113 seconds. The native
one-shot was the longest stage at 10.270401 seconds; session opening took
1.175781 seconds, checkpoint lease acquisition 0.208044 seconds, fd5
reservation 0.190611 seconds, input measurement 0.017047 seconds and every
remaining persistence/tree stage under 0.005 seconds. The receipt self-hashes
to `78ff396e17c7b8ea363cdebd3c9a66757129c1df4216e506efbce47020ebf3bd`.
This is one coarse runtime observation, not a benchmark: the one-shot still
combines transport, spawn, model load/inference, observers, staging checks and
terminal cleanup. The v3 stems differ from v2 by at most one PCM24 LSB, but the
unchanged downstream evaluator again produced byte-identical primary MIDI
`65111b1dadbc9daaa7ea015a542a256510bd1b8f3ecbb88a36f55dc63dd5dcc1`.
Broader cross-song execution and listening remain before any integration
decision.

That cross-song execution repeat is now complete on the already authorised
`I am a Alien mashup` 219–234-second excerpt. The exact same native chain
completed through output evidence in 11.299359 seconds: 9.671387 seconds in
the coarse one-shot and 1.205779 seconds opening the session, with all other
outer stages below 0.21 seconds. Timing self-hash:
`96ffa4e7637ee91c0993c54f110866c4d6a8992eb5263f7c0564792cf8907334`.
The unchanged 114 BPM downstream evaluator produced 23 primary notes and MIDI
SHA-256
`776a07c43bdddbde585736e039f202ab8df13ed50d54750e6e83969aa39747e5`,
byte-identical to both earlier Kim evaluations of that song. Exact-pitch/onset
F1 was 0.8889 against local HTDemucs, 0.9130 against Moises, 0.8444 against
Suno A and 0.7727 against Suno B. Those comparisons show reproducible relative
agreement, not score truth.

The existing blind review already heard this exact MIDI and resolved it to
`neither`: both anonymous candidates followed the female backing vocal rather
than the intended male lead in the mixed reference. No duplicate review is
needed. The cross-song result therefore clears execution-to-MIDI reproducibility
but confirms that voice/line assignment remains a musical-quality blocker.
Do not activate Kim, infer singer identity or expose a product route from these
engineering results.

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

The same private adapter can narrow one review to an explicit 0.5–15 second
window and explicit candidate subset. Use paired `--start-seconds` and
`--end-seconds` plus repeated `--candidate` values. The page loops only the
stated window and reports both the notes that overlap that window and the
candidate's complete-excerpt note count. A candidate that is non-empty across
the complete excerpt but has no overlapping notes is shown as unavailable for
that scope. Its complete evidence remains preserved; it is not offered as a
silent listening choice or treated as rejected.
Candidates outside the scope remain sealed in the inventory: omission is not a
rejection, ranking, choice or singer assignment. Resolution must use the same
window and candidate IDs, so a browser export cannot silently expand, shrink
or swap its question.

```bash
PYTHONPATH=src .venv/bin/python \
  scripts/private-vocal-candidate-audition.py \
  --candidate-set /absolute/private/vocal-candidate-set.json \
  --melroformer-evaluation /absolute/private/private-melroformer-vocal-midi-evaluation.json \
  --vocal-leaf-evaluation /absolute/private/authorised-vocal-leaf-midi-evaluation.json \
  --phrase-completeness /absolute/private/vocal-phrase-completeness.json \
  --authorised-excerpt /absolute/private/authorised-separation-excerpt.json \
  --focus "Which candidate follows the intended lead in this phrase?" \
  --start-seconds 3.45 \
  --end-seconds 6.85 \
  --candidate kim/primary \
  --candidate kim/register/lowest-line \
  --open
```

Public Studio finished-song separation remains Phase S4. One-action Simple
separation remains Phase S6 and requires cross-song, licence, offline,
resource, downstream-MIDI and human listening acceptance.

### Cross-song evidence catalogue

The owner-only `scripts/private-separation-evidence-index.py` command builds a
fresh, path-free integrity index from already sealed private reports. Each
`--evidence` value supplies a caller-declared track ID, method-family ID,
finite evidence kind and report. The current catalogue covers the synthetic
Demucs separator/audio and downstream-MIDI reports plus provider-reference and
Kim Vocal 2 MIDI reports for `Be Alone` and `I am a Alien mashup`:

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-evidence-index.py \
  --evidence synthetic-demo demucs separator_audio /absolute/synthetic-audio.json \
  --evidence synthetic-demo demucs downstream_midi /absolute/synthetic-midi.json \
  --evidence be-alone provider-reference provider_midi /absolute/be-alone-provider.json \
  --evidence i-am-a-alien provider-reference provider_midi /absolute/alien-provider.json \
  --evidence be-alone kim-vocal-2 vocal_midi /absolute/be-alone-kim.json \
  --evidence i-am-a-alien kim-vocal-2 vocal_midi /absolute/alien-kim.json \
  --out /absolute/fresh/private-cross-song-separation-evidence-index.json
```

The current six-entry document has SHA-256
`4368c30a78feabdf37674239bce7168292e63a4ed03bbc4268c87accaa66949e`.
It verifies source file hashes, source document self-hashes, private scope and
inactive permissions. It copies no audio, MIDI, report bodies or filesystem
paths. It does not normalize unlike metrics, compare methods, rank a backend,
evaluate cross-song acceptance, resolve licensing, or enable Simple/Studio.
The broader bake-off-corpus publication gate therefore remains open.

The follow-on owner-only coverage command verifies that exact index and
reports its comparison topology without opening any of the six source report
bodies:

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-corpus-coverage.py \
  /absolute/private-cross-song-separation-evidence-index.json \
  --out /absolute/fresh/private-separation-corpus-coverage.json
```

The current coverage document has SHA-256
`f40eea3eb661d0d42ddca739efdd850a153e1884e7cc107f89fe8ff3997f88f1`.
It finds four schema/kind groups. Provider MIDI and Kim vocal MIDI each repeat
one method family across two songs. Synthetic separator audio and downstream
MIDI each have only one song/method cell. There is no same-schema cross-method
pair and no complete two-song-by-two-method rectangle. Even a future complete
rectangle remains topology only: this command always keeps metric comparison
false until a separate normalized metric and acceptance contract exists.

The report also makes its boundary explicit. The index does not represent a
hidden test set and cannot evaluate checkpoint licensing, human listening,
offline operation or resource acceptance. Those facts do not erase the human
reviews already documented below; they mean this particular machine-readable
index cannot be used as evidence for those gates.

### Source-bound cross-song MIDI agreement

The owner-only
`scripts/private-separation-normalized-midi-agreement.py` command closes the
smallest metric-contract gap without turning a relative control into truth. A
comparison supplies four sealed reports for each song: the candidate MIDI
evaluation, its exact authorised MIDI control, the role mapping behind that
control and the original authorised excerpt. The command also requires the
candidate and provider-reference topology cells to exist in the sealed index.

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-normalized-midi-agreement.py \
  /absolute/private-cross-song-separation-evidence-index.json \
  --candidate-method kim-vocal-2 \
  --control-method provider-reference \
  --control-id moises \
  --comparison be-alone \
    /absolute/be-alone/private-melroformer-vocal-midi-evaluation.json \
    /absolute/be-alone/authorised-midi-comparison.json \
    /absolute/be-alone/authorised-role-mapping.json \
    /absolute/be-alone/authorised-separation-excerpt.json \
  --comparison i-am-a-alien \
    /absolute/alien/private-melroformer-vocal-midi-evaluation.json \
    /absolute/alien/authorised-midi-comparison.json \
    /absolute/alien/authorised-role-mapping.json \
    /absolute/alien/authorised-separation-excerpt.json \
  --out /absolute/fresh/private-separation-normalized-midi-agreement.json
```

The current two-song report has file SHA-256
`376183b91dd266ca6a6a1d9c30a9176ded21d0964753520859dde974cc05f591`
and document SHA-256
`bc901038f6ee1f40b99d518c59294efc12d38484e59be4bc85d05a15237b0095`.
It proves one same-excerpt chain per song and recomputes the unchanged
`sunofriend.private-demucs-midi-note-metrics.v1` comparison at 40 ms. The
`Be Alone` Kim/Moises cell has exact-pitch/onset F1 `0.6`; the `I am a Alien`
cell has exact-pitch/onset F1 `0.913043478`. These are descriptive agreement
values only. The higher second value does not override the completed human
review that both candidates followed the wrong vocal line for that question.

The report is path-free, creates no audio or MIDI, ranks no method and keeps
the publication gate open. Provider MIDI remains estimated rather than score
truth, human line identity is not a normalized metric, the corpus is not a
hidden test set, and licensing, offline and resource acceptance remain
separate gates.

### Source-bound human-listening coverage

The next owner-only projection binds completed phrase reviews to the exact
authorised excerpt identities in that normalized agreement report. It accepts
only completed focus-relative review resolutions that separately classify the
heard source line and the candidate MIDI's usefulness. It copies neither
free-text notes nor filesystem paths:

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-human-listening-coverage.py \
  /absolute/private-separation-normalized-midi-agreement.json \
  --review i-am-a-alien /absolute/earlier/private-vocal-candidate-review-resolution.json \
  --review i-am-a-alien /absolute/later/private-vocal-candidate-review-resolution.json \
  --out /absolute/fresh/private-separation-human-listening-coverage.json
```

The current report has file SHA-256
`028502c0fb4d5adaa46bb02042e48c77d39d4f311930a22bad5b1f2786240ff1`
and document SHA-256
`04b41f5fa71407802aa6f227082ee760815b1f723f5f58ba08b5f0d35746a7fd`.
It binds both role-correct `I am a Alien mashup` windows and the complete
15-second `Be Alone` excerpt to their matching song cells. The projection now
covers three structured windows, 16 candidate auditions and nine exact-focus
usefulness results across both normalized songs. Cross-song human-listening
coverage is complete for this bounded two-song corpus.

This clears the cross-song listening-coverage item without reinterpreting any
useful disposition as a winner, complete transcription, score truth or global
method judgement. Full-excerpt or full-song listening beyond this bounded
corpus, a hidden test set, checkpoint licensing, offline behaviour and resource
acceptance remain open publication gates.

### Publication-readiness ledger

The owner-only `scripts/private-separation-publication-readiness.py` command
now gives those distributed findings one fail-closed, path-free status report:

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-publication-readiness.py \
  work/separation-bakeoff/cross-song-normalized-midi-agreement-v1/private-separation-normalized-midi-agreement.json \
  work/separation-bakeoff/cross-song-human-listening-coverage-v6/private-separation-human-listening-coverage.json \
  --separated-audio-quality \
    work/separation-bakeoff/cross-song-separated-audio-quality-result-v1/private-separated-audio-quality-result.json \
  --resource-benchmark-result \
    work/separation-bakeoff/be-alone-full-song-kim-resource-benchmark-result-v1.json \
  --full-song-review-result \
    work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-review-result-v1/private-separation-full-song-review-result.json \
  --full-song-alignment-result \
    work/separation-bakeoff/be-alone-full-song-source-reconstruction-alignment-v1/private-separation-full-song-alignment.json \
  --full-song-join-remediation-review-result \
    work/separation-bakeoff/be-alone-full-song-join-remediation-review-result-v4/private-separation-full-song-join-remediation-review-result.json \
  --out \
    work/separation-bakeoff/separation-publication-readiness-v12/private-separation-publication-readiness.json
```

The verified v12 report has file SHA-256
`f8148f7cc41b830ec9d48d4f4189764e782d784f74b023fcf55f532ecc597285`
and document SHA-256
`1d2b16100652e5fd2529695d27f32626b8b11eb36ecba19fce270547382e7dc9`.
The ledger records three passed bounded-evidence
milestones: source-bound cross-song downstream MIDI, source-bound cross-song
human listening and a separate
structured phrase-completeness judgement for every supplied window.
Each input report is parsed and hashed from one bounded, non-followed file
descriptor snapshot, then rechecked before publication. A newly created result
directory is mode `0700`; the ledger is fsynced as mode `0600` and published by
a no-overwrite hard link, so a raced path cannot replace the fresh result.

Eight publication gates remain explicitly open: cross-song separated-audio
quality, full-song duration/alignment, broad role coverage, a hidden
song-disjoint test set, checkpoint usage/distribution terms, offline execution,
the full-song resource envelope and a public CLI/TUI/Simple/Studio route. The
report therefore says `publication_ready: false` and describes the current
stage as `private_bounded_vocal_research`. It cannot accept a separator from
caller flags, compute a quality percentage, copy listener notes or enable a
product route. Future gates require new typed, hash-bound evidence.

Version 3 retains the Version 2 bounded separated-audio minimum. Every
source-bound Kim Vocal 2 excerpt must be rated `substantially_complete`, with
non-vocal bleed and distracting artefacts each no worse than `noticeable`.
All reviewed songs must pass. The separate A/B preference is deliberately
ignored by this gate, so preferring a provider cannot select or reject Kim.
The current evidence includes the completed two-song result. One of two Kim
excerpts meets the minimum, so the gate remains open.

The optional `--full-song-review-result` input accepts only the self-hashed
resolved v1 result with the exact clock, complete three-role song ratings and
all ordered boundary ratings consistent with its recomputed summary. The
predeclared duration/alignment minimum requires every generated complete-song
role to be rated `useful` and every role at every chunk boundary to be rated
`clean`. Notes are not copied into the ledger and never affect the assessment.
The review alone cannot establish synchronized source-to-output alignment or
accepted drift. The separate typed alignment input below can supply that
narrow evidence, but the duration/alignment milestone closes only when the
matching review minimum and alignment thresholds both pass. It still cannot
accept or select the separator. In the current `Be Alone` result all three complete
outputs were useful, exact duration was verified and all 17 boundaries were
reviewed. Reconstruction had 17 clean boundaries, but vocals had audible joins
at 11 and 12 and the instrumental had audible joins at 11 and 13. The gate
therefore remains open.

The optional `--full-song-alignment-result` input accepts only a self-hashed
report bound to the same stitch, plan, execution and exact clock as the human
review. `scripts/private-separation-full-song-alignment.py` compares the
canonical source with the diagnostic vocals-plus-instrumental reconstruction
in nine early-to-late windows. It uses gain-normalized log spectral-band energy
to search a declared plus/minus 100 ms range. Every window must be active, the
absolute lag and early-to-late lag spread must each be no more than 20 ms, and
every normalized correlation must be at least 0.90. These measurements test
synchronization only. They do not establish vocal or instrumental fidelity,
bleed, artefacts, musical quality or separator accuracy.

The current `Be Alone` alignment report has file SHA-256
`c28a84e3a28f30d3d700dd137707d36ecd2e49480270efb56a4d7bd85f66c955`
and document SHA-256
`d04c15f58cb5365f405bf82432c3c102048d4f9e622f543df253b0d0d98ca738`.
All nine windows were eligible, maximum absolute lag and lag spread were both
0 ms, and the minimum normalized correlation was 1.0. The automated alignment
contract passes. The combined duration/alignment milestone remains open only
because the human review recorded the vocal and instrumental audible joins
above. No separator or product route is enabled.

The optional `--full-song-join-remediation-review-result` input requires a
validated `--full-song-review-result` for the same exact raw stitch. It verifies
that the original audible vocal/instrumental role-boundary set exactly matches
the resolved remediation review units, then adds a separate supplementary
assessment. This is directional
raw-versus-candidate A/B evidence: `candidate_preferred` supports improvement,
while `equivalent` does not prove that an originally audible join became
clean. It does not rewrite the original full-song ratings, change their clean-
boundary counts or close the duration/alignment gate. Listener notes are not
copied.

In the current `Be Alone` remediation result, candidate remediation was
preferred or equivalent for every reviewed question, but the originally
audible boundary 11 vocals join and boundary 13 instrumental join were only
equivalent. Improvement is therefore not evidenced for those two role-boundary
pairs. The supplementary assessment keeps
`original_audible_joins_resolved: false`, leaves the original duration/alignment
assessment unchanged and cannot select, accept, publish or enable a separator.

The optional `--resource-benchmark-result` input accepts only a self-hashed,
complete controlled full-song result with three to ten distinct serial
repetitions, consistent plan/checkpoint/runtime/device/machine bindings and all
required timing, RSS, MLX, physical-footprint, thermal, timeout and OOM fields.
The current three-run 36 GiB development result met every frozen development
ceiling and is recorded in the ledger, including the 3.812089 GiB maximum
Darwin physical footprint. It does **not** close the resource gate: the
separately required 16 GiB acceptance class was not observed. The ledger still
has three passed and eight open gates, and every product/publication permission
remains false. A mixed pass/fail repetition set is valid evidence of a failed
development threshold, not malformed evidence or acceptance.

### Cross-song separated-audio quality review

The next gate now has a dedicated owner-only review contract rather than a
free-text listening note. `scripts/private-separated-audio-quality-review.py`
accepts two or more source-bound cases. Each case must bind one authorised
excerpt, one unchanged Kim Vocal 2 worker result and one provider broad-vocal
control from the exact same window. It copies the mixed source and two
anonymous candidates into a fresh private package, sample-RMS matches only the
candidate pair and asks the listener to rate vocal retention, non-vocal bleed
and distracting artefacts independently before recording a separate overall
preference.

The current package uses the exact 191.00–206.00 second `Be Alone` and
219.00–234.00 second `I am a Alien mashup` evidence chains:

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separated-audio-quality-review.py --create \
  --case be-alone \
    work/separation-bakeoff/be-alone-authorised-191-206-v2/authorised-separation-excerpt.json \
    work/separation-bakeoff/be-alone-kim-fixed-native-v3-timed-midi-191-206-v1/private-melroformer-vocal-midi-evaluation.json \
    work/separation-bakeoff/be-alone-role-mapping-191-206-v1/authorised-role-mapping.json \
    moises \
  --case i-am-a-alien \
    work/separation-bakeoff/i-am-a-alien-authorised-219-234-v1/authorised-separation-excerpt.json \
    work/separation-bakeoff/i-am-a-alien-kim-fixed-native-midi-219-234-v1/private-melroformer-vocal-midi-evaluation.json \
    work/separation-bakeoff/i-am-a-alien-role-mapping-219-234-v1/authorised-role-mapping.json \
    moises \
  --out-dir \
    work/separation-bakeoff/cross-song-separated-audio-quality-review-v1
```

The unreviewed seed SHA-256 is
`2c46910b86177fd01dddb2f09ab0409f0c751291b5291717226730ff7a62f63a`;
the six-file audio manifest SHA-256 is
`9233cdf8c938cadf968c8a824d44d41cd7ebe66f96e2787e1b97a480eedc5011`.
All six files are 15-second, 44.1 kHz, stereo PCM24 and have been re-read and
hash-verified. The review was completed on 4 August 2026. The browser export
SHA-256 is
`977c73edbd657440326d745218733a39c49acee8e4abdd6e73f8e109d41e4f0c`.
Resolution produced file SHA-256
`3a2891a4005b3bc955fc9289f9cda40ae447a9870f9b006965d2a5394fce72c6`
and document SHA-256
`adc2deabd517fc48f77c73cf33d4982e8b023c6f4cb825cdbf8b03b5c9fd8b75`.

The listener rated the Kim and provider vocals partially complete with low
bleed and low artefacts on `Be Alone`; Kim was preferred. On `I am a Alien
mashup`, both were rated substantially complete with noticeable bleed and
noticeable artefacts; Kim was again preferred. These are human judgements, not
score truth. Preference changes no selection or default. Because Kim was only
partially complete on one of the two songs, this does **not** close the
separated-audio quality gate.

For another review package, resolve the completed browser export without
reopening the answer key manually:

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separated-audio-quality-review.py \
  --resolve /absolute/separated-audio-quality.reviewed.json \
  --package-dir \
    work/separation-bakeoff/cross-song-separated-audio-quality-review-v1 \
  --out /absolute/fresh/private-separated-audio-quality-result.json
```

The resolver rejects incomplete ratings, changed audio, changed immutable
review evidence, invalid blind assignments and duplicate answer-key units. A
completed resolution remains `complete_review_no_activation` and now carries
the exact path-free authorised-excerpt, role-mapping and audio-hash binding for
each reviewed song. It cannot select Kim or the provider, change a default,
publish a separator or enable any product route.

After resolution, create a fresh ledger with the optional verified inputs:

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-publication-readiness.py \
  work/separation-bakeoff/cross-song-normalized-midi-agreement-v1/private-separation-normalized-midi-agreement.json \
  work/separation-bakeoff/cross-song-human-listening-coverage-v6/private-separation-human-listening-coverage.json \
  --separated-audio-quality \
    /absolute/fresh/private-separated-audio-quality-result.json \
  --resource-benchmark-result \
    /absolute/private-separation-full-song-resource-benchmark-result.json \
  --full-song-review-result \
    /absolute/private-separation-full-song-review-result.json \
  --full-song-alignment-result \
    /absolute/private-separation-full-song-alignment.json \
  --full-song-join-remediation-review-result \
    /absolute/private-separation-full-song-join-remediation-review-result.json \
  --out /absolute/fresh/private-separation-publication-readiness.json
```

The ledger rechecks exact track coverage and the authorised excerpt and role
mapping hashes against the normalized MIDI evidence. It copies no private note
and computes no score. If even one Kim rating is partial, cannot-tell or severe,
the gate stays open. If the bounded minimum passes, only that one gate closes;
the independently assessed full-song, broad-role, hidden-set, terms, offline,
resource and public-route gates remain unchanged.

### Focused separated-vocal challenger review

The cross-song review identified a narrower failure that its two-candidate
contract cannot answer: on `Be Alone`, the listener heard an extended,
robotic-sounding held vocal in the mixed source that neither Kim nor the Moises
control preserved for its full duration. A read-only 250 ms activity diagnostic
then found the largest Kim/provider disagreements late in the exact excerpt.
Kim was near digital silence while one Suno alternative still contained
material. That numeric disagreement is only a way to choose challengers. It
does not prove that the remaining sound is the target vocal rather than bleed.

`scripts/private-separated-vocal-focus-review.py` turns that kind of human
observation into one bounded follow-up. It accepts one exact authorised excerpt,
the unchanged Kim result, the matching role map, one to five named provider
groups and a required plain-language listening focus. It anonymously shuffles
all candidates, level-matches them together, keeps the mixed source separate and
asks for independent focus-retention, bleed, artefact and usefulness labels.
More than one candidate may be useful; there is no preference or winner field.

The current four-way `Be Alone` package compares Kim, Moises and both supplied
Suno vocal estimates without revealing their positions:

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separated-vocal-focus-review.py --create \
  --track-id be-alone \
  --authorised-excerpt \
    work/separation-bakeoff/be-alone-authorised-191-206-v2/authorised-separation-excerpt.json \
  --candidate-evaluation \
    work/separation-bakeoff/be-alone-kim-fixed-native-v3-timed-midi-191-206-v1/private-melroformer-vocal-midi-evaluation.json \
  --role-mapping \
    work/separation-bakeoff/be-alone-role-mapping-191-206-v1/authorised-role-mapping.json \
  --provider moises --provider suno-a --provider suno-b \
  --focus \
    'The extended, robotic-sounding held vocal note in this excerpt: does the separated vocal continue for its full audible duration rather than being cut short?' \
  --out-dir \
    work/separation-bakeoff/be-alone-held-vocal-focus-review-v1
```

The unreviewed seed SHA-256 is
`50361a5771ac88ead7e446f83a59a744bc1b87f647778897d4da31b23f63e85b`;
the five-file audio manifest SHA-256 is
`85b84b943963879119f72be0efc4e8bf0a161bf3e8f91bab51e7bd12bc5a9f96`.
All four anonymous candidates re-read at exactly `-24.548949` dBFS sample RMS.
That is level-control evidence, not perceived-loudness equality.

After the browser export, resolve identities without opening the answer key:

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separated-vocal-focus-review.py \
  --resolve /absolute/separated-vocal-focus.reviewed.json \
  --package-dir \
    work/separation-bakeoff/be-alone-held-vocal-focus-review-v1 \
  --out /absolute/fresh/private-separated-vocal-focus-result.json
```

The resolver fails closed on changed focus text, source bindings, audio,
manifest, blind assignment or incomplete ratings. Its result remains a private
diagnostic with no activation authority. It deliberately does not feed the
cross-song publication gate: first use it to learn whether an already-supplied
alternative retains the missing event, then design a new cross-song test only
if that hypothesis survives human listening.

That review is now complete. The verified result has document SHA-256
`d325ff3584aa573ea919815cf33797443fbe2aaeb80d2da96ceb541d0436ac81`.
Kim, Moises and Suno B were marked useful for the exact held-vocal focus; Suno
A was not. Every candidate was rated only `partially_complete`. The listener
heard the final vocal as badly cut off and noted that the sustained event stops
sounding recognisably vocal in isolation even though song context makes it
perceptually vocal. Preserve that as a target-specific diagnostic. It neither
selects a model nor weakens the predeclared cross-song gate.

### Full-song bounded-worker queue

The full-song duration/alignment gate now has a safe executable precursor.
`scripts/private-separation-full-song-plan.py` does not increase the audited
Kim worker's 15-second input ceiling. Instead, it decodes one owner-authorised
original, converts the complete song once to the worker's 44.1 kHz stereo
clock, divides that exact clock into contiguous chunks and writes one
independently self-hashed worker-compatible authorisation package per chunk.
The partition has no gaps or overlaps. No model, checkpoint or product route is
opened.

The first real plan uses the owned `Be Alone` original:

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-full-song-plan.py \
  --corpus stem_examples/corpus.json \
  --track-id be-alone \
  --out-dir \
    work/separation-bakeoff/be-alone-full-song-kim-plan-v1
```

It binds the 50,411,692-byte, 48 kHz stereo source at SHA-256
`68156218501b952703fcff76addea5ade377dbdab92f25375ecd4515b3efca5d`.
The canonical clock is exactly 11,578,896 frames, 262.56 seconds and has zero
end-clock error. Eighteen equal 643,272-frame chunks cover that clock from
frame zero through the final frame; each is about 14.586667 seconds and remains
below the unchanged 661,500-frame worker ceiling. The canonical PCM24 integer
sequence SHA-256 is
`8172affc93c8e210c16ceef74d5ac36f455357ccdc7635f721db6d285c343b09`.
The plan file SHA-256 is
`8eb63e00994482652059072d9c9f5ef034a1063478b2682e192723cd1004bc34`
and its document SHA-256 is
`ee89785e095657c853427a6bc984248052cd1e28cf2e6893b294071ab5aca89d`.
All retained paths are relative to the private 66 MiB plan tree.

`scripts/private-separation-full-song-execute.py` now resumes that sealed plan
through the unchanged native owner. It defaults to one next chunk; `--all`
runs every remaining chunk sequentially. Every successful attempt must bind
the exact authorisation, checkpoint, terminal receipt, timing document, PCM24
hashes and planned frame count before durable state advances. An interrupted
or malformed attempt is preserved and retried under a fresh attempt number.
It never trusts, deletes or overwrites partial output.

The complete private run is at
`work/separation-bakeoff/be-alone-full-song-kim-execution-v1`. Two pre-inference
failures on chunk zero were intentionally retained: one used the wrong
coordinator runtime and one used a non-canonical launcher name. The correct
split-runtime invocation then completed all 18 chunks. Each successful native
attempt took 9.294787–10.014054 seconds, with 170.139463 seconds of summed
per-attempt terminal timing. The execution report file SHA-256 is
`a9c01bcc38c68d23e170a6d3c56dfb894ba57d7d2143eae5a5b4610183c8cfdb`;
its state SHA-256 is
`c8802598451d96dbf6ee6d4c7484de8328eaca1d1de98482f168baa39582cd62`.
This is failure-recovery and coarse runtime evidence, not a benchmark or a
quality result.

The coordinator must run under the core `.venv` Python while
`--runtime-launcher` names `.venv-ai/bin/python`. This is intentional: the
trusted owner and isolated MLX worker use separate pinned runtimes.

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-full-song-execute.py \
  --plan \
    work/separation-bakeoff/be-alone-full-song-kim-plan-v1/private-separation-full-song-plan.json \
  --out-dir \
    work/separation-bakeoff/be-alone-full-song-kim-execution-v1 \
  --repository-root "$PWD" \
  --runtime-launcher "$PWD/.venv-ai/bin/python" \
  --source-root \
    "$HOME/.local/share/sunofriend/private-evaluation/kim-vocal-2-mlx-v1/mlx-audio-source" \
  --checkpoint \
    "$HOME/.local/share/sunofriend/private-evaluation/kim-vocal-2-mlx-v1/model.safetensors" \
  --companion-root \
    "$HOME/.local/share/sunofriend/private-evaluation/kim-vocal-2-mlx-v1/checkpoint-directory" \
  --device gpu --all
```

`scripts/private-separation-full-song-stitch.py` re-verifies the complete
execution before concatenating. It performs no crossfade, per-chunk gain or
hidden repair. The source, vocal, instrumental and diagnostic reconstruction
are all exactly 11,578,896 frames at 44.1 kHz stereo PCM24; the source integer
sequence re-verifies the plan hash. The diagnostic sum needed no global
attenuation. The current stitch report document SHA-256 is
`8221fc571b333b1070c9cfa0791ac112f6089d76db8a182c0af499f836951c64`.

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-full-song-stitch.py \
  --plan \
    work/separation-bakeoff/be-alone-full-song-kim-plan-v1/private-separation-full-song-plan.json \
  --execution \
    work/separation-bakeoff/be-alone-full-song-kim-execution-v1/private-separation-full-song-execution.json \
  --out-dir \
    work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-playable-review
```

The authoritative human-review page is at
`be-alone-full-song-kim-stitch-v3-playable-review/BOUNDARY-REVIEW/separation_boundary_review.html`.
It first presents all four complete-song tracks, then 17 four-second units
centred on the exact joins. Rate the vocal, instrumental and reconstruction
independently for overall usefulness and for clicks, cut notes, level jumps or
tone changes. Exact duration and reconstruction do not establish seamlessness,
musical completeness or product readiness.

The earlier `v2` HTML is retained as evidence of a review-generator defect: an
unescaped newline made its JavaScript invalid before it could create the audio
controls. The `v3` page was generated afresh after the fix. Its HTML SHA-256 is
`ffbb6ac6949dcf38b3a95d8c14b979c1d1481ece8d6f5cbba2fd545af3c26d40`;
all 72 referenced WAV paths exist, and the embedded script parses successfully.

After the page exports
`separation-boundary-and-full-song.reviewed.json`, resolve it against the
unchanged stitch root:

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-full-song-review.py \
  --resolve /absolute/path/separation-boundary-and-full-song.reviewed.json \
  --package-dir \
    work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-playable-review \
  --out /absolute/fresh/private-separation-full-song-review-result.json
```

The resolver fails closed unless the complete song and all 17 joins were heard
and rated. It re-verifies the stitch report, immutable browser seed and every
complete-song and boundary WAV before retaining the human ratings and notes.
Its result deliberately keeps full-song quality acceptance, separator
selection, publication and every product route false. Review completion is
evidence, not acceptance.

That review is complete. The verified result is at
`work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-review-result-v1/private-separation-full-song-review-result.json`.
Its file SHA-256 is
`b10be9019d5ed3c67fd0c187f63cad7aa9121ac4ad71aa6b8a90c77ebd9d2935`
and its document SHA-256 is
`b0d0417f84913bc5c50cf1dfd7d3bf1fd740b7d1acc8d087c8c23663f7643686`.
The listener rated vocals, instrumental and reconstruction useful. The exact
reconstruction was clean at all 17 joins; vocals had audible joins at 11 and
12, and the instrumental had audible joins at 11 and 13. Exact duration and
complete listening are therefore verified, while seamlessness and full-song
duration/alignment acceptance remain open. There are no further current human
review pages awaiting the owner; older full-song packages are superseded
defect or provenance evidence.

Measure the separate source-to-reconstruction timing evidence against that
unchanged stitch root:

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-full-song-alignment.py \
  work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-playable-review \
  --out \
    work/separation-bakeoff/be-alone-full-song-source-reconstruction-alignment-v1/private-separation-full-song-alignment.json
```

The current result passes all nine declared timing windows at 0 ms measured
lag and 1.0 minimum normalized correlation. This proves that the diagnostic
reconstruction remains on the source clock for those windows. It does not
prove that either separated role is accurate or sounds good, and the audible
human-reviewed joins still keep the combined milestone open.

Those four human-rated defects now have a separate model-free remediation
plan. `scripts/private-separation-full-song-join-remediation-plan.py` verifies
the unchanged stitch, the resolved human review and the passing alignment
result before writing any proposal. It copies no listener notes, creates no
audio, runs no model and does not change publication readiness.

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-full-song-join-remediation-plan.py \
  work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-playable-review \
  --review-result \
    work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-review-result-v1/private-separation-full-song-review-result.json \
  --alignment-result \
    work/separation-bakeoff/be-alone-full-song-source-reconstruction-alignment-v1/private-separation-full-song-alignment.json \
  --out \
    work/separation-bakeoff/be-alone-full-song-join-remediation-plan-v1/private-separation-full-song-join-remediation-plan.json
```

The plan retains the raw stitch as the only control and deduplicates the four
role defects into three exact 15-second source-clock inferences: boundary 11
targets both vocals and instrumental, boundary 12 targets vocals, and boundary
13 targets instrumental. A later executor may use only a two-second candidate
patch around each join with 100 ms equal-power transitions at the patch edges.
The patch regions do not overlap, although the independently inferred source
windows may overlap. The planned output must remain a separate candidate;
vocals plus instrumental must be recomputed as a separate diagnostic
reconstruction rather than altering the raw one.

The current plan file SHA-256 is
`71ec5ffdf6653929d3e14692dafd41d3c6ac4bccb73ecf36fa8b666c2519b089`
and its document SHA-256 is
`5b2cb4730fa710f0ff08e2398a2d05a2cb9fe100d969a7a6fb29ece05563cec5`.
It initially recorded zero created candidates and zero completed worker runs.
The separate executor now consumes that sealed plan while keeping the original
stitch immutable:

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-full-song-join-remediation-execute.py \
  work/separation-bakeoff/be-alone-full-song-join-remediation-plan-v1/private-separation-full-song-join-remediation-plan.json \
  --package-dir \
    work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-playable-review \
  --source-plan \
    work/separation-bakeoff/be-alone-full-song-kim-plan-v1/private-separation-full-song-plan.json \
  --out-dir \
    work/separation-bakeoff/be-alone-full-song-join-remediation-execution-v1 \
  --repository-root "$PWD" \
  --runtime-launcher "$PWD/.venv-ai/bin/python" \
  --source-root \
    "$HOME/.local/share/sunofriend/private-evaluation/kim-vocal-2-mlx-v1/mlx-audio-source" \
  --checkpoint \
    "$HOME/.local/share/sunofriend/private-evaluation/kim-vocal-2-mlx-v1/model.safetensors" \
  --companion-root \
    "$HOME/.local/share/sunofriend/private-evaluation/kim-vocal-2-mlx-v1/checkpoint-directory" \
  --device gpu --all
```

The command is resumable and preserves interrupted attempts. It independently
reverified all three native worker results before creating candidate vocals,
instrumental and diagnostic reconstruction WAVs. The four two-second role
patches use only the planned 100 ms equal-power edges. Both role candidates are
PCM24-exact outside their named patch regions. Their pre-write peaks are
0.619194746 for vocals and 0.667407751 for instrumental. The reconstructed
candidate peak is 0.812045455, so its disclosed global gain remained 1.0.
Candidate creation is not evidence that any join improved.

Create the required owner listening page from those verified candidates:

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-full-song-join-remediation-review.py \
  work/separation-bakeoff/be-alone-full-song-join-remediation-execution-v1 \
  --package-dir \
    work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-playable-review \
  --out-dir \
    work/separation-bakeoff/be-alone-full-song-join-remediation-review-v1
```

The fresh page contains four blind raw-versus-candidate boundary comparisons,
eight blind patch-edge comparisons and three blind complete-song comparisons.
Short clips attenuate only the louder item to the quieter whole-window sample
RMS; the complete-song files are unchanged. All 30 audio references and their
hashes have been rechecked and the HTML JavaScript parses. Open
`join_remediation_review.html`, hear A and B for all 15 units, choose an
outcome and export `join_remediation_review.reviewed.json`. Do not open the
separate answer key first. The current owner review is now complete and was
verified before the answer key was opened. Readiness, separator selection and
every public product route remain false.

After the browser has exported the completed JSON, verify it without opening
the answer key:

```bash
chmod 600 /absolute/path/join_remediation_review.reviewed.json
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-full-song-join-remediation-review-result.py \
  --status /absolute/path/join_remediation_review.reviewed.json \
  --review-package-dir \
    work/separation-bakeoff/be-alone-full-song-join-remediation-review-v1 \
  --execution-dir \
    work/separation-bakeoff/be-alone-full-song-join-remediation-execution-v1 \
  --stitch-package-dir \
    work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-playable-review
```

The reviewed export, seed and later answer key must be owner-only, single-link
regular files. They are read once through bounded non-following descriptors;
the exact bytes parsed are the bytes hashed into the result. That read-only
status operation re-verifies the execution, candidate, stitch, immutable
browser export and all 30 audio references. For this v1 package it also
reconstructs every expected question, kind, time window and unordered
raw/candidate PCM24 pair from the verified execution evidence. Browser exports
larger than 8 MiB are rejected before parsing. Status reports that the key was
not opened and reveals no identity mapping. Only after status succeeds, run
the separate resolver with a fresh output:

The verified execution, candidate and stitch trees must remain quiescent while
status or resolution runs. Their report and WAV descriptors are not held open
as one atomic snapshot across the whole verification; this limitation is
recorded explicitly in both status and result documents.

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-full-song-join-remediation-review-result.py \
  --resolve /absolute/path/join_remediation_review.reviewed.json \
  --review-package-dir \
    work/separation-bakeoff/be-alone-full-song-join-remediation-review-v1 \
  --execution-dir \
    work/separation-bakeoff/be-alone-full-song-join-remediation-execution-v1 \
  --stitch-package-dir \
    work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-playable-review \
  --out /absolute/fresh/private-separation-full-song-join-remediation-review-result.json
```

The resolver repeats every public-evidence check before it opens the sealed
key. It then verifies the key's slot identities and level facts against the
already verified audio, writes and fsyncs a hidden owner-only file, and
atomically hard-links that complete inode to the fresh result name without
overwriting a raced file. Its self-hashed owner-only result maps A/B
choices to raw or candidate and summarises boundary, patch-edge and complete-
song outcomes. Terminal output is summary-only and does not print private unit
notes. The result deliberately keeps `original_audible_joins_resolved`,
publication readiness, separator selection and every product permission
false. A subsequent explicit readiness assessment, not the resolver, must
decide whether the human evidence satisfies the predeclared gate.

The current resolved result is the fresh, strengthened-verifier result at
`work/separation-bakeoff/be-alone-full-song-join-remediation-review-result-v4/private-separation-full-song-join-remediation-review-result.json`.
The earlier `v1`, `v2` and `v3` results are superseded private history; the
listening export and its choices did not change and no repeat listening review
was required.
All 15 units and 30 audio references verified. The targeted candidate was
preferred for two of four boundary-role comparisons and equivalent for the
other two; it was preferred for one patch edge and equivalent for seven; and
it was preferred for one complete-song role and equivalent for two. No unit
preferred the raw stitch, selected neither or returned cannot-tell. This is
useful evidence that the candidate introduced no heard regression in these
questions, but the two equivalent originally audible joins are not proven
removed. The result therefore keeps `original_audible_joins_resolved: false`
and the duration/alignment publication milestone open.

The next bounded increment is now recorded as the owner-only, self-hashed v2
plan at
`work/separation-bakeoff/be-alone-full-song-join-remediation-plan-v2/private-separation-full-song-join-remediation-plan-v2.json`.
Its file SHA-256 is
`dfdff09fbd7b6b79701f96075004493ba4726bf950a62b2425f031c030ef29c6` and
its document SHA-256 is
`3ca4ce793b569e3c0032051e90767796bf4147bafa658c5563ee94863a671a90`.
The plan derives only the two v1 outcomes that the listener rated equivalent:
boundary 11 vocals at 160.453333 seconds and boundary 13 instrumental at
189.626667 seconds. Their full-song patch ranges are respectively
`[6987792, 7164192)` and `[8274336, 8450736)` frames; both reuse the verified
worker-local range `[242550, 418950)`. The successful boundary 11
instrumental and boundary 12 vocals v1 repairs remain preserved.

Generate this plan from the exact sealed evidence chain with:

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-full-song-join-remediation-plan-v2.py \
  work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-playable-review \
  --full-song-review-result \
    work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-review-result-v1/private-separation-full-song-review-result.json \
  --v1-plan \
    work/separation-bakeoff/be-alone-full-song-join-remediation-plan-v1/private-separation-full-song-join-remediation-plan.json \
  --v1-execution \
    work/separation-bakeoff/be-alone-full-song-join-remediation-execution-v1/private-separation-full-song-join-remediation-execution.json \
  --v1-candidate \
    work/separation-bakeoff/be-alone-full-song-join-remediation-execution-v1/private-separation-full-song-join-remediation-candidates.json \
  --resolved-join-review-result \
    work/separation-bakeoff/be-alone-full-song-join-remediation-review-result-v4/private-separation-full-song-join-remediation-review-result.json \
  --publication-readiness \
    work/separation-bakeoff/separation-publication-readiness-v12/private-separation-publication-readiness.json \
  --out \
    work/separation-bakeoff/be-alone-full-song-join-remediation-plan-v2/private-separation-full-song-join-remediation-plan-v2.json
```

The sole signal-processing change is a wider patch: one second on either side
of the join becomes two seconds on either side, so the total patch grows from
two to four seconds. The 100 ms equal-power edges and original 15-second
source windows do not change. This is an assembly-policy experiment over the
sealed v1 worker WAVs: it schedules zero model calls, creates no audio, starts
from the verified v1 candidate and cannot select a separator or close a
readiness gate. Publication readiness therefore remains the unchanged v12
context, not an authority for choosing targets.

A targeted v2 listening page now exists and its human review is outstanding.
It is deliberately limited to the two anonymous v1-versus-v2 boundary
comparisons and four new v2 patch edges described below. No v1 review or
alignment decision transfers to this candidate.

The sealed v2 candidate can now be assembled without another model run:

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-full-song-join-remediation-execute-v2.py \
  work/separation-bakeoff/be-alone-full-song-join-remediation-plan-v2/private-separation-full-song-join-remediation-plan-v2.json \
  --package-dir \
    work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-playable-review \
  --full-song-review-result \
    work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-review-result-v1/private-separation-full-song-review-result.json \
  --v1-plan \
    work/separation-bakeoff/be-alone-full-song-join-remediation-plan-v1/private-separation-full-song-join-remediation-plan.json \
  --v1-execution \
    work/separation-bakeoff/be-alone-full-song-join-remediation-execution-v1/private-separation-full-song-join-remediation-execution.json \
  --v1-candidate \
    work/separation-bakeoff/be-alone-full-song-join-remediation-execution-v1/private-separation-full-song-join-remediation-candidates.json \
  --resolved-join-review-result \
    work/separation-bakeoff/be-alone-full-song-join-remediation-review-result-v4/private-separation-full-song-join-remediation-review-result.json \
  --publication-readiness \
    work/separation-bakeoff/separation-publication-readiness-v12/private-separation-publication-readiness.json \
  --out-dir \
    work/separation-bakeoff/be-alone-full-song-join-remediation-execution-v2
```

The completed execution report is
`work/separation-bakeoff/be-alone-full-song-join-remediation-execution-v2/private-separation-full-song-join-remediation-execution-v2.json`.
Its file SHA-256 is
`a4f4231f70fdac4991243b31c87b7efbb0503d547cd6e3731e4dd13ac3ef1bce`
and its document SHA-256 is
`ba25d98198f47d8e957020efd69656442d290652a0ac43b25243c608e7aad906`.
The three 44.1 kHz stereo PCM24 candidate WAV hashes are:

- vocals:
  `9818d546c64591a42dc9fa5593e88e0dd2e147295c3e00d6147a1a667f49db5e`;
- instrumental:
  `1f5c7a4b111832f87577325cfba4535075b6e903c4c53c1a683b0ef62869a5a9`;
- diagnostic reconstruction:
  `0755a13ef7313d900339673730725d83e644077681e3b67d0c59b4f3a6a9b5fd`.

The executor re-derived the plan from the complete evidence chain, began from
the verified v1 candidate rather than the raw stitch, and reused the exact
sealed worker-local `[242550, 418950)` slice. It changed 194,026 PCM24 sample
values in vocals `[6987792, 7164192)` and 194,028 in instrumental
`[8274336, 8450736)`. Every PCM24 sample outside each role's target range is
identical to the v1 candidate, including the preserved boundary 12 vocals and
boundary 11 instrumental repairs. The diagnostic reconstruction was computed
from the written v2 role WAVs; its pre-gain peak was 0.812045455 and its
attenuation-only global gain was 1.0.

The output root is fresh and owner-only, files are owner-only and single-link,
staged WAVs use exclusive no-follow descriptor writes, inputs and published
audio are rechecked before the completion report is written, and outputs are
forbidden inside any bound evidence tree. The operation made zero model calls,
used no network and did not mutate the stitch, v1 candidate, worker output,
review evidence or readiness ledger. Candidate integrity is not audible repair
or musical quality: every permission and readiness decision remains false,
and the targeted v2 listening review described above is still required.

Generate the sealed targeted review into a fresh directory whose existing
parent is owner-only:

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-full-song-join-remediation-review-v2.py \
  work/separation-bakeoff/be-alone-full-song-join-remediation-execution-v2 \
  --v2-plan \
    work/separation-bakeoff/be-alone-full-song-join-remediation-plan-v2/private-separation-full-song-join-remediation-plan-v2.json \
  --v1-execution-dir \
    work/separation-bakeoff/be-alone-full-song-join-remediation-execution-v1 \
  --full-song-review-result \
    work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-review-result-v1/private-separation-full-song-review-result.json \
  --v1-plan \
    work/separation-bakeoff/be-alone-full-song-join-remediation-plan-v1/private-separation-full-song-join-remediation-plan.json \
  --resolved-join-review-result \
    work/separation-bakeoff/be-alone-full-song-join-remediation-review-result-v4/private-separation-full-song-join-remediation-review-result.json \
  --publication-readiness \
    work/separation-bakeoff/separation-publication-readiness-v12/private-separation-publication-readiness.json \
  --package-dir \
    work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-playable-review \
  --out-dir \
    work/separation-bakeoff/be-alone-full-song-join-remediation-review-v2
```

Open
`work/separation-bakeoff/be-alone-full-song-join-remediation-review-v2/join_remediation_review_v2.html`.
The page has two blind v1-versus-v2 boundary comparison units and four
single-player v2 patch-edge units: six units and eight audio references in
total. For each boundary, hear A and B, rate each independently as `clean`,
`audible_join` or `cannot_tell`, then choose `A`, `B`, `equivalent`, `neither`
or `cannot_tell`. For each edge, confirm it was heard and give the same
absolute cleanliness rating. The short boundary pairs use attenuation-only
sample-RMS matching. The four edge clips preserve the exact v2 PCM24 samples.
The public report and page expose only opaque commitments; v1/v2 identities
and source details remain in the sealed answer key.

The review report file SHA-256 is
`e646043606b75c884fadc2bc22591868db72089f93b06b6d6db7f45d20befe1b` and
its document SHA-256 is
`0d691805f4f8ecfda3e57f26a1f9b87f3d12858dd26f2ba156b79cd82a1b423a`.
The HTML SHA-256 is
`5b460af9293cc5825298f66df36a55f284a7ae93033dff9151fd11ab977e9fa2`.
The sealed answer-key file SHA-256 is
`e17a034eb7a220957952ad3657772c31918be4d1d54dd09ba10593fa547fb47c`
and its document SHA-256 is
`6848541cc0b634937debf04397650dabe19e72c299065cd72e62c3b3d6a4f4f7`.
The package commitment is
`2bc140793f4b483b1aa3e9db8f619174aa564736dee726c09ad9fa2898f2974a`.

After the listener marks every unit complete and exports
`join_remediation_review_v2.reviewed.json`, secure the browser download and
run the key-blind status check first:

```bash
REVIEWED="$HOME/Downloads/join_remediation_review_v2.reviewed.json"
chmod 600 "$REVIEWED"

PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-full-song-join-remediation-review-result-v2.py \
  --status "$REVIEWED" \
  --review-package-dir \
    work/separation-bakeoff/be-alone-full-song-join-remediation-review-v2 \
  --v2-execution-dir \
    work/separation-bakeoff/be-alone-full-song-join-remediation-execution-v2 \
  --v2-plan \
    work/separation-bakeoff/be-alone-full-song-join-remediation-plan-v2/private-separation-full-song-join-remediation-plan-v2.json \
  --v1-execution-dir \
    work/separation-bakeoff/be-alone-full-song-join-remediation-execution-v1 \
  --package-dir \
    work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-playable-review \
  --full-song-review-result \
    work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-review-result-v1/private-separation-full-song-review-result.json \
  --v1-plan \
    work/separation-bakeoff/be-alone-full-song-join-remediation-plan-v1/private-separation-full-song-join-remediation-plan.json \
  --resolved-join-review-result \
    work/separation-bakeoff/be-alone-full-song-join-remediation-review-result-v4/private-separation-full-song-join-remediation-review-result.json \
  --publication-readiness \
    work/separation-bakeoff/separation-publication-readiness-v12/private-separation-publication-readiness.json
```

Status reconstructs the six public units and all eight PCM24 references from
the exact evidence chain, validates the immutable browser export and keeps the
answer key unopened. Keep all bound evidence trees quiescent during status and
resolution. If status succeeds, create a fresh owner-only result directory and
repeat the same bindings with `--resolve`:

```bash
RESULT_DIR=work/separation-bakeoff/be-alone-full-song-join-remediation-review-result-v2
mkdir -m 700 "$RESULT_DIR"

PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-full-song-join-remediation-review-result-v2.py \
  --resolve "$REVIEWED" \
  --review-package-dir \
    work/separation-bakeoff/be-alone-full-song-join-remediation-review-v2 \
  --v2-execution-dir \
    work/separation-bakeoff/be-alone-full-song-join-remediation-execution-v2 \
  --v2-plan \
    work/separation-bakeoff/be-alone-full-song-join-remediation-plan-v2/private-separation-full-song-join-remediation-plan-v2.json \
  --v1-execution-dir \
    work/separation-bakeoff/be-alone-full-song-join-remediation-execution-v1 \
  --package-dir \
    work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-playable-review \
  --full-song-review-result \
    work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-review-result-v1/private-separation-full-song-review-result.json \
  --v1-plan \
    work/separation-bakeoff/be-alone-full-song-join-remediation-plan-v1/private-separation-full-song-join-remediation-plan.json \
  --resolved-join-review-result \
    work/separation-bakeoff/be-alone-full-song-join-remediation-review-result-v4/private-separation-full-song-join-remediation-review-result.json \
  --publication-readiness \
    work/separation-bakeoff/separation-publication-readiness-v12/private-separation-publication-readiness.json \
  --out \
    "$RESULT_DIR/private-separation-full-song-join-remediation-review-result-v2.json"
```

Resolution opens the sealed key only after the complete export passes the
public checks. It records identity-resolved absolute cleanliness and relative
preference separately. A targeted pass requires the v2 identity to be rated
`clean` at both target boundaries and all four v2 patch edges to be rated
`clean`. Even a pass enables only fresh candidate-bound full-song and
alignment reviews: `original_audible_joins_resolved`, selection, acceptance,
readiness and publication remain false.

This targeted review remains outstanding. Its creation, completion or a
passing result cannot select a separator, accept the candidate, change
readiness, enable publication or activate any product route. Passing all six
units permits only the later creation of a fresh immutable candidate-bound
three-role, 17-boundary full-song review and a fresh nine-window alignment
review. Those later reviews must not inherit v1 decisions.

The full-song half of that later gate is now implemented but remains inert
until the targeted result exists and passes. The builder verifies the complete
v1/v2 evidence chain again, requires both v2 target joins and all four v2 patch
edges to be explicitly `clean`, copies the unchanged source plus the exact v2
vocals, instrumental and reconstruction PCM24 files into a fresh private root,
and recreates all 17 original boundary windows. It runs no model and writes its
completion report last. A missing, changed, incomplete or non-passing targeted
result is rejected before the output directory is created.

After a passing result only, use:

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-candidate-full-song-review.py \
  --v2-review-result \
    work/separation-bakeoff/be-alone-full-song-join-remediation-review-result-v2/private-separation-full-song-join-remediation-review-result-v2.json \
  --v2-execution-dir \
    work/separation-bakeoff/be-alone-full-song-join-remediation-execution-v2 \
  --v2-plan \
    work/separation-bakeoff/be-alone-full-song-join-remediation-plan-v2/private-separation-full-song-join-remediation-plan-v2.json \
  --v1-execution-dir \
    work/separation-bakeoff/be-alone-full-song-join-remediation-execution-v1 \
  --package-dir \
    work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-playable-review \
  --full-song-review-result \
    work/separation-bakeoff/be-alone-full-song-kim-stitch-v3-review-result-v1/private-separation-full-song-review-result.json \
  --v1-plan \
    work/separation-bakeoff/be-alone-full-song-join-remediation-plan-v1/private-separation-full-song-join-remediation-plan.json \
  --resolved-join-review-result \
    work/separation-bakeoff/be-alone-full-song-join-remediation-review-result-v4/private-separation-full-song-join-remediation-review-result.json \
  --publication-readiness \
    work/separation-bakeoff/separation-publication-readiness-v12/private-separation-publication-readiness.json \
  --out-dir \
    work/separation-bakeoff/be-alone-v2-candidate-full-song-review-v1
```

The fixed completion marker is
`private-separation-candidate-full-song-review-package.json`; the human page is
`BOUNDARY-REVIEW/separation_boundary_review.html`. Building or completing that
page still cannot select or accept the candidate, prove alignment, resolve the
original audible joins, change readiness or publish anything. A separate
candidate-bound review resolver and the fresh nine-window alignment package
remain later increments.

The independent coarse resource observation can run before the listener
finishes that page because it makes no musical judgement:

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-full-song-resource.py \
  --plan \
    work/separation-bakeoff/be-alone-full-song-kim-plan-v1/private-separation-full-song-plan.json \
  --execution \
    work/separation-bakeoff/be-alone-full-song-kim-execution-v1/private-separation-full-song-execution.json \
  --stitch \
    work/separation-bakeoff/be-alone-full-song-kim-stitch-v2-full-review/private-separation-full-song-stitch.json \
  --out \
    work/separation-bakeoff/be-alone-full-song-kim-resource-v1/private-separation-full-song-resource.json
```

That verified report has document SHA-256
`a6a68350336037ad1cc5944808f136f64a55c2cad1a99f18d47f6f4b758d481a`.
It rechecked all 18 selected attempts, the two safely preserved incomplete
attempts, the exact stitch and every retained regular file. The selected
coarse monotonic timings total 170.139463 seconds for 262.56 seconds of source,
an observed serial real-time factor of 0.648002 in this one uncontrolled run.
The plan, execution and stitch snapshots contain 565,805,462 regular-file
bytes in aggregate. This is not a benchmark: operating-system cache, scheduler
and thermal state were uncontrolled, and peak process RSS, accelerator memory,
energy and concurrent load were not measured. The full-song resource envelope
therefore remains unaccepted.

Fresh native attempts now retain two separate path-free resource projections
in their terminal receipt. The worker projection carries validated model-call
duration, input frames, chunk count, device and peak MLX allocator bytes. The
native owner separately captures Darwin `wait4` peak RSS and
`proc_pid_rusage` V6 lifetime maximum physical and neural footprints only at
exact reap, after the owned process group is empty; no PID is retained. Both
projections are self-hashed and bound to the exact request, worker result and
child result. The full-song observer reports a measurement as complete only
when every selected attempt has its matching projection. These remain distinct
allocator, RSS and physical-footprint quantities. Existing completed attempts
predate the projections, so they cannot be backfilled and the current 18-chunk
coarse report correctly remains unchanged.

The next resource step is now frozen before any repeat is run:

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-full-song-resource-benchmark-plan.py \
  --plan \
    work/separation-bakeoff/be-alone-full-song-kim-plan-v1/private-separation-full-song-plan.json \
  --runtime-launcher .venv-ai/bin/python \
  --checkpoint \
    "$HOME/.local/share/sunofriend/private-evaluation/kim-vocal-2-mlx-v1/model.safetensors" \
  --device gpu \
  --repetitions 3 \
  --out \
    work/separation-bakeoff/be-alone-full-song-kim-resource-benchmark-plan-v1/private-separation-full-song-resource-benchmark-plan.json
```

This starts no model. It binds the exact full-song clock, checkpoint and
resolved runtime executable, probes the current Mac with fixed local commands,
then rechecks the runtime and checkpoint before publication. It freezes three
fresh, serial, non-overlapping repetitions and the existing ceilings of 120
wall seconds per audio minute, 900 wall seconds per song and 12 GiB peak total
unified memory. Every repeat must retain parent-observed full-song wall time,
worker model-call time, process RSS, MLX allocator peak, total unified-memory
peak, thermal state before/after and timeout/OOM outcome. MLX allocator peak
cannot stand in for either of the other memory measurements.

The current plan's JSON file SHA-256 is
`b551213724acef7163e468a785e77ece5fe030f04bf660a7a1a9532dd4b04437` and
its document SHA-256 is
`d3005fbf0fb12ec6948e59597f2927231919523b16109b43a96bf2855eacbeef`.
It records the development machine as macOS 26.5.1 build 25F80, arm64,
CPython 3.12.10 and 36 GiB unified memory. That is useful development evidence
but cannot satisfy the separately required 16 GiB acceptance class. All three
slots remain `not_run`, resource acceptance remains false and no separator or
product route is enabled.

The bounded one-repetition runner and three-report verifier are now
implemented. The runner re-verifies the inert plan, sealed song plan, runtime,
checkpoint and current machine before starting, creates one fresh owner-only
root, runs every chunk, stitches it, writes the resource observation, then
rechecks the plan/runtime/checkpoint. It records parent wall time, worker model
time, exact-reap RSS, MLX allocator peak, Darwin physical-footprint peak,
thermal state before/after and explicit no-timeout/no-OOM outcomes. One script
process can write only one repetition. A failed or interrupted root is evidence
to preserve; rerun into a different fresh root.

Run the three repetitions serially as three separate Python processes. This is
the command shape used for the completed private development run:

```bash
set -e
for repetition in 1 2 3; do
  PYTHONPATH=src ./.venv/bin/python \
    scripts/private-separation-full-song-resource-benchmark-run.py \
    --benchmark-plan \
      work/separation-bakeoff/be-alone-full-song-kim-resource-benchmark-plan-v1/private-separation-full-song-resource-benchmark-plan.json \
    --plan \
      work/separation-bakeoff/be-alone-full-song-kim-plan-v1/private-separation-full-song-plan.json \
    --repetition "$repetition" \
    --out-dir \
      "work/separation-bakeoff/be-alone-full-song-kim-resource-run-$repetition" \
    --repository-root "$PWD" \
    --runtime-launcher "$PWD/.venv-ai/bin/python" \
    --source-root \
      "$HOME/.local/share/sunofriend/private-evaluation/kim-vocal-2-mlx-v1/mlx-audio-source" \
    --checkpoint \
      "$HOME/.local/share/sunofriend/private-evaluation/kim-vocal-2-mlx-v1/model.safetensors" \
    --companion-root \
      "$HOME/.local/share/sunofriend/private-evaluation/kim-vocal-2-mlx-v1/checkpoint-directory"
done
```

Only after all three commands succeed, verify the exact reports:

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-full-song-resource-benchmark-result.py \
  --benchmark-plan \
    work/separation-bakeoff/be-alone-full-song-kim-resource-benchmark-plan-v1/private-separation-full-song-resource-benchmark-plan.json \
  --repetition-report \
    work/separation-bakeoff/be-alone-full-song-kim-resource-run-1-v2/private-separation-full-song-resource-benchmark-repetition.json \
  --repetition-report \
    work/separation-bakeoff/be-alone-full-song-kim-resource-run-2/private-separation-full-song-resource-benchmark-repetition.json \
  --repetition-report \
    work/separation-bakeoff/be-alone-full-song-kim-resource-run-3/private-separation-full-song-resource-benchmark-repetition.json \
  --out \
    work/separation-bakeoff/be-alone-full-song-kim-resource-benchmark-result-v1.json
```

The verifier rejects missing/duplicate slots, reused nonces, overlapping wall
intervals, identity drift, incomplete measurements, malformed thermal states,
and threshold fields that do not recompute. It may report whether all three
runs met the frozen ceilings on the 36 GiB development Mac. It must still keep
`resource_envelope_accepted` false because this is not the separately required
16 GiB acceptance class. Neither command selects a separator or enables a
public route.

The first attempted repetition root,
`be-alone-full-song-kim-resource-run-1`, is preserved as an 8 KiB
pre-inference failure. The initial runner verified the virtual-environment
launcher but passed its resolved base executable into the native session,
which correctly rejected the missing virtual-environment boundary. The runner
now keeps those responsibilities separate: it hash-binds the resolved
executable while passing the exact `.venv-ai/bin/python` invocation path. A
symlinked-launcher regression test guards that distinction. Repetition 1 was
then run from a fresh `-run-1-v2` root; the failed root was not reused.

All three successful roots contain 18 independently verified native attempts
and distinct process-scoped nonces. The aggregate verifier confirmed serial
non-overlap, identical plan/checkpoint/runtime/device/machine bindings and all
required measurements. On the 262.56-second song:

- whole-pipeline time was 172.561330–173.454702 seconds, median 172.962042;
- wall time per audio minute was 39.433576–39.637729 seconds;
- summed worker model-call time was 53.882378–53.985068 seconds;
- peak RSS was 1,118,208,000–1,141,309,440 bytes;
- peak MLX allocator memory was 2,324,039,502 bytes in all three runs;
- Darwin lifetime physical footprint was
  4,089,218,536–4,093,199,920 bytes, at most 3.812089 GiB;
- every before/after thermal state was `nominal`, with zero timeouts and zero
  OOM outcomes.

Every repetition met the frozen development ceilings. The result file SHA-256
is `9a2541d16009de4173076db0e3771026ae34167f4cdaf4c2a30c6957fbcbb7cf`;
its document SHA-256 is
`a56216ca88fd4795e802d0b4ae01f5104d1dc60338373f33482b3c4ed3769ec9`.
`controlled_repeated_benchmark_complete` and
`development_machine_thresholds_met` are true. Resource acceptance and
publication readiness remain false because the observed Mac has 36 GiB, not
the separately required 16 GiB acceptance class. This evidence changes no
separator selection, source graph or product route.

The optional review contract now asks that question explicitly with
`--classify-focus-phrase-coverage`. For every playable candidate, the listener
must separately choose `substantially_complete`, `partially_complete`,
`little_or_no_focus_line` or `cannot_tell`. This stays independent of source
line identity and the existing useful/not-useful disposition. A fresh review
of the earlier window recorded four `partially_complete` candidates and two
`little_or_no_focus_line` candidates; none was `substantially_complete`. Suno B
`leaf-01` was the only candidate both useful for the focus and partially
complete. The authoritative later-window repeat classified Kim primary,
Moises leaf 01, Moises leaf 02 and Suno A leaf 01 as substantially complete
and useful for the focus; Suno B leaf 01 was `cannot_tell` for source line,
completeness and usefulness. Moises leaf 01's reference was classified as a
different line even though its MIDI was still marked substantially complete
and useful for the written focus. Preserve those independent human judgements
rather than inferring one from another. The next listening gap is the
song-disjoint `Be Alone` cell, not another `I am a Alien mashup` repeat.

The browser now puts the enabled review purpose in the page and browser-tab
title, states the required independent decisions above the players and exports
a purpose-and-window-specific filename such as
`vocal-line-and-phrase-completeness-3450-6850.reviewed.json`. This prevents a
generic export from an older open tab being mistaken for the new structured
review. An older open tab may still download under a generic name, as happened
for the completed earlier-window review. The resolver nevertheless verifies
the exact seed, candidate set, window and evidence hashes and fails closed if
the contents do not match; the filename is navigation help, not evidence.

### Current private human-review queue

As of 3 August 2026, the first scoped `I am a Alien mashup` review is complete.
It compared only the unchanged Kim primary and unchanged lowest-line hypothesis
from 3.45 to 6.85 seconds, where both contain activity, with the question
**Which candidate follows the intended male lead melody in this phrase?** The
listener marked the lowest-line hypothesis useful for that exact focus and the
primary not useful for it. The separate verifier accepted the exact export and
published a `complete_review_no_activation` resolution with document SHA-256
`c26d293df96ae0259ba32510eea3827edf2dba257dc5fbd5a3b7c3989ad45fae`.
The other 15 candidates remain preserved, unranked and unaffected. This result
does not select, merge, repair or activate either candidate. There is no
outstanding review on this scope.

The later-phrase review from 9.20 to 14.95 seconds is also complete. It asked
whether unchanged `kim/primary` follows the intended male-lead melody. That
candidate contains 17 overlapping notes out of 23 across the complete excerpt;
`kim/register/lowest-line` has no notes in this window and was omitted rather
than presented as a silent comparison. The listener marked the primary not
useful for the stated male-lead focus and added the decisive observation that
the source in this window is a female vocal and that the MIDI reflects that
vocal accurately. The exact reviewed export SHA-256 is
`38d07cbb966854c4f1d5fbc944dd19197d35e395929310d818b27dc0fe99ab4a`.
The separate verifier accepted it and wrote a
`complete_review_no_activation` result whose document SHA-256 is
`96745fb47a396606f225eb66a3b3380bca601fb98c5981e0234e730cd89c4764`.

This is evidence of a **line-assignment failure**, not a transcription-quality
failure. It does not justify a stitched male-lead challenger: the earlier
lowest-register evidence is useful for the male lead only in the earlier
phrase, while this later primary evidence follows a different vocal line. All
other candidates remain preserved, unranked and unaffected.

A follow-up scoped review tested four provider vocal leaves over the same
9.20–14.95 second window. All four references were marked as a different line
from the written male-line focus, and all four candidate MIDIs were marked
`not_useful_for_focus`. The authoritative reviewed export SHA-256 is
`645820e9d6dab0b1a77ff4650429dbe8651de05be1971859acf08a35ef9ec850`;
the path-free resolution document SHA-256 is
`42ca7df2fa3ef30da6a38d63205fdc22cf7d0b263910d11fd657c0d9145b3b52`.
An earlier browser export of the same four choices is retained as a superseded
draft, not counted as an independent listening result.

More importantly, the listener corrected the question itself: the useful
musical distinction is **principal lead versus backing or overlapping vocal
line**, not male versus female voice. The completed result remains valid only
for its exact written focus and therefore cannot answer which candidate best
captures the principal lead. No stitched candidate is justified. Future
reference-line reviews must name the musical role or phrase and keep voice
demographics out of the target definition.

The fresh role-based repeat is now complete. It added unchanged `kim/primary`
to the four provider leaves and asked for the **principal lead-vocal melody;
backing harmony or another overlapping line was not the target**. The listener
classified `kim/primary`, Moises `leaf-02`, Suno A `leaf-01` and Suno B
`leaf-01` as the focus line and marked each MIDI useful for that exact focus.
Moises `leaf-01` was classified as a different line and its MIDI was not useful
for the principal-lead focus. The exact reviewed export SHA-256 is
`221e24708d4a2076583dd0c7e6ae5f2176d7313717eba43b3b3383564fbe9232`;
the path-free resolution document SHA-256 is
`1e10f317def79776515659a2dc950e6f1181448d850386d9597c183735629098`.

This resolves the framing problem but does not select a winner. Four useful
candidates remain separate; the different-line leaf is preserved as potential
backing or alternate evidence. No merge, repair, default, activation or product
route changed.

The follow-up private geometry report compared those four useful candidates
without rendering, selecting or merging them. Across the six pairings, each
pair had 16 exact-pitch onset matches at an 80 ms tolerance. Pairwise F1 was
either 0.941176 or 0.969697, median onset error was 0 ms, and p95 onset error
was no more than 23.22 ms. All four used the same six MIDI pitches from 68 to
77. Their differences are therefore limited to one boundary-overlapping note
and small timing or duration changes around a common 16-note phrase, not
complementary inner-phrase notes. The path-free report is
`i-am-a-alien-principal-lead-later-phrase-geometry-9200-14950-v1/private-reviewed-vocal-geometry.json`;
its document SHA-256 is
`3993aa00547b388e3df328bbb4b58d52896f8cc05617b77e8c5b40fdd7d1e5e7`.
This does not promote Kim primary, but it shows there is no evidence-based
reason to merge these near-duplicates for this phrase.

The matching role-correct review of the earlier 3.45–6.85 second phrase is now
also complete. It compared Kim primary, Kim lowest-line, two Moises leaves and
one leaf from each Suno pack. Only Suno B `leaf-01` was marked useful for the
principal-lead focus. The listener explicitly noted that it covers the lead
but does not capture every note. The other five candidates were heard and
marked not useful for this exact focus; they remain preserved rather than
deleted or globally rejected. The authoritative reviewed export SHA-256 is
`4a327cc1f567c253bdafbf6ee777e78e807915c6d0ced6d0d99e8fd2d6d6c513`;
the path-free resolution document SHA-256 is
`a96a0e462359070f923105b4b64537a8c0ebe4634b1250b39485d14ae1b218c7`.
This resolves the outstanding review queue but does not make Suno B a winner,
complete transcription, automatic merge source, default or product route.

A fresh structured repeat of that earlier window is also complete. It retained
the same six-candidate scope and independently asked about source-line
relationship, usefulness and focus-phrase coverage. Suno B `leaf-01` remained
the only useful candidate and was classified `partially_complete`, not
`substantially_complete`. Kim primary and Moises leaf 01 were classified
`little_or_no_focus_line`; Kim lowest-line, Moises leaf 02 and Suno A leaf 01
were `partially_complete` but not useful for the exact focus. The reviewed
export file SHA-256 is
`c3ab7186a9deb1ed6e7af0cea76a3552f1f734157ec9055db22951a38ad3554c`.
The verified resolution has file SHA-256
`3834cdaa4b6a54c385bd7bc7ad4650cfe3b727cd80755a86242000b70e1cb184`
and document SHA-256
`173dbb800ee1d0bc64a1ff885fdd125aa064ef076dc0ff4c7ae53ec14a4de1e9`.
Its status is `complete_review_no_activation`: no candidate was selected,
merged, repaired, promoted or made production-eligible.

The later 9.20–14.95 second phrase now has the same structured review. The
first complete export is retained as superseded history because the listener
made a second pass over the same exact seed. The later export is authoritative:
Kim primary, Moises leaf 01, Moises leaf 02 and Suno A leaf 01 were each marked
`substantially_complete` and useful for the principal-lead focus. Suno B leaf
01 was `cannot_tell` for source-line relationship, phrase completeness and
usefulness. Moises leaf 01's reference was classified as a different line even
though its MIDI was marked substantially complete and useful; those are
separate human questions and are preserved without reinterpretation. The
authoritative export file SHA-256 is
`21e6ec91e5b09c2d5e449905427986d793e0aeb60d46856fa2c74128d290f044`.
The verified resolution has file SHA-256
`a2f52c99a758d6022568c85c58461b21fc263e1c36cac31f1ac5e88fe8c520d7`
and document SHA-256
`79e1f2cf72e8037c5d5dde8cc0bbb26ccbc39a496eca870c3e83f2ecfe937b23`.
It selected, merged, repaired and activated nothing.

The song-disjoint `Be Alone` review is now complete over the entire sealed
0.00–15.00 second excerpt. Kim primary, Moises leaf 02, Suno A leaf 01 and
Suno B leaf 01 were each classified as the principal focus line and useful for
that exact focus. Suno B leaf 01 was `substantially_complete`; the other three
were `partially_complete`. Moises leaf 01 was a different line, contained
little or none of the focus line and was not useful for the principal-lead
focus. The reviewed export file SHA-256 is
`0eecf78afbf3b625f8a66e3560653a712cc0838211c645a65878771fd33f3339`.
The verified resolution has file SHA-256
`53efb9caeca7dd7b8d7410c9fe59e50b051da4c854e431561d91cfc6834a4188`
and document SHA-256
`257a308552dda806f29c2083bc52db46b07ebb587bd5e96e3b98cb8ff793b4d3`.
It selected, merged, repaired and activated nothing.

The reusable owner-only command is:

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-reviewed-vocal-geometry.py \
  --review-resolution /absolute/review-resolution.json \
  --candidate-set /absolute/vocal-candidate-set.json \
  --melroformer-evaluation /absolute/melroformer-evaluation.json \
  --vocal-leaf-evaluation /absolute/vocal-leaf-evaluation.json \
  --phrase-completeness /absolute/vocal-phrase-completeness.json \
  --authorised-excerpt /absolute/authorised-separation-excerpt.json \
  --out /absolute/fresh/private-reviewed-vocal-geometry.json
```

It requires at least two candidates marked useful by one exact completed
review, reconstructs the sealed review scope, verifies all note artifacts and
writes only diagnostic JSON. It cannot select, merge, repair, activate or
publish a candidate.

Future private reviews can explicitly opt into
`--classify-reference-line`. That adds a required, separate focus-relative
human label for whether the heard source is the named focus line, a different
line, mixed/overlapping lines or unclear. The MIDI usefulness judgement remains
separate. Existing review commands retain their previous exact shape unless
the flag is supplied. These labels do not infer singer identity, sex, gender or
demographics. The caller must define the target musically, for example the
principal lead-vocal melody rather than backing harmony.

The first live browser load also exposed an escaped-newline defect in the
inline export script. It was fixed before the review, both source and candidate
audio were verified in the browser, and the served-page test now guards the
JavaScript escape sequence. Playback itself still writes nothing.

The
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
