---
name: sunofriend
description: Guide beginners and experts through local Sunofriend setup and use. Turn authorised separated WAV stems into editable MIDI plus a balanced MIDI-derived song-interpretation WAV and ZIP; offer a copyright-safe built-in demo when no stems are available; use Simple for automatic unreviewed results and Studio for multi-method comparison, feedback and GarageBand handoff. Also handle vocal melody, instrument matching and bundles, key/BPM/tuning/alignment transforms, mashups, Clip v1 reuse and bounded note correction. Use for Sunofriend, stems-to-MIDI, song interpolation, GarageBand, MIDI comparison, tempo/key changes and stem-derived instruments. Do not perform generic stem separation, music downloading, lyric writing, DAW GUI editing, human-approved release mastering or unapproved dependency/model installation.
---

<!-- sunofriend-interface-contract: 2026-07-28.1 -->

# Sunofriend

**Listen deeper. Create further.**

Sunofriend turns separated song parts into editable MIDI and a balanced
MIDI-derived WAV. It keeps multiple analytical, repaired and optional local-AI
interpretations available because a different method can work best for each
instrument or phrase.

The name comes from Hindi **सुनो** (*suno*), “listen.” Sunofriend is an
independent Unsigned Media Ltd project and is not related to or affiliated
with Suno Inc.

## Begin with the person, not the command line

When the user is new or does not provide a precise expert task:

1. Explain the outcome in one sentence: editable MIDI, a listening WAV and a
   ZIP, all made locally.
2. Ask one question at a time.
3. Offer exactly these first choices:
   - **Try the built-in demo**
   - **Use separate audio parts (stems) I already have**
   - **Help me get stems I am allowed to process**
4. If the user is unsure, recommend the built-in demo.
5. Do not begin with Git, Python, Homebrew, FluidSynth, model names or the full
   command catalogue.
6. Do not claim an ordinary browser chat can control the Mac. Continue only in
   an agent environment with local file and terminal access; otherwise point
   the user to a Codex local session.

Keep the first journey small. Explain the next action, perform or prepare it,
report the result, then move on.

## Preserve the product boundary

- Work locally. Do not upload stems, vocals, MIDI, chord files, private notes
  or feedback.
- Use only music the user owns or is authorised to process.
- Sunofriend does not download songs or separate a full mix into stems.
- The WAV contains rendered MIDI. Source stems provide timing, horizon and
  relative-level evidence but their audio is not mixed into the WAV.
- Call the WAV a **MIDI-derived song interpretation**, not an exact
  reconstruction or a human-approved release master.
- Playback, metrics, scores and visible defaults never imply preference.
- Use a fresh output outside the source folder. Never overwrite unless the
  user explicitly requests it and the chosen command supports it safely.
- Never download an optional model, checkpoint, plug-in or instrument without
  explicit approval and the applicable licence check.

## Inspect before installing

Resolve the application in this order:

1. `sunofriend` on `PATH`;
2. `.venv/bin/sunofriend` in the current workspace or a repository path the
   user already supplied;
3. `~/.local/share/sunofriend/app/.venv/bin/sunofriend`.

Do not scan the whole home directory. Ask for the location if those bounded
checks do not find a user-mentioned checkout.

Run `sunofriend --version` when found. Do not replace or update an existing
checkout merely because another copy exists.

If the application or required audio tools are missing:

1. Resolve `scripts/bootstrap-macos.sh` relative to this `SKILL.md`.
2. Run it with `--plan`. This is read-only.
3. Translate the plan into plain language. Name every known network
   destination and machine-level package change; say when Homebrew or PyPI may
   choose a mirror or CDN host that cannot be enumerated in advance.
4. If no checkout exists, ask for permission to prepare only the source.
5. After approval, run the helper with `--prepare --yes`. This clones the
   public source but installs no package or audio asset.
6. Run `--plan` again. Show the user the exact 40-character commit and explain
   all remaining changes.
7. Ask for a separate installation approval bound to that commit.
8. Only after approval, run `--apply --expected-revision COMMIT --yes`.
9. Report any blocked prerequisite precisely instead of improvising around it.

The helper uses `~/.local/share/sunofriend/app` by default. It may use an
existing Homebrew installation to install Python 3.11 and FluidSynth, create
an isolated virtual environment, install the constrained Sunofriend audio
stack, download the pinned hash-verified GeneralUser GS SoundFont and run the
conversion/preview doctors.

