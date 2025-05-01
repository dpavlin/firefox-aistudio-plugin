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
        return defaults
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            # Validate types or provide defaults for missing keys
            defaults['port'] = int(config.get('port', defaults['port']))
            defaults['enable_python_run'] = bool(config.get('enable_python_run', defaults['enable_python_run']))
            defaults['enable_shell_run'] = bool(config.get('enable_shell_run', defaults['enable_shell_run']))
            return defaults
    except (json.JSONDecodeError, ValueError, TypeError, OSError) as e:
        print(f"W: Error reading config file '{CONFIG_FILE}': {e}. Using defaults.", file=sys.stderr)
        return defaults

def save_config(config_data):
    """Saves config data to JSON file."""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4)
        print(f"Info: Configuration saved to '{CONFIG_FILE}'.", file=sys.stderr)
        return True
    except (OSError, TypeError) as e:
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
    default=current_config['enable_shell_run'], # Default from config
    help='DANGEROUS: Enable automatic execution of shell scripts. Overrides config file if used.'
)
parser.add_argument(
    '--enable-python-run', action='store_true',
    default=current_config['enable_python_run'], # Default from config
    help='Enable automatic execution of Python scripts. Overrides config file if used.'
)
# Add a flag to indicate if args were explicitly provided vs defaults
# This helps determine if command-line args should override loaded config values
# We need to parse known args first to see if they differ from loaded defaults
args, unknown = parser.parse_known_args()

# Determine final config values based on precedence: command-line > config file > hardcoded defaults
SERVER_PORT = args.port
AUTO_RUN_PYTHON_ON_SYNTAX_OK = args.enable_python_run
AUTO_RUN_SHELL_ON_SYNTAX_OK = args.shell

# Update current_config dictionary ONLY if args differ from initial config load AND weren't default arg values
# This logic is a bit complex because argparse sets defaults. A cleaner way might be separate load->parse->merge steps.
# Simpler approach: Just use the parsed args directly. The config file primarily provides defaults if args aren't given.
final_config_for_status = {
    'port': SERVER_PORT,
    'enable_python_run': AUTO_RUN_PYTHON_ON_SYNTAX_OK,
    'enable_shell_run': AUTO_RUN_SHELL_ON_SYNTAX_OK
}


# --- Flask App Setup ---
app = Flask(__name__)
CORS(app) # Enable CORS for all routes

# --- Lock ---
request_lock = threading.Lock()
print("Request lock initialized.", file=sys.stderr)

# --- Paths & Constants (rest is mostly unchanged) ---
SAVE_FOLDER = 'received_codes'; LOG_FOLDER = 'logs'
SERVER_DIR = Path.cwd().resolve()
SAVE_FOLDER_PATH = SERVER_DIR / SAVE_FOLDER
LOG_FOLDER_PATH = SERVER_DIR / LOG_FOLDER
THIS_SCRIPT_NAME = Path(__file__).name
os.makedirs(SAVE_FOLDER_PATH, exist_ok=True)
os.makedirs(LOG_FOLDER_PATH, exist_ok=True)

