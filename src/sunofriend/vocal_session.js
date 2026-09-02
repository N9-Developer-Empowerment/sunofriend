"use strict";

const token = new URLSearchParams(window.location.search).get("token") || "";
let appState = null;
let activePhraseId = null;
let activeSourceId = null;
let contextScope = "phrase";
let phraseFilter = "open";
let stopAt = null;
let draftTimer = null;
let draftNotes = {};
let microphoneStream = null;
let audioContext = null;
let microphoneSource = null;
let microphoneProcessor = null;
let silentGain = null;
let cueNode = null;
let captureTimer = null;
let recording = false;
let captureChunks = [];
let captureFrameCursor = 0;
let captureOriginContextTime = null;
let captureStartContextTime = null;
let recordedAttempt = null;
let attemptObjectUrl = null;
let workingAuditionContext = null;
let workingAuditionNodes = [];
let workingAuditionTimer = null;
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

function isHumanSourceForPhrase(item, phraseId) {
  if (!item) return false;
  if (item.source_class === "human_vocal_take") {
    return !item.eligible_phrase_ids || item.eligible_phrase_ids.includes(phraseId);
  }
  return ["human_vocal_phrase_capture", "unreviewed_vocal_candidate"].includes(item.source_class)
    && item.bound_phrase_id === phraseId;
}

function isPhraseLocalSource(item) {
  return ["human_vocal_phrase_capture", "unreviewed_vocal_candidate"].includes(
    item?.source_class,
  );
}

