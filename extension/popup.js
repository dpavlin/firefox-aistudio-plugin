// @@FILENAME@@ extension/popup.js
document.addEventListener('DOMContentLoaded', () => {
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

    function updateStatus(message, type = 'info', showRestartMsg = false) {
        if (!statusDisplay) return;
        let displayMessage = (typeof message === 'string' || message instanceof String) ? message : JSON.stringify(message);
        statusDisplay.textContent = displayMessage;
        statusDisplay.className = '';
        statusDisplay.classList.add(type);
        // Only show restart warning if explicitly told to (e.g., for port changes)
        if (restartWarning) {
            restartWarning.style.display = showRestartMsg ? 'block' : 'none';
        }
        console.log(`Popup status (${type}):`, displayMessage, `Restart Msg: ${showRestartMsg}`);
    }

    function setServerTogglesDisabled(disabled) {
        enablePythonToggle.disabled = disabled;
        enableShellToggle.disabled = disabled;
    }
    setServerTogglesDisabled(true);

    function updateServerInfoDisplay(serverStatus) {
        const naText = 'N/A';
        const cwdPath = serverStatus?.working_directory;
        const saveDir = serverStatus?.save_directory;
        const logDir = serverStatus?.log_directory;
        const gitStatus = serverStatus?.is_git_repo;

        if (serverCwdDisplay) { serverCwdDisplay.textContent = cwdPath || naText; serverCwdDisplay.title = cwdPath || 'Could not load CWD'; }
        if (serverSaveDirDisplay) { serverSaveDirDisplay.textContent = saveDir ? `./${saveDir}` : naText; serverSaveDirDisplay.title = saveDir ? `./${saveDir}` : 'Could not load Save Dir'; }
        if (serverLogDirDisplay) { serverLogDirDisplay.textContent = logDir ? `./${logDir}` : naText; serverLogDirDisplay.title = logDir ? `./${logDir}` : 'Could not load Log Dir'; }
        if (serverGitStatusDisplay) {
             if (gitStatus === true) { serverGitStatusDisplay.textContent = 'Enabled'; serverGitStatusDisplay.className = 'info-text status-true'; serverGitStatusDisplay.title = 'Git repo detected.'; }
             else if (gitStatus === false) { serverGitStatusDisplay.textContent = 'Disabled'; serverGitStatusDisplay.className = 'info-text status-false'; serverGitStatusDisplay.title = 'Not a Git repo.'; }
             else { serverGitStatusDisplay.textContent = naText; serverGitStatusDisplay.className = 'info-text'; serverGitStatusDisplay.title = 'Could not determine Git status.'; }
        }
    }
    updateServerInfoDisplay(null);

    browser.runtime.sendMessage({ action: "getSettings" })
        .then(settings => {
            let portIsValid = false;
            if (settings?.port !== undefined) { portInput.value = settings.port; portIsValid = validatePortInput(settings.port); }
            else { portInput.value = ''; portInput.classList.add('invalid'); }
            activationToggle.checked = settings?.isActivated === true;

            if (portIsValid) { loadServerConfig(); }
            else { updateStatus('Invalid port - cannot load server info.', 'warning'); updateServerInfoDisplay(null); setServerTogglesDisabled(true); }
        })
        .catch(error => {
            updateStatus(`Error loading extension settings: ${error.message}`, 'error');
            portInput.classList.add('invalid'); portInput.value = ''; activationToggle.checked = false;
            setServerTogglesDisabled(true); updateServerInfoDisplay(null);
        });

    function loadServerConfig() {
        updateStatus('Loading server information...', 'info');
        setServerTogglesDisabled(true); updateServerInfoDisplay(null);
        browser.runtime.sendMessage({ action: "getServerConfig" })
            .then(response => {
                 if (response?.success && response.data) {
                     const serverStatus = response.data;
                     // Use lowercase keys here
                     enablePythonToggle.checked = serverStatus.auto_run_python === true;
                     enableShellToggle.checked = serverStatus.auto_run_shell === true;
                     updateServerInfoDisplay(serverStatus);
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

    function validatePortInput(portValue) { /* ... unchanged ... */ const port = parseInt(portValue, 10); const isValid = !isNaN(port) && port >= 1025 && port <= 65535; if (isValid) { portInput.classList.remove('invalid'); } else { portInput.classList.add('invalid'); } return isValid; }

    portInput.addEventListener('input', () => {
        const newPort = portInput.value;
        serverConfigLoaded = false; setServerTogglesDisabled(true); updateServerInfoDisplay(null);
        if (validatePortInput(newPort)) {
            browser.runtime.sendMessage({ action: "updateSetting", key: "port", value: parseInt(newPort, 10) })
                .then(() => { updateStatus(`Port set to ${newPort}. Reloading server info...`, 'info'); loadServerConfig(); })
                .catch(error => { updateStatus(`Error saving port: ${error.message}`, 'error'); updateServerInfoDisplay(null); });
        } else { updateStatus('Invalid port number. Cannot load server info.', 'error'); updateServerInfoDisplay(null); }
    });

    activationToggle.addEventListener('change', () => { /* ... unchanged ... */ const newState = activationToggle.checked; browser.runtime.sendMessage({ action: "updateSetting", key: "isActivated", value: newState }).then(() => { updateStatus(`Auto-Capture ${newState ? 'Enabled' : 'Disabled'}`, 'info'); }).catch(error => { updateStatus(`Error saving toggle state: ${error.message}`, 'error'); }); });

    function handleServerConfigChange(key, value) {
        if (!serverConfigLoaded) { updateStatus("Cannot save server config - state may be out of sync.", "error"); return; }
        updateStatus('Saving server configuration...', 'info'); setServerTogglesDisabled(true);
        browser.runtime.sendMessage({ action: "updateServerConfig", key: key, value: value }) // key is already lowercase
        .then(response => {
             if (response?.success) {
                 // *** Don't show restart warning for auto-run toggles ***
                 updateStatus(response.message || 'Server config updated.', 'success', false); // showRestartMsg = false
             } else { updateStatus(`Failed to save server config: ${response?.message || response?.error || 'Unknown error'}`, 'error'); }
        })
        .catch(error => { updateStatus(`Error contacting background to save config: ${error.message}`, 'error'); })
        .finally(() => { if (serverConfigLoaded) { setServerTogglesDisabled(false); } });
    }

    // *** Send lowercase keys ***
    enablePythonToggle.addEventListener('change', () => { handleServerConfigChange('auto_run_python', enablePythonToggle.checked); });
    enableShellToggle.addEventListener('change', () => { handleServerConfigChange('auto_run_shell', enableShellToggle.checked); });

    testConnectionBtn.addEventListener('click', async () => { /* ... mostly unchanged, ensure reading lowercase keys ... */
        testConnectionBtn.disabled = true; updateStatus('Testing connection...', 'info'); updateServerInfoDisplay(null);
        try {
            const response = await browser.runtime.sendMessage({ action: "testConnection" });
            if (response?.success && response.data) {
                 const serverStatus = response.data;
                 let statusMsg = `Connection successful!\n`;
                 statusMsg += `Server running on port ${serverStatus?.port || '?'}.\n`;
                 // *** Read lowercase keys ***
                 statusMsg += `Python Auto-Run: ${serverStatus?.auto_run_python ?? '?'}\n`;
                 statusMsg += `Shell Auto-Run: ${serverStatus?.auto_run_shell ?? '?'}\n`;
                 statusMsg += `(This reflects the RUNNING server state)`;
                 updateStatus(statusMsg, 'success');
                 updateServerInfoDisplay(serverStatus);
                 // *** Sync toggles with lowercase keys ***
                 enablePythonToggle.checked = serverStatus?.auto_run_python === true;
                 enableShellToggle.checked = serverStatus?.auto_run_shell === true;
                 serverConfigLoaded = true; setServerTogglesDisabled(false);
            } else {
                 let errorMsg = 'Connection failed.';
                 if (response?.error) { errorMsg += `\nReason: ${response.error}`; }
                 else if (response?.message) { errorMsg = `Server Error: ${response.message}`; }
                 else if (response?.data?.error) { errorMsg = `Server Error: ${response.data.error}`; }
                 else { errorMsg += ' Check server status.'; }
                 updateStatus(errorMsg, 'error'); updateServerInfoDisplay(null);
                 serverConfigLoaded = false; setServerTogglesDisabled(true);
            }
        } catch (error) {
            updateStatus(`Error testing connection: ${error.message}`, 'error');
            updateServerInfoDisplay(null); serverConfigLoaded = false; setServerTogglesDisabled(true);
        } finally { testConnectionBtn.disabled = false; }
    });

     browser.runtime.onMessage.addListener((message, sender) => { /* ... unchanged ... */ if (message.action === "updatePopupStatus") { updateStatus(message.message, message.type || 'info'); return Promise.resolve(); } return false; });
});
// @@FILENAME@@ extension/popup.js