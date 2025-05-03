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
        # Ensure code content ends with a newline for cleaner diffs/file handling
        if not code_content.endswith('\n'):
             code_content += '\n'
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
        command = ['git', 'ls-files', f'**/{basename_to_find}']
        result = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8', cwd=server_dir, timeout=5)
        if result.returncode != 0:
             # Don't log error if return code is 1 (no matches found)
             if result.stderr and result.returncode != 1:
                 print(f"E: 'git ls-files' failed (RC={result.returncode}):\n{result.stderr.strip()}", file=sys.stderr)
             return None
        tracked_files = result.stdout.strip().splitlines()
        # Filter more strictly for exact basename match
        matches = [f for f in tracked_files if Path(f).name == basename_to_find]
        if len(matches) == 1:
            print(f"Info: Found unique tracked file match: '{matches[0]}'", file=sys.stderr)
            return matches[0]
        elif len(matches) > 1:
            print(f"W: Ambiguous filename marker '{basename_to_find}'. Found multiple tracked files: {matches}. Use a more specific path.", file=sys.stderr)
            return None
        else: # len == 0
            return None
    except (subprocess.TimeoutExpired, Exception) as e:
        print(f"E: Error searching Git for file '{basename_to_find}': {e}", file=sys.stderr)
        return None

def is_git_tracked(filepath_relative_to_repo: str, server_dir: Path, is_repo: bool) -> bool:
    """Checks if a specific relative path is tracked by Git."""
    if not is_repo: return False
    try:
        # Ensure path uses forward slashes for Git command
        git_path = Path(filepath_relative_to_repo).as_posix()
        command = ['git', 'ls-files', '--error-unmatch', git_path]
        # Use subprocess.run and check returncode for more control
        result = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8', cwd=server_dir, timeout=5)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, Exception) as e:
         print(f"E: Error checking Git tracking status for '{filepath_relative_to_repo}': {e}", file=sys.stderr)
         return False # Error occurred

def update_and_commit_file(filepath_absolute: Path, code_content: str, marker_filename: str, server_dir: Path, is_repo: bool) -> bool:
    """Writes content to an existing tracked file, stages, and commits if tracked and changed."""
    if not is_repo:
        print("W: Attempted Git commit, but not in a repo.", file=sys.stderr)
        return False
    try:
        # Convert absolute path to relative path for Git commands and messages
        try:
            git_path_relative = filepath_absolute.relative_to(server_dir).as_posix()
        except ValueError:
            print(f"E: Cannot commit file outside the Git repository root: {filepath_absolute} (Repo: {server_dir})", file=sys.stderr)
            return False

        # Ensure code content ends with a newline for consistency
        if not code_content.endswith('\n'):
             code_content += '\n'

        # Check for changes first to avoid empty commits
        current_content = ""
        if filepath_absolute.exists():
             try:
                 # Read existing file, also ensuring it ends with a newline for fair comparison
                 current_content = filepath_absolute.read_text(encoding='utf-8')
                 if not current_content.endswith('\n'):
                     current_content += '\n'
             except Exception as read_e:
                 print(f"W: Could not read existing file {git_path_relative} to check changes: {read_e}", file=sys.stderr)
                 # Proceed assuming changes if read fails? Or return False? For now, proceed.

        if code_content == current_content:
             print(f"Info: Content for '{git_path_relative}' identical. Skipping Git commit.", file=sys.stderr)
             # We still need to save, as save_code_to_file might not have been called yet
             if not save_code_to_file(code_content, filepath_absolute):
                 return False # Basic save failed
             return True # No commit needed, but save was successful or unnecessary

        # Write and commit
        print(f"Info: Overwriting tracked local file: {git_path_relative}", file=sys.stderr)
        if not save_code_to_file(code_content, filepath_absolute):
            return False # Basic save failed before attempting Git

        print(f"Running: git add '{git_path_relative}' from {server_dir}", file=sys.stderr)
        add_result = subprocess.run(['git', 'add', git_path_relative], capture_output=True, text=True, check=False, encoding='utf-8', cwd=server_dir, timeout=10)
        if add_result.returncode != 0:
            print(f"E: 'git add {git_path_relative}' failed (RC={add_result.returncode}):\n{add_result.stderr.strip()}", file=sys.stderr)
            # Consider attempting to reset the file if add fails?
            return False

        # Use the marker filename (which might be more user-friendly than the full relative path)
        commit_message = f"Update {marker_filename} from AI Code Capture"
        print(f"Running: git commit -m \"{commit_message}\" -- '{git_path_relative}' ...", file=sys.stderr)
        # Pass '--' to ensure filename isn't misinterpreted as an option
        commit_result = subprocess.run(['git', 'commit', '-m', commit_message, '--', git_path_relative], capture_output=True, text=True, check=False, encoding='utf-8', cwd=server_dir, timeout=15)

        if commit_result.returncode == 0:
            print(f"Success: Committed changes for '{git_path_relative}'.\n{commit_result.stdout.strip()}", file=sys.stderr)
            return True
        else:
             # Check common non-error messages from commit output
             no_changes_patterns = ["nothing to commit", "no changes added to commit", "nothing added to commit but untracked files present"]
             combined_output = (commit_result.stdout + commit_result.stderr).lower()
             if any(p in combined_output for p in no_changes_patterns):
                 print(f"Info: 'git commit' reported no effective changes staged for '{git_path_relative}'.", file=sys.stderr)
                 return True # Treat as success if git says nothing changed
             else:
                 print(f"E: 'git commit' failed for '{git_path_relative}' (RC={commit_result.returncode}):\n{commit_result.stderr.strip()}\n{commit_result.stdout.strip()}", file=sys.stderr)
                 return False
    except Exception as e:
        print(f"E: Unexpected error during Git update/commit for {filepath_absolute}: {e}", file=sys.stderr)
        return False
