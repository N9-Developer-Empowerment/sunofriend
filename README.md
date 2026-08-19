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

Finished-mix separation currently has four distinct lanes:

| Lane | Roles | Availability |
| --- | --- | --- |
| Public default | broad vocals, complementary instrumental | `broad-vocals-v1` |
| Public explicit opt-in | vocals, drums, bass, grouped other | SCNet `core-four-stems-v1` |
| Private research | vocals, drums, bass, synth, guitar, residual other | unregistered specialist evidence only |
| Private recovery | the same six roles plus source and reconstruction review | listening complete; `private_review_package_recovered_model_free_resource_gate_incomplete`; not objective qualification |

The private synth and guitar models are not public profiles. Exact
reconstruction demonstrates PCM accounting, not correct musical assignment.

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

For deeper separation, Sunofriend now has an opt-in Studio challenger for
refining one exact SCNet grouped-`other` stem into either one guitar target or
one keys target plus the transparent residual. The Apple-native
`htdemucs_6s` MLX profile is installed separately; the keys lane is honestly
labelled as a piano proxy. Its fraction-normalized local loader, synthetic
canary and both full-song target mappings passed the objective offline gates.
The completed fixed five-song review found no demonstrated useful guitar
extraction and no successful piano extraction. The technically valid profile
remains reproducible in Studio, but it is not promoted, selected or fed to
MIDI. Plan a run with:

```bash
.venv/bin/sunofriend-separate refine-other \
  "/absolute/path/to/core-four-separation" \
  --target guitar \
  --out "/absolute/path/to/fresh-guitar-candidate"
```

Add `--execute --confirm-rights` only after reviewing the plan. The command
never activates the target or starts MIDI automatically. The deterministic
PCM24 proof, setup plan and bounded qualification evidence are documented in
[Refining grouped other in Studio](docs/OTHER_STEM_REFINEMENT.md).

The completed bounded candidate broadened the target from piano to the modern
`keyboard_synth` family: electric piano, organ, synth pad and synth lead.
Banquet was audited as a query-conditioned local research challenger alongside
guitar, with one configuration and no post-feedback query hunt. Its historical
no-effects planning commands were:

```bash
.venv/bin/python \
  scripts/plan-separation-other-refinement-query-runtime.py

.venv/bin/python \
  scripts/plan-separation-other-refinement-query-forward.py

.venv/bin/python \
  scripts/plan-separation-other-refinement-query-synthetic-report.py

.venv/bin/python \
  scripts/plan-separation-other-refinement-query-synthetic.py

.venv/bin/python \
  scripts/plan-separation-other-refinement-query-reference.py
```

