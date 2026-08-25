# Remix research handover

Prepared: 19 August 2026

Branch: `codex/windows-setup-notes`

Purpose: give a new thread enough verified context to continue the Sunofriend
remix programme without repeating completed setup, implementation, generation,
separation, transcription or listening experiments.

Private source audio, generated candidates, separated stems, listening WAVs and
private review material are intentionally outside the repository. Use the
existing path-free hashes and receipts to identify them; do not ask for them to
be committed.

## Read these first

1. [`SEMANTIC_MUSICAL_STATE_AND_TRAINING_PLAN.md`](SEMANTIC_MUSICAL_STATE_AND_TRAINING_PLAN.md)
   is the current forward plan.
2. [`REFERENCE_CONDITIONED_SONG_GENERATION_EVALUATION_PLAN.md`](REFERENCE_CONDITIONED_SONG_GENERATION_EVALUATION_PLAN.md)
   contains the detailed empirical record and successive gates.
3. [`REFERENCE_CONDITIONED_SONG_GENERATION_SPEC.md`](REFERENCE_CONDITIONED_SONG_GENERATION_SPEC.md)
   defines the product and source-identity contract.
4. [`SONG_GENERATION_PROVIDERS.md`](SONG_GENERATION_PROVIDERS.md) records
   provider capabilities and truthful limitations.
5. [`GETTING_STARTED.md`](GETTING_STARTED.md) records the exact Windows and
   Demucs compatibility findings.

The current conclusion is not “find better prompts.” ACE-Step has been tested
through creative-reference generation, native cover/remix, extracted-vocal
completion and a deliberately bounded Turbo check. All failed the musical goal
for the current song. The next research object is a structured, time-aligned
Musical State representing accompaniment identity.

## Goal and decisive owner clarification

The goal is to transform one owner-authorised rough song using replacement
lyrics and a style direction while preserving an owner-recognisable musical
relationship to the source. At least one result must be enjoyable and useful
enough to continue through stems, MIDI, GarageBand arrangement, human vocal
recording and comping.

The rough vocal is deliberately a guide and is not tuneful enough to define the
composition's intended melody. It may provide words, approximate phrase
placement, range, energy and delivery. The primary identity is in the
accompaniment:

1. grouped `other`: instrumental motifs, harmonic motion and octave-spanning
   texture;
2. bass: recognisable harmonic/rhythmic movement;
3. drums: beat, groove and section energy, while their cheerful affect may be
   intentionally changed; and
4. section form and energy across these roles.

Do not revert to `rough vocal F0 = intended melody` unless the owner supplies a
different reviewed vocal that is explicitly authoritative.

## Canonical private fixture

- Owner-made and authorised for private use.
- Canonical mix: 237.769-second stereo 44.1 kHz 24-bit PCM WAV.
- SHA-256:
  `aa0cdb7ba15cf45d3a016fa5726d22db565743d2872769fb60d768bf025edd43`.
- Draft metadata: 120 BPM, A Major.
- Unreviewed automatic analysis: approximately the 123 BPM family; key result
  was ambiguous between low-confidence C# minor and strongest-major A Major.
- Owner decision: BPM and key need not be preserved. Enjoyment, source identity
  and downstream usefulness are more important.
- Target lyrics and style material are private and remain outside the repo.
- No private source audio was sent to a cloud model during these experiments.

The owner also supplied a private Suno remix as the positive quality control:
254.064 seconds, stereo 44.1 kHz 24-bit PCM. The owner confirmed that its vocal
is in tune and follows the lyrics. Exact Suno model, seed and settings are not
available, so this is a human-approved benchmark, not a reproducible provider
result.

## Local environments already established

### Sunofriend Windows environment

- Windows 11 x64.
- MSI Vector GP68HX 13VH.
- Intel Core i9-13950HX.
- 64 GB system RAM.
- NVIDIA GeForce RTX 4080 Laptop GPU, 11.99 GB usable VRAM.
- NVIDIA driver 610.88.
- Sunofriend uv-managed CPython 3.11 environment.
- `doctor --require convert`, `doctor --require preview`, FluidSynth smoke and
  `source-doctor` passed.
