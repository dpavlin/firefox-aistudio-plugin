from flask import Flask, request, jsonify, send_from_directory, render_template_string
from flask_cors import CORS
import os
import datetime
import subprocess
import re
import sys
import argparse
from pathlib import Path
import threading # Import the threading module

# --- Argument Parser ---
parser = argparse.ArgumentParser(description='AI Code Capture Server')
parser.add_argument(
    '-p', '--port', type=int, default=5000,
    help='Port number to run the Flask server on (default: 5000)'
)
args = parser.parse_args()
SERVER_PORT = args.port

# --- Flask App Setup ---
app = Flask(__name__)
CORS(app)

# --- Create a Lock for serializing requests ---
request_lock = threading.Lock()
print("Request lock initialized.", file=sys.stderr)

# --- Configuration & Paths ---
SAVE_FOLDER = 'received_codes'; LOG_FOLDER = 'logs'
SERVER_DIR = Path.cwd().resolve() # Use Current Working Directory as the base
SAVE_FOLDER_PATH = SERVER_DIR / SAVE_FOLDER
LOG_FOLDER_PATH = SERVER_DIR / LOG_FOLDER
THIS_SCRIPT_NAME = Path(__file__).name
os.makedirs(SAVE_FOLDER_PATH, exist_ok=True)
os.makedirs(LOG_FOLDER_PATH, exist_ok=True)

