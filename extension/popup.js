document.addEventListener('DOMContentLoaded', () => {
    // Use setTimeout to ensure elements are definitely ready
    setTimeout(() => {
        const serverPortInput = document.getElementById('serverPort');
        const activationToggle = document.getElementById('activationToggle');
        const refreshStatusBtn = document.getElementById('refreshStatusBtn'); // Now likely exists
        const saveConfigBtn = document.getElementById('saveConfigBtn');
        const lastActionStatus = document.getElementById('last-action-status'); // Now likely exists

        // --- Status Display Elements ---
        // ... (rest of getElementById calls)

        // Check if elements were found before proceeding
        if (!refreshStatusBtn || !lastActionStatus /* || !other elements */) {
             console.error("Popup DOM elements not found!");
             // Optionally display an error in the popup itself
             if (lastActionStatus) { // Check if even status area exists
                  lastActionStatus.textContent = "Error initializing popup UI.";
                  lastActionStatus.className = 'error';
             }
             return; // Stop execution if critical elements are missing
        }


        // --- Rest of your popup.js code ---
        // ... (utility functions, fetchServerStatus, saveConfiguration, etc.) ...
        // ... (load settings and initial status call) ...
        // ... (event listeners) ...

         // Example: Move event listener attachments here
         refreshStatusBtn.addEventListener('click', fetchServerStatus);
         saveConfigBtn.addEventListener('click', saveConfiguration);
          serverPortInput.addEventListener('change', handlePortChange); // Assuming you wrap port logic in a function
          activationToggle.addEventListener('change', handleActivationToggle); // Assuming you wrap toggle logic


    }, 0); // Zero delay setTimeout
});

// Define handler functions outside setTimeout if needed, e.g.:
// function handlePortChange() { ... }
// function handleActivationToggle() { ... }