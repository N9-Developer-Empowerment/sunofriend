# Refining grouped other in Studio

Sunofriend's public core-four preview ends at `vocals`, `drums`, `bass` and
grouped `other`. The next bounded research step is now registered as
`other-refinement-v1`, but it is deliberately **not executable**.

The contract refines one exact `other.wav` into exactly two persisted parts:

```text
core-four other
├── one requested target: guitar or keys
└── other residual
```

The target and residual must share the parent's stereo 44.1 kHz PCM24 clock and
must reconstruct that parent within two PCM24 least-significant bits. Exact
reconstruction is accounting evidence; it does not prove that the target is
clean, complete or musically useful.

## What is implemented

- immutable binding to the verified `scnet-large-musdb-release-v1` core-four
  parent profile, separation report, source-graph node, PCM24 audio hash and
  clock;
- one target per run, currently `guitar` or `keys`;
- an exact target-plus-residual output contract;
- Studio-only, non-executable registration reported by
  `sunofriend-separate profiles --json`;
- explicit false permissions for model execution, checkpoint download,
  dependency installation, public execution, source activation, MIDI
  activation, candidate selection and model promotion;
- the existing source-graph antichain rule, which prevents a parent and its
  descendant stems from being active together; and
- deterministic model-free synthetic PCM24 evidence for both target choices.

The synthetic proof can be generated into a fresh local directory:

```bash
.venv/bin/python scripts/run-other-refinement-synthetic.py \
  --target guitar \
  --out "/absolute/path/to/fresh-other-refinement-fixture"
```

Use `--target keys` for the second contract variant. The command creates only
mathematical oscillator audio, a path-free immutable plan and a verified result.
It downloads nothing, installs nothing, opens no checkpoint and runs no model.

## What is not implemented

There is no public or Studio execution button, no selected backend, no approved
checkpoint, no installer and no automatic import into the source graph. The
registration status is `blocked`, with target release tier
`studio_challenger`. It therefore cannot be selected by the finished-mix
`separate` command.

The first useful backend does not have to solve every instrument. A bounded
candidate should answer one question: can it extract either guitar or keys
from the exact grouped-other parent while retaining a transparent residual?

## Candidate qualification without another doom loop

For the first backend candidate:

1. audit and pin one exact runtime, source revision, checkpoint and terms
   record without installing it;
2. present a separate setup plan and request explicit approval before any
   dependency or checkpoint download;
3. run the deterministic fixture and one bounded authorised-song experiment
   under network denial;
4. reject only objective failures such as missing roles, clock mismatch,
   non-finite audio, failed residual accounting, source mutation, network use,
   crash or declared-machine OOM;
5. expose target, residual and unchanged parent as separate Studio candidates;
6. ask whether each output is useful, incomplete, bleeding or artefact-heavy,
   and whether downstream MIDI improved; and
7. preserve mixed or poor feedback as a limitation instead of disabling the
   public core-four profile or starting unlimited tuning.

One baseline configuration and one remediation cycle are enough before either
retaining the candidate for Studio feedback or switching to a different
backend. Studio must not choose a winner from display order, reconstruction or
automated metrics.

## Source and MIDI activation

Refinement output begins inactive. After explicit listening, a source-graph
revision may activate either:

- the unchanged grouped-other parent; or
- the target and residual children together.

It must never activate the parent alongside either child. MIDI/Create follows
only the active frontier, so the same musical evidence cannot be transcribed
twice by accidentally including both the grouped parent and its refinement.

## Later scope

After one target/refinement lane is useful, the same contract can be extended
carefully to another one-target choice or to drum-family refinement. Recursive
blind splitting of every residual is not the default: each new level needs an
explicit musical target, exact parent binding, transparent residual and a
separate listening decision.
