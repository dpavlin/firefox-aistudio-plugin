# ... (keep all existing imports and helper functions) ...

# --- Route Definitions ---

@app.route('/status', methods=['GET'])
def get_status():
    # ... (keep existing implementation) ...
    status_data = {
        'status': 'running',
        'working_directory': str(SERVER_DIR),
        'save_directory': str(SAVE_FOLDER_PATH.relative_to(SERVER_DIR)),
        'log_directory': str(LOG_FOLDER_PATH.relative_to(SERVER_DIR)),
        'is_git_repo': IS_REPO,
        'port': SERVER_PORT,
        'auto_run_python': AUTO_RUN_PYTHON_ON_SYNTAX_OK, # Running state
        'auto_run_shell': AUTO_RUN_SHELL_ON_SYNTAX_OK,    # Running state
        'config_file_exists': CONFIG_FILE.is_file(),
        'config_file_content': load_config() # Saved state
    }
    return jsonify(status_data)

@app.route('/update_config', methods=['POST'])
def update_config():
    # ... (keep existing implementation) ...
    # This route modifies the config *file*, requiring a server restart.
    # Response message already includes this information.
    if not request.is_json: return jsonify({'status': 'error', 'message': 'Request must be JSON'}), 400
    data = request.get_json(); print(f"Received /update_config request data: {data}", file=sys.stderr)
    config_changes = {}; updated = False; valid_keys = ['enable_python_run', 'enable_shell_run', 'port']
    for key in valid_keys:
        if key in data:
            req_value = data[key]
            try:
                if key == 'port':
                    port_val = int(req_value)
                    if 1 <= port_val <= 65535: config_changes[key] = port_val; updated = True; print(f"Config update: preparing to set {key} to {port_val} in file.", file=sys.stderr)
                    else: print(f"W: Invalid value for '{key}' in request: {req_value}. Port out of range.", file=sys.stderr)
                elif key in ['enable_python_run', 'enable_shell_run']:
                    if isinstance(req_value, bool): config_changes[key] = req_value; updated = True; print(f"Config update: preparing to set {key} to {req_value} in file.", file=sys.stderr)
                    else: print(f"W: Invalid type for '{key}' in request: {type(req_value)}. Expected JSON boolean.", file=sys.stderr)
            except (ValueError, TypeError): print(f"W: Invalid value/type for '{key}' in request: {req_value}.", file=sys.stderr)
    if updated:
        save_success, saved_data = save_config(config_changes)
        if save_success: return jsonify({'status': 'success', 'message': f'Config saved to {CONFIG_FILE.name}. Restart server for changes to take effect.', 'saved_config': saved_data})
        else: return jsonify({'status': 'error', 'message': 'Failed to save config file.'}), 500
    else: return jsonify({'status': 'success', 'message': 'No valid changes requested. Config file not modified.', 'current_config_file': load_config()})


@app.route('/submit_code', methods=['POST', 'OPTIONS'])
def submit_code():
    # ... (keep existing CORS and lock logic) ...
    if request.method == 'OPTIONS': return '', 204
    if request.method == 'POST':
        if not request_lock.acquire(blocking=False): return jsonify({'status': 'error', 'message': 'Server busy, please try again shortly.'}), 429
        try:
            # ... (keep existing request parsing, filename extraction, saving logic) ...
            # ... (keep git logic, fallback logic, syntax checks, run logic) ...

            # --- MODIFICATION: Add running config to the response data ---
            response_data = {
                'status': 'success',
                'saved_as': final_save_filename,
                'saved_path': str(Path(save_filepath_str).relative_to(SERVER_DIR)) if save_filepath_str else None,
                'log_file': log_filename,
                'syntax_ok': syntax_ok,
                'run_success': run_success,
                'script_type': script_type,
                'source_file_marker': extracted_filename_raw,
                'git_updated': was_git_updated,
                'save_location': save_target,
                'detected_language': detected_language_name,
                # --- ADDED THIS SECTION ---
                'running_config': {
                    'auto_run_python': AUTO_RUN_PYTHON_ON_SYNTAX_OK,
                    'auto_run_shell': AUTO_RUN_SHELL_ON_SYNTAX_OK
                }
                # --- END ADDED SECTION ---
            }
            print(f"Sending response: {response_data}", file=sys.stderr)
            print("--- Request complete ---")
            return jsonify(response_data)

        except Exception as e:
            # ... (keep existing exception handling) ...
            print(f"E: Unhandled exception during /submit_code: {e}", file=sys.stderr); import traceback; traceback.print_exc(file=sys.stderr); return jsonify({'status': 'error', 'message': f'Internal server error: {e}'}), 500
        finally:
            if request_lock.locked(): request_lock.release()
    return jsonify({'status': 'error', 'message': f'Unsupported method: {request.method}'}), 405

@app.route('/test_connection', methods=['GET'])
def test_connection():
    # ... (keep existing implementation - calls get_status which includes config) ...
    print("Received /test_connection request", file=sys.stderr)
    return get_status()

# --- Log Routes (keep existing implementation) ---
@app.route('/logs')
# ...
@app.route('/logs/<path:filename>')
# ...

# --- Main Execution (keep existing implementation) ---
if __name__ == '__main__':
    # ...
# @@FILENAME@@ server.py