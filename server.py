#!/usr/bin/env python3

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
        return defaults
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            # Validate types or provide defaults for missing keys
            loaded_config = defaults.copy() # Start with defaults
            loaded_config['port'] = int(config.get('port', defaults['port']))
            loaded_config['enable_python_run'] = bool(config.get('enable_python_run', defaults['enable_python_run']))
            loaded_config['enable_shell_run'] = bool(config.get('enable_shell_run', defaults['enable_shell_run']))
            print(f"Info: Loaded config from '{CONFIG_FILE}': {loaded_config}", file=sys.stderr)
            return loaded_config
    except (json.JSONDecodeError, ValueError, TypeError, OSError) as e:
        print(f"W: Error reading config file '{CONFIG_FILE}': {e}. Using defaults.", file=sys.stderr)
        return defaults

def save_config(config_data):
    """Saves config data to JSON file."""
    try:
        # Ensure values are correct types before saving
        config_to_save = {
            'port': int(config_data.get('port', 5000)),
            'enable_python_run': bool(config_data.get('enable_python_run', False)),
            'enable_shell_run': bool(config_data.get('enable_shell_run', False))
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_to_save, f, indent=4)
        print(f"Info: Configuration saved to '{CONFIG_FILE}'.", file=sys.stderr)
        return True
    except (OSError, TypeError, ValueError) as e:
        print(f"E: Failed to save config file '{CONFIG_FILE}': {e}", file=sys.stderr)
        return False

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

# Check if flags were explicitly passed on command line to override config
cmd_line_overrides = any(arg in sys.argv for arg in ['--shell', '--enable-python-run'])

AUTO_RUN_PYTHON_ON_SYNTAX_OK = args.enable_python_run if '--enable-python-run' in sys.argv else current_config['enable_python_run']
AUTO_RUN_SHELL_ON_SYNTAX_OK = args.shell if '--shell' in sys.argv else current_config['enable_shell_run']

# This dictionary reflects the actual running state
final_config_for_status = {
    'port': SERVER_PORT,
    'enable_python_run': AUTO_RUN_PYTHON_ON_SYNTAX_OK,
    'enable_shell_run': AUTO_RUN_SHELL_ON_SYNTAX_OK
}

# --- Flask App Setup ---
app = Flask(__name__)
# Allow all origins - adjust in production if needed
CORS(app, resources={r"/*": {"origins": "*"}})

# --- Lock ---
request_lock = threading.Lock()
print("Request lock initialized.", file=sys.stderr)

# --- Paths & Constants ---
SAVE_FOLDER = 'received_codes'; LOG_FOLDER = 'logs'
SERVER_DIR = Path.cwd().resolve()
SAVE_FOLDER_PATH = SERVER_DIR / SAVE_FOLDER
LOG_FOLDER_PATH = SERVER_DIR / LOG_FOLDER
THIS_SCRIPT_NAME = Path(__file__).name
os.makedirs(SAVE_FOLDER_PATH, exist_ok=True)
os.makedirs(LOG_FOLDER_PATH, exist_ok=True)

