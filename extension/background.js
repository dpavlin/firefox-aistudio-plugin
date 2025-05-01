// @@FILENAME@@ extension/background.js
'use strict';

console.log("Background script (v6 - Server Config Edit) loaded.");

// --- Globals for settings ---
let serverPort = 5000; // Default port
let isActivated = true;  // Default activation state

// --- Load initial settings from storage ---
function loadInitialSettings() {
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
    console.log("Extension installed/updated:", details.reason);
    loadInitialSettings().then(() => {
         console.log("Settings re-verified/defaults set on install/update. Current:", { port: serverPort, isActivated: isActivated });
    });
});

// --- Function to send status updates TO the popup ---
// (No changes needed for this function)
async function sendStatusToPopup(message, type = 'info') {
     console.log(`Background sending status to popup: ${message} (Type: ${type})`);
     try {
         const views = browser.extension.getViews({ type: "popup" });
         if (views.length > 0) {
             await browser.runtime.sendMessage({
                 action: "updatePopupStatus",
                 message: message,
                 type: type
             });
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
        console.log("Background responding with settings:", { port: serverPort, isActivated: isActivated });
        return Promise.resolve({ port: serverPort, isActivated: isActivated });
    }
    else if (message.action === "updateSetting") {
        // (No changes needed for port/isActivated update)
        if (message.key === "port") {
            const newPort = parseInt(message.value, 10);
            if (!isNaN(newPort) && newPort >= 1025 && newPort <= 65535) {
                serverPort = newPort;
                browser.storage.local.set({ port: serverPort })
                    .then(() => console.log("Saved new port to storage:", serverPort))
                    .catch(err => console.error("Error saving port:", err));
                return Promise.resolve({ success: true });
            } else {
                console.warn("Invalid port value received for update:", message.value);
                return Promise.reject(new Error("Invalid port number"));
            }
        } else if (message.key === "isActivated") {
            const newState = Boolean(message.value);
            isActivated = newState;
            browser.storage.local.set({ isActivated: isActivated })
                .then(() => console.log("Saved new activation state to storage:", isActivated))
                .catch(err => console.error("Error saving activation state:", err));
            return Promise.resolve({ success: true });
        } else {
            console.warn("Unknown setting key received for update:", message.key);
            return Promise.reject(new Error("Unknown setting key"));
        }
    }
    else if (message.action === "testConnection") {
        // (No changes needed)
        const url = `http://127.0.0.1:${serverPort}/test_connection`; // Use /test_connection (which calls get_status)
        console.log(`Background testing connection to: ${url}`);
        fetch(url, { method: 'GET', mode: 'cors' })
            .then(response => {
                if (!response.ok) {
                    return response.json().catch(() => null).then(errorData => {
                         sendResponse({
                             success: false,
                             error: `Server Error (Status ${response.status})`,
                             data: errorData || { error: response.statusText }
                         });
                    });
                }
                return response.json();
            })
            .then(data => {
                 if (data) {
                      console.log("Test Connection successful. Server response:", data);
                      sendResponse({ success: true, data: data });
                 }
            })
            .catch(error => {
                console.error("Test Connection: Network or fetch error:", error);
                sendResponse({ success: false, error: `Network/Fetch Error: ${error.message}` });
            });
        return true; // Indicate async response
    }
    else if (message.action === "getServerConfig") {
        // --- NEW: Get current config from server's status endpoint ---
        const url = `http://127.0.0.1:${serverPort}/status`; // Reuse /status as it contains config
        console.log(`Background getting server config from: ${url}`);

        fetch(url, { method: 'GET', mode: 'cors' })
            .then(response => {
                if (!response.ok) {
                    // Throw an error to be caught by the catch block
                    throw new Error(`Server responded with status ${response.status}`);
                }
                return response.json(); // Expect server status JSON
            })
            .then(data => {
                console.log("Background received server status/config:", data);
                // Extract relevant config fields (use the actual runtime state reported by /status)
                 const configData = {
                     auto_run_python: data?.auto_run_python, // Use running state from status
                     auto_run_shell: data?.auto_run_shell,   // Use running state from status
                     // Add other relevant fields from /status if needed later
                 };
                sendResponse({ success: true, data: configData });
            })
            .catch(error => {
                console.error("Background fetch error getting server config:", error);
                sendResponse({ success: false, error: `Failed to fetch server config: ${error.message}` });
            });
        return true; // Indicate async response
    }
     else if (message.action === "updateServerConfig") {
         // --- NEW: Send update request to server's config endpoint ---
         const url = `http://127.0.0.1:${serverPort}/update_config`;
         const configKey = message.key;
         const configValue = message.value;

         // Ensure the key is one we allow updating this way
         if (configKey !== 'enable_python_run' && configKey !== 'enable_shell_run') {
              console.error("Background: Invalid key for server config update:", configKey);
              return Promise.reject(new Error("Invalid server configuration key"));
         }

         const payload = {};
         payload[configKey] = configValue; // e.g., { "enable_python_run": true }

         console.log(`Background sending server config update to ${url}:`, payload);

         fetch(url, {
             method: 'POST',
             headers: { 'Content-Type': 'application/json' },
             mode: 'cors',
             body: JSON.stringify(payload)
         })
         .then(response => response.json().catch(err => { // Handle non-JSON responses gracefully
              console.error("Failed to parse JSON response from /update_config:", err);
              return response.text().then(text => {
                  throw new Error(`Server response not JSON. Status: ${response.status}. Body: ${text || '(empty)'}`);
              });
         }))
         .then(data => {
              console.log("Background received response from /update_config:", data);
              // Check the server's response structure for success/message
              if (data && data.status === 'success') {
                   sendResponse({ success: true, message: data.message }); // Forward server message
              } else {
                   // Server reported an error or unexpected status
                   sendResponse({ success: false, message: data?.message || 'Server returned error or unexpected response.' });
              }
         })
         .catch(error => {
              console.error("Background fetch error updating server config:", error);
              sendResponse({ success: false, error: `Network/Fetch Error: ${error.message}` });
         });

         return true; // Indicate async response
     }
    else if (message.action === "submitCode") {
        // (No changes needed)
        if (!isActivated) {
            console.log("Background: Received code submission, but extension is deactivated. Ignoring.");
            return Promise.resolve({ status: 'ignored', message: 'Extension is deactivated.' });
        }
        const codeData = message.data;
        const url = `http://127.0.0.1:${serverPort}/submit_code`;
        console.log(`Background submitting code to: ${url}`);
        return fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', },
            mode: 'cors',
            body: JSON.stringify({ code: codeData })
        })
        .then(response => response.json().catch(err => {
             console.error("Failed to parse JSON response from server:", err);
             return response.text().then(text => {
                 throw new Error(`Server response not JSON. Status: ${response.status}. Body: ${text || '(empty)'}`);
             });
        }))
        .then(data => {
            console.log("Background received server response for code submission:", data);
            if (data && (data.status === 'success' || data.git_updated === true)) {
                return { success: true, details: data };
            } else {
                console.warn("Server reported failure or unexpected status:", data);
                return { success: false, details: data || { message: "Unknown server error format."} };
            }
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