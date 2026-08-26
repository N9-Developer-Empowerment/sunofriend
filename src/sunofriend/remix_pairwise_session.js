"use strict";

const token = new URLSearchParams(window.location.search).get("token") || "";
const player = document.querySelector("#player");
const heardByPlayback = {control: false, a: false, b: false};
let state = null;

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

function render() {
  document.querySelector("#title").textContent = state.title;
  document.title = `${state.title} · Sunofriend`;
  document.querySelector("#anchor-copy").textContent = state.anchors
    .map((row) => row.owner_label).join(" · ");
  document.querySelectorAll("[data-heard]").forEach((item) => {
    const heard = heardByPlayback[item.dataset.heard];
    item.textContent = heard ? "Played in this browser session" : "Not marked as heard";
    item.classList.toggle("yes", heard);
  });
  const saved = Boolean(state.saved_label);
  document.querySelector("#save-label").disabled = saved;
  if (saved) {
    document.querySelector("#notice").textContent = "This exact A/B label is saved. Playback still changes nothing.";
  }
}

async function play(name) {
  const media = state.media[name];
  player.pause();
  player.src = media.media_url;
  player.currentTime = 0;
  try {
    await player.play();
    heardByPlayback[name] = true;
    render();
  } catch (error) {
    document.querySelector("#notice").textContent = `Could not play ${media.label}: ${error.message}`;
  }
}

function selectedValue(name) {
  return document.querySelector(`input[name="${name}"]:checked`)?.value || "";
}

async function saveLabel() {
  const outcome = selectedValue("outcome");
  const reasons = [...document.querySelectorAll(".reasons input:checked")].map((item) => item.value);
  const identityA = document.querySelector("#identity-a").value;
  const identityB = document.querySelector("#identity-b").value;
  const explicitHeard = document.querySelector("#heard-confirmation").checked;
  const trainingAdmission = document.querySelector("#training-admission").checked;
  if (!outcome || !identityA || !identityB || reasons.length < 1 || reasons.length > 4 || !explicitHeard || !trainingAdmission) {
    document.querySelector("#notice").textContent = "Complete the result, both identity questions, one to four reasons, and both confirmations.";
    return;
  }
  const button = document.querySelector("#save-label");
  button.disabled = true;
  try {
    const value = await api("/api/label", {
      method: "POST",
      body: JSON.stringify({
        expected_variant_set_sha256: state.variant_set_sha256,
        explicitly_heard: {control: true, a: true, b: true},
        outcome,
        identity_relationships: {a: identityA, b: identityB},
        reason_codes: reasons,
        admit_owner_local_training: true,
      }),
    });
    state = value.state;
    render();
  } catch (error) {
    button.disabled = false;
    document.querySelector("#notice").textContent = error.message;
  }
}

document.querySelectorAll("[data-play]").forEach((button) => {
  button.addEventListener("click", () => play(button.dataset.play));
});
document.querySelector("#save-label").addEventListener("click", saveLabel);

api("/api/session").then((value) => {
  state = value;
  render();
}).catch((error) => {
  document.querySelector("#notice").textContent = error.message;
});
