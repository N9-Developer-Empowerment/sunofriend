# Sunofriend

Sunofriend converts separated music stems and vocal performances into editable,
timing-aware MIDI for GarageBand and other DAWs. It can evaluate stem-to-MIDI
accuracy, publish conservative or reconstructed variants, change MIDI key and
tempo, preserve or straighten groove, and store reusable Clip v1 parts.
It can also inventory installed GarageBand/Audio Unit instruments, create
sound-based audition shortlists, and extract authorised isolated stem notes as
self-contained SF2 sample instruments with GarageBand-selectable Apple
AUSampler preset wrappers, with WAV/SFZ sources and pitch-mapping evidence
retained.
Instrument Bundle v1 keeps the MIDI, authorised carried sound, local factory
and General MIDI match evidence, source reference, and A/B previews together.
An arrangement-aware usability gate demotes incomplete source samplers to
optional texture layers. Explicit DAW choices can be hash-pinned with
`instrument-feedback`, combined into a deterministic local advisory profile,
and shown in later bundles without automatic patch selection or match
reordering.
Vocal melody extraction adds pYIN/Basic Pitch consensus, conservative repeated
phrase repair, an optional hummed guide, and a local visual correction report
whose reviewed JSON can be converted back into tuned MIDI.
An optional isolated AI runtime can also test pinned local learned cleanup on
short stem excerpts. Its target/residual evidence is reconstructable and never
replaces the normal MIDI path without an explicit listening decision.
Reviewed event-cluster evidence can then produce non-destructive multi-role
MIDI A/Bs, including a separately transcribed residual layer for overlapping
parts, without claiming automatic instrument recognition.
A completed role review can be resolved into an exact hash-verified copy of
the user-selected MIDI; component usefulness never silently overrides the
overall arrangement decision.
That fixed monophonic MIDI can then drive a level-matched timbre review that
compares complete, extracted-sample and deterministic harmonic-plus-noise
sounds while checking every note for functional audibility.
The loopback-only Workbench presents existing source/MIDI alternatives in a
normal browser, saves append-only solo/full-mix choices, renders missing MIDI
through a verified local neutral-preview cache, auditions only explicit
main/optional parts together, and packages unchanged selected MIDI plus a
clearly labelled proxy arrangement for GarageBand. Selected candidates with
the same candidate-origin source receive a diagnostic doubled-line warning
when exact-pitch attacks substantially overlap. AI candidates use the verified
run source hash; non-AI MIDI falls back to the review-stem source hash. The
arrangement remains audible, no MIDI is deduplicated, and GarageBand handoff
waits for explicit full-mix confirmation only when a selected same-origin pair
reaches that substantial-overlap threshold.
The exact private review can also be archived atomically from the CLI without
starting a server. The Workbench loads no remote scripts and has no upload or
submission endpoint. Each completed exact pack now links to a local guided
acceptance page: eight tutorial screens explain the result-space, timing,
instrument and privacy contracts; a 10-question one-at-a-time quiz requires
10/10 before the GarageBand and usability checks unlock. The reviewed export
can be verified against the exact downloaded ZIP with
`garageband-pack-resolve`; resolution recomputes the quiz, verifies every pack
member and records evidence without changing MIDI, selections, the pack basket
or any feedback state. Completed AI runs add path-free
model/config, label, boundary and safety diagnostics; severe or zero-note
results remain diagnostic-only. `sunofriend ai-matrix` compares controlled
immutable lanes without changing raw candidates or MIDI. Its M4 contract
compares distinct one-role passes only when source, excerpt and BPM match and
reports possible role collapse as diagnostic overlap. Fresh MuScriptor runs
also preserve model-load, inclusive-transcription, first-note, chunk and
process-memory evidence outside the deterministic candidate JSON. The
inclusive timer covers MuScriptor preprocessing, condition construction and
decoding. `sunofriend ai-benchmark` verifies two or more sequential,
non-overlapping completed runs with the same runtime identity and source-frame-
derived actual processed duration, then writes a
path-free timing and exact-output repeatability report without launching a
model; fresh-process repeats are not mislabelled as warm-model runs.
`sunofriend ai-transcribe-session` provides the separate bounded exact-repeat
test: one parent-owned worker loads one existing local MuScriptor checkpoint,
executes 2–20 serial copies of one fixed source/roles/excerpt/request over an
inherited Unix socket pair, then exits. It is a diagnostic benchmark harness,
not a multi-song service or content cache. Startup/model load is reported
separately; request 1 has a resident model but no prior transcription and is
not labelled warm or cold, while requests 2 and later are reused-model warm.
`sunofriend ai-session-benchmark` verifies the private path-bearing session
tree and writes a path-free report. Optional fresh-process comparison requires
at least two exact comparable `ai-transcribe` runs; ordinary `ai-benchmark`
rejects session repetitions. A path-free report can still contain identifying
content hashes and runtime details. The session commands download nothing,
change no checkpoint licence, mutate no MIDI and promote no candidate.
On the verified 15-second small-CPU golden, three session requests and two
fresh controls reproduced the same 107-note MIDI byte for byte; warm pipeline
median was `3.681 s` versus `5.193 s` fresh (observed ratio `0.709`). This is
end-to-end evidence under an uncontrolled OS file cache, not a causal claim or
a general hardware benchmark.
For exact unchanged MuScriptor requests,
`ai-transcribe --application-cache-dir PRIVATE_DIR` enables a separate opt-in
private content cache. A miss performs one fresh inference and stores only the
verified raw model candidate plus its original performance evidence. A
verified hit creates a fresh immutable run, starts no worker, loads no model,
executes no inference, and rebuilds current Sunofriend quality, expression and
MIDI artifacts. A missing cache root is created owner-only; an existing root
must grant no group or other permissions, and it must remain outside every run
output tree. `ai-cache-benchmark` verifies one `miss-stored` run and at least
two `verified-hit` runs without launching a model. Copied origin timing
is never current hit inference timing. The report omits paths and
caller-supplied run IDs, although hashes, timestamps and runtime identity can
still identify private material or a machine. This cache is neither
resident-model reuse nor the Workbench neutral-preview cache; the
operating-system file cache remains uncontrolled. Cache evidence cannot
promote a musical result.
The private 15-second Lidl M2 validation produced one `6.295 s` miss and a
`1.078 s` median across two verified no-worker/no-inference hits, with all 107
raw and derived note controls identical. Treat that as a local end-to-end
observation, not a general performance or accuracy claim.
`ai-label-split` can
then create an exact raw-event label partition plus deterministic requested and
complement MIDI auditions while retaining a byte-identical full-candidate
control. MIDI quantisation/normalisation effects are reported explicitly; this
is not source separation and never promotes a result automatically. Explicit
Workbench catalogs may add a focused
listening question and checklist without turning either into a score or choice.

