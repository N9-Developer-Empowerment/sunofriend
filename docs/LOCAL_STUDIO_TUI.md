# Guided Local Studio TUI

Status: Phase 5.10a and the initial Phase 5.10b full-project runner implemented;
remaining Phase 5.10b plus Phases 5.10c–d planned
Interface contract: `2026-07-27.2`

The Guided Local Studio is the preferred human entry point to Sunofriend. It
puts a clear terminal dashboard in front of the deterministic CLI and opens the
existing graphical Workbench when detailed listening, piano-roll evidence,
decisions, the Developer Inspector or GarageBand export is needed.

The complete product journey produces two linked creative outputs: reviewed,
editable MIDI and a MIDI-derived song-interpretation WAV rendered from the
selected MIDI. The conversion tab creates candidates; review establishes the
selected MIDI; the Workbench then renders the listening interpretation. The
TUI and Workbench share the versioned product definition from
`product_contract.py`; neither interface redefines the audio or MIDI policy.

It is not a replacement transcription engine and it is not a terminal rewrite
of the Workbench. Sunofriend's strength remains the same: retain several
analytical and AI MIDI alternatives, show how each was produced, let the
listener choose by role or phrase, and preserve the original evidence.

The expert routes remain supported:

- use the CLI directly for scripting, exact reproducibility and advanced
  options;
- use the Sunofriend agent skill when conversational orchestration is useful;
- use `sunofriend workbench` directly when a project is already prepared; or
- use `sunofriend tui` for the guided human workflow.

## Start the Guided Local Studio

Start without arguments and enter the folders in the dashboard:

```bash
sunofriend tui
```

Or open one project and its existing result roots immediately:

```bash
sunofriend tui \
  "/absolute/path/to/Song-B minor-113bpm-440hz" \
  --candidate-root "/absolute/path/to/song-specialist-midi" \
  --candidate-root "/absolute/path/to/song-ai-midi"
```

The TUI accepts the same optional catalog, state and SoundFont inputs used by
the visual review path:

```bash
sunofriend tui "$PROJECT" \
  --candidate-root "$RESULTS" \
  --catalog "$WORKBENCH_CATALOG" \
  --state-dir "$PRIVATE_WORKBENCH_STATE" \
  --soundfont "$GM_SOUNDFONT"
```

Candidate roots may also be entered interactively, separated by semicolons.
Inside the TUI:

- `Ctrl+R` refreshes the project projection;
- `F6` opens the visual Workbench without conflicting with path-field editing;
- `Ctrl+D` runs the local system check; and
- `Ctrl+Q` stops the owned Workbench process and exits.

### Convert a complete project into a separate output

Supply a project and prefill a destination that does not yet exist:

```bash
sunofriend tui \
  "/absolute/path/to/Song-B minor-113bpm-440hz" \
  --conversion-output "/absolute/path/to/fresh-song-midi-v1"
```

`--conversion-output` only fills the editable **Fresh conversion output**
field. It does not start conversion. Check the project and output paths, choose
**Convert all stems**, read the operation summary, and confirm the write.
Launch this conversion journey without `--catalog`: an explicit Workbench
catalog intentionally fixes candidate membership, so the TUI disables
conversion rather than create results that the catalog would ignore.

The initial 5.10b runner deliberately exposes one safe production recipe:

1. It rejects an output that already exists. It never supplies an overwrite
   option.
2. It calls the production `listen-all` engine in `repair` mode with candidate
   variant evaluation for the supported instrumental stems.
3. It then calls the production `vocal-melody` engine separately for each
   discovered lead or backing-vocal stem. `listen-all` itself does not process
   vocals.
4. It discloses three bounded compatibility routes for project filenames that
   have no direct instrumental converter: `wind` uses the `lead` engine,
   `rhythm` uses the `keys` engine, and `other` uses the `synth` engine. These
   are proxy conversion roles, not claims that the source instrument was
   identified.
5. It records a visible skip when a source is near-silent instead of treating
   the absence of useful evidence as a successful transcription.
6. It streams progress from the existing engines into the Activity tab.
7. **Cancel conversion** terminates the current job and preserves the partial
   fresh root. The partial result is evidence to inspect or remove manually;
   it is not an automatically resumable job.
8. A successful job reloads the project with the fresh output as its candidate
   root, ready for **Open visual studio**.

