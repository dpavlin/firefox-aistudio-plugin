// @@FILENAME@@ content.js
console.log("AI Code Capture content script loaded (v2 - Port aware).");

// --- Storage Keys & Default Port ---
const ACTIVATION_STORAGE_KEY = 'isActivated';
const PORT_STORAGE_KEY = 'serverPort';
const DEFAULT_PORT = 5000;
let contentScriptPort = DEFAULT_PORT; // Store port for this instance

// --- Session Storage Key (Dynamic based on port) ---
let SESSION_STORAGE_KEY = `aicapture_sent_hashes_v1_PORT_${contentScriptPort}`;

// --- Global State ---
let isExtensionActivated = true; // Assume active until loaded from storage
const sentCodeBlockHashes = new Set(); // Stores hashes for the *current port's* session

// --- CSS Selectors & Highlight ---
const targetNodeSelector = 'ms-chat-session ms-autoscroll-container > div';
const codeElementSelector = 'ms-code-block pre code';
const modelTurnSelector = 'ms-chat-turn:has(div.chat-turn-container.model)';
const HIGHLIGHT_INITIAL_CLASS = 'aicapture-highlight'; // Renamed for clarity
const HIGHLIGHT_SUCCESS_CLASS = 'aicapture-success';
const HIGHLIGHT_ERROR_CLASS = 'aicapture-error';
const HIGHLIGHT_FADEOUT_CLASS = 'aicapture-fadeout';
const HIGHLIGHT_FINAL_DURATION_MS = 3000;
const HIGHLIGHT_FADEOUT_DELAY_MS = 2500; // Start fade slightly before removing
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
    SESSION_STORAGE_KEY = `aicapture_sent_hashes_v1_PORT_${contentScriptPort}`; // Update key based on current port
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
        // Clear potentially corrupted data
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


// --- Highlight Helper ---
function applyHighlight(element, state = 'initial') {
    if (!element) return;

    const existingTimers = highlightTimers.get(element);
    if (existingTimers) {
        clearTimeout(existingTimers.initialTimer);
        clearTimeout(existingTimers.finalTimer);
        clearTimeout(existingTimers.fadeTimer);
    }

    console.log(`Applying ${state} highlight to element with ID: ${element.getAttribute(HIGHLIGHT_ID_ATTR)}`, element);

    // Remove all potentially existing highlight classes first
    element.classList.remove(HIGHLIGHT_INITIAL_CLASS, HIGHLIGHT_SUCCESS_CLASS, HIGHLIGHT_ERROR_CLASS, HIGHLIGHT_FADEOUT_CLASS);

    let initialTimerId = null;
    let finalTimerId = null;
    let fadeTimerId = null;

    switch (state) {
        case 'initial':
            element.classList.add(HIGHLIGHT_INITIAL_CLASS);
            // Longer initial timeout to allow for processing
            initialTimerId = setTimeout(() => {
                 console.log(`Initial highlight timeout for ID: ${element.getAttribute(HIGHLIGHT_ID_ATTR)}`);
                 // Don't remove initial if a final state is pending or applied
                 if (!element.classList.contains(HIGHLIGHT_SUCCESS_CLASS) && !element.classList.contains(HIGHLIGHT_ERROR_CLASS)) {
                    element.classList.remove(HIGHLIGHT_INITIAL_CLASS);
                 }
                 // Don't delete from map here, wait for final state or separate cleanup
            }, HIGHLIGHT_FINAL_DURATION_MS * 3); // e.g., 9 seconds
            break;
        case 'success':
            element.classList.add(HIGHLIGHT_SUCCESS_CLASS);
            fadeTimerId = setTimeout(() => element.classList.add(HIGHLIGHT_FADEOUT_CLASS), HIGHLIGHT_FADEOUT_DELAY_MS);
            finalTimerId = setTimeout(() => {
                console.log(`Removing final success highlight for ID: ${element.getAttribute(HIGHLIGHT_ID_ATTR)}`);
                element.classList.remove(HIGHLIGHT_SUCCESS_CLASS, HIGHLIGHT_FADEOUT_CLASS);
                highlightTimers.delete(element);
                element.removeAttribute(HIGHLIGHT_ID_ATTR); // Clean up ID
            }, HIGHLIGHT_FINAL_DURATION_MS);
            break;
        case 'error':
            element.classList.add(HIGHLIGHT_ERROR_CLASS);
             fadeTimerId = setTimeout(() => element.classList.add(HIGHLIGHT_FADEOUT_CLASS), HIGHLIGHT_FADEOUT_DELAY_MS);
            finalTimerId = setTimeout(() => {
                 console.log(`Removing final error highlight for ID: ${element.getAttribute(HIGHLIGHT_ID_ATTR)}`);
                element.classList.remove(HIGHLIGHT_ERROR_CLASS, HIGHLIGHT_FADEOUT_CLASS);
                highlightTimers.delete(element);
                element.removeAttribute(HIGHLIGHT_ID_ATTR); // Clean up ID
            }, HIGHLIGHT_FINAL_DURATION_MS);
            break;
        case 'remove': // Explicitly remove any highlight and tracking
            element.classList.remove(HIGHLIGHT_INITIAL_CLASS, HIGHLIGHT_SUCCESS_CLASS, HIGHLIGHT_ERROR_CLASS, HIGHLIGHT_FADEOUT_CLASS);
            highlightTimers.delete(element);
            element.removeAttribute(HIGHLIGHT_ID_ATTR);
             console.log(`Explicitly removed highlight for element`, element);
            break;
    }

    // Store timer IDs only if a timed action is set
    if (initialTimerId !== null || finalTimerId !== null || fadeTimerId !== null) {
         highlightTimers.set(element, { initialTimer: initialTimerId, finalTimer: finalTimerId, fadeTimer: fadeTimerId });
    } else if (state === 'remove') {
         highlightTimers.delete(element); // Ensure cleanup if explicitly removed
    }
}

