# Phase 1 AI Transcription Bake-off — close-out report

This report is the stable decision record for Phase 1. Private audio and the
large immutable run artifacts remain under `work/ai-bakeoff/`; they are not
published with the repository. The commands, schemas, checkpoint hashes and
licence boundaries needed to reproduce those runs are part of Sunofriend.

## Current close-out state

**Phase 1 is complete.** All engineering, automated evaluation, optional
experiments and required human listening are closed. The reviewed export was
completed on 23 July 2026 and retained privately at
`work/ai-bakeoff/sunofriend-phase1-listening-review.json`; its SHA-256 is
`b70863f5b64a6bea9e47c2187c8965780eeb0b7be2bddf92ef682017f72be75f`.
It uses `sunofriend.phase1-listening-review.v1`, has all three required rows
complete, contains all 46 required scores in the 1–5 range and has valid
explicit choices. Free-text review notes remain private and are not reproduced
in this report.

The user's existing lead-vocal verdict is already recorded: MuScriptor MIDI is
substantially better than the Sunofriend baseline on the Lidl 30–45 second
golden.

## Backend decisions

| Backend | Evidence | Decision |
| --- | --- | --- |
| Sunofriend / Basic Pitch / pYIN | Stable baseline; specialised stem repair; raw vocal evidence | **Integrate and always retain.** This remains the normal workflow and independent fallback. |
| MuScriptor small | Lead, backing, bass, keys, kick, strings, unrestricted full mix and silence | **Integrate as the preferred opt-in lead challenger and, on this private golden, the preferred bass and backing-dominant challenger.** Keep the deterministic backing harmony stack as the separate harmony representation and keep keys as an optional A/B. Do not generalise one golden into automatic role promotion. Reject automatic unrestricted-full-mix promotion; retain the existing specialised kick and strings paths. |
| GAME 1.0.3 small ONNX | Seeded lead, backing and silence runs | **Retain as an opt-in monophonic vocal challenger and boundary oracle.** Never replace backing harmony or merge automatically. |
| RMVPE 0.2.3 ONNX | Lead, backing and silence frame evidence | **Retain as an independent F0/alternate-voice oracle.** Do not use its decoded MIDI as the primary note-boundary source. |
| PESTO 2.0.1 `mir-1k_g7` | Repeated lead run, backing, bass and silence; raw F0 frames and activation matrix retained | **Retain as an optional independent F0 oracle for vocals. Reject for bass on the current golden.** Do not add it to consensus until a reviewed phrase demonstrates value beyond pYIN/RMVPE. |
| MT3 | Official repository/runtime assessment | **Reject for Phase 1.** The official inference path still depends on the large T5X/Colab environment, while MuScriptor already supplies the required MT3-style multi-instrument event comparison through the common contract. Revisit only if a maintained local checkpoint/runtime offers a material accuracy advantage. |

The MuScriptor checkpoint is optional and CC-BY-NC-4.0; it cannot become a
required or commercial Sunofriend dependency. PESTO is LGPL-3.0 and remains
isolated in the optional worker. Core Sunofriend remains Apache-2.0.

## Optional PESTO experiment

PESTO uses the pinned 534,664-byte `mir-1k_g7.ckpt`, SHA-256
`16c32e06ddd950e3e4866dfa3c7f8a87c4988f8adf43e57977b189f031f26f3e`.
CPU inference took 2.1–3.3 seconds per 15-second clip. A repeat lead run
produced byte-identical candidate JSON, MIDI, frame JSON and raw activation
matrix.

| Golden | Notes | Strong onset F1 | Possible onset F1 | Timing p50/p95 | Chroma | Supported notes | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Lead vocal 30–45 s | 39 | 0.1034 | 0.2459 | 22.46/33.64 ms | 0.9361 | 0.5641 | Useful pitch-class/F0 evidence, weak boundaries; oracle only |
| Backing vocal 205–220 s | 24 | 0.3333 | 0.3696 | 15.47/35.08 ms | 0.8581 | 0.1250 | Possible alternate voice; never replace harmony |
| Bass 200–215 s | 18 | 0.1818 | 0.2051 | 17.23/29.79 ms | 0.4442 | 0.2222 | Reject for this role |

Every PESTO run retains `pesto.frames.json`, `pesto.activations.npy`, raw and
validated candidates, neutral and source-expression MIDI, quality assessment,
logs and the immutable run manifest.

