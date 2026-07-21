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
  const DEFAULT_MAX_DECODED_SEQUENCE_BYTES = 64 * 1024 * 1024;
  const immutableDecodedBuffers = new WeakSet();

  function finiteNumber(value, label) {
    const number = Number(value);
    if (!Number.isFinite(number)) {
      throw new TypeError(`${label} must be a finite number`);
    }
    return number;
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

  function nonEmptyString(value, label) {
    if (typeof value !== "string" || !value.trim()) {
      throw new TypeError(`${label} must be a non-empty string`);
    }
    return value;
  }

  function sha256(value, label) {
    const digest = nonEmptyString(value, label);
    if (!/^[0-9a-f]{64}$/.test(digest)) {
      throw new TypeError(`${label} must be a lowercase SHA-256 digest`);
    }
    return digest;
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

  // Web Audio does not expose a read-only AudioBuffer type. This explicit
  // ownership marker lets a caller promise that it will never mutate the
  // decoded PCM again. The marker is module-private, so merely freezing an
  // AudioBuffer wrapper is not sufficient to bypass the defensive copy.
  function markDecodedBufferImmutable(buffer) {
    if (!buffer || (typeof buffer !== "object" && typeof buffer !== "function")) {
      throw new TypeError("decoded buffer must be an object");
    }
    immutableDecodedBuffers.add(buffer);
    return buffer;
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
      if (
        source.length === frameCount &&
        immutableDecodedBuffers.has(source)
      ) {
        normalised.set(key, source);
        continue;
      }
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

  function cancelSources(sources, when) {
    for (const source of sources) {
      if (!source) continue;
      if (typeof source.stop === "function") {
        try {
          source.stop(when);
        } catch (_) {
          // An unstarted or already-ended source can reject stop(). It still
          // must be disconnected before the failed schedule is reported.
        }
      }
      safeDisconnect(source);
    }
  }

  function rosterEntries(roster) {
    if (!Array.isArray(roster) || !roster.length) {
      throw new TypeError("roster must be a non-empty array");
    }
    const entries = [];
    const seen = new Set();
    for (const rawKey of roster) {
      const key = nonEmptyString(rawKey, "roster key");
      if (seen.has(key)) {
        throw new RangeError(`roster key is duplicated: ${key}`);
      }
      seen.add(key);
      entries.push(key);
    }
    return entries;
  }

  function sameRoster(left, right) {
    return (
      Array.isArray(right) &&
      left.length === right.length &&
      left.every((key, index) => key === right[index])
    );
  }

  function decodedBufferBytes(buffer) {
    const bytes = buffer.numberOfChannels * buffer.length * 4;
    if (!Number.isSafeInteger(bytes) || bytes <= 0) {
      throw new RangeError("decoded buffer byte size exceeds the safe integer range");
    }
    return bytes;
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

  class DecodedGroupLoopTransport {
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
      this._activeKeys = [];
      this._sources = [];
      this._playing = false;
      this._storedPlayheadSeconds = this.loopStartSeconds;
      this._anchorPlayheadSeconds = this.loopStartSeconds;
      this._anchorContextTime = finiteNumber(
        this.audioContext.currentTime,
        "audio context current time"
      );
      this._sourceSerial = 0;
      this._groupSerial = 0;
    }

    get activeKeys() {
      return this._activeKeys.slice();
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

    _requireBuffers(keys) {
      if (
        keys === null ||
        keys === undefined ||
        typeof keys === "string" ||
        typeof keys[Symbol.iterator] !== "function"
      ) {
        throw new TypeError("decoded buffer keys must be a non-empty iterable");
      }
      const selected = [];
      const seen = new Set();
      for (const rawKey of keys) {
        const key = String(rawKey);
        if (!key) {
          throw new TypeError("decoded buffer keys must not be empty");
        }
        if (seen.has(key)) {
          throw new RangeError(`decoded buffer key is duplicated: ${key}`);
        }
        const buffer = this.buffers.get(key);
        if (!buffer) {
          throw new RangeError(`unknown decoded buffer: ${key}`);
        }
        seen.add(key);
        selected.push({ key, buffer });
      }
      if (!selected.length) {
        throw new RangeError("at least one decoded buffer key is required");
      }
      return selected;
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

    _schedule(keys, playheadSeconds, followCurrentClock) {
      // Resolve the complete group before creating a node or touching current
      // playback. A bad key therefore cannot partially change the active mix.
      const selected = this._requireBuffers(keys);
      const currentTime = finiteNumber(
        this.audioContext.currentTime,
        "audio context current time"
      );
      const when = currentTime + this.scheduleLeadSeconds;
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
      const nextSources = [];

      try {
        for (const item of selected) {
          nextSources.push(this._newSource(item.buffer));
        }
        for (const source of nextSources) {
          source.start(when, offsetSeconds);
        }
      } catch (error) {
        // Some nodes may already be scheduled for the shared future time.
        // Cancel and disconnect every replacement node, including nodes whose
        // start failed, while leaving the old group and its clock untouched.
        cancelSources(nextSources, when);
        throw error;
      }

      const previousSources = this._sources.slice();
      const previousKeys = this._activeKeys.slice();
      const nextKeys = selected.map((item) => item.key);
      const groupSerial = this._groupSerial + 1;

      // The replacement is complete. Only now may the existing group retire,
      // and every old node retires on the same boundary used by every new one.
      for (const source of previousSources) retireSource(source, when);

      this._groupSerial = groupSerial;
      this._sources = nextSources;
      this._activeKeys = nextKeys;
      this._playing = true;
      this._storedPlayheadSeconds = absolutePlayhead;
      this._anchorPlayheadSeconds = absolutePlayhead;
      this._anchorContextTime = when;

      for (const nextSource of nextSources) {
        nextSource.onended = () => {
          safeDisconnect(nextSource);
          if (this._groupSerial !== groupSerial) return;
          const remaining = this._sources.filter(
            (source) => source !== nextSource
          );
          this._sources = remaining;
          if (remaining.length) return;
          this._storedPlayheadSeconds = this.playheadSeconds;
          this._playing = false;
        };
      }

      return {
        keys: nextKeys.slice(),
        previousKeys,
        when,
        absolutePlayheadSeconds: absolutePlayhead,
        bufferOffsetSeconds: offsetSeconds,
        sourceSerial: this._sourceSerial,
        groupSerial: this._groupSerial,
      };
    }

    play(keys) {
      const selectedKeys = keys === undefined ? this._activeKeys : keys;
      return this._schedule(selectedKeys, this.playheadSeconds, this._playing);
    }

    switchTo(keys) {
      return this._schedule(keys, this.playheadSeconds, this._playing);
    }

    seek(playheadSeconds) {
      const target = wrapAbsolutePlayhead(
        playheadSeconds,
        this.loopStartSeconds,
        this.loopEndSeconds
      );
      if (this._playing) return this._schedule(this._activeKeys, target, false);
      this._storedPlayheadSeconds = target;
      this._anchorPlayheadSeconds = target;
      this._anchorContextTime = finiteNumber(
        this.audioContext.currentTime,
        "audio context current time"
      );
      return {
        keys: this._activeKeys.slice(),
        previousKeys: this._activeKeys.slice(),
        when: null,
        absolutePlayheadSeconds: target,
        bufferOffsetSeconds: target - this.loopStartSeconds,
        sourceSerial: this._sourceSerial,
        groupSerial: this._groupSerial,
      };
    }

    pause() {
      const position = this.playheadSeconds;
      const sources = this._sources.slice();
      this._sources = [];
      this._playing = false;
      this._storedPlayheadSeconds = position;
      this._anchorPlayheadSeconds = position;
      this._anchorContextTime = finiteNumber(
        this.audioContext.currentTime,
        "audio context current time"
      );
      for (const source of sources) retireSource(source, this._anchorContextTime);
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
        activeKeys: this._activeKeys.slice(),
        playing: this._playing,
        playheadSeconds: this.playheadSeconds,
        loopStartSeconds: this.loopStartSeconds,
        loopEndSeconds: this.loopEndSeconds,
        loopDurationSeconds: this.loopDurationSeconds,
        frameCount: this.frameCount,
        sampleRate: this.audioContext.sampleRate,
        sourceSerial: this._sourceSerial,
        groupSerial: this._groupSerial,
      };
    }
  }

  class DecodedChunkSequenceTransport {
    constructor(options) {
      const settings = options || {};
      validateContext(settings.audioContext);
      this.audioContext = settings.audioContext;
      this.streamHash = sha256(settings.streamHash, "stream hash");
      this.presetId = nonEmptyString(settings.presetId, "preset ID");
      this.roster = Object.freeze(rosterEntries(settings.roster));
      this.totalFrameCount = positiveInteger(
        settings.totalFrameCount,
        "total frame count"
      );
      this.chunkFrameCount = positiveInteger(
        settings.chunkFrameCount,
        "chunk frame count"
      );
      this.chunkCount = Math.ceil(
        this.totalFrameCount / this.chunkFrameCount
      );
      this.durationSeconds =
        this.totalFrameCount / this.audioContext.sampleRate;
      this.maxDecodedBytes = positiveInteger(
        settings.maxDecodedBytes === undefined
          ? DEFAULT_MAX_DECODED_SEQUENCE_BYTES
          : settings.maxDecodedBytes,
        "maximum decoded bytes"
      );
      this.scheduleLeadSeconds = finiteNumber(
        settings.scheduleLeadSeconds === undefined
          ? DEFAULT_SCHEDULE_LEAD_SECONDS
          : settings.scheduleLeadSeconds,
        "schedule lead"
      );
      if (this.scheduleLeadSeconds < 0 || this.scheduleLeadSeconds > 1) {
        throw new RangeError("schedule lead must be between zero and one second");
      }

      this._chunks = new Map();
      this._groups = new Map();
      this._retiringSources = [];
      this._decodedBytes = 0;
      this._currentChunkIndex = null;
      this._storedFrame = 0;
      this._anchorFrame = 0;
      this._anchorContextTime = finiteNumber(
        this.audioContext.currentTime,
        "audio context current time"
      );
      this._playing = false;
      this._buffering = true;
      this._ended = false;
      this._sourceSerial = 0;
      this._sequenceSerial = 0;
    }

    get playing() {
      this._refreshClockState();
      return this._playing;
    }

    get buffering() {
      this._refreshClockState();
      return this._buffering;
    }

    get ended() {
      this._refreshClockState();
      return this._ended;
    }

    get sourceSerial() {
      return this._sourceSerial;
    }

    get sequenceSerial() {
      return this._sequenceSerial;
    }

    get decodedBytes() {
      return this._decodedBytes;
    }

    get playheadFrame() {
      this._refreshClockState();
      return this._playheadFrameWithoutRefresh();
    }

    get playheadSeconds() {
      return this.playheadFrame / this.audioContext.sampleRate;
    }

    get currentChunkIndex() {
      this._refreshClockState();
      return this._currentChunkIndex;
    }

    get neededChunkIndex() {
      this._refreshClockState();
      return this._neededChunkIndexWithoutRefresh();
    }

    _chunkIndexForFrame(frame) {
      if (frame >= this.totalFrameCount) return null;
      return Math.floor(frame / this.chunkFrameCount);
    }

    _expectedChunk(index) {
      const chunkIndex = nonNegativeInteger(index, "chunk index");
      if (chunkIndex >= this.chunkCount) {
        throw new RangeError("chunk index exceeds the sequence chunk count");
      }
      const startFrame = chunkIndex * this.chunkFrameCount;
      return {
        index: chunkIndex,
        startFrame,
        frameCount: Math.min(
          this.chunkFrameCount,
          this.totalFrameCount - startFrame
        ),
      };
    }

    _playheadFrameWithoutRefresh() {
      if (!this._playing) return this._storedFrame;
      const now = finiteNumber(
        this.audioContext.currentTime,
        "audio context current time"
      );
      const elapsedFrames = Math.max(
        0,
        Math.floor(
          (now - this._anchorContextTime) * this.audioContext.sampleRate +
            Number.EPSILON
        )
      );
      return Math.min(
        this.totalFrameCount,
        this._anchorFrame + elapsedFrames
      );
    }

    _boundaryContextTime(chunk) {
      return (
        this._anchorContextTime +
        (chunk.startFrame + chunk.frameCount - this._anchorFrame) /
          this.audioContext.sampleRate
      );
    }

    _neededChunkIndexWithoutRefresh() {
      if (this._ended) return null;
      if (this._buffering) {
        return this._chunkIndexForFrame(this._storedFrame);
      }
      if (!this._playing || this._currentChunkIndex === null) {
        const index = this._chunkIndexForFrame(this._storedFrame);
        return index !== null && !this._chunks.has(index) ? index : null;
      }
      const nextIndex = this._currentChunkIndex + 1;
      if (nextIndex >= this.chunkCount) return null;
      return this._groups.has(nextIndex) ? null : nextIndex;
    }

    _dropChunk(index) {
      const chunk = this._chunks.get(index);
      if (!chunk) return;
      this._chunks.delete(index);
      this._decodedBytes -= chunk.decodedBytes;
    }

    _dropChunksOutside(firstIndex, secondIndex) {
      for (const index of Array.from(this._chunks.keys())) {
        if (index !== firstIndex && index !== secondIndex) {
          this._dropChunk(index);
        }
      }
    }

    _refreshStoppedAvailability() {
      const requiredIndex = this._chunkIndexForFrame(this._storedFrame);
      this._ended = requiredIndex === null;
      this._buffering =
        requiredIndex !== null && !this._chunks.has(requiredIndex);
      return requiredIndex;
    }

    _finishAtBoundary(chunk, now) {
      this._sequenceSerial += 1;
      const sources = [];
      for (const group of this._groups.values()) {
        sources.push(...group.sources);
      }
      sources.push(...this._retiringSources.map((item) => item.source));
      this._groups.clear();
      this._retiringSources = [];
      cancelSources(sources, now);

      const endFrame = chunk.startFrame + chunk.frameCount;
      this._dropChunk(chunk.index);
      this._storedFrame = endFrame;
      this._anchorFrame = endFrame;
      this._anchorContextTime = now;
      this._currentChunkIndex = null;
      this._playing = false;
      const neededIndex = this._chunkIndexForFrame(endFrame);
      this._dropChunksOutside(neededIndex, null);
      this._refreshStoppedAvailability();
    }

    _refreshClockState() {
      if (!this._playing || this._currentChunkIndex === null) return;
      const now = finiteNumber(
        this.audioContext.currentTime,
        "audio context current time"
      );
      this._retiringSources = this._retiringSources.filter(
        (item) => item.when > now
      );

      // A browser can deliver onended after its logical boundary. Advance from
      // the immutable anchor and integer chunk frames so UI state never claims
      // that a late successor began on time.
      while (this._playing && this._currentChunkIndex !== null) {
        const chunk = this._chunks.get(this._currentChunkIndex);
        if (!chunk) {
          throw new Error("active decoded chunk is unavailable");
        }
        const boundary = this._boundaryContextTime(chunk);
        if (now < boundary) return;
        const nextIndex = chunk.index + 1;
        const nextGroup = this._groups.get(nextIndex);
        if (
          nextGroup &&
          nextGroup.sequenceSerial === this._sequenceSerial
        ) {
          const oldGroup = this._groups.get(chunk.index);
          if (oldGroup) {
            for (const source of oldGroup.sources) safeDisconnect(source);
          }
          this._groups.delete(chunk.index);
          this._dropChunk(chunk.index);
          this._currentChunkIndex = nextIndex;
          this._storedFrame = nextGroup.chunk.startFrame;
          continue;
        }
        this._finishAtBoundary(chunk, now);
      }
    }

    _validateChunk(rawChunk) {
      if (!rawChunk || typeof rawChunk !== "object" || Array.isArray(rawChunk)) {
        throw new TypeError("decoded chunk must be an object");
      }
      if (sha256(rawChunk.streamHash, "chunk stream hash") !== this.streamHash) {
        throw new RangeError("chunk stream hash does not match this transport");
      }
      if (
        nonEmptyString(rawChunk.presetId, "chunk preset ID") !== this.presetId
      ) {
        throw new RangeError("chunk preset ID does not match this transport");
      }
      if (!sameRoster(this.roster, rawChunk.roster)) {
        throw new RangeError("chunk roster does not match this transport");
      }
      if (
        positiveInteger(rawChunk.totalFrameCount, "chunk total frame count") !==
        this.totalFrameCount
      ) {
        throw new RangeError("chunk total frame count does not match the sequence");
      }
      if (
        positiveInteger(rawChunk.chunkFrameCount, "chunk frame count policy") !==
        this.chunkFrameCount
      ) {
        throw new RangeError("chunk frame count policy does not match the sequence");
      }
      const expected = this._expectedChunk(rawChunk.chunkIndex);
      if (
        nonNegativeInteger(rawChunk.startFrame, "chunk start frame") !==
        expected.startFrame
      ) {
        throw new RangeError("chunk start frame is not integer-derived from its index");
      }
      if (
        positiveInteger(rawChunk.frameCount, "chunk decoded frame count") !==
        expected.frameCount
      ) {
        throw new RangeError("chunk decoded frame count does not match its extent");
      }

      const entries = bufferEntries(rawChunk.decodedBuffers);
      const supplied = new Map();
      for (const [rawKey, buffer] of entries) {
        const key = String(rawKey);
        if (supplied.has(key)) {
          throw new RangeError(`decoded buffer key is duplicated: ${key}`);
        }
        supplied.set(key, buffer);
      }
      if (
        supplied.size !== this.roster.length ||
        this.roster.some((key) => !supplied.has(key))
      ) {
        throw new RangeError("decoded chunk buffers must exactly match the roster");
      }

      let decodedBytes = 0;
      const ordered = new Map();
      for (const key of this.roster) {
        const buffer = supplied.get(key);
        validateDecodedBuffer(buffer, this.audioContext.sampleRate, key);
        if (buffer.length !== expected.frameCount) {
          throw new RangeError(
            `decoded buffer ${key} frame count must match the chunk frame count`
          );
        }
        decodedBytes += decodedBufferBytes(buffer);
        if (!Number.isSafeInteger(decodedBytes)) {
          throw new RangeError("decoded chunk byte size exceeds the safe integer range");
        }
        ordered.set(key, buffer);
      }
      return { expected, ordered, decodedBytes };
    }

    _requiredAppendIndex() {
      const baseIndex = this._playing
        ? this._currentChunkIndex
        : this._chunkIndexForFrame(this._storedFrame);
      if (baseIndex === null) return null;
      if (!this._chunks.has(baseIndex)) return baseIndex;
      const nextIndex = baseIndex + 1;
      return nextIndex < this.chunkCount && !this._chunks.has(nextIndex)
        ? nextIndex
        : null;
    }

    _handleSourceEnded(group, source) {
      safeDisconnect(source);
      if (
        group.sequenceSerial !== this._sequenceSerial ||
        this._groups.get(group.chunk.index) !== group
      ) {
        return;
      }
      group.endedSources.add(source);
      if (group.endedSources.size < group.sources.length) return;
      this._refreshClockState();
    }

    _buildScheduledGroup(chunk, when, offsetFrames, sequenceSerial) {
      const sources = [];
      const group = {
        chunk,
        endedSources: new Set(),
        offsetFrames,
        sequenceSerial,
        sources,
        when,
      };
      try {
        for (const key of this.roster) {
          const source = this.audioContext.createBufferSource();
          source.buffer = chunk.buffers.get(key);
          source.loop = false;
          source.connect(this.audioContext.destination);
          source.onended = () => this._handleSourceEnded(group, source);
          sources.push(source);
          this._sourceSerial += 1;
        }
        const offsetSeconds = offsetFrames / this.audioContext.sampleRate;
        for (const source of sources) source.start(when, offsetSeconds);
      } catch (error) {
        cancelSources(sources, when);
        throw error;
      }
      return group;
    }

    _retireGroups(groups, when) {
      for (const group of groups.values()) {
        for (const source of group.sources) {
          this._retiringSources.push({ source, when });
          try {
            retireSource(source, when);
          } catch (_) {
            safeDisconnect(source);
          }
        }
      }
    }

    _scheduleFromFrame(frame) {
      const chunkIndex = this._chunkIndexForFrame(frame);
      const chunk = chunkIndex === null ? null : this._chunks.get(chunkIndex);
      if (!chunk) {
        this._buffering = chunkIndex !== null;
        this._ended = chunkIndex === null;
        return null;
      }

      const now = finiteNumber(
        this.audioContext.currentTime,
        "audio context current time"
      );
      const when = now + this.scheduleLeadSeconds;
      const nextSerial = this._sequenceSerial + 1;
      const replacements = new Map();
      try {
        const currentGroup = this._buildScheduledGroup(
          chunk,
          when,
          frame - chunk.startFrame,
          nextSerial
        );
        replacements.set(chunk.index, currentGroup);
        const nextChunk = this._chunks.get(chunk.index + 1);
        if (nextChunk) {
          const nextWhen =
            when +
            (nextChunk.startFrame - frame) / this.audioContext.sampleRate;
          replacements.set(
            nextChunk.index,
            this._buildScheduledGroup(nextChunk, nextWhen, 0, nextSerial)
          );
        }
      } catch (error) {
        const replacementSources = [];
        for (const group of replacements.values()) {
          replacementSources.push(...group.sources);
        }
        cancelSources(replacementSources, now);
        throw error;
      }

      const previousGroups = this._groups;
      this._sequenceSerial = nextSerial;
      this._groups = replacements;
      this._currentChunkIndex = chunk.index;
      this._storedFrame = frame;
      this._anchorFrame = frame;
      this._anchorContextTime = when;
      this._playing = true;
      this._buffering = false;
      this._ended = false;
      this._dropChunksOutside(chunk.index, chunk.index + 1);
      this._retireGroups(previousGroups, when);

      return {
        chunkIndex: chunk.index,
        when,
        offsetFrame: frame - chunk.startFrame,
        scheduledChunkIndices: Array.from(replacements.keys()),
        sequenceSerial: this._sequenceSerial,
      };
    }

    _scheduleNextIfTimely(chunk) {
      if (
        !this._playing ||
        this._currentChunkIndex === null ||
        chunk.index !== this._currentChunkIndex + 1 ||
        this._groups.has(chunk.index)
      ) {
        return false;
      }
      const when =
        this._anchorContextTime +
        (chunk.startFrame - this._anchorFrame) /
          this.audioContext.sampleRate;
      const now = finiteNumber(
        this.audioContext.currentTime,
        "audio context current time"
      );
      if (when <= now) return false;
      const group = this._buildScheduledGroup(
        chunk,
        when,
        0,
        this._sequenceSerial
      );
      this._groups.set(chunk.index, group);
      return true;
    }

    appendChunk(rawChunk) {
      this._refreshClockState();
      const validated = this._validateChunk(rawChunk);
      const index = validated.expected.index;
      if (this._chunks.has(index)) {
        throw new RangeError(`decoded chunk is already retained: ${index}`);
      }
      const requiredIndex = this._requiredAppendIndex();
      if (requiredIndex === null || index !== requiredIndex) {
        throw new RangeError(
          `decoded chunk must be contiguous; needed index is ${requiredIndex}`
        );
      }
      if (this._chunks.size >= 2) {
        throw new RangeError("only the current and next chunks may be retained");
      }
      const projectedBytes = this._decodedBytes + validated.decodedBytes;
      if (
        !Number.isSafeInteger(projectedBytes) ||
        projectedBytes > this.maxDecodedBytes
      ) {
        throw new RangeError("decoded chunk would exceed the memory cap");
      }

      const buffers = normaliseDecodedBuffers(
        this.audioContext,
        validated.ordered,
        validated.expected.frameCount
      );
      const chunk = Object.freeze({
        buffers,
        decodedBytes: validated.decodedBytes,
        frameCount: validated.expected.frameCount,
        index,
        startFrame: validated.expected.startFrame,
      });
      this._chunks.set(index, chunk);
      this._decodedBytes = projectedBytes;
      if (!this._playing && index === this._chunkIndexForFrame(this._storedFrame)) {
        this._buffering = false;
      }

      let scheduled = false;
      try {
        scheduled = this._scheduleNextIfTimely(chunk);
      } catch (error) {
        this._dropChunk(index);
        throw error;
      }
      return {
        chunkIndex: index,
        decodedBytes: chunk.decodedBytes,
        retainedChunkIndices: Array.from(this._chunks.keys()),
        scheduled,
      };
    }

    play() {
      this._refreshClockState();
      if (this._playing || this._ended) return this.snapshot();
      const scheduled = this._scheduleFromFrame(this._storedFrame);
      return scheduled || this.snapshot();
    }

    seekFrame(frame) {
      this._refreshClockState();
      const target = nonNegativeInteger(frame, "seek frame");
      if (target > this.totalFrameCount) {
        throw new RangeError("seek frame exceeds the sequence duration");
      }
      if (target === this.totalFrameCount) {
        this.pause();
        this._storedFrame = target;
        this._anchorFrame = target;
        this._ended = true;
        this._buffering = false;
        this._dropChunksOutside(null, null);
        return this.snapshot();
      }

      const targetIndex = this._chunkIndexForFrame(target);
      if (this._playing && this._chunks.has(targetIndex)) {
        return this._scheduleFromFrame(target);
      }
      if (this._playing) this.pause();
      this._storedFrame = target;
      this._anchorFrame = target;
      this._anchorContextTime = finiteNumber(
        this.audioContext.currentTime,
        "audio context current time"
      );
      this._ended = false;
      this._dropChunksOutside(targetIndex, targetIndex + 1);
      this._buffering = !this._chunks.has(targetIndex);
      return this.snapshot();
    }

    seek(playheadSeconds) {
      const seconds = finiteNumber(playheadSeconds, "seek time");
      if (seconds < 0 || seconds > this.durationSeconds) {
        throw new RangeError("seek time must be within the sequence duration");
      }
      return this.seekFrame(
        Math.min(
          this.totalFrameCount,
          Math.round(seconds * this.audioContext.sampleRate)
        )
      );
    }

    pause() {
      this._refreshClockState();
      const frame = this._playheadFrameWithoutRefresh();
      const now = finiteNumber(
        this.audioContext.currentTime,
        "audio context current time"
      );
      this._sequenceSerial += 1;
      const sources = [];
      for (const group of this._groups.values()) {
        sources.push(...group.sources);
      }
      sources.push(...this._retiringSources.map((item) => item.source));
      this._groups.clear();
      this._retiringSources = [];
      cancelSources(sources, now);
      this._storedFrame = frame;
      this._anchorFrame = frame;
      this._anchorContextTime = now;
      this._currentChunkIndex = null;
      this._playing = false;
      this._refreshStoppedAvailability();
      return frame;
    }

    stop() {
      this.pause();
      this._storedFrame = 0;
      this._anchorFrame = 0;
      this._ended = false;
      this._dropChunksOutside(0, 1);
      this._buffering = !this._chunks.has(0);
      return 0;
    }

    snapshot() {
      this._refreshClockState();
      const frame = this._playheadFrameWithoutRefresh();
      return {
        buffering: this._buffering,
        chunkCount: this.chunkCount,
        chunkFrameCount: this.chunkFrameCount,
        currentChunkIndex: this._currentChunkIndex,
        decodedBytes: this._decodedBytes,
        durationSeconds: this.durationSeconds,
        ended: this._ended,
        maxDecodedBytes: this.maxDecodedBytes,
        neededChunkIndex: this._neededChunkIndexWithoutRefresh(),
        playing: this._playing,
        playheadFrame: frame,
        playheadSeconds: frame / this.audioContext.sampleRate,
        presetId: this.presetId,
        retainedChunkIndices: Array.from(this._chunks.keys()),
        roster: this.roster.slice(),
        sampleRate: this.audioContext.sampleRate,
        scheduledChunkIndices: Array.from(this._groups.keys()),
        sequenceSerial: this._sequenceSerial,
        sourceSerial: this._sourceSerial,
        streamHash: this.streamHash,
        totalFrameCount: this.totalFrameCount,
      };
    }
  }

  return Object.freeze({
    DEFAULT_MAX_DECODED_SEQUENCE_BYTES,
    DEFAULT_SCHEDULE_LEAD_SECONDS,
    DecodedChunkSequenceTransport,
    DecodedGroupLoopTransport,
    DecodedLoopTransport,
    absolutePlayheadAt,
    frameCountForLoop,
    markDecodedBufferImmutable,
    normaliseDecodedBuffers,
    normalizeDecodedBuffers: normaliseDecodedBuffers,
    wrapAbsolutePlayhead,
  });
});
