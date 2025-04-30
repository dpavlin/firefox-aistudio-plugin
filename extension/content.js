console.log("AI Code Capture content script loaded (for automatic capture - all blocks).");

// --- Storage Key ---
const ACTIVATION_STORAGE_KEY = 'isActivated';
let isExtensionActivated = true;

// --- CSS Selectors ---
const targetNodeSelector = 'ms-chat-session ms-autoscroll-container > div';
const codeElementSelector = 'ms-code-block pre code';
const modelTurnSelector = 'ms-chat-turn:has(div.chat-turn-container.model)';

// --- Highlight Logic Variables ---
const HIGHLIGHT_INITIAL_CLASS = 'aicapture-highlight-initial';
const HIGHLIGHT_SUCCESS_CLASS = 'aicapture-success';
const HIGHLIGHT_ERROR_CLASS = 'aicapture-error';
const HIGHLIGHT_FADEOUT_CLASS = 'aicapture-fadeout';
const HIGHLIGHT_FINAL_DURATION_MS = 3000;
const HIGHLIGHT_FADEOUT_DELAY_MS = 2500;
const highlightTimers = new Map();
// --- Use a unique attribute instead of innerText for mapping ---
const HIGHLIGHT_ID_ATTR = 'data-aicapture-id';
let highlightCounter = 0; // Simple counter for unique IDs

// --- Debounce and Duplicate Check ---
let debounceTimer;
const DEBOUNCE_DELAY_MS = 1500;
const sentCodeBlocksContent = new Set(); // Still useful to prevent re-sending identical *content*

// --- Helper Function to Apply/Remove/Update Highlight ---
function applyHighlight(element, state = 'initial') {
  if (!element) return;
  const existingTimers = highlightTimers.get(element);
  if (existingTimers) {
    clearTimeout(existingTimers.initialTimer);
    clearTimeout(existingTimers.finalTimer);
    clearTimeout(existingTimers.fadeTimer);
  }
  console.log(`Applying ${state} highlight to:`, element);
  element.classList.remove(
      HIGHLIGHT_INITIAL_CLASS, HIGHLIGHT_SUCCESS_CLASS,
      HIGHLIGHT_ERROR_CLASS, HIGHLIGHT_FADEOUT_CLASS
  );
  let initialTimerId = null, finalTimerId = null, fadeTimerId = null;

  switch (state) {
    case 'initial':
      element.classList.add(HIGHLIGHT_INITIAL_CLASS);
      initialTimerId = setTimeout(() => {
         element.classList.remove(HIGHLIGHT_INITIAL_CLASS);
         highlightTimers.delete(element);
      }, HIGHLIGHT_FINAL_DURATION_MS * 3);
      break;
    case 'success':
      element.classList.add(HIGHLIGHT_SUCCESS_CLASS);
      fadeTimerId = setTimeout(() => element.classList.add(HIGHLIGHT_FADEOUT_CLASS), HIGHLIGHT_FADEOUT_DELAY_MS);
      finalTimerId = setTimeout(() => {
        element.classList.remove(HIGHLIGHT_SUCCESS_CLASS, HIGHLIGHT_FADEOUT_CLASS);
        highlightTimers.delete(element);
        element.removeAttribute(HIGHLIGHT_ID_ATTR); // Clean up attribute
      }, HIGHLIGHT_FINAL_DURATION_MS);
      break;
    case 'error':
      element.classList.add(HIGHLIGHT_ERROR_CLASS);
      fadeTimerId = setTimeout(() => element.classList.add(HIGHLIGHT_FADEOUT_CLASS), HIGHLIGHT_FADEOUT_DELAY_MS);
      finalTimerId = setTimeout(() => {
        element.classList.remove(HIGHLIGHT_ERROR_CLASS, HIGHLIGHT_FADEOUT_CLASS);
        highlightTimers.delete(element);
        element.removeAttribute(HIGHLIGHT_ID_ATTR); // Clean up attribute
      }, HIGHLIGHT_FINAL_DURATION_MS);
      break;
    case 'remove':
       element.classList.remove(HIGHLIGHT_INITIAL_CLASS, HIGHLIGHT_SUCCESS_CLASS, HIGHLIGHT_ERROR_CLASS, HIGHLIGHT_FADEOUT_CLASS);
       highlightTimers.delete(element);
       element.removeAttribute(HIGHLIGHT_ID_ATTR); // Clean up attribute
       break;
  }
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
            // --- Check if element ALREADY has our processing ID ---
            if (codeElement.hasAttribute(HIGHLIGHT_ID_ATTR)) {
                // console.log(` -> Code block ${codeIndex + 1} already being processed or waiting for response. Skipping.`);
                return; // Skip if we're already handling this specific element
            }

            const capturedCode = codeElement.innerText;
            const trimmedCode = capturedCode ? capturedCode.trim() : '';

            // Check content duplication separately
            if (trimmedCode.length > 0 && !sentCodeBlocksContent.has(capturedCode)) {
                 const uniqueId = `aicapture-${Date.now()}-${highlightCounter++}`;
                 console.log(` -> Found NEW code block ${codeIndex + 1} (ID: ${uniqueId}). Applying INITIAL highlight and sending to background:`, capturedCode.substring(0, 80) + "...");

                 // --- Add unique ID attribute ---
                 codeElement.setAttribute(HIGHLIGHT_ID_ATTR, uniqueId);

                 applyHighlight(codeElement, 'initial');
                 // --- Send ID along with code ---
                 chrome.runtime.sendMessage({
                     action: 'sendCodeDirectly',
                     code: capturedCode,
                     captureId: uniqueId // Send the ID
                 });
                 sentCodeBlocksContent.add(capturedCode); // Still track content to avoid resending identical blocks
            } else if (sentCodeBlocksContent.has(capturedCode)) {
                 console.log(` -> Code block ${codeIndex + 1} content already sent. Skipping.`);
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
        if (chrome.runtime.lastError) { console.error("Error reading activation state:", chrome.runtime.lastError.message); isExtensionActivated = true; }
        else { isExtensionActivated = result.isActivated !== undefined ? result.isActivated : true; }
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
        // Simplified check - trigger debounce on almost any relevant change within target
        for(const mutation of mutationsList) {
             if (mutation.type === 'childList' || mutation.type === 'subtree' || mutation.type === 'characterData') {
                 relevantMutationDetected = true;
                 break;
             }
        }
        if (relevantMutationDetected) {
             // console.log("Relevant mutation detected, scheduling code check after debounce."); // Less verbose
             clearTimeout(debounceTimer);
             debounceTimer = setTimeout(() => {
                 // console.log("MutationObserver running findAndSendNewCodeBlocks after debounce."); // Less verbose
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
  if (message.action === 'serverProcessingComplete') {
    console.log("CONTENT SCRIPT: Received 'serverProcessingComplete'", message); // Added log
    // --- Find element by ID attribute ---
    const elementId = message.captureId;
    if (!elementId) {
        console.warn("Received server response without capture ID.");
        return false;
    }
    const codeElement = document.querySelector(`[${HIGHLIGHT_ID_ATTR}="${elementId}"]`);

    if (codeElement) {
      console.log(`Found matching element for ID ${elementId}, applying final highlight state (Success: ${message.success})`);
      applyHighlight(codeElement, message.success ? 'success' : 'error');
      // No need to manage map anymore, attribute is removed by applyHighlight on final timer
    } else {
      console.warn(`Could not find the specific code element on page with ID ${elementId} to apply final highlight.`);
    }
  }
  return false; // No async response needed
});
// --- END OF FILE content.js ---