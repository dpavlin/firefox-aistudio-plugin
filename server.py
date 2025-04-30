from flask import Flask, request, jsonify, send_from_directory, render_template_string
from flask_cors import CORS
import os
import datetime
import subprocess
import re
import sys
import argparse
from pathlib import Path
import threading # Import the threading module

# --- Argument Parser ---
parser = argparse.ArgumentParser(description='AI Code Capture Server')
parser.add_argument(
    '-p', '--port', type=int, default=5000,
    help='Port number to run the Flask server on (default: 5000)'
)
args = parser.parse_args()
SERVER_PORT = args.port

# --- Flask App Setup ---
app = Flask(__name__)
CORS(app)

# --- Create a Lock for serializing requests ---
request_lock = threading.Lock()
print("Request lock initialized.", file=sys.stderr)

# --- Configuration & Paths ---
SAVE_FOLDER = 'received_codes'; LOG_FOLDER = 'logs'
SERVER_DIR = Path(__file__).parent.resolve() # Assume server runs from repo root
SAVE_FOLDER_PATH = SERVER_DIR / SAVE_FOLDER
LOG_FOLDER_PATH = SERVER_DIR / LOG_FOLDER
THIS_SCRIPT_NAME = Path(__file__).name
os.makedirs(SAVE_FOLDER_PATH, exist_ok=True)
os.makedirs(LOG_FOLDER_PATH, exist_ok=True)

