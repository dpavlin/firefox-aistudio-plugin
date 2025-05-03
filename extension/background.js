// @@FILENAME@@ extension/background.js
// Default server port
const DEFAULT_PORT = 5000;
const STORAGE_TAB_PORTS_KEY = 'tabServerPorts';
const STORAGE_BLOCK_STATUS_KEY = 'tabBlockStatuses';
// const STORAGE_LAST_OUTPUT_KEY = 'tabLastOutputs'; // REMOVED
const STORAGE_ACTIVE_KEY = 'extensionActive';

// --- Helper Functions ---
// getTabPortsObject, getBlockStatusObject (remain the same)
async function getTabPortsObject() {
  try {
    let data = await browser.storage.local.get(STORAGE_TAB_PORTS_KEY);
    const portsObj = data?.[STORAGE_TAB_PORTS_KEY];
    if (typeof portsObj === 'object' && portsObj !== null) {
        return portsObj;
    }
  } catch (error) { console.error("BG Error getting tab ports object:", error); }
  return {};
}
async function getBlockStatusObject() {
    try {
        let data = await browser.storage.local.get(STORAGE_BLOCK_STATUS_KEY);
        const statusObj = data?.[STORAGE_BLOCK_STATUS_KEY];
        if (typeof statusObj === 'object' && statusObj !== null) {
            return statusObj;
        }
    } catch (error) { console.error("BG Error getting block status object:", error); }
    return {};
}
async function getPortForTab(tabId) {
    if (typeof tabId !== 'number') return DEFAULT_PORT;
    const portsObj = await getTabPortsObject();
    const port = parseInt(portsObj[tabId], 10);
    return (!isNaN(port) && port >= 1025 && port <= 65535) ? port : DEFAULT_PORT;
 }
async function setPortForTab(tabId, port) {
    if (typeof tabId !== 'number') return false;
     const portToStore = parseInt(port, 10);
     if (isNaN(portToStore) || portToStore < 1025 || portToStore > 65535) return false;
    try {
        const portsObj = await getTabPortsObject();
        portsObj[tabId] = portToStore;
        await browser.storage.local.set({ [STORAGE_TAB_PORTS_KEY]: portsObj });
        console.log(`BG: Stored port ${portToStore} for tab ${tabId}`);
        return true;
    } catch (error) { console.error(`BG Error storing port ${portToStore} for tab ${tabId}:`, error); return false; }
 }
async function getBlockStatus(tabId, blockHash) {
    if (typeof tabId !== 'number' || !blockHash) return null;
    try {
        const statusObject = await getBlockStatusObject();
        return statusObject[tabId]?.[blockHash] || null;
    } catch (error) { console.error(`BG Error getting status for hash ${blockHash} in tab ${tabId}:`, error); return null; }
 }
async function setBlockStatus(tabId, blockHash, status) {
    if (typeof tabId !== 'number' || !blockHash || !status) return false;
    try {
        const statusObject = await getBlockStatusObject();
        if (!statusObject[tabId]) { statusObject[tabId] = {}; }
        statusObject[tabId][blockHash] = status;
        await browser.storage.local.set({ [STORAGE_BLOCK_STATUS_KEY]: statusObject });
        console.log(`BG: Set status for hash ${blockHash} in tab ${tabId} to ${status}`);
        return true;
    } catch (error) { console.error(`BG Error setting status for hash ${blockHash} in tab ${tabId}:`, error); return false; }
 }
async function getActivationState() {
    try {
        let data = await browser.storage.local.get(STORAGE_ACTIVE_KEY);
        return data?.[STORAGE_ACTIVE_KEY] !== false;
    } catch (error) { console.error("BG Error getting activation state:", error); return true; }
 }
async function storeActivationState(isActive) {
    const stateToStore = isActive === true;
     try {
         await browser.storage.local.set({ [STORAGE_ACTIVE_KEY]: stateToStore });
         console.log(`BG: Stored global activation state: ${stateToStore}`);
         return true;
     } catch (error) { console.error(`BG Error storing activation state ${stateToStore}:`, error); return false; }
 }

// REMOVED getLastOutputObject function
// REMOVED storeLastOutput function

