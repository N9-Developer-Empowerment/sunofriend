# Sunofriend Workbench

The Workbench is the local Phase 5 interface for deciding which MIDI result is
musically useful. It does not run a model or upload a song. Its explicit
preview/arrangement actions create content-addressed local audition proxies;
discovered MIDI remains byte-for-byte unchanged.

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
- elapsed time and real-time factor.

These values explain how a result was made; they do not select the most musical
one. Ordinary label leakage stays auditionable because a useful line may be in
the wrong broad family. Severe decoder bursts and zero-note results are marked
diagnostic-only: their original files remain available, but preview rendering
and **Use as main**/**Keep optional** are disabled. **Needs correction** and
**Reject** remain available so the failure can still be recorded.

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

- Existing preview WAVs remain labelled unnormalised; use the neutral renderer
  when comparing MIDI rather than embedded instruments.
- Browser switching shares time in seconds but does not yet use decoded
  short-loop Web Audio buffers for sample-accurate blind tests.
- The arrangement is a dry GM proxy. Complete-instrument checks and installed
  GarageBand patch choice remain a later view.
- Phrase piano-roll correction, model-size comparison and opt-in contribution
  remain later increments. The Workbench
  still consumes completed AI runs rather than launching a model itself.

These limits are shown in the interface so an incomplete feature is not
mistaken for a musical judgement.
