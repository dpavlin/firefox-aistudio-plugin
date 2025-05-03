// Default server port
const DEFAULT_PORT = 5000;
const STORAGE_TAB_PORTS_KEY = 'tabServerPorts'; // Key for the object storing ports per tab
const STORAGE_BLOCK_STATUS_KEY = 'tabBlockStatuses'; // Key for object storing block statuses per tab {tabId: {hash: status}}
// const STORAGE_LAST_OUTPUT_KEY = 'tabLastOutputs'; // REMOVED
const STORAGE_ACTIVE_KEY = 'extensionActive';

// --- Helper Functions ---

// Gets the entire object mapping tab IDs to ports
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

// Gets the entire object mapping tab IDs to block statuses {tabId: {hash: status}}
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

// Gets the port for a specific tab ID
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

// Gets status for a specific block hash in a specific tab
async function getBlockStatus(tabId, blockHash) {
    if (typeof tabId !== 'number' || !blockHash) return null; // Invalid input
    try {
        const statusObject = await getBlockStatusObject();
        return statusObject[tabId]?.[blockHash] || null; // Return status or null if not found
    } catch (error) {
        console.error(`BG Error getting status for hash ${blockHash} in tab ${tabId}:`, error);
        return null; // Return null on error
    }
}

// Sets status for a specific block hash in a specific tab
async function setBlockStatus(tabId, blockHash, status) {
    if (typeof tabId !== 'number' || !blockHash || !status) return false;
    try {
        const statusObject = await getBlockStatusObject();
        if (!statusObject[tabId]) {
            statusObject[tabId] = {}; // Initialize object for the tab if it doesn't exist
        }
        statusObject[tabId][blockHash] = status; // Set the status ('pending', 'sent', 'error')
        await browser.storage.local.set({ [STORAGE_BLOCK_STATUS_KEY]: statusObject });
        console.log(`BG: Set status for hash ${blockHash} in tab ${tabId} to ${status}`);
        return true;
    } catch (error) {
        console.error(`BG Error setting status for hash ${blockHash} in tab ${tabId}:`, error);
        return false;
    }
}


// Activation state remains global
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

// REMOVED getLastOutputObject function
// REMOVED storeLastOutput function

// --- Main Message Listener ---
browser.runtime.onMessage.addListener(async (request, sender, sendResponse) => {
  console.log("Background: Received message:", request.action, "from tab:", sender.tab?.id, request);
  const senderTabId = sender.tab?.id; // Get the sender tab ID

  // --- Port Management ---
  if (request.action === "getPort") {
        const tabIdToGet = request.tabId ?? senderTabId;
        if (typeof tabIdToGet !== 'number') {
             console.error("BG: Invalid tabId for getPort:", tabIdToGet);
             return Promise.resolve({ port: DEFAULT_PORT }); // Send default on error
        }
        const port = await getPortForTab(tabIdToGet);
        // console.log(`Background: Responding to getPort for tab ${tabIdToGet} with: ${port}`); // Less verbose
        return Promise.resolve({ port: port });
  }
  else if (request.action === "storePort") {
       const tabIdToSet = request.tabId; // Popup MUST provide this
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
        // console.log(`Background: Responding to getActivationState with: ${isActive}`); // Less verbose
        return Promise.resolve({ isActive: isActive });
   }
   else if (request.action === "storeActivationState") {
        const success = await storeActivationState(request.isActive);
        return Promise.resolve({ success: success });
    }
  // --- Block Status Management (NEW) ---
  else if (request.action === "getBlockStatus") {
       if (typeof senderTabId !== 'number' || !request.hash) {
           console.error("BG: Invalid getBlockStatus request", request);
           return Promise.resolve({ status: null });
       }
       const status = await getBlockStatus(senderTabId, request.hash);
       // console.log(`BG: Responding to getBlockStatus for hash ${request.hash} in tab ${senderTabId} with: ${status}`); // Less verbose
       return Promise.resolve({ status: status });
   }
   else if (request.action === "setBlockStatus") {
        if (typeof senderTabId !== 'number' || !request.hash || !request.status) {
            console.error("BG: Invalid setBlockStatus request", request);
            return Promise.resolve({ success: false });
        }
        const success = await setBlockStatus(senderTabId, request.hash, request.status);
        return Promise.resolve({ success: success });
    }
  // REMOVED getLastOutput handler

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
    if (!request.code || !request.hash) { // Ensure hash is included
      console.error("BG: submitCode request missing code or hash.", request);
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
      let statusToStore = 'error'; // Assume error initially

      if (!response.ok) {
          console.error(`Background: Server responded to /submit_code with status ${response.status} ${response.statusText}`);
          const errorText = await response.text().catch(() => `Server returned status ${response.status}`);
          await setBlockStatus(senderTabId, request.hash, 'error');
          // REMOVED await storeLastOutput(...)
          // Return error details for potential display or logging by content script
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
       let errorMessage = 'Network error or server unavailable.';
        const portForError = await getPortForTab(senderTabId);
       if (error instanceof TypeError && error.message.includes('NetworkError')) {
           errorMessage = `Network error connecting to port ${portForError} for tab ${senderTabId}. Is the server running?`;
       } else if (error instanceof Error) {
           errorMessage = error.message;
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
        // NOTE: This action is no longer triggered by the current popup UI for auto-run,
        // but keeping handler structure in case port setting via this route is desired later.
        if (typeof senderTabId !== 'number') {
            console.error("Background: Cannot update config - sender tab ID missing.");
            return Promise.resolve({ success: false, details: { message: 'Missing sender tab ID.' } });
        }
       try {
            const port = await getPortForTab(senderTabId);
            const url = `http://127.0.0.1:${port}/update_config`;
            const settingsToSend = {};
            // Only handle 'port' if sent via this message in the future
            if (request.settings && request.settings.hasOwnProperty('port')) {
                 settingsToSend.port = request.settings.port;
            }

             if (Object.keys(settingsToSend).length === 0) {
                 console.log("Background: No relevant settings found in updateConfig request.");
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
    } catch (error) {
        console.error(`BG: Error cleaning storage for closed tab ${tabId}:`, error);
    }
});


console.log("AI Code Capture: Background script loaded (Tab-local ports/status. No output storage)."); // Updated log