// --- Main Message Listener ---
browser.runtime.onMessage.addListener(async (request, sender, sendResponse) => {
  console.log("Background: Received message:", request.action, "from tab:", sender.tab?.id, request);
  const senderTabId = sender.tab?.id;

  // --- Port Management ---
  if (request.action === "getPort") {
        const tabIdToGet = request.tabId ?? senderTabId;
        if (typeof tabIdToGet !== 'number') {
             return Promise.resolve({ port: DEFAULT_PORT });
        }
        const port = await getPortForTab(tabIdToGet);
        return Promise.resolve({ port: port });
  }
  else if (request.action === "storePort") {
       const tabIdToSet = request.tabId;
       if (typeof tabIdToSet !== 'number') {
           return Promise.resolve({ success: false, message: "Invalid tab ID" });
       }
      const success = await setPortForTab(tabIdToSet, request.port);
      return Promise.resolve({ success: success });
  }
  // --- Activation State Management ---
  else if (request.action === "getActivationState") {
        const isActive = await getActivationState();
        return Promise.resolve({ isActive: isActive });
   }
   else if (request.action === "storeActivationState") {
        const success = await storeActivationState(request.isActive);
        return Promise.resolve({ success: success });
    }
  // --- Block Status Management ---
  else if (request.action === "getBlockStatus") {
       if (typeof senderTabId !== 'number' || !request.hash) {
           return Promise.resolve({ status: null });
       }
       const status = await getBlockStatus(senderTabId, request.hash);
       return Promise.resolve({ status: status });
   }
   else if (request.action === "setBlockStatus") {
        if (typeof senderTabId !== 'number' || !request.hash || !request.status) {
            return Promise.resolve({ success: false });
        }
        const success = await setBlockStatus(senderTabId, request.hash, request.status);
        return Promise.resolve({ success: success });
    }

  // REMOVED Get Last Output handler
  // else if (request.action === "getLastOutput") { /* ... */ }

  // --- Server Interaction ---
  else if (request.action === "submitCode") {
    const isActive = await getActivationState();
    if (!isActive) {
        return Promise.resolve({ success: false, details: { status: 'inactive', message: 'Extension is currently inactive.' } });
    }
     if (typeof senderTabId !== 'number') {
         return Promise.resolve({ success: false, details: { status: 'error', message: 'Missing sender tab ID.' } });
     }
    if (!request.code || !request.hash) {
      return Promise.resolve({ success: false, details: { status: 'error', message: 'Missing code or hash in submitCode request.' } });
    }

    try {
      const port = await getPortForTab(senderTabId);
      const url = `http://127.0.0.1:${port}/submit_code`;
      console.log(`BG: Sending code from tab ${senderTabId} to ${url} (Hash: ${request.hash})`);

      const response = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
          body: JSON.stringify({ code: request.code })
       });

      let serverResponseData = null;
      let fetchSuccess = false;
      let statusToStore = 'error';

      if (!response.ok) {
          const errorText = await response.text().catch(() => `Server returned status ${response.status}`);
          await setBlockStatus(senderTabId, request.hash, 'error');
          // REMOVED await storeLastOutput(...)
          return Promise.resolve({ success: false, details: { status: 'error', message: `Server error: ${response.status} ${response.statusText}`, server_response: errorText } });
      } else {
          serverResponseData = await response.json();
          fetchSuccess = serverResponseData.status === 'success';
          statusToStore = fetchSuccess ? 'sent' : 'error';
          console.log("BG: Received response from server for /submit_code:", serverResponseData);
          // REMOVED await storeLastOutput(...)
          await setBlockStatus(senderTabId, request.hash, statusToStore);
          return Promise.resolve({ success: fetchSuccess, details: serverResponseData });
      }

    } catch (error) {
       console.error("Background: Error fetching /submit_code:", error);
       const portForError = await getPortForTab(senderTabId);
       let errorMessage = `Network error connecting to port ${portForError} for tab ${senderTabId}. Is the server running?`;
       if (!(error instanceof TypeError && error.message.includes('NetworkError'))) {
            errorMessage = error.message || 'Unknown fetch error.';
       }
       await setBlockStatus(senderTabId, request.hash, 'error');
       // REMOVED await storeLastOutput(...)
       return Promise.resolve({ success: false, details: { status: 'error', message: errorMessage } });
    }
  }
  else if (request.action === "testConnection") {
     try {
          const port = request.port;
          if (isNaN(port) || port < 1025 || port > 65535) {
              throw new Error(`Invalid port specified in request: ${port}`);
          }
          const url = `http://127.0.0.1:${port}/test_connection`;
          console.log(`Background: Testing connection to ${url} (requested by popup)`);
          const response = await fetch(url, {cache: "no-store"});
          if (!response.ok) {
               const errorText = await response.text().catch(() => `Server returned status ${response.status}`);
               throw new Error(`Server responded with status ${response.status}. Response: ${errorText}`);
          }
          const data = await response.json();
          console.log("Background: Test connection successful:", data);
          return Promise.resolve({ success: true, details: data });
      } catch (error) {
           console.error("Background: Test connection failed:", error);
           return Promise.resolve({ success: false, details: { status: 'error', message: error.message || 'Connection failed' } });
      }
  }
   else if (request.action === "updateConfig") {
        if (typeof senderTabId !== 'number') {
            return Promise.resolve({ success: false, details: { message: 'Missing sender tab ID.' } });
        }
       try {
            const port = await getPortForTab(senderTabId);
            const url = `http://127.0.0.1:${port}/update_config`;
            const settingsToSend = {};
            if (request.settings && request.settings.hasOwnProperty('port')) {
                 settingsToSend.port = request.settings.port;
            }
             if (Object.keys(settingsToSend).length === 0) {
                 return Promise.resolve({ success: true, details: { message: "No applicable settings to update.", status: "info"} });
             }

            console.log(`Background: Sending config update for tab ${senderTabId} to ${url}`, settingsToSend);
            const response = await fetch(url, {
                 method: 'POST',
                 headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                 body: JSON.stringify(settingsToSend)
            });
             if (!response.ok) {
                 const errorText = await response.text().catch(() => `Server returned status ${response.status}`);
                 throw new Error(`Server error updating config: ${response.status} ${response.statusText}. Response: ${errorText}`);
             }
             const data = await response.json();
             console.log("Background: Config update response:", data);
             return Promise.resolve({ success: data.status === 'success', details: data });
         } catch (error) {
             console.error("Background: Update config failed:", error);
              const portForError = await getPortForTab(senderTabId);
             return Promise.resolve({ success: false, details: { status: 'error', message: error.message || `Update failed for server on port ${portForError}` } });
         }
   }

  // Default fallback
  console.warn(`Background: Unhandled message action: ${request.action}`);
  return Promise.resolve({ success: false, details: { message: `Unhandled action: ${request.action}` }});

});

