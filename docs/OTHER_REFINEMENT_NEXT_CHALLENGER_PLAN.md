# Synth-first fine-stem challenger

Sunofriend's public opt-in baseline remains vocals, drums, bass and grouped
other. Two bounded attempts to split grouped other more deeply are retained as
negative evidence:

- `htdemucs_6s` passed objective execution but demonstrated neither useful
  guitar extraction nor successful piano extraction; and
- Banquet passed its objective adapter and canary gates, but the completed
  review rated eight of nine targets not useful and one quiet keyboard target
  partly useful.

Neither result is being retuned or rerun. Negative listening does not disable
the public core-four profile, and it does not create an empirical doom loop.

## Priority is synth, then guitar and wind

The next milestone targets `synth` first. Synthesizers are more pervasive in
modern popular music than acoustic piano, while treating piano as “keys” hid
the actual product goal. The priority is now:

1. `synth`;
2. `guitar`; and
3. `wind`.

Acoustic piano remains an optional control. It is not a proxy for synth,
organ, electric-piano or general keyboard separation.

## First research candidate

The next candidate is the public
[MVSep Mega 53 Stems v1.0.21 release](https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/tag/v1.0.21),
which publishes explicit `synth`, `wind`, `guitar`, `electric-guitar` and
`acoustic-guitar` roles. It uses a Band-Split RoFormer architecture, unlike the
failed query-conditioned Banquet route and the earlier `htdemucs_6s` route.

This is a research candidate, not a product claim. Upstream says the model is
memory-intensive, recommends at least 16 GB VRAM, warns that individual roles
may underperform specialised models, and states that its 53 outputs overlap
and do not sum to the mixture. The first benchmark therefore targets the
verified 36 GB M3 Max and persists only:

- the native `synth` estimate; and
- `residual_other = canonical_grouped_other - persisted_synth`.

That two-file equality is transparent PCM24 accounting, not proof that the
synth estimate is musically accurate. The report records the native estimate's
correction RMS and peak. Guitar and wind require separate later evidence even
though the same model exposes those roles.

Inspect the immutable no-effects plan with:

```bash
.venv/bin/python \
  scripts/plan-separation-other-refinement-next-challenger.py
```

The plan neither downloads nor loads anything, reads no audio and grants no
execution, source-selection or MIDI authority.

## Exact source and artifacts

The proposed Apple-silicon runtime is the MLX backend at exact
`openmirlab/bs-roformer-infer` revision
`de35ada5817b878da0194ee2860253dda3a9c2b2`. Its git-archive SHA-256 is
`e64fe7733a45f5efc53091bbc2ab6dd04a0ee7373a639f1c9b27275502f26691`.
The source is MIT-licensed, but the published version string remains `0.1.5`
and the released wheel predates this audited MLX revision. The completed
evidence runtime therefore pins this source revision, not merely
a package version, and never installs the stale released wheel.

The upstream registry declares:

| Artifact | Bytes | Declared SHA-256 |
| --- | ---: | --- |
| `mvsep_mega_model_bs_roformer_53_stems_v1.ckpt` | 1,368,919,887 | `c62820893bbf86d4e734f966bd142d9157cfc8bb8e79e9d8f9ea553f3ff3519f` |
| `mvsep_mega_model_bs_roformer_53_stems.yaml` | 4,184 | `7e198062a251587088adb91215a4f44ab59e67bd62fcc805cf54d6e7dfc51103` |

Those identities were locally verified on 8 August 2026 by the separately
approved evidence-only gate. The exact observed total was 1,368,924,071 bytes,
and both SHA-256 values matched the registry. Network was denied before the
inspector inventoried 13,599 checkpoint members and parsed 565,328 pickle
opcodes. It did not deserialize the checkpoint, call `torch.load`, import or
construct a model, run inference or read audio. The immutable static-evidence
document SHA-256 is
`d855138176807a7ca8738bd660141eb2b142676e41ccf56014be64e53f012a24`.

Reproduce the already consumed evidence boundary only in a fresh evidence root
and only with equivalent explicit approval:

