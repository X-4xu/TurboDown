// ============================================================
// TurboDown - Background Service Worker
// Intercepts downloads and sends them to local app
// ============================================================

const APP_BASE_URL = "http://127.0.0.1:9000";
const ADD_URL = `${APP_BASE_URL}/add`;
const YOUTUBE_URL = `${APP_BASE_URL}/youtube`;
const STATUS_URL = `${APP_BASE_URL}/status`;

// File extensions to always intercept
const INTERCEPT_EXTENSIONS = new Set([
  "exe", "msi", "zip", "rar", "7z", "tar", "gz", "bz2", "xz",
  "iso", "img", "pdf",
  "mp4", "mp3", "mkv", "avi", "webm", "flv", "mov", "wmv", "m4a", "m4v",
  "ogg", "opus", "aac", "flac", "wav",
  "doc", "docx", "xls", "xlsx", "ppt", "pptx",
  "dmg", "apk", "deb", "rpm",
  "torrent", "bin", "dat"
]);

// Minimum file size to intercept (1 MB) for unknown extensions
const MIN_SIZE_INTERCEPT = 1 * 1024 * 1024;

// Track recent downloads to avoid duplicates
const recentDownloads = new Map();
const DUPLICATE_WINDOW_MS = 3000;

// ============================================================
// Initialization
// ============================================================

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.set({
    interceptEnabled: true,
    interceptHistory: []
  });
  createContextMenus();
});

chrome.runtime.onStartup.addListener(() => {
  createContextMenus();
});

function createContextMenus() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "idm-download-link",
      title: "Download with TurboDown",
      contexts: ["link"]
    });
    chrome.contextMenus.create({
      id: "idm-download-image",
      title: "Download Image with TurboDown",
      contexts: ["image"]
    });
    chrome.contextMenus.create({
      id: "idm-download-video",
      title: "Download Video with TurboDown",
      contexts: ["video"]
    });
    chrome.contextMenus.create({
      id: "idm-download-audio",
      title: "Download Audio with TurboDown",
      contexts: ["audio"]
    });
    chrome.contextMenus.create({
      id: "idm-download-page",
      title: "Send Page URL to TurboDown",
      contexts: ["page"]
    });
  });
}

// ============================================================
// Context Menu Handler
// ============================================================

chrome.contextMenus.onClicked.addListener((info, tab) => {
  let url = null;

  switch (info.menuItemId) {
    case "idm-download-link":
      url = info.linkUrl;
      break;
    case "idm-download-image":
      url = info.srcUrl;
      break;
    case "idm-download-video":
      url = info.srcUrl;
      break;
    case "idm-download-audio":
      url = info.srcUrl;
      break;
    case "idm-download-page":
      url = info.pageUrl || (tab && tab.url);
      break;
  }

  if (url) {
    sendToApp(url, extractFilename(url), tab ? tab.url : "");
  }
});

// ============================================================
// Download Interception
// ============================================================

chrome.downloads.onCreated.addListener(async (downloadItem) => {
  const settings = await chrome.storage.local.get("interceptEnabled");
  if (settings.interceptEnabled === false) return;

  const url = downloadItem.url || downloadItem.finalUrl;

  // Skip internal URLs
  if (!url || url.startsWith("blob:") || url.startsWith("data:") ||
      url.startsWith("chrome-extension:") || url.startsWith("chrome:") ||
      url.startsWith("about:") || url.startsWith("edge:")) {
    return;
  }

  const ext = getExtension(url);
  const shouldIntercept = INTERCEPT_EXTENSIONS.has(ext) ||
    (downloadItem.fileSize && downloadItem.fileSize >= MIN_SIZE_INTERCEPT) ||
    (downloadItem.totalBytes && downloadItem.totalBytes >= MIN_SIZE_INTERCEPT) ||
    hasDownloadableContentType(downloadItem.mime);

  if (!shouldIntercept && ext && !INTERCEPT_EXTENSIONS.has(ext)) {
    if (downloadItem.fileSize === -1 || downloadItem.totalBytes === -1) {
      // Unknown size - likely a real download, intercept it
    } else if (downloadItem.fileSize > 0 || downloadItem.totalBytes > 0) {
      return;
    }
  }

  // Duplicate detection
  const now = Date.now();
  if (recentDownloads.has(url)) {
    if (now - recentDownloads.get(url) < DUPLICATE_WINDOW_MS) {
      try { chrome.downloads.cancel(downloadItem.id); } catch (e) {}
      try { chrome.downloads.erase({ id: downloadItem.id }); } catch (e) {}
      return;
    }
  }
  recentDownloads.set(url, now);

  // Clean old entries
  for (const [key, time] of recentDownloads) {
    if (now - time > DUPLICATE_WINDOW_MS * 5) recentDownloads.delete(key);
  }

  const filename = downloadItem.filename || extractFilename(url);

  // Cancel the browser download
  try { chrome.downloads.cancel(downloadItem.id); } catch (e) {}
  try { chrome.downloads.erase({ id: downloadItem.id }); } catch (e) {}

  sendToApp(url, filename, downloadItem.referrer || "");
});

chrome.downloads.onDeterminingFilename.addListener((downloadItem, suggest) => {
  suggest();
});

// ============================================================
// Send Download to Local App
// ============================================================

