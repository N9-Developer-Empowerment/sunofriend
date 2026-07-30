# Sunofriend architecture

Sunofriend has four user-facing layers:

1. The Python package and `sunofriend` command are the deterministic engine.
2. The Guided Local Studio TUI is the preferred human control surface. Its
   default **Make my song** mode runs one typed automatic pipeline and publishes
   an explicitly unreviewed MIDI/WAV/ZIP starter result. Its **Studio** tabs
   project local project state and orchestrate typed engine/Workbench actions
   without implementing musical algorithms. Its native **Master** tab also
   orchestrates the shared fixed-policy Listening Master service.
3. The loopback-only Workbench presents completed source/MIDI alternatives,
   records explicit decisions, renders the selected MIDI as a
   song-interpretation WAV, can explicitly create a separate fixed-policy
   listening-master challenger, can record a bounded blind quality review in a
   separate feedback plane and prepares the GarageBand handoff.
4. The portable Agent Skill is the conversational expert route: it selects
   commands, checks prerequisites and interprets reports. It must not duplicate
   audio or MIDI algorithms.

These layers preserve Sunofriend's core separation. Several analytical and AI
processes may produce immutable candidates. Simple mode accepts only the exact
primary already published by each production conversion summary and records it
in a separate automatic, unreviewed receipt. Studio makes the alternatives
approachable and records only explicit human choices. Both paths create
editable MIDI plus a MIDI-derived song-interpretation WAV; only Studio may
describe its completed selection as reviewed. No shared score or model label
is silently promoted into a Workbench decision.

The optional Developer Inspector is a read-only projection across these
layers. Its `sunofriend.workbench-developer-snapshot.v1` document explains
application operations, append-only events, derived current state and the
separate Pack Composer revision without becoming another state store. It is
disabled unless `workbench --developer-inspector` is supplied, remains behind
the loopback launch token and has no model, decision, basket, render, MIDI or
export effect. The Guided Local Studio supplies that flag by default when it
starts Workbench; `tui --no-developer-inspector` keeps it absent. See the
[technical tour](TECHNICAL_TOUR.md).

## Current execution flow

```text
authorised local audio
        |
        +--> one asset: source-import --plan / source-import
        |
        +--> 2–64 already-separated parts:
        |       source-import-folder --plan
        |       source-import-folder
        |         --> immutable originals + per-source receipts
        |         --> aggregate receipt + source-project manifest
        |         --> canonical top-level PCM24 WAV stems
        |         --> deterministic source-graph revision 1 on read
        |
        +--> source-doctor (read-only existing FFmpeg/FFprobe evidence)
        |
        v
prepared stem folder / existing MIDI
        |
        v
Guided Local Studio (`tui.py`, `simple_create.py`, `tui_model.py`,
                     `tui_conversion.py`) or direct expert route
        |
        +--> Simple: production conversion
        |       --> exact summary primaries (`automatic_selection.py`)
        |       --> verified MIDI/WAV/ZIP (`simple_result.py`)
        |
        +--> Studio: immutable candidate review and explicit decisions
        |
        v
CLI/application services (`cli.py`)
        |
        +--> folder orchestration (`listen_all.py`)
        |       --> composite drums: review-required mixed-kit MIDI
        +--> stem refinement (`loop.py`)
        +--> vocal extraction (`vocal.py`)
        +--> lossless MIDI transforms (`midi_tempo.py`, `midi_transform.py`,
        |                            `midi_anchor.py`)
        +--> creative grid rebuild (`midi_align.py`)
        +--> short MIDI-guided cleanup evidence (`midi_mask.py`)
        +--> isolated learned cleanup challenger (`ai_cleanup.py`,
        |                                         `ai_cleanup_worker.py`)
        +--> immutable AI lane comparison (`ai_matrix.py`)
        +--> read-only phrase consensus evidence (`hybrid_report.py`,
        |                                         `note_alignment.py`)
        +--> fresh-process AI timing comparison (`ai_benchmark.py`)
        +--> one-variable MuScriptor comparison (`ai_setting_compare.py`)
        +--> bounded exact-repeat MuScriptor session (`ai_session.py`,
        |                                             `ai_worker_session.py`)
        +--> reused-model session verification (`ai_session_benchmark.py`)
        +--> exact MuScriptor raw-result reuse (`ai_cache.py`)
        +--> application-cache verification (`ai_cache_benchmark.py`)
        +--> reviewed multi-role MIDI challenger (`midi_role_split.py`)
        +--> fixed-MIDI timbre baseline (`timbre_resynthesis.py`)
        +--> blind source-aligned MIDI comparison (`midi_ab_review.py`)
        +--> local decision workbench (`workbench_catalog.py`,
        |                              `workbench_store.py`,
        |                              `workbench_semantics.py`,
        |                              `workbench_privacy.py`,
        |                              `product_contract.py`,
        |                              `workbench_home.py`,
        |                              `workbench_timeline.py`,
        |                              `workbench_mix.py`,
        |                              `workbench_artifacts.py`,
        |                              `workbench_instrument_policy.py`,
        |                              `workbench_instrument_coverage.py`,
        |                              `workbench_instrument_review.py`,
        |                              `workbench_listening_master.py`,
        |                              `workbench_master_review.py`,
        |                              `workbench_master_review.js`,
        |                              `workbench_server.py`,
        |                              `workbench_clips.py`,
        |                              `workbench_clips.js`,
        |                              `workbench_reuse.py`,
        |                              `workbench_transform.py`,
        |                              `workbench_correction.py`,
        |                              `workbench_velocity.py`,
        |                              `workbench_deletion.py`,
        |                              `workbench_developer.py`,
        |                              `workbench_developer.js`,
        |                              `workbench_visualization.js`,
        |                              `workbench_transport.js`)
        +--> instrument discovery (`instrument_catalog.py`)
        +--> timbre matching/sample packs (`instrument_match.py`)
        +--> arrangement-aware sampler gate (`instrument_usability.py`)
        +--> explicit local patch preferences (`instrument_preference.py`)
        +--> portable sound/match handoff (`instrument_bundle.py`)
        +--> hummed guidance and review artifacts (`melody_correction.py`)
        +--> self-contained SoundFont writing (`soundfont.py`)
        +--> reusable Clip v1 library (`clip.py`, `library.py`)
        |
        v
automatic unreviewed starter result OR reviewed Studio result + provenance
```

Source Access S1 is intentionally separate from transcription.
`audio_formats.py` validates supported local container-plus-codec
combinations and the exact existing FFmpeg/FFprobe toolchain.
`source_import.py` plans or atomically executes one fresh import;
`source_folder_import.py` composes 2–64 already-separated top-level parts,
checks role and available recorded-origin evidence, and publishes one fresh
project atomically. `source_receipt.py` pins unchanged originals and canonical
PCM24 WAV files. `source_project.py` preserves role, filename, key, BPM,
tuning, chord and user-declared rights context.

Both import commands have an explicitly read-only `--plan` form. Execution
uses file-only decoder protocols with no normalization, network access or
dependency installation. Folder import does not recurse, separate a full mix,
shift, pad, stretch or musically align files. `project_audio_inputs.py`
centralises the preflight that prevents an unprepared mixed-format folder from
being mistaken for a valid project. A successfully prepared folder exposes
canonical top-level WAV stems, so Create, TUI and Workbench retain their
existing production discovery and candidate identities. Prepared-project
metadata and an optional chord document are read from the manifest before
falling back to legacy filename inference.

Source Access S2 keeps the S1 import manifest stable and adds two independent
boundaries:

- `source_roles.py` is the canonical role vocabulary and conservative
  set-valued inference policy. `drums`, `vocals` and `other` may be explicitly
  represented as composite nodes; imported `vocals` and `other` remain leaves
  unless refinement evidence says otherwise. Provider labels and General MIDI
  families do not expand that vocabulary.
- `source_lineage.py` supplies an immutable append-only
  `sunofriend.source-graph.v1` overlay. A project without a saved graph gets a
  deterministic read-only revision 1. Explicit revisions use
  content-addressed objects and a compare-and-swap current pointer. The active
  frontier prevents a parent and its children from both feeding production,
  while the parent remains available for rollback.

`drum_roles.py` and `transcribe_drums.py` route a broad `drums` source through
the existing mixed-kit spectral classifier. This produces review-required
MIDI family variants only. One dominant family is selected per onset, so
coincident layered hits may collapse; no kick, snare, hat, tom or cymbal audio
children are created. Viable explicit drum-family sources shadow the broad
candidate in automatic arrangements to prevent doubled hits, but the broad
candidate remains available in Studio. If the explicit leaves produce no
viable primary MIDI, the composite result is the review-required fallback.

Source Access S3 keeps `separation_contract.py` as the pure, backend-neutral
DTO and receipt boundary. New path-free, self-hashed receipts use
`sunofriend.separation-run.v2`, while canonical v1 float-leakage receipts
remain readable. They bind source, backend, checkpoint, roles, execution,
same-clock target/residual pairs, quality and side-effect facts; only
`complete` is loadable.

An internal optional-dependency-free harness in `separation.py` and
`separation_quality.py` accepts only the exact deterministic
`FakeSeparationBackend`. The parent verifies source/checkpoint identity,
recomputes persisted PCM16/PCM24 hashes, geometry, level and reconstruction
evidence, records unmeasured leakage as review-required, uses a fresh private
sibling work root and publishes a completely revalidated terminal tree with
one rename. Its v2 receipt embeds the full canonical run plan, derives
`run_id` from that plan hash and cross-binds the plan to all receipt-visible
execution identities. Module/runtime identity and monotonic wall time are
derived by the parent; aggregate files, bytes, checkpoint size and free-space
reserve are bounded. Arbitrary in-process backends, fake subclasses and
executable cancellation callbacks are rejected because they cannot prove zero
network or outside-output writes. There is still no CLI/TUI action, isolated
real worker/backend, model or install flow, cache, or finished-song operation.

`separation_acceptance.py` is the third internal S3 boundary. It validates the
strict, path-free `sunofriend.separation-acceptance-thresholds.v1` schema. Its
pure freeze operation requires explicit policy sections and thresholds,
self-hashes the canonical document and returns an immutable projection;
loading is bounded, canonical, regular-file-only and read-only.
`verify_hidden_evaluation_manifest` accepts the complete frozen artifact,
independently rehashes a
`sunofriend.separation-hidden-evaluation-manifest.v1`, derives dataset coverage
and split identity, and rejects committed development/hidden song-identity and
canonical-source overlap. Candidate and baseline execution identities,
resource classes, per-song rights and distinct ground-truth evidence,
licences, private audition/assignment/answer-key commitments, level matching
and statistical treatment are fixed before hidden evaluation. The module
contains no production profile, hidden scores, pass logic, model execution,
registry integration or promotion effect.

`separation_bakeoff.py` is the fourth internal S3 boundary. Its deterministic,
read-only `sunofriend.separation-bakeoff-preparation.v1` document is canonical,
self-hashed, deeply immutable, redacted and explicitly `prepared_not_run`.
Prepare, validate and load each reload the complete canonical frozen acceptance
artifact and reverify the complete canonical hidden manifest. The plan binds
the profile identity and acceptance artifact, canonical-document,
hidden-manifest and split hashes, aggregate coverage, ordered
baseline-then-candidate separator arms, roles proposed for promotion,
downstream MIDI identities, evaluator, resource classes and the fixed gate
conjunction. It exposes no song or source ID; no song, source, ground-truth,
checkpoint or worker hash; and no path, threshold value, score or private
note. Every model, worker, inference, checkpoint, download, network, audio,
file, result, metric, score, selection, promotion and default-changing effect
is false; the module has no writer, CLI/TUI, registry, result, pass or
promotion operation.

`separation_backend_preflight.py` is the fifth internal S3 boundary. Its
path-free `sunofriend.separation-backend-preflight.v1` report reverifies the
complete frozen acceptance, hidden manifest and redacted preparation before
inspecting one exact baseline or candidate arm. The trusted parent reads
bounded regular non-symlink worker, dependency-lock and checkpoint files,
checks a stable native-executable header without starting it, and inventories
the complete package and matching `.dist-info` trees named by the installed
distribution. The package digest includes directory markers, executable
`.pth`, bytecode, empty directories and undeclared files inside those owned
roots; install-path-bearing
`direct_url.json` is parsed only for separately bound Git provenance. Exact
read-time file facts are retained and rechecked, so replaced metadata,
inventories and launchers fail closed. Duplicate identities, intermediate
symlinks and malformed editable metadata also block. Shared namespace-package
roots are intentionally over-bound as a whole, so an unrelated neighbour can
cause a conservative mismatch rather than false verification. A clean report is
`verified_not_run`, not executable proof: runtime identity, importability,
dependencies, console scripts, external site-startup code, accelerator
availability and the offline gate remain explicit limitations. The module
starts no process, imports no backend, loads no checkpoint, reads no audio or
result, writes nothing and cannot select, score, promote or change defaults.
It has no CLI/TUI operation and is not authorisation for a later runner.