```bash
scripts/setup-separation-other-refinement-next-challenger-macos.sh \
  --evidence-only \
  --accept-provisional-local-noncommercial-terms \
  --accept-checkpoint-use
```

The source registry still labels
the checkpoint licence `not-reviewed`. The public GitHub release is strong
evidence that the maker intended the artifact to be shared, but it is not a
licence grant for hosting, redistribution or a commercial default. The first
gate therefore used a capped evidence-only download under an explicit
provisional local-noncommercial acknowledgement. It did not wait for a bespoke
email, and grants nothing beyond the completed static evidence collection.

The source's MLX backend reaches an unrestricted `torch.load`, so Sunofriend
does not use that loader. The completed restricted adapter loaded one explicit
local checkpoint with
`torch.load(weights_only=True, map_location="cpu")`, compared every key, shape
and dtype before strict conversion, disabled automatic downloads and ran with
network denied.

The exact GitHub source tarball was separately capped at 32 MiB and observed at
144,791 bytes with SHA-256
`9b95036b8219eb5cd7be61a29868e6633dd42df0078eda55a0f3710123551c73`.
All 64 files (522,358 logical bytes) matched the sealed inventory, including
the six previously audited critical-file hashes. Static extraction and
inspection ran with network denied and imported or executed no source. The
source-evidence document SHA-256 is
`982ce7c2e9355be9a79d701c8f505237ada7da6ebad41695b48b70dc8c6aad97`.

## Exact runtime closure

The separately approved evidence-only dependency gate resolved 29 exact
CPython 3.12/macOS-arm64 wheels. The closure is 127,527,173 bytes, against a
1,610,612,736-byte cap; peak staged evidence was 128,346,422 bytes. Static
inspection ran with network denied, checked every wheel ZIP, parsed package and
dependency metadata, and hashed bundled licence files. It did not install or
import a package, execute wheel code, load a checkpoint, construct a model,
run inference or read audio.

The exact lock is
`separation-other-refinement-next-runtime-requirements.txt`, SHA-256
`284d198c43e9074a4d645f005d937dd4e93b99e22aa21d942caaa1822b13d10b`.
The immutable static-evidence document SHA-256 is
`d8488079a9c82961056e296fa1050e07f2d341602293b01ed3e5b1de32ae5327`.
Direct pins include Torch 2.2.2, MLX 0.31.2, MLX-Spectro 0.7.0 and NumPy
1.26.4. All 29 wheels have licence metadata or bundled licence-file evidence;
no contradiction with private local evaluation was found. Binary
redistribution still needs a separate composite-notice review, and this audit
does not change the checkpoint's provisional local-noncommercial boundary.

The single bounded resolver remediation made two compatibility constraints
explicit: MLX 0.31.2 requires a macOS 14-or-later arm64 wheel target, and
rotary-embedding-torch 0.9.1 requires Torch 2.4 or later. The lock therefore
uses the newest compatible 0.8 release, rotary-embedding-torch 0.8.9, while
retaining the already proven Torch 2.2.2 and NumPy 1.26.4 baseline.

The completed evidence command was:

```bash
scripts/setup-separation-other-refinement-next-challenger-macos.sh \
  --runtime-wheel-evidence-only \
  --accept-runtime-wheel-evidence
```

That authority is consumed.

## Isolated runtime import gate

The separately approved follow-up installed the exact 29-wheel lock into a
fresh CPython 3.12.10/macOS-arm64 environment using only the local cache,
`--no-index`, `--require-hashes` and OS network denial. All 29 installed
distributions matched the lock and the thirteen direct runtime modules imported
from the isolated environment. The runtime contains 21,124 regular files and
620,247,886 logical file bytes. The canonical import-report SHA-256 is
`60eefa4285f720cc81f795b126c32dbc9462f05d1398662702bd313f394202a9`;
the report file SHA-256 is
`567068a414c5ebc0cdb7cd47564934c5ec8f6b13c70425dd736c02af43892ac7`.

The first verifier pass correctly stopped on a socket audit event. The single
allowed remediation established from installed source that importing
`requests`/`urllib3` constructs a socket and attempts a loopback `::1` bind to
probe IPv6 support. The final verifier records that contained local probe
separately while continuing to fail any connect, DNS or non-loopback operation.
The OS network-denial sandbox remained active. There were zero Python network
attempts, checkpoint or audio opens, and `torch.load` calls.

