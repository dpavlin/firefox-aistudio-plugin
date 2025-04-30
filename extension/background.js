console.log("Background script (v3 - Per-Tab Port) loaded.");

// --- Storage Keys & Default Port ---
const ACTIVATION_STORAGE_KEY = 'isActivated';
const PORT_STORAGE_KEY = 'serverPort'; // Stores the *default* port
const LAST_RESPONSE_STORAGE_KEY = 'lastServerResponse';
const DEFAULT_PORT = 5000;

// --- State & Request Mapping ---
let isExtensionActivated = true; // Default assumption, updated from storage
const tabPortMap = new Map(); // Map: tabId -> portNumber
const codeRequestMap = new Map(); // Map: captureId -> { tabId: number, originalCode: string }

// --- Function to get current GLOBAL/DEFAULT settings ---
async function getDefaultSettings() {
  return new Promise((resolve) => {
    chrome.storage.local.get([ACTIVATION_STORAGE_KEY, PORT_STORAGE_KEY], (result) => {
      if (chrome.runtime.lastError) {
        console.error("Error reading default settings:", chrome.runtime.lastError.message);
        resolve({ activated: true, port: DEFAULT_PORT }); // Fallback to defaults
      } else {
        resolve({
          activated: result.isActivated !== undefined ? result.isActivated : true,
          port: result.serverPort !== undefined ? parseInt(result.serverPort, 10) || DEFAULT_PORT : DEFAULT_PORT
        });
      }
    });
  });
}

// --- Initialize default state & load current global state ---
chrome.runtime.onInstalled.addListener(async () => {
  const settings = await getDefaultSettings();
  isExtensionActivated = settings.activated; // Update global state variable
  // Ensure default port is set if not present
  if (settings.port === DEFAULT_PORT) {
     chrome.storage.local.set({ [PORT_STORAGE_KEY]: DEFAULT_PORT });
  }
  // Ensure last response exists
  chrome.storage.local.get([LAST_RESPONSE_STORAGE_KEY], (res) => {
      if (res.lastServerResponse === undefined) {
           chrome.storage.local.set({ [LAST_RESPONSE_STORAGE_KEY]: "Ready." });
      }
   });
  console.log("Default activation/port state checked/set. Initial active state:", isExtensionActivated);
});

// Load initial global activation state when the script starts
getDefaultSettings().then(settings => {
  isExtensionActivated = settings.activated;
  console.log("Background script loaded initial global state: Activated =", isExtensionActivated);
});


// --- Listen for storage changes (only for global activation state) ---
chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName === 'local' && changes[ACTIVATION_STORAGE_KEY]) {
        isExtensionActivated = changes[ACTIVATION_STORAGE_KEY].newValue;
        console.log(`Background script updated global activation state: ${isExtensionActivated}`);
        // Note: Port changes are handled via messages now, not directly from storage change
    }
});

// --- Clean up map when tabs are closed ---
chrome.tabs.onRemoved.addListener((tabId, removeInfo) => {
    if (tabPortMap.has(tabId)) {
        tabPortMap.delete(tabId);
        console.log(`Removed port mapping for closed tab: ${tabId}`);
    }
    // Also clean up any pending requests associated with the closed tab
    for (const [captureId, requestInfo] of codeRequestMap.entries()) {
        if (requestInfo.tabId === tabId) {
            codeRequestMap.delete(captureId);
            console.log(`Removed pending request mapping for closed tab ${tabId}, capture ID ${captureId}`);
        }
    }
});


