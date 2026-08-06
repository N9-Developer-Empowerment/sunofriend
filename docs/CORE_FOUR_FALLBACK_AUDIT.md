# Core-four fallback audit

## Decision

`demucs-mlx-htdemucs-v1` exhausted the permitted baseline configuration and
single remediation cycle before publishing any synthetic output. Further
retries of that profile are disabled. The first fallback candidate is
[`demucs-infer`](https://github.com/openmirlab/demucs-infer/tree/4b79d5c756ce298503d90b0cca2abbc76c565416)
with the single `htdemucs` model. Its worker and exact setup plan are now
implemented and the approved revised runtime is installed locally. Exact
receipt and doctor checks pass, but the profile is **not executable**.

The first approved installation attempt on 2026-08-06 failed safely because
Torch's package metadata required an additional `setuptools` wheel that was
not in the 19-wheel hash lock. Hash-locked pip stopped before publication and
the atomic staging directory was removed. The revised no-write plan pins that
wheel too. The revised approved install then succeeded atomically with all 20
packages and six retained artifacts verified.

The first synthetic activation attempt failed before inference or publication.
The installed model exposes its native segment as `Fraction(39, 5)`, while the
pinned fallback worker accepts only built-in `int` or `float` values. A
network-denied read-only classification confirmed the single model bag, exact
four roles, stereo 44.1 kHz clock and the `Fraction(39, 5)` value. No stem or
review output was published and no human listen was reached.

## Baseline failure retained

The exact `demucs-mlx==1.4.4` install passed package, artifact, terms, platform
and offline doctor checks. Its first synthetic run then failed because the
pinned model config stores segment as the string `"39/5"`; the runtime repeated
that string while converting a segment length to an integer. The one permitted
remediation parsed it as numeric `7.8` at the `apply_model` boundary. The second
run failed earlier inside the loaded HTDemucs model's `valid_length`, where the
unchanged model field was still the string.

Both failures occurred inside private staging before atomic publication. No
stem, review page or listening result was published, and no private song was
processed. This is an objective runtime failure, not poor musical feedback.

## Candidate evidence captured on 2026-08-06

| Item | Static identity |
| --- | --- |
| Package | `demucs-infer==4.2.2` |
| Source revision / PyPI attestation | `4b79d5c756ce298503d90b0cca2abbc76c565416` |
| Wheel | `demucs_infer-4.2.2-py3-none-any.whl`, 87,489 bytes |
| Wheel SHA-256 | `df07b115690021dcfa6b2a6de1b7b352741111bc46fad31ca83eaaba6afced8b` |
| Source licence | MIT; retained source hash `761f67137c6e733d551b8ed1111e48e267e032c2c0fb0df07127cf55ddbeef5b` |
| Model name | single `htdemucs`, not the four-model `htdemucs_ft` ensemble |
| Model bag config | `models: ['955717e8']`, SHA-256 `239c445d0b14454d541ad8bd9bb271c9e536d267e8a4625208744cbb2e7bb66c` |
| Model checkpoint | `955717e8-8726e21a.th`, 84,141,911 bytes |
| Model SHA-256 | `8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4` |
| Checkpoint provenance document | SHA-256 `e209056d816cdc8f91be9cfdf9c1883aec9e34f739fc4278de2ebb60d58e5b75` |
| Model roles / clock | drums, bass, other, vocals; stereo 44.1 kHz |
| Runtime closure | 20 exact Apple-arm64/Python 3.13 wheels |
| PyTorch pair | `torch==2.8.0`, `torchaudio==2.8.0` |
| Added setup dependency | `setuptools==83.0.0`, MIT, wheel SHA-256 `29b23c360f22f414dc7336bb39178cc7bcbf6021ed2733cde173f09dba19abb3` |
| Runtime wheel download total | 99,430,373 bytes |
| Model plus runtime download total | 183,572,284 bytes |

The initial safe setup failure consumed the fallback's one permitted
remediation. The revised installation succeeded, but the subsequent objective
synthetic failure means new installs and activation retries are now disabled.
The installed profile is retained only for local integrity evidence and
read-only doctor checks.

The pinned package's
[`pretrained.py`](https://github.com/openmirlab/demucs-infer/blob/4b79d5c756ce298503d90b0cca2abbc76c565416/demucs_infer/pretrained.py)
and
[`repo.py`](https://github.com/openmirlab/demucs-infer/blob/4b79d5c756ce298503d90b0cca2abbc76c565416/demucs_infer/repo.py)
support an explicit local repository. When `repo` is supplied,
the source selects `LocalRepo`, validates the checksum prefix embedded in the
checkpoint filename and does not take its normal remote or Google Drive
fallback. Sunofriend still needs full SHA-256 verification during setup and
must launch inference under network denial.

One deterministic shift requires seeding Python's `random` module immediately
before `apply_model`; seeding only PyTorch is insufficient. The candidate's
own source also documents that passing an explicit segment can fail for
HTDemucs. The worker left the `segment` argument unset as planned, but its
strict validation rejected the loaded `fractions.Fraction` representation.
Accepting another numeric representation would be a further code remediation,
so it is not being attempted after the bounded budget was exhausted.

The repository and package declare MIT terms and describe the official model
weights as unchanged. No separate model-specific checkpoint licence file was
located, and no contradictory use restriction was found. The exact setup plan
discloses that limitation rather than waiting indefinitely for a bespoke
letter or silently presenting stronger evidence than exists.

## Objective fallback failure

- Failure ID: `demucs-infer-native-fraction-segment-contract-v1`.
- The exact installation and read-only doctor pass, including local artifacts,
  terms receipt and network-denial capability.
- The synthetic worker fails before inference because the native segment is
  `Fraction(39, 5)`, not a built-in `int` or `float`.
- Atomic publication withheld the destination and removed private staging.
- This is a reproducible objective execution failure, not poor listening
  feedback and not a separation-quality rating.
- The 16 GiB resource repeats and authorised-song canaries were not reached.

## Next bounded action

The no-write plan now records the failure and refuses new installs:

```bash
scripts/setup-separation-core-four-fallback-macos.sh --plan
```

Do not reinstall, relax the segment contract or rerun this profile. The next
bounded action is to select and statically review a different backend under a
new explicit plan. That is a new model/runtime decision, not authority to begin
an open-ended candidate search or install anything.

The Spleeter control was also checked without installation. Its current pinned
package requires `tensorflow==2.12.1`, for which the official resolver found no
Python 3.11 Apple-arm64 wheel. It therefore remains a later control and does
not delay this fallback qualification.