- Remove TensorFlow 2.14 packages from the isolated Windows Sunofriend
  environment after installing `.[all]`; retain ONNX Runtime for Basic Pitch.
- POSIX locking was replaced on this branch with `msvcrt.locking` on Windows.
  Thirty applicable source-lineage/project-input tests passed; two symlink
  tests could not run because the Windows account lacks symlink privilege.
- Native Windows remains a research route, not a generally supported release.

### ACE-Step environment

- Separate repository/environment at sibling `ace-step-1.5/`.
- ACE-Step source commit used by Gate 1: `14c0211`.
- `acestep-v15-base` and `acestep-v15-turbo` available.
- `acestep-5Hz-lm-0.6B` is the supported planner on this 11.99 GB tier.
- The 1.7B planner did not start generation because ACE exposed only the 0.6B
  planner at the detected VRAM tier.
- CPU offload was used for full songs.
- vLLM/Triton could not create a cache artifact under the OneDrive checkout;
  ACE's PyTorch LM fallback loaded and completed.
- A non-private ten-second 48 kHz stereo smoke generation passed.

### Demucs experiment environment

- Separate Windows CUDA environment; do not merge it into Sunofriend or ACE.
- PyTorch/torchaudio 2.7.1 CUDA 12.8.
- Demucs 4.0.1.
- SoundFile 0.13.1.
- `htdemucs_ft` was used.
- Under OneDrive, install with `uv pip --link-mode copy`; hardlink mode failed
  with Windows cloud-file error 396.
- Demucs 4.0.1 required integer `--segment 7`, not `7.8`.

## Implementation already completed

Do not rebuild these contracts or adapters from scratch:

- `sunofriend song-generate`, read-only by default with explicit execution and
  rights confirmation.
- Hash-bound generation request and durable success/failure receipts.
- Two candidate outputs per request.
- Independent backend-neutral reference/style controls where the backend
  genuinely supports them.
- ACE creative-reference mode: `text2music` plus multipart
  `reference_audio`, `audio_cover_strength` and Base guidance mapping.
- ACE native-remix mode: `--generation-mode remix` maps to `cover` plus
  multipart `src_audio`; source duration is locked and unsupported BPM/key/
  meter/duration overrides are rejected.
- Requested-checkpoint integrity: missing or mismatched returned `dit_model`
  evidence fails candidate admission.
- Compatibility with old and OpenAI-style ACE model-inventory response shapes.
- Provider capability registry that distinguishes registered, evaluated and
  unavailable operations and contains no secrets.
- `source_identity.py`, `vocal-melody` and `source-scaffold` evidence paths.
- Role-specific accompaniment MIDI work, hybrid low tracking and the current
  multi-register review bank.
- Documentation, skill/interface capability descriptions and Windows website
  material for these boundaries.

Important current limitations:

- No immutable song-project version graph yet.
- No public section repaint/stem replacement workflow yet.
- No service lifecycle command; generation expects an already running API.
- ACE track tasks remain outside the public command surface.
- No backend beyond ACE is registered for the complete reference-conditioned
  operation.

## Completed generation experiments

### A. ACE creative-reference Base pairs

Mode: `text2music` with multipart `reference_audio`.

#### Pair A1: inferred metadata

- Reference strength `0.35`.
- Style strength `0.75`.
- BPM/key/duration omitted.
- ACE reported 70 BPM, E minor, 4/4 and 232 seconds.
- Two candidates completed in 121.187 seconds.
- Request:
  `965a910e542170b9208a39aa928d65885ba26e32964a49d9bac85adff1b52de1`.
- Receipt:
  `8d658a5e550b249ae43f16822e9a2b3adefd21c70b6fdde0cebd886ce150bb2d`.

#### Pair A2: explicit source metadata

- Reference strength `0.35`.
- Style strength `0.75`.
- 120 BPM, A Major, 4/4; duration omitted.
- ACE reported 120 BPM, A Major, 4/4 and 199 seconds.
- Two candidates completed in 110.984 seconds.
- Request:
  `61bfc378abc4ec225be7598dc46f6b8600084d004eead8702e22f063d798427d`.
