// ============================================================
// TurboDown - Popup Script
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
  const statusBadge = document.getElementById("statusBadge");
  const statusText = document.getElementById("statusText");
  const interceptToggle = document.getElementById("interceptToggle");
  const urlInput = document.getElementById("urlInput");
  const urlSendBtn = document.getElementById("urlSendBtn");
  const urlFeedback = document.getElementById("urlFeedback");
  const historyList = document.getElementById("historyList");

  // ===== Connection Status =====
  function checkStatus() {
    chrome.runtime.sendMessage({ action: "checkStatus" }, (response) => {
      if (chrome.runtime.lastError) { setStatus(false); return; }
      setStatus(response && response.connected);
    });
  }

  function setStatus(connected) {
    statusBadge.className = `status-badge ${connected ? "connected" : "disconnected"}`;
    statusText.textContent = connected ? "Connected" : "Disconnected";
  }

  // ===== Intercept Toggle =====
  function loadInterceptState() {
    chrome.runtime.sendMessage({ action: "getIntercept" }, (response) => {
      if (chrome.runtime.lastError) return;
      if (response) interceptToggle.checked = response.enabled !== false;
    });
  }

  interceptToggle.addEventListener("change", () => {
    chrome.runtime.sendMessage({ action: "setIntercept", enabled: interceptToggle.checked });
  });

  // ===== Manual URL Submission =====
  function sendUrl() {
    const url = urlInput.value.trim();

    if (!url) { showFeedback("Please enter a URL", "error"); return; }

    if (!url.startsWith("http://") && !url.startsWith("https://") &&
        !url.startsWith("ftp://") && !url.startsWith("magnet:")) {
      showFeedback("Invalid URL. Must start with http:// or https://", "error");
      return;
    }

    urlSendBtn.disabled = true;
    urlSendBtn.textContent = "Sending...";

    chrome.runtime.sendMessage({ action: "addUrl", url: url }, (response) => {
      urlSendBtn.disabled = false;
      urlSendBtn.textContent = "Send";

      if (chrome.runtime.lastError) {
        showFeedback("Extension error: " + chrome.runtime.lastError.message, "error");
        return;
      }

      if (response && response.success) {
        showFeedback("\u2713 URL sent to TurboDown!", "success");
        urlInput.value = "";
        setTimeout(loadHistory, 500);
      } else {
        showFeedback("\u2717 Failed to send. Is the app running?", "error");
      }
    });
  }

  urlSendBtn.addEventListener("click", sendUrl);
  urlInput.addEventListener("keydown", (e) => { if (e.key === "Enter") sendUrl(); });

  function showFeedback(message, type) {
    urlFeedback.textContent = message;
    urlFeedback.className = `url-feedback ${type}`;
    setTimeout(() => { urlFeedback.textContent = ""; urlFeedback.className = "url-feedback"; }, 4000);
  }

  // ===== Download History =====
  function loadHistory() {
    chrome.runtime.sendMessage({ action: "getHistory" }, (response) => {
      if (chrome.runtime.lastError) return;
      const history = (response && response.history) || [];
      renderHistory(history.slice(0, 5));
    });
  }

  function renderHistory(items) {
    historyList.innerHTML = "";

    if (items.length === 0) {
      historyList.innerHTML = '<li class="history-empty">No downloads yet</li>';
      return;
    }

    items.forEach(item => {
      const li = document.createElement("li");
      li.className = "history-item";

      const filename = item.filename || extractFilename(item.url) || "Unknown file";
      const timeStr = formatTime(item.time);

      li.innerHTML = `
        <div class="history-icon">
          <svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
        </div>
        <div class="history-details">
          <div class="history-filename" title="${escapeHtml(item.url)}">${escapeHtml(filename)}</div>
          <div class="history-time">${timeStr}</div>
        </div>
      `;

      historyList.appendChild(li);
    });
  }

  function extractFilename(url) {
    try {
      const u = new URL(url);
      const parts = u.pathname.split("/");
      const last = parts[parts.length - 1];
      if (last && last.includes(".")) return decodeURIComponent(last);
      if (url.includes("youtube.com")) return "YouTube Video";
      return last ? decodeURIComponent(last) : url.substring(0, 40);
    } catch (e) {
      return url.substring(0, 40);
    }
  }

  function formatTime(isoStr) {
    try {
      const diffSec = Math.floor((new Date() - new Date(isoStr)) / 1000);
      if (diffSec < 60) return "Just now";
      const diffMin = Math.floor(diffSec / 60);
      if (diffMin < 60) return `${diffMin}m ago`;
      const diffHr = Math.floor(diffMin / 60);
      if (diffHr < 24) return `${diffHr}h ago`;
      return new Date(isoStr).toLocaleDateString();
    } catch (e) { return ""; }
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // ===== Initialize =====
  checkStatus();
  loadInterceptState();
  loadHistory();
  setInterval(checkStatus, 5000);
});
