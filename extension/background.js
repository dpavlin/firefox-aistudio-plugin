// background.js
console.log("Background script loaded. Waiting for messages.");

const ACTIVATION_STORAGE_KEY = 'isActivated';
const LAST_RESPONSE_STORAGE_KEY = 'lastServerResponse';

// --- Initialize default state on install/update ---
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get([ACTIVATION_STORAGE_KEY], (result) => {
    if (result.isActivated === undefined) {
      chrome.storage.local.set({ [ACTIVATION_STORAGE_KEY]: true }, () => {
        console.log("Default activation state set to true.");
      });
    }
    // Initialize last response if not set
     chrome.storage.local.get([LAST_RESPONSE_STORAGE_KEY], (res) => {
        if (res.lastServerResponse === undefined) {
             chrome.storage.local.set({ [LAST_RESPONSE_STORAGE_KEY]: "Ready." });
        }
     });
  });
});


// --- Message Listener ---
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log("Background received message:", message, "from sender:", sender?.tab?.id); // Log tab ID if available

  // --- Handler for direct sending from content script ---
  if (message.action === 'sendCodeDirectly' && message.code) {
    chrome.storage.local.get([ACTIVATION_STORAGE_KEY], (result) => {
      const isActivated = result.isActivated !== undefined ? result.isActivated : true; // Default to true if unset
      if (isActivated) {
        console.log("Extension activated. Calling sendCodeToServer.");
        sendCodeToServer(message.code);
      } else {
        console.log("Extension disabled. Ignoring code sent from content script.");
      }
    });
    // Indicate sync response or no response needed back to content script
    return false;
  }
  // --- Handler for Popup Requesting Data ---
  else if (message.action === 'getPopupData') {
      console.log("Popup requested data.");
      chrome.storage.local.get([ACTIVATION_STORAGE_KEY, LAST_RESPONSE_STORAGE_KEY], (result) => {
          const responsePayload = {
              activated: result.isActivated !== undefined ? result.isActivated : true, // Default to true
              lastResponse: result.lastServerResponse || "No response yet."
          };
          console.log("Sending data to popup:", responsePayload);
          sendResponse(responsePayload);
      });
      // Required: Indicate that the response will be sent asynchronously.
      return true;
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
              // Optional: Notify content scripts if state changed (more advanced)
              // notifyContentScriptsOfStateChange(newState);
          }
      });
      // Required: Indicate that the response will be sent asynchronously.
      return true;
  }
  // --- Handle other messages if needed ---
  else {
      console.log("Received unknown message action:", message.action);
  }
  // Default: return false if we don't send an async response for this message type
  // return false; // Implicitly returned if no other return statement is hit
});


// --- Function to send the captured code to the local Flask server ---
async function sendCodeToServer(code) {
  const url = 'http://localhost:5000/submit_code';
  console.log(`Attempting to send code to server at ${url}`);
  let responseDataForStorage = null; // Variable to store what we save

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ code: code }),
    });

    console.log(`Fetch response status: ${response.status}`);
    const responseText = await response.text(); // Get text first
    console.log("Raw server response text received:", responseText);

    try {
        // Try to parse the text as JSON
        responseDataForStorage = JSON.parse(responseText);
        console.log("Server response parsed successfully:", responseDataForStorage);
        if (!response.ok) {
             console.error(`Server responded with non-OK status: ${response.status}`);
             // Keep the parsed error JSON if available
        }
    } catch (parseError) {
        // If parsing fails, store the raw text as an error indicator
        console.error("Failed to parse server response as JSON:", parseError);
        console.error("Raw text was:", responseText); // Log the text that failed
        responseDataForStorage = { status: "error", message: `Failed to parse server response (Status: ${response.status}). Response body was not valid JSON. See background console for details.` };
    }

  } catch (error) {
    console.error('!!! Network error or issue sending code to server:', error);
    responseDataForStorage = { status: "error", message: `Network Error: ${error.message}. Is the server running?` };
  }

  // --- Store the last response and notify popup ---
  if (responseDataForStorage) {
      chrome.storage.local.set({ [LAST_RESPONSE_STORAGE_KEY]: responseDataForStorage }, () => {
          if (chrome.runtime.lastError) {
              console.error("Error saving last server response:", chrome.runtime.lastError.message);
          } else {
              console.log("Last server response saved to storage.");
              // Send message to potentially open popups
              chrome.runtime.sendMessage({action: 'updatePopupResponse', lastResponse: responseDataForStorage}).catch(err => {
                  // Ignore error if no popup is open to receive the message
                  if (err.message !== "Could not establish connection. Receiving end does not exist.") {
                      console.warn("Could not send response update to popup:", err.message);
                  }
              });
          }
      });
  }
}

console.log("Background script finished loading.");