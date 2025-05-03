// Default server port
const DEFAULT_PORT = 5000;
const STORAGE_TAB_PORTS_KEY = 'tabServerPorts'; // Key for the object storing ports per tab
const STORAGE_BLOCK_STATUS_KEY = 'tabBlockStatuses'; // Key for object storing block statuses per tab {tabId: {hash: status}}
const STORAGE_LAST_OUTPUT_KEY = 'tabLastOutputs'; // NEW: Key for {tabId: {stdout:..., stderr:...}}
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


// *** MODIFY getLasyOutputObject helper for more robust logging ***
async function getLastOutputObject() {
    console.log("BG DEBUG: Entering getLastOutputObject"); // Log entry
    try {
        let data = await browser.storage.local.get(STORAGE_LAST_OUTPUT_KEY);
        console.log("BG DEBUG: Raw data from storage.local.get:", data); // Log raw storage result
        const outputObj = data?.[STORAGE_LAST_OUTPUT_KEY];
        if (typeof outputObj === 'object' && outputObj !== null) {
            console.log("BG DEBUG: Found valid output object in storage:", outputObj);
            return outputObj;
        } else {
             console.log("BG DEBUG: No valid output object found in storage (key:", STORAGE_LAST_OUTPUT_KEY, "). Returning empty object.");
             return {}; // Return empty if not found or invalid type
        }
    } catch (error) {
        console.error("BG Error in getLastOutputObject:", error); // Log error specifically here
        return {}; // Return empty object on error
    }
}



// NEW: Store output details for a tab
async function storeLastOutput(tabId, outputDetails) {
     if (typeof tabId !== 'number') return false;
     try {
         const outputObj = await getLastOutputObject();
         // Store only relevant fields
         outputObj[tabId] = {
            timestamp: new Date().toISOString(), // Add timestamp for context
            syntax_stdout: outputDetails?.syntax_stdout || null,
            syntax_stderr: outputDetails?.syntax_stderr || null,
            run_stdout: outputDetails?.run_stdout || null,
            run_stderr: outputDetails?.run_stderr || null
         };
         await browser.storage.local.set({ [STORAGE_LAST_OUTPUT_KEY]: outputObj });
         console.log(`BG: Stored last output for tab ${tabId}`);
         return true;
     } catch (error) {
         console.error(`BG Error storing last output for tab ${tabId}:`, error);
         return false;
     }
}

