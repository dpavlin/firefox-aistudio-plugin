// @@FILENAME@@ content.js
console.log("AI Code Capture content script loaded (for automatic capture - all blocks).");

// --- Storage Key ---
const ACTIVATION_STORAGE_KEY = 'isActivated';
let isExtensionActivated = true;

// --- CSS Selectors ---
const targetNodeSelector = 'ms-chat-session ms-autoscroll-container > div';
const codeElementSelector = 'ms-code-block pre code';
const modelTurnSelector = 'ms-chat-turn:has(div.chat-turn-container.model)';

// --- Highlight Logic Variables ---
const HIGHLIGHT_INITIAL_CLASS = 'aicapture-highlight'; // Yellow processing indicator
const HIGHLIGHT_SUCCESS_CLASS = 'aicapture-success'; // Green border for success
const HIGHLIGHT_ERROR_CLASS = 'aicapture-error';     // Red border for error
const HIGHLIGHT_FADEOUT_CLASS = 'aicapture-fadeout'; // Class to trigger fade-out transition
const HIGHLIGHT_FINAL_DURATION_MS = 3000; // How long GREEN/RED border stays
const HIGHLIGHT_FADEOUT_DELAY_MS = 2500; // How long GREEN/RED stays before starting fade
const highlightTimers = new Map(); // Map<Element, { initialTimer: number, finalTimer: number, fadeTimer: number }>

// --- Debounce and Duplicate Check ---
let debounceTimer;
const DEBOUNCE_DELAY_MS = 1500;
const sentCodeBlocksContent = new Set();
// Map to find code element by its content (needed for response handling)
const codeElementMap = new Map();

// --- Helper Function to Apply/Remove/Update Highlight ---
function applyHighlight(element, state = 'initial') {
  if (!element) return;

  // Clear any existing timers for this element
  const existingTimers = highlightTimers.get(element);
  if (existingTimers) {
    clearTimeout(existingTimers.initialTimer);
    clearTimeout(existingTimers.finalTimer);
    clearTimeout(existingTimers.fadeTimer);
  }

  console.log(`Applying ${state} highlight to:`, element);

  // Remove all potentially existing highlight classes first
  element.classList.remove(HIGHLIGHT_INITIAL_CLASS, HIGHLIGHT_SUCCESS_CLASS, HIGHLIGHT_ERROR_CLASS, HIGHLIGHT_FADEOUT_CLASS);

  let initialTimerId = null;
  let finalTimerId = null;
  let fadeTimerId = null;

  switch (state) {
    case 'initial':
      element.classList.add(HIGHLIGHT_INITIAL_CLASS);
      // Set a timer to remove the initial highlight if no server response comes back quickly enough
      initialTimerId = setTimeout(() => {
         console.log("Initial highlight timeout, removing:", element);
         element.classList.remove(HIGHLIGHT_INITIAL_CLASS);
         highlightTimers.delete(element);
      }, HIGHLIGHT_DURATION_MS * 2); // Give it longer than usual highlight duration
      break;
    case 'success':
      element.classList.add(HIGHLIGHT_SUCCESS_CLASS);
      // Timer to start fadeout
      fadeTimerId = setTimeout(() => {
         element.classList.add(HIGHLIGHT_FADEOUT_CLASS);
      }, HIGHLIGHT_FADEOUT_DELAY_MS);
      // Timer to remove class completely after fadeout
      finalTimerId = setTimeout(() => {
        element.classList.remove(HIGHLIGHT_SUCCESS_CLASS, HIGHLIGHT_FADEOUT_CLASS);
        highlightTimers.delete(element);
      }, HIGHLIGHT_FINAL_DURATION_MS);
      break;
    case 'error':
      element.classList.add(HIGHLIGHT_ERROR_CLASS);
      // Timer to start fadeout
      fadeTimerId = setTimeout(() => {
          element.classList.add(HIGHLIGHT_FADEOUT_CLASS);
       }, HIGHLIGHT_FADEOUT_DELAY_MS);
      // Timer to remove class completely after fadeout
      finalTimerId = setTimeout(() => {
        element.classList.remove(HIGHLIGHT_ERROR_CLASS, HIGHLIGHT_FADEOUT_CLASS);
        highlightTimers.delete(element);
      }, HIGHLIGHT_FINAL_DURATION_MS);
      break;
    case 'remove': // Explicit removal
       element.classList.remove(HIGHLIGHT_INITIAL_CLASS, HIGHLIGHT_SUCCESS_CLASS, HIGHLIGHT_ERROR_CLASS, HIGHLIGHT_FADEOUT_CLASS);
       highlightTimers.delete(element);
       break;
  }
  // Store timers
   if (state !== 'remove') {
     highlightTimers.set(element, { initialTimer: initialTimerId, finalTimer: finalTimerId, fadeTimer: fadeTimerId });
   }
}

