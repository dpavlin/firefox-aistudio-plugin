from flask import Flask, request, jsonify, send_from_directory, render_template_string
from flask_cors import CORS
import os
import datetime
import subprocess
import re
import sys
import argparse # Added for command-line arguments
from pathlib import Path

# --- Argument Parser ---
parser = argparse.ArgumentParser(description='AI Code Capture Server')
parser.add_argument(
    '-p', '--port', type=int, default=5000,
    help='Port number to run the Flask server on (default: 5000)'
)
args = parser.parse_args()
SERVER_PORT = args.port # Use the parsed port

# --- Flask App Setup ---
app = Flask(__name__)
CORS(app) # Enable CORS

# --- Configuration & Paths ---
SAVE_FOLDER = 'received_codes'
LOG_FOLDER = 'logs'
EXTENSION_SUBDIR = 'extension'

SERVER_DIR = Path(__file__).parent.resolve()
SAVE_FOLDER_PATH = SERVER_DIR / SAVE_FOLDER
LOG_FOLDER_PATH = SERVER_DIR / LOG_FOLDER
EXTENSION_DIR_PATH = SERVER_DIR / EXTENSION_SUBDIR if EXTENSION_SUBDIR else SERVER_DIR
THIS_SCRIPT_NAME = Path(__file__).name

os.makedirs(SAVE_FOLDER_PATH, exist_ok=True)
os.makedirs(LOG_FOLDER_PATH, exist_ok=True)

# --- Regex & Constants (Unchanged) ---
FILENAME_EXTRACT_REGEX = re.compile(
    r"^\s*(?://|#)\s*@@FILENAME@@\s+(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE
)
FILENAME_SANITIZE_REGEX = re.compile(r'[^a-zA-Z0-9._-]')
MAX_FILENAME_LENGTH = 100
LANGUAGE_PATTERNS = {'.py': re.compile(r'\b(def|class|import|from|if|else|elif|for|while|try|except|print)\b', re.MULTILINE), '.js': re.compile(r'\b(function|var|let|const|if|else|for|while|document|window|console\.log)\b', re.MULTILINE), '.html': re.compile(r'<(!DOCTYPE html|html|head|body|div|p|a|img|script|style)\b', re.IGNORECASE | re.MULTILINE), '.css': re.compile(r'[{};]\s*([a-zA-Z-]+)\s*:', re.MULTILINE), '.json': re.compile(r'^\s*\{.*\}\s*$|^\s*\[.*\]\s*$', re.DOTALL), '.md': re.compile(r'^#+\s|\*\*|\*|_|`|> |-', re.MULTILINE), '.sql': re.compile(r'\b(SELECT|INSERT|UPDATE|DELETE|CREATE|TABLE|FROM|WHERE|JOIN)\b', re.IGNORECASE | re.MULTILINE), '.xml': re.compile(r'<(\?xml|!DOCTYPE|[a-zA-Z:]+)', re.MULTILINE)}
DEFAULT_EXTENSION = '.txt'
AUTO_RUN_ON_SYNTAX_OK = True

# --- Helper Functions (Unchanged from previous working version) ---
def sanitize_filename(filename: str) -> str | None:
    if not filename or filename.isspace(): return None
    if '..' in filename or filename.startswith('/') or filename.startswith('\\'): print(f"Warning: Rejected potentially unsafe filename pattern: {filename}", file=sys.stderr); return None
    filename = os.path.basename(filename)
    if filename.startswith('.'): print(f"Warning: Rejected filename starting with '.': {filename}", file=sys.stderr); return None
    sanitized = FILENAME_SANITIZE_REGEX.sub('_', filename)
    if len(sanitized) > MAX_FILENAME_LENGTH:
        base, ext = os.path.splitext(sanitized)
        if len(ext) > (MAX_FILENAME_LENGTH - 2): ext = ext[:MAX_FILENAME_LENGTH - 2] + "~"
        base = base[:MAX_FILENAME_LENGTH - len(ext) - 1]; sanitized = f"{base}{ext}"
    if not os.path.splitext(sanitized)[0] and len(sanitized) <= 1: return None
    base, ext = os.path.splitext(sanitized)
    if not ext or len(ext) < 2: print(f"Warning: Sanitized filename '{sanitized}' lacks extension. Appending .txt", file=sys.stderr); sanitized += ".txt"
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
    today = datetime.datetime.now().strftime("%Y%m%d"); counter = 1
    if not extension.startswith('.'): extension = '.' + extension
    safe_base_prefix = FILENAME_SANITIZE_REGEX.sub('_', base_prefix)
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
    except FileNotFoundError: return False
    except Exception as e: print(f"Error checking Git repository: {e}", file=sys.stderr); return False

