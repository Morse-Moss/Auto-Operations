(() => {
  const importer = globalThis.XhsCurrentNoteImporter;

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.action !== importer.ACTION) return false;
    try {
      sendResponse({
        ok: true,
        payload: importer.extractCurrentNote({
          locationLike: window.location,
          documentLike: document,
          initialState: window.__INITIAL_STATE__ || {},
        }),
      });
    } catch (error) {
      sendResponse({ ok: false, error: error instanceof Error ? error.message : String(error) });
    }
    return true;
  });
})();
