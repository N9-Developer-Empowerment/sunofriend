# Repository hygiene audit — 2026-08-26

## Outcome

The repository was refreshed from `origin`, every pre-existing local and
`origin` feature tip was checked against exact `origin/main`, and superseded
branch names were removed only after their changes were proven present by
ancestry or patch equivalence. Unique legacy Sites history and current local
work were preserved explicitly instead of being discarded.

The quality/refactor branch was created in a separate clean worktree from
`origin/main` commit
`2d4064f6c27804e723fca7367f930fa9572fb7c8`. A second fetch before publication
confirmed that this remained the current main commit.

## Proof used before deletion

For each feature tip, the audit checked:

- whether the tip was an ancestor of `origin/main`;
- whether `git cherry origin/main <branch>` contained any `+` patch;
- whether a corresponding pull request was merged;
- whether an attached worktree contained uncommitted files; and
- whether a non-ancestor history contained files or patches absent from main.

All 42 pull requests present at the initial audit cutoff were merged. Every
deleted feature branch was either a direct ancestor of main or patch-equivalent
to main with no unique `+` patch.

## Cleanup performed

- Deleted 19 merged or patch-equivalent feature branches from `origin`.
- Deleted 24 corresponding superseded local feature branches.
- Removed three obsolete orphan `sites/*` branch refs.
- Preserved the two distinct legacy Sites tips as annotated local archive tags:
  - `archive/legacy-sites-monorepo-20260826`;
  - `archive/legacy-sites-app-20260826`.
- Fast-forwarded the clean local `main` worktree to exact `origin/main`.
- Renamed the dirty primary checkout branch to
  `local/album-cover-workbench-20260826`, removed its misleading upstream and
  left every tracked and untracked user file in place.
- Locked the detached PR 41 and PR-base worktrees because they contain retained
  quality evidence. They were not mistaken for active feature branches.

The configured `sites-source/main` remote-tracking ref was retained. Its
remote could not be refreshed with the available authentication, and its
history is covered by the local archive tags; deleting it without a verified
remote comparison would not be safe.

## Concurrent active work

Two clean feature worktrees appeared after the initial cleanup while the
quality suite was running:

| Branch | Unique tip | State at audit cutoff |
|---|---|---|
| `codex/remix-musicfm-followup-20260826` | `57dc494` | clean, based on current main, one unique commit, remote branch present, not yet in a PR |
| `codex/vocal-candidate-vault-20260826` | `4bb9d24` | clean, based on current main, one unique commit, remote branch present, not yet in a PR |

These are active work, not superseded clutter. They were deliberately retained
and must go through their own review, quality gates and merge before deletion.

## Ongoing rule

`AGENTS.md` and the pull-request template now require material work to start
from freshly fetched `origin/main`. A clean local main should be refreshed at
least once in each 24-hour period of active work. If main advances, the branch
must integrate it and rerun the proposed-merge checks. A merged branch may be
deleted only after proving that it has no unique commits, patches or
uncommitted files.

This keeps feature development parallel without turning branches into an
unreviewed archive or risking loss of local work.
