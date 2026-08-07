# Six-source MLX Studio-challenger audit

Status: **installed and objectively qualified as an opt-in Studio challenger**.

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

## Resolved objective compatibility problem

Static inspection found that this six-source config stores `segment` as the
string `"39/5"`. That is the same representation involved in the earlier
four-source MLX activation failure. It was the candidate's one permitted
compatibility remediation, not a reason for indefinite pre-release tuning.

Exactly one remediation is permitted: after verifying the immutable config,
copy it in memory, parse `Fraction(39, 5)`, replace only the copied
`kwargs.segment` with `7.8`, and construct the model from explicit local files.
The source config cannot be mutated, no derived config may be persisted, named
model resolution stays disabled and `auto_convert=False` remains mandatory.

The remediation passed without changing the pinned config. Model construction,
the synthetic canary, and guitar and piano-proxy runs on one authorised
234-second parent all ran with networking denied. The full-song runs completed
in 9.94 and 9.22 seconds at about 3.49 GB peak MLX memory and reconstructed at
zero PCM24 LSB. Both requested targets were low-energy; that limitation is
published and does not revoke Studio access.

The later fixed five-song, ten-report review provided the final musical result
for this bounded candidate. Four guitar reports were `not_useful`; the fifth
reported severe missing content. The only nominally useful piano-proxy report
was correct near-silence where no piano existed, while one reviewed piano-like
instrument was missed. The objective pass stands, but the candidate did not
demonstrate useful guitar or successful piano extraction. It remains
reproducible in Studio and is neither promoted nor selected for MIDI.

This completes the candidate's feedback cycle. Do not tune or rerun it as a
route to general keyboard separation. The separately reviewed next question
targets guitar and broad `keyboard_synth` through a query-conditioned model.

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

## Bounded execution route

After the separately approved setup, plan one bound run with
`sunofriend-separate refine-other CORE_FOUR_ROOT --target guitar --out FRESH`.
Add `--execute --confirm-rights` to load the installed model offline. The
result exposes target, residual and unchanged parent for human listening
without selecting a winner. Only objective faults can stop execution: identity
drift, network access, missing or extra roles, clock mismatch, non-finite
audio, failed target/residual accounting, source mutation, crash or declared-
machine OOM. Poor musical feedback stays visible without disabling core four
or forcing more pre-release tuning.
