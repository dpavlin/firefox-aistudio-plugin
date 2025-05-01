#!/usr/bin/env python3
# @@FILENAME@@ server.py

from flask import Flask, request, jsonify, send_from_directory, render_template_string
from flask_cors import CORS
import os
import datetime
import subprocess
import re
import sys
import argparse
from pathlib import Path
import threading
import json # For config file handling
import unicodedata # Used in sanitize_filename
import shutil # For shutil.which

# --- Configuration File Handling ---
CONFIG_FILE = Path.cwd().resolve() / 'server_config.json'

def load_config():
    """Loads config from JSON file, returns defaults if not found/invalid."""
    defaults = {
        'port': 5000,
        'enable_python_run': False,
        'enable_shell_run': False
    }
    if not CONFIG_FILE.is_file():
        print(f"Info: Config file '{CONFIG_FILE}' not found. Using defaults.", file=sys.stderr)
        return defaults.copy() # Return a copy to avoid modifying defaults dict
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            loaded_config = defaults.copy() # Start with defaults
            # Ensure loaded values are of correct type, fall back to default if not
            try:
                loaded_config['port'] = int(config.get('port', defaults['port']))
                if not (1 <= loaded_config['port'] <= 65535): loaded_config['port'] = defaults['port']
            except (ValueError, TypeError): loaded_config['port'] = defaults['port']
            try: loaded_config['enable_python_run'] = bool(config.get('enable_python_run', defaults['enable_python_run']))
            except TypeError: loaded_config['enable_python_run'] = defaults['enable_python_run']
            try: loaded_config['enable_shell_run'] = bool(config.get('enable_shell_run', defaults['enable_shell_run']))
            except TypeError: loaded_config['enable_shell_run'] = defaults['enable_shell_run']

            print(f"Info: Loaded config from '{CONFIG_FILE}': {loaded_config}", file=sys.stderr)
            return loaded_config
    except (json.JSONDecodeError, OSError) as e:
        print(f"W: Error reading config file '{CONFIG_FILE}': {e}. Using defaults.", file=sys.stderr)
        return defaults.copy() # Return a copy

def save_config(config_data):
    """Saves config data to JSON file."""
    try:
        # Ensure values are correct types before saving - Load current to preserve other keys
        current_saved_config = load_config() # Load existing state from file
        current_saved_config.update(config_data) # Update with provided keys

        config_to_save = {
             # Use updated value if present and valid, else keep current saved value
            'port': int(current_saved_config.get('port', 5000)),
            'enable_python_run': bool(current_saved_config.get('enable_python_run', False)),
            'enable_shell_run': bool(current_saved_config.get('enable_shell_run', False))
        }
        # Re-validate port range after update
        if not (1 <= config_to_save['port'] <= 65535):
            print(f"W: Invalid port {config_to_save['port']} during save, reverting to default 5000.", file=sys.stderr)
            config_to_save['port'] = 5000


        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_to_save, f, indent=4)
        print(f"Info: Configuration saved to '{CONFIG_FILE}'. Restart server for changes.", file=sys.stderr)
        return True, config_to_save # Return success and what was saved
    except (OSError, TypeError, ValueError) as e:
        print(f"E: Failed to save config file '{CONFIG_FILE}': {e}", file=sys.stderr)
        return False, None # Return failure

# --- Load Initial Config ---
current_config = load_config()

# --- Argument Parser (Overrides config file) ---
parser = argparse.ArgumentParser(description='AI Code Capture Server', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '-p', '--port', type=int,
    default=current_config['port'], # Default from config
    help='Port number to run the Flask server on.'
)
parser.add_argument(
    '--shell', action='store_true',
    help='DANGEROUS: Enable automatic execution of shell scripts. Overrides config file if used.'
)
parser.add_argument(
    '--enable-python-run', action='store_true',
    help='Enable automatic execution of Python scripts. Overrides config file if used.'
)
args = parser.parse_args()

# Determine final config values based on precedence: command-line args > config file > hardcoded defaults
SERVER_PORT = args.port

# Check if flags were explicitly passed on command line to override config file setting for runtime
# Note: We use current_config (from file) as the base if flag not passed
AUTO_RUN_PYTHON_ON_SYNTAX_OK = args.enable_python_run if '--enable-python-run' in sys.argv else current_config['enable_python_run']
AUTO_RUN_SHELL_ON_SYNTAX_OK = args.shell if '--shell' in sys.argv else current_config['enable_shell_run']


# This dictionary reflects the actual running state for the /status endpoint
final_config_for_status = {
    'port': SERVER_PORT,
    'enable_python_run': AUTO_RUN_PYTHON_ON_SYNTAX_OK,
    'enable_shell_run': AUTO_RUN_SHELL_ON_SYNTAX_OK
}

# --- Flask App Setup ---
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}) # Allow requests from the extension

# --- Lock ---
request_lock = threading.Lock()
print("Request lock initialized.", file=sys.stderr)

# --- Paths & Constants ---
SAVE_FOLDER = 'received_codes'; LOG_FOLDER = 'logs'
SERVER_DIR = Path.cwd().resolve()
SAVE_FOLDER_PATH = SERVER_DIR / SAVE_FOLDER
LOG_FOLDER_PATH = SERVER_DIR / LOG_FOLDER
try: THIS_SCRIPT_NAME = Path(__file__).name
except NameError: THIS_SCRIPT_NAME = "server.py"

os.makedirs(SAVE_FOLDER_PATH, exist_ok=True)
os.makedirs(LOG_FOLDER_PATH, exist_ok=True)

