# Reference-conditioned song generation

Status: iterative product goal agreed; reference-conditioned and native-remix
ACE-Step modes implemented on Windows; whole-song and track-level ACE Base
approaches rejected for the current fixture; final Turbo pair awaiting review

Discovery completed: 16 August 2026

Iterative workflow refinement: 17 August 2026

Native remix evidence: 18 August 2026

Source: twenty-question product interview with the project owner

## Implementation progress

Implemented on the current feature branch:

- a path-free, hash-bound generation request contract and durable success or
  failure receipt;
- a read-only-by-default `sunofriend song-generate` CLI operation with explicit
  execution and rights-confirmation gates;
- exactly two candidate outputs, independent reference/style controls and
  model-selected duration in the default reference-conditioned contract;
- a first adapter for an already running ACE-Step API using a Base model,
  multipart audio transport, `audio_cover_strength` and `guidance_scale`;
- a distinct `--generation-mode remix` route that maps to ACE-Step's native
  `cover` task and `src_audio`, truthfully records its source-locked duration,
  and rejects unsupported independent BPM/key/meter/duration locks;
- a secret-free `song-providers` capability registry that can describe local,
  self-hosted and BYO-key cloud providers without treating unlike operations as
  interchangeable; and
- agent-skill and website capability documentation for the new boundary.

Still to validate or implement:

- a whole-song method that meets the Suno benchmark: the retained native-remix
  pair was in tune but rejected for monotonic talk-singing, unmusical
  accompaniment and lack of enjoyment or creativity;
- owner listening review of one intentionally configured Turbo native-remix
  pair, the last bounded ACE model-quality check; it produced two valid audio
  candidates, but Turbo cannot honour the independent style-strength control
  because ACE documents guidance scale as Base-only;
- the bounded, successive-gate comparison in
  [`REFERENCE_CONDITIONED_SONG_GENERATION_EVALUATION_PLAN.md`](REFERENCE_CONDITIONED_SONG_GENERATION_EVALUATION_PLAN.md);
- empirical calibration of both strength mappings and lyric annotations;
- a service lifecycle command or approved setup workflow (the generation
  command deliberately does not install or start a model server);
- backend selection beyond the first ACE-Step API adapter; and
- an immutable song-project/version graph, section and stem revision operations,
  project-level authorisation settings, and equivalent TUI/web controls after
  the CLI contract is proven.

## Product goal

Sunofriend should turn one authorised reference recording, a separately
annotated lyric sheet and a written style description into **two new,
complete, enjoyable songs**. Each result should be ready to listen to as a
finished track and useful as source material for further human production in
Sunofriend.

Generation is the beginning of an iterative production process, not the final
operation. The musician must be able to keep, compare, branch, revise and
replace material without destroying an earlier candidate. A selected sketch
then moves through separation, editable MIDI reconstruction, human arrangement
and human vocal recording. Vocal comping happens after the AI-assisted remix
and arrangement have settled, not before them.

The intended final master may contain only human vocals and user-selected
MIDI/human-rendered instruments. It is therefore accurate to describe the
result as **AI-assisted composition and arrangement with no generated audio in
the final master** when that audit passes. It would be inaccurate to claim
that no part of the musical composition or arrangement was AI-assisted.

The reference is creative guidance, not a template. A result may be generally
similar in musical character while changing the structure, melody, chords,
tempo, key, rhythm, instrumentation and vocal phrasing. The generator should
infer useful high-level traits automatically and must not deliberately copy an
identifiable melody, riff, lyric or arrangement passage from the reference.

The first success criterion is deliberately subjective: the project owner
hears two enjoyable full songs and considers at least one of them good enough
to continue producing in Sunofriend. A vocal song is not listenable merely
because it contains a voice: its lead must be acceptably in tune with the
arrangement and deliver the intended lyrics without singing control metadata.

## Standing personal-use authorisation

For the owner's private projects, Sunofriend assumes that every imported track
is authorised for private personal use. That scope is recorded once in the
song-project manifest and inherited by local operations; the interface should
not ask the same rights question before every local generation or analysis
run.

This standing assumption does not grant model-execution authority, publish an
asset or approve a network transfer. Selecting a cloud/API backend remains a
separate explicit decision because it sends private audio or text to another
party and may accept provider terms or incur a charge. That acknowledgement is
about privacy, provider terms and cost rather than repeating the track-rights
question.

The implemented `song-generate --execute --confirm-rights` gate predates this
project-level design. It remains truthful for the current vertical slice until
a versioned project manifest and migration are implemented.

## Target iterative journey

1. The user selects a full reference song or an excerpt.
2. Sunofriend imports it into a private song project, records its hash and
   inherits the standing personal-use authorisation scope.
3. Sunofriend automatically analyses useful musical traits. The default route
   does not require the user to configure those traits separately; an advanced
   review may correct a clearly wrong inference.
4. The user supplies separate annotated lyrics and a written style description.
5. The user independently sets reference strength and style-description
   strength.