# --- Regex & Constants ---
FILENAME_EXTRACT_REGEX = re.compile(r"^\s*(?://|#)\s*@@FILENAME@@\s+(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
FILENAME_SANITIZE_REGEX = re.compile(r'[^a-zA-Z0-9._\-\/]')
MAX_FILENAME_LENGTH = 200
LANGUAGE_PATTERNS = {'.py': re.compile(r'\b(def|class|import|from|if|else|elif|for|while|try|except|print)\b', re.MULTILINE), '.js': re.compile(r'\b(function|var|let|const|if|else|for|while|document|window|console\.log)\b', re.MULTILINE), '.html': re.compile(r'<(!DOCTYPE html|html|head|body|div|p|a|img|script|style)\b', re.IGNORECASE | re.MULTILINE), '.css': re.compile(r'[{};]\s*([a-zA-Z-]+)\s*:', re.MULTILINE), '.json': re.compile(r'^\s*\{.*\}\s*$|^\s*\[.*\]\s*$', re.DOTALL), '.md': re.compile(r'^#+\s|\*\*|\*|_|`|> |-', re.MULTILINE), '.sql': re.compile(r'\b(SELECT|INSERT|UPDATE|DELETE|CREATE|TABLE|FROM|WHERE|JOIN)\b', re.IGNORECASE | re.MULTILINE), '.xml': re.compile(r'<(\?xml|!DOCTYPE|[a-zA-Z:]+)', re.MULTILINE)}
DEFAULT_EXTENSION = '.txt'; AUTO_RUN_ON_SYNTAX_OK = True

# --- Helper Functions ---
def sanitize_filename(filename: str) -> str | None:
    if not filename or filename.isspace(): return None
    filename = filename.strip()
    if filename.startswith(('/', '\\')) or '..' in Path(filename).parts: print(f"W: Rejected potentially unsafe path pattern: {filename}", file=sys.stderr); return None
    basename = os.path.basename(filename)
    if basename.startswith('.'): print(f"W: Rejected path ending in hidden file: {filename}", file=sys.stderr); return None
    sanitized = FILENAME_SANITIZE_REGEX.sub('_', filename)
    if len(sanitized) > MAX_FILENAME_LENGTH:
        print(f"W: Filename too long, might be truncated unexpectedly: {sanitized}", file=sys.stderr)
        sanitized = sanitized[:MAX_FILENAME_LENGTH]
        base, ext = os.path.splitext(sanitized); original_base, original_ext = os.path.splitext(filename)
        if original_ext and not ext: sanitized = base + original_ext
    base, ext = os.path.splitext(os.path.basename(sanitized))
    if not ext or len(ext) < 2: print(f"W: Sanitized path '{sanitized}' lacks a proper extension. Appending .txt", file=sys.stderr); sanitized += ".txt"
    if not base: print(f"W: Sanitized filename part is empty: {sanitized}", file=sys.stderr); return None
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
    print("W: Cannot detect language. Defaulting to .txt", file=sys.stderr)
    return DEFAULT_EXTENSION, 'Text'

def generate_timestamped_filepath(extension: str = '.txt', base_prefix="code"):
    today = datetime.datetime.now().strftime("%Y%m%d"); counter = 1
    if not extension.startswith('.'): extension = '.' + extension
    safe_base_prefix = FILENAME_SANITIZE_REGEX.sub('_', base_prefix);
    if not safe_base_prefix: safe_base_prefix = "code"
    while True:
        filename = f"{safe_base_prefix}_{today}_{counter:03d}{extension}"
        filepath = SAVE_FOLDER_PATH / filename
        if not filepath.exists(): return str(filepath)
        counter += 1

def is_git_repository() -> bool:
    try:
        result = subprocess.run(['git', 'rev-parse', '--git-dir'], capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR)
        is_repo = result.returncode == 0
        if not is_repo: print("Info: Not running inside a Git repository.", file=sys.stderr)
        return is_repo
    except FileNotFoundError: print("W: 'git' command not found.", file=sys.stderr); return False
    except Exception as e: print(f"E: checking Git repository: {e}", file=sys.stderr); return False

IS_REPO = is_git_repository() # Define after function

def find_tracked_file_by_name(basename_to_find: str) -> str | None:
    if not IS_REPO: return None
    try:
        command = ['git', 'ls-files']
        print(f"Running: {' '.join(command)} from {SERVER_DIR} to find matches for '*/{basename_to_find}'", file=sys.stderr)
        result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', cwd=SERVER_DIR)
        tracked_files = result.stdout.splitlines()
        matches = [f for f in tracked_files if f.endswith('/' + basename_to_find) or f == basename_to_find]
        if len(matches) == 1: print(f"Info: Found unique tracked file match: '{matches[0]}'", file=sys.stderr); return matches[0]
        elif len(matches) > 1: print(f"W: Ambiguous filename marker '{basename_to_find}'. Found multiple tracked files: {matches}. Cannot determine target.", file=sys.stderr); return None
        else: print(f"Info: No tracked file ending in '{basename_to_find}' found in Git index.", file=sys.stderr); return None
    except subprocess.CalledProcessError as e: print(f"E: 'git ls-files' failed:\n{e.stderr}", file=sys.stderr); return None
    except Exception as e: print(f"E: checking Git for file '{basename_to_find}': {e}", file=sys.stderr); return None

def is_git_tracked(filepath_relative_to_repo: str) -> bool:
    if not IS_REPO: return False
    try:
        git_path = Path(filepath_relative_to_repo).as_posix(); command = ['git', 'ls-files', '--error-unmatch', git_path]
        print(f"Running: {' '.join(command)} from {SERVER_DIR}", file=sys.stderr)
        result = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR)
        is_tracked = result.returncode == 0
        print(f"Info: Git track status for '{git_path}': {is_tracked}", file=sys.stderr)
        if result.returncode != 0 and result.stderr: print(f"Info: git ls-files stderr: {result.stderr.strip()}", file=sys.stderr)
        return is_tracked
    except Exception as e: print(f"E: checking Git track status for '{filepath_relative_to_repo}': {e}", file=sys.stderr); return False

