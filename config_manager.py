# @@FILENAME@@ config_manager.py
import argparse
import json
import sys
import os
import subprocess
from pathlib import Path

CONFIG_FILE = Path.cwd().resolve() / 'server_config.json'
SERVER_DIR = Path.cwd().resolve() # Define SERVER_DIR here
SAVE_FOLDER = 'received_codes'
LOG_FOLDER = 'logs'
SAVE_FOLDER_PATH = SERVER_DIR / SAVE_FOLDER
LOG_FOLDER_PATH = SERVER_DIR / LOG_FOLDER

try:
    THIS_SCRIPT_NAME = Path(__file__).name # Or the name of the main server script if different
except NameError:
    THIS_SCRIPT_NAME = "server.py" # Fallback

def load_config():
    """Loads config from JSON file, returns defaults if not found/invalid."""
    defaults = {
        'port': 5000,
        'enable_python_run': False,
        'enable_shell_run': False
    }
    if not CONFIG_FILE.is_file():
        print(f"Info: Config file '{CONFIG_FILE}' not found. Using defaults.", file=sys.stderr)
        return defaults.copy()
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            loaded_config = defaults.copy()
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
        return defaults.copy()

def save_config(config_data):
    """Saves specific config data to JSON file, preserving other keys."""
    try:
        current_saved_config = load_config() # Load existing state from file
        # Only update keys that are explicitly passed in config_data
        for key, value in config_data.items():
            if key in current_saved_config: # Only update known keys
                 current_saved_config[key] = value
            else:
                 print(f"W: Ignoring unknown key '{key}' during config save.", file=sys.stderr)

        config_to_save = {
            'port': int(current_saved_config.get('port', 5000)),
            'enable_python_run': bool(current_saved_config.get('enable_python_run', False)),
            'enable_shell_run': bool(current_saved_config.get('enable_shell_run', False))
        }
        if not (1 <= config_to_save['port'] <= 65535):
            print(f"W: Invalid port {config_to_save['port']} during save, reverting to default 5000.", file=sys.stderr)
            config_to_save['port'] = 5000

        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_to_save, f, indent=4)
        print(f"Info: Configuration saved to '{CONFIG_FILE}'. Restart server for changes.", file=sys.stderr)
        return True, config_to_save
    except (OSError, TypeError, ValueError) as e:
        print(f"E: Failed to save config file '{CONFIG_FILE}': {e}", file=sys.stderr)
        return False, None

def _is_git_repository(check_dir: Path) -> bool:
    """Checks if check_dir is a Git repository."""
    # Renamed to avoid conflict if imported elsewhere
    try:
        result = subprocess.run(['git', 'rev-parse', '--is-inside-work-tree'], capture_output=True, text=True, check=False, encoding='utf-8', cwd=check_dir, timeout=5)
        return result.returncode == 0 and result.stdout.strip() == 'true'
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return False

def initialize_config():
    """Loads config, parses args, determines effective settings."""
    print("--- Initializing Configuration ---", file=sys.stderr)
    file_config = load_config()

    parser = argparse.ArgumentParser(description='AI Code Capture Server', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-p', '--port', type=int, default=file_config['port'], help='Port number.')
    parser.add_argument('--shell', action='store_true', help='DANGEROUS: Enable shell script execution.')
    parser.add_argument('--enable-python-run', action='store_true', help='Enable Python script execution.')
    args = parser.parse_args()

    # Determine effective runtime settings
    effective_port = args.port
    # Command-line flags override config file values only if explicitly provided
    run_python = args.enable_python_run if '--enable-python-run' in sys.argv else file_config['enable_python_run']
    run_shell = args.shell if '--shell' in sys.argv else file_config['enable_shell_run']

    # Check Git status
    is_repo = _is_git_repository(SERVER_DIR)
    if not is_repo:
        print("Info: Not running inside a Git work tree or 'git' command failed.", file=sys.stderr)

    # Create directories if they don't exist
    os.makedirs(SAVE_FOLDER_PATH, exist_ok=True)
    os.makedirs(LOG_FOLDER_PATH, exist_ok=True)

    config = {
        'SERVER_PORT': effective_port,
        'SERVER_DIR': SERVER_DIR,
        'SAVE_FOLDER_PATH': SAVE_FOLDER_PATH,
        'LOG_FOLDER_PATH': LOG_FOLDER_PATH,
        'CONFIG_FILE': CONFIG_FILE,
        'THIS_SCRIPT_NAME': THIS_SCRIPT_NAME, # Pass this along
        'IS_REPO': is_repo,
        'AUTO_RUN_PYTHON_ON_SYNTAX_OK': run_python,
        'AUTO_RUN_SHELL_ON_SYNTAX_OK': run_shell,
        'loaded_file_config': file_config # Keep the original file content if needed
    }
    print(f"Effective Runtime Settings: Port={config['SERVER_PORT']}, PyRun={config['AUTO_RUN_PYTHON_ON_SYNTAX_OK']}, ShellRun={config['AUTO_RUN_SHELL_ON_SYNTAX_OK']}, Git={config['IS_REPO']}", file=sys.stderr)
    print("-" * 30, file=sys.stderr)
    return config
# @@FILENAME@@ config_manager.py