# Stem-separation developer preview

Sunofriend has two distinct finished-mix lanes on Apple-silicon macOS:

- the existing public default, `broad-vocals-v1`, which estimates broad vocals
  and complementary instrumental; and
- the explicit `core-four-stems-v1` public opt-in preview, served by the
  separately pinned SCNet-large profile for vocals, drums, bass and grouped
  other.

The MLX baseline and first PyTorch fallback remain blocked after their bounded
objective remediations failed. Further retries and installs of those immutable
profiles are disabled. SCNet passed its finite synthetic, authorised-song,
repeat-resource and catastrophic-listen gates and is admitted as
`public_opt_in`. Registration, doctor and setup planning load no model and
process no audio; the two-stem route remains the default.

## Architecture

- [`separation_profiles.py`](../src/sunofriend/separation_profiles.py) is the
  immutable model/runtime/terms/status registry.
- [`separation_scopes.py`](../src/sunofriend/separation_scopes.py) defines the
  role contracts and keeps the two-stem scope as the default.
- [`separation_alpha.py`](../src/sunofriend/separation_alpha.py) provides
  read-only planning, rights confirmation, network-denied worker launch,
  integrity verification and atomic publication.
- [`separation_demucs_mlx_worker.py`](../src/sunofriend/separation_demucs_mlx_worker.py)
  retains the failed fixed MLX baseline and exact PCM24 residual accounting.
- [`separation_demucs_infer_worker.py`](../src/sunofriend/separation_demucs_infer_worker.py)
  implements the pinned CPU fallback with one seeded shift, an explicit local
  model repository and no segment override.
- [`separation_scnet_worker.py`](../src/sunofriend/separation_scnet_worker.py)
  loads only the pinned release source and local checkpoint, then applies one
  seed-0 shift through fixed 11-second, overlap-0.25 sequential chunks.
- [`separation_scnet_canary.py`](../src/sunofriend/separation_scnet_canary.py)
  runs the copyright-safe 60-second fixture under network denial without
  changing profile status or applying a subjective quality threshold.
- [`separation_review.py`](../src/sunofriend/separation_review.py) exports a
  scope/profile/report-bound private review and safe text-only summary.
- [`separation_rollout.py`](../src/sunofriend/separation_rollout.py) encodes the
  one-configuration, one-remediation objective admission rule and non-blocking
  feedback policy.
- [`setup-separation-core-four-macos.sh`](../scripts/setup-separation-core-four-macos.sh)
  preserves the exact no-write historical plan and now refuses new installs of
  the objectively failed baseline.
- [`setup-separation-core-four-fallback-macos.sh`](../scripts/setup-separation-core-four-fallback-macos.sh)
  shows the exact no-write PyTorch fallback plan and requires separate terms
  approval before an atomic install.
- [`setup-separation-core-four-scnet-macos.sh`](../scripts/setup-separation-core-four-scnet-macos.sh)
  preserves the completed exact SCNet setup boundary and refuses to overwrite
  the installed profile.

## Inspect without changing the Mac

```bash
.venv/bin/sunofriend-separate profiles --json
scripts/setup-separation-core-four-macos.sh --plan
.venv/bin/sunofriend-separate doctor --scope core-four-stems-v1
```

The doctor verifies platform, exact packages, safetensors structure and hash,
configuration roles/clock, retained MIT evidence, terms receipt and network
denial availability without importing MLX or loading weights. An 8 GiB or
otherwise unverified Apple-silicon class receives an advisory warning; it is
not silently described as benchmarked.

## Fixed worker behavior

The coordinator canonicalizes one authorised source to stereo 44.1 kHz PCM24.
The worker loads only `model/htdemucs.safetensors` and
`model/htdemucs_config.json`, calls `load_mlx_model(..., auto_convert=False)`,
and refuses a first-run conversion artifact. It uses one deterministic shift
with seed `0`, overlap `0.25`, batch size `1` and one synchronous writer.
The unchanged pinned config stores its native segment as `"39/5"`. The first
run failed when the runtime repeated that string. The single bounded
remediation parsed the fraction as `7.8` seconds at the apply-model boundary,
but the second run failed inside HTDemucs `valid_length` because the model's
own field was still the string. The budget is therefore exhausted.

It preserves native vocals, drums and bass, adds the native reconstruction
residual to grouped other, applies one shared attenuation and constructs the
PCM24 other complement. Reports distinguish residual-correction RMS/peak from
separation quality. Every role and diagnostic is re-hashed before atomic
publication.

## Admission and feedback policy

`evaluate_preview_admission` requires exactly one synthetic demo, three
authorised song-disjoint canaries, three repeat resource runs, one baseline
configuration and at most one remediation. It reads objective gates and
resource measurements; subjective usefulness fields cannot affect admission.
An unresolved objective failure after remediation selects the fallback-backend
decision.

After activation, `feedback_rollout_action` triggers review at 30 days or 10
valid reports. Poor feedback publishes limitations and starts one bounded
challenger. It cannot demote the last functioning baseline. No code chooses a
model winner or starts downstream MIDI automatically. The first SCNet
technical run passed in 69.97 seconds at 6,581,846,016-byte peak RSS with
exact clocks and zero-LSB persisted reconstruction error. Its mathematical
vocal estimate was extremely quiet and vocal reference content remained mainly
in grouped other; this is recorded without starting a remediation loop. The
first verified machine class is the 36 GB M3 Max used for these runs. Other
Apple-silicon classes, including 16 GiB machines, remain accessible but
unverified and resource-supervised.

## Focused verification

```bash
.venv/bin/pytest -q \
  tests/test_separation_profiles.py \
  tests/test_separation_rollout.py \
  tests/test_separation_scopes.py \
  tests/test_separation_alpha.py
```

These tests cover registry immutability, package/hash locks, read-only setup,
explicit terms approval, offline launch, exact role mapping, residual
accounting, report binding, review validation, objective rollout and atomic
handoff. They use generated arrays and fake workers; they do not install or
load the model.

No live MLX activation artifact exists: both attempts failed in private staging
before publication, so no human listen or song canary was reached. The exact
PyTorch fallback plan and offline CPU worker were then installed with the
revised 20-wheel closure and passed doctor. Its synthetic worker failed before
inference or publication because the loaded native segment is
`Fraction(39, 5)`, which the pinned contract rejects. Retries are disabled; see
[the fallback audit](CORE_FOUR_FALLBACK_AUDIT.md). Approval is followed by the same finite
synthetic, song and resource sequence—not an unlimited search for unanimously
positive listening feedback.