def update_and_commit_file(filepath_absolute: Path, code_content: str, marker_filename: str) -> bool:
    if not IS_REPO: return False
    try:
        filepath_relative_to_repo_str = str(filepath_absolute.relative_to(SERVER_DIR)); git_path_posix = filepath_absolute.relative_to(SERVER_DIR).as_posix()
        print(f"Overwriting local file: {filepath_relative_to_repo_str}", file=sys.stderr)
        filepath_absolute.parent.mkdir(parents=True, exist_ok=True)
        filepath_absolute.write_text(code_content, encoding='utf-8')
        print(f"Running: git add '{git_path_posix}' from {SERVER_DIR}", file=sys.stderr)
        add_result = subprocess.run(['git', 'add', git_path_posix], capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR)
        if add_result.returncode != 0: print(f"E: 'git add' failed:\n{add_result.stderr}", file=sys.stderr); return False
        commit_message = f"Update {marker_filename} from AI Code Capture"
        print(f"Running: git commit -m \"{commit_message}\" from {SERVER_DIR}", file=sys.stderr)
        commit_result = subprocess.run(['git', 'commit', '-m', commit_message], capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR)
        if commit_result.returncode != 0:
            no_changes_patterns = ["nothing to commit", "no changes added to commit", "nothing added to commit"]
            commit_output = commit_result.stdout + commit_result.stderr
            if any(pattern in commit_output for pattern in no_changes_patterns): print("Info: No changes detected by Git for commit.", file=sys.stderr); return True
            else: print(f"E: 'git commit' failed:\n{commit_result.stderr}", file=sys.stderr); return False
        print(f"Successfully committed changes for {filepath_relative_to_repo_str}.", file=sys.stderr)
        return True
    except IOError as e: print(f"E: writing file {filepath_absolute}: {e}", file=sys.stderr); return False
    except Exception as e: print(f"E: during Git update/commit for {filepath_absolute}: {e}", file=sys.stderr); return False

def run_script(filepath):
    filepath_obj = Path(filepath); filename_base = filepath_obj.stem
    logpath = LOG_FOLDER_PATH / f"{filename_base}.log"
    try:
        python_exe = sys.executable; run_cwd = filepath_obj.parent
        print(f"Executing: {python_exe} {filepath_obj.name} in {run_cwd}", file=sys.stderr)
        result = subprocess.run([python_exe, filepath_obj.name], capture_output=True, text=True, timeout=10, encoding='utf-8', check=False, cwd=run_cwd)
        os.makedirs(LOG_FOLDER_PATH, exist_ok=True)
        with open(logpath, 'w', encoding='utf-8') as f: f.write(f"--- STDOUT ---\n{result.stdout}\n--- STDERR ---\n{result.stderr}\n--- Return Code: {result.returncode} ---\n")
        print(f"Exec finished. RC: {result.returncode}. Log: {logpath.name}", file=sys.stderr)
        return result.returncode == 0, str(logpath)
    except subprocess.TimeoutExpired:
        print(f"E: Script timed out: {filepath}", file=sys.stderr)
        os.makedirs(LOG_FOLDER_PATH, exist_ok=True)
        with open(logpath, 'w', encoding='utf-8') as f: f.write("Error: Script timed out after 10 seconds.\n")
        return False, str(logpath)
    except Exception as e:
        print(f"E: running script {filepath}: {e}", file=sys.stderr)
        os.makedirs(LOG_FOLDER_PATH, exist_ok=True)
        with open(logpath, 'w', encoding='utf-8') as f: f.write(f"Error running script: {str(e)}\n")
        return False, str(logpath)

