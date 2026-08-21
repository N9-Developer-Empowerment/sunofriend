const query = new URLSearchParams(location.search);
const token = query.get("token") || "";
const withToken = (path) =>
  `${path}${path.includes("?") ? "&" : "?"}token=${encodeURIComponent(token)}`;
const api = async (path, options = {}) => {
  const response = await fetch(withToken(path), options);
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || `Request failed (${response.status})`);
  return value;
};

const labels = {
  motif: "Main melody, vocal contour, instrumental hook or motif",
  bass_movement: "Bass melody or bass movement",
  groove: "Groove, pulse or rhythmic pattern",
  harmonic_event: "Chord movement, harmony or cadence",
  structural_relationship: "Section shape or structural relationship",
};

let state = null;
let selectedEstimateId = "";
const player = document.getElementById("player");
const status = document.getElementById("status");
const diagnostics = document.getElementById("diagnostics");
const setStatus = (message, kind = "") => {
  status.textContent = message;
  status.className = kind;
};

const play = async (media) => {
  player.pause();
  player.src = media.media_url;
  player.load();
  await new Promise((resolve, reject) => {
    if (player.readyState >= 1) {
      resolve();
      return;
    }
    player.addEventListener("loadedmetadata", resolve, { once: true });
    player.addEventListener(
      "error",
      () => reject(new Error("Audio could not be loaded")),
      { once: true },
    );
  });
  await player.play();
};

document.querySelector("[data-play-source]").addEventListener("click", () =>
  play(state.media.source).catch((error) => setStatus(error.message, "error")),
);
document.getElementById("stop").addEventListener("click", () => {
  player.pause();
  player.currentTime = 0;
});

const renderDiagnostics = () => {
  diagnostics.replaceChildren();
  state.media.diagnostics.forEach((item) => {
    const card = document.createElement("article");
    card.className = "diagnostic";
    const functions = item.musical_functions.length
      ? item.musical_functions.join(" · ")
      : "diagnostic view";
    card.innerHTML = `
      <p class="function-tags">${functions}</p>
      <h3>${item.label}</h3>
      <p>${item.description}</p>
      <button type="button" data-play-diagnostic>Play this estimate</button>
      <label><input type="checkbox" data-heard-diagnostic> I heard this estimate</label>
      <label class="anchor-source"><input type="radio" name="anchor-source" value="${item.diagnostic_id}"> Use this view as evidence for my anchor</label>
    `;
    card.querySelector("[data-play-diagnostic]").addEventListener("click", () =>
      play(item).catch((error) => setStatus(error.message, "error")),
    );
    card.querySelector('[name="anchor-source"]').addEventListener("change", () => {
      selectedEstimateId = item.diagnostic_id;
      document.querySelectorAll(".diagnostic").forEach((node) =>
        node.classList.toggle(
          "selected",
          node.querySelector('[name="anchor-source"]:checked') !== null,
        ),
      );
    });
    diagnostics.appendChild(card);
  });
};

const initialize = async () => {
  state = await api("/api/session");
  document.getElementById("title").textContent = state.title;
  document.getElementById("duration").textContent =
    `Available clock: 0.000 to ${state.clock.duration_seconds.toFixed(3)} seconds.`;
  const select = document.getElementById("anchor-kind");
  select.innerHTML =
    '<option value="">Choose the primary musical function…</option>' +
    state.anchor_kinds
      .map((value) => `<option value="${value}">${labels[value] || value}</option>`)
      .join("");
  renderDiagnostics();
  if (state.saved_confirmation) {
    document.getElementById("confirm").disabled = true;
    setStatus("Musical anchor already confirmed locally.", "saved");
  }
};

document.getElementById("confirm").addEventListener("click", async () => {
  setStatus("");
  const rate = state.clock.sample_rate_hz;
  const start = Number(document.getElementById("start-seconds").value);
  const end = Number(document.getElementById("end-seconds").value);
  if (!Number.isFinite(start) || !Number.isFinite(end)) {
    setStatus("Enter the exact start and end of the musical anchor.", "error");
    return;
  }
  if (!selectedEstimateId) {
    setStatus("Choose the diagnostic view where you hear this anchor most clearly.", "error");
    return;
  }
  const selectedCard = [...document.querySelectorAll(".diagnostic")].find(
    (card) => card.querySelector('[name="anchor-source"]:checked'),
  );
  const heardSelected =
    selectedCard?.querySelector("[data-heard-diagnostic]").checked === true;
  const payload = {
    expected_project_state_sha256: state.project_state.document_sha256,
    explicitly_heard: {
      source_control: document.getElementById("heard-source").checked,
      selected_estimate: heardSelected,
    },
    owner_label: document.getElementById("owner-label").value,
    anchor_kind: document.getElementById("anchor-kind").value,
    selected_estimate_id: selectedEstimateId,
    start_frame: Math.round(start * rate),
    end_frame: Math.round(end * rate),
    preservation_requirement: state.preservation_requirement,
  };
  try {
    const result = await api("/api/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state = result.state;
    document.getElementById("confirm").disabled = true;
    setStatus(
      "Musical anchor saved locally. Controlled variants can now be prepared separately.",
      "saved",
    );
  } catch (error) {
    setStatus(error.message, "error");
  }
});

initialize().catch((error) => setStatus(error.message, "error"));