6. An agent skill submits the same backend-neutral request through a CLI, TUI
   or web interface.
7. The selected backend generates two complete song alternatives as sibling
   branches.
8. The user auditions both and may keep neither, one or both. Every subsequent
   operation creates a child version rather than overwriting its parent.
9. The user may regenerate a whole song, revise one section, extend or shorten
   the arrangement, change a named musical property, or add/remove/replace a
   stem when the selected backend truthfully supports that operation.
10. A selected version enters separation and editable MIDI reconstruction.
    Generated stems may remain temporarily as production guides while the user
    replaces instruments with MIDI or human performances in GarageBand.
11. The user records human vocal takes against the settled arrangement and uses
    vocal comping to replace the generated guide vocal.
12. Sunofriend exports audio, MIDI, stems and decision/provenance manifests and
    reports whether any generated audio remains in the final master.

At every creative stage, the shared operations are: accept or lock; adjust and
regenerate; branch; compare; revert; and replace with human or MIDI material.
The correct persistence model is therefore a version graph rather than one
mutable linear checklist.

## Current implemented vertical slice

The current CLI deliberately implements only steps 1 and 4-8 for whole-song
generation. If neither candidate is useful, it changes the lyrics, prompt or
strengths and generates two complete songs again. It does not yet create a
project graph, inherit a project-level authorisation setting, lock regions,
repair a section or replace a stem. Those are planned capabilities, not claims
about the present command.

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

The user-authored annotated document remains canonical, but it is not blindly
copied into every backend's lyrics field. A provider adapter must compile a
backend-safe transport: keep the exact words and concise temporal tags; route
long production descriptions into the caption; route BPM, key, meter or similar
metadata into dedicated controls only when the user has actually locked them.
The receipt records the canonical hash, transported hash and every cue mapping.
No adapter may silently drop a cue, and metadata such as `120 BPM` must not be
exposed to a model as text it may sing.

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

For production-oriented requests, arrangement quality includes distinct,
musically useful drums, bass, synth and other named roles with stable timing and
limited masking so downstream stem separation and MIDI transcription are
practical. The generated lead vocal is a guide and part of an enjoyable full
song, but should not automatically dominate the accompaniment.

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

### Iterative project record

The target project record retains immutable version nodes and explicit parent
edges. A version node binds its input hashes, operation, selected backend,
parameters, generated assets and review status. An edge records why a child
exists, for example `whole_song_regeneration`, `section_repaint`,
`arrangement_extension`, `stem_replacement`, `midi_reconstruction` or
`human_vocal_comp`.

Locks apply to declared sections, time ranges or stems and must never be
silently ignored. A backend that cannot honour the requested lock is
ineligible for that operation. The user may compare any siblings or ancestors,
and deleting a working selection must not erase its retained provenance.

The project record also distinguishes generated source audio from the final
render. A final "no generated audio remains" result requires evidence that all
audible generated stems and vocals have been replaced or deliberately excluded;
MIDI derived from a generated arrangement remains AI-assisted musical evidence.

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

The receipt must verify the checkpoint or hosted model actually reported for
every candidate. A missing identity or silent substitution is a failed run,
even when valid audio was returned.

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

## Current vertical-slice non-goals

- Preserving the reference song's exact form, melody, chords, key or tempo.
- Directly copying identifiable material from the reference.
- Asking the user to configure individual similarity dimensions.
- Regenerating, inpainting or repairing a selected section in the current CLI;
  section revision is part of the target iterative workflow.
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
6. generated lead vocals are acceptably in tune and deliver the supplied words;
7. the user subjectively considers the results enjoyable; and
8. at least one result is good enough to continue through Sunofriend's
   separation, MIDI reconstruction and human-vocal production workflow.

Automated audio validity, provenance and reproducibility checks support this
decision but cannot replace the listening judgement.

The later iterative-production acceptance demonstration additionally passes
when the user can branch from a retained candidate, improve at least one weak
part without losing the parent, reconstruct useful editable musical material,
record and comp human vocals after the arrangement, and export an auditable
final master. The first empirical fixture will be an owner-made track containing
sample initial vocals and music plus separate target annotated lyrics. Private
audio is not committed to this repository.

## Implementation questions to answer empirically

The staged protocol, comparison matrix, listening rubric and stop/replan gates
are defined in
[`REFERENCE_CONDITIONED_SONG_GENERATION_EVALUATION_PLAN.md`](REFERENCE_CONDITIONED_SONG_GENERATION_EVALUATION_PLAN.md).

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
- Is native reference conditioning materially more useful than a reviewed
  reference-analysis bridge for downstream Sunofriend production?
- Which revision unit should be implemented first after whole-song generation:
  section/time range, arrangement/stem, or both behind capability gates?
- Can a selected result be separated and transcribed into MIDI that is easier
  to finish than the owner's initial arrangement?
- Can the complete downstream process remove all generated audio while
  retaining the useful AI-assisted musical decisions?
