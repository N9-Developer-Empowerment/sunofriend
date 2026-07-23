# Phase 6: Creative Arrangement and Reusable MIDI

Status on 23 July 2026: **entry gate passed; Increment 6.0, the first
read-only Clip Library slice, is complete; Increment 6.1, the explicit Clip
reuse proposal, is complete; Increment 6.2a, the first bounded immutable
key/BPM transform workflow, is complete; Increment 6.3a, bounded immutable
pitch correction, is complete; and Increment 6.3b, bounded immutable
attack-velocity correction, is complete without changing the published pitch
contract. Increment 6.3c, bounded exact note removal, and Increment 6.3d,
bounded existing-note onset shift, and Increment 6.3e, bounded existing-note
end/duration correction, are complete.** No listening-quality claim is made
for the 6.3d or 6.3e engineering close-outs.
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
3. **Reversible transforms (6.2a complete):** same-mode key and explicit
   musical/stem-locked BPM operations now create reviewed immutable child
   versions with a minimal audit diff and range/alignment warnings. Mode
   remapping, tuning and downbeat remain separate later slices.
4. **Phrase and note correction (6.3a–e complete):** bounded, explicitly
   selected pitch, attack-velocity, exact
   note-removal, existing-note onset or note-end patches retain the parent and
   exact diff. Attack velocity, removal and both timing shifts are available
   for drums. Insertion and continuous expression follow under
   separate contracts.
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

## Increment 6.2a: reviewed immutable key/BPM alternatives

Increment 6.2a exposes a deliberately narrow wrapper around Sunofriend's
existing Clip-level transforms. A user reviews one exact, temporary projection
and may then explicitly append one immutable child Clip. The parent remains an
available alternative; “undo” means choosing the parent, not mutating the
child back into it.

The transform capability requires the three Increment 6.0 gate inputs and a
fourth explicit flag:

```bash
sunofriend workbench "/absolute/path/to/stems" \
  --candidate-root "/absolute/path/to/results" \
  --catalog "/absolute/path/to/workbench-catalog.json" \
  --state-dir "/absolute/path/to/workbench-state" \
  --clip-library "/absolute/path/to/existing-clip-library" \
  --phase6-acceptance "/absolute/path/to/passed-phase5-acceptance-result.json" \
  --phase6-pack "/absolute/path/to/exact-accepted-garageband-pack.zip" \
  --enable-clip-transforms \
  --open
```

`--enable-clip-transforms` and `--enable-clip-reuse-plan` are mutually
exclusive in this first slice. Reuse v1 intentionally binds the complete Clip
library state, while a successful transform intentionally changes that state.
The safe workflow is therefore:

1. start transform mode, review and create the required child versions;
2. stop that Workbench; and
3. restart with `--enable-clip-reuse-plan` and explicitly place the exact
   child Clip wanted.

An older proposal remains stored under its old complete-library binding. It is
not migrated, rewritten or made to point at a new child.

### Review, then create

The browser supplies only the exact parent Clip/object/library pins and one
typed transform request. `POST /api/clip-transform-projection` revalidates the
accepted pack and whole library, performs the transformation in memory and
returns a path-free, bounded before/after audit. Its effects are all false and
it writes no object or catalog row.

Editing any control invalidates that projection. Creation stays unavailable
until the current draft has been projected. `POST /api/clip-transform-action`
must contain the same parent/object/library/transform pins plus the exact
projection SHA-256. The server recomputes and verifies the request and performs
an optimistic catalog compare-and-swap. A fresh request appends exactly one
child; an exact retry returns that already-existing child as an idempotent
replay and appends nothing. Either result identifies the exact parent and child
Clip/object hashes, lineage, revision, operation and before/after library
states.

Any drift is a conflict. The browser reloads current detail once, retains only
the user's draft, clears the old projection and never retries the write. A
fresh successful write is the sole durable effect: it adds one immutable Clip
version. An idempotent replay has all effects false. Neither outcome mutates
its parent, chooses or ranks a candidate, alters a reuse placement, changes
Workbench decisions or the current arrangement, adds a Pack Composer item,
attaches an instrument, records feedback or submits data.

The capability disables both review and create at the accepted 10,000-Clip
inventory boundary. The browser explains that limit and keeps inspection,
audition and deterministic export available for existing Clips.

