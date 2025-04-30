from flask import Flask, request, jsonify, send_from_directory, render_template_string
from flask_cors import CORS
import os
import datetime
import subprocess
import re
import sys
from pathlib import Path

app = Flask(__name__)
CORS(app)

SAVE_FOLDER = 'received_codes' # Used for non-Git tracked files / fallbacks
LOG_FOLDER = 'logs'
os.makedirs(SAVE_FOLDER, exist_ok=True)
os.makedirs(LOG_FOLDER, exist_ok=True)

# --- Regex to EXTRACT filename FROM NEW @@FILENAME@@ MARKER ---
FILENAME_EXTRACT_REGEX = re.compile(
    r"^\s*(?://|#)\s*@@FILENAME@@\s+(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE
)

# --- Filename Sanitization ---
FILENAME_SANITIZE_REGEX = re.compile(r'[^a-zA-Z0-9._-]')
MAX_FILENAME_LENGTH = 100

# --- Language Detection (Unchanged) ---
LANGUAGE_PATTERNS = {
    '.py': re.compile(r'\b(def|class|import|from|if|else|elif|for|while|try|except|print)\b', re.MULTILINE),
    '.js': re.compile(r'\b(function|var|let|const|if|else|for|while|document|window|console\.log)\b', re.MULTILINE),
    '.html': re.compile(r'<(!DOCTYPE html|html|head|body|div|p|a|img|script|style)\b', re.IGNORECASE | re.MULTILINE),
    '.css': re.compile(r'[{};]\s*([a-zA-Z-]+)\s*:', re.MULTILINE),
    '.json': re.compile(r'^\s*\{.*\}\s*$|^\s*\[.*\]\s*$', re.DOTALL),
    '.md': re.compile(r'^#+\s|\*\*|\*|_|`|> |-', re.MULTILINE),
    '.sql': re.compile(r'\b(SELECT|INSERT|UPDATE|DELETE|CREATE|TABLE|FROM|WHERE|JOIN)\b', re.IGNORECASE | re.MULTILINE),
    '.xml': re.compile(r'<(\?xml|!DOCTYPE|[a-zA-Z:]+)', re.MULTILINE),
}
DEFAULT_EXTENSION = '.txt'

# --- Helper Functions (Sanitize, Detect Lang, Generate Timestamped) - Unchanged ---
def sanitize_filename(filename: str) -> str | None:
    if not filename or filename.isspace(): return None
    if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
        print(f"Warning: Rejected potentially unsafe filename pattern: {filename}", file=sys.stderr)
        return None
    filename = os.path.basename(filename)
    if filename.startswith('.'):
        print(f"Warning: Rejected filename starting with '.': {filename}", file=sys.stderr)
        return None
    sanitized = FILENAME_SANITIZE_REGEX.sub('_', filename)
    if len(sanitized) > MAX_FILENAME_LENGTH:
        base, ext = os.path.splitext(sanitized)
        if len(ext) > (MAX_FILENAME_LENGTH - 2): ext = ext[:MAX_FILENAME_LENGTH - 2] + "~"
        base = base[:MAX_FILENAME_LENGTH - len(ext) - 1]
        sanitized = f"{base}{ext}"
    if not os.path.splitext(sanitized)[0] and len(sanitized) <= 1: return None
    return sanitized

def detect_language_and_extension(code: str) -> tuple[str, str]:
    first_lines = code.splitlines()[:3]
    if first_lines:
        if first_lines[0].startswith('#!/usr/bin/env python') or first_lines[0].startswith('#!/usr/bin/python'): return '.py', 'Python'
        if first_lines[0].startswith('#!/bin/bash') or first_lines[0].startswith('#!/bin/sh'): return '.sh', 'Shell'
        if first_lines[0].startswith('<?php'): return '.php', 'PHP'
    if LANGUAGE_PATTERNS['.html'].search(code): return '.html', 'HTML'
    if LANGUAGE_PATTERNS['.xml'].search(code): return '.xml', 'XML'
    if LANGUAGE_PATTERNS['.json'].search(code):
         try: import json; json.loads(code); return '.json', 'JSON'
         except: pass
    if LANGUAGE_PATTERNS['.css'].search(code): return '.css', 'CSS'
    if LANGUAGE_PATTERNS['.py'].search(code): return '.py', 'Python'
    if LANGUAGE_PATTERNS['.js'].search(code): return '.js', 'JavaScript'
    if LANGUAGE_PATTERNS['.sql'].search(code): return '.sql', 'SQL'
    if LANGUAGE_PATTERNS['.md'].search(code): return '.md', 'Markdown'
    print("Warning: Could not reliably detect language. Defaulting to .txt", file=sys.stderr)
    return DEFAULT_EXTENSION, 'Text'