# --- Route Definitions ---
@app.route('/submit_code', methods=['POST', 'OPTIONS'])
def submit_code():
    if request.method == 'OPTIONS': return '', 204
    if request.method == 'POST':
        # --- Acquire Lock ---
        with request_lock:
            print("--- Handling /submit_code request (Lock acquired) ---", file=sys.stderr)
            data = request.get_json()
            if not data: print("E: No JSON data.", file=sys.stderr); return jsonify({'status': 'error', 'message': 'No JSON data received'}), 400
            received_code = data.get('code', '')
            if not received_code or received_code.isspace(): print("E: Empty code.", file=sys.stderr); return jsonify({'status': 'error', 'message': 'Empty code received'}), 400

            save_filepath_str = None; final_save_filename = None; code_to_save = received_code
            extracted_filename_raw = None; detected_language_name = "Unknown"
            marker_line_length = 0; was_git_updated = False; sanitized_path_from_marker = None
            save_target = "fallback"

            match = FILENAME_EXTRACT_REGEX.search(received_code)
            if match:
                extracted_filename_raw = match.group(1).strip(); marker_line_length = match.end()
                if marker_line_length < len(received_code) and received_code[marker_line_length] == '\n': marker_line_length += 1
                print(f"Found marker: '{extracted_filename_raw}'", file=sys.stderr)
                sanitized_path_from_marker = sanitize_filename(extracted_filename_raw)

                if sanitized_path_from_marker:
                    print(f"Sanitized relative path from marker: '{sanitized_path_from_marker}'", file=sys.stderr)
                    git_path_to_check = sanitized_path_from_marker
                    if '/' not in sanitized_path_from_marker.replace('\\', '/'):
                        print(f"Marker is basename only. Searching Git index...", file=sys.stderr)
                        found_rel_path = find_tracked_file_by_name(sanitized_path_from_marker)
                        if found_rel_path: git_path_to_check = found_rel_path
                        else: print(f"No unique match for '{sanitized_path_from_marker}'. Fallback.", file=sys.stderr); git_path_to_check = None

                    if git_path_to_check:
                        absolute_path_for_commit = (SERVER_DIR / git_path_to_check).resolve()
                        if not str(absolute_path_for_commit).startswith(str(SERVER_DIR)):
                             print(f"W: Resolved path '{absolute_path_for_commit}' outside server dir. Blocking Git.", file=sys.stderr)
                             sanitized_path_from_marker = None
                        else:
                            is_tracked = is_git_tracked(git_path_to_check)
                            if is_tracked:
                                print(f"File '{git_path_to_check}' is tracked. Committing to '{absolute_path_for_commit}'.", file=sys.stderr)
                                code_to_save = received_code[marker_line_length:]
                                commit_success = update_and_commit_file(absolute_path_for_commit, code_to_save, extracted_filename_raw)
                                if commit_success: save_filepath_str = str(absolute_path_for_commit); final_save_filename = git_path_to_check; was_git_updated = True; save_target = "git"; print(f"Git OK: {final_save_filename}", file=sys.stderr)
                                else: print(f"W: Git commit failed for {git_path_to_check}. Saving to '{SAVE_FOLDER}'.", file=sys.stderr); sanitized_path_from_marker = git_path_to_check; code_to_save = received_code
                            else: print(f"Info: Path '{git_path_to_check}' not tracked. Saving to '{SAVE_FOLDER}'.", file=sys.stderr); code_to_save = received_code
                else: print(f"W: Invalid extracted filename '{extracted_filename_raw}'. Saving to '{SAVE_FOLDER}'.", file=sys.stderr); code_to_save = received_code
            else: print("Info: No filename marker found. Saving to '{SAVE_FOLDER}'.", file=sys.stderr); code_to_save = received_code

            if save_target == "fallback":
                base_name_for_fallback = "code"; ext_for_fallback = DEFAULT_EXTENSION
                if sanitized_path_from_marker: base_name_for_fallback = Path(sanitized_path_from_marker).stem; ext_for_fallback = Path(sanitized_path_from_marker).suffix or DEFAULT_EXTENSION; detected_language_name = "From Marker (Untracked)"
                else: detected_ext, detected_language_name = detect_language_and_extension(code_to_save); ext_for_fallback = detected_ext;
                if detected_language_name != "Unknown": base_name_for_fallback = detected_language_name.lower().replace(" ", "_")
                save_filepath_str = generate_timestamped_filepath(extension=ext_for_fallback, base_prefix=base_name_for_fallback)
                final_save_filename = os.path.basename(save_filepath_str)
                print(f"Saving fallback to: '{save_filepath_str}'", file=sys.stderr)
                try: os.makedirs(SAVE_FOLDER_PATH, exist_ok=True); Path(save_filepath_str).write_text(code_to_save, encoding='utf-8'); print(f"Code saved successfully to {save_filepath_str}", file=sys.stderr)
                except Exception as e: print(f"E: Failed saving fallback file: {e}", file=sys.stderr); return jsonify({'status': 'error', 'message': f'Failed to save fallback file: {str(e)}'}), 500

            is_likely_python = final_save_filename.lower().endswith('.py')
            syntax_ok = None; run_success = None; log_filename = None

            if is_likely_python and Path(final_save_filename).name != THIS_SCRIPT_NAME:
                print(f"File '{final_save_filename}' is Python, performing checks.", file=sys.stderr)
                try:
                    compile(code_to_save, save_filepath_str, 'exec'); syntax_ok = True; print(f"Syntax OK for {final_save_filename}", file=sys.stderr)
                    if AUTO_RUN_ON_SYNTAX_OK:
                        print(f"Attempting to run {final_save_filename}", file=sys.stderr)
                        run_success, logpath = run_script(save_filepath_str)
                        log_filename = Path(logpath).name if logpath else None
                        print(f"Script run completed. Success: {run_success}, Log: {log_filename}", file=sys.stderr)
                except SyntaxError as e:
                    syntax_ok = False; print(f"Syntax Error: L{e.lineno} C{e.offset} {e.msg}", file=sys.stderr)
                    log_fn_base = Path(save_filepath_str).stem; log_path_err = LOG_FOLDER_PATH / f"{log_fn_base}_syntax_error.log"; marker = extracted_filename_raw or 'None'
                    try:
                        os.makedirs(LOG_FOLDER_PATH, exist_ok=True);
                        with open(log_path_err, 'w', encoding='utf-8') as f: f.write(f"Syntax Error:\nFile: {final_save_filename} (Marker: {marker})\nLine: {e.lineno}, Offset: {e.offset}\nMsg: {e.msg}\nCtx:\n{e.text}")
                        log_filename = log_path_err.name
                    except Exception as log_e: print(f"E: writing syntax error log: {log_e}", file=sys.stderr) # Corrected: Use log_e
                except Exception as compile_e:
                    syntax_ok = False; run_success = False; print(f"Compile/run setup error: {compile_e}", file=sys.stderr)
                    log_fn_base = Path(save_filepath_str).stem; log_path_err = LOG_FOLDER_PATH / f"{log_fn_base}_compile_error.log"; marker = extracted_filename_raw or 'None'
                    try:
                        os.makedirs(LOG_FOLDER_PATH, exist_ok=True);
                        with open(log_path_err, 'w', encoding='utf-8') as f: f.write(f"Compile/Run Setup Error:\nFile: {final_save_filename} (Marker: {marker})\nError: {compile_e}\n")
                        log_filename = log_path_err.name
                    except Exception as log_e: print(f"E: writing compile error log: {log_e}", file=sys.stderr) # Corrected: Use log_e
            elif is_likely_python and Path(final_save_filename).name == THIS_SCRIPT_NAME:
                 print(f"Skipping run for server script itself: '{final_save_filename}'.", file=sys.stderr)
                 try: compile(code_to_save, save_filepath_str, 'exec'); syntax_ok = True; print(f"Syntax OK for {final_save_filename}", file=sys.stderr)
                 except SyntaxError as e: syntax_ok = False; print(f"Syntax Error: L{e.lineno} C{e.offset} {e.msg}", file=sys.stderr)
                 except Exception as compile_e: syntax_ok = False; print(f"Compile check error: {compile_e}", file=sys.stderr)
            else: print(f"File '{final_save_filename}' is not Python, skipping checks.", file=sys.stderr)

            response_data = {'status': 'success', 'saved_as': final_save_filename, 'log_file': log_filename, 'syntax_ok': syntax_ok, 'run_success': run_success, 'source_file_marker': extracted_filename_raw, 'git_updated': was_git_updated, 'save_location': save_target, 'detected_language': detected_language_name if not extracted_filename_raw else None}
            print(f"Sending response: {response_data}", file=sys.stderr)
            print("--- Request complete (Lock released) ---", file=sys.stderr)
            return jsonify(response_data)
        # --- Lock Released ---

    return jsonify({'status': 'error', 'message': f'Unsupported method: {request.method}'}), 405

