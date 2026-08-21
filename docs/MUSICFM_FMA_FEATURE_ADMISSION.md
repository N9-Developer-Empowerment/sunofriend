# MusicFM-FMA frozen-feature admission

Status: exact public metadata and static artifact evidence complete; runtime
installation, model loading, inference and private-audio access are not
authorised.

## Decision

The first pretrained candidate for the remix ranker is the FMA checkpoint of
MusicFM. It is a **frozen feature provider**, not a remix generator. Sunofriend
will train only a small comparison head over its features and the existing
transparent edit features. Even a promoted head may only order which bounded
challenger the musician hears first.

The current no-effects plan pins:

- upstream source revision `b83ebedb401bcef639b26b05c0c8bee1dc2dfe71`;
- Hugging Face publication revision
  `4513b38bc25ad1d227b1980819b9691ba97f4d87`;
- `pretrained_fma.pt`, 1,316,802,154 bytes, SHA-256
  `68392eee13d34c2941b3761934abb6b1e67b2e9df498695bda2ea5c1087d4b96`;
- `fma_stats.json`, 2,281 bytes, publication Git blob
  `4b72fa21d6962f55ae9c95b3457e765eb19552e5`; and
- external Conformer configuration publication revision
  `6b36ef01c6443c67ae7ed0822876d091ab50e4aa`, 2,239 bytes, Git blob
  `f74dbbf6fe96728cceda4888cf841b39a579e66e`; and
- the proposed 24 kHz mono, 25 Hz, layer-7, 1,024-dimensional feature clock.

Generate the path-free plan without writing or downloading anything:

```bash
python3 scripts/plan-remix-musicfm-fma.py
```

## Why admission is still blocked

The upstream constructor calls `from_pretrained` for a separate Facebook
Wav2Vec2-Conformer configuration. That must be replaced by an exact local,
hash-pinned configuration so an offline run cannot fetch implicitly. The
checkpoint is a PyTorch pickle wrapper; it must be statically inspected and
loaded only with `weights_only=True`, exact key/shape/dtype validation and
network denial. Static artifact inspection is now complete, but the complete
runtime still needs a source manifest and dependency lock before any import or
load may occur.

The approved evidence-only gate subsequently established:

- statistics SHA-256
  `5416e468018bae68c6231d4cbb2b11f0d11c04e6437881505ae427a3f8344904`;
- Conformer configuration SHA-256
  `7a63cb5706c9a37483f1973a3c226d54eb504ce15cf62cb52637019540c8a75d`;
- static-evidence document SHA-256
  `99f1c24d44a3f08d68d614e4878c1cc0c05f1e941e071cbb9a3f5e9c7aeaf846`;
- runtime-blocked readiness document SHA-256
  `699515e32ce70fc20e5f1f528f988ad6746e01d89580b436e644ec0f8ffbc2a9`;
- 66 ZIP members and one 108,293-byte protocol-2 pickle metadata stream; and
- exactly five declared pickle globals, with no unresolved stack globals or
  trailing bytes.

The inspection ran under OS network denial. It parsed archive metadata and
pickle opcodes only; it did not read tensor-storage payloads, deserialize the
checkpoint, import MusicFM, call `torch.load`, open audio or run inference.
The exact three-file round trip passed.

The published MIT metadata and Creative-Commons corpus description are useful
evidence, not a guarantee that every training-data or downstream-use question
is resolved. Licence and source evidence remain visible in every admitted
feature manifest.

## Separate gates

1. The capped evidence-only download and static inspection are complete.
2. Create the hash-locked runtime source and dependency plan. Upstream publishes
   no requirements lock; static imports identify `torch`, `torchaudio`,
   `transformers` and `einops` as the direct runtime packages.
3. Separately approve dependency download and installation into a new isolated
   runtime, followed by import-only
   inspection under network denial.
4. Separately approve one deterministic synthetic feature extraction. Require
   exact repeat features, finite float32 output, fixed shape/clock and a 12 GB
   RTX resource receipt.
5. Only after those pass, create a fresh plan for authorised owner-audio
   feature extraction. Real ranker training remains blocked until the explicit
   composition-disjoint label gate is satisfied.

MusicFM's upstream documentation reports weak key-detection performance, so
Sunofriend retains deterministic harmony/chroma, onset and edit-envelope
features in parallel. Replacing the extractor creates a new manifest and
invalidates dependent training evidence.

## Windows runtime plan

`scripts/plan-remix-musicfm-fma-runtime.py` now creates a path-free plan bound
to the exact admission plan, static evidence and readiness documents. It pins
the seven required source/licence files by Git blob and the first four direct
Windows wheels:

- Torch 2.7.1+cu128, CPython 3.11 win-amd64;
- Torchaudio 2.7.1+cu128, CPython 3.11 win-amd64;
- Transformers 4.53.2; and
- Einops 0.8.1.

Those direct wheels total 3,288,617,517 bytes. They are **not** a complete
dependency closure and are not an installable lock. The plan requires a fresh
`musicfm-fma-windows-py311-cu128-v1` environment and explicitly forbids
modifying or reusing the working Demucs environment.

The first plan-only resolver pass selected 26 Windows wheel candidates totalling
3,319,356,874 bytes and retained their public hashes without downloading the
wheels. It also exposed an important cross-platform limitation: while pip chose
Windows artifacts, it evaluated dependency environment markers against the Mac
host. As a result, Windows-only `colorama` was omitted and host-selected
`hf-xet` still requires a native Windows recheck. Sunofriend therefore records
this pass only as partial evidence, never as a complete closure or install lock.

The next plan-only step is a native Windows metadata-only resolution. It may
retain the resolver report but downloads and installs no wheels. Only that
native roster can set the final byte ceiling for a separately approved
evidence-only wheel and licence inspection.
The retained runtime plan is bound to commit
`d1f559fe417916d22a7ee0aba26676fcc9b46abb` and has document SHA-256
`fc728a03d7525425a67f42924eadaabd17aeb1ee28b34e894250e09d6c123b83`.
