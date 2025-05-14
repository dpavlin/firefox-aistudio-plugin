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

console.log("AI Code Capture: Content script loaded (V7 - Log Content).");

// --- Configuration ---
const FILENAME_MARKER = '@@FILENAME@@';
const CODE_BLOCK_SELECTOR = 'ms-code-block pre code';
const HIGHLIGHT_TARGET_SELECTOR = 'ms-code-block';
const STABILIZATION_DELAY_MS = 2500; // Increased slightly for testing
const OBSERVER_DEBOUNCE_MS = 300;
const OUTPUT_CONTAINER_CLASS = 'aicapture-output-container'; // Class for the injected output div
const DEBUG_FLICKER_CLASS = 'aicapture-debug-flicker'; // Temporary class for visual debug

// --- State ---
let stabilizationTimers = new Map(); // Map: highlightTargetElement -> timerId

// --- Simple Hashing Function ---
function hashCode(str) {
  let hash = 0;
  if (!str || str.length === 0) return hash;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash |= 0; // Convert to 32bit integer
  }
  return `hash_${hash}`;
}

// --- Async Helpers for Background Communication ---
async function getStoredStatus(blockHash) {
    try {
        const response = await browser.runtime.sendMessage({ action: "getBlockStatus", hash: blockHash });
        return response?.status || null;
    } catch (error) {
        console.error(`CS: Error getting status for hash ${blockHash}:`, error);
        return null;
    }
}

async function setStoredStatus(blockHash, status) {
    try {
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
            'aicapture-success', 'aicapture-error',
            DEBUG_FLICKER_CLASS
        );
    }
}

// --- Function to Inject Output (remains the same) ---
function displayOutputNearBlock(targetElement, outputData) {
    if (!targetElement || !outputData) return;
    const hasSyntaxOutput = outputData.syntax_stdout?.trim() || outputData.syntax_stderr?.trim();
    const hasRunOutput = outputData.run_stdout?.trim() || outputData.run_stderr?.trim();
    if (!hasSyntaxOutput && !hasRunOutput) return;
     const existingOutput = targetElement.nextElementSibling;
     if (existingOutput && existingOutput.classList.contains(OUTPUT_CONTAINER_CLASS)) {
         existingOutput.remove();
     }
    const outputContainer = document.createElement('div');
    outputContainer.className = OUTPUT_CONTAINER_CLASS;
    let outputHTML = '';
    if (hasSyntaxOutput) {
        outputHTML += `<strong class="output-label">Syntax Check:</strong>`;
        if (outputData.syntax_stdout?.trim()) outputHTML += `<pre class="aicapture-stdout">${outputData.syntax_stdout}</pre>`;
        if (outputData.syntax_stderr?.trim()) outputHTML += `<pre class="aicapture-stderr">${outputData.syntax_stderr}</pre>`;
    }
    if (hasRunOutput) {
        outputHTML += `<strong class="output-label">Execution Run:</strong>`;
         if (outputData.run_stdout?.trim()) outputHTML += `<pre class="aicapture-stdout">${outputData.run_stdout}</pre>`;
        if (outputData.run_stderr?.trim()) outputHTML += `<pre class="aicapture-stderr">${outputData.run_stderr}</pre>`;
    }
    outputContainer.innerHTML = outputHTML;
    targetElement.insertAdjacentElement('afterend', outputContainer);
    console.log("AICapture: DEBUG Injected execution output after block:", targetElement);
}


