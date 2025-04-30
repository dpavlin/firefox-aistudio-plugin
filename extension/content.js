console.log("AI Code Capture content script loaded (v3 - Port aware).");

// --- Storage Keys & Default Port ---
const ACTIVATION_STORAGE_KEY = 'isActivated';
const PORT_STORAGE_KEY = 'serverPort'; // Default port key
const DEFAULT_PORT = 5000;
let contentScriptPort = DEFAULT_PORT; // Store *default* port initially

// --- Session Storage Key (Now Dynamic based on ACTUAL port used for sending) ---
// We re-calculate this key just before adding a hash, using the *current* port setting
// let SESSION_STORAGE_KEY = `aicapture_sent_hashes_v1_PORT_${contentScriptPort}`; // Initial value based on default

// --- Global State ---
let isExtensionActivated = true; // Assume active until loaded from storage
const sentCodeBlockHashes = new Set(); // Stores hashes for the *current port's* session

// --- CSS Selectors & Highlight ---
const targetNodeSelector = 'ms-chat-session ms-autoscroll-container > div';
const codeElementSelector = 'ms-code-block pre code';
const modelTurnSelector = 'ms-chat-turn:has(div.chat-turn-container.model)';
const HIGHLIGHT_INITIAL_CLASS = 'aicapture-highlight'; // Use the original class name
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

// --- Simple String Hash Function ---
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

// --- Function to load sent hashes from PORT-SPECIFIC sessionStorage ---
function loadSentHashes() {
    sentCodeBlockHashes.clear(); // Clear previous hashes
    // **Crucially, get the current port setting from storage to build the key**
    chrome.storage.local.get(PORT_STORAGE_KEY, (result) => {
        contentScriptPort = result.serverPort !== undefined ? parseInt(result.serverPort, 10) || DEFAULT_PORT : DEFAULT_PORT;
        SESSION_STORAGE_KEY = `aicapture_sent_hashes_v1_PORT_${contentScriptPort}`;
        console.log(`Attempting to load hashes for session key: ${SESSION_STORAGE_KEY}`);
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
    });
}

// --- Function to save sent hashes to PORT-SPECIFIC sessionStorage ---
// Uses the dynamically updated SESSION_STORAGE_KEY
function saveSentHashes() {
    try {
        // Use the SESSION_STORAGE_KEY that was set based on the current port during load/change
        const hashesArray = Array.from(sentCodeBlockHashes);
        sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(hashesArray));
        // console.log(`Saved ${hashesArray.length} hashes to ${SESSION_STORAGE_KEY}`);
    } catch (e) {
        console.error(`Error saving hashes to sessionStorage (${SESSION_STORAGE_KEY}):`, e);
    }
}