`separation_worker_contract.py` is the sixth internal S3 boundary. Its private
`sunofriend.separation-worker-request.v1` is deliberately path-bearing and
must never be published. The validator requires the trusted complete frozen
acceptance artifact, the verified static preflight and the original
`SeparationRequest`; it derives the registered baseline/candidate identity and
cross-checks worker, dependency lock, runtime, checkpoint, source, roles,
settings, seed, a separate parent-owned runtime-launcher artifact and the
canonical `STEMS/<role>.wav` allowlist. Its
`sunofriend.separation-worker-result.v1` is path-free and binds the same
trusted inputs, before/after input hashes, exact output hashes/geometry and
named isolation evidence. It contains no quality, ranking, preference,
selection or promotion field. V1 accepts only private-development isolation;
hidden acceptance and `acceptance_ready` are not representable.
This is a pure contract: it performs no filesystem access and starts no
process. There is still no approved subprocess transport, platform isolation
provider, real worker, model execution or artifact publication path.

`separation_runtime_artifact.py` is the seventh internal S3 boundary. Its pure
`sunofriend.separation-runtime-artifact.v1` document binds a bounded, acyclic
launcher chain, every relevant ancestor directory, the final native
executable, `pyvenv.cfg`, installed package-tree digest, worker and dependency
lock to separate parent-owned request, preflight and measurement identities.
It rejects upward relative symlink targets, incomplete or resolved ancestor
evidence, case/Unicode path aliases and duplicate device/inode identities.
The document is always `private_development_unregistered`; it says that
execution is unproven, TOCTOU is open and a pre-exec remeasurement is
required.

`separation_launch_contract.py` composes that artifact into an exact pure
launch plan and supervisor-owned lifecycle. The plan fixes a no-shell,
no-path-search argv, replacement environment, closed descriptor allowlist,
isolation template, process policy and private output staging. The module
cannot spawn: `REAL_WORKER_EXECUTION_SUPPORTED` is literally false and AST
tests exclude process, filesystem, network and dynamic-execution surfaces.
Lifecycle events are cross-checked against a separate in-memory exact-type
supervisor ledger. Handle acquisition, exec observation and worker handshake
are distinct; a created process cannot be reclassified as not started, and
reap plus empty-process-tree evidence is required before lease release.
Exports remain path-free. Normal terminal cleanup is named
`execution_finished_unvalidated`, not success, and explicitly records that no
worker result, post-input immutability, parent output verification,
quarantine, publication, acceptance or promotion has been proved.

`separation_runtime_measurement.py` is the eighth internal S3 boundary and the
first filesystem-facing counterpart to those pure records. It accepts only an
exact parent-issued request binding. Read-only, no-follow descriptors measure
the launcher chain, stable complete ancestor identity, native executable,
`pyvenv.cfg`, worker, lockfile and a bounded descriptor-relative
`site-packages` tree. Immediate remeasurement must reproduce the complete
artifact. Runtime/package files retain full identity and byte checks; ancestor
directories use a documented stable device/inode/mode projection and pinned
parent-child bindings so unrelated sibling writes do not create false
failures. System site packages, cross-device descendants, hardlinks, symlinks,
unsafe aliases, devices, sockets and resource overruns fail closed.

The measurer starts no process and makes no model, audio, network-API or write
operation. Its artifact remains unregistered, execution-unproven and
TOCTOU-open. Launch uses `-S` to avoid automatic `site` and `.pth` startup, but
base-standard-library, `pyvenv` home, native dynamic-library and same-device
APFS alias closure remain later admission/provider boundaries.

`separation_checkpoint_policy.py` and
`separation_execution_admission.py` form the ninth internal S3 boundary. They
are pure, private-local policy projections over synthetic, reported evidence,
not trusted authority. Every checkpoint decision and execution admission is
therefore `blocked` and `not_run`; private-development eligibility,
worker-start permission and every execution or publication effect are false.
The exact pinned HTDemucs SHA-256 is classified in code as an executable
PyTorch pickle model package even if a caller reports another format.
Checkpoint terms and allowed use remain unverified, and an unsafe-pickle
exception record is descriptive only and cannot waive that blocker.

The code-owned runtime-closure, output-boundary, resource-limit and real
execution capabilities are false, while supported isolation and
model-descendant provider sets are empty. Admission collects, rather than
short-circuits, the missing trusted acceptance/preflight/request/launch
bindings, runtime closure, isolation and outbound-attempt observation,
input/process/filesystem confinement, real transport, parent output
verification and quarantine, and hard resource-enforcement blockers. Neither
module opens a path, inspects or deserializes checkpoint bytes, starts a
process, imports a model, reads audio, writes a file or makes a network call.

`separation_checkpoint_inspection.py` is the tenth internal S3 boundary and
the filesystem-facing counterpart to the pure checkpoint policy. It accepts
only an exact parent-issued worker request and reverifies the complete trusted
acceptance, preflight, separation-request and runtime-artifact binding.
Canonical absolute path components are opened descriptor-relative with
no-follow, directory-only, close-on-exec and nonblocking flags. Every ancestor
attachment and the regular single-link checkpoint are checked before and
after bounded reads, and all descriptors are closed even when validation
fails.

The module hashes the request-bound bytes, validates a narrow stored-only
Torch ZIP dialect manually before `zipfile`, then parses only bounded
`pickletools` opcodes. It recognizes the exact registered HTDemucs whole-file,
global and opcode profile as a pickle model package. It deliberately leaves
generic state-dict-like streams `unknown`; it neither executes abstract pickle
stack/memo semantics nor calls pickle/Torch deserialization. Member names and
globals are represented by counts and hashes in a private, immutable,
path-free report. No loading, model import, process, network API, audio, write,
selection, publication, acceptance or promotion effect is available.

This inspection is evidence, not loader authority. It does not pass the
verified checkpoint descriptor to a future worker, cannot prove that the
underlying mount is local and does not recompute every tensor member CRC.
Path-to-loader TOCTOU therefore remains explicit. The next launch/transport
boundary must inherit the verified descriptor and bind the inspection into
admission while keeping real execution disabled.
`REAL_SEPARATION_EXECUTION_SUPPORTED` remains false.

`separation_execution_admission_binding.py` is the eleventh internal S3
boundary. It leaves the pure synthetic v1 admission and all v1 launch hashes
untouched, then wraps one completely revalidated v1 record with the exact
parent-observed checkpoint inspection. Authority requires the candidate and a
separately retained trusted inspection to be the same object; class identity,
canonical hashes and copied module-private tokens are not sufficient. This
prevents a rehashed classification forgery from borrowing a valid inspection
request.

The v2 wrapper binds the v1 admission and checkpoint policy to inspection,
classification, worker-request, preflight, acceptance and checkpoint hashes.
A code-owned vocabulary map is required because inspection calls the exact
HTDemucs artifact a `torch-zip-pickle-model-package` while policy calls the
same load risk a `torch-pickle-model-package`. Only that static checkpoint
observation is trusted. Runtime, isolation, output, resources, terms and
loader reports remain synthetic, so the wrapper preserves every v1 blocker
and adds descriptor-not-carried, path-to-loader-TOCTOU and
static-inspection-not-load-authority. Its record is path-free, mixed-authority,
blocked and not run; all operation effects are false.

`separation_checkpoint_descriptor_lease.py` is the twelfth internal S3
boundary. It reopens and reparses the exact request-bound checkpoint, requires
equality with the separately retained trusted inspection, closes all
descriptor-pinned ancestors and retains one non-inheritable read-only leaf
descriptor in private weak-registry state. Its public handle is opaque,
non-copyable and non-serializable. The immutable path-free observation exposes
hashes and classification only; it never exposes the descriptor number or a
path and is historical evidence rather than current liveness authority.

Recheck and close are serialized per lease and use only the retained
descriptor. Full hashing plus before/after identity checks fail closed on
pathname replacement, in-place mutation, inheritance, descriptor ownership
loss or parent-PID mismatch. Terminal state is one-way: active ownership and
the finalizer are detached before one close call, and a sealed acquisition
anchor lets the public receipt preserve integrity and cleanup outcomes even
when later authority validation fails. Close-call success is reported as such,
not as post-close content proof; garbage-collection cleanup is best effort.

No inherited checkpoint descriptor is implemented. Launch v1 still contains
only FDs 3 and 4 and retains a checkpoint path in the private request. The
ordinary retained inode is not an immutable snapshot and cannot authorize
unsafe pickle loading. A later transport design must remove the child
checkpoint path, reserve and remeasure the lease under the same lock,
atomically install read-only FD 5 and bind child-side identity/hash evidence
without changing any current capability to true.

`_separation_checkpoint_transport_records.py` and
`_separation_worker_request_v2_values.py` form the thirteenth internal S3
boundary. They define and validate the pure, private, path-free
`sunofriend.separation-worker-request.v2` design-evidence record without
importing the V1 production boundary. It accepts only the stricter admitted
and inspected V1 subset defined by this internal schema. The record carries a
canonical logical
projection of preflight, identities, roles, settings, seed and isolation,
plus 16 expected hashes or sizes supplied by a future facade. It derives
role-specific logical output slots and describes the purposes of descriptors
3, 4 and 5, but contains no path or raw descriptor number.

Canonical type comparison prevents boolean/integer/float substitution; value,
depth, item, checkpoint-size and sealed-request-size bounds fail closed. The
record inherits the mandatory admission blockers, adds the code-owned source,
output, protocol, FD 5, child-remeasurement, immutable-backing, unsafe-pickle
and real-execution blockers, and fixes every capability and effect to false.
Its inputs are expected values rather than authority or self-proving
provenance, the validating V1-to-V2 facade is not implemented, and the V2
schema is permanently non-executable. It reserves no lease, installs no descriptor,
opens no file, starts no process and exposes no CLI, TUI, model or separation
operation. A future executable request needs a new schema.

On 29 July 2026, `_separation_checkpoint_fd5_reservation.py` forms the
fourteenth internal S3 boundary. Its private zero-field token binds one live
retained lease to one exact V2 record, the exact V1 inspection request and the
current observation backing. All lease-provable facts are cross-bound. The
runtime-artifact document, execution-admission and runtime-parent hashes remain
sealed by the V2 record but are not proven by the lease. Reserve and release
remeasure under the existing lease lock. Healthy close refuses while reserved;
integrity and ownership failures terminalize once. The token exposes and
installs no FD 5, starts no process, imports or loads no model, and adds no
user-facing separation. V1 schemas, hashes and APIs remain unchanged. Blocked
launch V2 and atomic FD 5 installation design are still the next boundary.

The 29 July 2026 fifteenth S3 increment is a behaviour-preserving
maintainability split rather than another capability boundary. Descriptor-only
`fstat`, `pread`, `lseek` and owned-close helpers now live in
`_separation_checkpoint_descriptor_io.py`, while pure acquisition-evidence
derivation lives with the observation and receipt policy in
`_separation_checkpoint_lease_records.py`. The live
`separation_checkpoint_descriptor_lease.py` facade is reduced from 884 to 793
lines and still owns every lock, registry entry, state transition and
finalizer. Public V1 and reservation types, signatures, `__all__`, schemas,
hashes and behaviour are unchanged. This refactor adds no separator, FD 5
installation, process, model load, CLI/TUI route or other user-facing
capability.

The 29 July 2026 sixteenth S3 boundary is
`_separation_checkpoint_launch_v2_records.py`. It defines a private, path-free,
deeply immutable `sunofriend.separation-launch-plan.v2` record. The descriptor
lease facade may issue that record only while holding the lease lock, after
full authority validation, checkpoint remeasurement and exact-object checks
for the current reservation and its V2 request. Issuance leaves the live
descriptor and reservation unchanged.

The plan describes logical FD 3 request, FD 4 result and FD 5 checkpoint
requirements plus a future child-creation atomicity sequence. It serializes no
path, raw descriptor, token or argv. The three V2 values outside lease
authority remain explicitly sealed but unproven. Its serialized construction
conditions are requirements rather than evidence that the private facade
performed them. The record is not liveness or installation authority; a
duplicated descriptor would share the retained open-file-description offset,
so an offset-independent child reader or serialized ownership protocol remains
mandatory. A future worker must also make FD 5 non-inheritable immediately
after the one intended exec. All process, installation, loading, model,
inference, result, selection and publication capabilities and effects are
false. Existing V1 launch records and lifecycles do not import or accept this
type. A later fake-worker transport needs new executable request and launch
schemas.

The 30 July 2026 seventeenth S3 boundary is
`_separation_fake_transport_records.py`. It defines new private fake-worker
request, blocked launch and worker-report result schemas without changing the
permanently non-executable V1/V2 records. The request and launch bind a
64-hex run identifier, exact historical V2 hashes, logical descriptors 3/4/5
and one code-owned two-frame PCM24 fixture per requested role. They contain
no path, raw descriptor, argv or live token. A same-shaped record is never
lease, reservation or run authority, and nonce shape does not prove
freshness or single use. Fake request and launch V1 are permanently
non-executable; an actual fake executor requires a new launch schema.

The fake launch records platform requirements rather than pretending they
have run. Its native close-all launcher, child-only mapping, unlisted
descriptor closure, live lease authority, immediate checkpoint
remeasurement and parent quarantine verification are all unproven blockers.
Consequently worker-start permission remains false. The result type is only a
bounded worker report; it cannot publish output or become parent verification
evidence.

