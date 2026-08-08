---
name: sunofriend
description: Guide local Sunofriend setup and use. Optionally separate one authorised finished mix into experimental broad vocals and instrumental, or an available opt-in vocals/drums/bass/grouped-other preview, on a supported Apple-silicon Mac; alternatively prepare 2–64 existing stems, then create editable MIDI, a balanced MIDI-derived song-interpretation WAV and ZIP. Offer a copyright-safe demo; use Simple for automatic unreviewed results and Studio for multi-method comparison, feedback and GarageBand handoff. Also handle vocal melody, instruments, key/BPM/tuning/alignment transforms, mashups, Clip v1 reuse and bounded correction. Use for Sunofriend, local experimental separation, stems-to-MIDI, song interpolation, GarageBand, MIDI comparison, tempo/key changes and stem-derived instruments. Do not download music, upload private audio, use unpinned separator models, write lyrics, edit a DAW GUI, claim human-approved release mastering or install dependencies/models without explicit approval.
---

<!-- sunofriend-interface-contract: 2026-08-08.3 -->

# Sunofriend

**Listen deeper. Create further.**

Sunofriend turns useful separated song parts into editable MIDI, named starter
sounds and a balanced MIDI-derived WAV. It preserves several analytical,
repaired and optional local-AI interpretations because a different method can
work best for each instrument or phrase.

The name comes from Hindi **सुनो** (*suno*), “listen.” Sunofriend is an
independent Unsigned Media Ltd project and is not related to or affiliated
with Suno Inc.

## Begin with the person

For a newcomer or imprecise request:

1. Explain the outcome in one sentence: editable MIDI, a listening WAV and a
   ZIP, made locally after useful stems exist.
2. Ask one question at a time.
3. Offer exactly four choices:
   - **Try the built-in demo**
   - **Start with one finished song (experimental local separation)**
   - **Use separate audio parts (stems) I already have**
   - **Help me get stems I am allowed to process**
4. Recommend the demo when the person is unsure.
5. Do not begin with model names, Python, Homebrew or the full command list.
6. Do not claim an ordinary browser chat can control the Mac. Hands-on work
   requires a coding agent with local workspace and terminal access.

Explain one next action, perform or prepare it, report the result, then move
on.

## Preserve the product boundary

- Keep music, MIDI, chord files, reviews and private notes local. Never upload
  them or attach them to a public issue.
- Process only music the user owns or is authorised to process. Sunofriend
  never downloads songs or grants processing rights.
- The opt-in public separator accepts one local finished mix. Broad `vocals`
  plus complementary `instrumental` remains the default. The separately
  selectable core-four profile estimates `vocals`, `drums`, `bass` and grouped
  `other` only when `sunofriend-separate profiles` reports it `public_opt_in`.
  Neither route is ground truth or activates output for MIDI automatically.
- `other-refinement-v1` is an opt-in Studio challenger. It binds one exact
  SCNet grouped-`other` parent to either one guitar target or one keys target
  plus the exact residual. The separately installed
  `demucs-mlx-htdemucs-6s-other-refinement-v1` passed its one allowed loader
  remediation and bounded offline gates; `keys` is explicitly a piano proxy,
  not general keyboard isolation. Planning is read-only, execution requires
  `--execute --confirm-rights`, and neither result is selected automatically.
  Never put both the parent and its children into MIDI.
  The completed fixed five-song, ten-report review demonstrated neither useful
  guitar extraction nor successful piano extraction. Keep the technically
  valid profile reproducible in Studio, but do not promote it, describe it as
  a working guitar/keys capability or send it to MIDI. The next read-only
  candidate is documented in `docs/OTHER_REFINEMENT_QUERY_CHALLENGER_PLAN.md`; it
  targets guitar plus broad `keyboard_synth`. Its approved evidence-only
  checkpoint download and static inspection did not themselves grant model
  loading, inference or audio processing. The completed source audit found
  a second required 341,546,630-byte OpenMIC PaSST checkpoint and forbids both
  upstream automatic/unrestricted loaders. Use
  `scripts/plan-separation-other-refinement-query-runtime.py` for the current
  no-effects gate. Its separately approved evidence-only download established
  SHA-256
  `dc229428753176e8be0373d25887116fc15b490af86f671cecf9ed76a0f287da`
  without loading it. A separately approved evidence-only dependency step
  resolved and hashed 28 exact CPython-3.12/macOS-arm64 wheels under a 1 GiB
  cap. Their 99,354,620-byte closure and licence metadata were inspected under
  network denial without installation or import; the committed lock SHA-256 is
  `28249f5d6ab80d4b72a5f256ac435f3a2d150b1baa30d751754af44049c33b92`.
  A later separately approved gate installed those exact wheels into a fresh
  CPython 3.12.10/macOS-arm64 environment and imported the eight relevant
  modules under network denial. It recorded zero network attempts, checkpoint
  opens, `torch.load` calls and audio opens. A later explicit approval completed
  the restricted construction/load gate: the real 64-band adapter and both
  download-disabled PaSST variants matched all 1,228 combined checkpoint keys,
  shapes and dtypes before strict loading, with no missing or unexpected keys,
  network or audio access. No inference ran. Do not run a forward pass, process
  audio, activate a source or create MIDI without a new reviewed plan and
  explicit approval.
