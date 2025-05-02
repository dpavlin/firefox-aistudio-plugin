// @@FILENAME@@ extension/background.js
// Default server port
const DEFAULT_PORT = 5000;
const STORAGE_TAB_PORTS_KEY = 'tabServerPorts'; // Key for the object storing ports per tab
const STORAGE_ACTIVE_KEY = 'extensionActive';

// --- Helper Functions ---
// getTabPortsObject, getPortForTab, setPortForTab, getActivationState, storeActivationState
// ... (These functions remain the same as the previous fix) ...
async function getTabPortsObject() { /* ... */ }
async function getPortForTab(tabId) { /* ... */ }
async function setPortForTab(tabId, port) { /* ... */ }
async function getActivationState() { /* ... */ }
async function storeActivationState(isActive) { /* ... */ }

// --- Main Message Listener ---
browser.runtime.onMessage.addListener(async (request, sender, sendResponse) => {
  console.log("Background: Received message:", request.action, "from tab:", sender.tab?.id, request);
  const senderTabId = sender.tab?.id;

  // --- Port Management ---
  if (request.action === "getPort") {
      // ... (remains the same) ...
  }
  else if (request.action === "storePort") {
      // ... (remains the same) ...
  }
  // --- Activation State Management (Remains Global) ---
  else if (request.action === "getActivationState") {
      // ... (remains the same) ...
   }
   else if (request.action === "storeActivationState") {
      // ... (remains the same) ...
    }
  // --- Server Interaction ---
  else if (request.action === "submitCode") {
    // ... (remains the same - uses getPortForTab(senderTabId)) ...
  }
  else if (request.action === "testConnection") {
     // ... (remains the same - uses request.port) ...
  }
   else if (request.action === "updateConfig") {
        // NOTE: This action is no longer triggered by the current popup UI,
        // but keeping handler structure in case other config options are added later.
        if (typeof senderTabId !== 'number') {
            console.error("Background: Cannot update config - sender tab ID missing.");
            return Promise.resolve({ success: false, details: { message: 'Missing sender tab ID.' } });
        }
       try {
            const port = await getPortForTab(senderTabId);
            const url = `http://127.0.0.1:${port}/update_config`;
            // Filter settings to only include relevant ones if needed in future
            const settingsToSend = {};
            if (request.settings && request.settings.hasOwnProperty('port')) { // Example if port could be set this way
                 settingsToSend.port = request.settings.port;
            }
            // ** REMOVED auto_run_python / auto_run_shell handling **
            // if (request.settings && request.settings.hasOwnProperty('auto_run_python')) {
            //      settingsToSend.auto_run_python = request.settings.auto_run_python;
            // }
            // ... etc ...

            // If no valid settings were found to send, maybe return early?
             if (Object.keys(settingsToSend).length === 0) {
                 console.log("Background: No relevant settings found in updateConfig request.");
                 // Maybe return info instead of error? Depends on expected use.
                 return Promise.resolve({ success: true, details: { message: "No applicable settings to update.", status: "info"} });
             }

            console.log(`Background: Sending config update for tab ${senderTabId} to ${url}`, settingsToSend);
            const response = await fetch(url, {
                 method: 'POST',
                 headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                 body: JSON.stringify(settingsToSend) // Send only relevant settings
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

  // Default fallback if action not handled
  console.warn(`Background: Unhandled message action: ${request.action}`);
  return Promise.resolve({ success: false, details: { message: `Unhandled action: ${request.action}` }});

});

// --- Tab Close Listener ---
browser.tabs.onRemoved.addListener(async (tabId, removeInfo) => {
    // ... (remains the same) ...
});

console.log("AI Code Capture: Background script loaded (Tab-local ports, No auto-run UI).");