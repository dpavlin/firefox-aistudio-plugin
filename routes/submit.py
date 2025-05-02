#!/usr/bin/env python3
# @@FILENAME@@ routes/submit.py

from flask import Blueprint, jsonify, request, current_app
from pathlib import Path
import sys
import traceback # For detailed error logging
import codecs # Import codecs to handle BOM
import re # Import re for the end marker check

# Import necessary functions from other modules
from utils import FILENAME_EXTRACT_REGEX, sanitize_filename, detect_language_and_extension, generate_timestamped_filepath
from file_handler import save_code_to_file, find_tracked_file_by_name, is_git_tracked, update_and_commit_file
from script_runner import check_shell_syntax, run_script # Updated import signature not needed, handled internally

submit_bp = Blueprint('submit_bp', __name__)

# Define BOM constants
BOM_UTF8 = codecs.BOM_UTF8.decode('utf-8') # Usually u'\ufeff'

# Regex to match the end marker line robustly (accounts for path and ---)
END_MARKER_REGEX = re.compile(r"^\s*--- END OF @@FILENAME@@ .+? ---\s*$", re.IGNORECASE)

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
        # ... (rest of JSON and BOM handling code remains the same) ...
        received_code_raw = data.get('code', '')
        if not received_code_raw or received_code_raw.isspace():
            # ... error handling ...
            return jsonify({'status': 'error', 'message': 'Empty code received.'}), 400

        received_code = received_code_raw
        if received_code.startswith(BOM_UTF8):
            print("Info: Stripping leading UTF-8 BOM.", file=sys.stderr)
            received_code = received_code[len(BOM_UTF8):]

        # --- Initialize variables ---
        save_filepath_str = None
        final_save_filename = None
        code_to_save = received_code
        extracted_filename_raw = None
        sanitized_path_from_marker = None
        was_git_updated = False
        save_target = "fallback"
        absolute_path_target = None
        detected_language_name = "Unknown"
        marker_found_and_valid = False

        # --- Marker Parsing and Content Stripping (Strict first line) ---
        match = FILENAME_EXTRACT_REGEX.search(received_code)
        if match:
            # ... (marker parsing logic remains the same) ...
            marker_found_and_valid = True
            extracted_filename_raw = match.group(1).strip()
            # ... calculate code_to_save ...
            sanitized_path_from_marker = sanitize_filename(extracted_filename_raw)
            # ... handle sanitization failure ...
        else:
            # ... (no marker found logic) ...
            marker_found_and_valid = False

        # --- Determine Save Path (Git or Fallback) ---
        # ... (this logic remains the same) ...
        if marker_found_and_valid:
             # ... determine save_target (git, fallback_named) ...
             pass # Placeholder
        else:
            save_target = "fallback"

        # --- Strip Optional End Marker before Saving ---
        original_code_to_save = code_to_save # Keep a copy
        lines = code_to_save.splitlines()
        # ... (end marker stripping logic remains the same) ...
        if len(lines) > 0:
            last_line_index = -1
            for i in range(len(lines) - 1, -1, -1):
                 if lines[i].strip():
                     last_line_index = i
                     break
            if last_line_index != -1 and END_MARKER_REGEX.match(lines[last_line_index]):
                print(f"Info: Stripping end-of-file marker line: '{lines[last_line_index]}'", file=sys.stderr)
                code_to_save = "\n".join(lines[:last_line_index]).rstrip()
                if code_to_save: code_to_save += "\n"
            else:
                code_to_save = code_to_save.rstrip() + "\n"


        # --- Handle Saving ---
        # ... (saving logic remains the same, uses final code_to_save) ...
        if save_target == "git":
            # ... save/commit ...
            pass
        elif save_target == "fallback_named":
            # ... save to named file ...
            pass
        else: # fallback timestamped
            # ... generate name, save ...
            pass

        # --- Syntax Check & Execution (captures output) ---
        syntax_ok = None
        run_success = None
        script_type = None
        syntax_stdout = None # Renamed from log_filename
        syntax_stderr = None
        run_stdout = None
        run_stderr = None

        if not save_filepath_str or not Path(save_filepath_str).is_file():
             print("E: Internal error - saved file path is invalid after save.", file=sys.stderr)
             return jsonify({'status': 'error', 'message': 'Internal error: Saved file path invalid.'}), 500

        check_run_filepath = save_filepath_str
        display_filename = final_save_filename
        file_extension = Path(display_filename).suffix.lower()

        # Determine relative path for logging
        try:
            check_run_filepath_rel = Path(check_run_filepath).relative_to(config['SERVER_DIR']).as_posix()
        except ValueError:
            check_run_filepath_rel = Path(check_run_filepath).name
        # Print path type
        print(f"Info: Checking/Running {'Git' if save_target == 'git' else 'Fallback'} file: {check_run_filepath_rel}", file=sys.stderr)


        if file_extension == '.py':
            script_type = 'python'
            is_server_script = Path(check_run_filepath).resolve() == (config['SERVER_DIR'] / config['THIS_SCRIPT_NAME']).resolve()
            if not is_server_script:
                try:
                    saved_code_content = Path(check_run_filepath).read_text(encoding='utf-8')
                    compile(saved_code_content, check_run_filepath, 'exec')
                    syntax_ok = True
                    # No separate syntax output for Python compile
                    if config['auto_run_python']:
                        print(f"Attempting auto-run for Python script: {check_run_filepath}", file=sys.stderr)
                        # Capture output from run_script
                        run_success, run_stdout, run_stderr = run_script(check_run_filepath, 'python')
                except SyntaxError as py_syntax_e:
                    print(f"E: Python syntax error in '{check_run_filepath_rel}': {py_syntax_e}", file=sys.stderr)
                    syntax_ok = False; run_success = False
                    syntax_stderr = str(py_syntax_e) # Capture syntax error message
                except Exception as py_compile_e:
                    print(f"E: Error compiling Python script '{check_run_filepath_rel}': {py_compile_e}", file=sys.stderr)
                    syntax_ok = False; run_success = False
                    syntax_stderr = f"Compile error: {py_compile_e}"
            else:
                 print("W: Skipping syntax check/run for server script itself.", file=sys.stderr)

        elif file_extension == '.sh':
             script_type = 'shell'
             print(f"Attempting syntax check for Shell script: {check_run_filepath}", file=sys.stderr)
             # Capture output from check_shell_syntax
             syntax_ok, syntax_stdout, syntax_stderr = check_shell_syntax(check_run_filepath)
             if syntax_ok:
                  if config['auto_run_shell']:
                       print(f"Attempting auto-run for Shell script: {check_run_filepath}", file=sys.stderr)
                       # Capture output from run_script
                       run_success, run_stdout, run_stderr = run_script(check_run_filepath, 'shell')
             else: run_success = False # Syntax failed, so run must also fail

        # --- Prepare and send response ---
        response_data = {
            'status': 'success',
            'saved_as': final_save_filename,
            'saved_path': str(Path(save_filepath_str).relative_to(config['SERVER_DIR'])) if save_filepath_str else None,
            # 'log_file': log_filename, # REMOVED
            'syntax_ok': syntax_ok,
            'syntax_stdout': syntax_stdout, # ADDED
            'syntax_stderr': syntax_stderr, # ADDED
            'run_success': run_success,
            'run_stdout': run_stdout, # ADDED
            'run_stderr': run_stderr, # ADDED
            'script_type': script_type,
            'source_file_marker': extracted_filename_raw,
            'git_updated': was_git_updated,
            'save_location': save_target,
            'detected_language': detected_language_name
        }
        print(f"Sending response: {response_data}", file=sys.stderr)
        print("--- Request complete (inside lock) ---")
        return jsonify(response_data)

    # ... (except and finally blocks remain the same) ...
    except Exception as e:
        print(f"E: Unhandled exception during /submit_code: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({'status': 'error', 'message': f'Internal server error: {e}'}), 500
    finally:
        if request_lock.locked():
             request_lock.release()
             print("--- Lock released ---", file=sys.stderr)
        else:
             print("W: Lock was not held by this thread in finally block?", file=sys.stderr)

# @@FILENAME@@ routes/submit.py