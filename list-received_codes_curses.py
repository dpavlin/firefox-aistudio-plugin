#!/usr/bin/env python3

# list-received_codes_curses.py: Interactive viewer using Python curses.
# Shows filename, size, and modification time (YYYY-MM-DD HH:MM:SS, newest first).
# Adapts filename width, crops filename if needed. Select to view with 'less'.
# Optimized drawing to reduce flicker.

import os
import sys
import subprocess
import argparse
import shutil
from pathlib import Path
import curses
import datetime
import math
import time # For potential small delays if needed

DEFAULT_CODES_DIR = Path("./received_codes")
MAX_FILES = 40

def check_dependencies():
    """Check if 'less' command is available."""
    if not shutil.which("less"):
        print("Warning: 'less' command not found. Viewing files might fail.", file=sys.stderr)

def get_files_list(codes_dir: Path) -> list[Path]:
    """Gets the list of latest file paths, sorted newest first."""
    # Keep console message minimal as screen will be taken over shortly
    # print(f"Scanning '{codes_dir}'...", file=sys.stderr)
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
    if size_bytes == 0: return "    0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    max_i = len(size_name) - 1
    i = min(max_i, int(math.floor(math.log(size_bytes, 1024)))) if size_bytes > 0 else 0
    p = math.pow(1024, i)
    s = round(size_bytes / p, 1) if i > 0 else size_bytes
    unit = size_name[i]
    if i == 0: return f"{int(s): >7}{unit}"
    else: return f"{s: >6.1f}{unit}"

def format_mtime(timestamp):
    """Formats a Unix timestamp into YYYY-MM-DD HH:MM:SS."""
    dt_object = datetime.datetime.fromtimestamp(timestamp)
    return dt_object.strftime("%Y-%m-%d %H:%M:%S") # Added seconds

