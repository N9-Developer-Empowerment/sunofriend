# Private full-song six-role canary plan

Sunofriend has qualified private 15-second evidence for six mutually exclusive
roles: `vocals`, `drums`, `bass`, `synth`, `guitar` and residual `other`. That
does not yet establish full-song continuity. The immutable plan and its guarded
executor are implemented, but the executor has not been authorised or run. Its
default mode emits a no-effects execution request without loading a checkpoint,
running a model, reading audio content or granting a product permission.

The immutable plan document is
`sunofriend.fine-stem-full-song-six-role-plan.v1`, with SHA-256
`869ac229d5c95c9c3d5eb2c9eb38da368056f6fe3c644de9830cc593313efb7d`.

## Fixed corpus

The corpus contains exactly three song-disjoint owner-authorised sources:

| Coverage slot | Track | Scored specialist roles | Confirmed-present evidence |
| --- | --- | --- | --- |
| Both targets | `I am a Alien mashup` | synth and guitar | guitar at 5–20 seconds; synth at 210–225 seconds |
| Synth | `Be Alone` | synth | synth at 201–216 seconds |
| Guitar | `In the way` | guitar | guitar at 73–88 seconds |

Every presence decision was made from the source before the relevant model was
scored. A provider stem label is not treated as truth. A complementary role
without confirmed presence remains reviewable context but is not counted as a
model failure.

The plan binds the exact original source hashes, byte counts, clocks and
rights categories already preserved by the qualified presence package. During
planning it checks only that each regular source file exists at the expected
path and byte count. It does not open or hash the audio content again; the
future executor must re-hash before canonicalisation.

## One bounded execution

If separately approved, the worker will:

1. verify each exact source hash and canonicalise it once to stereo 44.1 kHz
   PCM24 without modifying the original;
2. load SCNet core four, Mega-53 synth and BS-RoFormer-SW guitar once each;
3. run the models sequentially for three attempts per profile, nine full-song
   profile attempts in total;
4. constrain synth and guitar allocation to SCNet grouped other; and
5. write source, six roles and reconstruction check atomically for each song.

Internal model forward calls are duration-dependent and are now derived before
execution from the exact canonical frame counts and frozen backend contracts:
94 SCNet forwards after the deterministic seed-0 shift, 75 Mega-53 forwards
using the approved 512-hop-aligned overlap-2 contract and 122
BS-RoFormer-SW forwards using its verified reflect-pad overlap loop. These are
accounting limits, not permission to tune chunking, overlap, weights or
configuration.

The ceilings are 900 seconds per song, 2,700 seconds total and 30 GiB peak
unified memory on the first supported 36 GB M3 Max class. Any objective failure
is preserved and stops the run. There is no automatic retry and no remediation
cycle in this plan.

## Feedback without another doom loop

Objective stop-ship conditions remain licence/hash contradiction, network
access, source mutation/privacy breach, corrupt or missing roles, non-finite
audio, clock mismatch, failed reconstruction accounting, crash, OOM or a
resource-ceiling failure.

Musical feedback is separate. The review records playback automatically and
has no listened checkbox. It presents each complete song plus the exact
confirmed-present specialist windows, records usefulness and issue dimensions,
and accepts `cannot_tell` and `not_tested`. It does not require exhaustive
internal chunk-boundary clicking or a minimum usefulness score. Poor results
add limitations; they do not disable core four, erase the qualified private
profile or trigger a configuration search.

This remains private Studio evidence. It grants no public activation, source
selection, MIDI, hosting, redistribution or audio upload.

## Reproduce the no-effects plan

Use a fresh owner-only output root:

```bash
.venv/bin/python scripts/plan-fine-stem-full-song-six-role.py \
  PRIVATE-PRESENCE-ROOT \
  PRIVATE-INTEGRATION-OUTCOME.json \
  --source-root /absolute/path/to/stem_examples \
  --both-targets-track i-am-a-alien-mashup \
  --synth-track be-alone \
  --guitar-track in-the-way \
  --out PRIVATE-EVIDENCE/fine-stem-full-song-six-role-plan-v1
```

The command reads JSON and source metadata only. It writes one mode-`0600`
plan inside a mode-`0700` directory and performs no model or audio operation.

## Preflight the guarded executor

This command prints the immutable, path-light execution request and exits. It
does not require approval because it performs zero source-content reads,
canonical writes, model loads, inference attempts or audio writes:

```bash
.venv/bin/python scripts/run-fine-stem-full-song-six-role.py \
  --plan PRIVATE-EVIDENCE/fine-stem-full-song-six-role-plan-v1/FULL-SONG-SIX-ROLE-PLAN.json \
  --out PRIVATE-EVIDENCE/fine-stem-full-song-six-role-canary-v1
```

The execution path is fail-closed. It requires Apple-silicon macOS,
`sandbox-exec` network denial, a fresh output root, `--confirm-rights` and an
`--approved-plan-sha256` exactly equal to the immutable plan hash. It verifies
every source before and after processing, canonicalises each source once, runs
three single-load workers sequentially and gives one coordinator sole PCM24
write authority. Objective failure is retained under a fresh `-FAILED` root;
there is no retry.

Once the exact approval below has been received, the authorised command is:

```bash
.venv/bin/python scripts/run-fine-stem-full-song-six-role.py \
  --plan PRIVATE-EVIDENCE/fine-stem-full-song-six-role-plan-v1/FULL-SONG-SIX-ROLE-PLAN.json \
  --out PRIVATE-EVIDENCE/fine-stem-full-song-six-role-canary-v1 \
  --approved-plan-sha256 869ac229d5c95c9c3d5eb2c9eb38da368056f6fe3c644de9830cc593313efb7d \
  --confirm-rights \
  --execute
```

After objective completion, serve the report-bound local page with:

```bash
.venv/bin/python scripts/serve-fine-stem-full-song-six-role-review.py \
  PRIVATE-EVIDENCE/fine-stem-full-song-six-role-canary-v1 \
  --plan PRIVATE-EVIDENCE/fine-stem-full-song-six-role-plan-v1/FULL-SONG-SIX-ROLE-PLAN.json
```

The page records playback automatically, including the confirmed-present
source windows, and has no listened checkbox. Autosave, download and the
visible fallback all bind feedback to the exact plan and report. The review
JSON contains no audio, paths, filenames or telemetry and cannot select a
source, start MIDI or activate a profile.

## Exact later approval

Execution remains blocked until the user cites the plan hash in this form:

> I approve one network-denied private full-song six-role canary bound to plan
> SHA-256
> `869ac229d5c95c9c3d5eb2c9eb38da368056f6fe3c644de9830cc593313efb7d`,
> over its three exact song-disjoint owner-authorised sources. I approve
> canonicalising each source once to stereo 44.1 kHz PCM24, loading SCNet
> core-four, Mega-53 synth and BS-RoFormer-SW guitar once each and running the
> nine fixed full-song profile attempts sequentially. I approve the fixed
> grouped-other-constrained projection and private PCM24 source, vocals,
> drums, bass, synth, guitar, residual-other and reconstruction review
> artifacts. No automatic retry, public activation, source selection, MIDI,
> hosting, redistribution or audio upload is approved.
