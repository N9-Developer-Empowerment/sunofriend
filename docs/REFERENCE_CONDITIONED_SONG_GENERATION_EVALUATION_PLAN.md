# Empirical reference-conditioned song evaluation

Status: private intake and local runtime gates complete; two diagnostic
ACE-Step pairs retained; awaiting owner listening before advancement

Plan agreed: 17 August 2026

Evidence updated: 17 August 2026

## Current empirical evidence

The owner supplied one owner-made, privately authorised input pack through
Google Drive. The audio and extracted lyric/style files remain outside this
repository; no private asset was sent to a cloud model. The intake records a
237.769-second stereo, 44.1 kHz, 24-bit PCM WAV with SHA-256
`aa0cdb7ba15cf45d3a016fa5726d22db565743d2872769fb60d768bf025edd43`.
The supplied target is 120 BPM in A Major. Sunofriend's unreviewed automatic
analysis estimated the 123 BPM tempo family with medium confidence; its key
selection was low-confidence C# minor, while A Major was the strongest major
candidate and won more analysis windows. The explicit owner metadata therefore
remains authoritative for the controlled run.

Gate 1 passed locally on Windows 11 with an RTX 4080 Laptop GPU (12 GB VRAM),
64 GB system RAM, NVIDIA driver 610.88, ACE-Step source commit `14c0211`, the
`acestep-v15-base` DiT and `acestep-5Hz-lm-0.6B`. A non-private 10-second smoke
request completed. For full songs, CPU offload was enabled. vLLM/Triton failed
to create a temporary cache artifact under the OneDrive checkout, after which
ACE-Step's automatic PyTorch LM fallback loaded and completed normally.

The first private submission exposed two current API compatibility differences:
the model inventory now uses an OpenAI-style list, and `/release_task` rejects
client-supplied absolute audio paths. Sunofriend now accepts both current and
older inventory shapes and streams the reference as multipart audio. The
failed absolute-path attempt is retained as a failure receipt rather than
erased.

Two diagnostic pairs are retained:

| Pair | Fixed controls | ACE-Step reported metadata | Independent unreviewed analysis | Result evidence |
| --- | --- | --- | --- | --- |
| Inferred metadata | reference `0.35`; style `0.75`; metadata omitted | 70 BPM, E minor, 4/4, model-selected 232 s | candidates: 136 BPM/C# minor (medium/low) and 144 BPM/E minor (low/low); the detected double-time tempo family is broadly compatible with 70 BPM | request `965a910e542170b9208a39aa928d65885ba26e32964a49d9bac85adff1b52de1`, receipt `8d658a5e550b249ae43f16822e9a2b3adefd21c70b6fdde0cebd886ce150bb2d`; elapsed 121.187 s |
| Explicit target metadata | reference `0.35`; style `0.75`; 120 BPM, A Major, 4/4; duration omitted | 120 BPM, A Major, 4/4, model-selected 199 s | both candidates: 117 BPM; both A minor, with high key confidence; musician/DAW review is required to distinguish relative-major/minor behaviour from analysis error | request `61bfc378abc4ec225be7598dc46f6b8600084d004eead8702e22f063d798427d`, receipt `81c2713a2b428d993f73665d425958d362208630bde90bb4752ba9ee53dd3dd7`; elapsed 110.984 s |

All four outputs are stereo, 48 kHz, 32-bit float WAVs with distinct hashes.
The explicit parameters moved the measured tempo family close to the requested
120 BPM, but backend metadata alone does not prove the rendered key or musical
quality. These runs used bring-up settings rather than the formal Gate 2 centre
point and must not be presented as a provider win. The next gate is the owner's
blind-enough listening decision on enjoyment, lyric behaviour, reference
influence, style adherence and downstream usefulness. No additional candidates,
strength sweep, stem separation or MIDI reconstruction should begin until that
decision is recorded.

## Decision to make

Determine which local, self-hosted or bring-your-own-key method produces the
most useful starting material for further Sunofriend production from one
owner-made song, its sample initial vocals and music, and a separate target
annotated lyric sheet.

"Most useful" does not necessarily mean the most polished first render. A
candidate that separates cleanly, yields editable MIDI, supports bounded
revision and makes it practical to replace every generated instrument and
vocal may be more valuable than a superficially impressive but uneditable mix.

The comparison is empirical. Model descriptions and demonstrations decide
which methods are eligible to test; only retained outputs and the owner's
listening/production decisions determine which method advances.

## Standing scope and privacy

- Every track the owner supplies to this private project is assumed to be
  authorised for private personal use. The assumption is recorded once at
  project level and is not re-asked for every local operation.
- Source audio, stems, lyrics, generated candidates, listening notes that reveal
  private material and DAW projects remain outside the public repository.
