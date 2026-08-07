# Separation examples

This directory contains two deliberately separate local collections:

1. Sunofriend's first **owner-authorised real-song development corpus**: four
   Ezzye originals, one Moises stem pack and two distinct Suno stem packs per
   song; and
2. a **private-reference inventory**: five additional originals with one
   detailed Moises pack each. Their folder names include third-party artist
   names, so presence here is not an ownership, reuse or redistribution claim.

The audio and chord PDFs remain local and are ignored by Git. They are
development evidence, not repository assets. The tracked
[`corpus.json`](corpus.json) records the owner-authorised four-song inventory.
[`private-reference-corpus.json`](private-reference-corpus.json) records the
additional metadata without granting blanket processing authority. The private
runner can use only a track carrying the exact user-authorised private-local
record; exact hashes belong in fresh evaluation receipts.

## Permission and credit

Ezzye, the creator and copyright holder, supplied these four original tracks
and authorised their use as Sunofriend examples on 31 July 2026. The original
music may be downloaded, studied, transformed and reused with credit.

Use this credit unless the individual track page gives a more specific form:

> Music by Ezzye — <https://soundcloud.com/ezzye-1>

Prefer a link to the individual SoundCloud track when one is available. The
permission recorded here applies to the four named original tracks in this
corpus; it is not a claim about every historical upload on the profile.

The five private-reference folders have no ownership or reuse permission
record in their manifest. They must not be published, redistributed or used as
public demos merely because they are present. `Mauvais djo - Pilé` now has a
separate user-authorised private-local-evaluation record; the other four need
their own track-specific processing authority before an evaluation uses one.
None belongs to the public authorised-corpus runner.

Moises and Suno are independent providers. Their derived stem packs are kept
local for comparison until the applicable export-redistribution terms are
recorded. Sunofriend is not affiliated with either provider.

## Corpus layout

```text
stem_examples/
└── Song title-key-BPM-tuning/
    ├── ORIGINAL/one source WAV
    ├── MOISES/one detailed stem pack
    └── SUNO/two independently generated stem-pack folders
```

Do not normalize, trim, align or rename these source files. Differences in
clock, duration, level and provider naming are part of the evidence.

## Initial read-only inventory

| Track | Original | Moises | Suno A/B | Initial state |
| --- | --- | --- | --- | --- |
| Be Alone | 262.56 s, 48 kHz | 17 files | 8 + 8 files, 262.36 s | First 191–206 s private excerpt staged |
| I am a Alien mashup | 276.12 s, 48 kHz | 17 files | 9 + 9 files, 275.92 s | 219–234 s private excerpt staged and compared |
| In the way | 225.88 s, 44.1 kHz | 17 files, about 160.72 s | 8 + 8 files, 160.52 s | Investigate source/provider horizon before comparison |
| Tell Me That I Do It Bitch | 186.36 s, 48 kHz | 17 files | 7 + 7 files, 186.36 s | Ready for excerpt selection |

Every corresponding Suno A/B WAV differed after decoding to PCM. The two
packs are therefore retained as distinct separator outcomes. Moises metronome
files end slightly earlier than their musical stems and are timing evidence,
not source roles for MIDI conversion.

## Additional private-reference inventory

| Reference | Original and musical stems | Moises | Initial state |
| --- | --- | --- | --- |
| Mauvais djo - Pilé | 156.08 s | 17 files | Authorised; 33–48 s private excerpt staged and compared |
| Silva Bumpa - On 2nite | 158.85 s | 17 files | Geometry ready; authority required before evaluation |
| Slayyyter - DANCE... (Edit) | 236.04 s | 17 files | Geometry ready; authority required before evaluation |
| sombr - 12 to 12 | 242.90 s | 17 files | Geometry ready; authority required before evaluation |
| Toots & The Maytals - Monkey Man | 175.53 s; folder declares A=446 Hz | 17 files | Geometry ready; authority and tuning handling required |

All 90 private-reference audio files decode as stereo 44.1 kHz audio. Each
original is FLAC and each Moises export is PCM16 WAV. All five musical stem
packs now match their original duration; the metronomes are shorter and remain
timing evidence only. No Suno pack is present, so these are not direct
replacements for the original three-provider comparison design.

The redone `Mauvais djo - Pilé` pack has 16 musical stems with the original's
exact 6,882,992-frame horizon. Its float64 musical-stem sum has 0.997537
sample correlation with the original at recorded zero, a best 10 ms envelope
lag of 0.00 seconds, 0.998738 envelope correlation and only -0.059 dB level
difference. This clears the former geometry/clock blocker; it does not itself
make the provider estimates ground truth. On 31 July 2026 the user separately
authorised this track for private local evaluation only. That authority permits
the next bounded experiment but does not permit repository distribution or
public-demo use.

That bounded experiment now uses seconds 33–48, selected by a deterministic
four-group activity scan rather than by recognising a chorus. The Moises stem
sum and original remained aligned at recorded zero: sample correlation was
0.994250, best-envelope lag was 0 ms and envelope correlation was 0.997934.
Pinned four-source HTDemucs took 10.15 seconds of inference and about 2.12 GB
reported peak resident memory. Its bass, drums, other and vocals outputs each
ranked closest to the matching proposed Moises group, but broad `other` was
weakly separated from vocals: similarity 0.5973 with only a +0.0753 margin.

