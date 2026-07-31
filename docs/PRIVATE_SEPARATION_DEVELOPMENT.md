# Private stem-separation development

Sunofriend has started running a real local separator. This page describes the
developer-only bake-off, not a finished-song feature.

## Current result

The first real run completed on 31 July 2026 with the already-installed
Demucs 4.0.1 `htdemucs` checkpoint. One model application produced four broad
estimated stems:

- bass;
- drums;
- other; and
- vocals.

The input was Sunofriend's eight-second copyright-safe synthetic demo. It
contains fixed mathematical waveforms and deterministic noise, with no
recordings, samples, lyrics or third-party audio. Exact references are:

- drums = kick + snare + hat;
- bass = bass;
- other = keys + lead; and
- vocals = digital silence.

The hardened private run took 8.00 seconds in the parent report, including
6.82 seconds of model inference. The worker reported about 2.10 GB maximum
resident memory on this Mac. Geometry remained exactly 44.1 kHz stereo and
352,800 frames. No stem clipped.

Initial ground-truth observations were:

| Role | SI-SDR | Level difference | 10 ms envelope correlation | Lag/drift |
| --- | ---: | ---: | ---: | ---: |
| bass | 19.75 dB | +0.06 dB | 0.957 | 0 ms / 0 ms |
| drums | 4.13 dB | -2.22 dB | 0.910 | 0 ms / 0 ms |
| other | 14.01 dB | +0.14 dB | 0.959 | 0 ms / 0 ms |

The deliberately silent vocal reference produced a small false-positive
estimate at -62.95 dBFS, or -47.81 dB relative to the mixture. These are
observations from one synthetic fixture, not promotion thresholds or proof
of quality on real songs.

The four model outputs differed additively from the source by -24.87 dB RMS.
Sunofriend separately persisted `source - estimated sum`; the float64 sum of
the four re-read persisted stem WAV arrays plus that accounting remainder
reconstructed the PCM source exactly in this run. The separately written sum
WAV is only an audition rendering and is not used for closure because PCM
clipping could hide oversummed samples. This proves arithmetic accounting
only. It does not prove that a model assigned sounds to the correct stems.

## Repeat the canary

This command uses only an existing local runtime and checkpoint. Every output
path must be fresh.

```bash
.venv/bin/python scripts/private-demucs-four-stem-canary.py \
  --fixture-out work/separation-bakeoff/demo-fixture-v2 \
  --run-out work/separation-bakeoff/demo-run-v2 \
  --evaluation-out work/separation-bakeoff/demo-evaluation-v2 \
  --checkpoint ~/.local/share/sunofriend/models/demucs-4.0.1-htdemucs/955717e8-8726e21a.th \
  --python .venv-ai/bin/python
```

The command never installs or downloads a model. It rejects a checkpoint
whose SHA-256 is not
`8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4`.

## Evidence produced

The private run keeps:

- the exact PCM24 source excerpt;
- one float32 model array and PCM24 estimated WAV per broad role;
- the model stem sum and source-minus-sum accounting remainder;
- request, worker-result, stdout and stderr evidence;
- source, request-bound excerpt, checkpoint, worker and resolved
  runtime-launcher identities and hashes;
- geometry, clipping, energy, reconstruction and resource observations; and
- a self-hashed, review-required experiment report.

The separate synthetic evaluation revalidates both reports and every stem
hash before computing SI-SDR, level error, envelope lag, quarter-to-quarter
drift, silent-vocal leakage and energy ratios.

## Deliberate boundary

This private experiment:

- is not imported by CLI, TUI, Simple or Workbench;
- does not use or weaken the fake-only public separation runner;
- creates no source-graph node or active candidate;
- makes no automatic selection, acceptance or promotion;
- does not prove network denial, attempted-connection observation,
  outside-write confinement or complete descendant supervision; and
- keeps the checkpoint under Sunofriend's private-evaluation-only policy
  because separate official weight terms have not been established.

`REAL_SEPARATION_BACKENDS_SUPPORTED` and
`CHECKPOINT_DESCRIPTOR_LEASE_EXECUTION_SUPPORTED` remain `False`.

## Next evidence

The next bounded development increment is a downstream MIDI comparison:

1. transcribe each exact clean reference and matching estimated stem with
   identical production settings;
2. compare note/onset coverage, pitch, octave, duration and drift;
3. test drum-family onsets separately;
4. retain all candidates without activating the source graph; and
5. repeat on authorised real excerpts before considering a Studio importer.

Public Studio finished-song separation remains Phase S4. One-action Simple
separation remains Phase S6 and requires cross-song, licence, offline,
resource, downstream-MIDI and human listening acceptance.
