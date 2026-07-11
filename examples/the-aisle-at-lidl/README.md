# The Aisle at Lidl — worked example

![The Aisle at Lidl Sunofriend artwork](../../assets/social/the-aisle-at-lidl-square-v2.png)

**[Listen to Version 1 on SoundCloud](https://soundcloud.com/ezzye-1/the-aisle-at-lidl?si=97cf744ff4a743bca875bec3db88024f&utm_source=clipboard&utm_medium=text&utm_campaign=social_sharing).**

“The Aisle at Lidl” is an original song written by the repository maintainer
and included with the author's permission. It demonstrates a practical
four-tool workflow:

1. Suno helped create the initial AI performance.
2. Moises separated the performance into stems and supplied harmonic/timing
   evidence.
3. Sunofriend converted the difficult stems into timing-locked MIDI, preserved
   drum timbre families, separated keys roles and labelled every repair or
   inference.
4. GarageBand supplied the playable software instruments and final production
   environment.

The finished track linked above is Version 1. The purpose of this pack is not
to claim that MIDI replaces the stems; it shows how clean MIDI can reinforce
or replace muddy AI-generated instruments while vocals and useful audio stems
remain in the mix.

## What is included

The files are intentionally small and DAW-neutral Standard MIDI Files:

```text
midi/
├── repair/
│   ├── full-arrangement.mid
│   ├── kick.mid
│   ├── kick-deep.mid
│   ├── kick-high.mid
│   ├── bass-contour-clean.mid
│   ├── bass-raw-verified.mid
│   ├── bass-root-safe.mid
│   ├── keys-main.mid
│   ├── keys-melody.mid
│   ├── keys-accompaniment.mid
│   └── keys-uncertain.mid
└── reconstruct/
    ├── full-arrangement.mid
    ├── hats.mid
    ├── pads.mid
    └── strings-audition-only.mid
```

[`results.json`](results.json) records the source metadata, note counts,
semantic metrics, track/channel expectations and timing baselines. Each listed
part/variant also has a matching `.provenance.json` sidecar that identifies
observed, repaired or inferred notes; combined arrangements intentionally do
not merge those sidecars.

The original 17 WAV stems are not committed: together they are about 765 MB.
The local source folder remains an optional golden test, while the finished
mix is streamed from SoundCloud.

## GarageBand and other DAWs

Set the project tempo to **119 BPM** before importing. For a stem-aligned test,
place audio and MIDI at the same timeline origin, leave MIDI quantisation off,
and disable tempo-follow/stretching on the stems.

Start with [`midi/repair/full-arrangement.mid`](midi/repair/full-arrangement.mid).
Then audition the family and role files separately:

- `kick-deep.mid` and `kick-high.mid` demonstrate preservation of two kick
  timbres instead of collapsing the stem to one pitch.
- `bass-raw-verified.mid`, `bass-contour-clean.mid` and `bass-root-safe.mid`
  expose evidence-first through harmony-safe bass choices.
- `keys-melody.mid`, `keys-accompaniment.mid` and `keys-uncertain.mid` make a
  layered keyboard stem editable by role.
- The reconstruct arrangement uses melody-role keys plus pads and keeps the
  [`strings-audition-only.mid`](midi/reconstruct/strings-audition-only.mid)
  outside the default mix to avoid doubled harmony.

Please test these files in another DAW or music application and submit a
[compatibility report](https://github.com/N9-Developer-Empowerment/sunofriend/issues/new?template=daw-ai-compatibility.yml).

## Reproduce from authorised stems

If you have the maintainer's local stems—or substitute your own folder with the
same naming convention—the accepted repair run is:

```bash
.venv/bin/sunofriend listen-all \
  "work/Lidl-B major-119bpm-440hz" \
  --out-dir work/lidl-v2 \
  --parts bass,cymbals,hat,keys,kick,other_kit,pads,snare,strings,toms \
  --conversion-mode repair \
  --max-iterations 2
```

Commercial product and retailer names describe the production workflow and
song title only. Sunofriend and this example are independent and are not
affiliated with or endorsed by Suno, Moises, Apple, GarageBand, SoundCloud or
Lidl.