- `source-import` prepares one local audio asset. `source-import-folder`
  prepares 2–64 existing separated parts. Neither command separates, aligns,
  pads, stretches or normalizes audio.
- The balanced WAV contains rendered MIDI. The source stems provide timing,
  horizon and relative-level evidence but are not mixed into it.
- Call the WAV a **MIDI-derived song interpretation**, not an exact
  reconstruction or a human-approved release master.
- Playback, metrics, scores and visible defaults never imply preference.
- Use a fresh output outside the source folder. Do not overwrite unless the
  user explicitly requests it and the command supports it safely.
- Never install a dependency, checkpoint, plug-in or instrument without the
  user's explicit approval and the applicable licence check.

For historical separation experiments, optional AI methods and expert
commands, read the references only when relevant:

- [Public interface contract](references/interface-contract.md)
- [Advanced operations and research history](references/advanced-operations.md)

The active public separation guide is `docs/STEM_SEPARATION_ALPHA.md`.
The exact four-stem implementation and bounded activation route is
`docs/FULL_STEM_SEPARATION_PLAN.md`. `sunofriend-separate profiles` reports
its immutable backend and current status. Do not bypass a `blocked` profile.
The MLX baseline exhausted its one-remediation budget; do not reinstall or
retry it. `docs/CORE_FOUR_FALLBACK_AUDIT.md` and
`scripts/setup-separation-core-four-fallback-macos.sh --plan` describe the
exact `demucs-infer` fallback. Its first approved setup failed safely at the
hash lock; the revised 20-wheel install passed doctor, but the synthetic worker
then rejected the native `Fraction(39, 5)` segment before publication. Its
remediation is exhausted: do not reinstall, patch or rerun it.
`docs/CORE_FOUR_SCNET_AUDIT.md` and
`scripts/plan-separation-core-four-scnet.py` describe the installed public
opt-in profile. An explicitly approved evidence-only download established a
168,848,417-byte checkpoint with SHA-256
`719e5abb8ed920305dad546ac3cd6fb0b1e9c3092d14ce21827bfc0423af3070`;
the disclosed repository MIT metadata plus README link was accepted as
sufficient provisional preview evidence. The approved 264,851,903-byte setup
installed 12 hash-locked wheels and passed an offline weights-only strict
compatibility inspection after the one allowed official `best_state` wrapper
remediation. A real network-denied 60-second mathematical canary, three
authorised song-disjoint canaries and three repeat resource runs passed the
objective gates. Every full-song output received the required
catastrophic-output listen with no defect reported. The first verified machine
class is a 36 GB M3 Max; 16 GiB and other Apple-silicon machines remain
accessible but unverified and resource-supervised. Poor musical quality is a
limitation, not a preview veto. Do not reinstall or mutate the profile, use
personal audio without rights confirmation or enter MIDI/Create automatically.
Preview admission uses objective licensing, privacy, integrity, runtime and
output gates; poor musical feedback is recorded and must not create an
unlimited pre-release tuning loop.
Historical statements in the advanced record do not override this contract.

The model-free synthetic contract can be checked by a developer with a fresh
output directory:

