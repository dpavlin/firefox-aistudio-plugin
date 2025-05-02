import os
import re
import sys
import argparse

# --- Configuration ---
START_MARKER_PREFIX = "--- START OF FILE "
END_MARKER_BASE_PREFIX = "--- END OF " # Used for flexible END marker parsing
MARKER_SUFFIX = " ---"
CODE_FENCE_MARKER = "```"
# Pattern to identify @@FILENAME@@ marker lines,
# allowing for optional common comment syntax (#, /* */, *, //) and whitespace.
FILENAME_MARKER_PATTERN = re.compile(r"^\s*(?:/\*|\*|#|//)?\s*@@FILENAME@@.*\s*(?:\*/)?\s*$")
# ---------------------

def extract_filename_from_end_marker(line_content):
    """
    Extracts the filename from different END marker formats.

    Args:
        line_content (str): The content of the line between the base prefix
                           '--- END OF ' and the suffix ' ---'.

    Returns:
        str or None: The extracted filename if successful, otherwise None.
    """
    content = line_content.strip()
    # Case 1: --- END OF FILE filename ---
    if content.startswith("FILE "):
        filename = content[len("FILE "):].strip()
        return filename
    # Case 2: --- END OF `filename` ---
    elif content.startswith("`") and content.endswith("`"):
        filename = content[1:-1].strip() # Extract content between backticks
        if filename: # Check it's not just ``
            return filename
    # Case 3: --- END OF @@FILENAME@@ filename --- (NEW)
    elif content.startswith("@@FILENAME@@ "):
        filename = content[len("@@FILENAME@@ "):].strip()
        return filename

    return None # Format not recognized


