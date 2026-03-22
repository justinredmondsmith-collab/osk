(function () {
  const DEFAULT_AUDIO_MIME_CANDIDATES = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/ogg",
    "audio/mp4",
  ];
  const DEFAULT_FRAME_CONTENT_TYPE = "image/jpeg";

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

  function canvasToBlob(canvas, type, quality) {
    return new Promise((resolve, reject) => {
      canvas.toBlob((blob) => {
        if (!blob) {
          reject(new Error("Manual photo encoding failed."));
          return;
        }
        resolve(blob);
      }, type, quality);
    });
  }

  function wait(ms) {
    return new Promise((resolve) => {
      window.setTimeout(resolve, ms);
    });
  }

  function createObserverMediaCapture(options = {}) {
    const onStateChange = options.onStateChange || (() => {});
    const onError = options.onError || (() => {});
    const sendJson = options.sendJson || (() => false);
    const sendBinary = options.sendBinary || (() => false);
    const getContext = options.getContext || (() => ({}));
    const clipDurationSeconds = Math.max(4, Number(options.clipDurationSeconds || 10));
    const clipCooldownSeconds = Math.max(0, Number(options.clipCooldownSeconds || 20));
    const photoQuality = Math.min(0.92, Math.max(0.4, Number(options.photoQuality || 0.78)));
    const targetWidth = Math.max(320, Number(options.targetWidth || 1280));
    const targetHeight = Math.max(240, Number(options.targetHeight || 720));

    let photoCapturing = false;
    let photoError = null;
    let lastPhotoAck = null;
    let lastPhotoId = null;
    let lastPhotoAt = null;

    let clipStream = null;
    let clipRecorder = null;
    let clipMimeType = "";
    let clipRecording = false;
    let clipError = null;
    let lastClipAck = null;
    let lastClipId = null;
    let lastClipAt = null;
    let lastClipDurationMs = 0;
    let clipCaptureId = null;
    let clipChunks = [];
    let clipStartedAt = 0;
    let clipStopTimerId = null;
    let clipCooldownEndsAt = 0;
    let cooldownTimerId = null;

    function cooldownRemainingMs() {
      if (!clipCooldownEndsAt) {
        return 0;
      }
      return Math.max(0, clipCooldownEndsAt - Date.now());
    }

    function snapshot() {
      return {
        photo: {
          capturing: photoCapturing,
          error: photoError,
          lastAck: lastPhotoAck,
          lastCaptureId: lastPhotoId,
          lastCapturedAt: lastPhotoAt,
        },
        clip: {
          recording: clipRecording,
          error: clipError,
          mimeType: clipMimeType,
          lastAck: lastClipAck,
          lastCaptureId: lastClipId,
          lastCapturedAt: lastClipAt,
          lastDurationMs: lastClipDurationMs,
          cooldownRemainingMs: cooldownRemainingMs(),
        },
      };
    }

    function publishState() {
      onStateChange(snapshot());
    }

    function setError(kind, message) {
      if (kind === "photo") {
        photoError = message;
      } else {
        clipError = message;
      }
      onError(message);
      publishState();
    }

    function stopClipTracks() {
      if (!clipStream) {
        return;
      }
      for (const track of clipStream.getTracks()) {
        track.stop();
      }
      clipStream = null;
    }

    function stopCooldownTicker() {
      if (cooldownTimerId !== null) {
        window.clearInterval(cooldownTimerId);
        cooldownTimerId = null;
      }
    }

    function startCooldown() {
      stopCooldownTicker();
      if (!clipCooldownSeconds) {
        clipCooldownEndsAt = 0;
        publishState();
        return;
      }
      clipCooldownEndsAt = Date.now() + clipCooldownSeconds * 1000;
      cooldownTimerId = window.setInterval(() => {
        if (!cooldownRemainingMs()) {
          stopCooldownTicker();
          clipCooldownEndsAt = 0;
        }
        publishState();
      }, 1000);
      publishState();
    }

    async function capturePhoto() {
      if (photoCapturing) {
        return snapshot();
      }
      if (
        !navigator.mediaDevices ||
        typeof navigator.mediaDevices.getUserMedia !== "function"
      ) {
        const message = "Photo capture is not supported in this browser.";
        setError("photo", message);
        throw new Error(message);
      }

      photoCapturing = true;
      photoError = null;
      lastPhotoAck = null;
      publishState();

      let stream = null;
      let video = null;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: { ideal: "environment" },
            width: { ideal: targetWidth },
            height: { ideal: targetHeight },
          },
          audio: false,
        });
        video = document.createElement("video");
        video.autoplay = true;
        video.muted = true;
        video.playsInline = true;
        video.srcObject = stream;
        await video.play();
        await wait(220);

        const width = video.videoWidth || targetWidth;
        const height = video.videoHeight || targetHeight;
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const context2d = canvas.getContext("2d");
        if (!context2d) {
          throw new Error("Photo capture canvas is unavailable.");
        }
        context2d.drawImage(video, 0, 0, width, height);
        const blob = await canvasToBlob(canvas, DEFAULT_FRAME_CONTENT_TYPE, photoQuality);
        const capturedAt = new Date().toISOString();
        const captureId = generateId("observer-photo");
        const context = getContext() || {};
        const ingestKey = context.memberId
          ? `${context.memberId}:observer-photo:${captureId}`
          : `observer-photo:${captureId}`;
        const payload = {
          type: "frame_meta",
          frame_id: captureId,
          ingest_key: ingestKey,
          sequence_no: 0,
          content_type: blob.type || DEFAULT_FRAME_CONTENT_TYPE,
          width,
          height,
          change_score: 1.0,
          captured_at: capturedAt,
          manual_capture: true,
        };
        if (!sendJson(payload)) {
          throw new Error("Photo metadata could not be sent.");
        }
        if (!sendBinary(blob)) {
          throw new Error("Photo payload could not be sent.");
        }
        lastPhotoId = captureId;
        lastPhotoAt = capturedAt;
        publishState();
        return snapshot();
      } catch (error) {
        const message = error instanceof Error ? error.message : "Photo capture failed.";
        setError("photo", message);
        throw error;
      } finally {
        photoCapturing = false;
        if (video) {
          video.srcObject = null;
        }
        if (stream) {
          for (const track of stream.getTracks()) {
            track.stop();
          }
        }
        publishState();
      }
    }

    async function emitClip(captureId) {
      const blob = new Blob(clipChunks, {
        type: clipMimeType || clipChunks[0]?.type || "audio/webm",
      });
      clipChunks = [];
      if (!blob.size || !captureId) {
        return;
      }
      const capturedAt = new Date().toISOString();
      const context = getContext() || {};
      const ingestKey = context.memberId
        ? `${context.memberId}:observer-clip:${captureId}`
        : `observer-clip:${captureId}`;
      const payload = {
        type: "audio_meta",
        chunk_id: captureId,
        ingest_key: ingestKey,
        sequence_no: 0,
        duration_ms: lastClipDurationMs,
        sample_rate_hz: Number(options.sampleRateHz || 16000),
        codec: blob.type || clipMimeType || "audio/webm",
        captured_at: capturedAt,
        manual_capture: true,
      };
      if (!sendJson(payload)) {
        throw new Error("Audio clip metadata could not be sent.");
      }
      if (!sendBinary(blob)) {
        throw new Error("Audio clip payload could not be sent.");
      }
      lastClipId = captureId;
      lastClipAt = capturedAt;
      publishState();
    }

    async function startClip() {
      if (clipRecording) {
        return snapshot();
      }
      if (cooldownRemainingMs()) {
        const message = "Audio clip capture is cooling down.";
        setError("clip", message);
        throw new Error(message);
      }
      if (
        !navigator.mediaDevices ||
        typeof navigator.mediaDevices.getUserMedia !== "function" ||
        typeof MediaRecorder === "undefined"
      ) {
        const message = "Audio clip capture is not supported in this browser.";
        setError("clip", message);
        throw new Error(message);
      }

      clipError = null;
      lastClipAck = null;
      clipMimeType = preferredMimeType(options.mimeTypeCandidates || DEFAULT_AUDIO_MIME_CANDIDATES);

      let stream = null;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        });
        const recorder = new MediaRecorder(
          stream,
          clipMimeType ? { mimeType: clipMimeType } : undefined,
        );

        clipStream = stream;
        clipRecorder = recorder;
        clipChunks = [];
        clipCaptureId = generateId("observer-clip");
        clipStartedAt = Date.now();
        clipRecording = true;

        recorder.addEventListener("dataavailable", (event) => {
          if (event.data && event.data.size) {
            clipChunks.push(event.data);
          }
        });

        recorder.addEventListener("stop", () => {
          if (clipStopTimerId !== null) {
            window.clearTimeout(clipStopTimerId);
            clipStopTimerId = null;
          }
          const captureId = clipCaptureId;
          lastClipDurationMs = Math.max(750, Date.now() - clipStartedAt);
          clipRecording = false;
          clipRecorder = null;
          clipCaptureId = null;
          clipStartedAt = 0;
          stopClipTracks();
          void emitClip(captureId)
            .catch((error) => {
              const message = error instanceof Error ? error.message : "Audio clip capture failed.";
              setError("clip", message);
            })
            .finally(() => {
              startCooldown();
              publishState();
            });
        });

        recorder.start();
        clipStopTimerId = window.setTimeout(() => {
          void stopClip();
        }, clipDurationSeconds * 1000);
        publishState();
        return snapshot();
      } catch (error) {
        if (clipStopTimerId !== null) {
          window.clearTimeout(clipStopTimerId);
          clipStopTimerId = null;
        }
        clipRecording = false;
        clipRecorder = null;
        clipCaptureId = null;
        clipStartedAt = 0;
        clipChunks = [];
        if (stream) {
          for (const track of stream.getTracks()) {
            track.stop();
          }
        }
        stopClipTracks();
        const message =
          error instanceof Error ? error.message : "Audio clip capture could not start.";
        setError("clip", message);
        throw error;
      }
    }

    async function stopClip() {
      if (!clipRecording || !clipRecorder) {
        return snapshot();
      }
      if (clipStopTimerId !== null) {
        window.clearTimeout(clipStopTimerId);
        clipStopTimerId = null;
      }
      clipRecorder.stop();
      clipRecorder = null;
      publishState();
      return snapshot();
    }

    function handleAck(kind, ackPayload) {
      if (kind === "photo") {
        lastPhotoAck = ackPayload || null;
      } else if (kind === "clip") {
        lastClipAck = ackPayload || null;
      }
      publishState();
    }

    async function destroy() {
      stopCooldownTicker();
      if (clipRecording) {
        await stopClip();
      }
      stopClipTracks();
      publishState();
    }

    return {
      capturePhoto,
      startClip,
      stopClip,
      handleAck,
      destroy,
      snapshot,
    };
  }

  globalThis.OskObserverMedia = {
    createObserverMediaCapture,
  };
})();
