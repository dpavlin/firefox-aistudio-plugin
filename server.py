# @@FILENAME@@ server.py
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

# --- Language Detection ---
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
    # Ensure there's an extension, otherwise default to .txt
    base, ext = os.path.splitext(sanitized)
    if not ext or len(ext) < 2:
        print(f"Warning: Sanitized filename '{sanitized}' lacks extension. Appending .txt", file=sys.stderr)
        sanitized += ".txt"
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
    # Ensure base_prefix is filesystem-safe
    safe_base_prefix = FILENAME_SANITIZE_REGEX.sub('_', base_prefix)
    if not safe_base_prefix: safe_base_prefix = "code" # Fallback if prefix becomes empty

    while True:
        filename = f"{safe_base_prefix}_{today}_{counter:03d}{extension}"
        filepath = os.path.join(SAVE_FOLDER, filename)
        if not os.path.exists(filepath): return filepath
        counter += 1

# --- Git Helper Functions ---
def is_git_repository() -> bool:
    try:
        result = subprocess.run(['git', 'rev-parse', '--git-dir'], capture_output=True, text=True, check=False, encoding='utf-8')
        is_repo = result.returncode == 0
        if not is_repo: print("Info: Not running inside a Git repository.", file=sys.stderr)
        return is_repo
    except FileNotFoundError:
        print("Warning: 'git' command not found.", file=sys.stderr)
        return False
    except Exception as e:
         print(f"Error checking for Git repository: {e}", file=sys.stderr)
         return False

def is_git_tracked(filename_relative: str) -> bool:
    """Checks if a specific file (relative to CWD) is tracked by Git."""
    if not IS_REPO: return False
    try:
        # Use the filename directly, assuming it's relative to CWD (where server.py runs)
        # git ls-files expects paths relative to repo root, which should be CWD here.
        command = ['git', 'ls-files', '--error-unmatch', filename_relative]
        print(f"Running: {' '.join(command)}", file=sys.stderr) # Log the command being run
        result = subprocess.run(
            command, capture_output=True, text=True, check=False, encoding='utf-8'
        )
        is_tracked = result.returncode == 0
        print(f"Info: Git track status for '{filename_relative}': {is_tracked}", file=sys.stderr)
        if result.returncode != 0 and result.stderr:
             print(f"Info: git ls-files stderr: {result.stderr.strip()}", file=sys.stderr)
        return is_tracked
    except Exception as e:
        print(f"Error checking Git track status for '{filename_relative}': {e}", file=sys.stderr)
        return False

