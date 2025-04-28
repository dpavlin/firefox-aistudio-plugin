// content.js
console.log("AI Code Capture content script loaded (for automatic capture).");

// --- CSS Selectors for Google AI Studio ---
const targetNodeSelector = 'ms-chat-session ms-autoscroll-container > div';
const codeElementSelector = 'ms-code-block pre code';
const modelTurnSelector = 'ms-chat-turn:has(div.chat-turn-container.model)';

// --- Highlight Logic Variables ---
const HIGHLIGHT_CLASS = 'aicapture-highlight';
const HIGHLIGHT_DURATION_MS = 2500; // How long the highlight lasts (2.5 seconds)
let highlightTimer = null;
let highlightedElement = null;

// --- Debounce and Duplicate Check Logic ---
let debounceTimer;
let lastSentCode = '';
const DEBOUNCE_DELAY_MS = 1500;

// --- Helper Function to Apply/Remove Highlight ---
function applyHighlight(element) {
  // Clear any previous highlight timer
  if (highlightTimer) {
    clearTimeout(highlightTimer);
    highlightTimer = null;
  }
  // Remove highlight from any previously highlighted element
  if (highlightedElement && highlightedElement !== element) {
    highlightedElement.classList.remove(HIGHLIGHT_CLASS);
  }

  // Apply highlight to the new element
  if (element) {
    console.log("Applying highlight to:", element);
    element.classList.add(HIGHLIGHT_CLASS);
    highlightedElement = element;

    // Set timer to remove the highlight
    highlightTimer = setTimeout(() => {
      if (highlightedElement) {
        console.log("Removing highlight from:", highlightedElement);
        highlightedElement.classList.remove(HIGHLIGHT_CLASS);
      }
      highlightedElement = null;
      highlightTimer = null;
    }, HIGHLIGHT_DURATION_MS);
  } else {
      highlightedElement = null; // Ensure cleared if no element
  }
}


function findAndSendCode(target) {
    console.log(`Searching within target:`, target);
    console.log(`Using model turn selector: ${modelTurnSelector}`);
    const modelTurns = target.querySelectorAll(modelTurnSelector);

    if (!modelTurns || modelTurns.length === 0) {
        console.log(`No model turns found using selector: ${modelTurnSelector}`);
        return;
    }
    const lastModelTurn = modelTurns[modelTurns.length - 1];
    console.log("Found last model turn element:", lastModelTurn);

    console.log(`Searching for code element using selector: ${codeElementSelector}`);
    const codeElement = lastModelTurn.querySelector(codeElementSelector);

    if (!codeElement) {
        console.log(`Code element ('${codeElementSelector}') not found within the last model turn.`);
        // If no code found, ensure any previous highlight is removed
        applyHighlight(null);
        return;
    }

    // Code element FOUND
    const capturedCode = codeElement.innerText;

    if (capturedCode && capturedCode.trim().length > 0 && capturedCode !== lastSentCode) {
        console.log("Detected new/changed code via MutationObserver, applying highlight and sending to background:", capturedCode.substring(0, 100) + "...");
        // Apply visual highlight
        applyHighlight(codeElement); // <<< APPLY HIGHLIGHT HERE
        // Send message
        chrome.runtime.sendMessage({ action: 'sendCodeDirectly', code: capturedCode });
        lastSentCode = capturedCode;
    } else if (capturedCode === lastSentCode) {
        console.log("Code detected, but it hasn't changed since last send.");
        // Optionally re-apply highlight if desired even if not sending again
        // applyHighlight(codeElement);
    } else if (!capturedCode || capturedCode.trim().length === 0) {
        console.log("Code element found, but it is empty.");
        applyHighlight(null); // Remove highlight if code is empty
    }
}

// --- MutationObserver Setup ---
const targetNode = document.querySelector(targetNodeSelector);

if (targetNode) {
    console.log("Target node found:", targetNode, "Setting up MutationObserver.");

    const callback = function(mutationsList, observer) {
        clearTimeout(debounceTimer);
        let relevantMutationDetected = false;
        for(const mutation of mutationsList) {
             if (mutation.type === 'childList' || mutation.type === 'subtree' ) {
                 relevantMutationDetected = true;
                 break;
             }
             if (mutation.type === 'characterData' && mutation.target.parentElement?.closest(modelTurnSelector)) {
                relevantMutationDetected = true;
                 break;
             }
        }
        if (relevantMutationDetected) {
             console.log("Relevant mutation detected, scheduling code check after debounce.");
             debounceTimer = setTimeout(() => {
                 console.log("MutationObserver running findAndSendCode after debounce.");
                 findAndSendCode(targetNode);
             }, DEBOUNCE_DELAY_MS);
        } else {
            // console.log("Mutation detected, but deemed not relevant."); // Less verbose logging
        }
    };

    const observer = new MutationObserver(callback);
    const config = { childList: true, subtree: true, characterData: true };
    observer.observe(targetNode, config);
    console.log("MutationObserver is now observing the target node and its subtree.");

    console.log("Checking for initial code on page load...");
    findAndSendCode(targetNode);

} else {
    console.error(`Could not find the target node ('${targetNodeSelector}') to observe. Automatic capture will not work. Please update the selector in content.js.`);
}

// --- Listener for Manual Capture ---
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'getCodeFromPage') {
    console.log("Manual action getCodeFromPage received.");
    const modelTurns = document.querySelectorAll(modelTurnSelector);
    if (!modelTurns || modelTurns.length === 0) {
         console.error(`Could not find model turn ('${modelTurnSelector}') manually on the page.`);
         sendResponse({ code: null, error: "Model turn element not found manually" });
         applyHighlight(null); // Clear highlight
         return true;
    }
    const lastModelTurn = modelTurns[modelTurns.length - 1];
    const codeElement = lastModelTurn.querySelector(codeElementSelector);

    if (codeElement) {
        const capturedCode = codeElement.innerText;
        console.log("Found code element manually, applying highlight and sending back:", capturedCode.substring(0, 100) + "...");
        applyHighlight(codeElement); // <<< APPLY HIGHLIGHT HERE for manual trigger
        sendResponse({ code: capturedCode });
    } else {
        console.error(`Could not find code element ('${codeElementSelector}') manually within the last model turn.`);
        sendResponse({ code: null, error: "Code element not found manually within model turn" });
        applyHighlight(null); // Clear highlight
    }
    return true;
  }
});