`hybrid-report` provides a separate lead-melody-only S0/M1/M3 phrase
diagnostic over existing specialist, full-mix-label and conditioned-stem MIDI.
It reports path-free agreement and disagreement evidence but creates no MIDI,
selects no winner and runs no model. The v1 evidence can verify the supplied
S0/M3 comparison source and rendered candidate payloads; it explicitly cannot
prove that M1's pinned full mix was derived from the same song or verify M3's
unsupplied original pre-projection MIDI.

Sunofriend complements AI music generators, stem separators, and DAWs rather
than replacing them. The current supported production workflow is macOS-first,
using Python 3.9–3.11, FluidSynth for offline preview, and CoreMIDI for optional
live playback.

See the [full documentation, worked examples, and agent-skill setup](https://github.com/N9-Developer-Empowerment/sunofriend#readme).

After a package release, install the full tool with:

```bash
brew install fluid-synth
uv tool install --python 3.11 'sunofriend[all]'
sunofriend doctor --require convert
```

The repository also contains a portable Agent Skills workflow for Codex and
Claude Code. Agent discovery links are installed by cloning or linking the
repository; they are not written by the Python wheel. The skill orchestrates
the packaged CLI without uploading audio or replacing the deterministic
conversion engine.

Sunofriend is distributed under the Apache License 2.0.
