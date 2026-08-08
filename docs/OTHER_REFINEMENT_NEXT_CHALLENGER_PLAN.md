# Synth-first fine-stem challenger

Sunofriend's public opt-in baseline remains vocals, drums, bass and grouped
other. Two bounded attempts to split grouped other more deeply are retained as
negative evidence:

- `htdemucs_6s` passed objective execution but demonstrated neither useful
  guitar extraction nor successful piano extraction; and
- Banquet passed its objective adapter and canary gates, but the completed
  review rated eight of nine targets not useful and one quiet keyboard target
  partly useful.

Neither result is being retuned or rerun. Negative listening does not disable
the public core-four profile, and it does not create an empirical doom loop.

## Priority is synth, then guitar and wind

The next milestone targets `synth` first. Synthesizers are more pervasive in
modern popular music than acoustic piano, while treating piano as “keys” hid
the actual product goal. The priority is now:

1. `synth`;
2. `guitar`; and
3. `wind`.

Acoustic piano remains an optional control. It is not a proxy for synth,
organ, electric-piano or general keyboard separation.

## First research candidate

The next candidate is the public
[MVSep Mega 53 Stems v1.0.21 release](https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/tag/v1.0.21),
which publishes explicit `synth`, `wind`, `guitar`, `electric-guitar` and
`acoustic-guitar` roles. It uses a Band-Split RoFormer architecture, unlike the
failed query-conditioned Banquet route and the earlier `htdemucs_6s` route.

This is a research candidate, not a product claim. Upstream says the model is
memory-intensive, recommends at least 16 GB VRAM, warns that individual roles
may underperform specialised models, and states that its 53 outputs overlap
and do not sum to the mixture. The first benchmark therefore targets the
verified 36 GB M3 Max and persists only:

- the native `synth` estimate; and
- `residual_other = canonical_grouped_other - persisted_synth`.

That two-file equality is transparent PCM24 accounting, not proof that the
synth estimate is musically accurate. The report records the native estimate's
correction RMS and peak. Guitar and wind require separate later evidence even
though the same model exposes those roles.

Inspect the immutable no-effects plan with:

```bash
.venv/bin/python \
  scripts/plan-separation-other-refinement-next-challenger.py
```

The plan neither downloads nor loads anything, reads no audio and grants no
execution, source-selection or MIDI authority.

## Exact source and artifacts

The proposed Apple-silicon runtime is the MLX backend at exact
`openmirlab/bs-roformer-infer` revision
`de35ada5817b878da0194ee2860253dda3a9c2b2`. Its git-archive SHA-256 is
`e64fe7733a45f5efc53091bbc2ab6dd04a0ee7373a639f1c9b27275502f26691`.
The source is MIT-licensed, but the published version string remains `0.1.5`
and the released wheel predates this audited MLX revision. A future runtime
must therefore pin this source revision, not merely a package version.

The upstream registry declares:

| Artifact | Bytes | Declared SHA-256 |
| --- | ---: | --- |
| `mvsep_mega_model_bs_roformer_53_stems_v1.ckpt` | 1,368,919,887 | `c62820893bbf86d4e734f966bd142d9157cfc8bb8e79e9d8f9ea553f3ff3519f` |
| `mvsep_mega_model_bs_roformer_53_stems.yaml` | 4,184 | `7e198062a251587088adb91215a4f44ab59e67bd62fcc805cf54d6e7dfc51103` |

Those identities were locally verified on 8 August 2026 by the separately
approved evidence-only gate. The exact observed total was 1,368,924,071 bytes,
and both SHA-256 values matched the registry. Network was denied before the
inspector inventoried 13,599 checkpoint members and parsed 565,328 pickle
opcodes. It did not deserialize the checkpoint, call `torch.load`, import or
construct a model, run inference or read audio. The immutable static-evidence
document SHA-256 is
`d855138176807a7ca8738bd660141eb2b142676e41ccf56014be64e53f012a24`.

Reproduce the already consumed evidence boundary only in a fresh evidence root
and only with equivalent explicit approval:

```bash
scripts/setup-separation-other-refinement-next-challenger-macos.sh \
  --evidence-only \
  --accept-provisional-local-noncommercial-terms \
  --accept-checkpoint-use
```

