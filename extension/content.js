// @@FILENAME@@ content.js
console.log("AI Code Capture content script loaded (for automatic capture - all blocks).");

// --- Storage Keys & Default Port ---
const ACTIVATION_STORAGE_KEY = 'isActivated';
const PORT_STORAGE_KEY = 'serverPort';
const DEFAULT_PORT = 5000;
let contentScriptPort = DEFAULT_PORT; // Store port for this instance

// --- Session Storage Key (Now Dynamic) ---
let SESSION_STORAGE_KEY = `aicapture_sent_hashes_v1_PORT_${contentScriptPort}`;

// --- Global State ---
let isExtensionActivated = true;
const sentCodeBlockHashes = new Set(); // Stores hashes for the current port's session

// --- CSS Selectors & Highlight --- (Unchanged from previous version)
const targetNodeSelector = 'ms-chat-session ms-autoscroll-container > div';
const codeElementSelector = 'ms-code-block pre code';
const modelTurnSelector = 'ms-chat-turn:has(div.chat-turn-container.model)';
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

// --- Simple String Hash Function --- (Unchanged)
function hashCode(str) { /* ... hash function code ... */
  let hash = 0, i, chr; if (str.length === 0) return hash;
  for (i = 0; i < str.length; i++) { chr = str.charCodeAt(i); hash = ((hash << 5) - hash) + chr; hash |= 0; }
  return hash;
}

// --- Function to load sent hashes from PORT-SPECIFIC sessionStorage ---
function loadSentHashes() {
    sentCodeBlockHashes.clear(); // Clear previous hashes if port changed mid-session
    SESSION_STORAGE_KEY = `aicapture_sent_hashes_v1_PORT_${contentScriptPort}`; // Update key
    try {
        const storedHashes = sessionStorage.getItem(SESSION_STORAGE_KEY);
        if (storedHashes) {
            const parsedHashes = JSON.parse(storedHashes);
            if (Array.isArray(parsedHashes)) {
                parsedHashes.forEach(hash => sentCodeBlockHashes.add(hash));
                console.log(`Loaded ${sentCodeBlockHashes.size} hashes for port ${contentScriptPort} from sessionStorage.`);
            } else {
                 console.warn(`Invalid data in sessionStorage for key ${SESSION_STORAGE_KEY}. Clearing.`);
                 sessionStorage.removeItem(SESSION_STORAGE_KEY);
            }
        } else {
            console.log(`No hashes found in sessionStorage for port ${contentScriptPort}.`);
        }
    } catch (e) {
        console.error(`Error loading/parsing hashes from sessionStorage (${SESSION_STORAGE_KEY}):`, e);
        sessionStorage.removeItem(SESSION_STORAGE_KEY);
    }
}

// --- Function to save sent hashes to PORT-SPECIFIC sessionStorage ---
function saveSentHashes() {
    try {
        const hashesArray = Array.from(sentCodeBlockHashes);
        sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(hashesArray));
    } catch (e) {
        console.error(`Error saving hashes to sessionStorage (${SESSION_STORAGE_KEY}):`, e);
    }
}


// --- Highlight Helper --- (Unchanged)
function applyHighlight(element, state = 'initial') { /* ... applyHighlight code ... */
    if (!element) return;
    const existingTimers = highlightTimers.get(element);
    if (existingTimers) { clearTimeout(existingTimers.initialTimer); clearTimeout(existingTimers.finalTimer); clearTimeout(existingTimers.fadeTimer); }
    console.log(`Applying ${state} highlight to:`, element);
    element.classList.remove(HIGHLIGHT_INITIAL_CLASS, HIGHLIGHT_SUCCESS_CLASS, HIGHLIGHT_ERROR_CLASS, HIGHLIGHT_FADEOUT_CLASS);
    let initialTimerId = null, finalTimerId = null, fadeTimerId = null;
    switch (state) {
      case 'initial': element.classList.add(HIGHLIGHT_INITIAL_CLASS); initialTimerId = setTimeout(() => { element.classList.remove(HIGHLIGHT_INITIAL_CLASS); highlightTimers.delete(element); }, HIGHLIGHT_FINAL_DURATION_MS * 3); break;
      case 'success': element.classList.add(HIGHLIGHT_SUCCESS_CLASS); fadeTimerId = setTimeout(() => element.classList.add(HIGHLIGHT_FADEOUT_CLASS), HIGHLIGHT_FADEOUT_DELAY_MS); finalTimerId = setTimeout(() => { element.classList.remove(HIGHLIGHT_SUCCESS_CLASS, HIGHLIGHT_FADEOUT_CLASS); highlightTimers.delete(element); element.removeAttribute(HIGHLIGHT_ID_ATTR); }, HIGHLIGHT_FINAL_DURATION_MS); break;
      case 'error': element.classList.add(HIGHLIGHT_ERROR_CLASS); fadeTimerId = setTimeout(() => element.classList.add(HIGHLIGHT_FADEOUT_CLASS), HIGHLIGHT_FADEOUT_DELAY_MS); finalTimerId = setTimeout(() => { element.classList.remove(HIGHLIGHT_ERROR_CLASS, HIGHLIGHT_FADEOUT_CLASS); highlightTimers.delete(element); element.removeAttribute(HIGHLIGHT_ID_ATTR); }, HIGHLIGHT_FINAL_DURATION_MS); break;
      case 'remove': element.classList.remove(HIGHLIGHT_INITIAL_CLASS, HIGHLIGHT_SUCCESS_CLASS, HIGHLIGHT_ERROR_CLASS, HIGHLIGHT_FADEOUT_CLASS); highlightTimers.delete(element); element.removeAttribute(HIGHLIGHT_ID_ATTR); break;
    }
    if (state !== 'remove') { highlightTimers.set(element, { initialTimer: initialTimerId, finalTimer: finalTimerId, fadeTimer: fadeTimerId }); }
}

