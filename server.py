# --- START OF FILE server.py ---
from flask import Flask, request, jsonify, send_from_directory, render_template_string
from flask_cors import CORS # Import CORS
import os
import datetime
import subprocess
import re
import sys
from pathlib import Path

app = Flask(__name__)
CORS(app) # Enable CORS for all routes by default

SAVE_FOLDER = 'received_codes'
LOG_FOLDER = 'logs'
os.makedirs(SAVE_FOLDER, exist_ok=True)
os.makedirs(LOG_FOLDER, exist_ok=True)

# --- Regex to EXTRACT filename FROM START MARKER ---
FILENAME_EXTRACT_REGEX = re.compile(
    r"^\s*(?://|#|--|\*)\s*--- START OF FILE (.+?) ---\s*\n",
    re.IGNORECASE
)

# --- Filename Sanitization ---
FILENAME_SANITIZE_REGEX = re.compile(r'[^a-zA-Z0-9._-]')
MAX_FILENAME_LENGTH = 100

def sanitize_filename(filename: str) -> str | None:
    """
    Cleans a filename extracted from the code marker.
    - Removes directory components.
    - Rejects filenames starting with '.' (hidden files).
    - Replaces unsafe characters with underscores.
    - Enforces max length.
    - Returns the sanitized filename or None if it's fundamentally invalid.
    (Extension is preserved from the original marker)
    """
    if not filename or filename.isspace():
        return None

    # Basic check for directory traversal attempts before basename
    if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
        print(f"Warning: Rejected potentially unsafe filename pattern: {filename}", file=sys.stderr)
        return None

    # Get only the filename part, removing any directory paths
    filename = os.path.basename(filename)

    # Reject hidden files or invalid starting characters
    if filename.startswith('.'):
        print(f"Warning: Rejected filename starting with '.': {filename}", file=sys.stderr)
        return None

    # Replace potentially unsafe characters with underscores
    sanitized = FILENAME_SANITIZE_REGEX.sub('_', filename)

    # Enforce maximum length
    if len(sanitized) > MAX_FILENAME_LENGTH:
        base, ext = os.path.splitext(sanitized)
        if len(ext) > (MAX_FILENAME_LENGTH - 2): # Prevent huge extension from breaking logic
             ext = ext[:MAX_FILENAME_LENGTH - 2] + "~" # Truncate extension too if needed
        base = base[:MAX_FILENAME_LENGTH - len(ext) - 1] # Truncate base part
        sanitized = f"{base}{ext}"

    # Final check for empty name after sanitization (e.g., input was just unsafe chars)
    if not os.path.splitext(sanitized)[0] and len(sanitized) <= 1: # Allow just extension like '.gitignore'
         return None

    return sanitized


def find_unique_filepath(suggested_filename: str) -> str:
    """
    Takes a sanitized suggested filename and finds a unique path in SAVE_FOLDER,
    appending _1, _2, etc., if necessary to avoid collisions.
    """
    base, ext = os.path.splitext(suggested_filename)
    counter = 1
    filepath = Path(SAVE_FOLDER) / suggested_filename # Use Path object

    while filepath.exists():
        filename = f"{base}_{counter}{ext}"
        filepath = Path(SAVE_FOLDER) / filename
        counter += 1
    return str(filepath) # Return as string


def generate_timestamped_py_filepath():
    """Generates a unique python filepath based on timestamp (Fallback)."""
    today = datetime.datetime.now().strftime("%Y%m%d")
    counter = 1
    while True:
        filename = f"python_code_{today}_{counter:03d}.py"
        filepath = os.path.join(SAVE_FOLDER, filename)
        if not os.path.exists(filepath):
            return filepath # Return the full path
        counter += 1

AUTO_RUN_ON_SYNTAX_OK = True # Original setting

def run_script(filepath):
    """Runs the python script and captures output."""
    filename_base = Path(filepath).stem # Use pathlib for cleaner base name
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
        os.makedirs(LOG_FOLDER, exist_ok=True) # Ensure log folder exists
        with open(logpath, 'w', encoding='utf-8') as f:
            f.write(f"--- STDOUT ---\n{result.stdout}\n")
            f.write(f"--- STDERR ---\n{result.stderr}\n")
            f.write(f"--- Return Code: {result.returncode} ---\n")
        return result.returncode == 0, logpath
    except subprocess.TimeoutExpired:
        os.makedirs(LOG_FOLDER, exist_ok=True)
        with open(logpath, 'w', encoding='utf-8') as f:
            f.write("Error: Script timed out after 10 seconds.\n")
        return False, logpath
    except Exception as e:
        os.makedirs(LOG_FOLDER, exist_ok=True)
        with open(logpath, 'w', encoding='utf-8') as f:
            f.write(f"Error running script: {str(e)}\n")
        return False, logpath

