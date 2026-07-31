# Authorised separation examples

This directory is Sunofriend's first authorised real-song separation corpus.
It currently contains four original songs, one Moises stem pack and two
distinct Suno stem packs for each song.

The WAV files remain local and are ignored by Git. At roughly 5.4 GB they are
development evidence, not repository assets. The tracked
[`corpus.json`](corpus.json) records only the bounded inventory needed to plan
repeatable evaluation. Exact hashes belong in fresh evaluation receipts.

## Permission and credit

Ezzye, the creator and copyright holder, supplied these four original tracks
and authorised their use as Sunofriend examples on 31 July 2026. The original
music may be downloaded, studied, transformed and reused with credit.

Use this credit unless the individual track page gives a more specific form:

> Music by Ezzye — <https://soundcloud.com/ezzye-1>

Prefer a link to the individual SoundCloud track when one is available. The
permission recorded here applies to the four named original tracks in this
corpus; it is not a claim about every historical upload on the profile.

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
| Be Alone | 262.56 s, 48 kHz | 17 files | 8 + 8 files, 262.36 s | Ready for excerpt selection |
| I am a Alien mashup | 276.12 s, 48 kHz | 17 files | 9 + 9 files, 275.92 s | Ready for excerpt selection |
| In the way | 225.88 s, 44.1 kHz | 17 files, about 160.72 s | 8 + 8 files, 160.52 s | Investigate source/provider horizon before comparison |
| Tell Me That I Do It Bitch | 186.36 s, 48 kHz | 17 files | 7 + 7 files, 186.36 s | Ready for excerpt selection |

Every corresponding Suno A/B WAV differed after decoding to PCM. The two
packs are therefore retained as distinct separator outcomes. Moises metronome
files end slightly earlier than their musical stems and are timing evidence,
not source roles for MIDI conversion.

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