def generate_timestamped_filepath(extension: str = '.txt', base_prefix="code"):
    today = datetime.datetime.now().strftime("%Y%m%d")
    counter = 1
    if not extension.startswith('.'): extension = '.' + extension
    while True:
        filename = f"{base_prefix}_{today}_{counter:03d}{extension}"
        filepath = os.path.join(SAVE_FOLDER, filename)
        if not os.path.exists(filepath): return filepath
        counter += 1

# --- NEW Git Helper Functions ---
def is_git_repository() -> bool:
    """Checks if the current directory is part of a Git repository."""
    try:
        # Use --git-dir to check without printing errors for non-repo dirs
        result = subprocess.run(['git', 'rev-parse', '--git-dir'], capture_output=True, text=True, check=False, encoding='utf-8')
        is_repo = result.returncode == 0
        if is_repo:
             print("Info: Git repository detected in current working directory.", file=sys.stderr)
        else:
             print("Info: Not running inside a Git repository.", file=sys.stderr)
        return is_repo
    except FileNotFoundError:
        print("Warning: 'git' command not found. Cannot perform Git operations.", file=sys.stderr)
        return False
    except Exception as e:
         print(f"Error checking for Git repository: {e}", file=sys.stderr)
         return False

def is_git_tracked(filepath_relative: str) -> bool:
    """Checks if a specific file is tracked by Git."""
    if not IS_REPO: return False # Don't bother if not in a repo
    try:
        # Use relative path, ensure forward slashes
        git_path = Path(filepath_relative).as_posix()
        # ls-files lists tracked files. --error-unmatch causes non-zero exit if not tracked.
        result = subprocess.run(
            ['git', 'ls-files', '--error-unmatch', git_path],
            capture_output=True, text=True, check=False, encoding='utf-8'
        )
        is_tracked = result.returncode == 0
        print(f"Info: Git track status for '{git_path}': {is_tracked}", file=sys.stderr)
        return is_tracked
    except Exception as e:
        print(f"Error checking Git track status for '{filepath_relative}': {e}", file=sys.stderr)
        return False

