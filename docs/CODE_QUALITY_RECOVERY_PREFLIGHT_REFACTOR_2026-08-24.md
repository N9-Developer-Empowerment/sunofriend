# Phase 4 increment 1 — recovery worker-request preflight

## Outcome

The first bounded Phase 4 increment is complete. The recovery facade still
owns the same request preflight and exposes the same public interface, but its
worker-request check now separates document identity, forward-budget, source
identity, SCNet output and specialist-output decisions.

No schema, hash algorithm, request field, error text, caller, filesystem
effect, review state or authority boundary changed. The recovery package
remains resource-incomplete private evidence. Planning remains no-write, and
this refactor grants no execution or publication authority.

## Refactoring boundary

The former `_validate_worker_request_binding` mixed four concerns at
complexity 26. It is now a complexity-3 coordinator over these focused checks:

| Function | Complexity | Branch-aware coverage | CRAP |
|---|---:|---:|---:|
| `_expected_worker_forward_calls` | 1 | 100% | 1.000000 |
| `_validate_worker_case_binding` | 2 | 100% | 2.000000 |
| `_validate_worker_request_binding` | 3 | 100% | 3.000000 |
| `_validate_specialist_output_binding` | 3 | 100% | 3.000000 |
| `_validate_scnet_output_binding` | 6 | 80% | 6.288000 |
| `_worker_request_cases` | 7 | 100% | 7.000000 |
| `_validate_worker_source_binding` | 10 | 100% | 10.000000 |

Five characterization cases now independently reject a wrong forward budget,
canonical source geometry, SCNet path, specialist path and network-denial
claim through the unchanged `build_recovery_request` facade.

## Measured change

| Measure | Phase 3 | Phase 4 increment 1 | Change |
|---|---:|---:|---:|
| Target worker-request CRAP | 44.252000 | 3.000000 coordinator | warning removed |
| Repository CRAP load | 49,717.196175 | 49,702.944175 | -14.252000 |
| Advisory CRAP warnings | 564 | 563 | -1 |
| Measured functions | 6,639 | 6,645 | +6 |
| Combined branch-aware coverage | 75.874% | 75.883% | +0.009 points |
| Source modules | 414 | 414 | unchanged |
| Internal dependencies | 1,607 | 1,607 | unchanged |
| Static cycles | 6 | 6 | unchanged |
| Contract violations | 0 | 0 | unchanged |

The recovery facade now has two accepted historical warnings:
`_tree_snapshot` at 33.323566 and
`_build_recovery_request_with_documents` at 30.320988. Neither changed in this
increment.

## Deterministic evidence

The unrestricted macOS branch-coverage run completed with 3,858 tests passing,
15 skipped, 13 deselected and 619 subtests passing. Two independently generated
CRAP reports and coverage bindings are byte-identical:

- CRAP report SHA-256: `2515211fc54c3b6ae4d107458b56f60c664a582eac0218f45bf23be6793d08b5`;
- coverage-binding SHA-256: `515ebb53d59bcba4cbb578e511847a1e84d97e0db260e4daec9289d12e1c2fff`;
- coverage JSON SHA-256: `4ca96da150702a3f57da4c38b21f964782ce3261c2b0c53129505b63897a9bab`;
- production source-tree SHA-256: `a88a81cdf4d495a7f0a2bd1ed218f95c5a19ac7264820e436f5f1c8e13cb350b`.

The changed-code CRAP ratchet and architecture ratchet both pass. The
architecture diff reports no added dependency, module, cycle, contract
violation or public-interface change. Local reproducible evidence is under
`work/quality/deep-module-recovery-preflight-2026-08-24/final/`.
The source-current explorer is under
`work/architecture-viewer-recovery-preflight-2026-08-24/`.

## Next bounded step

Continue one seam at a time. The smallest remaining recovery seam is
`_build_recovery_request_with_documents` at CRAP 30.320988. A separate Phase 4
increment should first characterize its retained-current and prior-package
evidence capture; it must not combine that work with the lossless MIDI or
review-transport changes.
