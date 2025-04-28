// --- START OF FILE content.js ---
console.log("AI Code Capture content script loaded (for automatic capture).");

// --- CSS Selectors for Google AI Studio ---
// Selector for the container where new chat turns are added.
// ** INSPECT LIVE PAGE: Verify this selector is correct! **
const targetNodeSelector = 'ms-chat-session ms-autoscroll-container > div'; // <<< CHECK THIS!

// Selector for the specific code block element WITHIN a model's response turn.
const codeElementSelector = 'ms-code-block pre code';

// Selector to find the specific ms-chat-turn element representing a MODEL response.
const modelTurnSelector = 'ms-chat-turn:has(div.chat-turn-container.model)'; // Uses :has() pseudo-class

// --- Debounce and Duplicate Check Logic ---
let debounceTimer;
let lastSentCode = '';
const DEBOUNCE_DELAY_MS = 1500;

function findAndSendCode(target) {
    console.log(`Searching within target:`, target);
    console.log(`Using model turn selector: ${modelTurnSelector}`);

    // Find ALL model response turns within the target container using the :has() selector
    const modelTurns = target.querySelectorAll(modelTurnSelector);

    if (!modelTurns || modelTurns.length === 0) {
        console.log(`No model turns found using selector: ${modelTurnSelector}`);
        return;
    }
    // Get the last model turn element
    const lastModelTurn = modelTurns[modelTurns.length - 1];
    console.log("Found last model turn element:", lastModelTurn);

    // Find the code element within that last model turn
    console.log(`Searching for code element using selector: ${codeElementSelector}`);
    const codeElement = lastModelTurn.querySelector(codeElementSelector);

    if (!codeElement) {
        console.log(`Code element ('${codeElementSelector}') not found within the last model turn.`);
        return;
    }

    const capturedCode = codeElement.innerText;

    if (capturedCode && capturedCode.trim().length > 0 && capturedCode !== lastSentCode) {
        console.log("Detected new/changed code via MutationObserver, sending to background:", capturedCode.substring(0, 100) + "...");
        chrome.runtime.sendMessage({ action: 'sendCodeDirectly', code: capturedCode });
        lastSentCode = capturedCode;
    } else if (capturedCode === lastSentCode) {
        console.log("Code detected, but it hasn't changed since last send.");
    } else if (!capturedCode || capturedCode.trim().length === 0) {
        console.log("Code element found, but it is empty.");
    }
}

// --- MutationObserver Setup ---
const targetNode = document.querySelector(targetNodeSelector);

if (targetNode) {
    console.log("Target node found:", targetNode, "Setting up MutationObserver.");

    const callback = function(mutationsList, observer) {
        clearTimeout(debounceTimer);
        let relevantMutationDetected = false;
        // Check if nodes were added or significant changes occurred
        for(const mutation of mutationsList) {
             // Check specifically if new nodes were added or removed at the top level of targetNode
             // or if subtree content changed significantly.
             if (mutation.type === 'childList' || mutation.type === 'subtree') {
                // Check if added nodes include ms-chat-turn or if removed nodes were ms-chat-turn
                // More complex checking could be done here if needed.
                relevantMutationDetected = true;
                break;
             }
             // CharacterData changes deep within might also signal content update
             if (mutation.type === 'characterData' && mutation.target.parentElement?.closest(modelTurnSelector)) {
                relevantMutationDetected = true;
                 break;
             }
        }

        if (relevantMutationDetected) {
             console.log("Relevant mutation detected, scheduling code check after debounce.");
             debounceTimer = setTimeout(() => {
                 console.log("MutationObserver running findAndSendCode after debounce.");
                 findAndSendCode(targetNode); // Re-check the container
             }, DEBOUNCE_DELAY_MS);
        } else {
             console.log("Mutation detected, but deemed not relevant for triggering code check.");
        }
    };

    const observer = new MutationObserver(callback);
    const config = {
        childList: true,
        subtree: true,
        characterData: true // Keep watching text changes too, might catch updates within a turn
     };

    observer.observe(targetNode, config);
    console.log("MutationObserver is now observing the target node and its subtree.");

    console.log("Checking for initial code on page load...");
    findAndSendCode(targetNode);

} else {
    console.error(`Could not find the target node ('${targetNodeSelector}') to observe. Automatic capture will not work. Please update the selector in content.js.`);
}

// --- Listener for Manual Capture ---
// Use the same selector logic for consistency
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'getCodeFromPage') {
    console.log("Manual action getCodeFromPage received.");
    // Find the LAST model turn on the page
    const modelTurns = document.querySelectorAll(modelTurnSelector);
    if (!modelTurns || modelTurns.length === 0) {
         console.error(`Could not find model turn ('${modelTurnSelector}') manually on the page.`);
         sendResponse({ code: null, error: "Model turn element not found manually" });
         return true;
    }
    const lastModelTurn = modelTurns[modelTurns.length - 1];
    const codeElement = lastModelTurn.querySelector(codeElementSelector);

    if (codeElement) {
        const capturedCode = codeElement.innerText;
        console.log("Found code element manually, sending back:", capturedCode.substring(0, 100) + "...");
        sendResponse({ code: capturedCode });
    } else {
        console.error(`Could not find code element ('${codeElementSelector}') manually within the last model turn.`);
        sendResponse({ code: null, error: "Code element not found manually within model turn" });
    }
    return true; // Indicate async response
  }
});
// --- END OF FILE content.js ---