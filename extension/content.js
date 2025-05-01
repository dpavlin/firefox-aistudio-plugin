'use strict';

console.log("AI Code Capture content script loaded (v8 - Increased Debounce).");

let isActivated = false;
let serverPort = 5000; // Default, will be updated
const HIGHLIGHT_CLASS = 'aicapture-highlight';
const SUCCESS_CLASS = 'aicapture-success';
const ERROR_CLASS = 'aicapture-error';
const FADEOUT_CLASS = 'aicapture-fadeout';
const HIGHLIGHT_ID_ATTR = 'data-aicapture-id';
const HIGHLIGHT_STATE_ATTR = 'data-aicapture-state'; // 'initial', 'success', 'error'
const FADEOUT_DURATION_MS = 600; // Duration for fade-out effect
const REMOVAL_DELAY_MS = 5000; // How long to keep success/error highlight before removing

// Debounce timer
let debounceTimeout;
// *** INCREASED DEBOUNCE DELAY ***
const DEBOUNCE_DELAY_MS = 2000; // Increased from 750ms to 2 seconds

// Session storage key for sent hashes (port-specific)
let sessionKey = `aicapture_sent_hashes_v1_PORT_${serverPort}`;
let sentHashes = new Set(); // Holds hashes of code blocks already sent in this session for this port


// --- Hash and Storage Functions ---

function simpleHash(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = (hash << 5) - hash + char;
        hash |= 0; // Convert to 32bit integer
    }
    return hash;
}

function loadSentHashes() {
    sessionKey = `aicapture_sent_hashes_v1_PORT_${serverPort}`; // Update key based on current port
    sentHashes.clear(); // Clear existing hashes before loading for the new port
    console.log("AICapture: Attempting to load hashes for session key:", sessionKey);
    try {
        const storedHashes = sessionStorage.getItem(sessionKey);
        if (storedHashes) {
            const parsed = JSON.parse(storedHashes);
            if (Array.isArray(parsed)) {
                sentHashes = new Set(parsed);
                console.log(`AICapture: Loaded ${sentHashes.size} hashes for port ${serverPort} from sessionStorage.`);
            } else {
                 console.warn(`AICapture: Invalid data in sessionStorage for key ${sessionKey}. Starting fresh.`);
                 sessionStorage.removeItem(sessionKey);
                 sentHashes = new Set();
            }
        } else {
            sentHashes = new Set();
             console.log(`AICapture: No hashes found in sessionStorage for port ${serverPort}.`);
        }
    } catch (e) {
        console.error("AICapture: Error loading or parsing sent hashes from sessionStorage:", e);
        sentHashes = new Set(); // Reset on error
    }
}

function saveSentHash(hash) {
    if (sentHashes.has(hash)) return; // Don't re-add
    sentHashes.add(hash);
    try {
        sessionKey = `aicapture_sent_hashes_v1_PORT_${serverPort}`;
        sessionStorage.setItem(sessionKey, JSON.stringify(Array.from(sentHashes)));
    } catch (e) {
        console.error("AICapture: Error saving sent hashes to sessionStorage:", e);
    }
}

// --- Highlight Functions ---

function applyHighlight(element, className, captureId) {
    if (!element) return;
    console.log(`AICapture: Applying ${className} highlight to element ID: ${captureId}`, element);
    element.classList.remove(HIGHLIGHT_CLASS, SUCCESS_CLASS, ERROR_CLASS, FADEOUT_CLASS);
    element.classList.add(className);
    element.setAttribute(HIGHLIGHT_ID_ATTR, captureId);
    if (className === HIGHLIGHT_CLASS) element.setAttribute(HIGHLIGHT_STATE_ATTR, 'initial');
    if (className === SUCCESS_CLASS) element.setAttribute(HIGHLIGHT_STATE_ATTR, 'success');
    if (className === ERROR_CLASS) element.setAttribute(HIGHLIGHT_STATE_ATTR, 'error');
}

