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
| Compare and conservatively repair vocal trackers | `vocal-trackers` | Immutable pYIN/Basic Pitch evidence, optional RMVPE consensus, and Basic Pitch/GAME boundaries accepted only where pYIN and RMVPE agree on pitch |
| Review a lead melody in musical units | `melody-review` | Hash-checked two-to-eight-bar units, repeat suggestions, MIDI/source auditions, explicit human choices and an unreviewed seed that cannot be applied accidentally |
| Refine one unresolved melody unit | `melody-guide` | A short hum, whistle, single-note rhythm or taps adds a fourth alternative only where the vocal stem supports it |
| Learn review hints from your choices | `melody-profile` | Local, deterministic and advisory ranking built only from explicitly reviewed correction files |
| Apply reviewed melody edits | `melody-apply` | Validated correction JSON becomes tuned GarageBand-ready MIDI |
| Speed up or slow down finished MIDI | `midi-tempo` | Only tempo events change; tracks, notes and groove ticks are untouched |
| Put complete MIDI in a new key and BPM | `midi-transform` | Semitone transposition plus tick-preserving tempo change; channel 10 drums stay fixed |
| Put two performances on one starting bar | `midi-anchor` | Recommended mashup operation: one constant shift preserves natural tempo wander |
| Force stem-derived MIDI onto straight bars | `midi-align` | Experimental 4/4 note-only rebuild through the source metronome map |
| Inventory and sound-match instruments | `instrument-inventory`, `instrument-match` | Installed GarageBand assets and Audio Units, explainable rendered auditions, and optional local OpenL3 evidence |
| Make and function-check an instrument from isolated stem notes | `sample-pack` | GarageBand-selectable AUSampler preset, self-contained SF2 bank, every-performance-pitch usability audition, extraction evidence and advisory sustain-loop auditions |
| Review and apply sampler dynamics | `sample-pack-review`, `sample-pack-apply`, `sample-pack-boundary-review`, `sample-pack-boundary-apply` | Explicit listening gates, reviewed velocity layers/boundaries, SFZ round robin, GarageBand A/B banks and embedded v2 rollback |
| Blind-test reviewed instruments | `sample-pack-ab-review`, `sample-pack-ab-resolve` | Hash-pinned source and neutral Candidate A/B performances with a separate answer key and zero sampler changes |
| Keep MIDI, sound and instrument matches together | `instrument-bundle` | Portable Bundle v1 with performance MIDI, reference audio, rankings, A/B previews and a complete-patch fallback when the source sampler is texture-only |
| Learn from explicit DAW patch choices | `instrument-feedback`, `instrument-profile` | Hash-pinned full-mix/solo decisions become a local advisory role profile with no auto-selection, ranking mutation or playability bypass |
| Store and version reusable parts | `clip-import`, `clip-transform`, `clip-export` | Immutable Clip v1 assets with explicit musical or stem-locked timing |
| Preview or route MIDI to an instrument | `preview`, `play` | FluidSynth WAV preview or CoreMIDI/IAC playback |
| Run an optional local AI transcription challenger | `ai-transcribe` | Isolated worker, explicit local checkpoint, raw candidate, MIDI, hashes and immutable logs |
| Test one MIDI-defined layer inside a mixed stem | `midi-mask` | Short, local harmonic target plus residual with persisted reconstruction evidence and no automatic promotion |

Development has started on a local-first ensemble of optional transcription
models, phrase-level melody review and learned instrument matching. See the
multi-week **[AI transcription and instrument roadmap](docs/AI_TRANSCRIPTION_ROADMAP.md)**
for Phase 1–4 goals, licence boundaries, success criteria, current checklist
and daily progress log. The measured backend decisions and final listening
gate are in the **[Phase 1 bake-off close-out report](docs/PHASE1_TRANSCRIPTION_BAKEOFF.md)**.
Phase 3 is complete; its implemented instrument features, reproducible golden
evidence and final GarageBand/loop decisions are recorded in the
**[Instrument Intelligence v2 close-out report](docs/PHASE3_INSTRUMENT_INTELLIGENCE.md)**.
Phase 4 has started with an evidence-first bass/keys golden. The current
experiments, listening order and promotion rules are in the
**[Cleanup and Neural Timbre Lab](docs/PHASE4_CLEANUP_TIMBRE_LAB.md)**. The
**[Phase 4 stabilization review](docs/PHASE4_STABILIZATION_REVIEW.md)**
compares those executions with the original goals and records the gate before
another model experiment begins.

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

### Optional: run a Phase 1 AI transcription challenger

The experimental AI runtime is isolated from the stable Python 3.9 CLI. Set
it up and check it independently:

```bash
brew install uv
scripts/setup-ai-runtime.sh
.venv/bin/sunofriend ai-doctor --require muscriptor
```

