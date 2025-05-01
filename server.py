# --- START OF FILE server.py ---

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
# --- MODIFIED: Renamed shell flag to --shell ---
parser.add_argument(
    '--shell', action='store_true',
    help='DANGEROUS: Enable automatic execution of detected shell scripts (.sh) if syntax is OK. Disabled by default.'
)
# --- Kept Python flag separate ---
parser.add_argument(
    '--enable-python-run', action='store_true',
    help='Enable automatic execution of Python scripts (.py) if syntax is OK. Disabled by default.'
)
args = parser.parse_args()
SERVER_PORT = args.port
# --- Configuration flags ---
AUTO_RUN_PYTHON_ON_SYNTAX_OK = args.enable_python_run
# --- MODIFIED: Controlled by --shell flag ---
AUTO_RUN_SHELL_ON_SYNTAX_OK = args.shell

# --- Flask App Setup ---
app = Flask(__name__)
CORS(app)

# --- Create a Lock for serializing requests ---
request_lock = threading.Lock()
print("Request lock initialized.", file=sys.stderr)

# --- Configuration & Paths ---
SAVE_FOLDER = 'received_codes'; LOG_FOLDER = 'logs'
SERVER_DIR = Path.cwd().resolve() # Use Current Working Directory as the base
SAVE_FOLDER_PATH = SERVER_DIR / SAVE_FOLDER
LOG_FOLDER_PATH = SERVER_DIR / LOG_FOLDER
THIS_SCRIPT_NAME = Path(__file__).name
os.makedirs(SAVE_FOLDER_PATH, exist_ok=True)
os.makedirs(LOG_FOLDER_PATH, exist_ok=True)

