# Sunofriend architecture explorer

The architecture explorer is a local, deterministic view and governance check
for Sunofriend's Python package. It parses source and tests with `ast`; it does
not import or execute application code, launch model workers, inspect audio, or
make network requests.

It supports the feedback loop needed for CRAP, mutation-testing and deep-module
work: observe the current structure, enforce a small set of intended boundaries,
compare a refactor with a hash-bound baseline, and inspect exact evidence before
accepting the change.

## Views and evidence

The browser moves through these levels:

```text
system context and effects
  -> runtime/product container
    -> architecture area
      -> subarea/component
        -> Python module
          -> interface or implementation symbol
            -> escaped source with line anchors
```

For each module it shows:

- public top-level definitions, public class members and re-exports;
- private implementation definitions;
- outgoing and incoming imports with source line, requested import, symbols,
  module/deferred scope, guard (`none`, conditional, `try`, or
  `TYPE_CHECKING`) and confidence;
- dashed boundary stubs for dependencies outside the selected area;
- contract violations and their exact import evidence;
- approximate static calls, object construction and inheritance;
- test files which directly import the module;
- static filesystem, process, network and dynamic-import call candidates;
- maintained semantic/deep-module annotations; and
- optional source-bound coverage, CRAP, mutation and runtime-effect evidence.

Static calls and effects are candidates, not runtime proof. Playback, coverage,
CRAP, mutation status and graph position never authorize a musical decision,
model run, render, selection or publication.

## Plan, build and check

Always inspect a fresh plan first:

```bash
.venv/bin/python -m devtools.architecture_viewer --plan
```

The plan reports source and architecture hashes, counts, parse errors, contract
results and a write-free effects receipt. Then build into a fresh directory:

```bash
.venv/bin/python -m devtools.architecture_viewer \
  --out work/architecture-viewer-NEW-SNAPSHOT
```

Snapshot directories are immutable. If the requested directory already
exists, the CLI preserves it and builds into the first available numbered
sibling, such as `architecture-viewer-NEW-SNAPSHOT-2`. It prints the actual
`index.html` path on standard output. The Python renderer API remains strict
and raises `FileExistsError` for an existing destination.

The command publishes owner-only files:

```text
index.html                offline interactive explorer
architecture.json         deterministic v2 graph and source evidence
architecture-check.json   contract and parse result
overlays.json             normalized optional evidence lanes
architecture-diff.json    optional comparison, when --diff is also supplied
code/*.html               escaped, collision-safe source pages
```

Run the deterministic boundary gate without building pages:

```bash
.venv/bin/python -m devtools.architecture_viewer --check
```

It exits nonzero for source parse errors, scanned-test parse errors or an
enforced contract violation.

To retain a machine-readable baseline without source pages:

```bash
.venv/bin/python -m devtools.architecture_viewer \
  --snapshot-out work/architecture-before.json
```

Snapshots and pages contain source structure and, for pages, source code. Keep
them local unless publication is a separate intentional decision.

## Nested areas and architecture contracts

[`architecture-viewer-groups.json`](architecture-viewer-groups.json) is the
maintained hierarchy and contract specification. A configured group can contain
`children`; module assignment uses exact names before patterns before prefixes,
with deeper matching groups preferred. Every module is assigned, including to
the explicit default group, and empty configured groups remain visible.

Supported contract types are:

- `forbidden`: selected sources must not import selected targets;
- `allowed`: selected sources may import only the selected targets;
- `independence`: selected member sets must not import one another;
- `layers`: lower layers must not import earlier upper layers; and
- `acyclic`: the selected induced graph must contain no cycle.

An exception must name the exact source and target, explain the reason, and
include either an `until` value or a `review_condition`. Exceptions remain
visible as ignored evidence; they are not silently deleted.

The current contracts intentionally start small. Visual grouping is not itself
an import rule. Add a contract only when the dependency direction expresses a
real maintained boundary and its existing exceptions can be reviewed.

## Before/after comparisons and ratchets

Compare current source with a v1 legacy or integrity-checked v2 snapshot:

```bash
.venv/bin/python -m devtools.architecture_viewer \
  --diff work/architecture-before.json
```

The comparison reports added, removed, changed and moved modules; dependency
changes; public top-level and class-member API changes; cycles; contract
violations; group sizes; and per-module fan-in, fan-out, interface,
implementation and line-count changes. It does not infer renames.

Build the comparison into the browser with:

```bash
.venv/bin/python -m devtools.architecture_viewer \
  --diff work/architecture-before.json \
  --out work/architecture-viewer-AFTER
```

The no-new-regressions gate is:

```bash
.venv/bin/python -m devtools.architecture_viewer \
  --ratchet work/architecture-before.json
```

It fails for new cycles, new contract violations, current source parse errors
or current scanned-test parse errors. It deliberately does not claim that every
historical issue must be fixed in one refactor.

## Semantic, effect and quality overlays

The viewer consumes neutral JSON reports; it does not run coverage or mutation
tools itself.

```bash
.venv/bin/python -m devtools.architecture_viewer \
  --semantic-annotations docs/architecture-viewer-semantics.json \
  --runtime-effects work/quality/runtime-effects.json \
  --coverage-json work/quality/coverage.json \
  --coverage-binding work/quality/coverage-binding.json \
  --risk-report work/quality/code-risk.json \
  --mutation-report work/quality/mutation.json \
  --out work/architecture-viewer-WITH-QUALITY
```

