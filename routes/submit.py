# @@FILENAME@@ routes/submit.py

from flask import Blueprint, jsonify, request, current_app
from pathlib import Path
import sys
import traceback # For detailed error logging
import codecs # Import codecs to handle BOM

# Import necessary functions from other modules
from utils import FILENAME_EXTRACT_REGEX, sanitize_filename, detect_language_and_extension, generate_timestamped_filepath
from file_handler import save_code_to_file, find_tracked_file_by_name, is_git_tracked, update_and_commit_file
from script_runner import check_shell_syntax, run_script

submit_bp = Blueprint('submit_bp', __name__)

# Define BOM constants
BOM_UTF8 = codecs.BOM_UTF8.decode('utf-8') # Usually u'\ufeff'

@submit_bp.route('/submit_code', methods=['POST'])
def submit_code_route():
    """Handles code submission, saving, Git, checks, and execution."""
    config = current_app.config['APP_CONFIG']
    request_lock = current_app.config['REQUEST_LOCK']

    print("--- /submit_code request received, attempting lock acquisition (blocking) ---", file=sys.stderr)
    request_lock.acquire()
    print("--- Lock acquired, proceeding with request ---", file=sys.stderr)

    try:
        print("\n--- Handling /submit_code request (inside lock) ---", file=sys.stderr)
        if not request.is_json:
             print("E: Request body is not JSON", file=sys.stderr)
             return jsonify({'status': 'error', 'message': 'Request body must be JSON.'}), 400

        data = request.get_json()
        if not data:
            print("E: Failed to parse JSON or JSON is empty", file=sys.stderr)
            return jsonify({'status': 'error', 'message': 'Invalid or empty JSON received.'}), 400

        received_code_raw = data.get('code', '') # Get raw code first
        if not received_code_raw or received_code_raw.isspace():
            print("E: 'code' field missing or empty in JSON", file=sys.stderr)
            return jsonify({'status': 'error', 'message': 'Empty code received.'}), 400

        # --- Strip potential BOM ---
        received_code = received_code_raw
        if received_code.startswith(BOM_UTF8):
            print("Info: Stripping leading UTF-8 BOM.", file=sys.stderr)
            received_code = received_code[len(BOM_UTF8):]

        # --- Initialize variables ---
        save_filepath_str = None
        final_save_filename = None
        code_to_save = received_code  # Default to potentially BOM-stripped code
        extracted_filename_raw = None # The raw filename from the marker
        sanitized_path_from_marker = None # Sanitized version for path construction
        was_git_updated = False
        save_target = "fallback" # Assume fallback initially
        absolute_path_target = None
        detected_language_name = "Unknown"
        marker_found_and_valid = False # Flag to track if we should use the marker info

        # --- Marker Parsing and Content Stripping (Strict first line) ---
        # Use the simplified regex from utils.py (Strict first line)
        match = FILENAME_EXTRACT_REGEX.search(received_code)

        if match:
            # Marker is guaranteed to be effectively on line 1 due to regex anchor ^
            marker_found_and_valid = True
            extracted_filename_raw = match.group(1).strip()
            print(f"Info: Found marker on first line: '{extracted_filename_raw}'.", file=sys.stderr)

            # Find the first newline character to split off the marker line
            first_newline = received_code.find('\n')
            if first_newline != -1:
                code_to_save = received_code[first_newline + 1:] # Content starts after the newline
            else:
                code_to_save = "" # Marker was the only content

            print(f"Info: Stripped marker line. Code to save length: {len(code_to_save)}", file=sys.stderr)
            sanitized_path_from_marker = sanitize_filename(extracted_filename_raw)
            if not sanitized_path_from_marker:
                print(f"W: Filename sanitization failed for '{extracted_filename_raw}'. Reverting to fallback.", file=sys.stderr)
                marker_found_and_valid = False # Treat as invalid if sanitization fails
                code_to_save = received_code # Revert to original (BOM-stripped) code
                extracted_filename_raw = None
        else:
            print("Info: No valid @@FILENAME@@ marker found at the start.", file=sys.stderr)
            marker_found_and_valid = False
            # code_to_save remains original (BOM-stripped)

        # --- Determine Save Path (Git or Fallback) ---
        if marker_found_and_valid: # Use marker info ONLY if found and sanitized
            save_target = "try_git_or_named_fallback" # Tentative target
            if config['IS_REPO']:
                git_path_to_check = sanitized_path_from_marker
                if '/' not in sanitized_path_from_marker.replace('\\', '/'):
                    found_rel_path = find_tracked_file_by_name(sanitized_path_from_marker, config['SERVER_DIR'], config['IS_REPO'])
                    if found_rel_path:
                        print(f"Info: Found unique tracked file via basename: '{found_rel_path}'", file=sys.stderr)
                        git_path_to_check = found_rel_path
                    else:
                         print(f"Info: Basename '{sanitized_path_from_marker}' not found uniquely in Git or search failed. Checking relative path.", file=sys.stderr)

                potential_target_abs = (config['SERVER_DIR'] / git_path_to_check).resolve()

                if str(potential_target_abs).startswith(str(config['SERVER_DIR'])):
                    is_tracked = is_git_tracked(git_path_to_check, config['SERVER_DIR'], config['IS_REPO'])
                    if is_tracked:
                        print(f"Info: Target path '{git_path_to_check}' is tracked. Setting target to 'git'.", file=sys.stderr)
                        absolute_path_target = potential_target_abs
                        save_target = "git"
                        final_save_filename = git_path_to_check
                    else:
                        print(f"Info: Target path '{git_path_to_check}' exists but is not tracked by Git. Setting target to 'fallback_named'.", file=sys.stderr)
                        absolute_path_target = (config['SAVE_FOLDER_PATH'] / sanitized_path_from_marker).resolve()
                        save_target = "fallback_named"
                else:
                    print(f"W: Potential target path '{potential_target_abs}' is outside SERVER_DIR. Reverting to fallback.", file=sys.stderr)
                    save_target = "fallback" # Revert to standard timestamped fallback
            else: # Not a Git repo
                 absolute_path_target = (config['SAVE_FOLDER_PATH'] / sanitized_path_from_marker).resolve()
                 if str(absolute_path_target).startswith(str(config['SAVE_FOLDER_PATH'])):
                      print(f"Info: Not a git repo. Setting target to 'fallback_named': '{sanitized_path_from_marker}'", file=sys.stderr)
                      save_target = "fallback_named"
                 else:
                      print(f"W: Potential target path '{absolute_path_target}' is outside SAVE_FOLDER. Reverting to fallback.", file=sys.stderr)
                      save_target = "fallback"
        else:
            # Explicitly ensure fallback if marker wasn't found or was invalid
            save_target = "fallback"


        # --- Handle Saving ---
        # This section uses the final determined `save_target` and `code_to_save`
        if save_target == "git":
            commit_success = update_and_commit_file(absolute_path_target, code_to_save, git_path_to_check, config['SERVER_DIR'], config['IS_REPO'])
            if commit_success:
                save_filepath_str = str(absolute_path_target)
                was_git_updated = True
                detected_language_name = f"From Git ({Path(git_path_to_check).suffix})"
            else:
                print("E: Git update/commit failed. File not saved.", file=sys.stderr)
                return jsonify({'status': 'error', 'message': f'Git commit failed for {git_path_to_check}.'}), 500

        elif save_target == "fallback_named":
            if not str(absolute_path_target).startswith(str(config['SAVE_FOLDER_PATH'])):
                 print(f"E: Internal error - fallback_named path '{absolute_path_target}' outside save folder '{config['SAVE_FOLDER_PATH']}'.", file=sys.stderr)
                 return jsonify({'status': 'error', 'message': 'Internal error constructing fallback path.'}), 500

            if save_code_to_file(code_to_save, absolute_path_target):
                 save_filepath_str = str(absolute_path_target)
                 try: final_save_filename = Path(save_filepath_str).relative_to(config['SAVE_FOLDER_PATH']).as_posix()
                 except ValueError: final_save_filename = Path(save_filepath_str).name
                 ext = Path(save_filepath_str).suffix.lower()
                 detected_language_name = f"From Path ({ext})" if ext else "From Path (no ext)"
            else:
                 return jsonify({'status': 'error', 'message': 'Failed to save named fallback file.'}), 500

        else: # save_target == "fallback" (timestamped)
            ext_for_fallback, detected_language_name = detect_language_and_extension(code_to_save)
            base_name = "code"
            # Use sanitized filename part for prefix only if marker was valid originally
            if marker_found_and_valid and sanitized_path_from_marker:
                 base_name = Path(sanitized_path_from_marker).stem
            elif detected_language_name not in ["Unknown", "Text"]:
                 base_name = detected_language_name.lower().replace(" ", "_").replace("/", "_")

            save_filepath_str = generate_timestamped_filepath(config['SAVE_FOLDER_PATH'], extension=ext_for_fallback, base_prefix=base_name)
            final_save_filename = Path(save_filepath_str).name

            if not save_code_to_file(code_to_save, Path(save_filepath_str)):
                return jsonify({'status': 'error', 'message': 'Failed to save timestamped fallback file.'}), 500


        # --- Syntax Check & Execution (using the saved file path) ---
        # (This logic remains the same)
        syntax_ok = None; run_success = None; log_filename = None; script_type = None
        if not save_filepath_str or not Path(save_filepath_str).is_file():
             print("E: Internal error - saved file path is invalid after save.", file=sys.stderr)
             return jsonify({'status': 'error', 'message': 'Internal error: Saved file path invalid.'}), 500

        check_run_filepath = save_filepath_str
        display_filename = final_save_filename # This should always be set now
        file_extension = Path(display_filename).suffix.lower()

        if save_target == "git":
             check_run_filepath_rel = Path(final_save_filename).as_posix()
             print(f"Info: Checking/Running Git file: {check_run_filepath_rel}", file=sys.stderr)
        else:
            check_run_filepath_rel = Path(check_run_filepath).relative_to(config['SERVER_DIR']).as_posix()
            print(f"Info: Checking/Running Fallback file: {check_run_filepath_rel}", file=sys.stderr)

        if file_extension == '.py':
            script_type = 'python'
            is_server_script = Path(check_run_filepath).resolve() == (config['SERVER_DIR'] / config['THIS_SCRIPT_NAME']).resolve()
            if not is_server_script:
                try:
                    saved_code_content = Path(check_run_filepath).read_text(encoding='utf-8')
                    compile(saved_code_content, check_run_filepath, 'exec')
                    syntax_ok = True
                    if config['auto_run_python']:
                        print(f"Attempting auto-run for Python script: {check_run_filepath}", file=sys.stderr)
                        run_success, logpath = run_script(check_run_filepath, 'python', config['LOG_FOLDER_PATH'])
                        if logpath: log_filename = Path(logpath).name
                except SyntaxError as py_syntax_e:
                    print(f"E: Python syntax error in '{check_run_filepath_rel}': {py_syntax_e}", file=sys.stderr)
                    syntax_ok = False; run_success = False
                except Exception as py_compile_e:
                    print(f"E: Error compiling Python script '{check_run_filepath_rel}': {py_compile_e}", file=sys.stderr)
                    syntax_ok = False; run_success = False
            else:
                 print("W: Skipping syntax check/run for server script itself.", file=sys.stderr)

        elif file_extension == '.sh':
             script_type = 'shell'
             print(f"Attempting syntax check for Shell script: {check_run_filepath}", file=sys.stderr)
             syntax_ok, syntax_log_path = check_shell_syntax(check_run_filepath, config['LOG_FOLDER_PATH'])
             if syntax_log_path: log_filename = Path(syntax_log_path).name
             if syntax_ok:
                  if config['auto_run_shell']:
                       print(f"Attempting auto-run for Shell script: {check_run_filepath}", file=sys.stderr)
                       run_success, run_log_path = run_script(check_run_filepath, 'shell', config['LOG_FOLDER_PATH'])
                       if run_log_path: log_filename = Path(run_log_path).name
             else: run_success = False

        # --- Prepare and send response ---
        response_data = {
            'status': 'success',
            'saved_as': final_save_filename,
            'saved_path': str(Path(save_filepath_str).relative_to(config['SERVER_DIR'])) if save_filepath_str else None,
            'log_file': log_filename,
            'syntax_ok': syntax_ok,
            'run_success': run_success,
            'script_type': script_type,
            'source_file_marker': extracted_filename_raw, # Original marker text if found and valid
            'git_updated': was_git_updated,
            'save_location': save_target,
            'detected_language': detected_language_name
        }
        print(f"Sending response: {response_data}", file=sys.stderr)
        print("--- Request complete (inside lock) ---")
        return jsonify(response_data)

    except Exception as e:
        print(f"E: Unhandled exception during /submit_code: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({'status': 'error', 'message': f'Internal server error: {e}'}), 500
    finally:
        # Ensure the lock is released even if errors occur
        if request_lock.locked():
             request_lock.release()
             print("--- Lock released ---", file=sys.stderr)
        else:
             print("W: Lock was not held by this thread in finally block?", file=sys.stderr)

# @@FILENAME@@ routes/submit.py
