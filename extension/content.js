console.log("AI Code Capture content script loaded (v3 - Port aware).");

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
    console.log("Attempting to load hashes for session key:", sessionKey); // Debug
    try {
        const storedHashes = sessionStorage.getItem(sessionKey);
        if (storedHashes) {
            sentHashes = new Set(JSON.parse(storedHashes));
            console.log(`Loaded ${sentHashes.size} hashes for port ${serverPort} from sessionStorage.`); // Debug
        } else {
            sentHashes = new Set(); // Start fresh if nothing stored for this port
             console.log(`No hashes found in sessionStorage for port ${serverPort}.`); // Debug
        }
    } catch (e) {
        console.error("Error loading or parsing sent hashes from sessionStorage:", e);
        sentHashes = new Set(); // Reset on error
    }
}

function saveSentHash(hash) {
    if (sentHashes.has(hash)) return; // Don't re-add
    sentHashes.add(hash);
    try {
        sessionStorage.setItem(sessionKey, JSON.stringify(Array.from(sentHashes)));
    } catch (e) {
        console.error("Error saving sent hashes to sessionStorage:", e);
        // If storage fails, we might send duplicates on reload, but better than crashing
    }
}

// --- Highlight Functions ---

function applyHighlight(element, className, captureId) {
    console.log(`Applying ${className} highlight to element ID: ${captureId}`, element); // Debug
    // Remove other highlight classes first
    element.classList.remove(HIGHLIGHT_CLASS, SUCCESS_CLASS, ERROR_CLASS, FADEOUT_CLASS);
    // Add the new class and the ID attribute
    element.classList.add(className);
    element.setAttribute(HIGHLIGHT_ID_ATTR, captureId);
    if(className === HIGHLIGHT_CLASS) element.setAttribute(HIGHLIGHT_STATE_ATTR, 'initial');
    if(className === SUCCESS_CLASS) element.setAttribute(HIGHLIGHT_STATE_ATTR, 'success');
    if(className === ERROR_CLASS) element.setAttribute(HIGHLIGHT_STATE_ATTR, 'error');

}

function removeHighlight(element, delayMs = 0) {
    if (!element) return;
    const captureId = element.getAttribute(HIGHLIGHT_ID_ATTR);
    // console.log(`Removing highlight for element ID: ${captureId} after delay ${delayMs}`); // Debug

    setTimeout(() => {
        if (element) { // Check if element still exists
            element.classList.add(FADEOUT_CLASS); // Start fade-out transition
            // After transition, remove all classes and attributes
             setTimeout(() => {
                 if (element) {
                     element.classList.remove(HIGHLIGHT_CLASS, SUCCESS_CLASS, ERROR_CLASS, FADEOUT_CLASS);
                     element.removeAttribute(HIGHLIGHT_ID_ATTR);
                     element.removeAttribute(HIGHLIGHT_STATE_ATTR);
                     // console.log(`Highlight fully removed for ID: ${captureId}`); // Debug
                 }
             }, FADEOUT_DURATION_MS);
        }
    }, delayMs);
}


// --- Code Processing ---

