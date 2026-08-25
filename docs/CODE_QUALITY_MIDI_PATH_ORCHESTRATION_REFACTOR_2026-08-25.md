# Phase 4 increment 6 — MIDI transform path orchestration

## Outcome

The sixth bounded Phase 4 increment splits
`midi_transform.transform_midi_path` into private planning, destination
preflight, whole-batch preparation and publication boundaries. The public
facade, `transform_midi_file`, CLI report, result records and exact error text
remain unchanged.

Directory inputs still recurse over `.mid` and `.midi` files, preserve relative
paths and use case-folded ordering. File outputs still accept the exact caller
path without imposing a suffix. Every output collision and parent hazard is
still rejected before any MIDI is decoded, every MIDI is still transformed
before any destination directory or file is published, and each prepared file
is still replaced atomically through the established same-directory temporary
file helper.

## Deep-module boundary

The public facade now coordinates four narrow internal operations:

- `_plan_transform_paths` hides file-versus-directory classification,
  recursive discovery, relative destination mapping and output-root policy;
- `_preflight_transform_destinations` hides resolved collision detection,
  input/output alias rejection, symlink and existing-path rules, and safe
  parent traversal;
- `_prepare_transforms` reads and transforms the complete batch without
  publishing anything; and
- `_publish_prepared_transforms` creates all required parents before writing
  the prepared files in deterministic batch order.

Private frozen records bind the path plan, unchanged transformation options and
prepared payloads. The options remain deliberately unvalidated until
`transform_midi_bytes` processes the first prepared input, preserving the
established rule that all destination collisions are reported before an
invalid transform option.

No shared cross-module filesystem utility was introduced. The existing
`_validate_output_parents` and `_write_bytes_atomic` implementations and import
paths remain unchanged because `midi_anchor.py` also consumes them. Clip
semantics, anchor delta rewriting, MIDI event decoding and musical policy were
outside this increment.

## Characterization and independent review

Eight new path-focused tests brought the original complexity-28 facade to 100%
statement and branch coverage before the production extraction. They pin:

- missing, unsupported, file and directory input shapes and exact validation
  precedence;
- mixed-case MIDI suffixes, recursive relative paths, ignored non-MIDI files,
  case-folded result ordering and caller-selected output suffixes;
- output-inside-input, same-path, duplicate-resolved-output, output-symlink,
  parent-symlink, parent-file, existing-directory and existing-file rejection;
- `overwrite=True` replacement and temporary-file cleanup;
- collision checks before decoding an invalid earlier input;
- whole-batch transformation before the first output is created; and
- the complete `MidiTransformFileResult.to_dict()` key surface.

The extracted facade and all seven new helpers also reach 100% statement and
branch coverage in the focused run. The wider codec, tempo, transform, CLI,
anchor and Workbench consumer set passes 110 tests.

DeepSeek V4 Flash supplied an independent read-only compatibility inventory at
an estimated provider-reported cost of USD $0.01936391. Codex independently
checked its useful findings against current callers, source and tests. In
particular, the final change preserves the lenient output suffix, CLI-visible
error strings, collision-before-option ordering and the private helpers used by
MIDI anchor. The delegate made no edits and was not used as the acceptance
authority.

## Measured change

| Measure | Phase 4 increment 5 | Phase 4 increment 6 | Change |
|---|---:|---:|---:|
| `transform_midi_path` CRAP | 46.285714 | 1.000000 | warning removed |
| Highest extracted helper CRAP | not applicable | 10.000000 | below threshold |
| Repository CRAP load above 30 | 49,674.152558 | 49,657.866844 | -16.285714 |
| Advisory CRAP warnings | 559 | 558 | -1 |
| Measured functions | 6,681 | 6,688 | +7 |
| Combined branch-aware coverage | 75.985351% | 76.009803% | +0.024451 points |
| Source modules | 415 | 415 | unchanged |
| Internal dependencies | 1,609 | 1,609 | unchanged |
| Static cycles | 6 | 6 | unchanged |
| Contract violations | 0 | 0 | unchanged |

The changed-code ratchet covers eight materially changed and seven new
functions with no failure. The architecture ratchet reports one source-changed
module, no added or removed module, dependency, cycle or violation, and no
public-interface change.

## Deterministic evidence

The unrestricted macOS branch-coverage run completed with 3,894 tests passing,
15 skipped, 13 deselected and 656 subtests passing. Two independently generated
CRAP reports, coverage bindings and current mutation reports are byte-identical
within each pair:

- CRAP report SHA-256:
  `02c5776f69f5fc1315911bf73c846903e10752ca68b434e623f29f670b0b964e`;
- coverage-binding SHA-256:
  `027d1ec227a06866d17b85f85cbec8f4a91b41992015e99a1d31b49c71241bc1`;
- coverage JSON SHA-256:
  `6367ee3a99b9715cdfaa3e90c2758126e5ffd3aad592d9d6ca628da67b1c58e2`;
- current mutation report SHA-256:
  `fc30c8824a8ef82084775e541d15394701173f16604df5532829410efc4fb87b`;
- architecture snapshot SHA-256:
  `bc751b8fd02d374b6127f59a6e6b7cacc918de8463a345c35b17cddd99bf916f`;
  and
- production source-tree SHA-256:
  `35cc38934f54ef9550c8ed2e9b5e4e0dbd5a112f7a24ec42c8293184881731d9`.

Ruff, diff whitespace, the changed-code CRAP ratchet, the architecture ratchet
and all three architecture contracts pass. The source-current viewer attaches
415 coverage, 6,697 CRAP, 1,391 established-pilot mutation and six semantic
records with zero diagnostics and 415 unique source pages.

Local reproducible evidence is under
`work/quality/deep-module-midi-path-orchestration-2026-08-25/final-macos/`.
The source-current explorer is under
`work/architecture-viewer-midi-path-orchestration-2026-08-25/`.

No private or source audio was read, no model or checkpoint was loaded, and no
inference, MIDI musical selection, render or review decision was performed.

## Next bounded step

The accepted `midi_transform` warning queue is now exhausted. Continue with the
planned review-transport consolidation as a separate increment. The remaining
`midi_tempo.retime_midi_path` path-orchestration warning is an independent
future candidate and must not be folded into review transport or a new shared
cross-module path utility.
