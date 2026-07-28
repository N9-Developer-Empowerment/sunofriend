# Product modes and the hosted future

Status: Simple and Studio are local alpha experiences. Hosted processing,
accounts and payment are product plans, not implemented services.

## Product goal

Sunofriend should help two kinds of musician without splitting into two
different audio engines:

1. A person who wants to provide stems, choose one clear action and receive
   useful MIDI plus a listenable WAV.
2. A person who wants to understand, compare and improve how that result was
   made.

Both journeys use the same production conversion and rendering services.
Simple is a safe automatic projection of those services. Studio exposes the
evidence and human decisions.

The two experiences are not separate applications. A visible switch in the TUI
moves between **Simple · Make my song** and **Studio · Compare & improve** at
any time, with `F2` and `F3` as keyboard alternatives. Returning to Studio
restores its last open tab. The switch is memory-only navigation: it starts no
conversion or render, writes no feedback or review, and changes no MIDI,
selection, pack or export state. `--mode` chooses only the first view at
launch.

This distinction lets Sunofriend remain approachable without losing its main
advantage: it can preserve several analytical, tracker, AI and repair results
instead of hiding every stem behind one model answer.

## Simple mode

Simple mode is the default `sunofriend tui` experience.

### Input

- One local folder of top-level WAV stems.
- Key, BPM and tuning in the folder name.
- An optional metronome and chord PDF.
- One fresh output folder outside the source project.

### One-action journey

The user chooses **Create MIDI + WAV**. Sunofriend then:

1. validates the source and local capabilities;
2. runs the supported production instrumental and vocal conversion paths;
3. pairs each source role with the exact primary MIDI published by its
   production summary;
4. omits ambiguous, missing, silent, diagnostic-only or unsafe pairings;
5. copies the paired MIDI without changing its notes;
6. builds a combined General MIDI interpretation;
7. renders a source-referenced balanced MIDI WAV; and
8. creates a plain-English receipt and starter ZIP.

Progress uses a small fixed set of phases. Cancellation stops conversion at a
safe boundary and keeps partial evidence without calling it success.

### Selection contract

Simple mode does not:

- score every available candidate and invent a global winner;
- convert an automated metric into a preference;
- write a Workbench human-decision event;
- claim that the user reviewed or accepted a part;
- mutate source stems or source MIDI; or
- hide a failed role behind a successful project count.

It uses only the primary result explicitly published by each production
process. The receipt says:

- `review_status: not_reviewed`;
- `quality_status: review_recommended`;
- `automatic_selection: true`;
- `automatic_ranking: false`; and
- `human_decision_events: 0`.

The source and MIDI hashes are checked before and after rendering.

### Output contract

The `AUTOMATIC-SONG` result contains:

- individual exact automatic-primary MIDI files;
- one combined General MIDI interpretation;
- one balanced MIDI-derived song-interpretation WAV;
- a GarageBand fader recipe;
- technical mix evidence;
- a path-free result receipt;
- `START-HERE.txt`; and
- one deterministic ZIP.

The WAV contains rendered MIDI only. Source audio supplies timing, song
horizon and relative-level evidence but is not mixed into it. The renderer
uses the existing source-referenced gain policy, same-source group
calibration, drum-bus guard, audition normalisation and sample-peak
protection.

It is labelled `mastered: false` and `release_master: false`. It is a useful
creative interpretation and arrangement reference, not waveform
reconstruction or human release approval.

### Feedback contract

Simple creation records no listening feedback. Playback, progress and file
creation are not treated as preference.

A later beginner-friendly feedback form may ask whether the result completed,
imported, sounded useful and which role needs work. That must be explicit,
optional and separate from MIDI selection. It must not infer a preference from
play count, dwell time, downloads or an unclicked default.

## Studio mode

Studio starts with:

```bash
sunofriend tui --mode studio
```

It is for deliberate comparison, correction and handoff.

### What Studio adds

- Read-only project and candidate orientation in the TUI.
- Explicit full-project conversion into a fresh result root.
- A loopback-only browser Workbench.
- Source waveform and unchanged MIDI note timelines.
- Short level-assisted source/candidate switching on one decoded clock.
- Bounded selected-arrangement and full-song playback.
- Explicit main, optional, needs-correction, reject and no-usable-result
  decisions.
- Private listening notes and structured feedback.
- Fixed-MIDI bass and keys instrument comparisons.
- A reviewed balanced interpretation and optional separate Listening Master
  challenger.
- A separate exact GarageBand pack basket and export.
- A read-only application-level Developer Inspector.
- Gated reusable Clip browsing, transformation and bounded corrections.

Studio preserves every method's identity. Technical scores, agreement,
execution speed and model labels are evidence, not preference.

### Saved and temporary state

