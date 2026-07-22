(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.SunofriendWorkbenchClips = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const DEFAULT_LIMIT = 24;

  function createClipLibrary({ api, escapeHtml }) {
    if (typeof api !== "function") throw new Error("Clip Library requires the Workbench API");
    const esc = typeof escapeHtml === "function" ? escapeHtml : fallbackEscape;
    let capability = null;
    let reuseCapability = null;
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
    let requestSequence = 0;
    let planRequestSequence = 0;
    const artifacts = new Map();
    const placementDrafts = new Map();
    const filters = { text: "", role: "", key: "", bpm: "", tags: "", offset: 0 };

    function setCapability(value, optionalReuseCapability = null) {
      capability = value && value.enabled === true ? value : null;
      const wasReuseEnabled = reuseEnabled();
      reuseCapability = optionalReuseCapability && optionalReuseCapability.enabled === true
        ? optionalReuseCapability
        : null;
      if (!capability) reset();
      if (wasReuseEnabled !== reuseEnabled()) resetReuseState();
    }

    function enabled() {
      return capability !== null;
    }

    function reuseEnabled() {
      return capability !== null && reuseCapability !== null;
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
      resetReuseState();
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
    }

    function gateHtml() {
      const acceptance = capability?.acceptance || {};
      const count = Number(capability?.library?.clip_count || 0);
      const boundary = reuseEnabled()
        ? "no transform, edit, tag change, hybrid, current-project selection or library write is available here"
        : "no transform, edit, tag change, hybrid, selection or library write is available here";
      return `<section class="identity"><p><b>Phase 6 read-only Clip Library</b></p><p>The exact Phase 5.9 GarageBand and usability review passed before this view was enabled. This slice can browse verified Clip v1 objects, render a neutral listening proxy and download a deterministic MIDI reconstruction.</p><p class="muted">${esc(count)} immutable clip${count === 1 ? "" : "s"} · accepted pack ${esc(shortHash(acceptance.pack_sha256))} · ${boundary}.</p></section>`;
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
      return `<section aria-labelledby="clip-detail-heading"><button id="clip-back" type="button">${backLabel}</button><h2 id="clip-detail-heading">${esc(clip.title)}</h2>${clipHeaderHtml()}${statusHtml()}<div class="clip-detail-grid"><section class="panel"><h3>Musical content</h3><dl class="clip-facts"><dt>Role</dt><dd>${esc(clip.role)}</dd><dt>Key</dt><dd>${esc(clip.key || "unknown")}</dd><dt>Tempo</dt><dd>${esc(numberLabel(clip.bpm))} BPM</dd><dt>Timing contract</dt><dd>${esc(timing.resolved_mode || "musical")}</dd><dt>GarageBand tempo</dt><dd>${esc(numberLabel(timing.export_bpm || clip.bpm))} BPM</dd><dt>Notes / chords</dt><dd>${esc(clip.note_count)} / ${esc(clip.chord_count)}</dd><dt>Pitch range</dt><dd>${range}</dd><dt>Duration</dt><dd>${esc(numberLabel(duration.export_seconds))} seconds</dd><dt>Program / channel</dt><dd>${esc(instrument.program)} / ${esc(Number(instrument.channel) + 1)}</dd></dl></section><section class="panel"><h3>Immutable identity</h3><p>Revision ${esc(clip.revision)} · ${esc(lineage.length)} version${lineage.length === 1 ? "" : "s"} in this lineage.</p><p class="muted">Clip ID ${esc(clip.clip_id)}<br>Object SHA-256 ${esc(clip.object_sha256)}</p><p>The source pathname and private provenance are deliberately absent from this browser projection.</p></section></div><section class="controls"><h3>Listen and export</h3><p>The MIDI download is a deterministic reconstruction of this immutable Clip v1 document. It is not claimed to be a byte-for-byte copy of an earlier source MIDI. A neutral preview, when requested, renders that exact reconstructed MIDI through the pinned dry local SoundFont.</p><p class="muted">Listening and downloading do not record a preference or add this Clip to the reuse proposal.</p><div class="actions"><button id="clip-midi" class="primary" type="button">Prepare MIDI download</button><button id="clip-preview" type="button">Prepare neutral audition</button></div><div id="clip-artifact">${artifactHtml(artifact)}</div></section>${reusePlacementHtml(clip)}<section class="panel"><h3>Version lineage</h3>${lineage.length ? `<ol class="clip-lineage">${lineage.map((item) => `<li><button type="button" data-lineage-clip="${esc(item.clip_id)}" ${item.clip_id === clip.clip_id ? "disabled" : ""}>Revision ${esc(item.revision)} · ${esc(item.title)} · ${esc(numberLabel(item.bpm))} BPM${item.clip_id === clip.clip_id ? " (current)" : ""}</button></li>`).join("")}</ol>` : "<p>No lineage records were found.</p>"}</section></section>`;
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
      if (back) back.onclick = () => { stopAudio(); mode = detailReturnMode; errorMessage = ""; statusMessage = ""; actionErrorMessage = ""; render(); };
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
