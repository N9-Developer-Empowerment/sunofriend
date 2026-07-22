# Sunofriend Workbench

The Workbench is the local Phase 5 interface for deciding which MIDI result is
musically useful. It does not run a model or upload a song. Its explicit
preview/arrangement actions create content-addressed local audition proxies;
discovered MIDI remains byte-for-byte unchanged.

Sunofriend's distinctive purpose is to compare a small, understandable family
of results from different analytical and AI processes. It does not present one
transcription model as the answer. Specialist conversion, tracker consensus,
conditioned AI, source-supported repair and reviewed alternatives may each be
useful for a different role or phrase. Workbench keeps that provenance and
uncertainty visible, records an explicit human choice and never infers a winner
from a score, label, audition count or displayed default.

The current interface supplies per-stem source/candidate playback, persistent
decisions, neutral preview rendering, selected-arrangement audition and an
explicit GarageBand pack composer. Phase 5.4 now supplies both a read-only
per-stem source/MIDI comparison timeline and a full-song selected-arrangement
explorer, plus an explicit bridge from verified disputed lead-vocal ranges to
the existing phrase-review page. Phase 5.5 now adds a default Project Overview,
a safe restart/retry path and explicit decision/privacy barriers that keep an
inconclusive review or legacy path-like role out of a GarageBand export. It
also adds Decoded Stem Comparison v1: a precise 0.5–15 second per-stem source
versus requested candidate-preview loop scheduled on one decoded Web Audio
clock. Phase 5.6 adds a bounded decoded selected-arrangement loop with four
canonical, server-derived groups. Phase 5.7 adds fixed-window long-song
visualization with explicit recovery and a minimal exact full-song chunk
transport for those same canonical groups. Arbitrary custom mute/solo/gain
playback remains an explicitly coarse compatibility path.
Phase 5.8 explains independently verified execution provenance. Phase 5.9 now
adds the exact-pack interactive tutorial, required 10/10 comprehension quiz and
two-check local acceptance resolver. That review passed on 22 July 2026, so the
first explicitly gated read-only Phase 6 Clip Library increment is complete.
The separate explicit Clip reuse proposal is also complete. Broader Phase 6
creative arrangement remains in progress.
The optional **Developer Inspector** adds a read-only application operation and
state explorer for developers who want to understand those contracts before
reviewing or extending them. See the
[technical tour](TECHNICAL_TOUR.md) for the implementation path and guided
usage.
The arrangement explorer shows every unique project source stem beside only
the active explicit main and optional MIDI choices, with temporary visibility,
mute, solo and level controls. It does not infer an offset: every source and
MIDI file begins at its recorded zero, so equal displayed seconds do not by
themselves prove source/MIDI alignment. The user-composed GarageBand basket is
persistent local export state, separate from both musical decisions and the
temporary audition mixer.

## Developer Inspector

Add `--developer-inspector` to the normal `sunofriend workbench` command to
make the **Developer Inspector** view available in the same token-protected
loopback session. It presents the path-free
`sunofriend.workbench-developer-snapshot.v1` projection: application operation
steps, append-only events, derived current state, the separate basket revision
and temporary-state boundaries.

The Inspector is optional and read-only. Opening it, selecting an operation or
scrubbing the event sequence does not append feedback, save a decision, change
the basket, render audio, run a model, build a pack or alter MIDI. Its trace is
bounded local diagnostic state and is not included in review or acceptance
exports. It is an application-specific learning tool, not a Python line
debugger, evaluator, shell, SQL editor or filesystem browser.

Follow the worked invocation, architecture map, state-fold example and safe
extension checklist in [Sunofriend technical tour](TECHNICAL_TOUR.md).

## Project overview and restart boundary

Workbench now opens on a path-free `sunofriend.workbench-home.v1` projection.
It derives its counts, stem statuses and one recommended next workflow step only from
the current catalog plus explicit saved state. It can direct the listener to an
undecided stem, a stem with no active selection, the full arrangement or the
pack composer, or truthfully report that no MIDI part is selected. It never
uses model scores, process labels, preview activity or
technical metrics to rank a candidate, and navigation records no feedback.

Routing is deterministic: first visit the first candidate-bearing stem with no
candidate decision or explicit outcome; then revisit any non-terminal decided
stem that still has no active main/optional part; then hear selected parts that
lack `full_mix` context; otherwise compose the pack. When no active
main/optional part remains, explicit **None are usable** and **I cannot tell**
outcomes are terminal for resume routing, so they do not create an endless
revisit loop. They are also no-selection barriers: older main/optional events
remain in the private history but become inactive and cannot enter the selected
arrangement, pack plan, ZIP or proxy MIDI. A later explicit main or optional
choice clears the barrier and activates only that candidate; it does not revive
older optional selections. Reject and needs-correction decisions do not clear a
terminal barrier. If they are the only results, Overview
truthfully reports that no MIDI part was selected. If pack composition is next,
the page lazily checks the current plan and offers **Resume saved pack** only
when the saved basket still matches it.

Each stem row distinguishes **compare candidates**, **no active selection**,
**no usable result recorded**, **listening inconclusive**, **hear in
arrangement**, **ready for pack** and **no candidates**. The sidebar
uses the more precise phrase **decisions recorded** rather than treating every
event as a completed review. Keyboard focus follows a resume action to the
actual workflow heading, and connection or saved-pack-status failures are
announced with a retry that changes no musical or export state.
The home projection excludes paths, private notes, process labels, quality
metrics and problem tags. Initial project-load and lazy pack-status failures
are retryable; both keep the current decisions intact and append no event.
New free-form role tags and explicit-catalog roles must be one-line musical
descriptions of at most 80 characters and cannot contain a local path. Legacy
POSIX, home-relative, relative, Windows-drive or UNC path-like roles are not
rewritten in private SQLite history, but path-free browser/public/handoff
projections use **custom role**. That shared boundary covers Project Overview,
browser state, contribution preview, public catalog inspection, timelines,
pack labels and archive names, and generated proxy-MIDI track names. The full
private review export deliberately retains the raw role and remains private.

The URL hash restores the current view and stem after a browser reload. SQLite
decisions, Project Overview state and the separate GarageBand basket survive
browser and server restarts. Audition state does not: prepared Web Audio,
decoded stream/chunk state, playhead, loop, viewport/zoom, lane visibility,
mute, solo and level start fresh on reload and remain outside review history,
cache identity and export selection. A compatible last verified visualization
may remain marked stale after an in-tab refresh failure, but it is not durable
reload state. A two-launch loopback regression verifies that the same
decisions and non-default basket return under a new launch token without any
GET request appending feedback or changing the basket revision. Primary candidate audio preloads metadata; advanced
alternatives use `preload="none"` until the listener asks for them.

## Result Explorer direction

The interface is an evolution of this Workbench, not a Mirelo clone and
not a replacement for GarageBand. It adopts approachable interaction ideas—a
single transport, visible source and MIDI events, clear track controls and a
direct export path—while preserving Sunofriend's multi-process evidence model.

