console.log("Background script loaded. Waiting for messages.");

const ACTIVATION_STORAGE_KEY = 'isActivated';
const LAST_RESPONSE_STORAGE_KEY = 'lastServerResponse';

// --- Map Request ID to Tab ID ---
// Store mapping of capture ID to originating tab ID
const requestTabMap = new Map();

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get([ACTIVATION_STORAGE_KEY], (result) => {
    if (result.isActivated === undefined) {
      chrome.storage.local.set({ [ACTIVATION_STORAGE_KEY]: true }, () => console.log("Default activation state set to true."));
    }
    chrome.storage.local.get([LAST_RESPONSE_STORAGE_KEY], (res) => {
        if (res.lastServerResponse === undefined) chrome.storage.local.set({ [LAST_RESPONSE_STORAGE_KEY]: "Ready." });
     });
  });
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log("Background received message:", message, "from sender tab:", sender?.tab?.id);

  if (message.action === 'sendCodeDirectly' && message.code && message.captureId) {
    // Store the capture ID and sender tab ID
    if (sender?.tab?.id) {
         requestTabMap.set(message.captureId, sender.tab.id);
         console.log(`Mapping captureId ${message.captureId} to tab ${sender.tab.id}`);
         setTimeout(() => {
            if (requestTabMap.delete(message.captureId)) console.log(`Cleaned up mapping for captureId ${message.captureId}`);
         }, 30000);
    } else { console.warn("Sender tab ID not available for 'sendCodeDirectly' message."); }

    chrome.storage.local.get([ACTIVATION_STORAGE_KEY], (result) => {
      const isActivated = result.isActivated !== undefined ? result.isActivated : true;
      if (isActivated) {
        console.log("Extension activated. Calling sendCodeToServer.");
        sendCodeToServer(message.code, message.captureId); // Pass captureId
      } else {
        console.log("Extension disabled. Ignoring code sent from content script.");
        requestTabMap.delete(message.captureId); // Remove mapping if not activated
      }
    });
    return false;
  }
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
      return true;
  }
  else if (message.action === 'setActivationState') {
      const newState = message.activated;
      console.log(`Setting activation state to: ${newState}`);
      chrome.storage.local.set({ [ACTIVATION_STORAGE_KEY]: newState }, () => {
          if (chrome.runtime.lastError) sendResponse({success: false, error: chrome.runtime.lastError.message});
          else sendResponse({success: true});
      });
      return true;
  }
  else { console.log("Received unknown message action:", message.action); }
});

// --- Function to send code, now takes captureId ---
async function sendCodeToServer(codeToSend, captureId) { // Added captureId parameter
  const url = 'http://localhost:5000/submit_code';
  console.log(`Attempting to send code to server at ${url} for captureId ${captureId}`);
  let responseDataForStorage = null;
  let serverResponseOk = false;

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', },
      body: JSON.stringify({ code: codeToSend }), // Send the code content
    });
    const responseText = await response.text();
    console.log(`[${captureId}] Fetch response status: ${response.status}. Raw text:`, responseText.substring(0, 200) + "...");

    try {
        responseDataForStorage = JSON.parse(responseText);
        console.log(`[${captureId}] Server response parsed successfully:`, responseDataForStorage);
        if (response.ok && responseDataForStorage.status === 'success') {
             if (responseDataForStorage.git_updated === false && responseDataForStorage.source_file_marker) {
                 console.warn(`[${captureId}] Server OK but Git update failed.`);
                 serverResponseOk = false;
                 responseDataForStorage.status = 'error';
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
    responseDataForStorage = { status: "error", message: `Network Error: ${error.message}. Is server running?` };
    serverResponseOk = false;
  }

  // --- Store response & notify ---
  if (responseDataForStorage) {
      chrome.storage.local.set({ [LAST_RESPONSE_STORAGE_KEY]: responseDataForStorage }, () => {
          if (chrome.runtime.lastError) console.error("Error saving last server response:", chrome.runtime.lastError.message);
          else console.log("Last server response saved to storage.");

          const originatingTabId = requestTabMap.get(captureId); // Use captureId to get tabId
          if (originatingTabId) {
              console.log(`Sending processing result back to tab ${originatingTabId} for captureId ${captureId}`);
              chrome.tabs.sendMessage(originatingTabId, {
                  action: 'serverProcessingComplete',
                  captureId: captureId, // Send the ID back
                  success: serverResponseOk,
                  details: responseDataForStorage
              }).catch(err => console.warn(`Could not send result to