def curses_selector(stdscr, files_with_paths: list[Path], initial_index: int) -> tuple[Path | None, int]:
    """
    Main curses function to display the list with details and handle selection.
    Optimized drawing to reduce flicker.
    Returns: (selected_path or None, last_highlighted_index)
    """
    if not files_with_paths:
        stdscr.erase() # Clear screen before showing message
        h, w = stdscr.getmaxyx()
        msg = "No files found in directory."
        try: stdscr.addstr(h // 2, (w - len(msg)) // 2, msg)
        except curses.error: pass
        stdscr.refresh(); stdscr.nodelay(False); stdscr.getch()
        return None, 0

    curses.curs_set(0); stdscr.nodelay(False); stdscr.keypad(True)
    has_colors = curses.has_colors()
    highlight_attr = curses.A_REVERSE # Fallback attribute
    header_attr = curses.A_BOLD
    if has_colors:
        curses.start_color()
        try:
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE) # Highlight
            curses.init_pair(2, curses.COLOR_CYAN, -1)                  # Header
            highlight_attr = curses.color_pair(1)
            header_attr = curses.color_pair(2) | curses.A_BOLD
        except curses.error: has_colors = False # Fallback to attributes without color

    current_row_idx = max(0, min(initial_index, len(files_with_paths) - 1))
    top_row_idx = 0
    # Force redraw on first loop iteration
    prev_top_row_idx = -1
    prev_current_row_idx = -1
    needs_redraw = True # Flag to force redraw

    # Define FIXED column widths
    size_col_width = 8  # e.g., " 123.4KB"
    time_col_width = 19 # "YYYY-MM-DD HH:MM:SS" - Increased width
    num_col_width = 4   # " 40:"
    col_spacer = " | "
    num_spacers = 3
    fixed_total_width = size_col_width + time_col_width + num_col_width + (len(col_spacer) * num_spacers)
    min_filename_width = 5

    # --- Main Loop ---
    while True:
        h, w = stdscr.getmaxyx()

        # Handle terminal resize event
        if key == curses.KEY_RESIZE:
             needs_redraw = True
             # Optional: Clear screen fully on resize if artifacts appear
             # stdscr.clear()

        # --- Calculate available filename width dynamically ---
        available_filename_width = max(min_filename_width, w - fixed_total_width - 1)

        # --- Scroll list if necessary (adjust before redraw check) ---
        list_h = h - 2 # Available height for list items
        if list_h <= 0: # Terminal too small to display list
             stdscr.erase()
             try:
                 stdscr.addstr(0, 0, "Terminal too small!".center(w-1))
                 stdscr.addstr(h-1, 0, "q/ESC=Quit"[:w-1])
             except curses.error: pass
             stdscr.refresh()
             key = stdscr.getch() # Wait for input even if small
             if key == ord('q') or key == 27: return None, current_row_idx
             needs_redraw = True # Force redraw on resize if key wasn't quit
             continue

        if current_row_idx < top_row_idx: top_row_idx = current_row_idx
        elif current_row_idx >= top_row_idx + list_h: top_row_idx = current_row_idx - list_h + 1

        # --- Determine if redraw is needed ---
        scrolled = (top_row_idx != prev_top_row_idx)
        moved = (current_row_idx != prev_current_row_idx)

        if needs_redraw or scrolled or moved:
            # --- Redraw Header and Footer (always relatively cheap) ---
            try:
                # Clear header/footer lines explicitly before redraw
                stdscr.move(0, 0); stdscr.clrtoeol()
                stdscr.move(h-1, 0); stdscr.clrtoeol()

                if w < fixed_total_width + min_filename_width:
                    stdscr.addstr(0, 0, "Terminal too narrow!".center(w-1))
                else:
                    header_text = f"{'#':<{num_col_width-1}}{col_spacer}{'Filename':<{available_filename_width}}{col_spacer}{'Size':>{size_col_width}}{col_spacer}{'Modified':>{time_col_width}}"
                    header_text = header_text[:w-1]
                    stdscr.attron(header_attr); stdscr.addstr(0, 0, header_text); stdscr.attroff(header_attr)

                footer_text = "Enter=View, q/ESC=Quit, Arrows/PgUp/Dn/g/G=Navigate"[:w-1]
                stdscr.addstr(h-1, 0, footer_text)
            except curses.error: pass # Ignore errors if terminal became too small mid-draw

            # --- Redraw List Area ---
            for i in range(list_h):
                screen_row = i + 1
                list_idx = top_row_idx + i

                # Clear the line before drawing
                try: stdscr.move(screen_row, 0); stdscr.clrtoeol()
                except curses.error: continue # Skip if can't move cursor

                if list_idx >= len(files_with_paths):
                    continue # Don't draw past the end of the list

                file_path = files_with_paths[list_idx]
                try:
                    stat_info = file_path.stat()
                    size_str = human_readable_size(stat_info.st_size)
                    mtime_str = format_mtime(stat_info.st_mtime)
                except OSError:
                    size_str = "Error".rjust(size_col_width)
                    mtime_str = "Error".rjust(time_col_width)

                filename = file_path.name
                if len(filename) > available_filename_width:
                    filename = filename[:available_filename_width - 3] + "..."

                num_str = f"{list_idx+1}:"
                display_str = f"{num_str:<{num_col_width}}{col_spacer}{filename:<{available_filename_width}}{col_spacer}{size_str:>{size_col_width}}{col_spacer}{mtime_str:>{time_col_width}}"
                display_str = display_str[:w-1] # Final safety truncate

                attrs = curses.A_NORMAL
                if list_idx == current_row_idx:
                    attrs = highlight_attr

                try:
                    stdscr.addstr(screen_row, 0, display_str, attrs)
                except curses.error:
                    # Should not happen often with pre-truncation, but handle anyway
                    break # Stop drawing if error occurs

            # Update previous state after drawing
            prev_top_row_idx = top_row_idx
            prev_current_row_idx = current_row_idx
            needs_redraw = False # Reset redraw flag

            # Move cursor logically (it's hidden anyway)
            try: stdscr.move(current_row_idx - top_row_idx + 1, 1)
            except curses.error: pass

            stdscr.refresh() # Refresh the screen *after* all updates

        # --- Handle Input ---
        key = stdscr.getch() # Wait for next key

        if key == curses.KEY_UP: current_row_idx = max(0, current_row_idx - 1)
        elif key == curses.KEY_DOWN: current_row_idx = min(len(files_with_paths) - 1, current_row_idx + 1)
        elif key == curses.KEY_PPAGE: current_row_idx = max(0, current_row_idx - list_h)
        elif key == curses.KEY_NPAGE: current_row_idx = min(len(files_with_paths) - 1, current_row_idx + list_h)
        elif key == ord('g') or key == curses.KEY_HOME: current_row_idx = 0
        elif key == ord('G') or key == curses.KEY_END: current_row_idx = len(files_with_paths) - 1
        elif key == ord('q') or key == 27: return None, current_row_idx
        elif key == curses.KEY_ENTER or key == 10 or key == 13:
            if 0 <= current_row_idx < len(files_with_paths):
                 selected_path = files_with_paths[current_row_idx].resolve()
                 return selected_path, current_row_idx
        elif key == curses.KEY_RESIZE:
             needs_redraw = True # Set flag to redraw everything on next loop
             # Don't process movement based on resize key itself
             continue # Skip straight to next loop iteration

        # If we reached here, it was a movement key or ignored key
        # The loop will check if redraw is needed based on index changes

