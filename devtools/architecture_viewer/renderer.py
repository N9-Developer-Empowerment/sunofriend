"""Render a static, offline architecture explorer from an analysed source tree."""

from __future__ import annotations

import html
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from .analyzer import calculate_architecture_sha256


_INDEX_STYLE = r"""
:root {
  color-scheme: dark;
  --ink: #020617;
  --ink-soft: #07102a;
  --panel: rgba(8, 17, 43, 0.94);
  --panel-strong: #0d1935;
  --line: rgba(106, 174, 255, 0.28);
  --white: #f7fbff;
  --muted: #a9b9da;
  --cyan: #00e6ff;
  --orange: #ff7448;
  --pink: #ff3d8d;
  --purple: #955cff;
  --acid: #dfff37;
  --good: #75e6a4;
  --mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  --body: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
* { box-sizing: border-box; }
html { background: var(--ink); }
body {
  margin: 0;
  min-width: 320px;
  background:
    radial-gradient(circle at 78% 8%, rgba(149, 92, 255, 0.16), transparent 34rem),
    radial-gradient(circle at 9% 20%, rgba(0, 230, 255, 0.09), transparent 28rem),
    var(--ink);
  color: var(--white);
  font-family: var(--body);
}
button, input { font: inherit; }
button { color: inherit; }
a { color: var(--cyan); }
:focus-visible { outline: 3px solid var(--acid); outline-offset: 3px; }
.shell { width: min(1540px, calc(100% - 32px)); margin: 0 auto; padding: 24px 0 48px; }
.masthead { display: flex; gap: 24px; align-items: flex-start; justify-content: space-between; padding: 10px 0 22px; border-bottom: 1px solid var(--line); }
.eyebrow { margin: 0 0 7px; color: var(--cyan); font-size: .72rem; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; }
h1, h2, h3 { margin-top: 0; font-weight: 800; letter-spacing: -.025em; }
h1 { margin-bottom: 8px; font-size: clamp(1.7rem, 3vw, 2.8rem); }
h2 { font-size: 1.35rem; }
h3 { font-size: 1rem; }
.subtitle, .muted { color: var(--muted); }
.subtitle { max-width: 72ch; margin: 0; }
.hash { max-width: 26ch; overflow: hidden; color: var(--muted); font: .72rem var(--mono); text-overflow: ellipsis; white-space: nowrap; }
.stats { display: flex; flex-wrap: wrap; gap: 10px; padding: 18px 0; }
.stat { min-width: 118px; padding: 10px 12px; border-left: 2px solid var(--cyan); background: rgba(8, 17, 43, .58); }
.stat strong { display: block; font-size: 1.15rem; }
.stat span { color: var(--muted); font-size: .75rem; }
.toolbar { display: grid; grid-template-columns: minmax(220px, 1fr) auto; gap: 14px; align-items: end; margin: 2px 0 18px; }
.search-wrap { position: relative; }
.search-wrap label { display: block; margin-bottom: 6px; color: var(--muted); font-size: .76rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
input[type="search"] { width: 100%; border: 1px solid var(--line); border-radius: 0; padding: 11px 12px; background: var(--panel); color: var(--white); }
.search-results { position: absolute; z-index: 8; top: 100%; right: 0; left: 0; max-height: 340px; margin-top: 4px; overflow: auto; border: 1px solid var(--line); background: #07102a; box-shadow: 0 18px 50px rgba(0, 0, 0, .42); }
.search-results[hidden] { display: none; }
.search-result { display: block; width: 100%; border: 0; border-bottom: 1px solid var(--line); padding: 10px 12px; background: transparent; text-align: left; cursor: pointer; }
.search-result:hover { background: rgba(0, 230, 255, .08); }
.search-result small { display: block; margin-top: 3px; color: var(--muted); }
.switch { display: flex; gap: 8px; align-items: center; min-height: 43px; color: var(--muted); font-size: .85rem; }
.switch input { width: 18px; height: 18px; }
.breadcrumbs { display: flex; flex-wrap: wrap; gap: 7px; align-items: center; margin: 4px 0 14px; color: var(--muted); font-size: .86rem; }
.crumb { border: 0; padding: 4px 0; background: transparent; color: var(--cyan); cursor: pointer; }
.workspace { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(330px, .75fr); gap: 20px; align-items: start; }
.graph-panel, .detail-panel { border: 1px solid var(--line); background: var(--panel); }
.panel-head { display: flex; gap: 16px; align-items: flex-start; justify-content: space-between; padding: 18px 18px 8px; }
.panel-head p { margin: 3px 0 0; color: var(--muted); font-size: .85rem; }
.legend { display: flex; flex-wrap: wrap; gap: 12px; color: var(--muted); font-size: .75rem; }
.legend span::before { display: inline-block; width: 18px; height: 2px; margin: 0 6px 3px 0; background: var(--cyan); content: ""; }
.legend .incoming::before { background: var(--purple); }
.legend .outgoing::before { background: var(--orange); }
.graph-shell { position: relative; min-height: 340px; padding: 18px; overflow: hidden; }
.edges { position: absolute; z-index: 0; inset: 0; width: 100%; height: 100%; overflow: visible; pointer-events: none; }
.edge { fill: none; stroke: var(--cyan); stroke-width: 1.3; opacity: .46; }
.edge.incoming { stroke: var(--purple); opacity: .85; }
.edge.outgoing { stroke: var(--orange); opacity: .88; }
.edge-label { fill: var(--muted); font: 10px var(--mono); paint-order: stroke; stroke: var(--ink); stroke-width: 4px; }
.nodes { position: relative; z-index: 1; display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 26px 20px; align-items: stretch; }
.node { min-height: 92px; border: 1px solid rgba(106, 174, 255, .38); border-radius: 0; padding: 13px 14px; background: var(--panel-strong); text-align: left; cursor: pointer; box-shadow: 0 10px 24px rgba(0, 0, 0, .18); }
.node:hover { border-color: var(--cyan); transform: translateY(-1px); }
.node.selected { border: 2px solid var(--acid); }
.node.cycle { border-left: 4px solid var(--pink); }
.node.stub { border-style: dashed; background: rgba(13, 25, 53, .58); }
.node.violation { box-shadow: inset 0 0 0 2px var(--pink), 0 10px 24px rgba(0, 0, 0, .18); }
.node-name { display: block; overflow-wrap: anywhere; font: 700 .86rem var(--mono); }
.node-meta { display: block; margin-top: 8px; color: var(--muted); font-size: .72rem; line-height: 1.4; }
.detail-panel { position: sticky; top: 12px; max-height: calc(100vh - 24px); overflow: auto; padding: 20px; }
.detail-panel p { line-height: 1.55; }
.detail-panel code, .path { font-family: var(--mono); overflow-wrap: anywhere; }
.detail-panel code { color: var(--cyan); }
.detail-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin: 16px 0; }
.detail-metric { padding: 9px; background: rgba(0, 230, 255, .055); }
.detail-metric strong { display: block; }
.detail-metric span { color: var(--muted); font-size: .72rem; }
.action { display: inline-block; border: 1px solid var(--orange); padding: 9px 11px; color: var(--orange); font-weight: 750; text-decoration: none; }
.action:hover { background: var(--orange); color: var(--ink); }
.definition, .dependency { padding: 9px 0; border-top: 1px solid var(--line); }
.definition:first-child, .dependency:first-child { border-top: 0; }
.definition a { font-family: var(--mono); font-size: .82rem; text-decoration: none; }
.definition small, .dependency small { display: block; margin-top: 4px; color: var(--muted); line-height: 1.4; }
.members { margin: 8px 0 0 14px; padding-left: 14px; border-left: 1px solid var(--line); }
.relation { width: 100%; border: 0; padding: 8px 0; background: transparent; color: var(--cyan); font: .78rem var(--mono); text-align: left; cursor: pointer; overflow-wrap: anywhere; }
.relation:hover { color: var(--acid); }
details { margin-top: 16px; }
summary { color: var(--white); font-weight: 750; cursor: pointer; }
.notice { padding: 12px; border-left: 3px solid var(--pink); background: rgba(255, 61, 141, .07); color: var(--muted); }
.notice.good { border-left-color: var(--good); background: rgba(117, 230, 164, .07); }
.badge { display: inline-block; margin: 2px 4px 2px 0; border: 1px solid var(--line); padding: 2px 6px; color: var(--muted); font: .68rem var(--mono); }
.badge.bad { border-color: var(--pink); color: var(--pink); }
.badge.good { border-color: var(--good); color: var(--good); }
.badge.changed { border-color: var(--orange); color: var(--orange); }
.provenance { margin: 7px 0 0; padding-left: 18px; color: var(--muted); font: .72rem/1.55 var(--mono); }
.provenance a { text-decoration: none; }
.agent-query { width: 100%; min-height: 118px; margin-top: 8px; border: 1px solid var(--line); padding: 9px; background: var(--ink-soft); color: var(--muted); font: .72rem/1.45 var(--mono); resize: vertical; }
.copy-button { margin-top: 7px; border: 1px solid var(--cyan); padding: 7px 9px; background: transparent; color: var(--cyan); cursor: pointer; }
.system-list { display: grid; gap: 8px; margin-top: 10px; }
.system-item { padding: 9px; border-left: 2px solid var(--purple); background: rgba(149, 92, 255, .06); }
.empty { padding: 44px 18px; color: var(--muted); text-align: center; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@media (max-width: 980px) {
  .workspace { grid-template-columns: 1fr; }
  .detail-panel { position: static; max-height: none; }
}
@media (max-width: 620px) {
  .shell { width: min(100% - 20px, 1540px); padding-top: 10px; }
  .masthead { display: block; }
  .hash { margin-top: 12px; }
  .toolbar { grid-template-columns: 1fr; }
  .nodes { grid-template-columns: 1fr; }
  .graph-shell { padding: 12px; }
}
"""


