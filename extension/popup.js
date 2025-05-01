// @@FILENAME@@ extension/popup.js
document.addEventListener('DOMContentLoaded', () => {
    // UI Elements
    const portInput = document.getElementById('serverPort');
    const activationToggle = document.getElementById('activationToggle');
    const testConnectionBtn = document.getElementById('testConnectionBtn');
    const statusDisplay = document.getElementById('last-response');
    const enablePythonToggle = document.getElementById('serverEnablePython');
    const enableShellToggle = document.getElementById('serverEnableShell');
    const restartWarning = document.getElementById('restartWarning');
    const serverCwdDisplay = document.getElementById('serverCwdDisplay');
    const serverSaveDirDisplay = document.getElementById('serverSaveDirDisplay');
    const serverLogDirDisplay = document.getElementById('serverLogDirDisplay');
    const serverGitStatusDisplay = document.getElementById('serverGitStatusDisplay');

    let serverConfigLoaded = false;
    let currentTabId = null; // Store the active tab ID for this popup instance

    // --- Utility Functions ---
    function updateStatus(message, type = 'info', showRestartMsg = false) { /* ... unchanged ... */ if (!statusDisplay) return; let displayMessage = (typeof message === 'string' || message instanceof String) ? message : JSON.stringify(message); statusDisplay.textContent = displayMessage; statusDisplay.className = ''; statusDisplay.classList.add(type); if (restartWarning) { restartWarning.style.display = showRestartMsg ? 'block' : 'none'; } console.log(`Popup status (${type}):`, displayMessage, `Restart Msg: ${showRestartMsg}`); }
    function setServerTogglesDisabled(disabled) { /* ... unchanged ... */ enablePythonToggle.disabled = disabled; enableShellToggle.disabled = disabled; }
    function updateServerInfoDisplay(serverStatus) { /* ... unchanged ... */ const naText = 'N/A'; const cwdPath = serverStatus?.working_directory; const saveDir = serverStatus?.save_directory; const logDir = serverStatus?.log_directory; const gitStatus = serverStatus?.is_git_repo; if (serverCwdDisplay) { serverCwdDisplay.textContent = cwdPath || naText; serverCwdDisplay.title = cwdPath || 'Could not load CWD'; } if (serverSaveDirDisplay) { serverSaveDirDisplay.textContent = saveDir ? `./${saveDir}` : naText; serverSaveDirDisplay.title = saveDir ? `./${saveDir}` : 'Could not load Save Dir'; } if (serverLogDirDisplay) { serverLogDirDisplay.textContent = logDir ? `./${logDir}` : naText; serverLogDirDisplay.title = logDir ? `./${logDir}` : 'Could not load Log Dir'; } if (serverGitStatusDisplay) { if (gitStatus === true) { serverGitStatusDisplay.textContent = 'Enabled'; serverGitStatusDisplay.className = 'info-text status-true'; serverGitStatusDisplay.title = 'Git repo detected.'; } else if (gitStatus === false) { serverGitStatusDisplay.textContent = 'Disabled'; serverGitStatusDisplay.className = 'info-text status-false'; serverGitStatusDisplay.title = 'Not a Git repo.'; } else { serverGitStatusDisplay.textContent = naText; serverGitStatusDisplay.className = 'info-text'; serverGitStatusDisplay.title = 'Could not determine Git status.'; } } }
    function validatePortInput(portValue) { /* ... unchanged ... */ const port = parseInt(portValue, 10); const isValid = !isNaN(port) && port >= 1025 && port <= 65535; if (isValid) { portInput.classList.remove('invalid'); } else { portInput.classList.add('invalid'); } return isValid; }

    // --- Initialization ---
    setServerTogglesDisabled(true);
    updateServerInfoDisplay(null);
    updateStatus('Initializing...', 'info');

    // ** Get current tab ID first **
    browser.tabs.query({ active: true, currentWindow: true })
        .then((tabs) => {
            if (!tabs || tabs.length === 0 || !tabs[0].id) {
                throw new Error("Could not get active tab ID.");
            }
            currentTabId = tabs[0].id;
            console.log("Popup loaded for Tab ID:", currentTabId);
            loadExtensionSettings(); // Load settings now that we have the tab ID
        })
        .catch(error => {
            console.error("Error getting current tab:", error);
            updateStatus(`Error initializing popup: ${error.message}`, 'error');
            // Disable interactive elements if we don't have a tab ID
            portInput.disabled = true;
            activationToggle.disabled = true;
            testConnectionBtn.disabled = true;
            setServerTogglesDisabled(true);
            updateServerInfoDisplay(null);
        });

    // --- Load EXTENSION Settings ---
    function loadExtensionSettings() {
        if (!currentTabId) return; // Should not happen if called correctly
        updateStatus('Loading settings...', 'info');
        // ** Send Tab ID **
        browser.runtime.sendMessage({ action: "getSettings", tabId: currentTabId })
            .then(settings => {
                console.log(`Popup received settings for Tab ${currentTabId}:`, settings);
                let portIsValid = false;
                if (settings?.port !== undefined) {
                    portInput.value = settings.port; // This is the tab-specific or default port
                    portIsValid = validatePortInput(settings.port);
                } else { portInput.value = ''; portInput.classList.add('invalid'); }
                activationToggle.checked = settings?.isActivated === true;

                // Load server info using the determined port for this tab
                if (portIsValid) { loadServerConfig(); }
                else { updateStatus('Invalid port - cannot load server info.', 'warning'); updateServerInfoDisplay(null); setServerTogglesDisabled(true); }
            })
            .catch(error => {
                console.error(`Error getting settings for Tab ${currentTabId}:`, error);
                updateStatus(`Error loading settings: ${error.message}`, 'error');
                portInput.classList.add('invalid'); portInput.value = ''; activationToggle.checked = false;
                setServerTogglesDisabled(true); updateServerInfoDisplay(null);
            });
    }

    // --- Function to Load SERVER Config & Info ---
    function loadServerConfig() {
        if (!currentTabId) return; // Need tab context
        updateStatus('Loading server information...', 'info');
        setServerTogglesDisabled(true); updateServerInfoDisplay(null); // Show loading
        // ** Send Tab ID **
        browser.runtime.sendMessage({ action: "getServerConfig", tabId: currentTabId })
            .then(response => {
                 if (response?.success && response.data) {
                     const serverStatus = response.data;
                     enablePythonToggle.checked = serverStatus.auto_run_python === true;
                     enableShellToggle.checked = serverStatus.auto_run_shell === true;
                     updateServerInfoDisplay(serverStatus); // Update CWD, Save, Log, Git
                     updateStatus('Extension and server info loaded.', 'info');
                     setServerTogglesDisabled(false); serverConfigLoaded = true;
                 } else {
                     const errorMsg = response?.error || 'Unknown error fetching server info.';
                     updateStatus(`Could not load server info: ${errorMsg}`, 'error');
                     enablePythonToggle.checked = false; enableShellToggle.checked = false;
                     serverConfigLoaded = false; setServerTogglesDisabled(true); updateServerInfoDisplay(null);
                 }
            })
            .catch(error => {
                updateStatus(`Error contacting background for server info: ${error.message}`, 'error');
                enablePythonToggle.checked = false; enableShellToggle.checked = false;
                serverConfigLoaded = false; setServerTogglesDisabled(true); updateServerInfoDisplay(null);
            });
    }

    // --- Event Listener for Port Input Change ---
    portInput.addEventListener('input', () => {
        if (!currentTabId) return; // Need tab context
        const newPort = portInput.value;
        serverConfigLoaded = false; setServerTogglesDisabled(true); updateServerInfoDisplay(null); // Mark stale

        if (validatePortInput(newPort)) {
            // ** Send Tab ID **
            browser.runtime.sendMessage({ action: "updateSetting", key: "port", value: parseInt(newPort, 10), tabId: currentTabId })
                .then(() => {
                     updateStatus(`Port for this tab set to ${newPort}. Reloading server info...`, 'info');
                     // Port change for a tab *might* mean connecting to a different server, so reload info
                     loadServerConfig();
                })
                .catch(error => { updateStatus(`Error saving port: ${error.message}`, 'error'); updateServerInfoDisplay(null); });
        } else { updateStatus('Invalid port number. Cannot load server info.', 'error'); updateServerInfoDisplay(null); }
    });

    // --- Event Listener for Activation Toggle Change ---
    activationToggle.addEventListener('change', () => {
        // Activation is global, no tabId needed here
        const newState = activationToggle.checked;
        browser.runtime.sendMessage({ action: "updateSetting", key: "isActivated", value: newState })
        .then(() => { updateStatus(`Auto-Capture ${newState ? 'Enabled' : 'Disabled'}`, 'info'); })
        .catch(error => { updateStatus(`Error saving toggle state: ${error.message}`, 'error'); });
    });

    // --- Function to handle server config toggle changes ---
    function handleServerConfigChange(key, value) {
        if (!currentTabId) return; // Need context for messaging
        if (!serverConfigLoaded) { updateStatus("Cannot save: server info not loaded.", "error"); return; }
        updateStatus('Saving server configuration...', 'info'); setServerTogglesDisabled(true);
        // ** Send Tab ID (although server uses it mainly for port, good practice)**
        // Key is already lowercase (auto_run_python/shell)
        browser.runtime.sendMessage({ action: "updateServerConfig", key: key, value: value, tabId: currentTabId })
        .then(response => {
             if (response?.success) {
                 updateStatus(response.message || 'Server config updated.', 'success', false); // No restart warning needed
                 // Re-sync UI just in case? Or trust the update worked. Fetching again might be overkill.
             } else { updateStatus(`Failed to save server config: ${response?.message || response?.error || 'Unknown error'}`, 'error'); }
        })
        .catch(error => { updateStatus(`Error contacting background to save config: ${error.message}`, 'error'); })
        .finally(() => { if (serverConfigLoaded) { setServerTogglesDisabled(false); } });
    }

    // --- Event Listeners for Server Config Toggles ---
    enablePythonToggle.addEventListener('change', () => { handleServerConfigChange('auto_run_python', enablePythonToggle.checked); });
    enableShellToggle.addEventListener('change', () => { handleServerConfigChange('auto_run_shell', enableShellToggle.checked); });

    // --- Event Listener for Test Connection Button ---
    testConnectionBtn.addEventListener('click', async () => {
        if (!currentTabId) return; // Need tab context
        testConnectionBtn.disabled = true; updateStatus('Testing connection...', 'info'); updateServerInfoDisplay(null); // Show loading

        try {
            // ** Send Tab ID **
            const response = await browser.runtime.sendMessage({ action: "testConnection", tabId: currentTabId });
            if (response?.success && response.data) {
                 const serverStatus = response.data;
                 let statusMsg = `Connection successful!\n`;
                 // Use the port we *attempted* to connect to for display consistency
                 statusMsg += `Using Port: ${portInput.value || '(default)'}\n`;
                 // Display RUNNING state from the server
                 statusMsg += `Server CWD: ${serverStatus?.working_directory || 'N/A'}\n`; // Show CWD here too
                 statusMsg += `Py Auto-Run: ${serverStatus?.auto_run_python ?? '?'}\n`;
                 statusMsg += `Sh Auto-Run: ${serverStatus?.auto_run_shell ?? '?'}\n`;
                 statusMsg += `Git Repo: ${serverStatus?.is_git_repo ?? '?'}`;
                 updateStatus(statusMsg, 'success');
                 // Update all info displays and sync toggles
                 updateServerInfoDisplay(serverStatus);
                 enablePythonToggle.checked = serverStatus?.auto_run_python === true;
                 enableShellToggle.checked = serverStatus?.auto_run_shell === true;
                 serverConfigLoaded = true; setServerTogglesDisabled(false);
            } else {
                 let errorMsg = 'Connection failed.';
                 if (response?.error) { errorMsg += `\nReason: ${response.error}`; }
                 else { errorMsg += ` Using Port: ${portInput.value || '(default)'}. Check server status.`; }
                 updateStatus(errorMsg, 'error'); updateServerInfoDisplay(null);
                 serverConfigLoaded = false; setServerTogglesDisabled(true);
            }
        } catch (error) {
            updateStatus(`Error testing connection: ${error.message}`, 'error');
            updateServerInfoDisplay(null); serverConfigLoaded = false; setServerTogglesDisabled(true);
        } finally { testConnectionBtn.disabled = false; }
    });

     // --- Listener for status updates from background ---
     browser.runtime.onMessage.addListener((message, sender) => { /* ... unchanged ... */ if (message.action === "updatePopupStatus") { updateStatus(message.message, message.type || 'info'); return Promise.resolve(); } return false; });
});
// @@FILENAME@@ extension/popup.js