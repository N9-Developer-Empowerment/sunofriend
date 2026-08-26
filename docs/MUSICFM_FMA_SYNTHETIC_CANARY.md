# MusicFM-FMA synthetic frozen-feature canary

Status: hermetic runtime boundary implemented; retained Windows result
qualified; private-audio extraction and real training remain gated.

## Visible behaviour and evidence contract

The canary accepts one exact path-free request bound to:

- a full Sunofriend commit;
- the byte count and SHA-256 of an existing isolated Windows setup receipt;
- the pinned 1,316,802,154-byte MusicFM-FMA checkpoint;
- a generated two-second mono 24 kHz signal; and
- one CUDA execution with no retry, network or download.

The private loader constructs the pinned local architecture from the retained
configuration and source files. It uses `torch.load(..., weights_only=True,
map_location="cpu")`, applies only the exact legacy weight-normalisation rename
and BatchNorm bookkeeping-counter cast seen in the pinned checkpoint, requires
strict state key/shape/dtype equality, freezes the model and extracts layer 7
twice. A qualified result is two byte-identical `[1, 50, 1024]` float32 arrays
at 25 Hz plus path-free loader, environment and artifact evidence.

The independent verifier never imports Torch or model code. It checks the
complete output roster, JSON identities, artifact sizes and hashes, array
shape/dtype/finiteness/equality and metrics agreement.

## Errors and side effects

The run fails before publication for a changed request, setup receipt, runtime
asset, checkpoint identity, model state, environment, feature geometry,
repeatability or any network attempt. Output is written to a fresh directory
outside the isolated runtime and published atomically. The runtime is read
only; no private audio is opened and no weights are changed.

## Windows handoff

These commands are for the already-prepared isolated Windows runtime. They do
not grant fresh authority to install, download, open private audio or train.

```powershell
$Commit = git rev-parse HEAD
python scripts/create-remix-musicfm-synthetic-canary-request.py `
  C:\ABSOLUTE\MUSICFM-RUNTIME\setup-receipt.json `
  --repository-commit $Commit `
  --out C:\ABSOLUTE\CANARY\request.json

python scripts/run-remix-musicfm-synthetic-canary.py `
  C:\ABSOLUTE\CANARY\request.json `
  --runtime-root C:\ABSOLUTE\MUSICFM-RUNTIME `
  --out-dir C:\ABSOLUTE\CANARY\result

python scripts/verify-remix-musicfm-synthetic-canary.py `
  C:\ABSOLUTE\CANARY\request.json `
  C:\ABSOLUTE\CANARY\result
```

## What this clears and what remains

The canary clears only these technical questions for the exact qualified
runtime:

- the restricted loader can reconstruct the pinned checkpoint;
- layer 7 exposes a 25 Hz, 1,024-dimensional frozen representation;
- the exact synthetic input is repeatable; and
- retained feature evidence can be independently verified.

It does not clear:

- owner authorization to open private song audio with the extractor;
- a real controlled-variant and pairwise-label corpus;
- composition-disjoint snapshot sufficiency;
- a real feature manifest bound to every labelled variant;
- a real training execution request;
- held-out superiority over deterministic and shuffled controls; or
- checkpoint promotion or product audition ordering.

The next deterministic implementation is an admission artifact joining this
canary evidence to one exact `remix_musicfm_feature_plan` without changing its
historical v0 bytes. It may mark the runtime and synthetic clock as evidenced,
but must still leave owner-audio extraction and training authority false. The
next human work is to create and review controlled remix comparisons; GPU time
cannot substitute for those labels.

## Deep-module review

1. The private loader owns Torch, Transformers, pinned architecture,
   compatibility migration, offline guarding and synthetic signal knowledge.
2. Callers do not know module imports, state-key rewrites, tensor construction,
   deterministic CUDA settings or feature extraction mechanics.
3. The common execution is one typed loader operation behind a small canary
   facade; request creation and independent verification remain separate
   authority boundaries.
4. Fresh-output, read-only-runtime, network, CUDA, exact-repeat and publication
   rules are explicit.
5. Loader mechanics can change without changing the request/result schemas so
   long as the exact evidence contract remains true.
6. The split removes framework policy from scripts and prevents each caller
   from rebuilding a subtly different MusicFM loader.