_INDEX_SCRIPT = r"""
(() => {
  "use strict";
  const data = JSON.parse(document.getElementById("architecture-data").textContent);
  const modules = data.modules;
  const groups = new Map(data.groups.map(group => [group.id, group]));
  const groupOf = name => groups.get(modules[name].group);
  const graphShell = document.getElementById("graph-shell");
  const nodeRoot = document.getElementById("nodes");
  const edgeRoot = document.getElementById("edges");
  const detailRoot = document.getElementById("detail");
  const titleRoot = document.getElementById("graph-title");
  const captionRoot = document.getElementById("graph-caption");
  const breadcrumbs = document.getElementById("breadcrumbs");
  const allEdges = document.getElementById("all-edges");
  const edgeControl = document.getElementById("edge-control");
  const search = document.getElementById("search");
  const searchResults = document.getElementById("search-results");
  const live = document.getElementById("live");
  const state = { level: "groups", group: null, selected: null };

  function escapeText(value) {
    const span = document.createElement("span");
    span.textContent = value == null ? "" : String(value);
    return span.innerHTML;
  }

  function setHash(value) {
    if (history.replaceState) history.replaceState(null, "", value ? `#${value}` : location.pathname);
  }

  function groupButton(group) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "node";
    button.dataset.nodeId = group.id;
    button.setAttribute("aria-label", `${group.label}: ${group.module_count} modules`);
    button.innerHTML = `<span class="node-name">${escapeText(group.label)}</span><span class="node-meta">${group.module_count} modules · ${group.line_count.toLocaleString()} lines<br>${group.public_definition_count} public definitions</span>`;
    button.addEventListener("click", () => openGroup(group.id));
    return button;
  }

  function moduleButton(name) {
    const module = modules[name];
    const button = document.createElement("button");
    button.type = "button";
    button.className = "node" + (state.selected === name ? " selected" : "") + (module.cycle ? " cycle" : "");
    button.dataset.nodeId = name;
    button.setAttribute("aria-label", `${module.short_name}: ${module.imports.length} dependencies, ${module.imported_by.length} dependents`);
    button.innerHTML = `<span class="node-name">${escapeText(module.short_name)}</span><span class="node-meta">${module.line_count.toLocaleString()} lines · ${module.public_interface.length} public<br>imports ${module.imports.length} · used by ${module.imported_by.length}</span>`;
    button.addEventListener("click", () => openModule(name));
    return button;
  }

  function renderBreadcrumbs() {
    breadcrumbs.replaceChildren();
    const home = document.createElement("button");
    home.type = "button";
    home.className = "crumb";
    home.textContent = data.package;
    home.addEventListener("click", openOverview);
    breadcrumbs.append(home);
    if (state.group) {
      breadcrumbs.append(document.createTextNode(" / "));
      const group = groups.get(state.group);
      const groupControl = document.createElement("button");
      groupControl.type = "button";
      groupControl.className = "crumb";
      groupControl.textContent = group.label;
      groupControl.addEventListener("click", () => openGroup(group.id));
      breadcrumbs.append(groupControl);
    }
    if (state.selected) {
      breadcrumbs.append(document.createTextNode(" / "));
      const current = document.createElement("span");
      current.textContent = modules[state.selected].short_name;
      breadcrumbs.append(current);
    }
  }

  function renderOverviewDetail() {
    const cycleText = data.stats.cycle_count === 0
      ? "No static import cycles were detected."
      : `${data.stats.cycle_count} static import cycle${data.stats.cycle_count === 1 ? "" : "s"} detected.`;
    detailRoot.innerHTML = `<p class="eyebrow">How to read this</p><h2>System areas</h2><p>Each node is a configured architectural area. An arrow means at least one module in the source area imports a module in the target area.</p><div class="detail-grid"><div class="detail-metric"><strong>${data.stats.internal_dependency_count.toLocaleString()}</strong><span>module import relationships</span></div><div class="detail-metric"><strong>${data.stats.external_package_count}</strong><span>external import roots</span></div></div><p>${escapeText(cycleText)}</p><p class="muted">Choose an area to see its modules. Select a module to separate its public interface from implementation details and then open exact code lines.</p>`;
  }

  function renderGroupDetail(group) {
    const incoming = data.group_edges.filter(edge => edge.target === group.id);
    const outgoing = data.group_edges.filter(edge => edge.source === group.id);
    const relationList = (edges, direction) => edges.length
      ? edges.map(edge => {
          const other = groups.get(direction === "out" ? edge.target : edge.source);
          return `<div class="dependency"><button class="relation" data-group="${escapeText(other.id)}">${escapeText(other.label)}</button><small>${edge.count} module-level import relationship${edge.count === 1 ? "" : "s"}</small></div>`;
        }).join("")
      : `<p class="muted">None detected.</p>`;
    detailRoot.innerHTML = `<p class="eyebrow">Architecture area</p><h2>${escapeText(group.label)}</h2><p>${escapeText(group.description)}</p><div class="detail-grid"><div class="detail-metric"><strong>${group.module_count}</strong><span>modules</span></div><div class="detail-metric"><strong>${group.line_count.toLocaleString()}</strong><span>source lines</span></div></div><details open><summary>Imports from other areas</summary>${relationList(outgoing, "out")}</details><details><summary>Imported by other areas</summary>${relationList(incoming, "in")}</details>`;
    detailRoot.querySelectorAll("[data-group]").forEach(button => button.addEventListener("click", () => openGroup(button.dataset.group)));
  }

  function definitionHtml(definition, module) {
    const members = definition.members && definition.members.length
      ? `<div class="members">${definition.members.map(member => definitionHtml(member, module)).join("")}</div>`
      : "";
    const summary = definition.summary ? `<small>${escapeText(definition.summary)}</small>` : "";
    return `<div class="definition"><a href="${escapeText(module.code_page)}#L${definition.line}">${escapeText(definition.signature || definition.qualified_name)}</a><small>${escapeText(definition.kind)} · lines ${definition.line}–${definition.end_line}</small>${summary}${members}</div>`;
  }

  function relationHtml(name, note) {
    const module = modules[name];
    if (!module) return "";
    return `<div class="dependency"><button class="relation" data-module="${escapeText(name)}">${escapeText(module.short_name)}</button><small>${escapeText(groupOf(name).label)}${note ? ` · ${escapeText(note)}` : ""}</small></div>`;
  }

  function renderModuleDetail(name) {
    const module = modules[name];
    const imports = module.imports.length
      ? module.imports.map(item => relationHtml(item.module, item.symbols.length ? `symbols: ${item.symbols.join(", ")}` : "module import")).join("")
      : `<p class="muted">No internal imports detected.</p>`;
    const importedBy = module.imported_by.length
      ? module.imported_by.map(item => relationHtml(item, "imports this module")).join("")
      : `<p class="muted">No internal importers detected.</p>`;
    const publicDefinitions = module.public_interface.length
      ? module.public_interface.map(item => definitionHtml(item, module)).join("")
      : `<p class="muted">No public top-level functions or classes detected.</p>`;
    const privateDefinitions = module.implementation.length
      ? module.implementation.map(item => definitionHtml(item, module)).join("")
      : `<p class="muted">No private top-level functions or classes detected.</p>`;
    const external = module.external_imports.length
      ? module.external_imports.map(escapeText).join(", ")
      : "None detected";
    const cycle = module.cycle
      ? `<p class="notice">This module is in static import cycle ${module.cycle}. Follow the incoming and outgoing relationships before changing the boundary.</p>`
      : "";
    const parseError = module.parse_error
      ? `<p class="notice">AST parsing failed: ${escapeText(module.parse_error)}</p>`
      : "";
    detailRoot.innerHTML = `<p class="eyebrow">Module · ${escapeText(groupOf(name).label)}</p><h2><code>${escapeText(module.short_name)}</code></h2><p>${escapeText(module.summary || "No module docstring summary.")}</p><p class="path">${escapeText(module.path)}</p>${cycle}${parseError}<div class="detail-grid"><div class="detail-metric"><strong>${module.public_interface.length}</strong><span>public definitions</span></div><div class="detail-metric"><strong>${module.implementation.length}</strong><span>private definitions</span></div><div class="detail-metric"><strong>${module.imports.length}</strong><span>internal imports</span></div><div class="detail-metric"><strong>${module.imported_by.length}</strong><span>internal importers</span></div></div><p><a class="action" href="${escapeText(module.code_page)}">Open complete source</a></p><details open><summary>Public interface (${escapeText(module.interface_source)})</summary>${publicDefinitions}</details><details><summary>Implementation definitions</summary>${privateDefinitions}</details><details><summary>Internal dependencies</summary>${imports}</details><details><summary>Imported by</summary>${importedBy}</details><details><summary>External import roots</summary><p class="muted">${external}</p></details><details><summary>Identity</summary><p class="hash">SHA-256 ${escapeText(module.source_sha256)}</p></details>`;
    detailRoot.querySelectorAll("[data-module]").forEach(button => button.addEventListener("click", () => openModule(button.dataset.module)));
  }

  function currentEdges() {
    if (state.level === "groups") return data.group_edges;
    const names = new Set(groups.get(state.group).modules);
    const edges = [];
    names.forEach(source => {
      modules[source].imports.forEach(item => {
        if (names.has(item.module)) edges.push({ source, target: item.module, count: 1 });
      });
    });
    if (allEdges.checked || !state.selected) return allEdges.checked ? edges : [];
    return edges.filter(edge => edge.source === state.selected || edge.target === state.selected);
  }

  function drawEdges() {
    edgeRoot.replaceChildren();
    const shellBox = graphShell.getBoundingClientRect();
    const width = Math.max(1, graphShell.clientWidth);
    const height = Math.max(1, graphShell.clientHeight);
    edgeRoot.setAttribute("viewBox", `0 0 ${width} ${height}`);
    const definitions = document.createElementNS("http://www.w3.org/2000/svg", "defs");
    definitions.innerHTML = `<marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke"></path></marker>`;
    edgeRoot.append(definitions);
    currentEdges().forEach(edge => {
      const source = nodeRoot.querySelector(`[data-node-id="${CSS.escape(edge.source)}"]`);
      const target = nodeRoot.querySelector(`[data-node-id="${CSS.escape(edge.target)}"]`);
      if (!source || !target || source === target) return;
      const a = source.getBoundingClientRect();
      const b = target.getBoundingClientRect();
      const x1 = a.left + a.width / 2 - shellBox.left;
      const y1 = a.top + a.height / 2 - shellBox.top;
      const x2 = b.left + b.width / 2 - shellBox.left;
      const y2 = b.top + b.height / 2 - shellBox.top;
      const dx = x2 - x1;
      const dy = y2 - y1;
      const length = Math.max(1, Math.hypot(dx, dy));
      const startPad = Math.min(a.width, a.height) * .36;
      const endPad = Math.min(b.width, b.height) * .43;
      const sx = x1 + dx / length * startPad;
      const sy = y1 + dy / length * startPad;
      const tx = x2 - dx / length * endPad;
      const ty = y2 - dy / length * endPad;
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      const direction = state.selected && edge.source === state.selected ? " outgoing" : state.selected && edge.target === state.selected ? " incoming" : "";
      line.setAttribute("class", `edge${direction}`);
      line.setAttribute("x1", sx); line.setAttribute("y1", sy);
      line.setAttribute("x2", tx); line.setAttribute("y2", ty);
      line.setAttribute("marker-end", "url(#arrow)");
      const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      title.textContent = `${edge.source} imports ${edge.target}`;
      line.append(title);
      edgeRoot.append(line);
      if (state.level === "groups") {
        const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
        label.setAttribute("class", "edge-label");
        label.setAttribute("x", (sx + tx) / 2);
        label.setAttribute("y", (sy + ty) / 2 - 3);
        label.textContent = edge.count;
        edgeRoot.append(label);
      }
    });
  }

  function renderGraph() {
    nodeRoot.replaceChildren();
    if (state.level === "groups") {
      titleRoot.textContent = "System overview";
      captionRoot.textContent = "Configured areas and aggregate import direction. Select an area to drill down.";
      data.groups.forEach(group => nodeRoot.append(groupButton(group)));
      edgeControl.hidden = true;
      renderOverviewDetail();
    } else {
      const group = groups.get(state.group);
      titleRoot.textContent = group.label;
      captionRoot.textContent = `${group.module_count} modules. Select one to focus its incoming and outgoing imports.`;
      group.modules.forEach(name => nodeRoot.append(moduleButton(name)));
      edgeControl.hidden = false;
      if (state.selected) renderModuleDetail(state.selected); else renderGroupDetail(group);
    }
    renderBreadcrumbs();
    requestAnimationFrame(drawEdges);
  }

  function openOverview() {
    state.level = "groups"; state.group = null; state.selected = null;
    setHash(""); renderGraph(); live.textContent = "Showing the system overview.";
  }

  function openGroup(id) {
    if (!groups.has(id)) return;
    state.level = "modules"; state.group = id; state.selected = null;
    setHash(`group=${encodeURIComponent(id)}`); renderGraph();
    live.textContent = `Showing ${groups.get(id).label}.`;
  }

  function openModule(name) {
    if (!modules[name]) return;
    state.level = "modules"; state.group = modules[name].group; state.selected = name;
    setHash(`module=${encodeURIComponent(name)}`); renderGraph();
    const selectedNode = nodeRoot.querySelector(`[data-node-id="${CSS.escape(name)}"]`);
    if (selectedNode) selectedNode.scrollIntoView({ block: "nearest", behavior: "smooth" });
    live.textContent = `Showing module ${modules[name].short_name}.`;
  }

  function searchableText(name) {
    const module = modules[name];
    const definitions = [...module.public_interface, ...module.implementation];
    const symbols = [];
    definitions.forEach(item => {
      symbols.push(item.name);
      (item.members || []).forEach(member => symbols.push(member.qualified_name));
    });
    return `${name} ${module.summary} ${symbols.join(" ")}`.toLowerCase();
  }
  const searchIndex = Object.keys(modules).map(name => ({ name, text: searchableText(name) }));

  function renderSearch() {
    const query = search.value.trim().toLowerCase();
    searchResults.replaceChildren();
    if (query.length < 2) { searchResults.hidden = true; return; }
    const matches = searchIndex.filter(item => item.text.includes(query)).slice(0, 30);
    if (!matches.length) {
      const empty = document.createElement("div");
      empty.className = "empty"; empty.textContent = "No module or symbol matched.";
      searchResults.append(empty);
    } else {
      matches.forEach(item => {
        const module = modules[item.name];
        const button = document.createElement("button");
        button.type = "button"; button.className = "search-result";
        button.innerHTML = `${escapeText(module.short_name)}<small>${escapeText(groupOf(item.name).label)} · ${escapeText(module.summary || module.path)}</small>`;
        button.addEventListener("click", () => { openModule(item.name); searchResults.hidden = true; });
        searchResults.append(button);
      });
    }
    searchResults.hidden = false;
  }

  search.addEventListener("input", renderSearch);
  search.addEventListener("keydown", event => { if (event.key === "Escape") searchResults.hidden = true; });
  document.addEventListener("click", event => { if (!event.target.closest(".search-wrap")) searchResults.hidden = true; });
  allEdges.addEventListener("change", drawEdges);
  new ResizeObserver(drawEdges).observe(graphShell);

  const hash = decodeURIComponent(location.hash.slice(1));
  if (hash.startsWith("module=") && modules[hash.slice(7)]) openModule(hash.slice(7));
  else if (hash.startsWith("group=") && groups.has(hash.slice(6))) openGroup(hash.slice(6));
  else openOverview();
})();
"""


