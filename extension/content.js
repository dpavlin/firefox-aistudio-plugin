// content.js
console.log("AI Code Capture content script loaded (for automatic capture - all blocks).");

// --- Storage Key (must match background.js) ---
const ACTIVATION_STORAGE_KEY = 'isActivated';
let isExtensionActivated = true; // Default to activated until checked

// --- CSS Selectors for Google AI Studio ---
const targetNodeSelector = 'ms-chat-session ms-autoscroll-container > div';
const codeElementSelector = 'ms-code-block pre code';
const modelTurnSelector = 'ms-chat-turn:has(div.chat-turn-container.model)';

// --- Highlight Logic Variables ---
const HIGHLIGHT_CLASS = 'aicapture-highlight';
const HIGHLIGHT_DURATION_MS = 2500;
const highlightTimers = new Map();

// --- Debounce and Duplicate Check Logic ---
let debounceTimer;
const DEBOUNCE_DELAY_MS = 1500;
const sentCodeBlocksContent = new Set();

// --- Helper Function to Apply/Remove Highlight ---
function applyHighlight(element) {
  if (!element) return;
  if (highlightTimers.has(element)) {
    clearTimeout(highlightTimers.get(element));
  }
  console.log("Applying highlight to:", element);
  element.classList.add(HIGHLIGHT_CLASS);
  const timerId = setTimeout(() => {
    console.log("Removing highlight from:", element);
    element.classList.remove(HIGHLIGHT_CLASS);
    highlightTimers.delete(element);
  }, HIGHLIGHT_DURATION_MS);
  highlightTimers.set(element, timerId);
}

// Function to process model turns and send NEW code blocks
function findAndSendNewCodeBlocks(target) {
    // --- Check activation state before proceeding ---
    if (!isExtensionActivated) {
        console.log("Auto-capture is disabled. Skipping code block check.");
        return;
    }
    // --- End activation check ---

    console.log(`Processing turns within target:`, target);
    console.log(`Using model turn selector: ${modelTurnSelector}`);
    const modelTurns = target.querySelectorAll(modelTurnSelector);

    if (!modelTurns || modelTurns.length === 0) {
        console.log(`No model turns found.`);
        return;
    }
    console.log(`Found ${modelTurns.length} model turn(s). Processing...`);

    modelTurns.forEach((turnElement, turnIndex) => {
        console.log(`Processing Turn ${turnIndex + 1}`);
        console.log(`Searching for code elements using selector: ${codeElementSelector}`);
        const codeElements = turnElement.querySelectorAll(codeElementSelector);

        if (!codeElements || codeElements.length === 0) {
            console.log(` -> No code elements found in this turn.`);
            return; // Continue to the next turn
        }
        console.log(` -> Found ${codeElements.length} code element(s) in this turn.`);

        codeElements.forEach((codeElement, codeIndex) => {
            const capturedCode = codeElement.innerText;
            const trimmedCode = capturedCode ? capturedCode.trim() : '';

            if (trimmedCode.length > 0 && !sentCodeBlocksContent.has(capturedCode)) {
                 console.log(` -> Found NEW code block ${codeIndex + 1} in Turn ${turnIndex + 1}. Applying highlight and sending to background:`, capturedCode.substring(0, 80) + "...");
                 applyHighlight(codeElement);
                 chrome.runtime.sendMessage({ action: 'sendCodeDirectly', code: capturedCode }); // Send only if activated (already checked)
                 sentCodeBlocksContent.add(capturedCode);
            } else if (sentCodeBlocksContent.has(capturedCode)) {
                 console.log(` -> Code block ${codeIndex + 1} in Turn ${turnIndex + 1} already sent. Skipping.`);
            } else {
                 console.log(` -> Code block ${codeIndex + 1} in Turn ${turnIndex + 1} is empty. Skipping.`);
            }
        });
    });
     console.log("Finished processing turns.");
}

// --- Function to get initial activation state ---
function loadActivationState() {
    chrome.storage.local.get([ACTIVATION_STORAGE_KEY], (result) => {
        if (chrome.runtime.lastError) {
            console.error("Error reading activation state:", chrome.runtime.lastError.message);
            isExtensionActivated = true; // Default to active on error
        } else {
            isExtensionActivated = result.isActivated !== undefined ? result.isActivated : true; // Default true
        }
        console.log(`Content script initial activation state: ${isExtensionActivated}`);
    });
}

// --- Listen for changes in storage (e.g., user toggles in popup) ---
chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName === 'local' && changes[ACTIVATION_STORAGE_KEY]) {
        isExtensionActivated = changes[ACTIVATION_STORAGE_KEY].newValue;
        console.log(`Content script detected activation state change: ${isExtensionActivated}`);
        // Optional: If disabling, maybe clear the MutationObserver? And restart if enabling?
        // For simplicity, we just check the flag before sending.
    }
});


// --- MutationObserver Setup ---
const targetNode = document.querySelector(targetNodeSelector);

if (targetNode) {
    console.log("Target node found:", targetNode, "Setting up MutationObserver.");

    const callback = function(mutationsList, observer) {
        let relevantMutationDetected = false;
        for(const mutation of mutationsList) {
             if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                 for (const node of mutation.addedNodes) {
                     if (node.nodeType === Node.ELEMENT_NODE && node.matches(modelTurnSelector)) {
                         relevantMutationDetected = true; break;
                     }
                 }
             }
             if (relevantMutationDetected) break;
             if (mutation.type === 'subtree' || mutation.type === 'characterData') {
                 relevantMutationDetected = true; break;
             }
        }
        if (relevantMutationDetected) {
             console.log("Relevant mutation detected, scheduling code check after debounce.");
             clearTimeout(debounceTimer);
             debounceTimer = setTimeout(() => {
                 console.log("MutationObserver running findAndSendNewCodeBlocks after debounce.");
                 findAndSendNewCodeBlocks(targetNode);
             }, DEBOUNCE_DELAY_MS);
        }
    };

    const observer = new MutationObserver(callback);
    const config = { childList: true, subtree: true, characterData: true };
    observer.observe(targetNode, config);
    console.log("MutationObserver is now observing the target node and its subtree.");

    // Load initial state and check for initial code
    loadActivationState(); // Get initial activation state
    console.log("Checking for initial code on page load...");
    setTimeout(() => findAndSendNewCodeBlocks(document), 500);

} else {
    console.error(`Could not find the target node ('${targetNodeSelector}') to observe. Automatic capture will not work. Please update the selector in content.js.`);
}


// --- Listener for Manual Capture (REMOVED - replaced by popup toggle) ---
/*
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'getCodeFromPage') {
      // ... old manual capture logic removed ...
  }
});
*/