It downloads, loads and executes nothing. The approved private checkpoint
evidence established SHA-256
`657295888781e62ef50593002720d2edb3858b9e5bbfabf0c54f715a0da4b9e2`
and a network-denied static structure report. The source audit also
found the required 341,546,630-byte OpenMIC PaSST checkpoint and rejected the
upstream automatic download and unrestricted loaders. Its separately approved
evidence-only download established SHA-256
`dc229428753176e8be0373d25887116fc15b490af86f671cecf9ed76a0f287da`
without loading it. A separately approved evidence-only dependency step
then resolved 28 exact CPython 3.12/macOS-arm64 wheels (99,354,620 bytes),
recorded every SHA-256 and licence metadata under network-denied non-importing
inspection, and committed the 2,800-byte lock with SHA-256
`28249f5d6ab80d4b72a5f256ac435f3a2d150b1baa30d751754af44049c33b92`.
A later separately approved gate installed those exact 28 packages from the
local cache into a fresh CPython 3.12.10/macOS-arm64 environment using
`--no-index --require-hashes`. Eight relevant package modules imported under
network denial with zero checkpoint opens, `torch.load` calls, network
attempts or audio opens. A further explicitly approved gate then constructed
the real 64-band Banquet adapter and both download-disabled PaSST variants and
loaded the two exact local checkpoints with
`torch.load(weights_only=True, map_location="cpu")`. All 1,069 Banquet and 159
OpenMIC PaSST keys, shapes and dtypes matched before strict loading, with no
missing or unexpected keys, network attempt or audio open. The later approved
single synthetic inference attempt then passed every objective gate under
network denial: 2.85 seconds, 2,052,014,080-byte peak RSS, finite stereo
float32 output at 44.1 kHz and `7.450580596923828e-09` maximum in-memory
reconstruction error. It used only generated tensors and opened no audio.
The second command prints the immutable forward contract bound to nine exact
files from the pinned upstream revision and its setup-C configuration. The
third prints the pure result validator contract: an objective failure must be
retained and grants neither automatic retry nor activation. The fourth command
is the immutable plan that bound the now-consumed one-attempt authority. The
planning commands still construct no model, run no inference and read no
audio. The retained report SHA-256 is
`bd5fa57716267488cfd9a0d1d69bc1627da6244d283fdaec5a5592234d51cec8`.
The very quiet synthetic target peak (`4.118360084248707e-05`) is explicitly
not musical evidence. A later, separately approved rights-bound canary used
the fifth command's frozen song-disjoint guitar, keyboard and synth query bank
against three owner-authorised mixtures. Exactly nine CPU attempts completed
under network denial in 64.01 seconds at 3,259,236,352-byte peak RSS. All 36
private PCM24 artifacts matched their hashes, every target plus residual
reconstructed its reference with zero-LSB error, and the worker recorded zero
network, forbidden-audio or unapproved-checkpoint attempts. The report SHA-256
is `fd15e3ba9524a49ebd182f86fa5c50ea0f5b02e95cc776ee5943a09147206ea8`.
That is objective execution evidence, not musical validation. The completed
bound review rated eight of nine targets not useful and one quiet keyboard
target partly useful; several guitar/synth targets were heard as blank or had
query hints unrelated to the mixture. The challenger is therefore technically
valid but musically unsuccessful. It remains unregistered, unselected and
unavailable to MIDI; the approved nine-attempt authority is consumed and poor
feedback cannot trigger a query hunt. See
[Guitar and keyboard/synth query-challenger plan](docs/OTHER_REFINEMENT_QUERY_CHALLENGER_PLAN.md).
The incremental code-structure work is tracked in
[Separation maintainability plan](docs/SEPARATION_MAINTAINABILITY_PLAN.md).
Probability, delivery time and the alternative synth/guitar portfolio are
tracked separately in the
[Fine-stem separation delivery forecast](docs/FINE_STEM_SEPARATION_FORECAST.md).