Supported schemas are:

- `sunofriend-architecture-semantics.v1`;
- `sunofriend-architecture-effects.v1`;
- coverage.py JSON plus `sunofriend-coverage-binding.v1`;
- `sunofriend-code-risk.v1`; and
- `sunofriend-mutation-report.v1`.

Function-level quality records bind to repository-relative path, module,
qualified name, exact line range, module source SHA-256 and source-tree SHA-256.
The analyser records nested functions separately for this binding without
misrepresenting them as public API.
The viewer labels evidence `current`, `unbound`, `source_stale`,
`snapshot_stale`, `symbol_stale_or_missing` or `orphaned`; it never presents
stale evidence as current. Mutation reports also preserve source-before and
source-after identity so a non-restored run is invalid rather than a score.

CRAP uses the declared CRAP1 formula:

```text
complexity^2 * (1 - coverage_fraction)^3 + complexity
```

The report must state covered and possible branch-aware opportunities. Static
complexity without coverage is not labelled CRAP. Installing or running
coverage.py, Radon or mutmut remains a separate quality-workflow step requiring
the dependency and execution approval described in
[`CODE_QUALITY_AND_DEEP_MODULES_PLAN.md`](CODE_QUALITY_AND_DEEP_MODULES_PLAN.md).

The dependency-free report adapter is available at
`scripts/report-code-risk.py`. It validates coverage.py format-3 function
regions, requires branch data, obtains exact function complexity through
Radon's supported programmatic visitor, rejects absolute input paths, and
writes deterministic owner-only `sunofriend-code-risk.v1` JSON. A missing
Radon installation is reported as an approval-gated blocker.

Maintained semantic records can describe responsibility, supported entry
points, inputs, outputs, stability, knowledge hidden, caller obligations,
effects, errors, schemas and authority boundaries. `intent` claims describe the
desired boundary; hash-bound `source_observation` claims describe one exact
snapshot. The declared system nodes and relationships are maintained intent,
not observed runtime behavior.

## Small agent queries

Fresh-context agents should request a bounded slice rather than load the whole
graph:

```bash
.venv/bin/python -m devtools.architecture_viewer --module sunofriend.source_roles
.venv/bin/python -m devtools.architecture_viewer \
  --neighbourhood sunofriend.source_roles --depth 2
.venv/bin/python -m devtools.architecture_viewer --violations
.venv/bin/python -m devtools.architecture_viewer --cycles
.venv/bin/python -m devtools.architecture_viewer \
  --why-dependency sunofriend.cli sunofriend.source_roles
```

Each JSON answer includes the source-tree and architecture identity. Module
queries include static relations, test links, effects and exact imports. The
browser also provides a copyable, hash-bound module inspection prompt.

## Regression and security guarantees

The focused suite covers analysis, hierarchy, all five contract types,
provenance, diffs, ratchets, overlays, CLI exits, integrity checks, escaping,
permissions, stale source, symlink escapes and collision-safe code pages:

```bash
.venv/bin/python -m pytest -q tests/test_architecture_viewer*.py
.venv/bin/python -m pytest -q tests/test_code_risk_report.py
.venv/bin/python -m ruff check \
  devtools/architecture_viewer devtools/code_risk.py \
  scripts/report-code-risk.py tests/test_architecture_viewer*.py \
  tests/test_code_risk_report.py
```

When Node is available, the suite also executes the embedded browser script
against a dependency-free DOM stub and verifies module-hash navigation,
breadcrumbs and search. It skips that one smoke check when Node is absent; Node
is not an application dependency.

Generated pages use a restrictive content security policy, make no fetch or
XHR requests, escape source and JSON script data, use owner-only permissions,
verify v2 snapshot integrity, reject source/test symlink escapes, recheck the
complete source-file set and hashes before rendering, and publish only to a
fresh destination.

## Refactoring workflow

For one bounded seam:

1. Generate and retain a fresh pre-change snapshot.
2. Inspect the candidate's public interface, semantic responsibility, exact
   imports, callers, tests and effect candidates.
3. Add characterization tests for bytes, schemas, errors and authority gates.
4. Attach current coverage/CRAP/mutation evidence when that separately approved
   quality workflow is available.
5. Refactor behind the existing facade without broadening authority.
6. Run focused and applicable full tests, Ruff and `--check`.
7. Run `--ratchet` and inspect the full `--diff`.
8. Generate a fresh post-change viewer and inspect the intended dependency and
   public-surface changes.

## Limits

- The primary graph is Python-only. Maintained system annotations represent
  JavaScript, HTML, shell, C, processes and stores at a higher level.
- Non-literal dynamic imports and dependency-injected runtime relationships may
  be absent.
- Static call resolution is approximate and intentionally bounded; inheritance
  is not proof of structural protocol conformance.
- Test relationships prove direct imports, not which assertion covers a
  function. Coverage contexts can add execution evidence when supplied.
- Static effect candidates do not prove an effect occurs, and absence does not
  prove purity.
- Semantic annotations and group assignments require human maintenance.
- The viewer supplies evidence and deterministic checks; it does not decide
  whether a proposed module boundary is musically or strategically correct.
