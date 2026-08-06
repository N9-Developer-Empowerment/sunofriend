# Stem-separation developer preview

Sunofriend now publishes its first opt-in local finished-mix separator as an
**experimental alpha**. Musicians can use the current implementation while the
project improves its setup, long-song handling, model comparisons and role
coverage through open participation.

The public route is intentionally narrow and honest:

- one authorised finished mix in a supported audio format;
- Apple-silicon macOS for the first verified platform;
- one exact MIT Kim Vocal 2 MLX checkpoint and hash-pinned runtime;
- broad `vocals.wav` plus complementary `instrumental.wav`;
- a source reference and additive reconstruction diagnostic;
- a local review page and private JSON review export; and
- no upload, telemetry, silent MIDI conversion or automatic model promotion.

This is not ground-truth recovery of the lost studio multitracks. It does not
yet split drums, bass, keys or guitars separately. Human listening remains the
authority for whether a result is musically useful.

## Overall development goal

The long-term goal is one understandable local journey:

1. supply music you own or may process;
2. obtain useful estimated stems when original multitracks are unavailable;
3. compare analytical and optional local-AI MIDI interpretations;
4. hear a balanced MIDI-derived song interpretation;
5. edit MIDI and suggested instruments in GarageBand or another DAW; and
6. use explicit observations to improve later bounded releases.

Sunofriend should make useful musical evidence and interpretations, not hide
uncertainty behind a single score or model.

## Public alpha architecture

The public slice is separate from the older private evidence harness:

- [`separation_alpha.py`](../src/sunofriend/separation_alpha.py) owns the
  read-only doctor, plan, rights confirmation, atomic output and review page;
- [`separation_worker.py`](../src/sunofriend/separation_worker.py) loads the
  exact audited model offline once and processes bounded contiguous chunks;
- [`setup-separation-alpha-macos.sh`](../scripts/setup-separation-alpha-macos.sh)
  explains and explicitly installs the pinned source, model and runtime; and
- [`STEM_SEPARATION_ALPHA.md`](STEM_SEPARATION_ALPHA.md) is the musician-facing
  setup, use, listening and feedback guide.

The model worker reuses the already-audited loader and fixed model
configuration. The public coordinator keeps installation, planning, execution,
review and downstream MIDI conversion as separate explicit actions.

## How it was developed

Each increment followed a repeatable evidence loop:

1. state one narrow musical or engineering question;
2. bind authorised inputs and exact runtime identities;
3. run one bounded experiment without activating the result;
4. check geometry, finite audio, timing, hashes and additive accounting;
5. bind a human listening review to that exact result; and
6. preserve useful, poor and inconclusive observations before changing policy.

Private evaluation covered three source-distinct full-song chains plus targeted
join reviews. The listener judged the overall separation and audio quality good
to good enough, while also noting that join artefacts could be subjective and
hard to hear in context. That was sufficient to support an experimental public
alpha, not a claim of universal accuracy.

The new public smoke test exercises the complete route. All four output WAVs
retain identical stereo 44.1 kHz PCM24 duration; the test reconstruction stayed
within one PCM24 least-significant bit of its level-managed source reference;
and the self-hashed report verified. Musical accuracy still requires listening.

## Run the public route

Inspect setup without changing the Mac:

```bash
scripts/setup-separation-alpha-macos.sh --plan
```

After reading and accepting the linked MIT model terms:

```bash
scripts/setup-separation-alpha-macos.sh \
  --install --accept-model-terms
.venv/bin/sunofriend-separate doctor
```

Plan a song without creating its output:

```bash
.venv/bin/sunofriend-separate separate SONG \
  --out FRESH \
  --rights-category owned
```

Then run only after confirming the rights statement:

```bash
.venv/bin/sunofriend-separate separate SONG \
  --out FRESH \
  --rights-category owned \
  --execute --confirm-rights --open-review
```

The other affirmative categories are `licensed`, `authorised_private_use` and
`statutory_exception`. The output is always labelled `complete_unreviewed` and
`human_listening_required`.

## Reviewable code and tests

The focused public contract tests are:

```bash
.venv/bin/python -m pytest \
  tests/test_separation_alpha.py \
  tests/test_interface_contract.py -q
```

The longer private research harness remains available for developers who need
the evidence chain, independent chunk execution, boundary packages and
historical experiments. It is no longer the beginner entry point and its older
private-only product statements are historical.

## Feedback that can improve the alpha

The local review page asks whether the vocals and instrumental are useful,
whether all tracks were heard and what bleed, missing sound, artefacts or join
changes were audible. Exporting that JSON is local only.

Public text feedback belongs in the existing
[compatibility and developer report](https://github.com/N9-Developer-Empowerment/sunofriend/issues/new?template=daw-ai-compatibility.yml).
Useful reports include:

- Mac model and macOS version;
- source format and approximate duration;
- the first setup or command that was confusing or failed;
- whether vocals and instrumental were useful, partly useful or unusable;
- audible bleed, missing sound, metallic texture, level changes or joins; and
- whether those stems improved the later MIDI interpretation.

Do not attach private music, vocals, stems or review exports to a public issue.
Feedback can repair instructions, expose a platform gap or motivate a bounded
comparison. It never silently selects a model or musical default.

## Next engineering increments

1. improve installer recovery and progress on more Apple-silicon Macs;
2. expose clearer long-song progress and join diagnostics;
3. compare additional checkpoints with clear usable terms;
4. add narrower instrument and drum-family roles;
5. connect explicitly reviewed stems to MIDI plus WAV creation with fewer
   manual steps; and
6. broaden tests across songs, machines and listeners without uploading
   private audio.