FILENAME_EXTRACT_REGEX = re.compile(r"^\s*(?://|#)\s*@@FILENAME@@\s+(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
FILENAME_SANITIZE_REGEX = re.compile(r'[^\w\.\-\/]+')
MAX_FILENAME_LENGTH = 200
LANGUAGE_PATTERNS = {
    '.py': re.compile(r'\b(def|class|import|from|if|else|elif|for|while|try|except|print)\b', re.MULTILINE),
    '.js': re.compile(r'\b(function|var|let|const|if|else|for|while|document|window|console\.log)\b', re.MULTILINE),
    '.html': re.compile(r'<(!DOCTYPE html|html|head|body|div|p|a|img|script|style)\b', re.IGNORECASE | re.MULTILINE),
    '.css': re.compile(r'[{};]\s*([a-zA-Z-]+)\s*:', re.MULTILINE),
    '.json': re.compile(r'^\s*\{.*\}\s*$|^\s*\[.*\]\s*$', re.DOTALL),
    '.md': re.compile(r'^#+\s|\*\*|\*|_|`|> |-', re.MULTILINE),
    '.sql': re.compile(r'\b(SELECT|INSERT|UPDATE|DELETE|CREATE|TABLE|FROM|WHERE|JOIN)\b', re.IGNORECASE | re.MULTILINE),
    '.xml': re.compile(r'<(\?xml|!DOCTYPE|[a-zA-Z:]+)', re.MULTILINE),
    '.sh': re.compile(r'\b(echo|if|then|else|fi|for|do|done|while|case|esac|function|source|export|\$\(|\{|\})\b|^(#!\/bin\/(bash|sh))', re.MULTILINE)
}
DEFAULT_EXTENSION = '.txt';

# =====================================================
# >>> HELPER FUNCTIONS (No changes needed here) <<<
# =====================================================
def sanitize_filename(filename: str) -> str | None:
    if not filename or filename.isspace(): return None
    filename = filename.strip()
    if filename.startswith(('/', '\\')) or '..' in Path(filename).parts:
        print(f"W: Rejected potentially unsafe path pattern: {filename}", file=sys.stderr)
        return None
    if Path(filename).name.startswith('.'):
        print(f"W: Rejected path ending in hidden file/directory: {filename}", file=sys.stderr)
        return None
    filename = filename.replace('\\', '/')
    parts = filename.split('/')
    sanitized_parts = []
    for part in parts:
        sanitized_part = FILENAME_SANITIZE_REGEX.sub('_', part)
        sanitized_part = sanitized_part.strip('_')
        if not sanitized_part:
            print(f"W: Path segment became empty after sanitization in '{filename}'. Rejecting.", file=sys.stderr)
            return None
        sanitized_parts.append(sanitized_part)
    sanitized = '/'.join(sanitized_parts)
    if len(sanitized) > MAX_FILENAME_LENGTH:
        print(f"W: Sanitized path too long ('{sanitized}'), might be truncated unexpectedly.", file=sys.stderr)
        base, ext = os.path.splitext(sanitized)
        original_ext = Path(filename).suffix
        max_base_len = MAX_FILENAME_LENGTH - len(original_ext if original_ext else '')
        if max_base_len < 1:
             print(f"W: Path too long even for extension. Hard truncating.", file=sys.stderr)
             sanitized = sanitized[:MAX_FILENAME_LENGTH]
        else:
             sanitized = base[:max_base_len] + (original_ext if original_ext else '')
    final_path = Path(sanitized)
    if not final_path.name or final_path.name.startswith('.'):
         print(f"W: Final sanitized path has empty or hidden basename: '{sanitized}'. Rejecting.", file=sys.stderr)
         return None
    if not final_path.suffix or len(final_path.suffix) < 2:
        print(f"W: Sanitized path '{sanitized}' lacks a proper extension. Appending {DEFAULT_EXTENSION}", file=sys.stderr)
        sanitized += DEFAULT_EXTENSION
    return sanitized

def detect_language_and_extension(code: str) -> tuple[str, str]:
    first_lines = code.splitlines()[:3]
    if first_lines:
        first_line = first_lines[0].strip()
        if first_line.startswith('#!/usr/bin/env python') or first_line.startswith('#!/usr/bin/python'): return '.py', 'Python'
        if first_line.startswith('#!/bin/bash') or first_line.startswith('#!/bin/sh'): return '.sh', 'Shell'
        if first_line.startswith('<?php'): return '.php', 'PHP'
    if LANGUAGE_PATTERNS['.html'].search(code): return '.html', 'HTML'
    if LANGUAGE_PATTERNS['.xml'].search(code): return '.xml', 'XML'
    if LANGUAGE_PATTERNS['.json'].search(code):
         try:
             import json
             json.loads(code)
             return '.json', 'JSON'
         except json.JSONDecodeError: pass
    if LANGUAGE_PATTERNS['.css'].search(code): return '.css', 'CSS'
    if LANGUAGE_PATTERNS['.py'].search(code): return '.py', 'Python'
    if LANGUAGE_PATTERNS['.sh'].search(code): return '.sh', 'Shell'
    if LANGUAGE_PATTERNS['.js'].search(code): return '.js', 'JavaScript'
    if LANGUAGE_PATTERNS['.sql'].search(code): return '.sql', 'SQL'
    if LANGUAGE_PATTERNS['.md'].search(code): return '.md', 'Markdown'
    print("W: Cannot detect language. Defaulting to .txt", file=sys.stderr)
    return DEFAULT_EXTENSION, 'Text'

def generate_timestamped_filepath(extension: str = '.txt', base_prefix="code"):
    today = datetime.datetime.now().strftime("%Y%m%d")
    counter = 1
    if not extension.startswith('.'): extension = '.' + extension
    safe_base_prefix = re.sub(r'[^a-zA-Z0-9_\-]', '_', base_prefix).strip('_')
    if not safe_base_prefix: safe_base_prefix = "code"
    while True:
        filename = f"{safe_base_prefix}_{today}_{counter:03d}{extension}"
        filepath = SAVE_FOLDER_PATH / filename
        if not filepath.exists():
            return str(filepath.resolve())
        counter += 1
        if counter > 999:
             print(f"W: Could not find unique filename for prefix '{safe_base_prefix}' after 999 attempts. Adding timestamp.", file=sys.stderr)
             fallback_filename = f"{safe_base_prefix}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{extension}"
             return str((SAVE_FOLDER_PATH / fallback_filename).resolve())

def is_git_repository() -> bool:
    try:
        result = subprocess.run(['git', 'rev-parse', '--is-inside-work-tree'], capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR, timeout=5)
        is_repo = result.returncode == 0 and result.stdout.strip() == 'true'
        if result.returncode != 0 and result.stderr:
             if 'not a git repository' not in result.stderr.lower():
                  print(f"W: Git check failed: {result.stderr.strip()}", file=sys.stderr)
        elif not is_repo and result.returncode == 0:
             print("Info: Not running inside a Git work tree.", file=sys.stderr)
        return is_repo
    except FileNotFoundError: return False
    except subprocess.TimeoutExpired: return False
    except Exception as e: return False

IS_REPO = is_git_repository()

def find_tracked_file_by_name(basename_to_find: str) -> str | None:
    if not IS_REPO: return None
    try:
        command = ['git', 'ls-files', f'**/{basename_to_find}']
        result = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR, timeout=5)
        if result.returncode != 0:
             if result.stderr and result.returncode != 1: print(f"E: 'git ls-files' failed (RC={result.returncode}):\n{result.stderr.strip()}", file=sys.stderr)
             return None
        tracked_files = result.stdout.strip().splitlines()
        matches = [f for f in tracked_files if Path(f).name == basename_to_find]
        if len(matches) == 1: return matches[0]
        elif len(matches) > 1: print(f"W: Ambiguous filename marker '{basename_to_find}'. Found multiple tracked files: {matches}.", file=sys.stderr); return None
        else: return None
    except subprocess.TimeoutExpired: return None
    except Exception as e: return None

