# @@FILENAME@@ routes/submit.py
from flask import Blueprint, jsonify, request, current_app
from pathlib import Path
import sys
import traceback # For detailed error logging

# Import necessary functions from other modules
from utils import FILENAME_EXTRACT_REGEX, sanitize_filename, detect_language_and_extension, generate_timestamped_filepath
from file_handler import save_code_to_file, find_tracked_file_by_name, is_git_tracked, update_and_commit_file
from script_runner import check_shell_syntax, run_script

submit_bp = Blueprint('submit_bp', __name__)

@submit_bp.route('/submit_code', methods=['POST'])
def submit_code_route():
    """Handles code submission, saving, Git, checks, and execution."""
    config = current_app.config['APP_CONFIG']
    request_lock = current_app.config['REQUEST_LOCK']

    if not request_lock.acquire(blocking=False):
        print("W: Request rejected, server busy (lock acquisition failed).", file=sys.stderr)
        return jsonify({'status': 'error', 'message': 'Server busy, please try again shortly.'}), 429

    try:
        print("\n--- Handling /submit_code request ---", file=sys.stderr)
        data = request.get_json()
        if not data: return jsonify({'status': 'error', 'message': 'Request body must be JSON.'}), 400
        received_code = data.get('code', '')
        if not received_code or received_code.isspace(): return jsonify({'status': 'error', 'message': 'Empty code received.'}), 400

        # --- Variable Initialization ---
        save_filepath_str = None; final_save_filename = None
        code_to_save = received_code; extracted_filename_raw = None
        marker_line_length = 0; was_git_updated = False
        sanitized_path_from_marker = None; save_target = "fallback"
        absolute_path_target = None; detected_language_name = "Unknown"

        # --- Marker Parsing and Git/Fallback Logic (Unchanged from previous refactor) ---
        match = FILENAME_EXTRACT_REGEX.search(received_code)
        if match:
            extracted_filename_raw = match.group(1).strip()
            marker_line_length = match.end(0)
            if marker_line_length < len(received_code) and received_code[marker_line_length] == '\n': marker_line_length += 1
            elif marker_line_length < len(received_code) and received_code[marker_line_length:marker_line_length+2] == '\r\n': marker_line_length += 2
            print(f"Info: Found @@FILENAME@@ marker: '{extracted_filename_raw}'", file=sys.stderr)
            sanitized_path_from_marker = sanitize_filename(extracted_filename_raw)

            if sanitized_path_from_marker:
                if config['IS_REPO']:
                    git_path_to_check = sanitized_path_from_marker
                    if '/' not in sanitized_path_from_marker.replace('\\', '/'):
                        found_rel_path = find_tracked_file_by_name(sanitized_path_from_marker, config['SERVER_DIR'], config['IS_REPO'])
                        if found_rel_path: git_path_to_check = found_rel_path
                    absolute_path_target = (config['SERVER_DIR'] / git_path_to_check).resolve()
                    if not str(absolute_path_target).startswith(str(config['SERVER_DIR'])): absolute_path_target = None
                    else:
                        is_tracked = is_git_tracked(git_path_to_check, config['SERVER_DIR'], config['IS_REPO'])
                        if is_tracked:
                            code_to_save = received_code[marker_line_length:]
                            commit_success = update_and_commit_file(absolute_path_target, code_to_save, git_path_to_check, config['SERVER_DIR'], config['IS_REPO'])
                            if commit_success:
                                save_filepath_str = str(absolute_path_target); final_save_filename = git_path_to_check
                                was_git_updated = True; save_target = "git"
                                detected_language_name = f"From Git ({Path(git_path_to_check).suffix})"
                            else: code_to_save = received_code; absolute_path_target = None; save_target = "fallback"
                        else:
                            absolute_path_target = (config['SAVE_FOLDER_PATH'] / sanitized_path_from_marker).resolve()
                            if not str(absolute_path_target).startswith(str(config['SAVE_FOLDER_PATH'])): absolute_path_target = None
                            code_to_save = received_code; save_target = "fallback"
                else:
                     absolute_path_target = (config['SAVE_FOLDER_PATH'] / sanitized_path_from_marker).resolve()
                     if not str(absolute_path_target).startswith(str(config['SAVE_FOLDER_PATH'])): absolute_path_target = None
                     code_to_save = received_code; save_target = "fallback"
            else: absolute_path_target = None; save_target = "fallback"; code_to_save = received_code
        else: absolute_path_target = None; save_target = "fallback"; code_to_save = received_code

        if save_target == "fallback":
            if absolute_path_target:
                 save_filepath_str = str(absolute_path_target)
                 try: final_save_filename = Path(save_filepath_str).relative_to(config['SAVE_FOLDER_PATH']).as_posix()
                 except ValueError: final_save_filename = Path(save_filepath_str).name
                 ext = Path(save_filepath_str).suffix.lower()
                 detected_language_name = f"From Path ({ext})" if ext else "From Path (no ext)"
            else:
                 ext_for_fallback, detected_language_name = detect_language_and_extension(code_to_save)
                 base_name = "code"
                 if detected_language_name not in ["Unknown", "Text"]: base_name = detected_language_name.lower().replace(" ", "_").replace("/", "_")
                 save_filepath_str = generate_timestamped_filepath(config['SAVE_FOLDER_PATH'], extension=ext_for_fallback, base_prefix=base_name)
                 final_save_filename = Path(save_filepath_str).name

            if not save_code_to_file(code_to_save, Path(save_filepath_str)):
                return jsonify({'status': 'error', 'message': 'Failed to save fallback file.'}), 500

        # --- Syntax Check & Optional Execution (Using lowercase config keys) ---
        syntax_ok = None; run_success = None; log_filename = None; script_type = None
        if not save_filepath_str or not Path(save_filepath_str).is_file(): return jsonify({'status': 'error', 'message': 'Internal error: Saved file path invalid.'}), 500

        check_run_filepath = save_filepath_str
        display_filename = final_save_filename or Path(check_run_filepath).name
        file_extension = Path(display_filename).suffix.lower()

        if file_extension == '.py':
            script_type = 'python'
            is_server_script = Path(check_run_filepath).resolve() == (config['SERVER_DIR'] / config['THIS_SCRIPT_NAME']).resolve()
            if not is_server_script:
                try:
                    saved_code_content = Path(check_run_filepath).read_text(encoding='utf-8')
                    compile(saved_code_content, check_run_filepath, 'exec')
                    syntax_ok = True
                    # *** Use lowercase config key ***
                    if config['auto_run_python']:
                        run_success, logpath = run_script(check_run_filepath, 'python', config['LOG_FOLDER_PATH'])
                        if logpath: log_filename = Path(logpath).name
                except SyntaxError: syntax_ok = False; run_success = False
                except Exception: syntax_ok = False; run_success = False

        elif file_extension == '.sh':
             script_type = 'shell'
             syntax_ok, syntax_log_path = check_shell_syntax(check_run_filepath, config['LOG_FOLDER_PATH'])
             if syntax_log_path: log_filename = Path(syntax_log_path).name
             if syntax_ok:
                  # *** Use lowercase config key ***
                  if config['auto_run_shell']:
                       run_success, run_log_path = run_script(check_run_filepath, 'shell', config['LOG_FOLDER_PATH'])
                       if run_log_path: log_filename = Path(run_log_path).name
             else: run_success = False

        # --- Send Response ---
        response_data = {
            'status': 'success', 'saved_as': final_save_filename,
            'saved_path': str(Path(save_filepath_str).relative_to(config['SERVER_DIR'])) if save_filepath_str else None,
            'log_file': log_filename, 'syntax_ok': syntax_ok, 'run_success': run_success,
            'script_type': script_type, 'source_file_marker': extracted_filename_raw,
            'git_updated': was_git_updated, 'save_location': save_target,
            'detected_language': detected_language_name
        }
        print(f"Sending response: {response_data}", file=sys.stderr)
        print("--- Request complete ---")
        return jsonify(response_data)

    except Exception as e:
        print(f"E: Unhandled exception during /submit_code: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({'status': 'error', 'message': f'Internal server error: {e}'}), 500
    finally:
        if request_lock.locked(): request_lock.release()
# @@FILENAME@@ routes/submit.py