# Phase 4 increment 4 — lossless MIDI codec and tempo migration

## Outcome

The fourth bounded Phase 4 increment introduces one source-bound Standard
MIDI File codec and migrates the existing tempo-retiming boundary without
changing its public command or result interfaces.

The codec retains the exact source bytes, exposes header, track and event
spans, and applies only typed edits. `midi_tempo.py` remains the compatibility
facade for its existing private consumers. No Clip importer, canonical MIDI
writer, transform command, path policy or musical interpretation was changed.

## Deep-module boundary

`midi_codec.py` now hides:

- extended SMF headers and declared track chunks;
- variable-length quantities and running status;
- meta, SysEx, system and channel event widths;
- exact source, event-data, post-End-Of-Track padding and trailing spans;
- source-SHA and object-identity binding for edit handles;
- non-overlap and track-containment checks;
- automatic repair of each affected 32-bit track length; and
- a mandatory parse of the rewritten result before it is returned.

The rewrite interface deliberately supports only the operations needed by the
first migration:

- an equal-width replacement of one parsed event's data bytes; and
- one self-contained, explicit-status, zero-delta event at a track start.

Those constraints prevent an edit from splitting an event, replaying against a
same-shaped different source, changing an event payload's encoded width,
introducing invalid seven-bit channel data, encoding a zero tempo, moving all
existing ticks through a nonzero prefix delta or placing an event after End Of
Track. Unedited bytes are copied directly from the retained source.

The codec accepts valid SMF formats 0, 1 and 2 and retains the raw division.
The tempo adapter separately preserves its established policy of format 0/1,
PPQ timing and exact header-error precedence. This keeps storage knowledge in
the codec and tempo policy in the caller.

## Characterization and review evidence

The new independent fixtures cover:

- extended headers, format 0/1/2 and SMPTE division inspection;
- tempo maps, controllers, channel 10 drums, pitch bend and programs;
- explicit and running channel status across real-time events;
- unknown meta events and both SysEx framing statuses;
- post-End-Of-Track padding and bytes after the declared tracks;
- equal-width tempo replacement and multi-track length repair;
- malformed headers, tracks, VLQs, events and payloads;
- overlapping, escaping, ambiguous and wrong-source edits;
- invalid same-width channel and tempo replacements;
- invalid, multi-event, running-status, End-Of-Track and nonzero-delta inserts;
  and
- the tempo adapter's historical format/SMPTE error precedence.

The direct codec, tempo, transform, anchor, CLI, AI-matrix, hybrid-report,
writer and role-split set passes 104 tests. The final independent ChatGPT code
review reported no remaining correctness or compatibility blocker after three
review-and-fix rounds. DeepSeek Flash supplied a useful pre-implementation
inventory and risk assessment; its later implementation review did not return
within the bounded wait and was stopped without contributing findings.

## Measured change

| Measure | Phase 4 increment 3 | Phase 4 increment 4 | Change |
|---|---:|---:|---:|
| Tempo `_scan_track` CRAP | 42.554470 | removed behind codec | warning removed |
| Tempo `_scan_midi` CRAP | 14.528139 | 10.178089 | -4.350050 |
| Highest codec CRAP | not applicable | 14.196000 | below threshold |
| Repository CRAP load | 49,699.299621 | 49,686.745151 | -12.554470 |
| Advisory CRAP warnings | 561 | 560 | -1 |
| Measured functions | 6,657 | 6,675 | +18 |
| Combined branch-aware coverage | 75.904% | 75.965% | +0.061 points |
| Source modules | 414 | 415 | +1 codec module |
| Internal dependencies | 1,607 | 1,608 | +1 intended dependency |
| Static cycles | 6 | 6 | unchanged |
| Contract violations | 0 | 0 | unchanged |

The changed-code ratchet covers 23 materially changed and 21 new functions
with no failure. The architecture ratchet reports one intended module and
dependency, no new cycle, violation, parse error or existing public-interface
change.

## Deterministic evidence

The unrestricted macOS branch-coverage run completed with 3,881 tests passing,
15 skipped, 13 deselected and 647 subtests passing. Two independently generated
CRAP reports and coverage bindings are byte-identical:

- CRAP report SHA-256:
  `7b95ff529decce1eaa2e2912280dfb2bffe352d01b28b776519b0df8ee585f69`;
- coverage-binding SHA-256:
  `47e0057c22c25488f5a6db66e808302035e2d12ad3ee450ca0cc0a6691b881f6`;
- coverage JSON SHA-256:
  `c2f8bf17985a75b6d839823df48903d82f74b416a78fbcff27aa5f641d3e18cc`;
  and
- production source-tree SHA-256:
  `e3ca05d7fb2d8767be599afe1e5c267b906d52a76028d00efabb675f647c4cc4`.

The first sandboxed coverage attempt was diagnostic only: it produced 3,744
passes, 137 failures and 16 setup errors where loopback/native macOS operations
were denied with `PermissionError`. The exact unrestricted rerun passed those
same groups and is the accepted evidence.

Ruff, diff whitespace, the changed-code CRAP ratchet, the architecture ratchet
and all three architecture contracts pass. The source-current viewer attaches
415 coverage, 6,684 CRAP, 1,391 established-pilot mutation and six semantic
records with zero diagnostics and 415 unique code pages.

Local reproducible evidence is under
`work/quality/deep-module-midi-codec-2026-08-25/final-macos/`. The
source-current explorer is under
`work/architecture-viewer-midi-codec-2026-08-25/`.

No private or source audio was read, no model or checkpoint was loaded, and no
inference or MIDI musical selection was performed.

## Next bounded step

Migrate one additional raw-SMF caller behind the codec in a separate change.
`midi_transform._parse_midi` is the preferred next compatibility boundary
because it already has loss-preservation tests and needs the codec's complete
event spans. Do not combine that migration with `Clip`, writer, batch/path or
review-transport changes.
