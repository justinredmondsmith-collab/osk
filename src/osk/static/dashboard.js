(function () {
  const bootstrapNode = document.getElementById("osk-dashboard-bootstrap");
  if (!bootstrapNode) {
    return;
  }

  const bootstrap = JSON.parse(bootstrapNode.textContent || "{}");
  const state = {
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
    operationStatus: null,
    intelligenceStatus: null,
    lastSyncAt: null,
    freshKeys: new Set(),
    pollHandle: null,
    refreshInFlight: false,
  };

  const elements = {
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
    latestSitrep: document.getElementById("latest-sitrep"),
    pipelineStatus: document.getElementById("pipeline-status"),
    selectionEcho: document.getElementById("selection-echo"),
  };

  const authHeaders = {
    Authorization: `Bearer ${bootstrap.api_token}`,
    "Content-Type": "application/json",
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
        ...authHeaders,
        ...(options && options.headers ? options.headers : {}),
      },
      cache: "no-store",
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
      throw new Error(message);
    }
    return response.json();
  }

  function buildReviewFeedPath() {
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
    return `${bootstrap.paths.review_feed}?${params.toString()}`;
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
    if (state.refreshInFlight) {
      return;
    }
    state.refreshInFlight = true;
    elements.refreshLabel.textContent = "Refreshing";
    updateConnectionState("pending", "Refreshing");

    try {
      const previous = new Map(state.feedItems.map((item) => [itemKey(item), item.timestamp]));
      const [feedResult, sitrepResult, operationResult, intelligenceResult] = await Promise.allSettled([
        fetchJson(buildReviewFeedPath(), {
          method: "GET",
          headers: { Authorization: authHeaders.Authorization },
        }),
        fetchJson(bootstrap.paths.latest_sitrep, {
          method: "GET",
          headers: { Authorization: authHeaders.Authorization },
        }),
        fetchJson(bootstrap.paths.operation_status, {
          method: "GET",
          headers: { Authorization: authHeaders.Authorization },
        }),
        fetchJson(bootstrap.paths.intelligence_status, {
          method: "GET",
          headers: { Authorization: authHeaders.Authorization },
        }),
      ]);

      if (feedResult.status !== "fulfilled") {
        throw feedResult.reason;
      }
      if (operationResult.status !== "fulfilled") {
        throw operationResult.reason;
      }

      const feedItems = feedResult.value;
      const operationStatus = operationResult.value;
      const latestSitrep = sitrepResult.status === "fulfilled" ? sitrepResult.value : state.latestSitrep;
      const intelligenceStatus =
        intelligenceResult.status === "fulfilled"
          ? intelligenceResult.value
          : state.intelligenceStatus;

      state.feedItems = feedItems;
      state.latestSitrep = latestSitrep;
      state.operationStatus = operationStatus;
      state.intelligenceStatus = intelligenceStatus;
      state.lastSyncAt = new Date().toISOString();
      state.freshKeys = new Set(
        feedItems
          .filter((item) => previous.get(itemKey(item)) !== item.timestamp)
          .map((item) => itemKey(item)),
      );

      if (!state.selectedKey || !state.feedItems.some((item) => itemKey(item) === state.selectedKey)) {
        state.selectedKey = state.feedItems[0] ? itemKey(state.feedItems[0]) : null;
      }

      renderFeed();
      renderContext();
      await refreshDetail();
      setBanner("", "info");
      updateConnectionState("live", "Connected");
      elements.refreshLabel.textContent = `Every ${Math.round(bootstrap.poll_interval_ms / 1000)}s`;
      window.setTimeout(() => {
        state.freshKeys.clear();
        renderFeed();
      }, 1800);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Dashboard refresh failed";
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
        headers: { Authorization: authHeaders.Authorization },
      }),
      fetchJson(`${bootstrap.paths.findings}/${item.finding_id}/correlations?limit=6`, {
        method: "GET",
        headers: { Authorization: authHeaders.Authorization },
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
        headers: { Authorization: authHeaders.Authorization },
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
        headers: { Authorization: authHeaders.Authorization },
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
      elements.operationName.textContent = state.operationStatus.name || bootstrap.operation.name;
      elements.operationSubtitle.textContent =
        `${state.operationStatus.id} • ${state.operationStatus.connected} active connections`;
    }

    elements.startedAt.textContent = formatLongTimestamp(bootstrap.operation.started_at);
    elements.uptime.textContent = formatUptime(bootstrap.operation.started_at);

    if (state.latestSitrep) {
      const prefix = state.latestSitrep.trend ? `${state.latestSitrep.trend.toUpperCase()} • ` : "";
      elements.latestSitrep.textContent = `${prefix}${state.latestSitrep.text || "No situation reports yet."}`;
    }

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
    }
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
  }

  function stripQueryToken() {
    const url = new URL(window.location.href);
    if (!url.searchParams.has("token")) {
      return;
    }
    url.searchParams.delete("token");
    window.history.replaceState({}, document.title, url.toString());
  }

  function startPolling() {
    if (state.pollHandle) {
      window.clearInterval(state.pollHandle);
    }
    state.pollHandle = window.setInterval(() => {
      void refreshDashboard();
    }, bootstrap.poll_interval_ms || 10000);
  }

  function bindEvents() {
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

  function init() {
    document.title = `Osk | ${bootstrap.operation.name}`;
    stripQueryToken();
    bindEvents();
    renderContext();
    renderFeed();
    startPolling();
    void refreshDashboard();
    window.setInterval(() => {
      elements.uptime.textContent = formatUptime(bootstrap.operation.started_at);
    }, 1000);
  }

  init();
})();
