# Automatic key and tempo evidence

Status: deterministic v1 implemented; calibration and richer ensemble views remain
Product boundary: local, deterministic evidence; no automatic musical approval

## Implementation status (2026-08-07)

The first production slice is now implemented:

- `sunofriend musical-metadata SOURCE [--out FRESH.json]` performs local,
  path-free, self-hashed analysis without changing the source;
- `source-import` always attempts analysis and records a bounded unavailable
  result for short, silent, undecodable or dependency-limited audio;
- `source-import-folder --metadata-source ORIGINAL_MIX` binds evidence to the
  exact pre-separation mix, while a folder with no authoritative mix records
  `no_authoritative_mix_source` instead of guessing from one stem;
- explicit CLI metadata wins over filename/folder metadata, which wins over a
  high-confidence automatic key/BPM; automatic tuning remains evidence-only;
- prepared projects contain
  `INPUT/context/automatic-musical-metadata.json` plus a hash-pinned manifest
  reference; and
- Simple carries the unchanged path-free document into
  `TECHNICAL/automatic-musical-metadata.json`, its result receipt and ZIP.

The v1 analyzer uses onset-strength tempo consensus across ten segments and a
tuning-aware CQT chroma/profile key view. It preserves half/double tempo,
ranked keys, window votes and confidence. CENS/STFT ensemble comparison,
tempo-change segmentation, explicit conflict taxonomy, Workbench confirmation
events and corpus calibration remain follow-up work; none is implied by the v1
confidence label.

## Problem

Sunofriend currently obtains key, BPM and tuning from explicit CLI values or
the `-KEY-BPMbpm-TUNINGhz` filename convention. A finished mix without that
metadata therefore needs an external analysis step before separated parts can
enter the prepared-project and MIDI workflow.

Key and tempo are required for a useful DAW handoff, but neither is always a
single unambiguous machine answer. Beat trackers can prefer double time, and
key estimators can confuse a tonic with its relative minor, dominant or an
enharmonic spelling. The product should always calculate and preserve this
evidence without presenting an estimate as a human-confirmed fact.

## Target experience

For every authorised source import, prepared stem folder and finished-mix
separation plan:

1. Analyze the exact local audio bytes for tempo and key without network use.
2. Retain the leading result, alternatives, confidence evidence, half/double
   tempo family, tuning observation and exact source identity.
3. Compare automatic evidence with an explicit CLI value, prepared manifest
   or filename declaration instead of silently replacing it.
4. Use a high-confidence estimate when no declaration exists; otherwise mark
   the field `review_required` and ask for a musician decision before MIDI is
   activated.
5. Show the effective key and BPM, their provenance and any conflict in
   `START-HERE.txt`, the Workbench setup panel and technical receipts.
6. Preserve an explicit override as the effective value while keeping the
   automatic estimate available for audit and later correction.

Finished-mix separation must retain its existing rights and listening gates.
Calculating metadata must not cause separation, select separated stems or
start MIDI creation automatically.

## Worked evidence: `show you me`

The exact MP3 with SHA-256
`7aaf7b57f0de0a52bb1807dfbf547230b0e48cc66ff447050b108db405fe7251`
produced the following local observations:

- global beat and tempogram estimate: `143.554688 BPM`;
- ten overlapping windows: all `143.554688 BPM`;
- strong half-time candidate: `71.777344 BPM`;
- proposed DAW tempo after bounded integer snapping: `144 BPM`, while
  retaining `72 BPM` as the half-time interpretation;
- leading tuning-aware chroma result: `G# major`, presented enharmonically as
  `Ab major` for an ordinary key signature;
- key-window votes: `G# major` 7, `C minor` 2, `D# major` 1; and
- secondary global candidates included `C minor` and `D# major`.

This is sufficient for an automatic first-pass `Ab major / 144 BPM` project,
but the receipt must remain `review_recommended`. The observed half-time pulse
and alternative keys must not be discarded.

## Implemented v1 architecture and follow-up design

### 1. Pure analysis module

Add `src/sunofriend/musical_metadata.py` with a side-effect-free analysis
contract. It should accept decoded mono PCM plus sample rate and return a
versioned document rather than making a product decision.

Tempo evidence:

- harmonic/percussive separation followed by a percussive onset envelope;
- full-song beat tracking and tempogram peak extraction;
- overlapping 20–30 second window estimates;
- explicit half-time and double-time candidate grouping;
- robust consensus, stability and integer-snap distance; and
- no inferred downbeat unless a separate downbeat contract is implemented.

Key evidence:

- tuning-aware harmonic CQT chroma;
- CENS and STFT chroma as independent views;
- Krumhansl-Schmuckler major/minor profile correlations;
- overlapping segment votes and global rankings;
- canonical enharmonic presentation without losing pitch-class identity; and
- an explicit ambiguity margin for relative-key, dominant and modulation
  cases.

Use the already installed NumPy/librosa stack. Add no model, checkpoint,
download, telemetry or network dependency.

### 2. Versioned evidence document

Define `sunofriend.musical-metadata-analysis.v1` with at least:

- source SHA-256, bytes, decoded duration, sample rate and channel policy;
- implementation version and deterministic analysis settings;
- ranked BPM candidates, tempo-family relationships, window values,
  stability, selected first-pass value and confidence status;
