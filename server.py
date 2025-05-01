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
        sanitized_part = FILENAME_SANITIZE_REGEX.sub('_', part).strip('_')
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
    """Detects language and returns (extension, language_name)."""
    first_lines = code.splitlines()[:3]
    if first_lines:
        if first_lines[0].startswith('#!/usr/bin/env python') or first_lines[0].startswith('#!/usr/bin/python'): return '.py', 'Python'
        if first_lines[0].startswith('#!/bin/bash') or first_lines[0].startswith('#!/bin/sh'): return '.sh', 'Shell'
        if first_lines[0].startswith('<?php'): return '.php', 'PHP'

    # Simple heuristic checks (order might matter)
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
    """Generates a unique timestamped filepath in SAVE_FOLDER_PATH."""
    today = datetime.datetime.now().strftime("%Y%m%d"); counter = 1
    if not extension.startswith('.'): extension = '.' + extension
    safe_base_prefix = re.sub(r'[^a-zA-Z0-9_\-]', '_', base_prefix).strip('_')
    if not safe_base_prefix: safe_base_prefix = "code"

    while True:
        filename = f"{safe_base_prefix}_{today}_{counter:03d}{extension}"
        filepath = SAVE_FOLDER_PATH / filename
        if not filepath.exists():
            return str(filepath)
        counter += 1
        if counter > 999:
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
        command = ['git', 'ls-files', f'**/{basename_to_find}']
        # print(f"Running: {' '.join(command)} from {SERVER_DIR} to find matches for '*/{basename_to_find}'", file=sys.stderr) # Less verbose
        result = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR, timeout=5)
        if result.returncode != 0:
             if result.returncode == 1 and not result.stdout and not result.stderr: pass # No matches found is okay
             else: print(f"E: 'git ls-files' failed (RC={result.returncode}):\n{result.stderr}", file=sys.stderr)
             return None

        tracked_files = result.stdout.splitlines()
        matches = [f for f in tracked_files if Path(f).nam