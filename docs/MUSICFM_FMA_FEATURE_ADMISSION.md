# MusicFM-FMA frozen-feature admission

Status: exact public metadata pinned; checkpoint access, runtime installation,
model loading, inference and private-audio access are not authorised.

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
network denial. The statistics file still needs its actual local SHA-256, and
the complete runtime needs a dependency lock.

The published MIT metadata and Creative-Commons corpus description are useful
evidence, not a guarantee that every training-data or downstream-use question
is resolved. Licence and source evidence remain visible in every admitted
feature manifest.

## Separate gates

1. Explicitly approve a capped evidence-only download of the exact checkpoint,
   statistics and required configuration. This grants no installation, load,
   inference or audio access.
2. Inspect all artifacts without unrestricted deserialisation and create the
   hash-locked runtime plan.
3. Separately approve installation into a new isolated runtime and import-only
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