MuScriptor code is installed, but its gated CC-BY-NC-4.0 checkpoint is not
downloaded or accepted for you. After you have personally accepted those
terms and placed the checkpoint on disk, transcribe a short authorised excerpt
with an explicit local path:

```bash
.venv/bin/sunofriend ai-transcribe \
  "/absolute/path/to/lead-vocal.wav" \
  --checkpoint "/absolute/path/to/accepted/model.safetensors" \
  --out-dir "/absolute/path/to/work/ai-bakeoff/my-song" \
  --bpm 119 \
  --start-seconds 30 \
  --end-seconds 45 \
  --device auto
```

The standard small-model location is
`~/.local/share/sunofriend/models/muscriptor-small/model.safetensors`. Once it
exists, verify both code and weights with:

```bash
.venv/bin/sunofriend ai-doctor --require muscriptor-checkpoint
```

At that location `--checkpoint` may be omitted. For another accepted local
checkpoint, pass `--checkpoint` or set `SUNOFRIEND_MUSCRIPTOR_MODEL`.

For an independent vocal-specific result, install GAME's pinned official
v1.0.3 small ONNX release explicitly, then run the same authorised excerpt:

```bash
scripts/setup-game-model.sh
.venv/bin/sunofriend ai-doctor --require game

.venv/bin/sunofriend ai-transcribe \
  "/absolute/path/to/lead-vocal.wav" \
  --backend game \
  --out-dir "/absolute/path/to/work/ai-bakeoff/my-song/game" \
  --bpm 119 \
  --instrument voice \
  --start-seconds 30 \
  --end-seconds 45 \
  --language en \
  --device cpu \
  --seed 0
```

The setup script clones the tagged MIT-licensed GAME code and downloads the
official release asset only when the script is deliberately invoked. It pins
the tag commit, release ZIP SHA-256 and all six extracted component hashes.
Inference itself accepts only the existing local ONNX directory, defaults to
`~/.local/share/sunofriend/models/game-1.0.3-small-onnx/GAME-1.0.3-small-onnx`,
and never contacts the network. Override that location with `--checkpoint` or
`SUNOFRIEND_GAME_MODEL`.

GAME preserves its floating MIDI pitch and separate voiced/unvoiced regions in
`candidate.raw.json`; the playable MIDI rounds pitch only at the final MIDI
boundary. Its diffusion boundary decoder is stochastic unless seeded, so
Sunofriend defaults to and records `--seed 0`. `--boundary-threshold`,
`--boundary-radius-ms`, `--presence-threshold` and `--game-steps` expose the
official inference controls for deliberate bake-offs. GAME currently runs
through ONNX Runtime's CPU provider; `mps` is rejected rather than silently
falling back.

RMVPE is the independent frame-level F0 challenger. Its setup is also a
separate, explicit network action:

```bash
scripts/setup-rmvpe-model.sh
.venv/bin/sunofriend ai-doctor --require rmvpe

.venv/bin/sunofriend ai-transcribe \
  "/absolute/path/to/lead-vocal.wav" \
  --backend rmvpe \
  --out-dir "/absolute/path/to/work/ai-bakeoff/my-song/rmvpe" \
  --bpm 119 \
  --instrument "lead vocal" \
  --start-seconds 30 \
  --end-seconds 45 \
  --device cpu
```

This pins `rmvpe-onnx==0.2.3`, the MIT-labelled
`lj1995/VoiceConversionWebUI` model revision
`b2c8cae96e3b05de46d36c5ef9970ef6cbccafba`, and checkpoint SHA-256
`5370e71ac80af8b4b7c793d27efd51fd8bf962de3a7ede0766dac0befa3660fd`.
The authors' reference code is Apache-2.0; the ONNX adapter and labelled model
distribution are MIT. The model stays outside the repository. Normal
diagnostics and inference accept only the existing local `.onnx` file and do
not contact the network.

`rmvpe.frames.json` preserves every model F0 and confidence observation at
about 10 ms resolution. `candidate.raw.json` contains a conservative,
deterministic note draft produced from those frames using a confidence gate,
five-frame median smoothing, short same-pitch gap bridging, pitch hysteresis
and minimum-note cleanup. Tune that explicitly with
`--confidence-threshold`, `--minimum-note-ms`, `--maximum-gap-ms` and
`--pitch-change-semitones`. The frame artifact is the primary model evidence;
the decoded notes are Sunofriend's versioned adapter output, not note
boundaries supplied by RMVPE.

PESTO is the small optional second F0 oracle. It is useful for independent
pitch-class evidence, not as another automatic winner. Install its LGPL-3.0
package in the isolated runtime, fetch the pinned checkpoint explicitly and
run it on the same short excerpt:

