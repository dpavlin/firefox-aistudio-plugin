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
        ext