# Sunofriend architecture

Sunofriend has three user-facing layers:

1. The Python package and `sunofriend` command are the deterministic engine.
2. The loopback-only Workbench presents completed source/MIDI alternatives,
   records explicit decisions and prepares the GarageBand handoff.
3. The portable Agent Skill selects commands, checks prerequisites and
   interprets reports. It must not duplicate audio or MIDI algorithms.

These layers preserve Sunofriend's core separation: several analytical and AI
processes may produce immutable candidates, the Workbench makes their evidence
approachable, and a human chooses what becomes part of an arrangement. No
shared score or model label is an automatic winner.

## Current execution flow

```text
stem folder / MIDI
        |
        v
CLI parsing (`cli.py`)
        |
        +--> folder orchestration (`listen_all.py`)
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
        |                              `workbench_home.py`,
        |                              `workbench_timeline.py`,
        |                              `workbench_artifacts.py`,
        |                              `workbench_server.py`,
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
MIDI + provenance/evaluation JSON + optional WAV preview
```

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
non-diagnostic candidates. `workbench_store.py` records immutable events in a
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
streams, selected-arrangement proxies and deterministic
GarageBand handoff ZIPs. It reads notes through Clip v1 and renders through the
existing MIDI/FluidSynth boundaries; discovered MIDI is never rewritten, and
numbered handoff tracks are exact copies of explicit main/optional choices.
Rejected, needs-correction, superseded and unreviewed candidates never enter
the arrangement or ZIP.
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

`workbench_transport.js` decodes those bounded clips, normalises their decoded
frame lengths on one `AudioContext`, and creates fresh source nodes for every
scheduled start or switch. The outgoing stop and incoming start share one
future clock time, while an absolute loop playhead survives the switch. This is
sample-scheduled browser playback, not inferred alignment: source and MIDI
still begin at their recorded zero and no offset is estimated. Preparing,
playing, switching, seeking, pausing and stopping have zero selection, event,
ranking and MIDI-mutation effects. The explicit compatibility fallback retains
second-synchronised HTML media elements and is not sample-accurate, but its
transport controls are likewise feedback- and event-free.

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

Alternative MIDI, Instrument Bundles, persistent mixer projects and custom-mix
rendering are not implemented in Pack Composer v1. Canonical selected
arrangements now have bounded and chunked decoded audition paths, while the
arbitrary custom mixer remains coarse HTML media. All audition transports stay
separate from ZIP composition.

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

- Preserve source audio and existing output by default. Require an explicit
  overwrite option for destructive replacement.
- Characterize MIDI byte/event behaviour before moving parsers. Running status,
  SysEx, tempo maps, controllers, drum channel 10 and pitch bends all matter.
- Keep `exact`, `repair` and `reconstruct` evidence policies distinct.
- Publish uncertainty and provenance rather than silently turning weak evidence
  into main-track notes.
- Keep optional audio, preview and playback dependencies lazy so pure MIDI and
  Clip operations work in a lightweight installation.
- Add a deterministic regression test before changing pitch, timing, note
  count, provenance or output layout.
- Keep instrument discovery read-only. Treat matching weights and report
  fields as evidence contracts, and retain the final patch choice as user
  feedback that can be stored through Clip v1.

## Incremental refactoring map

The safest next boundaries are:

1. Harden the completed GarageBand Pack Composer and add another artifact kind
   only after it has an explicit eligibility and rights contract. Keep
   waveform display data, temporary mixer state, musical decisions and
   export-basket choices separate.
2. Add typed application operations for folder conversion, one-stem conversion,
   vocal extraction and MIDI transformation; keep CLI handlers as adapters.
3. Centralize instrument roles, aliases, channels, GM programs and GarageBand
   suggestions in one immutable registry.
4. Introduce a lossless Standard MIDI File codec and shared batch/path-safety
   utilities, then migrate one command at a time against a common fixture set.
5. Share phase-safe audio loading and an explicit beat-grid to `TempoMap`
   adapter.
6. Split the large Clip and vocal modules only after compatibility re-exports
   and characterization tests exist.

Do not combine those moves into a single rewrite. The existing golden songs
and synthetic tests are the guardrail for each small migration.