`_separation_fake_worker_protocol.py` is the eighteenth S3 boundary. It is
process-free. It frames the exact fake request/launch envelope and result as
canonical bounded JSON with separate magic values, rejects ambiguous or
trailing bytes and cross-binds the run nonce and hashes. Its parent observer
uses only supplied directory and file descriptors, `fstat`, descriptor-
relative entry observations and `pread` to verify the exact observed entry
set, stable identity, owner-only permissions, link count, distinct inodes,
per-slot limits, hashes and PCM24 RIFF geometry.

The observer reports one path-free observation with selection and publication
disabled. It does not prove directory freshness, permanent immutable backing,
process isolation or a completed child lifecycle and issues no terminal
receipt. FD 4 carries the bounded worker report and its tiny fixture payloads.
A future parent creates the private quarantine from validated result bytes,
then reopens it for observation; the child receives no output path or
directory descriptor. The missing audited native close-all launcher remains
the next boundary before a deterministic fake child can start.

`_separation_fake_launch_v2_records.py` is the nineteenth S3 boundary. It
defines a pure, private and permanently non-executable
`sunofriend.separation-fake-launch-plan.v2` record. Existing fake request and
blocked-launch V1 records are exact historical bindings only; they supply no
live nonce, lease, reservation or run authority. Native-launcher, runtime and
worker hashes, sizes and stat identities are sealed as caller claims rather
than measured artifacts or build provenance.

The contract fixes a no-shell, no-path-search isolated Python invocation, an
exact three-variable replacement environment and a child-only descriptor
action plan. It requires scratch-first copies, explicit closure of the
original child descriptors, scratch-to-3/4/5 mapping, scratch closure, null
standard streams and Darwin close-all behavior while leaving the parent FD
table unchanged. FDs 3/4/5 must be inheritable across the intended exec and
the fixed worker must set them non-inheritable before protocol parsing,
checkpoint access or any possible later exec; noninheritability before
CPython starts is neither possible under this design nor claimed.

New-process-group ownership, a monotonic timeout, TERM/KILL escalation,
exact-PID reap, nonterminal unreaped supervision, split worker/parent errors
and parent-owned FD4 payload materialisation are requirements only. Current
fake envelope and result V1 schemas do not bind the new plan. The record
measures no artifact, loads no extension, invokes no native function, creates
no descriptor action, starts no child and creates no file. Build provenance,
live remeasurement, nonce freshness, exact live authority, path-to-exec/open
TOCTOU closure, close-all canaries and lifecycle enforcement remain absent.
Every capability and effect is false. A separately built and audited native
boundary is the next increment; this record itself must never be enabled.

`_separation_native_spawn_darwin.c` is the twentieth S3 boundary. The C file
is packaged as source data but deliberately has no setuptools extension
registration, Python import or caller. Its static contract is macOS-only and
contains direct Darwin `posix_spawn` plus close-all, process-group and signal
attributes. Fixed arguments/environment, read-only validation of three exact
parent transport descriptors, collision-safe child actions, explicit alias
closure, null standard streams, compatible parent `SIGCHLD` and a
post-spawn allocation-failure kill/reap path are visible for source review.
No parent descriptor is duplicated, closed or reflagged.

The twenty-first S3 boundary adds a separate internal macOS-only builder and
test-only canary without making the C extension publicly reachable. Every
build uses fresh owner-only storage, a hash-pinned source and recipe, measured
Apple tools, split Clang object compilation and a direct measured `ld`
invocation. The recorded artifact-input provenance covers the
compiler-discovered header closure, compiled object and explicit SDK
`libSystem.B.tbd` before and after their relevant operations. It deliberately
does not claim to enumerate dynamic runtime libraries used internally by the
Apple tools. The final thin host-architecture Mach-O, deployment target,
linked dylib set, absent RPATH, deterministic `LC_UUID`, strict ad-hoc
signature and complete artifact hash are revalidated. Two fresh builds on the
same measured host must produce the same artifact hash and UUID; their
per-build receipts retain distinct filesystem identities.

The isolated live canary imports only the remeasured private artifact. It
proves all six logical permutations of exact physical source FDs 3/4/5 and a
fixed representative matrix of ordinary low non-target, mixed target-collision
and scratch-candidate/near-limit layouts. Every case has exactly FDs 0–5 in the
child, closure of
unrelated low and high inheritable descriptors, and unchanged parent
descriptor identities, relevant flags and offsets after spawn and reap.
Non-default parent `SIGCHLD` states fail closed.

The native entry point no longer returns a bare integer PID. It preallocates a
nonconstructible, noncopyable exact-child owner before `posix_spawn`, arms and
returns that same object without a post-spawn Python allocation, hides the raw
PID and binds destructive methods to the creating process. Exact nonblocking
wait caches status and releases leader ownership atomically; no signal or
negative-PID probe is permitted after reap. `ECHILD` poisons the owner, so a
stolen reap cannot lead to a stale-PID signal. Live canaries cover ordinary
reap, stable cached wait, signal rejection after reap, last-reference
`SIGKILL` plus exact reap, and poisoned ownership after a deliberately stolen
reap.

This finite evidence does not enable fake-launch V2 or provide model-execution
authority. The emergency destructor's exact wait is not time-bounded, the
fork-clone check is static rather than live, fixed workers are required to
create no descendants, and no generic post-leader process-group claim is
made. Exhaustive arbitrary source-FD values, inside-harness observation of the
required clean outer supervisor, post-CPython child signal state and
extension/runtime/worker path TOCTOU closure remain unproven. Only fixed test
probes ran; there is no standalone deterministic fake result, checkpoint FD 5
transport, model execution, audio operation, terminal receipt or user-facing
separator.

The following prepared-worker boundary keeps execution-era schemas isolated
from every permanently blocked predecessor. The fixed
`_separation_fake_worker_darwin.py` script imports only a narrow stdlib set,
makes FDs 3/4/5 non-inheritable before its remaining imports, performs no path
open, source-audio, model, network or child-process operation, and emits only
the role-hash two-frame PCM24 fixture. Its source hash and size are pinned by
the prepared fake launch V3 record. V3 has support but no start permission and
is explicitly not serialized authority. Complete-only Result V2 requires a
dedicated worker process group and remains self-report evidence.

`_separation_fake_execution_protocol.py` validates the new V2 magics and
canonical bindings but intentionally cannot encode an admitted product
request or issue an admission. Synthetic envelope creation exists only in
tests. The later executor must add a nonconstructible, single-use authority
under the exact live checkpoint lease/reservation lock, supervise the native
owner through exact reap and perform separate parent quarantine verification.
The current modules therefore add no process, terminal receipt, separator,
model, audio read or CLI/TUI capability.

Simple mode branches exact production-summary primaries into individual MIDI,
a combined General MIDI proxy, the existing balanced MIDI-derived WAV and a
starter ZIP. It does not create or mutate Workbench SQLite state. After
explicit Studio review, the Workbench branches one human-selected arrangement
into the unchanged editable MIDI handoff and the same kind of MIDI-derived
song-interpretation WAV. In both cases source stems supply timing, horizon and
level evidence; their audio is not mixed into the WAV. The optional listening
master is a separate comparative derivative, not a release master, and
GarageBand Pack Composer remains a reviewed Studio handoff.

## Guided Local Studio boundary

`tui.py` contains Textual widgets and lifecycle orchestration.
`tui_model.py` contains deterministic, widget-free project projections, compact
MIDI maps and exact Workbench command construction. It reuses
`workbench_catalog.py`, `workbench_home.py`, `workbench_store.py` and
`workbench_timeline.py`; it does not parse or rewrite MIDI independently.
`tui_conversion_contract.py` defines the Textual-independent request, progress,
result and runner protocol. `tui_conversion.py` validates and orchestrates the
production child commands; it contains no transcription algorithm.

`simple_create_contract.py` is the Textual-independent one-action request,
progress, cancellation and result boundary. `simple_create.py` composes the
existing production conversion runner with two new side-effect-isolated
services:

- `automatic_selection.py` verifies bounded production summaries and matches
  only their exact primary paths back to hash-pinned catalog entries. It neither
  scores alternatives nor writes a Workbench decision.
- `simple_result.py` copies those exact MIDI files, builds a combined GM proxy,
  reuses the accepted balanced-mix policy, and atomically publishes
  `AUTOMATIC-SONG/` with a path-free receipt and deterministic ZIP.

The automatic receipt says `not_reviewed` and `review_recommended`, reports
omitted roles, records zero human decisions and feedback, and cannot be
mistaken for GarageBand Pack Composer state.

Studio's orientation path is read-only except for starting and stopping
its owned Workbench child process. Loading an unreviewed project does not
create SQLite state.
Existing explicit events are read through SQLite `mode=ro` and may be folded
to report progress, while the public TUI document remains path-free. The
activity view is capped in memory, hides the per-launch token and private
decision-store location, and disappears on exit. Project controls are locked
while the child is active; the child is terminated and reaped on Stop, Quit or
unmount.

The Studio conversion runner adds one typed, explicitly confirmed full-project
write. Its editable output must be fresh. It runs the production `listen-all`
operation in repair mode with candidate-variant evaluation, then runs
`vocal-melody` separately for discovered lead/backing stems. Compatibility
roles are explicit at the adapter boundary: `wind` routes to the `lead`
engine, `rhythm` to `keys`, and `other` to `synth`; those proxies are not
instrument-identification claims. Near-silent sources become visible skips.
Engine output is streamed into bounded in-memory activity.

The TUI owns and reaps its conversion child. Cancellation preserves the
partial fresh tree; a completed Simple run publishes its result only after
verification, while a completed Studio conversion merely reloads candidates.
There is no automatic overwrite, retry, durable job ledger or restart recovery
yet. The runner must not use an arbitrary shell field or reimplement
`listen-all` or `vocal-melody` inside Textual callbacks. Workbench remains
review-only and starts no transcription. See
[Guided Local Studio TUI](LOCAL_STUDIO_TUI.md).

Bass continuity remains an engine concern, not a TUI or Workbench inference.
`transcribe_pitched.py` publishes `octave_resolved` as a separate repair that
preserves note count, timing, velocity and pitch class while allowing dominant
octave-resolved pYIN evidence to correct a harmonic-register error.
`continuous_sustain` starts from that candidate and changes note ends only:
it fills a 35 ms–1.25 beat gap only when source RMS activity, pYIN voicing and
the exact preceding pitch support the gap. Both remain challengers;
`contour_clean` is still repair mode's selected output. MIDI describes the
gate continuity but cannot contain the source waveform's buzz, so Workbench's
bass proxy uses GM 39 Synth Bass 1 and GarageBand patch choice remains
separate.

`midi_mask.py` is an experimental Phase 4 boundary, not a generic separator.
It accepts one explicit note-bearing MIDI track, limits work to a short audio
excerpt, and publishes source, harmonic target and waveform-defined residual
as deterministic PCM24. Persisted target-plus-residual reconstruction, hashes
and zero input-mutation effects are part of its report contract; listening and
re-transcription decide whether either derivative is useful.

`ai_cleanup.py` is the corresponding learned-model boundary. The deterministic
core extracts an immutable PCM24 excerpt, hard-verifies the pinned external
checkpoint, invokes `ai_cleanup_worker.py` in `.venv-ai`, validates the
float32 target, and defines the residual from persisted source minus persisted
target. The worker is CPU-only with zero random shifts and cannot download a
model or promote its output. Because the exact Demucs checkpoint uses PyTorch
pickle serialization, the worker permits `weights_only=False` only after the
complete official SHA-256 has matched. Failed and successful runs both retain
request, logs and hashes.

`midi_role_split.py` is the post-listening arrangement boundary. It consumes
one immutable note-bearing MIDI plus its matching source-event cluster report,
requires the retained body cluster explicitly and writes an exact body-plus-
complement partition. An optional independently transcribed residual becomes a
separate overlapping challenger rather than being silently merged. The module
copies source references into a fresh local review directory, renders
contrasting GM proxies and publishes an unreviewed export; it neither identifies
physical instruments nor promotes a split from clustering metrics.
Its resolver accepts only a complete user-exported review, verifies the entire
source evidence tree and treats the overall decision as authoritative. The
recommended MIDI is an exact copied artifact, never a regenerated or merged
track; useful component auditions remain evidence rather than implicit votes.

`timbre_resynthesis.py` is the fixed-performance sound boundary. It accepts one
short aligned reference and one monophonic constant-tempo MIDI, fits a single
harmonic distribution, sustain ratio and deterministic attack-noise amount,
and renders every note with that common profile. The identical note multiset is
also rendered through complete SoundFont controls. Candidates are level-matched
and checked note by note for functional silence before an unreviewed listening
page is published. The module trains no model, changes no MIDI and does not
claim that the resulting WAV is a GarageBand instrument.

`midi_ab_review.py` is the generic blind listening-evidence boundary for two
already completed MIDI candidates. It accepts one reference WAV, a positive
BPM, an explicit common MIDI time corresponding to reference-source time zero,
and one or more non-overlapping 0.5–15 second source-time intervals. The origin
must land on a source sample frame and is applied to both candidates; alignment
is never inferred. The builder hash-pins the source, both unchanged MIDI files,
FluidSynth executable and SF2; writes private neutral proxies that use the same
zero-based GM program, dry renderer, gain and sample rate; and crops source/A/B
at the corresponding exact rounded frame indices.

