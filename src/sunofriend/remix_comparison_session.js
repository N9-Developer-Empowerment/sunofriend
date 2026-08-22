"use strict";

const token = new URLSearchParams(window.location.search).get("token") || "";
const player = document.querySelector("#player");
const seek = document.querySelector("#seek");
let state = null;
let activeSource = "";
let switching = false;

function apiPath(path) {
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}token=${encodeURIComponent(token)}`;
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

function clock(seconds) {
  if (!Number.isFinite(seconds)) return "0:00";
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

function setNotice(message) {
  document.querySelector("#notice").textContent = message;
}

function render() {
  document.querySelector("#title").textContent = state.title;
  document.title = `${state.title} · Sunofriend`;
  document.querySelector("#goal").textContent = state.goal;
  document.querySelector("#anchor").textContent = `Keep: ${state.anchors.join(" · ")}`;
  document.querySelector("#progress").textContent = state.status === "open_for_review"
    ? `Review ${state.revision} · ${state.draft ? "Draft resumed" : "Not yet saved"}`
    : `Review ${state.revision} saved locally`;
  const open = state.status === "open_for_review";
  document.querySelector("#decision").hidden = !open;
  document.querySelector("#saved-panel").hidden = open;
  if (open && state.draft) applyAnswers(state.draft.answers);
  if (!open) renderHistory();
}

function renderHistory() {
  const history = document.querySelector("#history");
  history.replaceChildren();
  const heading = document.createElement("strong");
  heading.textContent = "Saved review history";
  history.append(heading);
  state.history.forEach((row) => {
    const item = document.createElement("p");
    item.textContent = `Review ${row.revision} · ${new Date(row.reviewed_at).toLocaleString()}`;
    history.append(item);
  });
}

function selected(name) {
  return document.querySelector(`input[name="${name}"]:checked`)?.value || "";
}

function answers() {
  return {
    expected_comparison_sha256: state.comparison_sha256,
    explicitly_heard: {
      original: document.querySelector("#heard-original").checked,
      a: document.querySelector("#heard-a").checked,
      b: document.querySelector("#heard-b").checked,
    },
    outcome: selected("outcome"),
    identity_retention: {
      a: document.querySelector("#identity-a").value,
      b: document.querySelector("#identity-b").value,
    },
    goal_usefulness: {
      a: document.querySelector("#usefulness-a").value,
      b: document.querySelector("#usefulness-b").value,
    },
    reason_codes: [...document.querySelectorAll(".reasons input:checked")].map((item) => item.value),
  };
}

function applyAnswers(value) {
  ["original", "a", "b"].forEach((name) => {
    document.querySelector(`#heard-${name}`).checked = Boolean(value.explicitly_heard[name]);
  });
  const outcome = document.querySelector(`input[name="outcome"][value="${value.outcome}"]`);
  if (outcome) outcome.checked = true;
  document.querySelector("#identity-a").value = value.identity_retention.a;
  document.querySelector("#identity-b").value = value.identity_retention.b;
  document.querySelector("#usefulness-a").value = value.goal_usefulness.a;
  document.querySelector("#usefulness-b").value = value.goal_usefulness.b;
  document.querySelectorAll(".reasons input").forEach((item) => {
    item.checked = value.reason_codes.includes(item.value);
  });
}

async function chooseSource(name) {
  if (!state) return;
  const keepTime = Number.isFinite(player.currentTime) ? player.currentTime : 0;
  const shouldPlay = !player.paused || !activeSource;
  switching = true;
  player.pause();
  activeSource = name;
  document.querySelectorAll("[data-play]").forEach((button) => {
    button.classList.toggle("active", button.dataset.play === name);
  });
  document.querySelector("#playing").textContent = `Ready: ${state.media[name].label}`;
  player.src = state.media[name].media_url;
  player.load();
  player.addEventListener("loadedmetadata", async () => {
    player.currentTime = Math.min(keepTime, Math.max(0, player.duration - .01));
    switching = false;
    if (shouldPlay) {
      try { await player.play(); } catch (error) { setNotice(`Could not play: ${error.message}`); }
    }
  }, {once: true});
}

function updateTimeline() {
  const duration = Number.isFinite(player.duration) ? player.duration : 0;
  const current = Number.isFinite(player.currentTime) ? player.currentTime : 0;
  seek.value = duration ? String(Math.round((current / duration) * 1000)) : "0";
  document.querySelector("#clock").textContent = `${clock(current)} / ${clock(duration)}`;
  document.querySelector("#play-pause").textContent = player.paused ? "Play" : "Pause";
}

async function saveDraft() {
  try {
    const value = await api("/api/draft", {method: "POST", body: JSON.stringify(answers())});
    state = value.state;
    render();
    setNotice("Draft saved on this computer.");
  } catch (error) { setNotice(error.message); }
}

async function saveReview() {
  try {
    const value = await api("/api/review", {method: "POST", body: JSON.stringify(answers())});
    state = value.state;
    render();
  } catch (error) { setNotice(error.message); }
}

async function reopenReview() {
  const reason = document.querySelector("#reopen-reason").value;
  if (!reason) {
    setNotice("Choose why you are reopening this review.");
    return;
  }
  try {
    const value = await api("/api/reopen", {
      method: "POST",
      body: JSON.stringify({
        expected_comparison_sha256: state.comparison_sha256,
        expected_review_sha256: state.saved_review.document_sha256,
        reason_code: reason,
      }),
    });
    state = value.state;
    render();
    setNotice("Review reopened. The earlier version remains in history.");
  } catch (error) { setNotice(error.message); }
}

document.querySelectorAll("[data-play]").forEach((button) => {
  button.addEventListener("click", () => chooseSource(button.dataset.play));
});
document.querySelector("#play-pause").addEventListener("click", async () => {
  if (!activeSource) return chooseSource("original");
  if (player.paused) {
    try { await player.play(); } catch (error) { setNotice(`Could not play: ${error.message}`); }
  } else player.pause();
});
document.querySelector("#stop").addEventListener("click", () => { player.pause(); player.currentTime = 0; });
seek.addEventListener("input", () => {
  if (Number.isFinite(player.duration)) player.currentTime = (Number(seek.value) / 1000) * player.duration;
});
player.addEventListener("timeupdate", updateTimeline);
player.addEventListener("durationchange", updateTimeline);
player.addEventListener("play", updateTimeline);
player.addEventListener("pause", () => { if (!switching) updateTimeline(); });
document.querySelector("#save-draft").addEventListener("click", saveDraft);
document.querySelector("#save-review").addEventListener("click", saveReview);
document.querySelector("#reopen").addEventListener("click", reopenReview);

api("/api/session").then((value) => { state = value; render(); }).catch((error) => setNotice(error.message));
