# @@FILENAME@@ routes/config_routes.py
from flask import Blueprint, jsonify, request, current_app # Added Blueprint import
import sys

config_bp = Blueprint('config_bp', __name__)

@config_bp.route('/update_config', methods=['POST'])
def update_config():
    """
    Updates the server_config.json file (now only for port).
    Port changes still require restart. Auto-run is NOT changed here.
    """
    save_config_func = current_app.config['save_config_func']
    load_config_func = current_app.config['load_config_func']
    runtime_config = current_app.config['APP_CONFIG'] # Current runtime config

    if not request.is_json:
        return jsonify({'status': 'error', 'message': 'Request must be JSON'}), 400

    data = request.get_json()
    print(f"Received /update_config request data: {data}", file=sys.stderr)

    config_changes_for_file = {}
    # runtime_updated = False # No longer relevant for auto-run
    port_changed = False
    valid_keys = ['port'] # Only port is valid now
    # live_update_keys = [] # No live update keys

    for key in valid_keys:
        if key in data:
            req_value = data[key]
            # is_live_key = False # No live keys
            try:
                if key == 'port':
                    port_val = int(req_value)
                    if 1 <= port_val <= 65535:
                        config_changes_for_file[key] = port_val
                        # Check against runtime config to see if it's actually a change
                        if port_val != runtime_config['SERVER_PORT']:
                             port_changed = True
                             print(f"Info: Port change requested to {port_val} (currently running on {runtime_config['SERVER_PORT']}). Will save to config.", file=sys.stderr)
                        else:
                             print(f"Info: Requested port {port_val} matches current runtime port. Saving anyway.", file=sys.stderr)
                    else:
                        print(f"W: Invalid value for '{key}'. Port out of range.", file=sys.stderr)
                # REMOVED logic for auto_run_python/shell
            except (ValueError, TypeError):
                 print(f"W: Invalid value/type for '{key}'.", file=sys.stderr)

    if config_changes_for_file:
        save_success, saved_data = save_config_func(config_changes_for_file)
        if save_success:
            message = "Server config updated. "
            # if runtime_updated and not port_changed: message += "Auto-run setting applied immediately." # Removed
            if port_changed:
                message += "Restart server for port change to take effect."
            else:
                message += "No runtime settings changed (port matches)." # Modified message
            return jsonify({'status': 'success', 'message': message, 'saved_config': saved_data })
        else:
             return jsonify({'status': 'error', 'message': 'Failed to save config file.'}), 500
    else:
        # Load current config if no valid changes were requested
        return jsonify({ 'status': 'info', 'message': 'No valid config changes requested.', 'current_config_file': load_config_func() }) # Changed status to info
