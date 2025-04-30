// @@FILENAME@@ background.js
console.log("Background script loaded. Waiting for messages.");

// --- Storage Keys & Default Port ---
const ACTIVATION_STORAGE_KEY = 'isActivated';
const PORT_STORAGE_KEY = 'serverPort';
const LAST_RESPONSE_STORAGE_KEY = 'lastServerResponse';
const DEFAULT_PORT = 5000;

// --- State & Request Mapping ---
let isExtensionActivated = true; // Default assumption, will be updated from storage
const codeRequestMap = new Map(); // Map: originalCode -> { tabId: number, captureId: string }

// --- Function to get current settings ---
async function getCurrentSettings() {
  return new Promise((resolve) => {
    chrome.storage.local.get([ACTIVATION_STORAGE_KEY, PORT_STORAGE_KEY], (result) => {
      if (chrome.runtime.lastError) {
        console.error("Error reading settings from storage:", chrome.runtime.lastError.message);
        // Resolve with defaults on error
        resolve({
          activated: true,
          port: DEFAULT_PORT
        });
      } else {
        resolve({
          activated: result.isActivated !== undefined ? result.isActivated : true,
          port: result.serverPort !== undefined ? parseInt(result.serverPort, 10) || DEFAULT_PORT : DEFAULT_PORT
        });
      }
    });
  });
}

// --- Initialize default state & load current state ---
chrome.runtime.onInstalled.addListener(async () => {
  const settings = await getCurrentSettings(); // Use await here
  isExtensionActivated = settings.activated; // Update global state variable

  chrome.storage.local.get([LAST_RESPONSE_STORAGE_KEY], (res) => {
      if (res.lastServerResponse === undefined) {
           chrome.storage.local.set({ [LAST_RESPONSE_STORAGE_KEY]: "Ready." });
      }
   });
  console.log("Default activation state checked/set. Initial active state:", isExtensionActivated);
});

// Load initial state when the script starts
getCurrentSettings().then(settings => {
  isExtensionActivated = settings.activated;
  console.log("Background script loaded initial state: Activated =", isExtensionActivated);
});


// --- Listen for storage changes to update internal activation state ---
chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName === 'local' && changes[ACTIVATION_STORAGE_KEY]) {
        isExtensionActivated = changes[ACTIVATION_STORAGE_KEY].newValue;
        console.log(`Background script updated activation state: ${isExtensionActivated}`);
    }
    // Port change doesn't need immediate update here, sendCodeToServer will read it.
});

// --- Message Listener ---
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log("Background received message:", message, "from sender tab:", sender?.tab?.id);

  // --- Handler for direct sending from content script ---
  if (message.action === 'sendCodeDirectly' && message.code && message.captureId) {
    // Store the code and sender tab ID before checking activation
    const requestKey = message.captureId; // Use unique capture ID as the key
    if (sender?.tab?.id) {
         codeRequestMap.set(requestKey, { tabId: sender.tab.id, originalCode: message.code });
         console.log(`Mapping capture ID "${requestKey}" to tab ${sender.tab.id}`);
         // Clean up map entry after a delay
         setTimeout(() => {
            if (codeRequestMap.delete(requestKey)) {
                 console.log(`Cleaned up mapping for capture ID "${requestKey}"`);
            }
         }, 30000); // Cleanup after 30 seconds
    } else {
         console.warn("Sender tab ID not available for 'sendCodeDirectly' message.");
    }

    // Use the globally tracked activation state
    if (isExtensionActivated) {
      console.log("Extension activated. Calling sendCodeToServer.");
      sendCodeToServer(message.code, requestKey); // Pass code AND captureId
    } else {
      console.log("Extension disabled. Ignoring code sent from content script.");
      codeRequestMap.delete(requestKey); // Remove mapping if not activated
    }
    return false; // Sync response
  }
  // --- Handler for Popup Requesting Data ---
  else if (message.action === 'getPopupData') {
      console.log("Popup requested data.");
      // Combine current activation state with stored last response
      chrome.storage.local.get([LAST_RESPONSE_STORAGE_KEY], (result) => {
          const responsePayload = {
              activated: isExtensionActivated, // Use current state
              lastResponse: result.lastServerResponse || "No response yet."
          };
          console.log("Sending data to popup:", responsePayload);
          sendResponse(responsePayload);
      });
      return true; // Async response
  }
  // --- Handler for Popup Setting Activation State ---
  else if (message.action === 'setActivationState') {
      const newState = message.activated;
      console.log(`Saving activation state from popup: ${newState}`);
      chrome.storage.local.set({ [ACTIVATION_STORAGE_KEY]: newState }, () => {
          if (chrome.runtime.lastError) {
              console.error("Error saving activation state:", chrome.runtime.lastError);
              sendResponse({success: false, error: chrome.runtime.lastError.message});
          } else {
              console.log("Activation state saved.");
              isExtensionActivated = newState; // Update background's immediate state
              sendResponse({success: true});
              // Optionally: Notify content scripts about the change if needed immediately
              // chrome.tabs.query({url: "https://aistudio.google.com/*"}, (tabs) => { ... });
          }
      });
      return true; // Async response
  }
   // --- Handler for Popup Setting Port ---
  else if (message.action === 'setServerPort') {
      const newPort = parseInt(message.port, 10);
      if (isNaN(newPort) || newPort < 1025 || newPort > 65535) {
          console.error(`Invalid port number received from popup: ${message.port}`);
          sendResponse({ success: false, error: 'Invalid port number.' });
          return true;
      }
      console.log(`Saving server port from popup: ${newPort}`);
      chrome.storage.local.set({ [PORT_STORAGE_KEY]: newPort }, () => {
          if (chrome.runtime.lastError) {
              console.error("Error saving server port:", chrome.runtime.lastError);
              sendResponse({success: false, error: chrome.runtime.lastError.message});
          } else {
              console.log("Server port saved.");
              sendResponse({success: true});
              // Content scripts will pick this up via storage.onChanged
          }
      });
      return true; // Indicate async response
  }
  // --- Handler for Popup Requesting Port ---
  else if (message.action === 'getServerPort') {
        console.log("Popup requested server port.");
        chrome.storage.local.get([PORT_STORAGE_KEY], (result) => {
            const port = result.serverPort !== undefined ? parseInt(result.serverPort, 10) || DEFAULT_PORT : DEFAULT_PORT;
            console.log("Sending port to popup:", port);
            sendResponse({ port: port });
        });
        return true; // Indicate async response
   }
  else {
      console.log("Received unknown message action:", message.action);
  }
});


