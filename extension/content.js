// @@FILENAME@@ extension/content.js
// Debounce function (remains the same)
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

console.log("AI Code Capture: Content script loaded (V2 - Stabilization Logic).");

// --- Configuration ---
const FILENAME_MARKER = '@@FILENAME@@';
const CODE_BLOCK_SELECTOR = 'ms-code-block pre code'; // Selector for the code element itself
const HIGHLIGHT_TARGET_SELECTOR = 'ms-code-block'; // Selector for the element to highlight/track
const STABILIZATION_DELAY_MS = 2000; // Wait 2 seconds for inactivity before sending
const OBSERVER_DEBOUNCE_MS = 300; // Debounce DOM scans

// --- State ---
// Tracks elements that have been successfully processed and sent
let processedBlocks = new Set();
// Tracks stabilization timers for elements that might be code blocks
let stabilizationTimers = new Map(); // Map: highlightTargetElement -> timerId

// --- Core Logic ---

// Removes all AICapture classes
function removeAllHighlights(element) {
    if (element) {
        element.classList.remove(
            'aicapture-highlight',
            'aicapture-success',
            'aicapture-error',
            'aicapture-fadeout' // Just in case
        );
    }
}

// Function called ONLY when stabilization timer completes
function sendCodeToServer(highlightTarget, codeElement) {
    if (!highlightTarget || !codeElement || processedBlocks.has(highlightTarget)) {
        console.log("AICapture: Skipping send - already processed or invalid.", highlightTarget);
        return; // Don't send if already processed or elements missing
    }

    const codeContent = codeElement.textContent || '';

    // Final check for marker before sending
    if (!codeContent.trimStart().startsWith(FILENAME_MARKER)) {
        console.log("AICapture: Skipping send - marker disappeared?", highlightTarget);
        removeAllHighlights(highlightTarget); // Clean up any temporary highlight
        return;
    }

    // Mark as processed *before* sending to prevent race conditions
    processedBlocks.add(highlightTarget);
    console.log("AICapture: Stabilization complete. Sending code for:", highlightTarget);

    // Apply temporary processing highlight (optional, could just wait for final)
    removeAllHighlights(highlightTarget); // Ensure clean state
    highlightTarget.classList.add('aicapture-highlight'); // Yellow while sending

    // Send to background script
    browser.runtime.sendMessage({
        action: "submitCode",
        code: codeContent
    }).then(response => {
        console.log("AICapture: Received response from background:", response);
        highlightTarget.classList.remove('aicapture-highlight'); // Remove processing highlight

        const success = response && response.status === 'success';
        const finalClass = success ? 'aicapture-success' : 'aicapture-error';

        // Apply final, persistent highlight class
        highlightTarget.classList.add(finalClass);
        if (success) {
            console.log("AICapture: Highlight success (persistent)");
        } else {
            console.error("AICapture: Highlight error (persistent). Response:", response);
        }
        // ** NO removal logic here **

    }).catch(error => {
        console.error('AICapture: Error sending message or processing response:', error);
        highlightTarget.classList.remove('aicapture-highlight'); // Remove processing highlight
        highlightTarget.classList.add('aicapture-error'); // Apply persistent error highlight on catch
         // ** NO removal logic here **
    });
}


// Function to reset the stabilization timer for a potential code block
function resetStabilizationTimer(highlightTarget, codeElement) {
    if (!highlightTarget || !codeElement) return;

     // If it's already been successfully processed and sent, don't restart timer
    if (processedBlocks.has(highlightTarget)) {
        // console.log("AICapture: Timer skip - already processed:", highlightTarget);
        return;
    }

    // Check if the code content *still* has the marker - it might be removed during editing
    const currentCodeContent = codeElement.textContent || '';
    if (!currentCodeContent.trimStart().startsWith(FILENAME_MARKER)) {
         // If marker removed, clear any existing timer and highlights
         if (stabilizationTimers.has(highlightTarget)) {
             clearTimeout(stabilizationTimers.get(highlightTarget));
             stabilizationTimers.delete(highlightTarget);
             console.log("AICapture: Marker removed, clearing timer for:", highlightTarget);
         }
         removeAllHighlights(highlightTarget); // Remove any previous highlight
         return; // Don't start a new timer if marker is gone
    }


    // Clear existing timer for this specific block
    if (stabilizationTimers.has(highlightTarget)) {
        clearTimeout(stabilizationTimers.get(highlightTarget));
        // console.log("AICapture: Resetting timer for:", highlightTarget);
    } else {
        // console.log("AICapture: Starting timer for:", highlightTarget);
        // Optional: Add a subtle visual cue that it's potentially going to be processed?
        // highlightTarget.classList.add('aicapture-pending'); // Example - would need CSS
    }

    // Start a new timer
    const timerId = setTimeout(() => {
        // Timer completed without being reset, proceed to send
        stabilizationTimers.delete(highlightTarget); // Remove from timer map
        // highlightTarget.classList.remove('aicapture-pending'); // Remove pending cue
        sendCodeToServer(highlightTarget, codeElement);
    }, STABILIZATION_DELAY_MS);

    // Store the new timer ID
    stabilizationTimers.set(highlightTarget, timerId);
}

// --- Scan Function (called by observer via debounce) ---
function scanForCodeBlocks() {
    // console.log("AICapture: Scanning document...");
    document.querySelectorAll(CODE_BLOCK_SELECTOR).forEach(codeElement => {
        // Find the highlight target for this code element
        const highlightTarget = codeElement.closest(HIGHLIGHT_TARGET_SELECTOR);
        if (highlightTarget) {
            // We found a potential block. Reset its timer.
            // If it's stable, the timer completion will handle sending.
            // If it changes again, the observer will trigger another scan,
            // which will find it again and reset the timer anew.
            resetStabilizationTimer(highlightTarget, codeElement);
        } else {
             // This shouldn't happen if CODE_BLOCK_SELECTOR requires HIGHLIGHT_TARGET_SELECTOR as an ancestor
             // console.warn("AICapture: Found code element without highlight target parent?", codeElement);
        }
    });
}

const debouncedScan = debounce(scanForCodeBlocks, OBSERVER_DEBOUNCE_MS);

// --- Mutation Observer ---
const observer = new MutationObserver(mutations => {
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
        // This is broad but necessary as we don't know exactly which node's text changes
        else if (mutation.type === 'characterData') {
            const targetParent = mutation.target.parentElement?.closest(HIGHLIGHT_TARGET_SELECTOR);
             if (targetParent) {
                 potentiallyRelevant = true;
             }
        }
         // Check attribute changes on the target itself (less likely relevant for content change)
         // else if (mutation.type === 'attributes') {
         //     if (mutation.target.matches && mutation.target.matches(HIGHLIGHT_TARGET_SELECTOR)) {
         //         potentiallyRelevant = true;
         //     }
         // }

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

// Initial scan in case content is already present
console.log("AICapture: Performing initial scan.");
debouncedScan(); // Use the debounced version for initial scan too