Use these newcomer translations:

- **Python:** the private runtime Sunofriend needs.
- **Virtual environment:** Sunofriend's own dependency folder, separate from
  other Python projects.
- **FluidSynth:** the local player that turns MIDI notes into a WAV.
- **SoundFont:** the approximately 31 MB set of neutral instrument sounds used
  by FluidSynth.
- **SHA-256 check:** verification that the downloaded SoundFont is the exact
  reviewed file.
- **`.[all]` dependencies:** Sunofriend's full local application feature set;
  it does not include optional AI checkpoints.

Before approval, distinguish local music processing from setup network use.
State that the tested environment occupies roughly 0.5 GB before Homebrew and
download caches, recommend at least 1 GB free, and explain that setup time and
download size vary by what is already installed. The helper does not use
`sudo`, but a separate Homebrew installation may have its own prompts.

Explain that GeneralUser GS supplies preview sounds under its own License
v2.0. Link to the pinned licence and mention its sample-origin caveat when the
user is deciding about commercial software distribution. The demo itself is
generated mathematically by Sunofriend and contains no recorded samples.

The helper deliberately does not install Homebrew, update or reset an existing
checkout, replace a mismatched SoundFont, or install optional AI checkpoints.
If Homebrew is missing, explain the official Homebrew prerequisite and ask
before helping with that separate system change.

The current alpha preparation resolves the public `main` branch once. Tell the
user that a tagged end-user release is not available yet. The helper then
stops, prints the exact local commit and requires that same 40-character
commit in the separately approved apply command. Apply never fetches, pulls or
switches the checkout.

For cleanup, preserve evidence first. The isolated checkout can be removed
later from `~/.local/share/sunofriend/app` and the SoundFont from
`~/.local/share/sunofriend/soundfonts/GeneralUser-GS.sf2`. Do not remove shared
Homebrew packages automatically. An interrupted install can be inspected and
resumed; it is not rolled back silently.

After setup, run:

```bash
SUNOFRIEND doctor --require convert
SUNOFRIEND doctor --require preview
```

Here and below, replace `SUNOFRIEND` with the resolved executable path. Do not
ask a newcomer to perform that substitution manually.

## Route A: built-in demo

Use this when the user has no stems, wants a quick proof, or is evaluating the
installation.

1. Choose a fresh, clearly named output such as
   `~/Music/Sunofriend/demo-YYYYMMDD-HHMMSS`.
2. Read `sunofriend demo --help`.
3. Run:

```bash
SUNOFRIEND demo --out-dir "/absolute/fresh/demo-output"
```

The command creates copyright-safe synthetic stems beside the result and then
uses the normal automatic production path. It must produce the normal
automatic MIDI, balanced WAV and starter ZIP rather than a hand-built toy
preview.

When it completes, show the user:

1. the balanced WAV;
2. `START-HERE.txt`;
3. the individual MIDI folder; and
4. the ZIP.

Open or reveal the WAV first when the environment supports it. Explain that
the demo proves the workflow, not transcription accuracy on every real song.

## Route B: stems the user already has

Inventory the source folder read-only. Confirm:

- top-level `.wav` files exist;
- the key and BPM are known or parseable from the folder name;
- useful role words are present, such as `kick`, `snare`, `hat`, `bass`,
  `keys`, `strings`, `lead`, `vocals` or `backing vocals`;
- any chord PDF or metronome is identified as optional evidence; and
- the proposed output is fresh and outside the source.

For an agent-led automatic result, read `sunofriend create --help` and run:

```bash
SUNOFRIEND create "/absolute/path/to/stems" \
  --out-dir "/absolute/path/to/fresh-result"
```

If the installed application predates the `create` command, use
`sunofriend tui "/absolute/path/to/stems"` and guide the user to the single
**Create MIDI + WAV** action in Simple mode. Do not automate TUI keystrokes or
reimplement the production runner.

The automatic route uses each production process's published primary result.
It remains explicitly `not_reviewed` and `review_recommended`; it creates no
human Workbench choice or feedback event.

## Route C: help obtaining authorised stems

Explain that stems are separate audio parts such as drums, bass, keys and
vocals. Offer:

- separate-track exports from GarageBand or another DAW;
- stems or multitracks from a generator project the user may process;
- separated tracks exported from Moises or another stem separator; or
- the built-in demo.

Provider features, subscriptions and export formats change. When the user
wants current guidance, check the provider's official help rather than relying
on remembered prices. Prefer WAV where the user's plan supports it.

Useful official starting points include:

- Suno Studio export and stem-separation help at `help.suno.com`;
- Moises separated-track export help at `help.moises.ai`.

Do not sign up, subscribe, upload music or accept provider terms on the user's
behalf. Do not infer that a subscription grants rights to process or
redistribute a particular song.

## Hand off a first result

The automatic bundle is under `AUTOMATIC-SONG/` and should include:

- `START-HERE.txt`
- `MIDI/` with individual roles and combined General MIDI
- `AUDIO/balanced-midi-song-interpretation.wav`
- `TECHNICAL/balanced-mix-report.json`
- `garageband-mix-recipe.md`
- `sunofriend-result.json`
- `sunofriend-automatic-midi-and-wav.zip`

Check that the reported files exist and are non-empty. Report omitted,
ambiguous, silent, proxy or failed roles honestly.

Use plain language:

- **Listen first:** the balanced WAV.
- **Edit next:** individual MIDI files.
- **Move everything:** the ZIP.
- **Set the DAW:** use the exact BPM from `START-HERE.txt`.
- **Choose the feeling:** replace the General MIDI proxy sounds with suitable
  GarageBand or DAW instruments.

Ask one useful feedback question after the user listens, such as:

> Did the WAV help you hear the song's musical parts clearly?

Do not record approval, a choice or review unless the user explicitly performs
the labelled review action.

## Use Simple or Studio honestly

Prefer **Simple** for a newcomer or an automatic first interpretation.

Use **Studio** when the user wants to:

- compare the source with several unchanged MIDI candidates;
- see waveform and note timelines;
- choose main, optional, needs-correction or rejected parts;
- record explicit local feedback;
- hear selected arrangements;
- inspect developer state;
- try instrument matches; or
- create a reviewed GarageBand pack.

Launch the detailed route with:

```bash
SUNOFRIEND tui "/absolute/path/to/stems" \
  --mode studio \
  --candidate-root "/absolute/path/to/result"
```

Use the loopback Workbench for graphical comparison. Treat zoom, playback,
mute, solo, level, dwell time and audition count as temporary interaction, not
feedback or preference.

## Route advanced requests

Before any advanced workflow, read both references completely:

- [Public interface contract](references/interface-contract.md)
- [Advanced operations](references/advanced-operations.md)

Use the interface contract to confirm the command exists in the installed
version. Read the selected command's `--help` before constructing it.

The advanced reference contains the exact contracts for:

- whole-folder and vocal transcription;
- tracker consensus, MuScriptor and other optional local-AI comparisons;
- melody guides, phrase review and bounded correction;
- Workbench catalogues, playback, feedback and GarageBand packs;
- instrument inventory, matching, sample packs and instrument bundles;
- MIDI preview, CoreMIDI playback, key, BPM, tuning, anchoring and alignment;
- mashup preparation;
- listening-master challengers and blind review; and
- Clip v1 import, search, reuse, transformation and correction.

Do not compress those workflows into an improvised command or silently choose
a candidate. Keep raw, analytical, AI, repaired and reviewed artifacts
distinct.

## Validate and finish

For every completed task:

1. confirm the exact command and application version used;
2. confirm source files were not modified;
3. verify expected outputs exist and are non-empty;
4. report key, BPM, tuning, role coverage and warnings;
5. distinguish automatic output from human-reviewed output;
6. distinguish the balanced interpretation from any separate listening-master
   challenger;
7. provide clickable absolute local paths when the client supports them; and
8. give one smallest useful next action.

For failure:

1. state the failed phase and exact missing component;
2. preserve partial output for diagnosis;
3. do not call it a completed song;
4. do not retry a destructive or network action automatically; and
5. propose the smallest safe recovery.

## Help install this skill elsewhere

When the user asks to install Sunofriend on another Codex setup, use
`$skill-installer` with:

`https://github.com/N9-Developer-Empowerment/sunofriend/tree/main/skills/sunofriend`

Install the skill first. Let the installed skill inspect and plan the
application setup separately. If the new skill is not detected immediately,
tell the user to restart Codex once.
