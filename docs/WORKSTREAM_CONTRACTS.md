# Sunofriend workstream contracts

Status: active coordination policy for parallel product and research work.

The useful organisational lesson from the composability discussion is not to
rewrite Sunofriend around a dynamic plug-in framework. It is to make every
workstream declare what it needs, what it provides, what it changes, and how a
failed or stale result is compensated.

## Common contract

Every bounded workstream records:

- `requires`: exact immutable inputs and human authorities;
- `provides`: exact artifacts or evidence it may create;
- `effects`: state, files, compute or external resources it changes;
- `compensation`: how the active project stops using the result without
  deleting historical evidence;
- `dependency_change`: which hashes or declarations make the result stale;
- `next_evidence_gate`: the next explicit technical or human decision; and
- `authority`: actions the workstream cannot take.

The preferred state progression is:

```text
planned -> preflight_passed -> executed -> technically_verified
        -> human_reviewed -> product_admitted
```

Not every workstream reaches every state. A training canary may finish at
`technically_verified`. A vocal recording may reach `human_reviewed` without
being selected. A failed one-attempt GPU request is terminal for that request
identity; a later attempt is a new request with retained failure lineage.

## Current lanes

### Vocal Comping Workbench

- Requires: exact Musical State, reviewed phrase geometry, immutable sources,
  canonical lyrics and current usable-base hash.
- Provides: captures, explicit source decisions, join reviews and versioned dry
  comp revisions.
- Effects: owner-only local files and derived states; never source mutation.
- Compensation: create a later comp revision or restore an earlier active
  revision. Never delete or rewrite the recording history.
- Dependency change: changed phrase geometry retains recordings but invalidates
  placement, source choice, joins and renders.
- Authority: recording and playback never select a take or create a training
  label.

### Deterministic remix

- Requires: byte-exact source control, synchronized separation estimate,
  musician-named identity anchor and one bounded edit variable.
- Provides: unchanged control, one deterministic challenger, edit map and
  explicit listening review.
- Effects: a local derivative only; no model weights or source changes.
- Compensation: stop referencing the challenger. The source remains exact.
- Dependency change: changed source, estimate, anchor or renderer invalidates
  the comparison plan.
- Authority: no automatic preference, product selection or training label.

### Remix learning

- Requires: owner registry, controlled variant sets, explicit three-way
  listening labels, composition-disjoint snapshot, admitted feature manifest,
  baselines and an exact bounded training request.
- Provides: a technically verified proposal-ordering checkpoint candidate and
  metrics. It does not generate remix audio.
- Effects: bounded GPU time and local research artifacts.
- Compensation: retain the evidence but remove the checkpoint from candidate
  admission. Compute time cannot be undone.
- Dependency change: changed label, registry, split, extractor or checkpoint
  identity invalidates downstream evidence.
- Authority: even a promoted model may only order what to audition first. It
  cannot select a remix or judge preserved identity for the owner.

### RTX execution

- Requires: clean exact commit, unique attempt ID, exact request, approved
  existing runtime, resource ceilings and stop rules.
- Provides: fixed artifacts plus independent verification.
- Effects: one bounded computation and a fresh output directory.
- Compensation: quarantine invalid output and retain the consumed attempt.
  Never retry it automatically.
- Dependency change: any commit, request or artifact drift rejects the run.
- Authority: the Windows worker cannot modify labels, decide the next
  experiment, promote a checkpoint, merge code or download new assets.

## Reconciliation policy

Sunofriend reconciles dependency changes through validators and new immutable
states, not live provider substitution:

- a new separator creates new evidence; it does not silently replace stems;
- a new feature extractor creates a new manifest and invalidates old model
  requests;
- a changed label registry makes a snapshot ineligible until rebuilt;
- a changed repository commit requires a new GPU request; and
- a new comp revision changes the active reference without erasing its parent.

This keeps experimentation cheap while preserving the musician's authority and
the full history needed to understand failures.
