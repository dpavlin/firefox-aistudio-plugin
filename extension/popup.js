// Wait for the popup's DOM to be fully loaded
document.addEventListener('DOMContentLoaded', () => {
    // Get references to the UI elements
    const portInput = document.getElementById('serverPort');
    const serverCwdDisplay = document.getElementById('serverCwdDisplay'); // New CWD display
    const activationToggle = document.getElementById('activationToggle');
    const testConnectionBtn = document.getElementById('testConnectionBtn');
    const statusDisplay = document.getElementById('last-response');
    const enablePythonToggle = document.getElementById('serverEnablePython');
    const enableShellToggle = document.getElementById('serverEnableShell');
    const restartWarning = document.getElementById('restartWarning');

    let serverConfigLoaded = false;

    // --- Function to update status display ---
    function updateStatus(message, type = 'info', showRestartMsg = false) {
        // ... (keep existing implementation)
        if (!statusDisplay) return;
        let displayMessage = (typeof message === 'string' || message instanceof String) ? message : JSON.stringify(message);
        statusDisplay.textContent = displayMessage;
        statusDisplay.className = '';
        statusDisplay.classList.add(type);
        if (restartWarning) {
            restartWarning.style.display = showRestartMsg ? 'block' : 'none';
        }
        console.log(`Popup status (${type}):`, displayMessage, `Restart Msg: ${showRestartMsg}`);
    }

    // --- Disable server config toggles initially ---
    function setServerTogglesDisabled(disabled) {
        enablePythonToggle.disabled = disabled;
        enableShellToggle.disabled = disabled;
    }
    setServerTogglesDisabled(true);

    // --- Update CWD Display ---
    function updateCwdDisplay(cwdPath) {
        if (!serverCwdDisplay) return;
        if (cwdPath) {
            serverCwdDisplay.textContent = cwdPath;
            serverCwdDisplay.title = cwdPath; // Show full path on hover
        } else {
             serverCwdDisplay.textContent = 'N/A';
             serverCwdDisplay.title = 'Could not load server CWD';
        }
    }
    updateCwdDisplay('Loading...'); // Initial state


    // --- Request initial EXTENSION settings from background script ---
    updateStatus('Loading extension settings...', 'info');
    browser.runtime.sendMessage({ action: "getSettings" })
        .then(settings => {
            console.log('Popup received extension settings:', settings);
            let portIsValid = false;
            if (settings && settings.port !== undefined) {
                portInput.value = settings.port;
                portIsValid = validatePortInput(settings.port);
            } else {
                portInput.value = '';
                 portInput.classList.add('invalid');
                console.warn('Port setting missing in response from background.');
            }
            if (settings && settings.isActivated !== undefined) {
                activationToggle.checked = settings.isActivated;
            } else {
                activationToggle.checked = false;
                console.warn('Activation setting missing in response from background.');
            }

            if (portIsValid) {
                 loadServerConfig(); // Load server config (which includes CWD)
            } else {
                updateStatus('Extension settings loaded. Invalid port - cannot load server info.', 'warning');
                updateCwdDisplay(null); // Indicate CWD cannot be loaded
                setServerTogglesDisabled(true);
            }
        })
        .catch(error => {
            console.error('Error getting extension settings from background:', error);
            updateStatus(`Error loading extension settings: ${error.message}`, 'error');
            portInput.classList.add('invalid');
            portInput.value = '';
            activationToggle.checked = false;
            setServerTogglesDisabled(true);
            updateCwdDisplay(null); // Indicate CWD cannot be loaded
        });

    // --- Function to Load SERVER Config (now also updates CWD) ---
    function loadServerConfig() {
        updateStatus('Loading server configuration...', 'info');
        console.log('Popup requesting server config from background...');
        setServerTogglesDisabled(true);
        updateCwdDisplay('Loading...'); // Show loading state for CWD too

        browser.runtime.sendMessage({ action: "getServerConfig" })
            .then(response => {
                 console.log('Popup received server config/status response:', response);
                 if (response && response.success && response.data) {
                     const serverStatus = response.data;
                     // Update toggles based on RUNNING state from server
                     enablePythonToggle.checked = serverStatus.auto_run_python === true;
                     enableShellToggle.checked = serverStatus.auto_run_shell === true;
                     // Update CWD display
                     updateCwdDisplay(serverStatus.working_directory);
                     // Update status message
                     updateStatus('Extension and server settings loaded.', 'info');
                     setServerTogglesDisabled(false); // Enable toggles now
                     serverConfigLoaded = true;
                 } else {
                     const errorMsg = response?.error || 'Unknown error fetching server config.';
                     console.error('Failed to load server config:', errorMsg);
                     updateStatus(`Could not load server config: ${errorMsg}`, 'error');
                     enablePythonToggle.checked = false;
                     enableShellToggle.checked = false;
                     serverConfigLoaded = false;
                     setServerTogglesDisabled(true);
                     updateCwdDisplay(null); // Update CWD display with error state
                 }
            })
            .catch(error => {
                console.error('Error requesting server config from background:', error);
                updateStatus(`Error contacting background for server config: ${error.message}`, 'error');
                enablePythonToggle.checked = false;
                enableShellToggle.checked = false;
                serverConfigLoaded = false;
                setServerTogglesDisabled(true);
                updateCwdDisplay(null); // Update CWD display with error state
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
        serverConfigLoaded = false; // Mark server config as potentially stale on port change
        setServerTogglesDisabled(true);
        updateCwdDisplay('Loading...'); // Reset CWD display

        if (validatePortInput(newPort)) {
            console.log('Popup sending updated port:', newPort);
            browser.runtime.sendMessage({ action: "updateSetting", key: "port", value: parseInt(newPort, 10) })
                .then(() => {
                     updateStatus(`Port set to ${newPort}. Reloading server info...`, 'info');
                     loadServerConfig(); // Reload server config with the new port
                })
                .catch(error => {
                    console.error('Error sending port update:', error);
                    updateStatus(`Error saving port: ${error.message}`, 'error');
                    updateCwdDisplay(null); // Indicate CWD cannot be loaded
                });
        } else {
             updateStatus('Invalid port number (must be 1025-65535). Cannot load server info.', 'error');
             updateCwdDisplay(null);
        }
    });

    // --- Event Listener for Activation Toggle Change ---
    activationToggle.addEventListener('change', () => {
        // ... (keep existing implementation)
        const newState = activationToggle.checked;
        console.log('Popup sending updated activation state:', newState);
        browser.runtime.sendMessage({ action: "updateSetting", key: "isActivated", value: newState })
        .then(() => { updateStatus(`Auto-Capture ${newState ? 'Enabled' : 'Disabled'}`, 'info'); })
        .catch(error => {
            console.error('Error sending activation update:', error);
            updateStatus(`Error saving toggle state: ${error.message}`, 'error');
         });
    });

    // --- Function to handle server config toggle changes ---
    function handleServerConfigChange(key, value) {
        // ... (keep existing implementation)
        if (!serverConfigLoaded) {
             console.warn("Server config change ignored as config is not loaded/stale.");
             updateStatus("Cannot save server config - state may be out of sync.", "error");
             return;
        }
        console.log(`Popup sending server config update: ${key}=${value}`);
        updateStatus('Saving server configuration...', 'info');
        setServerTogglesDisabled(true);

        browser.runtime.sendMessage({ action: "updateServerConfig", key: key, value: value })
        .then(response => {
             console.log("Popup received response for server config update:", response);
             if (response && response.success) {
                 updateStatus(response.message || 'Server config saved.', 'success', true);
             } else {
                  const errorMsg = response?.message || response?.error || 'Unknown error saving server config.';
                 updateStatus(`Failed to save server config: ${errorMsg}`, 'error');
             }
        })
        .catch(error => {
             console.error('Error sending server config update message:', error);
             updateStatus(`Error contacting background to save config: ${error.message}`, 'error');
        })
        .finally(() => {
              if (serverConfigLoaded) {
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


    // --- Event Listener for Test Connection Button (Update CWD display on success) ---
    testConnectionBtn.addEventListener('click', async () => {
        testConnectionBtn.disabled = true;
        updateStatus('Testing connection...', 'info');
        updateCwdDisplay('Testing...'); // Show testing state for CWD
        console.log('Popup requesting connection test...');

        try {
            const response = await browser.runtime.sendMessage({ action: "testConnection" });
            console.log('Popup received test connection response:', response);

            if (response && response.success && response.data) { // Check for data object
                 const serverStatus = response.data;
                 let statusMsg = `Connection successful!\n`;
                 statusMsg += `Server running on port ${serverStatus?.port || '?'}.\n`;
                 statusMsg += `Python Auto-Run: ${serverStatus?.auto_run_python ?? '?'}\n`;
                 statusMsg += `Shell Auto-Run: ${serverStatus?.auto_run_shell ?? '?'}\n`;
                 statusMsg += `(This reflects the RUNNING server state)`;

                 updateStatus(statusMsg, 'success');
                 // Update CWD display from the successful test response
                 updateCwdDisplay(serverStatus?.working_directory);
                 // Re-sync toggles based on tested server state
                 enablePythonToggle.checked = serverStatus?.auto_run_python === true;
                 enableShellToggle.checked = serverStatus?.auto_run_shell === true;
                 serverConfigLoaded = true; // Mark as loaded/synced
                 setServerTogglesDisabled(false);

            } else {
                 let errorMsg = 'Connection failed.';
                 // ... (keep existing error message handling) ...
                 if (response && response.error) { errorMsg += `\nReason: ${response.error}`; }
                 else if (response && response.message) { errorMsg = `Server Error: ${response.message}`; }
                 else if (response && response.data && response.data.error) { errorMsg = `Server Error: ${response.data.error}`; }
                 else { errorMsg += ' Check server status.'; }

                 updateStatus(errorMsg, 'error');
                 updateCwdDisplay(null); // Indicate CWD failed
                 serverConfigLoaded = false; // Mark as not loaded
                 setServerTogglesDisabled(true); // Disable server toggles on fail
            }
        } catch (error) {
            console.error('Error during test connection message:', error);
            updateStatus(`Error testing connection: ${error.message}\nIs the background script running?`, 'error');
            updateCwdDisplay(null);
            serverConfigLoaded = false;
            setServerTogglesDisabled(true);
        } finally {
            testConnectionBtn.disabled = false;
        }
    });

     // --- Listener for status updates from background ---
     browser.runtime.onMessage.addListener((message, sender) => {
         // ... (keep existing implementation)
         if (message.action === "updatePopupStatus") {
             console.log("Popup received status update from background:", message);
             updateStatus(message.message, message.type || 'info');
             return Promise.resolve();
         }
         return false;
     });

});
// @@FILENAME@@ extension/popup.js