```bash
.venv/bin/python scripts/run-other-refinement-synthetic.py \
  --target guitar --out "/absolute/path/to/fresh-other-refinement-fixture"
```

This creates only deterministic oscillator PCM24 evidence. It is not approval
to download or install a target-separation model and it does not activate a
source-graph child.

The first challenger can be inspected without side effects using:

```bash
scripts/setup-separation-other-refinement-demucs-mlx-macos.sh --plan
```

Do not run its `--install` route until the user explicitly accepts both the
displayed model terms and checkpoint use. Setup alone does not grant model
construction, inference, private-audio processing, source activation or MIDI.
After setup, a user can explicitly plan one bound Studio run with:

```bash
.venv/bin/sunofriend-separate refine-other \
  "/absolute/path/to/core-four-separation" \
  --target guitar --out "/absolute/path/to/fresh-candidate"
```

Only add `--execute --confirm-rights` when the user approves execution for that
authorised parent. Present the local listening page afterward. Do not choose
the parent or children, activate a source graph, or create MIDI until the
musician makes that later musical choice.

After the musician genuinely exports the page JSON, bind it without activating
anything:

```bash
.venv/bin/sunofriend-separate review-other \
  "/absolute/path/to/refinement-result" \
  "/absolute/path/to/review-export.json" \
  --out "/absolute/path/to/fresh-private-feedback.json"
```

The command accepts the original compact v1 page as legacy evidence, but marks
its missing issue dimensions as not recorded rather than as passes. It must
not infer a source or MIDI choice from usefulness or notes.

For cross-song guitar/keys development, use the fixed definition in
`stem_examples/other-refinement-evaluation-v1.json` and inspect the no-write
plan first:

```bash
.venv/bin/python scripts/create-other-refinement-corpus-review.py --plan
```

It caps the first round at five authorised songs and ten frozen 15-second
cases under one configuration. Moises and Suno stems are local comparison
estimates, never truth; `keys` remains the model's piano proxy. Prepare and
serve only after the ten execution roots exist, and use the bundle `--record`
route only after all ten listens. Negative feedback is valid evidence and
must not trigger configuration tuning, profile pause, source selection or
MIDI activation.

Inspect the next no-effects query-challenger plan with:

```bash
.venv/bin/python scripts/plan-separation-other-refinement-query-runtime.py
```

It records Banquet under a CC BY-NC-SA 4.0 local-noncommercial boundary. The
approved capped evidence-only download established the exact checkpoint
SHA-256 and a network-denied, non-deserializing opcode report. The later
restricted load approval authorized only construction and strict weights-only
loading; it did not authorize model inference, private-song processing, public
activation, source selection or MIDI. Require a new reviewed plan and explicit
approval before any of those actions. The
audit found and separately inspected the second required OpenMIC PaSST
checkpoint, establishing SHA-256
`dc229428753176e8be0373d25887116fc15b490af86f671cecf9ed76a0f287da`
  without loading it. Both model-artifact identities and the 28-wheel runtime
  hash closure are complete. A separately approved isolated gate installed the
  closure from the local cache and verified the relevant imports under network
  denial. The approved restricted loader then constructed PaSST with
  `pretrained=False`, verified every state key, shape and dtype and strictly
  loaded both checkpoints under network denial. Do not use the upstream
  downloader or loader, run inference or process audio until a new synthetic
  inference plan is reviewed and explicitly approved.

## Inspect before installing

Resolve the application in this order:

1. `sunofriend` on `PATH`;
2. `.venv/bin/sunofriend` in the current workspace or a repository the user
   supplied;
3. `~/.local/share/sunofriend/app/.venv/bin/sunofriend`.

Do not scan the whole home directory. Ask for the location if those bounded
checks fail. Run `sunofriend --version`; do not replace an existing checkout
just because another exists.

If the app or core audio tools are missing, resolve
`scripts/bootstrap-macos.sh` relative to this skill:

1. Run `--plan` without changing the Mac.
2. Explain each network destination, package, disk estimate and licence.
3. If source is absent, ask before `--prepare --yes`. This installs nothing.
4. Run `--plan` again and show the exact 40-character commit.
5. Ask separately before
   `--apply --expected-revision COMMIT --yes`.
