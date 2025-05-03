# @@FILENAME@@ config_manager.py
import argparse
# import json # REMOVED
import sys
import os
import subprocess
from pathlib import Path

# CONFIG_FILE = Path.cwd().resolve() / 'server_config.json' # REMOVED
SERVER_DIR = Path.cwd().resolve()
SAVE_FOLDER = 'received_codes'
SAVE_FOLDER_PATH = SERVER_DIR / SAVE_FOLDER

try:
    THIS_SCRIPT_NAME = Path(sys.argv[0]).name
except IndexError:
    THIS_SCRIPT_NAME = "server.py"

# REMOVED load_config function
# REMOVED save_config function

def _is_git_repository(check_dir: Path) -> bool:
    try:
        result = subprocess.run(['git', 'rev-parse', '--is-inside-work-tree'], capture_output=True, text=True, check=False, encoding='utf-8', cwd=check_dir, timeout=5)
        return result.returncode == 0 and result.stdout.strip() == 'true'
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return False

def initialize_config():
    """Parses args, determines effective settings. No config file used."""
    print("--- Initializing Configuration (Args Only) ---", file=sys.stderr)
    # file_config = load_config() # REMOVED

    DEFAULT_SERVER_PORT = 5000 # Define default here

    parser = argparse.ArgumentParser(description='AI Code Capture Server', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    # Default port is now hardcoded
    parser.add_argument('-p', '--port', type=int, default=DEFAULT_SERVER_PORT, help=f'Port number (default: {DEFAULT_SERVER_PORT}).')
    # Auto-run flags
    parser.add_argument('--shell', action='store_true', help='DANGEROUS: Enable shell script execution.')
    # CHANGE 1: Renamed flag
    parser.add_argument('--python', action='store_true', help='Enable Python script execution.')
    args = parser.parse_args()

    effective_port = args.port
    # Auto-run flags are solely determined by command-line arguments
    # CHANGE 2: Use the new flag name
    run_python = args.python
    run_shell = args.shell

    is_repo = _is_git_repository(SERVER_DIR)
    if not is_repo: print("Info: Not running inside a Git work tree or 'git' command failed.", file=sys.stderr)

    os.makedirs(SAVE_FOLDER_PATH, exist_ok=True)

    # Store effective RUNTIME settings
    runtime_config = {
        'SERVER_PORT': effective_port,
        'SERVER_DIR': SERVER_DIR,
        'SAVE_FOLDER_PATH': SAVE_FOLDER_PATH,
        # 'CONFIG_FILE': CONFIG_FILE, # REMOVED
        'THIS_SCRIPT_NAME': THIS_SCRIPT_NAME,
        'IS_REPO': is_repo,
        'auto_run_python': run_python,
        'auto_run_shell': run_shell,
        # 'loaded_file_config': None # REMOVED
    }
    print(f"Effective Runtime Settings: Port={runtime_config['SERVER_PORT']}, PyRun={runtime_config['auto_run_python']}, ShellRun={runtime_config['auto_run_shell']}, Git={runtime_config['IS_REPO']}", file=sys.stderr)
    print("-" * 30, file=sys.stderr)
    return runtime_config
