// popup.js
document.addEventListener('DOMContentLoaded', () => {
    const activationToggle = document.getElementById('activationToggle');
    const lastResponseDiv = document.getElementById('last-response');

    if (!activationToggle || !lastResponseDiv) {
        console.error("Popup elements not found!");
        return;
    }

    // --- Request initial state and last response from background ---
    console.log("Popup requesting initial data from background.");
    chrome.runtime.sendMessage({ action: 'getPopupData' }, (response) => {
        if (chrome.runtime.lastError) {
            console.error("Error getting popup data:", chrome.runtime.lastError.message);
            lastResponseDiv.textContent = `Error loading status: ${chrome.runtime.lastError.message}`;
            lastResponseDiv.className = 'error'; // Apply error style
            return;
        }

        if (response) {
            console.log("Popup received data:", response);
            // Set the toggle state based on stored value (default to true if undefined)
            activationToggle.checked = response.activated !== undefined ? response.activated : true;

            // Display the last server response
            displayServerResponse(response.lastResponse || "No response recorded yet.");
        } else {
            console.error("Received empty response from background for getPopupData.");
            lastResponseDiv.textContent = "Failed to load status (empty response).";
            lastResponseDiv.className = 'error';
            // Default toggle to active if no response received
            activationToggle.checked = true;
        }
    });

    // --- Add listener for toggle changes ---
    activationToggle.addEventListener('change', () => {
        const newState = activationToggle.checked;
        console.log(`Activation toggled to: ${newState}`);
        // Send message to background to update the state
        chrome.runtime.sendMessage(
            { action: 'setActivationState', activated: newState },
            (response) => {
                 if (chrome.runtime.lastError) {
                    console.error("Error setting activation state:", chrome.runtime.lastError.message);
                    // Optional: display an error to the user in the popup
                 } else {
                    console.log("Activation state update sent successfully.");
                 }
            }
        );
    });

    // --- Function to display server response nicely ---
    function displayServerResponse(response) {
        lastResponseDiv.className = ''; // Reset classes
        if (typeof response === 'object' && response !== null) {
            // Format the JSON object for display
            let displayText = `Status: ${response.status || 'N/A'}\n`;
            if (response.status === 'success') {
                 lastResponseDiv.classList.add('success');
                 displayText += `Saved As: ${response.saved_as || 'N/A'}\n`;
                 displayText += `Syntax OK: ${response.syntax_ok !== null ? response.syntax_ok : 'N/A'}\n`;
                 displayText += `Run Success: ${response.run_success !== null ? response.run_success : 'N/A'}\n`;
                 displayText += `Log File: ${response.log_file || 'N/A'}`;
            } else if (response.status === 'error') {
                lastResponseDiv.classList.add('error');
                displayText += `Message: ${response.message || 'Unknown error'}`;
            } else {
                 // Handle unexpected object structure
                 displayText = JSON.stringify(response, null, 2);
            }
            lastResponseDiv.textContent = displayText;
        } else {
            // If it's just a string (like default or error message)
            lastResponseDiv.textContent = response;
             if (response.toLowerCase().includes("error") || response.toLowerCase().includes("failed")) {
                 lastResponseDiv.classList.add('error');
             }
        }
    }

     // Listen for updates from the background script (optional, good for real-time updates)
     chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        if (message.action === 'updatePopupResponse' && message.lastResponse) {
            console.log("Popup received updated response from background.");
            displayServerResponse(message.lastResponse);
        }
        // Note: We don't need an async response from the popup here
        return false;
     });

});