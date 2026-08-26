## Summary

Describe the user-visible change, the compatibility boundary and the exact
facade or workflow affected.

## Verification

- [ ] This branch was created from current `origin/main`; if work crossed a
      24-hour boundary, `main` was refreshed and proposed-merge checks were
      rerun after integration.
- [ ] Focused tests cover the changed behaviour and failure boundaries.
- [ ] The applicable full test suite and Ruff pass.
- [ ] Architecture contracts pass for the proposed merged tree.
- [ ] The changed-function CRAP ratchet passes, or this PR explains why it is
      not applicable.
- [ ] A bounded mutation report was reviewed when a configured pilot module
      changed, or this PR explains why it is not applicable.
- [ ] No private audio, MIDI, reviews, filenames, credentials or local quality
      caches are included.

## Deep-module review

- [ ] The module owns one coherent piece of design knowledge.
- [ ] Callers know fewer implementation details after this change.
- [ ] The common case uses a small, typed interface.
- [ ] Errors, side effects and ordering rules are explicit at the boundary.
- [ ] The implementation can change without changing callers, evidence schemas
      or musical authority.
- [ ] The change reduces duplicated knowledge or change amplification instead
      of creating forwarding layers solely to improve metrics.

Explain any unchecked item or mark it not applicable:

<!-- Design and quality notes -->
