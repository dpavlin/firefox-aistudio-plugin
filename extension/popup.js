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
    currentTabId = await getCurrentTabId();
    // ... (rest of initialization for port and activation state remains the same) ...
    if (currentTabId === null) {
         displayStatus('Error: Could not identify the current tab. Port settings might not work correctly.', 'error');
    } else {
        console.log(`Popup: Initializing for tab ID: ${currentTabId}`);
        try {
            const portResponse = await browser.runtime.sendMessage({ action: "getPort", tabId: currentTabId });
            const initialPort = portResponse?.port || DEFAULT_PORT;
            serverPortInput.value = initialPort;
            console.log(`Popup: Initial port for tab ${currentTabId} set to ${initialPort}`);
        } catch (error) { /* ... error handling ... */ }
    }
     try {
         const activationResponse = await browser.runtime.sendMessage({ action: "getActivationState" });
         activationToggle.checked = activationResponse?.isActive === true;
         console.log(`Popup: Initial global activation state: ${activationToggle.checked}`);
     } catch (error) { /* ... error handling ... */ }

     if (currentTabId !== null) { testConnectionBtn.click(); }
     else { displayStatus("Cannot perform initial connection test without Tab ID.", "warning"); }


    // --- Event Listeners ---

    // Port input listener remains the same
    serverPortInput.addEventListener('input', () => {
        // ... validation and storePort message sending ...
    });

    // Test Connection listener remains the same
    testConnectionBtn.addEventListener('click', async () => {
        // ... reads input, sends testConnection message, calls updateServerInfoDisplay ...
    });

    // Activation Toggle listener remains the same
    activationToggle.addEventListener('change', () => {
        // ... sends storeActivationState message ...
    });

    // REMOVED Event listeners for server config toggles
    // serverEnablePython.addEventListener(...)
    // serverEnableShell.addEventListener(...)

});