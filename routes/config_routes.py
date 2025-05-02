# @@FILENAME@@ routes/config_routes.py
from flask import Blueprint, jsonify, request, current_app # Added Blueprint import
import sys

config_bp = Blueprint('config_bp', __name__)

@config_bp.route('/update_config', methods=['POST'])
def update_config():
    """
    Updates the server_config.json file AND the current running state
    for auto-run flags. Port changes still require restart.
    """
    save_config_func = current_app.config['save_config_func']
    load_config_func = current_app.config['load_config_func']
    runtime_config = current_app.config['APP_CONFIG']

    if not request.is_json:
        return jsonify({'status': 'error', 'message': 'Request must be JSON'}), 400

    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'Empty JSON received'}), 400

    print(f"Received /update_config request data: {data}", file=sys.stderr)

    config_changes_for_file = {}
    runtime_updated = False
    port_change_requested = False
    valid_keys = ['auto_run_python', 'auto_run_shell', 'port']
    live_update_keys = ['auto_run_python', 'auto_run_shell'] # Keys affecting runtime directly

    for key in valid_keys:
        if key in data:
            req_value = data[key]
            # is_live_key = key in live_update_keys # Not currently used, but kept for clarity
            try:
                if key == 'port':
                    port_val = int(req_value)
                    if 1 <= port_val <= 65535:
                        config_changes_for_file[key] = port_val
                        # Check if this is different from the currently *running* port
                        if port_val != runtime_config['SERVER_PORT']:
                            port_change_requested = True
                    else:
                        print(f"W: Invalid value for '{key}'. Port out of range.", file=sys.stderr)
                        # Don't add invalid port to changes
                elif key in live_update_keys:
                    # Check type explicitly for booleans
                    if isinstance(req_value, bool):
                         config_changes_for_file[key] = req_value
                         # Check if this changes the current runtime state
                         if runtime_config[key] != req_value:
                              runtime_config[key] = req_value # Apply change immediately to runtime config
                              runtime_updated = True
                              print(f"RUNTIME update: {key} set to {req_value}.", file=sys.stderr)
                         else:
                              print(f"Info: Runtime value for {key} already {req_value}. No change applied.", file=sys.stderr)
                    else:
                        print(f"W: Invalid type for '{key}'. Expected JSON boolean.", file=sys.stderr)
                        # Don't add invalid type to changes
            except (ValueError, TypeError):
                print(f"W: Invalid value/type for '{key}'. Skipping.", file=sys.stderr)
                # Don't add invalid value/type to changes

    response_status = 'success' # Assume success unless save fails
    message = ""

    if config_changes_for_file:
        save_success, saved_data = save_config_func(config_changes_for_file)
        if save_success:
            message = "Server config saved. "
            if runtime_updated and not port_change_requested:
                message += "Auto-run setting applied immediately."
            elif port_change_requested:
                 message += "Restart server for port change to take effect."
            elif runtime_updated and port_change_requested: # Both changed
                message += "Auto-run setting applied immediately. Restart server for port change."
            else: # Only port saved, no runtime change or port change request affecting runtime
                message += "No immediate runtime settings changed by this update."
            # Return the config *as saved*
            return jsonify({'status': response_status, 'message': message, 'saved_config': saved_data })
        else:
            response_status = 'error'
            message = 'Failed to save config file.'
            return jsonify({'status': response_status, 'message': message}), 500
    else:
        # No valid changes were requested or applied
        message = 'No valid config changes requested or required.'
        # Return current config file content if no changes were made
        return jsonify({ 'status': response_status, 'message': message, 'current_config_file': load_config_func() })