// --- Function to send the captured code to the local Flask server ---
async function sendCodeToServer(codeToSend, captureId) {
    // *** FIX: Read port from storage ***
    const settings = await getCurrentSettings();
    const portToUse = settings.port;
    const url = `http://localhost:${portToUse}/submit_code`; // Dynamic URL
    // ***********************************

    console.log(`Attempting to send code (ID: ${captureId}) to server at ${url}`);
    let responseDataForStorage = null;
    let serverResponseOk = false;

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', },
            body: JSON.stringify({ code: codeToSend }),
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
                     responseDataForStorage.status = 'error'; // Override status
                     responseDataForStorage.message = 'File saved but Git commit failed.';
                 } else {
                     serverResponseOk = true; // All good
                 }
            } else {
                 console.error(`Server responded with non-OK status: ${response.status} or error status in JSON.`);
                 serverResponseOk = false;
                 if (!responseDataForStorage.status || responseDataForStorage.status !== 'error') {
                     responseDataForStorage.status = 'error';
                     responseDataForStorage.message = responseDataForStorage.message || `Server returned status ${response.status}.`;
                 }
            }
        } catch (parseError) {
            console.error("Failed to parse server response as JSON:", parseError);
            console.error("Raw text was:", responseText);
            responseDataForStorage = { status: "error", message: `Invalid JSON (Status: ${response.status}). ${responseText.substring(0, 100)}...` };
            serverResponseOk = false;
        }
    } catch (error) {
        console.error(`!!! Network error sending code (ID: ${captureId}) to ${url}:`, error);
        responseDataForStorage = { status: "error", message: `Network Error: ${error.message}. Is server running on port ${portToUse}?` };
        serverResponseOk = false;
    }

    // --- Store the last response and notify popup/content script ---
    if (responseDataForStorage) {
        chrome.storage.local.set({ [LAST_RESPONSE_STORAGE_KEY]: responseDataForStorage }, () => {
            if (chrome.runtime.lastError) { console.error("Error saving last response:", chrome.runtime.lastError.message); }
            else { console.log("Last server response saved."); }

            // Send detailed response back to specific content script tab for highlighting
            const requestInfo = codeRequestMap.get(captureId);
            if (requestInfo?.tabId) {
                console.log(`Sending processing result (Success: ${serverResponseOk}) for ID ${captureId} back to tab ${requestInfo.tabId}`);
                chrome.tabs.sendMessage(requestInfo.tabId, {
                    action: 'serverProcessingComplete',
                    captureId: captureId, // Use the ID to find the element
                    success: serverResponseOk,
                    details: responseDataForStorage
                }).catch(err => {
                    console.warn(`Could not send processing result to content script tab ${requestInfo.tabId}:`, err.message);
                });
                codeRequestMap.delete(captureId); // Clean up map entry
            } else {
                 console.warn(`Could not find originating tab ID for capture ID: ${captureId}`);
            }

            // Also update any open popup
            chrome.runtime.sendMessage({action: 'updatePopupResponse', lastResponse: responseDataForStorage}).catch(err => {
                if (err.message.includes("Receiving end does not exist")) {
                   // Expected if popup is not open, do nothing.
                } else {
                   console.warn("Could not send response update to popup:", err.message);
                }
            });
        });
    } else {
        console.error("responseDataForStorage was unexpectedly null after fetch attempt.");
    }
}

console.log("Background script finished loading.");