# --- Regex & Constants ---
FILENAME_EXTRACT_REGEX = re.compile(r"^\s*(?://|#)\s*@@FILENAME@@\s+(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
FILENAME_SANITIZE_REGEX = re.compile(r'[^a-zA-Z0-9._\-\/]')
MAX_FILENAME_LENGTH = 200
# --- Language Patterns (unchanged from previous version) ---
LANGUAGE_PATTERNS = {
    '.py': re.compile(r'\b(def|class|import|from|if|else|elif|for|while|try|except|print)\b', re.MULTILINE),
    '.js': re.compile(r'\b(function|var|let|const|if|else|for|while|document|window|console\.log)\b', re.MULTILINE),
    '.html': re.compile(r'<(!DOCTYPE html|html|head|body|div|p|a|img|script|style)\b', re.IGNORECASE | re.MULTILINE),
    '.css': re.compile(r'[{};]\s*([a-zA-Z-]+)\s*:', re.MULTILINE),
    '.json': re.compile(r'^\s*\{.*\}\s*$|^\s*\[.*\]\s*$', re.DOTALL),
    '.md': re.compile(r'^#+\s|\*\*|\*|_|`|> |-', re.MULTILINE),
    '.sql': re.compile(r'\b(SELECT|INSERT|UPDATE|DELETE|CREATE|TABLE|FROM|WHERE|JOIN)\b', re.IGNORECASE | re.MULTILINE),
    '.xml': re.compile(r'<(\?xml|!DOCTYPE|[a-zA-Z:]+)', re.MULTILINE),
    '.sh': re.compile(r'\b(echo|if|then|else|fi|for|do|done|while|case|esac|function|source|export|\$\(|\{|\})\b|^(#!\/bin\/(bash|sh))', re.MULTILINE) # Added shebang check here too
}
DEFAULT_EXTENSION = '.txt';

# --- Helper Functions ---
# (sanitize_filename, detect_language_and_extension, generate_timestamped_filepath remain unchanged)
def sanitize_filename(filename: str) -> str | None:
    if not filename or filename.isspace(): return None
    filename = filename.strip()
    # Basic path traversal and hidden file checks
    if filename.startswith(('/', '\\')) or '..' in Path(filename).parts:
        print(f"W: Rejected potentially unsafe path pattern: {filename}", file=sys.stderr)
        return None
    basename = os.path.basename(filename)
    if basename.startswith('.'): # Reject hidden files/folders at the end
        print(f"W: Rejected path ending in hidden file/folder: {filename}", file=sys.stderr)
        return None

    # Sanitize characters
    sanitized = FILENAME_SANITIZE_REGEX.sub('_', filename)

    # Length check (apply after sanitization)
    if len(sanitized) > MAX_FILENAME_LENGTH:
        print(f"W: Filename too long after sanitization, might be truncated unexpectedly: {sanitized}", file=sys.stderr)
        sanitized = sanitized[:MAX_FILENAME_LENGTH]
        # Try to preserve original extension if truncation removed it
        base, ext = os.path.splitext(sanitized)
        original_base, original_ext = os.path.splitext(filename)
        if original_ext and not ext:
             # Check length again before adding potentially long original extension
             if len(base) + len(original_ext) <= MAX_FILENAME_LENGTH:
                 sanitized = base + original_ext
             # else: keep truncated version without extension (or add default later)

    # Ensure filename part is not empty and has a reasonable extension
    final_path = Path(sanitized)
    base_name_part = final_path.name
    base, ext = os.path.splitext(base_name_part)

    if not base: # Check if the base name (without extension) is empty
        print(f"W: Sanitized filename part is empty: '{sanitized}'. Rejecting.", file=sys.stderr)
        return None
    if not ext or len(ext) < 2: # Check for missing or trivial extension like "."
        print(f"W: Sanitized path '{sanitized}' lacks a proper extension. Appending .txt", file=sys.stderr)
        sanitized += ".txt" # Append default extension

    return sanitized

def detect_language_and_extension(code: str) -> tuple[str, str]:
    first_lines = code.splitlines()[:3]
    if first_lines:
        # Prioritize shebangs
        if first_lines[0].startswith('#!/usr/bin/env python') or first_lines[0].startswith('#!/usr/bin/python'): return '.py', 'Python'
        if first_lines[0].startswith('#!/bin/bash') or first_lines[0].startswith('#!/bin/sh'): return '.sh', 'Shell'
        if first_lines[0].startswith('<?php'): return '.php', 'PHP'
    # Check patterns
    if LANGUAGE_PATTERNS['.html'].search(code): return '.html', 'HTML'
    if LANGUAGE_PATTERNS['.xml'].search(code): return '.xml', 'XML'
    if LANGUAGE_PATTERNS['.json'].search(code):
         try: import json; json.loads(code); return '.json', 'JSON'
         except: pass # Ignore invalid JSON
    if LANGUAGE_PATTERNS['.css'].search(code): return '.css', 'CSS'
    if LANGUAGE_PATTERNS['.py'].search(code): return '.py', 'Python'
    if LANGUAGE_PATTERNS['.sh'].search(code): return '.sh', 'Shell' # Check shell pattern
    if LANGUAGE_PATTERNS['.js'].search(code): return '.js', 'JavaScript'
    if LANGUAGE_PATTERNS['.sql'].search(code): return '.sql', 'SQL'
    if LANGUAGE_PATTERNS['.md'].search(code): return '.md', 'Markdown'
    print("W: Cannot detect language. Defaulting to .txt", file=sys.stderr)
    return DEFAULT_EXTENSION, 'Text'

def generate_timestamped_filepath(extension: str = '.txt', base_prefix="code"):
    today = datetime.datetime.now().strftime("%Y%m%d"); counter = 1
    if not extension.startswith('.'): extension = '.' + extension
    # Sanitize base_prefix just in case
    safe_base_prefix = FILENAME_SANITIZE_REGEX.sub('_', base_prefix).strip('_')
    if not safe_base_prefix: safe_base_prefix = "code" # Ensure not empty

    while True:
        filename = f"{safe_base_prefix}_{today}_{counter:03d}{extension}"
        filepath = SAVE_FOLDER_PATH / filename
        if not filepath.exists():
            # Create parent directory if it doesn't exist (relevant if base_prefix had slashes)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            return str(filepath)
        counter += 1
        if counter > 999: # Avoid infinite loop in unlikely scenario
             print(f"E: Could not generate unique timestamped filename for prefix '{safe_base_prefix}'", file=sys.stderr)
             # Fallback to a more unique name perhaps
             fallback_filename = f"{safe_base_prefix}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{extension}"
             filepath = SAVE_FOLDER_PATH / fallback_filename
             filepath.parent.mkdir(parents=True, exist_ok=True)
             return str(filepath)


# (is_git_repository, find_tracked_file_by_name, is_git_tracked, update_and_commit_file remain unchanged)
def is_git_repository() -> bool:
    try:
        result = subprocess.run(['git', 'rev-parse', '--git-dir'], capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR)
        is_repo = result.returncode == 0
        if not is_repo: print("Info: Not running inside a Git repository.", file=sys.stderr)
        return is_repo
    except FileNotFoundError: print("W: 'git' command not found.", file=sys.stderr); return False
    except Exception as e: print(f"E: checking Git repository: {e}", file=sys.stderr); return False

IS_REPO = is_git_repository()

def find_tracked_file_by_name(basename_to_find: str) -> str | None:
    if not IS_REPO: return None
    try:
        # Use find and git ls-files for potentially better performance/accuracy
        # First, check exact match relative to SERVER_DIR
        exact_path = SERVER_DIR / basename_to_find
        if exact_path.is_file():
             rel_path_str = str(exact_path.relative_to(SERVER_DIR).as_posix())
             if is_git_tracked(rel_path_str):
                  print(f"Info: Found exact tracked file match: '{rel_path_str}'", file=sys.stderr)
                  return rel_path_str

        # If not an exact match relative to root, search using git ls-files
        command = ['git', 'ls-files', f'**/{basename_to_find}']
        print(f"Running: {' '.join(command)} from {SERVER_DIR} to find matches for '*/{basename_to_find}'", file=sys.stderr)
        result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', cwd=SERVER_DIR)
        tracked_files = result.stdout.splitlines()

        # Filter for exact basename match
        matches = [f for f in tracked_files if Path(f).name == basename_to_find]

        if len(matches) == 1:
            print(f"Info: Found unique tracked file match via ls-files: '{matches[0]}'", file=sys.stderr)
            return matches[0]
        elif len(matches) > 1:
            print(f"W: Ambiguous filename marker '{basename_to_find}'. Found multiple tracked files ending in that name: {matches}. Cannot determine target.", file=sys.stderr)
            return None
        else:
            print(f"Info: No tracked file ending in '{basename_to_find}' found in Git index.", file=sys.stderr)
            return None
    except subprocess.CalledProcessError as e:
        # Ignore error if pattern simply doesn't match anything
        if e.returncode == 1 and not e.stdout and not e.stderr:
             print(f"Info: No tracked file ending in '{basename_to_find}' found (git ls-files returned 1).", file=sys.stderr)
        else:
             print(f"E: 'git ls-files' failed:\n{e.stderr}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"E: checking Git for file '{basename_to_find}': {e}", file=sys.stderr)
        return None

def is_git_tracked(filepath_relative_to_repo: str) -> bool:
    if not IS_REPO: return False
    try:
        # Ensure we use posix path for git command
        git_path = Path(filepath_relative_to_repo).as_posix()
        command = ['git', 'ls-files', '--error-unmatch', git_path]
        # print(f"Running: {' '.join(command)} from {SERVER_DIR}", file=sys.stderr) # Less verbose
        # Use check=True and catch CalledProcessError for cleaner logic
        subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', cwd=SERVER_DIR)
        print(f"Info: Git track status for '{git_path}': True (Tracked)", file=sys.stderr)
        return True
    except subprocess.CalledProcessError:
        # This error (returncode 1) specifically means the file is not tracked
        print(f"Info: Git track status for '{git_path}': False (Not tracked or doesn't exist in index)", file=sys.stderr)
        return False
    except Exception as e:
        print(f"E: checking Git track status for '{filepath_relative_to_repo}': {e}", file=sys.stderr)
        return False


def update_and_commit_file(filepath_absolute: Path, code_content: str, marker_filename: str) -> bool:
    if not IS_REPO: return False
    try:
        # Ensure file exists and parent dirs are created before Git operations
        filepath_absolute.parent.mkdir(parents=True, exist_ok=True)

        # Check if content is actually different to avoid empty commits
        current_content = ""
        if filepath_absolute.exists():
             try:
                 current_content = filepath_absolute.read_text(encoding='utf-8')
             except Exception as read_e:
                 print(f"W: Could not read existing file {filepath_absolute} to check for changes: {read_e}", file=sys.stderr)
                 # Proceed with overwrite anyway

        if code_content == current_content:
             print(f"Info: Content for '{filepath_absolute.relative_to(SERVER_DIR)}' has not changed. Skipping Git commit.", file=sys.stderr)
             return True # Treat as success, no action needed

        # Content is different, proceed with write and commit
        print(f"Overwriting local file: {filepath_absolute.relative_to(SERVER_DIR)}", file=sys.stderr)
        filepath_absolute.write_text(code_content, encoding='utf-8')

        # Use relative posix path for Git commands
        git_path_posix = filepath_absolute.relative_to(SERVER_DIR).as_posix()

        print(f"Running: git add '{git_path_posix}' from {SERVER_DIR}", file=sys.stderr)
        add_result = subprocess.run(['git', 'add', git_path_posix], capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR)
        if add_result.returncode != 0:
            print(f"E: 'git add' failed for {git_path_posix}:\n{add_result.stderr}", file=sys.stderr)
            return False

        commit_message = f"Update {marker_filename} from AI Code Capture"
        print(f"Running: git commit -m \"{commit_message}\" from {SERVER_DIR}", file=sys.stderr)
        # Commit only the specific file added
        commit_result = subprocess.run(['git', 'commit', git_path_posix, '-m', commit_message], capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR)

        # Check commit success more robustly
        if commit_result.returncode == 0:
             print(f"Successfully committed changes for {git_path_posix}.", file=sys.stderr)
             return True
        else:
             # Check common "nothing to commit" messages
             no_changes_patterns = ["nothing to commit", "no changes added to commit", "nothing added to commit"]
             commit_output = commit_result.stdout + commit_result.stderr
             if any(pattern in commit_output for pattern in no_changes_patterns):
                 print(f"Info: No effective changes detected by Git for commit on {git_path_posix}.", file=sys.stderr)
                 return True # No changes is not a failure
             else:
                 print(f"E: 'git commit' failed for {git_path_posix}:\n{commit_output}", file=sys.stderr)
                 # Attempt to reset the added file if commit fails? Maybe too complex.
                 return False

    except IOError as e: print(f"E: writing file {filepath_absolute}: {e}", file=sys.stderr); return False
    except Exception as e: print(f"E: during Git update/commit for {filepath_absolute}: {e}", file=sys.stderr); return False

# --- run_script and check_shell_syntax remain unchanged from previous version ---
def run_script(filepath: str, script_type: str):
    filepath_obj = Path(filepath)
    filename_base = filepath_obj.stem
    logpath = LOG_FOLDER_PATH / f"{filename_base}_{script_type}_run.log" # More specific log name
    run_cwd = filepath_obj.parent
    os.makedirs(LOG_FOLDER_PATH, exist_ok=True)

    command = []
    if script_type == 'python':
        python_exe = sys.executable
        command = [python_exe, filepath_obj.name]
        print(f"Executing Python: {' '.join(command)} in {run_cwd}", file=sys.stderr)
    elif script_type == 'shell':
        command = ['bash', filepath_obj.name] # Defaulting to bash
        print(f"Executing Shell: {' '.join(command)} in {run_cwd}", file=sys.stderr)
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
        with open(logpath, 'w', encoding='utf-8') as f:
            f.write(f"Error: Script timed out after 15 seconds.\nCommand: {' '.join(command)}\n")
        return False, str(logpath)
    except FileNotFoundError:
         print(f"E: Interpreter or script not found for command: {' '.join(command)}", file=sys.stderr)
         with open(logpath, 'w', encoding='utf-8') as f:
            f.write(f"Error: Interpreter or script not found.\nCommand: {' '.join(command)}\n")
         return False, str(logpath)
    except Exception as e:
        print(f"E: running script {filepath}: {e}", file=sys.stderr)
        with open(logpath, 'w', encoding='utf-8') as f:
            f.write(f"Error running script: {str(e)}\nCommand: {' '.join(command)}\n")
        return False, str(logpath)

def check_shell_syntax(filepath: str) -> tuple[bool, str | None]:
    filepath_obj = Path(filepath)
    filename_base = filepath_obj.stem
    logpath = LOG_FOLDER_PATH / f"{filename_base}_shell_syntax.log"
    os.makedirs(LOG_FOLDER_PATH, exist_ok=True)
    command = ['bash', '-n', str(filepath_obj)] # Using bash -n for basic check

    print(f"Checking Shell syntax: {' '.join(command)}", file=sys.stderr)
    try:
        # Use absolute path for the command to avoid cwd issues if filepath is relative
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, encoding='utf-8', check=False)
        syntax_ok = result.returncode == 0

        # Log output regardless of success, as 'bash -n' might produce no output on success
        # but shellcheck might produce warnings. Keep logs consistent.
        with open(logpath, 'w', encoding='utf-8') as f:
             f.write(f"--- COMMAND ---\n{' '.join(command)}\n")
             if not syntax_ok:
                 f.write(f"--- SYNTAX ERROR --- (RC: {result.returncode})\n")
             else:
                 f.write(f"--- SYNTAX OK --- (RC: {result.returncode})\n")
             f.write(f"--- STDOUT ---\n{result.stdout}\n")
             f.write(f"--- STDERR ---\n{result.stderr}\n") # Errors usually on stderr

        if syntax_ok:
            print(f"Shell syntax OK for {filepath_obj.name}", file=sys.stderr)
            return True, str(logpath) # Return log path even if OK
        else:
            print(f"Shell syntax Error for {filepath_obj.name}. RC: {result.returncode}. Log: {logpath.name}", file=sys.stderr)
            return False, str(logpath)
    except FileNotFoundError:
         print(f"E: Syntax check command not found: '{command[0]}'", file=sys.stderr)
         with open(logpath, 'w', encoding='utf-8') as f:
             f.write(f"Error: Syntax check command ('{command[0]}') not found.\n")
         return False, str(logpath) # Can't check syntax
    except subprocess.TimeoutExpired:
        print(f"E: Shell syntax check timed out: {filepath}", file=sys.stderr)
        with open(logpath, 'w', encoding='utf-8') as f:
            f.write("Error: Shell syntax check timed out after 10 seconds.\n")
        return False, str(logpath)
    except Exception as e:
        print(f"E: checking shell syntax for {filepath}: {e}", file=sys.stderr)
        with open(logpath, 'w', encoding='utf-8') as f:
            f.write(f"Error during shell syntax check: {str(e)}\n")
        return False, str(logpath)


# --- Route Definitions ---
@app.route('/submit_code', methods=['POST', 'OPTIONS'])
def submit_code():
    if request.method == 'OPTIONS': return '', 204 # Handle CORS preflight
    if request.method == 'POST':
        with request_lock: # Ensure only one request handles files/git at a time
            print("--- Handling /submit_code request (Lock acquired) ---", file=sys.stderr)
            data = request.get_json()
            if not data:
                print("E: No JSON data received.", file=sys.stderr)
                return jsonify({'status': 'error', 'message': 'No JSON data received'}), 400
            received_code = data.get('code', '')
            if not received_code or received_code.isspace():
                print("E: Empty code received.", file=sys.stderr)
                return jsonify({'status': 'error', 'message': 'Empty code received'}), 400

            # --- Variable Initialization ---
            save_filepath_str = None          # Absolute path where the file was saved
            final_save_filename = None        # Filename (potentially relative path) as saved/committed
            code_to_save = received_code      # The actual code content to write to disk
            extracted_filename_raw = None     # Raw filename from @@FILENAME@@ marker
            detected_language_name = "Unknown" # Detected language if no marker/Git
            marker_line_length = 0            # Length of the marker line(s) to strip for Git commit
            was_git_updated = False           # Flag if Git commit was successful
            sanitized_path_from_marker = None # Validated/sanitized relative path from marker
            save_target = "fallback"          # Where the code ended up: 'git' or 'fallback'
            absolute_path_target = None       # Resolved absolute path for saving

            # --- 1. Check for @@FILENAME@@ Marker ---
            match = FILENAME_EXTRACT_REGEX.search(received_code)
            if match:
                extracted_filename_raw = match.group(1).strip()
                # Calculate length to potentially strip marker line(s) later
                marker_line_length = match.end()
                if marker_line_length < len(received_code) and received_code[marker_line_length] == '\n':
                    marker_line_length += 1
                print(f"Info: Found @@FILENAME@@ marker: '{extracted_filename_raw}'", file=sys.stderr)
                sanitized_path_from_marker = sanitize_filename(extracted_filename_raw)

                if sanitized_path_from_marker:
                    print(f"Info: Sanitized relative path from marker: '{sanitized_path_from_marker}'", file=sys.stderr)
                    # --- 2. Attempt Git Integration (if marker valid and repo exists) ---
                    if IS_REPO:
                        git_path_to_check = sanitized_path_from_marker
                        # If marker is just a basename, try to find the unique tracked file
                        if '/' not in sanitized_path_from_marker.replace('\\', '/'):
                            print(f"Info: Marker is basename only ('{sanitized_path_from_marker}'). Searching Git index...", file=sys.stderr)
                            found_rel_path = find_tracked_file_by_name(sanitized_path_from_marker)
                            if found_rel_path:
                                git_path_to_check = found_rel_path # Use the found full relative path
                            else:
                                print(f"Info: No unique tracked file for basename '{sanitized_path_from_marker}'. Will treat as new/untracked file.", file=sys.stderr)
                                git_path_to_check = sanitized_path_from_marker # Keep original sanitized name

                        # Resolve the potential target path relative to server dir
                        absolute_path_target = (SERVER_DIR / git_path_to_check).resolve()

                        # Security check: Ensure resolved path is still within server directory
                        if not str(absolute_path_target).startswith(str(SERVER_DIR)):
                            print(f"W: Resolved path '{absolute_path_target}' is outside server dir ({SERVER_DIR}). Blocking Git operation, will use fallback save.", file=sys.stderr)
                            absolute_path_target = None # Prevent Git use
                        else:
                            # Check if this specific relative path is tracked by Git
                            is_tracked = is_git_tracked(git_path_to_check)
                            if is_tracked:
                                print(f"Info: Target file '{git_path_to_check}' is tracked by Git. Attempting update and commit.", file=sys.stderr)
                                code_to_save = received_code[marker_line_length:] # Use code *after* marker line for commit
                                commit_success = update_and_commit_file(absolute_path_target, code_to_save, git_path_to_check) # Use relative path in commit msg
                                if commit_success:
                                    save_filepath_str = str(absolute_path_target)
                                    final_save_filename = git_path_to_check # Store the relative path used
                                    was_git_updated = True
                                    save_target = "git"
                                    print(f"Success: Git update/commit successful for {git_path_to_check}.", file=sys.stderr)
                                else:
                                    print(f"W: Git commit failed for {git_path_to_check}. Will save to fallback location.", file=sys.stderr)
                                    # Keep marker info for fallback name, revert code_to_save
                                    code_to_save = received_code
                                    absolute_path_target = None # Force fallback path generation
                            else:
                                # Path is valid, inside repo, but not tracked by Git yet
                                print(f"Info: Path '{git_path_to_check}' is valid but not tracked by Git. Will save to this path in working dir (no commit).", file=sys.stderr)
                                # We will save to this specific path, but won't commit
                                code_to_save = received_code # Save full code including marker
                                # Keep absolute_path_target, it's where we'll save in fallback
                    else: # Not a Git repo
                         print(f"Info: Not a Git repository. Will save using marker path '{sanitized_path_from_marker}' in fallback location.", file=sys.stderr)
                         absolute_path_target = (SAVE_FOLDER_PATH / sanitized_path_from_marker).resolve()
                         # Security check for non-git save too
                         if not str(absolute_path_target).startswith(str(SAVE_FOLDER_PATH)):
                              print(f"W: Resolved fallback path '{absolute_path_target}' is outside save folder ({SAVE_FOLDER_PATH}). Using default timestamped name.", file=sys.stderr)
                              absolute_path_target = None
                         else:
                              code_to_save = received_code # Save full code
                else: # Marker found but filename was invalid after sanitization
                    print(f"W: Invalid filename extracted from marker: '{extracted_filename_raw}'. Using fallback save.", file=sys.stderr)
                    # absolute_path_target remains None
            else: # No marker found
                 print("Info: No @@FILENAME@@ marker found. Using fallback save.", file=sys.stderr)
                 # absolute_path_target remains None

            # --- 3. Fallback Saving Logic (if Git not used, failed, or no marker) ---
            if save_target == "fallback":
                if absolute_path_target:
                     # Use the path determined from marker (e.g., untracked file, or non-git repo save)
                     save_filepath_str = str(absolute_path_target)
                     final_save_filename = Path(save_filepath_str).name # Use base name for reporting
                     # Try to determine language from extension
                     ext = Path(save_filepath_str).suffix.lower()
                     if ext == '.py': detected_language_name = "Python"
                     elif ext == '.sh': detected_language_name = "Shell"
                     elif ext == '.js': detected_language_name = "JavaScript"
                     # ... other common extensions ...
                     else: detected_language_name = "From Marker Path"
                else:
                     # Generate a timestamped filename
                     base_name_for_fallback = "code"; ext_for_fallback = DEFAULT_EXTENSION
                     # Use marker info for naming if available but path wasn't used
                     if sanitized_path_from_marker:
                         p = Path(sanitized_path_from_marker)
                         base_name_for_fallback = p.stem if p.stem else "code"
                         ext_for_fallback = p.suffix if p.suffix else DEFAULT_EXTENSION
                         detected_language_name = "From Marker (Invalid Path)"
                     else:
                         # Detect language if no marker at all
                         detected_ext, detected_language_name = detect_language_and_extension(code_to_save)
                         ext_for_fallback = detected_ext

                     # Refine base name based on detected language
                     if detected_language_name not in ["Unknown", "Text", "From Marker (Invalid Path)", "From Marker Path"]:
                          base_name_for_fallback = detected_language_name.lower().replace(" ", "_")

                     save_filepath_str = generate_timestamped_filepath(extension=ext_for_fallback, base_prefix=base_name_for_fallback)
                     final_save_filename = Path(save_filepath_str).name # Use base name for reporting

                # Perform the save operation for fallback
                print(f"Info: Saving fallback file to: '{save_filepath_str}'", file=sys.stderr)
                try:
                    save_path_obj = Path(save_filepath_str)
                    save_path_obj.parent.mkdir(parents=True, exist_ok=True) # Ensure directory exists
                    save_path_obj.write_text(code_to_save, encoding='utf-8')
                    print(f"Success: Code saved successfully to {save_filepath_str}", file=sys.stderr)
                except Exception as e:
                    print(f"E: Failed to save fallback file '{save_filepath_str}': {str(e)}", file=sys.stderr)
                    # Critical error, cannot proceed with checks
                    return jsonify({'status': 'error', 'message': f'Failed to save file: {str(e)}'}), 500

            # --- 4. Syntax Check & Optional Execution ---
            syntax_ok = None; run_success = None; log_filename = None
            script_type = None # 'python' or 'shell'

            # Ensure we have a valid saved path string before proceeding
            if not save_filepath_str:
                 print("E: Internal error - save_filepath_str is not set before checks.", file=sys.stderr)
                 return jsonify({'status': 'error', 'message': 'Internal server error saving file path.'}), 500

            file_extension = Path(final_save_filename).suffix.lower()

            # --- Python Check ---
            if file_extension == '.py':
                script_type = 'python'
                # Avoid running the server script itself unless explicitly forced (though flag is safer)
                if Path(save_filepath_str).resolve() == (SERVER_DIR / THIS_SCRIPT_NAME).resolve():
                    print(f"Info: Skipping run checks for server script itself: '{final_save_filename}'. Checking syntax only.", file=sys.stderr)
                    try:
                        compile(code_to_save, save_filepath_str, 'exec')
                        syntax_ok = True
                        print(f"Syntax OK for {final_save_filename}", file=sys.stderr)
                    except SyntaxError as e:
                        syntax_ok = False
                        print(f"Syntax Error in server script: L{e.lineno} C{e.offset} {e.msg}", file=sys.stderr)
                        # Log syntax error (simplified logging)
                        log_fn_base = Path(save_filepath_str).stem
                        log_path_err = LOG_FOLDER_PATH / f"{log_fn_base}_py_syntax_error.log"
                        try: log_path_err.write_text(f"Syntax Error (Server Script):\nLine: {e.lineno}, Offset: {e.offset}\nMsg: {e.msg}\nContext:\n{e.text}", encoding='utf-8'); log_filename = log_path_err.name
                        except Exception as log_e: print(f"E: writing syntax error log: {log_e}", file=sys.stderr)
                    except Exception as compile_e:
                         syntax_ok = False; print(f"Compile check error for server script: {compile_e}", file=sys.stderr)

                else: # Standard Python file check
                    print(f"Info: File '{final_save_filename}' is Python, performing checks.", file=sys.stderr)
                    try:
                        compile(code_to_save, save_filepath_str, 'exec')
                        syntax_ok = True
                        print(f"Syntax OK for {final_save_filename}", file=sys.stderr)
                        if AUTO_RUN_PYTHON_ON_SYNTAX_OK:
                            print(f"Info: Attempting to run Python script {final_save_filename} (auto-run enabled).", file=sys.stderr)
                            run_success, logpath = run_script(save_filepath_str, 'python')
                            log_filename = Path(logpath).name if logpath else None # run_script creates log
                            print(f"Info: Python script run completed. Success: {run_success}, Log: {log_filename}", file=sys.stderr)
                        else:
                             print("Info: Python auto-run disabled.", file=sys.stderr)

                    except SyntaxError as e:
                        syntax_ok = False; print(f"Syntax Error: L{e.lineno} C{e.offset} {e.msg}", file=sys.stderr)
                        log_fn_base = Path(save_filepath_str).stem; log_path_err = LOG_FOLDER_PATH / f"{log_fn_base}_py_syntax_error.log"
                        try: log_path_err.write_text(f"Python Syntax Error:\nFile: {final_save_filename} (Marker: {extracted_filename_raw or 'N/A'})\nLine: {e.lineno}, Offset: {e.offset}\nMsg: {e.msg}\nContext:\n{e.text}", encoding='utf-8'); log_filename = log_path_err.name
                        except Exception as log_e: print(f"E: writing python syntax error log: {log_e}", file=sys.stderr)
                    except Exception as compile_e:
                        syntax_ok = False; run_success = False; print(f"Python compile/run setup error: {compile_e}", file=sys.stderr)
                        log_fn_base = Path(save_filepath_str).stem; log_path_err = LOG_FOLDER_PATH / f"{log_fn_base}_py_compile_error.log"
                        try: log_path_err.write_text(f"Python Compile/Run Setup Error:\nFile: {final_save_filename} (Marker: {extracted_filename_raw or 'N/A'})\nError: {compile_e}\n", encoding='utf-8'); log_filename = log_path_err.name
                        except Exception as log_e: print(f"E: writing python compile error log: {log_e}", file=sys.stderr)

            # --- Shell Check ---
            elif file_extension == '.sh':
                 script_type = 'shell'
                 print(f"Info: File '{final_save_filename}' is Shell, performing checks.", file=sys.stderr)
                 syntax_ok, syntax_log_path = check_shell_syntax(save_filepath_str)
                 if syntax_log_path: log_filename = Path(syntax_log_path).name # Log created by check_shell_syntax

                 if syntax_ok:
                      if AUTO_RUN_SHELL_ON_SYNTAX_OK:
                           print(f"Info: Attempting to run Shell script {final_save_filename} (auto-run enabled via --shell).", file=sys.stderr)
                           run_success, run_log_path = run_script(save_filepath_str, 'shell')
                           # Prefer run log if execution happened
                           if run_log_path: log_filename = Path(run_log_path).name
                           print(f"Info: Shell script run completed. Success: {run_success}, Log: {log_filename}", file=sys.stderr)
                      else:
                           print("Info: Shell auto-run disabled.", file=sys.stderr)
                 else: # Syntax failed
                      run_success = False # Cannot run if syntax is bad
                      print(f"Info: Shell syntax error prevented execution. Log: {log_filename}", file=sys.stderr)

            else: # Not Python or Shell
                print(f"Info: File '{final_save_filename}' is not Python or Shell, skipping syntax/run checks.", file=sys.stderr)
                # detected_language_name might be set from fallback logic

            # --- 5. Send Response ---
            response_data = {
                'status': 'success',
                'saved_as': final_save_filename, # The final filename (basename or relative path if Git)
                'saved_path': str(Path(save_filepath_str).relative_to(SERVER_DIR)) if save_filepath_str else None, # Path relative to server root
                'log_file': log_filename, # Name of the log file created, if any
                'syntax_ok': syntax_ok, # True, False, or None
                'run_success': run_success, # True, False, or None
                'script_type': script_type, # 'python', 'shell', or None
                'source_file_marker': extracted_filename_raw, # The raw marker text
                'git_updated': was_git_updated, # Boolean if Git commit happened
                'save_location': save_target, # 'git' or 'fallback'
                'detected_language': detected_language_name if save_target == 'fallback' and not absolute_path_target else None # Language if auto-detected
            }
            print(f"Sending response: {response_data}", file=sys.stderr)
            print("--- Request complete (Lock released) ---", file=sys.stderr)
            return jsonify(response_data)
        # --- Lock Released ---

    # Fallthrough for unsupported methods
    return jsonify({'status': 'error', 'message': f'Unsupported method: {request.method}'}), 405

# --- Test Connection Route (Unchanged) ---
@app.route('/test_connection', methods=['GET'])
def test_connection():
    print("Received /test_connection request", file=sys.stderr)
    try:
        cwd = str(SERVER_DIR)
        return jsonify({'status': 'ok', 'message': 'Server is running.', 'working_directory': cwd})
    except Exception as e:
        print(f"Error getting working directory for test connection: {e}", file=sys.stderr)
        return jsonify({'status': 'error', 'message': f'Server error: {str(e)}'}), 500

# --- Log Routes (Unchanged) ---
@app.route('/logs')
def list_logs():
    log_files = []; template = '''<!DOCTYPE html><html><head><title>Logs Browser</title><style>body{font-family:Arial,sans-serif;background:#1e1e1e;color:#d4d4d4;padding:20px}h1{color:#4ec9b0;border-bottom:1px solid #444;padding-bottom:10px}ul{list-style:none;padding:0}li{background:#252526;margin-bottom:8px;border-radius:4px}li a{color:#9cdcfe;text-decoration:none;display:block;padding:10px 15px;transition:background-color .2s ease}li a:hover{background-color:#333}p{color:#888}pre{background:#1e1e1e;border:1px solid #444;padding:15px;border-radius:5px;overflow-x:auto;white-space:pre-wrap;word-wrap:break-word;color:#d4d4d4}</style></head><body><h1>🗂️ Available Logs</h1>{% if logs %}<ul>{% for log in logs %}<li><a href="/logs/{{ log | urlencode }}">{{ log }}</a></li>{% endfor %}</ul>{% else %}<p>No logs found in '{{ log_folder_name }}'.</p>{% endif %}</body></html>'''
    try:
         # Use Pathlib for listing and sorting
         log_paths = [p for p in LOG_FOLDER_PATH.glob('*.log') if p.is_file()]
         # Sort by modification time, newest first
         log_paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
         log_files = [p.name for p in log_paths]
    except FileNotFoundError: # Log folder might not exist yet
         pass
    except Exception as e: print(f"Error listing logs: {e}", file=sys.stderr)
    return render_template_string(template, logs=log_files, log_folder_name=LOG_FOLDER)

@app.route('/logs/<path:filename>')
def serve_log(filename):
    # Security: Sanitize filename before using it with send_from_directory
    # Basic check: prevent directory traversal and absolute paths
    if '..' in filename or filename.startswith('/'):
         print(f"W: Forbidden log access attempt: {filename}", file=sys.stderr)
         return "Forbidden", 403

    print(f"Request received for log file: {filename}", file=sys.stderr)
    # Let send_from_directory handle path construction and security below log_dir
    try:
        # Resolve to ensure it's within the intended directory (send_from_directory does this too, but belt-and-suspenders)
        log_dir = LOG_FOLDER_PATH.resolve()
        requested_path = (log_dir / filename).resolve()
        if not str(requested_path).startswith(str(log_dir)):
             print(f"W: Forbidden log access attempt (resolved outside log dir): {filename}", file=sys.stderr)
             return "Forbidden", 403

        return send_from_directory(
             LOG_FOLDER_PATH,
             filename,
             mimetype='text/plain',
             as_attachment=False # Display in browser
        )
    except FileNotFoundError:
        return "Log file not found", 404
    except Exception as e:
        print(f"Error serving log file {filename}: {e}", file=sys.stderr)
        return "Error serving file", 500

# --- Main Execution ---
if __name__ == '__main__':
    host_ip = '127.0.0.1'; port_num = SERVER_PORT
    print(f"Starting Flask server on http://{host_ip}:{port_num}", file=sys.stderr)
    print(f"Server CWD (Potential Git Root): {SERVER_DIR}", file=sys.stderr)
    print(f"Saving non-Git files to: {SAVE_FOLDER_PATH}", file=sys.stderr)
    print(f"Saving logs to: {LOG_FOLDER_PATH}", file=sys.stderr)
    print(f"Server script name: {THIS_SCRIPT_NAME}", file=sys.stderr)
    print("Will use filename from '@@FILENAME@@' marker if present and valid.", file=sys.stderr)
    if IS_REPO: print("Git integration: ENABLED (Running in a Git repository).")
    else: print("Git integration: DISABLED (Not in a Git repo or git command failed).")
    print("Will attempt language detection for fallback filename extensions.", file=sys.stderr)

    # --- MODIFIED: Startup messages reflect flags ---
    if AUTO_RUN_PYTHON_ON_SYNTAX_OK:
        print("Python auto-run: ENABLED (--enable-python-run specified).")
    else:
        print("Python auto-run: DISABLED (Use --enable-python-run to enable).")

    if AUTO_RUN_SHELL_ON_SYNTAX_OK:
        print("Shell auto-run:  ENABLED (--shell specified). !!! USE WITH EXTREME CAUTION !!!")
    else:
        print("Shell auto-run:  DISABLED (Use --shell to enable).")

    print("*** CORS enabled for all origins (ensure firewall allows access if needed) ***", file=sys.stderr)
    print("--- Server ready and waiting for requests ---", file=sys.stderr)

    try:
        # Use waitress or another production-ready WSGI server for better performance/security
        # from waitress import serve
        # serve(app, host=host_ip, port=port_num)
        # Using Flask's development server for simplicity here:
        app.run(host=host_ip, port=port_num, debug=False)
    except OSError as e:
        if "Address already in use" in str(e) or "WinError 10048" in str(e):
            print(f"\nE: Address already in use.\nPort {port_num} is likely in use by another program.", file=sys.stderr)
            print(f"Stop the other program or start this server with a different port using: python3 {THIS_SCRIPT_NAME} -p {port_num + 1}\n", file=sys.stderr)
            sys.exit(1)
        else:
             print(f"\nE: Failed to start server: {e}", file=sys.stderr)
             sys.exit(1)
    except KeyboardInterrupt:
         print("\n--- Server shutting down (Ctrl+C received) ---", file=sys.stderr)
         sys.exit(0)

# --- END OF FILE server.py ---