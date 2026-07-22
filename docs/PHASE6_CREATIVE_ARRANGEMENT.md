# Phase 6: Creative Arrangement and Reusable MIDI

Status on 22 July 2026: **entry gate passed; Increment 6.0, the first
read-only Clip Library slice, is complete; and Increment 6.1, the explicit
Clip reuse proposal, is complete.**
Broader Phase 6 creative arrangement remains in progress.

Phase 6 builds on the local Workbench without turning Sunofriend into another
DAW. Sunofriend continues to preserve several analytical, specialist, AI and
reviewed-repair MIDI candidates. A person chooses useful parts, and GarageBand
continues to own final performance, patch editing and mixing.

## Phase 5.9 close-out

The first Phase 6 entry gate was resolved from one exact GarageBand pack on
22 July 2026. The path-free result records:

- all eight technical tutorial screens completed;
- a 10/10 score on the 10-question, one-question-at-a-time quiz;
- both named human checks passed, with six passes, no issues and no
  `cannot_tell` answers in each check;
- five selected MIDI payloads, the dry arrangement proxy and no source audio
  in the accepted pack;
- the exact pack member set, receipt, payload sizes and hashes verified;
- original selected MIDI declared unchanged;
- the listened downbeat recorded as `reviewer-observation-only`, because no
  catalog-pinned downbeat was available; and
- every tutorial, quiz, MIDI, candidate, selection, basket, default, feedback,
  submission and automatic-phase-start effect false.

The result therefore sets `phase6_read_only_clip_entry_ready` to true and has
no remaining local Studio acceptance gates. It leaves
`explicit_hybrid_construction_ready` false. The separate Phase 5.3 blind-choice
and source-lineage gates remain open and still control hybrid construction.
Private review note text was not copied into the resolved result and is not
repeated in project documentation.

## Increment 6.0: gated read-only Clip Library

The smallest safe Phase 6 increment is an optional Workbench view over one
existing Clip v1 library. It is a way to find, understand, hear and export a
reusable part. It does not change that part or use it in the current project.

Launch remains explicit. These three flags form one indivisible gate and **all
three are required**:

```bash
sunofriend workbench "/path/to/project" \
  --candidate-root "/path/to/results" \
  --catalog "/path/to/workbench-catalog.json" \
  --state-dir "/path/to/workbench-state" \
  --clip-library "/path/to/existing-clip-library" \
  --phase6-acceptance "/path/to/passed-phase5-acceptance-result.json" \
  --phase6-pack "/path/to/the-exact-accepted-garageband-pack.zip" \
  --open
```

Supplying none of the three flags leaves ordinary Workbench behaviour
unchanged. Supplying only one or two must fail before the Clip library opens.
Sunofriend must not discover an acceptance result, ZIP or library implicitly.
It must verify that the result passed, that it explicitly permits read-only
Clip entry, and that the supplied ZIP is the exact pack named by that result.
The existing library then opens read-only; startup must not initialize,
migrate or repair it.

### Verified completion

The completed local browser exercise opened a real read-only library containing
73 immutable Clips across 51 lineages. It verified:

- bounded browse/search and one path-free Clip detail/lineage view;
- deterministic MIDI reconstruction and download from the immutable Clip;
- a dry local FluidSynth/SoundFont listening proxy made from that same MIDI;
- a repeat request returning a verified content-addressed cache hit;
- token-protected, path-free byte-range delivery of the derived MIDI and WAV;
- the optional Developer Inspector tracing the Clip operations without exposing
  a path or adding an application effect; and
- no musical decision, pack basket, Clip object, library database or source
  candidate mutation.

These checks complete only Increment 6.0. Transformations,
current-arrangement placement, piano-roll/phrase editing, instrument attachment
and explicit hybrids remain later Phase 6 work; Increment 6.1's proposal is a
separate state plane rather than current-arrangement construction.

### Browse and search