6. Report a blocked prerequisite instead of improvising around it.

Apply never fetches or switches the prepared checkout. The helper can install
Python 3.11, FluidSynth, the constrained local app and the pinned GeneralUser
GS SoundFont, but it does not install Homebrew or optional AI models. Explain
that FluidSynth renders MIDI, the SoundFont supplies neutral preview sounds,
and the SHA-256 check verifies the exact reviewed asset.

Run the resolved executable, shown below as `SUNOFRIEND`:

```bash
SUNOFRIEND doctor --require convert
SUNOFRIEND doctor --require preview
```

Do not ask a newcomer to substitute executable placeholders manually.
FFmpeg/FFprobe are separate optional prerequisites for source import. Run
`source-doctor` first and ask before installing or upgrading either tool.

## Route A: built-in demo

Use the demo when the person has no stems or wants a quick, copyright-safe
proof. Read `demo --help`, choose a fresh output, then run:

```bash
SUNOFRIEND demo --out-dir "/absolute/fresh/demo-output"
```

The command creates synthetic stems and uses the normal production pipeline.
Show the balanced WAV first, then `START-HERE.txt`, the individual MIDI and the
ZIP. Explain that it proves the workflow, not accuracy on every real song.

## Route B: one finished song through the public alpha

Use this only when the person wants to estimate stems from one local song they
may process. Explain before setup:

- Apple-silicon macOS is the first supported platform;
- setup downloads about 500 MB of pinned MIT model/runtime material;
- inference then stays local with offline model settings;
- broad vocals and instrumental is the default; core four is explicit opt-in
  only when its profile is available, and grouped other is not one instrument;
- full songs can take several minutes; and
- output remains unreviewed until the musician listens.

Read `docs/STEM_SEPARATION_ALPHA.md` and run
`.venv/bin/sunofriend-separate profiles` before choosing a scope. If
`demucs-mlx-htdemucs-v1` is `blocked`, do not attempt core-four execution or
silently substitute a model. Its read-only setup plan is:

```bash
scripts/setup-separation-core-four-macos.sh --plan
```

That plan installs nothing and now refuses new installs because the MLX
baseline exhausted its objective remediation budget. Do not retry the
activation canary or patch the loaded segment again. The exact fallback plan is:

```bash
scripts/setup-separation-core-four-fallback-macos.sh --plan
```

It pins a PyTorch CPU runtime and discloses that the original checkpoint has no
separate model-specific licence file. It now reports the objective synthetic
failure and refuses new installs. A different backend needs a new reviewed plan
and separate explicit approval; do not infer either from an ordinary request.

The current read-only SCNet profile plan is:

```bash
.venv/bin/python scripts/plan-separation-core-four-scnet.py
```

It deliberately changes nothing. Compatibility, synthetic, authorised-song,
resource and catastrophic-listen evidence are complete, and the immutable
profile is admitted as `public_opt_in`.

The completed private approval and canary records are local evidence and must
not be attached to public issues. For a future profile, the local approval page
remains available through `scripts/create-core-four-approval-page.py --out
FRESH --synthetic-root SYNTHETIC --open`; validate its JSON with the same
script's `--validate JSON` route before treating it as authority.

The reviewed SCNet setup boundary is:

```bash
scripts/setup-separation-core-four-scnet-macos.sh --plan
```

It is read-only. A later approved install requires a fresh profile root and
refuses to overwrite an existing profile. The setup selects the checkpoint
publication revision as an immutable profile, preserves the earlier
current-source candidate, permits no forward pass or audio read during
compatibility inspection, and uses its single transparent wrapper remediation.

After the user reviews the plan and explicitly accepts both the model terms and
checkpoint use, the install command is:

```bash
scripts/setup-separation-core-four-scnet-macos.sh \
  --install --accept-model-terms --accept-checkpoint-use
```

It now refuses to overwrite the existing profile. Local synthetic execution is
separately bounded by
`scripts/run-separation-core-four-scnet-synthetic.py`; do not use that route to
bypass per-song rights confirmation or public status.

For the default broad route, resolve
`scripts/setup-separation-alpha-macos.sh` relative to the application checkout,
not the current shell directory. Inspect setup first:

```bash
scripts/setup-separation-alpha-macos.sh --plan
```

The plan writes nothing. Explain the pinned model terms and ask explicitly
before:

```bash
scripts/setup-separation-alpha-macos.sh --install --accept-model-terms
```

Do not infer model approval from a request to separate a song. Resolve the
matching `sunofriend-separate` executable and run its read-only doctor:

```bash
.venv/bin/sunofriend-separate doctor
```

Create a fresh output outside the source. Plan with the accurate rights
category (`owned`, `licensed`, `authorised_private_use` or
`statutory_exception`):

```bash
.venv/bin/sunofriend-separate separate "/absolute/path/to/song.wav" \
  --out "/absolute/path/to/fresh-separation" \
  --rights-category owned
```

When and only when the profile reports `public_opt_in`, select core four
explicitly and use its matching doctor/setup:

```bash
.venv/bin/sunofriend-separate doctor --scope core-four-stems-v1
.venv/bin/sunofriend-separate separate "/absolute/path/to/song.wav" \
  --scope core-four-stems-v1 \
  --out "/absolute/path/to/fresh-core-four-separation" \
  --rights-category owned
```

Explain the source hash, duration, output, space requirement and limits. Ask
for a separate rights confirmation before executing:

```bash
.venv/bin/sunofriend-separate separate "/absolute/path/to/song.wav" \
  --out "/absolute/path/to/fresh-separation" \
  --rights-category owned \
  --execute --confirm-rights --open-review
```

Open `REVIEW/separation_review.html`. Ask the musician to hear source, vocals,
every declared stem role and reconstruction. A close reconstruction proves
additive PCM accounting, not correct assignment. The review accepts poor,
`cannot_tell` and `not_tested` results. Use Copy text-only feedback; never
upload audio, review JSON, telemetry, filenames or private metadata
automatically.

If the stems are useful, copy them into a new folder and continue with Route
C. Never silently start MIDI conversion, promote a model or generalise one
review into a default.

## Route C: stems the user already has

Inventory the folder read-only. Confirm:

- 2–64 top-level audio parts exist;
- key and BPM are known or parseable from the folder name;
- useful role words exist, such as `kick`, `snare`, `hat`, `bass`, `keys`,
  `strings`, `lead`, `vocals` or `backing vocals`;
- chord PDF and metronome files are identified as optional evidence; and
- the proposed output is fresh and outside the source.

Use an already compatible synchronized top-level WAV project directly. If
existing parts need preparation, read the command help, then run:

```bash
SUNOFRIEND source-doctor
SUNOFRIEND source-import-folder "/absolute/path/to/source-parts" \
  --out-dir "/absolute/path/to/fresh-prepared-project" \
  --rights-category authorised_private_use \
  --plan
```

Doctor and plan are read-only. Explain inferred roles, origin status, warnings
and outputs. Ask before executing without `--plan`; execution replans current
inputs, so plan again after any file, role map or option changes.

For ambiguous names, a role map is a flat JSON object keyed by exact filename.
Do not guess. `hats` normalizes to `hat`, guitars to `rhythm`, and percussion
to `other_kit`; only `vocals` and `backing_vocals` may repeat. Do not invent an
observed `pads` role. Map only a genuinely string-like sustained part to
`strings`; otherwise leave it unresolved.

If origin is `unconfirmed`, explain that the container lacks concrete origin
evidence. Never silently add `--accept-unconfirmed-origin`; it acknowledges
uncertainty but does not prove alignment. A concrete origin conflict blocks
execution. Different endings are warnings and are not silently padded.

A composite `drums` part can produce review-required MIDI through the mixed-kit
family classifier, but layered hits can collapse and no child audio files are
made. Explicit viable drum-family sources take automatic precedence to avoid
doubled hits. Keep a metronome outside the import folder.

Folder execution preserves original bytes/hashes and publishes canonical
PCM24 WAV parts plus receipts atomically. It makes no network request and does
not recurse, separate, align or normalize. Use the prepared project as the
Create/TUI source. For exactly one standalone asset, use the separate
`source-import --plan` then execute flow; do not loop it over a folder.

For an agent-led automatic result, read `create --help`, then run:

