# Sunofriend AI roadmap

Status: Phase 1 complete; Phase 2 engineering, explicit three-unit human review
and final assembled-versus-automatic blind review complete, with one reviewed
opening-phrase win, no automatic win and two **neither** results, so the overall
programme preference criterion was not demonstrated; Phase 3 complete; Phase 4
fixed-MIDI review complete; Phase 5.1 private listening and the Phase 5.2
fresh-process, bounded reused-model, exact-result cache and beam-1/beam-2
small-CPU golden measurements plus the hardened private blind short-loop
package, resolved listening result and batch-size 1→2 CPU comparison complete;
the first hardened, lead-only Phase 5.3 S0/M1/M3 phrase-disagreement report is
complete with explicit verified/unverified lineage boundaries; blind phrase
choice remains; Phase 5.4 is complete with its per-stem comparison, full-song
selected-arrangement explorer/mixer, GarageBand Pack Composer and explicit
disputed-range phrase-review bridge; Phase 5.5 local Studio hardening has
completed Project Overview/Resume v1, decision-safety, path-free-role and
two-launch restart verification plus Decoded Stem Comparison v1; Phase 5.6
completes bounded decoded short arrangement presets; Phase 5.7 implements
long-song visualization/recovery and minimal exact canonical full-song chunk
transport; Phase 5.8 completes verified exact-result-cache and bounded
reused-model execution-provenance display; Phase 5.9 guided exact-pack
learning and acceptance passed on 22 July 2026; Phase 5.10a's Guided Local
Studio TUI orientation and visual-Workbench bridge plus the initial Phase
5.10b fresh full-project conversion runner are implemented; the default
one-action Simple path now publishes separately labelled automatic, unreviewed
MIDI, a balanced MIDI-derived WAV and a starter ZIP from exact production
primaries, while its durable
conversion ledger and additional guided operations remain planned; broader
TUI/process/role/instrument/DAW feedback also remains planned, while the first
bounded Workbench Listening Master A/B feedback slice is implemented;
Workbench Stage 4 now supports fixed-selected-MIDI bass and keys instrument
comparisons: bass uses zero-based GM programmes 38/39 with coverage
`not_required`, while keys uses 4/5 and publishes A/B only after both private
identities pass the bounded representative functional-response preflight;
both roles remain `quality_status: review_required`;
Phase 6 Increment 6.0's gated,
read-only Clip Library is complete and Increment 6.1's separate explicit Clip
reuse proposal is complete; Increment 6.2a's reviewed immutable
same-mode key and BPM child workflow is complete; Increment 6.3a's bounded
immutable pitch-correction workflow is complete; Increment 6.3b's bounded
immutable attack-velocity correction is complete; Increment 6.3c's bounded exact
note-removal workflow is complete; Increment 6.3d's bounded existing-note
onset-shift workflow is complete; Increment 6.3e's bounded existing-note
note-end/duration workflow is complete; the ordinary-Workbench
MIDI-derived song-interpretation WAV is complete;
the separate fixed-policy Listening Master v1 CLI challenger is implemented;
ordinary Workbench now has an explicit exact-control Listening Master action
and separate player/downloads; the native TUI **Master** action now provides
the same fixed-policy cache/reuse operation with protected progress; the first
bounded, fixed-window level-matched blind Workbench review and separate
identity-resolution step plus the gated identity-labelled native-level
readiness review are implemented;
broader Phase 6
creative arrangement remains in progress

Started: 15 July 2026  
Scope: local-first AI assistance for transcription, review, instrument matching
and source-derived instruments

This is the working plan for a difficult, multi-week programme. It is intended
to make one measured piece of progress at a time without destabilising the
existing GarageBand-ready workflow. The roadmap is evidence-led: a model is
not integrated merely because it produces plausible MIDI. It must improve a
golden example, preserve timing and provenance, and remain useful in a
GarageBand A/B test.

## Programme goal

Make stems and vocals easier to turn into two linked creative outputs:
accurate, musical, editable MIDI and a MIDI-derived song-interpretation WAV,
with useful playable instruments. A non-technical musician can first request a
transparent automatic, unreviewed starting result; Studio can then replace
those defaults with explicit reviewed choices. The WAV helps a listener
understand and continue the song.
Analytical and AI processes supply independent observations and alternatives.
Sunofriend preserves and compares them rather than forcing one global winner,
and remains responsible for timing, evidence policy, musical constraints,
evaluation, provenance, explicit human decisions and handoff to GarageBand.

The intended flow is:

```text
source mix / stem / vocal
        |
        +--> existing Basic Pitch, pYIN and deterministic analysis
        +--> optional isolated AI backends
        |
        v
raw versioned candidates and confidence
        |
        v
beat, key, chord, repetition and source-evidence checks
        |
        v
small comparable MIDI result space + uncertain passages + audible previews
        |
        v
human recognition/review in short phrases
        |
        v
reviewed GarageBand-ready MIDI, Instrument Bundle and durable provenance
        |
        v
MIDI-derived song-interpretation WAV
        |
        v
optional comparative listening-master challengers
```

The rendering branch, accepted Pupsies golden control, fixed mastering policy
and control/challenger promotion rules are in
[Musical rendering and listening mastering](MUSICAL_RENDERING_AND_MASTERING.md).
Source stems provide timing, horizon and level evidence for the
song-interpretation WAV and are not mixed into it. No rendering or mastering
result becomes a default from metrics, plays or downloads alone; an optional
listening master remains comparative rather than a release master.

## Parallel source-access programme

Sunofriend's Simple and Studio journeys consume separated, synchronized
top-level WAV stems. Source Access S1 is now accepted:
`source-doctor` inspects an existing local FFmpeg/FFprobe toolchain;
`source-import` preserves one authorised local asset; and
`source-import-folder` prepares 2–64 already-separated supported audio parts
as one fresh canonical WAV project. Both import commands have explicit
read-only `--plan` forms.

Source Access S2 is also accepted. It centralizes the source-role vocabulary,
adds an append-only source graph and active frontier, and routes a composite
`drums` source through the mixed-kit family classifier as review-required MIDI.
That route creates no drum sub-stem audio; viable explicit drum-family sources
take automatic-arrangement precedence while the broad result remains
reviewable.

The first S3 slice is a pure backend-neutral separation contract. It defines
local request/result DTOs and strict path-free versioned receipts with
source/backend/checkpoint identity, target/residual geometry, quality and
terminal loadability rules. New receipts use
`sunofriend.separation-run.v2`; canonical v1 float-leakage receipts remain
readable.

The second S3 slice adds an internal controlled-fake-only harness. Its parent
verifies source/checkpoint identity, recomputes persisted PCM16/PCM24 WAV
hashes, geometry, level and target-plus-residual reconstruction evidence,
records structured `not_measured` leakage as `review_required`, confines work
to fresh private sibling directories and atomically renames one completely
revalidated terminal tree. The v2 receipt embeds and hashes the canonical run
plan, derives its `run_id` from that hash and cross-binds actual module,
package, runtime, checkpoint, settings and role identities. Resource use is
bounded and wall time is measured. Arbitrary in-process backends and
executable callbacks are rejected. This is an integration self-test, not
source separation: it adds no CLI/TUI action, isolated real backend, model or
finished-song action to Simple or Studio.

The third S3 slice adds the internal
`sunofriend.separation-acceptance-thresholds.v1` pre-registration contract. It
requires every threshold explicitly, produces a self-hashed immutable
in-memory projection and loads separately persisted canonical JSON read-only.
Its verifier accepts the complete frozen artifact and derives coverage, split
identity and development exclusion from a separate
`sunofriend.separation-hidden-evaluation-manifest.v1`, including canonical
source hashes rather than trusting relabelled song IDs. The artifact fixes
operationally distinct candidate/baseline arms, deterministic evaluation,
Mac/offline/licence gates, per-song rights and independent ground-truth
commitments, and hash-committed blind-listening/statistical policy. This is
protocol scaffolding only: there is no production profile, hidden score or
pass result, backend/model/checkpoint operation, CLI/registry integration or
promotion decision.

The fourth S3 slice adds the internal, deterministic and read-only
`sunofriend.separation-bakeoff-preparation.v1` contract. Prepare, validate and
load each reload the complete canonical frozen acceptance artifact and
reverify the complete canonical hidden manifest before returning the same
self-hashed, deeply immutable redacted `prepared_not_run` plan. It binds the
profile identity and acceptance artifact, canonical-document, hidden-manifest
and split hashes, aggregate coverage, ordered baseline-then-candidate arms,
roles proposed for promotion, downstream identities, evaluator, resource
classes and gate IDs. It discloses no song or source ID; no song, source,
ground-truth, checkpoint or worker hash; and no path, threshold value, score
or private note. All execution, result, selection, promotion and
default-changing effects are false. It has no writer, model or audio operation,
CLI/TUI or registry integration, result, pass or promotion behaviour.

The fifth S3 slice adds the internal, deterministic and read-only
`sunofriend.separation-backend-preflight.v1` contract. It reverifies the
complete frozen acceptance, hidden manifest and redacted preparation, then
inspects one exact arm from the trusted parent without executing its runtime.
The report binds the worker, dependency lock, checkpoint, complete installed
package/metadata trees and separate Git provenance while exposing no local
path. It retains exact read-time facts, includes executable `.pth` and
undeclared files plus empty-directory markers in owned package roots, rechecks
every measured file and inventoried directory immediately before reporting,
and fails closed on changing or symlinked evidence, duplicate identities,
non-native script launchers and malformed editable metadata.
`verified_not_run` is deliberately narrow:
runtime identity/imports/dependencies, external site-startup code, console
scripts, accelerator availability and offline behaviour are not probed. No
worker, model, checkpoint or backend is started or loaded; no audio, result,
score, pass, selection, promotion, default, CLI or TUI operation is added.

The following installed-baseline audit found the local Demucs 4.0.1 code and
exact pinned `htdemucs` checkpoint bytes available, but did not clear a real
S3 run. Separate pretrained-weight terms remain unidentified, the installed
package lacks exact source-commit provenance, and the required OS-level
deny-and-observe offline gate has not passed. The deprecated macOS
`sandbox-exec` command cannot supply complete attempted-connection evidence
and cannot currently apply a profile from the Codex execution context.
Sunofriend therefore keeps this pair in a conditional private-development
lane. No model was executed and no hidden evaluation, pass or promotion
result exists.

The sixth S3 slice adds the pure
`sunofriend.separation-worker-request.v1` and
`sunofriend.separation-worker-result.v1` contracts. A private path-bearing
request must cross-bind the complete frozen acceptance identity, verified
static preflight and backend-neutral separation request. This prevents a
different worker, dependency lock, runtime, checkpoint, source, role set,
settings or seed from borrowing a valid preflight. The result carries only
path-free immutable input, output and enforcement evidence; it contains no
quality, ranking, preference, selection or promotion field. Development-grade
isolation cannot satisfy hidden acceptance: v1 accepts only the
`private_development` lane and cannot represent an `acceptance_ready` request
or result. The exact runtime launcher is a separate parent-owned identity, and
canonical type-aware settings plus path-alias checks prevent re-signed
substitutions.
The module performs no I/O and starts no process. A non-bypassable
subprocess transport, concrete provider, real worker, model execution and
artifact publication remain unimplemented.

The seventh S3 slice adds two more pure, non-executing boundaries.
`sunofriend.separation-runtime-artifact.v1` binds the complete bounded Python
launcher chain and ancestor evidence, final native executable, virtual
environment configuration, installed package-tree digest, worker and lockfile
to separate parent-owned request, preflight and measurement identities. It
rejects symlink escape, case/Unicode aliases and duplicate filesystem
identities. It is explicitly private-development, unregistered measurement
evidence: execution is unproven, TOCTOU is not closed and exact pre-exec
remeasurement remains mandatory.

`sunofriend.separation-launch-plan.v1` then validates that runtime artifact
again and fixes the exact no-shell argv, replacement environment, descriptor,
isolation, process and output-staging policies. Its companion lifecycle
accepts only exact parent/supervisor observations. Process-handle acquisition,
exec and worker handshake are separate, so cancellation or failure between
them cannot lose a live child; every acquired handle must be reaped before its
lease is released. Public events and the terminal receipt are path-free. A
normal close is deliberately `execution_finished_unvalidated` with explicit
false result, input, output, quarantine, publication, acceptance and promotion
flags. Real worker execution is a literal false capability and these modules
contain no filesystem, process, model, audio or network operation.

The eighth S3 slice implements the separate read-only parent measurer.
`separation_runtime_measurement.py` binds only a parent-issued exact worker
request, measures the launcher, full ancestor identity chain, native
executable, virtual-environment configuration, worker, lockfile and bounded
installed package tree, then can repeat the complete observation immediately
before a future exec. Directory traversal is descriptor-relative, no-follow
and read-only; package descendants cannot cross devices or use aliases,
hardlinks, devices or sockets. `include-system-site-packages` must be present
and false. Broad ancestor evidence deliberately projects volatile size and
timestamps away while retaining device/inode/mode and pinned parent-child
bindings, so unrelated sibling activity cannot create a false runtime change.

The measurer makes no network API call and performs no process, model,
checkpoint, audio or write operation. It does not close TOCTOU or prove an
executable runtime. The launch policy now includes `-S` to disable automatic
`site` and `.pth` processing, while base-standard-library, `pyvenv` home and
native dynamic-library closure remain unmeasured. A pure checkpoint and
execution-admission policy is therefore the next safe slice; real execution
support stays literally false.

The ninth S3 slice adds the pure
`separation_checkpoint_policy.py` and
`separation_execution_admission.py` boundaries. Both consume only
synthetic, reported, private-local evidence and always return
`blocked`/`not_run`; neither can authorize a worker. The code-owned
classification for the exact pinned HTDemucs checkpoint hash
`8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4`
is an executable PyTorch pickle model package, regardless of a conflicting
caller-declared format. Its checkpoint terms and allowed-use evidence remain
unresolved, and unsafe-pickle exception metadata cannot waive the categorical
deserialization blocker.

All execution, runtime-closure, output-boundary and resource-limit capability
flags remain false, and the isolation and descendant-policy provider sets
remain empty. The admission record therefore retains explicit blockers for
trusted cross-binding, runtime closure, isolation and network-attempt
observation, input/process/filesystem confinement, transport, output
verification and quarantine, and hard resource enforcement. These modules
perform no filesystem, process, model, checkpoint-deserialization, audio or
network operation.

The tenth S3 slice adds the internal
`sunofriend.separation-checkpoint-inspection.v1` boundary. It accepts only an
exact parent-issued worker binding and reverifies the trusted acceptance,
preflight, separation request and runtime-artifact chain. The inspector opens
the canonical checkpoint descriptor-relative and no-follow, rejects aliases
and special files, hashes the request-bound bytes, repeatedly rechecks every
ancestor attachment and closes every descriptor. It manually validates the
bounded, stored-only Torch ZIP dialect before using the standard ZIP reader,
including central and local records, signed data descriptors, 64-byte payload
alignment, canonical member names, contiguous tensor members and the exact
redundant single-disk ZIP64 terminal used by the installed checkpoint.

Pickle evidence is parsed as bounded `pickletools` opcodes only. No pickle or
Torch deserialization, model import or worker occurs. Only the exact pinned
HTDemucs file hash plus its exact global/opcode profile is classified as a
`torch-zip-pickle-model-package`; generic mapping- or state-dict-looking
pickles remain `unknown` because stack, memo and persistent-ID semantics are
not implemented. A read-only diagnostic of the installed 84,141,911-byte
checkpoint observed 535 ZIP members, 533 tensor payload members and 18,523
pickle opcodes without loading the model. The immutable path-free report is
private development evidence and cannot authorize loading, execution,
selection, publication, acceptance or promotion.

The inspector does not carry its open descriptor into a future loader, cannot
prove filesystem-mount locality and does not recompute every tensor member's
declared CRC. The exact whole-file hash still binds the registered diagnostic,
but path-to-loader TOCTOU remains open. The next safe slice is a launch/worker
transport revision that inherits the already-verified checkpoint descriptor
and cross-binds this inspection into blocked admission without enabling a real
separator. Real separation execution remains literally false.

The eleventh S3 slice adds the pure
`sunofriend.separation-execution-admission-binding.v2` wrapper without
changing the existing v1 admission or launch schemas. It recomputes the
complete canonical blocked v1 admission, then requires both the candidate
checkpoint inspection and the separately retained exact parent-issued
inspection object. This exact-object anchor closes the copied-authority-token
gap found during adversarial review: an exact-class record with changed
classification fields, a recomputed hash and copied private attributes cannot
declare itself trusted.

The wrapper cross-binds admission, checkpoint-policy, inspection,
classification, worker-request, preflight, acceptance and checkpoint hashes.
A fixed code-owned map translates the inspector's
`torch-zip-pickle-model-package` to the policy's
`torch-pickle-model-package` and `unknown` to `uninspected`. Only checkpoint
identity and static classification have parent-observation authority; terms,
loader, runtime closure, isolation, output and resource evidence remain
synthetic. Every v1 blocker is retained, and descriptor-not-carried,
path-to-loader-TOCTOU and static-inspection-not-load-authority blockers are
added. All effects and capabilities remain false.

The twelfth S3 slice adds the parent-only
`sunofriend.separation-checkpoint-descriptor-lease-observation.v1` boundary.
Acquisition reopens the exact request-bound checkpoint through the bounded
inspector, hashes and parses that newly opened descriptor, requires exact
evidence equality with the separately retained trusted inspection, closes all
ancestor descriptors and retains one non-inheritable read-only leaf descriptor
at offset zero. The raw descriptor and finalizer exist only in private weak
registry state; the opaque lease handle cannot be copied or serialized, and
at most two leases can be live.

Recheck uses only the retained descriptor. It performs before/after identity
checks and a full request-bound hash, never reopens the path, and fails closed
on pathname replacement, in-place mutation, inheritance, ownership loss or
parent-PID mismatch. Terminalisation removes active ownership before one
close attempt and returns a path-free receipt that keeps integrity and cleanup
outcomes separate. Explicit close is idempotent; an unconfirmed close is never
retried, while garbage-collection cleanup remains best effort and produces no
receipt. The returned observation is historical evidence, not liveness or load
authority.

Launch v1 is intentionally unchanged and still passes only request/result
descriptors 3 and 4. No FD 5, loader, child request, process, model import,
deserialization, audio read or file write exists in this slice. A retained
ordinary inode is not an immutable snapshot: another writer can change it
after the last measurement. This established requirements for a path-free
request, a blocked launch revision, lease reservation, remeasurement and
atomic read-only worker descriptor 5 installation while keeping the
immutable-backing, executable-pickle, worker-protocol and real-execution
blockers explicit.

The thirteenth S3 slice adds only the pure, private
`sunofriend.separation-worker-request.v2` design-evidence record. It validates
a bounded, canonical, path-free logical request plus 16 expected binding
values supplied by a future facade. It is deliberately a stricter admitted
and inspected subset of V1, not a claim that every valid V1 request projects
unchanged. The logical request retains the verified
preflight projection, source/checkpoint/worker/runtime/lock identities,
canonical roles, type-aware settings, seed and isolation policy. Code derives
logical output slots and records descriptor purposes 3, 4 and 5 without
carrying paths or raw descriptor numbers.

This V2 schema is permanently `blocked`/`not_run`: every capability and effect
is false, the required v2 transport blockers are combined with the inherited
admission blockers, and its expected inputs confer no live authority or
provenance by themselves. The validating V1-to-V2 facade is still absent. It is
not a child-executable request, lease reservation, FD 5 installation, launch
plan, worker protocol, model load or separation feature. Any later executable
request requires a new schema.

The 29 July 2026 fourteenth S3 slice adds a private zero-field reservation
token. It binds one live retained lease to one exact V2 record, the exact V1
inspection request and the current observation backing. All facts the lease
can prove are cross-bound. The runtime-artifact document, execution-admission
and runtime-parent hashes remain sealed by the V2 record but unproven by the
lease. Reserve and release each remeasure under the lease lock; healthy close
refuses while reserved, while integrity or ownership failures terminalize
once. No raw descriptor or FD 5 is exposed or installed, and no process,
model, load or user-facing separation operation exists. V1 schemas and APIs
are unchanged. The next increment remains the blocked launch V2 and atomic FD
5 installation design.

The 29 July 2026 fifteenth S3 slice is maintainability-only. Descriptor
`fstat`, `pread`, `lseek` and owned-close helpers moved to
`_separation_checkpoint_descriptor_io.py`, and pure acquisition-evidence
derivation moved to `_separation_checkpoint_lease_records.py`. The live lease
facade is 793 rather than 884 lines, while public V1 and reservation types,
signatures, `__all__`, schemas, hashes, locks, registry, finalizer and behaviour
remain unchanged. No separator or user-facing capability was added.

The 29 July 2026 sixteenth S3 slice adds only the internal, permanently blocked
`sunofriend.separation-launch-plan.v2` design record. The lease facade issues
it under the existing lock after validating the exact live reservation, exact
V2 request, owner and full checkpoint remeasurement. The path-free record
copies all 16 sealed request bindings, but identifies execution admission,
runtime artifact and runtime-parent measurements as sealed but unproven
rather than promoting them to authority.

The record fixes logical descriptor purposes 3, 4 and 5 and documents the
requirements for a future child-creation-only checkpoint mapping. It does not
install or expose a descriptor, mutate parent FD 5, reopen a path, start a
process or supply argv, source/output transport or a worker protocol. Its
serialized construction conditions are requirements, not proof that the
private issuance route ran, and cannot authorize later use. Ordinary mutable
inode backing, executable-pickle loading, child identity/hash handshake,
post-exec close-on-exec transition and shared open-file-description offset
ownership remain explicit requirements or blockers. Every capability and
effect is false.
Worker-request and launch-plan V2 are permanently non-executable; a
deterministic fake-worker proof must use new executable request and launch
schemas rather than changing V2.

The 30 July 2026 seventeenth S3 slice adds private fake-only request, blocked
launch and worker-result records. They retain V2 and blocked-launch-V2 hashes
only as historical design bindings, add an explicit 64-hex run identifier and
describe a fixed code-owned two-frame PCM24 fixture. Serialized records are
not live authority: execution and worker-start permission remain false, and
source audio, checkpoint deserialization, model import, inference, selection,
acceptance and publication remain unavailable.

Nonce shape does not prove parent-owned freshness or single use. Fake request
and launch V1 are permanently non-executable protocol/planning records; an
actual fake executor requires a new launch schema and live run authority.

The blocked fake launch also records a newly verified platform boundary.
Python's macOS `os.posix_spawn` API cannot prove closure of unrelated
inheritable descriptors. A reviewed native close-all launcher is therefore a
required, unimplemented blocker, alongside exact live lease authority,
immediate checkpoint remeasurement, child-only logical mapping and parent
quarantine verification. No process is started in this slice.

The eighteenth S3 slice adds process-free canonical framing and a
descriptor-pinned parent quarantine observer. The request envelope binds the
exact fake request, blocked fake launch, nonce and hashes. Request and result
frames share the contract's 64 KiB and 1 MiB total limits and reject
noncanonical, duplicate, non-finite, over-deep, truncated and trailing JSON.
The observer verifies one exact directory-entry observation, owner-only
regular files, one link, distinct identities, per-slot size, full hash,
stable identity and independent PCM24 RIFF geometry using `pread`.

This is deliberately not a terminal receipt, launch authority or exact
freshness/immutability proof. It starts no child, installs no FD 5, loads no
checkpoint, runs no model and enables no CLI, TUI or real separation route.
FD 4 carries the bounded result and tiny fixture payloads. A future parent
must create the private quarantine from those validated bytes and then invoke
the observer; the child receives no output path or directory descriptor.

The nineteenth S3 slice adds the private, pure and permanently blocked
`sunofriend.separation-fake-launch-plan.v2` contract in
`_separation_fake_launch_v2_records.py`. It accepts the exact fake request and
blocked fake launch V1 only as historical bindings, then seals caller-supplied
hash, size and stat-identity claims for a native launcher, Python runtime and
fixed fake worker. These are claims, not filesystem measurements, build
provenance or proof of the bytes that would execute.

The contract fixes the abstract invocation
`bound_runtime_executable -I -B -S bound_fake_worker_entrypoint`, an exact
replacement environment containing only `LANG=C`, `LC_ALL=C` and `TZ=UTC`,
and a child-only descriptor plan. All three sources are first copied to
collision-free scratch descriptors, the original child copies are closed,
scratch is mapped to request/result/checkpoint descriptors 3/4/5, and scratch
is closed. Standard streams must be replaced with the native null device and
Darwin `POSIX_SPAWN_CLOEXEC_DEFAULT` must close every unlisted inherited
descriptor. None of those actions is attempted here. FDs 3/4/5 necessarily
remain inheritable across the one intended exec; the fixed worker must make
them non-inheritable as its first user-code action before parsing a request or
reading the checkpoint. Birth-time or pre-CPython noninheritability is not
claimed. Isolated mode ignores Python configuration environment variables,
so hash randomisation remains enabled and fixture determinism cannot depend
on `PYTHONHASHSEED`.

The same record defines parent-owned process-group supervision, one monotonic
deadline, TERM/grace/KILL escalation, exact-PID reap, a nonterminal supervised
unreaped state, bounded worker and parent error taxonomies, and the FD4-only
payload boundary. The child receives no output path or directory descriptor
and creates no files; a future parent must validate the complete result before
materialising and reopening a private quarantine. Current envelope and result
V1 schemas do not bind this V2 plan. Nonce freshness and single use, exact
non-copyable live authority, native build provenance, immediate artifact
remeasurement, runtime and worker path TOCTOU closure, child mapping,
lifecycle enforcement and parent verification are all absent. State remains
`blocked`/`not_run`; every capability and effect is false. This V2 contract
must never be enabled. A future executor requires new live-authority,
envelope, result and terminal-receipt schemas.

The twentieth S3 slice packages
`_separation_native_spawn_darwin.c` as reviewed source only. It is not
registered as an extension, compiled, imported or reachable from Python,
CLI, TUI or the fake protocol. Static tests require a private macOS-only
CPython module, direct `posix_spawn`, `POSIX_SPAWN_CLOEXEC_DEFAULT`, a new
process group, reset signal state, exact isolated-Python arguments and the
same three-variable environment as fake-launch V2. The source validates
non-inheritable, distinct regular-file transports with request/checkpoint
read-only and result write-only access; performs source-to-scratch mapping
entirely in child file actions; closes original and scratch copies; and
replaces standard streams with the null device. It contains no parent FD
mutator. An incompatible parent `SIGCHLD` disposition is rejected in the
future entry point, and a post-spawn result-allocation failure has a
kill-and-exact-reap emergency path so child ownership is not silently lost.

The twenty-first S3 slice adds the separate internal macOS-only build and
test-only canary boundary. A fresh owner-only build pins the source and recipe,
measures the chosen Apple tools, compiles one measured object and invokes the
measured Darwin linker directly with only that object and an explicit measured
SDK `libSystem.B.tbd` as artifact inputs. The receipt binds the
compiler-discovered header closure, object and explicit SDK input; it
explicitly does not claim a complete dynamic runtime-library closure for the
Apple tools. The final thin Mach-O architecture, minimum macOS and SDK
versions, dylib allowlist, absent RPATH, deterministic `LC_UUID`, strict
ad-hoc signature and artifact hash are verified. Two fresh builds on the same
measured host must have identical artifact hashes and UUIDs.

An isolated test harness remeasures and imports only that private artifact.
Across all six logical permutations of exact physical source FDs 3/4/5, it
observes exactly FDs 0–5 in the child, no unrelated low or high inheritable
descriptor, and no change to the parent descriptors' identities, relevant
flags or offsets after spawn and reap. A following finite-matrix increment
repeats those invariants for ten fixed ordinary low non-target,
scratch-candidate-collision, mixed 3/4/5-collision and near-limit physical
layouts. Custom parent `SIGCHLD`
handling and `SA_NOCLDWAIT` fail before child creation. This does not enable
fake-launch V2. Canary matrix v2 now observes only FDs 0–2 at harness entry
before local cleanup after the parent uses `close_fds=True, pass_fds=()`.
Each fixed child reports an empty main-thread signal mask and selected handler
dispositions after CPython startup, while the exact native owner separately
records normal zero-status exit, no signal termination and exact reap. The v2
report retains no raw PID, PGID or wait status. Arbitrary source-FD values and
extension/runtime/worker path TOCTOU remain unproven, the post-CPython
observation does not reconstruct the pre-exec instant, and these facts are not
bound to a deterministic transport worker or model. No production fake worker,
checkpoint transport, model, audio operation, terminal result or user-facing
separator ran.

The next native-ownership increment closes a bare-PID exception gap before any
transport worker runs. The extension preallocates a nonconstructible owner
before `posix_spawn`, returns that exact object without another Python
allocation, hides raw PID authority, caches exact wait status and rejects
post-reap signalling. Last-reference cleanup of a deliberately blocking
process-creation-free canary sends `SIGKILL` and exact-reaps it. A deliberately
stolen external reap moves the owner to a poisoned state and proves later
signalling is rejected. The owner-process destructor guard is statically
present. Emergency destructor wait is not bounded, no generic descendant or
post-leader process-group claim is made, and this remains canary-only rather
than fake or real execution authority.

The next bounded transport-contract slice is complete without starting a
worker. `_separation_fake_worker_darwin.py` is a hash- and size-pinned,
stdlib-only fixed fixture worker: its first effectful module code makes
FDs 3/4/5 non-inheritable, it accepts only V2 transport magic, reads only
FD 3 and FD 5 with offset-independent operations, never deserializes the
checkpoint, creates no process and can write only the deterministic two-frame
PCM24 fixture to FD 4. Prepared fake launch V3 binds the historical request,
blocked launches, worker identity and native build-receipt claim while keeping
the serialized plan non-authoritative and worker-start permission false.
Complete-only worker Result V2 requires a dedicated `PGID == PID` group and
keeps model, source-audio, network, selection and publication effects false.

At that checkpoint the V2 execution protocol was validation-only. It had no
product admitted-envelope encoder or admission issuer, so prepared records
could not become permission after a lease closed. Test code alone made
synthetic V2 envelope bytes. Those serialized records remain non-authoritative
after the later private executor work.

The twenty-third S3 slice adds a private verified native-launcher session. Its
open and recheck routes make one fresh owner-only build, remeasure the artifact
across extension import, verify the compiled source and build contract, and
bind the exact built-in method to full measurements of the current Python
executable and pinned fake worker without calling it. Its opaque,
non-copyable, non-serializable identity and path-free observation are not
execution authority. The same module now contains the later executor-only
guarded call, which cannot be reached with the session alone.

The twenty-fourth S3 slice adds a Result V2-specific parent quarantine
verifier without starting a process or writing a file. It revalidates the
exact historical request/blocked launches, prepared V3 plan and complete
Result V2 before checking an already-materialized owner-only directory via
read-only, non-inheritable descriptors. Exact entry names, distinct file
objects, full hashes and PCM24 geometry are bound into a path-free immutable
exact observation that can be revalidated against the same V3/Result V2
objects. Only the shared low-level descriptor checks are reused; V2 is never
adapted into the historical V1 wrapper. At that boundary, fresh exclusive
materialization, proof that the worker actually executed, live supervision
and terminal parent evidence remained the next gate.

The twenty-fifth S3 slice proves the successful owned-child transport path for
the deterministic fixture protocol through a private synchronous Darwin
executor. Historical fake V1/V2 and
checkpoint-launch V2 remain permanently blocked; prepared V3 is still not
serialized authority; the public lease execution flag remains false; and no
CLI or TUI imports the executor.

The call requires the exact live lease, FD5 reservation, worker request,
current observation, historical record chain, prepared V3 plan and verified
native session. Under the lease lock a one-shot private bridge is consumed to
mint a nonconstructible single-use admission immediately before the exact
native method. Bound artifacts and checkpoint are remeasured, request/result
files are distinct and owner-only, and the lease-owned checkpoint descriptor
is passed directly. Monotonic polling, TERM/KILL escalation, exact reap,
normal exit zero, worker/native PID-PGID agreement and complete Result V2 are
mandatory.

The validated Result V2 reports that the child remeasured the checkpoint, but
the terminal receipt scopes that statement as a worker report. Runtime-exec and
worker-script path TOCTOU remain open, so this slice does not prove that the
exact measured runtime and worker bytes were the bytes executed.

The parent then exclusively creates a fresh owner-only quarantine, writes the
code-owned fixture payloads, reopens them read-only, performs the committed V2
descriptor verification and closes the checkpoint lease. Only then does a
strict validator accept the self-hashed, path-free whole-run terminal receipt.
The intermediate materialization observation is also exact-type, path-free
and self-hashed: it cross-binds every result slot to the verified quarantine
file identity and is revalidated both when created and before the terminal
receipt binds it.

A separate pure post-lease failure schema now defines and seals the ordinary
code-owned parent boundary without weakening native exact-reap or no-start
records. It accepts only an exact, self-hashed native success observation bound
to the V3 plan and Result V2, the exact healthy closed-lease receipt cross-bound
to the worker request and checkpoint evidence, one code-owned parent-side
stage, consistent materialization milestones and every ordered cleanup stage.
The executor issues this inert, path-free receipt for result/root
revalidation, quarantine creation, output creation, descriptor verification,
materialization-observation sealing, descriptor cleanup, root close and
whole-run receipt-seal failures. It preserves the first primary, closes
write descriptors before read reopen, closes read descriptors in LIFO order
and closes the quarantine directory before the private root. The exact
evidence core is snapshotted before root cleanup, and the root is closed before
success receipt construction. No failure receipt permits publication or
selection.

The next bounded failure slice covers one earlier boundary without widening
that post-lease schema. Immediately after a successful, exactly reaped fake
worker returns its execution core, the parent remeasures the same live
lease-owned checkpoint descriptor while the lease lock is still held. One
identity, byte-count or hash mismatch terminalizes the lease and can produce
the disjoint
`sunofriend.separation-fake-post-core-checkpoint-failure.v1` receipt. That
inert, path-free receipt cross-binds the complete fake request/V1/blocked
V2/prepared V3/Result V2 chain, exact native-success observation and exact
failed lease receipt. It requires exactly one admitted integrity reason, no
materialization, and either no cleanup event or one failed
`private_root_descriptor_close`; authenticated root cleanup is prevalidated
for both outcomes and cannot be replayed. A failed strict close retains the
exact armed owner.

This receipt is historical failure evidence, not checkpoint-execution proof.
The child hash remains a worker report, the post-core mismatch cannot identify
which checkpoint bytes were executed or deserialized, transient mutation
outside the observed stat/hash windows is not excluded, and later mutation
after descriptor close cannot change or invalidate an already sealed receipt.

The following disjoint slice covers the next clean lifecycle window. When the
immediate post-core remeasurement matched, bridge finish completed normally
and the FD5 reservation-release remeasurement detects exactly one admitted
identity, byte-count or hash mutation, the executor can issue
`sunofriend.separation-fake-reservation-release-checkpoint-failure.v1`.
Its exact aggregate shape is lease-authenticated: there is no execution
primary, the sole lifecycle error is the exact
`fd5_reservation_release` lease error, and that error carries the same terminal
lease document. The new inert receipt records the release mismatch as its
primary rather than mislabelling it as cleanup, requires complete checkpoint
descriptor cleanup and no materialization, and permits only zero or one failed
private-root close. Both root outcomes are prebuilt before the one-use
authority is consumed; success clears the owner and strict-close failure keeps
it armed.

This second receipt remains historical and conservative. It records that the
earlier post-core check matched and the later release check did not, but cannot
locate the mutation time, prove which checkpoint bytes were executed or
deserialized, exclude transient mutation outside measured windows, or prove
immutability after descriptor close.

The third disjoint integrity slice covers the final clean measurement window.
If post-core and FD5 release both remeasured successfully, bridge finish
returned normally, the reservation was cleared and the final checkpoint-lease
close remeasurement finds one admitted identity, byte-count or hash mutation,
the executor can issue
`sunofriend.separation-fake-lease-close-checkpoint-failure.v1`. The exact
lease-issued aggregate has no execution primary and one
`checkpoint_lease_close` error carrying the same terminal lease document. The
composer normalizes that error into the whole-run primary, cross-binds the
complete fake/native/lease chain, proves materialization never began, and
prebuilds the no-root-error and failed-root-close records before consuming the
one-use cleanup authority.

The receipt requires complete checkpoint-descriptor cleanup and exactly one
admitted integrity reason. It records that both earlier parent checks matched
and the final close check did not, but cannot identify the mutation time or
actor, prove executed or deserialized checkpoint bytes, exclude transient
changes outside observed windows, or prove continued immutability after
descriptor close.

Failures before an exact descriptor backstop can be armed, evidence-snapshot
failure and failure-receipt sealing failure remain explicitly receipt-less.
They preserve the exact owners and errors that are still safe to retain. When
descriptor identity is unavailable, the executor does not perform an unsafe
raw close; when identity is known, cleanup is identity-checked so an unrelated
descriptor reused at the same number is never closed.

The successful-path live proof runs with bounded output in an isolated outer
process group; timeout cleanup discovers and signals child groups before
killing and reaping the helper.

The non-bypassable gate is not complete. Exact-reap native failures,
code-owned native setup or `posix_spawn` no-start outcomes and ordinary
code-owned post-lease failures now have disjoint path-free whole-run receipts.
Each binds its native observation, the terminal checkpoint lease, the original
primary stage and every observed cleanup stage in order. The no-start receipt
makes no child, wait, signal or worker-result claim. Unproven start/reap and
pre-owner, evidence-snapshot or receipt-seal catastrophes remain receipt-less.
Immediate post-core mutation, exact clean FD5 reservation-release mutation and
exact clean checkpoint-lease-close mutation now have separate conservative
receipts. Mutation combined with bridge-finish or release failure, checkpoint
integrity combined with checkpoint-lease descriptor-cleanup or terminalization
failure, a clean remeasurement followed by unconfirmed descriptor close,
runtime/worker path-to-exec TOCTOU and the remaining catastrophic ownership,
inheritability, I/O and authority boundaries are still receipt-less. Those
boundaries and the wider replay matrix keep the gate open.

As failure-receipt groundwork, the private lease bridge now records cleanup
stages in observed order and carries a validated terminal lease receipt when
one exists. If ordinary FD5 reservation release fails, it revalidates the
lease, clears only that private logical reservation, detaches and closes the
owned checkpoint descriptor, and seals the normal lease terminal record.
Any root descriptor already transferred in a successful execution core is
strictly closed by the outer executor. If that close fails, ownership remains
attached to the aggregate failure and a private best-effort finalizer remains
armed; the fallback is leak containment, never terminal evidence. Catastrophic
terminalization failure remains receipt-less and therefore cannot be promoted.

The native layer now has two disjoint path-free failure observations. The first
covers post-start failures only when its exact child owner proves reap,
ownership release and no ownership loss: nonzero or signalled exit, an exactly
reaped timeout, result-close/decode failure, worker identity mismatch and
post-reap remeasurement failure. The second accepts only the exact
nonconstructible native owner tagged `not_started` with a code-owned setup or
`posix_spawn` stage and a private positive native status. It records no status
number, PID, wait or signal event. A live macOS probe verifies that a missing
executable returns `ENOENT`, mutates no parent descriptor and never enters
supervision. Successful spawn followed by child exit 127 remains a post-start
exact-reap failure. Python exceptions, wrong owner types, invalid tags and any
unproven reap deliberately receive no terminal observation. Both record only
code-owned stages; exception text stays private.

`_separation_fake_failure_records.py` now composes either exact-reap or
no-start evidence with the terminal lease receipt into distinct inert
whole-run records. Both bind the validated request/plan hashes, retain
duplicate cleanup events in their observed order, record that private
transport files may remain, and keep publication, selection, acceptance and
promotion false. No-start remeasurement failure must match its recorded
cleanup stage. The raised private error retains the code-owned primary and
source evidence; no exception text, path, PID, PGID or native status number
enters either receipt.

Receipt construction revalidates the complete fake request/launch chain
against the exact reserved worker request and lease observation. The lease
module issues a one-use, non-copyable failure capability only after it
revalidates the terminal lease document; constructed, borrowed, cross-run and
second-use failures cannot mint the receipt. The capability binds the exact
nested primary chain, cleanup tuples and request/plan object identities and
hashes. Before authenticated cleanup or capability consumption, composition
captures the bound native observation and primary and purely validates both
possible receipt forms: no added cleanup, or one failed strict root close.
Only one of those prebuilt receipts is selected afterward, so re-entrant
mutation cannot change the evidence or burn replay authority during later
receipt validation. A raw tuple mutation therefore cannot claim that an outer
cleanup retry happened: composition performs that strict retry itself, only
after authenticating the exact bound owner, and records only its observed
result. Unissued or mutated failures cannot trigger that descriptor close.
Admission cleanup always terminalizes its registry entry, pre-arms an
identity-checked owner for every transport descriptor before native start,
attempts every owned close in deterministic order and preserves the original
native error. A descriptor whose strict close fails retains its pre-armed
finalizer owner; that backstop is private cleanup containment, not successful
evidence.

This is not a separator result. The worker hashes but never deserializes the
checkpoint, reads no source audio, imports no model, performs no inference,
uses no network and creates no output file. Runtime-exec and worker-script
path TOCTOU, binding the model-free canary's post-CPython signal-state
observation to this worker, persistent ordinary-file
immutability and possible failure of the bounded native emergency fallback to
prove reap remain explicit.

Measured local-backend evaluation has now started in a separate private
development lane. `_separation_demucs_private_run.py` extends the existing
isolated cleanup worker with a disjoint four-stem request/result mode. It
hash-verifies the already-installed Demucs 4.0.1 `htdemucs` checkpoint before
deserialisation, applies the model once, and preserves bass, drums, other and
vocals estimates plus source-minus-sum accounting evidence. A fixed
copyright-safe stereo fixture derives exact broad-role references from the
built-in demo, and a separate evaluator revalidates all hashes before
measuring SI-SDR, level error, 10 ms envelope lag/drift, silent-vocal
false-positive energy and aggregate energy.

The first eight-second run completed on 31 July 2026. Bass, drums and other
measured 19.75, 4.13 and 14.01 dB SI-SDR respectively, with no measured lag or
drift; the deliberately silent vocal reference produced -62.95 dBFS. These
are observations on one synthetic fixture, not frozen acceptance thresholds.
The worker reported one model application, 6.82 seconds of inference and
about 2.10 GB maximum resident memory on this Mac. No stem clipped. The four
model estimates differed from the source by -24.87 dB RMS; the separately
persisted accounting remainder closed the float64 sum of the four re-read
stem WAV arrays exactly. The clipped-capable audition sum WAV is not used for
that calculation. This proves arithmetic accounting rather than correct role
assignment.

The first private downstream slice runs the same existing seed transcriber and
explicit settings on each clean reference and matching estimate. It does not
itself exercise `refine_stem`, rendering, iterative repair or variants. Its
self-hashed report persists inactive reference/estimate MIDI and note
evidence. On the same synthetic fixture, bass exact-pitch/onset F1 was 0.556,
`other` was 0.889 and drum onset F1 was 0.815 at a 40 ms tolerance matching
the independent evaluator's default. Broad and articulation drum-family
onset F1 were both only 0.296, and the silent vocal estimate caused one false
MIDI note. These are relative transcription observations, not score truth or
acceptance thresholds. They show that onset survival and correct role/timbre
classification must be evaluated separately.

Production-refinement parity is now also complete for bass, composite drums
and broad `other`, the three synthetic roles actually handled by
`refine_stem`. The repair loop, production dry-GM renderer, generated variants
and independent semantic evaluator all ran on both clean and estimated input.
Clean-to-estimate exact-pitch/onset F1 was 0.625 for bass and 0.909 for
`other`; drum onset F1 was 0.815 but broad-family F1 was 0.296. Independent
strong-onset F1 for `other` fell from 0.813 to 0.471 and supported-note ratio
from 0.800 to 0.646 even though the loop's internal estimate score increased.
Acceptance must therefore combine independent evidence and listening rather
than trust the self-comparison score. Vocal parity remains separately named
because the production vocal melody path does not call `refine_stem`.

The first authorised real slice is now staged from `Be Alone`, 191–206
seconds. The Moises and two Suno pack sums all measured zero 10 ms envelope
lag against the original; their recorded-zero correlations were 0.9985,
0.9305 and 0.9306. The native 48 kHz evidence remains unchanged and the local
runner records its deterministic 44.1 kHz model-input derivative. Pinned local
HTDemucs completed in 11.16 seconds of inference with about 2.13 GB reported
maximum resident memory, no clipped stem and exact sum-plus-residual PCM
accounting closure. Both Suno stems labelled `Keyboard` were effectively
silent in this passage while `Synth` was active, demonstrating that provider
labels cannot define the downstream comparison groups.

The separate role-mapping receipt now assigns every non-metronome provider
item exactly once, writes common-rate four-role auditions and compares every
provider group with every local HTDemucs group. All twelve proposed diagonals
ranked first; similarities ranged from 0.863 to 0.998 and the smallest margin
over the best other role was +0.397. These observations permit an inactive
identical-settings MIDI comparison, not automatic mapping acceptance.

This real-model experiment deliberately bypasses neither the fake-only product
gate nor any acceptance contract. It has no CLI/TUI/Simple/Workbench import,
does not update source lineage, cannot select or promote a result and records
network denial, attempted-connection observation, outside-write confinement
and complete descendant supervision as unproven. Public real-separation and
checkpoint-lease execution flags remain false. Authorised real-excerpt
cross-song MIDI and leaf-level `other` comparisons are now complete on two
songs. Human listening remains open. The next private evidence increment is a
pinned six-source guitar/piano challenger on the same windows; it is not a
product integration or a default.

This work is deliberately parallel to the numbered transcription phases:
input import and source separation change the evidence supplied to every
transcriber. They need independent lineage, model/checkpoint licensing,
residuals, Mac resource measurements and downstream-MIDI gates. No separator
has been integrated or selected as a default. The delivered folder importer
compares available recorded-origin evidence and feeds its canonical WAV
project to existing Create/TUI discovery, but it never shifts, pads, stretches
or normalizes audio, proves a downbeat, repairs alignment, or splits a finished
mix.

See:

- [Stems: what they are and where to get them](STEMS.md); and
- [Stem access and local separation research](STEM_ACCESS_AND_SEPARATION_RESEARCH.md).
- [Private stem-separation development](PRIVATE_SEPARATION_DEVELOPMENT.md).

## Principles and guardrails

- Work locally by default. No source audio is uploaded by an automatic command.
- Preserve the current `.venv` and deterministic CLI. Heavy models run through
  a separate Python 3.12 worker in `.venv-ai`.
- Never silently replace existing transcription evidence with model output.
- Retain raw candidates so consensus and later decoders can be reproduced.
- Keep `exact`, `repair` and `reconstruct` meanings intact.
- Model agreement increases confidence; it does not prove correctness.
- Do not hide several useful analytical and AI processes behind one automatic
  score-based winner. Simple mode may consume the exact primary already
  published by each production conversion, but it must preserve that lineage,
  remain unreviewed and direct uncertain roles to Studio. A different process
  may be useful for each role or phrase.
- Make evidence approachable through plain musical questions, synchronized
  listening and visual lanes while preserving advanced provenance and metrics.
- Borrow useful interaction patterns from other transcription tools without
  cloning their product, hosted service or single-model workflow.
- Keep model code licence, checkpoint licence and training-data notes separate.
- Do not bundle gated, non-commercial or custom-licensed weights in the
  Apache-2.0 repository.
- Make a model earn integration on golden clips before running it over every
  song.
- Treat GarageBand A/B listening as a required evaluation, not an anecdotal
  final check.

## Current programme status

| Phase                                                      | State                                                                                                                                                                                                                                                                                                                                                                                                                        | Outcome                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
|------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1. AI Transcription Bake-off v1                            | **Complete**                                                                                                                                                                                                                                                                                                                                                                                                                 | Independent local model candidates, common JSON, repeatable metrics and final role-specific listening decisions; see the close-out report                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| 2. Phrase Review v2                                        | **Engineering and human review complete; overall programme preference criterion not demonstrated**                                                                                                                                                                                                                                                                                                                           | Recognition-first correction using short candidates, hum/tap/contour guidance, repeated-phrase propagation and advisory personal history. The applied 61-note review won the opening blind loop, the untouched 23-note automatic candidate won none, and both later loops were judged neither                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 3. Instrument Intelligence v2                              | **Complete**                                                                                                                                                                                                                                                                                                                                                                                                                 | Reviewable sound matching, source-event and drum-family evidence, explicit sampler choices, blind A/B, DAW confirmation and advisory loop selection                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| 4. Cleanup and Neural Timbre Lab                           | **In progress; first fixed-MIDI listening gate complete**                                                                                                                                                                                                                                                                                                                                                                    | Complete GM patch preferred; source-fitted resynthesis retained as useful, source sampler rejected; no generated sound beat the simple complete-patch control                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 5. Multi-Process MIDI Comparison and Local Result Explorer | **In progress: Phase 5.0–5.2 complete; Phase 5.3 diagnostic and Phase 5.4 explorer slices complete; Phase 5.5–5.9 hardening complete and Phase 5.9 human acceptance passed; Phase 5.10a, full-project conversion, one-action Simple result, the first 5.10c native Listening Master operation, bounded blind quality review and native-level readiness slice implemented; Phase 5.3 gates and remaining guided work remain** | Local Workbench, immutable analytical/AI alternatives, MuScriptor M0–M4 matrices, exact label partitions, measured CPU/cache/setting choices and blind A/B tooling are complete. The Workbench has hash-pinned per-stem and full-song timelines, bounded decoded transports, a separate exact GarageBand pack basket, Project Overview, fail-closed execution provenance, guided exact-pack acceptance and receipt-bound Listening Master reviews. The Textual TUI now opens with a lay-user Simple action that runs the production engines, consumes only exact published primaries, and creates automatic unreviewed MIDI, balanced WAV and ZIP without fabricating Workbench state; Studio retains detailed comparison, diagnostics, feedback, Inspector and reviewed handoff. A durable conversion ledger/restart contract, additional operation forms and broader process/role/instrument/DAW feedback are not yet implemented |
| 6. Creative Arrangement and Reusable MIDI                  | **In progress: Increments 6.0, 6.1, 6.2a and 6.3a–e plus the selected-arrangement balance slice complete**                                                                                                                                                                                                                                                                                                                   | The gated browser, immutable-placement proposal, key/BPM children and bounded recognition-first pitch/attack-velocity/exact-note-removal/existing-note onset and end patches are complete. Ordinary Workbench also creates the MIDI-derived, source-referenced, drum-guarded and sample-peak-protected song-interpretation WAV while retaining its unity controls. One kind per Clip child, zero-write review, immutable parent and restart validation remain mandatory. Note insertion, release velocity/continuous expression, mode remapping, tuning/downbeat and hybrids remain later slices; hybrid construction still waits for the Phase 5.3 gates                                                                                                                                                                                                                                                                           |
| 7. Cross-DAW, Hosted Access and Opt-in Community Learning  | **Planned, not implemented**                                                                                                                                                                                                                                                                                                                                                                                                 | Beginner installation/acceptance evidence first; then compatibility testing, cleared public goldens and consented contextual feedback. Wider access should use a thin authenticated API/control plane with queued CPU/GPU workers and encrypted expiring object storage, not pretend heavy music inference is a request-duration serverless function. Usage metering, per-transaction payment, rights declarations, model/checkpoint licences and deletion policy are design gates; see [Product modes and hosted future](PRODUCT_MODES_AND_HOSTING.md)                                                                                                                                                                                                                                                                                                                                                                             |

## Phase 1: AI Transcription Bake-off v1

### Goals

1. Establish a modern local PyTorch runtime without changing the existing
   Basic Pitch environment.
2. Define one versioned, model-neutral candidate format for notes, confidence,
   instrument labels, warnings and raw artifacts.
3. Run each backend independently and preserve its untouched output.
4. Compare candidates with existing Sunofriend output and reviewed golden
   examples.
5. Decide separately whether a backend is useful for full mixes, individual
   pitched stems, drums, lead vocals or backing vocals.
6. Publish disagreement and uncertainty instead of forcing one answer.

### Non-goals

- Replacing `listen-all` or `vocal-melody` in one rewrite.
- Downloading every available checkpoint.
- Training a foundation model.
- Assuming a semantically plausible MIDI is accurately aligned.
- Uploading complete songs to an API.
- Making non-commercial model weights a required Sunofriend dependency.

### Candidate backends

| Backend             | Initial purpose                      | Code licence                           | Checkpoint constraint                                         | Phase 1 position                                                                                   |
|---------------------|--------------------------------------|----------------------------------------|---------------------------------------------------------------|----------------------------------------------------------------------------------------------------|
| Existing Sunofriend | Stable baseline                      | Apache-2.0 plus existing dependencies  | Existing Basic Pitch model                                    | Always run                                                                                         |
| MuScriptor          | Full mix and per-instrument MIDI     | MIT                                    | CC-BY-NC-4.0, gated                                           | First local challenger; optional personal/research worker                                          |
| GAME                | Vocal pitches and note boundaries    | MIT                                    | Official v1.0.3 small ONNX release; component hashes recorded | Implemented independent vocal challenger; local CPU worker                                         |
| RMVPE               | Vocal F0 under bleed/noise           | MIT ONNX adapter; Apache-2.0 reference | MIT-labelled canonical ONNX at a pinned revision/hash         | Implemented tracker, consensus evidence and boundary repair; retain as F0 oracle                   |
| PESTO               | Lightweight vocal/instrument F0      | LGPL-3.0                               | Pinned `mir-1k_g7` checkpoint/hash                            | Implemented independent optional worker; retain as vocal F0 oracle, reject for current bass golden |
| MT3                 | Multi-instrument research comparison | Apache-2.0                             | Large/brittle T5X environment                                 | Rejected for Phase 1; MuScriptor covers the comparison without a second T5X stack                  |

### Deliverables

- Reproducible `.venv-ai` setup using `scripts/setup-ai-runtime.sh`.
- `sunofriend ai-doctor` JSON containing Python, PyTorch, MPS and backend
  readiness plus licence manifests.
- `sunofriend.ai-transcription-candidate.v1` request/note/candidate contract.
- One adapter per evaluated model, isolated from the core environment.
- Bake-off run directory containing configuration, raw model output, converted
  MIDI, evaluation, previews and exact model/checkpoint provenance.
- A comparison report covering objective metrics and GarageBand listening.
- A decision for each model: integrate, retain as optional oracle, investigate,
  or reject.

### Reproduce the isolated runtime

On Apple Silicon, install `uv` once and run the checked-in setup script:

```bash
brew install uv
scripts/setup-ai-runtime.sh
.venv/bin/sunofriend ai-doctor --require torch
.venv/bin/sunofriend ai-doctor --require muscriptor
scripts/setup-game-model.sh
.venv/bin/sunofriend ai-doctor --require game
scripts/setup-rmvpe-model.sh
.venv/bin/sunofriend ai-doctor --require rmvpe
scripts/setup-pesto-model.sh
.venv/bin/sunofriend ai-doctor --require pesto
```

The script uses Python 3.12 and installs the versions recorded in
`requirements-ai-macos.txt`. It installs MuScriptor's code but does not accept
its checkpoint licence, authenticate with Hugging Face or download model
weights. Those remain explicit, separately recorded steps before the first
audio experiment.

`scripts/setup-game-model.sh` is a separate, explicit network action. It pins
GAME tag `v1.0.3` at commit
`475a8ee781fe8cca980b3b12fbe6c80c768a813a`, verifies the official small ONNX
release ZIP SHA-256 and verifies all six extracted files. Normal diagnostics
and inference never download or update either the external checkout or model.

`scripts/setup-rmvpe-model.sh` separately downloads only the canonical
`rmvpe.onnx` from the pinned `lj1995/VoiceConversionWebUI` revision
`b2c8cae96e3b05de46d36c5ef9970ef6cbccafba` and verifies SHA-256
`5370e71ac80af8b4b7c793d27efd51fd8bf962de3a7ede0766dac0befa3660fd`.
The isolated package is pinned to `rmvpe-onnx==0.2.3`; normal inference rejects
URLs and receives the existing absolute model path.

Once the user has personally accepted a checkpoint's terms and placed it on
disk, the first challenger can be run without allowing an implicit download:

```bash
.venv/bin/sunofriend ai-doctor --require muscriptor-checkpoint
.venv/bin/sunofriend ai-transcribe \
  /absolute/path/to/excerpt.wav \
  --checkpoint /absolute/path/to/accepted/model.safetensors \
  --out-dir /absolute/path/to/work/ai-bakeoff/song-name \
  --bpm 119 \
  --start-seconds 30 \
  --end-seconds 45
```

The checkpoint must be an existing, absolute `.safetensors` path. Model names
and URLs are rejected before MuScriptor is imported. This preserves explicit
licence acceptance and ensures the checkpoint hash exists before inference.

### Bake-off artifact layout

The current Phase 1 runner creates a fresh, immutable directory per backend
invocation:

```text
work/ai-bakeoff/<song>/<run-id>/
├── run.started.json
├── run.json
├── request.json
├── candidate.raw.json
├── candidate.json
├── candidate.quality.json
├── candidate.mid
├── candidate.expression.json
├── candidate.expression.mid
├── rmvpe.frames.json              # RMVPE only: immutable 10 ms F0/confidence
├── worker.stdout.log
└── worker.stderr.log
```

`run.json` identifies operating system, Python, device, package versions,
model/checkpoint hash, licences, command, parameters, input hash, artifacts,
exit status and elapsed time. A failed or timed-out worker still produces the
final record and captured logs. Reusing a run ID is an error. Source paths may
be retained locally, but a later comparison report intended for Git must use
safe relative labels rather than private absolute paths. Preview, evaluation,
multi-backend comparison and listening-note layers can be added around these
per-backend records without changing the raw candidate.

### Golden material

Use short, representative, authorised excerpts before full songs:

- Lead vocal with obvious phrase boundaries and slides.
- Backing vocals with overlapping harmony.
- Walking or melodic bass.
- Layered keys containing melody and accompaniment.
- Kick/snare examples containing more than one timbre.
- Mixed `other_kit` or percussion with separator bleed.
- Sustained strings or pads.
- A deliberately quiet/no-evidence clip to measure false positives.

The existing Move Your Body and Lidl tests remain regression guards. Additional
private audio may be used as local golden material without being committed.

### Evaluation

Objective MIDI measures:

- note onset precision, recall and F1 at documented tolerances;
- pitch and pitch-class accuracy;
- octave-error rate;
- note-with-offset F1 and duration error;
- median and p95 absolute onset error;
- drift from the source over the complete excerpt;
- false positives during silence or non-target instrument activity;
- instrument-label leakage for multi-instrument output;
- tracker agreement, solo evidence and disputed duration.

Listening measures, scored per phrase:

- recognisable melody without the source vocal;
- correct rhythm and phrase start;
- source-like contour and octave;
- useful density rather than random detail;
- fit with the original stem in GarageBand;
- preference over the current Sunofriend result.

There is no universal pass threshold. A backend advances only when it improves
the relevant golden material without causing an unacceptable regression.

### Work sequence

#### Workstream A — runtime and contract

- [x] Preserve the Python 3.9 core environment.
- [x] Add isolated Python 3.12/PyTorch setup.
- [x] Add licence-aware backend manifests.
- [x] Add a versioned request/note/candidate contract.
- [x] Add runtime/backend diagnostics.
- [x] Add worker request/response invocation with timeouts and captured logs.
- [x] Add immutable run manifests and input/checkpoint hashing.

#### Workstream B — MuScriptor

- [x] Install code without downloading gated checkpoints.
- [x] Record explicit acceptance and checkpoint hash for the small model.
- [x] Test CPU and MPS support; do not assume MPS compatibility.
- [x] Adapt streamed note events into candidate v1 without adding velocity.
- [x] Test restricted instrument lists and isolated vocal/bass stems.
- [x] Test a full mix and quantify instrument-label leakage.
- [x] Recover velocity from source evidence after the raw candidate is saved.

#### Workstream C — vocal models

- [x] Install GAME in an external checkout and record its release bundle.
- [x] Adapt GAME pitches, boundaries and voiced/unvoiced evidence.
- [x] Test seeded GAME on lead and backing vocals and expose an opt-in variant.
- [x] Install/adapt RMVPE as a frame-level tracker.
- [x] Compare GAME, RMVPE, Basic Pitch and pYIN independently.
- [x] Add consensus only after raw per-model evaluation exists.
- [x] Test conservative Basic Pitch/GAME boundaries only on agreed pYIN/RMVPE F0.

#### Workstream D — evaluation and decisions

- [x] Create the bake-off runner and artifact layout.
- [x] Add synthetic protocol and failure tests.
- [x] Run the first 10–15-second vocal and bass clips.
- [x] Render neutral-instrument previews.
- [x] Capture GarageBand listening scores.
- [x] Write the first local model decision record; publish after listening.

Optional close-out improvements are complete: PESTO has a pinned local worker
and three-role comparison; MuScriptor has keys, kick and strings comparisons;
all four AI backends pass a digital-silence no-false-note check; and MT3 has an
explicit Phase 1 rejection decision. See
[the Phase 1 close-out report](PHASE1_TRANSCRIPTION_BAKEOFF.md).

### Phase 1 completion criteria

Phase 1 is complete when:

1. At least one multi-instrument model and one vocal-specific model can be run
   reproducibly through the common contract.
2. Every result contains raw output, MIDI, evaluation and model provenance.
3. Failures and missing checkpoints degrade safely without affecting existing
   commands.
4. At least three representative stem types and lead vocals have measured
   comparisons.
5. GarageBand A/B notes are recorded alongside quantitative metrics.
6. There is an explicit integrate/reject/retain decision for every evaluated
   backend.

## Phase 2: Phrase Review v2

The goal is to turn melody correction into recognition rather than singing
performance.

Planned features:

- automatic phrase segmentation into two-to-eight-bar review units;
- two to five rendered MIDI alternatives per uncertain phrase;
- synchronized source, waveform/pitch map, piano roll and chord lane;
- actions such as closest candidate, octave up/down, earlier/later, repeated
  note, split, merge and contour direction;
- optional two-to-five-second hum, whistle, tap or single-note guide;
- contour/time alignment that does not require the guide to be in the source
  key or octave;
- accepted correction propagation to repeated phrases;
- a small deterministic personal ranking/calibration signal learned from
  explicit choices;
- untouched automatic and reviewed versions with complete audit history.

Phase 2 succeeds when a user who cannot hum a whole song can correct its main
melody phrase by phrase and prefers the reviewed neutral-instrument rendering
to the automatic candidate.

Implemented so far:

- [x] turn confidence-ranked agreed-F0 regions into three local alternatives;
- [x] render MIDI-only and source-plus-MIDI phrase auditions;
- [x] capture explicit choices in the existing correction JSON contract;
- [x] require completed review and matching source hash before MIDI export;
- [x] preserve every raw tracker artifact and refuse monophonic backing review;
- [x] merge note clusters into musical two-to-eight-bar review units;
- [x] add source-supported short hum/whistle/tap/single-note correction only
  for one explicitly unresolved review unit at a time;
- [x] suggest genuinely repeated absolute-pitch/rhythm units and propagate an
  alternative only after an explicit, audited user action;
- [x] learn a local advisory personal ranking only from explicit reviewed
  choices, without changing candidate order, defaults or review status.
- [x] complete the first genuine three-unit review, validate its source and
  tracker lineage, apply its explicit choices and build a real local profile;
- [x] resolve the assembled reviewed neutral rendering against the untouched
  automatic combined candidate in a blind three-loop review. The reviewed
  assembly won the opening loop, the automatic candidate won none and both
  later loops were judged neither. This completes the gate but does **not**
  satisfy the overall Phase 2 preference criterion.

## Phase 3: Instrument Intelligence v2

Status: **complete**. See [the Phase 3 close-out report](PHASE3_INSTRUMENT_INTELLIGENCE.md)
for the implemented evidence, reproducible goldens and final listening
decisions.

Planned features:

- learned audio embeddings alongside existing explainable spectral features;
- source-versus-rendered candidate matching using the same MIDI phrase;
- sample clustering by instrument identity, articulation and timbre;
- distinct kick, snare, tom and percussion families rather than one pitch/name;
- velocity-layer and round-robin discovery from repeated source events;
- root-note, tuning and usable-range estimation with confidence;
- bleed, transition and outlier rejection;
- loop-point suggestions with waveform and representation continuity;
- user accept/reject feedback stored as instrument-choice evidence;
- backward-compatible Instrument Bundle output and GarageBand audition steps.

Implemented so far:

- [x] optional local, hash-pinned OpenL3 music embeddings beside the unchanged
  explainable spectral/dynamics/attack score;
- [x] compare the source and every FluidSynth candidate using the same aligned
  MIDI performance and active one-second windows;
- [x] retain separate learned MIDI/WAV auditions, complete evidence JSON and
  additive Instrument Bundle v1 fields without automatic score blending.
- [x] deterministically cluster MIDI-aligned source events into advisory
  candidate timbre families and independent articulation groups, retain robust
  outliers, and carry JSON/SVG evidence through matching, sample packs and
  Instrument Bundle v1 without changing selection.
- [x] turn drum/percussion mapping units into role-specific GM channel-10
  proposals with assigned one-shot auditions, existing-note guardrails,
  immutable input hashes and additive Instrument Bundle v1 handoff.
- [x] discover advisory velocity-layer and round-robin candidates only within
  one timbre-family/note/articulation unit, retain a visual/source-index audit,
  and apply zero MIDI, sample, SoundFont or drum-mapping changes.
- [x] require an explicit all-unit listening review before applying candidates
  to a separate Sample Instrument v3; pin every input/review excerpt, retain a
  self-contained v2 rollback, use real SF2 velocity layers, expose true SFZ
  round robin and honest separate GarageBand alternate banks.
- [x] retain every isolated candidate while adding hash-pinned source-context
  and role auditions: repeated two-bar beats for drums/percussion and short
  sampler pitch phrases for pitched instruments, with zero selection effect.
- [x] add a real-MIDI source/v2/v3 musical A/B and explicit velocity-boundary
  sweeps to reviewed v3 outputs without altering source MIDI or review choices.
- [x] rank advisory post-attack/pre-release loop boundaries using waveform and
  spectral continuity, render raw repeated-loop auditions, exclude percussive
  one-shots, and leave every SF2/SFZ zone unlooped until a human accepts one.
- [x] build neutral, context-rich and byte-reproducible close-out reviews for
  snare, hats, cymbals and toms without carrying earlier kick or `other_kit`
  choices into another role.
- [x] hide v2/v3 identity behind deterministic Candidate A/B performance and
  velocity-sweep audio, keep the answer key outside the HTML, and resolve only
  a complete hash-pinned user export with zero sampler or MIDI effects.
- [x] close the human gate with a GarageBand/AUSampler snare decision and an
  explicit pitched-loop candidate, while retaining v2 rollback and leaving the
  sampler loop disabled.

Phase 3 evaluation is complete. Its evidence showed that reviewed suggestions
can improve an isolated sample without consistently sounding closer in a full
performance; blind proxy and final DAW listening therefore remain mandatory
selection gates.

## Phase 4: Cleanup and Neural Timbre Lab

This remains an explicit experimental lane.

Planned experiments:

- query- or prompt-based isolation for mixed stems;
- target plus residual reconstruction checks;
- neural denoise/de-reverb only when it improves downstream transcription;
- monophonic DDSP-style timbre models for bass, wind, strings or vocal-like
  instruments;
- optional DAW hosting through a suitable Audio Unit bridge;
- generated missing samples marked separately from extracted samples;
- no generic image diffusion over spectrograms without an audio-valid decoder;
- no generated output promoted to `exact` evidence.

Implemented foundations:

- [x] add a short, transparent MIDI-informed harmonic-mask baseline with
  explicit note-bearing track selection;
- [x] persist source excerpt, target, residual and zero-based guide MIDI with
  hashes and source/MIDI zero-mutation effects;
- [x] measure persisted target-plus-residual reconstruction and refuse excerpts
  longer than 60 seconds;
- [x] make WAV evidence byte-reproducible with GarageBand-friendly PCM24 rather
  than timestamped float-WAV PEAK chunks;
- [x] compare harmonic-only and explicitly labelled broadband-transient
  challengers without promoting either; and
- [x] re-transcribe source, target and residual separately and publish a local
  listening page;
- [x] reject incomplete source samplers with an arrangement-aware playability
  gate before timbre matching; and
- [x] retain explicit full-mix/solo patch choices in a deterministic local
  advisory profile without changing rankings, defaults or playability.
- [x] add a hash-pinned, isolated Demucs target/residual challenger with
  deterministic short excerpts, failed-run preservation and no automatic
  promotion.
- [x] resolve an explicit multi-role listening review against its complete
  hash-pinned evidence tree without regenerating or silently merging MIDI.
- [x] add a native-44.1-kHz fixed-MIDI harmonic-plus-noise baseline, mandatory
  complete-patch control, optional source sampler and explicit listening page.

Phase 4 succeeds only if an experiment beats the simpler sample/DSP path in
listening tests and remains reproducible, attributable and safe to distribute.
The current foundations meet the reproducibility and safety requirements. The
first fixed-MIDI review found harmonic-plus-noise resynthesis useful but still
preferred the complete GM patch, while rejecting the source sampler; no cleanup
or neural-timbre challenger has yet beaten the simpler path. See the
[Phase 4 stabilization review](PHASE4_STABILIZATION_REVIEW.md) for the
goals-versus-execution matrix and the gate before the next experiment.

## Phase 5: Multi-Process MIDI Comparison and Local Result Explorer

The converter identified from Mirelo's Audio-to-MIDI workflow is MuScriptor,
the same optional model already evaluated in Phase 1. Phase 5 therefore does
not begin with another installation and is not a Mirelo clone. It asks when
unrestricted discovery, role-conditioned full-mix/stem passes, specialist
analysis, tracker consensus and source-aware repair are useful. Each process
remains an immutable auditionable candidate; success can differ by role and
phrase, and no global model winner is required.

The website is primarily the local product UI: project setup, per-role
source/MIDI comparison, arrangement audition, instrument choice and explicit
GarageBand export. The current Workbench already provides synchronized
per-stem comparison, append-only choices, a selected-arrangement proxy and a
safe exact-MIDI handoff. Phase 5.4's first visual slice adds the compare-role
timeline for the small family of analytical and AI alternatives. Its second
slice adds a full-song view of unique project sources and current explicit
main/optional MIDI, with temporary source/MIDI/hybrid audition controls that do
not record feedback. Its initial GarageBand Pack Composer now presents a
separate persistent basket containing active selected MIDI, an optional dry
arrangement proxy and source audio behind explicit opt-in. Hash-pinned plans
and baskets make the ZIP contents inspectable and reject stale builds; plays,
visibility and mixer state never imply inclusion. The final 5.4 slice adds an
explicit, hash-pinned bridge from diagnostic S0/M1/M3 disagreement ranges to
the exact existing phrase-review anchors. It changes only temporary loop and
navigation state and creates no choice, MIDI or feedback.

A later cross-cutting Workbench slice adds the source-referenced MIDI-derived
song-interpretation WAV described under Phase 6. It is deliberately separate
from the three unity technical transports and Pack Composer: a product
derivative and fader recipe, not a candidate score, saved custom mixer or
final master.

Phase 5.5 starts with a default Project Overview backed by the path-free
`sunofriend.workbench-home.v1` projection. It reports explicit decisions,
selected parts, full-mix work and one deterministic resume state/action without
using candidate scores or process names; the terminal state deliberately has
no navigation action. Saved decisions and a current pack
basket survive restart; audition controls reset. Initial connection and lazy
pack-status failures are retryable and have zero feedback, selection, pack or
artifact effects. This makes the multi-process space easier to enter; it does
not replace per-stem comparison or promote a model.
The second hardening slice now makes `none_usable` and `cannot_tell` selection
barriers, applies one path-free role guard to browser/timeline/pack/MIDI
surfaces and verifies both positive selections and terminal outcomes across
real server restarts. The raw private history remains append-only.
Phase 5.5's third slice adds Decoded Stem Comparison v1. It prepares a 0.5–15 second
recorded-time source loop with the primary candidates and only explicitly
opted-in advanced candidates, capped at six. Source, MIDI and neutral-preview
hashes are verified before private content-addressed clips are served. One
decoded Web Audio clock schedules switches without saving an event or choice,
ranking a process or changing MIDI. It infers no offset: source and MIDI begin
at recorded zero. The disclosed compatibility fallback remains
second-synchronised HTML media rather than sample-accurate transport.

Phase 5.6 applies one decoded clock to a canonical 0.5–15 second selected
arrangement. The server—not the browser—derives source-only, selected-MIDI,
hybrid and main-only memberships from the current manifest, with 24-track,
2 GiB input and 64 MiB output bounds.

Phase 5.7 adds fixed-window Fit/4×/16× visualization, paging and visible-event
culling, stale-request rejection and compatible-last-result recovery. Culling
reduces canvas painting only: the complete bounded timeline JSON is still
downloaded, parsed and indexed. It also adds exact full-song playback for the
same four canonical rosters using integer-frame non-looping chunks, one Web
Audio clock and only current plus next decoded chunks. A missing successor
stops at the verified boundary; retry does not auto-restart, and no failure
silently starts coarse playback. Full-song limits are 24 tracks, a 20-minute
longest source, 2 GiB input, mono/stereo 8–96 kHz audio, 480 adaptive chunks of
at most five seconds/32 MiB PCM16, 192 MiB projected two-chunk decoded memory,
16 active stream plans and 768 generated-media capabilities per launch. The
arbitrary mute/solo/gain full-song mixer remains the third, coarse path.

Phase 5.8 verifies how every completed AI candidate was executed before showing
that provenance. Exact-result cache misses and hits remain distinct; a hit says
that no model ran. A completed bounded session is revalidated as a whole before
request one is described as resident-but-not-warm or request two and later as
reused-model warm. Missing or changed parent/run/response/performance evidence
fails closed. Workbench only displays these facts: it starts no model, worker,
session or cache and never treats execution reuse as musical agreement.

Phase 5.9 attaches one local learning and acceptance package to the exact
GarageBand ZIP. Eight interactive tutorial screens precede a fixed
one-question-at-a-time quiz; all 10 answers must be correct before the two
human checks unlock. The first check covers exact-BPM GarageBand import,
playable patches, drum routing where applicable, listened downbeat and
full-song drift. The second confirms an authorised local project and the
understandability of comparison, choice, arrangement, state separation, export
and restart. A strict resolver re-verifies the downloaded ZIP and recomputes
the review without changing project state. The 22 July 2026 result passed all
eight tutorial screens, the quiz at 10/10 and both six-item human checks
without an issue or `cannot_tell` answer. It verified five selected MIDI
payloads, the dry proxy and no source audio. The downbeat result remains
reviewer observation rather than invented catalog metadata, and every project
effect is false.

Phase 5.10 makes the existing power approachable without changing its
authority boundaries. The preferred human route is now `sunofriend tui`; the
CLI remains the deterministic engine, the graphical Workbench remains the
rich comparison/decision/export surface and the agent skill remains an expert
conversational route.

Increment 5.10a is implemented. Its Textual dashboard scans an existing local
project read-only, reports key/BPM/tuning, shows stem/candidate/decision state
and compact primary-MIDI pitch/activity maps, runs local system diagnostics,
keeps a bounded in-memory activity log and opens the existing Workbench with
the read-only Developer Inspector available by default. It owns, stops and
reaps the Workbench child process. Highlighting, mapping, diagnostics and
navigation record no preference or feedback.

The initial Increment 5.10b slice is implemented. **Convert all stems** uses an
editable, explicitly confirmed fresh output. It calls production `listen-all`
in repair mode with variant evaluation, then separate `vocal-melody` runs for
lead and backing vocals. It discloses `wind` → `lead`, `rhythm` → `keys` and
`other` → `synth` proxy engines, skips near-silent sources with a visible
reason, streams progress, preserves partial output on cancellation and reloads
the new root only after success. It never overwrites or auto-selects MIDI.

The remaining 5.10b–d work adds a durable owner-only job ledger and restart
recovery, further typed operation forms, an end-to-end Workbench/pack journey
and explicit structured local feedback. Every form must call existing
CLI/application operations rather than duplicate musical code, expose no
arbitrary shell input, infer nothing from audition activity and add no upload
or telemetry. Workbench remains review-only. The authoritative contract,
carry-forward register and delivery order are in
[Guided Local Studio TUI](LOCAL_STUDIO_TUI.md).

Reload restores URL-hash view/stem and durable SQLite decisions, Overview state
and the pack basket. Prepared audio/chunks, playhead, loop,
viewport/zoom/visibility and mixer controls reset.

This direction borrows the approachability of a visual transcription tool—one
transport, visible notes, understandable track controls and direct export—not
its product identity. Sunofriend's differentiator is the transparent result
space: several methods, source evidence, provenance, role-specific choices,
valid `equivalent`/`neither` outcomes and no automatic winner. Direct note
editing and creative recombination are reserved for Phase 6. Public feedback,
accounts, telemetry and hosted ingestion are deferred to Phase 7; Phase 5.4–5.9
stay local-only, and Phase 5.9 adds no network submission path.

The complete research findings, licence boundary, benchmark matrix,
performance strategy, feedback schema, privacy design, increments and
promotion gates are in the
[Phase 5 multi-process comparison and Result Explorer plan](PHASE5_MUSCRIPTOR_COMMUNITY_PLAN.md).

## Phase 6: Creative Arrangement and Reusable MIDI

Once the local explorer and pack composer are trustworthy, add broader
reversible piano-roll correction beyond the completed bounded pitch and attack
velocity and exact-removal slices, phrase alternatives and explicit hybrids;
key, BPM, tuning and downbeat transformation; Clip v1 browsing and reuse; mashup
preparation; and instrument/Bundle attachment to reviewed parts. Every edit
must preserve its source candidate and a minimal audit diff. GarageBand remains
the final performance, patch and mixing environment.

The first arrangement-balance slice is complete in ordinary Workbench. It is
an explicit selected-MIDI derivative rather than a Clip edit: verified source
stems guide per-lane gain, the actual waveform sum of alternatives sharing one
source is calibrated back towards that source reference, a bounded shared drum
trim prevents the combined drum bus masking the non-drum bus, and final
audition gain preserves −1 dBFS sample-peak headroom. The
unity-gain dry proxy and exact transports remain unchanged. The report says
`mastered: false`; no compressor, limiter, EQ or creative effects are used, and
GarageBand still owns final patches, automation, mixing and mastering. The
WAV/receipt/fader recipe are currently Workbench-only and do not enter Pack
Composer v1. The longest verified stem across the whole project also owns the
balanced WAV horizon; longer neutral-render tails are disclosed and excluded.

The technical and guided-review gate has passed. The first read-only Clip
Library slice is complete under an explicit all-or-none launch
contract: `--clip-library`, `--phase6-acceptance` and `--phase6-pack` are all
required. Its only functions are bounded browse/search, path-free detail and
lineage, dry neutral audition and deterministic MIDI reconstruction from the
immutable Clip document. That reconstruction is not an original-MIDI byte
copy. It changes no library, project decision or basket and adds no transforms,
writes, piano roll or hybrids. Explicit hybrid construction remains separately
gated by the open Phase 5.3 blind-choice and source-lineage work. See
[Phase 6: Creative Arrangement and Reusable
MIDI](PHASE6_CREATIVE_ARRANGEMENT.md).

Completion used a real read-only library with 73 Clips in 51 lineages. Browser
validation covered browse/detail, deterministic MIDI, a dry FluidSynth proxy,
a repeat cache hit, path-free byte-range serving and Developer Inspector
tracing while producing zero musical/library mutations. Broader Phase 6
remains in progress.

Increment 6.1 is implemented behind an additional explicit
`--enable-clip-reuse-plan` flag, valid only with those same three gate inputs.
It adds **Browse Clips** and **Proposed reuse plan** modes, exact
`clip_id`/object-hash placement, explicit removal and exact-binding restart
restoration in a separate append-only local database. Its fixed 4/4,
480-TPQ, whole-beat grid starts at recorded zero; neither downbeat nor time
signature is inferred by the grid, and existing project downbeat evidence is
reported but not applied. Key/BPM/timing/overlap/instrument warnings describe
compatibility but apply no transformation. The plan is bounded to 64 active
placements, 512 events, 20,000 notes per Clip, 40,000 active note instances
and a 20-minute nominal end. Focused/full-suite and local restart/browser
verification passed, so Increment 6.1 is complete.

Increment 6.2a adds a separate `--enable-clip-transforms` launch, mutually
exclusive with the complete-library-bound reuse proposal. On exact Clip detail,
the user chooses one same-mode key change or one BPM timing contract, reviews a
zero-write server projection and then explicitly creates one immutable child.
The action is pinned to the parent Clip/object, complete library state,
transform request and projection hash. It changes only the library by appending
the child; the parent, process alternatives, project decisions, current
arrangement, proposal placements and Pack Composer remain unchanged. Musical
BPM changes retain beats and change elapsed time; stem-locked changes retain
source seconds and change beat positions. Mode remapping, tuning, downbeat and
note editing remain separate.

Increment 6.3a is the first bounded note-editing slice. A separate
`--enable-clip-corrections` launch exposes one exact 480-TPQ phrase window for
a pitched, non-drum Clip. The user selects 1–64 existing notes and supplies
only their target pitches, reviews a zero-write exact diff, then may append one
deterministic immutable child. The parent plus timing, duration, source
seconds, expression, key, chords, instrument and unaffected notes remain
unchanged. New same-pitch MIDI overlap/collapse is rejected. A recognized
bounded correction recipe can be validated against the retained parent and
shown again after restart.

Increment 6.3b keeps that authority boundary and published pitch-v1 hashes,
then adds an explicit `attack_velocity_patch` policy. One child changes 1–64
unique attack velocities to integers from 1–127 and preserves pitch, timing,
duration, source seconds, release velocity, articulation and metadata. It is
available for pitched and drum-family Clips. Notes that normalize to a shared
channel/onset/pitch Note On are visible but blocked because the requested
source-note edit would not map to one exported event. Pitch and velocity never
share a draft or recipe. Exact deletion is the separately bounded 6.3c slice
below, exact existing-note onset shift is the 6.3d slice after it, and
note-end/duration is the 6.3e slice. Note insertion, release velocity and
continuous expression remain deferred to their own identity/evidence contracts.

Increment 6.3c is complete under the same correction gate and routes. Its
kind is `note_delete_patch`, its retained operation is
`delete_clip_notes`, and its isolated policy belongs in
`workbench_deletion.py`. A listener may explicitly mark 1–64 unique exact
existing note references in a bounded phrase, for pitched or drum-family Clips,
but at least one note must remain. Selection/focus alone is not a deletion:
**Mark for removal**, zero-write **Review temporary note removal** and explicit
creation remain separate actions. Sunofriend never infers noise or unwanted
material.

The deletion validator proves that normalized child MIDI is normalized parent
MIDI minus exactly the named intervals, every survivor is byte-for-byte
equivalent at the Clip-note field level and beat/export/source horizons do not
move. Duplicate or cascade-dependent export groups, horizon-changing notes and
the only remaining note are blocked. A fresh child may set only
`library_mutated`, `child_clip_created`, `correction_applied`,
`note_count_changed` and `note_deleted`; replay and restart are zero-effect.
Pitch-v1 and attack-velocity-v1 requests, schemas, hashes and recipes remain
frozen. At the 6.3c close-out, note insertion and onset/duration editing still
required separate identity/evidence and dual-time contracts; 6.3d now takes
only the onset part under the contract below.

Increment 6.3d is complete as the next bounded note-editing slice under the
same explicit correction gate. Its separately discriminated kind is
`note_onset_shift_patch`; its retained recipe operation is
`shift_note_onsets`. One request names 1–64 exact existing pitched or drum note
references and an exact integer `target_start_tick` for each. Every target must
differ by a non-zero value no greater than 480 ticks, and both the source and
target note intervals must be wholly inside the loaded half-open window.

The operation shifts the normalized Note On and matching Note Off by the same
delta. MIDI duration ticks, pitch, attack/release velocity, articulation,
microtiming and note count remain exact. It does not infer a better time, snap
to a grid, quantise, propagate a phrase or use scale/chord evidence. It rejects
target overlap/duplicate/cascade ambiguity, negative or unencodable ticks,
window escape and any changed beat/export/source horizon. Window rows use only
these four block reasons: `context-note-outside-window`,
`duplicate-export-note-on`, `normalized-lifetime-dependent` and
`unsupported-stem-locked-microtiming`.

For `musical` timing, the operation adds `delta / 480` to `start_beat`, keeps
`duration_beats` and both microtiming fields, then recomputes source seconds
through the retained tempo map. For `stem_locked` timing, v1 requires both
microtiming fields to be exactly zero, shifts source start/end by
`delta * 60 / (export_bpm * 480)`, preserves source duration and derives beat
coordinates. Both paths must round-trip to the exact requested ticks. Preview
is zero-effect; a fresh child may set only `library_mutated`,
`child_clip_created`, `correction_applied`, `note_onset_changed` and
`note_timing_changed`; replay and restart are all false.

The overall correction capability remains schema v2 and continues to report
generic `timing: false`; clients must test the explicit
`note_onset_shift_patch` entry and `maximum_onset_delta_ticks: 480`. The frozen
pitch, attack-velocity and deletion contracts remain byte-compatible. Release
velocity was not selected for this increment because all audited local Clip
libraries contain only zero release velocities and GarageBand patch support
for Note Off velocity varies. Increment 6.3e now takes note-end/duration alone;
note insertion, release velocity and continuous expression remain deferred.

Increment 6.3e is complete under the same correction gate. Its kind is
`note_end_shift_patch`, retained operation is `shift_note_ends`, and the four
public schemas are
`sunofriend.workbench-clip-note-end-window.v1`,
`sunofriend.workbench-clip-note-end-preview.v1`,
`sunofriend.workbench-clip-note-end-result.v1` and
`sunofriend.workbench-clip-note-end-summary.v1`. One patch contains 1–64
unique exact existing pitched or drum note references and one integer
`target_end_tick` for each. The non-zero delta is bounded to ±480 ticks, the
new duration is at least one tick, and both source and target full intervals
must remain inside the loaded half-open window.

Only the normalized Note Off and duration move. Note On, pitch,
attack/release velocity, articulation, note count and every unaffected note
remain exact. The same four row reasons used by onset shift apply:
`context-note-outside-window`, `duplicate-export-note-on`,
`normalized-lifetime-dependent` and
`unsupported-stem-locked-microtiming`. Crossing the next same-channel,
same-pitch onset, changing a neighbouring normalized lifetime, moving a global
beat/export/source horizon or exceeding the window/MIDI bounds fails closed.

In `musical` mode, `duration_beats` changes by `delta / 480`, onset and both
microtiming fields remain exact, and source end is recomputed through the
tempo map. In `stem_locked` mode, v1 requires zero start/end microtiming,
changes source end by `delta * 60 / (export_bpm * 480)` and derives the new
beat duration. Both paths must round-trip to the requested integer Note Off.
The capability remains v2 with generic `timing: false`; clients must require
`maximum_note_end_delta_ticks: 480` and
`minimum_note_duration_ticks: 1` as well as the explicit kind.

Typing and focus are zero-effect. The user must Apply, Review and Create.
Preview has every effect false; a fresh child may set only
`library_mutated`, `child_clip_created`, `correction_applied`,
`note_duration_changed` and `note_timing_changed`; exact replay and restart
have every effect false. No legato, phrase, quantisation, correctness or
musical-quality inference is made.

## Phase 7: Cross-DAW and Opt-in Community Learning

Only after the private workflow is useful and hardened, expand compatibility
testing to other DAWs and consider cleared public listening reviews. Ordinary
use remains local. Any contribution must show the exact data leaving the
machine, require explicit consent, exclude private audio by default and retain
context such as role, process, version and `equivalent`/`neither` outcomes.
Only a rights-qualified immutable dataset can support a later small independent
selector or error-classifier experiment; community popularity never overrides
the user's choice.

## Daily progress routine

Each working day should aim for one narrow vertical improvement:

1. Choose one unchecked item or one clearly stated investigation.
2. Record the hypothesis and the golden clip before changing code.
3. Make the smallest implementation or experiment that can answer it.
4. Run focused tests and one relevant end-to-end comparison.
5. Save metrics, preview paths, warnings and unexpected findings.
6. Update the checklist and daily log.
7. Stop with the repository usable; do not leave the core workflow depending
   on an unfinished model installation.

### Daily log template

```markdown
### YYYY-MM-DD — short title

- Goal:
- Change or experiment:
- Inputs:
- Model/runtime/checkpoint:
- Evidence and metrics:
- Listening result:
- Decision:
- Problems/risks:
- Next smallest step:
```

## Daily log

### 2026-08-03 — fixed native Kim output bound to unchanged MIDI evidence

- Goal: carry the clean native Kim result into the already established private
  vocal-MIDI comparison without changing the transcriber, selecting a winner or
  widening any product route.
- Change or experiment: the native attempt now writes an owner-only, path-free,
  self-hashed evidence envelope after the terminal receipt. It binds the
  request, terminal receipt, checkpoint, authorisation, worker/source/companion
  identities and exact PCM24 output hashes and geometry. The private MIDI
  evaluator accepts either this envelope or the legacy worker observation,
  revalidates both native outputs and preserves its existing report contract.
- Inputs: the clean `Be Alone` native v2 attempt and the unchanged four-pack
  authorised MIDI comparison for seconds 191–206.
- Model/runtime/checkpoint: no inference rerun. The evaluator consumed the
  already quarantined Kim Vocal 2 PCM24 vocal and used the unchanged production
  pYIN lead plus Basic Pitch register-hypothesis settings at 136 BPM and A=440.
- Evidence and metrics: native evidence self-hash
  `ef418783b15c9a64f188b5f7be9b0612ba491c537c3e2b669021b073f48b6d8c`;
  MIDI-evaluation canonical document SHA-256
  `b901a672c65276cf09514d05056cc912555df241693f1cde864bca4d7cea042a`.
  The primary has 14 notes; the lowest/dominant/top/harmony hypotheses have
  2/17/1/20 notes. The primary MIDI SHA-256
  `65111b1dadbc9daaa7ea015a542a256510bd1b8f3ecbb88a36f55dc63dd5dcc1`
  is byte-identical to both earlier Kim evaluations. Exact-pitch/onset F1 is
  0.5185 against local HTDemucs, 0.6000 against Moises, 0.5600 against Suno A
  and 0.4615 against Suno B; these controls are estimates, not score truth.
  The focused native/evaluator suite passes 197 portable tests plus the trusted
  exact-private-asset static composition test.
- Listening result: no duplicate review was generated because its MIDI audio
  would be identical. The existing blind `Be Alone` Kim-versus-Moises review
  already resolved this exact primary MIDI as `equivalent`.
- Decision: accept exact one-excerpt downstream parity from fixed native
  execution through MIDI evidence. Keep the separator inactive and private;
  this does not establish broad separation quality or product readiness.
- Problems/risks: one excerpt and one unchanged MIDI result cannot establish
  cross-song robustness. The execution still lacks bounded per-stage timings,
  and earlier total wall time varied materially.
- Next smallest step: add safe path-free stage timing to locate the native
  latency, then repeat the full execution-to-MIDI/listening gate on a disjoint
  song before considering any Studio integration.

### 2026-08-03 — fixed native Kim authority chain completed and run privately

- Goal: execute the unchanged authorised `Be Alone` 191–206-second excerpt
  once through the fully composed native fd3–fd7 path, without widening any
  product route or borrowing public separator-acceptance authority.
- Change or experiment: added one developer-only attempt owner that measures
  the exact repository worker, source tree, companion files and authorisation
  receipt; creates a fresh owner-only attempt/staging tree; opens the verified
  native session; acquires and reserves the dedicated private checkpoint lease;
  invokes the one-shot transport; and terminalises unused authority after a
  pre-coordinator failure. A successful attempt now persists the coordinator's
  immutable path-free receipt as owner-only canonical JSON.
- Inputs: exact creator-authorised `Be Alone` 15-second PCM24 model input under
  `be-alone-authorised-191-206-v2`, exact private Kim source/companion pack and
  exact 456,483,463-byte checkpoint. GPU mode remained explicit.
- Model/runtime/checkpoint: the fixed macOS native owner launched the pinned
  `.venv-ai` runtime and worker, loaded Kim Vocal 2 only from inherited fd5,
  read the authorised 661,500-frame 44.1 kHz stereo excerpt, and wrote exactly
  the two quarantined PCM24 roles plus its import-closure claim.
- Evidence and metrics: the first successful run exposed only a caller-side
  JSON diagnostic bug because `mappingproxy` is intentionally not serializable;
  its two stems remained valid. The clean repeat persisted a self-verifying
  receipt with SHA-256
  `950a20550278985381a32df9eb44c37e2b79204652be1fc739d2f306aa3535f7`.
  The receipt records ready/image observation before release, fd4 drain while
  live, network observation before reap, complete group exact reap, mapped-file
  and staging remeasurement, checkpoint remeasurement, fd5 release, lease close
  and terminal native session. `vocals.wav` and `instrumental.wav` are each
  3,969,044 bytes, 44.1 kHz stereo PCM24 with 661,500 frames. Their integer sum
  differs from the authorised PCM24 input by at most one LSB; 87,800 of
  1,323,000 samples differ by that rounding bound. Across the two GPU runs each
  role differed by at most one LSB, so bitwise GPU repeatability is not claimed.
  Four portable attempt-owner tests, one trusted-local full static-authority
  test and the related 24 focused lease/coordinator/one-shot tests pass.
- Listening result: not yet auditioned in this increment; execution provenance
  and exact reconstruction accounting do not establish vocal quality.
- Decision: the previously separate safety layers now form one working private
  native execution chain. Keep the result inactive and private until listening
  and downstream MIDI comparisons are complete.
- Problems/risks: the two runs took roughly 222 and 101 seconds of total wall
  time, substantially longer than earlier isolated inference timings. The
  durable receipt intentionally omits timing and detailed child evidence, so
  the next diagnostic must measure safe per-stage durations without exposing
  paths or process identity. Dyld shared-cache and transient-load coverage also
  remain incomplete.
- Next smallest step: independently verify the persisted receipt and outputs,
  generate a private listening/MIDI comparison from the v2 stems, and add
  bounded path-free stage timing before considering any separator integration.

### 2026-08-03 — private Kim checkpoint descriptor lease verified, not loaded

- Goal: construct truthful private checkpoint authority for the approved Kim
  Vocal 2 evaluation without borrowing the public bake-off acceptance schema
  or fabricating a hidden-corpus result.
- Change or experiment: added a developer-only opaque lease that validates the
  canonical native request, re-verifies the author-hosted upstream licence
  evidence, opens the exact owner-only checkpoint with `O_NOFOLLOW`, retains a
  non-inheritable read-only descriptor, and binds descriptor/path identity to
  the existing descriptor-pinned Safetensors inspection. Recheck and terminal
  close each repeat the identity and full-file inspection. Returned evidence is
  path-free and explicitly grants no execution, model-load, product, selection
  or publication authority.
- Inputs: synthetic sparse files for adversarial portable tests and the exact
  approved local Kim checkpoint for one trusted-local static check.
- Model/runtime/checkpoint: Kim Vocal 2 MLX `model.safetensors`, 456,483,463
  bytes, exact pinned SHA-256, 708 BF16 tensors. The checkpoint was hashed but
  tensor values were not observed or deserialized.
- Evidence and metrics: Ruff passes; five portable lease tests and the related
  fixed-coordinator/one-shot tests pass; the real
  checkpoint acquire/recheck/close test passes in 0.61 seconds. Tests cover
  path-free evidence, exact observation identity, terminal idempotence,
  pathname identity change rejection, single-use reservation, exact native
  session admission/fd5 handoff, coordinator recheck/release/close and absence
  from public CLI/TUI commands.
- Listening result: not applicable; no model or audio was loaded.
- Decision: use this dedicated private lease for the approved Kim experiment.
  The general separator lease remains tied to genuine public bake-off
  acceptance and must not be repurposed for a one-song private evaluation. The
  fixed coordinator and one-shot wrapper now consume the private lease,
  reservation and canonical request directly; their obsolete general worker-V2
  argument has been removed.
- Problems/risks: this made the checkpoint start boundary executable only
  when composed with an exact verified private native session. It is still not
  a product route or separation-quality claim. The preceding log entry records
  the later one-run authority composition and live execution.
- Next smallest step at this checkpoint: construct the exact private native
  session and one-run authority chain around the unchanged authorised
  `Be Alone` excerpt.

### 2026-08-03 — one-shot native transport owner composed, not run

- Goal: remove the last ad hoc caller responsibility for fd3 request and fd4
  result-file assembly before attempting the fixed private Kim coordinator.
- Change or experiment: added one developer-only wrapper that requires the
  already-issued checkpoint lease/reservation, session and
  observations; creates a fresh owner-only transport directory through
  directory-relative operations; writes and reopens the exact framed request;
  supplies distinct write/read descriptions for one empty result inode; calls
  only the fixed coordinator; and removes both frames and the directory after
  success or failure. It preserves the coordinator's original exception if
  cleanup also fails and never deletes the separate output staging tree.
- Inputs: canonical in-memory private Kim requests and dependency-substituted
  coordinator outcomes. No native process, checkpoint, model, source audio or
  output staging content was opened.
- Model/runtime/checkpoint: no backend import or inference occurred.
- Evidence and metrics: five focused one-shot tests and 36 related
  session/coordinator tests pass. They prove the exact request bytes, shared
  result inode, distinct non-inheritable descriptor roles, coordinator
  argument identity, cleanup after coordinator-owned descriptor close,
  preservation of the primary failure, rejection of a non-private transport
  parent and absence from public CLI/TUI command sets. Ruff passes.
- Listening result: not applicable; this increment produced no audio.
- Decision: retain this helper as the sole future transport-file owner around
  the fixed coordinator. It is not a public runner, trust-record constructor
  or separation-quality claim.
- Problems/risks: a real authorised run still needs the exact private
  safetensors lease/reservation/start bridge composed around the existing
  approved Kim checkpoint. It must not reuse the general bake-off acceptance
  record. Pathname-to-`exec` TOCTOU, incomplete dyld
  shared-cache coverage and transient native loads remain open.
- Next smallest step: complete the private lease-to-start authority chain, then
  run the unchanged authorised `Be Alone` excerpt once through this one-shot
  boundary outside the Codex sandbox.

### 2026-08-03 — native failure receipts made disjoint, not run

- Goal: make the fixed private Kim coordinator explain failure without
  confusing a proved no-child start with a child that started and was later
  exactly reaped, and without replacing the first error when cleanup also
  fails.
- Change or experiment: the guarded session now emits a terminal, path-free
  no-start record only for the native launcher's exact code-owned setup or
  `posix_spawn` result with a positive native status. The coordinator composes
  that with the terminal checkpoint lease into a distinct inert receipt. A
  second receipt covers only a started owner whose complete group was drained,
  exactly reaped and released without ownership loss. Safe cleanup stage codes
  are retained in observed order, including repeated child-descriptor cleanup;
  exception text, native status number, PID, PGID and paths are excluded.
  Unknown start state, incomplete session or lease terminalization, and
  incomplete reap deliberately receive no receipt.
- Inputs: dependency-substituted request, session, lease, owner, terminal and
  cleanup evidence plus pure receipt fixtures. No native process, checkpoint,
  model, source audio or output staging was opened.
- Model/runtime/checkpoint: no backend import or inference occurred.
- Evidence and metrics: 51 focused portable tests pass. They cover the two
  non-interchangeable receipt types, self-hashes, path-free and inert policy,
  rehashed tampering, unproven start, duplicate ordered cleanup, cleanup-only
  failure labelling, release failure and a second handshake-cleanup failure
  without loss of the primary error. The complete portable suite passes 2,945
  tests with one expected skip, 11 trusted-local deselections and the existing
  third-party `resampy`/`pkg_resources` warning. The trusted-local installed-AI-
  runtime session check passes, as does the macOS unified-log observer when run
  outside the Codex sandbox. Ruff passes.
- Listening result: not applicable; this increment produced no audio.
- Decision: keep both receipts private and non-authorising. Receipt presence
  proves only the bounded failure lifecycle it records, never separator
  quality or product readiness.
- Problems/risks: the fixed real-worker coordinator still has no authorised
  live model/audio execution evidence. Pathname-to-`exec` TOCTOU, incomplete
  dyld shared-cache coverage and transient native loads remain open.
- Next smallest step: run the broader native and complete portable gates, then
  attempt one fresh authorised excerpt through the fixed coordinator under the
  existing private evaluation boundary.

### 2026-08-03 — exact private AI virtual environment bound, not run

- Goal: prevent the future native Kim worker from silently falling back from
  the explicitly prepared AI environment to the parent process's resolved base
  Python executable.
- Change or experiment: the private session now requires an explicit Python
  launcher path. It preserves that exact virtual-environment invocation for
  native `exec`, while separately resolving and hashing the base executable for
  signed process-image observation. The session also binds `pyvenv.cfg`, the
  environment and `bin` directory identities, the resolved base-runtime root,
  CPython version and disabled system-site-packages policy. Every binding is
  repeated at validation, immediately before start and after exact reap. The
  fixed coordinator now gives the staging verifier these session-bound roots
  instead of deriving a false environment from the resolved executable or the
  parent interpreter.
- Inputs: synthetic virtual environments in portable tests and the existing
  local `.venv-ai` launcher in one trusted-local static session check. No
  checkpoint, model, source audio or output staging was opened.
- Model/runtime/checkpoint: `.venv-ai/bin/python` remains the intended private
  ML runtime; the check measured its launcher/config/base executable only. No
  backend import or inference occurred.
- Evidence and metrics: 27 focused portable session/coordinator tests pass,
  the 151-test related native gate passes and the trusted-local fresh native-
  session check passes. The complete portable suite passes 2,921 tests with
  one expected skip, 11 trusted-local deselections and the existing third-
  party `resampy`/`pkg_resources` warning. Tests prove that the
  guarded spawn receives the unresolved environment launcher, the post-run
  verifier receives distinct environment/base roots, path-free observations
  reveal no local path, system-site packages fail closed and runtime/config
  mutation invalidates the session. The separate macOS unified-log observer
  also passes when run outside the Codex sandbox, which cannot read that host
  log by design.
- Listening result: not applicable; this increment produced no audio.
- Decision: keep the explicit AI-runtime binding inside the sole private future
  coordinator. It remains unavailable to CLI, TUI, Simple, Studio and the
  source graph and does not make separation or quality claims.
- Problems/risks: pathname-to-`exec` TOCTOU still exists; base-runtime files
  outside the virtual environment are measured and observed but not frozen.
  Proven no-start and mixed cleanup-failure receipts remain incomplete.
- Next smallest step: make no-start and mixed cleanup outcomes disjoint and
  path-free, then run one fresh authorised excerpt through the fixed
  coordinator before considering any private activation.

### 2026-08-03 — fixed real-worker coordinator composed, not run

- Goal: replace the remaining loose parent-side Kim lifecycle pieces with one
  fixed, private and non-configurable coordinator while preserving exact cleanup
  and the existing no-product-route boundary.
- Change or experiment: added a developer-only coordinator that validates the
  request and measured session, prepares the network and ready/release
  observers, starts only through the live fd5 lease bridge, binds the exact
  opaque owner, captures the process image and two executable-region
  snapshots, releases the worker, drains bounded fd4 while ownership is live,
  finishes the network observer, supervises and exactly reaps the group, then
  completes native-image, staging, checkpoint-lease, terminal-identity and
  session evidence in one fixed order. Added a separate failed-run session
  terminal transition so a nonzero or signalled but fully drained and exactly
  reaped owner is not left registered as running.
- Inputs: dependency-substituted request, session, lease, descriptors,
  observers, owner, result and staging evidence only. No native process,
  accepted checkpoint, model, authorised source, audio or staging tree was
  opened by these tests.
- Evidence and metrics: the success test proves observer preparation before
  start; ready/image observation before release; fd4 drain before observer
  finish and reap; post-reap image/staging/checkpoint verification; private
  PID/PGID consumption only through the opaque owner matcher; and session then
  fd5/lease terminalization. A forced pre-release process-image failure proves
  observer abort, complete group cleanup, failed-session terminalization and
  lease closure. The related portable native suite passes 90 tests with two
  deliberate deselections. The complete portable suite passes 2,917 tests with
  one expected skip and 11 trusted-local deselections; Ruff passes.
- Listening result: not applicable; this increment produced no audio.
- Decision: retain this as the sole future real-worker parent composition and
  keep it absent from CLI, TUI, Simple, Studio and source-graph routes. Its
  substituted tests prove ordering and cleanup, not live execution provenance
  or separation quality.
- Problems/risks: the measured session currently resolves `sys.executable` to
  the base Python image. In a virtual environment that can discard the launcher
  context and its MLX packages even though the signed process image is correctly
  bound. Proven-no-start and mixed cleanup-failure receipts also remain
  separate work. A real Kim run is not yet authorised by this increment.
- Next smallest step: preserve and measure the exact virtual-environment
  launcher separately from its resolved process image and runtime roots, then
  add disjoint no-start and mixed-failure receipts before attempting one fresh
  authorised excerpt through this coordinator.

### 2026-08-03 — real-worker staging and session terminal boundaries fixed

- Goal: remove the two remaining caller-shaped claims between a completed real
  native worker and the future fixed parent coordinator: private artifact
  verification and the running-session-to-terminal transition.
- Change or experiment: added a developer-only parent verifier that validates
  the real child-result contract, fd5-only checkpoint claim, fixed sandbox
  canaries and post-CPython signal state; reopens the exact authorised source;
  independently verifies both PCM24 quarantine files and additive closure;
  reopens the canonical private Python import-closure claim and every claimed
  module; then repeats the source, closure and quarantine checks before
  returning path-free evidence. Added a one-use native-session transition that
  accepts only normal zero exit, complete group drain, exact reap and released
  ownership from the exact retained opaque owner, remeasures all session
  bindings and removes that owner from the running registry.
- Inputs: synthetic owner-only staging with canonical 4,096-frame PCM24 source,
  two-role quarantine and one-file Python closure; dependency-substituted
  opaque owner and terminal observations.
- Model/runtime/checkpoint: no native process, model, accepted checkpoint or
  user audio was opened. Numpy is imported only inside the private verifier.
- Evidence and metrics: the focused staging/session suite passes 24 tests,
  including closure-byte tampering, unexpected staging content, forbidden
  checkpoint pathname reopen, incomplete ownership, non-zero exit, wrong owner
  and terminal replay. The complete portable suite passes 2,912 tests with one
  expected skip, 11 trusted-local cases deselected and the existing
  `resampy`/`pkg_resources` warning. Ruff passes for all changed source and
  tests.
- Listening result: not applicable; this increment validates execution
  provenance and cleanup, not separation quality.
- Decision: accept both contracts as fixed private prerequisites. Keep their
  limits explicit: staging evidence does not claim checkpoint-lease, session
  or live-observer verification, and the terminal transition does not supervise
  a process itself. No CLI, TUI, Simple, Studio or source-graph route is added.
- Problems/risks: the real coordinator still must prepare the observers, call
  the live lease-to-start bridge, drain/decode fd4 while the owner is live,
  complete observers and whole-group supervision, invoke these new boundaries,
  remeasure/release/close fd5 and the lease, consume PID/PGID only through the
  owner matcher and emit one path-free terminal receipt on every outcome.
- Next smallest step: compose that fixed coordinator with substituted
  components first and prove success plus failure cleanup before any authorised
  Kim excerpt is run through it.

### 2026-08-03 — fixed model-free macOS parent adapter proved live

- Goal: replace the two-phase lifecycle's caller-supplied hooks with one fixed
  developer-only adapter before allowing an accepted checkpoint or authorised
  audio into the native path.
- Change or experiment: added a private Darwin adapter that owns the concrete
  order for the kernel Sandbox denial broker, fd6/fd7 ready/release gate,
  opaque-owner process-image match, two stable executable-region snapshots,
  bounded fd4 decode, live-observer finish, whole-group supervision, exact
  reap, mapped-file remeasurement and three-entry staging verification. It
  calls only the fixed native sandbox method and fixed stdlib bootstrap. Its
  fd5 input must be a small placeholder; a checkpoint-sized descriptor is
  rejected. A forced wrong-CDHash run is rejected before worker release and
  still drains and exact-reaps the owned group.
- Inputs: the fixed stdlib frame-bootstrap worker, a canonical model-free fd3
  request, empty fd4 file, small fd5 placeholder, fresh owner-only staging,
  freshly provenance-built native extension, signed Python process image and
  `/usr/bin/sandbox-exec`.
- Model/runtime/checkpoint: no model or accepted checkpoint. The worker read
  zero fd5 bytes, imported no model and read no audio. The accepted 456,483,463-
  byte Kim checkpoint is explicitly outside this adapter.
- Evidence and metrics: eight portable adapter cases cover transport/staging,
  exact result decode, empty-result timeout, oversized-result rejection,
  checkpoint-sized-fd5 rejection, child-result checkpoint-read rejection and
  spawn-binding rejection, plus absence from every public and direct-TUI
  command route. The related portable parent/image suite passes 38 tests. One
  trusted-local macOS canary passed both the complete native
  lifecycle and forced process-image failure cleanup. It also exposed and
  corrected an older policy mismatch: a kernel executable mapping may be
  backed by a regular library without a filesystem execute bit, so mapped-file
  evidence now requires stable regular hashed bytes rather than launchability.
  The complete portable regression suite passes 2,904 tests, with one expected
  skip and the 11 trusted-local cases deliberately deselected.
- Listening result: not applicable; no audio was opened or produced.
- Decision: accept this as concrete model-free native-parent evidence. Keep it
  developer-only and unreachable from CLI, TUI, Simple, Studio and the source
  graph. It is not Kim execution or separator-quality evidence.
- Problems/risks: the real measured Kim session, live checkpoint lease and
  reservation, guarded start, import-closure/quarantine staging verifier and
  lease terminal receipt are still not composed through this adapter. Runtime,
  worker and provider invocation retain their documented pathname TOCTOU; dyld
  shared-cache and transient-load coverage remain incomplete.
- Next smallest step: build one fixed real coordinator that reuses this proven
  observer/result/supervision boundary while composing the existing live
  lease-to-start bridge and terminal lease closure. Prove its failure paths
  with substituted artifacts before running one previously authorised excerpt.

### 2026-08-03 — two-phase native parent order made explicit and fail-closed

- Goal: replace the older substituted lifecycle's unsafe assumption that a
  final live observation could be sealed before reap and that fd4 could be
  drained only after supervising the worker.
- Change or experiment: added a private v2 dependency-substituted parent
  exercise. It prepares the observer handle before spawn, requires the exact
  opaque owner, captures readiness and releases the worker, drains and validates
  fd4 while ownership is live, consumes the live observers, exact-reaps the
  process group, and only then seals deferred mapped-file evidence and verifies
  staging. Invalid owners are never passed to observer or supervisor hooks.
  Result, observer and post-reap failures retain bounded cleanup evidence;
  unconsumed prepared observers are explicitly aborted.
- Inputs: frozen request/result documents, one model-free opaque-owner stand-in,
  opaque capture tokens and dependency-substituted lifecycle callbacks.
- Model/runtime/checkpoint: dependency-substituted only. No native process,
  checkpoint, model, authorised audio, staging directory, kernel log stream or
  executable region was opened or run.
- Evidence and metrics: seven new cases cover exact success order, fd4 failure,
  observer-finish failure, invalid-owner rejection, post-reap sealing failure
  and absent ready or observer captures. The focused parent/lease/session suite
  passes 36 tests and Ruff passes.
- Listening result: not applicable; no audio was read or produced.
- Decision: accept the v2 ordering as the target parent contract and retain v1
  only as compatibility evidence. This is still substituted wiring, not real
  Kim execution or separator evidence.
- Problems/risks: the fixed macOS adapter still needs to bind concrete network,
  process-image, ready/executable-region, fd4, whole-group supervisor, staging,
  lease remeasurement and terminal-receipt operations to this order. A bounded
  fd4 reader must ensure the real child cannot block indefinitely or exceed the
  result-frame contract.
- Next smallest step: implement one fixed model-free macOS adapter over the
  existing owner-bound primitives, then exercise it with the fixed stdlib
  worker before permitting a live Kim checkpoint or authorised audio.

### 2026-08-03 — native Kim fd5 lease handoff bound without opening the checkpoint

- Goal: remove the raw checkpoint-descriptor gap between the existing live
  lease and the guarded native start without exposing fd5 or treating the old
  blocked worker record as execution authority.
- Change or experiment: added one private lease-module bridge that runs under
  the exact lease lock, revalidates the live reservation and observation,
  cross-binds the Kim request's checkpoint hash, byte count and path to the
  lease, cross-binds its worker hash to the measured native session, mints the
  one-use session admission internally and passes the retained fd5 only to the
  guarded start stack frame. A successful start deliberately leaves the exact
  reservation and lease active for later supervision, post-run remeasurement,
  release and close. Binding failures occur before transport ownership is
  transferred to the guarded start.
- Inputs: one small model-free regular-file descriptor, path-free frozen lease,
  reservation, worker-request and session stand-ins, canonical Kim native
  request values and substituted admission/start functions.
- Model/runtime/checkpoint: dependency-substituted only. The accepted Kim
  checkpoint was not opened, hashed, read or deserialized; no native process,
  model, audio, source companion, network observer or staging artifact ran.
- Evidence and metrics: eight new tests cover exact fd5 handoff, retained lease
  ownership, checkpoint identity drift, blocked-worker binding drift, fixed
  worker drift, checkpoint-path drift, wrong reservation and substituted
  worker-request objects and incomplete binding evidence. All 29 focused
  bridge/session/parent tests pass, and Ruff passes.
- Listening result: not applicable; no audio was read or produced.
- Decision: accept the lease handoff as a private non-exporting composition
  boundary. It is still code wiring, not live lease execution provenance,
  separator evidence or product authority.
- Problems/risks: the bridge has not yet been exercised with one concrete live
  lease and native owner. The two-phase process-image, network and executable-
  region observers still need to be composed around readiness/release and
  whole-group supervision; fd4 decode, independent staging verification,
  post-run fd5 remeasurement, reservation release, lease close and one terminal
  receipt remain outstanding. Source/companion evidence is carried by the Kim
  request but is not yet independently rebound by this narrow checkpoint
  bridge.
- Next smallest step: build the model-free parent coordinator around this
  bridge, separating live observer capture from post-reap sealing so the same
  exact opaque owner can drive readiness, release, supervision, result decode,
  staging verification and terminal projection without opening the accepted
  checkpoint or authorised audio.

### 2026-08-03 — guarded native Kim start boundary exercised without a process

- Goal: make the exact fixed C spawn method reachable only through the measured
  session and one-use request admission while leaving checkpoint ownership and
  the live model outside this increment.
- Change or experiment: added one private guarded start function that validates
  the canonical fd3 frame, distinct non-inheritable fd3–fd7 access/type
  geometry, an empty fd4 result, fixed checkpoint byte size and a fresh
  owner-only staging identity. It repeats descriptor, staging, worker, runtime,
  sandbox-provider, native-method and owner-type measurements immediately
  before consuming the exact admission and making the module's only bound C
  method call. The parent closes fd3/fd4/fd6/fd7 on success and every failure,
  deliberately leaves fd5 with its separate lease owner, and retains only the
  exact opaque native owner after `started_owned` plus parent cleanup.
- Inputs: canonical request frames, sparse synthetic fixed-size checkpoint
  descriptors, regular-file request/result transports, real local pipes,
  owner-only temporary staging directories and substituted spawn outcomes.
- Model/runtime/checkpoint: dependency-substituted only. No native process was
  created, no checkpoint byte was read, and no model, audio, source companion
  or quarantine artifact was opened.
- Evidence and metrics: 15 portable session/admission/start tests pass. They
  exercise the exact success path, wrong ready/release geometry, request-frame
  drift, non-private staging, an exact native no-start result and a native-call
  exception. Every transferred child-side descriptor closes, fd5 remains open
  at offset zero, an issued admission is retired or consumed once, and only an
  exact started owner becomes the registered running owner. The related
  session/parent/transport/worker regression passed 67 tests, the trusted-local
  real static-session remeasurement passed in 1.34 seconds, and the complete
  portable repository suite passed 2,881 tests with one skip, 10 trusted-local
  deselections and only the existing third-party `resampy/pkg_resources`
  warning.
- Listening result: not applicable; no audio was read or produced.
- Decision: accept the guarded start boundary as code wiring only, not process
  provenance, separator evidence or a product route.
- Problems/risks: the caller still needs a concrete request/result/handshake
  constructor under the existing live checkpoint lease. Actual process-image,
  kernel-network and executable-region observers, whole-group supervision,
  fd4 decode, independent quarantine/closure verification and the terminal
  receipt are not yet composed around this start. Runtime, worker and sandbox
  provider remain remeasured pathname exec bindings.
- Next smallest step: compose one model-free private coordinator from the live
  fd5 lease, guarded start, concrete opaque-owner observers and the existing
  dependency-substituted parent lifecycle before opening the accepted Kim
  checkpoint or an authorised excerpt.

### 2026-08-02 — fixed native Kim session and request-bound admission proved

- Goal: bind the real fixed worker and native sandbox method to a fresh measured
  macOS session while keeping the fd3 request value separate from spawn
  authority.
- Change or experiment: added a private opaque session that wraps one freshly
  built verified native-launcher session, binds the exact fixed Kim worker,
  `/usr/bin/sandbox-exec`, runtime, native spawn method and nonconstructible
  owner type, and remeasures those bindings. Added a separate nonconstructible,
  noncopyable, nonserializable admission that binds the exact session, request
  hash, run nonce, repository root and worker SHA, changes the session to one
  outstanding-admission state and can be consumed only once. Abandoning an
  unconsumed admission restores the measured session to ready but permanently
  retires its nonce.
- Inputs: synthetic canonical requests for unit tests, plus one fresh real
  native build/import and static worker/provider remeasurement on the
  development Mac.
- Model/runtime/checkpoint: the trusted-local canary binds the current Python
  runtime, fixed worker and Apple sandbox provider. It starts no child and opens
  no checkpoint, model, audio, source, companion or staging artifact.
- Evidence and metrics: 42 portable focused tests pass and the one trusted-local
  fresh-session canary passes in 1.24 seconds. Tests reject copied or serialized
  capabilities, replacement observations, another request, worker/repository
  mismatches, nonce reuse, repeat admission consumption and cross-process use.
- Listening result: not applicable; no audio was read or produced.
- Decision: accept the session and admission as private prerequisites only.
  Neither the session observation nor fd3 bytes grants execution authority.
- Problems/risks: descriptor creation, live checkpoint lease attachment, the
  native spawn call, actual owner-bound observers, staging verification and
  terminal receipt remain unimplemented. The runtime, worker and sandbox
  provider are remeasured path bindings and retain execution-time TOCTOU.
- Next smallest step: add the one guarded native-call adapter that constructs
  fd3–fd7, consumes the exact admission immediately before the fixed C method
  and guarantees bounded supervision and descriptor cleanup on every outcome.

### 2026-08-02 — native Kim parent lifecycle exercised with substituted dependencies

- Goal: fix the private parent-side order and failure behaviour before allowing
  the native adapter to open the accepted checkpoint or authorised audio.
- Change or experiment: added a private dependency-substituted lifecycle core
  that requires one exact opaque native-owner type, observes and releases the
  worker before supervision, requires normal zero exit plus complete group
  drain and exact reap, decodes fd4 against the exact fd3 request, requires an
  independent path-free staging verification, consumes the worker PID/PGID
  only through the owner's boolean matcher and derives the existing terminal
  projection. Generalised the terminal-projection helper name while retaining
  the model-free compatibility entry point used by earlier canaries.
- Inputs: pure request/result frames, an in-memory exact-shape owner and injected
  observer, supervisor, result-reader and staging-verifier functions. A forced
  observer failure and three malformed observer claims prove that supervision
  still runs before failure is returned.
- Model/runtime/checkpoint: no native extension was built or imported; no
  process, checkpoint, model, audio or staging path was opened.
- Evidence and metrics: 58 focused parent, transport, worker and supervision
  tests pass. The successful exercise emits a self-hashed, path-free record
  whose effects and every product permission are false; wrong worker identity,
  incomplete staging verification and unsafe live observations fail closed.
- Listening result: not applicable; no audio was read or produced.
- Decision: accept the dependency-substituted lifecycle core as the parent
  orchestration contract, not as real-model execution evidence and not as a
  separator route.
- Problems/risks: the real macOS adapter still needs to create and measure the
  descriptors and files, consume one fresh live admission, invoke the fixed C
  method, attach the actual process-image/network/native-image observers and
  perform the concrete closure and PCM24 quarantine verification. Runtime,
  worker and sandbox-provider execution are still pathname based.
- Next smallest step: connect this lifecycle order to one private macOS adapter
  and prove the complete native lifecycle with model-free substitute artifacts
  before opening the accepted checkpoint or authorised excerpt.

### 2026-08-02 — fixed real native Kim worker adapter implemented, not run

- Goal: replace the model-free fd3–fd7 bootstrap with a fixed adapter capable
  of running the already-audited Kim bridge without yet creating a live launch
  or product route.
- Change or experiment: added
  `scripts/private-melroformer-native-worker.py`, whose first effectful
  user-code action marks descriptors 3–7 non-inheritable, and a separate
  `_separation_melroformer_native_worker.py` execution core. The worker derives
  the repository package root only from its parent-bound script location,
  validates the canonical fd3 request, hashes its own fixed source, verifies
  source and companion manifests, supplies fd5 to the audited Safetensors/MLX
  loader, uses fd6/fd7 for the existing post-inference ready/release boundary,
  writes only a fresh PCM24 quarantine and private closure claim inside the
  staging tree, and emits a path-free fd4 result. The path-bearing Python
  import-closure claim is stored as a private staging artifact for later
  independent parent verification rather than embedded in the result frame.
- Inputs: small descriptor fixtures and monkeypatched model, inference,
  quarantine and closure operations. No Kim checkpoint, MLX model or authorised
  audio was opened.
- Model/runtime/checkpoint: no model execution. The focused contract test proves
  that the core passes the already-open checkpoint descriptor to the loader and
  closes it without treating the checkpoint pathname as the tensor-load source.
- Evidence and metrics: Ruff passes and 88 focused native-worker, supervision,
  frame, Safetensors and bridge tests pass. The synthetic core exercise
  revalidates the fd4 result against the exact request, retains no absolute path
  and keeps publication, automatic selection and product routing false.
- Listening result: not applicable; no audio was read or produced.
- Decision: mark the fixed real native entrypoint and fd5 attachment as
  implemented in source, but not live-exercised. The active Kim evaluation path
  remains the unchanged subprocess route.
- Problems/risks: no parent executor yet supplies a fresh live admission,
  remeasures the fixed worker/runtime/provider, attaches the opaque-owner
  process-image, network and executable-region observers, verifies the private
  closure/quarantine artifacts, consumes the result PID/PGID or derives the
  terminal projection. Runtime, worker and sandbox-provider execution remain
  pathname based.
- Next smallest step: implement the private parent adapter around the existing
  native launcher and run a model-free dependency-substituted lifecycle through
  that exact adapter before opening the accepted checkpoint or authorised audio.

### 2026-08-02 — Kim checkpoint loader accepts inherited fd5

- Goal: remove the checkpoint-path reopen from the future native Kim worker
  before connecting the real model to the new owner and sandbox lifecycle.
- Change or experiment: added path-free Safetensors static inspection for an
  already-open descriptor and an optional descriptor transport to the existing
  audited Kim loader. The descriptor must already be non-inheritable, read-only,
  single-link, regular and the exact accepted size and SHA-256. Static inspection
  uses positioned reads and leaves the caller's offset unchanged. MLX receives
  a non-inheritable duplicate of that same descriptor, not a reopened path.
- Inputs: synthetic Safetensors containers and small descriptor fixtures only.
  No accepted Kim checkpoint, model or authorised audio was opened.
- Model/runtime/checkpoint: no model. Tests substitute bounded fixture identities
  for the real 456,483,463-byte checkpoint identity.
- Evidence and metrics: 36 direct inspection/bridge tests and 80 affected Kim
  bridge, authorised-worker, challenger, supervision and inspection tests pass.
  Tests prove path-free evidence, offset-neutral static inspection, exact bytes
  through the yielded stream, and rejection of inheritable or writable files.
- Listening result: not applicable; no audio was read or produced.
- Decision: accept descriptor-native checkpoint inspection and tensor-load
  plumbing as implemented. A later fixed real worker adapter now calls it, but
  that adapter has not been launched and remains outside every product route.
  Every CLI, TUI, Simple, Studio and automatic-selection route remains disabled.
- Problems/risks: at this point in the log the fixed native worker entry point
  was still absent. The request carries a checkpoint pathname for private
  evidence, and the current authorised worker still follows its unchanged
  subprocess path.
- Next smallest step: add the fixed real worker adapter whose first user-code
  action hardens fds 3–7, validates fd3, imports the audited bridge and passes
  fd5 to this loader without reopening the checkpoint path.

### 2026-08-02 — native Kim sandbox launch shape proved model-free

- Goal: put the fd3–fd7 bootstrap behind the same fixed macOS isolation shape
  required by the real authorised Kim worker before opening its checkpoint.
- Change or experiment: added a third private native entry point. The native
  boundary accepts only `/usr/bin/sandbox-exec`, constructs the fixed profile
  itself around one validated staging path, denies all network operations,
  child forks and writes outside that tree, supplies a fixed offline
  environment and starts isolated Python without `-S` so the future pinned MLX
  runtime can load. The model-free frame bootstrap now has an explicit sandbox
  mode that deliberately attempts loopback, `fork()` and an outside-tree
  create after completing the existing request and ready/release protocol.
- Inputs: synthetic request/checkpoint fixtures, fresh private staging,
  `/usr/bin/sandbox-exec`, a freshly provenance-built Darwin launcher and the
  fixed stdlib bootstrap. No authorised audio or model asset.
- Model/runtime/checkpoint: no model. The request still names the accepted Kim
  checkpoint, but fd5 remains unread. Live proof used the locally valid signed
  Homebrew Python 3.13 canary runtime because strict validation of the separate
  system and Python 3.12 images currently reports invalid signatures. The
  freshly built native source hash is
  `fa7d1fe2ad4512fbe6ce280439e957fe544b9ca0037a02e6483145d76e9c3e2c` and
  its build-contract hash is
  `01eb89ccc95caa09daa95485be12309cd0fc73b7c70d707fc268d38128267843`.
- Evidence and metrics: the isolated sandbox-only proof validates fd3, blocks
  for owner-bound process-image inspection, completes the exact release,
  verifies fd4 in the parent, consumes and discards private PID/PGID through
  the opaque owner, observes `EPERM` for network, fork and outside write, then
  proves normal zero exit, whole-group drain and exact reap. Focused static and
  contract tests pass. The unrestricted portable suite passes with
  `2851 passed, 1 skipped, 9 deselected`; its outer Codex-sandbox run was
  intentionally discarded because that sandbox forbids the loopback sockets
  and local tool operations exercised by existing tests. The separate trusted
  sandbox-frame canary passes under the strictly signed Homebrew Python 3.13
  runtime.
- Listening result: not applicable; no audio is opened or produced.
- Decision: accept the fixed native sandbox launch shape as one more real-run
  prerequisite. Keep `fixed_real_worker_native_entrypoint_implemented: false`,
  the current Kim subprocess route unchanged and every product route false.
- Problems/risks: this still executes the model-free bootstrap. It does not
  open or descriptor-load the real checkpoint, import MLX, read authorised
  audio, write stems or bind the final parent verification projection. Runtime,
  worker and sandbox-provider execution remain pathname based.
- Next smallest step: implement the fixed real Kim fd3/fd4 worker adapter,
  make fd5 the checkpoint load source, and run one previously authorised
  excerpt under this exact owner/sandbox lifecycle against the unchanged
  subprocess evidence.

### 2026-08-02 — native Kim frame bootstrap proved model-free

- Goal: make the fixed fd3 request/fd4 result contract executable under the
  opaque native owner without opening the Kim checkpoint or authorised audio.
- Change or experiment: added a fixed stdlib-only bootstrap worker and upgraded
  the macOS canary to matrix v9. The worker hardens descriptors 3–7 as its first
  effectful user-code action, decodes and validates the exact canonical request,
  uses the existing Kim ready/release pipe protocol, and writes the exact
  path-free result frame. The parent validates the result against the original
  request, submits the transient private PID/PGID to the owner's boolean matcher
  and discards them before retaining the report.
- Inputs: synthetic path-bearing request values, a tiny unread checkpoint-file
  fixture, two private pipes, the freshly built Darwin launcher and the fixed
  bootstrap worker. No source audio, MIDI or model asset.
- Model/runtime/checkpoint: isolated current Python plus the provenance-bound
  native launcher. The request binds the already accepted Kim checkpoint hash
  and byte count, but the worker reads zero bytes from fd5 and loads no model.
- Evidence and metrics: two live invalid cases, a trailing frame byte and a
  tampered request self-hash, both fail before readiness, write no result and
  are group-drained and exact-reaped. The valid case blocks for owner-bound
  process-image inspection, completes the exact release, produces a
  parent-validated result, matches and discards private process identity, exits
  zero, closes temporary pipes and leaves the parent descriptor table stable.
  Sixty-five focused/static/live tests pass and Ruff is clean. The complete
  repository suite passes 2,858 tests with one platform skip and the existing
  third-party `resampy`/`pkg_resources` deprecation warning.
- Listening result: not applicable; no audio is opened or produced.
- Decision: accept the model-free bootstrap as the final framed-transport proof.
  Keep real-worker native supervision, separator activation and every public
  CLI/TUI/Simple/Studio/source-graph route false.
- Problems/risks: the bootstrap deliberately opens no request path or
  checkpoint, does no inference and does not derive the full terminal projection
  used by the future real worker. Runtime and worker execution remain pathname
  based, and the current authorised Kim worker still uses its subprocess route.
- Next smallest step: adapt one fixed authorised Kim worker invocation to the
  same request/result bootstrap and opaque-owner lifecycle, run one previously
  authorised excerpt, and compare its result with the unchanged subprocess
  evidence before considering any route migration.

### 2026-08-02 — native Kim request/result frames fixed model-free

- Goal: define the bounded data carried on native descriptors 3 and 4 before
  writing a real-worker bootstrap or granting any new execution authority.
- Change or experiment: added a pure request/result transport contract with
  fixed eight-byte magics, big-endian bounded lengths, canonical JSON,
  duplicate-key rejection, exact field sets and semantic self-hashes. The
  private request may contain six absolute local paths but is explicitly not
  execution authority. It binds a fresh nonce, the exact accepted Kim
  checkpoint identity, all required artifact hashes, the full owner-bound
  observation policy and descriptors 3–7. The path-free private result binds
  back to the same request and child-result hashes; PID/PGID exist only in that
  transient result so the future parent can submit them to the opaque owner's
  boolean matcher.
- Inputs: synthetic value fixtures only. No file, descriptor, process, model,
  checkpoint, audio or network operation.
- Model/runtime/checkpoint: no model or checkpoint opened. The contract accepts
  only checkpoint SHA-256
  `312c38e5b698f8dfaa4d6064e8f79010744825828917871a9d22673a43eb7fe5`
  and 456,483,463 bytes, matching the already accepted Kim conversion asset.
- Evidence and metrics: 103 focused transport, handshake, supervision, source,
  build and live-v8 tests pass. Mutations cover relative/root/URL/duplicate
  paths, the wrong checkpoint, descriptor or execution-policy drift, serialized
  authority expansion, noncanonical/duplicate/truncated/trailing frames,
  request/nonce/hash mismatches, invalid private process identities and Unix or
  Windows paths in results. Ruff passes. The complete repository suite passes
  2,857 tests with one platform skip and the existing third-party
  `resampy`/`pkg_resources` deprecation warning.
- Listening result: not applicable; this is pure value validation.
- Decision: accept the frame contract as preparation only and keep the native
  real-worker entry point blocked. A serialized request remains non-authority,
  and a worker result remains an unverified claim until exact owner and parent
  artifact/output verification complete.
- Problems/risks: there is no fixed native bootstrap that consumes these frames
  yet. The path-bearing request is private but still requires strict parent
  construction and lifetime controls. The current real worker still expects
  CLI arguments, uses the subprocess route and has not been adapted to fd3/4.
- Next smallest step: build one fixed stdlib bootstrap that hardens descriptors
  3–7 first, decodes this request, imports no model in canary mode and emits a
  bound result. Add model-free failure and exact-reap tests before any authorised
  Kim excerpt is run.

### 2026-08-02 — native Kim ready/release transport proved model-free

- Goal: prove the exact descriptor and lifecycle shape needed by the existing
  Kim post-inference native-image handshake before migrating the authorised
  model worker from its subprocess supervisor.
- Change or experiment: added a second fixed private native entry point that
  reuses the same nonconstructible child owner and shared `posix_spawn`
  implementation. It maps regular-file request/result/checkpoint transports to
  descriptors 3/4/5 and the existing ready-write/release-read pipes to 6/7. A
  fixed stdlib-only worker emits a valid Kim readiness claim with dummy hashes,
  blocks until the parent verifies its signed process image, accepts only the
  exact existing release bytes, writes one bounded path-free result, exits zero
  and is group-drained and exact-reaped. Swapped pipe access is rejected before
  spawn.
- Inputs: freshly provenance-built private Darwin extension, current isolated
  Python runtime, three synthetic regular files, two private pipes and the
  fixed ready/release worker. No source audio, MIDI, model or checkpoint.
- Model/runtime/checkpoint: no model or checkpoint. Updated native source
  SHA-256 is
  `10fc9911b89a5093e87f4d64d466cebcd1ae3e26b49ab3a2601b5b189a2f64a4`;
  updated build-contract SHA-256 is
  `7671be0c6a25f0a5642a5f6076a6979388a4eb5f53e5a759671a587f84ebcfac`.
- Evidence and metrics: 95 focused handshake, supervision, source, build and
  live-matrix tests pass. The live macOS v8 matrix proves invalid access is a
  no-start failure; valid readiness blocks before release; the owner-bound
  process-image match succeeds while blocked; release leads to normal exit 0,
  group emptiness and exact reap; spawn does not change the parent descriptor
  table; and all temporary pipe ends close. Ruff passes. The complete
  repository suite passes 2,828 tests with one platform skip and the existing
  third-party `resampy`/`pkg_resources` deprecation warning.
- Listening result: not applicable; the worker reads no audio and creates no
  MIDI or separation.
- Decision: accept the fixed five-descriptor transport as the final model-free
  prerequisite for a narrowly reviewed Kim migration. Keep
  `fixed_real_worker_native_entrypoint_implemented: false`; the real authorised
  Kim route remains on its subprocess supervisor.
- Problems/risks: the test claim uses dummy hashes and does not import MLX,
  open the checkpoint or process audio. Runtime and worker invocation still use
  pathnames, and the model worker's argument/request/result adaptation has not
  yet been moved behind the native owner.
- Next smallest step: design the fixed real-worker request/result adapter and
  its failure projections around these exact descriptor targets. Run one
  authorised Kim excerpt only after that adapter's model-free static and
  failure tests pass.

### 2026-08-02 — combined fixed-worker native bridge proved model-free

- Goal: prove that the three owner-bound observers and the native terminal
  projection can describe one exact execution before changing the authorised
  Kim Vocal 2 worker route.
- Change or experiment: added a fixed stdlib-only combined worker and canary
  matrix v7. One opaque native owner now spans the worker's self-sandboxing
  exec transition, PID-free ready marker, signed process-image match, two
  stable executable-region snapshots, one deliberate loopback denial, private
  worker PID/PGID boolean match, normal zero exit, whole-group drain and exact
  leader reap. A code-owned projection consumes the private identity only for
  the owner's boolean match and returns no raw PID, PGID, path or destination.
- Inputs: freshly provenance-built private Darwin extension, current isolated
  Python runtime, three fixed regular-file transports and the fixed combined
  worker. No source audio, MIDI, model or checkpoint.
- Model/runtime/checkpoint: none. The native C source and build-contract hashes
  remain unchanged from matrix v6; this increment needs no new PID-returning or
  signal-authority native method.
- Evidence and metrics: 66 focused source, helper, build and supervision tests
  pass. The live macOS v7 matrix passes and proves one deliberate owned denial,
  zero other owned denials, stable mapped-image evidence, a hash-bound redacted
  worker result, normal exit 0, group emptiness, exact reap and a validated
  path-free terminal projection from the same owner. The complete repository
  suite passes 2,826 tests with one platform skip and the existing third-party
  `resampy`/`pkg_resources` deprecation warning.
- Listening result: not applicable; the worker reads no audio and creates no
  MIDI or separation.
- Decision: accept the model-free combined bridge as the prerequisite proof.
  Keep `fixed_real_worker_native_entrypoint_implemented: false` and leave the
  authorised Kim route on its existing subprocess supervisor.
- Problems/risks: this proves the orchestration shape with a fixed canary, not
  the real checkpoint/audio worker. Runtime and worker invocation still use
  pathnames, dyld shared-cache and transient-load coverage remain incomplete,
  and mapped-file remeasurement is not mapped-memory byte proof.
- Next smallest step: design the narrow native Kim worker entry point and its
  explicit ready/release transport. Do not run the model until that bridge has
  static, failure and model-free tests and an explicit private-run review.

### 2026-08-02 — worker-ready executable regions bound to opaque native owner

- Goal: remove the post-inference executable-region inventory's last raw-PID
  dependency before designing a real-worker native entry point.
- Change or experiment: added `snapshot_owned_executable_regions` to the
  nonconstructible Darwin child owner. It calls `proc_pidinfo` against only
  the internally retained live child, returns a bounded transient region
  snapshot without PID/PGID, and rechecks ownership and liveness before and
  after enumeration. Canary matrix v6 adds a fixed stdlib-only worker that
  loads seven fixed native modules, emits one PID-free ready marker and stays
  alive. Only after that marker does the parent take two owner-bound snapshots,
  require stability, hash and statically inspect each file-backed mapping,
  terminate the private group, exact-reap it and remeasure every file.
- Inputs: current isolated Python runtime, freshly provenance-built private
  Darwin extension, three fixed regular-file transports and the fixed
  model-free ready worker. No audio, model or checkpoint input and no network
  operation.
- Model/runtime/checkpoint: no model or checkpoint. The pinned native source
  SHA-256 is `997a3f21386a9af9c79fbfb5a96a2947dfc37fa468296cde4f3867a01148a06f`;
  the updated build-contract SHA-256 is
  `89530410bf6f6c08fcacb246e002ed22fe1b74a0f748e8d59802f3c73fc3f130`.
- Evidence and metrics: the focused source, build, helper and live-matrix
  tests pass. The live v6 canary observed the PID-free marker before two
  matching executable-region snapshots, found the main signed Python process
  image exactly once, retained only a path-free artifact-manifest hash, then
  proved whole-group termination, group emptiness, exact reap and unchanged
  parent descriptors. The complete repository suite passes 2,823 tests with
  one platform skip and the existing third-party `resampy`/`pkg_resources`
  deprecation warning; Ruff and diff checks pass.
- Listening result: not applicable; no audio, MIDI or separation changed.
- Decision: retain the native-owner executable-region snapshot and v6
  worker-ready canary as the third owner-bound primitive. Mark the primitive
  implemented, but keep the Kim Vocal 2 route on its current subprocess
  supervisor.
- Problems/risks: executable paths cross the private native/Python boundary
  transiently so their files can be measured, although no path or process ID
  enters the report. Reopened file bytes are not proof of mapped memory bytes;
  dyld shared-cache constituents and transient loads remain incomplete.
  Pathname TOCTOU is not closed. The native entry point still cannot run the
  real worker with its ready/release transport, and no product route changed.
- Next smallest step: completed by model-free canary matrix v7 above. Only
  after that proof should a narrowly reviewed private authorised Kim worker
  migration be designed.

### 2026-08-02 — single-use network stream bound to opaque native owner

- Goal: remove the kernel-network observer's need for a caller-supplied target
  PID before considering any real-worker native bridge.
- Change or experiment: added a factory-only, non-copyable, non-serializable
  owner-bound observation broker. It starts the existing bounded
  `/usr/bin/log stream` before native spawn and, at completion, submits each
  transient kernel-reported event PID to the opaque owner's existing
  `matches_pid_and_pgid` method. The owner never returns its PID/PGID. The
  broker retains only verified counts, consumes itself on success, mismatch or
  abort, and closes its pipes deterministically. Canary matrix v5 adds one
  fixed stdlib-only worker that replaces itself through `sandbox-exec`, denies
  all network operations, attempts only IPv4 loopback port 9, emits a PID-free
  result and remains alive while the parent drains the stream.
- Inputs: current isolated Python runtime, freshly provenance-built private
  Darwin extension, `/usr/bin/log`, `/usr/bin/sandbox-exec`, three fixed
  transport fixtures and the fixed model-free network worker. No audio, model
  or checkpoint input.
- Model/runtime/checkpoint: no model or checkpoint. The native C source and
  build contract are unchanged from matrix v4 because the existing opaque
  identity matcher was sufficient; no new PID-returning native method was
  added.
- Evidence and metrics: 54 focused observer, supervision, source, build and
  live-matrix tests pass. Synthetic evidence rejects a mismatched owner and a
  transferable-authority claim. The live v5 matrix observed readiness before
  spawn, one deliberate owner-matched denial, zero other owned denials, broker
  replay rejection, normal zero exit, group emptiness and exact reap. Its
  path-free report retains no PID, PGID, destination or raw log message. The
  complete repository suite passes 2,819 tests with one platform skip and the
  existing third-party `resampy`/`pkg_resources` deprecation warning.
- Listening result: not applicable; no audio, MIDI or separation changed.
- Decision: retain the broker as the owner-bound kernel-network primitive.
  Keep the historical PID-based observer for the unchanged Kim v10/v11 path;
  do not imply that the real model now uses native ownership.
- Problems/risks: kernel log event PIDs exist transiently inside the bounded
  parser because they are the OS records being matched, but the owner's hidden
  PID is never exported and no event PID is retained. Unified logging remains
  denial-only evidence, not a packet monitor. `sandbox-exec` is deprecated,
  pathname TOCTOU remains, and the broker has not been attached to Kim Vocal 2.
- Next smallest step: build and exercise the post-inference executable-region
  inventory in an owner-bound, worker-ready form with a fixed model-free
  worker. Only after that should one combined fixed-worker bridge be considered.

### 2026-08-02 — native owner observes its process image without exporting PID

- Goal: replace the first raw-PID dependency in the future Kim native bridge
  with an observation performed by the exact native owner, while keeping the
  real model and every product route untouched.
- Change or experiment: added `observe_owned_process_image` to the
  nonconstructible Darwin owner. It polls `proc_pidpath` on the internally
  retained child, obtains the kernel CDHash with `csops`, and accepts only the
  prepared runtime-launcher transition, exact process-image path and exact
  lowercase 40-hex CDHash. It returns a path-free two-field result and never
  exports PID or PGID. Native canary matrix v4 uses a fixed blocking worker to
  reject a deliberately wrong path and wrong CDHash, prove both rejections
  preserve ownership, accept the real image and then group-kill and exact-reap
  the child.
- Inputs: current isolated Python runtime, its strictly validated signed
  process image, the freshly provenance-built private Darwin extension and a
  fixed stdlib-only blocking worker. No audio or model input.
- Model/runtime/checkpoint: no model or checkpoint. Native source SHA-256 is
  `95191625be35d2052cdefc7446cb1847ad42a22706851300ef7aadfea5a2433e`;
  build-contract SHA-256 is
  `e72175cbb64cf5419c797e00c7293349ff200c54d4b00b81ccc2074401c99727`.
- Evidence and metrics: 33 focused source/build/live-canary tests pass. Matrix
  v4 retains only path-free file identities and boolean qualification facts;
  the test rejects any serialized temporary, repository, extension, worker or
  expected process-image path. The complete repository suite passes 2,813
  tests with one platform skip and the existing third-party
  `resampy`/`pkg_resources` deprecation warning.
- Listening result: not applicable; no audio, MIDI or separation changed.
- Decision: retain this as the first owner-bound observer primitive. It is
  model-free infrastructure, not real-worker supervision or separation
  acceptance.
- Problems/risks: caller-prepared paths and static identities retain their
  stated TOCTOU limits. The current Kim v10/v11 subprocess route still uses its
  existing raw-PID observers and both native-supervision flags remain false.
  Kernel-network denial and post-inference executable-region observations do
  not yet have owner-bound adapters.
- Next smallest step: design and exercise a single-use owner-bound observation
  broker for the kernel-network denial stream with a fixed model-free worker,
  without exposing PID/PGID or invoking Kim.

### 2026-08-02 — native real-worker terminal projection fixed but not run

- Goal: define exactly what evidence the Kim worker must produce before it may
  inherit the model-free native descendant-supervision proof, without
  launching the model or weakening the current observers.
- Change or experiment: added a validation-only native terminal projection and
  self-hashed blocked bridge plan. The projection requires bound session,
  execution and worker-result hashes; exact owned start; normal zero exit;
  matched identity; leader-exit observation; complete group drain; exact reap;
  and ownership release. It rejects timeout TERM/KILL escalation, ownership
  loss, partial terminal state, raw PID/PGID retention and signal authority.
- Inputs: fixed in-memory mappings in unit tests only. No audio, checkpoint,
  model, sandbox worker or native process ran.
- Model/runtime/checkpoint: none.
- Evidence and metrics: focused supervision tests pass, including rejection of
  partial, lost, PID-bearing, subprocess-labelled, nonzero-exit, malformed-hash
  and extra-field projections. The surrounding boundary suite passed 66 tests;
  the complete repository suite passed 2,812 tests with one platform skip and
  the existing third-party `resampy`/`pkg_resources` deprecation warning.
- Listening result: not applicable; no audio or MIDI changed.
- Decision: retain this as a strict future bridge contract, not as evidence of
  real-worker native supervision. The current Kim v10/v11 route remains
  synchronous `Popen.communicate` evidence with both native supervision flags
  false.
- Problems/risks: process-image, network-denial and native-image-ready
  observers currently consume a raw child PID, while the native owner hides
  PID authority. Shape validation alone is not execution provenance.
- Next smallest step: introduce an owner-bound observation capability that can
  perform the required parent observations without exposing PID/PGID, then
  exercise that capability with a fixed model-free worker before Kim.

### 2026-08-02 — native descendant lifetime held through exact reap

- Goal: make the existing Darwin native owner safe for a future real worker
  whose descendant might survive its leader, without enabling any separator
  route or attaching an unfinished primitive to Kim Vocal 2.
- Change or experiment: native spawn now creates a private session. The owner
  uses `waitid(P_PID, ..., WNOWAIT)` to observe leader exit without reaping,
  then `proc_listpgrppids` to census the still-reserved process group. Exact
  `waitpid` is permitted only when the retained leader is the sole member.
  Ownership release therefore means both group emptiness and exact leader
  reap. Emergency cleanup uses the same bounded state machine.
- Inputs: a new fixed stdlib-only model-free canary. It hardens FDs 3/4/5,
  forks exactly one descendant, writes only bounded request/checkpoint hashes
  and PID/PGID self-report evidence to its existing result descriptor, then
  exits normally. No audio, checkpoint, model, network or product route ran.
- Model/runtime/checkpoint: current isolated Python runtime and freshly built
  private Darwin launcher only.
- Evidence and metrics: the live matrix v3 observed leader exit while the
  descendant kept `leader_reaped`, `group_empty` and `ownership_released`
  false. Whole-group `SIGKILL` was followed by a leader-only census, exact
  zero-status leader reap, `group_empty=true` and ownership release. The report
  retains no PID/PGID. The focused native boundary suite passed 94 tests,
  including one fresh live Darwin canary build/run. The complete suite passed
  2,803 tests with one platform skip and the existing third-party
  `resampy`/`pkg_resources` deprecation warning.
- Listening result: not applicable; no audio or MIDI changed.
- Decision: retain this as model-free native process-group state-machine
  evidence. Public and private real-model execution permissions are unchanged.
- Problems/risks: the Kim worker still uses synchronous `Popen.communicate`
  and has not been moved under this native owner. The canary covers one fixed
  descendant, not arbitrary hostile process trees. Pre-exec signal state,
  runtime/provider path-to-execution TOCTOU and complete native-library closure
  remain open.
- Next smallest step: started by the validation-only terminal projection above;
  the owner-bound observer transport remains to be implemented.

### 2026-08-02 — real Kim Vocal 2 worker supervision bound

- Goal: attach the already tested outer-descriptor, post-CPython signal-state
  and exact normal-exit contract to one real, authorised Kim Vocal 2 worker
  without enabling a separator product route.
- Change or experiment: the private launcher now observes its complete open-FD
  set before importing Sunofriend. The real worker reports a fixed selected
  signal mask/handler record after CPython startup. The parent validates both,
  waits synchronously for the exact child, and adds one path-free self-hashed
  supervision layer only after clean exit. This opt-in mode requires the
  existing import-closure, sandbox-network, signed process-image and
  post-inference native-image boundaries.
- Inputs: the unchanged authorised `Be Alone` 191-206 second PCM24 excerpt,
  exact Kim Vocal 2 source revision `41092c02...`, 456,483,463-byte BF16
  checkpoint and pinned config/licence companions.
- Model/runtime/checkpoint: GPU mode with checkpoint SHA-256
  `312c38e5...7fe5`; the exact 9,535-byte descriptor-executed worker hashes to
  `c95f0544...6e4b`.
- Evidence and metrics: the live private run passed as worker schema v10. The
  launcher had exactly FDs 0-2. The worker reported an empty main-thread mask,
  default `SIGHUP`/`SIGQUIT`/`SIGTERM` and `SIGCHLD`, plus CPython's expected
  `SIGINT`, `SIGPIPE` and `SIGXFSZ` dispositions. The parent observed normal
  exit 0 and exact-child reap through synchronous `Popen.communicate`. The
  120,078-byte owner-only report has evidence self-hash `7bd289b9...ca4e`, file
  SHA-256 `f0057201...43e`, and nested supervision hash `d4762583...e9d`. It
  retained 322 modules, 279 files, 18,097,696 import bytes, one deliberate
  denied network canary and zero other worker denials.
- Listening result: not repeated. The source, separator output and downstream
  MIDI path are unchanged.
- Decision: retain this as private real-worker execution evidence. Every
  source-graph, CLI, TUI, Simple, Studio, selection, publication and promotion
  permission remains false.
- Problems/risks: post-CPython state does not reconstruct the pre-exec signal
  instant. A synchronous subprocess wait is not native process-group or
  descendant supervision. Provider/runtime path-to-execution TOCTOU, complete
  native-library closure, dyld shared-cache constituents, transient loads and
  mapped-memory byte identity remain open.
- Next smallest step: design a native-owned real-worker process-group terminal
  boundary, while preserving the current no-route and fail-closed contracts.

### 2026-08-02 — deterministic transport worker supervision bound

- Goal: bind the clean outer-supervisor, post-CPython signal and exact normal
  termination observations to one exact execution of the existing
  deterministic transport worker before considering any real-model route.
- Change or experiment: the pinned stdlib-only fake worker now places its
  main-thread mask and selected handler dispositions inside its self-hashed
  Result V2. The native terminal receipt validates and binds that result to a
  normal zero exit with no signal termination and exact reap. The isolated
  one-shot helper observes only FDs 0–2 before importing Sunofriend or creating
  execution state, then emits one path-free self-hashed supervision report
  containing both that outer observation and the exact terminal receipt.
- Inputs: the code-owned two-frame PCM24 deterministic fixture and existing
  synthetic checkpoint lease. No source audio, optional checkpoint, model,
  inference or network resource was used.
- Model/runtime/checkpoint: the current isolated Python runtime and freshly
  built private Darwin launcher only. The fake worker source is pinned at
  SHA-256 `8efec22498bdabef33d951eafaba9cc80cc51a7e0f0adef52ab21e883c38b741`
  and 24,003 bytes.
- Evidence and metrics: the exact live Darwin execution passed. The outer
  helper observed FDs 0–2; the worker observed an empty main-thread mask,
  default `SIGHUP`/`SIGQUIT`/`SIGTERM` and `SIGCHLD`, and CPython's expected
  `SIGINT`, `SIGPIPE` and `SIGXFSZ` dispositions. The parent bound the worker
  result hash to normal zero exit, no signal termination and exact reap.
- Listening result: not applicable; no source audio or MIDI changed.
- Decision: the earlier canary facts are now bound to the deterministic
  transport worker only. Real-model, source-graph, CLI, TUI, Simple, Studio,
  selection, publication and promotion routes remain disabled.
- Problems/risks: this observes worker state after CPython startup and does not
  reconstruct the pre-exec signal instant. It is not Kim Vocal 2 or other
  real-separator evidence. Extension/runtime/worker pathname TOCTOU, dynamic
  native-library closure and the real-worker outer-supervision boundary remain
  open.
- Next smallest step: completed by the real Kim Vocal 2 worker-supervision
  increment above.

### 2026-08-02 — outer supervisor and post-CPython signal canary

- Goal: independently observe the clean outer canary boundary, the signal
  state that fixed child code actually enters after CPython startup, and exact
  normal termination without attaching unfinished supervision to a model.
- Change or experiment: upgraded the private Darwin descriptor canary to
  matrix v2. Before its own cleanup, the harness scans the complete current FD
  limit and requires exactly FDs 0–2 after its parent launch with
  `close_fds=True, pass_fds=()`. Every fixed child records its main-thread
  signal mask and selected handlers after CPython startup. The native owner
  separately checks normal zero-status exit, no signal termination, exact
  reap, stable cached wait and post-reap signal rejection. The final matrix no
  longer retains raw PID, PGID or wait status.
- Inputs: the existing model-free, stdlib-only native-spawn canary and all 16
  fixed exact/representative descriptor layouts. No audio, checkpoint, model
  or network resource was used.
- Model/runtime/checkpoint: current isolated Python runtime and freshly built
  private Darwin launcher only; no checkpoint or inference.
- Evidence and metrics: the live Darwin matrix passed every layout. Harness
  entry had only FDs 0–2. Every child reached user code with an empty mask,
  default `SIGHUP`/`SIGQUIT`/`SIGTERM` and `SIGCHLD`, plus expected CPython
  `SIGINT`, `SIGPIPE` and `SIGXFSZ` adjustments. Twelve focused source and live
  canary tests pass; the broader native boundary suite passes 65 tests. The
  complete repository suite passes 2,785 tests with one platform skip and the
  one existing third-party `resampy`/`pkg_resources` deprecation warning.
- Listening result: not applicable; no audio or MIDI changed.
- Decision: retain v2 as private model-free supervision evidence. Every
  separator, source-graph, Simple, Studio, product and publication route stays
  disabled.
- Problems/risks: a post-CPython observation cannot reconstruct the pre-exec
  signal instant. This canary itself remains model-free; the later increment
  above binds equivalent facts to the deterministic transport worker, not Kim
  Vocal 2. Extension/runtime/worker path TOCTOU and arbitrary source-FD
  coverage remain open.
- Next smallest step: completed by the deterministic transport-worker
  supervision increment above.

### 2026-08-02 — worker-ready native images bound to two authorised runs

- Goal: attach the parent-owned native executable-region inventory to the
  exact live Kim Vocal 2 worker after model inference, without sampling an
  early partial load set or enabling any separator route.
- Change or experiment: added two explicit non-inheritable pipe pairs whose
  child ends alone are passed through `sandbox-exec`. The worker emits one
  bounded, path-free readiness claim after inference and before PCM24
  quarantine, then blocks for the parent's exact release. The parent binds the
  existing signed process-image observation, takes two stable `libproc`
  executable-region snapshots, hashes and signature-checks every reported
  file, releases the worker, and rehashes the files after clean exit. Additive
  v8/v9 validators preserve historical worker evidence v1-v7 unchanged.
- Inputs: the unchanged authorised `Be Alone` 191-206 second PCM24 excerpt,
  exact Kim Vocal 2 source revision `41092c02...`, 456,483,463-byte BF16
  checkpoint and its pinned config/licence companions. The missing private
  cache was re-materialised outside the repository with owner-only permissions
  and every pinned hash was reverified before use.
- Model/runtime/checkpoint: both fresh observations used GPU mode and checkpoint
  SHA-256 `312c38e5...7fe5`. Readiness bound the candidate, checkpoint, authorised
  audio, 661,500 source frames and both in-memory float-output hashes before
  the parent allowed quarantine writing.
- Evidence and metrics: both runs observed exactly 33 file-backed executable
  regions across 33 files, no unpathed executable region and one exact main
  process image. Their path-free inventory payloads were identical, with
  canonical SHA-256 `26132d6c...75d`; every file was unchanged after its child
  exited. Thirty-two files passed strict static-code validation and one was
  retained explicitly as not strictly valid. The first 117,143-byte owner-only
  observation has evidence self-hash `6b468be1...9ba` and file SHA-256
  `8d19702a...3d6`; the 117,144-byte repeat has evidence self-hash
  `2a5d05b4...e35` and file SHA-256 `8312560d...b5a`. Forty-seven focused
  handshake, native-image,
  process-image, network-observer and worker-validator tests pass. The complete
  standard non-trusted-local suite passes 2,777 tests, with one platform skip,
  eight explicitly deselected trusted-local tests and the one pre-existing
  dependency deprecation warning.
- Listening result: not repeated. This increment changes provenance evidence,
  not candidate audio or MIDI evaluation.
- Decision: retain the post-inference/pre-quarantine handshake and repeatable
  file-backed inventory as private evidence. Product, publication, automatic
  selection, source-graph, Simple and Studio permissions remain false.
- Problems/risks: the two GPU runs produced different float-output hashes, so
  bitwise conversion repeatability is not claimed. The inventory does not
  enumerate individual dyld shared-cache constituents, exclude transient loads
  outside the snapshots, prove reopened file bytes equal mapped memory, prevent
  post-observation mutation, or close the wider supervisor/signal boundary.
  Dynamic native-library closure and independent conversion parity remain
  false.
- Next smallest step: completed by the later model-free outer-supervisor and
  post-CPython signal canary above. Binding those facts to the deterministic
  transport worker and real model remains separate; every separator route is
  disabled.

### 2026-08-02 — stable native executable-region inventory canary

- Goal: make the first parent-owned observation of native executable mappings
  outside Python's `sys.modules` without attaching an unfinished mechanism to
  another authorised model run.
- Change or experiment: added a private Darwin-only `libproc`
  `PROC_PIDREGIONPATHINFO` canary. One exact inert child imports seven fixed
  standard-library native modules, emits only a readiness record, then sleeps
  while the parent takes two bounded executable-region snapshots. The parent
  requires byte-identical snapshot geometry, hashes every reported mapped file,
  records strict code-signature status where available, waits for clean child
  exit and rehashes every file. Paths and the child PID are not retained.
- Inputs: the installed `.venv-ai` Python runtime only. No audio, model,
  checkpoint, provider result, MIDI, review or product state was read.
- Model/runtime/checkpoint: no model or checkpoint. The nested process-image
  binding is unchanged at `1d13892e…c798` and still verifies the exact
  `Python.app` main image before the mapping inventory.
- Evidence and metrics: each of two fresh owner-only runs produced the same
  9,411-byte JSON and the same self-hash `be0a3601…714a`; the on-disk file hash
  is `c954dfbe…2b53`. Both snapshots contained 13 executable file-backed
  regions across 13 files and no unpathed executable region. The files totalled
  30,677,328 bytes, all were unchanged after child exit, 12 passed strict
  static-code validation and one was explicitly recorded as not strictly
  valid. Twenty-eight focused inventory/process-image tests pass. The complete
  standard non-trusted-local suite passes 2,762 tests, with one platform skip,
  eight explicitly deselected trusted-local tests and the one pre-existing
  dependency deprecation warning.
- Listening result: not applicable. This canary intentionally performs no
  music processing.
- Decision: retain the deterministic path-free inventory as private design
  evidence. It proves that the parent can observe and remeasure stable
  file-backed executable mappings for an exact inert child. It grants no
  separator, model, checkpoint, source-graph, Simple, Studio, product or
  publication permission.
- Problems/risks: `libproc` does not enumerate individual dyld shared-cache
  constituents here; two snapshots cannot exclude a transient load between
  them; reopened file hashes do not prove that mapped memory has those bytes;
  and this canary is not bound to the model worker. Complete dynamic native
  closure therefore remains false.
- Next smallest step: design an explicit, bounded worker-ready observation
  point so this parent-owned snapshot can be attached to a future authorised
  model run without mistaking an early partial inventory for the final native
  load set. Keep every separator route disabled.

### 2026-08-02 — runtime process image bound to the authorised worker

- Goal: attach the model-free parent-PID process-image primitive to the exact
  Kim Vocal 2 process that reads the authorised excerpt and checkpoint.
- Change or experiment: factored a reusable prepared process-image binding,
  combined it with the existing ready-before-child macOS Sandbox denial
  observer, and introduced additive worker evidence schemas v6/v7. Historical
  v1–v5 validation remains unchanged. The parent observes the final image
  before waiting for the child, then remeasures provider, launcher and final
  image after completion.
- Inputs: the unchanged authorised `Be Alone` 191–206 second PCM24 excerpt,
  current 6,790-byte descriptor-executed worker, pinned Kim Vocal 2 BF16
  checkpoint and already installed MLX runtime. No MIDI, listening result,
  source-graph or product state changed.
- Model/runtime/checkpoint: the worker used GPU mode and the existing exact
  456,483,463-byte checkpoint. The signed launcher CDHash was
  `60332d8d…8f3`; the final `Python.app` static and kernel CDHashes were both
  `b9f4c42c…aae`. The exact `sandbox-exec` provider was strictly signed and
  remained on a read-only filesystem.
- Evidence and metrics: the v6 path-free worker evidence self-hashes to
  `fd9ee6dd…4249`; its nested runtime binding hashes to `1d13892e…c798`.
  The 97,617-byte owner-only observation file hashes to `4de79291…7cb`.
  The run retained 320 Python modules across 277 independently reopened files
  totalling 18,075,137 bytes with zero unclassified modules. It observed the
  single deliberate denied outbound canary and zero other worker denials.
  Inference covered 661,500 frames in three chunks, took 3.349 seconds and
  recorded 2,419,165,306 peak MLX bytes. Both 3,969,044-byte PCM24 outputs
  passed parent re-read and source reconstruction within one integer LSB.
  Thirty-two focused tests pass. The complete standard non-trusted-local suite
  passes 2,748 tests, with one platform skip, eight explicitly deselected
  trusted-local tests and one pre-existing dependency deprecation warning.
- Listening result: not repeated. This increment deliberately preserves all
  earlier MIDI and human listening evidence rather than manufacturing a new
  musical comparison from a runtime-safety check.
- Decision: retain the v6/v7 binding as private development evidence. It
  closes the earlier “not attached to the model worker” gap for one exact
  authorised run and grants no separator, activation, selection, Simple,
  Studio, product or publication permission.
- Problems/risks: a kernel/static CDHash match is code-signature identity, not
  proof that the full measured file bytes or every dynamically loaded native
  library were the bytes executed. Post-observation image mutability and the
  wider outer-supervisor/signal-state boundary also remain open.
- Next smallest step: completed by the later stable native executable-region
  inventory canary above. It remains model-free and does not close complete
  dynamic native closure.

### 2026-08-02 — actual macOS runtime process-image observation

- Goal: stop treating the measured Python launcher as if it were necessarily
  the native image that executes the private separator worker.
- Change or experiment: added a model-free Darwin canary that launches one
  inert child through the exact `sandbox-exec` provider, observes the exact
  child PID from the parent with `proc_pidpath`, reads its kernel CDHash with
  `csops`, and compares that identity with a strictly validated static code
  signature. Provider, launcher and final-image full-file hashes are rechecked
  after the child exits; the provider must reside on a read-only filesystem.
- Inputs: the installed `.venv-ai` Python runtime only. No audio, model,
  checkpoint, provider stem or existing private review was read.
- Model/runtime/checkpoint: no model or checkpoint. The observed python.org
  runtime uses a two-stage transition: its signed framework launcher CDHash is
  `60332d8d…8f3`, while the actual `Python.app` process image and kernel CDHash
  are both `b9f4c42c…aae`.
- Evidence and metrics: the owner-only path-free observation is 2,837 bytes,
  mode `0600`, and self-hashes to `4d5ed400…5d4`. Thirteen focused validation,
  tamper, wrong-path, wrong-CDHash, transition, private-write and no-public-
  route tests pass. The complete repository suite passes 2,754 tests with one
  platform skip and the existing third-party `resampy`/`pkg_resources`
  deprecation warning.
- Listening result: not applicable. The child performs only a fixed arithmetic
  probe and sleeps briefly for parent observation.
- Decision: retain the process-image observer as a private development
  primitive. It neither enables a separator nor grants model, checkpoint,
  audio, source-graph, product or publication permission.
- Problems/risks: at this canary-only stage the observation was not attached
  to the authorised Kim Vocal 2 worker. A kernel/static CDHash match binds
  executed code-signature identity, not the full file SHA-256 or every
  dynamically loaded native library. Post-observation image mutability also
  remains outside this narrow result.
- Next smallest step: completed by the later entry above, which attaches the
  same parent-PID observation to one existing sealed authorised excerpt without
  changing its MIDI, listening or product status.

### 2026-08-02 — private vocal candidate loopback audition

- Goal: make every preserved vocal hypothesis understandable and explicitly
  reviewable without copying private audio or allowing playback behaviour to
  become a hidden preference.
- Change or experiment: added a private-only loopback server, browser review
  and separate exact verifier. The server revalidates the complete inventory,
  MelRoFormer, vocal-leaf, phrase-completeness and authorised-excerpt chain;
  opens source/reference WAVs with a descriptor-relative no-follow walk;
  verifies their complete hashes before serving byte ranges; and exposes only
  opaque token-protected media routes on `127.0.0.1`.
- Inputs: both existing 17-candidate inventories and their already sealed
  reports. No separation, transcription or rendering was rerun and no media
  was copied.
- Model/runtime/checkpoint: no model or checkpoint was loaded. The page serves
  only existing original/leaf references and neutral MIDI-render WAVs.
- Evidence and metrics: `I am a Alien mashup` revalidated with 16 playable and
  one zero-note candidate; `Be Alone` revalidated with 13 playable and four
  zero-note candidates. The page records one exact written focus, requires
  explicit heard-reference/heard-candidate marks and accepts useful, not
  useful or cannot-tell for every playable candidate. Multiple useful outcomes
  are valid.
- Listening result: none requested. The tool is ready, but no new focus was
  opened as an acceptance gate.
- Decision: keep the tool private and outside CLI/TUI/Simple/Studio/Workbench
  and the source graph. Playback, seeking, looping and dwell time remain
  zero-write browser state. Only the browser export plus exact verifier can
  create review evidence, and that evidence cannot select, merge, repair,
  promote or identify a singer.
- Problems/risks: the neutral MIDI sound is not final instrumentation, provider
  leaf labels remain observations and a `useful` result applies only to the
  written focus. Reviewing 13–16 candidates is deliberately thorough and may
  be tiring; later bounded grouping must not become hidden ranking.
- Verification: both real private inventories passed exact load/revalidation;
  24 focused review, tamper, range-serving, changed-media, no-write, symlink
  and no-public-route tests passed. The complete repository suite passed 2,741
  tests with one skipped test and the existing third-party
  `resampy`/`pkg_resources` deprecation warning.
- Next smallest step: use this interface only when an exact lead/backing or
  phrase question justifies the listening effort; separately continue the S3
  execution-path and independent-backend gates before any S4 Studio route.

### 2026-08-02 — private vocal candidate-set preservation

- Goal: preserve complementary primary, register and provider-leaf vocal MIDI
  evidence without hiding alternatives behind a new automatic choice.
- Change or experiment: added a private-only, path-free candidate-set builder
  and runner. It validates exact self-hashed MelRoFormer, vocal-leaf and phrase-
  completeness reports; reopens every referenced artifact; preserves zero-note
  observations; and publishes only one owner-readable JSON manifest into a
  fresh owner-only directory.
- Inputs: the sealed `I am a Alien mashup` 219–234 second and `Be Alone`
  191–206 second evidence chains. Separation and model inference were not
  rerun.
- Model/runtime/checkpoint: no model was loaded. The candidate identities bind
  the already approved, inactive Kim Vocal 2 and unchanged deterministic vocal
  adapters.
- Evidence and metrics: both inventories contain 17 candidates: one Kim
  primary, four Kim register hypotheses and twelve provider-leaf adapter
  primaries. `I am a Alien mashup` has 16 auditionable plus one zero-note
  candidate; `Be Alone` has 13 plus four. Canonical document hashes are
  `01779801…d2e4` and `0b8b0266…174f4`; report hashes are
  `947559a9…dea1` and `89a25dea…e0b` respectively.
- Listening result: none requested. Phrase activity alone did not warrant a
  new review.
- Decision: retain every candidate and its path-free artifact identities, with
  no ranking, selection, default, merge, repair or singer assignment. Keep the
  builder out of the public CLI, TUI, Simple, Studio and source graph.
- Problems/risks: the manifest itself is not an audition UI and provider groups
  are estimated evidence rather than score truth. Zero-note results may be
  useful diagnostics but are not playable.
- Next smallest step: completed by the separate bounded private loopback
  audition and explicit review verifier described above.

### 2026-08-01 — final MIDI review and exact worker-script descriptor

- Goal: close the last Kim Vocal 2 listening gate and remove the worker-script
  pathname race without weakening the existing macOS Sandbox boundary.
- Change or experiment: resolved only the user's complete `I am a Alien
  mashup` export, then changed the authorised parent to hash and execute one
  already-open worker descriptor through Python standard input. The child
  binds `__main__` back to the same repository identity for the independently
  verified import closure.
- Inputs: the unchanged 0–15 second blind MIDI package and the already
  authorised `Be Alone` 191–206 second worker case.
- Model/runtime/checkpoint: exact published BF16 Kim Vocal 2 MLX checkpoint on
  GPU; unchanged audited source, offline profile and write confinement.
- Evidence and metrics: the reviewed export is `b289ec5d…2b167` and resolver
  result is `62320a75…e83e`. The 6,730-byte worker
  (`372ef11b…286a35`) was executed from its verified descriptor. The final
  record is `e074e3da…a34ca`; 320 modules, 277 files and 18,067,782 bytes were
  rebound. Inference took 2.93 seconds with 2,419,165,306 peak bytes. The
  kernel observer again saw one deliberate denied canary and no other worker
  denial.
- Listening result: `neither`. Both candidate MIDIs mainly followed the female
  backing vocal instead of the male lead heard in the mixed source.
- Decision: close the worker-script TOCTOU and human-review checklist items,
  but add an explicit lead-versus-backing quality blocker. Keep the candidate
  inactive, private and unavailable to every CLI, TUI, Simple, Studio,
  Workbench and source-graph route.
- Problems/risks: `sandbox-exec` and the Python virtual-environment runtime
  still launch by pathname. Native non-module loads and post-observation
  ordinary-file mutability remain open. The review also shows that a single
  vocal output is not sufficient when lead and backing singers overlap.
- Next smallest step: investigate a non-bypassable provider/runtime launch or
  an in-process sandbox transition, while designing lead/backing vocal
  assignment as a separate quality experiment rather than promoting this
  checkpoint.

### 2026-08-01 — Kim Vocal 2 FP32/BF16 listening gate resolved

- Goal: make the measured FP32-to-BF16 output delta reviewable by ear before
  deciding whether a second, roughly doubled-size FP32 MLX artifact is useful.
- Change or experiment: factored the exact three-output inference into a
  reusable private gate, added a sealed single-unit audio review and resolver,
  and reran original-FP32 PyTorch plus published-BF16 MLX on the same authorised
  eight-second source window.
- Inputs: `Be Alone`, original seconds 191–199, exact sealed PCM24 source.
- Model/runtime/checkpoint: exact author-hosted FP32 PyTorch checkpoint and
  published BF16 MLX checkpoint, both on CPU; the existing BF16-roundtrip to
  MLX parity gate had to remain above 40 dB before review publication.
- Evidence and metrics: both anonymous final PCM24 candidates measure
  `-21.093168` dBFS fixed-window sample RMS with zero reported mismatch. The
  audio-manifest SHA-256 is `202b5e6d…c97d9`; all package files are owner-only.
  The complete repository suite passes with 2,679 tests, one platform skip and
  the existing third-party `resampy` deprecation warning.
- Listening result: the user's complete blind export resolved to
  `equivalent`. Candidate A was original FP32 PyTorch and candidate B was
  published BF16 MLX. The reviewed export SHA-256 is
  `aa95d0dc6df8a698864aae34c1c345bddf299b56d82117da0612bb8924693d3c`.
- Decision: do not create a roughly doubled FP32 MLX artifact on this evidence.
  Continue evaluating the exact published BF16 candidate privately, while
  keeping separator enablement, selection, promotion, defaults and every
  product route false.
- Problems/risks: sample RMS is not perceived loudness; one eight-second song
  excerpt cannot establish universal precision equivalence.
- Next smallest step: complete the two prepared cross-song Kim-Vocal-2-versus-
  Moises MIDI reviews and close the worker path-to-execution race before any
  promotion decision.

### 2026-08-01 — Kim Vocal 2 BF16 runtime output parity

- Goal: distinguish MLX implementation error from the effect of publishing the
  converted checkpoint at BF16 precision.
- Change or experiment: installed the exact MIT `BS-RoFormer==0.3.10` reference
  and its pinned pure-Python dependencies in the private AI environment, then
  ran original-FP32 PyTorch, BF16-roundtrip PyTorch and published-BF16 MLX on
  the same authorised eight-second music window with no overlap.
- Inputs: `Be Alone`, original seconds 191–199, exact sealed PCM24 source.
- Model/runtime/checkpoint: PyTorch 2.13.0 CPU and MLX 0.31.2 CPU. The three new
  wheel identities are retained; checkpoint loading remained restricted and
  hash-bound.
- Evidence and metrics: BF16-roundtrip PyTorch versus BF16 MLX reached 117.70
  dB SDR, 1.15e-7 RMS difference and 1.67e-6 maximum difference. Original FP32
  versus BF16 MLX reached 29.14 dB; original FP32 versus BF16-roundtrip PyTorch
  also reached 29.14 dB. The tracked report SHA-256 is `a85939af…b389`.
- Listening result: not performed; no output audio was retained.
- Decision: verify the converted BF16 runtime implementation, while explicitly
  retaining the source-precision fidelity concern. Do not claim independent
  reproduction of the upstream 66.08 dB result or separator quality.
- Problems/risks: the upstream parity clip is unavailable and the 29.14 dB
  precision delta may or may not be musically important. Product permissions
  remain false.
- Next smallest step: equal-level blind comparison of original-FP32 and
  published-BF16 vocal output before considering a larger FP32 MLX artifact.

### 2026-08-01 — exact Kim Vocal 2 weight-conversion parity

- Goal: independently verify that the pinned MLX checkpoint contains the same
  weights as the exact author-hosted PyTorch checkpoint after the published
  BF16 conversion, without treating a model-card parity number as evidence.
- Change or experiment: privately downloaded the exact 913,106,900-byte source
  checkpoint, verified its published SHA-256, loaded it with PyTorch
  `weights_only=True`, reproduced converter revision `8380ab8` and compared
  every Safetensors payload through a descriptor-pinned reader.
- Inputs: no audio. The exact source checkpoint at SHA-256 `87201f4d…559e` and
  exact MLX Safetensors checkpoint at SHA-256 `312c38e5…7fe5`.
- Model/runtime/checkpoint: PyTorch performed restricted checkpoint loading;
  no model class was imported and no inference ran.
- Evidence and metrics: 684 retained source tensors became 708 BF16 tensors,
  including 12 packed Q/K/V splits. Names, shapes and every BF16 payload were
  bit-exact. The tracked report SHA-256 is `7386eaa1…a4c` and its tensor
  manifest SHA-256 is `ce0c29ff…e8ba`.
- Listening result: not applicable; no audio was read or produced.
- Decision: close only the weight-conversion blocker. Keep all model selection,
  product, publication, Simple, Studio and source-graph permissions false.
- Problems/risks: equivalent weights do not prove equivalent preprocessing,
  numerical operations, overlap handling or inference output.
- Next smallest step: completed by the BF16 runtime output observation above.

### 2026-08-01 — complete Python import-closure binding

- Goal: replace the authorised worker's unbounded Python import assumption
  with exact, independently verified evidence without expanding any product
  permission.
- Change or experiment: the child captured every post-inference `sys.modules`
  entry, opened file-backed modules without following symlinks, sealed hashes
  and per-root manifests, then proved that the module-name set stayed stable.
  The parent independently reopened and rehashed every claimed file and
  emitted only path-free evidence. Shared checkpoint inspection was moved to a
  small artifact module so the plan no longer hashes itself recursively.
- Inputs: the unchanged authorised `Be Alone` 191–206 second excerpt, pinned
  MLX overlay/runtime, repository Python sources and exact Kim Vocal 2
  checkpoint. No network or additional audio was used.
- Evidence and metrics: 320 Python modules, 277 file-backed modules,
  18,067,576 aggregate file bytes and zero unclassified modules. Closure
  evidence SHA-256 is `ce187b7b…c74f`; complete worker evidence is
  `3de1b71e…0a8f`; the owner-only 92,670-byte observation file hashes to
  `230aa5b8…8e6`.
- Listening result: not applicable; this run verifies execution provenance,
  not musical preference.
- Decision: close only `complete_worker_import_closure_not_bound`. Keep every
  product, publication, Simple, Studio and source-graph permission false.
- Problems/risks: `sys.modules` does not enumerate native libraries loaded
  outside Python's module registry. Path-to-execution TOCTOU, arbitrary
  outbound-attempt observation, mutable post-observation files and human
  listening remain open.
- Next smallest step: close path-to-execution TOCTOU and add bounded
  outbound-attempt observation before resolving the prepared listening
  reviews.

### 2026-08-01 — second-song MelRoFormer vocal-MIDI evidence

- Goal: close the cross-song downstream-MIDI blocker without changing the
  separator, transcription settings or inactive/private product boundary.
- Change or experiment: repeated the exact offline/write-confined Kim Vocal 2
  worker on a second sealed authorised excerpt, generalised the downstream
  evaluator to consume validated per-song BPM/tuning policy, ran the unchanged
  production pYIN dominant-contour path and prepared a second equal-level blind
  Kim-versus-Moises review.
- Inputs: Ezzye `I am a Alien mashup`, original seconds 219–234, 114 BPM,
  A=440 Hz, plus the existing local HTDemucs, Moises and two Suno vocal
  controls.
- Model/runtime/checkpoint: the exact approved Kim Vocal 2 MLX checkpoint on
  GPU; three 50%-overlapped chunks, offline and confined to a fresh owner-only
  staging tree.
- Evidence and metrics: the worker evidence is `53b6fd72…00e1`; its persisted
  observation file is `bf331358…38f0`. PCM24 reconstruction stayed within one
  least-significant bit. The downstream report is `36599d2b…9f18`; its
  23-note MIDI is `776a07c4…47e5`. Exact-pitch/onset F1 at 40 ms was 0.913
  versus Moises, 0.889 versus HTDemucs, 0.844 versus Suno A and 0.773 versus
  Suno B.
- Listening result: pending at this increment. The later entry above records
  the complete `neither` result; neither answer key was opened manually.
- Decision: close only the cross-song downstream-MIDI blocker. Keep selection,
  activation, publication and every product permission false because the
  controls are estimated, not score truth.
- Problems/risks: both observations are short and monophonic. Exact BF16
  runtime parity now passes. The complete post-inference Python `sys.modules`
  closure is bound for one exact authorised worker run, but native non-module
  loads, the original-FP32-to-published-BF16 precision effect,
  hash-before-exec TOCTOU and human listening remain open.
- Next smallest step: close the path-to-execution TOCTOU window and add bounded
  outbound-attempt observation, then have the user complete and export the
  sealed blind reviews. Resolve them only after completion before
  reconsidering any default.

### 2026-08-01 — authorised vocal worker to downstream MIDI

- Goal: determine whether the isolated Kim Vocal 2 output survives the exact
  production vocal-to-MIDI path before considering any product integration.
- Change or experiment: retained the complete owner-only worker observation,
  revalidated its vocal PCM24 hash, ran the unchanged pYIN dominant-contour
  lead-vocal process, and prepared a blind equal-level MIDI listening review.
- Inputs: the sealed authorised `Be Alone` 191–206 second mixed excerpt and
  the existing local HTDemucs, Moises and two Suno vocal control MIDIs.
- Model/runtime/checkpoint: exact approved Kim Vocal 2 MLX checkpoint on GPU;
  the model worker remained offline and write-confined.
- Evidence and metrics: the retained worker observation is
  `ff086359…7b0`; the downstream report is `e2ae906d…3a0c`. The candidate has
  14 notes. Exact-pitch/onset F1 at 40 ms was 0.600 versus Moises, 0.560 versus
  Suno A, 0.519 versus HTDemucs and 0.462 versus Suno B.
- Listening result: the complete blind Kim-versus-Moises export resolved to
  `equivalent`. Its reviewed-export SHA-256 is `8146d04d…d96c`; no MIDI,
  selection or default changed.
- Decision: keep all product, selection and publication permissions false.
  Agreement with estimated controls is not ground truth and selects no winner.
- Problems/risks: one short excerpt cannot establish recognition, cross-song
  reliability or the musical impact of the later-observed FP32-to-BF16
  precision delta. The dominant contour remains monophonic.
- Next smallest step: the exact contract has now repeated on a second
  authorised song. The later entry above completes its blind review and keeps
  the gate blocked on quality.

### 2026-08-01 — exact-worker macOS Sandbox network-denial observation

- Goal: replace reliance on one self-reported connection canary with a bounded
  parent observation of kernel Sandbox `network-*` denials for the exact real
  model-worker PID.
- Change or experiment: added a private macOS unified-log observer that hashes
  `/usr/bin/log`, becomes ready before the worker starts, consumes NDJSON under
  a fixed kernel-Sandbox predicate, verifies the stream's final count and
  rejects malformed, excessive or unexpected records. Raw events are bounded
  in memory and discarded; the durable evidence contains counts only, without
  PID, destination or message text.
- Inputs: the already authorised `Be Alone` 191–206 second PCM24 excerpt, exact
  Kim Vocal 2 Safetensors checkpoint, audited MLX source and the existing
  import-closure-bound worker. No new model or network access.
- Evidence and metrics: the observer was ready before the model process and
  bound one `network-outbound` denial to its exact PID. That event was the
  deliberate port-9 canary; there were zero other worker denials and zero
  unrelated denials. The final stream summary matched one parsed event, with no
  malformed record or byte/event overflow. Network evidence is sealed as
  `393bc04ec7247c415dd83d1732cbd84f47f5b5cb99b98c35206a2b6bc891ce5c`;
  the complete worker record is
  `11e10ca1dbb372e63f785c4a935a554d1c036232b539cf66552e6e4c53f6c534`.
- Listening result: not applicable; the musical outputs and review identities
  are unchanged, and no blind answer key was opened.
- Decision: close the plan blocker for bounded observation of sandbox-denied
  model-process network acquisitions. Keep all product routes false.
- Problems/risks: unified logging is not a packet monitor and this evidence
  records denied Sandbox acquisitions, not successful network traffic. The
  runtime and worker are still executed by pathname; native non-module load
  closure and path-to-execution TOCTOU remain open.
- Next smallest step: the later entry above closes the worker-script portion
  of the race and completes the MIDI review. Provider/runtime path execution
  and lead/backing assignment remain blocked.

### 2026-08-01 — isolated synthetic two-role worker

- Goal: bind the denial and PCM24 boundaries to one child process before
  loading the real checkpoint.
- Change or experiment: added a fixed private synthetic worker launched by the
  parent through `sandbox-exec`. The profile denies all network operations,
  process forks and writes outside one fresh owner-only staging tree. The child
  deliberately attempts one operation in each denied class, writes the two
  deterministic PCM24 outputs, and returns path-free evidence; the parent
  independently reopens and verifies the output tree.
- Inputs: the exact `.venv-ai` launcher and code-owned 4,096-frame synthetic
  arrays. No authorised audio, model or checkpoint.
- Evidence and metrics: network connect, `fork()` and outside-tree create each
  returned `EPERM`. Child and parent PCM24 evidence matched at SHA-256
  `6e7b30431e9b01e8e3802876508d3e07d7fbe94150cbe5284c924de81355d784`;
  the complete run is sealed as
  `8b1a91a95609d09175be6240af2a9d44f5bd8161249ebab01b9878e7cb406cb4`.
- Listening result: not applicable; the files contain a mathematical canary.
- Decision: the isolation and persistence rules can coexist in one synthetic
  worker. Do not transfer that result to the model worker yet.
- Problems/risks: at this synthetic stage the profile provider was deprecated;
  arbitrary-attempt observation, hash-before-exec path TOCTOU and complete
  Python import closure were still open. The later authorised closure run above
  closes only the Python-import item. Ordinary output bytes can change after
  the parent observation.
- Next smallest step: add the real authorised-excerpt action to this exact
  worker, bind all model/source/checkpoint evidence, then run it once under the
  same profile and reverify its PCM24 outputs.

### 2026-08-01 — deterministic PCM24 quarantine boundary

- Goal: prove the exact two-file persistence and parent-verification logic
  independently of the model process.
- Change or experiment: added a standard-library deterministic PCM24 encoder
  and fresh owner-only quarantine for fixed `vocals.wav` and
  `instrumental.wav` outputs. The parent reopens both files read-only, verifies
  the exact entry allowlist, permissions, hashes, canonical 44.1 kHz stereo
  geometry and integer-domain source reconstruction.
- Inputs: precomputed synthetic arrays only, including the maximum 661,500
  frame, 15-second geometry. No model, checkpoint or authorised song audio.
- Evidence and metrics: two identical materializations produced identical
  hashes and self-hashed path-free evidence. The full-length files were
  3,969,044 bytes each. Reconstruction passed the fixed maximum two-LSB policy;
  the silent full-length canary was exact at zero LSB.
- Listening result: not applicable; this tests encoding and evidence, not
  separation quality.
- Decision: replace “PCM24 persistence not implemented” with the narrower
  blocker “PCM24 quarantine not bound to worker.” Keep product and publication
  permissions false.
- Problems/risks: the writer currently receives precomputed arrays in-process;
  outside-write denial, worker provenance, descendant denial and immutability
  after the parent observation remain unproven.
- Next smallest step: bind this exact boundary and the proven network-denial
  profile to one fixed private worker, then verify the real authorised excerpt
  before downstream MIDI evaluation.

### 2026-08-01 — macOS network-denial canary

- Goal: replace the MelRoFormer plan's executable-presence assumption with an
  observed OS-level network-denial fact before any private worker writes audio.
- Change or experiment: added a bounded model-free canary that hashes the exact
  `sandbox-exec` provider and Python runtime, runs identical isolated-mode
  standard-library loopback probes with and without `(deny network*)`, and
  returns self-hashed path-free evidence.
- Inputs: no audio, checkpoint, model or external network destination. The
  deliberate target is local IPv4 loopback port 9.
- Evidence and metrics: the unsandboxed control returned `ECONNREFUSED`; the
  sandboxed child returned `EPERM`; both completed the same arithmetic probe.
  The exact `.venv-ai` observation is sealed as SHA-256
  `ff64dca9e59a8862b68202842ed1ede67e39bbcfb824bb97427620c23c658b86`.
  Tests also reject a modified conclusion whose self-hash was not recomputed.
- Listening result: not applicable; no audio was read or written.
- Decision: record OS network denial as verified for this exact canary only.
  Keep worker start, checkpoint access, model import, output persistence and
  every product route false.
- Problems/risks: `sandbox-exec` is deprecated; the canary does not provide a
  complete stream of arbitrary model connection attempts, test IPv6/DNS,
  confine writes or deny descendants, and it is not yet bound to the model
  worker. Hash-before-exec does not yet close provider/runtime path TOCTOU.
- Next smallest step: launch the fixed two-role worker under the proven profile
  while separately confining PCM24 outputs to a fresh private quarantine and
  parent-verifying their hashes, geometry and additive reconstruction.

### 2026-07-31 — Cross-song narrow `other` evidence

- Goal: determine whether provider leaves inside composite `other` are stable
  enough to define instrument-specific audio or MIDI targets.
- Change or experiment: added a private-only, fresh-output analyzer that
  revalidates every upstream report and artifact, stages each `other` leaf at
  44.1 kHz stereo, calculates full pairwise spectral/envelope/waveform
  rankings in both directions, and records exact/semantic label observations
  without using names in the score.
- Inputs: the existing `Be Alone` 191–206 and `I am a Alien mashup` 219–234
  authorised reports; seven Moises leaves per song and three/four leaves in
  each Suno pack.
- Model/runtime/checkpoint: no new model. The analyzer is deterministic NumPy,
  SciPy resampling and SoundFile evidence over already-staged excerpts.
- Evidence and metrics: on `Be Alone`, all three Suno same-label pairs ranked
  first both ways, but only `Synth` had strong combined similarity (0.936);
  `Keyboard` was 0.461 and Moises `keys` ranked Suno `Keyboard` third. On `I
  am a Alien mashup`, only `Keyboard` ranked first both ways (0.937). Guitar,
  synth and residual `Other` failed the bidirectional check, and Moises/Suno
  semantic keys/other matches failed on both songs.
- Listening result: pending; common-rate private leaf WAVs are retained, but
  no additional human burden is required before the existing four blind MIDI
  choices are returned.
- Decision: reject automatic filename- or provider-label-based narrow source
  activation. Keep broad parents and all leaf evidence immutable and inactive.
- Problems/risks: provider outputs are estimates rather than multitrack ground
  truth; nearest-neighbour audio similarity cannot prove instrument identity;
  silence and leakage can make a relative rank look cleaner than it sounds.
- Next smallest step: completed below. The installed and statically inspected
  official experimental six-source Demucs challenger ran only on these two
  fixed windows; every guitar/piano/other estimate plus residual was compared
  with every provider leaf and downstream neutral MIDI without trusting
  labels.

The preparation and two private runs are complete:
the private registry pins official signature `5c90dfd2`, byte count
54,996,327 and full SHA-256
`34c22ccb381c6f9fdbf324f04e1e2fe21aaaf293f5ded163a162697ff9a02ddd`.
The separate installer required explicit private-evaluation acceptance, and
the offline resolver is excluded from ordinary AI readiness. On 31 July 2026
the accepted install passed its exact size/full-hash checks, and bounded static
inspection registered the exact 527-member ZIP and 17,488-opcode profile
without deserialisation. The accepted private runner then produced all six
estimates on both fixed 15-second windows. Exact re-read PCM24
sum-plus-residual accounting passed on both runs; no product surface is
enabled.

The exact private six-source request/worker/result path is implemented and
tested with both a deterministic fake worker and the real pinned checkpoint.
It preserves the four-source schemas, requires one model application and
exactly six role arrays, revalidates source/checkpoint/worker/runtime, seals
reconstruction and resource evidence, and keeps acceptance, source-graph,
Simple, Studio and publication permissions false.

The same neutral transcription and rendering path then compared guitar,
piano, broad `other` and the accounting residual with every supplied provider
leaf. `Be Alone` produced guitar/piano RMS 0.01595/0.000364; broad `other`, not
the new piano lane, was the strong Suno `Synth` audio match at 0.933. `I am a
Alien mashup` produced guitar/piano RMS 0.000563/0.000494; broad `other` was
closest to Moises `keys` at 0.857. Audio-nearest and MIDI-nearest leaves also
did not consistently agree. This is not ground truth, but it fails the current
usable-quality case for activating six-source guitar/piano. The challenger
remains review-required and inactive.

The quality escalation after that experiment is now explicit. First measure
same-checkpoint Demucs-MLX parity so runtime speed is not confused with model
quality. If the local quality gap remains, register one fixed, licence-audited
RoFormer candidate and only then test a deterministic role-specific ensemble.
Fine-tuning is reserved for a repeated named failure and requires owned or
licensed finished-mixture plus actual clean-target pairs, a frozen baseline
and a song-disjoint held-out set; provider estimates are comparison evidence,
not supervised ground truth. A provider API belongs to S7 and must be an
explicitly consented, costed upload with retention/deletion and provenance,
never a hidden local fallback. All routes must improve downstream MIDI and the
interpretation WAV under the same listening gate, not separation metrics
alone.

The Demucs-MLX step passed its explicit installation gate after user approval.
The five exact MIT packages were installed only in `.venv-ai`; no model or
system package changed. The runner converted the verified local checkpoint in
memory and compared all six raw float32 estimates on the two sealed 15-second
references without named-model resolution, model-cache use, automatic download
or a product route. MLX observed a 1.94x first-case and 16.72x process-local
second-case speed factor with about 604 MB reported peak resident memory, but
full split-pipeline numerical parity failed. Bass/drums correlation remained
0.99994–0.99999, while one low-energy guitar case fell to 0.743 and piano was
0.363–0.376. No role met the borrowed direct-model `1e-4` relative-maximum
reference. MLX therefore remains a private inactive runtime challenger, not an
accepted accelerator or separator-quality improvement.

The next architecture is now exact but deliberately unavailable. ZFTurbo's
four-stem BS-RoFormer [`v1.0.12` release](https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/tag/v1.0.12) is registered at source revision
`aef04b2e52fb3beaf25e333199f5a7236e628e7b` with its release asset IDs and
sizes, exact configuration SHA-256 and fixed roles. A read-only command records
the planned comparison against the sealed Demucs excerpts and makes no network,
installation, import, deserialisation, worker or product-surface change. It
fails closed because the release does not publish a checkpoint SHA-256 or
checkpoint-specific allowed-use terms, and static-inspection/resource/worker
contracts are not yet complete. The broad upstream requirements were reduced
to the actual two-file model import surface. The future adapter must bypass the
package initializer that imports an unrelated MelBand model, and it will use
standard-library PCM WAV I/O. That removes librosa, SciPy, scikit-learn, Numba,
SoXR, SoundFile and bundled media libraries from the plan. A 15-package,
wheel-only, version-and-hash lock now resolves for CPython 3.12.10 on this
Darwin arm64 Mac without installation. All 15 exact releases have an attached
licence audit and permit private local evaluation; binary redistribution still
requires notice review. The lock is reserved for a fresh environment, not
`.venv-ai`. No download or approval request is appropriate while checkpoint,
static-inspection, worker and resource preconditions remain open.

The candidate is now bound to Sunofriend's existing parent-issued checkpoint
inspection and worker request/result schemas. The inspector caps
checkpoint, ZIP and pickle work, pins a non-inheritable descriptor, inventories
pickle opcodes without deserialising them and never authorises loading. The
non-executable RoFormer protocol now validates one or two path-free canonical
15-second stereo 44.1 kHz PCM24 case identities, canonical sorted
`bass`/`drums`/`other`/`vocals` outputs, one fresh worker and quarantine per
case, no network or child processes, and parent-verified hashes plus exact
source-frame geometry. It is self-hashed, immutable and deliberately cannot
materialise the private request. These are safety contracts, not a new model
runner: no candidate checkpoint has been inspected and no executable adapter
has been implemented.

The two-module source boundary is now independently enforceable. A tracked
manifest binds `attend.py` at SHA-256
`0459d799ade55541df2994b0becf7aec12214491360c5a06e346f6d615eaed15`,
`bs_roformer.py` at
`93408c7254c60c48e47be0657a64745065396b0b1c6da4e02c75aca57eb62bf3`
and the release MIT licence at
`3282dc057695ef5b9a64909a7092ca40b2c292c232580fc6ace6e5d665cc0207`.
The read-only verifier passed on the exact temporary release checkout while
making no imports, writes, network calls or process launches. The verifier now
also caps each module at 64 KiB and parses its AST without execution. Exact
direct-import roots are manifest-bound; relative and wildcard imports,
dynamic-import calls and runtime code-generation calls fail closed. A 1 August
2026 official release-API recheck still found no checkpoint digest or
checkpoint-specific terms. The exact release, tag-ref and pinned-revision
licence fields from that observation are retained in a tracked 3,362-byte
snapshot with SHA-256
`7767d27d2b4e75f0780560e1510ca835af35a0f5600c200add5654b9cf875bd8`.
Its no-network verifier returns `verified_no_checkpoint_authority`: it proves
the recorded tag/revision and missing release evidence without converting
absence into permission. The private admission now verifies this fifth
repository artifact alongside the source/runtime/licence evidence. A future
worker must repeat the source check on its
own source tree; the current plan does not claim that a durable runtime
checkout exists, that the checkpoint is approved or that it has been loaded.

A separate private admission command now cross-binds that source verification
to the exact source manifest, six-package input, 15-package wheel/hash lock and
exact-version licence audit. It semantically verifies lock coverage and the
audit's private-local-use, no-installation and no-checkpoint-terms findings,
then emits a self-hashed path-free result. The result remains `blocked` and
explicitly records false checkpoint-open, download, deserialisation, model-
import, process and product-route effects. It closes only the code/runtime-plan
integrity increment; checkpoint terms, a published checkpoint hash, static
checkpoint inspection, runtime installation approval and the bounded worker
remain open.

The separate role-specific path now has a stronger identity and licence
starting point. The exact
[`mlx-community/mel-roformer-kim-vocal-2-mlx`](https://huggingface.co/mlx-community/mel-roformer-kim-vocal-2-mlx)
revision `64cbfcb004e39430e5f584552c05949440ec39ce` publishes a
456,483,463-byte Safetensors file with SHA-256
`312c38e5b698f8dfaa4d6064e8f79010744825828917871a9d22673a43eb7fe5`.
Its original author-hosted Kim Vocal 2 checkpoint was explicitly changed from
GPL-3.0 to MIT at revision
`ac9b0614ab3cd7f77219e18ba494dfd93956c348`, and two independent LFS
records reproduce its 913,106,900-byte source hash. A tracked, no-network
verifier preserves those facts and records two hash-stable ViperX alternatives
as rejected because their creator-authorised terms remain unverified.

This is a vocal-only private challenger, not a broad separator or public
feature. A supplied evidence ZIP was reviewed as a secondary lead; its
download helper was not run. On 1 August 2026 the user explicitly approved
private local evaluation of the exact Kim Vocal 2 checkpoint. The exact
checkpoint and audited source were subsequently placed in an owner-only cache
outside the repository; no model is redistributed.

The exact non-executable runtime and inspection slice is now complete. The
five required MLX-Audio `v0.4.3` source/runtime files are pinned to revision
`41092c02db18efd5b9d8281b2fcc41d84801757a`, with their MIT licence and package
metadata. A minimal macOS arm64/Python 3.12 lock names only MLX 0.31.2,
MLX-Metal 0.31.2 and NumPy 2.3.5 with exact wheel identities and licence
findings. The upstream network-capable `from_pretrained` convenience loader is
explicitly forbidden. The audit records its stale GPL comment about Kim Vocal
2 but continues to derive checkpoint terms from the owner's later immutable
MIT relicense evidence.
The future adapter must additionally turn the upstream non-strict load into a
fail-closed boundary by proving complete post-sanitisation model-key coverage.

A bounded standard-library Safetensors parser validates header size, unique
JSON keys, metadata shape, dtype/shape/offset agreement and complete
non-overlapping data coverage while hashing tensor bytes as opaque data. The
exact 456,483,463-byte checkpoint passed with 708 BF16 tensors. Its MLX
conversion contains non-canonical null metadata; the result calls that out as
a specific compatibility exception rather than claiming Safetensors metadata
conformance. The inspection does not deserialize tensors or import a
tensor/model runtime. A separate
self-hashed protocol fixes one or two maximum-15-second canonical inputs and
exactly two outputs, vocals plus mixture-minus-vocals instrumental, including
PCM reconstruction accounting. Artifact preflight passes for the exact source,
config, licence and checkpoint. A separate private loader probe now re-verifies
those artifacts at execution time, bypasses all upstream package initializers
and `from_pretrained`, pins the checkpoint descriptor, and independently proves
the 708-raw-key to 696-model-parameter sanitizer mapping. The real probe
  completed with zero missing, unexpected or shape-mismatched tensors and about
  458 MB peak MLX memory, without audio inference. Exact source-to-BF16
  weight-conversion parity now passes for all 708 converted tensors, including
  12 packed Q/K/V splits. The BF16-roundtrip PyTorch implementation and BF16
  MLX runtime subsequently reached 117.70 dB SDR on the same authorised music
  frames. Original FP32 versus BF16 MLX reached 29.14 dB, localising the
  remaining observed difference to publication precision. A separate
model-free macOS canary has observed `EPERM` for an identical loopback
connection that returned `ECONNREFUSED` without the profile, but it does not
observe arbitrary model attempts or authorize the worker. Bounded single-call
inference is now measured through eight seconds. The 15-second transport uses
three
eight-second chunks at a four-second hop, returned the exact 661,500-frame
horizon in about 2.6 seconds, reported about 2.42 GB peak MLX memory and passed
additive residual accounting at `7.45e-9` maximum float32 error. No output was
persisted by that run. A separate model-independent PCM24 boundary now writes
and parent-verifies exact deterministic vocals/instrumental files from
precomputed arrays, including the full 15-second geometry, but it is not yet
bound to the worker or authorised excerpt.

The same adapter then accepted the exact self-hashed `Be Alone` 191–206 second
authorisation receipt and its hash-bound PCM24 model input. The real-song run
completed in about 2.78 seconds with the same measured peak, produced active
vocal and instrumental arrays and closed additive accounting at `2.98e-8`.
Only path-free hashes and measurements were returned. This proves bounded real
transport, not separation quality.

The no-output control comparison then bound the exact role-mapping report and
four PCM24 vocal controls to that same receipt. Candidate similarity was
`0.9948` to Moises, `0.9736` to HTDemucs and about `0.92` to each Suno control.
The controls also disagreed with one another, so no source was treated as
ground truth and no ranking or winner was emitted. Repeated GPU runs varied by
at most one projected PCM24 least-significant bit. Two explicit CPU-mode
15-second synthetic runs were byte-identical, but took about 23.4 seconds each
and used about 3.58 GB peak versus roughly 2.8 seconds and 2.42 GB for GPU. The
future worker policy therefore names `fast_gpu` as the default and
`repeatable_cpu` as the optional deterministic mode; every actual artifact must
still receive its own hash and per-run reconstruction check.

The intervening model-independent adapter contract is now implemented and
tested with injected synthetic result data only. It invokes no engine. The
contract rejects wrong audio geometry, non-finite or unbounded samples,
incomplete post-sanitisation model-key coverage, arbitrary dropped weights or
any claimed operational side effect. It derives the instrumental residual,
hashes both float32 outputs and proves additive closure. The same core now
accepts only the exact private real-engine record, and both full-excerpt smoke
tests passed through it. PCM24 persistence and the worker remain absent. This
reduces the amount of new logic that must be trusted after approval without
weakening the download, install, checkpoint or product-route gates.

### 2026-07-31 — Second authorised separation-to-MIDI repeat

- Goal: test whether the first real-song observations repeat on different
  authorised music before considering any separator or role mapping usable by
  default.
- Change or experiment: selected a 15-second window with a deterministic
  cross-pack/role activity scan, then repeated the exact self-hashed excerpt,
  local HTDemucs, provider alignment, four-role mapping, production repair,
  vocal contour, independent evaluation and dry-render chain.
- Inputs: Ezzye `I am a Alien mashup`, original seconds 219–234, Eb minor,
  114 BPM, A=440 Hz; one detailed Moises pack and two distinct nine-stem Suno
  packs.
- Model/runtime/checkpoint: unchanged from the first authorised run; the same
  pinned private HTDemucs 4.0.1 checkpoint and existing Sunofriend production
  MIDI components were used.
- Evidence and metrics: all provider sums had zero envelope lag; recorded-zero
  correlation was 0.99952 for Moises, 0.92357 for Suno A and 0.91953 for Suno
  B. All twelve roles ranked first, but broad-`other` mapping margins were only
  +0.119/+0.055/+0.132. Provider-to-local drum onset F1 was
  0.861/0.874/0.819; bass exact-pitch/onset F1 0.462/0.190/0.273;
  broad-`other` exact-pitch/onset F1 0.243/0.164/0.188; dominant-vocal
  exact-pitch/onset F1 0.844/0.864/0.791.
- Listening result: pending. The first song's four blind screening choices are
  still open; no second review burden is added before those are returned.
- Decision: the first pattern partly repeats. Drum timing is stable and
  composite `other` is not instrument-specific enough. Bass remains
  separator-dependent. Vocal agreement is passage-dependent and substantially
  stronger here. Keep every role/provider inactive and make future evaluation
  and selection role-specific.
- Problems/risks: no score truth exists; the provider-to-local metric measures
  agreement rather than correctness; full-mix reference listening is still
  required; the current four broad roles cannot answer which instrument owns
  notes inside `other`.
- Next smallest step: collect the existing four blind choices, then design one
  narrower `other` hypothesis using already-separated keys/guitar/synth parts
  rather than adding more broad-role review pages.

### 2026-07-31 — First authorised separation-to-MIDI parity run

- Goal: determine whether the first real authorised excerpt remains musically
  comparable after local and provider separation are passed through identical
  Sunofriend MIDI processing, without using any separator as score truth.
- Change or experiment: added a private-only runner that validates the
  self-hashed role-mapping receipt and all artifacts, applies the production
  repair loop to bass, drums and broad `other`, applies the separate production
  pYIN dominant contour to vocals, independently evaluates and dry-renders
  every non-empty primary and variant, and compares provider primary MIDI with
  local HTDemucs primary MIDI. No product surface imports the runner.
- Inputs: the authorised Ezzye `Be Alone` excerpt at original seconds 191–206,
  provisional four-role Moises and two Suno packs, and the pinned local
  HTDemucs groups; 136 BPM and A=440 Hz.
- Model/runtime/checkpoint: existing Sunofriend production Basic Pitch,
  drum-classification, pYIN, refinement, evaluator, FluidSynth and GeneralUser
  GM paths; local separation remains the pinned private HTDemucs 4.0.1
  checkpoint recorded by the upstream receipt.
- Evidence and metrics: local MIDI contained 16 bass notes, 99 drum hits, 74
  broad-`other` notes and 13 dominant-vocal notes. Provider-to-local drum onset
  F1 was 0.939/0.890/0.900 for Moises/Suno A/Suno B; bass exact-pitch/onset F1
  was 0.526/0.545/0.200; broad-`other` exact-pitch/onset F1 was
  0.225/0.252/0.161; vocal exact-pitch/onset F1 was 0.483/0.417/0.400. The
  report binds 231 artifacts and all selection, activation and product
  permissions remain false.
- Listening result: pending. Dry primary and variant auditions exist for all
  four local/provider packs, but metrics do not choose a winner. A four-choice
  blind screening package is ready locally: one full-excerpt decision each for
  bass, drums, broad `other` and dominant vocals. Candidate pairs are
  level-matched; the original mix remains an unlevelled common reference;
  equivalent, neither and cannot-tell outcomes are valid.
- Decision: retain the four-way partition as useful comparison evidence, not
  a production mapping. Drum timing is comparatively stable; broad `other`,
  bass and dominant vocals remain separator-dependent. Do not globally rank
  providers or enable a separator from this one excerpt.
- Problems/risks: local HTDemucs is only a relative baseline; broad `other`
  contains multiple instruments; a 15-second passage cannot establish
  full-song or cross-song quality; General MIDI auditions do not test final
  GarageBand instruments.
- Next smallest step: prepare a short human listening review from the existing
  evidence, then repeat the same receipt chain on a second authorised song and
  test narrower `other`/drum hypotheses.

### 2026-07-27 — Stage 4 keys functional preflight and fixed-MIDI A/B

- Goal: extend the existing bass instrument review to keys without publishing
  a keyboard A/B that has an unmeasured response gap, while keeping the chosen
  musical performance fixed.
- Pair and binding: bass retains zero-based GM Synth Bass 1/2 programmes 38/39
  and reports coverage `not_required`. Keys uses Electric Piano 1/2 programmes
  4/5. Both roles bind the current arrangement-selection, selected MIDI,
  verified SoundFont, FluidSynth renderer and anonymous identity commitment.
  The selected-MIDI A/B still differs only in audited Program Change bytes.
- Keys preflight: for each occupied channel, pitch and soft (1–42), medium
  (43–84) or strong (85–127) velocity bucket, test the minimum velocity
  actually observed in that zone. CC120/CC123 guards bracket 0.20-second notes
  in 0.35-second slots. The probe is bounded to 512 zones and 180 seconds.
  Both private identities must reach −72 dBFS RMS and −60 dBFS peak, at least
  3 dB active RMS above the 50 ms pre-note guard, and no more than a 24 dB
  velocity-normalised deficit from the same channel/bucket median when peers
  exist.
- Local acceptance evidence: the private Pupsies keys selection
  `mode_repair/keys_listened.mid` exercised 73 representative zones with the
  GeneralUser-GS bank SHA-256
  `9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe`.
  Both programmes passed. Programme 4 measured minimum RMS −51.993632 dBFS,
  minimum peak −43.150302 dBFS, minimum active-over-guard 41.158745 dB and
  maximum normalised deficit 11.428001 dB. Programme 5 measured −56.26035,
  −46.962652, 3.886066 and 11.171982 dB respectively. The 3 dB guard was
  calibrated to retain this valid dry Electric Piano 2 release-tail case;
  a constant-drone adversarial fixture remains rejected at 0 dB.
- Privacy and effects: synthetic probe MIDI is private, owner-only and
  rebuildable. Raw probe audio is deleted after measurement and can be
  re-rendered from verified inputs. Only blind, path-free aggregate response
  evidence reaches the loopback browser. Preflight, A/B preparation/playback,
  review and resolution do not mutate MIDI, selection, ranking, defaults,
  mixes, packs or exports.
- Decision: integrate the keys sibling, but keep
  `quality_status: review_required` for bass and keys. A pass proves only
  representative measurable response. It does not prove pitch/octave
  correctness, every-velocity audibility, chord/polyphonic clarity, tone
  consistency or source similarity, GarageBand equivalence, or a winner,
  recommendation or default. Listening to the unchanged selected-MIDI A/B
  remains mandatory.
- Validation: the complete instrument-review gate passed 56 tests, including
  malformed evidence and the constant-drone guard failure. Adjacent Workbench
  UI, server and core gates passed 102, 28 and 32 tests respectively. The
  complete repository suite passed 1,285 tests with the existing single
  `resampy`/`pkg_resources` deprecation warning.
- Next smallest step: run the human keys A/B in musical context, then add
  another role only with its own narrowly scoped functional evidence rather
  than generalising this keyboard probe.

### 2026-07-27 — Native TUI Listening Master operation

- Goal: make the fixed-policy comparative challenger available in the preferred
  Guided Local Studio without duplicating its audio policy or weakening the
  accepted balanced v3 control.
- Change: added a parameter-free **Master** tab operation over the same
  `WorkbenchListeningMasterService` used by Workbench. It derives the exact
  current selection and balanced-control manifests from read-only folded state,
  reuses a verified content-addressed cache hit without FFmpeg, or runs a
  path-free SoundFile/FFmpeg/`loudnorm` preflight before a fresh build. The
  runner rechecks both hashes before promotion and discards pending work if
  either changed. It rereads both immediately after promotion and refuses a
  successful/current result if an independently launched local Workbench
  changed them in that final gap; the old content-addressed entry remains only
  a non-current cache.
- Interaction boundary: the form exposes no audio/output path, target, filter
  graph, policy selector or release-master switch. An explicit confirmation,
  bounded progress and private result paths are presentation only. Project,
  conversion and Workbench controls remain locked during synchronous work;
  Quit is deferred rather than claiming a process-safe cancel that does not
  exist.
- Evidence boundary: the challenger remains `mastered: true` and
  `release_master: false`. Create, reuse, progress and display record no event,
  review, feedback or preference and change no MIDI, selection, ranking,
  default, required-product completion or GarageBand Pack.
- Listening result: none recorded by this increment. Workbench remains the
  surface for hearing/downloading both the unchanged control and challenger.
- Decision: keep TUI, Workbench and CLI as adapters over one immutable
  listening-master contract. Cache reuse must remain verified and must not
  depend on the fresh-build toolchain.
- Next smallest step: completed in the following bounded Workbench blind-review
  increment and its subsequent native-level readiness increment below.

### 2026-07-27 — Bounded blind Listening Master quality review

- Goal: let a listener judge processing quality without knowing which exact
  artifact is the gain-only control and without letting a simple level
  difference dominate the first choice.
- Change: ordinary Workbench now prepares one exact 0.5–15 second frame window
  from the current balanced control and current Listening Master. Both windows
  must be at least −60 dBFS RMS. Only the louder crop may be attenuated, by at
  most 18 dB, and the generated PCM16 A/B WAVs must finish within 0.05 dB
  fixed-window RMS. No boost, limiting, compression, EQ, resampling, time shift
  or time stretch is used; this is not LUFS, true-peak or perceived-loudness
  matching.
- Review contract: A/B assignment is random, stable for the exact comparison
  and hidden behind a 32-byte nonce commitment. The reviewer explicitly marks
  both candidates heard, chooses A, B, equivalent, neither or cannot tell, and
  may add at most eight allow-listed tags per candidate plus a 2,000-character
  private note. Playback and drafting write nothing. **Complete blind review**
  is the only feedback append and stays blind. A separate **Resolve A/B
  identities** action reveals the nonce and mapping and writes only the
  resolution.
- Evidence boundary: review audio, SQLite state and exports are owner-only and
  remain outside `WorkbenchStore`. Selection, MIDI, candidate ranking,
  balanced/master bytes, defaults, product completion and GarageBand Pack
  state stay unchanged. A resolved preference is evidence, never automatic
  promotion.
- Validation: isolated audio/ledger tests, real loopback HTTP tests, browser
  controller tests and Developer Inspector privacy/effect tests cover restart,
  CAS, Range media, tamper/drift rejection, explicit heard evidence, blind and
  resolved downloads and zero musical/product mutation.
- Next smallest step: completed in the following native-level readiness
  increment; then feed explicitly named verified reviews into advisory profile
  analysis without automatic ranking or default changes.

### 2026-07-27 — Identity-labelled native-level readiness review

- Goal: answer the separate practical question of which delivered file is more
  useful at its own level without allowing loudness to bias or rewrite the
  earlier blind processing-quality choice.
- Gate: Workbench enables this stage only for the latest local blind quality
  review after its separate identity resolution has been verified. The
  readiness comparison binds the quality review ID/SHA, resolution SHA,
  current control/master manifests and exact canonical frame window.
- Audio contract: the reviewer cannot submit times, paths, gains or policy
  parameters. Sunofriend reuses the exact quality frames and writes labelled
  Balanced control and Listening Master PCM24 crops with linear scale `1.0`
  and applied gain `0.0 dB`. There is no matching, boost, attenuation,
  normalisation, limiting, compression, EQ, resampling, shift or stretch.
- Review contract: both labelled files must be explicitly marked heard before
  choosing control, master, equivalent, neither or cannot tell. Tags and notes
  retain the existing bounds. One immutable response is allowed for the exact
  quality result and local reviewer: an exact retry replays the verified
  record and a changed retry conflicts.
- Evidence boundary: readiness audio and its SQLite row are owner-only,
  path-free at the browser boundary and separate from the quality ledger and
  `WorkbenchStore`. Preparation, playback, completion and export change no
  quality outcome, candidate decision, selected MIDI, ranking, default,
  product bytes/completion or GarageBand Pack.
- Maintainability: verified file reads, exact-frame decode, PCM16 writing and
  measurements moved into `workbench_master_review_audio`; blind quality and
  native readiness remain sibling services rather than modes in one contract.
- Validation: service, tamper/restart/concurrency, real loopback HTTP, browser
  double-submit/unity-volume and Developer Inspector privacy/effect tests are
  included. The final focused gate passed 73 tests and the repository suite
  passed 1,249 tests; the sole warning remains the existing
  `resampy`/`pkg_resources` deprecation. The next increment is
  complete-instrument challengers, beginning with bass and keys while holding
  MIDI fixed. The first bounded bass challenger is now a real Workbench Stage
  4: it hash-pins one currently selected bass lane and renders its unchanged
  performance through complete GM Synth Bass 1 and Synth Bass 2 patches. A
  source crop is a labelled reference; source and candidates are
  attenuation-only matched to the quietest fixed-window RMS and share one
  −1 dBFS sample-peak guard. The two rendered candidates remain blind until
  explicit heard/choice feedback is complete, and resolution is evidence
  rather than automatic promotion. At this checkpoint keys remained the next
  sibling because they needed a separate response probe; the newer Stage 4
  keys entry above records that completed follow-on without rewriting this
  bass evidence.
- Validation: 14 backend tests and the 34-test artifact/backend/server/browser
  integration gate cover bank/program ordering, immutable proxies, common
  level matching, resource bounds, restart, races and privacy. The wider
  adjacent Workbench gate passed 125 tests and the complete repository passed
  1,275 tests. The sole warning remains the existing
  `resampy`/`pkg_resources` deprecation.

### 2026-07-27 — Workbench Listening Master v1

- Goal: make the already implemented fixed-policy challenger approachable
  without replacing the accepted gain-only v3 song interpretation.
- Change: ordinary Workbench now exposes **Create Listening Master
  challenger** after the exact current balanced artifact exists. Its POST
  accepts only the current selection-manifest and balanced-arrangement
  manifest hashes. A separate application service prepares in owner-only
  storage, verifies the PCM24 WAV and `sunofriend.listening-master.v2` receipt,
  rechecks current selection/control state and publishes a content-addressed
  player plus WAV/receipt downloads.
- Evidence boundary: the balanced v3 player remains visible, unchanged and the
  required product output. The challenger remains `mastered: true`,
  `release_master: false`. Creating, caching, playing or downloading it records
  no event, review, feedback or preference and changes no MIDI, selection,
  ranking, default, required-product completion or GarageBand pack.
- Decision: keep the standalone fresh-path CLI and Workbench action as two thin
  clients of one immutable listening-master contract. Do not expose browser
  paths, targets, filter graphs or policy selection.
- Listening result: none recorded by this increment; UI availability and
  objective measurements are not a preference.
- Next smallest step: completed for native TUI orchestration and for the
  bounded level-matched Workbench review. Native-level readiness remains a
  separate later comparison.

### 2026-07-27 — Pupsies golden balance and Listening Master v1

- Goal: retain the useful, praised MIDI interpolation as an exact control while
  adding a reproducible listening-master challenger and making rendering
  quality a first-class goal alongside editable MIDI.
- Change: added standalone `sunofriend listening-master BALANCED.wav --out
  FRESH.wav --report FRESH.json`. Its fixed
  `ffmpeg-loudnorm-two-pass-fixed-horizon-v1` policy targets −16 LUFS
  integrated, 11 LU loudness range and −1 dBTP, writes PCM24, preserves the
  exact input frame horizon, independently verifies the encoded artifact and
  records `mastered: true` plus `release_master: false`. The existing gain-only
  v3 control is not replaced.
- Maintainability: the renderer and cache verifier now share the frozen
  `BALANCED_MIX_CONTRACT` for v3 schemas, measurements, safety limits and
  mastering boundary. A shared role/instrument registry and extraction of
  balanced-artifact orchestration from the large Workbench artifact module are
  the next refactors.
- Feedback: added an owner-only v2 foundation that distinguishes balanced
  controls from listening-master challengers, binds each master back to its
  exact control, requires `cannot_tell` for mastering on an unmastered control,
  and separates path-free artifact identity from a domain-hashed
  reviewer/session identity. Profiles re-verify every named artifact and
  remain advisory; no playback changes a default.
- Inputs: the private Pupsies B-major, 119 BPM balanced selected-MIDI result,
  containing 22 selected lanes across 15 source groups. Fourteen lanes reached
  the +6 dB source-match clamp.
- Evidence and metrics: the exact gain-only control SHA-256 is
  `c202bba190d0556f2909cb072137f65e92863eba0f6d724c5f279414d98e2763`.
  FFmpeg measured it at −17.37 LUFS integrated, −0.99 dBTP and 4.0 LU LRA.
  The challenger reached exactly −16.00 LUFS and −1.00 dBTP, with 4.2 LU
  output LRA and the same 7,338,321-frame, 44.1 kHz horizon. Its SHA-256 is
  `5e8e59c716602168d1e0996295369e1c3ea536c6ca2aaf3d7798151929fd1e43`;
  hardened receipt-file SHA-256 is
  `ba7ddbdcd9b2310d2b3c475219c13439021e22e0810989133af9825ba89d8cbb`;
  internal unsigned-payload commitment is
  `46981e4547db0ddb1fb5eca357df685377bcedd0842e02c3b0cc123caeed3bbc`.
  The hardened artifact uses the `sunofriend.listening-master.v2` receipt
  schema so it cannot be confused with the earlier unpinned v1 renderer
  record.
- Listening result: the user described the v3 balanced control as very good,
  good-sounding and especially helpful for understanding the song without
  distracting effects. The new listening master has objective safety evidence
  but has not yet won a human control/challenger A/B.
- Decision: make musical rendering and a good mixed/mastered listening WAV an
  explicit product goal. Preserve dry unity and accepted v3 controls, change
  one declared dimension per challenger, and require receipt-bound explicit
  listening before any bounded promotion. No play, download, metric or default
  position counts as feedback.
- Problems/risks: 14 source-match clamps show that neutral proxy
  instrumentation and source-level matching still interact strongly. A louder
  master may be preferred for loudness alone. The standalone local feedback
  foundation is not yet a Workbench/TUI feedback interface.
- Next smallest step: completed for Workbench evidence-only playback and native
  TUI orchestration in the following increments; explicit blinded
  receipt-bound ratings remain, followed by complete bass and keys instrument
  challengers with fixed MIDI before any balance-policy change.

### 2026-07-26 — Pupsies continuous synth-bass correction

- Goal: stop an invalid Workbench result space and short, octave-confused
  plucked proxies from making a continuous buzzing bass sound like another
  song.
- Change: automatic discovery now excludes arrangement-named, multi-role,
  incompatible-BPM/key and neutral-audition-duplicate MIDI while retaining
  layered single-role and explicit invalid/empty diagnostics. Bass adds a
  separate pYIN-backed `octave_resolved` challenger and an exact-pitch-gated
  `continuous_sustain` challenger. Workbench v3 renders bass with GM 39 Synth
  Bass 1 and applies disclosed browser-only active-block gains in the precise
  per-stem switcher.
- Inputs: private Pupsies `misery.` bass stem, B major, 119 BPM, 166.402
  seconds. The current source is byte-identical to the source used by the
  previous conversion.
- Evidence: the old normal view contained one genuine 204-note bass, its
  audible duplicate, a flattened 1,374-note drums/bass/pads arrangement and
  two incompatible 124 BPM transforms. The new 165-note octave-resolved lane
  shifts 31 strongly supported octave harmonics and raises exact pYIN pitch
  agreement from 79.2% to 90.9%. The continuous lane extends 51 note ends by
  10.761 seconds, covers 89.7% of pYIN-voiced frames and measures 91.6% exact
  pitch agreement. In the first 15 seconds the comparison receipt applies
  −4.150 dB to source and +8.504 dB to the MIDI proxy towards the common
  −18 dBFS target.
- Listening result: pending the user's fresh three-lane TUI/Workbench review;
  engineering metrics must not become a preference.
- Decision: retain `contour_clean` as repair mode's main output. Present
  contour-clean, continuous-sustain and octave-resolved as the three primary
  lanes and raw/root-safe as advanced evidence. Treat buzz as patch texture,
  not MIDI-note data.
- Validation: 155 focused tests and the complete 1,114-test suite pass. Ruff,
  Python compilation, JavaScript syntax and `git diff --check` pass. The only
  warning is the existing third-party `resampy`/`pkg_resources` deprecation.
- Next smallest step: collect the user's continuity/register/texture review.
  If the MIDI contour is accepted but the proxy timbre is not, continue with a
  separate GarageBand synth-patch or source-derived instrument comparison
  rather than changing the notes.

### 2026-07-26 — Phase 5.10b initial full-project conversion runner

- Goal: let a human learn and run the normal complete project conversion in
  the TUI without asking an agent to construct shell commands.
- Change: added an editable **Fresh conversion output** field,
  `--conversion-output` prefill and an explicitly confirmed **Convert all
  stems** operation. Prefilling never starts work.
- Engine contract: the runner uses production `listen-all` in repair mode with
  candidate-variant evaluation, followed by separate production
  `vocal-melody` operations for discovered lead and backing-vocal stems.
  `wind` → `lead`, `rhythm` → `keys` and `other` → `synth` are disclosed proxy
  engines, not instrument-identification claims. Near-silent inputs are
  skipped visibly.
- Safety/state contract: an existing output is rejected; progress is streamed
  into bounded memory; cancel preserves the partial fresh root;
  success reloads the new candidate root; no path automatically starts,
  retries, overwrites, ranks or selects MIDI. Workbench remains review-only.
- Deliberate limits: there is no durable job ledger, restart recovery or
  automatic partial-tree resume yet. Standalone one-stem/vocal forms, common
  transformations, guided review progress and structured local feedback remain
  later increments.
- Next smallest step: exercise the mixed instrumental/vocal/proxy/near-silent
  outcomes on a real complete project before designing the durable ledger.

### 2026-07-26 — Phase 5.10a Guided Local Studio TUI

- Goal: let a lay user orient themselves, inspect current output and reach the
  complete visual review surface without relying on an agent to construct
  commands.
- Change: added `sunofriend tui`, a Textual project dashboard with key, BPM,
  tuning, stem/candidate/decision progress, compact primary-MIDI contour and
  activity maps, local capability diagnostics, a bounded memory-only activity
  log and one-key Workbench launch. The Workbench starts with its read-only
  Developer Inspector available by default and is stopped/reaped on request or
  TUI exit.
- Evidence contract: project loading does not create a decision database;
  existing explicit state is folded read-only. The widget projections contain
  no paths, project loading and MIDI maps have all-false musical effects, and
  Workbench tokens and decision-store paths are hidden from the activity log.
- Validation: a private 16-stem/46-candidate long-song smoke exercised the
  large and compact layouts without recording a preference; wheel/sdist
  inspection verified the TUI dependency and canonical skill resources; the
  complete suite passed 1,107 tests with the one existing third-party
  `resampy`/`pkg_resources` deprecation warning; and the final independent
  audit was clean.
- Decision: make the TUI the preferred human route while retaining direct CLI,
  Workbench and agent-skill expert routes.
- Problems/risks at close-out: 5.10a did not run conversion, keep a durable job
  ledger or record structured improvement feedback. The initial conversion
  capability was added separately in 5.10b.
- Next smallest step at close-out: implement one read-only 5.10b operation
  preview/preflight before adding a cancellable fresh-output `listen-all` job;
  that first 5.10b slice is now implemented above.

### 2026-07-25 — Phase 2 final evidence and balanced selected-MIDI audition

- Phase 2 goal: resolve the final assembled reviewed-versus-automatic listening
  gate without inferring a whole-melody preference from the earlier phrase
  choices or objective metrics.
- Phase 2 evidence: the reviewed browser export SHA-256 is
  `15ad1de80c5485b4c6dfeb05f158123218595ce698f763a3d53cc05c646ec275`.
  `midi-ab-resolve` verified it against package commitment
  `ea2b3f6367e1b0856db01c80902a1fadda1f42e0362f032f29c30ccf89c3b778`;
  the resolved result SHA-256 is
  `252fd87b3fd2e9a0a7b156426eca79562959159999f67dca07318e816568efdd`.
- Phase 2 listening result: the 61-note reviewed assembly was preferred to the
  untouched 23-note automatic candidate for the opening 0.250–4.966 second
  loop. The 4.988–9.860 and 10.600–15.000 second loops were both judged
  **neither**. The automatic candidate won no loop. This is a local
  opening-phrase improvement, not evidence that the reviewed melody is
  preferable overall; the Phase 2 programme success criterion was not met.
  Every source/MIDI mutation, selection, promotion and default-change effect is
  false.
- Arrangement goal: make the selected MIDI useful as a combined listening
  sample when several unity-gain drum tracks mask bass, keys and other pitched
  parts, without corrupting the dry technical evidence or pretending to create
  a release master.
- Change: ordinary Workbench now offers a separate
  `sunofriend.workbench-balanced-arrangement.v1` derivative. It measures each
  selected neutral preview against its verified matching stem, measures and
  calibrates the actual waveform sum of same-source alternatives, applies a
  bounded drum-bus guard, then uses gain-only audition normalisation with a
  −1 dBFS sample-peak ceiling. It writes a PCM24 WAV, path-free exact receipt
  and GarageBand fader recipe. The API accepts only the current
  selection-manifest hash.
- Arrangement evidence: the 10-part Train smoke produced a source-horizon
  199.200 second PCM24 WAV under
  `source-referenced-summed-group-balance-v3`, cache key
  `7026d22f124ccdd5aff4eb6e66247bc12a6f509310792d9e795636cf85978fd1`.
  In 360 qualifying overlap windows, the drum/non-drum
  median and p95 changed from −2.081/+9.625 dB to −8.706/+3.000 dB after a
  −6.625 dB guard, meeting both drum targets. Final median active-block RMS was
  −18.325 dBFS with a −1.000 dBFS sample peak and zero full-scale samples. The
  requested −18 dBFS target was truthfully marked unmet by −0.325 dB because
  the sample-peak ceiling prevented more gain. WAV SHA-256 is
  `eea86a2f57d984850c6b3b1defb93969813239a228fd6880659d970769d46e0c`;
  the receipt **file** SHA-256 is
  `d8c187a425d19d087d15e305ccc830c71311a5ff7f966ab9b2c80f13a8b66032`,
  while its separate internal unsigned-payload commitment
  `receipt_sha256` is
  `9f2f76c7bffbf7b7629ab5f09c9cc354cdc322754a688019f119eb6d3ada07fe`.
  The GarageBand recipe SHA-256 is
  `d2f792c7515938d133f638cd6ea0ebf4a09a85855879e59015e8f1efe3433e57`.
- Verification: the focused balanced-audition, UI and developer suite passed
  125 tests; the complete repository suite passed 1085 tests in 308.23
  seconds. The sole warning is the existing third-party
  `resampy`/`pkg_resources` deprecation warning.
- Boundary: the dry proxy and all decoded transports remain unity gain. No MIDI
  note, velocity, timing, source, selection, review event, feedback or default
  changes. Compression, limiting, EQ, saturation and creative effects remain
  off; the report records `mastered: false`. The new artifacts are
  Workbench-only and are not standalone CLI or GarageBand Pack Composer v1
  outputs. Final patch choice, mix automation and mastering remain in
  GarageBand.

### 2026-07-23 — Phase 1 closed; first genuine Phase 2 choices applied

- Goal: close the outstanding human evidence honestly and turn the first real
  phrase choices into an auditable MIDI result.
- Phase 1: the private `sunofriend.phase1-listening-review.v1` export is
  complete with all 46 required 1–5 scores and explicit choices. Its SHA-256
  is
  `b70863f5b64a6bea9e47c2187c8965780eeb0b7be2bddf92ef682017f72be75f`.
  Bass preferred MuScriptor; backing preferred MuScriptor for the dominant line
  and the existing harmony stack for polyphonic representation; neutral
  MuScriptor velocity was preferred to source-derived expression. Phase 1 is
  complete. Free-text notes remain private.
- Phase 2: the reviewed export SHA-256 is
  `0626b1dc2f62f50ef064792f9b547a3fd2afe64c98a37856aaaff4b461f9a48c`.
  It pins source SHA-256
  `a52b874719af8468e087ba62dec628cca142e6c649f79a718bbe9f880475a488`
  and tracker-run SHA-256
  `258aaf9c821aa59e6627cfffe1abe96016ad09ada3e31529d80f0929bcc86bc6`.
  All three musical-length units were explicitly reviewed and selected raw
  Basic Pitch instead of the automatic combined default.
- Applied evidence: `melody-apply` produced a fresh 61-note, 119 BPM MIDI and
  retained the complete three-choice audit. The reviewed evaluation scored
  strong/possible onset F1 0.2059/0.4091, timing p95 35.21 ms, chroma 0.9266,
  supported-note ratio 0.6230 and contour-direction accuracy 0.5745. The
  untouched 23-note automatic combined candidate scored
  0.3810/0.3396, 37.50 ms, 0.8872, 0.4348 and 0.5455 respectively. This is a
  useful multi-metric trade-off, not an automatic accuracy verdict.
- Personal calibration: the first genuine advisory profile contains three
  explicit observations, all for Basic Pitch, at SHA-256
  `84e91173a5423f8baa9e50db7ff96ff3094b5e48790d2c8dfd221ae034afdee8`.
  It remains local, deterministic and advisory; it does not reorder candidates,
  change defaults or select future melodies.
- Phase 2 gate as of 23 July: record one explicit preference between the assembled
  reviewed neutral rendering and the untouched automatic candidate. The phrase
  review itself is complete, but that separate programme success criterion is
  not inferred from JSON structure or objective metrics. A private three-loop
  blind package is ready at
  `work/ai-bakeoff/lidl-vocals-30-45/phase2-final-reviewed-vs-automatic-ab-v1/midi_ab_review.html`.
  Its seed, answer-key and page SHA-256 values are respectively
  `c972b27330a8c4cad34d075b45a2fe8921e5af4f155d1af88a36083bc9a39676`,
  `64bb90d9be78bb7ffe6cacb44ad28c78864f485cc5092c206564d9c1b5452762`
  and
  `c46cee4d459e87b7e39537524774f438c4c8c2b951eb261e2996cedca6480e79`.
  The answer key remained separate until the reviewed export was resolved on
  25 July; see the newer daily entry above for the final 1/0/2 result and
  honest non-promotion decision.

### 2026-07-23 — Phase 6.3e bounded existing-note end/duration correction

- Goal: let a listener shorten or lengthen an exact existing pitched note or
  drum hit without moving its Note On or changing pitch, expression or count.
- Contract: `note_end_shift_patch` retains `shift_note_ends`; one request names
  1–64 unique exact existing refs and integer `target_end_tick` values. Every
  target differs by a non-zero delta within ±480 ticks, leaves at least one
  tick of duration and keeps source and target full intervals in the window.
- Timing: musical mode changes duration beats by `delta / 480` and derives
  source end through the tempo map. Stem-locked mode requires zero microtiming,
  changes source end at the export BPM and derives duration beats. The Note On
  stays exact and both modes round-trip to the requested Note Off tick.
- Safety: the same four onset row block reasons apply. The next same-pitch
  onset, normalized-lifetime cascade, window/MIDI bounds and global
  beat/export/source horizons fail closed. Apply, Review and Create remain
  explicit, and Sunofriend makes no musical-quality or preference inference.
  Browser restart summaries also fail closed against malformed child, lineage,
  timing, diff or effect evidence.
- Capability and effects: v2 keeps generic `timing: false` and adds
  `maximum_note_end_delta_ticks: 480` plus
  `minimum_note_duration_ticks: 1`. Preview is all false; fresh creation may
  set only library/child/correction/duration/timing; replay/restart are false.
- Evidence: ignored smoke
  `work/ai-bakeoff/lidl-phase6-duration-smoke-v1` has report SHA-256
  `d0141814026c434c4702a9c7dcd00466fd6502921bb5e0fa1b437657d675bb77`.
  The source remained at 12 Clips, the copied parent stayed byte-identical and
  the copy grew from 12 to 13. Parent Keys Clip
  `a6112b69031a233a54531128dca4925f32d5b3b32ce5552daaa6393d0138d8aa`
  (object
  `d37975c915e790e290650cf5b48e316c19318c28bd1a50c3de342e889180356a`)
  produced child
  `sf-correction-067bbbfc65e112ba175da84648f2b74f40b5cb5137eabb5f91ff28f4af9f03f6`
  (object
  `14fee0a6ac7dbc29043199e30041adc93c59eda34fccd8a6a9a15d972846281f`).
  In the 1,727-note Clip, channel-1 pitch 66 changed 442–873→442–903:
  +30 ticks/+31.512625 ms and duration 431→461 ticks. Horizons stayed
  462.6458333333333 beats, 222070 ticks and 233.26695445833332 seconds.
  Parent MIDI was
  `e741334f8dfc1421850618d088b382a5fc051fc1fada4797ac742a1dcd201036`;
  child and repeat were
  `27d5be64a4e992548c6a58139f8a7fb677e3d7f4cefc55ea4e2fc163b74fa918`.
  The focused integrated correction/UI suite passed 133 tests, the real smoke
  passed and the complete repository suite passed 1009 tests with the one
  existing `resampy`/`pkg_resources` deprecation warning. This closes
  deterministic engineering evidence only, without a human preference claim.
- Deferred: note insertion, release velocity, continuous expression,
  split/merge, phrase inference and hybrids. Broader Phase 6 remains in
  progress.

### 2026-07-22 — Phase 6.3d bounded existing-note onset shift

- Goal: let a listener move an existing pitched note or drum hit earlier or
  later without changing its emitted duration, pitch or expression.
- Contract: `note_onset_shift_patch` retains `shift_note_onsets`; one request
  names 1–64 exact existing refs and exact integer targets within ±480 ticks.
  The source and target intervals must both fit the loaded half-open window.
- Timing: Note On and Note Off move by the same delta. Musical timing keeps
  duration beats and microtiming and recomputes source seconds; stem-locked
  timing requires zero microtiming, shifts source seconds at the export BPM and
  derives beat coordinates. Both must round-trip to exact 480-TPQ ticks.
- Safety: no target is inferred, snapped or quantised. Duplicate, normalized-
  lifetime, overlap/cascade, window, MIDI-bound and global-horizon cases fail
  closed. Preview is zero-effect; only the five named onset-child effects may
  be true on a fresh create, and replay/restart are all false.
- Compatibility: capability schema v2 and generic `timing: false` remain
  unchanged; the explicit onset kind and 480-tick limit advertise support.
  Earlier correction schemas, hashes and recipes remain frozen.
- Evidence: the fresh copied Lidl library at
  `work/ai-bakeoff/lidl-phase6-onset-smoke-v1` grew from 12 to 13 Clips while
  the 12-Clip source and copied parent stayed unchanged. Parent Keys Clip
  `a6112b69031a233a54531128dca4925f32d5b3b32ce5552daaa6393d0138d8aa`
  (object
  `d37975c915e790e290650cf5b48e316c19318c28bd1a50c3de342e889180356a`)
  produced child
  `sf-correction-495e77ba31528090cc979465459d50acf9ad8f4e36f8a783e9f30398703d5727`
  (object
  `e70a297a01be3a086f5fa05e8dabb47975e6b634dd1adfc4e8c17565524932a2`).
  Both contain 1,727 notes. One channel-1 pitch-66 interval moved
  442–873→472–903: +30 ticks, +31.512625 ms and an unchanged 431-tick
  duration. Beat/export/source horizons stayed 462.6458333333333 beats,
  222070 ticks and 233.26695445833332 seconds. Fresh creation set exactly the
  five onset-child effects; replay and restart were all false. Parent/child
  MIDI SHA-256 values were
  `e741334f8dfc1421850618d088b382a5fc051fc1fada4797ac742a1dcd201036`
  and
  `20b1298550568bb51cdb98c4d8e342a4ac27e22b2cd58f5e03f48f062cad7d9b`.
  The focused integrated suite passed 101 tests and the adversarial audit
  passed 17 onset-specific plus 82 broader correction/server/UI tests. The
  complete repository suite passed 990 tests in 282.58 seconds with the one
  existing third-party `resampy`/`pkg_resources` deprecation warning. This
  closes 6.3d as deterministic engineering evidence, not a human preference
  or musical-quality claim.
- Deferred at 6.3d: note insertion, note-end/duration, release velocity and
  continuous expression. Increment 6.3e now completes the separately bounded
  note-end/duration contract; the other items remain deferred.

### 2026-07-22 — Phase 6.3c bounded exact note removal complete

- Goal: let a listener remove recognisable unwanted or extra MIDI notes from a
  pitched or drum Clip without asking Sunofriend to classify noise.
- Contract: keep the existing correction gate/routes and one-kind immutable
  child. `note_delete_patch` carries 1–64 unique exact existing references;
  `delete_clip_notes` retains the exact parent and requires at least one note.
- Safety: explicit Mark, Review and Create are distinct. Focus is zero-effect;
  projection writes nothing; fresh creation changes only `library_mutated`,
  `child_clip_created`, `correction_applied`, `note_count_changed` and
  `note_deleted`; replay and restart are zero-effect. There is no draft
  audition, ranking, selection, placement or export.
- Topology: normalized child MIDI must equal normalized parent MIDI minus the
  named intervals. Every survivor plus beat/export/source horizon stays exact;
  duplicate, cascade, horizon and only-note cases are blocked.
- Compatibility at 6.3c: pitch and attack-velocity v1 remained frozen.
  Insertion and onset/duration still awaited separate contracts; 6.3d now
  takes onset alone and the later 6.3e takes note-end/duration. Insertion
  remains deferred.
- Evidence: a fresh copy of the accepted Lidl library at
  `work/ai-bakeoff/lidl-phase6-deletion-smoke-v2` grew from 12 to 13 Clips
  while the source remained at 12.
  Parent Snare
  `0718458e900dbcdf7dff7332c77808054dfaadb6c517d2c22d7b967a28f50826`
  (object
  `65b140afecb84099abbdf9880ee4597d8eeb7c6caf5d470e62213654ee857ae5`)
  lost one channel-9 pitch-38, velocity-46 note at ticks 140487–140573
  (beat 292.68125, duration 0.17916666666667425) in child
  `sf-correction-6914357fcfbca9f597fe09ca8912fda3516554226bbbdab1507295f9b309576c`
  (object
  `622f9e88616f3b9450a126e5b671aae557e1b2ac8e27f9de3103828f61e5f20b`).
  Clip and normalized-MIDI note counts changed 249→248 exactly, while beat,
  export-event and source horizons remained 442.7395833333333 beats, 212515
  ticks and 223.23018339583334 seconds. Replay returned every effect false,
  restart recovered a path-free summary and deterministic child MIDI repeated
  at SHA-256
  `1e3e20d607c62b7b6c06d210b9f3fa90c1f126166aadcf86d82d870d83f5535c`.
- Verification: the focused integrated correction suite passed 81 tests, the
  final independent audit passed 49 and the complete repository suite passed
  970 tests. The single warning is the existing `resampy`/`pkg_resources`
  deprecation notice.
- Decision: Increment 6.3c is complete. Broader Phase 6 remains in progress.
  The later 6.3d contract takes onset shift alone; insertion,
  note-end/duration, release velocity, continuous expression and the other
  deferred operations remain outside 6.3c.

### 2026-07-22 — Phase 6.3b bounded attack velocity

- Goal: let a listener repair an individual note attack or drum-hit intensity
  without treating source amplitude as truth or changing the published pitch
  correction contract.
- Contract: the existing correction gate and routes accept exactly one sealed
  kind per draft/child. Velocity targets are exact integers 1–127 on 1–64
  unique note references; pitch-v1 requests, serializers, hashes and recipes
  remain frozen by literal compatibility tests.
- Meaning: velocity is Note On intensity, not dB, track volume, release
  velocity, CC7/CC11 expression or guaranteed perceived loudness. A patch can
  use it for loudness, brightness, attack or sample-layer selection.
- Safety: pitched and drum Clips are eligible, but exact or quantised duplicate
  exported channel/onset/pitch events are visible and blocked. Preview writes
  nothing; create appends one immutable child; replay and restart retain exact
  evidence without audition, selection, placement, ranking or feedback.
- Browser evidence: kind-specific schemas, request/window/library pins, the
  exact one-to-one server diff, deterministic child and complete effect map
  must agree before review/create claims are shown. Missing rows are never
  synthesized, and applying an unchanged value preserves an existing review.
- Preserved: pitch, timing, duration, source seconds, microtiming, release
  velocity, articulation, key/chords, instrument, provenance, parent and all
  project/reuse/pack state.
- Evidence: a copied accepted Lidl library grew from 12 to 13 Clips after one
  channel-9 Snare Note On changed from velocity 101 to 89. Source and parent
  bytes stayed exact, normalized MIDI changed only that event, replay was
  zero-effect, restart recovered the −12 diff and deterministic MIDI repeated
  at SHA-256
  `f8570c9af8636e3cfeb1605082616a3e1e72f0bdd546b764baf055bca9abbc4c`.
- Verification: the complete repository suite passed with 955 tests; the one
  warning is the existing `resampy`/`pkg_resources` deprecation notice.
- Deferred at the 6.3b boundary: insertion, onset/duration, release velocity,
  continuous expression, quantisation, phrase replacement and hybrids. The
  later 6.3d contract takes onset alone; the other items remain deferred.

### 2026-07-22 — Phase 6.3a bounded pitch correction complete

- Goal: let a listener fix recognizable wrong pitches or octaves without
  turning the multi-process explorer into an automatic theory repairer.
- Contract: a half-open integer 480-TPQ window, at most 32 beats/15 seconds,
  512 visible and 256 editable notes, with 1–64 unique exact note references
  and a maximum ±24-semitone change.
- Identity: each reference binds parent object, canonical note index and the
  complete `ClipNote` payload, so stale state and identical duplicates are
  handled without a Clip schema migration.
- Safety: preview is zero-write; explicit creation appends one deterministic
  child through the existing sole-child CAS; replay is zero-effect; ambiguous
  newly introduced same-pitch export intervals are rejected.
- Exportability: notes/chords/tempo events, tempo encoding, time-signature
  bytes and text meta payloads are checked against the deterministic SMF
  writer, including the exact four-byte variable-length tick boundary.
- Preserved: timing/source seconds, expression, key/chords, instrument,
  provenance, unaffected notes, parent, decisions, arrangement, reuse plan,
  pack, feedback and submission.
- Deferred at 6.3a: add/delete, timing, duration, attack/release velocity,
  split/merge, quantisation,
  hum/F0 guidance, repetition propagation, automatic theory repair and
  hybrids.
- Evidence: a copied accepted Lidl library grew from 12 to 13 Clips after one
  explicit 59-to-61 keys edit. The source library and parent stayed unchanged;
  exact replay was zero-effect; restart retained the one-note diff; public
  correction outputs were path-free; and deterministic MIDI repeated at
  SHA-256 `ce1edbc85f44b5c37cdb0576c89ef5cd2eee74afe7c9ee6f904ca248f866d4a8`.
- Verification: the complete repository suite passed with 943 tests, including
  adversarial restart recipes, exact SMF limits, loopback/browser contracts and
  concurrent lazy reuse-store publication.
- Decision: Increment 6.3a is complete. The next note-editing operation remains
  separately gated rather than expanding this pitch-only contract implicitly.

### 2026-07-22 — Phase 6.2a reviewed immutable transforms complete

- Goal: expose the existing key/BPM musical operations without mutating a
  source Clip, silently selecting an alternative or weakening the accepted
  Phase 6 evidence gate.
- Change: added a separate `--enable-clip-transforms` launch, exact zero-write
  projection, one-operation immutable child creation, same-mode key direction,
  explicit musical/stem-locked BPM meaning and full parent/child/library audit
  evidence in the local Workbench.
- Atomicity: the existing-only writer checks the complete catalog state under
  `BEGIN IMMEDIATE`, validates every old row and the sole expected child before
  commit, cleans a published orphan while retaining the writer lock after
  rollback and rejects new work at the 10,000-Clip bound. Adversarial trigger,
  concurrent cleanup and capacity tests confirm rollback safety.
- Concurrency: identical requests from two already-open servers resolve as one
  fresh create plus one zero-effect idempotent replay; different transforms
  resolve as one create plus one fixed conflict. Unrelated external additions
  remain fail-closed.
- Real acceptance: a copied accepted Lidl library grew from 10 to exactly 12
  Clips. Its 171-note B-major bass at `118.99992463338107` BPM produced a
  musical-timing 125 BPM child and then a +1-semitone C-major child. Restart
  recovered the three-version lineage; the source library and all ten original
  rows/objects remained unchanged; public responses were path-free.
- Reconstruction: the final 125 BPM C-major child rebuilt MIDI twice at
  SHA-256 `42eabbb41cd484d104d67080833710bb240b0d73d817e8af93aa95217b35b502`;
  the second request was a verified content-addressed cache hit.
- Verification: the full project suite passed with `910 passed, 1 warning`;
  the warning is the existing `resampy`/`pkg_resources` deprecation notice.
- Status: Increment 6.2a is complete. The next bounded Phase 6 work is explicit
  phrase/note correction; mode remapping, tuning/downbeat and hybrids remain
  separately gated.

### 2026-07-22 — Phase 6.1 explicit Clip reuse proposal complete

- Goal: make one chosen library part reusable without silently constructing a
  song, changing the Clip or coupling the action to Phase 5 decisions.
- Change: added an explicit fourth launch flag, sibling Browse/Proposal views,
  immutable Clip/object pinning, whole-beat place/remove actions, compatibility
  facts and optimistic plan revision/hash checks.
- State: the append-only owner-only proposal database lives at
  `STATE_DIR/phase6-reuse/reuse.sqlite3` and is created only by the first
  explicit action. Exact evidence binding controls restart restoration.
- Bounds: 64 active placements, 512 events, 20,000 notes per Clip, 40,000
  active note instances and a 20-minute nominal plan end.
- Effects: no Clip/library, MIDI, transform, current-arrangement, decision,
  pack, render/play/export, instrument, feedback or submission effect.
- Verification: the real accepted Lidl project placed an exact immutable bass
  Clip at bar 3, beat 2; revision 1 restored after restart; explicit removal
  produced revision 2; and the empty active proposal restored after a second
  restart while both append-only events remained. Owner-only modes, path-free
  Inspector state, compatibility warnings and byte-identical decision,
  library-object and accepted-pack inputs were confirmed.
- Status: focused and full tests passed. Increment 6.1 is complete; broader
  Phase 6 remains in progress.

### 2026-07-22 — Phase 5.9 accepted; Phase 6 read-only Clip entry complete

- Acceptance: the path-free resolver result is `passed`. All eight technical
  tutorial screens were completed, the quiz scored 10/10 and both named
  six-item human checks passed without an issue or `cannot_tell` answer.
- Pack evidence: the exact accepted ZIP contained five selected MIDI payloads,
  the dry arrangement proxy and no source audio. Schema, receipt, member set,
  payload sizes and hashes were verified, and original selected MIDI remained
  declared unchanged.
- Timing/privacy: the listened downbeat is
  `reviewer-observation-only`; it did not become catalog timing evidence.
  Private note text remains outside the path-free result and these docs.
- Effects: MIDI, candidates, decisions, basket, defaults, feedback, submission
  and automatic phase-start effects are all false.
- Phase boundary: `phase6_read_only_clip_entry_ready` is true and the first
  gated Clip Library increment is complete. All three launch inputs are
  required. Hybrid construction remains false behind the Phase 5.3 gates, and
  broader Phase 6 remains in progress.
- First increment: browse/search, path-free detail/lineage, dry neutral
  audition and deterministic Clip reconstruction only. No transforms, writes,
  piano roll, placement or hybrids; reconstruction is not an original-MIDI
  byte copy.
- Completion evidence: a real read-only library exposed 73 Clips across 51
  lineages; browser checks verified browse/detail, deterministic MIDI, dry
  FluidSynth proxy rendering, a repeat cache hit, path-free byte-range serving
  and Developer Inspector tracing with zero musical/library mutations.

### 2026-07-21 — Phase 5.9 guided exact-pack learning and acceptance

- Goal: ensure the user understands Sunofriend before completing the final two
  Phase 5 local acceptance checks.
- Learning flow: added eight interactive tutorial screens followed by exactly
  10 one-at-a-time comprehension questions. Nothing starts selected; checked
  answers explain the concept, the whole quiz can be retried and 10/10 is
  required before the human checks unlock.
- Human evidence: GarageBand acceptance now covers exact BPM, authoritative
  selected MIDI import/editability, playable patches, drum routing where
  applicable, listened downbeat and beginning/middle/end drift. Local usability
  explicitly confirms an authorised project plus comparison, no-automatic-
  winner understanding, arrangement audition, state separation, export and
  restart.
- Integrity: the resolver independently verifies the downloaded ZIP's strict
  v1 receipt, canonical names, basket identities, member set and streamed
  hashes, rebuilds the neutral seed and recomputes quiz/check outcomes. Cached
  ZIP, seed and HTML substitution fail closed and rebuild from current
  catalogued bytes.
- Privacy/security: the served page is frozen under the no-connect review CSP
  and sandbox. It has no POST, fetch, upload, telemetry or event action.
  Private note text stays in the reviewed export and is omitted from the
  path-free result.
- Effects: tutorial, quiz, checks and resolution change no MIDI, candidate,
  selection, basket, rank, default or contribution state and do not start
  Phase 6 automatically.
- Decision: Phase 5.9 tooling is ready; human evidence remains pending. A
  resolver `passed` result opens the read-only Phase 6 Clip Library entry gate.
  Hybrid construction remains separately gated by Phase 5.3 blind-choice and
  source-lineage work.

### 2026-07-21 — Phase 5.8 verified execution provenance

- Goal: close the remaining purely engineering local-Studio trust gate before
  the first Phase 6 Clip Library slice.
- Change: Workbench now projects one path-free execution state for a fresh
  subprocess, exact-result cache miss, verified cache hit, first bounded-session
  request or genuinely reused-model warm request. Every state says that it is
  execution provenance rather than musical agreement and that Workbench did
  not enable an optimisation.
- Integrity: bounded-session candidates are checked through the complete
  closed-session verifier, including parent/run membership and hashes, one
  model load, exact request template, sequence, worker response, performance
  evidence and output identity. Changed or missing evidence fails closed.
- Packaging: a fresh wheel is installed into an isolated target and its HTML,
  transport JavaScript and visualization JavaScript are loaded through the
  production resource functions; CLI `workbench --inspect` starts no server.
- Effects: no model, worker, session or application-cache action is started;
  no selection, rank, MIDI, pack basket or contribution field changes.
- Decision: the technical Phase 6 entry gate is complete. One GarageBand pack
  acceptance pass and one small authorised local usability pass remain before
  the first read-only Clip Library increment. Hybrid construction still waits
  for the Phase 5.3 blind-choice and source-lineage gates.

### 2026-07-20 — Phase 5.7 long-song recovery and exact chunk transport

- Goal: keep multi-process evidence understandable across a long song and add
  the smallest precise full-song path without turning Workbench into a DAW.
- Visualization: extracted fixed-window projection/culling helpers; added
  Fit/4×/16×, earlier/later and playhead-centred navigation, bounded canvas
  geometry, stale-fetch guards, compatible-last-result Retry and canvas-context
  recovery. Painting is culled, but the full server-bounded timeline JSON is
  still downloaded, parsed and indexed. There is no silent coarse projection.
- Playback: added immutable server-owned stream/chunk contracts for source-only,
  selected-MIDI, hybrid and main-only. Exact integer anchor-frame boundaries,
  deterministic ties-even rate conversion, disclosed silence padding and one
  Web Audio clock preserve the recorded-zero contract. Only current plus next
  chunks are decoded.
- Failure behavior: a not-ready required chunk stops at the last verified
  boundary. Late completion enables explicit Play; absent or failed data
  requires Retry. Neither auto-restarts; seek pauses while its chunk is
  prepared. The coarse full-song/custom mixer is never started
  silently and remains the only arbitrary mute/solo/gain path.
- Bounds: 24 tracks, 20-minute longest source, 2 GiB verified input,
  mono/stereo 8–96 kHz audio, adaptive chunks no longer than five seconds,
  480 chunks, 32 MiB PCM16 output per chunk, 192 MiB projected two-chunk memory,
  16 active stream plans and 768 generated-media capabilities per launch.
  Chunks share the rebuildable 32-entry/256 MiB precise-audio cache.
- Snapshot/cache verification: immutable full-song inputs use a separate
  owner-only eight-stream/2 GiB disk LRU, retaining the current stream even when
  oversized. Prepare/reprepare fully verifies hashes; an eight-stream
  process-local cache uses file identity/stat signatures for unchanged later
  chunks. Drift falls back to full verification and altered evidence fails
  closed.
- Recovery: reload restores URL-hash view/stem plus durable decisions, Overview
  state and pack basket. Prepared audio/chunks, playhead, loop,
  viewport/zoom/visibility and mixer controls reset.
- Decision: retain three explicit arrangement paths—Phase 5.6 precise short
  loop, Phase 5.7 precise canonical full-song preset and coarse arbitrary
  full-song/custom mixer. Defer precise arbitrary custom mixes and
  server-paginated timeline payloads.

### 2026-07-20 — Phase 5.6 bounded decoded arrangement presets

- Goal: make short whole-arrangement comparisons precise without decoding an
  entire song or turning Sunofriend into a DAW.
- Change or experiment: added a canonical path-free arrangement-selection
  manifest and a private 0.5–15 second decoded artifact. Byte-identical source
  stems share one lane; every active main/optional MIDI remains distinct. The
  server defines source-only, selected-MIDI, hybrid and main-only groups, and
  the browser can submit only the manifest hash and time bounds.
- Timing/integrity: a separate group transport starts all incoming nodes and
  retires all outgoing nodes at one Web Audio time. Invalid or partially failed
  switches leave the previous group intact. Current state is checked before
  rendering and again before media registration; a concurrent choice returns
    409. Current path-free roles, SoundFont and neutral-render policy are pinned,
         and owner-only snapshots are removed before publication.
- Bounds/effects: at most 24 total tracks, 2 GiB verified input and 64 MiB PCM16
  output; stem and arrangement windows share the 32-entry/256 MiB rebuildable
  cache. Preparation and playback append no event, feedback or ranking and
  mutate no MIDI, source or selection.
- Listening boundary: all tracks start at recorded zero. Unity-gain groups are
  not level matched or limited, so a dense hybrid can clip. The existing
  full-song mute/solo/gain mixer remains explicitly coarse; the standalone
  blind A/B remains the promotion gate.
- Evidence: artifact, server, stale-render, private-media, UI cancellation and
  atomic JavaScript transport tests pass on portable fixtures.
- Decision at completion of 5.6: retain bounded canonical presets as the
  precise short arrangement path. Phase 5.7 subsequently implemented long-song
  visual recovery and canonical chunk streaming; precise arbitrary custom
  mixes, level matching and persistent audition state remain deferred.
- Next step completed by 5.7: harden long-song visualization/recovery and add
  the smallest chunked full-song transport without losing immutable
  multi-process provenance.

### 2026-07-20 — Phase 5.5 Decoded Stem Comparison v1

- Goal: make short source-versus-MIDI changes precise enough to judge several
  analytical and AI candidates without turning playback activity into a vote.
- Change or experiment: added a bounded decoded-loop artifact/API, a packaged
  one-clock Web Audio transport and a per-stem **Precise short-loop
  comparison** panel. A request covers 0.5–15 seconds, includes primary
  candidates by default, requires explicit opt-in for advanced candidates and
  is capped at six MIDI candidates.
- Integrity and privacy: the builder verifies source, MIDI and neutral-preview
  hashes, renders a missing neutral proxy without rewriting MIDI, crops private
  content-addressed PCM clips and exposes path-free metadata. Every included
  preview must use the current SoundFont hash and neutral-renderer policy or the
  request fails closed. Renderer MIDI/SoundFont and decoder source/preview
  inputs are copied through single open handles into owner-only hash-and-size-
  verified snapshots; work uses only those bytes and deletes the snapshots
  before publication. This closes the verified-path replace/restore race.
  Generated media is verified and frozen before serving.
- Timing/effects: decoded buffers share one browser clock and equal frame
  extent; source/candidate switches use a common scheduled time and retain one
  absolute loop playhead. Every artifact starts at recorded zero and no
  alignment offset is inferred. Prepare, play, switch, seek, pause and stop have
  zero selection, review-event, ranking and MIDI-mutation effects.
- Evidence: focused artifact, API, transport and static-UI tests cover bounds,
  hash/corruption handling, private cache permissions, range serving, frame
  normalisation, same-renderer enforcement, verified input snapshots,
  replace/restore resistance, scheduled switching, invalidation, silence-
  padding disclosure and the zero-event UI contract. Each request is capped at
  2 GiB across source, candidate MIDI, SoundFont and preview input, rejecting
  oversized declared inputs before rendering, and 64 MiB of generated output;
  the rebuildable cache retains
  at most 32 recent windows or 256 MiB and evicts older entries.
- Decision: retain this as the normal precise per-stem comparison. Keep the
  explicitly labelled second-synchronised compatibility fallback for browser
  recovery; its controls also record no feedback or event. Retain the
  standalone blinded, level-matched `midi-ab-review` package as the stricter
  promotion gate. When a source or preview ends early, expose its generated
  end-silence duration in a persistent warning and tell the listener not to
  interpret it as missing transcription.
- Problems/risks: the later bounded selected-arrangement path now has one-clock
  canonical presets, but source and neutral MIDI remain unlevelled; full-song
  custom playback still needs chunked decoded transport and visualization
  hardening.
- Next smallest step: retain this per-stem contract while extending the same
  safety invariants to bounded arrangement groups.

### 2026-07-20 — Phase 5.5 decision safety, path-free roles and restart proof

- Goal: make saved review outcomes unambiguous at export time and prove that a
  real restart restores durable state without restoring temporary audition
  controls or causing GET-side effects.
- Change or experiment: defined `none_usable` and `cannot_tell` as deterministic
  no-selection barriers in event replay and every selection consumer. Earlier
  events remain auditable but inactive; a later main/optional decision clears
  the barrier and activates only that candidate. Added one shared role-privacy
  boundary for new-event/catalog validation and legacy browser, contribution,
  timeline, pack, ZIP-name and proxy-MIDI projections. Empty Pack Composer now
  explains that no MIDI is ready and returns to Project Overview.
- Evidence: focused store/home/UI/privacy/timeline/pack tests include malformed
  legacy state, relative/POSIX/home/Windows/UNC role forms, pack manifests and
  generated MIDI track metadata. A two-server loopback integration test saves
  decisions plus a non-default basket, stops the first server, starts a second
  with a new token and verifies restoration with no GET mutation.
- Private integrity boundary: the planned Slayyyter usability fixture failed
  closed because an adjacent completed AI run's worker hash had changed. No
  provenance check was relaxed; portable fixtures supplied the restart proof.
- Decision: retain append-only history but make active export eligibility
  explicit. Keep raw private review exports unchanged; reject path-like roles
  on new writes and redact only legacy browser/public/handoff projections.
- Problems/risks: media-element playback is still shared-second rather than
  decoded/sample-accurate; direct browser controls can bypass the common seek;
  long-song virtualization, keyboard/save affordances and a controlled
  audition-family choice for free-form roles remain open.
- Next smallest step: implement the first decoded playback/synchronisation
  increment without changing the multi-process evidence or explicit-choice
  contract.

### 2026-07-20 — Phase 5.5 Project Overview/Resume v1

- Goal: let a non-expert reopen a local project, understand its truthful state
  and continue with one useful action without reading model names or JSON.
- Change or experiment: added the path-free
  `sunofriend.workbench-home.v1` server projection, a default project home with
  per-stem statuses and one deterministic next state/action, view-specific focus,
  retryable connection/pack-status failures and lazy advanced-candidate audio.
- Safety contract: counts and routing use only the catalog and explicit SQLite
  state. Navigation, reload and retry do not rank/select MIDI, append feedback,
  alter audio, run AI or change the pack. Private paths, notes, process labels
  and quality metrics are absent from the home projection; path-like free-form
  role text is represented as a redacted custom role.
- Restart boundary: saved musical decisions and the separate pack basket are
  restored; playhead, loop, visibility, mute, solo and level intentionally
  reset and remain outside review history and export selection.
- Evidence: focused projection/UI/API tests, the full Workbench suite and a
  real loopback-browser smoke test against the private Lidl catalog. The smoke
  test confirmed that **Compare this stem** opens the intended stem and focuses
  **2. Choose a MIDI part**.
- Decision: retain Project Overview as the default Phase 5.5 resume surface;
  keep it an explainable router over multi-process results, not a dashboard
  that chooses a process.
- Problems/risks: decoded Web Audio switching, long-song visual
  virtualization, broader keyboard/save focus, canonical custom mixes and
  repeated GarageBand beta verification remain open.
- Next smallest step: harden comparison playback and long-project interaction
  without weakening explicit-choice or byte-identity boundaries.

### 2026-07-20 — Phase 5.4 disputed-range phrase-review bridge

- Goal: turn the existing S0/M1/M3 disagreement ranges into understandable
  listening shortcuts without claiming that disagreement proves accuracy.
- Change or experiment: added an explicit-catalog, path-free
  `sunofriend.workbench-phrase-review-link.v1` projection; range cards below
  the role timeline; temporary loop shortcuts; and links to the exact existing
  phrase-review anchors.
- Safety contract: report, source, manifest, S0/M1/M3 candidate, geometry,
  diagnostic-count and served-file hashes fail closed. No report is discovered
  automatically. The link does not run AI, mutate MIDI, choose/promote a
  candidate, append feedback or enter a GarageBand pack.
- Privacy and serving: the private page gets a random per-launch loopback
  capability. Only its pinned HTML and referenced source/MIDI/overlay WAVs are
  served, each rehashed; manifest, correction seed, MIDI, evaluation JSON and
  arbitrary siblings remain inaccessible. Browser policy blocks connection
  APIs, forms, autoplay, popups and top-level navigation while preserving the
  existing reviewed-JSON download and alert dialogs.
- Evidence: portable validator, path-escape/tamper, catalog, capability,
  byte-range, drift, UI and zero-state-effect tests, plus the authorised Lidl
  15-second vocal golden with three ranked review units.
- Decision: Phase 5.4's read-only Result Explorer vertical slice is complete.
- Problems/risks: the destination phrase page compares its own Basic
  Pitch/GAME-boundary/combined alternatives, plus guide-assisted only when
  present, not S0/M1/M3 directly; the UI states that boundary. Long-song
  rendering and browser recovery were then open and are implemented in Phase
  5.7.
- Next smallest step: begin local Studio hardening with one private end-to-end
  usability pass and address the first observed friction rather than adding a
  new model.

### 2026-07-20 — Phase 5.4 GarageBand Pack Composer v1

- Goal: make GarageBand ZIP contents visible and intentional without turning
  export choices into musical feedback or changing the selected MIDI bytes.
- Change or experiment: added versioned path-free plan, basket and pack
  contracts; a dedicated append-only basket store; authenticated local
  plan/save/build routes; and a Workbench composer grouped into selected MIDI,
  dry arrangement proxy and source-audio sections.
- Safety contract: only current explicit main/optional MIDI is eligible. MIDI
  and the proxy default on; sources default off and require a separate opt-in.
  Rejected, needs-correction, unreviewed and superseded candidates are absent.
  Playback, visibility, mute, solo and gain do not affect inclusion or review
  history. The legacy exact-MIDI handoff remains unchanged.
- Evidence and metrics: plan, basket and selection-scope hashes reject stale
  saves/builds; optimistic revisions prevent concurrent lost updates; exact
  input bytes are hash-verified before deterministic ZIP construction; source
  audio is deduplicated by content without deduplicating selected MIDI.
  Artifact, store, HTTP and UI tests cover safe defaults, source opt-in,
  isolation, stale conflicts, drift and compatibility.
- Listening result: no listening verdict is claimed by the composer. It
  packages only explicit eligible artifacts after musical review.
- Decision: retain Pack Composer v1 as the supported explicit export path and
  retain the original handoff as the smallest compatibility path.
- Problems/risks: alternative MIDI, Instrument Bundles, custom rendered mixes
  and long-song/browser hardening still need their own contracts.
- Next smallest step: the disputed-range bridge recorded above completed the
  remaining Phase 5.4 slice; begin Phase 5.5 local Studio usability hardening.

### 2026-07-20 — Phase 5.4 selected-arrangement explorer

- Goal: turn explicit per-role choices into one understandable full-song view
  without collapsing the underlying analytical and AI alternatives into a
  winner or turning mixer activity into feedback.
- Change or experiment: added the path-free
  `sunofriend.workbench-arrangement-timeline.v1` projection, derived only from
  server-side current main/optional choices. The page now draws every unique
  source waveform and each selected MIDI lane, keeps Candidate A/B/C identity,
  supplied the initial fit/2×/4× navigation (replaced by Phase 5.7's bounded
  Fit/4×/16× viewport) and added temporary source-only, selected-MIDI, hybrid
  and main-MIDI auditions with show, mute, solo and attenuation.
- Safety contract: byte-identical sources may share one disclosed lane;
  selected MIDI is never deduplicated. Hashes are rechecked, the selection hash
  ignores review-context-only reconfirmation, and aggregate visual limits are
  24 sources, 24 MIDI lanes and 40,000 rendered notes. Mixer state is browser
  memory only and does not enter SQLite, arrangement caches, overlap evidence
  or GarageBand handoff bytes.
- Inputs and evidence: synthetic path/hash/filter/cap tests plus the authorised
  private 15-second Lidl Workbench state. That project displayed three source
  lanes and five selected MIDI lanes. Source-only, selected-MIDI and hybrid
  presets, manual attenuation/visibility, shared seeking, a 2.0–2.5 second
  loop and 2× zoom worked in the browser; the append-only event count remained
  31 before and after audition controls.
- Listening boundary: missing MIDI sound is prepared explicitly through the
  neutral renderer. Source and MIDI levels are not normalised, and independent
  browser media elements share seconds rather than samples, so the hybrid is a
  creative audition, not comparison evidence. The prepared dry proxy remains
  the reproducible control.
- Decision: retain this as a second linked Result Explorer view. Only the
  separate **Save after listening** actions append `full_mix` decisions.
- Problems/risks: large projects need later virtualization/Web Audio hardening;
  custom mixer state is intentionally not persisted or rendered.
- Next smallest step: build the explicit GarageBand pack composer while
  retaining the current source-audio-free exact-MIDI ZIP as the safe default.

### 2026-07-20 — Phase 5 Result Explorer direction

- Goal: make Sunofriend's existing result space approachable without reducing
  it to one model output or attempting to copy Mirelo Studio.
- Change or experiment: reframed Phase 5.4 as an Interactive Result Explorer
  and GarageBand Pack Composer, Phase 5.5–5.7 as staged local Studio hardening,
  Phase 6 as creative arrangement/reuse and Phase 7 as cross-DAW and
  opt-in community learning.
- Inputs: the existing 5.0 Workbench contracts, the completed analytical/AI
  comparison evidence and the user's review of visual audio-to-MIDI workflows.
- Model/runtime/checkpoint: none; this is a product and architecture decision.
- Evidence and metrics: current Workbench already has hash-pinned discovery,
  at most three primary candidates, synchronized per-stem playback,
  append-only decisions, arrangement audition and exact selected-MIDI handoff.
  Its first new visual slice adds a canonical, path-free per-stem timeline with
  a bounded PCM waveform, per-track MIDI note geometry, primary-only default
  loading, explicit advanced-lane loading and zero mutation/ranking effects.
  The full-song arrangement timeline, arbitrary mixer and pack basket do not
  yet exist.
- Listening result: the approachable presentation is useful, while
  Sunofriend's main value remains comparison of several analytical and AI
  methods with explicit role-specific human choices.
- Decision: evolve the current Workbench; preserve every candidate and its
  provenance; introduce no automatic winner; keep source audio local and keep
  public contribution out of Phase 5.4/5.5.
- Problems/risks: showing every alternative at once could confuse alternatives
  with intentional layers; musical selection and ZIP inclusion must remain
  separate; the interface must not imply sample-accurate switching before it
  exists.
- Real-project check: the explorer loaded the private Lidl source waveform and
  three distinct MIDI lanes, shared seeking worked by mouse and keyboard,
  advanced lanes stayed lazy and mobile overflow remained inside the timeline
  panel. Display changes did not alter the saved review count or selection.
- Next smallest step: reuse the stable contract for a read-only
  selected-arrangement timeline without changing current decisions or handoff
  bytes.

### 2026-07-20 — Phase 5.3 vocal phrase-disagreement evidence

- Goal: locate the most useful S0 specialist, M1 full-mix-label and M3
  conditioned-stem disagreements before attempting another automatic
  consensus or producing a hybrid MIDI.
- Change or experiment: added a shared deterministic, one-to-one note-onset
  alignment primitive and migrated the matrix, setting comparator and
  Workbench overlap counters to it while retaining the legacy nearest-unused
  policy for existing v1 matrix/setting metrics. Added the lead-only
  `hybrid-report`, which strictly verifies an exact source WAV, matching melody
  phrase review, distinct S0/M1/M3 MIDI and their three provenance schemas.
  It validates M1 label/render bookkeeping and M3 projection/media/mutation
  claims, recomputes phrase segmentation and repetition geometry, requires S0
  provenance to resolve to the supplied WAV, rechecks every input after
  analysis, and projects only schema-owned, path-free phrase evidence. It
  reports per-note raw source support and
  per-phrase exact, cross-boundary, boundary/duration, octave, lane-only and
  duplicate evidence; each cross-boundary endpoint is represented in every
  phrase or review-unit gap it touches. Chords remain unavailable/unpinned.
- Inputs: private 15-second Lidl vocal excerpt at 119 BPM, source SHA-256
  `a52b874719af8468e087ba62dec628cca142e6c649f79a718bbe9f880475a488`;
  the existing three-unit lead phrase review; S0 repaired specialist MIDI,
  M1 `soprano_and_alto_sax` label partition and projected M3 vocal MIDI.
- Model/runtime/checkpoint: no inference, worker or checkpoint access. The
  command reads completed artifacts and uses the normal local audio runtime
  only for `StemSpectrum` evidence.
- Evidence and metrics: S0/M1/M3 contain 23/38/39 notes. Within 80 ms,
  S0↔M1 matched 6 exact-pitch onsets, S0↔M3 matched 8 and M1↔M3 matched 28.
  Their same-pitch boundary/duration dispute counts were 4/6/6; this clip had
  no octave-equivalent onset disputes. S0↔M3 had one exact match crossing a
  phrase boundary; the other pairs had none. Phrase IDs 0, 1 and 2 ranked at
  47, 36 and 36 disagreement references respectively. Two fresh report writes
  were byte-identical at SHA-256
  `8e476e89d17cfed50a8c4d7f15557e8d0997c734210a56091fe9596b9b3ba995`.
  Existing beam and batch comparator goldens remained byte-identical after the
  shared-alignment migration.
- Listening result: not yet applicable. The report ranks disagreement evidence,
  not musical preference, and creates no audition or MIDI.
- Decision and effects: retain all three raw candidates. Agreement is not
  accuracy, raw spectrum support is not selection and octave equivalence is a
  dispute. The report records zero inference runs, MIDI creation/mutation,
  automatic selection, promotion and default changes.
- Problems/risks: dense vocal syllables and harmonics can inflate both source
  support and pairwise agreement. M1 is a model label rather than a confirmed
  physical instrument. Its pinned full mix is caller-associated with this song
  but has no supplied reproducible derivation manifest; M3's original
  pre-projection MIDI is named by its manifest but was not supplied for payload
  checking. The exact excerpt also has no hash-pinned chord timeline.
- Next smallest step: turn the highest-ranked disagreements into a blind,
  recognition-first phrase review. Build an H1 challenger only from explicit
  reviewed choices, then compare it with the current M3 control.

### 2026-07-20 — Strict batch-size 1 versus 2 comparison

- Goal: test whether limited MuScriptor batching improves useful local CPU
  throughput while changing only batch size and preserving musical output.
- Change or experiment: extended `ai-setting-compare` with
  `--setting batch-size`. It requires at least two repeatable current,
  cache-disabled fresh-process runs per arm, batch size 1→2, beam fixed at
  1/greedy, sampling disabled, non-overlapping execution windows and equality
  of every other request, source, runtime and execution field. The existing
  `--setting beam-size` contract remains available and is still the default.
- Chunk/progress contract: both arms retain independent fixed five-second
  chunks. MuScriptor's first positive progress event represents one completed
  chunk at batch 1 and two completed chunks at batch 2, so the comparator
  records those counts and excludes `time_to_first_completed_chunk` from its
  direct performance fields rather than comparing unlike milestones. Fixed
  five-second chunks are not a supported variable in this comparison.
- Inputs and repeatability: two fresh CPU repetitions per arm on the same
  15-second, three-chunk Lidl golden. Both arms were exact. Batch 1 and batch 2
  each produced 107 notes; canonical note payload, base MIDI, expression MIDI
  and every auditionable MIDI were identical. Greedy one-to-one overlap was
  107/107. Candidate JSON and raw JSON differed only in execution/progress
  provenance. The ignored private report is
  `work/ai-bakeoff/lidl-phase5-batch-compare-v1/batch1-vs-batch2-v1.json`,
  SHA-256
  `ef221cf6908ecf49f08c69286e4eaf0808f589daf35d869b34c84267a8639483`.
- Observed performance: batch-2 median pipeline was `8.792904 s` versus
  `5.282282 s` for batch 1 (`1.664603×`); inclusive transcription was
  `7.058380 s` versus `3.824411 s` (`1.845612×`); peak RSS was
  `1,566,097,408` versus `1,173,610,496` bytes (`1.334427×`). Run order was
  not randomized and the operating-system file cache was uncontrolled, so
  these are bounded observations rather than causal speed claims.
- Device boundary: MPS is unavailable in the installed runtime. This
  experiment therefore remains CPU-only and makes no wider device claim.
- Decision and effects: no listening review is required because all
  auditionable MIDI is identical. The comparator reports zero raw or MIDI
  mutations, selection changes and promotions. Batch 2 was slower and used
  more memory in these ordered runs, so batch 1 remains the default.
- Next smallest step: keep fixed five-second chunks and batch 1 while moving to
  the next separately bounded Phase 5 question; do not infer a result for
  another device, model size or source.

### 2026-07-19 — Phase 5.2 blind source-aligned MIDI review tooling

- Goal: make the outstanding beam-1/beam-2 musical decision possible without
  revealing candidate identity or letting louder playback become a hidden
  preference.
- Change or experiment: added generic `midi-ab-review` and
  `midi-ab-resolve`. The builder accepts a reference WAV, two unchanged MIDI
  files, a BPM, required `--midi-time-at-source-start SECONDS` and repeated
  `--interval START END "FOCUS"` values. The explicit common MIDI origin must
  land on a source sample frame; `0` is valid when the WAV and both MIDIs share
  their excerpt origin. No alignment offset is inferred. Each interval is an
  exact source-time, non-overlapping 0.5–15 second window inside the WAV. The
  builder renders private neutral proxies through the same hash-pinned dry
  FluidSynth executable, SF2, zero-based GM program, sample rate and gain, then
  crops source/A/B at the corresponding exact rounded frame indices.
- Level and blind contract: only the louder candidate is attenuated to the
  quieter candidate's fixed-window sample RMS. The source reference remains
  unlevelled; no candidate is amplified and no limiter, compression, EQ, time
  shift or stretch is applied. Each candidate window must be at least -60 dBFS
  RMS. This is sample RMS, not LUFS, true peak or perceived loudness. A secret
  random nonce assigns A/B independently per loop and stays only in the
  hash-pinned answer key; the public seed exposes only its commitment. The HTML
  auto-loops audio, scopes the shared playhead per review unit and requires
  heard checkboxes for source, A and B plus one explicit
  A/B/equivalent/neither/cannot-tell outcome before reviewed JSON can be
  exported.
- Resolution and effects: `midi-ab-resolve REVIEWED.json` with
  `--package-dir ORIGINAL_UNCHANGED_REVIEW_DIR` and `--out FRESH.json` compares
  the user export with the original seed, key, manifest, audio and inputs. Only
  status/reviewed count, heard, choice and notes changes are permitted. Swapped
  A/B or cross-unit slots and changed timing, focus or geometry fail closed
  before identities are revealed. Both commands report zero MIDI edits,
  selection, promotion and default-change effects.
- Browser-export regression: JavaScript may serialize an equal finite JSON
  number differently, such as `0.0` to `0`. The resolver accepts that numeric
  canonicalization but still rejects booleans, strings, changed numeric values,
  keys, list order and every other immutable change.
- Private package: generated under ignored
  `work/ai-bakeoff/lidl-phase5-beam-rms-review-v4/`, with package commitment
  `b5e3556f70560c86cbe79fbcc4bb7d9a8362c67824beed203bffa0675162dd10`.
  Its exact 48 kHz windows are 0.20–3.50, 3.50–7.50 and 11.60–15.00 seconds,
  using explicit common origin `0`, GeneralUser-GS program 4/SF2 hash
  `9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe`
  and FluidSynth 2.5.6 hash
  `93589cfaf73a5aaaaf37dd313be4d815fb2ced8f0e8ae641b0e1d0026e546911`.
  Every final A/B PCM RMS pair matches to six decimals and is unclipped.
- Listening result: the 0.20–3.50 and 11.60–15.00 second loops were equivalent;
  3.50–7.50 seconds marginally preferred beam 1. Beam 2 won no loop. The
  resolved result records zero MIDI edits, source mutations, selection changes,
  promotions and default changes.
- Problems/risks: exact common frame windows do not make browser media-element
  switching sample-accurate. The standalone page remains shared-second media;
  Phase 5.5 gives Workbench a separate decoded per-stem path, while Phase 5.6
  and 5.7 add decoded canonical short/full-song arrangement paths. The
  arbitrary selected-arrangement mixer remains coarse. Fixed-window sample RMS
  also cannot guarantee equal perceived loudness.
- Decision: retain beam 1 as the default. Equivalent loops provide no
  directional evidence, and the marginal beam-1 preference does not authorize
  merging or changing either candidate. Continue with one-variable performance
  experiments without reopening this resolved review or promoting beam 2.

### 2026-07-19 — Strict beam-1 versus beam-2 small-CPU comparison

- Goal: test whether MuScriptor beam search changes the useful MIDI enough to
  justify its additional local CPU cost, changing one semantic setting only.
- Change or experiment: added read-only `ai-setting-compare`. It consumes at
  least two current fresh-process runs per arm, re-verifies every immutable
  input, requires exact within-arm output repeatability and permits only
  `beam_size` 1→2 with the derived strategy change `greedy`→`beam-search`.
  Legacy, session, application-cache, overlapping, non-repeatable and
  multi-setting evidence fail closed. Candidate-provenance JSON and canonical
  note-payload equality are reported separately.
- Inputs: two beam-1 controls followed by two beam-2 challengers on the private
  15-second Lidl M2 full-mix golden at 119 BPM, with the same seven ordered
  roles and three independent five-second chunks.
- Model/runtime/checkpoint: MuScriptor 0.2.1 small on CPU, macOS
  26.5.1 arm64, Python 3.12.10 and PyTorch 2.13.0; checkpoint
  `bbd482c786b895cf7d8f44185073d951adae2ebb8a66f82ca84cd1f84569549c`,
  config `3008fc481e4a1cd978e337eb3759260c270892204db5039235ac939e1f42aeb2`
  and worker
  `65553b60c4bc0d51533fc56c56e359eab2cac18e49f23f31c6d585ddb346d4dd`.
  Batch 1, CFG 1.0, temperature 1.0, no sampling and every other setting were
  identical. No checkpoint was downloaded.
- Evidence and metrics: both repetitions inside each arm produced exact raw,
  normalized, note-payload, base/expression MIDI, quality and program-mapping
  hashes. Beam 1 produced 107 notes; beam 2 produced 124. Beam 2 added a
  12-note `voice` label, changed `electric_bass` 34→48, `flutes` 44→33 and
  `clean_electric_guitar` 14→16 while `drums` stayed 15. Ninety greedy
  one-to-one same-pitch/same-label onsets matched within 80 ms: 84.1% of beam 1
  and 72.6% of beam 2. Both arms remain `review-required` because restricted
  label leakage was present. In the ordered golden, observed beam-2 median
  pipeline was `32.787408 s` versus `5.282282 s` (`6.207054×`); inclusive
  transcription `31.177499 s` versus `3.824411 s` (`8.152235×`); first
  completed note `10.908671 s` versus
  `1.554210 s`; and peak RSS `1,489,354,752` versus `1,173,610,496` bytes
  (`1.269037×`). The hardened v2 path-free report also treats expression MIDI
  as auditionable output; its SHA-256 is
  `8177d3245856d97a26d0c1e5c289a0bb5eddbb257579fdb414456cd9f0db2fb0`.
- Listening result: pending. The note payload and MIDI differ, so automated
  quality, label, overlap and resource metrics cannot select a winner. A
  preliminary private same-patch Workbench pair is ready under ignored `work/`
  evidence. Both neutral previews use GeneralUser-GS SHA-256
  `9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe`,
  program 4, channel 1 in human numbering and one Workbench role-neutral render
  policy/configured gain. Their WAV hashes are
  `21afa60f863a8a3d9de6083ea0095d727eeec4100c55c8d35e2723a4d18114ab`
  (beam 1) and
  `0847e16b0cea533a94752a9a699e930c4fa6d6f16e328c76db361cc8e0fa0566`
  (beam 2). This controls the Workbench patch and configured render gain, but
  it is not perceptually loudness-normalized and cannot close the final
  listening gate.
- Decision: retain beam 1 as the default. Beam 2 is a listening challenger only;
  it cannot become a preset unless an explicit same-renderer, same-patch review
  on a source-aligned loop with separately verified level matching prefers it
  on a predeclared musical question without an unacceptable stability/resource
  regression. The five reviewed selection hash
  and GarageBand handoff ZIP remain
  `1dce19ce7595a72b8417225b8d23679e0fc92e53581807ccf9db6ea929d7709c`
  and `7824e25850037821287fd77337ae9e8ad2d61cea2cbd2ea57e3b2f92e0c532f8`.
- Problems/risks: controls ran before challengers; order was not randomized and
  the operating-system file cache was uncontrolled. Two repeats establish this
  golden's determinism, not a hardware distribution or musical accuracy.
- Next smallest step: use the preliminary pair to find the useful comparison
  passages, then prepare source-aligned, separately verified level-matched short
  loops for the actual gate. If the full-note piano proxy is too dense to judge,
  split the changed bass, flute, voice and guitar-labelled layers into short
  fixed-patch phrase comparisons; keep the default unchanged until that review.

### 2026-07-19 — Exact MuScriptor raw-result application cache

- Goal: avoid rerunning one byte-identical deterministic MuScriptor request
  without calling a stored result resident-model reuse or inference.
- Change or experiment: added explicit
  `ai-transcribe --application-cache-dir`, a private content-addressed
  raw-result cache, fail-closed verification, fresh-run materialisation with
  current post-processing, Workbench cache provenance, and read-only
  `ai-cache-benchmark` over one stored miss plus at least two verified hits.
- Inputs: deterministic synthetic source/checkpoint/worker regression fixtures,
  then the existing private 15-second Lidl M2 full-mix golden at 119 BPM as one
  fresh miss followed by two exact hits.
- Model/runtime/checkpoint: MuScriptor 0.2.1 small on CPU, Python 3.12.10,
  PyTorch 2.13.0, greedy decoding, batch 1, beam 1, CFG 1.0 and three
  independent five-second chunks. Stochastic sampling is rejected; no model
  was downloaded and no checkpoint licence changed.
- Evidence and metrics: the private gate produced one `miss-stored` run and two
  `verified-hit` runs under cache key
  `ea405ee021800e1fb980d39cab8c274e888a45c74b838f29b13ead8f0eb4b3a9`.
  Both hits started no worker, loaded no model and executed no inference. All
  runs produced 107 notes with candidate JSON hash
  `fba42cf43cbcacf614e25936ff1457be44a4f68f37f9e257d291c843df53c552`
  and MIDI hash
  `9bc1ede96cf8be5704573456753f7892748c14ecbe1b1c294249afb0c45d4e05`;
  raw candidate, expression JSON/MIDI, quality and program mapping were also
  identical. Miss pipeline time was `6.295317 s`; verified-hit median was
  `1.077984 s` (RTF `0.071866`), an observed hit/miss pipeline ratio of
  `0.171236`. The path-free benchmark SHA-256 is
  `6f0cb17c9a63f45dbf7be5c3886a2a977f79881dc805a14b5b0e691f54187d86`.
- Listening result: not applicable. Cache evidence cannot promote, select or
  repair a musical candidate.
- Decision: the private exact-repeat gate passes. Keep the cache explicit and
  disabled by default, cache only raw model evidence, rebuild derived MIDI with
  current Sunofriend, and do not silently integrate it into Workbench
  processing. The five reviewed selection hash and GarageBand handoff ZIP
  remain `1dce19ce7595a72b8417225b8d23679e0fc92e53581807ccf9db6ea929d7709c`
  and `7824e25850037821287fd77337ae9e8ad2d61cea2cbd2ea57e3b2f92e0c532f8`.
- Problems/risks: cache roots and immutable runs are private; content hashes
  and runtime identity can still identify material or a machine. Disk eviction
  is not implemented, the operating-system file cache remains uncontrolled,
  and exact reuse proves neither independent model agreement nor accuracy.
- Next smallest step: retain this as an opt-in execution primitive while Phase
  5 proceeds to measured model/preset comparisons and hybrid phrase consensus;
  add eviction or broader Workbench processing only behind a separate design
  and privacy gate.

### 2026-07-19 — Bounded reused-model session harness

- Goal: isolate the cost and output effects of reusing one loaded MuScriptor
  model without conflating that change with application caching or a production
  multi-song service.
- Change or experiment: added `ai-transcribe-session` for 2–20 exact serial
  copies of one fixed source/roles/excerpt/request through one parent-owned
  inherited Unix socket pair, plus read-only `ai-session-benchmark` evidence.
- Inputs: the private 15-second Lidl M2 full-mix golden at 119 BPM, repeated
  three times in one session, plus two new final-worker fresh-process controls.
- Model/runtime/checkpoint: MuScriptor 0.2.1 small on CPU, Python 3.12.10,
  PyTorch 2.13.0, greedy decoding, batch 1, beam 1, CFG 1.0 and three
  independent five-second chunks. Checkpoint, config and worker hashes were
  pinned; no model was downloaded.
- Evidence and metrics: startup/model load is separate; request 1 has a resident
  model but no prior transcription and is not warm/cold evidence; requests 2+
  are reused-model warm. All five runs produced the same 107-note candidate
  JSON hash
  `fba42cf43cbcacf614e25936ff1457be44a4f68f37f9e257d291c843df53c552`
  and MIDI hash
  `9bc1ede96cf8be5704573456753f7892748c14ecbe1b1c294249afb0c45d4e05`.
  Model load was `0.279094 s`; request-1 pipeline was `3.983435 s`; warm
  pipeline median was `3.680823 s` (RTF `0.245388`); warm worker-request median
  was `3.651402 s`; and warm inclusive-transcription median was `3.641215 s`.
  The new fresh controls had median pipeline `5.193385 s` and inclusive
  transcription `3.731320 s`, yielding observed warm/fresh ratios `0.708752`
  and `0.975852` respectively. Parent-observed session total was `16.189478 s`
  (`5.396493 s` amortised per request). Startup, first-request, request-2,
  request-3 and final process-RSS high-water values were `1,062,928,384`,
  `1,122,189,312`, `1,145,618,432`, `1,157,349,376` and `1,157,365,760` bytes.
- Listening result: not applicable; this increment cannot promote, select or
  mutate a musical candidate.
- Decision: the exact-repeat CPU gate passes and justifies retaining the
  bounded worker for controlled reuse experiments. Keep it a diagnostic
  harness; do not describe it as a background service, multi-song role worker
  or content cache. The warm/fresh ratios are observed end-to-end differences,
  not proof that model reuse alone caused the gain.
- Problems/risks: the private session tree contains paths. Its separate report
  is path-free, but hashes and runtime identity can still be identifying and do
  not provide publication consent. The operating-system file cache is
  uncontrolled. RSS is cumulative process high-water evidence, excludes
  accelerator allocation and is not a standalone leak measurement. The five
  reviewed Phase 5.1 selection hash and handoff ZIP hash remain
  `1dce19ce7595a72b8417225b8d23679e0fc92e53581807ccf9db6ea929d7709c`
  and `7824e25850037821287fd77337ae9e8ad2d61cea2cbd2ea57e3b2f92e0c532f8`.
- Next smallest step: completed by the separate exact-result application-cache
  increment and private golden above. Broader Workbench processing remains a
  later, separately reviewed gate.

### 2026-07-19 — Phase 5.2 fresh-process small-model baseline

- Goal: establish an honest, reproducible speed baseline before adding a
  persistent worker, cache, larger checkpoint or faster decoding setting.
- Change or experiment: added a separate hash-pinned
  `muscriptor.performance.json` to fresh MuScriptor runs, parent-observed worker
  subprocess timing, and `sunofriend ai-benchmark`. The report reuses the
  immutable matrix verifier, requires equal source/requested-and-actual-
  excerpt/BPM/roles/device/checkpoint/config/worker/execution/runtime evidence,
  source-frame-derived duration, nested timers and non-overlapping repetition
  windows; it is path-free and never launches a model or promotes a musical
  result.
- Inputs: two fresh sequential runs of the existing private 15-second Lidl M2
  full-mix golden at 119 BPM. The original source and all generated evidence
  remain under ignored `work/` paths.
- Model/runtime/checkpoint: MuScriptor 0.2.1 small on CPU; checkpoint
  `bbd482c786b895cf7d8f44185073d951adae2ebb8a66f82ca84cd1f84569549c`,
  config `3008fc481e4a1cd978e337eb3759260c270892204db5039235ac939e1f42aeb2`,
  greedy, batch 1, beam 1, CFG 1.0 and three independent five-second chunks.
  No checkpoint was downloaded.
- Evidence and metrics: both repetitions produced byte-identical 107-note
  candidate MIDI. Median pipeline wall time was `5.189138 s` (RTF `0.345943`),
  worker subprocess `5.114512 s` (RTF `0.340967`), inclusive transcription
  `3.654508 s` (RTF `0.243634`), model load `0.291326 s`, first note start
  `1.478891 s`, first completed note `1.580453 s`, first completed chunk
  `2.541311 s`, and peak process RSS `1,142,669,312` bytes (about `1.06 GiB`).
  First/later pipeline ratio was `1.117054`.
- Comparability: both runs used `macOS-26.5.1-arm64-arm-64bit`, Python 3.12.10,
  PyTorch 2.13.0 and MuScriptor 0.2.1. All RTFs use the 15-second duration
  verified from the pinned source frames and request bounds. Inclusive
  transcription is iteration of
  MuScriptor's lazy `model.transcribe` result, so it includes backend
  preprocessing, condition construction and decoding rather than only model
  forward time.
- Listening result: none required. This increment measures execution and exact
  output repeatability; it does not compare musical alternatives.
- Decision: keep the small CPU fresh-process measurements as the Phase 5.2
  baseline. The second process may benefit from an uncontrolled OS file cache,
  but both runs reload the model, so neither is called a warm-model run.
- Controls: the new candidate MIDI hash
  `9bc1ede96cf8be5704573456753f7892748c14ecbe1b1c294249afb0c45d4e05`
  matches the earlier M2 MIDI. The five-track Phase 5.1 selection hash remains
  `1dce19ce7595a72b8417225b8d23679e0fc92e53581807ccf9db6ea929d7709c`
  and the handoff ZIP remains
  `7824e25850037821287fd77337ae9e8ad2d61cea2cbd2ea57e3b2f92e0c532f8`.
- Problems/risks: process RSS excludes accelerator allocation; pipeline time
  includes local post-processing but ends before the final runtime snapshot and
  manifest write; two repetitions are a baseline, not a hardware distribution.
- Next smallest step: completed by the bounded resident-model gate plus the
  separate application-cache implementation and private golden above. Broader
  integration remains later work.

### 2026-07-19 — Safe-lane bass, keys and vocal review completed

- Goal: compare the decoder-safe small-model routes on musical usefulness
  without letting different preview patches or absolute timelines bias the
  result.
- Change or experiment: built a three-row private Workbench catalog for bass,
  keys and vocal melody. Each row compares the isolated-stem M3 result with
  two exact M1/M2 full-mix label partitions. M3 review copies were shifted
  from song seconds 30–45 to review seconds 0–15 without changing pitches,
  durations, velocities or note counts.
- Controls: all nine candidates are rendered locally through one fixed
  role-appropriate General MIDI program per row (bass 33, keys 4, vocal 73),
  using the same SoundFont and preview policy. Original candidate MIDI remains
  unchanged.
- Review question: choose by recognisable bass contour, useful keys theme or
  accompaniment, and recognisable sung contour. Model labels such as sax,
  flute or guitar are hypotheses, not physical source-instrument identities;
  `none usable` remains a valid outcome.
- Listening result: bass had a clear choice: the 34-note M2 metadata-
  conditioned full-mix partition is main; the 19-note isolated M3 result needs
  correction and the 13-note M1 full-mix partition is rejected. Keys also had
  a clear choice: the 181-note isolated M3 result is main and the 106-note M1
  piano-labelled partition is optional; the 14-note M2 clean-guitar-labelled
  subset needs correction. Vocal outcome was `equivalent`: the 39-note
  isolated M3 line is the arrangement main and the 38-note M1 sax-labelled
  line remains optional; the 44-note M2 flute-labelled line needs correction.
  No problem tags or written reasons were supplied, so none are inferred.
- Full-mix check: all five selected main/optional tracks were explicitly saved
  in `full_mix` context. Three selected pairs share the verified full-mix AI
  origin, but none meets the substantial-overlap threshold. Their exact-
  pitch/onset match counts are 21, 0 and 11; the corresponding coverage pairs
  are 61.8%/19.8%, 0%/0% and 10.4%/28.9%.
- Decision: there is no universal lane winner. For this private golden, M2 is
  the reviewed bass route and isolated M3 is the reviewed keys route. The
  vocal row has an `equivalent` outcome, with M3 main and M1 optional; the
  saved data does not state a more specific equivalence claim. Keep raw lanes
  and role-labelled partitions; use the result as role-specific routing
  evidence, not automatic promotion across songs. The zero-note M3 drum lane
  and severe M0 decoder burst remain diagnostic-only.
- Handoff: a five-track, 119 BPM, B-major GarageBand ZIP contains exact copies
  of the reviewed main/optional MIDI and a dry neutral proxy. Source audio,
  private notes and every rejected/needs-correction candidate are excluded.
- Next smallest step: begin Phase 5.2 with a reproducible small-model runtime
  and cache benchmark; require separate authorisation before acquiring any
  medium or large checkpoint.

### 2026-07-19 — M4 listening rejects label isolation but keeps both full contours

- Goal: decide whether the bass-conditioned pass, clean-guitar-conditioned
  pass or exact label partition gives useful separate body/pluck MIDI.
- Listening result: the 41-note bass-conditioned full candidate and 43-note
  clean-guitar-conditioned full candidate were both chosen as main and
  confirmed together in full-mix context. The earlier 30-note body control was
  marked needs-correction; the earlier 11-note pluck and 14-note exact
  clean-guitar label derivative were rejected. No written problem tags or
  private notes were supplied, so no more specific reason is inferred.
- Evidence: the two accepted full candidates match on 40 notes at the declared
  80 ms exact-pitch/onset tolerance. The label derivative is concentrated in
  roughly the final five-second chunk and all 14 of its notes overlap the bass
  pass. The result supports useful contrasting performances or timbral layers,
  not successful source-role separation.
- Decision: retain both unchanged full candidates as the user's private
  arrangement choices; do not promote the model-label partition and do not
  deduplicate the two mains automatically. Add an overlap-aware full-mix
  finalisation warning before using this pattern in broader reviews.
- Handoff: a verified two-track GarageBand ZIP was built at 113 BPM in B minor;
  its numbered MIDI files are exact selected copies and its dry GM proxy is
  only an audition aid. Private media and review state remain ignored.
- Product follow-through: the Workbench now reports substantial overlap for
  selected candidates with the same candidate-origin source audio (verified AI
  run source, with review-stem fallback for non-AI MIDI), leaves the
  arrangement audible, requires the latest `full_mix` confirmation on both
  members before GarageBand handoff, and can export an exact private review to
  a fresh path without starting a server.
- Next smallest step: present the safe M1/M2/M3 Lidl lanes for explicit
  listening.

### 2026-07-19 — Strict M4 mixed-role evidence and label partition

- Goal: test whether one-role conditioning can separate the reviewed deep-body
  and plucked lines in one private mixed-role bass excerpt.
- Change or experiment: made M4 matrices require one distinct role per lane on
  the same source, excerpt and BPM; added M4 peer-overlap diagnostics,
  `ai-label-split`, and optional Workbench `review_question`/`listening_focus`
  prompts. Focused prompt hashes are pinned to review identity and private
  events, while prompt text is excluded from contribution preview. Label
  splitting preserves the unchanged full candidate and exact complement; it is
  not audio separation or instrument identification.
- Inputs: the private reviewed 16-second Slayyyter learned bass target at
  `113.000096` BPM and its earlier body/pluck listening controls. Audio and
  complete artifacts remain under ignored `work/` paths.
- Model/runtime/checkpoint: MuScriptor 0.2.1 small with the already accepted
  checkpoint/config; CPU, greedy, batch 1, beam 1, CFG 1.0 and independent
  five-second chunks.
- Evidence and metrics: the body pass produced 41 `electric_bass` notes. The
  clean-guitar-requested pluck pass produced 43 notes—14 requested
  `clean_electric_guitar` plus 29 off-role `electric_bass`. Forty notes matched,
  covering 40/41 of the body pass and 40/43 of the pluck pass. The exact label
  derivative contains 14 notes and its exhaustive complement contains 29;
  the raw-event partition deletes and duplicates nothing. Its deterministic
  MIDI auditions record integer-pitch/tick quantisation and same-pitch lifetime
  normalisation separately instead of claiming a lossless MIDI encoding.
- Listening result: pending. The private Workbench asks separate body and
  pluck questions and names leakage, missing/extra notes, octave, timing and
  duration as listening focuses; prompts make no selection.
- Decision: engineering evidence suggests substantial role collapse or
  relabelling, not successful two-source separation. Keep both full passes,
  the exact label partition, complement and earlier controls; promote nothing
  automatically.
- Problems/risks: model labels are broad semantic evidence. High overlap is
  not an accuracy score, and a 14-note label partition may still follow the
  wrong audible line.
- Next smallest step: complete the private bass/pluck listening review, then
  decide whether a separate keys melody/accompaniment M4 golden is warranted.

### 2026-07-19 — Explicit MuScriptor manifests and first small-model matrix

- Goal: make Phase 5 AI alternatives reproducible and keep demonstrably broken
  output out of normal Workbench decisions.
- Change or experiment: pinned the installed MuScriptor 0.2.1 execution
  contract, added `sunofriend ai-matrix`, attached its path-free quality/runtime
  evidence to Workbench candidates and reverified every served or handed-off
  artifact at the point of use.
- Inputs: the existing private 15-second reconstructed Lidl golden, its matching
  bass, keys, voice and mixed-percussion stems, and fresh immutable M0–M3 runs.
- Model/runtime/checkpoint: MuScriptor 0.2.1 small; checkpoint
  `bbd482c786b895cf7d8f44185073d951adae2ebb8a66f82ca84cd1f84569549c`;
  adjacent model config
  `3008fc481e4a1cd978e337eb3759260c270892204db5039235ac939e1f42aeb2`;
  greedy, batch 1, beam 1, CFG 1.0, independent five-second chunks. The pinned
  runtime does not expose prelude forcing, which is now recorded explicitly.
- Evidence and metrics: M0 reproduced the rejected 1,912-note result with 1,818
  drum-labelled notes and severe duplicate/onset/polyphony burst metrics.
  Conditioning on its discovered labels (M1)
  produced 169 notes without a severe decoder gate; metadata-conditioned M2
  produced 107 but substituted an unrequested clean-guitar label. Isolated M3
  bass/keys/voice produced 19/181/39 notes; M3 mixed percussion produced no
  notes. M0 is blocked, no-evidence is diagnostic-only, and raw candidate/MIDI
  mutation counts remain zero.
- Listening result: none yet. Cross-lane overlap supplies role-allocation clues,
  not correctness; no M1/M2/M3 lane has been promoted.
- Decision: Phase 5.0 is complete. Keep severe/no-evidence artifacts available
  for diagnosis and download but prevent main/optional selection. Ordinary role
  leakage remains auditionable because the listener may recognise the line.
- Problems/risks: label conditioning is not an output guarantee; the M3
  percussion lane needs a role/input review; browser switching is still
  second-synchronised rather than sample-accurate.
- Next smallest step: completed by the strict M4 entry above; listening of M4
  and the safe M1/M2/M3 alternatives remains before any medium/large model
  download or speed preset.

### 2026-07-19 — Cached comparisons, selected arrangement and GarageBand handoff

- Goal: make the Phase 5 Workbench useful when candidates do not already have
  preview WAVs and carry explicit choices into a listenable/exportable result.
- Change or experiment: added content-addressed neutral candidate rendering,
  shared-second source/candidate switching, an arrangement made only from active
  main/optional decisions, explicit `full_mix` confirmation and a deterministic
  GarageBand handoff ZIP containing unchanged selected MIDI.
- Inputs: synthetic cache/exclusion fixtures and the private Slayyyter Phase 4
  keys, kick, snare and bass artifacts.
- Model/runtime/checkpoint: no model. Existing FluidSynth and GeneralUser-GS
  render the role-neutral audition proxies.
- Evidence and metrics: repeated renders reuse verified SHA-256 caches; tests
  prove rejected/unreviewed MIDI is absent, private notes/paths are absent from
  the ZIP manifest and numbered selected MIDI bytes are unchanged. A real keys
  proxy rendered to `40,525,868` bytes; a four-choice real arrangement produced
  three proxy tracks (combined drums, bass and keys), and the verified handoff
  ZIP was `24,666,200` bytes.
- Listening result: implementation/packaging exercise only; no candidate was
  promoted from the render.
- Decision: keep neutral previews and the arrangement clearly labelled GM
  audition proxies. The selected numbered MIDI remains the authoritative DAW
  handoff.
- Problems/risks: HTML media elements synchronize by seconds, not samples;
  existing previews are not comparable; the instrument-choice view is still
  pending. A public blind review still needs decoded, level-matched short-loop
  switching.
- Next smallest step: completed by the explicit-manifest/matrix increment above.

### 2026-07-19 — Phase 5 local Workbench vertical slice started

- Goal: make existing source/MIDI comparisons understandable in one useful
  local site and retain genuine user decisions across launches.
- Change or experiment: added `sunofriend workbench PROJECT`, deterministic
  automatic or explicit cataloguing, a token-protected loopback HTTP server,
  project/stem pages, shared loop positions, bounded A/B/C candidate cards,
  role/outcome/problem decisions, append-only SQLite storage, JSON export and
  a metadata-only contribution preview with no submission endpoint.
- Inputs: synthetic test fixtures plus a read-only discovery run over the
  private Slayyyter source folder and its Phase 4 specialist MIDI directory.
- Model/runtime/checkpoint: none; the first slice consumes existing immutable
  artifacts and starts no AI worker.
- Evidence and metrics: the real project correctly inferred `113 BPM`,
  `B minor`, `440 Hz` and the chord PDF. Normal candidates are capped at three;
  `possible` and `uncertain` variants are diagnostic-only. Focused catalog,
  persistence, redaction, HTTP token, range-serving and CLI tests pass.
- Listening result: not yet a musical comparison. Many Phase 4 MIDI files do
  not carry a neutral preview WAV, and existing previews are explicitly not
  claimed to be level-matched.
- Decision: keep this UI as a presentation/decision boundary over the existing
  CLI. Do not interpret audition events, dwell time or defaults as preference;
  do not enable public submission.
- Problems/risks: automatic filename discovery can only infer roles, not user
  intent. Use an explicit catalog for ambiguous multi-role material. On-demand
  neutral rendering and whole-arrangement playback remain necessary before the
  site becomes the primary end-to-end workflow.
- Next smallest step: completed by the subsequent cached-preview/arrangement
  and explicit-manifest/matrix increments above.

### 2026-07-19 — MuScriptor full-mix research and Phase 5 draft

- Goal: investigate Mirelo's newly presented Audio-to-MIDI method and plan a
  fair comparison, faster local workflow and contributor feedback loop.
- Change or experiment: identified the converter as the already integrated
  MuScriptor model; inspected the current paper, model cards, official runtime
  and web client; drafted the separate Phase 5 plan.
- Inputs: existing Phase 1 MuScriptor small evidence, official upstream sources
  and the completed fixed-MIDI bass timbre review.
- Model/runtime/checkpoint: no new download or inference. Current local
  `muscriptor-small` 0.2.1 remains optional, hash-pinned and CC-BY-NC-4.0.
- Evidence and metrics: the published method uses a five-second mel-spectrogram
  prefix and a decoder-only Transformer trained with 1.45M synthetic MIDIs,
  more than 11,000 hours of aligned real music and reinforcement-learning
  post-training on 300 verified pieces. The official open UI records consented
  usage analytics, but its source contains no correctness rating or note-edit
  feedback path.
- Listening result: the completed timbre export preferred General MIDI Synth
  Bass 2 overall. GM and harmonic-plus-noise resynthesis were both marked
  ballpark/main; the source sampler was marked far/reject with missing
  consistency.
- Decision: use Phase 5 to compare full-mix discovery with conditioned stem and
  specialist candidates. Keep public feedback opt-in and metadata-first; do not
  host non-commercial model inference or upload arbitrary songs.
- Problems/risks: Mirelo Studio uses a separately trained larger-data model, so
  hosted results are not reproducible evidence for the released checkpoints.
  MuScriptor still lacks velocity and same-pitch overlapping-note support.
- Next smallest step: implement the Phase 5.0 local Workbench vertical slice on
  existing artifacts, then record prelude/batch/beam settings and build one
  immutable full-mix/conditioned/stem review matrix before accepting larger
  checkpoints or enabling public submission.

### 2026-07-19 — Fixed-MIDI timbre review completed

- Goal: decide whether the source sampler or fitted harmonic-plus-noise sound
  beats a complete patch while every candidate plays the identical bass MIDI.
- Change or experiment: validated the user's reviewed export against the
  unchanged seed and all five pinned source/MIDI/candidate hashes.
- Inputs: private Slayyyter bass source excerpt and unchanged 41-note MuScriptor
  performance at `113.000096` BPM.
- Model/runtime/checkpoint: no model; deterministic resynthesis and FluidSynth
  controls only.
- Evidence and metrics: reviewed JSON SHA-256
  `8c9d388e13bbbe1740890a5d6fb73046cb856e609309a126ef609a09b30374ac`;
  source SHA-256 `2bda5f30ac164bf93ec27829a8c740364fe8562b720a46ee006e6d0157f85a1b`;
  fixed MIDI SHA-256
  `540634d7578c1941a7dd8dd6eedb5ddd1f8ab0bcfcfa453f5c535c0cc48f1b14`.
- Listening result: GM Synth Bass 2 was ballpark/main but somewhat uneven; the
  source sampler was far/rejected and missing notes or consistency; fitted
  resynthesis was ballpark/main and complete, with a consistently different
  tone. Overall decision: `prefer_gm`, nearest tone and consistent.
- Decision: retain resynthesis as an optional listening layer, do not package
  it as the recommended generated instrument, and keep the complete GM patch as
  the next model's control.
- Problems/risks: passing the automated 41/41 audibility test did not guarantee
  perceived note-to-note consistency. Functional and musical gates must remain
  separate.
- Next smallest step: use the outcome in the Phase 5 instrument policy and do
  not invest further in the rejected source-sampler primary for this song.

### 2026-07-18 — Fixed-MIDI timbre baseline

- Goal: test sound generation separately from transcription now that the bass
  MIDI is stable.
- Change or experiment: added `timbre-resynthesis`. It fits one shared harmonic
  distribution, sustain ratio and deterministic attack-noise amount from an
  aligned monophonic reference, while rendering the exact same notes through a
  complete GM patch and an optional earlier source SF2.
- Inputs: accepted 16-second learned bass target; unchanged 41-note MuScriptor
  primary at `113.000096` BPM; earlier nine-zone source-derived bass SF2.
- Model/runtime/checkpoint: no model or checkpoint. Native NumPy/soundfile DSP
  at 44.1 kHz. Magenta DDSP and MIDI-DDSP code are Apache-2.0, but direct
  MIDI-DDSP use was deferred because the official repository is archived and
  documents an incompatible TensorFlow 2.7/Python 3.8/M1 installation path.
- Evidence and metrics: fixed MIDI SHA-256
  `540634d7578c1941a7dd8dd6eedb5ddd1f8ab0bcfcfa453f5c535c0cc48f1b14`;
  41 fitted notes; 16 harmonics; noise mix `0.040092`; sustain ratio `1.0`;
  all three candidates functionally audible on 41/41 notes; all MIDI-change
  and automatic-promotion effects zero.
- Listening result: pending in
  `work/ai-bakeoff/slayyyter-dance-phase4-fixed-midi-timbre-review-v2/timbre_resynthesis_review.html`.
- Decision: no candidate promoted. Functional audibility is necessary but is
  not a tone, realism or full-mix musical-quality verdict.
- Next smallest step: complete the timbre review. Package the synthesized
  profile as a playable generated instrument only if listening justifies it;
  otherwise retain the preferred complete patch as the control for a later
  local neural challenger.

### 2026-07-18 — Bass role review resolved without changing the MIDI

- Goal: turn the completed body/pluck listening review into one reproducible
  arrangement choice while retaining all useful alternatives.
- Listening result: the source and unchanged primary contained both roles.
  The strict body/complement split was useful, but the independently
  transcribed residual MIDI was diagnostic rather than an improvement.
- Change or experiment: added `midi-role-split-resolve`. It requires a complete
  user export, verifies the seed, source report, inputs and every artifact, and
  follows the overall decision rather than inferring a winner from component
  usefulness.
- Evidence and metrics: decision `keep_primary`; review SHA-256
  `e0fc94ad9b6236c194ffcc11d4235feb6ee4071d265c28595244015501166833`;
  recommended MIDI SHA-256
  `540634d7578c1941a7dd8dd6eedb5ddd1f8ab0bcfcfa453f5c535c0cc48f1b14`;
  zero notes changed, zero source mutations and zero alternatives deleted.
- Decision: use the unchanged 41-note primary bass MIDI. Retain the body and
  primary-pluck tracks as optional creative resources and the independent
  residual challenger as diagnostic evidence.
- Next smallest step: completed by the fixed-MIDI timbre entry above.

### 2026-07-18 — Reviewed bass cleanup and two-role MIDI challenger

- Goal: act on the listener's consistent observation that the bass stem carries
  both a deep synth-bass line and a shorter plucked synth/guitar-like line.
- Listening result: the completed 12-sound cleanup review selected the learned
  target as the main cleanup and described two roles throughout. The learned
  target was convincing overall but slightly weakened the pluck; the learned
  residual remained musical and retained it. The reviewed JSON SHA-256 is
  `442d242f825bf921cbd7ae328d791ad30495dddca8715cf487c5f70ab414bb45`.
- Evidence: note-aligned OpenL3 plus explainable features found a 30-note body
  cluster with median duration `0.504478` seconds and pitch range 28–40, and a
  nine-note transient cluster with median duration `0.134487` seconds and pitch
  range 33–54; two further transient events remained explicit outliers.
- Change or experiment: added `midi-role-split`. It requires an explicit body
  cluster, preserves every primary note in a strict two-track partition and can
  add a separately transcribed residual MIDI as an overlapping pluck challenger.
  It writes contrasting GM auditions and an unreviewed local export page.
- Independent evidence: MuScriptor found 13 notes in the learned residual,
  including octave pairs at common onsets, so the independent challenger can
  represent overlap that the 41-note monophonic target candidate cannot.
- Decision: keep body cluster `I1` as an explicit listening-backed hypothesis,
  not instrument identification. Compare the exact 30+11 partition with the
  30+13 residual challenger; neither is promoted automatically.
- Next smallest step: completed by the role-resolution entry above. Do not
  generalise multi-role splitting yet; use the unchanged primary for the next
  controlled timbre experiment.

### 2026-07-18 — Phase 4 pinned learned bass cleanup

- Goal: determine whether a local learned separator improves a clearly audible
  bass passage and downstream MIDI more than the unchanged source or transparent
  MIDI-mask baseline.
- Change or experiment: added `ai-cleanup`, an isolated Demucs worker, hard
  checkpoint verification, deterministic PCM24 source/target/residual evidence,
  external model setup, diagnostics, failure records and focused tests. Ran a
  predeclared 192–208 second bass golden and built an explicit 12-sound review.
- Inputs: private Slayyyter bass stem; existing 44-note full-song MuScriptor
  excerpt guide; existing MIDI-mask bass target/residual; fresh same-input
  Basic Pitch and MuScriptor transcriptions.
- Model/runtime/checkpoint: `demucs==4.0.1`, `htdemucs` signature `955717e8`,
  CPU, shifts `0`, overlap `0.25`; external checkpoint SHA-256
  `8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4`.
  Code is MIT; checkpoint terms are not separately stated, so private local
  evaluation only and no vendoring or redistribution.
- Evidence and metrics: two runs produced identical source, target-array,
  target and residual hashes. Target RMS was `-0.214 dB` and residual RMS
  `-14.686 dB` relative to source; persisted reconstruction error was `0.0`.
  Against the same source, short-input MuScriptor learned cleanup improved
  supported notes from `0.744` to `0.805` and octave accuracy from `0.564` to
  `0.585`, but reduced chroma `0.821` to `0.818`, contour direction `0.868` to
  `0.700` and strong onset F1 `0.122` to `0.121`. The DSP target yielded only
  eight MuScriptor notes. Full-context unchanged MuScriptor remained strongest.
- Listening result: completed. The listener selected the learned target as the
  main cleanup, called it convincing overall, and consistently heard a deep
  bass role plus a separate plucked role across the useful alternatives.
- Decision: Demucs is the preferred broad cleanup for this excerpt, but it does
  not solve intra-stem role separation. Preserve the full-context source MIDI,
  target, residual and every cleanup alternative.
- Problems/risks: PyTorch checkpoint deserialisation requires trusted pickle;
  the worker permits it only after exact hash verification. Model source roles
  are broad families. The in-app browser blocks new local `file://` navigation.
- Next smallest step: test an explicit two-role MIDI challenger without
  rewriting or discarding the accepted cleanup evidence.

### 2026-07-18 — Phase 4 stabilization review

- Goal: compare delivered behavior with the original Phase 4 goals and remove
  maintainability or handoff ambiguity before another model experiment.
- Change or experiment: audited the full uncommitted Phase 4 diff and private
  Slayyyter evidence; tightened instrument feedback/profile validation,
  centralized policy contracts, simplified coverage accounting and clarified
  texture-only Bundle instructions.
- Inputs: the existing 16-second keys mask golden, the 413-note keys MIDI,
  source-derived keys bank, reviewed Small Time Piano decision and profiled
  OpenL3 bundle. No new musical challenger was introduced.
- Model/runtime/checkpoint: no model; local deterministic JSON, MIDI, SF2 and
  PCM24 evidence only.
- Evidence and metrics: the stabilization rebuild retained 388/413 mapped
  notes, 328/413 attack-supported notes and 244/413 musical-duration-supported
  notes. The profile repeated byte-for-byte at SHA-256
  `6ff152ecccde09ce214cf889e4e5f6ecdc9adb2e34f59df5c5a65548bbd90b53`;
  the copied performance MIDI remained
  `4c3171886544a56a2f470ce8b0df95a2334dcac6e223f0a8f9e51871c21db533`.
- Listening result: unchanged. Small Time Piano remains the usable primary
  keys patch; the source sampler remains optional texture; unchanged-source
  MIDI remains the best keys melody transcription.
- Decision: the guardrails are stable enough to checkpoint, but Phase 4's
  musical success criterion is not met. Begin no new model work until the
  stabilized code is committed and one clearly audible target passage has a
  predeclared listening test.
- Problems/risks: the CLI and instrument orchestration functions remain large;
  split them incrementally behind characterization tests rather than mixing a
  broad rewrite with research.
- Next smallest step: after checkpointing, test one learned-separation
  challenger on a clearly melody-carrying short passage, or use the more
  promising monophonic bass line if no suitable keys passage exists.

### 2026-07-18 — Explicit GarageBand patch preference profile

- Goal: learn from the successful Small Time Piano full-mix decision without
  turning personal history into an automatic or hidden selector.
- Change or experiment: added `instrument-feedback` to hash-pin one explicit
  DAW choice to a Bundle v1 report/recipe/performance, `instrument-profile` to
  aggregate only named reviewed files, and additive `instrument-bundle
  --preference-profile` guidance.
- Inputs: the private Slayyyter keys playability-gated bundle and the explicit
  full-mix preference for Small Time Piano over the incomplete source sampler.
- Model/runtime/checkpoint: no model. Local deterministic JSON and SHA-256
  evidence only; OpenL3 and explainable match orders remain separate.
- Evidence and metrics: preferred/acceptable/rejected decision weights are
  1/0.5/−1; full-mix/solo context weights are 1/0.5. Duplicate hashes,
  unreviewed feedback, policy mutations and existing outputs are refused. The
  reviewed feedback hash is `b4ba10f58ca5b5310a2041a9a888c45d2064124df2a0a1d7d9eac38fd2710089`;
  two profile builds are byte-identical at
  `6ff152ecccde09ce214cf889e4e5f6ecdc9adb2e34f59df5c5a65548bbd90b53`.
- Listening result: Small Time Piano remains the user's current keys choice
  because it played every note with a consistent usable tone.
- Decision: show a positive history-first patch in future same-role bundle
  instructions, but never reorder factory/GM/OpenL3 evidence, change the MIDI,
  auto-select a patch or bypass a `texture-only` result. The profiled golden
  confirms all three ranking arrays, portable program hint and usability report
  are exactly unchanged.
- Problems/risks: one song is not enough to generalise a universal keys patch;
  profiles therefore preserve counts, negative feedback and listening context.
- Next smallest step: add further decisions only after real full-mix listening
  on new songs, then assess whether context beyond role is justified by data.

### 2026-07-18 — Source-instrument playability gate

- Goal: stop successfully built but incomplete samplers from being recommended
  as primary GarageBand instruments.
- Change or experiment: added Instrument Usability Gate v1, every-performance-
  pitch and velocity-probe auditions, additive Bundle v1 selection evidence and
  an explicit complete-patch fallback. The gate changes no MIDI, samples or
  SoundFont zones.
- Inputs: the private Slayyyter keys baseline and electric-piano sampler, plus
  synthetic coverage, duration, pitched and drum regressions.
- Model/runtime/checkpoint: no new model; deterministic MIDI/SoundFont evidence.
- Evidence and metrics: the baseline MIDI spans 35–95 but the source bank spans
  44–87, leaving 25/413 notes silent; the electric-piano bank spans 51–80 and
  leaves 55/413 silent. Both use short unlooped one-shots and fail as main
  pitched instruments.
- Listening result: GarageBand's Small Time Piano played the full keys MIDI
  consistently and was “night and day” more useful than the source sampler.
- Decision: playability precedes similarity. Demote failing source banks to
  `texture-only`, keep a complete GarageBand/GM patch primary, and require
  listening even after a functional pass. Keys matching now excludes GM synth
  leads/pads, which had produced a musically inappropriate sawtooth winner.
- Problems/risks: pitch detection and timbre clustering cannot establish
  instrument consistency; they remain review evidence. A complete factory
  patch still needs arrangement-level selection by ear.
- Next smallest step: retain Small Time Piano as the current human preference,
  then capture future full-mix patch choices as local advisory ranking feedback.
  Do not let similarity bypass functional checks.

### 2026-07-18 — MIDI-informed keys cleanup baseline

- Goal: determine whether an AI-labelled electric-piano role can separate a
  cleaner transcription target from one short mixed keys passage.
- Change or experiment: added `midi-mask`, a deterministic harmonic target and
  waveform-defined residual with an optional short broadband-onset window.
  It writes a cropped guide MIDI, PCM24 audio, hashes, reconstruction evidence
  and zero input-mutation effects to a fresh directory.
- Inputs: seconds 200–216 of the private B-minor keys stem and MuScriptor's
  electric-piano track 2 with 88 intersecting notes.
- Model/runtime/checkpoint: no new model. The already preserved MuScriptor
  candidate supplies only the guide; librosa STFT/ISTFT supplies the transparent
  DSP baseline.
- Evidence and metrics: persisted reconstruction maximum error is
  `1.19209e-7`. The guide's mean pitch support was `0.503` against the harmonic
  target and `0.026` against the residual, but strong-onset F1 remained higher
  against the residual (`0.439`) than target (`0.330`). The transient target
  raised guide strong-onset F1 only to `0.348`.
- Listening result: the AI electric-piano guide sounded like accompaniment and
  lacked the musical theme. The unchanged-source transcription contained the
  clearest bare bones of the tune. The harmonic target was less convincing and
  more accompaniment-like; the transient target had no real tune; the harmonic
  residual was jumbled/random; and the transient residual was not useful.
- Decision: keep unchanged-source MIDI as the primary result, retain harmonic-
  target MIDI only as an optional accompaniment candidate, and reject the
  remaining masked transcriptions for music-making. The mask is not promoted
  as melody cleanup. Recognition and musical usefulness override favourable
  isolation or polyphony metrics.
- Problems/risks: shared harmonics can leak into the target; a broadband onset
  window can admit simultaneous non-target attacks. Float WAV initially broke
  byte reproducibility through a changing PEAK timestamp, so final evidence is
  deterministic PCM24.
- Next smallest step: do not force this accompaniment-like keys role to become
  the melody. Test a learned separator only on a passage with a clearly audible
  target role, and compare it against unchanged-source MIDI plus this exact DSP
  baseline. Separately improve role selection so a melody experiment starts
  from a guide that actually carries the theme.

### 2026-07-17 — Phase 4 bass/keys golden and honest auditions

- Goal: determine whether local AI improves difficult bass and layered keys,
  and make transcription/timbre comparisons independently audible.
- Change or experiment: built the deterministic 113 BPM full arrangement,
  ran full-song MuScriptor bass and keys challengers, fixed role-blind General
  MIDI program assignment, added custom-SF2 previewing and packaged baseline
  and challenger Instrument Bundle v1 outputs.
- Inputs: one private 236-second B-minor song with 17 local stems, metronome
  and chord chart. No source audio or extracted sample is checked into Git.
- Model/runtime/checkpoint: local MuScriptor small checkpoint under its
  accepted CC-BY-NC-4.0 terms; stable Sunofriend CLI and FluidSynth comparison
  path. Full hashes remain in each immutable run.
- Evidence and metrics: bass strong-onset F1 rose from 0.070 to 0.324 and
  contour accuracy from 0.521 to 0.693 with similar mean pitch support. Keys
  strong-onset F1 rose from 0.223 to 0.438, but mean pitch support fell from
  0.646 to 0.283 and mean polyphony rose from 0.965 to 1.860.
- Listening result: pending GarageBand full-mix review. Source/GM and 2×2
  MIDI/sample-bank auditions are ready under ignored `work/`.
- Decision: retain the baseline arrangement; treat AI bass as a challenger and
  split AI keys by role. Do not promote the combined AI keys candidate.
- Problems/risks: model roles were previously all rendered as program-0 piano;
  that defect changed timbre but not model notes. Short bass events and mixed
  keyboard layers still limit source-derived sampler quality.
- Next smallest step: review the prepared bass and keys comparisons in
  GarageBand, then select one short mixed-keys passage for a target/residual
  cleanup experiment.

### 2026-07-17 — Phase 3 completed

- Goal: close the final GarageBand and pitched-loop listening gates without
  converting either decision into an unreviewed sampler mutation.
- Change or experiment: recorded the listener's explicit `snare v2` and
  `loop 1` decisions in a versioned close-out document and reconciled them
  with the earlier blinded FluidSynth result.
- Inputs: the reviewed snare v2/v3 GarageBand instruments; the three raw Lidl
  bass loop auditions; the hash-pinned blind A/B result and loop report.
- Model/runtime/checkpoint: no model. Human DAW listening and local immutable
  evidence only.
- Evidence and metrics: GarageBand preferred snare v2, overriding the blind
  proxy preference for v3. Candidate 1 for the 1.002396-second MIDI-30 bass
  sample spans 0.304438–0.902167 seconds, lasts 0.597729 seconds and has
  continuity score 0.116972. Its audition SHA-256 is
  `cdf639ff05b43ec5bc66680fc91372c0d250cdb89fdd514d28746c39d43bf6d8`.
- Listening result: final cross-role selections are v2 for snare, hats,
  cymbals and toms. Bass loop candidate 1 is the reviewed suggestion. Earlier
  kick event-17 and `other_kit` event-25 v3 packs remain experiments.
- Decision: mark Phase 3 complete. Do not promote the reviewed cross-role v3
  packs, and do not enable candidate 1 in SF2/SFZ automatically. The
  machine-readable close-out SHA-256 is
  `31332e2b076367d697fbc7a7f3acf9141b85003e59e7d42d16af2c1db28e0ebe`.
- Problems/risks: a good isolated sample does not guarantee the best musical
  result in a full DAW performance. The selected loop remains advisory because
  automatic loop application and crossfade tuning are deliberately outside
  this phase.
- Next smallest step: begin Phase 4 only when explicitly requested; no Phase 3
  engineering or human-review task remains open.

### 2026-07-17 — Blinded v2/v3 performance result resolved

- Goal: reveal v2/v3 identity only after the listener completed every neutral
  Candidate A/B choice, then retain the musical result without altering a
  sampler automatically.
- Change or experiment: validated reviewed export SHA-256
  `573e23366f80ea4120ed54007c57ca558496ddea59ff3e3a51b6036d3cfec876`
  against three unchanged v3 reports, every copied WAV, manifest SHA-256
  `46272b4b6604188049703adab20b369a46e089a40c8e36f23c132b55fa1e867e`
  and answer-key SHA-256
  `b8b6e241dd8c2ac2757cd4096cc9d87d855c614e9d45f32b85519733c3748d23`.
  Resolved it twice at fresh result paths.
- Inputs: the completed three-unit blind export; the reviewed snare, hats and
  toms v3 packs and embedded v2 baselines.
- Model/runtime/checkpoint: no model. Local JSON/hash validation only.
- Evidence and metrics: Candidate B was selected for snare and hats; Candidate
  A for toms. The answer key revealed snare B as v3, hats B as v2 and toms A as
  v2. The listener noted that selected snare and hats candidates were useful
  but not as rich as the source. Result SHA-256 is
  `95cc52ab61e8aa5d4a3e6a24d67625a539cc8c6a9287df2c78497166f59f4e91`;
  the repeat result is byte-identical. Summary: one v3 preference, two v2
  preferences, zero equivalent/neither and zero sampler/MIDI effects.
- Listening result: retain snare v3 as the only cross-role challenger. Retain
  unchanged v2 for hats and toms; the full-performance result outweighs their
  accepted isolated source-event choices. Cymbals already remain v2 because
  every proposal was rejected.
- Decision: do not promote the reviewed hats v3 or the tom velocity-layer v3.
  Keep them as evidence and rollback experiments. Take only snare v3 to the
  final GarageBand comparison.
- Problems/risks: FluidSynth is still a proxy and the selected snare remains
  less rich than the source stem. An eight-bar excerpt may not expose every mix
  context.
- Next smallest step: confirm snare v3 against its v2 rollback in
  GarageBand/AUSampler using the supplied real-performance MIDI, and record a
  candidate-or-none bass loop decision before closing Phase 3.

### 2026-07-17 — Reviewed cross-role v3 and blinded close-out gate

- Goal: apply the completed snare, hats, cymbals and toms reviews exactly, then
  test the resulting challengers without revealing v2/v3 identity.
- Change or experiment: validated four new exports against all pinned source
  evidence. Built and repeated separate reviewed snare, hats and toms v3 packs.
  The all-rejected cymbal export correctly produced no no-op v3. Added a
  blinded multi-pack page with copied source reference, Candidate A/B
  performance audio, the tom velocity sweep, a separate answer key and a
  hash-checking resolver.
- Inputs: reviewed export SHA-256 values: snare
  `8e5c99e9bb220951c877b66d2cd4c674fd077eb1b23b0d19c13b421ef2f60572`,
  hats `0baf25457f9048cebe6d159fd0b1f69ef3a141aed11c044d47533ca51660f6cf`,
  cymbals `d2a6d33db92e18105feec1cb5e8328b8fb2444c8dcdec4d45c956f7654043c3a`
  and toms `b9aace5ef10baaec91b15c62c4eeb582c7143f05c408e6d2b3513da6500698fb`.
- Model/runtime/checkpoint: no model. Deterministic source-event extraction,
  SF2/SFZ generation, FluidSynth rendering and local HTML/JSON only.
- Evidence and metrics: snare accepted event 44 at MIDI 40; hats accepted event
  35 at MIDI 42 and event 21 at MIDI 46; cymbals rejected all three units;
  toms accepted events 5/39 as MIDI-45 velocity layers split at 107/108 plus
  event 9 at MIDI 48 and event 14 at MIDI 50. No alternates were accepted.
  The v3 SoundFont hashes are snare
  `ccc891b7619ebdf9d3e368e41c2d26032944d4db1118d4cc10ac3626471af0df`,
  hats `6d09775e2f3e1ea50d1db5c5fb9a6ad87240173461483cb8483f3598f7c84739`
  and toms `c4c592df360facffc0c68b68b3b79dd780a8e44f6114a37abdc160ff698dae4c`.
  Main/repeat musical artifacts, sample trees and normalized reports match.
  The blind page contains three neutral units and one tom sweep; answer-key
  SHA-256 is
  `b8b6e241dd8c2ac2757cd4096cc9d87d855c614e9d45f32b85519733c3748d23`
  and audio-manifest SHA-256 is
  `46272b4b6604188049703adab20b369a46e089a40c8e36f23c132b55fa1e867e`.
  The complete repository suite passes with 351 tests.
- Listening result: source-event choices are complete; blinded v2/v3 preference
  remains open. The listener must not inspect the separate answer key first.
- Decision: retain the three reviewed challengers and the unchanged cymbal v2.
  Do not call any challenger better until the blinded export is resolved. Keep
  the tom boundary at 107/108 unless its sweep motivates a separate reviewed
  boundary workflow.
- Problems/risks: FluidSynth remains a proxy for GarageBand/AUSampler and a
  short 8-bar excerpt may not expose every arrangement context. Blinding hides
  version identity, not audible extraction artefacts.
- Next smallest step: review and export the three-unit blinded page, resolve it
  against the pinned answer key, record the bass loop candidate-or-none result,
  and confirm any preferred v3 once in GarageBand before closing Phase 3.

### 2026-07-17 — Phase 3 engineering close-out and sustain-loop evidence

- Goal: resolve the final unchecked Phase 3 engineering feature and prepare a
  cross-role listening gate without manufacturing any musical decisions.
- Change or experiment: added deterministic advisory loop-boundary analysis for
  pitched sample packs, with waveform/spectral continuity metrics, an SVG and
  click-revealing raw-repeat WAVs. Built fresh neutral Sample Instrument v2
  packs and review pages for Lidl snare, hats, cymbals and toms, then repeated
  the whole batch at independent output paths.
- Inputs: the permanent authorised Lidl stems and listened repair MIDI; the
  existing Lidl bass 200–215-second fixture for pitched loop evidence. Source
  and MIDI hashes are pinned in each generated report.
- Model/runtime/checkpoint: no new learned model. Loop ranking uses deterministic
  PCM waveform, log-spectrum, centroid and within-loop level evidence. The
  existing optional OpenL3 path remains separate and unchanged.
- Evidence and metrics: the bass pack contains five zones. Four source samples
  are below the 0.65-second advisory minimum; MIDI 30 is 1.002396 seconds and
  produced 791 evaluated boundary pairs plus three review candidates. The first
  candidate spans 0.304438–0.902167 seconds with continuity score 0.116972.
  The generated SF2/SFZ contain zero looped zones. The drum batch exposes 12
  review units and 42 exact candidate events: snare 4/15, hats 2/6, cymbals
  3/9 and toms 3/12. Snare and toms each have one possible velocity split.
  Every seed remains unreviewed, every primary starts blank and all effects are
  zero. Main/repeat SF2, SFZ, MIDI, WAV, sample, analysis and review-audio
  hashes match after output-path provenance is normalised. The repository's
  348 tests pass; wheel/source builds, `twine check` and a supported-Python
  clean-install CLI smoke test also pass.
- Listening result: open. A continuity score cannot decide whether a loop
  repeats phrase motion, vibrato, bleed or an effect. Likewise, source-event
  clustering cannot establish that two drum hits are the same instrument.
- Decision: mark Phase 3 engineering complete but keep Phase 3 itself open at
  its explicit listening gate. Apply no loop, drum-family, velocity-layer or
  alternate-sample choice automatically.
- Problems/risks: raw loop auditions intentionally reveal discontinuities and
  do not preview a crossfade. Short extracted notes cannot sustain indefinitely.
  FluidSynth and extracted stem context remain proxies for GarageBand/AUSampler
  use in a full arrangement.
- Next smallest step: the listener reviews the four neutral drum pages and the
  three bass loop auditions. Apply accepted drum choices to fresh v3 outputs,
  retain rejected roles unchanged, and record whether any loop candidate is
  musically usable before declaring the Phase 3 listening gate closed.

### 2026-07-17 — Reviewed Lidl kick event 17 applied

- Goal: apply the listener's explicit Lidl kick review while preserving the
  source MIDI, v2 instrument and every unselected source event as evidence.
- Change or experiment: validated the exported review against its pinned stem,
  MIDI, v2 report/SF2, cluster/dynamics reports and nine review WAVs. Built a
  fresh Sample Instrument v3 in which MIDI 36 uses reviewed event 17; MIDI 35
  retains its v2 zone. Repeated the complete apply at a second fresh path.
- Inputs: reviewed JSON SHA-256
  `1e4767b7a03137e6230840ceb902176a40dd512f731a9acbe9ab12ee016dd88c`;
  source v2 report SHA-256
  `bb3d0bfb623f6fc33f94e4fea52ff4df6af37f72963944975a2cbebab30b219b`;
  source repair MIDI SHA-256
  `91a1ed0a573cfed46300c1567db3344f32c81d0db36d063112231dc9ea5e689a`.
- Model/runtime/checkpoint: no learned model. Reviewed source extraction,
  deterministic SF2/SFZ construction and FluidSynth A/B rendering only.
- Evidence and metrics: one unit was accepted at MIDI 36 with event 17 as its
  sole primary; events 42 and 6 were not accepted as alternates. The v3 has two
  zones, one reviewed replacement, no velocity layer, no round robin and no
  GarageBand alternate bank. It changed zero MIDI pitches and velocities and
  left the source v2 tree unchanged. SF2 SHA-256 is
  `0237587bf6ea22440e5e721c7c09a426a91c24494fa1cc3859a518b31b34fd4b`.
  The eight-bar performance A/B contains 35 notes, both source pitches 35/36,
  velocities 103–120, and source beats 396–428 (199.664–215.798 seconds).
  Performance MIDI SHA-256 is
  `74a6a7c5e649680671085fd20f77f13da0ec53a0864c722de3605c33a0a46481`;
  the new v3 preview SHA-256 is
  `80fc15ed92525fa91183b3ccab8c8b4fc48e38cd06e49d2b1608999e61b7135d`.
  The repeat build reproduced every musical artifact and sample-tree hash.
- Listening result: the reviewer explicitly accepted event 17 as primary and
  selected no alternates. No textual reason was supplied, so none is inferred.
- Decision: retain event 17 as the sole reviewed MIDI-36 replacement in this
  experimental v3. Do not claim round robin or a velocity layer. Keep the
  embedded v2 bank as the authoritative rollback.
- Problems/risks: event 17 still contains the source stem's separation,
  processing and room context. FluidSynth preview is a proxy for AUSampler;
  the event choice still needs source/v2/v3 listening in GarageBand context.
- Next smallest step: compare the shared eight-bar source, v2 and v3 renders;
  if event 17 remains preferable in context, retain this pack and prepare the
  next clean drum role for the same explicit review workflow.

### 2026-07-17 — Lidl kick alternate-sample review v1

- Goal: test the Phase 3 dynamics workflow on a cleaner, single-role drum stem
  after rejecting an unlike `other_kit` velocity pair, without carrying that
  earlier listening decision into a different instrument.
- Change or experiment: built a fresh two-zone Sample Instrument v2 from the
  user-written Lidl kick stem and its unchanged repair MIDI, then generated a
  context-rich, unreviewed sample review. Each candidate has an isolated hit,
  a source-rhythm excerpt and the same normalized repeated two-bar audition.
  Final handoff QA also removed the review page's visual first-primary default:
  every primary now starts blank, and an accepted layer cannot be marked
  reviewed until the listener explicitly chooses one.
- Inputs: `Lidl-kick-B major-119bpm-440hz.wav` SHA-256
  `6070f98d222eac1d19a78b529e71a8b10d09581483f9c83833766079aef16022`;
  published repair `kick.mid` SHA-256
  `91a1ed0a573cfed46300c1567db3344f32c81d0db36d063112231dc9ea5e689a`.
- Model/runtime/checkpoint: no learned model. Existing explainable event
  features, deterministic clustering/dynamics policy, PCM extraction, SF2
  construction and FluidSynth preview only.
- Evidence and metrics: the broad match experiment had profiled 240 events
  with polyphonic windows permitted and proposed one velocity-layer unit. The
  sample-pack path instead profiled its default 48 isolated candidate windows;
  no velocity-layer unit survived that safer scope. It retained one MIDI-36
  alternate set containing events 42, 6 and 17 at velocities 120, 111 and 115
  and RMS levels -12.340, -12.763 and -12.911 dB. The v2 bank has two zones;
  SF2 SHA-256 is
  `b83604899a91d3aa12b41164342292ec16ac1efa730eef439b0b79cbb77532d5`.
  The review pins nine WAVs, six of them contextual, under manifest SHA-256
  `057a7245e22dfb85d363d74289154b76a0f103b318d0085259b62521e7398895`.
  A second clean run reproduced every SF2, SFZ, MIDI, WAV, sample-tree and
  review-audio hash. The corrected v2 review retains the same pinned manifest
  because the listening audio is unchanged; only the decision UI changed.
- Listening result: open. The review must establish whether the three events
  retain the same kick pitch, attack/body balance and decay, with only useful
  natural variation; it must not assume similarity from cluster membership.
- Decision: expose one alternate-sample review only. Supersede the first page
  with the explicit-primary v2 page, keep the seed unreviewed, accept no
  velocity layer and make no MIDI, sample-selection, baseline or SoundFont-zone
  change.
- Problems/risks: the 48-event cap is a deterministic evidence subset rather
  than every isolated event in the song. Normalized repeated beats reveal
  timbre but not original level; source-context excerpts retain relative level
  but also contain musical context and possible separator residue.
- Next smallest step: collect the explicit review export. If events are judged
  one identity, build a fresh v3 with one primary and only the explicitly
  checked alternates; otherwise reject the proposal and retain v2 unchanged.

### 2026-07-17 — Reviewed single-upper mapping applied

- Goal: resolve the audible MIDI-35 identity change using the listener's
  explicit v2 mapping choice, while preserving the source MIDI, source sample
  audio and earlier v3 pack.
- Change or experiment: validated the hash-pinned reviewed export and applied
  `single-high`. The fresh v3 maps upper source event 25 across velocities
  0–127, deactivates lower event 13 and removes the former boundary at 116.
  A second clean build was made only to test deterministic output.
- Inputs: unchanged Lidl `other_kit` context-reviewed v3; reviewed schema v2
  export; MIDI 35 events 13 and 25; original source MIDI SHA-256
  `de5926a88993b1e0af29724363b924e9c42c275249662403131765d980fd3155`.
- Model/runtime/checkpoint: no learned model. Deterministic MIDI/SF2 generation,
  FluidSynth rendering and SHA-256 validation only.
- Evidence and metrics: the final SF2 has 11 zones, four reviewed primary
  replacements and no velocity layer, round robin or alternate bank. The
  boundary apply changed zero MIDI notes and zero velocities, introduced zero
  source events, modified zero source sample files and removed one active
  event. SF2 SHA-256 is
  `2301d36e54e010fa5d1a33ee0b8de922de47674a9d896667836aa8a84eda9dde`;
  the 12-bar performance MIDI remains
  `49a676dbfb643079a6eb8d3afcfc2c0ae8883a37966fc88e6b0033679bdb05d9`;
  its new v3 preview is
  `7e6b943cf31d5de1d28b438836b51f91134070158b4b9ccdb3a8556bf7ddad34`.
  A repeat build produced identical SF2, SFZ, MIDI, preview-WAV, decision and
  sample-tree hashes. The original v3 tree remained byte-for-byte unchanged.
- Listening result: the reviewer heard lower event 13 and upper event 25 as
  different sounds. Event 25 alone retained the same tone at every velocity,
  so the reviewer explicitly selected the upper event only.
- Decision: accept event 25 as the sole MIDI-35 source in this experimental v3.
  Do not retain event 13 as a velocity layer. Keep the embedded v2 baseline and
  the earlier context-reviewed v3 available for rollback and comparison.
- Problems/risks: one sample preserves identity but cannot reproduce true
  acoustic velocity-dependent timbre; FluidSynth remains a proxy for final
  GarageBand/AUSampler listening. Stem bleed and room/effect character remain
  baked into the extracted event.
- Next smallest step: compare source, v2 and single-event v3 performance renders
  in context, then repeat this explicit identity-versus-dynamics review only
  for another accepted layer candidate with genuinely similar timbre.

### 2026-07-17 — Velocity-layer mapping review v2

- Goal: represent the listener's real decision—whether two samples belong in
  one velocity-layered instrument at all—instead of forcing every answer to be
  a numeric boundary.
- Change or experiment: upgraded the boundary-review schema to v2. Every unit
  now offers lower event only, upper event only and the existing layered
  boundaries. A fixed-velocity repeated two-bar beat renders both individual
  events at identical pitch, velocity and rhythm before one common velocity
  ramp tests every complete mapping. The page reports actual source-MIDI
  velocities and flags a lower or upper zone that the song cannot trigger.
  Apply may deactivate one already accepted event, but cannot introduce a new
  event, modify sample audio or edit source MIDI. Legacy v1 exports are refused.
- Inputs: the unchanged Lidl `other_kit` context-reviewed v3; MIDI 35; lower
  event 13, upper event 25, current split 116 and user feedback that pitch,
  tone and texture changed between the two sources.
- Model/runtime/checkpoint: no learned model. Deterministic MIDI/SF2 generation,
  FluidSynth rendering and SHA-256 validation only.
- Evidence and metrics: source MIDI 35 uses velocities 102, 107, 109, 110, 111,
  112, 114, 116, 119 and 120. The old boundary-124 choice therefore made the
  125–127 upper zone unreachable and acted implicitly like lower-event-only.
  v2 presents ten mappings and 34 pinned files. Both tone previews use velocity
  111; repeated-beat MIDI SHA-256 is
  `f78e1be6225610f5c2c710f42385bf2c5736eb9cbd9c68dcc3040adee2d621a7`.
  Lower/upper tone WAV hashes are
  `51a85006afe92da375b7afc736341caf3e401a29bd5abfdb027acc556050140e`
  and `4bfe51b380701a4bfafa145b64132d2ffa9160fa8a8b9b10cf64081e8c0fc904`.
  The complete manifest SHA-256 is
  `2d62857062aeeadedb768ca9b968921273d1e7a661cf83ea61e352f56e7405b5`.
- Listening result: the first review found the two events perceptually unlike;
  choosing the final boundary was a sensible way to minimise the switch, but
  it exposed that “no layer” was missing from the decision surface.
- Decision: supersede the un-applied v1 export with a fresh unreviewed v2 page.
  Do not infer lower-event-only; let the user choose it explicitly after the
  equal-velocity comparison.
- Problems/risks: both extracted events are individually peak-normalised, so
  the equal-velocity test deliberately emphasises timbre/envelope identity.
  A real acoustic velocity layer can become brighter or harder, but an obvious
  instrument or pitch-identity change still argues for one source event.
- Next smallest step: collect the v2 mapping export and rebuild a fresh v3. If
  lower-event-only is selected, verify one MIDI-35 zone, no velocity sweep,
  one deactivated accepted event and unchanged source MIDI/sample WAV hashes.

### 2026-07-17 — Explicit sampler boundary review v1

- Goal: turn an audible velocity-layer transition question into a deliberate
  listening decision without treating “carry on” as approval to move the
  reviewed MIDI-35 boundary or replace either accepted sample.
- Change or experiment: added `sample-pack-boundary-review` and
  `sample-pack-boundary-apply`. Review rebuilds candidate SF2/AUSampler banks
  around each accepted two-layer split and renders one identical unit-specific
  velocity sweep through every bank. It labels but never preselects the current
  boundary. Apply accepts only a complete user export, validates its manifest
  and regenerates the full v3 pack from the original reviewed sample choices
  with only the chosen boundary overrides.
- Inputs: unchanged Lidl `other_kit` context-reviewed v3; MIDI 35; accepted
  low event 13, high event 25 and current boundary 116.
- Model/runtime/checkpoint: no learned model. Deterministic MIDI/SF2 generation,
  FluidSynth listening renders and SHA-256 evidence only.
- Evidence and metrics: the review offers boundaries 96, 100, 104, 108, 112,
  116, 120 and 124. Every candidate uses the same 29-hit MIDI velocities 32,
  48, 64, 80, 95–97, 99–101, 103–105, 107–109, 111–113, 115–117,
  119–121, 123–125 and 127. The seed is `unreviewed`, selected boundary is
  null, effects are all zero and 25 candidate MIDI/SF2/AUSampler/WAV artifacts
  are pinned by manifest SHA-256
  `8cafd80b6e8976c8deed5bfe1229c074533979a793e83823bfde1bd39133f84e`.
  Source v3 report SHA-256 remains
  `b183861f3bdd8eb44c1ec74506a3f7f90e8572a1c03b1d76e2a5cc7458b63005`;
  its reviewed sample decision SHA-256 remains
  `686b7ec1aec40b4058362f57dfe67f9a55c20134e9476a9e1165f0204d17b9da`.
- Listening result: open. The reviewer should prefer a candidate whose quiet-
  to-loud sweep changes naturally in level and timbre, and may explicitly keep
  116 if it remains best.
- Decision: hand off the unreviewed HTML. Do not build a boundary-adjusted v3
  until the user exports `sample_boundary_review.reviewed.json`.
- Problems/risks: velocity controls both sample selection and playback level,
  so boundary choice remains perceptual. FluidSynth is a proxy; the generated
  `.aupreset` plus shared MIDI supports a final AUSampler comparison.
- Next smallest step: collect the explicit boundary export, apply it to a fresh
  v3 pack and compare source/v2/new-v3 real-performance and sweep artifacts.

### 2026-07-17 — Reviewed velocity-layer sweep v1

- Goal: expose whether the accepted Lidl MIDI-35 sample switch at velocity 116
  sounds natural, without automatically moving the boundary or replacing
  either user-selected event.
- Change or experiment: `sample-pack-apply` now creates an audit-only velocity
  sweep whenever a review accepts a two-layer unit. It plays coarse dynamics
  plus dense steps at boundary −8/−4/−2/−1, the exact boundary, and
  +1/+2/+4/+8, clamps to valid MIDI values and removes duplicates. The same
  MIDI is rendered through the v2 one-sample bank and reviewed v3 bank.
- Inputs: context-reviewed Lidl `other_kit`; MIDI pitch 35; accepted events 13
  and 25; reviewed low/high ranges 0–116 and 117–127.
- Model/runtime/checkpoint: no learned model. Deterministic MIDI generation and
  the existing FluidSynth/SF2 A/B renderer only.
- Evidence and metrics: the 119 BPM sweep contains 16 hits at velocities 32,
  48, 64, 80, 96, 104, 108, 112, 114, 115, 116, 117, 118, 120, 124 and 127.
  Both renders are 7.885 seconds. The sweep MIDI SHA-256 is
  `b542f1f9d7f4cc0467aece91bb06e670d65c31a6005f31c569ee6029dd29c4c4`;
  v2 WAV is
  `68a275fb982062bce4057021deb81aa9e62054ed287b3a4e6bf6e41a2a985740`;
  v3 WAV is
  `b1fbd95195b4fee5bae3097dd88b07a89a3ad6a6b7672159263a8a008cbdbe50`.
  Independent builds reproduced these and all preceding performance artifacts
  byte-for-byte. Mapping and source-sample change counts remain zero.
- Listening result: open. The critical adjacent hits are velocity 116 on event
  13 followed by velocity 117 on event 25.
- Decision: ship the sweep as an audit artifact only. Preserve the reviewed
  116 boundary until the user explicitly reports that another transition is
  musically preferable.
- Problems/risks: MIDI velocity simultaneously changes playback level and
  selects the sample, so a perceived jump can combine loudness and timbre.
  FluidSynth is a proxy for AUSampler, making the GarageBand preset comparison
  the final decision surface.
- Next smallest step: collect the v2/v3 transition preference. If 116→117 is
  unnatural, implement a separate hash-pinned boundary-choice review and apply
  workflow rather than silently tuning a threshold.

### 2026-07-17 — Real-performance sampler A/B v1

- Goal: judge a reviewed percussion rack with musical evidence rather than
  relying on isolated events or a sequential note-per-zone test.
- Change or experiment: `sample-pack-apply` now retains the zone audit and
  additionally selects a representative real-MIDI excerpt. It searches
  bar-aligned 8-, 12- and 16-bar windows, stops at the shortest window covering
  every source pitch, and otherwise maximises pitch coverage, note density and
  then earliest position. The excerpt is shifted to bar 1 and channel 1 for
  AUSampler without pitch, velocity or rhythm edits. It publishes one source
  stem reference and identical v2/v3-bank renders.
- Inputs: the context-reviewed Lidl `other_kit` v3 decision, its 194-note
  source MIDI and authorised source stem.
- Model/runtime/checkpoint: no learned model. Clip v1 performs deterministic
  MIDI import/export; FluidSynth renders the two local sample banks.
- Evidence and metrics: the shortest complete-palette window is 12 bars,
  source beats 112–160 or 56.470624–80.672320 seconds at 119 BPM. It contains
  50 notes, all 11 rack pitches and velocities 52–120. Source channel 10 is
  changed only in the audition copy to channel 1 for the custom bank. The
  source MIDI reports zero pitch/velocity mutations and retains SHA-256
  `de5926a88993b1e0af29724363b924e9c42c275249662403131765d980fd3155`.
  Source, v2 and v3 WAV durations are 24.202, 26.124 and 26.124 seconds; the
  latter include sampler release tails. Independent builds produced identical
  source WAV (`a5b5b860678a6a38cae7eb651cd87b691de8c3be4e993b215d7f8f54be6adeb1`),
  MIDI (`49a676dbfb643079a6eb8d3afcfc2c0ae8883a37966fc88e6b0033679bdb05d9`),
  v2 WAV (`d8d819ddc88abe0b8509a9a748b450975aa6ef546e7bec4d8adf548415341651`)
  and v3 WAV (`e6bdac6aa05161f91c8b3bcd075db8e5d2d99c1ec0cdb3f089f0bb37d6effeae`).
- Listening result: open. The three files are the first direct source-versus-
  conservative-bank-versus-reviewed-bank musical comparison.
- Decision: add this performance comparison to every reviewed v3 output while
  retaining the sequential zone audit. It is an audition artifact only and
  cannot promote v3, edit the original MIDI or imply that all source timbre is
  captured by one sample per zone.
- Problems/risks: a 12-bar density/coverage window is representative of the
  MIDI pitch palette, not necessarily the song's most recognisable section.
  Source and sampler levels differ, and rendered banks have longer release
  tails. Channel 1 is required because the generated SF2 is a melodic bank,
  even for a percussion rack.
- Next smallest step: collect the user's source/v2/v3 preference and whether
  the velocity-116 layer transition is natural. If not, add a reviewed boundary
  adjustment rather than changing it automatically.

### 2026-07-16 — Context-reviewed Lidl percussion rack v3

- Goal: apply the first user decision made with isolated, source-context and
  repeated-beat evidence, without changing the conservative v2 bank or
  inventing alternates the reviewer did not select.
- Change or experiment: validated the exported v6 review against all 63 pinned
  WAVs and applied its exact choices to a fresh Sample Instrument v3 with a
  common GarageBand audition, v2/v3 renders and embedded v2 rollback.
- Inputs: authorised user-written Lidl `other_kit` pack; reviewed export
  SHA-256
  `686b7ec1aec40b4058362f57dfe67f9a55c20134e9476a9e1165f0204d17b9da`;
  contextual manifest SHA-256
  `4a18bb8c8b186c98f0300cd712734833219d46d4cba4816ea2c38ce076a1d7a0`.
- Model/runtime/checkpoint: no learned model. Selection is entirely the user's
  explicit local listening review; rendering uses the existing FluidSynth
  path only for A/B previews.
- Evidence and metrics: four units were accepted and two rejected. MIDI 35
  uses event 13 for velocities 0–116 and event 25 for 117–127. MIDI 40 uses
  event 44, MIDI 42 uses event 39, and MIDI 50 uses event 12. The competing
  MIDI-42 family and MIDI 48 were rejected. Five reviewed events replaced four
  v2 roots; zones changed 11→12 solely because of the accepted velocity split.
  MIDI notes and velocities changed by zero, no alternate event was accepted,
  and no round robin or GarageBand alternate bank was generated. The reviewed
  SF2 SHA-256 is
  `abd7131c27bf7d29828ddcaaaa8e3b0cd7c6a4f29b7e88c8e63aa6ce56e2bbeb`;
  the embedded baseline remains
  `55085be93289608810cceb33d02b7d1ef49c85e1caa963b8529663fb6c01a8b2`.
  Independent builds produced byte-identical SF2, SFZ, audition MIDI, v2/v3
  preview WAVs and all five extracted source WAVs.
- Listening result: the explicit review accepted a broader four-note
  percussion palette than the earlier one-event review and selected the only
  proposed two-level unit. The user's reasons are represented by the choices;
  no automatic interpretation or relabelling was added.
- Decision: publish this as a separate context-reviewed challenger. Keep v2
  embedded and authoritative until the user compares the two presets in the
  full song. Do not add round robin because no alternate checkbox was accepted.
- Problems/risks: the velocity boundary of 116 gives the louder sample a
  narrow 117–127 trigger range; that is the reviewed proposal but may need a
  later musical boundary review in GarageBand. Samples still contain any
  source bleed, effects and transitions present in their 0.208-second events.
- Next smallest step: compare the common audition and then the real
  `other_kit` MIDI through the v2 and context-reviewed AUSampler presets. Record
  whether the MIDI-35 layer transition and the four replacements improve the
  full percussion rack before changing a default or threshold.

### 2026-07-16 — Role-aware contextual sample auditions v1

- Goal: make advisory sampler candidates recognisable to a listener who cannot
  reliably distinguish similar 0.13–0.21-second one-shots in isolation.
- Change or experiment: retained the exact normalised event WAV and added two
  pinned views per candidate. A four-beat source excerpt uses one shared
  stem-level gain to retain relative dynamics, nearby rhythm and bleed. A
  normalised role audition uses a repeated two-bar beat for drum/percussion
  roles or a short sampler-resampling pitch phrase for pitched roles. The HTML
  labels all three, and apply verifies their manifest before accepting a
  reviewed document.
- Inputs: authorised user-written Lidl `other_kit` Sample Instrument v2, its
  119 BPM aligned MIDI and the same six-unit/21-event review set used for the
  first heard v3 decision.
- Model/runtime/checkpoint: no learned model and no external renderer. Context
  audio is deterministic local PCM24; pitched phrases emulate sampler playback
  through deterministic resampling.
- Evidence and metrics: the fresh page contains 21 isolated one-shots, 21
  source-context excerpts and 21 repeated-beat auditions (63 pinned WAVs,
  about 19 MB). Source contexts are 2.017 seconds; repeated beats are
  4.172–4.243 seconds. Original-level context peaks span 0.1887–0.8900 while
  isolated/role auditions use a 0.8900 comparison peak. Two independent builds
  produced byte-identical WAVs and manifest SHA-256
  `4a18bb8c8b186c98f0300cd712734833219d46d4cba4816ea2c38ce076a1d7a0`.
  JavaScript syntax, focused tests and the unchanged zero-effect audit pass.
- Listening result: the user reported hearing many different percussion
  sounds and judged that variety potentially representative of `other_kit`.
  This supports treating the stem as a multi-sound percussion palette rather
  than forcing every mapped note to resemble one physical instrument.
- Decision: preserve timbral diversity and make musical usefulness the review
  question. Do not merge families, relabel MIDI pitch as acoustic pitch or
  infer acceptance from the new auditions.
- Problems/risks: a repeated beat repeats one candidate recording and is not a
  reconstruction of the surrounding source performance. The source-context
  player identifies the target by its recorded offset rather than adding an
  audible marker. Pitched resampling changes sample duration like a basic
  sampler and does not model a sophisticated instrument.
- Next smallest step: collect listening feedback from the new Lidl page. If
  individual sounds remain difficult to place, add a separate post-build
  multi-pitch percussion-rack groove without changing the source-event review
  contract.

### 2026-07-16 — First heard Lidl Sample Instrument v3

- Goal: apply the user's completed `other_kit` listening review without
  inferring any additional musical choices, then prove that the resulting
  instrument and rollback are reproducible.
- Change or experiment: applied the exported reviewed JSON to a fresh v3
  directory, corrected v3 reporting so proposed-but-rejected velocity layers
  and alternates are not described as active, and added a regression test for
  the one-primary/no-layer/no-alternate case.
- Inputs: the authorised user-written Lidl `other_kit` Sample Instrument v2
  and reviewed export SHA-256
  `4a5d336209efb9a8ea477fbbf809ba4eb57686d29a48ee6fe337496e75c151fa`.
- Model/runtime/checkpoint: no learned model. This remains an explicit human
  listening gate over deterministic source-event evidence.
- Evidence and metrics: the user accepted only unit `I1-P050-A1`, primary
  event 10 at MIDI pitch 50, and rejected the other five units. The build
  extracted one 0.209-second source event, retained 11 SF2 zones before and
  after, changed zero MIDI notes or velocities, produced zero velocity-layer
  units, zero round-robin layers and zero GarageBand alternate banks, and
  embedded the unchanged baseline SF2 SHA-256
  `55085be93289608810cceb33d02b7d1ef49c85e1caa963b8529663fb6c01a8b2`.
  Two fresh builds produced byte-identical reviewed SF2, SFZ, audition MIDI,
  v2/v3 WAV previews and extracted event WAV. The reviewed SF2 SHA-256 is
  `4ad6450d7275fea863a72cc7c6f83ef867baa8926a4b15d487208d111c7bd448`.
- Listening result: the reviewer found the isolated 0.13–0.21-second drum
  excerpts difficult to distinguish because they sounded like similar short
  thuds. One source event was recognisably useful; the remainder were rejected.
- Decision: preserve that exact choice as a one-sample replacement. Do not
  apply the proposed two-level unit, alternates or any inferred instrument
  identity. A feature is now reported as active only when the reviewed choices
  actually activate it.
- Problems/risks: isolated one-shots hide rhythmic role, consistency and bleed
  in musical context. A mixed residual `other_kit` stem is not one physical
  instrument, and MIDI pitch 50 is a sampler mapping rather than proof of a
  high tom.
- Next smallest step: add role-aware contextual review auditions: repeated
  beats and source-rhythm comparisons for drum/percussion units, and short
  scale/phrase auditions for pitched instruments, while retaining the exact
  one-shot evidence and explicit review gate.

### 2026-07-16 — Phase 3 reviewed Sample Instrument v3 gate

- Goal: let heard and explicitly accepted source-event candidates improve a
  sampler without silently promoting advisory level groups or making the v2
  instrument difficult to recover.
- Change or experiment: added `sample-pack-review`, which extracts exact local
  listening WAVs and an unreviewed HTML/JSON decision page, plus
  `sample-pack-apply`, which accepts only a complete reviewed document. Apply
  creates a separate velocity-layered SF2/AUSampler bank, sequence-round-robin
  SFZ, separate alternate SF2/AUSampler A/B banks, shared audition MIDI/WAVs,
  mutation audit and embedded v2 rollback. Portable SF2's lack of round-robin
  selection is recorded rather than hidden.
- Inputs: a deterministic synthetic two-dynamic/16-event kick fixture for apply
  tests, plus the authorised user-written Lidl `other_kit` Sample Instrument v2
  for the real unreviewed listening handoff.
- Model/runtime/checkpoint: no learned model. The gate consumes the existing
  explainable source-event cluster and dynamics evidence.
- Evidence and metrics: the Lidl page contains six review units, one possible
  two-layer unit, seven alternate sets and 21 pinned event-audio excerpts. It
  records zero baseline, MIDI or SoundFont changes because no musical choice
  has yet been made. Two fresh Lidl review builds produced byte-identical 21
  WAV evidence sets and manifest SHA-256
  `aefccc3f2c15394b37e52bdf211c856597f5a29606968d21c34f6dd42ef06973`.
  The synthetic accepted fixture produced two SF2 velocity
  zones from one v2 zone, four reviewed event WAVs, true two-event SFZ sequence
  round robin, one alternate GarageBand bank and byte-identical main SF2/SFZ
  hashes on a fresh repeat.
- Listening result: intentionally open. No Lidl unit was accepted or rejected
  by the implementation; the page is the handoff for user judgement.
- Decision: keep v2 as the default. Refuse unreviewed/incomplete choices,
  unknown event indices, multiple accepted units at one pitch and any changed
  source, MIDI, v2 report/sample/SF2, cluster/dynamics or review-audio file.
- Problems/risks: source excerpts can still contain bleed, effects or phrase
  transitions; a level split can still reflect mixing; and AUSampler requires
  separate A/B banks instead of automatic round robin.
- Next smallest step: listen to the six Lidl units, export a reviewed document
  and build the first real v3 A/B only if at least one proposal is recognisably
  useful. Use that listening result before changing thresholds or defaults.

### 2026-07-16 — Phase 3 advisory dynamics and alternate samples v1

- Goal: identify repeated source events worth auditioning as quiet/loud layers
  or round-robin alternatives without letting a source-level split rewrite MIDI
  expression or silently expand a sample instrument.
- Change or experiment: added deterministic analysis within the intersection of
  candidate timbre family, existing MIDI pitch and articulation. A two-layer
  unit needs at least eight events, at least four and 20% of the unit per
  layer, and at least 3 dB median RMS separation. An alternate set needs three
  isolated events; it selects the medoid plus diverse central examples while
  excluding the most distant 20%. Matching, Sample Instrument v2 and
  Instrument Bundle v1 retain JSON and SVG evidence with explicit all-zero
  mutation effects.
- Inputs: the authorised user-written full Lidl `other_kit` stem and its
  194-note listened repair MIDI. The sample-pack handoff used its existing
  conservative 48-event analysis ceiling; the bundle handoff used the Lidl
  kick fixture.
- Model/runtime/checkpoint: no learned model. The analysis uses the existing
  explainable source-event timbre, articulation, RMS and isolation evidence.
- Evidence and metrics: the full mixed-kit run produced 28 comparable units,
  five two-layer candidates, 20 alternate-sample sets, 60 candidate events and
  two retained/unassigned outliers among 194 events. The real sample pack kept
  its existing 11 single-velocity zones while retaining one layer candidate
  and seven alternate sets from the 48 analyzed events. The kick Instrument
  Bundle recipe carries its match-side dynamics report and graph. Two fresh
  full mixed-kit runs produced byte-identical dynamics JSON SHA-256
  `afdec6f5b32074adbcbc65273c63a66677fe88e2601ef4e378ecf04aabc05b90`
  and SVG SHA-256
  `4edc60014fd76790439ee65c18db863bb381a6e3c0ad1ccc723ca2b13921ef74`.
- Listening result: open. The timeline clearly exposes candidate groups and
  exact source-event indices; it deliberately does not assert that apparent
  level groups are real separately recorded dynamics.
- Decision: ship discovery only as additive review evidence. Record zero MIDI
  note/velocity changes, zero sample additions/removals, zero SoundFont-zone
  changes and no drum-family change. Do not call a candidate a valid layer or
  round robin until its indexed excerpts have been compared by ear.
- Problems/risks: MIDI velocity already uses source energy and is therefore not
  independent evidence; bleed, room sound, phrase context or section-level mix
  changes can create a false split; and alternate events can preserve unwanted
  transitions even after centrality filtering.
- Next smallest step: add an explicit reviewed-sampler experiment that applies
  only user-accepted event indices to a new Sample Instrument v3 copy, with an
  A/B audition and rollback path. Do not alter the v2 default.

### 2026-07-16 — Phase 3 conservative GM drum-family proposals v1

- Goal: distinguish real kick, snare, hat, cymbal, tom and mixed-percussion
  sounds without treating MIDI pitch as acoustic pitch or silently replacing
  a repair that already classified the kit well.
- Change or experiment: added role-specific GM percussion candidates rendered
  through the configured SoundFont, explainable 80% timbre/20% articulation
  scoring, deterministic distinct-candidate assignment, assigned one-shot
  auditions and a separate channel-10 MIDI/WAV. Mapping units are the
  intersection of source timbre family and existing MIDI note, preventing a
  broad cluster from collapsing useful kit-piece labels. A valid existing role
  note changes only when a candidate scores at least 55 and leads by at least
  eight relative points. Original MIDI hashes are checked before and after.
- Inputs: authorised user-written Lidl full snare, hat, cymbals, toms and
  `other_kit` stems with newly generated repair MIDI, plus the permanent Lidl
  kick seconds 200–215 fixture and its existing 33-note repair MIDI.
- Model/runtime/checkpoint: no learned model. FluidSynth rendered the installed
  GeneralUser-GS SoundFont; every report records its path and SHA-256.
- Evidence and metrics: kick retained one persistent unit, four rare hits and
  all existing notes. Snare retained 249/249 notes across four mapping units;
  hats 484/484 across four units (15 outliers and one ceiling-retained event);
  cymbals 18/18 across three units; and toms 90/90 across eight units. Mixed
  `other_kit` retained all existing labels except two guarded experiments: 34
  note-42 events mapped to side stick and seven note-49 events mapped to cabasa,
  for 41 proposed changes among 194 notes, with two outliers retained. Every
  input MIDI before/after hash matched. Two fresh `other_kit` runs produced
  byte-identical report SHA-256
  `62d553a8e873b26bad3a43131f2d4a09df2627c9021e6d904155b5619b19a58a`,
  MIDI SHA-256
  `9bfeac77a0f9714484c078808c8728c75b62fc268fb32f39124fa0fbd169f10d`
  and WAV SHA-256
  `4439fbc9375f9757a39cd4ba5322ab4e5f266b5daab685981a6228d82fa45e9e`.
- Listening result: open. The unchanged role-specific proposals are a useful
  no-regression result. The two mixed-kit reassignments require source/proposal
  and intended-GarageBand-kit A/B before either is accepted.
- Decision: integrate only as review-required additive evidence. Keep
  `performance.mid` and the supplied MIDI authoritative; put the proposal and
  its WAV in `matches/` and bundle `previews/`. Call 55/eight-point rules policy
  guardrails rather than confidence calibration.
- Problems/risks: SoundFont kit pieces differ from GarageBand kits; separator
  bleed can form coherent families; the 512-event ceiling can leave a small
  number of hits unanalyzed; and mixed-kit candidates remain especially easy
  to mislabel even when their relative feature score is strong.
- Next smallest step: listen to the retained mixed-kit A/B in GarageBand. If
  useful, add velocity-layer and round-robin evidence inside an accepted drum
  mapping unit without changing its note assignment automatically.

### 2026-07-16 — Phase 3 source-event clustering v1

- Goal: expose when one nominal stem contains several timbres, articulations or
  separator artefacts without automatically deleting musically useful events.
- Change or experiment: added deterministic robust-distance/k-medoids candidate
  timbre families, independent articulation grouping, retained nearest-neighbour
  outliers, per-event/medoid JSON and an SVG pitch/timeline. Matching uses
  source-rate excerpts; sample packs mark selected events. Instrument Bundle v1
  carries both reports. Optional OpenL3 contributes 30% identity distance while
  explainable features retain 70%.
- Inputs: a 13-event synthetic two-family/two-articulation fixture with one
  deliberate outlier, plus the authorised user-written Lidl bass seconds
  200–215 and its aligned 20-note repair MIDI.
- Model/runtime/checkpoint: default clustering is model-free. The learned golden
  used the same pinned OpenL3 ONNX CPU checkpoint and hash recorded in the next
  log entry.
- Evidence and metrics: the synthetic fixture recovered both six-event timbre
  families, both articulation groups and the one retained outlier. On Lidl,
  explainable-only evidence found two candidate families, one articulation
  group and retained the short MIDI-39 event beginning at 8.941586s as an
  outlier. OpenL3-assisted evidence instead retained all events and found three
  candidate families of 11, 4 and 5 events with identity silhouette 0.302704.
  Two fresh learned runs produced byte-identical cluster JSON SHA-256
  `f5c151811743aed20ffc11470253005b38e6edfd602db3ae00a7b52721914f4e`,
  SVG SHA-256
  `462d5dada8bc27623304a6e2faa1c6ed2d0e8ed46040175c73ee27b38ed3bf86`
  and complete match report SHA-256
  `f8bff7cbbfd830673ab33c6cbc5162c116e66d9375d8d807f0c96cb8769330ca`.
- Listening result: open. The explainable/OpenL3 disagreement is preserved for
  review; no method is promoted from clustering metrics alone.
- Decision: integrate the report and visual as advisory evidence. Keep every
  event eligible for MIDI, matching and sampling; a rare articulation must not
  be called noise or removed without listening.
- Problems/risks: normal phrase, pitch, intensity or source-rate differences can
  create a candidate family even when one physical instrument played all notes.
  A single articulation cluster means the conservative selector found no stable
  multi-event split, not that every attack is identical.
- Next smallest step: completed by the conservative GM drum-family proposal
  increment above; continue only after listening to the mixed-kit A/B.

### 2026-07-16 — Phase 3 optional OpenL3 instrument evidence v1

- Goal: test whether a small local learned music representation can add useful
  timbre evidence without weakening the existing explainable matcher.
- Change or experiment: added an opt-in OpenL3 music/mel128/embedding-512 ONNX
  path, an explicit hash-verifying setup script, aligned one-second source and
  rendered-candidate fingerprints, a separate learned shortlist and auditions,
  complete candidate/window evidence, and additive Instrument Bundle v1 fields.
  The default ranking and behavior remain unchanged.
- Inputs: the authorised user-written Lidl bass fixture, original song seconds
  200–215, and its aligned 20-note Sunofriend repair MIDI; eight role-specific
  General MIDI bass programs rendered through the configured local SoundFont.
- Model/runtime/checkpoint: OpenL3 music mel128 embedding-512 ONNX on
  ONNX Runtime CPU; original weights CC-BY-4.0; checkpoint SHA-256
  `81c24c8a723054717fdea5c7448acb6023baaf70a0fc526deb030c2032db0ed3`.
- Evidence and metrics: all eight candidates had 15 aligned active windows.
  OpenL3 ranked Fretless Bass first at 97.589 relative cosine similarity,
  followed by Acoustic Bass at 97.511; the existing explainable score instead
  ranked Acoustic Bass first at 86.521 and Fretless Bass fifth at 82.334. Two
  fresh complete runs produced byte-identical evidence JSON SHA-256
  `83c955b6545bb1c9951e9a83b2458f8082b264965211baf963acc49dfa0d7d9a`
  and report SHA-256
  `4f169110b04333032f24839c37026a2226a91a2be93f8e9641984110c2ad59cf`.
- Listening result: open. The separate Fretless and Acoustic Bass auditions are
  retained specifically for blinded/full-mix comparison; no preference is
  inferred from the scores.
- Decision: integrate OpenL3 as optional advisory evidence only. Never download
  it during matching, accept an altered checkpoint, call cosine similarity
  confidence, blend it into the explainable score, or change the default order.
- Problems/risks: related music embeddings produce a narrow high-score range;
  the General MIDI SoundFont remains only a proxy for GarageBand patches; a
  strong timbre embedding can still miss articulation, emotion and mix fit.
- Next smallest step: listen to the retained Lidl bass A/B candidates, then add
  source-event clustering for identity/articulation/outlier evidence before
  attempting velocity layers or round robins.

### 2026-07-16 — Phase 2 explicit-choice personal ranking v1

- Goal: reduce repeated comparison effort by showing which alternative the user
  chose in similar past review units, without turning preference history into
  an automatic melody decision.
- Change or experiment: the new `melody-profile` command builds one fresh,
  deterministic local profile only from complete explicitly reviewed correction
  files. `melody-review --ranking-profile` adds a separate history panel based
  on review-unit duration, tracker agreement, selection score and combined-note
  density. Manual decisions have weight 1.0 and explicitly propagated repeated
  choices have weight 0.5. Guided child reviews inherit and hash-check the same
  profile.
- Inputs: deterministic test corrections plus a clearly labelled synthetic
  three-choice technical calibration fixture matched to the private Lidl
  30–45 second lead-vocal golden. The fixture is not a user review, listening
  result or statement of musical preference.
- Model/runtime/checkpoint: no model, checkpoint, network call or hidden
  preference store. Ranking is a deterministic nearest-context calculation over
  explicit local JSON inputs.
- Evidence and metrics: the profile contains one input, three explicit choices
  and three contextual observations, one per automatic alternative. On the
  three Lidl units, the matching artificial choices appeared history-first as
  GAME boundary, combined and Basic Pitch respectively. Two profile builds had
  identical SHA-256 `f1ef178ddd0357b04bdb032369f3daf16546c515f31f3870fbadb6129954ab39`.
  Two fresh review packages were byte-identical across 42 files. All three
  candidate orders remained `basic-pitch`, `game-boundary`, `combined`; all
  correction seeds remained unreviewed and selected `combined`; raw candidates
  remained unmodified.
- Listening result: deliberately not claimed. The synthetic fixture proves the
  immutable advisory mechanism, not that any hint matches the user's taste.
  Real calibration begins only after the user supplies actual reviewed choices.
- Decision: integrate the advisory panel and explicit profile builder. Call its
  score a relative personal-history ranking, never confidence. Reject incomplete
  reviews, duplicate input hashes, invalid propagation, changed profile hashes
  and existing output paths. Never scan for or silently update preference data.
- Problems/risks: sparse or stylistically narrow history can rank an irrelevant
  choice first, context features are deliberately small and propagated choices
  are not independent decisions. Candidate order and the combined default stay
  fixed so a misleading hint cannot silently change output.
- Next smallest step: collect genuine reviewed choices and record whether the
  history panel reduces review time or improves the final GarageBand A/B. Then
  begin Phase 3 Instrument Intelligence v2 without treating Phase 2 listening
  calibration as complete evidence.

### 2026-07-16 — Phase 2 explicit repeated-unit propagation v1

- Goal: reduce repeated listening decisions without allowing similarity scores
  to make musical choices automatically.
- Change or experiment: `melody-review` now compares every unit pair using a
  fixed conservative policy: at least three notes, exact note-count equality,
  matching absolute pitches and contour intervals, similar unit/content
  duration and onset timing within a quarter beat at p90. Accepted pairs expose
  an explicit browser button that copies only the selected alternative name;
  the target retains its own notes, timing and source evidence. The correction
  audit records the source unit, canonical pair and policy, and
  `melody-apply` rejects tampering or mismatched choices.
- Inputs: the private Lidl 30–45 second lead-vocal golden and deterministic
  synthetic positive/rejection fixtures covering exact repeats, octave
  transposition, sparse units and unequal note counts.
- Model/runtime/checkpoint: no model or checkpoint. This is a deterministic
  review-layer comparison over the immutable combined agreed-F0 MIDI.
- Evidence and metrics: the three Lidl units produced three evaluated pairs and
  zero accepted pairs; all had unequal note counts and therefore could not be
  treated as repeats. The exact synthetic repeat scored 1.000 for overall,
  pitch, interval and timing evidence. Its octave-transposed counterpart was
  rejected despite interval similarity 1.000. Two fresh Lidl packages were
  byte identical across 42 files, with 41 recorded artifacts and
  `raw_candidates_mutated: false`.
- Listening result: no Lidl selection changed because no strong repeat existed.
  Positive UI behaviour is regression-tested with synthetic repeated phrases;
  a future longer authorised golden is still needed for human A/B assessment.
- Decision: integrate pairwise suggestions and explicit propagation. Do not
  infer octave-equivalent or approximate note-count repeats in v1, do not copy
  notes between units, and invalidate dependent propagation after a manual
  source change.
- Problems/risks: the initial policy favours precision over recall and will miss
  repeated phrases with ornaments, omissions or deliberate octave changes.
  Connected repeat groups remain informational; every propagation action is
  still pairwise and explicit.
- Next smallest step: learn a local personal ranking/calibration signal only
  from explicit reviewed choices, without changing automatic candidates.

### 2026-07-16 — Phase 2 unresolved-unit short guides v1

- Goal: let a user reject all automatic melodies for one manageable review
  unit and add guidance without having to hum a complete song.
- Change or experiment: the review page now has an explicit unresolved choice.
  `melody-guide` verifies the complete parent review and tracker evidence, then
  adds a fourth alternative to one numbered unit from a short hum, whistle,
  contour, single-note rhythm or tapped rhythm. Hum-like guides contribute
  rhythm and contour; single-note and tap inputs contribute rhythm only. Every
  accepted pitch is still measured from the immutable source pYIN frames.
- Inputs: the private Lidl 30–45 second lead-vocal golden, its three-unit Phase
  2 review, and a 4.371-second unit-2 source excerpt used only as a technical
  self-guide ceiling fixture. This is not presented as a realistic humming
  result or as training data.
- Model/runtime/checkpoint: existing local pYIN/Basic Pitch stack and
  FluidSynth preview; no new model, network call or checkpoint.
- Evidence and metrics: all 41 parent artifacts were hash-verified. The guide
  detector proposed three notes and source gating accepted three at MIDI
  pitches 63, 63 and 64. Alignment offset was 5.238668 seconds, transposition
  zero and alignment score 0.988569. Only unit 2 gained `guide-assisted`; units
  1 and 3 retained exactly three alternatives. The child package contains 46
  recorded artifacts plus its manifest, and two independent builds were byte
  identical across all 47 files. The guide evaluation reported chroma 0.787
  and supported-note ratio 0.333, reinforcing that its label is not an
  automatic recommendation.
- Listening result: human recognition review remains pending. The ceiling
  fixture proves timing, evidence gating, rendering and audit flow, but cannot
  establish that an imperfect human hum will be preferable.
- Decision: integrate unresolved export and `melody-guide`; accept one guide
  and one unit per fresh run, preserve every automatic candidate, and refuse
  `melody-apply` while any exported choice remains unresolved. No-source
  evidence and tap/single-note pitch-ignoring paths have regression tests.
- Problems/risks: a guide can improve segmentation yet still be a worse
  musical abstraction, and weak pYIN regions cannot be repaired by this path.
  v1 evaluates one guide for one unit and does not yet combine guided units.
- Next smallest step: identify genuinely repeated review units and offer
  explicit propagation of an accepted choice without modifying unrelated
  phrases.

### 2026-07-16 — Phase 2 musical-length review units v1

- Goal: replace the nine short note-cluster cards in the recognition-first
  review with a smaller number of musical-scale decisions.
- Change or experiment: `melody-review` now groups consecutive immutable
  boundary clusters into configurable review units, defaulting to two-to-eight
  bars at four beats per bar. Each unit retains its original cluster indices,
  weighted agreement/selection evidence, providers, duration status and all
  three alternatives. Bar duration is derived from BPM; the implementation
  explicitly does not claim that an excerpt starts on a confirmed downbeat.
- Inputs: the private Lidl lead-vocal 30–45 second golden, B major, 119 BPM,
  A=440, and its completed boundary-repair v2 tracker run.
- Model/runtime/checkpoint: no new model. The increment is a deterministic
  review-layer transformation over the existing hashed Basic Pitch, GAME,
  pYIN and RMVPE evidence.
- Evidence and metrics: nine source clusters became three review units covering
  clusters 0–2, 3–5 and 6–8. Their content spans are 2.091, 2.167 and 2.005
  bars; none is below the two-bar preference or above the eight-bar maximum.
  Each unit retains raw Basic Pitch, GAME-boundary and combined MIDI, neutral
  audio, source overlay and evaluation. For example, unit 3 strong-onset F1
  was 0.333/0.462/0.400 respectively, while chroma was
  0.963/0.935/0.937—useful evidence that one metric still cannot choose the
  intended melody.
- Listening result: the new local page presents three longer recognition
  choices instead of nine fragmented decisions. Human selection remains
  pending. The in-app browser security policy does not permit automated
  navigation to local `file://` pages, so the page is handed off for local
  review rather than bypassing that restriction.
- Decision: integrate musical-length grouping as the `melody-review` default,
  expose `--minimum-bars`, `--maximum-bars` and `--beats-per-bar`, retain
  `phrase_count` for compatibility, and add explicit source-cluster and
  review-unit counts to the manifest and correction audit.
- Problems/risks: duration in bars is not the same as downbeat-aligned musical
  form; a confirmed downbeat is unavailable for this excerpt. Short sources or
  widely isolated clusters remain visible with an explicit warning instead of
  being stretched or joined across more than the configured maximum.
- Next smallest step: add a short hum/tap/contour guide only to a review unit
  the user marks unresolved, retaining the three automatic alternatives and
  source-pitch support rules.

### 2026-07-16 — Phase 1 optional close-out and PESTO F0 oracle

- Goal: finish every local Phase 1 engineering task and optional experiment,
  leaving only the listening decision that must be made by a person in
  GarageBand.
- Change or experiment: added a pinned, isolated PESTO 2.0.1 backend with raw
  frame and activation evidence; evaluated it on lead, backing and bass;
  extended the MuScriptor comparison to keys, kick and strings; ran all four
  optional AI backends on a deterministic silence fixture; assessed and
  rejected MT3 for this phase; and generated one local listening scorecard
  containing all required and optional A/B previews.
- Inputs: Lidl lead vocal 30–45 s, backing vocal 205–220 s, bass 200–215 s,
  keys 0–15 s, kick 200–215 s, strings 120–135 s and five seconds of digital
  silence. The private source audio and immutable outputs remain under
  `work/ai-bakeoff/`.
- Model/runtime/checkpoint: PESTO package 2.0.1 with the 534,664-byte
  `mir-1k_g7.ckpt`, SHA-256
  `16c32e06ddd950e3e4866dfa3c7f8a87c4988f8adf43e57977b189f031f26f3e`;
  the existing pinned MuScriptor, GAME and RMVPE environments were reused.
- Evidence and metrics: PESTO lead/backing/bass strong-onset F1 was
  0.103/0.333/0.182 and chroma similarity was 0.936/0.858/0.444. The existing
  specialised kick path scored 1.000 strong-onset F1 versus MuScriptor 0.985;
  MuScriptor improved keys attack F1 but reduced chroma and contour evidence,
  and was clearly worse for strings. Every optional backend emitted zero notes
  on digital silence. The repeated PESTO lead artifacts were byte-identical.
- Listening result: the prior human verdict that MuScriptor is substantially
  better than the lead baseline is recorded. Bass, backing-vocal and
  expression decisions remain deliberately unfilled in
  `work/ai-bakeoff/PHASE1_LISTENING_REVIEW.html`; optional keys, kick and
  strings checks are also available there.
- Decision: retain PESTO only as independent vocal F0 evidence and reject it
  for the current bass golden. Keep specialised kick and strings paths. Keep
  MuScriptor keys as an optional A/B candidate. Reject MT3 for Phase 1 because
  its official T5X/Colab inference stack adds substantial complexity without
  an identified advantage over the integrated MuScriptor comparison.
- Problems/risks: objective source agreement cannot decide whether a MIDI
  rendering sounds musically better, and a software agent cannot honestly
  manufacture GarageBand A/B judgments. The human review therefore remains a
  completion criterion rather than being silently waived.
- Next smallest step: complete the required rows in the local listening page,
  export `sunofriend-phase1-listening-review.json`, and record its decisions in
  this roadmap. No further model installation or engineering is required to
  close Phase 1. The close-out build passed all 300 tests, Ruff, all-backend
  diagnostics, package build and `twine check`; all 28 review audio links were
  also verified locally.

### 2026-07-16 — Recognition-first phrase review v1

- Goal: make melody correction possible by recognizing short alternatives
  instead of requiring a whole-song hum or trusting one aggregate score.
- Change or experiment: added `melody-review`; verified the completed tracker
  run, source, Basic Pitch, combined MIDI and boundary evidence hashes; ranked
  the weakest agreed-F0 regions first; rendered raw Basic Pitch, GAME-boundary
  and combined MIDI plus source overlays; added small piano rolls, explicit
  per-phrase radio choices and reviewed JSON export. `melody-apply` now refuses
  an unreviewed/incomplete phrase document or source-hash mismatch and records
  the choices in its audit. Backing runs are refused rather than collapsed.
- Inputs: the local Lidl lead-vocal seconds 30–45 golden, B major, 119 BPM,
  A=440, using the final boundary-repair v2 tracker run.
- Model/runtime/checkpoint: no new model. The package uses the existing hashed
  Basic Pitch 0.4.0, seeded GAME v1.0.3 and agreed pYIN/RMVPE evidence; neutral
  previews use the configured local FluidSynth/SoundFont.
- Evidence and metrics: nine regions each received three alternatives. The
  package contains 120 files: nine source excerpts and 27 each of MIDI,
  MIDI-only WAV, source-overlay WAV and evaluation JSON, plus the HTML,
  correction seed and manifest. GAME honestly has zero notes in three regions.
  Objective preference varies by region: for example, the 7.09–7.87 s region
  scores strong-onset F1 0.667/1.000/0.800 for raw Basic Pitch/GAME/combined,
  while raw Basic Pitch is often denser and has higher chroma. All 120 final
  v2 files were byte-identical in a fresh repeat and contain no temporary
  build paths.
- Listening result: every alternative has both isolated neutral MIDI and a
  source-plus-MIDI overlay ready in the local HTML. Actual human choices and
  GarageBand A/B preference are pending; the unreviewed seed is not presented
  as a reviewed melody.
- Decision: integrate `melody-review` as an explicit lead-only review layer,
  defaulting visually to combined but never treating it as chosen until the
  user reviews all nine regions. Keep raw evidence immutable and keep backing
  harmony outside this monophonic workflow.
- Problems/risks: several ranked regions are sub-second note clusters rather
  than musical two-to-eight-bar phrases; Basic Pitch may sound busy because it
  is raw/polyphonic; GAME has no accepted boundary in three regions; browser
  file pages must be opened locally by the user, so interaction QA is covered
  by generated-contract tests rather than uploading private audio.
- Next smallest step: collect the user's nine exported choices and GarageBand
  preference, evaluate that reviewed MIDI against the source, then use the
  explicit decisions to design repeated-region propagation and optional short
  hum/tap correction only where none of the three choices is close.

### 2026-07-15 — Agreed-F0 phrase boundary repair v1

- Goal: turn the saved independent trackers into phrase-sized melody options
  without allowing a boundary model to invent pitch or erase raw evidence.
- Change or experiment: added source- and checkpoint-hash-checked GAME input to
  `vocal-trackers`; treated raw Basic Pitch and GAME notes only as boundary
  proposals; required voiced pYIN/RMVPE pitch agreement within 70 cents,
  minimum coverage, stable pitch and supported edges; used their equal pitch
  midpoint because model confidence scales are uncalibrated. Published
  provider-specific and combined monophonic MIDI, every rejection reason and
  confidence-ranked phrases. Added hash-failure, selection, immutability and
  byte-repeat tests.
- Inputs: the same local Lidl lead seconds 30–45 and backing seconds 205–220
  goldens, B major, 119 BPM, A=440, plus their pinned RMVPE v2 frames and
  seeded GAME candidates.
- Model/runtime/checkpoint: librosa pYIN 0.11.0; Basic Pitch 0.4.0 packaged
  ICASSP 2022 ONNX SHA-256
  `2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec`;
  pinned RMVPE 0.2.3 ONNX and GAME v1.0.3 small ONNX bundle. Inference and
  repair stayed local.
- Evidence and metrics: lead received 114 proposals, accepted 42 before
  overlap selection and published 23 combined notes in nine phrases. Compared
  with the 35-note consensus, strong-onset F1 rose from 0.1481 to 0.3810;
  possible-onset F1 was 0.3396, timing p50/p95 21.73/37.50 ms, chroma 0.8872
  and supported-note ratio 0.4348. Fifteen selected lead boundaries came from
  GAME and eight from Basic Pitch. Backing received 73 proposals, accepted 14
  before selection and retained only six combined notes in two phrases;
  strong/possible onset F1 was 0.1111/0.1081 and supported-note ratio was zero.
  Sixteen evidence, MIDI and evaluation files per role were byte-identical in
  fresh repeat runs.
- Listening result: isolated variants, source overlays and 75-second source,
  raw Basic Pitch, consensus, GAME-boundary and combined sequences are ready
  for both roles. User GarageBand preference is pending.
- Decision: retain the lead combined result as an optional phrase-review
  challenger because it materially improves strong boundary matching over the
  first consensus. Do not promote it to the automatic primary. Treat the
  backing result as a negative experiment and retain raw polyphonic Basic
  Pitch, GAME/MuScriptor alternatives and the normal harmony stack.
- Problems/risks: accepted boundaries can still divide one expressive syllable
  into several notes; objective onset scores do not decide musical phrasing;
  equal pYIN/RMVPE agreement may still follow a harmonic; sparse rules lose
  too much genuine backing harmony.
- Next smallest step: expose the ranked lead phrases in the existing visual
  correction workflow with side-by-side raw Basic Pitch, GAME-boundary and
  combined auditions, then capture the user's selections as reviewed edits.

### 2026-07-15 — Independent core trackers and consensus v1

- Goal: expose pYIN and Basic Pitch on the same immutable evidence contract,
  then test whether a first time-aligned pYIN/Basic Pitch/RMVPE consensus adds
  useful melody evidence without erasing any tracker result.
- Change or experiment: added `vocal-trackers`; versioned and hashed raw pYIN
  frames and decoded notes; retained raw Basic Pitch events and its exact ONNX
  hash; required RMVPE's adjacent completed run and matching source SHA-256;
  recorded every aligned observation, agreement, solo, dispute and
  no-agreement decision; emitted separate MIDI/evaluation files and an
  experimental consensus. Added three-tracker, source-hash, immutability and
  byte-repeat tests.
- Inputs: the same local Lidl lead seconds 30–45 and backing seconds 205–220
  goldens, B major, 119 BPM, A=440, plus their existing RMVPE v2 frames.
- Model/runtime/checkpoint: librosa pYIN 0.11.0; Basic Pitch 0.4.0 packaged
  ICASSP 2022 ONNX SHA-256
  `2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec`;
  the previously pinned RMVPE 0.2.3 ONNX and hash. All inference stayed local.
- Evidence and metrics: lead pYIN/Basic Pitch/consensus produced 12/71/35
  notes. Their possible-onset F1 was 0.0211/0.4058/0.2542, chroma was
  0.8477/0.9323/0.9253, and supported-note ratio was
  0.2500/0.6197/0.3714. Lead consensus contained 631 agreement, 299
  no-agreement, one solo and 361 unvoiced frames. Backing produced 16/52/14
  notes; strong-onset F1 was 0.2609/0.3733/0.2727, while consensus pitch
  support collapsed to zero supported notes. Backing consensus contained 487
  agreement, 119 disputed, 103 no-agreement, 37 solo and 546 unvoiced frames.
  All nine evidence, MIDI and evaluation artifacts per role were byte-identical
  in fresh repeat runs.
- Listening result: isolated previews, source overlays and source-then-pYIN-
  then-Basic-Pitch-then-consensus auditions are ready for both roles.
- Decision: preserve raw Basic Pitch as the strongest evidence candidate on
  both goldens. Keep pYIN as the continuous baseline and RMVPE as an
  independent contour/alternate-voice oracle. Keep consensus v1 explicitly
  `review-required`; do not add it to the automatic vocal workflow. A single
  monophonic vote is particularly unsuitable for the backing harmony stack.
- Problems/risks: raw Basic Pitch can be polyphonic and dense, so its stronger
  objective score does not prove the best playable lead abstraction. Tracker
  confidence values are not calibrated to each other. A majority can follow a
  harmonic or a different real backing voice.
- Next smallest step: use the saved alignment to rank phrase-sized consensus
  regions and test a conservative repair that only borrows Basic Pitch/GAME
  note boundaries where pYIN and RMVPE agree on pitch; never replace the raw
  candidates or the polyphonic backing stack.

### 2026-07-15 — RMVPE immutable F0 challenger

- Goal: add a genuinely independent frame-level vocal pitch tracker on the
  same lead and backing goldens before attempting multi-model consensus.
- Change or experiment: pinned `rmvpe-onnx==0.2.3`; added a separate,
  hash-verifying model setup action; made `ai-doctor --require rmvpe` check
  both software and the exact checkpoint; added offline worker inference,
  path-confined `rmvpe.frames.json` evidence, and a deterministic
  frame-to-note v1 adapter with confidence, smoothing, short-gap, pitch-change
  and minimum-duration controls. Added immutable-artifact security tests,
  synthetic vibrato/rest decoder tests and standalone CLI routing.
- Inputs: local Lidl lead-vocal fixture from original song seconds 30–45 and
  backing-vocal fixture from seconds 205–220, B major, 119 BPM, A=440.
- Model/runtime/checkpoint: MIT `rmvpe-onnx` 0.2.3 adapter on ONNX Runtime
  1.27.0 CPU; MIT-labelled `lj1995/VoiceConversionWebUI` checkpoint revision
  `b2c8cae96e3b05de46d36c5ef9970ef6cbccafba`, SHA-256
  `5370e71ac80af8b4b7c793d27efd51fd8bf962de3a7ede0766dac0befa3660fd`;
  authors' reference implementation Apache-2.0. The 361,688,443-byte model is
  external and inference rejects URLs.
- Evidence and metrics: both lead and backing repeats produced byte-identical
  raw frames, candidates and MIDI. Lead produced 1,501 frames, 1,096 raw voiced
  frames and 44 notes; it passed the quality gate and scored strong/possible
  onset F1 0.2222/0.3622, timing p50/p95 25.04/37.03 ms, chroma 0.9339, mean
  pitch support 0.3089, supported-note ratio 0.4091, octave accuracy 0.2500,
  contour direction 0.7209 and contour correlation 0.1674. Backing produced
  1,501 frames, 782 raw voiced frames and 21 notes; its corresponding values
  were 0.2353/0.2022, 20.34/32.06 ms, 0.8591, 0.0723, 0.0952, 0.0476, 0.6500
  and 0.4353. It selected upper MIDI 70, 71 and 75 in addition to the shared
  dominant-line vocabulary, which may represent another backing voice or a
  harmonic.
- Listening result: source-plus-RMVPE overlays and source, MuScriptor, GAME,
  RMVPE sequential auditions were rendered for both goldens; preference is
  pending.
- Decision: retain RMVPE as an independent contour and alternate-voice oracle.
  Its lead chroma and contour direction are valuable, but its v1 decoded
  boundaries are not competitive; the backing result is not a replacement for
  either dominant line or the polyphonic harmony stack. Do not add a normal
  vocal-workflow flag or consensus yet.
- Problems/risks: RMVPE estimates F0, not notes; any MIDI boundary is therefore
  adapter policy. Polyphonic backing material can make it jump between voices
  or harmonics. The first parallel cold start took about 25.5 seconds, while
  warm repeats took about 2.65 seconds. The package's audio dependencies need
  explicit Python-3.12-compatible NumPy/Numba pins.
- Next smallest step: publish Basic Pitch and pYIN as separately evaluated raw
  candidates on these clips, then design a time-aligned consensus that uses
  RMVPE frames without erasing any model's independent evidence.

### 2026-07-15 — Backing-vocal GAME trial and opt-in integration

- Goal: determine whether GAME generalises beyond the lead-vocal golden and,
  if it does, make it usable without displacing the deterministic melody,
  MuScriptor or the polyphonic harmony stack.
- Change or experiment: ran two seeded GAME trials on the existing backing
  fixture, evaluated them against all three existing candidates, regenerated
  the identical MuScriptor MIDI with source-derived expression, prepared fair
  overlays and sequential auditions, refactored the model publication path,
  and added `vocal-melody --game` with language, seed, threshold, radius,
  D3PM-step, model, Python and timeout controls.
- Inputs: local Lidl backing-vocal fixture from original song seconds 205–220,
  B major, 119 BPM, A=440.
- Model/runtime/checkpoint: GAME v1.0.3 small ONNX on CPU, bundle SHA-256
  `0d1d57f0bdae5764d8bcff59561ecd26d93bc654548979bc20ac2a8aad0f38b9`,
  English language ID, official thresholds, eight D3PM steps and seed 0.
- Evidence and metrics: both runs produced byte-identical raw JSON and MIDI.
  GAME emitted 21 voiced notes from 23 regions, passed the quality gate and
  used the same four rounded pitches as MuScriptor. GAME scored strong/possible
  onset F1 0.5098/0.4045 versus MuScriptor 0.2439/0.2025 and the harmony stack
  0.3273/0.2796. MuScriptor retained better timing p50/p95 (11.45/24.77 ms
  versus GAME 16.25/34.98 ms), chroma (0.9023 versus 0.8753), contour direction
  (0.9000 versus 0.6500) and contour correlation (0.9085 versus 0.4955). The
  integrated command reproduced GAME's 21 notes, recorded all 21 as observed
  policy-confidence events, retained floating source pitch in provenance and
  recovered 14 distinct velocities from 42 to 116.
- Listening result: source-plus-model overlays, a 31-second
  MuScriptor-expression-then-GAME-expression A/B and a 79-second source,
  dominant, harmony, MuScriptor, GAME sequence are ready; preference remains
  pending.
- Decision: expose GAME as an opt-in monophonic vocal challenger because it
  materially improves boundary coverage on a second vocal role. Keep
  MuScriptor as a separate contour/timing alternative and keep the harmony
  stack as the only polyphonic backing-vocal representation. Never merge or
  promote these automatically.
- Problems/risks: backing-vocal harmonics still make absolute pitch/octave
  support unreliable; GAME may over-segment a phrase that MuScriptor expresses
  as one sustained note; the best boundary choice remains a listening decision.
- Next smallest step: install and evaluate RMVPE as an independent frame-level
  F0 tracker on the same two vocal goldens before designing any multi-model
  consensus.

### 2026-07-15 — GAME vocal boundary and pitch challenger

- Goal: add the first independent singing-specific note tracker so vocal
  boundaries and floating pitch can be compared with MuScriptor and the
  deterministic contour pipeline.
- Change or experiment: pinned GAME v1.0.3 and its official small ONNX release;
  added ONNX Runtime and Soxr to the isolated worker; implemented explicit
  local-bundle resolution, per-component hashing, English/universal language
  hints, D3PM boundary controls, voiced/unvoiced adaptation, floating-pitch
  candidates, seed recording, quality checks and source-expression MIDI.
- Inputs: the same local 15-second Lidl lead-vocal fixture from original song
  seconds 30–45, B major, 119 BPM, A=440.
- Model/runtime/checkpoint: GAME v1.0.3 small ONNX on CPU; bundle SHA-256
  `0d1d57f0bdae5764d8bcff59561ecd26d93bc654548979bc20ac2a8aad0f38b9`;
  ONNX Runtime 1.27.0; Soxr 1.1.0; English language ID; official thresholds;
  eight D3PM steps; seed 0.
- Evidence and metrics: two fresh seeded runs produced byte-identical raw JSON
  and MIDI. The selected 1.71-second run emitted 43 monophonic voiced notes
  from 48 regions and passed the quality gate. Against the source it scored
  strong-onset F1 0.4839, possible-onset F1 0.4762, timing p50/p95 22.25/36.34
  ms, chroma 0.9204, mean pitch support 0.3111, supported-note ratio 0.4884,
  octave accuracy 0.3256, contour-direction accuracy 0.6905 and contour pitch
  correlation 0.2781. MuScriptor's corresponding values were 0.4828, 0.5246,
  9.69/28.74 ms, 0.9084, 0.2978, 0.4615, 0.3333, 0.6579 and 0.2184.
- Listening result: source-expression preview, vocal mix and sequential
  MuScriptor-then-GAME audition prepared; user preference is pending.
- Decision: retain GAME as a reproducible independent vocal challenger. It
  improves chroma, pitch support and contour evidence on this clip while
  MuScriptor retains better possible-onset coverage and timing. Do not merge or
  automatically promote either candidate before listening and cross-role
  evidence.
- Problems/risks: GAME's D3PM boundary model was non-deterministic until an
  explicit ONNX seed was set; CPU is the only exposed execution provider;
  voiced presence is a boolean threshold result rather than a probability;
  source harmonics make the objective pitch evaluator comparative, not ground
  truth.
- Next smallest step: backing-vocal evaluation and opt-in integration are
  completed in the increment above; capture the outstanding listening
  preference while RMVPE becomes the next independent frame-level F0 increment.

### 2026-07-15 — Source expression and full-mix safety gate

- Goal: add usable dynamics without changing raw MuScriptor evidence, then
  measure whether the small model is safe and semantically reliable on a full
  mix rather than an isolated stem.
- Change or experiment: added note-local attack/body energy measurement,
  per-instrument robust velocity normalisation, separate expression JSON/MIDI,
  a model-neutral density/duplicate/polyphony/label quality gate, vocal
  integration and neutral-versus-expression auditions. Reconstructed a local
  15-second full mix from the user-written Lidl stems and ran unrestricted
  MuScriptor.
- Inputs: Lidl lead vocal seconds 30–45 and a 16-stem reconstruction of the
  same passage; metronome excluded; B major, 119 BPM, A=440.
- Model/runtime/checkpoint: MuScriptor 0.2.1 small on CPU with the previously
  recorded CC-BY-NC-4.0 checkpoint hash.
- Evidence and metrics: the accepted 39-note vocal candidate retained the
  exact raw MIDI SHA-256 `c02cc842bcde4235285b1983a9c2c05fa0c2a9b2cdfa28488b8d47c8d2ef0117`.
  Its separate source-expression MIDI used 26 distinct velocities from 42 to
  116 (median 89) and passed the new quality gate. The unrestricted full mix
  emitted 1,912 notes: 1,818 drums, 65 acoustic piano, 21 flutes, seven
  soprano/alto sax and one electric bass. Quality metrics were 127.47 notes/s,
  95.14% notes at 20ms or shorter, 93.62% duplicate signatures, 1,805 onsets
  in one 20ms bucket and maximum simultaneous polyphony of 1,806. Seventeen of
  28 flute/sax events matched the isolated voice's exact pitch and onset within
  80ms, demonstrating substantial vocal-to-wind label leakage.
- Listening result: source/neutral/expression vocal audition prepared; user
  preference pending. The full-mix MIDI was deliberately not rendered because
  its extreme event burst should not be sent to a synth.
- Decision: use source-derived expression for the opt-in GarageBand vocal
  challenger while preserving neutral/raw evidence. Reject automatic promotion
  of unrestricted MuScriptor-small full mixes. Prefer isolated, role-restricted
  stems and require `candidate.quality.json` to pass before promotion.
- Problems/risks: source energy is a relative velocity proxy, not a recovered
  MIDI performance controller. Full-mix instrument identity is unreliable and
  the model produced a severe short-note duplicate burst. The quality gate
  detects but does not rewrite the raw pathology.
- Next smallest step: add the first independent vocal-specific tracker (GAME
  or RMVPE) so note-boundary and F0 evidence can be compared with MuScriptor
  without relying on unrestricted full-mix semantics.

### 2026-07-15 — Cross-role evidence and explicit vocal integration

- Goal: decide whether the user's preferred MuScriptor lead-vocal result also
  generalises to melodic bass and overlapping backing vocals, then make the
  proven improvement usable without replacing existing evidence.
- Change or experiment: recorded the user's lead-vocal preference; created
  permanent local 15-second bass and backing-vocal fixtures; ran electric,
  acoustic, unrestricted and voice restrictions; evaluated and rendered the
  candidates; added `vocal-melody --muscriptor` as an explicit isolated
  challenger with tuned MIDI, note provenance and immutable run artifacts.
- Inputs: user-written Lidl song, bass seconds 200–215 and backing-vocal
  seconds 205–220, B major, 119 BPM, A=440.
- Model/runtime/checkpoint: the same MuScriptor 0.2.1 small checkpoint and hash
  recorded below, using CPU greedy decoding.
- Evidence and metrics: unrestricted MuScriptor increased the bass baseline's
  possible-onset F1 from 0.2152 to 0.3077, strong-onset F1 from 0.2456 to
  0.3235, contour correlation from 0.6581 to 0.7582 and notes from 20 to 31;
  timing p50 regressed from 7.10ms to 18.98ms. On backing vocals, MuScriptor's
  11-note voice line improved the deterministic dominant line's strong-onset
  F1 from 0.1905 to 0.2439, timing p50 from 27.31ms to 11.45ms, chroma from
  0.7098 to 0.9023 and contour correlation from 0.3846 to 0.9085. The existing
  26-note harmony stack still had higher onset coverage, confirming that a
  dominant line and a polyphonic harmony track must remain separate outputs.
- Listening result: the user states, “MuScriptor MIDI is substantially better
  than Sunofriend baseline” for the lead-vocal golden clip. Bass and backing
  A/B listening notes remain open beside their local auditions.
- Decision: integrate MuScriptor as an opt-in vocal challenger and retain the
  deterministic result as independent evidence and fallback. Do not
  automatically merge or promote it to primary yet. Preserve the existing
  backing harmony stack even when MuScriptor supplies the dominant line.
- Problems/risks: MuScriptor has no velocity evidence; the non-commercial
  checkpoint remains optional; backing-vocal absolute-octave evaluation is
  unreliable under harmonics/polyphony and needs listening; full-mix label
  leakage is still unmeasured.
- Next smallest step: collect bass/backing listening preferences, add source-
  evidence velocity recovery after the untouched raw candidate, and test one
  short full-mix passage before deciding on automatic role-specific ranking.

### 2026-07-15 — First real MuScriptor vocal bake-off

- Goal: measure whether a local open model adds useful melody evidence beyond
  the current pYIN/Basic Pitch vocal pipeline.
- Change or experiment: the user accepted the gated model terms; downloaded
  MuScriptor small locally; added checkpoint discovery/hashing diagnostics;
  ran identical CPU and MPS trials; evaluated and rendered A/B auditions.
- Inputs: locally extracted 15-second lead-vocal passage from the user-written
  Lidl song, original song seconds 30–45, B major, 119 BPM, A=440.
- Model/runtime/checkpoint: MuScriptor 0.2.1 small (103M), revision
  `8c127f603b807520fa465c838e9bfee8a91ada4e`, checkpoint SHA-256
  `bbd482c786b895cf7d8f44185073d951adae2ebb8a66f82ca84cd1f84569549c`.
- Evidence and metrics: CPU and MPS produced byte-identical 39-note MIDI. CPU
  completed in 3.30s versus MPS 5.37s. MuScriptor improved strong-onset F1
  from 0.0000 to 0.4828, possible-onset F1 from 0.0377 to 0.5246, chroma
  similarity from 0.8758 to 0.9084, supported-note ratio from 0.3913 to
  0.4615, and contour-direction accuracy from 0.4091 to 0.6579. Timing p95
  increased from 18.69ms to 28.74ms. The local comparison record preserves
  the complete metrics and paths. The full suite passes (265 tests), Ruff
  passes, both distributions build, and Twine validates both packages.
- Listening result: the user subsequently reported that MuScriptor MIDI is
  substantially better than the Sunofriend baseline.
- Decision: advance MuScriptor small as the preferred lead-vocal challenger;
  retain the current contour pipeline as independent evidence and fallback.
  Prefer CPU for this model/clip size because it was faster with identical
  output.
- Problems/risks: MuScriptor is much denser (39 notes/12.23 note-seconds versus
  23 notes/2.94 note-seconds), so listening must distinguish improved phrase
  continuity from syllable over-segmentation or over-sustain. The vocal
  evaluator's apparent polyphony is influenced by harmonics.
- Next smallest step: completed in the cross-role increment above; collect
  the remaining bass/backing listening scores before automatic ranking.

### 2026-07-15 — Isolated worker and immutable run records

- Goal: make the first optional model runnable without weakening licence,
  provenance or failure boundaries.
- Change or experiment: added `ai-transcribe`, a standalone MuScriptor event
  adapter, excerpt support, raw/validated candidate separation, neutral MIDI
  export, worker timeout/log capture and immutable per-run manifests.
- Inputs: synthetic audio/checkpoint bytes and fake success/failure workers;
  no song audio and no gated checkpoint.
- Model/runtime/checkpoint: core tests use fake workers; the real adapter
  requires an existing local `.safetensors` checkpoint and rejects aliases and
  URLs before importing MuScriptor.
- Evidence and metrics: synthetic tests cover success, event/schema parsing,
  raw candidate preservation, MIDI generation, source/checkpoint SHA-256,
  worker failure, timeout, collision/no-overwrite and no-download rejection.
  The complete suite passes (263 tests), Ruff passes, both distributions build,
  and Twine validates the wheel and source archive.
- Listening result: not applicable; no real checkpoint inference yet.
- Decision: retain raw notes with null model velocity and create a separate
  neutral-velocity MIDI; do not mix repairs into the model evidence.
- Problems/risks: MuScriptor MPS compatibility and instrument-name behaviour
  remain unmeasured; CC-BY-NC-4.0 acceptance must be explicit.
- Next smallest step: after explicit checkpoint acceptance, run CPU and MPS on
  one authorised 10–15-second clip and compare timing/pitch against the current
  Sunofriend transcription.

### 2026-07-15 — Phase 1 foundation

- Goal: begin the bake-off without destabilising the existing audio stack.
- Change or experiment: added the isolated Python 3.12 runtime definition,
  PyTorch/MuScriptor package setup, licence manifests, candidate v1 contract
  and `ai-doctor` design.
- Inputs: environment and synthetic protocol validation only; no song audio.
- Model/runtime/checkpoint: Python 3.12, pinned PyTorch and MuScriptor package;
  no gated model checkpoint downloaded.
- Evidence and metrics: Python 3.12.10, PyTorch 2.13.0, MPS built/available,
  MuScriptor 0.2.1 code installed; both `ai-doctor --require torch` and
  `ai-doctor --require muscriptor` pass. The complete existing suite plus new
  protocol tests passes (257 tests), Ruff passes, and the wheel/sdist build
  succeeds with `ai_runtime.py` included.
- Listening result: not applicable; model inference has not started.
- Decision: keep AI inference isolated and checkpoint downloads explicit.
- Problems/risks: MuScriptor weights are non-commercial and gated; GAME and
  RMVPE need external-checkout adapters and checkpoint manifests.
- Next smallest step: implement worker invocation/run manifests (completed in
  the following increment), then evaluate MuScriptor small on one authorised
  10–15-second clip after explicit checkpoint acceptance.

## Decision record template

Every backend decision should state:

- backend and exact model/checkpoint;
- task and golden clips;
- objective result relative to current Sunofriend;
- listening preference and reviewer;
- hardware/runtime cost;
- failure modes;
- code, weight and data-licence status;
- decision: integrate, optional oracle, investigate, or reject;
- conditions for revisiting the decision.
