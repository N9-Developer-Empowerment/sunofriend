# Experimental local stem separation

Sunofriend can be tried on a finished song before separate stems already
exist. The default public **experimental alpha** remains broad vocals plus
complementary instrumental. The immutable SCNet-large profile is now available
as an explicit **vocals/drums/bass/grouped-other public opt-in preview**. The
earlier MLX baseline and first PyTorch fallback remain fail-closed after their
bounded objective remediations failed.

The first alpha produces:

- `vocals.wav`, an estimate of the broad vocal content;
- `instrumental.wav`, the complementary source-minus-vocals result;
- a level-managed source reference;
- a reconstruction check made by adding the two persisted stems; and
- a local listening page with a private JSON review export.

The default does **not** produce separate drums, bass, keys or guitars. A
reconstruction that sounds right proves that outputs account for the source.
It does not prove that every sound is in the correct stem.

After an explicit SCNet core-four run, the separately installed Studio
challenger can refine that exact grouped `other` into one experimental guitar
target or one disclosed piano-as-keys proxy plus an exact residual. Use
`sunofriend-separate refine-other CORE_FOUR_ROOT --target guitar --out FRESH`
to plan it; add `--execute --confirm-rights` only after review. The completed
five-song, ten-report review demonstrated neither useful guitar extraction nor
successful piano extraction. The profile remains reproducible but is not
promoted, selected or fed to MIDI. See
[Refining grouped other in Studio](OTHER_STEM_REFINEMENT.md).
Use `sunofriend-separate review-other RESULT_ROOT REVIEW_JSON --out FRESH.json`
to bind an explicit guitar/keys listening export without selecting or
activating either frontier.

A completed bounded evaluation tracked a query-conditioned candidate for
guitar and broad `keyboard_synth`—electric piano, organ, synth pad and synth
lead. Its objective runtime, load, synthetic and nine-case private audio gates
passed, but the bound human review rated eight targets not useful and one
partly useful. It remains negative evidence, not a working product claim. See
[Guitar and keyboard/synth query-challenger plan](OTHER_REFINEMENT_QUERY_CHALLENGER_PLAN.md).

The synth-first Mega-53 and specialised BS-RoFormer-SW guitar canaries and their
fixed six-role integration are now complete. Source presence was confirmed
before inference in four song-disjoint cases per target. The combined
network-denied worker constrained both specialists inside SCNet grouped other
and published mutually exclusive vocals, drums, bass, synth, guitar and
residual other. All eight persisted sets were finite and reconstructed within
zero PCM24 LSB.

The combined review rated synth `useful` in 2/4 confirmed-present cases and
`partly_useful` in 2/4; guitar was `useful` in 4/4. All eight outputs had no
catastrophic defect. The pure outcome is
`private_six_role_integration_qualified`. Neither model is registered,
publicly executable or selected for MIDI. Downstream MIDI musical usefulness
remains unreviewed, three synth cases retained some missing content, and
absent-role ratings were excluded from qualification. The no-effects
downstream-MIDI plan is bound
to the eight exact role-present artifacts with SHA-256
`7afab38b0bd446e2de75b4c408b1e275e533298765f25d89280c055fbb63e1e4`.
The later separately authorised execution verified all 24 inputs and completed
exactly 16 candidate/control transcriptions under network denial without
rerunning separation or selecting a source. It published 16 private MIDI files
and 16 loudness-matched neutral previews. Report SHA-256:
`5f3ebf50c0097ca5a0169b63ed1eb4f2efc010d54b525321e5bfd3f621668b09`.
The blind musical review is pending and poor results cannot disable the private
six-role evidence.
See
[Synth-first fine-stem challenger](OTHER_REFINEMENT_NEXT_CHALLENGER_PLAN.md).

Inspect the executable default and immutable profiles at any time:

```bash
.venv/bin/sunofriend-separate profiles
```

The reviewed engineering sequence and promotion gates are in
[Full stem separation: reviewed path forward](FULL_STEM_SEPARATION_PLAN.md).
The selected backend is the installed SCNet-large release profile. Its exact
checkpoint, source and 12-wheel runtime are hash-pinned. Weights-only strict
compatibility passed after one transparent official-wrapper remediation. A
network-denied synthetic canary, three authorised song-disjoint canaries and
three repeat resource runs passed the objective gates, and the project owner
reported no catastrophic defect after listening to every full-song output.
See [the SCNet audit](CORE_FOUR_SCNET_AUDIT.md) and
[approval ledger](CORE_FOUR_MODEL_APPROVALS.md).