```bash
scripts/setup-pesto-model.sh
.venv/bin/sunofriend ai-doctor --require pesto

.venv/bin/sunofriend ai-transcribe \
  "/absolute/path/to/lead-vocal.wav" \
  --backend pesto \
  --out-dir "/absolute/path/to/work/ai-bakeoff/my-song/pesto" \
  --bpm 119 \
  --instrument "lead vocal" \
  --device cpu
```

The setup pins `pesto-pitch==2.0.1` and `mir-1k_g7.ckpt` SHA-256
`16c32e06ddd950e3e4866dfa3c7f8a87c4988f8adf43e57977b189f031f26f3e`.
Every run preserves `pesto.frames.json` plus the untouched activation matrix
in `pesto.activations.npy`. Use `--pesto-step-ms`, `--pesto-reduction`,
`--pesto-chunks` and the shared frame-to-note controls only for deliberate
bake-offs. Phase 1 retains PESTO as a vocal F0 oracle and rejects its decoded
MIDI for the current bass golden; it is not part of automatic consensus.

Add a repeated `--instrument "exact MuScriptor name"` to restrict the model.
Every invocation creates a new run directory and refuses to overwrite an old
one. It contains the request, raw and validated candidates, `candidate.mid`,
worker logs, source/checkpoint hashes and a final `run.json`. It now also
writes:

- `candidate.quality.json`, which flags decoder bursts, implausible density,
  duplicate rectangles, extreme polyphony and restricted-label leakage;
- `candidate.programs.json`, which maps each model role to a conservative
  zero-based General MIDI audition program without changing any note or raw
  model evidence;
- `candidate.expression.json`, containing note-local source-energy evidence;
- `candidate.expression.mid`, with relative source-derived velocities when
  the model supplies none.

Frame-producing backends may declare additional immutable evidence. RMVPE adds
`rmvpe.frames.json`; PESTO adds `pesto.frames.json` and
`pesto.activations.npy`. Every artifact is confined to the run directory and
included with its own hash in `run.json`.

The raw candidate is never mutated. `candidate.mid` therefore keeps neutral
velocity when a backend supplies none, while the separate expression MIDI is
the more playable audition. A model alias such as `small` or a URL is
deliberately rejected so inference cannot trigger an unrecorded checkpoint
download. Neither MIDI has undergone Sunofriend melody repair. Do not promote
or audition a candidate whose quality status is `review-required` until its
warnings have been understood; extreme polyphony can overload a synth.

After a short bake-off has shown that MuScriptor is useful for the material,
MuScriptor and GAME can also be requested directly from the normal vocal
workflow:

```bash
.venv/bin/sunofriend vocal-melody \
  "$STEMS/My Song-vocals-B major-119bpm-440hz.wav" \
  --role lead \
  --out-dir "$OUT/vocal_melody/lead" \
  --muscriptor \
  --game \
  --game-language en \
  --game-seed 0
```

This writes `variants/lead_vocal-muscriptor.mid` and
`variants/lead_vocal-game.mid` (or the corresponding backing-vocal files),
note provenance and separate immutable `ai-runs/<backend>/<run-id>/` records.
Either flag may be used alone. Both GarageBand variants use separately recorded
source-expression velocity layers; provenance identifies recovered velocity
and GAME's original floating pitch, while each raw null-velocity candidate
remains unchanged. They are explicit challengers: neither silently replaces
the deterministic primary or correction-page seed. A `review-required`
quality result is surfaced in `vocal_summary.json`.

For backing vocals, treat GAME and MuScriptor as alternative monophonic
dominant lines and retain Sunofriend's separate polyphonic `harmony-stack`.
The Lidl backing golden gave GAME much stronger onset coverage while
MuScriptor retained better timing and contour, so there is deliberately no
automatic winner or merge. GAME records its language, thresholds, D3PM
schedule, seed and model bundle hash in the summary. CPU is the default for
MuScriptor because it was faster than MPS for the first 15-second golden; use
`--muscriptor-device auto` or `mps` to re-test other hardware and models. The
MuScriptor checkpoint remains optional, gated and CC-BY-NC-4.0; neither model
bundle is included in Sunofriend's Apache-2.0 package.

RMVPE remains outside the automatic `vocal-melody` primary, but its saved
frames can now be compared safely with independent pYIN and Basic Pitch
records:

```bash
.venv/bin/sunofriend vocal-trackers \
  "$STEMS/My Song-vocals-B major-119bpm-440hz.wav" \
  --role lead --bpm 119 --tuning-hz 440 \
  --rmvpe-frames "$RMVPE_RUN/rmvpe.frames.json" \
  --game-candidate "$GAME_RUN/candidate.json" \
  --out-dir "$OUT/vocal-tracker-runs"
```

