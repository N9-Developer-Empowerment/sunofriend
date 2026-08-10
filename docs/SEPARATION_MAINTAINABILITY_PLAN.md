# Separation maintainability plan

Sunofriend's separation work grew deliberately through small, evidence-bound
experiments. The next engineering phase will consolidate those experiments
without changing public profiles, invalidating retained evidence or weakening
approval boundaries.

## Non-negotiable invariants

- immutable profile, runtime, checkpoint and report identities;
- local processing and explicit rights declarations;
- atomic publication and reconstruction accounting;
- no model install, inference, song processing, activation or MIDI beyond the
  authority recorded for that gate;
- objective preview admission remains separate from human musical feedback;
- negative listening results remain evidence and do not start an unlimited
  tuning loop.

## Target structure

1. **Contracts** — pure standard-library schemas, hashes and validators with no
   model or audio imports.
2. **Guards** — reusable one-way network, audio and checkpoint enforcement for
   short-lived model processes, backed by operating-system network denial.
3. **Adapters** — model topology and strict local checkpoint loading, isolated
   from CLI, setup and publication code.
4. **Runners** — bounded synthetic, canary and resource execution with explicit
   effects and stop conditions.
5. **Publication** — PCM24 roles, residual accounting, atomic output roots and
   immutable profile registry transitions.
6. **Review** — report-bound local listening pages and text-only feedback with
   no automatic upload or source choice.
7. **Interfaces** — small CLI/setup commands that orchestrate the modules above
   and contain no duplicated validation logic.

## Incremental sequence

- Extract pure validation and receipt construction from large setup scripts.
- Split load-compatible topology from forward/inference implementations.
- Give each runner one input/output contract and one deterministic test fixture.
- Replace repeated profile, hash and effects literals with shared immutable
  records, while retaining compatibility tests for every existing report.
- Reduce shell scripts to platform checks, explicit approval flags, sandboxing,
  staging and atomic publication.
- Consolidate review-page JavaScript around shared download/copy primitives and
  browser tests, preserving the repaired fallbacks.
- Remove obsolete experimental paths only after their evidence is archived and
  every public command/document points to the replacement.

This is not a big-bang rewrite. Each extraction must preserve existing output
hashes where the schema is unchanged, pass focused tests, and leave the last
functioning public profile available.

## Current increment

The Banquet/PaSST load-report validator and approval-receipt builder have moved
from an embedded Python heredoc into
`separation_other_refinement_query_load_contract.py`. The setup shell now calls
that pure contract. The 522-line construction/load CLI has also been split into
an exact state-compatible topology module, a strict weights-only loading module
that retains the two model objects, and a 118-line guarded evidence CLI. A
network-denied rerun after extraction produced a byte-identical report with the
same canonical SHA-256 and zero network, audio or inference effects. The next
synthetic-forward plan is also a pure, no-effects document. A reusable one-way
execution guard now owns network, audio and exact-checkpoint enforcement. A
separate pure forward contract binds the proposed math and exact setup-C values
to nine pinned upstream source/configuration hashes. Forward math,
synthetic execution and report validation remain distinct boundaries. The
synthetic-result validator and receipt writer are now
implemented as a pure pass-or-retained-failure contract: they accept no
subjective rating, grant no automatic retry and cannot activate a profile,
source or MIDI path. The initial combined implementation has been split again:
immutable contract construction, objective projection/validation and receipt
creation are separate one-way modules, with a small compatibility facade for
the earlier import surface. This preserves the published contract identity.
The approved one-shot runner now uses a separate single-use tensor adapter and
the pure report-projection module. Its only attempt passed all objective gates
and was retained without granting audio, activation, source-selection or MIDI
authority. The reference-query increment is now split into an immutable six-
input rights/identity contract, deterministic WAV/PCM24 accounting, a dedicated
audio-aware effects guard, a nine-call tensor boundary, a strict objective
report, and a localhost review/download server. The approved worker loaded the
models once, completed exactly nine calls and atomically published its private
package. Model math remains outside the audio and review layers; the setup
shells still contain neither inference nor product activation.