# --- NEW Test Connection Route ---
@app.route('/test_connection', methods=['GET'])
def test_connection():
    print("Received /test_connection request", file=sys.stderr)
    try:
        cwd = str(SERVER_DIR)
        return jsonify({'status': 'ok', 'message': 'Server is reachable.', 'working_directory': cwd})
    except Exception as e:
        print(f"Error getting working directory for test connection: {e}", file=sys.stderr)
        return jsonify({'status': 'error', 'message': f'Server error: {str(e)}'}), 500

# --- Log Routes (Unchanged) ---
@app.route('/logs')
def list_logs():
    log_files = []; template = '''<!DOCTYPE html><html><head><title>Logs Browser</title><style>body{font-family:Arial,sans-serif;background:#1e1e1e;color:#d4d4d4;padding:20px}h1{color:#4ec9b0;border-bottom:1px solid #444;padding-bottom:10px}ul{list-style:none;padding:0}li{background:#252526;margin-bottom:8px;border-radius:4px}li a{color:#9cdcfe;text-decoration:none;display:block;padding:10px 15px;transition:background-color .2s ease}li a:hover{background-color:#333}p{color:#888}pre{background:#1e1e1e;border:1px solid #444;padding:15px;border-radius:5px;overflow-x:auto;white-space:pre-wrap;word-wrap:break-word;color:#d4d4d4}</style></head><body><h1>🗂️ Available Logs</h1>{% if logs %}<ul>{% for log in logs %}<li><a href="/logs/{{ log | urlencode }}">{{ log }}</a></li>{% endfor %}</ul>{% else %}<p>No logs found in '{{ log_folder_name }}'.</p>{% endif %}</body></html>'''
    try:
         log_paths = [p for p in LOG_FOLDER_PATH.iterdir() if p.is_file() and p.name.endswith('.log')]
         log_paths.sort(key=lambda p: p.stat().st_mtime, reverse=True); log_files = [p.name for p in log_paths]
    except FileNotFoundError: pass
    except Exception as e: print(f"Error listing logs: {e}", file=sys.stderr)
    return render_template_string(template, logs=log_files, log_folder_name=LOG_FOLDER)

