document.addEventListener('DOMContentLoaded', () => {
    const activationToggle = document.getElementById('activationToggle');
    const serverPortInput = document.getElementById('serverPort');
    const statusDisplay = document.getElementById('last-response');
    const testConnectionBtn = document.getElementById('testConnectionBtn');
    let currentTabId = null;
    const DEFAULT_PORT = 5000; // Keep default consistent

    function validatePort(port) {
        const num = parseInt(port, 10);
        return !isNaN(num) && num >= 1025 && num <= 65535;
    }

    // --- Get current tab ID ---
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (tabs && tabs.length > 0) {
            currentTabId = tabs[0].id;
            console.log("Popup opened for Tab ID:", currentTabId);
            loadState(); // Load state only after getting tab ID
            testConnectionBtn.disabled = false; // Enable button once tab ID is known
        } else {
            console.error("Could not get active tab ID for popup.");
            statusDisplay.textContent = "Error: Could not identify active tab.";
            statusDisplay.className = 'error';
            testConnectionBtn.disabled = true;
        }
    });

    // --- Load initial state (called after getting tab ID) ---
    function loadState() {
        if (!currentTabId) return;

        // Request data associated with *this* tab from the background script
        chrome.runtime.sendMessage({ action: 'getPopupData', tabId: currentTabId }, (response) => {
            if (chrome.runtime.lastError) {
                console.error("Error getting popup data:", chrome.runtime.lastError.message);
                statusDisplay.textContent = `Error loading: ${chrome.runtime.lastError.message}`;
                statusDisplay.className = 'error';
                activationToggle.checked = true; // Default UI state on error
                serverPortInput.value = DEFAULT_PORT;
                serverPortInput.classList.remove('invalid');
            } else if (response && response.error) {
                console.error("Error received from background:", response.error);
                statusDisplay.textContent = `Error: ${response.error}`;
                statusDisplay.className = 'error';
            } else if (response) {
                console.log("Popup received data:", response);
                activationToggle.checked = response.activated;
                serverPortInput.value = response.port;
                serverPortInput.classList.remove('invalid');
                updateStatusDisplay(response.lastResponse);
            } else {
                console.warn("Received empty/invalid response from background for getPopupData");
                statusDisplay.textContent = "Could not load status.";
                statusDisplay.className = 'error';
                serverPortInput.value = DEFAULT_PORT; // Default UI state on error
            }
        });
        // Note: Port request is now part of getPopupData to ensure atomicity
    }

    // --- Update Status Display ---
    function updateStatusDisplay(response) {
        if (!statusDisplay) return;
        statusDisplay.className = ''; // Reset class

        if (typeof response === 'string') {
            statusDisplay.textContent = response;
        } else if (typeof response === 'object' && response !== null) {
            let text = `Status: ${response.status || 'N/A'}\n`;
             // Add specific messages for connection tests
            if (response.action === 'testResult') {
                text = response.success ? `Connection OK ✅\n` : `Connection Failed ❌\n`;
                text += `Port: ${response.port_tested}\n`;
                if(response.working_directory) text += `Server CWD: ${response.working_directory}\n`;
                 if (response.message) text += `Message: ${response.message}\n`;
                 statusDisplay.className = response.success ? 'success info' : 'error'; // Use 'info' too
            } else {
                // Format regular submit response
                if (response.message) text += `Message: ${response.message}\n`;
                if (response.saved_as) text += `Saved As: ${response.saved_as}\n`;
                if (response.log_file) text += `Log File: ${response.log_file}\n`;
                if (response.syntax_ok !== undefined && response.syntax_ok !== null) text += `Syntax OK: ${response.syntax_ok}\n`;
                if (response.run_success !== undefined && response.run_success !== null) text += `Run OK: ${response.run_success}\n`;
                if (response.git_updated !== undefined) text += `Git Updated: ${response.git_updated}\n`;
                if (response.save_location) text += `Saved To: ${response.save_location}\n`;
                if (response.source_file_marker) text += `Marker Found: ${response.source_file_marker}\n`;
                if (response.detected_language) text += `Detected Lang: ${response.detected_language}\n`;

                // Set class based on overall status
                if (response.status === 'success' && (response.git_updated === false && response.source_file_marker)) { statusDisplay.className = 'error'; }
                else if (response.status === 'success') { statusDisplay.className = 'success'; }
                else if (response.status === 'error' || response.syntax_ok === false || response.run_success === false) { statusDisplay.className = 'error'; }
            }
            statusDisplay.textContent = text.trim();
        } else {
            statusDisplay.textContent = 'Received unexpected status format.';
            statusDisplay.className = 'error';
        }
    }


    // --- Event Listeners ---
    activationToggle.addEventListener('change', (event) => {
        const isActivated = event.target.checked;
        chrome.runtime.sendMessage({ action: 'setActivationState', activated: isActivated }, (response) => {
            if (chrome.runtime.lastError || !response?.success) { console.error("Error setting activation state:", chrome.runtime.lastError?.message || response?.error); }
            else { console.log("Activation state update acknowledged."); }
        });
    });

    let portChangeTimeout;
    serverPortInput.addEventListener('input', () => {
        if (!currentTabId) return; // Shouldn't happen if loaded correctly

        clearTimeout(portChangeTimeout);
        portChangeTimeout = setTimeout(() => {
            const portValue = serverPortInput.value;
            const newPort = parseInt(portValue, 10);

            if (!validatePort(portValue)) {
                 console.warn("Invalid port entered:", portValue);
                 serverPortInput.classList.add('invalid');
                 // Optionally briefly show error in status?
                 // statusDisplay.textContent = "Port must be 1025-65535.";
                 // statusDisplay.className = 'error';
                 return;
            }
            serverPortInput.classList.remove('invalid');

            console.log(`Popup sending new port ${newPort} for Tab ID ${currentTabId}`);
            chrome.runtime.sendMessage({ action: 'setServerPort', port: newPort, tabId: currentTabId }, (response) => {
                if (chrome.runtime.lastError || !response?.success) {
                    console.error("Error setting server port:", chrome.runtime.lastError?.message || response?.error);
                     updateStatusDisplay({ status: 'error', message: `Error saving port: ${chrome.runtime.lastError?.message || response?.error}` });
                } else {
                     console.log("Server port update acknowledged by background for tab", currentTabId);
                     // updateStatusDisplay({ status: 'info', message: `Port ${newPort} saved for this tab.`}); // Optional confirmation
                 }
            });
        }, 750);
    });

    testConnectionBtn.addEventListener('click', () => {
        if (!currentTabId) {
            updateStatusDisplay({ status: 'error', message: 'Cannot test: Tab ID unknown.' });
            return;
        }
        const portValue = serverPortInput.value;
        if (!validatePort(portValue)) {
            serverPortInput.classList.add('invalid');
            updateStatusDisplay({ status: 'error', message: 'Cannot test: Invalid port.' });
            return;
        }
        serverPortInput.classList.remove('invalid');
        const portToTest = parseInt(portValue, 10);

        statusDisplay.textContent = `Testing port ${portToTest}...`;
        statusDisplay.className = 'info';
        testConnectionBtn.disabled = true; // Disable while testing

        chrome.runtime.sendMessage({ action: 'testServerConnection', port: portToTest, tabId: currentTabId }, (response) => {
            testConnectionBtn.disabled = false; // Re-enable button
            if (chrome.runtime.lastError) {
                 console.error("Error testing connection:", chrome.runtime.lastError.message);
                 updateStatusDisplay({ status: 'error', message: `Test failed: ${chrome.runtime.lastError.message}` });
             } else if (response) {
                 console.log("Received test connection response:", response);
                 // The updateStatusDisplay function will handle formatting this response object
                 updateStatusDisplay(response);
             } else {
                 console.error("Received no response for test connection.");
                  updateStatusDisplay({ status: 'error', message: 'Test failed: No response from background script.' });
             }
        });
    });

    // --- Listen for global status updates from the background script ---
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        if (message.action === 'updatePopupResponse') {
            console.log("Popup received global response update:", message.lastResponse);
            updateStatusDisplay(message.lastResponse);
        }
    });

    // Initial load is triggered after getting tab ID
});