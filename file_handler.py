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
        # Use glob pattern directly in ls-files
        # Using ** might be slow in very large repos, but necessary for arbitrary depth
        command = ['git', 'ls-files', f'**/{basename_to_find}']
        result = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8', cwd=server_dir, timeout=5)

        if result.returncode != 0:
             # Return code 1 means no files matched, which is not an error here
             if result.stderr and result.returncode != 1:
                 print(f"E: 'git ls-files' failed (RC={result.returncode}):\n{result.stderr.strip()}", file=sys.stderr)
             return None # No match or error

        tracked_files = result.stdout.strip().splitlines()

        # Filter again just in case ls-files pattern was too broad (e.g., case sensitivity issues)
        matches = [f for f in tracked_files if Path(f).name == basename_to_find]

        if len(matches) == 1:
            print(f"Info: Found unique tracked file match: '{matches[0]}'", file=sys.stderr)
            return matches[0] # Return the relative path
        elif len(matches) > 1:
            print(f"W: Ambiguous filename marker '{basename_to_find}'. Found multiple tracked files: {matches}.", file=sys.stderr)
            return None # Ambiguous
        else:
            # print(f"Info: No tracked file found matching basename '{basename_to_find}'.", file=sys.stderr)
            return None # No match
    except (subprocess.TimeoutExpired, Exception) as e:
        print(f"E: Error searching Git for file '{basename_to_find}': {e}", file=sys.stderr)
        return None

def is_git_tracked(filepath_relative_to_repo: str, server_dir: Path, is_repo: bool) -> bool:
    """Checks if a specific relative path is tracked by Git."""
    if not is_repo: return False
    try:
        # Ensure consistent path separators for git
        git_path = Path(filepath_relative_to_repo).as_posix()
        command = ['git', 'ls-files', '--error-unmatch', git_path]
        # check=True will raise CalledProcessError if the file is not tracked (or other errors)
        subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', cwd=server_dir, timeout=5)
        return True
    except subprocess.CalledProcessError:
        return False # Not tracked (this is the expected case for non-tracked files)
    except (subprocess.TimeoutExpired, Exception) as e:
        print(f"E: Error checking Git tracking status for '{filepath_relative_to_repo}': {e}", file=sys.stderr)
        return False # Error occurred

def update_and_commit_file(filepath_absolute: Path, code_content: str, marker_filename: str, server_dir: Path, is_repo: bool) -> bool:
    """Writes content to an existing tracked file, stages, and commits if tracked and changed."""
    if not is_repo:
        print("W: Attempted Git commit, but not in a repo.", file=sys.stderr)
        return False # Should not happen if called correctly, but safe check
    try:
        # Get the path relative to the repo root for Git commands
        git_path_posix = filepath_absolute.relative_to(server_dir).as_posix()

        # --- Check for changes first ---
        # Read existing content, handling potential file-not-found or encoding errors
        current_content = ""
        if filepath_absolute.exists():
             try:
                 # Detect common encodings or default to utf-8 with error handling
                 current_content = filepath_absolute.read_text(encoding='utf-8', errors='replace')
             except Exception as read_e:
                 print(f"W: Could not read existing file {git_path_posix} to check changes: {read_e}", file=sys.stderr)
                 # Proceed assuming changes if we can't read it reliably

        # Compare content (normalize line endings maybe? For now, direct comparison)
        # Python's write_text uses '\n', Git might normalize based on core.autocrlf
        # A more robust check might involve normalizing line endings before comparison
        if code_content == current_content:
             print(f"Info: Content for '{git_path_posix}' identical. Skipping Git.", file=sys.stderr)
             return True # Report success as no action was needed

        # --- Write and commit ---
        print(f"Info: Overwriting tracked local file: {git_path_posix}", file=sys.stderr)
        # Reuse basic save, which already handles potential exceptions
        if not save_code_to_file(code_content, filepath_absolute):
            return False # Basic save failed

        print(f"Running: git add '{git_path_posix}' from {server_dir}", file=sys.stderr)
        # Use the specific path for 'git add'
        add_result = subprocess.run(['git', 'add', git_path_posix], capture_output=True, text=True, check=False, encoding='utf-8', cwd=server_dir, timeout=10)
        if add_result.returncode != 0:
            print(f"E: 'git add {git_path_posix}' failed (RC={add_result.returncode}):\n{add_result.stderr.strip()}", file=sys.stderr)
            # Consider attempting to reset the file if add fails? Or just report error.
            return False

        commit_message = f"Update {marker_filename} from AI Code Capture"
        print(f"Running: git commit -m \"{commit_message}\" -- '{git_path_posix}' ...", file=sys.stderr)
        # Commit only the added file
        commit_result = subprocess.run(['git', 'commit', '-m', commit_message, '--', git_path_posix], capture_output=True, text=True, check=False, encoding='utf-8', cwd=server_dir, timeout=15)

        if commit_result.returncode == 0:
            print(f"Success: Committed changes for '{git_path_posix}'.\n{commit_result.stdout.strip()}", file=sys.stderr)
            return True
        else:
             # Check common "no changes" messages from git commit output
             no_changes_patterns = ["nothing to commit", "no changes added to commit", "nothing added to commit but untracked files present"]
             # Combine stdout and stderr for checking, convert to lower for case-insensitivity
             combined_output = (commit_result.stdout + commit_result.stderr).lower()
             if any(p in combined_output for p in no_changes_patterns):
                 print(f"Info: 'git commit' reported no effective changes staged for '{git_path_posix}'.", file=sys.stderr)
                 # This can happen if 'git add' staged something but it was identical
                 # to HEAD after line ending normalization etc. Treat as success.
                 return True
             else:
                 # Genuine commit error
                 print(f"E: 'git commit' failed for '{git_path_posix}' (RC={commit_result.returncode}):\n{commit_result.stderr.strip()}\n{commit_result.stdout.strip()}", file=sys.stderr)
                 return False
    except ValueError as e:
        # Handles case where filepath_absolute is not relative to server_dir
        print(f"E: Error calculating relative path for Git operations: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"E: Unexpected error during Git update/commit for {filepath_absolute}: {e}", file=sys.stderr)
        return False
