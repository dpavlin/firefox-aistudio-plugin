// @@FILENAME@@ extension/content.js
// Debounce function (assuming it exists)
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

console.log("AI Code Capture: Content script loaded (V4 - Persistent Hashing).");

// --- Configuration ---
const FILENAME_MARKER = '@@FILENAME@@';
const CODE_BLOCK_SELECTOR = 'ms-code-block pre code';
const HIGHLIGHT_TARGET_SELECTOR = 'ms-code-block';
const STABILIZATION_DELAY_MS = 2000;
const OBSERVER_DEBOUNCE_MS = 300;

// --- State ---
// let processedBlocks = new Set(); // REMOVED - Replaced by persistent storage
let stabilizationTimers = new Map(); // Map: blockHash -> timerId

// --- Simple Hashing Function ---
// Basic hash function (not cryptographically secure, but good enough for distinction)
function hashCode(str) {
  let hash = 0;
  if (!str || str.length === 0) return hash;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash |= 0; // Convert to 32bit integer
  }
  // Return as a string to use as object key
  return `hash_${hash}`;
}

// --- Async Helpers for Background Communication ---
async function getStoredStatus(blockHash) {
    try {
        // console.log(`CS: Requesting status for hash: ${blockHash}`);
        const response = await browser.runtime.sendMessage({ action: "getBlockStatus", hash: blockHash });
        // console.log(`CS: Received status for hash ${blockHash}:`, response?.status);
        return response?.status || null; // Return status ('pending', 'sent', 'error') or null
    } catch (error) {
        console.error(`CS: Error getting status for hash ${blockHash}:`, error);
        return null; // Assume unknown on error
    }
}

async function setStoredStatus(blockHash, status) {
    try {
        // console.log(`CS: Setting status for hash ${blockHash} to ${status}`);
        const response = await browser.runtime.sendMessage({ action: "setBlockStatus", hash: blockHash, status: status });
        if (!response?.success) {
             console.error(`CS: Failed to set status for hash ${blockHash} to ${status}`);
        }
    } catch (error) {
        console.error(`CS: Error setting status for hash ${blockHash}:`, error);
    }
}


// --- Core Logic ---

function removeAllHighlights(element) {
    if (element) {
        element.classList.remove(
            'aicapture-highlight', 'aicapture-pending',
            'aicapture-success', 'aicapture-error'
            // No fadeout class anymore
        );
    }
}

// Function called ONLY when stabilization timer completes
async function sendCodeToServer(highlightTarget, codeElement, blockHash) {
    // Check status *again* right before sending, in case something changed
    const currentStatus = await getStoredStatus(blockHash);
    if (!highlightTarget || !codeElement || currentStatus === 'sent' || currentStatus === 'error') {
        console.log(`AICapture: Skipping send for hash ${blockHash} - status is ${currentStatus} or invalid elements.`);
        if(highlightTarget && currentStatus !== 'sent' && currentStatus !== 'error') {
             removeAllHighlights(highlightTarget); // Clean up if status wasn't final
        }
        return;
    }

    const codeContent = codeElement.textContent || '';
    if (!codeContent.trimStart().startsWith(FILENAME_MARKER)) {
        console.log(`AICapture: Skipping send for hash ${blockHash} - marker disappeared.`);
        removeAllHighlights(highlightTarget);
        await setStoredStatus(blockHash, null); // Clear status if marker gone
        return;
    }

    console.log(`AICapture: Stabilization complete. Sending code for hash: ${blockHash}`);
    removeAllHighlights(highlightTarget); // Remove pending
    highlightTarget.classList.add('aicapture-highlight'); // Add processing highlight

    try {
        const response = await browser.runtime.sendMessage({
            action: "submitCode",
            code: codeContent,
            hash: blockHash // Send hash for background storage update
        });

        console.log(`AICapture: Received response from background for hash ${blockHash}:`, response);
        highlightTarget.classList.remove('aicapture-highlight'); // Remove processing highlight

        const success = response && response.success; // Background now returns success boolean directly
        const finalStatus = success ? 'sent' : 'error';
        const finalClass = success ? 'aicapture-success' : 'aicapture-error';

        // Apply final, persistent highlight class
        highlightTarget.classList.add(finalClass);
        // Persist final status
        await setStoredStatus(blockHash, finalStatus);

        if (success) {
            console.log(`AICapture: Highlight success (persistent) for hash ${blockHash}`);
        } else {
            console.error(`AICapture: Highlight error (persistent) for hash ${blockHash}. Response:`, response?.details);
        }

    } catch (error) {
        console.error(`AICapture: Error in sendMessage/response for hash ${blockHash}:`, error);
        highlightTarget.classList.remove('aicapture-highlight'); // Remove processing highlight
        highlightTarget.classList.add('aicapture-error'); // Apply persistent error highlight
        await setStoredStatus(blockHash, 'error'); // Persist error status
    }
}


