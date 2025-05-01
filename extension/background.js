'use strict';

console.log("Background script (v7 - Popup CWD) loaded.");

// --- Globals for settings ---
let serverPort = 5000; // Default port
let isActivated = true;  // Default activation state

// --- Load initial settings from storage ---
function loadInitialSettings() {
    // ... (keep existing implementation)
    return browser.storage.local.get(['port', 'isActivated'])
        .then(result => {
            let changed = false;
            if (result.port !== undefined && typeof result.port === 'number' && result.port >= 1025 && result.port <= 65535) {
                serverPort = result.port;
            } else {
                console.log("Port not found or invalid in storage, using default:", serverPort);
                browser.storage.local.set({ port: serverPort });
                changed = true;
            }

            if (result.isActivated !== undefined && typeof result.isActivated === 'boolean') {
                isActivated = result.isActivated;
            } else {
                console.log("Activation state not found in storage, using default:", isActivated);
                browser.storage.local.set({ isActivated: isActivated });
                changed = true;
            }
            console.log(`Initial settings loaded: Port=${serverPort}, Activated=${isActivated}`);
            if (changed) {
                 console.log("Default setting(s) saved to storage.");
            }
        })
        .catch(error => {
            console.error("Error loading settings from storage:", error);
        });
}

// --- Initialization ---
(async () => {
    await loadInitialSettings();
    console.log("Background script initialization complete after loading settings.");
})();


// --- Listener for extension installation/update ---
browser.runtime.onInstalled.addListener(details => {
    // ... (keep existing implementation)
    console.log("Extension installed/updated:", details.reason);
    loadInitialSettings().then(() => {
         console.log("Settings re-verified/defaults set on install/update. Current:", { port: serverPort, isActivated: isActivated });
    });
});

// --- Function to send status updates TO the popup ---
async function sendStatusToPopup(message, type = 'info') {
     // ... (keep existing implementation)
     console.log(`Background sending status to popup: ${message} (Type: ${type})`);
     try {
         const views = browser.extension.getViews({ type: "popup" });
         if (views.length > 0) {
             await browser.runtime.sendMessage({ action: "updatePopupStatus", message: message, type: type });
             console.log("Status message sent to popup.");
         } else {
             console.log("Popup not open, status message not sent.");
         }
     } catch (error) {
         console.error("Error sending status message to popup:", error);
     }
}