`vocal-trackers` creates a fresh immutable run. `pyin.evidence.json` retains
every continuous F0 frame and the named contour-to-note adapter;
`basic-pitch.evidence.json` retains the raw note events and exact packaged
model hash. Each has its own MIDI and source comparison. RMVPE is accepted
only when its adjacent immutable `run.json` proves that it analysed the exact
same WAV SHA-256. The optional `consensus.evidence.json` then aligns all three
trackers on the pYIN timeline and records every observation, selected source,
agreement, solo frame, dispute and no-agreement frame. Its MIDI is always an
experimental `review-required` challenger; none of the inputs is modified or
deleted. `--game-candidate` is optional and requires RMVPE. Both saved AI
inputs must belong to completed immutable runs for the exact same WAV and
must match the checkpoint hashes recorded in their adjacent manifests.

When RMVPE is present, Sunofriend also tests note boundaries from raw Basic
Pitch and, when supplied, GAME. A boundary is accepted only where pYIN and
RMVPE are both voiced, agree within 70 cents, support enough of the proposed
note and support its edges. Pitch comes from the equal pYIN/RMVPE midpoint;
tracker confidence values are deliberately not compared as though they shared
one calibrated scale. The run publishes `boundary-basic-pitch.candidate.mid`,
`boundary-game.candidate.mid`, `boundary-repair.candidate.mid` and a complete
`boundary-repair.evidence.json` audit with accepted/rejected reasons and
ranked phrases. These are review candidates, not edits to any raw model file.

On the Lidl goldens, raw Basic Pitch was stronger than consensus v1. Lead
Basic Pitch emitted 71 raw notes with possible-onset F1 `0.4058`, chroma
`0.9323` and supported-note ratio `0.6197`; the 35-note consensus scored
`0.2542`, `0.9253` and `0.3714`. Backing Basic Pitch emitted 52 polyphonic
hypotheses with strong-onset F1 `0.3733`; reducing the three trackers to one
14-note consensus line lost useful harmony evidence. All evidence, evaluation
and MIDI files were byte-identical in fresh repeat runs. The decision is to
keep raw Basic Pitch, pYIN and RMVPE independently auditionable and not promote
consensus v1 into `vocal-melody`. The conservative boundary experiment reduced
the lead to 23 notes and raised strong-onset F1 from consensus's `0.1481` to
`0.3810`, with possible-onset F1 `0.3396` and chroma `0.8872`; it is a useful
phrase-review option, not a new primary. On backing vocals it retained only six
notes and zero supported-note ratio. That negative result is intentional:
retain raw polyphonic Basic Pitch and the normal backing harmony stack rather
than replacing either with a sparse monophonic boundary repair.

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

Add `--muscriptor` when the optional AI runtime and accepted checkpoint are
available and you want its model-backed melody beside these deterministic
variants. Inspect `vocal_summary.json` under `ai_challengers.muscriptor` for
the exact checkpoint hash, raw candidate, run manifest, note count and tuned
GarageBand MIDI path.

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

When `vocal-trackers` has produced an agreed-F0 boundary repair, use
`melody-review` for an easier recognition-first choice:

```bash
.venv/bin/sunofriend melody-review \
  "$OUT/vocal-tracker-runs/RUN_ID" \
  --out-dir "$OUT/lead-phrase-review" \
  --minimum-bars 2 \
  --maximum-bars 8 \
  --beats-per-bar 4
```

The command verifies the source WAV and every input evidence hash, requires a
fresh output and currently accepts lead vocals only. Open
`melody_phrase_review.html` locally. Consecutive note clusters are grouped into
two-to-eight-bar review units and the least-confident units appear first. Bar
duration comes from BPM; this does not pretend the excerpt begins on a known
downbeat. Each unit retains its source-cluster indices and has raw Basic Pitch,
GAME-boundary and combined agreed-F0 choices with a small piano roll, MIDI-only
audio and a source-plus-MIDI overlay. A missing GAME unit is shown as zero
notes and silence rather than invented evidence. Scores are clues, not
automatic winners. Short excerpts or isolated clusters that cannot reach the
minimum are retained with an explicit warning.

When two units have the same absolute-pitch sequence, contour intervals, note
count and closely matching source timing, a **Conservative repeat suggestion**
appears. It is only a suggestion: click **Apply this unit's current choice to
repeat unit …** to confirm it. Sunofriend copies the alternative name, not the
notes, so the target continues to use its own source-backed pitch, timing and
expression. Octave-transposed contours, unequal note counts, sparse phrases
and timing mismatches are rejected. The exported JSON records the source unit,
repeat metrics and fixed policy; `melody-apply` rejects altered evidence or a
propagated choice that no longer matches its source. If no strong pair exists,
the review page shows no propagation control.

Select or explicitly accept every review unit, export
`melody-corrections-reviewed.json`, then use the normal command:

```bash
.venv/bin/sunofriend melody-apply \
  "$HOME/Downloads/melody-corrections-reviewed.json" \
  --out "$OUT/vocal_melody/lead/reviewed-lead.mid"
```

