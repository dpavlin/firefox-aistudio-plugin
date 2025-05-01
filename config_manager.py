# ... (imports) ...

CONFIG_FILE = Path.cwd().resolve() / 'server_config.json'
SERVER_DIR = Path.cwd().resolve()
# ... (other paths) ...
try: THIS_SCRIPT_NAME = Path(sys.argv[0]).name
except IndexError: THIS_SCRIPT_NAME = "server.py"

def load_config():
    """Loads config from JSON file, returns defaults if not found/invalid."""
    defaults = {
        'port': 5000,
        'auto_run_python': False,
        'auto_run_shell': False,
        'batch_idle_timeout': 1.0 # Default idle time in seconds
    }
    if not CONFIG_FILE.is_file():
        # ... (existing no file logic) ...
        return defaults.copy()
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            loaded_config = defaults.copy()
            # ... (loading port, auto_run flags) ...
            try:
                timeout = float(config.get('batch_idle_timeout', defaults['batch_idle_timeout']))
                loaded_config['batch_idle_timeout'] = max(0.1, timeout) # Ensure minimum timeout
            except (ValueError, TypeError):
                loaded_config['batch_idle_timeout'] = defaults['batch_idle_timeout']

            print(f"Info: Loaded config from '{CONFIG_FILE}': {loaded_config}", file=sys.stderr)
            return loaded_config
    except (json.JSONDecodeError, OSError) as e:
        # ... (existing error logic) ...
        return defaults.copy()

def save_config(config_data):
    """Saves specific config data to JSON file, preserving other keys."""
    try:
        current_saved_config = load_config()
        valid_keys_to_save = ['port', 'auto_run_python', 'auto_run_shell', 'batch_idle_timeout'] # Add new key
        for key, value in config_data.items():
             if key in valid_keys_to_save:
                 current_saved_config[key] = value
             # ... (handle old keys if needed) ...

        # Ensure types before saving
        config_to_save = {
            'port': int(current_saved_config.get('port', 5000)),
            'auto_run_python': bool(current_saved_config.get('auto_run_python', False)),
            'auto_run_shell': bool(current_saved_config.get('auto_run_shell', False)),
            'batch_idle_timeout': float(current_saved_config.get('batch_idle_timeout', 1.0))
        }
        if not (1 <= config_to_save['port'] <= 65535): config_to_save['port'] = 5000
        if config_to_save['batch_idle_timeout'] < 0.1: config_to_save['batch_idle_timeout'] = 0.1 # Enforce min on save

        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_to_save, f, indent=4)
        print(f"Info: Configuration saved to '{CONFIG_FILE}'.", file=sys.stderr)
        return True, config_to_save
    except (OSError, TypeError, ValueError) as e:
        print(f"E: Failed to save config file '{CONFIG_FILE}': {e}", file=sys.stderr)
        return False, None

def _is_git_repository(check_dir: Path) -> bool: # ... (unchanged) ...
    try:
        result = subprocess.run(['git', 'rev-parse', '--is-inside-work-tree'], capture_output=True, text=True, check=False, encoding='utf-8', cwd=check_dir, timeout=5)
        return result.returncode == 0 and result.stdout.strip() == 'true'
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return False

def initialize_config():
    """Loads config, parses args, determines effective settings."""
    # ... (load file config, setup parser) ...
    file_config = load_config()

    parser = argparse.ArgumentParser(description='AI Code Capture Server', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-p', '--port', type=int, default=file_config['port'], help='Port number.')
    parser.add_argument('--shell', action='store_true', help='DANGEROUS: Enable shell script execution.')
    parser.add_argument('--enable-python-run', action='store_true', help='Enable Python script execution.')
    # Add arg for timeout, defaulting to file config
    parser.add_argument('--idle-timeout', type=float, default=file_config['batch_idle_timeout'], help='Idle time (sec) before batch processing.')
    args = parser.parse_args()

    # Determine effective runtime settings
    effective_port = args.port
    run_python = args.enable_python_run if '--enable-python-run' in sys.argv else file_config['auto_run_python']
    run_shell = args.shell if '--shell' in sys.argv else file_config['auto_run_shell']
    idle_timeout = args.idle_timeout if '--idle-timeout' in sys.argv else file_config['batch_idle_timeout']
    idle_timeout = max(0.1, idle_timeout) # Ensure minimum

    is_repo = _is_git_repository(SERVER_DIR)
    # ... (create directories) ...
    os.makedirs(SAVE_FOLDER_PATH, exist_ok=True)
    os.makedirs(LOG_FOLDER_PATH, exist_ok=True)

    # Store effective RUNTIME settings
    runtime_config = {
        'SERVER_PORT': effective_port,
        'SERVER_DIR': SERVER_DIR,
        'SAVE_FOLDER_PATH': SAVE_FOLDER_PATH,
        'LOG_FOLDER_PATH': LOG_FOLDER_PATH,
        'CONFIG_FILE': CONFIG_FILE,
        'THIS_SCRIPT_NAME': THIS_SCRIPT_NAME,
        'IS_REPO': is_repo,
        'auto_run_python': run_python,
        'auto_run_shell': run_shell,
        'batch_idle_timeout': idle_timeout, # Store effective timeout
        'loaded_file_config': file_config
    }
    # ... (print effective settings) ...
    print(f"Effective Runtime Settings: Port={runtime_config['SERVER_PORT']}, PyRun={runtime_config['auto_run_python']}, ShellRun={runtime_config['auto_run_shell']}, Git={runtime_config['IS_REPO']}, IdleTimeout={runtime_config['batch_idle_timeout']}s", file=sys.stderr)
    print("-" * 30, file=sys.stderr)
    return runtime_config
# @@FILENAME@@ config_manager.py