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
# Note: store_true defaults to False if not present, so we compare with the action's default value implicitly
# Default value for action='store_true' is False.
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
# Handle potential __file__ issues when run directly vs imported/packaged
try:
    THIS_SCRIPT_NAME = Path(__file__).name
except NameError:
    THIS_SCRIPT_NAME = "server.py" # Fallback name

os.makedirs(SAVE_FOLDER_PATH, exist_ok=True)
os.makedirs(LOG_FOLDER_PATH, exist_ok=True)

FILENAME_EXTRACT_REGEX = re.compile(r"^\s*(?://|#)\s*@@FILENAME@@\s+(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
# Relaxed regex: Allows word chars (letters, numbers, underscore), dot, dash, slash.
# Prevents sequences of disallowed chars becoming multiple underscores.
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
# >>> HELPER FUNCTIONS <<<
# =====================================================

def sanitize_filename(filename: str) -> str | None:
    """Sanitizes a filename or relative path."""
    if not filename or filename.isspace(): return None
    filename = filename.strip()

    # Prevent directory traversal or absolute paths explicitly
    if filename.startswith(('/', '\\')) or '..' in Path(filename).parts:
        print(f"W: Rejected potentially unsafe path pattern: {filename}", file=sys.stderr)
        return None
    # Prevent hidden files/folders at the end of the path
    if Path(filename).name.startswith('.'):
        print(f"W: Rejected path ending in hidden file/directory: {filename}", file=sys.stderr)
        return None

    # Normalize separators and split
    filename = filename.replace('\\', '/')
    parts = filename.split('/')
    sanitized_parts = []

    for part in parts:
        # Replace disallowed characters with underscore
        sanitized_part = FILENAME_SANITIZE_REGEX.sub('_', part)
        # Remove leading/trailing underscores that might result from replacement
        sanitized_part = sanitized_part.strip('_')
        # If a part becomes empty after sanitization (e.g., "???" -> "_"), reject the whole path
        if not sanitized_part:
            print(f"W: Path segment became empty after sanitization in '{filename}'. Rejecting.", file=sys.stderr)
            return None
        sanitized_parts.append(sanitized_part)

    sanitized = '/'.join(sanitized_parts)

    # Length check
    if len(sanitized) > MAX_FILENAME_LENGTH:
        print(f"W: Sanitized path too long ('{sanitized}'), might be truncated unexpectedly.", file=sys.stderr)
        base, ext = os.path.splitext(sanitized)
        original_ext = Path(filename).suffix # Use original for accurate length calc
        max_base_len = MAX_FILENAME_LENGTH - len(original_ext if original_ext else '')
        if max_base_len < 1:
             print(f"W: Path too long even for extension. Hard truncating.", file=sys.stderr)
             sanitized = sanitized[:MAX_FILENAME_LENGTH]
        else:
             # Truncate base, keep original (or sanitized if original was empty) extension
             sanitized = base[:max_base_len] + (original_ext if original_ext else '')

    # Final safety checks on the result
    final_path = Path(sanitized)
    # Ensure filename part is not empty or just '.' or '..' (though '..' should be caught earlier)
    if not final_path.name or final_path.name.startswith('.'):
         print(f"W: Final sanitized path has empty or hidden basename: '{sanitized}'. Rejecting.", file=sys.stderr)
         return None
    # Ensure there's a reasonable extension, otherwise default
    if not final_path.suffix or len(final_path.suffix) < 2: # Check for at least '.' + one char
        print(f"W: Sanitized path '{sanitized}' lacks a proper extension. Appending {DEFAULT_EXTENSION}", file=sys.stderr)
        sanitized += DEFAULT_EXTENSION

    return sanitized


def detect_language_and_extension(code: str) -> tuple[str, str]:
    """Detects language and returns (extension, language_name)."""
    # Check shebang lines first
    first_lines = code.splitlines()[:3] # Check first few lines
    if first_lines:
        first_line = first_lines[0].strip()
        if first_line.startswith('#!/usr/bin/env python') or first_line.startswith('#!/usr/bin/python'): return '.py', 'Python'
        if first_line.startswith('#!/bin/bash') or first_line.startswith('#!/bin/sh'): return '.sh', 'Shell'
        if first_line.startswith('<?php'): return '.php', 'PHP'
        # Add more shebang checks if needed

    # Simple heuristic checks based on keywords/syntax (order might matter)
    if LANGUAGE_PATTERNS['.html'].search(code): return '.html', 'HTML'
    if LANGUAGE_PATTERNS['.xml'].search(code): return '.xml', 'XML'
    # Validate JSON before declaring it
    if LANGUAGE_PATTERNS['.json'].search(code):
         try:
             import json # Local import might be slightly safer if module not always needed
             json.loads(code)
             return '.json', 'JSON'
         except json.JSONDecodeError:
             pass # It looked like JSON, but wasn't valid. Continue checks.
    if LANGUAGE_PATTERNS['.css'].search(code): return '.css', 'CSS'
    if LANGUAGE_PATTERNS['.py'].search(code): return '.py', 'Python'
    if LANGUAGE_PATTERNS['.sh'].search(code): return '.sh', 'Shell' # Check shell pattern after others
    if LANGUAGE_PATTERNS['.js'].search(code): return '.js', 'JavaScript'
    if LANGUAGE_PATTERNS['.sql'].search(code): return '.sql', 'SQL'
    if LANGUAGE_PATTERNS['.md'].search(code): return '.md', 'Markdown'

    # Fallback
    print("W: Cannot detect language. Defaulting to .txt", file=sys.stderr)
    return DEFAULT_EXTENSION, 'Text'

def generate_timestamped_filepath(extension: str = '.txt', base_prefix="code"):
    """Generates a unique timestamped filepath in SAVE_FOLDER_PATH."""
    today = datetime.datetime.now().strftime("%Y%m%d")
    counter = 1
    # Ensure extension starts with a dot
    if not extension.startswith('.'): extension = '.' + extension
    # Sanitize base prefix (allow only letters, numbers, underscore, hyphen)
    safe_base_prefix = re.sub(r'[^a-zA-Z0-9_\-]', '_', base_prefix).strip('_')
    if not safe_base_prefix: safe_base_prefix = "code" # Ensure prefix isn't empty

    while True:
        filename = f"{safe_base_prefix}_{today}_{counter:03d}{extension}"
        filepath = SAVE_FOLDER_PATH / filename
        if not filepath.exists():
            # Return the absolute path as a string
            return str(filepath.resolve()) # Use resolve() for consistency
        counter += 1
        # Prevent potential infinite loop if >999 files exist for the day/prefix
        if counter > 999:
             print(f"W: Could not find unique filename for prefix '{safe_base_prefix}' after 999 attempts. Adding timestamp.", file=sys.stderr)
             # Use a more unique timestamp including time and microseconds
             fallback_filename = f"{safe_base_prefix}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{extension}"
             return str((SAVE_FOLDER_PATH / fallback_filename).resolve())

def is_git_repository() -> bool:
    """Checks if SERVER_DIR is a Git repository."""
    try:
        # Use --is-inside-work-tree for a more direct check
        result = subprocess.run(['git', 'rev-parse', '--is-inside-work-tree'], capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR, timeout=5)
        # It prints 'true' or 'false' to stdout on success
        is_repo = result.returncode == 0 and result.stdout.strip() == 'true'
        if result.returncode != 0 and result.stderr:
             # Only log unexpected git errors, not "not a git repository" which is common
             if 'not a git repository' not in result.stderr.lower():
                  print(f"W: Git check failed: {result.stderr.strip()}", file=sys.stderr)
        elif not is_repo and result.returncode == 0:
             print("Info: Not running inside a Git work tree.", file=sys.stderr)
        return is_repo
    except FileNotFoundError:
        print("W: 'git' command not found. Cannot use Git features.", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print("W: Git check command timed out.", file=sys.stderr)
        return False
    except Exception as e:
        print(f"E: Error checking Git repository status: {e}", file=sys.stderr)
        return False

IS_REPO = is_git_repository() # Define global after function definition

def find_tracked_file_by_name(basename_to_find: str) -> str | None:
    """Finds a unique tracked file by its basename within the repo."""
    if not IS_REPO: return None
    try:
        # Use glob pattern directly with ls-files
        # Need to be careful with shell metacharacters in basename_to_find, though Path().name usually avoids them
        # Using f-string is generally safe here as basename_to_find comes from sanitized input or Path().name
        command = ['git', 'ls-files', f'**/{basename_to_find}']
        # print(f"Running: {' '.join(command)} from {SERVER_DIR} to find matches for '*/{basename_to_find}'", file=sys.stderr) # Debugging
        result = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR, timeout=5)

        if result.returncode != 0:
             # RC 1 usually means no files found, which is okay. Check stderr for actual errors.
             if result.stderr and result.returncode != 1:
                  print(f"E: 'git ls-files' failed (RC={result.returncode}):\n{result.stderr.strip()}", file=sys.stderr)
             #else: # No match found or expected RC 1 if no match
             #    print(f"Info: 'git ls-files' found no matches for pattern '*/{basename_to_find}'.", file=sys.stderr)
             return None

        tracked_files = result.stdout.strip().splitlines()
        # Ensure we only match the exact basename
        matches = [f for f in tracked_files if Path(f).name == basename_to_find]

        if len(matches) == 1:
            print(f"Info: Found unique tracked file match: '{matches[0]}'", file=sys.stderr)
            return matches[0] # Return the relative path found by git
        elif len(matches) > 1:
            print(f"W: Ambiguous filename marker '{basename_to_find}'. Found multiple tracked files: {matches}. Cannot determine unique target.", file=sys.stderr)
            return None
        else:
            # This case might be hit if ls-files returns paths but none have the exact basename (unlikely with **/ pattern but possible)
            print(f"Info: No tracked file with exact basename '{basename_to_find}' found via ls-files.", file=sys.stderr)
            return None
    except subprocess.TimeoutExpired:
        print(f"W: Git ls-files command timed out while searching for '{basename_to_find}'.", file=sys.stderr)
        return None
    except Exception as e:
        print(f"E: Error searching Git for file '{basename_to_find}': {e}", file=sys.stderr)
        return None

def is_git_tracked(filepath_relative_to_repo: str) -> bool:
    """Checks if a specific relative path is tracked by Git."""
    if not IS_REPO: return False
    try:
        # Ensure path uses forward slashes for Git
        git_path = Path(filepath_relative_to_repo).as_posix()
        command = ['git', 'ls-files', '--error-unmatch', git_path]
        # Run the command. check=True will raise CalledProcessError if the file is not tracked (or other errors occur)
        subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', cwd=SERVER_DIR, timeout=5)
        # If check=True passes, the file is tracked
        return True
    except subprocess.CalledProcessError as e:
        # Return code 1 specifically means '--error-unmatch' failed because the file isn't tracked.
        # Other return codes might indicate different problems.
        #if e.returncode == 1:
        #    print(f"Info: Path '{filepath_relative_to_repo}' is not tracked by Git.", file=sys.stderr) # Debug
        #else:
        #    print(f"W: Git ls-files check failed for '{filepath_relative_to_repo}' (RC={e.returncode}): {e.stderr.strip()}", file=sys.stderr)
        return False # Specifically means not tracked or error occurred
    except subprocess.TimeoutExpired:
        print(f"W: Git track status check timed out for '{filepath_relative_to_repo}'. Assuming not tracked.", file=sys.stderr)
        return False
    except Exception as e:
        # Log other potential errors (e.g., permissions)
        print(f"E: Error checking Git track status for '{filepath_relative_to_repo}': {e}", file=sys.stderr)
        return False

def update_and_commit_file(filepath_absolute: Path, code_content: str, marker_filename: str) -> bool:
    """Writes content to an existing tracked file, stages, and commits if tracked and changed."""
    if not IS_REPO:
        print("W: Attempted Git commit, but not in a repo.", file=sys.stderr)
        return False
    try:
        # Derive relative path for Git commands and messages
        filepath_relative_to_repo_str = str(filepath_absolute.relative_to(SERVER_DIR))
        git_path_posix = filepath_absolute.relative_to(SERVER_DIR).as_posix()

        # Ensure parent directory exists (should already, if file is tracked, but belt-and-suspenders)
        filepath_absolute.parent.mkdir(parents=True, exist_ok=True)

        # Check if content has actually changed to avoid empty commits
        current_content = ""
        if filepath_absolute.exists():
             try:
                 current_content = filepath_absolute.read_text(encoding='utf-8')
             except Exception as read_e:
                 # If we can't read it, proceed with writing but warn
                 print(f"W: Could not read existing file {filepath_relative_to_repo_str} to check for changes: {read_e}", file=sys.stderr)

        if code_content == current_content:
             print(f"Info: Content for '{filepath_relative_to_repo_str}' is identical to the received code. Skipping Git add/commit.", file=sys.stderr)
             return True # Indicate success (no action needed)

        # Write the new content (overwrite)
        print(f"Info: Overwriting tracked local file: {filepath_relative_to_repo_str}", file=sys.stderr)
        try:
            filepath_absolute.write_text(code_content, encoding='utf-8')
        except OSError as write_e:
            print(f"E: Failed to write to file '{filepath_relative_to_repo_str}': {write_e}", file=sys.stderr)
            return False

        # Stage the changes
        print(f"Running: git add '{git_path_posix}' from {SERVER_DIR}", file=sys.stderr)
        add_result = subprocess.run(['git', 'add', git_path_posix], capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR, timeout=10)
        if add_result.returncode != 0:
            print(f"E: 'git add {git_path_posix}' failed (RC={add_result.returncode}):\n{add_result.stderr.strip()}", file=sys.stderr)
            # Consider attempting a git restore or reset here? Maybe too complex.
            return False

        # Commit the staged changes
        # Use the original marker filename in the commit message for clarity
        commit_message = f"Update {marker_filename} from AI Code Capture"
        print(f"Running: git commit -m \"{commit_message}\" -- '{git_path_posix}' ...", file=sys.stderr)
        # Use '--' to disambiguate path from other options, good practice
        commit_result = subprocess.run(['git', 'commit', '-m', commit_message, '--', git_path_posix], capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR, timeout=15)

        if commit_result.returncode == 0:
            # Success message often in stdout
            print(f"Success: Committed changes for '{git_path_posix}'.\n{commit_result.stdout.strip()}", file=sys.stderr)
            return True
        else:
             # Check common "no changes" messages in stdout or stderr
             no_changes_patterns = ["nothing to commit", "no changes added to commit", "nothing added to commit but untracked files present"]
             combined_output = (commit_result.stdout + commit_result.stderr).lower()
             if any(p in combined_output for p in no_changes_patterns):
                 print(f"Info: 'git commit' reported no effective changes staged for '{git_path_posix}'.", file=sys.stderr)
                 return True # Treat as success if no actual changes were committed
             else:
                 # Report actual commit error
                 print(f"E: 'git commit' failed for '{git_path_posix}' (RC={commit_result.returncode}):\n{commit_result.stderr.strip()}\n{commit_result.stdout.strip()}", file=sys.stderr)
                 # Consider git reset --hard HEAD ? Risky. Maybe git reset HEAD <file> to unstage?
                 # Best to leave the staged state and report failure.
                 return False
    except Exception as e:
        print(f"E: Unexpected error during Git update/commit process for {filepath_absolute}: {e}", file=sys.stderr)
        return False

def run_script(filepath: str, script_type: str):
    """Runs a Python or Shell script, logs output."""
    filepath_obj = Path(filepath).resolve() # Use absolute path for robustness
    # Check if file exists before proceeding
    if not filepath_obj.is_file():
        print(f"E: Script file not found for execution: {filepath_obj}", file=sys.stderr)
        return False, None # Cannot run a non-existent file

    filename_base = filepath_obj.stem
    # Ensure log folder exists right before logging
    os.makedirs(LOG_FOLDER_PATH, exist_ok=True)
    # Create log path using absolute path to log folder
    logpath = LOG_FOLDER_PATH / f"{filename_base}_{script_type}_run.log"
    # Run the script from its own directory
    run_cwd = filepath_obj.parent

    command = []
    interpreter_name = ""
    if script_type == 'python':
        # Prefer sys.executable if available, otherwise search PATH
        python_exe = sys.executable or shutil.which("python3") or shutil.which("python") or "python"
        if not shutil.which(python_exe): # Check if the chosen interpreter exists
             print(f"E: Python interpreter '{python_exe}' not found.", file=sys.stderr)
             try: logpath.write_text(f"Error: Python interpreter '{python_exe}' not found.\n", encoding='utf-8'); return False, str(logpath)
             except Exception as log_e: print(f"E: writing log: {log_e}"); return False, None
        command = [python_exe, str(filepath_obj)] # Pass absolute path to script
        interpreter_name = Path(python_exe).name
        print(f"Executing Python ({interpreter_name}): {' '.join(command)} in '{run_cwd}'", file=sys.stderr)
    elif script_type == 'shell':
        # Prefer bash if available, then sh
        shell_exe = shutil.which("bash") or shutil.which("sh")
        if not shell_exe:
             print("E: No 'bash' or 'sh' interpreter found in PATH.", file=sys.stderr)
             try: logpath.write_text("Error: No 'bash' or 'sh' interpreter found.\n", encoding='utf-8'); return False, str(logpath)
             except Exception as log_e: print(f"E: writing log: {log_e}"); return False, None
        command = [shell_exe, str(filepath_obj)] # Pass absolute path to script
        interpreter_name = Path(shell_exe).name
        print(f"Executing Shell ({interpreter_name}): {' '.join(command)} in '{run_cwd}'", file=sys.stderr)
    else:
        # Should not happen if called correctly, but handle defensively
        print(f"E: Cannot run script of unknown type '{script_type}' for {filepath}", file=sys.stderr)
        return False, None # No log path applicable here

    log_content = f"--- COMMAND ---\n{' '.join(command)}\n"
    log_content += f"--- CWD ---\n{run_cwd}\n"
    try:
        # Execute the command
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, encoding='utf-8', check=False, cwd=run_cwd)
        # Log results after completion
        log_content += f"--- STDOUT ---\n{result.stdout}\n"
        log_content += f"--- STDERR ---\n{result.stderr}\n"
        log_content += f"--- Return Code: {result.returncode} ---\n"
        with open(logpath, 'w', encoding='utf-8') as f: f.write(log_content)
        print(f"Exec finished ({script_type}). RC: {result.returncode}. Log: {logpath.name}", file=sys.stderr)
        return result.returncode == 0, str(logpath) # Success only if RC is 0

    except subprocess.TimeoutExpired:
        print(f"E: Script timed out after 15 seconds: {filepath_obj.name}", file=sys.stderr)
        log_content += f"--- ERROR ---\nScript execution timed out after 15 seconds.\n"
        # Write log even on timeout
        try:
            with open(logpath, 'w', encoding='utf-8') as f: f.write(log_content)
            return False, str(logpath)
        except Exception as log_e:
            print(f"E: Failed to write timeout log for {filepath_obj.name}: {log_e}", file=sys.stderr)
            return False, None # Indicate failure, log couldn't be written

    except FileNotFoundError:
        # This might happen if the script file disappears between the check and execution,
        # or less likely if cwd becomes invalid. The interpreter check earlier should prevent most cases.
        print(f"E: Script file '{filepath_obj}' or CWD '{run_cwd}' not found during execution.", file=sys.stderr)
        log_content += f"--- ERROR ---\nScript file '{filepath_obj}' or CWD '{run_cwd}' not found during execution.\n"
        try:
            with open(logpath, 'w', encoding='utf-8') as f: f.write(log_content)
            return False, str(logpath)
        except Exception as log_e:
            print(f"E: Failed to write FileNotFoundError log for {filepath_obj.name}: {log_e}", file=sys.stderr)
            return False, None

    except Exception as e:
        # Catch other potential errors during subprocess.run
        print(f"E: Unexpected error running script {filepath_obj.name}: {e}", file=sys.stderr)
        log_content += f"--- ERROR ---\nUnexpected error during script execution:\n{e}\n"
        try:
            with open(logpath, 'w', encoding='utf-8') as f: f.write(log_content)
            return False, str(logpath)
        except Exception as log_e:
            print(f"E: Failed to write general error log for {filepath_obj.name}: {log_e}", file=sys.stderr)
            return False, None

