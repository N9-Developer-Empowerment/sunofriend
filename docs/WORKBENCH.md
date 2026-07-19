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

## Export a GarageBand handoff

The ZIP is content-addressed and contains:

- numbered, byte-for-byte copies of explicit main/optional MIDI choices;
- `selected-arrangement-proxy.mid` and its dry WAV audition;
- a path-free selection/setup manifest; and
- concise GarageBand import instructions, including the exact BPM to set.

It excludes source audio, private notes, absolute paths, rejected candidates
and unreviewed defaults. Import the numbered MIDI files onto separate Software
Instrument tracks and choose the final patches in GarageBand; those originals
are authoritative.

## Current limits

- Existing preview WAVs remain labelled unnormalised; use the neutral renderer
  when comparing MIDI rather than embedded instruments.
- Browser switching shares time in seconds but does not yet use decoded
  short-loop Web Audio buffers for sample-accurate blind tests.
- The arrangement is a dry GM proxy. Complete-instrument checks and installed
  GarageBand patch choice remain a later view.
- Phrase piano-roll correction, M4 mixed-role candidate generation, model-size
  comparison and opt-in contribution remain later increments. The Workbench
  still consumes completed AI runs rather than launching a model itself.

These limits are shown in the interface so an incomplete feature is not
mistaken for a musical judgement.