The source registry still labels
the checkpoint licence `not-reviewed`. The public GitHub release is strong
evidence that the maker intended the artifact to be shared, but it is not a
licence grant for hosting, redistribution or a commercial default. The first
gate therefore used a capped evidence-only download under an explicit
provisional local-noncommercial acknowledgement. It did not wait for a bespoke
email, and grants nothing beyond the completed static evidence collection.

The source's MLX backend currently reaches an unrestricted `torch.load`.
Sunofriend will not use that loader. A future adapter must load one explicit
local checkpoint with
`torch.load(weights_only=True, map_location="cpu")`, compare every key, shape
and dtype before strict conversion, disable automatic downloads with
`download_missing=False`, and run with network denied.

## Exact runtime closure

The separately approved evidence-only dependency gate resolved 29 exact
CPython 3.12/macOS-arm64 wheels. The closure is 127,527,173 bytes, against a
1,610,612,736-byte cap; peak staged evidence was 128,346,422 bytes. Static
inspection ran with network denied, checked every wheel ZIP, parsed package and
dependency metadata, and hashed bundled licence files. It did not install or
import a package, execute wheel code, load a checkpoint, construct a model,
run inference or read audio.

The exact lock is
`separation-other-refinement-next-runtime-requirements.txt`, SHA-256
`284d198c43e9074a4d645f005d937dd4e93b99e22aa21d942caaa1822b13d10b`.
The immutable static-evidence document SHA-256 is
`d8488079a9c82961056e296fa1050e07f2d341602293b01ed3e5b1de32ae5327`.
Direct pins include Torch 2.2.2, MLX 0.31.2, MLX-Spectro 0.7.0 and NumPy
1.26.4. All 29 wheels have licence metadata or bundled licence-file evidence;
no contradiction with private local evaluation was found. Binary
redistribution still needs a separate composite-notice review, and this audit
does not change the checkpoint's provisional local-noncommercial boundary.

The single bounded resolver remediation made two compatibility constraints
explicit: MLX 0.31.2 requires a macOS 14-or-later arm64 wheel target, and
rotary-embedding-torch 0.9.1 requires Torch 2.4 or later. The lock therefore
uses the newest compatible 0.8 release, rotary-embedding-torch 0.8.9, while
retaining the already proven Torch 2.2.2 and NumPy 1.26.4 baseline.

The completed evidence command was:

```bash
scripts/setup-separation-other-refinement-next-challenger-macos.sh \
  --runtime-wheel-evidence-only \
  --accept-runtime-wheel-evidence
```

That authority is consumed. The next gate is a fresh isolated installation
from the local wheel cache plus network-denied import verification, and needs
separate explicit approval. It may not load either checkpoint or construct the
model.

## Evaluation without false failures

The earlier corpus exposed an evaluation flaw: some windows may not audibly
contain the requested instrument. A silent target can be correct when the
instrument is absent, and an empty estimate cannot prove model failure when
presence was never established.

The synth evaluation separates two questions:

1. Before scoring the model, a listener records `present`, `absent` or
   `cannot_tell` for synth in each frozen source window.
2. Only an audibly present case receives `useful`, `partly_useful`,
   `not_useful` or `cannot_tell` model feedback.

`absent` and `cannot_tell` remain valid reports. They are not counted as model
failures and do not trigger a search for replacement windows. This prevents
both false negatives and a post-result hunt for favourable examples.

The first round freezes one 15-second window from each of four
owner-authorised Ezzye tracks, one model configuration and at most four
inference calls. Provider stems remain independent comparison estimates, not
truth. There is at most one remediation cycle, and only for an objective
execution fault. Poor or mixed musical feedback is published and informs the
next candidate; it cannot start automatic tuning, select a source, activate
MIDI or remove the functioning core-four route.

## Ordered gates

The remaining gates are deliberately one-way:

1. **Complete:** evidence-only artifact download and exact hash verification;
2. **Complete:** network-denied, non-loading static inspection;
3. **Complete:** a fully hash-locked CPython 3.12/macOS 14+ arm64 dependency closure;
4. **Next, not yet approved:** isolated install and import verification;
5. strict weights-only construction and load;
6. one generated-tensor objective forward; and
7. one four-song synth canary.

Failure of an objective gate stops this candidate or uses its single
remediation. Poor listening does not. Public activation, hosted conversion,
source selection and MIDI remain separate decisions.