def update_and_commit_file(filepath: Path, code_content: str, marker_filename: str) -> bool:
    """Overwrites, adds, and commits a file using Git."""
    if not IS_REPO:
        print("Error: Cannot commit, not in a Git repository.", file=sys.stderr)
        return False

    filepath_relative = str(filepath.relative_to(Path.cwd())) # Get relative path for Git commands
    git_path = filepath.as_posix() # Ensure forward slashes

    try:
        # 1. Overwrite local file
        print(f"Overwriting local file: {filepath_relative}", file=sys.stderr)
        filepath.write_text(code_content, encoding='utf-8')

        # 2. Stage the file
        print(f"Running: git add {filepath_relative}", file=sys.stderr)
        add_result = subprocess.run(['git', 'add', filepath_relative], capture_output=True, text=True, check=False, encoding='utf-8')
        if add_result.returncode != 0:
            print(f"Error: 'git add {filepath_relative}' failed:", file=sys.stderr)
            print(add_result.stderr, file=sys.stderr)
            return False

        # 3. Commit the file
        commit_message = f"Update {marker_filename} from AI Code Capture"
        print(f"Running: git commit -m \"{commit_message}\"", file=sys.stderr)
        commit_result = subprocess.run(['git', 'commit', '-m', commit_message], capture_output=True, text=True, check=False, encoding='utf-8')
        if commit_result.returncode != 0:
            # Check if commit failed because there were no changes staged (maybe file content was identical)
            if "nothing to commit, working tree clean" in commit_result.stdout or \
               "no changes added to commit" in commit_result.stdout:
                print("Info: No changes detected by Git for commit.", file=sys.stderr)
                return True # Treat as success if no changes needed committing
            else:
                print(f"Error: 'git commit' failed:", file=sys.stderr)
                print(commit_result.stderr, file=sys.stderr)
                return False

        print(f"Successfully committed changes for {filepath_relative}.", file=sys.stderr)
        return True

    except IOError as e:
        print(f"Error writing file {filepath_relative}: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"An unexpected error occurred during Git update/commit for {filepath_relative}: {e}", file=sys.stderr)
        return False


# --- Global check if running inside a Git repo ---
IS_REPO = is_git_repository()

# --- Original Script Runner (Unchanged) ---
AUTO_RUN_ON_SYNTAX_OK = True
def run_script(filepath):
    filename_base = Path(filepath).stem
    logpath = os.path.join(LOG_FOLDER, f"{filename_base}.log")
    try:
        python_exe = sys.executable
        result = subprocess.run(
            [python_exe, filepath], capture_output=True, text=True, timeout=10,
            encoding='utf-8', check=False
        )
        os.makedirs(LOG_FOLDER, exist_ok=True)
        with open(logpath, 'w', encoding='utf-8') as f:
            f.write(f"--- STDOUT ---\n{result.stdout}\n")
            f.write(f"--- STDERR ---\n{result.stderr}\n")
            f.write(f"--- Return Code: {result.returncode} ---\n")
        return result.returncode == 0, logpath
    except subprocess.TimeoutExpired:
        os.makedirs(LOG_FOLDER, exist_ok=True)
        with open(logpath, 'w', encoding='utf-8') as f: f.write("Error: Script timed out after 10 seconds.\n")
        return False, logpath
    except Exception as e:
        os.makedirs(LOG_FOLDER, exist_ok=True)
        with open(logpath, 'w', encoding='utf-8') as f: f.write(f"Error running script: {str(e)}\n")
        return False, logpath

# --- Modified Submit Route ---
@app.route('/submit_code', methods=['POST', 'OPTIONS'])
def submit_code():
    if request.method == 'OPTIONS': return '', 204

    if request.method == 'POST':
        data = request.get_json()
        if not data: return jsonify({'status': 'error', 'message': 'No JSON data received'}), 400
        received_code = data.get('code', '')
        if not received_code or received_code.isspace(): return jsonify({'status': 'error', 'message': 'Empty code received'}), 400

        save_filepath_str = None      # The final path where code was written (Git or timestamped)
        final_save_filename = None    # The basename of save_filepath_str
        code_to_process = received_code # Code to check syntax/run (marker potentially removed)
        extracted_filename_raw = None # Original filename from marker
        detected_language_name = "Unknown"
        marker_line_length = 0
        was_git_updated = False     # Flag to track if Git commit was attempted/successful

        # --- Try to extract filename from marker ---
        match = FILENAME_EXTRACT_REGEX.search(received_code)
        if match:
            extracted_filename_raw = match.group(1).strip()
            marker_line_length = match.end() # Position after the marker line
            # Also skip potential newline right after marker
            if marker_line_length < len(received_code) and received_code[marker_line_length] == '\n':
                marker_line_length += 1
            print(f"Found filename marker: '{extracted_filename_raw}'", file=sys.stderr)
            sanitized = sanitize_filename(extracted_filename_raw)

            if sanitized:
                print(f"Sanitized filename: '{sanitized}'", file=sys.stderr)
                # Check if this sanitized file exists AND is tracked by Git
                git_target_path = Path(sanitized).resolve() # Absolute path for local checks
                is_tracked = is_git_tracked(str(git_target_path.relative_to(Path.cwd()))) # Check relative path

                if is_tracked:
                    print(f"File '{sanitized}' is tracked by Git. Preparing commit.", file=sys.stderr)
                    code_to_process = received_code[marker_line_length:] # Use code *without* marker for commit/processing
                    # Attempt to update and commit
                    commit_success = update_and_commit_file(git_target_path, code_to_process, extracted_filename_raw)
                    if commit_success:
                        save_filepath_str = str(git_target_path)
                        final_save_filename = sanitized
                        was_git_updated = True
                        print(f"Git update successful for {final_save_filename}", file=sys.stderr)
                    else:
                        print(f"Warning: Git update/commit failed for {sanitized}. Falling back to saving in '{SAVE_FOLDER}'.", file=sys.stderr)
                        # Fall through to save timestamped version with original code
                        code_to_process = received_code # Revert to original code with marker for saving
                else:
                    print(f"Info: File '{sanitized}' from marker not tracked by Git. Saving to '{SAVE_FOLDER}'.", file=sys.stderr)
                    # Fall through to save timestamped version
            else:
                print(f"Warning: Invalid extracted filename '{extracted_filename_raw}'. Saving to '{SAVE_FOLDER}'.", file=sys.stderr)
                # Fall through to save timestamped version
        else:
             print("Info: No filename marker found. Saving to '{SAVE_FOLDER}'.", file=sys.stderr)
             # Fall through to save timestamped version

        # --- Fallback / Timestamped Save Logic ---
        if save_filepath_str is None: # Only if Git path wasn't successfully used
            detected_ext, detected_language_name = detect_language_and_extension(received_code)
            base_prefix = detected_language_name.lower().replace(" ", "_")
            save_filepath_str = generate_timestamped_filepath(extension=detected_ext, base_prefix=base_prefix)
            final_save_filename = os.path.basename(save_filepath_str)
            code_to_process = received_code # Use original code as received
            print(f"Using generated filepath: '{save_filepath_str}'", file=sys.stderr)
            # Save the original code to the timestamped file
            try:
                os.makedirs(SAVE_FOLDER, exist_ok=True)
                with open(save_filepath_str, 'w', encoding='utf-8') as f:
                    f.write(code_to_process)
                print(f"Code saved successfully to {save_filepath_str}", file=sys.stderr)
            except Exception as e:
                 print(f"Error: Failed to save fallback file '{save_filepath_str}': {str(e)}", file=sys.stderr)
                 return jsonify({'status': 'error', 'message': f'Failed to save file: {str(e)}'}), 500


        # --- Process the code (Syntax check / Run) ---
        is_likely_python = final_save_filename.lower().endswith('.py')
        syntax_ok = None
        run_success = None
        log_filename = None

        if is_likely_python:
            print(f"File '{final_save_filename}' is Python, performing checks.", file=sys.stderr)
            try:
                # Compile the code content that was intended for the final file
                compile(code_to_process, save_filepath_str, 'exec')
                syntax_ok = True
                print(f"Syntax OK for {final_save_filename}", file=sys.stderr)
                if AUTO_RUN_ON_SYNTAX_OK:
                    print(f"Attempting to run {final_save_filename}", file=sys.stderr)
                    # Run the actual file on disk
                    run_success, logpath = run_script(save_filepath_str)
                    log_filename = os.path.basename(logpath) if logpath else None
                    print(f"Script run completed. Success: {run_success}, Log: {log_filename}", file=sys.stderr)
            except SyntaxError as e:
                syntax_ok = False
                print(f"Syntax Error in {final_save_filename}: Line {e.lineno}, Offset: {e.offset}, Message: {e.msg}", file=sys.stderr)
                log_filename_base = Path(save_filepath_str).stem
                logpath_err = os.path.join(LOG_FOLDER, f"{log_filename_base}_syntax_error.log")
                try:
                    os.makedirs(LOG_FOLDER, exist_ok=True)
                    original_marker_name = extracted_filename_raw or 'None'
                    with open(logpath_err, 'w', encoding='utf-8') as f:
                         f.write(f"Syntax Error:\nFile: {final_save_filename} (Marker: {original_marker_name})\nLine: {e.lineno}, Offset: {e.offset}\nMessage: {e.msg}\nCode Context:\n{e.text}")
                    log_filename = os.path.basename(logpath_err)
                except Exception as log_e: print(f"Error writing syntax error log: {log_e}", file=sys.stderr)
            except Exception as compile_e:
                syntax_ok = False; run_success = False
                print(f"Error during compile/run setup for {final_save_filename}: {str(compile_e)}", file=sys.stderr)
                log_filename_base = Path(save_filepath_str).stem
                logpath_err = os.path.join(LOG_FOLDER, f"{log_filename_base}_compile_error.log")
                try:
                     os.makedirs(LOG_FOLDER, exist_ok=True)
                     original_marker_name = extracted_filename_raw or 'None'
                     with open(logpath_err, 'w', encoding='utf-8') as f:
                         f.write(f"Error during compile/run setup:\nFile: {final_save_filename} (Marker: {original_marker_name})\nError: {str(compile_e)}\n")
                     log_filename = os.path.basename(logpath_err)
                except Exception as log_e: print(f"Error writing compile error log: {log_e}", file=sys.stderr)
        else:
            print(f"File '{final_save_filename}' is not Python, skipping syntax check and run.", file=sys.stderr)

        # Return Response
        response_data = {
            'status': 'success',
            'saved_as': final_save_filename, # Report actual saved name (Git or timestamped)
            'log_file': log_filename,
            'syntax_ok': syntax_ok,
            'run_success': run_success,
            'source_file_marker': extracted_filename_raw,
            'git_updated': was_git_updated, # Add Git status flag
            'detected_language': detected_language_name if not extracted_filename_raw else None
        }
        print(f"Sending response: {response_data}", file=sys.stderr)
        return jsonify(response_data)

    return jsonify({'status': 'error', 'message': f'Unsupported method: {request.method}'}), 405


# --- Log Routes (Unchanged) ---
@app.route('/logs')
def list_logs():
    log_files = []
    try:
         log_dir = os.path.abspath(LOG_FOLDER)
         log_paths = [os.path.join(log_dir, f) for f in os.listdir(log_dir) if f.endswith('.log')]
         log_paths.sort(key=lambda x: os.path.getmtime(x), reverse=True)
         log_files = [os.path.basename(p) for p in log_paths]
    except FileNotFoundError: pass
    except Exception as e: print(f"Error listing logs: {e}", file=sys.stderr)
    template = '''
    <!DOCTYPE html><html><head><title>Logs Browser</title><style>
    body{font-family:Arial,sans-serif;background:#1e1e1e;color:#d4d4d4;padding:20px}
    h1{color:#4ec9b0;border-bottom:1px solid #444;padding-bottom:10px}
    ul{list-style:none;padding:0}li{background:#252526;margin-bottom:8px;border-radius:4px}
    li a{color:#9cdcfe;text-decoration:none;display:block;padding:10px 15px;transition:background-color .2s ease}
    li a:hover{background-color:#333}p{color:#888}
    pre{background:#1e1e1e;border:1px solid #444;padding:15px;border-radius:5px;overflow-x:auto;white-space:pre-wrap;word-wrap:break-word;color:#d4d4d4}
    </style></head><body><h1>🗂️ Available Logs</h1>{% if logs %}<ul>
    {% for log in logs %}<li><a href="/logs/{{ log | urlencode }}">{{ log }}</a></li>{% endfor %}
    </ul>{% else %}<p>No logs found in '{{ log_folder_name }}'.</p>{% endif %}</body></html>
    '''
    return render_template_string(template, logs=log_files, log_folder_name=LOG_FOLDER)

@app.route('/logs/<path:filename>')
def serve_log(filename):
    print(f"Request received for log file: {filename}", file=sys.stderr)
    log_dir = os.path.abspath(LOG_FOLDER)
    requested_path = os.path.abspath(os.path.join(log_dir, filename))
    if not requested_path.startswith(log_dir) or '..' in filename:
         print(f"Warning: Forbidden access attempt for log: {filename}", file=sys.stderr)
         return "Forbidden", 403
    try:
        return send_from_directory(LOG_FOLDER, filename, mimetype='text/plain', as_attachment=False)
    except FileNotFoundError: return "Log file not found", 404
    except Exception as e:
        print(f"Error serving log file {filename}: {e}", file=sys.stderr)
        return "Error serving file", 500


if __name__ == '__main__':
    host_ip = '127.0.0.1'
    port_num = 5000
    print(f"Starting Flask server on http://{host_ip}:{port_num}", file=sys.stderr)
    print(f"Saving non-Git files to: {Path(SAVE_FOLDER).resolve()}", file=sys.stderr)
    print(f"Saving logs to: {Path(LOG_FOLDER).resolve()}", file=sys.stderr)
    print("Will use filename from '@@FILENAME@@' marker if present and valid.", file=sys.stderr)
    if IS_REPO:
        print("Git integration ENABLED. Will update tracked files and commit.")
    else:
        print("Git integration DISABLED (Not in a Git repo or git command failed).")
    print("Will attempt language detection for fallback filename extensions.", file=sys.stderr)
    print("*** CORS enabled for all origins ***")
    app.run(host=host_ip, port=port_num, debug=False)
# --- END OF FILE server.py ---