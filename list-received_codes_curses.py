# @@FILENAME@@ list-received_codes_curses_adaptive.py
#!/usr/bin/env python3

# list-received_codes_curses_adaptive.py: Interactive viewer using Python curses.
# Shows filename, size, and modification time (sorted newest first).
# Adapts filename width to terminal size, prioritizing size/time columns.
# Select to view with 'less'.

import os
import sys
import subprocess
import argparse
import shutil
from pathlib import Path
import curses
import datetime
import math

DEFAULT_CODES_DIR = Path("./received_codes")
MAX_FILES = 40

def check_dependencies():
    """Check if 'less' command is available."""
    if not shutil.which("less"):
        print("Warning: 'less' command not found. Viewing files might fail.", file=sys.stderr)

def get_files_list(codes_dir: Path) -> list[Path]:
    """Gets the list of latest file paths, sorted newest first."""
    print(f"Scanning '{codes_dir}'...", file=sys.stderr)
    try:
        all_entries = list(codes_dir.iterdir())
        files = [p for p in all_entries if p.is_file()]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True) # Sort newest first
        return files[:MAX_FILES]
    except FileNotFoundError:
        return []
    except OSError as e:
        print(f"Error listing directory '{codes_dir}': {e}", file=sys.stderr)
        return []

def human_readable_size(size_bytes):
    """Converts bytes to a human-readable string (KB, MB, GB), fixed width."""
    if size_bytes == 0:
        return "    0B" # Ensure width matches others
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    # Ensure index stays within bounds
    max_i = len(size_name) - 1
    i = min(max_i, int(math.floor(math.log(size_bytes, 1024)))) if size_bytes > 0 else 0
    p = math.pow(1024, i)
    s = round(size_bytes / p, 1) if i > 0 else size_bytes
    unit = size_name[i]

    # Format: Right-aligned, 7 chars total (e.g., " 123.4KB", "   987B")
    if i == 0: # Bytes
        return f"{int(s): >7}{unit}"
    else:
        return f"{s: >6.1f}{unit}" # e.g. " 123.4K", add B later

def format_mtime(timestamp):
    """Formats a Unix timestamp into YYYY-MM-DD HH:MM."""
    dt_object = datetime.datetime.fromtimestamp(timestamp)
    return dt_object.strftime("%Y-%m-%d %H:%M")

def curses_selector(stdscr, files_with_paths: list[Path], initial_index: int) -> tuple[Path | None, int]:
    """
    Main curses function to display the list with details and handle selection.
    Prioritizes showing size/time, crops filename.
    Returns: (selected_path or None, last_highlighted_index)
    """
    if not files_with_paths:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        msg = "No files found in directory."
        try: stdscr.addstr(h // 2, (w - len(msg)) // 2, msg)
        except curses.error: pass
        stdscr.refresh(); stdscr.nodelay(False); stdscr.getch()
        return None, 0

    curses.curs_set(0); stdscr.nodelay(False); stdscr.keypad(True)
    has_colors = curses.has_colors()
    if has_colors:
        curses.start_color()
        try:
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE) # Highlight
            curses.init_pair(2, curses.COLOR_CYAN, -1)                  # Header
        except curses.error: has_colors = False

    current_row_idx = max(0, min(initial_index, len(files_with_paths) - 1))
    top_row_idx = 0

    # Define FIXED column widths
    size_col_width = 8  # Includes unit (e.g., " 123.4KB")
    time_col_width = 16 # "YYYY-MM-DD HH:MM"
    num_col_width = 4   # " 40:"
    col_spacer = " | "
    num_spacers = 3
    fixed_total_width = size_col_width + time_col_width + num_col_width + (len(col_spacer) * num_spacers)
    min_filename_width = 5 # Minimum space for filename (e.g., "fi...")

    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()

        # --- Calculate available filename width dynamically ---
        available_filename_width = max(min_filename_width, w - fixed_total_width - 1) # -1 for safety/padding

        # --- Display Header ---
        if w < fixed_total_width + min_filename_width: # Check if terminal is too narrow
             try: stdscr.addstr(0, 0, "Terminal too narrow!".center(w-1))
             except curses.error: pass
        else:
            header_text = f"{'#':<{num_col_width-1}}{col_spacer}{'Filename':<{available_filename_width}}{col_spacer}{'Size':>{size_col_width}}{col_spacer}{'Modified':>{time_col_width}}"
            header_text = header_text[:w-1] # Final safety truncate
            try:
                header_attrs = curses.color_pair(2) | curses.A_BOLD if has_colors else curses.A_BOLD
                stdscr.attron(header_attrs); stdscr.addstr(0, 0, header_text); stdscr.attroff(header_attrs)
            except curses.error: pass # Ignore if still too small

        # --- Display Footer ---
        try:
            footer_text = "Enter=View, q/ESC=Quit, Arrows/PgUp/Dn/g/G=Navigate"[:w-1]
            stdscr.addstr(h-1, 0, footer_text)
        except curses.error: pass

        # --- Calculate visible rows ---
        list_h = h - 2
        if list_h <= 0: # Terminal too small even for header/footer
             stdscr.refresh()
             key = stdscr.getch()
             if key == ord('q') or key == 27: return None, current_row_idx
             continue

        # Scroll list if necessary
        if current_row_idx < top_row_idx: top_row_idx = current_row_idx
        elif current_row_idx >= top_row_idx + list_h: top_row_idx = current_row_idx - list_h + 1

        # --- Display List Items ---
        for i in range(list_h):
            list_idx = top_row_idx + i
            if list_idx >= len(files_with_paths): break

            file_path = files_with_paths[list_idx]
            try:
                stat_info = file_path.stat()
                size_str = human_readable_size(stat_info.st_size)
                mtime_str = format_mtime(stat_info.st_mtime)
            except OSError:
                size_str = "Error".rjust(size_col_width)
                mtime_str = "Error".rjust(time_col_width)

            filename = file_path.name
            # Truncate filename based on *calculated available width*
            if len(filename) > available_filename_width:
                filename = filename[:available_filename_width - 3] + "..."

            num_str = f"{list_idx+1}:"
            # Construct string using the calculated filename width
            display_str = f"{num_str:<{num_col_width}}{col_spacer}{filename:<{available_filename_width}}{col_spacer}{size_str:>{size_col_width}}{col_spacer}{mtime_str:>{time_col_width}}"

            screen_row = i + 1
            attrs = curses.A_NORMAL
            if list_idx == current_row_idx:
                attrs = curses.color_pair(1) if has_colors else curses.A_REVERSE

            # Display the line, truncating only if absolutely necessary (shouldn't be if calcs are right)
            try:
                stdscr.addstr(screen_row, 0, display_str[:w-1], attrs)
            except curses.error:
                break

        stdscr.refresh()

        # --- Handle Input ---
        key = stdscr.getch()

        if key == curses.KEY_UP: current_row_idx = max(0, current_row_idx - 1)
        elif key == curses.KEY_DOWN: current_row_idx = min(len(files_with_paths) - 1, current_row_idx + 1)
        elif key == curses.KEY_PPAGE: current_row_idx = max(0, current_row_idx - list_h); top_row_idx = max(0, top_row_idx - list_h)
        elif key == curses.KEY_NPAGE: current_row_idx = min(len(files_with_paths) - 1, current_row_idx + list_h); top_row_idx = min(max(0, len(files_with_paths) - list_h), top_row_idx + list_h); current_row_idx = max(top_row_idx, min(current_row_idx, top_row_idx + list_h - 1))
        elif key == ord('g') or key == curses.KEY_HOME: current_row_idx = 0; top_row_idx = 0
        elif key == ord('G') or key == curses.KEY_END: current_row_idx = len(files_with_paths) - 1; top_row_idx = max(0, current_row_idx - list_h + 1)
        elif key == ord('q') or key == 27: return None, current_row_idx
        elif key == curses.KEY_ENTER or key == 10 or key == 13:
            if 0 <= current_row_idx < len(files_with_paths):
                 selected_path = files_with_paths[current_row_idx].resolve()
                 return selected_path, current_row_idx
        elif key == curses.KEY_RESIZE: pass # Loop redraws


