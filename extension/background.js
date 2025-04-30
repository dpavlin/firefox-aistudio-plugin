// @@FILENAME@@ background.js
console.log("Background script (v4 - Test Connection) loaded.");

// --- Storage Keys & Default Port ---
const ACTIVATION_STORAGE_KEY = 'isActivated';
const PORT_STORAGE_KEY = 'serverPort';
const LAST_RESPONSE_STORAGE_KEY = 'lastServerResponse';
const DEFAULT_PORT = 5000;

// --- State & Request Mapping ---
let isExtensionActivated = true;
const tabPortMap = new Map(); // Map: tabId -> portNumber
const codeRequestMap = new Map(); // Map: captureId -> { tabId: number, originalCode: string }

// --- Function to get current GLOBAL/DEFAULT settings ---
async function getDefaultSettings() {
  return new Promise((resolve) => {
    chrome.storage.local.get([ACTIVATION_STORAGE_KEY, PORT_STORAGE_KEY], (result) => {
      if (chrome.runtime.lastError) {
        console.error("Error reading default settings:", chrome.runtime.lastError.message);
        resolve({ activated: true, port: DEFAULT_PORT });
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
  isExtensionActivated = settings.activated;
  if (settings.port === DEFAULT_PORT) { chrome.storage.local.set({ [PORT_STORAGE_KEY]: DEFAULT_PORT }); }
  chrome.storage.local.get([LAST_RESPONSE_STORAGE_KEY], (res) => {
      if (res.lastServerResponse === undefined) { chrome.storage.local.set({ [LAST_RESPONSE_STORAGE_KEY]: "Ready." }); }
   });
  console.log("Default activation/port state checked/set. Initial active state:", isExtensionActivated);
});

// Load initial global activation state when the script starts
getDefaultSettings().then(settings => { isExtensionActivated = settings.activated; });

// --- Listen for storage changes (only for global activation state) ---
chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName === 'local' && changes[ACTIVATION_STORAGE_KEY]) {
        isExtensionActivated = changes[ACTIVATION_STORAGE_KEY].newValue;
        console.log(`Background script updated global activation state: ${isExtensionActivated}`);
    }
});

// --- Clean up map when tabs are closed ---
chrome.tabs.onRemoved.addListener((tabId, removeInfo) => {
    if (tabPortMap.has(tabId)) { tabPortMap.delete(tabId); console.log(`Removed port mapping for closed tab: ${tabId}`); }
    for (const [captureId, requestInfo] of codeRequestMap.entries()) {
        if (requestInfo.tabId === tabId) { codeRequestMap.delete(captureId); console.log(`Removed pending request mapping for closed tab ${tabId}, capture ID ${captureId}`); }
    }
});

// --- Helper to save and broadcast last response ---
function updateLastResponse(responseData) {
    chrome.storage.local.set({ [LAST_RESPONSE_STORAGE_KEY]: responseData }, () => {
        if (chrome.runtime.lastError) { console.error("Error saving last server response:", chrome.runtime.lastError.message); }
        else { console.log("Last server response saved to storage."); }
        // Update any open popup
        chrome.runtime.sendMessage({action: 'updatePopupResponse', lastResponse: responseData}).catch(err => {
            if (!err.message.includes("Receiving end does not exist")) { console.warn("Could not send response update to popup:", err.message); }
        });
    });
}

// --- Message Listener ---
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const senderTabId = sender?.tab?.id;
  console.log("Background received message:", message, "from sender tab:", senderTabId);

  // --- Handler for direct sending from content script ---
  if (message.action === 'sendCodeDirectly' && message.code && message.captureId) {
    const requestKey = message.captureId;
    if (senderTabId) {
         codeRequestMap.set(requestKey, { tabId: senderTabId, originalCode: message.code });
         console.log(`Mapping capture ID "${requestKey}" to tab ${senderTabId}`);
         setTimeout(() => { if (codeRequestMap.delete(requestKey)) { console.log(`Cleaned up mapping for capture ID "${requestKey}"`); } }, 35000);
    } else { console.warn("Sender tab ID not available for 'sendCodeDirectly'. Cannot process."); return false; }
    if (isExtensionActivated) { console.log("Extension activated. Calling sendCodeToServer for capture ID:", requestKey); sendCodeToServer(message.code, requestKey); }
    else { console.log("Extension disabled. Ignoring code."); codeRequestMap.delete(requestKey); }
    return false;
  }
  // --- Handler for Popup Requesting Data ---
  else if (message.action === 'getPopupData') {
      const requestingTabId = message.tabId;
      if (!requestingTabId) { console.error("Popup did not provide Tab ID."); sendResponse({ error: "Missing Tab ID from popup." }); return true; }
      console.log(`Popup (Tab ID: ${requestingTabId}) requested data.`);
      chrome.storage.local.get([LAST_RESPONSE_STORAGE_KEY], async (storageResult) => {
           const defaultSettings = await getDefaultSettings();
           const tabSpecificPort = tabPortMap.get(requestingTabId);
           const portToSend = tabSpecificPort !== undefined ? tabSpecificPort : defaultSettings.port;
           const responsePayload = { activated: isExtensionActivated, port: portToSend, lastResponse: storageResult.lastServerResponse || "No response yet." };
           console.log("Sending data to popup:", responsePayload);
           sendResponse(responsePayload);
      });
      return true; // Async response
  }
  // --- Handler for Popup Setting Activation State (Global) ---
  else if (message.action === 'setActivationState') {
      const newState = message.activated;
      console.log(`Saving global activation state from popup: ${newState}`);
      chrome.storage.local.set({ [ACTIVATION_STORAGE_KEY]: newState }, () => {
          if (chrome.runtime.lastError) { console.error("Error saving activation state:", chrome.runtime.lastError); sendResponse({success: false, error: chrome.runtime.lastError.message}); }
          else { console.log("Activation state saved."); isExtensionActivated = newState; sendResponse({success: true}); }
      });
      return true;
  }
   // --- Handler for Popup Setting Port (Per-Tab + Default) ---
  else if (message.action === 'setServerPort') {
      const newPort = parseInt(message.port, 10); const targetTabId = message.tabId;
      if (!targetTabId) { console.error("Popup did not provide Tab ID when setting port."); sendResponse({ success: false, error: 'Missing Tab ID.' }); return true; }
      if (isNaN(newPort) || newPort < 1025 || newPort > 65535) { console.error(`Invalid port number: ${message.port}`); sendResponse({ success: false, error: 'Invalid port number.' }); return true; }
      console.log(`Setting server port for Tab ID ${targetTabId} to: ${newPort}`);
      tabPortMap.set(targetTabId, newPort);
      chrome.storage.local.set({ [PORT_STORAGE_KEY]: newPort }, () => {
           if (chrome.runtime.lastError) { console.error("Error saving default server port:", chrome.runtime.lastError); }
           else { console.log("Default server port updated in storage."); }
           sendResponse({success: true});
      });
      return true;
  }
  // --- Handler for Popup Requesting Port (Gets Tab-Specific or Default) ---
  else if (message.action === 'getServerPort') { // This might be redundant now that getPopupData includes it
       const requestingTabId = message.tabId;
       if (!requestingTabId) { console.error("Popup did not provide Tab ID for getServerPort."); sendResponse({ error: "Missing Tab ID from popup." }); return true; }
       console.log(`Popup (Tab ID: ${requestingTabId}) requested server port.`);
       getDefaultSettings().then(defaultSettings => {
            const tabSpecificPort = tabPortMap.get(requestingTabId);
            const portToSend = tabSpecificPort !== undefined ? tabSpecificPort : defaultSettings.port;
            console.log(`Sending port ${portToSend} to popup for tab ${requestingTabId}`);
            sendResponse({ port: portToSend });
       });
       return true;
   }
   // --- NEW: Handler for Test Connection Request ---
   else if (message.action === 'testServerConnection') {
       const portToTest = message.port;
       const sourceTabId = message.tabId; // Tab that initiated the test
       console.log(`Received test connection request for port ${portToTest} from tab ${sourceTabId}`);
       testServerConnection(portToTest, sourceTabId).then(response => {
            sendResponse(response);
       }).catch(error => {
           console.error("Error in testServerConnection promise:", error);
           sendResponse({ success: false, message: "Background script error during test.", action: 'testResult', port_tested: portToTest });
       });
       return true; // Async response
   }
  else {
      console.log("Received unknown message action:", message.action);
  }
});