// Function to reset the stabilization timer for a potential code block - NOW ASYNC
async function resetStabilizationTimer(highlightTarget, codeElement) {
    if (!highlightTarget || !codeElement) return;

    const codeContent = codeElement.textContent || '';
    // Calculate hash regardless of marker presence to clear potential old timers/status
    const blockHash = hashCode(codeContent);

    if (!codeContent.trimStart().startsWith(FILENAME_MARKER)) {
        // Marker not present (or removed) - ensure no timer and no highlight for this specific hash
        if (stabilizationTimers.has(blockHash)) {
            clearTimeout(stabilizationTimers.get(blockHash));
            stabilizationTimers.delete(blockHash);
        }
        // Check stored status - if it was pending for this hash, clear it. Don't clear sent/error.
        const storedStatus = await getStoredStatus(blockHash);
        if (storedStatus === 'pending') {
             await setStoredStatus(blockHash, null); // Clear pending status
        }
         // Only remove highlights if status isn't final success/error
        if (storedStatus !== 'sent' && storedStatus !== 'error') {
            removeAllHighlights(highlightTarget);
        }
        return;
    }

    // Marker is present, proceed.

    // Check persistent storage - don't process if already sent or errored
    const storedStatus = await getStoredStatus(blockHash);
    if (storedStatus === 'sent' || storedStatus === 'error') {
        // console.log(`AICapture: Timer skip for hash ${blockHash} - already processed (status: ${storedStatus}). Applying final highlight.`);
        // Re-apply final highlight in case it was somehow removed
        removeAllHighlights(highlightTarget);
        highlightTarget.classList.add(storedStatus === 'sent' ? 'aicapture-success' : 'aicapture-error');
        // Ensure no timer is running for this hash
         if (stabilizationTimers.has(blockHash)) {
            clearTimeout(stabilizationTimers.get(blockHash));
            stabilizationTimers.delete(blockHash);
         }
        return;
    }

    // --- Proceed with timer logic ---

    // Clear existing timer for this specific hash
    if (stabilizationTimers.has(blockHash)) {
        clearTimeout(stabilizationTimers.get(blockHash));
        // console.log(`AICapture: Resetting timer for hash: ${blockHash}`);
    } else {
        console.log(`AICapture: Starting stabilization timer for hash: ${blockHash}`);
    }

    // Add the pending highlight (ensure others removed)
    removeAllHighlights(highlightTarget);
    highlightTarget.classList.add('aicapture-pending');
    // Mark as pending in storage
    await setStoredStatus(blockHash, 'pending');

    // Start a new timer
    const timerId = setTimeout(async () => {
        // Timer completed, proceed to send (sendCodeToServer handles final status check)
        stabilizationTimers.delete(blockHash); // Remove from timer map first
        await sendCodeToServer(highlightTarget, codeElement, blockHash);
    }, STABILIZATION_DELAY_MS);

    // Store the new timer ID (keyed by hash)
    stabilizationTimers.set(blockHash, timerId);
}

// --- Scan Function (called by observer via debounce) ---
// Now needs to be async aware, but the core loop can call the async timer function
function scanForCodeBlocks() {
    // console.log("AICapture: Scanning document...");
    document.querySelectorAll(CODE_BLOCK_SELECTOR).forEach(codeElement => {
        const highlightTarget = codeElement.closest(HIGHLIGHT_TARGET_SELECTOR);
        if (highlightTarget) {
            // Call the async function, but don't necessarily need to await it here
            // as resetStabilizationTimer handles its own async logic internally.
            resetStabilizationTimer(highlightTarget, codeElement);
        }
    });
}

const debouncedScan = debounce(scanForCodeBlocks, OBSERVER_DEBOUNCE_MS);

// --- Mutation Observer ---
const observer = new MutationObserver(mutations => {
    // ... (Observer logic to detect relevant changes remains the same) ...
    let potentiallyRelevant = false;
    for (const mutation of mutations) {
        // Check added nodes
        if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
            for (const node of mutation.addedNodes) {
                if (node.nodeType === Node.ELEMENT_NODE) {
                    if (node.matches(HIGHLIGHT_TARGET_SELECTOR) || node.querySelector(HIGHLIGHT_TARGET_SELECTOR)) {
                        potentiallyRelevant = true;
                        break;
                    }
                }
            }
        }
        // Check if text content changed within a relevant element or its children
        else if (mutation.type === 'characterData') {
             // Check if the change happened within or is an ancestor of a potential code block
             const targetParent = mutation.target.parentElement?.closest(HIGHLIGHT_TARGET_SELECTOR);
             if (targetParent) {
                 potentiallyRelevant = true;
             }
             // Also consider changes directly to the code element's text node (if possible)
             else if (mutation.target.parentElement?.matches(CODE_BLOCK_SELECTOR)) {
                 potentiallyRelevant = true;
             }
        }

        if (potentiallyRelevant) break;
    }
    if (potentiallyRelevant) {
        // console.log("AICapture: Relevant mutation detected, queueing debounced scan.");
        debouncedScan();
    }
});


// --- Initialization ---
console.log("AICapture: Starting observer...");
observer.observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true // ** IMPORTANT: Observe text changes **
});

// Initial scan on load
console.log("AICapture: Performing initial scan.");
debouncedScan(); // Use the debounced version for initial scan too