def is_git_tracked(filepath_relative_to_repo: str) -> bool:
    if not IS_REPO: return False
    try:
        git_path = Path(filepath_relative_to_repo).as_posix()
        command = ['git', 'ls-files', '--error-unmatch', git_path]
        subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', cwd=SERVER_DIR, timeout=5)
        return True
    except subprocess.CalledProcessError: return False
    except subprocess.TimeoutExpired: return False
    except Exception: return False

def update_and_commit_file(filepath_absolute: Path, code_content: str, marker_filename: str) -> bool:
    if not IS_REPO: return False
    try:
        filepath_relative_to_repo_str = str(filepath_absolute.relative_to(SERVER_DIR))
        git_path_posix = filepath_absolute.relative_to(SERVER_DIR).as_posix()
        filepath_absolute.parent.mkdir(parents=True, exist_ok=True)
        current_content = ""
        if filepath_absolute.exists():
             try: current_content = filepath_absolute.read_text(encoding='utf-8')
             except Exception as read_e: print(f"W: Could not read existing file {filepath_relative_to_repo_str} to check for changes: {read_e}", file=sys.stderr)
        if code_content == current_content:
             print(f"Info: Content for '{filepath_relative_to_repo_str}' identical. Skipping Git.", file=sys.stderr)
             return True
        print(f"Info: Overwriting tracked local file: {filepath_relative_to_repo_str}", file=sys.stderr)
        try: filepath_absolute.write_text(code_content, encoding='utf-8')
        except OSError as write_e: print(f"E: Failed to write to file '{filepath_relative_to_repo_str}': {write_e}", file=sys.stderr); return False
        print(f"Running: git add '{git_path_posix}' from {SERVER_DIR}", file=sys.stderr)
        add_result = subprocess.run(['git', 'add', git_path_posix], capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR, timeout=10)
        if add_result.returncode != 0: print(f"E: 'git add {git_path_posix}' failed (RC={add_result.returncode}):\n{add_result.stderr.strip()}", file=sys.stderr); return False
        commit_message = f"Update {marker_filename} from AI Code Capture"
        print(f"Running: git commit -m \"{commit_message}\" -- '{git_path_posix}' ...", file=sys.stderr)
        commit_result = subprocess.run(['git', 'commit', '-m', commit_message, '--', git_path_posix], capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR, timeout=15)
        if commit_result.returncode == 0:
            print(f"Success: Committed changes for '{git_path_posix}'.\n{commit_result.stdout.strip()}", file=sys.stderr)
            return True
        else:
             no_changes_patterns = ["nothing to commit", "no changes added to commit", "nothing added to commit but untracked files present"]
             combined_output = (commit_result.stdout + commit_result.stderr).lower()
             if any(p in combined_output for p in no_changes_patterns):
                 print(f"Info: 'git commit' reported no effective changes staged for '{git_path_posix}'.", file=sys.stderr)
                 return True
             else:
                 print(f"E: 'git commit' failed for '{git_path_posix}' (RC={commit_result.returncode}):\n{commit_result.stderr.strip()}\n{commit_result.stdout.strip()}", file=sys.stderr)
                 return False
    except Exception as e: print(f"E: Unexpected error during Git update/commit for {filepath_absolute}: {e}", file=sys.stderr); return False

