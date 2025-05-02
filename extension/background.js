//@@FILENAME@@ extension/background.js
// Default server port
const DEFAULT_PORT = 5000;

// Function to get the port for the current tab (implement if needed, or use global)
// For simplicity now, we'll use a global variable or fetch from storage each time.
async function getPortForTab(tabId) {
  // In a real scenario, you might store port per tabId or windowId
  // For now, just get the globally stored port or default
  let data = await browser.storage.local.get('serverPort');
  return data.serverPort || DEFAULT_PORT;
}


// Listen for messages from content scripts or popup
browser.runtime.onMessage.addListener(async (request, sender, sendResponse) => {
  console.log("Background: Received message:", request);

  if (request.action === "submitCode") {
    if (!request.code) {
      console.error("Background: Received submitCode request with no code.");
      return Promise.resolve({ success: false, details: { status: 'error', message: 'No code provided in message.' } });
    }

    try {
      const port = await getPortForTab(sender.tab?.id); // Get port (adjust storage logic if needed)
      const url = `http://127.0.0.1:${port}/submit_code`;
      console.log(`Background: Sending code to ${url}`);

      const response = await fetch(url, {
        method: 'POST',
        // *** FIX: Add Content-Type header ***
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json' // Good practice to include Accept as well
        },
        // *** FIX: Stringify the data into a JSON body ***
        body: JSON.stringify({ code: request.code })
      });

      // Check if the response itself is okay (e.g., 404, 500 errors)
      if (!response.ok) {
          console.error(`Background: Server responded with status ${response.status} ${response.statusText}`);
          // Try to get text for more details, might not be JSON
          const errorText = await response.text().catch(() => `Server returned status ${response.status}`);
           return Promise.resolve({ success: false, details: { status: 'error', message: `Server error: ${response.status} ${response.statusText}`, server_response: errorText } });
      }

      // Try to parse the response as JSON
      const data = await response.json();
      console.log("Background: Received response from server:", data);
      // Send the server's response back to the content script
      return Promise.resolve({ success: data.status === 'success', details: data });

    } catch (error) {
      console.error("Background: Error fetching /submit_code:", error);
      // Handle network errors or other fetch issues
       let errorMessage = 'Network error or server unavailable.';
       if (error instanceof TypeError && error.message.includes('NetworkError')) {
           errorMessage = 'Network error: Could not connect to the server. Is it running?';
       } else if (error instanceof Error) {
           errorMessage = error.message;
       }
       return Promise.resolve({ success: false, details: { status: 'error', message: errorMessage } });
    }
  }
  // --- Handle other actions (like from popup) ---
  else if (request.action === "testConnection") {
     try {
          const port = request.port || DEFAULT_PORT; // Use port from request if provided
          const url = `http://127.0.0.1:${port}/test_connection`;
          console.log(`Background: Testing connection to ${url}`);
          const response = await fetch(url);
          if (!response.ok) {
               throw new Error(`Server responded with status ${response.status}`);
          }
          const data = await response.json();
          console.log("Background: Test connection successful:", data);
          return Promise.resolve({ success: true, details: data });
      } catch (error) {
           console.error("Background: Test connection failed:", error);
           return Promise.resolve({ success: false, details: { status: 'error', message: error.message || 'Connection failed' } });
      }
  }
   else if (request.action === "updateConfig") {
       try {
            const port = await getPortForTab(null); // Assuming config updates affect the main server instance
            const url = `http://127.0.0.1:${port}/update_config`;
            console.log(`Background: Sending config update to ${url}`, request.settings);
            const response = await fetch(url, {
                 method: 'POST',
                 headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                 body: JSON.stringify(request.settings || {}) // Send settings from request
            });
             if (!response.ok) {
                 const errorText = await response.text().catch(() => `Server returned status ${response.status}`);
                 throw new Error(`Server error: ${response.status} ${response.statusText}. Response: ${errorText}`);
             }
             const data = await response.json();
             console.log("Background: Config update response:", data);
             return Promise.resolve({ success: data.status === 'success', details: data });
         } catch (error) {
             console.error("Background: Update config failed:", error);
             return Promise.resolve({ success: false, details: { status: 'error', message: error.message || 'Update failed' } });
         }
   }
  // --- Add other message handlers if needed ---

  // Indicate that the response will be sent asynchronously.
  // return true; // This is implicitly handled by returning a Promise
});

// Handle storing the port from the popup (Example)
browser.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "storePort") {
    browser.storage.local.set({ serverPort: request.port })
      .then(() => {
        console.log(`Background: Port stored: ${request.port}`);
        sendResponse({ success: true });
      })
      .catch(error => {
        console.error(`Background: Error storing port: ${error}`);
        sendResponse({ success: false, message: error.message });
      });
    return true; // Keep message channel open for async response
  }
   // If action === 'getPort', fetch and return it
   else if (request.action === "getPort") {
     getPortForTab(null).then(port => { // Use null tabId or relevant context
       sendResponse({ port: port });
     });
     return true; // Keep message channel open for async response
   }
});

console.log("AI Code Capture: Background script loaded.");