_INDEX_SCRIPT_V2 = r"""
(() => {
  "use strict";
  const read = id => JSON.parse(document.getElementById(id).textContent);
  const data = read("architecture-data");
  const overlays = read("overlay-data");
  const comparison = read("comparison-data");
  const check = read("check-data");
  data.groups.forEach(group => {
    if (!Array.isArray(group.children)) group.children = [];
    if (!Array.isArray(group.direct_modules)) group.direct_modules = group.modules || [];
    if (!Array.isArray(group.path)) group.path = [group.id];
    if (group.parent === undefined) group.parent = null;
  });
  const modules = data.modules;
  const groups = new Map(data.groups.map(group => [group.id, group]));
  const roots = data.top_level_groups || data.groups.filter(group => !group.parent).map(group => group.id);
  const graphShell = document.getElementById("graph-shell");
  const nodeRoot = document.getElementById("nodes");
  const edgeRoot = document.getElementById("edges");
  const detailRoot = document.getElementById("detail");
  const titleRoot = document.getElementById("graph-title");
  const captionRoot = document.getElementById("graph-caption");
  const breadcrumbs = document.getElementById("breadcrumbs");
  const allEdges = document.getElementById("all-edges");
  const edgeControl = document.getElementById("edge-control");
  const search = document.getElementById("search");
  const searchResults = document.getElementById("search-results");
  const live = document.getElementById("live");
  const state = { container: null, selected: null, projectedEdges: [] };

  function escapeText(value) {
    const span = document.createElement("span");
    span.textContent = value == null ? "" : String(value);
    return span.innerHTML;
  }
  function setHash(value) {
    if (history.replaceState) history.replaceState(null, "", value ? `#${value}` : location.pathname);
  }
  function groupOf(name) { return groups.get(modules[name].group); }
  function topGroup(groupId) {
    let group = groups.get(groupId);
    while (group && group.parent) group = groups.get(group.parent);
    return group;
  }
  function immediateGroup(groupId, containerId) {
    let group = groups.get(groupId);
    while (group && group.parent && group.parent !== containerId) group = groups.get(group.parent);
    return group;
  }
  function descendants(containerId) {
    return new Set(groups.get(containerId).modules || []);
  }
  function overlayDocuments(kind) {
    return (overlays.documents || []).filter(document => document.kind === kind);
  }
  function overlayRecords(kind, moduleName) {
    return overlayDocuments(kind).flatMap(document =>
      (document.records || []).filter(record => record.module === moduleName).map(record => ({...record, lane: document.lane, document}))
    );
  }
  function moduleChange(name) {
    if (!comparison) return [];
    const badges = [];
    if ((comparison.modules.added || []).includes(name)) badges.push("added");
    if ((comparison.modules.source_changed || []).includes(name)) badges.push("changed");
    if ((comparison.modules.moved || []).some(item => item.module === name)) badges.push("moved");
    return badges;
  }
  function badgeHtml(value, css="") { return `<span class="badge ${css}">${escapeText(value)}</span>`; }

  function groupButton(group, stub=false) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "node" + (stub ? " stub" : "");
    button.dataset.nodeId = `g:${group.id}`;
    button.setAttribute("aria-label", `${group.label}: ${group.module_count} modules`);
    button.innerHTML = `<span class="node-name">${escapeText(group.label)}</span><span class="node-meta">${stub ? "Outside this area · " : ""}${group.module_count} modules · ${group.line_count.toLocaleString()} lines<br>${group.children.length} subareas · ${group.direct_modules.length} direct</span>`;
    button.addEventListener("click", () => openGroup(group.id));
    return button;
  }
  function moduleButton(name, stub=false) {
    const module = modules[name];
    const violations = module.contract_violations || [];
    const changes = moduleChange(name);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "node" + (state.selected === name ? " selected" : "") + (module.cycle ? " cycle" : "") + (stub ? " stub" : "") + (violations.length ? " violation" : "");
    button.dataset.nodeId = `m:${name}`;
    button.setAttribute("aria-label", `${module.short_name}: ${module.imports.length} dependencies, ${module.imported_by.length} dependents`);
    const flags = [
      stub ? badgeHtml(`Outside · ${groupOf(name).label}`) : "",
      violations.length ? badgeHtml(`${violations.length} violation`, "bad") : "",
      ...changes.map(value => badgeHtml(value, "changed")),
    ].join("");
    button.innerHTML = `<span class="node-name">${escapeText(module.short_name)}</span><span class="node-meta">${module.line_count.toLocaleString()} lines · ${module.public_interface.length} public<br>imports ${module.imports.length} · used by ${module.imported_by.length}<br>${flags}</span>`;
    button.addEventListener("click", () => openModule(name));
    return button;
  }

  function renderBreadcrumbs() {
    breadcrumbs.replaceChildren();
    const home = document.createElement("button");
    home.type = "button"; home.className = "crumb"; home.textContent = data.package;
    home.addEventListener("click", openOverview); breadcrumbs.append(home);
    if (state.container) {
      const path = groups.get(state.container).path || [state.container];
      path.forEach(id => {
        breadcrumbs.append(document.createTextNode(" / "));
        const control = document.createElement("button");
        control.type = "button"; control.className = "crumb"; control.textContent = groups.get(id).label;
        control.addEventListener("click", () => openGroup(id)); breadcrumbs.append(control);
      });
    }
    if (state.selected) {
      breadcrumbs.append(document.createTextNode(" / "));
      const current = document.createElement("span"); current.textContent = modules[state.selected].short_name; breadcrumbs.append(current);
    }
  }

  function comparisonHtml() {
    if (!comparison) return "";
    const summary = comparison.summary;
    const list=(items,render,limit=100)=>items.length?`<ul class="provenance">${items.slice(0,limit).map(item=>`<li>${render(item)}</li>`).join("")}</ul>${items.length>limit?`<p class="muted">Showing ${limit} of ${items.length}.</p>`:""}`:`<p class="muted">None.</p>`;
    const publicChanges=list(comparison.public_interfaces||[],item=>`${escapeText(item.module)} · +${item.added.length} / -${item.removed.length}`);
    const addedEdges=list(comparison.dependencies.added||[],item=>`${escapeText(item.source)} → ${escapeText(item.target)} · ${(item.occurrences||[]).length} occurrences`);
    const removedEdges=list(comparison.dependencies.removed||[],item=>`${escapeText(item.source)} → ${escapeText(item.target)} · ${(item.occurrences||[]).length} occurrences`);
    const changedEdges=list(comparison.dependencies.changed||[],item=>`${escapeText(item.source)} → ${escapeText(item.target)} · provenance or symbols changed`);
    const groupMetrics=list(comparison.group_metrics||[],item=>`${escapeText(item.group)} · ${escapeText(JSON.stringify(item.before))} → ${escapeText(JSON.stringify(item.after))}`);
    const moduleMetrics=list(comparison.module_metrics||[],item=>`${escapeText(item.module)} · ${escapeText(JSON.stringify(item.before))} → ${escapeText(JSON.stringify(item.after))}`);
    const cyclesAdded=list(comparison.cycles.added||[],item=>escapeText(item.join(" → "))), cyclesRemoved=list(comparison.cycles.removed||[],item=>escapeText(item.join(" → ")));
    const violationsAdded=list(comparison.violations.added||[],item=>`${escapeText(item.contract)} · ${escapeText(item.source)} → ${escapeText(item.target)}`), violationsResolved=list(comparison.violations.resolved||[],item=>`${escapeText(item.contract)} · ${escapeText(item.source)} → ${escapeText(item.target)}`);
    return `<details><summary>Changes from bound snapshot</summary><p class="hash">Before ${escapeText(comparison.before.source_tree_sha256 || "unknown")}</p><p>${badgeHtml(`${summary.modules_added} modules added`, "changed")}${badgeHtml(`${summary.modules_removed} removed`, "changed")}${badgeHtml(`${summary.dependencies_added} edges added`, "changed")}${badgeHtml(`${summary.dependencies_removed} removed`, "changed")}${badgeHtml(`${summary.dependencies_changed||0} edge evidence changed`, "changed")}${badgeHtml(`${summary.cycles_added} cycles added`, summary.cycles_added ? "bad" : "good")}${badgeHtml(`${summary.violations_added} violations added`, summary.violations_added ? "bad" : "good")}</p><details><summary>Added modules</summary>${list(comparison.modules.added_details||[],item=>`${escapeText(item.module)} · ${escapeText(item.group)} · ${escapeText(item.path)}`)}</details><details><summary>Removed modules</summary>${list(comparison.modules.removed_details||[],item=>`${escapeText(item.module)} · ${escapeText(item.group)} · ${escapeText(item.path)}`)}</details><details><summary>Public interface changes</summary>${publicChanges}</details><details><summary>Added dependencies</summary>${addedEdges}</details><details><summary>Removed dependencies</summary>${removedEdges}</details><details><summary>Changed dependency evidence</summary>${changedEdges}</details><details><summary>Group metric changes</summary>${groupMetrics}</details><details><summary>Module metric changes</summary>${moduleMetrics}</details><details><summary>Cycles added / removed</summary><h3>Added</h3>${cyclesAdded}<h3>Removed</h3>${cyclesRemoved}</details><details><summary>Violations added / resolved</summary><h3>Added</h3>${violationsAdded}<h3>Resolved</h3>${violationsResolved}</details></details>`;
  }
  function overlaySummaryHtml() {
    const documents=overlays.documents||[], records=documents.flatMap(document=>(document.records||[]).map(record=>({...record,kind:document.kind,lane:document.lane})));
    const stale=records.filter(record=>record.attachment&&record.attachment!=="current"), diagnostics=overlays.diagnostics||[];
    if(!documents.length)return `<details><summary>Overlay inventory</summary><p class="muted">No optional evidence reports attached.</p></details>`;
    return `<details><summary>Overlay inventory</summary>${documents.map(document=>`<div class="dependency">${badgeHtml(document.kind)}${badgeHtml(document.lane)}<small>${(document.records||[]).length} records${document.run_status?` · run ${escapeText(document.run_status)}`:""}${document.binding?` · ${escapeText(document.binding)}`:""}</small></div>`).join("")}<p>${badgeHtml(`${stale.length} non-current attachments`,stale.length?"bad":"good")}${badgeHtml(`${diagnostics.length} diagnostics`,diagnostics.length?"bad":"good")}</p>${stale.slice(0,100).map(record=>`<div class="dependency"><small>${escapeText(record.kind)} · ${escapeText(record.lane)} · ${escapeText(record.module)} · ${escapeText(record.attachment)}</small></div>`).join("")}</details>`;
  }
  function systemHtml() {
    const semantic = overlayDocuments("semantics")[0];
    if (!semantic || !semantic.system) return "";
    const nodes = semantic.system.nodes || [];
    const relationships = semantic.system.relationships || [];
    return `<details><summary>Declared system and runtime context</summary><p class="muted">Maintained intent, not observed runtime evidence.</p><div class="system-list">${nodes.map(node => `<div class="system-item"><strong>${escapeText(node.label)}</strong><br><small>${escapeText(node.type)} · ${escapeText(node.description)}</small></div>`).join("")}</div>${relationships.map(edge => `<div class="dependency"><small>${escapeText(edge.source)} → ${escapeText(edge.target)} · ${escapeText(edge.label)}</small></div>`).join("")}</details>`;
  }
  function renderOverviewDetail() {
    const failed = check && check.status === "failed", sourceErrors=(check&&check.parse_errors||[]).length, testErrors=(check&&check.test_parse_errors||[]).length;
    detailRoot.innerHTML = `<p class="eyebrow">How to read this</p><h2>System areas</h2><p>Each node is a configured architectural container. Arrows aggregate source-bound Python imports; open a container to reach subareas and code.</p><p class="notice ${failed ? "" : "good"}">${failed ? `${check.violations.length} contract violations, ${sourceErrors} source parse errors and ${testErrors} test parse errors.` : `${(check.contracts || []).length} architecture contracts pass; no parse errors.`}</p><div class="detail-grid"><div class="detail-metric"><strong>${data.stats.internal_dependency_count.toLocaleString()}</strong><span>module relationships</span></div><div class="detail-metric"><strong>${data.stats.internal_import_occurrence_count.toLocaleString()}</strong><span>import occurrences</span></div><div class="detail-metric"><strong>${data.stats.static_call_relation_count.toLocaleString()}</strong><span>static call candidates</span></div><div class="detail-metric"><strong>${data.stats.test_dependency_count || 0}</strong><span>test import links</span></div></div><p class="muted">Static candidates and annotations are evidence for review. They do not authorize a refactor, model run, render or musical selection.</p>${comparisonHtml()}${overlaySummaryHtml()}${systemHtml()}`;
  }
  function renderGroupDetail(group) {
    const members = new Set(group.modules);
    let incoming = 0, outgoing = 0;
    Object.entries(modules).forEach(([source, module]) => module.imports.forEach(edge => {
      const sourceInside = members.has(source), targetInside = members.has(edge.module);
      if (sourceInside && !targetInside) outgoing += 1;
      if (!sourceInside && targetInside) incoming += 1;
    }));
    const effects=[...members].flatMap(name=>modules[name].effects||[]), effectKinds=[...new Set(effects.map(item=>item.kind))].sort();
    const crossings=[]; Object.entries(modules).forEach(([source,module])=>module.imports.forEach(edge=>{const sourceInside=members.has(source),targetInside=members.has(edge.module);if(sourceInside!==targetInside)crossings.push(`${source} → ${edge.module}`);}));
    detailRoot.innerHTML = `<p class="eyebrow">Architecture container</p><h2>${escapeText(group.label)}</h2><p>${escapeText(group.description)}</p><div class="detail-grid"><div class="detail-metric"><strong>${group.module_count}</strong><span>recursive modules</span></div><div class="detail-metric"><strong>${group.direct_modules.length}</strong><span>direct modules</span></div><div class="detail-metric"><strong>${outgoing}</strong><span>outgoing boundaries</span></div><div class="detail-metric"><strong>${incoming}</strong><span>incoming boundaries</span></div><div class="detail-metric"><strong>${effects.length}</strong><span>static effect candidates</span></div><div class="detail-metric"><strong>${effectKinds.length}</strong><span>effect categories</span></div></div><p class="muted">${group.children.length ? "Choose a subarea to reduce context before opening code." : "Choose a module to inspect exact interfaces and relationships."}</p><details><summary>Boundary relationships (${crossings.length})</summary>${crossings.slice(0,200).map(item=>`<div class="dependency"><small>${escapeText(item)}</small></div>`).join("")}${crossings.length>200?`<p class="muted">Showing 200 of ${crossings.length}.</p>`:""}</details><details><summary>Static effect candidates (${effects.length})</summary><p class="muted">Candidate categories: ${escapeText(effectKinds.join(", ")||"none")}. These are not proof of runtime effects or authority.</p></details>`;
  }

  function definitionHtml(definition, module) {
    const members = definition.members && definition.members.length ? `<div class="members">${definition.members.map(member => definitionHtml(member, module)).join("")}</div>` : "";
    return `<div class="definition"><a href="${escapeText(module.code_page)}#L${definition.line}">${escapeText(definition.signature || definition.qualified_name)}</a><small>${escapeText(definition.kind)} · lines ${definition.line}–${definition.end_line}</small>${definition.summary ? `<small>${escapeText(definition.summary)}</small>` : ""}${members}</div>`;
  }
  function occurrencesHtml(sourceModule, occurrences) {
    if (!occurrences || !occurrences.length) return `<small>Legacy snapshot: occurrence provenance unavailable.</small>`;
    return `<ul class="provenance">${occurrences.map(item => `<li><a href="${escapeText(sourceModule.code_page)}#L${item.line}">lines ${item.line}–${item.end_line||item.line}</a> · ${escapeText(item.kind)} · requested ${escapeText(item.requested||"unknown")} · ${escapeText((item.symbols||[]).join(", ")||"module")} · ${escapeText(item.runtime)} · ${escapeText(item.guard)} · ${escapeText(item.scope)} · ${escapeText(item.confidence)}</li>`).join("")}</ul>`;
  }
  function importHtml(sourceName, dependency) {
    const target = modules[dependency.module];
    return `<div class="dependency"><button class="relation" data-module="${escapeText(dependency.module)}">${escapeText(target.short_name)}</button><small>${escapeText(groupOf(dependency.module).label)}${dependency.symbols.length ? ` · symbols: ${escapeText(dependency.symbols.join(", "))}` : " · module import"}</small>${occurrencesHtml(modules[sourceName], dependency.occurrences)}</div>`;
  }
  function incomingHtml(targetName, sourceName) {
    const dependency = modules[sourceName].imports.find(item => item.module === targetName);
    return `<div class="dependency"><button class="relation" data-module="${escapeText(sourceName)}">${escapeText(modules[sourceName].short_name)}</button><small>${escapeText(groupOf(sourceName).label)} · imports this module</small>${occurrencesHtml(modules[sourceName], dependency ? dependency.occurrences : [])}</div>`;
  }
  function semanticHtml(name) {
    const records = overlayRecords("semantics", name);
    if (!records.length) return `<p class="muted">No maintained semantic annotation.</p>`;
    return records.map(record => `<div class="dependency">${badgeHtml(record.claim_kind)}${badgeHtml(record.attachment, record.attachment === "current" ? "good" : "bad")}<p>${escapeText(record.responsibility)}</p><small>Roles: ${escapeText(record.roles.join(", ") || "none")} · Surface: ${escapeText(record.surface)} · Stability: ${escapeText(record.stability)}</small>${record.supported_entry_points.length ? `<small>Supported entry points: ${escapeText(record.supported_entry_points.join("; "))}</small>` : ""}${record.inputs.length ? `<small>Inputs: ${escapeText(record.inputs.join("; "))}</small>` : ""}${record.outputs.length ? `<small>Outputs: ${escapeText(record.outputs.join("; "))}</small>` : ""}${record.knowledge_owned.length ? `<small>Knowledge hidden: ${escapeText(record.knowledge_owned.join("; "))}</small>` : ""}${record.caller_obligations.length ? `<small>Caller obligations: ${escapeText(record.caller_obligations.join("; "))}</small>` : ""}${record.side_effects.length ? `<small>Effects: ${escapeText(record.side_effects.join("; "))}</small>` : ""}${record.errors.length ? `<small>Errors: ${escapeText(record.errors.join("; "))}</small>` : ""}${record.schemas.length ? `<small>Schemas: ${escapeText(record.schemas.join("; "))}</small>` : ""}${record.authority_boundary ? `<small>Authority: ${escapeText(record.authority_boundary)}</small>` : ""}</div>`).join("");
  }
  function qualityHtml(name) {
    const records = [
      ...overlayRecords("risk", name).map(record => `<div class="dependency">${badgeHtml(record.status === "not_applicable" ? "CRAP n/a" : `CRAP ${record.crap_score ?? "unmeasured"}`, record.status === "warning" ? "bad" : record.status === "ok" ? "good" : "")}${badgeHtml(record.attachment, record.attachment === "current" ? "good" : "bad")}<small>${escapeText(record.qualified_name)} · complexity ${record.complexity} · coverage ${record.status === "not_applicable" ? "n/a" : `${record.coverage_percentage ?? "unmeasured"}%`} · line ${record.line}</small></div>`),
      ...overlayRecords("coverage", name).map(record => `<div class="dependency">${badgeHtml("coverage")}${badgeHtml(record.attachment, record.attachment === "current" ? "good" : "bad")}<small>${escapeText(JSON.stringify(record.summary))}</small></div>`),
      ...overlayRecords("mutation", name).map(record => `<div class="dependency">${badgeHtml(record.status, record.status === "survived" ? "bad" : record.status === "killed" ? "good" : "")}${badgeHtml(record.equivalence?.classification || "not reviewed", record.equivalence?.classification === "test_gap" ? "bad" : "")}${badgeHtml(record.attachment, record.attachment === "current" ? "good" : "bad")}${badgeHtml(`run ${record.document.run_status}`)}<small>${escapeText(record.qualified_name || "module")}: ${escapeText(record.operator)} at line ${record.line}. ${escapeText(record.equivalence?.rationale || "Equivalence has not been reviewed.")}</small></div>`),
    ];
    return records.length ? records.join("") : `<p class="muted">No coverage, CRAP or mutation report attached. Static complexity alone is not CRAP.</p>`;
  }
  function runtimeHtml(name, module) {
    const declared = overlayRecords("runtime_effects", name);
    const observed = module.effects || [];
    const declaredHtml = declared.length ? declared.map(record => `<div class="dependency">${badgeHtml("declared policy")}${badgeHtml(record.attachment, record.attachment === "current" ? "good" : "bad")}<small>${escapeText(JSON.stringify(record.declared_policy))}</small><small>Bounded observations: ${escapeText(JSON.stringify(record.observations))}</small></div>`).join("") : `<p class="muted">No source-bound runtime policy/observation report attached.</p>`;
    const observedHtml = observed.length ? observed.slice(0, 200).map(item => `<div class="dependency"><small><a href="${escapeText(module.code_page)}#L${item.line}">line ${item.line}</a> · ${escapeText(item.kind)} candidate · ${escapeText(item.operation)} · ${escapeText(item.scope)}</small></div>`).join("") : `<p class="muted">No known effect-call candidates detected.</p>`;
    return `${declaredHtml}<p class="muted">Static call candidates below are not proof that an effect occurs. Absence means unknown, not effect-free.</p>${observedHtml}`;
  }
  function relationList(records, module) {
    if (!records.length) return `<p class="muted">None detected.</p>`;
    const shown = records.slice(0, 250).map(record => `<div class="dependency"><button class="relation" data-module="${escapeText(record.target_module)}">${escapeText(record.target_module)}${record.target_symbol ? `.${escapeText(record.target_symbol)}` : ""}</button><small>${escapeText(record.kind)} · from ${escapeText(record.source_definition || record.source_symbol || "module")} · <a href="${escapeText(module.code_page)}#L${record.line}">line ${record.line}</a> · ${escapeText(record.confidence)}</small></div>`).join("");
    return shown + (records.length > 250 ? `<p class="muted">Showing 250 of ${records.length} static candidates.</p>` : "");
  }
  function agentQuery(name, module) {
    return `Inspect Sunofriend module ${name}.\nSource: ${module.path}\nSource SHA-256: ${module.source_sha256}\nArchitecture SHA-256: ${data.architecture_sha256 || "unavailable"}\nTree SHA-256: ${data.source_tree_sha256}\nGroup path: ${(module.group_path || []).join(" > ")}\nStart with its public interface, exact import occurrences, contract violations, tests, semantic intent and stale/current overlay states. Treat static calls/effects as candidates, not runtime proof. Do not infer musical approval or execution authority.`;
  }

  function renderModuleDetail(name) {
    const module = modules[name];
    const imports = module.imports.length ? module.imports.map(item => importHtml(name, item)).join("") : `<p class="muted">No internal imports detected.</p>`;
    const importedBy = module.imported_by.length ? module.imported_by.map(item => incomingHtml(name, item)).join("") : `<p class="muted">No internal importers detected.</p>`;
    const publicDefinitions = module.public_interface.length ? module.public_interface.map(item => definitionHtml(item, module)).join("") : `<p class="muted">No public top-level functions or classes detected.</p>`;
    const privateDefinitions = module.implementation.length ? module.implementation.map(item => definitionHtml(item, module)).join("") : `<p class="muted">No private top-level functions or classes detected.</p>`;
    const violations = module.contract_violations || [];
    const violationHtml = violations.length ? `<p class="notice">${violations.length} enforced architecture violation${violations.length === 1 ? "" : "s"}.</p>${violations.map(item => `<div class="dependency">${badgeHtml(item.contract, "bad")}<small>${escapeText(item.message)} · ${escapeText(item.source)} → ${escapeText(item.target)}</small>${occurrencesHtml(module, item.occurrences)}</div>`).join("")}` : `<p class="notice good">No configured contract violation originates here.</p>`;
    const testHtml = (module.tested_by || []).length ? module.tested_by.map(item => `<div class="dependency"><small>${escapeText(item.path)} · imports at lines ${escapeText(item.lines.join(", "))} · ${item.test_function_count} test functions in file</small></div>`).join("") : `<p class="muted">No production import from the scanned test tree was detected.</p>`;
    const externalHtml = (module.external_import_details || []).length ? module.external_import_details.map(item => `<div class="dependency"><strong>${escapeText(item.root)}</strong>${occurrencesHtml(module,item.occurrences)}</div>`).join("") : `<p class="muted">None detected.</p>`;
    const query = escapeText(agentQuery(name, module));
    const calls = module.calls || [], types = module.types || [];
    detailRoot.innerHTML = `<p class="eyebrow">Module · ${escapeText((module.group_path || [module.group]).map(id => groups.get(id).label).join(" / "))}</p><h2><code>${escapeText(module.short_name)}</code></h2><p>${escapeText(module.summary || "No module docstring summary.")}</p><p class="path">${escapeText(module.path)}</p>${module.cycle ? `<p class="notice">Static import cycle ${module.cycle}. Occurrence scope and guards determine its runtime significance.</p>` : ""}${module.parse_error ? `<p class="notice">AST parsing failed: ${escapeText(module.parse_error)}</p>` : ""}${violationHtml}<div class="detail-grid"><div class="detail-metric"><strong>${module.public_interface.length}</strong><span>public definitions</span></div><div class="detail-metric"><strong>${module.implementation.length}</strong><span>private definitions</span></div><div class="detail-metric"><strong>${module.imports.length}</strong><span>internal relationships</span></div><div class="detail-metric"><strong>${module.imported_by.length}</strong><span>internal importers</span></div></div><p><a class="action" href="${escapeText(module.code_page)}">Open complete source</a></p><details open><summary>Public interface (${escapeText(module.interface_source)})</summary>${publicDefinitions}</details><details><summary>Implementation definitions</summary>${privateDefinitions}</details><details><summary>Internal dependencies and provenance</summary>${imports}</details><details><summary>Imported by and provenance</summary>${importedBy}</details><details><summary>Semantic interface and deep-module intent</summary>${semanticHtml(name)}</details><details><summary>Coverage, CRAP and mutation</summary>${qualityHtml(name)}</details><details><summary>Runtime policy and effect candidates</summary>${runtimeHtml(name, module)}</details><details><summary>Static calls and construction (${calls.length})</summary>${relationList(calls, module)}</details><details><summary>Static type relationships (${types.length})</summary>${relationList(types, module)}</details><details><summary>Tests importing this module (${(module.tested_by || []).length})</summary>${testHtml}</details><details><summary>External import roots and provenance</summary>${externalHtml}</details><details><summary>Copy context for an agent</summary><textarea id="agent-query" class="agent-query" readonly>${query}</textarea><button id="copy-query" class="copy-button" type="button">Copy agent query</button><p id="copy-status" class="muted" aria-live="polite"></p></details><details><summary>Identity</summary><p class="hash">SHA-256 ${escapeText(module.source_sha256)}</p></details>`;
    detailRoot.querySelectorAll("[data-module]").forEach(button => button.addEventListener("click", () => openModule(button.dataset.module)));
    const copyButton = document.getElementById("copy-query");
    if (copyButton) copyButton.addEventListener("click", async () => {
      const textarea = document.getElementById("agent-query");
      let copied = false;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        try { await navigator.clipboard.writeText(textarea.value); copied = true; } catch (_) { copied = false; }
      }
      if (!copied) { textarea.focus(); textarea.select(); copied = document.execCommand && document.execCommand("copy"); }
      document.getElementById("copy-status").textContent = copied ? "Agent query copied." : "Copy was blocked; the text is selected for manual copy.";
    });
  }

  function overviewProjection() {
    const totals = new Map();
    Object.entries(modules).forEach(([source, module]) => module.imports.forEach(edge => {
      const a = topGroup(module.group), b = topGroup(modules[edge.module].group);
      if (!a || !b || a.id === b.id) return;
      const key = `${a.id}\u0000${b.id}`; totals.set(key, (totals.get(key) || 0) + 1);
    }));
    return [...totals].map(([key, count]) => { const [a,b] = key.split("\u0000"); return {source:`g:${a}`, target:`g:${b}`, count}; });
  }
  function groupProjection(group) {
    const members = descendants(group.id), totals = new Map();
    function bucket(name) {
      const module = modules[name];
      if (!members.has(name)) return `g:${module.group}`;
      const immediate = immediateGroup(module.group, group.id);
      return immediate && immediate.id !== group.id ? `g:${immediate.id}` : `m:${name}`;
    }
    Object.entries(modules).forEach(([source, module]) => module.imports.forEach(edge => {
      const sourceInside=members.has(source), targetInside=members.has(edge.module);
      if (!sourceInside && !targetInside) return;
      const a=bucket(source), b=bucket(edge.module); if (a===b) return;
      if (sourceInside && targetInside && !allEdges.checked && !group.children.length) return;
      const key=`${a}\u0000${b}`; totals.set(key,(totals.get(key)||0)+1);
    }));
    return [...totals].map(([key,count])=>{const [a,b]=key.split("\u0000"); return {source:a,target:b,count};});
  }
  function boundaryGroups(group) {
    const members=descendants(group.id), ids=new Set();
    Object.entries(modules).forEach(([source,module])=>module.imports.forEach(edge=>{
      const sourceInside=members.has(source), targetInside=members.has(edge.module);
      if(sourceInside&&!targetInside)ids.add(modules[edge.module].group);
      if(!sourceInside&&targetInside)ids.add(module.group);
    }));
    return [...ids].filter(id=>groups.has(id)&&!group.children.includes(id)).sort();
  }
  function selectedProjection(name) {
    const edges=[];
    modules[name].imports.forEach(edge => edges.push({source:`m:${name}`,target:`m:${edge.module}`,count:(edge.occurrences||[]).length||1}));
    modules[name].imported_by.forEach(source => {
      const edge=modules[source].imports.find(item=>item.module===name);
      edges.push({source:`m:${source}`,target:`m:${name}`,count:edge && edge.occurrences ? edge.occurrences.length : 1});
    });
    return edges;
  }
  function drawEdges() {
    edgeRoot.replaceChildren();
    const shellBox=graphShell.getBoundingClientRect(), width=Math.max(1,graphShell.clientWidth), height=Math.max(1,graphShell.clientHeight);
    edgeRoot.setAttribute("viewBox",`0 0 ${width} ${height}`);
    const defs=document.createElementNS("http://www.w3.org/2000/svg","defs"); defs.innerHTML=`<marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke"></path></marker>`; edgeRoot.append(defs);
    state.projectedEdges.forEach(edge=>{
      const source=nodeRoot.querySelector(`[data-node-id="${CSS.escape(edge.source)}"]`), target=nodeRoot.querySelector(`[data-node-id="${CSS.escape(edge.target)}"]`); if(!source||!target||source===target)return;
      const a=source.getBoundingClientRect(),b=target.getBoundingClientRect(),x1=a.left+a.width/2-shellBox.left,y1=a.top+a.height/2-shellBox.top,x2=b.left+b.width/2-shellBox.left,y2=b.top+b.height/2-shellBox.top,dx=x2-x1,dy=y2-y1,length=Math.max(1,Math.hypot(dx,dy)),sp=Math.min(a.width,a.height)*.36,ep=Math.min(b.width,b.height)*.43;
      const line=document.createElementNS("http://www.w3.org/2000/svg","line"); const direction=state.selected&&edge.source===`m:${state.selected}`?" outgoing":state.selected&&edge.target===`m:${state.selected}`?" incoming":""; line.setAttribute("class",`edge${direction}`); line.setAttribute("x1",x1+dx/length*sp); line.setAttribute("y1",y1+dy/length*sp); line.setAttribute("x2",x2-dx/length*ep); line.setAttribute("y2",y2-dy/length*ep); line.setAttribute("marker-end","url(#arrow)"); const title=document.createElementNS("http://www.w3.org/2000/svg","title"); title.textContent=`${edge.source} imports ${edge.target} (${edge.count})`; line.append(title); edgeRoot.append(line);
    });
  }
  function renderGraph() {
    nodeRoot.replaceChildren();
    if (!state.container) {
      titleRoot.textContent="System overview"; captionRoot.textContent="Configured top-level containers and aggregate import direction.";
      roots.forEach(id=>nodeRoot.append(groupButton(groups.get(id)))); state.projectedEdges=overviewProjection(); edgeControl.hidden=true; renderOverviewDetail();
    } else {
      const group=groups.get(state.container); titleRoot.textContent=group.label; captionRoot.textContent=`${group.module_count} recursive modules · ${group.children.length} subareas · ${group.direct_modules.length} direct modules.`;
      group.children.forEach(id=>nodeRoot.append(groupButton(groups.get(id)))); group.direct_modules.forEach(name=>nodeRoot.append(moduleButton(name)));
      if(state.selected){
        const local=new Set(group.direct_modules); const neighbours=new Set([...modules[state.selected].imported_by,...modules[state.selected].imports.map(item=>item.module)]); [...neighbours].filter(name=>!local.has(name)).sort().forEach(name=>nodeRoot.append(moduleButton(name,true)));
        state.projectedEdges=selectedProjection(state.selected); renderModuleDetail(state.selected);
      } else { boundaryGroups(group).forEach(id=>nodeRoot.append(groupButton(groups.get(id),true))); state.projectedEdges=groupProjection(group); renderGroupDetail(group); }
      edgeControl.hidden=!!state.selected || !!group.children.length;
    }
    renderBreadcrumbs(); requestAnimationFrame(drawEdges);
  }
  function openOverview(){state.container=null;state.selected=null;setHash("");renderGraph();live.textContent="Showing the system overview.";}
  function openGroup(id){if(!groups.has(id))return;state.container=id;state.selected=null;setHash(`group=${encodeURIComponent(id)}`);renderGraph();live.textContent=`Showing ${groups.get(id).label}.`;}
  function openModule(name){if(!modules[name])return;state.container=modules[name].group;state.selected=name;setHash(`module=${encodeURIComponent(name)}`);renderGraph();const selected=nodeRoot.querySelector(`[data-node-id="${CSS.escape(`m:${name}`)}"]`);if(selected)selected.scrollIntoView({block:"nearest",behavior:"smooth"});live.textContent=`Showing module ${modules[name].short_name}.`;}
  function searchableText(name){const module=modules[name],definitions=[...module.public_interface,...module.implementation],symbols=[];definitions.forEach(item=>{symbols.push(item.name);(item.members||[]).forEach(member=>symbols.push(member.qualified_name));});return `${name} ${module.summary} ${symbols.join(" ")}`.toLowerCase();}
  const searchIndex=Object.keys(modules).map(name=>({name,text:searchableText(name)}));
  function renderSearch(){const query=search.value.trim().toLowerCase();searchResults.replaceChildren();if(query.length<2){searchResults.hidden=true;return;}const matches=searchIndex.filter(item=>item.text.includes(query)).slice(0,30);if(!matches.length){const empty=document.createElement("div");empty.className="empty";empty.textContent="No module or symbol matched.";searchResults.append(empty);}else matches.forEach(item=>{const module=modules[item.name],button=document.createElement("button");button.type="button";button.className="search-result";button.innerHTML=`${escapeText(module.short_name)}<small>${escapeText(groupOf(item.name).label)} · ${escapeText(module.summary||module.path)}</small>`;button.addEventListener("click",()=>{openModule(item.name);searchResults.hidden=true;});searchResults.append(button);});searchResults.hidden=false;}
  search.addEventListener("input",renderSearch);search.addEventListener("keydown",event=>{if(event.key==="Escape")searchResults.hidden=true;});document.addEventListener("click",event=>{if(!event.target.closest(".search-wrap"))searchResults.hidden=true;});allEdges.addEventListener("change",renderGraph);if(typeof ResizeObserver!=="undefined")new ResizeObserver(drawEdges).observe(graphShell);
  const hash=decodeURIComponent(location.hash.slice(1));if(hash.startsWith("module=")&&modules[hash.slice(7)])openModule(hash.slice(7));else if(hash.startsWith("group=")&&groups.has(hash.slice(6)))openGroup(hash.slice(6));else openOverview();
})();
"""


