# Guided Local Studio TUI

Status: default Simple automatic MIDI + balanced-WAV bundle implemented;
Studio orientation, full-project conversion, Workbench bridge and native
Listening Master operation implemented; wider guided operations, durable job
recovery and broader feedback remain planned; Source Import S1 folder
preparation is available separately in the CLI.

Interface contract: `2026-07-29.3`

The Guided Local Studio is the preferred human entry point to Sunofriend. It
puts a clear terminal dashboard in front of the deterministic CLI and provides
two experiences over the same production engines:

- **Simple**, the default, accepts one stem folder and one fresh output, then
  creates automatic-primary MIDI, a combined MIDI, a balanced MIDI-derived WAV
  and a starter ZIP without requiring a technical review.
- **Studio** exposes project state, explicit conversion, several unchanged
  MIDI alternatives, local diagnostics and the existing graphical Workbench
  for detailed listening, decisions, the Developer Inspector and a reviewed
  GarageBand export.

The persistent **Simple · Make my song** and
**Studio · Compare & improve** controls switch between these experiences in
either direction. `F2` opens Simple; `F3` returns to the last Studio tab.
Changing mode is memory-only navigation and starts no process, writes no
review or feedback, and changes no MIDI, selection, pack or export state.
`--mode` selects only the initial view.

Simple has a separate `sunofriend.simple-result.v1` receipt. Its automatic
parts are explicitly `not_reviewed` and `review_recommended`; it writes no
Workbench decision or feedback. Studio's reviewed product journey produces
editable selected MIDI and a MIDI-derived song-interpretation WAV under the
versioned product definition from `product_contract.py`. The two journeys
reuse the same conversion, neutral rendering and balance policies rather than
reimplementing audio or MIDI work in Textual callbacks.

Workbench can create a separate fixed-policy Listening Master challenger from
the exact current balanced control. The TUI **Master** tab exposes the same
shared application service directly, while **Open visual studio** remains the
place to hear and download both versions and complete the bounded blind
level-matched control/challenger review.

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

The TUI source field still means a prepared folder of synchronized top-level
WAV stems. It never imports files or runs stem separation as a side effect of
loading. If you already have 2–64 separated parts as supported WAV, AIFF,
FLAC, MP3, M4A or Ogg audio, prepare them first with:

```bash
sunofriend source-doctor
sunofriend source-import-folder SOURCE_FOLDER --out-dir FRESH_OUTPUT --plan
sunofriend source-import-folder SOURCE_FOLDER --out-dir FRESH_OUTPUT
sunofriend tui FRESH_OUTPUT
```

The doctor and plan are read-only. Folder import writes immutable originals,
per-source and aggregate receipts, one source-project manifest and canonical
top-level WAV stems. It does not split a finished song, shift, pad, stretch,
normalize or align files. A raw mixed-format folder is rejected with guidance
rather than imported automatically. `source-import` remains available when
you need to preserve one standalone asset rather than make a full TUI project.

## Start the Guided Local Studio

Start without arguments and enter the stem folder in the dashboard:

```bash
sunofriend tui
```

This opens the default **Make my song** tab. To open the detailed Studio
experience first:

```bash
sunofriend tui --mode studio
```

Or open one project and its existing result roots in Studio immediately:

```bash
sunofriend tui \
  "/absolute/path/to/Song-B minor-113bpm-440hz" \
  --mode studio \
  --candidate-root "/absolute/path/to/song-specialist-midi" \
  --candidate-root "/absolute/path/to/song-ai-midi"
```

The TUI accepts the same optional catalog, state and SoundFont inputs used by
the visual review path:

```bash
sunofriend tui "$PROJECT" \
  --mode studio \
  --candidate-root "$RESULTS" \
  --catalog "$WORKBENCH_CATALOG" \
  --state-dir "$PRIVATE_WORKBENCH_STATE" \
  --soundfont "$GM_SOUNDFONT"
```