def update_and_commit_file(filepath: Path, code_content: str, marker_filename: str) -> bool:
    """Overwrites, adds, and commits a file using Git."""
    if not IS_REPO: return False
    filepath_relative = str(filepath.relative_to(Path.cwd()))
    try:
        print(f"Overwriting local file: {filepath_relative}", file=sys.stderr)
        filepath.write_text(code_content, encoding='utf-8')

        print(f"Running: git add {filepath_relative}", file=sys.stderr)
        add_result = subprocess.run(['git', 'add', filepath_relative], capture_output=True, text=True, check=False, encoding='utf-8')
        if add_result.returncode != 0:
            print(f"Error: 'git add {filepath_relative}' failed:\n{add_result.stderr}", file=sys.stderr)
            return False

        commit_message = f"Update {marker_filename} from AI Code Capture"
        print(f"Running: git commit -m \"{commit_message}\"", file=sys.stderr)
        commit_result = subprocess.run(['git', 'commit', '-m', commit_message], capture_output=True, text=True, check=False, encoding='utf-8')
        if commit_result.returncode != 0:
            if "nothing to commit" in commit_result.stdout or \
               "no changes added to commit" in commit_result.stdout or \
               "nothing added to commit" in commit_result.stdout: # Added more checks
                print("Info: No changes detected by Git for commit.", file=sys.stderr)
                return True
            else:
                print(f"Error: 'git commit' failed:\n{commit_result.stderr}", file=sys.stderr)
                return False
        print(f"Successfully committed changes for {filepath_relative}.", file=sys.stderr)
        return True
    except IOError as e:
        print(f"Error writing file {filepath_relative}: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"An unexpected error during Git update/commit for {filepath_relative}: {e}", file=sys.stderr)
        return False

# --- Global check if running inside a Git repo ---
IS_REPO = is_git_repository()

# --- Script Runner (Unchanged) ---
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

        save_filepath_str = None
        final_save_filename = None
        code_to_process = received_code
        extracted_filename_raw = None
        detected_language_name = "Unknown"
        marker_line_length = 0
        was_git_updated = False
        sanitized = None # Keep track of sanitized name if marker found

        # Try to extract filename from marker
        match = FILENAME_EXTRACT_REGEX.search(received_code)
        if match:
            extracted_filename_raw = match.group(1).strip()
            marker_line_length = match.end()
            if marker_line_length < len(received_code) and received_code[marker_line_length] == '\n':
                marker_line_length += 1
            print(f"Found filename marker: '{extracted_filename_raw}'", file=sys.stderr)
            sanitized = sanitize_filename(extracted_filename_raw)

            if sanitized:
                print(f"Sanitized filename: '{sanitized}'", file=sys.stderr)
                # Check if this sanitized file exists AND is tracked by Git (use sanitized name directly)
                is_tracked = is_git_tracked(sanitized)

                if is_tracked:
                    print(f"File '{sanitized}' is tracked by Git. Preparing commit.", file=sys.stderr)
                    code_to_process = received_code[marker_line_length:] # Use code *without* marker
                    git_target_path = Path(sanitized).resolve() # Absolute path for commit function
                    commit_success = update_and_commit_file(git_target_path, code_to_process, extracted_filename_raw)
                    if commit_success:
                        save_filepath_str = str(git_target_path)
                        final_save_filename = sanitized
                        was_git_updated = True
                        print(f"Git update successful for {final_save_filename}", file=sys.stderr)
                    else:
                        print(f"Warning: Git update/commit failed for {sanitized}. Falling back to saving in '{SAVE_FOLDER}'.", file=sys.stderr)
                        # Fallback: Save original code (with marker) to timestamped file using marker name hint
                        code_to_process = received_code # Revert to original code
                        base, ext = os.path.splitext(sanitized)
                        save_filepath_str = generate_timestamped_filepath(extension=ext, base_prefix=base)
                        final_save_filename = os.path.basename(save_filepath_str)
                        print(f"Using generated filepath: '{save_filepath_str}'", file=sys.stderr)
                        try:
                            os.makedirs(SAVE_FOLDER, exist_ok=True)
                            with open(save_filepath_str, 'w', encoding='utf-8') as f: f.write(code_to_process)
                            print(f"Fallback code saved successfully to {save_filepath_str}", file=sys.stderr)
                        except Exception as e:
                             print(f"Error: Failed to save fallback file '{save_filepath_str}': {str(e)}", file=sys.stderr)
                             return jsonify({'status': 'error', 'message': f'Failed to save fallback file: {str(e)}'}), 500

                else: # File from marker exists but is not tracked by Git
                    print(f"Info: File '{sanitized}' from marker not tracked by Git. Saving to '{SAVE_FOLDER}'.", file=sys.stderr)
                    code_to_process = received_code # Keep original code with marker
                    base, ext = os.path.splitext(sanitized) # Use marker name for prefix/ext
                    save_filepath_str = generate_timestamped_filepath(extension=ext, base_prefix=base)
                    final_save_filename = os.path.basename(save_filepath_str)
                    print(f"Using generated filepath: '{save_filepath_str}'", file=sys.stderr)
                    # Save to timestamped file
                    try:
                        os.makedirs(SAVE_FOLDER, exist_ok=True)
                        with open(save_filepath_str, 'w', encoding='utf-8') as f: f.write(code_to_process)
                        print(f"Untracked code saved successfully to {save_filepath_str}", file=sys.stderr)
                    except Exception as e:
                         print(f"Error: Failed to save untracked file '{save_filepath_str}': {str(e)}", file=sys.stderr)
                         return jsonify({'status': 'error', 'message': f'Failed to save untracked file: {str(e)}'}), 500

            else: # Sanitization failed
                print(f"Warning: Invalid extracted filename '{extracted_filename_raw}'. Detecting language & saving to '{SAVE_FOLDER}'.", file=sys.stderr)
                # Fall through to language detection below, code_to_process remains original

        # Fallback / Language Detection if no valid/tracked marker file was handled
        if save_filepath_str is None:
            detected_ext, detected_language_name = detect_language_and_extension(received_code)
            base_prefix = detected_language_name.lower().replace(" ", "_")
            save_filepath_str = generate_timestamped_filepath(extension=detected_ext, base_prefix=base_prefix)
            final_save_filename = os.path.basename(save_filepath_str)
            code_to_process = received_code # Use original code
            print(f"Using language detection filepath: '{save_filepath_str}'", file=sys.stderr)
            # Save to timestamped file
            try:
                os.makedirs(SAVE_FOLDER, exist_ok=True)
                with open(save_filepath_str, 'w', encoding='utf-8') as f: f.write(code_to_process)
                print(f"Detected language code saved successfully to {save_filepath_str}", file=sys.stderr)
            except Exception as e:
                 print(f"Error: Failed to save detected language file '{save_filepath_str}': {str(e)}", file=sys.stderr)
                 return jsonify({'status': 'error', 'message': f'Failed to save detected language file: {str(e)}'}), 500


        # Process the code (Syntax check / Run) using the final code and path
        is_likely_python = final_save_filename.lower().endswith('.py')
        syntax_ok = None; run_success = None; log_filename = None

        if is_likely_python:
            print(f"File '{final_save_filename}' is Python, performing checks.", file=sys.stderr)
            try:
                compile(code_to_process, save_filepath_str, 'exec')
                syntax_ok = True
                print(f"Syntax OK for {final_save_filename}", file=sys.stderr)
                if AUTO_RUN_ON_SYNTAX_OK:
                    print(f"Attempting to run {final_save_filename}", file=sys.stderr)
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
            'saved_as': final_save_filename,
            'log_file': log_filename,
            'syntax_ok': syntax_ok,
            'run_success': run_success,
            'source_file_marker': extracted_filename_raw,
            'git_updated': was_git_updated,
            'detected_language': detected_language_name if extracted_filename_raw is None else None
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