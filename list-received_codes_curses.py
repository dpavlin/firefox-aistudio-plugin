# @@FILENAME@@ list-received_codes_curses.py
#!/usr/bin/env python3

# list-received_codes_curses.py: Interactive viewer using Python curses.
# Select a file from the list to view with 'less'.

import os
import sys
import subprocess
import argparse
import shutil
from pathlib import Path
import curses # Standard library for terminal handling

DEFAULT_CODES_DIR = Path("./received_codes")
MAX_FILES = 40 # Or adjust as needed

def check_dependencies():
    """Check if 'less' command is available."""
    if not shutil.which("less"):
        print("Warning: 'less' command not found. Viewing files might fail.", file=sys.stderr)
        # Continue execution, viewing will just fail later

def get_files_list(codes_dir: Path) -> list[Path]:
    """Gets the list of latest file paths, sorted newest first."""
    print(f"Scanning '{codes_dir}'...", file=sys.stderr) # Initial message before curses starts
    try:
        all_entries = list(codes_dir.iterdir())
        files = [p for p in all_entries if p.is_file()]
        # Sort by modification time, newest first
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return files[:MAX_FILES]
    except FileNotFoundError:
        # Error will be handled after curses wrapper exits
        return []
    except OSError as e:
        print(f"Error listing directory '{codes_dir}': {e}", file=sys.stderr)
        return [] # Treat as empty

