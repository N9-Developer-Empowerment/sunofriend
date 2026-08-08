# Public core-four stem preview

Sunofriend's full-stem baseline means four broad, synchronized estimates:

- `vocals.wav`;
- `drums.wav`;
- `bass.wav`; and
- `other.wav`, a grouped remainder rather than a single instrument.

Guitar, broad keyboard/synth and drum-family splitting remain later
milestones. Acoustic piano alone is not treated as a sufficient keyboard
capability.

## Current state

The public coordinator is implemented. The immutable MLX baseline remains
`blocked`: its baseline run and single permitted remediation both failed an
objective runtime gate before publication. Further MLX activation retries and
new installs are disabled. The existing two-stem route remains the default.
The first pinned
`demucs-infer` fallback also exhausted its bounded remediation and failed
before synthetic publication. The separately pinned SCNet-large release
profile is installed and admitted as `public_opt_in`: a network-denied
synthetic canary, three authorised full-song canaries and three repeat resource
runs passed the objective gates, and every full-song result received the
required no-catastrophic-defect listening check.

Inspect the exact current state without loading a model:

```bash
.venv/bin/sunofriend-separate profiles
.venv/bin/sunofriend-separate profiles --json
scripts/setup-separation-core-four-macos.sh --plan
```

The public opt-in command is:

```bash
.venv/bin/sunofriend-separate separate SONG \
  --scope core-four-stems-v1 \
  --out FRESH \
  --rights-category owned
```

Planning remains read-only. Execution additionally requires
`--execute --confirm-rights`; it never starts MIDI conversion.

## Detailed separation after core four

The first bounded follow-on is now an opt-in Studio route.
`other-refinement-v1` binds one exact grouped-`other` artifact to one requested
guitar or keys target plus the exact residual. It is registered as a
`studio_challenger`, separate from the ordinary separation-scope choices. Its
first contract accepts only an `other` parent produced by the verified
`scnet-large-musdb-release-v1` profile and never activates output or MIDI.

The first exact challenger plan is
`demucs-mlx-htdemucs-6s-other-refinement-v1`: a pinned Apple-native six-source
MLX model with guitar plus a disclosed piano-as-keys proxy. The 109,726,583-byte
checkpoint and 1,946-byte config are hash-pinned and installed only through the
separate approved setup. The one allowed in-memory `"39/5"` normalization
passed under network denial, followed by a synthetic canary and both target
mappings on an authorised full-song parent. See
[Six-source MLX Studio-challenger audit](OTHER_REFINEMENT_DEMUCS_MLX_AUDIT.md).

The deterministic PCM24 fixture proves the target/residual accounting without
downloading or running a model:

```bash
.venv/bin/python scripts/run-other-refinement-synthetic.py \
  --target guitar --out FRESH
```

Run a read-only plan with
`sunofriend-separate refine-other CORE_FOUR_ROOT --target guitar --out FRESH`;
execution additionally requires `--execute --confirm-rights`. The existing
source graph prevents the grouped parent and its refined children from being
active together. Mixed or negative musical feedback remains evidence and
cannot disable the functioning public core-four profile. See
[Refining grouped other in Studio](OTHER_STEM_REFINEMENT.md).

The completed five-song, ten-report round demonstrated neither useful guitar
extraction nor successful piano extraction. That bounded result ends tuning of
the six-source candidate. The next proposed Studio experiment is the
unregistered, non-executable Banquet query challenger for guitar and broad
`keyboard_synth`. Its exact runtime, network-denied strict checkpoint load and
single generated-tensor synthetic forward pass. A later explicitly approved
nine-case, song-disjoint reference canary also passed its offline runtime,
hash, resource and zero-LSB reconstruction gates. Its completed bound review
rated eight targets not useful and one quiet keyboard target partly useful, so
the challenger is technically valid but musically unsuccessful. It remains
unregistered and selects no source or MIDI. See
[Guitar and keyboard/synth query-challenger plan](OTHER_REFINEMENT_QUERY_CHALLENGER_PLAN.md).

Completed refinement feedback is sealed separately with
`sunofriend-separate review-other RESULT_ROOT REVIEW_JSON --out FRESH.json`.
That validator rechecks the immutable PCM24 result, preserves negative and
legacy-page evidence honestly, and grants no activation or promotion.

## Immutable baseline

| Identity | Pinned value |
| --- | --- |
| Profile | `demucs-mlx-htdemucs-v1` |
| Runtime | `demucs-mlx==1.4.4` |
| Runtime source | `b37e6ba3c5985af531f61c43564cf13c6ed349fd` |
| Runtime wheel SHA-256 | `dc40828b0a8591720082d2494696249790573d4ff6e5be72b16594e131b23e64` |
| Model repository | `mlx-community/demucs-mlx` |
| Model revision | `d4519e24ddc2dd4a11d56a193092433d852c3961` |
| Weights SHA-256 | `339d267a7a6983a11eedbdc00413c602a65e9b9103f695fb5c2b2a481cd9d297` |
| Config SHA-256 | `9258499513944fc062fbca0f11be425a446ec5702869a87e225323d7a57d2a01` |
| Model roles | `drums`, `bass`, `other`, `vocals` |
| Fixed inference | `htdemucs`, one shift, seed `0`, overlap `0.25`, batch size `1`, one writer, pinned `39/5`-second segment parsed as `7.8` seconds |

The setup retains the pinned runtime MIT licence, source metadata and model
card. Those exact records, revisions and hashes are sufficient preview terms
evidence unless static inspection finds a contradiction. A bespoke permission
letter is not an open-ended release dependency.

