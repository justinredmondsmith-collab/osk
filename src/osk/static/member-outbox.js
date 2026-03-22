(function () {
  const DB_NAME = "osk-member-outbox";
  const DB_VERSION = 1;
  const STORE_NAME = "entries";
  const MAX_PENDING_ITEMS = 12;

  let dbPromise = null;

  function requestToPromise(request) {
    return new Promise((resolve, reject) => {
      request.addEventListener("success", () => resolve(request.result), { once: true });
      request.addEventListener("error", () => reject(request.error), { once: true });
    });
  }

  function openDatabase() {
    if (!("indexedDB" in globalThis)) {
      return Promise.resolve(null);
    }
    if (dbPromise) {
      return dbPromise;
    }
    dbPromise = new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.addEventListener(
        "upgradeneeded",
        () => {
          const db = request.result;
          if (db.objectStoreNames.contains(STORE_NAME)) {
            db.deleteObjectStore(STORE_NAME);
          }
          const store = db.createObjectStore(STORE_NAME, { keyPath: "id" });
          store.createIndex("scope", "scope", { unique: false });
          store.createIndex("lookup_key", "lookupKey", { unique: true });
          store.createIndex("created_at", "createdAt", { unique: false });
        },
        { once: true },
      );
      request.addEventListener("success", () => resolve(request.result), { once: true });
      request.addEventListener("error", () => reject(request.error), { once: true });
      request.addEventListener(
        "blocked",
        () => reject(new Error("The member outbox database is blocked in another tab.")),
        { once: true },
      );
    });
    return dbPromise;
  }

  async function withStore(mode, handler) {
    const db = await openDatabase();
    if (!db) {
      return null;
    }
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(STORE_NAME, mode);
      const store = transaction.objectStore(STORE_NAME);
      let settled = false;
      function finish(value) {
        if (settled) {
          return;
        }
        settled = true;
        resolve(value);
      }
      function fail(error) {
        if (settled) {
          return;
        }
        settled = true;
        reject(error);
      }
      transaction.addEventListener("abort", () => fail(transaction.error), { once: true });
      transaction.addEventListener("error", () => fail(transaction.error), { once: true });
      Promise.resolve(handler(store, finish, fail)).catch(fail);
    });
  }

  async function getEntriesForScope(scope) {
    const entries = await withStore("readonly", (store, resolve, reject) => {
      if (!scope) {
        resolve([]);
        return;
      }
      const request = store.index("scope").openCursor(IDBKeyRange.only(scope));
      const values = [];
      request.addEventListener(
        "success",
        () => {
          const cursor = request.result;
          if (!cursor) {
            values.sort((left, right) => {
              const leftTime = new Date(left.createdAt).getTime();
              const rightTime = new Date(right.createdAt).getTime();
              return leftTime - rightTime;
            });
            resolve(values);
            return;
          }
          values.push(cursor.value);
          cursor.continue();
        },
        { once: false },
      );
      request.addEventListener("error", () => reject(request.error), { once: true });
    });
    return entries || [];
  }

  async function getEntryByLookupKey(lookupKey) {
    if (!lookupKey) {
      return null;
    }
    return await withStore("readonly", async (store, resolve, reject) => {
      try {
        const entry = await requestToPromise(store.index("lookup_key").get(lookupKey));
        resolve(entry || null);
      } catch (error) {
        reject(error);
      }
    });
  }

  async function putEntry(entry) {
    return withStore("readwrite", async (store, resolve, reject) => {
      try {
        await requestToPromise(store.put(entry));
        resolve(entry);
      } catch (error) {
        reject(error);
      }
    });
  }

  async function deleteEntry(entryId) {
    return withStore("readwrite", async (store, resolve, reject) => {
      try {
        await requestToPromise(store.delete(entryId));
        resolve(true);
      } catch (error) {
        reject(error);
      }
    });
  }

  async function pruneToScope(scope) {
    return withStore("readwrite", (store, resolve, reject) => {
      const request = store.openCursor();
      request.addEventListener(
        "success",
        async () => {
          const cursor = request.result;
          if (!cursor) {
            resolve(true);
            return;
          }
          if (scope && cursor.value.scope !== scope) {
            try {
              await requestToPromise(cursor.delete());
            } catch (error) {
              reject(error);
              return;
            }
          }
          cursor.continue();
        },
        { once: false },
      );
      request.addEventListener("error", () => reject(request.error), { once: true });
    });
  }

  function isRetryableAck(payload) {
    if (!payload || payload.accepted !== false) {
      return false;
    }
    const reason = String(payload.reason || payload.error || "")
      .trim()
      .toLowerCase();
    return (
      reason.includes("queue full") ||
      reason.includes("service unavailable") ||
      reason.includes("temporary") ||
      reason.includes("try again")
    );
  }

  function buildSnapshot(scope, entries, inFlightEntryId, lastError) {
    const oldestPendingAt = entries[0]?.createdAt || null;
    const pendingKinds = entries.reduce(
      (counts, entry) => {
        counts[entry.kind] = (counts[entry.kind] || 0) + 1;
        return counts;
      },
      { report: 0, audio: 0, frame: 0 },
    );
    return {
      available: true,
      scope,
      pendingCount: entries.length,
      pendingKinds,
      inFlight: Boolean(inFlightEntryId),
      oldestPendingAt,
      lastError,
    };
  }

  function createMemberOutbox(options = {}) {
    const onStateChange = options.onStateChange || (() => {});
    const canSend = options.canSend || (() => false);
    const getScope = options.getScope || (() => "");
    const sendJson = options.sendJson || (() => false);
    const sendBinary = options.sendBinary || (() => false);

    let inFlightEntryId = null;
    let flushPromise = null;
    let lastError = null;
    let currentSnapshot = {
      available: "indexedDB" in globalThis,
      scope: "",
      pendingCount: 0,
      pendingKinds: { report: 0, audio: 0, frame: 0 },
      inFlight: false,
      oldestPendingAt: null,
      lastError: null,
    };

    function scopeKey() {
      return String(getScope() || "").trim();
    }

    async function refresh() {
      const scope = scopeKey();
      if (!("indexedDB" in globalThis)) {
        currentSnapshot = {
          ...currentSnapshot,
          available: false,
          scope,
          lastError: "This browser does not support IndexedDB outbox storage.",
        };
        onStateChange(currentSnapshot);
        return currentSnapshot;
      }
      if (!scope) {
        currentSnapshot = {
          ...currentSnapshot,
          available: true,
          scope: "",
          pendingCount: 0,
          pendingKinds: { report: 0, audio: 0, frame: 0 },
          inFlight: false,
          oldestPendingAt: null,
          lastError,
        };
        onStateChange(currentSnapshot);
        return currentSnapshot;
      }
      await pruneToScope(scope);
      const entries = await getEntriesForScope(scope);
      currentSnapshot = buildSnapshot(scope, entries, inFlightEntryId, lastError);
      onStateChange(currentSnapshot);
      return currentSnapshot;
    }

    async function ensureCapacity(scope) {
      const entries = await getEntriesForScope(scope);
      if (entries.length >= MAX_PENDING_ITEMS) {
        throw new Error(
          "The member outbox is full. Reconnect or clear queued items before capturing more.",
        );
      }
    }

    async function enqueueReport({
      reportId,
      text,
      operationId,
      operationName,
      memberId,
      memberName,
    }) {
      const scope = scopeKey();
      if (!scope) {
        throw new Error("Secure member session is not ready yet.");
      }
      await ensureCapacity(scope);
      const createdAt = new Date().toISOString();
      await putEntry({
        id: `report:${reportId}`,
        lookupKey: `${scope}:report:${reportId}`,
        scope,
        kind: "report",
        itemKey: reportId,
        createdAt,
        updatedAt: createdAt,
        attempts: 0,
        text,
        operationId,
        operationName,
        memberId,
        memberName,
      });
      await refresh();
      void flush();
      return currentSnapshot;
    }

    async function enqueueMedia({
      kind,
      itemId,
      metadata,
      blob,
      operationId,
      operationName,
      memberId,
      memberName,
    }) {
      const scope = scopeKey();
      if (!scope) {
        throw new Error("Secure member session is not ready yet.");
      }
      await ensureCapacity(scope);
      const createdAt = new Date().toISOString();
      await putEntry({
        id: `${kind}:${itemId}`,
        lookupKey: `${scope}:${kind}:${itemId}`,
        scope,
        kind,
        itemKey: itemId,
        createdAt,
        updatedAt: createdAt,
        attempts: 0,
        sizeBytes: Number(blob?.size || 0),
        operationId,
        operationName,
        memberId,
        memberName,
        metadata,
        blob,
      });
      await refresh();
      void flush();
      return currentSnapshot;
    }

    async function clearPending() {
      const scope = scopeKey();
      const entries = scope
        ? await getEntriesForScope(scope)
        : await withStore("readonly", (store, resolve, reject) => {
            const request = store.getAll();
            request.addEventListener("success", () => resolve(request.result || []), {
              once: true,
            });
            request.addEventListener("error", () => reject(request.error), { once: true });
          });
      await Promise.all(entries.map((entry) => deleteEntry(entry.id)));
      inFlightEntryId = null;
      lastError = null;
      return refresh();
    }

    async function sendEntry(entry) {
      if (entry.kind === "report") {
        return sendJson({
          type: "report",
          report_id: entry.itemKey,
          text: entry.text,
        });
      }
      if (!sendJson(entry.metadata)) {
        return false;
      }
      return sendBinary(entry.blob);
    }

    async function flush() {
      if (flushPromise) {
        return flushPromise;
      }
      flushPromise = (async () => {
        if (!canSend()) {
          return refresh();
        }
        if (inFlightEntryId) {
          return refresh();
        }
        const scope = scopeKey();
        if (!scope) {
          return refresh();
        }
        const entries = await getEntriesForScope(scope);
        const nextEntry = entries[0];
        if (!nextEntry) {
          return refresh();
        }
        nextEntry.attempts = Number(nextEntry.attempts || 0) + 1;
        nextEntry.updatedAt = new Date().toISOString();
        await putEntry(nextEntry);
        const sent = await sendEntry(nextEntry);
        if (!sent) {
          lastError = "Live member connection is unavailable. Pending items will retry.";
          return refresh();
        }
        inFlightEntryId = nextEntry.id;
        lastError = null;
        return refresh();
      })();
      try {
        return await flushPromise;
      } finally {
        flushPromise = null;
      }
    }

    async function handleAck(payload) {
      const scope = scopeKey();
      if (!scope || !payload || typeof payload !== "object") {
        return { handled: false, retryable: false };
      }
      const type = String(payload.type || "").trim();
      let lookupKey = "";
      if (type === "report_ack") {
        const reportId = String(payload.report_id || "").trim();
        if (!reportId) {
          return { handled: false, retryable: false };
        }
        lookupKey = `${scope}:report:${reportId}`;
      } else if (type === "audio_ack") {
        const chunkId = String(payload.chunk_id || "").trim();
        if (!chunkId) {
          return { handled: false, retryable: false };
        }
        lookupKey = `${scope}:audio:${chunkId}`;
      } else if (type === "frame_ack") {
        const frameId = String(payload.frame_id || "").trim();
        if (!frameId) {
          return { handled: false, retryable: false };
        }
        lookupKey = `${scope}:frame:${frameId}`;
      } else {
        return { handled: false, retryable: false };
      }

      const entry = await getEntryByLookupKey(lookupKey);
      if (!entry) {
        return { handled: false, retryable: false };
      }

      if (inFlightEntryId === entry.id) {
        inFlightEntryId = null;
      }

      const retryable = isRetryableAck(payload);
      if (payload.accepted === true || payload.duplicate === true) {
        await deleteEntry(entry.id);
        lastError = null;
      } else if (payload.accepted === false && retryable) {
        entry.updatedAt = new Date().toISOString();
        entry.lastError = String(payload.reason || payload.error || "Retry pending.");
        await putEntry(entry);
        lastError = entry.lastError;
      } else {
        await deleteEntry(entry.id);
        lastError = null;
      }

      await refresh();
      if (!retryable) {
        void flush();
      }
      return {
        handled: true,
        retryable,
        entry,
      };
    }

    return {
      clearPending,
      enqueueMedia,
      enqueueReport,
      flush,
      handleAck,
      refresh,
      snapshot() {
        return currentSnapshot;
      },
    };
  }

  globalThis.OskMemberOutbox = {
    createMemberOutbox,
  };
})();
