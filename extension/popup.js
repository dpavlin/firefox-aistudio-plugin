// @@FILENAME@@ extension/popup.js
document.addEventListener('DOMContentLoaded', async () => {
    // References to controls and status display
    const serverPortInput = document.getElementById('serverPort');
    const testConnectionBtn = document.getElementById('testConnectionBtn');
    const activationToggle = document.getElementById('activationToggle');
    const lastResponsePre = document.getElementById('last-response');
    const restartWarning = document.getElementById('restartWarning');

    // Server Info display elements
    const serverCwdDisplay = document.getElementById('serverCwdDisplay');
    const serverSaveDirDisplay = document.getElementById('serverSaveDirDisplay');
    const serverGitStatusDisplay = document.getElementById('serverGitStatusDisplay');
    const serverPyRunStatus = document.getElementById('serverPyRunStatus');
    const serverShRunStatus = document.getElementById('serverShRunStatus');

    // REMOVED Output elements
    // const outputContainer = document.getElementById('output-container');
    // const outputTimestamp = document.getElementById('output-timestamp');
    // const syntaxStdoutPre = document.getElementById('syntax-stdout');
    // const syntaxStderrPre = document.getElementById('syntax-stderr');
    // const runStdoutPre = document.getElementById('run-stdout');
    // const runStderrPre = document.getElementById('run-stderr');
    // const noOutputSpan = '<span class="no-output">(N/A)</span>';

    const DEFAULT_PORT = 5000;
    let currentTabId = null;

    // Status display function
    function displayStatus(message, type = 'info') {
        lastResponsePre.textContent = message;
        lastResponsePre.className = ''; // Clear previous classes
        lastResponsePre.classList.add(type);
        console.log(`Popup Status [${type}]: ${message}`);
    }

    // Update server info display (remains mostly the same)
    function updateServerInfoDisplay(details) {
        const cwd = details.working_directory || 'N/A';
        serverCwdDisplay.textContent = cwd;
        serverCwdDisplay.title = details.working_directory || 'Server Current Working Directory';
        serverSaveDirDisplay.textContent = details.save_directory || 'N/A';
        serverSaveDirDisplay.title = `Fallback save directory (relative to ${cwd})`;

        const isGit = details.is_git_repo === true;
        serverGitStatusDisplay.textContent = isGit ? 'Yes' : 'No';
        serverGitStatusDisplay.title = isGit ? 'CWD is a Git repository' : 'CWD is not a Git repository';
        serverGitStatusDisplay.classList.toggle('status-true', isGit);
        serverGitStatusDisplay.classList.toggle('status-false', !isGit);

        const pyRun = details.auto_run_python === true;
        serverPyRunStatus.textContent = pyRun ? 'Enabled' : 'Disabled';
        serverPyRunStatus.title = pyRun ? 'Enabled (via server flag --enable-python-run)' : 'Disabled';
        serverPyRunStatus.classList.toggle('status-true', pyRun);
        serverPyRunStatus.classList.toggle('status-false', !pyRun);

        const shRun = details.auto_run_shell === true;
        serverShRunStatus.textContent = shRun ? 'Enabled' : 'Disabled';
        serverShRunStatus.title = shRun ? 'Enabled (via server flag --shell)' : 'Disabled';
        serverShRunStatus.classList.toggle('status-true', shRun);
        serverShRunStatus.classList.toggle('status-false', !shRun);
        if (shRun) serverShRunStatus.classList.add('status-false'); // Keep red style for dangerous enabled shell
    }

     // Get current tab ID helper (remains the same)
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

    // REMOVED displayLastOutput function
    // function displayLastOutput(outputData) { /* ... */ }

    // --- Initialization ---
    displayStatus('Loading settings...');
    currentTabId = await getCurrentTabId();

    if (currentTabId === null) {
         displayStatus('Error: Could not identify the current tab. Settings might not work correctly.', 'error');
    } else {
        console.log(`Popup: Initializing for tab ID: ${currentTabId}`);
        // Fetch Port
        try {
            const portResponse = await browser.runtime.sendMessage({ action: "getPort", tabId: currentTabId });
            serverPortInput.value = portResponse?.port || DEFAULT_PORT;
        } catch (error) { console.error("Popup Init: Error getting port", error); serverPortInput.value = DEFAULT_PORT; }

        // Fetch Activation State
        try {
            const activationResponse = await browser.runtime.sendMessage({ action: "getActivationState" });
            activationToggle.checked = activationResponse?.isActive === true;
        } catch (error) { console.error("Popup Init: Error getting activation", error); activationToggle.checked = false; }

         // REMOVED Fetch Last Output Data
         // try {
         //     const outputResponse = await browser.runtime.sendMessage({ action: "getLastOutput", tabId: currentTabId });
         //     displayLastOutput(outputResponse?.output);
         // } catch (error) { /* ... */ }

        // Attempt initial connection test
        testConnectionBtn.click();
    }

    // --- Event Listeners ---
    // Port input listener remains the same
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
        restartWarning.style.display = (portValue !== '' && portNumber !== DEFAULT_PORT) ? 'block' : 'none';
     });

    // Test Connection listener remains the same
    testConnectionBtn.addEventListener('click', async () => {
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
            const response = await browser.runtime.sendMessage({ action: "testConnection", port: currentInputPort });
             if (response && response.success) {
                 displayStatus('Connection successful! Server status loaded.', 'success');
                 updateServerInfoDisplay(response.details); // This populates server info section
                 const serverReportedPort = response.details.port;
                 if (serverReportedPort && serverReportedPort !== currentInputPort) {
                     console.warn(`Popup: Test connection to ${currentInputPort} successful, but server reported running on ${serverReportedPort}.`);
                 } else {
                     console.log(`Popup: Test connection OK to port ${currentInputPort}. Server details:`, response.details);
                 }
             } else {
                 let errorMsg = response?.details?.message || `Connection failed to port ${currentInputPort}. Is a server running there?`;
                 displayStatus(errorMsg, 'error');
                 updateServerInfoDisplay({}); // Clear server info on failure
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

});
// @@FILENAME@@ extension/popup.js