"use strict";

const token = new URLSearchParams(window.location.search).get("token") || "";
const player = document.querySelector("#player");
const heard = {control: false, a: false, b: false};
let state = null;

function apiPath(path) {
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}token=${encodeURIComponent(token)}`;
}

function render() {
  document.querySelector("#title").textContent = state.title;
  document.title = `${state.title} · Sunofriend`;
  document.querySelectorAll("[data-heard]").forEach((item) => {
    const played = heard[item.dataset.heard];
    item.textContent = played ? "Played in this browser session" : "Not played yet";
    item.classList.toggle("yes", played);
  });
}

async function play(name) {
  const media = state.media[name];
  player.pause();
  player.src = media.media_url;
  player.currentTime = 0;
  try {
    await player.play();
    heard[name] = true;
    document.querySelector("#notice").textContent = `${media.label} is playing. Nothing is being saved.`;
    render();
  } catch (error) {
    document.querySelector("#notice").textContent = `Could not play ${media.label}: ${error.message}`;
  }
}

document.querySelectorAll("[data-play]").forEach((button) => {
  button.addEventListener("click", () => play(button.dataset.play));
});

fetch(apiPath("/api/session"), {headers: {"Accept": "application/json"}})
  .then(async (response) => {
    const value = await response.json();
    if (!response.ok) throw new Error(value.error || `Request failed (${response.status})`);
    return value;
  })
  .then((value) => {
    state = value;
    render();
  })
  .catch((error) => {
    document.querySelector("#notice").textContent = error.message;
  });