@app.route('/submit_code', methods=['POST', 'OPTIONS']) # Allow OPTIONS method
def submit_code():
    # Handle OPTIONS preflight request (Flask-CORS should mostly handle this,
    # but explicit handling can sometimes be needed depending on exact config)
    if request.method == 'OPTIONS':
        # Flask-CORS adds headers, so we can just return an empty OK response
        return '', 204 # Use 204 No Content for OPTIONS is common

    # Handle POST request
    if request.method == 'POST':
        data = request.get_json()
        if not data:
            print("Error: No JSON data received.", file=sys.stderr)
            return jsonify({'status': 'error', 'message': 'No JSON data received'}), 400

        received_code = data.get('code', '')

        if not received_code or received_code.isspace():
            print("Error: Empty code received.", file=sys.stderr)
            return jsonify({'status': 'error', 'message': 'Empty code received'}), 400

        save_filepath = None
        final_save_filename = None
        extracted_filename_raw = None
        is_likely_python = False

        # Determine filename and type
        match = FILENAME_EXTRACT_REGEX.search(received_code)
        if match:
            extracted_filename_raw = match.group(1).strip()
            print(f"Found filename marker: '{extracted_filename_raw}'", file=sys.stderr)
            sanitized = sanitize_filename(extracted_filename_raw)
            if sanitized:
                print(f"Sanitized filename: '{sanitized}'", file=sys.stderr)
                save_filepath = find_unique_filepath(sanitized)
                final_save_filename = os.path.basename(save_filepath)
                is_likely_python = final_save_filename.lower().endswith('.py')
                print(f"Using unique filepath: '{save_filepath}', is_python: {is_likely_python}", file=sys.stderr)
            else:
                print(f"Warning: Invalid extracted filename '{extracted_filename_raw}'. Falling back to timestamped Python name.", file=sys.stderr)
                save_filepath = generate_timestamped_py_filepath()
                final_save_filename = os.path.basename(save_filepath)
                is_likely_python = True
                print(f"Using generated filepath: '{save_filepath}'", file=sys.stderr)
        else:
            print("Info: No filename marker found. Saving as timestamped Python file.", file=sys.stderr)
            save_filepath = generate_timestamped_py_filepath()
            final_save_filename = os.path.basename(save_filepath)
            is_likely_python = True
            print(f"Using generated filepath: '{save_filepath}'", file=sys.stderr)

        # Save the received code
        try:
            os.makedirs(SAVE_FOLDER, exist_ok=True)
            with open(save_filepath, 'w', encoding='utf-8') as f:
                f.write(received_code)
            print(f"Code saved successfully to {save_filepath}", file=sys.stderr)
        except Exception as e:
             print(f"Error: Failed to save file '{save_filepath}': {str(e)}", file=sys.stderr)
             return jsonify({'status': 'error', 'message': f'Failed to save file: {str(e)}'}), 500

        # Check Syntax and Optionally Run ONLY if it's a Python file
        syntax_ok = None
        run_success = None
        log_filename = None

        if is_likely_python:
            print(f"File '{final_save_filename}' is Python, performing checks.", file=sys.stderr)
            try:
                compile(received_code, save_filepath, 'exec')
                syntax_ok = True
                print(f"Syntax OK for {final_save_filename}", file=sys.stderr)
                if AUTO_RUN_ON_SYNTAX_OK:
                    print(f"Attempting to run {final_save_filename}", file=sys.stderr)
                    run_success, logpath = run_script(save_filepath)
                    log_filename = os.path.basename(logpath) if logpath else None
                    print(f"Script run completed. Success: {run_success}, Log: {log_filename}", file=sys.stderr)

            except SyntaxError as e:
                syntax_ok = False
                print(f"Syntax Error in {final_save_filename}: Line {e.lineno}, Offset: {e.offset}, Message: {e.msg}", file=sys.stderr)
                log_filename_base = Path(save_filepath).stem
                logpath_err = os.path.join(LOG_FOLDER, f"{log_filename_base}_syntax_error.log")
                try:
                    os.makedirs(LOG_FOLDER, exist_ok=True)
                    with open(logpath_err, 'w', encoding='utf-8') as f:
                         f.write(f"Syntax Error:\nFile: {final_save_filename} (Marker: {extracted_filename_raw or 'None'})\nLine: {e.lineno}, Offset: {e.offset}\nMessage: {e.msg}\nCode Context:\n{e.text}")
                    log_filename = os.path.basename(logpath_err)
                except Exception as log_e:
                     print(f"Error writing syntax error log for {final_save_filename}: {log_e}", file=sys.stderr)

            except Exception as compile_e:
                syntax_ok = False
                run_success = False
                print(f"Error during compile/run setup for {final_save_filename}: {str(compile_e)}", file=sys.stderr)
                log_filename_base = Path(save_filepath).stem
                logpath_err = os.path.join(LOG_FOLDER, f"{log_filename_base}_compile_error.log")
                try:
                     os.makedirs(LOG_FOLDER, exist_ok=True)
                     with open(logpath_err, 'w', encoding='utf-8') as f:
                         f.write(f"Error during compile/run setup:\nFile: {final_save_filename} (Marker: {extracted_filename_raw or 'None'})\nError: {str(compile_e)}\n")
                     log_filename = os.path.basename(logpath_err)
                except Exception as log_e:
                     print(f"Error writing compile error log for {final_save_filename}: {log_e}", file=sys.stderr)
        else:
            print(f"File '{final_save_filename}' is not Python, skipping syntax check and run.", file=sys.stderr)

        # Return Response
        response_data = {
            'status': 'success',
            'saved_as': final_save_filename,
            'log_file': log_filename,
            'syntax_ok': syntax_ok,
            'run_success': run_success,
            'source_file_marker': extracted_filename_raw
        }
        print(f"Sending response: {response_data}", file=sys.stderr)
        return jsonify(response_data)

    # Should not be reached if only POST/OPTIONS allowed
    return jsonify({'status': 'error', 'message': f'Unsupported method: {request.method}'}), 405


@app.route('/logs')
def list_logs():
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
          <li><a href="/logs/{{ log | urlencode }}">{{ log }}</a></li> {# Ensure filename is URL encoded #}
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
    print(f"Saving received files to: {Path(SAVE_FOLDER).resolve()}", file=sys.stderr)
    print(f"Saving logs to: {Path(LOG_FOLDER).resolve()}", file=sys.stderr)
    print("Will use filename from start marker if present and valid.", file=sys.stderr)
    print("*** CORS enabled for all origins ***") # Indicate CORS is active
    app.run(host=host_ip, port=port_num, debug=False)