def check_shell_syntax(filepath: str) -> tuple[bool, str | None]:
    """Checks shell script syntax using 'bash -n'. Returns (syntax_ok, log_path)."""
    filepath_obj = Path(filepath).resolve()
    if not filepath_obj.is_file():
        print(f"E: Shell script file not found for syntax check: {filepath_obj}", file=sys.stderr)
        return False, None

    filename_base = filepath_obj.stem
    os.makedirs(LOG_FOLDER_PATH, exist_ok=True) # Ensure log folder exists
    logpath = LOG_FOLDER_PATH / f"{filename_base}_shell_syntax.log"

    # Find bash interpreter
    checker_exe = shutil.which("bash")
    if not checker_exe:
        print("W: 'bash' command not found. Cannot check shell syntax.", file=sys.stderr)
        # Try to write a log indicating this
        try: logpath.write_text("Error: 'bash' command not found for syntax check.\n", encoding='utf-8'); return False, str(logpath)
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
            # stderr usually contains the error message for bash -n
            print(f"Shell syntax Error for {filepath_obj.name}. RC: {result.returncode}. Log: {logpath.name}", file=sys.stderr)
            # Optionally print stderr directly if it's concise
            # if result.stderr: print(f"   Error details: {result.stderr.strip()}", file=sys.stderr)
            return False, str(logpath)

    except FileNotFoundError:
        # Should be caught by shutil.which earlier, but handle defensively
        print(f"E: Syntax check command '{checker_exe}' not found during execution.", file=sys.stderr)
        log_content += f"--- ERROR ---\nSyntax check command '{checker_exe}' not found during execution.\n"
        try:
             with open(logpath, 'w', encoding='utf-8') as f: f.write(log_content)
             return False, str(logpath)
        except Exception as log_e: print(f"E: writing log: {log_e}"); return False, None

    except subprocess.TimeoutExpired:
        print(f"E: Shell syntax check timed out for {filepath_obj.name}", file=sys.stderr)
        log_content += "--- ERROR ---\nShell syntax check timed out after 10 seconds.\n"
        try:
             with open(logpath, 'w', encoding='utf-8') as f: f.write(log_content)
             return False, str(logpath)
        except Exception as log_e: print(f"E: writing log: {log_e}"); return False, None

    except Exception as e:
        print(f"E: Unexpected error checking shell syntax for {filepath_obj.name}: {e}", file=sys.stderr)
        log_content += f"--- ERROR ---\nUnexpected error during syntax check:\n{e}\n"
        try:
            with open(logpath, 'w', encoding='utf-8') as f: f.write(log_content)
            return False, str(logpath)
        except Exception as log_e: print(f"E: writing log: {log_e}"); return False, None