# --- Regex & Constants ---
FILENAME_EXTRACT_REGEX = re.compile(r"^\s*(?://|#)\s*@@FILENAME@@\s+(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
FILENAME_SANITIZE_REGEX = re.compile(r'[^a-zA-Z0-9._\-\/]')
MAX_FILENAME_LENGTH = 200
LANGUAGE_PATTERNS = {'.py': re.compile(r'\b(def|class|import|from|if|else|elif|for|while|try|except|print)\b', re.MULTILINE), '.js': re.compile(r'\b(function|var|let|const|if|else|for|while|document|window|console\.log)\b', re.MULTILINE), '.html': re.compile(r'<(!DOCTYPE html|html|head|body|div|p|a|img|script|style)\b', re.IGNORECASE | re.MULTILINE), '.css': re.compile(r'[{};]\s*([a-zA-Z-]+)\s*:', re.MULTILINE), '.json': re.compile(r'^\s*\{.*\}\s*$|^\s*\[.*\]\s*$', re.DOTALL), '.md': re.compile(r'^#+\s|\*\*|\*|_|`|> |-', re.MULTILINE), '.sql': re.compile(r'\b(SELECT|INSERT|UPDATE|DELETE|CREATE|TABLE|FROM|WHERE|JOIN)\b', re.IGNORECASE | re.MULTILINE), '.xml': re.compile(r'<(\?xml|!DOCTYPE|[a-zA-Z:]+)', re.MULTILINE)}
DEFAULT_EXTENSION = '.txt'; AUTO_RUN_ON_SYNTAX_OK = True

# --- Helper Functions ---
def sanitize_filename(filename: str) -> str | None:
    if not filename or filename.isspace(): return None
    filename = filename.strip()
    if filename.startswith(('/', '\\')) or '..' in Path(filename).parts: print(f"W: Rejected potentially unsafe path pattern: {filename}", file=sys.stderr); return None
    basename = os.path.basename(filename)
    if basename.startswith('.'): print(f"W: Rejected path ending in hidden file: {filename}", file=sys.stderr); return None
    sanitized = FILENAME_SANITIZE_REGEX.sub('_', filename)
    if len(sanitized) > MAX_FILENAME_LENGTH:
        print(f"W: Filename too long, might be truncated unexpectedly: {sanitized}", file=sys.stderr)
        sanitized = sanitized[:MAX_FILENAME_LENGTH]
        base, ext = os.path.splitext(sanitized); original_base, original_ext = os.path.splitext(filename)
        if original_ext and not ext: sanitized = base + original_ext
    base, ext = os.path.splitext(os.path.basename(sanitized))
    if not ext or len(ext) < 2: print(f"W: Sanitized path '{sanitized}' lacks a proper extension. Appending .txt", file=sys.stderr); sanitized += ".txt"
    if not base: print(f"W: Sanitized filename part is empty: {sanitized}", file=sys.stderr); return None
    return sanitized

def detect_language_and_extension(code: str) -> tuple[str, str]:
    first_lines = code.splitlines()[:3]
    if first_lines:
        if first_lines[0].startswith('#!/usr/bin/env python') or first_lines[0].startswith('#!/usr/bin/python'): return '.py', 'Python'
        if first_lines[0].startswith('#!/bin/bash') or first_lines[0].startswith('#!/bin/sh'): return '.sh', 'Shell'
        if first_lines[0].startswith('<?php'): return '.php', 'PHP'
    if LANGUAGE_PATTERNS['.html'].search(code): return '.html', 'HTML'
    if LANGUAGE_PATTERNS['.xml'].search(code): return '.xml', 'XML'
    if LANGUAGE_PATTERNS['.json'].search(code):
         try: import json; json.loads(code); return '.json', 'JSON'
         except: pass
    if LANGUAGE_PATTERNS['.css'].search(code): return '.css', 'CSS'
    if LANGUAGE_PATTERNS['.py'].search(code): return '.py', 'Python'
    if LANGUAGE_PATTERNS['.js'].search(code): return '.js', 'JavaScript'
    if LANGUAGE_PATTERNS['.sql'].search(code): return '.sql', 'SQL'
    if LANGUAGE_PATTERNS['.md'].search(code): return '.md', 'Markdown'
    print("W: Cannot detect language. Defaulting to .txt", file=sys.stderr)
    return DEFAULT_EXTENSION, 'Text'

def generate_timestamped_filepath(extension: str = '.txt', base_prefix="code"):
    today = datetime.datetime.now().strftime("%Y%m%d"); counter = 1
    if not extension.startswith('.'): extension = '.' + extension
    safe_base_prefix = FILENAME_SANITIZE_REGEX.sub('_', base_prefix);
    if not safe_base_prefix: safe_base_prefix = "code"
    while True:
        filename = f"{safe_base_prefix}_{today}_{counter:03d}{extension}"
        filepath = SAVE_FOLDER_PATH / filename
        if not filepath.exists(): return str(filepath)
        counter += 1

def is_git_repository() -> bool:
    try:
        result = subprocess.run(['git', 'rev-parse', '--git-dir'], capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR)
        is_repo = result.returncode == 0
        if not is_repo: print("Info: Not running inside a Git repository.", file=sys.stderr)
        return is_repo
    except FileNotFoundError: print("W: 'git' command not found.", file=sys.stderr); return False
    except Exception as e: print(f"E: checking Git repository: {e}", file=sys.stderr); return False

IS_REPO = is_git_repository()

def find_tracked_file_by_name(basename_to_find: str) -> str | None:
    if not IS_REPO: return None
    try:
        command = ['git', 'ls-files']
        print(f"Running: {' '.join(command)} from {SERVER_DIR} to find matches for '*/{basename_to_find}'", file=sys.stderr)
        result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', cwd=SERVER_DIR)
        tracked_files = result.stdout.splitlines()
        matches = [f for f in tracked_files if f.endswith('/' + basename_to_find) or f == basename_to_find]
        if len(matches) == 1: print(f"Info: Found unique tracked file match: '{matches[0]}'", file=sys.stderr); return matches[0]
        elif len(matches) > 1: print(f"W: Ambiguous filename marker '{basename_to_find}'. Found multiple tracked files: {matches}. Cannot determine target.", file=sys.stderr); return None
        else: print(f"Info: No tracked file ending in '{basename_to_find}' found in Git index.", file=sys.stderr); return None
    except subprocess.CalledProcessError as e: print(f"E: 'git ls-files' failed:\n{e.stderr}", file=sys.stderr); return None
    except Exception as e: print(f"E: checking Git for file '{basename_to_find}': {e}", file=sys.stderr); return None

def is_git_tracked(filepath_relative_to_repo: str) -> bool:
    if not IS_REPO: return False
    try:
        git_path = Path(filepath_relative_to_repo).as_posix(); command = ['git', 'ls-files', '--error-unmatch', git_path]
        print(f"Running: {' '.join(command)} from {SERVER_DIR}", file=sys.stderr)
        result = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8', cwd=SERVER_DIR)
        is_tracked = result.returncode == 0
        print(f"Info: Git track status for '{git_path}': {is_tracked}", file=sys.stderr)
        if result.returncode != 0 and result.stderr: print(f"Info: git ls-files stderr: {result.stderr.strip()}", file=sys.stderr)
        return is_tracked
    except Exception as e: print(f"E: checking Git track status for '{filepath_relative_to_repo}': {e}", file=sys.stderr); return False

def update_and_commit_file(filepath_absolute: Path, code_content: str, marker_filename: str) -> bool:
    if not IS_REPO: return False
    try:
        filepath_relative_to_repo_str = str(filepath_absolute.relative_to(SERVER_DIR)); git_path_posix = filepath_absolute.re