FILENAME_EXTRACT_REGEX = re.compile(r"^\s*(?://|#)\s*@@FILENAME@@\s+(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
FILENAME_SANITIZE_REGEX = re.compile(r'[^\w\.\-\/]') # More permissive: Allow word chars, dot, dash, slash
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
# >>> HELPER FUNCTIONS <<<
# =====================================================

def sanitize_filename(filename: str) -> str | None:
    """Sanitizes a filename or relative path."""
    if not filename or filename.isspace(): return None
    filename = filename.strip()

    # Security: Prevent absolute paths and directory traversal
    if filename.startswith(('/', '\\')) or '..' in Path(filename).parts:
        print(f"W: Rejected potentially unsafe path pattern: {filename}", file=sys.stderr)
        return None

    # Security: Prevent hidden files/dirs at the end of the path
    if Path(filename).name.startswith('.'):
        print(f"W: Rejected path ending in hidden file/directory: {filename}", file=sys.stderr)
        return None

    # Normalize path separators for consistency
    filename = filename.replace('\\', '/')

    # Sanitize characters in each part of the path
    parts = filename.split('/')
    sanitized_parts = []
    for part in parts:
        # Replace sequences of disallowed characters with a single underscore
        sanitized_part = FILENAME_SANITIZE_REGEX.sub('_', part)
        # Remove leading/trailing underscores that might result from sanitization
        sanitized_part = sanitized_part.strip('_')
        # If a part becomes empty after sanitization, reject the path
        if not sanitized_part:
            print(f"W: Path segment became empty after sanitization in '{filename}'. Rejecting.", file=sys.stderr)
            return None
        sanitized_parts.append(sanitized_part)

    sanitized = '/'.join(sanitized_parts)

    # Length check
    if len(sanitized) > MAX_FILENAME_LENGTH:
        print(f"W: Sanitized path too long ('{sanitized}'), might be truncated unexpectedly.", file=sys.stderr)
        # Attempt intelligent truncation
        base, ext = os.path.splitext(sanitized)
        original_ext = Path(filename).suffix # Get original extension if any
        max_base_len = MAX_FILENAME_LENGTH - len(original_ext if original_ext else '')
        if max_base_len < 1: # Cannot even fit extension
             print(f"W: Path too long even for extension. Hard truncating.", file=sys.stderr)
             sanitized = sanitized[:MAX_FILENAME_LENGTH]
        else:
             sanitized = base[:max_base_len] + (original_ext if original_ext else '')

    # Final check for empty basename or missing extension after potential truncation
    final_path = Path(sanitized)
    if not final_path.name or final_path.name.startswith('.'): # Should be caught earlier, but double-check
         print(f"W: Final sanitized path has empty or hidden basename: '{sanitized}'. Rejecting.", file=sys.stderr)
         return None
    if not final_path.suffix or len(final_path.suffix) < 2:
        print(f"W: Sanitized path '{sanitized}' lacks a proper extension. Appending {DEFAULT_EXTENSION}", file=sys.stderr)
        sanitized += DEFAULT_EXTENSION

    return sanitized


def detect_language_and_extension(code: str) -> tuple[str, str]:
    """Detects language and returns (extension, language_name)."""
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
    if LANGUAGE_PATTERNS['.sh'].search(code): return '.sh', 'Shell'
    if LANGUAGE_PATTERNS['.js'].search(code): return '.js', 'JavaScript'
    if LANGUAGE_PATTERNS['.sql'].search(code): return '.sql', 'SQL'
    if LANGUAGE_PATTERNS['.md'].search(code): return '.md', 'Markdown'

    print("W: Cannot detect language. Defaulting to .txt", file=sys.stderr)
    return DEFAULT_EXTENSION, 'Text'

def generate_timestamped_filepath(extension: str = '.txt', base_prefix="code"):
    """Generates a unique timestamped filepath in SAVE_FOLDER_PATH."""
    today = datetime.datetime.now().strftime("%Y%m%d"); counter = 1
    if not extension.startswith('.'): extension = '.' + extension
    # Sanitize base_prefix just in case (allow only basic chars for prefix)
    safe_base_prefix = re.sub(r'[^a-zA-Z0-9_\-]', '_', base_prefix).strip('_')
    if not safe_base_prefix: safe_base_prefix = "code"

    while True:
        filename = f"{safe_base_prefix}_{today}_{counter:03d}{extension}"
        filepath = SAVE_FOLDER_PATH / filename
        if not filepath.exists():
            # No need to mkdir here, saving logic will handle it if needed
            return str(filepath)
        counter += 1
        if counter > 999: # Avoid potential infinite loop
             print(f"W: Could not find unique filename for prefix '{safe_base_prefix}' after 999 attempts. Adding timestamp.", file=sys.stderr)
             fallback_filename = f"{safe_base_prefix}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{extension}"
             return str(SAVE_FOLDER_PATH / fallback_filename)

def is_git_repository() -> bool:
    """Checks if SERVER_DIR is a Git repository."""
    try:
        result = subprocess.run(['git', 'rev-parse', '--git-dir'], capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR, timeout=5)
        is_repo = result.returncode == 0
        if not is_repo and result.stderr and 'not a git repository' not in result.stderr.lower():
             print(f"W: Git check failed: {result.stderr.strip()}", file=sys.stderr)
        elif not is_repo:
             print("Info: Not running inside a Git repository.", file=sys.stderr)
        return is_repo
    except FileNotFoundError: print("W: 'git' command not found.", file=sys.stderr); return False
    except subprocess.TimeoutExpired: print("W: Git check timed out.", file=sys.stderr); return False
    except Exception as e: print(f"E: checking Git repository: {e}", file=sys.stderr); return False

IS_REPO = is_git_repository() # Define global after function definition

def find_tracked_file_by_name(basename_to_find: str) -> str | None:
    """Finds a unique tracked file by its basename within the repo."""
    if not IS_REPO: return None
    try:
        # Search using git ls-files with pattern matching end of path
        command = ['git', 'ls-files', f'**/{basename_to_find}']
        print(f"Running: {' '.join(command)} from {SERVER_DIR} to find matches for '*/{basename_to_find}'", file=sys.stderr)
        result = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR, timeout=5)

        if result.returncode != 0:
            # Error doesn't necessarily mean failure if pattern just doesn't match
             if result.returncode == 1 and not result.stdout and not result.stderr:
                 print(f"Info: No tracked file ending in '{basename_to_find}' found (git ls-files returned 1).", file=sys.stderr)
             else:
                 print(f"E: 'git ls-files' failed (RC={result.returncode}):\n{result.stderr}", file=sys.stderr)
             return None

        tracked_files = result.stdout.splitlines()
        # Filter for exact basename match (case-sensitive on Linux/macOS usually)
        matches = [f for f in tracked_files if Path(f).name == basename_to_find]

        if len(matches) == 1:
            print(f"Info: Found unique tracked file match via ls-files: '{matches[0]}'", file=sys.stderr)
            return matches[0]
        elif len(matches) > 1:
            print(f"W: Ambiguous filename marker '{basename_to_find}'. Found multiple tracked files: {matches}. Cannot determine target.", file=sys.stderr)
            return None
        else:
            print(f"Info: No tracked file with exact basename '{basename_to_find}' found in Git index.", file=sys.stderr)
            return None

    except subprocess.TimeoutExpired: print("W: Git ls-files check timed out.", file=sys.stderr); return None
    except Exception as e: print(f"E: checking Git for file '{basename_to_find}': {e}", file=sys.stderr); return None

