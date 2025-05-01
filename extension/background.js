console.log("Background script (v4 - Test Connection) loaded.");

// Default settings
const DEFAULT_PORT = 5000;
const DEFAULT_ACTIVATION = false;

// Store mapping from capture ID to element details for highlighting
const captureIdToElement = new Map();

// Function to get settings from storage
function getSettings(callback) {
  chrome.storage.local.get(['serverPort', 'isActivated'], (result) => {
    const settings = {
      port: result.serverPort || DEFAULT_PORT,
      isActivated: result.isActivated === undefined ? DEFAULT_ACTIVATION : !!result.isActivated,
    };
    // console.log("Background: Retrieved settings:", settings); // Debug
    callback(settings);
  });
}

// Initialize default settings on install/update
chrome.runtime.onInstalled.addListener(() => {
  getSettings(settings => {
    // No action needed on install unless you want to force defaults
    console.log("Extension installed/updated. Current settings:", settings);
  });
});

// Check initial state when the background script loads
getSettings(settings => {
  console.log("Default activation/port state checked/set. Initial active state:", settings.isActivated);
});


// Helper function to send messages to content scripts
function sendMessageToContentScript(tabId, message) {
    // console.log(`Background: Sending message to Tab ${tabId}:`, message); // Debug
    chrome.tabs.sendMessage(tabId, message, (response) => {
        if (chrome.runtime.lastError) {
            console.warn(`Background: Could not send message to tab ${tabId}: ${chrome.runtime.lastError.message}. Tab might be closed or navigating.`);
            // Clean up mapping if tab is gone
            for (const [captureId, details] of captureIdToElement.entries()) {
                if (details.tabId === tabId) {
                    captureIdToElement.delete(captureId);
                }
            }
        } else {
            // Optional: Handle response from content script if needed
            // console.log("Background: Response from content script:", response);
        }
    });
}

// --- Main Function to Handle Code Submission ---
async function submitCodeToServer(code, port, captureId, tabId) {
    const url = `http://127.0.0.1:${port}/submit_code`;
    console.log(`Sending code (ID: ${captureId}, Tab: ${tabId}) to server at ${url}`);

    let serverResponseData = { success: false, message: 'Unknown error', saved_as: null, log_file: null, syntax_ok: null, run_success: null, git_updated: false, save_location: 'unknown' };

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ code: code }),
            signal: AbortSignal.timeout(25000) // 25 second timeout for server processing + network
        });

        if (!response.ok) {
            // Try to get error message from server response if possible
            let errorBody = 'Server returned error status.';
            try {
                 const errorJson = await response.json();
                 errorBody = errorJson.message || JSON.stringify(errorJson);
            } catch (e) {
                errorBody = await response.text(); // Fallback to text
            }
             throw new Error(`HTTP error! status: ${response.status} - ${errorBody}`);
        }

        const data = await response.json();
        console.log("Background: Server response data:", data);

        // Assume success if response is ok and data has 'status: success'
        if (data && data.status === 'success') {
             serverResponseData = {
                 success: true,
                 message: `Code processed. Saved as: ${data.saved_as || 'N/A'}. Git: ${data.git_updated}. Syntax: ${data.syntax_ok}. Run: ${data.run_success}.`,
                 saved_as: data.saved_as,
                 log_file: data.log_file,
                 syntax_ok: data.syntax_ok,
                 run_success: data.run_success,
                 git_updated: data.git_updated,
                 save_location: data.save_location
             };
        } else {
             serverResponseData.message = data.message || 'Server reported an issue, but no specific message.';
             // serverResponseData.success remains false
        }

    } catch (error) {
        console.error(`Background: Error sending code to server (Port: ${port}):`, error);
        serverResponseData.message = `Failed to send code to server on port ${port}.\nError: ${error.message}`;
        serverResponseData.success = false;
         if (error.name === 'AbortError') {
             serverResponseData.message = `Request to server on port ${port} timed out.`;
         }
    } finally {
        // --- Send result back to content script ---
        const elementDetails = captureIdToElement.get(captureId);
        if (elementDetails) {
            sendMessageToContentScript(tabId, {
                action: 'serverProcessingComplete',
                captureId: captureId,
                success: serverResponseData.success,
                details: serverResponseData // Include full details
            });
            // Clean up the mapping after processing
            console.log(`Cleaned up mapping for capture ID "${captureId}"`); // Debug
            captureIdToElement.delete(captureId);
        } else {
            console.warn(`Background: No element details found for capture ID ${captureId} after server response.`);
        }
    }
}


// --- Listen for Messages from Content Script or Popup ---
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log("Background received message:", message, "From:", sender.tab ? "Tab ID " + sender.tab.id : "Popup/Other"); // Debug message source

    if (message.action === 'submitCode') {
        // Store element details before processing
        captureIdToElement.set(message.captureId, {
            tabId: sender.tab.id,
            /* other details if needed */
        });

        // Retrieve current settings before sending
        getSettings(settings => {
            if (settings.isActivated) {
                submitCodeToServer(message.code, settings.port, message.captureId, sender.tab.id);
            } else {
                console.log("Background: Received code submission, but extension is deactivated. Ignoring.");
                 // Optionally send back a deactivated message?
                 sendMessageToContentScript(sender.tab.id, {
                     action: 'serverProcessingComplete', // Still use this action name
                     captureId: message.captureId,
                     success: false, // Indicate failure
                     details: { message: 'Capture deactivated in extension settings.', success: false }
                 });
                 captureIdToElement.delete(message.captureId); // Clean up if deactivated
            }
        });
        // Indicate that we will respond asynchronously (optional but good practice)
        return true;
    } else if (message.action === 'getSettings') {
        // Handle request from content script for settings
        getSettings(settings => {
            sendResponse(settings);
        });
        return true; // Indicate asynchronous response
    }
    // Add other message handlers if needed

     // Default: If the message isn't handled, return false or undefined implicitly
     // return false; // Explicitly indicate no async response if not handled
});


// --- Listen for changes in storage (e.g., from popup) ---
chrome.storage.onChanged.addListener((changes, namespace) => {
    if (namespace === 'local') {
         let changedKeys = Object.keys(changes);
         console.log(`Background: Storage changed: ${changedKeys.join(', ')}`);
         // Optionally notify content scripts if activation state or port changes?
         if (changedKeys.includes('serverPort') || changedKeys.includes('isActivated')) {
             // Example: Notify all relevant tabs about setting changes
              getSettings(settings => {
                  chrome.tabs.query({url: ["https://aistudio.google.com/*"]}, (tabs) => {
                      tabs.forEach(tab => {
                          sendMessageToContentScript(tab.id, { action: 'settingsUpdated', newSettings: settings });
                      });
                  });
             });
         }
    }
});


console.log("Background script finished loading."); // Debug