@@FILENAME@@ verify.md
**Consolidated Verification List (with Full Paths)**

**I. Core Code Capture & Highlighting (Content Script)**

1.  **Verify that** the `extension/content.js` script uses the correct CSS selector (`ms-code-block pre code`) to identify potential code elements within the AI Studio page structure.
2.  **Verify that** `extension/content.js` checks the `textContent` of identified code elements for the `@@FILENAME@@` marker strictly at the beginning of the first line (allowing for leading whitespace).
3.  **Verify that** when a code element with the marker is detected, `extension/content.js` correctly finds the parent `<ms-code-block>` element to use as the target for highlighting and state tracking.
4.  **Verify that** a subtle "pending" highlight (`.aicapture-pending`) is applied to the `<ms-code-block>` element when its stabilization timer starts or restarts.
5.  **Verify that** the plugin waits for a period of inactivity (`STABILIZATION_DELAY_MS`, e.g., 2 seconds) after a marked code block appears or changes before processing it further.
6.  **Verify that** if changes occur to the text content within a monitored code block while its stabilization timer is running, the timer is correctly reset in `extension/content.js`.
7.  **Verify that** if the `@@FILENAME@@` marker is removed from a block while its timer is pending, the pending highlight is removed, and the block is not sent to the server.
8.  **Verify that** once the stabilization timer completes successfully, the pending highlight is removed, and a temporary processing highlight (`.aicapture-highlight`) is applied while the request is sent to `extension/background.js`.
9.  **Verify that** each specific `<ms-code-block>` element is processed and sent to the server **only once** per page load (achieved by adding it to `processedBlocks` in `extension/content.js` and not removing it).
10. **Verify that** after server processing, the highlight on the `<ms-code-block>` changes to green (`.aicapture-success`) or red (`.aicapture-error`) based on the server's response.
11. **Verify that** the final success or error highlight applied to a code block **remains visible indefinitely** (no fade-out or automatic removal).
12. **Verify that** the `MutationObserver` in `extension/content.js` listens for `characterData` changes to correctly detect modifications within code blocks during generation.
13. **Verify that** the `MutationObserver` processing is debounced (`debouncedScan`) in `extension/content.js` to handle rapid DOM changes efficiently.

**II. Background Script & Communication**

14. **Verify that** the `extension/background.js` script correctly receives `submitCode` messages from `extension/content.js`.
15. **Verify that** `extension/background.js` retrieves the correct server port associated with the *sending tab's ID* from storage before sending a `submitCode` request.
16. **Verify that** `extension/background.js` correctly sends the code to the backend server's `/submit_code` endpoint (on `server.py`) with the `Content-Type: application/json` header and a properly stringified JSON body (`{ "code": "..." }`).
17. **Verify that** `extension/background.js` handles potential network errors or non-JSON responses from the server gracefully and relays an appropriate error status back to `extension/content.js`.
18. **Verify that** `extension/background.js` correctly relays the success/failure status received from the server back to the calling `extension/content.js`.
19. **Verify that** `extension/background.js` checks the global activation state before processing a `submitCode` message and sends an "inactive" status back if the extension is disabled.
20. **Verify that** `extension/background.js` handles `getPort`, `storePort`, `getActivationState`, and `storeActivationState` messages correctly, interacting with `browser.storage.local` and using the appropriate tab ID for port operations.
21. **Verify that** the `testConnection` message handler in `extension/background.js` uses the specific `port` number provided in the message payload for the fetch request to the server's `/test_connection` endpoint.
22. **Verify that** the `updateConfig` message handler in `extension/background.js` uses the port associated with the *sender tab* to target the correct server instance's `/update_config` endpoint.
23. **Verify that** `extension/background.js` includes a listener (`tabs.onRemoved`) that cleans up the stored port setting for a tab when it is closed.

**III. Backend Server Processing (Python)**