- Receipt:
  `81c2713a2b428d993f73665d425958d362208630bde90bb4752ba9ee53dd3dd7`.

All four outputs were distinct stereo 48 kHz float WAVs. The owner preferred
inferred-metadata candidate 02 but found all four too dominated by the rough
vocal and wanted stronger, more distinct drums, bass and synth. The backend
also sang the `120 BPM` lyric-sheet header because the full annotated document
had been passed verbatim.

Do not repeat these two pairs or treat exact text transport as proof that lyric
and production annotations were interpreted correctly.

#### Pair A3: accompaniment-priority follow-up

- Reference strength `0.15`.
- Style strength `0.8`.
- No BPM/key/duration lock.
- Production details moved from lyrics into the caption; concise lyric tags
  retained.
- Two valid 210-second stereo 48 kHz float Base outputs.
- Owner rejected both because the generated vocals were out of tune.

The first attempt at this pair silently used ACE's lazily initialised Turbo
default instead of the requested Base model. Those outputs are retained only as
invalid diagnostic evidence. The adapter now prevents this substitution.

Do not repeat the same prompt/strength pair. Its failure has been reviewed.

### B. ACE native Base cover/remix

- Native `cover` with `src_audio`.
- Clean replacement lyrics.
- Reference strength `0.2`.
- Style strength `0.8`.
- Source-locked duration; no claimed independent BPM/key/meter/duration lock.
- Two technically valid 237.56-second stereo 48 kHz float outputs.
- Request:
  `3d5799c637fcc44392faed91852aba8e5a68549e0e28f082cdb75594a2d55205`.
- Receipt:
  `b7b83696b338610377b23c1b608162655e43bf6ef0eeea2f44ca7400079417b9`.
- Candidate hash prefixes: `5d7dcbd8`, `6a2acc74`.

Owner decision: both voices were in tune but flat, monotonic and talk-sung.
The accompaniment was unmusical; neither result was enjoyable or creative.

Do not run another Base cover-strength sweep on this fixture. The method has a
quality failure, not an untested-strength problem.

### C. ACE Base extracted-vocal completion

- Base `extract` created a vocal-role track from the draft.
- Base `complete` used that track as context and requested drums, bass, guitar
  and synth.
- No target lyrics; this was a preservation/arrangement gate.
- Two 237.56-second outputs completed in 56.313 seconds.
- Candidate 01 waveform correlation with vocal source: `0.970`.
- Candidate 02 waveform correlation with vocal source: `-0.001`.

Owner decision: candidate 01 retained the unusable out-of-tune draft vocal;
candidate 02 was an unrelated instrumental with no recognisable melody,
likeness or musical connection.

Do not repeat Base `complete` or try `lego` on this fixture without a new,
owner-recognised scaffold. The problem was the conditioning evidence.

### D. Final bounded ACE Turbo native-remix check

- `acestep-v15-turbo`.
- `acestep-5Hz-lm-0.6B`.
- Eight Turbo steps.
- Native reference strength `0.2`.
- Requested style strength `0.8`, but Turbo does not use classifier-free
  guidance, so the `guidance_scale` mapping is ineffective.
- Two technically valid 237.76-second outputs in 41.219 seconds.
- Candidate hash prefixes: `13cc46cf`, `8014f1e3`.

Owner decision: both vocals were in tune and the backings were more musical
than Base, but neither preserved an audible connection to the original melody
or rhythm. Better surface quality did not make them remixes.

ACE-Step is therefore executable but rejected as the full-song remix provider
for this fixture. Do not run more seeds, prompt variants or strength sweeps as
the next step.

## Completed source-identity experiments

### Rejected vocal-derived scaffold

An ACE `extract` result was treated as a vocal input and `vocal-melody` emitted
379 notes:

- 219 shorter than 200 ms;
- 128 shorter than 120 ms; and
- a reported 87.1% within 50 cents.

The percentage was circular: it compared MIDI with the same derived F0 contour
used to construct the MIDI. It was not independent melody accuracy.

