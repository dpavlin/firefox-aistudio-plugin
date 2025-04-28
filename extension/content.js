// content.js
console.log("AI Code Capture content script loaded (for automatic capture - all blocks).");

// --- CSS Selectors for Google AI Studio ---
const targetNodeSelector = 'ms-chat-session ms-autoscroll-container > div'; // Container for chat turns
const codeElementSelector = 'ms-code-block pre code'; // Selector for code elements
const modelTurnSelector = 'ms-chat-turn:has(div.chat-turn-container.model)'; // Selector for model turn containers

// --- Highlight Logic Variables ---
const HIGHLIGHT_CLASS = 'aicapture-highlight';
const HIGHLIGHT_DURATION_MS = 2500;
// Keep track of multiple highlight timers if needed, mapping element to timer ID
const highlightTimers = new Map();

// --- Debounce and Duplicate Check Logic ---
let debounceTimer;
const DEBOUNCE_DELAY_MS = 1500;
// Use a Set to store the innerText of code blocks already processed and sent
const sentCodeBlocksContent = new Set();

// --- Helper Function to Apply/Remove Highlight ---
function applyHighlight(element) {
  if (!element) return;

  // Clear any existing timer for THIS element
  if (highlightTimers.has(element)) {
    clearTimeout(highlightTimers.get(element));
  }

  console.log("Applying highlight to:", element);
  element.classList.add(HIGHLIGHT_CLASS);

  // Set a new timer to remove the highlight for THIS element
  const timerId = setTimeout(() => {
    console.log("Removing highlight from:", element);
    element.classList.remove(HIGHLIGHT_CLASS);
    highlightTimers.delete(element); // Clean up the map
  }, HIGHLIGHT_DURATION_MS);

  highlightTimers.set(element, timerId); // Store the timer ID
}

// Function to process model turns and send NEW code blocks
function findAndSendNewCodeBlocks(target) {
    console.log(`Processing turns within target:`, target);
    console.log(`Using model turn selector: ${modelTurnSelector}`);

    // Find all model turns within the observed node/document
    const modelTurns = target.querySelectorAll(modelTurnSelector);

    if (!modelTurns || modelTurns.length === 0) {
        console.log(`No model turns found.`);
        return;
    }

    console.log(`Found ${modelTurns.length} model turn(s). Processing...`);

    // Iterate through each model turn found
    modelTurns.forEach((turnElement, turnIndex) => {
        console.log(`Processing Turn ${turnIndex + 1}`);
        console.log(`Searching for code elements using selector: ${codeElementSelector}`);
        const codeElements = turnElement.querySelectorAll(codeElementSelector);

        if (!codeElements || codeElements.length === 0) {
            console.log(` -> No code elements found in this turn.`);
            return; // Continue to the next turn
        }

        console.log(` -> Found ${codeElements.length} code element(s) in this turn.`);

        // Iterate through each code block found in this specific turn
        codeElements.forEach((codeElement, codeIndex) => {
            const capturedCode = codeElement.innerText;
            const trimmedCode = capturedCode ? capturedCode.trim() : '';

            // Check if code is non-empty AND if we haven't sent this exact content before
            if (trimmedCode.length > 0 && !sentCodeBlocksContent.has(capturedCode)) {
                 console.log(` -> Found NEW code block ${codeIndex + 1} in Turn ${turnIndex + 1}. Applying highlight and sending to background:`, capturedCode.substring(0, 80) + "...");

                 // Apply visual highlight
                 applyHighlight(codeElement);

                 // Send message to background script
                 chrome.runtime.sendMessage({ action: 'sendCodeDirectly', code: capturedCode });

                 // Add this code content to the set to prevent duplicates
                 sentCodeBlocksContent.add(capturedCode);

            } else if (sentCodeBlocksContent.has(capturedCode)) {
                 console.log(` -> Code block ${codeIndex + 1} in Turn ${turnIndex + 1} already sent. Skipping.`);
                 // Optionally re-highlight if desired: applyHighlight(codeElement);
            } else {
                 console.log(` -> Code block ${codeIndex + 1} in Turn ${turnIndex + 1} is empty. Skipping.`);
            }
        });
    });
     console.log("Finished processing turns.");
}

