# Stems: what they are and where to get them

Sunofriend's Simple and Studio journeys start with a prepared folder of
separated, synchronized WAV files. Existing separated parts in several common
audio formats can now be preserved and converted into that prepared project.
This guide explains what those files are, how to obtain them legitimately,
and why a file called `drums` or `keys` may still contain several sounds.

Only process music you made or have permission or another lawful basis to use.
The more formal term **authorised audio** is used elsewhere in the project for
that boundary.

For the engineering research and implementation plan for accepting a finished
song and making stems locally, see
[Stem access and separation research](STEM_ACCESS_AND_SEPARATION_RESEARCH.md).

## The short answer

A finished song is normally one stereo audio file. A **stem** is a separate
audio file containing one grouped part of that song, such as drums, bass,
vocals or keys.

A stem is often a **grouped submix**, not one original instrument:

- a drums stem may contain kick, snare, hats, toms, cymbals and percussion;
- a keys stem may contain piano, organ, pads and several synthesizers;
- a vocal stem may contain lead, doubles, harmonies and effects; and
- an `other` stem is usually everything the separator did not put elsewhere.

AI separation estimates these groups from a finished mix. It cannot recover
the lost original studio tracks exactly, so bleed, muffling and watery
artefacts are normal.

## What Sunofriend can do today

> **Today, Sunofriend can prepare an existing folder of separated audio
> parts. It still cannot turn one finished song into stems.**