Owner decision: the melody-only and melody-plus-accent review WAVs sounded like
random notes without form, melody or rhythm. Both were rejected.

Do not use these controls as generation input, a target melody or evidence of
progress. Do not optimise note filtering around this failed premise.

### Accepted vocal-suppression gate

The separate Demucs environment processed the exact 47-65 second source window
(18 seconds):

- float32 `vocals` and `no_vocals` at 44.1 kHz;
- sum-to-source waveform correlation `0.993192`; and
- reconstruction SNR `18.573 dB`.

Those measurements establish technical preservation only. The owner listening
decision passed: `no_vocals.wav` retained recognisable instrumental music and
sufficiently removed the scratch singing.

### Accepted role hierarchy

A four-stem view of the same window established:

- grouped `other.wav`: primary source-identity carrier;
- `bass.wav`: secondary recognisable identity;
- `drums.wav`: timing/groove evidence, not melody; and
- drum affect: cheerful/upbeat and explicitly allowed to change for the target
  lyrics.

This hierarchy is the current source of truth for the fixture.

### Role-specific MIDI auditions

First repair-mode outputs:

- grouped-other polyphonic keys: 82 notes;
- grouped-other accompaniment: 55 notes;
- grouped-other upper melody hypothesis: 27 notes;
- bass: 20 notes; and
- drums: 55 events.

Owner decision:

- all three grouped-other renders were unrecognisable;
- bass MIDI was usefully recognisable; and
- the missing grouped-other identity seemed lower in pitch with higher
  additions, suggesting an octave-spanning texture rather than one top melody.

Do not repeat the upper-voice-only extraction or present drums as melody.

### Current unresolved multi-register gate

Sunofriend now publishes competing hypotheses rather than silently selecting
the highest voice:

- exact lowest-onset line: 64 notes;
- upper 27-note contour shifted down one octave: inferred;
- upper 27-note contour shifted down two octaves: inferred;
- exact low-plus-upper union: 75 notes;
- separate hybrid low tracker: 29 notes in MIDI 44-52; and
- cross-stem control combining the hybrid low line with accepted bass MIDI.

Neutral review WAVs are private. At the time of handover, owner recognition of
these new variants has not been recorded. This is the only unfinished listening
gate in the existing accompaniment-MIDI branch.

However, the new semantic plan does not require forcing one of these hypotheses
to win. If none is recognisable, record that result and proceed to temporal
representation probing rather than generating more hand-designed register
variants indefinitely.

## Providers already assessed conceptually

- **ACE-Step 1.5:** only registered current provider for the implemented local
  reference and native-remix routes; executable but rejected for this fixture.
- **TREBLO Melodia v3:** prompt/lyrics and continuation capabilities evaluated;
  not registered because its documented interface does not provide the agreed
  general reference-conditioned operation or independent reference control.
- **Downloadable MiniMax Music 3:** text/lyrics/description generation only in
  the inspected release; no documented general reference-audio input,
  repaint, reference-strength control or training path. Do not call it a remix
  backend.
- **Hosted MiniMax `music-cover` / `music-cover-free`:** accepts reference
  audio and replacement style/lyrics but is a separate API family and lacks a
  documented independent reference-strength control. It remains an opt-in
  BYO-key cloud candidate, not a completed test.

Do not silently discard the source audio to make a provider appear compatible.
Cloud use requires explicit upload, terms, privacy and cost acknowledgement.

## Relevant branch history

The remix programme is recorded by these commits, in order:

- `30d8c86` Document Windows setup and song generation goal
- `dcb1fa6` Add reference-conditioned song generation contract
- `7e554fe` Add BYO music provider capability registry
- `da6e855` Document iterative song generation evaluation
- `0ceb391` Run local ACE-Step song generation pilot
- `f2e8121` Refine accompaniment experiment and verify ACE model
- `c14eac0` Admit Suno vocal quality benchmark
- `fb91fe7` Add native ACE-Step remix mode
- `a1eaa34` Record ACE remix rejection and track-level gate
- `619c14e` Record ACE completion rejection and Turbo review gate
- `f046f37` Make source identity a hard remix requirement
- `039e979` Add source identity scaffold gate
- `ac80e70` Switch remix evaluation to accompaniment-first
- `208a6ec` Preserve accompaniment identity on Windows
- `49bff17` Add multi-register accompaniment review bank
- `d0d84cd` Add semantic musical state training plan