## Blocked core-four MLX baseline

`demucs-mlx-htdemucs-v1` is pinned to `demucs-mlx==1.4.4`, source revision
`b37e6ba3c5985af531f61c43564cf13c6ed349fd`, MLX Community model revision
`d4519e24ddc2dd4a11d56a193092433d852c3961`, and exact wheel, weights and
config SHA-256 identities. It is Apple-silicon-native and PyTorch-free at
inference.

Inspect its retained no-write setup record:

```bash
scripts/setup-separation-core-four-macos.sh --plan
```

New installs and activation retries for this failed profile are disabled because its
objective remediation budget is exhausted. The plan command explains the
failure and downloads nothing. The first separately approved PyTorch fallback
also failed before publication and now refuses retries. The qualified SCNet
profile now reports `public_opt_in`; select the core-four scope explicitly:

Review the exact fallback without changing the Mac:

```bash
scripts/setup-separation-core-four-fallback-macos.sh --plan
```

It uses 20 hash-pinned Apple-arm64/Python 3.13 wheels, including PyTorch and
`setuptools==83.0.0`, and discloses that the original checkpoint has no separate
model-specific licence file. The revised approved install passed doctor, but
the synthetic worker rejected the model's native `Fraction(39, 5)` segment
before inference or publication. Its remediation budget is exhausted, so the
plan now refuses new installs and activation retries.

For the selected SCNet profile, inspect the separate setup plan:

```bash
scripts/setup-separation-core-four-scnet-macos.sh --plan
```

On a fresh Apple-silicon setup, install only after reviewing the exact source,
checkpoint, hashes, terms evidence, download size and local path:

```bash
scripts/setup-separation-core-four-scnet-macos.sh \
  --install --accept-model-terms --accept-checkpoint-use
```

The installer refuses to overwrite an existing profile. Verify it without
loading the checkpoint or processing audio:

```bash
.venv/bin/sunofriend-separate doctor --scope core-four-stems-v1
```

```bash
.venv/bin/sunofriend-separate separate SONG \
  --scope core-four-stems-v1 \
  --out FRESH \
  --rights-category owned
```

The shared four-stem output contract preserves vocals, drums and bass, and transparently adds
the model reconstruction residual to grouped other. The review reports the
native-other correction RMS/peak so exact reconstruction cannot be mistaken
for accurate separation.

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

The page can export a scope/profile/report-bound private local review JSON and
copy a safe text-only summary. It asks for per-role usefulness, bleed, missing
content, artefacts, timing, joins and downstream MIDI outcome; `cannot_tell`
and `not_tested` are valid. It also links to the existing
[compatibility and developer report](https://github.com/N9-Developer-Empowerment/sunofriend/issues/new?template=daw-ai-compatibility.yml).
Share text observations only. Do not attach private audio, stems, vocals,
review JSON, filenames or private metadata to a public issue.

If the outputs are useful, copy `vocals.wav` and `instrumental.wav` into a new
folder. That folder can then enter the normal Sunofriend `create`, TUI or Studio
workflow. The alpha deliberately does not activate those stems or choose MIDI
automatically, because listening remains the musical decision boundary.

## What feedback changes

Feedback can reveal setup failures, platform gaps, bleed, missing content,
join problems and whether stems are useful for MIDI. Preview admission uses
objective licensing, privacy, integrity, runtime and output gates—not a minimum
usefulness score. Review occurs after 30 days or 10 valid reports, whichever
comes first. Poor feedback keeps the last functioning baseline accessible,
publishes a limitation and motivates one bounded challenger. It never silently
selects a winner or becomes a universal musical default.

The immediate post-release plan is:

1. keep the working SCNet profile publicly accessible while collecting
   scope/profile-bound usefulness feedback;
2. verify the existing resource supervision on a real 16 GiB Apple-silicon
   machine without making that evidence a new admission veto;
3. review feedback after 30 days or 10 valid reports, whichever comes first,
   and publish repeated musical limitations plainly;
4. run at most one bounded Studio challenger when repeated poor feedback
   justifies it; do not retry the exhausted MLX or `demucs-infer` profiles; and
5. connect explicitly reviewed stems to the existing MIDI plus interpretation
   WAV workflow with fewer manual steps, only after a separate user decision.