def run_script(filepath: str, script_type: str):
    filepath_obj = Path(filepath).resolve()
    if not filepath_obj.is_file(): print(f"E: Script file not found for execution: {filepath_obj}", file=sys.stderr); return False, None
    filename_base = filepath_obj.stem
    os.makedirs(LOG_FOLDER_PATH, exist_ok=True)
    logpath = LOG_FOLDER_PATH / f"{filename_base}_{script_type}_run.log"
    run_cwd = filepath_obj.parent
    command = []
    interpreter_name = ""
    if script_type == 'python':
        python_exe = sys.executable or shutil.which("python3") or shutil.which("python") or "python"
        if not shutil.which(python_exe):
             print(f"E: Python interpreter '{python_exe}' not found.", file=sys.stderr)
             try: # Colon needed
                 logpath.write_text(f"Error: Python interpreter '{python_exe}' not found.\n", encoding='utf-8')
                 return False, str(logpath)
             except Exception as log_e: print(f"E: writing log: {log_e}"); return False, None
        command = [python_exe, str(filepath_obj)]
        interpreter_name = Path(python_exe).name
        print(f"Executing Python ({interpreter_name}): {' '.join(command)} in '{run_cwd}'", file=sys.stderr)
    elif script_type == 'shell':
        shell_exe = shutil.which("bash") or shutil.which("sh")
        if not shell_exe:
             print("E: No 'bash' or 'sh' interpreter found in PATH.", file=sys.stderr)
             try: # Colon needed
                 logpath.write_text("Error: No 'bash' or 'sh' interpreter found.\n", encoding='utf-8')
                 return False, str(logpath)
             except Exception as log_e: print(f"E: writing log: {log_e}"); return False, None
        command = [shell_exe, str(filepath_obj)]
        interpreter_name = Path(shell_exe).name
        print(f"Executing Shell ({interpreter_name}): {' '.join(command)} in '{run_cwd}'", file=sys.stderr)
    else: print(f"E: Cannot run script of unknown type '{script_type}' for {filepath}", file=sys.stderr); return False, None
    log_content = f"--- COMMAND ---\n{' '.join(command)}\n--- CWD ---\n{run_cwd}\n"
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, encoding='utf-8', check=False, cwd=run_cwd)
        log_content += f"--- STDOUT ---\n{result.stdout}\n--- STDERR ---\n{result.stderr}\n--- Return Code: {result.returncode} ---\n"
        with open(logpath, 'w', encoding='utf-8') as f: f.write(log_content)
        print(f"Exec finished ({script_type}). RC: {result.returncode}. Log: {logpath.name}", file=sys.stderr)
        return result.returncode == 0, str(logpath)
    except subprocess.TimeoutExpired:
        print(f"E: Script timed out after 15 seconds: {filepath_obj.name}", file=sys.stderr)
        log_content += f"--- ERROR ---\nScript execution timed out after 15 seconds.\n"
        try: # Colon needed
            with open(logpath, 'w', encoding='utf-8') as f: f.write(log_content)
            return False, str(logpath)
        except Exception as log_e: print(f"E: Failed to write timeout log for {filepath_obj.name}: {log_e}", file=sys.stderr); return False, None
    except FileNotFoundError:
        print(f"E: Script file '{filepath_obj}' or CWD '{run_cwd}' not found during execution.", file=sys.stderr)
        log_content += f"--- ERROR ---\nScript file '{filepath_obj}' or CWD '{run_cwd}' not found during execution.\n"
        try: # Colon needed
            with open(logpath, 'w', encoding='utf-8') as f: f.write(log_content)
            return False, str(logpath)
        except Exception as log_e: print(f"E: Failed to write FileNotFoundError log for {filepath_obj.name}: {log_e}", file=sys.stderr); return False, None
    except Exception as e:
        print(f"E: Unexpected error running script {filepath_obj.name}: {e}", file=sys.stderr)
        log_content += f"--- ERROR ---\nUnexpected error during script execution:\n{e}\n"
        try: # Colon needed
            with open(logpath, 'w', encoding='utf-8') as f: f.write(log_content)
            return False, str(logpath)
        except Exception as log_e: print(f"E: Failed to write general error log for {filepath_obj.name}: {log_e}", file=sys.stderr); return False, None

