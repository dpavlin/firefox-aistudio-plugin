// @@FILENAME@@ extension/background.js
// Default server port
const DEFAULT_PORT = 5000;
const STORAGE_TAB_PORTS_KEY = 'tabServerPorts'; // Key for the object storing ports per tab
const STORAGE_ACTIVE_KEY = 'extensionActive';

// --- Helper Functions ---

// Gets the entire object mapping tab IDs to ports
async function getTabPortsObject() {
  try {
    let data = await browser.storage.local.get(STORAGE_TAB_PORTS_KEY);
    // Return the stored object or an empty one if not found/invalid
    const portsObj = data?.[STORAGE_TAB_PORTS_KEY];
    if (typeof portsObj === 'object' && portsObj !== null) {
        return portsObj;
    }
  } catch (error) {
    console.error("Background: Error getting tab ports object:", error);
  }
  return {}; // Return empty object on error or if not found
}

// Gets the port for a specific tab ID, falling back to default
async function getPortForTab(tabId) {
    if (typeof tabId !== 'number') {
        console.warn("Background: Invalid tabId received for getPortForTab, returning default.");
        return DEFAULT_PORT;
    }
    const portsObj = await getTabPortsObject();
    const port = parseInt(portsObj[tabId], 10); // Get port specifically for this tab
    if (!isNaN(port) && port >= 1025 && port <= 65535) {
        return port;
    }
    // console.log(`Background: No specific port found for tab ${tabId}, returning default ${DEFAULT_PORT}`);
    return DEFAULT_PORT; // Fallback to default
}

// Sets the port for a specific tab ID
async function setPortForTab(tabId, port) {
    if (typeof tabId !== 'number') {
        console.error("Background: Invalid tabId received for setPortForTab.");
        return false;
    }
    const portToStore = parseInt(port, 10);
     if (isNaN(portToStore) || portToStore < 1025 || portToStore > 65535) {
         console.warn(`Background: Invalid port ${port} received for storage for tab ${tabId}.`);
         return false;
     }

    try {
        const portsObj = await getTabPortsObject();
        portsObj[tabId] = portToStore; // Update or add the port for this tab
        await browser.storage.local.set({ [STORAGE_TAB_PORTS_KEY]: portsObj });
        console.log(`Background: Stored port ${portToStore} for tab ${tabId}`);
        return true;
    } catch (error) {
        console.error(`Background: Error storing port ${portToStore} for tab ${tabId}:`, error);
        return false;
    }
}

// Activation state remains global for simplicity
async function getActivationState() {
    try {
        let data = await browser.storage.local.get(STORAGE_ACTIVE_KEY);
        return data?.[STORAGE_ACTIVE_KEY] !== false; // Default to active
    } catch (error) {
        console.error("Background: Error getting activation state:", error);
        return true; // Default to active on error
    }
}

async function storeActivationState(isActive) {
     const stateToStore = isActive === true;
     try {
         await browser.storage.local.set({ [STORAGE_ACTIVE_KEY]: stateToStore });
         console.log(`Background: Stored global activation state: ${stateToStore}`);
         return true;
     } catch (error) {
         console.error(`Background: Error storing activation state ${stateToStore}:`, error);
         return false;
     }
}