def is_git_tracked(filepath_relative_to_repo: str) -> bool:
    """Checks if a specific relative path is tracked by Git."""
    if not IS_REPO: return False
    try:
        git_path = Path(filepath_relative_to_repo).as_posix() # Use POSIX paths for Git
        command = ['git', 'ls-files', '--error-unmatch', git_path]
        # Use check=True and catch CalledProcessError for cleaner logic
        subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', cwd=SERVER_DIR, timeout=5)
        # print(f"Info: Git track status for '{git_path}': True (Tracked)", file=sys.stderr) # Less verbose
        return True
    except subprocess.CalledProcessError:
        # This error (returncode 1) specifically means the file is not tracked
        # print(f"Info: Git track status for '{git_path}': False (Not tracked or doesn't exist in index)", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired: print(f"W: Git track status check timed out for '{filepath_relative_to_repo}'.", file=sys.stderr); return False
    except Exception as e: print(f"E: checking Git track status for '{filepath_relative_to_repo}': {e}", file=sys.stderr); return False


def update_and_commit_file(filepath_absolute: Path, code_content: str, marker_filename: str) -> bool:
    """Writes content to file, stages, and commits if tracked and changed."""
    if not IS_REPO: return False
    try:
        filepath_relative_to_repo_str = str(filepath_absolute.relative_to(SERVER_DIR))
        git_path_posix = filepath_absolute.relative_to(SERVER_DIR).as_posix()

        # Ensure parent directories exist
        filepath_absolute.parent.mkdir(parents=True, exist_ok=True)

        # Check if content is actually different to avoid empty commits
        current_content = ""
        if filepath_absolute.exists():
             try: current_content = filepath_absolute.read_text(encoding='utf-8')
             except Exception as read_e: print(f"W: Could not read existing file {filepath_relative_to_repo_str} to check for changes: {read_e}", file=sys.stderr)

        if code_content == current_content:
             print(f"Info: Content for '{filepath_relative_to_repo_str}' has not changed. Skipping Git commit.", file=sys.stderr)
             return True # Treat as success

        # Content is different, write and proceed with Git
        print(f"Info: Overwriting local file: {filepath_relative_to_repo_str}", file=sys.stderr)
        filepath_absolute.write_text(code_content, encoding='utf-8')

        # Stage the specific file
        print(f"Running: git add '{git_path_posix}' from {SERVER_DIR}", file=sys.stderr)
        add_result = subprocess.run(['git', 'add', git_path_posix], capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR, timeout=10)
        if add_result.returncode != 0:
            print(f"E: 'git add' failed for {git_path_posix}:\n{add_result.stderr}", file=sys.stderr)
            return False

        # Commit only the staged file
        commit_message = f"Update {marker_filename} from AI Code Capture"
        print(f"Running: git commit -m \"{commit_message}\" '{git_path_posix}' from {SERVER_DIR}", file=sys.stderr)
        commit_result = subprocess.run(['git', 'commit', '-m', commit_message, '--', git_path_posix], capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR, timeout=15)

        if commit_result.returncode == 0:
             print(f"Success: Committed changes for {git_path_posix}.", file=sys.stderr)
             return True
        else:
             no_changes_patterns = ["nothing to commit", "no changes added to commit", "nothing added to commit but untracked files present"]
             commit_output = commit_result.stdout + commit_result.stderr
             if any(pattern in commit_output for pattern in no_changes_patterns):
                 print(f"Info: No effective changes detected by Git for commit on {git_path_posix}.", file=sys.stderr)
                 # Potentially unstage if add succeeded but commit finds no changes?
                 # subprocess.run(['git', 'reset', 'HEAD', '--', git_path_posix], cwd=SERVER_DIR)
                 return True # Not a failure
             else:
                 print(f"E: 'git commit' failed for {git_path_posix}:\n{commit_output}", file=sys.stderr)
                 return False

    except IOError as e: print(f"E: Writing file {filepath_absolute}: {e}", file=sys.stderr); return False
    except subprocess.TimeoutExpired: print(f"E: Git operation timed out for {filepath_absolute}.", file=sys.stderr); return False
    except Exception as e: print(f"E: During Git update/commit for {filepath_absolute}: {e}", file=sys.stderr); return False


