console.log("AI Code Capture content script loaded (for automatic capture - all blocks).");

// --- Storage Keys ---
const ACTIVATION_STORAGE_KEY = 'isActivated';
const SESSION_STORAGE_KEY = 'aicapture_sent_hashes_v1'; // Key for sessionStorage

// --- Global State ---
let isExtensionActivated = true;
// Use a Set to store HASHES of code blocks already processed in this session
const sentCodeBlockHashes = new Set();

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
const HIGHLIGHT_ID_ATTR = 'data-aicapture-id';
let highlightCounter = 0;

// --- Debounce ---
let debounceTimer;
const DEBOUNCE_DELAY_MS = 1500;

// --- Simple String Hash Function (basic, not crypto grade) ---
function hashCode(str) {
  let hash = 0, i, chr;
  if (str.length === 0) return hash;
  for (i = 0; i < str.length; i++) {
    chr = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + chr;
    hash |= 0; // Convert to 32bit integer
  }
  return hash;
}

// --- Function to load sent hashes from sessionStorage ---
function loadSentHashes() {
    try {
        const storedHashes = sessionStorage.getItem(SESSION_STORAGE_KEY);
        if (storedHashes) {
            const parsedHashes = JSON.parse(storedHashes);
            if (Array.isArray(parsedHashes)) {
                parsedHashes.forEach(hash => sentCodeBlockHashes.add(hash));
                console.log(`Loaded ${sentCodeBlockHashes.size} previously sent code block hashes from sessionStorage.`);
            } else {
                 console.warn("Invalid data found in sessionStorage for sent hashes.");
                 sessionStorage.removeItem(SESSION_STORAGE_KEY); // Clear invalid data
            }
        } else {
            console.log("No previously sent hashes found in sessionStorage for this session.");
        }
    } catch (e) {
        console.error("Error loading or parsing sent hashes from sessionStorage:", e);
        sessionStorage.removeItem(SESSION_STORAGE_KEY); // Clear potentially corrupt data
    }
}

// --- Function to save sent hashes to sessionStorage ---
function saveSentHashes() {
    try {
        const hashesArray = Array.from(sentCodeBlockHashes);
        sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(hashesArray));
        // console.log(`Saved ${hashesArray.length} hashes to sessionStorage.`); // Can be verbose
    } catch (e) {
        console.error("Error saving sent hashes to sessionStorage:", e);
        // Consider if storage is full or other issues
    }
}


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
        element.removeAttribute(HIGHLIGHT_ID_ATTR);
      }, HIGHLIGHT_FINAL_DURATION_MS);
      break;
    case 'error':
      element.classList.add(HIGHLIGHT_ERROR_CLASS);
      fadeTimerId = setTimeout(() => element.classList.add(HIGHLIGHT_FADEOUT_CLASS), HIGHLIGHT_FADEOUT_DELAY_MS);
      finalTimerId = setTimeout(() => {
        element.classList.remove(HIGHLIGHT_ERROR_CLASS, HIGHLIGHT_FADEOUT_CLASS);
        highlightTimers.delete(element);
        element.removeAttribute(HIGHLIGHT_ID_ATTR);
      }, HIGHLIGHT_FINAL_DURATION_MS);
      break;
    case 'remove':
       element.classList.remove(HIGHLIGHT_INITIAL_CLASS, HIGHLIGHT_SUCCESS_CLASS, HIGHLIGHT_ERROR_CLASS, HIGHLIGHT_FADEOUT_CLASS);
       highlightTimers.delete(element);
       element.removeAttribute(HIGHLIGHT_ID_ATTR);
       break;
  }
   if (state !== 'remove') {
     highlightTimers.set(element, { initialTimer: initialTimerId, finalTimer: finalTimerId, fadeTimer: fadeTimerId });
   }
}