The first view provides bounded browse, paging and search over safe Clip v1
fields such as title, role, key, BPM and tags. Search text and paging are
temporary browser state. They are not saved as preference, feedback or project
state.

A Clip detail view may show:

- immutable Clip, object and lineage identities;
- title, role, key, BPM and safe tags;
- revision and path-free parent/version lineage;
- note and chord counts, pitch and velocity ranges, duration and timing mode;
- channel, General MIDI program/drum status and safe instrument suggestions;
  and
- the GarageBand BPM required by the Clip export timing contract.

It must not expose `source_uri`, local paths, source stems, private provenance,
private notes, transform parameters or transform seeds. Unsafe legacy display
text must be replaced with an explicit path-free placeholder rather than
leaked or used as a filesystem locator.

### Dry neutral audition

Audition is requested explicitly from the Clip detail view. Sunofriend first
reconstructs a deterministic MIDI file from the verified immutable Clip v1
document, then renders that reconstruction through a pinned local dry
FluidSynth/SoundFont policy. The preview is a role-neutral listening proxy, not
an original instrument match, GarageBand patch choice or claim of musical
accuracy.

The renderer and SoundFont are optional until the user asks for the preview.
MIDI-only browse and reconstruction remain lightweight. Derived MIDI and WAV
files live in a separate rebuildable content-addressed cache, never in the
read-only library. A failed or unavailable preview must leave browsing and
MIDI reconstruction usable.

### Deterministic MIDI reconstruction

The MIDI download is a deterministic Standard MIDI File reconstruction of the
Clip v1 musical document under its recorded timing contract. It is **not an
original-MIDI byte copy**. Clip v1 preserves canonical musical content and
lineage, not every byte, ordering choice or unsupported event from an earlier
SMF file. The page and handoff must say this plainly.

The reconstruction must be repeatable from the same Clip object and export
policy, carry a content hash, state the GarageBand BPM and leave the immutable
Clip unchanged. This differs from Phase 5 Pack Composer, whose numbered MIDI
payloads are exact copies of the selected candidate files.

### Zero-effect contract

Browse, search, paging, detail, lineage navigation, preview and reconstruction
must all declare and enforce zero effects:

| State or artifact | Effect |
| --- | --- |
| Clip library/database/object files | No write, migration, tag edit, import or version creation |
| Clip notes, chords, timing and metadata | No mutation or transform |
| Workbench musical decisions | No selection, promotion or outcome change |
| Pack Composer basket | No revision or inclusion change |
| Source candidates and accepted GarageBand pack | No mutation |
| Review or community feedback | No event or preference record |
| Network | Loopback only; no upload or submission |
| Derived preview/download cache | Rebuildable artifacts only, outside the library |

Every request must remain behind the Workbench per-launch token. Public
browser projections are path-free. The service must recheck acceptance, pack
and library identity and fail closed if any immutable evidence changes during
the launch.

## Deliberately absent from Increment 6.0

This first slice does **not** add:

- key, BPM, tuning, downbeat or register transformations;
- Clip imports, tag edits, deletes, writes or new versions from Workbench;
- piano-roll or phrase editing;
- automatic candidate selection or ranking from library use;
- dragging a Clip into a current arrangement;
- Instrument Bundle attachment or patch selection;
- source-audio sampling; or
- hybrid MIDI construction.

In particular, no Clip may be merged with a current candidate merely because
it was opened, auditioned or downloaded. Explicit hybrids remain Phase 5.3
gated. The accepted Phase 5.9 result is not evidence for blind phrase choice or
source lineage.

## Increment sequence

The completed baseline and each later increment have their own reversible
contract and tests:

1. **Safe Clip entry (complete):** gated read-only browser, lineage, neutral
   audition and deterministic reconstruction described above.
2. **Explicit reuse plan (complete):** let a
   user place a chosen immutable Clip into a proposed arrangement without
   mutating the source Clip or project decisions.
3. **Reversible transforms:** expose existing key, BPM, tuning and downbeat
   operations as new Clip versions with a minimal audit diff and range/alignment
   warnings.
