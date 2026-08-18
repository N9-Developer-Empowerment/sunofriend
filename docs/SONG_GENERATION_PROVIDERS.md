# Song-generation provider policy

Status: provider capability registry implemented; ACE-Step reference and native
remix routes registered; TREBLO evaluated but not registered; MiniMax candidate
routes documented for empirical evaluation

Last verified: 18 August 2026

## Purpose

Sunofriend may use local models, self-hosted services or optional third-party
APIs behind one evidence contract. A provider is not interchangeable merely
because it can generate a song: it must truthfully support the inputs and
controls required by the selected operation.

Run this read-only command to inspect the current machine-readable inventory:

```console
sunofriend song-providers
```

The inventory contains no API-key values and performs no network request.
Evaluated providers may be listed without being executable. The selected
provider must be registered for the requested operation; the current CLI
exposes ACE-Step for both `reference_conditioned_full_song` and
`native_audio_remix`.

## Current matrix

| Capability | ACE-Step 1.5 API | TREBLO Melodia v3 API |
| --- | --- | --- |
| Provider type | Open-weight local or self-hosted | Proprietary BYO-key cloud |
| Prompt and supplied lyrics | Yes | Yes |
| Exact supplied lyric-text transport | Adapter passes exact text | API accepts supplied text |
| Agreed section/production annotation semantics | Not yet verified by listening test | Not yet verified |
| General reference-audio conditioning | Yes | No documented v3 endpoint |
| Native source-audio cover/remix with replacement lyrics | Yes; source-locked duration | No general remix endpoint documented |
| Source-audio continuation | Yes | Yes |
| Independent reference-strength control | Yes | No |
| Style-strength control | Base-model guidance mapping | Native style scale, not yet calibrated to Sunofriend's 0–1 control |
| Songs per provider request | Two | One; two alternatives require two tasks |
| Deterministic seed | Available | Not in v3 |
| Explicit BPM | Backend-dependent | Not in v3 |
| Result retention | Local destination | Remote URLs expire after 168 hours |
| Current registration | Registered | Evaluated, not registered |

TREBLO v3 can help with a future prompt-and-lyrics-only operation. Its source
audio endpoint extends an existing recording; it does not document “make a new
song generally influenced by this complete reference.” Submitting the current
reference-conditioned request while ignoring the reference or its strength
would violate the agreed product contract, so Sunofriend does not silently do
that.

A future reference-analysis bridge could extract reviewed abstract traits from
the authorised reference and turn them into provider-neutral musical evidence.
That would be a new, explicit workflow with its own tests; it would not be
described as native TREBLO reference conditioning.

The ACE-Step adapter has two explicitly different modes. Default `reference`
mode maps to `text2music` and streams multipart `reference_audio`; optional
explicit BPM, key, time signature and duration are real API fields, while
omitted values remain available for LM inference. `--generation-mode remix`
maps to native `cover` and streams multipart `src_audio` with replacement
lyrics. Native cover locks duration to its source and the adapter rejects
claimed independent BPM, key, meter or duration overrides. This is a remix
operation, not a synonym for creative-reference generation.

Windows RTX 4080 Laptop GPU trials completed two 199-232 second reference-mode
candidates per request and a two-candidate 237.56-second native-remix request
with Base plus the 0.6B LM and CPU offload. Execution, requested-checkpoint
identity, exact lyric transport and audio validity are verified. The native
pair still awaits the owner's judgement on tuning, actually performed lyric
coverage, creative value and downstream stem/MIDI usefulness, so its quality
capability remains false in the registry.

## MiniMax routes under evaluation

MiniMax currently exposes two materially different routes and Sunofriend must
not merge their names or capabilities:

- The downloadable **MiniMax Music 3** checkpoint documents complete-song
  generation from lyrics and a detailed music description. Its published local
  serving route uses two CUDA GPUs. The released interface does not document a
  reference-audio input, reference-strength control, repaint operation or LoRA
  training path. Sunofriend may evaluate it through an explicitly labelled
  reference-analysis/structured-caption bridge, but that is not native remix.
- The hosted **`music-cover` / `music-cover-free`** API model accepts reference
  audio, a target cover-style prompt and optional replacement lyrics. It is a
  separate model family from API `music-3.0`, and the current API documentation
  does not expose an independent reference-strength control. It may be tested as
  an opt-in BYO-key cloud method, but does not yet meet the complete registered
  operation contract.

An ordinary style LoRA would personalise an existing input route; it would not
by itself add missing audio conditioning to Music 3. Genuine Music 3 remix
research would require a reference encoder/conditioning path, a learned
strength signal and paired training evidence. That research is tracked as an
option in
[`REFERENCE_CONDITIONED_SONG_GENERATION_EVALUATION_PLAN.md`](REFERENCE_CONDITIONED_SONG_GENERATION_EVALUATION_PLAN.md),
not presented as a current laptop capability.

## Bring-your-own-key rules

An optional cloud adapter must:

- remain disabled until the user explicitly selects it;
- read an individual user's key from an environment variable or local secret
  store and never commit, print or place that value in a receipt;
- never send a shared API key to browser JavaScript;
- show that audio, lyrics and prompts leave the machine;
- require explicit terms, privacy and possible-cost acknowledgement before the
  first network call;
- use polling unless authenticated webhook signing is documented and
  implemented;
- immediately download every successful output, hash it and record the task ID,
  provider/model version and exact request mapping;
- display required provider attribution in user-facing invocation surfaces; and
- never describe the proprietary service as locally runnable or open-weight.

For TREBLO, the proposed environment variable is
`SUNOFRIEND_TREBLO_API_KEY`. Sunofriend has no shared project key.

## Terms and operational caution

TREBLO's developer pricing advertises production API plans and requires
attribution for user-facing integrations. Its general terms also contain broad
restrictions on automated, competitive and commercial use, while separately
stating that restrictions on commercial use of the service do not limit use of
generated outputs. Before a public hosted, multi-user or competitive service is
enabled, obtain current legal review and preferably written confirmation from
TREBLO. This document is an engineering boundary, not legal advice.

With bring-your-own-key, the end user is the API customer. A future shared-key
hosted service would have different billing, privacy and output-rights handling
and is outside the current scope.

## Evidence sources

- [TREBLO API documentation](https://treblo.com/developers/docs)
- [TREBLO developer pricing](https://treblo.com/developers/pricing)
- [TREBLO terms of service](https://treblo.com/tos)
- [ACE-Step 1.5 repository](https://github.com/ace-step/ACE-Step-1.5)
- [MiniMax Music 3 repository](https://github.com/MiniMax-AI/MiniMax-Music3)
- [MiniMax music API documentation](https://platform.minimax.io/docs/api-reference/music-generation)

Provider behaviour, prices and terms can change. Re-verify them before enabling
or materially changing an adapter.