Candidate identity is assigned separately per loop from a secret random nonce.
Only its cryptographic commitment is public; the nonce and mappings are stored
only in the separate hash-pinned answer key and never embedded in the seed or
HTML. This is intentionally non-deterministic package blinding, although the
public package contract and media remain independently hash-pinned.

Level policy is intentionally narrow and auditable. Within each interval, the
louder candidate render is attenuated to the quieter candidate's fixed-window
channel-energy sample RMS. The source reference is unlevelled, no candidate is
amplified and no limiter, compression, EQ, time shift or stretch is applied.
Each candidate window must reach at least -60 dBFS RMS. This is not a LUFS,
true-peak or perceived-loudness claim. The browser auto-loops audio and keeps a
separate shared playhead for each review unit. It requires heard checkboxes for
source/A/B plus one explicit A, B, equivalent, neither or cannot-tell choice
before it can export a reviewed JSON.

Resolution requires both that reviewed export and the original unchanged
package directory. The resolver re-verifies its seed, audio manifest, answer
key and original inputs. It allows only status/reviewed-count, heard, choice
and notes fields to differ, and rejects swapped A/B or cross-unit slots and any
changed timing, focus or geometry before revealing per-loop identities as
listening evidence. Immutable comparison is recursively type-strict except for
equal finite JSON numbers, allowing browser canonicalization such as `0.0` to
`0` while rejecting booleans, strings, changed numeric values and structural
changes. Answer-key unit commitments are verified against the original pinned
seed units after that comparison. Neither operation edits MIDI, selects a
Workbench candidate, promotes a preset or changes a default.

The Phase 5 Workbench is a presentation and explicit-decision boundary, not a
new transcription engine. `workbench_catalog.py` hash-pins existing source,
MIDI and preview artifacts and limits the normal result space to three
non-diagnostic candidates. Automatic discovery rejects arrangement-named or
multi-role MIDI, uses an unambiguous basename role before bounded parent-name
fallback, rejects incompatible explicit BPM/key metadata, and removes both
byte-identical and neutral-audition-equivalent note geometry. Layered Clips
with one consistent role remain valid; malformed and note-free role-specific
files remain explicit unavailable/empty diagnostics. An explicit catalog may
intentionally bypass those automatic eligibility rules.
`workbench_store.py` records immutable events in a
local SQLite database and derives current state without updating old choices.
`workbench_semantics.py` defines terminal no-selection outcomes: replay keeps
the old main/optional evidence but marks it inactive until a later explicit
selection reopens that stem. Every arrangement/export consumer repeats that
barrier defensively. `workbench_privacy.py` rejects new path-like musical roles
and projects legacy roles as `custom role` before they reach browser state,
public catalogs, contribution previews, timelines, archive names or proxy MIDI
metadata; private raw history is not rewritten.
`workbench_artifacts.py` owns content-addressed role-neutral previews, private
decoded per-stem/selected-arrangement clips, exact canonical full-song chunk
streams, selected-arrangement proxies, source-referenced balanced selected-MIDI
auditions and deterministic GarageBand handoff ZIPs. `workbench_mix.py` owns
the gain-only balance calculation and its path-free receipt/fader recipe. Both
read through verified source and neutral-preview snapshots. Discovered MIDI is
never rewritten, and numbered handoff tracks are exact copies of explicit
main/optional choices. Rejected, needs-correction, superseded and unreviewed
candidates never enter the arrangement or ZIP.
`workbench_server.py` binds only to `127.0.0.1`, requires a per-launch token,
serves only catalogued or locally generated verified-cache files, supports byte
ranges for media seeking and loads no remote scripts. Its packaged HTML uses a
shared position for playback and records explicit solo or full-mix context only
when the listener presses a save action. Its contribution preview excludes
audio, MIDI, paths, free-text notes, dwell time and play counts; there is no
submission endpoint.
The standalone MIDI A/B package completes the Phase 5.2 beam-listening tooling
and remains a separate blind, fixed-window level-matched promotion gate. Its
page still coordinates browser media elements in seconds, with the playhead
scoped per unit. Workbench now has separate decoded, sample-scheduled per-stem,
bounded selected-arrangement and canonical full-song paths, described below.
The private three-window package
has been generated and verified, while its human
export and resolved result are now complete. Two loops were equivalent and the
3.50–7.50 second loop marginally preferred beam 1; beam 2 won no loop. All
reported mutation, selection, promotion and default-change effects are zero,
so beam 1 remains the execution default.

Phase 5.4 is an interaction-layer extension over these existing boundaries,
not a second transcription engine or a Mirelo clone. Its compare-role slice is
a versioned, hash-pinned per-stem timeline derived from the current catalog:
bounded classic/WAVE_EXTENSIBLE integer-PCM WAV display data beside per-track
MIDI note geometry on the embedded-tempo clock. `/api/timeline` loads the
at-most-three primary candidates by default and accepts explicit candidate IDs
for lazy advanced lanes. It rechecks selected source/MIDI hashes before and
after projection, returns no paths and records zero mutation, ranking,
selection and default effects. Unsupported waveforms and malformed or
oversized MIDI lanes remain explicitly unavailable rather than being silently
omitted.

The primary request includes the source projection. An explicit advanced-lane
request verifies the source identity once but returns only its path-free
reference, then verifies the selected MIDI before and after decoding. The page
keeps the already loaded base waveform, which avoids rebuilding a large source
for every checkbox without treating a stale or different source as equivalent.

Phase 5.5 Decoded Stem Comparison v1 is a bounded audition boundary over those
already catalogued artifacts. `POST /api/decoded-loop` accepts one stem, a
0.5–15 second recorded-time window beginning within the first 24 hours and at
most six unique candidate IDs. The normal UI includes the at-most-three primary
candidates; an advanced candidate is admitted only by an explicit visual
opt-in. Aggregate source audio, candidate MIDI, SoundFont and preview input is
capped at 2 GiB, with oversized declared inputs rejected before rendering;
generated PCM is capped at 64 MiB per request. The owner-only stem and
arrangement decoded caches share at most 32 recent entries or 256 MiB; older
content-addressed windows are evicted and rebuilt on
demand rather than treated as durable state.

Every included candidate preview must match the neutral-preview schema,
current renderer policy and current SoundFont SHA-256 or preparation fails
closed. A missing preview is rendered without changing MIDI. Renderer input
does not rely on a path that can be replaced between verification and use:
candidate MIDI and SoundFont bytes are copied from single open handles into
owner-only hash-and-size-verified snapshots, rendering uses those snapshots,
the originals are rechecked and the snapshots are deleted before publication.
Neutral preview MIDI is capped at 20 minutes.

The same boundary applies to decoding. Source and preview audio are copied to
owner-only verified snapshots and only those snapshots are inspected and
cropped, preventing a replace/restore race from substituting different bytes.
The snapshots are deleted before private content-addressed PCM clips with
path-free public metadata are published. Generated media is verified and
frozen before serving. A short input is padded with zeros to the requested end;
`silence_padded_frames` exposes this per track so the UI can warn that the
silence is generated rather than missing transcription evidence. The warning
uses a separate persistent element so transport-status updates do not erase it.

The decoded-loop artifact uses
`recorded-zero-source-frame-window-level-matched-v2`. Each source/candidate
track carries a verified `common-target-active-block-rms-v1` receipt:
median active non-overlapping 400 ms RMS aims at −18 dBFS, target gain is
bounded to −24…+12 dB, and −1 dBFS sample-peak room can reduce it further.
The underlying source and `role-neutral-general-midi-v3` preview bytes remain
unchanged; the page publishes the signed gains and applies them only through a
Web Audio `GainNode`. Bass neutral rendering uses zero-based program 38,
published as **GM 39 Synth Bass 1 proxy**.

Instrument choice is a sibling review boundary rather than another mode in the
transcription or balanced-mix renderer.
`workbench_instrument_policy.py` is the single source for the supported
server-owned pairs: bass zero-based GM 38/39 (Synth Bass 1/2), and keys 4/5
(Electric Piano 1/2). The
`sunofriend.workbench-instrument-review` contract accepts one currently
selected bass or keys lane and its exact arrangement-selection/MIDI hashes. It
creates two private audition proxies from the same verified MIDI and
SoundFont. Only Program Change bytes may differ; normalised note timing,
duration, pitch and velocity signatures must remain identical and the selected
source MIDI is re-hashed before publication.
Non-zero CC0/CC32 bank selection, cross-track bank/program ordering and a
target Program Change that does not precede every playable Note On are rejected
so the programme identity is effective, including raw same-tick event order.
Effective CC7 volume and CC11 expression must be non-zero at every playable
Note On.

`workbench_instrument_coverage.py` owns the separate keys-only functional
preflight. It constructs one private probe zone for each occupied channel,
pitch and soft/medium/strong velocity bucket, using the minimum actually
observed velocity. CC120/CC123 guards bracket 0.20-second notes in 0.35-second
slots. Both identities must pass within 512 zones and 180 seconds: at least
−72 dBFS RMS, −60 dBFS peak, 3 dB above the pre-note guard, and no more than a
24 dB velocity-normalised deficit from the channel/bucket median when peers
exist. Playable notes on General MIDI channel 10 (zero-based channel 9) are
rejected because that channel uses note numbers as drum identities. The server
validates full private per-zone reports and exposes only anonymous, path-free
aggregate counts, floors and bucket counts after both identities pass. The
synthetic MIDI remains private and rebuildable; raw probe audio is deleted
after measurement and can be re-rendered from the verified inputs. Bass
carries the exact `not_required` coverage contract.

The service crops one exact 0.5–15 second source-reference window and the same
elapsed-time window from both renders. One disclosed policy attenuates the
source and both candidates to the quietest input's fixed-window RMS, rejects
more than 18 dB divergence, and applies one common attenuation-only guard for
a −1 dBFS PCM16 sample-peak ceiling. It never boosts, limits or compresses.
The source remains labelled reference evidence, not a third candidate. The
browser receives anonymous A/B media capabilities and uses one decoded clock.
Review completion records explicit heard, choice, allow-listed problem tags
and bounded notes in a separate owner-only ledger. Resolution is a separate
operation that reveals the committed programme mapping. Neither operation
writes `WorkbenchStore`, changes the selection manifest, promotes an
instrument, rebuilds the balanced WAV or alters a pack.

Coverage success is only `functional_status: passed`; both bass and keys keep
`quality_status: review_required`. It does not establish pitch/octave
correctness, every-velocity response, chord/polyphonic clarity, tone
consistency or source similarity, GarageBand equivalence, or any winner,
recommendation or default. The A/B review still renders the unchanged selected
MIDI and requires listening.

Preparation checks resource ceilings before any copy or render: 64 MiB for
MIDI, 20 minutes for its complete event horizon, 2 GiB each for source audio
and SoundFont, 256 MiB for the renderer and 3 GiB in aggregate. It snapshots
only the exact decoded source window, while the bounded MIDI and SoundFont are
private verified snapshots. This prevents an ostensibly short review from
silently copying an unbounded source or rendering an unbounded MIDI timeline.

This separation matters for maintainability: transcription chooses notes,
the policy module owns role/program pairs, the coverage module answers one
narrow functional question, instrument review compares sounds with notes held
fixed, and arrangement/mastering compares balances only after those earlier
variables are understood.

`workbench_transport.js` decodes those bounded clips, equalises their decoded
frame lengths on one `AudioContext`, and creates fresh source nodes for every
scheduled start or switch. The outgoing stop and incoming start share one
future clock time, while an absolute loop playhead survives the switch. This is
sample-scheduled browser playback, not inferred alignment: source and MIDI
still begin at their recorded zero and no offset is estimated. Preparing,
playing, switching, seeking, pausing and stopping have zero selection, event,
ranking and MIDI-mutation effects. The explicit compatibility fallback retains
second-synchronised, unlevelled HTML media elements and is not sample-accurate,
but its transport controls are likewise feedback- and event-free. Canonical
arrangement and full-song transports remain unity-gain and unlevelled.

Phase 5.6's bounded selected-arrangement extension adds
`sunofriend.workbench-arrangement-selection.v1` and
`sunofriend.workbench-decoded-arrangement-loop.v1`. The selection manifest is
derived only from catalog plus current saved state: every byte-identical source
is represented once, active main/optional MIDI remains distinct, and ordered
source-only, selected-MIDI, hybrid and main-only track-ID groups are hashed
with project/BPM/role/decision/content identity. Review context is excluded, so
an unchanged solo-to-full-mix confirmation does not rebuild audio. Browser
requests contain only the manifest hash and 0.5–15 second bounds; arbitrary
track lists, roles, gains and presets are not accepted. A request has at most
24 total decoded tracks and otherwise shares the 2 GiB input and 64 MiB output
limits.