4. **Phrase and note correction:** add bounded piano-roll/phrase edits with the
   original candidate and exact edit diff retained.
5. **Explicit hybrids:** only after both Phase 5.3 gates pass, construct a new
   candidate from user-named sources and ranges. Never infer a hybrid from
   agreement or popularity.
6. **Instrument attachment:** attach an explicitly eligible, hash-pinned
   instrument recommendation or Bundle without presenting it as a portable
   patch identity.
7. **Mashup preparation:** align confirmed downbeats, key, BPM and timing while
   retaining every source and transformation recipe for GarageBand handoff.

Phase 7 remains the boundary for cross-DAW expansion and separately consented
community learning. Increments 6.0 and 6.1 add neither telemetry nor a public
service.

## Completed acceptance criteria for Increment 6.0

Tests and the local browser exercise showed that:

1. the three launch flags are all-or-none and changed/mismatched acceptance or
   pack evidence fails before library access;
2. the library has independent SQLite and application write guards and is not
   initialized or migrated;
3. all Clip objects and lineage relationships are hash-verified and the
   browser receives no path/private provenance;
4. search, detail and lineage are bounded and useful without editing JSON;
5. a MIDI download repeats byte-for-byte from one Clip/policy while remaining
   clearly labelled as reconstruction rather than original-byte export;
6. a neutral preview, when dependencies are available, is derived from that
   same MIDI and cannot modify the library;
7. ordinary Workbench is unchanged when the flags are absent; and
8. every library, Clip, project, decision, basket, feedback and submission
   effect remains false.

Those code, security, packaging and real-browser checks passed together.
Increment 6.0 is **complete**; this does not mark broader Phase 6 complete.

## Increment 6.1: explicit Clip reuse proposal

Increment 6.1 adds an optional **Proposed reuse plan** beside the existing
read-only **Browse Clips** view. It lets the user place one exact immutable
Clip at a named bar and beat, see the proposed order and compatibility facts,
and remove a placement explicitly. It does not put the Clip into the current
selected arrangement or change any Phase 5 state.

The proposal requires a fourth explicit launch flag in addition to all three
Increment 6.0 gate inputs:

```bash
sunofriend workbench "/path/to/project" \
  --candidate-root "/path/to/results" \
  --catalog "/path/to/workbench-catalog.json" \
  --state-dir "/path/to/workbench-state" \
  --clip-library "/path/to/existing-clip-library" \
  --phase6-acceptance "/path/to/passed-phase5-acceptance-result.json" \
  --phase6-pack "/path/to/the-exact-accepted-garageband-pack.zip" \
  --enable-clip-reuse-plan \
  --open
```

Without `--enable-clip-reuse-plan`, the completed Increment 6.0 read-only
behaviour is unchanged and no proposal route or proposal database is exposed.
The new flag is invalid unless the existing library, accepted result and exact
pack flags are all present.

### Proposal and grid contract

Each placement pins the exact `clip_id` and immutable Clip object SHA-256. The
server derives title, role, timing, note/chord counts and instrument metadata
from that verified object; the browser cannot substitute those values. The
same Clip may appear more than once only through several explicit placements.
There is no hidden repeat count and no move operation: moving means removing
one placement and explicitly placing it again.

Version 1 uses a deliberately small planning grid:

- 4/4 planning assumption and 480 ticks per quarter note;
- whole-beat placement only, with `tick_in_beat` fixed to zero; and
- bar 1, beat 1 means the project's recorded-zero planning origin.

That origin is **not** a confirmed musical downbeat. The time signature is
also unconfirmed. Reuse v1 does not apply project downbeat evidence; if the
catalog contains it, the warning reports that it is present but not applied.
These facts remain visible warnings rather than inferred timing evidence.

The plan is bounded to 64 active placements, 512 append-only placement/removal
events, 20,000 notes in any placed Clip, 40,000 active note instances and a
20-minute nominal end at the positive current project BPM. Exceeding a bound
fails before an event is appended.

