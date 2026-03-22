(function () {
  const bootstrapNode = document.getElementById("osk-member-bootstrap");
  if (!bootstrapNode) {
    return;
  }

  const bootstrap = JSON.parse(bootstrapNode.textContent || "{}");
  const runtimeConfig = bootstrap.runtime || {};
  const reconnectConfig = {
    baseDelayMs: Math.max(750, Number(runtimeConfig.reconnect_base_delay_ms || 1500)),
    maxDelayMs: Math.max(2500, Number(runtimeConfig.reconnect_max_delay_ms || 10000)),
  };
  const gpsConfig = {
    movingIntervalMs: Math.max(
      1000,
      Number(runtimeConfig.gps_interval_moving_seconds || 10) * 1000,
    ),
    stationaryIntervalMs: Math.max(
      5000,
      Number(runtimeConfig.gps_interval_stationary_seconds || 60) * 1000,
    ),
    significantChangeMeters: Math.max(
      5,
      Number(runtimeConfig.gps_significant_change_meters || 15),
    ),
  };
  const sensorConfig = {
    audioChunkMs: Math.max(1000, Number(runtimeConfig.audio_chunk_ms || 4000)),
    frameSamplingFps: Math.max(0.5, Number(runtimeConfig.frame_sampling_fps || 2)),
    frameChangeThreshold: Math.max(0, Number(runtimeConfig.frame_change_threshold || 0.15)),
    frameBaselineIntervalSeconds: Math.max(
      5,
      Number(runtimeConfig.frame_baseline_interval_seconds || 30),
    ),
    frameJpegQuality: Math.min(0.92, Math.max(0.3, Number(runtimeConfig.frame_jpeg_quality || 0.68))),
    videoWidth: Math.max(320, Number(runtimeConfig.sensor_video_width || 960)),
    videoHeight: Math.max(240, Number(runtimeConfig.sensor_video_height || 540)),
  };
  const observerConfig = {
    clipDurationSeconds: Math.max(
      4,
      Number(runtimeConfig.observer_clip_duration_seconds || 10),
    ),
    clipCooldownSeconds: Math.max(
      0,
      Number(runtimeConfig.observer_clip_cooldown_seconds || 20),
    ),
    photoQuality: Math.min(
      0.92,
      Math.max(0.4, Number(runtimeConfig.observer_photo_quality || 0.78)),
    ),
  };
  const manualReportMaxLength = Math.max(
    80,
    Number(runtimeConfig.manual_report_max_length || 280),
  );

  const storageKeys = {
    memberId: "osk_member_id",
    memberName: "osk_member_name",
    operationName: "osk_operation_name",
    gpsEnabled: "osk_member_gps_enabled",
    sensorEnabled: "osk_member_sensor_enabled",
    audioMuted: "osk_member_audio_muted",
  };

  const state = {
    socket: null,
    session: null,
    authenticated: false,
    feed: [],
    alerts: [],
    reconnectAttempt: 0,
    reconnectTimer: null,
    intentionallyLeaving: false,
    endingOperation: false,
    manualReportPending: false,
    gps: {
      active: false,
      watchId: null,
      lastFixAt: null,
      lastPosition: null,
      lastSentAt: null,
      lastSentPosition: null,
      error: null,
    },
    sensor: {
      role: "observer",
      starting: false,
      audioCapture: null,
      frameSampler: null,
      audio: null,
      frame: null,
    },
    observer: {
      mediaCapture: null,
      snapshot: null,
    },
  };

  const elements = {
    joinOperationName: document.getElementById("join-operation-name"),
    joinSessionStatus: document.getElementById("join-session-status"),
    joinForm: document.getElementById("join-form"),
    joinDisplayName: document.getElementById("join-display-name"),
    joinEmpty: document.getElementById("join-empty"),
    joinReset: document.getElementById("join-reset"),
    runtimeOperationName: document.getElementById("runtime-operation-name"),
    runtimeConnectionDot: document.getElementById("runtime-connection-dot"),
    runtimeConnectionLabel: document.getElementById("runtime-connection-label"),
    runtimeConnectionState: document.getElementById("runtime-connection-state"),
    runtimeDisplayName: document.getElementById("runtime-display-name"),
    runtimeRole: document.getElementById("runtime-role"),
    runtimeMemberId: document.getElementById("runtime-member-id"),
    runtimeSessionState: document.getElementById("runtime-session-state"),
    runtimeLastReport: document.getElementById("runtime-last-report"),
    runtimeFeed: document.getElementById("runtime-feed"),
    runtimeLeave: document.getElementById("runtime-leave"),
    runtimeAlerts: document.getElementById("runtime-alerts"),
    runtimeAlertCount: document.getElementById("runtime-alert-count"),
    runtimeAlertSummary: document.getElementById("runtime-alert-summary"),
    runtimeGpsState: document.getElementById("runtime-gps-state"),
    runtimeGpsDetail: document.getElementById("runtime-gps-detail"),
    runtimeGpsToggle: document.getElementById("runtime-gps-toggle"),
    runtimeReportForm: document.getElementById("runtime-report-form"),
    runtimeReportText: document.getElementById("runtime-report-text"),
    runtimeReportStatus: document.getElementById("runtime-report-status"),
    runtimeReportSend: document.getElementById("runtime-report-send"),
    runtimeSensorSignal: document.getElementById("runtime-sensor-signal"),
    runtimeSensorState: document.getElementById("runtime-sensor-state"),
    runtimeSensorDetail: document.getElementById("runtime-sensor-detail"),
    runtimeSensorPanel: document.getElementById("runtime-sensor-panel"),
    runtimeSensorSummary: document.getElementById("runtime-sensor-summary"),
    runtimeAudioState: document.getElementById("runtime-audio-state"),
    runtimeAudioDetail: document.getElementById("runtime-audio-detail"),
    runtimeFrameState: document.getElementById("runtime-frame-state"),
    runtimeFrameDetail: document.getElementById("runtime-frame-detail"),
    runtimeSensorPreview: document.getElementById("runtime-sensor-preview"),
    runtimeSensorPreviewCopy: document.getElementById("runtime-sensor-preview-copy"),
    runtimeSensorToggle: document.getElementById("runtime-sensor-toggle"),
    runtimeAudioToggle: document.getElementById("runtime-audio-toggle"),
    runtimeObserverPanel: document.getElementById("runtime-observer-panel"),
    runtimeObserverSummary: document.getElementById("runtime-observer-summary"),
    runtimePhotoState: document.getElementById("runtime-photo-state"),
    runtimePhotoDetail: document.getElementById("runtime-photo-detail"),
    runtimeClipState: document.getElementById("runtime-clip-state"),
    runtimeClipDetail: document.getElementById("runtime-clip-detail"),
    runtimePhotoCapture: document.getElementById("runtime-photo-capture"),
    runtimeClipToggle: document.getElementById("runtime-clip-toggle"),
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function normalizeWhitespace(value) {
    return String(value ?? "").replace(/\s+/g, " ").trim();
  }

  function isSensorRole(role) {
    return String(role || "").toLowerCase() === "sensor";
  }

  async function fetchJson(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      cache: "no-store",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
    let payload = {};
    try {
      payload = await response.json();
    } catch (error) {
      payload = {};
    }
    if (!response.ok) {
      const failure = new Error(payload.error || `${response.status} ${response.statusText}`);
      failure.status = response.status;
      throw failure;
    }
    return payload;
  }

  function readStoredName() {
    return String(sessionStorage.getItem(storageKeys.memberName) || "").trim();
  }

  function readStoredOperationName() {
    return String(sessionStorage.getItem(storageKeys.operationName) || "").trim();
  }

  function rememberOperationName(value) {
    const operationName = normalizeWhitespace(value);
    if (!operationName) {
      return;
    }
    sessionStorage.setItem(storageKeys.operationName, operationName);
  }

  function shouldAutoRestartGps() {
    return sessionStorage.getItem(storageKeys.gpsEnabled) === "1";
  }

  function setGpsPreference(enabled) {
    if (enabled) {
      sessionStorage.setItem(storageKeys.gpsEnabled, "1");
    } else {
      sessionStorage.removeItem(storageKeys.gpsEnabled);
    }
  }

  function setSensorPreference(enabled) {
    if (enabled) {
      sessionStorage.setItem(storageKeys.sensorEnabled, "1");
    } else {
      sessionStorage.setItem(storageKeys.sensorEnabled, "0");
    }
  }

  function shouldAutoStartSensorCapture() {
    const stored = sessionStorage.getItem(storageKeys.sensorEnabled);
    return stored === null ? true : stored === "1";
  }

  function setAudioMutePreference(muted) {
    if (muted) {
      sessionStorage.setItem(storageKeys.audioMuted, "1");
    } else {
      sessionStorage.removeItem(storageKeys.audioMuted);
    }
  }

  function shouldStartMuted() {
    return sessionStorage.getItem(storageKeys.audioMuted) === "1";
  }

  function clearLocalMemberState() {
    sessionStorage.removeItem(storageKeys.memberId);
    sessionStorage.removeItem(storageKeys.memberName);
    sessionStorage.removeItem(storageKeys.operationName);
    sessionStorage.removeItem(storageKeys.gpsEnabled);
    sessionStorage.removeItem(storageKeys.sensorEnabled);
    sessionStorage.removeItem(storageKeys.audioMuted);
  }

  function formatTime(timestamp) {
    try {
      return new Date(timestamp).toLocaleTimeString([], {
        hour: "numeric",
        minute: "2-digit",
      });
    } catch (error) {
      return "--";
    }
  }

  function formatRelativeTime(timestamp) {
    if (!timestamp) {
      return "--";
    }
    const elapsedSeconds = Math.max(
      0,
      Math.round((Date.now() - new Date(timestamp).getTime()) / 1000),
    );
    if (elapsedSeconds < 30) {
      return "just now";
    }
    if (elapsedSeconds < 3600) {
      return `${Math.round(elapsedSeconds / 60)}m ago`;
    }
    return `${Math.round(elapsedSeconds / 3600)}h ago`;
  }

  function formatCoordinate(value) {
    return Number(value).toFixed(5);
  }

  function distanceMeters(first, second) {
    if (!first || !second) {
      return Number.POSITIVE_INFINITY;
    }
    const toRadians = (degrees) => (degrees * Math.PI) / 180;
    const earthRadiusMeters = 6371000;
    const lat1 = toRadians(first.latitude);
    const lat2 = toRadians(second.latitude);
    const deltaLat = lat2 - lat1;
    const deltaLon = toRadians(second.longitude - first.longitude);
    const a =
      Math.sin(deltaLat / 2) ** 2 +
      Math.cos(lat1) * Math.cos(lat2) * Math.sin(deltaLon / 2) ** 2;
    return earthRadiusMeters * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  function updateConnectionMeta(label) {
    if (elements.runtimeConnectionState) {
      elements.runtimeConnectionState.textContent = label;
    }
  }

  function setConnectionState(status, label) {
    if (elements.runtimeConnectionDot) {
      elements.runtimeConnectionDot.classList.remove("is-live", "is-error");
      if (status === "live") {
        elements.runtimeConnectionDot.classList.add("is-live");
      } else if (status === "error") {
        elements.runtimeConnectionDot.classList.add("is-error");
      }
    }
    if (elements.runtimeConnectionLabel) {
      elements.runtimeConnectionLabel.textContent = label;
    }
    updateConnectionMeta(label);
  }

  function setSessionState(label) {
    if (elements.runtimeSessionState) {
      elements.runtimeSessionState.textContent = label;
    }
  }

  function setGpsState(status, detail) {
    if (elements.runtimeGpsState) {
      elements.runtimeGpsState.textContent = status;
    }
    if (elements.runtimeGpsDetail) {
      elements.runtimeGpsDetail.textContent = detail;
    }
    if (elements.runtimeGpsToggle) {
      if (!navigator.geolocation) {
        elements.runtimeGpsToggle.disabled = true;
        elements.runtimeGpsToggle.textContent = "GPS unsupported";
      } else {
        elements.runtimeGpsToggle.disabled = state.endingOperation;
        elements.runtimeGpsToggle.textContent = state.gps.active ? "Stop GPS" : "Start GPS";
      }
    }
  }

  function setReportState(message, { error = false } = {}) {
    if (elements.runtimeReportStatus) {
      elements.runtimeReportStatus.textContent = message;
      elements.runtimeReportStatus.classList.toggle("is-error", error);
    }
  }

  function pushFeed(message, kind = "note") {
    if (!elements.runtimeFeed) {
      return;
    }
    state.feed.unshift({
      kind,
      message,
      timestamp: new Date().toISOString(),
    });
    state.feed = state.feed.slice(0, 14);
    renderFeed();
  }

  function renderFeed() {
    if (!elements.runtimeFeed) {
      return;
    }
    if (!state.feed.length) {
      elements.runtimeFeed.innerHTML =
        '<div class="member-empty"><p>Waiting for member connection status.</p></div>';
      return;
    }
    elements.runtimeFeed.innerHTML = state.feed
      .map(
        (entry) => `
          <div class="member-feed-item member-feed-item--${escapeHtml(entry.kind)}">
            <p>${escapeHtml(entry.message)}</p>
            <small>${escapeHtml(formatTime(entry.timestamp))}</small>
          </div>
        `,
      )
      .join("");
  }

  function renderAlerts() {
    if (!elements.runtimeAlerts) {
      return;
    }
    if (!state.alerts.length) {
      elements.runtimeAlerts.innerHTML =
        '<div class="member-empty"><p>Waiting for live alerts.</p></div>';
      return;
    }
    elements.runtimeAlerts.innerHTML = state.alerts
      .map((alert) => {
        const category = String(alert.category || "alert").replaceAll("_", " ");
        const location =
          Number.isFinite(alert.latitude) && Number.isFinite(alert.longitude)
            ? ` · ${formatCoordinate(alert.latitude)}, ${formatCoordinate(alert.longitude)}`
            : "";
        return `
          <article class="member-alert-item member-alert-item--${escapeHtml(alert.severity || "info")}">
            <div class="member-alert-head">
              <span class="member-alert-pill">${escapeHtml(category)}</span>
              <small>${escapeHtml(formatRelativeTime(alert.timestamp))}</small>
            </div>
            <p>${escapeHtml(alert.text || "Alert received.")}</p>
            <small>${escapeHtml(formatTime(alert.timestamp))}${escapeHtml(location)}</small>
          </article>
        `;
      })
      .join("");
  }

  function renderAlertSummary() {
    if (elements.runtimeAlertCount) {
      elements.runtimeAlertCount.textContent = String(state.alerts.length);
    }
    if (!elements.runtimeAlertSummary) {
      return;
    }
    if (!state.alerts.length) {
      elements.runtimeAlertSummary.textContent = "Waiting for live alerts.";
      return;
    }
    const latest = state.alerts[0];
    elements.runtimeAlertSummary.textContent = `${latest.severity || "info"} · ${formatRelativeTime(latest.timestamp)}`;
  }

  function pushAlert(alert) {
    state.alerts.unshift({
      severity: String(alert.severity || "info"),
      category: String(alert.category || "alert"),
      text: String(alert.text || "Alert received."),
      timestamp: String(alert.timestamp || new Date().toISOString()),
      latitude:
        alert.latitude === null || alert.latitude === undefined ? null : Number(alert.latitude),
      longitude:
        alert.longitude === null || alert.longitude === undefined
          ? null
          : Number(alert.longitude),
      event_id: alert.event_id ? String(alert.event_id) : null,
    });
    state.alerts = state.alerts.slice(0, 8);
    renderAlerts();
    renderAlertSummary();
  }

  function updateIdentity(role, memberId) {
    if (elements.runtimeRole) {
      elements.runtimeRole.textContent = role || "observer";
    }
    if (elements.runtimeMemberId) {
      elements.runtimeMemberId.textContent = memberId || "--";
    }
  }

  function updateOperationName(name) {
    const operationName = normalizeWhitespace(name) || "Osk";
    if (elements.runtimeOperationName) {
      elements.runtimeOperationName.textContent = operationName;
    }
    rememberOperationName(operationName);
  }

  function clearReconnectTimer() {
    if (state.reconnectTimer) {
      window.clearTimeout(state.reconnectTimer);
      state.reconnectTimer = null;
    }
  }

  function scheduleReconnect(reason) {
    if (state.intentionallyLeaving || state.endingOperation || state.reconnectTimer) {
      return;
    }
    state.reconnectAttempt += 1;
    const delayMs = Math.min(
      reconnectConfig.maxDelayMs,
      reconnectConfig.baseDelayMs * 2 ** Math.max(0, state.reconnectAttempt - 1),
    );
    setSessionState("Reconnecting");
    setConnectionState("error", `Reconnecting in ${Math.round(delayMs / 1000)}s`);
    if (reason) {
      pushFeed(reason, "warning");
    }
    state.reconnectTimer = window.setTimeout(() => {
      state.reconnectTimer = null;
      connectMemberSocket();
    }, delayMs);
  }

  function isSocketOpen() {
    return Boolean(state.socket && state.socket.readyState === WebSocket.OPEN);
  }

  function sendSocketJson(payload) {
    if (!isSocketOpen()) {
      return false;
    }
    state.socket.send(JSON.stringify(payload));
    return true;
  }

  function sendSocketBinary(payload) {
    if (!isSocketOpen()) {
      return false;
    }
    state.socket.send(payload);
    return true;
  }

  function refreshGpsState() {
    if (!navigator.geolocation) {
      setGpsState("Unsupported", "This browser cannot share location.");
      return;
    }
    if (state.gps.error) {
      setGpsState("Blocked", state.gps.error);
      return;
    }
    if (!state.gps.active) {
      setGpsState("Off", "Location sharing is off.");
      return;
    }
    if (!state.gps.lastPosition) {
      setGpsState("Acquiring", "Waiting for the first GPS fix.");
      return;
    }
    const detailParts = [];
    if (Number.isFinite(state.gps.lastPosition.accuracy)) {
      detailParts.push(`Accuracy ${Math.round(state.gps.lastPosition.accuracy)}m`);
    }
    if (state.gps.lastFixAt) {
      detailParts.push(`Updated ${formatTime(state.gps.lastFixAt)}`);
    }
    if (!state.authenticated || !isSocketOpen()) {
      setGpsState("Tracking", `${detailParts.join(" · ")} · waiting for reconnect`);
      return;
    }
    setGpsState("Live", detailParts.join(" · "));
  }

  function maybeSendLatestGps({ force = false } = {}) {
    if (!state.gps.lastPosition) {
      refreshGpsState();
      return;
    }
    const current = state.gps.lastPosition;
    const now = current.capturedAt;
    const movedMeters = distanceMeters(state.gps.lastSentPosition, current);
    const intervalMs =
      movedMeters >= gpsConfig.significantChangeMeters
        ? gpsConfig.movingIntervalMs
        : gpsConfig.stationaryIntervalMs;
    if (!force && state.gps.lastSentAt && now - state.gps.lastSentAt < intervalMs) {
      refreshGpsState();
      return;
    }
    if (
      !sendSocketJson({
        type: "gps",
        lat: current.latitude,
        lon: current.longitude,
        accuracy: current.accuracy,
      })
    ) {
      refreshGpsState();
      return;
    }
    state.gps.lastSentAt = now;
    state.gps.lastSentPosition = current;
    refreshGpsState();
  }

  function stopGpsWatch({ preservePreference = false, preserveError = false } = {}) {
    if (state.gps.watchId !== null && navigator.geolocation) {
      navigator.geolocation.clearWatch(state.gps.watchId);
    }
    state.gps.active = false;
    state.gps.watchId = null;
    if (!preserveError) {
      state.gps.error = null;
    }
    if (!preservePreference) {
      setGpsPreference(false);
    }
    refreshGpsState();
  }

  function startGpsWatch() {
    if (!navigator.geolocation) {
      setGpsState("Unsupported", "This browser cannot share location.");
      return;
    }
    if (state.gps.active) {
      return;
    }
    state.gps.error = null;
    state.gps.active = true;
    setGpsPreference(true);
    refreshGpsState();
    state.gps.watchId = navigator.geolocation.watchPosition(
      (position) => {
        state.gps.lastFixAt = new Date().toISOString();
        state.gps.lastPosition = {
          latitude: Number(position.coords.latitude),
          longitude: Number(position.coords.longitude),
          accuracy: Number(position.coords.accuracy || 0),
          capturedAt: Date.now(),
        };
        state.gps.error = null;
        maybeSendLatestGps({ force: state.gps.lastSentAt === null });
      },
      (gpsError) => {
        const message =
          gpsError && gpsError.code === gpsError.PERMISSION_DENIED
            ? "Location permission was denied."
            : "Location fix unavailable.";
        state.gps.error = message;
        pushFeed(message, "warning");
        if (gpsError && gpsError.code === gpsError.PERMISSION_DENIED) {
          stopGpsWatch({ preserveError: true });
          return;
        }
        refreshGpsState();
      },
      {
        enableHighAccuracy: true,
        maximumAge: 15000,
        timeout: 20000,
      },
    );
  }

  function toggleGpsWatch() {
    if (state.gps.active) {
      stopGpsWatch();
      pushFeed("Location sharing stopped.", "note");
      return;
    }
    startGpsWatch();
    pushFeed("Location sharing requested.", "note");
  }

  function updateSensorSnapshot(kind, snapshot) {
    state.sensor[kind] = snapshot || null;
    refreshSensorUi();
    refreshObserverUi();
    updateActionAvailability();
  }

  function sensorStreamRunning() {
    return Boolean(
      state.sensor.audio?.running || state.sensor.frame?.running || state.sensor.starting,
    );
  }

  function updateObserverSnapshot(snapshot) {
    state.observer.snapshot = snapshot || null;
    refreshObserverUi();
    updateActionAvailability();
  }

  function observerClipRecording() {
    return Boolean(state.observer.snapshot?.clip?.recording);
  }

  function observerClipCoolingDown() {
    return Number(state.observer.snapshot?.clip?.cooldownRemainingMs || 0) > 0;
  }

  function renderSensorStatus(stateLabel, detailLabel) {
    if (elements.runtimeSensorState) {
      elements.runtimeSensorState.textContent = stateLabel;
    }
    if (elements.runtimeSensorDetail) {
      elements.runtimeSensorDetail.textContent = detailLabel;
    }
  }

  function refreshSensorUi() {
    const sensorRole = isSensorRole(state.sensor.role);
    if (elements.runtimeSensorPanel) {
      elements.runtimeSensorPanel.hidden = !sensorRole;
    }
    if (elements.runtimeSensorSignal) {
      elements.runtimeSensorSignal.hidden = !sensorRole;
    }

    if (!sensorRole) {
      renderSensorStatus("Observer", "Promote this member to sensor to start live capture.");
      if (elements.runtimeSensorSummary) {
        elements.runtimeSensorSummary.textContent =
          "Observer mode. Promote this member to sensor before starting live capture.";
      }
      if (elements.runtimeAudioState) {
        elements.runtimeAudioState.textContent = "Idle";
      }
      if (elements.runtimeAudioDetail) {
        elements.runtimeAudioDetail.textContent = "No microphone capture yet.";
      }
      if (elements.runtimeFrameState) {
        elements.runtimeFrameState.textContent = "Idle";
      }
      if (elements.runtimeFrameDetail) {
        elements.runtimeFrameDetail.textContent = "No camera sampling yet.";
      }
      return;
    }

    const audio = state.sensor.audio || {};
    const frame = state.sensor.frame || {};
    const audioAck = audio.lastAck;
    const frameAck = frame.lastAck;
    const audioLive = Boolean(audio.running);
    const frameLive = Boolean(frame.running);

    let sensorState = "Ready";
    let sensorDetail = "Waiting for sensor stream start.";
    if (state.sensor.starting) {
      sensorState = "Starting";
      sensorDetail = "Requesting microphone and camera access.";
    } else if (audioLive && frameLive) {
      sensorState = "Live";
      sensorDetail = "Microphone and key-frame sampling are active.";
    } else if (audioLive || frameLive) {
      sensorState = "Partial";
      sensorDetail = "One live stream is active; the other needs attention.";
    } else if (audio.error || frame.error) {
      sensorState = "Blocked";
      sensorDetail = audio.error || frame.error || "Sensor capture could not start.";
    }
    renderSensorStatus(sensorState, sensorDetail);

    if (elements.runtimeSensorSummary) {
      elements.runtimeSensorSummary.textContent = sensorDetail;
    }

    if (elements.runtimeAudioState) {
      elements.runtimeAudioState.textContent = audio.error
        ? "Blocked"
        : audioLive
          ? audio.muted
            ? "Muted"
            : "Live"
          : "Idle";
    }
    if (elements.runtimeAudioDetail) {
      if (audio.error) {
        elements.runtimeAudioDetail.textContent = audio.error;
      } else if (audioLive) {
        const ackText =
          audioAck && audioAck.accepted === false
            ? ` · last ack rejected`
            : audioAck && audioAck.duplicate
              ? " · duplicate ack"
              : "";
        elements.runtimeAudioDetail.textContent = `${audio.emittedChunks || 0} chunks sent${ackText}`;
      } else {
        elements.runtimeAudioDetail.textContent = "No microphone capture yet.";
      }
    }

    if (elements.runtimeFrameState) {
      elements.runtimeFrameState.textContent = frame.error
        ? "Blocked"
        : frameLive
          ? "Live"
          : "Idle";
    }
    if (elements.runtimeFrameDetail) {
      if (frame.error) {
        elements.runtimeFrameDetail.textContent = frame.error;
      } else if (frameLive) {
        const score =
          typeof frame.lastScore === "number" ? `score ${frame.lastScore.toFixed(2)}` : "sampling";
        const ackText =
          frameAck && frameAck.accepted === false
            ? " · last ack rejected"
            : frameAck && frameAck.duplicate
              ? " · duplicate ack"
              : "";
        elements.runtimeFrameDetail.textContent = `${frame.emittedFrames || 0} frames sent · ${score}${ackText}`;
      } else {
        elements.runtimeFrameDetail.textContent = "No camera sampling yet.";
      }
    }
  }

  function refreshObserverUi() {
    const observerRole = !isSensorRole(state.sensor.role);
    if (elements.runtimeObserverPanel) {
      elements.runtimeObserverPanel.hidden = !observerRole;
    }
    if (!observerRole) {
      return;
    }

    const snapshot = state.observer.snapshot || {};
    const photo = snapshot.photo || {};
    const clip = snapshot.clip || {};

    if (elements.runtimeObserverSummary) {
      elements.runtimeObserverSummary.textContent = observerClipRecording()
        ? `Recording up to ${observerConfig.clipDurationSeconds}s of audio for the hub.`
        : observerClipCoolingDown()
          ? `Audio clip cooldown is active for ${Math.ceil(
              Number(clip.cooldownRemainingMs || 0) / 1000,
            )}s.`
          : "Capture a quick still or a short audio clip when there is something worth review, without switching into full sensor mode.";
    }

    if (elements.runtimePhotoState) {
      elements.runtimePhotoState.textContent = photo.capturing
        ? "Capturing"
        : photo.error
          ? "Blocked"
          : photo.lastCapturedAt
            ? "Sent"
            : "Ready";
    }
    if (elements.runtimePhotoDetail) {
      if (photo.error) {
        elements.runtimePhotoDetail.textContent = photo.error;
      } else if (photo.capturing) {
        elements.runtimePhotoDetail.textContent =
          "Camera access granted. Grabbing a single still frame now.";
      } else if (photo.lastCapturedAt) {
        const ackText =
          photo.lastAck && photo.lastAck.accepted === false
            ? `rejected · ${photo.lastAck.reason || "hub rejected the still"}`
            : photo.lastAck && photo.lastAck.duplicate
              ? "duplicate ack from hub"
              : "hub ack received";
        elements.runtimePhotoDetail.textContent = `${formatRelativeTime(photo.lastCapturedAt)} · ${ackText}`;
      } else {
        elements.runtimePhotoDetail.textContent =
          "Still images upload as high-priority observer evidence.";
      }
    }

    if (elements.runtimeClipState) {
      elements.runtimeClipState.textContent = clip.recording
        ? "Recording"
        : observerClipCoolingDown()
          ? "Cooldown"
          : clip.error
            ? "Blocked"
            : clip.lastCapturedAt
              ? "Sent"
              : "Ready";
    }
    if (elements.runtimeClipDetail) {
      if (clip.error && !observerClipCoolingDown()) {
        elements.runtimeClipDetail.textContent = clip.error;
      } else if (clip.recording) {
        elements.runtimeClipDetail.textContent = `Capturing up to ${observerConfig.clipDurationSeconds}s of audio. Tap again to stop early.`;
      } else if (observerClipCoolingDown()) {
        elements.runtimeClipDetail.textContent = `${Math.ceil(
          Number(clip.cooldownRemainingMs || 0) / 1000,
        )}s until the next short clip can start.`;
      } else if (clip.lastCapturedAt) {
        const durationSeconds = Math.max(
          1,
          Math.round(Number(clip.lastDurationMs || 0) / 1000),
        );
        const ackText =
          clip.lastAck && clip.lastAck.accepted === false
            ? `rejected · ${clip.lastAck.reason || "hub rejected the clip"}`
            : clip.lastAck && clip.lastAck.duplicate
              ? "duplicate ack from hub"
              : "hub ack received";
        elements.runtimeClipDetail.textContent = `${durationSeconds}s clip · ${formatRelativeTime(clip.lastCapturedAt)} · ${ackText}`;
      } else {
        elements.runtimeClipDetail.textContent =
          "Short audio clips help the hub transcribe urgent context.";
      }
    }
  }

  function updateActionAvailability() {
    const socketOpen = isSocketOpen();
    if (elements.runtimeReportText) {
      elements.runtimeReportText.disabled = state.endingOperation;
      elements.runtimeReportText.maxLength = manualReportMaxLength;
    }
    if (elements.runtimeReportSend) {
      elements.runtimeReportSend.disabled =
        !socketOpen || state.manualReportPending || state.endingOperation;
    }
    if (elements.runtimeSensorToggle) {
      elements.runtimeSensorToggle.disabled =
        !isSensorRole(state.sensor.role) ||
        state.sensor.starting ||
        (!socketOpen && !sensorStreamRunning()) ||
        state.endingOperation;
      elements.runtimeSensorToggle.textContent = sensorStreamRunning()
        ? "Stop sensor stream"
        : "Start sensor stream";
    }
    if (elements.runtimeAudioToggle) {
      const audioRunning = Boolean(state.sensor.audio?.running);
      elements.runtimeAudioToggle.disabled =
        !isSensorRole(state.sensor.role) || !audioRunning || state.endingOperation;
      elements.runtimeAudioToggle.textContent = state.sensor.audio?.muted
        ? "Unmute mic"
        : "Mute mic";
    }
    if (elements.runtimePhotoCapture) {
      const photoBusy = Boolean(state.observer.snapshot?.photo?.capturing);
      elements.runtimePhotoCapture.disabled =
        isSensorRole(state.sensor.role) || !socketOpen || photoBusy || state.endingOperation;
      elements.runtimePhotoCapture.textContent = photoBusy ? "Capturing photo" : "Snap photo";
    }
    if (elements.runtimeClipToggle) {
      elements.runtimeClipToggle.disabled =
        isSensorRole(state.sensor.role) ||
        !socketOpen ||
        observerClipCoolingDown() ||
        state.endingOperation;
      elements.runtimeClipToggle.textContent = observerClipRecording()
        ? "Stop clip"
        : observerClipCoolingDown()
          ? `Hold ${Math.ceil(
              Number(state.observer.snapshot?.clip?.cooldownRemainingMs || 0) / 1000,
            )}s`
          : "Record clip";
    }
  }

  function ensureSensorModules() {
    if (!state.sensor.audioCapture) {
      const audioFactory = globalThis.OskAudioCapture?.createAudioCapture;
      if (typeof audioFactory !== "function") {
        throw new Error("Audio capture module is unavailable.");
      }
      state.sensor.audioCapture = audioFactory({
        chunkMs: sensorConfig.audioChunkMs,
        sendJson: sendSocketJson,
        sendBinary: sendSocketBinary,
        getContext: () => ({
          memberId: sessionStorage.getItem(storageKeys.memberId) || "",
        }),
        onStateChange: (snapshot) => updateSensorSnapshot("audio", snapshot),
        onError: (message) => {
          pushFeed(message, "warning");
        },
      });
    }

    if (!state.sensor.frameSampler) {
      const frameFactory = globalThis.OskFrameSampler?.createFrameSampler;
      if (typeof frameFactory !== "function") {
        throw new Error("Frame sampling module is unavailable.");
      }
      state.sensor.frameSampler = frameFactory({
        fps: sensorConfig.frameSamplingFps,
        threshold: sensorConfig.frameChangeThreshold,
        baselineIntervalSeconds: sensorConfig.frameBaselineIntervalSeconds,
        jpegQuality: sensorConfig.frameJpegQuality,
        targetWidth: sensorConfig.videoWidth,
        targetHeight: sensorConfig.videoHeight,
        workerUrl: "/static/sampling-worker.js",
        previewElement: elements.runtimeSensorPreview,
        sendJson: sendSocketJson,
        sendBinary: sendSocketBinary,
        getContext: () => ({
          memberId: sessionStorage.getItem(storageKeys.memberId) || "",
        }),
        onStateChange: (snapshot) => updateSensorSnapshot("frame", snapshot),
        onError: (message) => {
          pushFeed(message, "warning");
        },
      });
    }
  }

  function ensureObserverMediaModule() {
    if (state.observer.mediaCapture) {
      return;
    }
    const mediaFactory = globalThis.OskObserverMedia?.createObserverMediaCapture;
    if (typeof mediaFactory !== "function") {
      throw new Error("Observer media module is unavailable.");
    }
    state.observer.mediaCapture = mediaFactory({
      clipDurationSeconds: observerConfig.clipDurationSeconds,
      clipCooldownSeconds: observerConfig.clipCooldownSeconds,
      photoQuality: observerConfig.photoQuality,
      targetWidth: sensorConfig.videoWidth,
      targetHeight: sensorConfig.videoHeight,
      sendJson: sendSocketJson,
      sendBinary: sendSocketBinary,
      getContext: () => ({
        memberId: sessionStorage.getItem(storageKeys.memberId) || "",
      }),
      onStateChange: (snapshot) => updateObserverSnapshot(snapshot),
      onError: (message) => {
        pushFeed(message, "warning");
      },
    });
  }

  async function startSensorCapture({ automatic = false } = {}) {
    if (!isSensorRole(state.sensor.role) || state.sensor.starting) {
      return;
    }
    if (!isSocketOpen()) {
      if (!automatic) {
        pushFeed("Connection must be live before sensor capture can start.", "warning");
      }
      return;
    }

    setSensorPreference(true);
    state.sensor.starting = true;
    refreshSensorUi();
    updateActionAvailability();

    try {
      ensureSensorModules();
    } catch (error) {
      state.sensor.starting = false;
      refreshSensorUi();
      updateActionAvailability();
      pushFeed(error instanceof Error ? error.message : "Sensor modules are unavailable.", "critical");
      return;
    }

    const failures = [];
    try {
      await state.sensor.audioCapture.start();
      if (shouldStartMuted()) {
        state.sensor.audioCapture.mute();
      }
    } catch (error) {
      failures.push(error instanceof Error ? error.message : "Microphone capture failed.");
    }

    try {
      await state.sensor.frameSampler.start();
    } catch (error) {
      failures.push(error instanceof Error ? error.message : "Camera sampling failed.");
    }

    state.sensor.starting = false;
    refreshSensorUi();
    updateActionAvailability();

    if (failures.length >= 2) {
      pushFeed("Sensor capture could not start. Check microphone and camera permissions.", "warning");
      return;
    }
    if (failures.length === 1) {
      pushFeed(`Sensor capture started with partial availability: ${failures[0]}`, "warning");
      return;
    }
    pushFeed(automatic ? "Sensor capture restored." : "Sensor capture started.", "success");
  }

  async function stopSensorCapture({ preservePreference = false, quiet = false } = {}) {
    state.sensor.starting = false;
    if (!preservePreference) {
      setSensorPreference(false);
    }
    const tasks = [];
    if (state.sensor.audioCapture) {
      tasks.push(state.sensor.audioCapture.stop());
    }
    if (state.sensor.frameSampler) {
      tasks.push(state.sensor.frameSampler.stop());
    }
    if (tasks.length) {
      await Promise.allSettled(tasks);
    }
    refreshSensorUi();
    updateActionAvailability();
    if (!quiet) {
      pushFeed("Sensor capture stopped.", "note");
    }
  }

  async function captureObserverPhoto() {
    if (isSensorRole(state.sensor.role) || !isSocketOpen()) {
      pushFeed("Connection must be live before a manual photo can be sent.", "warning");
      return;
    }
    try {
      ensureObserverMediaModule();
      await state.observer.mediaCapture.capturePhoto();
      pushFeed("Manual photo captured. Waiting for hub acknowledgement.", "note");
    } catch (error) {
      if (error instanceof Error) {
        pushFeed(error.message, "warning");
      }
    }
  }

  async function stopObserverMedia({ quiet = false } = {}) {
    if (!state.observer.mediaCapture) {
      return;
    }
    await state.observer.mediaCapture.destroy();
    state.observer.mediaCapture = null;
    updateObserverSnapshot(null);
    if (!quiet) {
      pushFeed("Manual observer media capture stopped.", "note");
    }
  }

  async function toggleObserverClip() {
    if (isSensorRole(state.sensor.role) || !isSocketOpen()) {
      pushFeed("Connection must be live before a short clip can be sent.", "warning");
      return;
    }
    try {
      ensureObserverMediaModule();
      if (observerClipRecording()) {
        await state.observer.mediaCapture.stopClip();
        pushFeed("Short audio clip stopped. Waiting for hub acknowledgement.", "note");
        return;
      }
      await state.observer.mediaCapture.startClip();
      pushFeed(`Recording up to ${observerConfig.clipDurationSeconds}s of audio.`, "note");
    } catch (error) {
      if (error instanceof Error) {
        pushFeed(error.message, "warning");
      }
    }
  }

  function toggleSensorCapture() {
    if (sensorStreamRunning()) {
      void stopSensorCapture();
      return;
    }
    void startSensorCapture();
  }

  function toggleAudioMute() {
    if (!state.sensor.audioCapture || !state.sensor.audio?.running) {
      return;
    }
    if (state.sensor.audio?.muted) {
      state.sensor.audioCapture.unmute();
      setAudioMutePreference(false);
      pushFeed("Microphone unmuted.", "note");
      return;
    }
    state.sensor.audioCapture.mute();
    setAudioMutePreference(true);
    pushFeed("Microphone muted.", "note");
  }

  function applyMemberRole(role, { automaticStart = true } = {}) {
    state.sensor.role = String(role || "observer");
    updateIdentity(
      state.sensor.role,
      sessionStorage.getItem(storageKeys.memberId) || "--",
    );
    if (!isSensorRole(state.sensor.role)) {
      if (sensorStreamRunning()) {
        void stopSensorCapture({ preservePreference: false, quiet: true });
      }
      refreshSensorUi();
      refreshObserverUi();
      updateActionAvailability();
      return;
    }
    void stopObserverMedia({ quiet: true });
    refreshSensorUi();
    refreshObserverUi();
    updateActionAvailability();
    if (automaticStart && shouldAutoStartSensorCapture() && isSocketOpen()) {
      void startSensorCapture({ automatic: true });
    }
  }

  async function fetchMemberSession() {
    try {
      return await fetchJson(bootstrap.paths.member_session, { method: "GET" });
    } catch (error) {
      if (error && error.status === 401) {
        return null;
      }
      throw error;
    }
  }

  function applySessionIdentity(session) {
    if (!session) {
      return;
    }
    if (session.member_id) {
      sessionStorage.setItem(storageKeys.memberId, String(session.member_id));
    }
    if (session.member_name) {
      const memberName = normalizeWhitespace(session.member_name);
      if (memberName) {
        sessionStorage.setItem(storageKeys.memberName, memberName);
      }
    }
    if (session.operation_name) {
      updateOperationName(session.operation_name);
    }
  }

  async function exchangeMemberRuntimeSession(memberSessionCode) {
    const code = String(memberSessionCode || "").trim();
    if (!code) {
      return null;
    }
    try {
      const session = await fetchJson(bootstrap.paths.member_runtime_session, {
        method: "POST",
        body: JSON.stringify({ member_session_code: code }),
      });
      state.session = session;
      applySessionIdentity(session);
      return session;
    } catch (error) {
      pushFeed(
        "Secure member session refresh failed. A full reload may require rescanning the coordinator QR code.",
        "warning",
      );
      return null;
    }
  }

  async function clearOfflineState() {
    try {
      await globalThis.OskPwaRuntime?.clearMemberOfflineState?.();
    } catch (error) {
      // Ignore offline-cache cleanup failures during member teardown.
    }
  }

  async function clearMemberSession() {
    state.intentionallyLeaving = true;
    clearReconnectTimer();
    stopGpsWatch();
    await stopSensorCapture({ preservePreference: false, quiet: true });
    await stopObserverMedia({ quiet: true });
    if (state.socket && state.socket.readyState < WebSocket.CLOSING) {
      try {
        state.socket.close(1000, "member leaving");
      } catch (error) {
        // Ignore close failures during local cleanup.
      }
    }
    try {
      await fetchJson(bootstrap.paths.member_session, { method: "DELETE" });
    } catch (error) {
      // Ignore remote clear failures and still clear browser state.
    }
    await clearOfflineState();
    clearLocalMemberState();
    window.location.href = bootstrap.paths.join_page;
  }

  function handleMediaAck(kind, payload) {
    if (kind === "audio" && state.sensor.audioCapture) {
      state.sensor.audioCapture.handleAck(payload);
    }
    if (kind === "frame" && state.sensor.frameSampler) {
      state.sensor.frameSampler.handleAck(payload);
    }
    if (kind === "audio" && state.observer.mediaCapture && !isSensorRole(state.sensor.role)) {
      state.observer.mediaCapture.handleAck("clip", payload);
      if (payload.accepted === true) {
        pushFeed(
          payload.duplicate
            ? "Manual audio clip was already received by the hub."
            : "Manual audio clip delivered to the hub.",
          payload.duplicate ? "note" : "success",
        );
      }
    }
    if (kind === "frame" && state.observer.mediaCapture && !isSensorRole(state.sensor.role)) {
      state.observer.mediaCapture.handleAck("photo", payload);
      if (payload.accepted === true) {
        pushFeed(
          payload.duplicate
            ? "Manual photo was already received by the hub."
            : "Manual photo delivered to the hub.",
          payload.duplicate ? "note" : "success",
        );
      }
    }
    if (payload.accepted === false) {
      pushFeed(payload.reason || `${kind} capture was rejected by the hub.`, "warning");
    }
  }

  function handleSocketMessage(payload) {
    if (payload.type === "auth_ok") {
      state.authenticated = true;
      state.reconnectAttempt = 0;
      sessionStorage.setItem(storageKeys.memberId, String(payload.member_id || ""));
      if (payload.operation_name) {
        updateOperationName(payload.operation_name);
      }
      applyMemberRole(String(payload.role || "observer"));
      setSessionState(payload.resumed ? "Resumed" : "Joined");
      setConnectionState("live", payload.resumed ? "Resumed" : "Connected");
      pushFeed(
        payload.resumed ? "Member session resumed." : "Member session established.",
        "success",
      );
      if (shouldAutoRestartGps()) {
        startGpsWatch();
        maybeSendLatestGps({ force: true });
      } else {
        refreshGpsState();
      }
      if (payload.member_session_code) {
        void exchangeMemberRuntimeSession(payload.member_session_code);
      }
      updateActionAvailability();
      return;
    }

    if (payload.type === "role_change") {
      applyMemberRole(String(payload.role || "observer"));
      pushFeed(`Role updated to ${payload.role}.`);
      return;
    }

    if (payload.type === "alert") {
      pushAlert(payload);
      pushFeed(payload.text || "Received alert.", payload.severity || "warning");
      return;
    }

    if (payload.type === "report_ack") {
      state.manualReportPending = false;
      if (payload.accepted) {
        if (elements.runtimeLastReport) {
          elements.runtimeLastReport.textContent = formatTime(payload.timestamp);
        }
        if (elements.runtimeReportText) {
          elements.runtimeReportText.value = "";
        }
        setReportState("Field note sent.");
        pushFeed("Field note delivered to the hub.", "success");
      } else {
        setReportState(payload.error || "Report was rejected.", { error: true });
        pushFeed(payload.error || "Report was rejected.", "warning");
      }
      updateActionAvailability();
      return;
    }

    if (payload.type === "audio_ack") {
      handleMediaAck("audio", payload);
      return;
    }

    if (payload.type === "frame_ack") {
      handleMediaAck("frame", payload);
      return;
    }

    if (payload.type === "status") {
      setSessionState("Live");
      pushFeed("Operation status updated.");
      return;
    }

    if (payload.type === "ping") {
      sendSocketJson({ type: "pong" });
      return;
    }

    if (payload.type === "wipe" || payload.type === "op_ended") {
      state.endingOperation = true;
      stopGpsWatch();
      void stopSensorCapture({ preservePreference: false, quiet: true });
      void stopObserverMedia({ quiet: true });
      pushFeed("Operation ended. Clearing local member session.", "critical");
      setSessionState("Ended");
      setConnectionState("error", "Ended");
      updateActionAvailability();
      window.setTimeout(() => {
        void clearMemberSession();
      }, 250);
      return;
    }

    if (payload.type) {
      pushFeed(`Received ${payload.type}.`);
    }
  }

  function connectMemberSocket() {
    if (state.intentionallyLeaving || state.endingOperation) {
      return;
    }
    if (state.socket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(state.socket.readyState)) {
      return;
    }

    const memberName = readStoredName() || "Observer";
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const socketUrl = `${protocol}://${window.location.host}${bootstrap.paths.websocket}`;
    const socket = new WebSocket(socketUrl);
    state.socket = socket;
    state.authenticated = false;
    updateActionAvailability();

    socket.addEventListener("open", () => {
      clearReconnectTimer();
      const payload = {
        type: "auth",
        name: memberName,
      };
      setSessionState("Authorizing");
      setConnectionState("pending", "Authorizing");
      socket.send(JSON.stringify(payload));
    });

    socket.addEventListener("message", (event) => {
      let payload = {};
      try {
        payload = JSON.parse(event.data);
      } catch (error) {
        return;
      }
      handleSocketMessage(payload);
    });

    socket.addEventListener("close", (event) => {
      state.authenticated = false;
      void stopSensorCapture({ preservePreference: true, quiet: true });
      void stopObserverMedia({ quiet: true });
      updateActionAvailability();
      if (state.intentionallyLeaving || state.endingOperation) {
        return;
      }
      if (event.code === 4003 || event.code === 4004) {
        setSessionState("Expired");
        setConnectionState("error", "Rejoin required");
        pushFeed(
          event.code === 4004
            ? "The operation is no longer available. Clearing the local member session."
            : "Secure member session expired. Clearing the local member session.",
          "critical",
        );
        window.setTimeout(() => {
          void clearMemberSession();
        }, 250);
        refreshGpsState();
        return;
      }
      setSessionState("Disconnected");
      scheduleReconnect("Connection closed. Trying to resume.");
      refreshGpsState();
    });

    socket.addEventListener("error", () => {
      setConnectionState("error", "Connection error");
      setReportState("Connection error. Waiting for reconnect.", { error: true });
    });
  }

  async function initializeJoinPage() {
    const session = await fetchMemberSession();
    if (!session) {
      if (elements.joinOperationName) {
        elements.joinOperationName.textContent = "Rescan the coordinator QR";
      }
      if (elements.joinSessionStatus) {
        elements.joinSessionStatus.textContent =
          "The join link creates a clean browser session first, then returns you here without the shared token in the URL.";
      }
      if (elements.joinForm) {
        elements.joinForm.hidden = true;
      }
      if (elements.joinEmpty) {
        elements.joinEmpty.hidden = false;
      }
      return;
    }

    state.session = session;
    applySessionIdentity(session);
    if (session.runtime_authenticated) {
      window.location.href = bootstrap.paths.member_page;
      return;
    }
    if (elements.joinOperationName) {
      elements.joinOperationName.textContent = session.operation_name || "Osk";
    }
    if (elements.joinSessionStatus) {
      elements.joinSessionStatus.textContent =
        "Choose a display name, then continue into the member runtime shell.";
    }
    if (elements.joinForm) {
      elements.joinForm.hidden = false;
    }
    if (elements.joinEmpty) {
      elements.joinEmpty.hidden = true;
    }
    if (elements.joinDisplayName) {
      elements.joinDisplayName.value = readStoredName();
    }
  }

  async function initializeMemberPage() {
    const session = await fetchMemberSession();
    if (!session) {
      clearLocalMemberState();
      window.location.href = bootstrap.paths.join_page;
      return;
    }
    state.session = session;
    applySessionIdentity(session);
    const memberName = normalizeWhitespace(session.member_name || readStoredName() || "Observer");
    if (memberName) {
      sessionStorage.setItem(storageKeys.memberName, memberName);
    }
    updateOperationName(session.operation_name || readStoredOperationName() || "Osk");
    if (elements.runtimeDisplayName) {
      elements.runtimeDisplayName.textContent = memberName;
    }
    updateIdentity(
      session.role || state.sensor.role || "observer",
      session.member_id || sessionStorage.getItem(storageKeys.memberId) || "--",
    );
    applyMemberRole(String(session.role || "observer"), { automaticStart: false });
    if (elements.runtimeLastReport) {
      elements.runtimeLastReport.textContent = "None sent";
    }
    renderFeed();
    renderAlerts();
    renderAlertSummary();
    refreshSensorUi();
    refreshObserverUi();
    updateActionAvailability();
    refreshGpsState();
    setReportState("Reports send over the live member connection.");
    setSessionState(session.runtime_authenticated ? "Resuming" : "Connecting");
    if (session.runtime_authenticated) {
      pushFeed("Secure member session restored from the local browser session.", "note");
    }
    connectMemberSocket();
  }

  function bindEvents() {
    if (elements.joinForm) {
      elements.joinForm.addEventListener("submit", (event) => {
        event.preventDefault();
        const displayName = String(elements.joinDisplayName?.value || "").trim() || "Observer";
        sessionStorage.setItem(storageKeys.memberName, displayName);
        window.location.href = bootstrap.paths.member_page;
      });
    }

    if (elements.joinReset) {
      elements.joinReset.addEventListener("click", () => {
        void clearMemberSession();
      });
    }

    if (elements.runtimeLeave) {
      elements.runtimeLeave.addEventListener("click", () => {
        void clearMemberSession();
      });
    }

    if (elements.runtimeGpsToggle) {
      elements.runtimeGpsToggle.addEventListener("click", () => {
        toggleGpsWatch();
      });
    }

    if (elements.runtimeSensorToggle) {
      elements.runtimeSensorToggle.addEventListener("click", () => {
        toggleSensorCapture();
      });
    }

    if (elements.runtimeAudioToggle) {
      elements.runtimeAudioToggle.addEventListener("click", () => {
        toggleAudioMute();
      });
    }

    if (elements.runtimePhotoCapture) {
      elements.runtimePhotoCapture.addEventListener("click", () => {
        void captureObserverPhoto();
      });
    }

    if (elements.runtimeClipToggle) {
      elements.runtimeClipToggle.addEventListener("click", () => {
        void toggleObserverClip();
      });
    }

    if (elements.runtimeReportForm) {
      elements.runtimeReportForm.addEventListener("submit", (event) => {
        event.preventDefault();
        const text = normalizeWhitespace(elements.runtimeReportText?.value || "");
        if (!text) {
          setReportState("Enter a short field note before sending.", { error: true });
          return;
        }
        if (!isSocketOpen()) {
          setReportState("Connection is down. Wait for reconnect, then resend.", {
            error: true,
          });
          return;
        }
        state.manualReportPending = true;
        setReportState("Sending field note...");
        updateActionAvailability();
        if (
          !sendSocketJson({
            type: "report",
            text: text.slice(0, manualReportMaxLength),
          })
        ) {
          state.manualReportPending = false;
          setReportState("Connection dropped before the report could be sent.", {
            error: true,
          });
          updateActionAvailability();
        }
      });
    }
  }

  async function init() {
    bindEvents();
    if (bootstrap.page === "join") {
      await initializeJoinPage();
      return;
    }
    if (bootstrap.page === "member") {
      await initializeMemberPage();
    }
  }

  void init();
})();