def is_git_tracked(filepath_relative_to_repo: str) -> bool:
    if not IS_REPO: return False
    try:
        git_path = Path(filepath_relative_to_repo).as_posix()
        command = ['git', 'ls-files', '--error-unmatch', git_path]
        print(f"Running: {' '.join(command)} from {SERVER_DIR}", file=sys.stderr)
        result = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR)
        is_tracked = result.returncode == 0
        print(f"Info: Git track status for '{git_path}': {is_tracked}", file=sys.stderr)
        if result.returncode != 0 and result.stderr: print(f"Info: git ls-files stderr: {result.stderr.strip()}", file=sys.stderr)
        return is_tracked
    except Exception as e: print(f"Error checking Git track status for '{filepath_relative_to_repo}': {e}", file=sys.stderr); return False

def update_and_commit_file(filepath_absolute: Path, code_content: str, marker_filename: str) -> bool:
    if not IS_REPO: return False
    try:
        filepath_relative_to_repo = str(filepath_absolute.relative_to(SERVER_DIR))
        git_path_posix = filepath_absolute.relative_to(SERVER_DIR).as_posix()
        print(f"Overwriting local file: {filepath_relative_to_repo}", file=sys.stderr)
        filepath_absolute.write_text(code_content, encoding='utf-8')
        print(f"Running: git add '{git_path_posix}' from {SERVER_DIR}", file=sys.stderr)
        add_result = subprocess.run(['git', 'add', git_path_posix], capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR)
        if add_result.returncode != 0: print(f"Error: 'git add' failed:\n{add_result.stderr}", file=sys.stderr); return False
        commit_message = f"Update {marker_filename} from AI Code Capture"
        print(f"Running: git commit -m \"{commit_message}\" from {SERVER_DIR}", file=sys.stderr)
        commit_result = subprocess.run(['git', 'commit', '-m', commit_message], capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR)
        if commit_result.returncode != 0:
            if "nothing to commit" in commit_result.stdout or "no changes added to commit" in commit_result.stdout or "nothing added to commit" in commit_result.stdout:
                print("Info: No changes detected by Git for commit.", file=sys.stderr); return True
            else: print(f"Error: 'git commit' failed:\n{commit_result.stderr}", file=sys.stderr); return False
        print(f"Successfully committed changes for {filepath_relative_to_repo}.", file=sys.stderr)
        return True
    except IOError as e: print(f"Error writing file {filepath_absolute}: {e}", file=sys.stderr); return False
    except Exception as e: print(f"An unexpected error during Git update/commit: {e}", file=sys.stderr); return False

IS_REPO = is_git_repository()

def run_script(filepath):
    filepath_obj = Path(filepath); filename_base = filepath_obj.stem
    logpath = LOG_FOLDER_PATH / f"{filename_base}.log"
    try:
        python_exe = sys.executable
        result = subprocess.run([python_exe, filepath], capture_output=True, text=True, timeout=10, encoding='utf-8', check=False, cwd=filepath_obj.parent)
        os.makedirs(LOG_FOLDER_PATH, exist_ok=True)
        with open(logpath, 'w', encoding='utf-8') as f: f.write(f"--- STDOUT ---\n{result.stdout}\n--- STDERR ---\n{result.stderr}\n--- Return Code: {result.returncode} ---\n")
        return result.returncode == 0, str(logpath)
    except subprocess.TimeoutExpired: os.makedirs(LOG_FOLDER_PATH, exist_ok=True); with open(logpath, 'w', encoding='utf-8') as f: f.write("Error: Script timed out after 10 seconds.\n"); return False, str(logpath)
    except Exception as e: os.makedirs(LOG_FOLDER_PATH, exist_ok=True); with open(logpath, 'w', encoding='utf-8') as f: f.write(f"Error running script: {str(e)}\n"); return False, str(logpath)

