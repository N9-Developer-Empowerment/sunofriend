# Six-source MLX Studio-challenger audit

Status: **pinned plan; installation and execution not approved by this audit**.

The first concrete backend candidate for `other-refinement-v1` is
`demucs-mlx-htdemucs-6s-other-refinement-v1`. It is a Studio-only challenger,
not a replacement for the public SCNet core-four profile and not a public
finished-mix route.

The candidate was selected because it is Apple-silicon-native and PyTorch-free
at inference, while exposing the official experimental Demucs six-source role
set. The [Demucs v4.0.1 documentation](https://github.com/facebookresearch/demucs/tree/v4.0.1)
describes `htdemucs_6s` as adding guitar and piano and explicitly warns that
piano contains substantial bleed and artefacts. The
[demucs-mlx project](https://github.com/ssmall256/demucs-mlx) supports this
model, and the pinned [MLX Community repository](https://huggingface.co/mlx-community/demucs-mlx/tree/d4519e24ddc2dd4a11d56a193092433d852c3961)
publishes its converted safetensors and config with MIT metadata.

## Immutable candidate identity

| Item | Pinned identity |
| --- | --- |
| Profile | `demucs-mlx-htdemucs-6s-other-refinement-v1` |
| Model | `mlx-community/demucs-mlx:htdemucs_6s` |
| Model revision | `d4519e24ddc2dd4a11d56a193092433d852c3961` |
| Weights | `htdemucs_6s.safetensors`, 109,726,583 bytes |
| Weights SHA-256 | `d298f7f746bf53c21baad44fb08e88807ef47feb551dd22f1601a546c85b8e02` |
| Config | `htdemucs_6s_config.json`, 1,946 bytes |
| Config SHA-256 | `97f8315891d8edc9aa6f59e56e0d352fbad5ebfb8a4faf46341ab2f1844596a9` |
| Exact model roles | `drums`, `bass`, `other`, `vocals`, `guitar`, `piano` |
| Runtime | `demucs-mlx==1.4.4` |
| Runtime source audit | `b37e6ba3c5985af531f61c43564cf13c6ed349fd` |
| Runtime wheel SHA-256 | `dc40828b0a8591720082d2494696249790573d4ff6e5be72b16594e131b23e64` |
| Runtime lock | 9 exact packages, 1,640 bytes, SHA-256 `11af62d2ce759e8e4937bd10046892c03dc8ba61bf8cb2537b6a53f4a257587c` |

The runtime source audit revision is the revision already used by the failed
four-source MLX profile. The `v1.4.4` Git tag resolves to
`36b43ce2fc908129fb9166d4c109f7ccb77d12bf`; the exact wheel hash, not a
mutable branch name, remains the executable runtime identity.

## Product mapping

The model always computes six diagnostic roles, whose order must match exactly.
Sunofriend will request only one product target per run:

- `guitar` uses the model's experimental `guitar` role and maps to canonical
  `rhythm`;
- `keys` uses the model's `piano` role as a disclosed proxy. It is not a claim
  to isolate synthesizers, organs or every keyboard sound.

Only the requested target and `other residual = persisted parent other -
persisted target` may become product artifacts. The two PCM24 children must
reconstruct the exact grouped-other parent within two LSBs. Other computed
model roles are diagnostic evidence, not additional stems, and the parent plus
children can never enter MIDI together.

## Known objective compatibility problem

Static inspection found that this six-source config stores `segment` as the
string `"39/5"`. That is the same representation involved in the earlier
four-source MLX activation failure. The candidate therefore remains blocked.

Exactly one remediation is permitted: after verifying the immutable config,
copy it in memory, parse `Fraction(39, 5)`, replace only the copied
`kwargs.segment` with `7.8`, and construct the model from explicit local files.
The source config cannot be mutated, no derived config may be persisted, named
model resolution stays disabled and `auto_convert=False` remains mandatory.

If that remediation fails the installed-artifact compatibility or synthetic
canary, this candidate stops. It does not begin an unlimited tuning sequence.

## Read-only plan and exact approval boundary

Inspect the complete JSON plan without changing the machine:

```bash
scripts/setup-separation-other-refinement-demucs-mlx-macos.sh --plan
```

The approval-gated setup command is:

```bash
scripts/setup-separation-other-refinement-demucs-mlx-macos.sh \
  --install --accept-model-terms --accept-checkpoint-use
```

That approval covers only:

- installation of the nine hash-locked runtime packages;
- download of the exact checkpoint, config, model card and runtime evidence;
- retention of the MIT/provenance record; and
- a network-denied static identity/config inspection.

Even after approval, setup does **not** import the model module, open the
safetensors payload, construct a model, run inference, read audio, publish a
conversion service, activate a source-graph node or create MIDI. Those remain
separate gates. The installer has a 1 GiB staged-installation ceiling and
refuses to overwrite an existing profile root.

## Bounded way forward

After an approved setup passes, the next separately reviewed step is one
network-denied model-construction check and one deterministic synthetic canary.
Only objective faults can stop it: identity drift, network access, missing or
extra roles, clock mismatch, non-finite audio, failed target/residual
accounting, source mutation, crash or declared-machine OOM.

If those gates pass, Studio may expose the target, residual and unchanged
parent for human listening without selecting a winner. Poor guitar isolation
or the already expected weak piano result becomes a published limitation and
feedback signal; it does not disable core four or force more pre-release tuning.
