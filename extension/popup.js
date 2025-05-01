document.addEventListener('DOMContentLoaded', () => {
    // Use setTimeout to ensure elements are definitely ready
    setTimeout(() => {
        const serverPortInput = document.getElementById('serverPort');
        const activationToggle = document.getElementById('activationToggle');
        const refreshStatusBtn = document.getElementById('refreshStatusBtn'); // Moved lookup inside setTimeout
        const saveConfigBtn = document.getElementById('saveConfigBtn');
        const lastActionStatus = document.getElementById('last-action-status'); // Moved lookup inside setTimeout

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

        // Check if critical elements were found before proceeding
        if (!refreshStatusBtn || !lastActionStatus || !serverPortInput || !activationToggle || !saveConfigBtn || !serverLiveStatus || !serverRunningPort || !serverDetailsSection || !serverCwd || !serverGitStatus || !serverConfigFileStatus || !currentPythonRun || !currentShellRun || !enablePythonToggle || !enableShellToggle ) {
             console.error("Popup DOM elements not found! Check IDs in popup.html and popup.js.");
             const statusArea = document.getElementById('last-action-status'); // Try getting it again
             if (statusArea) {
                  statusArea.textContent = "Error initializing popup UI. Check console.";
                  statusArea.className = 'error';
             }
             return; // Stop execution if critical elements are missing
        }

        let currentServerConfig = {}; // Store last known server config

        // --- Utility Functions ---
        function updateStatusDisplay(message, type = 'info') {
             if (lastActionStatus) {
                 lastActionStatus.textContent = message;
                 lastActionStatus.className = type;
             } else {
                 console.error("lastActionStatus element is null, cannot update status:", message);
             }
        }

        function updateServerDetailsUI(data) {
            if (!serverLiveStatus || !serverRunningPort || !serverCwd || !serverGitStatus || !serverConfigFileStatus || !currentPythonRun || !currentShellRun || !serverDetailsSection || !saveConfigBtn || !enablePythonToggle || !enableShellToggle) {
                console.error("One or more UI elements for server details are missing.");
                return;
            }

            if (data && data.status === 'running') {
                serverLiveStatus.textContent = 'Running';
                serverLiveStatus.className = 'value success';
                serverRunningPort.textContent = data.port || 'N/A';
                serverCwd.textContent = data.working_directory || 'N/A';
                serverGitStatus.textContent = data.is_git_repo ? 'Yes' : 'No';
                serverConfigFileStatus.textContent = data.config_file_exists ? 'Found' : 'Not Found';
                currentPythonRun.textContent = data.auto_run_python ? 'ENABLED' : 'DISABLED';
                currentShellRun.textContent = data.auto_run_shell ? 'ENABLED' : 'DISABLED';
                // Sync editable toggles
                enablePythonToggle.checked = data.auto_run_python;
                enableShellToggle.checked = data.auto_run_shell;
                serverDetailsSection.style.display = 'block';
                saveConfigBtn.disabled = false; // Enable saving if connected
                // Re-enable config toggles after successful fetch
                enablePythonToggle.disabled = false;
                enableShellToggle.disabled = false;
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
                // Disable config toggles if offline
                enablePythonToggle.disabled = true;
                enableShellToggle.disabled = true;
            }
        }

        // --- Fetch Server Status ---
        async function fetchServerStatus() {
            updateStatusDisplay('Checking server status...', 'info');
            if(saveConfigBtn) saveConfigBtn.disabled = true;
            if(enablePythonToggle) enablePythonToggle.disabled = true;
            if(enableShellToggle) enableShellToggle.disabled = true;

            const port = serverPortInput.value;
            if (!port || port < 1025 || port > 65535) {
                updateStatusDisplay('Invalid port number.', 'error');
                updateServerDetailsUI(null);
                return;
            }
            const url = `http://127.0.0.1:${port}/status`;

            try {
                const response = await fetch(url, { method: 'GET', cache: 'no-cache', signal: AbortSignal.timeout(3000) });
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                const data = await response.json();
                currentServerConfig = data;
                updateServerDetailsUI(data);
                updateStatusDisplay(`Status refreshed successfully at ${new Date().toLocaleTimeString()}`, 'success');
                 // Ensure toggles are enabled after success (handled in updateServerDetailsUI)

            } catch (error) {
                console.error('Error fetching server status:', error);
                let errorMsg = `Failed to connect on port ${port}. Server running?\nError: ${error.message}`;
                if (error.name === 'AbortError') { errorMsg = `Connection to server on port ${port} timed out.`; }
                updateStatusDisplay(errorMsg, 'error');
                currentServerConfig = {};
                updateServerDetailsUI(null); // Clear details UI and disable toggles
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
            };
            const url = `http://127.0.0.1:${port}/update_config`;

            try {
                const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(configPayload), signal: AbortSignal.timeout(5000) });
                const result = await response.json();
                if (!response.ok || result.status !== 'success') { throw new Error(result.message || `HTTP error! status: ${response.status}`); }
                console.log('Config save response:', result);
                updateStatusDisplay(`${result.message}`, 'warning'); // Remind user to restart
            } catch (error) {
                console.error('Error saving configuration:', error);
                let errorMsg = `Error saving configuration: ${error.message}`;
                if (error.name === 'AbortError') { errorMsg = `Save request timed out for port ${port}.`; }
                updateStatusDisplay(errorMsg, 'error');
            } finally {
                 // Re-enable button only if server was still considered running before save attempt
                 if (serverLiveStatus && serverLiveStatus.textContent === 'Running') {
                     saveConfigBtn.disabled = false;
                 }
            }
        }

        // --- Handle Port Change ---
         function handlePortChange() {
             const port = serverPortInput.value;
             if (port && port >= 1025 && port <= 65535) {
                 chrome.storage.local.set({ serverPort: port }, () => {
                     console.log(`Port ${port} saved to storage.`);
                     fetchServerStatus(); // Fetch status immediately after saving valid port
                 });
                 serverPortInput.classList.remove('invalid');
             } else {
                 serverPortInput.classList.add('invalid');
                 updateStatusDisplay('Invalid port number (must be 1025-65535).', 'error');
                 updateServerDetailsUI(null);
             }
         }

        // --- Handle Activation Toggle ---
        function handleActivationToggle() {
             chrome.storage.local.set({ isActivated: activationToggle.checked }, () => {
                 updateStatusDisplay(`Auto-Capture ${activationToggle.checked ? 'Enabled' : 'Disabled'}.`, 'info');
             });
         }

        // --- Load Settings and Initial Status ---
        chrome.storage.local.get(['serverPort', 'isActivated'], (result) => {
             serverPortInput.value = result.serverPort || '5000';
             activationToggle.checked = !!result.isActivated;
             fetchServerStatus(); // Initial fetch
        });

        // --- Attach Event Listeners ---
        serverPortInput.addEventListener('change', handlePortChange);
        activationToggle.addEventListener('change', handleActivationToggle);
        refreshStatusBtn.addEventListener('click', fetchServerStatus);
        saveConfigBtn.addEventListener('click', saveConfiguration);

    }, 0); // End of setTimeout(..., 0)
});