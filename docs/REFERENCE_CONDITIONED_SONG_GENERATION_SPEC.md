# Reference-conditioned song generation

Status: product goal agreed; first backend-neutral vertical slice implemented

Discovery completed: 16 August 2026

Source: twenty-question product interview with the project owner

## Implementation progress

Implemented on the current feature branch:

- a path-free, hash-bound generation request contract and durable success or
  failure receipt;
- a read-only-by-default `sunofriend song-generate` CLI operation with explicit
  execution and rights-confirmation gates;
- exactly two candidate outputs, independent reference/style controls and
  model-selected duration in the public interface contract;
- a first adapter for an already running ACE-Step API using a Base model,
  shared-filesystem reference transport, `audio_cover_strength` and
  `guidance_scale`; and
- a secret-free `song-providers` capability registry that can describe local,
  self-hosted and BYO-key cloud providers without treating unlike operations as
  interchangeable; and
- agent-skill and website capability documentation for the new boundary.

Still to validate or implement:

- a real two-song generation run on the RTX 4080 Laptop GPU and subjective
  listening acceptance;
- empirical calibration of both strength mappings and lyric annotations;
- a service lifecycle command or approved setup workflow (the generation
  command deliberately does not install or start a model server);
- backend selection beyond the first ACE-Step API adapter; and
- equivalent TUI/web controls after the CLI contract is proven.

## Product goal

Sunofriend should turn one authorised reference recording, a separately
annotated lyric sheet and a written style description into **two new,
complete, enjoyable songs**. Each result should be ready to listen to as a
finished track and useful as source material for further human production in
Sunofriend.

The reference is creative guidance, not a template. A result may be generally
similar in musical character while changing the structure, melody, chords,
tempo, key, rhythm, instrumentation and vocal phrasing. The generator should
infer useful high-level traits automatically and must not deliberately copy an
identifiable melody, riff, lyric or arrangement passage from the reference.

The first success criterion is deliberately subjective: the project owner
hears two enjoyable full songs and considers at least one of them good enough
to continue producing in Sunofriend.

## First-release journey

1. The user selects a full reference song or an excerpt.
2. The user affirms that they are authorised to process it for private personal
   use.
3. The user supplies separate annotated lyrics and a written style description.
4. The user independently sets reference strength and style-description
   strength.
5. An agent skill submits the same backend-neutral request through a CLI, TUI
   or web interface.
6. The selected backend generates two complete song alternatives.
7. Sunofriend retains the songs and their generation receipts for comparison.
8. If neither result is suitable, the user changes the lyrics, prompt or either
   strength and generates two complete songs again.
9. A selected result can enter the existing Sunofriend production workflow,
   where generated instruments may be reconstructed with MIDI instruments and
   generated vocals may be replaced with recorded human vocals and vocal
   comping.

The first release regenerates whole songs. It does not repair or regenerate an
individual section.

## Inputs

### Reference audio

- The normal input is a complete reference song.
- An excerpt is also valid.
- Reference duration does not determine output duration.
- The model automatically infers which abstract characteristics are useful.
- The user is not asked to select separate reference dimensions such as key,
  groove, range, energy or instrumentation.

### Annotated lyrics

Lyrics are supplied separately from the reference recording. Annotations are
lightweight song and production directions, for example:

```text
[intro]

[verse]
...

[chorus]
...

[instrumental break]

[full band comes back in]
...

[outro]
```

The lyrics define how much lyrical material the new song must accommodate.
They do not impose a fixed duration or note-by-note timing.

### Style description

The style description is free descriptive language. Genre, era, mood,
instrumentation, vocal character and production language are useful. The
interface does not reject or silently remove artist-derived words such as
`Beatlesque`, or artist and song names, but it does not promise that a model
understands them. Descriptive musical language is preferred over relying on a
proper name.

### Independent strength controls

The request has two independent controls:

- **Reference strength** controls how strongly the output is influenced by the
  reference recording's automatically inferred, generalised musical traits.
- **Style-description strength** controls how strongly the output follows the
  written style description.

Neither control grants permission to copy material. Their ranges and exact
backend mappings must be calibrated empirically rather than pretending that
different models expose identical scales.

## Required generation behaviour

The generator should:

- create a new song rather than preserve the reference composition;
- use some automatically inferred reference characteristics as a starting
  point;
- follow the annotated lyrics and production cues;
- choose an appropriate song structure, tempo and duration;
- add an intro, breaks, instrumental passages or an outro when musically useful;
- change BPM when that better serves the requested style and lyric length;
- generate a complete arrangement, lead vocal and any useful additional
  vocals; and
- return two alternatives from a normal request.

