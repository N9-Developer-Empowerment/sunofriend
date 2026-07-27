(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.SunofriendWorkbenchMasterReview = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";

  const CHOICES = Object.freeze([
    ["candidate_a", "Candidate A"],
    ["candidate_b", "Candidate B"],
    ["equivalent", "Equivalent"],
    ["neither", "Neither is useful"],
    ["cannot_tell", "Cannot tell"],
  ]);
  const DEFAULT_MAXIMUM_TAGS = 8;
  const DEFAULT_MAXIMUM_NOTES = 2000;

  function createMasterReview(options = {}) {
    const api = options.api;
    const escapeHtml = options.escapeHtml || escape;
    const pauseOtherAudio = options.pauseOtherAudio || (() => {});
    const onComparisonChange =
      options.onComparisonChange || (() => {});
    if (typeof api !== "function") throw new Error("Master review needs an API");

    let artifacts = null;
    let artifactKey = "";
    let comparison = null;
    let holder = null;
    let requestSequence = 0;
    let activeAudio = null;
    let sharedPosition = 0;
    let errorMessage = "";
    let busyMessage = "";
    let requestInFlight = false;
    let draft = emptyDraft();

    function setArtifacts(next) {
      const checked = normalizeArtifacts(next);
      const nextKey = checked ? artifactIdentity(checked) : "";
      if (nextKey !== artifactKey) {
        requestSequence += 1;
        stopAudio();
        artifactKey = nextKey;
        comparison = null;
        errorMessage = "";
        busyMessage = "";
        requestInFlight = false;
        draft = emptyDraft();
      }
      artifacts = checked;
      return apiObject;
    }

    function setComparison(next) {
      if (next == null) {
        comparison = null;
        draft = emptyDraft();
        return apiObject;
      }
      const checked = normalizeComparison(next);
      if (artifacts && !comparisonMatchesArtifacts(checked, artifacts)) {
        return apiObject;
      }
      if (
        comparison?.comparison_sha256 !== checked.comparison_sha256 ||
        checked.status === "reviewed" ||
        checked.status === "resolved"
      ) {
        draft = draftFromComparison(checked);
      }
      comparison = checked;
      return apiObject;
    }

    function renderInto(element) {
      stopAudio();
      holder = element || null;
      if (!holder) return;
      if (!artifacts) {
        holder.innerHTML =
          '<p class="muted">Create the exact current balanced control and ' +
          "Listening Master challenger before starting a blind review.</p>";
        return;
      }
      if (!comparison) {
        holder.innerHTML = prepareHtml(escapeHtml, errorMessage, busyMessage);
        wirePrepare();
        return;
      }
      holder.innerHTML = comparisonHtml(
        comparison,
        draft,
        escapeHtml,
        errorMessage,
        busyMessage,
      );
      if (comparison.status === "unreviewed") wireDraft();
      if (comparison.status === "reviewed") wireResolve();
    }

    function reset() {
      requestSequence += 1;
      stopAudio();
      artifacts = null;
      artifactKey = "";
      comparison = null;
      holder = null;
      sharedPosition = 0;
      errorMessage = "";
      busyMessage = "";
      requestInFlight = false;
      draft = emptyDraft();
    }

    function stopAudio() {
      if (activeAudio) {
        try {
          activeAudio.pause();
        } catch {}
      }
      if (holder?.querySelectorAll) {
        holder
          .querySelectorAll("[data-master-review-audio]")
          .forEach((audio) => {
            try {
              audio.pause();
            } catch {}
          });
      }
      activeAudio = null;
    }

    function wirePrepare() {
      const button = holder?.querySelector?.("#prepare-master-review");
      if (!button) return;
      button.onclick = async () => {
        if (requestInFlight) return;
        const start = Number(
          holder.querySelector("#master-review-start")?.value,
        );
        const end = Number(holder.querySelector("#master-review-end")?.value);
        if (
          !Number.isFinite(start) ||
          !Number.isFinite(end) ||
          start < 0 ||
          end - start < 0.5 ||
          end - start > 15
        ) {
          errorMessage =
            "Choose one window between 0.5 and 15 seconds with a non-negative start.";
          renderInto(holder);
          return;
        }
        const requestId = ++requestSequence;
        requestInFlight = true;
        busyMessage = "Preparing the exact local blind comparison…";
        errorMessage = "";
        renderInto(holder);
        try {
          const response = await api("/api/listening-master-review/prepare", {
            method: "POST",
            body: JSON.stringify({
              selection_manifest_sha256:
                artifacts.selection_manifest_sha256,
              balanced_arrangement_manifest_sha256:
                artifacts.balanced_arrangement_manifest_sha256,
              listening_master_manifest_sha256:
                artifacts.listening_master_manifest_sha256,
              start_seconds: start,
              end_seconds: end,
            }),
          });
          if (requestId !== requestSequence) return;
          const received = response.comparison || response.review;
          const checked = normalizeComparison(received);
          if (!comparisonMatchesArtifacts(checked, artifacts)) {
            requestInFlight = false;
            busyMessage = "";
            errorMessage =
              "The control or challenger changed; reload before reviewing.";
            renderInto(holder);
            return;
          }
          comparison = checked;
          draft = draftFromComparison(checked);
          requestInFlight = false;
          busyMessage = "";
          onComparisonChange(comparison);
          renderInto(holder);
        } catch (error) {
          if (requestId !== requestSequence) return;
          requestInFlight = false;
          busyMessage = "";
          errorMessage = error?.message || String(error);
          renderInto(holder);
        }
      };
    }

    function wireDraft() {
      const audios = {
        candidate_a: holder?.querySelector?.("#master-review-audio-a"),
        candidate_b: holder?.querySelector?.("#master-review-audio-b"),
      };
      for (const candidate of Object.keys(audios)) {
        const audio = audios[candidate];
        if (!audio) continue;
        audio.loop = true;
        // The server-generated private WAV already contains the fixed-window
        // attenuation. Browser gain must stay at unity or the louder input
        // would be attenuated twice.
        audio.volume = 1;
        audio.ontimeupdate = () => {
          if (audio === activeAudio && Number.isFinite(audio.currentTime)) {
            sharedPosition = audio.currentTime;
            updatePosition();
          }
        };
        audio.onended = () => {
          if (audio === activeAudio) activeAudio = null;
        };
      }
      holder
        ?.querySelectorAll?.("[data-master-review-play]")
        .forEach((button) => {
          button.onclick = async () => {
            const candidate = button.dataset.masterReviewPlay;
            const target = audios[candidate];
            if (!target) return;
            pauseOtherAudio();
            for (const audio of Object.values(audios)) {
              if (audio && audio !== target) audio.pause();
            }
            if (activeAudio && Number.isFinite(activeAudio.currentTime)) {
              sharedPosition = activeAudio.currentTime;
            }
            const maximum = Number.isFinite(target.duration)
              ? Math.max(0, target.duration - 0.01)
              : sharedPosition;
            target.currentTime = Math.min(sharedPosition, maximum);
            activeAudio = target;
            try {
              await target.play();
            } catch (error) {
              errorMessage = error?.message || String(error);
              renderInto(holder);
            }
          };
        });
      const pause = holder?.querySelector?.("#pause-master-review");
      if (pause) {
        pause.onclick = () => {
          if (activeAudio && Number.isFinite(activeAudio.currentTime)) {
            sharedPosition = activeAudio.currentTime;
            activeAudio.pause();
          }
          activeAudio = null;
          updatePosition();
        };
      }
      const stop = holder?.querySelector?.("#stop-master-review");
      if (stop) {
        stop.onclick = () => {
          stopAudio();
          sharedPosition = 0;
          for (const audio of Object.values(audios)) {
            if (audio) audio.currentTime = 0;
          }
          updatePosition();
        };
      }
      holder
        ?.querySelectorAll?.("[data-master-review-heard]")
        .forEach((input) => {
          input.onchange = () => {
            draft.heard[input.dataset.masterReviewHeard] = !!input.checked;
            updateCompletionState();
          };
        });
      holder
        ?.querySelectorAll?.('input[name="master-review-choice"]')
        .forEach((input) => {
          input.onchange = () => {
            if (input.checked) draft.choice = input.value;
            updateCompletionState();
          };
        });
      holder
        ?.querySelectorAll?.("[data-master-review-tag]")
        .forEach((input) => {
          input.onchange = () => {
            const candidate = input.dataset.masterReviewCandidate;
            const selected = new Set(draft.problem_tags[candidate] || []);
            if (input.checked) selected.add(input.value);
            else selected.delete(input.value);
            const maximum = maximumProblemTags(comparison);
            if (selected.size > maximum) {
              input.checked = false;
              errorMessage = `Choose no more than ${maximum} problem tags for one candidate.`;
              renderInto(holder);
              return;
            }
            draft.problem_tags[candidate] = [...selected].sort();
            updateCompletionState();
          };
        });
      const notes = holder?.querySelector?.("#master-review-notes");
      if (notes) {
        notes.oninput = () => {
          draft.notes = String(notes.value || "").slice(
            0,
            maximumNotes(comparison),
          );
        };
      }
      const complete = holder?.querySelector?.("#complete-master-review");
      if (complete) complete.onclick = completeReview;
      updateCompletionState();
      updatePosition();
    }

    async function completeReview() {
      if (requestInFlight || !draftComplete(draft)) return;
      const requestId = ++requestSequence;
      requestInFlight = true;
      busyMessage = "Saving the explicit blind review locally…";
      errorMessage = "";
      renderInto(holder);
      try {
        const response = await api("/api/listening-master-review", {
          method: "POST",
          body: JSON.stringify({
            comparison_sha256: comparison.comparison_sha256,
            expected_revision: Number(comparison.expected_revision || 0),
            heard: {
              candidate_a: draft.heard.candidate_a,
              candidate_b: draft.heard.candidate_b,
            },
            choice: draft.choice,
            problem_tags: {
              candidate_a: [...draft.problem_tags.candidate_a],
              candidate_b: [...draft.problem_tags.candidate_b],
            },
            notes: draft.notes,
          }),
        });
        if (requestId !== requestSequence) return;
        const received = normalizeComparison(
          response.review || response.comparison,
        );
        if (
          received.comparison_sha256 !== comparison.comparison_sha256 ||
          !comparisonMatchesArtifacts(received, artifacts)
        ) {
          requestInFlight = false;
          busyMessage = "";
          errorMessage =
            "The comparison changed while feedback was being saved; reload it.";
          renderInto(holder);
          return;
        }
        comparison = received;
        draft = draftFromComparison(received);
        requestInFlight = false;
        busyMessage = "";
        onComparisonChange(comparison);
        renderInto(holder);
      } catch (error) {
        if (requestId !== requestSequence) return;
        requestInFlight = false;
        busyMessage = "";
        errorMessage = error?.message || String(error);
        renderInto(holder);
      }
    }

    function wireResolve() {
      const button = holder?.querySelector?.("#resolve-master-review");
      if (!button) return;
      button.onclick = async () => {
        if (requestInFlight) return;
        const reviewSha = comparison?.review?.review_sha256;
        const reviewId = comparison?.review?.review_id;
        if (
          typeof reviewSha !== "string" ||
          typeof reviewId !== "string"
        ) return;
        const requestId = ++requestSequence;
        requestInFlight = true;
        busyMessage = "Verifying the blind review before revealing identities…";
        errorMessage = "";
        renderInto(holder);
        try {
          const response = await api(
            "/api/listening-master-review/resolve",
            {
              method: "POST",
              body: JSON.stringify({
                comparison_sha256: comparison.comparison_sha256,
                review_id: reviewId,
                review_sha256: reviewSha,
              }),
            },
          );
          if (requestId !== requestSequence) return;
          const received = normalizeComparison(
            response.result || response.comparison,
          );
          if (
            received.comparison_sha256 !== comparison.comparison_sha256 ||
            !comparisonMatchesArtifacts(received, artifacts)
          ) {
            requestInFlight = false;
            busyMessage = "";
            errorMessage =
              "The comparison changed before resolution; reload it.";
            renderInto(holder);
            return;
          }
          comparison = received;
          requestInFlight = false;
          busyMessage = "";
          onComparisonChange(comparison);
          renderInto(holder);
        } catch (error) {
          if (requestId !== requestSequence) return;
          requestInFlight = false;
          busyMessage = "";
          errorMessage = error?.message || String(error);
          renderInto(holder);
        }
      };
    }

    function updateCompletionState() {
      const complete = holder?.querySelector?.("#complete-master-review");
      if (complete) {
        complete.disabled = requestInFlight || !draftComplete(draft);
      }
      const status = holder?.querySelector?.("#master-review-draft-status");
      if (status) {
        status.textContent = draftComplete(draft)
          ? "Ready to save. Identity remains hidden until a separate resolve action."
          : "Hear and explicitly confirm both candidates, then choose one outcome.";
      }
    }

    function updatePosition() {
      const output = holder?.querySelector?.("#master-review-position");
      if (output) output.textContent = `${sharedPosition.toFixed(2)}s`;
    }

    const apiObject = {
      setArtifacts,
      setComparison,
      renderInto,
      reset,
      stopAudio,
      snapshot: () => ({
        artifact_key: artifactKey,
        comparison_status: comparison?.status || null,
        comparison_sha256: comparison?.comparison_sha256 || null,
        heard: { ...draft.heard },
        choice: draft.choice,
        playing: !!activeAudio,
        persisted: comparison?.status === "reviewed" ||
          comparison?.status === "resolved",
      }),
    };
    return apiObject;
  }

  function normalizeArtifacts(value) {
    if (!value) return null;
    const keys = [
      "selection_manifest_sha256",
      "balanced_arrangement_manifest_sha256",
      "listening_master_manifest_sha256",
    ];
    const checked = {};
    for (const key of keys) {
      if (!isSha256(value[key])) return null;
      checked[key] = String(value[key]);
    }
    return checked;
  }

  function normalizeComparison(value) {
    if (!value || typeof value !== "object") {
      throw new Error("Blind master review evidence is unavailable");
    }
    if (
      !["unreviewed", "reviewed", "resolved"].includes(value.status) ||
      !isSha256(value.comparison_sha256) ||
      !isSha256(value.selection_manifest_sha256) ||
      !isSha256(value.balanced_arrangement_manifest_sha256) ||
      !isSha256(value.listening_master_manifest_sha256)
    ) {
      throw new Error("Blind master review evidence is invalid");
    }
    if (value.status === "unreviewed") {
      for (const candidate of ["candidate_a", "candidate_b"]) {
        const record = value.candidates?.[candidate];
        if (
          !record ||
          typeof record.audio_url !== "string" ||
          [
            "identity",
            "applied_gain_db",
            "rms_dbfs",
            "sample_peak_dbfs",
          ].some((key) => Object.hasOwn(record, key))
        ) {
          throw new Error("Blind candidate audio evidence is invalid");
        }
      }
      const anonymousCandidates = JSON.stringify(value.candidates);
      if (
        anonymousCandidates.includes("balanced_control") ||
        anonymousCandidates.includes("listening_master") ||
        value.assignment != null ||
        value.result != null
      ) {
        throw new Error("Blind candidate identity was revealed before review");
      }
    }
    return value;
  }

  function comparisonMatchesArtifacts(value, current) {
    return !!(
      value &&
      current &&
      value.selection_manifest_sha256 === current.selection_manifest_sha256 &&
      value.balanced_arrangement_manifest_sha256 ===
        current.balanced_arrangement_manifest_sha256 &&
      value.listening_master_manifest_sha256 ===
        current.listening_master_manifest_sha256
    );
  }

  function prepareHtml(escapeHtml, errorMessage, busyMessage) {
    return `<section class="diagnostics" aria-labelledby="master-review-heading">
      <h5 id="master-review-heading">Blind listening review</h5>
      <p>Choose one representative 0.5–15 second window. Sunofriend will
      compare the exact control and challenger at matched fixed-window sample
      RMS, hiding which is A and B. This judges processing quality without a
      simple louder-is-better advantage.</p>
      <p class="muted">The comparison attenuates only the louder crop. It is
      not LUFS, true-peak or perceived-loudness matching and it changes no
      source file, MIDI, mix, selection, default or GarageBand pack.</p>
      <div class="loop">
        <label>Start (seconds)<input id="master-review-start" type="number"
          min="0" step="0.1" value="0"></label>
        <label>End (seconds)<input id="master-review-end" type="number"
          min="0.5" step="0.1" value="10"></label>
        <button id="prepare-master-review" class="primary" type="button"
          ${busyMessage ? "disabled" : ""}>Prepare blind comparison</button>
      </div>
      ${statusHtml(escapeHtml, errorMessage, busyMessage)}
    </section>`;
  }

  function comparisonHtml(
    review,
    draft,
    escapeHtml,
    errorMessage,
    busyMessage,
  ) {
    if (review.status === "reviewed") {
      return reviewedHtml(review, escapeHtml, errorMessage, busyMessage);
    }
    if (review.status === "resolved") {
      return resolvedHtml(review, escapeHtml, errorMessage, busyMessage);
    }
    const start = finiteDisplay(review.window?.start_seconds);
    const end = finiteDisplay(review.window?.end_seconds);
    const tags = Array.isArray(review.allowed_problem_tags)
      ? review.allowed_problem_tags
      : [];
    return `<section class="diagnostics" aria-labelledby="master-review-heading">
      <h5 id="master-review-heading">Blind level-matched quality review</h5>
      <p><b>Window:</b> ${escapeHtml(start)}–${escapeHtml(end)} seconds.
      Candidate identity is hidden. Both artifact crops use the same exact
      frame indices and only the louder crop was attenuated.</p>
      <p class="muted">The switch uses one browser playhead and is intended
      for close local comparison; it is not a sample-accurate mastering meter.
      Playback alone records no feedback.</p>
      <div class="switcher" role="group" aria-label="Blind A B transport">
        <button type="button" data-master-review-play="candidate_a">Play / switch to A</button>
        <button type="button" data-master-review-play="candidate_b">Play / switch to B</button>
        <button id="pause-master-review" type="button">Pause</button>
        <button id="stop-master-review" type="button">Stop</button>
        <output id="master-review-position">0.00s</output>
      </div>
      <audio id="master-review-audio-a" data-master-review-audio
        aria-label="Blind Candidate A" preload="metadata"
        src="${escapeHtml(review.candidates.candidate_a.audio_url)}"></audio>
      <audio id="master-review-audio-b" data-master-review-audio
        aria-label="Blind Candidate B" preload="metadata"
        src="${escapeHtml(review.candidates.candidate_b.audio_url)}"></audio>
      <fieldset>
        <legend>Confirm what you heard</legend>
        ${heardCheckbox("candidate_a", "I heard Candidate A", draft)}
        ${heardCheckbox("candidate_b", "I heard Candidate B", draft)}
      </fieldset>
      <fieldset>
        <legend>Which is more musically useful at the matched review level?</legend>
        ${CHOICES.map(([value, label]) =>
          choiceRadio(value, label, draft),
        ).join("")}
      </fieldset>
      <div class="candidate-grid">
        ${problemFieldset(
          "candidate_a",
          "Problems heard in Candidate A",
          tags,
          draft,
          escapeHtml,
        )}
        ${problemFieldset(
          "candidate_b",
          "Problems heard in Candidate B",
          tags,
          draft,
          escapeHtml,
        )}
      </div>
      <label>Optional private note
        <textarea id="master-review-notes" maxlength="${maximumNotes(review)}"
          rows="4">${escapeHtml(draft.notes)}</textarea>
      </label>
      <p id="master-review-draft-status" class="muted"></p>
      <button id="complete-master-review" class="primary" type="button"
        disabled>Complete blind review</button>
      ${statusHtml(escapeHtml, errorMessage, busyMessage)}
      <p class="muted">Completing records only this explicit receipt-bound
      feedback. It does not reveal or promote a winner. Identity resolution is
      a separate action.</p>
    </section>`;
  }

  function reviewedHtml(review, escapeHtml, errorMessage, busyMessage) {
    const record = review.review || {};
    return `<section class="success" aria-labelledby="master-review-heading">
      <h5 id="master-review-heading">Blind review saved</h5>
      <p>Your choice <b>${escapeHtml(choiceLabel(record.choice))}</b> is bound
      to this exact control, challenger, review window and anonymous A/B
      assignment. Identity is still hidden.</p>
      <p>${record.review_url
        ? `<a href="${escapeHtml(record.review_url)}" download>Export reviewed blind JSON</a>`
        : "The reviewed JSON is stored locally."}</p>
      <button id="resolve-master-review" class="primary" type="button"
        ${busyMessage ? "disabled" : ""}>Resolve A/B identities</button>
      ${statusHtml(escapeHtml, errorMessage, busyMessage)}
      <p class="muted">Resolving verifies and reveals the mapping. It still
      changes no MIDI, mix, selection, ranking, default, product completion or
      GarageBand pack.</p>
    </section>`;
  }

  function resolvedHtml(review, escapeHtml, errorMessage, busyMessage) {
    const result = review.result || review;
    const mapping = result.assignment || {};
    const resolved = result.resolved_choice || "cannot_tell";
    return `<section class="success" aria-labelledby="master-review-heading">
      <h5 id="master-review-heading">Blind review resolved</h5>
      <p><b>Candidate A:</b> ${escapeHtml(identityLabel(mapping.candidate_a))}
      · <b>Candidate B:</b> ${escapeHtml(identityLabel(mapping.candidate_b))}</p>
      <p><b>Resolved outcome:</b> ${escapeHtml(identityLabel(resolved))}</p>
      <p>${result.result_url
        ? `<a href="${escapeHtml(result.result_url)}" download>Export resolved review JSON</a>`
        : "The resolved result is stored locally."}</p>
      ${statusHtml(escapeHtml, errorMessage, busyMessage)}
      <p class="muted">This is explicit listening evidence, not an automatic
      promotion. The balanced control remains required and the Listening
      Master remains a comparative challenger.</p>
    </section>`;
  }

  function heardCheckbox(candidate, label, draft) {
    return `<label><input type="checkbox"
      data-master-review-heard="${candidate}"
      ${draft.heard[candidate] ? "checked" : ""}> ${label}</label>`;
  }

  function choiceRadio(value, label, draft) {
    return `<label><input type="radio" name="master-review-choice"
      value="${value}" ${draft.choice === value ? "checked" : ""}>
      ${label}</label>`;
  }

  function problemFieldset(
    candidate,
    legend,
    tags,
    draft,
    escapeHtml,
  ) {
    const selected = new Set(draft.problem_tags[candidate] || []);
    return `<fieldset><legend>${legend}</legend><div class="problems">
      ${tags.map((tag) => `<label><input type="checkbox"
        data-master-review-tag data-master-review-candidate="${candidate}"
        value="${escapeHtml(tag)}" ${selected.has(tag) ? "checked" : ""}>
        ${escapeHtml(tag.replaceAll("_", " "))}</label>`).join("")}
      </div></fieldset>`;
  }

  function statusHtml(escapeHtml, errorMessage, busyMessage) {
    if (errorMessage) {
      return `<p class="error" role="alert">${escapeHtml(errorMessage)}</p>`;
    }
    if (busyMessage) {
      return `<p class="busy" role="status">${escapeHtml(busyMessage)}</p>`;
    }
    return '<p role="status" aria-live="polite"></p>';
  }

  function emptyDraft() {
    return {
      heard: { candidate_a: false, candidate_b: false },
      choice: null,
      problem_tags: { candidate_a: [], candidate_b: [] },
      notes: "",
    };
  }

  function draftFromComparison(value) {
    const response = value.review?.response || value.review || {};
    return {
      heard: {
        candidate_a: response.heard?.candidate_a === true,
        candidate_b: response.heard?.candidate_b === true,
      },
      choice: CHOICES.some(([choice]) => choice === response.choice)
        ? response.choice
        : null,
      problem_tags: {
        candidate_a: Array.isArray(response.problem_tags?.candidate_a)
          ? [...response.problem_tags.candidate_a]
          : [],
        candidate_b: Array.isArray(response.problem_tags?.candidate_b)
          ? [...response.problem_tags.candidate_b]
          : [],
      },
      notes: typeof response.notes === "string" ? response.notes : "",
    };
  }

  function draftComplete(value) {
    return !!(
      value.heard.candidate_a &&
      value.heard.candidate_b &&
      CHOICES.some(([choice]) => choice === value.choice)
    );
  }

  function maximumProblemTags(value) {
    const count = Number(value?.maximum_problem_tags);
    return Number.isInteger(count) && count > 0
      ? count
      : DEFAULT_MAXIMUM_TAGS;
  }

  function maximumNotes(value) {
    const count = Number(value?.maximum_notes_characters);
    return Number.isInteger(count) && count > 0
      ? count
      : DEFAULT_MAXIMUM_NOTES;
  }

  function finiteDisplay(value) {
    return Number.isFinite(Number(value))
      ? Number(value).toFixed(3).replace(/\.?0+$/, "")
      : "unknown";
  }

  function choiceLabel(value) {
    return CHOICES.find(([choice]) => choice === value)?.[1] || "Cannot tell";
  }

  function identityLabel(value) {
    if (value === "balanced_control") return "Balanced control";
    if (value === "listening_master") return "Listening Master challenger";
    if (value === "equivalent") return "Equivalent";
    if (value === "neither") return "Neither";
    if (value === "cannot_tell") return "Cannot tell";
    return String(value || "Unavailable");
  }

  function artifactIdentity(value) {
    return [
      value.selection_manifest_sha256,
      value.balanced_arrangement_manifest_sha256,
      value.listening_master_manifest_sha256,
    ].join(":");
  }

  function isSha256(value) {
    return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
  }

  function escape(value) {
    return String(value ?? "").replace(
      /[&<>"']/g,
      (character) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[character],
    );
  }

  return {
    CHOICES,
    createMasterReview,
    normalizeArtifacts,
    normalizeComparison,
  };
});
