# Stem-separation developer preview

Sunofriend is developing an optional local step that can turn one authorised
finished mix into estimated stems before the existing stems-to-MIDI workflow.
The research is public so that musicians and developers can inspect the method,
challenge its assumptions and influence what is built next.

This is a **developer preview**, not a public separator. The current public
product still begins with already-separated authorised audio parts. Private
audio, model files and listening notes are not uploaded or redistributed.

## Overall development goals

The long-term goal is one understandable local journey:

1. supply music you own or are authorised to process;
2. obtain useful estimated stems when original multitracks are unavailable;
3. compare several analytical and optional local-AI MIDI interpretations;
4. hear a balanced MIDI-derived song interpretation;
5. edit the MIDI and suggested instruments in GarageBand or another DAW; and
6. feed explicit user observations back into better defaults, documentation
   and future experiments.

Sunofriend should make a useful musical interpretation, not pretend to recover
the lost studio session. Human listening remains the authority for musical
quality. Automated checks cover identities, geometry, timing, accounting and
reproducibility.

## What is new

The private local separation surface now has three deliberately separate
layers:

- [`_separation_private_local_contract.py`](../src/sunofriend/_separation_private_local_contract.py)
  owns status vocabulary, immutable permissions, profile configuration and
  backend argument construction;
- [`_separation_private_local_workflow.py`](../src/sunofriend/_separation_private_local_workflow.py)
  coordinates start, review and finish without redefining policy; and
- [`private-separation-local.py`](../scripts/private-separation-local.py)
  is the thin developer command adapter.

The separation contract keeps every public-product permission false. Moving
policy out of orchestration makes the boundary easier to review, test and
extend without hiding a product decision inside audio-processing code.

The public research surface adds:

- a plain-language [status page](https://sunofriend.com/research/separation/);
- machine-readable status in
  [`agent-capabilities.json`](https://sunofriend.com/agent-capabilities.json);
- agent discovery in [`llms.txt`](https://sunofriend.com/llms.txt); and
- the existing first-song and compatibility feedback routes.

## How the feature was developed

Each increment follows the same evidence loop:

1. **State one narrow question.** Examples include whether a whole song can be
   processed in bounded chunks or whether a join remains useful in context.
2. **Seal the inputs.** Authorised source audio, runtime components and result
   files receive exact identities. Source files are not silently modified.
3. **Run one bounded experiment.** New results remain inactive and cannot
   become a product default merely because execution succeeded.
4. **Check machine evidence.** Geometry, finite audio, reconstruction
   accounting, boundaries, timing and reproducibility are checked separately
   from musical judgement.
5. **Listen explicitly.** A local review names the exact question and exact
   result. Clean, poor and inconclusive outcomes are all preserved.
6. **Promote nothing automatically.** Human feedback can motivate another
   experiment, documentation repair or product proposal, but it cannot select
   a model, merge a vocal line or enable a public route by itself.

This approach came directly from practical listening. Some measurable joins
were hard to hear in musical context, several candidates were useful for
different vocal lines, and a technically valid result was not always the most
musically helpful one. The code therefore keeps evidence, candidate identity
and human decisions distinct.

## What you can use today

### Try the released public workflow

The copyright-safe demo exercises the normal automatic MIDI, listening WAV and
ZIP path without personal music:

```bash
sunofriend demo --out-dir FRESH
```

With an authorised folder of existing stems:

```bash
sunofriend create PROJECT --out-dir FRESH
```

Both routes produce automatic, unreviewed results. Start with the balanced WAV,
then open the individual MIDI and starter instrument guidance.

### Inspect the developer boundary

From a prepared development checkout, the doctor is read-only. It does not
load the separator, process audio or write a song result:

```bash
PYTHONPATH=src ./.venv/bin/python \
  scripts/private-separation-local.py --repository-root "$PWD" doctor
```

On a normal public checkout it may report that the private evaluation profile
is unavailable. That is an expected boundary, not an invitation to download a
checkpoint. The complete owner-only workflow remains documented in
[`PRIVATE_SEPARATION_DEVELOPMENT.md`](PRIVATE_SEPARATION_DEVELOPMENT.md#approachable-local-start-command)
for code review and reproducibility.

The focused contract tests are:

```bash
./.venv/bin/python -m pytest \
  tests/test_separation_private_local_workflow.py \
  tests/test_separation_private_render_review_equivalence.py \
  tests/test_separation_reviewed_output_import_assessment.py \
  tests/test_separation_reviewed_output_import.py -q
```

## Give feedback that can be acted on

Use the existing routes rather than attaching music:

- [first-song report](https://github.com/N9-Developer-Empowerment/sunofriend/issues/new?template=beginner-first-song.yml)
  for setup clarity, finding the result and whether the interpretation helped;
- [compatibility and developer report](https://github.com/N9-Developer-Empowerment/sunofriend/issues/new?template=daw-ai-compatibility.yml)
  for another Mac, operating system, coding agent, DAW, stem provider or exact
  failing step.

Useful feedback includes:

- what you tried and what you expected;
- operating system, hardware, agent and DAW;
- whether the problem was installation, separation, MIDI, instrumentation,
  mixing, export or explanation;
- the smallest reproducible command or synthetic/demo case; and
- what sounded useful, unhelpful or impossible to judge.

Do not attach private stems, vocals, unreleased songs, model files or private
review exports. Feedback is evidence for the next bounded change. It is not an
automatic vote that changes a model or musical default.

## What must happen before public separation

A public separator still needs:

- a beginner-safe start, progress, recovery and removal journey;
- useful roles beyond broad vocals and instrumental;
- song-disjoint evaluation across more music, machines and listeners;
- redistributable dependency and checkpoint terms;
- bounded resource behaviour and safe failure recovery; and
- an explicit product decision backed by both tests and human listening.

Until those gates are met, the research remains inspectable and discussable,
while actual separation stays private and developer-controlled.
