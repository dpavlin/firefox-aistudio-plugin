// @@FILENAME@@ extension/background.js
'use strict';

console.log("Background script (v8 - Per-Tab Port) loaded.");

// --- Globals for settings ---
let defaultServerPort = 5000; // Default port (used if no tab-specific one is set)
let isActivated = true;     // Global activation state
const tabPortMap = new Map(); // Map: tabId -> portNumber

// --- Load initial DEFAULT settings from storage ---
function loadInitialSettings() {
    // Only load global settings: default port and activation state
    return browser.storage.local.get(['port', 'isActivated'])
        .then(result => {
            let defaultPortChanged = false;
            if (result.port !== undefined && typeof result.port === 'number' && result.port >= 1025 && result.port <= 65535) {
                defaultServerPort = result.port;
            } else {
                // Default Port not set or invalid, save default
                console.log("Default Port not found or invalid in storage, using default:", defaultServerPort);
                browser.storage.local.set({ port: defaultServerPort }); // Save the default global port
                defaultPortChanged = true;
            }

            if (result.isActivated !== undefined && typeof result.isActivated === 'boolean') {
                isActivated = result.isActivated;
            } else {
                // Activation state not set, save default
                console.log("Activation state not found in storage, using default:", isActivated);
                browser.storage.local.set({ isActivated: isActivated }); // Save the default
            }
            console.log(`Initial settings loaded: Default Port=${defaultServerPort}, Activated=${isActivated}`);
            if (defaultPortChanged) {
                 console.log("Default port setting saved to storage.");
            }
        })
        .catch(error => {
            console.error("Error loading initial settings from storage:", error);
            // Keep hardcoded defaults if loading fails
            defaultServerPort = 5000;
            isActivated = true;
        });
}

// --- Initialization ---
(async () => {
    await loadInitialSettings();
    console.log("Background script initialization complete after loading settings.");
})();


// --- Listener for extension installation/update ---
browser.runtime.onInstalled.addListener(details => {
    console.log("Extension installed/updated:", details.reason);
    loadInitialSettings().then(() => {
         console.log("Settings re-verified/defaults set on install/update. Current:", { defaultPort: defaultServerPort, isActivated: isActivated });
    });
    // Clear the transient tab map on update/install
    tabPortMap.clear();
    console.log("Tab-port map cleared on install/update.");
});

// --- NEW: Listener for Tab Closure ---
browser.tabs.onRemoved.addListener((tabId, removeInfo) => {
    if (tabPortMap.has(tabId)) {
        tabPortMap.delete(tabId);
        console.log(`Removed port mapping for closed tab: ${tabId}. Map size: ${tabPortMap.size}`);
    }
});


// --- Function to send status updates TO the popup ---
async function sendStatusToPopup(message, type = 'info') {
     /* ... (implementation unchanged) ... */
     console.log(`Background sending status to popup: ${message} (Type: ${type})`);
     try {
         const views = browser.extension.getViews({ type: "popup" });
         if (views.length > 0) {
             await browser.runtime.sendMessage({ action: "updatePopupStatus", message: message, type: type });
              console.log("Status message sent to popup.");
         } else { console.log("Popup not open, status message not sent."); }
     } catch (error) { console.error("Error sending status message to popup:", error); }
}

// --- Helper to get port for a given tab ID ---
function getPortForTab(tabId) {
    // Return tab-specific port if set, otherwise return the global default
    const port = tabPortMap.get(tabId) || defaultServerPort;
    // console.log(`getPortForTab(${tabId}): Found=${tabPortMap.has(tabId)}, Port=${port}`); // Debugging - can be noisy
    return port;
}