# --- Route Definitions ---

@app.route('/status', methods=['GET'])
def get_status():
    """Returns current server status and configuration."""
    # print("Received /status request", file=sys.stderr) # Less verbose
    status_data = {
        'status': 'running',
        'working_directory': str(SERVER_DIR),
        'save_directory': str(SAVE_FOLDER_PATH.relative_to(SERVER_DIR)),
        'log_directory': str(LOG_FOLDER_PATH.relative_to(SERVER_DIR)),
        'is_git_repo': IS_REPO,
        'port': SERVER_PORT,
        'auto_run_python': AUTO_RUN_PYTHON_ON_SYNTAX_OK, # Report effective running state
        'auto_run_shell': AUTO_RUN_SHELL_ON_SYNTAX_OK,    # Report effective running state
        'config_file_exists': CONFIG_FILE.is_file()
    }
    return jsonify(status_data)

@app.route('/update_config', methods=['POST'])
def update_config():
    """Updates the server_config.json file with settings from the request.
       Note: Does NOT dynamically update the running server state."""
    if not request.is_json:
        return jsonify({'status': 'error', 'message': 'Request must be JSON'}), 400

    data = request.get_json()
    print(f"Received /update_config request data: {data}", file=sys.stderr)

    # Load current config state to update specific keys
    config_to_save = load_config() # Load existing or defaults
    updated = False

    # Validate and update enable_python_run if present in request
    python_run_req = data.get('auto_run_python')
    if python_run_req is not None:
        if isinstance(python_run_req, bool):
            if config_to_save.get('enable_python_run') != python_run_req:
                config_to_save['enable_python_run'] = python_run_req
                updated = True
                print(f"Config update: preparing to set enable_python_run to {python_run_req}", file=sys.stderr)
        else:
            print(f"W: Invalid type for 'auto_run_python' in request: {type(python_run_req)}. Expected bool.", file=sys.stderr)
            # Optionally return an error here, or just ignore the invalid value

    # Validate and update enable_shell_run if present in request
    shell_run_req = data.get('auto_run_shell')
    if shell_run_req is not None:
        if isinstance(shell_run_req, bool):
            if config_to_save.get('enable_shell_run') != shell_run_req:
                config_to_save['enable_shell_run'] = shell_run_req
                updated = True
                print(f"Config update: preparing to set enable_shell_run to {shell_run_req}", file=sys.stderr)
        else:
             print(f"W: Invalid type for 'auto_run_shell' in request: {type(shell_run_req)}. Expected bool.", file=sys.stderr)
             # Optionally return an error here, or just ignore the invalid value

    # Update port if present and valid
    port_req = data.get('port')
    if port_req is not None:
        try:
            port_val = int(port_req)
            if 1 <= port_val <= 65535:
                 if config_to_save.get('port') != port_val:
                     config_to_save['port'] = port_val
                     updated = True
                     print(f"Config update: preparing to set port to {port_val}", file=sys.stderr)
            else: raise ValueError("Port out of range")
        except (ValueError, TypeError):
            print(f"W: Invalid value for 'port' in request: {port_req}. Expected integer 1-65535.", file=sys.stderr)
            # Optionally return an error here, or just ignore the invalid value


    if updated:
        if save_config(config_to_save):
            return jsonify({
                'status': 'success',
                'message': f'Config saved to {CONFIG_FILE.name}. Restart server for changes to take effect.',
                'saved_config': config_to_save # Show what was actually saved
            })
        else:
            # Error saving the file
            return jsonify({'status': 'error', 'message': 'Failed to save config file.'}), 500
    else:
        print("Info: No effective config changes requested or values were invalid.", file=sys.stderr)
        return jsonify({
            'status': 'success', # Still success, just no action taken
            'message': 'No changes detected or requested values were invalid. Config file not modified.',
            'current_config': config_to_save # Show current state
        })

