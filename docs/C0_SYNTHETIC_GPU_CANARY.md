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
