import os
import sys
import argparse
import fnmatch # For matching patterns like .gitignore

# --- Configuration ---
# Markers to use when generating the dump file
START_MARKER_PREFIX = "--- START OF FILE "
END_MARKER_PREFIX = "--- END OF FILE " # Use the specific format required by the parser
MARKER_SUFFIX = " ---"
CODE_FENCE_MARKER = "```"
DEFAULT_OUTPUT_FILENAME = "all_generated.txt"

# Basic mapping of file extensions to Markdown language identifiers
LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".txt": "text",
    ".sql": "sql",
    ".xml": "xml",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c", # Often C or C++ headers
    ".hpp": "cpp",
    ".cs": "csharp",
    ".go": "go",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".rs": "rust",
    ".toml": "toml",
    ".cfg": "ini", # Often ini format
    ".ini": "ini",
    ".dockerfile": "dockerfile",
    "Dockerfile": "dockerfile", # Exact filename match
    ".gitignore": "text", # Treat as plain text
    ".env": "text", # Treat as plain text
}
# ---------------------

def get_language_identifier(filename):
    """Determine the language identifier based on filename extension."""
    # Handle exact filename matches first
    basename = os.path.basename(filename)
    if basename in LANGUAGE_MAP:
        return LANGUAGE_MAP[basename]

    # Fallback to extension matching
    _, ext = os.path.splitext(filename)
    return LANGUAGE_MAP.get(ext.lower(), "text") # Default to 'text'

def read_gitignore_patterns(gitignore_path):
    """Reads patterns from a .gitignore file."""
    patterns = []
    if os.path.exists(gitignore_path):
        try:
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                for line in f:
                    stripped_line = line.strip()
                    if stripped_line and not stripped_line.startswith('#'):
                        patterns.append(stripped_line)
        except Exception as e:
            print(f"Warning: Could not read .gitignore file '{gitignore_path}': {e}", file=sys.stderr)
    return patterns

def should_ignore(relative_path, gitignore_patterns):
    """Checks if a path should be ignored based on .gitignore patterns."""
    # Ensure forward slashes for matching, consistent with .gitignore
    match_path = relative_path.replace(os.sep, '/')
    for pattern in gitignore_patterns:
        # Basic handling for directory patterns
        is_dir_pattern = pattern.endswith('/')
        match_target = match_path + '/' if is_dir_pattern else match_path
        pattern_to_match = pattern

        # fnmatch needs the pattern adjusted slightly in some cases
        if is_dir_pattern:
            # Match directory and its contents
            pattern_to_match = pattern.rstrip('/') + '/*'
            if fnmatch.fnmatch(match_target, pattern_to_match):
                 return True
             # Also match the directory itself
            if fnmatch.fnmatch(match_target.rstrip('/'), pattern.rstrip('/')):
                 return True

        # Standard file/directory matching
        if fnmatch.fnmatch(match_target, pattern_to_match):
            return True
        # Handle patterns starting with '/' (match from root) - fnmatch handles this implicitly
        # Handle patterns without '/' (match anywhere) - fnmatch handles this implicitly

    # Ignore .git directory explicitly
    if match_path.startswith('.git/') or match_path == '.git':
        return True
        
    return False