The identical inactive MIDI comparison found strong drum timing agreement
(onset F1 0.8723), moderate bass agreement (exact-pitch/onset F1 0.5455) and
weaker composite-`other` agreement (exact-pitch/onset F1 0.4068). Neither broad
vocal signal produced notes through the current dominant-contour path on this
window, despite audible/energy evidence in the vocal groups. This is useful
negative evidence for improving vocal transcription and narrowing `other`, not
an acceptance decision. All excerpts, stems, MIDI and auditions remain local,
private, ignored by Git and inactive.

The first `Be Alone` observation uses 191–206 seconds. All three provider
packs measured zero 10 ms envelope lag against the original. The Moises
non-metronome sum correlated 0.9985 with the original excerpt; the two Suno
sums correlated 0.9305 and 0.9306. This establishes a usable common clock for
that excerpt, not correct instrument assignment. In particular, the two Suno
files labelled `Keyboard` were effectively silent in this passage while their
`Synth` files were active. Role mapping must therefore use sound evidence as
well as provider names before downstream MIDI comparison.

The provisional four-role groups have now been tested against all four local
HTDemucs outputs. Every proposed bass, drums, other and vocals group ranked
first for its matching local role. This validates the partition as a useful
comparison hypothesis only; neither provider nor HTDemucs is treated as
ground truth, and no mapping has been automatically accepted.

The same production MIDI settings have also been applied to every four-role
group in the first excerpt. Drum onset agreement against the local HTDemucs
MIDI was high (0.890–0.939 F1), but broad `other` exact-pitch/onset agreement
was low (0.161–0.252 F1). This is useful negative evidence: provider names and
four-way audio similarity are not enough to make composite `other` behave as
one instrument. The result remains private, unselected and unsuitable for
automatic promotion until listening and a second-song repeat are complete.

The second-song repeat is now complete on `I am a Alien mashup`, original
seconds 219–234. The fixed window was selected by a decoded group-energy scan,
not a provider name or a presumed chorus: it maximised a weighted lower
quartile and median of normalised activity across all twelve combinations of
three packs and four roles. All twelve proposed roles again ranked first, but
`other` was only weakly separated from the next role in the audio comparison.

The identical downstream MIDI repeat confirms that this matters. Provider
drum onset agreement against local HTDemucs MIDI remained high
(0.819–0.874 F1), while broad `other` exact-pitch/onset agreement remained low
(0.164–0.243). Bass was also variable (0.190–0.462), whereas dominant-vocal
agreement was substantially higher on this passage (0.791–0.864). This argues
for role-specific evidence and decisions, not one global separator winner.
Human listening remains required.

The individual provider leaves inside broad `other` have also been compared
across both excerpts using audio-only, bidirectional rankings. On `Be Alone`,
all three Suno A/B labels ranked their counterpart first, but Moises `keys`
did not align with Suno `Keyboard`; the strongest stable pair was Suno
`Synth`. On `I am a Alien mashup`, only Suno `Keyboard` was stable in both
directions. Guitar, synth and residual `Other` labels were not repeatable.
This rules out automatic filename-based leaf activation. Every result remains
private and inactive while a pinned six-source guitar/piano challenger is
prepared.

## Fixed guitar and piano-proxy corpus

[`other-refinement-evaluation-v1.json`](other-refinement-evaluation-v1.json)
freezes the next bounded round before inference: five authorised songs, one
guitar window and one piano-proxy window per song, one installed configuration
and ten reviews. The `In the way` windows remain inside its measured 160.52 s
common provider horizon; this does not erase the shorter-provider limitation.

The selection score is relative activity only. It does not prove that an
instrument is present, and filenames do not become labels of truth. Moises
`rhythm` is an ambiguous guitar cue; Moises `piano` is the direct cue for the
model's disclosed piano proxy; Moises `keys` and Suno `Keyboard`/`Synth` are
broader context. Missing provider labels and provider disagreement are useful
negative evidence.

The local review tool creates no model output itself. It verifies already
completed refinement results, stages exact 15-second provider comparison
excerpts, and serves a self-contained package with byte-range audio from
localhost:

```bash
.venv/bin/python scripts/create-other-refinement-corpus-review.py --plan
.venv/bin/python scripts/create-other-refinement-corpus-review.py \
  --prepare \
  --execution-root "/absolute/path/to/fixed-corpus-execution" \
  --out "/absolute/path/to/fresh-corpus-review"
.venv/bin/python scripts/create-other-refinement-corpus-review.py \
  --serve --review-root "/absolute/path/to/fresh-corpus-review"
```

After all ten listens, the downloaded bundle can be split into strict
per-result feedback plus a sealed corpus index:

```bash
.venv/bin/python scripts/create-other-refinement-corpus-review.py \
  --record \
  --execution-root "/absolute/path/to/fixed-corpus-execution" \
  --review-root "/absolute/path/to/fresh-corpus-review" \
  --bundle "/absolute/path/to/sunofriend-other-refinement-corpus-listening.json" \
  --out "/absolute/path/to/fresh-corpus-feedback"
```

No audio, filenames or browser telemetry enters the listening JSON. Poor or
mixed reports remain valid, the challenger stays accessible, and neither the
review package nor the feedback index selects a model, source or MIDI route.

## Intended evaluation

For each eligible track Sunofriend will:

1. preserve the original and every provider export unchanged;
2. bind exact file hashes and audio geometry in private receipts;
3. select short, source-aligned and level-matched listening windows;
4. compare provider stems without treating either provider as ground truth;
5. run identical seed and full production MIDI processing;
6. compare note timing, pitch, duration, drum family and false positives; and
7. retain human feedback without automatically promoting a separator.

These four songs are a development corpus, not the hidden acceptance set.
Additional authorised music and independent ground-truth multitracks remain
necessary before enabling full-mix separation in Studio or Simple mode.