def run_script(filepath: str, script_type: str):
    """Runs a Python or Shell script, logs output."""
    filepath_obj = Path(filepath)
    filename_base = filepath_obj.stem
    logpath = LOG_FOLDER_PATH / f"{filename_base}_{script_type}_run.log"
    run_cwd = filepath_obj.parent
    os.makedirs(LOG_FOLDER_PATH, exist_ok=True)

    command = []
    interpreter_name = ""
    if script_type == 'python':
        python_exe = sys.executable or "python3" # Fallback if sys.executable is None
        command = [python_exe, filepath_obj.name]
        interpreter_name = Path(python_exe).name
        print(f"Executing Python: {' '.join(command)} in {run_cwd}", file=sys.stderr)
    elif script_type == 'shell':
        # Defaulting to bash, could try sh or parse shebang if needed
        shell_exe = shutil.which("bash") or shutil.which("sh") or "bash" # Find bash or sh
        command = [shell_exe, filepath_obj.name]
        interpreter_name = Path(shell_exe).name
        print(f"Executing Shell ({interpreter_name}): {' '.join(command)} in {run_cwd}", file=sys.stderr)
    else:
        print(f"E: Cannot run script of unknown type '{script_type}' for file {filepath}", file=sys.stderr)
        return False, None

    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, encoding='utf-8', check=False, cwd=run_cwd)
        with open(logpath, 'w', encoding='utf-8') as f:
            f.write(f"--- COMMAND ---\n{' '.join(command)}\n")
            f.write(f"--- CWD ---\n{run_cwd}\n")
            f.write(f"--- STDOUT ---\n{result.stdout}\n")
            f.write(f"--- STDERR ---\n{result.stderr}\n")
            f.write(f"--- Return Code: {result.returncode} ---\n")
        print(f"Exec finished ({script_type}). RC: {result.returncode}. Log: {logpath.name}", file=sys.stderr)
        return result.returncode == 0, str(logpath)
    except subprocess.TimeoutExpired:
        print(f"E: Script timed out: {filepath}", file=sys.stderr)
        with open(logpath, 'w', encoding='utf-8') as f: f.write(f"Error: Script timed out after 15 seconds.\nCommand: {' '.join(command)}\n")
        return False, str(logpath)
    except FileNotFoundError:
         print(f"E: Interpreter '{interpreter_name}' or script '{filepath_obj.name}' not found.", file=sys.stderr)
         with open(logpath, 'w', encoding='utf-8') as f: f.write(f"Error: Interpreter or script not found.\nCommand: {' '.join(command)}\n")
         return False, str(logpath)
    except Exception as e:
        print(f"E: running script {filepath}: {e}", file=sys.stderr)
        with open(logpath, 'w', encoding='utf-8') as f: f.write(f"Error running script: {str(e)}\nCommand: {' '.join(command)}\n")
        return False, str(logpath)


def check_shell_syntax(filepath: str) -> tuple[bool, str | None]:
    """Checks shell script syntax using 'bash -n'. Returns (syntax_ok, log_path)."""
    filepath_obj = Path(filepath)
    filename_base = filepath_obj.stem
    logpath = LOG_FOLDER_PATH / f"{filename_base}_shell_syntax.log"
    os.makedirs(LOG_FOLDER_PATH, exist_ok=True)
    checker_exe = shutil.which("bash") or "bash" # Find bash
    command = [checker_exe, '-n', str(filepath_obj.resolve())] # Use absolute path

    print(f"Checking Shell syntax: {' '.join(command)}", file=sys.stderr)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, encoding='utf-8', check=False)
        syntax_ok = result.returncode == 0
        with open(logpath, 'w', encoding='utf-8') as f:
             f.write(f"--- COMMAND ---\n{' '.join(command)}\n")
             status_msg = "SYNTAX OK" if syntax_ok else f"SYNTAX ERROR (RC: {result.returncode})"
             f.write(f"--- STATUS: {status_msg} ---\n")
             f.write(f"--- STDOUT ---\n{result.stdout}\n")
             f.write(f"--- STDERR ---\n{result.stderr}\n") # Errors usually on stderr

        if syntax_ok:
            print(f"Shell syntax OK for {filepath_obj.name}", file=sys.stderr)
            return True, str(logpath)
        else:
            print(f"Shell syntax Error for {filepath_obj.name}. RC: {result.returncode}. Log: {logpath.name}", file=sys.stderr)
            return False, str(logpath)
    except FileNotFoundError:
         print(f"E: Syntax check command not found: '{checker_exe}'", file=sys.stderr)
         with open(logpath, 'w', encoding='utf-8') as f: f.write(f"Error: Syntax check command ('{checker_exe}') not found.\n")
         return False, str(logpath)
    except subprocess.TimeoutExpired:
        print(f"E: Shell syntax check timed out: {filepath}", file=sys.stderr)
        with open(logpath, 'w', encoding='utf-8') as f: f.write("Error: Shell syntax check timed out after 10 seconds.\n")
        return False, str(logpath)
    except Exception as e:
        print(f"E: checking shell syntax for {filepath}: {e}", file=sys.stderr)
        with open(logpath, 'w', encoding='utf-8') as f: f.write(f"Error during shell syntax check: {str(e)}\n")
        return False, str(logpath)


