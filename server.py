from flask import Flask, request, jsonify, send_from_directory, render_template_string
import os
import datetime
import subprocess

app = Flask(__name__)

SAVE_FOLDER = 'received_codes'
LOG_FOLDER = 'logs'
os.makedirs(SAVE_FOLDER, exist_ok=True)
os.makedirs(LOG_FOLDER, exist_ok=True)

AUTO_RUN_ON_SYNTAX_OK = True

def generate_filename():
    today = datetime.datetime.now().strftime("%Y%m%d")
    counter = 1
    while True:
        filename = f"python_code_{today}_{counter:03d}.py"
        filepath = os.path.join(SAVE_FOLDER, filename)
        if not os.path.exists(filepath):
            return filepath
        counter += 1

def run_script(filepath):
    filename_base = os.path.splitext(os.path.basename(filepath))[0]
    logpath = os.path.join(LOG_FOLDER, f"{filename_base}.log")

    try:
        result = subprocess.run(
            ['python', filepath],
            capture_output=True,
            text=True,
            timeout=10
        )
        with open(logpath, 'w', encoding='utf-8') as f:
            f.write(f"--- STDOUT ---\n{result.stdout}\n")
            f.write(f"--- STDERR ---\n{result.stderr}\n")
        return True, logpath
    except subprocess.TimeoutExpired:
        with open(logpath, 'w', encoding='utf-8') as f:
            f.write("Error: Script timed out after 10 seconds.\n")
        return False, logpath
    except Exception as e:
        with open(logpath, 'w', encoding='utf-8') as f:
            f.write(f"Error running script: {str(e)}\n")
        return False, logpath

@app.route('/submit_code', methods=['POST'])
def submit_code():
    data = request.get_json()
    code = data.get('code', '')

    if not code.strip():
        return jsonify({'status': 'error', 'message': 'Empty code received'}), 400

    filepath = generate_filename()
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(code)

    try:
        compile(code, filepath, 'exec')
        syntax_ok = True
    except SyntaxError:
        syntax_ok = False

    logpath = None
    if syntax_ok and AUTO_RUN_ON_SYNTAX_OK:
        _, logpath = run_script(filepath)

    return jsonify({
        'status': 'success',
        'syntax_ok': syntax_ok,
        'saved_as': os.path.basename(filepath),
        'log_file': os.path.basename(logpath) if logpath else None
    })

@app.route('/logs')
def list_logs():
    log_files = sorted(os.listdir(LOG_FOLDER), reverse=True)
    template = '''
    <html>
    <head>
      <title>Logs Browser</title>
      <style>
        body { font-family: Arial, sans-serif; background: #111; color: #eee; padding: 20px; }
        h1 { color: #00ff99; }
        a { color: #00ccff; text-decoration: none; }
        a:hover { text-decoration: underline; }
        pre { background: #222; padding: 10px; border-radius: 8px; overflow-x: auto; }
      </style>
    </head>
    <body>
      <h1>🗂 Available Logs</h1>
      <ul>
        {% for log in logs %}
          <li><a href="/logs/{{ log }}">{{ log }}</a></li>
        {% endfor %}
      </ul>
    </body>
    </html>
    '''
    return render_template_string(template, logs=log_files)

@app.route('/logs/<path:filename>')
def serve_log(filename):
    return send_from_directory(LOG_FOLDER, filename)

if __name__ == '__main__':
    app.run(port=5000)