The completed command was:

```bash
scripts/setup-separation-other-refinement-next-challenger-macos.sh \
  --install-runtime \
  --accept-runtime-install-and-import
```

That runtime-install authority is consumed.

## Strict construction and load gate

The separately approved model gate constructed the exact MLX topology from the
verified immutable source and loaded the checkpoint once with the required
weights-only CPU call. The raw checkpoint contains 13,595 tensor entries and
681,663,596 values. Its audited conversion skips 24 non-parameter rotary
buffers (768 values), leaving 13,571 model parameters and 681,662,828 values.
Every converted key, shape and dtype matched the constructed model before a
strict load; the constructed, converted and loaded inventory SHA-256 is
`565a9430061391486c8686d80eb4b6b65fdfd402b4bdeb603ab4ef5cf8c41fd8`.
The canonical report SHA-256 is
`798b5250eacf18d3f6193fde9d5c613ee68520490aed663395313a47eea4d666`.

The bounded compatibility remediation records an upstream config/adapter
contradiction rather than hiding it. Checkpoint tensor geometry requires
transformer expansion 4 and mask-head expansion 2, while the audited MLX port
feeds one setting to both. Sunofriend's process-local adapter splits those two
checkpoint-derived values and casts the constructed parameters to the
checkpoint's float16 dtype; it does not mutate the verified source. The gate
recorded one checkpoint load, zero network attempts, zero audio opens and zero
forward calls. It performed no inference, activation, selection or MIDI.

The upstream inference chunk is 882,000 samples and its overlap-2 step is
441,000 samples. Neither is divisible by the 512-sample STFT hop. Sunofriend
recorded that objective mismatch and did not silently change it during model
loading.

The pure no-effects contract now applies one deterministic rule: choose the
largest value no greater than the published chunk that is divisible by
`stft_hop_length * num_overlap`. This produces an 881,664-sample chunk and a
440,832-sample step—1,722 and 861 STFT hops respectively. The change is 336
samples, or 7.62 ms, shorter than the publication. The generated tensor uses
that exact length, so no input padding or output cropping is hidden. Verified
source, configuration and checkpoint bytes remain unchanged.

Inspect the frozen contract with:

```bash
.venv/bin/python \
  scripts/plan-separation-other-refinement-next-synthetic.py
```

Its canonical document SHA-256 is
`1ac15c7082223fcf2bdfd1d7443320f782cae87b8ac6e89cf991c19553da9903`.
The plan binds one seed-0 in-memory stereo float32 tensor with shape
`[1, 2, 881664]`, the exact 53-role output order, `synth` at zero-based index
38, one checkpoint reload, one construction and one forward attempt. It opens
and persists no audio, permits no retry and performs no action merely by being
printed.

## Evaluation without false failures

The earlier corpus exposed an evaluation flaw: some windows may not audibly
contain the requested instrument. A silent target can be correct when the
instrument is absent, and an empty estimate cannot prove model failure when
presence was never established.

The synth evaluation separates two questions:

1. Before scoring the model, a listener records `present`, `absent` or
   `cannot_tell` for synth in each frozen source window.
2. Only an audibly present case receives `useful`, `partly_useful`,
   `not_useful` or `cannot_tell` model feedback.

`absent` and `cannot_tell` remain valid reports and are never counted as model
failures. They also cannot enter an instrument canary: the source-presence gate
replaces that case before inference. Replacement is still bounded and occurs
from source-only listening, never after seeing separator output. If four
song-disjoint present cases cannot be established from the authorised local
corpus, the run stops and requests new authorised samples instead of searching
model results for favourable examples.

