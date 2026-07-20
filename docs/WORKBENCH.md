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
decisions, neutral preview rendering, selected-arrangement audition and a safe
exact-MIDI GarageBand handoff. Phase 5.4 now supplies both a read-only per-stem
source/MIDI comparison timeline and a full-song selected-arrangement explorer.
The arrangement explorer shows every unique project source stem beside only
the active explicit main and optional MIDI choices, with temporary visibility,
mute, solo and level controls. It does not infer an offset: every source and
MIDI file begins at its recorded zero, so equal displayed seconds do not by
themselves prove source/MIDI alignment. The user-composed GarageBand basket
remains the next planned increment.

## Result Explorer direction

The next interface is an evolution of this Workbench, not a Mirelo clone and
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
  and
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

The interface continues to call candidates A/B/C until technical details are
opened. The visual lanes make differences easier to locate; they do not say
which process is musically correct.

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

The planned pack composer will be separate from the main/optional musical
decision. It will show exactly which unchanged MIDI, explicitly requested
stems, preview mixes and eligible Instrument Bundles will enter a GarageBand
ZIP. The existing source-audio-free exact-MIDI handoff remains the current safe
default. Direct note editing, phrase recombination and Clip-library composition
belong to the later creative arrangement phase.

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
- **Equivalent**, **None are usable** and **I cannot tell** remain valid
  stem-level outcomes.

The complete local export contains paths, event history and private listening
notes. Treat it as private project data. The separately displayed contribution
preview excludes audio, MIDI files, absolute paths, notes, dwell time and play
counts. Phase 5.0 has no contribution or upload endpoint.

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

Set a short recognisable loop and use the source/Candidate A/B/C buttons. Each
button resumes at the shared position in seconds; pressing a browser player's
normal controls also updates that position. If a card has only an old preview
or none, choose **Render neutral preview**. The cached proxy uses:

- the same local SoundFont and FluidSynth settings;
- one stable GM program for the stem's role;
- the source MIDI's note times in seconds; and
- the project BPM in the proxy file.

The original MIDI hash does not change. Neutral means renderer-consistent, not
peak-normalised: note velocity and density remain audible. Browser media
switching is time-synchronised but is not claimed to be sample-accurate.

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
decoded sample-accurate Workbench switching remains a later gate.

The separate Phase 5.2 batch-size comparison does not add a Workbench choice.
Batch 1 and batch 2 produced identical canonical note payload, base MIDI,
expression MIDI and every auditionable MIDI on the private golden, so there is
no musical A/B to review. Its read-only comparator reports zero mutations,
selections and promotions; batch 1 remains the execution default after the
batch-2 arm was slower and used more memory in the bounded CPU observation.

The first Phase 5.3 `hybrid-report` is also upstream of the Workbench. It
checks the exact lead source, unresolved phrase geometry and existing S0/M1/M3
evidence, then records phrase-level and cross-phrase matches, boundary and
octave disputes, lane-only notes, duplicates and raw source support. Its report
also states that M1's same-song derivation and M3's unsupplied original-MIDI
payload are not verified by this v1 command. It creates no candidate MIDI and
the Workbench does not import, rank or apply the report yet. The next UI slice
must present selected disagreement phrases as a listening task and record
explicit choices before any hybrid challenger can enter the normal result
space.

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

Live MIDI layers use renderer-consistent neutral previews. When one is absent,
use **Prepare selected MIDI sounds locally**; Workbench does not silently
substitute an existing unnormalised preview. The source stems and neutral MIDI
previews are not level matched, so the hybrid mix is a creative listening aid,
not fair comparison evidence. Multiple browser media elements share displayed
seconds but are not sample-accurate. The separately prepared dry GM proxy
remains the reproducible control and downloadable convenience render.

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

It excludes source audio, private notes, absolute paths, rejected candidates
and unreviewed defaults. Import the numbered MIDI files onto separate Software
Instrument tracks and choose the final patches in GarageBand; those originals
are authoritative.

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
- The current GarageBand handoff contains explicit selected MIDI and a dry
  proxy. It is not yet a user-composed basket for optional source stems,
  alternative MIDI, preview mixes or eligible Instrument Bundles.
- Existing preview WAVs remain labelled unnormalised; use the neutral renderer
  when comparing MIDI rather than embedded instruments.
- Browser switching shares time in seconds but does not yet use decoded
  short-loop Web Audio buffers for sample-accurate switching. The standalone
  `midi-ab-review` command now supplies blind, exact-source-window,
  fixed-window sample-RMS-matched review packages, but does not change that
  Workbench playback limit.
- The arrangement is a dry GM proxy. Complete-instrument checks and installed
  GarageBand patch choice remain a later view.
- Phrase piano-roll correction and creative recombination remain a later phase.
  Model-size comparison and any opt-in public contribution are also later,
  separately authorised work. The Workbench still consumes completed AI runs
  rather than launching a model itself.

These limits are shown in the interface so an incomplete feature is not
mistaken for a musical judgement.