# --- Route Definitions ---

@app.route('/status', methods=['GET'])
def get_status():
    """Returns current server status and configuration."""
    print("Received /status request", file=sys.stderr)
    status_data = {
        'status': 'running',
        'working_directory': str(SERVER_DIR),
        'save_directory': str(SAVE_FOLDER_PATH.relative_to(SERVER_DIR)),
        'log_directory': str(LOG_FOLDER_PATH.relative_to(SERVER_DIR)),
        'is_git_repo': IS_REPO,
        'port': SERVER_PORT,
        'auto_run_python': AUTO_RUN_PYTHON_ON_SYNTAX_OK,
        'auto_run_shell': AUTO_RUN_SHELL_ON_SYNTAX_OK,
        'config_file_exists': CONFIG_FILE.is_file()
    }
    return jsonify(status_data)

@app.route('/update_config', methods=['POST'])
def update_config():
    """Updates the server_config.json file with settings from the request."""
    if not request.is_json:
        return jsonify({'status': 'error', 'message': 'Request must be JSON'}), 400

    data = request.get_json()
    print(f"Received /update_config request data: {data}", file=sys.stderr)

    config_to_save = load_config() # Reload current config from file

    # Update flags if present and valid boolean in request
    python_run = data.get('auto_run_python')
    shell_run = data.get('auto_run_shell')

    updated = False
    if python_run is not None and isinstance(python_run, bool):
        if config_to_save.get('enable_python_run') != python_run:
            config_to_save['enable_python_run'] = python_run
            print(f"Config update: set enable_python_run to {python_run}", file=sys.stderr)
            updated = True
    elif python_run is not None:
        print(f"W: Invalid type for auto_run_python in update request: {type(python_run)}", file=sys.stderr)

    if shell_run is not None and isinstance(shell_run, bool):
         if config_to_save.get('enable_shell_run') != shell_run:
            config_to_save['enable_shell_run'] = shell_run
            print(f"Config update: set enable_shell_run to {shell_run}", file=sys.stderr)
            updated = True
    elif shell_run is not None:
        print(f"W: Invalid type for auto_run_shell in update request: {type(shell_run)}", file=sys.stderr)

    # Save only if something actually changed
    if updated:
        if save_config(config_to_save):
            return jsonify({
                'status': 'success',
                'message': f'Configuration saved to {CONFIG_FILE.name}. Restart server manually for changes to take effect.',
                'saved_config': config_to_save
            })
        else:
            return jsonify({'status': 'error', 'message': 'Failed to save configuration file.'}), 500
    else:
         print("Info: No configuration changes requested in /update_config.", file=sys.stderr)
         return jsonify({
            'status': 'success',
            'message': 'No changes detected in request. Configuration file not modified.',
            'saved_config': config_to_save # Return current file content
         })