```bash
SUNOFRIEND create "/absolute/path/to/stems" \
  --out-dir "/absolute/path/to/fresh-result"
```

If `create` is unavailable, launch `sunofriend tui` and guide the user to
**Create MIDI + WAV** in Simple mode. Do not automate TUI keystrokes or
reimplement the production runner. Automatic output stays `not_reviewed` and
`review_recommended` and records no human Workbench choice.

## Route D: help obtaining authorised stems

Explain that a stem is often a grouped submix. A drums stem may contain many
drums; `other` is a mixed residual; an AI-separated stem is an estimate, not
the lost original studio track.

Offer DAW exports, authorised stems/multitracks, an authorised independent
separator, an available Sunofriend experimental profile or the built-in demo. Provider plans,
formats and terms change, so check current official help. Prefer WAV/FLAC when
available; converting lossy audio to WAV restores no lost detail. Ask whether
private or unreleased audio may be uploaded before suggesting a cloud service.

Use `docs/STEMS.md` for the maintained neutral provider and privacy guide. Do
not call any provider best for MIDI without a downstream bake-off. Do not use
an affiliate link unless the relationship is verified and disclosed. Never
sign up, subscribe, upload music or accept provider terms for the user.

## Hand off a first result

The automatic bundle under `AUTOMATIC-SONG/` should include:

- `START-HERE.txt`;
- unchanged automatic-primary MIDI and combined General MIDI under `MIDI/`;
- named starter sounds, sound-aware MIDI and previews under `SOUNDS/`;
- `AUDIO/balanced-midi-song-interpretation.wav`;
- `TECHNICAL/balanced-mix-report.json`;
- `garageband-mix-recipe.md`, result receipt and ZIP.

Verify every reported file exists and is non-empty. Report omitted, ambiguous,
silent, proxy or failed roles. Present in this order:

1. **Listen:** balanced WAV.
2. **Use sounds:** named starter instruments and sound-aware MIDI.
3. **Edit evidence:** unchanged individual primary MIDI.
4. **Move everything:** ZIP.
5. **Set the DAW:** exact BPM from `START-HERE.txt`.
6. **Choose the feeling:** keep or replace each starter sound after listening.

Ask one useful question after listening. Do not record approval or a review
unless the person explicitly performs the labelled action.

## Use Simple or Studio honestly

Prefer **Simple** for a newcomer or automatic first interpretation. Use
**Studio** for multiple candidate comparison, waveform/note timelines,
explicit choices and feedback, selected arrangements, developer inspection,
instrument matching or a reviewed GarageBand pack.

```bash
SUNOFRIEND tui "/absolute/path/to/stems" \
  --mode studio \
  --candidate-root "/absolute/path/to/result"
```

Playback, zoom, mute, solo, levels, dwell time and audition count are temporary
interaction, not feedback or preference.

## Route advanced requests

Read both references completely before an advanced workflow:

- [Public interface contract](references/interface-contract.md)
- [Advanced operations](references/advanced-operations.md)

The advanced reference covers transcription, optional AI comparisons, vocal
melody, phrase review, bounded correction, Workbench, instruments, CoreMIDI,
key/BPM/tuning/alignment, mashups, listening challengers and Clip v1 reuse.
Read the selected command's `--help`. Never compress a workflow into an
invented command or silently choose a candidate. Keep raw, analytical, AI,
repaired and reviewed artifacts distinct.

## Validate and finish

For completion:

1. report the exact command and version;
2. confirm source files were not modified;
3. verify outputs exist and are non-empty;
4. report key, BPM, tuning, role coverage and warnings;
5. distinguish automatic from human-reviewed output;
6. distinguish the balanced interpretation from a listening-master challenger;
7. provide clickable absolute local paths; and
8. give one smallest useful next action.

For failure, state the exact failed phase, preserve partial evidence, do not
call it complete, avoid automatic destructive/network retries, and propose the
smallest safe recovery.

## Help install this skill elsewhere

When asked to install Sunofriend in another Codex setup, use `$skill-installer`
with:

`https://github.com/N9-Developer-Empowerment/sunofriend/tree/main/skills/sunofriend`

Install the skill first, then let it inspect and plan the application setup.
If it is not detected immediately, tell the user to restart Codex once.
