# ... (imports and parser setup remain the same) ...

# --- Flask App Setup ---
app = Flask(__name__)
CORS(app)

# --- Configuration & Paths ---
# *** CHANGE: Base paths on CWD now ***
SERVER_DIR = Path.cwd().resolve() # Use Current Working Directory as the base
# *** SAVE_FOLDER and LOG_FOLDER will now be relative to CWD ***
# Consider if you want them always relative to script or always relative to CWD
# If always relative to script, define them before changing SERVER_DIR:
# SCRIPT_LOCATION_DIR = Path(__file__).parent.resolve()
# SAVE_FOLDER_PATH = SCRIPT_LOCATION_DIR / 'received_codes'
# LOG_FOLDER_PATH = SCRIPT_LOCATION_DIR / 'logs'
# If relative to CWD (as coded below):
SAVE_FOLDER = 'received_codes'; LOG_FOLDER = 'logs'
SAVE_FOLDER_PATH = SERVER_DIR / SAVE_FOLDER
LOG_FOLDER_PATH = SERVER_DIR / LOG_FOLDER
THIS_SCRIPT_NAME = Path(__file__).name # Still useful for preventing self-modification

os.makedirs(SAVE_FOLDER_PATH, exist_ok=True)
os.makedirs(LOG_FOLDER_PATH, exist_ok=True)

# --- Regex & Constants (Unchanged) ---
# ...

# --- Helper Functions ---
# ... (sanitize_filename, detect_language_and_extension, generate_timestamped_filepath remain the same) ...

def is_git_repository() -> bool:
    """Checks if SERVER_DIR (now CWD) is part of a Git repository."""
    try:
        # *** REMOVE cwd=SERVER_DIR ***
        result = subprocess.run(['git', 'rev-parse', '--git-dir'], capture_output=True, text=True, check=False, encoding='utf-8')
        is_repo = result.returncode == 0
        if not is_repo: print(f"Info: CWD '{SERVER_DIR}' is not inside a Git repository.", file=sys.stderr)
        return is_repo
    except FileNotFoundError: print("W: 'git' command not found.", file=sys.stderr); return False
    except Exception as e: print(f"E: checking Git repository: {e}", file=sys.stderr); return False

IS_REPO = is_git_repository()

def find_tracked_file_by_name(basename_to_find: str) -> str | None:
    """Searches the Git index (in CWD)"""
    if not IS_REPO: return None
    try:
        command = ['git', 'ls-files']
        print(f"Running: {' '.join(command)} from CWD ({SERVER_DIR}) to find matches for '*/{basename_to_find}'", file=sys.stderr)
        # *** REMOVE cwd=SERVER_DIR ***
        result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
        tracked_files = result.stdout.splitlines()
        matches = [f for f in tracked_files if f.endswith('/' + basename_to_find) or f == basename_to_find]
        if len(matches) == 1: print(f"Info: Found unique tracked file match: '{matches[0]}'", file=sys.stderr); return matches[0]
        elif len(matches) > 1: print(f"W: Ambiguous '{basename_to_find}'. Found: {matches}", file=sys.stderr); return None
        else: print(f"Info: No tracked file ending in '{basename_to_find}' found.", file=sys.stderr); return None
    except subprocess.CalledProcessError as e: print(f"E: 'git ls-files' failed:\n{e.stderr}", file=sys.stderr); return None
    except Exception as e: print(f"E: checking Git for file '{basename_to_find}': {e}", file=sys.stderr); return None

def is_git_tracked(filepath_relative_to_repo: str) -> bool:
    """Checks if a specific file is tracked by Git relative to CWD (SERVER_DIR)."""
    if not IS_REPO: return False
    try:
        git_path = Path(filepath_relative_to_repo).as_posix(); command = ['git', 'ls-files', '--error-unmatch', git_path]
        print(f"Running: {' '.join(command)} from CWD ({SERVER_DIR})", file=sys.stderr)
        # *** REMOVE cwd=SERVER_DIR ***
        result = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8')
        is_tracked = result.returncode == 0
        print(f"Info: Git track status for '{git_path}': {is_tracked}", file=sys.stderr)
        if result.returncode != 0 and result.stderr: print(f"Info: git ls-files stderr: {result.stderr.strip()}", file=sys.stderr)
        return is_tracked
    except Exception as e: print(f"E: checking Git track status for '{filepath_relative_to_repo}': {e}", file=sys.stderr); return False

