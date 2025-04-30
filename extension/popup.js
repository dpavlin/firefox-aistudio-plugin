document.addEventListener('DOMContentLoaded', () => {
    const activationToggle = document.getElementById('activationToggle');
    const lastResponseDiv = document.getElementById('last-response');
    const serverPortInput = document.getElementById('serverPort');

    // Storage keys (must match background.js)
    const ACTIVATION_STORAGE_KEY = 'isActivated';
    const PORT_STORAGE_KEY = 'serverPort';
    const LAST_RESPONSE_STORAGE_KEY = 'lastServerResponse';
    const DEFAULT_PORT = 5000;

    if (!activationToggle || !lastResponseDiv || !serverPortInput) {
        console.error("Popup elements not found!");
        return;
    }

    // --- Request initial state from background ---
    console.log("Popup requesting initial data from background.");
    chrome.runtime.sendMessage({ action: 'getPopupData' }, (response) => {
        if (chrome.runtime.lastError) {
            console.error("Error getting popup data:", chrome.runtime.lastError.message);
            lastResponseDiv.textContent = `Error loading status: ${chrome.runtime.lastError.message}`;
            lastResponseDiv.className = 'error';
            serverPortInput.value = DEFAULT_PORT; // Show default on error
            activationToggle.checked = true; // Default activation on error
            return;
        }

        if (response) {
            console.log("Popup received data:", response);
            // Set state from stored values (provide defaults)
            activationToggle.checked = response.activated !== undefined ? response.activated : true;
            serverPortInput.value = response.port !== undefined ? response.port : DEFAULT_PORT;
            displayServerResponse(response.lastResponse || "No response recorded yet.");
        } else {
            console.error("Received empty response from background for getPopupData.");
            lastResponseDiv.textContent = "Failed to load status (empty response).";
            lastResponseDiv.className = 'error';
            // Default values on empty response
            activationToggle.checked = true;
            serverPortInput.value = DEFAULT_PORT;
        }
    });

    // --- Listeners for user changes ---
    activationToggle.addEventListener('change', () => {
        const newState = activationToggle.checked;
        console.log(`Activation toggled to: ${newState}`);
        chrome.runtime.sendMessage(
            { action: 'setActivationState', activated: newState },
            handleBackgroundResponse
        );
    });

    // Use 'input' event for immediate feedback, consider debouncing if performance is an issue
    let portChangeTimeout;
    serverPortInput.addEventListener('input', () => {
        clearTimeout(portChangeTimeout);
        portChangeTimeout = setTimeout(() => {
            const newPort = parseInt(serverPortInput.value, 10);
            // Basic validation
            if (Number.isInteger(newPort) && newPort > 1024 && newPort <= 65535) {
                console.log(`Server port changed to: ${newPort}`);
                chrome.runtime.sendMessage(
                    { action: 'setServerPort', port: newPort },
                    handleBackgroundResponse
                );
            } else {
                console.warn(`Invalid port entered: ${serverPortInput.value}`);
                // Optional: Show validation feedback to user
            }
        }, 500); // Debounce: wait 500ms after last input before sending
    });

    // Helper for logging background responses (optional)
    function handleBackgroundResponse(response) {
        if (chrome.runtime.lastError) {
            console.error("Error communicating with background:", chrome.runtime.lastError.message);
        } else if (response && !response.success) {
            console.error("Background script reported an error:", response.error);
        } else {
            console.log("Background script acknowledged change.");
        }
    }


    // --- Function to display server response nicely ---
    function displayServerResponse(response) {
        lastResponseDiv.className = ''; // Reset classes
        if (typeof response === 'object' && response !== null) {
            let displayText = `Status: ${response.status || 'N/A'}\n`;
            if (response.status === 'success') {
                 lastResponseDiv.classList.add('success');
                 displayText += `Saved As: ${response.saved_as || 'N/A'}\n`;
                 // Indicate Git status clearly
                 if (response.git_updated !== undefined) {
                    displayText += `Git Updated: ${response.git_updated}\n`;
                 }
                 displayText += `Syntax OK: ${response.syntax_ok !== null ? response.syntax_ok : 'N/A'}\n`;
                 displayText += `Run Success: ${response.run_success !== null ? response.run_success : 'N/A'}\n`;
                 displayText += `Log File: ${response.log_file || 'N/A'}`;
            } else if (response.status === 'error') {
                lastResponseDiv.classList.add('error');
                displayText += `Message: ${response.message || 'Unknown error'}`;
            } else {
                 displayText = JSON.stringify(response, null, 2); // Fallback for unknown structure
            }
            lastResponseDiv.textContent = displayText;
        } else {
            lastResponseDiv.textContent = String(response); // Ensure it's a string
             if (String(response).toLowerCase().includes("error") || String(response).toLowerCase().includes("failed")) {
                 lastResponseDiv.classList.add('error');
             }
        }
    }

     // Listen for updates from the background script
     chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        if (message.action === 'updatePopupResponse' && message.lastResponse) {
            console.log("Popup received updated response from background.");
            displayServerResponse(message.lastResponse);
        }
        return false; // No async response needed
     });

});
// --- END OF FILE popup.js ---