Candidate roots may also be entered interactively, separated by semicolons.
Inside the TUI:

- the visible **Simple** and **Studio** buttons switch experiences;
- `F2` switches to Simple and `F3` returns to the last Studio tab;
- `Ctrl+R` refreshes the project projection;
- `F6` opens the visual Workbench without conflicting with path-field editing;
- `Ctrl+D` runs the local system check; and
- `Ctrl+Q` stops the owned Workbench process and exits.

### Make automatic MIDI and a balanced WAV

The default Simple journey needs only the source and one fresh output:

```bash
sunofriend tui \
  "/absolute/path/to/Song-B minor-113bpm-440hz"
```

The **Make my song** tab suggests a fresh sibling output. Check the source and
output paths, then choose **Create MIDI + WAV**. The TUI:

1. runs the production repair/variant conversion for supported instruments and
   the separate production vocal conversion for discovered vocals;
2. takes only the exact primary MIDI published by each completed production
   summary;
3. omits and reports ambiguous, silent, missing or diagnostic-only roles;
4. renders a combined General MIDI interpretation;
5. uses the existing source-referenced balance policy to create a MIDI-only
   song-interpretation WAV; and
6. publishes `AUTOMATIC-SONG/` with MIDI, WAV, receipt, recipe,
   `START-HERE.txt` and a deterministic ZIP.

This is automatic selection, not automatic ranking. It does not write a human
decision, mark a role reviewed or change Workbench feedback. The source audio
is measured for timing, horizon and relative level but is not mixed into the
WAV. The result is not a release master.

After completion, use **Open visual studio** when you want to compare
alternatives, replace a default or build a reviewed GarageBand pack. See
[Product modes and the hosted future](PRODUCT_MODES_AND_HOSTING.md) for the
complete Simple/Studio contract.

### Convert a complete Studio project into a separate output

Supply a project and prefill a destination that does not yet exist:

```bash
sunofriend tui \
  "/absolute/path/to/Song-B minor-113bpm-440hz" \
  --mode studio \
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

### Create or reuse the comparative Listening Master

The native **Master** tab operates only after the current selected MIDI has a
verified balanced v3 song-interpretation control:

1. Make and review the MIDI choices in Visual Studio.
2. Create the balanced song-interpretation WAV there.
3. Stop Visual Studio, refresh the same project in the TUI and open
   **Master**.
4. Read and tick the comparative-scope confirmation.
5. Choose **Create / reuse listening master**.
6. Open Visual Studio again and, when a bounded quality judgment is useful,
   prepare one exact 0.5–15 second blind window, explicitly complete the A/B
   response and optionally export it before resolving the identities.

The form deliberately has no source path, destination path, loudness target,
filter graph, FFmpeg option or release-master switch. It derives the current
selection and balanced-control identities from verified local state and calls
the same fixed-policy application service as Workbench. A verified
content-addressed cache hit is reusable without FFmpeg. Before a fresh build,
the runner performs a path-free SoundFile, FFmpeg and `loudnorm` capability
preflight.

The action rechecks both the selection-manifest and balanced-arrangement
manifest hashes before promotion. If either changed, it discards pending work
and asks for a refresh rather than publishing stale audio. It rereads both once
more immediately after promotion and refuses to report success if a separate
local Workbench changed them in that final gap; the old content-addressed cache
entry then remains non-current and is not presented as the project's result.
The operation
shows bounded phase progress and locks project, conversion and Visual Studio
controls while the synchronous FFmpeg work is protected. It offers no unsafe
pseudo-cancel: Quit waits briefly and is then explicitly deferred while the
operation remains active. This is distinct from full-project conversion,
whose child process has a real cancel contract.

Success shows whether the verified artifact was created or reused, bounded
loudness/true-peak evidence and the private PCM24 WAV and receipt paths. The
result is always `mastered: true` and `release_master: false`. Creating or
reusing it records no event, review, feedback or preference and changes no
MIDI, selection, ranking, default, required product status or GarageBand Pack.
Open Visual Studio afterwards for listening, downloads and the optional
bounded blind review. The TUI Master action itself still records no review.

The visual Workbench starts with its read-only Developer Inspector available by
default. Use `--no-developer-inspector` when the additional developer view is
not wanted:

```bash
sunofriend tui "$PROJECT" \
  --mode studio \
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
  --mode studio \
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