def create_dump(input_dir, output_file, verbose=False, use_gitignore=True):
    """
    Walks through the input directory and creates a formatted dump file.

    Args:
        input_dir (str): Path to the source directory.
        output_file (str): Path to the output dump file to be created.
        verbose (bool): If True, print more detailed progress.
        use_gitignore (bool): If True, try to read and apply .gitignore rules.
    """
    print(f"Scanning directory: '{os.path.abspath(input_dir)}'")
    print(f"Output file: '{os.path.abspath(output_file)}'")

    gitignore_patterns = []
    if use_gitignore:
        gitignore_path = os.path.join(input_dir, '.gitignore')
        gitignore_patterns = read_gitignore_patterns(gitignore_path)
        if gitignore_patterns:
            print(f"Using .gitignore patterns from: '{gitignore_path}'")

    file_count = 0
    skipped_count = 0
    try:
        with open(output_file, 'w', encoding='utf-8') as outfile:
            # Walk through the directory tree
            for dirpath, dirnames, filenames in os.walk(input_dir, topdown=True):

                 # Modify dirnames in-place to prevent descending into ignored directories
                original_dirnames = list(dirnames) # Copy for iteration
                dirnames[:] = [] # Clear the list that os.walk uses
                for d in original_dirnames:
                    dir_rel_path = os.path.relpath(os.path.join(dirpath, d), input_dir)
                    if use_gitignore and should_ignore(dir_rel_path, gitignore_patterns):
                         if verbose: print(f"  Ignoring directory: {dir_rel_path}")
                         skipped_count +=1 # Simplification: count dir skip as one skip
                    else:
                        dirnames.append(d) # Keep directory


                for filename in filenames:
                    source_path = os.path.join(dirpath, filename)
                    relative_path = os.path.relpath(source_path, input_dir)

                    # Convert to forward slashes for consistency in markers
                    marker_path = relative_path.replace(os.sep, '/')

                    # --- Check if file should be ignored ---
                    # Skip the output file itself if it's inside the input directory
                    if os.path.abspath(source_path) == os.path.abspath(output_file):
                        if verbose: print(f"  Skipping output file itself: {relative_path}")
                        continue

                    # Check against .gitignore patterns
                    if use_gitignore and should_ignore(relative_path, gitignore_patterns):
                        if verbose: print(f"  Ignoring file (gitignore): {relative_path}")
                        skipped_count += 1
                        continue
                    # ---------------------------------------


                    print(f"Processing file: {relative_path}")
                    file_count += 1

                    try:
                        with open(source_path, 'r', encoding='utf-8') as infile:
                            content = infile.read()
                    except UnicodeDecodeError:
                        print(f"Warning: Skipping file '{relative_path}' due to UnicodeDecodeError (likely binary file).", file=sys.stderr)
                        skipped_count += 1
                        continue
                    except Exception as e:
                        print(f"Warning: Skipping file '{relative_path}' due to read error: {e}", file=sys.stderr)
                        skipped_count += 1
                        continue

                    language = get_language_identifier(filename)

                    # --- Write formatted output ---
                    # Add blank line before start marker (unless it's the very first file)
                    if file_count > 1:
                         outfile.write("\n")

                    # 1. Start Marker
                    outfile.write(f"{START_MARKER_PREFIX}{marker_path}{MARKER_SUFFIX}\n")
                    # 2. Opening Code Fence
                    outfile.write(f"{CODE_FENCE_MARKER}{language}\n")
                    # 3. File Content (as is)
                    outfile.write(content)
                    # Ensure content ends with a newline before the fence if it doesn't already
                    if not content.endswith('\n'):
                        outfile.write("\n")
                    # 4. Closing Code Fence
                    outfile.write(f"{CODE_FENCE_MARKER}\n")
                    # 5. End Marker
                    outfile.write(f"{END_MARKER_PREFIX}{marker_path}{MARKER_SUFFIX}\n")
                    # --- End writing ---

    except OSError as e:
        print(f"Error writing to output file '{output_file}': {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\nDump generation finished.")
    print(f"Processed {file_count} files.")
    if skipped_count > 0:
        print(f"Skipped {skipped_count} files/directories.")
    print(f"Output written to: '{os.path.abspath(output_file)}'")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create a single dump file from a directory structure, formatted for AI parsing.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "input_dir",
        metavar="INPUT_DIR",
        help="Path to the source directory containing the files."
    )
    parser.add_argument(
        "output_file",
        metavar="OUTPUT_FILE",
        nargs='?', # Make output file optional
        default=DEFAULT_OUTPUT_FILENAME,
        help=f"Path to the output dump file to create (default: {DEFAULT_OUTPUT_FILENAME})."
    )
    parser.add_argument(
        "--no-gitignore",
        action="store_false", # Sets use_gitignore to False if present
        dest="use_gitignore",
        help="Do not read or apply .gitignore rules."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Increase output verbosity (show skipped files/dirs)."
    )

    args = parser.parse_args()

    # --- Validate Input Directory ---
    if not os.path.isdir(args.input_dir):
        print(f"Error: Input directory not found or is not a directory: '{args.input_dir}'", file=sys.stderr)
        sys.exit(1)

    # --- Execute Main Logic ---
    try:
        create_dump(args.input_dir, args.output_file, args.verbose, args.use_gitignore)
    except Exception as e:
        print(f"A critical error occurred: {e}", file=sys.stderr)
        sys.exit(1)

    sys.exit(0) # Success