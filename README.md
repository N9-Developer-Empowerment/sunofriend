# Sunofriend

![Sunofriend — सुनो means listen; listen deeper, create further; independent of Suno Inc.](assets/brand/sunofriend-listener-banner-v4.png)

> **Listen deeper. Create further.**

Sunofriend turns separated music stems into editable MIDI interpretations and
a balanced MIDI-rendered WAV that helps you hear the song in a simplified
instrumental form.

The name comes from **सुनो** (*suno*), the familiar Hindi invitation or
command meaning “listen.” Paired with “friend,” it can be read as both
**“Listen, friend”** and **“a friend that listens.”** Sunofriend listens,
offers musical interpretations and hands the decision back to the musician.

Sunofriend is an independent project of **Unsigned Media Ltd**. It is not
related to, affiliated with, endorsed by, or sponsored by **Suno Inc.**, the
AI music company. References to Suno in example workflows mean that separate
third-party service. See the canonical [brand and name guide](BRAND.md).

Sunofriend is a local-first companion to generators, stem separators and DAWs.
It does not try to replace stem separation or a DAW. Its distinctive strength
is keeping results from several analytical and AI processes available, because
a different method may work best for each instrument or phrase.

> Sunofriend is an alpha project. It is currently tested most deeply on macOS
> with GarageBand and exports from independent third-party tools including
> Suno and Moises.

## Choose how much control you want

| Experience | Best for | What happens |
| --- | --- | --- |
| **Simple**, the default | Musicians who want the shortest workflow after installation | Supply a folder of WAV stems and choose **Create MIDI + WAV**. Sunofriend converts the stems, uses each production process's published primary result, and creates individual MIDI, a combined MIDI, a balanced WAV and a ZIP. |
| **Studio** | Musicians and developers who want to compare and improve results | Hear the source beside several MIDI methods, inspect waveforms and notes, make explicit choices, record local feedback, test sounds, build a reviewed GarageBand pack and use the read-only Developer Inspector. |

Both experiences use the same conversion, rendering and verification code.
Simple mode does not pretend its automatic defaults were reviewed. Studio
keeps the alternatives visible so your ears, not a score, make the final
musical decision.

Use the visible **Simple · Make my song** and **Studio · Compare & improve**
buttons to switch at any time. `F2` and `F3` do the same from the keyboard.
Switching changes only the view and returns to your last Studio tab; it does
not start processing, save feedback or alter MIDI choices.

Read [Product modes and the hosted future](docs/PRODUCT_MODES_AND_HOSTING.md)
for the complete product boundary.

## Quick start on macOS

### 1. Install the app and audio tools

Python 3.11 is recommended:

```bash
git clone https://github.com/N9-Developer-Empowerment/sunofriend.git
cd sunofriend
brew install python@3.11 fluid-synth
"$(brew --prefix python@3.11)/bin/python3.11" -m venv .venv
.venv/bin/python -m ensurepip --upgrade
.venv/bin/python -m pip install \
  -c constraints-audio-macos.txt -e '.[all]'
```

Install the validated GeneralUser GS SoundFont used for MIDI previews:

```bash
mkdir -p "$HOME/.local/share/sunofriend/soundfonts"
curl --fail --location \
  "https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/684543d5e5efaef08d02be50dcda8d552478fa60/GeneralUser-GS.sf2" \
  --output "$HOME/.local/share/sunofriend/soundfonts/GeneralUser-GS.sf2"
echo "9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe  $HOME/.local/share/sunofriend/soundfonts/GeneralUser-GS.sf2" \
  | shasum -a 256 -c -
```

Check conversion and preview support:

```bash
.venv/bin/sunofriend doctor --require convert
.venv/bin/sunofriend doctor --require preview
```

### 2. Prepare one folder of stems

Keep the WAV files at the top level. Put the key, BPM and tuning in the folder
name:

```text
My Song-B minor-113bpm-440hz/
├── My Song-kick-B minor-113bpm-440hz.wav
├── My Song-snare-B minor-113bpm-440hz.wav
├── My Song-bass-B minor-113bpm-440hz.wav
├── My Song-keys-B minor-113bpm-440hz.wav
├── My Song-vocals-B minor-113bpm-440hz.wav
├── My Song-backing vocals-B minor-113bpm-440hz.wav
├── My Song-metronome-B minor-113bpm-440hz.wav  # optional
└── My Song-chords.pdf                           # optional
```

Use clear role words such as `kick`, `snare`, `hat`, `cymbals`, `toms`,
`other kit`, `bass`, `keys`, `piano`, `strings`, `lead`, `synth`, `vocals` or
`backing vocals`. Unsupported, silent or ambiguous stems are reported rather
than quietly presented as successful.

### 3. Make the song

```bash
.venv/bin/sunofriend tui \
  "/absolute/path/to/My Song-B minor-113bpm-440hz"
```

The default **Make my song** tab suggests a fresh output folder. Check the two
paths and choose **Create MIDI + WAV**. Use the **Studio** button whenever you
want the detailed controls. Conversion can take time, especially on a long
song; progress remains visible and everything stays on this Mac.

The fresh result contains:

```text
your-chosen-output/
├── ...conversion evidence and alternatives...
└── AUTOMATIC-SONG/
    ├── START-HERE.txt
    ├── MIDI/
    │   ├── individual automatic-primary parts
    │   └── combined-gm-interpretation.mid
    ├── AUDIO/balanced-midi-song-interpretation.wav
    ├── TECHNICAL/balanced-mix-report.json
    ├── garageband-mix-recipe.md
    ├── sunofriend-result.json
    └── sunofriend-automatic-midi-and-wav.zip
```

