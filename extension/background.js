// @@FILENAME@@ extension/background.js
'use strict';

console.log("Background script (v5 - Popup Logic Added) loaded.");

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
                // Port not set or invalid, save default
                console.log("Port not found or invalid in storage, using default:", serverPort);
                browser.storage.local.set({ port: serverPort }); // Save the default
                changed = true;
            }

            if (result.isActivated !== undefined && typeof result.isActivated === 'boolean') {
                isActivated = result.isActivated;
            } else {
                // Activation state not set, save default
                console.log("Activation state not found in storage, using default:", isActivated);
                browser.storage.local.set({ isActivated: isActivated }); // Save the default
                changed = true;
            }
            console.log(`Initial settings loaded: Port=${serverPort}, Activated=${isActivated}`);
            if (changed) {
                 console.log("Default setting(s) saved to storage.");
            }
        })
        .catch(error => {
            console.error("Error loading settings from storage:", error);
            // Keep defaults if loading fails
        });
}

// --- Initialization ---
// Use an async IIFE to ensure settings are loaded before listeners are fully active (optional but safer)
(async () => {
    await loadInitialSettings();
    console.log("Background script initialization complete after loading settings.");
})();


// --- Listener for extension installation/update ---
browser.runtime.onInstalled.addListener(details => {
    console.log("Extension installed/updated:", details.reason);
    // Re-check settings on install/update, ensures defaults are set if storage was cleared
    loadInitialSettings().then(() => {
         console.log("Settings re-verified/defaults set on install/update. Current:", { port: serverPort, isActivated: isActivated });
    });
});

// --- Function to send status updates TO the popup ---
async function sendStatusToPopup(message, type = 'info') {
     console.log(`Background sending status to popup: ${message} (Type: ${type})`);
     try {
         // Find the popup window (if open)
         const views = browser.extension.getViews({ type: "popup" });
         if (views.length > 0) {
              // Send message directly to the popup context
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
        // Send the current settings back to the requester (e.g., popup)
        console.log("Background responding with settings:", { port: serverPort, isActivated: isActivated });
        // Use Promise.resolve for async response
        return Promise.resolve({ port: serverPort, isActivated: isActivated });
    }
    else if (message.action === "updateSetting") {
        // Update a specific setting and save it
        if (message.key === "port") {
            const newPort = parseInt(message.value, 10);
            if (!isNaN(newPort) && newPort >= 1025 && newPort <= 65535) {
                serverPort = newPort;
                browser.storage.local.set({ port: serverPort })
                    .then(() => console.log("Saved new port to storage:", serverPort))
                    .catch(err => console.error("Error saving port:", err));
                // Optionally send confirmation back - not strictly needed if popup updates UI immediately
                // sendStatusToPopup(`Port updated to ${serverPort}`, 'success');
                return Promise.resolve({ success: true }); // Acknowledge receipt
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
             // sendStatusToPopup(`Activation state updated to ${isActivated}`, 'success');
            return Promise.resolve({ success: true }); // Acknowledge receipt
        } else {
            console.warn("Unknown setting key received for update:", message.key);
            return Promise.reject(new Error("Unknown setting key"));
        }
    }
    else if (message.action === "testConnection") {
        // Handle connection test request from popup
        const url = `http://127.0.0.1:${serverPort}/test_connection`;
        console.log(`Background testing connection to: ${url}`);

        fetch(url, { method: 'GET', mode: 'cors' }) // mode:'cors' is important
            .then(response => {
                if (!response.ok) {
                    // Server responded, but with an error status (4xx, 5xx)
                    console.error(`Test Connection: Server responded with status ${response.status}`);
                    // Try to get error message from server response body
                    return response.json().catch(() => null).then(errorData => {
                         // Send back failure status and any parsed error data or status text
                         sendResponse({
                             success: false,
                             error: `Server Error (Status ${response.status})`,
                             data: errorData || { error: response.statusText } // Send parsed JSON error or status text
                         });
                    });
                }
                // Response is OK (2xx status)
                return response.json(); // Assume server sends JSON status back
            })
            .then(data => {
                // This block runs only if response.ok was true
                 if (data) { // Check if data was successfully parsed from JSON
                      console.log("Test Connection successful. Server response:", data);
                      sendResponse({ success: true, data: data }); // Send success and server data
                 }
                 // If response was ok but body wasn't JSON or was empty, data might be null/undefined
                 // We already sent the response in the !response.ok block if status was bad
                 // Or if response was ok but parsing failed in the .catch below
            })
            .catch(error => {
                // Network error (server down, DNS issue, CORS denied by server *if server doesn't send headers*)
                console.error("Test Connection: Network or fetch error:", error);
                sendResponse({ success: false, error: `Network/Fetch Error: ${error.message}` });
            });

        return true; // Indicate that sendResponse will be called asynchronously
    }
    else if (message.action === "submitCode") {
        // --- Handle code submission from content script ---
        if (!isActivated) {
            console.log("Background: Received code submission, but extension is deactivated. Ignoring.");
            // Send failure back to content script immediately
            return Promise.resolve({ status: 'ignored', message: 'Extension is deactivated.' });
        }

        const codeData = message.data;
        const url = `http://127.0.0.1:${serverPort}/submit_code`;
        console.log(`Background submitting code to: ${url}`);

        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            mode: 'cors', // Ensure CORS is handled
            body: JSON.stringify({ code: codeData })
        })
        .then(response => response.json().catch(err => {
             // Handle cases where server response isn't valid JSON
             console.error("Failed to parse JSON response from server:", err);
             // Try to get text response instead
             return response.text().then(text => {
                 throw new Error(`Server response not JSON. Status: ${response.status}. Body: ${text || '(empty)'}`);
             });
        }))
        .then(data => {
            console.log("Background received server response for code submission:", data);
            // Check server's custom status field
            if (data && (data.status === 'success' || data.git_updated === true)) { // Consider git update a success too
                return { success: true, details: data }; // Forward server's detailed success response
            } else {
                // Server reported an error or unexpected status
                console.warn("Server reported failure or unexpected status:", data);
                return { success: false, details: data || { message: "Unknown server error format."} };
            }
        })
        .catch(error => {
            console.error("Background fetch error during code submission:", error);
            // Network error or failed fetch/JSON parse
            return { success: false, details: { message: `Network/Fetch Error: ${error.message}` } };
        });

        // Note: The promise returned by fetch/then/catch is automatically used as the response
        // No need for return true/sendResponse here when returning the promise chain.
    }


    // If message.action is none of the above, return false or undefined
    console.log("Background: Message action not recognized:", message.action);
    return false; // Indicate message not handled synchronously
});

console.log("Background script message listeners registered.");
// @@FILENAME@@ extension/background.js