// --- Message Listener ---
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const senderTabId = sender?.tab?.id;
  console.log("Background received message:", message, "from sender tab:", senderTabId);

  // --- Handler for direct sending from content script ---
  if (message.action === 'sendCodeDirectly' && message.code && message.captureId) {
    const requestKey = message.captureId;
    if (senderTabId) {
         // Map capture ID to tab ID and original code
         codeRequestMap.set(requestKey, { tabId: senderTabId, originalCode: message.code });
         console.log(`Mapping capture ID "${requestKey}" to tab ${senderTabId}`);
         // Clean up map entry after a delay
         setTimeout(() => {
            if (codeRequestMap.delete(requestKey)) {
                 console.log(`Cleaned up mapping for capture ID "${requestKey}"`);
            }
         }, 35000); // Increased timeout slightly
    } else {
         console.warn("Sender tab ID not available for 'sendCodeDirectly'. Cannot process.");
         return false;
    }

    // Use the globally tracked activation state
    if (isExtensionActivated) {
      console.log("Extension activated. Calling sendCodeToServer for capture ID:", requestKey);
      sendCodeToServer(message.code, requestKey); // Pass code AND captureId
    } else {
      console.log("Extension disabled. Ignoring code sent from content script.");
      codeRequestMap.delete(requestKey); // Remove mapping if not activated
    }
    return false; // Sync response
  }
  // --- Handler for Popup Requesting Data ---
  else if (message.action === 'getPopupData') {
      const requestingTabId = message.tabId; // Popup should now send its tab ID
      console.log(`Popup (Tab ID: ${requestingTabId}) requested data.`);
      if (!requestingTabId) {
          console.error("Popup did not provide its Tab ID.");
          sendResponse({ error: "Missing Tab ID from popup." });
          return true;
      }
      // Get global activation and last response, and tab-specific port
      chrome.storage.local.get([LAST_RESPONSE_STORAGE_KEY], async (storageResult) => {
           const defaultSettings = await getDefaultSettings(); // Get default port
           const tabSpecificPort = tabPortMap.get(requestingTabId);
           const portToSend = tabSpecificPort !== undefined ? tabSpecificPort : defaultSettings.port;

           const responsePayload = {
              activated: isExtensionActivated, // Global activation state
              port: portToSend,
              lastResponse: storageResult.lastServerResponse || "No response yet."
          };
          console.log("Sending data to popup:", responsePayload);
          sendResponse(responsePayload);
      });
      return true; // Async response
  }
  // --- Handler for Popup Setting Activation State (Remains Global) ---
  else if (message.action === 'setActivationState') {
      const newState = message.activated;
      console.log(`Saving global activation state from popup: ${newState}`);
      chrome.storage.local.set({ [ACTIVATION_STORAGE_KEY]: newState }, () => {
          if (chrome.runtime.lastError) {
              console.error("Error saving activation state:", chrome.runtime.lastError);
              sendResponse({success: false, error: chrome.runtime.lastError.message});
          } else {
              console.log("Activation state saved.");
              isExtensionActivated = newState; // Update background's immediate state
              sendResponse({success: true});
              // Notify content scripts if activation changed? Maybe not necessary.
          }
      });
      return true; // Async response
  }
   // --- Handler for Popup Setting Port (Now Per-Tab) ---
  else if (message.action === 'setServerPort') {
      const newPort = parseInt(message.port, 10);
      const targetTabId = message.tabId; // Get tab ID from popup message

      if (!targetTabId) {
          console.error("Popup did not provide Tab ID when setting port.");
          sendResponse({ success: false, error: 'Missing Tab ID.' });
          return true;
      }
      if (isNaN(newPort) || newPort < 1025 || newPort > 65535) {
          console.error(`Invalid port number received from popup: ${message.port}`);
          sendResponse({ success: false, error: 'Invalid port number.' });
          return true;
      }

      console.log(`Setting server port for Tab ID ${targetTabId} to: ${newPort}`);
      tabPortMap.set(targetTabId, newPort); // Store in the map for this specific tab

      // Also update the *default* port in storage.local
      // This means the last port set in *any* popup becomes the default for new tabs.
      chrome.storage.local.set({ [PORT_STORAGE_KEY]: newPort }, () => {
           if (chrome.runtime.lastError) {
               console.error("Error saving default server port:", chrome.runtime.lastError);
               // Proceed even if default save fails, map is primary for current tabs
           } else {
                console.log("Default server port updated in storage.");
           }
           sendResponse({success: true}); // Acknowledge the update
      });
      return true; // Async response
  }
  // --- Handler for Popup Requesting Port (Now Per-Tab) ---
  else if (message.action === 'getServerPort') {
       const requestingTabId = message.tabId; // Get tab ID from popup message
       console.log(`Popup (Tab ID: ${requestingTabId}) requested server port.`);
        if (!requestingTabId) {
            console.error("Popup did not provide its Tab ID for getServerPort.");
            sendResponse({ error: "Missing Tab ID from popup." });
            return true;
        }
       getDefaultSettings().then(defaultSettings => {
            const tabSpecificPort = tabPortMap.get(requestingTabId);
            const portToSend = tabSpecificPort !== undefined ? tabSpecificPort : defaultSettings.port;
            console.log(`Sending port ${portToSend} to popup for tab ${requestingTabId}`);
            sendResponse({ port: portToSend });
       });
       return true; // Indicate async response
   }
  else {
      console.log("Received unknown message action:", message.action);
  }
});


