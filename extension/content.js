//@@FILENAME@@ extension/content.js
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

console.log("AI Code Capture: Content script loaded.");

// --- Configuration ---
const FILENAME_MARKER = '@@FILENAME@@';
// *** UPDATED SELECTOR *** Targets code inside ms-code-block
const CODE_BLOCK_SELECTOR = 'ms-code-block pre code';
// This is no longer the primary way to find the target, but could be a fallback
// const PARENT_SELECTOR_FOR_HIGHLIGHT = 'div.markdown, user-query, model-response, code-block, ms-code-block'; // Added ms-code-block just in case
const HIGHLIGHT_DELAY_MS = 2000; // How long the success/error highlight stays visible before fading
const FADE_OUT_DURATION_MS = 500; // Must match transition duration in .aicapture-fadeout CSS

// --- State ---
let processingBlocks = new Set(); // Use the highlight target element as the key

// --- Core Logic ---

// Helper function to remove all highlight classes cleanly
function removeAllHighlights(element) {
    if (element) {
        element.classList.remove(
            'aicapture-highlight',
            'aicapture-success',
            'aicapture-error',
            'aicapture-fadeout'
        );
    }
}

function processCodeBlock(codeElement) { // Renamed parameter for clarity
    if (!codeElement) {
        return;
    }

    const codeContent = codeElement.textContent || '';
    // console.log("Checking block content:", codeContent.substring(0, 50) + "..."); // Debug

    // Check if the block starts with the marker (allowing for leading whitespace)
    if (codeContent.trimStart().startsWith(FILENAME_MARKER)) {
        // *** UPDATED HIGHLIGHT TARGET LOGIC ***
        // Find the parent <ms-code-block> element to apply the highlight style
        let highlightTarget = codeElement.closest('ms-code-block');
        if (!highlightTarget) {
            console.warn("AI Code Capture: Could not find 'ms-code-block' parent for code element:", codeElement, ". Skipping highlight/send.");
            // Optionally, try highlighting the <pre> or <code> as fallback, but it might look weird.
            // highlightTarget = codeElement.closest('pre') || codeElement;
            // if (!highlightTarget) return; // Give up if no reasonable target
            return; // Skip if we can't find the intended target
        }

        // Use the highlightTarget for the processing check
        if (processingBlocks.has(highlightTarget)) {
            // console.log("Skipping block, already processing highlight target:", highlightTarget);
            return;
        }

        // Mark as processing to avoid loops
        processingBlocks.add(highlightTarget);

        // Add initial highlight
        highlightTarget.classList.add('aicapture-highlight');
        console.log("AI Code Capture: Highlighting block:", highlightTarget);


        // Send to background script
        browser.runtime.sendMessage({
            action: "submitCode",
            code: codeContent // Send the full code content from the <code> tag
        }).then(response => {
            console.log("AI Code Capture: Received response from background:", response);
            // Always remove initial highlight
            highlightTarget.classList.remove('aicapture-highlight');

            const success = response && response.status === 'success';
            const finalClass = success ? 'aicapture-success' : 'aicapture-error';

            highlightTarget.classList.add(finalClass);
            if (success) {
                console.log("AI Code Capture: Highlight success");
            } else {
                console.error("AI Code Capture: Highlight error. Response:", response);
            }

            // Set timeout to initiate fade-out, then final removal
            setTimeout(() => {
                // Add fadeout class to start transition
                highlightTarget.classList.add('aicapture-fadeout');
                // Remove the specific success/error class *after* adding fadeout
                // Note: .aicapture-fadeout's transition handles the visual disappearance
                highlightTarget.classList.remove(finalClass);

                // Set another timeout to remove all classes *after* the fade transition completes
                setTimeout(() => {
                    removeAllHighlights(highlightTarget);
                    // Mark as no longer processing AFTER the highlight is fully gone
                    processingBlocks.delete(highlightTarget);
                    console.log("AI Code Capture: Removed highlight after fade");
                }, FADE_OUT_DURATION_MS); // Wait for fade duration

            }, HIGHLIGHT_DELAY_MS); // Wait before starting fade

        }).catch(error => {
            console.error('AI Code Capture: Error sending message or processing response:', error);
            // Still try to clean up the initial highlight and add error state
            highlightTarget.classList.remove('aicapture-highlight');
            highlightTarget.classList.add('aicapture-error');

            // Set timeout to initiate fade-out for error state after catch
            setTimeout(() => {
                 highlightTarget.classList.add('aicapture-fadeout');
                 highlightTarget.classList.remove('aicapture-error'); // Remove error class

                 setTimeout(() => {
                     removeAllHighlights(highlightTarget);
                     // Mark as no longer processing AFTER the highlight is fully gone
                     processingBlocks.delete(highlightTarget);
                     console.log("AI Code Capture: Removed error highlight after catch & fade");
                 }, FADE_OUT_DURATION_MS); // Wait for fade duration

            }, HIGHLIGHT_DELAY_MS); // Wait before starting fade
        });

    } else {
       // console.log("Block skipped (no marker):", codeElement);
    }
}


// --- Mutation Observer ---

const debouncedScan = debounce(() => {
    // console.log("AI Code Capture: Scanning for code blocks..."); // Debug
    // Use the updated selector here
    document.querySelectorAll(CODE_BLOCK_SELECTOR).forEach(processCodeBlock);
}, 300); // Adjust debounce timing if needed

const observer = new MutationObserver(mutations => {
    // Check if any added nodes might contain code blocks or are code blocks themselves
    let potentiallyRelevant = false;
    for (const mutation of mutations) {
        if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
            for (const node of mutation.addedNodes) {
                // Check if the added node itself matches or contains matching elements
                if (node.nodeType === Node.ELEMENT_NODE) {
                    // Use the updated selector here as well
                    if (node.matches(CODE_BLOCK_SELECTOR) || node.querySelector(CODE_BLOCK_SELECTOR)) {
                        potentiallyRelevant = true;
                        break; // Found a relevant node in this mutation
                    }
                    // Also check if an ms-code-block was added directly
                     if (node.matches('ms-code-block') || node.querySelector('ms-code-block')) {
                         potentiallyRelevant = true;
                         break;
                     }
                }
            }
        }
        if (potentiallyRelevant) break; // Found a relevant mutation
    }

    if (potentiallyRelevant) {
        // console.log("AI Code Capture: Relevant mutation detected, queueing scan."); // Debug
        debouncedScan();
    }
});


// --- Initialization ---

console.log("AI Code Capture: Starting observer...");
observer.observe(document.body, {
    childList: true,
    subtree: true
});

// Initial scan in case content is already present
console.log("AI Code Capture: Performing initial scan.");
debouncedScan();
