# Vocal comping ranked-evidence pilot

The current private pilot compares synchronized vocal-only takes one musical
phrase at a time. It produces evidence, audition clips and pickup suggestions.
It does **not** choose takes, assemble joins, tune notes or render a replacement
vocal stem yet.

## What you need

- 2–24 top-level WAV files containing alternative vocal takes. Silence is
  allowed where a take did not attempt a phrase.
- A UTF-8 text file containing the canonical lyrics. A PDF may be retained as
  source material, but its extracted text must be checked by a person first.
- One reviewed monophonic MIDI track representing the intended sung melody.
- A reviewed JSON timeline that binds musical phrase bounds to lyric text.
- The exact BPM, concert tuning, rights category and confirmation that every
  file shares the same recorded song zero.
- Optionally, the authorized AI vocal as fallback evidence. It is never ranked
  against or substituted for an acceptable human candidate.

Use dry recordings where possible. If a gentle recording chain was necessary,
apply the same chain to every take and declare `same-gentle-chain`.

## Reviewed phrase timeline

Phrase IDs must be unique. Bounds are seconds from the common recorded zero,
must be chronological and may contain gaps. Lyric words must occur in the same
order as the canonical lyrics.

```json
{
  "schema": "sunofriend.vocal-comp-timeline.v1",
  "status": "reviewed",
  "phrases": [
    {
      "phrase_id": "verse-01-a",
      "start_seconds": 8.42,
      "end_seconds": 11.76,
      "lyrics": "The first complete musical phrase"
    }
  ]
}
```

Each phrase must overlap at least one note in the reviewed target MIDI. The
tool will not infer phrase boundaries, rewrite lyrics or claim that an
automatic MIDI extraction was reviewed.

## Review automatic inputs

When lyrics were extracted from a PDF, phrase timing came from vocal-energy
gaps, or the target MIDI came from automatic vocal transcription, keep all
three drafts outside the comp project. Give the timeline
`status: "automatic_unreviewed"`, then build a fresh private listening page:

```bash
.venv/bin/sunofriend vocal-comp-draft-review \
  --lyrics "/path/to/automatic-lyrics.txt" \
  --target-midi "/path/to/automatic-target.mid" \
  --phrase-timeline "/path/to/automatic-phrases.json" \
  --target-vocal "/path/to/ai-reference-vocal.wav" \
  --bpm 86 \
  --tuning-hz 440 \
  --out-dir "/fresh/path/vocal-comp-input-review"
```

Hear the AI vocal and dry MIDI proxy for every phrase. Approve both the
lyrics/timing and target melody only when they are genuinely usable. Playback,
page defaults and an unresolved export create no decision. After the page
exports a complete reviewed JSON, resolve it against the exact package:

```bash
.venv/bin/sunofriend vocal-comp-draft-resolve \
  "/fresh/path/vocal-comp-input-review" \
  "/path/to/vocal-comp-draft.reviewed.json" \
  --out-dir "/fresh/path/vocal-comp-reviewed-inputs"
```

The resolver rejects changed packages, incomplete phrase rosters, unresolved
answers and reviews exported for a different draft. It copies the exact target
MIDI and lyrics, publishes the approved timeline separately, and still makes
no take selection or audio comp.

If listening shows that the draft is wrong, preserve that outcome instead of
forcing approvals through the resolver:

```bash
.venv/bin/sunofriend vocal-comp-draft-feedback \
  "/fresh/path/vocal-comp-input-review" \
  "/path/to/vocal-comp-draft.unresolved.json" \
  --out "/fresh/path/vocal-comp-draft-feedback.json"
```

The feedback artifact binds the exact package and review but has zero authority
over lyrics, timing, melody, take selection, rendering or correction.

## Transcribe words before ranking

The Heart Sees review demonstrated that energy gaps and target-relative MIDI
are not enough to establish a lyric phrase. One added AI-vocal ad-lib shifted
the apparent phrase mapping even though parts of the melody sounded close.
Every AI and human vocal therefore needs auxiliary word-timestamp evidence
before the pilot can rank phrases safely.

`vocal-comp-stt` runs one unprompted local OpenAI Whisper transcript from an
exact checkpoint that is already on disk. It has no model-name download
fallback and does not send the known lyrics as a prompt:

```bash
.venv/bin/sunofriend vocal-comp-stt \
  "/path/to/take-01.wav" \
  --checkpoint "/path/to/small.en.pt" \
  --python "/path/to/python-with-openai-whisper" \
  --model-label small.en \
  --source-id take-01 \
  --out-dir "/fresh/path/take-01-stt"
```

Repeat for the AI reference and every human take, then bind every transcript
to its exact source audio and align the observed words globally to the
canonical lyrics:

```bash
.venv/bin/sunofriend vocal-comp-word-align \
  "/path/to/canonical-lyrics.txt" \
  --transcript ai-reference=/path/to/ai-stt/transcript.words.json \
  --audio ai-reference=/path/to/ai-reference.wav \
  --transcript take-01=/path/to/take-01-stt/transcript.words.json \
  --audio take-01=/path/to/take-01.wav \
  --out-dir "/fresh/path/vocal-comp-word-alignment"
```

Known lyrics remain canonical. The result preserves exact matches and exposes
insertions as ad-lib candidates, omissions as omission candidates, and changed
words as substitution candidates. All three require listening review; speech
recognition is evidence, not truth. Word timestamps are not silently divided
into syllables. Syllable/phoneme timing remains unavailable until a
singing-oriented aligner has been separately qualified and reviewed.

If a complete canonical lyric line has no exact word anchor, the aligner does
not force a word-for-word substitution against an unrelated heard phrase. It
keeps the heard phrase as ad-lib candidates and the canonical line as omission
candidates. This conservative rule prevents a short non-canonical phrase from
silently acquiring the timing identity of a missing lyric line.

Build a private detailed listening page after word alignment:

```bash
.venv/bin/sunofriend vocal-comp-word-review \
  "/path/to/vocal-comp-word-alignment.json" \
  --lyrics "/path/to/canonical-lyrics.txt" \
  --audio ai-reference=/path/to/ai-reference.wav \
  --audio take-01=/path/to/take-01.wav \
  --out-dir "/fresh/path/vocal-comp-word-review"
```

Repeat `--audio` for every source in the alignment. The page provides full
context, a shared ad-lib window, one common comparison window per canonical
line, visible STT differences, detailed per-source questions, progress and
explicit draft/completed JSON export. Browser draft saving is local form
recovery only. Playback and drafts grant no authority, and completed feedback
still cannot select a take or approve melody.

## Plan and admit a project

Run the read-only plan first:

```bash
.venv/bin/sunofriend vocal-comp-create \
  "/path/to/vocal-takes" \
  --lyrics "/path/to/lyrics.txt" \
  --target-midi "/path/to/reviewed-target.mid" \
  --phrase-timeline "/path/to/reviewed-phrases.json" \
  --target-vocal "/path/to/optional-ai-reference.wav" \
  --bpm 120 \
  --tuning-hz 440 \
  --rights-category owned \
  --processing-chain dry \
  --confirm-common-recorded-zero \
  --confirm-target-reviewed \
  --out-dir "/fresh/path/vocal-comp-project" \
  --plan
```

Remove `--plan` to copy the exact admitted files into the fresh, owner-only
project. Existing output is never replaced.

## Analyze phrases

```bash
.venv/bin/sunofriend vocal-comp-analyze \
  "/fresh/path/vocal-comp-project" \
  --out-dir "/fresh/path/vocal-comp-analysis"
```

This runs the existing local pYIN and Basic Pitch evidence paths. An already
completed source-matched RMVPE run may be added without downloading or running
a model inside comp analysis:

```bash
--rmvpe-frames 'take-001=/path/to/rmvpe.frames.json'
```

The HTML report contains at most three local audition excerpts for each
phrase. JSON retains the independent tracker observations and fixed score
dimensions. CSV is a compact inspection surface. `pickup-plan.json` records
phrases with `no_acceptable_candidate`; if an AI reference was admitted, its
excerpt appears there as fallback-only evidence.

## Interpret the result carefully

The pilot ranking is transparent but deliberately uncalibrated. Melody has the
largest weight, followed by voiced completeness and timing; signal safety has
a small weight, uncertainty is penalized, and expression has zero weight.
That makes the report useful for checking engineering topology, not musical
truth. Listen to the candidates before making any take decision.

The next implementation increment is a review surface for the word alignment,
followed by revised phrase boundaries. Phrase ranking must not resume until
the lyrics and timing survive that review. A human decision store, global
phrase-selection proposal, natural assembly, boundary review and optional
gentle correction remain later gates.
