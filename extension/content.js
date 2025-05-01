'use strict';

console.log("AI Code Capture content script loaded (v8 - Increased Debounce).");

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
// *** INCREASED DEBOUNCE DELAY ***
const DEBOUNCE_DELAY_MS = 2000; // Increased from 750ms to 2 seconds

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
            if (Array.isArray(parsed)) {
                sentHashes = new Set(parsed);
                console.log(`AICapture: Loaded ${sentHashes.size} hashes for port ${serverPort} from sessionStorage.`);
            } else {
                 console.warn(`AICapture: Invalid data in sessionStorage for key ${sessionKey}. Starting fresh.`);
                 sessionStorage.removeItem(sessionKey);
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
        sessionKey = `aicapture_sent_hashes_v1_PORT_${serverPort}`;
        sessionStorage.setItem(sessionKey, JSON.stringify(Array.from(sentHashes)));
    }