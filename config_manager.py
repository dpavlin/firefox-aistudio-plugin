import argparse
import json
import sys
import os
import subprocess
from pathlib import Path

CONFIG_FILE = Path.cwd().resolve() / 'server_config.json'
SERVER_DIR = Path.cwd().resolve() # Define SERVER_DIR here
SAVE_FOLDER = 'received_codes'
# LOG_FOLDER = 'logs' # REMOVED
SAVE_FOLDER_PATH = SERVER_DIR / SAVE_FOLDER
# LOG_FOLDER_PATH = SERVER_DIR / LOG_FOLDER # REMOVED

try:
    THIS_SCRIPT_NAME = Path(sys.argv[0]).name
except IndexError:
    THIS_SCRIPT_NAME = "server.py"

def load_config():
    """Loads config from JSON file (now only port), returns defaults if not found/invalid."""
    defaults = {
        'port': 5000,
        # 'auto_run_python': False, # REMOVED from file config
        # 'auto_run_shell': False     # REMOVED from file config
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

            # REMOVED auto-run loading logic
            print(f"Info: Loaded config from '{CONFIG_FILE}': {loaded_config}", file=sys.stderr)
            return loaded_config
    except (json.JSONDecodeError, OSError) as e:
        print(f"W: Error reading config file '{CONFIG_FILE}': {e}. Using defaults.", file=sys.stderr)
        return defaults.copy()

def save_config(config_data):
    """Saves specific config data (now only port) to JSON file."""
    try:
        current_saved_config = load_config() # Load existing to preserve unknown keys potentially
        # Only update keys that are explicitly passed and known
        valid_keys_to_save = ['port'] # Only port is saved now
        for key, value in config_data.items():
            if key in valid_keys_to_save:
                 current_saved_config[key] = value
            else:
                 print(f"W: Ignoring unknown key '{key}' during config save.", file=sys.stderr)

        # Ensure types before saving
        config_to_save = {
            'port': int(current_saved_config.get('port', 5000)),
            # REMOVED auto-run saving logic
        }
        if not (1 <= config_to_save['port'] <= 65535):
            print(f"W: Invalid port {config_to_save['port']} during save, reverting to default 5000.", file=sys.stderr)
            config_to_save['port'] = 5000

        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_to_save, f, indent=4)
        print(f"Info: Configuration saved to '{CONFIG_FILE}'.", file=sys.stderr)
        return True, config_to_save
    except (OSError, TypeError, ValueError) as e:
        print(f"E: Failed to save config file '{CONFIG_FILE}': {e}", file=sys.stderr)
        return False, None

def _is_git_repository(check_dir: Path) -> bool:
    try:
        result = subprocess.run(['git', 'rev-parse', '--is-inside-work-tree'], capture_output=True, text=True, check=False, encoding='utf-8', cwd=check_dir, timeout=5)
        return result.returncode == 0 and result.stdout.strip() == 'true'
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return False

def initialize_config():
    """Loads config, parses args, determines effective settings."""
    print("--- Initializing Configuration ---", file=sys.stderr)
    file_config = load_config() # Only contains port now

    parser = argparse.ArgumentParser(description='AI Code Capture Server', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    # Default port now comes from file_config (which itself defaults to 5000)
    parser.add_argument('-p', '--port', type=int, default=file_config['port'], help='Port number.')
    # Auto-run flags: default action is False
    parser.add_argument('--shell', action='store_true', help='DANGEROUS: Enable shell script execution.')
    parser.add_argument('--enable-python-run', action='store_true', help='Enable Python script execution.')
    args = parser.parse_args()

    effective_port = args.port
    # Auto-run flags are now SOLELY determined by command-line arguments
    run_python = args.enable_python_run
    run_shell = args.shell

    is_repo = _is_git_repository(SERVER_DIR)
    if not is_repo: print("Info: Not running inside a Git work tree or 'git' command failed.", file=sys.stderr)

    os.makedirs(SAVE_FOLDER_PATH, exist_ok=True)
    # os.makedirs(LOG_FOLDER_PATH, exist_ok=True) # REMOVED

    # Store effective RUNTIME settings
    runtime_config = {
        'SERVER_PORT': effective_port,
        'SERVER_DIR': SERVER_DIR,
        'SAVE_FOLDER_PATH': SAVE_FOLDER_PATH,
        # 'LOG_FOLDER_PATH': LOG_FOLDER_PATH, # REMOVED
        'CONFIG_FILE': CONFIG_FILE,
        'THIS_SCRIPT_NAME': THIS_SCRIPT_NAME,
        'IS_REPO': is_repo,
        'auto_run_python': run_python, # Directly from args
        'auto_run_shell': run_shell,    # Directly from args
        'loaded_file_config': file_config # Keep original loaded content (port only)
    }
    print(f"Effective Runtime Settings: Port={runtime_config['SERVER_PORT']}, PyRun={runtime_config['auto_run_python']}, ShellRun={runtime_config['auto_run_shell']}, Git={runtime_config['IS_REPO']}", file=sys.stderr)
    print("-" * 30, file=sys.stderr)
    return runtime_config