The server derives and checks the manifest under the state lock, releases it
while rendering, then re-derives it before registering frozen media. A change
from another local tab returns 409 and publishes no stale URLs. Saved path-free
role tags are used as internal neutral-preview role overrides and participate
in the preview cache key; they are never supplied by the browser. The separate
`DecodedGroupLoopTransport` validates a whole preset before creating playback,
starts each incoming node and retires each outgoing node at one shared future
time, and rolls back a partial start without stopping the previous group.
The Workbench preserves that rollback instead of clearing the transport,
serialises async preset ownership across delayed `AudioContext.resume()` calls,
and aborts/stale-guards preparation when its view or loop is invalidated.

The compare-role canvas consumes that contract with a shared playhead; it does
not edit notes or treat visibility as preference. The second slice adds
`sunofriend.workbench-arrangement-timeline.v1` through the read-only
`/api/arrangement-timeline` route. The server derives its rows from
`selected_candidates()` and therefore exposes only current explicit main and
optional MIDI. It groups byte-identical source audio once while retaining all
stem/role labels, never deduplicates selected MIDI, rechecks hashes before and
after projection and returns no paths. Aggregate caps bound it to 24 distinct
sources, 24 selected MIDI lanes and 40,000 rendered notes; an over-budget lane
is explicit unavailable evidence.

Phase 5.7 extracts fixed-window projection math into
`workbench_visualization.js`. Fit-song, 4× and 16× viewports plus paging and
playhead centring paint only intersecting waveform bins and MIDI notes. CSS
canvas width, device-pixel ratio and the arrangement backing-pixel budget are
bounded to 480–1,600 CSS pixels, DPR 2 and a 12,000,000-pixel arrangement
target. Viewports are at least 0.5 seconds; the UI asks for 0.25 seconds of
overscan and the helper rejects more than 5 seconds. Source projections default
to 720 waveform bins per stem and 320 per arrangement source; the API accepts
64–4,096. A four-document in-memory per-stem timeline cache has no
local/session-storage backing. This reduces draw cost only: `/api/timeline` and
`/api/arrangement-timeline` still return their complete server-bounded JSON and
the browser parses and indexes the whole document. Per-candidate limits remain
20,000 notes and 8 MiB, a timeline request accepts at most 12 candidates, and
the arrangement remains capped at 24 distinct source lanes, 24 selected MIDI
lanes and 40,000 rendered notes.

Timeline fetch ownership is abortable and guarded by both request generation
and selection identity. A failed refresh can retain only a previously verified
projection that still matches the current selection; it is marked stale and
gets an explicit retry. With no compatible result the visualization becomes
explicitly unavailable without disabling audio, decisions or export. Canvas
context loss/restoration follows the same visible recovery contract. The URL
hash persists only the current view/stem. Timeline viewport/zoom/visibility,
prepared audio, chunk state, playhead, loop and mixer controls are memory-only
and reset on reload; SQLite decisions, Overview state and the saved pack basket
survive browser and server restarts.

The arrangement selection SHA covers audible candidate identity, role,
decision, MIDI hash and BPM but deliberately excludes review context, so a
solo-to-full-mix reconfirmation does not reset an unchanged audition. The live
mixer is browser-memory state only: visibility, mute, solo, attenuation,
preset, loop and playhead never enter SQLite, selection hashes, overlap
evidence, arrangement caches or handoff bytes. Source-stem, selected-MIDI,
hybrid and main-MIDI presets use lazily loaded source media plus explicitly
prepared neutral MIDI previews. Bounded canonical presets can now use the
Phase 5.6 decoded group transport. Phase 5.7 adds
`sunofriend.workbench-decoded-arrangement-stream.v1` and
`sunofriend.workbench-decoded-arrangement-chunk.v1`. The stream POST accepts
exactly a current selection-manifest SHA and one of `source-only`,
`selected-midi`, `hybrid` or `main-only`; the chunk POST accepts exactly the
immutable stream SHA and chunk index. The browser cannot inject arbitrary
track IDs, roles, groups or gains. The server rechecks current selection before
and after planning and chunk work; drift returns 409 and registers no stale
media capability.
All HTTP POST bodies are capped at 64 KiB.

The stream plan snapshots verified private source and neutral-preview bytes
once. The first source defines the anchor rate, the longest source defines the
end, and every track begins at recorded zero. Deterministic nearest-frame,
ties-even scaling maps each input rate onto exact integer anchor-frame chunk
boundaries. Tracks remain separate PCM16 and shorter inputs are padded with
disclosed silence. `DecodedChunkSequenceTransport` uses one `AudioContext`,
primes up to the first two chunks, retains only current plus next decoded chunks
and schedules a ready successor at the exact non-looping boundary. Missing or late
successor data stops truthfully at the verified boundary. A successor that
finishes late enables explicit Play; missing or failed data requires Retry.
Neither action auto-restarts. Seek also pauses while its required chunk is prepared.
No error silently starts the coarse mixer.

A precise stream is capped at 24 tracks, a 20-minute longest source and 2 GiB
aggregate input across every catalog source required for the song clock plus
relevant selected MIDI, SoundFont and neutral previews. Decoder geometry is
mono/stereo at 8–96 kHz; there are five-second adaptive
chunks, 480 chunks, 32 MiB aggregate PCM16 per chunk and 192 MiB projected
two-decoded-chunk float memory. Chunk artifacts share the rebuildable
32-entry/256 MiB cache with short loops. Per launch, at most 16 active stream
plans and 768 generated-media capability records remain addressable; an
evicted URL returns 404 and is recovered by preparing again. Tracks are unity
gain without matching or limiting, so a dense hybrid can clip.

Full-song immutable input snapshots use a separate owner-only disk LRU capped
at eight streams and 2 GiB. The current stream remains even when oversized.
Prepare/reprepare fully hashes canonical inputs and snapshots. A process-local
eight-stream verified cache lets sequential chunk requests validate selection
identity plus regular-file device/inode/size/mtime/ctime/mode signatures rather
than repeatedly hashing every full-song input. Drift evicts the fast entry and
falls back to complete verification; missing or tampered snapshots fail closed.
Invalid chunk indices are rejected before expensive original-input hashing.

The independent full-song/custom media elements remain the coarse third path:
they share seconds but are not sample-accurate and permit arbitrary
visibility/mute/solo/0–100 attenuation. Precise arbitrary custom mixes remain
deferred. The content-addressed prepared dry proxy remains the reproducible
control.

The optional balanced selected-MIDI artifact is deliberately outside all three
transport contracts. `POST /api/balanced-arrangement` accepts exactly one
current `selection_manifest_sha256`; it cannot accept lanes, roles or gains.
The server validates current state, builds through
`WorkbenchArtifacts.render_balanced_arrangement`, then rechecks the same
selection before publishing. Its cache key pins the project and selection
manifest, BPM, balance policy, SoundFont, source/MIDI/neutral-preview hashes
and sizes. Source and preview bytes are copied through verified owner-only
snapshots; source audio is measured and never included in the result.

`workbench_mix.build_balanced_midi_audition` computes median active RMS from
non-overlapping 400 ms blocks, first gated at −70 dBFS and then within 10 dB of
each file's active peak. Its final partial analysis block is zero-padded to the
same 400 ms without extending the written audio. Each neutral MIDI lane is matched towards its source
level with a −24…+6 dB clamp. Several selected lanes that share one source
SHA-256 are first matched provisionally, then their actual summed waveform is
measured and calibrated towards one source reference. This handles identical
or otherwise coherent alternatives without assuming uncorrelated power. A
source with no measurable active block uses a disclosed
conservative fallback of −6 dB for drums or 0 dB for non-drums.
The longest verified source stem fixes the output horizon. The manifest records
the maximum neutral-preview horizon and any excluded preview tail, preventing
renderer or transcription overrun from extending the source-aligned audition.

The combined drum bus then receives at most 18 dB attenuation using
time-aligned 400 ms windows where both buses are active. It aims for the median
drum/non-drum difference to be at most −2 dB and its p95 to be at most +3 dB.
The overlap gate extends 30 dB below each bus peak while retaining the
−70 dBFS floor; no active overlap means no invented drum trim. Required/applied
gain, exact before/after overlap measurements on one fixed pre-guard qualifying
cohort, clamp state and achieved flags are explicit. Both reported gates remain
the original cohort-selection thresholds; only the after-gain level
differences shift. A
single output gain requests −18 dBFS median active-block RMS. Positive boost is
capped at +12 dB while attenuation is unbounded by an arbitrary floor; peak
protection may attenuate further to retain −1 dBFS sample-peak headroom. Target
error and achieved status are recorded. The PCM24 result must contain no
full-scale sample.
Compression, limiting, EQ, saturation, reverb, chorus and widening are absent.
The report explicitly sets `mastered: false`: this is gain staging, audition
normalisation and sample-peak protection, not LUFS/true-peak or release
mastering.

The v3 renderer and cache verifier now read those schemas, measurements,
limits, labels and mastering boundary from one frozen
`workbench_balanced_contract.BALANCED_MIX_CONTRACT`. This prevents a renderer
policy change from being verified under duplicated stale constants. The next
maintainability boundaries are extending the new narrow Workbench instrument
policy without duplicating it elsewhere, and extracting a small
balanced-artifact service from the larger Workbench artifact module.

A separate `listening_master.build_listening_master` stage accepts the exact
balanced WAV as an immutable control. It uses fixed two-pass FFmpeg
`loudnorm` at −16 LUFS integrated, an 11 LU loudness-range target and −1 dBTP,
then independently measures the actual encoded PCM24 bytes and verifies their
geometry against the exact input frame horizon. Private temporary files are
owner-only from creation; device/inode checks guard publication and rollback.
Its path-free receipt says `mastered: true` and `release_master: false`; it does
not alter the v3 report, Workbench selection or MIDI. The standalone command
publishes to fresh caller paths. Ordinary Workbench instead delegates to
`WorkbenchListeningMasterService`, which binds the exact selection and balanced
manifests, prepares in owner-only pending storage, re-verifies the PCM24 WAV
and receipt, then promotes only after the server has rechecked current
selection/control state. The separate content-addressed cache is restart-safe,
bounded to eight entries/2 GiB and loses no musical decision when evicted.

`POST /api/listening-master` accepts exactly
`selection_manifest_sha256` and
`balanced_arrangement_manifest_sha256`. The browser cannot choose source paths,
targets or FFmpeg filters. Public output exposes only the verified challenger,
receipt, bounded measurements and all-false musical/preference effects. The
balanced v3 control remains the required product output.

The native TUI path uses
`tui_listening_master.ProductionListeningMasterRunner` as a typed, one-at-a-time
adapter over that same service. Its request is only the already verified TUI
project snapshot; it exposes no mastering path, target, filter or policy. The
runner reads and folds append-only Workbench state without creating a database,
resolves the exact current selection/balanced control and checks for a verified
cache entry. Cache hits are reused without an FFmpeg dependency. Fresh builds
first call the shared path-free SoundFile/FFmpeg/`loudnorm` preflight, then
prepare, re-read and compare both manifest hashes before promotion. A mismatch
discards pending work and fails closed. The runner performs one final read
immediately after promotion before it reports success. If an independently
launched Workbench changed either identity in the promotion gap, the promoted
content-addressed entry remains a harmless non-current cache and the TUI fails
closed instead of presenting it as current.

Textual owns only confirmation, protected bounded progress and result
presentation. Project-changing, conversion and Workbench-launch actions remain
locked during the synchronous operation. Quit may be deferred, because there
is no process-safe cancel contract and the UI must not claim a pseudo-cancel.
Creating or reusing the artifact still changes no event, feedback, MIDI,
selection, default, required-product completion or GarageBand Pack. Explicit
blinded A/B feedback is a separate application layer implemented by
`workbench_master_review.WorkbenchMasterReviewService`. It binds the exact
selection, balanced-control and Listening Master manifests, extracts one exact
0.5–15 second frame window, rejects windows below −60 dBFS RMS or requiring
more than 18 dB attenuation, and writes anonymous PCM16 A/B crops within
0.05 dB fixed-window RMS. Only the louder crop is attenuated; the service does
not boost, limit, compress, equalise, resample or alter time.

The review service owns a mode-`0600` SQLite ledger and mode-`0700` private
audio cache outside `WorkbenchStore`. `prepare` and `current` are zero-write
with respect to feedback; `complete` appends one CAS-checked blind response;
`resolve` separately reveals and verifies the nonce-derived assignment. The
loopback server exposes frozen anonymous media capabilities and path-free JSON,
rechecks current product identities under its state lock, and never projects
this evidence into candidate decisions, rankings, product completion or Pack
state. It derives the stable project-scoped local reviewer key itself, so the
browser neither stores nor submits a raw key and only a domain-hashed reviewer
identity reaches the ledger. Exact frame bounds, rather than non-canonical
requested floats, identify a comparison; concurrent identical preparation
accepts only a fully verified cache winner. This is a distinct durable state
plane: comparison sessions, blind
feedback revisions and identity resolutions do not enter the append-only
musical-decision history, while prepared A/B audio remains rebuildable private
cache data. See
[Musical rendering and listening mastering](MUSICAL_RENDERING_AND_MASTERING.md).

