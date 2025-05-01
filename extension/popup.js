document.addEventListener('DOMContentLoaded', () => {
    const serverPortInput = document.getElementById('serverPort');
    const activationToggle = document.getElementById('activationToggle');
    const refreshStatusBtn = document.getElementById('refreshStatusBtn');
    const saveConfigBtn = document.getElementById('saveConfigBtn');
    const lastActionStatus = document.getElementById('last-action-status');

    // --- Status Display Elements ---
    const serverLiveStatus = document.getElementById('serverLiveStatus');
    const serverRunningPort = document.getElementById('serverRunningPort');
    const serverDetailsSection = document.getElementById('server-details');
    const serverCwd = document.getElementById('serverCwd');
    const serverGitStatus = document.getElementById('serverGitStatus');
    const serverConfigFileStatus = document.getElementById('serverConfigFileStatus');
    const currentPythonRun = document.getElementById('currentPythonRun');
    const currentShellRun = document.getElementById('currentShellRun');

    // --- Config Editable Elements ---
    const enablePythonToggle = document.getElementById('enablePythonToggle');
    const enableShellToggle = document.getElementById('enableShellToggle');

    let currentServerConfig = {}; // Store last known server config

    // --- Utility Functions ---
    function updateStatusDisplay(message, type = 'info') {
        lastActionStatus.textContent = message;
        lastActionStatus.className = type; // error, success, warning, info
    }

    function updateServerDetailsUI(data) {
        if (data && data.status === 'running') {
            serverLiveStatus.textContent = 'Running';
            serverLiveStatus.className = 'value success';
            serverRunningPort.textContent = data.port || 'N/A';
            serverCwd.textContent = data.working_directory || 'N/A';
            serverGitStatus.textContent = data.is_git_repo ? 'Yes' : 'No';
            serverConfigFileStatus.textContent = data.config_file_exists ? 'Found' : 'Not Found';
            currentPythonRun.textContent = data.auto_run_python ? 'ENABLED' : 'DISABLED';
            currentShellRun.textContent = data.auto_run_shell ? 'ENABLED' : 'DISABLED';

            // Set the editable toggles based on current server state initially
            // Only do this if we don't have pending changes maybe? Or always sync? Let's sync.
            enablePythonToggle.checked = data.auto_run_python;
            enableShellToggle.checked = data.auto_run_shell;

            serverDetailsSection.style.display = 'block';
            saveConfigBtn.disabled = false; // Enable saving if connected
        } else {
            serverLiveStatus.textContent = 'Offline / Error';
            serverLiveStatus.className = 'value error';
            serverRunningPort.textContent = 'N/A';
            serverCwd.textContent = 'N/A';
            serverGitStatus.textContent = 'N/A';
             serverConfigFileStatus.textContent = 'N/A';
            currentPythonRun.textContent = 'N/A';
            currentShellRun.textContent = 'N/A';
            serverDetailsSection.style.display = 'none';
            saveConfigBtn.disabled = true;
        }
    }

    // --- Fetch Server Status ---
    async function fetchServerStatus() {
        updateStatusDisplay('Checking server status...', 'info');
        const port = serverPortInput.value;
        if (!port || port < 1025 || port > 65535) {
            updateStatusDisplay('Invalid port number.', 'error');
            updateServerDetailsUI(null); // Clear details
            return;
        }
        const url = `http://127.0.0.1:${port}/status`;

        try {
            const response = await fetch(url, { method: 'GET', cache: 'no-cache' });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            currentServerConfig = data; // Store the latest successful status
            updateServerDetailsUI(data);
            updateStatusDisplay(`Status refreshed successfully at ${new Date().toLocaleTimeString()}`, 'success');

        } catch (error) {
            console.error('Error fetching server status:', error);
            updateStatusDisplay(`Failed to connect to server on port ${port}. Is it running?\nError: ${error.message}`, 'error');
            currentServerConfig = {}; // Clear stored config on error
            updateServerDetailsUI(null); // Clear details UI
        }
    }

    // --- Save Configuration ---
    async function saveConfiguration() {
        const port = serverPortInput.value;
        const desiredPythonRun = enablePythonToggle.checked;
        const desiredShellRun = enableShellToggle.checked;

        updateStatusDisplay('Saving configuration...', 'info');
        saveConfigBtn.disabled = true; // Disable while saving

        const configPayload = {
            auto_run_python: desiredPythonRun,
            auto_run_shell: desiredShellRun
            // Not sending port, as decided
        };

        const url = `http://127.0.0.1:${port}/update_config`;

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(configPayload)
            });
            const result = await response.json(); // Expect JSON response from server

            if (!response.ok || result.status !== 'success') {
                 throw new Error(result.message || `HTTP error! status: ${response.status}`);
            }

            console.log('Config save response:', result);
            updateStatusDisplay(`${result.message}`, 'warning'); // Use warning to emphasize restart needed

            // Optionally refresh status display immediately after save
            // Note: The displayed *current* status won't change until server restarts
            // fetchServerStatus();

        } catch (error) {
            console.error('Error saving configuration:', error);
            updateStatusDisplay(`Error saving configuration: ${error.message}`, 'error');
        } finally {
            // Re-enable button unless server became unreachable during save attempt
             if (serverLiveStatus.textContent === 'Running') {
                 saveConfigBtn.disabled = false;
             }
        }
    }


    // --- Load Settings and Initial Status ---
    chrome.storage.local.get(['serverPort', 'isActivated'], (result) => {
        serverPortInput.value = result.serverPort || '5000'; // Default to 5000 if not set
        activationToggle.checked = !!result.isActivated;
        fetchServerStatus(); // Fetch status on popup open
    });

    // --- Event Listeners ---
    serverPortInput.addEventListener('change', () => {
        const port = serverPortInput.value;
        if (port && port >= 1025 && port <= 65535) {
            chrome.storage.local.set({ serverPort: port });
            serverPortInput.classList.remove('invalid');
            // Fetch status immediately when port changes
            fetchServerStatus();
        } else {
            serverPortInput.classList.add('invalid');
            updateStatusDisplay('Invalid port number (must be 1025-65535).', 'error');
             updateServerDetailsUI(null); // Clear details if port invalid
        }
    });

    activationToggle.addEventListener('change', () => {
        chrome.storage.local.set({ isActivated: activationToggle.checked });
        updateStatusDisplay(`Auto-Capture ${activationToggle.checked ? 'Enabled' : 'Disabled'}.`, 'info');
    });

    refreshStatusBtn.addEventListener('click', fetchServerStatus);

    saveConfigBtn.addEventListener('click', saveConfiguration);

});