### Supported musical contracts

One action performs one operation, so changing both key and BPM requires two
visible lineage children.

**Same-mode key change** uses a mechanical semitone transposition to a target
tonic while retaining the source major/minor mode. The user must choose
nearest, upward or downward interval direction and inspect the exact semitone
shift and resulting pitch range. Key changes for drum-family Clips are
rejected because their MIDI pitches identify drum sounds. Major-to-minor or
minor-to-major remapping remains deferred; that is a creative scale/chord
rewrite, not the same reversible mechanical operation.

**BPM change** requires one of two timing meanings:

- `musical` retains bar/beat positions and groove while scaling elapsed time,
  warp seconds and microtiming. This genuinely speeds up or slows down the
  MIDI, so it no longer aligns with untreated source audio; or
- `stem_locked` retains source seconds and recalculates beat positions against
  a straight target GarageBand tempo. It preserves audio alignment and is not
  an audible speed-up relative to that untreated audio.

The target must be finite, from 20 to 400 BPM and from one quarter to four
times the source BPM. A no-op, out-of-range MIDI pitch, Clip over 20,000 notes
or output over 20 minutes is rejected before persistence.

### Why tuning and downbeat remain absent

The existing raw-MIDI concert-pitch cleanup uses pitch-bend and RPN events.
Clip v1 does not retain those complete Standard MIDI File events, so presenting
that operation as an immutable Clip transform would lose evidence. Similarly,
the existing downbeat anchor shifts the complete MIDI event stream, while the
current accepted downbeat is reviewer-observation-only and Clip v1 contains a
canonical note/chord document rather than the whole original stream. Both need
a separately defined Clip representation and hash-pinned evidence contract.

Increment 6.2a therefore does not expose mode remapping, arbitrary semitone
editing, tuning, downbeat, register, piano-roll, batch or combined transforms.
It also creates no audio preview by itself. After a child exists, its ordinary
Clip detail view can use the existing deterministic reconstruction and neutral
audition; that audition still records no preference.

### Completion evidence

The real loopback exercise used a copy of the accepted Lidl Clip library. The
171-note B-major bass at `118.99992463338107` BPM first produced a reviewed
musical-timing 125 BPM child, then a reviewed +1-semitone C-major child. Exactly
two rows/objects were added to the copy; the original 10-Clip library and all
ten inherited rows/objects were unchanged. Both exact retries were zero-effect
idempotent replays. Restart recovered all three lineage versions, public API
documents remained path-free and the final deterministic MIDI repeated at
SHA-256 `42eabbb41cd484d104d67080833710bb240b0d73d817e8af93aa95217b35b502`.

Adversarial tests also prove that an insert trigger cannot mutate the parent
before commit, capacity cannot create a durable 10,001st Clip, identical
cross-server requests become create-plus-replay and different cross-server
requests become create-plus-conflict. The complete project suite passed with
910 tests. Increment 6.2a is **complete**; broader Phase 6 remains in progress.

## Increment 6.3a: bounded immutable pitch correction

Increment 6.3a addresses a common failure that can be recognised more easily
than it can be described: a transcription contains the right phrase rhythm but
one or more notes sound wrong or sit in the wrong octave. It does not ask an
algorithm to decide what the melody ought to be. The user identifies exact
existing notes in a short visual window and supplies their replacement MIDI
pitches.

This is a separate controlled-write launch:

```bash
sunofriend workbench "/absolute/path/to/stems" \
  --candidate-root "/absolute/path/to/results" \
  --catalog "/absolute/path/to/workbench-catalog.json" \
  --state-dir "/absolute/path/to/workbench-state" \
  --clip-library "/absolute/path/to/existing-clip-library" \
  --phase6-acceptance "/absolute/path/to/passed-phase5-acceptance-result.json" \
  --phase6-pack "/absolute/path/to/exact-accepted-garageband-pack.zip" \
  --enable-clip-corrections \
  --open
```

Correction, key/BPM transform and reuse-proposal modes are mutually exclusive.
Each intentionally pins or changes the complete Clip library in a different
way. Create any corrected children first, stop the process, then restart under
reuse mode to place an exact chosen child.

### Fixed-grid phrase window

