import re
import subprocess
import sys
import argparse
from pathlib import Path

# --- Regex to find the file blocks ---
# It captures:
# Group 1: The filename
# Group 2: The content between START and END markers
# It requires the re.DOTALL flag so '.' matches newlines.
# It also requires the backreference \1 in the END marker to match the filename.
FILE_BLOCK_REGEX = re.compile(
    r"^(// --- START OF FILE (.+?) ---$).*?^(// --- END OF FILE \2 ---$)",
    re.MULTILINE | re.DOTALL
)

# --- Markers ---
# Ensure these match exactly what's in your file (including spaces/slashes)
START_MARKER_FORMAT = "// --- START OF FILE {} ---"
END_MARKER_FORMAT = "// --- END OF FILE {} ---"

def get_git_committed_content(filepath: Path) -> str | None:
    """
    Retrieves the content of a file from the HEAD commit using git show.

    Args:
        filepath: Path object representing the file.

    Returns:
        The file content as a string if successful, None otherwise.
    """
    if not filepath.is_file():
        print(f"Warning: Local file not found: {filepath}", file=sys.stderr)
        # Decide if you want to proceed without a local file check
        # return None # Or continue to try git show

    # Use relative path for git show command
    relative_filepath = filepath.as_posix() # Use forward slashes for git

    command = ['git', 'show', f'HEAD:{relative_filepath}']
    print(f"Running git command: {' '.join(command)}", file=sys.stderr)

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=False  # Don't raise exception on non-zero exit
        )

        if result.returncode != 0:
            print(f"Error: git show failed for '{relative_filepath}' (return code {result.returncode}):", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            return None
        
        print(f"Successfully fetched content for '{relative_filepath}' from HEAD.", file=sys.stderr)
        return result.stdout

    except FileNotFoundError:
        print("Error: 'git' command not found. Is Git installed and in your PATH?", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error running git show for '{relative_filepath}': {e}", file=sys.stderr)
        return None

def replacement_callback(match: re.Match) -> str:
    """
    Callback function for re.sub. Attempts to replace the matched block
    with the Git-committed version of the file.
    """
    original_block = match.group(0)
    start_marker_line = match.group(1) # Full start marker line
    filename = match.group(2).strip()    # Captured filename, stripped
    end_marker_line = match.group(3)   # Full end marker line

    print(f"Found block for file: '{filename}'", file=sys.stderr)

    filepath = Path(filename).resolve() # Resolve to absolute path based on CWD

    git_content = get_git_committed_content(filepath)

    if git_content is not None:
        # Ensure git content doesn't have trailing newline issues if not desired
        # git_content = git_content.rstrip('\n')

        # Reconstruct the block with new content
        new_block = f"{start_marker_line}\n{git_content}\n{end_marker_line}"
        print(f"Replacing block for '{filename}'.", file=sys.stderr)
        return new_block
    else:
        # If fetching from Git failed, return the original block unchanged
        print(f"Warning: Could not get Git content for '{filename}'. Keeping original block.", file=sys.stderr)
        return original_block

def process_file(input_path: Path, output_path: Path):
    """Reads input file, processes content, and writes to output file."""
    print(f"Processing input file: {input_path}", file=sys.stderr)
    try:
        original_text = input_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading input file {input_path}: {e}", file=sys.stderr)
        sys.exit(1)

    # Perform the replacements using the callback
    modified_text = FILE_BLOCK_REGEX.sub(replacement_callback, original_text)

    try:
        output_path.write_text(modified_text, encoding='utf-8')
        print(f"Successfully wrote modified content to: {output_path}", file=sys.stderr)
    except Exception as e:
        print(f"Error writing output file {output_path}: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Replaces marked file blocks in an input file with their last Git-committed versions."
    )
    parser.add_argument(
        "input_file",
        help="Path to the input file containing the marked blocks."
    )
    parser.add_argument(
        "-o", "--output-file",
        help="Path to the output file. If omitted, overwrites the input file."
    )

    args = parser.parse_args()

    input_path = Path(args.input_file).resolve() # Get absolute path
    
    if args.output_file:
        output_path = Path(args.output_file).resolve()
        # Prevent accidental overwrite if input/output are same via different relative paths
        if input_path == output_path:
             print(f"Warning: Input and output paths resolve to the same file ({input_path}). Overwriting.", file=sys.stderr)
    else:
        output_path = input_path # Overwrite input if no output specified
        print(f"Warning: No output file specified. Input file '{input_path}' will be overwritten.", file=sys.stderr)
        try:
            # Basic safety prompt for overwriting
            confirm = input("Are you sure you want to continue? (y/N): ")
            if confirm.lower() != 'y':
                print("Operation cancelled.", file=sys.stderr)
                sys.exit(0)
        except EOFError: # Handle non-interactive environments
             print("Warning: Cannot confirm overwrite in non-interactive mode. Proceeding with overwrite.", file=sys.stderr)


    process_file(input_path, output_path)

if __name__ == "__main__":
    main()