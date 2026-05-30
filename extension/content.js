// ============================================================
// TurboDown - YouTube Content Script
// Injects a floating download button on YouTube video pages
// ============================================================

(function () {
  "use strict";

  const BUTTON_ID = "idm-clone-yt-download-btn";
  const CONTAINER_ID = "idm-clone-yt-container";

  let currentVideoUrl = "";
  let isInjected = false;

  // ============================================================
  // Styles
  // ============================================================

  function injectStyles() {
    if (document.getElementById("idm-clone-yt-styles")) return;

    const style = document.createElement("style");
    style.id = "idm-clone-yt-styles";
    style.textContent = `
      #${CONTAINER_ID} {
        display: inline-flex;
        align-items: center;
        position: relative;
        z-index: 2147483647;
      }

      #${BUTTON_ID} {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 12px;
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: 4px;
        background: rgba(15, 52, 96, 0.85); /* Matches COLORS.bg_light */
        backdrop-filter: blur(8px);
        color: #ffffff;
        font-family: "Segoe UI", "Roboto", sans-serif;
        font-size: 12px;
        font-weight: bold;
        cursor: pointer;
        transition: all 0.2s ease;
        line-height: 1.2;
        white-space: nowrap;
        box-shadow: 0 4px 12px rgba(0,0,0,0.5);
      }

      #${BUTTON_ID}:hover {
        background: #0984e3; /* Matches COLORS.blue */
        box-shadow: 0 4px 15px rgba(9, 132, 227, 0.5);
        border-color: rgba(255, 255, 255, 0.4);
        transform: translateY(-1px);
      }

      #${BUTTON_ID}:active {
        transform: translateY(0);
        box-shadow: 0 2px 4px rgba(0,0,0,0.3);
      }

      #${BUTTON_ID}.idm-sending {
        background: #636e72;
        cursor: wait;
        pointer-events: none;
      }

      #${BUTTON_ID}.idm-success {
        background: #00b894; /* Matches COLORS.green */
        border-color: rgba(255, 255, 255, 0.3);
      }

      #${BUTTON_ID}.idm-error {
        background: #d63031; /* Matches COLORS.red */
        border-color: rgba(255, 255, 255, 0.3);
      }

      #${BUTTON_ID} .idm-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 14px;
        height: 14px;
      }

      #${BUTTON_ID} .idm-icon svg {
        width: 14px;
        height: 14px;
        fill: currentColor;
      }
    `;
    document.head.appendChild(style);
  }

  // ============================================================
  // SVG Icons
  // ============================================================

  function getDownloadIcon() {
    return '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>';
  }

  function getCheckIcon() {
    return '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>';
  }

  function getErrorIcon() {
    return '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>';
  }

  // ============================================================
  // Button Creation
  // ============================================================

  function createDownloadButton() {
    const container = document.createElement("div");
    container.id = CONTAINER_ID;

    const button = document.createElement("button");
    button.id = BUTTON_ID;
    button.title = "Download this video with TurboDown";
    button.innerHTML = '<span class="idm-icon">' + getDownloadIcon() + '</span><span class="idm-label">Download Video</span>';

    button.addEventListener("click", handleDownloadClick);
    container.appendChild(button);
    return container;
  }

  // ============================================================
  // Click Handler
  // ============================================================

  async function handleDownloadClick(e) {
    e.preventDefault();
    e.stopPropagation();

    const button = document.getElementById(BUTTON_ID);
    if (!button || button.classList.contains("idm-sending")) return;

    const videoUrl = window.location.href;
    if (!videoUrl.includes("youtube.com/watch")) {
      updateButtonState("error", "Not a video page");
      return;
    }

    updateButtonState("sending", "Sending...");

    try {
      const response = await new Promise((resolve, reject) => {
        chrome.runtime.sendMessage(
          { action: "downloadYouTube", url: videoUrl },
          (response) => {
            if (chrome.runtime.lastError) {
              reject(new Error(chrome.runtime.lastError.message));
            } else {
              resolve(response);
            }
          }
        );
      });

      if (response && response.success) {
        updateButtonState("success", "Sent!");
      } else {
        updateButtonState("error", "Failed");
      }
    } catch (err) {
      console.error("TurboDown: Failed to send YouTube URL:", err);
      updateButtonState("error", "App offline");
    }
  }

  function updateButtonState(state, text) {
    const button = document.getElementById(BUTTON_ID);
    if (!button) return;

    button.classList.remove("idm-sending", "idm-success", "idm-error");

    const label = button.querySelector(".idm-label");
    const icon = button.querySelector(".idm-icon");

    switch (state) {
      case "sending":
        button.classList.add("idm-sending");
        if (label) label.textContent = text || "Sending...";
        break;
      case "success":
        button.classList.add("idm-success");
        if (icon) icon.innerHTML = getCheckIcon();
        if (label) label.textContent = text || "Sent!";
        setTimeout(() => updateButtonState("default", "Download Video"), 3000);
        break;
      case "error":
        button.classList.add("idm-error");
        if (icon) icon.innerHTML = getErrorIcon();
        if (label) label.textContent = text || "Error";
        setTimeout(() => updateButtonState("default", "Download Video"), 4000);
        break;
      default:
        if (icon) icon.innerHTML = getDownloadIcon();
        if (label) label.textContent = text || "Download Video";
        break;
    }
  }

  // ============================================================
  // Button Injection
  // ============================================================

  function injectButton() {
    const existing = document.getElementById(CONTAINER_ID);
    if (existing) existing.remove();

    if (!isVideoPage()) return;

    injectStyles();

    // 1. Try to inject floating over the video player
    const player = document.querySelector(".html5-video-player") || document.querySelector("#movie_player");
    if (player) {
      const button = createDownloadButton();
      // Apply absolute positioning for player overlay
      button.style.position = "absolute";
      button.style.top = "15px";
      button.style.right = "15px";
      button.style.zIndex = "2147483647"; // Float above everything
      
      player.appendChild(button);
      isInjected = true;
      currentVideoUrl = window.location.href;
      console.log("TurboDown: Injected floating button over player");
      return true;
    }

    // 2. Fallback to normal layout injection targets if player is not found
    const injectionTargets = [
      "#owner #subscribe-button",
      "#above-the-fold #subscribe-button",
      "#top-level-buttons-computed",
      "#menu-container #top-level-buttons-computed",
      "ytd-menu-renderer #top-level-buttons-computed",
      "#actions #actions-inner",
      "#actions ytd-menu-renderer",
      "#owner",
      "#above-the-fold #owner",
      "#info-contents",
      "#above-the-fold"
    ];

    for (const selector of injectionTargets) {
      const target = document.querySelector(selector);
      if (target && target.parentNode) {
        const button = createDownloadButton();
        target.parentNode.insertBefore(button, target.nextSibling);
        isInjected = true;
        currentVideoUrl = window.location.href;
        console.log("TurboDown: Button injected near fallback", selector);
        return true;
      }
    }

    console.log("TurboDown: No injection target found, will retry...");
    return false;
  }

  // ============================================================
  // Page Detection
  // ============================================================

  function isVideoPage() {
    return window.location.hostname.includes("youtube.com") &&
           window.location.pathname === "/watch" &&
           window.location.search.includes("v=");
  }

  // ============================================================
  // SPA Navigation Observer
  // ============================================================

  function setupNavigationObserver() {
    let lastUrl = window.location.href;

    const titleObserver = new MutationObserver(() => {
      const newUrl = window.location.href;
      if (newUrl !== lastUrl) {
        lastUrl = newUrl;
        isInjected = false;
        setTimeout(() => attemptInjection(), 800);
        setTimeout(() => attemptInjection(), 1500);
        setTimeout(() => attemptInjection(), 3000);
      }
    });

    const titleElement = document.querySelector("title");
    if (titleElement) {
      titleObserver.observe(titleElement, { childList: true, subtree: true, characterData: true });
    }

    window.addEventListener("popstate", () => {
      isInjected = false;
      setTimeout(() => attemptInjection(), 800);
      setTimeout(() => attemptInjection(), 1500);
    });

    window.addEventListener("yt-navigate-finish", () => {
      isInjected = false;
      setTimeout(() => attemptInjection(), 500);
      setTimeout(() => attemptInjection(), 1200);
      setTimeout(() => attemptInjection(), 2500);
    });

    window.addEventListener("yt-page-data-updated", () => {
      if (!isInjected || currentVideoUrl !== window.location.href) {
        isInjected = false;
        setTimeout(() => attemptInjection(), 500);
        setTimeout(() => attemptInjection(), 1500);
      }
    });

    const bodyObserver = new MutationObserver(() => {
      if (!isVideoPage()) return;
      if (isInjected && document.getElementById(CONTAINER_ID)) return;
      if (isInjected && !document.getElementById(CONTAINER_ID)) {
        isInjected = false;
        setTimeout(() => attemptInjection(), 300);
      }
    });

    bodyObserver.observe(document.body, { childList: true, subtree: true });
  }

  function attemptInjection() {
    if (isInjected && document.getElementById(CONTAINER_ID) && currentVideoUrl === window.location.href) return;

    if (!isVideoPage()) {
      const existing = document.getElementById(CONTAINER_ID);
      if (existing) existing.remove();
      isInjected = false;
      return;
    }

    injectButton();
  }

  // ============================================================
  // Initialize
  // ============================================================

  function init() {
    attemptInjection();
    setTimeout(() => attemptInjection(), 1000);
    setTimeout(() => attemptInjection(), 2000);
    setTimeout(() => attemptInjection(), 4000);
    setupNavigationObserver();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