The browser requests a half-open window using integer Standard MIDI File ticks
at 480 ticks per quarter note. Membership therefore matches the note-on times
GarageBand receives under the Clip's existing automatic export timing,
including stem-locked source-second mapping and musical microtiming. The window
does not quantise or move a note.

One window is limited to 32 quarter-note beats and 15 rendered seconds. It may
show at most 512 intersecting notes, of which no more than 256 may start in the
window and therefore be editable. Notes crossing into the window are visible
locked context. Chord context is capped at 64 events. A dense phrase fails with
an instruction to choose a narrower window; it is never silently truncated.

Each note reference binds:

- the exact parent object SHA-256;
- the note's canonical index in that immutable parent; and
- every `ClipNote` field, including beat and source-second timing,
  microtiming, velocity, release velocity and articulation.

The index distinguishes byte-identical duplicate notes. The hash detects a
stale or fabricated browser reference without changing the Clip v1 schema.

### Pitch-patch contract

One child may replace the pitch of 1 to 64 uniquely referenced notes. Each
target is an integer MIDI pitch from 0 to 127 and no note may move by more than
24 semitones in this first slice. Nothing is preselected and a patch containing
only no-ops is rejected. Drum-family Clips are excluded because their MIDI
note numbers identify kit pieces rather than a pitched melody.

Pitch changes preserve the exact parent values for start, duration, source
start/end, both microtiming fields, velocity, release velocity and
articulation. The tempo map, key signature, chords, time signature, instrument,
provenance, tags and every unaffected note remain unchanged. Key and chord
relationships in the review are advisory evidence only; Sunofriend does not
snap a chromatic note to a scale or chord.

Before projection, the service calculates the exact 480-TPQ intervals produced
by the Clip's existing export timing. It rejects a patch that would newly
introduce a duplicate same-pitch onset or an overlapping same-channel,
same-pitch lifetime, because Standard MIDI has no independent identity for
those simultaneous note instances. Pre-existing ambiguity is not silently
normalised into the correction.

The same boundary rejects a parent that the deterministic Clip-to-MIDI writer
cannot encode. Both notes and chords are capped at 20,000; note, chord and
musical-tempo event ticks must fit the Standard MIDI File four-byte
variable-length maximum (`0x0fffffff`); tempo values must fit the three-byte
microseconds-per-quarter field; time-signature bytes and UTF-8 title/chord meta
payloads must also be encodable. The maximum safe tick has a write/read
round-trip test. This is validation of preserved data, not quantisation or
repair.

### Review, creation and restart audit

`POST /api/clip-note-correction-window` returns the bounded path-free visual
evidence and a hash of that exact window. `POST
/api/clip-note-correction-projection` accepts only the parent/object/library
pins, exact window/hash and canonical pitch patch. It recomputes everything in
memory and returns the projected deterministic child, every before/after pitch,
semitone delta, advisory harmony facts, warnings and unchanged-field
invariants. All projection effects are false.

Editing a note or window invalidates the projection. `POST
/api/clip-note-correction-action` additionally requires `action: create` and
the exact projection SHA-256. A fresh action appends one child whose ID is
derived from the complete correction intent. An exact retry returns the same
existing child as an idempotent replay and appends nothing. A stale or
different library state is a conflict; the browser may reload detail/window
once but never retries a write automatically.

The recognized correction recipe retains a bounded canonical before/after
audit. Clip detail validates it against the exact retained parent and exposes a
path-free correction summary after restart. Arbitrary or legacy transform
parameters remain hidden. Reversibility means inspecting or choosing the
retained parent, not mutating the child backwards.

A fresh create changes only the Clip library by adding that one corrected
child. It does not select or rank a process, update the current arrangement or
reuse proposal, alter the Pack Composer, attach an instrument, record
feedback, submit data or build a hybrid. Existing deterministic MIDI and dry
neutral audition can be prepared after explicitly opening either parent or
child; listening still records no preference.

### Verified completion