The later bounded challenger prioritised **synth first**, then guitar and wind;
acoustic piano was only an optional control and no longer stood in for modern
keys. Its no-effects plan audited the public MVSep Mega 53 Stems release and an
exact Apple-native BS-RoFormer source revision. The contract allowed only a
native `synth` candidate plus a transparent residual, separated audible target
presence from model usefulness, and permitted one configuration with no
post-feedback tuning loop. The approved evidence-only gate locally verified the
1,368,919,887-byte checkpoint and 4,184-byte configuration against their exact
published SHA-256 values, then inspected the checkpoint under network denial
without loading it. A later evidence-only gate resolved and statically
inspected 29 exact CPython 3.12/macOS 14+ arm64 wheels (127,527,173 bytes)
without installing or importing them. The committed lock SHA-256 is
`284d198c43e9074a4d645f005d937dd4e93b99e22aa21d942caaa1822b13d10b`.
An explicit follow-up installed that exact closure into a fresh isolated
CPython 3.12.10 runtime and imported thirteen direct modules under OS network
denial. There were zero connect or DNS calls, checkpoint/audio opens or
`torch.load` calls; `requests` made one contained `::1` capability-bind probe.
The exact 144,791-byte source archive was then materialised and all 64 files
were verified against the sealed source inventory. The separately approved
construction gate loaded the checkpoint exactly once with
`weights_only=True`, matched 13,571 converted MLX parameter keys, shapes and
dtypes, and retained the 53-stem model with zero network, audio or forward
calls. That check also exposed and transparently adapted an upstream mismatch:
the checkpoint requires transformer expansion 4, mask-head expansion 2 and
float16 parameters, while the published adapter conflates the two expansion
settings. The verified source was not mutated. Checkpoint use remains
provisional local noncommercial evaluation and the profile is not public; one
generated-tensor objective forward has now passed its separately approved gate.
The frozen no-effects
contract resolves the published 882,000-sample/441,000-step mismatch to an
881,664-sample chunk and 440,832-sample step, keeping both on the 512-sample
STFT clock without padding, cropping or source mutation. It authorizes nothing
by itself and permitted no automatic retry. The one call completed in 18.19
seconds at 15.42 GB peak MLX allocation with exact finite 53-role output and
zero network/audio attempts. The later four-song Mega-53 synth canary completed
in 37.44 seconds at 15.42 GB peak MLX allocation; the four-song
BS-RoFormer-SW guitar canary completed in 52.79 seconds at 8.51 GB. Both ran
under network denial, produced finite PCM24 target/residual artifacts and
reconstructed within zero LSB. The bound human reviews found synth partly
useful in 4/4 confirmed-present cases and guitar useful or partly useful in
4/4, with no catastrophic defects, bleed, artefacts or timing problems. Both
therefore passed the frozen 60% private-Studio gate. The later fixed
integration completed over the same eight reviewed windows: three sequential
model loads made 16 bounded inference attempts and published 64 finite PCM24
artifacts with zero-LSB reconstruction and no network access. In the combined
six-role review, synth was `useful` in 2/4 confirmed-present cases and
`partly_useful` in 2/4; guitar was `useful` in 4/4. All eight outputs had no
catastrophic defect. The exact no-effects outcome is
`private_six_role_integration_qualified`. This is positive private Studio
evidence, not a public six-stem product claim: three synth cases retained some
content outside the synth estimate, the first downstream-MIDI review is
methodology-limited, and model terms/resources still constrain release tier.

A no-effects integration plan bound the exact reports and reviews, reused the
eight persisted primary estimates, and fixed a grouped-other-constrained
three-way projection so synth, guitar and residual other could not be
double-counted. The completed plan SHA-256 is
`9507d1ef182a0060270033a770a823b758ba024e75cc42e768117e66893f1dec`;
the objective report SHA-256 is
`af0533233c4469c3914fbe2cf4eae1195de1ee545847c122a8a9f023f350d513`.
Record the completed review as a pure outcome without loading a model or
reading audio:

```bash
python3 scripts/record-fine-stem-six-role-integration-outcome.py \
  SIX-ROLE-INTEGRATION-ROOT \
  --out FRESH/fine-stem-six-role-integration-outcome-v1
```

The completed review document SHA-256 is
`407e4bf0ab686ceee2bcaa77473eca0a76b307b13b217e070cf5ae8a8cdb31ce`;
the pure outcome document SHA-256 is
`85b63909743da20a0b68e9d2fc130d0120f99e88036653586f7507766cf5d6f9`.

The downstream-MIDI no-effects plan is complete. It binds all eight exact
confirmed-present synth/guitar artifacts and compares each target candidate
with a sample-exact grouped-other control under identical BPM, key, tuning and
transcription settings. It opens no audio, runs no model or transcriber, writes
no MIDI and selects nothing. Reproduce that plan with:

```bash
.venv/bin/python scripts/plan-fine-stem-downstream-midi.py \
  SIX-ROLE-INTEGRATION-ROOT \
  FRESH/fine-stem-six-role-integration-outcome-v1/INTEGRATION-OUTCOME.json \
  --out FRESH/fine-stem-downstream-midi-plan-v1
```

