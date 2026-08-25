# Phase 4 increment 5 — MIDI transform parser migration

## Outcome

The fifth bounded Phase 4 increment removes the duplicate Standard MIDI File
track/event parser from `midi_transform.py`. Its established private
`_parse_midi` facade now delegates structural decoding to the lossless
`midi_codec.py` boundary and projects the codec result into the unchanged
transform layout used by transposition, concert-pitch cleanup, MIDI anchoring
and Workbench instrument review.

No public command, result record, Clip model, MIDI writer, batch/path policy or
musical interpretation changed. The transform still accepts only format 0/1
PPQ files, preserves its exact validation precedence and keeps its historical
transpose-only tolerance for structurally readable malformed Set Tempo events.
Actual tempo retiming remains strict.

## Deep-module boundary

The codec now owns one implementation of:

- extended SMF headers and declared track chunks;
- variable-length quantities and accumulated ticks;
- explicit and running channel status;
- meta, SysEx, system and channel event widths;
- End Of Track termination, track padding and trailing bytes; and
- absolute raw-event and event-data spans.

The transform compatibility facade continues to own its narrower policy:

- format 0 and 1 only;
- PPQ timing only;
- transform-specific error text and check ordering;
- meta-type, channel and system data projections expected by existing private
  consumers; and
- deferred Set Tempo validation for non-tempo transformations.

Strict `parse_midi` behavior and its public signature remain unchanged. A
private structural codec entry point supports the compatibility adapter, while
the transform's `_Event`, `_Track` and `_Layout` shapes remain stable. The
separate `_read_varlen` compatibility helper remains because `midi_anchor.py`
still uses it when rewriting delta fields; that broader rewrite seam was not
combined with this migration.

## Characterization and review evidence

Five new tests establish that:

- private header inspection exposes structurally complete fields before the
  compatibility caller chooses format, track-count and timing policy, while
  strict public inspection and tempo error precedence remain unchanged;
- strict codec parsing still rejects unsupported document headers and invalid
  Set Tempo events;
- the private structural route defers only Set Tempo semantics;
- transform projections retain meta types, absolute channel/system data
  offsets, running status, ticks, raw spans, post-End-Of-Track padding and
  trailing bytes; and
- format, track-count, SMPTE and zero-division errors retain their established
  precedence and wording, while transpose-only and retime behavior remain
  deliberately distinct for malformed tempo payloads.

The focused codec, tempo and transform set passes 52 tests. The unrestricted
codec, tempo, transform, CLI, anchor and Workbench consumer set passes 102
tests. DeepSeek V4 Flash supplied an independent read-only compatibility
inventory; Codex verified its findings against every consumer, retained the
anchor helper it identified and completed the implementation and acceptance
review.

## Measured change

| Measure | Phase 4 increment 4 | Phase 4 increment 5 | Change |
|---|---:|---:|---:|
| Transform `_parse_track` CRAP | 42.592593 | removed behind codec | warning removed |
| Transform `_parse_midi` CRAP | 18.089010 | 6.000000 | -12.089010 |
| Highest new compatibility-helper CRAP | not applicable | 5.000000 | below threshold |
| Repository CRAP load above 30 | 49,686.745151 | 49,674.152558 | -12.592593 |
| Advisory CRAP warnings | 560 | 559 | -1 |
| Measured functions | 6,675 | 6,681 | +6 |
| Combined branch-aware coverage | 75.964897% | 75.985351% | +0.020454 points |
| Source modules | 415 | 415 | unchanged |
| Internal dependencies | 1,608 | 1,609 | +1 intended dependency |
| Static cycles | 6 | 6 | unchanged |
| Contract violations | 0 | 0 | unchanged |

The changed-code ratchet covers 15 materially changed and seven new functions
with no failure. Its first run rejected a complexity increase in
`_parse_meta_event`; moving the optional tempo-policy check into one fully
covered complexity-4 helper made the final ratchet pass. The architecture
ratchet reports no added module, cycle, violation or public-interface change.

## Deterministic evidence

The final unrestricted macOS branch-coverage run completed with 3,886 tests
passing, 15 skipped, 13 deselected and 656 subtests passing. Two independently
generated CRAP reports, coverage bindings and current mutation reports are
byte-identical within each pair:

- CRAP report SHA-256:
  `ab0f8faf283331447660b308935ac0aece7ccaa4e9f263c674fc10725fec31f5`;
- coverage-binding SHA-256:
  `31ea08f68002e7228139becfbd7ab62ba02228a202c4c0fafa1ed930e047c645`;
- coverage JSON SHA-256:
  `3bb7fabcc2be9a6a20e39f1895908dbef463d55b6954e2f9e1ee1fbc40847f89`;
- current mutation report SHA-256:
  `ffeec763b2818392d80fb500c49b748a33f33989f59f629bd447839f7f6ef9ff`;
- architecture snapshot SHA-256:
  `b6c64a36daaf5251c2af884d7548dc9faa09bd94aef91c5936dc759427496c68`;
  and
- production source-tree SHA-256:
  `66e4e5e58c7f580191c1dc93d0eaa2de155dec25c6f61e1400120a58d4b6e0fe`.

Ruff, diff whitespace, the changed-code CRAP ratchet, the architecture
ratchet and all three architecture contracts pass. The source-current viewer
attaches 415 coverage, 6,690 CRAP, 1,391 established-pilot mutation and six
semantic records with zero diagnostics and 415 unique source pages.

Local reproducible evidence is under
`work/quality/deep-module-midi-transform-codec-2026-08-25/final-macos-3/`.
The source-current explorer is under
`work/architecture-viewer-midi-transform-codec-2026-08-25-3/`.

No private or source audio was read, no model or checkpoint was loaded, and no
inference, MIDI musical selection or render was performed.

## Next bounded step

Split `midi_transform.transform_midi_path` batch discovery, destination
preflight and prepared-write coordination behind narrow private helpers. It is
the remaining transform warning at CRAP 46.285714. Preserve every path,
collision, symlink, atomic-publication and whole-batch preflight behavior; do
not combine that refactor with Clip semantics, anchor delta rewriting or a new
shared cross-module path utility.
