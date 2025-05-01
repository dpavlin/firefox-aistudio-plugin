// @@FILENAME@@ extension/popup.js
// Wait for the popup's DOM to be fully loaded
document.addEventListener('DOMContentLoaded', () => {
    // Get references to the UI elements
    const portInput = document.getElementById('serverPort');
    const activationToggle = document.getElementById('activationToggle');
    const testConnectionBtn = document.getElementById('testConnectionBtn');
    const statusDisplay = document.getElementById('last-response');
    // New server config elements
    const enablePythonToggle = document.getElementById('serverEnablePython');
    const enableShellToggle = document.getElementById('serverEnableShell');
    const restartWarning = document.getElementById('restartWarning');

    let serverConfigLoaded = false; // Flag to track if server config fetch succeeded

    // --- Function to update status display ---
    function updateStatus(message, type = 'info', showRestartMsg = false) {
        if (!statusDisplay) return;
        // Ensure message is a string
        let displayMessage = (typeof message === 'string' || message instanceof String) ? message : JSON.stringify(message);

        statusDisplay.textContent = displayMessage;
        statusDisplay.className = ''; // Clear previous classes
        statusDisplay.classList.add(type); // Add 'info', 'success', 'error', or 'warning'

        // Show/hide restart warning based on flag
        if (restartWarning) {
            restartWarning.style.display = showRestartMsg ? 'block' : 'none';
        }
        console.log(`Popup status (${type}):`, displayMessage, `Restart Msg: ${showRestartMsg}`);
    }

    // --- Disable server config toggles initially ---
    function setServerTogglesDisabled(disabled) {
        enablePythonToggle.disabled = disabled;
        enableShellToggle.disabled = disabled;
        // Optionally add visual styling for disabled state if not handled by CSS
    }
    setServerTogglesDisabled(true); // Disable until loaded

    // --- Request initial EXTENSION settings from background script ---
    updateStatus('Loading extension settings...', 'info');
    console.log('Popup requesting extension settings from background...');
    browser.runtime.sendMessage({ action: "getSettings" })
        .then(settings => {
            console.log('Popup received extension settings:', settings);
            let portIsValid = false;
            if (settings && settings.port !== undefined) {
                portInput.value = settings.port;
                portIsValid = validatePortInput(settings.port); // Validate loaded port
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

            // Now try to load SERVER config if port is valid
            if (portIsValid) {
                 loadServerConfig();
            } else {
                updateStatus('Extension settings loaded. Invalid port - cannot load server config.', 'warning');
            }
        })
        .catch(error => {
            console.error('Error getting extension settings from background:', error);
            updateStatus(`Error loading extension settings: ${error.message}`, 'error');
            portInput.classList.add('invalid');
            portInput.value = ''; // Clear on error
            activationToggle.checked = false;
            setServerTogglesDisabled(true); // Keep server toggles disabled
        });

    // --- Function to Load SERVER Config ---
    function loadServerConfig() {
        updateStatus('Loading server configuration...', 'info');
        console.log('Popup requesting server config from background...');
        setServerTogglesDisabled(true); // Disable while loading

        browser.runtime.sendMessage({ action: "getServerConfig" })
            .then(response => {
                 console.log('Popup received server config response:', response);
                 if (response && response.success && response.data) {
                     const config = response.data;
                     enablePythonToggle.checked = config.auto_run_python || false; // Use current state from server status
                     enableShellToggle.checked = config.auto_run_shell || false;   // Use current state from server status
                     updateStatus('Extension and server settings loaded.', 'info');
                     setServerTogglesDisabled(false); // Enable toggles now
                     serverConfigLoaded = true;
                 } else {
                     // Handle failure to load server config
                     const errorMsg = response?.error || 'Unknown error fetching server config.';
                     console.error('Failed to load server config:', errorMsg);
                     updateStatus(`Could not load server config: ${errorMsg}`, 'error');
                     // Keep toggles disabled, maybe show default state greyed out?
                     enablePythonToggle.checked = false;
                     enableShellToggle.checked = false;
                     serverConfigLoaded = false;
                     setServerTogglesDisabled(true);
                 }
            })
            .catch(error => {
                console.error('Error requesting server config from background:', error);
                updateStatus(`Error contacting background for server config: ${error.message}`, 'error');
                enablePythonToggle.checked = false;
                enableShellToggle.checked = false;
                serverConfigLoaded = false;
                setServerTogglesDisabled(true);
            });
    }


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
        const wasConfigLoaded = serverConfigLoaded; // Store state before potential reload
        serverConfigLoaded = false; // Mark server config as potentially stale
        setServerTogglesDisabled(true); // Disable server toggles until reloaded

        if (validatePortInput(newPort)) {
            console.log('Popup sending updated port:', newPort);
            browser.runtime.sendMessage({
                action: "updateSetting",
                key: "port",
                value: parseInt(newPort, 10) // Send as number
            }).then(() => {
                 updateStatus(`Port set to ${newPort}. Reloading server config...`, 'info');
                 // Attempt to reload server config with the new port
                 loadServerConfig();
            }).catch(error => {
                console.error('Error sending port update:', error);
                updateStatus(`Error saving port: ${error.message}`, 'error');
            });
        } else {
             updateStatus('Invalid port number (must be 1025-65535). Cannot load server config.', 'error');
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
        }).then(() => {
             updateStatus(`Auto-Capture ${newState ? 'Enabled' : 'Disabled'}`, 'info');
        }).catch(error => {
            console.error('Error sending activation update:', error);
            updateStatus(`Error saving toggle state: ${error.message}`, 'error');
         });
    });

    // --- Function to handle server config toggle changes ---
    function handleServerConfigChange(key, value) {
        if (!serverConfigLoaded) {
             console.warn("Server config change ignored as config is not loaded/stale.");
             updateStatus("Cannot save server config - state may be out of sync.", "error");
             // Optionally revert the toggle visually?
             return;
        }
        console.log(`Popup sending server config update: ${key}=${value}`);
        updateStatus('Saving server configuration...', 'info');
        setServerTogglesDisabled(true); // Disable while saving

        browser.runtime.sendMessage({
            action: "updateServerConfig",
            key: key,
            value: value
        })
        .then(response => {
             console.log("Popup received response for server config update:", response);
             if (response && response.success) {
                 updateStatus(response.message || 'Server config saved successfully.', 'success', true); // Show restart message
             } else {
                  const errorMsg = response?.message || response?.error || 'Unknown error saving server config.';
                 updateStatus(`Failed to save server config: ${errorMsg}`, 'error');
                 // Optionally revert the toggle change if save failed
                 // Re-enable toggles even on failure so user can retry
             }
        })
        .catch(error => {
             console.error('Error sending server config update message:', error);
             updateStatus(`Error contacting background to save config: ${error.message}`, 'error');
        })
        .finally(() => {
             // Re-enable toggles after attempt, unless we are reloading config
             // If the port changes, loadServerConfig handles re-enabling.
             // Only re-enable here if it wasn't a port change that triggered this.
              if (serverConfigLoaded) { // Check flag again in case port changed during save
                  setServerTogglesDisabled(false);
              }
        });
    }

    // --- Event Listeners for Server Config Toggles ---
    enablePythonToggle.addEventListener('change', () => {
        handleServerConfigChange('enable_python_run', enablePythonToggle.checked);
    });

    enableShellToggle.addEventListener('change', () => {
        handleServerConfigChange('enable_shell_run', enableShellToggle.checked);
    });


    // --- Event Listener for Test Connection Button ---
    testConnectionBtn.addEventListener('click', async () => {
        testConnectionBtn.disabled = true;
        updateStatus('Testing connection...', 'info');
        console.log('Popup requesting connection test...');

        try {
            // Test connection uses the *current* extension port setting
            const response = await browser.runtime.sendMessage({ action: "testConnection" });
            console.log('Popup received test connection response:', response);

            if (response && response.success) {
                 const serverStatus = response.data; // Server status data
                 let statusMsg = `Connection successful!\n`;
                 statusMsg += `Server running on port ${serverStatus?.port || '?'}.\n`; // Use status port
                 statusMsg += `Python Auto-Run: ${serverStatus?.auto_run_python ?? '?'}\n`; // Use status value
                 statusMsg += `Shell Auto-Run: ${serverStatus?.auto_run_shell ?? '?'}\n`;   // Use status value
                 statusMsg += `(This reflects the RUNNING server state)`;

                 updateStatus(statusMsg, 'success');
                 // Optionally re-sync UI toggles if server state differs? Or trust loadServerConfig.
                 // Maybe just reload server config after successful test?
                 if (serverConfigLoaded) { // Only if we were loaded before
                     loadServerConfig(); // Re-sync server config UI after test
                 }

            } else {
                 let errorMsg = 'Connection failed.';
                 // (Error handling remains the same as before)
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

     // --- Listener for status updates from background ---
     browser.runtime.onMessage.addListener((message, sender) => {
         if (message.action === "updatePopupStatus") {
             console.log("Popup received status update from background:", message);
             updateStatus(message.message, message.type || 'info');
             return Promise.resolve();
         }
         return false;
     });

});
// @@FILENAME@@ extension/popup.js