def check_shell_syntax(filepath: str) -> tuple[bool, str | None]:
    """Checks shell script syntax using 'bash -n'. Returns (syntax_ok, log_path)."""
    filepath_obj = Path(filepath).resolve()
    if not filepath_obj.is_file():
        print(f"E: Shell script file not found for syntax check: {filepath_obj}", file=sys.stderr)
        return False, None

    filename_base = filepath_obj.stem
    os.makedirs(LOG_FOLDER_PATH, exist_ok=True) # Ensure log folder exists
    logpath = LOG_FOLDER_PATH / f"{filename_base}_shell_syntax.log"

    checker_exe = shutil.which("bash")
    if not checker_exe:
        print("W: 'bash' command not found. Cannot check shell syntax.", file=sys.stderr)
        try: # Colon needed
            logpath.write_text("Error: 'bash' command not found for syntax check.\n", encoding='utf-8')
            return False, str(logpath)
        except Exception as log_e: print(f"E: writing log: {log_e}"); return False, None

    command = [checker_exe, '-n', str(filepath_obj)] # Use absolute path

    log_content = f"--- COMMAND ---\n{' '.join(command)}\n"
    print(f"Checking Shell syntax: {' '.join(command)}", file=sys.stderr)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, encoding='utf-8', check=False)
        syntax_ok = result.returncode == 0

        status_msg = "OK" if syntax_ok else f"ERROR (RC: {result.returncode})"
        log_content += f"--- STATUS: {status_msg} ---\n"
        log_content += f"--- STDOUT ---\n{result.stdout}\n"
        log_content += f"--- STDERR ---\n{result.stderr}\n"

        with open(logpath, 'w', encoding='utf-8') as f: f.write(log_content)

        if syntax_ok:
            print(f"Shell syntax OK for {filepath_obj.name}", file=sys.stderr)
            return True, str(logpath)
        else:
            print(f"Shell syntax Error for {filepath_obj.name}. RC: {result.returncode}. Log: {logpath.name}", file=sys.stderr)
            return False, str(logpath)

    except FileNotFoundError:
        # This covers the case where 'bash' exists but fails to run (very unlikely)
        print(f"E: Syntax check command '{checker_exe}' not found during execution.", file=sys.stderr)
        log_content += f"--- ERROR ---\nSyntax check command '{checker_exe}' not found during execution.\n"
        try: # Colon needed and verified correct
            with open(logpath, 'w', encoding='utf-8') as f: f.write(log_content)
            return False, str(logpath) # Return after writing log
        except Exception as log_e: print(f"E: writing log: {log_e}"); return False, None # Return if logging fails

    except subprocess.TimeoutExpired:
        print(f"E: Shell syntax check timed out for {filepath_obj.name}", file=sys.stderr)
        log_content += "--- ERROR ---\nShell syntax check timed out after 10 seconds.\n"
        try: # Colon needed and verified correct
             with open(logpath, 'w', encoding='utf-8') as f: f.write(log_content)
             return False, str(logpath)
        except Exception as log_e: print(f"E: writing log: {log_e}"); return False, None

    except Exception as e:
        print(f"E: Unexpected error checking shell syntax for {filepath_obj.name}: {e}", file=sys.stderr)
        log_content += f"--- ERROR ---\nUnexpected error during syntax check:\n{e}\n"
        try: # Colon needed and verified correct
            with open(logpath, 'w', encoding='utf-8') as f: f.write(log_content)
            return False, str(logpath)
        except Exception as log_e: print(f"E: writing log: {log_e}"); return False, None


# --- Route Definitions ---

@app.route('/status', methods=['GET'])
def get_status():
    """Returns current server status and RUNNING configuration."""
    status_data = {
        'status': 'running',
        'working_directory': str(SERVER_DIR),
        'save_directory': str(SAVE_FOLDER_PATH.relative_to(SERVER_DIR)),
        'log_directory': str(LOG_FOLDER_PATH.relative_to(SERVER_DIR)),
        'is_git_repo': IS_REPO,
        'port': SERVER_PORT,
        'auto_run_python': AUTO_RUN_PYTHON_ON_SYNTAX_OK,
        'auto_run_shell': AUTO_RUN_SHELL_ON_SYNTAX_OK,
        'config_file_exists': CONFIG_FILE.is_file(),
        'config_file_content': load_config()
    }
    return jsonify(status_data)

@app.route('/update_config', methods=['POST'])
def update_config():
    """
    Updates the server_config.json file with settings from the request.
    Does NOT dynamically update the running server state. Requires restart.
    """
    if not request.is_json:
        return jsonify({'status': 'error', 'message': 'Request must be JSON'}), 400

    data = request.get_json()
    print(f"Received /update_config request data: {data}", file=sys.stderr)

    config_changes = {}
    updated = False
    valid_keys = ['enable_python_run', 'enable_shell_run', 'port']

    for key in valid_keys:
        if key in data:
            req_value = data[key]
            try:
                if key == 'port':
                    port_val = int(req_value)
                    if 1 <= port_val <= 65535:
                        config_changes[key] = port_val
                        updated = True
                        print(f"Config update: preparing to set {key} to {port_val} in file.", file=sys.stderr)
                    else:
                        print(f"W: Invalid value for '{key}' in request: {req_value}. Port out of range.", file=sys.stderr)
                elif key in ['enable_python_run', 'enable_shell_run']:
                    if isinstance(req_value, bool):
                         config_changes[key] = req_value # Use the direct boolean value
                         updated = True
                         print(f"Config update: preparing to set {key} to {req_value} in file.", file=sys.stderr)
                    else:
                         print(f"W: Invalid type for '{key}' in request: {type(req_value)}. Expected JSON boolean.", file=sys.stderr)
            except (ValueError, TypeError):
                 print(f"W: Invalid value/type for '{key}' in request: {req_value}.", file=sys.stderr)

    if updated:
        save_success, saved_data = save_config(config_changes)
        if save_success:
            return jsonify({
                'status': 'success',
                'message': f'Config saved to {CONFIG_FILE.name}. Restart server for changes to take effect.',
                'saved_config': saved_data
            })
        else:
            return jsonify({'status': 'error', 'message': 'Failed to save config file.'}), 500
    else:
        print("Info: No valid config changes requested.", file=sys.stderr)
        return jsonify({
            'status': 'success',
            'message': 'No valid changes requested. Config file not modified.',
            'current_config_file': load_config()
        })


