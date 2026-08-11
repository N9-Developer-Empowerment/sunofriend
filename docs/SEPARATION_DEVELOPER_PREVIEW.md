# Stem-separation developer preview

Sunofriend has four deliberately distinct finished-mix lanes:

| Lane | Roles | Release boundary |
| --- | --- | --- |
| Public default | broad vocals and complementary instrumental | `broad-vocals-v1` |
| Public explicit opt-in | vocals, drums, bass and grouped other | SCNet `core-four-stems-v1` |
| Private specialist research | vocals, drums, bass, synth, guitar and residual other | unregistered Mega-53/BS-RoFormer evidence |
| Private model-free recovery | full-song source, six roles and reconstruction | `private_review_package_recovered_model_free_resource_gate_incomplete`; not objective qualification |

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
- [`separation_fine_stem_full_song_plan_contract.py`](../src/sunofriend/separation_fine_stem_full_song_plan_contract.py)
  validates the immutable three-song private plan without model or audio
  imports.
- [`separation_fine_stem_full_song_execution_worker.py`](../src/sunofriend/separation_fine_stem_full_song_execution_worker.py)
  contains the three bounded, single-profile private worker modes. Future
  BS-RoFormer runs install the verified source-package stub before importing
  `MLXBackend`.
- [`separation_fine_stem_full_song_recovery.py`](../src/sunofriend/separation_fine_stem_full_song_recovery.py)
  binds retained failure evidence and performs the fixed no-model projection,
  private publication and incomplete-resource report.
- [`_private_verified_audio_inputs.py`](../src/sunofriend/_private_verified_audio_inputs.py)
  supplies descriptor-bound PCM24, NPY and exact-byte reads for immutable
  private evidence.
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

## Historical blocked MLX worker behavior

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

## Private six-role full-song outcome

The private excerpt evidence qualified synth and guitar for Studio research,
not for public registration. The exact full-song plan at SHA-256
`869ac229d5c95c9c3d5eb2c9eb38da368056f6fe3c644de9830cc593313efb7d`
was approved and consumed once. Its guarded execution retained objective
failure and no automatic retry. The replacement retained complete SCNet,
Mega-53 and guitar arrays, but no guitar worker result, guard counters or
peak-memory receipt.

An exact-hash-approved recovery reverified retained JSON, PCM24 and NPY under
network denial, performed the fixed grouped-other-constrained projection and
wrote 24 PCM24 review files. It loaded no checkpoint, constructed or loaded no
model, ran no inference or canonicalisation and started no model worker. The
report status is
`private_review_package_recovered_model_free_resource_gate_incomplete`.
`full_objective_qualification` is false; guitar and aggregate resource gates
are incomplete and supported-ceiling compliance is unknown.

The upstream package-barrel path that imports requests/urllib3 and performs a
caught IPv6 loopback `socket.bind` probe has been reproduced without a model.
Future workers avoid it through verified import order without weakening bind
denial. The absent historical guitar receipt means that mechanism is
consistent with the failure, not proven as its historical cause. A later model
run requires a new bounded plan and explicit authority; the consumed plan and
recovery are not retry permission.

## Private evidence IO and publication invariants

- New evidence roots, staging directories and published directories are
  owner-only mode `0700`. Retained legacy failed-package inner directories may
  be mode `0755`; their exact modes are bound and they remain immutable. Files
  are mode `0600`, owned by the current user, single-link, regular and
  size-bounded.
- Private execution processes set `umask 077` before staging. Coordinators and
  workers keep it for their process lifetime; recovery restores the prior mask
  in `finally`.
- Every directory component is opened using no-follow, directory and
  close-on-exec flags. Recovery binds approved directory and leaf
  device/inode/mode/owner/time/size facts rather than trusting a later path.
- Hashing plus PCM24 decode or `np.load(allow_pickle=False)` uses the same held
  leaf descriptor. The descriptor, visible leaf and every directory attachment
  are rechecked after consumption. The neutral WAV parser supports classic
  packed PCM24 and integer `WAVE_FORMAT_EXTENSIBLE` PCM24.
- Publication requires an exact fresh sibling, pins the parent identity, uses
  owner-only staging and performs an exclusive atomic no-replace rename. A
  raced destination becomes a retained recovery failure, never an overwrite.
- Both failed packages are cryptographically bound and left byte-preserved.
  Recovery remains inside OS network denial even though it imports no model.

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
  tests/test_separation_alpha.py \
  tests/test_private_atomic_directory.py \
  tests/test_private_verified_audio_inputs.py \
  tests/test_separation_fine_stem_full_song_plan.py \
  tests/test_separation_fine_stem_full_song_execution.py \
  tests/test_separation_fine_stem_full_song_recovery.py
```

These tests cover registry immutability, package/hash locks, read-only setup,
explicit terms approval, offline launch, exact role mapping, residual
accounting, report binding, review validation, objective rollout,
`WAVE_FORMAT_EXTENSIBLE` PCM24, descriptor and symlink races, owner-only
creation, guarded import order, model-free recovery and exclusive atomic
handoff. They use generated arrays and fake workers; they do not install or
load a model.

For the historical blocked MLX core-four baseline, no live activation artifact
exists: both attempts failed in private staging before publication, so no
human listen or song canary was reached. The exact
PyTorch fallback plan and offline CPU worker were then installed with the
revised 20-wheel closure and passed doctor. Its synthetic worker failed before
inference or publication because the loaded native segment is
`Fraction(39, 5)`, which the pinned contract rejects. Retries are disabled; see
[the fallback audit](CORE_FOUR_FALLBACK_AUDIT.md). Any future backend would
need a new reviewed plan and authority for the same finite synthetic, song and
resource sequence—not an unlimited search for unanimously positive listening
feedback. SCNet's public admission is already complete and is not waiting on
that future authority.
