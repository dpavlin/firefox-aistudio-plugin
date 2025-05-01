# @@FILENAME@@ routes/logs.py
from flask import Blueprint, render_template_string, send_from_directory, current_app # Added Blueprint import
import sys

logs_bp = Blueprint('logs_bp', __name__)

@logs_bp.route('/logs')
def list_logs():
    """Provides an HTML page listing available log files."""
    config = current_app.config['APP_CONFIG']
    log_folder_path = config['LOG_FOLDER_PATH']
    log_files = []
    template = '''<!DOCTYPE html><html><head><title>Logs Browser</title><style>body{font-family:sans-serif;background-color:#f4f4f4;color:#333;margin:0;padding:20px}h1{color:#444;border-bottom:1px solid #ccc;padding-bottom:10px}ul{list-style:none;padding:0}li{background-color:#fff;margin-bottom:8px;border:1px solid #ddd;border-radius:4px;transition:box-shadow .2s ease-in-out}li:hover{box-shadow:0 2px 5px rgba(0,0,0,.1)}li a{color:#007bff;text-decoration:none;display:block;padding:12px 15px}li a:hover{background-color:#eee}p{color:#666}pre{background-color:#eee;border:1px solid #ccc;padding:15px;border-radius:5px;overflow-x:auto;white-space:pre-wrap;word-wrap:break-word;font-family:monospace}</style></head><body><h1>🗂️ Available Logs</h1>{% if logs %}<p>Found {{ logs|length }} log file(s) in '{{ log_folder_name }}'. Click to view.</p><ul>{% for log in logs %}<li><a href="/logs/{{ log | urlencode }}">{{ log }}</a></li>{% endfor %}</ul>{% else %}<p>No log files found in '{{ log_folder_name }}'.</p>{% endif %}</body></html>'''
    try:
         if log_folder_path.is_dir():
             log_paths = [p for p in log_folder_path.glob('*.log') if p.is_file()]
             log_paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
             log_files = [p.name for p in log_paths]
    except Exception as e: print(f"E: Error listing log files: {e}", file=sys.stderr)
    return render_template_string(template, logs=log_files, log_folder_name=log_folder_path.name)


@logs_bp.route('/logs/<path:filename>')
def serve_log(filename):
    """Serves a specific log file as plain text."""
    config = current_app.config['APP_CONFIG']
    log_folder_path = config['LOG_FOLDER_PATH']

    if '..' in filename or filename.startswith('/'): return "Forbidden", 403
    try:
        log_dir = log_folder_path.resolve()
        requested_path = (log_dir / filename).resolve()
        if not str(requested_path).startswith(str(log_dir)) or not requested_path.is_file():
            return "Log file not found", 404
        return send_from_directory(log_folder_path, filename, mimetype='text/plain; charset=utf-8', as_attachment=False)
    except Exception as e: print(f"E: Error serving log file {filename}: {e}", file=sys.stderr); return "Error serving file", 500
# @@FILENAME@@ routes/logs.py