function removeHighlight(element, delayMs = 0) {
    if (!element) return;
    const captureId = element.getAttribute(HIGHLIGHT_ID_ATTR);

    setTimeout(() => {
        if (element) {
             const currentState = element.getAttribute(HIGHLIGHT_STATE_ATTR);
            if (currentState === 'success' || currentState === 'error') {
                 element.classList.add(FADEOUT_CLASS);
                 setTimeout(() => {
                     if (element && element.classList.contains(FADEOUT_CLASS)) {
                         element.classList.remove(HIGHLIGHT_CLASS, SUCCESS_CLASS, ERROR_CLASS, FADEOUT_CLASS);
                         element.removeAttribute(HIGHLIGHT_ID_ATTR);
                         element.removeAttribute(HIGHLIGHT_STATE_ATTR);
                          console.log(`AICapture: Highlight fully removed for ID: ${captureId}`);
                     }
                 }, FADEOUT_DURATION_MS);
            }
        }
    }, delayMs);
}


// --- Code Processing ---

function processCodeBlock(blockElement) {
    if (!isActivated || !blockElement) return;
    if (blockElement.closest('.user-prompt-container')) {
        return;
    }
    if (blockElement.hasAttribute(HIGHLIGHT_ID_ATTR)) {
        return;
    }
    const codeContent = blockElement.textContent || '';
    const trimmedContent = codeContent.trimStart();
    const markerRegex = /^\s*(?:\/\/|#)\s*@@FILENAME@@/i;

    if (!markerRegex.test(trimmedContent)) {
        return;
    }

    const codeHash = simpleHash(codeContent);

    if (sentHashes.has(codeHash)) {
        return;
    }

    const captureId = `aicapture-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
    console.log(`AICapture: Found NEW block (ID: ${captureId}, Hash: ${codeHash}). Applying INITIAL highlight & sending...`);

    applyHighlight(blockElement, HIGHLIGHT_CLASS, captureId);
    saveSentHash(codeHash);

    browser.runtime.sendMessage({
        action: 'submitCode',
        data: codeContent,
        captureId: captureId
    })
    .then(response => {
        console.log("AICapture: Received response from background for " + captureId + ": ", response);
        const currentElement = document.querySelector(`[${HIGHLIGHT_ID_ATTR}="${captureId}"]`); // Re-query in case DOM changed
        if (!currentElement) {
             console.warn("AICapture: Element for " + captureId + " disappeared before processing response.");
             return;
        }
        if (!response) {
            console.error("AICapture: Received empty response from background for " + captureId);
            applyHighlight(currentElement, ERROR_CLASS, captureId);
            removeHighlight(currentElement, REMOVAL_DELAY_MS);
            return;
        }

        const finalClass = response.success ? SUCCESS_CLASS : ERROR_CLASS;
        applyHighlight(currentElement, finalClass, captureId);
        removeHighlight(currentElement, REMOVAL_DELAY_MS);

        if (!response.success) {
             console.error("AICapture: Server/Background reported error for " + captureId + ":", response.details?.message || response.details || 'Unknown error');
        }
    })
    .catch(error => {
         console.error(`AICapture: Error sending 'submitCode' message or processing response for ${captureId}:`, error);
         const currentElement = document.querySelector(`[${HIGHLIGHT_ID_ATTR}="${captureId}"]`);
         if (currentElement) {
             applyHighlight(currentElement, ERROR_CLASS, captureId);
             removeHighlight(currentElement, REMOVAL_DELAY_MS);
         }
     });
}

function processAllCodeBlocks(targetNode) {
    if (!isActivated || !targetNode) return;
    // console.log("AICapture: processAllCodeBlocks running..."); // Less noisy logging

    const selector = 'div.chat-turn-container.model ms-code-block code';
    const codeBlocks = targetNode.querySelectorAll(selector);

    // console.log(`AICapture: Found ${codeBlocks.length} potential code blocks with selector "${selector}".`); // Less noisy
    if (codeBlocks.length === 0 && targetNode === document) {
        // console.warn(`AICapture: No code blocks found with primary selector. Structure might have changed.`); // Less noisy
    }

    codeBlocks.forEach(processCodeBlock);
}

// --- Settings Update ---

function updateSettings(newSettings) {
    let settingsChanged = false;
    if (newSettings.isActivated !== undefined && newSettings.isActivated !== isActivated) {
        isActivated = newSettings.isActivated;
        console.log("AICapture: Activation status updated:", isActivated);
        settingsChanged = true;
        if (isActivated) {
            console.log("AICapture: Re-checking code blocks after activation.");
            setTimeout(() => processAllCodeBlocks(document), 250);
        }
    }
    if (newSettings.port !== undefined && newSettings.port !== serverPort) {
        serverPort = newSettings.port;
        console.log("AICapture: Server port updated:", serverPort);
        loadSentHashes();
        settingsChanged = true;
    }
     if (settingsChanged) {
         console.log("AICapture: Content script settings updated. Current state: Activated=" + isActivated + ", Port=" + serverPort);
     }
}

// --- Initial Load and Observer Setup ---

function initialize() {
    console.log("AICapture: Initializing...");
    browser.runtime.sendMessage({ action: 'getSettings' })
        .then(response => {
            if (response) {
                 console.log("AICapture: Received initial settings:", response);
                 updateSettings(response);
            } else {
                 console.warn("AICapture: No initial settings received, using defaults.");
                 isActivated = true; serverPort = 5000;
            }
            loadSentHashes();

            const targetNode = document.querySelector('ms-chat-session') || document.body;
            if (!targetNode) {
                console.error("AICapture: Target node for MutationObserver not found.");
                return;
            }
             console.log("AICapture: Target node found: ", targetNode);

            const config = { childList: true, subtree: true };

            const callback = (mutationList, observer) => {
                 if (!isActivated) return;
                 clearTimeout(debounceTimeout);
                 // console.log("AICapture: Mutation detected, setting debounce timer..."); // Less noisy
                 debounceTimeout = setTimeout(() => {
                    // console.log("AICapture: Debounce timer fired, running processAllCodeBlocks."); // Less noisy
                     processAllCodeBlocks(targetNode);
                 }, DEBOUNCE_DELAY_MS); // Use the increased delay
            };

            const observer = new MutationObserver(callback);
            try {
                 console.log("AICapture: Setting up MutationObserver.");
                 observer.observe(targetNode, config);
                 console.log("AICapture: MutationObserver observing.");
            } catch (error) {
                 console.error("AICapture: Failed to start MutationObserver:", error);
            }

            console.log("AICapture: Scheduling initial check...");
            setTimeout(() => {
                 console.log("AICapture: Running initial check.");
                 if (isActivated) { processAllCodeBlocks(document); }
                 else { console.log("AICapture: Initial check skipped, extension not activated."); }
             }, 1500);

        })
        .catch(error => {
            console.error("AICapture: Error getting initial settings:", error.message);
            isActivated = true; serverPort = 5000;
             loadSentHashes();
             // Maybe still try to setup observer? Less critical if settings failed.
             // initializeObserver();
        });
}


// --- Listen for Messages from Background Script ---
browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'settingsUpdated') {
        console.log("AICapture: Received 'settingsUpdated'", message.newSettings);
        updateSettings(message.newSettings);
    } else if (message.action === 'serverProcessingComplete') {
         // This path should ideally not be hit frequently now
         console.warn("AICapture: Received unexpected 'serverProcessingComplete' message directly.");
         const element = document.querySelector(`[${HIGHLIGHT_ID_ATTR}="${message.captureId}"]`);
         if (element) {
             const finalClass = message.success ? SUCCESS_CLASS : ERROR_CLASS;
             applyHighlight(element, finalClass, message.captureId);
             removeHighlight(element, REMOVAL_DELAY_MS);
         }
    }
    return false;
});

// --- Start Initialization ---
initialize();

// @@FILENAME@@ extension/content.js