Inspect these commits before assuming a requested capability is absent or an
experiment has not been tried.

## Testing and evidence boundary

The branch contains automated coverage for:

- generation request/receipt schemas and validation;
- CLI read-only and execution gates;
- provider registration and truthful capabilities;
- old/new ACE inventory compatibility;
- multipart audio transport;
- native remix input/control restrictions;
- requested checkpoint identity and substitution rejection;
- source-identity/scaffold schema and provenance;
- Windows source-lineage locking and input handling;
- transcription/register variants and conversion modes;
- interface/website capability consistency; and
- rendered website HTML.

Historical real-run evidence is retained in the evaluation document and
private receipts. The complete repository suite has not been declared
Windows-clean: the project remains macOS-oriented and contains POSIX/private
modules outside the bounded Windows work. Do not turn the thirty passing
Windows lineage/input tests or successful local research operations into a
general Windows-support claim.

Before changing code, run focused tests for the touched modules. Do not rerun
private audio or model experiments merely to prove that the committed tests
exist.

## Decisions that must remain fixed unless new evidence changes them

1. Source identity is a hard gate at non-zero reference strength.
2. Lyrics and genre similarity cannot substitute for musical connection.
3. Technical audio validity, pitch accuracy and model completion are not
   musical success.
4. The scratch vocal is not authoritative melody evidence for this fixture.
5. Bass evidence remains separate from polyphonic grouped-other identity.
6. Drums carry rhythm/groove, not melody, and their affect may change.
7. Automatic chroma/onset/F0 scores do not override owner listening.
8. ACE full-song generation is stopped for this fixture pending materially new
   conditioning evidence or architecture.
9. Private audio and provider secrets remain outside the repository.
10. A style LoRA alone does not solve composition/source conditioning.

## Exact next step for the new thread

Follow Phase 0 and Phase 1 of
[`SEMANTIC_MUSICAL_STATE_AND_TRAINING_PLAN.md`](SEMANTIC_MUSICAL_STATE_AND_TRAINING_PLAN.md):

1. Define `musical-state.v0` and an identity-anchor benchmark schema using the
   existing provenance conventions.
2. Create a no-model, path-free benchmark builder around the accepted
   accompaniment hierarchy and owner-marked anchors.
3. Instrument the separate ACE service to extract aligned VAE,
   text-conditioning and selected temporal DiT features from short windows.
4. Compare controlled variants and independent frozen music representations.
5. Train only small probes/adapters after the frozen representation report.
6. Purchase bounded cloud compute only after a reduced local training run has
   passed its data, loss, resume and held-out evaluation gates.

If the owner first supplies the pending multi-register listening decision,
record it immutably. It may refine the benchmark, but it should not restart the
rejected generation or vocal-F0 experiments.

## One-paragraph thread handoff

Sunofriend has a working, provenance-safe Windows ACE-Step generation adapter
and has already tested Base creative-reference generation, Base native cover,
Base extracted-vocal completion and Turbo native cover on the authorised
237.769-second fixture. All routes were rejected: Base had tuning, phrasing and
arrangement failures; Turbo sounded better but erased source identity. A
vocal-derived 379-note scaffold was also rejected because the scratch vocal is
not the intended melody. Demucs vocal suppression on the 47-65 second excerpt
passed owner listening and established grouped other as the main identity
carrier, bass as secondary and drums as transformable groove evidence. Bass
MIDI passed; three initial grouped-other MIDI views failed; a multi-register
bank is awaiting review. Do not generate more ACE candidates or optimise vocal
F0. Build `musical-state.v0`, the owner-anchored benchmark and an ACE/frozen-
encoder representation laboratory, then train the smallest adapter that proves
composition identity on song-disjoint evidence.