async function sendToApp(url, filename, referrer) {
  if (!url) return;

  try {
    const payload = {
      url: url,
      filename: filename || extractFilename(url),
      referrer: referrer || "",
      timestamp: new Date().toISOString()
    };

    const response = await fetch(ADD_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (response.ok) {
      addToHistory(payload.url, payload.filename);
      showNotification("Download Sent", `Sent to TurboDown:\n${payload.filename || payload.url}`);
    } else {
      showNotification("Download Error", `App returned error ${response.status}`);
    }
  } catch (error) {
    showNotification(
      "TurboDown Not Running",
      "Could not connect to TurboDown app. Make sure it is running on port 9000."
    );
  }
}

async function sendYouTubeToApp(url) {
  if (!url) return;

  try {
    const response = await fetch(YOUTUBE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: url, timestamp: new Date().toISOString() })
    });

    if (response.ok) {
      addToHistory(url, "YouTube Video");
      showNotification("YouTube Video Sent", "Sent YouTube URL to TurboDown");
    } else {
      showNotification("Error", `App returned error ${response.status}`);
    }
  } catch (error) {
    showNotification(
      "TurboDown Not Running",
      "Could not connect to TurboDown app. Make sure it is running on port 9000."
    );
  }
}

// ============================================================
// Utility Functions
// ============================================================

function extractFilename(url) {
  try {
    const urlObj = new URL(url);
    const parts = urlObj.pathname.split("/");
    const last = parts[parts.length - 1];
    if (last && last.includes(".")) return decodeURIComponent(last);
    return last ? decodeURIComponent(last) : "";
  } catch (e) {
    return "";
  }
}

function getExtension(url) {
  try {
    const path = new URL(url).pathname;
    const match = path.match(/\.([a-zA-Z0-9]+)(?:\?|$)/);
    if (match) return match[1].toLowerCase();
    const lastDot = path.lastIndexOf(".");
    if (lastDot > path.lastIndexOf("/")) return path.substring(lastDot + 1).toLowerCase();
    return "";
  } catch (e) {
    return "";
  }
}

function hasDownloadableContentType(mime) {
  if (!mime) return false;
  const types = [
    "application/octet-stream", "application/zip", "application/x-rar",
    "application/x-7z-compressed", "application/x-tar", "application/gzip",
    "application/pdf", "application/x-iso9660-image", "application/x-msdownload",
    "application/x-msi", "application/vnd.android.package-archive",
    "application/x-bittorrent", "video/", "audio/",
    "application/vnd.openxmlformats", "application/msword",
    "application/vnd.ms-excel", "application/vnd.ms-powerpoint"
  ];
  const m = mime.toLowerCase();
  return types.some(t => m.startsWith(t));
}

function showNotification(title, message) {
  try {
    chrome.notifications.create({ type: "basic", iconUrl: "icon.png", title, message });
  } catch (e) {
    console.log(`Notification: ${title} - ${message}`);
  }
}

async function addToHistory(url, filename) {
  try {
    const data = await chrome.storage.local.get("interceptHistory");
    let history = data.interceptHistory || [];
    history.unshift({ url, filename: filename || extractFilename(url), time: new Date().toISOString() });
    history = history.slice(0, 20);
    await chrome.storage.local.set({ interceptHistory: history });
  } catch (e) {}
}

// ============================================================
// YouTube Tab Detection - Set Badge
// ============================================================

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (tab.url && tab.url.includes("youtube.com/watch")) {
    chrome.action.setBadgeText({ text: "YT", tabId });
    chrome.action.setBadgeBackgroundColor({ color: "#FF0000", tabId });
  } else if (changeInfo.url && !changeInfo.url.includes("youtube.com/watch")) {
    chrome.action.setBadgeText({ text: "", tabId });
  }
});

chrome.tabs.onActivated.addListener(async (activeInfo) => {
  try {
    const tab = await chrome.tabs.get(activeInfo.tabId);
    if (tab.url && tab.url.includes("youtube.com/watch")) {
      chrome.action.setBadgeText({ text: "YT", tabId: tab.id });
      chrome.action.setBadgeBackgroundColor({ color: "#FF0000", tabId: tab.id });
    } else {
      chrome.action.setBadgeText({ text: "", tabId: tab.id });
    }
  } catch (e) {}
});

// ============================================================
// Message Handler (from content script and popup)
// ============================================================

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "downloadYouTube") {
    sendYouTubeToApp(message.url).then(() => sendResponse({ success: true }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
  }

  if (message.action === "addUrl") {
    sendToApp(message.url, message.filename || "", "").then(() => sendResponse({ success: true }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
  }

  if (message.action === "checkStatus") {
    fetch(STATUS_URL, { method: "GET" })
      .then(res => res.ok ? res.json() : Promise.reject("Not OK"))
      .then(data => sendResponse({ connected: true, data }))
      .catch(() => sendResponse({ connected: false }));
    return true;
  }

  if (message.action === "getHistory") {
    chrome.storage.local.get("interceptHistory").then(data => {
      sendResponse({ history: data.interceptHistory || [] });
    });
    return true;
  }

  if (message.action === "setIntercept") {
    chrome.storage.local.set({ interceptEnabled: message.enabled }).then(() => sendResponse({ success: true }));
    return true;
  }

  if (message.action === "getIntercept") {
    chrome.storage.local.get("interceptEnabled").then(data => {
      sendResponse({ enabled: data.interceptEnabled !== false });
    });
    return true;
  }
});
