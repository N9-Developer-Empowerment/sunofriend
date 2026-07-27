# MIDI-derived song interpretation and listening mastering

Status: paired product contract and Workbench/TUI presentation implemented;
receipt-bound listening-master feedback integration and promotion remain
planned

Sunofriend has two linked creative outputs: reviewed, editable MIDI and a
useful, good-sounding MIDI-derived song-interpretation WAV rendered from the
selected MIDI. The WAV should help a listener hear the song's melody, harmony,
rhythm and structure without being distracted by implausible effects or an
unbalanced technical render.

Here, **interpolation** means a creative interpretation of the source song's
melody, harmony, rhythm and structure. It does not mean reconstruction of the
source waveform, production effects or exact timbre.

The original source stems remain evidence for timing, output horizon and level
relationships; their audio is not mixed into the song-interpretation WAV.
Sunofriend renders the reviewed MIDI through complete, consistent instruments
and balances the selected parts. An optional listening master is a comparative
challenger, not a release master. The MIDI, dry control and gain-only balanced
control remain unchanged.

## Golden control: Pupsies `misery.`

The private Pupsies B-major, 119 BPM result established the first positive
golden control. The user described its `balanced-selected-midi-preview.wav` as
a very good song interpretation that sounded good and made the song easier to
understand. This is important qualitative evidence: a clean MIDI interpretation
can reveal a song even when it does not reproduce every source texture.

It is one accepted local example, not proof that the policy is best for every
song or role. Future changes must therefore compare against this exact control
rather than silently replacing it.

The exact control:

- contains 22 explicitly selected MIDI lanes across 15 source groups;
- includes main and optional alternatives, so its useful interpolation comes
  partly from reviewed layering rather than one automatic winning model;
- has 14 lanes at the current +6 dB source-match ceiling, useful evidence that
  proxy-instrument loudness and clamp behaviour deserve further study;
- has SHA-256
  `c202bba190d0556f2909cb072137f65e92863eba0f6d724c5f279414d98e2763`;
- measured −17.37 LUFS integrated, −0.99 dBTP and 4.0 LU loudness range when
  analysed by the FFmpeg pipeline's independent encoded-artifact pass.

The existing Workbench receipt also reports its own deliberately different
gain-staging measures: −19.565650 dBFS median gated active-block RMS and
−1.000 dBFS sample peak. The two sets of numbers are not interchangeable.
Workbench v3 measures block RMS and sample peak; the listening-master
challenger measures integrated loudness and true peak.

No private source audio, MIDI or WAV is added to the repository by this
documentation.

## Four connected quality goals

### 1. MIDI interpretation

The notes should express the recognisable musical role:

- pitch and octave follow the heard line;
- note starts and ends preserve phrasing and groove;
- sustained accompaniment remains sustained rather than becoming unrelated
  short plucks;
- dense or polyphonic stems keep useful harmony without random note clutter;
- repeated phrases provide repair evidence without erasing genuine variation;
- analytical and AI candidates remain separate and reviewable.

Objective agreement, chord fit and repetition can narrow the result space, but
only explicit listening can establish that an interpretation is musically
useful.

### 2. Instrumentation

Every note in the useful range should sound audibly and consistently. A
complete instrument in the right broad family is preferable to a closer
texture match with silent notes, abrupt timbre changes or unusable velocity
zones.

The first baseline remains role-aware General MIDI/FluidSynth rendering.
Future challengers may use better complete local patches, reviewed GarageBand
recommendations, layered synthesis or rights-qualified source-derived
instruments. They must pass full-range audibility and consistency checks before
timbre similarity is considered.

### 3. Mix

The arrangement should let melody, bass, harmony and rhythm be heard together:

- no bus routinely masks the rest of the arrangement;
- same-source optional alternatives are calibrated as a summed group;
- important melodic parts remain audible;
- the output horizon stays exactly aligned to the source-song horizon;
- every trim, guard and output gain is reported;
- a new policy is compared with the accepted v3 control.

The current Workbench v3 balance is intentionally transparent. It uses 400 ms
active-block measurements, a −70 dBFS absolute gate, a relative gate within
10 dB of each file's active peak, per-lane source matching bounded to
−24…+6 dB, actual waveform-sum calibration for same-source groups, and a
maximum 18 dB drum-bus attenuation. It aims for drums to sit at least 2 dB
below non-drums at the median and no more than 3 dB above them at p95 in
qualifying overlap windows. Final gain aims for −18 dBFS median active-block
RMS with a −1 dBFS **sample-peak** ceiling.

