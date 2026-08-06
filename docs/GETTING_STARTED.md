# Getting started

This guide is the detailed manual route for a musician who has separated
audio parts and wants editable MIDI plus a clean listening version of the
song. Simple and Studio consume synchronized top-level WAV stems. If your
existing separated parts are WAV, AIFF, FLAC, M4A, MP3 or Ogg, the folder
importer can first preserve and prepare them as that canonical WAV project.
The separate experimental alpha can estimate broad vocals and complementary
instrumental from one authorised finished mix on supported Apple-silicon Macs.
Neither route repairs musical alignment.

If “stem” is unfamiliar, or you need legitimate ways to obtain examples, read
[Stems: what they are and where to get them](STEMS.md) first. If you have only
a finished mix, read [Experimental local stem separation](STEM_SEPARATION_ALPHA.md).
It is an opt-in two-stem alpha, not exact multitrack recovery. The source-import
boundaries and wider research record are documented in
[Stem access and separation research](STEM_ACCESS_AND_SEPARATION_RESEARCH.md).

Sunofriend is currently an alpha macOS application presented in the terminal.
The default **Make my song** screen is designed to keep the technical choices
out of the first journey. The deeper Studio and command line remain available
when you want them.

If you do not want to install Python and audio tools yourself, start with
the [beginner website](https://sunofriend.com) or
[AI-assisted first song](AI_ASSISTED_START.md). The Sunofriend skill asks one
question at a time, inspects the Mac without changing it, uses separate
source-preparation and exact-commit installation approvals, and can run a
copyright-safe demo even when you have no stems.

## Before you begin

You need:

- a Mac;
- [Homebrew](https://brew.sh/) for this manual route;
- a folder containing one song's separated, synchronized audio parts, or the
  built-in demo;
- the song's key and BPM, preferably in the folder name; and
- permission to process the music.

Python 3.11 is the recommended runtime. Sunofriend supports Python 3.9 through
3.11, but the audio dependency set is tested most often with 3.11.

All current processing is local. The TUI does not upload your stems, MIDI,
private notes or feedback.

## Have one finished song instead of stems?

On Apple-silicon macOS, Sunofriend can experimentally estimate broad
`vocals.wav` and complementary `instrumental.wav`. The setup and model are a
separate explicit choice; they are not installed by the normal demo.

Start with read-only plans:

```bash
scripts/setup-separation-alpha-macos.sh --plan
.venv/bin/sunofriend-separate doctor
.venv/bin/sunofriend-separate separate \
  "/absolute/path/to/authorised-song.flac" \
  --out "/absolute/path/to/fresh-separation" \
  --rights-category owned
```

After reviewing the setup, terms, rights and output path, follow the complete
[alpha guide](STEM_SEPARATION_ALPHA.md). Listen to the source, both estimates
and reconstruction check before deciding whether either result should enter a
later MIDI workflow. The website never receives the audio.

## Install Sunofriend manually

Open Terminal and run:

```bash
git clone https://github.com/N9-Developer-Empowerment/sunofriend.git
cd sunofriend
brew install python@3.11 fluid-synth
"$(brew --prefix python@3.11)/bin/python3.11" -m venv .venv
.venv/bin/python -m ensurepip --upgrade
.venv/bin/python -m pip install \
  -c constraints-audio-macos.txt -e '.[all]'
```

The clone is currently the manual installation route. An agent using the
installed skill can instead use the conservative setup helper, which defaults
to a read-only plan, prepares an isolated checkout separately, and binds the
later installation approval to its exact commit. A PyPI end-user release and a
signed macOS application are future packaging work.

### Install the preview sound

Sunofriend uses a General MIDI SoundFont to turn MIDI into local WAV previews:

```bash
mkdir -p "$HOME/.local/share/sunofriend/soundfonts"
curl --fail --location \
  "https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/684543d5e5efaef08d02be50dcda8d552478fa60/GeneralUser-GS.sf2" \
  --output "$HOME/.local/share/sunofriend/soundfonts/GeneralUser-GS.sf2"
echo "9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe  $HOME/.local/share/sunofriend/soundfonts/GeneralUser-GS.sf2" \
  | shasum -a 256 -c -
```

The final line verifies the exact file before Sunofriend uses it.
GeneralUser GS is supplied under its own
[License v2.0](https://github.com/mrbumpy409/GeneralUser-GS/blob/684543d5e5efaef08d02be50dcda8d552478fa60/documentation/LICENSE.txt).
That licence permits music creation and documents a sample-origin caveat that
commercial software distributors should review.

### Check the installation

From the repository folder, run:

```bash
.venv/bin/sunofriend --version
.venv/bin/sunofriend doctor --require convert
.venv/bin/sunofriend doctor --require preview
```

Both checks should complete successfully. The conversion check covers audio
analysis and transcription. The preview check covers FluidSynth and the
SoundFont.

CoreMIDI is not required to create the files. It is needed only for live MIDI
playback through a software or hardware MIDI destination.

## Prepare one local audio asset

Source Import S1 is a bounded expert preparation tool for exactly one local
file. It accepts the tested portable combinations of PCM WAV or AIFF, FLAC,
MP3, M4A containing AAC or ALAC, and Ogg containing Vorbis or Opus. The
installed FFmpeg build still decides which encoders and decoders are present.
AIFC, CAF and WMA require the explicit `--allow-conditional-format` option.

Sunofriend uses an existing local `ffmpeg` and `ffprobe`; it does not install
them, download anything or access the network. Check that toolchain first:

```bash
.venv/bin/sunofriend source-doctor
```

Inspect an exact read-only plan:

```bash
.venv/bin/sunofriend source-import \
  "/absolute/path/to/My Song-bass-B minor-113bpm-440hz.flac" \
  --out-dir "/absolute/path/to/fresh-bass-import" \
  --role bass \
  --rights-category authorised_private_use \
  --plan
```

`--plan` is the explicit read-only form. Remove only that flag to execute the
same import:

```bash
.venv/bin/sunofriend source-import \
  "/absolute/path/to/My Song-bass-B minor-113bpm-440hz.flac" \
  --out-dir "/absolute/path/to/fresh-bass-import" \
  --role bass \
  --rights-category authorised_private_use
```

The output must not already exist and must be outside the source file's
folder:

```text
fresh-bass-import/
└── INPUT/
    ├── original/<unchanged source filename>
    ├── canonical/<deterministic PCM24 WAV>
    ├── source-import.json
    └── source-project.json
```

Keep the source and output-parent paths unchanged while the command runs.
Sunofriend rejects ordinary collisions and detected symlink/path changes, but
this local single-user workflow is not a sandbox against another hostile
process continually renaming filesystem ancestors during decoding.

The original bytes and SHA-256 identity are preserved. The canonical WAV is
decoded without loudness normalization, and the receipts record format,
geometry, clock, decoder and musical context. Lossy MP3 or AAC evidence
remains lossy after decoding. Packet-edge evidence records codec priming and
padding, and the canonical WAV is capped to the declared source duration.

This command does **not** split a finished song, align several files, import a
folder, or launch conversion. The current Simple and Studio journeys below
still need a prepared folder of separate synchronized WAV stems. Use the
folder importer below when you already have several separated parts.

## Prepare a folder of existing audio parts

`source-import-folder` prepares 2–64 already-separated, synchronized,
top-level audio files as one canonical WAV project. It supports the same
portable formats as the one-file importer. It does **not** separate a finished
mix, shift or pad files, stretch time, normalize audio, repair alignment, or
claim that recorded zero is the musical downbeat.

Check the existing local decoder first, then inspect a read-only plan:

```bash
.venv/bin/sunofriend source-doctor
.venv/bin/sunofriend source-import-folder \
  "/absolute/path/to/My Song source parts" \
  --out-dir "/absolute/path/to/fresh-prepared-project" \
  --rights-category authorised_private_use \
  --key "B minor" \
  --bpm 113 \
  --tuning-hz 440 \
  --plan
```

The plan reports inferred roles, source clocks, duration warnings and every
intended output without writing anything. If any input, role map or option
changes, run the plan again. Removing `--plan` replans the current inputs and
then executes; it does not replay a stored plan:

```bash
.venv/bin/sunofriend source-import-folder \
  "/absolute/path/to/My Song source parts" \
  --out-dir "/absolute/path/to/fresh-prepared-project" \
  --rights-category authorised_private_use \
  --key "B minor" \
  --bpm 113 \
  --tuning-hz 440
```

The source folder must contain 2–64 supported regular audio files directly at
its top level. Subfolders and symbolic links are not followed. The output must
be fresh. Sunofriend publishes it as one atomic, no-replace operation:

```text
fresh-prepared-project/
├── <safe-name>-<role>-canonical.wav
└── INPUT/
    ├── original/<byte-identical source copies with safe local names>
    ├── receipts/<one receipt per source>.source-import.json
    ├── source-folder-import.json
    ├── source-project.json
    └── context/<optional copied PDF or text file>
```

Role inference is deliberately conservative. If a filename is ambiguous,
provide a flat JSON role map keyed by exact filename:

```json
{
  "My Song low synth.flac": "bass",
  "My Song handclaps.m4a": "other_kit"
}
```

Then add `--role-map "/absolute/path/to/roles.json"` to both plan and
execution. Supported observed roles are `backing_vocals`, `bass`, `cymbals`,
`drums`, `hat`, `keys`, `kick`, `lead`, `other`, `other_kit`, `piano`,
`rhythm`, `snare`, `strings`, `synth`, `toms`, `vocals` and `wind`. Only
`vocals` and `backing_vocals` may repeat. `hats` is normalized to `hat`, guitars to
`rhythm`, and percussion to `other_kit`.

`pads` is deliberately not an accepted observed role yet: production
currently synthesizes pads from keys and has no observed-pads conversion job.
Map a genuinely string-like sustained part to `strings`; otherwise keep the
role unresolved rather than mislabelling it.

A composite `drums` part is now usable directly. Sunofriend sends each
detected onset through the existing mixed-kit spectral family classifier and
publishes review-required drum MIDI variants. It chooses one dominant family
per onset, so coincident layered hits can collapse to one MIDI note. This is
MIDI classification, not audio separation: it does not create kick, snare,
hat, tom or cymbal WAV files.

If viable explicit drum-family sources such as `kick`, `snare` or `hat` are
also present, those narrower sources take precedence in the automatic
arrangement and the composite `drums` MIDI is retained for Studio review.
This prevents doubled drum hits. If the explicit leaves produce no viable
primary MIDI, the review-required composite result remains the automatic
fallback. A metronome is timing evidence rather than an observed source role,
so keep it outside the folder being imported.

Sunofriend compares recorded start times when the containers expose them.
Compatible origins are evidence only. If any origin is missing, the plan is
`unconfirmed` and execution requires the explicit
`--accept-unconfirmed-origin` acknowledgement. A concrete origin conflict
blocks execution. Different end times are reported as warnings rather than
silently padded or trimmed.

Once preparation succeeds, use the fresh project directly with `create` or
the TUI:

```bash
.venv/bin/sunofriend create \
  "/absolute/path/to/fresh-prepared-project" \
  --out-dir "/absolute/path/to/fresh-song-output"

.venv/bin/sunofriend tui "/absolute/path/to/fresh-prepared-project"
```

Prepared projects are resolved through an immutable source graph. A project
with no saved graph gets the same original sources as a deterministic
read-only first revision. Later refinements can append child evidence without
rewriting the import manifest, and the active frontier prevents an original
parent and its children from both entering one conversion. No current command
creates refined child audio, so this lineage support does not claim that
Sunofriend can separate a finished mix.

## Try the built-in demo

The quickest manual check needs no private music or stem subscription:

```bash
.venv/bin/sunofriend demo \
  --out-dir "$HOME/Music/Sunofriend/demo-first-run"
```

The output path must be fresh. The command creates a small copyright-safe
synthetic stem project beside it, then runs the same production Simple
workflow used for a real song. It prints progress and the exact balanced WAV,
MIDI, receipt and ZIP paths.

Listen to
`demo-first-run/AUTOMATIC-SONG/AUDIO/balanced-midi-song-interpretation.wav`
first. The demo proves that setup, transcription, rendering and packaging work
together; it does not predict accuracy on every real stem.

## Prepare the stems

Put one song's WAV files directly inside one folder. Do not put each stem in a
separate subfolder.

Include the key, BPM and tuning in the folder name:

```text
My Song-B minor-113bpm-440hz/
├── My Song-kick-B minor-113bpm-440hz.wav
├── My Song-snare-B minor-113bpm-440hz.wav
├── My Song-hat-B minor-113bpm-440hz.wav
├── My Song-bass-B minor-113bpm-440hz.wav
├── My Song-keys-B minor-113bpm-440hz.wav
├── My Song-strings-B minor-113bpm-440hz.wav
├── My Song-vocals-B minor-113bpm-440hz.wav
├── My Song-backing vocals-B minor-113bpm-440hz.wav
├── My Song-metronome-B minor-113bpm-440hz.wav  # optional
└── My Song-chords.pdf                           # optional
```

Useful role words include:

- drums: `kick`, `snare`, `hat`, `cymbals`, `toms`, `other kit`;
- pitched instruments: `bass`, `keys`, `piano`, `strings`, `lead`, `synth`;
- broad separator roles: `wind`, `rhythm`, `other`; and
- voice: `vocals`, `lead vocals`, `backing vocals`.

Broad `wind`, `rhythm` and `other` stems use conservative proxy engines. They
remain labelled as proxies and should be heard in Studio before you rely on
them. A metronome is timing evidence, not a musical stem.

Name an optional chord PDF with the word `chords`. Chord evidence can help
supported harmonic processing, but a PDF does not make a noisy or mixed stem
unambiguous.

Sunofriend lists silent, unsupported and ambiguous roles in its result instead
of silently claiming that they converted.

## Make a first song in Simple mode

An agent can run the non-interactive wrapper:

```bash
.venv/bin/sunofriend create \
  "/absolute/path/to/My Song-B minor-113bpm-440hz" \
  --out-dir "/absolute/path/to/fresh-song-output"
```

It uses the exact same production runner as the TUI's Simple action and prints
bounded progress plus a machine-readable result. It does not write a human
review or feedback event.

To operate the visual terminal journey yourself, run the TUI:

Run the TUI with the absolute path to the stem folder:

```bash
cd /absolute/path/to/sunofriend
.venv/bin/sunofriend tui \
  "/absolute/path/to/My Song-B minor-113bpm-440hz"
```

Simple mode is the default. You should see the **Make my song** tab.
The **Simple · Make my song** and **Studio · Compare & improve** buttons stay
visible above the tabs. You can switch in either direction without reloading
the project. `F2` opens Simple and `F3` returns to the last Studio tab.
Switching is navigation only: it does not begin conversion, record feedback or
change a MIDI choice.

1. Check the **Stem project** path.
2. Check the suggested **Fresh output folder**.
3. Make sure the output is outside the stem folder and does not already exist.
4. Choose **Create MIDI + WAV**.
5. Leave the terminal open while the six progress phases run.

No second technical form is required. Sunofriend checks the project, converts
the supported stems, takes the explicit primary result published by each
production process, renders the MIDI and creates the bundle.

The first run can be slow. Audio analysis and vocal transcription are local
CPU work. The progress panel shows the current phase and role rather than
pretending the app has frozen.

### Cancelling

Choose **Cancel** if you need to stop. The running converter stops at a safe
boundary. A WAV already being verified may need to finish safely.

A partial conversion folder is preserved for diagnosis. It is not reported as
a successful song and is not automatically resumed after a restart. Choose a
new fresh output path for another run, or inspect and remove the partial folder
yourself.

## Understand the result

The output root contains conversion evidence and alternatives. The simple
starter bundle is:

```text
AUTOMATIC-SONG/
├── START-HERE.txt
├── MIDI/
│   ├── 01-role-automatic-primary.mid
│   ├── ...one file for each safely paired role...
│   └── combined-gm-interpretation.mid
├── SOUNDS/
│   ├── INSTRUMENTS-START-HERE.md
│   ├── automatic-starter-instruments.json
│   ├── MIDI/...named automatic starter-sound parts...
│   └── PREVIEWS/...short audible starter-sound excerpts...
├── AUDIO/
│   └── balanced-midi-song-interpretation.wav
├── TECHNICAL/
│   └── balanced-mix-report.json
├── garageband-mix-recipe.md
├── sunofriend-result.json
└── sunofriend-automatic-midi-and-wav.zip
```

Start with:

1. `START-HERE.txt` for the BPM, included role count and important limits;
2. the balanced WAV to hear the whole interpretation;
3. `SOUNDS/INSTRUMENTS-START-HERE.md` for named starter instruments and the
   sound-aware GarageBand MIDI files;
4. the exact individual automatic-primary MIDI files when you want the
   unchanged transcription evidence; and
5. the ZIP when you want one convenient copy of the bundle.

The result has `review_status: not_reviewed` and
`quality_status: review_recommended`. That wording is deliberate. Simple mode
does not compare every alternative and invent a winner, create a Workbench
decision, or claim that you listened.

The balanced WAV:

- contains rendered MIDI only;
- uses source stems for timing, song horizon and relative-level evidence;
- includes a conservative drum-bus guard and sample-peak protection;
- is not an exact reconstruction of production texture; and
- is not a human-approved release master.

It is useful as a clean interpretation, an arrangement reference and a quick
way to understand the song before choosing better sounds in a DAW.

## Import into GarageBand

1. Create a GarageBand project and set its tempo to the exact BPM in
   `START-HERE.txt`.
2. For an immediately assigned starting sound, drag the files from
   `AUTOMATIC-SONG/SOUNDS/MIDI/` into the project, or import the combined MIDI.
   Use the short matching files in `SOUNDS/PREVIEWS/` as the audible reference.
3. Keep every MIDI region at the same recorded-zero project origin.
4. Each file requests the named General MIDI starter in
   `SOUNDS/INSTRUMENTS-START-HERE.md`. GarageBand may substitute a comparable
   installed patch; replace it when you prefer another sound.
5. Leave quantisation off for the first comparison so the source timing is not
   hidden by a new grid.
6. Keep the balanced WAV on a reference track if it helps you compare the
   complete arrangement.

The combined MIDI and the separate files under `SOUNDS/MIDI/` use one shared
automatic starter-sound policy. Files directly under `MIDI/` remain exact
automatic-primary copies and may retain their process-specific program hints.

MIDI describes notes, timing, velocity and basic performance information. It
does not contain the continuous buzzing texture of a synth bass, a singer's
words, effects, amp character or the exact GarageBand patch. Choosing the
instrument remains an important creative step.

## Use Studio when you want control

Open the same source and result in Studio:

```bash
.venv/bin/sunofriend tui \
  "/absolute/path/to/My Song-B minor-113bpm-440hz" \
  --mode studio \
  --candidate-root "/absolute/path/to/your-chosen-output"
```

Then choose **Open visual studio**. The local browser Workbench lets you:

- see the source waveform and unchanged MIDI notes on one timeline;
- prepare short level-assisted source and candidate loops;
- compare analytical, AI and repaired alternatives;
- save a main, optional, needs-correction or reject decision;
- hear source-only, selected-MIDI and hybrid arrangements;
- inspect long songs with bounded visual and playback tools;
- record clearly labelled local feedback;
- render a reviewed balanced interpretation; and
- compose a source-audio-free GarageBand ZIP by default.

Temporary playback, mute, solo, gain, zoom and loop controls do not count as a
choice. Only explicit decision and feedback actions are saved.

If you want Studio to convert a project before review, prefill a fresh
conversion root:

```bash
.venv/bin/sunofriend tui \
  "/absolute/path/to/My Song-B minor-113bpm-440hz" \
  --mode studio \
  --conversion-output "/absolute/path/to/fresh-studio-results"
```

Open the **Convert** tab, read the operation summary and explicitly confirm
**Convert all stems**. After conversion, open the visual studio and make the
musical choices yourself.

Read [Guided Local Studio](LOCAL_STUDIO_TUI.md) for all TUI controls and
[Workbench](WORKBENCH.md) for the visual review contract.

## Agent-led route

The repository includes a Sunofriend skill for Codex and compatible coding
agents. It uses the same conversion engine; it is not a simplified or remote
copy of Sunofriend.

For a first installation, use the copyable prompts in
[AI-assisted first song](AI_ASSISTED_START.md). The agent should offer three
clear choices:

1. run the copyright-safe built-in demo;
2. process an existing authorised stem folder; or
3. explain current ways to obtain authorised stems.

The skill's macOS setup helper inspects by default. A new checkout requires
one explicit approval to prepare only the source. The agent then shows its
exact 40-character commit and requests a separate installation approval bound
to that same commit. Apply preserves the checkout rather than fetching,
resetting, switching or overwriting it.

## Troubleshooting

### `sunofriend` is not found

Run the repository command with its full local prefix:

```bash
.venv/bin/sunofriend --version
```

Also check that Terminal is currently inside the cloned `sunofriend` folder.

### Conversion support is missing

Run:

```bash
.venv/bin/sunofriend doctor --require convert
```

Re-run the constrained `pip install -e '.[all]'` command if a Python audio
component is missing. Warnings about unused TensorFlow or TFLite routes do not
matter when the standard ONNX conversion check passes.

### MIDI previews are silent

Run:

```bash
fluidsynth --version
.venv/bin/sunofriend doctor --require preview
```

Verify that
`$HOME/.local/share/sunofriend/soundfonts/GeneralUser-GS.sf2` exists and passed
the SHA-256 command above. A custom SoundFont can be supplied with
`--soundfont "/absolute/path/to/file.sf2"`.

### No stems were found

Check that:

- the files end in `.wav`;
- they are directly inside the selected project folder;
- their filenames contain recognisable role words; and
- the project folder name contains a parseable key and BPM.

Use the TUI **Activity** tab for the exact local failure phase.

### The output already exists

This is a safety feature. Simple and conversion operations require a fresh
folder and do not expose overwrite. Pick a new versioned name such as
`my-song-sunofriend-v2`.

### The source is much louder than the MIDI

Raw source stems and renderer previews can have very different levels. In
Studio, prepare the precise short loop: it reports and applies temporary,
bounded comparison gain in the browser without rewriting either file. Do not
judge a candidate only from an unmatched volume difference.

### The local browser page will not reconnect

Keep the TUI process running and use the newest loopback URL from its
**Activity** tab. Every launch uses a fresh private token. Restarted pages
cannot use an old token.

### The MIDI sounds unlike the stem

Separate three questions:

1. Are the notes, rhythm and register useful?
2. Are held notes and genuine rests represented?
3. Is the selected software instrument capable of the source texture?

A correct note line played through the wrong patch can sound unrelated. Studio
keeps note conversion and instrument choice as separate review questions.

## Update the checkout

From the repository root:

```bash
git pull --ff-only
.venv/bin/python -m pip install \
  -c constraints-audio-macos.txt -e '.[all]'
.venv/bin/sunofriend --version
```

Read release or migration notes before updating a project that has important
saved review state.

## Tell us whether the beginner journey worked

Useful feedback is simple:

- Did the install instructions work on a clean Mac?
- Did the app recognise the stems?
- Was progress understandable?
- Did it create the MIDI, WAV and ZIP?
- Did the MIDI import into your DAW at the right BPM?
- Was the balanced WAV musically useful?
- At what point did you need technical help?

Use the
[beginner first-song report](https://github.com/N9-Developer-Empowerment/sunofriend/issues/new?template=beginner-first-song.yml).
For another DAW, separator, AI tool or MIDI device, use the
[DAW / AI compatibility report](https://github.com/N9-Developer-Empowerment/sunofriend/issues/new?template=daw-ai-compatibility.yml).
You can also follow [Contributing](../CONTRIBUTING.md). Share only material you
have permission to share.