// --- NEW: Function to test server connection ---
async function testServerConnection(port, sourceTabId) {
    const url = `http://localhost:${port}/test_connection`;
    let testResponseData = { action: 'testResult', success: false, port_tested: port }; // Include action for popup handler
    console.log(`Attempting test connection to ${url} for tab ${sourceTabId}`);
    try {
        const response = await fetch(url, { method: 'GET', cache: 'no-cache' }); // GET request, no cache
        console.log(`Test connection response status: ${response.status}`);
        const responseText = await response.text();

        if (response.ok) {
            try {
                const data = JSON.parse(responseText);
                if (data.status === 'ok') {
                    testResponseData.success = true;
                    testResponseData.working_directory = data.working_directory;
                    testResponseData.message = "Server is reachable.";
                    console.log("Test connection successful:", data);
                } else {
                    testResponseData.message = `Server responded, but status was not 'ok': ${data.status || responseText}`;
                     console.warn("Test connection server status not ok:", data);
                }
            } catch (e) {
                testResponseData.message = `Server responded, but response was not valid JSON (Status: ${response.status}).`;
                console.error("Test connection JSON parse error:", e, "Response Text:", responseText);
            }
        } else {
            testResponseData.message = `Server connection failed with status: ${response.status}.`;
            console.error(`Test connection failed: ${response.status} - ${responseText}`);
        }
    } catch (error) {
        testResponseData.message = `Network Error: ${error.message}. Is server running on port ${port}?`;
        console.error(`Test connection network error to ${url}:`, error);
    }

    // Update global last response (useful for debugging if popup closes)
    updateLastResponse(testResponseData);

    return testResponseData; // Return result for the popup's sendResponse callback
}