The completion exercise used a fresh copy of the accepted Lidl library. The
source keys Clip contained 1,727 notes; its first eight beats exposed 22
editable notes at 480 TPQ. A deliberate test patch changed MIDI pitch 59 to 61
and created revision 2,
`sf-correction-daa1ce4dca1cd99823af371ffd16ffad9f3a5df387eaaa167245b4daec1767e6`,
with object SHA-256
`99b894f9aa78fb745d05c194a2cffbce0b6db705b8f8f392c68178d472b42caf`.
The copied library grew from 12 to 13 Clips while the original library and
parent bytes remained unchanged. An exact retry returned `replayed` with all
effects false; restart re-derived the same one-note diff; public correction,
detail and artifact responses were path-free; and two deterministic MIDI
reconstructions matched at SHA-256
`ce1edbc85f44b5c37cdb0576c89ef5cd2eee74afe7c9ee6f904ca248f866d4a8`.
The complete repository suite passed with 943 tests. It includes the maximum
SMF boundary round-trip, forged-recipe/restart cases, browser contracts and a
deterministic two-server lazy-reuse initialization check.

## Increment 6.3b: bounded immutable attack velocity

Increment 6.3b keeps the existing correction opt-in, routes and optimistic
sole-child append, but adds a separately discriminated
`attack_velocity_patch`. The four-field pitch window request, pitch schemas,
hashes and `correct_note_pitches` recipes remain frozen. A velocity window adds
only `correction_kind: attack_velocity_patch`; its preview/create patch carries
1 to 64 unique `{note_ref, target_velocity}` changes, where every value is an
exact integer from 1 through 127. The retained operation is
`correct_note_attack_velocities`.

One draft and one immutable child contain exactly one correction kind. Pitch
and attack velocity can be chained as two visible lineage revisions, but are
never merged implicitly. Velocity works on pitched and drum-family Clips. It
changes only the Note On attack byte: pitch, onset, duration, source timing,
microtiming, release velocity, articulation, instrument and metadata remain
exact. The review is numeric and zero-write; creation does not audition,
select, place, rank or export the child.

Attack velocity is not dB, track volume, CC7/CC11 expression, aftertouch or a
promise of perceived loudness. A GarageBand patch can use it for loudness,
brightness, attack character or sample-layer selection. Sunofriend therefore
does not infer a target from source energy, normalise dynamics or claim that a
higher value is better.

Standard MIDI normalisation collapses multiple source notes that export to the
same channel, onset tick and pitch. Those exact or quantised duplicate Note On
events remain visible but carry `duplicate-export-note-on` and are not
velocity-editable, because no one-to-one audible edit can be guaranteed.
Restart validation rebuilds the exact child and confirms that normalized MIDI
event topology, pitch, timing, duration and release velocity are unchanged and
only the named unique Note On velocities differ.

The Workbench does not trust a response merely because it contains a hash. It
checks the kind-specific schema and operation, request/window/library pins,
exact correction and one-to-one diff, deterministic child identity and the
complete effect map before showing a reviewed or created result. Missing rows
are never rebuilt from the browser draft. Applying the already-current draft
value changes no state and preserves any valid review.

The real completion exercise copied the accepted 12-Clip Lidl library and
used its channel-9 Snare Clip. In a five-note exact window, one pitch-38 Note
On changed from velocity 101 to 89. The copy gained exactly child
`sf-correction-bd3c06f634a12c5920d87bc901b7f618b46751766f807eb5a77f398862e307d6`
with object SHA-256
`a836e97bedce9f31b094f373121b602112054da8cd29b3366d90a54957425cb7`.
The source library and copied parent remained byte-identical, normalized MIDI
changed only that event velocity, exact replay had zero effects, restart
restored the same −12 diff and deterministic MIDI repeated at SHA-256
`f8570c9af8636e3cfeb1605082616a3e1e72f0bdd546b764baf055bca9abbc4c`.
The complete repository suite passed with 955 tests; the single warning is the
existing `resampy`/`pkg_resources` deprecation notice.

## Increment 6.3c: bounded exact note removal (complete)

Increment 6.3c retains the same explicit `--enable-clip-corrections` launch,
routes, bounded phrase window and sole-child compare-and-swap. It adds one
isolated policy in `workbench_deletion.py`, with frozen correction kind
`note_delete_patch` and retained recipe operation `delete_clip_notes`. The
published pitch-v1 request, hashes and `correct_note_pitches` recipe, plus every
6.3b attack-velocity schema and recipe, remain unchanged.

The user-facing choice is **Remove unwanted/extra MIDI notes**. It is available
for pitched and drum-family Clips and accepts 1–64 unique exact existing note
references, while requiring at least one note to remain. Nothing is selected or
marked automatically. Clicking or keyboard-navigating to a note changes focus
only; the listener must explicitly **Mark for removal**, then **Review temporary
note removal**, then **Create immutable corrected Clip**. Sunofriend does not
infer that any event is noise, bleed, leakage or musically wrong.

