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
    # Use the name of the main server script
    THIS_SCRIPT_NAME = Path(sys.argv[0]).name
except IndexError:
    THIS_SCRIPT_NAME = "server.py" # Fallback

def load_config():
    """Loads config from JSON file, returns defaults if not found/invalid."""
    # Use lowercase keys consistent with runtime config
    defaults = {
        'port': 5000,
        'auto_run_python': False, # Renamed key
        'auto_run_shell': False    # Renamed key
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
            # Map old keys if necessary, preferring new keys
            py_run_val = config.get('auto_run_python', config.get('enable_python_run', defaults['auto_run_python']))
            sh_run_val = config.get('auto_run_shell', config.get('enable_shell_run', defaults['auto_run_shell']))
            try: loaded_config['auto_run_python'] = bool(py_run_val)
            except TypeError: loaded_config['auto_run_python'] = defaults['auto_run_python']
            try: loaded_config['auto_run_shell'] = bool(sh_run_val)
            except TypeError: loaded_config['auto_run_shell'] = defaults['auto_run_shell']
            print(f"Info: Loaded config from '{CONFIG_FILE}': {loaded_config}", file=sys.stderr)
            return loaded_config
    except (json.JSONDecodeError, OSError) as e:
        print(f"W: Error reading config file '{CONFIG_FILE}': {e}. Using defaults.", file=sys.stderr)
        return defaults.copy()

def save_config(config_data):
    """Saves specific config data to JSON file, preserving other keys."""
    try:
        # Read the current content of the file first to preserve unknown keys
        current_on_disk = {}
        if CONFIG_FILE.is_file():
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    current_on_disk = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                 print(f"W: Could not read existing config '{CONFIG_FILE}' during save: {e}. Overwriting might occur.", file=sys.stderr)
                 current_on_disk = {} # Start fresh if read fails

        # Use the current runtime defaults/loaded values as a base
        current_saved_config = load_config()
        # Merge with unknown keys from disk file if they exist
        for key, value in current_on_disk.items():
            if key not in current_saved_config:
                current_saved_config[key] = value

        # Update with the explicitly passed changes
        valid_keys_to_save = ['port', 'auto_run_python', 'auto_run_shell']
        for key, value in config_data.items():
            if key in valid_keys_to_save:
                 current_saved_config[key] = value
            # Optional: Map old keys if received from older popup version?
            # elif key == 'enable_python_run': current_saved_config['auto_run_python'] = value
            # elif key == 'enable_shell_run': current_saved_config['auto_run_shell'] = value
            else: print(f"W: Ignoring unknown key '{key}' during config save.", file=sys.stderr)

        # Ensure types before saving - Build the final dict to save
        config_to_save = {}
        for key, value in current_saved_config.items():
             if key == 'port':
                 try:
                     port_val = int(value)
                     if 1 <= port_val <= 65535: config_to_save[key] = port_val
                     else:
                         print(f"W: Invalid port {port_val} during save, reverting to default 5000.", file=sys.stderr)
                         config_to_save[key] = 5000
                 except (ValueError, TypeError): config_to_save[key] = 5000
             elif key == 'auto_run_python': config_to_save[key] = bool(value)
             elif key == 'auto_run_shell': config_to_save[key] = bool(value)
             else: config_to_save[key] = value # Preserve unknown keys

        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_to_save, f, indent=4)
        print(f"Info: Configuration saved to '{CONFIG_FILE}'.", file=sys.stderr)
        return True, config_to_save # Return the actually saved config
    except (OSError, TypeError, ValueError) as e:
        print(f"E: Failed to save config file '{CONFIG_FILE}': {e}", file=sys.stderr)
        return False, None

def _is_git_repository(check_dir: Path) -> bool:
    """Checks if the given directory is inside a Git work tree."""
    if not shutil.which("git"): # Check if git command exists first
        print("W: 'git' command not found. Cannot check Git repository status.", file=sys.stderr)
        return False
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--is-inside-work-tree'],
            capture_output=True, text=True, check=False, encoding='utf-8',
            cwd=check_dir, timeout=5
        )
        return result.returncode == 0 and result.stdout.strip() == 'true'
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
         print(f"W: Error running 'git rev-parse' in {check_dir}: {e}", file=sys.stderr)
         return False

# Need to import shutil for _is_git_repository check
import shutil

def initialize_config():
    """Loads config, parses args, determines effective settings."""
    print("--- Initializing Configuration ---", file=sys.stderr)
    file_config = load_config()

    parser = argparse.ArgumentParser(description='AI Code Capture Server', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    # Default port comes from file/defaults FIRST, then override by arg
    parser.add_argument('-p', '--port', type=int, default=None, help=f"Port number (default: {file_config['port']} from config or 5000).")
    # Arg flags only enable if specified, otherwise use config file value
    parser.add_argument('--shell', action='store_true', help='DANGEROUS: Enable shell script execution (overrides config).')
    parser.add_argument('--enable-python-run', action='store_true', help='Enable Python script execution (overrides config).')
    args = parser.parse_args()

    # Determine effective settings
    effective_port = args.port if args.port is not None else file_config['port']
    run_python = args.enable_python_run if '--enable-python-run' in sys.argv else file_config['auto_run_python']
    run_shell = args.shell if '--shell' in sys.argv else file_config['auto_run_shell']


    # Validate port range
    if not (1 <= effective_port <= 65535):
        print(f"W: Invalid port {effective_port} specified. Reverting to default 5000.", file=sys.stderr)
        effective_port = 5000


    is_repo = _is_git_repository(SERVER_DIR)
    if not is_repo and (run_shell or run_python):
         print("Info: Not running inside a Git work tree or 'git' command failed.", file=sys.stderr)
    elif is_repo:
         print("Info: Running inside a Git work tree.", file=sys.stderr)

    # Ensure directories exist
    try:
        os.makedirs(SAVE_FOLDER_PATH, exist_ok=True)
        os.makedirs(LOG_FOLDER_PATH, exist_ok=True)
    except OSError as e:
        print(f"E: Failed to create necessary directories ({SAVE_FOLDER_PATH}, {LOG_FOLDER_PATH}): {e}", file=sys.stderr)
        sys.exit(1)


    # Store effective RUNTIME settings using uppercase for constants if preferred,
    # but KEEP lowercase keys ('auto_run_python', 'auto_run_shell') consistent
    # with how they are accessed and updated via the config routes/popup.
    runtime_config = {
        'SERVER_PORT': effective_port,
        'SERVER_DIR': SERVER_DIR,
        'SAVE_FOLDER_PATH': SAVE_FOLDER_PATH,
        'LOG_FOLDER_PATH': LOG_FOLDER_PATH,
        'CONFIG_FILE': CONFIG_FILE,
        'THIS_SCRIPT_NAME': THIS_SCRIPT_NAME,
        'IS_REPO': is_repo,
        'auto_run_python': run_python, # Use lowercase key matching config file/updates
        'auto_run_shell': run_shell,    # Use lowercase key matching config file/updates
        'loaded_file_config': file_config # Keep original loaded content if needed for comparison etc.
    }
    print(f"Runtime Config Initialized: Port={runtime_config['SERVER_PORT']}, PyRun={runtime_config['auto_run_python']}, ShellRun={runtime_config['auto_run_shell']}, Git={runtime_config['IS_REPO']}", file=sys.stderr)
    print("-" * 30, file=sys.stderr)
    return runtime_config
