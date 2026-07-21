(function (root, factory) {
  "use strict";

  const exported = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = exported;
  }
  // Publish the browser contract even when an embedded browser exposes a
  // CommonJS-like module shim.
  if (root && typeof root === "object") {
    root.SunofriendWorkbenchVisualization = exported;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const MINIMUM_VIEWPORT_SECONDS = 0.5;
  const MAXIMUM_OVERSCAN_SECONDS = 5;
  const MINIMUM_TICK_COUNT = 2;
  const MAXIMUM_TICK_COUNT = 100;
  const NOTE_INDEX_SCHEMA = "sunofriend.workbench-note-interval-index.v1";
  const builtNoteIndexes = new WeakSet();

  function finiteNumber(value, label) {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      throw new TypeError(`${label} must be a finite number`);
    }
    return value;
  }

  function nonNegativeNumber(value, label) {
    const number = finiteNumber(value, label);
    if (number < 0) {
      throw new RangeError(`${label} must be non-negative`);
    }
    return number;
  }

  function positiveNumber(value, label) {
    const number = finiteNumber(value, label);
    if (number <= 0) {
      throw new RangeError(`${label} must be greater than zero`);
    }
    return number;
  }

  function safeInteger(value, label) {
    if (!Number.isSafeInteger(value)) {
      throw new TypeError(`${label} must be a safe integer`);
    }
    return value;
  }

  function clamp(value, minimum, maximum) {
    return Math.min(maximum, Math.max(minimum, value));
  }

  function immutableViewport(
    totalDurationSeconds,
    requestedZoom,
    requestedStartSeconds
  ) {
    const total = nonNegativeNumber(totalDurationSeconds, "total duration");
    const requestedScale = positiveNumber(requestedZoom, "zoom");
    const requestedStart = finiteNumber(requestedStartSeconds, "viewport start");

    if (total === 0) {
      return Object.freeze({
        totalDurationSeconds: 0,
        requestedZoom: requestedScale,
        zoom: 1,
        requestedStartSeconds: requestedStart,
        startSeconds: 0,
        endSeconds: 0,
        durationSeconds: 0,
      });
    }

    const minimumDuration = Math.min(total, MINIMUM_VIEWPORT_SECONDS);
    const requestedDuration = total / Math.max(1, requestedScale);
    const duration = clamp(requestedDuration, minimumDuration, total);
    const maximumStart = Math.max(0, total - duration);
    let start = clamp(requestedStart, 0, maximumStart);
    let end = start + duration;

    // Keep the returned geometry inside the song despite floating-point
    // addition near the right edge.
    if (end > total) {
      end = total;
      start = Math.max(0, end - duration);
    }
    if (Object.is(start, -0)) start = 0;
    if (Object.is(end, -0)) end = 0;

    return Object.freeze({
      totalDurationSeconds: total,
      requestedZoom: requestedScale,
      zoom: total / duration,
      requestedStartSeconds: requestedStart,
      startSeconds: start,
      endSeconds: end,
      durationSeconds: end - start,
    });
  }

  function clampViewport(totalDurationSeconds, zoom, requestedStartSeconds) {
    return immutableViewport(totalDurationSeconds, zoom, requestedStartSeconds);
  }

  function validateViewport(viewport) {
    if (!viewport || typeof viewport !== "object" || Array.isArray(viewport)) {
      throw new TypeError("viewport must be an object");
    }
    const total = nonNegativeNumber(
      viewport.totalDurationSeconds,
      "viewport total duration"
    );
    const zoom = positiveNumber(viewport.zoom, "viewport zoom");
    const start = nonNegativeNumber(viewport.startSeconds, "viewport start");
    const end = nonNegativeNumber(viewport.endSeconds, "viewport end");
    const duration = nonNegativeNumber(
      viewport.durationSeconds,
      "viewport duration"
    );
    if (end < start || end > total) {
      throw new RangeError("viewport range must stay inside the total duration");
    }
    const expectedDuration = end - start;
    const tolerance = Math.max(1, total) * Number.EPSILON * 16;
    if (Math.abs(duration - expectedDuration) > tolerance) {
      throw new RangeError("viewport duration must equal viewport end minus start");
    }
    if (total === 0 && (start !== 0 || end !== 0 || duration !== 0)) {
      throw new RangeError("an empty song must use an empty viewport");
    }
    if (total > 0 && duration <= 0) {
      throw new RangeError("a non-empty song must use a positive viewport");
    }
    return { total, zoom, start, end, duration };
  }

  function centreViewport(viewport, centreSeconds) {
    const geometry = validateViewport(viewport);
    const centre = finiteNumber(centreSeconds, "viewport centre");
    return immutableViewport(
      geometry.total,
      geometry.zoom,
      centre - geometry.duration / 2
    );
  }

  function pageViewport(viewport, pageCount) {
    const geometry = validateViewport(viewport);
    const pages = safeInteger(pageCount, "page count");
    if (geometry.duration === 0 || pages === 0) {
      return immutableViewport(
        geometry.total,
        geometry.zoom,
        geometry.start
      );
    }
    const offset = geometry.duration * pages;
    const requestedStart = Number.isFinite(offset)
      ? geometry.start + offset
      : pages > 0
        ? geometry.total
        : 0;
    return immutableViewport(
      geometry.total,
      geometry.zoom,
      Number.isFinite(requestedStart)
        ? requestedStart
        : pages > 0
          ? geometry.total
          : 0
    );
  }

  function tickStepSeconds(spanSeconds, targetTickCount) {
    const rawStep = spanSeconds / targetTickCount;
    if (!Number.isFinite(rawStep) || rawStep <= 0) return 0;

    const subMinuteMultipliers = [1, 2, 5, 10, 15, 30, 60];
    if (rawStep < 1) {
      const exponent = Math.floor(Math.log10(rawStep));
      const scale = 10 ** exponent;
      const scaled = rawStep / scale;
      for (const multiplier of [1, 2, 5, 10]) {
        if (scaled <= multiplier) return multiplier * scale;
      }
    }
    if (rawStep <= 60) {
      for (const step of subMinuteMultipliers) {
        if (rawStep <= step) return step;
      }
    }
    for (const step of [120, 300, 600, 900, 1800, 3600]) {
      if (rawStep <= step) return step;
    }
    for (const step of [7200, 10800, 21600, 43200, 86400]) {
      if (rawStep <= step) return step;
    }

    const days = rawStep / 86400;
    const exponent = Math.floor(Math.log10(days));
    const scale = 10 ** exponent;
    const scaled = days / scale;
    for (const multiplier of [1, 2, 5, 10]) {
      if (scaled <= multiplier) return multiplier * scale * 86400;
    }
    throw new RangeError("viewport duration is too large to create finite ticks");
  }

  function normaliseTickSeconds(value, step) {
    if (value === 0) return 0;
    const exponent = Math.floor(Math.log10(step));
    const decimalPlaces = clamp(2 - exponent, 0, 12);
    return Number(value.toFixed(decimalPlaces));
  }

  function buildViewportTicks(viewport, targetTickCount) {
    const geometry = validateViewport(viewport);
    const target = targetTickCount === undefined ? 6 : targetTickCount;
    safeInteger(target, "target tick count");
    if (target < MINIMUM_TICK_COUNT || target > MAXIMUM_TICK_COUNT) {
      throw new RangeError(
        `target tick count must be between ${MINIMUM_TICK_COUNT} and ${MAXIMUM_TICK_COUNT}`
      );
    }
    if (geometry.duration === 0) {
      return Object.freeze([
        Object.freeze({
          seconds: 0,
          offsetSeconds: 0,
          ratio: 0,
          edge: true,
          stepSeconds: 0,
        }),
      ]);
    }

    const step = tickStepSeconds(geometry.duration, target);
    const tolerance = Math.max(step, geometry.total, 1) * Number.EPSILON * 32;
    const tickValues = [];

    function addTick(seconds, edge) {
      const bounded = clamp(seconds, geometry.start, geometry.end);
      const normalised = edge ? bounded : normaliseTickSeconds(bounded, step);
      const existing = tickValues.find(
        (tick) => Math.abs(tick.seconds - normalised) <= tolerance
      );
      if (existing) {
        existing.edge = existing.edge || edge;
        if (edge) existing.seconds = bounded;
        return;
      }
      tickValues.push({
        seconds: normalised,
        edge,
      });
    }

    addTick(geometry.start, true);
    const firstIndex = Math.ceil(geometry.start / step - tolerance / step);
    const lastIndex = Math.floor(geometry.end / step + tolerance / step);
    const maximumGridTicks = MAXIMUM_TICK_COUNT + 2;
    let gridTickCount = 0;
    for (let index = firstIndex; index <= lastIndex; index += 1) {
      const seconds = index * step;
      if (!Number.isFinite(seconds)) break;
      if (
        seconds >= geometry.start - tolerance &&
        seconds <= geometry.end + tolerance
      ) {
        addTick(seconds, false);
        gridTickCount += 1;
        if (gridTickCount > maximumGridTicks) {
          throw new RangeError("tick calculation exceeded its deterministic bound");
        }
      }
    }
    addTick(geometry.end, true);

    const ticks = tickValues
      .sort((left, right) => left.seconds - right.seconds)
      .map((tick) =>
        Object.freeze({
          seconds: tick.seconds,
          offsetSeconds: tick.seconds - geometry.start,
          ratio: clamp(
            (tick.seconds - geometry.start) / geometry.duration,
            0,
            1
          ),
          edge: tick.edge,
          stepSeconds: step,
        })
      );
    return Object.freeze(ticks);
  }

  function buildNoteIntervalIndex(notes) {
    if (!Array.isArray(notes)) {
      throw new TypeError("notes must be an array");
    }
    const entries = notes.map((note, sourceIndex) => {
      if (!note || typeof note !== "object" || Array.isArray(note)) {
        throw new TypeError(`note ${sourceIndex} must be an object`);
      }
      const startSeconds = nonNegativeNumber(
        note.start_seconds,
        `note ${sourceIndex} start`
      );
      const endSeconds = nonNegativeNumber(
        note.end_seconds,
        `note ${sourceIndex} end`
      );
      if (endSeconds < startSeconds) {
        throw new RangeError(`note ${sourceIndex} end must not precede its start`);
      }
      const snapshot = Object.freeze({ ...note });
      return {
        startSeconds,
        endSeconds,
        sourceIndex,
        note: snapshot,
      };
    });
    entries.sort(
      (left, right) =>
        left.startSeconds - right.startSeconds ||
        left.endSeconds - right.endSeconds ||
        left.sourceIndex - right.sourceIndex
    );

    let maximumEnd = -Infinity;
    const prefixMaximumEndSeconds = [];
    for (const entry of entries) {
      maximumEnd = Math.max(maximumEnd, entry.endSeconds);
      prefixMaximumEndSeconds.push(maximumEnd);
      Object.freeze(entry);
    }
    Object.freeze(entries);
    Object.freeze(prefixMaximumEndSeconds);
    const index = Object.freeze({
      schema: NOTE_INDEX_SCHEMA,
      noteCount: entries.length,
      entries,
      prefixMaximumEndSeconds,
    });
    builtNoteIndexes.add(index);
    return index;
  }

  function validateOverscan(overscanSeconds) {
    const overscan =
      overscanSeconds === undefined
        ? 0
        : nonNegativeNumber(overscanSeconds, "overscan");
    if (overscan > MAXIMUM_OVERSCAN_SECONDS) {
      throw new RangeError(
        `overscan must not exceed ${MAXIMUM_OVERSCAN_SECONDS} seconds`
      );
    }
    return overscan;
  }

  function firstPrefixGreater(prefixMaximumEndSeconds, value, upperBound) {
    let low = 0;
    let high = upperBound;
    while (low < high) {
      const middle = low + Math.floor((high - low) / 2);
      if (prefixMaximumEndSeconds[middle] > value) high = middle;
      else low = middle + 1;
    }
    return low;
  }

  function firstStartAtOrAfter(entries, value) {
    let low = 0;
    let high = entries.length;
    while (low < high) {
      const middle = low + Math.floor((high - low) / 2);
      if (entries[middle].startSeconds >= value) high = middle;
      else low = middle + 1;
    }
    return low;
  }

  function queryNoteIntervalIndex(
    index,
    visibleStartSeconds,
    visibleEndSeconds,
    overscanSeconds
  ) {
    if (!index || typeof index !== "object" || !builtNoteIndexes.has(index)) {
      throw new TypeError("note index must come from buildNoteIntervalIndex");
    }
    const visibleStart = nonNegativeNumber(
      visibleStartSeconds,
      "visible range start"
    );
    const visibleEnd = nonNegativeNumber(
      visibleEndSeconds,
      "visible range end"
    );
    if (visibleEnd <= visibleStart) {
      throw new RangeError("visible range end must be greater than its start");
    }
    const overscan = validateOverscan(overscanSeconds);
    const queryStart = Math.max(0, visibleStart - overscan);
    const queryEnd = visibleEnd + overscan;
    if (!Number.isFinite(queryEnd)) {
      throw new RangeError("visible range plus overscan must remain finite");
    }

    const upper = firstStartAtOrAfter(index.entries, queryEnd);
    const lower = firstPrefixGreater(
      index.prefixMaximumEndSeconds,
      queryStart,
      upper
    );
    const result = [];
    for (let position = lower; position < upper; position += 1) {
      const entry = index.entries[position];
      if (
        entry.endSeconds > entry.startSeconds &&
        entry.startSeconds < queryEnd &&
        entry.endSeconds > queryStart
      ) {
        result.push(entry.note);
      }
    }
    return Object.freeze(result);
  }

  function validateWaveformViewport(viewport, totalDurationSeconds) {
    const geometry = validateViewport(viewport);
    const total = nonNegativeNumber(totalDurationSeconds, "waveform duration");
    if (total > geometry.total + Number.EPSILON) {
      throw new RangeError(
        "waveform duration must not exceed the viewport total duration"
      );
    }
    return { ...geometry, waveformTotal: total };
  }

  function sliceWaveformBins(
    bins,
    totalDurationSeconds,
    viewport,
    overscanSeconds
  ) {
    if (!Array.isArray(bins)) {
      throw new TypeError("waveform bins must be an array");
    }
    const geometry = validateWaveformViewport(viewport, totalDurationSeconds);
    const overscan = validateOverscan(overscanSeconds);
    const sliceStart = Math.min(
      geometry.waveformTotal,
      Math.max(0, geometry.start - overscan)
    );
    const sliceEnd = Math.max(
      sliceStart,
      Math.min(geometry.waveformTotal, geometry.end + overscan)
    );
    if (!bins.length) {
      return Object.freeze({
        totalBinCount: 0,
        startIndex: 0,
        endIndexExclusive: 0,
        visibleStartSeconds: geometry.start,
        visibleEndSeconds: geometry.end,
        sliceStartSeconds: sliceStart,
        sliceEndSeconds: sliceEnd,
        bins: Object.freeze([]),
      });
    }
    if (geometry.waveformTotal <= 0) {
      throw new RangeError("non-empty waveform bins require a positive duration");
    }

    const count = bins.length;
    const startIndex = clamp(
      Math.floor((sliceStart / geometry.waveformTotal) * count),
      0,
      count
    );
    const endIndexExclusive = clamp(
      Math.ceil((sliceEnd / geometry.waveformTotal) * count),
      startIndex,
      count
    );
    const selected = [];
    for (let binIndex = startIndex; binIndex < endIndexExclusive; binIndex += 1) {
      const bin = bins[binIndex];
      if (!Array.isArray(bin) || bin.length !== 2) {
        throw new TypeError(`waveform bin ${binIndex} must contain [minimum, maximum]`);
      }
      const minimum = finiteNumber(bin[0], `waveform bin ${binIndex} minimum`);
      const maximum = finiteNumber(bin[1], `waveform bin ${binIndex} maximum`);
      if (minimum > maximum) {
        throw new RangeError(
          `waveform bin ${binIndex} minimum must not exceed its maximum`
        );
      }
      const startSeconds = (geometry.waveformTotal * binIndex) / count;
      const endSeconds = (geometry.waveformTotal * (binIndex + 1)) / count;
      if (startSeconds < sliceEnd && endSeconds > sliceStart) {
        selected.push(
          Object.freeze({
            binIndex,
            startSeconds,
            endSeconds,
            fullSongStartRatio: binIndex / count,
            fullSongEndRatio: (binIndex + 1) / count,
            minimum,
            maximum,
          })
        );
      }
    }

    const boundedStartIndex = selected.length
      ? selected[0].binIndex
      : startIndex;
    const boundedEndIndexExclusive = selected.length
      ? selected[selected.length - 1].binIndex + 1
      : boundedStartIndex;
    return Object.freeze({
      totalBinCount: count,
      startIndex: boundedStartIndex,
      endIndexExclusive: boundedEndIndexExclusive,
      visibleStartSeconds: geometry.start,
      visibleEndSeconds: geometry.end,
      sliceStartSeconds: sliceStart,
      sliceEndSeconds: sliceEnd,
      bins: Object.freeze(selected),
    });
  }

  return Object.freeze({
    MINIMUM_VIEWPORT_SECONDS,
    MAXIMUM_OVERSCAN_SECONDS,
    clampViewport,
    centreViewport,
    pageViewport,
    buildViewportTicks,
    buildNoteIntervalIndex,
    queryNoteIntervalIndex,
    sliceWaveformBins,
  });
});