After you have several explicitly reviewed correction files, build a fresh
local profile and use it to put the most similar past choice at the top of a
separate history panel:

```bash
.venv/bin/sunofriend melody-profile \
  "$HOME/Downloads/song-a-melody-corrections-reviewed.json" \
  "$HOME/Downloads/song-b-melody-corrections-reviewed.json" \
  --out "$OUT/my-melody-review-profile-v1.json"

.venv/bin/sunofriend melody-review \
  "$OUT/vocal-tracker-runs/ANOTHER_RUN_ID" \
  --ranking-profile "$OUT/my-melody-review-profile-v1.json" \
  --out-dir "$OUT/another-lead-phrase-review"
```

`melody-profile` accepts only complete phrase-review corrections whose every
choice was explicitly reviewed. Manual choices have full weight; choices that
you explicitly propagated to a repeated unit have half weight. Older reviewed
files without unit context still contribute global counts and produce a
warning. The displayed scores are relative similarity to your local review
history, not confidence or proof of correctness. They never reorder the audio
cards, change the `combined` default, mark a choice reviewed or select a melody
automatically. Profiles and review packages are write-once: to add more choices,
rebuild from all wanted correction files at a new path. No profile or correction
is written outside the paths you provide.

If none of the three automatic versions is recognisable, select **None are
close — add a short guide**, export the unresolved review for its audit, and
record only that numbered unit. You can hum or whistle its contour, play its
rhythm repeatedly on one note, or tap its rhythm:

```bash
.venv/bin/sunofriend melody-guide \
  "$OUT/lead-phrase-review" \
  --unit 2 \
  --guide "$GUIDES/lead-unit-02-hum.wav" \
  --guide-kind hum \
  --search-seconds 0.75 \
  --out-dir "$OUT/lead-unit-02-guided-review"
```

`--guide-kind` accepts `hum`, `whistle`, `contour`, `single-note` or `tap`.
Hum, whistle and contour recordings contribute rhythm and pitch direction;
single-note and tap recordings contribute rhythm only. In every case the
emitted MIDI pitch is remeasured from the original vocal stem. A guide with no
source support produces a zero-note fourth alternative and cannot invent a
melody. The command verifies the complete parent review, tracker run and pYIN
evidence, writes a fresh child review and leaves all automatic candidates
unchanged. Open the new `melody_phrase_review.html`, compare the new **Short
guide + source contour** choice with the original three. This v1 command
evaluates one guide for one unit per child review; use the existing repeatable
`vocal-melody --guide-snippet` workflow when several guided excerpts must be
combined into one full-song candidate.

The generated seed is deliberately `unreviewed`; `melody-apply` refuses it,
an unresolved unit, an incomplete set of choices, or a correction whose source
SHA-256 no longer matches. The resulting `.correction.json` audit retains the
selected alternative for every unit and its original cluster indices. Raw
tracker artifacts are never modified.

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

### Test a MIDI-defined layer inside a mixed pitched stem

Phase 4's experimental `midi-mask` command uses one aligned MIDI track as a
transparent time-and-pitch query. It opens narrow bands around the guide notes
and their harmonics, writes the proposed target, and defines the residual as
the original excerpt minus that target. It is a DSP baseline for later cleanup
models—not a claim that it has recovered the physical original instrument.

Use it on a focused excerpt of at most 60 seconds and a fresh output path:

```bash
.venv/bin/sunofriend midi-mask \
  path/to/keys.wav \
  work/ai-run/candidate.mid \
  --track-index 2 \
  --start-seconds 200 \
  --end-seconds 216 \
  --out-dir work/keys-electric-piano-mask
```

Multi-track MIDI requires an explicit zero-based `--track-index`; the command
lists the available note-bearing track names if it is omitted. The output has
`source-excerpt.wav`, `target.wav`, `residual.wav`, a zero-based
`guide-excerpt.mid` and `midi_mask.json`. The report pins every input/output
hash, measures the persisted PCM24 reconstruction error and confirms that the
source WAV and guide MIDI were not changed.

If the tonal target loses useful attacks, test a separate broadband-onset
challenger rather than altering the first result:

```bash
.venv/bin/sunofriend midi-mask \
  path/to/keys.wav \
  work/ai-run/candidate.mid \
  --track-index 2 \
  --start-seconds 200 \
  --end-seconds 216 \
  --transient-ms 45 \
  --transient-strength 0.35 \
  --out-dir work/keys-electric-piano-mask-with-transients
```

Compare source, target and residual by ear, then transcribe them separately.
Shared harmonics and simultaneous attacks can enter the target; a cleaner
numeric pitch score does not justify replacing the original stem or MIDI.

### Preview or play MIDI through GarageBand

Render an offline WAV with the configured SoundFont:

```bash
.venv/bin/sunofriend preview \
  work/single-kick/mode_repair/kick_listened.mid \
  --out work/single-kick/kick-preview.wav
```

