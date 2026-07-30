# Stem access and local separation research

Status: **research and architecture decision complete; S1 synchronized source
preparation and S2 source lineage/composite drums accepted; S3 includes the
backend-neutral and blocked-execution groundwork, a fresh private
provenance-bound Darwin build, and a test-only live descriptor canary for the
exact physical source FDs 3/4/5 plus representative low, mixed-collision and
scratch-collision/near-limit layouts. The native call now returns a
preallocated exact-child owner rather than a bare PID. Deterministic fake
execution, exhaustive arbitrary source-FD proof, path-TOCTOU closure, bounded
emergency-finalizer proof, live child-signal-state proof, real source
separation, hidden evaluation and promotion are not implemented**

Checked: 30 July 2026

## Contents

- [Decision and current boundary](#executive-decision)
- [Terms and ways to obtain stems](#terminology-contract)
- [Local model landscape](#open-source-and-local-model-landscape)
- [Input and source-project contracts](#input-format-contract)
- [Quality and bake-off](#quality-and-bake-off-contract)
- [TUI and Workbench experience](#tui-and-workbench-experience)
- [Phased delivery plan](#phased-delivery-plan)
- [Tests and open questions](#tests-required-by-implementation)

## Executive decision

Sunofriend should eventually accept either:

1. one authorised finished song file;
2. a folder of existing stems or multitracks; or
3. the built-in demo.

It should not hide full-mix separation inside the existing transcription
functions. Add a source-preparation programme before the stable conversion
pipeline:

```text
authorised source audio
        |
        v
canonical, immutable local audio asset
        |
        v
broad separator candidates
  vocals / drums / bass / other
        |
        v
optional role-specific refinement
  drums -> kick / snare / hats / toms / cymbals / other_kit
  vocals -> lead / backing
  other -> keys / guitars / strings / wind / residual
        |
        v
accepted active leaf stems
        |
        v
existing multi-method MIDI conversion
        |
        v
balanced MIDI-derived interpretation WAV and GarageBand ZIP
```

The first engineering increment should be **canonical multi-format import
plus a minimal source-project manifest**, not a model download. Import must
preserve the role, key, BPM, tuning, chord-document and filename context used
by today's pipeline. It must not replace named stems with anonymous
`source.wav` files and then ask legacy discovery to guess what they mean.

That bounded S1 source-preparation slice is now implemented. `source-doctor`
and `source-import` inspect and prepare one asset.
`source-import-folder` prepares 2–64 already-separated, synchronized parts as
one fresh canonical WAV project that existing Simple and Studio paths can
consume.

S2 now adds a canonical role registry and an append-only source graph with an
active-source frontier. Composite `drums` can use the existing mixed-kit MIDI
family classifier without pretending that narrower audio stems were created.
The first S3 increment added the strict backend-neutral request/result and
receipt contract. New receipts use `sunofriend.separation-run.v2`; canonical
v1 receipts remain readable.

The second S3 increment is an internal, dependency-free deterministic-fake
integration harness. It verifies the contract, evidence calculations and
failure cleanup without presenting fake separation as a product feature. It
has no CLI or TUI action, isolated worker, real backend, model installation,
checkpoint loading or finished-song route. There is still no full-mix
separator.

The third S3 increment adds the internal, dependency-free
`sunofriend.separation-acceptance-thresholds.v1` contract in
`separation_acceptance.py`. Its pure freeze step requires every policy section
and threshold explicitly, computes a self-hash and returns a deeply immutable
canonical projection. Its read-only loader accepts only bounded canonical
regular non-symlink JSON and revalidates that hash. A separate
`sunofriend.separation-hidden-evaluation-manifest.v1` verifier accepts the
complete frozen artifact, rehashes the private manifest, derives song, group
and unique song-role-pair coverage, and rejects both declared-song and
canonical-source overlap with the committed development split. The policy also
commits blind audition windows, random assignment, the withheld answer key,
level-matcher identity and exact statistical treatment without exposing those
private records. This slice publishes or registers no production profile,
consumes no hidden scores, returns no pass result and adds no
model/checkpoint, install, run, audio, CLI, registry or promotion operation.

The fourth S3 increment adds the internal, read-only
`sunofriend.separation-bakeoff-preparation.v1` contract in
`separation_bakeoff.py`. It reloads the complete canonical frozen acceptance
artifact, reverifies the complete hidden manifest and returns a deterministic,
canonical, deeply immutable redacted plan with status `prepared_not_run`. The
plan binds the profile identity and acceptance artifact, canonical-document,
hidden-manifest and split hashes; retains only aggregate group and
ground-truth-role coverage; and fixes the baseline-before-candidate arms,
roles proposed for promotion, downstream MIDI identities, evaluator, resource
classes and gate IDs. Every execution, result, score, private-data, selection,
promotion and default-changing effect is explicitly false. It contains no
song or source ID; no song, source, ground-truth, checkpoint or worker hash;
and no path, threshold value, score or private note. It adds no writer,
model/audio operation, CLI/TUI, registry, result, pass or promotion.

The fifth S3 increment adds the internal, read-only
`sunofriend.separation-backend-preflight.v1` contract in
`separation_backend_preflight.py`. It reverifies the complete acceptance,
hidden-manifest and preparation chain, then statically checks one frozen arm's
worker, dependency lock, checkpoint and installed backend package from the
trusted parent process. Package evidence covers every directory marker and
regular file in the recorded package and distribution-metadata trees,
including executable `.pth` startup code, empty directories and files absent
from `RECORD`; Git provenance is bound separately so private install paths
never enter the report. All measured files and inventoried directories are
rechecked immediately before the report is built. Symlinks, changing evidence,
duplicate package identities, scripts masquerading as native launchers and
malformed editable metadata fail closed. A clean arm is only
`verified_not_run`: the target interpreter is not executed, and its exact
identity, imports, dependencies, accelerator and offline behaviour remain
explicitly unprobed. The module starts no worker, imports no package code,
loads no checkpoint, reads no audio or result, writes no file and makes no
quality or promotion claim. It is not execution authorisation and has no
CLI/TUI action.

The sixth S3 increment adds the pure
`sunofriend.separation-worker-request.v1` and
`sunofriend.separation-worker-result.v1` contracts in
`separation_worker_contract.py`. The private request cross-binds the complete
frozen acceptance identity, verified preflight and backend-neutral separation
request, including the registered worker, dependency lock, runtime,
checkpoint, source, role set, settings and seed. The result retains only
path-free immutable input, output and enforcement evidence and cannot express
quality, ranking, preference, selection or promotion. Development isolation
cannot satisfy hidden acceptance: v1 accepts only `private_development` and
cannot represent `acceptance_ready`. The runtime launcher is separately
parent-owned, settings compare by canonical JSON type and local path aliases
fail closed. This pure boundary performs no I/O and starts no process; the
subprocess transport and real separator remain unimplemented.

The seventh S3 increment adds a pure measured-runtime artifact and an exact
non-spawning launch/lifecycle contract. The runtime artifact binds the full
bounded Python launcher and ancestor chain, native executable, virtual
environment configuration, installed package tree, worker and lockfile to
separate parent-owned request, preflight and measurement identities. It is
explicitly private-development and unregistered: it neither proves execution
nor closes replacement between measurement and exec, so remeasurement is
mandatory.

The launch plan revalidates that artifact and fixes exact argv, environment,
file-descriptor, isolation, process and staging policies without offering an
execution function. Its lifecycle consumes only parent/supervisor
observations, records handle acquisition before exec and handshake, and
requires any acquired process to be reaped before lease release. Path-free
terminal evidence cannot be mistaken for a successful separation:
`execution_finished_unvalidated` explicitly leaves worker-result validation,
post-input immutability, parent output verification, quarantine, publication,
acceptance and promotion false. No worker, model or audio ran in this
increment.

The eighth S3 increment adds the filesystem-facing, read-only parent
measurement in `separation_runtime_measurement.py`. It accepts only a
parent-issued exact request binding, walks the runtime launcher and complete
ancestor tree with no-follow read-only descriptors, requires an explicit
`include-system-site-packages = false`, and hashes the final executable,
`pyvenv.cfg`, worker, lockfile and a bounded, descriptor-relative
`site-packages` tree. Immediate remeasurement rejects changed bytes or
identities. Stable ancestor evidence uses device, inode and mode so unrelated
sibling activity does not invalidate a long measurement; actual runtime and
package-tree content retains full mutation checks. Cross-device descendants,
hardlinks, symlinks, unsafe aliases, devices, sockets and resource-bound
overruns fail closed.

This remains measurement, not execution authorisation. The launch plan uses
`-S` so Python does not automatically process `site` or `.pth` startup code,
but the base standard library, `pyvenv` home and native dynamic-library closure
are not yet measured. Portable checks also cannot distinguish every
same-device APFS firmlink or mount alias. The module makes no network API
calls, but a caller must still avoid network-mounted runtime paths. No process,
model, checkpoint or audio ran.

The ninth S3 increment adds pure checkpoint-policy and execution-admission
records in `separation_checkpoint_policy.py` and
`separation_execution_admission.py`. They accept only synthetic, reported,
private-local evidence and always return `blocked`/`not_run`; they are not
trusted evidence, runner authority or worker-start permission. The exact
pinned HTDemucs checkpoint SHA-256
`8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4`
is classified by code as an executable PyTorch pickle model package,
independent of a caller's declared format. Its separate checkpoint terms and
allowed-use evidence remain unresolved. Unsafe-pickle exception metadata is
recordable for later design work but is categorically non-waivable in this
version.

Real execution, complete runtime closure, output-boundary and resource-limit
capabilities remain false; isolation and model-descendant provider registries
remain empty. The admission record reports all applicable blockers, including
missing trusted acceptance/preflight/request/launch cross-binding, runtime
closure, isolation, network denial and attempted-connection observation,
model-descendant and filesystem/input confinement, real transport, parent
output verification and quarantine, and hard resource enforcement. These
modules perform no filesystem, process, model, checkpoint-deserialization,
audio or network operation. They deliberately leave trusted byte-level
checkpoint inspection to a separate boundary.

The tenth S3 increment implements that internal static boundary in
`separation_checkpoint_inspection.py`. It accepts only a parent-issued exact
worker request and revalidates the trusted acceptance, preflight, separation
request and runtime artifact before opening the request-bound checkpoint.
Descriptor-relative, no-follow path traversal rejects aliases, hardlinks,
special files and changing ancestor attachments. Reads are bounded, the exact
checkpoint hash and size must match, and cleanup attempts every descriptor
even after an error.

A manual parser validates the narrow stored Torch ZIP layout before the
standard ZIP reader sees it: byte-zero local header, exact central/local
agreement, signed data descriptors, 64-byte payload alignment, canonical
single-root names, contiguous decimal tensor members and either an ordinary
EOCD or the exact consistent redundant ZIP64 terminal observed locally. Only
`data.pkl` is read through ZIP CRC verification; all tensor CRCs are not
recomputed, while the exact whole-file hash still binds the registered file.
`pickletools` walks bounded opcodes without deserializing. The registered
84,141,911-byte HTDemucs hash and its exact 18,523-opcode/global profile are
classified as a Torch ZIP pickle model package; all generic or state-dict-like
profiles remain `unknown`.

The result is immutable, path-free, private-development evidence with every
load, execution, network-API, audio, write, selection, publication, acceptance
and promotion effect false. It cannot prove filesystem-mount locality and its
open descriptor is not carried into a loader, so path-to-loader TOCTOU remains
unresolved. This is not a runner, and real execution remains false.

The eleventh S3 increment adds
`sunofriend.separation-execution-admission-binding.v2` as a new pure wrapper;
the existing v1 admission and launch schemas remain unchanged. It rebuilds the
complete canonical v1 admission and validates the checkpoint inspection
against a separately retained exact parent object. Requiring candidate and
trusted inspection object identity prevents a caller from changing static
classification evidence, rehashing it and copying the genuine record's
private token/request into a forged exact-class object.

The wrapper binds admission, policy, inspection, classification, worker,
preflight, acceptance and checkpoint hashes through a fixed mapping between
the inspection and checkpoint-policy container vocabularies. It does not
upgrade the rest of the synthetic evidence: terms, loader, runtime closure,
isolation, output and resource claims remain untrusted. Every v1 blocker is
retained, and the wrapper adds explicit descriptor-not-carried,
path-to-loader-TOCTOU and static-inspection-not-load-authority blockers. It
performs no I/O and every capability/effect is false.

The twelfth S3 increment adds a parent-only live checkpoint-descriptor lease.
It reopens the request-bound checkpoint through the bounded inspector,
reparses and rehashes that exact descriptor, requires equality with the
separately retained trusted inspection, closes every ancestor descriptor and
retains one non-inheritable read-only leaf descriptor at offset zero. The
opaque handle is non-copyable and non-serializable; the raw descriptor stays
inside bounded weak-registry state.

Recheck never reopens the pathname. It verifies the same descriptor's identity
before and after a complete request-bound hash and terminalizes on pathname
replacement, in-place mutation, inheritance, ownership loss or parent-PID
mismatch. Terminalization attempts closure once and records integrity
separately from cleanup; explicit close is idempotent and an unconfirmed close
is not retried. Garbage-collection cleanup is best effort, and the returned
observation is historical rather than liveness authority.

This slice does not add FD 5, a loader, worker protocol, model import,
deserialization or real execution. A read-only descriptor prevents writes
through that descriptor but does not make the inode immutable or prevent
another writer from changing it after the last hash. This established
requirements for a path-free worker request, one exclusive lease reservation,
atomic FD 5 installation under the same lease lock, child-side pre/post
identity and hash evidence, and all existing executable-pickle and
immutable-backing blockers.

The thirteenth S3 increment adds the internal
`sunofriend.separation-worker-request.v2` design-evidence record in
`_separation_checkpoint_transport_records.py`, with pure value validation in
`_separation_worker_request_v2_values.py`. It accepts expected values from a
future facade, not trusted live objects, and produces one bounded, canonical,
deeply immutable, path-free record. The accepted domain is deliberately the
stricter admitted and inspected V1 subset; a validating V1-to-V2 facade is not
yet implemented, so the record does not prove the provenance of its expected
inputs. Sixteen binding fields retain the earlier
worker, acceptance, preflight, separation, allowlist, admission, inspection,
classification, lease, checkpoint and runtime evidence hashes and sizes. The
logical request retains the complete verified preflight projection,
source/checkpoint/worker/runtime/lock identities, canonical role set,
type-aware settings, seed and fixed private-development isolation policy.

Output slots are derived from roles rather than paths. Descriptor rows 3, 4
and 5 describe only logical purpose, direction and access; raw descriptors,
path fields, URLs and path-like strings are rejected. Ordinary model settings
may still use the exact generic names `fd` or `descriptor`; transport-shaped
names such as `checkpoint_fd` and `raw_fd` remain forbidden. Canonical comparisons reject
type substitutions, and JSON depth/item, checkpoint-size and
sealed-request-size limits are explicit.
Mandatory admission blockers are preserved alongside the undefined
source/output transport, missing worker protocol, unattempted FD 5
installation, missing child remeasurement, unproven immutable backing,
unauthorised executable-pickle loading and unsupported real execution.

This V2 schema is permanently blocked design evidence, not an executable child
request. Every capability and effect is false. It does not reserve the live
lease, install FD 5, define source/output transport, implement a worker
protocol, open a file, start a process, load a model or expose a CLI/TUI
feature. A future executable request must use a new schema.

The 29 July 2026 fourteenth S3 increment adds a private zero-field reservation
token that binds one live retained lease to one exact V2 record, the exact V1
inspection request and the current observation backing. It cross-binds every
fact the lease can prove. The runtime-artifact document, execution-admission
and runtime-parent hashes remain sealed by the V2 record but unproven by the
lease. Reserve and release remeasure under the lease lock. Healthy close
refuses while reserved; integrity or ownership failures terminalize once. The
reservation exposes and installs no FD 5, starts no process, imports or loads
no model, and adds no user-facing separation. V1 schemas, hashes and APIs are
unchanged. The next work remains the blocked launch V2 and atomic FD 5
installation design.

The 29 July 2026 fifteenth S3 increment changes structure only. Descriptor-only
`fstat`, `pread`, `lseek` and owned-close helpers moved to
`_separation_checkpoint_descriptor_io.py`; pure acquisition-evidence
derivation moved to `_separation_checkpoint_lease_records.py`. The live lease
facade fell from 884 to 793 lines without moving its locks, weak registries,
state transitions or finalizer. Public V1 and reservation types, signatures,
`__all__`, schemas, hashes and behaviour remain unchanged. This maintainability
split creates no usable separator, execution authority or user-facing
capability.

The 29 July 2026 sixteenth S3 increment adds the internal
`sunofriend.separation-launch-plan.v2` as permanently blocked design evidence.
The lease facade issues it only under the existing lock after checking the
exact live reservation, its exact V2 request, owner and a full checkpoint
remeasurement. The immutable path-free record seals all 16 V2 bindings while
marking execution admission, runtime artifact and runtime-parent measurements
as unproven by the lease. It retains every inherited blocker and adds the
missing atomic FD 5 installation, child identity/hash handshake and runtime
authority blockers.

Logical FD 3, 4 and 5 rows and a future child-creation sequence are now
specified, but no descriptor is exposed or installed and parent FD 5 is not
changed. The serialized construction conditions are requirements, not proof
that the private facade checked them. The record cannot establish live
reservation authority, immutable checkpoint backing or safe offset ownership:
a child duplicate would share the retained descriptor's open-file description.
The future sequence also requires FD 5 to become non-inheritable immediately
after the one intended exec. Every capability and effect is false. There is
still no argv, source/output transport, worker protocol, process, loader,
model operation or user-facing separation. A fake-worker transport must
introduce new executable request and launch schemas rather than enabling V2.

The 30 July 2026 seventeenth S3 increment adds private, fake-only request,
launch and worker-result records. They cross-bind V2 and blocked launch V2 for
historical continuity, carry a 64-hex run identifier and describe only a
code-owned two-frame PCM24 fixture. Request and launch records are
path-free, deeply immutable and explicitly not live authority. Their
execution-support and permission flags are false. Nonce shape does not prove
parent-owned freshness or single use. Real separation, source audio,
checkpoint deserialization, model import, inference, acceptance, selection
and publication remain false or forbidden.

The fake launch record makes the platform gap explicit. Python's macOS
`os.posix_spawn` surface cannot prove closure of unrelated inheritable
descriptors and exposes no close-on-exec-default flag. The record therefore
requires an audited native close-all launcher, says it is not implemented,
keeps worker start blocked and records child-only FD mapping, exact pre-exec
checkpoint remeasurement, live lease authority and parent quarantine
verification as unresolved blockers. It neither starts a process nor changes
V1 or V2. Fake request and launch V1 are permanently non-executable; an
actual fake executor requires a new launch schema.

The eighteenth S3 increment adds a separate process-free protocol boundary.
It canonically frames the exact fake request/launch envelope and fake result
with shared 64 KiB and 1 MiB total-frame limits, duplicate-field rejection,
bounded JSON depth and an exact run-nonce/hash handshake. Its parent observer
accepts only exact record objects plus read-only, non-inheritable directory
and output descriptors. It checks the exact observed entry set, owner-only
files, one link, distinct file identities, per-slot size, full SHA-256,
stable before/after identity and packed PCM24 RIFF geometry using
offset-independent reads.

That observer is one descriptor-pinned observation, not launch authority or a
terminal receipt. It does not prove that a directory was freshly created or
that ordinary files stay immutable after observation, and it never permits
selection or publication. FD 4 is the only worker-to-parent transport: its
bounded result contains the tiny fixture payloads. A future parent, not the
worker, must materialize those bytes in a fresh private quarantine and reopen
them for this observer. No output path or directory descriptor enters the
child. No subprocess, FD 5 installation, checkpoint load, model operation or
user-facing separator exists in either increment.

The nineteenth S3 increment adds the pure, private and permanently blocked
`sunofriend.separation-fake-launch-plan.v2` contract. It seals the exact fake
request and blocked-launch V1 hashes as historical inputs plus caller-supplied
native-launcher, runtime and fake-worker identity claims. It observes no path
or file, verifies no build and carries no live authority.

The contract fixes an isolated `-I -B -S` worker invocation, the exact
`LANG=C`, `LC_ALL=C`, `TZ=UTC` replacement environment, null standard streams
and a child-only source-to-scratch-to-3/4/5 action sequence with explicit
original and scratch closure. It requires Darwin close-all behavior but does
not invoke it. FDs 3/4/5 must cross the intended exec inheritable; first
worker code must make them non-inheritable before parsing or checkpoint
access. It also makes clear that isolated Python ignores configuration
environment variables, leaves hash randomisation enabled and cannot rely on
`PYTHONHASHSEED` for deterministic fixture output.

Process-group ownership, monotonic timeout, TERM/grace/KILL, exact reap,
nonterminal unreaped supervision, bounded error handling and parent-owned FD4
payload materialisation are declarative requirements. Existing fake envelope
and result V1 schemas do not bind the plan. Build provenance, artifact
remeasurement, nonce freshness/single use, exact live authority, executable
and worker-path TOCTOU closure, child mapping, lifecycle execution and terminal
verification remain blockers. The record starts no process and every
capability and effect remains false.

The twentieth S3 increment packages the reviewed macOS-only
`_separation_native_spawn_darwin.c` source without registering, compiling,
importing or calling it. Static tests pin its direct Darwin `posix_spawn`
surface, close-all/process-group/signal flags, fixed `-I -B -S` invocation,
exact three-variable environment, descriptor access and identity checks,
child-only collision-safe mapping, original/scratch closure, null standard
streams, parent `SIGCHLD` compatibility and post-spawn allocation-failure
kill/reap path. It contains no parent FD-table mutator.

At that twentieth-increment boundary, source review was not native execution
evidence: no binary, build receipt, code signature, extension import, canary
descriptor set, child, worker or terminal receipt existed. The next increment
therefore had to provenance-bind a private owner-only build and run
adversarial macOS canaries before the fake protocol could advance.

The 30 July 2026 twenty-first S3 increment adds an internal macOS-only builder.
It verifies the hash-pinned C source and build contract, measures the selected
Xcode tools, SDK, compiler-discovered header closure, compiled object and
explicit SDK `libSystem` linker input, then uses split Clang object compilation
and the measured Darwin linker directly. Every call writes a fresh owner-only
build, validates the thin host-architecture Mach-O bundle, deployment target,
linked dylib set, absence of RPATH, deterministic `LC_UUID` and strict ad-hoc
signature, and emits a canonical receipt without transient build paths. Two
fresh builds on the same measured host must have the same artifact hash and
UUID. The receipt explicitly does not claim to enumerate dynamic runtime
libraries used internally by Apple build tools. The builder does not import
the artifact, start a worker, model or audio operation, or request a network
resource.

A separate test-only macOS canary remeasures and imports that private artifact
inside an isolated harness. Across all six logical permutations of the exact
physical source FDs 3/4/5 and ten fixed representative layouts covering
ordinary low non-target descriptors, collisions with the launcher's first
scratch candidates, mixed 3/4/5 collisions and descriptors near the fixed
scan limit, the child observed exactly FDs 0–5. Unrelated low
and high inheritable descriptors were absent, and the parent descriptor
identities, access/inheritability state and offsets were unchanged after spawn
and reap.

The following ownership hardening removes the bare-PID handoff. The extension
allocates a private, nonconstructible child owner before `posix_spawn`, arms
that same object after success and returns it without another Python
allocation. It exposes no raw PID and cannot be copied or pickled. Its native
nonblocking exact wait caches the wait status before allocating a Python
result, rejects signalling after reap and poisons itself if another reaper
steals the child. A test-only blocking worker proves that dropping the last
live handle sends `SIGKILL` and exact-reaps the child while preserving the
parent descriptor table. A second adversarial canary externally steals the
reap and proves the poisoned handle cannot signal a possibly recycled PID or
group. An owner-process check prevents a fork-cloned destructor from acting,
but that branch is presently static rather than live proof.

This finite matrix is deliberately narrower than execution authority:
arbitrary source-FD values are not exhaustively live-proven; the harness
requires an outer
`close_fds=True, pass_fds=()` launch but cannot observe that policy from
inside; CPython startup prevents the worker from proving the spawn-time signal
reset and mask state; and extension-import, runtime-exec and worker-script path
TOCTOU are not eliminated. Emergency last-reference cleanup deliberately uses
a potentially blocking exact `waitpid` after `SIGKILL`; it is an
exception-safety backstop, not a bounded terminal receipt. The fixed canary
workers create no descendants, and the owner makes no numeric process-group
call after exact leader reap; generic descendant supervision is not claimed.
Parent `SIGCHLD` incompatibilities fail closed, but no standalone deterministic
fake transport worker, checkpoint lease transport, source audio, model,
terminal fake result or user-facing separator ran.

The following prepared-worker increment adds three isolated execution-era
modules without enabling a launch. A hash- and size-pinned, stdlib-only Darwin
worker makes FDs 3/4/5 non-inheritable as its first effectful module code,
accepts only the new V2 envelope magic, hashes but never deserializes FD 5,
creates no descendants and can emit only code-owned two-frame PCM24 payloads.
The prepared launch V3 record binds the exact historical V1 and permanently
blocked V2 hashes, pinned worker source and caller-supplied native build
receipt hash. It reports fixed-worker support but retains
`test_only_worker_start_permitted=false`,
`serialized_plan_is_execution_authority=false` and every real-separation
permission false. Worker Result V2 is complete-only, requires `PGID == PID`
and remains worker-report evidence rather than parent verification.

The process-free V2 protocol can validate the new request/result frames but
intentionally has no product admitted-envelope encoder, admission issuer,
descriptor operation or spawn surface. Tests alone synthesize envelope bytes
to exercise parsing. The next live increment must introduce one exact,
non-copyable, single-use admission under the live checkpoint lease and
reservation lock, then pass the lease-owned descriptor directly to the native
launcher. Until that exists, the fixed worker cannot be started by
Sunofriend. No fake terminal receipt, quarantine V2 verifier, model, source
audio or user-facing separation route exists.

The twenty-third S3 increment adds a private verified native-launcher session,
still without a spawn call. It makes one fresh provenance-checked Darwin
build, remeasures the extension immediately before and after import, verifies
the compiled source/build-contract identities and binds the exact built-in
entry point to the measured current Python executable and pinned fixed worker.
The session identity is parent-issued, opaque, non-copyable and
non-serializable; its observation is immutable, path-free and explicitly not
execution authority. A live macOS test proves the import and subsequent full
remeasurement while every process, checkpoint, model, audio, network and
publication effect stays false.

This closes the unmeasured extension-import gap for one fresh session, not the
runtime-exec or worker-script path race at a future spawn. The session module
deliberately contains no call to the native spawn method. Exact lease-bound
admission, FD 3/4 transport construction, locked FD 5 handoff, owned-child
supervision, Result V2 verification, quarantine and a parent terminal receipt
remain the next gate.

The twenty-fourth S3 increment adds a distinct, process-free Result V2
quarantine verifier. It first revalidates the exact historical request,
blocked launch records, prepared V3 plan and complete Result V2, then observes
an already-materialized owner-only tree entirely through a read-only directory
descriptor and one distinct read-only, non-inheritable descriptor per output.
It reuses only the low-level full-hash, descriptor/entry identity and PCM24
geometry checks beneath the historical V1 wrapper; it never presents V2
evidence as V1.

The path-free observation binds the V3 and Result V2 hashes, exact entry set,
file identities, bytes and geometry while keeping publication, selection,
acceptance and promotion false. It creates or modifies no file and cannot
prove that the worker executed, who created the tree or that ordinary files
stay immutable afterward. Result V2 remains worker-reported content until the
later parent receipt binds it to an exact owned-child lifecycle.
Exclusive parent materialization, the live worker, exact reap and a terminal
parent receipt therefore remain outstanding.

The first model execution increment should be a measured bake-off, not a hard-coded
winner. HTDemucs, BS-RoFormer, MelBand-RoFormer and other systems are
unverified candidates until one exact runtime/checkpoint pair has known terms,
a fixed hash, offline inference, supported-Mac measurements and downstream
MIDI evidence. Narrow drum and query-based models remain optional experiments
under the same rule.

## Why this is a separate programme

The current Sunofriend contract is honest and useful:

- production conversion reads synchronized top-level WAV stems;
- different analytical and AI transcription candidates remain separate;
- Simple mode can make an automatic unreviewed MIDI/WAV/ZIP result;
- Studio can compare evidence and record explicit choices; and
- model downloads and non-permissive checkpoints are optional and explicit.

Full-mix separation changes the evidence before transcription. A poor
separator can remove note attacks, move harmonics to the wrong stem or create
plausible-sounding material with the wrong timing. That would affect every
later candidate. The source-preparation boundary therefore needs its own
lineage, quality gates, licences, review and cache.

## What the repository already has

### Production boundary

Legacy production projects still use top-level lowercase `*.wav` discovery.
Prepared projects instead resolve their manifest-declared active source-graph
frontier, so an inactive parent, undeclared file or future refined child is
not silently mistaken for a production source. Metadata and an optional chord
document come from the prepared manifest before legacy filename inference.

The accepted S1 preparation boundary now provides:

- `source-doctor`, a read-only report over existing local FFmpeg/FFprobe
  binaries;
- `source-import SOURCE --out-dir FRESH_OUTPUT`, which executes by default;
- `source-import-folder SOURCE_FOLDER --out-dir FRESH_OUTPUT`, with separate
  read-only plan and execute invocations for 2–64 existing separated parts;
- the explicit read-only `source-import ... --plan` form;
- immutable original and deterministic PCM24 canonical assets;
- per-source receipts, `INPUT/source-folder-import.json` and
  `INPUT/source-project.json`;
- tested preservation of hash, role, key, BPM, tuning, chord-document and
  clock evidence without normalization, alignment correction, network access
  or installation; and
- direct compatibility of the prepared top-level canonical WAV files with
  existing Create, TUI and Workbench discovery.

Folder import does not recurse, separate a mix, shift, pad, stretch or
normalize files, prove a downbeat, or repair alignment. Missing recorded-origin
evidence requires explicit acknowledgement; concrete origin conflicts block
execution. Execution replans current inputs rather than replaying a stored
plan. `pads` is not accepted as an observed role because
production currently synthesizes pads from keys and has no observed-pads job.

The accepted S2 boundary now provides:

- one canonical role vocabulary and conservative set-valued filename
  inference;
- deterministic in-memory source-graph revision 1 for an unchanged prepared
  project, plus content-addressed append-only revisions when explicitly
  written;
- active-parent/active-child mutual exclusion and reversible parent
  retention;
- explicit composite semantics for `drums`, `vocals` and `other`;
- review-required composite-drum MIDI through the existing mixed-kit family
  classifier; and
- an explicit leaf-over-composite automatic-arrangement policy that retains
  the broad result for Studio and prevents doubled drum hits.

Composite-drum processing assigns one dominant family per detected onset, so
coincident layered hits can collapse. It creates MIDI family variants only,
not kick/snare/hat/tom/cymbal audio children. No current operation writes
refined audio nodes into the source graph.

### Reusable foundations

Sunofriend already provides:

- drum-family MIDI classification in `transcribe_drums.py`;
- leakage and uncertain-family evidence in `conversion.py`;
- source/MIDI evaluation in `evaluate.py`;
- AI candidate quality gates in `ai_quality.py`;
- note-level lineage and content-addressed receipts;
- local Workbench comparison and bounded playback; and
- an isolated AI environment containing PyTorch and Demucs 4.0.1.

The current Demucs cleanup experiment is not a production separator. It is
limited to a 60-second, 44.1 kHz CPU excerpt and emits one target plus a
residual. Its checkpoint is recorded as private evaluation because the
pretrained-weight terms were not sufficiently clear. It proves worker
isolation and provenance concepts, not public product readiness.

The 29 July 2026 installed-baseline audit found Demucs 4.0.1 and the official
`htdemucs` `955717e8` checkpoint already present locally. The checkpoint is
84,141,911 bytes and matches the pinned SHA-256
`8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4`.
This establishes byte identity, not permission or acceptance. The code's MIT
licence is recorded, but no separate pretrained-weight terms were found; the
training provenance is incomplete for deployment decisions; exact installed
package source-commit provenance is absent; and no OS-level deny-and-observe
offline run has passed. The installed pair is therefore a conditional
private-development candidate and a strict **no-go** for hidden evaluation,
promotion, redistribution or an automatic profile.

The same audit found `/usr/bin/sandbox-exec` on the development Mac, but its
local manual marks the mechanism deprecated and the current Codex execution
context cannot apply even a no-network profile. More importantly,
`sandbox-exec` does not expose a complete, independently verifiable stream of
denied connection attempts. Executable presence is not an isolation result.
A future provider must pass a no-op canary and report separately whether
network denial, attempted-connection observation and outside-write
confinement were each enforced.

## Terminology contract

The user-facing definitions are in [Stems](STEMS.md). The implementation must
preserve these distinctions:

| Term | Product meaning |
| --- | --- |
| Original asset | The exact file supplied by the user; immutable and hashed |
| Canonical asset | A deterministic decoded PCM representation; derived, not a replacement |
| Original multitrack | A discrete production track supplied by its owner or authorised source |
| Original stem | A grouped submix exported by the project owner |
| Estimated stem | A model output inferred from a mix or parent stem |
| Composite source | A part expected to contain multiple roles, such as drums or other |
| Leaf source | The currently active narrowest source selected for transcription |
| Complement/residual | Material not assigned to a target; not one instrument |
| Separation candidate | One immutable model result; never silently promoted |

The interface should say **estimated stem**, not “recovered original stem,”
when a model produced it.

## Ways users can obtain stems

### Best evidence: their own production

Synchronized original multitracks or DAW-exported stems retain the most note,
timing and timbre evidence. They should remain the preferred source.

### Authorised education and demonstration material

Sunofriend's demo is the safest first experience. For broader testing,
[Telefunken Live From The Lab](https://www.telefunken-elektroakustik.com/livefromthelab/)
offers labelled 24-bit/48 kHz WAV multitracks for stated home-studio and
educational use, while the
[Cambridge Music Technology library](https://cambridge-mt.com/ms2/mtk/)
indexes freely downloadable mixing-practice projects. Each project's terms
still govern reuse and publication.

### Commercial or cloud separation

The provider comparison and affiliate policy are maintained in
[Stems](STEMS.md). The main product conclusions are:

- Moises is technically relevant for detailed drum parts;
- LALAL.AI is the clearest genuine affiliate candidate, but its desktop app
  uses cloud processing by default; the current offline Lyra mode requires
  Pro and supports a smaller role set;
- BandLab and Fadr are approachable beginner experiments;
- Suno is convenient for material already authorised inside its workflow;
- RipX and Logic Pro are useful local commercial options; and
- no provider may be called best for Sunofriend until downstream tests support
  that claim.

Provider rankings must never depend on commission. No affiliate URL should be
published before programme acceptance and link-level disclosure.

## Open-source and local model landscape

Code licence, checkpoint licence and training-data provenance are separate
facts. An MIT inference repository does not make every downloaded checkpoint
commercially redistributable.

### Broad fixed-role separation

| Candidate | Outputs and evidence | Mac position | Licence/provenance position | Programme position |
| --- | --- | --- | --- | --- |
| [Demucs / HTDemucs](https://github.com/facebookresearch/demucs) | Stable four-source vocabulary: drums, bass, vocals, other. Experimental `htdemucs_6s` adds guitar and piano, but the official README warns that piano has substantial bleed. | Original project supports MPS but is no longer actively maintained. [Demucs-MLX](https://github.com/ssmall256/demucs-mlx) and [demucs-infer](https://github.com/openmirlab/demucs-infer) are possible adapters to test. Demucs-MLX's first-use download behaviour must be disabled or preinstalled and then verified offline. | Code is MIT; checkpoint terms and hashes still require an explicit registry entry. | Unverified broad-baseline candidate. |
| [BS-RoFormer architecture](https://arxiv.org/abs/2309.02612) | Strong four-stem research result, particularly relevant to the bass problem. | PyTorch and emerging MLX adapters exist; no runtime/checkpoint pair is selected here. | Architecture/runtime licences do not establish community-checkpoint rights. | Unverified quality candidate, especially for bass. |
| [MelBand-RoFormer architecture](https://arxiv.org/abs/2310.01809) | Competitive vocals, drums and other; specialised checkpoints could complement a broad model. | Active MLX and PyTorch ecosystems exist; no runtime/checkpoint pair is selected here. | Every checkpoint needs a separate licence, hash and provenance record. | Unverified role-specific candidate. |
| [SCNet](https://github.com/starrytong/SCNet) | Official sparse-compression four-stem model with released MUSDB checkpoint. | PyTorch path; Apple runtime and memory need measurement. | Official code is MIT; record the release asset terms/hash separately. | Useful independent architecture in the bake-off. |
| [Spleeter](https://github.com/deezer/spleeter) | Two, four and five source configurations; five-source adds piano. | Older TensorFlow stack has known Apple-silicon friction. | MIT code, last formal release in 2021. | Historical speed/reproducibility control only. |
| [Open-Unmix](https://github.com/sigsep/open-unmix-pytorch) | Established four-stem reference implementation. | Generic PyTorch CPU/GPU rather than a first-class current Mac route. | MIT code; default UMXL weights are CC BY-NC-SA 4.0. | Non-commercial reference baseline, not public default. |

The active
[Music Source Separation Training](https://github.com/ZFTurbo/Music-Source-Separation-Training)
repository supports RoFormer, MDX23C, Demucs, BandIt, SCNet and other
architectures. It is a valuable bake-off framework, but its repository licence
must not be projected onto community weights.

The same rule applies to
[python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator)
and [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui):
they are useful model runners and comparison tools, not one uniformly licensed
model.

### Wide-taxonomy models

Reports of an MVSep “Mega 53 Stems” BS-RoFormer release describe roles including
lead/backing vocals, drum families, keys, piano, synth, guitars, strings,
brass and wind. It is attractive because its vocabulary resembles
Sunofriend's desired role graph, but it is not a safe default:

- this research has not established a stable primary model-card or release
  URL, exact checkpoint hash or licence;
- the release guidance expects high GPU memory;
- many output categories overlap and do not sum cleanly to the source;
- an Apple runtime has not yet been proven for the supported contract;
- each role needs its own accuracy evidence; and
- the checkpoint licence/provenance requires explicit confirmation.

Treat it as an **unverified lead**, not a runnable candidate, until those
missing facts are recorded.

### Narrow drum separation

The desired hierarchy is:

```text
finished mix -> broad drums -> kick / snare / hats / toms / cymbals / other
```

Relevant candidates include:

- the MDX23C DrumSep configuration described in the
  [Music Source Separation Training release discussion](https://github.com/ZFTurbo/Music-Source-Separation-Training/issues/1),
  which targets kick, snare, toms, hi-hat, ride and crash;
- [LarsNet](https://github.com/polimi-ispl/larsnet), which targets kick,
  snare, toms, hi-hat and cymbals from solo drum mixtures; and
- a wide-taxonomy direct separator as a comparison.

LarsNet's weights are non-commercial and its training domain is largely
synthetic acoustic kits, so electronic and AI-generated drums are a material
domain-shift risk. The original DrumSep provenance is incomplete enough that
Sunofriend must not auto-download it until the archival licence and checksum
are established.

The lower-risk composite route is now implemented: public `drums` uses
Sunofriend's existing mixed-kit MIDI family classifier. It produces
review-required family-aware drum MIDI without a second separator or any child
audio stems. It remains the control for evaluating whether a later dedicated
drum separator actually improves downstream MIDI.

### Query-based separation

Query models are promising when a broad stem contains two bass timbres,
several keyboards, lead plus backing vocals, or miscellaneous `other` sounds.

| Candidate | Query | Strength | Current constraint |
| --- | --- | --- | --- |
| [AudioSep](https://github.com/Audio-AGI/AudioSep) | Text | Open-domain target plus broad zero-shot instrument separation; chunk inference available | Processes at 32 kHz; official path documents CUDA/CPU rather than MPS; checkpoint terms need separate verification |
| [Banquet](https://github.com/kwatcharasupat/query-bandit) | Example audio | Small stem-agnostic decoder; paper reports useful guitar, piano and long-tail instrument results | Official workflow is CUDA-centric and needs a suitable clean query example |
| [SAM Audio](https://github.com/facebookresearch/sam-audio) | Text, time span or visual prompt | Returns target plus residual and can generate/rerank several candidates; prompts could include “buzzing synth bass” or “pluck bass” | Python 3.11+, large memory footprint, CUDA recommended, gated weights and a custom SAM licence requiring review |
| [CLIPSep](https://github.com/sony/CLIPSep) | Text | Permissive research implementation for text-queried sound separation | Older general audio path; exact pretrained release terms and hash remain unverified |

These are **advanced refinement challengers**, not the first integration.
Semantic confidence can be high while note timing is damaged. A query result
must be compared against the unchanged parent and residual.

## Input-format contract

### User promise

The public promise must name tested **container-plus-codec combinations**,
not infer quality from an extension. The initial portable baseline should be:

- WAV containing integer PCM16, PCM24 or PCM32;
- AIFF containing integer PCM16, PCM24 or PCM32;
- FLAC;
- M4A containing ALAC or AAC;
- MP3; and
- Ogg containing Vorbis or Opus.

AIFC, CAF and WMA are conditional capabilities because those containers can
hold several codecs and support depends on the installed decoder. Likewise,
an `.m4a` suffix alone does not say whether the audio is lossless ALAC or
lossy AAC. The receipt must classify the stream only after `ffprobe`.

Use `ffprobe` and FFmpeg to validate the actual container, stream and codec,
not just the filename suffix. FFmpeg documents that available demuxers depend
on the build and exposes them through `-formats`; its
[format documentation](https://ffmpeg.org/ffmpeg-formats.html) is therefore a
better capability source than a hard-coded promise that “everything” works.

FFmpeg is not installed by the current newcomer bootstrap. Before import,
`source-doctor` reports the exact existing local `ffmpeg`/`ffprobe` binaries,
versions, hashes and declared capability policy without writing files.
Installation remains a separately planned and approved step; Sunofriend does
not silently install or substitute a decoder.

The importer should reject:

- DRM-protected or encrypted files;
- files without exactly one selected audio stream unless the user chooses one;
- unsupported channel layouts or corrupt/non-finite decoded audio;
- remote URLs in the local source path; and
- symbolic-link inputs in the first release; and
- video containers in the initial release, even if FFmpeg could decode their
  audio.

Video/audio extraction can be a later explicit feature with its own rights and
stream-selection UX.

Initial safety defaults reject a file larger than 2 GiB, audio longer than 30
minutes, more than eight channels, or a projected canonical asset larger than
8 GiB. Required free space includes the preserved original and chord
evidence, twice the projected decoded size, and 1 GiB of headroom. FFmpeg is
also given explicit duration and file-size output limits. Probing is bounded
to 30 seconds and decoding to the greater of 120 seconds or four times
declared duration, capped at 30 minutes. These limits may become explicit
advanced settings, but must remain recorded in the receipt and must never
expand silently.

The S1 threat model is a trusted local, single-user filesystem namespace.
Planning and execution reject collisions and detected path/symlink drift, and
publication is descriptor-anchored and no-replace. Defending against a hostile
process continually renaming ancestors while FFmpeg is actively reading and
writing would require descriptor-relative handling throughout the decoder and
is outside this local preparation boundary.

### Canonical representation

For every input:

1. preserve the original bytes unchanged;
2. compute an original SHA-256;
3. inspect with `ffprobe`;
4. decode deterministically to a canonical local PCM24 integer WAV without
   loudness normalization, because current Sunofriend readers do not all
   interpret float32 WAV correctly;
5. preserve sample rate and channel layout when the canonical contract allows;
6. compute canonical hash and audio geometry;
7. create model-specific resampled derivatives separately; and
8. record the decoder binary, version and exact arguments; and
9. create a minimal source-project manifest that preserves the original role,
   key, BPM, tuning, chord-document and filename context before legacy
   conversion discovers the canonical WAV.

Float32 can become a later canonical option only after every production,
Workbench and evaluation consumer has a tested float path.

The clock contract records the container start time, stream time base, codec
delay/priming, skip-sample metadata, decoder padding, first retained sample
and exact decoded frame count. The implementation reads bounded first and
tail packet windows because MP3 and AAC priming is not reliably present in
stream-level metadata. When importing several stems, compare their decoded
origins and lengths before claiming alignment. Equal duration alone is not
proof that MP3 or AAC files start on the same musical sample.

The canonical representation should be a processing asset, not a user-facing
claim that an MP3 became lossless. Lossy input remains lossy evidence after
decoding.

### Implemented initial receipt

```json
{
  "schema": "sunofriend.source-import.v1",
  "source_id": "sha256:...",
  "original": {
    "name": "song.m4a",
    "path": "INPUT/original/song.m4a",
    "bytes": 123456,
    "sha256": "...",
    "container": "mov,mp4,m4a",
    "codec": "alac",
    "sample_rate": 48000,
    "channels": 2
  },
  "canonical": {
    "path": "INPUT/canonical/song.wav",
    "sha256": "...",
    "sample_format": "pcm_s24le",
    "sample_width_bytes": 3,
    "sample_rate": 48000,
    "channels": 2,
    "frames": 12345678
  },
  "clock": {
    "format_start_time_seconds": 0,
    "stream_start_time_seconds": 0,
    "first_retained_source_sample": 0,
    "decoder_padding_samples": 0,
    "decoded_frame_count": 12345678
  },
  "decoder": {
    "name": "ffmpeg",
    "ffmpeg": {
      "path": "/local/path/to/ffmpeg",
      "sha256": "...",
      "version": "ffmpeg version ..."
    },
    "ffprobe": {
      "path": "/local/path/to/ffprobe",
      "sha256": "...",
      "version": "ffprobe version ..."
    },
    "arguments": ["...", "<SOURCE>", "...", "<CANONICAL>"],
    "network_protocols": ["file"],
    "normalization_filters": []
  },
  "limits": {
    "maximum_duration_seconds": 1800,
    "maximum_input_bytes": 2147483648
  },
  "normalised": false,
  "network_used": false
}
```

The one-asset implementation fixes and tests this
`sunofriend.source-import.v1` boundary, including `normalised: false`,
`network_used: false`, file-only decoder protocols, original/canonical hashes
and clock evidence. `source-import-folder` composes those per-source receipts
under `sunofriend.source-folder-import.v2` while continuing to validate
existing v1 receipts, compares available recorded origins and atomically
publishes one multi-source
`sunofriend.source-project.v1` manifest plus canonical top-level WAV stems.
The aggregate receipt records that audio was not normalized, alignment was not
corrected and any composite-drum precedence warning.

## Source-project and separation contracts

### Source part

S2 implements source identity and refinement lineage as a separate
`sunofriend.source-graph.v1` overlay. The stable
`INPUT/source-project.json` import manifest is not rewritten. Reading a
prepared project without a saved graph deterministically synthesizes the
original source nodes in memory and performs no write. Explicit graph updates
are content-addressed, append-only and use a compare-and-swap current pointer.

Together, the accepted import receipts, project manifest and graph record:

- stable source and asset identities;
- canonical role plus the originally declared role;
- optional parent node and immutable derivation evidence;
- `original`, `derived` or `view` origin;
- `composite` or `leaf` shape;
- an explicit active-node frontier;
- canonical audio and receipt references confined to the project;
- complete, partial or unknown refinement-group coverage plus an optional
  residual node; and
- the rights category supplied by the user without pretending Sunofriend
  verified it.

Backend/checkpoint provenance, output geometry and quality belong to the S3
separation receipt before a derived graph node can be accepted; the graph does
not fabricate those facts.

Suggested rights values are `owned`, `licensed`, `authorised_private_use`,
`statutory_exception`, `unknown` and `declined_to_state`. They are a user
declaration, not legal adjudication.

### Separation run

The first S3 increment implements an immutable, backend-neutral contract in
`separation_contract.py`. Its local `SeparationRequest` and
`SeparationResult` DTOs are separate from the shareable receipt. New receipts
use `sunofriend.separation-run.v2`, while strict validation retains canonical
v1 float-leakage receipts. Private source, checkpoint and work paths remain in
the local DTOs and cannot enter either receipt.

A complete receipt binds:

- source and canonical hashes;
- backend package/version/commit;
- model/checkpoint ID and SHA-256;
- code licence, weight licence and known training-data note;
- requested and actual roles;
- device, runtime, settings, seed and wall time;
- every target and residual hash;
- duration, sample rate, channels, peak, RMS and silence report;
- reconstruction and leakage evidence;
- network and filesystem side effects; and
- completion/cancellation state.

Only `complete` is loadable. `failed`, `cancelled` and `abandoned` are terminal,
non-loadable and expose no output or quality artifacts. Target and residual
roles, hashes and geometry must pair exactly; residuals use the explicit
persisted-source-minus-persisted-target definition. The quality report is
hash-bound, reconstruction is explicitly not treated as separation-accuracy
evidence, settings and measurements must be finite, and artifact paths must
be safe relative POSIX paths. The canonical receipt hash excludes only its
own `receipt_sha256` field.

The contract module remains a pure boundary: it imports no model or audio
runtime and performs no file I/O. `separation.py` and
`separation_quality.py` now exercise it through one exact
`FakeSeparationBackend` type. Arbitrary protocol implementations and fake
subclasses are rejected because an in-process Python backend cannot prove
network denial or filesystem confinement.

The controlled parent verifies the canonical source hash and geometry plus
the checkpoint hash before execution. It then independently inspects the
persisted PCM16/PCM24 target and residual bytes for hashes, geometry, levels,
silence, clipping and target-plus-residual reconstruction. Backend-supplied
quality claims are not trusted. The v2 receipt carries the complete canonical
run plan and its hash, cross-binds that plan to the receipt and derives
`run_id` from it. The plan includes the actual parent/backend module hash,
package/runtime identity and cache/backend policy rather than caller-supplied
claims.

Each run builds in fresh private sibling work and publication directories,
confines declared regular non-symlink artifacts, revalidates every terminal
byte and publishes the complete directory with one final rename. Failed,
cancelled or invalid runs similarly publish only a non-loadable path-free
receipt. Staging identity is pinned so cleanup refuses to recurse into a
replacement directory. Aggregate output, checkpoint size, file count and
free-space reserve are bounded; copying, zero-fill and hashing are chunked,
and wall time is measured with a monotonic clock.

The fake copies the source as each target and creates a silent residual. Its
arithmetic therefore closes, but that is integration evidence rather than
separation-accuracy evidence. It records leakage for every actual role as
structured `not_measured` evidence with null metric, score and reference, so
v2 quality is necessarily `review_required`. New v2 receipts still cannot
claim `passed`: the separate acceptance-thresholds contract pre-registers
policy only and is not wired to result evaluation or receipt promotion. There
is still no isolated real worker, backend adapter, model install flow or
cache. No model may download implicitly when those pieces are added.

### Nested refinement

Refinement creates children of a broad parent. The project must enforce:

- an active parent and any active child are mutually exclusive for final
  transcription;
- all children share the parent's clock and duration within a strict tolerance;
- the unchanged parent remains auditionable;
- residuals remain available;
- accepting children never deletes the parent; and
- a user can revert to the parent without recomputation.

### Two independent candidate axes

Separation candidates and MIDI candidates are different decisions:

```text
original source
├── separator A → bass estimate ─┬─ analytical MIDI
│                               ├─ AI MIDI
│                               └─ repaired MIDI
└── separator B → bass estimate ─┬─ analytical MIDI
                                ├─ AI MIDI
                                └─ repaired MIDI
```

The catalogue must preserve both levels of provenance and never flatten them
into one label or silently choose a separator before the existing
multi-method MIDI comparison. Source selection and MIDI selection need
separate review events. Bound the first implementation to at most five broad
separator candidates per source, two refinement levels and five MIDI
candidates per active leaf unless an explicit advanced plan raises the limit.
Regression tests must preserve blind labels, deterministic ordering, existing
review identities and legacy WAV candidate IDs.

The runtime implementation should generalise the existing `ai_runtime.py`,
`ai_cleanup.py`, Demucs worker/checkpoint-hash policy and the
`listening_master.py` pinned-executable pattern. Do not create a second model
registry or executable-discovery path that can drift from those controls.

## Quality and bake-off contract

Source-separation SDR alone does not answer Sunofriend's question. A stem can
sound pleasant but have smeared note attacks; another can sound noisy but
produce substantially more accurate MIDI.

### Test material

Use three evidence groups:

1. copyright-safe synthetic material with exact notes and clean component
   audio;
2. authorised original multitracks that can be mixed into known broad and
   narrow ground truth; and
3. private real songs for generalisation and GarageBand listening, never
   committed or uploaded.

Useful research datasets include:

- [Slakh2100](https://www.slakh.com/), which provides CC BY 4.0 synthesized
  multitracks and aligned MIDI;
- [MUSDB18-HQ](https://sigsep.github.io/datasets/musdb.html), an educational
  four-stem benchmark with per-track rights restrictions; and
- [MoisesDB](https://arxiv.org/abs/2307.15913), a two-level hierarchical
  240-track research dataset distributed under CC BY-NC-SA 4.0.

Only appropriately licensed subsets and usage profiles may enter automated
tests. MUSDB18-HQ is an academic/per-track-restricted evaluation source, not
an ordinary committed CI fixture.

### Technical gates

- Successful deterministic decode with finite samples.
- Exact or tolerance-bounded duration, clock and channel geometry.
- No unexplained clipping or silent target.
- Hashes revalidated before reuse.
- Target-plus-residual or summed-stem reconstruction error reported.
- Cancelled and partial output rejected.
- Warm-cache and fresh-process results distinguished.

Reconstruction error must not be described as separation accuracy: a model can
reconstruct the mix while allocating sounds to the wrong role.

### Separation and leakage evidence

- SI-SDR/SDR per role where ground truth exists.
- Cross-stem leakage and correlation matrix.
- Spectral holes, high-frequency loss and transient preservation.
- Silent-target false-positive rate.
- Role plausibility, such as pitched sustained energy in a drum-only output.
- Parent-versus-children reconstruction and duplicated energy.

### Downstream MIDI evidence

- Onset precision, recall and F1.
- Pitch-class, exact-pitch and octave accuracy.
- Note-duration and timing-error percentiles.
- Full-song drift and alignment.
- Drum family onset F1.
- Chroma and contour retention for bass, keys and vocals.
- Phrase recognition and human correction effort.

Compare MIDI made from:

1. the known clean source;
2. each separator estimate;
3. the unchanged full mix or broad parent where applicable; and
4. each refinement candidate.

### Product evidence

- Blind, level-matched source/stem/MIDI listening.
- Usefulness of the final balanced Sunofriend interpretation.
- GarageBand import and A/B checks.
- Installation success on supported Mac classes.
- Model size, wall time, peak unified memory and energy/thermal behaviour.
- Licence and provenance completeness.

A model can win one role and lose another. Promotion remains role-specific.

### Pre-registered acceptance

Before running hidden evaluation, S3 must commit a
`sunofriend.separation-acceptance-thresholds.v1` artifact. At minimum:

- use at least 12 songs across acoustic, electronic/AI-generated and mixed
  production, with at least four songs in each group;
- require at least eight ground-truth examples for every role proposed for
  promotion;
- name the comparison baseline and exact required deltas for onset F1,
  exact-pitch/octave accuracy, median and 95th-percentile timing error;
- set a catastrophic per-song regression limit, not only a median target;
- set wall-time and peak-memory ceilings for every declared supported Mac,
  including one 16 GiB Apple-silicon class;
- require a zero-network offline inference test after explicit model
  installation; and
- define the blind level-matched human non-inferiority and preference rule.

The internal v1 contract now validates and freezes that policy in memory and
can load a separately persisted canonical artifact read-only. Its
hidden-manifest verifier derives coverage and split identity from canonical
manifest bytes, checks both song-identity and canonical-source exclusion, and
requires distinct per-role ground-truth evidence plus per-song rights evidence
before counting coverage. It matches licence commitments to the complete
frozen artifact and also requires hash commitments for private audition
windows, assignment and the answer key, plus exact tie, cannot-tell,
non-inferiority and preference policies. No production threshold artifact or
hidden evaluation result is included in this slice.

The separate bake-off preparation boundary now reloads that complete frozen
artifact and reverifies the complete hidden manifest before deriving its
redacted `prepared_not_run` plan. Validation and loading repeat both checks;
the plan is not self-sufficient evidence. It exposes only the bound document
hashes, aggregate coverage and exact public orchestration IDs, never the
private evaluation units, threshold values, scores or paths, and every
execution, result, selection, promotion and default effect remains false.

The separate backend preflight then reverifies both frozen inputs and that
redacted preparation before inspecting one exact arm. Its path-free report
contains only hashes, public identities, fixed check states, safe blocker codes
and explicit limitations. `verified_not_run` means the registered static
artifacts matched at that instant. It does not mean the runtime imported, the
checkpoint loaded, the accelerator worked, the network gate passed or the
separator produced useful audio.

No threshold may be filled in after hidden results are seen. Missing sample
coverage, missing licence/hash evidence, a blank threshold or a failed gate
means **no promotion**. Development data may be used to calibrate the numbers,
but the frozen artifact and hidden run must remain separate.

## Recommended initial bake-off

### Broad candidates

1. A maintained Demucs/HTDemucs Apple runtime and exact four-stem checkpoint.
2. One fixed four-stem BS-RoFormer runtime/checkpoint pair.
3. One fixed MelBand-RoFormer role-specific pair.
4. SCNet as an independent architecture if it runs within the supported Mac
   memory envelope.
5. Spleeter or Open-Unmix only as historical controls.

### Narrow candidates

1. Existing mixed-kit MIDI classifier on a composite drums stem.
2. MDX23C DrumSep only after licence and provenance recovery.
3. LarsNet in an explicitly non-commercial research profile.
4. Direct wide-taxonomy separation as a capable-hardware challenger.
5. Query-based target/residual models for compound bass, keys, vocals and
   `other`, never as automatic defaults in the first release.

### Decision rule

No single average score selects the winner. A default must:

- satisfy technical and licence gates;
- satisfy the frozen role-specific MIDI improvement and non-regression
  thresholds;
- avoid a material regression in timing/alignment;
- fit the supported Mac runtime envelope;
- produce an understandable residual and lineage; and
- pass level-matched human listening for the MIDI interpretation.

If no candidate meets the rule, Sunofriend should keep provider guidance and
existing-stem input rather than ship a misleading local separator.

## TUI and Workbench experience

### First screen

The beginner route should ask:

```text
What do you have?

[ A finished song file ]
[ A folder of stems or multitracks ]
[ Nothing yet — try the demo ]
```

For a finished file, show before any installation:

- local or cloud processing;
- model name and licence profile;
- expected model download;
- estimated time and disk/memory needs;
- planned broad roles;
- whether optional refinement will follow; and
- exact network and filesystem changes.

### Studio review

Studio should show:

- source, broad stems and refined children as one lineage tree;
- synchronized solo/mute and level-matched audition;
- target and residual together;
- activity, leakage and reconstruction warnings;
- active-leaf selection;
- separator provenance and licence;
- downstream MIDI comparison; and
- a reversible “use broad parent” choice.

The Workbench should never silently choose children because they are narrower.

### Simple mode

One-action finished-song processing comes last. It should use only accepted,
whitelisted backend/checkpoint pairs and publish:

```text
RUN/
├── INPUT/
│   ├── original/
│   ├── canonical/
│   └── source-import.json
├── STEMS/
│   ├── broad/
│   ├── refined/
│   └── separation-runs/
├── CONVERSION/
└── AUTOMATIC-SONG/
    ├── MIDI/
    ├── AUDIO/balanced-midi-song-interpretation.wav
    └── sunofriend-automatic-midi-and-wav.zip
```

The output must be labelled automatic, estimated and unreviewed.

## Privacy, security and licensing

- Local remains the default. No automatic command uploads audio.
- Remote providers are links or explicit adapters, never silent fallbacks.
- Model installation is a separate, approved action.
- Inference cannot download weights.
- Only checksum-whitelisted weights can enter an automatic profile.
- Pickled checkpoints require a trusted-source policy and ideally a converted
  safe tensor format.
- Code, runtime, weight and dataset licences are recorded separately.
- Gated, non-commercial and custom-licensed weights are never bundled into the
  Apache-2.0 package.
- Original audio, stems and private review stay ignored by Git.
- Logs and path-free public receipts must not expose titles or user paths.
- Affiliate attribution is separate from technical metrics and selection.
- A future compensated provider link must retain an ordinary alternative, be
  labelled beside the link, carry a clear disclosure before engagement and
  use `rel="sponsored noreferrer"` on the public site.

## Phased delivery plan

This is a parallel **Source Access programme**. It does not renumber the
existing transcription phases.

### S0 — Research and honest documentation

Status: **repository research complete; public-site delivery tracked
separately**

- Publish stem definitions, provider choices and affiliate policy.
- Audit current format and role assumptions.
- Record the model landscape and define the initial bake-off.
- Publish a plain-language `/stems/` page on `sunofriend.com`, with a stable
  `/glossary/` alias or anchor and agent-readable links/metadata.
- Keep the skill and website statement “Sunofriend does not yet separate a
  full mix” until implementation is genuinely accepted.

### S1 — Canonical multi-format import and minimal manifest

Status: **accepted**

- [x] Add a central tested suffix/container/codec capability policy.
- [x] Add the explicit read-only FFmpeg capability doctor.
- [x] Implement bounded `ffprobe` validation and deterministic FFmpeg decode.
- [x] Preserve original and canonical hashes, geometry and clock metadata.
- [x] Write minimal source-import and source-project manifests preserving
  role, key, BPM, tuning, chord-document and original filename context.
- [x] Keep planning read-only and execution local, fresh-output-only,
  no-network and no-install.
- [x] Reject mixed audio/video containers, record lossy packet-edge timing,
  hard-bound decoder output and publish without replacing a raced destination.
- [x] Orchestrate several synchronized source parts and compare decoded
  origins before claiming alignment.
- [x] Make existing WAV-stem behaviour a regression golden across every
  production surface.
- [x] Integrate prepared projects with TUI and Workbench catalogue/timeline
  paths without changing legacy candidate identities.

Likely modules:

- `source_import.py`
- `audio_formats.py`
- `source_receipt.py`
- `source_project.py`
- `source_folder_import.py`
- `project_audio_inputs.py`

### S2 — Source graph and composite roles

Status: **accepted**

- [x] Add a separate versioned parent/child lineage overlay without rewriting
  the minimal import manifest.
- [x] Centralise role inference and role policy.
- [x] Add composite `drums`, `vocals` and `other` semantics.
- [x] Route composite drums through the existing family-aware MIDI classifier
  as review-required MIDI without creating audio children.
- [x] Enforce parent/child active-frontier exclusivity and reversible parent
  retention.
- [x] Prevent automatic doubled drums by preferring viable explicit family
  sources while preserving the broad candidate for Studio review.

Likely modules:

- `source_roles.py`
- `source_lineage.py`

### S3 — Separation bake-off harness

Status: **contract, blocked-execution groundwork, a fresh private Darwin
build/provenance slice, test-only live descriptor-canary slice and private
verified-import session
implemented; deterministic fake transport, isolated real runner/backends and
bake-off execution not implemented**

- [x] Add a pure backend-neutral `SeparationBackend` contract plus immutable
  request/result DTOs and strict versioned separation-run receipts.
- [x] Add a controlled-fake-only parent harness with private staging,
  parent-computed WAV/reconstruction evidence, review-required unmeasured
  leakage, plan-bound v2 receipts, atomic terminal-tree publication and
  fail-closed cleanup.
- [x] Add a pure explicit-threshold validator/freezer, read-only canonical
  loader and full-artifact-bound hidden-manifest verifier, with no bundled
  production profile, result or promotion behaviour.
- [x] Add a deterministic, read-only, redacted `prepared_not_run` bake-off
  plan that reverifies both complete frozen inputs, fixes the
  baseline-before-candidate orchestration and declares every effect false.
- [x] Add a deterministic, parent-only `verified_not_run`/`blocked` backend
  preflight that binds one frozen arm's worker, lock, checkpoint, installed
  package tree and Git provenance without executing the runtime or backend.
- [x] Audit the already-installed Demucs runtime/checkpoint and record why
  byte identity and private-development policy do not satisfy the strict
  licence, provenance or offline gates.
- [x] Add a strict private worker request/path-free result contract that
  cross-binds the frozen acceptance identity, static preflight and separation
  request without starting a process.
- [x] Bind the exact runtime launcher chain, ancestors, executable, virtual
  environment, installed package tree, worker and lockfile to separate
  parent-owned measurements without claiming execution or TOCTOU closure.
- [x] Add a pure exact launch plan and supervisor-owned lifecycle with no
  execution surface, separate handle/exec/handshake observations, mandatory
  reap-before-release and explicitly unvalidated cleanup receipts.
- [x] Add read-only parent runtime measurement and immediate remeasurement
  with descriptor-pinned ancestor/package traversal, stable ancestor identity,
  explicit system-site exclusion and bounded fail-closed reads.
- [x] Add pure blocked-only checkpoint and execution-admission records that
  distinguish reported formats from code-owned executable-pickle
  classification, preserve unresolved terms/use and non-waivable unsafe
  deserialization blockers, and report every unavailable
  isolation/runtime/confinement/transport/output/resource prerequisite
  without starting a worker.
- [x] Cross-bind a descriptor-pinned, bounded static checkpoint inspector to
  trusted acceptance, preflight, request and runtime-artifact authority
  without deserializing checkpoint bytes or authorizing a worker.
- [x] Bind the trusted static inspection into a separate blocked v2 admission
  wrapper while retaining every v1 blocker and every false capability.
- [x] Add a bounded parent-owned live descriptor lease that reparses,
  rehashes, retains and rechecks the same inspected checkpoint without
  exposing the raw descriptor or enabling a loader.
- [x] Add a pure, path-free, permanently blocked worker-request v2
  design-evidence record with logical descriptor requirements and no
  executable child request, lease reservation or FD 5 installation.
- [x] Add a private exact-object lease reservation that remeasures under lock
  without exposing or installing FD 5.
- [x] Separate descriptor-only I/O and pure lease-evidence derivation from the
  live lease facade without changing authority, records or behaviour.
- [x] Add blocked launch-plan v2 and atomic read-only FD 5 installation design
  without enabling a process or model.
- [x] Add separate fake-only request, blocked launch and worker-result schemas
  with a run nonce, fixed code-owned PCM24 fixture and no serialized execution
  authority.
- [x] Add bounded canonical request/result framing plus a process-free,
  descriptor-pinned parent quarantine observer without issuing a terminal
  receipt.
- [x] Add a pure, permanently blocked native fake-launch V2 contract that
  fixes artifact claims, invocation/environment policy, child-only scratch
  mapping, Darwin close-all and supervised-lifecycle requirements without
  starting a process.
- [x] Package a private macOS-only CPython launcher source with fixed
  invocation, child-only mapping and static no-fallback checks, while keeping
  it outside every public command.
- [x] Reproducibly build and provenance-bind the private Darwin launcher on
  the measured host, then canary-audit all six logical permutations of exact
  physical source FDs 3/4/5: the child sees only FDs 0–5, unrelated
  descriptors are closed, and the parent descriptor table, identities,
  relevant flags and offsets remain unchanged.
- [x] Extend the finite live descriptor matrix beyond exact physical source
  FDs 3/4/5 with ordinary low non-target, scratch-candidate collision, mixed
  target-collision and near-limit layouts while retaining a truthful
  `arbitrary values not proven` boundary.
- [x] Replace the bare-PID return with a preallocated, nonconstructible native
  exact-child owner; prove cached exact wait, post-reap signal rejection,
  last-reference kill/reap and external-reap poisoning without exposing raw
  PID authority.
- [x] Add the pinned, process-creation-free deterministic worker plus prepared
  launch V3, complete-only Result V2 and validation-only V2 framing while
  intentionally withholding any product admission issuer or request encoder.
- [x] Bind one fresh remeasured native build, imported extension, exact
  built-in entry point, current runtime and pinned worker into an opaque,
  path-free, non-executing private session.
- [x] Add a distinct Result V2 quarantine verifier that revalidates the exact
  record chain and observes an owner-only descriptor tree without creating
  files or adapting V2 evidence into the historical V1 wrapper.
- [ ] Remove or explicitly confine extension/runtime/worker path TOCTOU, and
  make the clean outer-supervisor and child signal-state boundaries
  independently observable.
- [ ] Prove a non-bypassable fail-closed subprocess transport with the
  deterministic fake worker, exact pre-exec remeasurement, validated worker
  result, timeout/reap evidence and parent-verified quarantined outputs before
  any real model is allowed to start.
- [ ] Generalise the existing AI runtime/checkpoint registry and isolate heavy
  runtimes in a separate worker environment.
- [ ] Require explicit checkpoint installation, hashes and licences in the
  real parent runner.
- [ ] Prove that inference makes no network request after installation.
- [ ] Generate and persist immutable broad candidate runs, residuals and
  quality reports.
- [ ] Measure downstream MIDI and Mac resource behaviour.

Likely modules:

- `separation_contract.py`
- `separation.py`
- `ai_separation_worker.py`
- `separation_quality.py`
- `separation_acceptance.py`
- `separation_bakeoff.py`
- `separation_backend_preflight.py`
- `separation_worker_contract.py`
- `separation_runtime_artifact.py`
- `separation_runtime_measurement.py`
- `separation_launch_contract.py`
- `separation_checkpoint_policy.py`
- `separation_execution_admission.py`
- `separation_checkpoint_inspection.py`
- `separation_execution_admission_binding.py`
- `separation_checkpoint_descriptor_lease.py`
- `_separation_checkpoint_descriptor_io.py`
- `_separation_checkpoint_lease_records.py`
- `_separation_checkpoint_fd5_reservation.py`
- `_separation_checkpoint_transport_records.py`
- `_separation_worker_request_v2_values.py`
- `_separation_checkpoint_launch_v2_records.py`
- `_separation_fake_transport_records.py`
- `_separation_fake_worker_protocol.py`
- `_separation_fake_launch_v2_records.py`
- `_separation_fake_execution_records.py`
- `_separation_fake_execution_protocol.py`
- `_separation_fake_execution_quarantine.py`
- `_separation_fake_worker_darwin.py`
- `_separation_native_build_darwin.py`
- `_separation_native_session_darwin.py`
- `_separation_native_spawn_darwin.c`

### S4 — Experimental broad separation in Studio

- Promote only accepted broad backend/checkpoint pairs.
- Add TUI `Finished song` planning and Studio operation.
- Add synchronized lineage review and reversible leaf activation.
- Keep Simple finished-song mode disabled.

### S5 — Hierarchical refinement

- Bake off drum sub-stem candidates.
- Evaluate lead/backing vocal and compound keys/bass refinements.
- Add query target/residual experiments only behind explicit advanced controls.
- Retain unchanged parents and measure compounding artefacts.

### S6 — One-action finished-song route

- Enable Simple mode only after cross-song, downstream MIDI and human
  acceptance gates pass.
- Produce stems, MIDI, interpretation WAV and ZIP with complete receipts.
- Update the Sunofriend skill and website capability declarations.

### S7 — Hosted and provider integrations

- Consider a thin authenticated control plane and queued workers, not a
  request-duration serverless fiction.
- Add explicit cloud consent, deletion, retention, rights declaration,
  metering and payment design.
- Add provider APIs only when privacy, terms and failure semantics are
  documented.

## Tests required by implementation

### Import

- Every promised format with tiny generated fixtures.
- Container/codec combinations and conditional capability reporting.
- Missing, mismatched and unapproved FFmpeg binaries.
- Extension/codec mismatch.
- corrupt, encrypted, multi-stream and unsupported input.
- size, duration, channel, disk, timeout, expansion and symlink limits.
- sample-rate, channel, duration, start-time, priming and padding preservation.
- cross-file decoded-origin and alignment checks.
- no normalization and immutable original.
- deterministic receipt and hash validation.
- PCM24 compatibility in every production and Workbench reader.

### Source project

- broad and leaf roles;
- minimal imported metadata survives canonical filenames;
- stable IDs and parent/child cycles rejected;
- parent/child mutual exclusion;
- rollback to parent;
- no duplicate MIDI from active parent plus child; and
- legacy WAV folder produces the same production plan.

### Separation

- backend protocol and worker failure;
- explicit model-missing result with no download;
- installed-model offline inference with network access denied;
- cancellation and partial-run cleanup;
- complete launcher/ancestor evidence, alias rejection and exact parent-bound
  runtime remeasurement;
- cancellation before spawn, between handle/exec/handshake and after process
  exit, with every acquired handle reaped before release;
- forged/reordered supervisor events, resigned launch policy and false
  result-success claims;
- static proof that the pure runtime/launch contracts expose no filesystem,
  process, network or dynamic-execution surface;
- cache key includes source, model, checkpoint and settings;
- duration/alignment/residual checks;
- non-finite, silent and clipped outputs;
- licence/profile enforcement; and
- no private paths in shareable receipts.

### Product

- TUI plan before side effects;
- Studio source/broad/refined lineage;
- level-matched audition;
- Simple disabled before acceptance;
- Workbench format/timeline consistency; and
- GarageBand pack excludes inactive parents.

## Open questions to answer with evidence

1. Does HTDemucs on Apple silicon beat a fixed BS-RoFormer checkpoint for
   downstream bass MIDI, not merely isolated-audio quality?
2. Does a dedicated drum separator improve family onset F1 over the existing
   mixed-kit MIDI classifier?
3. Is direct wide-taxonomy separation better than broad-then-refine for
   electronic and AI-generated music?
4. Can query separation split two timbres without damaging shared pitch and
   timing?
5. Which lossless/lossy formats materially change MIDI accuracy?
6. What Mac memory/runtime floor is realistic for a non-technical user?
7. Can a fully permissive checkpoint profile meet the quality bar, or must
   some higher-quality profiles remain opt-in/non-commercial?
8. Which provider outputs produce the best downstream MIDI per role?
9. How should a user describe private-use or licensed processing without
   Sunofriend making a legal determination?
10. When does a second separation pass do more harm than using a composite
    stem directly?

## Primary sources

- [Demucs](https://github.com/facebookresearch/demucs)
- [BS-RoFormer paper](https://arxiv.org/abs/2309.02612)
- [MelBand-RoFormer paper](https://arxiv.org/abs/2310.01809)
- [SCNet](https://github.com/starrytong/SCNet)
- [Spleeter](https://github.com/deezer/spleeter)
- [Open-Unmix](https://github.com/sigsep/open-unmix-pytorch)
- [Music Source Separation Training](https://github.com/ZFTurbo/Music-Source-Separation-Training)
- [AudioSep](https://github.com/Audio-AGI/AudioSep)
- [Banquet](https://github.com/kwatcharasupat/query-bandit)
- [SAM Audio](https://github.com/facebookresearch/sam-audio)
- [MoisesDB paper](https://arxiv.org/abs/2307.15913)
- [MUSDB18-HQ](https://sigsep.github.io/datasets/musdb.html)
- [Slakh2100](https://www.slakh.com/)
- [FFmpeg format documentation](https://ffmpeg.org/ffmpeg-formats.html)
- [ASA/CAP affiliate guidance](https://www.asa.org.uk/advice-online/affiliate-marketing.html)
- [FTC endorsement guidance](https://www.ftc.gov/business-guidance/resources/ftcs-endorsement-guides-what-people-are-asking)