24. **Verify that** the backend server (`routes/submit.py`) correctly handles potential leading UTF-8 BOM characters in the received code.
25. **Verify that** the backend server (`routes/submit.py`) uses the correct regex defined in `utils.py` (`^\s*@@FILENAME@@\s+(.+?)\s*$`) to detect the marker *only* at the beginning of the (potentially BOM-stripped) first line.
26. **Verify that** when a valid first-line marker is found, the backend server (`routes/submit.py`) strips exactly that first line before saving the content or passing it to Git.
27. **Verify that** the backend correctly sanitizes the filename extracted from the marker using `utils.py::sanitize_filename`, rejecting invalid paths (e.g., absolute, containing `..`, hidden segments) and appending `.txt` if no valid extension exists.
28. **Verify that** if filename sanitization fails, the backend (`routes/submit.py`) reverts to using the original (BOM-stripped) code content for fallback saving.
29. **Verify that** if no valid marker is found on the first line, the backend (`routes/submit.py`) uses the original (BOM-stripped) code content for fallback processing.
30. **Verify that** the server (`routes/submit.py`) correctly determines the save target ("git", "fallback_named", "fallback") based on the marker validity, sanitization result, repo status, and file tracking status (using functions from `file_handler.py`).
31. **Verify that** for tracked files in a Git repo, the backend (`file_handler.py`) only commits if the new (stripped) content is different from the existing file content.
32. **Verify that** the server correctly generates timestamped filenames in the `received_codes/` directory during fallback scenarios using `utils.py::generate_timestamped_filepath`.
33. **Verify that** the server (`server.py`) uses a `threading.Lock` to process `/submit_code` requests sequentially, preventing race conditions.
34. **Verify that** Flask Blueprints (from `routes/`) are correctly imported and registered in `server.py`.

**IV. Backend Server Execution (Optional)**

35. **Verify that** Python syntax checking (`compile()`) is performed on saved `.py` files (unless it's the server script itself, identified by `THIS_SCRIPT_NAME` from `config_manager.py`).
36. **Verify that** Shell syntax checking (`bash -n`) is performed on saved `.sh` files (`script_runner.py`).
37. **Verify that** script execution (`script_runner.py::run_script`) only occurs if the corresponding `auto_run_python` or `auto_run_shell` flag is enabled *in the server's current runtime configuration* (`APP_CONFIG`).
38. **Verify that** script execution (`script_runner.py`) captures stdout/stderr to the correct log files in the `logs/` directory and handles timeouts.

**V. Popup UI & Configuration**

39. **Verify that** when the popup (`extension/popup.html`) is opened, it fetches and displays the server port number specifically associated with the *current active tab* from storage, defaulting to the correct default port (e.g., 5000) if none is stored for that tab.
40. **Verify that** the popup (`extension/popup.html`) fetches and displays the current *global* activation state correctly.
41. **Verify that** changing the port number in the popup input field triggers a message from `extension/popup.js` to `extension/background.js` to store the new port *for the current tab*.
42. **Verify that** clicking "Test Connection" in the popup sends the request to the port number *currently visible* in the popup's input field.
43. **Verify that** after a successful "Test Connection", the popup displays the server's CWD, Save Dir, Log Dir, Git status, and the *server's reported running configuration* for auto-run Python/Shell toggles.
44. **Verify that** toggling the activation switch in the popup updates the *global* activation state via `extension/background.js`.
45. **Verify that** toggling the "Auto-Run Py/Sh" switches in the popup sends an `updateConfig` message, targeting the server associated with the *current tab's* port, and updates the server's *runtime* state immediately.
46. **Verify that** the popup (`extension/popup.html`) status message correctly reflects connection status, success/failure of operations, and configuration update results (including whether a server restart is needed for port changes vs. immediate effect for auto-run).

**VI. Server Setup & Configuration**

47. **Verify that** the `server.py` script starts without basic Python syntax errors (like missing colons).
48. **Verify that** the server correctly loads initial settings from `server_config.json` if present, using defaults otherwise (`config_manager.py`).
49. **Verify that** command-line arguments (`--port`, `--shell`, `--enable-python-run`) correctly override settings from the config file or defaults for the *running server instance* (`config_manager.py`).
50. **Verify that** the `/update_config` endpoint saves changes (port, auto-run flags) back to `server_config.json` (`config_manager.py`).
51. **Verify that** the `/update_config` endpoint updates the *live runtime configuration* for `auto_run_python` and `auto_run_shell` in the `APP_CONFIG` dictionary used by the running server instance (`routes/config_routes.py`).
