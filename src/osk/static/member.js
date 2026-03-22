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
  const manualReportMaxLength = Math.max(
    80,
    Number(runtimeConfig.manual_report_max_length || 280),
  );

  const storageKeys = {
    memberId: "osk_member_id",
    memberName: "osk_member_name",
    operationName: "osk_operation_name",
    resumeToken: "osk_member_resume_token",
    gpsEnabled: "osk_member_gps_enabled",
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

  function hasResumeState() {
    return Boolean(
      sessionStorage.getItem(storageKeys.memberId) &&
        sessionStorage.getItem(storageKeys.resumeToken),
    );
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

  function clearLocalMemberState() {
    sessionStorage.removeItem(storageKeys.memberId);
    sessionStorage.removeItem(storageKeys.memberName);
    sessionStorage.removeItem(storageKeys.operationName);
    sessionStorage.removeItem(storageKeys.resumeToken);
    sessionStorage.removeItem(storageKeys.gpsEnabled);
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
        elements.runtimeGpsToggle.disabled = false;
        elements.runtimeGpsToggle.textContent = state.gps.active ? "Stop GPS" : "Start GPS";
      }
    }
  }

  function setReportState(message, { error = false } = {}) {
    if (elements.runtimeReportStatus) {
      elements.runtimeReportStatus.textContent = message;
      elements.runtimeReportStatus.classList.toggle("is-error", error);
    }
    if (elements.runtimeReportSend) {
      const socketOpen = state.socket && state.socket.readyState === WebSocket.OPEN;
      elements.runtimeReportSend.disabled = state.manualReportPending || !socketOpen;
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
      (error) => {
        const message =
          error && error.code === error.PERMISSION_DENIED
            ? "Location permission was denied."
            : "Location fix unavailable.";
        state.gps.error = message;
        pushFeed(message, "warning");
        if (error && error.code === error.PERMISSION_DENIED) {
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

  async function clearMemberSession() {
    state.intentionallyLeaving = true;
    clearReconnectTimer();
    stopGpsWatch();
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
    clearLocalMemberState();
    window.location.href = bootstrap.paths.join_page;
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
  }

  function handleSocketMessage(payload) {
    if (payload.type === "auth_ok") {
      state.authenticated = true;
      state.reconnectAttempt = 0;
      sessionStorage.setItem(storageKeys.memberId, String(payload.member_id || ""));
      sessionStorage.setItem(storageKeys.resumeToken, String(payload.resume_token || ""));
      if (payload.operation_name) {
        updateOperationName(payload.operation_name);
      }
      updateIdentity(String(payload.role || "observer"), String(payload.member_id || "--"));
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
      updateActionAvailability();
      return;
    }

    if (payload.type === "role_change") {
      updateIdentity(String(payload.role || "--"), sessionStorage.getItem(storageKeys.memberId));
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
      const resumeMemberId = sessionStorage.getItem(storageKeys.memberId);
      const resumeToken = sessionStorage.getItem(storageKeys.resumeToken);
      const payload = {
        type: "auth",
        name: memberName,
      };
      if (resumeMemberId && resumeToken) {
        payload.resume_member_id = resumeMemberId;
        payload.resume_token = resumeToken;
      }
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

    socket.addEventListener("close", () => {
      state.authenticated = false;
      updateActionAvailability();
      if (state.intentionallyLeaving || state.endingOperation) {
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
    rememberOperationName(session.operation_name);
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
    const resumeReady = hasResumeState();
    if (!session && !resumeReady) {
      clearLocalMemberState();
      window.location.href = bootstrap.paths.join_page;
      return;
    }
    state.session = session;
    const memberName = readStoredName() || "Observer";
    updateOperationName(session?.operation_name || readStoredOperationName() || "Osk");
    if (elements.runtimeDisplayName) {
      elements.runtimeDisplayName.textContent = memberName;
    }
    if (elements.runtimeLastReport) {
      elements.runtimeLastReport.textContent = "None sent";
    }
    renderFeed();
    renderAlerts();
    renderAlertSummary();
    updateActionAvailability();
    refreshGpsState();
    setReportState("Reports send over the live member connection.");
    if (!session && resumeReady) {
      setSessionState("Resuming");
      pushFeed(
        "Join session is no longer present. Attempting reconnect from local member resume state.",
        "warning",
      );
    } else {
      setSessionState("Connecting");
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
