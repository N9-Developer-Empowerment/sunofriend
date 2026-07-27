(function (root, factory) {
  "use strict";

  const exported = factory(root);
  if (typeof module === "object" && module.exports) {
    module.exports = exported;
  }
  if (root && typeof root === "object") {
    root.SunofriendWorkbenchInstrumentReview = exported;
  }
})(
  typeof globalThis !== "undefined" ? globalThis : this,
  function (root) {
    "use strict";

    const PLAN_SCHEMA = "sunofriend.workbench-instrument-review-plan.v1";
    const COMPARISON_SCHEMA =
      "sunofriend.workbench-instrument-review.comparison.v1";
    const CHOICES = Object.freeze([
      ["candidate_a", "Candidate A"],
      ["candidate_b", "Candidate B"],
      ["equivalent", "Equivalent"],
      ["none_usable", "Neither is usable"],
      ["cannot_tell", "Cannot tell"],
    ]);
    const TRACKS = Object.freeze([
      ["source_reference", "Source stem reference"],
      ["candidate_a", "Candidate A"],
      ["candidate_b", "Candidate B"],
    ]);
    const DEFAULT_MAXIMUM_TAGS = 8;
    const DEFAULT_MAXIMUM_NOTES = 2000;
    const MAXIMUM_LANES = 64;
    const MAXIMUM_TAG_CATALOGUE = 32;

    function createInstrumentReview(options = {}) {
      const api = options.api;
      const escapeHtml = options.escapeHtml || escape;
      const pauseOtherAudio = options.pauseOtherAudio || (() => {});
      if (typeof api !== "function") {
        throw new Error("Instrument review needs an API");
      }
      if (typeof pauseOtherAudio !== "function") {
        throw new Error("Instrument review pauseOtherAudio must be a function");
      }

      let plan = null;
      let planKey = "";
      let activeLaneKey = "";
      let comparison = null;
      let holder = null;
      let draft = emptyDraft();
      let requestSequence = 0;
      let requestInFlight = false;
      let audioLoadSequence = 0;
      let audioLoadInFlight = false;
      let audioAbortController = null;
      let audioContext = null;
      let transport = null;
      let activeTrack = null;
      let errorMessage = "";
      let busyMessage = "";

      function setPlan(next) {
        const checked = next == null ? null : normalizePlan(next);
        const nextKey = checked ? planIdentity(checked) : "";
        if (nextKey !== planKey) {
          invalidateRequests();
          comparison = null;
          draft = emptyDraft();
          errorMessage = "";
          busyMessage = "";
        }
        plan = checked;
        planKey = nextKey;
        const lanes = checked?.eligible_lanes || [];
        if (!lanes.some((lane) => laneIdentity(lane) === activeLaneKey)) {
          activeLaneKey = lanes.length ? laneIdentity(lanes[0]) : "";
        }
        if (comparison && !comparisonMatchesPlan(comparison, checked)) {
          comparison = null;
          draft = emptyDraft();
        }
        return controller;
      }

      function setComparison(next) {
        if (next == null) {
          if (comparison !== null) invalidateRequests();
          comparison = null;
          draft = emptyDraft();
          errorMessage = "";
          busyMessage = "";
          return controller;
        }
        const checked = normalizeComparison(next);
        if (plan && !comparisonMatchesPlan(checked, plan)) {
          throw new Error(
            "Instrument comparison does not match an eligible selected MIDI lane",
          );
        }
        const previous = comparisonIdentity(comparison);
        const following = comparisonIdentity(checked);
        if (previous && previous !== following) invalidateRequests();
        comparison = checked;
        activeLaneKey = laneIdentity(checked);
        draft = draftFromComparison(checked);
        errorMessage = "";
        busyMessage = "";
        return controller;
      }

      function renderInto(element) {
        stopAudio();
        holder = element || null;
        if (!holder) return;
        if (!plan) {
          holder.innerHTML = unavailableHtml(
            "Instrument review plan is not loaded.",
          );
          return;
        }
        if (!plan.eligible_lanes.length) {
          holder.innerHTML = unavailableHtml(
            "Choose at least one bass MIDI part before comparing complete instruments.",
          );
          return;
        }
        if (!comparison) {
          holder.innerHTML = prepareHtml(
            plan,
            activeLane(),
            escapeHtml,
            errorMessage,
            busyMessage,
          );
          wireLaneSelection();
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
        else if (comparison.status === "reviewed") wireResolve();
      }

      function stopAudio() {
        audioLoadSequence += 1;
        if (audioAbortController) {
          try {
            audioAbortController.abort();
          } catch {}
        }
        audioAbortController = null;
        audioLoadInFlight = false;
        if (transport) {
          try {
            transport.stop();
          } catch {}
        }
        transport = null;
        activeTrack = null;
      }

      function reset() {
        invalidateRequests();
        plan = null;
        planKey = "";
        activeLaneKey = "";
        comparison = null;
        holder = null;
        draft = emptyDraft();
        errorMessage = "";
        busyMessage = "";
        if (audioContext && typeof audioContext.close === "function") {
          try {
            const closing = audioContext.close();
            if (closing && typeof closing.catch === "function") {
              closing.catch(() => {});
            }
          } catch {}
        }
        audioContext = null;
      }

      function snapshot() {
        let transportState = null;
        if (transport && typeof transport.snapshot === "function") {
          try {
            transportState = transport.snapshot();
          } catch {}
        }
        return {
          plan_schema: plan?.schema || null,
          eligible_lane_count: plan?.eligible_lanes?.length || 0,
          active_lane: activeLane()
            ? {
                stem_id: activeLane().stem_id,
                candidate_id: activeLane().candidate_id,
                role: activeLane().role,
              }
            : null,
          comparison_status: comparison?.status || null,
          comparison_sha256: comparison?.comparison_sha256 || null,
          audio_prepared: !!transport,
          playing: !!transportState?.playing,
          active_track: activeTrack,
          request_in_flight: requestInFlight,
          feedback_persisted:
            comparison?.status === "reviewed" ||
            comparison?.status === "resolved",
          browser_state_persisted: false,
        };
      }

      function invalidateRequests() {
        requestSequence += 1;
        requestInFlight = false;
        stopAudio();
      }

      function activeLane() {
        return (
          plan?.eligible_lanes?.find(
            (lane) => laneIdentity(lane) === activeLaneKey,
          ) || null
        );
      }

      function wireLaneSelection() {
        holder
          ?.querySelectorAll?.("[data-instrument-review-lane]")
          .forEach((button) => {
            button.onclick = () => {
              if (requestInFlight) return;
              const requested = button.dataset.instrumentReviewLane;
              if (
                !plan.eligible_lanes.some(
                  (lane) => laneIdentity(lane) === requested,
                )
              ) {
                return;
              }
              activeLaneKey = requested;
              errorMessage = "";
              renderInto(holder);
            };
          });
      }

      function wirePrepare() {
        const button = holder?.querySelector?.("#prepare-instrument-review");
        if (!button) return;
        button.onclick = async () => {
          if (requestInFlight) return;
          const lane = activeLane();
          if (!lane) return;
          const start = Number(
            holder.querySelector("#instrument-review-start")?.value,
          );
          const end = Number(
            holder.querySelector("#instrument-review-end")?.value,
          );
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
          const requestedPlanKey = planKey;
          const requestedLaneKey = laneIdentity(lane);
          const requestId = ++requestSequence;
          requestInFlight = true;
          errorMessage = "";
          busyMessage =
            "Preparing the exact fixed-MIDI blind instrument comparison locally…";
          renderInto(holder);
          try {
            const response = await api("/api/instrument-review/prepare", {
              method: "POST",
              body: JSON.stringify({
                selection_manifest_sha256:
                  lane.selection_manifest_sha256,
                stem_id: lane.stem_id,
                candidate_id: lane.candidate_id,
                midi_sha256: lane.midi_sha256,
                start_seconds: start,
                end_seconds: end,
              }),
            });
            if (
              requestId !== requestSequence ||
              planKey !== requestedPlanKey ||
              activeLaneKey !== requestedLaneKey
            ) {
              return;
            }
            const checked = normalizeComparison(
              response?.comparison ?? response,
            );
            if (!comparisonMatchesLane(checked, lane)) {
              throw new Error(
                "The selected MIDI lane changed while its instrument comparison was prepared",
              );
            }
            comparison = checked;
            draft = draftFromComparison(checked);
            requestInFlight = false;
            busyMessage = "";
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
        const load = holder?.querySelector?.(
          "#load-instrument-review-audio",
        );
        if (load) load.onclick = loadDecodedAudio;
        holder
          ?.querySelectorAll?.("[data-instrument-review-play]")
          .forEach((button) => {
            button.onclick = () =>
              playTrack(button.dataset.instrumentReviewPlay);
          });
        const pause = holder?.querySelector?.("#pause-instrument-review");
        if (pause) {
          pause.onclick = () => {
            if (!transport) return;
            try {
              transport.pause();
              activeTrack = transport.activeKey || activeTrack;
              updateTransportPresentation();
            } catch (error) {
              setInlineError(error);
            }
          };
        }
        const stop = holder?.querySelector?.("#stop-instrument-review");
        if (stop) {
          stop.onclick = () => {
            if (!transport) return;
            try {
              transport.stop();
              activeTrack = null;
              updateTransportPresentation();
            } catch (error) {
              setInlineError(error);
            }
          };
        }
        holder
          ?.querySelectorAll?.("[data-instrument-review-heard]")
          .forEach((input) => {
            input.onchange = () => {
              const key = input.dataset.instrumentReviewHeard;
              if (Object.prototype.hasOwnProperty.call(draft.heard, key)) {
                draft.heard[key] = !!input.checked;
              }
              updateCompletionState();
            };
          });
        holder
          ?.querySelectorAll?.('input[name="instrument-review-choice"]')
          .forEach((input) => {
            input.onchange = () => {
              if (
                input.checked &&
                CHOICES.some(([choice]) => choice === input.value)
              ) {
                draft.choice = input.value;
              }
              updateCompletionState();
            };
          });
        holder
          ?.querySelectorAll?.("[data-instrument-review-tag]")
          .forEach((input) => {
            input.onchange = () => {
              const candidate = input.dataset.instrumentReviewCandidate;
              if (!["candidate_a", "candidate_b"].includes(candidate)) return;
              const selected = new Set(draft.problem_tags[candidate]);
              if (input.checked) selected.add(input.value);
              else selected.delete(input.value);
              if (
                !comparison.allowed_problem_tags.includes(input.value) ||
                selected.size > comparison.limits.maximum_problem_tags_per_candidate
              ) {
                input.checked = false;
                setInlineError(
                  new Error(
                    `Choose no more than ${comparison.limits.maximum_problem_tags_per_candidate} allow-listed problem tags for one candidate.`,
                  ),
                );
                return;
              }
              draft.problem_tags[candidate] = [...selected].sort();
              updateCompletionState();
            };
          });
        holder
          ?.querySelectorAll?.("[data-instrument-review-notes]")
          .forEach((input) => {
            input.oninput = () => {
              const candidate = input.dataset.instrumentReviewNotes;
              if (!["candidate_a", "candidate_b"].includes(candidate)) return;
              const maximum =
                comparison.limits.maximum_notes_characters_per_candidate;
              const value = String(input.value || "").slice(0, maximum);
              draft.notes[candidate] = value;
              if (input.value !== value) input.value = value;
            };
          });
        const complete = holder?.querySelector?.(
          "#complete-instrument-review",
        );
        if (complete) complete.onclick = completeReview;
        updateCompletionState();
        updateTransportPresentation();
      }

      async function loadDecodedAudio() {
        if (
          audioLoadInFlight ||
          requestInFlight ||
          comparison?.status !== "unreviewed"
        ) {
          return;
        }
        const transportApi = root?.SunofriendWorkbenchTransport;
        if (typeof transportApi?.DecodedLoopTransport !== "function") {
          setInlineError(
            new Error(
              "The shared one-clock Workbench transport is unavailable. Independent drifting players are intentionally not provided.",
            ),
          );
          return;
        }
        if (typeof root?.fetch !== "function") {
          setInlineError(
            new Error("The browser cannot fetch the private comparison audio."),
          );
          return;
        }
        let context;
        try {
          context = ensureAudioContext();
        } catch (error) {
          setInlineError(error);
          return;
        }
        stopAudio();
        audioLoadInFlight = true;
        const loadId = ++audioLoadSequence;
        const comparisonKey = comparisonIdentity(comparison);
        const abortController = new AbortController();
        audioAbortController = abortController;
        setAudioStatus("Decoding one source crop and two blind candidates…");
        const loadButton = holder?.querySelector?.(
          "#load-instrument-review-audio",
        );
        if (loadButton) loadButton.disabled = true;
        try {
          const records = comparisonTracks(comparison);
          const entries = await Promise.all(
            records.map(async ([key, record]) => [
              key,
              await fetchDecodedBuffer(
                root.fetch.bind(root),
                context,
                record.audio_url,
                abortController.signal,
              ),
            ]),
          );
          if (
            loadId !== audioLoadSequence ||
            comparisonKey !== comparisonIdentity(comparison)
          ) {
            return;
          }
          transport = new transportApi.DecodedLoopTransport({
            audioContext: context,
            decodedBuffers: new Map(entries),
            gainDbByKey: new Map(entries.map(([key]) => [key, 0])),
            loopStartSeconds: 0,
            loopEndSeconds: comparisonWindowDuration(comparison),
          });
          activeTrack = null;
          audioLoadInFlight = false;
          audioAbortController = null;
          setAudioStatus(
            "One-clock comparison ready. Browser gain is unity because the server already prepared the fixed review crops.",
            "ready",
          );
          setPlayButtonsDisabled(false);
          updateTransportPresentation();
        } catch (error) {
          if (loadId !== audioLoadSequence) return;
          audioLoadInFlight = false;
          audioAbortController = null;
          if (error?.name !== "AbortError") setInlineError(error);
          if (loadButton) loadButton.disabled = false;
        }
      }

      async function playTrack(key) {
        if (!transport || !TRACKS.some(([track]) => track === key)) return;
        try {
          pauseOtherAudio();
          if (
            audioContext?.state === "suspended" &&
            typeof audioContext.resume === "function"
          ) {
            await audioContext.resume();
          }
          transport.switchTo(key);
          activeTrack = key;
          updateTransportPresentation();
        } catch (error) {
          setInlineError(error);
        }
      }

      async function completeReview() {
        if (
          requestInFlight ||
          comparison?.status !== "unreviewed" ||
          !draftComplete(draft)
        ) {
          return;
        }
        const requestedComparison = comparisonIdentity(comparison);
        const requestId = ++requestSequence;
        requestInFlight = true;
        busyMessage = "Saving only this explicit instrument feedback locally…";
        errorMessage = "";
        updateCompletionState();
        setReviewStatus(busyMessage, "busy");
        try {
          const response = await api("/api/instrument-review", {
            method: "POST",
            body: JSON.stringify({
              comparison_sha256: comparison.comparison_sha256,
              expected_revision: Number(comparison.expected_revision || 0),
              heard: {
                source_reference: draft.heard.source_reference,
                candidate_a: draft.heard.candidate_a,
                candidate_b: draft.heard.candidate_b,
              },
              choice: draft.choice,
              problem_tags: {
                candidate_a: [...draft.problem_tags.candidate_a],
                candidate_b: [...draft.problem_tags.candidate_b],
              },
              notes: {
                candidate_a: draft.notes.candidate_a,
                candidate_b: draft.notes.candidate_b,
              },
            }),
          });
          if (
            requestId !== requestSequence ||
            requestedComparison !== comparisonIdentity(comparison)
          ) {
            return;
          }
          const checked = normalizeComparison(
            response?.comparison ?? response,
          );
          if (
            checked.comparison_sha256 !== comparison.comparison_sha256 ||
            !comparisonMatchesPlan(checked, plan)
          ) {
            throw new Error(
              "The comparison changed while feedback was being saved; reload it",
            );
          }
          comparison = checked;
          draft = draftFromComparison(checked);
          requestInFlight = false;
          busyMessage = "";
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
        const button = holder?.querySelector?.("#resolve-instrument-review");
        if (!button) return;
        button.onclick = async () => {
          if (requestInFlight || comparison?.status !== "reviewed") return;
          const reviewId = comparison.review?.review_id;
          const reviewSha = comparison.review?.review_sha256;
          if (!isSha256(reviewId) || !isSha256(reviewSha)) return;
          const requestedComparison = comparisonIdentity(comparison);
          const requestId = ++requestSequence;
          requestInFlight = true;
          busyMessage =
            "Verifying the saved blind review before revealing identities…";
          errorMessage = "";
          renderInto(holder);
          try {
            const response = await api("/api/instrument-review/resolve", {
              method: "POST",
              body: JSON.stringify({
                comparison_sha256: comparison.comparison_sha256,
                review_id: reviewId,
                review_sha256: reviewSha,
              }),
            });
            if (
              requestId !== requestSequence ||
              requestedComparison !== comparisonIdentity(comparison)
            ) {
              return;
            }
            const checked = normalizeComparison(
              response?.comparison ?? response,
            );
            if (
              checked.comparison_sha256 !== comparison.comparison_sha256 ||
              !comparisonMatchesPlan(checked, plan)
            ) {
              throw new Error(
                "The comparison changed before resolution; reload it",
              );
            }
            comparison = checked;
            draft = draftFromComparison(checked);
            requestInFlight = false;
            busyMessage = "";
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
        const complete = holder?.querySelector?.(
          "#complete-instrument-review",
        );
        const ready = draftComplete(draft);
        if (complete) complete.disabled = !ready || requestInFlight;
        const status = holder?.querySelector?.(
          "#instrument-review-draft-status",
        );
        if (status) {
          status.textContent = ready
            ? "Ready to save this explicit blind review."
            : "Confirm that you heard the source reference, Candidate A and Candidate B, then choose one outcome.";
        }
      }

      function updateTransportPresentation() {
        let state = null;
        if (transport && typeof transport.snapshot === "function") {
          try {
            state = transport.snapshot();
          } catch {}
        }
        holder
          ?.querySelectorAll?.("[data-instrument-review-play]")
          .forEach((button) => {
            const selected =
              !!state?.playing &&
              button.dataset.instrumentReviewPlay === activeTrack;
            button.setAttribute?.("aria-pressed", String(selected));
            if (button.classList?.toggle) {
              button.classList.toggle("playing", selected);
            }
          });
        const position = holder?.querySelector?.(
          "#instrument-review-position",
        );
        if (position) {
          position.textContent = `${Number(
            state?.playheadSeconds || 0,
          ).toFixed(2)}s`;
        }
      }

      function setPlayButtonsDisabled(disabled) {
        holder
          ?.querySelectorAll?.("[data-instrument-review-play]")
          .forEach((button) => {
            button.disabled = !!disabled;
          });
        const pause = holder?.querySelector?.("#pause-instrument-review");
        const stop = holder?.querySelector?.("#stop-instrument-review");
        if (pause) pause.disabled = !!disabled;
        if (stop) stop.disabled = !!disabled;
      }

      function setAudioStatus(message, tone = "") {
        const status = holder?.querySelector?.(
          "#instrument-review-audio-status",
        );
        if (!status) return;
        status.textContent = message;
        status.className = `decoded-status ${tone}`.trim();
      }

      function setReviewStatus(message, tone = "") {
        const status = holder?.querySelector?.("#instrument-review-status");
        if (!status) return;
        status.textContent = message;
        status.className =
          tone === "error"
            ? "error"
            : tone === "busy"
              ? "busy"
              : "muted";
      }

      function setInlineError(error) {
        errorMessage = error?.message || String(error);
        setAudioStatus(errorMessage, "error");
        setReviewStatus(errorMessage, "error");
      }

      function ensureAudioContext() {
        if (audioContext && audioContext.state !== "closed") {
          return audioContext;
        }
        const Context = root?.AudioContext || root?.webkitAudioContext;
        if (typeof Context !== "function") {
          throw new Error(
            "Web Audio is unavailable. Independent drifting players are intentionally not provided.",
          );
        }
        audioContext = new Context();
        return audioContext;
      }

      const controller = Object.freeze({
        renderInto,
        reset,
        setComparison,
        setPlan,
        snapshot,
        stopAudio,
      });
      return controller;
    }

    function normalizePlan(value) {
      const source = value?.plan ?? value;
      if (!source || typeof source !== "object" || Array.isArray(source)) {
        throw new TypeError("Instrument review plan must be an object");
      }
      if (source.schema !== PLAN_SCHEMA) {
        throw new TypeError("Instrument review plan schema is invalid");
      }
      const selection = requireSha256(
        source.selection_manifest_sha256,
        "plan selection_manifest_sha256",
      );
      const rawLanes = source.eligible_lanes ?? source.lanes;
      if (!Array.isArray(rawLanes) || rawLanes.length > MAXIMUM_LANES) {
        throw new TypeError(
          `Instrument review plan needs at most ${MAXIMUM_LANES} eligible lanes`,
        );
      }
      const identities = new Set();
      const eligibleLanes = rawLanes.map((lane, index) => {
        const checked = normalizeLane(lane, selection, index);
        const identity = laneIdentity(checked);
        if (identities.has(identity)) {
          throw new TypeError("Instrument review plan contains a duplicate lane");
        }
        identities.add(identity);
        return checked;
      });
      return Object.freeze({
        schema: PLAN_SCHEMA,
        selection_manifest_sha256: selection,
        eligible_lanes: Object.freeze(eligibleLanes),
        effects: normalizePlanEffects(source.effects),
      });
    }

    function normalizeLane(value, planSelection, index = 0) {
      if (!value || typeof value !== "object" || Array.isArray(value)) {
        throw new TypeError(`Instrument review lane ${index + 1} is invalid`);
      }
      const selection = requireSha256(
        value.selection_manifest_sha256 ?? planSelection,
        "lane selection_manifest_sha256",
      );
      if (selection !== planSelection) {
        throw new TypeError("Instrument review lane selection does not match its plan");
      }
      const role = requireString(value.role, "lane role", 40).toLowerCase();
      if (role !== "bass") {
        throw new TypeError("Instrument review v1 accepts bass lanes only");
      }
      const pair = normalizePair(value.pair ?? value.pair_description);
      return Object.freeze({
        selection_manifest_sha256: selection,
        stem_id: requireString(value.stem_id, "lane stem_id", 256),
        candidate_id: requireString(
          value.candidate_id,
          "lane candidate_id",
          256,
        ),
        midi_sha256: requireSha256(
          value.midi_sha256,
          "lane midi_sha256",
        ),
        role,
        label:
          typeof value.label === "string"
            ? boundedString(value.label, 256)
            : "Selected bass MIDI",
        pair,
      });
    }

    function normalizePair(value) {
      if (typeof value === "string") {
        return Object.freeze({ description: boundedString(value, 500) });
      }
      if (!value || typeof value !== "object" || Array.isArray(value)) {
        throw new TypeError("Instrument review lane pair description is invalid");
      }
      for (const key of ["assignment", "candidate_a", "candidate_b", "answer_key"]) {
        if (Object.prototype.hasOwnProperty.call(value, key)) {
          throw new TypeError(
            "Instrument review plan must not reveal the A/B assignment",
          );
        }
      }
      const description =
        typeof value.description === "string"
          ? boundedString(value.description, 500)
          : "Two complete broad-family programs; the A/B assignment stays hidden until resolution.";
      const controlLabel = pairLabel(value.control);
      const challengerLabel = pairLabel(value.challenger);
      return Object.freeze({
        description,
        control_label: controlLabel,
        challenger_label: challengerLabel,
      });
    }

    function pairLabel(value) {
      if (typeof value === "string") return boundedString(value, 200);
      if (value && typeof value === "object" && typeof value.label === "string") {
        return boundedString(value.label, 200);
      }
      return null;
    }

    function normalizeComparison(value) {
      const source = value?.comparison ?? value;
      if (!source || typeof source !== "object" || Array.isArray(source)) {
        throw new TypeError("Instrument comparison must be an object");
      }
      if (source.schema !== COMPARISON_SCHEMA) {
        throw new TypeError("Instrument comparison schema is invalid");
      }
      const status = requireEnum(
        source.status,
        ["unreviewed", "reviewed", "resolved"],
        "comparison status",
      );
      const blind = status !== "resolved";
      if (source.blind !== blind) {
        throw new TypeError(
          "Instrument comparison blind state does not match its status",
        );
      }
      const effects = normalizeComparisonEffects(source.effects, status);
      if (
        status !== "resolved" &&
        ["assignment", "answer_key", "resolved_choice"].some((key) =>
          Object.prototype.hasOwnProperty.call(source, key),
        )
      ) {
        throw new TypeError(
          "Unresolved instrument comparison exposed its A/B assignment",
        );
      }
      const selection = requireSha256(
        source.selection_manifest_sha256,
        "comparison selection_manifest_sha256",
      );
      const lane = {
        selection_manifest_sha256: selection,
        stem_id: requireString(source.stem_id, "comparison stem_id", 256),
        candidate_id: requireString(
          source.candidate_id,
          "comparison candidate_id",
          256,
        ),
        midi_sha256: requireSha256(
          source.midi_sha256,
          "comparison midi_sha256",
        ),
        role: requireString(source.role ?? "bass", "comparison role", 40)
          .toLowerCase(),
      };
      if (lane.role !== "bass") {
        throw new TypeError("Instrument comparison v1 accepts bass lanes only");
      }
      const window = normalizeWindow(source.window);
      const sourceReference = normalizeAudioRecord(
        source.source_reference,
        "source reference",
        false,
      );
      const rawCandidates = source.candidates ?? source;
      const candidateA = normalizeAudioRecord(
        rawCandidates.candidate_a,
        "Candidate A",
        status !== "resolved",
      );
      const candidateB = normalizeAudioRecord(
        rawCandidates.candidate_b,
        "Candidate B",
        status !== "resolved",
      );
      const allowedProblemTags = normalizeTags(
        source.allowed_problem_tags ?? source.problem_tags ?? [],
        "allowed problem tags",
        MAXIMUM_TAG_CATALOGUE,
      );
      const limits = normalizeLimits(source);
      const expectedRevision = nonNegativeInteger(
        source.expected_revision ?? source.revision ?? 0,
        "comparison expected_revision",
      );
      const review =
        status === "reviewed" || status === "resolved"
          ? normalizeReview(source.review, allowedProblemTags, limits)
          : null;
      const result =
        status === "resolved" ? normalizeResult(source.result ?? source) : null;
      return Object.freeze({
        schema: COMPARISON_SCHEMA,
        status,
        blind,
        comparison_sha256: requireSha256(
          source.comparison_sha256,
          "comparison comparison_sha256",
        ),
        ...lane,
        expected_revision: expectedRevision,
        window,
        source_reference: sourceReference,
        candidates: Object.freeze({
          candidate_a: candidateA,
          candidate_b: candidateB,
        }),
        allowed_problem_tags: Object.freeze(allowedProblemTags),
        limits,
        review,
        result,
        effects,
      });
    }

    function normalizeWindow(value) {
      if (!value || typeof value !== "object" || Array.isArray(value)) {
        throw new TypeError("Instrument comparison window is invalid");
      }
      const start = finiteNumber(value.start_seconds, "window start_seconds");
      const end = finiteNumber(value.end_seconds, "window end_seconds");
      if (start < 0 || end - start < 0.5 || end - start > 15) {
        throw new TypeError(
          "Instrument comparison window must be between 0.5 and 15 seconds",
        );
      }
      return Object.freeze({
        start_seconds: start,
        end_seconds: end,
        duration_seconds: end - start,
      });
    }

    function normalizeAudioRecord(value, label, blind) {
      if (!value || typeof value !== "object" || Array.isArray(value)) {
        throw new TypeError(`${label} audio is invalid`);
      }
      if (
        blind &&
        [
          "identity",
          "program",
          "program_number",
          "program_label",
          "assignment",
          "control",
          "challenger",
        ].some((key) => Object.prototype.hasOwnProperty.call(value, key))
      ) {
        throw new TypeError(`${label} exposed a hidden instrument identity`);
      }
      return Object.freeze({
        audio_url: requireLocalMediaUrl(value.audio_url, `${label} audio_url`),
        applied_gain_db: attenuationDb(
          value.applied_gain_db,
          `${label} applied_gain_db`,
        ),
      });
    }

    function normalizeLimits(source) {
      const raw = source.limits || {};
      const maximumTags = positiveInteger(
        raw.maximum_problem_tags_per_candidate ??
          source.maximum_problem_tags ??
          DEFAULT_MAXIMUM_TAGS,
        "maximum problem tags per candidate",
      );
      const maximumNotes = positiveInteger(
        raw.maximum_notes_characters_per_candidate ??
          source.maximum_notes_characters ??
          DEFAULT_MAXIMUM_NOTES,
        "maximum notes characters per candidate",
      );
      if (maximumTags > MAXIMUM_TAG_CATALOGUE || maximumNotes > 10000) {
        throw new TypeError("Instrument comparison limits exceed browser bounds");
      }
      return Object.freeze({
        maximum_problem_tags_per_candidate: maximumTags,
        maximum_notes_characters_per_candidate: maximumNotes,
      });
    }

    function normalizeReview(value, allowedTags, limits) {
      if (!value || typeof value !== "object" || Array.isArray(value)) {
        throw new TypeError("Reviewed instrument comparison is missing its review");
      }
      const response = value.response ?? value;
      const heard = response.heard || {};
      const choice = requireEnum(
        response.choice ?? value.choice,
        CHOICES.map(([item]) => item),
        "instrument review choice",
      );
      const problemTags = {
        candidate_a: normalizeSelectedTags(
          response.problem_tags?.candidate_a,
          allowedTags,
          limits,
          "Candidate A problem tags",
        ),
        candidate_b: normalizeSelectedTags(
          response.problem_tags?.candidate_b,
          allowedTags,
          limits,
          "Candidate B problem tags",
        ),
      };
      const notes = {
        candidate_a: normalizeNote(
          response.notes?.candidate_a,
          limits.maximum_notes_characters_per_candidate,
          "Candidate A notes",
        ),
        candidate_b: normalizeNote(
          response.notes?.candidate_b,
          limits.maximum_notes_characters_per_candidate,
          "Candidate B notes",
        ),
      };
      if (
        heard.source_reference !== true ||
        heard.candidate_a !== true ||
        heard.candidate_b !== true
      ) {
        throw new TypeError(
          "Reviewed instrument comparison lacks complete heard evidence",
        );
      }
      return Object.freeze({
        review_id: requireSha256(value.review_id, "instrument review_id"),
        review_sha256: requireSha256(
          value.review_sha256,
          "instrument review_sha256",
        ),
        revision: positiveInteger(
          value.revision ?? 1,
          "instrument review revision",
        ),
        review_url: optionalApiUrl(value.review_url, "instrument review_url"),
        response: Object.freeze({
          heard: Object.freeze({
            source_reference: true,
            candidate_a: true,
            candidate_b: true,
          }),
          choice,
          problem_tags: Object.freeze({
            candidate_a: Object.freeze(problemTags.candidate_a),
            candidate_b: Object.freeze(problemTags.candidate_b),
          }),
          notes: Object.freeze(notes),
        }),
      });
    }

    function normalizeResult(value) {
      if (!value || typeof value !== "object" || Array.isArray(value)) {
        throw new TypeError("Resolved instrument comparison is missing its result");
      }
      const assignment = value.assignment;
      if (!assignment || typeof assignment !== "object") {
        throw new TypeError("Resolved instrument comparison lacks an assignment");
      }
      const candidateA = requireString(
        identityValue(assignment.candidate_a),
        "resolved Candidate A identity",
        200,
      );
      const candidateB = requireString(
        identityValue(assignment.candidate_b),
        "resolved Candidate B identity",
        200,
      );
      return Object.freeze({
        assignment: Object.freeze({
          candidate_a: candidateA,
          candidate_b: candidateB,
        }),
        resolved_choice: requireString(
          identityValue(value.resolved_choice),
          "resolved instrument choice",
          200,
        ),
        result_url: optionalApiUrl(
          value.result_url,
          "instrument result_url",
        ),
      });
    }

    function identityValue(value) {
      if (typeof value === "string") return value;
      if (value && typeof value === "object") {
        return value.label ?? value.identity ?? value.name;
      }
      return value;
    }

    function normalizeSelectedTags(value, allowed, limits, label) {
      const tags = normalizeTags(
        value ?? [],
        label,
        limits.maximum_problem_tags_per_candidate,
      );
      if (tags.some((tag) => !allowed.includes(tag))) {
        throw new TypeError(`${label} include a tag outside the allowlist`);
      }
      return tags;
    }

    function normalizeTags(value, label, maximum) {
      if (!Array.isArray(value) || value.length > maximum) {
        throw new TypeError(`${label} are invalid`);
      }
      const result = value.map((tag) => requireString(tag, label, 80));
      if (new Set(result).size !== result.length) {
        throw new TypeError(`${label} contain duplicates`);
      }
      return result;
    }

    function normalizeNote(value, maximum, label) {
      if (value == null) return "";
      if (typeof value !== "string" || value.length > maximum) {
        throw new TypeError(`${label} exceed the fixed limit`);
      }
      return value;
    }

    function normalizePlanEffects(value) {
      if (value == null) {
        return Object.freeze({
          midi_changed: false,
          instrument_default_changed: false,
          pack_changed: false,
          mix_changed: false,
          feedback_recorded: false,
        });
      }
      if (!value || typeof value !== "object" || Array.isArray(value)) {
        throw new TypeError("Instrument review plan effects are invalid");
      }
      for (const key of [
        "midi_changed",
        "instrument_default_changed",
        "pack_changed",
        "mix_changed",
        "feedback_recorded",
      ]) {
        if (value[key] !== false) {
          throw new TypeError(
            "Instrument review plan must declare zero product effects",
          );
        }
      }
      return Object.freeze({
        midi_changed: false,
        instrument_default_changed: false,
        pack_changed: false,
        mix_changed: false,
        feedback_recorded: false,
      });
    }

    function normalizeComparisonEffects(value, status) {
      const keys = [
        "midi_changed",
        "instrument_default_changed",
        "pack_changed",
        "mix_changed",
        "feedback_recorded",
      ];
      if (
        !value ||
        typeof value !== "object" ||
        Array.isArray(value) ||
        Object.keys(value).length !== keys.length ||
        keys.some((key) => !Object.prototype.hasOwnProperty.call(value, key))
      ) {
        throw new TypeError(
          "Instrument comparison effects must use the exact public effect map",
        );
      }
      for (const key of keys.slice(0, 4)) {
        if (value[key] !== false) {
          throw new TypeError(
            "Instrument comparison must declare zero product effects",
          );
        }
      }
      const feedbackRecorded = status !== "unreviewed";
      if (value.feedback_recorded !== feedbackRecorded) {
        throw new TypeError(
          "Instrument comparison feedback effect does not match its status",
        );
      }
      return Object.freeze({
        midi_changed: false,
        instrument_default_changed: false,
        pack_changed: false,
        mix_changed: false,
        feedback_recorded: feedbackRecorded,
      });
    }

    function draftFromComparison(value) {
      const response = value?.review?.response || {};
      return {
        heard: {
          source_reference: response.heard?.source_reference === true,
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
        notes: {
          candidate_a:
            typeof response.notes?.candidate_a === "string"
              ? response.notes.candidate_a
              : "",
          candidate_b:
            typeof response.notes?.candidate_b === "string"
              ? response.notes.candidate_b
              : "",
        },
      };
    }

    function emptyDraft() {
      return {
        heard: {
          source_reference: false,
          candidate_a: false,
          candidate_b: false,
        },
        choice: null,
        problem_tags: { candidate_a: [], candidate_b: [] },
        notes: { candidate_a: "", candidate_b: "" },
      };
    }

    function draftComplete(value) {
      return !!(
        value.heard.source_reference &&
        value.heard.candidate_a &&
        value.heard.candidate_b &&
        CHOICES.some(([choice]) => choice === value.choice)
      );
    }

    function comparisonMatchesPlan(value, currentPlan) {
      return !!(
        value &&
        currentPlan &&
        value.selection_manifest_sha256 ===
          currentPlan.selection_manifest_sha256 &&
        currentPlan.eligible_lanes.some((lane) =>
          comparisonMatchesLane(value, lane),
        )
      );
    }

    function comparisonMatchesLane(value, lane) {
      return !!(
        value &&
        lane &&
        value.selection_manifest_sha256 ===
          lane.selection_manifest_sha256 &&
        value.stem_id === lane.stem_id &&
        value.candidate_id === lane.candidate_id &&
        value.midi_sha256 === lane.midi_sha256 &&
        value.role === lane.role
      );
    }

    function planIdentity(value) {
      return [
        value.selection_manifest_sha256,
        ...value.eligible_lanes.map(laneIdentity),
      ].join("|");
    }

    function laneIdentity(value) {
      return value
        ? [
            value.selection_manifest_sha256,
            value.stem_id,
            value.candidate_id,
            value.midi_sha256,
            value.role,
          ].join(":")
        : "";
    }

    function comparisonIdentity(value) {
      return value
        ? `${laneIdentity(value)}:${value.comparison_sha256 || ""}`
        : "";
    }

    function comparisonTracks(value) {
      return [
        ["source_reference", value.source_reference],
        ["candidate_a", value.candidates.candidate_a],
        ["candidate_b", value.candidates.candidate_b],
      ];
    }

    function comparisonWindowDuration(value) {
      return value.window.end_seconds - value.window.start_seconds;
    }

    async function fetchDecodedBuffer(fetchFunction, context, url, signal) {
      const response = await fetchFunction(url, {
        cache: "no-store",
        credentials: "same-origin",
        signal,
      });
      if (!response?.ok) {
        throw new Error(
          `Private instrument-review audio could not be loaded (${response?.status || "network error"})`,
        );
      }
      const encoded = await response.arrayBuffer();
      if (!(encoded instanceof ArrayBuffer) || encoded.byteLength === 0) {
        throw new Error("Private instrument-review audio is empty");
      }
      const decoded = await context.decodeAudioData(encoded.slice(0));
      if (!decoded || !Number.isFinite(decoded.duration)) {
        throw new Error("Private instrument-review audio could not be decoded");
      }
      return decoded;
    }

    function prepareHtml(
      plan,
      lane,
      escapeHtml,
      errorMessage,
      busyMessage,
    ) {
      const laneButtons = plan.eligible_lanes
        .map((item, index) => {
          const selected = laneIdentity(item) === laneIdentity(lane);
          return `<button type="button"
            data-instrument-review-lane="${escapeHtml(laneIdentity(item))}"
            aria-pressed="${selected}"
            ${selected ? 'class="selected"' : ""}>
            ${escapeHtml(item.label || `Selected bass part ${index + 1}`)}
          </button>`;
        })
        .join("");
      return `<section class="panel" aria-labelledby="instrument-review-heading">
        <h2 id="instrument-review-heading">4. Compare complete bass instruments</h2>
        <p>Hear the <b>same selected MIDI performance</b> through two complete
        broad-family instruments. The source stem is a tone and texture
        reference, not a candidate.</p>
        <p class="notice"><b>One controlled variable:</b> note pitches, starts,
        durations and velocities stay fixed. Only the complete instrument
        program changes. This is a listening comparison, not proof that every
        possible keyboard pitch has passed a separate full-range probe.</p>
        <div class="actions" role="group" aria-label="Eligible bass MIDI lanes">
          ${laneButtons}
        </div>
        ${lane ? `<section class="diagnostics">
          <h3>${escapeHtml(lane.label)}</h3>
          <p>${escapeHtml(lane.pair.description)}</p>
          ${lane.pair.control_label && lane.pair.challenger_label
            ? `<p class="muted">Pair under review: ${escapeHtml(lane.pair.control_label)}
              and ${escapeHtml(lane.pair.challenger_label)}. Which is A or B
              remains hidden until resolution.</p>`
            : ""}
        </section>` : ""}
        <div class="loop">
          <label>Start (seconds)<input id="instrument-review-start"
            type="number" min="0" step="0.1" value="0"></label>
          <label>End (seconds)<input id="instrument-review-end"
            type="number" min="0.5" step="0.1" value="10"></label>
          <button id="prepare-instrument-review" class="primary" type="button"
            ${busyMessage ? "disabled" : ""}>Prepare blind instrument comparison</button>
        </div>
        ${statusHtml(escapeHtml, errorMessage, busyMessage)}
        ${effectsHtml()}
      </section>`;
    }

    function comparisonHtml(
      value,
      draft,
      escapeHtml,
      errorMessage,
      busyMessage,
    ) {
      if (value.status === "reviewed") {
        return reviewedHtml(value, escapeHtml, errorMessage, busyMessage);
      }
      if (value.status === "resolved") {
        return resolvedHtml(value, escapeHtml, errorMessage, busyMessage);
      }
      const tags = value.allowed_problem_tags;
      return `<section class="panel" aria-labelledby="instrument-review-heading">
        <h2 id="instrument-review-heading">4. Blind fixed-MIDI bass-instrument review</h2>
        <p><b>Source window:</b>
          ${escapeHtml(displaySeconds(value.window.start_seconds))}–
          ${escapeHtml(displaySeconds(value.window.end_seconds))} seconds.
          The three private crops share one crop-relative browser clock.</p>
        <p class="muted">The source stem is a non-candidate reference.
          Candidate identities remain hidden. All three fixed-window crops
          were attenuated to one common sample-RMS target. Browser gain stays
          at unity because the disclosed gain was already applied by the
          server.</p>
        <table><thead><tr><th>Review track</th><th>Server crop gain</th></tr></thead>
          <tbody>${comparisonTracks(value)
            .map(
              ([key, record]) => `<tr><td>${escapeHtml(
                TRACKS.find(([track]) => track === key)?.[1] || key,
              )}</td><td>${escapeHtml(
                signedDb(record.applied_gain_db),
              )}</td></tr>`,
            )
            .join("")}</tbody></table>
        <button id="load-instrument-review-audio" class="primary" type="button">
          Load one-clock comparison
        </button>
        <p id="instrument-review-audio-status" class="decoded-status muted"
          role="status" aria-live="polite">Audio is not loaded. No independent
          drifting playback fallback is provided.</p>
        <div class="switcher" role="group"
          aria-label="Source and blind instrument transport">
          ${TRACKS.map(([key, label]) => `<button type="button"
            data-instrument-review-play="${key}" aria-pressed="false" disabled>
            Play / switch to ${escapeHtml(label)}</button>`).join("")}
          <button id="pause-instrument-review" type="button" disabled>Pause</button>
          <button id="stop-instrument-review" type="button" disabled>Stop</button>
          <output id="instrument-review-position">0.00s</output>
        </div>
        <fieldset>
          <legend>Confirm what you deliberately heard</legend>
          ${heardCheckbox(
            "source_reference",
            "I heard the source stem reference",
            draft,
          )}
          ${heardCheckbox("candidate_a", "I heard Candidate A", draft)}
          ${heardCheckbox("candidate_b", "I heard Candidate B", draft)}
        </fieldset>
        <fieldset>
          <legend>Which complete instrument is more musically useful for this fixed MIDI?</legend>
          ${CHOICES.map(([choice, label]) =>
            choiceRadio(choice, label, draft),
          ).join("")}
        </fieldset>
        <div class="candidate-grid">
          ${candidateFeedback(
            "candidate_a",
            "Candidate A",
            tags,
            value.limits,
            draft,
            escapeHtml,
          )}
          ${candidateFeedback(
            "candidate_b",
            "Candidate B",
            tags,
            value.limits,
            draft,
            escapeHtml,
          )}
        </div>
        <p id="instrument-review-draft-status" class="muted"></p>
        <button id="complete-instrument-review" class="primary" type="button"
          disabled>Complete blind instrument review</button>
        <p id="instrument-review-status" role="status" aria-live="polite"></p>
        ${statusHtml(escapeHtml, errorMessage, busyMessage)}
        ${effectsHtml()}
      </section>`;
    }

    function reviewedHtml(value, escapeHtml, errorMessage, busyMessage) {
      const review = value.review;
      return `<section class="panel success"
        aria-labelledby="instrument-review-heading">
        <h2 id="instrument-review-heading">4. Blind instrument review saved</h2>
        <p>Your explicit choice <b>${escapeHtml(
          choiceLabel(review.response.choice),
        )}</b> is bound to this selected MIDI, exact source window and hidden
        A/B assignment.</p>
        <p>${review.review_url
          ? `<a href="${escapeHtml(review.review_url)}" download>
              Export blind instrument-review JSON</a>`
          : "The blind review is stored locally."}</p>
        <button id="resolve-instrument-review" class="primary" type="button"
          ${busyMessage ? "disabled" : ""}>Resolve A/B identities</button>
        ${statusHtml(escapeHtml, errorMessage, busyMessage)}
        ${effectsHtml()}
      </section>`;
    }

    function resolvedHtml(value, escapeHtml, errorMessage, busyMessage) {
      const result = value.result;
      return `<section class="panel success"
        aria-labelledby="instrument-review-heading">
        <h2 id="instrument-review-heading">4. Instrument review resolved</h2>
        <p><b>Candidate A:</b>
          ${escapeHtml(result.assignment.candidate_a)}<br>
          <b>Candidate B:</b>
          ${escapeHtml(result.assignment.candidate_b)}</p>
        <p><b>Resolved listening outcome:</b>
          ${escapeHtml(identityLabel(result.resolved_choice))}</p>
        <p>${value.review?.review_url
          ? `<a href="${escapeHtml(value.review.review_url)}" download>
              Export blind instrument-review JSON</a>`
          : ""}
          ${result.result_url
            ? `<a href="${escapeHtml(result.result_url)}" download>
                Export resolved instrument-review JSON</a>`
            : ""}</p>
        ${statusHtml(escapeHtml, errorMessage, busyMessage)}
        <p class="notice">This result is advisory listening evidence. It does
        not automatically promote either instrument or alter the neutral
        rendering policy.</p>
        ${effectsHtml()}
      </section>`;
    }

    function unavailableHtml(message) {
      return `<section class="panel" aria-labelledby="instrument-review-heading">
        <h2 id="instrument-review-heading">4. Compare complete instruments</h2>
        <p class="notice">${escape(message)}</p>
        ${effectsHtml()}
      </section>`;
    }

    function candidateFeedback(
      candidate,
      label,
      tags,
      limits,
      draft,
      escapeHtml,
    ) {
      const selected = new Set(draft.problem_tags[candidate]);
      return `<fieldset><legend>${escapeHtml(label)} feedback</legend>
        <div class="problems">${tags
          .map(
            (tag) => `<label><input type="checkbox"
              data-instrument-review-tag
              data-instrument-review-candidate="${candidate}"
              value="${escapeHtml(tag)}"
              ${selected.has(tag) ? "checked" : ""}>
              ${escapeHtml(tag.replaceAll("_", " "))}</label>`,
          )
          .join("")}</div>
        <label>Optional private note about ${escapeHtml(label)}
          <textarea data-instrument-review-notes="${candidate}"
            maxlength="${limits.maximum_notes_characters_per_candidate}"
            rows="3">${escapeHtml(draft.notes[candidate])}</textarea>
        </label>
      </fieldset>`;
    }

    function heardCheckbox(key, label, draft) {
      return `<label><input type="checkbox"
        data-instrument-review-heard="${key}"
        ${draft.heard[key] ? "checked" : ""}> ${label}</label>`;
    }

    function choiceRadio(value, label, draft) {
      return `<label><input type="radio"
        name="instrument-review-choice" value="${value}"
        ${draft.choice === value ? "checked" : ""}> ${label}</label>`;
    }

    function effectsHtml() {
      return `<p class="muted">Preparing, loading, playing, switching,
        drafting, completing and resolving this comparison do not change
        selected MIDI, the instrument default, the song mix or the GarageBand
        pack. Only the explicit completion action records separate local
        instrument-review feedback; resolution reveals identities without
        promotion.</p>`;
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

    function pairSummary(pair) {
      return pair?.description || "Complete instrument pair";
    }

    function choiceLabel(value) {
      return CHOICES.find(([choice]) => choice === value)?.[1] || "Cannot tell";
    }

    function identityLabel(value) {
      if (value === "candidate_a") return "Candidate A";
      if (value === "candidate_b") return "Candidate B";
      if (value === "equivalent") return "Equivalent";
      if (value === "none_usable") return "Neither is usable";
      if (value === "cannot_tell") return "Cannot tell";
      return String(value || "Unavailable");
    }

    function displaySeconds(value) {
      return Number(value).toFixed(3).replace(/\.?0+$/, "");
    }

    function signedDb(value) {
      const gain = Number(value);
      return `${gain > 0 ? "+" : ""}${gain.toFixed(2)} dB`;
    }

    function requireLocalMediaUrl(value, label) {
      const url = requireString(value, label, 2048);
      if (!url.startsWith("/media/")) {
        throw new TypeError(`${label} must be a local Workbench media URL`);
      }
      return url;
    }

    function optionalApiUrl(value, label) {
      if (value == null || value === "") return null;
      const url = requireString(value, label, 2048);
      if (!url.startsWith("/api/instrument-review")) {
        throw new TypeError(`${label} must be a local instrument-review URL`);
      }
      return url;
    }

    function requireSha256(value, label) {
      if (!isSha256(value)) {
        throw new TypeError(`${label} must be a lowercase SHA-256 digest`);
      }
      return value;
    }

    function isSha256(value) {
      return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
    }

    function requireString(value, label, maximum) {
      if (typeof value !== "string" || !value || value.length > maximum) {
        throw new TypeError(`${label} must be a bounded non-empty string`);
      }
      return value;
    }

    function boundedString(value, maximum) {
      if (typeof value !== "string" || value.length > maximum) {
        throw new TypeError("Instrument review text exceeds its fixed limit");
      }
      return value;
    }

    function requireEnum(value, choices, label) {
      if (!choices.includes(value)) {
        throw new TypeError(`${label} is invalid`);
      }
      return value;
    }

    function finiteNumber(value, label) {
      const number = Number(value);
      if (!Number.isFinite(number)) {
        throw new TypeError(`${label} must be finite`);
      }
      return number;
    }

    function attenuationDb(value, label) {
      const gain = finiteNumber(value, label);
      if (gain < -60 || gain > 0) {
        throw new TypeError(`${label} must be attenuation-only`);
      }
      return gain;
    }

    function positiveInteger(value, label) {
      const number = Number(value);
      if (!Number.isSafeInteger(number) || number <= 0) {
        throw new TypeError(`${label} must be a positive integer`);
      }
      return number;
    }

    function nonNegativeInteger(value, label) {
      const number = Number(value);
      if (!Number.isSafeInteger(number) || number < 0) {
        throw new TypeError(`${label} must be a non-negative integer`);
      }
      return number;
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

    return Object.freeze({
      CHOICES,
      COMPARISON_SCHEMA,
      PLAN_SCHEMA,
      TRACKS,
      createInstrumentReview,
      normalizeComparison,
      normalizePlan,
      pairSummary,
    });
  },
);