`workbench_master_readiness.WorkbenchMasterReadinessService` is a sibling
application boundary, not a mode in the blind-review service. It accepts only
the latest completed and explicitly resolved quality review for the same
project-scoped reviewer across all comparison windows and current immutable
artifacts. Its comparison hash binds the quality review/result hashes and
reuses that review's canonical frame window. It writes direct-identity PCM24
crops at zero applied gain and, on every cache load, re-reads the hash-pinned
exact source frames and requires sample equality. It stores
at most one immutable readiness response per quality result/reviewer; an exact
retry is replayed and a changed retry conflicts. Its audio cache and SQLite
ledger are separate from both `WorkbenchStore` and the quality ledger.

Verified owner-only file reads, exact-frame decoding, PCM16 quality-crop
writing and audio measurements live in
`workbench_master_review_audio`. This shared internal security boundary keeps
the two service schemas, persistence rules and musical questions isolated
while avoiding duplicated file-verification code. The loopback server remains
the only browser adapter: it derives the reviewer key, registers frozen media
capabilities and projects bounded path-free fields. Developer Inspector labels
readiness preparation as private rebuildable cache work, completion as
separate feedback and export as a read.

`sunofriend.workbench-balanced-arrangement.v1` points to the private WAV,
`sunofriend.workbench-balanced-mix-receipt.v1` provenance receipt and
GarageBand fader recipe. The receipt pins project/selection/BPM identity, every
project-source and selected-lane fingerprint, renderer/SoundFont identity,
per-lane and output horizons, artifact hashes and the complete
`sunofriend.workbench-balanced-mix-report.v1` calculation. Every
musical/project effect is false. Creating or playing the artifact does not alter
the unity dry proxy, selected MIDI, precise transports, decisions, ranking or
feedback. It is Workbench-only and is not a Pack Composer item or standalone
CLI output.

The balanced cache is rebuildable and bounded independently to eight entries
and 2 GiB. A public media capability never streams a mutable balanced file
after merely checking it: WAV, receipt and recipe bytes are copied and
hash/size verified into a per-request disk-backed anonymous snapshot first,
then full or Range responses seek within that frozen snapshot. Drift returns
409. Failure to allocate temporary snapshot storage returns 503. This avoids
both a verification-to-stream race and loading a possible 20-minute PCM24 WAV
into memory.

The GarageBand Pack Composer translates explicit checkboxes into a versioned,
path-free plan, canonical basket and deterministic ZIP. Its v1 inventory
contains each current main/optional MIDI track unchanged, one optional dry
arrangement proxy and deduplicated source audio behind a separate explicit
opt-in. Selected MIDI and the proxy are checked by default; source audio is
not. Plan, scope and basket hashes reject stale builds, and the builder
rechecks the exact input bytes before copying them. Basket revisions live in a
dedicated append-only `pack_selection_events` table, separate from musical
decisions, private reviews and contribution previews. The original
source-audio-free handoff route remains unchanged for compatibility.
No active selection produces a blocked, inspectable empty plan; the browser
routes back to Project Overview instead of offering an empty build. A
two-launch loopback integration test verifies restoration of decisions and a
non-default basket under a fresh capability token while GET routes remain
effect-free.

Alternative MIDI, Instrument Bundles, persistent mixer projects, custom-mix
rendering and the balanced-audition WAV/receipt/recipe are not implemented as
Pack Composer v1 items. Canonical selected arrangements now have bounded and
chunked decoded audition paths, while the arbitrary custom mixer remains coarse
HTML media. All audition transports and the optional balance derivative stay
separate from ZIP composition.

Phase 5.9 adds a report-only learning and local acceptance boundary beside the
deterministic ZIP. The builder creates a neutral
`sunofriend.workbench-garageband-pack-acceptance.v1` seed and a self-contained
HTML page after the ZIP bytes exist; neither artifact is placed inside the
pack. The loopback server exposes only the frozen HTML through a random
capability URL with a no-connect review CSP and sandbox. The seed remains a
private cache record and is never returned with a local path.

The tutorial has eight fixed slides. The quiz has exactly 10 fixed questions,
one visible at a time, and requires 10/10 before the two human checks unlock.
Browser edits are limited to viewed slides, quiz answers, two check outcomes,
item answers and private notes. Export is a user-initiated Blob download; there
is no POST, event, upload or telemetry route.

`garageband-pack-resolve` treats the exact downloaded ZIP as the source of
truth. It independently enforces the canonical v1 receipt key set, safe
generated archive-name forms, unique basket item identity, the intentional
two-file/single-item proxy exception, count/opt-in consistency and streamed
payload hashes without extraction. It rebuilds the neutral seed, recomputes
the quiz and mechanically validates both human outcomes. The path-free
`sunofriend.workbench-garageband-pack-acceptance-result.v1` omits private note
text and the private review-file digest, binds only a canonical redacted copy
of the resolved choices, and declares every project effect false. A stale or
tampered cached ZIP, seed or HTML page is rejected and rebuilt from current
catalogued bytes rather than served as a cache hit.

A `passed` result can open only the first read-only Phase 6 Clip Library slice.
It is not an automatic phase transition and does not satisfy the separate
Phase 5.3 blind-choice/source-lineage prerequisites for hybrid construction.
When no catalog downbeat is pinned, the result labels a listened pass as
reviewer-observation-only rather than manufacturing exact downbeat evidence.

The 22 July 2026 result passed that boundary: eight tutorial screens, a 10/10
quiz and both six-item human checks passed without an issue or `cannot_tell`
answer. The accepted pack contained five selected MIDI payloads, the dry
arrangement proxy and no source audio. The resolver verified the exact member
set, receipt, payload sizes and hashes and declared every project effect false.
Its downbeat remains reviewer observation, not catalog metadata. The result is
path-free and contains no private note text.

Phase 6 Increment 6.0 is complete as a separate gated read-only
projection. `workbench --clip-library --phase6-acceptance --phase6-pack`
requires all three values together. Before opening the explicit existing
library, the server verifies the passed result and exact pack; ordinary
Workbench has no Clip capability when all three are absent. The library opens
through independent SQLite and application read-only guards, and all catalog
objects and lineage links are hash-checked.

The browser may receive bounded browse/search results and path-free detail,
then request deterministic MIDI reconstruction and an optional dry neutral
render. Derived artifacts use a separate rebuildable cache. They are not added
to the library. The reconstruction expresses Clip v1's canonical musical and
timing contract; it is not an original-SMF byte copy. No source path, source
URI, private provenance/note or transform parameter enters the browser.

This boundary has no library, Clip, source-candidate, project-decision, basket,
feedback or submission effect. It does not expose transforms, writes,
piano-roll editing, arrangement placement or hybrid construction. The latter
remains behind the Phase 5.3 blind-choice and source-lineage gates. See
[Phase 6: Creative Arrangement and Reusable
MIDI](PHASE6_CREATIVE_ARRANGEMENT.md).

The real-browser completion check exposed 73 verified Clips across 51
lineages, traversed browse/detail, built deterministic MIDI and a dry
FluidSynth proxy, observed a repeat content-addressed cache hit, byte-range
served both path-free artifacts and traced the operations through the optional
Developer Inspector. Every musical, Clip-library and pack-state mutation
remained zero. Broader Phase 6 remains in progress; transforms, piano roll,
current-arrangement placement and hybrids are still outside this completed
boundary.

Phase 6 Increment 6.1 adds placement only as a separately gated proposal.
`--enable-clip-reuse-plan` is valid only beside the three Increment 6.0 inputs;
without it, the proposal endpoints and state plane do not exist. The browser
keeps **Browse Clips** and **Proposed reuse plan** separate. A place action
supplies only the current plan identity/revision/hash, exact `clip_id` and
object SHA-256, plus a whole-beat target. The server derives all other Clip
facts from the verified read-only library. Removal appends a tombstone; a move
is an explicit remove followed by an explicit place.

`workbench_reuse.py` contains `WorkbenchClipReuseStore` and
`WorkbenchClipReuseService`. The store owns an append-only owner-only SQLite
state plane at `STATE_DIR/phase6-reuse/reuse.sqlite3`, created lazily on the
first explicit action. An empty GET does not create it. The service pins the
project identity/setup/source hashes, resolved acceptance and pack hashes,
complete library state, policy and fixed planning grid. Only an exact binding
restores after restart. It validates immutable object identity, the positive
project BPM and bounds before appending, and computes path-free compatibility
warnings without transforming the Clip.

The first explicit write uses an owner-only sidecar file lock. Writers hold an
exclusive cross-process lock across lazy schema publication and the optimistic
head-check/insert transaction; readers of an already-visible database take a
shared lock before querying. This prevents a second Workbench process from
observing the SQLite file before its append-only schema exists. A concurrent
loser reaches the normal stale-plan conflict instead of being misreported as
evidence corruption, while empty reads remain storage-free.

`workbench_server.py` exposes token-protected
`GET /api/clip-reuse-plan` and `POST /api/clip-reuse-action` only when enabled.
Optimistic concurrency uses the plan ID, SHA-256 and revision. A conflict
cannot replay a mutation: `workbench_clips.js` reloads current proposal state
once, preserves the draft where possible and requires a fresh explicit submit.
The optional Developer Inspector maps those routes to `clip_reuse.read` and
`clip_reuse.change`, exposing only a bounded path-free summary.

The planning grid is 4/4 and 480 ticks per quarter note, permits only whole
beats and treats bar 1/beat 1 as recorded zero. It does not claim a confirmed
downbeat or time signature, and it reports but does not apply existing project
downbeat evidence. Bounds are 64 active placements, 512 events,
20,000 notes per Clip, 40,000 active note instances and a 20-minute nominal
end. The proposal state is independent of musical decisions, Clip/library
state, the current arrangement and the Pack Composer basket. Increment 6.1
does not add a transform, render/play, export, instrument attachment, feedback,
submission, piano roll or hybrid path. Focused/full and real local
restart/browser verification passed, completing Increment 6.1 without
completing broader Phase 6.

Phase 6 Increment 6.2a adds a different, mutually exclusive controlled-write
boundary. `--enable-clip-transforms` is valid only with the three Increment
6.0 evidence inputs and cannot be combined with `--enable-clip-reuse-plan`.
That separation is structural rather than cosmetic: reuse v1 pins the complete
library state, while a transform intentionally appends a new library version.
Transform first, then restart under the new state and place explicitly.

`workbench_transform.py` owns the typed projection/create operation. A
projection resolves one exact parent Clip and performs either a same-mode key
transpose or one musical/stem-locked BPM retime in memory. Its path-free audit
is bound to the parent Clip/object, complete library state, normalized request
and projection SHA-256, and has no durable effect. Creation accepts only that
current projection and uses an expected-catalog-state append to add one
immutable child. `MidiClip.child`, `TransformRecipe` and the existing pure
functions in `transform.py` remain the musical implementation; the Workbench
layer adds authority, bounds, state pinning and public projections rather than
duplicating their algorithms.

After the controlled append, `WorkbenchClipService` re-captures every object
and lineage and adopts the new state only when every old row/object is
unchanged and the exact expected child is the sole addition. Unexpected drift
fails closed. The parent is never mutated or hidden, and historical branches
are identified by exact Clip/object/parent hashes rather than treating a
revision number as unique. The browser invalidates a projection whenever the
draft changes, never retries a failed create automatically and labels the
opened lineage item as “viewing,” not “current” or “best.”

The only true effects in a fresh-created result are the library append, child
version creation and transform applied to that child. An exact idempotent
replay returns the existing child with every effect false and no additional
catalog row or object. Decisions, selected arrangement, old reuse-plan
storage, Pack Composer, instruments, feedback, submission and source
candidates are separate and unchanged. At the accepted 10,000-Clip boundary
the capability disables new preview/create actions. Tuning and
downbeat remain outside this boundary because Clip v1 does not preserve the
complete pitch-bend/RPN or original-SMF event streams required by the existing
raw-MIDI operations.

The create-only replay path also handles two already-open Workbench processes.
It may recompute from its verified preview baseline, but adopts a newer catalog
only after proving that the deterministic requested child is its sole delta.
Thus identical requests become one create plus one replay, while a different
transform or unrelated external append remains a conflict. Ordinary browse,
detail, preview and capability reads never use this exception and remain strict
against any unexpected library drift.

Phase 6 Increments 6.3a–e reuse that sole-child append
boundary but give it a separate authority flag and sealed note-edit policies.
`workbench_correction.py` keeps the published pitch-v1 facade and dispatches an
explicit `attack_velocity_patch` to the isolated policy in
`workbench_velocity.py` or `note_delete_patch` to the isolated policy in
`workbench_deletion.py`. The bounded `note_onset_shift_patch` dispatches to
`workbench_onset.py` and retains operation `shift_note_onsets`. The bounded
`note_end_shift_patch` dispatches to `workbench_duration.py` and retains
`shift_note_ends`. All use a
bounded half-open integer window at 480 TPQ
resolved through the Clip's existing automatic export timing. The four-key
pitch window request and its hashed public serializer remain byte-compatible;
velocity, deletion, onset and note-end windows add their explicit
correction-kind discriminators. The published earlier schemas, hashes and
retained recipes remain frozen.

