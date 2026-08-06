# Sunofriend

![Sunofriend — सुनो means listen; listen deeper, create further; independent of Suno Inc.](assets/brand/sunofriend-listener-banner-v4.png)

> **Listen deeper. Create further.**

Sunofriend turns separated music stems into editable MIDI and a balanced
MIDI-derived WAV. The WAV is a clean musical interpretation that can make a
song's rhythm, harmony and melody easier to hear; the MIDI can then be changed
in GarageBand or another DAW.

It is local-first, open source and designed to compare several analytical and
AI transcription methods rather than pretending one method always wins.

Sunofriend is an independent Unsigned Media Ltd project. Its name comes from
the Hindi **सुनो** (*suno*), “listen.” It is not related to, affiliated with,
endorsed by or sponsored by Suno Inc.

## Easiest start: ask Codex

You do not need to clone the repository or understand Python first. Use
[Codex with access to a local folder on your Mac](https://learn.chatgpt.com/docs/quickstart)
and follow the copyable prompts on the
[beginner website](https://sunofriend.com), or send them directly:

```text
Use $skill-installer to install the Sunofriend skill from
https://github.com/N9-Developer-Empowerment/sunofriend/tree/main/skills/sunofriend.
Do not install the application yet. Tell me when the skill is available.
```

Then start a new message:

```text
Use $sunofriend. I am new to music software. Help me choose between:
1. trying the built-in demo,
2. experimentally separating one finished song locally,
3. using stems I already have, or
4. getting stems I am allowed to process.
Explain one thing at a time. Inspect my Mac and show me an installation plan
before making system or network changes. Keep my audio local.
```

The skill should:

1. ask what you want to try;
2. inspect the Mac without changing it;
3. explain the exact setup plan in plain language;
4. ask once before preparing the source and again before installing the exact
   reviewed commit;
5. run the demo or process your stem folder; and
6. show the WAV, MIDI and ZIP in the order they are useful.

If the skill does not appear immediately, restart Codex and send the second
message again. See [AI-assisted first song](docs/AI_ASSISTED_START.md) for the
complete newcomer journey.

## No stems yet?

Choose the built-in demo. It creates a small copyright-safe synthetic song and
runs the same automatic MIDI, WAV and ZIP workflow used for a real project.
It is the quickest way to decide whether Sunofriend is useful before processing
personal music.

Sunofriend also has an opt-in public **experimental local separator** for an
authorised finished song on Apple-silicon macOS. Broad vocals plus complementary
instrumental remains the default. The separately installed, immutable
SCNet-large profile is now available as an explicit local
vocals/drums/bass/grouped-other preview. Its objective offline canaries passed
and its full-song outputs had no catastrophic defect reported; musical quality
remains experimental. The working two-stem route produces a
reconstruction check and local listening page. Read [Experimental local stem separation](docs/STEM_SEPARATION_ALPHA.md)
before installing a separate pinned model/runtime or treating any estimate as
useful.

> **Core-four preview available:** after the separately approved SCNet setup,
> Sunofriend can estimate `vocals.wav`, `drums.wav`, `bass.wav` and grouped
> `other.wav`. Inspect the immutable profile first, then select the scope
> explicitly:

```bash
.venv/bin/sunofriend-separate profiles
.venv/bin/sunofriend-separate separate "/absolute/path/to/song.wav" \
  --scope core-four-stems-v1 \
  --out "/absolute/path/to/fresh-core-four-separation" \
  --rights-category owned
```

The command above is a read-only plan until `--execute --confirm-rights` is
added. It never starts MIDI/Create automatically, and grouped `other` is not a
single instrument.

For deeper separation, Sunofriend now has a non-executable Studio contract for
refining one exact grouped-`other` stem into either one guitar target or one
keys target plus the transparent residual. It installs and runs no model yet;
the first deterministic PCM24 proof and bounded backend-qualification path are
documented in [Refining grouped other in Studio](docs/OTHER_STEM_REFINEMENT.md).

Not sure what a stem is, why a drums stem contains several drums, or where to
get authorised examples? Read
[Stems: what they are and where to get them](docs/STEMS.md).

For your own music, valid starting points include:

- separate tracks exported from a DAW;
- stems from a song generator or project you are allowed to process;
- separated tracks exported from Moises or another stem separator; or
- the built-in Sunofriend demo.

Plans and export features change, so ask the agent to check the provider's
current official help before you subscribe. Sunofriend does not download songs
or grant permission to process music. Its default alpha is a broad two-stem
estimate, and even the core-four preview is not lost multitrack recovery or a
replacement for every specialist separation service.

Already have separate, synchronized parts as MP3, FLAC, M4A, AIFF, Ogg or
WAV? The local `source-import-folder` command can check and prepare 2–64 files
as one canonical WAV stem project before Simple or Studio runs. It does not
separate a finished mix, repair alignment or prove the musical downbeat.
One broad `drums` part can now produce review-required mixed-kit MIDI; it does
not create separate kick, snare or cymbal audio files.
The narrower `source-import` command still prepares one standalone asset.
See [source preparation](docs/GETTING_STARTED.md#prepare-a-folder-of-existing-audio-parts).

## What you receive

The automatic result contains:

```text
AUTOMATIC-SONG/
├── START-HERE.txt
├── MIDI/individual parts and combined-gm-interpretation.mid
├── SOUNDS/named starter-sound MIDI, short previews and GarageBand guide
├── AUDIO/balanced-midi-song-interpretation.wav
├── garageband-mix-recipe.md
└── sunofriend-automatic-midi-and-wav.zip
```

Listen to the WAV first. Then follow `SOUNDS/INSTRUMENTS-START-HERE.md` and
import either the combined MIDI or the separate sound-aware MIDI files into
GarageBand. Each one requests the same named General MIDI starter sound heard
in the interpretation. The exact automatic-primary MIDI stays unchanged under
`MIDI/`, and every starter sound remains an editable, unreviewed choice.

The WAV contains rendered MIDI, not the original stems. It is a creative
interpretation of notes, rhythm and structure, not an exact reconstruction or
a human-approved release master.

## Simple or Studio?

| Mode | Use it when | Result |
| --- | --- | --- |
| **Simple** | You want Sunofriend to make a useful first interpretation | Automatic, explicitly unreviewed MIDI, WAV and ZIP |
| **Studio** | You want to compare methods, listen closely and choose | Visual timelines, explicit feedback, reviewed selections and GarageBand handoff |

Both modes use the same conversion engine. Studio preserves Sunofriend's main
strength: different methods can be best for different instruments or phrases.

## Hear an example

<p align="center">
  <img src="assets/social/out-of-place-interpolation-square-v1.png" width="520" alt="Out of Place, a Sunofriend interpolation">
</p>

[Listen to “Out of Place” on SoundCloud](https://soundcloud.com/ezzye-1/out-of-place?si=93616bdf10d7406c838be366106c1025&utm_source=clipboard&utm_medium=text&utm_campaign=social_sharing).
It is shared as an example of Sunofriend interpolation: a new MIDI-derived
musical interpretation, not an exact copy of source audio.

For a documented four-tool workflow, hear
[“The Aisle at Lidl”](https://soundcloud.com/ezzye-1/the-aisle-at-lidl?si=97cf744ff4a743bca875bec3db88024f&utm_source=clipboard&utm_medium=text&utm_campaign=social_sharing)
and explore its compact [worked MIDI pack](examples/the-aisle-at-lidl/).

## More detail

| I want to… | Read |
| --- | --- |
| Let an agent guide my first session | [AI-assisted first song](docs/AI_ASSISTED_START.md) |
| Understand or obtain stems | [Stems and provider guide](docs/STEMS.md) |
| Try the public finished-mix separation alpha | [Experimental local stem separation](docs/STEM_SEPARATION_ALPHA.md) |
| Inspect the vocals, drums, bass and other preview contract | [Public core-four stem preview](docs/FULL_STEM_SEPARATION_PLAN.md) |
| Understand the Studio-only guitar/keys refinement path | [Refining grouped other in Studio](docs/OTHER_STEM_REFINEMENT.md) |
| Prepare a folder of existing separated parts | [Folder source import](docs/GETTING_STARTED.md#prepare-a-folder-of-existing-audio-parts) |
| Prepare one local audio file safely | [Source import](docs/GETTING_STARTED.md#prepare-one-local-audio-asset) |
| Install or troubleshoot manually | [Getting started](docs/GETTING_STARTED.md) |
| Understand Simple and Studio | [Product modes](docs/PRODUCT_MODES_AND_HOSTING.md) |
| Use the terminal studio | [Local Studio TUI](docs/LOCAL_STUDIO_TUI.md) |
| Compare results visually | [Workbench](docs/WORKBENCH.md) |
| Understand the WAV and mix boundary | [Musical rendering](docs/MUSICAL_RENDERING_AND_MASTERING.md) |
| Work with vocal melody | [Vocal melody](docs/VOCAL_MELODY.md) |
| Review the future vocal-comping design | [Vocal comping design](docs/VOCAL_COMPING_DESIGN.md) and [implementation plan](docs/VOCAL_COMPING_IMPLEMENTATION_PLAN.md) |
| Match or build instruments | [Instruments](docs/INSTRUMENTS.md) |
| Review the architecture and code | [Technical tour](docs/TECHNICAL_TOUR.md) |
| Use every expert command | Run `sunofriend --help` and read the [skill interface contract](skills/sunofriend/references/interface-contract.md) |
| Share or promote the project | [Social media kit](SOCIAL.md) and [brand guide](BRAND.md) |
| Inspect how separation was developed | [Developer preview](docs/SEPARATION_DEVELOPER_PREVIEW.md) and [research record](docs/STEM_ACCESS_AND_SEPARATION_RESEARCH.md) |

## Privacy, rights and limits

- Current processing, review notes and feedback stay on the local Mac.
- Use only music you own or are authorised to process.
- GarageBand or another instrument supplies the final sound; MIDI does not
  contain a stem's exact texture, voice or effects.
- Mixed or noisy stems and melody extraction remain difficult. Automatic
  results are useful starting points, not ground truth.
- The current release is an alpha local macOS application. A hosted service
  for people without suitable hardware is a future direction.

## Contribute

Reports from beginners, other Macs, other DAWs, separation results, operating
systems and AI tools are especially useful. Use the
[beginner first-song report](https://github.com/N9-Developer-Empowerment/sunofriend/issues/new?template=beginner-first-song.yml),
the
[DAW / AI compatibility report](https://github.com/N9-Developer-Empowerment/sunofriend/issues/new?template=daw-ai-compatibility.yml),
or read [CONTRIBUTING.md](CONTRIBUTING.md).

## Contact and support

For a private or general enquiry, email
[hello@sunofriend.com](mailto:hello@sunofriend.com). Please do not email stems,
vocals, unreleased music, MIDI, project files or private review notes.

Use the public issue forms for reproducible first-song and compatibility
reports. For a security concern, follow [SECURITY.md](SECURITY.md) and do not
open a public issue. The full routes and privacy notice are at
[sunofriend.com/contact](https://sunofriend.com/contact/).

Sunofriend is licensed under [Apache-2.0](LICENSE).