## Broader stem-role experiment

The user-written Lidl song supplied additional 15-second keys, kick and
strings goldens. Each MuScriptor run was restricted to relevant instrument
labels and compared with Sunofriend's specialised repair output.

| Role | Candidate | Notes | Strong onset F1 | Possible onset F1 | Timing p95 | Chroma | Decision |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Keys | Sunofriend | 104 | 0.1714 | 0.3955 | 35.66 ms | 0.9707 | Primary; strongest harmonic match |
| Keys | MuScriptor | 74 | 0.3678 | 0.5157 | 35.43 ms | 0.8519 | Optional A/B; better attacks, worse harmonic/contour evidence |
| Kick | Sunofriend | 33 | 1.0000 | 1.0000 | 8.59 ms | — | Primary |
| Kick | MuScriptor | 32 | 0.9846 | 0.9846 | 24.01 ms | — | Do not promote |
| Strings | Sunofriend | 31 | 0.1867 | 0.2542 | 29.99 ms | 0.8322 | Primary |
| Strings | MuScriptor | 99 | 0.0333 | 0.1553 | 36.57 ms | 0.6824 | Reject for this golden |

Keys are the only mixed result: MuScriptor finds more attacks, while the
specialised result has substantially stronger pitch-class and contour
evidence. Neither is promoted solely from aggregate metrics; both are in the
optional listening section of the local review page.

## Safety and no-evidence checks

- The quality gate correctly rejected unrestricted MuScriptor-small full-mix
  output after its 1,912-note duplicate burst and vocal-to-wind label leakage.
- MuScriptor, GAME, RMVPE and PESTO each emitted zero notes for the same
  deterministic five-second digital-silence fixture. Every run completed with
  `no-evidence` status rather than failing or inventing notes.
- A missing, wrong-type or hash-mismatched checkpoint fails before inference
  and leaves the existing Sunofriend commands unaffected.
- Raw candidates are never rewritten by source-expression recovery, consensus
  or note-boundary experiments.

## Human listening result

The local review page presented source and neutral-instrument audio for:

1. bass: Sunofriend versus MuScriptor, with PESTO retained only as optional
   evidence;
2. backing vocals: dominant baseline, harmony stack, MuScriptor and GAME, with
   RMVPE/PESTO contour alternatives;
3. MuScriptor neutral velocity versus source-derived expression;
4. optional keys, kick and strings sanity checks.

The completed required results are:

| Decision | Result | Mean score evidence |
| --- | --- | --- |
| Bass | **MuScriptor preferred** | MuScriptor 3.0; Sunofriend 1.5 |
| Backing dominant line | **MuScriptor preferred** | MuScriptor 3.0; GAME 2.5; dominant baseline 1.0 |
| Backing harmony representation | **Sunofriend harmony stack preferred** | Harmony stack 2.67 |
| MuScriptor expression | **Neutral velocity preferred** | Neutral 3.0; source-derived expression 2.0 |

These are role- and golden-specific listening decisions, not universal model
rankings. The bass result keeps MuScriptor opt-in rather than changing the
existing primary automatically. Backing vocals retain separate dominant-line
and harmony outputs. Neutral velocity remains the dependable default for this
MuScriptor lead example; source-derived expression remains reviewable evidence,
not an automatic improvement.

The page records the six Phase 1 listening measures, explicit winners and
free-text GarageBand notes. It saves only to browser local storage and exports
a local JSON document. No private audio or review data was uploaded.

## Close-out verification

The completed local implementation was verified on 16 July 2026 with:

- all 300 unit and integration tests passing;
- the complete Ruff check passing;
- `ai-doctor --require all` confirming MuScriptor, GAME, RMVPE and PESTO code,
  checkpoints, expected hashes and the isolated Python 3.12 runtime;
- all 28 audio references in the local listening page resolving to files;
- a clean source distribution and wheel build, both passing `twine check`;
- the AI runtime and all model setup scripts passing shell syntax checks; and
- the source distribution containing the AI requirements, all model setup
  scripts, this decision record and the Sunofriend skill.

Those checks closed reproducibility, failure safety, packaging and optional
experiment work. The separately completed 23 July listening export closes the
remaining human gate and supplies the final role-specific decisions above.