function formatTime(seconds) {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(Math.floor(seconds % 60)).padStart(2, "0")}.${String(Math.round((seconds % 1) * 10))}`;
}

function outcomeText(decision) {
  if (decision.outcome === "human_take") {
    const available = appState.sources.filter(
      (item) => isHumanSourceForPhrase(item, decision.phrase_id || activePhraseId),
    );
    const index = available.findIndex((item) => item.source_id === decision.selected_source_id);
    return `Human base: ${index >= 0 ? `Attempt ${index + 1}` : "saved take"}`;
  }
  if (decision.outcome === "ai_fallback") return "Authorised AI kept here for now";
  if (decision.outcome === "record_again") return "Needs a new recording";
  return "No acceptable candidate yet";
}

function render() {
  document.title = `${appState.title} · Vocal Session`;
  document.querySelector("#song-title").textContent = appState.title;
  const coverage = appState.session.coverage;
  document.querySelector("#progress-count").textContent = `${coverage.decision_count} of ${coverage.phrase_count}`;
  document.querySelector("#progress-fill").style.width = `${coverage.phrase_count ? 100 * coverage.decision_count / coverage.phrase_count : 0}%`;

  const list = document.querySelector("#phrase-list");
  const visiblePhrases = appState.session.phrases.filter((row) => {
    if (phraseFilter === "open") return !row.decision;
    if (phraseFilter === "decided") return Boolean(row.decision);
    return true;
  });
  list.replaceChildren(...visiblePhrases.map((row) => {
    const index = appState.session.phrases.findIndex((item) => item.phrase_id === row.phrase_id);
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
  if (!visiblePhrases.length) {
    const empty = document.createElement("p");
    empty.className = "empty-phrases";
    empty.textContent = phraseFilter === "open"
      ? "Every phrase currently has a saved decision."
      : "No phrases match this view.";
    list.append(empty);
  }
  document.querySelectorAll("[data-phrase-filter]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.phraseFilter === phraseFilter));
  });
  document.querySelector("#next-open-phrase").disabled = coverage.remaining_phrase_count === 0;

  const row = phrase();
  const phraseIndex = appState.session.phrases.findIndex(
    (item) => item.phrase_id === row.phrase_id,
  );
  document.querySelector("#phrase-position").textContent = `Phrase ${phraseIndex + 1} of ${coverage.phrase_count}`;
  document.querySelector("#previous-phrase").disabled = phraseIndex <= 0 || recording || Boolean(recordedAttempt);
  document.querySelector("#next-phrase").disabled = phraseIndex >= coverage.phrase_count - 1 || recording || Boolean(recordedAttempt);
  document.querySelector("#phrase-lyrics").textContent = row.lyrics;
  document.querySelector("#phrase-time").textContent = `${formatTime(row.start_seconds)} – ${formatTime(row.end_seconds)}`;
  const chip = document.querySelector("#phrase-state");
  chip.textContent = row.decision ? "Decision saved" : "Needs your decision";
  chip.classList.toggle("decided", Boolean(row.decision));

  const selected = row.decision?.selected_source_id || null;
  const workingSelected = appState.candidate_vault?.working_choices?.choices?.[
    row.phrase_id
  ]?.source_id || null;
  const tray = document.querySelector("#source-tray");
  const availableSources = appState.sources.filter(
    (item) => isHumanSourceForPhrase(item, row.phrase_id),
  );
  tray.replaceChildren(...availableSources.map((item, attemptIndex) => {
    const card = document.createElement("article");
    const activeAudition = item.source_id === activeSourceId;
    card.className = `source-card${item.source_id === selected ? " selected" : ""}${item.source_id === workingSelected ? " working-choice" : ""}${activeAudition ? " active-audition" : ""}`;
    card.dataset.sourceId = item.source_id;
    const label = document.createElement("strong");
    label.textContent = item.display_label || `Attempt ${attemptIndex + 1}`;
    const actions = document.createElement("div");
    actions.className = "source-card-actions";
    const play = document.createElement("button");
    play.type = "button";
    play.className = "source-button";
    play.textContent = activeAudition ? "Play again" : "Play";
    play.ariaPressed = String(activeAudition);
    play.addEventListener("click", () => playSource(item.source_id));
    const use = document.createElement("button");
    use.type = "button";
    use.className = "quiet-button";
    const provisional = item.source_class === "unreviewed_vocal_candidate";
    use.textContent = item.source_id === selected
      ? "Saved choice"
      : (item.source_id === workingSelected ? "Working choice" : (provisional ? "Use in draft" : "Use this attempt"));
    use.disabled = Boolean(row.decision);
    use.addEventListener("click", () => provisional
      ? useWorkingChoice(item.source_id)
      : decide("human_take", item.source_id));
    actions.append(play, use);
    card.append(label, actions);
    return card;
  }));

  const current = document.querySelector("#current-choice");
  const actions = document.querySelector("#decision-actions");
  const revisionActions = document.querySelector("#decision-revision-actions");
  if (row.decision) {
    current.classList.remove("hidden");
    current.innerHTML = "<strong>Saved explicit decision</strong><span></span>";
    current.querySelector("span").textContent = outcomeText(row.decision);
    actions.classList.add("hidden");
    revisionActions.classList.remove("hidden");
    document.querySelector("#reopen-phrase").disabled = false;
    document.querySelector("#record-new-attempt").disabled = false;
  } else {
    current.classList.add("hidden");
    actions.classList.remove("hidden");
    revisionActions.classList.add("hidden");
  }
  document.querySelector("#ai-fallback").classList.toggle(
    "hidden",
    !appState.ai_fallback_available,
  );
  document.querySelector("#use-human").disabled = !isHumanSourceForPhrase(source(activeSourceId), row.phrase_id);
  const originalContext = appState.context_playback.original;
  const workingContext = appState.context_playback.working;
  const originalButton = document.querySelector("#play-original");
  originalButton.disabled = !appState.context_playback.original_source_id;
  originalButton.textContent = originalContext?.comparison_kind === "full_mix"
    ? "Play original full mix"
    : "Play reference vocal";
  document.querySelector("#play-working-audition").textContent = workingContext?.backing_available
    ? "Play rough working comp"
    : "Play working vocal only";
  document.querySelector("#context-help").textContent = workingContext?.backing_available
    ? "Compare the complete original mix with the instrumental backing plus your reversible working vocal. Unreplaced phrases, breaths, gaps and ad-libs stay on the reference vocal. Playback saves nothing and renders nothing."
    : "No instrumental backing was supplied, so the working audition is vocal-only. Unreplaced phrases, breaths, gaps and ad-libs stay on the reference vocal. Playback saves nothing and renders nothing.";
  document.querySelector("#play-working-audition").disabled = !appState.candidate_vault?.working_audition_url;
  document.querySelectorAll("[data-context-scope]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.contextScope === contextScope));
  });

  document.querySelector("#record-title").textContent = appState.recording.available
    ? (appState.recording.transition_required ? "Ready for an explicit new recording round" : "Ready to record")
    : "Cue required before recording";
  document.querySelector("#record-reason").textContent = appState.recording.reason || "";
  document.querySelector("#enable-mic").disabled = !appState.recording.available || Boolean(microphoneStream);
  document.querySelector("#record-attempt").disabled = !appState.recording.available || !microphoneStream || recording;
  document.querySelector("#recorder-panel").classList.toggle("hidden", !appState.recording.available);
  restoreNote();
}

function selectPhrase(phraseId) {
  if (recording || recordedAttempt) {
    showNotice("Finish, save or discard the current recording before changing phrase.", true);
    return;
  }
  if (phraseId === activePhraseId) return;
  stopPlayback();
  activePhraseId = phraseId;
  activeSourceId = null;
  render();
  saveDraftSoon();
}

function selectAdjacentPhrase(direction) {
  const rows = appState.session.phrases;
  const currentIndex = rows.findIndex((row) => row.phrase_id === activePhraseId);
  const target = rows[currentIndex + direction];
  if (target) selectPhrase(target.phrase_id);
}

function selectNextOpenPhrase() {
  const rows = appState.session.phrases;
  const currentIndex = rows.findIndex((row) => row.phrase_id === activePhraseId);
  const ordered = rows.slice(currentIndex + 1).concat(rows.slice(0, currentIndex + 1));
  const next = ordered.find((row) => !row.decision);
  if (!next) {
    showNotice("Every phrase currently has a saved decision.");
    return;
  }
  phraseFilter = "open";
  selectPhrase(next.phrase_id);
}

function contextWindow() {
  const row = phrase();
  if (contextScope === "song") {
    return {
      start: appState.context_playback.song_start_seconds,
      end: appState.context_playback.song_end_seconds,
    };
  }
  if (contextScope === "section") {
    const rows = appState.session.phrases;
    const index = rows.findIndex((item) => item.phrase_id === row.phrase_id);
    const radius = appState.context_playback.section_phrase_radius;
    return {
      start: rows[Math.max(0, index - radius)].start_seconds,
      end: rows[Math.min(rows.length - 1, index + radius)].end_seconds,
    };
  }
  return {start: row.start_seconds, end: row.end_seconds};
}

function waitForMetadata(media) {
  if (media.readyState >= 1) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const loaded = () => { cleanup(); resolve(); };
    const failed = () => { cleanup(); reject(new Error("This audio source could not be loaded.")); };
    const cleanup = () => {
      media.removeEventListener("loadedmetadata", loaded);
      media.removeEventListener("error", failed);
    };
    media.addEventListener("loadedmetadata", loaded, {once: true});
    media.addEventListener("error", failed, {once: true});
  });
}

async function playSource(sourceId) {
  stopPlayback();
  activeSourceId = sourceId;
  const item = source(sourceId);
  const row = phrase();
  render();
  try {
    player.src = item.media_url;
    // waitForMetadata resolves only after loadedmetadata, before any currentTime seek.
    await waitForMetadata(player);
    const window = contextWindow();
    const sourceLocalCapture = isPhraseLocalSource(item);
    player.currentTime = sourceLocalCapture
      ? (item.playback_start_seconds ?? 0)
      : window.start;
    stopAt = sourceLocalCapture
      ? (item.playback_end_seconds ?? player.duration)
      : Math.min(window.end, player.duration);
    if (sourceLocalCapture && contextScope !== "phrase") {
      showNotice("This short pickup can play only its recorded phrase. Use an original or full take for wider context.");
    }
    await player.play();
  } catch (error) {
    showNotice(error.message, true);
  }
}

function stopPlayback() {
  player.pause();
  player.removeAttribute("src");
  player.load();
  stopAt = null;
  window.clearTimeout(workingAuditionTimer);
  workingAuditionTimer = null;
  workingAuditionNodes.forEach((node) => {
    try { node.stop(); } catch (error) { /* already stopped */ }
  });
  workingAuditionNodes = [];
  if (workingAuditionContext) {
    workingAuditionContext.close().catch(() => {});
    workingAuditionContext = null;
  }
  document.querySelectorAll(".source-button.playing").forEach((button) => button.classList.remove("playing"));
}

async function decodeAuditionSource(context, mediaUrl) {
  const response = await fetch(mediaUrl, {cache: "no-store"});
  if (!response.ok) throw new Error("A working-audition source could not be loaded.");
  return context.decodeAudioData(await response.arrayBuffer());
}

async function playWorkingAudition() {
  stopPlayback();
  try {
    const plan = await api(`/api/working-audition?scope=${encodeURIComponent(contextScope)}&phrase_id=${encodeURIComponent(activePhraseId)}`);
    workingAuditionContext = new AudioContext({latencyHint: "playback"});
    const context = workingAuditionContext;
    const buffers = new Map();
    const scheduledSegments = [...plan.working_mix.vocal_segments];
    if (plan.working_mix.backing) scheduledSegments.unshift(plan.working_mix.backing);
    await Promise.all([...new Set(scheduledSegments.map((row) => row.media_url))].map(async (url) => {
      buffers.set(url, await decodeAuditionSource(context, url));
    }));
    await context.resume();
    const clockStart = context.currentTime + 0.05;
    scheduledSegments.forEach((segment) => {
      const sourceNode = context.createBufferSource();
      const gainNode = context.createGain();
      const duration = segment.source_end_seconds - segment.source_start_seconds;
      const fade = Math.min(plan.join.edge_fade_seconds, duration / 2);
      const scheduledStart = clockStart + segment.destination_start_seconds;
      sourceNode.buffer = buffers.get(segment.media_url);
      sourceNode.connect(gainNode).connect(context.destination);
      gainNode.gain.setValueAtTime(0, scheduledStart);
      gainNode.gain.linearRampToValueAtTime(1, scheduledStart + fade);
      gainNode.gain.setValueAtTime(1, scheduledStart + duration - fade);
      gainNode.gain.linearRampToValueAtTime(0, scheduledStart + duration);
      sourceNode.start(scheduledStart, segment.source_start_seconds, duration);
      sourceNode.stop(scheduledStart + duration);
      workingAuditionNodes.push(sourceNode);
    });
    workingAuditionTimer = window.setTimeout(
      stopPlayback,
      Math.ceil((plan.duration_seconds + 0.1) * 1000),
    );
    showNotice("Playing a browser-only rough audition. Nothing is saved, selected or rendered.");
  } catch (error) {
    stopPlayback();
    showNotice(error.message, true);
  }
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

async function useWorkingChoice(sourceId) {
  const current = appState.candidate_vault?.working_choices;
  const choices = {};
  Object.entries(current?.choices || {}).forEach(([phraseId, choice]) => {
    choices[phraseId] = choice.source_id;
  });
  choices[activePhraseId] = sourceId;
  try {
    const result = await api("/api/working-choices", {
      method: "PUT",
      body: JSON.stringify({
        expected_revision: current?.revision || 0,
        working_source_by_phrase: choices,
      }),
    });
    appState.candidate_vault.working_choices = result.working_choices;
    showNotice("Working choice updated. This is reversible and is not a saved phrase decision.");
    render();
  } catch (error) {
    showNotice(error.message, true);
  }
}

document.querySelector("#use-human").addEventListener("click", () => {
  const active = source(activeSourceId);
  if (active?.source_class === "unreviewed_vocal_candidate") {
    useWorkingChoice(activeSourceId);
  } else {
    decide("human_take", activeSourceId);
  }
});
document.querySelector("#no-candidate").addEventListener("click", () => decide("no_acceptable_candidate"));
document.querySelector("#ai-fallback").addEventListener("click", () => decide("ai_fallback"));

async function reopenPhrase(reason = "review_again") {
  const row = phrase();
  if (!row.decision) return;
  if (!window.confirm("Reopen this phrase? The earlier choice remains in the private history and no audio is changed.")) return;
  try {
    const result = await api("/api/reopen", {
      method: "POST",
      body: JSON.stringify({
        phrase_id: row.phrase_id,
        expected_decision_document_sha256: row.decision.decision_document_sha256,
        reason,
      }),
    });
    appState = result.state;
    activeSourceId = null;
    render();
    showNotice("Phrase reopened. The earlier decision is retained in history.");
  } catch (error) {
    showNotice(error.message, true);
  }
}

async function beginRecordWorkflow() {
  if (!appState.recording.available) {
    showNotice(appState.recording.reason || "Recording is not configured for this session.", true);
    return;
  }
  document.querySelector("#recorder-panel").scrollIntoView({behavior: "smooth", block: "center"});
  if (!microphoneStream) await enableMicrophone();
  if (microphoneStream) setRecorderStatus("Ready. Hear the original if needed, then press Record.");
}

document.querySelector("#reopen-phrase").addEventListener("click", () => reopenPhrase("review_again"));
document.querySelector("#record-new-attempt").addEventListener("click", beginRecordWorkflow);
document.querySelector("#record-replacement").addEventListener("click", beginRecordWorkflow);
document.querySelector("#play-original").addEventListener("click", () => {
  const original = appState.context_playback.original_source_id;
  if (original) playSource(original);
});
document.querySelector("#play-working-audition").addEventListener("click", playWorkingAudition);
document.querySelectorAll("[data-context-scope]").forEach((button) => {
  button.addEventListener("click", () => {
    contextScope = button.dataset.contextScope;
    stopPlayback();
    render();
  });
});
document.querySelectorAll("[data-phrase-filter]").forEach((button) => {
  button.addEventListener("click", () => {
    phraseFilter = button.dataset.phraseFilter;
    render();
  });
});
document.querySelector("#next-open-phrase").addEventListener("click", selectNextOpenPhrase);
document.querySelector("#previous-phrase").addEventListener("click", () => selectAdjacentPhrase(-1));
document.querySelector("#next-phrase").addEventListener("click", () => selectAdjacentPhrase(1));
document.addEventListener("keydown", (event) => {
  const target = event.target;
  if (target instanceof HTMLElement && (
    target.isContentEditable
    || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)
  )) return;
  if (event.altKey || event.ctrlKey || event.metaKey) return;
  if (event.key.toLowerCase() === "j") {
    event.preventDefault();
    selectAdjacentPhrase(1);
  } else if (event.key.toLowerCase() === "k") {
    event.preventDefault();
    selectAdjacentPhrase(-1);
  }
});

function dbfs(value) {
  return value > 0 ? 20 * Math.log10(value) : -Infinity;
}

function setRecorderStatus(message, error = false) {
  const status = document.querySelector("#record-status");
  status.textContent = message;
  status.style.color = error ? "var(--danger)" : "";
}

async function enableMicrophone() {
  if (!navigator.mediaDevices?.getUserMedia || !window.AudioContext) {
    setRecorderStatus("This browser cannot provide the required local microphone capture.", true);
    return;
  }
  try {
    microphoneStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: {ideal: 1},
        sampleRate: {ideal: 44100},
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
      },
      video: false,
    });
    audioContext = new AudioContext({sampleRate: 44100, latencyHint: "interactive"});
    await audioContext.resume();
    microphoneSource = audioContext.createMediaStreamSource(microphoneStream);
    microphoneProcessor = audioContext.createScriptProcessor(2048, 1, 1);
    silentGain = audioContext.createGain();
    silentGain.gain.value = 0;
    microphoneSource.connect(microphoneProcessor);
    microphoneProcessor.connect(silentGain);
    silentGain.connect(audioContext.destination);
    microphoneProcessor.onaudioprocess = (event) => {
      const input = event.inputBuffer.getChannelData(0);
      let sum = 0;
      for (let index = 0; index < input.length; index += 1) sum += input[index] * input[index];
      const rms = Math.sqrt(sum / Math.max(1, input.length));
      const level = Math.max(0, Math.min(100, (dbfs(rms) + 60) * (100 / 60)));
      document.querySelector("#mic-meter").style.width = `${level}%`;
      if (recording) {
        if (captureOriginContextTime === null) captureOriginContextTime = event.playbackTime;
        captureChunks.push({frame: captureFrameCursor, samples: new Float32Array(input)});
        captureFrameCursor += input.length;
      }
    };
    const settings = microphoneStream.getAudioTracks()[0]?.getSettings?.() || {};
    document.querySelector("#mic-status").textContent =
      `Microphone enabled at ${audioContext.sampleRate} Hz. Echo cancellation ${settings.echoCancellation === false ? "off" : "browser-controlled"}; noise suppression ${settings.noiseSuppression === false ? "off" : "browser-controlled"}; automatic gain ${settings.autoGainControl === false ? "off" : "browser-controlled"}.`;
    setRecorderStatus("Ready. Wear headphones, then record the current phrase.");
    render();
  } catch (error) {
    microphoneStream = null;
    setRecorderStatus(`Microphone could not be enabled: ${error?.message || error}`, true);
  }
}

async function startRecording() {
  if (!audioContext || !microphoneStream || recording || !appState.recording.available) return;
  stopPlayback();
  discardRecordedAttempt();
  const row = phrase();
  const plan = appState.recording;
  const phrasePlan = plan.phrases.find((item) => item.phrase_id === row.phrase_id);
  try {
    setRecorderStatus("Loading the verified cue…");
    const response = await fetch(phrasePlan.cue.media_url, {cache: "no-store"});
    if (!response.ok) throw new Error(`cue request failed (${response.status})`);
    const cueBuffer = await audioContext.decodeAudioData(await response.arrayBuffer());
    await audioContext.resume();
    const before = phrasePlan.placement.pre_guard_frames / audioContext.sampleRate;
    const after = phrasePlan.placement.post_guard_frames / audioContext.sampleRate;
    const phraseDuration = row.end_seconds - row.start_seconds;
    const totalDuration = before + phraseDuration + after;
    const cueOffset = Math.max(0, phrasePlan.cue.playback_start_seconds);
    const cueDelay = Math.max(0, -phrasePlan.cue.playback_start_seconds);
    const availableCueDuration = Math.max(0, cueBuffer.duration - cueOffset);
    if (availableCueDuration < phraseDuration + after - 0.02) {
      throw new Error("the verified cue does not cover this phrase and its end guard");
    }
    cueNode = audioContext.createBufferSource();
    cueNode.buffer = cueBuffer;
    cueNode.connect(audioContext.destination);
    captureChunks = [];
    captureFrameCursor = 0;
    captureOriginContextTime = null;
    captureStartContextTime = audioContext.currentTime + 0.25;
    recording = true;
    document.querySelector("#record-count").textContent = "SING";
    document.querySelector("#record-attempt").disabled = true;
    document.querySelector("#stop-recording").disabled = false;
    cueNode.start(
      captureStartContextTime + cueDelay,
      cueOffset,
      Math.min(availableCueDuration, totalDuration - cueDelay),
    );
    captureTimer = window.setTimeout(() => stopRecording(false), (totalDuration + 0.32) * 1000);
    setRecorderStatus("Recording now. Follow the reference naturally; timing will remain reviewable.");
  } catch (error) {
    recording = false;
    document.querySelector("#record-attempt").disabled = !microphoneStream;
    document.querySelector("#stop-recording").disabled = true;
    setRecorderStatus(`Recording could not start: ${error?.message || error}`, true);
  }
}

function assembleFrames(startFrame, frameCount) {
  const result = new Float32Array(frameCount);
  const endFrame = startFrame + frameCount;
  for (const chunk of captureChunks) {
    const chunkStart = chunk.frame;
    const chunkEnd = chunkStart + chunk.samples.length;
    const overlapStart = Math.max(startFrame, chunkStart);
    const overlapEnd = Math.min(endFrame, chunkEnd);
    if (overlapEnd <= overlapStart) continue;
    const sourceOffset = overlapStart - chunkStart;
    const destinationOffset = overlapStart - startFrame;
    result.set(
      chunk.samples.subarray(sourceOffset, sourceOffset + overlapEnd - overlapStart),
      destinationOffset,
    );
  }
  return result;
}

function encodePcm24Wav(samples, sampleRate) {
  const dataBytes = samples.length * 3;
  const buffer = new ArrayBuffer(44 + dataBytes);
  const view = new DataView(buffer);
  const writeText = (offset, text) => {
    for (let index = 0; index < text.length; index += 1) view.setUint8(offset + index, text.charCodeAt(index));
  };
  writeText(0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  writeText(8, "WAVE");
  writeText(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 3, true);
  view.setUint16(32, 3, true);
  view.setUint16(34, 24, true);
  writeText(36, "data");
  view.setUint32(40, dataBytes, true);
  let offset = 44;
  for (const sample of samples) {
    const clamped = Math.max(-1, Math.min(1, sample));
    let value = clamped < 0 ? Math.round(clamped * 8388608) : Math.round(clamped * 8388607);
    if (value < 0) value += 16777216;
    view.setUint8(offset, value & 255);
    view.setUint8(offset + 1, (value >> 8) & 255);
    view.setUint8(offset + 2, (value >> 16) & 255);
    offset += 3;
  }
  return new Blob([buffer], {type: "audio/wav"});
}

function encodePcm16PreviewWav(samples, sampleRate) {
  const dataBytes = samples.length * 2;
  const buffer = new ArrayBuffer(44 + dataBytes);
  const view = new DataView(buffer);
  const writeText = (offset, text) => {
    for (let index = 0; index < text.length; index += 1) view.setUint8(offset + index, text.charCodeAt(index));
  };
  writeText(0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  writeText(8, "WAVE");
  writeText(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeText(36, "data");
  view.setUint32(40, dataBytes, true);
  let offset = 44;
  for (const sample of samples) {
    const clamped = Math.max(-1, Math.min(1, sample));
    const value = clamped < 0 ? Math.round(clamped * 32768) : Math.round(clamped * 32767);
    view.setInt16(offset, value, true);
    offset += 2;
  }
  return new Blob([buffer], {type: "audio/wav"});
}

function analyseSamples(samples) {
  let peak = 0;
  let sum = 0;
  for (const sample of samples) {
    peak = Math.max(peak, Math.abs(sample));
    sum += sample * sample;
  }
  return {peakDb: dbfs(peak), rmsDb: dbfs(Math.sqrt(sum / Math.max(1, samples.length))), clipped: peak >= 0.99};
}

function stopRecording(discard = false) {
  if (!recording) return;
  recording = false;
  window.clearTimeout(captureTimer);
  captureTimer = null;
  try { cueNode?.stop(); } catch (_) {}
  cueNode = null;
  document.querySelector("#stop-recording").disabled = true;
  document.querySelector("#record-count").textContent = discard ? "READY" : "REVIEW";
  if (discard || !audioContext || captureOriginContextTime === null || captureStartContextTime === null) {
    captureChunks = [];
    document.querySelector("#record-attempt").disabled = !microphoneStream;
    setRecorderStatus(discard ? "Recording stopped and discarded." : "No microphone frames were captured; please try again.", !discard);
    return;
  }
  const row = phrase();
  const sampleRate = audioContext.sampleRate;
  const phrasePlan = appState.recording.phrases.find((item) => item.phrase_id === row.phrase_id);
  const preGuardFrames = Math.round(0.5 * sampleRate);
  const phraseFrames = Math.round((row.end_seconds - row.start_seconds) * sampleRate);
  const postGuardFrames = Math.round(0.5 * sampleRate);
  const frameCount = preGuardFrames + phraseFrames + postGuardFrames;
  const startFrame = Math.round((captureStartContextTime - captureOriginContextTime) * sampleRate);
  const samples = assembleFrames(startFrame, frameCount);
  const metrics = analyseSamples(samples.subarray(preGuardFrames, preGuardFrames + phraseFrames));
  const trackSettings = microphoneStream.getAudioTracks()[0]?.getSettings?.() || {};
  const actualProcessing = {sample_rate: sampleRate, channel_count: 1};
  if (typeof trackSettings.echoCancellation === "boolean") actualProcessing.echo_cancellation = trackSettings.echoCancellation;
  if (typeof trackSettings.noiseSuppression === "boolean") actualProcessing.noise_suppression = trackSettings.noiseSuppression;
  if (typeof trackSettings.autoGainControl === "boolean") actualProcessing.automatic_gain_control = trackSettings.autoGainControl;
  recordedAttempt = {
    phraseId: row.phrase_id,
    captureId: `attempt-${randomHex(20)}`,
    blob: encodePcm24Wav(samples, sampleRate),
    previewBlob: encodePcm16PreviewWav(samples, sampleRate),
    preGuardFrames,
    phraseStartFrame: preGuardFrames,
    phraseEndFrame: preGuardFrames + phraseFrames,
    postGuardFrames,
    actualProcessing,
    metrics,
  };
  captureChunks = [];
  attemptObjectUrl = URL.createObjectURL(recordedAttempt.previewBlob);
  const attemptPlayer = document.querySelector("#attempt-player");
  const saveButton = document.querySelector("#save-recording");
  saveButton.disabled = true;
  attemptPlayer.onloadedmetadata = () => {
    if (Number.isFinite(attemptPlayer.duration) && attemptPlayer.duration > 0) {
      saveButton.disabled = false;
      setRecorderStatus(metrics.clipped
        ? "Attempt captured, but it may be clipping. Listen before saving."
        : "Attempt captured. Listen, then save or discard it.", metrics.clipped);
      return;
    }
    setRecorderStatus("The microphone signal was captured, but its listening preview has no duration. Please discard it and try again.", true);
  };
  attemptPlayer.onerror = () => {
    saveButton.disabled = true;
    setRecorderStatus("The microphone signal was captured, but the listening preview could not be loaded. Please discard it and try again.", true);
  };
  attemptPlayer.src = attemptObjectUrl;
  attemptPlayer.load();
  document.querySelector("#attempt-level").textContent =
    `Peak ${Number.isFinite(metrics.peakDb) ? metrics.peakDb.toFixed(1) : "−∞"} dBFS · RMS ${Number.isFinite(metrics.rmsDb) ? metrics.rmsDb.toFixed(1) : "−∞"} dBFS${metrics.clipped ? " · possible clipping" : ""}. This is a safety check, not a musical score.`;
  document.querySelector("#recorded-attempt").classList.remove("hidden");
  document.querySelector("#record-attempt").disabled = false;
  setRecorderStatus("Preparing the captured attempt for playback…");
}

function randomHex(length) {
  const bytes = new Uint8Array(Math.ceil(length / 2));
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("").slice(0, length);
}

function discardRecordedAttempt() {
  if (attemptObjectUrl) URL.revokeObjectURL(attemptObjectUrl);
  attemptObjectUrl = null;
  recordedAttempt = null;
  const attemptPlayer = document.querySelector("#attempt-player");
  attemptPlayer.onloadedmetadata = null;
  attemptPlayer.onerror = null;
  attemptPlayer.pause();
  attemptPlayer.removeAttribute("src");
  attemptPlayer.load();
  document.querySelector("#recorded-attempt").classList.add("hidden");
}

async function blobBase64(blob) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 32768) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 32768));
  }
  return btoa(binary);
}

async function saveRecordedAttempt() {
  if (!recordedAttempt || recordedAttempt.phraseId !== activePhraseId) return;
  const vaultMode = appState.recording.save_url === "/api/candidate";
  const transitionRequired = !vaultMode && Boolean(appState.recording.transition_required);
  const confirmation = vaultMode
    ? "Keep this recording as an unreviewed local candidate? It will not change the Musical State or choose this take."
    : (transitionRequired
    ? "Start an explicit new recording round and save this unreviewed source? The target phrase will reopen. Earlier decisions remain immutable; only choices whose phrase and source hashes are unchanged will be revalidated."
    : "Save this recording as a new unreviewed phrase source? This does not choose or correct it.");
  if (!window.confirm(confirmation)) return;
  const button = document.querySelector("#save-recording");
  button.disabled = true;
  try {
    const phrasePlan = appState.recording.phrases.find((item) => item.phrase_id === recordedAttempt.phraseId);
    const payload = {
      expected_musical_state_sha256: appState.session.binding.musical_state_sha256,
      phrase_id: recordedAttempt.phraseId,
      capture_id: recordedAttempt.captureId,
      cue_id: phrasePlan.cue.cue_id,
      cue_asset_sha256: phrasePlan.cue.audio_sha256,
      audio_wav_base64: await blobBase64(recordedAttempt.blob),
      placement: {
        source_phrase_start_frame: recordedAttempt.phraseStartFrame,
        source_phrase_end_frame: recordedAttempt.phraseEndFrame,
        pre_guard_frames: recordedAttempt.preGuardFrames,
        post_guard_frames: recordedAttempt.postGuardFrames,
        destination_start_seconds: phrasePlan.placement.destination_start_seconds,
        destination_end_seconds: phrasePlan.placement.destination_end_seconds,
      },
      actual_processing: recordedAttempt.actualProcessing,
    };
    if (transitionRequired) payload.transition = phrasePlan.transition;
    const result = await api(appState.recording.save_url, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    discardRecordedAttempt();
    appState = result.state;
    activeSourceId = result.candidate?.source_id || result.admission?.source_id || null;
    draftNotes = {...(appState.draft?.draft?.notes_by_phrase || draftNotes)};
    render();
    showNotice(result.candidate
      ? "Candidate kept locally. It is available for the working draft and has not been selected."
      : (result.transition
      ? "New round saved. The target phrase is open; unchanged earlier decisions were explicitly revalidated. No take was selected."
      : "Recording saved locally as an unreviewed phrase source. No take was selected."));
  } catch (error) {
    showNotice(error.message, true);
    setRecorderStatus(`Attempt was not saved: ${error.message}`, true);
  } finally {
    button.disabled = false;
  }
}

document.querySelector("#enable-mic").addEventListener("click", enableMicrophone);
document.querySelector("#record-attempt").addEventListener("click", startRecording);
document.querySelector("#stop-recording").addEventListener("click", () => stopRecording(true));
document.querySelector("#save-recording").addEventListener("click", saveRecordedAttempt);
document.querySelector("#discard-attempt").addEventListener("click", () => {
  discardRecordedAttempt();
  setRecorderStatus("Attempt discarded. Ready to record again.");
});
window.addEventListener("beforeunload", () => microphoneStream?.getTracks().forEach((track) => track.stop()));

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
