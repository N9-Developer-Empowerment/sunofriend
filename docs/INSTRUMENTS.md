# Instruments, sound matching and stem-derived sample packs

Instrument selection is an arrangement decision, not a final transcription
step. The same notes, timing and velocities can feel entirely different when
the patch changes its attack, decay, brightness, noise, articulation or
register. Sunofriend therefore produces audition evidence and keeps the final
choice with the musician.

## What is available on this Mac?

Run:

```bash
sunofriend instrument-inventory \
  --out work/instruments/installed.json
```

The report lists:

- GarageBand factory sampler assets already installed under the system sound
  library;
- GarageBand and Logic `.exs` sampler-instrument definitions, including their
  categories and searchable preset names;
- installed GarageBand/Logic drum sample groups;
- Apple and third-party Audio Unit music devices exposed by `auval`; and
- the GarageBand version and Audio Unit component directories.

It deliberately reports only representative factory sample paths rather than
thousands of internal files, while retaining the complete installed sampler
preset catalogue. Sunofriend reads those assets for local analysis; it does
not alter or redistribute them.

GarageBand can download more Apple content from **GarageBand > Sound Library >
Download All Available Sounds**. It also supports compatible 64-bit Audio Unit
plug-ins. Install third-party components only from a supplier you trust, follow
its licence, restart GarageBand, and enable the instrument in GarageBand's
Audio/MIDI settings if macOS has not validated it automatically.

Apple references:

- [Download additional sounds and loops for GarageBand](https://support.apple.com/en-euro/101959)
- [Use Audio Units plug-ins on Mac](https://support.apple.com/en-gb/102239)
- [GarageBand supports 64-bit Audio Units](https://support.apple.com/en-us/101846)
- [AVAudioUnitSampler loads DLS and SF2 sound banks](https://developer.apple.com/documentation/avfaudio/avaudiounitsampler/loadsoundbankinstrument%28at%3Aprogram%3Abankmsb%3Abanklsb%3A%29)

## Find instruments by sound

Given a source stem and the MIDI already aligned to it:

```bash
sunofriend instrument-match \
  "/absolute/path/to/song-bass.wav" \
  "/absolute/path/to/bass_listened.mid" \
  --kind bass \
  --out-dir work/instruments/bass
```

The command uses two independent evidence paths:

1. **Installed factory assets.** MIDI-aligned excerpts from the stem are
   compared with readable GarageBand/Logic sample recordings. Audio features
   contribute 92% of the ranking and a deliberately weak role/name prior
   contributes 8%.
2. **Rendered performance proxies.** For pitched parts, the complete MIDI is
   rendered with role-appropriate General MIDI programs through FluidSynth.
   Aligned spectral shape contributes 70%, dynamics 15% and attack activity
   15%. The best MIDI and WAV auditions are retained.

Outputs are:

```text
work/instruments/bass/
├── instrument_matches.json
├── GARAGEBAND_AUDITION.md
├── timbre_profiles.svg
└── gm_auditions/
    ├── 01-...mid
    ├── 01-...wav
    └── ...
```

The scores rank only the candidates examined for that stem. They are not
probabilities, proof of the original instrument, or a guarantee that the
highest isolated-timbre match will sit best in the full mix. GarageBand does
not expose its complete patch renderer as a supported headless API, and patch
names do not always match underlying sample-asset names. Use the report as a
shortlist, then listen in the actual song.

Each factory-family match also lists related installed sampler definitions
when their names overlap, turning a sample-family result such as `Picked
Electric Bass` into concrete local preset names such as `Picked Rock Bass`.

Useful controls:

```bash
# Factory assets only; useful without FluidSynth
sunofriend instrument-match STEM.wav PART.mid \
  --kind keys --out-dir work/instruments/keys --no-gm

# Render all 128 General MIDI programs instead of the role shortlist
sunofriend instrument-match STEM.wav PART.mid \
  --kind lead --out-dir work/instruments/lead-all --all-programs

# Select one note-bearing track from a multitrack MIDI
sunofriend instrument-match STEM.wav SONG.mid \
  --kind bass --track-index 2 --out-dir work/instruments/bass-track-2
```

`listen-all` now puts name-based starting suggestions and an exact
`instrument_match_command` argument list beside every successful part in its
summary JSON.

## Make a new instrument from a stem

This is possible when the stem contains clean, isolated notes and you own or
have permission to sample the recording:

```bash
sunofriend sample-pack \
  "/absolute/path/to/song-bass.wav" \
  "/absolute/path/to/bass_listened.mid" \
  --kind bass \
  --name "Song Walking Bass" \
  --out-dir work/sample-packs/song-bass
```

Sample Instrument v2 uses the MIDI note boundaries as evidence, rejects
overlapping notes by default, keeps a short natural tail, applies small
click-removing fades, normalises conservatively, and chooses at most one strong
sample per MIDI pitch. The output is:

```text
work/sample-packs/song-bass/
├── sunofriend-instrument.aupreset # GarageBand-selectable AUSampler wrapper
├── sunofriend-instrument.sf2   # self-contained SoundFont sample bank
├── sunofriend-instrument.sfz   # mapping for compatible third-party samplers
├── garageband-audition.mid     # one note for every generated zone
├── garageband-audition.wav     # the exact SF2 rendered through FluidSynth
├── sample_pack.json            # roots, ranges, tuning and source evidence
├── README.md                   # instructions specific to this instrument
└── samples/                    # cleaned 24-bit source WAV zones
```

The SF2 embeds mono PCM16 copies for broad sound-bank compatibility, while the
separate extracted WAVs remain PCM24. Each melodic sample is mapped only to
nearby notes—six semitones by default—and a stable pitch estimate can add a
cents correction without modifying the source WAV. The report distinguishes
`applied`, `no-stable-pitch`, `rejected-unstable` and other tuning outcomes.
Keys outside all reported zones remain silent rather than being heavily
pitch-shifted.

### Direct GarageBand import

1. Drag `garageband-audition.mid` into the GarageBand Tracks area and select
   the new software-instrument track.
2. Open Smart Controls. In the instrument plug-in slot choose **AU Instruments
   > Apple > AUSampler > Stereo**.
3. Open AUSampler's preset menu (normally labelled **Manual**), choose its
   load/open setting command, and select `sunofriend-instrument.aupreset`.
   The `.sf2` is the referenced sound bank and is intentionally greyed out in
   GarageBand's plug-in-preset chooser.
4. Play the audition region to check every root and transposed zone. Replace it
   with the song MIDI when satisfied.
5. Save the configured GarageBand track as a custom patch for future projects.

The `.aupreset` is a public AUSampler state wrapper around Apple's documented
SF2 sound-bank support; it is not a private GarageBand project or patch. The
audio remains embedded in the SF2. Keep the preset and bank at their generated
paths; regenerate the preset after moving the sample-pack directory.

Useful controls:

```bash
# Restrict each source sample to three semitones of transposition
sunofriend sample-pack STEM.wav PART.mid --kind bass \
  --max-transpose 3 --out-dir work/sample-packs/tight-bass

# Preserve raw sample tuning and skip the FluidSynth audition WAV
sunofriend sample-pack STEM.wav PART.mid --kind lead \
  --no-auto-tune --no-preview --out-dir work/sample-packs/raw-lead
```

Use `--allow-polyphonic` only as an explicit experiment. Chords, separator
bleed, room sound, reverb, vibrato and transitions become baked into a sample
and then repeat on every played note. Sample Instrument v2 also does not infer
loop points or velocity layers, so a long held MIDI note ends when its embedded
sample ends.

## Recommended listening loop

1. Convert and evaluate the stem-to-MIDI timing and pitch first.
2. Run `instrument-match` on the unchanged, aligned stem and main MIDI.
3. Audition the top factory families and retained GM WAVs in isolation.
4. Audition them again with the complete song; compare emotion, register,
   masking and articulation, not just spectral similarity.
5. Save the winning GarageBand patch on the reusable Clip v1 part:

   ```bash
   sunofriend clip-instrument CLIP_ID \
     --suggest "Stinger Bass" --suggest "Picked Electric Bass"
   ```

6. If no installed sound works and the source has isolated notes, build a
   `sample-pack` and audition it in AUSampler or an SFZ-compatible Audio Unit.

This workflow makes instrument choice repeatable without pretending that
emotion can be reduced to a single automatic score.
