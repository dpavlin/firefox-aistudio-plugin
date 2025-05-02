#!/usr/bin/env python3
# @@FILENAME@@ server.py

import sys
import threading
import os # Needed for exception check
from flask import Flask
from flask_cors import CORS

# Import configuration and route blueprints
import config_manager
from routes.status import status_bp
from routes.config_routes import config_bp # Renamed to avoid conflict
from routes.submit import submit_bp
from routes.logs import logs_bp

# Initialize configuration (loads from file, parses args)
config = config_manager.initialize_config()

# Create Flask app
app = Flask(__name__)

# Configure CORS - Allow all origins for simplicity in development
CORS(app, resources={r"/*": {"origins": "*"}})

# Create a shared lock (can be accessed via app config)
request_lock = threading.Lock()
print("Request lock initialized.", file=sys.stderr)

# Store config and lock in Flask app config for access in blueprints
app.config['APP_CONFIG'] = config
app.config['REQUEST_LOCK'] = request_lock
# Pass config manager functions if needed by routes (like config update)
app.config['load_config_func'] = config_manager.load_config
app.config['save_config_func'] = config_manager.save_config


# Register Blueprints
app.register_blueprint(status_bp)
app.register_blueprint(config_bp)
app.register_blueprint(submit_bp)
app.register_blueprint(logs_bp)


# --- Main Execution ---
if __name__ == '__main__':
    host_ip = '127.0.0.1'
    port_num = config['SERVER_PORT']

    print(f"--- AI Code Capture Server ---")
    print(f"Config File Path: '{config['CONFIG_FILE']}' ({'Exists' if config['CONFIG_FILE'].is_file() else 'Not Found'})")
    # print(f"  Config File Content: {config['loaded_file_config']}") # Might be too verbose
    print("-" * 30)
    # This block prints the effective RUNTIME settings using the lowercase keys
    print(f"Effective RUNNING Settings:")
    print(f"  Host: {host_ip}")
    print(f"  Port: {port_num}")
    print(f"  Server CWD: {config['SERVER_DIR']}")
    print(f"  Save Dir:   ./{config['SAVE_FOLDER_PATH'].relative_to(config['SERVER_DIR'])}")
    print(f"  Log Dir:    ./{config['LOG_FOLDER_PATH'].relative_to(config['SERVER_DIR'])}")
    print(f"  Git Repo:   {'YES' if config['IS_REPO'] else 'NO'}")
    print(f"  Py Auto-Run:  {'ENABLED' if config['auto_run_python'] else 'DISABLED'}") # Lowercase
    print(f"  Sh Auto-Run:  {'ENABLED' if config['auto_run_shell'] else 'DISABLED'}{' <-- DANGEROUS!' if config['auto_run_shell'] else ''}") # Lowercase
    print("-" * 30)
    print(f"Starting Flask server on http://{host_ip}:{port_num}")
    print("Use Ctrl+C to stop the server.")
    print(f"NOTE: Auto-run settings changed via popup apply immediately.", file=sys.stderr) # Updated Note
    print(f"      Port changes require a server restart for that specific port.", file=sys.stderr)
    print("--- Server ready ---", file=sys.stderr)

    try:
        app.run(host=host_ip, port=port_num, debug=False)
    except OSError as e:
        if "Address already in use" in str(e) or ("WinError 10048" in str(e) and os.name == 'nt'):
            print(f"\nE: Port {port_num} is already in use.", file=sys.stderr)
            print(f"   Stop the other process or use '-p <new_port>'", file=sys.stderr)
            sys.exit(1)
        else: print(f"\nE: Failed to start server: {e}", file=sys.stderr); sys.exit(1)
    except KeyboardInterrupt: print("\n--- Server shutting down ---", file=sys.stderr); sys.exit(0)
    except Exception as e: print(f"\nE: Unexpected error during startup: {e}", file=sys.stderr); sys.exit(1)

