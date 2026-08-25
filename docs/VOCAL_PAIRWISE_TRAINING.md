# Vocal A/B labels and provisional pairwise training

This increment supplies the missing bridge between listening and bounded
training without treating ordinary interaction as feedback.

## One explicit label

`sunofriend.vocal-attempt-pairwise-label.v1` binds:

- the exact Musical State document hash;
- the reviewed phrase ID, start/end geometry and phrase-binding hash;
- two distinct human-attempt audio hashes; and
- one deliberate musician action: `left`, `right`, `equivalent`, `neither` or
  `cannot_tell`, plus one to four bounded reason codes.

`cannot_tell` requires `unable_to_compare`; `neither` requires
`no_usable_attempt`. The label contains no lyric text, private note or path.
Playing, dwelling on or repeatedly auditioning an attempt creates no label.
Neither does the earlier action that selected a phrase source for a comp.

Saving this document does not select a vocal, render or correct a comp, start
training or authorise product ranking.

## Immutable training snapshot

`sunofriend.vocal-pairwise-training-snapshot.v1` contains only validated
explicit A/B labels and path-free split assignments. Composition IDs, group
IDs and Musical State hashes must each belong to exactly one of `train`,
`validation` or `test`. A group must belong to one composition, and an
unordered A/B pair may appear only once.

The provisional first real-data evidence gate is intentionally conservative:

- at least 200 explicit labels;
- at least 120 directional (`left` or `right`) labels;
- at least 30 left and 30 right directional labels;
- at least six compositions and twelve recording/session groups; and
- at least four train, one validation and one test composition.

The current snapshot always says `training_ineligible`. Passing the counts is
recorded, but cannot grant eligibility until a separate owner-confirmed,
immutable composition/group registry contract is implemented. This prevents
caller-renamed IDs from gaming a split. A later passing registry would mean
only that a separate bounded training request may be reviewed. It never authorises
execution, checkpoint promotion, automatic take selection or product use.

The snapshot embeds and revalidates each full path-free explicit label before
recomputing its projected row. It still does not reopen the exact Musical State
manifest behind that label. Exact state-manifest binding is therefore a second
future eligibility gate alongside the owner registry; until both exist, even a
structurally valid label with invented hashes cannot become training-eligible.

The thresholds are a provisional anti-overfit gate, not a claim that 200
labels will be enough for a useful ranker. Learning curves and held-out owner
listening can raise them.

## Synthetic ranker canary

`sunofriend.vocal_pairwise_canary` exercises a six-parameter linear ranker on
192 deterministic synthetic feature differences across twelve synthetic,
composition-disjoint groups. It runs:

1. an uninterrupted clean-label arm;
2. a clean arm resumed from a canonical JSON checkpoint; and
3. a shuffled-label control.

The canary passes only when clean held-out accuracy is at least 0.85, clean
beats shuffled by at least 0.20, resumed parameters match uninterrupted
parameters exactly and every metric is finite. It reads no audio or real
labels, uses no network or downloads and changes no product behaviour. Its
result is technical pipeline evidence only.

The executable CUDA worker and checkpoint verifier are not part of this
foundation. They remain a follow-up gate that must first provide hermetic
runtime characterization and satisfy the repository's CRAP and architecture
contracts. This document therefore authorizes no GPU execution, checkpoint
creation or training run. The deterministic synthetic pairwise fixture remains
available for testing the label and admission contracts without private audio.

## Next owner-facing step

The Vocal Session page can add a separate **Compare two attempts** action. The
owner must see the phrase and neutral left/right attempt identities, listen,
press one outcome and choose bounded reasons before **Save comparison** is
enabled. The save action should write the explicit label to the private
append-only session evidence. No background event may call it.
