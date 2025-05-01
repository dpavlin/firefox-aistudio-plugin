'use strict';

console.log("AI Code Capture content script loaded (v7 - Selector Fix & Debounce).");

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
const DEBOUNCE_DELAY_MS = 750; // Increased delay to be safer

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
            // Ensure it's actually an array before creating a Set
            if (Array.isArray(parsed)) {
                sentHashes = new Set(parsed);
                console.log(`AICapture: Loaded ${sentHashes.size} hashes for port ${serverPort} from sessionStorage.`);
            } else {
                 console.warn(`AICapture: Invalid data in sessionStorage for key ${sessionKey}. Starting fresh.`);
                 sessionStorage.removeItem(sessionKey); // Remove invalid data
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
        // Make sure sessionKey is up-to-date before saving
        sessionKey = `aicapture_sent_hashes_v1_PORT_${serverPort}`;
        sessionStorage.setItem(sessionKey, JSON.stringify(Array.from(sentHashes)));
        // console.log(`AICapture: Saved hash ${hash}. Total hashes for port ${serverPort}: ${sentHashes.size}`);
    } catch (e) {
        console.error("AICapture: Error saving sent hashes to sessionStorage:", e);
        // If storage fails, we might send duplicates on reload, but better than crashing
    }
}

// --- Highlight Functions ---

function applyHighlight(element, className, captureId) {
    if (!element) return;
    console.log(`AICapture: Applying ${className} highlight to element ID: ${captureId}`, element);
    // Remove other highlight classes first
    element.classList.remove(HIGHLIGHT_CLASS, SUCCESS_CLASS, ERROR_CLASS, FADEOUT_CLASS);
    // Add the new class and the ID attribute
    element.classList.add(className);
    element.setAttribute(HIGHLIGHT_ID_ATTR, captureId);
    if (className === HIGHLIGHT_CLASS) element.setAttribute(HIGHLIGHT_STATE_ATTR, 'initial');
    if (className === SUCCESS_CLASS) element.setAttribute(HIGHLIGHT_STATE_ATTR, 'success');
    if (className === ERROR_CLASS) element.setAttribute(HIGHLIGHT_STATE_ATTR, 'error');
}

