// Wait for the popup's DOM to be fully loaded
document.addEventListener('DOMContentLoaded', () => {
    // Get references to the UI elements
    const portInput = document.getElementById('serverPort');
    const activationToggle = document.getElementById('activationToggle');
    const testConnectionBtn = document.getElementById('testConnectionBtn');
    const statusDisplay = document.getElementById('last-response');
    // Server Config elements
    const enablePythonToggle = document.getElementById('serverEnablePython');
    const enableShellToggle = document.getElementById('serverEnableShell');
    const restartWarning = document.getElementById('restartWarning');
    // Server Info elements
    const serverCwdDisplay = document.getElementById('serverCwdDisplay');
    const serverSaveDirDisplay = document.getElementById('serverSaveDirDisplay');
    const serverLogDirDisplay = document.getElementById('serverLogDirDisplay');
    const serverGitStatusDisplay = document.getElementById('serverGitStatusDisplay');

    let serverConfigLoaded = false; // Flag to track if server config fetch succeeded

    // --- Function to update status display ---
    function updateStatus(message, type = 'info', showRestartMsg = false) {
        // ... (implementation unchanged) ...
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

    // --- Update Server Info Displays ---
    function updateServerInfoDisplay(serverStatus) {
        const naText = 'N/A';
        const loadingText = 'Loading...';

        const cwdPath = serverStatus?.working_directory;
        const saveDir = serverStatus?.save_directory;
        const logDir = serverStatus?.log_directory;
        const gitStatus = serverStatus?.is_git_repo; // Boolean or undefined

        if (serverCwdDisplay) {
            serverCwdDisplay.textContent = cwdPath || naText;
            serverCwdDisplay.title = cwdPath || 'Could not load server CWD';
        }
        if (serverSaveDirDisplay) {
            serverSaveDirDisplay.textContent = saveDir ? `./${saveDir}` : naText; // Prepend ./ for clarity
            serverSaveDirDisplay.title = saveDir ? `Save directory (relative to CWD): ./${saveDir}` : 'Could not load save directory';
        }
        if (serverLogDirDisplay) {
            serverLogDirDisplay.textContent = logDir ? `./${logDir}` : naText; // Prepend ./
            serverLogDirDisplay.title = logDir ? `Log directory (relative to CWD): ./${logDir}` : 'Could not load log directory';
        }
        if (serverGitStatusDisplay) {
             if (gitStatus === true) {
                 serverGitStatusDisplay.textContent = 'Enabled';
                 serverGitStatusDisplay.className = 'info-text status-true'; // Apply green style
                 serverGitStatusDisplay.title = 'Server is running inside a Git repository.';
             } else if (gitStatus === false) {
                 serverGitStatusDisplay.textContent = 'Disabled';
                 serverGitStatusDisplay.className = 'info-text status-false'; // Apply red style
                 serverGitStatusDisplay.title = 'Server is not running inside a Git repository.';
             } else {
                 serverGitStatusDisplay.textContent = naText;
                 serverGitStatusDisplay.className = 'info-text'; // Reset style
                 serverGitStatusDisplay.title = 'Could not determine Git status.';
             }
        }
    }
    // Set initial loading state for info displays
    updateServerInfoDisplay(null);


    // --- Request initial EXTENSION settings from background script ---
    updateStatus('Loading extension settings...', 'info');
    browser.runtime.sendMessage({ action: "getSettings" })
        .then(settings => {
            // ... (loading port and activation toggle unchanged) ...
            console.log('Popup received extension settings:', settings);
            let portIsValid = false;
            if (settings && settings.port !== undefined) {
                portInput.value = settings.port;
                portIsValid = validatePortInput(settings.port);
            } else {
                portInput.value = ''; portInput.classList.add('invalid');
                console.warn('Port setting missing in response from background.');
            }
            if (settings && settings.isActivated !== undefined) {
                activationToggle.checked = settings.isActivated;
            } else {
                activationToggle.checked = false;
                console.warn('Activation setting missing in response from background.');
            }

            if (portIsValid) {
                 loadServerConfig(); // Load server config (which includes CWD & other info)
            } else {
                updateStatus('Extension settings loaded. Invalid port - cannot load server info.', 'warning');
                updateServerInfoDisplay(null); // Update displays to N/A
                setServerTogglesDisabled(true);
            }
        })
        .catch(error => {
            // ... (error handling unchanged) ...
            console.error('Error getting extension settings from background:', error);
            updateStatus(`Error loading extension settings: ${error.message}`, 'error');
            portInput.classList.add('invalid'); portInput.value = '';
            activationToggle.checked = false;
            setServerTogglesDisabled(true);
            updateServerInfoDisplay(null);
        });

    // --- Function to Load SERVER Config & Info ---
    function loadServerConfig() {
        updateStatus('Loading server information...', 'info'); // Updated message
        console.log('Popup requesting server config/status from background...');
        setServerTogglesDisabled(true);
        updateServerInfoDisplay(null); // Show loading state

        browser.runtime.sendMessage({ action: "getServerConfig" })
            .then(response => {
                 console.log('Popup received server config/status response:', response);
                 if (response && response.success && response.data) {
                     const serverStatus = response.data;
                     // Update toggles based on RUNNING state from server
                     enablePythonToggle.checked = serverStatus.auto_run_python === true;
                     enableShellToggle.checked = serverStatus.auto_run_shell === true;
                     // Update all info displays
                     updateServerInfoDisplay(serverStatus);
                     // Update status message
                     updateStatus('Extension and server info loaded.', 'info');
                     setServerTogglesDisabled(false); // Enable toggles now
                     serverConfigLoaded = true;
                 } else {
                     const errorMsg = response?.error || 'Unknown error fetching server info.';
                     console.error('Failed to load server info:', errorMsg);
                     updateStatus(`Could not load server info: ${errorMsg}`, 'error');
                     enablePythonToggle.checked = false; enableShellToggle.checked = false;
                     serverConfigLoaded = false; setServerTogglesDisabled(true);
                     updateServerInfoDisplay(null); // Update displays to N/A
                 }
            })
            .catch(error => {
                console.error('Error requesting server config/status from background:', error);
                updateStatus(`Error contacting background for server info: ${error.message}`, 'error');
                enablePythonToggle.checked = false; enableShellToggle.checked = false;
                serverConfigLoaded = false; setServerTogglesDisabled(true);
                updateServerInfoDisplay(null); // Update displays to N/A
            });
    }


    // --- Validate Port Input ---
    function validatePortInput(portValue) {
        // ... (implementation unchanged) ...
        const port = parseInt(portValue, 10);
        const isValid = !isNaN(port) && port >= 1025 && port <= 65535;
        if (isValid) { portInput.classList.remove('invalid'); }
        else { portInput.classList.add('invalid'); }
        return isValid;
    }

    // --- Event Listener for Port Input Change ---
    portInput.addEventListener('input', () => {
        // ... (implementation unchanged, loadServerConfig will update displays) ...
        const newPort = portInput.value;
        serverConfigLoaded = false;
        setServerTogglesDisabled(true);
        updateServerInfoDisplay(null); // Show loading state

        if (validatePortInput(newPort)) {
            browser.runtime.sendMessage({ action: "updateSetting", key: "port", value: parseInt(newPort, 10) })
                .then(() => {
                     updateStatus(`Port set to ${newPort}. Reloading server info...`, 'info');
                     loadServerConfig();
                })
                .catch(error => {
                    updateStatus(`Error saving port: ${error.message}`, 'error');
                    updateServerInfoDisplay(null);
                });
        } else {
             updateStatus('Invalid port number (must be 1025-65535). Cannot load server info.', 'error');
             updateServerInfoDisplay(null);
        }
    });

    // --- Event Listener for Activation Toggle Change ---
    activationToggle.addEventListener('change', () => {
        // ... (implementation unchanged) ...
         const newState = activationToggle.checked;
         browser.runtime.sendMessage({ action: "updateSetting", key: "isActivated", value: newState })
         .then(() => { updateStatus(`Auto-Capture ${newState ? 'Enabled' : 'Disabled'}`, 'info'); })
         .catch(error => { updateStatus(`Error saving toggle state: ${error.message}`, 'error'); });
    });

    // --- Function to handle server config toggle changes ---
    function handleServerConfigChange(key, value) {
        // ... (implementation unchanged) ...
        if (!serverConfigLoaded) {
             updateStatus("Cannot save server config - state may be out of sync.", "error"); return;
        }
        updateStatus('Saving server configuration...', 'info');
        setServerTogglesDisabled(true);
        browser.runtime.sendMessage({ action: "updateServerConfig", key: key, value: value })
        .then(response => {
             if (response && response.success) { updateStatus(response.message || 'Server config saved.', 'success', true); }
             else { updateStatus(`Failed to save server config: ${response?.message || response?.error || 'Unknown error'}`, 'error'); }
        })
        .catch(error => { updateStatus(`Error contacting background to save config: ${error.message}`, 'error'); })
        .finally(() => { if (serverConfigLoaded) { setServerTogglesDisabled(false); } });
    }

    // --- Event Listeners for Server Config Toggles ---
    enablePythonToggle.addEventListener('change', () => {
        handleServerConfigChange('enable_python_run', enablePythonToggle.checked);
    });

    enableShellToggle.addEventListener('change', () => {
        handleServerConfigChange('enable_shell_run', enableShellToggle.checked);
    });


    // --- Event Listener for Test Connection Button (Update ALL info displays on success) ---
    testConnectionBtn.addEventListener('click', async () => {
        testConnectionBtn.disabled = true;
        updateStatus('Testing connection...', 'info');
        updateServerInfoDisplay(null); // Show loading state for all server info
        console.log('Popup requesting connection test...');

        try {
            const response = await browser.runtime.sendMessage({ action: "testConnection" });
            console.log('Popup received test connection response:', response);

            if (response && response.success && response.data) {
                 const serverStatus = response.data;
                 let statusMsg = `Connection successful!\n`;
                 // ... (status message generation unchanged) ...
                 statusMsg += `Server running on port ${serverStatus?.port || '?'}.\n`;
                 statusMsg += `Python Auto-Run: ${serverStatus?.auto_run_python ?? '?'}\n`;
                 statusMsg += `Shell Auto-Run: ${serverStatus?.auto_run_shell ?? '?'}\n`;
                 statusMsg += `(This reflects the RUNNING server state)`;

                 updateStatus(statusMsg, 'success');
                 // Update ALL server info displays from the successful test response
                 updateServerInfoDisplay(serverStatus);
                 // Re-sync toggles based on tested server state
                 enablePythonToggle.checked = serverStatus?.auto_run_python === true;
                 enableShellToggle.checked = serverStatus?.auto_run_shell === true;
                 serverConfigLoaded = true;
                 setServerTogglesDisabled(false);

            } else {
                 let errorMsg = 'Connection failed.';
                 // ... (error handling unchanged) ...
                 if (response && response.error) { errorMsg += `\nReason: ${response.error}`; }
                 else if (response && response.message) { errorMsg = `Server Error: ${response.message}`; }
                 else if (response && response.data && response.data.error) { errorMsg = `Server Error: ${response.data.error}`; }
                 else { errorMsg += ' Check server status.'; }

                 updateStatus(errorMsg, 'error');
                 updateServerInfoDisplay(null); // Update displays to N/A
                 serverConfigLoaded = false;
                 setServerTogglesDisabled(true);
            }
        } catch (error) {
            console.error('Error during test connection message:', error);
            updateStatus(`Error testing connection: ${error.message}\nIs the background script running?`, 'error');
            updateServerInfoDisplay(null);
            serverConfigLoaded = false;
            setServerTogglesDisabled(true);
        } finally {
            testConnectionBtn.disabled = false;
        }
    });

     // --- Listener for status updates from background ---
     browser.runtime.onMessage.addListener((message, sender) => {
         // ... (implementation unchanged) ...
         if (message.action === "updatePopupStatus") {
             console.log("Popup received status update from background:", message);
             updateStatus(message.message, message.type || 'info');
             return Promise.resolve();
         }
         return false;
     });

});
// @@FILENAME@@ extension/popup.js