FILENAME_EXTRACT_REGEX = re.compile(r"^\s*(?://|#)\s*@@FILENAME@@\s+(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
FILENAME_SANITIZE_REGEX = re.compile(r'[^a-zA-Z0-9._\-\/]')
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

# --- Helper Functions (sanitize_filename, detect_language_and_extension, etc. remain the same) ---
# (Include all helper functions from list-received_codes_curses_adaptive.py version here)
# ... (sanitize_filename, detect_language_and_extension, ...)
# ... (generate_timestamped_filepath, is_git_repository, find_tracked_file_by_name, ...)
# ... (is_git_tracked, update_and_commit_file, run_script, check_shell_syntax)
# --- [PASTE ALL HELPER FUNCTIONS HERE FROM PREVIOUS VERSION] ---
# --- Make sure IS_REPO is defined after is_git_repository() ---
IS_REPO = is_git_repository()

# --- Route Definitions ---

# --- NEW: Server Status Endpoint ---
@app.route('/status', methods=['GET'])
def get_status():
    print("Received /status request", file=sys.stderr)
    status_data = {
        'status': 'running',
        'working_directory': str(SERVER_DIR),
        'save_directory': str(SAVE_FOLDER_PATH.relative_to(SERVER_DIR)),
        'log_directory': str(LOG_FOLDER_PATH.relative_to(SERVER_DIR)),
        'is_git_repo': IS_REPO,
        'port': SERVER_PORT, # The actual port the server is running on
        'auto_run_python': AUTO_RUN_PYTHON_ON_SYNTAX_OK, # Actual running state
        'auto_run_shell': AUTO_RUN_SHELL_ON_SYNTAX_OK,    # Actual running state
        'config_file_exists': CONFIG_FILE.is_file()
    }
    return jsonify(status_data)

# --- NEW: Update Configuration Endpoint ---
@app.route('/update_config', methods=['POST'])
def update_config():
    if not request.is_json:
        return jsonify({'status': 'error', 'message': 'Request must be JSON'}), 400

    data = request.get_json()
    print(f"Received /update_config request data: {data}", file=sys.stderr)

    # Prepare new config data, starting with current RUNNING config
    # (or reload from file to prevent overwriting unrelated settings?)
    # Let's reload from file to be safer with potential future settings
    config_to_save = load_config()

    # Update only the keys we allow changing from the popup
    python_run = data.get('auto_run_python')
    shell_run = data.get('auto_run_shell')

    # Basic validation
    if python_run is not None and isinstance(python_run, bool):
        config_to_save['enable_python_run'] = python_run
        print(f"Config update: set enable_python_run to {python_run}", file=sys.stderr)
    elif python_run is not None:
        print(f"W: Invalid type for auto_run_python in update request: {type(python_run)}", file=sys.stderr)

    if shell_run is not None and isinstance(shell_run, bool):
        config_to_save['enable_shell_run'] = shell_run
        print(f"Config update: set enable_shell_run to {shell_run}", file=sys.stderr)
    elif shell_run is not None:
        print(f"W: Invalid type for auto_run_shell in update request: {type(shell_run)}", file=sys.stderr)

    # Add port saving? Might be tricky if current port != config port due to command line override
    # Let's keep port changes manual via command line or direct config edit for now.
    # config_to_save['port'] = SERVER_PORT # Save the *currently running* port?

    if save_config(config_to_save):
        return jsonify({
            'status': 'success',
            'message': f'Configuration saved to {CONFIG_FILE.name}. Restart server manually for changes to take effect.',
            'saved_config': config_to_save # Send back what was saved
        })
    else:
        return jsonify({'status': 'error', 'message': 'Failed to save configuration file.'}), 500


# --- submit_code Route (largely unchanged, uses global flag vars) ---
@app.route('/submit_code', methods=['POST', 'OPTIONS'])
def submit_code():
    # (Keep the /submit_code logic exactly as in list-received_codes_curses_adaptive.py)
    # ... It uses the global AUTO_RUN_PYTHON_ON_SYNTAX_OK and AUTO_RUN_SHELL_ON_SYNTAX_OK ...
    # --- [PASTE THE FULL /submit_code ROUTE HERE FROM PREVIOUS VERSION] ---
    pass # Placeholder

# --- Test Connection Route (Unchanged) ---
@app.route('/test_connection', methods=['GET'])
def test_connection():
    # Maybe merge this functionality into /status ?
    print("Received /test_connection request (will redirect to /status logic)", file=sys.stderr)
    return get_status() # Just return the full status

# --- Log Routes (Unchanged) ---
# (Include list_logs and serve_log routes here)
# --- [PASTE /logs and /logs/<filename> ROUTES HERE] ---
pass # Placeholder

# --- Main Execution ---
if __name__ == '__main__':
    host_ip = '127.0.0.1'; port_num = SERVER_PORT # Use final port value
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
        app.run(host=host_ip, port=port_num, debug=False)
    except OSError as e:
        if "Address already in use" in str(e) or "WinError" in str(e): # Broader check
            print(f"\nE: Address already in use (Port {port_num}).", file=sys.stderr)
            print(f"   Another program might be running, or use 'python3 {THIS_SCRIPT_NAME} -p <new_port>'", file=sys.stderr)
            sys.exit(1)
        else: print(f"\nE: Failed to start server: {e}", file=sys.stderr); sys.exit(1)
    except KeyboardInterrupt: print("\n--- Server shutting down ---", file=sys.stderr); sys.exit(0)

# --- END OF FILE: server.py ---