function removeHighlight(element, delayMs = 0) {
    if (!element) return;
    const captureId = element.getAttribute(HIGHLIGHT_ID_ATTR);
    // console.log(`AICapture: Scheduling highlight removal for element ID: ${captureId} after delay ${delayMs}`);

    setTimeout(() => {
        if (element) { // Check if element still exists and hasn't been re-highlighted
             const currentState = element.getAttribute(HIGHLIGHT_STATE_ATTR);
             // Only fade out if it's still in a final state (success/error)
            if (currentState === 'success' || currentState === 'error') {
                 element.classList.add(FADEOUT_CLASS); // Start fade-out transition
                 // After transition, remove all classes and attributes
                 setTimeout(() => {
                     if (element && element.classList.contains(FADEOUT_CLASS)) { // Check if it's still fading out
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
    // Skip blocks within user input areas (heuristic, might need adjustment)
    if (blockElement.closest('.user-prompt-container')) {
        // console.log("AICapture: Skipping code block within user prompt.");
        return;
    }
    // Skip blocks already processed or actively being processed
    if (blockElement.hasAttribute(HIGHLIGHT_ID_ATTR)) {
        // console.log("AICapture: Skipping already processed/highlighted block:", blockElement);
        return;
    }
    // Check if the block contains the required @@FILENAME@@ marker *at the start*
    const codeContent = blockElement.textContent || '';
    const trimmedContent = codeContent.trimStart(); // Remove leading whitespace only
    const markerRegex = /^\s*(?:\/\/|#)\s*@@FILENAME@@/i; // Match marker at the beginning

    if (!markerRegex.test(trimmedContent)) {
        // console.log("AICapture: Skipping block without marker.", blockElement);
        return; // Skip blocks that don't start with the marker
    }

    const codeHash = simpleHash(codeContent); // Hash the *full* original content

    if (sentHashes.has(codeHash)) {
        // console.log("AICapture: Skipping already sent code block (hash match).");
        return;
    }

    const captureId = `aicapture-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
    console.log(`AICapture: Found NEW block (ID: ${captureId}, Hash: ${codeHash}). Applying INITIAL highlight & sending...`);

    applyHighlight(blockElement, HIGHLIGHT_CLASS, captureId);
    saveSentHash(codeHash); // Mark as sent immediately for this session/port

    // Send to background script
    browser.runtime.sendMessage({
        action: 'submitCode',
        data: codeContent, // Send the full code content
        captureId: captureId // Send ID for mapping back
    })
    .then(response => {
        console.log("AICapture: Received response from background for " + captureId + ": ", response); // Debug
        if (!response) {
            console.error("AICapture: Received empty response from background for " + captureId);
            applyHighlight(blockElement, ERROR_CLASS, captureId);
            removeHighlight(blockElement, REMOVAL_DELAY_MS);
            return;
        }

        // Handle response and update highlight (Now expecting {success: boolean, details: {...}})
        const finalClass = response.success ? SUCCESS_CLASS : ERROR_CLASS;
        applyHighlight(blockElement, finalClass, captureId);
        removeHighlight(blockElement, REMOVAL_DELAY_MS); // Remove highlight after delay

        if (!response.success) {
             console.error("AICapture: Server/Background reported error for " + captureId + ":", response.details?.message || response.details || 'Unknown error');
        }
    })
    .catch(error => {
         console.error(`AICapture: Error sending 'submitCode' message or processing response for ${captureId}:`, error);
         // Apply error highlight directly if sending failed
         applyHighlight(blockElement, ERROR_CLASS, captureId);
         removeHighlight(blockElement, REMOVAL_DELAY_MS);
     });
}

// Scans the targetNode (or document) for relevant code blocks and processes them
function processAllCodeBlocks(targetNode) {
    if (!isActivated || !targetNode) return;
    console.log("AICapture: processAllCodeBlocks running...");

    // *** UPDATED SELECTOR *** targeting the div containing model class, then descendants
    const selector = 'div.chat-turn-container.model ms-code-block code';
    const codeBlocks = targetNode.querySelectorAll(selector);

    console.log(`AICapture: Found ${codeBlocks.length} potential code blocks with selector "${selector}".`);
    if (codeBlocks.length === 0 && targetNode === document) {
        // If initial scan finds nothing, maybe try the older selector once as fallback?
        // Or log a more specific warning. Let's just log for now.
        console.warn(`AICapture: No code blocks found with primary selector. Structure might have changed.`);
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
            // Optional: Introduce a small delay before processing to let UI settle
            setTimeout(() => processAllCodeBlocks(document), 250);
        }
    }
    if (newSettings.port !== undefined && newSettings.port !== serverPort) {
        serverPort = newSettings.port;
        console.log("AICapture: Server port updated:", serverPort);
        loadSentHashes(); // Reload hashes for the new port
        settingsChanged = true;
    }
     if (settingsChanged) {
         console.log("AICapture: Content script settings updated. Current state: Activated=" + isActivated + ", Port=" + serverPort);
     }
}

// --- Initial Load and Observer Setup ---

function initialize() {
    console.log("AICapture: Initializing...");
    // Request initial settings from background script
    browser.runtime.sendMessage({ action: 'getSettings' })
        .then(response => {
            if (response) {
                 console.log("AICapture: Received initial settings:", response);
                 updateSettings(response);
            } else {
                 console.warn("AICapture: No initial settings received from background, using defaults.");
                 isActivated = true; // Default activation
                 serverPort = 5000; // Default port
            }
            loadSentHashes(); // Load hashes *after* getting the initial port

             // --- Mutation Observer Setup ---
            const targetNode = document.querySelector('ms-chat-session') || document.body; // Monitor chat session or fallback to body
            if (!targetNode) {
                console.error("AICapture: Target node for MutationObserver not found.");
                return;
            }
             console.log("AICapture: Target node found: ", targetNode);

            const config = { childList: true, subtree: true };

            const callback = (mutationList, observer) => {
                 // Check if still activated on mutation
                 if (!isActivated) return;

                 // Use debouncing to avoid rapid processing during streaming
                 clearTimeout(debounceTimeout);
                 console.log("AICapture: Mutation detected, setting debounce timer..."); // Debug
                 debounceTimeout = setTimeout(() => {
                    console.log("AICapture: Debounce timer fired, running processAllCodeBlocks."); // Debug
                     processAllCodeBlocks(targetNode); // Process blocks within the target area after debounce
                 }, DEBOUNCE_DELAY_MS);
            };

            const observer = new MutationObserver(callback);
            try {
                 console.log("AICapture: Setting up MutationObserver.");
                 observer.observe(targetNode, config);
                 console.log("AICapture: MutationObserver observing.");
            } catch (error) {
                 console.error("AICapture: Failed to start MutationObserver:", error);
            }

            // Initial check after a small delay for page elements to render
            console.log("AICapture: Scheduling initial check...");
            setTimeout(() => {
                 console.log("AICapture: Running initial check.");
                 if (isActivated) {
                      processAllCodeBlocks(document); // Scan the whole document initially
                 } else {
                      console.log("AICapture: Initial check skipped, extension not activated.");
                 }
             }, 1500); // Delay initial check slightly more

        })
        .catch(error => {
            console.error("AICapture: Error getting initial settings:", error.message);
            // Use defaults if background is unavailable on load
            isActivated = true;
            serverPort = 5000;
             loadSentHashes(); // Load with default port
            // Still try to set up observer
             initializeObserver(); // TODO: Refactor observer setup into a function if needed here
        });
}


// --- Listen for Messages from Background Script ---
browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
    // console.log("AICapture: Received message:", message); // Can be noisy, enable if needed

    // The 'submitCode' action response is now handled within the .then() of the sendMessage call in processCodeBlock

    if (message.action === 'settingsUpdated') {
        console.log("AICapture: Received 'settingsUpdated'", message.newSettings);
        updateSettings(message.newSettings);
    } else if (message.action === 'serverProcessingComplete') {
         // This handler might be redundant now as the response is handled in the processCodeBlock promise chain.
         // Keep it for now as a fallback or for potential future use cases.
         console.warn("AICapture: Received unexpected 'serverProcessingComplete' message directly (should be handled by originating promise).");
         const element = document.querySelector(`[${HIGHLIGHT_ID_ATTR}="${message.captureId}"]`);
         if (element) {
             const finalClass = message.success ? SUCCESS_CLASS : ERROR_CLASS;
             applyHighlight(element, finalClass, message.captureId);
             removeHighlight(element, REMOVAL_DELAY_MS);
         }
    }

    // Indicate sync processing or that no async response is needed from this top-level listener
    // unless specifically required for a message type not handled above.
    return false;
});

// --- Start Initialization ---
initialize();

// @@FILENAME@@ extension/content.js