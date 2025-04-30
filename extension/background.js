console.log("Background script loaded. Waiting for messages.");

// --- Storage Keys ---
const ACTIVATION_STORAGE_KEY = 'isActivated';
const PORT_STORAGE_KEY = 'serverPort'; // New key for port
const LAST_RESPONSE_STORAGE_KEY = 'lastServerResponse';
const DEFAULT_PORT = 5000;

// --- Global State ---
let currentServerPort = DEFAULT_PORT; // Hold the current port
let isExtensionActivated = true;      // Hold current activation state

// Map Request ID to Tab ID
const requestTabMap = new Map();

// --- Function to load initial state from storage ---
function loadInitialState() {
    chrome.storage.local.get(
        [ACTIVATION_STORAGE_KEY, PORT_STORAGE_KEY, LAST_RESPONSE_STORAGE_KEY],
        (result) => {
            if (chrome.runtime.lastError) {
                console.error("Error loading initial state:", chrome.runtime.lastError.message);
            } else {
                isExtensionActivated = result.isActivated !== undefined ? result.isActivated : true;
                currentServerPort = result.serverPort !== undefined ? result.serverPort : DEFAULT_PORT;
                console.log(`Initial state loaded: Activated=${isExtensionActivated}, Port=${currentServerPort}`);

                // Initialize last response if needed (can remove from onInstalled)
                if (result.lastServerResponse === undefined) {
                    chrome.storage.local.set({ [LAST_RESPONSE_STORAGE_KEY]: "Ready." });
                }
            }
        }
    );
}

// --- Initialize on startup ---
loadInitialState();

// --- Listener for storage changes ---
chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName === 'local') {
        if (changes[ACTIVATION_STORAGE_KEY]) {
            isExtensionActivated = changes[ACTIVATION_STORAGE_KEY].newValue;
            console.log(`Background detected activation state change: ${isExtensionActivated}`);
        }
        if (changes[PORT_STORAGE_KEY]) {
            currentServerPort = changes[PORT_STORAGE_KEY].newValue;
            console.log(`Background detected port change: ${currentServerPort}`);
        }
    }
});


// --- Message Listener ---
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log("Background received message:", message, "from sender tab:", sender?.tab?.id);

  if (message.action === 'sendCodeDirectly' && message.code && message.captureId) {
    if (sender?.tab?.id) {
         requestTabMap.set(message.captureId, sender.tab.id);
         console.log(`Mapping captureId ${message.captureId} to tab ${sender.tab.id}`);
         setTimeout(() => { if (requestTabMap.delete(message.captureId)) console.log(`Cleaned up mapping for captureId ${message.captureId}`); }, 30000);
    } else { console.warn("Sender tab ID not available for 'sendCodeDirectly'."); }

    // Use internal state variable directly
    if (isExtensionActivated) {
      console.log("Extension activated. Calling sendCodeToServer.");
      sendCodeToServer(message.code, message.captureId);
    } else {
      console.log("Extension disabled. Ignoring code sent from content script.");
      requestTabMap.delete(message.captureId);
    }
    return false; // Sync response
  }
  else if (message.action === 'getPopupData') {
      console.log("Popup requested data.");
      // Read directly from storage for the most up-to-date lastResponse
      chrome.storage.local.get([LAST_RESPONSE_STORAGE_KEY], (storageResult) => {
           const responsePayload = {
               activated: isExtensionActivated, // Use current background state
               port: currentServerPort,       // Use current background state
               lastResponse: storageResult.lastServerResponse || "No response yet."
           };
           console.log("Sending data to popup:", responsePayload);
           sendResponse(responsePayload);
      });
      return true; // Async response
  }
  else if (message.action === 'setActivationState') {
      const newState = message.activated;
      console.log(`Setting activation state to: ${newState}`);
      isExtensionActivated = newState; // Update internal state immediately
      chrome.storage.local.set({ [ACTIVATION_STORAGE_KEY]: newState }, () => {
          if (chrome.runtime.lastError) sendResponse({success: false, error: chrome.runtime.lastError.message});
          else sendResponse({success: true});
      });
      return true; // Async response
  }
  // --- Handler for Popup Setting Server Port ---
  else if (message.action === 'setServerPort') {
      const newPort = message.port;
      if (Number.isInteger(newPort) && newPort > 1024 && newPort <= 65535) {
          console.log(`Setting server port to: ${newPort}`);
          currentServerPort = newPort; // Update internal state immediately
          chrome.storage.local.set({ [PORT_STORAGE_KEY]: newPort }, () => {
               if (chrome.runtime.lastError) sendResponse({success: false, error: chrome.runtime.lastError.message});
               else sendResponse({success: true});
          });
      } else {
           console.error(`Invalid port number received: ${newPort}`);
           sendResponse({success: false, error: "Invalid port number"});
      }
      return true; // Async response
  }
  else { console.log("Received unknown message action:", message.action); }
});


