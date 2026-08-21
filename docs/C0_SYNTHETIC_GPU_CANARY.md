# C0 synthetic RTX training canary

`c0-synthetic-tiny-overfit-001` is a technical training-pipeline check. It is
not a music model, a vocal selector or evidence that a learned representation
belongs in Sunofriend.

The request deterministically generates 256 non-private rows with 16 float32
features. Twelve composition-disjoint groups supply 192 training rows and four
different groups supply 64 held-out rows. The worker trains an exact
16→16→1 tanh MLP with AdamW, a fixed seed, batch size 32 and at most 200 steps
per arm. It retains:

- one uninterrupted clean run;
- a step-100 checkpoint and an exact resume to step 200;
- a deterministically shuffled-label control; and
- path-free hashes, metrics, checkpoint identities and resource receipts.

The technical gate requires clean held-out accuracy of at least 0.90, an
advantage of at least 0.20 over shuffled labels and model plus optimiser resume
equivalence within `1e-7`. Every loss, parameter and reported metric must be
finite.

## Boundaries

- Network access and downloads are denied. A network attempt stops the worker.
- The checked-out repository commit must exactly match the request and tracked
  files must be unchanged.
- There are no audio files, private paths, credentials or human labels.
- The maximums are 900 seconds, 4 GiB GPU allocation, 8 GiB process RAM,
  64 MiB output and zero retries.
- A result has technical-research-challenger authority only. It cannot select
  music, promote a checkpoint, change the product or justify paid compute.

The newer vocal-pairwise canary retains compatibility with its completed
legacy evidence but gives every new execution a one-attempt identity. A
pretraining failure may be linked only through a hash-bound path-free receipt
which records zero training, outputs, network, downloads and automatic
retries. The receipt itself grants no new execution. A separately reviewed
request embeds a fresh attempt ID and the complete prior-failure receipt while
continuing to declare one maximum training execution and zero retries. See
[`VOCAL_PAIRWISE_TRAINING.md`](VOCAL_PAIRWISE_TRAINING.md) for the exact
recorder, request, runner and verifier commands.

## Exact Windows result — 20 August 2026

The hardened worker at repository commit
`c427b3ab0ac8f2d42d6a87e29a29cdc8dba3f8f0` completed one authorised run on
the Windows RTX 4080 Laptop GPU. No retry, download, private audio or network
access was used.

- request document SHA-256:
  `ad68e25e53cd649bd076e5599537f1e9073b6ab968a8583a0b0d6579cde0a676`;
- result document SHA-256:
  `9264c0151d0adee587e71147a77eb211e7e6b61a9bfe40e81c4dc52d5d95b05e`;
- clean and resumed held-out accuracy: `1.0`; shuffled-label accuracy: `0.5`;
- clean-minus-shuffled advantage: `0.5`;
- resumed-versus-uninterrupted maximum parameter and optimiser difference:
  `0.0` at tolerance `1e-7`;
- 200 clean steps, resume from step 100 to global step 200, and 200 shuffled
  steps completed;
- wall time `21.68800000002375` seconds, peak GPU allocation `68,222,976`
  bytes, peak process RAM `1,113,731,072` bytes and output `42,823` bytes;
- zero network attempts, zero downloads, zero retries and no warnings.

This proves only the bounded synthetic loader, split, optimisation,
checkpoint/resume, control and evidence pipeline. It does not train a music
model, admit a representation, select a vocal or authorise real-data training.
The returned artifact set subsequently passed the read-only round-trip
verifier from commit `ad5adc76c2986d1ab2a1db10b62a41d537df87fd` without
rerunning training or loading a checkpoint. The path-free verification receipt
has document SHA-256
`e1fef9064ed47dc2c6bdeb8ae1ffcaf245448e15c412af8d813cbc467d2715fc`;
all artifact byte counts and hashes, the clean exact-commit checkout, resource
ceilings, offline evidence and technical-only authority passed.

## Windows worker commands

Run these from a clean checkout after the intended commit has been pushed and
checked out on the RTX machine. Use the already approved Python/PyTorch CUDA
environment; these commands install and download nothing.