Every runtime dependency is version- and hash-pinned, including
`safetensors`. The approved installer prefetches and verifies the explicit
local model cache. Inference calls the local loader with `auto_convert=False`,
contains no PyTorch, and runs under macOS network denial. No mutable name or
first-run download may resolve a model.

## Output and accounting contract

The worker accepts only stereo 44.1 kHz PCM24 WAV. It rejects missing or extra
model roles, clock changes, non-finite values, all-role silence and peaks beyond
the declared bound.

The native vocal, drum and bass estimates are retained. The model's native
reconstruction residual is added transparently to grouped `other`. One shared
attenuation is applied if necessary. PCM24 `other` is then constructed as the
exact complement of persisted vocals, drums and bass, so the four persisted
stems reconstruct the level-managed reference within two PCM24 least-significant
bits. The report records the native-other correction RMS and peak. That metric
explains accounting; it is not a separation-accuracy score.

Outputs are written to a fresh staging directory, verified by role, size and
SHA-256, then published atomically. Useful stems enter Create or Studio only
after a separate explicit user decision.

## Bounded preview admission

Preview admission uses objective safety and execution evidence. For the
selected SCNet profile, the completed admission ran exactly:

1. one copyright-safe synthetic four-role demo;
2. three authorised, song-disjoint complete songs covering vocal-forward,
   dense/electronic and acoustic-or-mixed material; and
3. three repeat resource runs on the approved first verified 36 GB M3 Max
   Apple-silicon class.

Each canary needs one complete internal listen only to catch mislabelling,
corruption, silence across all roles or gross timing errors. No minimum
“useful” rating exists. Pre-release work is limited to one baseline
configuration and one remediation cycle. If an objective gate still fails,
switch to the fallback backend rather than starting another tuning loop.

The first installed synthetic attempt exposed that upstream loaded the pinned
config's `"39/5"` segment as a string and later repeated that string during
multiplication. The one permitted remediation parses the unchanged fraction as
exactly `7.8` seconds before inference. It changes no model, weights, overlap,
shift, seed, batch or writer setting. The remediated run then failed inside the
loaded HTDemucs model's own `valid_length`, where the model's segment remained
the string. That exhausted the finite budget and selected the fallback-backend
path. Both attempts failed in staging; no synthetic output was published and
no listening gate was reached.

Resource limits are unchanged:

- at most 120 seconds per audio minute;
- at most 900 seconds per song; and
- at most 12 GiB peak unified memory on the verified machine class.

Other Apple-silicon classes remain accessible but unverified: doctor warns and
resource supervision remains active.

Only these conditions pause a profile: licence/hash contradiction, inference
network access, source mutation or privacy breach, corrupt or missing roles,
non-finite audio, clock mismatch, failed reconstruction accounting, or a
reproducible crash/OOM on a declared supported machine.

## Feedback without a doom loop

The local review is bound to the exact scope, profile and report hash. It asks
for overall and per-role usefulness, bleed, missing content, artefacts, timing,
join problems and downstream MIDI outcome. `cannot_tell` and `not_tested` are
valid. “Copy text-only feedback” omits the source filename, private notes,
telemetry and audio; nothing is uploaded automatically.

Review accumulated feedback after 30 days or 10 valid reports, whichever
comes first. Development continues if ten reports never arrive. Repeated poor
musical feedback keeps the last functioning baseline accessible, adds a known
limitation and triggers one bounded challenger experiment. Demotion to
Studio-only is permitted only after another objectively qualified baseline
exists.

## Challenger lane

`demucs-infer` is now the first fallback candidate because the MLX baseline
objectively failed. Its exact Apple-arm64/Python 3.13 dependency closure,
single checkpoint, local-repository loader and CPU worker are pinned. Its first
approved setup stopped safely because the 19-wheel lock omitted Torch's
`setuptools` dependency. The revised 20-wheel install passed exact receipt and
doctor checks, but the synthetic worker rejected the loaded native
`Fraction(39, 5)` segment before inference or publication. That exhausted the
fallback remediation; new installs and retries are disabled. See
[Core-four fallback audit](CORE_FOUR_FALLBACK_AUDIT.md). A future bounded
compare command may run only explicitly named, already-installed profiles into
separate candidate roots and must never record a winner automatically.
Spleeter is a later independent control and cannot delay the fallback.

## Next bounded action

The historical MLX setup plan now reports the objective failure and refuses
new installs:

```bash
scripts/setup-separation-core-four-macos.sh --plan
```

Review the `demucs-infer` fallback's retained no-write failure plan:

```bash
scripts/setup-separation-core-four-fallback-macos.sh --plan
```

It names and hashes every dependency and model artifact, retains terms
evidence, and now refuses new installs. Do not patch or rerun either failed
profile. Official SCNet-large is now the installed public opt-in profile. An
approved evidence-only download established its exact 168,848,417-byte,
SHA-256-pinned identity under accepted provisional terms evidence; see
[the SCNet audit](CORE_FOUR_SCNET_AUDIT.md). The exact 12-wheel runtime and
release source are installed. Weights-only compatibility passed after the one
allowed official-wrapper remediation, and the fixed worker produced all four
roles in 69.97 seconds at 6.58 GB peak RSS with zero-LSB reconstruction error
on the current 36 GB M3 Max. Reference diagnostics found very weak synthetic
vocal output with much of that reference in grouped other; this is recorded as
a usefulness limitation and does not restart tuning or reverse the technical
pass. See [the approval ledger](CORE_FOUR_MODEL_APPROVALS.md). Admission gates
are complete. Accumulated usefulness feedback now informs limitations and one
bounded challenger; it does not disable the functioning preview.