That policy uses gain only. It does not apply EQ, compression, limiting,
saturation, widening, reverb or chorus, and its report correctly says
`mastered: false`.

### 4. Listening master

A listening master makes the already reviewed and balanced MIDI arrangement
comfortable and consistent to audition. It is not a substitute for a
human-approved DAW release master.

Listening Master v1 uses a fixed two-pass FFmpeg `loudnorm` render followed by
an independent third analysis of the encoded PCM24 artifact:

- target integrated loudness: −16 LUFS;
- target loudness range parameter: 11 LU;
- true-peak ceiling: −1 dBTP;
- output: PCM24 WAV held in an owner-only workspace and mode `0600` from
  creation;
- timing: the exact input sample rate, channel count and frame horizon;
- no time shift or time stretch;
- no EQ, widening, reverb, chorus or saturation;
- a fresh, path-free receipt containing input/output hashes, render
  measurements, independently verified encoded-artifact measurements, FFmpeg
  identity, processing and all relevant no-mutation effects.

The hardened evidence uses the `sunofriend.listening-master.v2` receipt
schema. It is intentionally incompatible with the earlier five-field renderer
record because v2 proves that one pinned FFmpeg executable was identity-checked
before and after every pass.

The report says `mastered: true` because loudness normalisation and true-peak
limiting have been applied. It also says `release_master: false` because no
human has approved it as a release master.

## Run Listening Master v1

First create and download the accepted
`balanced-selected-midi-preview.wav` from Workbench. Install FFmpeg with its
`loudnorm` filter, then choose two paths that do not exist:

```bash
sunofriend listening-master \
  "/absolute/path/to/balanced-selected-midi-preview.wav" \
  --out "/absolute/fresh/path/listening-master.wav" \
  --report "/absolute/fresh/path/listening-master.json"
```

The shorter equivalent is:

```bash
sunofriend listening-master BALANCED.wav \
  --out FRESH.wav \
  --report FRESH.json
```

The command refuses to overwrite either output. It accepts mono or stereo WAV,
supports at most 20 minutes, verifies that FFmpeg provides `loudnorm`, runs a
measurement pass and a pinned render pass, trims the result to the exact input
frame count, then measures the encoded PCM24 bytes independently. It fails
instead of publishing a result that misses its fixed integrated-loudness or
true-peak bounds. Private work files live in mode-`0700` directories; file
publication and rollback are device/inode checked so a competing path is
neither overwritten nor removed.

On the Pupsies control, Listening Master v1 produced:

- −16.00 LUFS integrated and −1.00 dBTP;
- the same 7,338,321 frames at 44.1 kHz, with no time shift or stretch;
- PCM24 master SHA-256
  `5e8e59c716602168d1e0996295369e1c3ea536c6ca2aaf3d7798151929fd1e43`;
- hardened receipt-file SHA-256
  `ba7ddbdcd9b2310d2b3c475219c13439021e22e0810989133af9825ba89d8cbb`;
- internal unsigned-payload commitment
  `46981e4547db0ddb1fb5eca357df685377bcedd0842e02c3b0cc123caeed3bbc`.

These measurements establish a reproducible challenger. They do not establish
that it sounds better than the praised gain-only control.

## Control and challenger evidence ladder

Each improvement should move through the same ladder:

1. **Immutable MIDI evidence.** Preserve the exact selected MIDI, decisions,
   candidate lineage and source timing.
2. **Dry unity control.** Keep the existing unlevelled neutral render for
   technical diagnosis.
3. **Accepted balanced control.** Keep the exact v3 gain-only WAV and receipt.
4. **One-variable challenger.** Change one declared dimension, such as the
   complete instrument set, balance policy or listening-master policy.
5. **Objective safety checks.** Verify complete audible note range, exact frame
   horizon, no unexpected clipping, hashes and policy-specific targets.
6. **Level-aware listening comparison.** Compare recognisable phrases and the
   full arrangement without letting simple loudness dominate the choice.
7. **Explicit human decision.** Record better, equivalent, neither or
   cannot-tell against the exact receipts and WAV bytes.
8. **Bounded promotion.** Promote only the reviewed role or policy context
   supported by the evidence. Keep rollback and the control.

No play count, dwell time, download, default button or objective metric counts
as a preference. A new renderer, mix or master must not silently become the
default.

