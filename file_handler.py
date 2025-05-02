# @@FILENAME@@ file_handler.py
import subprocess
import sys
from pathlib import Path
import os # For os.path.splitext
import shutil # For shutil.which

# Note: Requires config dict containing SERVER_DIR and IS_REPO passed to functions or class init

def save_code_to_file(code_content: str, target_path: Path) -> bool:
    """Saves code content to the specified absolute path."""
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(code_content, encoding='utf-8')
        print(f"Success: Code saved to file '{target_path.relative_to(Path.cwd())}'", file=sys.stderr) # Log relative path
        return True
    except Exception as e:
        print(f"E: Failed to save file '{target_path}': {str(e)}", file=sys.stderr)
        return False

def find_tracked_file_by_name(basename_to_find: str, server_dir: Path, is_repo: bool) -> str | None:
    """Finds a unique tracked file by its basename within the repo."""
    if not is_repo: return None
    if not shutil.which("git"): return None # Cannot search if git isn't installed

    try:
        # Use glob pattern within git ls-files for potentially faster search
        command = ['git', 'ls-files', '--', f'**/{basename_to_find}']
        result = subprocess.run(
            command, capture_output=True, text=True, check=False,
            encoding='utf-8', cwd=server_dir, timeout=5
        )

        if result.returncode != 0:
             # Return code 1 usually means no files matched, which isn't an error here.
             # Log actual errors.
             if result.stderr and result.returncode != 1:
                 print(f"W: 'git ls-files' failed (RC={result.returncode}): {result.stderr.strip()}", file=sys.stderr)
             return None # No matches or error

        tracked_files = result.stdout.strip().splitlines()

        # Filter again strictly by basename just in case glob was too broad
        # (though it should be accurate with **)
        matches = [f for f in tracked_files if Path(f).name == basename_to_find]

        if len(matches) == 1:
            print(f"Info: Found unique tracked file match: '{matches[0]}'", file=sys.stderr)
            return matches[0] # Return the relative path found
        elif len(matches) > 1:
            print(f"W: Ambiguous filename marker '{basename_to_find}'. Found multiple tracked files: {matches}. Cannot auto-select.", file=sys.stderr)
            return None
        else:
             # print(f"Info: No tracked file found with basename '{basename_to_find}'.", file=sys.stderr)
            return None # No file with that exact basename found

    except (subprocess.TimeoutExpired, Exception) as e:
        print(f"E: Error searching Git for file '{basename_to_find}': {e}", file=sys.stderr)
        return None

def is_git_tracked(filepath_relative_to_repo: str, server_dir: Path, is_repo: bool) -> bool:
    """Checks if a specific relative path is tracked by Git."""
    if not is_repo: return False
    if not shutil.which("git"): return False

    try:
        # Ensure path uses forward slashes for git commands
        git_path = Path(filepath_relative_to_repo).as_posix()
        command = ['git', 'ls-files', '--error-unmatch', '--', git_path] # Add '--' for safety
        # Use check=True to raise CalledProcessError if file isn't tracked (non-zero exit code)
        subprocess.run(
            command, capture_output=True, text=True, check=True,
            encoding='utf-8', cwd=server_dir, timeout=5
        )
        return True # No error means it's tracked
    except subprocess.CalledProcessError:
        return False # Expected error if not tracked
    except (subprocess.TimeoutExpired, Exception) as e:
        print(f"W: Error running 'git ls-files --error-unmatch' for '{filepath_relative_to_repo}': {e}", file=sys.stderr)
        return False # Treat other errors as 'not tracked' for safety