Explicit decisions, pack choices and supported review responses can survive a
restart in private local state.

Playheads, loops, zoom, visibility, mute, solo, temporary gain, decoded audio
and prepared chunks are browser audition state. They reset and never silently
become decisions or feedback.

### Reviewed output

Only explicit active main and optional choices enter the reviewed arrangement.
Rejected, needs-correction, superseded and unreviewed candidates stay out.

The reviewed GarageBand pack is separate from the Simple ZIP. It includes
exact selected MIDI by default. Source audio requires an explicit rights-aware
opt-in.

## Moving between the modes

The modes are not competing products.

- Start in Simple to get a useful first interpretation quickly.
- Open the same source and result root in Studio when one role is weak, an
  instrument needs comparison, or a reviewed GarageBand pack matters.
- A Studio user can still use the automatic bundle as a neutral starting
  reference.
- Studio decisions do not rewrite the earlier Simple receipt.
- A Simple result must never be renamed or displayed as reviewed after a user
  merely opens it.

The command line and agent skill remain expert orchestration routes over the
same services.

## Beginner usability release gate

The Simple implementation is an engineering milestone, not yet proof that a
new musician can install and use Sunofriend unaided.

Before presenting it publicly as easy for non-technical users, run a small
clean-machine acceptance programme. Give each participant only:

- the repository or packaged-app link;
- the beginner getting-started page;
- their own authorised stem folder; and
- the issue/feedback link.

Collect explicit answers to:

1. Could they install without live developer intervention?
2. Did the capability checks explain any missing component?
3. Did the app recognise their folder and roles?
4. Did **Create MIDI + WAV** finish?
5. Could they find and play the WAV?
6. Could they find and import the MIDI at the correct BPM?
7. Did the WAV help them understand or reuse the song?
8. Which stem roles were useful or weak?
9. Did they understand that the automatic result was unreviewed?
10. Would they use it again, and in which DAW?

Record the Sunofriend version, macOS version, Mac architecture, source
duration, stem-role list, elapsed time and DAW. Do not collect source audio,
private notes or identifiable filenames unless the participant separately
chooses to share them.

Until independent users complete that path, social posts should describe
Sunofriend as a local alpha seeking musicians and DAW testers rather than as a
finished one-click consumer product.

## Packaging work before hosting

The current clone-and-venv setup is still technical. The local product should
progress through:

1. a stable versioned release and migration notes;
2. a reproducible end-user package that does not require an editable checkout;
3. signed/notarised macOS distribution when practical;
4. first-run dependency and SoundFont setup with clear licences;
5. a project picker and output reveal action;
6. resumable conversion jobs rather than only a preserved partial folder;
7. structured, opt-in beginner feedback; and
8. acceptance testing on clean Intel and Apple Silicon Macs plus other DAWs.

The TUI should remain useful for developers and remote terminals even if a
native desktop shell is added later.

## Why a hosted version may be needed

Local processing protects privacy and avoids a permanent infrastructure bill,
but it excludes people who:

- do not have a supported Mac;
- cannot install Python and audio dependencies;
- have limited CPU, memory or disk space;
- need a phone/tablet-friendly upload journey; or
- prefer to pay for an occasional conversion instead of maintaining a local
  ML environment.

A hosted edition could make Sunofriend available to those users. It would
change the privacy, rights, licensing, cost and security model, so it must be a
separate explicit product rather than a silent mode of the local app.

## Honest hosted architecture

Heavy audio transcription should not be described as a single
request-duration serverless function. Songs can take minutes, need substantial
memory and may require a GPU.

A practical hosted system separates the control plane from the compute plane.

### Serverless-friendly control plane

Short-lived API or serverless components can handle:

- authentication and account management;
- upload-session creation;
- job validation and idempotency keys;
- price estimates and payment authorization;
- queue submission;
- job status and progress;
- signed download links;
- deletion requests;
- structured feedback; and
- notifications.

A durable database stores job state, consent, receipts, payment state and
non-audio feedback. It must not rely on an in-memory web process.

### Queued compute plane

Conversion and rendering should run in isolated queued CPU/GPU workers:

- container images pin the Sunofriend, Python and model environments;
- a scheduler selects CPU, Apple-compatible alternative or GPU worker classes;
- each job gets an isolated temporary workspace;
- workers read only the authorised job inputs;
- progress and safe checkpoints are written to durable job state;
- exact model, code, source and output hashes enter the receipt;
- failed or cancelled workers clean up temporary files; and
- workers scale to zero or a small warm pool according to demand.

Long CPU/GPU workers may be supplied by a container service, batch platform or
specialised inference provider. Calling the API layer “serverless” must not
hide these persistent compute costs.

### Encrypted object storage

Uploaded stems and generated files need encrypted object storage rather than a
web-server disk:

