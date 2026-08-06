# Core-four SCNet static audit

## Decision

Official SCNet-large is the installed `public_opt_in` core-four profile. Its
finite objective canaries and catastrophic-output listening checks are
complete. Musical usefulness remains open feedback, not an admission gate.

The approved exact setup installed the 12-wheel Apple-arm64 runtime and pinned
release source, then performed a weights-only strict checkpoint inspection
under network denial. The published checkpoint uses the official `best_state`
tensor wrapper rather than the initially accepted direct/`state` shapes. The
one permitted transparent remediation accepted that documented wrapper;
strict keys, shapes and dtypes then passed with no prefix changes. No forward
pass or audio read occurred during setup.

Separately approved real forward passes then processed Sunofriend's 60-second
copyright-safe mathematical fixture under network denial. Three same-setting
runs produced byte-identical canonical audio in 69.97, 70.20 and 71.18 seconds,
with 6,581,846,016 to 6,719,586,304-byte peak RSS and zero-LSB reconstruction
error. The machine was a 36 GB M3 Max, explicitly approved as the first
verified class. Other Apple-silicon classes, including 16 GiB machines, remain
accessible but unverified and resource-supervised.

## Exact evidence captured on 2026-08-06

| Item | Evidence |
| --- | --- |
| Official repository | [`starrytong/SCNet`](https://github.com/starrytong/SCNet) |
| Current source revision | `5d95bf96b19c3eede63248d171efeca8e3abb948` |
| Selected release source revision | `6236f8c559778dc271e1aea9baa3993ae655e905` |
| Release architecture source | 13,853 bytes, SHA-256 `5e77c363f7f0187432a984d8ae1aa511826295d732372f0c280e68e4fecd4550` |
| Release README | 2,031 bytes, SHA-256 `5216a5b0ae85715f7eedbadda4d8d71dd063fb2bc40ba2a90cb61cf3458136dc` |
| Release requirements | 136 bytes, SHA-256 `892a58352a75ee9d6cd98c68de9a4b6c733fb4f2e5788f3c6bd2b07676c2b66f` |
| Source licence | MIT, 1,067 bytes, SHA-256 `0bdf1b69335198118ab16cfc50d337b496b8c6d90e83beeaba4643781ab62513` |
| README | 2,044 bytes, SHA-256 `edc1d7e1f190068eff924b974aa901d5e0b8b560139587787939de04062a009b` |
| Upstream requirements | 136 bytes, SHA-256 `5af27b6912eddb99793d94936f3ab53e344fb09bd139d75c0969c54086a821bd` |
| Official release | `update`, release ID `176435283`, tag revision `6236f8c559778dc271e1aea9baa3993ae655e905` |
| GitHub release assets | none in the official API; no asset digest |
| Large checkpoint | Google Drive file `1s7QvQwn8ag9oVstGDBQ6KZvacJkvyK7t`; filename `SCNet-large.th` |
| Checkpoint bytes / SHA-256 | 168,848,417 bytes; `719e5abb8ed920305dad546ac3cd6fb0b1e9c3092d14ce21827bfc0423af3070` |
| Evidence method | approved evidence-only download capped at 1 GiB; `stat`, `shasum -a 256` and `openssl dgst -sha256` agreed; checkpoint not loaded; temporary copy removed after recheck |
| Separate checkpoint terms | not found |
| Large config | Google Drive file `1qxK7SZx6-Gsp1s3wCrj98X7--UcI4O3K`, 1,080 bytes, SHA-256 `629a4901184bf1d3a75b0b13904f35974785aa042cad3c010fd576248cdce3f0` |
| Roles / clock | drums, bass, other, vocals; stereo 44.1 kHz |
| Large architecture | 42,181,232 parameters; 168,724,928 uncompressed state bytes |
| Release-source probe | Torch 2.8.0, network denied, no checkpoint/audio; 380,043,264-byte maximum RSS |
| Installed runtime | 12 exact Apple-arm64/Python 3.13 wheels, 95,981,536 bytes |
| Exact setup transfer | 264,851,903 bytes; 2,000,000,000 free bytes required before staging |
| Compatibility | weights-only, memory-mapped, strict 372-key state dict; official `best_state` wrapper; one remediation; 536,199,168-byte max RSS; zero forward/audio |
| Synthetic inference | three same-setting 60.0-second runs; 69.97–71.18 seconds worker elapsed; 6,581,846,016–6,719,586,304-byte peak RSS; byte-identical outputs; network denied |
| Persistence | exact four roles; shared gain 1.0; native-other correction RMS 0.000671776 / peak 0.00568625; zero-LSB reconstruction error |

The release tag uses `torch==2.0.1` and `torchaudio==2.0.2`. The selected
minimal adapter instead uses the already-audited Apple-arm64 `torch==2.8.0`
wheel and removes the wrapper/training dependencies. The official large config
constructs and executes the release architecture exactly under that runtime.
The compatibility difference is confined to the official checkpoint's
`best_state` wrapper and is permanently recorded as the one remediation.

## Minimal adapter position

SCNet's inference architecture itself needs PyTorch; the official wrapper also
imports training/general-purpose packages including Accelerate,
`ml_collections`, Julius, SoundFile and Torchaudio. Sunofriend's canonical
stereo 44.1 kHz PCM24 boundary can avoid those wrapper dependencies by:

- retaining only the exact MIT `SCNet.py` and `separation.py` source;
- loading one explicit local checkpoint under macOS network denial;
- using a Sunofriend-owned deterministic one-shift, seed-0, overlap-0.25
  chunk runner;
- preserving the existing four-role, finite-sample, clock, peak, residual and
  exact PCM24 reconstruction contracts; and
- keeping MIDI activation separate.

The installed hash lock is
[`separation-core-four-scnet-runtime-requirements.txt`](../separation-core-four-scnet-runtime-requirements.txt).
The exact approved installation receipt retains terms/checkpoint acceptance,
artifact identities and both the baseline-failure and remediated compatibility
receipts.

## Resolved admission evidence

- The exact observed checkpoint identity is now pinned. The upstream Google
  Drive object remains mutable, so every future approved download must match
  the recorded 168,848,417 bytes and SHA-256 before use.
- No checkpoint-specific terms file exists. On 2026-08-06 the disclosed
  repository MIT metadata plus official README-linked checkpoint was explicitly
  accepted as sufficient provisional preview evidence. This is a documented
  project admission decision, not a claim that a separate weights licence was
  found.

## Admission result

- The synthetic fixture and three same-configuration repeat runs passed.
- Three authorised, song-disjoint full-song canaries passed role, clock,
  integrity, offline, resource and exact reconstruction checks.
- The project owner listened to every source, four stems and reconstruction
  check and reported no catastrophic defect.
- The immutable profile is admitted as `public_opt_in`. Poor musical
  usefulness remains valid feedback but is not an admission blocker.

Inspect the no-write decision record:

```bash
.venv/bin/python scripts/plan-separation-core-four-scnet.py
```

The command performs no network access, downloads, installs, model loads,
audio reads or writes. It reports the exact immutable installed-profile plan.

Inspect the reviewed human-readable setup boundary:

```bash
scripts/setup-separation-core-four-scnet-macos.sh --plan
```

It records exactly 264,851,903 download bytes across four network
destinations, a 2 GB free-disk preflight, atomic fresh staging, 12 hash-locked
binary wheels, and an offline `torch.load(weights_only=True,
map_location='cpu')` compatibility inspection. No forward pass or audio read
is permitted during that compatibility phase. With an existing profile root,
the command refuses to overwrite it.

## Current bounded inference command

The approved synthetic-only worker boundary is:

```bash
.venv/bin/python scripts/run-separation-core-four-scnet-synthetic.py \
  --out FRESH --execute --confirm-synthetic
```

The first run passed technically. Reference diagnostics found that the
mathematical vocal role was largely retained in grouped other and the vocal
estimate was extremely quiet. Record that limitation and continue the finite
canaries; do not tune repeatedly or revoke the only technically functioning
profile because of this subjective/usefulness result. See
[the approval ledger](CORE_FOUR_MODEL_APPROVALS.md) for the remaining consent
boundaries and optional maintainer-email trigger.
