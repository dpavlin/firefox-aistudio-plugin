from flask import Blueprint, jsonify, request, current_app
from pathlib import Path
import sys
import traceback # For detailed error logging

# Import necessary functions from other modules
# *** Add create_commented_marker_line ***
from utils import FILENAME_EXTRACT_REGEX, sanitize_filename, detect_language_and_extension, generate_timestamped_filepath, create_commented_marker_line
from file_handler import save_code_to_file, find_tracked_file_by_name, is_git_tracked, update_and_commit_file
from script_runner import check_shell_syntax, run_script

submit_bp = Blueprint('submit_bp', __name__)

@submit_bp.route('/submit_code', methods=['POST'])
def submit_code_route():
    """Handles code submission, saving, Git, checks, and execution."""
    config = current_app.config['APP_CONFIG']
    request_lock = current_app.config['REQUEST_LOCK']

    print("--- /submit_code request received, attempting lock acquisition (blocking) ---", file=sys.stderr)
    request_lock.acquire()
    print("--- Lock acquired, proceeding with request ---", file=sys.stderr)

    try:
        print("\n--- Handling /submit_code request (inside lock) ---", file=sys.stderr) # Log inside lock
        data = request.get_json()
        if not data: return jsonify({'status': 'error', 'message': 'Request body must be JSON.'}), 400
        received_code = data.get('code', '')
        if not received_code or received_code.isspace(): return jsonify({'status': 'error', 'message': 'Empty code received.'}), 400

        save_filepath_str = None; final_save_filename = None
        code_content_without_marker = None # Store code after stripping marker
        extracted_filename_raw = None
        marker_line_length = 0; was_git_updated = False
        sanitized_path_from_marker = None; save_target = "fallback"
        absolute_path_target = None; detected_language_name = "Unknown"
        save_path_for_commenting = None # Store the path used to determine comment style

        match = FILENAME_EXTRACT_REGEX.search(received_code)
        if match:
            extracted_filename_raw = match.group(1).strip()
            marker_line_length = match.end(0)
            # Adjust length for potential \r\n or \n line ending after marker
            if marker_line_length < len(received_code):
                if received_code[marker_line_length:marker_line_length+2] == '\r\n':
                    marker_line_length += 2
                elif received_code[marker_line_length] == '\n':
                    marker_line_length += 1

            # Store the code *without* the marker line
            code_content_without_marker = received_code[marker_line_length:]
            # print(f"Info: Found @@FILENAME@@ marker: '{extracted_filename_raw}'", file=sys.stderr)
            sanitized_path_from_marker = sanitize_filename(extracted_filename_raw)

            if sanitized_path_from_marker:
                # print(f"Info: Sanitized path from marker: '{sanitized_path_from_marker}'", file=sys.stderr)
                if config['IS_REPO']:
                    git_path_to_check = sanitized_path_from_marker
                    # If marker only contains basename, try finding unique tracked file
                    if '/' not in sanitized_path_from_marker.replace('\\', '/'):
                        found_rel_path = find_tracked_file_by_name(sanitized_path_from_marker, config['SERVER_DIR'], config['IS_REPO'])
                        if found_rel_path:
                             git_path_to_check = found_rel_path
                             print(f"Info: Matched basename marker to tracked file: '{git_path_to_check}'", file=sys.stderr)

                    potential_target = (config['SERVER_DIR'] / git_path_to_check).resolve()
                    # Check if potential target is within server directory
                    if str(potential_target).startswith(str(config['SERVER_DIR'])):
                        is_tracked = is_git_tracked(git_path_to_check, config['SERVER_DIR'], config['IS_REPO'])
                        if is_tracked:
                            # print(f"Info: Target path '{git_path_to_check}' is tracked. Attempting Git update.", file=sys.stderr)
                            absolute_path_target = potential_target
                            save_path_for_commenting = absolute_path_target # Use this path for comment style
                            save_filepath_str = str(absolute_path_target)
                            final_save_filename = git_path_to_check
                            save_target = "git"
                            detected_language_name = f"From Git ({Path(git_path_to_check).suffix})"
                            # Git update happens later, after reconstructing content
                        else:
                            # Not tracked in Git, treat as fallback to save folder
                            # Use the *sanitized path* relative to the save folder
                            print(f"Info: Path '{git_path_to_check}' from marker is not tracked in Git. Saving to fallback.", file=sys.stderr)
                            save_target = "fallback"
                            absolute_path_target = (config['SAVE_FOLDER_PATH'] / sanitized_path_from_marker).resolve()
                            if not str(absolute_path_target).startswith(str(config['SAVE_FOLDER_PATH'])):
                                print(f"W: Fallback path '{absolute_path_target}' seems outside save folder. Rejecting.", file=sys.stderr)
                                absolute_path_target = None # Safety check failed
                    else:
                         # Potential target outside server dir, reject
                         print(f"W: Potential Git path '{potential_target}' seems outside server root. Rejecting.", file=sys.stderr)
                         absolute_path_target = None
                         save_target = "fallback"

                # If not a repo, or marker path resolved outside repo, or not tracked, use save