// Function to process model turns and send NEW code blocks
function findAndSendNewCodeBlocks(target) {
    if (!isExtensionActivated) {
        // console.log("Auto-capture is disabled. Skipping code block check."); // Less verbose
        return;
    }
    // console.log(`Processing turns within target:`, target); // Less verbose
    const modelTurns = target.querySelectorAll(modelTurnSelector);
    if (!modelTurns || modelTurns.length === 0) return;

    // console.log(`Found ${modelTurns.length} model turn(s). Processing...`);

    modelTurns.forEach((turnElement, turnIndex) => {
        const codeElements = turnElement.querySelectorAll(codeElementSelector);
        if (!codeElements || codeElements.length === 0) return;

        // console.log(` -> Found ${codeElements.length} code element(s) in Turn ${turnIndex + 1}.`);

        codeElements.forEach((codeElement, codeIndex) => {
            if (codeElement.hasAttribute(HIGHLIGHT_ID_ATTR)) {
                return; // Skip if already being processed
            }

            const capturedCode = codeElement.innerText;
            const trimmedCode = capturedCode ? capturedCode.trim() : '';

            if (trimmedCode.length > 0) {
                const codeHash = hashCode(capturedCode); // Calculate hash

                // Check if HASH has been sent before in this session
                if (!sentCodeBlockHashes.has(codeHash)) {
                     const uniqueId = `aicapture-${Date.now()}-${highlightCounter++}`;
                     console.log(` -> Found NEW code block ${codeIndex + 1} (ID: ${uniqueId}, Hash: ${codeHash}). Applying INITIAL highlight and sending:`, capturedCode.substring(0, 80) + "...");
                     codeElement.setAttribute(HIGHLIGHT_ID_ATTR, uniqueId);
                     applyHighlight(codeElement, 'initial');

                     chrome.runtime.sendMessage({
                         action: 'sendCodeDirectly',
                         code: capturedCode,
                         captureId: uniqueId
                     });

                     // Add hash to Set and save to sessionStorage
                     sentCodeBlockHashes.add(codeHash);
                     saveSentHashes();

                } else {
                     console.log(` -> Code block ${codeIndex + 1} hash (${codeHash}) already sent in this session. Skipping.`);
                }
            } else {
                 // console.log(` -> Code block ${codeIndex + 1} is empty. Skipping.`);
            }
        });
    });
     // console.log("Finished processing turns.");
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


// --- Initialize ---
loadActivationState(); // Get initial activation state
loadSentHashes(); // Load hashes from sessionStorage on script start

// --- MutationObserver Setup ---
const targetNode = document.querySelector(targetNodeSelector);
if (targetNode) {
    console.log("Target node found:", targetNode, "Setting up MutationObserver.");
    const callback = function(mutationsList, observer) {
        let relevantMutationDetected = false;
        for(const mutation of mutationsList) {
             if (mutation.type === 'childList' || mutation.type === 'subtree' || mutation.type === 'characterData') {
                 relevantMutationDetected = true;
                 break;
             }
        }
        if (relevantMutationDetected) {
             clearTimeout(debounceTimer);
             debounceTimer = setTimeout(() => {
                 findAndSendNewCodeBlocks(targetNode);
             }, DEBOUNCE_DELAY_MS);
        }
    };
    const observer = new MutationObserver(callback);
    const config = { childList: true, subtree: true, characterData: true };
    observer.observe(targetNode, config);
    console.log("MutationObserver is now observing the target node and its subtree.");
    console.log("Checking for initial code on page load...");
    setTimeout(() => findAndSendNewCodeBlocks(document), 500);
} else {
    console.error(`Could not find the target node ('${targetNodeSelector}') to observe.`);
}


// --- Listener for updates from Background Script ---
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'serverProcessingComplete') {
    console.log("CONTENT SCRIPT: Received 'serverProcessingComplete'", message);
    const elementId = message.captureId;
    if (!elementId) { console.warn("Received server response without capture ID."); return false; }

    // Find element using the attribute selector
    const codeElement = document.querySelector(`[${HIGHLIGHT_ID_ATTR}="${elementId}"]`);

    if (codeElement) {
      console.log(`Found matching element for ID ${elementId}, applying final highlight state (Success: ${message.success})`);
      applyHighlight(codeElement, message.success ? 'success' : 'error');
      // Note: element ID attribute is removed by applyHighlight final timer
    } else {
      console.warn(`Could not find code element with ID ${elementId} to apply final highlight.`);
    }
  }
  return false;
});
// --- END OF FILE content.js ---