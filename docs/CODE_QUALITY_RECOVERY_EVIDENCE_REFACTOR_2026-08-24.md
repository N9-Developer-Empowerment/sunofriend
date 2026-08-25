# Phase 4 increment 2 — retained recovery evidence capture

## Outcome

The second bounded Phase 4 increment is complete. The unchanged recovery
facade now coordinates four private boundaries instead of owning path checks,
current retained-evidence capture, prior-package hashing and request assembly
in one function.

No request field, schema, hash algorithm, error ordering, filesystem effect,
public interface, review state or authority boundary changed. Preflight remains
no-write. Recovery remains resource-incomplete private evidence and grants no
model retry, activation, source selection, MIDI, hosting, redistribution,
upload or musical approval.

## Deep-module boundary

`_build_recovery_request_with_documents` is now a complexity-1 coordinator.
Its private collaborators hide distinct knowledge:

| Function | Hidden responsibility | Complexity | Branch-aware coverage | CRAP |
|---|---|---:|---:|---:|
| `_resolve_recovery_request_paths` | failed-root and fresh exact-sibling binding | 9 | 70.000% | 11.187000 |
| `_capture_prior_failed_package` | prior tree, receipt, content hashes and counts | 9 | 88.571% | 9.120910 |
| `_expected_retained_files` | exact current retained-tree inventory | 4 | 84.615% | 4.058261 |
| `_capture_retained_recovery_evidence` | current tree, JSON, worker and payload binding | 4 | 88.235% | 4.026053 |
| `_retained_guitar_hashes` | three unreceipted guitar-array identities | 2 | 100.000% | 2.000000 |
| `_recovery_request_document` | unchanged request projection and document hash | 1 | 100.000% | 1.000000 |
| `_build_recovery_request_with_documents` | stable facade coordination | 1 | 100.000% | 1.000000 |

The two private tuple records keep the coordinator from knowing the internal
shape of current and prior evidence capture. They are underscore-prefixed and
the architecture diff reports no public-interface change.

## Characterization and safety evidence

The existing deterministic request, execution, preservation and race tests
remain green. Four new characterization cases prove that:

- malformed current evidence is rejected before a missing prior-package error,
  preserving preflight error order;
- the prior package must contain its exact failure report;
- current retained evidence changing during capture fails closed; and
- the separately bound prior package changing during capture also fails closed.

The complete suite uses synthetic fixtures only. It did not read private or
source music, load a checkpoint, construct a model or run inference.

## Measured change

| Measure | Phase 4 increment 1 | Phase 4 increment 2 | Change |
|---|---:|---:|---:|
| Target request-builder CRAP | 30.320988 | 1.000000 coordinator | warning removed |
| Repository CRAP load | 49,702.944175 | 49,702.623187 | -0.320988 |
| Advisory CRAP warnings | 563 | 562 | -1 |
| Measured functions | 6,645 | 6,651 | +6 |
| Combined branch-aware coverage | 75.883% | 75.893% | +0.010 points |
| Source modules | 414 | 414 | unchanged |
| Internal dependencies | 1,607 | 1,607 | unchanged |
| Static cycles | 6 | 6 | unchanged |
| Contract violations | 0 | 0 | unchanged |

The repository CRAP-load reduction is deliberately small because the former
single function was replaced by separately measurable helpers. The useful
result is that no helper exceeds the threshold, the warning is removed and
each evidence boundary can now be reasoned about and tested independently.

## Deterministic evidence

The unrestricted macOS branch-coverage run completed with 3,862 tests passing,
15 skipped, 13 deselected and 619 subtests passing. Two independently generated
CRAP reports and coverage bindings are byte-identical:

- CRAP report SHA-256: `fff9f7d99ed37e47c09ea404d754761e48d86c4104ff2c56eae46486cd08d770`;
- coverage-binding SHA-256: `e5c1b1f21280fbdb7b90bdbf2b8ca8aecff88a77003560ed85d691447d056d22`;
- coverage JSON SHA-256: `d03aeac82b74ddd3cc80933d1d1a4cc7bfa34fb8f1e62423490d4c3b73185d92`;
- production source-tree SHA-256: `eca61ad06d3aa81d23006b921c0bfa0e7b297e571c48bb2de641c434699099e9`.

The changed-code CRAP ratchet, architecture ratchet, three architecture
contracts, Ruff and diff checks pass. The architecture diff reports no added
module, dependency, cycle, contract violation or public-interface change.
The source-current mutation adapter still binds all 1,391 established pilot
mutants, and the fresh viewer attaches 414 coverage, 6,660 CRAP, 1,391
mutation and six semantic records with zero diagnostics.

Local reproducible evidence is under
`work/quality/deep-module-recovery-evidence-2026-08-24/final/`. The
source-current explorer is under
`work/architecture-viewer-recovery-evidence-2026-08-24/`.

## Next bounded step

Continue one seam at a time. The only remaining accepted warning in the
recovery facade is `_tree_snapshot` at CRAP 33.323566. A separate increment
may split filesystem enumeration from invariant validation without changing
the snapshot schema, metadata captured, traversal rules or race checks.
