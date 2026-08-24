# CRAP, mutation testing and deep modules for Sunofriend

Status: exploration and implementation plan, 23 August 2026. This document
does not change production code, install tools or authorize any audio/model
operation.

## The proposal in one page

Sunofriend should adopt the three ideas as one small feedback loop:

1. **CRAP identifies change risk.** Combine function-level cyclomatic
   complexity with branch-aware test coverage. Use the original score of more
   than 30 as the first warning threshold, not a repo-wide target of 6.
2. **Mutation testing checks whether the tests notice meaningful mistakes.**
   Start with three pure, fast modules. Do not begin with model workers, audio
   execution, subprocess supervision or localhost servers.
3. **Deep modules reduce the amount of system knowledge a caller needs.** Keep
   a small stable facade while moving format, validation, persistence or
   platform knowledge behind it. A deep module may be large; splitting a file
   into many thin wrappers is not the goal.
4. **Adopt the checks as a ratchet.** Measure the existing code without failing
   it, then prevent new or changed functions from making the result worse.
5. **Refactor one seam at a time.** Characterize current behaviour, run the
   mutation pilot, preserve schemas and hashes, refactor behind a compatibility
   facade, and run the deterministic checks again.

This extends the existing [architecture](ARCHITECTURE.md),
[technical tour](TECHNICAL_TOUR.md) and
[separation maintainability plan](SEPARATION_MAINTAINABILITY_PLAN.md). It does
not replace their product, privacy or musical-authority rules.

Use the local [architecture explorer](ARCHITECTURE_VIEWER.md) before and after
each structural change. It records static module dependencies, public
interfaces, private implementation definitions and exact source links without
importing application code.

## Sunofriend's starting point

The following is a read-only snapshot of commit `e32f9f1` plus the user's
pre-existing uncommitted work. Counts will change as the repository evolves.

| Measure | Current snapshot |
| --- | ---: |
| Python production modules in `src/sunofriend` | 413 |
| Python production lines | 275,964 |
| Top-level functions and class methods | 6,495 |
| Python test modules | 366 |
| Tests collected | 3,824 total; 3,811 selected by `-m "not trusted_local"` |
| Current Python quality tools | pytest and Ruff |
| Not currently installed in `.venv` | coverage.py, Radon, mutmut, Import Linter |

Ruff's existing McCabe implementation provides a useful complexity-only
snapshot:

| McCabe complexity | Functions over the value | Files containing them |
| --- | ---: | ---: |
| greater than 6 | 1,092 | 329 |
| greater than 8 | 700 | 274 |
| greater than 10 | 471 | 229 |
| greater than 15 | 214 | 129 |
| greater than 20 | 95 | 67 |
| greater than 30 | 26 | 25 |
| greater than 50 | 8 | 7 |

These are **not CRAP scores**. There is no function-level coverage baseline
yet, so a genuine CRAP report cannot currently be calculated. The figures also
show why enabling a strict global limit immediately would produce noise rather
than useful guidance.

The largest McCabe results include `workbench_server.do_POST` (100),
`cli.main` (77), `ai_bakeoff.run_ai_transcription` (64),
`workbench_server.do_GET` (62) and `listen_all.run_listen_all` (51). They are
places to investigate, not automatic refactoring instructions. A long dispatch
function can be well tested and stable; a short function can still leak a
dangerous design decision.

## Non-negotiable Sunofriend boundaries

Quality work must preserve these invariants:

- source audio, MIDI, private reviews and private notes remain local and are
  never added to reports or CI artifacts;
- raw, analytical, AI, repaired, automatic and human-reviewed evidence remain
  distinct;
- coverage, CRAP, mutation score, playback and other automated signals never
  select a musical candidate or authorize rendering, training or promotion;
- old receipts and schemas remain readable where their contracts require it;
- a code refactor may legitimately change an implementation identity, but it
  must never make a consumed approval reusable;
- model installation, inference and private-audio execution remain outside
  this quality initiative; and
- public two-stem/core-four behaviour remains available during each small
  refactor.

## 1. CRAP: where complexity and missing tests meet

CRAP means **Change Risk Anti-Patterns**. For a function `m`, the original
CRAP1 formula is:

```text
CRAP(m) = complexity(m)^2 * (1 - coverage(m))^3 + complexity(m)
```

