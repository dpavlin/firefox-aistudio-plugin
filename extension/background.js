// --- START OF FILE background.js ---
console.log("Background script loaded. Waiting for messages.");

// Listen for messages from other parts of the extension (popup or content scripts)
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // Log EVERY message received
  console.log("Background received message:", message, "from sender:", sender);

  // --- Handler for direct sending from content script (automatic capture) ---
  if (message.action === 'sendCodeDirectly' && message.code) {
      console.log("Action 'sendCodeDirectly' received with code. Calling sendCodeToServer."); // <<< CONFIRM THIS LOG APPEARS
      sendCodeToServer(message.code);
      return false; // Indicate that we will not be sending an asynchronous response
  }
  // --- Handler for the original trigger from popup (manual capture) ---
  else if (message.action === 'captureCode') {
    console.log("Manual 'captureCode' action triggered via popup.");
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs.length === 0) {
        console.error("No active tab found for manual capture.");
        return;
      }
      const activeTabId = tabs[0].id;
      console.log(`Sending 'getCodeFromPage' message to content script on tab ${activeTabId}`);
      chrome.tabs.sendMessage(
        activeTabId,
        { action: 'getCodeFromPage' },
        (response) => {
          if (chrome.runtime.lastError) {
            console.error("Error sending/receiving message for manual capture:", chrome.runtime.lastError.message);
            return;
          }
          if (response && response.code) {
            console.log("Received code manually from content script:", response.code.substring(0, 100) + "...");
            sendCodeToServer(response.code);
          } else {
            console.error("No code received from content script for manual capture, or response invalid:", response);
          }
        }
      );
    });
    return true; // Async response expected later
  } else {
      console.log("Received message action is not 'sendCodeDirectly' or 'captureCode'. Action:", message.action);
  }
});

// --- Function to send the captured code to the local Flask server ---
async function sendCodeToServer(code) {
  const url = 'http://localhost:5000/submit_code'; // Or 127.0.0.1:5000
  console.log(`Attempting to send code to server at ${url}`); // <<< CONFIRM THIS LOG APPEARS
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ code: code }),
    });

    console.log(`Fetch response status: ${response.status}`); // <<< LOG STATUS CODE
    const result = await response.json(); // Try to parse JSON regardless of status for more info
    console.log("Server response received:", result); // <<< CONFIRM THIS LOG APPEARS

    if (!response.ok) {
        console.error(`Server responded with non-OK status: ${response.status}`);
        // Handle server-side error reporting if needed
    }

  } catch (error) {
    // <<< CRITICAL: CHECK FOR THIS ERROR LOG >>>
    console.error('!!! Network error or issue sending code to server:', error);
    // Possible reasons: Server not running, connection refused, CORS (unlikely for localhost), network config issue.
  }
}

console.log("Background script finished loading.");
// --- END OF FILE background.js ---