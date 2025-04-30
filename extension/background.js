// @@FILENAME@@ background.js
console.log("Background script loaded. Waiting for messages.");

const ACTIVATION_STORAGE_KEY = 'isActivated';
const LAST_RESPONSE_STORAGE_KEY = 'lastServerResponse';

// Store mapping of code content hash (simple way to identify) to originating tab ID
// NOTE: This is basic. Collisions are possible but unlikely for short-lived requests.
// A more robust solution might use unique request IDs.
const codeRequestMap = new Map();

// --- Initialize default state on install/update ---
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get([ACTIVATION_STORAGE_KEY], (result) => {
    if (result.isActivated === undefined) {
      chrome.storage.local.set({ [ACTIVATION_STORAGE_KEY]: true }, () => {
        console.log("Default activation state set to true.");
      });
    }
    chrome.storage.local.get([LAST_RESPONSE_STORAGE_KEY], (res) => {
        if (res.lastServerResponse === undefined) {
             chrome.storage.local.set({ [LAST_RESPONSE_STORAGE_KEY]: "Ready." });
        }
     });
  });
});


// --- Message Listener ---
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log("Background received message:", message, "from sender tab:", sender?.tab?.id);

  // --- Handler for direct sending from content script ---
  if (message.action === 'sendCodeDirectly' && message.code) {
    // Store the code and sender tab ID before checking activation
    if (sender?.tab?.id) {
         // Using the code itself as a temporary key - simplistic approach
         codeRequestMap.set(message.code, sender.tab.id);
         console.log(`Mapping code starting with "${message.code.substring(0,20)}..." to tab ${sender.tab.id}`);
         // Clean up map entry after a delay in case response never comes
         setTimeout(() => {
            if (codeRequestMap.delete(message.code)) {
                 console.log(`Cleaned up mapping for code starting with "${message.code.substring(0,20)}..."`);
            }
         }, 30000); // Cleanup after 30 seconds
    } else {
         console.warn("Sender tab ID not available for 'sendCodeDirectly' message.");
    }

    chrome.storage.local.get([ACTIVATION_STORAGE_KEY], (result) => {
      const isActivated = result.isActivated !== undefined ? result.isActivated : true;
      if (isActivated) {
        console.log("Extension activated. Calling sendCodeToServer.");
        // Pass the original code along to map the response back
        sendCodeToServer(message.code);
      } else {
        console.log("Extension disabled. Ignoring code sent from content script.");
        codeRequestMap.delete(message.code); // Remove mapping if not activated
      }
    });
    return false; // Sync response (no response needed back to content script immediately)
  }
  // --- Handler for Popup Requesting Data ---
  else if (message.action === 'getPopupData') {
      console.log("Popup requested data.");
      chrome.storage.local.get([ACTIVATION_STORAGE_KEY, LAST_RESPONSE_STORAGE_KEY], (result) => {
          const responsePayload = {
              activated: result.isActivated !== undefined ? result.isActivated : true,
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
      console.log(`Setting activation state to: ${newState}`);
      chrome.storage.local.set({ [ACTIVATION_STORAGE_KEY]: newState }, () => {
          if (chrome.runtime.lastError) {
              console.error("Error saving activation state:", chrome.runtime.lastError);
              sendResponse({success: false, error: chrome.runtime.lastError.message});
          } else {
              console.log("Activation state saved.");
              sendResponse({success: true});
          }
      });
      return true; // Async response
  }
  else {
      console.log("Received unknown message action:", message.action);
  }
});


// --- Function to send the captured code to the local Flask server ---
// Now takes originalCode to map response back to the correct tab
async function sendCodeToServer(originalCode) {
  const url = 'http://localhost:5000/submit_code';
  console.log(`Attempting to send code to server at ${url}`);
  let responseDataForStorage = null;
  let serverResponseOk = false; // Track overall success for highlighting

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', },
      body: JSON.stringify({ code: originalCode }), // Send original code
    });

    console.log(`Fetch response status: ${response.status}`);
    const responseText = await response.text();
    console.log("Raw server response text received:", responseText);

    try {
        responseDataForStorage = JSON.parse(responseText);
        console.log("Server response parsed successfully:", responseDataForStorage);
        // Determine success based on server status AND git status if relevant
        if (response.ok && responseDataForStorage.status === 'success') {
             // Check git status if it was supposed to update
             if (responseDataForStorage.git_updated === false && responseDataForStorage.source_file_marker) {
                 // Explicitly marked file failed to commit (treat as error for highlight)
                 console.warn("Server reported success but Git update failed for marker file.");
                 serverResponseOk = false;
                 // Optionally modify the stored status to reflect the git issue
                 responseDataForStorage.status = 'error';
                 responseDataForStorage.message = 'File saved but Git commit failed.';
             } else {
                 // Server success, and either Git updated ok OR Git wasn't applicable
                 serverResponseOk = true;
             }
        } else {
             console.error(`Server responded with non-OK status: ${response.status} or error status in JSON.`);
             serverResponseOk = false;
             // Ensure status is 'error' if not already set by server
             if (!responseDataForStorage.status || responseDataForStorage.status !== 'error') {
                 responseDataForStorage.status = 'error';
                 responseDataForStorage.message = responseDataForStorage.message || `Server returned status ${response.status}.`;
             }
        }
    } catch (parseError) {
        console.error("Failed to parse server response as JSON:", parseError);
        console.error("Raw text was:", responseText);
        responseDataForStorage = { status: "error", message: `Failed to parse server response (Status: ${response.status}). Not valid JSON.` };
        serverResponseOk = false;
    }
  } catch (error) {
    console.error('!!! Network error or issue sending code to server:', error);
    responseDataForStorage = { status: "error", message: `Network Error: ${error.message}. Is server running?` };
    serverResponseOk = false;
  }

  // --- Store the last response and notify popup/content script ---
  if (responseDataForStorage) {
      chrome.storage.local.set({ [LAST_RESPONSE_STORAGE_KEY]: responseDataForStorage }, () => {
          if (chrome.runtime.lastError) {
              console.error("Error saving last server response:", chrome.runtime.lastError.message);
          } else {
              console.log("Last server response saved to storage.");
              // Send detailed response back to specific content script tab for highlighting
              const originatingTabId = codeRequestMap.get(originalCode);
              if (originatingTabId) {
                  console.log(`Sending processing result back to tab ${originatingTabId}`);
                  chrome.tabs.sendMessage(originatingTabId, {
                      action: 'serverProcessingComplete',
                      originalCode: originalCode, // Send back original code to identify block
                      success: serverResponseOk, // Simple boolean for success/error highlight
                      details: responseDataForStorage // Full details for popup/logging
                  }).catch(err => {
                      console.warn(`Could not send processing result to content script tab ${originatingTabId}:`, err.message);
                  });
                  codeRequestMap.delete(originalCode); // Clean up map entry after sending response
              } else {
                   console.warn("Could not find originating tab ID for code:", originalCode.substring(0, 50) + "...");
              }

              // Also update any open popup
              chrome.runtime.sendMessage({action: 'updatePopupResponse', lastResponse: responseDataForStorage}).catch(err => {
                  if (err.message !== "Could not establish connection. Receiving end does not exist.") {
                      console.warn("Could not send response update to popup:", err.message);
                  }
              });
          }
      });
  }
}

console.log("Background script finished loading.");
// --- END OF FILE background.js ---