The lead vocal should, when technically possible and appropriate to the style
description, preserve the reference vocalist's recognisable identity. If that
is not possible, it should preserve useful abstract traits such as vocal range,
energy, register and delivery. The model may add backing vocals, harmonies,
doubles or contrasting singers.

This is a best-effort creative requirement, not a promise that every backend
can reproduce identity. The Sunofriend workflow uses one general authorisation
affirmation for the reference; it does not add a separate voice-specific
approval step. An external backend may still impose its own terms and safety
requirements.

## Outputs

Each normal request returns two full-length, listener-ready song candidates.
The required first output is a complete mixed track containing its generated
instrumentation and vocals. Direct stem and MIDI generation are not required
from the generation backend in the first release: Sunofriend can separate,
transcribe and reconstruct a selected candidate afterwards.

Every completed or failed request should retain a generation receipt. Where
the backend makes the data available, the receipt contains:

- request and candidate identifiers;
- reference and lyric asset hashes;
- the exact annotated lyrics and style description;
- reference-strength and style-strength values plus their backend mappings;
- backend, model, checkpoint and adapter versions;
- seed and inference settings;
- start time, finish time and generation duration;
- the user's authorisation affirmation;
- candidate paths, formats, durations and hashes; and
- an explicit statement when exact deterministic reproduction is unavailable.

Exact regeneration is required when the backend can guarantee it and is
best-effort otherwise.

## Backend and interface contract

The product contract must not depend on a single model or hosting location.
Local models, a hosted deployment and third-party APIs should be interchangeable
behind one Sunofriend request and receipt contract. Local inference is a likely
first implementation because the current machine is available, but it has no
permanent priority in the product design.

Interchangeability is capability-gated. A provider may be documented without
being registered for this operation. Registration requires genuine support for
the authorised reference audio, annotated lyrics, two independent strength
controls and two retained candidates; Sunofriend must not silently discard an
input or simulate support with an unrelated endpoint.

Cloud providers are optional and bring-your-own-key. They require explicit
selection plus terms, privacy and possible-cost acknowledgement before any
network call. Keys must remain in the user's environment or secret store and
must never enter a plan, receipt, browser bundle or repository. Remote outputs
must be archived locally immediately with hashes and task/model evidence. See
[`SONG_GENERATION_PROVIDERS.md`](SONG_GENERATION_PROVIDERS.md).

TREBLO Melodia v3 has been evaluated as a future prompt-and-lyrics cloud
provider, but is not registered for `reference_conditioned_full_song`. Its v3
API documents one song per task and source audio for continuation, not general
reference conditioning or an independent reference-strength control.

The primary user experience is an agent skill. The skill may drive the same
capability through the CLI, TUI or web interface; those interfaces must not
develop incompatible definitions of the request.

On the current RTX 4080 Laptop GPU, a run taking up to about 60 minutes is
acceptable. Generation time is not a hard product constraint for local,
private use. Musical usefulness takes priority over realtime output.

## First-release non-goals

- Preserving the reference song's exact form, melody, chords, key or tempo.
- Directly copying identifiable material from the reference.
- Asking the user to configure individual similarity dimensions.
- Regenerating, inpainting or repairing a selected section.
- Making the reference duration determine the new song duration.
- Requiring offline-only execution.
- Requiring the generation backend itself to return stems or MIDI.
- Falling back to a prompt-only cloud provider while claiming it used the
  reference audio.
- Guaranteeing singer-identity preservation on an incapable backend.
- Guaranteeing bit-identical reproduction when a backend cannot provide it.

## Acceptance demonstration

The first end-to-end demonstration passes when:

1. one authorised full song or excerpt is submitted;
2. a separate lyric sheet containing section and production annotations is
   supplied;
3. a descriptive style prompt is supplied;
4. reference strength and style-description strength can be changed
   independently and are recorded accurately;
5. the system generates two distinct, complete, listenable songs;
6. the user subjectively considers the results enjoyable; and
7. at least one result is good enough to continue through Sunofriend's
   separation, MIDI reconstruction and human-vocal production workflow.

Automated audio validity, provenance and reproducibility checks support this
decision but cannot replace the listening judgement.

## Implementation questions to answer empirically

These are engineering questions, not missing product decisions:

- Which available backend best supports reference audio, annotated lyrics and
  full-song vocal generation on the current hardware?
- How should the two strength controls map onto each backend without implying
  false equivalence?
- Which annotation vocabulary is reliably understood directly, and which cues
  require translation into a backend-specific prompt?
- What audio format, sample rate and loudness target make a candidate easiest
  to audition and process in Sunofriend?
- How consistently can each backend preserve vocal identity or abstract vocal
  traits without copying reference composition?
- Which backend settings produce two meaningfully different alternatives while
  remaining reproducible?
- What maximum lyric length and generated duration are reliable on local,
  hosted and API backends?
