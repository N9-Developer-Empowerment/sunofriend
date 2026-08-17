# Song-generation provider policy

Status: provider capability registry implemented; ACE-Step registered; TREBLO
evaluated but not registered for reference-conditioned generation

Last verified: 17 August 2026

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
Evaluated providers may be listed without being executable. Only a provider
registered for `reference_conditioned_full_song` may be selected by
`song-generate --backend`.

## Current matrix

| Capability | ACE-Step 1.5 API | TREBLO Melodia v3 API |
| --- | --- | --- |
| Provider type | Open-weight local or self-hosted | Proprietary BYO-key cloud |
| Prompt and supplied lyrics | Yes | Yes |
| Exact supplied lyric-text transport | Adapter passes exact text | API accepts supplied text |
| Agreed section/production annotation semantics | Not yet verified by listening test | Not yet verified |
| General reference-audio conditioning | Yes | No documented v3 endpoint |
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

Provider behaviour, prices and terms can change. Re-verify them before enabling
or materially changing an adapter.