@app.route('/submit_code', methods=['POST', 'OPTIONS'])
def submit_code():
    if request.method == 'OPTIONS': return '', 204 # Handle CORS preflight
    if request.method == 'POST':
        with request_lock: # Ensure only one request handles files/git at a time
            print("--- Handling /submit_code request (Lock acquired) ---", file=sys.stderr)
            data = request.get_json()
            if not data: print("E: No JSON data received.", file=sys.stderr); return jsonify({'status': 'error', 'message': 'No JSON data received'}), 400
            received_code = data.get('code', '');
            if not received_code or received_code.isspace(): print("E: Empty code received.", file=sys.stderr); return jsonify({'status': 'error', 'message': 'Empty code received'}), 400

            # --- Variable Initialization ---
            save_filepath_str = None; final_save_filename = None; code_to_save = received_code
            extracted_filename_raw = None; detected_language_name = "Unknown"
            marker_line_length = 0; was_git_updated = False; sanitized_path_from_marker = None
            save_target = "fallback"; absolute_path_target = None

            # --- 1. Check for @@FILENAME@@ Marker ---
            match = FILENAME_EXTRACT_REGEX.search(received_code)
            if match:
                extracted_filename_raw = match.group(1).strip()
                marker_line_length = match.end();
                if marker_line_length < len(received_code) and received_code[marker_line_length] == '\n': marker_line_length += 1
                print(f"Info: Found @@FILENAME@@ marker: '{extracted_filename_raw}'", file=sys.stderr)
                sanitized_path_from_marker = sanitize_filename(extracted_filename_raw)

                if sanitized_path_from_marker:
                    print(f"Info: Sanitized relative path from marker: '{sanitized_path_from_marker}'", file=sys.stderr)
                    # --- 2. Attempt Git Integration ---
                    if IS_REPO:
                        git_path_to_check = sanitized_path_from_marker
                        if '/' not in sanitized_path_from_marker.replace('\\', '/'):
                            print(f"Info: Marker is basename only ('{sanitized_path_from_marker}'). Searching Git index...", file=sys.stderr)
                            found_rel_path = find_tracked_file_by_name(sanitized_path_from_marker)
                            if found_rel_path: git_path_to_check = found_rel_path
                            else: git_path_to_check = sanitized_path_from_marker # Treat as potentially new file

                        absolute_path_target = (SERVER_DIR / git_path_to_check).resolve()

                        if not str(absolute_path_target).startswith(str(SERVER_DIR)):
                            print(f"W: Resolved path '{absolute_path_target}' is outside server dir ({SERVER_DIR}). Blocking Git operation.", file=sys.stderr)
                            absolute_path_target = None # Prevent Git use
                        else:
                            is_tracked = is_git_tracked(git_path_to_check)
                            if is_tracked:
                                print(f"Info: Target file '{git_path_to_check}' is tracked by Git. Attempting update and commit.", file=sys.stderr)
                                code_to_save = received_code[marker_line_length:] # Use code *after* marker
                                commit_success = update_and_commit_file(absolute_path_target, code_to_save, git_path_to_check)
                                if commit_success:
                                    save_filepath_str = str(absolute_path_target); final_save_filename = git_path_to_check
                                    was_git_updated = True; save_target = "git"
                                    print(f"Success: Git update/commit successful for {git_path_to_check}.", file=sys.stderr)
                                else:
                                    print(f"W: Git commit failed for {git_path_to_check}. Saving to fallback location.", file=sys.stderr)
                                    code_to_save = received_code # Revert to full code for fallback
                                    absolute_path_target = None # Force fallback path generation
                            else: # Valid path, in repo, but not tracked
                                print(f"Info: Path '{git_path_to_check}' is valid but not tracked by Git. Saving to this path (no commit).", file=sys.stderr)
                                code_to_save = received_code # Save full code including marker
                                # Keep absolute_path_target, save there in fallback logic
                    else: # Not a Git repo
                         print(f"Info: Not a Git repository. Will save using marker path '{sanitized_path_from_marker}' in fallback location.", file=sys.stderr)
                         absolute_path_target = (SAVE_FOLDER_PATH / sanitized_path_from_marker).resolve()
                         if not str(absolute_path_target).startswith(str(SAVE_FOLDER_PATH)):
                              print(f"W: Resolved fallback path '{absolute_path_target}' outside save folder. Using timestamped name.", file=sys.stderr)
                              absolute_path_target = None
                         else: code_to_save = received_code
                else: # Marker found but invalid filename
                    print(f"W: Invalid filename extracted from marker: '{extracted_filename_raw}'. Using fallback save.", file=sys.stderr)
                    absolute_path_target = None
            else: # No marker found
                 print("Info: No @@FILENAME@@ marker found. Using fallback save.", file=sys.stderr)
                 absolute_path_target = None

            # --- 3. Fallback Saving Logic ---
            if save_target == "fallback":
                if absolute_path_target: # Use path from marker (untracked or non-git repo)
                     save_filepath_str = str(absolute_path_target)
                     final_save_filename = Path(save_filepath_str).relative_to(SAVE_FOLDER_PATH).as_posix() if str(save_filepath_str).startswith(str(SAVE_FOLDER_PATH)) else Path(save_filepath_str).name
                     ext = Path(save_filepath_str).suffix.lower()
                     if ext == '.py': detected_language_name = "Python"
                     elif ext == '.sh': detected_language_name = "Shell"
                     else: detected_language_name = "From Marker Path"
                else: # Generate timestamped filename
                     base_name_for_fallback = "code"; ext_for_fallback = DEFAULT_EXTENSION
                     if sanitized_path_from_marker: # Use marker info for naming if path wasn't used
                         p = Path(sanitized_path_from_marker)
                         base_name_for_fallback = p.stem if p.stem else "code"; ext_for_fallback = p.suffix if p.suffix else DEFAULT_EXTENSION
                         detected_language_name = "From Marker (Invalid Path)"
                     else: # Detect language if no marker at all
                         detected_ext, detected_language_name = detect_language_and_extension(code_to_save); ext_for_fallback = detected_ext

                     if detected_language_name not in ["Unknown", "Text", "From Marker (Invalid Path)", "From Marker Path"]: base_name_for_fallback = detected_language_name.lower().replace(" ", "_")
                     save_filepath_str = generate_timestamped_filepath(extension=ext_for_fallback, base_prefix=base_name_for_fallback)
                     final_save_filename = Path(save_filepath_str).name # Basename for timestamped

                # Perform the save
                print(f"Info: Saving fallback file to: '{save_filepath_str}'", file=sys.stderr)
                try:
                    save_path_obj = Path(save_filepath_str)
                    save_path_obj.parent.mkdir(parents=True, exist_ok=True)
                    save_path_obj.write_text(code_to_save, encoding='utf-8')
                    print(f"Success: Code saved successfully to {save_filepath_str}", file=sys.stderr)
                except Exception as e:
                    print(f"E: Failed to save fallback file '{save_filepath_str}': {str(e)}", file=sys.stderr)
                    return jsonify({'status': 'error', 'message': f'Failed to save file: {str(e)}'}), 500

            # --- 4. Syntax Check & Optional Execution ---
            syntax_ok = None; run_success = None; log_filename = None
            script_type = None

            if not save_filepath_str: # Should not happen if saving logic is correct
                 print("E: Internal error - save_filepath_str is not set before checks.", file=sys.stderr); return jsonify({'status': 'error', 'message': 'Internal server error saving file path.'}), 500

            # Determine effective filename for checks (might be relative path if git, or basename if fallback)
            check_filename = final_save_filename if save_target == 'git' else Path(save_filepath_str).name
            file_extension = Path(check_filename).suffix.lower()

            if file_extension == '.py':
                script_type = 'python'
                is_server_script = Path(save_filepath_str).resolve() == (SERVER_DIR / THIS_SCRIPT_NAME).resolve()

                if is_server_script: print(f"Info: Skipping run checks for server script itself: '{check_filename}'. Checking syntax only.", file=sys.stderr)
                else: print(f"Info: File '{check_filename}' is Python, performing checks.", file=sys.stderr)

                try:
                    compile(code_to_save, save_filepath_str, 'exec'); syntax_ok = True
                    print(f"Syntax OK for {check_filename}", file=sys.stderr)
                    if not is_server_script and AUTO_RUN_PYTHON_ON_SYNTAX_OK:
                        print(f"Info: Attempting to run Python script {check_filename} (auto-run enabled).", file=sys.stderr)
                        run_success, logpath = run_script(save_filepath_str, 'python'); log_filename = Path(logpath).name if logpath else None
                        print(f"Info: Python script run completed. Success: {run_success}, Log: {log_filename}", file=sys.stderr)
                    elif not is_server_script: print("Info: Python auto-run disabled.", file=sys.stderr)
                except SyntaxError as e:
                    syntax_ok = False; print(f"Syntax Error: L{e.lineno} C{e.offset} {e.msg}", file=sys.stderr)
                    log_fn_base = Path(save_filepath_str).stem; log_path_err = LOG_FOLDER_PATH / f"{log_fn_base}_py_syntax_error.log"
                    try: log_path_err.write_text(f"Python Syntax Error:\nFile: {check_filename} (Marker: {extracted_filename_raw or 'N/A'})\nLine: {e.lineno}, Offset: {e.offset}\nMsg: {e.msg}\nContext:\n{e.text}", encoding='utf-8'); log_filename = log_path_err.name
                    except Exception as log_e: print(f"E: writing python syntax error log: {log_e}", file=sys.stderr)
                except Exception as compile_e:
                    syntax_ok = False; run_success = False; print(f"Python compile/run setup error: {compile_e}", file=sys.stderr)
                    log_fn_base = Path(save_filepath_str).stem; log_path_err = LOG_FOLDER_PATH / f"{log_fn_base}_py_compile_error.log"
                    try: log_path_err.write_text(f"Python Compile/Run Setup Error:\nFile: {check_filename} (Marker: {extracted_filename_raw or 'N/A'})\nError: {compile_e}\n", encoding='utf-8'); log_filename = log_path_err.name
                    except Exception as log_e: print(f"E: writing python compile error log: {log_e}", file=sys.stderr)

            elif file_extension == '.sh':
                 script_type = 'shell'
                 print(f"Info: File '{check_filename}' is Shell, performing checks.", file=sys.stderr)
                 syntax_ok, syntax_log_path = check_shell_syntax(save_filepath_str)
                 if syntax_log_path: log_filename = Path(syntax_log_path).name

                 if syntax_ok:
                      if AUTO_RUN_SHELL_ON_SYNTAX_OK:
                           print(f"Info: Attempting to run Shell script {check_filename} (auto-run enabled via --shell).", file=sys.stderr)
                           run_success, run_log_path = run_script(save_filepath_str, 'shell')
                           if run_log_path: log_filename = Path(run_log_path).name
                           print(f"Info: Shell script run completed. Success: {run_success}, Log: {log_filename}", file=sys.stderr)
                      else: print("Info: Shell auto-run disabled.", file=sys.stderr)
                 else: # Syntax failed
                      run_success = False
                      print(f"Info: Shell syntax error prevented execution. Log: {log_filename}", file=sys.stderr)

            else: # Not Python or Shell
                print(f"Info: File '{check_filename}' is not Python or Shell, skipping syntax/run checks.", file=sys.stderr)

            # --- 5. Send Response ---
            response_data = {
                'status': 'success',
                'saved_as': final_save_filename, # Report relative path if git/marker, basename if timestamped
                'saved_path': str(Path(save_filepath_str).relative_to(SERVER_DIR)) if save_filepath_str else None,
                'log_file': log_filename,
                'syntax_ok': syntax_ok,
                'run_success': run_success,
                'script_type': script_type,
                'source_file_marker': extracted_filename_raw,
                'git_updated': was_git_updated,
                'save_location': save_target,
                'detected_language': detected_language_name if save_target == 'fallback' and not absolute_path_target else None
            }
            print(f"Sending response: {response_data}", file=sys.stderr)
            print("--- Request complete (Lock released) ---", file=sys.stderr)
            return jsonify(response_data)
        # --- Lock Released ---

    return jsonify({'status': 'error', 'message': f'Unsupported method: {request.method}'}), 405


