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
  const READINESS_CHOICES = Object.freeze([
    ["balanced_control", "Balanced control"],
    ["listening_master", "Listening Master challenger"],
    ["equivalent", "Equivalent readiness"],
    ["neither", "Neither is ready"],
    ["cannot_tell", "Cannot tell"],
  ]);
  const READINESS_IDENTITIES = Object.freeze([
    "balanced_control",
    "listening_master",
  ]);
  const READINESS_COMPARISON_SCHEMA =
    "sunofriend.workbench-listening-master-native-readiness-comparison.v1";
  const READINESS_POLICY =
    "identity-labelled-native-level-exact-window-pcm24-v1";
  const READINESS_AUDIO_POLICY =
    "exact-frame-native-level-zero-gain-pcm24-v1";
  const READINESS_EFFECT_KEYS = Object.freeze([
    "feedback_recorded",
    "readiness_review_record_created",
    "quality_review_mutated",
    "quality_resolution_mutated",
    "source_audio_mutated",
    "balanced_control_mutated",
    "listening_master_mutated",
    "midi_mutated",
    "selection_changed",
    "automatic_selection",
    "automatic_ranking",
    "default_selection_changed",
    "pack_changed",
    "product_completion_changed",
  ]);
  const READINESS_FORBIDDEN_EFFECTS = Object.freeze(
    READINESS_EFFECT_KEYS.filter(
      (key) =>
        key !== "feedback_recorded" &&
        key !== "readiness_review_record_created",
    ),
  );
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
    let readinessDraft = emptyReadinessDraft();

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
        readinessDraft = emptyReadinessDraft();
      }
      artifacts = checked;
      return apiObject;
    }

    function setComparison(next) {
      if (next == null) {
        if (comparison !== null) {
          requestSequence += 1;
          stopAudio();
          requestInFlight = false;
          errorMessage = "";
          busyMessage = "";
        }
        comparison = null;
        draft = emptyDraft();
        readinessDraft = emptyReadinessDraft();
        return apiObject;
      }
      const checked = normalizeComparison(next);
      if (artifacts && !comparisonMatchesArtifacts(checked, artifacts)) {
        return apiObject;
      }
      const previousIdentity = comparisonIdentity(comparison);
      const nextIdentity = comparisonIdentity(checked);
      if (previousIdentity && previousIdentity !== nextIdentity) {
        requestSequence += 1;
        stopAudio();
        requestInFlight = false;
        errorMessage = "";
        busyMessage = "";
      }
      if (
        comparison?.comparison_sha256 !== checked.comparison_sha256 ||
        checked.status === "reviewed" ||
        checked.status === "resolved"
      ) {
        draft = draftFromComparison(checked);
      }
      const previousReadiness = comparison?.readiness;
      if (
        !checked.readiness ||
        previousReadiness?.comparison_sha256 !==
          checked.readiness.comparison_sha256 ||
        checked.readiness.status === "reviewed"
      ) {
        readinessDraft = checked.readiness
          ? readinessDraftFromComparison(checked.readiness)
          : emptyReadinessDraft();
        sharedPosition = 0;
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
        readinessDraft,
        escapeHtml,
        errorMessage,
        busyMessage,
      );
      if (comparison.status === "unreviewed") wireDraft();
      if (comparison.status === "reviewed") wireResolve();
      if (comparison.status === "resolved") {
        if (!comparison.readiness) wireReadinessPrepare();
        else if (comparison.readiness.status === "unreviewed") {
          wireReadinessDraft();
        }
      }
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
      readinessDraft = emptyReadinessDraft();
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
        holder
          .querySelectorAll("[data-master-readiness-audio]")
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

    function wireReadinessPrepare() {
      const button = holder?.querySelector?.("#prepare-master-readiness");
      if (!button) return;
      button.onclick = async () => {
        if (requestInFlight || comparison?.status !== "resolved") return;
        const quality = qualityResolutionBinding(comparison);
        if (!quality) {
          errorMessage =
            "The resolved quality-review receipt is incomplete; reload it before stage 2.";
          renderInto(holder);
          return;
        }
        const requestedComparisonIdentity = comparisonIdentity(comparison);
        const requestedArtifactKey = artifactKey;
        const requestId = ++requestSequence;
        requestInFlight = true;
        busyMessage =
          "Preparing the identity-labelled native-level comparison…";
        errorMessage = "";
        renderInto(holder);
        try {
          const response = await api(
            "/api/listening-master-readiness/prepare",
            {
              method: "POST",
              body: JSON.stringify({
                quality_review_id: quality.review_id,
                quality_review_sha256: quality.review_sha256,
                quality_result_sha256: quality.result_sha256,
              }),
            },
          );
          if (
            requestId !== requestSequence ||
            artifactKey !== requestedArtifactKey ||
            comparisonIdentity(comparison) !== requestedComparisonIdentity
          ) return;
          const checked = normalizeReadiness(response.readiness, comparison);
          if (!readinessMatchesResolution(checked, comparison)) {
            requestInFlight = false;
            busyMessage = "";
            errorMessage =
              "The quality review or one of its artifacts changed; reload before stage 2.";
            renderInto(holder);
            return;
          }
          comparison = normalizeComparison({
            ...comparison,
            readiness: checked,
          });
          readinessDraft = readinessDraftFromComparison(checked);
          sharedPosition = 0;
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

    function wireReadinessDraft() {
      const readiness = comparison?.readiness;
      if (!readiness || readiness.status !== "unreviewed") return;
      const audios = {
        balanced_control: holder?.querySelector?.(
          "#master-readiness-audio-balanced-control",
        ),
        listening_master: holder?.querySelector?.(
          "#master-readiness-audio-listening-master",
        ),
      };
      for (const identity of READINESS_IDENTITIES) {
        const audio = audios[identity];
        if (!audio) continue;
        audio.loop = true;
        // Stage 2 deliberately preserves each native artifact level. The
        // browser adds zero gain and performs no matching or attenuation.
        audio.volume = 1;
        audio.ontimeupdate = () => {
          if (audio === activeAudio && Number.isFinite(audio.currentTime)) {
            sharedPosition = audio.currentTime;
            updateReadinessPosition();
          }
        };
        audio.onended = () => {
          if (audio === activeAudio) activeAudio = null;
        };
      }
      holder
        ?.querySelectorAll?.("[data-master-readiness-play]")
        .forEach((button) => {
          button.onclick = async () => {
            const identity = button.dataset.masterReadinessPlay;
            const target = audios[identity];
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
      const pause = holder?.querySelector?.("#pause-master-readiness");
      if (pause) {
        pause.onclick = () => {
          if (activeAudio && Number.isFinite(activeAudio.currentTime)) {
            sharedPosition = activeAudio.currentTime;
            activeAudio.pause();
          }
          activeAudio = null;
          updateReadinessPosition();
        };
      }
      const stop = holder?.querySelector?.("#stop-master-readiness");
      if (stop) {
        stop.onclick = () => {
          stopAudio();
          sharedPosition = 0;
          for (const audio of Object.values(audios)) {
            if (audio) audio.currentTime = 0;
          }
          updateReadinessPosition();
        };
      }
      holder
        ?.querySelectorAll?.("[data-master-readiness-heard]")
        .forEach((input) => {
          input.onchange = () => {
            readinessDraft.heard[input.dataset.masterReadinessHeard] =
              !!input.checked;
            updateReadinessCompletionState();
          };
        });
      holder
        ?.querySelectorAll?.('input[name="master-readiness-choice"]')
        .forEach((input) => {
          input.onchange = () => {
            if (input.checked) readinessDraft.choice = input.value;
            updateReadinessCompletionState();
          };
        });
      holder
        ?.querySelectorAll?.("[data-master-readiness-tag]")
        .forEach((input) => {
          input.onchange = () => {
            const identity = input.dataset.masterReadinessCandidate;
            const selected = new Set(
              readinessDraft.problem_tags[identity] || [],
            );
            if (input.checked) selected.add(input.value);
            else selected.delete(input.value);
            const maximum = maximumProblemTags(readiness);
            if (selected.size > maximum) {
              input.checked = false;
              errorMessage =
                `Choose no more than ${maximum} problem tags for one artifact.`;
              renderInto(holder);
              return;
            }
            readinessDraft.problem_tags[identity] = [...selected].sort();
            updateReadinessCompletionState();
          };
        });
      const notes = holder?.querySelector?.("#master-readiness-notes");
      if (notes) {
        notes.oninput = () => {
          readinessDraft.notes = String(notes.value || "").slice(
            0,
            maximumNotes(readiness),
          );
        };
      }
      const complete = holder?.querySelector?.(
        "#complete-master-readiness",
      );
      if (complete) complete.onclick = completeReadiness;
      updateReadinessCompletionState();
      updateReadinessPosition();
    }

    async function completeReadiness() {
      const readiness = comparison?.readiness;
      if (
        requestInFlight ||
        readiness?.status !== "unreviewed" ||
        !readinessDraftComplete(readinessDraft)
      ) return;
      const requestedComparisonIdentity = comparisonIdentity(comparison);
      const requestedReadinessSha = readiness.comparison_sha256;
      const requestedArtifactKey = artifactKey;
      const requestId = ++requestSequence;
      requestInFlight = true;
      busyMessage =
        "Saving the explicit identity-labelled readiness review locally…";
      errorMessage = "";
      renderInto(holder);
      try {
        const response = await api("/api/listening-master-readiness", {
          method: "POST",
          body: JSON.stringify({
            comparison_sha256: requestedReadinessSha,
            quality_review_id:
              readiness.quality_review.quality_review_id,
            quality_review_sha256:
              readiness.quality_review.quality_review_sha256,
            quality_result_sha256:
              readiness.quality_review.quality_result_sha256,
            heard: {
              balanced_control:
                readinessDraft.heard.balanced_control,
              listening_master:
                readinessDraft.heard.listening_master,
            },
            choice: readinessDraft.choice,
            problem_tags: {
              balanced_control: [
                ...readinessDraft.problem_tags.balanced_control,
              ],
              listening_master: [
                ...readinessDraft.problem_tags.listening_master,
              ],
            },
            notes: readinessDraft.notes,
          }),
        });
        if (
          requestId !== requestSequence ||
          artifactKey !== requestedArtifactKey ||
          comparisonIdentity(comparison) !== requestedComparisonIdentity ||
          comparison?.readiness?.comparison_sha256 !== requestedReadinessSha
        ) return;
        const received = normalizeReadiness(
          response.readiness,
          comparison,
        );
        if (
          received.status !== "reviewed" ||
          received.comparison_sha256 !== requestedReadinessSha ||
          !readinessMatchesResolution(received, comparison)
        ) {
          requestInFlight = false;
          busyMessage = "";
          errorMessage =
            "The native-level comparison changed while its review was being saved; reload it.";
          renderInto(holder);
          return;
        }
        comparison = normalizeComparison({
          ...comparison,
          readiness: received,
        });
        readinessDraft = readinessDraftFromComparison(received);
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

    function updateReadinessCompletionState() {
      const complete = holder?.querySelector?.(
        "#complete-master-readiness",
      );
      if (complete) {
        complete.disabled =
          requestInFlight || !readinessDraftComplete(readinessDraft);
      }
      const status = holder?.querySelector?.(
        "#master-readiness-draft-status",
      );
      if (status) {
        status.textContent = readinessDraftComplete(readinessDraft)
          ? "Ready to save this separate native-level readiness outcome."
          : "Hear and explicitly confirm both labelled artifacts, then choose one outcome.";
      }
    }

    function updatePosition() {
      const output = holder?.querySelector?.("#master-review-position");
      if (output) output.textContent = `${sharedPosition.toFixed(2)}s`;
    }

    function updateReadinessPosition() {
      const output = holder?.querySelector?.("#master-readiness-position");
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
        readiness_status: comparison?.readiness?.status || null,
        readiness_heard: { ...readinessDraft.heard },
        readiness_choice: readinessDraft.choice,
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
    if (value.status !== "resolved" && value.readiness != null) {
      throw new Error(
        "Native-level readiness evidence is unavailable before identity resolution",
      );
    }
    if (value.status === "resolved" && value.readiness != null) {
      return {
        ...value,
        readiness: normalizeReadiness(value.readiness, value),
      };
    }
    return value;
  }

  function normalizeReadiness(value, qualityComparison) {
    if (!value || typeof value !== "object") {
      throw new Error("Native-level readiness evidence is unavailable");
    }
    if (
      !hasExactKeys(value, [
        "schema",
        "status",
        "identity_labelled",
        "native_level",
        "comparison_sha256",
        "selection_manifest_sha256",
        "balanced_arrangement_manifest_sha256",
        "listening_master_manifest_sha256",
        "quality_review",
        "artifact_hashes",
        "window",
        "policy",
        "candidates",
        "choices",
        "problem_tags",
        "limits",
        "review",
        "effects",
      ]) ||
      !["unreviewed", "reviewed"].includes(value.status) ||
      value.schema !== READINESS_COMPARISON_SCHEMA ||
      value.identity_labelled !== true ||
      value.native_level !== true ||
      !isSha256(value.comparison_sha256)
    ) {
      throw new Error("Native-level readiness evidence is invalid");
    }
    if (!readinessMatchesResolution(value, qualityComparison)) {
      throw new Error(
        "Native-level readiness evidence is not bound to this quality review",
      );
    }
    if (
      !hasExactKeys(value.artifact_hashes, [
        "balanced_control_preview_sha256",
        "listening_master_wav_sha256",
        "listening_master_receipt_sha256",
      ]) ||
      !Object.values(value.artifact_hashes).every(isSha256)
    ) {
      throw new Error("Native-level readiness artifact hashes are invalid");
    }
    const window = value.window;
    if (
      !hasExactKeys(window, [
        "start_frame",
        "end_frame",
        "frame_count",
        "sample_rate",
        "start_seconds",
        "end_seconds",
        "duration_seconds",
        "recorded_zero",
        "alignment_inferred",
      ]) ||
      !Number.isSafeInteger(window.start_frame) ||
      !Number.isSafeInteger(window.end_frame) ||
      !Number.isSafeInteger(window.frame_count) ||
      !Number.isSafeInteger(window.sample_rate) ||
      window.start_frame < 0 ||
      window.end_frame <= window.start_frame ||
      window.frame_count !== window.end_frame - window.start_frame ||
      window.sample_rate <= 0 ||
      !Number.isFinite(window.start_seconds) ||
      !Number.isFinite(window.end_seconds) ||
      !Number.isFinite(window.duration_seconds) ||
      window.start_seconds !== window.start_frame / window.sample_rate ||
      window.end_seconds !== window.end_frame / window.sample_rate ||
      window.duration_seconds !== window.frame_count / window.sample_rate ||
      window.duration_seconds < 0.5 ||
      window.duration_seconds > 15 ||
      window.recorded_zero !== true ||
      window.alignment_inferred !== false
    ) {
      throw new Error("Native-level readiness window is invalid");
    }
    const candidateKeys = Object.keys(value.candidates || {}).sort();
    if (
      candidateKeys.length !== READINESS_IDENTITIES.length ||
      candidateKeys.some(
        (identity, index) =>
          identity !== [...READINESS_IDENTITIES].sort()[index],
      )
    ) {
      throw new Error("Native-level readiness candidates are invalid");
    }
    let candidateChannels = null;
    for (const identity of READINESS_IDENTITIES) {
      const record = value.candidates[identity];
      const expectedName = `${identity.replaceAll("_", "-")}.wav`;
      if (
        !record ||
        typeof record !== "object" ||
        !hasExactKeys(record, [
          "label",
          "format",
          "subtype",
          "sample_rate",
          "channels",
          "frames",
          "applied_gain_db",
          "processing_applied",
          "audio",
          "audio_url",
        ]) ||
        typeof record.audio_url !== "string" ||
        !record.audio_url.startsWith("/media/") ||
        record.label !== identityLabel(identity).replace(
          " challenger",
          "",
        ) ||
        record.format !== "WAV" ||
        record.subtype !== "PCM_24" ||
        !Number.isSafeInteger(record.sample_rate) ||
        record.sample_rate !== window.sample_rate ||
        !Number.isSafeInteger(record.channels) ||
        record.channels <= 0 ||
        !Number.isSafeInteger(record.frames) ||
        record.frames !== window.frame_count ||
        !hasExactKeys(record.audio, ["name", "bytes", "sha256"]) ||
        record.audio.name !== expectedName ||
        !Number.isSafeInteger(record.audio.bytes) ||
        record.audio.bytes <= 0 ||
        !isSha256(record.audio.sha256) ||
        record.applied_gain_db !== 0 ||
        record.processing_applied !== false
      ) {
        throw new Error("Native-level readiness candidate audio is invalid");
      }
      if (candidateChannels === null) candidateChannels = record.channels;
      if (record.channels !== candidateChannels) {
        throw new Error("Native-level readiness candidate geometry is invalid");
      }
    }
    if (
      !hasExactKeys(value.limits, [
        "maximum_problem_tags_per_identity",
        "maximum_notes_characters",
      ]) ||
      !Number.isInteger(
        value.limits.maximum_problem_tags_per_identity,
      ) ||
      value.limits.maximum_problem_tags_per_identity < 1 ||
      !Number.isInteger(value.limits.maximum_notes_characters) ||
      value.limits.maximum_notes_characters < 1
    ) {
      throw new Error("Native-level readiness limits are invalid");
    }
    const allowed = normalizedAllowedProblemTags(
      value.problem_tags,
    );
    if (
      !hasExactKeys(value.policy, [
        "name",
        "audio",
        "identity_hidden",
        "quality_review_resolved",
        "quality_review_latest",
        "exact_quality_frame_window_reused",
        "native_level_unchanged",
        "output_format",
        "output_subtype",
        "applied_gain_db",
        "gain_matching_used",
        "resampling_used",
        "limiter_used",
        "compression_used",
        "equalisation_used",
        "time_shift_seconds",
        "time_stretch_ratio",
      ]) ||
      value.policy.name !== READINESS_POLICY ||
      value.policy.audio !== READINESS_AUDIO_POLICY ||
      value.policy.identity_hidden !== false ||
      value.policy.quality_review_resolved !== true ||
      value.policy.quality_review_latest !== true ||
      value.policy.exact_quality_frame_window_reused !== true ||
      value.policy.native_level_unchanged !== true ||
      value.policy.output_format !== "WAV" ||
      value.policy.output_subtype !== "PCM_24" ||
      value.policy.applied_gain_db !== 0 ||
      value.policy.gain_matching_used !== false ||
      value.policy.resampling_used !== false ||
      value.policy.limiter_used !== false ||
      value.policy.compression_used !== false ||
      value.policy.equalisation_used !== false ||
      value.policy.time_shift_seconds !== 0 ||
      value.policy.time_stretch_ratio !== 1
    ) {
      throw new Error("Native-level readiness processing policy is invalid");
    }
    if (!validReadinessEffects(value.effects, value.status)) {
      throw new Error("Native-level readiness effects are invalid");
    }
    const projectedChoices = Array.isArray(value.choices)
      ? [...value.choices].sort()
      : [];
    const allowedChoices = READINESS_CHOICES
      .map(([choice]) => choice)
      .sort();
    if (
      projectedChoices.length !== allowedChoices.length ||
      projectedChoices.some(
        (choice, index) => choice !== allowedChoices[index],
      )
    ) {
      throw new Error("Native-level readiness choices are invalid");
    }
    if (value.status === "unreviewed") {
      if (value.review != null) {
        throw new Error(
          "Native-level readiness was marked reviewed without a response",
        );
      }
      return value;
    }
    const review = value.review;
    const response = review?.response;
    if (
      !review ||
      typeof review !== "object" ||
      !hasExactKeys(review, [
        "readiness_review_id",
        "readiness_review_sha256",
        "response",
        "choice",
        "review_url",
      ]) ||
      !isSha256(review.readiness_review_id) ||
      !isSha256(review.readiness_review_sha256) ||
      review.choice !== response?.choice ||
      typeof review.review_url !== "string" ||
      !review.review_url ||
      !response ||
      typeof response !== "object" ||
      !hasExactKeys(response, [
        "heard",
        "choice",
        "problem_tags",
        "notes",
      ]) ||
      !hasExactKeys(response.heard, READINESS_IDENTITIES) ||
      !hasExactKeys(response.problem_tags, READINESS_IDENTITIES) ||
      !READINESS_CHOICES.some(([choice]) => choice === response.choice) ||
      response.heard?.balanced_control !== true ||
      response.heard?.listening_master !== true ||
      typeof response.notes !== "string" ||
      response.notes.length > maximumNotes(value)
    ) {
      throw new Error("Native-level readiness review is invalid");
    }
    const maximum = maximumProblemTags(value);
    for (const identity of READINESS_IDENTITIES) {
      const tags = response.problem_tags?.[identity];
      if (
        !Array.isArray(tags) ||
        tags.length > maximum ||
        new Set(tags).size !== tags.length ||
        tags.some((tag) => !allowed.has(tag))
      ) {
        throw new Error(
          "Native-level readiness review problem tags are invalid",
        );
      }
    }
    return value;
  }

  function validReadinessEffects(value, status) {
    if (!hasExactKeys(value, READINESS_EFFECT_KEYS)) return false;
    if (
      typeof value.feedback_recorded !== "boolean" ||
      typeof value.readiness_review_record_created !== "boolean" ||
      value.feedback_recorded !== value.readiness_review_record_created ||
      READINESS_FORBIDDEN_EFFECTS.some((key) => value[key] !== false)
    ) {
      return false;
    }
    return status !== "unreviewed" || value.feedback_recorded === false;
  }

  function hasExactKeys(value, expected) {
    if (
      !value ||
      typeof value !== "object" ||
      Array.isArray(value)
    ) return false;
    const actual = Object.keys(value).sort();
    const wanted = [...expected].sort();
    return (
      actual.length === wanted.length &&
      actual.every((key, index) => key === wanted[index])
    );
  }

  function normalizedAllowedProblemTags(value) {
    if (
      !Array.isArray(value) ||
      value.some(
        (tag) =>
          typeof tag !== "string" ||
          !tag ||
          tag.length > 80 ||
          /[\r\n]/.test(tag),
      ) ||
      new Set(value).size !== value.length
    ) {
      throw new Error(
        "Native-level readiness problem-tag allowlist is invalid",
      );
    }
    return new Set(value);
  }

  function qualityResolutionBinding(value) {
    if (value?.status !== "resolved") return null;
    const reviewId = value.review?.review_id;
    const reviewSha = value.review?.review_sha256;
    const resultSha = value.result?.result_sha256;
    const comparisonSha = value.comparison_sha256;
    const revision = value.review?.revision;
    const resolvedChoice = value.result?.resolved_choice;
    if (
      !isSha256(reviewId) ||
      !isSha256(reviewSha) ||
      !isSha256(resultSha) ||
      !isSha256(comparisonSha) ||
      !Number.isInteger(revision) ||
      revision < 1 ||
      !READINESS_CHOICES.some(
        ([choice]) => choice === resolvedChoice,
      )
    ) return null;
    return {
      review_id: reviewId,
      review_sha256: reviewSha,
      result_sha256: resultSha,
      comparison_sha256: comparisonSha,
      revision,
      resolved_choice: resolvedChoice,
    };
  }

  function readinessMatchesResolution(value, qualityComparison) {
    const expected = qualityResolutionBinding(qualityComparison);
    const actual = value?.quality_review;
    return !!(
      expected &&
      actual &&
      typeof actual === "object" &&
      Object.keys(actual).length === 8 &&
      actual.quality_review_id === expected.review_id &&
      actual.quality_review_sha256 === expected.review_sha256 &&
      actual.quality_result_sha256 === expected.result_sha256 &&
      actual.quality_comparison_sha256 === expected.comparison_sha256 &&
      actual.quality_revision === expected.revision &&
      actual.resolved_choice === expected.resolved_choice &&
      actual.explicitly_resolved === true &&
      actual.latest_for_reviewer === true &&
      value.selection_manifest_sha256 ===
        qualityComparison.selection_manifest_sha256 &&
      value.balanced_arrangement_manifest_sha256 ===
        qualityComparison.balanced_arrangement_manifest_sha256 &&
      value.listening_master_manifest_sha256 ===
        qualityComparison.listening_master_manifest_sha256
    );
  }

  function comparisonIdentity(value) {
    if (!value) return "";
    const quality = qualityResolutionBinding(value);
    return [
      value.status || "",
      value.comparison_sha256 || "",
      value.selection_manifest_sha256 || "",
      value.balanced_arrangement_manifest_sha256 || "",
      value.listening_master_manifest_sha256 || "",
      quality?.review_id || "",
      quality?.review_sha256 || "",
      quality?.result_sha256 || "",
      value.readiness?.comparison_sha256 || "",
      value.readiness?.status || "",
    ].join(":");
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
    readinessDraft,
    escapeHtml,
    errorMessage,
    busyMessage,
  ) {
    if (review.status === "reviewed") {
      return reviewedHtml(review, escapeHtml, errorMessage, busyMessage);
    }
    if (review.status === "resolved") {
      return resolvedHtml(
        review,
        readinessDraft,
        escapeHtml,
        errorMessage,
        busyMessage,
      );
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

  function resolvedHtml(
    review,
    readinessDraft,
    escapeHtml,
    errorMessage,
    busyMessage,
  ) {
    const result = review.result || review;
    const mapping = result.assignment || {};
    const resolved = result.resolved_choice || "cannot_tell";
    return `<section class="success" aria-labelledby="master-review-heading">
      <h5 id="master-review-heading">Stage 1 — Blind level-matched quality review resolved</h5>
      <p><b>Candidate A:</b> ${escapeHtml(identityLabel(mapping.candidate_a))}
      · <b>Candidate B:</b> ${escapeHtml(identityLabel(mapping.candidate_b))}</p>
      <p><b>Level-matched quality outcome:</b>
      ${escapeHtml(identityLabel(resolved))}</p>
      <p>${result.result_url
        ? `<a href="${escapeHtml(result.result_url)}" download>Export resolved quality review JSON</a>`
        : "The resolved quality result is stored locally."}</p>
      <p class="muted">This is explicit listening evidence, not an automatic
      promotion. The balanced control remains required and the Listening
      Master remains a comparative challenger.</p>
    </section>
    ${readinessHtml(
      review.readiness,
      readinessDraft,
      escapeHtml,
      errorMessage,
      busyMessage,
    )}`;
  }

  function readinessHtml(
    readiness,
    draft,
    escapeHtml,
    errorMessage,
    busyMessage,
  ) {
    if (!readiness) {
      return `<section class="diagnostics" aria-labelledby="master-readiness-heading">
        <h5 id="master-readiness-heading">Stage 2 — Identity-labelled native-level readiness</h5>
        <p>Compare the exact balanced control and Listening Master challenger
        again in the same read-only window, now with their identities visible
        and each artifact playing at its own native level.</p>
        <p class="muted">Browser volume is fixed at unity: zero added gain,
        no attenuation and no level matching are applied in this stage. This
        is separate from the matched-level quality outcome above.</p>
        <button id="prepare-master-readiness" class="primary" type="button"
          ${busyMessage ? "disabled" : ""}>Prepare native-level readiness</button>
        ${statusHtml(escapeHtml, errorMessage, busyMessage)}
        ${readinessEffectsHtml()}
      </section>`;
    }
    if (readiness.status === "reviewed") {
      return readinessReviewedHtml(
        readiness,
        escapeHtml,
        errorMessage,
        busyMessage,
      );
    }
    const start = finiteDisplay(readiness.window?.start_seconds);
    const end = finiteDisplay(readiness.window?.end_seconds);
    const tags = Array.isArray(readiness.problem_tags)
      ? readiness.problem_tags
      : [];
    return `<section class="diagnostics" aria-labelledby="master-readiness-heading">
      <h5 id="master-readiness-heading">Stage 2 — Identity-labelled native-level readiness</h5>
      <p><b>Same read-only window:</b> ${escapeHtml(start)}–${escapeHtml(end)}
      seconds. Identities are visible and the two files retain their native
      artifact levels.</p>
      <p class="muted">Both browser players are fixed at unity volume
      (zero added gain). There is no gain matching, attenuation, boost,
      normalisation, limiting or other processing in this stage.</p>
      <div class="switcher" role="group"
        aria-label="Identity-labelled native-level transport">
        <button type="button"
          data-master-readiness-play="balanced_control">Play / switch to Balanced control</button>
        <button type="button"
          data-master-readiness-play="listening_master">Play / switch to Listening Master</button>
        <button id="pause-master-readiness" type="button">Pause</button>
        <button id="stop-master-readiness" type="button">Stop</button>
        <output id="master-readiness-position">0.00s</output>
      </div>
      <audio id="master-readiness-audio-balanced-control"
        data-master-review-audio data-master-readiness-audio
        aria-label="Balanced control at native artifact level"
        preload="metadata"
        src="${escapeHtml(readiness.candidates.balanced_control.audio_url)}"></audio>
      <audio id="master-readiness-audio-listening-master"
        data-master-review-audio data-master-readiness-audio
        aria-label="Listening Master challenger at native artifact level"
        preload="metadata"
        src="${escapeHtml(readiness.candidates.listening_master.audio_url)}"></audio>
      <fieldset>
        <legend>Confirm what you heard at native artifact level</legend>
        ${readinessHeardCheckbox(
          "balanced_control",
          "I heard the Balanced control",
          draft,
        )}
        ${readinessHeardCheckbox(
          "listening_master",
          "I heard the Listening Master challenger",
          draft,
        )}
      </fieldset>
      <fieldset>
        <legend>Which outcome is ready at its native artifact level?</legend>
        ${READINESS_CHOICES.map(([value, label]) =>
          readinessChoiceRadio(value, label, draft),
        ).join("")}
      </fieldset>
      <div class="candidate-grid">
        ${readinessProblemFieldset(
          "balanced_control",
          "Problems heard in the Balanced control",
          tags,
          draft,
          escapeHtml,
        )}
        ${readinessProblemFieldset(
          "listening_master",
          "Problems heard in the Listening Master challenger",
          tags,
          draft,
          escapeHtml,
        )}
      </div>
      <label>Optional private note
        <textarea id="master-readiness-notes"
          maxlength="${maximumNotes(readiness)}"
          rows="4">${escapeHtml(draft.notes)}</textarea>
      </label>
      <p id="master-readiness-draft-status" class="muted"></p>
      <button id="complete-master-readiness" class="primary" type="button"
        disabled>Complete native-level readiness</button>
      ${statusHtml(escapeHtml, errorMessage, busyMessage)}
      ${readinessEffectsHtml()}
    </section>`;
  }

  function readinessReviewedHtml(
    readiness,
    escapeHtml,
    errorMessage,
    busyMessage,
  ) {
    const record = readiness.review || {};
    const response = record.response || {};
    return `<section class="success" aria-labelledby="master-readiness-heading">
      <h5 id="master-readiness-heading">Stage 2 — Native-level readiness saved</h5>
      <p><b>Native-level readiness outcome:</b>
      ${escapeHtml(identityLabel(response.choice))}</p>
      <p>This identity-labelled result is separate from the level-matched
      quality outcome above.</p>
      <p>${record.review_url
        ? `<a href="${escapeHtml(record.review_url)}" download>Export native-level readiness JSON</a>`
        : "The native-level readiness result is stored locally."}</p>
      ${statusHtml(escapeHtml, errorMessage, busyMessage)}
      <p class="muted">The reviewed files stayed at native level with browser
      volume at unity, zero added gain and no level matching.</p>
      ${readinessEffectsHtml()}
    </section>`;
  }

  function readinessEffectsHtml() {
    return `<p class="muted">Preparing, playing, switching, drafting and
      completing this stage do not promote or select either artifact and
      change no source, MIDI, audio artifact, mix, ranking, default, product
      completion or GarageBand pack state.</p>`;
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

  function readinessHeardCheckbox(identity, label, draft) {
    return `<label><input type="checkbox"
      data-master-readiness-heard="${identity}"
      ${draft.heard[identity] ? "checked" : ""}> ${label}</label>`;
  }

  function readinessChoiceRadio(value, label, draft) {
    return `<label><input type="radio" name="master-readiness-choice"
      value="${value}" ${draft.choice === value ? "checked" : ""}>
      ${label}</label>`;
  }

  function readinessProblemFieldset(
    identity,
    legend,
    tags,
    draft,
    escapeHtml,
  ) {
    const selected = new Set(draft.problem_tags[identity] || []);
    return `<fieldset><legend>${legend}</legend><div class="problems">
      ${tags.map((tag) => `<label><input type="checkbox"
        data-master-readiness-tag
        data-master-readiness-candidate="${identity}"
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

  function emptyReadinessDraft() {
    return {
      heard: { balanced_control: false, listening_master: false },
      choice: null,
      problem_tags: { balanced_control: [], listening_master: [] },
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

  function readinessDraftFromComparison(value) {
    const response = value.review?.response || {};
    return {
      heard: {
        balanced_control: response.heard?.balanced_control === true,
        listening_master: response.heard?.listening_master === true,
      },
      choice: READINESS_CHOICES.some(
        ([choice]) => choice === response.choice,
      )
        ? response.choice
        : null,
      problem_tags: {
        balanced_control: Array.isArray(
          response.problem_tags?.balanced_control,
        )
          ? [...response.problem_tags.balanced_control]
          : [],
        listening_master: Array.isArray(
          response.problem_tags?.listening_master,
        )
          ? [...response.problem_tags.listening_master]
          : [],
      },
      notes: typeof response.notes === "string" ? response.notes : "",
    };
  }

  function readinessDraftComplete(value) {
    return !!(
      value.heard.balanced_control &&
      value.heard.listening_master &&
      READINESS_CHOICES.some(([choice]) => choice === value.choice)
    );
  }

  function maximumProblemTags(value) {
    const count = Number(
      value?.schema === READINESS_COMPARISON_SCHEMA
        ? value?.limits?.maximum_problem_tags_per_identity
        : value?.maximum_problem_tags,
    );
    return Number.isInteger(count) && count > 0
      ? count
      : DEFAULT_MAXIMUM_TAGS;
  }

  function maximumNotes(value) {
    const count = Number(
      value?.schema === READINESS_COMPARISON_SCHEMA
        ? value?.limits?.maximum_notes_characters
        : value?.maximum_notes_characters,
    );
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
    READINESS_CHOICES,
    createMasterReview,
    normalizeArtifacts,
    normalizeComparison,
    normalizeReadiness,
  };
});
