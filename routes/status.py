from flask import Blueprint, jsonify, current_app
import sys

status_bp = Blueprint('status_bp', __name__)

@status_bp.route('/status', methods=['GET'])
def get_status():
    """Returns current server status and RUNNING configuration."""
    config = current_app.config['APP_CONFIG'] # Access config passed during registration
    status_data = {
        'status': 'running',
        'working_directory': str(config['SERVER_DIR']),
        'save_directory': str(config['SAVE_FOLDER_PATH'].relative_to(config['SERVER_DIR'])),
        # 'log_directory': str(config['LOG_FOLDER_PATH'].relative_to(config['SERVER_DIR'])), # REMOVED
        'is_git_repo': config['IS_REPO'],
        'port': config['SERVER_PORT'],
        'auto_run_python': config['auto_run_python'], # Still report runtime value (from flags)
        'auto_run_shell': config['auto_run_shell'],    # Still report runtime value (from flags)
        'config_file_exists': config['CONFIG_FILE'].is_file(),
        'config_file_content': current_app.config['load_config_func']() # Load current saved config (port only)
    }
    return jsonify(status_data)

@status_bp.route('/test_connection', methods=['GET'])
def test_connection():
    """Simple endpoint to test if the server is running, returns status."""
    print("Received /test_connection request", file=sys.stderr)
    return get_status() # Reuse the status endpoint logic
