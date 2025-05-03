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
# Auto-run for Python/Shell is DISABLED by default.
# Use flags to enable (DANGEROUS):
python3 server.py [--port <port_number>] [--enable-python-run] [--shell]
```
*Default port is 5000.*
*Auto-run settings are controlled **only** by server startup flags.*

## Load Temporary Add-on in Firefox

1.  Go to `about:debugging` in Firefox.
2.  Click "This Firefox".
3.  Click "Load Temporary Add-on...".
4.  Select the `manifest.json` file inside the `extension` directory.

## Pack and Send Source Code to Model

To provide context to the AI:

```bash
# Run from your project's root directory
zip /tmp/firefox-aistudio-plugin.zip $(git ls-files)
```

*Upload `/tmp/firefox-aistudio-plugin.zip` to AI Studio.*

## Google AI Studio Prompt Instructions

**Crucial:** Instruct the AI how to format its output. Use the content of `prompt.txt`.

## Git Integration

*   If the server runs within a local Git repository, it will automatically `git add` and `git commit` changes for **tracked** files specified via the `@@FILENAME@@` marker.
*   It **will not** add *new* files to Git automatically; you must `git add` them manually first.

## Multiple Projects in Separate Tabs

*   Use the server's `--port <number>` option to run multiple instances on different ports for different projects.
*   Configure the matching port number in the extension popup *for each corresponding AI Studio tab*. The port setting is now tab-specific.

## Execution Output

*   If auto-run is enabled via server flags, the `stdout` and `stderr` from syntax checks and script execution will be injected directly into the AI Studio page below the processed code block.
*   Execution output is *not* saved to log files.

