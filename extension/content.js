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

console.log("AI Code Capture: Content script loaded (V5 - Inject Output).");

// --- Configuration ---
const FILENAME_MARKER = '@@FILENAME@@';
const CODE_BLOCK_SELECTOR = 'ms-code-block pre code';
const HIGHLIGHT_TARGET_SELECTOR = 'ms-code-block';
const STABILIZATION_DELAY_MS = 2000;
const OBSERVER_DEBOUNCE_MS = 300;
const OUTPUT_CONTAINER_CLASS = 'aicapture-output-container'; // Class for the injected output div

// --- State ---
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
        );
    }
}

// --- NEW: Function to Inject Output ---
function displayOutputNearBlock(targetElement, outputData) {
    if (!targetElement || !outputData) return;

    // Check if there's actually any output to display
    const hasSyntaxOutput = outputData.syntax_stdout?.trim() || outputData.syntax_stderr?.trim();
    const hasRunOutput = outputData.run_stdout?.trim() || outputData.run_stderr?.trim();

    if (!hasSyntaxOutput && !hasRunOutput) {
        console.log("AICapture: No execution/syntax output to display.");
        return; // Nothing to show
    }

     // Remove any previous output container for this block
     const existingOutput = targetElement.nextElementSibling;
     if (existingOutput && existingOutput.classList.contains(OUTPUT_CONTAINER_CLASS)) {
         console.log("AICapture: Removing existing output container before injecting new one.");
         existingOutput.remove();
     }

    // Create container
    const outputContainer = document.createElement('div');
    outputContainer.className = OUTPUT_CONTAINER_CLASS;

    let outputHTML = '';

    // Add Syntax Output if present
    if (hasSyntaxOutput) {
        outputHTML += `<strong class="output-label">Syntax Check:</strong>`;
        if (outputData.syntax_stdout?.trim()) {
            outputHTML += `<pre class="aicapture-stdout">${escapeHtml(outputData.syntax_stdout)}</pre>`; // Escape output
        }
        if (outputData.syntax_stderr?.trim()) {
            outputHTML += `<pre class="aicapture-stderr">${escapeHtml(outputData.syntax_stderr)}</pre>`; // Escape output
        }
    }

    // Add Run Output if present
    if (hasRunOutput) {
        outputHTML += `<strong class="output-label">Execution Run:</strong>`;
         if (outputData.run_stdout?.trim()) {
            outputHTML += `<pre class="aicapture-stdout">${escapeHtml(outputData.run_stdout)}</pre>`; // Escape output
        }
        if (outputData.run_stderr?.trim()) {
            outputHTML += `<pre class="aicapture-stderr">${escapeHtml(outputData.run_stderr)}</pre>`; // Escape output
        }
    }

    outputContainer.innerHTML = outputHTML;

    // Inject after the target element (<ms-code-block>)
    targetElement.insertAdjacentElement('afterend', outputContainer);
    console.log("AICapture: Injected execution output after block:", targetElement);
}