Eligibility and patch validation must prove a stronger topology invariant than
a simple note-count delta: normalized child MIDI equals normalized parent MIDI
minus exactly the named intervals. Every surviving note retains its complete
pitch, onset, duration, source-second timing, microtiming, attack and release
velocity and articulation. Beat, export and source horizons also remain exact.
A note is visible but not removable when it belongs to a duplicate or
cascade-dependent export group, when its removal would move any horizon, or
when it is the only remaining note. Those cases fail before projection or
creation rather than silently changing another audible interval.

One draft, projection, recipe and immutable child contain exactly one of
`pitch_patch`, `attack_velocity_patch` or `note_delete_patch`. The operations
may be chained only as separately visible lineage revisions. Projection is
zero-write. A fresh create appends one deterministic child and sets only the
`library_mutated`, `child_clip_created`, `correction_applied`,
`note_count_changed` and `note_deleted` effects;
an exact retry and restart audit have zero effects. The parent, every survivor,
chords, tempo, key, time signature, instrument, provenance, project decisions,
current arrangement, reuse proposal and GarageBand Pack remain unchanged.
There is no draft audition, ranking, preference, selection, placement or export
effect; the created child can be inspected and auditioned explicitly afterward.

The completion exercise used a fresh copy of the accepted Lidl library at
`work/ai-bakeoff/lidl-phase6-deletion-smoke-v2`. Both source and copy began at
12 Clips. From channel-9 Snare parent
`0718458e900dbcdf7dff7332c77808054dfaadb6c517d2c22d7b967a28f50826`
(object
`65b140afecb84099abbdf9880ee4597d8eeb7c6caf5d470e62213654ee857ae5`),
the explicit patch removed one pitch-38, velocity-46 note at ticks
140487–140573, beat 292.68125, duration 0.17916666666667425. The source stayed
at 12 Clips, while the copied library grew to 13 and child
`sf-correction-6914357fcfbca9f597fe09ca8912fda3516554226bbbdab1507295f9b309576c`
(object
`622f9e88616f3b9450a126e5b671aae557e1b2ac8e27f9de3103828f61e5f20b`)
contained 248 notes instead of 249. Normalized MIDI also changed exactly
249→248; beat, export-event and source horizons remained respectively
442.7395833333333 beats, 212515 ticks and 223.23018339583334 seconds. Replay
returned every effect false, restart restored a path-free summary, and two
child reconstructions matched at SHA-256
`1e3e20d607c62b7b6c06d210b9f3fa90c1f126166aadcf86d82d870d83f5535c`.
The focused integrated correction suite passed 81 tests, the final independent
audit passed 49 and the complete repository suite passed 970 tests. The single
warning is the existing `resampy`/`pkg_resources` deprecation notice. Increment
6.3c is complete; broader Phase 6 remains in progress.

## Increment 6.3d: bounded existing-note onset shift

Increment 6.3d keeps the same explicit correction launch, bounded phrase
window, immutable-parent and sole-child compare-and-swap. It adds one isolated
policy in `workbench_onset.py` with correction kind
`note_onset_shift_patch`, retained recipe operation `shift_note_onsets` and its
own window/preview/result/summary v1 schemas. The overall correction capability
remains v2. Generic `timing: false` is deliberately unchanged; a client must
check the explicit onset kind plus `maximum_onset_delta_ticks: 480` before
offering this operation. Published pitch, attack-velocity and deletion
schemas, hashes and recipes remain frozen.

The user-facing choice is **Move existing note earlier or later**. It is
available for pitched and drum-family Clips. One patch contains 1–64 unique
exact existing note references and one exact integer `target_start_tick` for
each. The target must differ from the source, the absolute delta may not exceed
480 ticks, and both the complete source and target intervals must fit the
loaded half-open phrase window. Focus, navigation and typing are browser-only;
the user must explicitly apply a value, review the projection and create the
immutable child.

The emitted Note On and matching Note Off move by the same tick delta. Exact
normalized MIDI duration ticks, pitch, attack/release velocity, articulation,
note count and all unaffected notes remain unchanged. The operation neither
infers a preferred onset nor snaps, quantises, repairs theory, copies a
repeated phrase or uses chord evidence to choose one.