// --- Tab Close Listener ---
browser.tabs.onRemoved.addListener(async (tabId, removeInfo) => {
    console.log(`BG: Tab ${tabId} removed. Cleaning up storage.`);
    try {
        // Clean up port storage
        const portsObj = await getTabPortsObject();
        if (portsObj.hasOwnProperty(tabId)) {
             delete portsObj[tabId];
             await browser.storage.local.set({ [STORAGE_TAB_PORTS_KEY]: portsObj });
             console.log(`BG: Removed port setting for closed tab ${tabId}`);
         }
        // Clean up block status storage
        const statusObject = await getBlockStatusObject();
         if (statusObject.hasOwnProperty(tabId)) {
             delete statusObject[tabId];
             await browser.storage.local.set({ [STORAGE_BLOCK_STATUS_KEY]: statusObject });
             console.log(`BG: Removed block statuses for closed tab ${tabId}`);
         }
         // REMOVED Clean up last output storage
         // const outputObj = await getLastOutputObject();
         // if (outputObj.hasOwnProperty(tabId)) { /* ... */ }
    } catch (error) {
        console.error(`BG: Error cleaning storage for closed tab ${tabId}:`, error);
     }
});

console.log("AI Code Capture: Background script loaded (Tab-local ports/status. No output storage)."); // Updated log
// @@FILENAME@@ extension/background.js