- ranked key candidates, enharmonic display name, correlations, window votes,
  ambiguity margin and confidence status;
- tuning observation as evidence, not an automatic concert-A assignment;
- effects booleans proving no source mutation, selection, feedback, network
  or upload; and
- a self-hash over the path-free document.

Store the report under the prepared project and include it in the final ZIP as
`TECHNICAL/automatic-musical-metadata.json`.

### 3. Read-only CLI first

Add a command such as:

```bash
sunofriend musical-metadata "/absolute/path/to/song.mp3"
```

The initial command should be read-only and print the complete JSON evidence.
An optional fresh `--out` may publish the same path-free document atomically,
but must not import, separate, rename or edit audio.

### 4. Metadata precedence and conflict rules

Keep the effective-value precedence explicit:

1. direct `--key` / `--bpm` user override;
2. validated prepared-project metadata;
3. parseable filename declaration;
4. high-confidence automatic estimate; and
5. unknown / review required.

Always run analysis when decodable audio is available, even when a higher
precedence value exists. Record whether evidence agrees, differs only by a
half/double tempo relation, differs only enharmonically, or conflicts.

Never silently overwrite a declaration. A low-confidence estimate or material
conflict must keep the project usable only with an explicit value and visibly
recommend review.

### 5. Import and separation integration

Integrate the analyzer into:

- `source-import` planning, using the source asset once;
- `source-import-folder` planning, preferring a declared reference mix and
  otherwise fusing suitable harmonic and percussive roles without analyzing
  every file independently as though each were a song;
- the finished-mix separation plan, so key/BPM evidence is bound to the exact
  pre-separation source hash; and
- the reviewed separation-to-prepared-project handoff, carrying that bound
  evidence without recalculating against model estimates.

The existing separation review remains mandatory before its stems are used
for MIDI. A future guided command may resume after an explicit useful-stems
decision, but it must not collapse rights confirmation, listening review and
MIDI activation into one implicit action.

### 6. Product surfaces

Update:

- `src/sunofriend/cli.py` for the read-only command and import flags;
- `src/sunofriend/source_import.py` and
  `src/sunofriend/source_folder_import.py` for planning and receipts;
- `src/sunofriend/source_project.py` for evidence references and effective
  metadata provenance;
- `src/sunofriend/metadata.py` so filename parsing is one declared source,
  not the only inference mechanism;
- `src/sunofriend/simple_result.py` and automatic pack reports;
- Workbench/TUI setup panels, keeping estimates visibly unreviewed; and
- README, interface contract, Sunofriend skill and stem-separation guide.

## Confidence policy

Start conservatively and calibrate thresholds from fixtures and authorised
review data. A proposed first policy is:

- `high`: stable tempo family across at least 80% of windows and a clear key
  margin with at least 70% segment agreement;
- `medium`: usable leading result but a half/double or relative-key ambiguity;
- `low`: inconsistent windows, weak harmonic energy, modulation, silence or
  insufficient duration; and
- `unavailable`: decoding or bounded-analysis failure.

Only `high` may fill a previously missing effective value automatically.
`medium` may provide a prefilled suggestion but must remain review-required.
Thresholds must be validated before becoming product defaults.

## Test and evaluation plan

Add unit and contract tests for:

- synthetic major/minor keys across all twelve pitch classes;
- constant tempos, half-time/double-time patterns and tempo changes;
- enharmonic normalization, including `G# major` to `Ab major` display;
- silence, drums-only, vocals-only, short audio and modulation;
- detuned audio without treating estimated tuning as confirmed concert A;
- repeatable path-free JSON and source-hash binding;
- explicit override, filename agreement and conflict precedence;
- source-import and folder-import plan/execute identity;
- no source mutation, network, upload, feedback or stem selection;
- final ZIP inclusion and START-HERE provenance wording; and
- the existing automatic-primary versus starter-MIDI note identity checks.

Build a bounded evaluation corpus from mathematical fixtures and separately
authorised local songs with human-supplied reference labels. Report top-one and
top-three key accuracy, correct tempo-family rate, exact-BPM tolerance and
confidence calibration. Do not tune thresholds against one song or publish
private filenames/audio.

## Delivery sequence

1. Implement the pure analyzer and fixture tests behind no product route.
2. Add the read-only `musical-metadata` CLI and versioned evidence schema.
3. Run the bounded evaluation and set conservative confidence thresholds.
4. Integrate evidence into source-import plans and prepared-project receipts.
5. Add conflict handling and effective-value provenance to Create/TUI.
6. Bind finished-mix evidence through separation review into prepared stems.
7. Update documentation and skill guidance, then run the full test suite and
   real local smoke tests without changing existing source bytes.

## Acceptance gates

- No network or new dependency/model installation.
- Repeat runs on the same bytes produce the same path-free evidence document.
- Source bytes and existing user-declared metadata are never mutated.
- Half/double tempo and relative-key ambiguity are retained, not hidden.
- No low/medium-confidence estimate becomes an unlabelled project fact.
- Explicit values remain authoritative and conflicts are visible.
- The finished pack contains the exact analysis evidence and provenance.
- Existing Simple, Studio, separation rights and listening boundaries remain
  intact.
