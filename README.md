# AI Code Capture

Firefox plugin for Google AI Studio integration with local file system

## Motivation

Google Gemini 2.5 Pro is currently best model for discussing your code, freely available via the Google AI Studio web interface.

However, manually copy-pasting changes gets old quickly. This project automates that process.

## Install Local Dependencies

```bash
sudo apt install python3-flask python3-flask-cors
```

## Start Local Server

```bash
# Navigate to your project's root directory first
# Example: Start on default port 5000
python3 server.py

# Example: Start on port 5001
python3 server.py -p 5001

# Example: Enable Python execution (Use with caution!)
python3 server.py --python

# Example: Enable Shell execution (DANGEROUS!)
python3 server.py --shell

# Example: Combine options
python3 server.py -p 5050 --python --shell
```
*   `-p <port>` or `--port <port>`: Specifies the listening port (default: 5000).
*   `--python`: Enables auto-execution of received Python files. **Use with caution!**
*   `--shell`: Enables auto-execution of received Shell scripts. **DANGEROUS! Use only if you fully trust the AI's output and understand the risks.**

*Note: The server no longer uses `server_config.json`. Port and auto-run settings are controlled only at startup.*

## Load Temporary Add-on in Firefox

1.  Go to `about:debugging` in Firefox.
2.  Click "This Firefox".
3.  Click "Load Temporary Add-on...".
4.  Select the `manifest.json` file inside the `extension` directory.

## Configure Extension Popup

1.  Click the AI Code Capture icon in the Firefox toolbar.
2.  Enter the **Port** number corresponding to the running server instance you want *this specific AI Studio tab* to communicate with.
3.  Use the **Active** toggle to enable/disable the extension globally.
4.  Click **Test** to verify the connection and view server status (including read-only auto-run status based on server flags).

*Port settings are saved per-tab.*

## Pack and Send Source Code to Model

To provide context to the AI:

```bash
# Run from your project's root directory
zip /tmp/firefox-aistudio-plugin.zip $(git ls-files)
```

*Upload `/tmp/firefox-aistudio-plugin.zip` to AI Studio.*

## Google AI Studio Prompt Instructions

**Crucial:** Instruct the AI how to format its output. Include this in your prompt (refer to `prompt.txt` for the full recommended prompt):

> ALWAYS add in the very first line marker `@@FILENAME@@ path/to/modified/file.ext`.

## Git Integration

*   If the server runs within a local Git repository, it will automatically `git add` and `git commit` changes for **tracked** files specified via the `@@FILENAME@@` marker.
*   It **will not** add *new* files to Git automatically; you must `git add` them manually first.

## Multiple Projects in Separate Tabs

*   Use the server's `-p <number>` option to run multiple instances on different ports for different projects.
*   Configure the matching port number in the extension popup for each corresponding AI Studio tab. The extension saves the port setting independently for each tab.