// --- Main Message Listener ---
browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
    // Determine the originating tab ID if possible
    // Messages from popup should include 'tabId', messages from content script use sender.tab.id
    const originatingTabId = message.tabId || sender?.tab?.id;
    const source = message.tabId ? "Popup" : (sender?.tab?.id ? `Content Script (Tab ${sender.tab.id})` : "Other/Unknown");

    console.log(`Background received message: `, message, ` From: ${source}`);

    // --- Get Settings (for Popup) ---
    if (message.action === "getSettings") {
        if (!originatingTabId) {
            console.error("getSettings: Originating Tab ID missing.");
            return Promise.reject(new Error("Tab ID required for getSettings"));
        }
        const portForThisTab = getPortForTab(originatingTabId);
        const settingsResponse = { port: portForThisTab, isActivated: isActivated };
        console.log(`Background responding to getSettings for Tab ${originatingTabId} with:`, settingsResponse);
        return Promise.resolve(settingsResponse);
    }
    // --- Update Setting (from Popup) ---
    else if (message.action === "updateSetting") {
        if (!originatingTabId) {
            console.error("updateSetting: Originating Tab ID missing.");
            return Promise.reject(new Error("Tab ID required for updateSetting"));
        }
        // Update GLOBAL activation state
        if (message.key === "isActivated") {
            const newState = Boolean(message.value);
            isActivated = newState;
            browser.storage.local.set({ isActivated: isActivated }) // Save global state
                .then(() => console.log("Saved GLOBAL activation state to storage:", isActivated))
                .catch(err => console.error("Error saving activation state:", err));
            // Optionally notify other content scripts/popups? Might be complex.
            return Promise.resolve({ success: true });
        }
        // Update TAB-SPECIFIC port mapping (Does NOT change defaultServerPort or storage)
        else if (message.key === "port") {
            const newPort = parseInt(message.value, 10);
            if (!isNaN(newPort) && newPort >= 1025 && newPort <= 65535) {
                tabPortMap.set(originatingTabId, newPort);
                console.log(`Set port for Tab ${originatingTabId} to ${newPort}. Current map:`, tabPortMap);
                return Promise.resolve({ success: true }); // Acknowledge update for this tab
            } else {
                console.warn("Invalid port value received for update:", message.value);
                return Promise.reject(new Error("Invalid port number"));
            }
        }
        // Update DEFAULT port (if we add a separate UI element later)
        // else if (message.key === "defaultPort") { ... }
        else {
            console.warn("Unknown setting key received for update:", message.key);
            return Promise.reject(new Error("Unknown setting key"));
        }
    }
    // --- Test Connection / Get Server Config (from Popup) ---
    else if (message.action === "testConnection" || message.action === "getServerConfig") {
         if (!originatingTabId) {
            console.error(`${message.action}: Originating Tab ID missing.`);
            return Promise.reject(new Error(`Tab ID required for ${message.action}`));
         }
        const portToUse = getPortForTab(originatingTabId); // Use tab-specific or default port
        const endpoint = (message.action === "testConnection") ? "test_connection" : "status";
        const url = `http://127.0.0.1:${portToUse}/${endpoint}`;
        console.log(`Background action '${message.action}' for Tab ${originatingTabId}: Fetching ${url}`);

        return fetch(url, { method: 'GET', mode: 'cors' })
            .then(response => {
                if (!response.ok) {
                     // Try to parse error even on bad status
                     return response.json().catch(() => null).then(errorData => {
                         throw new Error(`Server Error (Status ${response.status}): ${errorData?.message || response.statusText || 'Unknown server error'}`);
                     });
                 }
                return response.json();
            })
            .then(data => {
                 console.log(`${message.action} successful for Tab ${originatingTabId}. Server response:`, data);
                 // Send back success and the *full* data from the server
                 return { success: true, data: data };
             })
            .catch(error => {
                 console.error(`${message.action} for Tab ${originatingTabId}: Network or fetch error:`, error);
                 // Send back failure and the error message
                 return { success: false, error: error.message };
             });
        // Return the promise chain
    }
    // --- Update Server Config File (from Popup) ---
     else if (message.action === "updateServerConfig") {
        // This action modifies the JSON file, affecting future server starts.
        // It also modifies the *currently running* server's auto-run flags.
        // It needs the config functions passed from server.py
        if (!current_app?.config?.['save_config_func']) { // Check if function reference exists
            console.error("updateServerConfig: save_config_func not available in app context.");
             return Promise.resolve({ success: false, error: "Server integration error (missing save func)." });
        }
        const save_config_func = current_app.config['save_config_func'];
        const runtime_config = current_app.config['APP_CONFIG'];

        const configKey = message.key; // Should be auto_run_python or auto_run_shell
        const configValue = message.value;
        const live_update_keys = ['auto_run_python', 'auto_run_shell'];

        if (configKey !== 'auto_run_python' && configKey !== 'auto_run_shell') {
              console.error("Background: Invalid key for server config update:", configKey);
              return Promise.reject(new Error("Invalid server configuration key"));
        }

        // 1. Update live runtime config immediately
        let runtime_updated = false;
        if (runtime_config[configKey] !== configValue) {
            runtime_config[configKey] = configValue;
            runtime_updated = true;
            console.log(`RUNTIME update: ${configKey} set to ${configValue}.`);
        }

        // 2. Prepare data to save to file
        const payload = { [configKey]: configValue };
        console.log(`Background preparing to save server config update:`, payload);

        // 3. Save to file (This is synchronous within the server thread, but the message handling is async)
        const [save_success, saved_data] = save_config_func(payload);

        if (save_success) {
            const message = `Server config file updated. ${runtime_updated ? 'Setting applied immediately.' : 'No runtime change needed.'}`;
             return Promise.resolve({ success: true, message: message });
        } else {
            // If save failed, should we revert the runtime change? Potentially complex.
            // For now, just report the save failure.
            console.error("Failed to save config to file after runtime update.");
             return Promise.resolve({ success: false, message: "Failed to save config file." });
        }
        // Note: This specific handler assumes it's running within the server's context
        // where current_app is available. If background.js were truly separate,
        // it would need to send a message *to* the server for this action.
     }
    // --- Submit Code (from Content Script) ---
    else if (message.action === "submitCode") {
        if (!isActivated) {
            console.log("Background: Received code submission, but extension is deactivated. Ignoring.");
            return Promise.resolve({ success: false, details: { message: 'Extension is deactivated.' } }); // Return details structure
        }
        if (!originatingTabId) {
            console.error("submitCode: Originating Tab ID missing from sender.");
            return Promise.resolve({ success: false, details: { message: 'Internal Error: Missing sender tab ID.' } });
        }

        const codeData = message.data;
        const portToUse = getPortForTab(originatingTabId); // Use tab-specific or default port
        const url = `http://127.0.0.1:${portToUse}/submit_code`;
        console.log(`Background submitting code for Tab ${originatingTabId} to: ${url}`);

        return fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', },
            mode: 'cors',
            body: JSON.stringify({ code: codeData })
        })
        .then(response => response.json().catch(err => {
             console.error(`Failed to parse JSON response from ${url}:`, err);
             return response.text().then(text => {
                 throw new Error(`Server response not JSON. Status: ${response.status}. Body: ${text || '(empty)'}`);
             });
        }))
        .then(data => {
            console.log(`Background received server response for Tab ${originatingTabId}:`, data);
            if (data && (data.status === 'success' || data.git_updated === true)) {
                return { success: true, details: data };
            } else {
                console.warn(`Server reported failure or unexpected status for Tab ${originatingTabId}:`, data);
                return { success: false, details: data || { message: "Unknown server error format."} };
            }
        })
        .catch(error => {
            console.error(`Background fetch error during code submission for Tab ${originatingTabId} to ${url}:`, error);
            return { success: false, details: { message: `Network/Fetch Error: ${error.message}` } };
        });
        // The promise chain is returned automatically
    }

    // If message.action is none of the above
    console.log("Background: Message action not recognized or improperly handled:", message.action);
    return false; // Indicate message not handled synchronously if no promise was returned
});

console.log("Background script message listeners registered.");
// @@FILENAME@@ extension/background.js