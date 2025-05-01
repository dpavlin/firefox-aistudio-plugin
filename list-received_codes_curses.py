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
# import time # Not strictly needed now

DEFAULT_CODES_DIR = Path("./received_codes")
MAX_FILES = 40

def check_dependencies():
    """Check if 'less' command is available."""
    if not shutil.which("less"):
        print("Warning: 'less' command not found. Viewing files might fail.", file=sys.stderr)

def get_files_list(codes_dir: Path) -> list[Path]:
    """Gets the list of latest file paths, sorted newest first."""
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
    return dt_object.strftime("%Y-%m-%d %H:%M:%S")

def curses_selector(stdscr, files_with_paths: list[Path], initial_index: int) -> tuple[Path | None, int]:
    """
    Main curses function to display the list with details and handle selection.
    Optimized drawing to reduce flicker.
    Returns: (selected_path or None, last_highlighted_index)
    """
    if not files_with_paths:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        msg = "No files found in directory."
        try: stdscr.addstr(h // 2, (w - len(msg)) // 2, msg)
        except curses.error: pass
        stdscr.refresh(); stdscr.nodelay(False); stdscr.getch()
        return None, 0

    curses.curs_set(0); stdscr.nodelay(False); stdscr.keypad(True)
    has_colors = curses.has_colors()
    highlight_attr = curses.A_REVERSE
    header_attr = curses.A_BOLD
    if has_colors:
        curses.start_color()
        try:
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE) # Highlight
            curses.init_pair(2, curses.COLOR_CYAN, -1)                  # Header
            highlight_attr = curses.color_pair(1)
            header_attr = curses.color_pair(2) | curses.A_BOLD
        except curses.error: has_colors = False

    current_row_idx = max(0, min(initial_index, len(files_with_paths) - 1))
    top_row_idx = 0
    prev_top_row_idx = -1
    prev_current_row_idx = -1
    needs_redraw = True # Force initial draw

    size_col_width = 8; time_col_width = 19; num_col_width = 4
    col_spacer = " | "; num_spacers = 3
    fixed_total_width = size_col_width + time_col_width + num_col_width + (len(col_spacer) * num_spacers)
    min_filename_width = 5

    key = 0 # Initialize key variable outside the loop first iteration

    while True:
        h, w = stdscr.getmaxyx()
        list_h = h - 2

        # Handle resize BEFORE drawing/scrolling checks if the key was RESIZE
        if key == curses.KEY_RESIZE:
             needs_redraw = True
             # Re-calculate list height based on new dimensions
             list_h = h - 2
             key = 0 # Reset key so we don't process resize again immediately

        # Scroll list if necessary
        if list_h > 0:
            if current_row_idx < top_row_idx: top_row_idx = current_row_idx
            elif current_row_idx >= top_row_idx + list_h: top_row_idx = current_row_idx - list_h + 1
        else:
             top_row_idx = current_row_idx # Keep current item roughly visible if possible


        # Determine if redraw is needed
        scrolled = (top_row_idx != prev_top_row_idx)
        moved = (current_row_idx != prev_current_row_idx)

        if needs_redraw or scrolled or moved:
            # Use erase() instead of clear() for potential flicker reduction
            # (clear() does a full repaint, erase() just blanks)
            stdscr.erase()

            # Recalculate dynamic width inside redraw block
            available_filename_width = max(min_filename_width, w - fixed_total_width - 1)

            # Draw Header and Footer
            try:
                if w < fixed_total_width + min_filename_width or list_h <= 0:
                    stdscr.addstr(0, 0, "Terminal too narrow!".center(w-1))
                else:
                    header_text = f"{'#':<{num_col_width-1}}{col_spacer}{'Filename':<{available_filename_width}}{col_spacer}{'Size':>{size_col_width}}{col_spacer}{'Modified':>{time_col_width}}"
                    header_text = header_text[:w-1]
                    stdscr.attron(header_attr); stdscr.addstr(0, 0, header_text); stdscr.attroff(header_attr)

                footer_text = "Enter=View, q/ESC=Quit, Arrows/PgUp/Dn/g/G=Navigate"[:w-1]
                stdscr.addstr(h-1, 0, footer_text)
            except curses.error: pass # Ignore errors if terminal shrunk drastically

            # Draw List Area (only if height allows)
            if list_h > 0:
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
                    if len(filename) > available_filename_width:
                        filename = filename[:available_filename_width - 3] + "..."

                    num_str = f"{list_idx+1}:"
                    display_str = f"{num_str:<{num_col_width}}{col_spacer}{filename:<{available_filename_width}}{col_spacer}{size_str:>{size_col_width}}{col_spacer}{mtime_str:>{time_col_width}}"

                    screen_row = i + 1
                    attrs = curses.A_NORMAL
                    if list_idx == current_row_idx:
                        attrs = highlight_attr

                    try:
                        stdscr.addstr(screen_row, 0, display_str[:w-1], attrs) # Final truncate here
                    except curses.error: break

            prev_top_row_idx = top_row_idx
            prev_current_row_idx = current_row_idx
            needs_redraw = False
            stdscr.refresh()

        # Get Input AFTER drawing is complete for the current state
        key = stdscr.getch()

        # Process Input
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
             needs_redraw = True # Will trigger redraw on next loop
             # Don't need 'continue' here, just let loop proceed
        # else: ignore other keys

def view_file(filepath: Path):
    """Attempts to view the specified file using less."""
    # (No changes needed in view_file)
    if not shutil.which("less"): print(f"\nError: 'less' not found: {filepath}", file=sys.stderr); input("Press Enter..."); return
    if not filepath.is_file(): print(f"\nError: Not a file: {filepath}", file=sys.stderr); input("Press Enter..."); return
    print(f"\nViewing '{filepath.name}' with less... (Press 'q' to quit less)", file=sys.stderr)
    try: subprocess.run(["less", str(filepath)], check=False)
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

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\nOperation cancelled by user (Ctrl+C).")
    except Exception as e: print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
    finally:
        try:
             if sys.stdout.isatty(): curses.endwin()
        except Exception: pass
        sys.exit(0)