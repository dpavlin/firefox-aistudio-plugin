// @@FILENAME@@ popup.js
document.addEventListener('DOMContentLoaded', () => {
    const activationToggle = document.getElementById('activationToggle');
    const serverPortInput = document.getElementById('serverPort');
    const statusDisplay = document.getElementById('last-response');
    let currentTabId = null;

    // --- Get current tab ID ---
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (tabs && tabs.length > 0) {
            currentTabId = tabs[0].id;
            console.log("Popup opened for Tab ID:", currentTabId);
            loadState(); // Load state only after getting tab ID
        } else {
            console.error("Could not get active tab ID for popup.");
            statusDisplay.textContent = "Error: Could not identify active tab.";
            statusDisplay.className = 'error';
        }
    });

    // --- Load initial state (called after getting tab ID) ---
    function loadState() {
        if (!currentTabId) return; // Should not happen if called correctly

        // Request data associated with *this* tab from the background script
        chrome.runtime.sendMessage({ action: 'getPopupData', tabId: currentTabId }, (response) => {
            if (chrome.runtime.lastError) {
                console.error("Error getting popup data:", chrome.runtime.lastError.message);
                statusDisplay.textContent = `Error loading: ${chrome.runtime.lastError.message}`;
                statusDisplay.className = 'error';
                activationToggle.checked = true; // Default UI state on error
                serverPortInput.value = 5000;
            } else if (response && response.error) {
                console.error("Error received from background:", response.error);
                statusDisplay.textContent = `Error: ${response.error}`;
                statusDisplay.className = 'error';
            } else if (response) {
                console.log("Popup received data:", response);
                // Activation is global, port is potentially tab-specific (or default)
                activationToggle.checked = response.activated;
                serverPortInput.value = response.port; // Display the port relevant to this tab
                updateStatusDisplay(response.lastResponse); // Last response is still global
            } else {
                console.warn("Received empty/invalid response from background for getPopupData");
                statusDisplay.textContent = "Could not load status.";
                statusDisplay.className = 'error';
            }
        });
    }

    // --- Update Status Display --- (Unchanged from previous)
    function updateStatusDisplay(response) {
        if (!statusDisplay) return;
        if (typeof response === 'string') { statusDisplay.textContent = response; statusDisplay.className = ''; }
        else if (typeof response === 'object' && response !== null) {
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
            if (response.status === 'success' && (response.git_updated === false && response.source_file_marker)) { statusDisplay.className = 'error'; }
            else if (response.status === 'success') { statusDisplay.className = 'success'; }
            else if (response.status === 'error' || response.syntax_ok === false || response.run_success === false) { statusDisplay.className = 'error'; }
            else { statusDisplay.className = ''; }
        } else { statusDisplay.textContent = 'Received unexpected status format.'; statusDisplay.className = 'error'; }
    }


    // --- Event Listeners ---
    activationToggle.addEventListener('change', (event) => {
        const isActivated = event.target.checked;
        console.log("Popup sending global activation state:", isActivated);
        // Activation state remains global
        chrome.runtime.sendMessage({ action: 'setActivationState', activated: isActivated }, (response) => {
            if (chrome.runtime.lastError || !response?.success) { console.error("Error setting activation state:", chrome.runtime.lastError?.message || response?.error); }
            else { console.log("Global activation state update acknowledged."); }
        });
    });

    let portChangeTimeout;
    serverPortInput.addEventListener('input', () => {
        if (!currentTabId) return; // Don't do anything if tab ID wasn't found

        clearTimeout(portChangeTimeout);
        portChangeTimeout = setTimeout(() => {
            const newPort = parseInt(serverPortInput.value, 10);
            if (isNaN(newPort) || newPort < 1025 || newPort > 65535) {
                 console.warn("Invalid port entered in popup:", serverPortInput.value);
                 serverPortInput.style.borderColor = 'red'; return;
            }
            serverPortInput.style.borderColor = '';

            console.log(`Popup sending new port ${newPort} for Tab ID ${currentTabId}`);
            // Send message to set port for *this specific tab*
            chrome.runtime.sendMessage({ action: 'setServerPort', port: newPort, tabId: currentTabId }, (response) => {
                if (chrome.runtime.lastError || !response?.success) {
                    console.error("Error setting server port:", chrome.runtime.lastError?.message || response?.error);
                     statusDisplay.textContent = `Error saving port: ${chrome.runtime.lastError?.message || response?.error}`;
                     statusDisplay.className = 'error';
                } else {
                     console.log("Server port update acknowledged by background for tab", currentTabId);
                 }
            });
        }, 750); // Debounce port input
    });

    // --- Listen for global status updates from the background script ---
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        if (message.action === 'updatePopupResponse') {
            console.log("Popup received global response update from background:", message.lastResponse);
            updateStatusDisplay(message.lastResponse); // Update with the latest global response
        }
        // return true; // Keep alive only if expecting async responses from other message types
    });

    // Initial load is called after getting tab ID
});