// Function to process model turns and send NEW code blocks
function findAndSendNewCodeBlocks(target) {
    if (!isExtensionActivated) {
        console.log("Auto-capture is disabled. Skipping code block check.");
        return;
    }
    console.log(`Processing turns within target:`, target);
    const modelTurns = target.querySelectorAll(modelTurnSelector);
    if (!modelTurns || modelTurns.length === 0) return;

    console.log(`Found ${modelTurns.length} model turn(s). Processing...`);

    modelTurns.forEach((turnElement, turnIndex) => {
        const codeElements = turnElement.querySelectorAll(codeElementSelector);
        if (!codeElements || codeElements.length === 0) return;

        console.log(` -> Found ${codeElements.length} code element(s) in Turn ${turnIndex + 1}.`);

        codeElements.forEach((codeElement, codeIndex) => {
            const capturedCode = codeElement.innerText;
            const trimmedCode = capturedCode ? capturedCode.trim() : '';

            if (trimmedCode.length > 0 && !sentCodeBlocksContent.has(capturedCode)) {
                 console.log(` -> Found NEW code block ${codeIndex + 1}. Applying INITIAL highlight and sending to background:`, capturedCode.substring(0, 80) + "...");
                 applyHighlight(codeElement, 'initial'); // Apply initial yellow highlight
                 codeElementMap.set(capturedCode, codeElement); // Map content to element
                 chrome.runtime.sendMessage({ action: 'sendCodeDirectly', code: capturedCode });
                 sentCodeBlocksContent.add(capturedCode);
                 // Clean up map entry after a while if no response comes
                 setTimeout(() => {
                     if (codeElementMap.delete(capturedCode)) {
                         console.log(`Cleaned up element map for code starting with "${capturedCode.substring(0,20)}..."`);
                     }
                 }, 35000); // Slightly longer than background timeout
            } else if (sentCodeBlocksContent.has(capturedCode)) {
                 console.log(` -> Code block ${codeIndex + 1} already sent. Skipping.`);
            } else {
                 console.log(` -> Code block ${codeIndex + 1} is empty. Skipping.`);
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
            isExtensionActivated = true;
        } else {
            isExtensionActivated = result.isActivated !== undefined ? result.isActivated : true;
        }
        console.log(`Content script initial activation state: ${isExtensionActivated}`);
    });
}

// --- Listen for changes in storage ---
chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName === 'local' && changes[ACTIVATION_STORAGE_KEY]) {
        isExtensionActivated = changes[ACTIVATION_STORAGE_KEY].newValue;
        console.log(`Content script detected activation state change: ${isExtensionActivated}`);
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
                     if (node.nodeType === Node.ELEMENT_NODE && (node.matches(modelTurnSelector) || node.querySelector(modelTurnSelector))) {
                         relevantMutationDetected = true; break;
                     }
                 }
             }
             if (relevantMutationDetected) break;
             if (mutation.type === 'subtree' || mutation.type === 'characterData') {
                 // Check if the change happened within a model turn, more targeted
                 let parentTurn = mutation.target.parentElement?.closest('ms-chat-turn');
                 if (parentTurn?.querySelector('div.chat-turn-container.model')) {
                    relevantMutationDetected = true; break;
                 }
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
    loadActivationState();
    console.log("Checking for initial code on page load...");
    setTimeout(() => findAndSendNewCodeBlocks(document), 500);
} else {
    console.error(`Could not find the target node ('${targetNodeSelector}') to observe.`);
}


// --- Listener for updates from Background Script ---
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // Note: We are NOT checking sender ID here, assuming messages are from our background
  if (message.action === 'serverProcessingComplete') {
    console.log("Received server processing result:", message);
    const codeElement = codeElementMap.get(message.originalCode); // Find element by original code content
    if (codeElement) {
      console.log(`Found matching element for code, applying final highlight state (Success: ${message.success})`);
      applyHighlight(codeElement, message.success ? 'success' : 'error');
      codeElementMap.delete(message.originalCode); // Clean up map entry now
    } else {
      console.warn("Could not find the specific code element on page to apply final highlight for code:", message.originalCode.substring(0, 50) + "...");
    }
  }
  // No async response needed from content script for this message
  return false;
});
// --- END OF FILE content.js ---