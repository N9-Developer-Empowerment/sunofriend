# Accepted code-quality baseline — 2026-08-24

## Outcome

The first full macOS coverage and CRAP baseline is accepted as **advisory**,
and the first bounded mutation pilot is complete. The ordinary non-live suite
passed cleanly outside the restricted harness. All retained reports bind to the
same unchanged production source tree and attach to current source in the
architecture viewer.

These measurements do not authorize a refactor, model run, render or musical
decision. No production source or audio was changed or run as a product
workflow. Mutation testing was limited to three pure or infrastructure modules.

## Exact measurement identity

| Item | Result |
|---|---:|
| Python | 3.11.7 |
| coverage.py | 7.15.3 |
| Radon | 6.0.1 |
| mutmut | 3.7.0 |
| Source-tree SHA-256 before and after | `a8d7ea9326ab49449538250df408b0f90dc25a13cfeb11d1a0b57570eb337504` |
| Accepted coverage JSON SHA-256 | `830d96350cff1610c533b5a4a8a6a4b428efd9059aca82550bd71935ed1b070d` |
| CRAP report SHA-256, both builds | `02fc2b63c31934c48e8742cda830b714c67470c87cb7755f5600f8416f4d1c7b` |
| Coverage-binding SHA-256, both builds | `d84186890094b8dcec9db996512f29afef2bc5ddb3210f4f0403acc67eaef001` |
| Mutation report SHA-256, both builds | `6d258ff610b53e61ea4f0302fdb2cdaf564ca330239c87922e02bfbfebdaea3c` |

The two accepted CRAP reports, two coverage bindings and two mutation reports
are byte-identical within each pair. The viewer attaches all 413 coverage
records, 6,606 risk records and 1,391 mutation records to current source.

## Accepted test and coverage result

The branch-aware command was:

```bash
COVERAGE_FILE=work/quality/accepted-macos-2026-08-24/.coverage \
  work/quality/venv/bin/python -m coverage run \
  -m pytest -q -m 'not trusted_local'
```

It completed in 18 minutes 4 seconds with 3,827 passed, 15 skipped, 13
deselected and 619 subtests passed. There were no failures or setup errors.

| Measure | Covered | Possible | Percentage |
|---|---:|---:|---:|
| Statements | 81,008 | 101,100 | 80.127% |
| Branches | 23,302 | 36,432 | 63.960% |
| Combined report opportunities | 104,310 | 137,532 | 75.844% |

The earlier restricted-harness diagnostic produced 137 failures and 16 setup
errors because loopback sockets, AVFoundation sampler construction and a
guarded `/dev/fd` handoff were denied. The clean accepted run confirms those
were environmental artifacts rather than application or coverage regressions.

## CRAP result

The report uses CRAP1 with statement-plus-branch opportunities and an advisory
warning threshold above 30.

| Measure | Result |
|---|---:|
| Functions found | 6,606 |
| Executable functions measured | 6,597 |
| Zero-opportunity declarations/no-op seams | 9, explicitly `not_applicable` |
| Unmeasured executable functions | 0 |
| Functions above CRAP 30 | 566 |
| Warning functions with zero observed coverage | 163 |
| Warning functions with some observed coverage | 403 |
| CRAP load above 30 | 50,441.440005 |

The complete result is advisory rather than a repository-wide score gate. A
changed-code ratchet may prevent newly changed functions from becoming worse;
it must not require the historical codebase to become clean in one change.

## Mutation pilot

The pinned pilot mutates only:

- `source_roles.py`;
- `automatic_selection.py`; and
- `separation_review_transport.py`.

The selected 53 tests and 35 subtests passed before the fresh run. Boundary
characterization then changed the mutation evidence as follows:

| Result | Before hardening | After hardening |
|---|---:|---:|
| Killed | 664 | 1,074 |
| Survived | 472 | 315 |
| Not exercised by selected tests | 253 | 0 |
| Timed out | 2 | 2 |
| Total | 1,391 | 1,391 |

All 315 survivors are explicitly classified. The default is conservative:
291 are `test_gap`, meaning the pilot tests did not distinguish the mutation.
The other 24 target the private `source_roles._definition` registry builder
and are `tool_model_limitation`: mutmut selects a function trampoline after
module initialization, but that builder has already populated the immutable
registry. They are not presented as killed or as proof of sufficient tests.
The two `_sha256` timeouts remain unresolved and no global mutation-score gate
has been introduced.

Per-module post-hardening results are:

| Module | Killed | Survived | Timed out |
|---|---:|---:|---:|
| `source_roles.py` | 98 | 27 | 0 |
| `automatic_selection.py` | 627 | 233 | 2 |
| `separation_review_transport.py` | 349 | 55 | 0 |

The report adapter records every exact mutant id, current function identity,
source hash, outcome and classification. Survivors remain work items; the
classification does not waive them.

## Hotspot assessment

`separation_fine_stem_full_song_recovery.py` was the clearest first Phase 3
deep-module candidate. `validate_recovery_request` scored CRAP 423.454810 at
complexity 115 and 71.429% coverage. `validate_recovery_report` scored
358.705990 at complexity 124 and 75.194% coverage. Both results were high in
the clean macOS baseline, so the evidence is not a sandbox-created zero-
coverage artifact.

That first refactor is now complete. The pure validation contract is hidden
behind the unchanged public facade, and the final CRAP and architecture
ratchets pass. See
[`CODE_QUALITY_DEEP_MODULE_REFACTOR_2026-08-24.md`](CODE_QUALITY_DEEP_MODULE_REFACTOR_2026-08-24.md)
for the source-current measurements. This document retains the original values
as the accepted pre-refactor baseline.

Other credible nonzero-coverage investigation targets remain:

- `ai_session_benchmark.build_ai_session_benchmark`: CRAP 581.690435;
- `workbench_catalog._ai_label_split_diagnostics`: CRAP 547.573503;
- `hybrid_report._verified_repetition_record`: CRAP 418.026706; and
- `garageband_pack_acceptance._inspect_pack_contents`: CRAP 408.451834.

These are investigation candidates, not permission to refactor several areas
at once.

## Viewer and retained evidence

The combined local viewer is:

`work/architecture-viewer-quality-mutation-2026-08-24-2/index.html`

It contains 413 modules, 1,603 internal dependencies, six existing static
cycles, three passing contracts, zero contract violations and zero source/test
parse errors. Coverage, CRAP and mutation attachments are hash-current. All
quality reports remain ignored local evidence under `work/quality/`; the
tracked adapter, classification policy, tests and documentation are sufficient
to reproduce them.