# --- Route Definitions ---
@app.route('/submit_code', methods=['POST', 'OPTIONS'])
def submit_code():
    if request.method == 'OPTIONS': return '', 204
    if request.method == 'POST':
        data = request.get_json()
        if not data: return jsonify({'status': 'error', 'message': 'No JSON data received'}), 400
        received_code = data.get('code', '')
        if not received_code or received_code.isspace(): return jsonify({'status': 'error', 'message': 'Empty code received'}), 400

        save_filepath_str = None; final_save_filename = None
        code_to_process = received_code
        extracted_filename_raw = None; detected_language_name = "Unknown"
        marker_line_length = 0; was_git_updated = False
        sanitized_basename = None

        match = FILENAME_EXTRACT_REGEX.search(received_code)
        if match:
            extracted_filename_raw = match.group(1).strip()
            marker_line_length = match.end()
            if marker_line_length < len(received_code) and received_code[marker_line_length] == '\n': marker_line_length += 1
            print(f"Found filename marker: '{extracted_filename_raw}'", file=sys.stderr)
            sanitized_basename = sanitize_filename(extracted_filename_raw)
            if sanitized_basename:
                if EXTENSION_SUBDIR and sanitized_basename != THIS_SCRIPT_NAME:
                     git_check_path_relative = str(Path(EXTENSION_SUBDIR) / sanitized_basename)
                     absolute_path_for_commit = EXTENSION_DIR_PATH / sanitized_basename
                else:
                     git_check_path_relative = sanitized_basename
                     absolute_path_for_commit = SERVER_DIR / sanitized_basename
                print(f"Checking Git tracking for relative path: '{git_check_path_relative}'", file=sys.stderr)
                is_tracked = is_git_tracked(git_check_path_relative)
                if is_tracked:
                    print(f"File '{git_check_path_relative}' is tracked. Preparing commit.", file=sys.stderr)
                    code_to_process = received_code[marker_line_length:]
                    commit_success = update_and_commit_file(absolute_path_for_commit, code_to_process, extracted_filename_raw)
                    if commit_success:
                        save_filepath_str = str(absolute_path_for_commit); final_save_filename = sanitized_basename; was_git_updated = True
                        print(f"Git update successful for {final_save_filename}", file=sys.stderr)
                    else: print(f"Warning: Git commit failed for {git_check_path_relative}. Saving to '{SAVE_FOLDER}'.", file=sys.stderr); sanitized_basename = None
                else: print(f"Info: File '{git_check_path_relative}' not tracked. Saving to '{SAVE_FOLDER}'.", file=sys.stderr)
            else: print(f"Warning: Invalid extracted filename '{extracted_filename_raw}'. Saving to '{SAVE_FOLDER}'.", file=sys.stderr)

        if not was_git_updated:
            code_to_process = received_code
            if sanitized_basename:
                 base, ext = os.path.splitext(sanitized_basename)
                 save_filepath_str = generate_timestamped_filepath(extension=ext, base_prefix=base)
                 print(f"Using generated filepath based on untracked marker: '{save_filepath_str}'", file=sys.stderr)
            else:
                 detected_ext, detected_language_name = detect_language_and_extension(received_code)
                 base_prefix = detected_language_name.lower().replace(" ", "_")
                 save_filepath_str = generate_timestamped_filepath(extension=detected_ext, base_prefix=base_prefix)
                 print(f"Using language detection filepath: '{save_filepath_str}'", file=sys.stderr)
            final_save_filename = os.path.basename(save_filepath_str)
            try:
                os.makedirs(SAVE_FOLDER_PATH, exist_ok=True)
                with open(save_filepath_str, 'w', encoding='utf-8') as f: f.write(code_to_process)
                print(f"Code saved successfully to {save_filepath_str}", file=sys.stderr)
            except Exception as e: return jsonify({'status': 'error', 'message': f'Failed to save fallback file: {str(e)}'}), 500

        is_likely_python = final_save_filename.lower().endswith('.py')
        syntax_ok = None; run_success = None; log_filename = None

        if is_likely_python and final_save_filename != THIS_SCRIPT_NAME:
            print(f"File '{final_save_filename}' is Python, performing checks.", file=sys.stderr)
            try:
                compile(code_to_process, save_filepath_str, 'exec')
                syntax_ok = True; print(f"Syntax OK for {final_save_filename}", file=sys.stderr)
                if AUTO_RUN_ON_SYNTAX_OK:
                    print(f"Attempting to run {final_save_filename}", file=sys.stderr)
                    run_success, logpath = run_script(save_filepath_str)
                    log_filename = os.path.basename(logpath) if logpath else None
                    print(f"Script run completed. Success: {run_success}, Log: {log_filename}", file=sys.stderr)
            except SyntaxError as e:
                syntax_ok = False; print(f"Syntax Error: L{e.lineno} C{e.offset} {e.msg}", file=sys.stderr)
                log_filename_base = Path(save_filepath_str).stem; logpath_err = LOG_FOLDER_PATH / f"{log_filename_base}_syntax_error.log"
                try: os.makedirs(LOG_FOLDER_PATH, exist_ok=True); original_marker = extracted_filename_raw or 'None'
                with open(logpath_err, 'w', encoding='utf-8') as f: f.write(f"Syntax Error:\nFile: {final_save_filename} (Marker: {original_marker})\nLine: {e.lineno}, Offset: {e.offset}\nMsg: {e.msg}\nCtx:\n{e.text}"); log_filename = logpath_err.name
                except Exception as log_e: print(f"Error writing syntax error log: {log_e}", file=sys.stderr)
            except Exception as compile_e:
                syntax_ok = False; run_success = False; print(f"Compile/run setup error: {compile_e}", file=sys.stderr)
                log_filename_base = Path(save_filepath_str).stem; logpath_err = LOG_FOLDER_PATH / f"{log_filename_base}_compile_error.log"
                try: os.makedirs(LOG_FOLDER_PATH, exist_ok=True); original_marker = extracted_filename_raw or 'None'
                with open(logpath_err, 'w', encoding='utf-8') as f: f.write(f"Compile/Run Setup Error:\nFile: {final_save_filename} (Marker: {original_marker})\nError: {compile_e}\n"); log_filename = logpath_err.name
                except Exception as log_e: print(f"Error writing compile error log: {log_e}", file=sys.stderr)
        elif is_likely_python and final_save_filename == THIS_SCRIPT_NAME:
             print(f"Skipping run for server script itself: '{final_save_filename}'.", file=sys.stderr)
             try: compile(code_to_process, save_filepath_str, 'exec'); syntax_ok = True; print(f"Syntax OK for {final_save_filename}", file=sys.stderr)
             except SyntaxError as e: syntax_ok = False; print(f"Syntax Error: L{e.lineno} C{e.offset} {e.msg}", file=sys.stderr) # Logged above if needed
             except Exception as compile_e: syntax_ok = False; print(f"Compile check error: {compile_e}", file=sys.stderr)
        else: print(f"File '{final_save_filename}' is not Python, skipping checks.", file=sys.stderr)

        response_data = {'status': 'success', 'saved_as': final_save_filename, 'log_file': log_filename, 'syntax_ok': syntax_ok, 'run_success': run_success, 'source_file_marker': extracted_filename_raw, 'git_updated': was_git_updated, 'detected_language': detected_language_name if not extracted_filename_raw else None}
        print(f"Sending response: {response_data}", file=sys.stderr)
        return jsonify(response_data)
    return jsonify({'status': 'error', 'message': f'Unsupported method: {request.method}'}), 405

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
    if not str(requested_path).startswith(str(log_dir)) or '..' in filename: return "Forbidden", 403
    try: return send_from_directory(LOG_FOLDER_PATH, filename, mimetype='text/plain', as_attachment=False)
    except FileNotFoundError: return "Log file not found", 404
    except Exception as e: print(f"Error serving log file {filename}: {e}", file=sys.stderr); return "Error serving file", 500

if __name__ == '__main__':
    host_ip = '127.0.0.1'
    # Use the port from command-line arguments
    port_num = SERVER_PORT
    print(f"Starting Flask server on http://{host_ip}:{port_num}", file=sys.stderr)
    print(f"Saving non-Git files to: {SAVE_FOLDER_PATH}", file=sys.stderr)
    print(f"Saving logs to: {LOG_FOLDER_PATH}", file=sys.stderr)
    print(f"Assuming extension files live in: {EXTENSION_DIR_PATH}", file=sys.stderr)
    print(f"This script name: {THIS_SCRIPT_NAME}", file=sys.stderr)
    print("Will use filename from '@@FILENAME@@' marker if present and valid.", file=sys.stderr)
    if IS_REPO: print("Git integration ENABLED. Will update tracked files and commit.")
    else: print("Git integration DISABLED (Not in a Git repo or git command failed).")
    print("Will attempt language detection for fallback filename extensions.", file=sys.stderr)
    print("*** CORS enabled for all origins ***")
    # Run Flask app using the configured port
    app.run(host=host_ip, port=port_num, debug=False)
# --- END OF FILE server.py ---