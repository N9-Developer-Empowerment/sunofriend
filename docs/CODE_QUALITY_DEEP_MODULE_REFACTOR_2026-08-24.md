# First deep-module refactor — full-song recovery contract

## Outcome

Phase 3 is complete. The pure request/report interpretation for full-song
recovery now lives in
`separation_fine_stem_full_song_recovery_contract.py`. The existing
`separation_fine_stem_full_song_recovery.py` module remains the public facade
and owns filesystem inspection, retained payload loading, output construction,
review rendering and exclusive publication.

No schema, status, public facade name, hash algorithm, receipt rule, review
state or authority boundary changed. No private or source audio, model or
checkpoint was used by the refactor or its quality measurements; tests used
only their synthetic fixtures.

## Deep-module boundary

Callers still use the same twelve-name recovery facade. The extracted contract
offers eight declared names, of which the four supported operations are:

- `recovery_request_sha256`;
- `recovery_report_sha256`;
- `validate_recovery_request`; and
- `validate_recovery_report`.

The contract hides request/report schema identity, retained-tree and payload
rules, worker evidence, resource-incomplete accounting, artifact identity,
effects and preservation binding. It does not import NumPy, resource, stat,
temporary-file, timing, review-rendering, publication, execution-worker or
execution-facade modules.

The facade's public functions remain defined in the facade, rather than being
exposed as direct re-exports. The architecture diff therefore reports zero
public-interface changes.

## Measured change

| Measure | Accepted baseline | After refactor | Change |
|---|---:|---:|---:|
| Full-song request validator CRAP | 423.454810 | facade 1.000000; contract 3.083977 | hotspot removed |
| Full-song report validator CRAP | 358.705990 | facade 1.000000; contract 1.000000 | hotspot removed |
| Repository CRAP load | 50,441.440005 | 49,717.196175 | -724.243830 |
| Advisory CRAP warnings | 566 | 564 | -2 |
| Measured functions | 6,597 | 6,639 | +42 |
| Source modules | 413 | 414 | +1 |
| Internal dependencies | 1,603 | 1,607 | +4 |
| Static cycles | 6 | 6 | unchanged |
| Contract violations | 0 | 0 | unchanged |

The first implementation attempt produced one new over-threshold helper:
`_validate_guitar_resources` scored 46.444444. The CRAP ratchet rejected it.
It was split into guitar-summary, incomplete-gate and resource-measurement
checks with complexities 10, 4 and 6. The final highest new score is
`_validate_prior_identity` at exactly 30.000000, so the final ratchet passes.

The facade still contains three accepted historical warnings:
`_validate_worker_request_binding` at 44.252000, `_tree_snapshot` at 33.323566
and `_build_recovery_request_with_documents` at 30.320988. They were not
worsened by this refactor and remain separate follow-up candidates.

The first subsequent Phase 4 increment has now removed the
`_validate_worker_request_binding` warning without changing the facade. See
[`CODE_QUALITY_RECOVERY_PREFLIGHT_REFACTOR_2026-08-24.md`](CODE_QUALITY_RECOVERY_PREFLIGHT_REFACTOR_2026-08-24.md).

## Deterministic evidence

The final unrestricted macOS branch-coverage run completed with 3,853 tests
passing, 15 skipped, 13 deselected and 619 subtests passing. Coverage remained
branch-aware at 75.874% combined opportunities.

Two independently generated final CRAP reports are byte-identical:

- CRAP report SHA-256: `c9af7ad3f49a6dabc81b385d272be3adbf153361424737161545894106eb3c58`;
- coverage-binding SHA-256: `89c34fb00de42a3afb8dbc6d85a0ffcd3664e1da774cd70af6cbcac8b8c7159f`;
- coverage JSON SHA-256: `1759195dbade8d1f28fe702e6eebd7e3a580d49dde96fde5e380890ed6187e99`;
- production source-tree SHA-256: `e9567fbc546b14138b16b17103a806159007ac6587314ea07f487512a3fe5175`.

The architecture ratchet reports no new cycle, violation or parse error and no
public-interface change. The source-current mutation overlay reuses the
completed three-module pilot metadata only after verifying its targeted source
identities remain unchanged; the recovery refactor was not added to that pilot.

Local reproducible evidence is retained under
`work/quality/deep-module-full-song-recovery/final/`. The fresh explorer is
under `work/architecture-viewer-deep-module-full-song-recovery-2026-08-24-2/`.

## Next bounded step

Do not broaden several seams at once. Phase 4 should select one of:

1. reduce the facade's remaining request-building warning without changing
   evidence or publication behavior;
2. prepare the lossless MIDI codec boundary and migrate one caller; or
3. consolidate one remaining review-transport mechanic.

Each change must begin with a fresh architecture snapshot and pass the same
coverage, CRAP and authority-preservation gates.
