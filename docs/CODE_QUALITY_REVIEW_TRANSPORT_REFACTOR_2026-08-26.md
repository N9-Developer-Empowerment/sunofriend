# Phase 4 increment 7 — review transport application boundary

## Outcome

The first remaining review-server assembly has been migrated behind one
source-bound `LocalReviewApplication` façade. The provider-synth review now
supplies page bytes, verified media routes, its validator and result
destination; the shared transport owns the fixed localhost HTTP routes, range
delivery, bounded JSON input and atomic owner-only persistence.

Existing provider review entry points, route names, server identity, response
bytes, validation order, saved schema, filenames and error text remain
unchanged. Review-specific musical policy and evidence validation remain in
the provider module. The transport gains no authority to approve a stem,
musical choice, render or publication.

## Deep-module assessment

The public interface added by this increment is one configuration object and
one operation:

```python
LocalReviewApplication(...).build_server(host=..., port=...)
```

That interface hides:

- request-handler subclass assembly;
- standard page, health, saved-result and download routes;
- GET/HEAD byte-range behavior;
- bounded JSON decoding and client-safe errors;
- validation-to-atomic-persistence coordination; and
- no-cache response mechanics.

Callers still own the information that should not be generalized:

- their rendered review page;
- already-verified artifact paths and media types;
- review schema and semantic validator;
- review-specific result path and download name; and
- any musical or evidence interpretation.

The implementation was initially placed in a nested handler. Mutation testing
showed that mutmut did not instrument that nested class. The route behavior was
therefore moved into a private top-level handler, leaving the same small public
façade while making its hidden behavior deterministically testable.

## Characterization and mutation evidence

The new end-to-end transport test covers:

- rejection of non-local binding;
- page and query routing, server identity and no-cache headers;
- health, missing and persisted-result behavior;
- ranged GET and HEAD media delivery;
- wrong POST routes and validator rejection;
- stable JSON bytes and owner-only file permissions; and
- exact attachment filename and configurable content type.

A provider-specific characterization test preserves the earlier host-check
ordering before package-root resolution. The existing provider review test
also verifies its historical JSON download type.

| Mutation measure | Exact main | Final branch | Change |
|---|---:|---:|---:|
| Transport mutants | 404 | 504 | +100 testable changes |
| Killed | 349 | 447 | +98 |
| Survived | 55 | 57 | +2 total |
| Genuine test-gap survivors | 55 | 54 | -1 |
| Tool-model limitations | 0 | 3 | +3 documented equivalents |
| Kill rate | 86.386% | 88.690% | +2.304 points |

The three tool limitations alter the redundant `body` argument passed during
HEAD handling. The base ranged-file sender independently suppresses the body
for every HTTP HEAD command, so those mutations cannot change observable
behavior. All nine meaningful survivors introduced by the new handler were
killed after exact response assertions were added.

## CRAP, coverage and architecture

The changed-function CRAP ratchet rejected the first final candidate because
the migrated provider builder increased from CRAP 4.010520 to 5.000000. The
extra branch was a redundant media-route dictionary comprehension. Building
the final route values directly restored complexity 4 and a fully covered CRAP
score of 4.000000.

| Measure | Exact main | Final branch | Change |
|---|---:|---:|---:|
| Provider server-builder CRAP | 4.010520 | 4.000000 | -0.010520 |
| Repository CRAP load | 50,307.616300 | 50,307.616300 | unchanged |
| Advisory CRAP warnings | 565 | 565 | unchanged |
| Measured functions | 7,463 | 7,464 | +1 net |
| Combined branch-aware coverage | 76.164163% | 76.182168% | +0.018005 points |
| Statement coverage | 80.489937% | 80.505168% | +0.015231 points |
| Branch coverage | 64.265173% | 64.289256% | +0.024083 points |
| Source modules | 453 | 453 | unchanged |
| Internal dependencies | 1,722 | 1,722 | unchanged |
| Static cycles | 7 | 7 | unchanged |
| Contract violations | 0 | 0 | unchanged |

The architecture diff reports no added or removed module or dependency edge,
no new cycle and no contract violation. It records one intentional public
interface addition: `LocalReviewApplication.build_server`. All three
architecture contracts pass.

## Deterministic evidence

The final complete macOS branch-coverage run finished with 4,219 tests passing,
15 skipped, 13 deselected and 658 subtests passing. Focused transport,
provider and mutation-report validation passes 47 tests. Ruff and whitespace
checks pass.

- CRAP report SHA-256:
  `bcd6427eb35b4da4c1a6a22d7ea1d245b7f68c36548d69606583869dd0e139ac`;
- coverage-binding SHA-256:
  `b37ba1fa2f5637afe62fab94f65b36f2f6262028626f4b668559502a385cfb36`;
- coverage JSON SHA-256:
  `60e81b83c9b286542983b0ca73a989ce1159c05af2255d9c5701098d77586389`;
- mutation report SHA-256:
  `58776ccd7a2c6a8a5aa98e3773aa4073b05f29684ee7be558f151bd536f70d41`;
- architecture snapshot SHA-256:
  `32b7bf86d5db11032a9d39e27a55be0a80941f1ce6e787e3f065b213ab4e8d6d`;
  and
- production source-tree SHA-256:
  `376ec6bf63740025d48d50adf5c2f6d81cf309cf4f44d4dca46514772717f01c`.

Local reproducible evidence is under
`work/quality/repository-hygiene-2026-08-26/`.
The source-current explorer is under
`work/architecture-viewer-review-transport-2026-08-26/`.

No private or source audio was read, no model or checkpoint was loaded, and no
inference, render, upload or musical decision was performed.

## Next bounded step

Six review modules still assemble a
`LocalReviewRequestHandler` subclass directly, and one additional report
server has its own handler. Migrate only one independently after preserving its
route, schema, validation-order and artifact-boundary behavior. Do not turn the
transport façade into a universal review-policy object.
