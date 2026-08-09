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
and the released wheel predates this audited MLX revision. The completed
evidence runtime therefore pins this source revision, not merely
a package version, and never installs the stale released wheel.

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

The source's MLX backend reaches an unrestricted `torch.load`, so Sunofriend
does not use that loader. The completed restricted adapter loaded one explicit
local checkpoint with
`torch.load(weights_only=True, map_location="cpu")`, compared every key, shape
and dtype before strict conversion, disabled automatic downloads and ran with
network denied.

The exact GitHub source tarball was separately capped at 32 MiB and observed at
144,791 bytes with SHA-256
`9b95036b8219eb5cd7be61a29868e6633dd42df0078eda55a0f3710123551c73`.
All 64 files (522,358 logical bytes) matched the sealed inventory, including
the six previously audited critical-file hashes. Static extraction and
inspection ran with network denied and imported or executed no source. The
source-evidence document SHA-256 is
`982ce7c2e9355be9a79d701c8f505237ada7da6ebad41695b48b70dc8c6aad97`.

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

That authority is consumed.

## Isolated runtime import gate

The separately approved follow-up installed the exact 29-wheel lock into a
fresh CPython 3.12.10/macOS-arm64 environment using only the local cache,
`--no-index`, `--require-hashes` and OS network denial. All 29 installed
distributions matched the lock and the thirteen direct runtime modules imported
from the isolated environment. The runtime contains 21,124 regular files and
620,247,886 logical file bytes. The canonical import-report SHA-256 is
`60eefa4285f720cc81f795b126c32dbc9462f05d1398662702bd313f394202a9`;
the report file SHA-256 is
`567068a414c5ebc0cdb7cd47564934c5ec8f6b13c70425dd736c02af43892ac7`.

The first verifier pass correctly stopped on a socket audit event. The single
allowed remediation established from installed source that importing
`requests`/`urllib3` constructs a socket and attempts a loopback `::1` bind to
probe IPv6 support. The final verifier records that contained local probe
separately while continuing to fail any connect, DNS or non-loopback operation.
The OS network-denial sandbox remained active. There were zero Python network
attempts, checkpoint or audio opens, and `torch.load` calls.

The completed command was:

```bash
scripts/setup-separation-other-refinement-next-challenger-macos.sh \
  --install-runtime \
  --accept-runtime-install-and-import
```

That runtime-install authority is consumed.

## Strict construction and load gate

The separately approved model gate constructed the exact MLX topology from the
verified immutable source and loaded the checkpoint once with the required
weights-only CPU call. The raw checkpoint contains 13,595 tensor entries and
681,663,596 values. Its audited conversion skips 24 non-parameter rotary
buffers (768 values), leaving 13,571 model parameters and 681,662,828 values.
Every converted key, shape and dtype matched the constructed model before a
strict load; the constructed, converted and loaded inventory SHA-256 is
`565a9430061391486c8686d80eb4b6b65fdfd402b4bdeb603ab4ef5cf8c41fd8`.
The canonical report SHA-256 is
`798b5250eacf18d3f6193fde9d5c613ee68520490aed663395313a47eea4d666`.

The bounded compatibility remediation records an upstream config/adapter
contradiction rather than hiding it. Checkpoint tensor geometry requires
transformer expansion 4 and mask-head expansion 2, while the audited MLX port
feeds one setting to both. Sunofriend's process-local adapter splits those two
checkpoint-derived values and casts the constructed parameters to the
checkpoint's float16 dtype; it does not mutate the verified source. The gate
recorded one checkpoint load, zero network attempts, zero audio opens and zero
forward calls. It performed no inference, activation, selection or MIDI.

The upstream inference chunk is 882,000 samples and its overlap-2 step is
441,000 samples. Neither is divisible by the 512-sample STFT hop. Sunofriend
recorded that objective mismatch and did not silently change it during model
loading.

The pure no-effects contract now applies one deterministic rule: choose the
largest value no greater than the published chunk that is divisible by
`stft_hop_length * num_overlap`. This produces an 881,664-sample chunk and a
440,832-sample step—1,722 and 861 STFT hops respectively. The change is 336
samples, or 7.62 ms, shorter than the publication. The generated tensor uses
that exact length, so no input padding or output cropping is hidden. Verified
source, configuration and checkpoint bytes remain unchanged.

Inspect the frozen contract with:

```bash
.venv/bin/python \
  scripts/plan-separation-other-refinement-next-synthetic.py
```

Its canonical document SHA-256 is
`1ac15c7082223fcf2bdfd1d7443320f782cae87b8ac6e89cf991c19553da9903`.
The plan binds one seed-0 in-memory stereo float32 tensor with shape
`[1, 2, 881664]`, the exact 53-role output order, `synth` at zero-based index
38, one checkpoint reload, one construction and one forward attempt. It opens
and persists no audio, permits no retry and performs no action merely by being
printed.

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
4. **Complete:** isolated install and import verification;
5. **Complete:** strict weights-only construction and load;
6. **Ready for explicit approval:** one generated-tensor objective forward
   under the frozen 881,664/440,832 alignment contract; and
7. one four-song synth canary.

Failure of an objective gate stops this candidate or uses its single
remediation. Poor listening does not. Public activation, hosted conversion,
source selection and MIDI remain separate decisions.