- short-lived signed upload and download URLs;
- private buckets with no public listing;
- per-job object prefixes and access boundaries;
- explicit retention periods visible before upload;
- automatic deletion after the chosen period;
- immediate user-initiated deletion;
- encrypted backups only when declared; and
- audit evidence that deletion and lifecycle rules ran.

The default should retain audio only long enough to finish and let the user
download the result. Keeping projects for reuse should be a separate opt-in.

### Browser experience

The hosted browser can reuse Sunofriend's approachable result ideas:

- upload stems and confirm detected roles;
- show job stages and realistic time/cost;
- play source, MIDI renders and prepared mixes;
- compare several methods without exposing raw internal complexity first;
- choose the MIDI included in a DAW ZIP; and
- offer an advanced technical view when requested.

The local Workbench cannot simply be exposed to the internet. Its loopback
token, local-path and trust assumptions must be replaced by authenticated,
authorised, multi-tenant APIs with strict object scopes and request limits.

## Payment per conversion

Per-transaction payment fits occasional music use better than requiring a
subscription, but billing must be predictable.

A safe flow is:

1. inspect file count, duration and requested processing tier without running
   the expensive job;
2. display a maximum price and expected range;
3. authorise, but do not necessarily capture, that amount;
4. run one idempotent job;
5. meter declared billable dimensions such as audio minutes, stem count and
   optional GPU/model tier;
6. capture no more than the accepted maximum;
7. automatically release or refund failed platform work; and
8. show a receipt alongside the technical result.

Retries caused by the platform must not create duplicate charges. User-requested
new settings should be a new clearly priced job. Free short previews or a
small first-song allowance can reduce the risk of paying before understanding
the product.

## Rights and model licensing

Commercial hosting needs a fresh dependency and asset audit.

- Users must confirm that they may upload and process the music.
- A right to process privately is not automatically a right to redistribute a
  stem, sample instrument or public example.
- Optional checkpoints with non-commercial terms cannot power a paid service
  without a separate commercial licence.
- Checkpoint terms and code licences must be audited independently.
- Models with unclear weight licences should remain disabled until resolved.
- Apple GarageBand sounds and factory samples must not be uploaded, copied or
  rendered on a generic server as though Sunofriend owned them.
- Hosted previews need redistributable SoundFonts or synthesizers with verified
  terms.
- Training or fine-tuning on user audio requires separate, specific consent.

The Apache-2.0 licence for Sunofriend's code does not override the licences of
music, checkpoints, SoundFonts, samples or external services.

## Privacy and feedback

The hosted product should make three choices separate:

1. upload audio for this conversion;
2. retain the project for later reuse; and
3. contribute feedback or artefacts to product improvement.

None should imply another.

Structured feedback can include role, chosen process, correction category,
DAW, import success and a usefulness rating. Audio, MIDI, private notes and
filenames should stay excluded from shared analytics by default. If a user
offers an excerpt for research, show exactly what will be sent, for what
purpose, for how long and whether it may train a model.

Users should be able to export and delete their feedback. Aggregate popularity
can help order future audition options, but it must not silently replace
role-specific listening or turn one community favourite into ground truth.

## Proposed delivery stages

### Stage A: local beginner proof

- Stabilise Simple mode.
- Complete clean-machine musician tests.
- Fix installation, role-detection and output-discovery problems.
- Keep Studio and the CLI available for diagnosis.

### Stage B: packaged local release

- Publish a versioned end-user package.
- Add first-run setup and resumable jobs.
- Collect explicit, local-first usability evidence.

### Stage C: service boundary

- Define a path-free job request, immutable input manifest, progress events,
  cancellation contract and deterministic result receipt.
- Run that protocol locally against a queued worker before adding accounts or
  payment.
- Separate redistributable production dependencies from private experimental
  models.

### Stage D: private hosted pilot

- Use invited users and short authorised songs.
- Set strict duration, stem, storage and cost limits.
- Exercise deletion, failure, retry, refund and support paths.
- Test several DAWs, browsers and lower-powered client devices.

### Stage E: paid public service

- Open only after security, privacy, rights, licence, accessibility, support
  and unit-economics reviews.
- Publish clear price, retention and model disclosures.
- Keep local Sunofriend available for users who prefer private processing.

## Success measures

Product success is not only note-detection accuracy.

Measure:

- install or upload completion;
- time to first playable interpretation;
- percentage of supported roles with a safe primary;
- MIDI import success and correct BPM in each DAW;
- cancellation and retry recovery;
- whether the balanced WAV helps the musician understand the song;
- which roles require Studio correction;
- explicit process choices by role and context;
- repeat use; and
- privacy, deletion, billing and support failures.

Musical quality still needs listening. A popular option, low model loss,
high note overlap or fast worker is not automatically the best interpretation.