def update_and_commit_file(filepath_absolute: Path, code_content: str, marker_filename: str) -> bool:
    """Overwrites, adds, and commits a file using Git, relative to CWD (SERVER_DIR)."""
    if not IS_REPO: return False
    try:
        # We already have absolute path, relative path for git is calculated from CWD (SERVER_DIR)
        filepath_relative_to_repo_str = str(filepath_absolute.relative_to(SERVER_DIR)); git_path_posix = filepath_relative_to_repo_str # Already relative
        print(f"Overwriting local file: {filepath_relative_to_repo_str}", file=sys.stderr)
        filepath_absolute.parent.mkdir(parents=True, exist_ok=True)
        filepath_absolute.write_text(code_content, encoding='utf-8')
        print(f"Running: git add '{git_path_posix}' from CWD ({SERVER_DIR})", file=sys.stderr)
        # *** REMOVE cwd=SERVER_DIR ***
        add_result = subprocess.run(['git', 'add', git_path_posix], capture_output=True, text=True, check=False, encoding='utf-8')
        if add_result.returncode != 0: print(f"E: 'git add' failed:\n{add_result.stderr}", file=sys.stderr); return False
        commit_message = f"Update {marker_filename} from AI Code Capture"
        print(f"Running: git commit -m \"{commit_message}\" from CWD ({SERVER_DIR})", file=sys.stderr)
        # *** REMOVE cwd=SERVER_DIR ***
        commit_result = subprocess.run(['git', 'commit', '-m', commit_message], capture_output=True, text=True, check=False, encoding='utf-8')
        if commit_result.returncode != 0:
            no_changes_patterns = ["nothing to commit", "no changes added to commit", "nothing added to commit"]
            commit_output = commit_result.stdout + commit_result.stderr
            if any(pattern in commit_output for pattern in no_changes_patterns): print("Info: No changes detected by Git for commit.", file=sys.stderr); return True
            else: print(f"E: 'git commit' failed:\n{commit_result.stderr}", file=sys.stderr); return False
        print(f"Successfully committed changes for {filepath_relative_to_repo_str}.", file=sys.stderr)
        return True
    except IOError as e: print(f"E: writing file {filepath_absolute}: {e}", file=sys.stderr); return False
    except Exception as e: print(f"E: during Git update/commit for {filepath_absolute}: {e}", file=sys.stderr); return False

def run_script(filepath):
    filepath_obj = Path(filepath); filename_base = filepath_obj.stem
    logpath = LOG_FOLDER_PATH / f"{filename_base}.log" # LOG_FOLDER_PATH is now relative to CWD
    try:
        python_exe = sys.executable; run_cwd = filepath_obj.parent
        print(f"Executing: {python_exe} {filepath_obj.name} in {run_cwd}", file=sys.stderr)
        # Run script relative to its own path, which is correct
        result = subprocess.run([python_exe, filepath_obj.name], capture_output=True, text=True, timeout=10, encoding='utf-8', check=False, cwd=run_cwd)
        os.makedirs(LOG_FOLDER_PATH, exist_ok=True)
        with open(logpath, 'w', encoding='utf-8') as f: f.write(f"--- STDOUT ---\n{result.stdout}\n--- STDERR ---\n{result.stderr}\n--- Return Code: {result.returncode} ---\n")
        print(f"Exec finished. RC: {result.returncode}. Log: {logpath.name}", file=sys.stderr)
        return result.returncode == 0, str(logpath)
    except subprocess.TimeoutExpired: print(f"E: Script timed out: {filepath}", file=sys.stderr); os.makedirs(LOG_FOLDER_PATH, exist_ok=True); with open(logpath, 'w', encoding='utf-8') as f: f.write("Error: Script timed out after 10 seconds.\n"); return False, str(logpath)
    except Exception as e: print(f"E: running script {filepath}: {e}", file=sys.stderr); os.makedirs(LOG_FOLDER_PATH, exist_ok=True); with open(logpath, 'w', encoding='utf-8') as f: f.write(f"Error running script: {str(e)}\n"); return False, str(logpath)

