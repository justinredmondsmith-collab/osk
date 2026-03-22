(function () {
  const DEFAULT_CONTENT_TYPE = "image/jpeg";

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
          reject(new Error("Frame encoding failed."));
          return;
        }
        resolve(blob);
      }, type, quality);
    });
  }

  function createFrameSampler(options = {}) {
    const onStateChange = options.onStateChange || (() => {});
    const onFrame = options.onFrame || (() => {});
    const onAck = options.onAck || (() => {});
    const onError = options.onError || (() => {});
    const sendJson = options.sendJson || (() => false);
    const sendBinary = options.sendBinary || (() => false);
    const getContext = options.getContext || (() => ({}));
    const previewElement = options.previewElement || null;
    const fps = Math.max(0.5, Number(options.fps || 2.0));
    const threshold = Math.max(0, Number(options.threshold || 0.15));
    const baselineIntervalSeconds = Math.max(
      5,
      Number(options.baselineIntervalSeconds || 30),
    );
    const jpegQuality = Math.min(0.92, Math.max(0.3, Number(options.jpegQuality || 0.68)));
    const targetWidth = Math.max(320, Number(options.targetWidth || 960));
    const targetHeight = Math.max(240, Number(options.targetHeight || 540));
    const samplingIntervalMs = Math.max(250, Math.round(1000 / fps));
    const workerUrl = options.workerUrl || "/static/sampling-worker.js";

    let stream = null;
    let videoElement = null;
    let canvas = null;
    let context2d = null;
    let worker = null;
    let running = false;
    let timerId = null;
    let awaitingWorker = false;
    let emittedFrames = 0;
    let analyzedFrames = 0;
    let lastAck = null;
    let lastScore = 0;
    let lastSentAt = 0;
    let error = null;
    let sequenceNo = 0;
    let pendingFrame = null;

    function snapshot() {
      return {
        running,
        emittedFrames,
        analyzedFrames,
        lastAck,
        lastScore,
        error,
        previewActive: Boolean(stream),
      };
    }

    function publishState() {
      onStateChange(snapshot());
    }

    function clearPreview() {
      if (previewElement) {
        previewElement.srcObject = null;
        previewElement.hidden = true;
      }
      if (videoElement && videoElement !== previewElement) {
        videoElement.srcObject = null;
      }
    }

    function stopTracks() {
      if (!stream) {
        return;
      }
      for (const track of stream.getTracks()) {
        track.stop();
      }
      stream = null;
      clearPreview();
    }

    async function emitFrame(capturedAt, score) {
      if (!canvas) {
        return;
      }
      const blob = await canvasToBlob(canvas, DEFAULT_CONTENT_TYPE, jpegQuality);
      const context = getContext() || {};
      const frameId = generateId("frame");
      const payload = {
        type: "frame_meta",
        frame_id: frameId,
        sequence_no: sequenceNo,
        content_type: blob.type || DEFAULT_CONTENT_TYPE,
        width: canvas.width,
        height: canvas.height,
        change_score: score,
        captured_at: new Date(capturedAt).toISOString(),
      };
      if (context.memberId) {
        payload.ingest_key = `${context.memberId}:frame:${sequenceNo}`;
      }
      sequenceNo += 1;
      const metadataAccepted = await Promise.resolve(sendJson(payload));
      if (!metadataAccepted) {
        throw new Error("Frame metadata could not be sent.");
      }
      const payloadAccepted = await Promise.resolve(sendBinary(blob));
      if (!payloadAccepted) {
        throw new Error("Frame payload could not be sent.");
      }
      emittedFrames += 1;
      lastSentAt = capturedAt;
      onFrame({ ...payload, sizeBytes: blob.size });
      publishState();
    }

    function ensureWorker() {
      if (worker || typeof Worker === "undefined") {
        return;
      }
      worker = new Worker(workerUrl);
      worker.addEventListener("message", (event) => {
        awaitingWorker = false;
        const payload = event.data || {};
        if (payload.type !== "frame_score" || !pendingFrame) {
          return;
        }
        analyzedFrames += 1;
        lastScore = Number(payload.score || 0);
        const baselineDue =
          !lastSentAt || pendingFrame.capturedAt - lastSentAt >= baselineIntervalSeconds * 1000;
        const shouldSend = Boolean(payload.changed || baselineDue);
        const nextFrame = pendingFrame;
        pendingFrame = null;
        if (!shouldSend) {
          publishState();
          return;
        }
        void emitFrame(nextFrame.capturedAt, lastScore).catch((captureError) => {
          error = captureError instanceof Error ? captureError.message : "Frame capture failed.";
          onError(error);
          publishState();
        });
      });
      worker.addEventListener("error", () => {
        awaitingWorker = false;
        error = "Frame analysis worker failed.";
        onError(error);
        publishState();
      });
    }

    async function analyzeCurrentFrame() {
      if (!running || awaitingWorker || !videoElement || !canvas || !context2d) {
        return;
      }
      if (videoElement.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
        return;
      }
      const width = videoElement.videoWidth || targetWidth;
      const height = videoElement.videoHeight || targetHeight;
      if (!width || !height) {
        return;
      }
      canvas.width = width;
      canvas.height = height;
      context2d.drawImage(videoElement, 0, 0, width, height);
      const capturedAt = Date.now();

      if (!worker) {
        const baselineDue =
          !lastSentAt || capturedAt - lastSentAt >= baselineIntervalSeconds * 1000;
        analyzedFrames += 1;
        lastScore = baselineDue ? 1 : 0;
        if (baselineDue) {
          try {
            await emitFrame(capturedAt, lastScore);
          } catch (captureError) {
            error =
              captureError instanceof Error ? captureError.message : "Frame capture failed.";
            onError(error);
          }
        }
        publishState();
        return;
      }

      const imageData = context2d.getImageData(0, 0, width, height);
      awaitingWorker = true;
      pendingFrame = { capturedAt };
      worker.postMessage(
        {
          type: "compare",
          threshold,
          width,
          height,
          pixels: imageData.data.buffer,
        },
        [imageData.data.buffer],
      );
    }

    async function start() {
      if (running) {
        return snapshot();
      }
      if (
        !navigator.mediaDevices ||
        typeof navigator.mediaDevices.getUserMedia !== "function"
      ) {
        error = "Camera capture is not supported in this browser.";
        publishState();
        throw new Error(error);
      }

      error = null;
      lastAck = null;
      ensureWorker();
      canvas = document.createElement("canvas");
      context2d = canvas.getContext("2d", { willReadFrequently: true });
      videoElement = previewElement || document.createElement("video");
      videoElement.autoplay = true;
      videoElement.muted = true;
      videoElement.playsInline = true;

      stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: targetWidth },
          height: { ideal: targetHeight },
        },
        audio: false,
      });
      videoElement.srcObject = stream;
      if (previewElement) {
        previewElement.hidden = false;
      }
      await videoElement.play();

      running = true;
      timerId = window.setInterval(() => {
        void analyzeCurrentFrame();
      }, samplingIntervalMs);
      publishState();
      return snapshot();
    }

    async function stop() {
      running = false;
      awaitingWorker = false;
      pendingFrame = null;
      if (timerId !== null) {
        window.clearInterval(timerId);
        timerId = null;
      }
      stopTracks();
      if (worker) {
        worker.terminate();
        worker = null;
      }
      publishState();
      return snapshot();
    }

    function handleAck(ackPayload) {
      lastAck = ackPayload || null;
      onAck(ackPayload || null);
      publishState();
    }

    function destroy() {
      void stop();
      canvas = null;
      context2d = null;
      videoElement = null;
    }

    return {
      start,
      stop,
      destroy,
      handleAck,
      snapshot,
    };
  }

  globalThis.OskFrameSampler = {
    createFrameSampler,
  };
})();