def view_file(filepath: Path):
    """Attempts to view the specified file using less."""
    # (No changes needed in view_file)
    if not shutil.which("less"): print(f"\nError: 'less' not found: {filepath}", file=sys.stderr); input("Press Enter..."); return
    if not filepath.is_file(): print(f"\nError: Not a file: {filepath}", file=sys.stderr); input("Press Enter..."); return
    print(f"\nViewing '{filepath.name}' with less... (Press 'q' to quit less)", file=sys.stderr)
    try: subprocess.run(["less", str(filepath)], check=False) # Let less handle terminal
    except Exception as e: print(f"\nError running 'less': {e}", file=sys.stderr); input("Press Enter...")
    finally: pass

# --- Main Execution ---
def main():
    parser = argparse.ArgumentParser(
        description="Interactive viewer for recent files using Python curses.",
        epilog="Shows details, crops filename. Uses 'less'."
    )
    parser.add_argument(
        "codes_dir", nargs="?", type=Path, default=DEFAULT_CODES_DIR,
        help=f"Path to the directory containing files (default: {DEFAULT_CODES_DIR})"
    )
    args = parser.parse_args()

    codes_dir: Path = args.codes_dir.resolve()
    check_dependencies()

    if not codes_dir.is_dir():
        print(f"Error: Directory does not exist: {codes_dir}", file=sys.stderr); sys.exit(1)

    last_selection_index = 0
    while True:
        files = get_files_list(codes_dir)
        if not files and not codes_dir.exists():
             print(f"Error: Directory '{codes_dir}' disappeared.", file=sys.stderr); break

        selected_path = None
        try:
            # Clear screen before entering curses wrapper if needed
            # print("\033c", end="") # ANSI clear screen - use cautiously
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
            # Curses wrapper cleans up the screen, so less should display fine
            view_file(selected_path)
            # Loop continues, list will refresh, last_selection_index is preserved


if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\nOperation cancelled by user (Ctrl+C).")
    except Exception as e: print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
    finally:
        # Ensure terminal is reset if curses failed unexpectedly
        try:
             if sys.stdout.isatty(): # Only run endwin if we likely started curses
                 curses.endwin()
        except Exception: pass # Ignore errors during final cleanup
        sys.exit(0)