def update_and_commit_file(filepath_absolute: Path, code_content: str, marker_filename: str, server_dir: Path, is_repo: bool) -> bool:
    """Writes content to an existing tracked file, stages, and commits if tracked and changed."""
    if not is_repo:
        print("W: Attempted Git commit, but not in a repo.", file=sys.stderr)
        return False
    if not shutil.which("git"):
         print("E: 'git' command not found. Cannot commit.", file=sys.stderr)
         return False

    try:
        # Get path relative to repo root for git commands
        git_path_posix = filepath_absolute.relative_to(server_dir).as_posix()

        # 1. Check for actual content changes before writing/adding/committing
        current_content = ""
        needs_write = True
        if filepath_absolute.exists():
             try:
                 # Read existing content, attempting to normalize line endings for comparison
                 with open(filepath_absolute, 'r', encoding='utf-8', newline='') as f:
                     current_content = f.read()
                 # Simple normalization (replace \r\n with \n) - might need refinement
                 normalized_current = current_content.replace('\r\n', '\n')
                 normalized_new = code_content.replace('\r\n', '\n')

                 if normalized_new == normalized_current:
                      print(f"Info: Content for '{git_path_posix}' is identical (ignoring line endings). Skipping save and Git.", file=sys.stderr)
                      return True # Treat as success if no change needed
                 else:
                      print(f"Info: Content for '{git_path_posix}' differs. Proceeding with save and commit.", file=sys.stderr)
             except Exception as read_e:
                 print(f"W: Could not read existing file '{git_path_posix}' to check for changes: {read_e}. Proceeding with overwrite.", file=sys.stderr)
                 needs_write = True # Force write if read fails
        else:
             needs_write = True # File doesn't exist, needs writing

        # 2. Write the file (only if needed)
        if needs_write:
            print(f"Info: Overwriting local file: {git_path_posix}", file=sys.stderr)
            if not save_code_to_file(code_content, filepath_absolute):
                return False # Basic save failed

        # 3. Stage the file
        print(f"Running: git add -- '{git_path_posix}' from {server_dir}", file=sys.stderr)
        add_result = subprocess.run(
            ['git', 'add', '--', git_path_posix], # Use '--' for safety
            capture_output=True, text=True, check=False, encoding='utf-8',
            cwd=server_dir, timeout=10
        )
        if add_result.returncode != 0:
            print(f"E: 'git add {git_path_posix}' failed (RC={add_result.returncode}):\n{add_result.stderr.strip()}", file=sys.stderr)
            return False

        # 4. Commit the file
        # Use marker_filename (which could be different from git_path_posix if found via basename) for message
        commit_message = f"Update {marker_filename} from AI Code Capture"
        print(f"Running: git commit -m \"{commit_message}\" -- '{git_path_posix}' ...", file=sys.stderr)
        commit_result = subprocess.run(
            ['git', 'commit', '-m', commit_message, '--', git_path_posix], # Use '--' for safety
            capture_output=True, text=True, check=False, encoding='utf-8',
            cwd=server_dir, timeout=15
        )

        if commit_result.returncode == 0:
            # Check stdout for confirmation, stderr might contain warnings
            print(f"Success: Committed changes for '{git_path_posix}'.", file=sys.stderr)
            if commit_result.stdout: print(f"Commit Output:\n{commit_result.stdout.strip()}", file=sys.stderr)
            if commit_result.stderr: print(f"Commit Warnings:\n{commit_result.stderr.strip()}", file=sys.stderr)
            return True
        else:
             # Check if the error is simply "nothing to commit"
             no_changes_patterns = [
                 "nothing to commit",
                 "no changes added to commit",
                 "nothing added to commit" # Simplified pattern
             ]
             combined_output = (commit_result.stdout + commit_result.stderr).lower()
             if any(p in combined_output for p in no_changes_patterns):
                 print(f"Info: 'git commit' reported no effective changes staged for '{git_path_posix}' (likely identical after normalization).", file=sys.stderr)
                 return True # Considered success as the state is correct
             else:
                 # Report actual commit failure
                 print(f"E: 'git commit' failed for '{git_path_posix}' (RC={commit_result.returncode}):\n{commit_result.stderr.strip()}\n{commit_result.stdout.strip()}", file=sys.stderr)
                 return False
    except Exception as e:
        print(f"E: Unexpected error during Git update/commit for {filepath_absolute}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr) # Add traceback for unexpected errors
        return False
