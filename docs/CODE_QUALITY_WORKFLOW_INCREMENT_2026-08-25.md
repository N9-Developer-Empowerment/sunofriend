# Quality workflow increment — feature gate integration

## Outcome

This bounded process increment makes the established CRAP, mutation and
deep-module policy part of ordinary feature development before the planned
review-transport refactor. It changes repository instructions, CI and quality
reporting support only. No `src/sunofriend` production module or public product
interface is changed.

The root `AGENTS.md` now requires each material feature or refactor to identify
its facade, callers, behavior, evidence, effects and authority boundary; add
characterization tests; use a coherent deep-module interface; run the quality
gauntlet; and inspect the dependency and public-interface diff. It also records
the CRAP threshold, bounded mutation policy, six deep-module questions and
local/private musical-evidence restrictions.

The pull-request template makes those questions visible at review time rather
than relying on a long agent prompt.

## What is checked

The workflow separates integration health from changed-code risk:

| Scope | Check |
| --- | --- |
| Proposed merged tree | Existing pytest, Ruff and architecture-contract jobs protect the complete candidate repository. |
| Exact PR base and proposed merge | The macOS Python 3.11 quality job runs complete branch-aware coverage for both and applies the function-source-bound CRAP ratchet. |
| Changed mutation pilot modules | The Linux job runs mutmut only when the PR changes `source_roles.py`, `automatic_selection.py` or `separation_review_transport.py`, then emits a selected-module source-bound report. |
| Current default branch | Nightly and manually dispatched jobs run complete macOS coverage/CRAP and the complete three-module mutation pilot. |

The CRAP ratchet is blocking: new executable functions must remain at or below
30, and changed functions may neither increase CRAP nor reduce branch-aware
coverage. Unchanged historical hotspots are ignored by the ratchet.

The pull-request mutation lane is intentionally advisory about survivors. The
established baseline still contains explicitly classified test gaps and a
documented mutmut trampoline limitation, so a binary global score would be
misleading. Collection failures, untested mutations and report corruption do
block the report; surviving and timed-out mutants remain visible review
evidence.

## Base and merge semantics

For a GitHub pull request, `actions/checkout` supplies the proposed merge. The
workflow uses the exact `pull_request.base.sha` for a detached base worktree and
builds both CRAP reports with the same pinned reporter. This answers two
different questions:

1. Does the feature still integrate safely with the current base branch?
2. Did the functions changed by the feature become riskier than their exact
   base versions?

It does not make every advisory warning already present on `main` block an
unrelated feature. Scheduled and manual jobs still measure the complete current
default branch so historical trends remain visible.

## Concurrent feature development

The user may continue adding features while another agent performs review or
quality measurement, but the work should use a separate branch and preferably
a separate worktree. Two people or agents should not edit the same mutable
checkout concurrently. Before acceptance, refresh the base and rerun the
proposed-merge checks; never stage or rewrite the other workstream's files.

## Safety and artifacts

- The workflow uses `pull_request`, never privileged `pull_request_target`.
- Permissions are read-only and no repository secret or user-owned external
  service is required.
- Only path-free JSON quality evidence is retained.
- No private audio, MIDI, reviews, filenames or musical notes enter CI.
- Metrics and mutation results remain technical evidence and grant no musical,
  rendering, training, publication or review authority.
- No dependency was added to the application runtime; quality and mutation
  dependencies remain isolated extras.

## Validation

- The exact `601e9be` base suite completed with 3,894 tests passing, 15
  skipped, 13 deselected and 656 subtests passing.
- The proposed candidate suite completed with 3,900 tests passing, 15 skipped,
  13 deselected and 656 subtests passing.
- Both reports measured 6,688 of 6,697 functions, marked nine declarations not
  applicable and retained 558 advisory warnings. The ratchet found zero new or
  materially changed production functions and zero failures.
- A real selected-module run exercised all 125 `source_roles` mutants: 98 were
  killed and 27 survived. The selected-module report is complete and classifies
  three survivors as test gaps and 24 as the established mutmut trampoline
  limitation.
- Twenty focused code-risk, ratchet, mutation-report and workflow-policy tests
  pass.
- Ruff passes across `src`, `tests`, `devtools` and `scripts`.
- The GitHub Actions YAML parses successfully.
- All three architecture contracts pass with zero source or test parse errors
  and zero violations.
- Diff whitespace checks pass.

## Next bounded step

After this workflow increment is accepted, the next independent production
increment remains consolidation of repeated review-server assembly behind the
existing shared review transport. It must not move review-specific musical
policy into the transport or create one universal review object.