Timing coordinates are reconciled under the Clip's existing export mode:

- In `musical` mode, `start_beat` moves by `delta / 480`, `duration_beats` and
  both microtiming values stay exact, and source start/end seconds are
  recomputed through the retained tempo map.
- In `stem_locked` mode, both microtiming fields must be exactly zero. Source
  start/end move by `delta * 60 / (export_bpm * 480)`, source duration stays
  exact, and beat start/duration are derived from those shifted source times.

Both paths must round-trip to the exact requested Note On and Note Off ticks.
Negative or overlong MIDI ticks, changed beat/export/source horizons and any
reversed time fail closed.

The public window uses exactly four eligibility reasons:

- `context-note-outside-window` for a crossing context note whose full source
  interval is not available to edit;
- `duplicate-export-note-on` where source objects collapse to one Note On;
- `normalized-lifetime-dependent` where normalization or a same-pitch
  predecessor makes this interval dependent on another source note; and
- `unsupported-stem-locked-microtiming` for the deliberately unsupported first
  stem-locked microtiming case.

Even an editable source is rejected when its target would escape the window,
overlap or duplicate a same-channel/same-pitch lifetime, cause a normalization
cascade, cross a global horizon or exceed the MIDI encoding bounds. These are
identity and topology checks, not musical rankings.

Projection has every effect false. A fresh create may set only
`library_mutated`, `child_clip_created`, `correction_applied`,
`note_onset_changed` and `note_timing_changed`. An exact replay appends nothing
and every effect is false. Restart validates the recognized recipe against the
exact retained parent and exposes only the bounded path-free summary. The
child is not auditioned, ranked, selected, placed, exported or added to a Pack
automatically.

### Completed 6.3d evidence

The completion exercise used a fresh copy of the accepted 12-Clip Lidl library
at `work/ai-bakeoff/lidl-phase6-onset-smoke-v1`. The source stayed at 12 Clips
and the copy grew to 13, while the copied parent remained byte-identical.
Parent Keys Clip
`a6112b69031a233a54531128dca4925f32d5b3b32ce5552daaa6393d0138d8aa`
(object
`d37975c915e790e290650cf5b48e316c19318c28bd1a50c3de342e889180356a`)
produced child
`sf-correction-495e77ba31528090cc979465459d50acf9ad8f4e36f8a783e9f30398703d5727`
(object
`e70a297a01be3a086f5fa05e8dabb47975e6b634dd1adfc4e8c17565524932a2`).
Both Clips contain 1,727 notes. One channel-1 pitch-66 interval moved from
442–873 to 472–903, a +30-tick/+31.512625-ms shift with its 431-tick duration
unchanged. Beat, export-event and source horizons remained
462.6458333333333 beats, 222070 ticks and 233.26695445833332 seconds.

Fresh creation set exactly `library_mutated`, `child_clip_created`,
`correction_applied`, `note_onset_changed` and `note_timing_changed`; exact
replay and restart had every effect false. Parent and deterministic child MIDI
SHA-256 values were
`e741334f8dfc1421850618d088b382a5fc051fc1fada4797ac742a1dcd201036`
and
`20b1298550568bb51cdb98c4d8e342a4ac27e22b2cd58f5e03f48f062cad7d9b`.
The focused integrated correction suite passed 101 tests. The adversarial
audit passed 17 onset-specific and 82 broader correction/server/UI tests. The
complete repository suite passed 990 tests in 282.58 seconds with the one
existing third-party `resampy`/`pkg_resources` deprecation warning. This
completes the contract and deterministic evidence only; no human preference or
musical-quality result was recorded.

## Increment 6.3e: bounded existing-note end/duration correction

Increment 6.3e keeps the same explicit correction launch and immutable-child
boundary. Its isolated `workbench_duration.py` policy uses correction kind
`note_end_shift_patch`, retained operation `shift_note_ends`, and these public
schemas:

- `sunofriend.workbench-clip-note-end-window.v1`;
- `sunofriend.workbench-clip-note-end-preview.v1`;
- `sunofriend.workbench-clip-note-end-result.v1`; and
- `sunofriend.workbench-clip-note-end-summary.v1`.