Listen to the WAV first, then drag the individual MIDI files into GarageBand
and set the GarageBand project to the exact BPM in `START-HERE.txt`. Choose the
GarageBand sounds you like for the software-instrument tracks.

The WAV contains rendered MIDI only. Source stems provide timing, song length
and relative-level evidence; their audio is not mixed into it. It is a
balanced creative interpretation, not an exact reconstruction or a
human-approved release master.

For screenshots, detailed setup, GarageBand steps and troubleshooting, follow
the [Getting started guide](docs/GETTING_STARTED.md).

## Explore and improve the result

Open the detailed experience directly:

```bash
.venv/bin/sunofriend tui \
  "/absolute/path/to/My Song-B minor-113bpm-440hz" \
  --mode studio \
  --candidate-root "/absolute/path/to/your-chosen-output"
```

Studio can compare the unchanged MIDI alternatives, prepare level-assisted
source/MIDI loops, save explicit main or optional choices, hear the selected
arrangement, create the reviewed song-interpretation WAV and compose an exact
GarageBand ZIP. Playback and mixer experiments do not silently become
feedback. Only clearly labelled review actions save a choice.

See the [Guided Local Studio](docs/LOCAL_STUDIO_TUI.md) and
[visual Workbench](docs/WORKBENCH.md) guides.

## Hear an example

<p align="center">
  <img src="assets/social/out-of-place-interpolation-square-v1.png" width="520" alt="Out of Place, a Sunofriend interpolation">
</p>

[Listen to “Out of Place” on SoundCloud](https://soundcloud.com/ezzye-1/out-of-place?si=93616bdf10d7406c838be366106c1025&utm_source=clipboard&utm_medium=text&utm_campaign=social_sharing).
The maintainer shares it as an example of Sunofriend interpolation: a new
MIDI-derived musical interpretation, not an exact reconstruction of source
audio.

For a documented four-tool workflow, [listen to Version 1 of “The Aisle at
Lidl”](https://soundcloud.com/ezzye-1/the-aisle-at-lidl?si=97cf744ff4a743bca875bec3db88024f&utm_source=clipboard&utm_medium=text&utm_campaign=social_sharing).
The maintainer wrote that song and approved it as a public **Suno
(third-party) → Moises → Sunofriend → GarageBand** example. It is a finished
workflow example rather than the raw Simple-mode WAV. The repository contains a compact
[worked MIDI pack](examples/the-aisle-at-lidl/); the large source stems are not
committed.

## Documentation

| If you want to… | Read |
| --- | --- |
| Understand the name, strapline and independence language | [Brand and name guide](BRAND.md) |
| Install and make a first song | [Getting started](docs/GETTING_STARTED.md) |
| Understand Simple and Studio modes | [Product modes and hosted future](docs/PRODUCT_MODES_AND_HOSTING.md) |
| Operate the terminal dashboard | [Guided Local Studio TUI](docs/LOCAL_STUDIO_TUI.md) |
| Compare, review and export visually | [Workbench](docs/WORKBENCH.md) |
| Understand the WAV, mix and mastering boundary | [Musical rendering and mastering](docs/MUSICAL_RENDERING_AND_MASTERING.md) |
| Improve vocal melody extraction | [Vocal melody](docs/VOCAL_MELODY.md) |
| Match or build playable instruments | [Instruments](docs/INSTRUMENTS.md) |
| Review the code and state model | [Technical tour](docs/TECHNICAL_TOUR.md) and [architecture](docs/ARCHITECTURE.md) |
| Follow AI and product research | [AI roadmap](docs/AI_TRANSCRIPTION_ROADMAP.md) and [Phase 5 plan](docs/PHASE5_MUSCRIPTOR_COMMUNITY_PLAN.md) |
| Reuse and transform MIDI clips | [Phase 6 creative arrangement](docs/PHASE6_CREATIVE_ARRANGEMENT.md) |
| Use the full command line | Run `.venv/bin/sunofriend --help` and the chosen command's `--help` |

## Privacy, rights and current limits

- The current TUI, Workbench, stems, MIDI, notes and feedback are local. The
  Workbench binds to loopback and has no community-upload endpoint.
- Use only music you own or are authorised to process. Do not redistribute
  stems, samples or model outputs unless their rights permit it.
- GarageBand supplies the final playable patches. Sunofriend does not copy
  Apple factory samples or claim to reproduce every production effect.
- Melody extraction, mixed stems and source-derived instruments remain
  difficult. Automatic results are starting points, not ground truth.
- The current release is a local macOS application. A paid hosted version for
  people without suitable hardware is a future product direction, not an
  available service.

## Help improve Sunofriend

Testing in other DAWs, on other operating systems, and with other stem
separators or AI music tools is especially valuable. Please report whether the
setup was understandable, the song completed, the MIDI imported at the right
tempo, and the WAV was musically useful.

Read [Contributing](CONTRIBUTING.md), submit a
[beginner first-song report](https://github.com/N9-Developer-Empowerment/sunofriend/issues/new?template=beginner-first-song.yml),
or submit a
[DAW / AI compatibility report](https://github.com/N9-Developer-Empowerment/sunofriend/issues/new?template=daw-ai-compatibility.yml).
Share only material you are allowed to share.

Ready-to-post artwork and draft copy for X, Bluesky, Threads, Instagram,
Facebook, WhatsApp and Slack are in the [social media kit](SOCIAL.md).

## Development

```bash
.venv/bin/python -m pip install -e '.[all,dev]'
.venv/bin/python -m pytest
.venv/bin/python -m ruff check src tests
```

Sunofriend is available under the [Apache License 2.0](LICENSE).
