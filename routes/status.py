# @@FILENAME@@ routes/status.py
from flask import Blueprint, jsonify, current_app
import sys # <-- Import sys module

status_bp = Blueprint('status_bp', __name__)

@status_bp.route('/status', methods=['GET'])
def get_status():
    """Returns current server status and RUNNING configuration."""
    config = current_app.config['APP_CONFIG'] # Access config passed during registration
    load_config_func = current_app.config['load_config_func'] # Get function to load saved config

    status_data = {
        'status': 'running',
        'working_directory': str(config['SERVER_DIR']),
        'save_directory': str(config['SAVE_FOLDER_PATH'].relative_to(config['SERVER_DIR'])),
        'log_directory': str(config['LOG_FOLDER_PATH'].relative_to(config['SERVER_DIR'])),
        'is_git_repo': config['IS_REPO'],
        'port': config['SERVER_PORT'], # The port this instance is *actually* running on
        # Use lowercase keys consistent with runtime updates
        'auto_run_python': config['auto_run_python'],
        'auto_run_shell': config['auto_run_shell'],
        'config_file_exists': config['CONFIG_FILE'].is_file(),
        'config_file_content': load_config_func() # Load the *saved* state from the file
    }
    return jsonify(status_data)

@status_bp.route('/test_connection', methods=['GET'])
def test_connection():
    """Simple endpoint to test if the server is running, returns status."""
    print("Received /test_connection request", file=sys.stderr)
    # Reuse the status endpoint logic to return current state
    # The caller (popup) uses this to verify connectivity to a specific port
    # and to get the current state of *that* running server instance.
    return get_status()