// Function called ONLY when stabilization timer completes
async function sendCodeToServer(highlightTarget, codeElement) {
    if (!stabilizationTimers.has(highlightTarget)) {
        console.warn(`AICapture: DEBUG sendCodeToServer called for element without active timer?`, highlightTarget);
        return;
    }
    stabilizationTimers.delete(highlightTarget); // Remove timer *before* processing
    console.log(`AICapture: DEBUG Stabilization timer expired for element:`, highlightTarget);

    const codeContent = codeElement?.textContent || '';
    const blockHash = hashCode(codeContent);
    console.log(`AICapture: DEBUG Final content before send (Hash: ${blockHash}):\n---\n${codeContent}\n---`); // Log final content

    const currentStatus = await getStoredStatus(blockHash);
    if (!highlightTarget || !codeElement || currentStatus === 'sent' || currentStatus === 'error') {
        console.log(`AICapture: DEBUG Skipping send for hash ${blockHash} (final status: ${currentStatus || 'none'}) or invalid elements.`);
        if (currentStatus !== 'sent' && currentStatus !== 'error') {
            removeAllHighlights(highlightTarget);
            console.log(`AICapture: DEBUG Cleared non-final highlights for hash ${blockHash}`);
        } else if (highlightTarget && currentStatus) {
             removeAllHighlights(highlightTarget);
             highlightTarget.classList.add(currentStatus === 'sent' ? 'aicapture-success' : 'aicapture-error');
             console.log(`AICapture: DEBUG Re-applied final highlight ${currentStatus} for hash ${blockHash}`);
        }
        return;
    }

    if (!codeContent.trimStart().startsWith(FILENAME_MARKER)) {
        console.log(`AICapture: DEBUG Skipping send for hash ${blockHash} - FINAL CHECK FAILED: marker disappeared before send.`);
        removeAllHighlights(highlightTarget);
        await setStoredStatus(blockHash, null);
        console.log(`AICapture: DEBUG Cleared highlights and status for ${blockHash} (marker gone at final check).`);
        return;
    }

    console.log(`AICapture: DEBUG Sending code block. Hash: ${blockHash}, Element:`, highlightTarget);
    removeAllHighlights(highlightTarget);
    highlightTarget.classList.add('aicapture-highlight');

    try {
        const response = await browser.runtime.sendMessage({
            action: "submitCode",
            code: codeContent,
            hash: blockHash
        });

        console.log(`AICapture: DEBUG Received response from background for hash ${blockHash}:`, response);
        highlightTarget.classList.remove('aicapture-highlight');

        const success = response && response.success;
        const finalStatus = success ? 'sent' : 'error';
        const finalClass = success ? 'aicapture-success' : 'aicapture-error';

        highlightTarget.classList.add(finalClass);
        await setStoredStatus(blockHash, finalStatus);

        if (success) {
            console.log(`AICapture: DEBUG Applied final highlight SUCCESS for hash ${blockHash}`);
        } else {
            console.error(`AICapture: DEBUG Applied final highlight ERROR for hash ${blockHash}. Response:`, response?.details);
        }
        displayOutputNearBlock(highlightTarget, response?.details);

    } catch (error) {
        console.error(`AICapture: DEBUG Error in sendMessage/response for hash ${blockHash}:`, error);
        highlightTarget.classList.remove('aicapture-highlight');
        highlightTarget.classList.add('aicapture-error');
        await setStoredStatus(blockHash, 'error');
        displayOutputNearBlock(highlightTarget, { run_stderr: `Extension Error: ${error.message}` });
    }
}


