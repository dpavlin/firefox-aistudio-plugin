// --- START OF FILE background.js ---
console.log("Background script loaded.");

// Listen for messages from the popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log("Background received message:", message);

  if (message.action === 'captureCode') {
    console.log("Capture code action triggered.");
    // Get the currently active tab
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs.length === 0) {
        console.error("No active tab found.");
        return;
      }
      const activeTabId = tabs[0].id;
      console.log(`Sending message to content script on tab ${activeTabId}`);

      // Send a message to the content script in the active tab
      chrome.tabs.sendMessage(
        activeTabId,
        { action: 'getCodeFromPage' },
        (response) => {
          // This callback handles the response from the content script
          if (chrome.runtime.lastError) {
            // Handle errors, e.g., content script not injected or couldn't connect
            console.error("Error sending message to content script:", chrome.runtime.lastError.message);
            // Optionally notify the user
            // chrome.notifications.create({ type: 'basic', iconUrl: 'icon.png', title: 'Error', message: 'Could not connect to page content.' });
            return;
          }

          if (response && response.code) {
            console.log("Received code from content script:", response.code.substring(0, 100) + "..."); // Log first 100 chars
            sendCodeToServer(response.code);
          } else {
            console.error("No code received from content script or response was invalid:", response);
             // Optionally notify the user
            // chrome.notifications.create({ type: 'basic', iconUrl: 'icon.png', title: 'Error', message: 'Could not find code on the page.' });
          }
        }
      );
    });
    // Return true to indicate you wish to send a response asynchronously
    // (although we handle the response in the chrome.tabs.sendMessage callback here)
    return true;
  }
});

async function sendCodeToServer(code) {
  const url = 'http://localhost:5000/submit_code';
  console.log(`Sending code to server at ${url}`);
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ code: code }),
    });

    const result = await response.json();
    console.log("Server response:", result);

    // Optional: Notify user of success/failure
    // const message = result.status === 'success'
    //   ? `Code saved as ${result.saved_as}. Syntax OK: ${result.syntax_ok}. Log: ${result.log_file || 'N/A'}`
    //   : `Server Error: ${result.message || 'Unknown error'}`;
    // chrome.notifications.create({ type: 'basic', iconUrl: 'icon.png', title: 'AI Code Capture', message: message });

  } catch (error) {
    console.error('Error sending code to server:', error);
     // Optional: Notify user of network error
    // chrome.notifications.create({ type: 'basic', iconUrl: 'icon.png', title: 'Network Error', message: `Failed to connect to server: ${error.message}` });
  }
}
// --- END OF FILE background.js ---