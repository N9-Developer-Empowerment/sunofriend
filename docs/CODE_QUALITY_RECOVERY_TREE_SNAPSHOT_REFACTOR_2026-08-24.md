# Phase 4 increment 3 — retained-tree snapshot boundary

## Outcome

The third bounded Phase 4 increment is complete. The unchanged
`_tree_snapshot` facade now coordinates private tree enumeration, metadata
projection, exact inventory matching, directory invariants and file
invariants instead of combining those responsibilities in one function.

The snapshot schema, field order, traversal order, captured metadata, error
order and accepted legacy inner-directory mode are unchanged. The refactor
does not decode audio, write recovery output, load a checkpoint, construct a
model, run inference or change any review or authority state.

## Deep-module boundary

The facade hides six focused collaborators and one private tuple record:

| Function | Hidden responsibility | Complexity | Branch-aware coverage | CRAP |
|---|---|---:|---:|---:|
| `_directory_snapshot_identity` | stable directory metadata projection | 1 | 100.000% | 1.000000 |
| `_file_snapshot_identity` | stable regular-file metadata projection | 1 | 100.000% | 1.000000 |
| `_enumerate_tree_snapshot` | no-follow traversal and entry classification | 7 | 92.308% | 7.022303 |
| `_validate_tree_file_inventory` | exact expected/observed file equality | 4 | 100.000% | 4.000000 |
| `_validate_tree_directory_invariants` | root, legacy and private directory modes | 7 | 100.000% | 7.000000 |
| `_validate_tree_file_invariants` | private mode, owner and single-link rules | 6 | 100.000% | 6.000000 |
| `_tree_snapshot` | stable facade and legacy-mode count | 3 | 100.000% | 3.000000 |

This is a split by hidden filesystem knowledge, not a collection of public
wrappers. Every new interface is underscore-prefixed, callers still receive
the same dictionary, and the architecture diff reports no public-interface
change.

## Characterization and safety evidence

The existing request, execution, preservation, race and atomic-publication
tests remain green. Nine new synthetic cases establish that:

- directory and file identity fields and their output order remain stable;
- the legacy inner-directory `0755` count remains stable;
- exact inventory mismatch is reported before a later file-mode mismatch;
- root, inner and strict-private directory modes fail with their established
  errors;
- non-private files and multiply linked files fail closed; and
- symlinks and special files are rejected during enumeration.

The focused recovery module passes all 39 tests with normal macOS loopback
permissions. Its synthetic fixtures did not read private or source music and
did not load or execute any model.

## Measured change

| Measure | Phase 4 increment 2 | Phase 4 increment 3 | Change |
|---|---:|---:|---:|
| Target `_tree_snapshot` CRAP | 33.323566 | 3.000000 facade | warning removed |
| Highest new helper CRAP | not applicable | 7.022303 | below threshold |
| Repository CRAP load | 49,702.623187 | 49,699.299621 | -3.323566 |
| Advisory CRAP warnings | 562 | 561 | -1 |
| Measured functions | 6,651 | 6,657 | +6 |
| Combined branch-aware coverage | 75.893% | 75.904% | +0.011 points |
| Source modules | 414 | 414 | unchanged |
| Internal dependencies | 1,607 | 1,607 | unchanged |
| Static cycles | 6 | 6 | unchanged |
| Contract violations | 0 | 0 | unchanged |

The changed-code CRAP ratchet covers seven materially changed functions and
six new functions with no failure. The architecture ratchet reports no added
module, dependency, cycle, violation or public-interface change.

## Deterministic evidence

The unrestricted macOS branch-coverage run completed with 3,871 tests passing,
15 skipped, 13 deselected and 619 subtests passing. Two independently generated
CRAP reports and coverage bindings are byte-identical:

- CRAP report SHA-256: `a4df5f8a03e2a591248c8dff79890e0516bc39ddcefacb92a5ac2f64b77b722a`;
- coverage-binding SHA-256: `15ddf9675eb290f3be2e90caa3ed83b66c7c232016c5bd877808e6aa7be3c60b`;
- coverage JSON SHA-256: `e5854f081309e91ced04e16325edcf259d4c73c54674e2d97067eb9159548516`;
- production source-tree SHA-256: `9e6223cdf54643b5ae67496f2445bd1bc80d5de3ce47f375fc1be6a17855a85c`.

Ruff, the changed-code CRAP ratchet, the architecture ratchet and all three
architecture contracts pass. The source-current viewer attaches 414 coverage,
6,666 CRAP, 1,391 established-pilot mutation and six semantic records with
zero diagnostics.

Local reproducible evidence is under
`work/quality/deep-module-recovery-tree-snapshot-2026-08-24/final/`. The
source-current explorer is under
`work/architecture-viewer-recovery-tree-snapshot-2026-08-24/`.

## Next bounded step

The three accepted recovery-facade warnings identified after the first deep
module extraction are now removed. Continue with one independent track: the
lossless MIDI codec with one migrated caller, shared review transport, or the
planned Import Linter package contracts. Do not combine those seams in one
change.