# --- Route Definitions ---
@app.route('/submit_code', methods=['POST', 'OPTIONS'])
def submit_code():
    if request.method == 'OPTIONS': return '', 204
    if request.method == 'POST':
        with request_lock: # Keep lock
            print("--- Handling /submit_code request (Lock acquired) ---", file=sys.stderr)
            # ... (rest of the submit_code logic - it now uses the CWD-based SERVER_DIR indirectly via helper funcs) ...

            data = request.get_json();
            if not data: return jsonify({'status': 'error', 'message': 'No JSON data received'}), 400
            received_code = data.get('code', '');
            if not received_code or received_code.isspace(): return jsonify({'status': 'error', 'message': 'Empty code received'}), 400

            save_filepath_str = None; final_save_filename = None; code_to_save = received_code
            extracted_filename_raw = None; detected_language_name = "Unknown"
            marker_line_length = 0; was_git_updated = False; sanitized_path_from_marker = None
            save_target = "fallback"

            match = FILENAME_EXTRACT_REGEX.search(received_code)
            if match:
                extracted_filename_raw = match.group(1).strip(); marker_line_length = match.end()
                if marker_line_length < len(received_code) and received_code[marker_line_length] == '\n': marker_line_length += 1
                print(f"Found marker: '{extracted_filename_raw}'", file=sys.stderr)
                sanitized_path_from_marker = sanitize_filename(extracted_filename_raw)

                if sanitized_path_from_marker:
                    print(f"Sanitized relative path from marker: '{sanitized_path_from_marker}'", file=sys.stderr)
                    git_path_to_check = sanitized_path_from_marker
                    if '/' not in sanitized_path_from_marker.replace('\\', '/'):
                        print(f"Marker is basename only. Searching Git index...", file=sys.stderr)
                        found_rel_path = find_tracked_file_by_name(sanitized_path_from_marker)
                        if found_rel_path: git_path_to_check = found_rel_path
                        else: print(f"No unique match for '{sanitized_path_from_marker}'. Fallback.", file=sys.stderr); git_path_to_check = None

                    if git_path_to_check:
                        # Construct absolute path based on CWD (SERVER_DIR)
                        absolute_path_for_commit = (SERVER_DIR / git_path_to_check).resolve()
                        # Security check remains important
                        if not str(absolute_path_for_commit).startswith(str(SERVER_DIR)):
                            print(f"W: Resolved path '{absolute_path_for_commit}' outside server dir ({SERVER_DIR}). Blocking Git.", file=sys.stderr)
                            sanitized_path_from_marker = None
                        else:
                            is_tracked = is_git_tracked(git_path_to_check)
                            if is_tracked:
                                print(f"File '{git_path_to_check}' is tracked. Committing to '{absolute_path_for_commit}'.", file=sys.stderr)
                                code_to_save = received_code[marker_line_length:]
                                commit_success = update_and_commit_file(absolute_path_for_commit, code_to_save, extracted_filename_raw)
                                if commit_success: save_filepath_str = str(absolute_path_for_commit); final_save_filename = git_path_to_check; was_git_updated = True; save_target = "git"; print(f"Git OK: {final_save_filename}", file=sys.stderr)
                                else: print(f"W: Git commit failed for {git_path_to_check}. Saving to '{SAVE_FOLDER}'.", file=sys.stderr); sanitized_path_from_marker = git_path_to_check; code_to_save = received_code
                            else: print(f"Info: Path '{git_path_to_check}' not tracked. Saving to '{SAVE_FOLDER}'.", file=sys.stderr); code_to_save = received_code
                else: print(f"W: Invalid extracted filename '{extracted_filename_raw}'. Saving to '{SAVE_FOLDER}'.", file=sys.stderr); code_to_save = received_code
            else: print("Info: No filename marker found. Saving to '{SAVE_FOLDER}'.", file=sys.stderr); code_to_save = received_code

            # --- Fallback Save Logic (Now uses CWD-relative SAVE_FOLDER_PATH) ---
            if save_target == "fallback":
                base_name_for_fallback = "code"; ext_for_fallback = DEFAULT_EXTENSION
                if sanitized_path_from_marker: base_name_for_fallback = Path(sanitized_path_from_marker).stem; ext_for_fallback = Path(sanitized_path_from_marker).suffix or DEFAULT_EXTENSION; detected_language_name = "From Marker (Untracked)"
                else: detected_ext, detected_language_name = detect_language_and_extension(code_to_save); ext_for_fallback = detected_ext;
                if detected_language_name != "Unknown": base_name_for_fallback = detected_language_name.lower().replace(" ", "_")
                save_filepath_str = generate_timestamped_filepath(extension=ext_for_fallback, base_prefix=base_name_for_fallback) # Returns path relative to SAVE_FOLDER_PATH
                final_save_filename = os.path.basename(save_filepath_str)
                print(f"Saving fallback to: '{save_filepath_str}'", file=sys.stderr)
                try: os.makedirs(Path(save_filepath_str).parent, exist_ok=True); Path(save_filepath_str).write_text(code_to_save, encoding='utf-8'); print(f"Code saved successfully to {save_filepath_str}", file=sys.stderr)
                except Exception as e: return jsonify({'status': 'error', 'message': f'Failed to save fallback file: {str(e)}'}), 500

            # --- Process the code (Syntax check / Run) ---
            is_likely_python = final_save_filename.lower().endswith('.py')
            syntax_ok = None; run_success = None; log_filename = None

            # Prevent running the *server script itself* if marker pointed to it
            is_server_script = False
            if save_target == "git":
                 is_server_script = Path(save_filepath_str).name == THIS_SCRIPT_NAME

            if is_likely_python and not is_server_script:
                 # ... (rest of the syntax check and run logic remains the same, using code_to_save and save_filepath_str) ...
                print(f"File '{final_save_filename}' is Python, performing checks.", file=sys.stderr)
                try:
                    compile(code_to_save, save_filepath_str, 'exec'); syntax_ok = True; print(f"Syntax OK for {final_save_filename}", file=sys.stderr)
                    if AUTO_RUN_ON_SYNTAX_OK:
                        print(f"Attempting to run {final_save_filename}", file=sys.stderr)
                        run_success, logpath = run_script(save_filepath_str)
                        log_filename = Path(logpath).name if logpath else None
                        print(f"Script run completed. Success: {run_success}, Log: {log_filename}", file=sys.stderr)
                except SyntaxError as e:
                    syntax_ok = False; print(f"Syntax Error: L{e.lineno} C{e.offset} {e.msg}", file=sys.stderr)
                    log_fn_base = Path(save_filepath_str).stem; log_path_err = LOG_FOLDER_PATH / f"{log_fn_base}_syntax_error.log"; marker = extracted_filename_raw or 'None'
                    try: os.makedirs(LOG_FOLDER_PATH, exist_ok=True);
                    with open(log_path_err, 'w', encoding='utf-8') as f: f.write(f"Syntax Error:\nFile: {final_save_filename} (Marker: {marker})\nLine: {e.lineno}, Offset: {e.offset}\nMsg: {e.msg}\nCtx:\n{e.text}"); log_filename = log_path_err.name
                    except Exception as log_e: print(f"E: writing syntax error log: {log_e}", file=sys.stderr)
                except Exception as compile_e:
                    syntax_ok = False; run_success = False; print(f"Compile/run setup error: {compile_e}", file=sys.stderr)
                    log_fn_base = Path(save_filepath_str).stem; log_path_err = LOG_FOLDER_PATH / f"{log_fn_base}_compile_error.log"; marker = extracted_filename_raw or 'None'
                    try: os.makedirs(LOG_FOLDER_PATH, exist_ok=True);
                    with open(log_path_err, 'w', encoding='utf-8') as f: f.write(f"Compile/Run Setup Error:\nFile: {final_save_filename} (Marker: {marker})\nError: {compile_e}\n"); log_filename = log_path_err.name
                    except Exception as log_e: print(f"E: writing compile error log: {log_e}", file=sys.stderr)
            elif is_server_script:
                 print(f"Skipping run for server script itself: '{final_save_filename}'.", file=sys.stderr)
                 try: compile(code_to_save, save_filepath_str, 'exec'); syntax_ok = True; print(f"Syntax OK for {final_save_filename}", file=sys.stderr)
                 except SyntaxError as e: syntax_ok = False; print(f"Syntax Error: L{e.lineno} C{e.offset} {e.msg}", file=sys.stderr)
                 except Exception as compile_e: syntax_ok = False; print(f"Compile check error: {compile_e}", file=sys.stderr)
            else: print(f"File '{final_save_filename}' is not Python, skipping checks.", file=sys.stderr)

            response_data = {'status': 'success', 'saved_as': final_save_filename, 'log_file': log_filename, 'syntax_ok': syntax_ok, 'run_success': run_success, 'source_file_marker': extracted_filename_raw, 'git_updated': was_git_updated, 'save_location': save_target, 'detected_language': detected_language_name if not extracted_filename_raw else None}
            print(f"Sending response: {response_data}", file=sys.stderr)
            print("--- Request complete (Lock released) ---", file=sys.stderr)
            return jsonify(response_data)
        # --- Lock Released ---

    return jsonify({'status': 'error', 'message': f'Unsupported method: {request.method}'}), 405

