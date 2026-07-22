(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.SunofriendWorkbenchClips = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const DEFAULT_LIMIT = 24;
  const CORRECTION_TICKS_PER_BEAT = 480;
  const DEFAULT_CORRECTION_WINDOW_BEATS = 8;
  const MAXIMUM_CORRECTION_WINDOW_BEATS = 32;
  const MAXIMUM_CORRECTION_CHANGES = 64;
  const MAXIMUM_CORRECTION_PITCH_DELTA = 24;
  const CORRECTION_KIND_PITCH = "pitch_patch";
  const CORRECTION_KIND_VELOCITY = "attack_velocity_patch";
  const CORRECTION_KIND_DELETE = "note_delete_patch";
  const PITCH_CORRECTION_EFFECT_KEYS = Object.freeze([
    "child_clip_created", "chords_changed", "correction_applied",
    "current_arrangement_changed", "data_submitted", "feedback_recorded",
    "hybrid_created", "instrument_changed", "key_changed", "library_mutated",
    "note_count_changed", "note_pitch_changed", "note_timing_changed",
    "pack_changed", "placement_changed", "provenance_changed",
    "reuse_plan_changed", "source_clip_mutated",
  ]);
  const VELOCITY_CORRECTION_EFFECT_KEYS = Object.freeze([
    "child_clip_created", "chords_changed", "correction_applied",
    "current_arrangement_changed", "data_submitted", "feedback_recorded",
    "hybrid_created", "instrument_changed", "key_changed", "library_mutated",
    "note_attack_velocity_changed", "note_count_changed", "note_pitch_changed",
    "note_timing_changed", "pack_changed", "placement_changed",
    "provenance_changed", "release_velocity_changed", "reuse_plan_changed",
    "source_clip_mutated",
  ]);
  const DELETE_CORRECTION_EFFECT_KEYS = Object.freeze([
    "child_clip_created", "chords_changed", "correction_applied",
    "current_arrangement_changed", "data_submitted", "feedback_recorded",
    "hybrid_created", "instrument_changed", "key_changed", "library_mutated",
    "note_attack_velocity_changed", "note_count_changed", "note_deleted",
    "note_pitch_changed", "note_timing_changed", "pack_changed",
    "placement_changed", "provenance_changed", "release_velocity_changed",
    "reuse_plan_changed", "source_clip_mutated",
  ]);
  const CORRECTION_CONTRACTS = Object.freeze({
    [CORRECTION_KIND_PITCH]: Object.freeze({
      kind: CORRECTION_KIND_PITCH,
      id: "pitch",
      label: "Pitch (MIDI note number)",
      name: "pitch",
      changeName: "pitch",
      resultName: "pitch-corrected",
      windowDiscriminator: false,
      windowSchema: "sunofriend.workbench-clip-correction-window.v1",
      windowOperation: "clip-correction-window",
      previewSchema: "sunofriend.workbench-clip-correction-preview.v1",
      previewOperation: "clip-correction-preview",
      resultSchema: "sunofriend.workbench-clip-correction-result.v1",
      resultOperation: "clip-correction-create",
      effectKeys: PITCH_CORRECTION_EFFECT_KEYS,
      freshEffectKeys: Object.freeze(["library_mutated", "child_clip_created", "correction_applied", "note_pitch_changed"]),
    }),
    [CORRECTION_KIND_VELOCITY]: Object.freeze({
      kind: CORRECTION_KIND_VELOCITY,
      id: "velocity",
      label: "Attack loudness (MIDI velocity)",
      name: "attack velocity",
      changeName: "attack-velocity",
      resultName: "attack-velocity-corrected",
      windowDiscriminator: true,
      windowSchema: "sunofriend.workbench-clip-attack-velocity-window.v1",
      windowOperation: "clip-attack-velocity-window",
      previewSchema: "sunofriend.workbench-clip-attack-velocity-preview.v1",
      previewOperation: "clip-attack-velocity-correction-preview",
      resultSchema: "sunofriend.workbench-clip-attack-velocity-result.v1",
      resultOperation: "clip-attack-velocity-correction-create",
      effectKeys: VELOCITY_CORRECTION_EFFECT_KEYS,
      freshEffectKeys: Object.freeze(["library_mutated", "child_clip_created", "correction_applied", "note_attack_velocity_changed"]),
    }),
    [CORRECTION_KIND_DELETE]: Object.freeze({
      kind: CORRECTION_KIND_DELETE,
      id: "delete",
      label: "Remove unwanted notes (new immutable version)",
      name: "note removal",
      changeName: "note-removal",
      resultName: "note-removal",
      windowDiscriminator: true,
      windowSchema: "sunofriend.workbench-clip-note-deletion-window.v1",
      windowOperation: "clip-note-deletion-window",
      previewSchema: "sunofriend.workbench-clip-note-deletion-preview.v1",
      previewOperation: "clip-note-deletion-correction-preview",
      resultSchema: "sunofriend.workbench-clip-note-deletion-result.v1",
      resultOperation: "clip-note-deletion-correction-create",
      effectKeys: DELETE_CORRECTION_EFFECT_KEYS,
      freshEffectKeys: Object.freeze(["library_mutated", "child_clip_created", "correction_applied", "note_count_changed", "note_deleted"]),
    }),
  });
  const DELETE_WINDOW_NOTE_KEYS = Object.freeze([
    "articulation", "channel", "duration_beats", "edit_block_reason", "editable",
    "end_tick", "export_note_on_group_size", "note_ref", "pitch", "release_velocity",
    "source_end_seconds", "source_start_seconds", "start_beat", "start_tick", "velocity",
  ]);
  const DELETE_DIFF_KEYS = Object.freeze([
    "changed_note_count", "changes", "duration_beats_after", "duration_beats_before",
    "duration_seconds_after", "duration_seconds_before", "kind", "normalized_midi_note_count_after",
    "normalized_midi_note_count_before", "note_count_after", "note_count_before",
    "pitch_range_after", "pitch_range_before", "retained_normalized_notes_changed", "unchanged",
  ]);
  const DELETE_DIFF_ROW_KEYS = Object.freeze([
    "articulation", "channel", "duration_beats", "end_tick", "note_ref", "pitch",
    "release_velocity", "source_end_seconds", "source_start_seconds", "start_beat",
    "start_tick", "velocity",
  ]);
  const DELETE_IDENTITY_KEYS = Object.freeze([
    "bpm", "chord_count", "clip_id", "duration_seconds", "key", "lineage_id",
    "note_count", "object_sha256", "parent_clip_id", "pitch_range", "revision",
    "role", "role_redacted",
  ]);
  const DELETE_BLOCK_REASONS = Object.freeze([
    "clip-horizon-would-change", "context-note-on-outside-window", "duplicate-export-note-on",
    "only-note-in-clip", "retained-note-lifetime-would-change",
  ]);
  const DELETE_UNCHANGED_KEYS = Object.freeze([
    "articulation", "chords", "clip_horizon", "instrument", "key", "microtiming",
    "normalized_midi_survivors", "note_durations", "note_onsets", "note_pitches",
    "provenance", "release_velocity", "retained_note_payloads", "source_seconds",
    "tempo_map", "timing_mode", "velocity",
  ]);
  const KEY_TONICS = Object.freeze(["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]);

  function createClipLibrary({ api, escapeHtml }) {
    if (typeof api !== "function") throw new Error("Clip Library requires the Workbench API");
    const esc = typeof escapeHtml === "function" ? escapeHtml : fallbackEscape;
    let capability = null;
    let reuseCapability = null;
    let transformCapability = null;
    let correctionCapability = null;
    let host = null;
    let mode = "browse";
    let detailReturnMode = "browse";
    let listDocument = null;
    let detailDocument = null;
    let planDocument = null;
    let currentClipId = null;
    let loading = false;
    let planLoading = false;
    let actionPending = false;
    let errorMessage = "";
    let planErrorMessage = "";
    let actionErrorMessage = "";
    let statusMessage = "";
    let planStatusMessage = "";
    let transformProjection = null;
    let transformProjectionTransform = null;
    let transformResult = null;
    let transformPending = "";
    let transformErrorMessage = "";
    let transformStatusMessage = "";
    let pendingTransformFocusId = "";
    let correctionWindowDocument = null;
    let correctionWindowContract = null;
    let correctionProjection = null;
    let correctionProjectionCorrection = null;
    let correctionResult = null;
    let correctionPending = "";
    let correctionErrorMessage = "";
    let correctionStatusMessage = "";
    let pendingCorrectionFocusId = "";
    let pendingCorrectionFocusRef = "";
    let observedLibraryCount = null;
    let libraryEvidenceStale = false;
    let requestSequence = 0;
    let planRequestSequence = 0;
    let transformRequestSequence = 0;
    let correctionRequestSequence = 0;
    const artifacts = new Map();
    const placementDrafts = new Map();
    const transformDrafts = new Map();
    const correctionDrafts = new Map();
    const filters = { text: "", role: "", key: "", bpm: "", tags: "", offset: 0 };

    function setCapability(value, optionalReuseCapability = null, optionalTransformCapability = null, optionalCorrectionCapability = null) {
      const wasReuseEnabled = reuseEnabled();
      const wasTransformEnabled = transformEnabled();
      const wasCorrectionEnabled = correctionEnabled();
      capability = value && value.enabled === true ? value : null;
      reuseCapability = optionalReuseCapability && optionalReuseCapability.enabled === true
        ? optionalReuseCapability
        : null;
      transformCapability = optionalTransformCapability && optionalTransformCapability.enabled === true
        ? optionalTransformCapability
        : null;
      correctionCapability = optionalCorrectionCapability && optionalCorrectionCapability.enabled === true
        ? optionalCorrectionCapability
        : null;
      if (!capability) reset();
      if (wasReuseEnabled !== reuseEnabled()) resetReuseState();
      if (wasTransformEnabled !== transformEnabled()) resetTransformState(true);
      if (wasCorrectionEnabled !== correctionEnabled()) resetCorrectionState(true);
    }

    function enabled() {
      return capability !== null;
    }

    function reuseEnabled() {
      return capability !== null && reuseCapability !== null;
    }

    function transformEnabled() {
      return capability !== null && transformCapability !== null;
    }

    function correctionEnabled() {
      return capability !== null && correctionCapability !== null;
    }

    function reset() {
      stopAudio();
      mode = "browse";
      detailReturnMode = "browse";
      listDocument = null;
      detailDocument = null;
      currentClipId = null;
      loading = false;
      errorMessage = "";
      statusMessage = "";
      requestSequence += 1;
      artifacts.clear();
      observedLibraryCount = null;
      libraryEvidenceStale = false;
      resetReuseState();
      resetTransformState(true);
      resetCorrectionState(true);
    }

    function resetReuseState() {
      if (mode === "plan") mode = "browse";
      planDocument = null;
      planLoading = false;
      actionPending = false;
      planErrorMessage = "";
      actionErrorMessage = "";
      planStatusMessage = "";
      planRequestSequence += 1;
      placementDrafts.clear();
    }

    function resetTransformState(clearDrafts = false) {
      transformProjection = null;
      transformProjectionTransform = null;
      transformResult = null;
      transformPending = "";
      transformErrorMessage = "";
      transformStatusMessage = "";
      pendingTransformFocusId = "";
      transformRequestSequence += 1;
      if (clearDrafts) transformDrafts.clear();
    }

    function resetCorrectionState(clearDrafts = false) {
      correctionWindowDocument = null;
      correctionWindowContract = null;
      correctionProjection = null;
      correctionProjectionCorrection = null;
      correctionResult = null;
      correctionPending = "";
      correctionErrorMessage = "";
      correctionStatusMessage = "";
      pendingCorrectionFocusId = "";
      pendingCorrectionFocusRef = "";
      correctionRequestSequence += 1;
      if (clearDrafts) correctionDrafts.clear();
    }

    function stopAudio() {
      if (!host) return;
      host.querySelectorAll("audio").forEach((audio) => audio.pause());
    }

    function renderInto(element) {
      host = element;
      if (!enabled()) {
        host.innerHTML = '<section class="panel"><h2>Clip Library unavailable</h2><p>The read-only Phase 6 entry has not been enabled for this Workbench launch.</p></section>';
        return;
      }
      render();
      if (mode === "browse" && !listDocument && !loading) loadList(0);
      if (reuseEnabled() && !planDocument && !planLoading && !planErrorMessage) loadPlan();
    }

    function render() {
      if (!host) return;
      stopAudio();
      host.innerHTML = mode === "detail" ? detailHtml() : mode === "plan" ? planHtml() : browseHtml();
      wire();
      restoreTransformFocus();
      restoreCorrectionFocus();
    }

    function gateHtml() {
      const acceptance = capability?.acceptance || {};
      const count = Number(observedLibraryCount ?? capability?.library?.clip_count ?? 0);
      const countText = libraryEvidenceStale
        ? browseFiltersAreEmpty()
          ? "library changed · exact count refreshes when Browse Clips reloads"
          : "library changed · clear filters to refresh the exact library count"
        : `${esc(count)} immutable clip${count === 1 ? "" : "s"}`;
      if (transformEnabled() || correctionEnabled()) {
        const operation = correctionEnabled()
          ? "one temporary bounded note correction"
          : "one temporary key or BPM change";
        return `<section class="identity"><p><b>Phase 6 Clip Library with explicit version creation</b></p><p>Existing Clip objects remain immutable. After reviewing ${operation}, you may explicitly create one new child version from the exact Clip you opened.</p><p class="muted">${countText} · accepted pack ${esc(shortHash(acceptance.pack_sha256))} · no automatic correction, transform, preference, selection, placement, current-arrangement change or GarageBand Pack change.</p></section>`;
      }
      const boundary = reuseEnabled()
        ? "no transform, edit, tag change, hybrid, current-project selection or library write is available here"
        : "no transform, edit, tag change, hybrid, selection or library write is available here";
      return `<section class="identity"><p><b>Phase 6 read-only Clip Library</b></p><p>The exact Phase 5.9 GarageBand and usability review passed before this view was enabled. This slice can browse verified Clip v1 objects, render a neutral listening proxy and download a deterministic MIDI reconstruction.</p><p class="muted">${countText} · accepted pack ${esc(shortHash(acceptance.pack_sha256))} · ${boundary}.</p></section>`;
    }

    function reuseHeaderHtml() {
      if (!reuseEnabled()) return "";
      const count = planPlacementCount();
      const browseActive = mode !== "plan";
      return `<section id="clip-reuse-boundary" class="decoded-boundary"><p><b>Reuse plan, not the current song.</b></p><p>Adding a Clip saves only an unchanged Clip reference and a planning position in a separate local proposal. It does not alter MIDI, current project decisions, the selected arrangement, the GarageBand Pack basket or feedback.</p><p class="muted">Listening and downloading never place or favour a Clip. No transpose, tempo conversion, stretch, merge, render or instrument choice is applied by the proposal.</p></section><nav class="actions" aria-label="Clip Library views"><button id="clip-browse-view" type="button" ${browseActive ? 'class="selected" aria-current="page"' : ""}>Browse Clips</button><button id="clip-plan-view" type="button" ${browseActive ? "" : 'class="selected" aria-current="page"'}>Proposed reuse plan (<output id="clip-plan-count">${esc(count)}</output>)</button></nav>${planStatusHtml()}`;
    }

    function clipHeaderHtml() {
      return `${gateHtml()}${reuseHeaderHtml()}`;
    }

    function planPlacementCount() {
      if (!planDocument) return 0;
      const declared = Number(planDocument.placement_count);
      return Number.isInteger(declared) && declared >= 0
        ? declared
        : list(planDocument.placements).length;
    }

    function planStatusHtml() {
      if (!reuseEnabled()) return "";
      if (planLoading && !planDocument) return '<p class="busy" id="clip-plan-status" role="status">Restoring the separate local reuse proposal…</p>';
      if (planErrorMessage) return `<div class="app-alert" id="clip-plan-status" role="alert"><p><b>The reuse proposal is unavailable:</b> ${esc(planErrorMessage)}</p><p>Clip browsing and audition remain separate and unchanged. No placement was saved.</p><button id="clip-plan-retry" class="primary" type="button">Retry proposal restore</button></div>`;
      if (actionErrorMessage) return `<div class="app-alert" id="clip-plan-status" role="alert"><p><b>The proposal action did not complete:</b> ${esc(actionErrorMessage)}</p><p>No automatic retry was attempted. Check the latest proposal before explicitly trying again.</p></div>`;
      if (planStatusMessage) return `<p class="success" id="clip-plan-status" role="status">${esc(planStatusMessage)}</p>`;
      return '<p class="muted" id="clip-plan-status">The proposal is loaded independently from Clip auditions and current song decisions.</p>';
    }

    function browseHtml() {
      const page = listDocument?.page || {};
      const rows = listDocument?.clips || [];
      const total = Number(page.total || capability?.library?.clip_count || 0);
      return `<section aria-labelledby="clip-library-heading"><h2 id="clip-library-heading">Explore reusable MIDI clips</h2>${clipHeaderHtml()}<form id="clip-search" class="controls"><h3>Find a part</h3><div class="clip-filters"><label>Title or tag<input name="text" value="${esc(filters.text)}" autocomplete="off"></label><label>Role<input name="role" value="${esc(filters.role)}" placeholder="bass, keys, kick"></label><label>Key<input name="key" value="${esc(filters.key)}" placeholder="B major"></label><label>BPM<input name="bpm" type="number" min="1" step="0.001" value="${esc(filters.bpm)}"></label><label>Tags, comma separated<input name="tags" value="${esc(filters.tags)}"></label></div><div class="actions"><button class="primary" type="submit">Search library</button><button id="clip-reset" type="button">Reset filters</button></div><p class="muted">Search and paging are temporary browser state. They are not preference feedback and are not saved.</p></form>${statusHtml()}${loading ? '<p class="busy" role="status">Reading and hash-checking the local Clip catalog…</p>' : errorMessage ? retryHtml() : rows.length ? `<p class="timeline-summary">Showing ${esc(Number(page.offset || 0) + 1)}–${esc(Number(page.offset || 0) + rows.length)} of ${esc(total)} matching clips.</p><div class="clip-grid">${rows.map(clipCard).join("")}</div>${pagerHtml(page)}` : '<div class="notice"><b>No clips matched these filters.</b><p>Reset the filters or import reviewed MIDI through the existing <code>clip-import</code> command. This read-only page will never add a clip itself.</p></div>'}</section>`;
    }

    function clipCard(clip) {
      const tags = (clip.tags || []).map((tag) => `<span class="badge">${esc(tag)}</span>`).join(" ");
      return `<article class="card clip-card"><h3>${esc(clip.title || "Untitled clip")}</h3><p><span class="badge good">${esc(clip.role || "unclassified")}</span> ${esc(clip.key || "key unknown")} · ${esc(numberLabel(clip.bpm))} BPM</p><p>${esc(clip.note_count || 0)} notes · ${esc(numberLabel(clip.duration_seconds))} seconds · revision ${esc(clip.revision || 1)}</p>${tags ? `<p>${tags}</p>` : ""}<p class="muted">Clip ${esc(shortHash(clip.clip_id))} · object ${esc(shortHash(clip.object_sha256))}</p><button type="button" class="primary" data-open-clip="${esc(clip.clip_id)}">Inspect and audition</button></article>`;
    }

    function pagerHtml(page) {
      const hasPrevious = Number(page.offset || 0) > 0;
      const hasNext = page.has_more === true;
      if (!hasPrevious && !hasNext) return "";
      return `<nav class="actions" aria-label="Clip result pages"><button id="clip-previous" type="button" ${hasPrevious ? "" : "disabled"}>Previous</button><button id="clip-next" type="button" ${hasNext ? "" : "disabled"}>Next</button></nav>`;
    }

    function detailHtml() {
      const clip = detailDocument?.clip;
      if (loading && !clip) return `<section aria-labelledby="clip-detail-heading"><h2 id="clip-detail-heading">Clip details</h2>${clipHeaderHtml()}<p class="busy">Verifying the immutable Clip object…</p></section>`;
      if (errorMessage && !clip) return `<section aria-labelledby="clip-detail-heading"><h2 id="clip-detail-heading">Clip details</h2>${clipHeaderHtml()}${retryHtml(true)}</section>`;
      if (!clip) return `<section class="panel"><h2>Clip details unavailable</h2><button id="clip-back" type="button">Back to library</button></section>`;
      const lineage = detailDocument?.lineage?.versions || [];
      const artifact = artifacts.get(clip.clip_id);
      const timing = clip.timing_contract || {};
      const duration = clip.duration || {};
      const instrument = clip.instrument || {};
      const range = clip.pitch_range ? `${esc(clip.pitch_range.minimum_name || clip.pitch_range.minimum)}–${esc(clip.pitch_range.maximum_name || clip.pitch_range.maximum)}` : "no notes";
      const backLabel = detailReturnMode === "plan" ? "← Back to proposed reuse plan" : "← Back to Clip Library";
      return `<section aria-labelledby="clip-detail-heading"><button id="clip-back" type="button">${backLabel}</button><h2 id="clip-detail-heading">${esc(clip.title)}</h2>${clipHeaderHtml()}${statusHtml()}<div class="clip-detail-grid"><section class="panel"><h3>Musical content</h3><dl class="clip-facts"><dt>Role</dt><dd>${esc(clip.role)}</dd><dt>Key</dt><dd>${esc(clip.key || "unknown")}</dd><dt>Tempo</dt><dd>${esc(numberLabel(clip.bpm))} BPM</dd><dt>Timing contract</dt><dd>${esc(timing.resolved_mode || "musical")}</dd><dt>GarageBand tempo</dt><dd>${esc(numberLabel(timing.export_bpm || clip.bpm))} BPM</dd><dt>Notes / chords</dt><dd>${esc(clip.note_count)} / ${esc(clip.chord_count)}</dd><dt>Pitch range</dt><dd>${range}</dd><dt>Duration</dt><dd>${esc(numberLabel(duration.export_seconds))} seconds</dd><dt>Program / channel</dt><dd>${esc(instrument.program)} / ${esc(Number(instrument.channel) + 1)}</dd></dl></section><section class="panel"><h3>Immutable identity</h3><p>Revision ${esc(clip.revision)} · ${esc(lineage.length)} version${lineage.length === 1 ? "" : "s"} in this lineage.</p><p class="muted">Clip ID ${esc(clip.clip_id)}<br>Object SHA-256 ${esc(clip.object_sha256)}</p><p>The source pathname and private provenance are deliberately absent from this browser projection.</p></section></div><section class="controls"><h3>Listen and export</h3><p>The MIDI download is a deterministic reconstruction of this immutable Clip v1 document. It is not claimed to be a byte-for-byte copy of an earlier source MIDI. A neutral preview, when requested, renders that exact reconstructed MIDI through the pinned dry local SoundFont.</p><p class="muted">Listening and downloading do not record a preference or add this Clip to the reuse proposal.</p><div class="actions"><button id="clip-midi" class="primary" type="button">Prepare MIDI download</button><button id="clip-preview" type="button">Prepare neutral audition</button></div><div id="clip-artifact">${artifactHtml(artifact)}</div></section>${correctionSummaryHtml()}${transformHtml(clip)}${correctionHtml(clip)}${reusePlacementHtml(clip)}<section class="panel"><h3>Version lineage</h3><p class="muted">Versions are alternatives in one source lineage, not a ranking. “Viewing” identifies only the detail currently open.</p>${lineage.length ? `<ol class="clip-lineage">${lineage.map((item) => `<li><button type="button" data-lineage-clip="${esc(item.clip_id)}" ${item.clip_id === clip.clip_id ? "disabled" : ""}>Revision ${esc(item.revision)} · ${esc(item.title)} · ${esc(numberLabel(item.bpm))} BPM${item.clip_id === clip.clip_id ? " (viewing)" : ""}</button></li>`).join("")}</ol>` : "<p>No lineage records were found.</p>"}</section></section>`;
    }

    function correctionSummaryHtml() {
      const summary = detailDocument?.correction_summary;
      if (!summary || !["correct_note_pitches", "correct_note_attack_velocities", "delete_clip_notes"].includes(summary.operation)) return "";
      const window = summary.window || {};
      const changes = list(summary.changes);
      const changedCount = Number.isInteger(Number(summary.changed_note_count)) ? Number(summary.changed_note_count) : changes.length;
      if (summary.operation === "delete_clip_notes") {
        const changeText = changes.length
          ? `<details><summary>Show ${esc(changes.length)} exact removed note${changes.length === 1 ? "" : "s"}</summary><ol>${changes.map((change) => `<li>${esc(noteRefLabel(change.note_ref))}: ${esc(midiPitchName(change.pitch))} (${esc(change.pitch ?? "unknown")}) · beat ${esc(numberLabel(change.start_beat))} · length ${esc(numberLabel(change.duration_beats))}</li>`).join("")}</ol></details>`
          : "";
        return `<section id="clip-correction-summary" class="panel" aria-labelledby="clip-correction-summary-heading"><h3 id="clip-correction-summary-heading">Saved note-removal correction</h3><p>This immutable Clip is a note-removal child. This evidence was restored from the Clip document; it is not a current draft, ranking or preference.</p><dl class="clip-facts"><dt>Removed notes</dt><dd>${esc(changedCount)}</dd><dt>Parent notes</dt><dd>${esc(summary.note_count_before ?? summary.parent?.note_count ?? "unknown")}</dd><dt>Child notes</dt><dd>${esc(summary.note_count_after ?? summary.child?.note_count ?? detailDocument?.clip?.note_count ?? "unknown")}</dd><dt>Exact tick window</dt><dd>${esc(window.start_tick ?? "unknown")}–${esc(window.end_tick ?? "unknown")} at ${esc(window.ticks_per_beat ?? "unknown")} ticks per beat</dd><dt>Parent Clip</dt><dd>${esc(summary.parent_clip_id || summary.parent?.clip_id || "unknown")}</dd><dt>Parent object</dt><dd>${esc(summary.parent_object_sha256 || summary.parent?.object_sha256 || "unknown")}</dd><dt>Contract</dt><dd>${esc(summary.contract_version || summary.schema || "unknown")}</dd></dl>${changeText}<p class="muted">Only the listed note events were removed. The retained note events and the Clip duration horizon remain exact; no phrase completion or automatic repair was inferred.</p><p class="muted">Reading this restored summary has zero effects. The earlier explicit create appended this child; it left the parent immutable and did not automatically select, place or add the child to a pack.</p></section>`;
      }
      if (summary.operation === "correct_note_attack_velocities") {
        const changeText = changes.length
          ? `<details><summary>Show ${esc(changes.length)} exact attack-velocity change${changes.length === 1 ? "" : "s"}</summary><ol>${changes.map((change) => {
              const before = Number(change.before_velocity ?? change.before?.velocity);
              const after = Number(change.after_velocity ?? change.target_velocity ?? change.after?.velocity);
              return `<li>${esc(noteRefLabel(change.note_ref))}: ${esc(velocityChangeLabel(before, after))}</li>`;
            }).join("")}</ol></details>`
          : "";
        return `<section id="clip-correction-summary" class="panel" aria-labelledby="clip-correction-summary-heading"><h3 id="clip-correction-summary-heading">Saved note attack-velocity correction</h3><p>This immutable Clip is an attack-velocity-corrected child. This evidence was restored from the Clip document; it is not a current draft, ranking or preference.</p><dl class="clip-facts"><dt>Changed notes</dt><dd>${esc(changedCount)}</dd><dt>Exact tick window</dt><dd>${esc(window.start_tick ?? "unknown")}–${esc(window.end_tick ?? "unknown")} at ${esc(window.ticks_per_beat ?? "unknown")} ticks per beat</dd><dt>Parent Clip</dt><dd>${esc(summary.parent_clip_id || summary.parent?.clip_id || "unknown")}</dd><dt>Parent object</dt><dd>${esc(summary.parent_object_sha256 || summary.parent?.object_sha256 || "unknown")}</dd><dt>Contract</dt><dd>${esc(summary.contract_version || summary.schema || "unknown")}</dd></dl>${changeText}<p class="muted">MIDI attack velocity is note-on intensity, not dB or track volume. The selected GarageBand patch may turn it into a loudness, brightness, articulation or sample-layer change.</p><p class="muted">Reading this restored summary has zero effects. The earlier explicit create appended this child; it left the parent immutable and did not automatically select, place or add the child to a pack.</p></section>`;
      }
      const changeText = changes.length
        ? `<details><summary>Show ${esc(changes.length)} exact pitch change${changes.length === 1 ? "" : "s"}</summary><ol>${changes.map((change) => `<li>${esc(noteRefLabel(change.note_ref))}: ${esc(midiPitchName(change.before_pitch ?? change.source_pitch))} (${esc(change.before_pitch ?? change.source_pitch ?? "unknown")}) → ${esc(midiPitchName(change.target_pitch ?? change.after_pitch))} (${esc(change.target_pitch ?? change.after_pitch ?? "unknown")})</li>`).join("")}</ol></details>`
        : "";
      return `<section id="clip-correction-summary" class="panel" aria-labelledby="clip-correction-summary-heading"><h3 id="clip-correction-summary-heading">Saved note-pitch correction</h3><p>This immutable Clip is a pitch-corrected child. This evidence was restored from the Clip document; it is not a current draft or preference.</p><dl class="clip-facts"><dt>Changed notes</dt><dd>${esc(changedCount)}</dd><dt>Exact tick window</dt><dd>${esc(window.start_tick ?? "unknown")}–${esc(window.end_tick ?? "unknown")} at ${esc(window.ticks_per_beat ?? "unknown")} ticks per beat</dd><dt>Parent Clip</dt><dd>${esc(summary.parent_clip_id || summary.parent?.clip_id || "unknown")}</dd><dt>Parent object</dt><dd>${esc(summary.parent_object_sha256 || summary.parent?.object_sha256 || "unknown")}</dd><dt>Contract</dt><dd>${esc(summary.contract_version || summary.schema || "unknown")}</dd></dl>${changeText}<p class="muted">Reading this restored summary has zero effects. The earlier explicit create appended this child; it left the parent immutable and did not automatically select, place or add the child to a pack.</p></section>`;
    }

    function transformHtml(clip) {
      if (!transformEnabled()) return "";
      const draft = transformDraft(clip.clip_id);
      const sourceMode = keyMode(clip.key);
      const drumFamily = isDrumFamilyClip(clip);
      const previewAllowed = transformActionAllowed("preview");
      const createAllowed = transformActionAllowed("create");
      const keyAllowed = transformOperationAllowed("key") && !!sourceMode && !drumFamily;
      const bpmAllowed = transformOperationAllowed("bpm");
      const targetProject = transformCapability?.target_project || {};
      const projectKey = sameModeKey(targetProject.key, sourceMode);
      const projectBpm = positiveFinite(targetProject.bpm);
      const busy = !!transformPending;
      const bpmBounds = transformBpmBounds(clip);
      const formDisabled = busy || !previewAllowed ? "disabled" : "";
      const keyOptions = sourceMode
        ? KEY_TONICS.map((tonic) => {
            const value = `${tonic} ${sourceMode}`;
            return `<option value="${esc(value)}" ${draft.targetKey === value ? "selected" : ""}>${esc(value)}</option>`;
          }).join("")
        : "";
      const operationHelp = !previewAllowed
        ? '<div class="notice" id="clip-transform-capacity"><b>Version creation is unavailable at this library size.</b><p>The accepted 10,000-Clip boundary has been reached, so both temporary transform review and child creation are disabled. Existing Clips remain available to inspect, audition and export.</p></div>'
        : !keyAllowed
          ? `<p class="muted" id="clip-transform-key-unavailable">${drumFamily ? "Key change is unavailable because drum MIDI note numbers select kit pieces." : "This Clip has no usable source key, so this increment can only review a BPM change."}</p>`
        : "";
      const projectionHtml = transformProjectionHtml();
      const resultHtml = transformResultHtml();
      const createReady = !!transformProjection && !busy && createAllowed;
      const reviewReady = !busy && previewAllowed && (keyAllowed || bpmAllowed);
      const createHelp = createAllowed
        ? "Creation is available only for the exact current temporary review. Editing any field invalidates it."
        : "Creation is disabled because the accepted library capacity has been reached.";
      return `<section id="clip-transform-section" class="controls" aria-labelledby="clip-transform-heading" aria-busy="${busy ? "true" : "false"}"><h3 id="clip-transform-heading">Create a transformed alternative</h3><p>Choose and review exactly one change to this exact Clip. Review is temporary and zero-effect. Only <b>Create immutable Clip version</b> adds a child; the parent and every analytical, AI and repaired alternative stay intact.</p><div class="notice"><b>State boundary</b><p>Draft and temporary review: this browser tab only. Created child: durable immutable version. Current song, reuse proposal, selection and GarageBand Pack: unchanged.</p></div>${transformStatusHtml()}${resultHtml}<form id="clip-transform-form"><fieldset ${formDisabled}><legend>1. Choose one change</legend><label class="answer-row"><input id="clip-transform-operation-key" name="clip-transform-operation" type="radio" value="key" ${draft.operation === "key" ? "checked" : ""} ${keyAllowed ? "" : "disabled"}> Key, keeping ${esc(sourceMode || "the existing mode")}</label><label class="answer-row"><input id="clip-transform-operation-bpm" name="clip-transform-operation" type="radio" value="bpm" ${draft.operation === "bpm" ? "checked" : ""} ${bpmAllowed ? "" : "disabled"}> BPM and timing behaviour</label><p class="muted">Sunofriend preselects nothing. Project values are never inferred or applied automatically.</p>${operationHelp}</fieldset><div id="clip-transform-key-controls" ${draft.operation === "key" ? "" : "hidden"}><fieldset ${formDisabled}><legend>2. Choose the target key and register direction</legend><label for="clip-transform-target-key">Target key</label><select id="clip-transform-target-key" aria-describedby="clip-transform-key-help"><option value="">Choose a target key</option>${keyOptions}</select>${projectKey ? `<button id="clip-transform-use-project-key" type="button">Use project key ${esc(projectKey)}</button>` : ""}<p id="clip-transform-key-help" class="muted">Only the source major/minor mode is offered. Smallest shift, upward and downward can land the same notes in different registers.</p><label class="answer-row"><input id="clip-transform-direction-nearest" name="clip-transform-direction" type="radio" value="nearest" ${draft.direction === "nearest" ? "checked" : ""}> Smallest semitone shift</label><label class="answer-row"><input id="clip-transform-direction-up" name="clip-transform-direction" type="radio" value="up" ${draft.direction === "up" ? "checked" : ""}> Transpose upward</label><label class="answer-row"><input id="clip-transform-direction-down" name="clip-transform-direction" type="radio" value="down" ${draft.direction === "down" ? "checked" : ""}> Transpose downward</label></fieldset></div><div id="clip-transform-bpm-controls" ${draft.operation === "bpm" ? "" : "hidden"}><fieldset ${formDisabled}><legend>2. Choose the target BPM and timing behaviour</legend><label for="clip-transform-target-bpm">Target BPM</label><input id="clip-transform-target-bpm" type="number" min="${esc(numberInputLabel(bpmBounds.minimum))}" max="${esc(numberInputLabel(bpmBounds.maximum))}" step="0.001" inputmode="decimal" value="${esc(draft.targetBpm)}" aria-describedby="clip-transform-bpm-help">${projectBpm ? `<button id="clip-transform-use-project-bpm" type="button">Use project BPM ${esc(numberLabel(projectBpm))}</button>` : ""}<p id="clip-transform-bpm-help" class="muted">For this ${esc(numberLabel(clip.bpm))} BPM Clip, choose ${esc(numberLabel(bpmBounds.minimum))}–${esc(numberLabel(bpmBounds.maximum))} BPM (${esc(numberLabel(bpmBounds.minimumRatio))}×–${esc(numberLabel(bpmBounds.maximumRatio))}×, within the global ${esc(numberLabel(bpmBounds.globalMinimum))}–${esc(numberLabel(bpmBounds.globalMaximum))} BPM boundary). <b>Musical</b> keeps bars and beats while elapsed duration changes. <b>Stem-locked</b> keeps source seconds while MIDI beat positions and the required GarageBand tempo change.</p><label class="answer-row"><input id="clip-transform-timing-musical" name="clip-transform-timing" type="radio" value="musical" ${draft.timingMode === "musical" ? "checked" : ""}> Musical timing</label><label class="answer-row"><input id="clip-transform-timing-stem-locked" name="clip-transform-timing" type="radio" value="stem_locked" ${draft.timingMode === "stem_locked" ? "checked" : ""}> Stem-locked timing</label></fieldset></div><div class="actions"><button id="clip-transform-review" class="primary" type="submit" ${reviewReady ? "" : "disabled"}>${transformPending === "projection" ? "Reviewing locally…" : "Review temporary transform"}</button><button id="clip-transform-create" type="button" aria-describedby="clip-transform-create-help" aria-disabled="${createReady ? "false" : "true"}" ${createReady ? "" : "disabled"}>${transformPending === "create" ? "Verifying or creating immutable version…" : "Create immutable Clip version"}</button></div><p id="clip-transform-create-help" class="muted">${esc(createHelp)}</p></form>${projectionHtml}<p class="muted">This increment does not tune audio, align a downbeat, edit notes, combine processes, render a song, export a pack or choose a winner.</p></section>`;
    }

    function reusePlacementHtml(clip) {
      if (!reuseEnabled()) return "";
      const compatibility = detailDocument?.reuse_compatibility;
      if (!compatibility || compatibility.proposal_enabled !== true) {
        return '<section class="panel"><h3>Propose reuse</h3><p class="notice">This Clip has no verified project-compatibility projection, so placement is unavailable. Browsing and audition remain unchanged.</p></section>';
      }
      const project = compatibility.target_project || reuseCapability?.target_project || {};
      const source = compatibility.clip || {};
      const comparison = compatibility.comparison || {};
      const grid = compatibility.target_grid || reuseCapability?.target_grid || {};
      const draft = placementDraft(clip.clip_id);
      const beatsPerBar = positiveInteger(grid.beats_per_bar, 4);
      const warnings = list(compatibility.warnings);
      const ready = compatibility.placement_ready === true
        && compatibility.transform_applied === false
        && !!planDocument
        && !planLoading
        && !planErrorMessage
        && !actionPending
        && actionAllowed("place");
      const warningHtml = warnings.length
        ? `<div class="notice"><h4>Review before placing</h4><ul>${warnings.map(warning => `<li data-clip-compatibility-warning="${esc(warning?.code || "warning")}">${esc(warning?.message || "Compatibility needs review.")}</li>`).join("")}</ul><p>These warnings do not transform or reject the Clip. They describe what may need resolving in a later increment or in GarageBand.</p></div>`
        : '<p class="success">The server reported no key or BPM mismatch. This is still a proposal, not a rendered arrangement.</p>';
      const originText = grid.origin === "recorded-zero"
        ? "Bar 1, beat 1 is the recorded-zero planning origin"
        : "Bar 1, beat 1 is the proposal planning origin";
      return `<section id="clip-reuse-compatibility" class="controls" aria-labelledby="clip-reuse-heading"><h3 id="clip-reuse-heading">Propose this unchanged Clip</h3><p>This creates one separate placement reference. It does not add MIDI to the current selected arrangement or GarageBand Pack.</p><div class="clip-detail-grid"><section class="panel"><h4>Compatibility with this project</h4><dl class="clip-facts"><dt>Project</dt><dd>${esc(project.key || "key unknown")} · ${esc(numberLabel(project.bpm))} BPM</dd><dt>Clip</dt><dd>${esc(source.key || clip.key || "key unknown")} · ${esc(numberLabel(source.bpm ?? clip.bpm))} BPM</dd><dt>Key comparison</dt><dd>${esc(statusLabel(comparison.key_status))}</dd><dt>BPM comparison</dt><dd>${esc(statusLabel(comparison.bpm_status))}</dd></dl></section><section class="panel"><h4>Planning grid</h4><p>${esc(beatsPerBar)}/4 · ${esc(positiveInteger(grid.ticks_per_beat, 480))} ticks per beat.</p><p><b>${esc(originText)}.</b> Reuse v1 does not apply project downbeat or time-signature evidence, so these are planning coordinates, not confirmed musical bars.</p></section></div>${warningHtml}${actionErrorMessage ? `<p class="error" role="alert">${esc(actionErrorMessage)}</p>` : ""}<form id="clip-place-form"><div class="loop"><label>Start bar<input id="clip-start-bar" name="bar" type="number" min="1" step="1" value="${esc(draft.bar)}"></label><label>Start beat<input id="clip-start-beat" name="beat" type="number" min="1" max="${esc(beatsPerBar)}" step="1" value="${esc(draft.beat)}"></label></div><p class="muted">Whole beats only in this first slice. To reuse the Clip again, add a separate explicit placement.</p><button id="clip-place-submit" class="primary" type="submit" ${ready ? "" : "disabled"}>${actionPending ? "Saving proposal…" : "Place unchanged Clip"}</button>${!planDocument && !planLoading ? '<p class="error">Restore the proposal before placing this Clip.</p>' : ""}</form></section>`;
    }

    function planHtml() {
      if (!reuseEnabled()) return browseHtml();
      const placements = list(planDocument?.placements);
      const target = planDocument?.target_project || reuseCapability?.target_project || {};
      const grid = planDocument?.target_grid || reuseCapability?.target_grid || {};
      const revision = Number(planDocument?.revision || 0);
      const restore = statusLabel(planDocument?.restore_status || "not yet restored");
      const content = planLoading && !planDocument
        ? '<p class="busy" role="status">Restoring the separate local reuse proposal…</p>'
        : planErrorMessage && !planDocument
          ? '<p class="error">The proposal cannot be displayed until its exact evidence is restored.</p>'
          : placements.length
            ? `<div class="clip-grid">${placements.map(placementCard).join("")}</div>`
            : '<div class="notice"><b>No Clips are in this proposal.</b><p>Browse the library, inspect a Clip and explicitly place its unchanged reference at a planning bar and beat.</p><button id="clip-empty-browse" type="button">Browse Clips</button></div>';
      return `<section aria-labelledby="clip-reuse-plan-heading"><h2 id="clip-reuse-plan-heading">Proposed Clip arrangement</h2>${clipHeaderHtml()}<section id="clip-reuse-plan-summary" class="panel"><h3>Separate saved proposal</h3><p><b>${esc(planPlacementCount())} placement${planPlacementCount() === 1 ? "" : "s"}</b> · revision ${esc(revision)} · ${esc(restore)}.</p><p>Target project: ${esc(target.key || "key unknown")} · ${esc(numberLabel(target.bpm))} BPM. Grid: ${esc(positiveInteger(grid.beats_per_bar, 4))} beats per planning bar, anchored at recorded zero.</p><p class="muted">An exact matching project/setup/library gate restores this proposal after Workbench restarts. Audition files, playback and unfinished form values start fresh. This proposal is not played, transformed, exported or inserted into the current arrangement.</p></section>${content}</section>`;
    }

    function placementCard(placement) {
      const clip = placement?.clip || {};
      const target = placement?.target || {};
      const compatibility = placement?.compatibility || {};
      const warnings = list(compatibility.warnings);
      const warningHtml = warnings.length
        ? `<ul>${warnings.map(warning => `<li data-placement-warning="${esc(warning?.code || "warning")}">${esc(warning?.message || "Compatibility needs review.")}</li>`).join("")}</ul>`
        : '<p class="success">No key or BPM mismatch was reported.</p>';
      const end = target.nominal_end_beat == null ? "unknown" : numberLabel(target.nominal_end_beat);
      return `<article class="card" data-placement-id="${esc(placement?.placement_id)}"><h3>${esc(clip.title || "Untitled Clip")}</h3><p><span class="badge good">${esc(clip.role || "unclassified")}</span> ${esc(clip.key || "key unknown")} · ${esc(numberLabel(clip.bpm))} BPM</p><p><b>Planning position:</b> bar ${esc(target.bar)} · beat ${esc(target.beat)} · nominal end beat ${esc(end)}.</p><p>${esc(clip.note_count || 0)} notes · ${esc(numberLabel(clip.duration_beats))} beats · source revision ${esc(clip.revision || 1)}</p>${warningHtml}<p class="muted">Unchanged Clip ${esc(shortHash(clip.clip_id))} · object ${esc(shortHash(clip.object_sha256))}. No transform or render is attached.</p><div class="actions"><button type="button" data-plan-inspect-clip="${esc(clip.clip_id)}">Inspect Clip</button><button type="button" data-remove-placement="${esc(placement?.placement_id)}" ${actionPending || !!planErrorMessage || !actionAllowed("remove") ? "disabled" : ""}>Remove from proposal</button></div></article>`;
    }

    function transformStatusHtml() {
      if (transformErrorMessage) return `<div id="clip-transform-status" class="app-alert" role="alert" tabindex="-1"><p><b>The transform action did not complete:</b> ${esc(transformErrorMessage)}</p><p>No automatic retry was attempted. The parent Clip, current song, proposal, selection and pack remain unchanged.</p></div>`;
      if (transformStatusMessage) return `<p id="clip-transform-status" class="success" role="status" aria-live="polite">${esc(transformStatusMessage)}</p>`;
      if (transformPending) return `<p id="clip-transform-status" class="busy" role="status" aria-live="polite" tabindex="-1">${transformPending === "create" ? "Verifying or creating the exact immutable child…" : "Calculating a temporary, zero-effect transform review…"}</p>`;
      return '<p id="clip-transform-status" class="muted" role="status" aria-live="polite">No transform has been reviewed or created in this browser tab.</p>';
    }

    function transformProjectionHtml() {
      const projection = transformProjection;
      if (!projection) return '<div id="clip-transform-projection"><p class="muted">No temporary transform review is active.</p></div>';
      const before = projection.parent || projection.source || projection.before || {};
      const after = projection.child || projection.target || projection.after || projection.proposed || {};
      const warnings = list(projection.warnings);
      const audit = projection.audit || projection.diff || {};
      const warningHtml = warnings.length
        ? `<div class="notice"><h4>Review warnings</h4><ul>${warnings.map((warning) => `<li>${esc(warning?.message || warning || "Review this transform carefully.")}</li>`).join("")}</ul></div>`
        : '<p class="success">No transform warning was reported. This is not a preference or accuracy score.</p>';
      const operation = transformProjectionOperation(projection);
      const diffHtml = transformProjectionDiffHtml(before, after, audit);
      const libraryState = projection.library?.state_sha256 || "unknown";
      return `<section id="clip-transform-projection" class="panel" aria-labelledby="clip-transform-projection-heading" tabindex="-1"><h4 id="clip-transform-projection-heading">Temporary transform review</h4><p><b>${esc(operation)}</b> · projection ${esc(shortHash(projection.projection_sha256))}.</p>${diffHtml}${warningHtml}<details><summary>Exact projection evidence</summary><dl class="clip-facts"><dt>Projection SHA-256</dt><dd>${esc(projection.projection_sha256 || "unknown")}</dd><dt>Library state</dt><dd>${esc(libraryState)}</dd><dt>Parent Clip</dt><dd>${esc(before.clip_id || "unknown")}</dd><dt>Parent object</dt><dd>${esc(before.object_sha256 || "unknown")}</dd><dt>Parent lineage / revision</dt><dd>${esc(before.lineage_id || "unknown")} / ${esc(before.revision ?? "unknown")}</dd><dt>Projected child Clip</dt><dd>${esc(after.clip_id || "unknown")}</dd><dt>Projected child object</dt><dd>${esc(after.object_sha256 || "unknown")}</dd><dt>Child lineage / revision</dt><dd>${esc(after.lineage_id || "unknown")} / ${esc(after.revision ?? "unknown")}</dd></dl></details><p class="muted"><b>Effects: zero.</b> This review is browser-session/rebuildable state. It has not created a Clip, changed a source, selected a process, placed MIDI or changed a pack.</p></section>`;
    }

    function transformProjectionDiffHtml(before, after, diff) {
      if (diff.kind === "key") {
        return `<dl class="clip-facts"><dt>Key</dt><dd>${esc(diff.key_before ?? before.key ?? "unknown")} → ${esc(diff.key_after ?? after.key ?? "unknown")}</dd><dt>Semitone shift</dt><dd>${esc(signedNumberLabel(diff.semitones))}</dd><dt>Pitch range</dt><dd>${esc(rangeLabel(before.pitch_range))} → ${esc(rangeLabel(after.pitch_range))}</dd><dt>Note pitches changed</dt><dd>${esc(diff.note_pitches_changed ?? "unknown")}</dd><dt>Chord symbols changed</dt><dd>${esc(diff.chord_symbols_changed ?? "unknown")}</dd><dt>Notes / chords</dt><dd>${esc(before.note_count ?? diff.note_count_before ?? "unknown")} / ${esc(before.chord_count ?? diff.chord_count_before ?? "unknown")} → ${esc(after.note_count ?? diff.note_count_after ?? "unknown")} / ${esc(after.chord_count ?? diff.chord_count_after ?? "unknown")}</dd><dt>BPM / timing</dt><dd>unchanged</dd><dt>Duration</dt><dd>${esc(numberLabel(before.duration_seconds ?? before.export_seconds))} → ${esc(numberLabel(after.duration_seconds ?? after.export_seconds))} seconds</dd></dl>`;
      }
      if (diff.kind === "bpm") {
        return `<dl class="clip-facts"><dt>BPM</dt><dd>${esc(numberLabel(diff.bpm_before ?? before.bpm))} → ${esc(numberLabel(diff.bpm_after ?? after.bpm))}</dd><dt>Tempo ratio</dt><dd>${esc(numberLabel(diff.ratio))}</dd><dt>Timing behaviour</dt><dd>${esc(statusLabel(diff.timing_mode))}</dd><dt>Elapsed duration</dt><dd>${esc(numberLabel(before.duration_seconds ?? before.export_seconds))} → ${esc(numberLabel(after.duration_seconds ?? after.export_seconds))} seconds</dd><dt>Beat positions changed</dt><dd>${esc(yesNo(diff.beat_positions_changed))}</dd><dt>Source seconds changed</dt><dd>${esc(yesNo(diff.source_seconds_changed))}</dd><dt>Key / pitch range</dt><dd>${esc(before.key || "unknown")} · ${esc(rangeLabel(before.pitch_range))} → unchanged</dd><dt>Notes / chords</dt><dd>${esc(before.note_count ?? diff.note_count_before ?? "unknown")} / ${esc(before.chord_count ?? diff.chord_count_before ?? "unknown")} → ${esc(after.note_count ?? diff.note_count_after ?? "unknown")} / ${esc(after.chord_count ?? diff.chord_count_after ?? "unknown")}</dd></dl>`;
      }
      return `<dl class="clip-facts"><dt>Key</dt><dd>${esc(before.key || "unknown")} → ${esc(after.key || "unchanged")}</dd><dt>BPM</dt><dd>${esc(numberLabel(before.bpm))} → ${esc(numberLabel(after.bpm))}</dd><dt>Duration</dt><dd>${esc(numberLabel(before.duration_seconds ?? before.export_seconds))} → ${esc(numberLabel(after.duration_seconds ?? after.export_seconds))} seconds</dd><dt>Pitch range</dt><dd>${esc(rangeLabel(before.pitch_range))} → ${esc(rangeLabel(after.pitch_range))}</dd><dt>Notes / chords</dt><dd>${esc(diff.note_count ?? after.note_count ?? "unchanged")} / ${esc(diff.chord_count ?? after.chord_count ?? "unchanged")}</dd></dl>`;
    }

    function transformResultHtml() {
      const document = transformResult?.result || transformResult || {};
      const child = document.child || document.clip || document.version;
      if (!child) return "";
      const parent = document.parent || {};
      const replayed = document.replayed === true || document.status === "replayed";
      const library = document.library || {};
      const heading = replayed ? "Existing immutable alternative verified" : "New immutable alternative created";
      const effectText = replayed
        ? "This exact child already existed. The explicit retry was idempotent and appended nothing additional."
        : "This explicit action appended exactly one child version.";
      const inspectLabel = replayed ? "Inspect existing version" : "Inspect created version";
      return `<section id="clip-transform-result" class="success" aria-labelledby="clip-transform-result-heading" tabindex="-1"><h4 id="clip-transform-result-heading">${heading}</h4><p>${effectText} Source revision ${esc(parent.revision ?? detailDocument?.clip?.revision ?? "unknown")} and every analytical, AI and repaired Clip remain unchanged. This child is not preferred, selected, placed or added to the GarageBand Pack.</p><dl class="clip-facts"><dt>Result status</dt><dd>${esc(replayed ? "idempotent replay · effects zero" : "created · one library append")}</dd><dt>Child revision</dt><dd>${esc(child.revision)}</dd><dt>Child Clip</dt><dd>${esc(child.clip_id)}</dd><dt>Child object</dt><dd>${esc(child.object_sha256)}</dd><dt>Lineage</dt><dd>${esc(child.lineage_id || parent.lineage_id || "unknown")}</dd><dt>Parent Clip</dt><dd>${esc(child.parent_clip_id || parent.clip_id || currentClipId)}</dd><dt>Parent object</dt><dd>${esc(parent.object_sha256 || detailDocument?.clip?.object_sha256 || "verified source")}</dd><dt>Key / BPM</dt><dd>${esc(child.key || "unknown")} · ${esc(numberLabel(child.bpm))} BPM</dd><dt>Projection SHA-256</dt><dd>${esc(document.projection_sha256 || "unknown")}</dd><dt>Requested library state</dt><dd>${esc(library.expected_state_sha256 || "unknown")}</dd><dt>Library before this response</dt><dd>${esc(library.previous_state_sha256 || "unknown")}</dd><dt>Library after this response</dt><dd>${esc(library.current_state_sha256 || "unknown")}</dd></dl><p class="muted">Reversibility means choosing the retained parent or another lineage version; Sunofriend did not mutate this child backwards.</p><div class="actions"><button id="clip-transform-inspect-child" class="primary" type="button">${inspectLabel}</button><button id="clip-transform-return-source" type="button">Return to source</button></div></section>`;
    }

    function correctionHtml(clip) {
      const kinds = correctionKindsForClip(clip);
      if (!correctionEnabled() || !correctionActionAllowed("window") || !kinds.length || Number(clip.note_count || 0) < 1) return "";
      const draft = correctionDraft(clip.clip_id);
      if (!kinds.includes(draft.kind)) draft.kind = kinds[0];
      const velocity = draft.kind === CORRECTION_KIND_VELOCITY;
      const deletion = draft.kind === CORRECTION_KIND_DELETE;
      const busy = !!correctionPending;
      const maximumWindow = correctionMaximumWindowBeats();
      const notes = correctionNotes();
      const changes = correctionChanges();
      const selected = correctionSelectedNote();
      const createReady = !!correctionProjection && correctionActionAllowed("create") && !busy;
      const reviewReady = !!correctionWindowDocument && changes.length > 0 && correctionActionAllowed("preview") && !busy;
      const windowDisabled = busy ? "disabled" : "";
      const exactValue = selected && !deletion ? correctionEffectiveValue(selected) : "";
      const sourceValue = selected && !deletion ? correctionSourceValue(selected) : "";
      const selectedCopy = selected
        ? deletion
          ? `Selected ${noteRefLabel(selected.note_ref)}: ${midiPitchName(correctionNotePitch(selected))} (${correctionNotePitch(selected)}) at beat ${numberLabel(correctionNoteStartBeat(selected))}, length ${numberLabel(correctionNoteDurationBeats(selected))}${correctionChangeForKey(correctionNoteRefKey(selected.note_ref)) ? "; marked for removal" : "; kept in the parent state"}${correctionNoteBlockedLabel(selected) ? `; ${correctionNoteBlockedLabel(selected)}` : ""}.`
          : velocity
            ? `Selected ${noteRefLabel(selected.note_ref)}: attack velocity ${sourceValue}${exactValue !== sourceValue ? ` → ${exactValue}` : ""}; pitch ${midiPitchName(correctionNotePitch(selected))} (${correctionNotePitch(selected)}) at beat ${numberLabel(correctionNoteStartBeat(selected))}.`
            : `Selected ${noteRefLabel(selected.note_ref)}: ${midiPitchName(correctionNotePitch(selected))} (${correctionNotePitch(selected)})${exactValue !== correctionNotePitch(selected) ? ` → ${midiPitchName(exactValue)} (${exactValue})` : ""}.`
        : "No note selected. Select one note from the roll or the accessible note list.";
      const kindChoices = kinds.map((kind) => {
        const kindContract = correctionContract(kind);
        const id = `clip-correction-kind-${kindContract.id}`;
        const switchBlocked = changes.length > 0 && kind !== draft.kind;
        return `<label class="answer-row"><input id="${id}" name="clip-correction-kind" type="radio" value="${esc(kind)}" ${kind === draft.kind ? "checked" : ""} ${busy || switchBlocked ? "disabled" : ""}> ${esc(kindContract.label)}</label>`;
      }).join("");
      const listHtml = notes.length
        ? `<ol class="clip-grid" id="clip-correction-note-list" aria-label="Notes in the loaded correction window">${notes.map((note) => {
            const key = correctionNoteRefKey(note.note_ref);
            const selectedNow = draft.selectedRefKey === key;
            const target = deletion ? null : correctionChangeForKey(key)?.[correctionTargetField(draft.kind)];
            const source = deletion ? null : correctionSourceValue(note);
            const changed = deletion ? !!correctionChangeForKey(key) : Number.isInteger(target) && target !== source;
            const editable = correctionNoteEditable(note);
            const reason = correctionNoteBlockedLabel(note);
            const draftText = changed
              ? deletion ? " · marked for removal" : velocity ? ` · draft attack ${target}` : ` · draft ${midiPitchName(target)} (${target})`
              : "";
            const blockedState = reason ? ` · state: ${esc(reason)}` : " · state: available";
            const deletionAccessibility = deletion && !editable ? `aria-disabled="true" aria-describedby="clip-correction-deletion-block-help"` : "";
            const nativeDisabled = busy || (!deletion && !editable) ? "disabled" : "";
            return `<li><button type="button" data-correction-note-ref="${esc(encodeURIComponent(key))}" aria-pressed="${selectedNow ? "true" : "false"}" ${deletionAccessibility} ${nativeDisabled}><b>${esc(noteRefLabel(note.note_ref))} · ${esc(midiPitchName(correctionNotePitch(note)))}</b><br><span class="muted">beat ${esc(numberLabel(correctionNoteStartBeat(note)))} · length ${esc(numberLabel(correctionNoteDurationBeats(note)))} · attack velocity ${esc(correctionNoteVelocity(note))}${deletion ? blockedState : reason ? ` · ${esc(reason)}` : ""}${draftText}</span></button></li>`;
          }).join("")}</ol>`
        : '<div class="notice"><b>No notes begin in this window.</b><p>Choose a different start beat or a longer window. Nothing was selected or changed.</p></div>';
      const pitchControls = `<fieldset ${busy || !selected ? "disabled" : ""}><legend>3. Change the selected note pitch</legend><p id="clip-correction-selection" role="status" aria-live="polite">${esc(selectedCopy)}</p><div class="actions" role="group" aria-label="Relative pitch changes"><button type="button" data-correction-pitch-delta="-12">Octave −</button><button type="button" data-correction-pitch-delta="-1">Semitone −</button><button type="button" data-correction-pitch-delta="1">Semitone +</button><button type="button" data-correction-pitch-delta="12">Octave +</button></div><label for="clip-correction-exact-pitch">Exact MIDI pitch, 0–127</label><input id="clip-correction-exact-pitch" type="number" min="0" max="127" step="1" inputmode="numeric" value="${esc(exactValue)}"><div class="actions"><button id="clip-correction-reset-note" type="button" ${selected && correctionChangeForKey(draft.selectedRefKey) ? "" : "disabled"}>Reset selected note</button><button id="clip-correction-reset-all" type="button" ${changes.length ? "" : "disabled"}>Reset all ${esc(changes.length)} draft change${changes.length === 1 ? "" : "s"}</button></div><p class="muted">Pitch edits are exact MIDI note numbers and must remain within ${esc(correctionMaximumPitchDelta())} semitones of the immutable parent note. They do not change key metadata, chords, timing, velocity, the source Clip or any unselected note. Up to ${esc(correctionMaximumChanges())} notes may be changed in one child.</p></fieldset>`;
      const velocityControls = `<fieldset ${busy || !selected ? "disabled" : ""}><legend>3. Change the selected note attack velocity</legend><p id="clip-correction-selection" role="status" aria-live="polite">${esc(selectedCopy)}</p><div class="actions" role="group" aria-label="Relative attack-velocity changes"><button type="button" data-correction-velocity-delta="-10">−10</button><button type="button" data-correction-velocity-delta="-1">−1</button><button type="button" data-correction-velocity-delta="1">+1</button><button type="button" data-correction-velocity-delta="10">+10</button></div><form id="clip-correction-velocity-form"><label for="clip-correction-exact-velocity">Exact MIDI attack velocity, 1–127</label><input id="clip-correction-exact-velocity" type="number" min="1" max="127" step="1" inputmode="numeric" value="${esc(exactValue)}"><button id="clip-correction-apply-velocity" type="submit">Apply exact attack velocity</button></form><div class="actions"><button id="clip-correction-reset-note" type="button" ${selected && correctionChangeForKey(draft.selectedRefKey) ? "" : "disabled"}>Reset selected note</button><button id="clip-correction-reset-all" type="button" ${changes.length ? "" : "disabled"}>Reset all ${esc(changes.length)} draft change${changes.length === 1 ? "" : "s"}</button></div><p class="muted"><b>MIDI attack velocity is note-on intensity, not dB or track volume.</b> The selected GarageBand patch may translate it into loudness, brightness, articulation or a different sample layer, so compare the created child with the same patch. Typing alone does not edit the draft; use Apply. Pitch, timing, duration, release velocity, metadata, the source Clip and unselected notes stay unchanged.</p></fieldset>`;
      const deletionControls = `<fieldset ${busy || !selected ? "disabled" : ""}><legend>3. Decide whether the selected note is retained</legend><p id="clip-correction-selection" role="status" aria-live="polite">${esc(selectedCopy)}</p><div class="actions" role="group" aria-label="Selected-note removal decision"><button id="clip-correction-mark-delete" type="button" ${!selected || !correctionNoteEditable(selected) || !!correctionChangeForKey(draft.selectedRefKey) || changes.length >= correctionMaximumChanges() || changes.length >= Number(clip.note_count || 0) - 1 ? "disabled" : ""}>Mark selected note for removal</button><button id="clip-correction-keep-delete" type="button" ${selected && correctionChangeForKey(draft.selectedRefKey) ? "" : "disabled"}>Keep selected note</button></div><div class="actions"><button id="clip-correction-reset-all" type="button" ${changes.length ? "" : "disabled"}>Keep all ${esc(changes.length)} marked note${changes.length === 1 ? "" : "s"}</button></div><p id="clip-correction-deletion-block-help" class="muted"><b>Selecting, clicking or focusing a note only inspects it.</b> Removal requires the explicit Mark button. Red crossed notes are marked for removal; amber dashed notes are blocked and state their reason in text. At least one parent note must remain. Retained notes, pitch, attack/release velocity, articulation, timing, duration horizon, key, chords and instrument metadata stay unchanged.</p></fieldset>`;
      const changeName = correctionChangeName(draft.kind);
      const heading = deletion ? "Remove unwanted notes in a new version" : velocity ? "Correct note attack velocities in a new version" : "Correct note pitches in a new version";
      const intro = deletion
        ? "Load a short recorded-zero beat window, inspect exact events and explicitly mark only unwanted notes for removal."
        : velocity
          ? "Load a short recorded-zero beat window, choose exact notes and review the attack-velocity-only diff."
          : "Load a short recorded-zero beat window, choose exact notes and review the pitch-only diff.";
      const controls = deletion ? deletionControls : velocity ? velocityControls : pitchControls;
      const kindsHelp = changes.length > 0
        ? "Reset all draft changes before switching correction kind."
        : "Pitch, attack velocity and note removal are separate alternatives and are never mixed in one child.";
      const rollHelp = deletion
        ? "Original retained notes are blue. Red crossed notes are explicitly marked for removal; amber dashed notes are blocked. Colour is backed by text and is not a score. Selecting or focusing another note only inspects it and does not change the draft or invalidate an exact review."
        : `Original notes are blue. Draft ${changeName} changes are gold overlays; display colour is not a score. Select on the roll or activate a matching note button below. Moving keyboard focus or inspecting another note does not change the draft or invalidate an exact review.`;
      return `<section id="clip-correction-section" class="controls" aria-labelledby="clip-correction-heading" aria-busy="${busy ? "true" : "false"}"><h3 id="clip-correction-heading">${heading}</h3><p>${intro} Nothing is preselected. A draft and review live only in this browser tab; only the explicit create action can append one immutable child.</p><div class="notice"><b>Not a preference or automatic repair</b><p>Sunofriend does not infer which note is wrong, rank a correction kind or audition a draft. Creating a child does not select it, place it, alter the current arrangement, change the GarageBand Pack or record feedback.</p></div><fieldset ${busy ? "disabled" : ""}><legend>Choose exactly one correction kind</legend>${kindChoices}<p class="muted">${kindsHelp}</p></fieldset>${correctionStatusHtml()}${correctionResultHtml()}<form id="clip-correction-window-form"><fieldset ${windowDisabled}><legend>1. Load a bounded note window</legend><label for="clip-correction-window-start">Start beat from recorded zero</label><input id="clip-correction-window-start" type="number" min="0" step="${esc(numberInputLabel(1 / correctionTicksPerBeat()))}" inputmode="decimal" value="${esc(draft.startBeat)}"><label for="clip-correction-window-length">Length in beats</label><input id="clip-correction-window-length" type="number" min="${esc(numberInputLabel(1 / correctionTicksPerBeat()))}" max="${esc(maximumWindow)}" step="${esc(numberInputLabel(1 / correctionTicksPerBeat()))}" inputmode="decimal" value="${esc(draft.lengthBeats)}"><button id="clip-correction-load-window" class="primary" type="submit">${correctionPending === "window" ? "Loading exact notes…" : "Load bounded note window"}</button><p class="muted">The window uses integer ticks at ${esc(correctionTicksPerBeat())} ticks per beat, begins at recorded zero rather than an inferred downbeat, defaults to ${DEFAULT_CORRECTION_WINDOW_BEATS} beats and is limited to ${esc(maximumWindow)} beats.</p></fieldset></form>${correctionWindowDocument ? `<section class="panel" aria-labelledby="clip-correction-roll-heading"><h4 id="clip-correction-roll-heading" tabindex="-1">2. Select and inspect notes</h4>${correctionRollSvg(notes)}<p class="muted">${rollHelp}</p>${listHtml}${controls}<div class="actions"><button id="clip-correction-review" class="primary" type="button" ${reviewReady ? "" : "disabled"}>${correctionPending === "projection" ? "Reviewing exact diff…" : `Review ${changes.length} ${changeName} change${changes.length === 1 ? "" : "s"}`}</button><button id="clip-correction-create" type="button" ${createReady ? "" : "disabled"}>${correctionPending === "create" ? "Verifying or creating immutable version…" : "Create immutable Clip version"}</button></div><p class="muted">Review is required again after any window or ${changeName} edit. Note focus and active-note navigation are browser-only inspection state. There is no draft audition: create the alternative, then explicitly inspect and audition that child.</p>${correctionProjectionHtml()}</section>` : '<p class="muted">No note window is loaded in this browser tab.</p>'}</section>`;
    }

    function correctionStatusHtml() {
      if (correctionErrorMessage) return `<div id="clip-correction-status" class="app-alert" role="alert" tabindex="-1"><p><b>The note-correction action did not complete:</b> ${esc(correctionErrorMessage)}</p><p>No automatic write retry was attempted. The parent Clip, selection, arrangement and pack remain unchanged.</p></div>`;
      if (correctionStatusMessage) return `<p id="clip-correction-status" class="success" role="status" aria-live="polite">${esc(correctionStatusMessage)}</p>`;
      if (correctionPending) {
        const name = correctionChangeName(correctionDraft(currentClipId).kind);
        return `<p id="clip-correction-status" class="busy" role="status" aria-live="polite" tabindex="-1">${correctionPending === "create" ? "Verifying or creating the exact immutable child…" : correctionPending === "projection" ? `Calculating an exact zero-effect ${name} review…` : "Loading the exact bounded note window…"}</p>`;
      }
      return '<p id="clip-correction-status" class="muted" role="status" aria-live="polite">No note window, correction review or child has been created in this browser tab.</p>';
    }

    function correctionRollSvg(notes) {
      const window = correctionWindowContract || {};
      const draft = correctionDraft(currentClipId);
      const velocity = draft.kind === CORRECTION_KIND_VELOCITY;
      const deletion = draft.kind === CORRECTION_KIND_DELETE;
      const ticksPerBeat = correctionTicksPerBeat();
      const startBeat = Number(window.start_tick || 0) / ticksPerBeat;
      const endBeat = Number(window.end_tick || 0) / ticksPerBeat;
      const duration = Math.max(1 / ticksPerBeat, endBeat - startBeat);
      const pitches = notes.flatMap((note) => {
        const source = correctionNotePitch(note);
        const target = correctionChangeForKey(correctionNoteRefKey(note.note_ref))?.target_pitch;
        return !velocity && Number.isInteger(target) ? [source, target] : [source];
      });
      const minimum = pitches.length ? Math.max(0, Math.min(...pitches) - 1) : 59;
      const maximum = pitches.length ? Math.min(127, Math.max(...pitches) + 1) : 72;
      const span = Math.max(1, maximum - minimum + 1);
      const left = 48;
      const top = 16;
      const width = 760;
      const height = Math.max(150, Math.min(320, 44 + span * 12));
      const plotWidth = width - left - 12;
      const plotHeight = height - top - 24;
      const noteHeight = Math.max(6, plotHeight / span - 2);
      const rows = [];
      for (let pitch = minimum; pitch <= maximum; pitch += 1) {
        const y = top + (maximum - pitch) * plotHeight / span;
        rows.push(`<line x1="${left}" y1="${numberInputLabel(y)}" x2="${width - 12}" y2="${numberInputLabel(y)}" stroke="#26384a"/><text x="4" y="${numberInputLabel(y + 10)}" fill="#a9bac8" font-size="10">${esc(midiPitchName(pitch))}</text>`);
      }
      const bars = notes.map((note) => {
        const key = correctionNoteRefKey(note.note_ref);
        const sourcePitch = correctionNotePitch(note);
        const change = correctionChangeForKey(key);
        const targetPitch = change?.target_pitch;
        const targetVelocity = change?.target_velocity;
        const start = correctionNoteStartBeat(note);
        const noteDuration = correctionNoteDurationBeats(note);
        const x = left + (start - startBeat) / duration * plotWidth;
        const noteWidth = Math.max(3, noteDuration / duration * plotWidth);
        const y = top + (maximum - sourcePitch) * plotHeight / span;
        const selected = draft.selectedRefKey === key;
        const editable = correctionNoteEditable(note);
        const reason = correctionNoteBlockedLabel(note);
        const markedForDeletion = deletion && !!change;
        const data = editable || deletion ? ` data-correction-note-svg="${esc(encodeURIComponent(key))}"` : "";
        const fill = markedForDeletion ? "#8f2d3b" : editable ? "#70c9ff" : deletion ? "#3e3422" : "#506575";
        const stroke = selected ? "#eff6fc" : markedForDeletion ? "#ff6b6b" : deletion && !editable ? "#ffc94a" : "#47708d";
        const dash = deletion && !editable ? ' stroke-dasharray="6 4"' : "";
        const cursor = deletion ? "pointer" : editable ? "pointer" : "not-allowed";
        const state = markedForDeletion ? "; marked for removal" : reason ? `; ${reason}` : "; retained";
        const original = `<rect${data} x="${numberInputLabel(x)}" y="${numberInputLabel(y)}" width="${numberInputLabel(noteWidth)}" height="${numberInputLabel(noteHeight)}" rx="2" fill="${fill}" stroke="${stroke}" stroke-width="${selected ? "3" : markedForDeletion || deletion && !editable ? "2" : "1"}"${dash} style="cursor:${cursor}"><title>${esc(`${noteRefLabel(note.note_ref)} ${midiPitchName(sourcePitch)} at beat ${numberLabel(start)}; attack velocity ${correctionNoteVelocity(note)}${state}`)}</title></rect>`;
        if (deletion) {
          if (!markedForDeletion) return original;
          const lineY2 = y + noteHeight;
          const lineX2 = x + noteWidth;
          return `${original}<line data-correction-note-svg="${esc(encodeURIComponent(key))}" x1="${numberInputLabel(x)}" y1="${numberInputLabel(y)}" x2="${numberInputLabel(lineX2)}" y2="${numberInputLabel(lineY2)}" stroke="#fff1f2" stroke-width="2" style="cursor:pointer"><title>${esc(`Draft ${noteRefLabel(note.note_ref)} will be removed`)}</title></line><line data-correction-note-svg="${esc(encodeURIComponent(key))}" x1="${numberInputLabel(lineX2)}" y1="${numberInputLabel(y)}" x2="${numberInputLabel(x)}" y2="${numberInputLabel(lineY2)}" stroke="#fff1f2" stroke-width="2" style="cursor:pointer"><title>${esc(`Draft ${noteRefLabel(note.note_ref)} will be removed`)}</title></line>`;
        }
        if (velocity) {
          if (!Number.isInteger(targetVelocity) || targetVelocity === correctionNoteVelocity(note)) return original;
          return `${original}<rect data-correction-note-svg="${esc(encodeURIComponent(key))}" x="${numberInputLabel(x)}" y="${numberInputLabel(y)}" width="${numberInputLabel(noteWidth)}" height="${numberInputLabel(noteHeight)}" rx="2" fill="none" stroke="#ffc94a" stroke-width="4" style="cursor:pointer"><title>${esc(`Draft ${noteRefLabel(note.note_ref)} attack velocity ${correctionNoteVelocity(note)} to ${targetVelocity}`)}</title></rect>`;
        }
        if (!Number.isInteger(targetPitch) || targetPitch === sourcePitch) return original;
        const targetY = top + (maximum - targetPitch) * plotHeight / span;
        return `${original}<rect data-correction-note-svg="${esc(encodeURIComponent(key))}" x="${numberInputLabel(x)}" y="${numberInputLabel(targetY)}" width="${numberInputLabel(noteWidth)}" height="${numberInputLabel(noteHeight)}" rx="2" fill="#ffc94a" stroke="#eff6fc" stroke-width="2" style="cursor:pointer"><title>${esc(`Draft ${noteRefLabel(note.note_ref)} ${midiPitchName(sourcePitch)} to ${midiPitchName(targetPitch)}`)}</title></rect>`;
      }).join("");
      const draftDescription = deletion ? "red crossed notes are marked for removal and amber dashed notes are blocked" : velocity ? "gold outline is the temporary attack-velocity draft" : "gold is the temporary pitch draft";
      return `<div class="timeline-scroll"><svg id="clip-correction-roll" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="img" aria-label="${esc(`${notes.length} notes from beat ${numberLabel(startBeat)} to ${numberLabel(endBeat)}; blue is original and ${draftDescription}`)}" style="display:block;width:100%;min-width:520px;background:#09111a;border-radius:10px">${rows.join("")}${bars}</svg></div>`;
    }

    function correctionProjectionHtml() {
      const projection = correctionProjection;
      const expectedKind = correctionDraft(currentClipId).kind;
      if (!projection) return `<div id="clip-correction-projection"><p class="muted">No exact ${esc(correctionChangeName(expectedKind))} review is active.</p></div>`;
      const kind = correctionProjectionKind(projection);
      const contract = correctionContract(kind);
      if (!contract) return '<div id="clip-correction-projection" class="app-alert" role="alert"><p><b>The correction review kind is not recognized.</b> No creation action is available.</p></div>';
      const velocity = kind === CORRECTION_KIND_VELOCITY;
      const deletion = kind === CORRECTION_KIND_DELETE;
      const warnings = list(projection.warnings);
      const rows = correctionDiffRows(projection, kind);
      const warningHtml = warnings.length
        ? `<div class="notice"><h5>Review warnings</h5><ul>${warnings.map((warning) => `<li>${esc(warning?.message || warning || `Review this ${contract.changeName} change carefully.`)}</li>`).join("")}</ul></div>`
        : '<p class="success">No correction warning was reported. This is not an accuracy, ranking or preference score.</p>';
      const table = deletion
        ? `<div class="timeline-scroll"><table><caption class="muted">Only these exact parent note references will be absent from the immutable child.</caption><thead><tr><th scope="col">Parent note</th><th scope="col">Pitch / beat</th><th scope="col">Exact lifetime</th><th scope="col">Velocity / articulation</th></tr></thead><tbody>${rows.map((row) => `<tr><th scope="row">${esc(noteRefLabel(row.note_ref))}</th><td>${esc(midiPitchName(row.pitch))} (${esc(row.pitch)}) · beat ${esc(numberLabel(row.start_beat))}</td><td>ticks ${esc(row.start_tick)}–${esc(row.end_tick)} · ${esc(numberLabel(row.duration_beats))} beats · source ${esc(numberLabel(row.source_start_seconds))}–${esc(numberLabel(row.source_end_seconds))} s</td><td>attack ${esc(row.velocity)} · release ${esc(row.release_velocity ?? "unknown")} · ${esc(row.articulation ?? "none")}</td></tr>`).join("")}</tbody></table></div><dl class="clip-facts"><dt>Parent → child notes</dt><dd>${esc(projection.diff?.note_count_before ?? "unknown")} → ${esc(projection.diff?.note_count_after ?? "unknown")}</dd><dt>Normalized MIDI notes</dt><dd>${esc(projection.diff?.normalized_midi_note_count_before ?? "unknown")} → ${esc(projection.diff?.normalized_midi_note_count_after ?? "unknown")}</dd><dt>Pitch range</dt><dd>${esc(rangeLabel(projection.diff?.pitch_range_before))} → ${esc(rangeLabel(projection.diff?.pitch_range_after))}</dd><dt>Beat horizon</dt><dd>${esc(numberLabel(projection.diff?.duration_beats_before))} → ${esc(numberLabel(projection.diff?.duration_beats_after))}</dd><dt>Second horizon</dt><dd>${esc(numberLabel(projection.diff?.duration_seconds_before))} → ${esc(numberLabel(projection.diff?.duration_seconds_after))}</dd><dt>Retained normalized notes changed</dt><dd>${esc(projection.diff?.retained_normalized_notes_changed ?? "unknown")}</dd></dl><p class="muted"><b>The child keeps the parent duration horizon.</b> Every retained normalized MIDI note must remain byte-for-byte equivalent in its musical payload; this review never repairs surrounding notes.</p>`
        : velocity
        ? `<div class="timeline-scroll"><table><caption class="muted">Only these exact parent note references will receive new MIDI Note On attack velocities.</caption><thead><tr><th scope="col">Parent note</th><th scope="col">Pitch / beat context</th><th scope="col">Before → after attack velocity</th><th scope="col">Change</th></tr></thead><tbody>${rows.map((row) => `<tr><th scope="row">${esc(noteRefLabel(row.note_ref))}</th><td>${esc(midiPitchName(row.pitch))} (${esc(row.pitch)}) · beat ${esc(numberLabel(row.start_beat))}</td><td>${esc(row.before_velocity)} → ${esc(row.after_velocity)}</td><td>${esc(velocityDeltaDirectionLabel(row.before_velocity, row.after_velocity))}</td></tr>`).join("")}</tbody></table></div><p class="muted"><b>This is MIDI Note On attack intensity, not dB or track volume.</b> A GarageBand patch may turn the same numeric change into loudness, tone, articulation or a different sample layer.</p>`
        : `<div class="timeline-scroll"><table><caption class="muted">Only these exact parent note references will receive new pitches.</caption><thead><tr><th scope="col">Parent note</th><th scope="col">Before</th><th scope="col">After</th></tr></thead><tbody>${rows.map((row) => `<tr><th scope="row">${esc(noteRefLabel(row.note_ref))}</th><td>${esc(midiPitchName(row.before_pitch))} (${esc(row.before_pitch)})</td><td>${esc(midiPitchName(row.after_pitch))} (${esc(row.after_pitch)})</td></tr>`).join("")}</tbody></table></div>`;
      return `<section id="clip-correction-projection" class="panel" aria-labelledby="clip-correction-projection-heading" tabindex="-1"><h4 id="clip-correction-projection-heading">Exact temporary ${esc(contract.changeName)} review</h4><p><b>${esc(rows.length)} note${rows.length === 1 ? "" : "s"} ${deletion ? "removed" : "changed"}</b> · projection ${esc(shortHash(projection.projection_sha256))}.</p>${table}${warningHtml}<details><summary>Exact projection evidence</summary><dl class="clip-facts"><dt>Projection SHA-256</dt><dd>${esc(projection.projection_sha256 || "unknown")}</dd><dt>Window SHA-256</dt><dd>${esc(projection.window_sha256 || correctionWindowSha256() || "unknown")}</dd><dt>Parent Clip</dt><dd>${esc(projection.parent?.clip_id || currentClipId || "unknown")}</dd><dt>Parent object</dt><dd>${esc(projection.parent?.object_sha256 || detailDocument?.clip?.object_sha256 || "unknown")}</dd><dt>Projected child Clip</dt><dd>${esc(projection.child?.clip_id || "unknown")}</dd><dt>Projected child object</dt><dd>${esc(projection.child?.object_sha256 || "unknown")}</dd></dl></details><p class="muted"><b>Effects: zero.</b> The parent, library, current song, reuse proposal, selection, pack, feedback and every unselected note remain unchanged.</p></section>`;
    }

    function correctionResultHtml() {
      const document = correctionResult?.result || correctionResult || {};
      const child = document.child || document.clip || document.version;
      if (!child) return "";
      const parent = document.parent || {};
      const library = document.library || {};
      const replayed = document.replayed === true || document.status === "replayed";
      const kind = correctionResultKind(document);
      const contract = correctionContract(kind);
      if (!contract) return '<section id="clip-correction-result" class="app-alert" role="alert"><p><b>The correction result kind is not recognized.</b> No child inspection action is available.</p></section>';
      const correctionName = contract.resultName;
      return `<section id="clip-correction-result" class="success" aria-labelledby="clip-correction-result-heading" tabindex="-1"><h4 id="clip-correction-result-heading">${replayed ? `Existing ${correctionName} alternative verified` : `New ${correctionName} alternative created`}</h4><p>${replayed ? "This exact child already existed, so the explicit retry appended nothing." : "This explicit action appended exactly one immutable child."} It is not preferred, ranked, selected, placed, auditioned or added to the GarageBand Pack.</p><dl class="clip-facts"><dt>Result status</dt><dd>${esc(replayed ? "idempotent replay · effects zero" : "created · one library append")}</dd><dt>Child revision</dt><dd>${esc(child.revision ?? "unknown")}</dd><dt>Child Clip</dt><dd>${esc(child.clip_id || "unknown")}</dd><dt>Child object</dt><dd>${esc(child.object_sha256 || "unknown")}</dd><dt>Lineage</dt><dd>${esc(child.lineage_id || parent.lineage_id || "unknown")}</dd><dt>Parent Clip</dt><dd>${esc(child.parent_clip_id || parent.clip_id || currentClipId || "unknown")}</dd><dt>Projection SHA-256</dt><dd>${esc(document.projection_sha256 || "unknown")}</dd><dt>Library before</dt><dd>${esc(library.previous_state_sha256 || library.expected_state_sha256 || "unknown")}</dd><dt>Library after</dt><dd>${esc(library.current_state_sha256 || "unknown")}</dd></dl><p class="muted">To hear the result, explicitly inspect the child and prepare its neutral audition. Opening it does not select or place it.</p><button id="clip-correction-inspect-child" class="primary" type="button">Inspect ${replayed ? "existing" : "created"} version</button></section>`;
    }

    function artifactHtml(artifact) {
      if (!artifact) return '<p class="muted">No derived file has been prepared in this browser session.</p>';
      const midi = artifact.midi || {};
      const preview = artifact.preview || null;
      const timing = artifact.timing_contract || {};
      return `<div class="success"><p><b>Verified derived artifact ready.</b>${artifact.cache_hit ? " Existing content-addressed bytes were reused." : " New content-addressed bytes were created outside the library."}</p>${preview?.url ? `<audio controls preload="metadata" src="${esc(preview.url)}"></audio>` : ""}<p><a href="${esc(midi.url)}" download="${esc(midi.name || "sunofriend-clip.mid")}">Download deterministic MIDI</a>${preview?.url ? ` · <a href="${esc(preview.url)}" download="${esc(preview.name || "sunofriend-clip-preview.wav")}">Download neutral WAV</a>` : ""}</p><p class="muted">MIDI ${esc(shortHash(midi.sha256))} · ${esc(timing.resolved_mode)} timing · set GarageBand to ${esc(numberLabel(timing.export_bpm))} BPM${preview ? " · dry FluidSynth proxy" : ""}. Library and project effects: zero.</p></div>`;
    }

    function statusHtml() {
      return statusMessage ? `<p class="success" role="status">${esc(statusMessage)}</p>` : "";
    }

    function retryHtml(detail = false) {
      return `<div class="app-alert" role="alert"><p><b>The read-only Clip operation did not complete:</b> ${esc(errorMessage)}</p><p>No Clip, Workbench decision or pack state was changed.</p><button id="clip-retry" type="button" class="primary">Retry ${detail ? "Clip details" : "library search"}</button></div>`;
    }

    function wire() {
      if (!host) return;
      const browseView = host.querySelector("#clip-browse-view");
      if (browseView) browseView.onclick = () => {
        stopAudio();
        mode = "browse";
        detailDocument = null;
        currentClipId = null;
        errorMessage = "";
        actionErrorMessage = "";
        render();
        if (!listDocument && !loading) loadList(filters.offset || 0);
      };
      const planView = host.querySelector("#clip-plan-view");
      if (planView) planView.onclick = () => {
        stopAudio();
        mode = "plan";
        detailDocument = null;
        currentClipId = null;
        errorMessage = "";
        actionErrorMessage = "";
        render();
        if (!planDocument && !planLoading) loadPlan();
      };
      const form = host.querySelector("#clip-search");
      if (form) form.onsubmit = (event) => {
        event.preventDefault();
        const values = new FormData(form);
        filters.text = String(values.get("text") || "").trim();
        filters.role = String(values.get("role") || "").trim();
        filters.key = String(values.get("key") || "").trim();
        filters.bpm = String(values.get("bpm") || "").trim();
        filters.tags = String(values.get("tags") || "").trim();
        loadList(0);
      };
      const resetButton = host.querySelector("#clip-reset");
      if (resetButton) resetButton.onclick = () => {
        Object.assign(filters, { text: "", role: "", key: "", bpm: "", tags: "", offset: 0 });
        loadList(0);
      };
      host.querySelectorAll("[data-open-clip]").forEach((button) => button.onclick = () => openClip(button.dataset.openClip, "browse"));
      host.querySelectorAll("[data-lineage-clip]").forEach((button) => button.onclick = () => openClip(button.dataset.lineageClip, detailReturnMode));
      host.querySelectorAll("[data-plan-inspect-clip]").forEach((button) => button.onclick = () => openClip(button.dataset.planInspectClip, "plan"));
      host.querySelectorAll("[data-remove-placement]").forEach((button) => button.onclick = () => removePlacement(button.dataset.removePlacement));
      const previous = host.querySelector("#clip-previous");
      if (previous) previous.onclick = () => loadList(Math.max(0, Number(listDocument?.page?.offset || 0) - DEFAULT_LIMIT));
      const next = host.querySelector("#clip-next");
      if (next) next.onclick = () => loadList(Number(listDocument?.page?.offset || 0) + DEFAULT_LIMIT);
      const back = host.querySelector("#clip-back");
      if (back) back.onclick = () => {
        stopAudio();
        mode = detailReturnMode;
        errorMessage = "";
        statusMessage = "";
        actionErrorMessage = "";
        render();
        if (mode === "browse" && !listDocument && !loading) loadList(filters.offset || 0);
      };
      const midi = host.querySelector("#clip-midi");
      if (midi) midi.onclick = () => prepareArtifact(false, midi);
      const preview = host.querySelector("#clip-preview");
      if (preview) preview.onclick = () => prepareArtifact(true, preview);
      const retry = host.querySelector("#clip-retry");
      if (retry) retry.onclick = () => mode === "detail" ? loadDetail(currentClipId) : loadList(filters.offset || 0);
      const planRetry = host.querySelector("#clip-plan-retry");
      if (planRetry) planRetry.onclick = () => loadPlan();
      const emptyBrowse = host.querySelector("#clip-empty-browse");
      if (emptyBrowse) emptyBrowse.onclick = () => { mode = "browse"; render(); if (!listDocument && !loading) loadList(0); };
      const barInput = host.querySelector("#clip-start-bar");
      const beatInput = host.querySelector("#clip-start-beat");
      const placeForm = host.querySelector("#clip-place-form");
      if (barInput) barInput.oninput = () => updatePlacementDraft();
      if (beatInput) beatInput.oninput = () => updatePlacementDraft();
      if (placeForm) placeForm.onsubmit = (event) => {
        event.preventDefault();
        updatePlacementDraft();
        placeCurrentClip();
      };
      const transformForm = host.querySelector("#clip-transform-form");
      if (transformForm) transformForm.onsubmit = (event) => {
        event.preventDefault();
        updateTransformDraftFromInputs();
        reviewTransform();
      };
      wireTransformChoice("clip-transform-operation-key", () => setTransformDraftValue("operation", "key", true, "clip-transform-target-key"));
      wireTransformChoice("clip-transform-operation-bpm", () => setTransformDraftValue("operation", "bpm", true, "clip-transform-target-bpm"));
      wireTransformChoice("clip-transform-direction-nearest", () => setTransformDraftValue("direction", "nearest", false, "clip-transform-direction-nearest"));
      wireTransformChoice("clip-transform-direction-up", () => setTransformDraftValue("direction", "up", false, "clip-transform-direction-up"));
      wireTransformChoice("clip-transform-direction-down", () => setTransformDraftValue("direction", "down", false, "clip-transform-direction-down"));
      wireTransformChoice("clip-transform-timing-musical", () => setTransformDraftValue("timingMode", "musical", false, "clip-transform-timing-musical"));
      wireTransformChoice("clip-transform-timing-stem-locked", () => setTransformDraftValue("timingMode", "stem_locked", false, "clip-transform-timing-stem-locked"));
      const targetKey = host.querySelector("#clip-transform-target-key");
      if (targetKey) targetKey.oninput = () => setTransformDraftValue("targetKey", String(targetKey.value || ""), false, "clip-transform-target-key");
      const targetBpm = host.querySelector("#clip-transform-target-bpm");
      if (targetBpm) targetBpm.oninput = () => setTransformDraftValue("targetBpm", String(targetBpm.value || ""), false, "clip-transform-target-bpm");
      const useProjectKey = host.querySelector("#clip-transform-use-project-key");
      if (useProjectKey) useProjectKey.onclick = () => setTransformDraftValue("targetKey", sameModeKey(transformCapability?.target_project?.key, keyMode(detailDocument?.clip?.key)) || "", true, "clip-transform-target-key");
      const useProjectBpm = host.querySelector("#clip-transform-use-project-bpm");
      if (useProjectBpm) useProjectBpm.onclick = () => setTransformDraftValue("targetBpm", String(positiveFinite(transformCapability?.target_project?.bpm) || ""), true, "clip-transform-target-bpm");
      const createTransform = host.querySelector("#clip-transform-create");
      if (createTransform) createTransform.onclick = () => createTransformVersion();
      const inspectChild = host.querySelector("#clip-transform-inspect-child");
      if (inspectChild) inspectChild.onclick = () => {
        const child = transformResultChild();
        if (child?.clip_id) openClip(child.clip_id, "browse");
      };
      const returnSource = host.querySelector("#clip-transform-return-source");
      if (returnSource) returnSource.onclick = () => {
        transformResult = null;
        transformProjection = null;
        transformStatusMessage = "Source Clip retained. No child was selected or placed.";
        loadDetail(currentClipId);
      };
      const correctionWindowForm = host.querySelector("#clip-correction-window-form");
      if (correctionWindowForm) correctionWindowForm.onsubmit = (event) => {
        event.preventDefault();
        updateCorrectionWindowDraftFromInputs();
        loadCorrectionWindow();
      };
      const pitchCorrectionKind = host.querySelector("#clip-correction-kind-pitch");
      if (pitchCorrectionKind) pitchCorrectionKind.onclick = () => setCorrectionKind(CORRECTION_KIND_PITCH, "clip-correction-kind-pitch");
      const velocityCorrectionKind = host.querySelector("#clip-correction-kind-velocity");
      if (velocityCorrectionKind) velocityCorrectionKind.onclick = () => setCorrectionKind(CORRECTION_KIND_VELOCITY, "clip-correction-kind-velocity");
      const deletionCorrectionKind = host.querySelector("#clip-correction-kind-delete");
      if (deletionCorrectionKind) deletionCorrectionKind.onclick = () => setCorrectionKind(CORRECTION_KIND_DELETE, "clip-correction-kind-delete");
      const correctionStart = host.querySelector("#clip-correction-window-start");
      if (correctionStart) correctionStart.oninput = () => setCorrectionWindowDraftValue("startBeat", String(correctionStart.value || ""), "clip-correction-window-start");
      const correctionLength = host.querySelector("#clip-correction-window-length");
      if (correctionLength) correctionLength.oninput = () => setCorrectionWindowDraftValue("lengthBeats", String(correctionLength.value || ""), "clip-correction-window-length");
      host.querySelectorAll("[data-correction-note-ref]").forEach((button) => {
        button.onclick = () => selectCorrectionNote(decodeURIComponent(String(button.dataset.correctionNoteRef || "")), true);
      });
      host.querySelectorAll("[data-correction-note-svg]").forEach((shape) => {
        shape.onclick = () => selectCorrectionNote(decodeURIComponent(String(shape.dataset.correctionNoteSvg || "")), false);
      });
      host.querySelectorAll("[data-correction-pitch-delta]").forEach((button) => {
        button.onclick = () => changeSelectedCorrectionPitch(Number(button.dataset.correctionPitchDelta));
      });
      host.querySelectorAll("[data-correction-velocity-delta]").forEach((button) => {
        button.onclick = () => changeSelectedCorrectionVelocity(Number(button.dataset.correctionVelocityDelta));
      });
      const exactPitch = host.querySelector("#clip-correction-exact-pitch");
      if (exactPitch) exactPitch.oninput = () => setSelectedCorrectionPitchInput(exactPitch.value);
      const exactVelocityForm = host.querySelector("#clip-correction-velocity-form");
      if (exactVelocityForm) exactVelocityForm.onsubmit = (event) => {
        event.preventDefault();
        const exactVelocity = host.querySelector("#clip-correction-exact-velocity");
        setSelectedCorrectionVelocityInput(exactVelocity?.value);
      };
      const resetCorrectionNote = host.querySelector("#clip-correction-reset-note");
      if (resetCorrectionNote) resetCorrectionNote.onclick = () => resetSelectedCorrectionNote();
      const markCorrectionDeletion = host.querySelector("#clip-correction-mark-delete");
      if (markCorrectionDeletion) markCorrectionDeletion.onclick = () => markSelectedCorrectionDeletion();
      const keepCorrectionDeletion = host.querySelector("#clip-correction-keep-delete");
      if (keepCorrectionDeletion) keepCorrectionDeletion.onclick = () => keepSelectedCorrectionDeletion();
      const resetCorrectionAll = host.querySelector("#clip-correction-reset-all");
      if (resetCorrectionAll) resetCorrectionAll.onclick = () => resetAllCorrectionChanges();
      const reviewCorrectionButton = host.querySelector("#clip-correction-review");
      if (reviewCorrectionButton) reviewCorrectionButton.onclick = () => reviewCorrection();
      const createCorrectionButton = host.querySelector("#clip-correction-create");
      if (createCorrectionButton) createCorrectionButton.onclick = () => createCorrectionVersion();
      const inspectCorrectionChild = host.querySelector("#clip-correction-inspect-child");
      if (inspectCorrectionChild) inspectCorrectionChild.onclick = () => {
        const child = correctionResultChild();
        if (child?.clip_id) openClip(child.clip_id, "browse");
      };
    }

    function wireTransformChoice(id, callback) {
      const element = host?.querySelector(`#${id}`);
      if (element) element.onclick = callback;
    }

    function restoreTransformFocus() {
      if (!pendingTransformFocusId || !host) return;
      const target = host.querySelector(`#${pendingTransformFocusId}`);
      pendingTransformFocusId = "";
      target?.focus();
    }

    function restoreCorrectionFocus() {
      if (!host) return;
      if (pendingCorrectionFocusId) {
        const target = host.querySelector(`#${pendingCorrectionFocusId}`);
        pendingCorrectionFocusId = "";
        target?.focus();
        return;
      }
      if (!pendingCorrectionFocusRef) return;
      const key = pendingCorrectionFocusRef;
      pendingCorrectionFocusRef = "";
      const target = [...host.querySelectorAll("[data-correction-note-ref]")].find((button) => {
        try {
          return decodeURIComponent(String(button.dataset.correctionNoteRef || "")) === key;
        } catch {
          return false;
        }
      });
      target?.focus();
    }

    async function loadList(offset) {
      const sequence = ++requestSequence;
      loading = true;
      errorMessage = "";
      statusMessage = "";
      filters.offset = Math.max(0, Number(offset) || 0);
      render();
      const query = new URLSearchParams({ limit: String(DEFAULT_LIMIT), offset: String(filters.offset) });
      for (const name of ["text", "role", "key", "bpm"]) if (filters[name]) query.set(name, filters[name]);
      for (const tag of filters.tags.split(",").map((item) => item.trim()).filter(Boolean)) query.append("tag", tag);
      try {
        const value = await api(`/api/clips?${query.toString()}`);
        if (sequence !== requestSequence) return;
        listDocument = value;
        if (browseFiltersAreEmpty()) {
          const total = Number(value?.page?.total);
          if (Number.isInteger(total) && total >= 0) {
            observedLibraryCount = total;
            libraryEvidenceStale = false;
          }
        }
        loading = false;
        render();
      } catch (error) {
        if (sequence !== requestSequence) return;
        loading = false;
        errorMessage = error.message || String(error);
        render();
      }
    }

    function openClip(clipId, returnMode = "browse") {
      stopAudio();
      resetTransformState(false);
      resetCorrectionState(false);
      mode = "detail";
      detailReturnMode = returnMode === "plan" ? "plan" : "browse";
      currentClipId = clipId;
      detailDocument = null;
      errorMessage = "";
      statusMessage = "";
      render();
      loadDetail(clipId);
    }

    async function loadPlan({ afterConflict = false } = {}) {
      if (!reuseEnabled()) return;
      const sequence = ++planRequestSequence;
      planLoading = true;
      planErrorMessage = "";
      if (!afterConflict) actionErrorMessage = "";
      render();
      try {
        const value = await api("/api/clip-reuse-plan");
        if (sequence !== planRequestSequence || !reuseEnabled()) return;
        planDocument = value?.plan || value;
        planLoading = false;
        const restore = String(planDocument?.restore_status || "");
        planStatusMessage = restore.includes("restored") || restore.includes("saved")
          ? "Saved proposal restored for this exact project, setup, library and acceptance gate."
          : "Separate reuse proposal ready. No Clip audition or song decision created it.";
        render();
      } catch (error) {
        if (sequence !== planRequestSequence || !reuseEnabled()) return;
        planLoading = false;
        planErrorMessage = error?.message || String(error);
        render();
      }
    }

    async function loadDetail(clipId) {
      if (!clipId) return;
      const sequence = ++requestSequence;
      loading = true;
      errorMessage = "";
      render();
      try {
        const value = await api(`/api/clips/${encodeURIComponent(clipId)}`);
        if (sequence !== requestSequence || currentClipId !== clipId) return;
        detailDocument = value;
        loading = false;
        render();
      } catch (error) {
        if (sequence !== requestSequence || currentClipId !== clipId) return;
        loading = false;
        errorMessage = error.message || String(error);
        render();
      }
    }

    async function prepareArtifact(includePreview, button) {
      if (!currentClipId) return;
      button.disabled = true;
      const originalLabel = button.textContent;
      button.textContent = includePreview ? "Rendering locally…" : "Preparing exact reconstruction…";
      errorMessage = "";
      statusMessage = "";
      try {
        const value = await api("/api/clip-artifact", {
          method: "POST",
          body: JSON.stringify({ clip_id: currentClipId, include_preview: includePreview }),
        });
        if (mode !== "detail" || currentClipId !== value.artifact?.clip?.clip_id) return;
        artifacts.set(currentClipId, value.artifact);
        statusMessage = includePreview ? "Neutral audition and MIDI are ready. Nothing was preferred, placed or saved." : "Deterministic MIDI is ready. No Clip or reuse-plan state changed.";
        render();
      } catch (error) {
        errorMessage = error.message || String(error);
        render();
      } finally {
        if (button.isConnected) {
          button.disabled = false;
          button.textContent = originalLabel;
        }
      }
    }

    function correctionDraft(clipId) {
      const existing = correctionDrafts.get(clipId);
      if (existing) {
        if (!existing.kind) existing.kind = defaultCorrectionKind(detailDocument?.clip);
        return existing;
      }
      const draft = {
        kind: defaultCorrectionKind(detailDocument?.clip),
        startBeat: "0",
        lengthBeats: String(DEFAULT_CORRECTION_WINDOW_BEATS),
        selectedRefKey: "",
        changes: new Map(),
      };
      correctionDrafts.set(clipId, draft);
      return draft;
    }

    function correctionContract(kind) {
      return Object.prototype.hasOwnProperty.call(CORRECTION_CONTRACTS, kind)
        ? CORRECTION_CONTRACTS[kind]
        : null;
    }

    function correctionKindName(kind) {
      return correctionContract(kind)?.name || "unknown correction";
    }

    function correctionChangeName(kind) {
      return correctionContract(kind)?.changeName || "unknown-correction";
    }

    function correctionKindCapability(kind) {
      if (!correctionContract(kind)) return { enabled: false, drum_family: false };
      const corrections = correctionCapability?.corrections;
      if (!corrections || typeof corrections !== "object" || Array.isArray(corrections)) {
        return kind === CORRECTION_KIND_PITCH ? { enabled: true, drum_family: false } : { enabled: false, drum_family: false };
      }
      const declared = corrections[kind];
      if (declared === true) return { enabled: true, drum_family: kind !== CORRECTION_KIND_PITCH };
      if (!declared || typeof declared !== "object" || Array.isArray(declared)) return { enabled: false, drum_family: false };
      return { enabled: declared.enabled === true, drum_family: declared.drum_family === true };
    }

    function correctionKindSupported(kind, clip = detailDocument?.clip) {
      const declared = correctionKindCapability(kind);
      if (!declared.enabled) return false;
      if (isDrumFamilyClip(clip) && kind === CORRECTION_KIND_PITCH) return false;
      if (isDrumFamilyClip(clip)) return declared.drum_family;
      return true;
    }

    function correctionKindsForClip(clip) {
      return [CORRECTION_KIND_PITCH, CORRECTION_KIND_VELOCITY, CORRECTION_KIND_DELETE].filter((kind) => correctionKindSupported(kind, clip));
    }

    function defaultCorrectionKind(clip) {
      if (isDrumFamilyClip(clip) && correctionKindSupported(CORRECTION_KIND_VELOCITY, clip)) return CORRECTION_KIND_VELOCITY;
      if (correctionKindSupported(CORRECTION_KIND_PITCH, clip)) return CORRECTION_KIND_PITCH;
      if (correctionKindSupported(CORRECTION_KIND_VELOCITY, clip)) return CORRECTION_KIND_VELOCITY;
      return CORRECTION_KIND_PITCH;
    }

    function setCorrectionKind(kind, focusId = "") {
      if (!currentClipId || correctionPending || !correctionKindSupported(kind, detailDocument?.clip)) return;
      const draft = correctionDraft(currentClipId);
      if (draft.kind === kind) return;
      if (draft.changes.size) {
        correctionErrorMessage = "Reset all draft changes before switching correction kind.";
        correctionStatusMessage = "";
        pendingCorrectionFocusId = focusId;
        render();
        return;
      }
      draft.kind = kind;
      draft.selectedRefKey = "";
      correctionWindowDocument = null;
      correctionWindowContract = null;
      invalidateCorrectionProjection(`Correction kind changed to ${correctionKindName(kind)}. Load the exact bounded note window again.`);
      pendingCorrectionFocusId = focusId;
      render();
    }

    function correctionTargetField(kind = correctionDraft(currentClipId).kind) {
      if (kind === CORRECTION_KIND_PITCH) return "target_pitch";
      if (kind === CORRECTION_KIND_VELOCITY) return "target_velocity";
      if (kind === CORRECTION_KIND_DELETE) return null;
      return null;
    }

    function correctionNoteBlockReason(note) {
      const value = note?.edit_block_reason ?? note?.blocked_reason;
      return value == null ? "" : String(value);
    }

    function correctionNoteBlockedLabel(note) {
      const reason = correctionNoteBlockReason(note);
      if (reason === "duplicate-export-note-on") return "blocked: duplicate exported Note On shares channel, start and pitch";
      if (reason === "context-note-on-outside-window") return "context only: Note On begins outside this window";
      if (reason === "retained-note-lifetime-would-change") return "blocked: removal would change a retained note lifetime";
      if (reason === "clip-horizon-would-change") return "blocked: removal would change the Clip horizon";
      if (reason === "only-note-in-clip") return "blocked: at least one parent note must remain";
      if (reason) return `blocked: ${reason}`;
      if (note?.editable === false) return "context only";
      return "";
    }

    function correctionNoteEditable(note) {
      return note?.editable !== false && !correctionNoteBlockReason(note);
    }

    function correctionActionAllowed(name) {
      const actions = correctionCapability?.actions;
      if (Array.isArray(actions)) return actions.includes(name);
      return !!actions && actions[name] === true;
    }

    function correctionTicksPerBeat() {
      const candidates = [
        correctionWindowDocument?.window?.ticks_per_beat,
        correctionWindowDocument?.ticks_per_beat,
        correctionCapability?.grid?.ticks_per_beat,
        correctionCapability?.window?.ticks_per_beat,
        correctionCapability?.ticks_per_beat,
        correctionCapability?.limits?.ticks_per_beat,
        CORRECTION_TICKS_PER_BEAT,
      ];
      for (const value of candidates) {
        const number = Number(value);
        if (Number.isInteger(number) && number > 0) return number;
      }
      return CORRECTION_TICKS_PER_BEAT;
    }

    function correctionMaximumWindowBeats() {
      const declared = Number(correctionCapability?.limits?.maximum_window_beats);
      if (!Number.isFinite(declared) || declared <= 0) return MAXIMUM_CORRECTION_WINDOW_BEATS;
      return Math.min(MAXIMUM_CORRECTION_WINDOW_BEATS, declared);
    }

    function correctionMaximumChanges() {
      const declared = Number(correctionCapability?.limits?.maximum_changes ?? correctionCapability?.limits?.maximum_edits);
      if (!Number.isInteger(declared) || declared < 1) return MAXIMUM_CORRECTION_CHANGES;
      return Math.min(MAXIMUM_CORRECTION_CHANGES, declared);
    }

    function correctionMaximumPitchDelta() {
      const declared = Number(correctionCapability?.limits?.maximum_pitch_delta_semitones);
      if (!Number.isInteger(declared) || declared < 1) return MAXIMUM_CORRECTION_PITCH_DELTA;
      return Math.min(MAXIMUM_CORRECTION_PITCH_DELTA, declared);
    }

    function updateCorrectionWindowDraftFromInputs() {
      if (!currentClipId || !host) return;
      const draft = correctionDraft(currentClipId);
      const start = host.querySelector("#clip-correction-window-start");
      const length = host.querySelector("#clip-correction-window-length");
      if (start) draft.startBeat = String(start.value || "").trim();
      if (length) draft.lengthBeats = String(length.value || "").trim();
    }

    function setCorrectionWindowDraftValue(name, value, focusId) {
      if (!currentClipId || correctionPending) return;
      const draft = correctionDraft(currentClipId);
      if (draft[name] === value) return;
      draft[name] = value;
      draft.selectedRefKey = "";
      draft.changes.clear();
      correctionWindowDocument = null;
      correctionWindowContract = null;
      invalidateCorrectionProjection("Window changed. Load the bounded notes again; the earlier temporary note draft was cleared.");
      pendingCorrectionFocusId = focusId;
      render();
    }

    function validatedCorrectionWindow() {
      const draft = correctionDraft(currentClipId);
      const startBeat = Number(draft.startBeat);
      const lengthBeats = Number(draft.lengthBeats);
      const ticksPerBeat = correctionTicksPerBeat();
      const maximum = correctionMaximumWindowBeats();
      if (!Number.isFinite(startBeat) || startBeat < 0) throw new Error("Window start beat must be zero or greater.");
      if (!Number.isFinite(lengthBeats) || lengthBeats <= 0 || lengthBeats > maximum) throw new Error(`Window length must be greater than zero and at most ${numberLabel(maximum)} beats.`);
      const startTick = Math.round(startBeat * ticksPerBeat);
      const lengthTicks = Math.round(lengthBeats * ticksPerBeat);
      if (Math.abs(startBeat * ticksPerBeat - startTick) > 1e-7 || Math.abs(lengthBeats * ticksPerBeat - lengthTicks) > 1e-7) {
        throw new Error(`Window values must land on the ${ticksPerBeat}-ticks-per-beat grid.`);
      }
      if (!Number.isSafeInteger(startTick) || startTick < 0 || !Number.isSafeInteger(lengthTicks) || lengthTicks < 1 || !Number.isSafeInteger(startTick + lengthTicks)) {
        throw new Error("Window tick positions exceed the safe local correction range.");
      }
      return { start_tick: startTick, end_tick: startTick + lengthTicks };
    }

    function correctionPins() {
      const clip = detailDocument?.clip || {};
      const libraryState = detailDocument?.library_state_sha256 || capability?.library?.state_sha256;
      if (!clip.clip_id || !isSha256(clip.object_sha256) || !isSha256(libraryState)) {
        throw new Error("The exact Clip and library pins are unavailable; reload the Clip detail.");
      }
      return {
        parent_clip_id: clip.clip_id,
        parent_object_sha256: clip.object_sha256,
        library_state_sha256: libraryState,
      };
    }

    function correctionWindowSha256() {
      const value = correctionWindowDocument?.window_sha256;
      return isSha256(value) ? value : "";
    }

    function correctionNotes() {
      return list(correctionWindowDocument?.notes).filter((note) => note && typeof note === "object" && note.note_ref != null);
    }

    function correctionNoteRefKey(value) {
      if (value && typeof value === "object" && !Array.isArray(value)) {
        const index = Number(value.index);
        const hash = String(value.note_sha256 || value.sha256 || "");
        if (Number.isSafeInteger(index) && index >= 0 && hash) return `index:${index}:${hash}`;
        return `object:${stableJson(value)}`;
      }
      return `value:${String(value ?? "")}`;
    }

    function noteRefLabel(value) {
      if (value && typeof value === "object" && !Array.isArray(value)) {
        const index = Number(value.index);
        if (Number.isSafeInteger(index) && index >= 0) return `note ${index + 1}`;
      }
      const text = String(value ?? "note");
      return text.length > 48 ? `${text.slice(0, 48)}…` : text || "note";
    }

    function correctionNotePitch(note) {
      const pitch = Number(note?.pitch);
      return Number.isInteger(pitch) && pitch >= 0 && pitch <= 127 ? pitch : 0;
    }

    function correctionNoteVelocity(note) {
      const velocity = Number(note?.velocity);
      return Number.isInteger(velocity) && velocity >= 1 && velocity <= 127 ? velocity : "unknown";
    }

    function correctionNoteStartBeat(note) {
      const beat = Number(note?.start_beat);
      if (Number.isFinite(beat)) return beat;
      const tick = Number(note?.start_tick);
      return Number.isFinite(tick) ? tick / correctionTicksPerBeat() : 0;
    }

    function correctionNoteDurationBeats(note) {
      const duration = Number(note?.duration_beats);
      if (Number.isFinite(duration) && duration > 0) return duration;
      const startTick = Number(note?.start_tick);
      const endTick = Number(note?.end_tick);
      if (Number.isFinite(startTick) && Number.isFinite(endTick) && endTick > startTick) return (endTick - startTick) / correctionTicksPerBeat();
      return 1 / correctionTicksPerBeat();
    }

    function correctionChangeForKey(key) {
      return correctionDraft(currentClipId).changes.get(key) || null;
    }

    function correctionChanges() {
      const draft = correctionDraft(currentClipId);
      const field = correctionTargetField(draft.kind);
      const ordered = [];
      const seen = new Set();
      for (const note of correctionNotes()) {
        const key = correctionNoteRefKey(note.note_ref);
        const change = draft.changes.get(key);
        if (draft.kind === CORRECTION_KIND_DELETE) {
          if (change && !seen.has(key)) {
            ordered.push({ note_ref: cloneJson(change.note_ref) });
            seen.add(key);
          }
          continue;
        }
        const target = change?.[field];
        if (Number.isInteger(target) && !seen.has(key)) {
          ordered.push({ note_ref: cloneJson(change.note_ref), [field]: target });
          seen.add(key);
        }
      }
      if (draft.kind === CORRECTION_KIND_DELETE) ordered.sort((left, right) => String(left.note_ref).localeCompare(String(right.note_ref)));
      return ordered;
    }

    function correctionSelectedNote() {
      const draft = correctionDraft(currentClipId);
      const key = draft.selectedRefKey;
      const note = key ? correctionNotes().find((item) => correctionNoteRefKey(item.note_ref) === key) || null : null;
      if (draft.kind === CORRECTION_KIND_DELETE) return note;
      return note && correctionNoteEditable(note) ? note : null;
    }

    function correctionEffectivePitch(note) {
      const source = correctionNotePitch(note);
      const target = correctionChangeForKey(correctionNoteRefKey(note.note_ref))?.target_pitch;
      return Number.isInteger(target) ? target : source;
    }

    function correctionEffectiveVelocity(note) {
      const source = Number(correctionNoteVelocity(note));
      const target = correctionChangeForKey(correctionNoteRefKey(note.note_ref))?.target_velocity;
      return Number.isInteger(target) ? target : source;
    }

    function correctionSourceValue(note) {
      return correctionDraft(currentClipId).kind === CORRECTION_KIND_VELOCITY
        ? Number(correctionNoteVelocity(note))
        : correctionNotePitch(note);
    }

    function correctionEffectiveValue(note) {
      return correctionDraft(currentClipId).kind === CORRECTION_KIND_VELOCITY
        ? correctionEffectiveVelocity(note)
        : correctionEffectivePitch(note);
    }

    function selectCorrectionNote(key, restoreFocus) {
      if (!correctionWindowDocument || correctionPending) return;
      const note = correctionNotes().find((item) => correctionNoteRefKey(item.note_ref) === key);
      const draft = correctionDraft(currentClipId);
      if (!note || (!correctionNoteEditable(note) && draft.kind !== CORRECTION_KIND_DELETE)) return;
      if (draft.selectedRefKey === key) return;
      draft.selectedRefKey = key;
      if (restoreFocus) pendingCorrectionFocusRef = key;
      render();
    }

    function markSelectedCorrectionDeletion() {
      const draft = correctionDraft(currentClipId);
      const note = correctionSelectedNote();
      if (!note || correctionPending || draft.kind !== CORRECTION_KIND_DELETE) return;
      const key = correctionNoteRefKey(note.note_ref);
      if (!correctionNoteEditable(note)) {
        correctionErrorMessage = `This note cannot be removed: ${correctionNoteBlockedLabel(note) || "the server marked it as context-only"}.`;
        correctionStatusMessage = "";
        pendingCorrectionFocusId = "clip-correction-mark-delete";
        render();
        return;
      }
      if (draft.changes.has(key)) {
        correctionErrorMessage = "";
        correctionStatusMessage = "That note is already marked for removal. The reviewed projection, if present, remains valid.";
        pendingCorrectionFocusId = "clip-correction-mark-delete";
        render();
        return;
      }
      if (draft.changes.size >= correctionMaximumChanges()) {
        correctionErrorMessage = `This correction is limited to ${correctionMaximumChanges()} removed notes. Keep one before marking another.`;
        correctionStatusMessage = "";
        pendingCorrectionFocusId = "clip-correction-mark-delete";
        render();
        return;
      }
      const parentNoteCount = Number(detailDocument?.clip?.note_count);
      if (!Number.isInteger(parentNoteCount) || parentNoteCount < 1 || draft.changes.size + 1 >= parentNoteCount) {
        correctionErrorMessage = "At least one parent note must remain in the immutable child; this note was not marked for removal.";
        correctionStatusMessage = "";
        pendingCorrectionFocusId = "clip-correction-mark-delete";
        render();
        return;
      }
      draft.changes.set(key, { note_ref: cloneJson(note.note_ref) });
      invalidateCorrectionProjection(`Temporary note-removal draft updated: ${draft.changes.size} note${draft.changes.size === 1 ? "" : "s"} marked for removal. Review is required before creation.`);
      pendingCorrectionFocusId = "clip-correction-keep-delete";
      render();
    }

    function keepSelectedCorrectionDeletion() {
      const draft = correctionDraft(currentClipId);
      const note = correctionSelectedNote();
      if (!note || correctionPending || draft.kind !== CORRECTION_KIND_DELETE) return;
      const key = correctionNoteRefKey(note.note_ref);
      if (!draft.changes.has(key)) {
        correctionErrorMessage = "";
        correctionStatusMessage = "That note is already kept. The reviewed projection, if present, remains valid.";
        pendingCorrectionFocusId = "clip-correction-mark-delete";
        render();
        return;
      }
      draft.changes.delete(key);
      invalidateCorrectionProjection(`The selected note is kept in the immutable parent state. ${draft.changes.size} note${draft.changes.size === 1 ? " remains" : "s remain"} marked for removal; review is required again.`);
      pendingCorrectionFocusId = "clip-correction-mark-delete";
      render();
    }

    function changeSelectedCorrectionPitch(delta) {
      const note = correctionSelectedNote();
      if (!note || correctionPending || correctionDraft(currentClipId).kind !== CORRECTION_KIND_PITCH || !Number.isInteger(delta)) return;
      setSelectedCorrectionPitch(correctionEffectivePitch(note) + delta, "clip-correction-exact-pitch");
    }

    function setSelectedCorrectionPitch(value, focusId = "") {
      const note = correctionSelectedNote();
      if (!note || correctionPending || correctionDraft(currentClipId).kind !== CORRECTION_KIND_PITCH) return;
      const pitch = Number(value);
      if (!Number.isInteger(pitch) || pitch < 0 || pitch > 127) {
        correctionErrorMessage = "Exact MIDI pitch must be a whole number from 0 to 127.";
        correctionStatusMessage = "";
        pendingCorrectionFocusId = focusId;
        render();
        return;
      }
      const draft = correctionDraft(currentClipId);
      const key = correctionNoteRefKey(note.note_ref);
      const sourcePitch = correctionNotePitch(note);
      if (Math.abs(pitch - sourcePitch) > correctionMaximumPitchDelta()) {
        correctionErrorMessage = `Exact MIDI pitch must remain within ${correctionMaximumPitchDelta()} semitones of the immutable parent note.`;
        correctionStatusMessage = "";
        pendingCorrectionFocusId = focusId;
        render();
        return;
      }
      const previous = draft.changes.get(key);
      const unchanged = pitch === sourcePitch
        ? !previous
        : Number(previous?.target_pitch) === pitch;
      if (unchanged) {
        correctionErrorMessage = "";
        correctionStatusMessage = "That exact pitch is already the current draft value. The reviewed projection, if present, remains valid.";
        pendingCorrectionFocusId = focusId;
        render();
        return;
      }
      if (pitch === sourcePitch) {
        draft.changes.delete(key);
      } else {
        if (!draft.changes.has(key) && draft.changes.size >= correctionMaximumChanges()) {
          correctionErrorMessage = `This correction is limited to ${correctionMaximumChanges()} changed notes. Reset one before adding another.`;
          correctionStatusMessage = "";
          pendingCorrectionFocusId = focusId;
          render();
          return;
        }
        draft.changes.set(key, { note_ref: cloneJson(note.note_ref), target_pitch: pitch });
      }
      invalidateCorrectionProjection(`Temporary pitch draft updated: ${draft.changes.size} changed note${draft.changes.size === 1 ? "" : "s"}. Review is required before creation.`);
      pendingCorrectionFocusId = focusId;
      render();
    }

    function setSelectedCorrectionPitchInput(value) {
      const text = String(value ?? "").trim();
      if (!text) {
        correctionErrorMessage = "Exact MIDI pitch must be a whole number from 0 to 127.";
        correctionStatusMessage = "";
        pendingCorrectionFocusId = "clip-correction-exact-pitch";
        render();
        return;
      }
      setSelectedCorrectionPitch(Number(text), "clip-correction-exact-pitch");
    }

    function changeSelectedCorrectionVelocity(delta) {
      const note = correctionSelectedNote();
      if (!note || correctionPending || correctionDraft(currentClipId).kind !== CORRECTION_KIND_VELOCITY || !Number.isInteger(delta)) return;
      setSelectedCorrectionVelocity(correctionEffectiveVelocity(note) + delta, "clip-correction-exact-velocity");
    }

    function setSelectedCorrectionVelocity(value, focusId = "") {
      const note = correctionSelectedNote();
      if (!note || correctionPending || correctionDraft(currentClipId).kind !== CORRECTION_KIND_VELOCITY) return;
      const velocity = Number(value);
      if (!Number.isInteger(velocity) || velocity < 1 || velocity > 127) {
        correctionErrorMessage = "Exact MIDI attack velocity must be a whole number from 1 to 127; the value was not clamped or applied.";
        correctionStatusMessage = "";
        pendingCorrectionFocusId = focusId;
        render();
        return;
      }
      const draft = correctionDraft(currentClipId);
      const key = correctionNoteRefKey(note.note_ref);
      const sourceVelocity = Number(correctionNoteVelocity(note));
      const previous = draft.changes.get(key);
      const unchanged = velocity === sourceVelocity
        ? !previous
        : Number(previous?.target_velocity) === velocity;
      if (unchanged) {
        correctionErrorMessage = "";
        correctionStatusMessage = "That exact attack velocity is already the current draft value. The reviewed projection, if present, remains valid.";
        pendingCorrectionFocusId = focusId;
        render();
        return;
      }
      if (velocity === sourceVelocity) {
        draft.changes.delete(key);
      } else {
        if (!draft.changes.has(key) && draft.changes.size >= correctionMaximumChanges()) {
          correctionErrorMessage = `This correction is limited to ${correctionMaximumChanges()} changed notes. Reset one before adding another.`;
          correctionStatusMessage = "";
          pendingCorrectionFocusId = focusId;
          render();
          return;
        }
        draft.changes.set(key, { note_ref: cloneJson(note.note_ref), target_velocity: velocity });
      }
      invalidateCorrectionProjection(`Temporary attack-velocity draft updated: ${draft.changes.size} changed note${draft.changes.size === 1 ? "" : "s"}. Review is required before creation.`);
      pendingCorrectionFocusId = focusId;
      render();
    }

    function setSelectedCorrectionVelocityInput(value) {
      const text = String(value ?? "").trim();
      if (!text) {
        correctionErrorMessage = "Exact MIDI attack velocity must be a whole number from 1 to 127; no edit was applied.";
        correctionStatusMessage = "";
        pendingCorrectionFocusId = "clip-correction-exact-velocity";
        render();
        return;
      }
      setSelectedCorrectionVelocity(Number(text), "clip-correction-exact-velocity");
    }

    function resetSelectedCorrectionNote() {
      const draft = correctionDraft(currentClipId);
      if (!draft.selectedRefKey || correctionPending || !draft.changes.delete(draft.selectedRefKey)) return;
      const resetValue = draft.kind === CORRECTION_KIND_DELETE ? "retained state" : draft.kind === CORRECTION_KIND_VELOCITY ? "attack velocity" : "pitch";
      invalidateCorrectionProjection(`The selected note was reset to the immutable parent ${resetValue}. Review the remaining draft again.`);
      pendingCorrectionFocusRef = draft.selectedRefKey;
      render();
    }

    function resetAllCorrectionChanges() {
      const draft = correctionDraft(currentClipId);
      if (!draft.changes.size || correctionPending) return;
      draft.changes.clear();
      invalidateCorrectionProjection(`All temporary ${correctionChangeName(draft.kind)} changes were reset. The immutable parent was never changed; correction-kind switching is available again.`);
      if (draft.selectedRefKey) pendingCorrectionFocusRef = draft.selectedRefKey;
      render();
    }

    function invalidateCorrectionProjection(message = "") {
      correctionRequestSequence += 1;
      correctionProjection = null;
      correctionProjectionCorrection = null;
      correctionResult = null;
      correctionErrorMessage = "";
      correctionStatusMessage = message;
    }

    function exactObjectKeys(value, expectedKeys) {
      if (!value || typeof value !== "object" || Array.isArray(value)) return false;
      return stableJson(Object.keys(value).sort()) === stableJson([...expectedKeys].sort());
    }

    function finiteNumber(value) {
      return typeof value === "number" && Number.isFinite(value);
    }

    function deletionWindowNoteValid(note, requestWindow) {
      if (!exactObjectKeys(note, DELETE_WINDOW_NOTE_KEYS) || !isSha256(note.note_ref)) return false;
      const reason = note.edit_block_reason;
      if (reason !== null && !DELETE_BLOCK_REASONS.includes(reason)) return false;
      if (typeof note.editable !== "boolean" || note.editable !== (reason === null)) return false;
      if (!Number.isInteger(note.export_note_on_group_size) || note.export_note_on_group_size < 1) return false;
      if (!Number.isInteger(note.channel) || note.channel < 0 || note.channel > 15) return false;
      if (!Number.isInteger(note.pitch) || note.pitch < 0 || note.pitch > 127) return false;
      if (!Number.isInteger(note.velocity) || note.velocity < 1 || note.velocity > 127) return false;
      if (!Number.isInteger(note.release_velocity) || note.release_velocity < 0 || note.release_velocity > 127) return false;
      if (!Number.isSafeInteger(note.start_tick) || !Number.isSafeInteger(note.end_tick) || note.start_tick < 0 || note.end_tick <= note.start_tick) return false;
      if (!finiteNumber(note.start_beat) || !finiteNumber(note.duration_beats) || note.duration_beats <= 0) return false;
      if (!finiteNumber(note.source_start_seconds) || !finiteNumber(note.source_end_seconds) || note.source_start_seconds < 0 || note.source_end_seconds <= note.source_start_seconds) return false;
      if (!(note.articulation === null || typeof note.articulation === "string")) return false;
      if (note.end_tick <= requestWindow.start_tick || note.start_tick >= requestWindow.end_tick) return false;
      const startsInWindow = note.start_tick >= requestWindow.start_tick && note.start_tick < requestWindow.end_tick;
      if (reason === "context-note-on-outside-window") return !startsInWindow;
      return startsInWindow;
    }

    function deletionWindowMatchesRequest(document, request) {
      const contract = correctionContract(CORRECTION_KIND_DELETE);
      const expectedTopKeys = [
        "blocked_note_count", "blocked_reason_counts", "chords", "correction_kind",
        "editable_note_count", "effects", "library", "notes", "operation", "parent",
        "policies", "schema", "timing", "visible_note_count", "window", "window_sha256",
      ];
      if (!exactObjectKeys(document, expectedTopKeys)) return false;
      if (document.schema !== contract.windowSchema || document.operation !== contract.windowOperation || document.correction_kind !== CORRECTION_KIND_DELETE) return false;
      if (!isSha256(document.window_sha256) || stableJson(document.library) !== stableJson({state_sha256: request.library_state_sha256})) return false;
      if (!correctionEffectsMatch(document.effects, CORRECTION_KIND_DELETE, false)) return false;
      const parent = document.parent || {};
      if (!deletionParentIdentityMatches(parent, request)) return false;
      const window = document.window || {};
      if (!exactObjectKeys(window, ["duration_seconds", "end_tick", "origin", "start_tick", "ticks_per_beat"])) return false;
      if (window.start_tick !== request.window.start_tick || window.end_tick !== request.window.end_tick || window.ticks_per_beat !== correctionTicksPerBeat() || window.origin !== "recorded-zero" || !finiteNumber(window.duration_seconds) || window.duration_seconds < 0) return false;
      const timing = document.timing || {};
      if (!exactObjectKeys(timing, ["export_bpm", "resolved_mode"]) || typeof timing.resolved_mode !== "string" || !timing.resolved_mode || !finiteNumber(timing.export_bpm) || timing.export_bpm <= 0) return false;
      if (!Array.isArray(document.notes) || !Array.isArray(document.chords) || !document.policies || typeof document.policies !== "object" || Array.isArray(document.policies)) return false;
      if (!document.notes.every((note) => deletionWindowNoteValid(note, window))) return false;
      const refs = document.notes.map((note) => note.note_ref);
      if (new Set(refs).size !== refs.length) return false;
      const editableCount = document.notes.filter((note) => note.editable).length;
      const blockedCount = document.notes.length - editableCount;
      if (document.visible_note_count !== document.notes.length || document.editable_note_count !== editableCount || document.blocked_note_count !== blockedCount) return false;
      if (!document.blocked_reason_counts || typeof document.blocked_reason_counts !== "object" || Array.isArray(document.blocked_reason_counts)) return false;
      const reasonKeys = Object.keys(document.blocked_reason_counts).sort();
      if (stableJson(reasonKeys) !== stableJson([...DELETE_BLOCK_REASONS].sort())) return false;
      for (const reason of DELETE_BLOCK_REASONS) {
        const expected = document.notes.filter((note) => note.edit_block_reason === reason).length;
        if (!Number.isInteger(document.blocked_reason_counts[reason]) || document.blocked_reason_counts[reason] !== expected) return false;
      }
      return true;
    }

    function correctionWindowMatchesRequest(document, request, kind) {
      const contract = correctionContract(kind);
      if (!contract) return false;
      if (kind === CORRECTION_KIND_DELETE) return deletionWindowMatchesRequest(document, request);
      return isSha256(document?.window_sha256)
        && Array.isArray(document?.notes)
        && (!contract.windowDiscriminator || document?.correction_kind === kind)
        && (!document?.schema || document.schema === contract.windowSchema)
        && (!document?.operation || document.operation === contract.windowOperation)
        && allEffectsFalse(document?.effects);
    }

    async function loadCorrectionWindow({ preserveDraft = false, afterConflict = false } = {}) {
      if (!correctionEnabled() || !correctionActionAllowed("window") || correctionPending || !currentClipId) return;
      correctionErrorMessage = "";
      correctionStatusMessage = "";
      let window;
      let pins;
      try {
        window = validatedCorrectionWindow();
        pins = correctionPins();
      } catch (error) {
        correctionErrorMessage = error?.message || String(error);
        render();
        focusCorrectionStatus();
        return;
      }
      const draft = correctionDraft(currentClipId);
      const preservedChanges = preserveDraft ? new Map(draft.changes) : new Map();
      const preservedSelection = preserveDraft ? draft.selectedRefKey : "";
      const request = { ...pins, window };
      const contract = correctionContract(draft.kind);
      if (!contract) {
        correctionErrorMessage = "The selected correction kind is not recognized. No request was sent.";
        render();
        focusCorrectionStatus();
        return;
      }
      if (contract.windowDiscriminator) request.correction_kind = draft.kind;
      const sourceClipId = currentClipId;
      const sequence = ++correctionRequestSequence;
      correctionPending = "window";
      render();
      focusCorrectionStatus();
      try {
        const value = await api("/api/clip-note-correction-window", { method: "POST", body: JSON.stringify(request) });
        if (sequence !== correctionRequestSequence || mode !== "detail" || currentClipId !== sourceClipId) return;
        const document = value?.window?.window_sha256 && Array.isArray(value.window.notes) ? value.window : value?.document || value;
        if (!correctionWindowMatchesRequest(document, request, draft.kind)) {
          throw new Error("The local server returned an invalid bounded note window.");
        }
        correctionWindowDocument = document;
        correctionWindowContract = { ...window };
        correctionProjection = null;
        correctionProjectionCorrection = null;
        correctionResult = null;
        const available = new Set(correctionNotes().filter(correctionNoteEditable).map((note) => correctionNoteRefKey(note.note_ref)));
        draft.changes.clear();
        if (preserveDraft) {
          for (const [key, change] of preservedChanges) if (available.has(key)) draft.changes.set(key, change);
        }
        draft.selectedRefKey = preserveDraft && available.has(preservedSelection) ? preservedSelection : "";
        const dropped = preserveDraft ? preservedChanges.size - draft.changes.size : 0;
        correctionStatusMessage = preserveDraft
          ? `Latest exact note window loaded. ${draft.changes.size} still-valid draft change${draft.changes.size === 1 ? "" : "s"} retained${dropped ? `; ${dropped} stale reference${dropped === 1 ? " was" : "s were"} removed` : ""}. Review is required again.`
          : `Exact note window loaded with ${correctionNotes().length} note${correctionNotes().length === 1 ? "" : "s"}. No note or ${correctionKindName(draft.kind)} decision is selected.`;
      } catch (error) {
        if (sequence !== correctionRequestSequence) return;
        if (Number(error?.status) === 409 && !afterConflict) {
          correctionPending = "";
          await reloadCorrectionAfterConflict("The Clip library changed while loading notes. Detail and this exact window were reloaded once; no write was attempted.");
          return;
        }
        correctionErrorMessage = Number(error?.status) === 409
          ? "The exact note window changed again while reloading. No further retry was attempted."
          : error?.message || String(error);
      } finally {
        if (sequence === correctionRequestSequence) correctionPending = "";
        render();
        if (correctionErrorMessage) focusCorrectionStatus();
        else if (correctionWindowDocument) host?.querySelector("#clip-correction-roll-heading")?.focus?.();
      }
    }

    function correctionRequest() {
      if (!correctionWindowDocument || !correctionWindowContract || !isSha256(correctionWindowSha256())) throw new Error("Load the exact bounded note window before reviewing corrections.");
      const draft = correctionDraft(currentClipId);
      const contract = correctionContract(draft.kind);
      if (!contract || !correctionKindSupported(draft.kind, detailDocument?.clip)) throw new Error("The selected correction kind is unavailable for this Clip.");
      const changes = correctionChanges();
      if (!changes.length) throw new Error(`${draft.kind === CORRECTION_KIND_DELETE ? "Mark at least one note for removal" : `Change at least one note ${correctionKindName(draft.kind)}`} before reviewing.`);
      if (changes.length > correctionMaximumChanges()) throw new Error(`At most ${correctionMaximumChanges()} notes may be changed in one child.`);
      if (draft.kind === CORRECTION_KIND_DELETE && changes.length >= Number(detailDocument?.clip?.note_count || 0)) throw new Error("At least one parent note must remain in the immutable child.");
      return {
        ...correctionPins(),
        window: { ...correctionWindowContract },
        window_sha256: correctionWindowSha256(),
        correction: { kind: draft.kind, changes },
      };
    }

    function correctionEffectKeys(kind) {
      return correctionContract(kind)?.effectKeys || null;
    }

    function correctionEffectsMatch(value, kind, changed = false) {
      if (!value || typeof value !== "object" || Array.isArray(value)) return false;
      const expectedKeys = correctionEffectKeys(kind);
      if (!expectedKeys) return false;
      const actualKeys = Object.keys(value).sort();
      if (stableJson(actualKeys) !== stableJson([...expectedKeys].sort())) return false;
      const trueKeys = changed
        ? new Set(correctionContract(kind).freshEffectKeys)
        : new Set();
      return actualKeys.every((key) => value[key] === trueKeys.has(key));
    }

    function deletionRangeValid(value) {
      if (!value || typeof value !== "object" || Array.isArray(value)) return false;
      const minimum = value.minimum;
      const maximum = value.maximum;
      return Number.isInteger(minimum) && minimum >= 0 && minimum <= 127
        && Number.isInteger(maximum) && maximum >= minimum && maximum <= 127;
    }

    function deletionParentIdentityMatches(parent, request) {
      if (!exactObjectKeys(parent, DELETE_IDENTITY_KEYS)) return false;
      const clip = detailDocument?.clip || {};
      return parent.clip_id === request.parent_clip_id
        && parent.object_sha256 === request.parent_object_sha256
        && (parent.parent_clip_id === null || typeof parent.parent_clip_id === "string")
        && typeof parent.lineage_id === "string" && parent.lineage_id.length > 0
        && Number.isInteger(parent.revision) && parent.revision >= 1
        && stableJson(parent.key) === stableJson(clip.key ?? null)
        && finiteNumber(parent.bpm) && Number(parent.bpm) === Number(clip.bpm)
        && typeof parent.role === "string" && parent.role === String(clip.role || "")
        && typeof parent.role_redacted === "boolean"
        && parent.note_count === Number(clip.note_count)
        && parent.chord_count === Number(clip.chord_count)
        && stableJson(parent.pitch_range) === stableJson(clip.pitch_range)
        && finiteNumber(parent.duration_seconds) && parent.duration_seconds >= 0;
    }

    function deletionChildIdentityMatches(parent, child, diff, intentSha256, request) {
      if (!exactObjectKeys(child, DELETE_IDENTITY_KEYS)) return false;
      return child.clip_id === `sf-correction-${intentSha256}`
        && isSha256(child.object_sha256)
        && child.parent_clip_id === request.parent_clip_id
        && child.lineage_id === parent.lineage_id
        && child.revision === parent.revision + 1
        && stableJson(child.key) === stableJson(parent.key)
        && child.bpm === parent.bpm
        && child.role === parent.role
        && child.role_redacted === parent.role_redacted
        && child.note_count === diff.note_count_after
        && child.chord_count === parent.chord_count
        && stableJson(child.pitch_range) === stableJson(diff.pitch_range_after)
        && finiteNumber(child.duration_seconds)
        && child.duration_seconds === parent.duration_seconds;
    }

    function deletionDiffRowMatchesNote(row, note) {
      if (!exactObjectKeys(row, DELETE_DIFF_ROW_KEYS)) return false;
      for (const field of DELETE_DIFF_ROW_KEYS) {
        if (field === "note_ref") continue;
        if (stableJson(row[field]) !== stableJson(note[field])) return false;
      }
      return stableJson(row.note_ref) === stableJson(note.note_ref);
    }

    function deletionDiffMatchesRequest(diff, request) {
      if (!exactObjectKeys(diff, DELETE_DIFF_KEYS) || diff.kind !== CORRECTION_KIND_DELETE) return false;
      const requested = list(request?.correction?.changes);
      const rows = list(diff.changes);
      if (diff.changed_note_count !== requested.length || rows.length !== requested.length) return false;
      const requestsByRef = new Map();
      for (const change of requested) {
        if (!exactObjectKeys(change, ["note_ref"]) || !isSha256(change.note_ref)) return false;
        const key = correctionNoteRefKey(change.note_ref);
        if (requestsByRef.has(key)) return false;
        requestsByRef.set(key, change);
      }
      const notesByRef = new Map(correctionNotes().map((note) => [correctionNoteRefKey(note.note_ref), note]));
      const seen = new Set();
      for (const row of rows) {
        const key = correctionNoteRefKey(row?.note_ref);
        const note = notesByRef.get(key);
        if (!requestsByRef.has(key) || !note || !correctionNoteEditable(note) || seen.has(key) || !deletionDiffRowMatchesNote(row, note)) return false;
        seen.add(key);
      }
      const noteCountBefore = Number(detailDocument?.clip?.note_count);
      if (!Number.isInteger(noteCountBefore) || noteCountBefore < 1) return false;
      if (diff.note_count_before !== noteCountBefore || diff.note_count_after !== noteCountBefore - requested.length || diff.note_count_after < 1) return false;
      if (!Number.isInteger(diff.normalized_midi_note_count_before) || !Number.isInteger(diff.normalized_midi_note_count_after)) return false;
      if (diff.normalized_midi_note_count_before < requested.length + 1 || diff.normalized_midi_note_count_before > noteCountBefore || diff.normalized_midi_note_count_after !== diff.normalized_midi_note_count_before - requested.length) return false;
      if (!deletionRangeValid(diff.pitch_range_before) || !deletionRangeValid(diff.pitch_range_after)) return false;
      const detailRange = detailDocument?.clip?.pitch_range;
      if (detailRange && (Number(diff.pitch_range_before?.minimum) !== Number(detailRange.minimum) || Number(diff.pitch_range_before?.maximum) !== Number(detailRange.maximum))) return false;
      if (diff.pitch_range_after.minimum < diff.pitch_range_before.minimum || diff.pitch_range_after.maximum > diff.pitch_range_before.maximum) return false;
      if (!finiteNumber(diff.duration_beats_before) || !finiteNumber(diff.duration_beats_after) || diff.duration_beats_before < 0 || diff.duration_beats_after !== diff.duration_beats_before) return false;
      if (!finiteNumber(diff.duration_seconds_before) || !finiteNumber(diff.duration_seconds_after) || diff.duration_seconds_before < 0 || diff.duration_seconds_after !== diff.duration_seconds_before) return false;
      if (diff.retained_normalized_notes_changed !== 0 || !exactObjectKeys(diff.unchanged, DELETE_UNCHANGED_KEYS)) return false;
      if (!DELETE_UNCHANGED_KEYS.every((key) => diff.unchanged[key] === true)) return false;
      return seen.size === requestsByRef.size;
    }

    function correctionDiffMatchesRequest(diff, request) {
      const kind = request?.correction?.kind;
      if (!correctionContract(kind)) return false;
      if (kind === CORRECTION_KIND_DELETE) return deletionDiffMatchesRequest(diff, request);
      const requested = list(request?.correction?.changes);
      const rows = list(diff?.changes);
      if (diff?.kind !== kind || diff?.changed_note_count !== requested.length || rows.length !== requested.length) return false;
      const requestsByRef = new Map(requested.map((change) => [correctionNoteRefKey(change.note_ref), change]));
      const notesByRef = new Map(correctionNotes().map((note) => [correctionNoteRefKey(note.note_ref), note]));
      const seen = new Set();
      for (const row of rows) {
        const key = correctionNoteRefKey(row?.note_ref);
        const change = requestsByRef.get(key);
        const note = notesByRef.get(key);
        if (!change || !note || !correctionNoteEditable(note) || seen.has(key)) return false;
        seen.add(key);
        if (kind === CORRECTION_KIND_VELOCITY) {
          if (
            Number(row.before_velocity) !== Number(correctionNoteVelocity(note))
            || Number(row.after_velocity) !== Number(change.target_velocity)
            || Number(row.velocity_delta) !== Number(change.target_velocity) - Number(correctionNoteVelocity(note))
            || Number(row.pitch) !== correctionNotePitch(note)
            || Number(row.channel) !== Number(detailDocument?.clip?.instrument?.channel)
            || Number(row.start_tick) !== Number(note.start_tick)
            || Number(row.end_tick) !== Number(note.end_tick)
            || Number(row.start_beat) !== correctionNoteStartBeat(note)
            || Number(row.duration_beats) !== correctionNoteDurationBeats(note)
          ) return false;
        } else if (
          Number(row.before_pitch) !== correctionNotePitch(note)
          || Number(row.after_pitch) !== Number(change.target_pitch)
          || Number(row.semitones) !== Number(change.target_pitch) - correctionNotePitch(note)
        ) return false;
      }
      return seen.size === requestsByRef.size;
    }

    function correctionProjectionMatchesRequest(projection, request) {
      const kind = request?.correction?.kind;
      const contract = correctionContract(kind);
      if (!contract) return false;
      if (kind === CORRECTION_KIND_DELETE && !exactObjectKeys(projection, [
        "child", "correction", "diff", "effects", "intent_sha256", "library", "operation",
        "parent", "projection_sha256", "schema", "status", "warnings", "window",
      ])) return false;
      const window = projection?.window || {};
      const parent = projection?.parent || {};
      const child = projection?.child || {};
      return projection?.schema === contract.previewSchema
        && projection?.status === "previewed"
        && projection?.operation === contract.previewOperation
        && isSha256(projection?.intent_sha256)
        && isSha256(projection?.projection_sha256)
        && stableJson(projection?.library) === stableJson({state_sha256: request.library_state_sha256})
        && window.start_tick === request.window.start_tick
        && window.end_tick === request.window.end_tick
        && window.ticks_per_beat === correctionTicksPerBeat()
        && (kind !== CORRECTION_KIND_DELETE || stableJson(window) === stableJson(correctionWindowDocument?.window))
        && stableJson(projection?.correction) === stableJson(request.correction)
        && parent.clip_id === request.parent_clip_id
        && parent.object_sha256 === request.parent_object_sha256
        && typeof parent.lineage_id === "string" && parent.lineage_id.length > 0
        && Number.isInteger(parent.revision) && parent.revision >= 1
        && child.clip_id === `sf-correction-${projection.intent_sha256}`
        && isSha256(child.object_sha256)
        && child.parent_clip_id === request.parent_clip_id
        && child.lineage_id === parent.lineage_id
        && child.revision === parent.revision + 1
        && correctionDiffMatchesRequest(projection?.diff, request)
        && (kind !== CORRECTION_KIND_DELETE || (
          deletionParentIdentityMatches(parent, request)
          && deletionChildIdentityMatches(parent, child, projection.diff, projection.intent_sha256, request)
        ))
        && Array.isArray(projection?.warnings)
        && correctionEffectsMatch(projection?.effects, request.correction.kind, false);
    }

    function correctionResultMatchesProjection(result, request, projection) {
      const kind = request?.correction?.kind;
      const contract = correctionContract(kind);
      if (!contract) return false;
      if (kind === CORRECTION_KIND_DELETE && !exactObjectKeys(result, [
        "child", "correction", "diff", "effects", "library", "operation", "parent",
        "projection_sha256", "replayed", "schema", "status", "warnings", "window",
      ])) return false;
      const replayed = result?.replayed === true && result?.status === "replayed";
      const created = result?.replayed === false && result?.status === "created";
      const library = result?.library || {};
      const libraryValid = isSha256(library.current_state_sha256)
        && library.expected_state_sha256 === request.library_state_sha256
        && (created
          ? library.previous_state_sha256 === request.library_state_sha256
            && library.current_state_sha256 !== request.library_state_sha256
          : replayed
            && library.previous_state_sha256 === library.current_state_sha256
        );
      return (created || replayed)
        && result?.schema === contract.resultSchema
        && result?.operation === contract.resultOperation
        && result?.projection_sha256 === projection?.projection_sha256
        && stableJson(result?.window) === stableJson(projection?.window)
        && stableJson(result?.correction) === stableJson(request.correction)
        && stableJson(result?.parent) === stableJson(projection?.parent)
        && stableJson(result?.child) === stableJson(projection?.child)
        && stableJson(result?.diff) === stableJson(projection?.diff)
        && stableJson(result?.warnings) === stableJson(projection?.warnings)
        && libraryValid
        && correctionEffectsMatch(result?.effects, kind, created);
    }

    async function reviewCorrection() {
      if (!correctionEnabled() || !correctionActionAllowed("preview") || correctionPending || !currentClipId) return;
      correctionErrorMessage = "";
      correctionStatusMessage = "";
      correctionResult = null;
      let request;
      try {
        request = correctionRequest();
      } catch (error) {
        correctionErrorMessage = error?.message || String(error);
        render();
        focusCorrectionStatus();
        return;
      }
      const sourceClipId = currentClipId;
      const sequence = ++correctionRequestSequence;
      correctionPending = "projection";
      render();
      focusCorrectionStatus();
      try {
        const value = await api("/api/clip-note-correction-projection", { method: "POST", body: JSON.stringify(request) });
        if (sequence !== correctionRequestSequence || mode !== "detail" || currentClipId !== sourceClipId) return;
        const projection = value?.projection || value;
        const changeName = correctionChangeName(request.correction.kind);
        if (!correctionProjectionMatchesRequest(projection, request)) throw new Error(`The local server returned an invalid or mismatched zero-effect ${changeName} review.`);
        correctionProjection = projection;
        correctionProjectionCorrection = cloneJson(request.correction);
        correctionStatusMessage = `Exact ${changeName} diff reviewed. No Clip or project state changed; create only if every listed note is intended.`;
      } catch (error) {
        if (sequence !== correctionRequestSequence) return;
        if (Number(error?.status) === 409) {
          correctionPending = "";
          await reloadCorrectionAfterConflict("The Clip or note window changed while reviewing. Detail and the exact window were reloaded once; review the retained valid draft again.");
          return;
        }
        correctionErrorMessage = error?.message || String(error);
      } finally {
        if (sequence === correctionRequestSequence) correctionPending = "";
        render();
        if (correctionErrorMessage) focusCorrectionStatus();
        else if (correctionProjection) host?.querySelector("#clip-correction-projection")?.focus();
      }
    }

    async function createCorrectionVersion() {
      if (!correctionEnabled() || !correctionActionAllowed("create") || correctionPending || !currentClipId || !correctionProjection) return;
      correctionErrorMessage = "";
      correctionStatusMessage = "";
      let request;
      try {
        request = correctionRequest();
        const correctionName = correctionChangeName(request.correction.kind);
        if (!isSha256(correctionProjection.projection_sha256)) throw new Error(`Review this ${correctionName} draft again before creating a version.`);
        if (stableJson(request.correction) !== stableJson(correctionProjectionCorrection)) throw new Error(`The ${correctionName} draft changed; review it again before creating a version.`);
      } catch (error) {
        correctionErrorMessage = error?.message || String(error);
        render();
        focusCorrectionStatus();
        return;
      }
      const createRequest = { action: "create", ...request, projection_sha256: correctionProjection.projection_sha256 };
      const sourceClipId = currentClipId;
      const sequence = ++correctionRequestSequence;
      correctionPending = "create";
      render();
      focusCorrectionStatus();
      try {
        const value = await api("/api/clip-note-correction-action", { method: "POST", body: JSON.stringify(createRequest) });
        if (sequence !== correctionRequestSequence || mode !== "detail" || currentClipId !== sourceClipId) return;
        const result = value?.result || value;
        const correctionName = correctionContract(request.correction.kind)?.resultName || "unknown-correction";
        if (!correctionResultMatchesProjection(result, request, correctionProjection)) throw new Error(`The local server returned an invalid or mismatched immutable ${correctionName} result.`);
        correctionResult = value;
        correctionProjection = null;
        correctionProjectionCorrection = null;
        const replayed = result.replayed === true || result.status === "replayed";
        correctionStatusMessage = replayed
          ? `The exact ${correctionName} child already existed; this explicit retry appended nothing. Inspect it only if wanted.`
          : `One immutable ${correctionName} child was created. Nothing was selected, placed, auditioned or added to a pack.`;
        listDocument = null;
        const knownCount = Number(observedLibraryCount ?? capability?.library?.clip_count);
        if (Number.isInteger(knownCount) && knownCount >= 0) {
          observedLibraryCount = knownCount + (replayed ? 0 : 1);
          libraryEvidenceStale = false;
        } else {
          observedLibraryCount = null;
          libraryEvidenceStale = true;
        }
      } catch (error) {
        if (sequence !== correctionRequestSequence) return;
        if (Number(error?.status) === 409) {
          correctionPending = "";
          await reloadCorrectionAfterConflict("The Clip library changed, or this creation may already have completed. Detail and the exact window were reloaded once. No write retry was made; inspect the lineage and review the retained valid draft again.");
          return;
        }
        correctionErrorMessage = error?.message || String(error);
      } finally {
        if (sequence === correctionRequestSequence) correctionPending = "";
        render();
        if (correctionErrorMessage) focusCorrectionStatus();
        else if (correctionResult) host?.querySelector("#clip-correction-result")?.focus();
      }
    }

    async function reloadCorrectionAfterConflict(message) {
      const draft = correctionDraft(currentClipId);
      const savedChanges = new Map(draft.changes);
      const savedSelection = draft.selectedRefKey;
      correctionProjection = null;
      correctionProjectionCorrection = null;
      correctionResult = null;
      correctionWindowDocument = null;
      correctionWindowContract = null;
      correctionPending = "";
      correctionStatusMessage = "";
      correctionErrorMessage = "";
      await loadDetail(currentClipId);
      if (!detailDocument?.clip || errorMessage) {
        correctionErrorMessage = `${message} The latest Clip detail could not be loaded.`;
        return;
      }
      draft.changes = savedChanges;
      draft.selectedRefKey = savedSelection;
      await loadCorrectionWindow({ preserveDraft: true, afterConflict: true });
      if (!correctionErrorMessage) correctionErrorMessage = message;
      render();
      focusCorrectionStatus();
    }

    function focusCorrectionStatus() {
      host?.querySelector("#clip-correction-status")?.focus();
    }

    function correctionResultChild() {
      const document = correctionResult?.result || correctionResult || {};
      return document.child || document.clip || document.version || null;
    }

    function correctionProjectionKind(projection) {
      const kind = projection?.diff?.kind || projection?.correction?.kind || correctionProjectionCorrection?.kind;
      return correctionContract(kind) ? kind : null;
    }

    function correctionResultKind(document) {
      const kind = document?.correction?.kind || document?.diff?.kind;
      return correctionContract(kind) ? kind : null;
    }

    function velocityDeltaDirectionLabel(before, after) {
      const delta = Number(after) - Number(before);
      if (!Number.isFinite(delta)) return "unknown";
      const signed = delta < 0 ? `−${Math.abs(delta)}` : delta > 0 ? `+${delta}` : "0";
      return `${signed} · ${delta < 0 ? "lower" : delta > 0 ? "higher" : "unchanged"}`;
    }

    function velocityChangeLabel(before, after) {
      if (!Number.isInteger(before) || !Number.isInteger(after)) return "unknown → unknown";
      return `${before} → ${after} (${velocityDeltaDirectionLabel(before, after)})`;
    }

    function correctionDiffRows(projection, kind = correctionProjectionKind(projection)) {
      const candidates = list(projection?.diff?.changes || projection?.diff?.edits || projection?.changes);
      if (kind === CORRECTION_KIND_DELETE) {
        return candidates.map((row) => ({
          note_ref: row.note_ref,
          channel: Number(row.channel),
          pitch: Number(row.pitch),
          velocity: Number(row.velocity),
          release_velocity: Number(row.release_velocity),
          start_tick: Number(row.start_tick),
          end_tick: Number(row.end_tick),
          start_beat: Number(row.start_beat),
          duration_beats: Number(row.duration_beats),
          source_start_seconds: Number(row.source_start_seconds),
          source_end_seconds: Number(row.source_end_seconds),
          articulation: row.articulation,
        })).filter((row) => isSha256(row.note_ref) && Number.isInteger(row.pitch));
      }
      if (kind === CORRECTION_KIND_VELOCITY) {
        return candidates.map((row) => ({
          note_ref: row.note_ref ?? row.ref ?? "note",
          pitch: Number(row.pitch ?? row.before?.pitch),
          start_beat: Number(row.start_beat ?? row.before?.start_beat),
          before_velocity: Number(row.before_velocity ?? row.before?.velocity ?? row.velocity_before),
          after_velocity: Number(row.after_velocity ?? row.target_velocity ?? row.after?.velocity ?? row.velocity_after),
        })).filter((row) => Number.isInteger(row.before_velocity) && Number.isInteger(row.after_velocity));
      }
      if (kind === CORRECTION_KIND_PITCH) return candidates.map((row) => ({
        note_ref: row.note_ref ?? row.ref ?? "note",
        before_pitch: Number(row.before?.pitch ?? row.before_pitch ?? row.pitch_before),
        after_pitch: Number(row.after?.pitch ?? row.after_pitch ?? row.target_pitch ?? row.pitch_after),
      })).filter((row) => Number.isInteger(row.before_pitch) && Number.isInteger(row.after_pitch));
      return [];
    }

    function transformDraft(clipId) {
      const existing = transformDrafts.get(clipId);
      if (existing) return existing;
      const draft = { operation: "", targetKey: "", direction: "", targetBpm: "", timingMode: "" };
      transformDrafts.set(clipId, draft);
      return draft;
    }

    function browseFiltersAreEmpty() {
      return !filters.text && !filters.role && !filters.key && !filters.bpm && !filters.tags;
    }

    function setTransformDraftValue(name, value, rerender = false, focusId = "") {
      if (!currentClipId || transformPending) return;
      const draft = transformDraft(currentClipId);
      if (draft[name] === value) return;
      const hadReviewedState = !!transformProjection || !!transformResult;
      draft[name] = value;
      invalidateTransformProjection("Draft changed. Review it again before creating a version.");
      if (rerender || hadReviewedState) {
        pendingTransformFocusId = focusId;
        render();
      }
    }

    function updateTransformDraftFromInputs() {
      if (!currentClipId || !host) return;
      const draft = transformDraft(currentClipId);
      const keyInput = host.querySelector("#clip-transform-target-key");
      const bpmInput = host.querySelector("#clip-transform-target-bpm");
      if (keyInput) draft.targetKey = String(keyInput.value || "").trim();
      if (bpmInput) draft.targetBpm = String(bpmInput.value || "").trim();
    }

    function invalidateTransformProjection(message = "") {
      transformRequestSequence += 1;
      transformProjection = null;
      transformProjectionTransform = null;
      transformResult = null;
      transformErrorMessage = "";
      transformStatusMessage = message;
      stopAudio();
    }

    function validatedTransform() {
      const clip = detailDocument?.clip;
      if (!clip || !currentClipId) throw new Error("Open an exact Clip before reviewing a transform.");
      const draft = transformDraft(currentClipId);
      if (draft.operation === "key") {
        if (!transformOperationAllowed("key")) throw new Error("Key transformation is unavailable for this Clip.");
        const sourceMode = keyMode(clip.key);
        if (!sourceMode) throw new Error("A same-mode key transformation requires a known source key.");
        const target = sameModeKey(draft.targetKey, sourceMode);
        if (!target) throw new Error(`Choose a target ${sourceMode} key.`);
        if (normalizeKey(target) === normalizeKey(clip.key)) throw new Error("Choose a target key different from the source key.");
        if (!["nearest", "up", "down"].includes(draft.direction)) throw new Error("Choose smallest shift, upward or downward register direction.");
        return { kind: "key", target_key: target, direction: draft.direction };
      }
      if (draft.operation === "bpm") {
        if (!transformOperationAllowed("bpm")) throw new Error("BPM transformation is unavailable for this Clip.");
        const target = Number(draft.targetBpm);
        const bounds = transformBpmBounds(clip);
        if (!Number.isFinite(target) || target < bounds.minimum || target > bounds.maximum) {
          throw new Error(`For this ${numberLabel(clip.bpm)} BPM Clip, target BPM must be from ${numberLabel(bounds.minimum)} to ${numberLabel(bounds.maximum)} (${numberLabel(bounds.minimumRatio)}×–${numberLabel(bounds.maximumRatio)}× within the global ${numberLabel(bounds.globalMinimum)}–${numberLabel(bounds.globalMaximum)} BPM boundary).`);
        }
        if (Math.abs(target - Number(clip.bpm)) < 1e-9) throw new Error("Choose a target BPM different from the source BPM.");
        if (!["musical", "stem_locked"].includes(draft.timingMode)) throw new Error("Choose musical or stem-locked timing behaviour.");
        return { kind: "bpm", target_bpm: target, timing_mode: draft.timingMode };
      }
      throw new Error("Choose key or BPM as the one transform for this version.");
    }

    function transformPins(transform) {
      const clip = detailDocument?.clip || {};
      const libraryState = detailDocument?.library_state_sha256 || capability?.library?.state_sha256;
      if (!clip.clip_id || !isSha256(clip.object_sha256) || !isSha256(libraryState)) {
        throw new Error("The exact Clip and library pins are unavailable; reload the Clip detail.");
      }
      return {
        parent_clip_id: clip.clip_id,
        parent_object_sha256: clip.object_sha256,
        library_state_sha256: libraryState,
        transform,
      };
    }

    async function reviewTransform() {
      if (!transformEnabled() || !transformActionAllowed("preview") || transformPending || !currentClipId) return;
      transformErrorMessage = "";
      transformStatusMessage = "";
      transformResult = null;
      let transform;
      let request;
      try {
        transform = validatedTransform();
        request = transformPins(transform);
      } catch (error) {
        transformErrorMessage = error?.message || String(error);
        render();
        focusTransformStatus();
        return;
      }
      const sourceClipId = currentClipId;
      const sequence = ++transformRequestSequence;
      transformPending = "projection";
      render();
      focusTransformStatus();
      try {
        const value = await api("/api/clip-transform-projection", { method: "POST", body: JSON.stringify(request) });
        if (sequence !== transformRequestSequence || mode !== "detail" || currentClipId !== sourceClipId) return;
        const projection = value?.projection || value;
        if (!isSha256(projection?.projection_sha256) || !allEffectsFalse(projection?.effects)) {
          throw new Error("The local server returned an invalid temporary transform review.");
        }
        transformProjection = projection;
        transformProjectionTransform = transform;
        transformStatusMessage = "Temporary transform reviewed. No Clip or project state changed; create only if this exact diff is intended.";
      } catch (error) {
        if (sequence !== transformRequestSequence) return;
        if (Number(error?.status) === 409) {
          await reloadTransformAfterConflict("The Clip library changed while reviewing. The latest source lineage was reloaded; review this retained draft again.");
        } else {
          transformErrorMessage = error?.message || String(error);
        }
      } finally {
        if (sequence === transformRequestSequence) transformPending = "";
        render();
        if (transformErrorMessage) focusTransformStatus();
        else if (transformProjection) host?.querySelector("#clip-transform-projection")?.focus();
      }
    }

    async function createTransformVersion() {
      if (!transformEnabled() || !transformActionAllowed("create") || transformPending || !currentClipId || !transformProjection) return;
      transformErrorMessage = "";
      transformStatusMessage = "";
      let transform;
      let pins;
      try {
        transform = validatedTransform();
        pins = transformPins(transform);
        if (!isSha256(transformProjection.projection_sha256)) throw new Error("Review this draft again before creating a version.");
        if (JSON.stringify(transform) !== JSON.stringify(transformProjectionTransform)) throw new Error("The draft changed; review it again before creating a version.");
      } catch (error) {
        transformErrorMessage = error?.message || String(error);
        render();
        focusTransformStatus();
        return;
      }
      const request = { action: "create", ...pins, projection_sha256: transformProjection.projection_sha256 };
      const sourceClipId = currentClipId;
      const sequence = ++transformRequestSequence;
      transformPending = "create";
      render();
      focusTransformStatus();
      try {
        const value = await api("/api/clip-transform-action", { method: "POST", body: JSON.stringify(request) });
        if (sequence !== transformRequestSequence || mode !== "detail" || currentClipId !== sourceClipId) return;
        const result = value?.result || value;
        if (!result?.child?.clip_id || !isSha256(result.child.object_sha256)) throw new Error("The local server returned no created immutable child.");
        transformResult = value;
        transformProjection = null;
        transformProjectionTransform = null;
        const replayed = result.replayed === true || result.status === "replayed";
        transformStatusMessage = replayed
          ? "The exact immutable child already existed; this explicit retry appended nothing. Nothing was selected, placed or added to a pack."
          : "One immutable child version was created. Nothing was selected, placed or added to a pack.";
        listDocument = null;
        const knownCount = Number(observedLibraryCount ?? capability?.library?.clip_count);
        if (Number.isInteger(knownCount) && knownCount >= 0) {
          observedLibraryCount = knownCount + (replayed ? 0 : 1);
          libraryEvidenceStale = false;
        } else {
          observedLibraryCount = null;
          libraryEvidenceStale = true;
        }
      } catch (error) {
        if (sequence !== transformRequestSequence) return;
        if (Number(error?.status) === 409) {
          await reloadTransformAfterConflict("The Clip library changed, or this creation may already have completed. No automatic retry was made. The latest lineage was reloaded; inspect it and review this retained draft again.");
        } else {
          transformErrorMessage = error?.message || String(error);
        }
      } finally {
        if (sequence === transformRequestSequence) transformPending = "";
        render();
        if (transformErrorMessage) focusTransformStatus();
        else if (transformResult) host?.querySelector("#clip-transform-result")?.focus();
      }
    }

    async function reloadTransformAfterConflict(message) {
      transformProjection = null;
      transformProjectionTransform = null;
      transformResult = null;
      transformPending = "";
      transformStatusMessage = "";
      await loadDetail(currentClipId);
      transformErrorMessage = message;
    }

    function focusTransformStatus() {
      host?.querySelector("#clip-transform-status")?.focus();
    }

    function transformResultChild() {
      const document = transformResult?.result || transformResult || {};
      return document.child || document.clip || document.version || null;
    }

    function transformOperationAllowed(name) {
      const transforms = transformCapability?.transforms;
      if (!transformActionAllowed("preview")) return false;
      if (name === "key" && transforms?.same_mode_key) return transforms.same_mode_key.enabled === true;
      if (name === "bpm" && transforms?.bpm) return transforms.bpm.enabled === true;
      return false;
    }

    function transformActionAllowed(name) {
      const action = transformCapability?.actions?.[name];
      return action !== false;
    }

    function transformBpmBounds(clip) {
      const globalMinimum = positiveFinite(transformCapability?.limits?.minimum_bpm) || 20;
      const globalMaximum = positiveFinite(transformCapability?.limits?.maximum_bpm) || 400;
      const minimumRatio = positiveFinite(transformCapability?.limits?.minimum_bpm_ratio) || 0.25;
      const maximumRatio = positiveFinite(transformCapability?.limits?.maximum_bpm_ratio) || 4;
      const sourceBpm = positiveFinite(clip?.bpm) || globalMinimum;
      return {
        globalMinimum,
        globalMaximum,
        minimumRatio,
        maximumRatio,
        minimum: Math.max(globalMinimum, sourceBpm * minimumRatio),
        maximum: Math.min(globalMaximum, sourceBpm * maximumRatio),
      };
    }

    function transformProjectionOperation(projection) {
      const transform = projection?.transform || transformProjectionTransform || {};
      if (transform.kind === "key") return `Key change to ${transform.target_key || "target key"} (${statusLabel(transform.direction)})`;
      if (transform.kind === "bpm") return `BPM change to ${numberLabel(transform.target_bpm)} (${statusLabel(transform.timing_mode)})`;
      return "One reviewed Clip transform";
    }

    function keyMode(value) {
      const match = String(value || "").trim().match(/\s+(major|minor)$/i);
      return match ? match[1].toLowerCase() : "";
    }

    function sameModeKey(value, mode) {
      if (!mode) return "";
      const text = String(value || "").trim();
      const match = text.match(/^([A-Ga-g](?:#|b)?)\s+(major|minor)$/i);
      if (!match || match[2].toLowerCase() !== mode) return "";
      const tonic = `${match[1][0].toUpperCase()}${match[1].slice(1)}`;
      if (!KEY_TONICS.includes(tonic)) return "";
      return `${tonic} ${mode}`;
    }

    function normalizeKey(value) {
      return String(value || "").trim().toLowerCase().replace(/\s+/g, " ");
    }

    function isDrumFamilyClip(clip) {
      if (clip?.instrument?.is_drums === true) return true;
      const role = String(clip?.role || clip?.instrument?.role || "")
        .trim()
        .toLowerCase()
        .replaceAll("-", "_")
        .replaceAll(" ", "_");
      return ["kick", "snare", "hat", "hats", "cymbal", "cymbals", "tom", "toms", "other_kit", "drum", "drums", "percussion"].includes(role);
    }

    function positiveFinite(value) {
      const number = Number(value);
      return Number.isFinite(number) && number > 0 ? number : null;
    }

    function allEffectsFalse(value) {
      if (!value || typeof value !== "object" || Array.isArray(value)) return false;
      const effects = Object.values(value);
      return effects.length > 0 && effects.every((effect) => effect === false);
    }

    function isSha256(value) {
      return /^[0-9a-f]{64}$/.test(String(value || ""));
    }

    function rangeLabel(value) {
      if (!value || typeof value !== "object") return "unknown";
      const minimum = value.minimum_name ?? value.minimum;
      const maximum = value.maximum_name ?? value.maximum;
      return minimum == null || maximum == null ? "unknown" : `${minimum}–${maximum}`;
    }

    function placementDraft(clipId) {
      const existing = placementDrafts.get(clipId);
      if (existing) return existing;
      const draft = { bar: 1, beat: 1 };
      placementDrafts.set(clipId, draft);
      return draft;
    }

    function updatePlacementDraft() {
      if (!currentClipId || !host) return;
      const bar = Number(host.querySelector("#clip-start-bar")?.value);
      const beat = Number(host.querySelector("#clip-start-beat")?.value);
      placementDrafts.set(currentClipId, { bar, beat });
    }

    function validatedPlacementTarget() {
      const grid = detailDocument?.reuse_compatibility?.target_grid || reuseCapability?.target_grid || {};
      const beatsPerBar = positiveInteger(grid.beats_per_bar, 4);
      const draft = placementDraft(currentClipId);
      if (!Number.isInteger(draft.bar) || draft.bar < 1) throw new Error("Start bar must be a whole number of 1 or greater.");
      if (!Number.isInteger(draft.beat) || draft.beat < 1 || draft.beat > beatsPerBar) throw new Error(`Start beat must be a whole number from 1 to ${beatsPerBar}.`);
      return { bar: draft.bar, beat: draft.beat, tick_in_beat: 0 };
    }

    function actionAllowed(name) {
      const actions = reuseCapability?.actions;
      if (Array.isArray(actions)) return actions.includes(name);
      return !!actions && actions[name] === true;
    }

    async function placeCurrentClip() {
      const clip = detailDocument?.clip;
      const compatibility = detailDocument?.reuse_compatibility;
      if (!reuseEnabled() || !clip || !planDocument || planErrorMessage || actionPending) return;
      actionErrorMessage = "";
      let target;
      try {
        target = validatedPlacementTarget();
      } catch (error) {
        actionErrorMessage = error?.message || String(error);
        render();
        return;
      }
      if (compatibility?.placement_ready !== true || compatibility?.transform_applied !== false || !actionAllowed("place")) {
        actionErrorMessage = "This unchanged Clip is not ready for the proposal under the verified capability.";
        render();
        return;
      }
      const request = {
        action: "place",
        plan_id: planDocument.plan_id,
        plan_sha256: planDocument.plan_sha256,
        expected_revision: planDocument.revision,
        clip_id: clip.clip_id,
        clip_object_sha256: clip.object_sha256,
        target,
      };
      actionPending = true;
      render();
      try {
        const value = await api("/api/clip-reuse-action", { method: "POST", body: JSON.stringify(request) });
        const nextPlan = value?.plan;
        if (!nextPlan) throw new Error("The local server returned no reuse proposal.");
        planDocument = nextPlan;
        planStatusMessage = "Unchanged Clip placement saved in the separate proposal. The current arrangement and GarageBand Pack were not changed.";
        actionErrorMessage = "";
        mode = "plan";
        detailDocument = null;
        currentClipId = null;
      } catch (error) {
        if (Number(error?.status) === 409) {
          await reloadAfterConflict("The proposal changed in another action, or an earlier save may already have completed. The latest proposal was reloaded; inspect it before explicitly trying again.");
        } else {
          actionErrorMessage = error?.message || String(error);
        }
      } finally {
        actionPending = false;
        render();
      }
    }

    async function removePlacement(placementId) {
      if (!reuseEnabled() || !planDocument || planErrorMessage || actionPending || !actionAllowed("remove")) return;
      const request = {
        action: "remove",
        plan_id: planDocument.plan_id,
        plan_sha256: planDocument.plan_sha256,
        expected_revision: planDocument.revision,
        placement_id: placementId,
      };
      actionPending = true;
      actionErrorMessage = "";
      render();
      try {
        const value = await api("/api/clip-reuse-action", { method: "POST", body: JSON.stringify(request) });
        const nextPlan = value?.plan;
        if (!nextPlan) throw new Error("The local server returned no reuse proposal.");
        planDocument = nextPlan;
        planStatusMessage = "Placement removed from the active proposal. Its append-only local history and immutable source Clip remain intact.";
      } catch (error) {
        if (Number(error?.status) === 409) {
          await reloadAfterConflict("The proposal changed in another action, or this removal may already have completed. The latest proposal was reloaded; inspect it before explicitly trying again.");
        } else {
          actionErrorMessage = error?.message || String(error);
        }
      } finally {
        actionPending = false;
        render();
      }
    }

    async function reloadAfterConflict(message) {
      actionPending = false;
      await loadPlan({ afterConflict: true });
      actionErrorMessage = planErrorMessage
        ? `${message} The latest proposal could not be restored, so further changes are disabled.`
        : message;
      planStatusMessage = "";
    }

    return { setCapability, enabled, renderInto, stopAudio, reset };
  }

  function fallbackEscape(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));
  }

  function shortHash(value) {
    const text = String(value || "");
    return text.length > 16 ? `${text.slice(0, 16)}…` : text || "not recorded";
  }

  function numberLabel(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(3).replace(/\.000$/, "").replace(/(\.\d*?)0+$/, "$1") : "unknown";
  }

  function numberInputLabel(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "";
    return number.toFixed(9).replace(/\.0+$/, "").replace(/(\.\d*?)0+$/, "$1");
  }

  function signedNumberLabel(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "unknown";
    const label = numberLabel(number);
    return number > 0 ? `+${label}` : label;
  }

  function yesNo(value) {
    if (value === true) return "yes";
    if (value === false) return "no";
    return "unknown";
  }

  function list(value) {
    return Array.isArray(value) ? value : [];
  }

  function positiveInteger(value, fallback) {
    const number = Number(value);
    return Number.isInteger(number) && number > 0 ? number : fallback;
  }

  function statusLabel(value) {
    const text = String(value ?? "unknown").trim();
    return text ? text.replaceAll("_", " ").replaceAll("-", " ") : "unknown";
  }

  function cloneJson(value) {
    if (value === undefined) return undefined;
    return JSON.parse(JSON.stringify(value));
  }

  function stableJson(value) {
    function normalize(item) {
      if (Array.isArray(item)) return item.map(normalize);
      if (!item || typeof item !== "object") return item;
      return Object.fromEntries(Object.keys(item).sort().map((key) => [key, normalize(item[key])]));
    }
    return JSON.stringify(normalize(value));
  }

  function midiPitchName(value) {
    const pitch = Number(value);
    if (!Number.isInteger(pitch) || pitch < 0 || pitch > 127) return "unknown";
    const names = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];
    return `${names[pitch % 12]}${Math.floor(pitch / 12) - 1}`;
  }

  return { createClipLibrary };
});