// --- Main Message Listener ---
browser.runtime.onMessage.addListener(async (request, sender, sendResponse) => {
  console.log("Background: Received message:", request.action, "from tab:", sender.tab?.id, request);
  const senderTabId = sender.tab?.id; // Get the sender tab ID

  // --- Port Management ---
  if (request.action === "getPort") {
      // Use the tabId from the request OR the sender if not provided (popup should provide)
      const tabIdToGet = request.tabId ?? senderTabId;
      if (typeof tabIdToGet !== 'number') {
          console.error("Background: Cannot get port - invalid tab ID.");
          return Promise.resolve({ port: DEFAULT_PORT }); // Send default on error
      }
      const port = await getPortForTab(tabIdToGet);
      console.log(`Background: Responding to getPort for tab ${tabIdToGet} with: ${port}`);
      return Promise.resolve({ port: port });
  }
  else if (request.action === "storePort") {
      // Use the tabId from the request (popup MUST provide this)
       const tabIdToSet = request.tabId;
       if (typeof tabIdToSet !== 'number') {
           console.error("Background: Cannot store port - invalid tab ID provided in request.");
           return Promise.resolve({ success: false, message: "Invalid tab ID" });
       }
      const success = await setPortForTab(tabIdToSet, request.port);
      return Promise.resolve({ success: success });
  }
  // --- Activation State Management (Remains Global) ---
  else if (request.action === "getActivationState") {
        const isActive = await getActivationState();
        console.log(`Background: Responding to getActivationState with: ${isActive}`);
        return Promise.resolve({ isActive: isActive });
   }
   else if (request.action === "storeActivationState") {
        const success = await storeActivationState(request.isActive);
        return Promise.resolve({ success: success });
    }
  // --- Server Interaction ---
  else if (request.action === "submitCode") {
    const isActive = await getActivationState();
    if (!isActive) {
        console.log("Background: Extension inactive, ignoring submitCode.");
         return Promise.resolve({ success: false, details: { status: 'inactive', message: 'Extension is currently inactive.' } });
    }
     if (typeof senderTabId !== 'number') {
         console.error("Background: Cannot submit code - sender tab ID missing.");
         return Promise.resolve({ success: false, details: { status: 'error', message: 'Missing sender tab ID.' } });
     }
    if (!request.code) {
      console.error("Background: Received submitCode request with no code.");
      return Promise.resolve({ success: false, details: { status: 'error', message: 'No code provided in message.' } });
    }

    try {
      // *** Use the port specific to the sender tab ***
      const port = await getPortForTab(senderTabId);
      const url = `http://127.0.0.1:${port}/submit_code`;
      console.log(`Background: Sending code from tab ${senderTabId} to ${url}`);

      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({ code: request.code })
      });

      if (!response.ok) {
          console.error(`Background: Server responded to /submit_code with status ${response.status} ${response.statusText}`);
          const errorText = await response.text().catch(() => `Server returned status ${response.status}`);
           return Promise.resolve({ success: false, details: { status: 'error', message: `Server error: ${response.status} ${response.statusText}`, server_response: errorText } });
      }

      const data = await response.json();
      console.log("Background: Received response from server for /submit_code:", data);
      return Promise.resolve({ success: data.status === 'success', details: data });

    } catch (error) {
      console.error("Background: Error fetching /submit_code:", error);
       let errorMessage = 'Network error or server unavailable.';
        const portForError = await getPortForTab(senderTabId); // Get port again for error msg
       if (error instanceof TypeError && error.message.includes('NetworkError')) {
           errorMessage = `Network error connecting to port ${portForError} for tab ${senderTabId}. Is the server running?`;
       } else if (error instanceof Error) {
           errorMessage = error.message;
       }
       return Promise.resolve({ success: false, details: { status: 'error', message: errorMessage } });
    }
  }
  else if (request.action === "testConnection") {
     // Test Connection still uses the port explicitly passed from the popup's input field
     try {
          const port = request.port; // Port comes from popup input
          if (isNaN(port) || port < 1025 || port > 65535) {
              throw new Error(`Invalid port specified in request: ${port}`);
          }
          const url = `http://127.0.0.1:${port}/test_connection`;
          console.log(`Background: Testing connection to ${url} (requested by popup)`);
          const response = await fetch(url, {cache: "no-store"});
          if (!response.ok) {
               // Try to get more details if possible
               const errorText = await response.text().catch(() => `Server returned status ${response.status}`);
               throw new Error(`Server responded with status ${response.status}. Response: ${errorText}`);
          }
          const data = await response.json();
          console.log("Background: Test connection successful:", data);
          // We send back the details reported by the server at that port
          return Promise.resolve({ success: true, details: data });
      } catch (error) {
           console.error("Background: Test connection failed:", error);
           return Promise.resolve({ success: false, details: { status: 'error', message: error.message || 'Connection failed' } });
      }
  }
   else if (request.action === "updateConfig") {
        // NOTE: This action is no longer triggered by the current popup UI for auto-run,
        // but keeping handler structure in case other config options (like port) are added later.
        if (typeof senderTabId !== 'number') {
            console.error("Background: Cannot update config - sender tab ID missing.");
            return Promise.resolve({ success: false, details: { message: 'Missing sender tab ID.' } });
        }
       try {
            const port = await getPortForTab(senderTabId); // Use port associated with the sending tab
            const url = `http://127.0.0.1:${port}/update_config`;
            // Filter settings to only include relevant ones if needed in future
            const settingsToSend = {};
            // Example: If port setting could be sent from popup to save in server_config.json
            if (request.settings && request.settings.hasOwnProperty('port')) {
                 const portToSet = parseInt(request.settings.port, 10);
                 if (!isNaN(portToSet) && portToSet >= 1025 && portToSet <= 65535) {
                    settingsToSend.port = portToSet;
                 } else {
                     console.warn("Background: Invalid port value in updateConfig settings, ignoring.");
                 }
            }
            // ** REMOVED auto_run_python / auto_run_shell handling **

            // If no valid settings were found to send, return early
             if (Object.keys(settingsToSend).length === 0) {
                 console.log("Background: No applicable settings found in updateConfig request.");
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
    try {
        const portsObj = await getTabPortsObject();
        if (portsObj.hasOwnProperty(tabId)) {
            delete portsObj[tabId];
            await browser.storage.local.set({ [STORAGE_TAB_PORTS_KEY]: portsObj });
            console.log(`Background: Removed port setting for closed tab ${tabId}`);
        }
    } catch (error) {
        console.error(`Background: Error removing port setting for closed tab ${tabId}:`, error);
    }
});


console.log("AI Code Capture: Background script loaded (Tab-local ports, No auto-run UI).");