// --- Highlight Helper --- (Unchanged)
function applyHighlight(element, state = 'initial') {
    if (!element) return;
    const existingTimers = highlightTimers.get(element);
    if (existingTimers) { clearTimeout(existingTimers.initialTimer); clearTimeout(existingTimers.finalTimer); clearTimeout(existingTimers.fadeTimer); }
    const currentId = element.getAttribute(HIGHLIGHT_ID_ATTR); // Get ID for logging
    console.log(`Applying ${state} highlight to element ID: ${currentId}`, element);
    element.classList.remove(HIGHLIGHT_INITIAL_CLASS, HIGHLIGHT_SUCCESS_CLASS, HIGHLIGHT_ERROR_CLASS, HIGHLIGHT_FADEOUT_CLASS);
    let initialTimerId = null, finalTimerId = null, fadeTimerId = null;
    switch (state) {
      case 'initial':
        element.classList.add(HIGHLIGHT_INITIAL_CLASS);
        initialTimerId = setTimeout(() => {
             // console.log(`Initial highlight timeout for ID: ${currentId}`);
             if (!element.classList.contains(HIGHLIGHT_SUCCESS_CLASS) && !element.classList.contains(HIGHLIGHT_ERROR_CLASS)) { element.classList.remove(HIGHLIGHT_INITIAL_CLASS); }
        }, HIGHLIGHT_FINAL_DURATION_MS * 3); break;
      case 'success':
        element.classList.add(HIGHLIGHT_SUCCESS_CLASS);
        fadeTimerId = setTimeout(() => element.classList.add(HIGHLIGHT_FADEOUT_CLASS), HIGHLIGHT_FADEOUT_DELAY_MS);
        finalTimerId = setTimeout(() => { element.classList.remove(HIGHLIGHT_SUCCESS_CLASS, HIGHLIGHT_FADEOUT_CLASS); highlightTimers.delete(element); element.removeAttribute(HIGHLIGHT_ID_ATTR); }, HIGHLIGHT_FINAL_DURATION_MS); break;
      case 'error':
        element.classList.add(HIGHLIGHT_ERROR_CLASS);
         fadeTimerId = setTimeout(() => element.classList.add(HIGHLIGHT_FADEOUT_CLASS), HIGHLIGHT_FADEOUT_DELAY_MS);
        finalTimerId = setTimeout(() => { element.classList.remove(HIGHLIGHT_ERROR_CLASS, HIGHLIGHT_FADEOUT_CLASS); highlightTimers.delete(element); element.removeAttribute(HIGHLIGHT_ID_ATTR); }, HIGHLIGHT_FINAL_DURATION_MS); break;
      case 'remove':
        element.classList.remove(HIGHLIGHT_INITIAL_CLASS, HIGHLIGHT_SUCCESS_CLASS, HIGHLIGHT_ERROR_CLASS, HIGHLIGHT_FADEOUT_CLASS);
        highlightTimers.delete(element); element.removeAttribute(HIGHLIGHT_ID_ATTR); console.log(`Explicitly removed highlight for element`, element); break;
    }
    if (state !== 'remove') { highlightTimers.set(element, { initialTimer: initialTimerId, finalTimer: finalTimerId, fadeTimer: fadeTimerId }); }
    else { highlightTimers.delete(element); }
}

// --- Code Processing Function ---
function findAndSendNewCodeBlocks(target) {
    if (!isExtensionActivated) { return; } // Check global state first
    console.log(`Processing turns within target (Activated=${isExtensionActivated}, Port=${contentScriptPort}):`, target);

    const modelTurns = target.querySelectorAll(modelTurnSelector);
    if (!modelTurns || modelTurns.length === 0) return;

    modelTurns.forEach((turnElement) => {
        const codeElements = turnElement.querySelectorAll(codeElementSelector);
        if (!codeElements || codeElements.length === 0) return;

        codeElements.forEach((codeElement) => {
            if (codeElement.hasAttribute(HIGHLIGHT_ID_ATTR)) { return; } // Skip already processing

            const capturedCode = codeElement.innerText;
            const trimmedCode = capturedCode?.trim();

            if (trimmedCode?.length > 0) {
                const codeHash = hashCode(capturedCode);
                const currentPortSpecificKey = `aicapture_sent_hashes_v1_PORT_${contentScriptPort}`; // Get current key

                // Check against hashes loaded for the *current* port
                if (!sentCodeBlockHashes.has(codeHash)) {
                    const uniqueId = `aicapture-${Date.now()}-${highlightCounter++}`;
                    console.log(` -> Found NEW block (ID: ${uniqueId}, Hash: ${codeHash}). Applying INITIAL highlight & sending...`);
                    codeElement.setAttribute(HIGHLIGHT_ID_ATTR, uniqueId);
                    applyHighlight(codeElement, 'initial');
                    chrome.runtime.sendMessage({
                        action: 'sendCodeDirectly',
                        code: capturedCode,
                        captureId: uniqueId
                    }).catch(error => {
                        console.error("Error sending message to background:", error);
                        applyHighlight(codeElement, 'remove'); // Remove highlight on send failure
                    });
                    sentCodeBlockHashes.add(codeHash); // Add to current port's set
                    saveSentHashes(); // Update session storage for current port
                } else {
                   // console.log(` -> Hash ${codeHash} already sent for port ${contentScriptPort}. Skipping.`);
                }
            }
        });
    });
    // console.log("Finished processing turns.");
}

