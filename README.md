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
# Examples:
# python3 server.py                                    # Run on default port 5000, auto-run disabled
# python3 server.py -p 5001                            # Run on port 5001, auto-run disabled
# python3 server.py --enable-python-run                # Run on port 5000, Python auto-run enabled
# python3 server.py -p 5002 --shell --enable-python-run # Run on port 5002, enable Shell and Python auto-run
python3 server.py [--port <port_number>] [--shell] [--enable-python-run]
```
*Default port is 5000.*
*Auto-run features (`--shell`, `--enable-python-run`) are **DANGEROUS** and should be used with extreme caution.*

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

**Crucial:** Instruct the AI how to format its output. Use the content from `prompt.txt` or ensure your instructions include:

> **CRUCIAL INSTRUCTIONS FOR CODE BLOCK FORMATTING:**
>
> 1.  **Show Full Content:** When you are asked to show the modified content of a file, ALWAYS provide the *complete* file content in the code block.
> 2.  **Mandatory Filename Marker:** You **MUST** include a filename marker at the very beginning of the code block.
> 3.  **Marker Format:** The marker format is *exactly*:
>     `@@FILENAME@@ path/relative/to/project/root.ext`
> 4.  **Strict First Line Placement:** The `@@FILENAME@@` marker **MUST** be on the **VERY FIRST LINE** of the code block.
> 5.  **No Prefix:** Do **NOT** put *anything* before the `@@FILENAME@@` marker on the first line.
> 6.  **Code Starts on Line 2:** The actual code content of the file **MUST** begin on the second line.
> 7.  **(Optional) End Marker:** For clarity in our chat, you *may* add a separator line after the *entire* code block, like `--- END OF @@FILENAME@@ path/to/file.ext ---`.

## Git Integration

*   If the server runs within a local Git repository, it will automatically `git add` and `git commit` changes for **tracked** files specified via the `@@FILENAME@@` marker.
*   It **will not** add *new* files to Git automatically; you must `git add` them manually first.

## Multiple Projects in Separate Tabs

*   Use the server's `--port <number>` option to run multiple instances on different ports for different projects.
*   Configure the matching port number in the extension popup for each corresponding AI Studio tab. The port setting is now tab-specific.

## Execution Output

*   If auto-run (`--shell` or `--enable-python-run`) is enabled via server flags, the stdout and stderr from script execution are no longer saved to log files.
*   Instead, the output is included directly in the JSON response sent back to the extension (under keys like `run_stdout`, `run_stderr`). This output is not currently displayed in the popup UI.
