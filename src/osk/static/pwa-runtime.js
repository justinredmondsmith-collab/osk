(function () {
  const CACHE_PREFIX = "osk-member-";
  let registrationPromise = null;
  let listenersBound = false;

  function updateNetworkState() {
    document.documentElement.dataset.oskNetwork = navigator.onLine === false ? "offline" : "online";
  }

  function bindNetworkListeners() {
    if (listenersBound) {
      return;
    }
    listenersBound = true;
    updateNetworkState();
    window.addEventListener("online", updateNetworkState);
    window.addEventListener("offline", updateNetworkState);
  }

  async function registerMemberPwa() {
    bindNetworkListeners();
    if (!("serviceWorker" in navigator)) {
      return null;
    }
    if (!window.isSecureContext) {
      return null;
    }
    if (registrationPromise) {
      return registrationPromise;
    }
    registrationPromise = navigator.serviceWorker
      .register("/sw.js", { scope: "/" })
      .catch(() => null);
    return registrationPromise;
  }

  async function clearMemberOfflineState() {
    bindNetworkListeners();
    if ("caches" in globalThis) {
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter((cacheName) => cacheName.startsWith(CACHE_PREFIX))
          .map((cacheName) => caches.delete(cacheName)),
      );
    }

    const registration = await registerMemberPwa();
    if (registration?.active) {
      registration.active.postMessage({ type: "clear_member_offline_state" });
      return;
    }
    if (navigator.serviceWorker?.controller) {
      navigator.serviceWorker.controller.postMessage({ type: "clear_member_offline_state" });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      () => {
        void registerMemberPwa();
      },
      { once: true },
    );
  } else {
    void registerMemberPwa();
  }

  globalThis.OskPwaRuntime = {
    clearMemberOfflineState,
    registerMemberPwa,
  };
})();