The completion panel names skipped, failed and proxy-routed roles and includes
bounded warning text instead of reducing those facts to counts. The reload
gate verifies role coverage from MIDI files inside the fresh output root; one
unrelated or previously discovered candidate cannot make a partial conversion
look complete.

Conversion never ranks, accepts or selects a MIDI candidate. The Workbench
remains a review/decision/export surface and does not start transcription.
There is no durable job ledger, restart recovery or automatic retry in this
increment.

The visual Workbench starts with its read-only Developer Inspector available by
default. Use `--no-developer-inspector` when the additional developer view is
not wanted:

```bash
sunofriend tui "$PROJECT" \
  --candidate-root "$RESULTS" \
  --no-developer-inspector
```

In a repository checkout, replace `sunofriend` with
`.venv/bin/sunofriend` when the command is not on `PATH`.

### Review the repaired Pupsies bass

Restart an older TUI/Workbench process before this review so the current
renderer and decoded-loop policies are loaded:

```bash
PROJECT="/Users/errolelliott/IdeaProjects/Sunofriend/work/pupsies - 01. misery. (1)-B major-119bpm-440hz"
RESULTS="$PWD/work/pupsies-misery-continuous-bass-v3"
STATE="$PWD/work/pupsies-misery-continuous-bass-review-state-v3"

.venv/bin/sunofriend tui "$PROJECT" \
  --candidate-root "$RESULTS" \
  --state-dir "$STATE"
```

Choose **Open visual studio**, select **bass**, set a recognisable 10–15 second
range and choose **Prepare precise loop**. The primary lanes are
`contour_clean`, `continuous_sustain` and `octave_resolved`; raw and
chord-root-safe evidence stays under advanced alternatives. The page asks
separately about contour, octave/register, held accompaniment, genuine rests
and proxy-patch texture. Each switch button shows its temporary comparison
gain. Source, preview WAV and MIDI remain unchanged.

## What the implemented TUI provides

Phase 5.10a provides the orientation and browser bridge:

1. A Textual dashboard accepts a stem project and one or more narrow existing
   candidate roots.
2. Read-only project discovery reports the inferred key, BPM and tuning.
3. A stem table shows role, primary/total candidate counts, whether an explicit
   decision exists, selected-part count and the next required attention.
4. Selecting a stem reads up to three unchanged primary MIDI candidates and
   draws compact terminal pitch-contour and note-activity maps. These maps are
   orientation aids, not scores or automatic rankings.
5. The System tab checks transcription, FluidSynth preview and CoreMIDI
   playback readiness without downloading a model.
6. The Activity tab keeps a bounded, in-memory account of TUI operations. It
   hides the Workbench launch token and private decision-store path.
7. One action starts the existing loopback Workbench with the Developer
   Inspector enabled by default. The TUI uses the exact project, candidate
   roots, catalog, state directory and SoundFont selected by the user.
8. Stop, quit and terminal unmount terminate and reap the Workbench child
   process. A process that does not stop within two seconds is killed and
   reaped rather than being left behind.
9. Project and result-root controls stay locked while that child is active, so
   the terminal dashboard and browser cannot silently point at different
   songs.

Loading a project does not create a Workbench database. If the exact private
database already exists, 5.10a folds its explicit events to show current
progress; otherwise it derives the same initial state from an empty event
stream.

The initial Phase 5.10b increment adds the explicit full-project operation
described above. The TUI owns one child conversion process, streams bounded
progress, supports cancellation and reloads only after successful completion.
It orchestrates `listen-all` and `vocal-melody`; it does not reimplement pitch,
timing, repair, evaluation or MIDI writing in Textual callbacks.

### 5.10a completion evidence

The final 26 July 2026 validation loaded a private 16-stem long-song project
with 46 discovered MIDI alternatives, opened on the first stem carrying MIDI
and rendered its primary pitch/activity lanes without creating a decision or
preference. Large-terminal, 110×34 boundary and 80×24 compact layouts were
visually and programmatically checked. The wheel contained the TUI and Textual
dependency; the source distribution contained the canonical skill and its
generated interface reference. The original completion suite passed 1,107
tests. After the bass-continuity increment the complete suite passes 1,114,
with the one existing third-party `resampy`/`pkg_resources` deprecation
warning. An independent final audit found no remaining actionable issue.

## TUI, Workbench and Inspector boundary

The three interfaces have separate jobs:

| Surface | Purpose | State it may change |
| --- | --- | --- |
| Guided Local Studio TUI | Project orientation, explicit fresh full-project conversion, local diagnostics and safe orchestration | In-memory navigation/activity; an explicitly confirmed conversion may create one fresh output through the production engines; it may start, cancel and reap its conversion child or start/stop its Workbench child |
| Workbench | Waveforms, MIDI lanes, synchronized listening, explicit musical decisions, MIDI-derived song-interpretation WAV and GarageBand pack basket | Only explicit decision, review and basket actions are durable; playback and views are temporary, while the requested WAV is a rebuildable artifact |
| Developer Inspector | Explain the five-stage application architecture, allow-listed module/function references, recent operations, reducer replay and separate state planes | None; refresh, clear and replay are read-only and zero-effect |
| CLI | Deterministic transcription, transformation, validation and artifact production | Only the files and stores explicitly named by the selected command |

The Inspector is an application-level debugger. It is not a Python line
debugger, evaluator, shell, SQL console or filesystem browser. The TUI Activity
tab is not a second Inspector: it is a small operational log for the current
terminal process.

The browser remains the right place for rich graphical evidence. Its
per-stem waveform and coloured MIDI lanes, full-song arrangement timeline,
precise decoded transports, coarse custom mixer, MIDI-derived
song-interpretation WAV, decisions and exact GarageBand ZIP are not compressed
into terminal widgets. The TUI makes that surface easy to reach and will
progressively guide the work around it. Only the prepared precise per-stem loop
applies disclosed browser-only active-block comparison gains; card/fallback and
canonical arrangement/full-song transports remain unlevelled.

## State and privacy contracts

These rules apply to every Phase 5.10 increment:

- Audio, MIDI, chord evidence, reviews and logs stay local by default.
- There is no account, upload, telemetry or hidden feedback route.
- Project and result paths may be entered in private terminal fields, but the
  TUI project and MIDI-map projections shown to widgets are path-free.
- Source audio and candidate MIDI are immutable evidence. Loading, mapping,
  highlighting, playing, opening a view and running diagnostics are not
  preferences.
- TUI activity is bounded in memory and disappears on exit. Streamed conversion
  output is operational progress, not training data, feedback or a durable job
  history.
- Workbench uses `127.0.0.1`, a fresh per-launch capability token and an
  allow-list of verified files. The token is hidden from the TUI activity
  display.
- Existing Workbench decisions remain append-only. Derived current selections,
  the separate pack basket, browser-only audition state and rebuildable media
  caches stay distinct.
- The TUI constructs typed, allow-listed Sunofriend operations. Its conversion
  runner is not an arbitrary shell-command box.
- A conversion output must be fresh. Cancellation preserves a partial root so
  evidence is not silently destroyed; the current increment does not resume or
  retry it after restart.
- Any future public or aggregate learning remains an explicit-consent Phase 7
  operation with a complete preview of the exact data leaving the machine.

## Delivery plan

### 5.10a — Orientation and visual bridge: implemented

The implemented slice is the Textual dashboard described above. Its acceptance
boundary is that a lay user can load an already processed project, understand
its setup and progress, inspect simple MIDI shape, check the machine and open
the complete visual review surface without asking an agent to assemble a
command.

### 5.10b — Guided conversion runner: initial full-project slice implemented

The implemented slice adds an editable fresh-output preflight and one
cancellable **Convert all stems** job. It runs `listen-all` in repair mode with
variant evaluation, follows with separate lead/backing `vocal-melody` jobs,
discloses the three proxy role routes, skips near-silent sources, streams
progress, preserves partial output on cancel and reloads the new root only on
success. It never overwrites or auto-selects a result.

Still planned for 5.10b:

- typed one-instrument `listen` and standalone vocal forms;
- common key, BPM, anchor and preview forms;
- an owner-only durable ledger with immutable request/result identities;
- safe restart recovery and explicit retry of partial or failed work; and
- richer structured failure summaries.

Retries must continue to use a new output rather than silently replacing an
existing tree.

### 5.10c — Guided project journey: planned

Connect completed jobs to an explicit sequence:

1. verify generated evidence;
2. compare each stem in Workbench;
3. hear selected parts alone, against stems and in the arrangement;
4. create and compare the MIDI-derived song-interpretation WAV;
5. inspect unresolved or failed candidates;
6. choose the GarageBand pack basket; and
7. run the existing tutorial, quiz and exact-pack acceptance checks.

