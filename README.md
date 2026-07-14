# Sunofriend

![Sunofriend — From AI stems to playable MIDI](assets/brand/sunofriend-banner-v2.png)

Sunofriend converts separated Suno/Moises audio stems into editable,
timing-locked MIDI for GarageBand. It preserves what was actually heard,
separates uncertain alternatives for auditioning, and clearly labels notes
that were repaired or musically inferred.

It complements Suno, Moises and GarageBand rather than replacing them: use
Suno to generate a song, Moises to export stems and chords, Sunofriend to make
clean MIDI resources, and GarageBand to choose instruments and finish the mix.

## What Sunofriend can do

| Goal | Command | Timing and data contract |
| --- | --- | --- |
| Convert a complete folder of instrumental stems | `listen-all` | Stem-locked MIDI with exact, repair and reconstruct policies |
| Turn lead or backing vocals into playable melodies | `vocal-melody` | pYIN/Basic Pitch consensus, repeated-phrase repair, hummed guidance and editable correction artifacts |
| Apply reviewed melody edits | `melody-apply` | Validated correction JSON becomes tuned GarageBand-ready MIDI |
| Speed up or slow down finished MIDI | `midi-tempo` | Only tempo events change; tracks, notes and groove ticks are untouched |
| Put complete MIDI in a new key and BPM | `midi-transform` | Semitone transposition plus tick-preserving tempo change; channel 10 drums stay fixed |
| Put two performances on one starting bar | `midi-anchor` | Recommended mashup operation: one constant shift preserves natural tempo wander |
| Force stem-derived MIDI onto straight bars | `midi-align` | Experimental 4/4 note-only rebuild through the source metronome map |
| Inventory and sound-match instruments | `instrument-inventory`, `instrument-match` | Installed GarageBand assets and Audio Units plus audio-based audition rankings |
| Make a playable instrument from isolated stem notes | `sample-pack` | GarageBand-selectable AUSampler preset, self-contained SF2 bank, audition MIDI/WAV and extraction evidence |
| Keep MIDI, sound and instrument matches together | `instrument-bundle` | Portable Bundle v1 with performance MIDI, source-derived instrument, reference audio, rankings and A/B previews |
| Store and version reusable parts | `clip-import`, `clip-transform`, `clip-export` | Immutable Clip v1 assets with explicit musical or stem-locked timing |
| Preview or route MIDI to an instrument | `preview`, `play` | FluidSynth WAV preview or CoreMIDI/IAC playback |

For combining songs, first use `midi-transform` to choose a common key, BPM
and tuning, then use `midi-anchor` to place confirmed downbeats on the same
bar. Same-mode key changes are exact semitone shifts, but register, instrument
range and simultaneous chord/melody compatibility still need listening and
arrangement decisions. Use `midi-align` only when a fully straight grid is
more important than preserving the performances' original breathing.

## Hear what it can do

<p align="center">
  <img src="assets/social/the-aisle-at-lidl-square-v2.png" width="560" alt="The Aisle at Lidl: a Sunofriend worked example, shown as a cyan and coral MIDI supermarket aisle">
</p>