// Function to reset the stabilization timer
async function resetStabilizationTimer(highlightTarget, codeElement) {
    if (!highlightTarget || !codeElement) return;

    const codeContent = codeElement.textContent || '';
    const blockHash = hashCode(codeContent);
    console.log(`AICapture: DEBUG Checking block. Hash: ${blockHash}, Element:`, highlightTarget);

    // *** ADDED: Log the exact content being checked ***
    console.log(`AICapture: DEBUG Content being checked:\n---\n${codeContent}\n---`);

    const storedStatus = await getStoredStatus(blockHash);
    if (storedStatus === 'sent' || storedStatus === 'error') {
        console.log(`AICapture: DEBUG Skipping timer setup for hash ${blockHash} - already processed (status: ${storedStatus}). Applying final highlight.`);
        removeAllHighlights(highlightTarget);
        highlightTarget.classList.add(storedStatus === 'sent' ? 'aicapture-success' : 'aicapture-error');
         if (stabilizationTimers.has(highlightTarget)) {
            console.log(`AICapture: DEBUG Clearing existing timer for element (final state reached):`, highlightTarget);
            clearTimeout(stabilizationTimers.get(highlightTarget));
            stabilizationTimers.delete(highlightTarget);
         }
        return;
    }

    // --- Perform the marker check ---
    const markerFound = codeContent.trimStart().startsWith(FILENAME_MARKER);
    console.log(`AICapture: DEBUG Marker check result: ${markerFound}`); // Log the result of the check

    if (!markerFound) {
         console.log(`AICapture: DEBUG Marker not found or removed. Clearing timer & pending highlight.`, highlightTarget);
         if (stabilizationTimers.has(highlightTarget)) {
             clearTimeout(stabilizationTimers.get(highlightTarget));
             stabilizationTimers.delete(highlightTarget);
             console.log(`AICapture: DEBUG Cleared existing timer for element (marker check failed).`);
         }
        removeAllHighlights(highlightTarget);
         return;
    }

    // --- Proceed with timer logic (Marker present, state not final) ---
    if (stabilizationTimers.has(highlightTarget)) {
        console.log(`AICapture: DEBUG Clearing existing timer before setting new one for element:`, highlightTarget);
        clearTimeout(stabilizationTimers.get(highlightTarget));
        stabilizationTimers.delete(highlightTarget);
    } else {
        console.log(`AICapture: DEBUG No existing timer found for element. Starting fresh.`, highlightTarget);
    }

    console.log(`AICapture: DEBUG Applying PENDING highlight and setting timer (${STABILIZATION_DELAY_MS}ms) for element. Hash: ${blockHash}`, highlightTarget);
    removeAllHighlights(highlightTarget);
    highlightTarget.classList.add('aicapture-pending');
    highlightTarget.classList.add(DEBUG_FLICKER_CLASS);
    setTimeout(() => {
        if (highlightTarget) highlightTarget.classList.remove(DEBUG_FLICKER_CLASS);
    }, 150);

    const timerId = setTimeout(() => {
        console.log(`AICapture: DEBUG Timer callback executing for element:`, highlightTarget);
        sendCodeToServer(highlightTarget, codeElement);
    }, STABILIZATION_DELAY_MS);

    stabilizationTimers.set(highlightTarget, timerId);
    console.log(`AICapture: DEBUG Timer ID ${timerId} stored for element.`, highlightTarget);
}

// --- Scan Function ---
function scanForCodeBlocks() {
    console.log("AICapture: DEBUG Scanning document...");
    document.querySelectorAll(CODE_BLOCK_SELECTOR).forEach(codeElement => {
        const highlightTarget = codeElement.closest(HIGHLIGHT_TARGET_SELECTOR);
        if (highlightTarget) {
            resetStabilizationTimer(highlightTarget, codeElement);
        } else {
            // This case should ideally not happen if selector is correct
            // console.warn("AICapture: DEBUG Found code element but no highlight target parent?", codeElement);
        }
    });
    console.log("AICapture: DEBUG Scan finished.");
}
const debouncedScan = debounce(scanForCodeBlocks, OBSERVER_DEBOUNCE_MS);

// --- Mutation Observer ---
const observer = new MutationObserver(mutations => {
    let potentiallyRelevant = false;
    for (const mutation of mutations) {
        let targetNode = mutation.target;
        if (targetNode.nodeType === Node.TEXT_NODE) targetNode = targetNode.parentElement;

        if (targetNode && targetNode.nodeType === Node.ELEMENT_NODE) {
             if (targetNode.closest(HIGHLIGHT_TARGET_SELECTOR)) {
                potentiallyRelevant = true;
                break;
             }
        }
         if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
            for (const node of mutation.addedNodes) {
                if (node.nodeType === Node.ELEMENT_NODE) {
                    if (node.matches(HIGHLIGHT_TARGET_SELECTOR) || node.querySelector(HIGHLIGHT_TARGET_SELECTOR)) {
                        potentiallyRelevant = true; break;
                    }
                }
            }
            if (potentiallyRelevant) break;
        }
    }

    if (potentiallyRelevant) {
        console.log("AICapture: DEBUG Relevant mutation detected, queueing debounced scan.");
        debouncedScan();
    }
});


// --- Initialization ---
console.log("AICapture: DEBUG Starting observer...");
observer.observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true
});

console.log("AICapture: DEBUG Performing initial scan.");
debouncedScan();

const style = document.createElement('style');
style.textContent = `
  .${DEBUG_FLICKER_CLASS} {
    outline: 2px dashed #ff00ff !important;
    transition: outline 0.1s ease-in-out !important;
  }
`;
document.head.appendChild(style);
