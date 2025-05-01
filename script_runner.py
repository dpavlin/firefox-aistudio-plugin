# @@FILENAME@@ script_runner.py
import subprocess
import sys
from pathlib import Path
import os
import shutil # For shutil.which

# Note: Requires config dict containing LOG_FOLDER_PATH passed to functions

def _write_log(log_path: Path, content: str):
    """Helper to write log file, creates directory."""
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(content, encoding='utf-8')
    except Exception as log_e:
        print(f"E: Failed to write log file '{log_path}': {log_e}", file=sys.stderr)

def run_script(filepath: str, script_type: str, log_folder_path: Path) -> tuple[bool, str | None]:
    """Runs a Python or Shell script, logs output."""
    filepath_obj = Path(filepath).resolve()
    if not filepath_obj.is_file():
        print(f"E: Script file not found for execution: {filepath_obj}", file=sys.stderr)
        return False, None

    filename_base = filepath_obj.stem
    logpath = log_folder_path / f"{filename_base}_{script_type}_run.log"
    run_cwd = filepath_obj.parent

    command = []
    interpreter_name = ""
    log_content = "" # Initialize log content

    if script_type == 'python':
        python_exe = sys.executable or shutil.which("python3") or shutil.which("python") or "python"
        if not shutil.which(python_exe):
             err_msg = f"Error: Python interpreter '{python_exe}' not found.\n"
             print(f"E: {err_msg.strip()}", file=sys.stderr)
             _write_log(logpath, err_msg); return False, str(logpath)
        command = [python_exe, str(filepath_obj)]
        interpreter_name = Path(python_exe).name
        print(f"Executing Python ({interpreter_name}): {' '.join(command)} in '{run_cwd}'", file=sys.stderr)
    elif script_type == 'shell':
        shell_exe = shutil.which("bash") or shutil.which("sh")
        if not shell_exe:
             err_msg = "Error: No 'bash' or 'sh' interpreter found.\n"
             print(f"E: {err_msg.strip()}", file=sys.stderr)
             _write_log(logpath, err_msg); return False, str(logpath)
        command = [shell_exe, str(filepath_obj)]
        interpreter_name = Path(shell_exe).name
        print(f"Executing Shell ({interpreter_name}): {' '.join(command)} in '{run_cwd}'", file=sys.stderr)
    else:
        print(f"E: Cannot run script of unknown type '{script_type}' for {filepath}", file=sys.stderr)
        return False, None

    log_content += f"--- COMMAND ---\n{' '.join(command)}\n--- CWD ---\n{run_cwd}\n"
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, encoding='utf-8', check=False, cwd=run_cwd)
        log_content += f"--- STDOUT ---\n{result.stdout}\n--- STDERR ---\n{result.stderr}\n--- Return Code: {result.returncode} ---\n"
        _write_log(logpath, log_content)
        print(f"Exec finished ({script_type}). RC: {result.returncode}. Log: {logpath.name}", file=sys.stderr)
        return result.returncode == 0, str(logpath)
    except subprocess.TimeoutExpired:
        print(f"E: Script timed out after 15 seconds: {filepath_obj.name}", file=sys.stderr)
        log_content += f"--- ERROR ---\nScript execution timed out after 15 seconds.\n"
        _write_log(logpath, log_content)
        return False, str(logpath)
    except FileNotFoundError:
        err_msg = f"--- ERROR ---\nScript file '{filepath_obj}' or CWD '{run_cwd}' not found during execution.\n"
        print(f"E: {err_msg.strip()}", file=sys.stderr)
        log_content += err_msg
        _write_log(logpath, log_content)
        return False, str(logpath)
    except Exception as e:
        err_msg = f"--- ERROR ---\nUnexpected error during script execution:\n{e}\n"
        print(f"E: Unexpected error running script {filepath_obj.name}: {e}", file=sys.stderr)
        log_content += err_msg
        _write_log(logpath, log_content)
        return False, str(logpath)

def check_shell_syntax(filepath: str, log_folder_path: Path) -> tuple[bool, str | None]:
    """Checks shell script syntax using 'bash -n'. Returns (syntax_ok, log_path)."""
    filepath_obj = Path(filepath).resolve()
    if not filepath_obj.is_file():
        print(f"E: Shell script file not found for syntax check: {filepath_obj}", file=sys.stderr)
        return False, None

    filename_base = filepath_obj.stem
    logpath = log_folder_path / f"{filename_base}_shell_syntax.log"

    checker_exe = shutil.which("bash")
    if not checker_exe:
        err_msg = "Error: 'bash' command not found for syntax check.\n"
        print(f"W: {err_msg.strip()}", file=sys.stderr)
        _write_log(logpath, err_msg); return False, str(logpath)

    command = [checker_exe, '-n', str(filepath_obj)]
    log_content = f"--- COMMAND ---\n{' '.join(command)}\n"
    print(f"Checking Shell syntax: {' '.join(command)}", file=sys.stderr)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, encoding='utf-8', check=False)
        syntax_ok = result.returncode == 0
        status_msg = "OK" if syntax_ok else f"ERROR (RC: {result.returncode})"
        log_content += f"--- STATUS: {status_msg} ---\n--- STDOUT ---\n{result.stdout}\n--- STDERR ---\n{result.stderr}\n"
        _write_log(logpath, log_content)
        if syntax_ok: print(f"Shell syntax OK for {filepath_obj.name}", file=sys.stderr)
        else: print(f"Shell syntax Error for {filepath_obj.name}. RC: {result.returncode}. Log: {logpath.name}", file=sys.stderr)
        return syntax_ok, str(logpath)
    except FileNotFoundError:
        err_msg = f"--- ERROR ---\nSyntax check command '{checker_exe}' not found during execution.\n"
        print(f"E: {err_msg.strip()}", file=sys.stderr)
        log_content += err_msg
        _write_log(logpath, log_content); return False, str(logpath)
    except subprocess.TimeoutExpired:
        err_msg = "--- ERROR ---\nShell syntax check timed out after 10 seconds.\n"
        print(f"E: Shell syntax check timed out for {filepath_obj.name}", file=sys.stderr)
        log_content += err_msg
        _write_log(logpath, log_content); return False, str(logpath)
    except Exception as e:
        err_msg = f"--- ERROR ---\nUnexpected error during syntax check:\n{e}\n"
        print(f"E: Unexpected error checking shell syntax for {filepath_obj.name}: {e}", file=sys.stderr)
        log_content += err_msg
        _write_log(logpath, log_content); return False, str(logpath)
# @@FILENAME@@ script_runner.py