The default Simple experience provides:

1. One visible source-folder field and one required fresh-output field.
2. One **Create MIDI + WAV** action with six bounded progress phases.
3. Production `listen-all` and separate lead/backing `vocal-melody`
   orchestration without duplicating their transcription policy.
4. Exact pairing of verified sources to production-summary primaries.
5. A fail-closed omission list for missing, ambiguous, silent or
   diagnostic-only roles.
6. Exact individual MIDI copies, one combined General MIDI proxy, a
   source-referenced balanced WAV, a path-free receipt and a starter ZIP.
7. Explicit `not_reviewed`, `review_recommended`, `mastered: false` and
   `release_master: false` boundaries.
8. Safe cancellation during conversion and protected completion of any WAV
   verification already in progress.
9. Automatic reload of the completed result root so Studio can inspect it.
10. Zero Workbench decision, preference or feedback writes.

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
10. The **Master** tab verifies the exact current balanced control and creates
    or reuses its fixed-policy comparative challenger through the shared
    application service, with fresh-build dependency preflight, identity
    rechecks and bounded protected progress.

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
tests. After the subsequent conversion, correction, instrument and Simple-mode
increments, the complete suite passes 1,296, with the one existing third-party
`resampy`/`pkg_resources` deprecation warning.

## TUI, Workbench and Inspector boundary

The three interfaces have separate jobs:

| Surface | Purpose | State it may change |
| --- | --- | --- |
| Guided Local Studio TUI | Default one-action automatic MIDI/WAV bundle, Studio project orientation, explicit fresh full-project conversion, local diagnostics, fixed-policy Listening Master orchestration and safe Workbench launch | In-memory navigation/activity; **Create MIDI + WAV** may create one fresh conversion tree and separately labelled automatic bundle without review state; an explicitly confirmed Studio conversion may create one fresh output through the same production engines; an explicitly confirmed Master action may create/reuse one rebuildable private challenger; it may start, cancel and reap its conversion child or start/stop its Workbench child |
| Workbench | Waveforms, MIDI lanes, synchronized listening, explicit musical decisions, MIDI-derived song-interpretation WAV, optional fixed-policy Listening Master challenger, bounded blind quality review, gated identity-labelled native-level readiness review and GarageBand pack basket | Only explicit decision, blind-review completion, identity resolution, native-readiness completion, other review and basket actions are feedback/state writes; playback and views are temporary, while requested audio outputs are rebuildable artifacts with no preference effect |
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

The same visual boundary now includes **Choose instruments** for an active bass
or keys lane. The browser compares the role's fixed server-owned General MIDI
pair while holding the selected MIDI fixed: zero-based Synth Bass 1/2
programmes 38/39, or Electric Piano 1/2 programmes 4/5. Keys first requires
both hidden identities to pass the private representative
channel/pitch/soft-medium-strong velocity-bucket response probe; bass records
that coverage is `not_required`. A keys pass remains
`quality_status: review_required` and says nothing about pitch/octave
correctness, every velocity, chord/polyphonic clarity, tone/source similarity,
GarageBand equivalence or a preferred default.

The TUI does not duplicate the private preflight, blind players, programme
policy or resolver, accept programme numbers or infer a winner. It launches
the Workbench and reports only that the visual stage is available. The private
synthetic probe MIDI, blind path-free projection and all heard/choice evidence
remain in the separate local Workbench instrument-review boundary. Raw probe
audio is deleted after measurement and can be re-rendered from verified inputs.
Neither surface may change MIDI, selection, ranking, a mix, a pack or an
export as a side effect of this review.

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
- Simple's automatic-primary receipt is separate from append-only Workbench
  decisions. Creating or opening it cannot mark a role reviewed.
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

