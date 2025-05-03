// @@FILENAME@@ extension/popup.js
document.addEventListener('DOMContentLoaded', async () => {
    const serverPortInput = document.getElementById('serverPort');
    const testConnectionBtn = document.getElementById('testConnectionBtn');
    const activationToggle = document.getElementById('activationToggle');
    const lastResponsePre = document.getElementById('last-response');

    // Status display elements
    const serverCwdDisplay = document.getElementById('serverCwdDisplay');
    const serverSaveDirDisplay = document.getElementById('serverSaveDirDisplay');
    // const serverLogDirDisplay = document.getElementById('serverLogDirDisplay'); // REMOVED
    const serverGitStatusDisplay = document.getElementById('serverGitStatusDisplay');
    const serverPyRunStatus = document.getElementById('serverPyRunStatus'); // Added for read-only status
    const serverShRunStatus = document.getElementById('serverShRunStatus'); // Added for read-only status


    // REMOVED Server config elements
    // const serverEnablePython = document.getElementById('serverEnablePython');
    // const serverEnableShell = document.getElementById('serverEnableShell');
    const restartWarning = document.getElementById('restartWarning');

    const DEFAULT_PORT = 5000; // Keep consistent with background
    let currentTabId = null; // Store the current tab's ID

    function displayStatus(message, type = 'info') {
        lastResponsePre.textContent = message;
        lastResponsePre.className = ''; // Clear previous classes
        lastResponsePre.classList.add(type);
        console.log(`Popup Status [${type}]: ${message}`);
    }

    function updateServerInfoDisplay(details) {
        const cwd = details.working_directory || 'N/A';
        serverCwdDisplay.textContent = cwd;
        serverCwdDisplay.title = details.working_directory || 'Server Current Working Directory';

        serverSaveDirDisplay.textContent = details.save_directory || 'N/A';
        serverSaveDirDisplay.title = `Fallback save directory (relative to ${cwd})`;

        // serverLogDirDisplay.textContent = details.log_directory || 'N/A'; // REMOVED
        // serverLogDirDisplay.title = `Log directory (relative to ${cwd})`; // REMOVED

        const isGit = details.is_git_repo === true; // Ensure boolean check
        serverGitStatusDisplay.textContent = isGit ? 'Yes' : 'No';
        serverGitStatusDisplay.title = isGit ? 'CWD is a Git repository' : 'CWD is not a Git repository';
        serverGitStatusDisplay.classList.toggle('status-true', isGit);
        serverGitStatusDisplay.classList.toggle('status-false', !isGit);

        // Update read-only status spans for auto-run (based on server flags)
        const pyRun = details.auto_run_python === true;
        serverPyRunStatus.textContent = pyRun ? 'Enabled' : 'Disabled';
        serverPyRunStatus.title = pyRun ? 'Enabled (via server flag --enable-python-run)' : 'Disabled';
        serverPyRunStatus.classList.toggle('status-true', pyRun);
        serverPyRunStatus.classList.toggle('status-false', !pyRun);

        const shRun = details.auto_run_shell === true;
        serverShRunStatus.textContent = shRun ? 'Enabled' : 'Disabled';
        serverShRunStatus.title = shRun ? 'Enabled (via server flag --shell)' : 'Disabled';
        serverShRunStatus.classList.toggle('status-true', shRun); // Maybe use warning class instead?
        serverShRunStatus.classList.toggle('status-false', !shRun);
        if (shRun) serverShRunStatus.classList.add('status-false'); // Use red style for dangerous enabled shell

        // REMOVED logic updating toggle controls
        // serverEnablePython.checked = details.auto_run_python || false;
        // serverEnableShell.checked = details.auto_run_shell || false;
        // serverEnablePython.disabled = false;
        // serverEnableShell.disabled = false;
    }

     // --- Helper to get current tab ID ---
     async function getCurrentTabId() {
         try {
             let tabs = await browser.tabs.query({ active: true, currentWindow: true });
             if (tabs && tabs.length > 0 && tabs[0].id) {
                 return tabs[0].id;
             }
         } catch (error) {
             console.error("Popup: Error querying for active tab:", error);
         }
         console.error("Popup: Could not get current tab ID.");
         return null; // Indicate failure
     }


    // --- Initialization ---

    displayStatus('Loading settings...');

    // 0. Get current tab ID first
    currentTabId = await getCurrentTabId();
    if (currentTabId === null) {
         displayStatus('Error: Could not identify the current tab. Port settings might not work correctly.', 'error');
         // Proceed with defaults, but things might be broken
    } else {
        console.log(`Popup: Initializing for tab ID: ${currentTabId}`);
    }


    // 1. Fetch and set initial port value for THIS tab
    try {
        // **Send tabId with the request**
        const portResponse = await browser.runtime.sendMessage({ action: "getPort", tabId: currentTabId });
        const initialPort = portResponse?.port || DEFAULT_PORT;
        serverPortInput.value = initialPort;
        console.log(`Popup: Initial port for tab ${currentTabId} set to ${initialPort}`);
    } catch (error) {
        console.error(`Popup: Error getting initial port for tab ${currentTabId}:`, error);
        serverPortInput.value = DEFAULT_PORT; // Fallback
        displayStatus(`Error loading port for this tab: ${error.message}. Using default ${DEFAULT_PORT}.`, 'error');
    }

    // 2. Fetch and set initial GLOBAL activation state (remains global)
    try {
        const activationResponse = await browser.runtime.sendMessage({ action: "getActivationState" });
        activationToggle.checked = activationResponse?.isActive === true;
        console.log(`Popup: Initial global activation state: ${activationToggle.checked}`);
    } catch (error) {
        console.error("Popup: Error getting initial activation state:", error);
        activationToggle.checked = false; // Default to inactive on error
        displayStatus(`Error loading activation state: ${error.message}.`, 'warning');
    }

    // 3. Attempt initial connection test (using the potentially tab-specific port now loaded)
     if (currentTabId !== null) { // Only test if we have a tab ID
        testConnectionBtn.click(); // Trigger test on load
     } else {
         displayStatus("Cannot perform initial connection test without Tab ID.", "warning");
     }

    // --- Event Listeners ---

    // Validate and Store Port on Input
    serverPortInput.addEventListener('input', () => {
        if (currentTabId === null) {
            displayStatus('Cannot save port setting - current tab ID unknown.', 'error');
            return;
        }
        const portValue = serverPortInput.value.trim();
        const portNumber = parseInt(portValue, 10);
        let isValid = false;

        if (portValue === '' || (!isNaN(portNumber) && portNumber >= 1025 && portNumber <= 65535)) {
            serverPortInput.classList.remove('invalid');
            isValid = true;
            if (portValue !== '') {
                 // **Send tabId with the store request**
                 browser.runtime.sendMessage({ action: "storePort", tabId: currentTabId, port: portNumber })
                     .then(response => {
                         if (!response?.success) console.error(`Popup: Failed to store port for tab ${currentTabId}.`);
                         else console.log(`Popup: Port ${portNumber} for tab ${currentTabId} sent to background.`);
                     })
                     .catch(err => console.error("Popup: Error sending storePort message:", err));
            }
        } else {
            serverPortInput.classList.add('invalid');
        }
        // Show restart warning if port differs from default (simplistic check)
        restartWarning.style.display = (portValue !== '' && portNumber !== DEFAULT_PORT) ? 'block' : 'none';
    });

    // Test Connection Button
    testConnectionBtn.addEventListener('click', async () => {
        // Tests the *currently entered* port, not necessarily the stored one for the tab
        const currentInputPort = parseInt(serverPortInput.value, 10);
        if (isNaN(currentInputPort) || currentInputPort < 1025 || currentInputPort > 65535) {
            displayStatus('Invalid port number in field. Enter 1025-65535.', 'error');
            serverPortInput.classList.add('invalid');
            return;
        }
        serverPortInput.classList.remove('invalid');

        displayStatus(`Testing connection to port ${currentInputPort}...`, 'info');
        testConnectionBtn.disabled = true;

        try {
            // Send the current input value to the background script for testing
            const response = await browser.runtime.sendMessage({ action: "testConnection", port: currentInputPort });

            if (response && response.success) {
                displayStatus('Connection successful! Server status loaded.', 'success');
                updateServerInfoDisplay(response.details);
                 // Update the input field ONLY if the server reports a DIFFERENT port than tested
                 // This indicates the user might be testing one port while the server for *this tab* runs elsewhere
                const serverReportedPort = response.details.port;
                 if (serverReportedPort && serverReportedPort !== currentInputPort) {
                     // serverPortInput.value = serverReportedPort; // Decide if you want this behavior
                     console.warn(`Popup: Test connection to ${currentInputPort} successful, but server reported running on ${serverReportedPort}.`);
                 } else {
                     console.log(`Popup: Test connection OK to port ${currentInputPort}. Server details:`, response.details);
                 }
            } else {
                 let errorMsg = response?.details?.message || `Connection failed to port ${currentInputPort}. Is a server running there?`;
                 displayStatus(errorMsg, 'error');
                 updateServerInfoDisplay({}); // Clear fields on failure
                 console.error(`Popup: Test connection to ${currentInputPort} failed:`, response?.details);
            }
        } catch (error) {
            displayStatus(`Error testing connection: ${error.message}`, 'error');
            updateServerInfoDisplay({});
            console.error("Popup: Error sending testConnection message:", error);
        } finally {
            testConnectionBtn.disabled = false;
        }
    });

    // Activation Toggle listener remains the same
    activationToggle.addEventListener('change', () => {
        const isActive = activationToggle.checked;
        browser.runtime.sendMessage({ action: "storeActivationState", isActive: isActive })
            .then(response => {
                if (!response?.success) console.error("Popup: Failed to store activation state.");
                else console.log(`Popup: Global activation state stored: ${isActive}`);
            })
            .catch(err => console.error("Popup: Error sending storeActivationState message:", err));
            displayStatus(`Extension ${isActive ? 'activated' : 'deactivated'} globally.`, 'info');
    });

    // REMOVED Event listeners for server config toggles
    // serverEnablePython.addEventListener(...)
    // serverEnableShell.addEventListener(...)

});
