# Guitar and keyboard/synth query-challenger plan

The first fixed-role `htdemucs_6s` Studio challenger passed its objective
offline and reconstruction gates but failed musically on the fixed five-song
review corpus. No reviewed case demonstrated useful guitar extraction. The
only nominally useful piano-proxy output was near-silence on a song without
piano, and the one reviewed piano-like instrument was missed.

That result remains accessible as evidence. It is not promoted, selected for
MIDI or described as working guitar or keyboard separation. Negative feedback
does not disable the public vocals/drums/bass/grouped-other profile.

## Change the question, not the review threshold

`piano` is too narrow to stand for modern keyboard parts. The next experiment
uses two explicit target families:

- **guitar**: acoustic, clean electric and distorted electric guitar; and
- **keyboard_synth**: electric piano, organ, synth pad and synth lead.

Acoustic piano can remain a later control. It is not required for a useful
`keyboard_synth` result. These experimental labels do not become downstream
source or MIDI roles automatically.

## First candidate: Banquet

The first read-only candidate is
[Banquet](https://github.com/kwatcharasupat/query-bandit), a music-specific,
query-conditioned separator. Its published setup-C class vocabulary includes
the guitar, electric-piano, organ, synth-pad and synth-lead classes above. The
official repository reports 24.9 million trainable parameters, supports a
bring-your-own 10-second audio query and exposes a CPU inference flag.

Pinned public evidence:

| Evidence | Identity |
| --- | --- |
| Source revision | `79ed5bb75e5c3a40cd319d9d990cee913fc65c26` |
| Source terms | MIT |
| Checkpoint record | Zenodo DOI `10.5281/zenodo.13694558` |
| Candidate file | `ev-pre-aug.ckpt` |
| Published size | 645,470,187 bytes |
| Published MD5 | `4dfb91d6d27c2dfd4992a15070915541` |
| Observed SHA-256 | `657295888781e62ef50593002720d2edb3858b9e5bbfabf0c54f715a0da4b9e2` |
| Checkpoint terms | CC BY-NC-SA 4.0 |
| Training dataset | MoisesDB, CC BY-NC-SA 4.0 |

The approved evidence-only download matched the published byte count and MD5.
A network-denied, non-deserializing inspection found a 3,491-member PyTorch ZIP
and parsed its 452,701-byte protocol-2 pickle metadata stream. Its four GLOBAL
references were limited to `OrderedDict`, Torch float/double storage and the
standard tensor rebuild helper; no application model class was observed. The
inspection did not read tensor-storage payloads, import a dependency, construct
a model or establish loading safety. Exact runtime pins and Apple-silicon
resource behaviour remain unknown. Consequently the candidate is still not
registered, executable or approved for model loading.

The NonCommercial term is an actual boundary, not something a user approval
can erase. This candidate may be evaluated only as local noncommercial
research unless separate permission changes that conclusion. It cannot become
a hosted conversion service, redistributed checkpoint or commercial default
through this experiment.

## Query boundary

Banquet requires a ten-second query example. The first experiment freezes two
song-disjoint, copyright-safe queries before inference: one guitar-family query
and one keyboard/synth-family query. Provider-derived Suno and Moises estimates
remain comparison cues and are not fed to the model as queries.

One fixed query per family prevents a post-feedback search for a favourable
prompt or example. If either query is objectively malformed, one remediation
cycle may replace it before the full corpus. Poor musical output does not
permit an unbounded query hunt.

## Output contract

Each run binds the exact SCNet grouped-`other` parent and persists:

1. one requested query-conditioned target; and
2. the exact residual after that target.

The two persisted files must share the parent clock and reconstruct it within
two PCM24 least-significant bits. Reconstruction proves accounting, not
instrument accuracy. The parent and its children remain mutually exclusive,
and neither output enters MIDI without a later human choice.

## Bounded evaluation

Use one model configuration, two frozen queries and ten 15-second cases:

- retain only the existing reviewed guitar windows that have credible
  instrument-present evidence;
- freeze new keyboard/synth windows using broad keyboard, organ and synth cues
  before inference;
- keep the five authorised songs song-disjoint from the query examples;
- show provider estimates only as independently generated comparisons; and
- collect the same usefulness, bleed, missing-content, artefact, timing and
  downstream-MIDI fields without choosing a winner.

There is one configuration and at most one objective remediation cycle. When
the objective gates pass, the profile may remain available in Studio even if
musical reports are poor. It is promoted only after accumulated listening
evidence shows that it actually extracts target content.

## Objective gates

- exact source, checkpoint and runtime identities;
- checkpoint SHA-256 and weights-only static inspection before model loading
  (**passed as non-authorising evidence**);
- hash-locked dependencies;
- network-denied model construction and inference;
- finite stereo 44.1 kHz samples on the parent clock;
- target-plus-residual reconstruction within two PCM24 LSBs;
- declared timeout and memory ceilings on the first supported Mac; and
- no upload, source mutation, automatic model/query choice or MIDI activation.

## Inspect the current no-effects plan

```bash
.venv/bin/python \
  scripts/plan-separation-other-refinement-query-challenger.py
```

The command prints a deterministic, hash-bound plan. It performs no network
request, reads no audio and installs nothing. It records the completed private
checkpoint-evidence step without reading the cached checkpoint.

The completed evidence approval did not authorize dependencies, loading or
inference. The next work is a no-effects dependency/runtime audit. Any later
installation or restricted model-loading attempt needs its own reviewed plan
and explicit approval.