`source-import-folder` accepts 2–64 top-level, already-separated PCM
WAV/AIFF, FLAC, MP3, AAC/ALAC M4A or Vorbis/Opus Ogg assets and prepares one
canonical PCM24 WAV project with receipts. It checks available recorded-origin
evidence, rejects concrete conflicts and warns about different endings. It
does not shift, pad, stretch or normalize audio, prove a downbeat, or repair
alignment. See
[Prepare a folder of existing audio parts](GETTING_STARTED.md#prepare-a-folder-of-existing-audio-parts).

One broad `drums` source can now be transcribed directly with Sunofriend's
mixed-kit family classifier. The result is review-required MIDI, not separated
audio: one dominant family is assigned to each detected onset, layered hits
may collapse, and no kick/snare/hat WAV children are created. Explicit
drum-family source files take automatic-arrangement precedence when they
produce viable MIDI; the broad result remains available for Studio review.

The narrower `source-import` command remains useful for preserving exactly one
standalone authorised asset. Local full-mix separation remains research, not
a product feature.

## Which route should I choose?

| Your situation | Start with |
| --- | --- |
| No stems yet, or just want to try Sunofriend | Use Sunofriend's built-in demo |
| You made the song in a DAW | Export the original synchronized tracks |
| You want a simple cloud experiment | Try BandLab Splitter or Fadr after checking current plans and privacy terms |
| You need narrow drum files | Check the current Moises or Fadr drum options |
| You want local processing on a Mac | Consider Logic Pro, RipX, or LALAL.AI Desktop's Pro-only Lyra mode |
| The song is already in Suno Studio | Use Suno's own stem export |

Sunofriend's own local separator is planned but not yet available. If privacy
is essential today, use an established local tool rather than waiting for an
unimplemented feature.

## Glossary

### Finished mix

The single stereo song that listeners normally hear. Its voices, instruments,
effects and mastering have already been combined.

### Multitracks

The discrete tracks from the original recording or production session, before
they are grouped into stems and mixed. Examples include kick microphone,
snare microphone, bass DI, bass amplifier, piano and lead vocal. Multitracks
usually provide the cleanest source for Sunofriend, but they are rarely
available for a released song.

### Stem

A grouped submix such as all drums, all guitars or all backing vocals. It may
contain several instruments, performers, microphones and effects. iZotope's
[stems and multitracks explanation](https://www.izotope.com/en/learn/stems-and-multitracks-whats-the-difference.html?page=1)
and the Incorporated Society of Musicians'
[stem guide](https://www.ism.org/advice/what-are-stems-in-music-production/)
make the same distinction.

### AI-separated stem

A model's estimate of one musical category from a finished mix. It is useful,
but it is not the lost original studio track. Sunofriend should preserve that
distinction in filenames, receipts and the user interface.

### Broad stem

A large category such as drums, vocals or other. Broad stems are convenient
but can contain several parts with different pitches, rhythms and timbres.

### Refined stem or sub-stem

A narrower child of a broad stem, such as:

```text
drums
├── kick
├── snare
├── hats
├── toms
├── cymbals
└── other percussion
```

Refining a stem is another estimation step. It can make MIDI analysis easier,
but it can also add artefacts. Parent and child stems must not both be
transcribed into the same arrangement or the notes will be duplicated.

### Bleed or leakage

Sound from one part that remains audible in another stem, such as vocals in
the keys stem or cymbals in the snare stem.

### Residual or complement

Everything not assigned to a requested target. It is not necessarily one
coherent instrument. A target plus its residual should approximately
reconstruct the source, but good reconstruction alone does not prove that the
model put each sound in the correct stem.

### MIDI

Instructions describing notes and performance events. MIDI can record pitch,
timing, duration, velocity and controls, but it does not contain the original
audio, words, voice, instrument texture or effects.

### Instrument or sample bundle

Sounds used to play MIDI. An instrument bundle can help the interpretation
resemble a source stem, but it is not itself a stem.

### Lossless and lossy audio

WAV, AIFF and FLAC commonly preserve the full decoded signal. MP3, AAC and
similar formats discard information to reduce file size. Lossy files can
still be useful, but stem separation cannot restore detail that compression
removed.

## Three ways to obtain stems

### 1. Export your own tracks

If you made the song in a DAW, export synchronized tracks or grouped stems
from bar one to the same ending. This is normally the cleanest and most
accurate source.

### 2. Use authorised stems or multitracks

An artist, producer, music generator or education library may provide stems.
Check the licence for each project: permission to practise does not
automatically include permission to publish a remix or redistribute the
source files.

Useful starting points include:

- Sunofriend's built-in copyright-safe demo;
- [Telefunken Live From The Lab](https://www.telefunken-elektroakustik.com/livefromthelab/),
  which provides labelled WAV multitracks for home-studio and educational use;
- the [Cambridge Music Technology multitrack library](https://cambridge-mt.com/ms2/mtk/),
  whose projects have their own usage terms; and
- stems exported from a song-generation account or project that you are
  allowed to process.

### 3. Separate an authorised finished recording

Local software or an online service can estimate stems from a finished mix.
This is convenient, but approximate. Prefer a lossless source and compare the
stems by listening before transcription.

## Current provider guide

Provider plans, prices, categories and terms change. These links and notes
were checked on 29 July 2026. They are neutral ordinary links, not affiliate
links.

| Provider | Useful for | Important boundary |
| --- | --- | --- |
| [Moises](https://moises.ai/) | Detailed cloud separation; its Pro documentation includes kick, snare, toms, hi-hat, cymbals and other drums | Audio is uploaded. Paid Web/Desktop plans can export WAV. See the [official instrument list](https://help.moises.ai/hc/en-us/articles/360010972019-Which-instruments-can-be-separated-on-Moises) and [privacy policy](https://help.moises.ai/hc/en-us/articles/360013805640-Privacy-Policy). |
| [LALAL.AI](https://www.lalal.ai/) | Target-plus-complement separation, several instruments, cloud and a local desktop option | The desktop app uses cloud processing by default. Offline on-device Lyra processing currently requires Pro and supports fewer stems. Check the [Stem Splitter](https://www.lalal.ai/stem-splitter/), [desktop app](https://www.lalal.ai/desktop-app/) and [privacy policy](https://www.lalal.ai/privacy-policy/) before supplying private audio. |
| [BandLab Splitter](https://www.bandlab.com/splitter) | Low-friction cloud experiment, auditioning and direct MIDI export | Some categories require membership and processing is online. See [Using Splitter](https://help.bandlab.com/hc/en-us/articles/16560236938777-Using-BandLab-Splitter). |
| [Fadr](https://fadr.com/) | Cloud stems, MIDI, chords, key and tempo; paid drum and melody refinements | Public privacy information does not yet answer every unreleased-audio question. See the [stems guide](https://fadr.com/help/stems). |
| [Suno stem separation](https://help.suno.com/en/articles/12702337) | Material already created in, or legitimately uploaded to, a Suno workflow; broad and requested-instrument splits | Paid cloud feature; labels can be wrong and absent targets may still consume credits. Check upload rights and current terms. |
| [RipX DAW](https://hitnmix.com/) | Local desktop separation, note-level editing and MIDI export | Commercial application; check current macOS support and use only authorised audio. |
| [Logic Pro Stem Splitter](https://support.apple.com/en-gb/guide/logicpro/lgcp61bae908/mac) | Local Apple-silicon separation into drums, bass, vocals, guitar, piano and other instruments | Requires Logic Pro and Apple silicon. It is not available inside GarageBand. |

No provider is yet labelled “best for Sunofriend MIDI.” Marketing quality and
pleasant isolated audio do not prove note, onset, octave or alignment
accuracy. Sunofriend now has a strict, backend-neutral receipt contract for a
future local bake-off, but no real separation backend has been connected to
it. The bake-off still needs to measure those downstream results.

## What files should I bring back?

After exporting or separating a song:

1. Prefer lossless WAV, AIFF or FLAC files when that option is available.
2. Make every file start at the same point and end at the same point.
3. Use recognisable names such as `bass.wav`, `drums.wav` and `vocals.wav`.
4. Put the files together in one folder.
5. Continue with [Getting started](GETTING_STARTED.md).

Simple and Studio still consume WAV. The folder importer can prepare supported
lossless or lossy parts as one complete canonical WAV project first. Turning
an MP3 into WAV changes its representation, not its sound quality, and does
not restore discarded information.

## Rights and privacy checklist

Before processing a recording, ask:

1. Do I own it, have permission, hold a suitable licence, or have another
   lawful basis to process it?
2. Is it unreleased, confidential or commercially sensitive?
3. Does the chosen tool process locally or upload the audio?
4. How long does the provider retain the upload and derived files?
5. May the provider use uploads to improve models or services?
6. May I publish the MIDI, sample instruments, remix or separated audio?

Owning a stream, download or subscription does not automatically grant rights
to copy, adapt, upload or distribute the recording. See
[GOV.UK copyright guidance](https://www.gov.uk/using-somebody-elses-intellectual-property/copyright).
This guide is practical product information, not legal advice.

## Affiliate-link policy

Sunofriend does not currently publish a tracked provider link.

LALAL.AI has a public
[affiliate programme](https://www.lalal.ai/affiliate-program/). Moises has a
[creator Partner Program](https://moises.ai/partner-program/), but its public
page does not promise commission. No tracked link should be added until
Sunofriend has been accepted and the exact commercial terms have been
verified.

If compensated links are added later, technical ranking must remain
independent of commission, an ordinary link must remain available, and the
commercial relationship must be clearly disclosed beside the link. This
follows the UK ASA/CAP guidance that
[affiliate marketing must be identifiable](https://www.asa.org.uk/advice-online/affiliate-marketing.html)
and the US FTC principle that a material connection needs a clear,
hard-to-miss disclosure close to the endorsement. The implementation detail
belongs in the
[engineering research and policy](STEM_ACCESS_AND_SEPARATION_RESEARCH.md#privacy-security-and-licensing),
not the beginner journey.

## Common questions

### Are stems always single instruments?

No. A stem is commonly a group of tracks. Treat names as useful categories,
not proof of isolation.

### Why does a drum stem contain several drums?

That is normal. A broad drum stem can later be analysed as a mixed kit or
refined into kick, snare, hats, toms, cymbals and other percussion.

### Is `other` an instrument?

Usually not. It is a residual group and can contain guitars, keyboards,
strings, effects and separation artefacts together.

### Can Sunofriend use MP3 today?

Yes, when the MP3 is one already-separated part. `source-import-folder` can
prepare 2–64 supported parts as one canonical WAV project for Simple or
Studio. It does not split a finished MP3 into stems, repair alignment or
restore information discarded by lossy compression.

### Can I label a pad as `pads`?

Not in the current folder-import contract. Production currently synthesizes
pads from keys and has no observed-pads conversion job. A genuinely
string-like sustained part may be mapped to `strings`; otherwise leave it
unresolved rather than mislabelling it. A broad `drums` part can be converted
to review-required mixed-kit MIDI, but it is not split into narrower audio
stems.

### Can I publish AI-separated stems?

Only when your rights in the recording and the provider's terms allow it.
Private processing permission and public redistribution permission are
different questions.

### Why do separated stems sound watery or muffled?

The model is estimating overlapping sources from one mix. Time-frequency
masking, phase reconstruction, reverb and sounds shared between instruments
can produce bleed, holes, smearing or metallic artefacts.
