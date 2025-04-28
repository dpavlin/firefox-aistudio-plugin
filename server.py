from flask import Flask, request, jsonify, send_from_directory, render_template_string
import os
import datetime
import subprocess
import re # Added for regex
import sys # Added for stderr printing and sys.executable
from pathlib import Path # Added for path handling

app = Flask(__name__)

SAVE_FOLDER = 'received_codes'
LOG_FOLDER = 'logs'
os.makedirs(SAVE_FOLDER, exist_ok=True)
os.makedirs(LOG_FOLDER, exist_ok=True)

# --- Regex to EXTRACT filename FROM START MARKER ---
# Captures filename in group 1. Looks at the beginning of the string.
FILENAME_EXTRACT_REGEX = re.compile(r"^\s*// --- START OF FILE (.+?) ---\s*\n", re.IGNORECASE)

# --- Filename Sanitization (copied from previous version) ---
FILENAME_SANITIZE_REGEX = re.compile(r'[^a-zA-Z0-9._-]')
MAX_FILENAME_LENGTH = 100

def sanitize_filename(filename: str) -> str | None:
    """Cleans a filename extracted from the code or provided by the client."""
    if not filename or filename.isspace():
        return None
    if '..' in filename or filename.startswith('/'):
        print(f"Warning: Rejected potentially unsafe filename pattern: {filename}", file=sys.stderr)
        return None
    filename = os.path.basename(filename)
    if filename.startswith('.'):
        print(f"Warning: Rejected filename starting with '.': {filename}", file=sys.stderr)
        return None
    sanitized = FILENAME_SANITIZE_REGEX.sub('_', filename)
    if len(sanitized) > MAX_FILENAME_LENGTH:
        base, ext = os.path.splitext(sanitized)
        base = base[:MAX_FILENAME_LENGTH - len(ext) - 1]
        sanitized = f"{base}{ext}"
    # Ensure it ends with a common code extension if not already present - adjust as needed
    # This is less critical here as we primarily use it for git lookup
    # if not any(sanitized.endswith(ext) for ext in ['.py', '.js', '.html', '.css', '.json', '.md', '.txt']):
    #      # Avoid adding extension if base name is empty
    #      if not os.path.splitext(sanitized)[0]:
    #          return None
    #      # Default or decide based on content? For now, just keep as is or add .txt?
    #      # sanitized += ".txt" # Example default
    #      pass # Let's allow other extensions found in marker for now
    if not os.path.splitext(sanitized)[0]:
         return None
    return sanitized