The downstream-MIDI plan SHA-256 is
`7afab38b0bd446e2de75b4c408b1e275e533298765f25d89280c055fbb63e1e4`.
Its separately approved private execution is complete. Under OS network denial,
it verified all 24 input identities, wrote eight sample-exact grouped-other
controls, made exactly 16 same-settings transcription attempts and published
16 private MIDI files plus 16 loudness-matched neutral previews. It made zero
separator, checkpoint, network, selection or activation attempts. The report
SHA-256 is
`5f3ebf50c0097ca5a0169b63ed1eb4f2efc010d54b525321e5bfd3f621668b09`.
The eight-case A/B review is complete with review SHA-256
`dc766790f97341521363f1705f90ab3dfa1456b1925b0e97e5e13d35e94c2103`.
Guitar candidate MIDI was preferred to its grouped-other control in 3/4 cases;
synth was equivalent once and `cannot_tell` in 3/4. Recognisable-note and
timing ratings were synth `useful` once and `partly_useful` three times, and
guitar `partly_useful` three times and `not_useful` once. The completed review
omitted the source reference, so these are methodology-limited findings rather
than promotion evidence. The repaired local review now shows the exact source
window beside A/B without changing the saved answers or requiring another
checkbox. Poor results cannot disable the qualified six-role evidence.

The completed review is now reduced into a pure, hashed outcome. It records
guitar as directional private evidence, records no isolated-stem synth
advantage, and grants no model, audio, MIDI, source-selection or activation
authority:

```bash
.venv/bin/python scripts/record-fine-stem-downstream-midi-outcome.py \
  PRIVATE-MIDI-CANARY-ROOT \
  --out FRESH/fine-stem-downstream-midi-outcome-v1
```

The outcome SHA-256 is
`d69863fb8ea59087ad6cfcd5669fee88db6afef6a7bd20809d42d88415c29a0c`.
A historical no-audio request then bound the exact four source-present synth
cases and froze a three-arm attribution test: current synth estimate, provider
synth/keyboard estimate and grouped-other control, all through the same
transcriber with the source visible during review. It neither opens provider
audio nor authorises the later 12-attempt run:

```bash
.venv/bin/python scripts/plan-fine-stem-synth-bottleneck.py \
  PRIVATE-MIDI-CANARY-ROOT \
  SIX-ROLE-INTEGRATION-ROOT \
  FRESH/fine-stem-downstream-midi-outcome-v1/MIDI-OUTCOME.json \
  --out FRESH/fine-stem-synth-bottleneck-request-v1
```

The request SHA-256 is
`d03f5ff549c5d778a6c07451c9f953be3fe29bc107e743ce5ae691e342e4419a`.
The missing `Uni Ava` pack was found locally and the deterministic first-pack
policy is now frozen across all four songs. A separate qualification step bound
36 exact private input identities, wrote four source/provider PCM24 pairs and
verified all four provider pack sums against the existing source windows. The
sample correlations were 0.913–0.949, envelope correlations 0.946–0.980 and
every best envelope lag was zero. The qualification report SHA-256 is
`64b564798a6f338c66039e40981a5d562160c83451f2bc6d2a5411c56eba0eea`.
It loaded no model, ran no transcription and does not treat the provider
`Synth` label as truth.

```bash
.venv/bin/python scripts/qualify-fine-stem-synth-provider-estimates.py \
  FRESH/fine-stem-synth-bottleneck-request-v1 \
  SIX-ROLE-INTEGRATION-ROOT \
  PRIVATE-PROVIDER-INPUTS.json \
  --out FRESH/fine-stem-synth-provider-qualification-v1

.venv/bin/python scripts/serve-fine-stem-synth-provider-review.py \
  FRESH/fine-stem-synth-provider-qualification-v1
```

