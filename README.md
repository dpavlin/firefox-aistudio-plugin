# AI Code Capture

Firefox plugin for Google AI Studio integration with local file system

## Motivation

Google Gemini models (like 2.5 Pro) are powerful tools for discussing and modifying your code, often freely available via the Google AI Studio web interface.

However, manually copy-pasting changes between the web UI and your local files becomes tedious quickly. This project automates that process by allowing the AI to directly specify file modifications, which are then applied to your local file system via a Firefox extension and a local Python server.

## Install Local Dependencies

Ensure you have Python 3 and Flask installed. On Debian/Ubuntu:
```bash
sudo apt update
sudo apt install python3 python3-pip python3-flask python3-flask-cors
```
Or using pip (recommended in a virtual environment):
```bash
python3 -m venv venv
source venv/bin/activate  # On Linux/macOS
# venv\Scripts\activate  # On Windows
pip install Flask Flask-Cors
```

## Start Local Server

Navigate to the project's root directory (where `server.py` is located) in your terminal.

```bash
# Using system Python
python3 server.py [options]

# Or using virtual environment Python
python server.py [options]
```

**Server Options:**

*   `--port <port_number>`: Specifies the port the server listens on (default defined in `config_manager.py`, usually 5000). Example: `python3 server.py --port 5001`
*   `--enable-python-run`: **DANGEROUS!** Allows the server to automatically execute received Python (`.py`) code blocks. Use with extreme caution and only on trusted code. Disabled by default.
*   `--shell`: **EXTREMELY DANGEROUS!** Allows the server to automatically execute received Shell (`.sh`) code blocks. Can easily lead to system compromise if used with untrusted code. Disabled by default.

The server needs to be running whenever you want to use the extension to save files.

## Load Temporary Add-on in Firefox

1.  Open Firefox and navigate to `about:debugging`.
2.  Click "This Firefox" on the left sidebar.
3.  Click the "Load Temporary Add-on..." button.
4.  Navigate to the directory containing this project and select the `extension/manifest.json` file.

The extension icon should appear in your Firefox toolbar.

## Configure the Extension

1.  Navigate to a Google AI Studio tab ([https://aistudio.google.com/](https://aistudio.google.com/)).
2.  Click the AI Code Capture extension icon in your toolbar.
3.  Enter the correct `Port` number that your local server is running on for **this specific tab**.
4.  Click the "Test Connection" button to verify the extension can reach the server and to populate server info.
5.  Ensure the "Active" toggle is enabled.

## Packing and Sending Source Code (Optional Context)

To provide existing code context to the AI model:

```bash
# Run from your project's root directory
zip /tmp/firefox-aistudio-plugin-context.zip $(git ls-files)
```
*(Requires `zip` command and running within a Git repository)*

Upload the generated `/tmp/firefox-aistudio-plugin-context.zip` file to AI Studio using the "Add files" button.

## Google AI Studio Prompt Instructions

**Crucial:** Instruct the AI how to format its output. Include the following instructions in your prompt to the AI model (see `prompt.txt` for the recommended text):

> **CRUCIAL INSTRUCTIONS FOR CODE BLOCK FORMATTING:**
>
> 1.  **Show Full Content:** When you are asked to show the modified content of a file, ALWAYS provide the *complete* file content in the code block.
> 2.  **Mandatory Filename Marker:** You **MUST** include a filename marker at the very beginning of the code block.
> 3.  **Marker Format:** The marker format is *exactly*:
>     `@@FILENAME@@ path/relative/to/project/root.ext`
>     *(Replace `path/relative/to/project/root.ext` with the correct file path relative to the project root.)*
> 4.  **Strict First Line Placement:** The `@@FILENAME@@` marker **MUST** be on the **VERY FIRST LINE** of the code block.
> 5.  **No Prefix:** Do **NOT** put *anything* before the `@@FILENAME@@` marker on the first line (no comments like `//` or `#`, no code, nothing except optional leading whitespace which is ignored).
> 6.  **Code Starts on Line 2:** The actual code content of the file **MUST** begin on the second line.
> 7.  **(Optional) End Marker:** For clarity in our chat, you *may* add a separator line after the *entire* code block, like `--- END OF @@FILENAME@@ path/to/file.ext ---`.

## How it Works

1.  The Firefox extension (`content.js`) monitors the AI Studio page for new code blocks.
2.  When a block appears, it checks if it starts with the `@@FILENAME@@` marker.
3.  If a marker is found, it waits for the block content to stabilize (stop changing for a few seconds).
4.  It then sends the full code block content to the background script (`background.js`).
5.  `background.js` looks up the server port configured for that specific tab and forwards the code (as JSON) to the local Python server's `/submit_code` endpoint.
6.  The Python server (`routes/submit.py`) receives the code:
    *   It verifies the `@@FILENAME@@` marker on the first line.
    *   If found, it extracts and sanitizes the filename, then removes the first line from the code content.
    *   It attempts to strip an optional `--- END OF @@FILENAME@@ ... ---` marker from the last line.
    *   It checks if the sanitized path corresponds to a tracked file in a local Git repository (if the server is run within one).
    *   If it's a tracked Git file, it overwrites the local file with the stripped content and runs `git add` and `git commit`.
    *   If not tracked, or not in a repo, or if the marker was invalid, it saves the (potentially stripped) code to the `received_codes/` subdirectory (either using the sanitized filename or a timestamped fallback name).
    *   If server execution flags (`--enable-python-run` or `--shell`) are active, it performs syntax checks and potentially executes the saved script, capturing output.
    *   It sends a JSON response back to the extension with the status (success/error), save location, Git status, and any execution output/errors.
7.  The extension receives the response and updates the highlight on the code block in AI Studio (green for success, red for error). The highlight remains persistent.
8.  Execution output (if any) can be viewed by opening the extension popup for the relevant tab.

## Git Integration Details

*   The server automatically runs `git add` and `git commit` for **tracked** files specified via a valid `@@FILENAME@@` marker *if the server is run from within a Git repository*.
*   The commit message is generic (e.g., "Update filename.ext from AI Code Capture").
*   It **will not** automatically `git add` *new* files mentioned in the marker. You must manually `git add` new files first if you want them to be tracked and updated by the plugin.
*   If a file exists but is *not* tracked (e.g., is in `.gitignore` or never added), it will be saved to the `received_codes/` directory using the name from the marker.

## Multiple Projects in Separate Tabs

*   Run separate instances of the Python server for each project, ensuring each instance runs on a **different port** using the `--port <number>` option.
*   In Firefox, open each project's AI Studio chat in a separate tab.
*   For each tab, click the extension icon, and configure the "Port" setting in the popup to match the specific server instance running for that project. The extension will remember the port setting for each tab.

## Viewing Fallback Files

Files saved because no valid marker was found, or because a marked file wasn't tracked by Git, are placed in the `received_codes/` directory next to `server.py`.

You can use the provided utility script to browse these files interactively:
```bash
python3 list-received_codes_curses.py [path/to/received_codes]
```
(Defaults to `./received_codes`) Requires `curses` support (standard on Linux/macOS).