// --- Function to send the captured code to the local Flask server ---
async function sendCodeToServer(codeToSend, captureId) {
    // *** Get the originating tab ID from the map ***
    const requestInfo = codeRequestMap.get(captureId);
    if (!requestInfo || !requestInfo.tabId) {
        console.error(`Could not find originating tab ID for capture ID: ${captureId}. Cannot send to server.`);
        // Maybe send an error back to content script? Requires modifying mapping again.
        return;
    }
    const originatingTabId = requestInfo.tabId;

    // *** Get the port for THIS tab, fallback to default ***
    const defaultSettings = await getDefaultSettings();
    const portToUse = tabPortMap.get(originatingTabId) || defaultSettings.port;
    // *****************************************************

    const url = `http://localhost:${portToUse}/submit_code`;
    console.log(`Attempting to send code (ID: ${captureId}, Tab: ${originatingTabId}) to server at ${url}`);
    let responseDataForStorage = null;
    let serverResponseOk = false;

    try {
        // Fetch logic remains mostly the same...
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', },
            body: JSON.stringify({ code: codeToSend }), // Send original code
        });

        console.log(`Fetch response status for ID ${captureId}: ${response.status}`);
        const responseText = await response.text();
        console.log("Raw server response text received:", responseText);

        try {
            responseDataForStorage = JSON.parse(responseText);
            console.log("Server response parsed successfully:", responseDataForStorage);
            if (response.ok && responseDataForStorage.status === 'success') {
                 if (responseDataForStorage.git_updated === false && responseDataForStorage.source_file_marker) {
                     console.warn("Server reported success but Git update failed for marker file.");
                     serverResponseOk = false;
                     responseDataForStorage.status = 'error';
                     responseDataForStorage.message = 'File saved but Git commit failed.';
                 } else { serverResponseOk = true; }
            } else {
                 console.error(`Server responded with non-OK status: ${response.status} or error status in JSON.`);
                 serverResponseOk = false;
                 if (!responseDataForStorage.status || responseDataForStorage.status !== 'error') {
                     responseDataForStorage.status = 'error';
                     responseDataForStorage.message = responseDataForStorage.message || `Server returned status ${response.status}.`;
                 }
            }
        } catch (parseError) {
            console.error("Failed to parse server response as JSON:", parseError); console.error("Raw text was:", responseText);
            responseDataForStorage = { status: "error", message: `Invalid JSON (Status: ${response.status}). ${responseText.substring(0, 100)}...` };
            serverResponseOk = false;
        }
    } catch (error) {
        console.error(`!!! Network error sending code (ID: ${captureId}, Tab: ${originatingTabId}) to ${url}:`, error);
        responseDataForStorage = { status: "error", message: `Network Error: ${error.message}. Is server running on port ${portToUse}?` };
        serverResponseOk = false;
    }

    // --- Store the last response (globally) and notify popup/content script ---
    if (responseDataForStorage) {
        chrome.storage.local.set({ [LAST_RESPONSE_STORAGE_KEY]: responseDataForStorage }, () => {
            if (chrome.runtime.lastError) { console.error("Error saving last response:", chrome.runtime.lastError.message); }
            else { console.log("Last server response saved."); }

            // Send detailed response back to specific content script tab
            console.log(`Sending processing result (Success: ${serverResponseOk}) for ID ${captureId} back to tab ${originatingTabId}`);
            chrome.tabs.sendMessage(originatingTabId, {
                action: 'serverProcessingComplete',
                captureId: captureId,
                success: serverResponseOk,
                details: responseDataForStorage
            }).catch(err => {
                console.warn(`Could not send processing result to content script tab ${originatingTabId}:`, err.message);
            });
            codeRequestMap.delete(captureId); // Clean up map entry

            // Update any open popup (still shows the global last response)
            chrome.runtime.sendMessage({action: 'updatePopupResponse', lastResponse: responseDataForStorage}).catch(err => {
                if (!err.message.includes("Receiving end does not exist")) {
                   console.warn("Could not send response update to popup:", err.message);
                }
            });
        });
    } else {
        console.error("responseDataForStorage was unexpectedly null after fetch attempt.");
         // Clean up map entry even on failure to get response data
         if (codeRequestMap.has(captureId)) {
             codeRequestMap.delete(captureId);
             console.log(`Cleaned up mapping for capture ID "${captureId}" due to null response data.`);
         }
    }
}

console.log("Background script finished loading.");