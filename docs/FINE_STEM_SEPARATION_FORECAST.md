# Fine-stem separation delivery forecast

Status date: 9 August 2026.

This forecast answers a narrower question than technical feasibility: how
likely is Sunofriend to produce musically useful synth and guitar stems, and
how long should that take? It is updated when song-disjoint listening evidence
changes the estimate. A model loading, producing finite tensors or preserving
reconstruction accounting does not count as musical success.

## What counts as success

The practical milestone is six persisted roles:

1. vocals;
2. drums;
3. bass;
4. synth/keyboards;
5. guitar; and
6. residual other.

Wind is a seventh, bonus role. Acoustic piano alone does not satisfy the
synth/keyboards role.

A target reaches the milestone when at least 60% of song-disjoint review clips
where a listener first confirms that the target is audibly present are rated
`useful` or `partly_useful`. `absent` and `cannot_tell` clips are retained but
do not count as model failures. Public preview admission remains objective;
this threshold controls the success claim, not whether negative evidence may
be published.

## Current evidence

- Core four is already public opt-in.
- `htdemucs_6s` produced no demonstrated useful guitar or piano-proxy result.
- Banquet produced eight not-useful targets and one partly-useful quiet
  keyboard target in its bounded canary.
- Mega-53 now passes strict construction and one generated-tensor MLX forward:
  18.19 seconds, 15,424,362,972-byte peak MLX allocation, finite
  `[1, 53, 2, 881664]` output and zero audio or network attempts. This removes
  substantial runtime uncertainty but says nothing about musical quality.
- The full repository regression after that forward passed: 3,637 tests, 17
  skipped, in 801.68 seconds.

## Probability and duration by route

The percentages are engineering confidence ranges, not measured frequencies.
They assume a 36 GB M3 Max for local inference and, where training is listed, a
single RTX 40-series machine with 24 GB GPU memory. Less GPU memory lengthens
or can invalidate the training estimate. “Delivery” means a reproducible
Studio profile and local review path, not hosted processing or automatic MIDI
selection.

| Route | Synth success | Guitar success | Both targets | Decisive evidence | Delivery if successful |
| --- | ---: | ---: | ---: | ---: | ---: |
| Current Mega-53 alone | 45–60% | 35–50% | 20–35% | 1–2 working days | 1–2 weeks |
| Mega-53 synth plus BS-RoFormer-SW guitar | 45–60% | 65–80% | 35–50% | 1–3 weeks | 2–4 weeks |
| LoRA specialists using clean/open stems plus a curated pseudo-labelled catalogue | 70–85% | 70–85% | 60–75% | 4–6 weeks | 8–12 weeks |
| LoRA using provider estimates alone | 50–65% | 55–70% | 35–55% | 3–5 weeks | 6–10 weeks |
| Reproduce the CP-JKU eight-stem training programme on one RTX 40-series GPU | 55–70% | 65–80% | 45–65% | 6–10 weeks | 12–20 weeks |
| New separator trained from scratch on provider estimates | 30–50% | 35–55% | 20–40% | 8–12 weeks | 16–30 weeks |
| Provider-assisted import rather than a Sunofriend model | 70–90% | 80–95% | 65–85% | 1–3 days | 1–2 weeks |

The provider-assisted row can meet an individual musician's stem need, but it
does not meet the independent local-separator goal and remains an import and
benchmark route.

## Recommended portfolio and cumulative forecast

Do not make one model carry all of the risk:

1. complete the four-song Mega-53 synth canary;
2. if synth passes, retain it immediately as a Studio challenger;
3. evaluate the six-stem BS-RoFormer-SW native guitar output rather than
   relying on Mega-53's weaker broad-role promise;
4. begin a data audit and one-epoch LoRA fit probe without waiting for either
   listening result; and
5. proceed to full specialist training only if the fit probe improves a fixed
   song-disjoint validation set.

Allowing for correlated model failures, this portfolio gives the following
forecast for reaching useful synth **and** guitar:

| Time from this status date | Cumulative probability |
| --- | ---: |
| 2 weeks | 35–50% |
| 6 weeks | 55–70% |
| 12 weeks | 70–80% |
| 16 weeks, with adequate clean training data | 75–85% |

The quickest credible success date is therefore within two weeks; the planning
date for a training-backed result should be 8–12 weeks. If no route succeeds
after the one pretrained portfolio and one specialist-training cycle, the
forecast must be reduced rather than starting an unlimited tuning loop.

## Why the alternatives receive those probabilities

### BS-RoFormer-SW is the stronger immediate guitar challenger

The audited BS-RoFormer source registry describes BS-RoFormer-SW as its
recommended six-stem production model with native vocals, drums, bass, guitar,
piano and other heads. Its checkpoint is about 699 MB and smaller in scope than
the 53-output model. It does not solve synth, but a specialised native guitar
head is a better bet than expecting every Mega-53 role to be strong.

The registry records a CC-BY-NC-SA-4.0 checkpoint boundary. That affects
release tier but not the musical probability estimate.

Source: [openmirlab/bs-roformer-infer](https://github.com/openmirlab/bs-roformer-infer).

### LoRA is plausible, but data quality dominates catalogue size

The upstream MVSep training code supports LoRA for BS-RoFormer and warm-starting
from a compatible checkpoint. A 700-song listening catalogue can provide
diversity, hard negatives and teacher estimates. It is not automatically 700
songs of ground truth: cloud-separated outputs contain the teacher model's
bleed, omissions and taxonomy decisions.

The ACMID study gives a useful scale warning. It reports that 4,643 hours of
uncleaned material underperformed 737 hours after classifier-based cleaning,
and that combining the cleaned material with MoisesDB and MedleyDB improved
the seven-stem separator. More pseudo-labels are therefore valuable only after
presence, purity and alignment filtering.

Sources: [MVSep LoRA guide](https://github.com/ZFTurbo/Music-Source-Separation-Training/blob/main/docs/LoRA.md),
[ACMID paper](https://arxiv.org/abs/2510.07840).

### The CP-JKU route proves the target taxonomy, not the local schedule

CP-JKU has published an eight-stem BS-RoFormer programme containing separate
guitar, keyboard and synthesizer roles. It expands a four-stem warm start with
LoRA and new mask heads, which is close to Sunofriend's desired product shape.
However, the published separator used four NVIDIA H100 GPUs and a multi-dataset
training curriculum. Reproducing it on one RTX 40-series GPU is a compression
and adaptation project, not a quick checkpoint trial; that is why it has a
higher eventual probability but a 12–20 week delivery estimate.

Sources: [CP-JKU code](https://github.com/CPJKU/music-source-restoration),
[system report](https://arxiv.org/abs/2603.04032).

## Data and evaluation sequence

The first catalogue round should use 120–200 deliberately balanced songs, not
all 700 at once:

- synth prominent;
- guitar prominent;
- both present;
- neither present or deliberately difficult;
- dense electronic, vocal-forward, acoustic/mixed and effects-heavy material.

Keep a song-disjoint blind test set that is never used for window selection,
prompt selection, training or early stopping. Provider estimates may be used
as teachers only where their terms and the source rights permit it. Genuine or
appropriately licensed multitracks remain the reference data for objective
metrics. Human review remains the final usefulness measure.