_CODE_STYLE = r"""
:root { color-scheme: dark; --ink: #020617; --panel: #07102a; --line: #214166; --white: #f7fbff; --muted: #a9b9da; --cyan: #00e6ff; --acid: #dfff37; --mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace; }
* { box-sizing: border-box; }
html { scroll-padding-top: 80px; background: var(--ink); }
body { margin: 0; background: var(--ink); color: var(--white); font-family: ui-sans-serif, system-ui, sans-serif; }
a { color: var(--cyan); }
:focus-visible { outline: 3px solid var(--acid); outline-offset: 3px; }
header { position: sticky; z-index: 2; top: 0; display: flex; flex-wrap: wrap; gap: 12px 24px; align-items: baseline; justify-content: space-between; padding: 14px 20px; border-bottom: 1px solid var(--line); background: rgba(2, 6, 23, .96); }
h1 { margin: 0; font: 800 1rem var(--mono); overflow-wrap: anywhere; }
header p { margin: 4px 0 0; color: var(--muted); font-size: .78rem; }
.source { min-width: max-content; margin: 0; padding: 18px 0 40px 68px; background: var(--panel); font: .78rem/1.62 var(--mono); }
.source li { min-height: 1.62em; padding: 0 20px 0 12px; border-left: 1px solid transparent; white-space: pre; }
.source li::marker { color: #6f84a8; }
.source li:target { border-left-color: var(--acid); background: rgba(223, 255, 55, .10); }
.source a { color: inherit; text-decoration: none; }
"""


