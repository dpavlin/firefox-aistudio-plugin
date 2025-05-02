import os
import re
import sys
import argparse # Import the argparse library

# --- Configuration (Defaults, can be overridden by command line) ---
# These are no longer primary config, but could serve as fallbacks if needed,
# though argparse positional arguments are usually required by default.
# INPUT_FILE_DEFAULT = "all.txt"
# OUTPUT_BASE_DIR_DEFAULT = "/tmp/all/"

START_MARKER_PREFIX = "--- START OF FILE "
END_MARKER_PREFIX = "--- END OF FILE "
MARKER_SUFFIX = " ---"
CODE_FENCE_MARKER = "```"
# Updated pattern to identify @@FILENAME@@ marker lines,
# allowing for optional common comment syntax (#, /* */, *, //) and whitespace.
FILENAME_MARKER_PATTERN = re.compile(r"^\s*(?:/\*|\*|#|//)?\s*@@FILENAME@@.*\s*(?:\*/)?\s*$")
# ---------------------

def parse_and_split_files(input_path, output_dir):
    """
    Parses the input file, removes specific code fence and @@FILENAME@@ markers,
    and splits content into individual files based on START/END markers,
    placing them in the output directory.

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
    print(f"Output directory: '{os.path.abspath(output_dir)}'") # Show absolute path

    try:
        # --- Ensure base output directory exists ---
        try:
            # Create the target directory if it doesn't exist.
            # exist_ok=True prevents an error if the directory already exists.
            os.makedirs(output_dir, exist_ok=True)
            print(f"Ensured base output directory exists: '{output_dir}'")
        except OSError as e:
             print(f"Error: Cannot create base output directory '{output_dir}': {e}", file=sys.stderr)
             # Exit here as we cannot proceed without the output directory
             sys.exit(1)
        # ------------------------------------------

        with open(input_path, 'r', encoding='utf-8') as infile:
            for line in infile:
                line_number += 1
                stripped_line = line.strip() # Use stripped for checks, but store original line

                # --- Check for START marker ---
                if not is_inside_file and stripped_line.startswith(START_MARKER_PREFIX) and stripped_line.endswith(MARKER_SUFFIX):
                    if current_file_lines:
                         print(f"Warning: Line {line_number}: Found START marker while lines were buffered unexpectedly. Discarding previous buffer.", file=sys.stderr)
                         current_file_lines = []

                    start_len = len(START_MARKER_PREFIX)
                    end_len = len(MARKER_SUFFIX)
                    filename = stripped_line[start_len:-end_len].strip()

                    if not filename:
                         print(f"Warning: Line {line_number}: Found START marker with empty filename. Skipping block.", file=sys.stderr)
                         continue

                    expected_filename = filename
                    # Construct the full path using the provided output_dir
                    output_path = os.path.join(output_dir, filename)
                    is_inside_file = True
                    first_line_after_start = True
                    current_file_lines = []
                    print(f"  -> Found START for '{filename}'. Preparing to write to '{output_path}'")
                    continue

                # --- Check for END marker ---
                elif is_inside_file and stripped_line.startswith(END_MARKER_PREFIX) and stripped_line.endswith(MARKER_SUFFIX):
                    end_filename = stripped_line[len(END_MARKER_PREFIX):-len(MARKER_SUFFIX)].strip()
                    if expected_filename and end_filename != expected_filename: # Add check for expected_filename not being None
                        print(f"Warning: Line {line_number}: END marker filename '{end_filename}' does not match expected '{expected_filename}'.", file=sys.stderr)
                    elif not expected_filename:
                         print(f"Warning: Line {line_number}: Found END marker '{end_filename}' but no file was expected (no START marker found?).", file=sys.stderr)


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
                            break # Reached actual content
                    # --- End of trimming ---

                    # --- Write the file ---
                    # Check if output_path was set (it should be if is_inside_file was true)
                    if output_path:
                        try:
                            parent_dir = os.path.dirname(output_path)
                            if parent_dir:
                                # Ensure the specific subdirectory exists (e.g., /tmp/all/extension)
                                os.makedirs(parent_dir, exist_ok=True)

                            with open(output_path, 'w', encoding='utf-8') as outfile:
                                outfile.writelines(current_file_lines)
                            print(f"  -> Finished writing '{output_path}' ({len(current_file_lines)} lines written).")

                        except OSError as e:
                            print(f"Error: Line {line_number}: Cannot create/write to file '{output_path}': {e}", file=sys.stderr)
                    else:
                         print(f"Error: Line {line_number}: Reached END marker but no output path was defined. This should not happen.", file=sys.stderr)


                    # Reset state for the next file
                    is_inside_file = False
                    expected_filename = None
                    output_path = None
                    current_file_lines = []
                    first_line_after_start = False
                    continue

                # --- Handle content lines (inside a file block) ---
                elif is_inside_file:
                    if first_line_after_start:
                        first_line_after_start = False
                        if stripped_line.startswith(CODE_FENCE_MARKER) and len(stripped_line) > len(CODE_FENCE_MARKER):
                             print(f"    - Skipping starting code fence with language: {stripped_line}")
                             continue # Skip this line

                    current_file_lines.append(line) # Append original line

                # --- Ignore lines outside any file block ---
                # else: pass

    except FileNotFoundError:
        print(f"Error: Input file '{input_path}' not found.", file=sys.stderr)
        # No need to exit here, the calling code in __main__ will handle it
        raise # Re-raise the exception to be caught in __main__

    except Exception as e:
        print(f"An unexpected error occurred during processing line {line_number}: {e}", file=sys.stderr)
        try:
            print(f"Problematic line content (approx): {line.strip()}", file=sys.stderr)
        except NameError:
             print("Problem occurred before line processing started.", file=sys.stderr)
        # Exit here because the error might be unrecoverable
        sys.exit(1)

    # --- Final Check (after loop finishes normally) ---
    if is_inside_file:
        print(f"Warning: Reached end of '{input_path}' but no END marker found for '{expected_filename}'.", file=sys.stderr)
        if output_path:
             # --- Process collected lines before potentially writing (same logic as above) ---
            while current_file_lines:
                last_line_original = current_file_lines[-1]
                last_line_stripped = last_line_original.strip()
                is_code_fence = (last_line_stripped == CODE_FENCE_MARKER)
                is_filename_marker = bool(FILENAME_MARKER_PATTERN.match(last_line_stripped))
                if is_code_fence:
                    print(f"    - Removing trailing code fence (EOF): '{last_line_stripped}'")
                    current_file_lines.pop()
                elif is_filename_marker:
                     print(f"    - Removing trailing filename marker (EOF): '{last_line_stripped}'")
                     current_file_lines.pop()
                else:
                    break
            # --- End of trimming ---

            if current_file_lines:
                print(f"  -> Attempting to write remaining buffer to '{output_path}' due to missing END marker.")
                try:
                    parent_dir = os.path.dirname(output_path)
                    if parent_dir:
                        os.makedirs(parent_dir, exist_ok=True)
                    with open(output_path, 'w', encoding='utf-8') as outfile:
                         outfile.writelines(current_file_lines)
                    print(f"  -> Finished writing incomplete file '{output_path}' ({len(current_file_lines)} lines written).")
                except OSError as e:
                    print(f"Error: Cannot write incomplete file '{output_path}': {e}", file=sys.stderr)
            else:
                print(f"  -> No content left for '{expected_filename}' after trimming markers, file not written (EOF).")
        else:
             print(f"  -> No output path defined for file '{expected_filename}', nothing written (EOF).")


    print(f"\nProcessing finished.")
    # The final message now uses the potentially user-provided output_dir
    print(f"Generated files should be under '{os.path.abspath(output_dir)}'")


if __name__ == "__main__":
    # --- Command Line Argument Parsing ---
    parser = argparse.ArgumentParser(
        description="Parse a single text file containing multiple files marked by specific delimiters "
                    "and extract them into a specified directory structure.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter # Shows defaults in help message
    )

    # Positional arguments (required)
    parser.add_argument(
        "input_file",
        metavar="INPUT_PATH", # How it appears in help messages
        help="Path to the input text file (e.g., all.txt)"
    )
    parser.add_argument(
        "output_dir",
        metavar="OUTPUT_DIR",
        help="Path to the base directory where output files will be created (e.g., /tmp/extracted_files)"
    )

    # Optional arguments (example - could add flags later if needed)
    # parser.add_argument(
    #     "-v", "--verbose",
    #     action="store_true", # Sets verbose to True if flag is present
    #     help="Increase output verbosity"
    # )

    args = parser.parse_args() # Parse the command line arguments

    # --- Execute Main Logic ---
    try:
        # Pass the parsed arguments to the main function
        parse_and_split_files(args.input_file, args.output_dir)
    except FileNotFoundError:
        # Error message already printed by the function, just exit gracefully
        sys.exit(1)
    except Exception as e:
        # Catch any other unexpected errors during the overall process
        print(f"A critical error occurred: {e}", file=sys.stderr)
        sys.exit(1)

    # If everything completed successfully, exit with code 0
    sys.exit(0)