- Repository records use path-free asset identifiers, hashes, model/settings
  evidence and redacted decisions. A hash proves identity, not permission to
  publish the underlying asset.
- Local processing needs no additional rights prompt. Every cloud/API method
  requires an explicit upload, provider-terms and possible-cost acknowledgement
  before the first transfer. Declining that acknowledgement simply marks the
  cloud method `not_run`.
- This plan does not itself download a model, start inference, upload audio,
  spend credits or authorise publication.

## Private input pack

The owner will provide:

1. one canonical reference mix containing the owner's sample initial vocals
   and music;
2. the target lyrics as a separate UTF-8 text file with lightweight section and
   production annotations;
3. a descriptive target style brief; and
4. short production notes describing what is already working, what may change
   and what would make a result worth continuing.

Optional inputs are original stems, a dry vocal, known BPM/key, an existing MIDI
arrangement and a GarageBand bounce. They are useful evidence but not required:
automatic inference remains the normal product behaviour.

Before inference, Sunofriend should create a private intake record containing
the input hashes, audio format/duration, lyric hash, the standing personal-use
scope and a redacted project identifier. Canonicalisation must preserve the
original files rather than replacing them.

## Method families

The first comparison may include the following capability-gated methods. A
method that cannot consume an input must say so rather than silently ignore it.

1. **ACE-Step native cover/remix:** source audio plus target caption and lyrics,
   using native reference/cover strength.
2. **ACE-Step analysis bridge:** automatically analyse the reference, review a
   structured abstract description, then generate from description and lyrics
   without claiming native reference conditioning.
3. **ACE-Step iterative operations:** repaint a selected time range, extend a
   retained candidate, or use supported track-level completion after a useful
   whole-song result exists.
4. **MiniMax Music 3 description route:** feed target lyrics and a structured
   caption derived from the reference. The released checkpoint is treated as
   description-conditioned unless a later verified runtime exposes genuine
   reference audio.
5. **MiniMax hosted music-cover:** evaluate the separate API cover model with
   reference audio, style and replacement lyrics, subject to explicit cloud
   acknowledgement. Do not describe it as the open Music 3 checkpoint or invent
   an undocumented reference-strength control.
6. **Other prompt/lyrics providers:** TREBLO or another BYO-key service may be
   tested through the explicit analysis bridge. Continuation is evaluated as a
   different operation from general reference-conditioned generation.
7. **Stem- or MIDI-informed hybrids:** where a backend supports them, compare a
   full mix, instrumental/stem context or reviewed MIDI/analysis as the creative
   starting point. Each variant is a distinct method with its own receipt.

MiniMax Music 3 modification is a separate research track. A style LoRA may
personalise an existing input path, but does not by itself add missing
reference-audio conditioning. Genuine remix research would need a reference
encoder, a learned conditioning/strength path and paired training examples;
it is not a prerequisite for the first product experiment.

See [`SONG_GENERATION_PROVIDERS.md`](SONG_GENERATION_PROVIDERS.md) for the
provider truthfulness and BYO-key boundary.

## Successive experiment gates

The experiment uses successive gates so weak or ineligible methods do not
consume an exhaustive parameter search.

### Gate 0 — intake and analysis only

- Preserve and hash the private inputs.
- Validate audio and annotated-lyric structure.
- Produce automatic tempo, key, section, instrumentation and vocal-trait
  observations with confidence/evidence where available.
- Let the owner correct a clearly wrong analysis without forcing manual control
  of every inferred trait.
- Freeze the first comparison brief before listening to generated output.

No model generation occurs at this gate.

### Gate 1 — runtime smoke qualification

- Prove each local runtime can load and complete one bounded non-private or
  synthetic smoke request on the current RTX 4080 Laptop GPU.
- Record model/checkpoint/runtime versions, peak GPU/system memory, duration,
  failures and any quantisation/offload settings.
- Do not expose the private song to a runtime that has not passed its smoke
  check.

### Gate 2 — centre-point full-song comparison

- Every eligible method receives the same canonical reference evidence, exact
  target lyrics and style brief to the extent it truthfully supports them.
- Start both public strength controls at the neutral centre (`0.5`). Record the
  exact backend mapping; do not pretend unlike scales are equivalent.
- Produce exactly two complete candidates per method with fixed, recorded seeds
  when available.
- Archive outputs locally immediately and audition them under randomised
  candidate labels so provider reputation does not dominate the first review.
- Advance only methods with at least one candidate worth further production.

### Gate 3 — independent strength calibration

For the shortlisted native-reference methods, vary one public control at a time
around the centre while holding lyrics, the other control and all possible
settings fixed. Begin with low/centre/high values (`0.25`, `0.5`, `0.75`) and
stop early if the control is ineffective, reverses meaning or damages quality.

