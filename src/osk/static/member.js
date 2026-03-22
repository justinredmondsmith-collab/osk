(function () {
  const bootstrapNode = document.getElementById("osk-member-bootstrap");
  if (!bootstrapNode) {
    return;
  }

  const bootstrap = JSON.parse(bootstrapNode.textContent || "{}");
  const storageKeys = {
    memberId: "osk_member_id",
    memberName: "osk_member_name",
    resumeToken: "osk_member_resume_token",
  };

  const state = {
    socket: null,
    session: null,
    feed: [],
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
    runtimeDisplayName: document.getElementById("runtime-display-name"),
    runtimeRole: document.getElementById("runtime-role"),
    runtimeMemberId: document.getElementById("runtime-member-id"),
    runtimeSessionState: document.getElementById("runtime-session-state"),
    runtimeFeed: document.getElementById("runtime-feed"),
    runtimeLeave: document.getElementById("runtime-leave"),
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
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

  function hasResumeState() {
    return Boolean(
      sessionStorage.getItem(storageKeys.memberId) &&
        sessionStorage.getItem(storageKeys.resumeToken),
    );
  }

  function clearLocalMemberState() {
    sessionStorage.removeItem(storageKeys.memberId);
    sessionStorage.removeItem(storageKeys.memberName);
    sessionStorage.removeItem(storageKeys.resumeToken);
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
    try {
      await fetchJson(bootstrap.paths.member_session, { method: "DELETE" });
    } catch (error) {
      // Ignore remote clear failures and still clear browser state.
    }
    clearLocalMemberState();
    window.location.href = bootstrap.paths.join_page;
  }

  function setConnectionState(status, label) {
    if (!elements.runtimeConnectionDot || !elements.runtimeConnectionLabel) {
      return;
    }
    elements.runtimeConnectionDot.classList.remove("is-live", "is-error");
    if (status === "live") {
      elements.runtimeConnectionDot.classList.add("is-live");
    } else if (status === "error") {
      elements.runtimeConnectionDot.classList.add("is-error");
    }
    elements.runtimeConnectionLabel.textContent = label;
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
    state.feed = state.feed.slice(0, 12);
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
      .map((entry) => {
        return `
          <div class="member-feed-item member-feed-item--${escapeHtml(entry.kind)}">
            <p>${escapeHtml(entry.message)}</p>
            <small>${escapeHtml(new Date(entry.timestamp).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }))}</small>
          </div>
        `;
      })
      .join("");
  }

  function connectMemberSocket() {
    const memberName = readStoredName() || "Observer";
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const socketUrl = `${protocol}://${window.location.host}${bootstrap.paths.websocket}`;
    const socket = new WebSocket(socketUrl);
    state.socket = socket;

    socket.addEventListener("open", () => {
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

      if (payload.type === "auth_ok") {
        sessionStorage.setItem(storageKeys.memberId, String(payload.member_id || ""));
        sessionStorage.setItem(storageKeys.resumeToken, String(payload.resume_token || ""));
        if (elements.runtimeMemberId) {
          elements.runtimeMemberId.textContent = String(payload.member_id || "--");
        }
        if (elements.runtimeRole) {
          elements.runtimeRole.textContent = String(payload.role || "observer");
        }
        if (elements.runtimeSessionState) {
          elements.runtimeSessionState.textContent = payload.resumed ? "Resumed" : "Joined";
        }
        setConnectionState("live", payload.resumed ? "Resumed" : "Connected");
        pushFeed(
          payload.resumed
            ? "Member session resumed."
            : "Member session established.",
          "success",
        );
        return;
      }

      if (payload.type === "role_change") {
        if (elements.runtimeRole) {
          elements.runtimeRole.textContent = String(payload.role || "--");
        }
        pushFeed(`Role updated to ${payload.role}.`);
        return;
      }

      if (payload.type === "alert") {
        pushFeed(payload.text || "Received alert.", payload.severity || "warning");
        return;
      }

      if (payload.type === "status") {
        if (elements.runtimeSessionState) {
          elements.runtimeSessionState.textContent = "Live";
        }
        pushFeed("Operation status updated.");
        return;
      }

      if (payload.type === "ping") {
        socket.send(JSON.stringify({ type: "pong" }));
        return;
      }

      if (payload.type === "wipe" || payload.type === "op_ended") {
        pushFeed("Operation ended. Clearing local member session.", "critical");
        setConnectionState("error", "Ended");
        window.setTimeout(() => {
          void clearMemberSession();
        }, 250);
        return;
      }

      if (payload.type) {
        pushFeed(`Received ${payload.type}.`);
      }
    });

    socket.addEventListener("close", () => {
      if (elements.runtimeSessionState) {
        elements.runtimeSessionState.textContent = "Disconnected";
      }
      setConnectionState("error", "Disconnected");
      pushFeed("Connection closed. Reload or rejoin if needed.", "warning");
    });

    socket.addEventListener("error", () => {
      setConnectionState("error", "Connection error");
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
    if (elements.runtimeOperationName) {
      elements.runtimeOperationName.textContent = session?.operation_name || "Osk";
    }
    if (elements.runtimeDisplayName) {
      elements.runtimeDisplayName.textContent = memberName;
    }
    if (elements.runtimeSessionState) {
      elements.runtimeSessionState.textContent = session ? "Connecting" : "Resuming";
    }
    renderFeed();
    if (!session && resumeReady) {
      pushFeed(
        "Join session is no longer present. Attempting reconnect from local member resume state.",
        "warning",
      );
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
