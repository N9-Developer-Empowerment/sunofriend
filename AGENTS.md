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
4. Run focused tests, Ruff, the applicable full suite, architecture contracts,
   the changed-function CRAP ratchet and any selected mutation lane.
5. Inspect the dependency and public-interface diff before accepting the
   change. Do not expose a private implementation module as a new integration
   API.

For CRAP:

- New executable functions must have CRAP at or below 30.
- A materially changed existing function must not increase CRAP or reduce its
  branch-aware coverage relative to the pull request's base revision.
- Historical untouched hotspots are advisory. Do not broaden a feature just to
  improve unrelated repository totals.

For mutation testing:

- Pull requests run mutation testing only when they change one of the bounded
  pilot modules in `pyproject.toml`.
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

## What CI compares

- `main` is the accepted baseline. Scheduled and manually dispatched quality
  jobs measure the complete current `main` tree.
- A pull request is tested as the proposed merged tree: the feature branch
  combined with its current base revision.
- Tests, Ruff and architecture contracts protect the whole proposed merged
  tree. The CRAP ratchet compares only new or materially changed functions with
  the exact pull-request base. Mutation work is limited to changed pilot
  modules.
- Therefore checks cover both integration with `main` and the code proposed for
  merge; they do not make every historical `main` warning block an unrelated
  feature.

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