@app.route('/submit_code', methods=['POST', 'OPTIONS'])
def submit_code():
    if request.method == 'OPTIONS': return '', 204
    if request.method == 'POST':
        if not request_lock.acquire(blocking=False):
             print("W: Request rejected, server busy (lock acquisition failed).", file=sys.stderr) # Add log here
             return jsonify({'status': 'error', 'message': 'Server busy, please try again shortly.'}), 429
        try:
            print("\n--- Handling /submit_code request ---", file=sys.stderr)
            data = request.get_json()
            if not data: return jsonify({'status': 'error', 'message': 'Request body must be JSON.'}), 400
            received_code = data.get('code', '')
            if not received_code or received_code.isspace(): return jsonify({'status': 'error', 'message': 'Empty code received.'}), 400

            save_filepath_str = None; final_save_filename = None
            code_to_save = received_code; extracted_filename_raw = None
            marker_line_length = 0; was_git_updated = False
            sanitized_path_from_marker = None; save_target = "fallback"
            absolute_path_target = None; detected_language_name = "Unknown"

            match = FILENAME_EXTRACT_REGEX.search(received_code)
            if match:
                extracted_filename_raw = match.group(1).strip()
                marker_line_length = match.end(0)
                if marker_line_length < len(received_code) and received_code[marker_line_length] == '\n': marker_line_length += 1
                elif marker_line_length < len(received_code) and received_code[marker_line_length:marker_line_length+2] == '\r\n': marker_line_length += 2
                print(f"Info: Found @@FILENAME@@ marker: '{extracted_filename_raw}'", file=sys.stderr)
                sanitized_path_from_marker = sanitize_filename(extracted_filename_raw)

                if sanitized_path_from_marker:
                    print(f"Info: Sanitized path from marker: '{sanitized_path_from_marker}'", file=sys.stderr)
                    if IS_REPO:
                        git_path_to_check = sanitized_path_from_marker
                        if '/' not in sanitized_path_from_marker.replace('\\', '/'):
                            found_rel_path = find_tracked_file_by_name(sanitized_path_from_marker)
                            if found_rel_path: git_path_to_check = found_rel_path
                        absolute_path_target = (SERVER_DIR / git_path_to_check).resolve()

                        if not str(absolute_path_target).startswith(str(SERVER_DIR)):
                            print(f"W: Potential directory traversal! Path '{absolute_path_target}' outside root '{SERVER_DIR}'. Blocking.", file=sys.stderr)
                            absolute_path_target = None
                        else:
                            is_tracked = is_git_tracked(git_path_to_check)
                            if is_tracked:
                                print(f"Info: Target path '{git_path_to_check}' is tracked. Attempting Git update.", file=sys.stderr)
                                code_to_save = received_code[marker_line_length:]
                                commit_success = update_and_commit_file(absolute_path_target, code_to_save, git_path_to_check)
                                if commit_success:
                                    save_filepath_str = str(absolute_path_target); final_save_filename = git_path_to_check
                                    was_git_updated = True; save_target = "git"
                                    detected_language_name = f"From Git ({Path(git_path_to_check).suffix})"
                                else:
                                    print(f"W: Git update failed for '{git_path_to_check}'. Reverting to fallback.", file=sys.stderr)
                                    code_to_save = received_code; absolute_path_target = None; save_target = "fallback"
                            else:
                                print(f"Info: Path '{git_path_to_check}' not tracked. Saving fallback with this name.", file=sys.stderr)
                                absolute_path_target = (SAVE_FOLDER_PATH / sanitized_path_from_marker).resolve()
                                if not str(absolute_path_target).startswith(str(SAVE_FOLDER_PATH)):
                                     print(f"W: Fallback path '{absolute_path_target}' escaped save folder! Using timestamped.", file=sys.stderr)
                                     absolute_path_target = None
                                code_to_save = received_code; save_target = "fallback"
                    else: # Not a Git repository
                         print(f"Info: Not Git repo. Saving fallback using marker path '{sanitized_path_from_marker}'.", file=sys.stderr)
                         absolute_path_target = (SAVE_FOLDER_PATH / sanitized_path_from_marker).resolve()
                         if not str(absolute_path_target).startswith(str(SAVE_FOLDER_PATH)):
                              print(f"W: Fallback path '{absolute_path_target}' escaped save folder! Using timestamped.", file=sys.stderr)
                              absolute_path_target = None
                         code_to_save = received_code; save_target = "fallback"
                else: # Sanitization failed
                    print(f"W: Invalid marker filename '{extracted_filename_raw}'. Using timestamped fallback.", file=sys.stderr)
                    absolute_path_target = None; save_target = "fallback"; code_to_save = received_code
            else: # No marker found
                print("Info: No @@FILENAME@@ marker. Using timestamped fallback.", file=sys.stderr)
                absolute_path_target = None; save_target = "fallback"; code_to_save = received_code

            if save_target == "fallback":
                if absolute_path_target:
                     save_filepath_str = str(absolute_path_target)
                     try: final_save_filename = Path(save_filepath_str).relative_to(SAVE_FOLDER_PATH).as_posix()
                     except ValueError: final_save_filename = Path(save_filepath_str).name
                     ext = Path(save_filepath_str).suffix.lower()
                     detected_language_name = f"From Path ({ext})" if ext else "From Path (no ext)"
                     print(f"Info: Saving fallback using marker-derived path: '{final_save_filename}' in '{SAVE_FOLDER}'", file=sys.stderr)
                else:
                     base_name = "code"; ext = DEFAULT_EXTENSION
                     if sanitized_path_from_marker:
                         p = Path(sanitized_path_from_marker)
                         base_name = p.stem if p.stem else "code"
                         ext = p.suffix if p.suffix and len(p.suffix) > 1 else DEFAULT_EXTENSION
                         detected_language_name = "From Fallback (Marker Invalid)"
                     else:
                         ext, detected_language_name = detect_language_and_extension(code_to_save)
                     if detected_language_name not in ["Unknown", "Text", "From Fallback (Marker Invalid)"]:
                         base_name = detected_language_name.lower().replace(" ", "_").replace("/", "_")
                     save_filepath_str = generate_timestamped_filepath(extension=ext, base_prefix=base_name)
                     final_save_filename = Path(save_filepath_str).name
                     print(f"Info: Saving fallback using generated filename: '{final_save_filename}'", file=sys.stderr)

                print(f"Info: Writing code to fallback file: '{save_filepath_str}'", file=sys.stderr)
                try:
                    save_path_obj = Path(save_filepath_str)
                    save_path_obj.parent.mkdir(parents=True, exist_ok=True)
                    save_path_obj.write_text(code_to_save, encoding='utf-8')
                    print(f"Success: Code saved to fallback file '{final_save_filename}'", file=sys.stderr)
                except Exception as e:
                    print(f"E: Failed to save fallback file '{save_filepath_str}': {str(e)}", file=sys.stderr)
                    return jsonify({'status': 'error', 'message': f'Failed to save file: {str(e)}'}), 500

            syntax_ok = None; run_success = None; log_filename = None; script_type = None
            if not save_filepath_str or not Path(save_filepath_str).is_file():
                 response_data = {'status': 'success', 'saved_as': final_save_filename, 'saved_path': str(Path(save_filepath_str).relative_to(SERVER_DIR)) if save_filepath_str else None, 'log_file': None, 'syntax_ok': None, 'run_success': None, 'script_type': None, 'source_file_marker': extracted_filename_raw, 'git_updated': was_git_updated, 'save_location': save_target, 'detected_language': detected_language_name, 'message': 'File saved, but checks could not be performed.' }
                 return jsonify(response_data)

            check_run_filepath = save_filepath_str
            display_filename = final_save_filename if final_save_filename else Path(check_run_filepath).name
            file_extension = Path(display_filename).suffix.lower()

            if file_extension == '.py':
                script_type = 'python'
                is_server_script = Path(check_run_filepath).resolve() == (SERVER_DIR / THIS_SCRIPT_NAME).resolve()
                if is_server_script: print(f"Info: Skipping check/run for server script itself.", file=sys.stderr)
                else:
                    print(f"Info: Performing Python syntax check for '{display_filename}'...", file=sys.stderr)
                    try:
                        saved_code_content = Path(check_run_filepath).read_text(encoding='utf-8')
                        compile(saved_code_content, check_run_filepath, 'exec')
                        syntax_ok = True
                        print(f"Info: Python syntax OK.", file=sys.stderr)
                        if AUTO_RUN_PYTHON_ON_SYNTAX_OK:
                            print(f"Info: Attempting Python run (auto-run enabled).", file=sys.stderr)
                            run_success, logpath = run_script(check_run_filepath, 'python')
                            if logpath: log_filename = Path(logpath).name
                        else: print(f"Info: Python auto-run disabled.", file=sys.stderr)
                    except SyntaxError as e:
                        syntax_ok = False; run_success = False
                        err_line = e.lineno if e.lineno else 'N/A'; err_offset = e.offset if e.offset else 'N/A'; err_msg = e.msg if e.msg else 'Unknown'; err_text = e.text.strip() if e.text else 'N/A'
                        print(f"E: Python Syntax Error in '{display_filename}': L{err_line} C{err_offset} -> {err_msg}", file=sys.stderr)
                        log_fn_base = Path(check_run_filepath).stem; log_path_err = LOG_FOLDER_PATH / f"{log_fn_base}_py_syntax_error.log"
                        try: # Colon needed
                            log_path_err.parent.mkdir(parents=True, exist_ok=True)
                            log_path_err.write_text(f"Python Syntax Error:\nFile: {display_filename}\nLine: {err_line}\nOffset: {err_offset}\nMessage: {err_msg}\nContext:\n{err_text}", encoding='utf-8')
                            log_filename = log_path_err.name
                        except Exception as log_e: print(f"E: Could not write Python syntax error log: {log_e}", file=sys.stderr)
                    except Exception as compile_e:
                        syntax_ok = False; run_success = False
                        print(f"E: Error during Python compile/setup for '{display_filename}': {compile_e}", file=sys.stderr)
                        log_fn_base = Path(check_run_filepath).stem; log_path_err = LOG_FOLDER_PATH / f"{log_fn_base}_py_compile_error.log"
                        try: # Colon needed
                            log_path_err.parent.mkdir(parents=True, exist_ok=True)
                            log_path_err.write_text(f"Python Compile/Setup Error:\nFile: {display_filename}\nError: {compile_e}\n", encoding='utf-8')
                            log_filename = log_path_err.name
                        except Exception as log_e: print(f"E: Could not write Python compile error log: {log_e}", file=sys.stderr)

            elif file_extension == '.sh':
                 script_type = 'shell'
                 print(f"Info: Performing Shell syntax check for '{display_filename}'...", file=sys.stderr)
                 syntax_ok, syntax_log_path = check_shell_syntax(check_run_filepath)
                 if syntax_log_path: log_filename = Path(syntax_log_path).name
                 if syntax_ok:
                      if AUTO_RUN_SHELL_ON_SYNTAX_OK:
                           print(f"Info: Attempting Shell run (auto-run enabled).", file=sys.stderr)
                           run_success, run_log_path = run_script(check_run_filepath, 'shell')
                           if run_log_path: log_filename = Path(run_log_path).name
                      else: print(f"Info: Shell auto-run disabled.", file=sys.stderr)
                 else: run_success = False

            else: print(f"Info: Not .py or .sh. Skipping syntax checks/execution.", file=sys.stderr)

            response_data = {
                'status': 'success', 'saved_as': final_save_filename,
                'saved_path': str(Path(save_filepath_str).relative_to(SERVER_DIR)) if save_filepath_str else None,
                'log_file': log_filename, 'syntax_ok': syntax_ok, 'run_success': run_success,
                'script_type': script_type, 'source_file_marker': extracted_filename_raw,
                'git_updated': was_git_updated, 'save_location': save_target,
                'detected_language': detected_language_name
            }
            print(f"Sending response: {response_data}", file=sys.stderr)
            print("--- Request complete ---")
            return jsonify(response_data)

        except Exception as e:
            print(f"E: Unhandled exception during /submit_code: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            return jsonify({'status': 'error', 'message': f'Internal server error: {e}'}), 500
        finally:
            if request_lock.locked(): request_lock.release()

    return jsonify({'status': 'error', 'message': f'Unsupported method: {request.method}'}), 405


@app.route('/test_connection', methods=['GET'])
def test_connection():
    """Simple endpoint to test if the server is running, returns status."""
    print("Received /test_connection request", file=sys.stderr)
    return get_status()

# --- Log Routes (No changes needed) ---
@app.route('/logs')
def list_logs():
    log_files = []
    template = '''<!DOCTYPE html><html><head><title>Logs Browser</title><style>body{font-family:sans-serif;background-color:#f4f4f4;color:#333;margin:0;padding:20px}h1{color:#444;border-bottom:1px solid #ccc;padding-bottom:10px}ul{list-style:none;padding:0}li{background-color:#fff;margin-bottom:8px;border:1px solid #ddd;border-radius:4px;transition:box-shadow .2s ease-in-out}li:hover{box-shadow:0 2px 5px rgba(0,0,0,.1)}li a{color:#007bff;text-decoration:none;display:block;padding:12px 15px}li a:hover{background-color:#eee}p{color:#666}pre{background-color:#eee;border:1px solid #ccc;padding:15px;border-radius:5px;overflow-x:auto;white-space:pre-wrap;word-wrap:break-word;font-family:monospace}</style></head><body><h1>🗂️ Available Logs</h1>{% if logs %}<p>Found {{ logs|length }} log file(s) in '{{ log_folder_name }}'. Click to view.</p><ul>{% for log in logs %}<li><a href="/logs/{{ log | urlencode }}">{{ log }}</a></li>{% endfor %}</ul>{% else %}<p>No log files found in '{{ log_folder_name }}'.</p>{% endif %}</body></html>'''
    try:
         if LOG_FOLDER_PATH.is_dir():
             log_paths = [p for p in LOG_FOLDER_PATH.glob('*.log') if p.is_file()]
             log_paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
             log_files = [p.name for p in log_paths]
    except Exception as e: print(f"E: Error listing log files: {e}", file=sys.stderr)
    return render_template_string(template, logs=log_files, log_folder_name=LOG_FOLDER_PATH.name)


@app.route('/logs/<path:filename>')
def serve_log(filename):
    if '..' in filename or filename.startswith('/'): return "Forbidden", 403
    try:
        log_dir = LOG_FOLDER_PATH.resolve()
        requested_path = (log_dir / filename).resolve()
        if not str(requested_path).startswith(str(log_dir)) or not requested_path.is_file():
            return "Log file not found", 404
        return send_from_directory(LOG_FOLDER_PATH, filename, mimetype='text/plain; charset=utf-8', as_attachment=False)
    except Exception as e: print(f"E: Error serving log file {filename}: {e}", file=sys.stderr); return "Error serving file", 500

# --- Main Execution ---
if __name__ == '__main__':
    host_ip = '127.0.0.1'
    port_num = SERVER_PORT # Use the effective port

    print(f"--- AI Code Capture Server ---")
    print(f"Config File Path: '{CONFIG_FILE}' ({'Exists' if CONFIG_FILE.is_file() else 'Not Found'})")
    # Load config again just for display ensures we show the actual file content at startup
    print(f"  Config File Content: {load_config()}")
    print("-" * 30)
    print(f"Effective RUNNING Settings:")
    print(f"  Host: {host_ip}")
    print(f"  Port: {port_num}")
    print(f"  Server CWD (Potential Git Root): {SERVER_DIR}")
    print(f"  Saving Non-Git Files to: ./{SAVE_FOLDER_PATH.relative_to(SERVER_DIR)}")
    print(f"  Saving Logs to:            ./{LOG_FOLDER_PATH.relative_to(SERVER_DIR)}")
    print(f"  Git Integration: {'ENABLED' if IS_REPO else 'DISABLED'}")
    print(f"  Python Auto-Run: {'ENABLED' if AUTO_RUN_PYTHON_ON_SYNTAX_OK else 'DISABLED'}")
    print(f"  Shell Auto-Run:  {'ENABLED' if AUTO_RUN_SHELL_ON_SYNTAX_OK else 'DISABLED'}{' <-- DANGEROUS!' if AUTO_RUN_SHELL_ON_SYNTAX_OK else ''}")
    print("-" * 30)
    print(f"Starting Flask server on http://{host_ip}:{port_num}")
    print("Use Ctrl+C to stop the server.")
    print(f"NOTE: Config changes made via the popup require a server restart to take effect.", file=sys.stderr)
    print("--- Server ready ---", file=sys.stderr)

    try:
        app.run(host=host_ip, port=port_num, debug=False)
    except OSError as e:
        if "Address already in use" in str(e) or ("WinError 10048" in str(e) and os.name == 'nt'):
            print(f"\nE: Port {port_num} is already in use.", file=sys.stderr)
            print(f"   Stop the other process or use '-p <new_port>'", file=sys.stderr)
            sys.exit(1)
        else: print(f"\nE: Failed to start server: {e}", file=sys.stderr); sys.exit(1)
    except KeyboardInterrupt: print("\n--- Server shutting down ---", file=sys.stderr); sys.exit(0)
    except Exception as e: print(f"\nE: Unexpected error during startup: {e}", file=sys.stderr); sys.exit(1)
# @@FILENAME@@ server.py