(function () {
  const CACHE_PREFIX = "osk-member-";
  const PWA_STATE_EVENT = "osk:pwa-state";
  const NETWORK_STATE_EVENT = "osk:pwa-network";

  let registrationPromise = null;
  let listenersBound = false;
  let installPromptEvent = null;
  let installState = null;

  function dispatchRuntimeEvent(name, detail) {
    window.dispatchEvent(new CustomEvent(name, { detail }));
  }

  function isStandalone() {
    return (
      window.matchMedia?.("(display-mode: standalone)").matches ||
      window.navigator?.standalone === true
    );
  }

  function detectManualInstallHint() {
    const agent = String(navigator.userAgent || "").toLowerCase();
    if (agent.includes("iphone") || agent.includes("ipad")) {
      return "Use Share → Add to Home Screen to install this shell on iPhone or iPad.";
    }
    if (agent.includes("android")) {
      return "Use the browser menu to install this shell if the prompt is unavailable.";
    }
    return "Install from the browser if your platform exposes an app install action.";
  }

  function buildInstallState() {
    return {
      serviceWorkerSupported: "serviceWorker" in navigator,
      installPromptAvailable: Boolean(installPromptEvent),
      installed: isStandalone(),
      secureContext: Boolean(window.isSecureContext),
      manualInstallHint: detectManualInstallHint(),
    };
  }

  function publishInstallState() {
    installState = buildInstallState();
    dispatchRuntimeEvent(PWA_STATE_EVENT, installState);
    return installState;
  }

  function updateNetworkState() {
    const detail = {
      online: navigator.onLine !== false,
    };
    document.documentElement.dataset.oskNetwork = detail.online ? "online" : "offline";
    dispatchRuntimeEvent(NETWORK_STATE_EVENT, detail);
    return detail;
  }

  function bindNetworkListeners() {
    if (listenersBound) {
      return;
    }
    listenersBound = true;
    updateNetworkState();
    publishInstallState();

    window.addEventListener("online", () => {
      updateNetworkState();
    });
    window.addEventListener("offline", () => {
      updateNetworkState();
    });
    window.addEventListener("beforeinstallprompt", (event) => {
      event.preventDefault();
      installPromptEvent = event;
      publishInstallState();
    });
    window.addEventListener("appinstalled", () => {
      installPromptEvent = null;
      publishInstallState();
    });

    const displayModeQuery = window.matchMedia?.("(display-mode: standalone)");
    if (displayModeQuery && typeof displayModeQuery.addEventListener === "function") {
      displayModeQuery.addEventListener("change", () => {
        publishInstallState();
      });
    }
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
      .then((registration) => {
        publishInstallState();
        return registration;
      })
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

  async function requestInstall() {
    bindNetworkListeners();
    if (isStandalone()) {
      installPromptEvent = null;
      publishInstallState();
      return { outcome: "already-installed" };
    }
    if (!installPromptEvent) {
      publishInstallState();
      return { outcome: "unavailable", hint: detectManualInstallHint() };
    }
    const promptEvent = installPromptEvent;
    installPromptEvent = null;
    await promptEvent.prompt();
    const result = (await promptEvent.userChoice?.catch(() => null)) || {
      outcome: "dismissed",
    };
    publishInstallState();
    return result;
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
    getInstallState() {
      if (!installState) {
        installState = buildInstallState();
      }
      return installState;
    },
    registerMemberPwa,
    requestInstall,
    updateNetworkState,
  };
})();
