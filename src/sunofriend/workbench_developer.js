(function (root, factory) {
  "use strict";

  const exported = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = exported;
  }
  if (root && typeof root === "object") {
    root.SunofriendWorkbenchDeveloper = exported;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const CLIENT_TRACE_LIMIT = 128;
  const CLIENT_TRACE_SCHEMA = "sunofriend.workbench-browser-operation.v1";

  // This is an intentionally static code map. Dynamic stack or frame inspection
  // could expose session tokens, private paths and listening notes. Stable symbols
  // also teach the production call path more clearly than an implementation stack.
  const ROUTES = Object.freeze({
    "/api/project": Object.freeze({
      operation: "project.load",
      label: "Load the path-free project projection",
      symbols: Object.freeze([
        "sunofriend.workbench_server._WorkbenchHandler.do_GET",
        "sunofriend.workbench_store.WorkbenchStore.current_state",
        "sunofriend.workbench_home.build_workbench_home",
        "sunofriend.workbench_catalog.public_catalog",
      ]),
      durableEffect: false,
    }),
    "/api/timeline": Object.freeze({
      operation: "timeline.stem",
      label: "Build bounded source and MIDI visual evidence",
      symbols: Object.freeze([
        "sunofriend.workbench_server._WorkbenchHandler.do_GET",
        "sunofriend.workbench_timeline.build_stem_timeline",
      ]),
      durableEffect: false,
    }),
    "/api/arrangement-timeline": Object.freeze({
      operation: "timeline.arrangement",
      label: "Derive the selected arrangement timeline",
      symbols: Object.freeze([
        "sunofriend.workbench_store.WorkbenchStore.current_state",
        "sunofriend.workbench_artifacts.selected_candidates",
        "sunofriend.workbench_timeline.build_arrangement_timeline",
      ]),
      durableEffect: false,
    }),
    "/api/events": Object.freeze({
      operation: "decision.append",
      label: "Validate and append one durable review event",
      symbols: Object.freeze([
        "sunofriend.workbench_server._WorkbenchHandler.do_POST",
        "sunofriend.workbench_store.WorkbenchStore.append",
        "sunofriend.workbench_store.WorkbenchStore.current_state",
      ]),
      durableEffect: true,
    }),
    "/api/render-preview": Object.freeze({
      operation: "preview.render",
      label: "Render or reuse a neutral MIDI preview",
      symbols: Object.freeze([
        "sunofriend.workbench_server._WorkbenchHandler.do_POST",
        "sunofriend.workbench_artifacts.WorkbenchArtifacts.render_candidate_preview",
      ]),
      durableEffect: false,
    }),
    "/api/decoded-loop": Object.freeze({
      operation: "transport.stem_loop.prepare",
      label: "Prepare one exact short comparison loop",
      symbols: Object.freeze([
        "sunofriend.workbench_server._WorkbenchHandler.do_POST",
        "sunofriend.workbench_artifacts.WorkbenchArtifacts.build_decoded_loop",
      ]),
      durableEffect: false,
    }),
    "/api/decoded-arrangement-loop": Object.freeze({
      operation: "transport.arrangement_loop.prepare",
      label: "Prepare one-clock arrangement presets",
      symbols: Object.freeze([
        "sunofriend.workbench_server._WorkbenchHandler.do_POST",
        "sunofriend.workbench_artifacts.WorkbenchArtifacts.build_decoded_arrangement_loop",
      ]),
      durableEffect: false,
    }),
    "/api/decoded-arrangement-stream": Object.freeze({
      operation: "transport.full_song.prepare",
      label: "Freeze a bounded full-song stream plan",
      symbols: Object.freeze([
        "sunofriend.workbench_server._WorkbenchHandler.do_POST",
        "sunofriend.workbench_artifacts.WorkbenchArtifacts.build_decoded_arrangement_stream",
      ]),
      durableEffect: false,
    }),
    "/api/decoded-arrangement-chunk": Object.freeze({
      operation: "transport.full_song.chunk",
      label: "Verify and decode one bounded stream chunk",
      symbols: Object.freeze([
        "sunofriend.workbench_server._WorkbenchHandler.do_POST",
        "sunofriend.workbench_artifacts.WorkbenchArtifacts.build_decoded_arrangement_chunk",
      ]),
      durableEffect: false,
    }),
    "/api/garageband-pack-plan": Object.freeze({
      operation: "pack.plan",
      label: "Derive the exact eligible GarageBand pack plan",
      symbols: Object.freeze([
        "sunofriend.workbench_store.WorkbenchStore.current_state",
        "sunofriend.workbench_artifacts.WorkbenchArtifacts.garageband_pack_plan",
      ]),
      durableEffect: false,
    }),
    "/api/garageband-pack-basket": Object.freeze({
      operation: "pack.basket.save",
      label: "Save a separate export-basket revision",
      symbols: Object.freeze([
        "sunofriend.workbench_server._WorkbenchHandler.do_POST",
        "sunofriend.workbench_store.WorkbenchStore.save_pack_selection",
      ]),
      durableEffect: true,
    }),
    "/api/garageband-pack": Object.freeze({
      operation: "pack.build",
      label: "Build and verify an exact local ZIP",
      symbols: Object.freeze([
        "sunofriend.workbench_server._WorkbenchHandler.do_POST",
        "sunofriend.workbench_artifacts.WorkbenchArtifacts.build_garageband_pack",
        "sunofriend.garageband_pack_acceptance.create_garageband_pack_acceptance_review",
      ]),
      durableEffect: false,
    }),
    "/api/review": Object.freeze({
      operation: "review.export",
      label: "Export the full private local review",
      symbols: Object.freeze([
        "sunofriend.workbench_server._WorkbenchHandler.do_GET",
        "sunofriend.workbench_store.WorkbenchStore.export_review",
      ]),
      durableEffect: false,
    }),
    "/api/clips": Object.freeze({
      operation: "clip_library.browse",
      label: "Browse verified immutable Clip objects",
      symbols: Object.freeze([
        "sunofriend.workbench_server._WorkbenchHandler.do_GET",
        "sunofriend.workbench_clips.WorkbenchClipService.browse",
      ]),
      durableEffect: false,
    }),
    "/api/clips/{clip_id}": Object.freeze({
      operation: "clip_library.detail",
      label: "Inspect one Clip and its version lineage",
      symbols: Object.freeze([
        "sunofriend.workbench_server._WorkbenchHandler.do_GET",
        "sunofriend.workbench_clips.WorkbenchClipService.detail",
      ]),
      durableEffect: false,
    }),
    "/api/clip-artifact": Object.freeze({
      operation: "clip_library.artifact",
      label: "Reconstruct deterministic MIDI or a dry proxy",
      symbols: Object.freeze([
        "sunofriend.workbench_server._WorkbenchHandler.do_POST",
        "sunofriend.workbench_clips.WorkbenchClipService.prepare_artifact",
      ]),
      durableEffect: false,
    }),
    "/api/clip-reuse-plan": Object.freeze({
      operation: "clip_reuse.read",
      label: "Read the separate explicit Clip reuse proposal",
      symbols: Object.freeze([
        "sunofriend.workbench_server._WorkbenchHandler.do_GET",
        "sunofriend.workbench_reuse.WorkbenchClipReuseService.plan",
      ]),
      durableEffect: false,
    }),
    "/api/clip-reuse-action": Object.freeze({
      operation: "clip_reuse.change",
      label: "Append one explicit Clip placement or removal",
      symbols: Object.freeze([
        "sunofriend.workbench_server._WorkbenchHandler.do_POST",
        "sunofriend.workbench_reuse.WorkbenchClipReuseService.apply",
        "sunofriend.workbench_reuse.WorkbenchClipReuseStore",
      ]),
      durableEffect: true,
    }),
    "/api/clip-transform-projection": Object.freeze({
      operation: "clip_transform.preview",
      label: "Preview one immutable Clip version without writing",
      symbols: Object.freeze([
        "sunofriend.workbench_server._WorkbenchHandler.do_POST",
        "sunofriend.workbench_transform.WorkbenchClipTransformService.preview",
      ]),
      durableEffect: false,
    }),
    "/api/clip-transform-action": Object.freeze({
      operation: "clip_transform.create",
      label: "Append one explicitly confirmed immutable Clip version",
      symbols: Object.freeze([
        "sunofriend.workbench_server._WorkbenchHandler.do_POST",
        "sunofriend.workbench_transform.WorkbenchClipTransformService.create",
        "sunofriend.library.ClipLibrary.append_version_if_state",
      ]),
      durableEffect: true,
    }),
    "/api/clip-note-correction-window": Object.freeze({
      operation: "clip_correction.window",
      label: "Read one bounded immutable Clip note window",
      symbols: Object.freeze([
        "sunofriend.workbench_server._WorkbenchHandler.do_POST",
        "sunofriend.workbench_correction.WorkbenchClipCorrectionService.window",
      ]),
      durableEffect: false,
    }),
    "/api/clip-note-correction-projection": Object.freeze({
      operation: "clip_correction.preview",
      label: "Preview one explicit pitch, attack-velocity, note-removal or onset-shift correction without writing",
      symbols: Object.freeze([
        "sunofriend.workbench_server._WorkbenchHandler.do_POST",
        "sunofriend.workbench_correction.WorkbenchClipCorrectionService.preview",
      ]),
      durableEffect: false,
    }),
    "/api/clip-note-correction-action": Object.freeze({
      operation: "clip_correction.create",
      label: "Append one explicitly confirmed corrected Clip version",
      symbols: Object.freeze([
        "sunofriend.workbench_server._WorkbenchHandler.do_POST",
        "sunofriend.workbench_correction.WorkbenchClipCorrectionService.create",
        "sunofriend.library.ClipLibrary.append_version_if_state",
      ]),
      durableEffect: true,
    }),
  });

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[character]);
  }

  function routePath(value) {
    const text = String(value || "");
    const query = text.indexOf("?");
    const hash = text.indexOf("#");
    const end = Math.min(
      query < 0 ? text.length : query,
      hash < 0 ? text.length : hash
    );
    return text.slice(0, end);
  }

  function routeDescriptor(path) {
    const route = routePath(path);
    const key = route.startsWith("/api/clips/") ? "/api/clips/{clip_id}" : route;
    return ROUTES[key] || null;
  }

  function finiteOrZero(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : 0;
  }

  function createOperationJournal(options = {}) {
    const limit = Math.max(1, Math.min(CLIENT_TRACE_LIMIT, Number(options.limit) || CLIENT_TRACE_LIMIT));
    const now = typeof options.now === "function"
      ? options.now
      : () => (typeof performance !== "undefined" ? performance.now() : Date.now());
    let sequence = 0;
    let dropped = 0;
    const records = [];

    function start(path, method = "GET") {
      const descriptor = routeDescriptor(path);
      // Inspector refreshes are excluded so observing the inspector never makes
      // its own trace appear to grow.
      if (!descriptor || routePath(path) === "/api/developer-snapshot") {
        return Object.freeze({ complete() {} });
      }
      const started = finiteOrZero(now());
      const record = {
        schema: CLIENT_TRACE_SCHEMA,
        sequence: ++sequence,
        operation: descriptor.operation,
        label: descriptor.label,
        method: String(method || "GET").toUpperCase(),
        route: routePath(path),
        status: "active",
        status_code: null,
        duration_ms: 0,
        durable_effect_possible: descriptor.durableEffect,
        symbols: [...descriptor.symbols],
        frames: [
          {
            label: "Browser request prepared",
            explanation: "The browser sends an allow-listed route plus IDs or hashes. The private session token is deliberately not recorded here.",
            symbol: "src/sunofriend/workbench.html::api",
          },
          {
            label: "Server route selected",
            explanation: "The loopback server validates the client, token, route and request shape before calling application code.",
            symbol: descriptor.symbols[0],
          },
        ],
      };
      records.push(record);
      if (records.length > limit) {
        records.shift();
        dropped += 1;
      }
      let finished = false;
      return Object.freeze({
        complete(result = {}) {
          if (finished) return;
          finished = true;
          const statusCode = Number(result.statusCode);
          record.status_code = Number.isInteger(statusCode) ? statusCode : null;
          record.status = result.errorClass
            ? String(result.errorClass)
            : statusCode >= 200 && statusCode < 400
              ? "completed"
              : "failed";
          record.duration_ms = Math.max(0, finiteOrZero(now()) - started);
          record.frames.push({
            label: record.status === "completed" ? "Response accepted" : "Operation stopped safely",
            explanation: record.status === "completed"
              ? "The browser accepted the path-free response. Any durable effect is explicit in the route contract."
              : "The operation failed without the inspector storing an exception message, response body or private input.",
            symbol: "src/sunofriend/workbench.html::api",
          });
        },
      });
    }

    return Object.freeze({
      start,
      clear() {
        records.length = 0;
        dropped = 0;
      },
      snapshot() {
        return {
          schema: "sunofriend.workbench-browser-operation-journal.v1",
          records: records.map((record) => ({
            ...record,
            symbols: [...record.symbols],
            frames: record.frames.map((frame) => ({ ...frame })),
          })),
          dropped_count: dropped,
          persisted: false,
        };
      },
    });
  }

  function safeBrowserState(value) {
    const input = value && typeof value === "object" ? value : {};
    const caches = input.caches && typeof input.caches === "object" ? input.caches : {};
    return Object.freeze({
      view: String(input.view || "unknown"),
      active_stem_id: input.active_stem_id == null ? null : String(input.active_stem_id),
      playhead_seconds: Math.max(0, finiteOrZero(input.playhead_seconds)),
      selected_midi_count: Math.max(0, Math.trunc(finiteOrZero(input.selected_midi_count))),
      mixer_preset: String(input.mixer_preset || "none"),
      mixer_playing: input.mixer_playing === true,
      precise_stem_loop_prepared: input.precise_stem_loop_prepared === true,
      precise_arrangement_loop_prepared: input.precise_arrangement_loop_prepared === true,
      full_song_stream_prepared: input.full_song_stream_prepared === true,
      caches: Object.freeze({
        timeline_entries: Math.max(0, Math.trunc(finiteOrZero(caches.timeline_entries))),
        decoded_extra_stems: Math.max(0, Math.trunc(finiteOrZero(caches.decoded_extra_stems))),
        mixer_tracks: Math.max(0, Math.trunc(finiteOrZero(caches.mixer_tracks))),
      }),
      persisted: false,
    });
  }

  function list(value) {
    return Array.isArray(value) ? value : [];
  }

  function object(value) {
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  }

  function displayJson(value) {
    return escapeHtml(JSON.stringify(value, null, 2));
  }

  function statusBadge(value) {
    const text = String(value || "unknown");
    const good = ["completed", "ready", "passed", "ok"].includes(text);
    return `<span class="badge ${good ? "good" : ""}">${escapeHtml(text)}</span>`;
  }

  function architectureHtml(snapshot) {
    const flow = object(snapshot.code_flow || snapshot.architecture);
    const nodes = list(flow.nodes);
    if (!nodes.length) {
      return `<p class="muted">The current server did not publish the static architecture map.</p>`;
    }
    return `<div class="developer-flow">${nodes.map((node, index) => {
      const symbols = list(node.symbols || node.code_refs || node.call_path);
      return `<article class="developer-node">
        <span class="badge">${index + 1}</span>
        <h4>${escapeHtml(node.label || node.name || node.id || "Code stage")}</h4>
        <p>${escapeHtml(node.explanation || node.summary || "")}</p>
        ${symbols.length ? `<ul class="developer-symbols">${symbols.map((symbol) => `<li><code>${escapeHtml(symbol)}</code></li>`).join("")}</ul>` : ""}
        ${node.invariant ? `<p><b>Invariant:</b> ${escapeHtml(node.invariant)}</p>` : ""}
      </article>`;
    }).join("<span class=\"developer-arrow\" aria-hidden=\"true\">→</span>")}</div>`;
  }

  function operationHtml(operation, frameIndex) {
    if (!operation) return `<p class="muted">Use the Workbench, then return here to inspect its bounded page trace.</p>`;
    const frames = list(operation.frames);
    const safeFrameIndex = Math.max(0, Math.min(frames.length - 1, frameIndex || 0));
    const frame = frames[safeFrameIndex] || {};
    return `<article class="developer-operation">
      <h4>${escapeHtml(operation.label || operation.operation || "Operation")} ${statusBadge(operation.status)}</h4>
      <p><code>${escapeHtml(operation.method || "")}</code> <code>${escapeHtml(operation.route || "")}</code> · ${escapeHtml(Math.round(finiteOrZero(operation.duration_ms) * 10) / 10)} ms</p>
      <p><b>Durable effect possible:</b> ${operation.durable_effect_possible ? "yes, only through this explicit production command" : "no"}</p>
      ${frames.length > 1 ? `<label>Operation checkpoint <input id="developer-frame-range" type="range" min="0" max="${frames.length - 1}" value="${safeFrameIndex}"> <output>${safeFrameIndex + 1} of ${frames.length}</output></label>` : ""}
      ${frames.length ? `<section class="developer-frame"><h4>${escapeHtml(frame.label || `Checkpoint ${safeFrameIndex + 1}`)}</h4><p>${escapeHtml(frame.explanation || frame.summary || "")}</p>${frame.symbol ? `<p><code>${escapeHtml(frame.symbol)}</code></p>` : ""}</section>` : ""}
      <details><summary>Static code call chain</summary><ol class="developer-symbols">${list(operation.symbols).map((symbol) => `<li><code>${escapeHtml(symbol)}</code></li>`).join("")}</ol></details>
    </article>`;
  }

  function replayFrames(snapshot) {
    const candidates = [
      snapshot.state_replay,
      object(snapshot.current).state_replay,
      object(snapshot.durable_state).replay,
      object(snapshot.runtime).state_replay,
    ];
    for (const candidate of candidates) {
      if (Array.isArray(candidate)) return candidate;
      if (candidate && Array.isArray(candidate.frames)) return candidate.frames;
      if (candidate && Array.isArray(candidate.events)) return candidate.events;
    }
    return [];
  }

  function replayHtml(snapshot, replayIndex) {
    const frames = replayFrames(snapshot);
    if (!frames.length) {
      return `<p class="muted">No durable review events exist yet, or this server has no replay projection. Playback, zoom, mute and Inspector refresh never create one.</p>`;
    }
    const safeIndex = Math.max(0, Math.min(frames.length - 1, replayIndex || 0));
    const frame = object(frames[safeIndex]);
    return `<label>State after durable event <input id="developer-replay-range" type="range" min="0" max="${frames.length - 1}" value="${safeIndex}"> <output>${safeIndex} of ${frames.length - 1}</output></label>
      <div class="developer-state-grid">
        <section><h4>Event</h4><pre>${displayJson(frame.event || frame.event_summary || { index: safeIndex })}</pre></section>
        <section><h4>Before</h4><pre>${displayJson(frame.before ?? null)}</pre></section>
        <section><h4>After</h4><pre>${displayJson(frame.after || frame.state || frame.derived_state || {})}</pre></section>
        <section><h4>Changed fields</h4><pre>${displayJson(frame.diff || frame.changes || [])}</pre></section>
      </div>`;
  }

  function currentStateHtml(snapshot, browserState) {
    const current = object(snapshot.current);
    const catalog = object(current.catalog || snapshot.catalog);
    const durable = object(current.durable_state || snapshot.durable_state);
    const derived = object(current.derived_state || snapshot.derived_state);
    const pack = object(
      current.pack_state || object(current.durable_state).pack_basket || snapshot.pack_state
    );
    const runtime = object(snapshot.runtime);
    return `<div class="developer-state-grid">
      <section><h4>Immutable catalog</h4><pre>${displayJson(catalog)}</pre></section>
      <section><h4>Durable event state</h4><pre>${displayJson(durable)}</pre></section>
      <section><h4>Derived selection</h4><pre>${displayJson(derived)}</pre></section>
      <section><h4>Separate pack basket</h4><pre>${displayJson(pack)}</pre></section>
      <section><h4>Server runtime</h4><pre>${displayJson(runtime)}</pre></section>
      <section><h4>This browser tab only</h4><pre>${displayJson(browserState)}</pre></section>
    </div>`;
  }

  function serverOperation(record, snapshot) {
    const codeMap = object(object(snapshot?.code_flow).code_map);
    const frames = list(record.frames).map((frame) => {
      const code = object(codeMap[frame.code_step]);
      const symbol = code.module && code.symbol
        ? `${code.module}.${code.symbol}`
        : null;
      const facts = object(frame.facts);
      return {
        label: String(frame.stage || frame.code_step || "operation checkpoint"),
        explanation: Object.keys(facts).length
          ? `Allow-listed facts: ${JSON.stringify(facts)}`
          : "This checkpoint deliberately records no request body, response document or local variable.",
        symbol,
      };
    });
    const projectedSymbols = list(record.symbols).filter((symbol) => (
      typeof symbol === "string"
      && symbol.length > 0
      && symbol.length <= 500
      && !/[\r\n]/.test(symbol)
      && (symbol.startsWith("sunofriend.") || symbol.startsWith("src/sunofriend/"))
    ));
    const frameSymbols = frames.map((frame) => frame.symbol).filter(Boolean);
    const projectedDurableEffect = typeof record.durable_effect_possible === "boolean"
      ? record.durable_effect_possible
      : ["decision.append", "pack_basket.save", "clip_reuse.change"].includes(record.operation);
    return {
      ...record,
      label: String(record.operation || "server operation")
        .split(/[._-]/)
        .map((part) => part ? part[0].toUpperCase() + part.slice(1) : "")
        .join(" "),
      route: "server-owned route",
      duration_ms: finiteOrZero(record.duration_ms),
      durable_effect_possible: projectedDurableEffect,
      symbols: [...new Set([...projectedSymbols, ...frameSymbols])],
      frames,
    };
  }

  function createInspector(options = {}) {
    if (typeof options.api !== "function") throw new TypeError("Developer Inspector requires an api function");
    const journal = options.journal || createOperationJournal();
    const browserState = typeof options.browserState === "function" ? options.browserState : () => ({});
    let enabled = false;
    let target = null;
    let snapshot = null;
    let error = "";
    let loading = false;
    let operationIndex = -1;
    let frameIndex = 0;
    let replayIndex = 0;

    function browserSnapshot() {
      try {
        return safeBrowserState(browserState());
      } catch {
        return safeBrowserState({});
      }
    }

    function operations() {
      const client = journal.snapshot().records;
      const serverRuntime = object(snapshot?.runtime);
      const trace = object(serverRuntime.trace);
      const active = list(serverRuntime.active_operations || trace.active_operations);
      const recent = list(serverRuntime.recent_operations || trace.recent_operations);
      const server = [...recent, ...active].map((record) => serverOperation(record, snapshot));
      return [...server, ...client];
    }

    function render() {
      if (!target) return;
      if (!enabled) {
        target.innerHTML = `<section class="panel"><h2>Developer Inspector unavailable</h2><p>Restart Workbench with <code>--developer-inspector</code>. It is off by default.</p></section>`;
        return;
      }
      const allOperations = operations();
      if (operationIndex < 0 && allOperations.length) operationIndex = allOperations.length - 1;
      operationIndex = Math.max(0, Math.min(Math.max(0, allOperations.length - 1), operationIndex));
      const selectedOperation = allOperations[operationIndex] || null;
      const privacy = object(snapshot?.privacy);
      const effects = object(snapshot?.effects);
      target.innerHTML = `<section class="panel developer-inspector" aria-labelledby="developer-inspector-heading">
        <h2 id="developer-inspector-heading">Developer Inspector <span class="badge">read only</span></h2>
        <div class="decoded-boundary"><b>An application-specific code microworld.</b> It observes explicit operation boundaries and state derivation. It cannot pause Python, evaluate expressions, browse files, run a model, edit state or save feedback.</div>
        <p>Start with the architecture, perform an ordinary Workbench action, then inspect its page trace and code call chain. Use the event scrubber to see how append-only decisions derive current state. This trace is bounded, memory-only and clears on restart.</p>
        <div class="actions"><button id="developer-refresh" class="primary" type="button" ${loading ? "disabled" : ""}>${loading ? "Refreshing…" : "Refresh read-only snapshot"}</button><button id="developer-clear" type="button">Clear this page trace</button></div>
        ${error ? `<p class="error" role="alert">${escapeHtml(error)}</p>` : ""}
        <section class="developer-section"><h3>1. Production architecture</h3>${snapshot ? architectureHtml(snapshot) : `<p class="busy">Loading the safe server projection…</p>`}</section>
        <section class="developer-section"><h3>2. Operations from this page and server launch</h3>
          <p class="muted">Only route, status, duration and a static call path are recorded. Query strings, tokens, bodies, returned data and exception messages are excluded.</p>
          ${allOperations.length > 1 ? `<label>Operation <input id="developer-operation-range" type="range" min="0" max="${allOperations.length - 1}" value="${operationIndex}"> <output>${operationIndex + 1} of ${allOperations.length}</output></label>` : ""}
          ${operationHtml(selectedOperation, frameIndex)}
        </section>
        <section class="developer-section"><h3>3. State at this instant</h3>${snapshot ? currentStateHtml(snapshot, browserSnapshot()) : `<p class="muted">No snapshot loaded.</p>`}</section>
        <section class="developer-section"><h3>4. Append-only event replay</h3>${snapshot ? replayHtml(snapshot, replayIndex) : `<p class="muted">No snapshot loaded.</p>`}</section>
        <section class="developer-section"><h3>5. Trust boundary</h3>
          <div class="developer-state-grid"><section><h4>Privacy claims</h4><pre>${displayJson(privacy)}</pre></section><section><h4>Inspector effects</h4><pre>${displayJson(effects)}</pre></section></div>
          <p><b>Important:</b> this is a curated observer, not proof that the musical result is correct. Use the source/MIDI comparison and GarageBand acceptance checks for musical judgement.</p>
        </section>
        <details class="developer-section"><summary>Raw safe snapshot</summary><pre>${snapshot ? displayJson(snapshot) : "No snapshot loaded."}</pre></details>
      </section>`;
      wire();
    }

    function wire() {
      target?.querySelector("#developer-refresh")?.addEventListener("click", refresh);
      target?.querySelector("#developer-clear")?.addEventListener("click", () => {
        journal.clear();
        operationIndex = -1;
        frameIndex = 0;
        render();
      });
      target?.querySelector("#developer-operation-range")?.addEventListener("input", (event) => {
        operationIndex = Number(event.currentTarget.value);
        frameIndex = 0;
        render();
      });
      target?.querySelector("#developer-frame-range")?.addEventListener("input", (event) => {
        frameIndex = Number(event.currentTarget.value);
        render();
      });
      target?.querySelector("#developer-replay-range")?.addEventListener("input", (event) => {
        replayIndex = Number(event.currentTarget.value);
        render();
      });
    }

    async function refresh() {
      if (!enabled || loading) return;
      loading = true;
      error = "";
      render();
      try {
        snapshot = await options.api("/api/developer-snapshot");
      } catch (caught) {
        error = caught?.message || String(caught);
      } finally {
        loading = false;
        render();
      }
    }

    return Object.freeze({
      journal,
      setEnabled(value) {
        enabled = value === true;
      },
      renderInto(element) {
        target = element;
        render();
        if (enabled && !snapshot && !loading) refresh();
      },
      refresh,
      snapshotForTests() {
        return {
          enabled,
          loading,
          hasSnapshot: !!snapshot,
          operationCount: operations().length,
          browserState: browserSnapshot(),
        };
      },
    });
  }

  return Object.freeze({
    CLIENT_TRACE_LIMIT,
    ROUTES,
    createInspector,
    createOperationJournal,
    escapeHtml,
    routeDescriptor,
    routePath,
    safeBrowserState,
  });
});