def _json_for_script(value: Any) -> str:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _index_html(
    architecture: Mapping[str, Any],
    *,
    overlays: Mapping[str, Any],
    comparison: Mapping[str, Any] | None,
    check: Mapping[str, Any],
) -> str:
    stats = architecture["stats"]
    data = _json_for_script(architecture)
    overlay_data = _json_for_script(overlays)
    comparison_data = _json_for_script(comparison)
    check_data = _json_for_script(check)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>Sunofriend architecture explorer</title><style>{_INDEX_STYLE}</style></head>
<body><main class="shell"><header class="masthead"><div><p class="eyebrow">Sunofriend developer map</p><h1>Architecture explorer</h1><p class="subtitle">Nested static architecture, exact import evidence, interfaces, contracts, tests and optional source-bound quality overlays. Generated without importing application code.</p></div><div class="hash" title="Source tree SHA-256">{html.escape(str(architecture['source_tree_sha256']))}</div></header>
<section class="stats" aria-label="Source summary"><div class="stat"><strong>{stats['module_count']:,}</strong><span>Python modules</span></div><div class="stat"><strong>{stats['line_count']:,}</strong><span>source lines</span></div><div class="stat"><strong>{stats['internal_dependency_count']:,}</strong><span>dependency relationships</span></div><div class="stat"><strong>{stats.get('internal_import_occurrence_count', stats['internal_dependency_count']):,}</strong><span>import occurrences</span></div><div class="stat"><strong>{stats['cycle_count']:,}</strong><span>static cycles</span></div><div class="stat"><strong>{stats.get('contract_violation_count', 0):,}</strong><span>contract violations</span></div><div class="stat"><strong>{stats['parse_error_count']:,}</strong><span>parse errors</span></div></section>
<section class="toolbar"><div class="search-wrap"><label for="search">Find a module or symbol</label><input id="search" type="search" autocomplete="off" placeholder="Try workbench, source_roles, validate…"><div id="search-results" class="search-results" hidden></div></div><label id="edge-control" class="switch" hidden><input id="all-edges" type="checkbox"> Show every relationship in this area</label></section>
<nav id="breadcrumbs" class="breadcrumbs" aria-label="Architecture location"></nav><div id="live" class="sr-only" aria-live="polite"></div>
<section class="workspace"><section class="graph-panel"><header class="panel-head"><div><h2 id="graph-title"></h2><p id="graph-caption"></p></div><div class="legend" aria-label="Dependency direction"><span class="incoming">imports selected</span><span class="outgoing">selected imports</span></div></header><div id="graph-shell" class="graph-shell"><svg id="edges" class="edges" aria-hidden="true"></svg><div id="nodes" class="nodes"></div></div></section><aside id="detail" class="detail-panel"></aside></section>
</main><script id="architecture-data" type="application/json">{data}</script><script id="overlay-data" type="application/json">{overlay_data}</script><script id="comparison-data" type="application/json">{comparison_data}</script><script id="check-data" type="application/json">{check_data}</script><script>{_INDEX_SCRIPT_V2}</script></body></html>
"""


def _code_html(module: Mapping[str, Any], source: str) -> str:
    lines = source.splitlines()
    if source.endswith("\n"):
        lines.append("")
    rendered_lines = "\n".join(
        f'<li id="L{number}"><a href="#L{number}" aria-label="Line {number}"><code>{html.escape(line)}</code></a></li>'
        for number, line in enumerate(lines, start=1)
    )
    module_hash = html.escape(str(module["source_sha256"]))
    module_name = html.escape(str(module["name"]))
    module_path = html.escape(str(module["path"]))
    back_link = "../index.html#module=" + html.escape(str(module["name"]), quote=True)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>{module_name} source</title><style>{_CODE_STYLE}</style></head><body>
<header><div><h1>{module_name}</h1><p>{module_path} · SHA-256 {module_hash}</p></div><a href="{back_link}">Back to module view</a></header>
<main><ol class="source">{rendered_lines}</ol></main></body></html>
"""