The source-visible presence review recorded playback automatically, autosaved
on the local server and had no listened checkbox. It completed all four cases
before the separately hash-bound 12-attempt MIDI plan ran; poor musical
feedback still cannot disable core four.

That source-visible three-arm MIDI comparison is now complete. Grouped other
was preferred in all four synth cases, so Sunofriend retains grouped other as
the MIDI control without discarding the separately qualified synth audio. The
reviewed six-role excerpts can now be copied into an owner-only Studio package:

```bash
.venv/bin/python scripts/package-fine-stem-private-studio.py \
  SIX-ROLE-INTEGRATION-ROOT \
  FRESH/fine-stem-six-role-integration-outcome-v1/INTEGRATION-OUTCOME.json \
  PRIVATE-MIDI-CANARY-ROOT \
  FRESH/fine-stem-downstream-midi-outcome-v1/MIDI-OUTCOME.json \
  FRESH/fine-stem-synth-provider-midi-outcome-v1/PROVIDER-SYNTH-MIDI-OUTCOME.json \
  --out FRESH/fine-stem-private-studio-package-v1
```

The exact local build copied and re-hashed 72 PCM24 files across eight
reviewed 15-second cases and wrote 16 explicit Studio catalogs. Each case has
one six-role audio catalog and a separate grouped-other MIDI-control catalog;
loading both as one source set would double-count synth and guitar. The package
contains no MIDI, makes no source choice, loads no model and activates nothing.
Its manifest SHA-256 is
`4b5bce6daa00607a93257d33db3e1055ab651287458c21ccd637b304438053bd`.
This is a private evaluation slice, not a full-song or public six-stem claim.

The exact three-song full-song plan at SHA-256
`869ac229d5c95c9c3d5eb2c9eb38da368056f6fe3c644de9830cc593313efb7d`
was approved and consumed once. It bound `I am a Alien mashup` for confirmed
synth and guitar, `Be Alone` for synth and `In the way` for guitar. The guarded
run ended in retained objective failure with no automatic retry. Its
replacement failure retained complete SCNet, Mega-53 and guitar arrays but no
guitar result receipt, guard counters or peak-memory measurement; both failed
packages remain immutable.

A separately exact-hash-approved recovery reverified the retained PCM24, NPY
and JSON identities under network denial and wrote the already-fixed 24 private
PCM24 review artifacts. It loaded no checkpoint, constructed or loaded no
model, ran no inference or canonicalisation and started no model worker. Its
status is
`private_review_package_recovered_model_free_resource_gate_incomplete`.
This provides private full-song listening material, not full objective or
resource qualification: the guitar and aggregate resource gates are incomplete
and supported-ceiling compliance is unknown. The reproducible urllib3 IPv6
loopback `socket.bind` import path is consistent with the failed effects guard,
but the missing historical worker receipt means it is not proven as that
failure's cause. The future worker import order is repaired without weakening
bind denial.

The bound review is complete with status
`human_listening_complete_no_selection`. Playback was recorded for all 24
full-song items and all four confirmed-present windows. All three cases were
overall `useful` and reported no catastrophic defect. Vocals, drums, bass and
residual other were useful in 3/3 cases; synth and guitar were each useful in
2/2 confirmed-present cases. No scored role reported bleed, artefacts or
timing/join problems. Synth and guitar each reported `some` missing content in
2/2 cases; core roles reported none. There were no `cannot_tell` or
`not_tested` ratings. This is positive private musical evidence, not
objective/resource qualification or a public six-role product.

The immutable private outcome is now recorded with status
`private_full_song_six_role_listening_evidence_recorded_resource_gate_incomplete`
and canonical document SHA-256
`fa5d1d24627dce4cb1e27175055f1e3d5a3a70683b98e2376d92ee125bc2163c`.
It preserves the positive listening aggregate and every incomplete
objective/resource/product boundary above.