function processCodeBlock(blockElement) {
    if (!isActivated || !blockElement) return;
    if (blockElement.closest('.user-prompt-container')) {
        // console.log("Skipping code block within user prompt."); // Debug
        return; // Skip blocks that are part of the user's input
    }
    if (blockElement.getAttribute(HIGHLIGHT_ID_ATTR)) {
        // console.log("Skipping already processed/highlighted block:", blockElement); // Debug
        return; // Already processed or being processed
    }

    const codeContent = blockElement.textContent || '';
    const codeHash = simpleHash(codeContent);

    if (sentHashes.has(codeHash)) {
        // console.log("Skipping already sent code block (hash match)."); // Debug
        return; // Skip if already sent in this session for this port
    }

    const captureId = `aicapture-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
    console.log(` -> Found NEW block (ID: ${captureId}, Hash: ${codeHash}). Applying INITIAL highlight & sending...`); // Debug

    applyHighlight(blockElement, HIGHLIGHT_CLASS, captureId);
    saveSentHash(codeHash); // Mark as sent immediately

    // Send to background script
    chrome.runtime.sendMessage({
        action: 'submitCode',
        code: codeContent,
        captureId: captureId // Send ID for mapping back
    }, (response) => {
         if (chrome.runtime.lastError) {
             console.error("Error sending code to background:", chrome.runtime.lastError.message);
              applyHighlight(blockElement, ERROR_CLASS, captureId); // Show error on block
              removeHighlight(blockElement, REMOVAL_DELAY_MS);
         } else {
             // Optional: Handle immediate response from background if needed
             // console.log("Background ack response:", response);
         }
    });
}

function processAllCodeBlocks(targetNode) {
    if (!isActivated) return;
    console.log("Processing turns within target (Activated=" + isActivated + ", Port=" + serverPort + "): ", targetNode); // Debug
    // Target code blocks within model responses more specifically
    const codeBlocks = targetNode.querySelectorAll(
        'ms-chat-turn.model ms-code-block code, ms-prompt-chunk.model ms-code-block code' // Target model responses
    );
    // console.log(`Found ${codeBlocks.length} potential code blocks.`); // Debug
    codeBlocks.forEach(processCodeBlock);
}

// --- Settings Update ---

function updateSettings(newSettings) {
    let settingsChanged = false;
    if (newSettings.isActivated !== undefined && newSettings.isActivated !== isActivated) {
        isActivated = newSettings.isActivated;
        console.log("Activation status updated:", isActivated);
        settingsChanged = true;
        // If activating, maybe trigger a scan?
        if(isActivated) {
            console.log("Re-checking code blocks after activation.");
            processAllCodeBlocks(document);
        }
    }
    if (newSettings.port !== undefined && newSettings.port !== serverPort) {
        serverPort = newSettings.port;
        console.log("Server port updated:", serverPort);
        loadSentHashes(); // Reload hashes for the new port
        settingsChanged = true;
    }
     if (settingsChanged) {
         console.log("Content script settings updated. Current state: Activated=" + isActivated + ", Port=" + serverPort);
     }
}

// --- Initial Load ---
// Request initial settings from background script
chrome.runtime.sendMessage({ action: 'getSettings' }, (response) => {
    if (chrome.runtime.lastError) {
        console.error("Error getting initial settings:", chrome.runtime.lastError.message);
        // Use defaults if background is unavailable on load
        isActivated = DEFAULT_ACTIVATION;
        serverPort = DEFAULT_PORT;
    } else if (response) {
         console.log("Content script initial state:", response); // Debug
        updateSettings(response); // Update local state
    }
     loadSentHashes(); // Load hashes after getting the initial port

    // --- Mutation Observer Setup ---
    // Select the node that contains the chat turns or code blocks
    // This might need adjustment based on AI Studio's structure
    const targetNode = document.querySelector('ms-chat-session') || document.body; // Fallback to body
    if (!targetNode) {
        console.error("AI Code Capture: Target node for MutationObserver not found.");
        return;
    }
     console.log("Target node found: ", targetNode); // Debug

    const config = { childList: true, subtree: true };

    const callback = (mutationList, observer) => {
        if (!isActivated) return; // Don't process if not active
        for (const mutation of mutationList) {
            if (mutation.type === 'childList') {
                mutation.addedNodes.forEach(node => {
                    // Check if the added node itself is or contains a code block
                    if (node.nodeType === Node.ELEMENT_NODE) {
                         // Look for code blocks specifically within model responses
                        const codeBlocks = node.querySelectorAll('ms-chat-turn.model ms-code-block code, ms-prompt-chunk.model ms-code-block code');
                        if(codeBlocks.length > 0) {
                            // console.log("MutationObserver detected added nodes containing code blocks:", node); // Debug
                            codeBlocks.forEach(processCodeBlock);
                        } else if (node.matches && node.matches('ms-chat-turn.model ms-code-block code, ms-prompt-chunk.model ms-code-block code')) {
                             // console.log("MutationObserver detected added code block itself:", node); // Debug
                             processCodeBlock(node);
                        }
                    }
                });
            }
            // We could also observe attribute changes if needed, but childList is primary
        }
    };

    const observer = new MutationObserver(callback);
    try {
        console.log("Setting up MutationObserver."); // Debug
        observer.observe(targetNode, config);
         console.log("MutationObserver observing."); // Debug
    } catch (error) {
        console.error("Failed to start MutationObserver:", error);
    }

    // Initial check in case code is already present
    console.log("Checking for initial code on page load..."); // Debug
    if (isActivated) {
        processAllCodeBlocks(document); // Scan the whole document initially
    } else {
        console.log("Initial check skipped, extension not activated."); // Debug
    }

}); // End of initial settings request


// --- Listen for Messages from Background Script ---
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    // console.log("CONTENT SCRIPT: Received message:", message); // Debug
    if (message.action === 'serverProcessingComplete') {
        console.log("CONTENT SCRIPT: Received 'serverProcessingComplete'", message); // Debug
        const element = document.querySelector(`[${HIGHLIGHT_ID_ATTR}="${message.captureId}"]`);
        if (element) {
            console.log(`Found element ID ${message.captureId}, applying final highlight (Success: ${message.success})`); // Debug
            const finalClass = message.success ? SUCCESS_CLASS : ERROR_CLASS;
            applyHighlight(element, finalClass, message.captureId);
            removeHighlight(element, REMOVAL_DELAY_MS); // Remove highlight after delay
        } else {
            console.warn(`Content Script: Element with capture ID ${message.captureId} not found for final highlight.`);
        }
         // Optional: Send response back to background if needed
         // sendResponse({status: "Highlight updated"});
    } else if (message.action === 'settingsUpdated') {
        console.log("Content Script: Received 'settingsUpdated'", message.newSettings); // Debug
        updateSettings(message.newSettings);
    }
});