To hear the same MIDI through a Sunofriend source-derived instrument, provide
the bundle or sample pack's self-contained SF2 explicitly:

```bash
.venv/bin/sunofriend preview \
  work/instrument-bundle/performance.mid \
  --soundfont work/instrument-bundle/source-instrument/sunofriend-instrument.sf2 \
  --out work/instrument-bundle/source-instrument-preview.wav
```

This is an offline comparison only. In GarageBand, load the neighbouring
`sunofriend-instrument.aupreset` through AUSampler so that the preset resolves
the same SF2 bank.

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

It also writes `source_event_clusters.json` and a
`source_event_clusters.svg` pitch/timeline view. These group MIDI-aligned
events into candidate timbre families and articulation shapes and flag rare
events for listening. They are advisory: no MIDI note, instrument rank or
sample is changed. With `--embedding-model`, OpenL3 supplies 30% of the event
identity distance while the existing explainable features retain 70%.

The companion `source_event_dynamics.json` and
`source_event_dynamics.svg` look for repeated events that may support quiet
and loud sample layers or alternate round-robin samples. Comparisons stay
inside one timbre family, MIDI note and articulation group. A two-layer
candidate needs at least eight events, at least four and 20% of the unit on
each side, and at least 3 dB between the two median source levels. Alternate
samples are chosen only from at least three isolated events and exclude the
most distant 20% from selection. This is listening evidence only: MIDI notes
and velocities, sample selection, SoundFont zones and drum mappings all remain
unchanged.

For drum roles, the same command also writes a separate channel-10
`drum_family_mapping.proposed.mid`, rendered WAV, per-family candidate report
and assigned one-shot auditions. It never overwrites the input MIDI. Each
timbre family is split by its existing MIDI note first, so useful kick, snare,
hat, tom or cymbal distinctions cannot be collapsed by one broad audio
cluster. A valid existing role note changes in the proposal only when the
alternative reaches a relative score of 55 and leads by at least eight points;
these are conservative policy guardrails, not confidence calibration.

```bash
.venv/bin/sunofriend instrument-match \
  "$LIDL_STEMS/Lidl-kick-B major-119bpm-440hz.wav" \
  examples/the-aisle-at-lidl/midi/repair/kick.mid \
  --kind kick \
  --out-dir work/instruments/lidl-kick-families
```

Listen to `drum_family_mapping.proposed.wav` before importing its MIDI into
GarageBand, then try the intended GarageBand drum kit: GM note timbre varies
by kit. Outliers and unanalyzed hits retain their original notes. `--no-gm`
disables this proposal.

For an independent learned timbre comparison, explicitly install the pinned
OpenL3 music checkpoint and supply its local path. This adds a separate
audition order without changing the default spectral/dynamics/attack ranking:

```bash
scripts/setup-openl3-model.sh

OPENL3="$HOME/.local/share/sunofriend/models/openl3-music-mel128-emb512-3/openl3-music-mel128-emb512-3.onnx"

.venv/bin/sunofriend instrument-match \
  "$LIDL_STEMS/Lidl-bass-B major-119bpm-440hz.wav" \
  examples/the-aisle-at-lidl/midi/repair/bass-contour-clean.mid \
  --kind bass \
  --out-dir work/instruments/lidl-bass-openl3 \
  --embedding-model "$OPENL3"
```