// --- Function to send code ---
async function sendCodeToServer(codeToSend, captureId) {
  // --- Use the current port from background state ---
  const url = `http://localhost:${currentServerPort}/submit_code`;
  console.log(`Attempting to send code to server at ${url} for captureId ${captureId}`);
  let responseDataForStorage = null;
  let serverResponseOk = false;

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', },
      body: JSON.stringify({ code: codeToSend }),
    });
    const responseText = await response.text();
    console.log(`[${captureId}] Fetch response status: ${response.status}. Raw text:`, responseText.substring(0, 200) + "...");

    try {
        responseDataForStorage = JSON.parse(responseText);
        console.log(`[${captureId}] Server response parsed:`, responseDataForStorage);
        if (response.ok && responseDataForStorage.status === 'success') {
             if (responseDataForStorage.git_updated === false && responseDataForStorage.source_file_marker) {
                 console.warn(`[${captureId}] Server OK but Git update failed.`);
                 serverResponseOk = false; responseDataForStorage.status = 'error';
                 responseDataForStorage.message = 'File saved but Git commit failed.';
             } else { serverResponseOk = true; }
        } else {
             console.error(`[${captureId}] Server responded non-OK/error status.`);
             serverResponseOk = false;
             if (!responseDataForStorage.status || responseDataForStorage.status !== 'error') {
                 responseDataForStorage.status = 'error';
                 responseDataForStorage.message = responseDataForStorage.message || `Server returned status ${response.status}.`;
             }
        }
    } catch (parseError) {
        console.error(`[${captureId}] Failed to parse server response as JSON:`, parseError);
        responseDataForStorage = { status: "error", message: `Failed to parse server response (Status: ${response.status}). Not valid JSON.` };
        serverResponseOk = false;
    }
  } catch (error) {
    console.error(`[${captureId}] !!! Network error sending code:`, error);
    responseDataForStorage = { status: "error", message: `Network Error: ${error.message}. Is server running on port ${currentServerPort}?` };
    serverResponseOk = false;
  }

  // --- Store response & notify ---
  if (responseDataForStorage) {
      chrome.storage.local.set({ [LAST_RESPONSE_STORAGE_KEY]: responseDataForStorage }, () => {
          if (chrome.runtime.lastError) console.error("Error saving last server response:", chrome.runtime.lastError.message);
          else console.log("Last server response saved to storage.");

          const originatingTabId = requestTabMap.get(captureId);
          if (originatingTabId) {
              console.log(`Sending processing result back to tab ${originatingTabId} for captureId ${captureId}`);
              chrome.tabs.sendMessage(originatingTabId, {
                  action: 'serverProcessingComplete',
                  captureId: captureId,
                  success: serverResponseOk,
                  details: responseDataForStorage
              }).catch(err => console.warn(`Could not send result to tab ${originatingTabId}:`, err.message));
              requestTabMap.delete(captureId);
          } else { console.warn(`Could not find originating tab ID for captureId ${captureId}`); }

          chrome.runtime.sendMessage({action: 'updatePopupResponse', lastResponse: responseDataForStorage})
             .catch(err => { if (err.message !== "Could not establish connection. Receiving end does not exist.") console.warn("Could not send response update to popup:", err.message); });
      });
  }
}

console.log("Background script finished loading.");
// --- END OF FILE background.js ---