# @@FILENAME@@ utils.py
import re
import os
from pathlib import Path
import datetime
import unicodedata
import json # For language patterns if needed, or move patterns here

# --- Constants ---
# Match marker ONLY at the start, after optional whitespace, greedy path capture
FILENAME_EXTRACT_REGEX = re.compile(r"^\s*@@FILENAME@@\s+(.+)\s*", re.IGNORECASE)
FILENAME_SANITIZE_REGEX = re.compile(r'[^\w\.\-\/]+')
MAX_FILENAME_LENGTH = 200
LANGUAGE_PATTERNS = {
    '.py': re.compile(r'\b(def|class|import|from|if|else|elif|for|while|try|except|print)\b', re.MULTILINE),
    '.js': re.compile(r'\b(function|var|let|const|if|else|for|while|document|window|console\.log)\b', re.MULTILINE),
    '.html': re.compile(r'<(!DOCTYPE html|html|head|body|div|p|a|img|script|style)\b', re.IGNORECASE | re.MULTILINE),
    '.css': re.compile(r'[{};]\s*([a-zA-Z-]+)\s*:', re.MULTILINE),
    '.json': re.compile(r'^\s*\{.*\}\s*$|^\s*\[.*\]\s*$', re.DOTALL),
    '.md': re.compile(r'^#+\s|\*\*|\*|_|`|> |-', re.MULTILINE),
    '.sql': re.compile(r'\b(SELECT|INSERT|UPDATE|DELETE|CREATE|TABLE|FROM|WHERE|JOIN)\b', re.IGNORECASE | re.MULTILINE),
    '.xml': re.compile(r'<(\?xml|!DOCTYPE|[a-zA-Z:]+)', re.MULTILINE),
    '.sh': re.compile(r'\b(echo|if|then|else|fi|for|do|done|while|case|esac|function|source|export|\$\(|\{|\})\b|^(#!\/bin\/(bash|sh))', re.MULTILINE)
}
DEFAULT_EXTENSION = '.txt'

def sanitize_filename(filename: str) -> str | None:
    """Sanitizes a filename or relative path."""
    if not filename or filename.isspace(): return None
    filename = filename.strip()
    # Reject absolute paths or paths attempting directory traversal
    if filename.startswith(('/', '\\')) or '..' in Path(filename).parts:
        # print(f"W: Rejected potentially unsafe path pattern: {filename}", file=sys.stderr) # Consider logging instead
        return None
    # Reject filenames starting with '.' (hidden files/dirs) in any part
    if any(part.startswith('.') for part in Path(filename).parts if part):
         # print(f"W: Rejected path containing hidden file/directory segment: {filename}", file=sys.stderr)
         return None

    filename = filename.replace('\\', '/')
    parts = filename.split('/')
    sanitized_parts = []
    for part in parts:
        if not part: # Handle potential empty parts from multiple slashes "//"
            continue
        # Replace disallowed characters with underscore
        sanitized_part = FILENAME_SANITIZE_REGEX.sub('_', part)
        # Remove leading/trailing underscores that might result from replacement
        sanitized_part = sanitized_part.strip('_')
        # If a part becomes empty after sanitization (e.g., "???" -> "_"), reject the whole path
        if not sanitized_part:
            # print(f"W: Path segment became empty after sanitization in '{filename}'. Rejecting.", file=sys.stderr)
            return None
        sanitized_parts.append(sanitized_part)

    if not sanitized_parts: # e.g., input was just "/" or similar
        return None

    sanitized = '/'.join(sanitized_parts)

    # Length check on the whole path
    if len(sanitized) > MAX_FILENAME_LENGTH:
        # Simple truncation for now, might need smarter logic if needed
        sanitized = sanitized[:MAX_FILENAME_LENGTH]
        # print(f"W: Sanitized path too long, truncated to: '{sanitized}'", file=sys.stderr)
        # Ensure truncation didn't leave just "." or ".." as the final component
        final_name = Path(sanitized).name
        if final_name == '.' or final_name == '..': return None


    # Ensure final component has a valid name and suffix
    final_path = Path(sanitized)
    if not final_path.name or final_path.name.startswith('.'):
         # print(f"W: Final sanitized path has empty or hidden basename: '{sanitized}'. Rejecting.", file=sys.stderr)
         return None

    # Check for extension, add default if missing or invalid (e.g., just ".")
    if not final_path.suffix or len(final_path.suffix) < 2 or final_path.suffix == '.':
        # print(f"W: Sanitized path '{sanitized}' lacks proper extension. Appending {DEFAULT_EXTENSION}", file=sys.stderr)
        sanitized += DEFAULT_EXTENSION

    return sanitized


def detect_language_and_extension(code: str) -> tuple[str, str]:
    """Detects language and returns (extension, language_name)."""
    first_lines = code.splitlines()[:3]
    if first_lines:
        first_line = first_lines[0].strip()
        if first_line.startswith('#!/usr/bin/env python') or first_line.startswith('#!/usr/bin/python'): return '.py', 'Python'
        if first_line.startswith('#!/bin/bash') or first_line.startswith('#!/bin/sh'): return '.sh', 'Shell'
        if first_line.startswith('<?php'): return '.php', 'PHP'
    if LANGUAGE_PATTERNS['.html'].search(code): return '.html', 'HTML'
    if LANGUAGE_PATTERNS['.xml'].search(code): return '.xml', 'XML'
    if LANGUAGE_PATTERNS['.json'].search(code):
         try:
             json.loads(code) # Use standard json library
             return '.json', 'JSON'
         except json.JSONDecodeError: pass
    if LANGUAGE_PATTERNS['.css'].search(code): return '.css', 'CSS'
    if LANGUAGE_PATTERNS['.py'].search(code): return '.py', 'Python'
    if LANGUAGE_PATTERNS['.sh'].search(code): return '.sh', 'Shell'
    if LANGUAGE_PATTERNS['.js'].search(code): return '.js', 'JavaScript'
    if LANGUAGE_PATTERNS['.sql'].search(code): return '.sql', 'SQL'
    if LANGUAGE_PATTERNS['.md'].search(code): return '.md', 'Markdown'
    # print("W: Cannot detect language. Defaulting to .txt", file=sys.stderr) # Less verbose logging
    return DEFAULT_EXTENSION, 'Text'

def generate_timestamped_filepath(save_folder_path: Path, extension: str = '.txt', base_prefix="code") -> str:
    """Generates a unique timestamped filepath in the specified save folder."""
    today = datetime.datetime.now().strftime("%Y%m%d")
    counter = 1
    if not extension.startswith('.'): extension = '.' + extension
    safe_base_prefix = re.sub(r'[^a-zA-Z0-9_\-]', '_', base_prefix).strip('_')
    if not safe_base_prefix: safe_base_prefix = "code"
    while True:
        filename = f"{safe_base_prefix}_{today}_{counter:03d}{extension}"
        filepath = save_folder_path / filename # Use passed path
        if not filepath.exists():
            return str(filepath.resolve())
        counter += 1
        if counter > 999:
             # print(f"W: Could not find unique filename for prefix '{safe_base_prefix}' after 999 attempts. Adding timestamp.", file=sys.stderr)
             fallback_filename = f"{safe_base_prefix}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{extension}"
             return str((save_folder_path / fallback_filename).resolve())