### Separate durable state and exact restoration

The proposal is an append-only local state plane, separate from Workbench
musical decisions, the Pack Composer basket and the immutable Clip library.
Its owner-only SQLite database is
`STATE_DIR/phase6-reuse/reuse.sqlite3`. It is created lazily by the first
explicit placement or removal; opening the view or reading an empty plan does
not create it.

The plan binding pins the project identity/setup and source hashes, accepted
result and exact pack hashes, complete Clip-library state hash, policy and
planning grid. A restart restores placements only when that whole binding is
unchanged. A different scope starts as a new empty proposal rather than
migrating or silently adapting older placements.

Every change uses the current plan ID, plan hash and revision. If either the
plan or immutable evidence changed, the server rejects the change. The browser
reloads the current proposal once, preserves the user's draft where possible
and does **not** retry the mutation automatically. The user must inspect the
new state and choose whether to submit again.

### Compatibility facts, not transformations

Clip detail and placement rows show server-derived compatibility facts for
the project and Clip key/BPM, stem-locked timing, unconfirmed or explicitly
not-applied downbeat evidence, unconfirmed time signature, overlaps and absent
instrument attachment. These are warnings for
human planning. They do not rank a Clip or apply a key, mode, tempo, tuning,
register, downbeat or timing transformation.

Increment 6.1 adds no arrangement playback, MIDI rendering, export, pack
inclusion, instrument attachment, source sampling, piano-roll edit, hybrid or
current-arrangement mutation. The existing Increment 6.0 Clip detail audition
and reconstruction remain separate read-only operations. Browse/search,
proposal reads and compatibility display remain feedback-free. A placement or
removal changes only this proposal state; library/Clip content, MIDI,
transforms, Workbench decisions, current arrangement, pack basket, feedback
and submission remain unchanged.

### Implementation map

- `sunofriend.workbench_reuse.WorkbenchClipReuseStore` owns the guarded,
  append-only proposal database and exact-scope restoration.
- `sunofriend.workbench_reuse.WorkbenchClipReuseService` validates evidence,
  Clip identity, bounds, compatibility facts and optimistic concurrency.
- `sunofriend.workbench_server` exposes token-protected
  `GET /api/clip-reuse-plan` and `POST /api/clip-reuse-action` only for an
  explicitly enabled launch.
- `workbench_clips.js` keeps **Browse Clips** and **Proposed reuse plan** as
  understandable sibling modes and submits only explicit place/remove actions.
- the optional Developer Inspector maps `clip_reuse.read` and
  `clip_reuse.change`, showing a bounded path-free state summary rather than
  request bodies or private evidence.

### Verified completion

The completion exercise used the real accepted Lidl Phase 5 project and its
73-Clip, 51-lineage library. In the local Workbench it placed the exact
immutable bass Clip at bar 3, beat 2, restored revision 1 after a process
restart, removed that placement explicitly, then restored the empty active
revision 2 after another restart. The append-only database retained the
`place,remove` history while the active proposal became empty.

The exercise also verified:

- lazy owner-only proposal storage (`0700` directory and `0600` SQLite file);
- exact Clip/object pinning and exact-scope restore status;
- visible BPM, stem-locked timing, downbeat/meter planning limits and absent
  instrument warnings;
- fixed JSON failures for malformed, oversized and extreme numeric actions,
  plus append-only trigger, corrupt-row and two-server stale-action checks;
- a path-free Developer Inspector summary with the reuse change identified as
  the only durable operation;
- no browser console errors; and
- byte-identical Workbench decision database, Clip catalog, Clip objects and
  accepted GarageBand Pack before and after place/remove.

Focused contract, UI, security, Developer Inspector and adjacent Clip tests
passed together with the full project suite. Increment 6.1 is **complete**;
this still does not complete broader Phase 6 or enable transforms, playback,
export, instrument attachment, current-arrangement construction or hybrids.