The user-facing choice is **Change existing note length (MIDI Note Off)**.
One patch contains 1–64 unique exact existing pitched or drum note references
and integer `target_end_tick` values. Each target must differ by a non-zero
delta within ±480 ticks, remain at least one tick after the fixed Note On, and
keep both source and target intervals wholly inside the loaded half-open
window. Focus and typing are inspection only: the listener must explicitly
Apply the target, Review the zero-write projection and Create the immutable
child.

Only the emitted Note Off and corresponding duration coordinates move. Note
On, pitch, attack/release velocity, articulation, note count and every
unaffected note remain exact. The same four row block reasons apply as for
onset shift: `context-note-outside-window`, `duplicate-export-note-on`,
`normalized-lifetime-dependent` and
`unsupported-stem-locked-microtiming`. Even an editable row fails closed if a
target crosses the next same-channel/same-pitch onset, changes another
normalized lifetime, escapes the window/MIDI bound or moves the global beat,
export-event or source horizon.

The dual-time update is explicit:

- `musical` mode changes `duration_beats` by `delta / 480`, keeps the onset and
  both microtiming values exact, and recomputes source end through the retained
  tempo map;
- `stem_locked` mode requires both microtiming values to be zero, changes
  source end by `delta * 60 / (export_bpm * 480)` and derives the new beat
  duration.

Both paths round-trip to the requested integer Note Off. The capability stays
at v2 with generic `timing: false`; clients must feature-test
`note_end_shift_patch`, `maximum_note_end_delta_ticks: 480` and
`minimum_note_duration_ticks: 1`. Preview is all false. Fresh creation may set
only `library_mutated`, `child_clip_created`, `correction_applied`,
`note_duration_changed` and `note_timing_changed`; exact replay and restart are
all false. The operation does not infer legato, phrasing, quantisation,
correctness or musical quality. The browser exposes a restored note-end summary
only after validating exact child, lineage, timing, diff and all-false effect
evidence; malformed restart state fails closed.

### Completed 6.3e evidence

The ignored real smoke at
`work/ai-bakeoff/lidl-phase6-duration-smoke-v1` has acceptance-report SHA-256
`d0141814026c434c4702a9c7dcd00466fd6502921bb5e0fa1b437657d675bb77`.
The accepted 12-Clip source and copied parent stayed unchanged, and only the
fresh copy grew from 12 to 13. Parent Keys Clip
`a6112b69031a233a54531128dca4925f32d5b3b32ce5552daaa6393d0138d8aa`
(object
`d37975c915e790e290650cf5b48e316c19318c28bd1a50c3de342e889180356a`)
produced child
`sf-correction-067bbbfc65e112ba175da84648f2b74f40b5cb5137eabb5f91ff28f4af9f03f6`
(object
`14fee0a6ac7dbc29043199e30041adc93c59eda34fccd8a6a9a15d972846281f`).
Both contain 1,727 notes. One channel-1 pitch-66 interval changed from
442–873 to 442–903: +30 ticks/+31.512625 ms and duration 431→461 ticks.
Beat, export-event and source horizons stayed 462.6458333333333 beats, 222070
ticks and 233.26695445833332 seconds. Parent MIDI SHA-256 was
`e741334f8dfc1421850618d088b382a5fc051fc1fada4797ac742a1dcd201036`;
child and deterministic repeat both were
`27d5be64a4e992548c6a58139f8a7fb677e3d7f4cefc55ea4e2fc163b74fa918`.
The focused integrated correction/UI suite passed 133 tests, the real smoke
passed and the complete repository suite passed 1009 tests with the one
existing `resampy`/`pkg_resources` deprecation warning. This is deterministic
engineering evidence, not a human preference or musical-quality result.

### Deliberately deferred after 6.3e

Note insertion, release velocity, continuous expression, split/merge, phrase
replacement, repetition propagation, source waveform/F0 or hummed-guide
correction, quantisation, automatic theory repair and hybrids remain absent.
Missing-note insertion needs a new note-identity and source-evidence contract.

Release velocity is not the next slice because every audited local Clip
library currently carries zero release velocities, while GarageBand and its
patches vary in whether Note Off velocity is audible. That leaves no useful
local golden for verifying value changes. These operations must arrive as
small reviewable increments rather than being hidden inside pitch, attack
velocity, deletion, onset or duration actions.
