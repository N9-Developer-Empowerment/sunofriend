# Vocal comping research and dependency assessment

Prepared: 1 August 2026

Status: current primary-source research for planning only. No listed code,
model or checkpoint has been installed, downloaded, approved or integrated.

## Industry reality

Vocal comping is normal studio practice. Apple describes comping as selecting
the best parts of multiple performances and piecing them into a composite take
with Logic Pro’s Quick Swipe Comping. Avid’s Pro Tools documentation describes
track compositing with alternate playlists and a target playlist. These tools
make the editing workflow efficient, but the person still decides which
performance to use.

Commercial tools then address adjacent stages:

- Celemony Melodyne edits pitch, vibrato, volume, sibilants, note length,
  timing and formants;
- Synchro Arts VocAlign matches the timing and, in Pro, pitch of a dub to a
  guide with adjustable tightness; and
- Revoice Pro manipulates voice timing, pitch and loudness and can match a dub
  to a guide.

This validates the problem, the guide/target concept and the need to preserve
natural vibrato and timing. It does not supply Sunofriend’s missing automatic
take-selection layer.

Primary sources:

- [Logic Pro comping overview](https://support.apple.com/en-mide/guide/logicpro/lgcp317d758e/10.7/mac/11.0)
- [Pro Tools 2025.12 Reference Guide](https://resources.avid.com/SupportFiles/PT/Pro_Tools_Reference_Guide_2025.12.pdf)
- [What is Melodyne?](https://www.celemony.com/en/melodyne/what-is-melodyne)
- [VocAlign timing and pitch matching](https://www.synchroarts.com/manuals/VocAlign6Pro/Manual/HTML/adjusting-the-automatic-time-and-pitch-matching.html)
- [Revoice Pro 5 overview](https://www.synchroarts.com/manuals/RevoiceProV5/Manual/HTML/welcome-to-revoice-pro.html)

## Direct open-source precedent

### AI Vocal Comp

[AI Vocal Comp](https://github.com/aliudovik/AI-Vocal-Tool) is the closest
direct implementation found. Its public `v0.1.0-alpha` workflow records looped
takes, pads and splits them, applies the reference take’s boundaries to all
takes, ranks segments, allows manual boundary/crossfade edits and exports a
comp. It is MIT licensed.

Its useful design ideas are:

- one recording action for repeated loop takes;
- deterministic take geometry;
- BPM-aware segmentation near RMS valleys;
- a non-destructive comp map;
- per-segment audition; and
- explicit crossfade editing.

Its current limits are material for Sunofriend:

- pitch accuracy is the proportion of voiced frames within the selected key,
  not similarity to a target melody;
- a reference take supplies fixed segmentation to all takes;
- the README exposes no known-lyrics or phoneme alignment;
- selection is per segment rather than a documented global sequence objective;
- the optional Balanced Random Forest was trained on a self-collected set of
  Jingle Bells and Happy Birthday takes; and
- the crossfade is described as an alpha linear implementation.

Recommendation: inspect its comp-map and boundary concepts during design, but
do not adopt its score or dataset as Sunofriend’s selection authority.

## Singing-specific analysis candidates

| Candidate | Primary capability | Current fit | Main blocker or caution |
| --- | --- | --- | --- |
| Existing Sunofriend vocal path | continuous pYIN/RMVPE evidence, Basic Pitch notes, GAME boundaries, phrase review | **Required baseline** | no lyrics, multiple-take project or waveform comping |
| [SOFA](https://github.com/qiuqiao/SOFA) | singing-oriented forced phoneme alignment; PyTorch and ONNX inference; confidence output | **Best first lyric-aligner bake-off candidate** | default resources are Mandarin-oriented; exact English model/checkpoint terms, accuracy and Mac runtime need audit |
| [STARS](https://github.com/gwx314/STARS) | phoneme/word alignment, note transcription, technique and global style annotation | **High-value research challenger** | tested on Python 3.10, PyTorch 2.4 and CUDA; bilingual Chinese/English checkpoint still needs exact weight audit and local feasibility proof |
| [ROSVOT](https://github.com/RickyL-2000/ROSVOT) | robust singing note transcription and note-word alignment when word boundaries are supplied | **Independent note/boundary challenger** | published checkpoint is Mandarin-trained; documented runtime is CUDA/PyTorch; word boundaries come from another aligner |
| [GAME](https://github.com/openvpi/GAME) | singing note/boundary extraction and alignment to labelled word boundaries | **Already relevant in Sunofriend** | stochastic boundary decoder requires seed; does not itself establish canonical lyrics |
| [VocalParse](https://github.com/pymaster17/VocalParse) | joint lyrics, pitch, note values and BPM in a 1.7B audio-language model | **Later exploratory challenger** | May 2026 release, Mandarin-centric, large runtime, segments over 30 seconds must be split, and released checkpoint does not provide physical note durations |
| [UltraSinger](https://github.com/rakuri255/UltraSinger) | orchestration of lyrics, pitch, MIDI and karaoke outputs | **Architecture reference** | not a take selector or natural waveform comping engine |

The code repositories above identify STARS, ROSVOT, GAME and SOFA as MIT
licensed, while VocalParse identifies its implementation and released model as
Apache-2.0. Code licence is not enough: every exact checkpoint, training-data
relationship, transitive runtime and redistribution plan still needs a separate
Sunofriend admission record.

Relevant papers and model cards:

- [STARS paper](https://arxiv.org/abs/2507.06670)
- [ROSVOT paper](https://arxiv.org/abs/2405.09940)
- [VocalParse model card](https://huggingface.co/pymaster/VocalParse)

## Known-lyrics alignment candidates

### Preferred experiment order

1. **Manual phrase/line timing** for the first MVP. This makes take scoring and
   comp assembly testable without conflating them with ASR research.
2. **SOFA** as the first singing-specific forced-alignment challenger.
3. **Montreal Forced Aligner** as a mature speech-domain baseline.
4. **STARS** as a singing-specific joint alignment/transcription challenger if
   its checkpoint and runtime clear the local gate.
5. **Whisper or VocalParse** only as mismatch/anomaly evidence, not the source
   of canonical lyric text.

### Montreal Forced Aligner

[MFA 3.x](https://montreal-forced-aligner.readthedocs.io/en/v3.4.1/user_guide/index.html)
takes an orthographic transcript, a pronunciation dictionary and an acoustic
model to generate word/phone timing. It is a useful controlled baseline with a
large model ecosystem, but its normal acoustic domain is speech. Sung vowels,
melisma, altered pronunciation and long notes require a measured singing
bake-off and editable results.

### WhisperX

[WhisperX](https://github.com/m-bain/whisperX) combines ASR with wav2vec2
alignment for word-level timestamps. It is BSD-2-Clause code, but its purpose
and paper are long-form speech. It should be treated as a speech-domain
comparison, not a preferred Mac singing aligner.

### whisper.cpp

[whisper.cpp](https://github.com/ggml-org/whisper.cpp) is attractive for rough
local recognition because Apple Silicon is a first-class target using
Accelerate, Metal and optional Core ML. Its proper role here is to flag
possible missing/repeated/substituted words or ad-libs and locate rough
sections. Forced alignment against the known text remains a separate stage.

### Research context

Lyrics-to-audio alignment is a recognised Music Information Retrieval task,
not a solved speech-transcription detail. MIREX defines it as synchronising a
singing recording and written lyrics and evaluates word boundaries in mixed
music. This reinforces the need for singing-specific evaluation rather than
assuming normal ASR timestamps are accurate.

- [MIREX 2024 Lyrics-to-Audio Alignment](https://music-ir.org/mirex/wiki/2024%3ALyrics-to-Audio_Alignment)
- [MIREX 2019 task and datasets](https://music-ir.org/mirex/wiki/2019%3AAutomatic_Lyrics-to-Audio_Alignment)

## Performance synchronisation

[Sync Toolbox](https://github.com/groupmm/synctoolbox) provides MIT-licensed
reference pipelines for music synchronisation with dynamic time warping,
including multiscale and high-resolution methods. It is relevant for aligning
performances and target features, but it does not determine lyric correctness,
vocal quality or take preference.

Recommendation: compare a narrow internal constrained-DTW baseline with Sync
Toolbox on the benchmark, but retain explicit common recorded zero. Local warp
is analytical correspondence, not authority to time-stretch source audio.

## Waveform assembly and correction

The phrase-level renderer initially needs only decoded PCM, exact frame crops,
short fades, bounded level trims and crossfades. NumPy and SoundFile are already
inside Sunofriend’s optional audio stack. No new model is required.

[Rubber Band Library](https://github.com/breakfastquay/rubberband) is a
technically relevant high-quality time-stretching and pitch-shifting option,
and its R3 engine is described as especially suitable for vocals and smooth
onsets. Its open-source licence is GPL, with commercial licensing offered for
other distribution terms. Sunofriend is Apache-2.0; therefore no dependency or
distribution decision should be made without explicit legal/licensing review.

Commercial Melodyne, VocAlign or Revoice workflows may remain manual DAW
handoffs. They should not become required local engines for Sunofriend’s core
open-source feature.

No correction engine should be chosen until an uncorrected comp wins the base
take listening gate. Correction can otherwise mask whether take selection and
joins work.

## Voice enhancement is a separate product mode

Research such as NeuralSVB and singing voice conversion may eventually render
an improved performance with the singer’s timbre, but that is generation, not
comping. It changes the authenticity and consent/provenance contract.

The future distinction must be explicit:

- **Authentic comp:** original recorded regions plus disclosed bounded
  pitch/time correction.
- **Generated voice:** model-rendered regions with a voice-consent and model
  provenance record.

Do not mix the two in the first feature or call generated audio a take.

## Dependency/admission checklist

Before any candidate is installed or run:

1. Pin the exact repository revision and licence file.
2. Identify every required checkpoint and its immutable full hash.
3. Establish checkpoint-specific usage and redistribution terms.
4. Inventory all packages, native libraries and licences.
5. Confirm supported Python/macOS/Apple-Silicon execution.
6. Define a path-free request/result protocol and fixed resource bounds.
7. Prevent network access during inference and observe a deliberate denial.
8. Confine writes to an owner-only fresh output.
9. Preserve source, model, runtime and result identities.
10. Run only authorised short excerpts first.
11. Compare against the current Sunofriend baseline on identical inputs.
12. Require human listening before any product/default decision.

## Research conclusion

The attachment’s overall verdict stands, with three refinements:

1. AI Vocal Comp is a useful alpha precedent, not evidence that target-aware
   automatic comping is solved.
2. Because lyrics are known, a singing-oriented forced aligner such as SOFA is
   more directly relevant than making Whisper the centre of the pipeline.
3. The first implementation should deliberately exclude ASR, word-level cuts
   and pitch correction so the core claim—better take selection with natural
   phrase continuity—can be evaluated cleanly.
