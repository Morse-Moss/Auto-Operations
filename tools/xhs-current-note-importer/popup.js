const DEFAULT_API_BASE = "http://127.0.0.1:18080";
const TOKEN_KEY = "xhs_import_access_token";
const API_BASE_KEY = "xhs_import_api_base";

const apiBaseInput = document.getElementById("api-base");
const tokenInput = document.getElementById("access-token");
const loadTokenButton = document.getElementById("load-token");
const importButton = document.getElementById("import-note");
const messageEl = document.getElementById("message");
const detailsEl = document.getElementById("details");

function setStatus(message, details = "") {
  messageEl.textContent = message;
  detailsEl.textContent = details;
}

function cleanToken(value) {
  return String(value || "").trim().replace(/^Bearer\s+/i, "");
}

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0];
}

async function saveSettings() {
  await chrome.storage.local.set({
    [API_BASE_KEY]: apiBaseInput.value.trim() || DEFAULT_API_BASE,
    [TOKEN_KEY]: cleanToken(tokenInput.value),
  });
}

async function loadSettings() {
  const stored = await chrome.storage.local.get([API_BASE_KEY, TOKEN_KEY]);
  apiBaseInput.value = stored[API_BASE_KEY] || DEFAULT_API_BASE;
  tokenInput.value = stored[TOKEN_KEY] || "";
}

async function loadTokenFromLocalApp() {
  const apiBase = apiBaseInput.value.trim() || DEFAULT_API_BASE;
  const origin = new URL(apiBase).origin;
  const tabs = await chrome.tabs.query({ url: [`${origin}/*`] });
  if (!tabs.length) {
    throw new Error("请先在本地平台页面完成登录，并保持页面打开。");
  }
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId: tabs[0].id },
    func: async () => {
      const refreshToken = window.localStorage.getItem("spider_xhs_refresh_token");
      if (!refreshToken) return "";
      const response = await fetch("/api/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!response.ok) return "";
      const data = await response.json();
      return data.access_token || "";
    },
  });
  if (!result) {
    throw new Error("未能读取登录态，请在本地平台重新登录后再试。");
  }
  tokenInput.value = result;
  await saveSettings();
}

async function extractFromCurrentTab(tabId) {
  await chrome.scripting.executeScript({
    target: { tabId },
    world: "MAIN",
    files: ["extractor.js"],
  });
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId },
    world: "MAIN",
    func: () => {
      const importer = globalThis.XhsCurrentNoteImporter;
      if (!importer) {
        return { ok: false, error: "Extractor is not ready on the current page." };
      }
      try {
        return {
          ok: true,
          payload: importer.extractCurrentNote({
            locationLike: window.location,
            documentLike: document,
            initialState: window.__INITIAL_STATE__ || {},
          }),
        };
      } catch (error) {
        return { ok: false, error: error instanceof Error ? error.message : String(error) };
      }
    },
  });
  if (result?.ok) {
    return result.payload;
  }
  throw new Error(result?.error || "当前页面暂时无法解析。");
}

async function importCurrentNote() {
  await saveSettings();
  const apiBase = (apiBaseInput.value.trim() || DEFAULT_API_BASE).replace(/\/$/, "");
  const token = cleanToken(tokenInput.value);
  if (!token) {
    throw new Error("缺少访问令牌。");
  }
  const tab = await getActiveTab();
  if (!tab?.id || !tab.url?.startsWith("https://www.xiaohongshu.com/explore/")) {
    throw new Error("请先切到小红书笔记详情页。");
  }
  const payload = await extractFromCurrentTab(tab.id);
  const response = await fetch(`${apiBase}/api/xhs/page-import/current-note`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `导入失败：HTTP ${response.status}`);
  }
  return data;
}

loadTokenButton.addEventListener("click", async () => {
  loadTokenButton.disabled = true;
  setStatus("正在读取令牌...");
  try {
    await loadTokenFromLocalApp();
    setStatus("令牌已读取。");
  } catch (error) {
    setStatus("读取失败", error instanceof Error ? error.message : String(error));
  } finally {
    loadTokenButton.disabled = false;
  }
});

importButton.addEventListener("click", async () => {
  importButton.disabled = true;
  setStatus("正在导入...");
  try {
    const data = await importCurrentNote();
    setStatus(
      "导入成功",
      `笔记：${data.item?.title || data.item?.note_id || "-"}\n素材：${data.asset_count}\n可见评论：${data.comment_count}`
    );
  } catch (error) {
    setStatus("导入失败", error instanceof Error ? error.message : String(error));
  } finally {
    importButton.disabled = false;
  }
});

void loadSettings();
