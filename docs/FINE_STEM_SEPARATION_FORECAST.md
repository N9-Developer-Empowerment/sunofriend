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
- The source-presence process completed before inference and produced four
  song-disjoint, confirmed-present cases for each target. The exact qualified
  package preserves every reviewed PCM24 source hash.
- The Mega-53 synth canary completed four attempts in 37.44 seconds at
  15,424,362,972-byte peak MLX allocation. All outputs were finite, network and
  forbidden-audio attempts were zero, and persisted target plus residual
  reconstructed within zero PCM24 LSB.
- The BS-RoFormer-SW guitar canary completed its four overlap-add cases in
  52.79 seconds at 8,512,054,588-byte peak MLX allocation. Its corresponding
  objective gates also passed with zero-LSB reconstruction and no network,
  forbidden-audio or external-checkpoint attempts.
- The bound review rated synth `partly_useful` in 4/4 cases. It rated guitar
  `partly_useful` in 3/4 and `useful` in 1/4. All eight cases reported no
  catastrophic defect, bleed, artefact or timing problem. Missing content was
  `some` for all synth cases and three guitar cases.
- Both targets therefore pass the frozen 60% private-Studio integration gate
  at 100%. That observed result replaces the earlier 35–50% forecast for both
  pretrained targets passing their first canary.
- The exact six-role integration then completed over the same eight windows.
  Three sequential model loads made 16 bounded attempts and published 64
  finite PCM24 artifacts. All eight persisted role sets reconstructed within
  zero LSB and the worker recorded no network access or automatic retry.
- In the combined review, synth was `useful` in 2/4 confirmed-present windows
  and `partly_useful` in 2/4; guitar was `useful` in 4/4. All eight outputs had
  no catastrophic defect. Three synth windows still reported some missing
  content; ratings on explicitly absent complementary roles are retained but
  excluded from qualification.
- The pure, hash-bound outcome status is
  `private_six_role_integration_qualified`. It grants no public activation,
  source selection or MIDI permission. Downstream MIDI usefulness remains the
  main unresolved musical-product question.
- The full repository regression after the review/qualification repair passed:
  3,659 tests, 17 skipped, in 758.41 seconds. The only warning was the existing
  `pkg_resources` deprecation emitted by the Python 3.9 test environment.

## Probability and duration from the current evidence

The model-selection and short-window reconciliation risks have now resolved
positively. The remaining uncertainty is whether these estimates improve
editable synth/guitar MIDI, whether the six-role package remains useful beyond
the eight frozen windows, and whether checkpoint terms and memory requirements
permit a distributable product. The percentages below are revised engineering
confidence ranges, not measured frequencies.

| Remaining milestone | Probability | Decisive evidence | Delivery if successful |
| --- | ---: | ---: | ---: |
| Coherent private six-role canary | **Achieved** | Completed objective run and listen | Completed |
| Synth/guitar estimates improve downstream editable MIDI | 55–75% | One frozen role-present MIDI bake-off | 2–4 working days |
| Product-integrated private Studio challenger | 85–95% | Import/review plumbing and explicit no-auto-selection boundary | 3–7 working days |
| Private challenger useful beyond the eight canary windows | 70–85% | 2–3 additional song-disjoint full-song reviews | 2–4 weeks |
| Public opt-in six-role preview with resolved terms and supported resources | 45–65% | Terms, installer, 16 GiB fallback or a narrower supported class | 4–8 weeks |
| Training-backed specialist fallback using clean/open stems and curated teacher estimates | 70–85% | 4–6 weeks | 8–12 weeks |
| Provider-assisted import for an individual musician | 65–85% | 1–3 days | 1–2 weeks |

The provider-assisted row can meet an individual musician's stem need, but it
does not meet the independent local-separator goal and remains an import and
benchmark route.

## Recommended portfolio and cumulative forecast

The pretrained portfolio and fixed six-role integration have passed their
first musical gates. The next sequence remains intentionally short:

1. **Complete:** freeze the positive canary and six-role outcome without public
   selection;
2. **Complete:** implement and review the grouped-other projection, exact PCM24
   accounting and combined listening package;
3. **Complete:** freeze a no-effects downstream MIDI comparison over the
   already persisted role-present synth/guitar artifacts—plan SHA-256
   `7afab38b0bd446e2de75b4c408b1e275e533298765f25d89280c055fbb63e1e4`;
4. **Complete technically, review pending:** the approved network-denied worker
   made exactly 16 same-settings attempts over the eight candidate/control
   pairs and published bound MIDI plus loudness-matched previews. Complete the
   blind review and record `cannot_tell` or `not_useful` without blocking
   private Studio access;
5. expose the reviewed six-role package only as a private Studio challenger
   with no automatic source choice; and
6. start LoRA or broader training only if broader validation exposes a real
   quality ceiling, not merely because more tuning is possible.

The revised cumulative forecast is:

| Time from this status date | Cumulative probability |
| --- | ---: |
| Now: reviewed objective six-role integration evidence | **Achieved** |
| Now: objective downstream MIDI package, human review pending | **Achieved** |
| 1 week: reviewed downstream MIDI evidence and private Studio packaging | 80–95% |
| 4 weeks: broader private validation | 70–85% |
| 8 weeks: public opt-in candidate, subject to terms/resources | 45–65% |
| 12 weeks: training-backed fallback if required | 75–85% |

The credible private six-role result has been achieved in the frozen canary.
The next useful answer should arrive within one working week: whether those
separate synth and guitar estimates materially improve editable MIDI. Public
availability is less certain because Mega-53 retains a provisional
local-noncommercial evidence boundary, BS-RoFormer-SW is noncommercial, and the
Mega-53 forward exceeded the original 12 GiB/16 GB-class goal. If the bounded
MIDI and broader-song checks are poor, retain the private evidence and switch
focus rather than starting an unlimited tuning loop.

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
