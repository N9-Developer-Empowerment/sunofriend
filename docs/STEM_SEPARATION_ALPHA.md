# Experimental local stem separation

Sunofriend can now be tried on a finished song before separate stems already
exist. This is a public **experimental alpha**, so the useful thing is not a
claim of perfect separation. It is a reproducible local result that a musician
can hear, keep or reject, then describe through the existing feedback route.

The first alpha produces:

- `vocals.wav`, an estimate of the broad vocal content;
- `instrumental.wav`, the complementary source-minus-vocals result;
- a level-managed source reference;
- a reconstruction check made by adding the two persisted stems; and
- a local listening page with a private JSON review export.

It does **not** yet produce separate drums, bass, keys or guitars. Those are
planned extensions. A reconstruction that sounds right proves that the two
outputs still account for the source. It does not prove that every sound is in
the correct stem.

## Requirements and boundaries

This initial route is verified on an Apple-silicon Mac. Windows, Linux and
Intel Macs are not yet supported. You need:

- a Sunofriend checkout and its normal `.venv`;
- FFmpeg and FFprobe;
- Python 3.12 or 3.13 for the separate MLX runtime;
- roughly 500 MB for the model plus runtime and working space; and
- audio you own, have licensed, or are otherwise permitted to process.

Inference stays on the Mac. The setup command downloads the pinned MIT model,
audited source files and hash-pinned runtime wheels. The separation command
runs with offline model settings and uploads nothing. The model is
[`mlx-community/mel-roformer-kim-vocal-2-mlx`](https://huggingface.co/mlx-community/mel-roformer-kim-vocal-2-mlx)
at immutable revision `64cbfcb004e39430e5f584552c05949440ec39ce`.

## Install once

First inspect the plan; this writes nothing:

```bash
scripts/setup-separation-alpha-macos.sh --plan
```

After reading the linked MIT terms, install explicitly:

```bash
scripts/setup-separation-alpha-macos.sh \
  --install \
  --accept-model-terms
```

Verify the local setup without loading the model or processing audio:

```bash
.venv/bin/sunofriend-separate doctor
```

If Python 3.12 or 3.13 is missing, ask your coding agent to install it, or use
Homebrew, then rerun the setup command. The main Sunofriend environment remains
separate.

## Separate one song

Always start with a read-only plan. This example is for music you own:

```bash
.venv/bin/sunofriend-separate separate \
  "/absolute/path/to/song.wav" \
  --out "/absolute/path/to/fresh-separation-output" \
  --rights-category owned
```

The plan checks the source, decoder, local model and available disk space. It
does not create the output folder. To run it:

```bash
.venv/bin/sunofriend-separate separate \
  "/absolute/path/to/song.wav" \
  --out "/absolute/path/to/fresh-separation-output" \
  --rights-category owned \
  --execute \
  --confirm-rights \
  --open-review
```

Use `licensed`, `authorised_private_use` or `statutory_exception` only when
that accurately describes your authority. MP3, FLAC, M4A, AIFF, OGG/Opus and
normal WAV inputs are accepted through Sunofriend's bounded FFmpeg import.

## Listen, then decide

Open `REVIEW/separation_review.html` in a normal browser and compare all four
tracks. Listen for:

- missing vocal phrases or vocal bleed;
- accompaniment leaking into the vocal stem;
- holes or watery/metallic sound in the instrumental;
- level or tone changes around chunk joins; and
- whether each output is musically useful, even when it is not perfect.

The page can export a private local review JSON. It also links to the existing
[compatibility and developer report](https://github.com/N9-Developer-Empowerment/sunofriend/issues/new?template=daw-ai-compatibility.yml).
Share text observations only. Do not attach private audio, stems or vocals to a
public issue.

If the outputs are useful, copy `vocals.wav` and `instrumental.wav` into a new
folder. That folder can then enter the normal Sunofriend `create`, TUI or Studio
workflow. The alpha deliberately does not activate those stems or choose MIDI
automatically, because listening remains the musical decision boundary.

## What feedback changes

Feedback can reveal setup failures, platform gaps, bleed, missing content,
join problems and whether the broad stems are useful for MIDI. It will guide
bounded tests and later releases. One review never silently changes a model,
selects a winner or becomes a universal musical default.

The immediate expansion plan is:

1. make setup clearer across more Apple-silicon Macs;
2. improve long-song joins and expose useful quality diagnostics;
3. compare additional permissively usable models;
4. add narrower instrument and drum-family separation; and
5. connect explicitly reviewed stems to the existing MIDI plus interpretation
   WAV workflow with fewer manual steps.