def curses_selector(stdscr, files_with_paths: list[Path], initial_index: int) -> tuple[Path | None, int]:
    """
    Main curses function to display the list and handle selection.
    Args:
        stdscr: The main window object provided by curses.wrapper.
        files_with_paths: List of Path objects to display.
        initial_index: The index to initially highlight.
    Returns:
        A tuple containing:
        - The selected Path object (absolute) if Enter is pressed.
        - None if 'q' or ESC is pressed.
        - The index that was highlighted when the function exited.
    """
    if not files_with_paths:
        # Display message if list is empty within curses window
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        msg = "No files found in directory."
        try:
             stdscr.addstr(h // 2, (w - len(msg)) // 2, msg)
        except curses.error: # Handle terminals that are too small
             pass # Cannot display message
        stdscr.refresh()
        stdscr.nodelay(False) # Wait for key press
        stdscr.getch() # Wait for any key
        return None, 0

    curses.curs_set(0)  # Hide cursor
    stdscr.nodelay(False) # Wait for user input
    stdscr.keypad(True)   # Enable capture of special keys (arrows, etc.)

    # Colors (optional, makes selection clearer)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE) # Highlighted pair

    current_row_idx = max(0, min(initial_index, len(files_with_paths) - 1))
    top_row_idx = 0 # Index of the file displayed at the top row

    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()

        # --- Display Instructions ---
        title = "Select File to View (Use Arrows, PgUp/Dn, g/G, Enter, q/ESC)"[:w-1]
        try:
            stdscr.addstr(0, 0, title)
            stdscr.addstr(h-1, 0, "Enter=View, q/ESC=Quit"[:w-1])
        except curses.error:
            pass # Ignore if terminal too small for instructions

        # --- Calculate visible rows ---
        list_h = h - 2 # Available height for list items (excluding title/footer)
        if list_h <= 0: # Terminal too small
             try:
                 stdscr.addstr(1, 0, "Terminal too small".center(w-1))
             except curses.error:
                 pass
             stdscr.refresh()
             key = stdscr.getch()
             if key == ord('q') or key == 27: # Allow quitting even if small
                 return None, current_row_idx
             continue # Otherwise just wait

        # Ensure current selection is visible
        if current_row_idx < top_row_idx:
            top_row_idx = current_row_idx
        elif current_row_idx >= top_row_idx + list_h:
            top_row_idx = current_row_idx - list_h + 1

        # --- Display List Items ---
        for i in range(list_h):
            list_idx = top_row_idx + i
            if list_idx >= len(files_with_paths):
                break # Don't try to display past the end of the list

            filename = files_with_paths[list_idx].name
            display_str = f"{list_idx+1: >3d}: {filename}" # Add line number
            display_str = display_str[:w-1] # Truncate if too wide

            screen_row = i + 1 # Start list below title row

            try:
                if list_idx == current_row_idx:
                    stdscr.attron(curses.color_pair(1))
                    stdscr.addstr(screen_row, 0, display_str)
                    stdscr.attroff(curses.color_pair(1))
                else:
                    stdscr.addstr(screen_row, 0, display_str)
            except curses.error:
                # Likely window too small even for truncated string, break loop
                break

        stdscr.refresh()

        # --- Handle Input ---
        key = stdscr.getch()

        if key == curses.KEY_UP:
            current_row_idx = max(0, current_row_idx - 1)
        elif key == curses.KEY_DOWN:
            current_row_idx = min(len(files_with_paths) - 1, current_row_idx + 1)
        elif key == curses.KEY_PPAGE: # Page Up
            current_row_idx = max(0, current_row_idx - list_h)
            top_row_idx = max(0, top_row_idx - list_h)
        elif key == curses.KEY_NPAGE: # Page Down
            current_row_idx = min(len(files_with_paths) - 1, current_row_idx + list_h)
            top_row_idx = min(len(files_with_paths) - list_h, top_row_idx + list_h)
            # Ensure current is still visible after page down adjustment
            if current_row_idx >= top_row_idx + list_h:
                 top_row_idx = current_row_idx - list_h + 1

        elif key == ord('g') or key == curses.KEY_HOME:
            current_row_idx = 0
            top_row_idx = 0
        elif key == ord('G') or key == curses.KEY_END:
            current_row_idx = len(files_with_paths) - 1
            top_row_idx = max(0, current_row_idx - list_h + 1)
        elif key == ord('q') or key == 27: # 27 is ESC key code
            return None, current_row_idx # Quit selection
        elif key == curses.KEY_ENTER or key == 10 or key == 13: # 10 is \n, 13 is \r
            if 0 <= current_row_idx < len(files_with_paths):
                 selected_path = files_with_paths[current_row_idx].resolve()
                 return selected_path, current_row_idx # Return selected absolute path and index
            # else: Index somehow out of bounds? Loop again.
        # Ignore other keys for now

def view_file(filepath: Path):
    """Attempts to view the specified file using less."""
    # (Keep the view_file function mostly the same, accepting Path)
    if not shutil.which("less"):
        print(f"\nError: 'less' command not found. Cannot view file: {filepath}", file=sys.stderr)
        input("Press Enter to continue...")
        return

    if not filepath.is_file():
        print(f"\nError: Cannot view - path is not a file: {filepath}", file=sys.stderr)
        input("Press Enter to continue...")
        return

    print(f"\nViewing '{filepath.name}' with less... (Press 'q' to quit less)", file=sys.stderr)
    try:
        # Run less, allow it to take over terminal
        subprocess.run(["less", str(filepath)], check=False) # Pass path as string
    except FileNotFoundError:
        print("\nError: 'less' command failed. Cannot view file.", file=sys.stderr)
        input("Press Enter to continue...")
    except KeyboardInterrupt:
        print("\n'less' interrupted.", file=sys.stderr)
    except Exception as e:
        print(f"\nError running 'less': {e}", file=sys.stderr)
        input("Press Enter to continue...")
    finally:
        # No "Returning to list" message needed here as curses handles screen redraw
        pass


# --- Main Execution ---
def main():
    parser = argparse.ArgumentParser(
        description="Interactive viewer for recent files using Python curses.",
        epilog="Uses 'less' for viewing."
    )
    parser.add_argument(
        "codes_dir",
        nargs="?",
        type=Path,
        default=DEFAULT_CODES_DIR,
        help=f"Path to the directory containing files (default: {DEFAULT_CODES_DIR})"
    )
    args = parser.parse_args()

    codes_dir: Path = args.codes_dir.resolve()

    check_dependencies() # Check for 'less'

    if not codes_dir.is_dir():
        print(f"Error: Specified directory does not exist: {codes_dir}", file=sys.stderr)
        sys.exit(1)

    # Store the index of the last viewed item to re-highlight it
    last_selection_index = 0

    while True:
        files = get_files_list(codes_dir)
        if not files and not codes_dir.exists():
            # Directory might have been deleted between checks
             print(f"Error: Directory '{codes_dir}' disappeared.", file=sys.stderr)
             break
        # If files list is empty but dir exists, curses_selector will handle message

        try:
            # curses.wrapper handles terminal setup and cleanup
            selected_path, last_selection_index = curses.wrapper(
                curses_selector, files, last_selection_index
            )
        except curses.error as e:
             print(f"\nCurses error: {e}", file=sys.stderr)
             print("Terminal might be too small or incompatible.", file=sys.stderr)
             break # Exit loop on curses errors
        except Exception as e:
             print(f"\nAn unexpected error occurred in the selector: {e}", file=sys.stderr)
             break


        if selected_path is None:
            # User quit the selector
            print("\nExiting.")
            break
        else:
            # User selected a file, view it
            view_file(selected_path)
            # Loop continues, list will refresh, last_selection_index is preserved

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user (Ctrl+C).")
        # curses.wrapper should have cleaned up the terminal
        sys.exit(0)