Because Clip v1 intentionally has no mutable note ID, an editable note is
addressed by its canonical parent index plus a digest over the parent object
hash, index and complete `ClipNote` payload. The parent pin makes the index
stable, the digest detects stale/tampered input and the index distinguishes
otherwise identical duplicates. A pitch patch changes only 1–64 selected
pitches by at most two octaves. Drum-family Clips and any pitch edit that newly
introduces an ambiguous same-pitch MIDI overlap or duplicate onset are
rejected. An attack-velocity patch changes 1–64 selected Note On velocities to
exact integers from 1–127 and is valid for pitched and drum-family Clips.
Source notes that collapse to the same exported channel/onset/pitch are shown
but blocked because they do not have a one-to-one MIDI event.

The completed 6.3c `note_delete_patch` names 1–64 unique exact existing note
references and retains operation `delete_clip_notes`. It is valid for pitched
and drum-family Clips and must leave at least one note. Eligibility and patch
validation normalize the parent and proposed child and prove that the latter is
exactly the former minus the named intervals. They also prove every survivor
is exact and that beat, export and source horizons are unchanged. Notes in
duplicate or cascade-dependent export groups, horizon-changing notes and the
only remaining note are non-editable. This prevents one source-object deletion
from changing a different normalized MIDI interval.

Before either live projection or restart audit, the correction service also
validates the complete preserved SMF encoding boundary: at most 20,000 notes
and 20,000 chords, four-byte variable-length note/chord/tempo event ticks,
three-byte tempo values, byte-encodable time signatures and bounded UTF-8
title/chord meta payloads. A maximum-safe-tick child is write/read round-tripped
in tests; a max-plus-one event is rejected.

Projection and creation use the same intent/projection/CAS/replay rules as the
key/BPM service. The deterministic child's recognized correction recipe keeps
a bounded exact before/after audit. On later detail reads, the correction
service validates that recipe against the retained exact parent before exposing
a path-free summary; arbitrary transform parameters remain hidden. Each child
contains exactly one correction kind. Key, chords, instrument, provenance,
unaffected notes and all project/reuse/pack state remain unchanged. Pitch,
velocity and deletion children also preserve timing and source seconds. Pitch
children preserve velocity; attack-velocity children preserve pitch, release
velocity and articulation.
Deletion children preserve every field of every surviving note plus chords,
tempo, key, time signature, instrument, provenance and all project/reuse/pack
state. Only note count and the explicitly named intervals differ. A fresh
deletion child may set only `library_mutated`, `child_clip_created`,
`correction_applied`, `note_count_changed` and `note_deleted` effects; replay
and restart validation have zero effects.
One recipe contains one correction kind, so removal, onset shift or note-end shift never shares
a child with pitch, attack velocity or another correction kind.

The 6.3d onset service addresses an existing note by the same exact canonical
reference and accepts one integer `target_start_tick` for each of 1–64 notes.
The non-zero delta is bounded to ±480 ticks. It moves the emitted Note On and
matching Note Off by the same amount, preserving normalized MIDI duration,
pitch, attack/release velocity, articulation and note count. Both old and new
full intervals must fit the loaded half-open window. Pitched and drum-family
Clips are eligible; the service performs no snapping, quantisation, theory
repair, F0 inference or preferred-time selection.

The onset policy exposes exactly four row-level block reasons:
`context-note-outside-window`, `duplicate-export-note-on`,
`normalized-lifetime-dependent` and
`unsupported-stem-locked-microtiming`. It also rejects target overlaps,
duplicates and normalization cascades, negative or VLQ-overflow ticks, window
escape and any global beat/export/source-horizon movement. In `musical` mode it
adds `delta / 480` to `start_beat`, keeps `duration_beats` and both microtiming
fields, and derives source seconds through the retained tempo map. In
`stem_locked` mode it accepts only notes whose two microtiming fields are
exactly zero, moves source start/end by
`delta * 60 / (export_bpm * 480)`, preserves source duration and derives beat
coordinates. Both paths must round-trip to the exact requested MIDI ticks.

Onset preview and restart audit have every effect false. A fresh create may
set only `library_mutated`, `child_clip_created`, `correction_applied`,
`note_onset_changed` and `note_timing_changed`; an exact replay is all false.
The capability schema stays at v2 and deliberately retains generic
`timing: false`; support is advertised only through the explicit
`note_onset_shift_patch` entry and `maximum_onset_delta_ticks: 480`.

The 6.3e duration service uses the same canonical references but accepts one
integer `target_end_tick` for each of 1–64 exact existing pitched or drum
notes. Each non-zero delta is bounded to ±480 ticks, must retain at least one
tick of duration and must keep both the source and target full intervals
inside the half-open window. Only the normalized Note Off, `duration_beats`
and `source_end_seconds` may change; Note On, pitch, attack/release velocity,
articulation, note count and unaffected notes remain exact.

The note-end policy exposes the same four block reasons as onset shift. Its
target validator rejects crossing the next same-channel/same-pitch onset,
changing a normalized neighbouring lifetime, escaping window/MIDI bounds or
moving a beat/export/source horizon. In `musical` mode it adds `delta / 480`
to `duration_beats`, preserves the onset and both microtiming values, and
derives source end through the tempo map. In `stem_locked` mode it requires
zero microtiming, moves source end by
`delta * 60 / (export_bpm * 480)` and derives duration beats. Both modes must
round-trip to the requested Note Off tick.

Its public contracts are
`sunofriend.workbench-clip-note-end-window.v1`,
`sunofriend.workbench-clip-note-end-preview.v1`,
`sunofriend.workbench-clip-note-end-result.v1` and
`sunofriend.workbench-clip-note-end-summary.v1`. The capability remains v2
with generic `timing: false` and advertises
`maximum_note_end_delta_ticks: 480` plus
`minimum_note_duration_ticks: 1`. Preview/replay/restart are all false; fresh
creation may set only `library_mutated`, `child_clip_created`,
`correction_applied`, `note_duration_changed` and `note_timing_changed`.
The browser's restored-summary validator independently requires the exact
child, lineage, timing, diff and complete all-false effect evidence; a malformed
field fails closed instead of being reconstructed from nearby detail state.
The browser separately validates the exact kind-specific preview/result
schema, all request and library pins, deterministic `sf-correction-<intent>`
identity, one-to-one server diff and the complete fresh/replay effect map. It
never fills absent server diff rows from its draft. A value equal to the
current draft is an inspection no-op and cannot discard accepted review
evidence. Public correction windows redact path-like articulation values; the
note-end diff and restart summary expose only their bounded change fields.
Regression
coverage also constructs normalized cascade and horizon-changing deletion
cases and requires them to fail before an immutable child can be appended.

`--enable-clip-corrections`, `--enable-clip-transforms` and
`--enable-clip-reuse-plan` are separate mutually exclusive launch modes. Note
insertion, release velocity and continuous expression remain
later contracts rather than being interpreted through pitch correction,
attack intensity, deletion, onset movement or note-end movement. Release velocity remains
deferred because every audited local Clip currently carries zero there and DAW
patch support for Note Off velocity varies. Increments 6.3c–e are
complete while broader Phase 6 remains in progress. The 6.3c copied-Lidl
exercise changed
one channel-9 Snare note at ticks 140487–140573, reduced both Clip and
normalized-MIDI counts from 249 to 248, kept beat/export/source horizons exact,
replayed with all effects false and reconstructed deterministic child MIDI at
SHA-256
`1e3e20d607c62b7b6c06d210b9f3fa90c1f126166aadcf86d82d870d83f5535c`.
The focused integrated suite passed 81 tests, the independent audit passed 49
and the complete repository suite passed 970 tests. The single warning is the
existing `resampy`/`pkg_resources` deprecation notice.

The 6.3d copied-Lidl exercise in
`work/ai-bakeoff/lidl-phase6-onset-smoke-v1` preserved the 12-Clip source and
grew only the copy to 13. Parent Keys Clip
`a6112b69031a233a54531128dca4925f32d5b3b32ce5552daaa6393d0138d8aa`
(object
`d37975c915e790e290650cf5b48e316c19318c28bd1a50c3de342e889180356a`)
produced child
`sf-correction-495e77ba31528090cc979465459d50acf9ad8f4e36f8a783e9f30398703d5727`
(object
`e70a297a01be3a086f5fa05e8dabb47975e6b634dd1adfc4e8c17565524932a2`).
Both have 1,727 notes. Channel-1 pitch 66 moved 442–873→472–903, exactly
+30 ticks/+31.512625 ms with its 431-tick duration unchanged. Beat, export and
source horizons remained 462.6458333333333 beats, 222070 ticks and
233.26695445833332 seconds. Fresh effects were exactly `library_mutated`,
`child_clip_created`, `correction_applied`, `note_onset_changed` and
`note_timing_changed`; replay and restart were all false. Parent and child MIDI
SHA-256 values were
`e741334f8dfc1421850618d088b382a5fc051fc1fada4797ac742a1dcd201036`
and
`20b1298550568bb51cdb98c4d8e342a4ac27e22b2cd58f5e03f48f062cad7d9b`.
The focused suite passed 101 tests; the adversarial audit passed 17 onset and
82 broader correction/server/UI tests. The complete repository suite passed
990 tests in 282.58 seconds with the one existing third-party
`resampy`/`pkg_resources` deprecation warning. This closes deterministic
engineering evidence only, with no human preference claim.

The 6.3e ignored smoke at
`work/ai-bakeoff/lidl-phase6-duration-smoke-v1` has report SHA-256
`d0141814026c434c4702a9c7dcd00466fd6502921bb5e0fa1b437657d675bb77`.
It preserved the 12-Clip source and grew only the copy to 13. Parent Keys Clip
`a6112b69031a233a54531128dca4925f32d5b3b32ce5552daaa6393d0138d8aa`
(object
`d37975c915e790e290650cf5b48e316c19318c28bd1a50c3de342e889180356a`)
produced child
`sf-correction-067bbbfc65e112ba175da84648f2b74f40b5cb5137eabb5f91ff28f4af9f03f6`
(object
`14fee0a6ac7dbc29043199e30041adc93c59eda34fccd8a6a9a15d972846281f`).
Both have 1,727 notes. Channel-1 pitch 66 retained onset tick 442 while Note
Off moved 873→903, +30 ticks/+31.512625 ms and duration 431→461 ticks.
Beat/export/source horizons stayed 462.6458333333333 beats, 222070 ticks and
233.26695445833332 seconds. Parent MIDI SHA-256 was
`e741334f8dfc1421850618d088b382a5fc051fc1fada4797ac742a1dcd201036`;
child and repeat were
`27d5be64a4e992548c6a58139f8a7fb677e3d7f4cefc55ea4e2fc163b74fa918`.
The focused integrated correction/UI suite passed 133 tests, the real smoke
passed and the complete repository suite passed 1009 tests with the one
existing `resampy`/`pkg_resources` deprecation warning. This is deterministic
engineering evidence only, not a human preference claim.

An optional explicit-catalog phrase link validates one existing diagnostic
S0/M1/M3 hybrid report against its exact stem, three current candidate MIDI
files and the pinned unresolved melody phrase-review package. The public
`sunofriend.workbench-phrase-review-link.v1` projection contains ranked ranges,
candidate IDs, limited-lineage statuses and hashes but no paths. It does not
change `sunofriend.workbench-timeline.v1`, run a model, rank candidates or
append state. The HTTP server registers only the pinned phrase page and its
semantically allow-listed source, MIDI-only and overlay WAVs behind a random
per-launch capability path; it rehashes every response, supports audio byte
ranges and denies the manifest, MIDI, correction seed, evaluation JSON and
arbitrary siblings. The private page uses a stricter `connect-src 'none'`
policy, disables autoplay and runs under a sandbox that permits its existing
scripts, alert dialogs and reviewed-JSON download but not forms, popups or
top-level navigation.

`ai_matrix.py` applies a model-neutral quality/report schema to already
completed immutable runs from one controlled backend, checkpoint, model config
worker, runtime version and execution profile. It verifies request, candidate,
raw artifacts, MIDI,
source, worker, checkpoint and model-config hashes, then publishes path-free
aggregate/per-instrument quality,
requested/detected-label differences, five-second-boundary activity, label
stability and cross-lane same-pitch/onset overlap. It reports zero raw/MIDI
mutations and cannot promote a candidate. `ai_bakeoff.py` owns the normalized
MuScriptor execution contract: the pinned 0.2.1 baseline is greedy, batch 1,
beam 1 and CFG 1.0 with independent five-second chunks. Because that runtime
does not expose prelude forcing, the manifest records it as unsupported and a
true request is rejected.