// --- Main Message Listener ---
browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log(`Background received message: `, message, ` From: ${sender.tab ? `Tab ID ${sender.tab.id}` : "Popup/Other"}`);

    if (message.action === "getSettings") {
        // ... (keep existing implementation)
        console.log("Background responding with settings:", { port: serverPort, isActivated: isActivated });
        return Promise.resolve({ port: serverPort, isActivated: isActivated });
    }
    else if (message.action === "updateSetting") {
        // ... (keep existing implementation)
        if (message.key === "port") {
            const newPort = parseInt(message.value, 10);
            if (!isNaN(newPort) && newPort >= 1025 && newPort <= 65535) {
                serverPort = newPort;
                browser.storage.local.set({ port: serverPort })
                    .then(() => console.log("Saved new port to storage:", serverPort))
                    .catch(err => console.error("Error saving port:", err));
                return Promise.resolve({ success: true });
            } else { return Promise.reject(new Error("Invalid port number")); }
        } else if (message.key === "isActivated") {
            const newState = Boolean(message.value);
            isActivated = newState;
            browser.storage.local.set({ isActivated: isActivated })
                .then(() => console.log("Saved new activation state to storage:", isActivated))
                .catch(err => console.error("Error saving activation state:", err));
            return Promise.resolve({ success: true });
        } else { return Promise.reject(new Error("Unknown setting key")); }
    }
    else if (message.action === "testConnection") {
        // ... (keep existing implementation - it already gets full status)
        const url = `http://127.0.0.1:${serverPort}/test_connection`;
        console.log(`Background testing connection to: ${url}`);
        fetch(url, { method: 'GET', mode: 'cors' })
            .then(response => {
                if (!response.ok) {
                    return response.json().catch(() => null).then(errorData => {
                         sendResponse({ success: false, error: `Server Error (Status ${response.status})`, data: errorData || { error: response.statusText } });
                    });
                }
                return response.json();
            })
            .then(data => {
                 if (data) {
                      console.log("Test Connection successful. Server response:", data);
                      sendResponse({ success: true, data: data }); // Already sends full status data
                 } else {
                      // Handle case where response is ok but data is null/undefined (maybe non-JSON response?)
                      sendResponse({ success: false, error: 'Received OK status but invalid/empty data from server.' });
                 }
            })
            .catch(error => {
                console.error("Test Connection: Network or fetch error:", error);
                sendResponse({ success: false, error: `Network/Fetch Error: ${error.message}` });
            });
        return true;
    }
    else if (message.action === "getServerConfig") {
        // *** MODIFIED: Return the full status data ***
        const url = `http://127.0.0.1:${serverPort}/status`;
        console.log(`Background getting server config/status from: ${url}`);

        fetch(url, { method: 'GET', mode: 'cors' })
            .then(response => {
                if (!response.ok) { throw new Error(`Server responded with status ${response.status}`); }
                return response.json();
            })
            .then(data => {
                console.log("Background received server status/config:", data);
                // Send the whole data object back, popup will extract what it needs
                sendResponse({ success: true, data: data });
            })
            .catch(error => {
                console.error("Background fetch error getting server config/status:", error);
                sendResponse({ success: false, error: `Failed to fetch server info: ${error.message}` });
            });
        return true; // Indicate async response
    }
     else if (message.action === "updateServerConfig") {
         // ... (keep existing implementation)
         const url = `http://127.0.0.1:${serverPort}/update_config`;
         const configKey = message.key;
         const configValue = message.value;
         if (configKey !== 'enable_python_run' && configKey !== 'enable_shell_run') {
              return Promise.reject(new Error("Invalid server configuration key"));
         }
         const payload = {};
         payload[configKey] = configValue;
         console.log(`Background sending server config update to ${url}:`, payload);
         fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, mode: 'cors', body: JSON.stringify(payload) })
         .then(response => response.json().catch(err => {
              return response.text().then(text => { throw new Error(`Server response not JSON. Status: ${response.status}. Body: ${text || '(empty)'}`); });
         }))
         .then(data => {
              console.log("Background received response from /update_config:", data);
              if (data && data.status === 'success') { sendResponse({ success: true, message: data.message }); }
              else { sendResponse({ success: false, message: data?.message || 'Server returned error or unexpected response.' }); }
         })
         .catch(error => {
              console.error("Background fetch error updating server config:", error);
              sendResponse({ success: false, error: `Network/Fetch Error: ${error.message}` });
         });
         return true;
     }
    else if (message.action === "submitCode") {
        // ... (keep existing implementation)
        if (!isActivated) { return Promise.resolve({ status: 'ignored', message: 'Extension is deactivated.' }); }
        const codeData = message.data;
        const url = `http://127.0.0.1:${serverPort}/submit_code`;
        console.log(`Background submitting code to: ${url}`);
        return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', }, mode: 'cors', body: JSON.stringify({ code: codeData }) })
        .then(response => response.json().catch(err => {
             return response.text().then(text => { throw new Error(`Server response not JSON. Status: ${response.status}. Body: ${text || '(empty)'}`); });
        }))
        .then(data => {
            console.log("Background received server response for code submission:", data);
            if (data && (data.status === 'success' || data.git_updated === true)) { return { success: true, details: data }; }
            else { console.warn("Server reported failure or unexpected status:", data); return { success: false, details: data || { message: "Unknown server error format."} }; }
        })
        .catch(error => {
            console.error("Background fetch error during code submission:", error);
            return { success: false, details: { message: `Network/Fetch Error: ${error.message}` } };
        });
    }

    console.log("Background: Message action not recognized:", message.action);
    return false;
});

console.log("Background script message listeners registered.");
// @@FILENAME@@ extension/background.js