# --- Git Content Fetching (copied from previous version) ---
def get_git_committed_content(filename_relative: str) -> str | None:
    """Retrieves the content of a file from the HEAD commit using git show."""
    # Use relative path for git show command
    # Ensure forward slashes for git compatibility
    filepath_git = Path(filename_relative).as_posix()

    command = ['git', 'show', f'HEAD:{filepath_git}']
    print(f"Running git command: {' '.join(command)}", file=sys.stderr)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=False
        )
        if result.returncode != 0:
            print(f"Info: git show failed for '{filepath_git}' (return code {result.returncode}). Maybe file not committed or path differs?", file=sys.stderr)
            # print(result.stderr, file=sys.stderr) # Optional: show git error
            return None
        print(f"Successfully fetched content for '{filepath_git}' from HEAD.", file=sys.stderr)
        return result.stdout
    except FileNotFoundError:
        print("Error: 'git' command not found. Is Git installed and in your PATH?", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error running git show for '{filepath_git}': {e}", file=sys.stderr)
        return None


AUTO_RUN_ON_SYNTAX_OK = True # Original setting

# --- Original Filename Generation (used for SAVING) ---
def generate_timestamped_filepath():
    """Generates a unique filepath based on timestamp."""
    today = datetime.datetime.now().strftime("%Y%m%d")
    counter = 1
    while True:
        filename = f"python_code_{today}_{counter:03d}.py"
        filepath = os.path.join(SAVE_FOLDER, filename)
        if not os.path.exists(filepath):
            return filepath # Return the full path
        counter += 1

# --- Original Script Runner ---
def run_script(filepath):
    """Runs the python script and captures output."""
    filename_base = os.path.splitext(os.path.basename(filepath))[0]
    logpath = os.path.join(LOG_FOLDER, f"{filename_base}.log")

    try:
        python_exe = sys.executable
        result = subprocess.run(
            [python_exe, filepath],
            capture_output=True,
            text=True,
            timeout=10,
            encoding='utf-8',
            check=False
        )
        with open(logpath, 'w', encoding='utf-8') as f:
            f.write(f"--- STDOUT ---\n{result.stdout}\n")
            f.write(f"--- STDERR ---\n{result.stderr}\n")
            f.write(f"--- Return Code: {result.returncode} ---\n")
        return result.returncode == 0, logpath
    except subprocess.TimeoutExpired:
        with open(logpath, 'w', encoding='utf-8') as f:
            f.write("Error: Script timed out after 10 seconds.\n")
        return False, logpath
    except Exception as e:
        with open(logpath, 'w', encoding='utf-8') as f:
            f.write(f"Error running script: {str(e)}\n")
        return False, logpath

# --- Modified Submit Route ---
@app.route('/submit_code', methods=['POST'])
def submit_code():
    data = request.get_json()
    if not data:
        print("Error: No JSON data received.", file=sys.stderr)
        return jsonify({'status': 'error', 'message': 'No JSON data received'}), 400

    original_code = data.get('code', '') # Get the code sent by the extension

    if not original_code or original_code.isspace():
        print("Error: Empty code received.", file=sys.stderr)
        return jsonify({'status': 'error', 'message': 'Empty code received'}), 400

    code_to_save = original_code # Start with the original code
    extracted_filename = None

    # --- Try to extract filename and replace code from Git ---
    match = FILENAME_EXTRACT_REGEX.search(original_code)
    if match:
        raw_filename = match.group(1).strip()
        print(f"Found filename marker: '{raw_filename}'", file=sys.stderr)
        extracted_filename = sanitize_filename(raw_filename) # Sanitize before use

        if extracted_filename:
            print(f"Sanitized filename for Git lookup: '{extracted_filename}'", file=sys.stderr)
            # Attempt to fetch content from Git HEAD based on the sanitized name
            git_content = get_git_committed_content(extracted_filename)
            if git_content is not None:
                print(f"Replacing received code with Git HEAD version of '{extracted_filename}'.", file=sys.stderr)
                # IMPORTANT: Replace the code content we intend to save and run
                code_to_save = git_content
                # Optional: Remove the start/end markers if they exist in git_content?
                # git_content = remove_markers(git_content) # Need a function for this if desired
            else:
                print(f"Warning: Could not get Git content for '{extracted_filename}'. Using code as received.", file=sys.stderr)
                # code_to_save remains original_code
                # Optionally, strip the marker from original_code if needed?
                # code_to_save = original_code[match.end():] # Example: strip marker if git fails
        else:
            print(f"Warning: Extracted filename '{raw_filename}' was invalid after sanitization. Using code as received.", file=sys.stderr)
            # code_to_save remains original_code
    else:
        print("Info: No filename marker found at start of received code. Using code as received.", file=sys.stderr)
        # code_to_save remains original_code

    # --- Generate SAVING filepath (always timestamped in this version) ---
    save_filepath = generate_timestamped_filepath()
    save_filename = os.path.basename(save_filepath)
    print(f"Generated filepath for saving: '{save_filepath}'", file=sys.stderr)

    # --- Save the final code (original or from Git) ---
    try:
        os.makedirs(SAVE_FOLDER, exist_ok=True)
        with open(save_filepath, 'w', encoding='utf-8') as f:
            f.write(code_to_save) # Write the potentially modified code
        print(f"Code saved successfully to {save_filepath}", file=sys.stderr)
    except Exception as e:
        print(f"Error: Failed to save file '{save_filepath}': {str(e)}", file=sys.stderr)
        return jsonify({'status': 'error', 'message': f'Failed to save file: {str(e)}'}), 500

    # --- Check Syntax and Optionally Run (using the saved file) ---
    syntax_ok = False
    run_success = None
    logpath = None
    log_filename = None

    try:
        compile(code_to_save, save_filepath, 'exec') # Compile the code we saved
        syntax_ok = True
        print(f"Syntax OK for {save_filename}", file=sys.stderr)
        if AUTO_RUN_ON_SYNTAX_OK:
            print(f"Attempting to run {save_filename}", file=sys.stderr)
            run_success, logpath = run_script(save_filepath) # Run the saved file
            log_filename = os.path.basename(logpath) if logpath else None
            print(f"Script run completed. Success: {run_success}, Log: {log_filename}", file=sys.stderr)

    except SyntaxError as e:
        syntax_ok = False
        print(f"Syntax Error in {save_filename}: Line {e.lineno}, Offset: {e.offset}, Message: {e.msg}", file=sys.stderr)
        log_filename_base = os.path.splitext(save_filename)[0]
        logpath_err = os.path.join(LOG_FOLDER, f"{log_filename_base}_syntax_error.log")
        try:
            os.makedirs(LOG_FOLDER, exist_ok=True)
            with open(logpath_err, 'w', encoding='utf-8') as f:
                 f.write(f"Syntax Error:\nFile: {save_filename} (Original Marker: {raw_filename if match else 'None'})\nLine: {e.lineno}, Offset: {e.offset}\nMessage: {e.msg}\nCode Context:\n{e.text}")
            log_filename = os.path.basename(logpath_err)
        except Exception as log_e:
             print(f"Error writing syntax error log for {save_filename}: {log_e}", file=sys.stderr)

    except Exception as compile_e:
        syntax_ok = False
        run_success = False
        print(f"Error during compile/run setup for {save_filename}: {str(compile_e)}", file=sys.stderr)
        log_filename_base = os.path.splitext(save_filename)[0]
        logpath_err = os.path.join(LOG_FOLDER, f"{log_filename_base}_compile_error.log")
        try:
             os.makedirs(LOG_FOLDER, exist_ok=True)
             with open(logpath_err, 'w', encoding='utf-8') as f:
                 f.write(f"Error during compile/run setup:\nFile: {save_filename} (Original Marker: {raw_filename if match else 'None'})\nError: {str(compile_e)}\n")
             log_filename = os.path.basename(logpath_err)
        except Exception as log_e:
             print(f"Error writing compile error log for {save_filename}: {log_e}", file=sys.stderr)

    # --- Return Response ---
    response_data = {
        'status': 'success',
        'syntax_ok': syntax_ok,
        'saved_as': save_filename, # Report the timestamped name it was saved as
        'log_file': log_filename,
        'source_file_marker': raw_filename if match else None, # Indicate if marker was found
        'used_git_content': (git_content is not None) if match and extracted_filename else False # Indicate if git content replaced original
    }
    if run_success is not None:
        response_data['run_success'] = run_success

    print(f"Sending response: {response_data}", file=sys.stderr)
    return jsonify(response_data)

# --- Original Log Routes ---
@app.route('/logs')
def list_logs():
    # (Keep the improved version from the previous iteration)
    log_files = []
    try:
         log_dir = os.path.abspath(LOG_FOLDER)
         log_paths = [os.path.join(log_dir, f) for f in os.listdir(log_dir) if f.endswith('.log')]
         log_paths.sort(key=lambda x: os.path.getmtime(x), reverse=True)
         log_files = [os.path.basename(p) for p in log_paths]
    except FileNotFoundError:
         print("Log directory not found.", file=sys.stderr)
         pass
    except Exception as e:
         print(f"Error listing logs: {e}", file=sys.stderr)

    template = '''
    <!DOCTYPE html>
    <html>
    <head>
      <title>Logs Browser</title>
      <style>
        body { font-family: Arial, sans-serif; background: #1e1e1e; color: #d4d4d4; padding: 20px; }
        h1 { color: #4ec9b0; border-bottom: 1px solid #444; padding-bottom: 10px; }
        ul { list-style: none; padding: 0; }
        li { background: #252526; margin-bottom: 8px; border-radius: 4px; }
        li a { color: #9cdcfe; text-decoration: none; display: block; padding: 10px 15px; transition: background-color 0.2s ease; }
        li a:hover { background-color: #333; }
        p { color: #888; }
        pre { background: #1e1e1e; border: 1px solid #444; padding: 15px; border-radius: 5px; overflow-x: auto; white-space: pre-wrap; word-wrap: break-word; color: #d4d4d4;}
      </style>
    </head>
    <body>
      <h1>🗂️ Available Logs</h1>
      {% if logs %}
      <ul>
        {% for log in logs %}
          <li><a href="/logs/{{ log | urlencode }}">{{ log }}</a></li>
        {% endfor %}
      </ul>
      {% else %}
      <p>No logs found in '{{ log_folder_name }}'.</p>
      {% endif %}
    </body>
    </html>
    '''
    return render_template_string(template, logs=log_files, log_folder_name=LOG_FOLDER)

@app.route('/logs/<path:filename>')
def serve_log(filename):
    # (Keep the improved version from the previous iteration)
    print(f"Request received for log file: {filename}", file=sys.stderr)
    log_dir = os.path.abspath(LOG_FOLDER)
    requested_path = os.path.abspath(os.path.join(log_dir, filename))
    if not requested_path.startswith(log_dir) or '..' in filename:
         print(f"Warning: Forbidden access attempt for log: {filename}", file=sys.stderr)
         return "Forbidden", 403
    try:
        return send_from_directory(LOG_FOLDER, filename, mimetype='text/plain', as_attachment=False)
    except FileNotFoundError:
         print(f"Error: Log file not found: {filename}", file=sys.stderr)
         return "Log file not found", 404
    except Exception as e:
        print(f"Error serving log file {filename}: {e}", file=sys.stderr)
        return "Error serving file", 500


if __name__ == '__main__':
    host_ip = '127.0.0.1'
    port_num = 5000
    print(f"Starting Flask server on http://{host_ip}:{port_num}", file=sys.stderr)
    print("Server will attempt to replace received code with Git HEAD version if start marker is found.", file=sys.stderr)
    app.run(host=host_ip, port=port_num, debug=False)