The synth-first challenger remains a pure status document in
`separation_other_refinement_next_challenger.py`, with a tiny print-only CLI.
It records exact upstream identities, loader hazards, authority boundaries and
evaluation semantics without importing a model or touching audio. Instrument
presence is explicitly separated from model usefulness, so absent targets do
not become false failures and do not trigger replacement-window hunting. Any
Mega-53 forward adapter must keep artifact verification, restricted loading,
model math, PCM24 accounting, review and activation in separate modules rather
than extending one of the legacy orchestration files.

The Mega-53 runtime-evidence increment follows the same separation: one
download-only helper owns resolver and aggregate-cap enforcement, one
stdlib-only module owns wheel ZIP/METADATA/licence inspection, and the setup
shell only binds approval, network denial and atomic publication. The exact
29-wheel lock is committed separately. A standalone stdlib verifier now owns
the isolated import gate, exact installed-distribution check and no-network,
no-checkpoint and no-audio guards. The setup shell remains orchestration only;
model construction and loading remain outside it.

The completed source/load increment follows the target structure directly:
`separation_other_refinement_next_source_evidence.py` safely inventories and
extracts the capped immutable source archive; the pure
`separation_other_refinement_next_model_load_contract.py` validates reports and
receipts; `separation_other_refinement_next_execution_guard.py` owns the
one-checkpoint effects boundary; and
`separation_other_refinement_next_model_loading.py` owns only checkpoint-derived
topology and strict MLX loading. The evidence CLI contains no forward call or
audio interface. This separation made the upstream expansion-factor
conflation visible and allowed one process-local adapter without mutating the
sealed source or leaking model details into setup shell. The pure
`separation_other_refinement_next_synthetic_plan.py` now owns the generated-
tensor identity, 53-role order, single-attempt authority and aligned chunk/step
math. A later runner must remain similarly isolated; song decoding and
publication stay out until that objective boundary passes.

The private song-canary increment now keeps source qualification outside the
model runner. `separation_target_presence_qualification.py` validates each
complete bound review, accepts only target-present cases, requires four
song-disjoint tracks per target and copies byte-identical reviewed PCM24 source
excerpts into one immutable cohort. It performs no model load or inference and
cannot select a replacement automatically. The localhost presence page records
individual player state without a manual listened checkbox, saves to both
browser-local and atomic server storage, and is rendered from the currently
validated manifest so a repaired server cannot serve stale JavaScript from an
older package. The completed reviews are reduced by the pure
`separation_fine_stem_canary_outcome.py` module; it applies the frozen 60%
threshold without activating a profile or touching audio.

The completed integration increment kept reconciliation separate again.
`separation_fine_stem_integration_plan.py` binds the exact outcome, reports and
reviews and produces only a hashed no-effects plan. The model-free
`separation_fine_stem_integration_audio.py` owns the fixed grouped-other-
constrained STFT projection and exact six-role PCM24 accounting. Model workers,
private package publication and review remain outside those modules. The
completed eight-window worker published exact six-role artifacts and the human
review qualified synth and guitar on their confirmed-present cohorts. The new
pure `separation_fine_stem_integration_outcome.py` reducer scores only those
cohorts and grants no activation, selection or MIDI permission.

The follow-on planning increment stays pure as well.
`separation_fine_stem_midi_plan.py` binds the qualified outcome, all eight
candidate identities, exact non-guessed track metadata and grouped-other
control inputs. It specifies one identical-parameter A/B transcription contract
per case while keeping every audio/model/MIDI effect at zero. A small CLI writes
that immutable plan. The later approved executor remains a separate module: it
verifies the plan and 24 input identities, constructs eight sample-exact
controls, owns only the 16-call transcription/MIDI/neutral-preview boundary and
atomically publishes one private report. Its localhost review module separately
owns blind display order, automatic playback recording, schema validation and
atomic save/download. Neither layer imports or reruns a separator, chooses a
source or activates a profile.