@app.route('/test_connection', methods=['GET'])
def test_connection():
    """Simple endpoint to check if the server is running and return CWD."""
    print("Received /test_connection request", file=sys.stderr)
    try:
        cwd = str(SERVER_DIR) # SERVER_DIR is now the CWD
        return jsonify({'status': 'ok', 'message': 'Server is running.', 'working_directory': cwd})
    except Exception as e:
        print(f"Error getting working directory for test connection: {e}", file=sys.stderr)
        return jsonify({'status': 'error', 'message': f'Server error: {str(e)}'}), 500

# --- Log Routes (Unchanged logic, but paths are now relative to CWD) ---
@app.route('/logs')
def list_logs():
    log_files = []; template = '''<!DOCTYPE html><html><head><title>Logs Browser</title><style>body{font-family:Arial,sans-serif;background:#1e1e1e;color:#d4d4d4;padding:20px}h1{color:#4ec9b0;border-bottom:1px solid #444;padding-bottom:10px}ul{list-style:none;padding:0}li{background:#252526;margin-bottom:8px;border-radius:4px}li a{color:#9cdcfe;text-decoration:none;display:block;padding:10px 15px;transition:background-color .2s ease}li a:hover{background-color:#333}p{color:#888}pre{background:#1e1e1e;border:1px solid #444;padding:15px;border-radius:5px;overflow-x:auto;white-space:pre-wrap;word-wrap:break-word;color:#d4d4d4}</style></head><body><h1>🗂️ Available Logs</h1>{% if logs %}<ul>{% for log in logs %}<li><a href="/logs/{{ log | urlencode }}">{{ log }}</a></li>{% endfor %}</ul>{% else %}<p>No logs found in '{{ log_folder_name }}'.</p>{% endif %}</body></html>'''
    try:
         # Use LOG_FOLDER_PATH which is now based on CWD
         log_paths = [p for p in LOG_FOLDER_PATH.iterdir() if p.is_file() and p.name.endswith('.log')]
         log_paths.sort(key=lambda p: p.stat().st_mtime, reverse=True); log_files = [p.name for p in log_paths]
    except FileNotFoundError: print(f"W: Log directory not found at {LOG_FOLDER_PATH}", file=sys.stderr)
    except Exception as e: print(f"Error listing logs: {e}", file=sys.stderr)
    return render_template_string(template, logs=log_files, log_folder_name=LOG_FOLDER) # Pass relative name for display