The first source-only round froze one 15-second window from each of four
owner-authorised Ezzye tracks. The completed review established three present
synth cases and one present guitar case; the other judgements remain valid
source evidence, not model failures. The single source-selection replacement
cycle used eight independently frozen high-activity windows across five
authorised tracks and established three present songs for each target. One
additional independently frozen `Uni Ava` synth window and one `Like Fire`
guitar window have been listened to, but their two radio decisions were lost
by the original browser page and require re-entry before inference. The
repaired localhost page has no listened checkbox: each case is marked listened
after every player emits playback, and playback/form state is saved to both
browser-local and atomic server storage. A model-free qualification composer
then requires exactly four song-disjoint `present` cases per target and copies
the exact reviewed PCM24 source artifacts without another audition. Provider
stems remain
independent attention estimates, not truth. Poor or mixed musical feedback
cannot start automatic tuning, select a source, activate MIDI or remove the
functioning core-four route.

## Ordered gates

The remaining gates are deliberately one-way:

1. **Complete:** evidence-only artifact download and exact hash verification;
2. **Complete:** network-denied, non-loading static inspection;
3. **Complete:** a fully hash-locked CPython 3.12/macOS 14+ arm64 dependency closure;
4. **Complete:** isolated install and import verification;
5. **Complete:** strict weights-only construction and load;
6. **Complete:** one generated-tensor objective forward under the frozen
   881,664/440,832 alignment contract; and
7. **Complete but insufficient:** the first source-only localhost review
   records all eight listening attestations and decisions, without running a
   model. It established three present synth cases and one present guitar case;
8. **Complete but insufficient:** the one allowed source-selection replacement
   package recorded all eight decisions and established three present songs for
   each target without running a model;
9. **Complete:** the final source-only addition plus explicit listening
   attestation established `Uni Ava` synth and `Like Fire` guitar as present.
   The immutable qualified package contains exactly four target-present,
   song-disjoint cases per role and preserves every reviewed source hash;
10. **Complete:** the separately approved Mega-53 synth and BS-RoFormer-SW
   guitar canaries ran once under network denial with no retry. Both objective
   reports contain finite artifacts, exact identities and zero-LSB PCM24
   reconstruction;
11. **Complete:** both bound reviews contain four no-catastrophic decisions.
   Synth was `partly_useful` in 4/4 cases. Guitar was `partly_useful` in 3/4
   and `useful` in 1/4. Neither review reported bleed, artefacts or timing
   problems. Both pass the frozen 60% private-Studio integration threshold; and
12. **Complete:** the approved integration reconciled both specialists inside
   SCNet grouped other as mutually exclusive synth, guitar and residual-other.
   Three sequential model loads made exactly 16 bounded attempts over the eight
   reviewed windows. All 64 PCM24 artifacts were finite and reconstructed
   within zero LSB. The report SHA-256 is
   `af0533233c4469c3914fbe2cf4eae1195de1ee545847c122a8a9f023f350d513`;
13. **Complete:** the bound review recorded all eight roles in all eight cases.
   On confirmed-present cohorts, synth was `useful` in 2/4 and
   `partly_useful` in 2/4; guitar was `useful` in 4/4. All outputs had no
   catastrophic defect. The pure outcome status is
   `private_six_role_integration_qualified`; and
14. **Complete, no MIDI authority implied:** the no-effects downstream MIDI
   usefulness plan binds all eight exact role-present artifacts. It compares
   each isolated synth/guitar candidate with a sample-exact grouped-other
   control under identical track metadata and transcription settings. Its
   SHA-256 is
   `7afab38b0bd446e2de75b4c408b1e275e533298765f25d89280c055fbb63e1e4`;
   and
15. **Next, separate authority required:** execute exactly 16 private MIDI
   transcription attempts without rerunning a separator, review candidate
   versus control blindly, and retain `cannot_tell`, `not_tested` and poor
   results without disabling private six-role evidence.

The completed synth report SHA-256 is
`b985dd021c33564967f445cb30697c50cb03362c7407b8aee21a54449c3caabf`;
its review SHA-256 is
`42b4cb99f515f813269602424857fe03083cdef6882da135eba5820bb3dca958`.
The completed guitar report SHA-256 is
`b7bc8722d603719d3131c623a659c90816ad70eede9987daa16012789ae3fbbc`;
its review SHA-256 is
`8e840fb97595b7d38e1e042188ed555ff31d749c3d41fe3ee7ee99984c4b9efa`.
The no-effects portfolio outcome SHA-256 is
`a2b73a607de1bef55fe04bff334a343fc815c0a0766efa6dec72133a689a37d4`.