In this document `coverage` is a decimal from 0 to 1. The original definition
used basis-path coverage and considered a result above 30 problematic. For a
practical Sunofriend v1 report, use coverage.py's per-function combined
statement-and-branch opportunity percentage, collected with branch measurement
enabled. This convention must be recorded in the report so a later formula
change cannot silently rewrite the baseline.

The formula has useful behaviour:

| Complexity | Minimum coverage to keep CRAP at or below 30 |
| ---: | ---: |
| 5 | 0% (the score is exactly 30) |
| 10 | about 42% |
| 15 | about 60% |
| 20 | about 71% |
| 25 | 80% |
| 30 | 100% |
| greater than 30 | impossible without reducing complexity |

This is why CRAP is more useful than either a blanket coverage percentage or a
complexity ceiling by itself. Tests can make moderately complex code safer,
but coverage cannot excuse unlimited branching.

### What CRAP does not prove

CRAP does not measure assertion quality, coupling, cohesion, information
leakage, privacy, musical correctness or whether the right behaviour was
specified. High coverage can execute a branch without checking its result.
Conversely, a schema validator may be intentionally explicit and moderately
complex because it must fail closed. Mutation testing checks test sensitivity;
deep-module review checks design.

The score of 6 discussed in the video should be treated as an experimental
personal threshold, not the initial Sunofriend gate. Even with perfect
coverage, every function with complexity above 6 would fail such a rule, and
the current static snapshot contains 1,092 of those functions. Start from the
original greater-than-30 warning and tighten only after observing real data.

### Proposed deterministic implementation

Do not add these tools to the existing `dev` extra initially. The application
supports Python 3.9, while current coverage.py supports Python 3.10 and later.
Create a separate, pinned `quality` extra and run it under Python 3.11. This
keeps the supported Python matrix intact.

After explicit approval to add dependencies, the first tooling change should:

1. add pinned coverage.py and Radon versions to a `quality` extra;
2. enable branch coverage for `src/sunofriend` and record per-function data;
3. add a small `scripts/report-code-risk.py` tool which combines Radon's
   function complexity with coverage.py's function regions;
4. write a stable, path-free JSON report under `work/quality/`, not into a
   source or private evidence tree; and
5. print a short sorted table of the highest scores and unmeasured functions.

Each function record should contain:

```text
schema, source-relative path, qualified function name, start line,
source hash, tool versions, complexity, covered/possible opportunities,
coverage percentage, CRAP score, threshold and status
```

Sort by score descending and then by path/name. Reject non-finite values,
duplicate function identities and mismatched source hashes. Report nested
functions explicitly rather than silently assigning their lines to a parent.
The generated report should contain no absolute paths, timestamps, audio names
or private data.

Use Ruff `C901` as the cheap static signal already available in the repository,
but do not call it CRAP. Ruff can warn before tests run; the CRAP report is the
combined result after tests.

### Scope and exclusions

The first report should cover all Python under `src/sunofriend`, including
private modules. It should not include:

- tests themselves;
- one-off files under `scripts/`;
- generated package metadata under `src/sunofriend.egg-info`;
- C, HTML or JavaScript assets; or
- `website/dist`, `website/.next`, dependencies and generated web output.

Do not exclude a difficult production file merely to improve the number.
Record code that cannot be measured as `unmeasured` with a reason. Add scripts
and the authored website as later, separate quality lanes because they have
different runtimes and test structures.

### Adoption policy

Use four stages:

1. **Baseline:** publish an advisory artifact; fail only if measurement is
   incomplete or internally inconsistent.
2. **Changed-code ratchet:** a new or materially changed function must not
   exceed CRAP 30. An existing changed function must not increase its CRAP
   score or reduce its branch-aware coverage.
3. **Hotspot reduction:** track the count above 30 and a "CRAP load" equal to
   the sum of `max(0, score - 30)`. Both should trend down, not become a single
   release gate.
4. **Recalibration:** after several refactors, review whether a lower threshold
   improves decisions. Never lower it merely to imitate another repository.

A small allowlist may document a temporarily accepted legacy hotspot, with an
owner, reason and removal condition. It must not accept new code or wildcard an
entire package.

## 2. Mutation testing: do the tests detect a wrong program?

Mutation testing makes small source changes such as changing `<` to `<=`,
replacing a constant or negating a condition. A good test suite should fail. A
mutation that leaves the tests green is a **surviving mutant** and points to
one of four things:

- a missing assertion or boundary case;
- code executed incidentally rather than tested deliberately;
- dead or redundant code; or
- an equivalent mutation that cannot change observable behaviour.

The last case matters: a 100% mutation score is not a sensible universal
target. Equivalent mutants should be reviewed and recorded; they should not be
hidden with broad exclusions.

### Recommended first pilot

Use mutmut under Python 3.11 and mutate only these modules first:

| Module | Why it is a good pilot |
| --- | --- |
| `source_roles.py` | Pure, deterministic role vocabulary and conservative inference; mistakes can change which musical route is offered. |
| `automatic_selection.py` | Enforces that Simple mode uses only exact published primaries and does not turn ranking into a human decision. |
| `separation_review_transport.py` | Small shared boundary for byte ranges, bounded JSON and owner-only atomic persistence, with direct tests and no model imports. |

This gives a useful spread of policy, validation and reusable infrastructure
without allowing a mutant to reach a model, private song, live network or DAW.

The initial `pyproject.toml` configuration should use an exact `only_mutate`
list, `source_paths = ["src/sunofriend"]` and pytest selection of
`-m "not trusted_local"`. Do not enable `mutate_only_covered_lines` at first;
it can make the result look better by omitting precisely the untested lines we
need to see. Keep mutmut's cache/results directory ignored and outside product
artifacts.

The working commands should be recorded by the implementation change. The
intended shape is:

```bash
python -m mutmut run "sunofriend.source_roles*"
python -m mutmut run "sunofriend.automatic_selection*"
python -m mutmut run "sunofriend.separation_review_transport*"
python -m mutmut results
```

Confirm the exact target names against the pinned mutmut version before making
these commands a contract.

### Mutation acceptance policy

For the first run:

- report killed, survived, suspicious, timeout, untested and skipped states
  separately;
- do not fail the build on the baseline score;
- inspect a small sample of killed mutants to prove the intended tests ran;
- write or strengthen tests for genuine survivors; and
- record equivalent mutants by exact module/function/mutation and explanation.

After the pilot stabilizes:

- changed functions must not introduce a new survivor;
- timeouts, crashes and collection failures are tool failures, not killed
  mutants;
- new exclusions require review; and
- a module-specific score floor may be introduced only after the denominator
  and equivalent-mutant policy are stable.

Run changed-function mutation checks on pull requests if they stay within a
short budget. Run the complete pilot nightly or manually. Do not place the full
3,824-test suite inside every mutation loop if mutmut can select the relevant
tests safely.

### Safety boundary for later expansion

Do not mutate model loaders, setup scripts, private-audio runners, native
process supervision, network guards or approval-consuming execution paths
until their tests are fully hermetic. A weakened guard inside a mutant must not
create a real side effect. Use generated/fake inputs, denied network, fresh
temporary output and exact attempt counters before expanding into those areas.

The authored website currently has one build/render test rather than a unit
test surface suitable for useful mutation analysis. Add focused behaviour tests
before considering StrykerJS. Embedded Workbench JavaScript should likewise be
extracted behind stable browser-facing contracts before adding a second
mutation system.

## 3. Deep modules: hide knowledge behind a small interface

A module is deep when its interface is much simpler than the functionality and
knowledge it hides. Its interface includes more than function signatures: it
also includes side effects, ordering rules, schemas, error handling and facts a
caller must remember.

Deep does **not** mean:

- every file is small;
- every function has only a few lines;
- every phase of an operation gets its own class; or
- a facade simply forwards all of its parameters to many shallow helpers.

Before extracting a module, answer:

1. What unique design knowledge will this module own?
2. Which details will callers no longer need to know?
3. Can the common case use one small typed operation?
4. Are errors and side effects explicit at the boundary?
5. Can the implementation change without changing callers, schemas or musical
   authority?
6. Does the extraction reduce duplicated knowledge and change amplification?

### Existing Sunofriend examples worth preserving

- `separation_review_transport.py` hides HTTP range parsing, bounded request
  bodies, no-store responses and private atomic JSON persistence. A static
  import scan found no imports from other Sunofriend modules, while seven
  review modules reuse it.
- `_private_atomic_directory.py` hides safe basenames, no-follow directory
  traversal and Darwin/Linux exclusive rename details from its callers.
- `simple_create.py` plus `simple_create_contract.py` gives the TUI a typed
  automatic-create operation without moving musical algorithms into the UI.