`hybrid_report.py` is the first Phase 5.3 boundary outside that model-only
matrix. Its v1 contract is lead-melody only. It verifies one exact excerpt WAV,
its unresolved melody phrase-review geometry, and the existing S0 specialist,
M1 full-mix-label and M3 conditioned-stem MIDI plus their distinct evidence
schemas. MIDI is interpreted in source seconds
and compared through `note_alignment.py`, the shared deterministic one-to-one
onset matcher also used by the matrix, setting comparator and Workbench overlap
diagnostic. Its explicit legacy nearest-unused policy preserves existing v1
matrix/setting metrics, while the hybrid and Workbench use chronological
maximum-cardinality matching. The path-free report projects only validated,
schema-owned phrase/repetition fields, preserves source phrase indices and
every candidate note, then publishes per-phrase exact-pitch/onset matches,
cross-phrase boundary references, boundary/duration disputes,
octave-equivalent disputes, lane-only notes, duplicate evidence and raw
`StemSpectrum` support. Gaps outside phrase units are counted rather than
discarded. S0 provenance must resolve to the same supplied source file, not a
separate equal-content copy. Chords remain unavailable until an exact excerpt timeline is
hash-pinned. S0 and the projected M3 excerpt are checked against the supplied
source bytes; M1's requested-label MIDI is checked against its report and
tick-level render signatures. The M1 full-mix-to-song relationship remains a
caller-supplied, derivation-unverified association because no reproducible mix
manifest exists. M3's original pre-projection MIDI hash is recorded but its
unsupplied payload is not verified. This layer rechecks every input after
analysis, starts no model, emits no MIDI, performs no automatic selection or
repair and is not yet imported by the Workbench.

Fresh MuScriptor workers keep nondeterministic execution measurements in the
separate hash-pinned `muscriptor.performance.json` raw artifact rather than in
the candidate JSON. `ai_benchmark.py` reuses the matrix verifier, then compares
only runs with equal source, requested and actual excerpt, BPM, roles, effective
device, execution identity and path-free platform/Python/PyTorch/MuScriptor
runtime identity. Its atomic path-free report separates parent pipeline wall
time, worker subprocess time and inclusive transcription time; records
first-note/chunk, chunk count and process-RSS evidence; and checks exact
candidate/MIDI repeatability. Candidate duration must match the request clipped
to the verified source frames, pipeline/subprocess/worker times must nest, and
timezone-aware repetition windows must not overlap. Inclusive transcription is
iteration of MuScriptor's lazy transcription generator and therefore includes
its preprocessing, condition construction and decoding. Current workers are
fresh per repetition and reload the model, so the report declares the OS cache
uncontrolled and cannot claim a warm model or promote a candidate.
Pre-session/cache v1 manifests without the newer execution fields remain
readable only while all hash-pinned external evidence still matches and under
a narrow legacy contract: successful non-empty subprocess command, null worker
transport and no cache artifacts. In particular, a historical run pointing at
a worker file that has since changed cannot be re-verified. The report counts
and labels accepted legacy rows instead of silently treating them as current
evidence.

`ai_setting_compare.py` is a stricter read-only two-arm verifier layered on the
same immutable matrix and fresh-process benchmark checks. Its v1 contract
accepts at least two exactly repeatable current runs per arm and permits one
declared semantic difference. `--setting beam-size` compares control beam 1/
greedy with challenger beam 2/beam-search. `--setting batch-size` compares
batch 1 with batch 2 while requiring beam 1/greedy, sampling disabled and the
same independent five-second chunks in both arms. It rejects legacy, session,
application-cache, overlapping, non-repeatable and multi-setting evidence. A
candidate JSON change is treated as provenance until the canonical note payload
or MIDI also changes. In batch mode, MuScriptor's first positive progress event
represents one completed chunk in the control and two in the challenger;
`time_to_first_completed_chunk` is omitted from direct comparison and the
unlike completed-chunk counts are reported explicitly. The atomic report
whitelists path-free hashes, quality, label, boundary and performance
diagnostics, mutates nothing, selects no winner and cannot promote a preset.
Run order and the operating-system file cache are uncontrolled, so its timing
ratios are not causal speed evidence; changed music requires an explicit
same-renderer, same-patch and separately verified level-matched listening
review.

The bounded MuScriptor session is a distinct diagnostic execution boundary.
`ai_session.py` prepares one immutable request template and starts one
parent-owned worker for 2–20 exact serial repetitions. `ai_worker_session.py`
creates an inherited Unix socket pair rather than a listening socket, pins the
worker/template/source/checkpoint/config identities, enforces contiguous
request sequence and exact template equality, and reaps the process on close,
failure or interruption. `ai_worker.py` loads the model before its ready
message, handles no more than the declared request count and exits. It is not a
daemon, production role queue, multi-song API or application content cache.

Each repetition still passes through `ai_bakeoff.py`, producing the normal
immutable candidate, MIDI, quality, expression, provenance and run manifest.
Only the transport and performance schema differ. Startup and model-load
timing live in session-level evidence; each request records its own inclusive
transcription and parent round-trip evidence. Request 1 has an already resident
model but no prior transcription to reuse, so it is neither a warm-request
measurement nor a cold-start claim. Requests 2 and later are the only
reused-model warm measurements. Application cache hits are always zero and the
operating-system file cache remains uncontrolled.

The session root is a private, path-bearing evidence tree containing the fixed
request template, started/ready/closed lifecycle records, worker logs and one
normal run directory per repetition. Successful close re-hashes the source,
checkpoint and adjacent model config. Each request is byte-matched to the
startup template, while the read-only verifier rechecks the pinned worker and
template. The session
cannot select, promote or mutate a candidate and does not alter the Workbench.
`ai_benchmark.py` deliberately rejects these repetitions because its schema is
fresh-process-only.

`ai_session_benchmark.py` performs the read-only publication boundary. It
re-verifies the full session tree, exact output repeatability, serial timing,
single model instance/load and warm-request flags, then publishes only
whitelisted path-free fields. With `--fresh-run`, it requires at least two
strictly comparable, repeatable fresh-process controls before calculating
warm-to-fresh ratios. Path-free is a structural privacy property, not consent:
content hashes and platform/Python/PyTorch/MuScriptor identity can still be
identifying. No session or benchmark action downloads a checkpoint or changes
its licence terms.

The application cache is a third, mutually exclusive execution regime.
`ai_cache.py` builds a canonical path-free key from source content and audio
layout, the exact ordered request (including excerpt and BPM), deterministic
MuScriptor options, checkpoint/config/worker hashes and runtime/device
identity. It stores only the verified raw candidate and the original
fresh-process `muscriptor.performance.json` under a private content-addressed
namespace. Source audio, checkpoints and derived MIDI are not cache payloads.
The cache root is owner-only: a missing root is created with mode `0700`, while
an existing root with any group or other permissions is rejected.
Every verified hit is copied into a fresh immutable run without hard links;
`ai_bakeoff.py` then repeats current quality assessment, GM mapping,
source-expression recovery and MIDI derivation. A hit has an empty worker
command and explicit false worker/model/inference flags. Invalid, linked or
inconsistent entries fail closed without an inference fallback.
Concurrent identical misses publish exactly one entry. A losing producer is
recorded as `miss-verified-existing`: inference ran, the winning raw candidate
was verified identical and the producer keeps its own timing, but that status
is not the `miss-stored` control required by `ai-cache-benchmark`.

`ai_cache_benchmark.py` re-verifies one `miss-stored` run and at least two
serial `verified-hit` runs against one immutable entry. It separates current
lookup, materialisation, post-processing and pipeline timing from the copied
origin-inference timing and writes a fresh report without paths or
caller-supplied run IDs. Hashes, timestamps and runtime identity remain
potentially identifying. It cannot promote or mutate a result. Fresh
`ai_benchmark.py` rejects every cache-enabled run;
`ai_matrix.py` rejects cache hits so the original fresh miss remains the
musical evidence lane.

The four caching/reuse terms are deliberately distinct:

| Mechanism | What is reused | Does inference run? | Evidence meaning |
| --- | --- | --- | --- |
| Bounded MuScriptor session | One resident model inside one bounded worker | Yes, for every request | Requests 2+ are reused-model warm; no application-cache hit |
| AI application cache | One prior verified raw MuScriptor result | No, on a verified hit | Current cache/pipeline timing plus separate original inference evidence |
| Workbench preview cache | A deterministic FluidSynth audition proxy for existing MIDI | No transcription is requested | Rendering reuse only; it does not avoid or claim AI inference |
| Operating-system file cache | Uncontrolled filesystem pages | Unknown and uncontrolled | Never sufficient for a cold-, warm-model- or application-cache claim |

When a Workbench candidate is adjacent to a completed AI run,
`workbench_catalog.py` attaches the same path-free diagnostics. Severe decoder
codes and zero-note results are diagnostic-only and cannot be rendered or
selected as main/optional; ordinary label leakage remains reviewable.
For an application-cache hit it labels elapsed time and real-time factor as
pipeline-not-inference and states that no worker, model load or inference ran.
For a `persistent-session-request`, it calls the complete closed-session
verifier before publishing
`sunofriend.workbench-ai-execution-provenance.v1`. The projection contains only
the request sequence/count, prior request count and the verified first-request
or reused-model-warm state; it omits the session/worker identities and paths.
A missing or changed parent manifest, run hash, worker response, performance
record or sequence fails catalog discovery. Fresh subprocess and exact-result
cache states use the same schema. Every state records false Workbench
optimisation and musical-agreement effects.
`workbench_server.py` and `workbench_artifacts.py` reverify hashes at each
serve, render, arrangement and handoff boundary so catalog discovery cannot be
invalidated silently by a later file change. The pinned SoundFont is rechecked
before cached use for the same reason.
Automatic discovery resolves sources, MIDI and previews and rejects symlinks
outside the explicit project/candidate roots before adding them to the
token-protected media map. Stem state identifiers include source content, role
and filename so byte-identical stems do not share SQLite decisions.

Instrument matching deliberately has two adapters rather than a private DAW
integration: installed GarageBand/Logic sample assets are profiled directly,
while candidate MIDI programs are rendered through the existing FluidSynth
boundary. The output is an audition shortlist. Stem-derived sample instruments
write cleaned WAV/SFZ assets plus a narrow, self-contained SoundFont 2.01 bank
that Apple's public sampler interface and FluidSynth can load. They never
mutate Apple factory content, private patch files or GarageBand project bundles.

`instrument_usability.py` is the boundary between successful artifact creation
and a usable musical instrument. It tests the generated zones against the
actual selected MIDI track for key/velocity coverage and effective one-shot
duration. A failure demotes the bank to an optional texture layer in Instrument
Bundle v1; it does not modify notes, samples or mappings. Pitch estimates and
timbre clusters remain listening evidence rather than automatic rejection.

`instrument_preference.py` is a deliberately explicit feedback boundary. It
hash-pins one reviewed DAW patch choice to an Instrument Bundle, then builds a
deterministic profile only from paths named by the user. Bundle integration is
additive: it copies the profile and displays a history-first hint while leaving
factory/GM/OpenL3 ranking, defaults, MIDI and the usability gate unchanged.
There is no implicit file discovery, hidden preference database or automatic
patch selection.

The CLI command names, exit codes, JSON reports, Clip v1 schema and generated
MIDI timing contracts are compatibility surfaces. Private helpers beginning
with `_` are implementation details and should not be called by agent skills or
third-party integrations.

## Change rules

For a literate walk through the modules, state transitions, invariants and
tests behind these rules, start with the
[Sunofriend technical tour](TECHNICAL_TOUR.md). It also gives the bounded
method for adding another transcription or review process without turning its
score into an automatic winner.

- Preserve source audio and existing output by default. Require an explicit
  overwrite option for destructive replacement.
- Characterize MIDI byte/event behaviour before moving parsers. Running status,
  SysEx, tempo maps, controllers, drum channel 10 and pitch bends all matter.
- Keep `exact`, `repair` and `reconstruct` evidence policies distinct.
- Publish uncertainty and provenance rather than silently turning weak evidence
  into main-track notes.
- Keep optional audio, preview and playback dependencies lazy so pure MIDI and
  Clip operations work in a lightweight installation.
- Keep neutral/unity technical evidence separate from any creative balance
  derivative. Label gain-only sample-peak protection as an audition aid, never
  final mastering; GarageBand still owns patch choice, automation, mixing and
  release loudness.
- Add a deterministic regression test before changing pitch, timing, note
  count, provenance or output layout.
- Keep instrument discovery read-only. Treat matching weights and report
  fields as evidence contracts, and retain the final patch choice as user
  feedback that can be stored through Clip v1.

## Incremental refactoring map

The safest next boundaries are:

1. Build the next reversible Phase 6 slice from the completed, separately
   gated Phase 6.1 immutable-placement contract.
   Add another pack artifact kind only after it has an explicit eligibility
   and rights contract. Keep Clip browse state, reuse proposals, derived
   previews, waveform display data, temporary mixer state, musical decisions
   and export-basket choices separate.
2. Continue Phase 5.10b from the implemented fresh full-project runner: add a
   durable owner-only ledger/restart contract, then typed one-stem, standalone
   vocal and MIDI transformation forms; keep CLI and TUI handlers as adapters.
3. Extend the new `workbench_instrument_policy.py` server-owned pair registry
   cautiously; keep broader role aliases, channels and GarageBand suggestions
   separate until their different evidence contracts can be unified safely.
4. Introduce a lossless Standard MIDI File codec and shared batch/path-safety
   utilities, then migrate one command at a time against a common fixture set.
5. Share phase-safe audio loading and an explicit beat-grid to `TempoMap`
   adapter.
6. Split the large Clip and vocal modules only after compatibility re-exports
   and characterization tests exist.

Do not combine those moves into a single rewrite. The existing golden songs
and synthetic tests are the guardrail for each small migration.