### Simple automatic result — implemented

The implemented slice makes **Make my song** the default tab. A lay user can
provide top-level stems and one fresh output, choose **Create MIDI + WAV**, see
bounded progress and receive exact MIDI, a combined General MIDI
interpretation, a balanced MIDI-only WAV and a ZIP without making technical
candidate decisions.

This engineering completion still needs independent clean-machine musician
testing before Sunofriend can claim that installation and first use are easy.
The acceptance questions and future packaging/hosted path are in
[Product modes and the hosted future](PRODUCT_MODES_AND_HOSTING.md).

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

### 5.10c — Guided project journey: started

Connect completed jobs to an explicit sequence:

1. verify generated evidence;
2. compare each stem in Workbench;
3. hear selected parts alone, against stems and in the arrangement;
4. create the MIDI-derived song-interpretation WAV and, when wanted, its
   separate fixed-policy Listening Master challenger in Workbench or the TUI
   **Master** tab;
5. optionally complete one exact-window blind control/challenger response and
   resolve its identities only as a separate explicit action;
6. inspect unresolved or failed candidates;
7. choose the GarageBand pack basket; and
8. run the existing tutorial, quiz and exact-pack acceptance checks.

The TUI will display durable progress derived from verified Workbench state and
job evidence, while rich playback and piano-roll interaction remain in the
browser. Navigation must not become a choice, and a visible default must not
become a winner.

The native Listening Master operation is implemented as the first narrow
5.10c orchestration slice. It retains the balanced v3 control, exposes no user
policy inputs and adds no inferred preference. The bounded blinded
control-versus-challenger feedback form is now implemented in the Workbench
opened by **Open visual studio**; it remains separate from the TUI Master
operation and from automatic promotion.

### 5.10d — Broader local feedback and full guided handoff: planned

Beyond the implemented bounded Listening Master A/B response, add structured,
user-initiated feedback for process usefulness, failure type, musical role,
phrase context, instrument choice and GarageBand outcome. The local record will
pin exact versions and candidate hashes, retain valid `equivalent`, `neither`,
`none usable` and `cannot tell` outcomes, and stay separate from audition
history. It may improve local ordering of what to hear first, but must not
mutate evidence or select a candidate automatically.

The TUI will also guide eligible Phase 6 Clip actions and exact handoff
artifacts only as their existing review-before-write contracts become
available. Exporting or contributing feedback will remain a separate explicit
action with a path-free disclosure preview. No general TUI feedback collection,
automatic learning or network contribution is implemented. The existing
Workbench keeps only its explicit, bounded local review records.

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

1. exercise Simple mode with independent musicians on clean Macs, recording
   install, recognition, completion, output discovery, DAW import and musical
   usefulness without collecting their audio by default;
2. fix the resulting setup and first-run problems before claiming one-click
   consumer usability;
3. exercise the full-project runner on mixed real projects and retain
   explicit near-silent/proxy/vocal outcomes;
4. add the durable owner-only ledger and restart recovery only after that
   single job is reliable;
5. add one-stem and standalone-vocal forms, then common transformations;
6. connect verified completed jobs to the 5.10c Workbench journey; and
7. design 5.10d local feedback against real user reviews before defining any
   opt-in Phase 7 contribution format.

Each increment must keep the CLI usable by itself, keep the agent skill current
with the same public interface contract, and leave the repository in a state
where an interrupted TUI cannot corrupt evidence or durable choices.

Packaging and any future paid hosted service follow the separate control-plane,
queued-worker, storage, privacy, licensing and payment plan in
[Product modes and the hosted future](PRODUCT_MODES_AND_HOSTING.md).
