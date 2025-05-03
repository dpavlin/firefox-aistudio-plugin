# @@FILENAME@@ file_handler.py
import subprocess
import sys
from pathlib import Path
import os # For os.path.splitext

# Note: Requires config dict containing SERVER_DIR and IS_REPO passed to functions or class init

def save_code_to_file(code_content: str, target_path: Path) -> bool:
    """Saves code content to the specified absolute path."""
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(code_content, encoding='utf-8')
        print(f"Success: Code saved to file '{target_path}'", file=sys.stderr)
        return True
    except Exception as e:
        print(f"E: Failed to save file '{target_path}': {str(e)}", file=sys.stderr)
        return False

def find_tracked_file_by_name(basename_to_find: str, server_dir: Path, is_repo: bool) -> str | None:
    """Finds a unique tracked file by its basename within the repo."""
    if not is_repo: return None
    try:
        # Ensure basename doesn't contain path separators for this specific search
        safe_basename = Path(basename_to_find).name
        if not safe_basename: return None

        command = ['git', 'ls-files', f'**/{safe_basename}']
        print(f"Running: {' '.join(command)} in {server_dir}", file=sys.stderr)
        result = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8', cwd=server_dir, timeout=5)

        if result.returncode != 0:
             # Return code 1 often means no files matched, which isn't an error here.
             if result.stderr and result.returncode != 1:
                 print(f"E: 'git ls-files' failed (RC={result.returncode}):\n{result.stderr.strip()}", file=sys.stderr)
             return None # No matches found or error occurred

        tracked_files = result.stdout.strip().splitlines()
        # Filter again specifically by basename just in case the glob pattern was too broad
        matches = [f for f in tracked_files if Path(f).name == safe_basename]

        if len(matches) == 1:
            print(f"Info: Found unique tracked file match: '{matches[0]}'", file=sys.stderr)
            return matches[0] # Return the relative path found
        elif len(matches) > 1:
            print(f"W: Ambiguous filename marker '{safe_basename}'. Found multiple tracked files: {matches}.", file=sys.stderr)
            return None # Ambiguous
        else:
             # print(f"Info: No tracked file found with basename '{safe_basename}'.", file=sys.stderr)
             return None # No matches found
    except (subprocess.TimeoutExpired, Exception) as e:
        print(f"E: Error searching Git for file '{basename_to_find}': {e}", file=sys.stderr)
        return None

def is_git_tracked(filepath_relative_to_repo: str, server_dir: Path, is_repo: bool) -> bool:
    """Checks if a specific relative path is tracked by Git."""
    if not is_repo: return False
    try:
        # Ensure we use forward slashes for git commands, even on Windows
        git_path = Path(filepath_relative_to_repo).as_posix()
        command = ['git', 'ls-files', '--error-unmatch', git_path]
        # Don't print this every time, too verbose
        # print(f"Running: {' '.join(command)} in {server_dir}", file=sys.stderr)
        # Use check=True to raise CalledProcessError if file isn't tracked
        subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', cwd=server_dir, timeout=5)
        return True # If no error, it's tracked
    except subprocess.CalledProcessError:
        # Expected error if file is not tracked
        return False
    except (subprocess.TimeoutExpired, Exception) as e:
        print(f"E: Error checking Git tracking status for '{filepath_relative_to_repo}': {e}", file=sys.stderr)
        return False # Error occurred

def update_and_commit_file(filepath_absolute: Path, code_content: str, marker_filename: str, server_dir: Path, is_repo: bool) -> bool:
    """Writes content to an existing tracked file, stages, and commits if tracked and changed."""
    if not is_repo:
        print("W: Attempted Git commit, but not in a repo.", file=sys.stderr)
        return False # Should not be called if not repo, but double-check

    if not filepath_absolute.is_file():
         print(f"W: Target file for Git commit does not exist: '{filepath_absolute}'. Saving it first.", file=sys.stderr)
         # Fall through to save, git add should handle new files if needed (though logic assumes existing tracked)

    try:
        # Ensure path relative to server_dir uses forward slashes for git commands
        git_path_posix = filepath_absolute.relative_to(server_dir).as_posix()

        # Check for changes first to avoid unnecessary commits
        current_content = ""
        needs_save = True
        if filepath_absolute.exists():
             try:
                 # Read existing file, be careful about line endings if comparing
                 # Let's assume write_text handles line endings consistently for the OS
                 current_content = filepath_absolute.read_text(encoding='utf-8')
                 if code_content == current_content:
                      print(f"Info: Content for '{git_path_posix}' identical. Skipping Git commit.", file=sys.stderr)
                      needs_save = False # No need to save or commit
                      return True # Operation successful (no change needed)
                 else:
                      print(f"Info: Content for '{git_path_posix}' differs. Proceeding with overwrite and commit.", file=sys.stderr)
             except Exception as read_e:
                 print(f"W: Could not read existing file {git_path_posix} to check changes: {read_e}. Will overwrite.", file=sys.stderr)
                 # Proceed assuming changes are needed

        if needs_save:
            print(f"Info: Overwriting tracked local file: {git_path_posix}", file=sys.stderr)
            if not save_code_to_file(code_content, filepath_absolute):
                 return False # Reuse basic save function

        # --- Git Add ---
        # Use the relative POSIX path for git commands
        print(f"Running: git add '{git_path_posix}' from {server_dir}", file=sys.stderr)
        add_result = subprocess.run(['git', 'add', git_path_posix], capture_output=True, text=True, check=False, encoding='utf-8', cwd=server_dir, timeout=10)
        if add_result.returncode != 0:
            # Don't treat return code 1 as error if stderr is empty (might be 'warning: LF will be replaced by CRLF')
            if add_result.returncode == 1 and not add_result.stderr.strip():
                print(f"Info: 'git add {git_path_posix}' completed with RC=1 (stdout: {add_result.stdout.strip()})", file=sys.stderr)
                # Continue to commit attempt
            else:
                print(f"E: 'git add {git_path_posix}' failed (RC={add_result.returncode}):\nstderr: {add_result.stderr.strip()}\nstdout: {add_result.stdout.strip()}", file=sys.stderr)
                return False

        # --- Git Commit ---
        commit_message = f"Update {marker_filename} from AI Code Capture"
        # Commit only the specific file using '--' to separate options from paths
        command = ['git', 'commit', '-m', commit_message, '--', git_path_posix]
        print(f"Running: {' '.join(command)} ...", file=sys.stderr)
        commit_result = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8', cwd=server_dir, timeout=15)

        if commit_result.returncode == 0:
            # Success
            print(f"Success: Committed changes for '{git_path_posix}'.\n{commit_result.stdout.strip()}", file=sys.stderr)
            return True
        else:
             # Check specific non-error conditions (like nothing to commit)
             no_changes_patterns = ["nothing to commit", "no changes added to commit", "nothing added to commit but untracked files present"]
             # Combine stdout and stderr for checking messages
             combined_output = (commit_result.stdout + commit_result.stderr).lower()
             if any(p in combined_output for p in no_changes_patterns):
                 print(f"Info: 'git commit' reported no effective changes staged for '{git_path_posix}'.", file=sys.stderr)
                 return True # Considered success as state matches intent
             else:
                 # Genuine commit error
                 print(f"E: 'git commit' failed for '{git_path_posix}' (RC={commit_result.returncode}):\nstderr: {commit_result.stderr.strip()}\nstdout: {commit_result.stdout.strip()}", file=sys.stderr)
                 return False
    except Exception as e:
        print(f"E: Unexpected error during Git update/commit for {filepath_absolute}: {e}", file=sys.stderr)
        return False

