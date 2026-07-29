# Stem access and local separation research

Status: **research and architecture decision complete; S1 multi-file source
preparation accepted; source separation not implemented**

Checked: 29 July 2026

## Contents

- [Decision and current boundary](#executive-decision)
- [Terms and ways to obtain stems](#terminology-contract)
- [Local model landscape](#open-source-and-local-model-landscape)
- [Input and source-project contracts](#input-format-contract)
- [Quality and bake-off](#quality-and-bake-off-contract)
- [TUI and Workbench experience](#tui-and-workbench-experience)
- [Phased delivery plan](#phased-delivery-plan)
- [Tests and open questions](#tests-required-by-implementation)

## Executive decision

Sunofriend should eventually accept either:

1. one authorised finished song file;
2. a folder of existing stems or multitracks; or
3. the built-in demo.

It should not hide full-mix separation inside the existing transcription
functions. Add a source-preparation programme before the stable conversion
pipeline:

```text
authorised source audio
        |
        v
canonical, immutable local audio asset
        |
        v
broad separator candidates
  vocals / drums / bass / other
        |
        v
optional role-specific refinement
  drums -> kick / snare / hats / toms / cymbals / other_kit
  vocals -> lead / backing
  other -> keys / guitars / strings / wind / residual
        |
        v
accepted active leaf stems
        |
        v
existing multi-method MIDI conversion
        |
        v
balanced MIDI-derived interpretation WAV and GarageBand ZIP
```

The first engineering increment should be **canonical multi-format import
plus a minimal source-project manifest**, not a model download. Import must
preserve the role, key, BPM, tuning, chord-document and filename context used
by today's pipeline. It must not replace named stems with anonymous
`source.wav` files and then ask legacy discovery to guess what they mean.

That bounded S1 source-preparation slice is now implemented. `source-doctor`
and `source-import` inspect and prepare one asset.
`source-import-folder` prepares 2–64 already-separated, synchronized parts as
one fresh canonical WAV project that existing Simple and Studio paths can
consume. There is still no full-mix separator.

The first model increment should be a measured bake-off, not a hard-coded
winner. HTDemucs, BS-RoFormer, MelBand-RoFormer and other systems are
unverified candidates until one exact runtime/checkpoint pair has known terms,
a fixed hash, offline inference, supported-Mac measurements and downstream
MIDI evidence. Narrow drum and query-based models remain optional experiments
under the same rule.

## Why this is a separate programme

The current Sunofriend contract is honest and useful:

- production conversion reads synchronized top-level WAV stems;
- different analytical and AI transcription candidates remain separate;
- Simple mode can make an automatic unreviewed MIDI/WAV/ZIP result;
- Studio can compare evidence and record explicit choices; and
- model downloads and non-permissive checkpoints are optional and explicit.

Full-mix separation changes the evidence before transcription. A poor
separator can remove note attacks, move harmonics to the wrong stem or create
plausible-sounding material with the wrong timing. That would affect every
later candidate. The source-preparation boundary therefore needs its own
lineage, quality gates, licences, review and cache.

## What the repository already has

### Production boundary

The production paths in `listen_all.py`, `tui_conversion.py`, `tui.py`,
`pipeline.py` and `cli.py` discover top-level lowercase `*.wav` files.
`workbench_catalog.py` advertises WAV/WAVE, AIFF, FLAC, MP3 and M4A by suffix,
but `workbench_timeline.py` only extracts waveform evidence from WAV. Format
support is therefore inconsistent.

Metadata currently comes mainly from folder and filename conventions. Role
discovery understands kick, snare, hats, cymbals, toms and `other_kit`, but
not one generic composite `drums` source. A separator's `other.wav` could also
be mistaken for a coherent synth role when it is normally a mixture.

The accepted S1 preparation boundary now provides:

- `source-doctor`, a read-only report over existing local FFmpeg/FFprobe
  binaries;
- `source-import SOURCE --out-dir FRESH_OUTPUT`, which executes by default;
- `source-import-folder SOURCE_FOLDER --out-dir FRESH_OUTPUT`, with separate
  read-only plan and execute invocations for 2–64 existing separated parts;
- the explicit read-only `source-import ... --plan` form;
- immutable original and deterministic PCM24 canonical assets;
- per-source receipts, `INPUT/source-folder-import.json` and
  `INPUT/source-project.json`;
- tested preservation of hash, role, key, BPM, tuning, chord-document and
  clock evidence without normalization, alignment correction, network access
  or installation; and
- direct compatibility of the prepared top-level canonical WAV files with
  existing Create, TUI and Workbench discovery.

Folder import does not recurse, separate a mix, shift, pad, stretch or
normalize files, prove a downbeat, or repair alignment. Missing recorded-origin
evidence requires explicit acknowledgement; concrete origin conflicts block
execution. Execution replans current inputs rather than replaying a stored
plan. Composite `drums` is preserved for S2 rather than silently treated as
one drum family. `pads` is not accepted as an observed S1 role because
production currently synthesizes pads from keys and has no observed-pads job.

### Reusable foundations

Sunofriend already provides:

- drum-family MIDI classification in `transcribe_drums.py`;
- leakage and uncertain-family evidence in `conversion.py`;
- source/MIDI evaluation in `evaluate.py`;
- AI candidate quality gates in `ai_quality.py`;
- note-level lineage and content-addressed receipts;
- local Workbench comparison and bounded playback; and
- an isolated AI environment containing PyTorch and Demucs 4.0.1.

The current Demucs cleanup experiment is not a production separator. It is
limited to a 60-second, 44.1 kHz CPU excerpt and emits one target plus a
residual. Its checkpoint is recorded as private evaluation because the
pretrained-weight terms were not sufficiently clear. It proves worker
isolation and provenance concepts, not public product readiness.

## Terminology contract

The user-facing definitions are in [Stems](STEMS.md). The implementation must
preserve these distinctions:

| Term | Product meaning |
| --- | --- |
| Original asset | The exact file supplied by the user; immutable and hashed |
| Canonical asset | A deterministic decoded PCM representation; derived, not a replacement |
| Original multitrack | A discrete production track supplied by its owner or authorised source |
| Original stem | A grouped submix exported by the project owner |
| Estimated stem | A model output inferred from a mix or parent stem |
| Composite source | A part expected to contain multiple roles, such as drums or other |
| Leaf source | The currently active narrowest source selected for transcription |
| Complement/residual | Material not assigned to a target; not one instrument |
| Separation candidate | One immutable model result; never silently promoted |

The interface should say **estimated stem**, not “recovered original stem,”
when a model produced it.

## Ways users can obtain stems

### Best evidence: their own production

Synchronized original multitracks or DAW-exported stems retain the most note,
timing and timbre evidence. They should remain the preferred source.

### Authorised education and demonstration material

Sunofriend's demo is the safest first experience. For broader testing,
[Telefunken Live From The Lab](https://www.telefunken-elektroakustik.com/livefromthelab/)
offers labelled 24-bit/48 kHz WAV multitracks for stated home-studio and
educational use, while the
[Cambridge Music Technology library](https://cambridge-mt.com/ms2/mtk/)
indexes freely downloadable mixing-practice projects. Each project's terms
still govern reuse and publication.

### Commercial or cloud separation

The provider comparison and affiliate policy are maintained in
[Stems](STEMS.md). The main product conclusions are:

- Moises is technically relevant for detailed drum parts;
- LALAL.AI is the clearest genuine affiliate candidate, but its desktop app
  uses cloud processing by default; the current offline Lyra mode requires
  Pro and supports a smaller role set;
- BandLab and Fadr are approachable beginner experiments;
- Suno is convenient for material already authorised inside its workflow;
- RipX and Logic Pro are useful local commercial options; and
- no provider may be called best for Sunofriend until downstream tests support
  that claim.

Provider rankings must never depend on commission. No affiliate URL should be
published before programme acceptance and link-level disclosure.

## Open-source and local model landscape

Code licence, checkpoint licence and training-data provenance are separate
facts. An MIT inference repository does not make every downloaded checkpoint
commercially redistributable.

### Broad fixed-role separation

| Candidate | Outputs and evidence | Mac position | Licence/provenance position | Programme position |
| --- | --- | --- | --- | --- |
| [Demucs / HTDemucs](https://github.com/facebookresearch/demucs) | Stable four-source vocabulary: drums, bass, vocals, other. Experimental `htdemucs_6s` adds guitar and piano, but the official README warns that piano has substantial bleed. | Original project supports MPS but is no longer actively maintained. [Demucs-MLX](https://github.com/ssmall256/demucs-mlx) and [demucs-infer](https://github.com/openmirlab/demucs-infer) are possible adapters to test. Demucs-MLX's first-use download behaviour must be disabled or preinstalled and then verified offline. | Code is MIT; checkpoint terms and hashes still require an explicit registry entry. | Unverified broad-baseline candidate. |
| [BS-RoFormer architecture](https://arxiv.org/abs/2309.02612) | Strong four-stem research result, particularly relevant to the bass problem. | PyTorch and emerging MLX adapters exist; no runtime/checkpoint pair is selected here. | Architecture/runtime licences do not establish community-checkpoint rights. | Unverified quality candidate, especially for bass. |
| [MelBand-RoFormer architecture](https://arxiv.org/abs/2310.01809) | Competitive vocals, drums and other; specialised checkpoints could complement a broad model. | Active MLX and PyTorch ecosystems exist; no runtime/checkpoint pair is selected here. | Every checkpoint needs a separate licence, hash and provenance record. | Unverified role-specific candidate. |
| [SCNet](https://github.com/starrytong/SCNet) | Official sparse-compression four-stem model with released MUSDB checkpoint. | PyTorch path; Apple runtime and memory need measurement. | Official code is MIT; record the release asset terms/hash separately. | Useful independent architecture in the bake-off. |
| [Spleeter](https://github.com/deezer/spleeter) | Two, four and five source configurations; five-source adds piano. | Older TensorFlow stack has known Apple-silicon friction. | MIT code, last formal release in 2021. | Historical speed/reproducibility control only. |
| [Open-Unmix](https://github.com/sigsep/open-unmix-pytorch) | Established four-stem reference implementation. | Generic PyTorch CPU/GPU rather than a first-class current Mac route. | MIT code; default UMXL weights are CC BY-NC-SA 4.0. | Non-commercial reference baseline, not public default. |

The active
[Music Source Separation Training](https://github.com/ZFTurbo/Music-Source-Separation-Training)
repository supports RoFormer, MDX23C, Demucs, BandIt, SCNet and other
architectures. It is a valuable bake-off framework, but its repository licence
must not be projected onto community weights.

The same rule applies to
[python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator)
and [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui):
they are useful model runners and comparison tools, not one uniformly licensed
model.

### Wide-taxonomy models

Reports of an MVSep “Mega 53 Stems” BS-RoFormer release describe roles including
lead/backing vocals, drum families, keys, piano, synth, guitars, strings,
brass and wind. It is attractive because its vocabulary resembles
Sunofriend's desired role graph, but it is not a safe default:

- this research has not established a stable primary model-card or release
  URL, exact checkpoint hash or licence;
- the release guidance expects high GPU memory;
- many output categories overlap and do not sum cleanly to the source;
- an Apple runtime has not yet been proven for the supported contract;
- each role needs its own accuracy evidence; and
- the checkpoint licence/provenance requires explicit confirmation.

Treat it as an **unverified lead**, not a runnable candidate, until those
missing facts are recorded.

### Narrow drum separation

The desired hierarchy is:

```text
finished mix -> broad drums -> kick / snare / hats / toms / cymbals / other
```

Relevant candidates include:

- the MDX23C DrumSep configuration described in the
  [Music Source Separation Training release discussion](https://github.com/ZFTurbo/Music-Source-Separation-Training/issues/1),
  which targets kick, snare, toms, hi-hat, ride and crash;
- [LarsNet](https://github.com/polimi-ispl/larsnet), which targets kick,
  snare, toms, hi-hat and cymbals from solo drum mixtures; and
- a wide-taxonomy direct separator as a comparison.

LarsNet's weights are non-commercial and its training domain is largely
synthetic acoustic kits, so electronic and AI-generated drums are a material
domain-shift risk. The original DrumSep provenance is incomplete enough that
Sunofriend must not auto-download it until the archival licence and checksum
are established.

An earlier, lower-risk improvement is to add a public composite `drums` role
and route it through Sunofriend's existing mixed-kit MIDI family classifier.
This does not produce child audio stems, but can create family-aware drum MIDI
without a second separator.

### Query-based separation

Query models are promising when a broad stem contains two bass timbres,
several keyboards, lead plus backing vocals, or miscellaneous `other` sounds.

| Candidate | Query | Strength | Current constraint |
| --- | --- | --- | --- |
| [AudioSep](https://github.com/Audio-AGI/AudioSep) | Text | Open-domain target plus broad zero-shot instrument separation; chunk inference available | Processes at 32 kHz; official path documents CUDA/CPU rather than MPS; checkpoint terms need separate verification |
| [Banquet](https://github.com/kwatcharasupat/query-bandit) | Example audio | Small stem-agnostic decoder; paper reports useful guitar, piano and long-tail instrument results | Official workflow is CUDA-centric and needs a suitable clean query example |
| [SAM Audio](https://github.com/facebookresearch/sam-audio) | Text, time span or visual prompt | Returns target plus residual and can generate/rerank several candidates; prompts could include “buzzing synth bass” or “pluck bass” | Python 3.11+, large memory footprint, CUDA recommended, gated weights and a custom SAM licence requiring review |
| [CLIPSep](https://github.com/sony/CLIPSep) | Text | Permissive research implementation for text-queried sound separation | Older general audio path; exact pretrained release terms and hash remain unverified |

These are **advanced refinement challengers**, not the first integration.
Semantic confidence can be high while note timing is damaged. A query result
must be compared against the unchanged parent and residual.

## Input-format contract

### User promise

The public promise must name tested **container-plus-codec combinations**,
not infer quality from an extension. The initial portable baseline should be:

- WAV containing integer PCM16, PCM24 or PCM32;
- AIFF containing integer PCM16, PCM24 or PCM32;
- FLAC;
- M4A containing ALAC or AAC;
- MP3; and
- Ogg containing Vorbis or Opus.

AIFC, CAF and WMA are conditional capabilities because those containers can
hold several codecs and support depends on the installed decoder. Likewise,
an `.m4a` suffix alone does not say whether the audio is lossless ALAC or
lossy AAC. The receipt must classify the stream only after `ffprobe`.

Use `ffprobe` and FFmpeg to validate the actual container, stream and codec,
not just the filename suffix. FFmpeg documents that available demuxers depend
on the build and exposes them through `-formats`; its
[format documentation](https://ffmpeg.org/ffmpeg-formats.html) is therefore a
better capability source than a hard-coded promise that “everything” works.

FFmpeg is not installed by the current newcomer bootstrap. Before import,
`source-doctor` reports the exact existing local `ffmpeg`/`ffprobe` binaries,
versions, hashes and declared capability policy without writing files.
Installation remains a separately planned and approved step; Sunofriend does
not silently install or substitute a decoder.

The importer should reject:

- DRM-protected or encrypted files;
- files without exactly one selected audio stream unless the user chooses one;
- unsupported channel layouts or corrupt/non-finite decoded audio;
- remote URLs in the local source path; and
- symbolic-link inputs in the first release; and
- video containers in the initial release, even if FFmpeg could decode their
  audio.

Video/audio extraction can be a later explicit feature with its own rights and
stream-selection UX.

Initial safety defaults reject a file larger than 2 GiB, audio longer than 30
minutes, more than eight channels, or a projected canonical asset larger than
8 GiB. Required free space includes the preserved original and chord
evidence, twice the projected decoded size, and 1 GiB of headroom. FFmpeg is
also given explicit duration and file-size output limits. Probing is bounded
to 30 seconds and decoding to the greater of 120 seconds or four times
declared duration, capped at 30 minutes. These limits may become explicit
advanced settings, but must remain recorded in the receipt and must never
expand silently.

The S1 threat model is a trusted local, single-user filesystem namespace.
Planning and execution reject collisions and detected path/symlink drift, and
publication is descriptor-anchored and no-replace. Defending against a hostile
process continually renaming ancestors while FFmpeg is actively reading and
writing would require descriptor-relative handling throughout the decoder and
is outside this local preparation boundary.

### Canonical representation

For every input:

1. preserve the original bytes unchanged;
2. compute an original SHA-256;
3. inspect with `ffprobe`;
4. decode deterministically to a canonical local PCM24 integer WAV without
   loudness normalization, because current Sunofriend readers do not all
   interpret float32 WAV correctly;
5. preserve sample rate and channel layout when the canonical contract allows;
6. compute canonical hash and audio geometry;
7. create model-specific resampled derivatives separately; and
8. record the decoder binary, version and exact arguments; and
9. create a minimal source-project manifest that preserves the original role,
   key, BPM, tuning, chord-document and filename context before legacy
   conversion discovers the canonical WAV.

Float32 can become a later canonical option only after every production,
Workbench and evaluation consumer has a tested float path.

The clock contract records the container start time, stream time base, codec
delay/priming, skip-sample metadata, decoder padding, first retained sample
and exact decoded frame count. The implementation reads bounded first and
tail packet windows because MP3 and AAC priming is not reliably present in
stream-level metadata. When importing several stems, compare their decoded
origins and lengths before claiming alignment. Equal duration alone is not
proof that MP3 or AAC files start on the same musical sample.

The canonical representation should be a processing asset, not a user-facing
claim that an MP3 became lossless. Lossy input remains lossy evidence after
decoding.

### Implemented initial receipt

```json
{
  "schema": "sunofriend.source-import.v1",
  "source_id": "sha256:...",
  "original": {
    "name": "song.m4a",
    "path": "INPUT/original/song.m4a",
    "bytes": 123456,
    "sha256": "...",
    "container": "mov,mp4,m4a",
    "codec": "alac",
    "sample_rate": 48000,
    "channels": 2
  },
  "canonical": {
    "path": "INPUT/canonical/song.wav",
    "sha256": "...",
    "sample_format": "pcm_s24le",
    "sample_width_bytes": 3,
    "sample_rate": 48000,
    "channels": 2,
    "frames": 12345678
  },
  "clock": {
    "format_start_time_seconds": 0,
    "stream_start_time_seconds": 0,
    "first_retained_source_sample": 0,
    "decoder_padding_samples": 0,
    "decoded_frame_count": 12345678
  },
  "decoder": {
    "name": "ffmpeg",
    "ffmpeg": {
      "path": "/local/path/to/ffmpeg",
      "sha256": "...",
      "version": "ffmpeg version ..."
    },
    "ffprobe": {
      "path": "/local/path/to/ffprobe",
      "sha256": "...",
      "version": "ffprobe version ..."
    },
    "arguments": ["...", "<SOURCE>", "...", "<CANONICAL>"],
    "network_protocols": ["file"],
    "normalization_filters": []
  },
  "limits": {
    "maximum_duration_seconds": 1800,
    "maximum_input_bytes": 2147483648
  },
  "normalised": false,
  "network_used": false
}
```

The one-asset implementation fixes and tests this
`sunofriend.source-import.v1` boundary, including `normalised: false`,
`network_used: false`, file-only decoder protocols, original/canonical hashes
and clock evidence. `source-import-folder` composes those per-source receipts
under `sunofriend.source-folder-import.v1`, compares available recorded
origins and atomically publishes one multi-source
`sunofriend.source-project.v1` manifest plus canonical top-level WAV stems.
The aggregate receipt records that audio was not normalized and alignment was
not corrected.

## Source-project and separation contracts

### Source part

Each source part needs:

- stable content identity;
- role and optional instrument label;
- parent source ID;
- `original` or `estimated` origin;
- `composite` or `leaf` shape;
- active/inactive status;
- audio geometry and content hash;
- provider or separator provenance;
- quality status and warnings; and
- rights category supplied by the user without pretending Sunofriend verified
  it.

Suggested rights values are `owned`, `licensed`, `authorised_private_use`,
`statutory_exception`, `unknown` and `declined_to_state`. They are a user
declaration, not legal adjudication.

### Separation run

One run should be immutable and contain:

- source and canonical hashes;
- backend package/version/commit;
- model/checkpoint ID and SHA-256;
- code licence, weight licence and known training-data note;
- requested and actual roles;
- device, runtime, settings, seed and wall time;
- every target and residual hash;
- duration, sample rate, channels, peak, RMS and silence report;
- reconstruction and leakage evidence;
- network and filesystem side effects; and
- completion/cancellation state.

An incomplete or cancelled run must never be loadable as completed output.
No model may download implicitly during inference.

### Nested refinement

Refinement creates children of a broad parent. The project must enforce:

- an active parent and any active child are mutually exclusive for final
  transcription;
- all children share the parent's clock and duration within a strict tolerance;
- the unchanged parent remains auditionable;
- residuals remain available;
- accepting children never deletes the parent; and
- a user can revert to the parent without recomputation.

### Two independent candidate axes

Separation candidates and MIDI candidates are different decisions:

```text
original source
├── separator A → bass estimate ─┬─ analytical MIDI
│                               ├─ AI MIDI
│                               └─ repaired MIDI
└── separator B → bass estimate ─┬─ analytical MIDI
                                ├─ AI MIDI
                                └─ repaired MIDI
```

The catalogue must preserve both levels of provenance and never flatten them
into one label or silently choose a separator before the existing
multi-method MIDI comparison. Source selection and MIDI selection need
separate review events. Bound the first implementation to at most five broad
separator candidates per source, two refinement levels and five MIDI
candidates per active leaf unless an explicit advanced plan raises the limit.
Regression tests must preserve blind labels, deterministic ordering, existing
review identities and legacy WAV candidate IDs.

The runtime implementation should generalise the existing `ai_runtime.py`,
`ai_cleanup.py`, Demucs worker/checkpoint-hash policy and the
`listening_master.py` pinned-executable pattern. Do not create a second model
registry or executable-discovery path that can drift from those controls.

## Quality and bake-off contract

Source-separation SDR alone does not answer Sunofriend's question. A stem can
sound pleasant but have smeared note attacks; another can sound noisy but
produce substantially more accurate MIDI.

### Test material

Use three evidence groups:

1. copyright-safe synthetic material with exact notes and clean component
   audio;
2. authorised original multitracks that can be mixed into known broad and
   narrow ground truth; and
3. private real songs for generalisation and GarageBand listening, never
   committed or uploaded.

Useful research datasets include:

- [Slakh2100](https://www.slakh.com/), which provides CC BY 4.0 synthesized
  multitracks and aligned MIDI;
- [MUSDB18-HQ](https://sigsep.github.io/datasets/musdb.html), an educational
  four-stem benchmark with per-track rights restrictions; and
- [MoisesDB](https://arxiv.org/abs/2307.15913), a two-level hierarchical
  240-track research dataset distributed under CC BY-NC-SA 4.0.

Only appropriately licensed subsets and usage profiles may enter automated
tests. MUSDB18-HQ is an academic/per-track-restricted evaluation source, not
an ordinary committed CI fixture.

### Technical gates

- Successful deterministic decode with finite samples.
- Exact or tolerance-bounded duration, clock and channel geometry.
- No unexplained clipping or silent target.
- Hashes revalidated before reuse.
- Target-plus-residual or summed-stem reconstruction error reported.
- Cancelled and partial output rejected.
- Warm-cache and fresh-process results distinguished.

Reconstruction error must not be described as separation accuracy: a model can
reconstruct the mix while allocating sounds to the wrong role.

### Separation and leakage evidence

- SI-SDR/SDR per role where ground truth exists.
- Cross-stem leakage and correlation matrix.
- Spectral holes, high-frequency loss and transient preservation.
- Silent-target false-positive rate.
- Role plausibility, such as pitched sustained energy in a drum-only output.
- Parent-versus-children reconstruction and duplicated energy.

### Downstream MIDI evidence

- Onset precision, recall and F1.
- Pitch-class, exact-pitch and octave accuracy.
- Note-duration and timing-error percentiles.
- Full-song drift and alignment.
- Drum family onset F1.
- Chroma and contour retention for bass, keys and vocals.
- Phrase recognition and human correction effort.

Compare MIDI made from:

1. the known clean source;
2. each separator estimate;
3. the unchanged full mix or broad parent where applicable; and
4. each refinement candidate.

### Product evidence

- Blind, level-matched source/stem/MIDI listening.
- Usefulness of the final balanced Sunofriend interpretation.
- GarageBand import and A/B checks.
- Installation success on supported Mac classes.
- Model size, wall time, peak unified memory and energy/thermal behaviour.
- Licence and provenance completeness.

A model can win one role and lose another. Promotion remains role-specific.

### Pre-registered acceptance

Before running hidden evaluation, S3 must commit an
`acceptance-thresholds.v1` artifact. At minimum:

- use at least 12 songs across acoustic, electronic/AI-generated and mixed
  production, with at least four songs in each group;
- require at least eight ground-truth examples for every role proposed for
  promotion;
- name the comparison baseline and exact required deltas for onset F1,
  exact-pitch/octave accuracy, median and 95th-percentile timing error;
- set a catastrophic per-song regression limit, not only a median target;
- set wall-time and peak-memory ceilings for every declared supported Mac,
  including one 16 GiB Apple-silicon class;
- require a zero-network offline inference test after explicit model
  installation; and
- define the blind level-matched human non-inferiority and preference rule.

No threshold may be filled in after hidden results are seen. Missing sample
coverage, missing licence/hash evidence, a blank threshold or a failed gate
means **no promotion**. Development data may be used to calibrate the numbers,
but the frozen artifact and hidden run must remain separate.

## Recommended initial bake-off

### Broad candidates

1. A maintained Demucs/HTDemucs Apple runtime and exact four-stem checkpoint.
2. One fixed four-stem BS-RoFormer runtime/checkpoint pair.
3. One fixed MelBand-RoFormer role-specific pair.
4. SCNet as an independent architecture if it runs within the supported Mac
   memory envelope.
5. Spleeter or Open-Unmix only as historical controls.

### Narrow candidates

1. Existing mixed-kit MIDI classifier on a composite drums stem.
2. MDX23C DrumSep only after licence and provenance recovery.
3. LarsNet in an explicitly non-commercial research profile.
4. Direct wide-taxonomy separation as a capable-hardware challenger.
5. Query-based target/residual models for compound bass, keys, vocals and
   `other`, never as automatic defaults in the first release.

### Decision rule

No single average score selects the winner. A default must:

- satisfy technical and licence gates;
- satisfy the frozen role-specific MIDI improvement and non-regression
  thresholds;
- avoid a material regression in timing/alignment;
- fit the supported Mac runtime envelope;
- produce an understandable residual and lineage; and
- pass level-matched human listening for the MIDI interpretation.

If no candidate meets the rule, Sunofriend should keep provider guidance and
existing-stem input rather than ship a misleading local separator.

## TUI and Workbench experience

### First screen

The beginner route should ask:

```text
What do you have?

[ A finished song file ]
[ A folder of stems or multitracks ]
[ Nothing yet — try the demo ]
```

For a finished file, show before any installation:

- local or cloud processing;
- model name and licence profile;
- expected model download;
- estimated time and disk/memory needs;
- planned broad roles;
- whether optional refinement will follow; and
- exact network and filesystem changes.

### Studio review

Studio should show:

- source, broad stems and refined children as one lineage tree;
- synchronized solo/mute and level-matched audition;
- target and residual together;
- activity, leakage and reconstruction warnings;
- active-leaf selection;
- separator provenance and licence;
- downstream MIDI comparison; and
- a reversible “use broad parent” choice.

The Workbench should never silently choose children because they are narrower.

### Simple mode

One-action finished-song processing comes last. It should use only accepted,
whitelisted backend/checkpoint pairs and publish:

```text
RUN/
├── INPUT/
│   ├── original/
│   ├── canonical/
│   └── source-import.json
├── STEMS/
│   ├── broad/
│   ├── refined/
│   └── separation-runs/
├── CONVERSION/
└── AUTOMATIC-SONG/
    ├── MIDI/
    ├── AUDIO/balanced-midi-song-interpretation.wav
    └── sunofriend-automatic-midi-and-wav.zip
```

The output must be labelled automatic, estimated and unreviewed.

## Privacy, security and licensing

- Local remains the default. No automatic command uploads audio.
- Remote providers are links or explicit adapters, never silent fallbacks.
- Model installation is a separate, approved action.
- Inference cannot download weights.
- Only checksum-whitelisted weights can enter an automatic profile.
- Pickled checkpoints require a trusted-source policy and ideally a converted
  safe tensor format.
- Code, runtime, weight and dataset licences are recorded separately.
- Gated, non-commercial and custom-licensed weights are never bundled into the
  Apache-2.0 package.
- Original audio, stems and private review stay ignored by Git.
- Logs and path-free public receipts must not expose titles or user paths.
- Affiliate attribution is separate from technical metrics and selection.
- A future compensated provider link must retain an ordinary alternative, be
  labelled beside the link, carry a clear disclosure before engagement and
  use `rel="sponsored noreferrer"` on the public site.

## Phased delivery plan

This is a parallel **Source Access programme**. It does not renumber the
existing transcription phases.

### S0 — Research and honest documentation

Status: **repository research complete; public-site delivery tracked
separately**

- Publish stem definitions, provider choices and affiliate policy.
- Audit current format and role assumptions.
- Record the model landscape and define the initial bake-off.
- Publish a plain-language `/stems/` page on `sunofriend.com`, with a stable
  `/glossary/` alias or anchor and agent-readable links/metadata.
- Keep the skill and website statement “Sunofriend does not yet separate a
  full mix” until implementation is genuinely accepted.

### S1 — Canonical multi-format import and minimal manifest

Status: **accepted**

- [x] Add a central tested suffix/container/codec capability policy.
- [x] Add the explicit read-only FFmpeg capability doctor.
- [x] Implement bounded `ffprobe` validation and deterministic FFmpeg decode.
- [x] Preserve original and canonical hashes, geometry and clock metadata.
- [x] Write minimal source-import and source-project manifests preserving
  role, key, BPM, tuning, chord-document and original filename context.
- [x] Keep planning read-only and execution local, fresh-output-only,
  no-network and no-install.
- [x] Reject mixed audio/video containers, record lossy packet-edge timing,
  hard-bound decoder output and publish without replacing a raced destination.
- [x] Orchestrate several synchronized source parts and compare decoded
  origins before claiming alignment.
- [x] Make existing WAV-stem behaviour a regression golden across every
  production surface.
- [x] Integrate prepared projects with TUI and Workbench catalogue/timeline
  paths without changing legacy candidate identities.

Likely modules:

- `source_import.py`
- `audio_formats.py`
- `source_receipt.py`
- `source_project.py`
- `source_folder_import.py`
- `project_audio_inputs.py`

### S2 — Source graph and composite roles

- Extend the minimal manifest with versioned parent/child lineage.
- Centralise role inference.
- Add composite `drums`, `vocals` and `other` semantics.
- Route composite drums through the existing family-aware MIDI classifier.
- Enforce parent/child active-leaf exclusivity.

Likely modules:

- `source_roles.py`
- `source_lineage.py`

### S3 — Separation bake-off harness

- Add a backend-neutral `SeparationBackend` contract.
- Generalise the existing AI runtime/checkpoint registry and isolate heavy
  runtimes in a separate worker environment.
- Require explicit checkpoint installation, hashes and licences.
- Prove that inference makes no network request after installation.
- Generate immutable broad candidate runs, residuals and quality reports.
- Measure downstream MIDI and Mac resource behaviour.

Likely modules:

- `separation_contract.py`
- `separation.py`
- `ai_separation_worker.py`
- `separation_quality.py`

### S4 — Experimental broad separation in Studio

- Promote only accepted broad backend/checkpoint pairs.
- Add TUI `Finished song` planning and Studio operation.
- Add synchronized lineage review and reversible leaf activation.
- Keep Simple finished-song mode disabled.

### S5 — Hierarchical refinement

- Bake off drum sub-stem candidates.
- Evaluate lead/backing vocal and compound keys/bass refinements.
- Add query target/residual experiments only behind explicit advanced controls.
- Retain unchanged parents and measure compounding artefacts.

### S6 — One-action finished-song route

- Enable Simple mode only after cross-song, downstream MIDI and human
  acceptance gates pass.
- Produce stems, MIDI, interpretation WAV and ZIP with complete receipts.
- Update the Sunofriend skill and website capability declarations.

### S7 — Hosted and provider integrations

- Consider a thin authenticated control plane and queued workers, not a
  request-duration serverless fiction.
- Add explicit cloud consent, deletion, retention, rights declaration,
  metering and payment design.
- Add provider APIs only when privacy, terms and failure semantics are
  documented.

## Tests required by implementation

### Import

- Every promised format with tiny generated fixtures.
- Container/codec combinations and conditional capability reporting.
- Missing, mismatched and unapproved FFmpeg binaries.
- Extension/codec mismatch.
- corrupt, encrypted, multi-stream and unsupported input.
- size, duration, channel, disk, timeout, expansion and symlink limits.
- sample-rate, channel, duration, start-time, priming and padding preservation.
- cross-file decoded-origin and alignment checks.
- no normalization and immutable original.
- deterministic receipt and hash validation.
- PCM24 compatibility in every production and Workbench reader.

### Source project

- broad and leaf roles;
- minimal imported metadata survives canonical filenames;
- stable IDs and parent/child cycles rejected;
- parent/child mutual exclusion;
- rollback to parent;
- no duplicate MIDI from active parent plus child; and
- legacy WAV folder produces the same production plan.

### Separation

- backend protocol and worker failure;
- explicit model-missing result with no download;
- installed-model offline inference with network access denied;
- cancellation and partial-run cleanup;
- cache key includes source, model, checkpoint and settings;
- duration/alignment/residual checks;
- non-finite, silent and clipped outputs;
- licence/profile enforcement; and
- no private paths in shareable receipts.

### Product

- TUI plan before side effects;
- Studio source/broad/refined lineage;
- level-matched audition;
- Simple disabled before acceptance;
- Workbench format/timeline consistency; and
- GarageBand pack excludes inactive parents.

## Open questions to answer with evidence

1. Does HTDemucs on Apple silicon beat a fixed BS-RoFormer checkpoint for
   downstream bass MIDI, not merely isolated-audio quality?
2. Does a dedicated drum separator improve family onset F1 over the existing
   mixed-kit MIDI classifier?
3. Is direct wide-taxonomy separation better than broad-then-refine for
   electronic and AI-generated music?
4. Can query separation split two timbres without damaging shared pitch and
   timing?
5. Which lossless/lossy formats materially change MIDI accuracy?
6. What Mac memory/runtime floor is realistic for a non-technical user?
7. Can a fully permissive checkpoint profile meet the quality bar, or must
   some higher-quality profiles remain opt-in/non-commercial?
8. Which provider outputs produce the best downstream MIDI per role?
9. How should a user describe private-use or licensed processing without
   Sunofriend making a legal determination?
10. When does a second separation pass do more harm than using a composite
    stem directly?

## Primary sources

- [Demucs](https://github.com/facebookresearch/demucs)
- [BS-RoFormer paper](https://arxiv.org/abs/2309.02612)
- [MelBand-RoFormer paper](https://arxiv.org/abs/2310.01809)
- [SCNet](https://github.com/starrytong/SCNet)
- [Spleeter](https://github.com/deezer/spleeter)
- [Open-Unmix](https://github.com/sigsep/open-unmix-pytorch)
- [Music Source Separation Training](https://github.com/ZFTurbo/Music-Source-Separation-Training)
- [AudioSep](https://github.com/Audio-AGI/AudioSep)
- [Banquet](https://github.com/kwatcharasupat/query-bandit)
- [SAM Audio](https://github.com/facebookresearch/sam-audio)
- [MoisesDB paper](https://arxiv.org/abs/2307.15913)
- [MUSDB18-HQ](https://sigsep.github.io/datasets/musdb.html)
- [Slakh2100](https://www.slakh.com/)
- [FFmpeg format documentation](https://ffmpeg.org/ffmpeg-formats.html)
- [ASA/CAP affiliate guidance](https://www.asa.org.uk/advice-online/affiliate-marketing.html)
- [FTC endorsement guidance](https://www.ftc.gov/business-guidance/resources/ftcs-endorsement-guides-what-people-are-asking)
