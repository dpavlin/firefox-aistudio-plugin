# @@FILENAME@@ routes/config_routes.py
from flask import Blueprint, jsonify, request, current_app
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
    # Get the mutable runtime config dictionary
    runtime_config = current_app.config['APP_CONFIG']

    if not request.is_json:
        return jsonify({'status': 'error', 'message': 'Request must be JSON'}), 400

    data = request.get_json()
    print(f"Received /update_config request data: {data}", file=sys.stderr)

    config_changes_for_file = {}
    runtime_updated = False
    port_changed = False
    # Use lowercase keys consistently
    valid_keys = ['auto_run_python', 'auto_run_shell', 'port']
    live_update_keys = ['auto_run_python', 'auto_run_shell'] # Keys that can be updated live

    for key in valid_keys:
        if key in data:
            req_value = data[key]
            is_live_key = key in live_update_keys
            try:
                if key == 'port':
                    port_val = int(req_value)
                    if 1 <= port_val <= 65535:
                        # Only update file, runtime port cannot change
                        config_changes_for_file[key] = port_val
                        if port_val != runtime_config['SERVER_PORT']:
                            port_changed = True
                        print(f"Config update: preparing to set {key} to {port_val} in file.", file=sys.stderr)
                    else: print(f"W: Invalid value for '{key}'. Port out of range.", file=sys.stderr)
                elif key in live_update_keys:
                    if isinstance(req_value, bool):
                         config_changes_for_file[key] = req_value # Prepare for file save
                         # *** UPDATE LIVE RUNTIME CONFIG ***
                         if runtime_config[key] != req_value:
                              runtime_config[key] = req_value
                              runtime_updated = True
                              print(f"RUNTIME update: {key} set to {req_value}.", file=sys.stderr)
                         else:
                              print(f"Info: Runtime value for {key} already {req_value}.", file=sys.stderr)
                    else: print(f"W: Invalid type for '{key}'. Expected JSON boolean.", file=sys.stderr)
            except (ValueError, TypeError): print(f"W: Invalid value/type for '{key}'.", file=sys.stderr)

    # Save changes to the config file if any valid changes were received
    if config_changes_for_file:
        save_success, saved_data = save_config_func(config_changes_for_file)
        if save_success:
            message = "Server config updated. "
            if runtime_updated and not port_changed:
                message += "Auto-run setting applied immediately."
            elif port_changed:
                message += "Restart server for port change to take effect."
            else: # only file updated, no runtime change
                message += "No runtime settings changed."

            return jsonify({
                'status': 'success',
                'message': message,
                'saved_config': saved_data # Show what was actually saved to file
            })
        else:
            # Revert runtime changes if save failed? Maybe safer not to.
            return jsonify({'status': 'error', 'message': 'Failed to save config file.'}), 500
    else:
        return jsonify({
            'status': 'success',
            'message': 'No valid config changes requested. Config file not modified.',
            'current_config_file': load_config_func()
        })
# @@FILENAME@@ routes/config_routes.py