@app.route('/logs/<path:filename>')
def serve_log(filename):
    print(f"Request received for log file: {filename}", file=sys.stderr)
    log_dir = LOG_FOLDER_PATH.resolve(); requested_path = (log_dir / filename).resolve()
    # Security check: Ensure resolved path is still within the intended log directory (now relative to CWD)
    if not str(requested_path).startswith(str(log_dir)) or '..' in filename or filename.startswith(('/', '\\')): return "Forbidden", 403
    try: return send_from_directory(LOG_FOLDER_PATH, filename, mimetype='text/plain', as_attachment=False)
    except FileNotFoundError: return "Log file not found", 404
    except Exception as e: print(f"Error serving log file {filename}: {e}", file=sys.stderr); return "Error serving file", 500

if __name__ == '__main__':
    host_ip = '127.0.0.1'; port_num = SERVER_PORT
    print(f"Starting Flask server on http://{host_ip}:{port_num}", file=sys.stderr)
    print(f"Server CWD (Git Root): {SERVER_DIR}", file=sys.stderr) # Changed label
    print(f"Saving non-Git files to: {SAVE_FOLDER_PATH}", file=sys.stderr) # Path is now relative to CWD
    print(f"Saving logs to: {LOG_FOLDER_PATH}", file=sys.stderr) # Path is now relative to CWD
    # print(f"Assuming extension files live in: {EXTENSION_DIR_PATH}", file=sys.stderr) # No longer needed
    print(f"This script name: {THIS_SCRIPT_NAME}", file=sys.stderr)
    print("Will use filename from '@@FILENAME@@' marker if present and valid.", file=sys.stderr)
    if IS_REPO: print("Git integration ENABLED. Will update tracked files and commit.")
    else: print("Git integration DISABLED (Not in a Git repo or git command failed).")
    print("Will attempt language detection for fallback filename extensions.", file=sys.stderr)
    print("*** CORS enabled for all origins ***")
    print("!!! Server requests will be serialized using a lock to prevent Git conflicts. !!!", file=sys.stderr)
    try: app.run(host=host_ip, port=port_num, debug=False)
    except OSError as e:
        if "Address already in use" in str(e) or "WinError 10048" in str(e):
            print(f"\nE: Address already in use.\nPort {port_num} is in use by another program.", file=sys.stderr)
            print(f"Stop the other program or start this server with a different port using: python {THIS_SCRIPT_NAME} -p {port_num + 1}\n", file=sys.stderr)
            sys.exit(1)
        else: raise
# --- END OF FILE server.py ---