// --- Function to send the captured code to the local Flask server ---
async function sendCodeToServer(codeToSend, captureId) {
    const requestInfo = codeRequestMap.get(captureId);
    if (!requestInfo || !requestInfo.tabId) { console.error(`No tab ID for capture ID: ${captureId}`); return; }
    const originatingTabId = requestInfo.tabId;

    const defaultSettings = await getDefaultSettings();
    const portToUse = tabPortMap.get(originatingTabId) || defaultSettings.port;
    const url = `http://localhost:${portToUse}/submit_code`;

    console.log(`Sending code (ID: ${captureId}, Tab: ${originatingTabId}) to server at ${url}`);
    let responseDataForStorage = null;
    let serverResponseOk = false;

    try {
        const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', }, body: JSON.stringify({ code: codeToSend }) });
        console.log(`Fetch response status for ID ${captureId}: ${response.status}`);
        const responseText = await response.text();
        console.log("Raw server response text received:", responseText);

        try {
            responseDataForStorage = JSON.parse(responseText);
            console.log("Server response parsed successfully:", responseDataForStorage);
            if (response.ok && responseDataForStorage.status === 'success') {
                 if (responseDataForStorage.git_updated === false && responseDataForStorage.source_file_marker) {
                     console.warn("Server reported success but Git update failed."); serverResponseOk = false;
                     responseDataForStorage.status = 'error'; responseDataForStorage.message = 'File saved but Git commit failed.';
                 } else { serverResponseOk = true; }
            } else {
                 console.error(`Server responded non-OK: ${response.status} or error status in JSON.`); serverResponseOk = false;
                 if (!responseDataForStorage.status || responseDataForStorage.status !== 'error') {
                     responseDataForStorage.status = 'error'; responseDataForStorage.message = responseDataForStorage.message || `Server returned status ${response.status}.`;
                 }
            }
        } catch (parseError) {
            console.error("Failed to parse server response as JSON:", parseError, "\nRaw text:", responseText);
            responseDataForStorage = { status: "error", message: `Invalid JSON (Status: ${response.status}). ${responseText.substring(0, 100)}...` };
            serverResponseOk = false;
        }
    } catch (error) {
        console.error(`!!! Network error sending code (ID: ${captureId}, Tab: ${originatingTabId}) to ${url}:`, error);
        responseDataForStorage = { status: "error", message: `Network Error: ${error.message}. Is server running on port ${portToUse}?` };
        serverResponseOk = false;
    }

    // --- Store the last response and notify popup/content script ---
    if (responseDataForStorage) {
        updateLastResponse(responseDataForStorage); // Use helper to save and update popup

        // Send detailed response back to specific content script tab
        console.log(`Sending processing result (Success: ${serverResponseOk}) for ID ${captureId} back to tab ${originatingTabId}`);
        chrome.tabs.sendMessage(originatingTabId, {
            action: 'serverProcessingComplete',
            captureId: captureId, success: serverResponseOk, details: responseDataForStorage
        }).catch(err => { console.warn(`Could not send result to tab ${originatingTabId}:`, err.message); });
        codeRequestMap.delete(captureId); // Clean up map entry
    } else {
        console.error("responseDataForStorage was unexpectedly null after fetch attempt.");
        if (codeRequestMap.has(captureId)) { codeRequestMap.delete(captureId); } // Cleanup map even on error
    }
}

console.log("Background script finished loading.");