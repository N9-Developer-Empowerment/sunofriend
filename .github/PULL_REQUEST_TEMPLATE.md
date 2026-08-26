## Summary

Describe the user-visible change, the compatibility boundary and the exact
facade or workflow affected.

## Verification

- [ ] This branch was created from current `origin/main`; if work crossed a
      24-hour boundary, `main` was refreshed and proposed-merge checks were
      rerun after integration.
- [ ] Focused tests cover the changed behaviour and failure boundaries.
- [ ] Ruff and architecture contracts pass locally.
- [ ] The complete local suite passed when the `AGENTS.md` risk triggers apply,
      or the notes explain why it is not applicable.
- [ ] The local changed-function CRAP ratchet passed for new or materially
      changed executable functions, or the notes explain why it is not
      applicable.
- [ ] A bounded local mutation report was reviewed when a configured pilot
      module or safety-critical condition changed, or the notes explain why it
      is not applicable.
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

<!-- Include exact local commands, base SHA and concise results. -->