@app.route('/submit_code', methods=['POST', 'OPTIONS'])
def submit_code():
    # Handle CORS preflight request
    if request.method == 'OPTIONS':
        # Flask-CORS should handle this automatically if configured correctly,
        # but an explicit empty response is safe.
        return '', 204

    # Handle actual POST request
    if request.method == 'POST':
        # Acquire lock to prevent race conditions if multiple requests arrive concurrently
        # (especially important with file system operations and git)
        if not request_lock.acquire(blocking=False):
             print("W: Request rejected, server busy (lock acquisition failed).", file=sys.stderr)
             return jsonify({'status': 'error', 'message': 'Server busy, please try again shortly.'}), 429 # Too Many Requests

        try:
            print("\n--- Handling /submit_code request ---", file=sys.stderr)
            data = request.get_json()
            if not data:
                print("E: No JSON data received.", file=sys.stderr)
                return jsonify({'status': 'error', 'message': 'Request body must be JSON.'}), 400

            received_code = data.get('code', '')
            if not received_code or received_code.isspace():
                print("E: Received empty or whitespace-only 'code' field.", file=sys.stderr)
                return jsonify({'status': 'error', 'message': 'Empty code received.'}), 400

            # --- Initialize variables for response ---
            save_filepath_str = None        # Final absolute path where code was saved (string)
            final_save_filename = None      # Filename part or relative path used for display/logging
            code_to_save = received_code    # Code content, potentially stripped of marker
            extracted_filename_raw = None   # Raw filename from @@FILENAME@@ marker
            marker_line_length = 0          # Length of the marker line(s) including newline
            was_git_updated = False         # Flag if Git commit occurred
            sanitized_path_from_marker = None # Sanitized path derived from marker
            save_target = "fallback"        # Where the code was saved ('git' or 'fallback')
            absolute_path_target = None     # Potential target Path object (absolute)
            detected_language_name = "Unknown" # Language detected if fallback used

            # --- 1. Check for @@FILENAME@@ marker ---
            match = FILENAME_EXTRACT_REGEX.search(received_code)
            if match:
                extracted_filename_raw = match.group(1).strip()
                # Calculate length to remove marker line(s) later if saving to git
                # Assumes marker is on its own line(s) at the very beginning
                marker_line_length = match.end(0) # End position of the whole match
                # Check if the character immediately after the match is a newline and include it
                if marker_line_length < len(received_code) and received_code[marker_line_length] == '\n':
                    marker_line_length += 1
                elif marker_line_length < len(received_code) and received_code[marker_line_length:marker_line_length+2] == '\r\n':
                    marker_line_length += 2

                print(f"Info: Found @@FILENAME@@ marker: '{extracted_filename_raw}'", file=sys.stderr)

                # --- 2. Sanitize the extracted filename/path ---
                sanitized_path_from_marker = sanitize_filename(extracted_filename_raw)

                if sanitized_path_from_marker:
                    print(f"Info: Sanitized path from marker: '{sanitized_path_from_marker}'", file=sys.stderr)

                    # --- 3. Determine Save Target (Git or Fallback) ---
                    if IS_REPO:
                        # Path to check within the Git repo (relative to SERVER_DIR)
                        git_path_to_check = sanitized_path_from_marker

                        # If the sanitized path is just a filename (no slashes), try to find its unique location in the repo
                        if '/' not in sanitized_path_from_marker.replace('\\', '/'):
                            found_rel_path = find_tracked_file_by_name(sanitized_path_from_marker)
                            if found_rel_path:
                                print(f"Info: Found unique tracked file '{found_rel_path}' matching basename '{sanitized_path_from_marker}'. Using it as target.", file=sys.stderr)
                                git_path_to_check = found_rel_path
                            #else: # Not found or ambiguous, proceed with the sanitized name
                            #    print(f"Info: Basename '{sanitized_path_from_marker}' not found uniquely in repo. Will check tracking status for this literal path.", file=sys.stderr)

                        # Construct the absolute path based on the potential relative path
                        absolute_path_target = (SERVER_DIR / git_path_to_check).resolve()

                        # SECURITY CHECK: Ensure the resolved path is still within the server directory
                        if not str(absolute_path_target).startswith(str(SERVER_DIR)):
                            print(f"W: Potential directory traversal detected! Resolved path '{absolute_path_target}' is outside server root '{SERVER_DIR}'. Blocking Git operation.", file=sys.stderr)
                            absolute_path_target = None # Prevent using this path
                        else:
                            # Check if this specific relative path is tracked by Git
                            is_tracked = is_git_tracked(git_path_to_check)
                            if is_tracked:
                                print(f"Info: Target path '{git_path_to_check}' (resolves to '{absolute_path_target.relative_to(SERVER_DIR)}') is tracked by Git. Attempting Git update.", file=sys.stderr)
                                # Prepare code content without the marker line
                                code_to_save = received_code[marker_line_length:]
                                # Attempt to update the file in Git
                                commit_success = update_and_commit_file(absolute_path_target, code_to_save, git_path_to_check)
                                if commit_success:
                                    # Git update successful!
                                    save_filepath_str = str(absolute_path_target)
                                    final_save_filename = git_path_to_check # Use the relative path for display
                                    was_git_updated = True
                                    save_target = "git"
                                    # Language is implicitly defined by the existing file's extension
                                    detected_language_name = f"From Git ({Path(git_path_to_check).suffix})"
                                else:
                                    # Git commit failed, fall back to saving in received_codes
                                    print(f"W: Git update/commit failed for '{git_path_to_check}'. Reverting to fallback save.", file=sys.stderr)
                                    # Reset variables for fallback
                                    code_to_save = received_code # Save original code including marker
                                    absolute_path_target = None
                                    save_target = "fallback"
                            else:
                                # Path is valid and within repo, but not tracked by Git
                                print(f"Info: Path '{git_path_to_check}' is within the repo but not tracked by Git. Will save to fallback location using this name.", file=sys.stderr)
                                # Use the sanitized path to save within SAVE_FOLDER_PATH
                                absolute_path_target = (SAVE_FOLDER_PATH / sanitized_path_from_marker).resolve()
                                # Security check: ensure it's within SAVE_FOLDER_PATH
                                if not str(absolute_path_target).startswith(str(SAVE_FOLDER_PATH)):
                                     print(f"W: Fallback path '{absolute_path_target}' escaped save folder '{SAVE_FOLDER_PATH}'! Using timestamped fallback.", file=sys.stderr)
                                     absolute_path_target = None
                                #else: # Path is okay, proceed with fallback using this name
                                code_to_save = received_code # Save original code including marker
                                save_target = "fallback"
                    else: # Not a Git repository
                         print(f"Info: Not a Git repository. Will save to fallback location using sanitized marker path '{sanitized_path_from_marker}'.", file=sys.stderr)
                         # Use the sanitized path to save within SAVE_FOLDER_PATH
                         absolute_path_target = (SAVE_FOLDER_PATH / sanitized_path_from_marker).resolve()
                         # Security check: ensure it's within SAVE_FOLDER_PATH
                         if not str(absolute_path_target).startswith(str(SAVE_FOLDER_PATH)):
                              print(f"W: Fallback path '{absolute_path_target}' escaped save folder '{SAVE_FOLDER_PATH}'! Using timestamped fallback.", file=sys.stderr)
                              absolute_path_target = None
                         #else: # Path is okay, proceed with fallback using this name
                         code_to_save = received_code # Save original code including marker
                         save_target = "fallback"

                else: # Sanitization failed
                    print(f"W: Invalid or unsafe marker filename '{extracted_filename_raw}'. Sanitization failed. Using timestamped fallback.", file=sys.stderr)
                    absolute_path_target = None # Force fallback to timestamped
                    save_target = "fallback"
                    code_to_save = received_code # Use original code
            else: # No marker found
                print("Info: No @@FILENAME@@ marker found. Using timestamped fallback.", file=sys.stderr)
                absolute_path_target = None # Force fallback to timestamped
                save_target = "fallback"
                code_to_save = received_code # Use original code

            # --- 4. Handle Fallback Saving (if not saved via Git) ---
            if save_target == "fallback":
                if absolute_path_target: # Use path derived from marker (but not committed to Git)
                     save_filepath_str = str(absolute_path_target)
                     # Determine display filename (relative to save folder if possible)
                     try: final_save_filename = Path(save_filepath_str).relative_to(SAVE_FOLDER_PATH).as_posix()
                     except ValueError: final_save_filename = Path(save_filepath_str).name # If somehow outside, just use name
                     # Infer language from extension
                     ext = Path(save_filepath_str).suffix.lower()
                     if ext == '.py': detected_language_name = "Python"
                     elif ext == '.sh': detected_language_name = "Shell"
                     elif ext == '.js': detected_language_name = "JavaScript"
                     # etc. Add more common ones if needed
                     else: detected_language_name = f"From Path ({ext})" if ext else "From Path (no ext)"
                     print(f"Info: Saving fallback using marker-derived path: '{final_save_filename}' in '{SAVE_FOLDER}'", file=sys.stderr)
                else: # Generate a timestamped filename
                     base_name = "code"
                     ext = DEFAULT_EXTENSION
                     # Try to get a better base name/extension if marker was present but invalid/unsafe
                     if sanitized_path_from_marker: # Marker existed but wasn't used for path
                         p = Path(sanitized_path_from_marker) # Use the sanitized version
                         base_name = p.stem if p.stem else "code"
                         ext = p.suffix if p.suffix and len(p.suffix) > 1 else DEFAULT_EXTENSION
                         detected_language_name = "From Fallback (Marker Invalid)"
                     else: # No marker, detect language from code content
                         ext, detected_language_name = detect_language_and_extension(code_to_save)

                     # Refine base_name based on detected language if useful
                     if detected_language_name not in ["Unknown", "Text", "From Fallback (Marker Invalid)"]:
                         base_name = detected_language_name.lower().replace(" ", "_").replace("/", "_")

                     save_filepath_str = generate_timestamped_filepath(extension=ext, base_prefix=base_name)
                     final_save_filename = Path(save_filepath_str).name # Just the filename part
                     print(f"Info: Saving fallback using generated timestamped filename: '{final_save_filename}'", file=sys.stderr)

                # Perform the actual save operation for fallback
                print(f"Info: Writing code to fallback file: '{save_filepath_str}'", file=sys.stderr)
                try:
                    save_path_obj = Path(save_filepath_str)
                    # Ensure parent directory exists (especially for nested paths from marker)
                    save_path_obj.parent.mkdir(parents=True, exist_ok=True)
                    save_path_obj.write_text(code_to_save, encoding='utf-8')
                    print(f"Success: Code saved to fallback file '{final_save_filename}'", file=sys.stderr)
                except Exception as e:
                    print(f"E: Failed to save fallback file '{save_filepath_str}': {str(e)}", file=sys.stderr)
                    # Critical error, cannot proceed
                    return jsonify({'status': 'error', 'message': f'Failed to save file: {str(e)}'}), 500

            # --- 5. Perform Syntax Checks and Auto-Run (if enabled) ---
            syntax_ok = None      # True, False, or None (if not checked)
            run_success = None    # True, False, or None (if not run)
            log_filename = None   # Name of the log file generated (syntax or run)
            script_type = None    # 'python' or 'shell' if applicable

            # Ensure we have a valid path to the saved file before checks
            if not save_filepath_str or not Path(save_filepath_str).is_file():
                print(f"E: Saved file path '{save_filepath_str}' is invalid or file does not exist before checks!", file=sys.stderr)
                # Return success based on saving, but indicate check failure
                response_data = {'status': 'success', 'saved_as': final_save_filename, 'saved_path': str(Path(save_filepath_str).relative_to(SERVER_DIR)) if save_filepath_str else None, 'log_file': None, 'syntax_ok': None, 'run_success': None, 'script_type': None, 'source_file_marker': extracted_filename_raw, 'git_updated': was_git_updated, 'save_location': save_target, 'detected_language': detected_language_name, 'message': 'File saved, but checks could not be performed due to internal path error.' }
                return jsonify(response_data)

            # Use the final saved path (absolute) for checks/runs
            check_run_filepath = save_filepath_str
            # Use the filename part for display purposes
            display_filename = final_save_filename if final_save_filename else Path(check_run_filepath).name

            file_extension = Path(display_filename).suffix.lower()

            # --- Python Check/Run ---
            if file_extension == '.py':
                script_type = 'python'
                # Prevent checking/running the server script itself
                is_server_script = Path(check_run_filepath).resolve() == (SERVER_DIR / THIS_SCRIPT_NAME).resolve()
                if is_server_script:
                    print(f"Info: Skipping syntax check and run for server script itself ('{display_filename}').", file=sys.stderr)
                else:
                    print(f"Info: Performing Python syntax check for '{display_filename}'...", file=sys.stderr)
                    try:
                        # Use the code content that was actually saved
                        saved_code_content = Path(check_run_filepath).read_text(encoding='utf-8')
                        # Compile to check syntax. Use the actual filepath for better tracebacks.
                        compile(saved_code_content, check_run_filepath, 'exec')
                        syntax_ok = True
                        print(f"Info: Python syntax OK for '{display_filename}'.", file=sys.stderr)

                        # Auto-run if enabled and syntax is OK
                        if AUTO_RUN_PYTHON_ON_SYNTAX_OK:
                            print(f"Info: Attempting to run Python script '{display_filename}' (auto-run enabled).", file=sys.stderr)
                            run_success, logpath = run_script(check_run_filepath, 'python')
                            if logpath: log_filename = Path(logpath).name
                            print(f"Info: Python run completed for '{display_filename}'. Success: {run_success}, Log: {log_filename}", file=sys.stderr)
                        else:
                            print(f"Info: Python auto-run disabled. Skipping execution.", file=sys.stderr)

                    except SyntaxError as e:
                        syntax_ok = False
                        run_success = False # Cannot run if syntax fails
                        err_line = e.lineno if e.lineno else 'N/A'
                        err_offset = e.offset if e.offset else 'N/A'
                        err_msg = e.msg if e.msg else 'Unknown syntax error'
                        err_text = e.text.strip() if e.text else 'N/A'
                        print(f"E: Python Syntax Error in '{display_filename}': L{err_line} C{err_offset} -> {err_msg}", file=sys.stderr)
                        # Try to create a simple log file for the syntax error
                        log_fn_base = Path(check_run_filepath).stem
                        log_path_err = LOG_FOLDER_PATH / f"{log_fn_base}_py_syntax_error.log"
                        try:
                            log_path_err.parent.mkdir(parents=True, exist_ok=True)
                            log_path_err.write_text(f"Python Syntax Error:\nFile: {display_filename}\nLine: {err_line}\nOffset: {err_offset}\nMessage: {err_msg}\nContext:\n{err_text}", encoding='utf-8')
                            log_filename = log_path_err.name
                        except Exception as log_e:
                            print(f"E: Could not write Python syntax error log: {log_e}", file=sys.stderr)
                    except Exception as compile_e:
                        # Catch other errors during compile (e.g., file read errors handled above, but maybe others)
                        syntax_ok = False # Treat as syntax failure if compile fails
                        run_success = False
                        print(f"E: Error during Python compile/setup for '{display_filename}': {compile_e}", file=sys.stderr)
                        log_fn_base = Path(check_run_filepath).stem
                        log_path_err = LOG_FOLDER_PATH / f"{log_fn_base}_py_compile_error.log"
                        try:
                            log_path_err.parent.mkdir(parents=True, exist_ok=True)
                            log_path_err.write_text(f"Python Compile/Setup Error:\nFile: {display_filename}\nError: {compile_e}\n", encoding='utf-8')
                            log_filename = log_path_err.name
                        except Exception as log_e:
                             print(f"E: Could not write Python compile error log: {log_e}", file=sys.stderr)

            # --- Shell Check/Run ---
            elif file_extension == '.sh':
                 script_type = 'shell'
                 print(f"Info: Performing Shell syntax check for '{display_filename}'...", file=sys.stderr)
                 syntax_ok, syntax_log_path = check_shell_syntax(check_run_filepath)
                 if syntax_log_path: log_filename = Path(syntax_log_path).name # Use syntax log by default

                 if syntax_ok:
                      # Auto-run if enabled and syntax is OK
                      if AUTO_RUN_SHELL_ON_SYNTAX_OK:
                           print(f"Info: Attempting to run Shell script '{display_filename}' (auto-run enabled).", file=sys.stderr)
                           run_success, run_log_path = run_script(check_run_filepath, 'shell')
                           # Overwrite log_filename with run log if run was attempted
                           if run_log_path: log_filename = Path(run_log_path).name
                           print(f"Info: Shell run completed for '{display_filename}'. Success: {run_success}, Log: {log_filename}", file=sys.stderr)
                      else:
                           print(f"Info: Shell auto-run disabled. Skipping execution.", file=sys.stderr)
                 else: # Syntax failed
                      run_success = False # Cannot run if syntax fails
                      print(f"Info: Shell syntax error prevented run for '{display_filename}'. Log: {log_filename}", file=sys.stderr)

            # --- Other file types ---
            else:
                print(f"Info: File '{display_filename}' is not Python (.py) or Shell (.sh). Skipping syntax checks and execution.", file=sys.stderr)
                # syntax_ok and run_success remain None

            # --- 6. Prepare and Send Response ---
            response_data = {
                'status': 'success',
                'saved_as': final_save_filename, # Filename or relative path for display
                'saved_path': str(Path(save_filepath_str).relative_to(SERVER_DIR)) if save_filepath_str else None, # Path relative to server root
                'log_file': log_filename, # Name of log file in logs dir, if any
                'syntax_ok': syntax_ok, # True, False, or None
                'run_success': run_success, # True, False, or None
                'script_type': script_type, # 'python', 'shell', or None
                'source_file_marker': extracted_filename_raw, # Original marker content, if any
                'git_updated': was_git_updated, # True if committed to Git
                'save_location': save_target, # 'git' or 'fallback'
                'detected_language': detected_language_name # Best guess language name
            }
            print(f"Sending response: {response_data}", file=sys.stderr)
            print("--- Request complete ---")
            return jsonify(response_data)

        except Exception as e:
            # Catch-all for unexpected errors during request processing
            print(f"E: Unhandled exception during /submit_code: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr) # Print full traceback for debugging
            return jsonify({'status': 'error', 'message': f'Internal server error: {e}'}), 500
        finally:
            # Ensure the lock is always released, even if errors occur
            if request_lock.locked():
                request_lock.release()
                # print("Info: Request lock released.", file=sys.stderr) # Debug

    # If method is not POST or OPTIONS (though Flask handles basic method errors)
    return jsonify({'status': 'error', 'message': f'Unsupported method: {request.method}'}), 405


@app.route('/test_connection', methods=['GET'])
def test_connection():
    """Simple endpoint to test if the server is running, returns status."""
    print("Received /test_connection request", file=sys.stderr)
    # Reuse the status endpoint logic
    return get_status()

# --- Log Routes ---
@app.route('/logs')
def list_logs():
    """Provides an HTML page listing available log files."""
    log_files = []
    # Simple HTML template with basic styling
    template = '''<!DOCTYPE html>
<html>
<head>
    <title>Logs Browser</title>
    <style>
        body { font-family: sans-serif; background-color: #f4f4f4; color: #333; margin: 0; padding: 20px; }
        h1 { color: #444; border-bottom: 1px solid #ccc; padding-bottom: 10px; }
        ul { list-style: none; padding: 0; }
        li { background-color: #fff; margin-bottom: 8px; border: 1px solid #ddd; border-radius: 4px; transition: box-shadow 0.2s ease-in-out; }
        li:hover { box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        li a { color: #007bff; text-decoration: none; display: block; padding: 12px 15px; }
        li a:hover { background-color: #eee; }
        p { color: #666; }
        pre { background-color: #eee; border: 1px solid #ccc; padding: 15px; border-radius: 5px; overflow-x: auto; white-space: pre-wrap; word-wrap: break-word; font-family: monospace; }
    </style>
</head>
<body>
    <h1>🗂️ Available Logs</h1>
    {% if logs %}
        <p>Found {{ logs|length }} log file(s) in '{{ log_folder_name }}'. Click to view.</p>
        <ul>
        {% for log in logs %}
            <li><a href="/logs/{{ log | urlencode }}">{{ log }}</a></li>
        {% endfor %}
        </ul>
    {% else %}
        <p>No log files found in '{{ log_folder_name }}'.</p>
    {% endif %}
</body>
</html>'''
    try:
         # Ensure log folder path exists before listing
         if LOG_FOLDER_PATH.is_dir():
             # Get Path objects, filter for files ending in .log
             log_paths = [p for p in LOG_FOLDER_PATH.glob('*.log') if p.is_file()]
             # Sort by modification time, newest first
             log_paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
             # Get just the filenames for the template
             log_files = [p.name for p in log_paths]
         # else: log_files remains empty if folder doesn't exist
    except FileNotFoundError:
        print(f"W: Log directory '{LOG_FOLDER_PATH}' not found when listing logs.", file=sys.stderr)
    except Exception as e:
        print(f"E: Error listing log files: {e}", file=sys.stderr)
        # Potentially return an error page or message here
    return render_template_string(template, logs=log_files, log_folder_name=LOG_FOLDER_PATH.name)

@app.route('/logs/<path:filename>')
def serve_log(filename):
    """Serves a specific log file as plain text."""
    # Basic security: prevent directory traversal
    if '..' in filename or filename.startswith('/'):
        print(f"W: Forbidden log access attempt: {filename}", file=sys.stderr)
        return "Forbidden", 403

    # print(f"Request for log file: {filename}", file=sys.stderr) # Verbose
    try:
        # Resolve paths securely
        log_dir = LOG_FOLDER_PATH.resolve()
        requested_path = (log_dir / filename).resolve()

        # Double-check the resolved path is still within the intended log directory
        if not str(requested_path).startswith(str(log_dir)) or not requested_path.is_file():
            print(f"W: Log file not found or path mismatch: {filename}", file=sys.stderr)
            return "Log file not found", 404 # Return 404 for security (don't reveal existence)

        # Use send_from_directory for safe serving
        # mimetype='text/plain' ensures browser displays it correctly
        # as_attachment=False makes it display inline instead of downloading
        return send_from_directory(
            LOG_FOLDER_PATH,
            filename,
            mimetype='text/plain; charset=utf-8', # Specify charset
            as_attachment=False
        )
    except FileNotFoundError:
        # This might be redundant due to the check above, but safe to keep
        return "Log file not found", 404
    except Exception as e:
        print(f"E: Error serving log file {filename}: {e}", file=sys.stderr)
        return "Error serving file", 500

# --- Main Execution ---
if __name__ == '__main__':
    host_ip = '127.0.0.1' # Listen only on localhost by default for security
    port_num = SERVER_PORT

    print(f"--- AI Code Capture Server ---")
    print(f"Config File Path: '{CONFIG_FILE}'")
    print(f"  Config Exists: {CONFIG_FILE.is_file()}")
    print(f"  Loaded/Default Config: {current_config}") # Show initial config loaded
    print("-" * 30)
    print(f"Effective Running Settings:")
    print(f"  Host: {host_ip}")
    print(f"  Port: {port_num}")
    print(f"  Server CWD (Potential Git Root): {SERVER_DIR}")
    print(f"  Saving Non-Git Files to: ./{SAVE_FOLDER_PATH.relative_to(SERVER_DIR)}")
    print(f"  Saving Logs to:            ./{LOG_FOLDER_PATH.relative_to(SERVER_DIR)}")
    print(f"  Git Integration: {'ENABLED' if IS_REPO else 'DISABLED (Not a Git repo or `git` not found)'}")
    print(f"  Python Auto-Run: {'ENABLED' if AUTO_RUN_PYTHON_ON_SYNTAX_OK else 'DISABLED'}")
    print(f"  Shell Auto-Run:  {'ENABLED' if AUTO_RUN_SHELL_ON_SYNTAX_OK else 'DISABLED'}{' <-- DANGEROUS! USE WITH EXTREME CAUTION!' if AUTO_RUN_SHELL_ON_SYNTAX_OK else ''}")
    print("-" * 30)
    print(f"Starting Flask server on http://{host_ip}:{port_num}")
    print("Use Ctrl+C to stop the server.")
    print("--- Server ready ---", file=sys.stderr) # Log to stderr as well

    try:
        # Use Flask's development server. For production, consider a WSGI server like Gunicorn or Waitress.
        # debug=False is crucial for security, prevents arbitrary code execution via debugger.
        app.run(host=host_ip, port=port_num, debug=False)
    except OSError as e:
        # Specific check for "Address already in use"
        if "Address already in use" in str(e) or ("WinError 10048" in str(e) and os.name == 'nt'):
            print(f"\nE: Port {port_num} is already in use.", file=sys.stderr)
            print(f"   Please stop the other process using this port or choose a different port", file=sys.stderr)
            print(f"   using the '-p <new_port>' argument, e.g.:", file=sys.stderr)
            print(f"   python3 {THIS_SCRIPT_NAME} -p {port_num + 1}", file=sys.stderr)
            sys.exit(1)
        else:
            # Catch other OS errors during server startup
            print(f"\nE: Failed to start server due to OS error: {e}", file=sys.stderr)
            sys.exit(1)
    except KeyboardInterrupt:
        # Handle graceful shutdown on Ctrl+C
        print("\n--- Server shutting down (Ctrl+C detected) ---", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        # Catch any other unexpected errors during startup
        print(f"\nE: An unexpected error occurred during server startup: {e}", file=sys.stderr)
        sys.exit(1)