// --- Code Processing Function ---
function findAndSendNewCodeBlocks(target) {
    if (!isExtensionActivated) {
        // console.log("Auto-capture disabled, skipping check.");
        return; // Exit if the extension is disabled
    }
    console.log(`Processing turns within target (Activated=${isExtensionActivated}, Port=${contentScriptPort}):`, target);

    const modelTurns = target.querySelectorAll(modelTurnSelector);
    if (!modelTurns || modelTurns.length === 0) return;

    modelTurns.forEach((turnElement) => {
        const codeElements = turnElement.querySelectorAll(codeElementSelector);
        if (!codeElements || codeElements.length === 0) return;

        codeElements.forEach((codeElement) => {
            // Skip if already highlighted/processed (has our ID)
            if (codeElement.hasAttribute(HIGHLIGHT_ID_ATTR)) {
                 // console.log("Skipping element already being processed:", codeElement);
                 return;
            }

            const capturedCode = codeElement.innerText;
            const trimmedCode = capturedCode?.trim();

            if (trimmedCode?.length > 0) {
                const codeHash = hashCode(capturedCode);

                if (!sentCodeBlockHashes.has(codeHash)) {
                    const uniqueId = `aicapture-${Date.now()}-${highlightCounter++}`;
                    console.log(` -> Found NEW block (ID: ${uniqueId}, Hash: ${codeHash}). Applying INITIAL highlight & sending...`);

                    // Add unique ID for tracking response
                    codeElement.setAttribute(HIGHLIGHT_ID_ATTR, uniqueId);
                    applyHighlight(codeElement, 'initial');

                    // Send message to background script WITH ID
                    chrome.runtime.sendMessage({
                        action: 'sendCodeDirectly',
                        code: capturedCode,
                        captureId: uniqueId // Include the ID
                    }).catch(error => {
                        console.error("Error sending message to background:", error);
                        // If send fails, remove highlight and attribute
                        applyHighlight(codeElement, 'remove');
                    });

                    // Add hash to prevent re-sending in this session for this port
                    sentCodeBlockHashes.add(codeHash);
                    saveSentHashes(); // Update session storage

                    // Optional: Set a long timeout to remove the initial highlight
                    // if no response is ever received from the background/server.
                    // This is handled partially by applyHighlight's initialTimer,
                    // but we could add another layer here if needed.

                } else {
                    // console.log(` -> Hash ${codeHash} already sent for port ${contentScriptPort}. Skipping.`);
                }
            }
        });
    });
    console.log("Finished processing turns.");
}

