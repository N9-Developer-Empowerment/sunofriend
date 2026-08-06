# Refining grouped other in Studio

Sunofriend's public core-four preview ends at `vocals`, `drums`, `bass` and
grouped `other`. The next bounded research step is available as the opt-in
Studio challenger `other-refinement-v1`.

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
- Studio-only, executable registration reported by
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

## First pinned challenger

The first backend candidate is now pinned as
`demucs-mlx-htdemucs-6s-other-refinement-v1`. It uses the Apple-native,
PyTorch-free `demucs-mlx==1.4.4` runtime and the exact MLX Community
`htdemucs_6s` checkpoint at revision
`d4519e24ddc2dd4a11d56a193092433d852c3961`.

The profile is now a `studio_challenger`; it does not replace either public
finished-mix route. Inspect the no-write setup plan with:

```bash
scripts/setup-separation-other-refinement-demucs-mlx-macos.sh --plan
```

The exact gated installation command and the permissions it does and does not
grant are documented in [Six-source MLX Studio-challenger audit](OTHER_REFINEMENT_DEMUCS_MLX_AUDIT.md).

The model role `guitar` maps directly to the experimental guitar target. The
contract's `keys` target is explicitly a `piano` proxy: it does not claim to
separate synthesizers, organs or all keyboard sounds. Upstream warns that the
piano estimate has substantial bleed and artefacts.

Static inspection also found the same `"39/5"` segment string involved in the
earlier MLX failure. The only allowed remediation is an exact in-memory
`Fraction(39, 5)` normalization after verifying the source config, with no
artifact mutation, first-run conversion or named/network model resolution.

That single remediation passed. The installed worker then passed a
network-denied synthetic model canary and both advertised target mappings on
one authorised 234-second SCNet parent. Guitar completed in 9.94 seconds and
keys in 9.22 seconds; both used about 3.49 GB peak MLX memory and reconstructed
the parent at zero PCM24 LSB. The first verified machine remains a 36 GB M3
Max; 16 GiB and other Apple-silicon classes are accessible but unverified.
Both first-song targets were low-energy, which is a published musical
limitation rather than an admission failure.

## Run the installed Studio challenger

Use the complete core-four output directory, not a loose `other.wav`, so the
command can bind the exact SCNet report, rights receipt, audio hash and clock:

```bash
.venv/bin/sunofriend-separate refine-other \
  "/absolute/path/to/core-four-separation" \
  --target guitar \
  --out "/absolute/path/to/fresh-guitar-candidate"
```

Planning is read-only. Add `--execute --confirm-rights` after reviewing it.
Use `--target keys` for the disclosed piano proxy. The result contains the
unchanged grouped parent, one requested target, the exact residual, technical
JSON and a local listening page. It selects no winner, mutates no source graph,
creates no MIDI and uploads nothing.

The first useful backend does not have to solve every instrument. A bounded
candidate should answer one question: can it extract either guitar or keys
from the exact grouped-other parent while retaining a transparent residual?

## Candidate qualification without another doom loop

The completed first-backend qualification used this bounded policy:

1. inspect the pinned setup plan and obtain explicit approval before any
   dependency or checkpoint download;
2. prove the one allowed fraction-normalized loader under network denial;
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