The review failure also exposed avoidable generated-JavaScript risk. The
six-role page now builds readable raw JavaScript separately from the Python
HTML f-string, loads browser-local progress before writing defaults, records
playback through `play`, `playing` and positive `timeupdate`, and waits for a
successful atomic save before downloading. Rendered-script syntax and the
server save/download contract are regression-tested. Future review pages should
reuse these primitives instead of embedding new one-line scripts.

The downstream decision increment now has two additional pure modules instead
of extending the model runner. `separation_fine_stem_midi_outcome.py` owns only
review aggregation, methodology disclosure and no-authority outcome validation.
`separation_fine_stem_synth_bottleneck_plan.py` joins report identities and
provider-manifest metadata without opening audio, then emits an explicitly
non-executable request for four exact provider estimates. A later provider
qualification step, transcriber runner and source-present review must remain
separate modules. This boundary prevents model-loading code, private paths and
musical decisions from accumulating in the already large six-role integration
test/runner surface.

That provider boundary is now implemented as four focused modules rather than
another branch in a model worker. `separation_fine_stem_synth_provider_qualification.py`
owns exact private input identity, deterministic resampling, pack-sum alignment
and PCM24 persistence. `separation_fine_stem_synth_provider_review.py` owns the
source-visible, checkbox-free, autosaving localhost page.
`separation_fine_stem_synth_provider_outcome.py` is a no-audio reducer, while
`separation_fine_stem_synth_provider_midi_plan.py` can bind—without executing—
the exact three arms and 12 attempt numbers only after four confirmed-present
provider targets. This keeps provider file handling, human decisions and the
future transcriber executor independently testable.

The localhost transport shared by the active fine-stem reviews is now isolated
in `separation_review_transport.py`. Review-specific modules continue to own
their schemas, report bindings and page content; the shared layer owns only
bounded JSON request parsing, owner-only atomic persistence, downloads and
single-range file responses. It uses unique same-directory temporary files so
autosaves cannot collide, streams large responses in bounded blocks and emits
an explicit `Content-Range: bytes */SIZE` for unsatisfiable browser requests.
The provider-synth, MIDI, six-role, fine-stem canary and target-presence servers
all use this transport. Compatibility tests retain their existing JSON schemas
and hashes, while transport tests cover open-ended and suffix ranges, malformed
or multiple ranges, non-finite JSON and refusal to create a new evidence tree.

The provider-synth MIDI comparison follows the same boundary. Common PCM24,
note-validation, neutral-render and multi-arm loudness-matching primitives now
live in `separation_midi_comparison.py`; the existing two-arm runner retains
its earlier report contract through a small compatibility wrapper. The new
`separation_fine_stem_synth_provider_midi_canary.py` executor accepts only the
exact approved plan hash, verifies four source references plus all 12 bound
transcription inputs, runs one fixed transcriber contract and atomically
publishes private MIDI and neutral previews. Its separate review module shows
the source and blind A/B/C previews, records playback automatically, allows
`not_tested` and `cannot_tell`, and never writes a source choice. Deterministic
tests cover wrong-hash refusal before effects, the exact 12-attempt budget,
zero separator effects, all three blind arms, byte-range audio and atomic
review save/download. Implementing and testing this boundary does not execute
the private comparison; that remains blocked only on explicit approval of the
already frozen plan hash.

That frozen plan has now been consumed exactly once. The network-denied worker
completed all 12 same-transcriber attempts, published 12 private MIDI files and
12 neutral previews, and retained the four source-visible blind review. The
new pure `separation_fine_stem_synth_provider_midi_outcome.py` reducer owns only
unblinding, aggregation and the downstream decision boundary. It records that
grouped other was preferred in 4/4 cases while the current separator beat the
provider estimate twice and tied it twice. This is a MIDI-method result, not a
rejection of the earlier human-reviewed synth audio evidence. The reducer
opens no audio, grants no source selection or activation, and explicitly keeps
private Studio audio admission separate from the choice of MIDI input.