The exact reviewed cohort can be reproduced without loading either model:

```bash
python3 scripts/compose-fine-stem-target-presence-qualified.py \
  --source-root "$REPLACEMENT_PRESENCE_ROOT" \
  --source-root "$ADDITION_PRESENCE_ROOT" \
  --out "$QUALIFIED_PRESENCE_ROOT"
```

The following commands describe the two already-consumed canary plans; do not
rerun them without fresh authority:

```bash
python3 scripts/run-fine-stem-canary.py \
  --profile bs-roformer-mega-53-synth-v1 \
  --presence-root "$PRESENCE_ROOT" \
  --checkpoint "$MEGA53_CHECKPOINT" \
  --config "$MEGA53_CONFIG"

python3 scripts/run-fine-stem-canary.py \
  --profile bs-roformer-sw-guitar-v1 \
  --presence-root "$PRESENCE_ROOT" \
  --checkpoint "$SW_CHECKPOINT" \
  --config "$SW_CONFIG"
```

The report-bound review page used HTTP byte ranges, atomic server-side save and
server-backed JSON download. It bound every decision to the exact profile,
report and cases, with catastrophic defects separate from usefulness, bleed,
missing content, artefacts, timing and downstream MIDI.

The completed no-effects six-role plan can still be reproduced with:

```bash
python3 scripts/plan-fine-stem-six-role-integration.py \
  --portfolio-outcome PORTFOLIO-OUTCOME.json \
  --synth-root SYNTH-CANARY-ROOT \
  --guitar-root GUITAR-CANARY-ROOT
```

It bound eight already reviewed 15-second references. Each case reused its
persisted qualified primary estimate and proposed only the missing specialist
estimate plus one SCNet core-four run. A fixed 4096/1024 grouped-other-
constrained three-way Wiener mask allocates synth, guitar and residual other.
The one approved execution is consumed. It allowed one configuration, no
remediation cycle and no automatic retry. Public activation, source selection,
MIDI, hosting, redistribution and upload remain false. Bind the completed
review into its pure outcome with:

```bash
python3 scripts/record-fine-stem-six-role-integration-outcome.py \
  SIX-ROLE-INTEGRATION-ROOT \
  --out FRESH/fine-stem-six-role-integration-outcome-v1
```

The review document SHA-256 is
`407e4bf0ab686ceee2bcaa77473eca0a76b307b13b217e070cf5ae8a8cdb31ce`;
the outcome document SHA-256 is
`85b63909743da20a0b68e9d2fc130d0120f99e88036653586f7507766cf5d6f9`.

The downstream-MIDI plan can be reproduced without opening audio or writing
MIDI:

```bash
.venv/bin/python scripts/plan-fine-stem-downstream-midi.py \
  SIX-ROLE-INTEGRATION-ROOT \
  FRESH/fine-stem-six-role-integration-outcome-v1/INTEGRATION-OUTCOME.json \
  --out FRESH/fine-stem-downstream-midi-plan-v1
```

Its SHA-256 is
`7afab38b0bd446e2de75b4c408b1e275e533298765f25d89280c055fbb63e1e4`.
The plan records exact BPM/key/tuning metadata rather than guessing, uses the
existing synth transcriber and the disclosed conservative polyphonic-keys
transcriber for guitar, and grants no execution or source-selection authority.

The single approved forward completed in 18.19 seconds at 15,424,362,972-byte
peak MLX allocation. Its exact `[1, 53, 2, 881664]` float32 output was finite,
mapped `synth` at index 38 and reconstructed the generated input plus residual
within `9.313225746154785e-10`. The guard recorded one checkpoint load, one
forward call and zero network or audio attempts. Report SHA-256 is
`07d8af0ccd913914f509a75015476c9a0efe85bb89639514032c138420ec3f10`.
The authority is consumed. This proves the adapter executes; it is not musical
usefulness evidence and grants no song processing, activation, selection or
MIDI authority.

Failure of an objective gate stops this candidate or uses its single
remediation. Poor listening does not. Public activation, hosted conversion,
source selection and MIDI remain separate decisions.