Matching remains offline and never fetches a model implicitly. The output adds
`openl3_embedding_evidence.json` and `gm_embedding_auditions/`; the evidence
pins the OpenL3 and SoundFont hashes and records every aligned active-window
comparison. These are relative shortlist scores, not confidence percentages.
The checkpoint weights are CC-BY-4.0; see the
[OpenL3 project](https://github.com/marl/openl3) and
[Essentia model catalogue](https://essentia.upf.edu/models.html).

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

The sample pack carries the same source-event JSON/SVG and marks exactly which
events became zones. Outliers remain eligible in v1 so a rare musically useful
articulation cannot disappear automatically. Append `--embedding-model
"$OPENL3"` when the optional learned clustering evidence is wanted.
It also carries the dynamics JSON/SVG, but Sample Instrument v2 does not turn
its candidate layers or alternates into zones automatically.
For pitched samples it also writes `source_sample_loops.json`,
`source_sample_loops.svg` and raw repeated-loop WAVs under `loop-auditions/`
when a sample is long enough to analyse. These rank post-attack/pre-release
boundary candidates using waveform and spectral continuity. They are listening
evidence only: the generated SF2 and SFZ remain unlooped, and drum/percussion
one-shots are marked not applicable.

Building a valid SF2 does not prove that it is a usable main instrument.
Instrument Usability Gate v1 checks the generated key/velocity zones against
every note in the supplied MIDI and checks whether the one-shot audio lasts
long enough to make those notes audible. It writes `instrument_usability.json`
and `instrument-usability-audition.mid` (plus a WAV unless `--no-preview`). The
audition plays every distinct performance pitch and then four velocity probes.
`review-required` means the functional checks passed but tone and musical fit
still need listening. `texture-only` means at least one note is unmapped or the
audio is too short: use a complete GarageBand/GM instrument as the main sound
and, if useful, keep the source sampler only as a quiet duplicate texture.
Failed or inconclusive pitch detection remains review evidence; it does not by
itself discard a noisy or percussive sample.

To load it in GarageBand:

1. Drag `garageband-audition.mid` into the Tracks area to create a software
   instrument track, then select that track.
2. Open Smart Controls and replace the instrument plug-in with **AU Instruments
   > Apple > AUSampler > Stereo**.
3. Open AUSampler's preset menu (normally labelled **Manual**), choose its
   load/open setting command, and select `sunofriend-instrument.aupreset`.
   Do not select the `.sf2` bank directly; GarageBand greys it out in this
   preset chooser.
4. Play `instrument-usability-audition.mid` first. Silence or abruptly cut-off
   notes are functional failures, not subjective timbre choices.
5. If the report says `texture-only`, put a normal complete GarageBand patch on
   the main MIDI track. Use the AUSampler track only as an optional quiet layer.
   Otherwise, audition the whole song before saving a custom patch.

By default, one sample covers no more than six semitones on either side, and
stable pitched samples are corrected by up to 99 cents. Use `--max-transpose`
to narrow the mapping, `--no-auto-tune` to retain the raw sample tuning, or
`--no-preview` when FluidSynth is unavailable. Separator bleed, effects and
transitions are baked into samples, so audition carefully and sample only
recordings you own or may legally reuse. Sample Instrument v2 does not
automatically enable sustain loops, velocity layers or round-robin playback.
Its loop and dynamics reports are evidence-led starting points for listening,
not applied sampler mappings. A low loop-continuity score is not proof that a
repeat is musically seamless.

To turn only choices you have actually heard into a separate Sample Instrument
v3 experiment, create a local review:

```bash
.venv/bin/sunofriend sample-pack-review \
  work/sample-packs/lidl-bass \
  --out-dir work/sample-reviews/lidl-bass-v1
```

Open `sample_pack_review.html`. Every candidate now has three pinned auditions:
the exact normalised one-shot, a four-beat excerpt at the stem's shared level
so its source rhythm and bleed remain audible, and a role-aware normalised
audition. Drum/percussion candidates play a repeated two-bar rhythm at the
MIDI's initial tempo; pitched candidates play a short sampler-style pitch
phrase. These contexts are listening evidence only and never choose a sample.
Explicitly accept or reject every unit, choose one primary event per layer and
optionally check other acceptable recordings. If two candidate units share a
MIDI pitch, accept at most one. Export the reviewed JSON, then apply it to a
fresh output:

```bash
.venv/bin/sunofriend sample-pack-apply \
  "$HOME/Downloads/sample_pack_review.reviewed.json" \
  --name "Lidl Walking Bass Reviewed" \
  --out-dir work/sample-packs/lidl-bass-v3
```

Apply refuses an unreviewed document, an unknown event, two accepted units at
one pitch, or changed source, MIDI, v2 sample, SF2, cluster, dynamics or review
audio evidence. The original v2 directory is never edited. The v3 output
always contains the reviewed SF2/AUSampler bank, one common audition MIDI,
optional rendered WAVs, and a self-contained `baseline-v2/` rollback. It adds
velocity zones only when the review accepts layers. It adds sequence round
robin to the SFZ and separate GarageBand A/B banks only when the review accepts
alternate source events. Portable SF2 has no round-robin opcode, so any
GarageBand alternatives remain separate banks rather than pretending to switch
automatically. The report and README state the actual applied feature counts;
rejected proposals are never described as active sampler features.

Apply also creates a musical performance A/B from the reviewed pack's real
source MIDI. It chooses the shortest bar-aligned 8-, 12- or 16-bar window that
covers the source pitch palette where possible, then prefers note density and
the earliest tie. `garageband-performance-ab.mid` retains the selected notes,
velocities and rhythm, shifts the excerpt to bar 1, and routes it to channel 1
for the custom AUSampler bank. Compare `garageband-performance-source.wav`,
`baseline-v2/garageband-performance-v2.wav` and
`garageband-performance-v3.wav`. The source MIDI is hash-checked and never
edited.

To avoid knowing which performance is v2 or v3, build one blinded page from
one or more completed v3 packs:

```bash
.venv/bin/sunofriend sample-pack-ab-review \
  work/sample-packs/lidl-snare-v3 \
  work/sample-packs/lidl-hats-v3 \
  work/sample-packs/lidl-toms-v3 \
  --out-dir work/sample-reviews/lidl-phase3-blind-ab
```

Open `sample_ab_review.html` without opening its separate answer key. The page
copies and pins the source reference plus neutral Candidate A/B performance
WAVs; accepted velocity sweeps use the same hidden mapping. Choose Candidate
A, Candidate B, equivalent or neither for every instrument, mark the page
reviewed and export its JSON. Resolve the labels only after exporting:

```bash
.venv/bin/sunofriend sample-pack-ab-resolve \
  "$HOME/Downloads/sample_ab_review.reviewed.json" \
  --out work/sample-reviews/lidl-phase3-blind-result.json
```

The resolver verifies the unchanged v3 reports, copied WAV manifest and
answer-key hash. Neither command edits MIDI, samples, zones or either bank.

When the review accepts a velocity layer, apply additionally creates
`garageband-velocity-sweep.mid`. It plays coarse quiet-to-loud steps plus dense
steps immediately below and above every accepted boundary. The v2 and v3 WAVs
make the sample switch audible while keeping the reviewed mapping untouched.
Use the sweep to decide whether a separate explicit boundary review is needed;
Sunofriend does not move a boundary from this audition automatically.

If the transition sounds abrupt—or the two sources sound like different
instruments—compare complete mapping choices in a separate, hash-pinned
review. This never preselects even the current mapping:

```bash
.venv/bin/sunofriend sample-pack-boundary-review \
  work/sample-packs/lidl-other-kit-v3 \
  --out-dir work/sample-reviews/lidl-other-kit-boundaries-v1
```

Open `sample_boundary_review.html` in a normal browser. First compare the lower
and upper accepted events with one identical, constant-velocity repeated beat;
this exposes pitch, tone and texture without a MIDI-level change. Then compare
the same velocity ramp through every complete mapping. Choices include the
lower event at all velocities, the upper event at all velocities and each
two-event boundary. The page reports the real source-MIDI velocity range and
warns when a proposed layer would never trigger. Choose exactly one mapping,
mark it reviewed and export the JSON. Keeping the current mapping is also an
explicit choice. Apply only that export to another fresh directory:

```bash
.venv/bin/sunofriend sample-pack-boundary-apply \
  "$HOME/Downloads/sample_boundary_review.reviewed.json" \
  --out-dir work/sample-packs/lidl-other-kit-boundary-reviewed-v3
```

Apply verifies the source v3 report, SF2, SFZ, reviewed decisions, every
source sample, source MIDI/cluster record and every candidate
MIDI/bank/preset/WAV hash. It then rebuilds all v3 artifacts from the original
reviewed sample decisions plus only the selected mapping. A single-source
choice deactivates one already accepted event; it never invents a replacement
or modifies sample audio. It refuses unreviewed, legacy-v1, unknown or modified
choices. The source v3 and source MIDI remain unchanged.

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
isolated notes exist, full-performance and explainable/learned best-GM previews
where requested and available, plus `instrument_recipe.json`. Append
`--embedding-model "$OPENL3"` to carry the optional OpenL3 evidence and preview.
Apple factory content is never
copied: its result is a local patch shortlist. If safe sampling is impossible,
the bundle is explicitly `partial` but still retains the editable MIDI, source
reference and match evidence.

If an SF2 is successfully built but fails the usability gate, the bundle build
can still be `complete` while `source_instrument_status` is `texture-only`.
Its recipe then makes a complete GarageBand/GM patch primary and labels the
sampler as an optional layer. Playability is evaluated before timbre similarity:
a close-sounding bank that drops notes is not a usable main instrument.

Record a real GarageBand listening decision only after trying the patch in the
arrangement, then build an explicit local profile:

```bash
.venv/bin/sunofriend instrument-feedback \
  work/instrument-bundles/song-keys \
  --patch "Small Time Piano" \
  --decision preferred \
  --context full-mix \
  --compared-with sunofriend-instrument \
  --notes "Consistent tone and every note audible" \
  --out work/instrument-feedback/song-keys-small-time-piano.json

.venv/bin/sunofriend instrument-profile \
  work/instrument-feedback/song-keys-small-time-piano.json \
  --out work/instrument-feedback/my-patch-profile.json

.venv/bin/sunofriend instrument-bundle STEM.wav PART.mid \
  --kind keys \
  --preference-profile work/instrument-feedback/my-patch-profile.json \
  --out-dir work/instrument-bundles/song-keys-profiled
```

Feedback pins the source Bundle report, recipe and performance-MIDI hashes and
changes none of them. Profiles are deterministic, use only explicitly supplied
reviewed files and have no hidden store. A full-mix preferred choice has weight
1, an acceptable choice 0.5, solo listening half the corresponding full-mix
weight, and rejection negative weight. The profiled bundle displays the
history-first patch separately; factory, GM and OpenL3 orders remain unchanged,
the patch is not selected automatically, and the usability gate still wins.

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
