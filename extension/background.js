'use strict';

console.log("Background script (v9 - Fix updateServerConfig context) loaded.");

// --- Globals for settings ---
let defaultServerPort = 5000;
let isActivated = true;
const tabPortMap = new Map();

// --- Load initial DEFAULT settings ---
function loadInitialSettings() {
    return browser.storage.local.get(['port', 'isActivated'])
        .then(result => {
            let defaultPortChanged = false;
            if (result.port !== undefined && typeof result.port === 'number' && result.port >= 1025 && result.port <= 65535) {
                defaultServerPort = result.port;
            } else {
                browser.storage.local.set({ port: defaultServerPort }); defaultPortChanged = true;
            }
            if (result.isActivated !== undefined && typeof result.isActivated === 'boolean') {
                isActivated = result.isActivated;
            } else { browser.storage.local.set({ isActivated: isActivated }); }
            console.log(`Initial settings loaded: Default Port=${defaultServerPort}, Activated=${isActivated}`);
            if (defaultPortChanged) { console.log("Default port setting saved."); }
        })
        .catch(error => { console.error("Error loading initial settings:", error); defaultServerPort = 5000; isActivated = true; });
}

// --- Initialization ---
(async () => { await loadInitialSettings(); console.log("Background init complete."); })();

// --- Listener for extension installation/update ---
browser.runtime.onInstalled.addListener(details => {
    console.log("Extension installed/updated:", details.reason);
    loadInitialSettings().then(() => { console.log("Settings re-verified. Current:", { defaultPort: defaultServerPort, isActivated: isActivated }); });
    tabPortMap.clear(); console.log("Tab-port map cleared.");
});

// --- Listener for Tab Closure ---
browser.tabs.onRemoved.addListener((tabId, removeInfo) => {
    if (tabPortMap.has(tabId)) { tabPortMap.delete(tabId); console.log(`Removed port mapping for closed tab: ${tabId}.`); }
});

// --- Function to send status updates TO the popup ---
async function sendStatusToPopup(message, type = 'info') { /* ... unchanged ... */ console.log(`Background sending status: ${message}`); try { const views = browser.extension.getViews({ type: "popup" }); if (views.length > 0) { await browser.runtime.sendMessage({ action: "updatePopupStatus", message: message, type: type }); } } catch (error) { console.error("Error sending status to popup:", error); } }

// --- Helper to get port for a given tab ID ---
function getPortForTab(tabId) { return tabPortMap.get(tabId) || defaultServerPort; }