def parse_and_split_files(input_path, output_dir):
    """
    Parses the input file, removes specific code fence and @@FILENAME@@ markers,
    and splits content into individual files based on START/END markers,
    placing them in the output directory. Handles multiple START/END marker formats.

    Args:
        input_path (str): Path to the input file.
        output_dir (str): Path to the base directory for output files.
    """
    current_file_lines = []
    is_inside_file = False
    expected_filename = None
    output_path = None
    line_number = 0
    first_line_after_start = False # Flag to check for starting code fence

    print(f"Starting parsing of '{input_path}'...")
    print(f"Output directory: '{os.path.abspath(output_dir)}'")

    try:
        # --- Ensure base output directory exists ---
        try:
            os.makedirs(output_dir, exist_ok=True)
            print(f"Ensured base output directory exists: '{output_dir}'")
        except OSError as e:
             print(f"Error: Cannot create base output directory '{output_dir}': {e}", file=sys.stderr)
             sys.exit(1)
        # ------------------------------------------

        with open(input_path, 'r', encoding='utf-8') as infile:
            for line in infile:
                line_number += 1
                stripped_line = line.strip() # Use stripped for checks

                # --- Check for START marker ---
                if not is_inside_file and stripped_line.startswith(START_MARKER_PREFIX) and stripped_line.endswith(MARKER_SUFFIX):
                    if current_file_lines:
                         print(f"Warning: Line {line_number}: Found START marker while lines were buffered unexpectedly. Discarding previous buffer.", file=sys.stderr)
                         current_file_lines = []

                    start_len = len(START_MARKER_PREFIX)
                    end_len = len(MARKER_SUFFIX)
                    # Extract raw filename, potentially with backticks
                    raw_filename = stripped_line[start_len:-end_len].strip()

                    if not raw_filename:
                         print(f"Warning: Line {line_number}: Found START marker with empty filename. Skipping block.", file=sys.stderr)
                         continue

                    # --- FIX: Strip backticks from filename ---
                    filename = raw_filename
                    if filename.startswith("`") and filename.endswith("`") and len(filename) > 1:
                        filename = filename[1:-1].strip()
                        if not filename: # Handle case of just "``"
                            print(f"Warning: Line {line_number}: Found START marker with empty filename inside backticks: {stripped_line}. Skipping block.", file=sys.stderr)
                            continue
                    # --- End of FIX ---

                    # Use the cleaned filename
                    expected_filename = filename
                    output_path = os.path.join(output_dir, filename) # Use cleaned name for path
                    is_inside_file = True
                    first_line_after_start = True
                    current_file_lines = []
                    # Print cleaned filename
                    print(f"  -> Found START for '{filename}'. Preparing to write to '{output_path}'")
                    continue

                # --- Check for END marker (flexible format) ---
                elif is_inside_file and stripped_line.startswith(END_MARKER_BASE_PREFIX) and stripped_line.endswith(MARKER_SUFFIX):
                    marker_content = stripped_line[len(END_MARKER_BASE_PREFIX):-len(MARKER_SUFFIX)]
                    # Use updated function to extract filename
                    end_filename = extract_filename_from_end_marker(marker_content)

                    if end_filename is None:
                         print(f"Warning: Line {line_number}: Unrecognized END marker format: {stripped_line}", file=sys.stderr)
                         continue # Skip only the marker line

                    # Compare extracted filename with expected (now cleaned) filename
                    if expected_filename and end_filename != expected_filename:
                        print(f"Warning: Line {line_number}: END marker filename '{end_filename}' does not match expected '{expected_filename}'.", file=sys.stderr)
                    elif not expected_filename:
                         print(f"Warning: Line {line_number}: Found END marker '{end_filename}' but no file was expected.", file=sys.stderr)

                    # --- Process collected lines before writing ---
                    while current_file_lines:
                        last_line_original = current_file_lines[-1]
                        last_line_stripped = last_line_original.strip()
                        is_code_fence = (last_line_stripped == CODE_FENCE_MARKER)
                        is_filename_marker = bool(FILENAME_MARKER_PATTERN.match(last_line_stripped))

                        if is_code_fence:
                            print(f"    - Removing trailing code fence: '{last_line_stripped}'")
                            current_file_lines.pop()
                        elif is_filename_marker:
                             print(f"    - Removing trailing filename marker: '{last_line_stripped}'")
                             current_file_lines.pop()
                        else:
                            break
                    # --- End of trimming ---

                    # --- Write the file ---
                    if output_path:
                        try:
                            parent_dir = os.path.dirname(output_path)
                            if parent_dir:
                                os.makedirs(parent_dir, exist_ok=True)
                            with open(output_path, 'w', encoding='utf-8') as outfile:
                                outfile.writelines(current_file_lines)
                            print(f"  -> Finished writing '{output_path}' ({len(current_file_lines)} lines written).")
                        except OSError as e:
                            print(f"Error: Line {line_number}: Cannot create/write to file '{output_path}': {e}", file=sys.stderr)
                    else:
                         print(f"Error: Line {line_number}: Reached END marker but no output path was defined.", file=sys.stderr)

                    # Reset state
                    is_inside_file = False
                    expected_filename = None
                    output_path = None
                    current_file_lines = []
                    first_line_after_start = False
                    continue

                # --- Handle content lines ---
                elif is_inside_file:
                    if first_line_after_start:
                        first_line_after_start = False
                        if stripped_line.startswith(CODE_FENCE_MARKER) and len(stripped_line) > len(CODE_FENCE_MARKER):
                             print(f"    - Skipping starting code fence with language: {stripped_line}")
                             continue
                    current_file_lines.append(line)

    except FileNotFoundError:
        print(f"Error: Input file '{input_path}' not found.", file=sys.stderr)
        raise

    except Exception as e:
        print(f"An unexpected error occurred during processing line {line_number}: {e}", file=sys.stderr)
        try: print(f"Problematic line content (approx): {line.strip()}", file=sys.stderr)
        except NameError: pass
        sys.exit(1)

    # --- Final Check ---
    if is_inside_file:
        print(f"Warning: Reached end of '{input_path}' but no END marker found for '{expected_filename}'.", file=sys.stderr)
        if output_path:
            while current_file_lines: # Trim trailing markers
                last_line_original = current_file_lines[-1]
                last_line_stripped = last_line_original.strip()
                is_code_fence = (last_line_stripped == CODE_FENCE_MARKER)
                is_filename_marker = bool(FILENAME_MARKER_PATTERN.match(last_line_stripped))
                if is_code_fence or is_filename_marker:
                    print(f"    - Removing trailing {'code fence' if is_code_fence else 'filename marker'} (EOF): '{last_line_stripped}'")
                    current_file_lines.pop()
                else: break

            if current_file_lines: # Write if content remains
                print(f"  -> Attempting to write remaining buffer to '{output_path}' due to missing END marker.")
                try:
                    parent_dir = os.path.dirname(output_path)
                    if parent_dir: os.makedirs(parent_dir, exist_ok=True)
                    with open(output_path, 'w', encoding='utf-8') as outfile:
                         outfile.writelines(current_file_lines)
                    print(f"  -> Finished writing incomplete file '{output_path}' ({len(current_file_lines)} lines written).")
                except OSError as e:
                    print(f"Error: Cannot write incomplete file '{output_path}': {e}", file=sys.stderr)
            else: print(f"  -> No content left for '{expected_filename}' after trimming markers, file not written (EOF).")
        else: print(f"  -> No output path defined for file '{expected_filename}', nothing written (EOF).")

    print(f"\nProcessing finished.")
    print(f"Generated files should be under '{os.path.abspath(output_dir)}'")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Parse a single text file containing multiple files marked by specific delimiters "
                    "and extract them into a specified directory structure.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("input_file", metavar="INPUT_PATH", help="Path to the input text file (e.g., all.txt)")
    parser.add_argument("output_dir", metavar="OUTPUT_DIR", help="Path to the base directory where output files will be created")
    args = parser.parse_args()
    try:
        parse_and_split_files(args.input_file, args.output_dir)
    except FileNotFoundError: sys.exit(1)
    except Exception as e:
        print(f"A critical error occurred: {e}", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)