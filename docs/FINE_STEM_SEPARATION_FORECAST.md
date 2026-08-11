# Fine-stem separation delivery forecast

Status date: 11 August 2026.

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
  source selection or MIDI permission.
- Both same-transcriber MIDI reviews are complete. Guitar candidate MIDI beat
  grouped other in 3/4 cases, which is directional private evidence. Isolated
  synth never beat grouped other, including the source-visible provider
  comparison, so there is no demonstrated isolated-synth MIDI advantage.
- The exact three-song full-song plan was approved and consumed once. Its
  guarded run retained objective failure with no automatic retry. The
  replacement retained complete arrays but no guitar worker result, guard
  counters or peak-memory receipt.
- A separately approved model-free recovery reused those exact arrays under
  network denial and published 24 private PCM24 review artifacts. It made
  zero checkpoint loads, model constructions/loads, inference attempts,
  canonicalisations and model-worker subprocesses. Its status is
  `private_review_package_recovered_model_free_resource_gate_incomplete`.
  Full objective qualification is false; guitar/full resource gates remain
  incomplete and supported-ceiling compliance is unknown.
- The full repository regression after the review/qualification repair passed:
  3,659 tests, 17 skipped, in 758.41 seconds. The only warning was the existing
  `pkg_resources` deprecation emitted by the Python 3.9 test environment.

## Probability and duration from the current evidence

The model-selection and short-window reconciliation risks resolved positively,
but isolated synth has not improved MIDI and full-song objective/resource
qualification is incomplete. The immediate uncertainty is musical continuity
in the recovered full-song package. A clean new objective run would require a
new bounded plan rather than replaying consumed authority. The percentages
below are revised engineering confidence ranges, not measured frequencies.

| Remaining milestone | Probability | Decisive evidence | Delivery if successful |
| --- | ---: | ---: | ---: |
| Coherent private six-role canary | **Achieved** | Completed objective run and listen | Completed |
| Directional guitar MIDI benefit | **Achieved privately** | Candidate beat grouped other in 3/4 methodology-limited cases | Completed |
| Isolated synth improves downstream editable MIDI | **Not demonstrated** | Two completed same-transcriber reviews | Completed negative result |
| Product-integrated private Studio excerpt challenger | **Achieved** | Owner-only package with mutually exclusive catalogs | Completed |
| Recovered full-song package is musically useful | 65–80% | One bound complete-song listen over the three recovered cases | 1–3 working days |
| New full-song run passes every objective/resource gate | 55–70% | New plan, complete guitar receipt and supported-ceiling evidence | 1–2 weeks after new authority |
| Private challenger useful beyond the original eight windows | 60–75% | Recovered review plus 2–3 additional song-disjoint songs | 2–4 weeks |
| Public opt-in six-role preview with resolved terms and supported resources | 35–55% | Terms, installer and supported resource class | 4–8 weeks |
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
3. **Complete:** run and review both bounded same-transcriber MIDI comparisons;
   retain directional guitar evidence and the negative isolated-synth result;
4. **Complete:** package the reviewed excerpts as an owner-only private Studio
   challenger with no automatic source choice;
5. **Complete but not qualified:** recover the fixed three-song listening
   package without rerunning a model, while preserving both failure roots and
   the missing guitar resource/guard evidence;
6. **Next:** complete one bound musical listen of the recovered full songs.
   Poor feedback is a result, not a trigger for automatic tuning; and
7. only if that listen justifies continued execution work, write a new bounded
   plan that can produce a complete guitar receipt and resource measurement.
   Start LoRA or broader training only after broader validation exposes a real
   quality ceiling.

The revised cumulative forecast is:

| Time from this status date | Cumulative probability |
| --- | ---: |
| Now: reviewed objective six-role integration evidence | **Achieved** |
| Now: reviewed MIDI evidence and private Studio excerpt package | **Achieved** |
| Now: model-free full-song listening package, objective gate incomplete | **Achieved** |
| 1 week: recovered full-song musical review | 65–80% |
| 4 weeks: broader private validation | 60–75% |
| 8 weeks: public opt-in candidate, subject to terms/resources | 35–55% |
| 12 weeks: training-backed fallback if required | 75–85% |

The credible private six-role excerpt result and its Studio package have been
achieved. The next useful answer should arrive within three working days: how
the recovered six-role estimates hold together across three complete songs.
That listen cannot repair the incomplete objective receipt. Public availability
is less certain because Mega-53 retains a provisional
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