// --- MutationObserver Setup ---
const targetNode = document.querySelector(targetNodeSelector);

if (targetNode) {
    console.log("Target node found:", targetNode, "Setting up MutationObserver.");

    const callback = function(mutationsList, observer) {
        // Check if any relevant mutations occurred before debouncing
        let relevantMutationDetected = false;
        for(const mutation of mutationsList) {
            // Check if nodes were added (new turn) or if significant subtree changes happened
            if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                // Check if any added node looks like a chat turn
                 for (const node of mutation.addedNodes) {
                     if (node.nodeType === Node.ELEMENT_NODE && node.matches(modelTurnSelector)) {
                         relevantMutationDetected = true;
                         break;
                     }
                 }
            }
             if (relevantMutationDetected) break; // No need to check others if found

             // Also consider subtree changes as potentially relevant (e.g., content loading into existing turn)
             if (mutation.type === 'subtree' || mutation.type === 'characterData') {
                 relevantMutationDetected = true;
                 break;
             }
        }

        if (relevantMutationDetected) {
             console.log("Relevant mutation detected, scheduling code check after debounce.");
             // Clear previous timer and set a new one
             clearTimeout(debounceTimer);
             debounceTimer = setTimeout(() => {
                 console.log("MutationObserver running findAndSendNewCodeBlocks after debounce.");
                 findAndSendNewCodeBlocks(targetNode); // Process potentially updated/new turns
             }, DEBOUNCE_DELAY_MS);
        }
    };

    const observer = new MutationObserver(callback);
    const config = { childList: true, subtree: true, characterData: true };
    observer.observe(targetNode, config);
    console.log("MutationObserver is now observing the target node and its subtree.");

    console.log("Checking for initial code on page load...");
    // Use setTimeout to allow initial rendering after load before first check
    setTimeout(() => findAndSendNewCodeBlocks(document), 500); // Check entire document initially

} else {
    console.error(`Could not find the target node ('${targetNodeSelector}') to observe. Automatic capture will not work. Please update the selector in content.js.`);
}

// --- Listener for Manual Capture ---
// Manual capture will find the LAST code block in the LAST model turn and send/highlight it.
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'getCodeFromPage') {
    console.log("Manual action getCodeFromPage received.");
    const modelTurns = document.querySelectorAll(modelTurnSelector);
    if (!modelTurns || modelTurns.length === 0) {
         console.error(`Could not find model turn ('${modelTurnSelector}') manually on the page.`);
         sendResponse({ code: null, error: "Model turn element not found manually" });
         // applyHighlight(null); // Clear any lingering highlight
         return true;
    }
    const lastModelTurn = modelTurns[modelTurns.length - 1];
    // Find all code blocks within the last turn
    const codeElements = lastModelTurn.querySelectorAll(codeElementSelector);

    if (codeElements && codeElements.length > 0) {
         // Target the very last code element found
        const lastCodeElement = codeElements[codeElements.length - 1];
        const capturedCode = lastCodeElement.innerText;
        console.log("Found last code element manually, applying highlight and sending back:", capturedCode.substring(0, 100) + "...");
        applyHighlight(lastCodeElement); // Apply highlight
        sendResponse({ code: capturedCode });
        // Optional: Add to sent set? Probably not needed for manual trigger unless causing issues.
        // sentCodeBlocksContent.add(capturedCode);
    } else {
        console.error(`Could not find code element ('${codeElementSelector}') manually within the last model turn.`);
        sendResponse({ code: null, error: "Code element not found manually within model turn" });
        // applyHighlight(null); // Clear any lingering highlight
    }
    return true; // Indicate async response
  }
});