// --- Function to get initial state from background storage ---
function loadInitialExtensionState() {
    chrome.storage.local.get([ACTIVATION_STORAGE_KEY, PORT_STORAGE_KEY], (result) => {
        if (chrome.runtime.lastError) {
            console.error("Content Script: Error reading initial state:", chrome.runtime.lastError.message);
            isExtensionActivated = true; // Default on error
            contentScriptPort = DEFAULT_PORT;
        } else {
            isExtensionActivated = result.isActivated !== undefined ? result.isActivated : true;
            contentScriptPort = result.serverPort !== undefined ? parseInt(result.serverPort, 10) || DEFAULT_PORT : DEFAULT_PORT;
        }
        console.log(`Content script initial state: Activated=${isExtensionActivated}, Port=${contentScriptPort}`);
        // Load hashes specific to this initial/default port
        loadSentHashes();
    });
}

// --- Listen for storage changes ---
chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName === 'local') {
        let stateOrPortChanged = false;
        if (changes[ACTIVATION_STORAGE_KEY]) {
            isExtensionActivated = changes[ACTIVATION_STORAGE_KEY].newValue;
            console.log(`Content script updated activation state: ${isExtensionActivated}`);
            stateOrPortChanged = true;
        }
        if (changes[PORT_STORAGE_KEY]) {
            const oldPort = contentScriptPort;
            const newPort = parseInt(changes[PORT_STORAGE_KEY].newValue, 10) || DEFAULT_PORT;
            console.log(`Content script detected default port change in storage: ${newPort}`);
            if (oldPort !== newPort) {
                contentScriptPort = newPort; // Update internal port variable
                // Port changed, reload hashes for the new port's session key
                // This is important for duplicate checking if the user changes the global default
                // and hasn't set a specific port for this tab via the popup yet.
                loadSentHashes();
            }
            stateOrPortChanged = true;
        }
        // Optional: Trigger re-scan only if needed, MutationObserver might be sufficient
        // if (stateOrPortChanged && isExtensionActivated && targetNode) { findAndSendNewCodeBlocks(targetNode); }
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
             debounceTimer = setTimeout(() => {
                if (isExtensionActivated) {
                    // console.log("MutationObserver running findAndSendNewCodeBlocks after debounce.");
                    findAndSendNewCodeBlocks(targetNode);
                }
             }, DEBOUNCE_DELAY_MS);
        }
    };
    const observer = new MutationObserver(callback);
    const config = { childList: true, subtree: true, characterData: true };
    observer.observe(targetNode, config);
    console.log("MutationObserver observing.");

    // Load initial state FIRST
    loadInitialExtensionState();
    console.log("Checking for initial code on page load...");
    // Check after a short delay
    setTimeout(() => {
        if (isExtensionActivated && targetNode) { findAndSendNewCodeBlocks(document); }
        else if (!targetNode) { console.error("Target node disappeared before initial check?"); }
        else { console.log("Initial check skipped, extension not activated."); }
    }, 750); // Slightly longer delay

} else {
    console.error(`Could not find target node ('${targetNodeSelector}') to observe.`);
    loadInitialExtensionState(); // Still load state
}


// --- Listener for updates from Background Script ---
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'serverProcessingComplete') {
    console.log("CONTENT SCRIPT: Received 'serverProcessingComplete'", message);
    const elementId = message.captureId;
    if (!elementId) { console.warn("Received server response without capture ID."); return false; }
    const codeElement = document.querySelector(`[${HIGHLIGHT_ID_ATTR}="${elementId}"]`);
    if (codeElement) {
      console.log(`Found element ID ${elementId}, applying final highlight (Success: ${message.success})`);
      applyHighlight(codeElement, message.success ? 'success' : 'error');
    } else { console.warn(`Could not find element with ID ${elementId} for final highlight.`); }
  }
  return false; // No async response needed here
});