The implemented explorer is deliberately smaller than the eventual Studio:

- `sunofriend.workbench-timeline.v1` is a path-free, canonical-hash-pinned
  projection of already catalogued artifacts;
- the ordinary request loads only the at-most-three primary candidates, while
  an advanced lane is decoded only after an explicit visual opt-in;
- classic and WAVE_EXTENSIBLE integer-PCM WAV sources provide a bounded min/max
  waveform, including common 24-bit stems; unsupported or invalid containers
  remain audible through their existing player and show an explicit
  unavailable waveform state;
- each MIDI candidate retains separate track title, channel, program, pitch,
  velocity, beat and embedded-tempo seconds evidence;
- note rectangles represent note-on/off only—sustain, controllers, pitch bend
  and later program changes are not rendered;
- candidates above 20,000 notes or 8 MiB remain available as original MIDI but
  use an explicit unavailable visual-lane state, while the moving playhead is
  kept separate from the static note drawing;
- advanced candidate requests return a verified source reference and reuse the
  base waveform already in the page rather than rebuilding it for every lane;
- one request accepts at most 12 candidate lanes, while the ordinary view
  starts with no more than three primary candidates; and
- visibility and click-to-seek actions do not create audition, preference,
  selection, ranking, repair or edit events.

The full-song view uses
`sunofriend.workbench-arrangement-timeline.v1`, another path-free,
canonical-hash-pinned projection. It is derived server-side from the current
explicit selection rather than a browser-supplied candidate list. Byte-identical
source audio shares one visibly labelled lane, but selected MIDI is never
deduplicated. The projection is capped at 24 distinct source lanes, 24 selected
MIDI lanes and 40,000 rendered MIDI notes in total; a lane that exceeds the
remaining visual budget stays visible as unavailable evidence rather than
silently disappearing.

Phase 5.7 renders both projections in a fixed-width viewport rather than a
song-width canvas. **Fit song**, **4×** and **16×**, earlier/later paging,
PageUp/PageDown and **Centre on playhead** change only the current view. Only
waveform bins and note events that overlap the visible window (plus a small
overscan) are painted. Canvas CSS size, device-pixel ratio and arrangement
backing-pixel budget are capped: width is 480–1,600 CSS pixels, DPR is at most
2 and the arrangement targets at most 12,000,000 backing pixels. A viewport is
never shorter than 0.5 seconds; the UI paints 0.25 seconds of overscan and the
helper rejects overscan above 5 seconds. Per-stem and arrangement waveforms use
720 and 320 bins by default, while the API accepts only 64–4,096. The browser
retains no more than four per-stem timeline documents and persists none to
local/session storage. This is paint culling, not payload
virtualisation: the browser still downloads and parses the complete
server-bounded timeline JSON and builds full indexes before drawing.

New visualization requests abort older ones and stale responses cannot replace
the current selection. If a refresh fails and the last verified projection
still matches that selection, Workbench leaves it visible, marks it stale and
offers **Retry visual evidence**. With no compatible projection it reports an
explicit unavailable state, while audio, decisions and export remain usable.
Canvas context loss reports a recovery state and restoration redraws the view.
No hidden coarse visual projection replaces missing or oversized evidence.

The interface continues to call candidates A/B/C until technical details are
opened. The visual lanes make differences easier to locate; they do not say
which process is musically correct.

### Link a disputed lead-vocal range to an existing phrase review

The completed lead-only S0/M1/M3 hybrid report can guide listening without
becoming a new transcription or score. This link is explicit-only; Workbench
does not search the filesystem or guess which report belongs to a lead-vocal
stem. Add all three exact report MIDI files to one explicit catalog stem, then
add:

```json
"phrase_review_link": {
  "hybrid_report": "/absolute/path/to/hybrid-report.json",
  "phrase_review_manifest": "/absolute/path/to/phrase_review.json"
}
```

Supply roots containing those files through `--candidate-root`. Catalog
creation fails closed unless the report is diagnostic-only, its source matches
the stem, S0/M1/M3 map uniquely to the catalogued MIDI bytes, its ranked counts
and phrase geometry agree, and the phrase-review manifest plus referenced page
audio still match their hashes. The public project projection contains no
paths.

When valid, **Disputed phrase ranges** appears directly under the role
timeline. The count is a listening locator, not an accuracy or preference
score. **Set compare loop** changes only the temporary loop and playhead; it
does not start audio. **Open existing phrase review** opens the matching
zero-based `#phrase-N` anchor on the already generated
Basic Pitch/GAME-boundary/combined page, with guide-assisted included only when
present. That page does not compare S0/M1/M3 directly and cannot choose a
Workbench candidate or create hybrid MIDI.

The private review page may embed local paths. It is therefore served only on
loopback behind a random per-launch capability URL. Browser policy blocks
connection APIs, forms, automatic playback, popups and top-level navigation;
the page retains only the scripts, alert dialogs and user-triggered reviewed-
JSON download needed by its existing workflow. Only its hash-pinned HTML and
semantically allow-listed source, MIDI-only and overlay WAV auditions are
reachable; its manifest, correction JSON, MIDI, evaluations and unrelated
sibling files are not served. Opening, looping and following the link create no
SQLite event, contribution data or pack item.

Two linked views avoid confusing alternatives with simultaneous parts:

- **Arrangement view** shows every unique source stem plus one explicit main
  choice per role and chosen optional layers on a shared full-song
  waveform/piano-roll timeline. Visibility, mute, solo and level affect this
  browser-tab audition only. Source-stems, selected-MIDI, hybrid and main-MIDI
  presets are temporary starting points; manual changes become an unsaved
  custom audition.
- **Compare-role view** keeps one source stem visible while the user
  switches among at most three primary process candidates and opens additional
  diagnostic alternatives only when needed.

The implemented Pack Composer is separate from the main/optional musical
decision. It shows exactly which unchanged selected MIDI, dry proxy pair and
explicitly opted-in source stems will enter a GarageBand ZIP. The existing
source-audio-free exact-MIDI-plus-proxy handoff remains its safe default.
Unselected alternatives and Instrument Bundles remain deferred until the
catalog has an explicit reviewed eligibility contract for them. Direct note
editing, phrase recombination and Clip-library composition belong to the later
creative arrangement phase.
When the active selection is empty, the composer explains why no MIDI is
eligible and provides a direct return to Project Overview; it cannot build an
empty ZIP.

## Start with automatic discovery

The project directory contains the original top-level stems. Keep candidate
roots narrow enough that they contain outputs for this song only:

```bash
sunofriend workbench "/absolute/path/to/Song-B minor-113bpm-440hz" \
  --candidate-root "/absolute/path/to/song/baseline-output" \
  --candidate-root "/absolute/path/to/song/ai-alternatives" \
  --open
```

Run `--inspect` first to see the path-free catalog without starting a server.
Filename-based discovery infers roles, deduplicates byte-identical MIDI, shows
at most three normal candidates and keeps `possible`, `uncertain` or `rejected`
variants under advanced diagnostics.

