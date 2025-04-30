// @@FILENAME@@ popup.js
document.addEventListener('DOMContentLoaded', () => {
    const activationToggle = document.getElementById('activationToggle');
    const serverPortInput = document.getElementById('serverPort');
    const statusDisplay = document.getElementById('last-response');

    // --- Load initial state ---
    function loadState() {
        // Request data from the background script
        chrome.runtime.sendMessage({ action: 'getPopupData' }, (response) => {
            if (chrome.runtime.lastError) {
                console.error("Error getting popup data:", chrome.runtime.lastError.message);
                statusDisplay.textContent = `Error: ${chrome.runtime.lastError.message}`;
                statusDisplay.className = 'error';
                // Set defaults on error?
                activationToggle.checked = true;
                serverPortInput.value = 5000; // DEFAULT_PORT
            } else if (response) {
                console.log("Popup received data:", response);
                activationToggle.checked = response.activated;
                updateStatusDisplay(response.lastResponse);
            } else {
                console.warn("Received empty response from background for getPopupData");
                statusDisplay.textContent = "Could not load status.";
                statusDisplay.className = 'error';
            }
        });

        // Also request the current port setting
        chrome.runtime.sendMessage({ action: 'getServerPort' }, (response) => {
             if (chrome.runtime.lastError) {
                 console.error("Error getting server port:", chrome.runtime.lastError.message);
                 serverPortInput.value = 5000; // DEFAULT_PORT
             } else if (response && response.port !== undefined) {
                  console.log("Popup received port:", response.port);
                  serverPortInput.value = response.port;
             } else {
                 console.warn("Received invalid response from background for getServerPort");
                 serverPortInput.value = 5000; // DEFAULT_PORT
             }
         });
    }

    // --- Update Status Display ---
    function updateStatusDisplay(response) {
        if (!statusDisplay) return;

        if (typeof response === 'string') {
            statusDisplay.textContent = response;
            statusDisplay.className = ''; // Default class
        } else if (typeof response === 'object' && response !== null) {
            // Format the object nicely
            let text = `Status: ${response.status || 'N/A'}\n`;
            if (response.message) text += `Message: ${response.message}\n`;
            if (response.saved_as) text += `Saved As: ${response.saved_as}\n`;
            if (response.log_file) text += `Log File: ${response.log_file}\n`;
            if (response.syntax_ok !== undefined && response.syntax_ok !== null) text += `Syntax OK: ${response.syntax_ok}\n`;
            if (response.run_success !== undefined && response.run_success !== null) text += `Run OK: ${response.run_success}\n`;
            if (response.git_updated !== undefined) text += `Git Updated: ${response.git_updated}\n`;
            if (response.save_location) text += `Saved To: ${response.save_location}\n`;
            if (response.source_file_marker) text += `Marker Found: ${response.source_file_marker}\n`;
            if (response.detected_language) text += `Detected Lang: ${response.detected_language}\n`;

            statusDisplay.textContent = text.trim();

            // Set class based on overall status
            if (response.status === 'success' && (response.git_updated === false && response.source_file_marker)) {
                 // Special case: saved but git failed
                 statusDisplay.className = 'error'; // Treat git failure as error for display
            } else if (response.status === 'success') {
                statusDisplay.className = 'success';
            } else if (response.status === 'error' || response.syntax_ok === false || response.run_success === false) {
                statusDisplay.className = 'error';
            } else {
                statusDisplay.className = '';
            }
        } else {
            statusDisplay.textContent = 'Received unexpected status format.';
            statusDisplay.className = 'error';
        }
    }


    // --- Event Listeners ---
    activationToggle.addEventListener('change', (event) => {
        const isActivated = event.target.checked;
        console.log("Popup sending activation state:", isActivated);
        chrome.runtime.sendMessage({ action: 'setActivationState', activated: isActivated }, (response) => {
            if (chrome.runtime.lastError || !response?.success) {
                console.error("Error setting activation state:", chrome.runtime.lastError?.message || response?.error);
                // Optionally revert UI or show error
            } else {
                 console.log("Activation state update acknowledged by background.");
            }
        });
    });

    let portChangeTimeout;
    serverPortInput.addEventListener('input', () => {
        clearTimeout(portChangeTimeout);
        portChangeTimeout = setTimeout(() => {
            const newPort = parseInt(serverPortInput.value, 10);
             // Basic validation in popup UI
            if (isNaN(newPort) || newPort < 1025 || newPort > 65535) {
                 console.warn("Invalid port entered in popup:", serverPortInput.value);
                 // Optionally add visual feedback (e.g., red border)
                 serverPortInput.style.borderColor = 'red';
                 return; // Don't send invalid port
            }
            serverPortInput.style.borderColor = ''; // Reset border if valid

            console.log("Popup sending new port:", newPort);
            chrome.runtime.sendMessage({ action: 'setServerPort', port: newPort }, (response) => {
                if (chrome.runtime.lastError || !response?.success) {
                    console.error("Error setting server port:", chrome.runtime.lastError?.message || response?.error);
                     statusDisplay.textContent = `Error saving port: ${chrome.runtime.lastError?.message || response?.error}`;
                     statusDisplay.className = 'error';
                } else {
                     console.log("Server port update acknowledged by background.");
                     // Optionally update status display to confirm save?
                     // updateStatusDisplay("Port saved.");
                 }
            });
        }, 750); // Debounce port input
    });

    // --- Listen for updates from the background script ---
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        if (message.action === 'updatePopupResponse') {
            console.log("Popup received response update from background:", message.lastResponse);
            updateStatusDisplay(message.lastResponse);
        }
        // Keep listener alive if needed for other potential messages
        // return true;
    });

    // --- Initial load ---
    loadState();
});