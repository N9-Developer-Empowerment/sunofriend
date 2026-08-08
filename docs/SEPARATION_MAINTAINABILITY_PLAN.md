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