// --- Main Message Listener ---
browser.runtime.onMessage.addListener(async (request, sender, sendResponse) => {
  console.log("Background: Received message:", request.action, "from tab:", sender.tab?.id, request);
  const senderTabId = sender.tab?.id; // Get the sender tab ID

  // --- Port Management ---
  if (request.action === "getPort") {
        const tabIdToGet = request.tabId ?? senderTabId;
        if (typeof tabIdToGet !== 'number') {
             return Promise.resolve({ port: DEFAULT_PORT }); // Error handling
        }
        const port = await getPortForTab(tabIdToGet);
        return Promise.resolve({ port: port });
  }
  else if (request.action === "storePort") {
       const tabIdToSet = request.tabId; // Popup MUST provide this
       if (typeof tabIdToSet !== 'number') {
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
  // --- Block Status Management (NEW) ---
  else if (request.action === "getBlockStatus") {
       if (typeof senderTabId !== 'number' || !request.hash) {
           console.error("BG: Invalid getBlockStatus request", request);
           return Promise.resolve({ status: null });
       }
       const status = await getBlockStatus(senderTabId, request.hash);
       // console.log(`BG: Responding to getBlockStatus for hash ${request.hash} in tab ${senderTabId} with: ${status}`);
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

  // --- NEW: Get Last Output ---
   else if (request.action === "getLastOutput") {
        console.log("BG DEBUG: Handling getLastOutput action"); // Log handler entry
        const tabIdToGet = request.tabId ?? senderTabId;
         if (typeof tabIdToGet !== 'number') {
             console.error("BG: Invalid tabId for getLastOutput:", tabIdToGet);
             // *** Explicitly return promise with null ***
             return Promise.resolve({ output: null });
         }
         console.log(`BG DEBUG: Attempting to get output object for tabId: ${tabIdToGet}`);
         const outputObj = await getLastOutputObject(); // Calls the enhanced helper
         const lastOutput = outputObj?.[tabIdToGet] || null; // Use optional chaining for safety
         console.log(`BG DEBUG: Retrieved output for tab ${tabIdToGet}:`, lastOutput); // Log the specific result
         // *** Explicitly return promise with retrieved output ***
         return Promise.resolve({ output: lastOutput });
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
    if (!request.code || !request.hash) { // Ensure hash is included
      console.error("BG: submitCode request missing code or hash.", request);
      return Promise.resolve({ success: false, details: { status: 'error', message: 'Missing code or hash in submitCode request.' } });
    }

    try {
      // *** Use the port specific to the sender tab ***
      const port = await getPortForTab(senderTabId);
      const url = `http://127.0.0.1:${port}/submit_code`;
      console.log(`BG: Sending code from tab ${senderTabId} to ${url} (Hash: ${request.hash})`);

      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({ code: request.code })
      });

      // IMPORTANT: Update block status storage after server response
      let serverResponseData = null;
      let fetchSuccess = false;
      let statusToStore = 'error'; // Assume error initially

      if (!response.ok) {
          console.error(`Background: Server responded to /submit_code with status ${response.status} ${response.statusText}`);
          const errorText = await response.text().catch(() => `Server returned status ${response.status}`);
          await setBlockStatus(senderTabId, request.hash, 'error');
          await storeLastOutput(senderTabId, { run_stderr: `Server Error ${response.status}: ${errorText}` }); // Store server error in stderr
          return Promise.resolve({ success: false, details: { status: 'error', message: `Server error: ${response.status} ${response.statusText}`, server_response: errorText } });
      } else {
          serverResponseData = await response.json();
          fetchSuccess = serverResponseData.status === 'success';
          statusToStore = fetchSuccess ? 'sent' : 'error';
          console.log("BG: Received response from server for /submit_code:", serverResponseData);
          // *** Store the relevant output details ***
          await storeLastOutput(senderTabId, serverResponseData);
          await setBlockStatus(senderTabId, request.hash, statusToStore);
          return Promise.resolve({ success: fetchSuccess, details: serverResponseData });
      }

    } catch (error) {
      console.error("Background: Error fetching /submit_code:", error);
       let errorMessage = 'Network error or server unavailable.';
        const portForError = await getPortForTab(senderTabId); // Get port again for error msg
       if (error instanceof TypeError && error.message.includes('NetworkError')) {
           errorMessage = `Network error connecting to port ${portForError} for tab ${senderTabId}. Is the server running?`;
       } else if (error instanceof Error) {
           errorMessage = error.message;
       }
       await setBlockStatus(senderTabId, request.hash, 'error');
       await storeLastOutput(senderTabId, { run_stderr: `Fetch Error: ${errorMessage}` }); // Store fetch error in stderr
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
          const response = await fetch(url, {cache: "no-store"}); // Prevent caching
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
        // NOTE: This action is no longer triggered by the current popup UI,
        // but keeping handler structure in case other config options are added later.
        if (typeof senderTabId !== 'number') {
            console.error("Background: Cannot update config - sender tab ID missing.");
            return Promise.resolve({ success: false, details: { message: 'Missing sender tab ID.' } });
        }
       try {
            const port = await getPortForTab(senderTabId); // Use port associated with the sending tab
            const url = `http://127.0.0.1:${port}/update_config`;
            // Filter settings to only include relevant ones if needed in future
            const settingsToSend = {};
            if (request.settings && request.settings.hasOwnProperty('port')) { // Example if port could be set this way
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
         // Clean up last output storage
         const outputObj = await getLastOutputObject();
          if (outputObj.hasOwnProperty(tabId)) {
              delete outputObj[tabId];
              await browser.storage.local.set({ [STORAGE_LAST_OUTPUT_KEY]: outputObj });
              console.log(`BG: Removed last output for closed tab ${tabId}`);
          }
    } catch (error) {
        console.error(`BG: Error cleaning storage for closed tab ${tabId}:`, error);
     }
});

console.log("AI Code Capture: Background script loaded (Tab-local ports/status/output).");
