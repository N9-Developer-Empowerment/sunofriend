# Sunofriend repository instructions

These instructions apply to every agent working anywhere in this repository.

## Protect the product boundary

- Keep private audio, MIDI, reviews, filenames and musical notes local. Never
  place them in commits, CI artifacts, issues or prompts sent to external
  services.
- Automated tests, coverage, CRAP, mutation results, architecture diagrams and
  playback are technical evidence only. They never select musical material or
  authorize rendering, training, publishing, promotion or a review decision.
- Preserve the distinction between raw, analytical, AI-generated, repaired,
  automatic and human-reviewed evidence.
- Do not install dependencies, models, checkpoints or plug-ins without the
  user's explicit approval.

## Quality workflow for features and refactors

Use the bounded gauntlet in
`docs/CODE_QUALITY_AND_DEEP_MODULES_PLAN.md` for every material feature or
refactor:

1. State the visible behaviour, evidence contract, errors, side effects and
   authority boundaries. Identify the current facade and callers.
2. Add characterization tests before changing bytes, schemas, validation
   order, persistence or other compatibility behaviour.
3. Prefer one coherent module that hides design knowledge behind a small
   interface. Do not create many forwarding helpers merely to reduce a score.
4. Always run focused tests, Ruff and architecture contracts locally. Run the
   applicable full suite, changed-function CRAP ratchet and selected mutation
   lane locally when the risk triggers below apply.
5. Inspect the dependency and public-interface diff before accepting the
   change. Do not expose a private implementation module as a new integration
   API.

For CRAP:

- New executable functions must have CRAP at or below 30.
- A materially changed existing function must not increase CRAP or reduce its
  branch-aware coverage relative to the feature branch's recorded base
  revision.
- Historical untouched hotspots are advisory. Do not broaden a feature just to
  improve unrelated repository totals.

For mutation testing:

- Do not run mutation testing automatically for every pull request. Run the
  bounded local mutation lane when a change touches one of the pilot modules
  in `pyproject.toml`, changes a safety-critical condition, or introduces a
  test whose assertion strength is uncertain.
- Surviving mutants remain explicit review evidence; do not hide them with a
  broad exclusion or treat a timeout, crash or collection failure as killed.
- Do not mutate model loaders, private-audio runners, network guards, native
  supervision or approval-consuming paths until their tests are hermetic.

For deep-module review, answer these questions in the pull request:

1. What unique design knowledge does the module own?
2. Which details do callers no longer need to know?
3. Is the common case exposed through one small, typed operation?
4. Are errors, side effects and ordering rules explicit?
5. Can the implementation change without changing callers, schemas or musical
   authority?
6. Does the change reduce duplicated knowledge and change amplification?

CRAP and mutation testing cannot prove that a module is deep. The architecture
viewer supplies dependency and interface evidence; a reviewer makes the design
judgment.

## Fast CI and local quality

- Pull requests run one short Linux/Python 3.11 gate: Ruff, architecture
  contracts, a bounded invariant suite, distribution build and wheel smoke.
- Ordinary pushes and merges do not rerun the test matrix. The complete
  coverage/CRAP and mutation workflow is manual-only; normal quality evidence
  is produced locally in the feature worktree.
- Always run focused tests for changed behaviour. Also run the complete local
  non-`trusted_local` suite when a change crosses module boundaries, changes a
  public interface/schema/persistence or authority rule, alters dependencies,
  packaging, audio/ML/platform behaviour, fixes an integration regression, or
  is being prepared for a release.
- Run the local CRAP base-versus-candidate ratchet for new or materially
  changed executable functions. Run the bounded mutation lane under the
  triggers above. Documentation-only and CI-only changes normally need the
  fast invariant checks rather than the complete suite.
- `main` remains the accepted baseline. Record the exact base SHA in the work
  evidence and attach the local commands/results to the pull request. A manual
  GitHub `Manual Full Quality` dispatch is an optional clean-machine fallback,
  not a routine merge gate.

The standard complete local suite is:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  .venv/bin/python -m pytest -q -m 'not trusted_local'
```

Use the isolated commands in `docs/CODE_QUALITY_AND_DEEP_MODULES_PLAN.md` for
coverage, CRAP and mutation evidence. Do not claim a skipped applicable local
lane passed.

## Concurrent work

The user may continue feature development while another agent reviews or
measures code, but use a separate Git branch. Use a separate Git worktree
whenever practical. Do not edit the same mutable checkout concurrently.

- Before starting a material feature or refactor, fetch `origin`, fast-forward
  the clean local `main` worktree, and create the branch/worktree from the exact
  current `origin/main` commit. Record that base commit in the work evidence.
- During active work that spans more than 24 hours, fetch `origin/main` and
  attempt to fast-forward the clean local `main` worktree at least once in each
  24-hour period. Never force an update through a dirty or shared worktree;
  report the blocker and continue from a fresh worktree based on `origin/main`.
- If `main` advances, integrate it in a clean worktree and rerun the applicable
  proposed-merge checks before final acceptance. Do not continue new work on a
  branch that has already been merged or superseded.
- After merge, delete local and remote feature branches only after verifying
  that they contain no unique commits, patches or uncommitted files. Preserve
  active or unique work explicitly with a named worktree, branch or archive.

Never stage, rewrite or discard unrelated user changes.
