import subprocess
import sys
from pathlib import Path
# import os # No longer needed
import shutil # For shutil.which

# Note: No longer requires log_folder_path

# Removed _write_log helper function

def run_script(filepath: str, script_type: str) -> tuple[bool, str | None, str | None]:
    """
    Runs a Python or Shell script, returns (success, stdout, stderr).
    Outputs are returned as strings.
    """
    filepath_obj = Path(filepath).resolve()
    if not filepath_obj.is_file():
        error_msg = f"E: Script file not found for execution: {filepath_obj}"
        print(error_msg, file=sys.stderr)
        return False, None, error_msg # Return error in stderr slot

    # filename_base = filepath_obj.stem # Not needed for logging anymore
    run_cwd = filepath_obj.parent

    command = []
    interpreter_name = ""
    # log_content = "" # No longer building log content string

    stdout_str = None
    stderr_str = None

    if script_type == 'python':
        python_exe = sys.executable or shutil.which("python3") or shutil.which("python") or "python"
        if not shutil.which(python_exe):
             err_msg = f"Error: Python interpreter '{python_exe}' not found."
             print(f"E: {err_msg.strip()}", file=sys.stderr)
             return False, None, err_msg
        command = [python_exe, str(filepath_obj)]
        interpreter_name = Path(python_exe).name
        print(f"Executing Python ({interpreter_name}): {' '.join(command)} in '{run_cwd}'", file=sys.stderr)
    elif script_type == 'shell':
        shell_exe = shutil.which("bash") or shutil.which("sh")
        if not shell_exe:
             err_msg = "Error: No 'bash' or 'sh' interpreter found."
             print(f"E: {err_msg.strip()}", file=sys.stderr)
             return False, None, err_msg
        command = [shell_exe, str(filepath_obj)]
        interpreter_name = Path(shell_exe).name
        print(f"Executing Shell ({interpreter_name}): {' '.join(command)} in '{run_cwd}'", file=sys.stderr)
    else:
        err_msg = f"E: Cannot run script of unknown type '{script_type}' for {filepath}"
        print(err_msg, file=sys.stderr)
        return False, None, err_msg

    # log_content += f"--- COMMAND ---\n{' '.join(command)}\n--- CWD ---\n{run_cwd}\n" # Removed
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, encoding='utf-8', check=False, cwd=run_cwd)
        stdout_str = result.stdout
        stderr_str = result.stderr
        # log_content += f"--- STDOUT ---\n{result.stdout}\n--- STDERR ---\n{result.stderr}\n--- Return Code: {result.returncode} ---\n" # Removed
        # _write_log(logpath, log_content) # Removed
        print(f"Exec finished ({script_type}). RC: {result.returncode}. Returning output.", file=sys.stderr)
        return result.returncode == 0, stdout_str, stderr_str
    except subprocess.TimeoutExpired:
        err_msg = f"E: Script timed out after 15 seconds: {filepath_obj.name}"
        print(err_msg, file=sys.stderr)
        # log_content += f"--- ERROR ---\nScript execution timed out after 15 seconds.\n" # Removed
        # _write_log(logpath, log_content) # Removed
        return False, None, "Execution timed out after 15 seconds."
    except FileNotFoundError:
        err_msg = f"--- ERROR ---\nScript file '{filepath_obj}' or CWD '{run_cwd}' not found during execution.\n"
        print(f"E: {err_msg.strip()}", file=sys.stderr)
        # log_content += err_msg # Removed
        # _write_log(logpath, log_content) # Removed
        return False, None, f"Script file or CWD not found during execution: {filepath_obj}"
    except Exception as e:
        err_msg = f"--- ERROR ---\nUnexpected error during script execution:\n{e}\n"
        print(f"E: Unexpected error running script {filepath_obj.name}: {e}", file=sys.stderr)
        # log_content += err_msg # Removed
        # _write_log(logpath, log_content) # Removed
        return False, None, f"Unexpected error during execution: {e}"

def check_shell_syntax(filepath: str) -> tuple[bool, str | None, str | None]:
    """
    Checks shell script syntax using 'bash -n'. Returns (syntax_ok, stdout, stderr).
    Outputs are returned as strings.
    """
    filepath_obj = Path(filepath).resolve()
    if not filepath_obj.is_file():
        error_msg = f"E: Shell script file not found for syntax check: {filepath_obj}"
        print(error_msg, file=sys.stderr)
        return False, None, error_msg

    # filename_base = filepath_obj.stem # Removed
    # logpath = log_folder_path / f"{filename_base}_shell_syntax.log" # Removed

    checker_exe = shutil.which("bash")
    if not checker_exe:
        err_msg = "Error: 'bash' command not found for syntax check."
        print(f"W: {err_msg.strip()}", file=sys.stderr)
        # _write_log(logpath, err_msg + "\n"); # Removed
        return False, None, err_msg

    command = [checker_exe, '-n', str(filepath_obj)]
    # log_content = f"--- COMMAND ---\n{' '.join(command)}\n" # Removed
    print(f"Checking Shell syntax: {' '.join(command)}", file=sys.stderr)
    stdout_str = None
    stderr_str = None
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, encoding='utf-8', check=False)
        syntax_ok = result.returncode == 0
        stdout_str = result.stdout
        stderr_str = result.stderr
        status_msg = "OK" if syntax_ok else f"ERROR (RC: {result.returncode})"
        # log_content += f"--- STATUS: {status_msg} ---\n--- STDOUT ---\n{result.stdout}\n--- STDERR ---\n{result.stderr}\n" # Removed
        # _write_log(logpath, log_content) # Removed
        if syntax_ok: print(f"Shell syntax OK for {filepath_obj.name}", file=sys.stderr)
        else: print(f"Shell syntax Error for {filepath_obj.name}. RC: {result.returncode}.", file=sys.stderr)
        return syntax_ok, stdout_str, stderr_str
    except FileNotFoundError:
        err_msg = f"--- ERROR ---\nSyntax check command '{checker_exe}' not found during execution.\n"
        print(f"E: {err_msg.strip()}", file=sys.stderr)
        # log_content += err_msg # Removed
        # _write_log(logpath, log_content); # Removed
        return False, None, f"Syntax check command '{checker_exe}' not found."
    except subprocess.TimeoutExpired:
        err_msg = "--- ERROR ---\nShell syntax check timed out after 10 seconds.\n"
        print(f"E: Shell syntax check timed out for {filepath_obj.name}", file=sys.stderr)
        # log_content += err_msg # Removed
        # _write_log(logpath, log_content); # Removed
        return False, None, "Shell syntax check timed out after 10 seconds."
    except Exception as e:
        err_msg = f"--- ERROR ---\nUnexpected error during syntax check:\n{e}\n"
        print(f"E: Unexpected error checking shell syntax for {filepath_obj.name}: {e}", file=sys.stderr)
        # log_content += err_msg # Removed
        # _write_log(logpath, log_content); # Removed
        return False, None, f"Unexpected error during syntax check: {e}"
