(function () {
  const bootstrapNode = document.getElementById("osk-dashboard-bootstrap");
  if (!bootstrapNode) {
    return;
  }

  const bootstrap = JSON.parse(bootstrapNode.textContent || "{}");
  const state = {
    authenticated: false,
    filters: {
      include: ["finding", "event", "sitrep"],
      status: "",
      severity: "",
      category: "",
    },
    selectedKey: null,
    feedItems: [],
    detail: null,
    correlations: null,
    latestSitrep: null,
    members: [],
    memberSummary: null,
    bufferHistory: null,
    mapStatus: null,
    operationStatus: null,
    intelligenceStatus: null,
    lastSyncAt: null,
    freshKeys: new Set(),
    streamHandle: null,
    streamRetryHandle: null,
    refreshInFlight: false,
  };

  const elements = {
    authCodeInput: document.getElementById("auth-code-input"),
    authForm: document.getElementById("auth-form"),
    authGate: document.getElementById("auth-gate"),
    authStatus: document.getElementById("auth-status"),
    authSubmit: document.getElementById("auth-submit"),
    operationName: document.getElementById("operation-name"),
    operationSubtitle: document.getElementById("operation-subtitle"),
    startedAt: document.getElementById("started-at"),
    uptime: document.getElementById("uptime"),
    refreshLabel: document.getElementById("refresh-label"),
    connectionIndicator: document.getElementById("connection-indicator"),
    connectionLabel: document.getElementById("connection-label"),
    refreshButton: document.getElementById("refresh-button"),
    filterForm: document.getElementById("filter-form"),
    feedBanner: document.getElementById("feed-banner"),
    feedCount: document.getElementById("feed-count"),
    lastSync: document.getElementById("last-sync"),
    reviewFeed: document.getElementById("review-feed"),
    detailTitle: document.getElementById("detail-title"),
    detailMeta: document.getElementById("detail-meta"),
    detailStage: document.getElementById("detail-stage"),
    findingActions: document.getElementById("finding-actions"),
    findingNoteForm: document.getElementById("finding-note-form"),
    findingNoteInput: document.getElementById("finding-note-input"),
    noteStatus: document.getElementById("note-status"),
    metricMembers: document.getElementById("metric-members"),
    metricSensors: document.getElementById("metric-sensors"),
    metricConnected: document.getElementById("metric-connected"),
    memberHealth: document.getElementById("member-health"),
    memberMap: document.getElementById("member-map"),
    memberMapStatus: document.getElementById("member-map-status"),
    memberMapViewport: document.getElementById("member-map-viewport"),
    memberSummary: document.getElementById("member-summary"),
    bufferTrendSummary: document.getElementById("buffer-trend-summary"),
    bufferTrendChart: document.getElementById("buffer-trend-chart"),
    ingestPressure: document.getElementById("ingest-pressure"),
    latestSitrep: document.getElementById("latest-sitrep"),
    pipelineStatus: document.getElementById("pipeline-status"),
    selectionEcho: document.getElementById("selection-echo"),
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function formatTimestamp(value) {
    if (!value) {
      return "Unknown";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return "Unknown";
    }
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }).format(date);
  }

  function formatLongTimestamp(value) {
    if (!value) {
      return "Unknown";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return "Unknown";
    }
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(date);
  }

  function formatUptime(startedAt) {
    if (!startedAt) {
      return "--";
    }
    const elapsedSeconds = Math.max(
      0,
      Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000),
    );
    const hours = Math.floor(elapsedSeconds / 3600);
    const minutes = Math.floor((elapsedSeconds % 3600) / 60);
    const seconds = elapsedSeconds % 60;
    const parts = [];
    if (hours > 0) {
      parts.push(`${hours}h`);
    }
    if (hours > 0 || minutes > 0) {
      parts.push(`${minutes}m`);
    }
    parts.push(`${seconds}s`);
    return parts.join(" ");
  }

  function formatCountLabel(value, singular, plural) {
    const count = Number(value || 0);
    return `${count} ${count === 1 ? singular : plural}`;
  }

  function clamp(value, minimum, maximum) {
    return Math.min(Math.max(value, minimum), maximum);
  }

  function wrapTileX(x, zoom) {
    const total = 2 ** zoom;
    return ((x % total) + total) % total;
  }

  function mercatorPoint(latitude, longitude, zoom, tileSize) {
    const scale = tileSize * 2 ** zoom;
    const clampedLatitude = clamp(Number(latitude), -85.0511, 85.0511);
    const sinLat = Math.sin((clampedLatitude * Math.PI) / 180);
    const x = ((Number(longitude) + 180) / 360) * scale;
    const y =
      (0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI)) * scale;
    return { x, y };
  }

  function chooseMapCenter(positionedMembers) {
    const preferredMembers = positionedMembers.filter((member) => member.role === "sensor");
    const source = preferredMembers.length ? preferredMembers : positionedMembers;
    const totals = source.reduce(
      (accumulator, member) => {
        accumulator.latitude += Number(member.latitude);
        accumulator.longitude += Number(member.longitude);
        return accumulator;
      },
      { latitude: 0, longitude: 0 },
    );
    return {
      latitude: totals.latitude / source.length,
      longitude: totals.longitude / source.length,
    };
  }

  function chooseMapZoom(positionedMembers, mapStatus, viewportWidth, viewportHeight) {
    const tileSize = Number(mapStatus?.tile_size || 256);
    const availableZooms = Array.isArray(mapStatus?.available_zooms)
      ? mapStatus.available_zooms
          .map((value) => Number(value))
          .filter((value) => Number.isInteger(value) && value >= 0)
          .sort((left, right) => right - left)
      : [];
    if (!availableZooms.length) {
      return 15;
    }

    const center = chooseMapCenter(positionedMembers);
    const usableWidth = Math.max(viewportWidth - 88, tileSize);
    const usableHeight = Math.max(viewportHeight - 88, tileSize);
    let fallbackZoom = availableZooms[availableZooms.length - 1];
    for (const zoom of availableZooms) {
      fallbackZoom = zoom;
      const points = positionedMembers.map((member) =>
        mercatorPoint(member.latitude, member.longitude, zoom, tileSize),
      );
      const xs = points.map((point) => point.x);
      const ys = points.map((point) => point.y);
      const spanWidth = Math.max(...xs) - Math.min(...xs);
      const spanHeight = Math.max(...ys) - Math.min(...ys);
      if (spanWidth <= usableWidth && spanHeight <= usableHeight) {
        return zoom;
      }
    }
    return fallbackZoom;
  }

  function buildTileUrl(template, zoom, x, y) {
    return template
      .replace("{z}", String(zoom))
      .replace("{x}", String(x))
      .replace("{y}", String(y));
  }

  function selectedItem() {
    return state.feedItems.find((item) => itemKey(item) === state.selectedKey) || null;
  }

  function itemKey(item) {
    return `${item.type}:${item.id}`;
  }

  async function fetchJson(path, options) {
    const response = await fetch(path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options && options.headers ? options.headers : {}),
      },
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!response.ok) {
      let message = `${response.status} ${response.statusText}`;
      try {
        const payload = await response.json();
        if (payload.error) {
          message = payload.error;
        }
      } catch (error) {
        // Ignore JSON parse failures and keep the HTTP status text.
      }
      const failure = new Error(message);
      failure.status = response.status;
      throw failure;
    }
    return response.json();
  }

  function buildDashboardQuery() {
    const params = new URLSearchParams();
    params.set("limit", "40");
    for (const type of state.filters.include) {
      params.append("include", type);
    }
    if (state.filters.status) {
      params.set("finding_status", state.filters.status);
    }
    if (state.filters.severity) {
      params.set("severity", state.filters.severity);
    }
    if (state.filters.category) {
      params.set("category", state.filters.category);
    }
    return params.toString();
  }

  function buildDashboardStatePath() {
    const query = buildDashboardQuery();
    return query ? `${bootstrap.paths.dashboard_state}?${query}` : bootstrap.paths.dashboard_state;
  }

  function buildDashboardStreamPath() {
    const query = buildDashboardQuery();
    return query ? `${bootstrap.paths.dashboard_stream}?${query}` : bootstrap.paths.dashboard_stream;
  }

  function setBanner(message, level) {
    if (!message) {
      elements.feedBanner.hidden = true;
      elements.feedBanner.textContent = "";
      elements.feedBanner.classList.remove("is-error");
      return;
    }
    elements.feedBanner.hidden = false;
    elements.feedBanner.textContent = message;
    elements.feedBanner.classList.toggle("is-error", level === "error");
  }

  function updateConnectionState(status, label) {
    elements.connectionIndicator.classList.remove("is-live", "is-error");
    if (status === "live") {
      elements.connectionIndicator.classList.add("is-live");
    } else if (status === "error") {
      elements.connectionIndicator.classList.add("is-error");
    }
    elements.connectionLabel.textContent = label;
  }

  function disconnectStream() {
    if (state.streamHandle) {
      state.streamHandle.close();
      state.streamHandle = null;
    }
    if (state.streamRetryHandle) {
      window.clearTimeout(state.streamRetryHandle);
      state.streamRetryHandle = null;
    }
  }

  function setAuthGateVisible(visible, message) {
    elements.authGate.hidden = !visible;
    document.body.classList.toggle("dashboard-auth-required", visible);
    if (message) {
      elements.authStatus.textContent = message;
    }
    if (visible) {
      disconnectStream();
    }
  }

  function lockDashboard(message) {
    state.authenticated = false;
    setAuthGateVisible(
      true,
      message || "Run `osk dashboard` for a fresh one-time dashboard code.",
    );
    updateConnectionState("error", "Locked");
    elements.refreshLabel.textContent = "Awaiting code";
  }

  function maybeRefreshDetail(previousSelection) {
    const nextSelection = selectedItem();
    if (!nextSelection) {
      void refreshDetail();
      return;
    }
    if (!previousSelection || itemKey(previousSelection) !== itemKey(nextSelection)) {
      void refreshDetail();
      return;
    }
    if ((previousSelection.timestamp || "") !== (nextSelection.timestamp || "")) {
      void refreshDetail();
    }
  }

  function applyDashboardState(snapshot) {
    const previousSelection = selectedItem();
    const previous = new Map(state.feedItems.map((item) => [itemKey(item), item.timestamp]));
    state.feedItems = snapshot.review_feed || [];
    state.latestSitrep = snapshot.latest_sitrep || null;
    state.operationStatus = snapshot.operation_status || null;
    state.intelligenceStatus = snapshot.intelligence_status || null;
    state.members = snapshot.members || [];
    state.memberSummary = snapshot.member_summary || null;
    state.bufferHistory = snapshot.buffer_history || null;
    state.mapStatus = snapshot.map || null;
    state.lastSyncAt = snapshot.generated_at || new Date().toISOString();
    state.freshKeys = new Set(
      state.feedItems
        .filter((item) => previous.get(itemKey(item)) !== item.timestamp)
        .map((item) => itemKey(item)),
    );

    if (!state.selectedKey || !state.feedItems.some((item) => itemKey(item) === state.selectedKey)) {
      state.selectedKey = state.feedItems[0] ? itemKey(state.feedItems[0]) : null;
    }

    renderFeed();
    renderContext();
    maybeRefreshDetail(previousSelection);
    setBanner("", "info");
    updateConnectionState("live", "Live stream");
    elements.refreshLabel.textContent = "Streaming";
    window.setTimeout(() => {
      state.freshKeys.clear();
      renderFeed();
    }, 1800);
  }

  async function syncDashboardSession() {
    const response = await fetch(bootstrap.paths.dashboard_session, {
      method: "GET",
      cache: "no-store",
      credentials: "same-origin",
    });
    let payload = {};
    try {
      payload = await response.json();
    } catch (error) {
      payload = {};
    }

    if (response.ok) {
      state.authenticated = true;
      setAuthGateVisible(false);
      return payload;
    }

    if (response.status === 401) {
      lockDashboard(
        payload.error || "Run `osk dashboard` for a fresh one-time dashboard code.",
      );
      return null;
    }

    const failure = new Error(payload.error || `${response.status} ${response.statusText}`);
    failure.status = response.status;
    throw failure;
  }

  async function submitDashboardCode(event) {
    event.preventDefault();
    const dashboardCode = elements.authCodeInput.value.trim();
    if (!dashboardCode) {
      elements.authStatus.textContent = "Enter the one-time dashboard code from `osk dashboard`.";
      return;
    }

    elements.authStatus.textContent = "Unlocking local dashboard session...";
    elements.authSubmit.disabled = true;
    try {
      await fetchJson(bootstrap.paths.dashboard_session, {
        method: "POST",
        body: JSON.stringify({ dashboard_code: dashboardCode }),
      });
      state.authenticated = true;
      elements.authCodeInput.value = "";
      setAuthGateVisible(false);
      await refreshDashboard();
      connectDashboardStream();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Dashboard login failed";
      lockDashboard(message);
    } finally {
      elements.authSubmit.disabled = false;
    }
  }

  function renderFeed() {
    elements.feedCount.textContent = `${state.feedItems.length} items`;
    elements.lastSync.textContent = state.lastSyncAt
      ? `Synced ${formatTimestamp(state.lastSyncAt)}`
      : "Not synced";

    if (!state.feedItems.length) {
      elements.reviewFeed.innerHTML =
        '<div class="empty-state"><p>No findings, events, or SitReps matched the current filters.</p></div>';
      return;
    }

    elements.reviewFeed.innerHTML = state.feedItems
      .map((item) => {
        const key = itemKey(item);
        const selected = key === state.selectedKey ? " is-selected" : "";
        const fresh = state.freshKeys.has(key) ? " is-fresh" : "";
        const typeClass = `timeline-row--${item.type}`;
        const severity = escapeHtml(item.severity || "");
        const title = escapeHtml(item.title || "Untitled item");
        const summary = escapeHtml(item.summary || "");
        const chips = [];
        if (item.status) {
          chips.push(statusPill(item.status));
        }
        if (item.category) {
          chips.push(`<span class="pill">${escapeHtml(item.category.replaceAll("_", " "))}</span>`);
        }
        if (item.trend) {
          chips.push(`<span class="pill pill--accent">${escapeHtml(item.trend)}</span>`);
        }
        if (item.corroborated) {
          chips.push('<span class="pill pill--accent">Corroborated</span>');
        }
        return `
          <button
            class="timeline-row ${typeClass}${selected}${fresh}"
            data-key="${escapeHtml(key)}"
            data-severity="${severity}"
            type="button"
          >
            <div class="timeline-row__top">
              <span>${escapeHtml(item.type.toUpperCase())}</span>
              <span>${formatTimestamp(item.timestamp)}</span>
            </div>
            <h3 class="timeline-row__title">${title}</h3>
            <p class="timeline-row__summary">${summary}</p>
            <div class="timeline-row__meta">${chips.join("")}</div>
          </button>
        `;
      })
      .join("");

    for (const button of elements.reviewFeed.querySelectorAll(".timeline-row")) {
      button.addEventListener("click", () => {
        state.selectedKey = button.dataset.key;
        renderFeed();
        void refreshDetail();
      });
    }
  }

  function statusPill(status) {
    const value = String(status);
    const className = value === "resolved" ? "pill pill--resolved" : "pill pill--warning";
    return `<span class="${className}">${escapeHtml(value)}</span>`;
  }

  function findingActionEnabled(action, status) {
    if (action === "acknowledge") {
      return status === "open";
    }
    if (action === "resolve") {
      return status !== "resolved";
    }
    if (action === "reopen") {
      return status !== "open";
    }
    return true;
  }

  async function refreshDashboard() {
    if (!state.authenticated) {
      setBanner("Dashboard login required before review data can load.", "error");
      updateConnectionState("error", "Locked");
      return;
    }
    if (state.refreshInFlight) {
      return;
    }
    state.refreshInFlight = true;
    elements.refreshLabel.textContent = "Refreshing";
    updateConnectionState("pending", "Refreshing");

    try {
      const snapshot = await fetchJson(buildDashboardStatePath(), {
        method: "GET",
      });
      applyDashboardState(snapshot);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Dashboard refresh failed";
      if (error && (error.status === 401 || error.status === 403)) {
        lockDashboard("Dashboard session expired. Run `osk dashboard` for a fresh one-time code.");
      }
      setBanner(message, "error");
      updateConnectionState("error", "Refresh failed");
      elements.refreshLabel.textContent = "Retry needed";
    } finally {
      state.refreshInFlight = false;
    }
  }

  async function refreshDetail() {
    const item = selectedItem();
    if (!item) {
      elements.detailTitle.textContent = "Waiting for data";
      elements.detailMeta.textContent = "Choose a finding, event, or SitRep.";
      elements.detailStage.innerHTML =
        '<div class="empty-state"><p>Select a review item to inspect its context and triage controls.</p></div>';
      elements.findingActions.hidden = true;
      elements.findingNoteForm.hidden = true;
      elements.selectionEcho.textContent =
        "The detail pane tracks the current feed selection and refreshes against the live API.";
      return;
    }

    elements.detailTitle.textContent = item.title || "Selected item";
    elements.detailMeta.textContent = `${item.type.toUpperCase()} • ${formatLongTimestamp(item.timestamp)}`;
    elements.selectionEcho.textContent = `${item.type.toUpperCase()} selected: ${item.title}`;

    if (item.type !== "finding") {
      renderNonFindingDetail(item);
      elements.findingActions.hidden = true;
      elements.findingNoteForm.hidden = true;
      return;
    }

    const [detail, correlations] = await Promise.all([
      fetchJson(`${bootstrap.paths.findings}/${item.finding_id}`, {
        method: "GET",
      }),
      fetchJson(`${bootstrap.paths.findings}/${item.finding_id}/correlations?limit=6`, {
        method: "GET",
      }),
    ]);
    state.detail = detail;
    state.correlations = correlations;
    renderFindingDetail(detail, correlations);
  }

  function renderNonFindingDetail(item) {
    const summary = escapeHtml(item.summary || "No summary available.");
    const timestamp = formatLongTimestamp(item.timestamp);
    const categoryLine = item.category
      ? `<div><dt>Category</dt><dd>${escapeHtml(item.category.replaceAll("_", " "))}</dd></div>`
      : "";
    const trendLine = item.trend
      ? `<div><dt>Trend</dt><dd>${escapeHtml(item.trend)}</dd></div>`
      : "";
    elements.detailStage.innerHTML = `
      <div class="detail-card">
        <div class="detail-header">
          <div class="timeline-row__meta">
            <span class="pill">${escapeHtml(item.type)}</span>
          </div>
          <p class="detail-summary">${summary}</p>
        </div>
        <dl class="detail-grid">
          <div><dt>Recorded</dt><dd>${timestamp}</dd></div>
          ${categoryLine}
          ${trendLine}
        </dl>
      </div>
    `;
  }

  function renderFindingDetail(detail, correlations) {
    const finding = detail.finding;
    const notes = detail.notes || [];
    const observations = detail.observations || [];
    const events = detail.events || [];
    const relatedFindings = correlations.related_findings || [];
    const relatedEvents = correlations.related_events || [];

    elements.detailStage.innerHTML = `
      <div class="detail-card">
        <div class="detail-header">
          <div class="timeline-row__meta">
            <span class="pill pill--warning">${escapeHtml(finding.status)}</span>
            <span class="pill">${escapeHtml(finding.category.replaceAll("_", " "))}</span>
            <span class="pill">${escapeHtml(finding.severity)}</span>
            ${finding.corroborated ? '<span class="pill pill--accent">Corroborated</span>' : ""}
          </div>
          <p class="detail-summary">${escapeHtml(finding.summary)}</p>
        </div>

        <dl class="detail-grid">
          <div><dt>First seen</dt><dd>${formatLongTimestamp(finding.first_seen_at)}</dd></div>
          <div><dt>Last seen</dt><dd>${formatLongTimestamp(finding.last_seen_at)}</dd></div>
          <div><dt>Sources</dt><dd>${escapeHtml(finding.source_count)}</dd></div>
          <div><dt>Signals</dt><dd>${escapeHtml(finding.signal_count)}</dd></div>
          <div><dt>Observations</dt><dd>${escapeHtml(finding.observation_count)}</dd></div>
          <div><dt>Notes</dt><dd>${escapeHtml(finding.notes_count)}</dd></div>
        </dl>

        <section class="detail-section">
          <h3>Linked events</h3>
          <div class="detail-list">
            ${
              events.length
                ? events
                    .map(
                      (event) => `
                        <div class="detail-item">
                          <p>${escapeHtml(event.text || "No event text")}</p>
                          <small>${escapeHtml(event.category)} • ${escapeHtml(event.severity)}</small>
                        </div>
                      `,
                    )
                    .join("")
                : '<div class="detail-item"><p>No linked events recorded.</p></div>'
            }
          </div>
        </section>

        <section class="detail-section">
          <h3>Observation context</h3>
          <div class="detail-list">
            ${
              observations.length
                ? observations
                    .slice(0, 4)
                    .map(
                      (observation) => `
                        <div class="detail-item">
                          <p>${escapeHtml(observation.summary || "No observation summary")}</p>
                          <small>${escapeHtml(observation.kind || "unknown")} • ${formatLongTimestamp(observation.created_at)}</small>
                        </div>
                      `,
                    )
                    .join("")
                : '<div class="detail-item"><p>No linked observations recorded.</p></div>'
            }
          </div>
        </section>

        <section class="detail-section">
          <h3>Correlations</h3>
          <div class="detail-list">
            ${
              relatedFindings.length || relatedEvents.length
                ? [
                    ...relatedFindings.map(
                      (item) => `
                        <div class="detail-item">
                          <p>${escapeHtml(item.title || "Related finding")}</p>
                          <small>Finding • ${escapeHtml((item.correlation_reasons || []).join(", "))}</small>
                        </div>
                      `,
                    ),
                    ...relatedEvents.map(
                      (item) => `
                        <div class="detail-item">
                          <p>${escapeHtml(item.text || "Related event")}</p>
                          <small>Event • ${escapeHtml((item.correlation_reasons || []).join(", "))}</small>
                        </div>
                      `,
                    ),
                  ].join("")
                : '<div class="detail-item"><p>No correlated findings or events in the current window.</p></div>'
            }
          </div>
        </section>

        <section class="detail-section">
          <h3>Coordinator notes</h3>
          <div class="detail-list">
            ${
              notes.length
                ? notes
                    .map(
                      (note) => `
                        <div class="detail-item">
                          <p>${escapeHtml(note.text || "")}</p>
                          <small>${formatLongTimestamp(note.created_at)}</small>
                        </div>
                      `,
                    )
                    .join("")
                : '<div class="detail-item"><p>No notes yet.</p></div>'
            }
          </div>
        </section>
      </div>
    `;

    elements.findingActions.hidden = false;
    for (const button of elements.findingActions.querySelectorAll("button")) {
      const action = button.dataset.findingAction;
      button.disabled = !findingActionEnabled(action, finding.status);
    }
    elements.findingNoteForm.hidden = false;
    elements.noteStatus.textContent = `Selected finding ${finding.id}`;
  }

  async function postFindingAction(action) {
    const item = selectedItem();
    if (!item || item.type !== "finding") {
      return;
    }
    try {
      await fetchJson(`${bootstrap.paths.findings}/${item.finding_id}/${action}`, {
        method: "POST",
      });
      await refreshDashboard();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Action failed";
      setBanner(message, "error");
    }
  }

  async function submitFindingNote(event) {
    event.preventDefault();
    const item = selectedItem();
    const noteText = elements.findingNoteInput.value.trim();
    if (!item || item.type !== "finding" || !noteText) {
      return;
    }
    try {
      elements.noteStatus.textContent = "Saving note...";
      await fetchJson(`${bootstrap.paths.findings}/${item.finding_id}/notes`, {
        method: "POST",
        body: JSON.stringify({ text: noteText }),
      });
      elements.findingNoteInput.value = "";
      elements.noteStatus.textContent = "Note saved.";
      await refreshDashboard();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not add note";
      elements.noteStatus.textContent = message;
      setBanner(message, "error");
    }
  }

  function renderContext() {
    if (state.operationStatus) {
      elements.metricMembers.textContent = state.operationStatus.members ?? "--";
      elements.metricSensors.textContent = state.operationStatus.sensors ?? "--";
      elements.metricConnected.textContent = state.operationStatus.connected ?? "--";
      elements.operationName.textContent = state.operationStatus.name || "Coordinator Review";
      elements.operationSubtitle.textContent =
        `${state.operationStatus.id} • ${state.operationStatus.connected} active connections`;
      elements.startedAt.textContent = formatLongTimestamp(state.operationStatus.started_at);
      elements.uptime.textContent = formatUptime(state.operationStatus.started_at);
    }

    if (state.latestSitrep) {
      const prefix = state.latestSitrep.trend ? `${state.latestSitrep.trend.toUpperCase()} • ` : "";
      elements.latestSitrep.textContent = `${prefix}${state.latestSitrep.text || "No situation reports yet."}`;
    }

    const memberSummary = state.memberSummary || {};
    elements.memberSummary.innerHTML = [
      ["Fresh", memberSummary.fresh ?? "--"],
      ["Buffered", memberSummary.buffered_members ?? "--"],
      ["Stale", memberSummary.stale ?? "--"],
      ["Disconnected", memberSummary.disconnected ?? "--"],
    ]
      .map(
        ([label, value]) =>
          `<div class="stack-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`,
      )
      .join("");

    renderBufferTrend();

    elements.memberHealth.innerHTML = state.members.length
      ? state.members
          .slice()
          .sort((left, right) => {
            return Number(left.seconds_since_last_seen || 0) - Number(right.seconds_since_last_seen || 0);
          })
          .slice(0, 6)
          .map((member) => {
            const bufferStatus = member.buffer_status || {};
            const pendingCount = Number(bufferStatus.pending_count || 0);
            const bufferDetail = pendingCount
              ? ` • ${pendingCount} buffered (${Number(bufferStatus.sensor_pending_count || 0)} sensor / ${Number(bufferStatus.manual_pending_count || 0)} manual)`
              : "";
            const networkDetail =
              pendingCount && bufferStatus.network ? ` • browser ${bufferStatus.network}` : "";
            const errorDetail =
              pendingCount && bufferStatus.last_error
                ? `<br /><small>${escapeHtml(bufferStatus.last_error)}</small>`
                : "";
            return `
              <div class="detail-item">
                <p>${escapeHtml(member.name)} <span class="pill">${escapeHtml(member.role)}</span></p>
                <small>
                  ${escapeHtml(member.heartbeat_state)} • last seen ${escapeHtml(member.last_seen_at)}${escapeHtml(bufferDetail)}${escapeHtml(networkDetail)}
                </small>
                ${errorDetail}
              </div>
            `;
          })
          .join("")
      : '<div class="detail-item"><p>No member telemetry yet.</p></div>';

    renderFieldMap();

    if (state.intelligenceStatus) {
      elements.pipelineStatus.innerHTML = [
        ["Transcriber", state.intelligenceStatus.transcriber?.backend || "--"],
        ["Vision", state.intelligenceStatus.vision?.backend || "--"],
        ["Location", state.intelligenceStatus.location?.backend || "--"],
        ["Synthesizer", state.intelligenceStatus.synthesizer?.backend || "--"],
      ]
        .map(
          ([label, value]) =>
            `<div class="stack-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`,
        )
        .join("");

      const audio = state.intelligenceStatus.audio_ingest || {};
      const frame = state.intelligenceStatus.frame_ingest || {};
      const recentFindings = (state.intelligenceStatus.recent_findings || []).length;
      const bufferedMembers = state.memberSummary?.buffered_members ?? "--";
      const bufferedItems = state.memberSummary?.buffered_items ?? "--";
      elements.ingestPressure.innerHTML = [
        [
          "Audio queue",
          `${escapeHtml(audio.queue_size ?? "--")} queued / ${escapeHtml(audio.accepted_chunks ?? "--")} accepted`,
        ],
        [
          "Frame queue",
          `${escapeHtml(frame.queue_size ?? "--")} queued / ${escapeHtml(frame.accepted_frames ?? "--")} accepted`,
        ],
        [
          "Member buffers",
          `${escapeHtml(bufferedMembers)} members / ${escapeHtml(bufferedItems)} items`,
        ],
        ["Recent findings", escapeHtml(recentFindings)],
      ]
        .map(
          ([label, value]) =>
            `<div class="stack-row"><span>${escapeHtml(label)}</span><strong>${value}</strong></div>`,
        )
        .join("");
    }
  }

  function renderBufferTrend() {
    const history = state.bufferHistory || {};
    const points = Array.isArray(history.points) ? history.points : [];
    if (!points.length) {
      elements.bufferTrendSummary.innerHTML =
        '<div class="stack-row"><span>Trend</span><strong>--</strong></div>';
      elements.bufferTrendChart.innerHTML =
        '<div class="empty-state empty-state--compact"><p>Waiting for buffer history.</p></div>';
      return;
    }

    const trendLabels = {
      rising: "Rising",
      falling: "Clearing",
      steady: "Steady",
    };
    const trend = trendLabels[history.trend] || "Steady";
    const changeItems = Number(history.change_items || 0);
    const maxBuffered = Math.max(
      1,
      ...points.map((point) => Number(point.buffered_items || 0)),
    );
    const currentPoint = points[points.length - 1] || {};
    const bars = points
      .map((point, index) => {
        const bufferedItems = Number(point.buffered_items || 0);
        const audioQueueSize = Number(point.audio_queue_size || 0);
        const frameQueueSize = Number(point.frame_queue_size || 0);
        const height = `${Math.max(12, Math.round((bufferedItems / maxBuffered) * 100))}%`;
        const isLatest = index === points.length - 1;
        const tooltip =
          `${formatTimestamp(point.generated_at)} • ` +
          `${formatCountLabel(bufferedItems, "buffered item", "buffered items")} • ` +
          `${formatCountLabel(point.buffered_members, "member", "members")} • ` +
          `audio ${audioQueueSize} • frame ${frameQueueSize}`;
        return `
          <span
            class="buffer-trend__bar${bufferedItems > 0 ? " is-buffered" : ""}${isLatest ? " is-latest" : ""}"
            style="height: ${height}"
            title="${escapeHtml(tooltip)}"
          ></span>
        `;
      })
      .join("");

    elements.bufferTrendSummary.innerHTML = [
      ["Trend", trend],
      ["Current", formatCountLabel(history.current_buffered_items, "item", "items")],
      [
        "Peak",
        `${formatCountLabel(history.peak_buffered_items, "item", "items")} / ${formatCountLabel(history.peak_buffered_members, "member", "members")}`,
      ],
      [
        "Window",
        `${formatCountLabel(history.window_points, "sample", "samples")} (${changeItems >= 0 ? "+" : ""}${changeItems})`,
      ],
    ]
      .map(
        ([label, value]) =>
          `<div class="stack-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`,
      )
      .join("");

    elements.bufferTrendChart.innerHTML = `
      <div class="buffer-trend">
        <div class="buffer-trend__bars" aria-label="Member buffer trend over recent dashboard samples">
          ${bars}
        </div>
        <div class="buffer-trend__meta">
          <span>${escapeHtml(formatTimestamp(history.window_started_at))}</span>
          <span>${escapeHtml(formatTimestamp(history.window_ended_at))}</span>
        </div>
      </div>
    `;
  }

  function renderFieldMap() {
    const positionedMembers = state.members.filter(
      (member) => member.latitude !== null && member.longitude !== null,
    );
    if (!positionedMembers.length) {
      elements.memberMapStatus.textContent = "Waiting for live GPS fixes.";
      elements.memberMapViewport.innerHTML =
        '<div class="empty-state empty-state--compact"><p>No live member positions yet.</p></div>';
      return;
    }

    const mapStatus = state.mapStatus || {};
    if (!mapStatus.available || !mapStatus.tile_template) {
      elements.memberMapStatus.textContent =
        "No cached local tiles available yet. Showing relative positions only.";
      renderRelativeFieldMap(positionedMembers);
      return;
    }

    elements.memberMapStatus.textContent =
      "Offline tile cache active. The map uses locally cached tiles and falls back to marker geometry when coverage is incomplete.";
    renderTileFieldMap(positionedMembers, mapStatus);
  }

  function renderRelativeFieldMap(positionedMembers) {
    const width = 320;
    const height = 180;
    const padding = 22;
    const latitudes = positionedMembers.map((member) => Number(member.latitude));
    const longitudes = positionedMembers.map((member) => Number(member.longitude));
    const minLat = Math.min(...latitudes);
    const maxLat = Math.max(...latitudes);
    const minLon = Math.min(...longitudes);
    const maxLon = Math.max(...longitudes);
    const latSpan = maxLat - minLat || 0.0002;
    const lonSpan = maxLon - minLon || 0.0002;

    const gridLines = [0.25, 0.5, 0.75]
      .map((ratio) => {
        const x = padding + (width - padding * 2) * ratio;
        const y = padding + (height - padding * 2) * ratio;
        return `
          <line class="tile-map__grid-line" x1="${x}" y1="${padding}" x2="${x}" y2="${height - padding}"></line>
          <line class="tile-map__grid-line" x1="${padding}" y1="${y}" x2="${width - padding}" y2="${y}"></line>
        `;
      })
      .join("");

    const members = positionedMembers
      .map((member) => {
        const x =
          padding +
          ((Number(member.longitude) - minLon) / lonSpan) * (width - padding * 2);
        const y =
          height -
          padding -
          ((Number(member.latitude) - minLat) / latSpan) * (height - padding * 2);
        const heartbeatClass =
          member.heartbeat_state === "fresh" ? "" : ` tile-map__relative-dot--${member.heartbeat_state}`;
        return `
          <g>
            <circle
              class="tile-map__relative-dot tile-map__relative-dot--${escapeHtml(member.role)}${heartbeatClass}"
              cx="${x.toFixed(1)}"
              cy="${y.toFixed(1)}"
              r="7"
            ></circle>
            <text class="tile-map__relative-label" x="${(x + 10).toFixed(1)}" y="${(y - 10).toFixed(1)}">
              ${escapeHtml(member.name)}
            </text>
          </g>
        `;
      })
      .join("");

    elements.memberMapViewport.innerHTML = `
      <div class="tile-map">
        <div class="tile-map__meta">
          <span class="map-chip">Relative fallback</span>
          <span class="map-chip">${escapeHtml(positionedMembers.length)} positioned</span>
        </div>
        <div class="tile-map__viewport tile-map__viewport--fallback">
          <svg class="tile-map__relative-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Relative member positions">
            <rect x="${padding}" y="${padding}" width="${width - padding * 2}" height="${height - padding * 2}" fill="transparent" stroke="rgba(159, 184, 214, 0.22)" />
            ${gridLines}
            ${members}
          </svg>
          <div class="tile-map__badge is-fallback">Fallback</div>
        </div>
      </div>
    `;
  }

  function renderTileFieldMap(positionedMembers, mapStatus) {
    const tileSize = Number(mapStatus.tile_size || 256);
    const viewportWidth = Math.max(elements.memberMapViewport.clientWidth - 2, 320);
    const viewportHeight = Math.max(Math.round(viewportWidth * 0.66), 220);
    const center = chooseMapCenter(positionedMembers);
    const zoom = chooseMapZoom(positionedMembers, mapStatus, viewportWidth, viewportHeight);
    const centerPoint = mercatorPoint(center.latitude, center.longitude, zoom, tileSize);
    const originX = centerPoint.x - viewportWidth / 2;
    const originY = centerPoint.y - viewportHeight / 2;
    const startTileX = Math.floor(originX / tileSize);
    const endTileX = Math.floor((originX + viewportWidth) / tileSize);
    const startTileY = Math.floor(originY / tileSize);
    const endTileY = Math.floor((originY + viewportHeight) / tileSize);
    const totalTiles = 2 ** zoom;

    const tiles = [];
    for (let tileY = startTileY; tileY <= endTileY; tileY += 1) {
      if (tileY < 0 || tileY >= totalTiles) {
        continue;
      }
      for (let tileX = startTileX; tileX <= endTileX; tileX += 1) {
        const wrappedX = wrapTileX(tileX, zoom);
        const left = tileX * tileSize - originX;
        const top = tileY * tileSize - originY;
        tiles.push(`
          <img
            class="tile-map__tile"
            data-role="map-tile"
            alt=""
            loading="lazy"
            src="${escapeHtml(buildTileUrl(mapStatus.tile_template, zoom, wrappedX, tileY))}"
            style="left:${left.toFixed(1)}px; top:${top.toFixed(1)}px;"
          />
        `);
      }
    }

    const markers = positionedMembers
      .map((member) => {
        const point = mercatorPoint(member.latitude, member.longitude, zoom, tileSize);
        const left = point.x - originX;
        const top = point.y - originY;
        const heartbeatClass =
          member.heartbeat_state === "fresh" ? "" : ` tile-map__marker--${member.heartbeat_state}`;
        return `
          <div
            class="tile-map__marker tile-map__marker--${escapeHtml(member.role)}${heartbeatClass}"
            style="left:${left.toFixed(1)}px; top:${top.toFixed(1)}px;"
            title="${escapeHtml(member.name)}"
          ></div>
          <div class="tile-map__label" style="left:${left.toFixed(1)}px; top:${top.toFixed(1)}px;">
            ${escapeHtml(member.name)}
          </div>
        `;
      })
      .join("");

    elements.memberMapViewport.innerHTML = `
      <div class="tile-map">
        <div class="tile-map__meta">
          <span class="map-chip">Offline tiles</span>
          <span class="map-chip">z${escapeHtml(zoom)}</span>
          <span class="map-chip">${escapeHtml(positionedMembers.length)} positioned</span>
        </div>
        <div class="tile-map__viewport">
          <div class="tile-map__surface" style="--map-height:${viewportHeight}px;">
            <div class="tile-map__tile-layer">
              ${tiles.join("")}
            </div>
            <div class="tile-map__marker-layer">
              ${markers}
            </div>
            <div class="tile-map__badge">Local cache</div>
            <div class="tile-map__status" data-role="tile-status" hidden></div>
          </div>
        </div>
      </div>
    `;

    const tileImages = Array.from(
      elements.memberMapViewport.querySelectorAll("img[data-role='map-tile']"),
    );
    const statusNode = elements.memberMapViewport.querySelector("[data-role='tile-status']");
    let tileHits = 0;
    let tileMisses = 0;

    function updateTileStatus() {
      if (!statusNode) {
        return;
      }
      if (!tileImages.length) {
        statusNode.hidden = false;
        statusNode.textContent =
          "No tile coverage intersects the current viewport. Showing member markers only.";
        return;
      }
      if (tileHits === 0 && tileMisses === tileImages.length) {
        statusNode.hidden = false;
        statusNode.textContent =
          "Cached tiles were not found for the current area. Marker positions are still live.";
        return;
      }
      if (tileMisses > 0) {
        statusNode.hidden = false;
        statusNode.textContent =
          "Partial local tile coverage. Missing tiles are omitted while markers stay live.";
        return;
      }
      statusNode.hidden = true;
    }

    for (const tile of tileImages) {
      tile.addEventListener("load", () => {
        tile.classList.add("is-loaded");
        tileHits += 1;
        updateTileStatus();
      });
      tile.addEventListener("error", () => {
        tile.classList.add("is-missing");
        tileMisses += 1;
        updateTileStatus();
      });
    }
    updateTileStatus();
  }

  function handleFilterChange() {
    const formData = new FormData(elements.filterForm);
    state.filters = {
      include: formData.getAll("include"),
      status: String(formData.get("status") || ""),
      severity: String(formData.get("severity") || ""),
      category: String(formData.get("category") || ""),
    };
    void refreshDashboard();
    connectDashboardStream();
  }

  function scheduleStreamReconnect() {
    if (state.streamRetryHandle || !state.authenticated) {
      return;
    }
    state.streamRetryHandle = window.setTimeout(async () => {
      state.streamRetryHandle = null;
      try {
        const payload = await syncDashboardSession();
        if (!payload) {
          return;
        }
        await refreshDashboard();
        connectDashboardStream();
      } catch (error) {
        const message = error instanceof Error ? error.message : "Stream reconnect failed";
        setBanner(message, "error");
        updateConnectionState("error", "Stream offline");
        scheduleStreamReconnect();
      }
    }, 1500);
  }

  function connectDashboardStream() {
    if (!state.authenticated) {
      return;
    }
    disconnectStream();
    const stream = new EventSource(buildDashboardStreamPath(), { withCredentials: true });
    state.streamHandle = stream;

    stream.addEventListener("snapshot", (event) => {
      const payload = JSON.parse(event.data || "{}");
      applyDashboardState(payload);
    });

    stream.addEventListener("ping", () => {
      updateConnectionState("live", "Live stream");
      elements.refreshLabel.textContent = "Streaming";
    });

    stream.addEventListener("auth_required", (event) => {
      const payload = JSON.parse(event.data || "{}");
      lockDashboard(
        payload.error || "Dashboard session expired. Run `osk dashboard` for a fresh one-time code.",
      );
    });

    stream.onerror = () => {
      if (!state.authenticated) {
        return;
      }
      updateConnectionState("pending", "Stream reconnecting");
      elements.refreshLabel.textContent = "Reconnecting";
      if (state.streamHandle) {
        state.streamHandle.close();
        state.streamHandle = null;
      }
      scheduleStreamReconnect();
    };
  }

  function bindEvents() {
    elements.authForm.addEventListener("submit", (event) => {
      void submitDashboardCode(event);
    });
    elements.refreshButton.addEventListener("click", () => {
      void refreshDashboard();
    });
    elements.filterForm.addEventListener("change", handleFilterChange);
    elements.findingNoteForm.addEventListener("submit", submitFindingNote);
    for (const button of elements.findingActions.querySelectorAll("button")) {
      button.addEventListener("click", () => {
        const action = button.dataset.findingAction;
        void postFindingAction(action);
      });
    }
  }

  async function initializeShell() {
    try {
      const payload = await syncDashboardSession();
      if (payload) {
        await refreshDashboard();
        connectDashboardStream();
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Could not initialize dashboard session";
      setBanner(message, "error");
      updateConnectionState("error", "Session check failed");
    }
  }

  function init() {
    document.title = "Osk | Coordinator Review";
    bindEvents();
    renderContext();
    renderFeed();
    void initializeShell();
    window.setInterval(() => {
      if (state.operationStatus && state.operationStatus.started_at) {
        elements.uptime.textContent = formatUptime(state.operationStatus.started_at);
      }
    }, 1000);
  }

  init();
})();
