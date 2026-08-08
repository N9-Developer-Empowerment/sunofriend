# Guitar and keyboard/synth query-challenger plan

The first fixed-role `htdemucs_6s` Studio challenger passed its objective
offline and reconstruction gates but failed musically on the fixed five-song
review corpus. No reviewed case demonstrated useful guitar extraction. The
only nominally useful piano-proxy output was near-silence on a song without
piano, and the one reviewed piano-like instrument was missed.

That result remains accessible as evidence. It is not promoted, selected for
MIDI or described as working guitar or keyboard separation. Negative feedback
does not disable the public vocals/drums/bass/grouped-other profile.

## Change the question, not the review threshold

`piano` is too narrow to stand for modern keyboard parts. The next experiment
uses two explicit target families:

- **guitar**: acoustic, clean electric and distorted electric guitar; and
- **keyboard_synth**: electric piano, organ, synth pad and synth lead.

Acoustic piano can remain a later control. It is not required for a useful
`keyboard_synth` result. These experimental labels do not become downstream
source or MIDI roles automatically.

## First candidate: Banquet

The first read-only candidate is
[Banquet](https://github.com/kwatcharasupat/query-bandit), a music-specific,
query-conditioned separator. Its published setup-C class vocabulary includes
the guitar, electric-piano, organ, synth-pad and synth-lead classes above. The
official repository reports 24.9 million trainable parameters, supports a
bring-your-own 10-second audio query and exposes a CPU inference flag.

Pinned public evidence:

| Evidence | Identity |
| --- | --- |
| Source revision | `79ed5bb75e5c3a40cd319d9d990cee913fc65c26` |
| Source terms | MIT |
| Checkpoint record | Zenodo DOI `10.5281/zenodo.13694558` |
| Candidate file | `ev-pre-aug.ckpt` |
| Published size | 645,470,187 bytes |
| Published MD5 | `4dfb91d6d27c2dfd4992a15070915541` |
| Observed SHA-256 | `657295888781e62ef50593002720d2edb3858b9e5bbfabf0c54f715a0da4b9e2` |
| Checkpoint terms | CC BY-NC-SA 4.0 |
| Training dataset | MoisesDB, CC BY-NC-SA 4.0 |

The approved evidence-only download matched the published byte count and MD5.
A network-denied, non-deserializing inspection found a 3,491-member PyTorch ZIP
and parsed its 452,701-byte protocol-2 pickle metadata stream. Its four GLOBAL
references were limited to `OrderedDict`, Torch float/double storage and the
standard tensor rebuild helper; no application model class was observed. The
inspection did not read tensor-storage payloads, import a dependency or
construct a model. Later bounded gates established the exact runtime and the
restricted loading result described below. The candidate is still not
registered or executable and has no inference authority.

## Runtime audit: a second checkpoint is required

The exact pinned source does not publish a dependency file or lock. Its
top-level `train.py` imports the training, data, metrics and augmentation stack
even for inference, then calls Lightning's unrestricted
`load_from_checkpoint`. Static checkpoint metadata identifies Lightning
`2.1.3`, but that does not make the upstream loader acceptable.

Banquet also constructs
`hear21passt.get_basic_model(mode="embed_only", arch="openmic")`. The pinned
`hear21passt==0.0.26` implementation resolves another model through its download
cache and loads it with an unrestricted `torch.load`. The required release
artifact is:

| PaSST evidence | Identity |
| --- | --- |
| Package | `hear21passt==0.0.26` |
| Package revision | `5f1cce6a54b88faf0abad82ed428355e7931213a` |
| Package wheel SHA-256 | `a3a7377604c6d829369111ab26a86fc5dd40154ec611b8fa5819ecaa6b252550` |
| PaSST release | `v0.0.5`, revision `d7049e78e84ba38173ffd779479d1c9ec7d1c116` |
| Required file | `openmic-passt-s-f128-10sec-p16-s10-ap.85.pt` |
| GitHub release size | 341,546,630 bytes |
| Observed SHA-256 | `dc229428753176e8be0373d25887116fc15b490af86f671cecf9ed76a0f287da` |
| PaSST code/release evidence | Apache-2.0 |
| OpenMIC-2018 training data | CC BY 4.0 |

No maintainer email is required for this local evidence stage. The public
package metadata, source license, source-linked release and OpenMIC terms are
sufficient provisional evidence unless a later static audit contradicts them.
The Banquet checkpoint's CC BY-NC-SA boundary still makes the combined route
local noncommercial research only.

Sunofriend will not run either upstream loader. The proposed adapter must
construct PaSST with `pretrained=False`, load both explicit local checkpoints
with `torch.load(weights_only=True, map_location="cpu")`, verify state-dict keys
and tensor shapes and dtypes before strict loading, and deny network access for import,
construction, loading and inference. Lightning, TorchMetrics, pandas,
TorchAudioMentations and OmegaConf are excluded from the inference adapter.

The NonCommercial term is an actual boundary, not something a user approval
can erase. This candidate may be evaluated only as local noncommercial
research unless separate permission changes that conclusion. It cannot become
a hosted conversion service, redistributed checkpoint or commercial default
through this experiment.

## Query boundary

Banquet requires a ten-second query example. The first experiment freezes two
song-disjoint, copyright-safe queries before inference: one guitar-family query
and one keyboard/synth-family query. Provider-derived Suno and Moises estimates
remain comparison cues and are not fed to the model as queries.

One fixed query per family prevents a post-feedback search for a favourable
prompt or example. If either query is objectively malformed, one remediation
cycle may replace it before the full corpus. Poor musical output does not
permit an unbounded query hunt.

## Output contract

Each run binds the exact SCNet grouped-`other` parent and persists:

1. one requested query-conditioned target; and
2. the exact residual after that target.

The two persisted files must share the parent clock and reconstruct it within
two PCM24 least-significant bits. Reconstruction proves accounting, not
instrument accuracy. The parent and its children remain mutually exclusive,
and neither output enters MIDI without a later human choice.

## Bounded evaluation

Use one model configuration, two frozen queries and ten 15-second cases:

- retain only the existing reviewed guitar windows that have credible
  instrument-present evidence;
- freeze new keyboard/synth windows using broad keyboard, organ and synth cues
  before inference;
- keep the five authorised songs song-disjoint from the query examples;
- show provider estimates only as independently generated comparisons; and
- collect the same usefulness, bleed, missing-content, artefact, timing and
  downstream-MIDI fields without choosing a winner.

There is one configuration and at most one objective remediation cycle. When
the objective gates pass, the profile may remain available in Studio even if
musical reports are poor. It is promoted only after accumulated listening
evidence shows that it actually extracts target content.

## Objective gates

- exact source, checkpoint and runtime identities;
- checkpoint SHA-256, weights-only static inspection and exact state-contract
  verification before strict model loading (**passed**);
- hash-locked dependencies;
- network-denied model construction (**passed**) and inference (**pending a
  separate approval**);
- finite stereo 44.1 kHz samples on the parent clock;
- target-plus-residual reconstruction within two PCM24 LSBs;
- declared timeout and memory ceilings on the first supported Mac; and
- no upload, source mutation, automatic model/query choice or MIDI activation.

## Inspect the current no-effects plan

```bash
.venv/bin/python \
  scripts/plan-separation-other-refinement-query-challenger.py

.venv/bin/python \
  scripts/plan-separation-other-refinement-query-runtime.py
```

The command prints a deterministic, hash-bound plan. It performs no network
request, reads no audio and installs nothing. It records the completed private
checkpoint-evidence step without reading the cached checkpoint.

The separately approved PaSST evidence step completed on 2026-08-08. The exact
341,546,630-byte release artifact has SHA-256
`dc229428753176e8be0373d25887116fc15b490af86f671cecf9ed76a0f287da`.
Its ZIP metadata and 4,917 pickle opcodes were inspected under network denial;
the checkpoint was not deserialized and tensor storage payloads were not read.
The retained evidence document has SHA-256
`990348267a373e2fe62c2fc87a13914411d7fe763b160568c87127a315f58362`.
The completed command was:

```bash
scripts/setup-separation-other-refinement-query-runtime-macos.sh \
  --passt-evidence-only \
  --accept-passt-terms \
  --accept-passt-checkpoint-use
```

Both required model-artifact identities are now complete. The challenger is
still blocked, unregistered and non-executable.

The separately approved dependency-evidence step also completed on 2026-08-08:

- target: CPython 3.12, macOS 11 or later, arm64;
- direct pins: Torch/TorchAudio `2.2.2`, TorchVision `0.17.2`,
  `hear21passt 0.0.26`, `timm 0.9.12` and NumPy `1.26.4`;
- resolved closure: 28 wheels and 99,354,620 wheel bytes;
- maximum staged evidence: 159,772,783 bytes under the approved 1 GiB cap;
- static evidence SHA-256:
  `d5976d21a919648dbe6a371f1ce1f7d19adee75296f31739f4c662c040dd5329`;
- committed lock SHA-256:
  `28249f5d6ab80d4b72a5f256ac435f3a2d150b1baa30d751754af44049c33b92`;
  and
- wheel metadata and licence-member hashes showed permissive, MPL/LGPL and
  disclosed GPL-with-runtime-exception material, with no contradiction for
  this local noncommercial research route.

The completed command was:

```bash
scripts/setup-separation-other-refinement-query-runtime-macos.sh \
  --runtime-wheel-evidence-only \
  --accept-runtime-wheel-evidence
```

The wheels were downloaded but not installed during that evidence-only step.
ZIP metadata inspection ran under network denial and imported no downloaded
package. The exact public lock is
`separation-other-refinement-query-runtime-requirements.txt`.

The separately approved isolated installation and import gate completed on
2026-08-08:

```bash
scripts/setup-separation-other-refinement-query-runtime-macos.sh \
  --install-runtime \
  --accept-runtime-install-and-import
```

The command created a fresh CPython 3.12.10/macOS-arm64 virtual environment,
installed the exact 28 packages from the approved local wheel cache with
`--no-index --require-hashes`, and ran package imports under operating-system
network denial and Python isolated mode. `pip check` reported no broken
requirements. The eight relevant imports were NumPy, Torch, TorchAudio,
TorchVision, timm, `hear21passt`, `hear21passt.models.passt` and
`hear21passt.base`. The import gate recorded zero network attempts, checkpoint
opens, `torch.load` calls and audio opens. Its canonical import report SHA-256
is `8f0b23e9943aa4e3f520f599479e575589102c07fa1c199424690cff0711768a`.

This installation did not make the challenger registered or executable.

The separately approved restricted construction and load gate then completed
on 2026-08-08:

```bash
scripts/setup-separation-other-refinement-query-runtime-macos.sh \
  --construct-and-load-models \
  --accept-restricted-model-load
```

The gate used the isolated CPython 3.12.10/macOS-arm64 runtime and operating
system network denial. It constructed the pinned 64-musical-band Banquet
setup-C topology with sixteen bidirectional GRUs, 64 mask heads, FiLM and its
embedded 527-class PaSST, plus the separate 20-class OpenMIC PaSST. Both PaSST
instances were constructed with `pretrained=False`; neither upstream loader
ran.

Before strict loading, Sunofriend compared every state key, tensor shape and
dtype:

| Model state | Verified result |
| --- | --- |
| Banquet checkpoint | 1,069 keys, 111,234,333 values, inventory SHA-256 `c562cc6f0b6807470d4d36ee4f6a048870e917afac9d7f92b2e35d7b9efec27f` |
| Standalone OpenMIC PaSST | 159 keys, 85,373,992 values, inventory SHA-256 `ed94f5ea73d96f5965b1f67f11e84264f0afadd2efbbfad4d22783a4fc2aef96` |
| Strict loads | zero missing keys and zero unexpected keys for both models |
| Effects boundary | zero network attempts, zero audio opens and zero inference runs |

The canonical load-report SHA-256 is
`12c028e88afdb94a22aa4344b75fb63a23386fd4f2292d9bf9aac0405b12dced`.
This result proves architecture/checkpoint compatibility under the restricted
loader. It does not prove separation quality, runtime resources or a working
forward adapter.

The challenger remains blocked, unregistered and non-executable. The next
bounded gate now has a pure forward contract and an immutable, no-effects plan:

```bash
.venv/bin/python \
  scripts/plan-separation-other-refinement-query-forward.py

.venv/bin/python \
  scripts/plan-separation-other-refinement-query-synthetic-report.py

.venv/bin/python \
  scripts/plan-separation-other-refinement-query-synthetic.py
```

The forward contract binds the exact setup-C topology and forward sequence to
nine files at source revision
`79ed5bb75e5c3a40cd319d9d990cee913fc65c26`; its document SHA-256 is
`cb83fdcf04057779d5970147d10e1944df29128b099c2a16b5d3b2e2cb829888`.
It describes STFT, 64-band splitting, sixteen alternating residual GRUs,
PaSST query embedding, FiLM conditioning, complex-mask overlap-add and exact-
length inverse STFT. It is design data only: no executable forward method was
added. The separate result contract has document SHA-256
`dd72e21b28734d5b2a2590e2751999a2cc76a78ced440b0c02b29974fe11a2a2`.
It validates either a complete objective pass or a retained objective failure,
requires the exact output clock, peaks, reconstruction and resource gates, and
rejects subjective feedback, automatic retry and product authority. The
synthetic plan document SHA-256 is
`301f4cbc6c3e6ec33be9459deacb049d9a004d94298402c8a7da63d8dc19926a`.
It proposes one CPU-only forward with a generated two-second stereo mixture and
generated ten-second stereo query, both held in memory, seed `0`, network
denial, a 180-second timeout and a 12 GiB memory ceiling. It writes only an
objective JSON report. One remediation is the absolute limit. No listening or
minimum usefulness rating can block recording the objective result.

The large setup shell previously duplicated validation and receipt-building
logic in an embedded Python block. That logic is now a pure standard-library
contract in
`src/sunofriend/separation_other_refinement_query_load_contract.py`, with a
small exclusive-write receipt command. Model identity, topology/loading,
synthetic execution and report validation are separate maintenance boundaries.
The refactor validates the already-recorded load report without changing its
canonical SHA-256. The topology and strict loading were then extracted into
separate reusable modules; a fresh network-denied load produced a byte-identical
report with zero network attempts, audio opens or inference runs. The one-way
network/audio/checkpoint enforcement is now a reusable execution guard rather
than inline CLI logic, and the proposed forward is a pure source-bound contract
rather than an inference implementation. Synthetic-result validation and its
exclusive receipt writer are also pure, reusable boundaries. A failed first
attempt remains evidence and cannot authorize an automatic remediation run.

The wider incremental restructuring sequence is recorded in
[Separation maintainability plan](SEPARATION_MAINTAINABILITY_PLAN.md).

Inference remains unapproved until the exact approval printed by the synthetic
plan is given. Private or persisted audio, song processing, public activation,
source selection and MIDI remain outside that approval.