@app.route('/test_connection', methods=['GET'])
def test_connection():
    """Simple endpoint to check connectivity, returns full status."""
    # Redirects to the main status endpoint logic
    return get_status()

# --- Log Routes ---
@app.route('/logs')
def list_logs():
    """Lists available log files."""
    log_files = []; template = '''<!DOCTYPE html><html><head><title>Logs Browser</title><style>body{font-family:Arial,sans-serif;background:#1e1e1e;color:#d4d4d4;padding:20px}h1{color:#4ec9b0;border-bottom:1px solid #444;padding-bottom:10px}ul{list-style:none;padding:0}li{background:#252526;margin-bottom:8px;border-radius:4px}li a{color:#9cdcfe;text-decoration:none;display:block;padding:10px 15px;transition:background-color .2s ease}li a:hover{background-color:#333}p{color:#888}pre{background:#1e1e1e;border:1px solid #444;padding:15px;border-radius:5px;overflow-x:auto;white-space:pre-wrap;word-wrap:break-word;color:#d4d4d4}</style></head><body><h1>🗂️ Available Logs</h1>{% if logs %}<ul>{% for log in logs %}<li><a href="/logs/{{ log | urlencode }}">{{ log }}</a></li>{% endfor %}</ul>{% else %}<p>No logs found in '{{ log_folder_name }}'.</p>{% endif %}</body></html>'''
    try:
         log_paths = [p for p in LOG_FOLDER_PATH.glob('*.log') if p.is_file()]
         log_paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
         log_files = [p.name for p in log_paths]
    except FileNotFoundError: pass
    except Exception as e: print(f"Error listing logs: {e}", file=sys.stderr)
    return render_template_string(template, logs=log_files, log_folder_name=LOG_FOLDER)

