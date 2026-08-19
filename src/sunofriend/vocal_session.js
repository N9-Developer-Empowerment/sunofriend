"use strict";

const token = new URLSearchParams(window.location.search).get("token") || "";
let appState = null;
let activePhraseId = null;
let activeSourceId = null;
let stopAt = null;
let draftTimer = null;
let draftNotes = {};
const player = document.querySelector("#player");

function apiPath(path) {
  const join = path.includes("?") ? "&" : "?";
  return `${path}${join}token=${encodeURIComponent(token)}`;
}

async function api(path, options = {}) {
  const response = await fetch(apiPath(path), {
    ...options,
    headers: {"Content-Type": "application/json", ...(options.headers || {})},
  });
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || `Request failed (${response.status})`);
  return value;
}

function phrase() {
  return appState.session.phrases.find((row) => row.phrase_id === activePhraseId);
}

function source(sourceId) {
  return appState.sources.find((row) => row.source_id === sourceId);
}

function formatTime(seconds) {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(Math.floor(seconds % 60)).padStart(2, "0")}.${String(Math.round((seconds % 1) * 10))}`;
}

function outcomeText(decision) {
  if (decision.outcome === "human_take") {
    return `Human base: ${source(decision.selected_source_id)?.display_label || "saved take"}`;
  }
  if (decision.outcome === "ai_fallback") return "Authorised AI kept here for now";
  if (decision.outcome === "record_again") return "Record this phrase again";
  return "No acceptable candidate yet";
}

function render() {
  document.title = `${appState.title} · Vocal Session`;
  document.querySelector("#song-title").textContent = appState.title;
  const coverage = appState.session.coverage;
  document.querySelector("#progress-count").textContent = `${coverage.decision_count} of ${coverage.phrase_count}`;
  document.querySelector("#progress-fill").style.width = `${coverage.phrase_count ? 100 * coverage.decision_count / coverage.phrase_count : 0}%`;

  const list = document.querySelector("#phrase-list");
  list.replaceChildren(...appState.session.phrases.map((row, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `phrase-row${row.phrase_id === activePhraseId ? " active" : ""}${row.decision ? " decided" : ""}`;
    const state = row.decision ? outcomeText(row.decision) : "Needs a decision";
    button.innerHTML = `<span class="phrase-index">${row.decision ? "✓" : index + 1}</span><span><strong></strong><small></small></span>`;
    button.querySelector("strong").textContent = row.lyrics;
    button.querySelector("small").textContent = state;
    button.addEventListener("click", () => selectPhrase(row.phrase_id));
    return button;
  }));

  const row = phrase();
  document.querySelector("#phrase-lyrics").textContent = row.lyrics;
  document.querySelector("#phrase-time").textContent = `${formatTime(row.start_seconds)} – ${formatTime(row.end_seconds)}`;
  const chip = document.querySelector("#phrase-state");
  chip.textContent = row.decision ? "Decision saved" : "Needs your decision";
  chip.classList.toggle("decided", Boolean(row.decision));

  const selected = row.decision?.selected_source_id || null;
  const tray = document.querySelector("#source-tray");
  tray.replaceChildren(...appState.sources.map((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `source-button${item.source_id === selected ? " selected" : ""}`;
    button.textContent = item.display_label;
    button.dataset.sourceId = item.source_id;
    button.addEventListener("click", () => playSource(item.source_id, button));
    return button;
  }));

  const current = document.querySelector("#current-choice");
  const actions = document.querySelector("#decision-actions");
  if (row.decision) {
    current.classList.remove("hidden");
    current.innerHTML = "<strong>Saved explicit decision</strong><span></span>";
    current.querySelector("span").textContent = outcomeText(row.decision);
    actions.classList.add("hidden");
  } else {
    current.classList.add("hidden");
    actions.classList.remove("hidden");
  }
  const ai = appState.sources.some((item) => item.source_class === "authorised_ai_vocal_reference");
  document.querySelector("#ai-fallback").classList.toggle("hidden", !ai);
  document.querySelector("#use-human").disabled = !activeSourceId || source(activeSourceId)?.source_class !== "human_vocal_take";

  document.querySelector("#record-title").textContent = appState.recording.available ? "Ready to record" : "Cue required before recording";
  document.querySelector("#record-reason").textContent = appState.recording.reason || "";
  restoreNote();
}

function selectPhrase(phraseId) {
  stopPlayback();
  activePhraseId = phraseId;
  activeSourceId = null;
  render();
  saveDraftSoon();
}

async function playSource(sourceId, button) {
  stopPlayback();
  activeSourceId = sourceId;
  const item = source(sourceId);
  const row = phrase();
  player.src = item.media_url;
  player.currentTime = row.start_seconds;
  stopAt = row.end_seconds;
  button.classList.add("playing");
  document.querySelector("#use-human").disabled = item.source_class !== "human_vocal_take" || Boolean(row.decision);
  try {
    await player.play();
  } catch (error) {
    showNotice(error.message, true);
    button.classList.remove("playing");
  }
}

function stopPlayback() {
  player.pause();
  player.removeAttribute("src");
  player.load();
  stopAt = null;
  document.querySelectorAll(".source-button.playing").forEach((button) => button.classList.remove("playing"));
}

player.addEventListener("timeupdate", () => {
  if (stopAt !== null && player.currentTime >= stopAt) stopPlayback();
});
player.addEventListener("ended", stopPlayback);
document.querySelector("#stop-audio").addEventListener("click", stopPlayback);

function draftPayload() {
  return {
    active_phrase_id: activePhraseId,
    notes_by_phrase: draftNotes,
  };
}

function restoreNote() {
  document.querySelector("#session-note").value = draftNotes[activePhraseId] || "";
}

function saveDraftSoon() {
  window.clearTimeout(draftTimer);
  document.querySelector("#draft-status").textContent = "Saving local draft…";
  draftTimer = window.setTimeout(saveDraft, 450);
}

async function saveDraft() {
  try {
    const value = await api("/api/draft", {
      method: "PUT",
      body: JSON.stringify({
        expected_revision: appState.draft?.revision || 0,
        draft: draftPayload(),
      }),
    });
    appState.draft = value.draft;
    document.querySelector("#draft-status").textContent = "Saved locally as a draft only.";
  } catch (error) {
    document.querySelector("#draft-status").textContent = "Draft not saved — reload to restore the latest copy.";
    showNotice(error.message, true);
  }
}

document.querySelector("#session-note").addEventListener("input", (event) => {
  draftNotes[activePhraseId] = event.target.value;
  saveDraftSoon();
});

async function decide(outcome, sourceId = null) {
  if (!window.confirm("Save this as your explicit phrase decision? Playback alone has made no choice.")) return;
  try {
    const result = await api("/api/decision", {
      method: "POST",
      body: JSON.stringify({
        phrase_id: activePhraseId,
        outcome,
        source_id: sourceId,
        notes: document.querySelector("#session-note").value,
      }),
    });
    appState = result.state;
    showNotice("Your phrase decision is saved. No audio was changed.");
    render();
  } catch (error) {
    showNotice(error.message, true);
  }
}

document.querySelector("#use-human").addEventListener("click", () => decide("human_take", activeSourceId));
document.querySelector("#record-again").addEventListener("click", () => decide("record_again"));
document.querySelector("#no-candidate").addEventListener("click", () => decide("no_acceptable_candidate"));
document.querySelector("#ai-fallback").addEventListener("click", () => decide("ai_fallback"));

function showNotice(message, error = false) {
  const notice = document.querySelector("#notice");
  notice.textContent = message;
  notice.classList.toggle("error", error);
}

async function start() {
  try {
    appState = await api("/api/session");
    draftNotes = {...(appState.draft?.draft?.notes_by_phrase || {})};
    activePhraseId = appState.draft?.draft?.active_phrase_id || appState.session.phrases.find((row) => !row.decision)?.phrase_id || appState.session.phrases[0]?.phrase_id;
    if (!activePhraseId) throw new Error("This session has no reviewed phrases yet.");
    render();
  } catch (error) {
    showNotice(error.message, true);
    document.querySelector("#phrase-lyrics").textContent = "This private session could not be opened.";
  }
}

start();
