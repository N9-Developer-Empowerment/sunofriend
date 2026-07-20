(function (root, factory) {
  "use strict";

  const exported = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = exported;
  }
  // Some embedded browsers expose a CommonJS-like `module` shim while still
  // loading this file as a normal page script. Always publish the page global
  // as well so the Workbench controller has a deterministic browser contract.
  if (root && typeof root === "object") {
    root.SunofriendWorkbenchTransport = exported;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const DEFAULT_SCHEDULE_LEAD_SECONDS = 0.025;

  function finiteNumber(value, label) {
    const number = Number(value);
    if (!Number.isFinite(number)) {
      throw new TypeError(`${label} must be a finite number`);
    }
    return number;
  }

  function positiveInteger(value, label) {
    const number = Number(value);
    if (!Number.isInteger(number) || number <= 0) {
      throw new TypeError(`${label} must be a positive integer`);
    }
    return number;
  }

  function frameCountForLoop(sampleRate, loopStartSeconds, loopEndSeconds) {
    const rate = positiveInteger(sampleRate, "sample rate");
    const start = finiteNumber(loopStartSeconds, "loop start");
    const end = finiteNumber(loopEndSeconds, "loop end");
    if (start < 0 || end <= start) {
      throw new RangeError("loop end must be greater than a non-negative loop start");
    }
    return Math.max(1, Math.round((end - start) * rate));
  }

  function wrapAbsolutePlayhead(playheadSeconds, loopStartSeconds, loopEndSeconds) {
    const playhead = finiteNumber(playheadSeconds, "playhead");
    const start = finiteNumber(loopStartSeconds, "loop start");
    const end = finiteNumber(loopEndSeconds, "loop end");
    const duration = end - start;
    if (start < 0 || duration <= 0) {
      throw new RangeError("loop end must be greater than a non-negative loop start");
    }
    const relative = ((playhead - start) % duration + duration) % duration;
    return start + relative;
  }

  function absolutePlayheadAt(
    anchorPlayheadSeconds,
    anchorContextTime,
    contextTime,
    loopStartSeconds,
    loopEndSeconds
  ) {
    const anchor = finiteNumber(anchorPlayheadSeconds, "anchor playhead");
    const anchorTime = finiteNumber(anchorContextTime, "anchor context time");
    const now = finiteNumber(contextTime, "context time");
    const elapsed = Math.max(0, now - anchorTime);
    return wrapAbsolutePlayhead(
      anchor + elapsed,
      loopStartSeconds,
      loopEndSeconds
    );
  }

  function bufferEntries(decodedBuffers) {
    if (decodedBuffers instanceof Map) {
      return Array.from(decodedBuffers.entries());
    }
    if (
      decodedBuffers !== null &&
      typeof decodedBuffers === "object" &&
      !Array.isArray(decodedBuffers)
    ) {
      return Object.entries(decodedBuffers);
    }
    throw new TypeError("decoded buffers must be a Map or plain object");
  }

  function validateContext(context) {
    if (!context || typeof context !== "object") {
      throw new TypeError("audio context is required");
    }
    positiveInteger(context.sampleRate, "audio context sample rate");
    finiteNumber(context.currentTime, "audio context current time");
    if (typeof context.createBuffer !== "function") {
      throw new TypeError("audio context must provide createBuffer");
    }
    if (typeof context.createBufferSource !== "function") {
      throw new TypeError("audio context must provide createBufferSource");
    }
    if (!context.destination) {
      throw new TypeError("audio context destination is required");
    }
  }

  function validateDecodedBuffer(buffer, contextSampleRate, key) {
    if (!buffer || typeof buffer.getChannelData !== "function") {
      throw new TypeError(`decoded buffer ${key} is not an AudioBuffer`);
    }
    const channels = positiveInteger(
      buffer.numberOfChannels,
      `decoded buffer ${key} channel count`
    );
    positiveInteger(buffer.length, `decoded buffer ${key} frame count`);
    const sampleRate = positiveInteger(
      buffer.sampleRate,
      `decoded buffer ${key} sample rate`
    );
    if (sampleRate !== contextSampleRate) {
      throw new RangeError(
        `decoded buffer ${key} sample rate must match the AudioContext sample rate`
      );
    }
    return channels;
  }

  function copyChannel(source, target, channel, targetFrameCount) {
    const sourceData = source.getChannelData(channel);
    const targetData = target.getChannelData(channel);
    if (!sourceData || !targetData || typeof targetData.set !== "function") {
      throw new TypeError("decoded AudioBuffer channel data is unavailable");
    }
    targetData.set(sourceData.subarray(0, targetFrameCount), 0);
  }

  function normaliseDecodedBuffers(context, decodedBuffers, targetFrameCount) {
    validateContext(context);
    const frameCount = positiveInteger(targetFrameCount, "target frame count");
    const entries = bufferEntries(decodedBuffers);
    if (!entries.length) {
      throw new RangeError("at least one decoded buffer is required");
    }
    const normalised = new Map();
    for (const [rawKey, source] of entries) {
      const key = String(rawKey);
      if (!key) {
        throw new TypeError("decoded buffer keys must not be empty");
      }
      if (normalised.has(key)) {
        throw new RangeError(`decoded buffer key is duplicated: ${key}`);
      }
      const channels = validateDecodedBuffer(source, context.sampleRate, key);
      const target = context.createBuffer(channels, frameCount, context.sampleRate);
      for (let channel = 0; channel < channels; channel += 1) {
        copyChannel(source, target, channel, frameCount);
      }
      normalised.set(key, target);
    }
    return normalised;
  }

  function safeDisconnect(source) {
    if (!source || typeof source.disconnect !== "function") return;
    try {
      source.disconnect();
    } catch (_) {
      // A source can already be disconnected after an asynchronous onended.
    }
  }

  function retireSource(source, when) {
    if (!source) return;
    const previousOnEnded = source.onended;
    source.onended = function () {
      safeDisconnect(source);
      if (typeof previousOnEnded === "function") previousOnEnded.call(source);
    };
    source.stop(when);
  }

  class DecodedLoopTransport {
    constructor(options) {
      const settings = options || {};
      validateContext(settings.audioContext);
      this.audioContext = settings.audioContext;
      this.requestedLoopStartSeconds = finiteNumber(
        settings.loopStartSeconds,
        "loop start"
      );
      this.requestedLoopEndSeconds = finiteNumber(
        settings.loopEndSeconds,
        "loop end"
      );
      this.frameCount = frameCountForLoop(
        this.audioContext.sampleRate,
        this.requestedLoopStartSeconds,
        this.requestedLoopEndSeconds
      );
      this.loopStartSeconds = this.requestedLoopStartSeconds;
      this.loopEndSeconds =
        this.loopStartSeconds + this.frameCount / this.audioContext.sampleRate;
      this.loopDurationSeconds = this.frameCount / this.audioContext.sampleRate;
      this.scheduleLeadSeconds = finiteNumber(
        settings.scheduleLeadSeconds === undefined
          ? DEFAULT_SCHEDULE_LEAD_SECONDS
          : settings.scheduleLeadSeconds,
        "schedule lead"
      );
      if (this.scheduleLeadSeconds < 0 || this.scheduleLeadSeconds > 1) {
        throw new RangeError("schedule lead must be between zero and one second");
      }
      this.buffers = normaliseDecodedBuffers(
        this.audioContext,
        settings.decodedBuffers,
        this.frameCount
      );
      this._activeKey = null;
      this._source = null;
      this._playing = false;
      this._storedPlayheadSeconds = this.loopStartSeconds;
      this._anchorPlayheadSeconds = this.loopStartSeconds;
      this._anchorContextTime = finiteNumber(
        this.audioContext.currentTime,
        "audio context current time"
      );
      this._sourceSerial = 0;
    }

    get activeKey() {
      return this._activeKey;
    }

    get playing() {
      return this._playing;
    }

    get sourceSerial() {
      return this._sourceSerial;
    }

    get playheadSeconds() {
      if (!this._playing) return this._storedPlayheadSeconds;
      return absolutePlayheadAt(
        this._anchorPlayheadSeconds,
        this._anchorContextTime,
        this.audioContext.currentTime,
        this.loopStartSeconds,
        this.loopEndSeconds
      );
    }

    getBuffer(key) {
      return this.buffers.get(String(key)) || null;
    }

    _requireBuffer(key) {
      const normalisedKey = String(key);
      const buffer = this.buffers.get(normalisedKey);
      if (!normalisedKey || !buffer) {
        throw new RangeError(`unknown decoded buffer: ${normalisedKey}`);
      }
      return { key: normalisedKey, buffer };
    }

    _newSource(buffer) {
      const source = this.audioContext.createBufferSource();
      source.buffer = buffer;
      source.loop = true;
      source.loopStart = 0;
      source.loopEnd = this.loopDurationSeconds;
      source.connect(this.audioContext.destination);
      this._sourceSerial += 1;
      return source;
    }

    _schedule(key, playheadSeconds, followCurrentClock) {
      const selected = this._requireBuffer(key);
      const when =
        finiteNumber(this.audioContext.currentTime, "audio context current time") +
        this.scheduleLeadSeconds;
      const absolutePlayhead = followCurrentClock
        ? absolutePlayheadAt(
            this._anchorPlayheadSeconds,
            this._anchorContextTime,
            when,
            this.loopStartSeconds,
            this.loopEndSeconds
          )
        : wrapAbsolutePlayhead(
            playheadSeconds,
            this.loopStartSeconds,
            this.loopEndSeconds
          );
      const offsetSeconds = absolutePlayhead - this.loopStartSeconds;
      const nextSource = this._newSource(selected.buffer);
      const previousSource = this._source;
      const previousKey = this._activeKey;

      // Start first so a failed new schedule cannot silence the current source.
      nextSource.start(when, offsetSeconds);
      if (previousSource) retireSource(previousSource, when);

      this._source = nextSource;
      this._activeKey = selected.key;
      this._playing = true;
      this._storedPlayheadSeconds = absolutePlayhead;
      this._anchorPlayheadSeconds = absolutePlayhead;
      this._anchorContextTime = when;
      nextSource.onended = () => {
        safeDisconnect(nextSource);
        if (this._source !== nextSource) return;
        this._storedPlayheadSeconds = this.playheadSeconds;
        this._source = null;
        this._playing = false;
      };
      return {
        key: selected.key,
        previousKey,
        when,
        absolutePlayheadSeconds: absolutePlayhead,
        bufferOffsetSeconds: offsetSeconds,
        sourceSerial: this._sourceSerial,
      };
    }

    play(key) {
      const selectedKey = key === undefined ? this._activeKey : key;
      if (selectedKey === null || selectedKey === undefined) {
        throw new RangeError("play requires a decoded buffer key");
      }
      return this._schedule(selectedKey, this.playheadSeconds, this._playing);
    }

    switchTo(key) {
      return this._schedule(key, this.playheadSeconds, this._playing);
    }

    seek(playheadSeconds) {
      const target = wrapAbsolutePlayhead(
        playheadSeconds,
        this.loopStartSeconds,
        this.loopEndSeconds
      );
      if (this._playing) return this._schedule(this._activeKey, target, false);
      this._storedPlayheadSeconds = target;
      this._anchorPlayheadSeconds = target;
      this._anchorContextTime = finiteNumber(
        this.audioContext.currentTime,
        "audio context current time"
      );
      return {
        key: this._activeKey,
        previousKey: this._activeKey,
        when: null,
        absolutePlayheadSeconds: target,
        bufferOffsetSeconds: target - this.loopStartSeconds,
        sourceSerial: this._sourceSerial,
      };
    }

    pause() {
      const position = this.playheadSeconds;
      const source = this._source;
      this._source = null;
      this._playing = false;
      this._storedPlayheadSeconds = position;
      this._anchorPlayheadSeconds = position;
      this._anchorContextTime = finiteNumber(
        this.audioContext.currentTime,
        "audio context current time"
      );
      if (source) retireSource(source, this._anchorContextTime);
      return position;
    }

    stop() {
      this.pause();
      this._storedPlayheadSeconds = this.loopStartSeconds;
      this._anchorPlayheadSeconds = this.loopStartSeconds;
      return this._storedPlayheadSeconds;
    }

    snapshot() {
      return {
        activeKey: this._activeKey,
        playing: this._playing,
        playheadSeconds: this.playheadSeconds,
        loopStartSeconds: this.loopStartSeconds,
        loopEndSeconds: this.loopEndSeconds,
        loopDurationSeconds: this.loopDurationSeconds,
        frameCount: this.frameCount,
        sampleRate: this.audioContext.sampleRate,
        sourceSerial: this._sourceSerial,
      };
    }
  }

  return Object.freeze({
    DEFAULT_SCHEDULE_LEAD_SECONDS,
    DecodedLoopTransport,
    absolutePlayheadAt,
    frameCountForLoop,
    normaliseDecodedBuffers,
    normalizeDecodedBuffers: normaliseDecodedBuffers,
    wrapAbsolutePlayhead,
  });
});