```powershell
$env:PYTHONPATH = "src"
$commit = (git rev-parse HEAD).Trim()
python scripts/create-gpu-canary-request.py `
  --repository-commit $commit `
  --out C:\sunofriend-c0\c0-request.json

python scripts/run-gpu-canary.py `
  C:\sunofriend-c0\c0-request.json `
  --out-dir C:\sunofriend-c0\c0-result
```

The request and result JSON are portable and path-free. The local request path,
output directory and checkpoint files remain execution details on the worker.
Use a fresh output directory; an existing destination is rejected rather than
overwritten or retried.

## Verify before returning evidence

Remain on the exact clean commit used to create the request. The verifier is
read-only: it does not start training, import a checkpoint, install or download
anything, contact a network service or write a verification file. It validates
the exact C0 request/result binding, repository commit and tracked files, the
five-output roster/kinds/media types/shapes, every local artifact byte count and
SHA-256, finite/resource evidence and the zero-network/zero-retry declarations.

```powershell
$env:PYTHONPATH = "src"
$verificationJson = (& python scripts/verify-gpu-canary-round-trip.py `
  C:\sunofriend-c0\c0-request.json `
  --artifact-dir C:\sunofriend-c0\c0-result | Out-String)
if ($LASTEXITCODE -ne 0) {
  throw "C0 evidence verification failed; do not return or retry the run."
}
$verification = $verificationJson | ConvertFrom-Json
if ($verification.status -ne "verified_technical_evidence_only") {
  throw "C0 evidence did not receive technical-only verification."
}
$verificationJson
```

By default, the verifier checks the repository containing the verifier. For an
earlier completed run whose exact commit is preserved in a separate clean
checkout, run the newer verifier code while explicitly pointing the read-only
commit check at that preserved checkout:

```powershell
$verificationJson = (& python scripts/verify-gpu-canary-round-trip.py `
  C:\sunofriend-c0\c0-request.json `
  --artifact-dir C:\sunofriend-c0\c0-result `
  --repository-root C:\path\to\preserved-c427b3a-checkout | Out-String)
```

`--repository-root` changes only which checkout supplies `HEAD` and tracked-file
evidence. It does not relax the exact request commit, clean-worktree, artifact or
authority checks, and its local value is never written into the receipt.

The printed verification receipt contains hashes, byte counts and fixed output
IDs, but no local paths. Saving that already-produced stdout is optional and is
separate from the read-only verifier:

```powershell
$returnDir = "C:\sunofriend-c0\c0-return"
if (Test-Path $returnDir) {
  throw "Return directory already exists; do not overwrite it."
}
New-Item -ItemType Directory -Path $returnDir | Out-Null
$verificationJson | Set-Content `
  -Path "$returnDir\c0-verification.json" -Encoding utf8
Copy-Item "C:\sunofriend-c0\c0-request.json" $returnDir
Copy-Item "C:\sunofriend-c0\c0-result\gpu-worker-result.json" $returnDir
Copy-Item "C:\sunofriend-c0\c0-result\metrics.json" $returnDir
Copy-Item "C:\sunofriend-c0\c0-result\checkpoint-step-100.pt" $returnDir
Copy-Item "C:\sunofriend-c0\c0-result\checkpoint-final-uninterrupted.pt" $returnDir
Copy-Item "C:\sunofriend-c0\c0-result\checkpoint-final-resumed.pt" $returnDir
Copy-Item "C:\sunofriend-c0\c0-result\checkpoint-final-shuffled.pt" $returnDir
Get-ChildItem $returnDir | Select-Object Name, Length
```

Return those eight fixed-name files together. Do not add logs, screenshots,
machine paths, private notes, credentials or music. On the receiving machine,
check out the same commit with unchanged tracked files and run the same verifier
against the returned request and artifact directory. Verification grants only
technical evidence that this bounded synthetic pipeline ran as declared. It
does not admit a representation, promote a checkpoint, select music, change the
product or authorise any private-data training.