The TUI will display durable progress derived from verified Workbench state and
job evidence, while rich playback and piano-roll interaction remain in the
browser. Navigation must not become a choice, and a visible default must not
become a winner.

### 5.10d — Explicit local feedback and full guided handoff: planned

Add structured, user-initiated feedback for process usefulness, failure type,
musical role, phrase context, instrument choice and GarageBand outcome. The
local record will pin exact versions and candidate hashes, retain valid
`equivalent`, `neither`, `none usable` and `cannot tell` outcomes, and stay
separate from audition history. It may improve local ordering of what to hear
first, but must not mutate evidence or select a candidate automatically.

The TUI will also guide eligible Phase 6 Clip actions and exact handoff
artifacts only as their existing review-before-write contracts become
available. Exporting or contributing feedback will remain a separate explicit
action with a path-free disclosure preview. No feedback collection, automatic
learning or network contribution is implemented in 5.10a.

## Unfinished work carried forward

Phase 5.10 changes the preferred interface, not the authority or completion
status of existing phases. The following register retains both
interface-relevant product work and the experimental work that must remain
visible; the [AI transcription and instrument roadmap](AI_TRANSCRIPTION_ROADMAP.md)
remains the exhaustive programme record.

### Phase 4 experimental lane

- Keep query/prompt isolation for mixed stems, neural denoise/de-reverb,
  monophonic DDSP-style timbre, optional Audio Unit hosting and clearly
  labelled generated missing samples as gated experiments.
- Require target-plus-residual reconstruction, an audio-valid decoder and
  explicit listening evidence; generated material must never become `exact`
  evidence automatically.

### Phase 5

- Complete the separately gated Phase 5.3 blind phrase choice, same-song source
  lineage and mixed-role evidence before any explicit hybrid is created.
- Add precise arbitrary custom mixes; the present arbitrary mixer is
  second-synchronized HTML media rather than sample-accurate decoded playback.
- Replace full bounded timeline downloads with server-paginated timeline
  payloads where long projects require it.
- Define eligibility contracts before adding unselected alternative MIDI,
  Instrument Bundles, balanced-audition artifacts or custom rendered mixes to
  GarageBand Pack Composer.
- Compare medium/large optional checkpoints only when a bounded golden and a
  clear musical question justify the cost.

### Phase 6

- Turn the immutable Clip reuse proposal into separately reviewed arrangement
  render, playback and export without coupling it to Workbench decisions.
- Add major/minor mode remapping, tuning and downbeat transformations with
  explicit alignment and register contracts.
- Keep register, batch and combined transforms separate until each has an
  explicit review and evidence contract.
- Add bounded note insertion, release velocity and continuous expression only
  after stable identity and GarageBand evidence exist.
- Add phrase alternatives/replacement, repeated-phrase reuse, split/merge and
  broader piano-roll editing without hiding a minimal reversible diff.
- Retain source-waveform/F0 and hummed-guide correction, quantisation and
  theory-assisted repair as explicit later operations, never hidden automatic
  cleanup.
- Add explicit hybrid construction only after the open Phase 5.3 gates close.
- Add cross-project stem/MIDI mashup preparation and eligible Instrument Bundle
  attachment to reviewed reusable parts.

### Phase 7

- Test exact exports in other DAWs and invite contributors to report
  compatibility against versioned fixtures.
- Publish only rights-cleared golden audio/MIDI/reviews with explicit licences
  and retention rules.
- Add explicit-consent, preview-before-send contextual feedback ingestion;
  ordinary projects remain local and private.
- Publish role/process/version scorecards and regression evidence before using
  feedback to change audition ordering.
- Consider a small independent candidate selector or note-error classifier
  only after a rights-qualified immutable dataset, held-out goldens and a
  participant-leakage test exist. Popularity must never override the user's
  choice.

## Next implementation increments

The next safe order is:

1. exercise the initial full-project runner on mixed real projects and retain
   explicit near-silent/proxy/vocal outcomes;
2. add the durable owner-only ledger and restart recovery only after that
   single job is reliable;
3. add one-stem and standalone-vocal forms, then common transformations;
4. connect verified completed jobs to the 5.10c Workbench journey; and
5. design 5.10d local feedback against real user reviews before defining any
   opt-in Phase 7 contribution format.

Each increment must keep the CLI usable by itself, keep the agent skill current
with the same public interface contract, and leave the repository in a state
where an interrupted TUI cannot corrupt evidence or durable choices.
