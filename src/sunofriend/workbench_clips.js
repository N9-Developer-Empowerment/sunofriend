(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.SunofriendWorkbenchClips = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const DEFAULT_LIMIT = 24;
  const KEY_TONICS = Object.freeze(["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]);

  function createClipLibrary({ api, escapeHtml }) {
    if (typeof api !== "function") throw new Error("Clip Library requires the Workbench API");
    const esc = typeof escapeHtml === "function" ? escapeHtml : fallbackEscape;
    let capability = null;
    let reuseCapability = null;
    let transformCapability = null;
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
    let observedLibraryCount = null;
    let libraryEvidenceStale = false;
    let requestSequence = 0;
    let planRequestSequence = 0;
    let transformRequestSequence = 0;
    const artifacts = new Map();
    const placementDrafts = new Map();
    const transformDrafts = new Map();
    const filters = { text: "", role: "", key: "", bpm: "", tags: "", offset: 0 };

    function setCapability(value, optionalReuseCapability = null, optionalTransformCapability = null) {
      const wasReuseEnabled = reuseEnabled();
      const wasTransformEnabled = transformEnabled();
      capability = value && value.enabled === true ? value : null;
      reuseCapability = optionalReuseCapability && optionalReuseCapability.enabled === true
        ? optionalReuseCapability
        : null;
      transformCapability = optionalTransformCapability && optionalTransformCapability.enabled === true
        ? optionalTransformCapability
        : null;
      if (!capability) reset();
      if (wasReuseEnabled !== reuseEnabled()) resetReuseState();
      if (wasTransformEnabled !== transformEnabled()) resetTransformState(true);
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
    }

    function gateHtml() {
      const acceptance = capability?.acceptance || {};
      const count = Number(observedLibraryCount ?? capability?.library?.clip_count ?? 0);
      const countText = libraryEvidenceStale
        ? browseFiltersAreEmpty()
          ? "library changed · exact count refreshes when Browse Clips reloads"
          : "library changed · clear filters to refresh the exact library count"
        : `${esc(count)} immutable clip${count === 1 ? "" : "s"}`;
      if (transformEnabled()) {
        return `<section class="identity"><p><b>Phase 6 Clip Library with explicit version creation</b></p><p>Existing Clip objects remain immutable. After reviewing one temporary key or BPM change, you may explicitly create one new child version from the exact Clip you opened.</p><p class="muted">${countText} · accepted pack ${esc(shortHash(acceptance.pack_sha256))} · no automatic transform, preference, selection, placement, current-arrangement change or GarageBand Pack change.</p></section>`;
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
      return `<section aria-labelledby="clip-detail-heading"><button id="clip-back" type="button">${backLabel}</button><h2 id="clip-detail-heading">${esc(clip.title)}</h2>${clipHeaderHtml()}${statusHtml()}<div class="clip-detail-grid"><section class="panel"><h3>Musical content</h3><dl class="clip-facts"><dt>Role</dt><dd>${esc(clip.role)}</dd><dt>Key</dt><dd>${esc(clip.key || "unknown")}</dd><dt>Tempo</dt><dd>${esc(numberLabel(clip.bpm))} BPM</dd><dt>Timing contract</dt><dd>${esc(timing.resolved_mode || "musical")}</dd><dt>GarageBand tempo</dt><dd>${esc(numberLabel(timing.export_bpm || clip.bpm))} BPM</dd><dt>Notes / chords</dt><dd>${esc(clip.note_count)} / ${esc(clip.chord_count)}</dd><dt>Pitch range</dt><dd>${range}</dd><dt>Duration</dt><dd>${esc(numberLabel(duration.export_seconds))} seconds</dd><dt>Program / channel</dt><dd>${esc(instrument.program)} / ${esc(Number(instrument.channel) + 1)}</dd></dl></section><section class="panel"><h3>Immutable identity</h3><p>Revision ${esc(clip.revision)} · ${esc(lineage.length)} version${lineage.length === 1 ? "" : "s"} in this lineage.</p><p class="muted">Clip ID ${esc(clip.clip_id)}<br>Object SHA-256 ${esc(clip.object_sha256)}</p><p>The source pathname and private provenance are deliberately absent from this browser projection.</p></section></div><section class="controls"><h3>Listen and export</h3><p>The MIDI download is a deterministic reconstruction of this immutable Clip v1 document. It is not claimed to be a byte-for-byte copy of an earlier source MIDI. A neutral preview, when requested, renders that exact reconstructed MIDI through the pinned dry local SoundFont.</p><p class="muted">Listening and downloading do not record a preference or add this Clip to the reuse proposal.</p><div class="actions"><button id="clip-midi" class="primary" type="button">Prepare MIDI download</button><button id="clip-preview" type="button">Prepare neutral audition</button></div><div id="clip-artifact">${artifactHtml(artifact)}</div></section>${transformHtml(clip)}${reusePlacementHtml(clip)}<section class="panel"><h3>Version lineage</h3><p class="muted">Versions are alternatives in one source lineage, not a ranking. “Viewing” identifies only the detail currently open.</p>${lineage.length ? `<ol class="clip-lineage">${lineage.map((item) => `<li><button type="button" data-lineage-clip="${esc(item.clip_id)}" ${item.clip_id === clip.clip_id ? "disabled" : ""}>Revision ${esc(item.revision)} · ${esc(item.title)} · ${esc(numberLabel(item.bpm))} BPM${item.clip_id === clip.clip_id ? " (viewing)" : ""}</button></li>`).join("")}</ol>` : "<p>No lineage records were found.</p>"}</section></section>`;
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

  return { createClipLibrary };
});
