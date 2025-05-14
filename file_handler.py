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

def _check_last_commit_for_amend(git_path_relative: str, server_dir: Path) -> bool:
    """Checks if the last commit modified ONLY the specified file."""
    try:
        cmd = ['git', 'log', '-1', '--name-only', '--pretty=format:']
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', cwd=server_dir, check=False, timeout=5)
        if result.returncode != 0:
            print(f"Info: Could not get last commit info (maybe first commit?), not amending. (RC={result.returncode})", file=sys.stderr)
            if result.stderr: print(f"   Git stderr: {result.stderr.strip()}", file=sys.stderr)
            return False

        changed_files = [line for line in result.stdout.strip().splitlines() if line] # Get non-empty lines
        if len(changed_files) == 1 and changed_files[0] == git_path_relative:
            print(f"Info: Last commit only changed '{git_path_relative}'. Will attempt amend.", file=sys.stderr)
            return True
        else:
            print(f"Info: Last commit changed {len(changed_files)} files ({changed_files[:3]}...). Not amending.", file=sys.stderr)
            return False
    except (subprocess.TimeoutExpired, Exception) as e:
        print(f"E: Error checking last commit for amend: {e}", file=sys.stderr)
        return False


def update_and_commit_file(filepath_absolute: Path, code_content: str, marker_filename: str, server_dir: Path, is_repo: bool) -> bool:
    """Writes content to an existing tracked file, stages, and commits (potentially amending)."""
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
        needs_save = True # Assume we need to save unless content is identical
        if filepath_absolute.exists():
             try:
                 # Read existing file, also ensuring it ends with a newline for fair comparison
                 current_content = filepath_absolute.read_text(encoding='utf-8')
                 if not current_content.endswith('\n'):
                     current_content += '\n'
                 if code_content == current_content:
                      print(f"Info: Content for '{git_path_relative}' identical. Skipping save and Git commit.", file=sys.stderr)
                      needs_save = False # No need to save or commit
                      return True # Nothing to do, operation is effectively successful
             except Exception as read_e:
                 print(f"W: Could not read existing file {git_path_relative} to check changes: {read_e}. Proceeding with save/commit.", file=sys.stderr)
                 # Proceed assuming changes if read fails

        # --- Save the file (only if needed) ---
        if needs_save:
            print(f"Info: Overwriting tracked local file: {git_path_relative}", file=sys.stderr)
            if not save_code_to_file(code_content, filepath_absolute):
                return False # Basic save failed before attempting Git

        # --- Git Add ---
        print(f"Running: git add '{git_path_relative}' from {server_dir}", file=sys.stderr)
        add_result = subprocess.run(['git', 'add', git_path_relative], capture_output=True, text=True, check=False, encoding='utf-8', cwd=server_dir, timeout=10)
        if add_result.returncode != 0:
            print(f"E: 'git add {git_path_relative}' failed (RC={add_result.returncode}):\n{add_result.stderr.strip()}", file=sys.stderr)
            # Consider attempting to reset the file if add fails?
            return False

        # --- Determine if amending ---
        should_amend = _check_last_commit_for_amend(git_path_relative, server_dir)

        # --- Git Commit (potentially amend) ---
        commit_command = ['git', 'commit']
        commit_action_log = "" # For logging

        if should_amend:
            # Use --amend and --no-edit to reuse the previous commit message
            commit_command.extend(['--amend', '--no-edit'])
            commit_action_log = f"Amending previous commit for '{git_path_relative}'..."
        else:
            # Create a new commit with a standard message
            commit_message = f"Update {marker_filename} from AI Code Capture"
            commit_command.extend(['-m', commit_message])
            commit_action_log = f"Creating new commit for '{git_path_relative}' with msg \"{commit_message}\"..."

        # Always add the file path using '--' to ensure it's treated as a path
        commit_command.extend(['--', git_path_relative])

        print(f"Running: {' '.join(commit_command)}", file=sys.stderr)
        print(f"Action: {commit_action_log}", file=sys.stderr)

        commit_result = subprocess.run(commit_command, capture_output=True, text=True, check=False, encoding='utf-8', cwd=server_dir, timeout=15)

        if commit_result.returncode == 0:
            action_verb = "Amended" if should_amend else "Committed"
            print(f"Success: {action_verb} changes for '{git_path_relative}'.\n{commit_result.stdout.strip()}", file=sys.stderr)
            return True
        else:
             # Check common non-error messages from commit output
             no_changes_patterns = ["nothing to commit", "no changes added to commit", "nothing added to commit but untracked files present"]
             # Special check for amend when nothing changed since previous commit
             if should_amend and "no changes" in (commit_result.stdout + commit_result.stderr).lower() and "amend" in (commit_result.stdout + commit_result.stderr).lower():
                  print(f"Info: 'git commit --amend' reported no new changes staged for '{git_path_relative}' since last commit.", file=sys.stderr)
                  return True # Treat as success if amend resulted in no effective change

             combined_output = (commit_result.stdout + commit_result.stderr).lower()
             if any(p in combined_output for p in no_changes_patterns):
                 print(f"Info: 'git commit' reported no effective changes staged for '{git_path_relative}'.", file=sys.stderr)
                 return True # Treat as success if git says nothing changed

             # Actual error
             print(f"E: 'git commit {'--amend' if should_amend else ''}' failed for '{git_path_relative}' (RC={commit_result.returncode}):\n{commit_result.stderr.strip()}\n{commit_result.stdout.strip()}", file=sys.stderr)
             return False
    except Exception as e:
        print(f"E: Unexpected error during Git update/commit for {filepath_absolute}: {e}", file=sys.stderr)
        return False
# @@FILENAME@@ file_handler.py