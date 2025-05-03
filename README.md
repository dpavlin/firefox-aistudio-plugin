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
python3 server.py [--port <port_number>] [--enable-python-run] [--shell]
```
*Default port is 5000.*
*Use `--enable-python-run` to allow execution of received Python files.*
*Use `--shell` (DANGEROUS) to allow execution of received Shell scripts.*

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

**Crucial:** Instruct the AI how to format its output. Include this in your prompt (or load from `prompt.txt`):

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
>
> **Why is this important?** An automated tool reads your code blocks. It *strictly* expects the `@@FILENAME@@` marker on the first line to identify the file and removes that line before saving. Any deviation will cause errors.

## Git Integration

*   If the server runs within a local Git repository, it will automatically `git add` and `git commit` changes for **tracked** files specified via the `@@FILENAME@@` marker.
*   It **will not** add *new* files to Git automatically; you must `git add` them manually first.

## Multiple Projects in Separate Tabs

*   Use the server's `--port <number>` option to run multiple instances on different ports for different projects.
*   Configure the matching port number in the extension popup **for each corresponding AI Studio tab**. The port setting is tab-specific.

## Execution Output

*   If `--enable-python-run` or `--shell` flags are used, the stdout/stderr from script execution is **not** saved to a file but is included in the JSON response sent back to the extension after a `/submit_code` request. This output is not currently displayed in the popup UI.
