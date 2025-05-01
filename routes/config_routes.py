# @@FILENAME@@ routes/config_routes.py
from flask import Blueprint, jsonify, request, current_app
import sys

config_bp = Blueprint('config_bp', __name__)

@config_bp.route('/update_config', methods=['POST'])
def update_config():
    """
    Updates the server_config.json file with settings from the request.
    Does NOT dynamically update the running server state. Requires restart.
    """
    save_config_func = current_app.config['save_config_func']
    load_config_func = current_app.config['load_config_func']
    config = current_app.config['APP_CONFIG'] # Access existing config info if needed

    if not request.is_json:
        return jsonify({'status': 'error', 'message': 'Request must be JSON'}), 400

    data = request.get_json()
    print(f"Received /update_config request data: {data}", file=sys.stderr)

    config_changes = {}
    updated = False
    valid_keys = ['enable_python_run', 'enable_shell_run', 'port']

    for key in valid_keys:
        if key in data:
            req_value = data[key]
            try:
                if key == 'port':
                    port_val = int(req_value)
                    if 1 <= port_val <= 65535:
                        config_changes[key] = port_val; updated = True
                    else: print(f"W: Invalid value for '{key}'. Port out of range.", file=sys.stderr)
                elif key in ['enable_python_run', 'enable_shell_run']:
                    if isinstance(req_value, bool):
                         config_changes[key] = req_value; updated = True
                    else: print(f"W: Invalid type for '{key}'. Expected JSON boolean.", file=sys.stderr)
            except (ValueError, TypeError): print(f"W: Invalid value/type for '{key}'.", file=sys.stderr)

    if updated:
        # Use the save_config function passed via app config
        save_success, saved_data = save_config_func(config_changes)
        if save_success:
            return jsonify({
                'status': 'success',
                'message': f'Config saved to {config["CONFIG_FILE"].name}. Restart server for changes.',
                'saved_config': saved_data
            })
        else:
            return jsonify({'status': 'error', 'message': 'Failed to save config file.'}), 500
    else:
        return jsonify({
            'status': 'success',
            'message': 'No valid changes requested. Config file not modified.',
            'current_config_file': load_config_func()
        })
# @@FILENAME@@ routes/config_routes.py