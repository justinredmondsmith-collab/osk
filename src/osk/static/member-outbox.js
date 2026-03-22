(function () {
  const DB_NAME = "osk-member-outbox";
  const DB_VERSION = 1;
  const STORE_NAME = "entries";
  const DEFAULT_MAX_PENDING_ITEMS = 12;
  const DEFAULT_MAX_SENSOR_AUDIO_ITEMS = 3;
  const DEFAULT_MAX_SENSOR_FRAME_ITEMS = 4;

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

  function buildSnapshot(scope, entries, inFlightEntryId, lastError, maxPendingItems) {
    const oldestPendingAt = entries[0]?.createdAt || null;
    const pendingKinds = entries.reduce(
      (counts, entry) => {
        counts[entry.kind] = (counts[entry.kind] || 0) + 1;
        return counts;
      },
      { report: 0, audio: 0, frame: 0 },
    );
    const pendingSources = entries.reduce(
      (counts, entry) => {
        const source = entry.source === "sensor" ? "sensor" : "manual";
        counts[source] = (counts[source] || 0) + 1;
        return counts;
      },
      { manual: 0, sensor: 0 },
    );
    const summarizedEntries = entries.slice(0, maxPendingItems).map((entry) => {
      const source = entry.source === "sensor" ? "sensor" : "manual";
      let label = "Queued item";
      let detail = "Pending local delivery.";
      if (entry.kind === "report") {
        label = "Field note";
        detail = String(entry.text || "").trim() || "Manual field note";
      } else if (entry.kind === "frame") {
        const width = Number(entry.metadata?.width || 0);
        const height = Number(entry.metadata?.height || 0);
        const score = Number(entry.metadata?.change_score || 0);
        if (source === "sensor") {
          label = "Sensor key frame";
          detail = width && height ? `Key frame ${width}x${height}` : "Sensor key frame";
          if (score > 0) {
            detail = `${detail} · score ${score.toFixed(2)}`;
          }
        } else {
          label = "Manual photo";
          detail =
            width && height
              ? `Still frame ${width}x${height}`
              : "Observer still photo";
        }
      } else if (entry.kind === "audio") {
        const durationMs = Number(entry.metadata?.duration_ms || 0);
        if (source === "sensor") {
          label = "Sensor audio";
          detail = durationMs
            ? `Live chunk ${Math.max(1, Math.round(durationMs / 1000))}s`
            : "Sensor audio chunk";
        } else {
          label = "Audio clip";
          detail = durationMs
            ? `Short clip ${Math.max(1, Math.round(durationMs / 1000))}s`
            : "Observer audio clip";
        }
      }
      return {
        id: entry.id,
        kind: entry.kind,
        itemKey: entry.itemKey,
        source,
        sourceLabel: source === "sensor" ? "Sensor buffer" : "Manual capture",
        label,
        detail,
        createdAt: entry.createdAt,
        updatedAt: entry.updatedAt,
        attempts: Number(entry.attempts || 0),
        sizeBytes: Number(entry.sizeBytes || 0),
        lastError: entry.lastError || null,
        inFlight: entry.id === inFlightEntryId,
      };
    });
    return {
      available: true,
      scope,
      pendingCount: entries.length,
      pendingKinds,
      pendingSources,
      entries: summarizedEntries,
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
    const maxPendingItems = Math.max(4, Number(options.maxPendingItems || DEFAULT_MAX_PENDING_ITEMS));
    const maxSensorAudioItems = Math.max(
      1,
      Number(options.maxSensorAudioItems || DEFAULT_MAX_SENSOR_AUDIO_ITEMS),
    );
    const maxSensorFrameItems = Math.max(
      1,
      Number(options.maxSensorFrameItems || DEFAULT_MAX_SENSOR_FRAME_ITEMS),
    );

    let inFlightEntryId = null;
    let flushPromise = null;
    let lastError = null;
    let currentSnapshot = {
      available: "indexedDB" in globalThis,
      scope: "",
      pendingCount: 0,
      pendingKinds: { report: 0, audio: 0, frame: 0 },
      pendingSources: { manual: 0, sensor: 0 },
      entries: [],
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
          pendingSources: { manual: 0, sensor: 0 },
          entries: [],
          inFlight: false,
          oldestPendingAt: null,
          lastError,
        };
        onStateChange(currentSnapshot);
        return currentSnapshot;
      }
      await pruneToScope(scope);
      const entries = await getEntriesForScope(scope);
      currentSnapshot = buildSnapshot(scope, entries, inFlightEntryId, lastError, maxPendingItems);
      onStateChange(currentSnapshot);
      return currentSnapshot;
    }

    function sensorLimitForKind(kind) {
      if (kind === "audio") {
        return maxSensorAudioItems;
      }
      if (kind === "frame") {
        return maxSensorFrameItems;
      }
      return 0;
    }

    async function ensureCapacity(scope, { kind, source }) {
      const entries = await getEntriesForScope(scope);
      const entrySource = source === "sensor" ? "sensor" : "manual";
      const removableIds = new Set();

      if (entrySource === "sensor" && (kind === "audio" || kind === "frame")) {
        const sameKindSensorEntries = entries.filter(
          (entry) =>
            entry.source === "sensor" && entry.kind === kind && entry.id !== inFlightEntryId,
        );
        const sameKindOverflow = sameKindSensorEntries.length - sensorLimitForKind(kind) + 1;
        if (sameKindOverflow > 0) {
          for (const entry of sameKindSensorEntries.slice(0, sameKindOverflow)) {
            removableIds.add(entry.id);
          }
        }

        const remainingEntries = entries.filter((entry) => !removableIds.has(entry.id));
        const totalOverflow = remainingEntries.length - maxPendingItems + 1;
        if (totalOverflow > 0) {
          const removableSensorEntries = remainingEntries.filter(
            (entry) => entry.source === "sensor" && entry.id !== inFlightEntryId,
          );
          for (const entry of removableSensorEntries.slice(0, totalOverflow)) {
            removableIds.add(entry.id);
          }
        }
      }

      const removableEntries = entries.filter((entry) => removableIds.has(entry.id));
      if (removableEntries.length) {
        await Promise.all(removableEntries.map((entry) => deleteEntry(entry.id)));
        return { droppedEntries: removableEntries };
      }

      if (entries.length >= maxPendingItems) {
        throw new Error(
          "The member outbox is full. Reconnect or clear queued items before capturing more.",
        );
      }
      return { droppedEntries: [] };
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
      await ensureCapacity(scope, { kind: "report", source: "manual" });
      const createdAt = new Date().toISOString();
      await putEntry({
        id: `report:${reportId}`,
        lookupKey: `${scope}:report:${reportId}`,
        scope,
        kind: "report",
        source: "manual",
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
      source,
      operationId,
      operationName,
      memberId,
      memberName,
    }) {
      const scope = scopeKey();
      if (!scope) {
        throw new Error("Secure member session is not ready yet.");
      }
      const entrySource = source === "sensor" ? "sensor" : "manual";
      const capacity = await ensureCapacity(scope, { kind, source: entrySource });
      const createdAt = new Date().toISOString();
      await putEntry({
        id: `${kind}:${itemId}`,
        lookupKey: `${scope}:${kind}:${itemId}`,
        scope,
        kind,
        source: entrySource,
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
      return {
        droppedEntries: capacity.droppedEntries,
        snapshot: currentSnapshot,
      };
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

    async function removeEntry(entryId) {
      const targetId = String(entryId || "").trim();
      if (!targetId) {
        return refresh();
      }
      if (inFlightEntryId === targetId) {
        inFlightEntryId = null;
      }
      await deleteEntry(targetId);
      return refresh();
    }

    async function prioritizeEntry(entryId) {
      const targetId = String(entryId || "").trim();
      const scope = scopeKey();
      if (!targetId || !scope) {
        return refresh();
      }
      const entries = await getEntriesForScope(scope);
      const target = entries.find((entry) => entry.id === targetId);
      if (!target) {
        return refresh();
      }
      const oldestCreatedAt = entries[0]?.createdAt || new Date().toISOString();
      const baseTime = new Date(oldestCreatedAt).getTime();
      target.createdAt = new Date(baseTime - 1).toISOString();
      target.updatedAt = new Date().toISOString();
      target.lastError = null;
      await putEntry(target);
      await refresh();
      void flush();
      return currentSnapshot;
    }

    async function markInflightRetry(reason) {
      if (!inFlightEntryId) {
        return refresh();
      }
      const scope = scopeKey();
      const targetId = inFlightEntryId;
      inFlightEntryId = null;
      if (!scope) {
        lastError = String(reason || "Connection lost before acknowledgement. Retry pending.");
        return refresh();
      }
      const entries = await getEntriesForScope(scope);
      const entry = entries.find((candidate) => candidate.id === targetId);
      if (!entry) {
        lastError = String(reason || "Connection lost before acknowledgement. Retry pending.");
        return refresh();
      }
      entry.updatedAt = new Date().toISOString();
      entry.lastError = String(reason || "Connection lost before acknowledgement. Retry pending.");
      await putEntry(entry);
      lastError = entry.lastError;
      return refresh();
    }

    async function sendEntry(entry) {
      if (entry.kind === "report") {
        return await Promise.resolve(
          sendJson({
          type: "report",
          report_id: entry.itemKey,
          text: entry.text,
          }),
        );
      }
      const metadataSent = await Promise.resolve(sendJson(entry.metadata));
      if (!metadataSent) {
        return false;
      }
      return await Promise.resolve(sendBinary(entry.blob));
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
      markInflightRetry,
      prioritizeEntry,
      refresh,
      removeEntry,
      snapshot() {
        return currentSnapshot;
      },
    };
  }

  globalThis.OskMemberOutbox = {
    createMemberOutbox,
  };
})();