These are more useful patterns than indiscriminately making every class or
function shorter.

### Highest-value deepening opportunities

#### A. Full-song recovery behind one facade

`separation_fine_stem_full_song_recovery.py` is currently 2,053 lines with 12
exported names. The existing maintainability plan already identifies its next
seams. Keep the current module as the compatibility facade and move private
implementation knowledge into:

- a pure request/report contract;
- retained-tree and verified-input binding;
- projection and persistence; and
- publication orchestration.

The facade should continue to offer the small operations callers need:
build/validate a request, execute recovery, validate a report and calculate
canonical hashes. The new internal modules should not become new integration
APIs. Preserve historical readability, owner-only permissions, exact input
binding, exclusive publication and the incomplete resource-gate status.

This is the recommended first structural refactor because it follows an
already documented boundary. Do only the contract extraction first; do not
split all four seams in one change.

#### B. One lossless Standard MIDI File codec

`clip.py`, `midi_tempo.py` and `midi_transform.py` each contain MIDI scanning,
track parsing or variable-length integer knowledge. The architecture plan
already calls for one lossless codec. A deep codec should hide:

- header and track chunks;
- running status and variable-length integers;
- meta, SysEx and channel events;
- byte offsets and unchanged byte ranges; and
- safe rewriting of only the requested events.

The public API should be small—parse/inspect and rewrite—while `Clip` remains a
semantic musical representation rather than the lossless storage model. Before
moving a parser, characterize byte-for-byte behaviour for tempo maps,
controllers, channel 10 drums, pitch bends, running status and SysEx. Migrate
one caller at a time behind compatibility functions.

#### C. Finish the shared review transport boundary

At least eleven modules still define a `build_*review_server` function. The
shared transport is a good start, but page builders still repeat routing and
server assembly. Deepen it with composition: a review-specific component owns
schema validation, report bindings and page content; the transport owns only
localhost HTTP, bounded bodies, byte ranges, atomic persistence and downloads.

Do not build one universal review object that understands musical ratings,
source selection and every schema. That would centralize unrelated policy and
turn a deep infrastructure module into a shallow, sprawling interface.

#### D. Defer the giant CLI/server dispatchers

`cli.main` and Workbench `do_GET`/`do_POST` are obvious complexity hotspots,
but they are compatibility surfaces. First establish deep application
operations and route-specific handlers. Then a dispatch table can become a
thin adapter without moving domain logic into command objects or changing CLI
names, exit codes, URLs or JSON schemas merely to reduce McCabe numbers.

### Deterministic architecture checks

Architecture should be executable, not only prose. Start with one small
standard-library import test because Sunofriend is currently a flat package:

- pure contract modules must not import CLI, TUI, HTTP, model or audio runtime
  modules;
- `separation_review_transport` must not import selection, activation, MIDI or
  model modules;
- domain/application modules must not import `cli` or `tui`; and
- compatibility facades may import their private implementations, but those
  implementations must not import back through the facade.

When the incremental package move described in the separation maintainability
plan begins, replace or supplement the test with Import Linter contracts for
forbidden imports and dependency layers. A useful target direction is:

```text
CLI / TUI / scripts
        |
        v
application facades and bounded runners
        |
        +----> contracts
        +----> guards and adapters
        +----> publication

review-specific policy ----> shared review transport
          |
          +---------------> contracts
```

Lower layers must not import interfaces above them. Review transport must not
gain musical decision authority. Add contracts only for boundaries the current
code already satisfies; fix a violation before creating a permanent ignore.

## The combined refactoring gauntlet

Use this loop for one small story or seam:

1. State the user-visible behaviour, evidence contract and invariants in a few
   sentences.
2. Identify the exact facade and current callers. Do not produce a large
   speculative redesign.
3. Add characterization tests for current bytes, schemas, errors and side
   effects.
4. Record the current CRAP result and run mutation testing on the selected pure
   functions.
5. Sketch two possible interfaces and choose the one that hides more knowledge
   with fewer caller obligations.
6. Refactor one seam behind the existing facade.
7. Run focused tests, Ruff, the full applicable suite, the CRAP ratchet,
   mutation checks and architecture contracts.
8. Inspect the dependency change and public surface. Update architecture,
   technical-tour and skill text only where behaviour or a maintained path
   genuinely changed.

When multiple agents are available, fresh contexts can keep the jobs narrow:

- an implementer preserves behaviour behind the facade;
- a cleaner reviews CRAP and information leakage;
- a hardener runs mutation testing and adds missing assertions; and
- a QA/reviewer checks the public workflow and retained invariants.

The agents' opinions are advisory. Deterministic checks enforce technical
facts, and a person remains the authority for musical usefulness and product
decisions.

## CI shape

Do not slow every existing job immediately.

### Pull requests

- retain the current pytest and Ruff jobs;
- run a fast architecture-contract test;
- generate the changed-function CRAP report on Python 3.11;
- fail only on an invalid report or a changed-code ratchet violation; and
- run mutation testing only for changed pilot modules within a fixed time
  budget.

### Nightly or manual quality run

- run the full non-`trusted_local` macOS Python 3.11 suite with branch coverage;
- generate the complete CRAP JSON and a short human-readable summary;
- run the complete three-module mutation pilot; and
- retain only path-free quality reports and logs with no private inputs.

Use macOS coverage for the complete package because the existing Linux CI
deliberately excludes separation tests. A Linux-only coverage report would
incorrectly label much of the platform-specific code as untested. Pure-module
mutation jobs may run on Linux when their tests are platform-neutral.

## Phased implementation

### Phase 0 — map and agree

- Generate the dependency-free local architecture explorer and save a fresh
  pre-change view.
- No third-party dependencies, CI or production runtime change.
- Record the current complexity and repository structure.
- Agree the formula, scope, thresholds and safety boundaries.

### Phase 1 — measurement only

- With explicit dependency approval, add the pinned `quality` extra,
  coverage/Radon configuration and `report-code-risk.py`.
- Generate the first complete report twice and require byte-identical output
  for the same source and coverage data.
- Keep the report advisory for at least one normal development increment.

### Phase 2 — mutation pilot and ratchet

- Add the exact three-module mutmut configuration.
- Classify every survivor in the first bounded run.
- Enable the changed-code CRAP ratchet and architecture test.
- Do not introduce a global mutation-score gate yet.

### Phase 3 — first deep-module refactor

- Extract only the pure request/report contract from full-song recovery behind
  the existing facade.
- Preserve old schema readability and add characterization, mutation and
  import-boundary tests.
- Stop if an existing approval, receipt identity, public profile or review
  state would acquire broader authority.

### Phase 4 — repeat and broaden

- Continue recovery seams one at a time.
- Introduce the lossless MIDI codec and migrate one caller per change.
- Consolidate remaining review transport mechanics.
- Add Import Linter with the planned package structure.
- Consider JavaScript mutation testing only after focused web/browser unit
  tests exist.

## Definition of success

The initiative is working when:

- every new or changed risky function has an explainable CRAP result;
- tests kill meaningful mutations at the boundaries they claim to protect;
- callers know fewer file-format, persistence, platform and review-transport
  details;
- public interfaces and evidence schemas stay stable through internal changes;
- agents stop thrashing because each task fits within one coherent module; and
- quality checks remain fast enough that developers and agents actually run
  them.

It is not successful if the repository merely gains a higher coverage number,
many tiny forwarding modules, blanket mutation exclusions or a long quality
prompt that can be ignored.

## Primary references

- Alberto Savoia, [This Code is CRAP](https://testing.googleblog.com/2011/02/this-code-is-crap.html): original formula, basis-path coverage and the
  greater-than-30 threshold.
- Ruff, [complex-structure (C901)](https://docs.astral.sh/ruff/rules/complex-structure/): the existing McCabe implementation used for the static snapshot.
- coverage.py, [branch coverage](https://coverage.readthedocs.io/en/latest/branch.html) and [JSON reporting](https://coverage.readthedocs.io/en/latest/commands/cmd_json.html): branch measurement and machine-readable reports.
- Radon, [programmatic cyclomatic-complexity API](https://radon.readthedocs.io/en/master/api.html): function-level complexity data.
- mutmut, [official documentation](https://mutmut.readthedocs.io/en/latest/): incremental mutation workflow, test selection and configuration.
- John Ousterhout, [Modular Design lecture notes](https://web.stanford.edu/~ouster/cgi-bin/cs190-winter18/lecture.php?topic=modularDesign): deep modules and information hiding.
- Import Linter, [contract types](https://import-linter.readthedocs.io/en/latest/contract_types.html): forbidden imports and layered dependency contracts.
