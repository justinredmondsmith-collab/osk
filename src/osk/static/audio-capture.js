(function () {
  const DEFAULT_MIME_CANDIDATES = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/ogg",
    "audio/mp4",
  ];

  function preferredMimeType(candidates) {
    if (typeof MediaRecorder === "undefined") {
      return "";
    }
    for (const candidate of candidates) {
      if (!candidate) {
        continue;
      }
      if (typeof MediaRecorder.isTypeSupported !== "function") {
        return candidate;
      }
      if (MediaRecorder.isTypeSupported(candidate)) {
        return candidate;
      }
    }
    return "";
  }

  function generateId(prefix) {
    if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
      return `${prefix}-${globalThis.crypto.randomUUID()}`;
    }
    return `${prefix}-${Date.now()}-${Math.round(Math.random() * 1e9)}`;
  }

  function createAudioCapture(options = {}) {
    const onStateChange = options.onStateChange || (() => {});
    const onChunk = options.onChunk || (() => {});
    const onAck = options.onAck || (() => {});
    const onError = options.onError || (() => {});
    const sendJson = options.sendJson || (() => false);
    const sendBinary = options.sendBinary || (() => false);
    const getContext = options.getContext || (() => ({}));
    const chunkMs = Math.max(1000, Number(options.chunkMs || 4000));

    let stream = null;
    let recorder = null;
    let mimeType = "";
    let sampleRateHz = Number(options.sampleRateHz || 16000);
    let sequenceNo = 0;
    let chunkStartedAt = 0;
    let emittedChunks = 0;
    let lastChunkId = null;
    let lastAck = null;
    let error = null;
    let muted = false;
    let running = false;
    let acceptingChunks = false;

    function snapshot() {
      return {
        running,
        muted,
        mimeType,
        sampleRateHz,
        emittedChunks,
        lastChunkId,
        lastAck,
        error,
      };
    }

    function publishState() {
      onStateChange(snapshot());
    }

    function stopTracks() {
      if (!stream) {
        return;
      }
      for (const track of stream.getTracks()) {
        track.stop();
      }
      stream = null;
    }

    async function emitChunk(blob) {
      if (!acceptingChunks || !blob || !blob.size) {
        return;
      }
      const now = Date.now();
      const durationMs = Math.max(250, now - chunkStartedAt);
      chunkStartedAt = now;
      const context = getContext() || {};
      const chunkId = generateId("audio");
      const payload = {
        type: "audio_meta",
        chunk_id: chunkId,
        sequence_no: sequenceNo,
        duration_ms: durationMs,
        sample_rate_hz: sampleRateHz,
        codec: mimeType || blob.type || "audio/webm",
        captured_at: new Date(now).toISOString(),
      };
      if (context.memberId) {
        payload.ingest_key = `${context.memberId}:audio:${sequenceNo}`;
      }
      sequenceNo += 1;
      const metadataAccepted = await Promise.resolve(sendJson(payload));
      if (!metadataAccepted) {
        throw new Error("Audio metadata could not be sent.");
      }
      const payloadAccepted = await Promise.resolve(sendBinary(blob));
      if (!payloadAccepted) {
        throw new Error("Audio chunk could not be sent.");
      }
      emittedChunks += 1;
      lastChunkId = chunkId;
      onChunk({ ...payload, sizeBytes: blob.size });
      publishState();
    }

    function setMuted(nextMuted) {
      muted = Boolean(nextMuted);
      if (stream) {
        for (const track of stream.getAudioTracks()) {
          track.enabled = !muted;
        }
      }
      publishState();
    }

    async function start() {
      if (running) {
        return snapshot();
      }
      if (
        !navigator.mediaDevices ||
        typeof navigator.mediaDevices.getUserMedia !== "function" ||
        typeof MediaRecorder === "undefined"
      ) {
        error = "Audio capture is not supported in this browser.";
        publishState();
        throw new Error(error);
      }

      error = null;
      lastAck = null;
      mimeType = preferredMimeType(options.mimeTypeCandidates || DEFAULT_MIME_CANDIDATES);
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      const audioTrack = stream.getAudioTracks()[0] || null;
      const settings =
        audioTrack && typeof audioTrack.getSettings === "function" ? audioTrack.getSettings() : {};
      sampleRateHz = Number(settings.sampleRate || options.sampleRateHz || 48000);
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      chunkStartedAt = Date.now();
      acceptingChunks = true;

      recorder.addEventListener("dataavailable", (event) => {
        if (!acceptingChunks) {
          return;
        }
        void emitChunk(event.data).catch((captureError) => {
          error = captureError instanceof Error ? captureError.message : "Audio capture failed.";
          onError(error);
          publishState();
        });
      });

      recorder.addEventListener("stop", () => {
        running = false;
        acceptingChunks = false;
        recorder = null;
        stopTracks();
        publishState();
      });

      recorder.start(chunkMs);
      running = true;
      setMuted(false);
      publishState();
      return snapshot();
    }

    async function stop() {
      acceptingChunks = false;
      if (recorder && recorder.state !== "inactive") {
        recorder.stop();
      } else {
        running = false;
        recorder = null;
        stopTracks();
        publishState();
      }
      return snapshot();
    }

    function handleAck(ackPayload) {
      lastAck = ackPayload || null;
      onAck(ackPayload || null);
      publishState();
    }

    return {
      start,
      stop,
      mute() {
        setMuted(true);
        return snapshot();
      },
      unmute() {
        setMuted(false);
        return snapshot();
      },
      handleAck,
      snapshot,
    };
  }

  globalThis.OskAudioCapture = {
    createAudioCapture,
  };
})();