The original planning command and its approval are historical, consumed and
non-reusable. Do not recreate or rerun that plan or solicit its old approval.
Any future model run needs a new bounded plan and explicit authority. Validate
the exact recovered report without loading a model:

```bash
.venv/bin/python scripts/recover-fine-stem-full-song-six-role.py \
  --plan PRIVATE-PLAN-ROOT/FULL-SONG-SIX-ROLE-PLAN.json \
  --validate-report \
  PRIVATE-RECOVERY-ROOT/TECHNICAL/FULL-SONG-SIX-ROLE-RECOVERY-REPORT.json
```

The recovered package grants no public activation, source choice, MIDI,
hosting, redistribution or upload. Poor listening feedback remains recordable
without disabling core four. See [Private full-song six-role canary
plan](docs/FINE_STEM_FULL_SONG_PLAN.md).

Inspect the already-completed recovered full-song review locally with:

```bash
.venv/bin/python scripts/serve-fine-stem-full-song-six-role-review.py \
  PRIVATE-RECOVERY-ROOT \
  --plan PRIVATE-PLAN-ROOT/FULL-SONG-SIX-ROLE-PLAN.json
```

See [Synth-first fine-stem challenger](docs/OTHER_REFINEMENT_NEXT_CHALLENGER_PLAN.md).

For the separate grouped-other refinement route, bind an exported listening
JSON to its exact result without selecting a source or starting MIDI:

```bash
.venv/bin/sunofriend-separate review-other \
  "/absolute/path/to/refinement-result" \
  "/absolute/path/to/sunofriend-other-refinement-listening.json" \
  --out "/absolute/path/to/fresh-private-feedback.json"
```

For development across several songs, the fixed private corpus runner freezes
five authorised songs, separate guitar and piano-proxy windows, one model
configuration and exactly ten reviews. It places the Sunofriend estimates
beside local Moises/Suno comparison excerpts without treating provider stems
as ground truth or using feedback to tune between cases:

```bash
.venv/bin/python scripts/create-other-refinement-corpus-review.py --plan
```

The prepared package is served only on localhost so every audio control works
reliably. Its ten-review bundle can be recorded as hash-bound evidence without
selecting a source, promoting a model or starting MIDI. See
[Refining grouped other in Studio](docs/OTHER_STEM_REFINEMENT.md).

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
Both import routes now retain automatic, unreviewed key/BPM evidence. Inspect
one file without importing it with `sunofriend musical-metadata SOURCE`; when
preparing separated stems, pass the original finished mix with
`source-import-folder --metadata-source ORIGINAL_MIX`. Explicit and filename
metadata remain authoritative, and tuning observations are never promoted
automatically.
See [source preparation](docs/GETTING_STARTED.md#prepare-a-folder-of-existing-audio-parts).

## What you receive

The automatic result contains:

```text
AUTOMATIC-SONG/
├── START-HERE.txt
├── MIDI/individual parts and combined-gm-interpretation.mid
├── SOUNDS/named starter-sound MIDI, short previews and GarageBand guide
├── AUDIO/balanced-midi-song-interpretation.wav
├── TECHNICAL/automatic-musical-metadata.json and mix evidence
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
| Try or review experimental evidence-first vocal comping | [Ranked-evidence pilot](docs/VOCAL_COMPING_PILOT.md), [design](docs/VOCAL_COMPING_DESIGN.md) and [implementation plan](docs/VOCAL_COMPING_IMPLEMENTATION_PLAN.md) |
| Match or build instruments | [Instruments](docs/INSTRUMENTS.md) |
| Review the iterative reference-to-song goal | [Reference-conditioned generation specification](docs/REFERENCE_CONDITIONED_SONG_GENERATION_SPEC.md) |
| Follow the private-song model comparison | [Empirical song-generation evaluation plan](docs/REFERENCE_CONDITIONED_SONG_GENERATION_EVALUATION_PLAN.md) and [provider policy](docs/SONG_GENERATION_PROVIDERS.md) |
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