// --- Function to get initial state from background storage ---
function loadInitialExtensionState() {
    chrome.storage.local.get([ACTIVATION_STORAGE_KEY, PORT_STORAGE_KEY], (result) => {
        if (chrome.runtime.lastError) {
            console.error("Content Script: Error reading initial state:", chrome.runtime.lastError.message);
            // Use defaults on error
            isExtensionActivated = true;
            contentScriptPort = DEFAULT_PORT;
        } else {
            isExtensionActivated = result.isActivated !== undefined ? result.isActivated : true;
            contentScriptPort = result.serverPort !== undefined ? parseInt(result.serverPort, 10) || DEFAULT_PORT : DEFAULT_PORT;
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
            contentScriptPort = parseInt(changes[PORT_STORAGE_KEY].newValue, 10) || DEFAULT_PORT;
            console.log(`Content script detected port change: ${contentScriptPort}`);
            if (oldPort !== contentScriptPort) {
                // Port changed, reload/clear hashes for the new port's session key
                loadSentHashes();
            }
            stateChanged = true;
        }
        // Optionally trigger a re-scan if needed after state change,
        // though MutationObserver might handle this anyway.
        // if (stateChanged && isExtensionActivated) findAndSendNewCodeBlocks(targetNode || document);
    }
});


// --- MutationObserver Setup ---
const targetNode = document.querySelector(targetNodeSelector);
if (targetNode) {
    console.log("Target node found:", targetNode, "Setting up MutationObserver.");
    const callback = function(mutationsList, observer) {
        let relevantMutationDetected = false;
        for(const mutation of mutationsList) {
             // Simplified check: any childList or subtree change triggers debounce
             if (mutation.type === 'childList' || mutation.type === 'subtree' || mutation.type === 'characterData') {
                 relevantMutationDetected = true; break;
             }
        }
        if (relevantMutationDetected) {
             // console.log("Relevant mutation detected, scheduling code check.");
             clearTimeout(debounceTimer);
             debounceTimer = setTimeout(() => {
                if (isExtensionActivated) { // Double-check activation before running
                    console.log("MutationObserver running findAndSendNewCodeBlocks after debounce.");
                    findAndSendNewCodeBlocks(targetNode);
                } else {
                    // console.log("MutationObserver debounce fired, but extension is disabled.");
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
    // Check after a short delay to allow state loading and initial rendering
    setTimeout(() => {
        if (isExtensionActivated && targetNode) { // Check activation again
            findAndSendNewCodeBlocks(document);
        } else if (!targetNode) {
            console.error("Target node disappeared before initial check?");
        } else {
            console.log("Initial check skipped, extension not activated.");
        }
    }, 500);

} else {
    console.error(`Could not find target node ('${targetNodeSelector}') to observe.`);
    // Still load state even if observer fails
    loadInitialExtensionState();
}


// --- Listener for updates from Background Script ---
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'serverProcessingComplete') {
    console.log("CONTENT SCRIPT: Received 'serverProcessingComplete'", message);
    const elementId = message.captureId; // Use the unique ID
    if (!elementId) {
        console.warn("Received server response without capture ID. Cannot update highlight state.");
        return false;
    }
    // Find the specific element that was processed
    const codeElement = document.querySelector(`[${HIGHLIGHT_ID_ATTR}="${elementId}"]`);
    if (codeElement) {
      console.log(`Found matching element for ID ${elementId}, applying final highlight state (Success: ${message.success})`);
      // Update the highlight based on success/failure
      applyHighlight(codeElement, message.success ? 'success' : 'error');
    } else {
        console.warn(`Could not find code element with ID ${elementId} to apply final highlight.`);
    }
  }
  return false; // No async response needed here
});