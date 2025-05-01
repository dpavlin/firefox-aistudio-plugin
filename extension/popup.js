// @@FILENAME@@ extension/popup.js
// Wait for the popup's DOM to be fully loaded
document.addEventListener('DOMContentLoaded', () => {
    // Get references to the UI elements
    const portInput = document.getElementById('serverPort');
    const activationToggle = document.getElementById('activationToggle');
    const testConnectionBtn = document.getElementById('testConnectionBtn');
    const statusDisplay = document.getElementById('last-response');

    // --- Function to update status display ---
    function updateStatus(message, type = 'info') {
        if (!statusDisplay) return;
        statusDisplay.textContent = message;
        statusDisplay.className = ''; // Clear previous classes
        statusDisplay.classList.add(type); // Add 'info', 'success', or 'error'
        console.log(`Popup status (${type}):`, message);
    }

    // --- Request initial settings from background script ---
    updateStatus('Loading settings...', 'info');
    console.log('Popup requesting settings from background...');
    browser.runtime.sendMessage({ action: "getSettings" })
        .then(settings => {
            console.log('Popup received settings:', settings);
            if (settings && settings.port !== undefined) {
                portInput.value = settings.port;
                validatePortInput(settings.port); // Validate loaded port
            } else {
                portInput.value = ''; // Clear if port is missing
                 portInput.classList.add('invalid'); // Mark as invalid if missing
                console.warn('Port setting missing in response from background.');
            }
            if (settings && settings.isActivated !== undefined) {
                activationToggle.checked = settings.isActivated;
            } else {
                activationToggle.checked = false; // Default to off if missing
                console.warn('Activation setting missing in response from background.');
            }
            updateStatus('Settings loaded.', 'info'); // Indicate loading complete
        })
        .catch(error => {
            console.error('Error getting settings from background:', error);
            updateStatus(`Error loading settings: ${error.message}`, 'error');
            portInput.classList.add('invalid');
            portInput.value = ''; // Clear on error
            activationToggle.checked = false;
        });

    // --- Validate Port Input ---
    function validatePortInput(portValue) {
        const port = parseInt(portValue, 10);
        const isValid = !isNaN(port) && port >= 1025 && port <= 65535;
        if (isValid) {
            portInput.classList.remove('invalid');
        } else {
            portInput.classList.add('invalid');
        }
        return isValid;
    }

    // --- Event Listener for Port Input Change ---
    portInput.addEventListener('input', () => {
        const newPort = portInput.value;
        if (validatePortInput(newPort)) {
            console.log('Popup sending updated port:', newPort);
            browser.runtime.sendMessage({
                action: "updateSetting",
                key: "port",
                value: parseInt(newPort, 10) // Send as number
            }).catch(error => {
                console.error('Error sending port update:', error);
                updateStatus(`Error saving port: ${error.message}`, 'error');
            });
             updateStatus(`Port set to ${newPort}`, 'info');
        } else {
             updateStatus('Invalid port number (must be 1025-65535).', 'error');
        }
    });

    // --- Event Listener for Activation Toggle Change ---
    activationToggle.addEventListener('change', () => {
        const newState = activationToggle.checked;
        console.log('Popup sending updated activation state:', newState);
        browser.runtime.sendMessage({
            action: "updateSetting",
            key: "isActivated",
            value: newState
        }).catch(error => {
            console.error('Error sending activation update:', error);
            updateStatus(`Error saving toggle state: ${error.message}`, 'error');
         });
         updateStatus(`Auto-Capture ${newState ? 'Enabled' : 'Disabled'}`, 'info');
    });

    // --- Event Listener for Test Connection Button ---
    testConnectionBtn.addEventListener('click', async () => {
        testConnectionBtn.disabled = true;
        updateStatus('Testing connection...', 'info');
        console.log('Popup requesting connection test...');

        try {
            const response = await browser.runtime.sendMessage({ action: "testConnection" });
            console.log('Popup received test connection response:', response);

            if (response && response.success) {
                // Use status info if available, otherwise generic success
                const serverStatus = response.data; // Assuming background sends server status data
                 let statusMsg = `Connection successful!\nServer Status:\n`;
                 if (serverStatus) {
                     statusMsg += `  Port: ${serverStatus.port}\n`;
                     statusMsg += `  Git Repo: ${serverStatus.is_git_repo}\n`;
                     statusMsg += `  Auto Run Py: ${serverStatus.auto_run_python}\n`;
                     statusMsg += `  Auto Run Shell: ${serverStatus.auto_run_shell}`;
                 } else {
                     statusMsg = 'Connection successful! (No detailed status returned)';
                 }
                updateStatus(statusMsg, 'success');
            } else {
                // Handle specific errors if background provides them
                 let errorMsg = 'Connection failed.';
                 if (response && response.error) {
                     errorMsg += `\nReason: ${response.error}`;
                 } else if (response && response.message) { // If background just sent back the server's error message
                    errorMsg = `Server Error: ${response.message}`;
                 } else if (response && response.data && response.data.error) { // check nested error
                    errorMsg = `Server Error: ${response.data.error}`;
                 } else {
                    errorMsg += ' Check if server is running on the correct port and accessible.';
                 }
                updateStatus(errorMsg, 'error');
            }
        } catch (error) {
            console.error('Error during test connection message:', error);
            updateStatus(`Error testing connection: ${error.message}\nIs the background script running?`, 'error');
        } finally {
            testConnectionBtn.disabled = false;
        }
    });

     // --- Listener for status updates from background (optional but good) ---
     browser.runtime.onMessage.addListener((message, sender) => {
         // Only process messages relevant to the popup's status display
         if (message.action === "updatePopupStatus") {
             console.log("Popup received status update from background:", message);
             updateStatus(message.message, message.type || 'info');
             return Promise.resolve(); // Indicate message processed asynchronously if needed
         }
         // Ignore other messages intended for content scripts etc.
         return false; // Indicate message not handled by this listener
     });

});
// @@FILENAME@@ extension/popup.js