def view_file(filepath: Path):
    """Attempts to view the specified file using less."""
    # (No changes needed in view_file)
    if not shutil.which("less"):
        print(f"\nError: 'less' not found. Cannot view file: {filepath}", file=sys.stderr); input("Press Enter..."); return
    if not filepath.is_file():
        print(f"\nError: Path is not a file: {filepath}", file=sys.stderr); input("Press Enter..."); return
    print(f"\nViewing '{filepath.name}' with less... (Press 'q' to quit less)", file=sys.stderr)
    try: subprocess.run(["less", str(filepath)], check=False)
    except Exception as e: print(f"\nError running 'less': {e}", file=sys.stderr); input("Press Enter...")
    finally: pass


# --- Main Execution ---
def main():
    parser = argparse.ArgumentParser(
        description="Interactive viewer for recent files using Python curses.",
        epilog="Shows size and modification time (newest first), crops filename if needed. Uses 'less'."
    )
    parser.add_argument(
        "codes_dir", nargs="?", type=Path, default=DEFAULT_CODES_DIR,
        help=f"Path to the directory containing files (default: {DEFAULT_CODES_DIR})"
    )
    args = parser.parse_args()

    codes_dir: Path = args.codes_dir.resolve()
    check_dependencies()

    if not codes_dir.is_dir():
        print(f"Error: Specified directory does not exist: {codes_dir}", file=sys.stderr); sys.exit(1)

    last_selection_index = 0
    while True:
        files = get_files_list(codes_dir)
        if not files and not codes_dir.exists():
             print(f"Error: Directory '{codes_dir}' disappeared.", file=sys.stderr); break

        selected_path = None
        try:
            selected_path, last_selection_index = curses.wrapper(
                curses_selector, files, last_selection_index
            )
        except curses.error as e:
             print(f"\nCurses error: {e}\nTerminal might be too small or incompatible.", file=sys.stderr); break
        except Exception as e:
             print(f"\nError in selector loop: {e}", file=sys.stderr); break

        if selected_path is None:
            print("\nExiting.")
            break
        else:
            view_file(selected_path)
            # Loop continues

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\nOperation cancelled by user (Ctrl+C).")
    except Exception as e: print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
    finally:
        # Ensure terminal is reset if curses failed unexpectedly mid-operation
        try: curses.endwin()
        except curses.error: pass # endwin throws error if curses hasn't been initialized
        sys.exit(0)