// --- Main Message Listener ---
browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
    const originatingTabId = message.tabId || sender?.tab?.id;
    const source = message.tabId ? "Popup" : (sender?.tab?.id ? `Content Script (Tab ${sender.tab.id})` : "Other");
    console.log(`Background received message: `, message, ` From: ${source}`);

    // --- Get Settings (for Popup) ---
    if (message.action === "getSettings") {
        if (!originatingTabId) return Promise.reject(new Error("Tab ID required"));
        const portForThisTab = getPortForTab(originatingTabId);
        return Promise.resolve({ port: portForThisTab, isActivated: isActivated });
    }
    // --- Update Setting (from Popup) ---
    else if (message.action === "updateSetting") {
        if (!originatingTabId) return Promise.reject(new Error("Tab ID required"));
        if (message.key === "isActivated") {
            isActivated = Boolean(message.value);
            browser.storage.local.set({ isActivated: isActivated }).catch(err => console.error("Error saving activation:", err));
            return Promise.resolve({ success: true });
        } else if (message.key === "port") {
            const newPort = parseInt(message.value, 10);
            if (!isNaN(newPort) && newPort >= 1025 && newPort <= 65535) {
                tabPortMap.set(originatingTabId, newPort);
                console.log(`Set port for Tab ${originatingTabId} to ${newPort}. Map:`, tabPortMap);
                return Promise.resolve({ success: true });
            } else { return Promise.reject(new Error("Invalid port number")); }
        } else { return Promise.reject(new Error("Unknown setting key")); }
    }
    // --- Test Connection / Get Server Config (from Popup) ---
    else if (message.action === "testConnection" || message.action === "getServerConfig") {
         if (!originatingTabId) return Promise.reject(new Error(`Tab ID required for ${message.action}`));
         const portToUse = getPortForTab(originatingTabId);
         const endpoint = (message.action === "testConnection") ? "test_connection" : "status";
         const url = `http://127.0.0.1:${portToUse}/${endpoint}`;
         console.log(`Background '${message.action}' for Tab ${originatingTabId}: Fetching ${url}`);
         return fetch(url, { method: 'GET', mode: 'cors' })
             .then(response => { if (!response.ok) { return response.json().catch(()=>null).then(errData => { throw new Error(`Server Error (${response.status}): ${errData?.message || response.statusText || 'Unknown'}`); }); } return response.json(); })
             .then(data => ({ success: true, data: data }))
             .catch(error => ({ success: false, error: error.message }));
    }
    // --- Update Server Config File (from Popup) ---
     else if (message.action === "updateServerConfig") {
         // *** REMOVED incorrect current_app checks and direct modification ***
         if (!originatingTabId) return Promise.reject(new Error(`Tab ID required for ${message.action}`));

         const portToUse = getPortForTab(originatingTabId); // Use correct port for this tab's target server
         const url = `http://127.0.0.1:${portToUse}/update_config`;
         const configKey = message.key; // Should be auto_run_python or auto_run_shell
         const configValue = message.value;

         // Key validation already happened in popup, but double check if needed
         if (configKey !== 'auto_run_python' && configKey !== 'auto_run_shell') {
              console.error("Background: Invalid key for server config update:", configKey);
              return Promise.resolve({ success: false, error: "Invalid server configuration key" }); // Use resolve for consistency
         }

         const payload = { [configKey]: configValue }; // e.g., { "auto_run_python": true }

         console.log(`Background sending server config update to ${url}:`, payload);

         // Perform the fetch request to the server
         return fetch(url, {
             method: 'POST',
             headers: { 'Content-Type': 'application/json' },
             mode: 'cors',
             body: JSON.stringify(payload)
         })
         .then(response => response.json().catch(err => {
              return response.text().then(text => { throw new Error(`Server response not JSON (Status ${response.status}): ${text || '(empty)'}`); });
         }))
         .then(data => {
              console.log("Background received response from /update_config:", data);
              // Relay server's response back to popup
              return { success: data?.status === 'success', message: data?.message };
         })
         .catch(error => {
              console.error("Background fetch error updating server config:", error);
              // Send failure details back to popup
              return { success: false, error: `Network/Fetch Error: ${error.message}` };
         });
         // The promise chain is returned
     }
    // --- Submit Code (from Content Script) ---
    else if (message.action === "submitCode") {
        if (!isActivated) return Promise.resolve({ success: false, details: { message: 'Extension is deactivated.' } });
        if (!originatingTabId) return Promise.resolve({ success: false, details: { message: 'Internal Error: Missing sender tab ID.' } });

        const codeData = message.data;
        const portToUse = getPortForTab(originatingTabId);
        const url = `http://127.0.0.1:${portToUse}/submit_code`;
        console.log(`Background submitting code for Tab ${originatingTabId} to: ${url}`);
        return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', }, mode: 'cors', body: JSON.stringify({ code: codeData }) })
        .then(response => response.json().catch(err => { return response.text().then(text => { throw new Error(`Server response not JSON (Status ${response.status}): ${text || '(empty)'}`); }); }))
        .then(data => {
            if (data && (data.status === 'success' || data.git_updated === true)) { return { success: true, details: data }; }
            else { console.warn(`Server fail/unexpected status for Tab ${originatingTabId}:`, data); return { success: false, details: data || { message: "Unknown server error format."} }; }
        })
        .catch(error => { console.error(`Background fetch error during code submission for Tab ${originatingTabId}:`, error); return { success: false, details: { message: `Network/Fetch Error: ${error.message}` } }; });
    }

    console.log("Background: Message action not recognized:", message.action);
    return false;
});

console.log("Background script message listeners registered.");
// @@FILENAME@@ extension/background.js