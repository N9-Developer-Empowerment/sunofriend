# Bounded deterministic remix delta

Status: first offline D+H product slice implemented; no private song artifact
created yet.

This slice answers one deliberately narrow musical question: does attenuating
one owner-named identity-bearing separation estimate inside one exact anchor
produce a useful change while the song remains recognisable?

It has three explicit stages:

1. `create_remix_identity_state` binds the musician's own anchor label to one
   separation estimate. The estimate is evidence, never an original studio
   stem or ground truth.
2. `create_remix_comparison_plan` binds the exact source-control WAV before
   rendering. Source and target estimate must have identical sample rate,
   channel count and frame count.
3. `render_remix_comparison` creates a fresh owner-only local package containing
   the byte-exact source control, one PCM24 challenger, technical evidence and
   a review page.

The only signal operation is:

```text
challenger = source + (envelope_linear_gain - 1) * target_estimate
```

The envelope spans the exact owner anchor, returns to unity at both edges, has
2-16 points and is attenuation-only from 0 to -12 dB. Everything outside the
anchor is unchanged apart from the challenger's declared PCM24 encoding. The
renderer rejects clipping rather than normalising or limiting the result.

The package review compares:

- `AUDIO/source-control.wav` — unchanged source bytes; and
- `AUDIO/delta-challenger.wav` — source plus the one target-estimate delta.

The listener must explicitly confirm hearing both and label identity
preservation and musical usefulness before exporting JSON. Playing, seeking or
dwelling creates no decision. `resolve_remix_comparison_review` verifies the
export against the exact package and turns it into the existing path-free
owner-review contract. The export remains a review record only: it does not
select a product result or become a training label.

This implementation uses deterministic analysis/rendering plus human review.
It uses no model, training, network, pitch change, time change, regeneration,
source selection or automatic preference. A real listening artifact should be
created only after an authorised, synchronized source/estimate pair and owner
anchor have been chosen.