def _write_private(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def build_architecture_viewer(
    architecture: Mapping[str, Any],
    *,
    source_root: Path,
    repository_root: Path,
    output_root: Path,
    overlays: Mapping[str, Any] | None = None,
    comparison: Mapping[str, Any] | None = None,
    check: Mapping[str, Any] | None = None,
) -> Path:
    """Write one fresh, owner-readable static explorer and return its root."""

    source_root = source_root.resolve()
    repository_root = repository_root.resolve()
    output_root = output_root.resolve()
    try:
        relative_source_root = source_root.relative_to(repository_root)
    except ValueError as error:
        raise ValueError("source root must be inside repository root") from error
    if Path(str(architecture.get("source_root", ""))) != relative_source_root:
        raise ValueError("architecture document does not describe the supplied source root")
    if architecture.get("schema") == "sunofriend-architecture-viewer.v2" and architecture.get(
        "architecture_sha256"
    ) != calculate_architecture_sha256(architecture):
        raise ValueError("architecture document integrity hash differs")
    if output_root.exists():
        raise FileExistsError(f"output root already exists: {output_root}")
    expected_paths: set[str] = set()
    code_pages: set[str] = set()
    for module in architecture["modules"].values():
        path = Path(str(module["path"]))
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"unsafe module source path: {path}")
        source_path = repository_root / path
        try:
            source_path.resolve().relative_to(source_root)
        except ValueError as error:
            raise ValueError(f"module source resolves outside source root: {path}") from error
        expected_paths.add(path.as_posix())
        page = Path(str(module["code_page"])).name
        if page in code_pages:
            raise ValueError(f"duplicate generated code page: {page}")
        code_pages.add(page)
    current_paths: set[str] = set()
    for path in source_root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            path.resolve().relative_to(source_root)
        except ValueError as error:
            raise ValueError(f"source file resolves outside source root: {path}") from error
        current_paths.add(path.relative_to(repository_root).as_posix())
    if current_paths != expected_paths:
        raise ValueError("source tree changed after analysis")
    output_root.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_root.name}-", dir=output_root.parent))
    staging.chmod(0o700)
    published_root_created = False
    if overlays is None:
        overlays = {
            "schema": "sunofriend-architecture-overlays.v1",
            "base": {
                "architecture_schema": architecture.get("schema"),
                "package": architecture.get("package"),
                "source_root": architecture.get("source_root"),
                "source_tree_sha256": architecture.get("source_tree_sha256"),
                "architecture_sha256": architecture.get("architecture_sha256"),
            },
            "documents": [],
            "diagnostics": [],
        }
    if check is None:
        check = {
            "schema": "sunofriend-architecture-check.v1",
            "package": architecture.get("package"),
            "source_tree_sha256": architecture.get("source_tree_sha256"),
            "architecture_sha256": architecture.get("architecture_sha256"),
            "status": "failed"
            if architecture.get("violations")
            or architecture.get("parse_errors")
            or architecture.get("tests", {}).get("parse_errors")
            else "passed",
            "contracts": architecture.get("contracts", []),
            "violations": architecture.get("violations", []),
            "ignored_violations": architecture.get("ignored_violations", []),
            "parse_errors": architecture.get("parse_errors", []),
            "test_parse_errors": architecture.get("tests", {}).get("parse_errors", []),
        }
    try:
        code_root = staging / "code"
        code_root.mkdir(mode=0o700)
        _write_private(
            staging / "index.html",
            _index_html(
                architecture,
                overlays=overlays,
                comparison=comparison,
                check=check,
            ),
        )
        _write_private(
            staging / "architecture.json",
            json.dumps(architecture, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
        _write_private(
            staging / "architecture-check.json",
            json.dumps(check, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
        _write_private(
            staging / "overlays.json",
            json.dumps(overlays, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
        if comparison is not None:
            _write_private(
                staging / "architecture-diff.json",
                json.dumps(comparison, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            )
        for module in architecture["modules"].values():
            source_path = repository_root / module["path"]
            try:
                source_path.resolve().relative_to(source_root)
            except ValueError as error:
                raise ValueError(
                    f"module source resolves outside source root: {module['path']}"
                ) from error
            source_bytes = source_path.read_bytes()
            source_hash = hashlib.sha256(source_bytes).hexdigest()
            if source_hash != module["source_sha256"]:
                raise ValueError(f"source changed after analysis: {module['path']}")
            source = source_bytes.decode("utf-8")
            _write_private(code_root / Path(module["code_page"]).name, _code_html(module, source))
        output_root.mkdir(mode=0o700)
        published_root_created = True
        for child in staging.iterdir():
            os.rename(child, output_root / child.name)
        staging.rmdir()
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        if published_root_created and output_root.exists():
            shutil.rmtree(output_root, ignore_errors=True)
        raise
    return output_root