Run `sunofriend doctor --require preview` before asking the page to render
missing previews or an arrangement. The normal SoundFont lookup uses
`SUNOFRIEND_SF2` and then the installed GeneralUser-GS bank. Pin another local
bank for this session when needed:

```bash
sunofriend workbench "/absolute/path/to/stems" \
  --candidate-root "/absolute/path/to/results" \
  --soundfont "/absolute/path/to/GM-bank.sf2" \
  --open
```

## Use an explicit catalog when roles are ambiguous

Paths are resolved relative to the catalog file unless absolute. Source audio
must remain under the project directory. MIDI and previews must remain under
the project or one of the explicitly supplied candidate roots.

```json
{
  "schema": "sunofriend.workbench-catalog.v1",
  "stems": [
    {
      "source": "private-stems/Song-keys-B minor-113bpm-440hz.wav",
      "label": "Keys",
      "role": "melody + accompaniment",
      "review_question": "Which MIDI preserves the recognisable theme without mixing in the accompaniment?",
      "listening_focus": [
        "recognisable melody",
        "missing or extra notes",
        "accompaniment leakage",
        "timing and note duration"
      ],
      "candidates": [
        {
          "midi": "results/baseline/keys_listened.mid",
          "preview": "results/baseline/keys_listened.preview.wav",
          "label": "Closest to detected notes",
          "description": "Conservative specialist transcription",
          "process": "sunofriend-specialist"
        },
        {
          "midi": "results/muscriptor/candidate.expression.mid",
          "preview": "results/muscriptor/candidate.expression.preview.wav",
          "label": "Role-conditioned AI transcription",
          "description": "MuScriptor challenger rendered with the same sound",
          "process": "muscriptor-conditioned",
          "warnings": ["Review note density and mixed accompaniment"]
        }
      ]
    }
  ]
}
```

```bash
sunofriend workbench "/absolute/path/to/private-stems" \
  --candidate-root "/absolute/path/to/results" \
  --catalog "/absolute/path/to/workbench-catalog.json" \
  --open
```

`review_question` and `listening_focus` are optional plain-language prompts for
one declared listening task. They are shown above the synchronized players but
do not preselect, promote, rank or score a candidate. Use separate catalog stem
rows when the same source excerpt needs distinct questions such as bass body
and pluck. Their canonical hash is part of that row's review identity and every
saved event. Editing the question or focus therefore starts a fresh row instead
of silently restoring choices made under a different task. The complete local
export retains the declared context for audit; the contribution preview omits
the prompt text.

## What a decision means

- **Use as main** identifies the current principal MIDI for that stem. A later
  main choice supersedes it in current state; the old event remains in history.
- **Keep optional** retains a useful layer without making it the main part.
- **Needs correction** records problem tags and an optional private note.
- **Reject** records that this candidate should not be used for the project.
- **Equivalent** can coexist with an active selection.
- **None are usable** and **I cannot tell** retain the audit history but
  deactivate all earlier main/optional choices for that stem. Only a later
  explicit main/optional decision reopens selection; it activates that one
  candidate and does not resurrect choices from before the barrier.

The complete local export contains paths, event history and private listening
notes. Treat it as private project data. The separately displayed contribution
preview excludes audio, MIDI files, absolute paths, notes, dwell time and play
counts. Path-like legacy roles are projected as **custom role** there as well.
Phase 5.0 has no contribution or upload endpoint.

## Understand AI transcription diagnostics

When a candidate MIDI sits inside a completed immutable `ai-transcribe` run,
automatic discovery verifies its request, run, candidate, MIDI, source,
checkpoint and model-config hashes. The candidate card then shows path-free
evidence including:

- effective model size, batch, beam, CFG and five-second chunk policy;
- requested and detected broad instrument labels;
- note count, density, polyphony, short/duplicate-note ratios and warnings;
- activity around local five-second boundaries; and
- execution mode/cache status and pipeline elapsed time and real-time factor.

