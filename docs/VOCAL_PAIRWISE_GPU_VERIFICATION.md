# Vocal pairwise CUDA round-trip verification

The vocal pairwise CUDA canary is synthetic technical evidence only. Its
round-trip verifier does not train, download, contact a network service, read
audio, consume a human label, select a vocal source or promote a checkpoint.

The verifier requires one exact clean repository commit and exactly these six
files in the returned artifact directory:

- `gpu-worker-result.json`;
- `metrics.json`;
- `checkpoint-step-120.pt`;
- `checkpoint-final-uninterrupted.pt`;
- `checkpoint-final-resumed.pt`; and
- `checkpoint-final-shuffled.pt`.

It rejects missing, extra, symlinked, changed or hash/size-mismatched files. It
also checks the fixed path-free request, exact result binding, tracked Git
state, output kinds/media types/shapes, resource ceilings, deterministic CUDA
configuration, zero network attempts, zero downloads and zero retries.

Each checkpoint is opened read-only with
`torch.load(weights_only=True, map_location="cpu")`. The verifier checks the
request hash, dataset hash, repository commit, experiment ID, synthetic-only
flag and exact step without trusting a local path stored by the worker. It then
independently recomputes clean, resumed and shuffled held-out accuracies from
the checkpoint weights, compares uninterrupted and resumed model/optimiser
state, requires finite evidence and reproduces the three fixed acceptance
tests. The metrics and result must match that checkpoint-derived evidence.

## Run on the exact Windows checkout

Use the already approved Python/PyTorch CUDA environment. These commands
install and download nothing. Create and run the request only once, in a fresh
output directory, following `VOCAL_PAIRWISE_TRAINING.md`. Then remain on the
same clean commit and verify the returned files:

```powershell
$env:PYTHONPATH = "src"
$verificationJson = (& python scripts/verify-vocal-pairwise-gpu-canary.py `
  C:\sunofriend-vocal-pairwise\request.json `
  --artifact-dir C:\sunofriend-vocal-pairwise\result | Out-String)
if ($LASTEXITCODE -ne 0) {
  throw "Vocal pairwise evidence verification failed; do not retry the run."
}
$verification = $verificationJson | ConvertFrom-Json
if ($verification.status -ne "verified_synthetic_technical_evidence_only") {
  throw "Vocal pairwise evidence did not receive technical-only verification."
}
$verificationJson
```

For an earlier run, a separately preserved checkout may be supplied with
`--repository-root`. That changes only the local checkout used for the exact
commit and tracked-file checks; it relaxes no request, artifact, metric,
checkpoint or authority gate, and the local path is not included in the
printed receipt.

The printed JSON is path-free and may be saved separately. Its authority ends
at verification of this bounded synthetic pipeline. It does not show that a
ranker works on real singing, authorise private-data training, choose a take or
change Sunofriend's product behaviour.
