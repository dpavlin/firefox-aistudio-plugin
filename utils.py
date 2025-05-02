import re
import os
from pathlib import Path
import datetime
import unicodedata
import json # For language patterns if needed, or move patterns here

# --- Constants ---
# Match marker ONLY at the start, after optional whitespace
FILENAME_EXTRACT_REGEX = re.compile(r"^\s*@@FILENAME@@\s+(.+?)\s*$", re.IGNORECASE)
FILENAME_SANITIZE_REGEX = re.compile(r'[^\w\.\-\/]+')
MAX_FILENAME_LENGTH = 200
LANGUAGE_PATTERNS = {
    '.py': re.compile(r'\b(def|class|import|from|if|else|elif|for|while|try|except|print)\b', re.MULTILINE),
    '.js': re.compile(r'\b(function|var|let|const|if|else|for|while|document|window|console\.l