These values explain how a result was made; they do not select the most musical
one. Ordinary label leakage stays auditionable because a useful line may be in
the wrong broad family. Severe decoder bursts and zero-note results are marked
diagnostic-only: their original files remain available, but preview rendering
and **Use as main**/**Keep optional** are disabled. **Needs correction** and
**Reject** remain available so the failure can still be recorded.

For a verified application-cache hit, the card explicitly says that no AI
worker, model load or inference ran for this output. Its elapsed time and
real-time factor describe the current parent pipeline—verified lookup, copying
and post-processing—not inference. The copied
`muscriptor.performance.json` still belongs to the original fresh miss. A hit
remains subject to the same quality and zero-note gates and is never promoted
automatically.

For a completed bounded reused-model session, automatic discovery revalidates
the whole closed session before displaying it. That includes parent/run
membership and hashes, the exact request template, one model load, serial
sequence, worker response, performance evidence and candidate/MIDI identity.
Request one is labelled **resident but not warm** because no earlier
transcription exists. Only request two and later are labelled **reused-model
warm**. The card also states that the application cache was disabled.

All five displayed execution states—fresh subprocess, exact-result cache miss,
verified cache hit, first session request and reused-model warm request—are
provenance, not musical votes. Workbench consumes the completed evidence and
does not enable a cache, start a session, launch a model or treat repeated
execution as independent agreement. Missing or changed session evidence fails
closed instead of falling back to an unverified execution label.

Use `sunofriend ai-matrix` before the Workbench when several completed lanes
need one reproducible comparison. The report adds per-instrument quality,
requested/detected-label differences, label stability, chunk-boundary activity
and same-pitch/onset overlap against role-conditioned lanes. It mutates neither
raw candidate JSON nor MIDI and never declares a winner.

```bash
sunofriend ai-matrix \
  --lane "M0=/absolute/path/to/full mix unconditioned/RUN" \
  --lane "M1=/absolute/path/to/full mix discovered labels/RUN" \
  --lane "M2=/absolute/path/to/full mix known labels/RUN" \
  --lane "M3-bass=/absolute/path/to/isolated bass/RUN" \
  --out "/absolute/path/to/fresh matrix.json"
```

All lanes in one report must share the backend, checkpoint, model config,
worker hash, model/runtime version and execution settings. The current
Workbench does not import `matrix.json`; it reads each adjacent completed run
directly, while the matrix is the durable audit and cross-lane comparison.
M4 lanes have a stricter contract: every lane uses the same source audio,
excerpt and positive BPM and requests exactly one distinct role. The matrix's
M4 overlap section reports same-pitch/onset matches and requested/off-role note
counts. High overlap can expose role collapse or relabelling, but is not an
accuracy score and does not prove that either pass isolated a source.

If a completed pass contains a useful reported label plus off-role labels,
`sunofriend ai-label-split RUN --label LABEL --out-dir FRESH_OUTPUT` writes an
exact source-index JSON partition, deterministic requested/complement MIDI
auditions and a byte-identical full-candidate control. The operation does not
run a model. Private byte-identical source-request/source-candidate controls
let Workbench bind every partition row back to the verified raw candidate; keep
those local because the request can contain absolute model/audio paths. The
JSON accounts for each raw event exactly; MIDI necessarily uses integer pitches
and ticks and may collapse duplicate onsets or truncate an ambiguous same-pitch
overlap. Those effects are measured in the report rather than hidden. This is
model-label partitioning, not audio separation or instrument identification.
Workbench cross-checks the report, partition, private provenance controls, full
MIDI control, render contract and decoded MIDI; a severe decoder burst or zero-note
requested label is blocked, while a non-empty safe split remains
review-required and has no automatic-promotion path.

## Compare with one consistent renderer

Do not confuse the Workbench neutral-preview cache with the opt-in MuScriptor
application cache. The preview cache stores only deterministic FluidSynth
audition proxies for already discovered MIDI. Workbench does not run
MuScriptor or look up/populate its raw-result cache; it only verifies and
displays cache provenance from a completed adjacent `ai-transcribe` run. The
operating-system file cache is uncontrolled and is neither of these mechanisms.
On a verified hit the card says that no model ran and treats elapsed time as
pipeline timing. `miss-stored` is the single published fresh control expected
by `ai-cache-benchmark`. A concurrent losing producer can instead be
`miss-verified-existing`: it ran inference and verified the winner's raw
candidate as identical, but it is not a benchmark control and Workbench does
not interpret it as a cache hit.

Set a short recognisable 0.5–15 second range and choose **Prepare precise
loop**. The normal request includes the source and up to three primary MIDI
candidates. An advanced alternative is included only after its explicit
**Include in precise loop** opt-in, and no more than six candidates can enter
one comparison. If a card has only an old preview or none, Workbench prepares
the same role-neutral render used by **Render neutral preview**. The cached
proxy uses:

- the same local SoundFont and FluidSynth settings;
- one stable GM program for the stem's role;
- the source MIDI's note times in seconds; and
- the project BPM in the proxy file.

The original MIDI hash does not change. Neutral means renderer-consistent, not
peak-normalised: note velocity and density remain audible. Every included
candidate must use the current SoundFont hash and neutral-renderer policy; a
mixed or stale renderer set fails closed rather than becoming an unfair
comparison. When a preview must be rendered, Workbench copies the verified
candidate MIDI and SoundFont through single open handles into owner-only
temporary snapshots and renders only from those bytes. It rechecks the
originals and deletes the snapshots before publishing the preview. Neutral
preview rendering is limited to MIDI no longer than 20 minutes.

Workbench then verifies the source and neutral-preview hashes and copies each
through a single open handle into an owner-only, hash-and-size-verified audio
snapshot. Cropping reads only those snapshots, which prevents a file
replace/restore race from changing the decoded bytes; the snapshots are deleted
before the content-addressed PCM clips are published. The source and every
included candidate switch on one Web Audio clock and retain one absolute loop
playhead. Every input starts at recorded zero; no offset or source/MIDI
alignment is inferred. Preparing, playing, switching, seeking, pausing and
stopping do not append an audition event, change a selection, rank a process or
mutate MIDI.

When a requested end is later than the available source or preview audio,
Workbench adds generated silence to that track's end and reports the padded
duration in a separate warning that remains visible while that prepared loop
is current. Do not judge disclosed padding as missing MIDI or a failed
transcription.

The explicitly labelled **Compatibility fallback** retains the older media
players for a browser or file that cannot complete the decoded path. Those
players share a position in seconds but are not sample-accurate. Their audition
controls are also feedback- and event-free; use the decoded panel for a precise
comparison and the fallback only when required.

On **Hear selected arrangement**, set the same kind of 0.5–15 second range and
choose **Prepare precise arrangement loop**. Workbench builds
`sunofriend.workbench-arrangement-selection.v1` from current saved state. It
deduplicates byte-identical project sources in catalog order, retains every
active main/optional MIDI lane separately and defines the exact source-only,
selected-MIDI, hybrid and main-only groups. The POST request carries only that
manifest hash and the time bounds; the browser cannot supply candidate IDs,
roles, gains or arbitrary track membership.

Missing MIDI sounds use the current saved path-free role and the same pinned
SoundFont/neutral-render policy. The server checks the manifest before work,
builds without holding the decision-state lock, then checks the manifest again
before registering private media URLs. A choice changed in another tab returns
a conflict instead of publishing an obsolete mix. Every group source is
started and every outgoing source is stopped at one shared Web Audio time. A
failed switch leaves the previous group playing. Empty groups are disabled.
Preset clicks, Pause, Stop and navigation invalidate older pending audio-clock
resumes, so a delayed click cannot restart or replace a newer action. Preparing
uses an abortable request and stale manifest/DOM guards; cancelling it creates
no partial browser transport. Starting any ordinary audio player pauses the
precise transport and announces that ownership change. If precise preparation
created a previously missing neutral MIDI sound, re-open the arrangement view
before using the already-rendered coarse panel so it can refresh that lane.
The tracks retain unity gain and are not level matched or limited, so a dense
hybrid can clip and this panel is not the standalone blind promotion test.

## Arrangement playback contracts

Keep these three paths distinct. Decoded Stem Comparison v1 above is the
separate Phase 5.5 per-stem comparison; the arrangement view provides:

1. **Precise short arrangement loop (Phase 5.6).** A 0.5–15 second decoded
   excerpt of one canonical source-only, selected-MIDI, hybrid or main-only
   roster, scheduled on one Web Audio clock.
2. **Precise full-song preset (Phase 5.7).** The same four canonical rosters as
   exact integer-frame, non-looping chunks on one Web Audio clock. Only the
   current and next chunks stay decoded.
3. **Coarse full-song/custom mixer.** Separate HTML media elements with
   arbitrary visibility, mute, solo and 0–100 attenuation. They share elapsed
   seconds but are not sample accurate.

For precise full-song playback the browser POSTs exactly the current selection
manifest hash and one preset name to `/api/decoded-arrangement-stream`; it
cannot supply track IDs, roles, groups or gains. The resulting immutable
`sunofriend.workbench-decoded-arrangement-stream.v1` plan snapshots verified
private source and neutral-preview bytes. The first source supplies the anchor
sample rate, the longest source supplies the end and every track starts at its
recorded zero. Input-rate conversion uses deterministic nearest integer frames
with ties-to-even. Shorter tracks are padded with disclosed silence.
All POST bodies are capped at 64 KiB.

The browser requests each exact
`sunofriend.workbench-decoded-arrangement-chunk.v1` by stream hash and chunk
index. Tracks remain separate PCM16 and play at unity gain without matching or
limiting, so a dense hybrid can clip. Up to two chunks are primed before Ready. The
next decoded chunk is scheduled at the exact boundary and an old chunk is
released. If the required next chunk is not ready, playback stops truthfully
at the last verified boundary. A late completion enables explicit Play; a
missing or failed chunk requires Retry. Neither action auto-restarts playback.
Seeking likewise waits in a paused state. No failure silently starts the coarse
mixer: choosing that fallback is always manual. If the remembered preset is
empty, the first available canonical preset is selected automatically; this
keeps source-only projects ready to prepare.
Changing preset creates a new immutable stream and resets its temporary
playhead.

The precise full-song path accepts at most 24 tracks, a 20-minute longest
source, and 2 GiB of aggregate verified input across every catalog source
needed for the song clock plus relevant selected MIDI, SoundFont and neutral
previews. Source and preview audio must be
mono/stereo at 8–96 kHz. A chunk is at most five seconds and can be shortened
to remain below 32 MiB aggregate PCM16 output and 192 MiB projected memory for
two decoded float chunks; one stream has at most 480 chunks. Chunk artifacts
share the rebuildable 32-entry/256 MiB decoded cache with short comparisons.
One server launch retains no more than 16 active stream-plan capabilities and
768 generated-media capability records. If a rebuildable capability URL has
been evicted it returns 404; preparing again is recovery, not loss of a saved
decision. No limit permits silent track omission or coarse fallback.

The immutable full-song input snapshots have their own owner-only disk LRU:
eight streams or 2 GiB, separate from the decoded chunk cache. The stream being
prepared is always retained, even if it alone is larger. Prepare/reprepare
performs complete hash verification. During that server process, up to eight
verified streams may use file identity and stat signatures for sequential
chunks, avoiding a full-song rehash on every chunk. Any identity/stat drift
invalidates the fast path and triggers full verification; altered or missing
evidence fails closed.

## Build a stricter blind MIDI A/B outside the Workbench

Use the standalone `midi-ab-review` package when a candidate decision needs
hidden identities, exact source-time short loops and verified candidate-level
matching. It does not read or change Workbench state:

```bash
sunofriend doctor --require preview

sunofriend midi-ab-review \
  "/absolute/path/to/source.wav" \
  "/absolute/path/to/first.mid" \
  "/absolute/path/to/second.mid" \
  --interval 0.0 5.0 "opening attacks and missing notes" \
  --interval 10.0 15.0 "recognisable contour and extra notes" \
  --bpm 119 \
  --midi-time-at-source-start 0 \
  --gm-program 4 \
  --soundfont "/absolute/path/to/pinned-bank.sf2" \
  --question "Which candidate is more musically useful?" \
  --out-dir "/absolute/fresh/path/midi-ab-review"
```

Repeat `--interval START END "FOCUS"` for each comparison passage. Intervals
are interpreted in reference-source seconds, must not overlap, must stay
inside the WAV and must each last 0.5–15 seconds. `--gm-program` is zero-based
and defaults to 4. `--midi-time-at-source-start` is required and pins the one
candidate-MIDI time corresponding to reference-WAV time zero. It must land on
a source sample frame; use `0` only when the WAV and both MIDI files have the
same excerpt origin. Both candidates use the supplied origin and no alignment
offset is inferred. The SoundFont and question are optional; normal local
SoundFont discovery is used when no SF2 is supplied. The output directory must
not already exist.

Both original MIDI files remain unchanged. Private neutral proxies preserve
their note pitch, velocity and source-time placement within one MIDI tick, then
use the same pinned dry FluidSynth executable, SF2, zero-based GM program,
sample rate and render gain. Every source/A/B excerpt uses the same rounded
source-frame bounds under the explicit common origin. For each interval, the
louder candidate alone is attenuated to the quieter candidate's fixed-window
sample RMS. The source
reference is not a candidate and is not level-matched. No amplification,
limiting, compression, EQ, time shifting or stretching is applied. Both
candidate windows must be at least -60 dBFS RMS. This is not LUFS, true-peak or
perceived-loudness matching.

Open `midi_ab_review.html`, but leave the separate
`midi_ab_answer_key.json` closed until the blind review is exported. Listen to
the source, Candidate A and Candidate B for every loop, tick all three heard
checkboxes, select A, B, equivalent, neither or cannot tell, add an optional
private note, mark all choices reviewed and export
`midi_ab_review.reviewed.json`. If an embedded browser blocks a local `file://`
download, use Safari, Chrome or Firefox for this page; no server or upload is
required. The audio elements auto-loop, and their shared playhead is scoped to
one review unit rather than leaking between passages. A
secret random nonce assigns A/B per loop; the public seed contains only its
commitment and the private nonce/mappings stay in the answer key. Then reveal
and verify the hidden mapping with a fresh result path and the original
unchanged package directory:

```bash
sunofriend midi-ab-resolve \
  "/absolute/path/to/midi_ab_review.reviewed.json" \
  --package-dir "/absolute/fresh/path/midi-ab-review" \
  --out "/absolute/fresh/path/midi-ab-result.json"
```

The resolver compares the reviewed export with the original seed, answer key,
manifest, audio and inputs. Only status/reviewed count, heard flags, choices and
notes may differ. Changed timing, focus or geometry, swapped A/B slots and
cross-unit candidate moves are rejected. A normal browser JSON round trip can
rewrite a finite number's representation—for example, `0.0` becomes `0`.
Exactly equal numeric values remain valid; booleans, strings, different values
and structural changes do not. The result is listening evidence only: it does
not edit either MIDI, save a Workbench choice, promote a preset or change a
default.

The Phase 5.2 private beam package has now been generated under ignored
`work/ai-bakeoff/lidl-phase5-beam-rms-review-v4/`, with commitment
`b5e3556f70560c86cbe79fbcc4bb7d9a8362c67824beed203bffa0675162dd10`.
Its three exact 48 kHz windows are 0.20–3.50, 3.50–7.50 and 11.60–15.00
seconds, using common origin `0`, GeneralUser-GS program 4, SoundFont hash
`9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe`
and FluidSynth 2.5.6 hash
`93589cfaf73a5aaaaf37dd313be4d815fb2ced8f0e8ae641b0e1d0026e546911`.
All final A/B PCM RMS pairs match to six decimals and are unclipped. The
resolved review judged the 0.20–3.50 and 11.60–15.00 second loops equivalent
and marginally preferred beam 1 on 3.50–7.50 seconds. Beam 2 won no loop. The
result reports zero MIDI edits, source mutations, selection changes,
promotions and default changes; beam 1 therefore remains the default. The
standalone page still uses per-unit shared-second media-element switching;
Workbench now supplies a separate decoded, sample-scheduled per-stem path. The
standalone blind package remains the stricter level-matched promotion gate.

The separate Phase 5.2 batch-size comparison does not add a Workbench choice.
Batch 1 and batch 2 produced identical canonical note payload, base MIDI,
expression MIDI and every auditionable MIDI on the private golden, so there is
no musical A/B to review. Its read-only comparator reports zero mutations,
selections and promotions; batch 1 remains the execution default after the
batch-2 arm was slower and used more memory in the bounded CPU observation.

The first Phase 5.3 `hybrid-report` remains diagnostic upstream evidence. It
checks the exact lead source, unresolved phrase geometry and existing S0/M1/M3
evidence, then records phrase-level and cross-phrase matches, boundary and
octave disputes, lane-only notes, duplicates and raw source support. Its report
also states that M1's same-song derivation and M3's unsupplied original-MIDI
payload are not verified by this v1 command. With a verified explicit
`phrase_review_link`, Workbench now imports only a path-free disputed-range
projection for loop and navigation shortcuts. It still does not rank or apply
the report or create candidate MIDI. Blind S0/M1/M3 phrase choice and explicit
hybrid construction remain future work before a challenger can enter the
normal result space.

Catalog hashes are not trusted only at startup. Source, MIDI and generated
media are checked again before serving, rendering, arranging or copying into a
handoff; the pinned SoundFont is also rechecked before reuse. If any file
changes during the session, the action stops with an integrity error and the
Workbench must be restarted against a fresh catalog.

Automatic discovery resolves every MIDI, preview and top-level source path and
rejects a symlink that escapes the named project/candidate roots. This prevents
the tokenised loopback media route from becoming a general local-file server.

## Hear the chosen arrangement

The arrangement contains only the active latest **Use as main** choice and any
explicit **Keep optional** choices. Rejected, needs-correction, superseded and
unreviewed candidates are excluded. All drum choices are combined into one GM
drum proxy; pitched selections receive separate tracks and role-neutral GM
programs. Confirming or changing a row after listening records a `full_mix`
decision context.

The **Selected arrangement explorer** above that proxy has a different job. It
draws the project's unique source waveforms and each unchanged selected MIDI
as separate lanes. Candidate letters remain the same as in the corresponding
compare-role page. **Source stems**, **Selected MIDI**, **Hybrid** and **Main
MIDI only** presets change audition state only; show, mute, solo, level, loop,
zoom and playhead changes are held in JavaScript memory and reset when the page
reloads or the audible selection changes. They do not append a Workbench event,
change a choice, alter the overlap gate or enter the GarageBand handoff.
The fixed-window view offers Fit song, 4× and 16× plus paging and centring. It
culls drawing outside the viewport, but the complete bounded arrangement JSON
is still downloaded, parsed and indexed.

Live MIDI layers use renderer-consistent neutral previews. When one is absent,
use **Prepare selected MIDI sounds locally**; Workbench does not silently
substitute an existing unnormalised preview. The source stems and neutral MIDI
previews are not level matched, so the hybrid mix is a creative listening aid,
not fair comparison evidence. **Prepare precise arrangement loop** supplies the
Phase 5.6 bounded section; **Prepare full-song preset** supplies the
Phase 5.7 chunked canonical transport. Both use server-owned source-only,
selected-MIDI, hybrid and main-only memberships. They appear before the
explicitly labelled **Coarse full-song/custom mixer**. That coarse mixer still
uses multiple browser media elements that share displayed seconds but are not
sample-accurate. Pressing its Play button or changing a coarse audio preset,
mute, solo or gain stops either precise transport rather than pretending those
settings were applied there. Timeline visibility remains display-only and does
not take over audio.
The separately prepared dry GM proxy remains the reproducible control and
downloadable convenience render.

Only the buttons under **Save after listening** append `full_mix` decisions.
Playback and mixer activity never counts as preference, including when the
source-only view is useful before any MIDI has been selected.

The proxy keeps imported note times in seconds and writes the inferred project
BPM. It is an audition aid, not a replacement for the selected originals. A
proxy supports at most 15 simultaneously selected pitched parts; reduce
optional alternatives if that limit is reached.

### Review possible doubled lines

The arrangement remains playable when two selected candidates with the same
candidate-origin source audio appear to contain substantially the same line.
For AI MIDI, candidate origin is the verified run source SHA-256. Non-AI MIDI
without that provenance falls back to the review-stem source SHA-256.
Workbench compares such pairs with a deterministic greedy exact-pitch/onset
heuristic: an onset may match at most once, must have the same MIDI pitch and
must fall within 80 ms. The warning is substantial only when there are at
least eight matches and they cover at least 80% of **each** candidate.

This is deliberately a review diagnostic, not an accuracy score, proof of role
separation or candidate preference. Legitimate doubling, thickening and flams
can trigger it. Workbench never deduplicates or merges the MIDI, changes a
decision or suppresses the arrangement. Listen to the arrangement, then use
its confirmation buttons to save the latest decision for both members of a
substantially overlapping pair in `full_mix` context. A later solo decision on
either candidate means the pair needs full-mix confirmation again.

## Export a GarageBand handoff

For overlap finalisation, an otherwise valid GarageBand handoff is blocked
while a substantially overlapping selected pair lacks that latest `full_mix`
confirmation on both candidates. Arrangement rendering stays available so the
decision can be made by listening. This gate does not alter either MIDI file.

The ZIP is content-addressed and contains:

- numbered, byte-for-byte copies of explicit main/optional MIDI choices;
- `selected-arrangement-proxy.mid` and its dry WAV audition;
- a path-free selection/setup manifest; and
- concise GarageBand import instructions, including the exact BPM to set.

It excludes source-audio files, rejected candidates and unreviewed defaults.
Workbench-generated names, the manifest and the instructions contain no local
paths or private review notes. The authoritative numbered MIDI payloads remain
byte-for-byte unchanged and are not metadata-scrubbed, so they may retain
embedded producer metadata; inspect the ZIP before sharing it. Import the MIDI
files onto separate Software Instrument tracks and choose the final patches in
GarageBand.

## Compose an exact GarageBand pack

Open **Compose GarageBand pack** after making the musical main/optional
choices. The page has three deliberately separate groups:

- **Authoritative selected MIDI** lists only current active main/optional
  choices. Every item is checked by the safe default, but a smaller export
  subset can be chosen without changing the arrangement.
- **Convenience audition** is one checked dry arrangement-proxy MIDI/WAV pair.
  Uncheck it when only the original selected MIDI is needed or when no local
  SoundFont renderer is available.
- **Original source stems** is closed and unchecked by default. Enable the
  separate local source-audio opt-in, then check only stems that may be copied
  into this private pack. Duplicate source bytes appear once with their roles
  retained.

**Reset to safe default** restores all active selected MIDI and the proxy while
removing source audio. **Save pack choices** persists only opaque item IDs and
the explicit source opt-in in a dedicated append-only SQLite table. It does not
append a review decision, alter review completion, enter contribution data or
remember mixer/playback activity. A changed musical selection opens a new safe
basket scope; a solo-to-full-mix reconfirmation can restore the same checked
items but must be saved against the refreshed plan before build.

**Build this exact pack** first saves the visible basket, then sends only its
plan and basket hashes to the loopback server. The server re-derives every
eligible item, rejects stale tabs and unknown or duplicate IDs, retains the
substantial-overlap gate, and reads each included catalog file once before
verifying the exact bytes written into the deterministic ZIP. Source audio
cannot be included without the separate opt-in. The path-free receipt records
BPM, key, tuning, downbeat, checked archive paths and hashes; it excludes local
paths and private notes.
Exact copied MIDI and explicitly opted-in source audio are not metadata-scrubbed
and may retain embedded producer metadata; inspect the ZIP before sharing it.

Pack Composer v1 intentionally excludes rejected, needs-correction,
superseded and unreviewed MIDI. It also does not search the filesystem for SF2,
`.aupreset` or Instrument Bundle files. Those will become eligible only through
a later explicit, hash-pinned catalog contract. The legacy
`sunofriend.workbench-garageband-handoff.v1` endpoint remains unchanged for
existing clients.

## Learn first, then complete the two acceptance checks

Every successfully built exact pack now has an adjacent, hash-pinned
**Guided tutorial, 10-question quiz and acceptance review**. Workbench serves
that page through a frozen loopback capability with `connect-src 'none'` and a
review sandbox. It contains no request, upload, submission or telemetry path.

The page must be completed in this order:

1. Eight interactive tutorial screens explain Sunofriend's multi-process
   result space, human decision boundary, temporary audition state, separate
   export basket, BPM/downbeat distinction, MIDI/instrument distinction,
   privacy policy and Phase 6 boundary.
2. Exactly 10 questions are presented one at a time. Nothing is preselected.
   **Check answer** explains the current answer, the whole quiz can be retried,
   and a 10/10 result is required before the next section unlocks.
3. **Human check 1 of 2 — GarageBand pack** asks for an exact-BPM import,
   expected editable selected files, audible playable patches, correct
   drum/percussion routing where applicable, a listened pickup/downbeat and a
   beginning/middle/end drift check.
4. **Human check 2 of 2 — local usability** begins with explicit confirmation
   that the local project was intentionally chosen and authorised. It then
   checks comparison/choice, understanding of the no-automatic-winner result
   space, arrangement audition, separation of decisions/playback/export and
   exact export plus restart behaviour without JSON editing.
5. The user explicitly downloads the private reviewed JSON. Free-text notes
   are allowed only there and are not copied into the resolved result.

Resolve the reviewed export against the exact ZIP that was actually imported:

```bash
sunofriend garageband-pack-resolve \
  "/absolute/path/to/garageband_pack_acceptance.reviewed.json" \
  "/absolute/path/to/sunofriend-garageband-pack.zip" \
  --out "/absolute/fresh/path/phase5-acceptance-result.json"
```

The resolver independently stream-verifies the ZIP, exact safe member set,
embedded receipt, basket item identities and payload hashes. It rebuilds the
neutral seed from those bytes, rejects changed tutorial/questions/evidence,
recomputes the quiz and checks the two declared outcomes against their item
answers. `passed` requires 10/10 and two all-pass checks; any issue produces
`needs_changes`, even when another item is `cannot_tell`; otherwise
`cannot_tell` produces `incomplete`. The resolver has
zero MIDI, candidate, decision, basket, ranking, default or submission effect.

When Workbench has no catalog-pinned downbeat, a listened downbeat pass is
reported as `reviewer-observation-only`. It is sufficient for this private
human acceptance gate but does not invent exact downbeat metadata. A future
hash-pinned downbeat catalog contract can strengthen that evidence separately.

For an older downloaded pack without the adjacent page, generate the same
fresh package without starting a server:

```bash
sunofriend garageband-pack-review \
  "/absolute/path/to/sunofriend-garageband-pack.zip" \
  --out-dir "/absolute/fresh/path/phase5-pack-review"
```

See [Phase 5 local Studio learning and acceptance](PHASE5_LOCAL_STUDIO_ACCEPTANCE.md)
for the close-out boundary and Phase 6 interpretation.

The resolved path-free close-out records eight tutorial screens complete,
10/10 on the quiz and both six-item human checks passed with no issue or
`cannot_tell` answer. The accepted pack contained five selected MIDI payloads,
the dry arrangement proxy and no source audio. Exact receipt, member and
payload evidence passed; the listened downbeat remains
`reviewer-observation-only`. Resolution changed no MIDI, candidate, decision,
basket, default, feedback or submission state.

## Phase 6 read-only Clip Library (Increment 6.0 complete)

The first Phase 6 slice is an optional Workbench view over one explicit,
existing Clip v1 library. It can browse/search safe Clip metadata, inspect
path-free detail and version lineage, request a dry neutral audition and
download deterministic MIDI reconstructed from the immutable Clip document.

The launch gate is all-or-none. **All three** Phase 6 flags are required:

```bash
sunofriend workbench "/absolute/path/to/stems" \
  --candidate-root "/absolute/path/to/results" \
  --catalog "/absolute/path/to/workbench-catalog.json" \
  --state-dir "/absolute/path/to/workbench-state" \
  --clip-library "/absolute/path/to/existing-clip-library" \
  --phase6-acceptance "/absolute/path/to/passed-phase5-acceptance-result.json" \
  --phase6-pack "/absolute/path/to/exact-accepted-garageband-pack.zip" \
  --open
```

Supplying none leaves ordinary Workbench unchanged. Supplying only one or two
must fail before the library opens. The acceptance result must be `passed`,
must allow read-only Clip entry and must name the exact supplied ZIP. The
existing Clip catalog and every object/lineage are opened and verified
read-only; Workbench must not initialise or migrate the library.

Browse/search and paging are temporary browser state. Public detail excludes
source URIs, source stems, paths, private provenance/notes and transform
parameters. The neutral preview renders the deterministic Clip reconstruction
through a pinned dry local FluidSynth/SoundFont policy into a separate
rebuildable cache. It is a listening proxy, not an original sound, instrument
match or GarageBand patch.

The MIDI download is **not an original-MIDI byte copy**. It is a repeatable SMF
reconstruction of Clip v1's canonical notes, chords, instrument and timing
contract. This is intentionally different from Pack Composer's exact selected
candidate MIDI copies.

Increment 6.0 has no Clip import/write/tag/version operation, transform,
piano-roll, arrangement placement or hybrid. It changes no library object,
Workbench decision, pack basket, candidate, feedback or contribution data.
Hybrid construction remains behind the separate Phase 5.3 blind-choice and
source-lineage gates. The complete scope and acceptance criteria are in
[Phase 6: Creative Arrangement and Reusable
MIDI](PHASE6_CREATIVE_ARRANGEMENT.md).

The completion exercise opened a real library with 73 Clips across 51
lineages. In the browser it verified browse and path-free detail/lineage,
deterministic MIDI download, a dry FluidSynth proxy, a repeated artifact-cache
hit, token-protected path-free byte-range serving and an optional Developer
Inspector trace. Library objects, catalog state, musical decisions, candidates
and the pack basket remained unchanged. This completes only the read-only
entry slice; transforms, piano-roll/phrase editing, arrangement placement and
hybrids remain deferred. Increment 6.1's proposal below is not placement in
the current arrangement.

## Phase 6 explicit Clip reuse proposal (Increment 6.1 complete)

The next bounded slice adds **Proposed reuse plan** beside **Browse Clips**.
It is disabled by default. Enable it only by adding
`--enable-clip-reuse-plan` to the complete Increment 6.0 launch:

```bash
sunofriend workbench "/absolute/path/to/stems" \
  --candidate-root "/absolute/path/to/results" \
  --catalog "/absolute/path/to/workbench-catalog.json" \
  --state-dir "/absolute/path/to/workbench-state" \
  --clip-library "/absolute/path/to/existing-clip-library" \
  --phase6-acceptance "/absolute/path/to/passed-phase5-acceptance-result.json" \
  --phase6-pack "/absolute/path/to/exact-accepted-garageband-pack.zip" \
  --enable-clip-reuse-plan \
  --open
```

In **Browse Clips**, choose an exact Clip and submit a bar/beat target. The
server pins the immutable `clip_id` and object SHA-256 and derives all Clip
metadata itself. In **Proposed reuse plan**, inspect placements in timeline
order or explicitly remove one. Multiple uses of one Clip require multiple
place actions. There is no move or implicit repeat operation; remove then place
again when a target changes.

The v1 plan uses 4/4, 480 ticks per quarter note and whole-beat positions only.
Bar 1/beat 1 is recorded zero for planning, not a confirmed musical downbeat,
and the time signature remains unconfirmed. Reuse v1 does not apply project
downbeat evidence; where it exists, the warning distinguishes present-but-not-
applied evidence from an unconfirmed downbeat. Server-generated warnings
describe key/BPM differences, stem-locked timing, grid limits, overlaps and
missing instrument attachment. Warnings are not scores or preferences and
apply no transformation.

The proposal is a separate append-only state plane. Its owner-only database is
`STATE_DIR/phase6-reuse/reuse.sqlite3`, created lazily by the first explicit
action; merely loading an empty plan creates no file. Exact project/setup,
source, acceptance, pack, library, policy and grid binding restores the plan
after restart. A different binding starts empty.

Every mutation includes the current plan ID, SHA-256 and revision. On a
conflict, Workbench loads the current plan once and does not replay the action
automatically; the user's unfinished target remains available where possible
for an informed resubmit. Limits are 64 active placements, 512 total events,
20,000 notes in one Clip, 40,000 active note instances and a 20-minute nominal
plan end at the positive project BPM.

Place/remove changes only this proposal. It neither edits the Clip/library or
MIDI nor changes Workbench decisions, the current selected arrangement, pack
basket, feedback or submission state. The proposal has no transform,
render/play, export, instrument attachment, source sampling, piano roll or
hybrid operation. Existing Increment 6.0 Clip audition and reconstructed-MIDI
download remain separate read-only tools.

The completed local acceptance exercise placed an exact immutable Lidl bass
Clip at bar 3, beat 2, restored it after restart, removed it explicitly and
restored revision 2 with no active placement after a second restart. The
append-only history retained both events. Owner-only storage, exact binding,
compatibility warnings, conflict-safe browser behaviour, path-free Inspector
state and byte-identical Workbench/library/pack inputs were verified alongside
the focused and full regression suites. Increment 6.1 is complete; wider
arrangement construction remains deferred.

## Export the private review without a server

The browser download remains available, but an agent or terminal workflow can
write the same current private review without opening a browser or binding a
loopback port:

```bash
sunofriend workbench "/absolute/path/to/stems" \
  --candidate-root "/absolute/path/to/results" \
  --catalog "/absolute/path/to/workbench-catalog.json" \
  --state-dir "/absolute/path/to/workbench-state" \
  --export-review "/absolute/fresh/path/workbench-review.json"
```

Use the same project, candidate roots, optional catalog and state directory as
the reviewed session. `--export-review` is mutually exclusive with `--inspect`
and `--open`; it starts no HTTP server. The destination must be fresh, is
written atomically and is never silently replaced. The JSON is private because
it may contain absolute paths, the full append-only event history and free-text
listening notes. The separate contribution preview remains the path- and
note-free disclosure boundary.

## Current limits

- The live mixer contains project source stems and current explicit selected
  MIDI only. It cannot audition an unselected candidate; use that stem's
  compare-role page first.
- Mixer settings, custom auditions, loops and play position are intentionally
  browser-tab state. They are not restored, rendered into a custom WAV or
  included in a handoff.
- Pack Composer v1 contains checked active selected MIDI, an optional dry proxy
  pair and separately opted-in source stems. Unselected alternative MIDI,
  custom mixer renders and eligible Instrument Bundles remain later additions.
- Existing preview WAVs remain labelled unnormalised; use the neutral renderer
  when comparing MIDI rather than embedded instruments.
- Precise decoded short comparison is bounded to 0.5–15 seconds. A per-stem
  request accepts at most six MIDI candidates; a canonical arrangement request
  accepts at most 24 total deduplicated-source and selected-MIDI tracks. Every
  path starts at recorded zero and therefore does not prove alignment.
- A decoded-loop request accepts at most 2 GiB across source audio, candidate
  MIDI, the SoundFont and neutral previews; oversized declared inputs fail
  before preview rendering. It accepts at most 64 MiB of generated PCM output.
  The owner-only stem/arrangement cache shares a limit of at most 32 recent
  windows or 256 MiB. Cached loops are rebuildable audition data, not
  durable project state: an older window can be evicted and prepared again.
- Exact full-song playback is available only for the four canonical presets,
  not arbitrary custom mute/solo/gain combinations. It accepts at most 24
  tracks and a 20-minute longest source; mono/stereo input must be 8–96 kHz.
  Its remaining 2 GiB, five-second/480-chunk, 32 MiB PCM16, 192 MiB two-chunk
  memory, 16 active-plan and 768 generated-capability limits are detailed in
  **Arrangement playback contracts** above. Failure stops at a verified
  boundary and never silently launches the coarse mixer.
- Fixed-window visualization culls paint work only. It still parses the full
  bounded JSON: 20,000 notes/8 MiB per candidate, 12 candidates per request,
  and 24 source lanes, 24 selected MIDI lanes and 40,000 notes in an
  arrangement. This is not server-side timeline pagination.
- A requested window can extend beyond one input. That track is silence-padded
  at the end and the interface reports the duration; the padded section is not
  evidence that the transcription omitted music.
- The standalone `midi-ab-review` command remains the blind,
  exact-source-window, fixed-window sample-RMS-matched promotion gate; the
  Workbench decoded loop is not level matched or blinded.
- The arrangement is a dry GM proxy. Complete-instrument checks and installed
  GarageBand patch choice remain a later view.
- Phrase piano-roll correction and creative recombination remain a later phase.
  Precise arbitrary custom mixes, server-paginated timeline payloads,
  medium/large checkpoint comparison and any opt-in public contribution are
  later, separately authorised work. The Workbench still consumes completed AI
  runs rather than launching a model itself.

These limits are shown in the interface so an incomplete feature is not
mistaken for a musical judgement.