// --- Code Processing Function --- (Unchanged logic, uses global state)
function findAndSendNewCodeBlocks(target) { /* ... findAndSendNewCodeBlocks code checking isExtensionActivated and sentCodeBlockHashes ... */
    if (!isExtensionActivated) return;
    const modelTurns = target.querySelectorAll(modelTurnSelector);
    if (!modelTurns || modelTurns.length === 0) return;
    modelTurns.forEach((turnElement, turnIndex) => {
        const codeElements = turnElement.querySelectorAll(codeElementSelector);
        if (!codeElements || codeElements.length === 0) return;
        codeElements.forEach((codeElement, codeIndex) => {
            if (codeElement.hasAttribute(HIGHLIGHT_ID_ATTR)) return;
            const capturedCode = codeElement.innerText; const trimmedCode = capturedCode?.trim();
            if (trimmedCode?.length > 0) {
                const codeHash = hashCode(capturedCode);
                if (!sentCodeBlockHashes.has(codeHash)) {
                     const uniqueId = `aicapture-${Date.now()}-${highlightCounter++}`;
                     console.log(` -> Found NEW block (ID: ${uniqueId}, Hash: ${codeHash}). Applying INITIAL highlight & sending...`);
                     codeElement.setAttribute(HIGHLIGHT_ID_ATTR, uniqueId);
                     applyHighlight(codeElement, 'initial');
                     chrome.runtime.sendMessage({ action: 'sendCodeDirectly', code: capturedCode, captureId: uniqueId });
                     sentCodeBlockHashes.add(codeHash); saveSentHashes();
                     setTimeout(() => { /* Cleanup map if needed */ }, 35000);
                } else { /* console.log(` -> Hash ${codeHash} already sent. Skipping.`); */ }
            }
        });
    });
}

// --- Function to get initial state from background storage ---
function loadInitialExtensionState() {
    chrome.storage.local.get([ACTIVATION_STORAGE_KEY, PORT_STORAGE_KEY], (result) => {
        if (chrome.runtime.lastError) {
            console.error("Error reading initial state:", chrome.runtime.lastError.message);
            // Use defaults on error
            isExtensionActivated = true;
            contentScriptPort = DEFAULT_PORT;
        } else {
            isExtensionActivated = result.isActivated !== undefined ? result.isActivated : true;
            contentScriptPort = result.serverPort !== undefined ? result.serverPort : DEFAULT_PORT;
        }
        console.log(`Content script initial state: Activated=${isExtensionActivated}, Port=${contentScriptPort}`);
        // Load hashes specific to this port AFTER port is determined
        loadSentHashes();
    });
}

// --- Listen for storage changes ---
chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName === 'local') {
        let stateChanged = false;
        if (changes[ACTIVATION_STORAGE_KEY]) {
            isExtensionActivated = changes[ACTIVATION_STORAGE_KEY].newValue;
            console.log(`Content script detected activation state change: ${isExtensionActivated}`);
            stateChanged = true;
        }
        if (changes[PORT_STORAGE_KEY]) {
            const oldPort = contentScriptPort;
            contentScriptPort = changes[PORT_STORAGE_KEY].newValue;
            console.log(`Content script detected port change: ${contentScriptPort}`);
            // Port changed, reload/clear hashes for the new port's session key
            if (oldPort !== contentScriptPort) {
                loadSentHashes(); // This clears the Set and loads hashes for the new port
            }
            stateChanged = true;
        }
        // Optional: trigger a re-scan if needed after state change
        // if (stateChanged) findAndSendNewCodeBlocks(targetNode || document);
    }
});


// --- MutationObserver Setup ---
const targetNode = document.querySelector(targetNodeSelector);
if (targetNode) {
    console.log("Target node found:", targetNode, "Setting up MutationObserver.");
    const callback = function(mutationsList, observer) {
        let relevantMutationDetected = false;
        for(const mutation of mutationsList) {
             if (mutation.type === 'childList' || mutation.type === 'subtree' || mutation.type === 'characterData') {
                 relevantMutationDetected = true; break;
             }
        }
        if (relevantMutationDetected) {
             clearTimeout(debounceTimer);
             debounceTimer = setTimeout(() => { findAndSendNewCodeBlocks(targetNode); }, DEBOUNCE_DELAY_MS);
        }
    };
    const observer = new MutationObserver(callback);
    const config = { childList: true, subtree: true, characterData: true };
    observer.observe(targetNode, config);
    console.log("MutationObserver observing.");
    // Load initial state FIRST, then check for initial code
    loadInitialExtensionState();
    console.log("Checking for initial code on page load...");
    setTimeout(() => findAndSendNewCodeBlocks(document), 500); // Check after state is likely loaded
} else {
    console.error(`Could not find target node ('${targetNodeSelector}') to observe.`);
    // Still load state even if observer fails, in case manual trigger is added back
    loadInitialExtensionState();
}


// --- Listener for updates from Background Script ---
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'serverProcessingComplete') {
    console.log("CONTENT SCRIPT: Received 'serverProcessingComplete'", message);
    const elementId = message.captureId;
    if (!elementId) { console.warn("Received server response without capture ID."); return false; }
    const codeElement = document.querySelector(`[${HIGHLIGHT_ID_ATTR}="${elementId}"]`);
    if (codeElement) {
      console.log(`Found matching element for ID ${elementId}, applying final highlight state (Success: ${message.success})`);
      applyHighlight(codeElement, message.success ? 'success' : 'error');
    } else { console.warn(`Could not find code element with ID ${elementId} to apply final highlight.`); }
  }
  return false;
});
// --- END OF FILE content.js ---