## Explicit local feedback and learning

The feedback contract is receipt-bound and local-first:

- one review identifies the exact balanced-arrangement receipt and preview WAV
  by hash;
- separate ratings cover overall usefulness, MIDI interpretation,
  instrumentation, balance, dynamics and mastering;
- bounded problem tags describe issues such as masked melody, wrong
  instrument, timing errors, excessive note density, mud or harshness;
- optional free text is explicitly private and may contain identifying
  material;
- profile building accepts only explicitly named, still-verifiable reviews;
- profiles summarize prior reviewed contexts and remain advisory.

The standalone feedback foundation is implemented separately from the
listening-master command. It creates immutable, owner-only review JSON pinned
to either the exact balanced control or an exact listening-master receipt/WAV
pair that is itself bound back to that control. Separate path-free artifact and
domain-hashed reviewer/session identities let independent reviewers assess one
artifact while rejecting a duplicate review by the same reviewer. Raw reviewer
keys are never stored. Profiles are deterministic and re-verify every input.
The first Pupsies control review records overall usefulness as excellent; MIDI
interpretation, instrumentation and balance as good; and dynamics/mastering as
cannot-tell. An unmastered control cannot be given a mastering rating.
That exact owner-only v2 review has SHA-256
`a0f2f384ec301fe6213976d2d70827caa79fcc1a38470fd40e40d8a28541c8a0`;
the one-review advisory profile has SHA-256
`92d24715a0868bdaf8481f7b84896c12a0c7cce25dd00244d020f7d6a6be4336`.
There is not yet a mix-feedback Workbench or TUI form. Until that interface and
its end-to-end acceptance tests exist, Sunofriend must not claim that ordinary
listening activity trains or updates the system.

Learning can later improve audition hints, expose historically successful
role/instrument families, or propose a challenger policy. It must never alter
MIDI, reorder candidates, choose a patch, change a selection or promote a
default without a new explicit review.

Before profiles inform any policy or instrument suggestion, their context
schema must also include the audition policy and a scoped renderer/instrument
identity. The current advisory profile groups only by balanced-mix policy,
renderer policy and control/master variant. That is safe for today's single
fixed master policy, but deliberately too weak for automated learning across
future master policies or SoundFonts.

## Maintainability contract

Rendering quality is only sustainable when policy and verification share one
source of truth.

The first refactor is complete:
`workbench_balanced_contract.BALANCED_MIX_CONTRACT` now owns the immutable v3
schemas, measurement values, safety limits, policy labels and mastering
boundary used by both the renderer and cache verifier. A policy change can no
longer leave the verifier silently interpreting a report under duplicated old
constants.

The next maintainability slices should be:

1. create one role/instrument registry for renderer programmes, drum-family
   classification, labels and supported ranges;
2. extract balanced-artifact creation and verification from the large
   Workbench artifact module behind a small typed interface;
3. keep audio measurement, balance policy, rendering, receipt construction
   and feedback as separate testable stages;
4. add golden receipt fixtures and deterministic policy-version tests;
5. make Workbench and TUI thin clients of those shared application services
   instead of reimplementing audio or policy decisions.
6. expose an immutable public listening-master contract plus receipt/audio
   validation boundary before the next master policy or schema, then split
   feedback evidence I/O and advisory-profile aggregation from that validator.
   The current v2 implementation is tested, but its feedback validator still
   imports private mastering helpers and should not carry that coupling into a
   second policy.

Each refactor should preserve byte-level evidence or declare a new policy and
produce a control/challenger comparison.

## Next acceptance increments

1. Add the listening-master action and exact receipt to Workbench without
   replacing the balanced v3 player.
2. Add the same explicit operation to the TUI, including dependency preflight,
   fresh-output semantics and bounded progress.
3. Present a level-aware balanced-control versus listening-master A/B with an
   explicit choice and useful problem tags.
4. Add complete-instrument challengers one role at a time, starting with bass
   and keys, while keeping the MIDI fixed.
5. Compare balance challengers only after instrumentation is held constant.
6. Connect verified local feedback profiles as advisory context, never silent
   selection or default promotion.

The near-term success criterion is not “sounds exactly like the stems.” It is:
the selected MIDI remains editable and recognisable, every chosen instrument
is complete and consistent, the combined interpretation is musically clear,
and a listener explicitly prefers or values the rendered WAV for understanding
or continuing the song.