**[Listen to Version 1 of “The Aisle at Lidl” on SoundCloud](https://soundcloud.com/ezzye-1/the-aisle-at-lidl?si=97cf744ff4a743bca875bec3db88024f&utm_source=clipboard&utm_medium=text&utm_campaign=social_sharing).**

The maintainer wrote the song and has approved it as a public example of a
Suno → Moises → Sunofriend → GarageBand workflow. The repository includes a
compact [worked-example pack](examples/the-aisle-at-lidl/) with repair and
reconstruct MIDI files, role/family alternatives and measured results. The
full stems are intentionally omitted from Git because they total about 765 MB;
the finished audio remains available through SoundCloud.

Ready-to-post artwork and suggested copy for X, Bluesky, Threads, Instagram,
Facebook, WhatsApp and Slack are in the [social media kit](SOCIAL.md). Brand
files and generation notes are under [`assets/`](assets/).

## Use Sunofriend as an AI-agent skill

The repository includes one portable [Sunofriend Agent Skill](skills/sunofriend/)
for Codex and Claude Code. The skill is the conversational front end: it
inventories a stem folder, chooses safe commands, runs capability checks,
keeps source audio local, validates the JSON/MIDI outputs and explains what to
import into a DAW. The packaged Python CLI remains the deterministic audio and
MIDI engine.

The checked-in discovery links expose the same skill without maintaining two
copies:

- Codex reads [`.agents/skills/sunofriend`](.agents/skills/sunofriend).
- Claude Code reads [`.claude/skills/sunofriend`](.claude/skills/sunofriend).

Clone the repository, install Sunofriend as below, start either agent in the
repository and ask, for example:

```text
Use $sunofriend to convert /absolute/path/to/stems into repair-mode
GarageBand-ready MIDI and validate every main part.
```

Installing the Python wheel or `uv` tool installs the deterministic CLI, not
the agent discovery links. Clone-first is therefore the supported skill setup.
To use the same clone from projects elsewhere on the machine, link it into the
two user skill directories (each command fails safely if a skill already
exists there):

```bash
mkdir -p "$HOME/.agents/skills" "$HOME/.claude/skills"
ln -s "$PWD/skills/sunofriend" "$HOME/.agents/skills/sunofriend"
ln -s "$PWD/skills/sunofriend" "$HOME/.claude/skills/sunofriend"
```

Claude Code also supports explicit `/sunofriend ...` invocation. Both tools
can select the skill implicitly for stem-to-MIDI, vocal-melody, tempo,
transposition, mashup-alignment and Clip v1 requests. The skill does not
separate stems, master audio, edit the GarageBand GUI or make audio uploads.
See the current [Codex skill documentation](https://developers.openai.com/codex/skills)
and [Claude Code skill documentation](https://code.claude.com/docs/en/skills)
for personal/global installation options.

## Getting started (macOS)

### 1. Install Sunofriend and its audio tools

Use Python 3.9–3.11; Python 3.11 is the recommended installation target. The
following contributor setup uses the dependency versions tested on Apple
Silicon and installs FluidSynth for offline MIDI previews:

```bash
git clone https://github.com/N9-Developer-Empowerment/sunofriend.git
cd sunofriend
brew install python@3.11 fluid-synth
"$(brew --prefix python@3.11)/bin/python3.11" -m venv .venv
.venv/bin/python -m ensurepip --upgrade
.venv/bin/python -m pip install -c constraints-audio-macos.txt -e '.[all,dev]'
```

For an isolated end-user command rather than an editable development checkout,
install from the cloned repository with `uv`:

```bash
brew install uv fluid-synth
uv tool install --python 3.11 \
  --constraints constraints-audio-macos.txt \
  '.[all]'
sunofriend --version
```

Once a release is published to PyPI, the source argument becomes
`'sunofriend[all]'`. A lightweight install without `[all]` supports pure MIDI
tempo/key/alignment and Clip v1 work, but not audio transcription, preview or
live playback. FluidSynth is deliberately a system dependency rather than a
Python package.

Install the validated GeneralUser GS 2.0.3 SoundFont:

```bash
mkdir -p "$HOME/.local/share/sunofriend/soundfonts"
curl --fail --location \
  "https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/684543d5e5efaef08d02be50dcda8d552478fa60/GeneralUser-GS.sf2" \
  --output "$HOME/.local/share/sunofriend/soundfonts/GeneralUser-GS.sf2"
echo "9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe  $HOME/.local/share/sunofriend/soundfonts/GeneralUser-GS.sf2" \
  | shasum -a 256 -c -
```

### 2. Check the installation

```bash
.venv/bin/sunofriend doctor --require convert
```

The command exits successfully when `convert_ready` is true. Use
`--require transcribe` for vocal extraction that does not need FluidSynth,
`--require preview` for offline rendering, `--require playback` for CoreMIDI,
or `--require all` for the complete setup. `listen_ready` remains as a
compatibility alias, while top-level `ready` additionally confirms a live
CoreMIDI destination for `play`. The standard Basic Pitch path uses ONNX
Runtime, so TensorFlow/TFLite warnings are harmless when the transcription or
conversion checks pass.

### 3. Prepare a stem export

Put one song's files in a folder whose name includes its key, BPM and tuning:

```text
My Song-B major-119bpm-440hz/
├── My Song-kick-B major-119bpm-440hz.wav
├── My Song-snare-B major-119bpm-440hz.wav
├── My Song-hat-B major-119bpm-440hz.wav
├── My Song-bass-B major-119bpm-440hz.wav
├── My Song-keys-B major-119bpm-440hz.wav
├── My Song-metronome-B major-119bpm-440hz.wav   # optional
└── My Song-chords.pdf                            # optional
```

Recognised stem tokens are `kick`, `snare`, `hat`, `cymbals`, `toms`,
`other_kit`, `bass`, `keys`, `piano`, `strings`, `lead`, `synth` and
`metronome`. The chord filename must contain `chords`. If key or BPM is not in
the folder name, provide `--key "B major"` and `--bpm 119` explicitly.

Lead and backing vocal stems use the separate `vocal-melody` workflow. They are
not added automatically to `listen-all`, because continuous vocal pitch and
polyphonic harmony need different evidence and uncertainty rules.

### 4. Convert your first song

Start with `repair`, the conservative default:

```bash
STEMS="/absolute/path/to/My Song-B major-119bpm-440hz"
OUT="work/my-song-v2"

.venv/bin/sunofriend listen-all "$STEMS" \
  --out-dir "$OUT" \
  --conversion-mode repair
```

Sunofriend discovers the stems, chord PDF and metronome, evaluates each MIDI
against its source stem, and prints the exact GarageBand tempo. The first build
looks like this:

```text
work/my-song-v2/
└── mode_repair/
    ├── full_arrangement.mid
    ├── kick_listened.mid
    ├── kick_provenance.json
    ├── kick_evaluation.json
    ├── ...other parts...
    ├── variants/
    └── listen_all_summary.json
```

### 5. Import into GarageBand

1. Set GarageBand to the exact `set GarageBand tempo to` value printed by
   Sunofriend before importing anything.
2. Place the audio stems and MIDI regions at the same project timeline origin.
3. Leave MIDI quantisation off and disable audio tempo-follow/stretching for
   the stems.
4. Import `mode_repair/full_arrangement.mid`, or import individual
   `<part>_listened.mid` files when you want separate control.
5. Choose the real GarageBand patch by ear. Audition family, `possible` and
   `uncertain` alternatives from `mode_repair/variants/` separately.

## How to

### Turn lead or backing vocals into an instrumental melody

Use `vocal-melody` for an isolated `vocals` or `backing_vocals` stem:

```bash
.venv/bin/sunofriend vocal-melody \
  "$STEMS/My Song-vocals-B major-119bpm-440hz.wav" \
  --role lead \
  --out-dir "$OUT/vocal_melody/lead"

.venv/bin/sunofriend vocal-melody \
  "$STEMS/My Song-backing_vocals-B major-119bpm-440hz.wav" \
  --role backing \
  --out-dir "$OUT/vocal_melody/backing"
```

The default lead path compares the continuous pYIN contour with independent
Basic Pitch note hypotheses. Agreement increases confidence; disagreement is
kept below the clean threshold rather than silently choosing a tracker. The
recommended melody is accompanied by strict, simplified and gently quantised
choices. When a weak source note completes a phrase that is already repeated
with at least three clean note anchors, `phrase_repaired` promotes that
observed note and records the repeated offset in provenance. No chord or key
rule invents the missing note.

Each run also writes `melody_correction.html` and `melody_corrections.json`.
The local HTML page overlays the waveform, F0 contour and MIDI notes; it can
transpose, move, resize, split, merge or remove notes and export reviewed JSON:

```bash
.venv/bin/sunofriend melody-apply \
  "$HOME/Downloads/melody-corrections-edited.json" \
  --out "$OUT/vocal_melody/lead/reviewed-lead.mid"
```

If automatic extraction cannot tell which continuous line you intend, record
a rough hum against the same song and use it as a guide:

```bash
.venv/bin/sunofriend vocal-melody \
  "$STEMS/My Song-vocals-B major-119bpm-440hz.wav" \
  --role lead \
  --guide "$HOME/Music/my-song-hummed-guide.wav" \
  --prefer-guide \
  --out-dir "$OUT/vocal_melody/guided-lead"
```

Sunofriend searches a small time offset and constant register difference, but
retains a guide note only where the source contour supports it. Use
`--guide-offset-seconds` when the recording offset is known. Backing vocals
also publish a dominant line, top line and full harmony stack when the audio
supports them. A noise-floor stem remains `no-evidence`.

You do not need to hum a complete song. For a more manageable workflow, cut a
10–15 second reference excerpt, record a matching hum (or `oo`, `la`, whistle,
or single-note instrument), and supply the approximate excerpt start time in
the full song. Repeat `--guide-snippet` for as many sections as needed:

```bash
.venv/bin/sunofriend vocal-melody \
  "$STEMS/My Song-vocals-B major-119bpm-440hz.wav" \
  --role lead \
  --guide-snippet "$GUIDES/verse-reference.wav" "$GUIDES/verse-hum.wav" 42.5 \
  --guide-snippet "$GUIDES/chorus-reference.wav" "$GUIDES/chorus-hum.wav" 87.0 \
  --prefer-guide \
  --out-dir "$OUT/vocal_melody/snippet-guided-lead"
```

The start time may be approximate: Sunofriend searches two seconds either side.
It finds a separate comfortable-register transposition for every snippet, then
remeasures each accepted pitch in the complete vocal stem. `snippet_guides`
contains only the accepted short sections; `snippet_patched` retains the
automatic full-song melody and replaces only notes overlapping accepted hums.
With `--prefer-guide`, the safer full-song `snippet_patched` result becomes the
primary MIDI and correction-page seed.

For easier tracking, use headphones, start the reference and recording at the
same phrase boundary, keep the source tempo, and sing a steady open vowel such
as `oo`. The pitch may be in any comfortable octave. Rhythm and the direction
of the tune matter more than vocal quality; uncertain notes still cannot bypass
the source-vocal evidence gate.

The command honours tuning in the folder name. A source recorded at A=429, for
example, receives a stem-matching pitch bend of about -43.83 cents plus a
separate A=440 concert-pitch file. See [Vocal melody extraction](docs/VOCAL_MELODY.md)
for the signal model, variants, metrics and GarageBand workflow.

### Choose how much Sunofriend may change

| Mode | Use it when | Main-output policy |
| --- | --- | --- |
| `exact` | You want only confident audio evidence | No theory-generated pads or pattern completion |
| `repair` | You want a faithful but cleaner conversion | Confidence-backed pitch, timing, register and recurring-pattern repairs |
| `reconstruct` | A stem is weak and you want a creative replacement | Clearly labelled chord, bass and drum-pattern inference is allowed |

Every mode owns a separate directory, so comparing them cannot overwrite a
previous result. Using the `STEMS` and `OUT` variables from the first
conversion:

```bash
.venv/bin/sunofriend listen-all "$STEMS" \
  --out-dir "$OUT" --conversion-mode exact
.venv/bin/sunofriend listen-all "$STEMS" \
  --out-dir "$OUT" --conversion-mode reconstruct
```

The results are in `mode_exact/`, `mode_repair/` and `mode_reconstruct/`.

### Worked example: The Aisle at Lidl

The committed [example pack](examples/the-aisle-at-lidl/) contains the selected
MIDI outputs. The ignored local golden `work/Lidl-B major-119bpm-440hz` contains
two kick and snare timbres, a walking bass, layered keys and separator
artefacts. Substitute your own export when the local audio is absent. This
command deliberately requests `pads` as well, demonstrating that repair mode
reports and skips a part that would require reconstruction:

```bash
LIDL_STEMS="work/Lidl-B major-119bpm-440hz"
LIDL_OUT="work/lidl-v2"

.venv/bin/sunofriend listen-all "$LIDL_STEMS" \
  --out-dir "$LIDL_OUT" \
  --parts bass,cymbals,hat,keys,kick,other_kit,pads,snare,strings,toms \
  --conversion-mode repair \
  --max-iterations 2
```

This run detects an average grid BPM of `118.926`, prints GarageBand tempo
`119`, and publishes nine usable tracks; pads are correctly skipped because
repair mode does not invent a missing pads stem. Current golden results are:

| Part | Main result | Useful alternatives |
| --- | ---: | --- |
| Kick | 240 hits: 177 deep + 63 high | 12 `possible` hits |
| Snare | 249 hits: 122 body + 127 bright | 50 `possible` hits |
| Hat | 484 hits: 337 closed + 147 open | 69 `possible` hits |
| Cymbals | 18 hits: 3 crash + 15 ride | 6 `possible` hits |
| Toms | 91 classified hits | 7 `possible` hits |
| Other kit | 189 classified mixed-kit hits | 182 `uncertain`, 42 `possible` |
| Bass | 191-note contour-clean line | 204 `raw_verified`, 191 `root_safe` |
| Keys | 1,227 notes: 533 melody + 694 accompaniment | 251 `uncertain` |
| Strings | 277 source-observed notes | Reconstruct separately when desired |

The selected part files are under
`mode_repair/selected_bass-cymbals-hat-keys-kick-other-kit-pads-snare-strings-toms/`.
Its arrangement and summary sit one level higher in `mode_repair/`, prefixed
with `selected_arrangement_` and `listen_all_summary_` respectively.

### Lidl reconstruction without doubled chords

For the same Lidl song, reconstruct only the parts that benefit from musical
inference:

```bash
.venv/bin/sunofriend listen-all "$LIDL_STEMS" \
  --out-dir "$LIDL_OUT" \
  --parts hat,bass,keys,strings,pads \
  --conversion-mode reconstruct \
  --max-iterations 1
```

The resulting arrangement contains 521 hats, a 191-note chord-root-safe bass,
533 melody-role keys notes and 340 pad notes. The 694-note keys accompaniment
and 61-note reconstructed strings part remain audition choices rather than
doubling the chart harmony in the arrangement. Hat provenance distinguishes
468 observed, 16 repaired and 37 inferred hits; all reconstructed bass, pads
and strings notes are explicitly labelled `inferred`.

Files are under `mode_reconstruct/selected_bass-hat-keys-pads-strings/`; the
GarageBand arrangement is
`mode_reconstruct/selected_arrangement_bass-hat-keys-pads-strings.mid`.

### Speed up or slow down finished MIDI tracks

Use `midi-tempo` after stem conversion when you want the same notes, bars and
groove to play at a new tempo. This example turns every MIDI file under a song
output—including nested variants—from 113 BPM into 125 BPM:

```bash
.venv/bin/sunofriend midi-tempo \
  work/my-song-v2/mode_repair \
  --from-bpm 113 \
  --to-bpm 125 \
  --out work/my-song-125bpm
```

The command preserves the relative directory layout and changes only MIDI
tempo events. Note and controller ticks, bars, durations in beats, track names,
channels, programs, velocities, pitch bends, automation and other MIDI
metadata remain unchanged. At 125 BPM the elapsed duration is `113 / 125 =
0.904` of the original, so the result is 9.6% shorter while retaining the same
musical structure.

For just the combined arrangement:

```bash
.venv/bin/sunofriend midi-tempo \
  work/my-song-v2/mode_repair/full_arrangement.mid \
  --from-bpm 113 \
  --to-bpm 125 \
  --out work/my-song-125bpm/full_arrangement.mid
```

Slowdown uses the same command with a lower target—for example
`--from-bpm 125 --to-bpm 100`. You may omit `--from-bpm` when every input MIDI
contains one unambiguous tempo at tick zero; specifying it is safer because it
catches accidental files from another song. For tempo-less MIDI it declares
the tempo supplied by the original DAW project; without it, the Standard MIDI
File default of 120 BPM is used. Existing outputs are protected unless
`--overwrite` is supplied. With no `--out`, Sunofriend creates a sibling file
or directory whose name ends in the target BPM.

Set GarageBand to **125 BPM before importing** the transformed files and place
all tracks at the same project origin. Leave quantisation off if you want to
retain the original groove. This is an intentional speed change: the new MIDI
will no longer align with the original 113 BPM audio stems unless those stems
are separately time-stretched by the same ratio. Provenance/evaluation
sidecars are therefore not copied into a directory retime.

### Put complete MIDI songs in one key and tempo

Use `midi-transform` when a complete multitrack file or output tree needs both
key and BPM changes. Unlike Clip v1, it patches the Standard MIDI File without
rebuilding its tracks, controllers or metadata. This C-major-to-G-major example
uses the nearest downward interval and changes 85 BPM to 89 BPM:

```bash
.venv/bin/sunofriend midi-transform \
  work/song-c-major-85bpm/full_arrangement.mid \
  --out work/song-g-major-89bpm/full_arrangement.mid \
  --from-bpm 85 --to-bpm 89 \
  --semitones -5 \
  --concert-pitch
```

Pitched note-on/off events move by the requested semitones; General MIDI
channel 10 drum notes do not. The operation rejects an out-of-range pitch
rather than clipping it. Tempo events change at unchanged ticks, preserving
bars, groove, programs, controllers, automation and velocities.

`--concert-pitch` removes only the exact constant RPN/pitch-bend tuning setup
written by Sunofriend when it is safe to do so. The JSON report says how many
setups were removed. Unknown or expressive pitch bends are retained, so a
request is not itself proof that a third-party MIDI file is at A=440. Raw
transposition also does not rewrite key-signature or chord-text metadata;
Sunofriend-generated stem MIDI currently contains neither.

### Give two performances a common starting downbeat

Changing BPM preserves each performance's tempo wander, so two independently
performed songs can still start on different downbeats and drift later. Use
`midi-anchor` to place a confirmed downbeat at a shared bar without quantising
or flattening the groove:

```bash
.venv/bin/sunofriend midi-anchor \
  work/song-c-major-85bpm/full_arrangement.mid \
  --out work/song-g-major-89bpm/bar-aligned.mid \
  --source-downbeat-seconds 0.79987 \
  --from-bpm 85 --to-bpm 89 \
  --target-downbeat-beat 4 \
  --semitones -5 --concert-pitch
```

In 4/4, output beat 4 is the start of bar 2, leaving a one-bar count-in for
pickups. The command first performs the raw key/tempo/tuning transform and then
adds one constant tick offset to musical notes, timed controllers, automation
and markers. Tick-zero conductor and instrument setup remains at tick zero.
The audit reports the source tick, target tick and applied shift.

Use a metronome click plus drum phase to confirm the source downbeat; the first
detected click is not necessarily beat 1 of a bar. Later song sections may
still need manual region alignment because one constant shift deliberately
retains both performances' different rubato shapes.

### Experiment with a completely straight bar grid

`midi-align` non-linearly maps a stem-derived MIDI performance through its
metronome click map onto an exact straight grid:

```bash
.venv/bin/sunofriend midi-align \
  work/song-c-major-85bpm/full_arrangement.mid \
  --metronome work/song-c-major-85bpm/metronome.wav \
  --source-bpm 85 --target-bpm 89 \
  --source-downbeat-beat 1 --count-in-bars 1 \
  --semitones -5 \
  --out work/song-g-major-89bpm/grid-locked.mid
```

This is a creative, 4/4, note-only rebuild at 480 PPQ. It preserves track
names, channels, initial programs, note-on velocities and within-beat
placement, but discards controllers/sustain, later bank/program changes,
pitch bend, aftertouch, SysEx, release velocity, and key/chord/lyric/marker
metadata. Playback assumes an A=440 receiver. Grid locking can flatten useful
tempo breathing or magnify a wrongly decoded pickup, so audition a short
section before processing a whole song. Prefer `midi-anchor` for the first
mashup pass.

### Re-run only the parts you want to improve

`--parts` is comma-separated. The output directory suffix is sorted so the
same selection always has the same location:

```bash
.venv/bin/sunofriend listen-all "$STEMS" \
  --out-dir "$OUT" \
  --parts kick,bass,keys \
  --conversion-mode repair \
  --evaluate-variants
```

This writes part files beneath `mode_repair/selected_bass-keys-kick/`, plus
`mode_repair/selected_arrangement_bass-keys-kick.mid` and
`mode_repair/listen_all_summary_bass-keys-kick.json`. Other full or selected
builds remain untouched.

### Convert and diagnose one stem

Use `listen` when you are tuning one problem part. Substitute the real path to
one of your stems:

```bash
STEM="/absolute/path/to/My Song-B major-119bpm-440hz/My Song-kick-B major-119bpm-440hz.wav"

.venv/bin/sunofriend listen "$STEM" \
  --kind kick \
  --bpm 119 \
  --out-dir work/single-kick \
  --conversion-mode repair \
  --evaluate-variants
```

The main MIDI is `work/single-kick/mode_repair/kick_listened.mid`. Provenance,
iteration history, evaluation and conversion summary files are beside it;
alternatives are under `mode_repair/variants/`.

Single-stem bass, lead or synth repair can also use explicit theory and timing
inputs. Use `--conversion-mode reconstruct` instead when you explicitly want a
chart-built replacement such as pads:

```bash
.venv/bin/sunofriend listen path/to/bass.wav \
  --kind bass --bpm 119 --key "B major" \
  --chords-pdf path/to/chords.pdf \
  --metronome path/to/metronome.wav \
  --out-dir work/single-bass \
  --conversion-mode repair
```

### Evaluate MIDI without reconverting it

```bash
.venv/bin/sunofriend evaluate \
  "$STEM" \
  work/single-kick/mode_repair/kick_listened.mid \
  --kind kick \
  --out work/single-kick/kick-check.json

jq '{
  notes: .note_count,
  strong_f1: .onsets.strong.f1,
  possible_f1: .onsets.possible.f1,
  timing_p95_ms: .onsets.timing.absolute_error_p95_ms,
  drift_ms: .onsets.timing.drift_ms,
  families: .drums.family_counts
}' work/single-kick/kick-check.json
```

For the Lidl kick golden, this reports possible-tier F1 `0.8511`, timing p95
`16.34 ms`, drift `-2.79 ms`, and the two kick-family counts shown above.

### Preview or play MIDI through GarageBand

Render an offline WAV with the configured SoundFont:

```bash
.venv/bin/sunofriend preview \
  work/single-kick/mode_repair/kick_listened.mid \
  --out work/single-kick/kick-preview.wav
```

Or play the MIDI into an armed GarageBand software-instrument track:

```bash
.venv/bin/sunofriend midi-ports
.venv/bin/sunofriend play \
  work/single-kick/mode_repair/kick_listened.mid \
  --port "GarageBand Virtual In"
```

Replace `GarageBand Virtual In` with the exact or uniquely matching destination
shown by `midi-ports`. `play` auditions the notes; it does not start recording
in GarageBand.

### Discover, match and make instruments

See what is already available before downloading anything:

```bash
.venv/bin/sunofriend instrument-inventory \
  --out work/instruments/installed.json
```

Then compare an aligned stem/MIDI pair with the installed GarageBand/Logic
sample assets and role-appropriate rendered instruments:

```bash
.venv/bin/sunofriend instrument-match \
  "$LIDL_STEMS/Lidl-bass-B major-119bpm-440hz.wav" \
  examples/the-aisle-at-lidl/midi/repair/bass-contour-clean.mid \
  --kind bass \
  --out-dir work/instruments/lidl-bass
```

The output is a GarageBand audition guide, JSON evidence, a relative timbre
graph and the best General MIDI proxy MIDI/WAV pairs. Scores shortlist the
candidates examined; they are not certainty percentages. Factory-family
matches include related installed sampler-preset names where available.
`listen-all` also records an exact `instrument_match_command` for every
successful part.

If the stem has isolated notes and you have the right to sample it, make a
portable sample instrument:

```bash
.venv/bin/sunofriend sample-pack \
  "$LIDL_STEMS/Lidl-bass-B major-119bpm-440hz.wav" \
  examples/the-aisle-at-lidl/midi/repair/bass-contour-clean.mid \
  --kind bass \
  --name "Lidl Walking Bass" \
  --out-dir work/sample-packs/lidl-bass
```

The self-contained sample bank is `sunofriend-instrument.sf2`; it embeds the
samples, MIDI root pitches, key ranges and measured cents corrections.
GarageBand's AUSampler preset chooser does not directly select raw SF2 files,
so on macOS Sunofriend also creates `sunofriend-instrument.aupreset`, a small
GarageBand-selectable wrapper that points AUSampler to that bank. Keep both
files at their generated paths. Sunofriend also writes the source-quality
24-bit WAV zones, portable SFZ, JSON report, `garageband-audition.mid`, and an
audition WAV rendered from the exact generated SF2. Overlapping notes are
rejected unless deliberately enabled.

To load it in GarageBand:

1. Drag `garageband-audition.mid` into the Tracks area to create a software
   instrument track, then select that track.
2. Open Smart Controls and replace the instrument plug-in with **AU Instruments
   > Apple > AUSampler > Stereo**.
3. Open AUSampler's preset menu (normally labelled **Manual**), choose its
   load/open setting command, and select `sunofriend-instrument.aupreset`.
   Do not select the `.sf2` bank directly; GarageBand greys it out in this
   preset chooser.
4. Audition every mapped note, then save the configured track as a custom patch
   if you want to reuse it.

By default, one sample covers no more than six semitones on either side, and
stable pitched samples are corrected by up to 99 cents. Use `--max-transpose`
to narrow the mapping, `--no-auto-tune` to retain the raw sample tuning, or
`--no-preview` when FluidSynth is unavailable. Separator bleed, effects and
transitions are baked into samples, so audition carefully and sample only
recordings you own or may legally reuse. Sample Instrument v2 does not yet add
seamless sustain loops or velocity layers.

For the normal end-to-end handoff, combine the performance, sound and matches
in one Instrument Bundle v1:

```bash
.venv/bin/sunofriend instrument-bundle \
  "$LIDL_STEMS/Lidl-bass-B major-119bpm-440hz.wav" \
  examples/the-aisle-at-lidl/midi/repair/bass-contour-clean.mid \
  --kind bass \
  --name "Lidl Walking Bass" \
  --out-dir work/instrument-bundles/lidl-bass
```

The bundle contains `performance.mid`, a local `source-reference.wav`, the
complete match report, the source-derived SF2/AUSampler instrument when safe
isolated notes exist, full-performance and best-GM previews where rendering is
available, plus `instrument_recipe.json`. Apple factory content is never
copied: its result is a local patch shortlist. If safe sampling is impossible,
the bundle is explicitly `partial` but still retains the editable MIDI, source
reference and match evidence.

GarageBand can install its additional Apple sound library and compatible
third-party 64-bit Audio Unit instruments. Sunofriend inventories locally
exposed instruments but does not download plug-ins or write private Apple
patch files. The generated SF2 uses the public sound-bank interface supported
by Apple's sampler. The full method, installation links, score meanings and audition
workflow are in [Instruments and sound matching](docs/INSTRUMENTS.md).

### Store, find and transform reusable MIDI clips

Archive generated parts with exact source timing and musical beat positions:

```bash
LIBRARY="$HOME/.local/share/sunofriend/library"

.venv/bin/sunofriend listen-all "$STEMS" \
  --out-dir "$OUT" \
  --parts bass,keys \
  --conversion-mode repair \
  --library "$LIBRARY"

.venv/bin/sunofriend clip-list \
  --library "$LIBRARY" --role bass --key "B major"
```

Copy a returned clip ID into these commands:

```bash
.venv/bin/sunofriend clip-show CLIP_ID --library "$LIBRARY"

.venv/bin/sunofriend clip-transform CLIP_ID \
  --library "$LIBRARY" \
  --target-key "G major" \
  --target-bpm 124 \
  --timing-mode musical \
  --out work/variants/bass-g-major-124.mid

.venv/bin/sunofriend clip-export CLIP_ID \
  --library "$LIBRARY" \
  --timing-mode auto \
  --out work/variants/bass-original-timing.mid
```

Use `musical` timing to preserve bars/beats at a new BPM. Use `stem_locked` to
preserve exact source seconds against the original stems.

## Outputs, instruments and provenance

### Output layouts

- A full batch writes parts, `full_arrangement.mid`, variants and
  `listen_all_summary.json` directly under `<out>/mode_<mode>/`.
- A selected batch writes its part files under
  `<out>/mode_<mode>/selected_<sorted-parts>/`; its uniquely named arrangement
  and summary are in `<out>/mode_<mode>/`.
- A single `listen` run writes its part, provenance, evaluation and conversion
  summary under `<out>/mode_<mode>/`, with alternatives under `variants/`.

Re-running one scope replaces only that scope's generated files. A disappeared,
silent or failed stem cannot leave an obsolete MIDI or arrangement looking
current, and another conversion mode cannot overwrite the result.

### What each instrument gets

| Stem | Conversion behaviour and audition outputs |
| --- | --- |
| Drums | Stereo/multiband onset evidence, `main` and `possible` tiers, measured source confidence and GM family tracks |
| Kick/snare | Deep/high kick and body/bright snare alternatives retain distinct timbres |
| Hats/cymbals/toms | Closed/open, ride/crash and floor/low/mid/high family tracks; recurring hat repair is mode-controlled |
| `other_kit` | Mixed events are classified as kicks, snares, hats, toms or crashes; unknowns stay `uncertain` |
| Bass | Hybrid Basic Pitch + pYIN contour with `raw_verified`, `contour_clean` and `root_safe` choices |
| Keys/piano | Polyphonic evidence separated into melody, accompaniment and `uncertain`; chords constrain accompaniment only |
| Lead/synth | Audio evidence cleaned against the metronome, key and chord chart in repair/reconstruct modes |
| Strings | Source-pitch transcription in exact/repair; reconstruct publishes a chart-based part but keeps it outside the default arrangement for auditioning |
| Pads | Reconstruct-only chart voicings aligned to keys activity; exact/repair do not invent a missing pads stem |

Near-silent separation bleed is skipped. In reconstruct arrangements, keys use
the melody role with chart pads, while reconstructed strings remain
audition-only to avoid doubled or tripled harmony.

### Provenance and semantic reports

Each primary MIDI has `<part>_provenance.json`; every alternative has its own
sidecar under `variants/`. Every note is labelled `observed`, `repaired` or
`inferred`, with confidence tier and instrument family when available.
`confidence_basis` distinguishes measured drum evidence from policy or
aggregate weights.

The independent evaluator reports strong/possible precision, recall and F1;
p50/p95/p99 timing error and full-song drift; drum-family distributions; and
pitched chroma, pitch support, octave accuracy, contour, density and polyphony.
Use `--evaluate-variants` to generate the same report for every alternative.
Use `--no-evaluate` only for a faster exploratory conversion; do not combine
it with `--evaluate-variants`.

When a library is enabled, variants are linked to their primary clip but do not
inherit its FluidSynth score. Their own semantic report is the valid comparison.

## How the refinement loop works

`listen` transcribes a single stem by actually listening to it, then iteratively
refines the result:

1. **Transcribe** — drums via onset detection (~6 ms resolution, velocity from hit
   energy, closed/open hat and tom pitch classification); keys/synth/bass via
   Spotify basic-pitch (polyphonic ML transcription with octave-ghost filtering).
2. **Render** — the candidate MIDI is played back headlessly through FluidSynth +
   a GM SoundFont (the "proxy instrument" — no GarageBand involved).
3. **Compare** — rendered audio vs. the original stem in *feature space* (onset
   times for drums, chroma + onsets for pitched), never raw waveforms, so the
   comparison is less timbre-sensitive. SoundFont attacks, envelopes and
   harmonics can still influence the score, so the permanent GarageBand A/B
   listening check remains important.
4. **Adjust** — supported edits can repair pitch/semitone, octave, timing,
   duration and velocity/dynamics. SoundFont tail peaks are not allowed to
   delete source-observed drum events. Each pitched edit records confidence and
   rationale in the iteration JSON; then the loop repeats until stable.

The automatic repair policy is deliberately conservative. Chord/theory-built
bass, lead, synth and pad parts keep their generated pitch, timing, duration,
grid and note count; stem evidence may refine expression only. Automatic
pitched-note insertion is currently disabled for every pitched part because
the detector cannot safely decide which voice owns a new note. Layered
keys/piano evidence is instead split into melody, accompaniment and uncertain
role tracks.

Supported single-stem kinds are `kick`, `snare`, `hat`, `cymbals`, `toms`,
`other_kit`, `keys`, `piano`, `synth`, `lead`, `pads` and `bass`.

## Configuration and troubleshooting

`SUNOFRIEND_FLUIDSYNTH` overrides the FluidSynth binary. `SUNOFRIEND_SF2`
overrides the default SoundFont, and `SUNOFRIEND_LIBRARY` overrides the default
Clip library location. `listen-all` archives clips only when `--library` is
supplied; the Clip commands themselves also honour `SUNOFRIEND_LIBRARY`.

- If `doctor` reports `render_ready: false`, check FluidSynth and the SoundFont
  path or checksum.
- If `doctor` reports `midi_ready: false`, enable an IAC Driver bus in Audio
  MIDI Setup, or open GarageBand so that it exposes its virtual destination.
- If `doctor` reports `version_consistent: false`, reinstall the editable/tool
  package so the command and source checkout use the same release.
- If metadata cannot be inferred, add `--bpm` and `--key` instead of renaming
  the source files.
- If a run is slow, omit `--evaluate-variants`; use `--no-evaluate` only during
  quick experiments.
- If `instrument-match` cannot render GM auditions, run
  `doctor --require preview` or add `--no-gm` to compare installed factory
  samples only.

### Inspect an existing GarageBand project

Read the supported metadata and instrument evidence from an existing project
without modifying its private project data:

```bash
.venv/bin/sunofriend garageband-info "$HOME/Music/GarageBand/Move your body.band"
```

## GarageBand MIDI Clip v1 reference

Clip v1 stores two explicit timing contracts:

- `stem_locked` preserves exact source seconds so MIDI continues to match its
  original stems, including pickups and measured beat wander.
- `musical` preserves bars/beats and changes elapsed time at a new BPM.

`listen-all --library` can capture both because it has the source audio and
warped beat grid. `clip-import` can only derive seconds from the MIDI file's
tempo events; it cannot recreate alignment to audio that was never supplied.
`clip-export --timing-mode auto` follows the contract stored with the clip.

The earlier worked example shows search, key/BPM transformation and export.
Use `clip-import` for an existing MIDI and `clip-instrument` to save the patch
that worked best in GarageBand:

```bash
LIBRARY="$HOME/.local/share/sunofriend/library"

.venv/bin/sunofriend clip-import \
  work/my-song-v2/mode_repair/full_arrangement.mid \
  --library "$LIBRARY" --key "B major" --tag released

.venv/bin/sunofriend clip-instrument CLIP_ID \
  --library "$LIBRARY" \
  --suggest "Upright Jazz Bass" --suggest "Sub Bass"
```

Both commands create immutable, auditable clip versions. The local library
uses SQLite for search metadata and SHA-256-addressed JSON objects for complete
musical documents. This boundary can later map to DynamoDB metadata and S3
objects without changing the Clip v1 schema.

For stem-locked GarageBand imports, follow the tempo, shared-origin,
quantisation and audio-stretch checklist in Getting started.

## Legacy remake command

The legacy grid-based workflow is retained for compatibility and can run
without the audio/ML extras. It is designed for EDM, hip-hop and club tracks
where drums and bass matter most. It uses separated stems as timing guides and
Moises chords as harmonic structure rather than attempting a literal
performance transcription:

- Kick, snare, hats, cymbals, toms, and other kit stems are detected, quantized, and exported as clean drum MIDI.
- Bass MIDI follows bass/kick rhythmic activity and uses the current chord root.
- Pad/chord MIDI is generated from the Moises chord PDF using smooth voicings.
- A full multitrack MIDI file combines drums, bass, and pads.

From the project folder:

```bash
.venv/bin/sunofriend remake \
  "$HOME/Downloads/Get This Party Start_reference_24bit_44hz_target-14-G major-150bpm-440hz" \
  --out-dir work/get-this-party-start-remake \
  --style edm
```

Outputs:

- `kick_clean.mid`
- `snare_clean.mid`
- `hats_clean.mid`
- `cymbals_clean.mid`
- `toms_clean.mid`
- `other_kit_clean.mid`
- `drums_clean.mid`
- `bass_clean.mid`
- `pads_chords.mid`
- `full_arrangement.mid`
- `chords_extracted.csv`
- `quality_report.json`

Set the GarageBand project tempo to the BPM in `quality_report.json`, then import either `full_arrangement.mid` or the separate MIDI files.

## Contributing and compatibility testing

Sunofriend needs testing beyond the current GarageBand, Suno and Moises
workflow. Contributions are especially useful from people using other DAWs,
music software, hardware MIDI instruments, AI music generators and stem
separators.

Please try the MIDI in [`examples/the-aisle-at-lidl/`](examples/the-aisle-at-lidl/)
or convert your own authorised stems, then report timing, tempo, key, patch,
import or musical-quality issues. The [contributor guide](CONTRIBUTING.md)
describes a short compatibility test and the evidence to collect.

Use the **[DAW / AI compatibility report](https://github.com/N9-Developer-Empowerment/sunofriend/issues/new?template=daw-ai-compatibility.yml)**
for results from Logic Pro, Ableton Live, FL Studio, REAPER, Cubase, Studio One,
Pro Tools, Bitwig, Ardour, LMMS, other AI generators/separators, or hardware.
Use a normal GitHub bug report for implementation defects. Please share only
audio and project material that you own or have permission to distribute.

## Tests

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check src tests
```

The optional local goldens use ignored source/output assets. Move Your Body
checks all 299 kick events; guards precision/recall, median and p95 timing
error, and four-segment drift; verifies
archive/export keeps the real source-second lead-in; and prevents a
theory-generated bass from accepting a role-unsafe high note. Lidl is the
noisy-stem semantic golden: it checks two kick families against an independent
audio reference, drum uncertainty quarantine, mixed-kit classification,
bass alternatives, keys role separation and reconstruct-mode provenance. When
those private assets are absent (for example in CI), only the relevant golden
checks skip; portable synthetic tests still exercise missed/extra/mistimed
notes, stereo cancellation, family classification, octave errors and contour.

## License

Sunofriend is available under the [Apache License 2.0](LICENSE).