// Helper to escape HTML entities in output
function escapeHtml(unsafe) {
    if (!unsafe) return '';
    return unsafe
         .replace(/&/g, "&amp;")
         .replace(/</g, "&lt;")
         .replace(/>/g, "&gt;")
         .replace(/"/g, "&quot;")
         .replace(/'/g, "&#039;");
 }


// Function called ONLY when stabilization timer completes - NOW calls displayOutputNearBlock
async function sendCodeToServer(highlightTarget, codeElement, blockHash) {
    const currentStatus = await getStoredStatus(blockHash);
    if (!highlightTarget || !codeElement || currentStatus === 'sent' || currentStatus === 'error') {
        console.log(`AICapture: Skipping send for hash ${blockHash} - status is ${currentStatus} or invalid elements.`);
        // If status isn't final, clear highlights. If it is final, re-apply highlight in case it was lost.
        if (currentStatus !== 'sent' && currentStatus !== 'error') {
            removeAllHighlights(highlightTarget);
        } else if (highlightTarget && currentStatus) {
             removeAllHighlights(highlightTarget);
             highlightTarget.classList.add(currentStatus === 'sent' ? 'aicapture-success' : 'aicapture-error');
        }
        return;
    }

    const codeContent = codeElement.textContent || '';
    if (!codeContent.trimStart().startsWith(FILENAME_MARKER)) {
        console.log(`AICapture: Skipping send for hash ${blockHash} - marker disappeared.`);
        removeAllHighlights(highlightTarget);
        await setStoredStatus(blockHash, null);
        return;
    }

    console.log(`AICapture: Stabilization complete. Sending code for hash: ${blockHash}`);
    removeAllHighlights(highlightTarget);
    highlightTarget.classList.add('aicapture-highlight');

    try {
        const response = await browser.runtime.sendMessage({
            action: "submitCode",
            code: codeContent,
            hash: blockHash
        });

        console.log(`AICapture: Received response from background for hash ${blockHash}:`, response);
        highlightTarget.classList.remove('aicapture-highlight');

        const success = response && response.success;
        const finalStatus = success ? 'sent' : 'error';
        const finalClass = success ? 'aicapture-success' : 'aicapture-error';

        highlightTarget.classList.add(finalClass);
        await setStoredStatus(blockHash, finalStatus);

        if (success) {
            console.log(`AICapture: Highlight success (persistent) for hash ${blockHash}`);
        } else {
            console.error(`AICapture: Highlight error (persistent) for hash ${blockHash}. Response:`, response?.details);
        }

        // *** Display the output after processing is complete ***
        displayOutputNearBlock(highlightTarget, response?.details);

    } catch (error) {
        console.error(`AICapture: Error in sendMessage/response for hash ${blockHash}:`, error);
        highlightTarget.classList.remove('aicapture-highlight');
        highlightTarget.classList.add('aicapture-error');
        await setStoredStatus(blockHash, 'error');
        // Optionally display error message if details available
        displayOutputNearBlock(highlightTarget, { run_stderr: `Extension Error: ${error.message}` });
    }
}


// Function to reset the stabilization timer - NOW ASYNC & applies stored highlights
async function resetStabilizationTimer(highlightTarget, codeElement) {
    if (!highlightTarget || !codeElement) return;

    const codeContent = codeElement.textContent || '';
    const blockHash = hashCode(codeContent); // Calculate hash regardless of marker for now

    // Check persistent storage first
    const storedStatus = await getStoredStatus(blockHash);
    if (storedStatus === 'sent' || storedStatus === 'error') {
        // console.log(`AICapture: Timer skip for hash ${blockHash} - already processed (status: ${storedStatus}). Applying final highlight.`);
        removeAllHighlights(highlightTarget);
        highlightTarget.classList.add(storedStatus === 'sent' ? 'aicapture-success' : 'aicapture-error');
         if (stabilizationTimers.has(blockHash)) {
            clearTimeout(stabilizationTimers.get(blockHash));
            stabilizationTimers.delete(blockHash);
         }
        return; // Stop processing if already finalized
    }

    // Now check for marker ONLY if not finalized
    if (!codeContent.trimStart().startsWith(FILENAME_MARKER)) {
         if (stabilizationTimers.has(blockHash)) {
             clearTimeout(stabilizationTimers.get(blockHash));
             stabilizationTimers.delete(blockHash);
             console.log(`AICapture: Marker removed or absent, clearing timer for hash: ${blockHash}`);
         }
        // Only remove non-final highlights
        if (storedStatus !== 'sent' && storedStatus !== 'error') {
             removeAllHighlights(highlightTarget);
        }
         // Clear pending status if it existed
         if (storedStatus === 'pending') { await setStoredStatus(blockHash, null); }
         return;
    }

    // --- Proceed with timer logic (Marker present, status not final) ---
    if (stabilizationTimers.has(blockHash)) {
        clearTimeout(stabilizationTimers.get(blockHash));
    } else {
        console.log(`AICapture: Starting stabilization timer for hash: ${blockHash}`);
    }

    removeAllHighlights(highlightTarget);
    highlightTarget.classList.add('aicapture-pending');
    // await setStoredStatus(blockHash, 'pending'); // Optionally mark pending

    const timerId = setTimeout(async () => {
        stabilizationTimers.delete(blockHash);
        await sendCodeToServer(highlightTarget, codeElement, blockHash);
    }, STABILIZATION_DELAY_MS);

    stabilizationTimers.set(blockHash, timerId);
}

// --- Scan Function (remains the same) ---
function scanForCodeBlocks() {
    // console.log("AICapture: Scanning document...");
    document.querySelectorAll(CODE_BLOCK_SELECTOR).forEach(codeElement => {
        const highlightTarget = codeElement.closest(HIGHLIGHT_TARGET_SELECTOR);
        if (highlightTarget) {
            resetStabilizationTimer(highlightTarget, codeElement);
        }
    });
}
const debouncedScan = debounce(scanForCodeBlocks, OBSERVER_DEBOUNCE_MS);

// --- Mutation Observer (remains the same) ---
const observer = new MutationObserver(mutations => {
    let potentiallyRelevant = false;
    for (const mutation of mutations) {
        // Check added nodes
        if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
            for (const node of mutation.addedNodes) {
                if (node.nodeType === Node.ELEMENT_NODE) {
                    if (node.matches(HIGHLIGHT_TARGET_SELECTOR) || node.querySelector(HIGHLIGHT_TARGET_SELECTOR)) {
                        potentiallyRelevant = true; break;
                    }
                }
            }
        }
        // Check text content changes
        else if (mutation.type === 'characterData') {
             const targetParent = mutation.target.parentElement?.closest(HIGHLIGHT_TARGET_SELECTOR);
             if (targetParent) potentiallyRelevant = true;
             else if (mutation.target.parentElement?.matches(CODE_BLOCK_SELECTOR)) potentiallyRelevant = true;
        }
        if (potentiallyRelevant) break;
    }
    if (potentiallyRelevant) { debouncedScan(); }
});


// --- Initialization ---
console.log("AICapture: Starting observer...");
observer.observe(document.body, { childList: true, subtree: true, characterData: true });
console.log("AICapture: Performing initial scan.");
debouncedScan();