@app.route('/logs/<path:filename>')
def serve_log(filename):
    print(f"Request received for log file: {filename}", file=sys.stderr)
    log_dir = LOG_FOLDER_PATH.resolve(); requested_path = (log_dir / filename).resolve()
    if not str(requested_path).startswith(str(log_dir)) or '..' in filename or filename.startswith(('/', '\\')): return "Forbidden", 403
    try: return send_from_directory(LOG_FOLDER_PATH, filename, mimetype='text/plain', as_attachment=False)
    except FileNotFoundError: return "Log file not found", 404
    except Exception as e: print(f"Error serving log file {filename}: {e}", file=sys.stderr); return "Error serving file", 500

if __name__ == '__main__':
    host_ip = '127.0.0.1'; port_num = SERVER_PORT
    print(f"Starting Flask server on http://{host_ip}:{port_num}", file=sys.stderr)
    print(f"Server Directory (Repo Root): {SERVER_DIR}", file=sys.stderr)
    print(f"Saving non-Git files to: {SAVE_FOLDER_PATH}", file=sys.stderr)
    print(f"Saving logs to: {LOG_FOLDER_PATH}", file=sys.stderr)
    print(f"This script name: {THIS_SCRIPT_NAME}", file=sys.stderr)
    print("Will use filename from '@@FILENAME@@' marker if present and valid.", file=sys.stderr)
    if IS_REPO: print("Git integration ENABLED. Will update tracked files and commit.")
    else: print("Git integration DISABLED (Not in a Git repo or git command failed).")
    print("Will attempt language detection for fallback filename extensions.", file=sys.stderr)
    print("*** CORS enabled for all origins ***")
    print("!!! Server requests will be serialized using a lock to prevent Git conflicts. !!!", file=sys.stderr)
    try: app.run(host=host_ip, port=port_num, debug=False)
    except OSError as e:
        if "Address already in use" in str(e) or "WinError 10048" in str(e):
            print(f"\nE: Address already in use.\nPort {port_num} is in use by another program.", file=sys.stderr)
            print(f"Stop the other program or start this server with a different port using: python {THIS_SCRIPT_NAME} -p {port_num + 1}\n", file=sys.stderr)
            sys.exit(1)
        else: raise
# --- END OF FILE server.py ---