The question is whether increasing reference strength produces a useful,
generalised increase in reference influence without direct copying, and whether
increasing style-description strength produces a useful increase in prompt
adherence. A numeric slider is not accepted merely because a backend parameter
has the same range.

### Gate 4 — iterative revision

Choose one promising candidate and one clearly described weak region. Compare:

- a whole-song branch with revised prompt/strengths;
- a section/time-range repaint while the remainder is locked, if supported;
- an extension, shortening or replacement intro/outro where useful; and
- a stem/arrangement operation if the backend can honour it.

Retain the original parent and every child. Score improvement, collateral
damage, transition continuity and the truthfulness of locks. This gate decides
which revision unit should become Sunofriend's next first-class feature.

### Gate 5 — downstream Sunofriend utility

For the best candidate from each surviving route:

1. separate it into the available stem roles;
2. infer tempo/key/grid and transcribe useful parts to MIDI;
3. compare the MIDI and stems with the owner's existing arrangement;
4. replace selected generated instruments with MIDI/human-rendered parts in
   GarageBand;
5. treat generated vocals as a guide while recording human takes;
6. perform vocal comping only after the remix and instrumental arrangement are
   settled; and
7. audit whether any generated audio remains in the exported master.

The downstream result, not generator prestige, selects the preferred method.

## Listening and production rubric

The owner scores each retained candidate from 0 (unusable) to 5 (excellent),
with a short reason, on:

- immediate enjoyment and emotional response;
- lyric accuracy, intelligibility and annotation/section behaviour;
- useful abstract influence from the reference;
- novelty and absence of concerning direct copying;
- adherence to the written style brief;
- arrangement and full-song coherence;
- vocal range, energy, register, identity traits and replaceability;
- mix/stem separability and timing/grid stability;
- MIDI transcription and editing usefulness; and
- expected effort to finish with human/MIDI instruments and comped vocals.

Automatic measures support rather than replace the owner's judgement: duration,
audio validity, loudness/clipping, lyric alignment when available, tempo/grid
stability, stem reconstruction error, resource use and generation time.

A method advances from Gate 2 when at least one of its two candidates scores at
least 3 for both enjoyment and expected downstream usefulness and raises no
copying or technical-integrity concern. The threshold is a triage rule, not a
claim of scientific model ranking.

## Experiment discipline and receipts

- Fix settings before each gate. A change made after listening creates a new
  experiment ID rather than rewriting the earlier comparison.
- Keep failed and rejected attempts in the ledger; do not report only the best
  seed.
- Record exact prompts, translated annotations, strength mappings, seeds,
  model/checkpoint/runtime versions, hashes, timings and errors.
- Distinguish native audio conditioning, source continuation and an analysis
  bridge in every UI label and receipt.
- Generate no more candidates than the current gate requires. Expand only after
  a recorded advance decision.
- A model/runtime update invalidates direct comparison unless the new version is
  recorded as a separate method.

## Stop and replan conditions

Stop the affected route, retain evidence and replan when:

- a backend would ignore the reference, supplied lyrics or a requested lock;
- the required cloud acknowledgement has not been given;
- a local runtime cannot complete its smoke test within safe memory/thermal
  bounds;
- outputs repeatedly contain corrupted audio, serious lyric failure or
  concerningly direct reuse;
- a nominal strength control has no observable or monotonic useful effect; or
- a provider/model/version changes materially during the comparison.

Stopping one route does not block useful work on the others.

## Completion criteria

The empirical programme succeeds when:

1. at least two technically different methods have produced retained evidence,
   or every alternative has a truthful recorded ineligibility reason;
2. at least one method produces a complete candidate the owner wants to finish;
3. the effect and limitations of both public strength controls are documented;
4. at least one iterative revision improves a chosen candidate without losing
   its parent;
5. the selected song can proceed through stems and useful MIDI into GarageBand;
6. human vocal recording and comping occur after the arrangement; and
7. the export record truthfully states whether generated audio remains.

The outcome updates the product contract and provider registry. It does not
automatically promote a backend for every song, because musical usefulness may
remain song- and task-dependent.

## Handoff when the private song arrives

When the owner supplies the files, the next turn should:

1. identify the reference mix and annotated lyric file without copying either
   into the repository;
2. ask only for any genuinely missing style brief or production note;
3. create and show the Gate 0 private intake/analysis plan;
4. inspect current local model/runtime readiness without installing, downloading
   or executing a generator implicitly;
5. present the exact Gate 1 smoke order and any cloud acknowledgements separately;
   and
6. begin the smallest approved local gate, retaining evidence before expanding
   to another method.

Do not ask the owner to repeat the personal-use authorisation for each file or
local run. Do ask before a new model download/install, private-audio upload,
paid API use or materially larger execution scope.