@app.route('/logs/<path:filename>')
def serve_log(filename):
    """Serves a specific log file."""
    # Basic security check
    if '..' in filename or filename.startswith('/'):
         print(f"W: Forbidden log access attempt: {filename}", file=sys.stderr)
         return "Forbidden", 403

    print(f"Request received for log file: {filename}", file=sys.stderr)
    try:
        log_dir = LOG_FOLDER_PATH.resolve()
        requested_path = (log_dir / filename).resolve()
        if not str(requested_path).startswith(str(log_dir)):
             print(f"W: Forbidden log access attempt (resolved outside log dir): {filename}", file=sys.stderr)
             return "Forbidden", 403

        return send_from_directory(
             LOG_FOLDER_PATH, filename, mimetype='text/plain', as_attachment=False
        )
    except FileNotFoundError: return "Log file not found", 404
    except Exception as e: print(f"Error serving log file {filename}: {e}", file=sys.stderr); return "Error serving file", 500


# --- Main Execution ---
if __name__ == '__main__':
    host_ip = '127.0.0.1'; port_num = SERVER_PORT
    print(f"--- AI Code Capture Server ---")
    print(f"Config File: '{CONFIG_FILE}' (exists: {CONFIG_FILE.is_file()})")
    print(f"Starting Flask server on http://{host_ip}:{port_num}")
    print(f"Server CWD (Potential Git Root): {SERVER_DIR}")
    print(f"Saving non-Git files to: {SAVE_FOLDER_PATH.relative_to(SERVER_DIR)}")
    print(f"Saving logs to: {LOG_FOLDER_PATH.relative_to(SERVER_DIR)}")
    if IS_REPO: print("Git integration: ENABLED")
    else: print("Git integration: DISABLED")

    # Print final effective settings
    print(f"Python auto-run: {'ENABLED' if AUTO_RUN_PYTHON_ON_SYNTAX_OK else 'DISABLED'}")
    print(f"Shell auto-run:  {'ENABLED' if AUTO_RUN_SHELL_ON_SYNTAX_OK else 'DISABLED'}{' !!! CAUTION !!!' if AUTO_RUN_SHELL_ON_SYNTAX_OK else ''}")

    print("--- Server ready ---", file=sys.stderr)

    try:
        # Consider using Waitress or Gunicorn for production:
        # from waitress import serve
        # serve(app, host=host_ip, port=port_num)
        app.run(host=host_ip, port=port_num, debug=False)
    except OSError as e:
        if "Address already in use" in str(e) or "WinError" in str(e): # Broader check
            print(f"\nE: Address already in use (Port {port_num}).", file=sys.stderr)
            print(f"   Another program might be running, or use 'python3 {THIS_SCRIPT_NAME} -p <new_port>'", file=sys.stderr)
            sys.exit(1)
        else: print(f"\nE: Failed to start server: {e}", file=sys.stderr); sys.exit(1)
    except KeyboardInterrupt: print("\n--- Server shutting down ---", file=sys.stderr); sys.exit(0)