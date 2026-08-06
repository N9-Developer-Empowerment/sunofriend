---
name: sunofriend
description: Guide beginners and experts through local Sunofriend setup and use. Optionally separate one authorised finished mix into experimental broad vocals and instrumental on a supported Apple-silicon Mac, or prepare 2–64 existing stems, then create editable MIDI, a balanced MIDI-derived song-interpretation WAV and ZIP. Offer a copyright-safe demo; use Simple for automatic unreviewed results and Studio for multi-method comparison, feedback and GarageBand handoff. Also handle vocal melody, instruments, key/BPM/tuning/alignment transforms, mashups, Clip v1 reuse and bounded correction. Use for Sunofriend, local experimental separation, stems-to-MIDI, song interpolation, GarageBand, MIDI comparison, tempo/key changes and stem-derived instruments. Do not download music, upload private audio, use unpinned separator models, write lyrics, edit a DAW GUI, claim human-approved release mastering or install dependencies/models without explicit approval.
---

<!-- sunofriend-interface-contract: 2026-08-06.1 -->

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
- The opt-in public separation alpha accepts one local finished mix and
  estimates broad `vocals` plus complementary `instrumental`. It is verified
  on Apple-silicon macOS, is not ground truth, does not yet make narrow drums,
  bass, keys or guitars, and never activates output for MIDI automatically.
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
Historical statements in the advanced record do not override this contract.

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
- output is broad vocals and instrumental, not narrow instrument families;
- full songs can take several minutes; and
- output remains unreviewed until the musician listens.

Read `docs/STEM_SEPARATION_ALPHA.md`. Resolve
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
SUNOFRIEND-SEPARATE doctor
```

Create a fresh output outside the source. Plan with the accurate rights
category (`owned`, `licensed`, `authorised_private_use` or
`statutory_exception`):

```bash
SUNOFRIEND-SEPARATE separate "/absolute/path/to/song.wav" \
  --out "/absolute/path/to/fresh-separation" \
  --rights-category owned
```

Explain the source hash, duration, output, space requirement and limits. Ask
for a separate rights confirmation before executing:

```bash
SUNOFRIEND-SEPARATE separate "/absolute/path/to/song.wav" \
  --out "/absolute/path/to/fresh-separation" \
  --rights-category owned \
  --execute --confirm-rights --open-review
```

Open `REVIEW/separation_review.html`. Ask the musician to hear source, vocals,
instrumental and reconstruction. A close reconstruction proves additive PCM
accounting, not correct assignment. Public feedback must be text-only unless
the musician separately chooses and is entitled to share audio.

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
separator, the Sunofriend two-stem alpha or the built-in demo. Provider plans,
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
