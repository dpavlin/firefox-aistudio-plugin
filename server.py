#!/usr/bin/env python3
# @@FILENAME@@ server.py

import sys
import threading
from flask import Flask
from flask_cors import CORS
import os # Import os for exception handling
import traceback # Import traceback

# Import configuration and route blueprints
import config_manager
from routes.status import status_bp
# from routes.config_routes import config_bp # REMOVED
from routes.submit import submit_bp

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
# REMOVED passing of config funcs


# Register Blueprints
app.register_blueprint(status_bp)
# app.register_blueprint(config_bp) # REMOVED
app.register_blueprint(submit_bp)


# --- Main Execution ---
if __name__ == '__main__':
    host_ip = '127.0.0.1'
    port_num = config['SERVER_PORT']

    print(f"--- AI Code Capture Server (Simplified Config) ---") # Updated Title
    # print(f"Config File Path: ... ") # REMOVED Config file info
    print("-" * 30)
    print(f"Effective RUNNING Settings:")
    print(f"  Host: {host_ip}")
    print(f"  Port: {port_num}")
    print(f"  Server CWD: {config['SERVER_DIR']}")
    print(f"  Save Dir:   ./{config['SAVE_FOLDER_PATH'].relative_to(config['SERVER_DIR'])}")
    print(f"  Git Repo:   {'YES' if config['IS_REPO'] else 'NO'}")
    print(f"  Py Auto-Run:  {'ENABLED (via --python flag)' if config['auto_run_python'] else 'DISABLED'}") # Updated Msg
    print(f"  Sh Auto-Run:  {'ENABLED (via --shell flag)' if config['auto_run_shell'] else 'DISABLED'}{' <-- DANGEROUS!' if config['auto_run_shell'] else ''}") # Updated Msg
    print("-" * 30)
    print(f"Starting Flask server on http://{host_ip}:{port_num}")
    print("Use Ctrl+C to stop the server.")
    print(f"NOTE: Auto-run controlled only by server startup flags.", file=sys.stderr)
    # Port changes msg remains relevant to the running process vs extension setting
    print(f"      Port changes require a server restart.", file=sys.stderr)
    print(f"      Execution output included in /submit_code response.", file=sys.stderr)
    print("--- Server ready ---", file=sys.stderr)

    try:
        # Use waitress or other production server in real deployment
        # For simplicity in development:
        app.run(host=host_ip, port=port_num, debug=False)
    except OSError as e:
        if "Address already in use" in str(e) or ("WinError" in str(e) and "10048" in str(e) and os.name == 'nt'): # More specific check
             print(f"\nE: Port {port_num} is already in use.", file=sys.stderr)
             print(f"   Stop the other process or use '-p <new_port>'", file=sys.stderr)
             sys.exit(1)
        else:
             print(f"\nE: Failed to start server: {e}", file=sys.stderr)
             sys.exit(1)
    except KeyboardInterrupt:
        print("\n--- Server shutting down ---", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"\nE: Unexpected error during startup: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr) # Print traceback for unexpected errors
        sys.exit(1)

