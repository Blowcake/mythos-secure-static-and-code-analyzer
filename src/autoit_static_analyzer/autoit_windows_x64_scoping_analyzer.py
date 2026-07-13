"""@file autoit_scoping_analyzer.py
@brief Command-line analyzer for AutoIt include preprocessing, scope diagnostics, and report generation.
@details Part of AutoIt_Static_Analyzer. This header is intentionally concise so Doxygen output and future code reviews expose the module boundary before implementation details.
@author Harald Frank
@copyright Copyright (c) 2026 Harald Frank. All rights reserved.
"""
import argparse
from functools import lru_cache
import os
import re
import sys
import urllib.parse

__version__ = "1.2.0"

# Default AutoIt standard include directory
AUTOIT_STD_INCLUDE = r"C:\Program Files (x86)\AutoIt3\Include"
PROJECT_MARKER_FILES = ('.git', 'project.json', 'pyproject.toml', 'setup.py', 'requirements.txt')
AUTOIT_ANSI_ENCODING = 'cp1252'
ERROR_DIAGNOSTIC_TYPES = {
    'Undeclared Variable',
    'Block Scoping Bug',
    'Reference Before Declaration',
    'Source Read Error',
}


class AutoItSourceError(Exception):
    """Raised when an AutoIt source file cannot be decoded without data loss."""


def read_autoit_source(file_path):
    """Read an AutoIt source file according to its BOM or the Windows ANSI fallback.

    AutoIt treats BOM-less scripts as ANSI.  UTF-8 and UTF-16 are Unicode source
    formats only when their BOM is present.  Decoding is deliberately strict: a
    source file must never be changed silently merely to let analysis continue.
    """
    try:
        with open(file_path, 'rb') as source_file:
            raw = source_file.read()
    except OSError as exc:
        raise AutoItSourceError(f"could not read source file: {exc}") from exc

    try:
        if raw.startswith(b'\x00\x00\xfe\xff') or raw.startswith(b'\xff\xfe\x00\x00'):
            raise AutoItSourceError("UTF-32 AutoIt source is not supported")
        if raw.startswith(b'\xef\xbb\xbf'):
            text = raw.decode('utf-8-sig', errors='strict')
        elif raw.startswith(b'\xff\xfe'):
            text = raw[2:].decode('utf-16-le', errors='strict')
        elif raw.startswith(b'\xfe\xff'):
            text = raw[2:].decode('utf-16-be', errors='strict')
        else:
            text = raw.decode(AUTOIT_ANSI_ENCODING, errors='strict')
    except UnicodeError as exc:
        raise AutoItSourceError(f"source decoding failed: {exc}") from exc

    if '\x00' in text:
        raise AutoItSourceError("source contains NUL characters after decoding; missing or unsupported BOM")
    return text


def read_autoit_lines(file_path, keepends=False):
    """Return decoded AutoIt source as lines using the central source policy."""
    return read_autoit_source(file_path).splitlines(keepends=keepends)


@lru_cache(maxsize=131072)
def leading_keyword(text):
    """Return the lowercase identifier at the start of an AutoIt statement."""
    stripped = text.lstrip()
    end = 0
    while end < len(stripped) and (stripped[end].isalnum() or stripped[end] == '_'):
        end += 1
    return stripped[:end].lower()


def starts_with_keyword(text, keyword):
    """Return whether text starts with an AutoIt keyword at a word boundary."""
    return leading_keyword(text) == keyword

def add_unique_path(paths, path):
    """
    @brief Adds a unique directory path to the provided paths list, resolving it to an absolute path.
    @param paths List of existing absolute paths.
    @param path Directory path to add.
    """
    if not path:
        return
    abs_path = os.path.abspath(path)
    if not os.path.isdir(abs_path):
        return
    abs_lower = abs_path.lower()
    if abs_lower in {p.lower() for p in paths}:
        return
    paths.append(abs_path)

def find_project_root(start_dir):
    """
    @brief Traverses up the directory tree to find the root directory of the project.
    @details Searches for project marker files like .git or project.json to determine the project root.
    @param start_dir Directory to start searching from.
    @return Absolute path to the detected project root, or the start directory if not found.
    """
    current = os.path.abspath(start_dir)
    fallback = current
    while True:
        if any(os.path.exists(os.path.join(current, marker)) for marker in PROJECT_MARKER_FILES):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return fallback
        fallback = current
        current = parent

def discover_include_dirs(main_file):
    """
    @brief Discovers directory paths containing AutoIt include files recursively up to the project root.
    @param main_file Path to the main AutoIt entry script.
    @return List of discovered absolute include directories.
    """
    main_dir = os.path.dirname(os.path.abspath(main_file))
    project_root = find_project_root(main_dir)
    include_dirs = []

    # Prefer include folders closest to the entry file.
    current = main_dir
    while True:
        for name in ('Include', 'Includes', 'inc'):
            add_unique_path(include_dirs, os.path.join(current, name))
        if current.lower() == project_root.lower():
            break
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent

    # Then add project-wide include folders, e.g. sibling SDK Include directories.
    max_depth = 6
    root_depth = project_root.rstrip("\\/").count(os.sep)
    for root, dirs, _ in os.walk(project_root):
        depth = root.rstrip("\\/").count(os.sep) - root_depth
        if depth >= max_depth:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d.lower() not in ('.git', '.svn', '.hg', 'node_modules', '.venv', 'venv', '__pycache__')]
        if os.path.basename(root).lower() in ('include', 'includes', 'inc'):
            add_unique_path(include_dirs, root)

    return include_dirs

@lru_cache(maxsize=131072)
def split_code_comment(line):
    """
    @brief Splits a line of code into the code statement and any trailing comment.
    @details Ensures that comment characters (;) found inside string literals are ignored.
    @param line The raw line of AutoIt code.
    @return A tuple of (code_part, comment_part).
    """
    in_single = False
    in_double = False
    i = 0
    while i < len(line):
        ch = line[i]
        if in_double:
            if ch == '"':
                if i + 1 < len(line) and line[i + 1] == '"':
                    i += 2
                    continue
                in_double = False
        elif in_single:
            if ch == "'":
                if i + 1 < len(line) and line[i + 1] == "'":
                    i += 2
                    continue
                in_single = False
        else:
            if ch == '"':
                in_double = True
            elif ch == "'":
                in_single = True
            elif ch == ';':
                return line[:i], line[i:]
        i += 1
    return line, ''

@lru_cache(maxsize=131072)
def strip_strings(code_part):
    """
    @brief Strips all string literals (single and double quoted) from a code snippet.
    @param code_part The raw code string.
    @return The string without any quoted content.
    """
    result = []
    in_single = False
    in_double = False
    i = 0
    while i < len(code_part):
        ch = code_part[i]
        if in_double:
            if ch == '"':
                if i + 1 < len(code_part) and code_part[i + 1] == '"':
                    i += 2
                    continue
                in_double = False
            i += 1
            continue
        if in_single:
            if ch == "'":
                if i + 1 < len(code_part) and code_part[i + 1] == "'":
                    i += 2
                    continue
                in_single = False
            i += 1
            continue
        if ch == '"':
            in_double = True
        elif ch == "'":
            in_single = True
        else:
            result.append(ch)
        i += 1
    return ''.join(result)


def normalize_simple_case_token(expr):
    """Normalize a simple Switch Case literal using AutoIt's comparisons."""
    expr = split_code_comment(expr)[0].strip()
    variable = re.match(r'^\s*(\$\w+)\s*$', expr)
    if variable:
        return ('var', variable.group(1).lower())
    if re.match(r'(?i)^[-+]?(?:0x[0-9a-f]+|\d+(?:\.\d+)?)$', expr):
        return ('num', expr.lower())
    string_value = re.match(r'^(["\'])(.*)\1$', expr)
    if string_value:
        return ('str', string_value.group(2).lower())
    return None

def replace_strings_with_placeholder(code_part):
    """
    @brief Replaces all string literals with placeholder characters of the same length to avoid regex confusion.
    @param code_part The raw code string.
    @return String with quoted content replaced by a placeholder digit.
    """
    result = []
    in_single = False
    in_double = False
    i = 0
    while i < len(code_part):
        ch = code_part[i]
        if in_double:
            if ch == '"':
                if i + 1 < len(code_part) and code_part[i + 1] == '"':
                    result.append('1')
                    result.append('1')
                    i += 2
                    continue
                in_double = False
            result.append('1')
            i += 1
            continue
        if in_single:
            if ch == "'":
                if i + 1 < len(code_part) and code_part[i + 1] == "'":
                    result.append('1')
                    result.append('1')
                    i += 2
                    continue
                in_single = False
            result.append('1')
            i += 1
            continue
        if ch == '"':
            in_double = True
            result.append('1')
        elif ch == "'":
            in_single = True
            result.append('1')
        else:
            result.append(ch)
        i += 1
    return ''.join(result)

@lru_cache(maxsize=131072)
def _split_top_level_cached(text, separator):
    """
    @brief Splits a string by a separator only at the top level of nesting.
    @details Respects parenthesis and bracket nesting depths, as well as string literals.
    @param text The text to split.
    @param separator The character separator to split on (e.g. ',' or '=').
    @return An immutable tuple of split substrings for safe cache reuse.
    """
    parts = []
    current = []
    paren_depth = 0
    bracket_depth = 0
    in_single = False
    in_double = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_double:
            current.append(ch)
            if ch == '"':
                if i + 1 < len(text) and text[i + 1] == '"':
                    current.append(text[i + 1])
                    i += 2
                    continue
                in_double = False
        elif in_single:
            current.append(ch)
            if ch == "'":
                if i + 1 < len(text) and text[i + 1] == "'":
                    current.append(text[i + 1])
                    i += 2
                    continue
                in_single = False
        else:
            if ch == '"':
                in_double = True
                current.append(ch)
            elif ch == "'":
                in_single = True
                current.append(ch)
            elif ch == '(':
                paren_depth += 1
                current.append(ch)
            elif ch == ')':
                paren_depth = max(0, paren_depth - 1)
                current.append(ch)
            elif ch == '[':
                bracket_depth += 1
                current.append(ch)
            elif ch == ']':
                bracket_depth = max(0, bracket_depth - 1)
                current.append(ch)
            elif ch == separator and paren_depth == 0 and bracket_depth == 0:
                parts.append(''.join(current))
                current = []
            else:
                current.append(ch)
        i += 1
    if current:
        parts.append(''.join(current))
    return tuple(parts)


def split_top_level(text, separator):
    """Split at top-level separators while preserving the historic list API."""
    return list(_split_top_level_cached(text, separator))

def split_assignment_left(text):
    """
    @brief Splits an assignment statement and returns the left-hand side.
    @param text The assignment statement.
    @return The left-hand side part.
    """
    return split_top_level(text, '=')[0]

def declaration_has_const(prefix_text):
    """
    @brief Checks if a declaration prefix contains the 'Const' keyword.
    @param prefix_text The variable declaration prefix.
    @return True if 'Const' is found, False otherwise.
    """
    code_part = split_code_comment(prefix_text)[0]
    return re.search(r'(?i)(?:^|\s)Const(?:\s|$)', strip_strings(code_part)) is not None

def is_std_include_path(file_path):
    """
    @brief Checks if a file path points to the standard AutoIt Include library.
    @param file_path The path to verify.
    @return True if the file resides in the standard Include folder.
    """
    std_include_abs = os.path.abspath(AUTOIT_STD_INCLUDE).lower() + os.sep.lower()
    file_abs = os.path.abspath(file_path).lower()
    return file_abs.startswith(std_include_abs)

def is_numeric_literal(expr):
    """
    @brief Validates if an expression matches an integer or hexadecimal literal.
    @param expr The expression string.
    @return True if the expression is a numeric literal.
    """
    expr = expr.strip()
    return re.match(r'(?i)^[-+]?(?:0x[0-9a-f]+|\d+)$', expr) is not None

def levenshtein_distance(s1, s2):
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]

def register_global_var(global_vars, var_lower, is_const, dims):
    """
    @brief Registers or updates a variable in the global scoping registry.
    @param global_vars Dictionary storing known global variables.
    @param var_lower Lowercase name of the variable.
    @param is_const Boolean indicating if the variable is defined as a Const.
    @param dims Dimensions of the array, or empty if scalar.
    """
    if var_lower not in global_vars:
        global_vars[var_lower] = (is_const, dims)
        return

    old_const, old_dims = global_vars[var_lower]
    merged_const = old_const or is_const
    if old_dims == dims:
        global_vars[var_lower] = (merged_const, old_dims)
        return

    dims_list = old_dims if isinstance(old_dims, list) else [old_dims]
    if dims not in dims_list:
        dims_list.append(dims)
    global_vars[var_lower] = (merged_const, dims_list)

def get_clickable_link(file_path, line_num):
    """
    @brief Formats an absolute file path and line number into a clickable Markdown link.
    @param file_path The path to the file.
    @param line_num The line number.
    @return Clickable Markdown link string.
    """
    abs_path = os.path.abspath(file_path).replace("\\", "/")
    url_path = urllib.parse.quote(abs_path)
    return f"[{os.path.basename(file_path)}:{line_num}](file:///{abs_path}#L{line_num})"

def read_source_line(file_path, line_num):
    """
    @brief Reads a specific line using the central AutoIt source encoding policy.
    @param file_path File path to read from.
    @param line_num 1-based index of the line to retrieve.
    @return The raw line content, or an empty string on failure.
    """
    try:
        for idx, src_line in enumerate(read_autoit_lines(file_path), start=1):
            if idx == line_num:
                return src_line
    except AutoItSourceError:
        return ""
    return ""

def estimate_warning_col(warning):
    """
    @brief Estimates the column number for a scoping warning based on variable match locations.
    @param warning Dictionary of warning metadata.
    @return The estimated 1-based column position.
    """
    if warning.get('col'):
        return warning['col']
    source_line = read_source_line(warning['file'], warning['line'])
    var_name = str(warning.get('var', ''))
    if var_name and var_name not in ('@error', '@extended'):
        idx = source_line.lower().find(var_name.lower())
        if idx >= 0:
            return idx + len(var_name)
    code_part = split_code_comment(source_line)[0].rstrip()
    return max(1, len(code_part) if code_part else 1)

def estimate_au3check_legacy_col(warning):
    """
    @brief Estimates the column index to align with legacy Au3Check diagnostics formats.
    @param warning Dictionary of warning metadata.
    @return Column number for the compiler-style diagnostic caret.
    """
    w_type = warning.get('type', '')
    source_line = read_source_line(warning['file'], warning['line'])
    if w_type == 'Duplicate Include':
        quote_idx = source_line.find('"')
        angle_idx = source_line.find('<')
        candidates = [idx for idx in (quote_idx, angle_idx) if idx >= 0]
        if candidates:
            return min(candidates) + 1
    if w_type == 'Missing Comments End':
        return 1
    if w_type == 'Local In Global Scope':
        return len('Local ') + 1
    return max(1, len(source_line) + 1)

def au3check_legacy_var_name(warning):
    """
    @brief Extracts the case-preserved variable name from the source line.
    @param warning The warning containing the variable name reference.
    @return Case-preserved name, or original name if not found.
    """
    var_name = str(warning.get('var', ''))
    if not var_name:
        return var_name
    source_line = read_source_line(warning['file'], warning['line'])
    match = re.search(re.escape(var_name), source_line, re.IGNORECASE)
    if match:
        return source_line[match.start():match.end()]
    return var_name

def au3check_legacy_desc(warning):
    """
    @brief Maps modern warning types to the equivalent legacy Au3Check compiler descriptions.
    @param warning The scoping warning dict.
    @return Description string suitable for compiler pane outputs.
    """
    w_type = warning.get('type', '')
    var_name = au3check_legacy_var_name(warning)
    if w_type == 'Duplicate Include':
        return warning['desc']
    if w_type == 'Missing Comments End':
        return "#comments-start has no explicit closing #comments-end (1 level)."
    if w_type == 'Local In Global Scope':
        return "'Local' specifier in global scope."
    if w_type == 'Duplicate Declaration':
        return f"{var_name} already declared/assigned"
    if w_type == 'Deprecated Dim Use':
        return "'Dim' deprecated as declaration. Prefer to use Local or Global."
    if w_type == 'Unused Variable':
        return f"{var_name}: declared, but not used in func."
    return warning['desc']

def au3check_legacy_sort_key(warning):
    """
    @brief Generates sorting keys to group diagnostics similarly to legacy compiler order.
    @param warning The diagnostic dictionary.
    @return Tuple sorting key.
    """
    order = {
        'Duplicate Declaration': 10,
        'Deprecated Dim Use': 20,
        'Unused Variable': 30,
    }
    return (order.get(warning.get('type', ''), 100), warning.get('line', 0), warning.get('var', ''))

def au3check_legacy_source_line(warning):
    """
    @brief Sanitizes or extracts the source line to print under compiler warnings.
    @param warning Scoping warning dictionary.
    @return Cleaned source code line.
    """
    source_line = read_source_line(warning['file'], warning['line'])
    if warning.get('type') == 'Local In Global Scope':
        m = re.match(r'(?i)^(\s*Local\s+\$\w+)', source_line)
        if m:
            return m.group(1)
    return source_line

def format_au3check_diagnostic(warning, level, display_path=None):
    """
    @brief Formats a warning dict into the standard three-line compiler-pane diagnostic output block.
    @param warning Dictionary of warning metadata.
    @param level String level ('warning' or 'error').
    @param display_path Optional relative file path to display in compiler logs.
    @return List of output lines representing the formatted diagnostic.
    """
    file_path = display_path or warning['file']
    line = warning['line']
    col = estimate_au3check_legacy_col(warning)
    desc = au3check_legacy_desc(warning)
    if warning.get('type') == 'Missing Comments End':
        return [f'"{file_path}"({line},{col}) : {level}: {desc}']
    source_line = au3check_legacy_source_line(warning)
    marker = ("~" * max(col - 1, 0)) + "^"
    return [
        f'"{file_path}"({line},{col}) : {level}: {desc}',
        source_line,
        marker,
    ]

class AutoItPreprocessor:
    """
    @brief Preprocessor for AutoIt source code files.
    @details Handles include file resolution, duplicate include checks, comment block validations, and continuation line merging.
    """
    def __init__(self, include_dirs=None):
        """
        @brief Initializes the AutoItPreprocessor.
        @param include_dirs Optional list of user-defined directories to search for includes.
        """
        self.include_dirs = include_dirs or []
        self.processed_files = set()
        self.raw_lines = []
        self.line_mappings = [] # list of (file_path, original_line_num)
        self.all_included_files = set()
        self.include_events = []
        self.warnings = []
        self.warnings_config = {}

    def preprocess(self, file_path, parent_file=None, parent_line=None):
        """
        @brief Recursively processes a file, resolving `#include` statements.
        @details Checks for duplicate includes (warning 1) and unterminated comment blocks (warning 2).
        @param file_path Path of the file to preprocess.
        @param parent_file Path of the parent file that included this file.
        @param parent_line Line number of the include statement in the parent file.
        """
        abs_path = os.path.abspath(file_path)
        
        # Check if already included (warning 1)
        if abs_path.lower() in self.all_included_files:
            if abs_path.lower() not in self.processed_files:
                if parent_file and self.warnings_config.get(1, True):
                    self.warnings.append({
                        'func': '<global>',
                        'var': os.path.basename(abs_path),
                        'type': 'Duplicate Include',
                        'desc': f"already included file: {abs_path}",
                        'file': parent_file,
                        'line': parent_line
                    })
            return

        self.all_included_files.add(abs_path.lower())

        if abs_path.lower() in self.processed_files:
            return

        try:
            lines = read_autoit_lines(abs_path, keepends=True)
        except AutoItSourceError as e:
            self.warnings.append({
                'func': '<global>',
                'var': '',
                'type': 'Source Read Error',
                'desc': f"Cannot analyze source file '{abs_path}': {e}",
                'file': abs_path,
                'line': 1,
            })
            return

        has_include_once = False
        for line in lines:
            if re.match(r'(?i)^\s*#include-once', line.strip()):
                has_include_once = True
                break

        if has_include_once:
            self.processed_files.add(abs_path.lower())

        current_dir = os.path.dirname(abs_path)
        include_rx = re.compile(r'(?i)^\s*#include\s+["<]([^">]+)[">]')

        in_comment_block = False
        comment_block_start_line = None

        for i, line in enumerate(lines):
            line_num = i + 1
            stripped = line.strip()
            stripped_lower = stripped.lower()
            
            # Check comment block boundaries
            if in_comment_block:
                if stripped_lower == '#comments-end' or stripped_lower == '#ce':
                    in_comment_block = False
                continue
            else:
                if stripped_lower == '#comments-start' or stripped_lower == '#cs':
                    in_comment_block = True
                    comment_block_start_line = line_num
                    continue

            # Standard processing
            m_inc = include_rx.match(stripped)
            if m_inc:
                inc_name = m_inc.group(1)
                is_user_include = re.match(r'(?i)^\s*#include\s+"', stripped) is not None
                resolved_path = self.resolve_include(inc_name, current_dir, is_user_include)
                if resolved_path:
                    self.include_events.append((abs_path, line_num, os.path.abspath(resolved_path)))
                    self.preprocess(resolved_path, abs_path, line_num)
                else:
                    self.raw_lines.append(line)
                    self.line_mappings.append((abs_path, line_num))
            else:
                self.raw_lines.append(line)
                self.line_mappings.append((abs_path, line_num))
                
        # Warning 2: missing #comments-end
        if in_comment_block and self.warnings_config.get(2, True):
            self.warnings.append({
                'func': '<global>',
                'var': '#comments-end',
                'type': 'Missing Comments End',
                'desc': "missing #comments-end.",
                'file': abs_path,
                'line': comment_block_start_line
            })

    def resolve_include(self, name, current_dir, is_user_include):
        """
        @brief Resolves an include name to an absolute file path.
        @details Searches relative path, user directories, and standard library directories.
        @param name Filename to resolve.
        @param current_dir Directory of the invoking source file.
        @param is_user_include True if using double quotes, False if using angle brackets.
        @return Absolute path to include file, or None if unresolved.
        """
        # 1. Try relative path if user include
        if is_user_include:
            p = os.path.join(current_dir, name)
            if os.path.exists(p):
                return p

        # 2. Search custom user include folders
        for d in self.include_dirs:
            p = os.path.join(d, name)
            if os.path.exists(p):
                return p

        # 3. Search standard AutoIt include folder
        p = os.path.join(AUTOIT_STD_INCLUDE, name)
        if os.path.exists(p):
            return p

        # 4. Fallback search relative path
        p = os.path.join(current_dir, name)
        if os.path.exists(p):
            return p

        return None

    def merge_continuations(self):
        """
        @brief Merges line continuations (lines ending with '_') into logical single lines.
        @return Tuple of (merged_lines, merged_mappings).
        """
        merged_lines = []
        merged_mappings = []
        
        i = 0
        while i < len(self.raw_lines):
            line = self.raw_lines[i]
            mapping = self.line_mappings[i]
            
            # Extract code and comment
            code_part, comment = split_code_comment(line)
            code = code_part.rstrip()
            
            while code.endswith('_') and (i + 1) < len(self.raw_lines):
                # Remove the trailing underscore from code
                code = code[:-1].rstrip()
                
                i += 1
                next_line = self.raw_lines[i]
                next_code_part, next_comment = split_code_comment(next_line)
                next_code = next_code_part.strip()
                
                # Append next code to current code
                code = (code + ' ' + next_code).rstrip()
                # If there's a comment in the next line, we can append it
                if next_comment:
                    comment = comment.rstrip() + ' ' + next_comment
            
            # Reconstruct the line
            merged_line = code
            if comment:
                merged_line += ' ' + comment
            if not merged_line.endswith('\n'):
                merged_line += '\n'
                
            merged_lines.append(merged_line)
            merged_mappings.append(mapping)
            i += 1
            
        return merged_lines, merged_mappings


class AutoItScopingAnalyzer:
    """
    @brief Static scoping analyzer for AutoIt codebases.
    @details Validates variable scopes, duplicate declarations, local/global usage, unreferenced symbols, and experimental checks.
    """
    EXPERIMENTAL_WARNING_TYPES = {
        'Unchecked SetError Return',
        'Overwritten @extended Check',
        'Suspicious UBound Dimension',
        'ReDim Dimension Change',
        'Unchecked Array Result Index',
        'Unchecked Map Key',
        'Unsafe Object Dereference',
        'DllCall Return Index Mismatch',
        'Handle Leak on Return',
        'Nested Loop Variable Reuse',
        'Unreachable Code',
        'Potential Uninitialized Use',
        'Implicit Empty String Use',
        'Enum Value Collision',
        'Potential Numeric Coercion',
        'Array Used as Boolean',
        'Duplicate Case Value',
        'Dead Store',
    }

    def __init__(self, experimental_checks=False, warnings_config=None, system_dead_stores=False):
        """
        @brief Initializes the AutoItScopingAnalyzer.
        @param experimental_checks True to enable experimental analysis checks.
        @param warnings_config Dict of warning IDs to boolean enablement flags.
        @param system_dead_stores True to report dead stores on system variables.
        """
        self.decl_rx = re.compile(r'(?i)^\s*(Static\s+)?(Global|Local|Dim|Static)\s+(?:Const\s+)?(.+)')
        self.var_ref_rx = re.compile(r'\$\w+')
        self.func_signature_rx = re.compile(r'(?i)^\s*Func\s+(\w+)\s*\(')
        self.warnings = []
        self.seterror_return_funcs = set()
        self.seterror_value_passthrough_funcs = set()
        self.setextended_return_funcs = set()
        self.byref_param_positions = {}
        self.function_return_constants = {}
        self.experimental_checks = experimental_checks
        self.system_dead_stores = system_dead_stores
        if warnings_config is None:
            warnings_config = {
                1: True, # already included file
                2: True, # missing #comments-end
                3: False, # already declared var
                4: False, # local var used in global scope
                5: False, # local var declared but not used
                6: False, # warn when using Dim
                7: False, # warn when passing Const or expression on ByRef param
            }
        self.warnings_config = warnings_config

    @lru_cache(maxsize=131072)
    def parse_func_signature(self, line):
        """
        @brief Parses a function declaration line and extracts parameters.
        @param line The line containing the Func declaration.
        @return Tuple of (function_name, parameter_string), or None if not a Func.
        """
        if not starts_with_keyword(line, 'func'):
            return None
        m = self.func_signature_rx.match(line)
        if not m:
            return None
        open_pos = line.find('(', m.end() - 1)
        if open_pos < 0:
            return None
        depth = 0
        in_single = False
        in_double = False
        for idx in range(open_pos, len(line)):
            ch = line[idx]
            if in_double:
                if ch == '"':
                    if idx + 1 < len(line) and line[idx + 1] == '"':
                        continue
                    in_double = False
                continue
            if in_single:
                if ch == "'":
                    if idx + 1 < len(line) and line[idx + 1] == "'":
                        continue
                    in_single = False
                continue
            if ch == '"':
                in_double = True
                continue
            if ch == "'":
                in_single = True
                continue
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    return m.group(1), line[open_pos + 1:idx]
        return None

    def is_multiline_if(self, line):
        """
        @brief Checks if a line initiates a multiline If-Then statement.
        @param line The preprocessed line of code.
        @return True if it is a multiline If statement, False otherwise.
        """
        code = split_code_comment(line)[0].strip()
        if not code.lower().startswith('if'):
            return False
        return code.lower().endswith(' then')

    def split_declaration_parts(self, vars_part):
        """
        @brief Splits declaration variables separated by commas.
        @param vars_part The string snippet of declared variables.
        @return List of variable declaration substrings.
        """
        return split_top_level(vars_part, ',')

    def parse_array_dimensions(self, decl_str):
        """
        @brief Parses a variable name and its array dimensions from a declaration statement.
        @param decl_str The variable declaration snippet (e.g. '$var[10][20]').
        @return Tuple of (lowercase_var_name, dimensions) where dimensions is a tuple of sizes or "scalar".
        """
        m = re.match(r'^\s*(\$\w+)', decl_str)
        if not m:
            return None, "scalar"
        var_name = m.group(1).lower()
        rest = decl_str[len(var_name):].strip()
        
        if not rest.startswith('['):
            return var_name, "scalar"
            
        dims = []
        i = 0
        while i < len(rest) and rest[i] == '[':
            depth = 0
            j = i
            dim_content = []
            while j < len(rest):
                if rest[j] == '[':
                    depth += 1
                elif rest[j] == ']':
                    depth -= 1
                    if depth == 0:
                        break
                if depth > 0 and j > i:
                    dim_content.append(rest[j])
                j += 1
            if depth == 0:
                content_str = ''.join(dim_content).strip()
                if content_str.isdigit():
                    dims.append(int(content_str))
                else:
                    dims.append(None)
                i = j + 1
                while i < len(rest) and rest[i].isspace():
                    i += 1
            else:
                break
                
        if not dims:
            return var_name, "scalar"
        return var_name, tuple(dims)

    def register_declaration(self, declarations, var_lower, ln, block_range, is_const, dims, guards=()):
        """
        @brief Registers a variable declaration in the analyzer's mapping.
        @param declarations Dictionary mapping variable names to declaration scopes.
        @param var_lower Lowercase name of the variable.
        @param ln Preprocessed line number of the declaration.
        @param block_range The block start/end line bounds of the defining block.
        @param is_const True if variable is Const.
        @param dims Dimensions tuple or "scalar".
        @param guards Conditional guards active at declaration.
        """
        if var_lower not in declarations:
            declarations[var_lower] = []
        declarations[var_lower].append((ln, block_range, is_const, dims, tuple(guards)))

    def promote_full_if_else_declarations(self, declarations, if_block, ln):
        """
        @brief Promotes variables declared in ALL branches of an If-Else block to parent scope.
        @details Prevents false-positives for variables that are guaranteed to be declared regardless of path.
        @param declarations The variables declaration mapping.
        @param if_block The active multi-branch If block metadata.
        @param ln Line number to register the promoted declaration.
        """
        sub_blocks = if_block[2]
        has_else = any(len(block) > 2 and block[2] == 'else' for block in sub_blocks)
        if not has_else or len(sub_blocks) < 2:
            return

        declared_per_branch = []
        for sub_block in sub_blocks:
            branch_vars = set()
            start_b, end_b = sub_block[0], sub_block[1]
            if end_b is None:
                continue
            for var, decls in declarations.items():
                if any(d[1] is sub_block or (d[1] and d[1][0] == start_b and d[1][1] == end_b) for d in decls):
                    branch_vars.add(var)
            declared_per_branch.append(branch_vars)

        if len(declared_per_branch) != len(sub_blocks):
            return

        common_vars = set.intersection(*declared_per_branch) if declared_per_branch else set()
        for var in common_vars:
            branch_decls = []
            for decl in declarations[var]:
                if decl[1] in sub_blocks:
                    branch_decls.append(decl)
            for _, _, is_const, dims, guards in branch_decls:
                self.register_declaration(declarations, var, ln, None, is_const, dims, guards)

    def promote_loop_declarations(self, declarations, loop_block, ln):
        """
        @brief Promotes declarations inside a loop block to the parent function scope.
        @param declarations The variable declarations registry.
        @param loop_block The active loop block bounds.
        @param ln Line number of the promotion event.
        """
        start_b, end_b = loop_block
        for var, decls in list(declarations.items()):
            for _, block_range, is_const, dims, guards in decls:
                if block_range is loop_block or (block_range and block_range[0] == start_b and block_range[1] == end_b):
                    self.register_declaration(declarations, var, ln, None, is_const, dims, guards)

    def strip_strings(self, code_part):
        """
        @brief Wrapper helper to strip strings.
        @param code_part The input code string.
        @return Code string stripped of string literals.
        """
        return strip_strings(code_part)

    def analyze_function(self, func_name, func_params, func_start_line, func_lines, line_mappings, global_vars, global_numeric_consts=None):
        """
        @brief Analyzes a single AutoIt function definition for variable scope and static diagnostic issues.
        @details Scans declarations, variable references, branch coverage, dead stores, and experimental diagnostics.
        @param func_name The name of the function.
        @param func_params The raw parameter string from the function signature.
        @param func_start_line The preprocessed line number where the function begins.
        @param func_lines List of preprocessed code lines representing the function body.
        @param line_mappings Map of preprocessed line numbers back to original file and line coordinates.
        @param global_vars The dict of registered global variables.
        @param global_numeric_consts Optional set of global constants holding numeric values.
        @author Harald Frank
        """
        # Stack stores active blocks: ('if'|'switch'|'loop', start_line, [[sub_start, sub_end], ...])
        stack = []
        declarations = {} # var_name -> [(preprocessed_line_num, block_range, is_const, dims, guards)]
        references = [] # (preprocessed_line_num, var_name, original_text, guards)
        global_numeric_consts = global_numeric_consts or set()

        # Unsafe dereference checks initializers
        unsafe_assigns = {}
        object_assigns = {}
        unchecked_array_results = {}
        unchecked_seterror_results = {}
        dllcall_result_sizes = {}
        ubound_aliases = {}
        maybe_uninitialized = set()
        uninit_candidates = set()
        warned_uninitialized = set()
        guarded_assignments = {}
        boolean_guarded_assignments = {}
        conditional_initializers = {}
        assignment_events = []
        map_vars = set()
        map_known_keys = {}
        file_handles = {}
        array_value_sources = {}
        value_set_vars = {}
        status_dependency_vars = {}
        branch_polymorphic_array_dims = {}
        loop_vars = []
        unreachable_after = None
        warned_unreachable = False
        pending_error_var = None
        com_error_handler_active = False
        type_check_rx = re.compile(r'(?i)is(?:array|obj|map)\s*\(\s*(\$\w+)\s*\)')
        deref_rx = re.compile(r'(\$\w+)(?:\[|\.\w+)')
        func_call_rx = re.compile(r'\b(?:[a-zA-Z_]\w*\.)*([a-zA-Z_]\w*)\s*\(')

        # @error overwrite tracking initializers
        primary_call = None
        intervening_calls = []
        lines_since_primary_call = None
        primary_extended_call = None
        extended_intervening_calls = []
        UTILITY_FUNCS = {'ubound', 'stringlen', 'isarray', 'isobj', 'ismap', 'vargettype', 'consolewrite', 'stringreplace', 'log', 'abs', 'round', 'int', 'number', 'string', '_log', '_debugout', '_logmessage', '_msgbox', 'msgbox'}
        ERROR_STATUS_PRIMARY_FUNCS = {'dllcall', 'dllcalladdress'}
        EXTENDED_STATUS_PRIMARY_FUNCS = {'filefindnextfile', 'stringreplace'}
        KNOWN_ARRAY_FUNCS = {'_aoauth_crackurl', '_budget_createdefaultconfig', '_budget_createdefaultstate', '_budget_loadconfig', '_budget_loadstate', '_crypto_generatepkce', '_date_time_dosdatetoarray', '_date_time_dosdatetimetoarray', '_date_time_dostimetoarray', '_date_time_gettimezoneinformation', '_date_time_systemtimetoarray', '_daysinmonth', '_gcli_auth_generatepkce', '_json_parse', '_mapkeys', '_provider_readconfigmap', '_session_buildcontextfingerprint', '_session_create', '_winapi_getsysteminfo', '_winapi_structtoarray', '_winhttpcrackurl', '_winhttpsimpleformfill_setuploadcallback', 'filereadtoarray', 'guigetmsg', 'mapkeys', 'mousegetpos', 'processlist', 'stringtoasciiarray', 'stringregexp', 'stringsplit', 'wingetpos', 'wingetclientsize', 'controlgetpos', 'dllcall', 'dllcalladdress'}
        KNOWN_MAP_FUNCS = {'_json_parse'}
        KNOWN_ARRAY_DIMS = {'processlist': (None, None)}
        KNOWN_OBJECT_FUNCS = {'objcreate'}
        KNOWN_STRUCT_FUNCS = {'dllstructcreate'}

        # Inject function parameters as function-level declarations (parameters are not constants)
        param_vars = set()
        byref_param_vars = set()
        if func_params:
            for param_part in split_top_level(func_params, ','):
                param_match = re.search(r'(\$\w+)', param_part)
                if not param_match:
                    continue
                var_lower = param_match.group(1).lower()
                param_vars.add(var_lower)
                if re.search(r'(?i)\bByRef\b', param_part):
                    byref_param_vars.add(var_lower)
                self.register_declaration(declarations, var_lower, func_start_line, None, False, None, ())

        def get_current_block_range(ln):
            if not stack:
                return None
            top = stack[-1]
            if top[0] in ('if', 'switch'):
                sub_blocks = top[2]
                if sub_blocks:
                    return sub_blocks[-1]
            if top[0] == 'select':
                sub_blocks = top[2]
                if sub_blocks:
                    return sub_blocks[-1]
            elif top[0] == 'loop':
                return top[2]
            return None

        def normalize_guard(line_text):
            code = split_code_comment(line_text)[0].strip()
            m = re.match(r'(?i)^If\s+(.+?)\s+Then(?:\s.*)?$', code)
            if not m:
                return None
            condition = self.strip_strings(m.group(1)).strip().lower()
            condition = re.sub(r'\s+', ' ', condition)
            return condition or None

        def raw_if_condition(line_text):
            code = split_code_comment(line_text)[0].strip()
            m = re.match(r'(?i)^If\s+(.+?)\s+Then(?:\s.*)?$', code)
            if not m:
                return None
            condition = m.group(1).strip().lower()
            condition = re.sub(r'\s+', ' ', condition)
            return condition or None

        def get_current_guards():
            guards = []
            for item in stack:
                if item[0] == 'if' and len(item) > 3 and item[3]:
                    guards.append(item[3])
            return tuple(guards)

        def get_current_raw_guards():
            guards = []
            for item in stack:
                if item[0] == 'if' and len(item) > 4 and item[4]:
                    guards.append(item[4])
            return tuple(guards)

        def is_handle_failure_return(handle_var):
            handle_rx = re.escape(handle_var)
            handle_failure_expr = rf'{handle_rx}\s*(?:={{1,2}}\s*-1\b|<\s*0\b|<=\s*-1\b)'
            if re.match(rf'(?i)^\s*If\b.*{handle_failure_expr}.*\bThen\b.*\bReturn\b', code_no_strings):
                return True
            if re.match(r'(?i)^\s*If\b.*@error\b.*\bThen\b.*\bReturn\b', code_no_strings):
                opened_ln = file_handles.get(handle_var)
                return opened_ln is not None and ln == opened_ln + 1
            return any(
                re.search(rf'(?i){handle_failure_expr}', guard)
                or ('@error' in guard and file_handles.get(handle_var) is not None and ln <= file_handles[handle_var] + 3)
                for guard in get_current_guards()
            )

        def mark_branch_assignment(var_lower):
            if not stack:
                return
            top = stack[-1]
            if top[0] not in ('if', 'switch', 'select'):
                return
            sub_blocks = top[2]
            if not sub_blocks:
                return
            sub_block = sub_blocks[-1]
            if len(sub_block) < 4:
                sub_block.append(set())
            sub_block[3].add(var_lower)

        def mark_current_branch_terminal():
            for item in reversed(stack):
                if item[0] not in ('if', 'switch', 'select'):
                    continue
                sub_blocks = item[2]
                if not sub_blocks:
                    continue
                sub_block = sub_blocks[-1]
                if len(sub_block) < 4:
                    sub_block.append(set())
                if len(sub_block) < 5:
                    sub_block.append(False)
                sub_block[4] = True
                return

        def mark_loop_assignment(var_lower):
            for item in reversed(stack):
                if item[0] != 'loop':
                    continue
                if len(item) < 4:
                    item.append(set())
                item[3].add(var_lower)
                return

        def current_branch_assigns(var_lower):
            for item in reversed(stack):
                if item[0] not in ('if', 'switch', 'select'):
                    continue
                sub_blocks = item[2]
                if not sub_blocks:
                    continue
                sub_block = sub_blocks[-1]
                if len(sub_block) > 3 and var_lower in sub_block[3]:
                    return True
            return False

        def current_loop_assigns(var_lower):
            for item in reversed(stack):
                if item[0] == 'loop' and len(item) > 3 and var_lower in item[3]:
                    return True
            return False

        def in_branch_inside_nearest_loop():
            for item in reversed(stack):
                if item[0] in ('if', 'switch', 'select'):
                    return True
                if item[0] == 'loop':
                    return False
            return False

        def boolean_guard_polarities(condition):
            polarities = set()
            if not condition:
                return polarities
            for part in re.split(r'(?i)\s+or\s+', condition):
                part = part.strip().lower()
                m_not = re.match(r'(?i)^not\s+(\$\w+)$', part)
                if m_not:
                    polarities.add((m_not.group(1).lower(), 'not'))
                    continue
                m_var = re.match(r'^(\$\w+)$', part)
                if m_var:
                    polarities.add((m_var.group(1).lower(), 'pos'))
            return polarities

        def record_boolean_guarded_assignment(var_lower, condition):
            for guard_var, polarity in boolean_guard_polarities(condition):
                key = (var_lower, guard_var)
                seen = boolean_guarded_assignments.setdefault(key, set())
                seen.add(polarity)
                if {'pos', 'not'}.issubset(seen):
                    maybe_uninitialized.discard(var_lower)
                    uninit_candidates.discard(var_lower)

        def record_assignment_effect(var_lower, ln):
            in_branch_context = any(item[0] in ('if', 'switch', 'select') for item in stack)
            in_choice_context = any(item[0] == 'select' for item in stack)
            in_loop_context = any(item[0] == 'loop' for item in stack)
            if var_lower not in uninit_candidates:
                return
            current_raw_guards = get_current_raw_guards()
            if current_raw_guards:
                record_boolean_guarded_assignment(var_lower, current_raw_guards[-1])
            if get_current_block_range(ln) is None and not in_branch_context:
                maybe_uninitialized.discard(var_lower)
                uninit_candidates.discard(var_lower)
            else:
                if in_choice_context:
                    maybe_uninitialized.add(var_lower)
                mark_branch_assignment(var_lower)
                if in_loop_context and not in_branch_inside_nearest_loop():
                    mark_loop_assignment(var_lower)

        def record_assignment_event(var_lower, ln, kind='assignment'):
            assignment_events.append((ln, var_lower, kind))

        def latest_visible_dims(var_lower, ln):
            if var_lower in declarations:
                visible = [
                    d for d in declarations[var_lower]
                    if d[0] <= ln and declaration_visible(d, ln, get_current_guards())
                ]
                if visible:
                    return max(visible, key=lambda d: d[0])[3]
            if var_lower in global_vars:
                return global_vars[var_lower][1]
            return None

        def scalar_assignment_dims(rhs_text):
            rhs = rhs_text.strip()
            if not rhs:
                return None
            if re.match(r'(?i)^(?:-?\d+(?:\.\d+)?|".*"|\'.*\'|true|false|default)$', rhs):
                return "scalar"
            if re.match(r'(?i)^\$\w+\s*\[[^\]]+\]\s*$', rhs):
                return "scalar"
            if re.match(r'(?i)^(?:number|string|int|binary|ptr|hwnd)\s*\(', rhs):
                return "scalar"
            return None

        def record_scalar_assignment_type(var_lower, ln, rhs_text):
            dims = scalar_assignment_dims(rhs_text)
            if dims is None:
                return
            if var_lower in declarations:
                self.register_declaration(declarations, var_lower, ln, get_current_block_range(ln), False, dims, get_current_guards())
            elif var_lower in global_vars:
                register_global_var(global_vars, var_lower, global_vars[var_lower][0], dims)

        def record_accumulator_initialization(var_lower):
            if var_lower in uninit_candidates:
                maybe_uninitialized.discard(var_lower)
                uninit_candidates.discard(var_lower)

        def is_self_concat_initializer(var_lower, assign_op, rhs_text):
            if assign_op == '&=':
                return True
            if assign_op != '=':
                return False
            return re.match(rf'(?i)^\s*{re.escape(var_lower)}\s*&', rhs_text) is not None

        def strip_self_accumulator_read(var_lower, assign_op, rhs_text):
            if assign_op == '&=':
                return rhs_text
            return re.sub(rf'(?i)^\s*{re.escape(var_lower)}\s*&\s*', '', rhs_text, count=1)

        def lhs_index_expressions(lhs_text):
            return re.findall(r'\[([^\]]+)\]', lhs_text)

        def is_string_concat_default_use(var_lower, code_text):
            if not var_lower.startswith('$s'):
                return False
            var_rx = re.escape(var_lower)
            return re.search(rf'(?i)(?:&\s*{var_rx}\b|{var_rx}\b\s*&)', code_text) is not None

        def simple_var_expr(expr):
            m = re.match(r'^\s*(\$\w+)\s*$', expr)
            return m.group(1).lower() if m else None

        def simple_case_token(expr):
            return normalize_simple_case_token(expr)

        def function_returns_array(func_lower, call_args):
            if func_lower != 'stringregexp':
                return func_lower in KNOWN_ARRAY_FUNCS
            flag_text = call_args[2].strip() if len(call_args) >= 3 else '0'
            if flag_text.lower() in {
                '$str_regexparraymatch',
                '$str_regexparrayfullmatch',
                '$str_regexparrayglobalmatch',
                '$str_regexparrayglobalfullmatch',
            }:
                return True
            if not re.match(r'^[-+]?\d+$', flag_text):
                return False
            return int(flag_text, 10) in (1, 2, 3, 4)

        def declaration_path_terminates(decl):
            block_range = decl[1]
            return bool(block_range and len(block_range) > 4 and block_range[4])

        def collect_clause_references(clause_text, clause_ln, original_line):
            clause_code = self.strip_strings(split_code_comment(clause_text)[0])
            for clause_var in self.var_ref_rx.findall(clause_code):
                references.append((clause_ln, clause_var.lower(), original_line, get_current_guards()))

        def apply_inline_terminal_postcondition(line_text):
            match = re.match(r'(?i)^\s*If\s+(Not\s+)?(\$\w+)\s+Then\s+(?:Return|Exit)\b', split_code_comment(line_text)[0])
            if not match:
                return
            guard_var = match.group(2).lower()
            surviving_polarity = 'pos' if match.group(1) else 'not'
            for initialized_var, guards in conditional_initializers.items():
                if (guard_var, surviving_polarity) in guards:
                    maybe_uninitialized.discard(initialized_var)
                    uninit_candidates.discard(initialized_var)

        def record_value_set_assignment(var_lower, rhs_text, conditional=False):
            rhs_match = re.match(r'^\s*(\$\w+)\s*$', rhs_text)
            is_uppercase_const = bool(rhs_match and rhs_match.group(1)[1:].isupper())
            rhs_var = simple_var_expr(rhs_text)
            if not rhs_var or is_uppercase_const:
                value_set_vars.pop(var_lower, None)
                return
            if conditional:
                value_set_vars.setdefault(var_lower, set()).add(rhs_var)
            else:
                value_set_vars[var_lower] = {rhs_var}

        def switch_expr_var(block):
            return block[3] if len(block) > 3 else None

        def switch_case_values(block):
            return block[4] if len(block) > 4 else {}

        def current_switch_case_tokens():
            for item in reversed(stack):
                if item[0] != 'switch' or len(item) < 6:
                    continue
                return item[5]
            return set()

        def current_switch_status_var():
            for item in reversed(stack):
                if item[0] == 'switch':
                    return switch_expr_var(item)
            return None

        def current_status_dependency_allows(var_lower):
            status_var = current_switch_status_var()
            if not status_var:
                return False
            deps_by_case = status_dependency_vars.get(status_var, {})
            for case_token in current_switch_case_tokens():
                if var_lower in deps_by_case.get(case_token, set()):
                    return True
            return False

        def in_else_branch():
            for item in reversed(stack):
                if item[0] != 'if':
                    continue
                sub_blocks = item[2]
                if sub_blocks and len(sub_blocks[-1]) > 2 and sub_blocks[-1][2] == 'else':
                    return True
            return False

        def extract_call_args(text, call_match):
            open_pos = text.find('(', call_match.start())
            if open_pos < 0:
                return []
            depth = 0
            in_single = False
            in_double = False
            chars = []
            i = open_pos
            while i < len(text):
                ch = text[i]
                if in_double:
                    if ch == '"':
                        if i + 1 < len(text) and text[i + 1] == '"':
                            chars.append(ch)
                            chars.append(text[i + 1])
                            i += 2
                            continue
                        in_double = False
                    if depth > 0 and i > open_pos:
                        chars.append(ch)
                elif in_single:
                    if ch == "'":
                        if i + 1 < len(text) and text[i + 1] == "'":
                            chars.append(ch)
                            chars.append(text[i + 1])
                            i += 2
                            continue
                        in_single = False
                    if depth > 0 and i > open_pos:
                        chars.append(ch)
                else:
                    if ch == '"':
                        in_double = True
                        if depth > 0 and i > open_pos:
                            chars.append(ch)
                    elif ch == "'":
                        in_single = True
                        if depth > 0 and i > open_pos:
                            chars.append(ch)
                    elif ch == '(':
                        depth += 1
                        if depth > 1:
                            chars.append(ch)
                    elif ch == ')':
                        depth -= 1
                        if depth == 0:
                            break
                        chars.append(ch)
                    elif depth > 0 and i > open_pos:
                        chars.append(ch)
                i += 1
            return split_top_level(''.join(chars), ',') if chars else []

        def parse_string_equality_disjuncts(condition):
            if not condition:
                return None, set()
            var_name = None
            values = set()
            for part in re.split(r'(?i)\s+or\s+', condition):
                m_eq = re.match(r'(?i)^\s*(\$\w+)\s*={1,2}\s*(["\'])(.*?)\2\s*$', part)
                if not m_eq:
                    return None, set()
                part_var = m_eq.group(1).lower()
                if var_name is None:
                    var_name = part_var
                elif var_name != part_var:
                    return None, set()
                values.add(m_eq.group(3).lower())
            return var_name, values

        def record_guarded_assignment(var_lower, condition):
            current_raw_guards = get_current_raw_guards()
            if not current_raw_guards:
                return
            guard_var, guard_values = parse_string_equality_disjuncts(current_raw_guards[-1])
            cond_var, cond_values = parse_string_equality_disjuncts(condition)
            if not guard_var or guard_var != cond_var or len(cond_values) != 1:
                return
            key = (var_lower, current_raw_guards[-1])
            assigned_values = guarded_assignments.setdefault(key, set())
            assigned_values.update(cond_values)
            if guard_values and guard_values.issubset(assigned_values):
                maybe_uninitialized.discard(var_lower)
                uninit_candidates.discard(var_lower)

        def is_seterror_payload_failure_guard(var_lower, line_text):
            code = split_code_comment(line_text)[0]
            var_rx = re.escape(var_lower)
            return re.search(
                rf'(?i)^\s*If\b.*{var_rx}.*(?:={1,2}|<>|<=|>=|<|>).*?\bThen\s+(?:Return|Exit)\b',
                code
            ) is not None

        def discard_fully_assigned_branch_vars(block):
            sub_blocks = block[2]
            has_default = False
            if block[0] == 'if':
                has_default = any(len(sub_block) > 2 and sub_block[2] == 'else' for sub_block in sub_blocks)
            elif block[0] in ('switch', 'select'):
                has_default = any(len(sub_block) > 2 and sub_block[2] == 'else' for sub_block in sub_blocks)
            if not has_default or len(sub_blocks) < 2:
                return
            live_sub_blocks = [sub_block for sub_block in sub_blocks if not (len(sub_block) > 4 and sub_block[4])]
            if not live_sub_blocks:
                return
            assigned_per_branch = [sub_block[3] if len(sub_block) > 3 else set() for sub_block in live_sub_blocks]
            if not assigned_per_branch:
                return
            for assigned_var in set.intersection(*assigned_per_branch):
                if any(item[0] in ('if', 'switch', 'select') for item in stack):
                    mark_branch_assignment(assigned_var)
                else:
                    maybe_uninitialized.discard(assigned_var)
                    uninit_candidates.discard(assigned_var)

        def discard_value_set_switch_assigned_vars(block):
            if block[0] != 'switch':
                return
            expr_var = switch_expr_var(block)
            if not expr_var or expr_var not in value_set_vars:
                return
            expected_values = value_set_vars[expr_var]
            case_values = switch_case_values(block)
            if len(expected_values) < 2 or not expected_values.issubset(set(case_values)):
                return
            assigned_sets = []
            for expected in expected_values:
                sub_block = case_values.get(expected)
                if not sub_block:
                    return
                assigned_sets.append(sub_block[3] if len(sub_block) > 3 else set())
            if not assigned_sets:
                return
            for assigned_var in set.intersection(*assigned_sets):
                if any(item[0] in ('if', 'switch', 'select') for item in stack):
                    mark_branch_assignment(assigned_var)
                else:
                    maybe_uninitialized.discard(assigned_var)
                    uninit_candidates.discard(assigned_var)

        def mark_incomplete_value_set_switch_vars(block):
            if block[0] != 'switch':
                return
            expr_var = switch_expr_var(block)
            if not expr_var or expr_var not in value_set_vars:
                return
            expected_values = value_set_vars[expr_var]
            case_values = switch_case_values(block)
            if len(expected_values) < 2 or expected_values.issubset(set(case_values)):
                return
            assigned_vars = set()
            for sub_block in block[2]:
                if len(sub_block) > 3:
                    assigned_vars.update(sub_block[3])
            for assigned_var in assigned_vars:
                if assigned_var in uninit_candidates:
                    maybe_uninitialized.add(assigned_var)

        def record_branch_polymorphic_array_dims(block):
            if block[0] != 'if':
                return
            sub_blocks = block[2]
            has_else = any(len(sub_block) > 2 and sub_block[2] == 'else' for sub_block in sub_blocks)
            if not has_else or len(sub_blocks) < 2:
                return
            dims_by_var = {}
            branches_by_var = {}
            for sub_block in sub_blocks:
                start_b, end_b = sub_block[0], sub_block[1]
                if end_b is None:
                    continue
                for var, decls in declarations.items():
                    for decl in decls:
                        block_range = decl[1]
                        dims = decl[3]
                        if not isinstance(dims, tuple):
                            continue
                        if block_range is sub_block or (block_range and block_range[0] == start_b and block_range[1] == end_b):
                            dims_by_var.setdefault(var, set()).add(len(dims))
                            branches_by_var.setdefault(var, set()).add(start_b)
            for var, dim_counts in dims_by_var.items():
                if len(dim_counts) > 1 and len(branches_by_var.get(var, set())) == len(sub_blocks):
                    branch_polymorphic_array_dims.setdefault(var, set()).update(dim_counts)

        def record_sibling_branch_array_dim(var_lower, dims, current_range):
            if not isinstance(dims, tuple) or current_range is None:
                return
            for item in reversed(stack):
                if item[0] != 'if' or current_range not in item[2]:
                    continue
                sibling_ranges = [sub_block for sub_block in item[2] if sub_block is not current_range]
                for decl in declarations.get(var_lower, []):
                    block_range = decl[1]
                    old_dims = decl[3]
                    if block_range in sibling_ranges and isinstance(old_dims, tuple) and len(old_dims) != len(dims):
                        branch_polymorphic_array_dims.setdefault(var_lower, set()).update({len(old_dims), len(dims)})
                return

        def declaration_visible(decl, ref_ln, ref_guards):
            decl_ln, block_range, _, _, decl_guards = decl
            if ref_ln < decl_ln:
                return False
            if block_range is None:
                return True
            start_b, end_b = block_range[0], block_range[1]
            if end_b is None or (start_b <= ref_ln <= end_b):
                return True
            return any(guard in ref_guards for guard in decl_guards)

        def add_warning(warn_type, var_name, desc, ln, details=None):
            if warn_type in self.EXPERIMENTAL_WARNING_TYPES and not self.experimental_checks:
                return
            orig_file, orig_ln = line_mappings[ln - 1]
            w = {
                'func': func_name,
                'var': var_name,
                'type': warn_type,
                'desc': desc,
                'file': orig_file,
                'line': orig_ln
            }
            if details is not None:
                w['details'] = details
            self.warnings.append(w)

        in_block_comment = False

        for ln, line in func_lines:
            stripped = line.strip()
            stripped_lower = stripped.lower()
            if re.match(r'(?i)^\s*#(?:comments-start|cs)\b', stripped):
                in_block_comment = True
                continue
            if re.match(r'(?i)^\s*#(?:comments-end|ce)\b', stripped):
                in_block_comment = False
                continue
            if in_block_comment:
                continue
            if not stripped or stripped.startswith(';') or (stripped.startswith('#') and not stripped_lower.startswith('#forceref')):
                continue

            # --- UNSAFE DEREFERENCE & TYPE VERIFICATION CHECKS ---
            code_part = split_code_comment(line)[0]
            code_no_strings = self.strip_strings(code_part)
            reference_code_parts = [code_part]
            assignment_lhs_vars = set()
            in_error_guard_path = '@error' in code_no_strings.lower() or any('@error' in guard for guard in get_current_guards())

            apply_inline_terminal_postcondition(stripped)

            if unreachable_after and not warned_unreachable and not stripped_lower.startswith('#forceref'):
                add_warning(
                    'Unreachable Code',
                    '',
                    f"Code at line {ln} is unreachable because a previous Return/Exit statement at line {unreachable_after} leaves the current block.",
                    ln
                )
                warned_unreachable = True

            if re.search(r'(?i)\bReturn\b', code_no_strings):
                for handle_var in list(file_handles):
                    if is_handle_failure_return(handle_var):
                        continue
                    add_warning(
                        'Handle Leak on Return',
                        handle_var,
                        f"Handle '{handle_var}' opened by FileOpen at line {file_handles[handle_var]} can leave function '{func_name}' through Return at line {ln} without FileClose.",
                        ln
                    )
                    del file_handles[handle_var]

            m_return_exit = re.match(r'(?i)^\s*(Return|Exit|ExitLoop|ContinueLoop)\b', stripped)
            if m_return_exit and get_current_block_range(ln) is None:
                unreachable_after = ln
            elif m_return_exit and m_return_exit.group(1).lower() in ('return', 'exit'):
                mark_current_branch_terminal()
            
            # 1. Type checks (e.g. IsArray($var)) satisfy type safety
            for var in type_check_rx.findall(code_no_strings):
                var_lower = var.lower()
                if var_lower in unsafe_assigns:
                    del unsafe_assigns[var_lower]
                    if pending_error_var == var_lower:
                        pending_error_var = None
                    if var_lower not in global_vars:
                        self.register_declaration(declarations, var_lower, ln, None, False, (None,), get_current_guards())
                if var_lower in object_assigns:
                    del object_assigns[var_lower]
                unchecked_array_results.pop(var_lower, None)

            for var in re.findall(r'(?i)\b_?MapExists\s*\(\s*(\$\w+)\s*,', code_part):
                map_known_keys.setdefault(var.lower(), set()).add('*')
            for var in re.findall(r'(?i)UBound\s*\(\s*(\$\w+)', code_part):
                unchecked_array_results.pop(var.lower(), None)
            if re.search(r'(?i)\bObjEvent\s*\(\s*["\']AutoIt\.Error["\']\s*,', code_part):
                com_error_handler_active = True
                        
            # 2. @error validation checks satisfy type safety
            if "@error" in code_no_strings.lower():
                # Check for overwritten error check warning
                if primary_call and intervening_calls and lines_since_primary_call is not None and lines_since_primary_call <= 1:
                    orig_file, orig_ln = line_mappings[ln - 1]
                    overwriter_ln, overwriter_func = intervening_calls[-1]
                    primary_ln, primary_name = primary_call
                    self.warnings.append({
                        'func': func_name,
                        'var': '@error',
                        'type': 'Overwritten @error Check',
                        'desc': f"The @error check at line {ln} (original: {os.path.basename(orig_file)}:{orig_ln}) is checking the status of the intervening call '{overwriter_func}' (line {overwriter_ln}) rather than the intended primary call '{primary_name}' (line {primary_ln}).",
                        'file': orig_file,
                        'line': orig_ln
                    })
                
                # Clear tracking variables on @error check
                primary_call = None
                intervening_calls = []
                lines_since_primary_call = None

                if pending_error_var and pending_error_var in unsafe_assigns:
                    del unsafe_assigns[pending_error_var]
                pending_error_var = None
                object_assigns.clear()
                unchecked_seterror_results.clear()
                unchecked_array_results.clear()

            if "@extended" in code_no_strings.lower():
                if primary_extended_call and extended_intervening_calls:
                    overwriter_ln, overwriter_func = extended_intervening_calls[-1]
                    primary_ln, primary_name = primary_extended_call
                    if overwriter_func.lower() != primary_name.lower():
                        add_warning(
                            'Overwritten @extended Check',
                            '@extended',
                            f"The @extended check at line {ln} is checking the status of intervening call '{overwriter_func}' (line {overwriter_ln}) rather than the intended primary call '{primary_name}' (line {primary_ln}).",
                            ln
                        )
                primary_extended_call = None
                extended_intervening_calls = []
                
            # 3. Track assignment of function call results
            decl_stripped = re.sub(r'(?i)^\s*(Local|Global|Dim|Static)\s+(?:Const\s+)?', '', stripped)
            m_func_assign = re.match(r'^(\$\w+)\s*=\s*(?:[a-zA-Z_]\w*\.)*([a-zA-Z_]\w*)\(', decl_stripped)
            if m_func_assign:
                var_lower = m_func_assign.group(1).lower()
                func_name_called = m_func_assign.group(2)
                func_lower = func_name_called.lower()

                rhs_start = decl_stripped.find('=') + 1
                rhs_text = decl_stripped[rhs_start:].strip() if rhs_start > 0 else ''
                args_text = rhs_text[rhs_text.find('(') + 1:rhs_text.rfind(')')] if '(' in rhs_text and ')' in rhs_text else ''
                call_args = split_top_level(args_text, ',') if args_text else []
                
                if func_lower not in ('isarray', 'isobj', 'ismap') and func_lower not in KNOWN_OBJECT_FUNCS and func_lower not in KNOWN_STRUCT_FUNCS:
                    unsafe_assigns[var_lower] = (ln, func_name_called)
                    pending_error_var = var_lower

                if func_lower in self.seterror_return_funcs and func_lower not in self.seterror_value_passthrough_funcs:
                    unchecked_seterror_results[var_lower] = (ln, func_name_called)
                    
                returns_array = function_returns_array(func_lower, call_args)
                if returns_array:
                    # Register variables receiving known array results as safe 1D arrays
                    known_dims = KNOWN_ARRAY_DIMS.get(func_lower, (None,))
                    if var_lower in global_vars:
                        register_global_var(global_vars, var_lower, global_vars[var_lower][0], known_dims)
                    else:
                        self.register_declaration(declarations, var_lower, ln, None, False, known_dims, get_current_guards())
                    # Clear from unsafe assignments
                    if var_lower in unsafe_assigns:
                        del unsafe_assigns[var_lower]
                    if pending_error_var == var_lower:
                        pending_error_var = None
                elif func_lower in KNOWN_OBJECT_FUNCS:
                    object_assigns[var_lower] = (ln, func_name_called)
                    if var_lower in unsafe_assigns:
                        del unsafe_assigns[var_lower]
                    if pending_error_var == var_lower:
                        pending_error_var = None
                elif func_lower in KNOWN_STRUCT_FUNCS:
                    if var_lower in unsafe_assigns:
                        del unsafe_assigns[var_lower]
                    if pending_error_var == var_lower:
                        pending_error_var = None

                if func_lower in ERROR_STATUS_PRIMARY_FUNCS:
                    primary_call = (ln, func_name_called)
                    intervening_calls = []
                    lines_since_primary_call = 0
                    if func_lower == 'dllcall':
                        max_index = max(0, (len(call_args) - 3) // 2)
                        dllcall_result_sizes[var_lower] = (ln, max_index)

                if func_lower in EXTENDED_STATUS_PRIMARY_FUNCS or func_lower in self.seterror_return_funcs or func_lower in self.setextended_return_funcs:
                    primary_extended_call = (ln, func_name_called)
                    extended_intervening_calls = []

                if func_lower == 'stringsplit' or (func_lower == 'stringregexp' and returns_array):
                    unchecked_array_results[var_lower] = (ln, func_name_called)

                if returns_array:
                    array_value_sources[var_lower] = func_lower

                if func_lower == 'ubound' and call_args:
                    source_var = re.match(r'\s*(\$\w+)\s*$', call_args[0])
                    if source_var and len(call_args) == 1:
                        ubound_aliases[var_lower] = source_var.group(1).lower()

                if func_lower == 'fileopen':
                    file_handles[var_lower] = ln

            # Track function calls for @error checks
            calls = func_call_rx.findall(code_no_strings)
            has_real_call = False
            for c_name in calls:
                c_lower = c_name.lower()
                if c_lower in ('isarray', 'isobj', 'ismap'):
                    continue
                has_real_call = True
                if not in_error_guard_path:
                    if (
                        primary_extended_call
                        and primary_extended_call[0] != ln
                        and c_lower not in EXTENDED_STATUS_PRIMARY_FUNCS
                        and c_lower not in self.seterror_return_funcs
                        and c_lower not in self.setextended_return_funcs
                    ):
                        extended_intervening_calls.append((ln, c_name))
                    if (
                        primary_extended_call
                        and primary_extended_call[0] != ln
                        and (c_lower in EXTENDED_STATUS_PRIMARY_FUNCS or c_lower in self.seterror_return_funcs or c_lower in self.setextended_return_funcs)
                    ):
                        primary_extended_call = (ln, c_name)
                        extended_intervening_calls = []
                if c_lower in UTILITY_FUNCS:
                    if primary_call and primary_call[0] != ln:
                        intervening_calls.append((ln, c_name))
                else:
                    if primary_call and primary_call[0] != ln:
                        intervening_calls.append((ln, c_name))
            if has_real_call:
                # Do not clear pending_error_var if it was just assigned on this line
                if not (m_func_assign and var_lower == pending_error_var):
                    pending_error_var = None

            if primary_call and primary_call[0] != ln and "@error" not in code_no_strings.lower():
                if lines_since_primary_call is None:
                    lines_since_primary_call = 0
                lines_since_primary_call += 1

            # 4. Detect unsafe dereferencing
            deref_scan_code = type_check_rx.sub('', code_no_strings)
            for var in deref_rx.findall(deref_scan_code):
                var_lower = var.lower()
                if var_lower in object_assigns:
                    func_called = object_assigns[var_lower][1]
                    if not (com_error_handler_active and func_called.lower() == 'objcreate'):
                        add_warning(
                            'Unsafe Object Dereference',
                            var_lower,
                            f"Variable '{var_lower}' is dereferenced as an object inside function '{func_name}' without IsObj or @error validation after being assigned by '{func_called}'.",
                            ln
                        )
                    del object_assigns[var_lower]
                if var_lower in unsafe_assigns:
                    orig_file, orig_ln = line_mappings[ln - 1]
                    func_called = unsafe_assigns[var_lower][1]
                    self.warnings.append({
                        'func': func_name,
                        'var': var_lower,
                        'type': 'Unsafe Return Dereference',
                        'desc': f"Variable '{var_lower}' is accessed as an array or object inside function '{func_name}' at line {ln} (original: {os.path.basename(orig_file)}:{orig_ln}) without type-checking or @error validation after being assigned by '{func_called}'.",
                        'file': orig_file,
                        'line': orig_ln
                    })
                    del unsafe_assigns[var_lower] # Warn once per variable in the function

            for m_map_read in re.finditer(r'(\$\w+)\s*\[\s*(["\'])(.*?)\2\s*\]', code_part):
                tail = code_part[m_map_read.end():]
                if re.match(r'\s*(?:\+|-|\*|/|&)?=', tail):
                    continue
                map_var = m_map_read.group(1).lower()
                key = m_map_read.group(3).lower()
                if map_var in map_vars and key not in map_known_keys.get(map_var, set()) and '*' not in map_known_keys.get(map_var, set()):
                    add_warning(
                        'Unchecked Map Key',
                        map_var,
                        f"Map key '{key}' is read from '{map_var}' without a visible MapExists/default guard.",
                        ln
                    )

            for m_bit in re.finditer(r'(?i)\b(BitAND|BitOR|BitXOR|BitShift)\s*\((.*?)\)', code_part):
                for arg in split_top_level(m_bit.group(2), ','):
                    m_arg_var = re.match(r'\s*(\$\w+)\s*$', arg)
                    if m_arg_var:
                        arg_var = m_arg_var.group(1).lower()
                        if 'flag' in arg_var or 'mask' in arg_var or 'bit' in arg_var:
                            continue
                        if re.match(r'^\$(?:str|se|fo|fd|ubound|array|regexp|obj|gui|ws|ss|es|lv|wm|tag)_', arg_var):
                            continue
                        if arg_var in global_numeric_consts:
                            continue
                        if arg_var.startswith('$s') or 'text' in arg_var or 'string' in arg_var:
                            add_warning(
                                'Potential Numeric Coercion',
                                arg_var,
                                f"Variable '{arg_var}' is passed to {m_bit.group(1)} where AutoIt may silently coerce non-numeric strings.",
                                ln
                            )
                            break

            m_bool_array = re.match(r'(?i)^\s*If\s+(\$\w+)\s+Then\b', code_no_strings)
            if m_bool_array:
                bool_var = m_bool_array.group(1).lower()
                is_array_like = isinstance(latest_visible_dims(bool_var, ln), tuple)
                if is_array_like and array_value_sources.get(bool_var) not in ('dllcall', 'dllcalladdress'):
                    add_warning(
                        'Array Used as Boolean',
                        bool_var,
                        f"Array variable '{bool_var}' is used directly as a Boolean condition inside function '{func_name}'.",
                        ln
                    )

            # End block checks
            if stripped_lower.startswith('endif'):
                if stack and stack[-1][0] == 'if':
                    top = stack.pop()
                    top[2][-1][1] = ln
                    record_branch_polymorphic_array_dims(top)
                    self.promote_full_if_else_declarations(declarations, top, ln)
                    discard_fully_assigned_branch_vars(top)
                continue

            if stripped_lower.startswith('endswitch'):
                if stack and stack[-1][0] == 'switch':
                    top = stack.pop()
                    if top[2]:
                        top[2][-1][1] = ln
                    mark_incomplete_value_set_switch_vars(top)
                    discard_value_set_switch_assigned_vars(top)
                    discard_fully_assigned_branch_vars(top)
                continue

            if stripped_lower.startswith('endselect'):
                if stack and stack[-1][0] == 'select':
                    top = stack.pop()
                    if top[2]:
                        top[2][-1][1] = ln
                    discard_fully_assigned_branch_vars(top)
                continue

            if stripped_lower.startswith('next') or stripped_lower.startswith('wend') or stripped_lower.startswith('until'):
                if stripped_lower.startswith('until'):
                    collect_clause_references(re.sub(r'(?i)^\s*Until\b', '', stripped), ln, line)
                if stack and stack[-1][0] == 'loop':
                    top = stack.pop()
                    top[2][1] = ln
                    self.promote_loop_declarations(declarations, top[2], ln)
                    if loop_vars:
                        loop_vars.pop()
                continue

            # ElseIf / Else
            m_elseif = re.match(r'(?i)^\s*(elseif\s|else\b)', stripped)
            if m_elseif:
                if stripped_lower.startswith('elseif'):
                    elseif_condition = re.sub(r'(?i)^\s*ElseIf\s+', '', split_code_comment(stripped)[0])
                    elseif_condition = re.sub(r'(?i)\s+Then\s*$', '', elseif_condition)
                    collect_clause_references(elseif_condition, ln, line)
                if stack and stack[-1][0] == 'if':
                    sub_blocks = stack[-1][2]
                    if sub_blocks:
                        sub_blocks[-1][1] = ln - 1
                    kind = 'else' if re.match(r'(?i)^\s*else\b', stripped) else 'elseif'
                    sub_blocks.append([ln, None, kind, set()])
                continue

            # Case
            if stripped_lower.startswith('case ') or stripped_lower == 'case':
                case_reference_text = re.sub(r'(?i)^\s*Case\s+', '', split_code_comment(stripped)[0])
                if not re.match(r'(?i)^\s*Else\b', case_reference_text):
                    collect_clause_references(case_reference_text, ln, line)
                if stack and stack[-1][0] in ('switch', 'select'):
                    sub_blocks = stack[-1][2]
                    if sub_blocks:
                        sub_blocks[-1][1] = ln - 1
                    kind = 'else' if re.match(r'(?i)^\s*case\s+else\b', stripped) else 'case'
                    sub_block = [ln, None, kind, set()]
                    sub_blocks.append(sub_block)
                    if stack[-1][0] == 'switch' and kind == 'case' and len(stack[-1]) > 4:
                        case_text = re.sub(r'(?i)^\s*case\s+', '', split_code_comment(stripped)[0]).strip()
                        case_tokens = set()
                        clause_literal_tokens = set()
                        new_case_tokens = []
                        for case_part in split_top_level(case_text, ','):
                            case_var = simple_var_expr(case_part)
                            if case_var:
                                stack[-1][4][case_var] = sub_block
                                case_tokens.add(case_var)
                            token = simple_case_token(case_part)
                            if token and len(stack[-1]) > 6:
                                seen_cases = stack[-1][6]
                                if token in clause_literal_tokens:
                                    continue
                                clause_literal_tokens.add(token)
                                if token in seen_cases and self.experimental_checks:
                                    orig_file, orig_ln = line_mappings[ln - 1]
                                    first_ln = seen_cases[token]
                                    self.warnings.append({
                                        'func': func_name,
                                        'var': split_code_comment(case_part)[0].strip().lower(),
                                        'type': 'Duplicate Case Value',
                                        'desc': f"Duplicate Switch Case value '{split_code_comment(case_part)[0].strip()}' at line {ln}; AutoIt Select/Switch does not fall through, so the earlier Case at line {first_ln} wins.",
                                        'file': orig_file,
                                        'line': orig_ln
                                    })
                                else:
                                    new_case_tokens.append(token)
                        for token in new_case_tokens:
                            stack[-1][6][token] = ln
                        if len(stack[-1]) > 5:
                            stack[-1][5] = case_tokens
                continue

            # Declarations checks
            m_local_enum = re.match(r'(?i)^\s*(Local|Dim|Static)\s+Enum\s+(.+)', stripped)
            if m_local_enum:
                reference_code_parts = []
                enum_part = split_code_comment(m_local_enum.group(2))[0]
                enum_part = re.sub(r'(?i)^\s*Step\s+[-+]?\d+\s+', '', enum_part)
                current_range = get_current_block_range(ln)
                for enum_item in split_top_level(enum_part, ','):
                    m_enum_var = re.search(r'(\$\w+)', enum_item)
                    if not m_enum_var:
                        continue
                    enum_var = m_enum_var.group(1).lower()
                    if self.warnings_config.get(3, False) and enum_var in declarations and any(d[0] != ln for d in declarations[enum_var]):
                        orig_file, orig_ln = line_mappings[ln - 1]
                        self.warnings.append({
                            'func': func_name,
                            'var': enum_var,
                            'type': 'Duplicate Declaration',
                            'desc': f"Variable '{enum_var}' is already declared.",
                            'file': orig_file,
                            'line': orig_ln
                        })
                    self.register_declaration(declarations, enum_var, ln, current_range, True, "scalar", get_current_guards())
                    maybe_uninitialized.discard(enum_var)
                    uninit_candidates.discard(enum_var)
                continue

            inline_decl = re.match(r'(?i)^\s*If\s+(.+?)\s+Then\s+((?:Static\s+)?(?:Global|Local|Dim|Static)\s+.+)$', split_code_comment(stripped)[0])
            declaration_text = inline_decl.group(2) if inline_decl else stripped
            m_decl = self.decl_rx.match(declaration_text)
            if m_decl:
                reference_code_parts = [inline_decl.group(1)] if inline_decl else []
                scope = m_decl.group(2).lower()
                is_const = declaration_has_const(stripped)
                if scope in ('local', 'dim', 'static'):
                    vars_part = split_code_comment(m_decl.group(3))[0]
                    current_range = get_current_block_range(ln)
                    parts = self.split_declaration_parts(vars_part)
                    for part in parts:
                        part_stripped = re.sub(r'(?i)^\s*(Static|Const)\s+', '', part)
                        assignment_parts = split_top_level(part_stripped, '=')
                        left = assignment_parts[0]
                        if len(assignment_parts) > 1:
                            reference_code_parts.append('='.join(assignment_parts[1:]))
                        var_lower, dims = self.parse_array_dimensions(left)
                        if var_lower:
                            prior_duplicate_decls = [d for d in declarations.get(var_lower, []) if d[0] != ln and not declaration_path_terminates(d)]
                            if self.warnings_config.get(3, False) and scope != 'dim' and dims == "scalar" and prior_duplicate_decls:
                                orig_file, orig_ln = line_mappings[ln - 1]
                                first_decl_ln = [d[0] for d in declarations[var_lower] if d[0] != ln]
                                details_val = None
                                if first_decl_ln:
                                    orig_decl_file, orig_decl_ln = line_mappings[first_decl_ln[0] - 1]
                                    details_val = {
                                        'original_declaration': {
                                            'file': os.path.abspath(orig_decl_file).replace('\\', '/'),
                                            'line': orig_decl_ln
                                        }
                                    }
                                self.warnings.append({
                                    'func': func_name,
                                    'var': var_lower,
                                    'type': 'Duplicate Declaration',
                                    'desc': f"Variable '{var_lower}' is already declared.",
                                    'file': orig_file,
                                    'line': orig_ln,
                                    'details': details_val
                                })
                            already_bound = var_lower in declarations or var_lower in global_vars
                            if self.warnings_config.get(6, False) and scope == 'dim' and not already_bound:
                                orig_file, orig_ln = line_mappings[ln - 1]
                                self.warnings.append({
                                    'func': func_name,
                                    'var': var_lower,
                                    'type': 'Deprecated Dim Use',
                                    'desc': f"Dim usage is deprecated; use Local or Global instead for '{var_lower}'.",
                                    'file': orig_file,
                                    'line': orig_ln
                                })
                            if re.search(r'\$\w+\s*\[\s*\]\s*$', left.strip()):
                                map_vars.add(var_lower)
                                map_known_keys.setdefault(var_lower, set())
                            if scope == 'dim' and var_lower in global_vars:
                                register_global_var(global_vars, var_lower, global_vars[var_lower][0], dims)
                                continue
                            record_sibling_branch_array_dim(var_lower, dims, current_range)
                            self.register_declaration(declarations, var_lower, ln, current_range, is_const, dims, get_current_guards())
                            if inline_decl and not already_bound:
                                initializer_guards = boolean_guard_polarities(inline_decl.group(1).strip().lower())
                                conditional_initializers.setdefault(var_lower, set()).update(initializer_guards)
                                maybe_uninitialized.add(var_lower)
                                uninit_candidates.add(var_lower)
                            if inline_decl:
                                if len(assignment_parts) > 1:
                                    record_assignment_event(var_lower, ln, 'inline initializer')
                            elif len(assignment_parts) == 1 and dims == "scalar":
                                uninit_candidates.add(var_lower)
                            else:
                                maybe_uninitialized.discard(var_lower)
                                uninit_candidates.discard(var_lower)
                                if len(assignment_parts) > 1:
                                    record_assignment_event(var_lower, ln, 'initializer')
                                    record_value_set_assignment(var_lower, '='.join(assignment_parts[1:]), conditional=False)
                elif scope == 'global':
                    vars_part = split_code_comment(m_decl.group(3))[0]
                    parts = self.split_declaration_parts(vars_part)
                    for part in parts:
                        assignment_parts = split_top_level(part, '=')
                        left = assignment_parts[0]
                        if len(assignment_parts) > 1:
                            reference_code_parts.append('='.join(assignment_parts[1:]))
                        m_var = re.search(r'(\$\w+)', left)
                        if m_var:
                            var_lower = m_var.group(1).lower()
                            orig_file, orig_ln = line_mappings[ln - 1]
                            self.warnings.append({
                                'func': func_name,
                                'var': var_lower,
                                'type': 'Global Scope Violation',
                                'desc': f"Variable '{var_lower}' is declared with Global scope inside function '{func_name}' at line {ln} (original: {os.path.basename(orig_file)}:{orig_ln}). Globals should only be declared at the file level.",
                                'file': orig_file,
                                'line': orig_ln
                            })
            else:
                m_redim = re.match(r'(?i)^\s*ReDim\s+(.+)', stripped)
                if not m_redim and self.experimental_checks:
                    m_redim = re.search(r'(?i)\bThen\s+ReDim\s+(.+)', stripped)
                if m_redim:
                    reference_code_parts = []
                    is_inline_then_redim = re.search(r'(?i)\bThen\s+ReDim\b', stripped) is not None
                    parts = self.split_declaration_parts(split_code_comment(m_redim.group(1))[0])
                    for part in parts:
                        left = split_assignment_left(part)
                        var_lower, dims = self.parse_array_dimensions(left)
                        if var_lower:
                            dim_exprs = left[len(var_lower):]
                            reference_code_parts.append(dim_exprs)
                            old_dim_counts = []
                            if var_lower in declarations:
                                for d in declarations[var_lower]:
                                    if isinstance(d[3], tuple):
                                        old_dim_counts.append(len(d[3]))
                            elif var_lower in global_vars:
                                old_dims = global_vars[var_lower][1]
                                if isinstance(old_dims, tuple):
                                    old_dim_counts.append(len(old_dims))
                            if (
                                isinstance(dims, tuple)
                                and old_dim_counts
                                and len(dims) not in old_dim_counts
                                and len(dims) not in branch_polymorphic_array_dims.get(var_lower, set())
                                and not (is_inline_then_redim and in_else_branch())
                                and var_lower not in param_vars
                            ):
                                add_warning(
                                    'ReDim Dimension Change',
                                    var_lower,
                                    f"ReDim changes array '{var_lower}' from {old_dim_counts[-1]}D to {len(dims)}D inside function '{func_name}'.",
                                    ln
                                )
                            if var_lower in declarations:
                                self.register_declaration(declarations, var_lower, ln, get_current_block_range(ln), False, dims, get_current_guards())
                            elif var_lower in global_vars:
                                register_global_var(global_vars, var_lower, global_vars[var_lower][0], dims)

                # Check for direct assignment to see if we're assigning to a Constant
                m_assign = re.match(r'^\s*(\$\w+)\s*((?:\+|-|\*|/|&)?=)\s*(.*)', split_code_comment(stripped)[0])
                if m_assign:
                    assign_var = m_assign.group(1).lower()
                    assign_op = m_assign.group(2)
                    assign_rhs = split_code_comment(m_assign.group(3))[0]
                    is_accumulator_init = is_self_concat_initializer(assign_var, assign_op, assign_rhs)
                    if assign_op == '=':
                        reference_code_parts = [strip_self_accumulator_read(assign_var, assign_op, assign_rhs) if is_accumulator_init else assign_rhs]
                    elif assign_op == '&=' and is_accumulator_init:
                        reference_code_parts = [assign_rhs]
                    is_const = False
                    if assign_var in declarations:
                        if any(d[2] for d in declarations[assign_var]):
                            is_const = True
                    elif assign_var in global_vars:
                        if global_vars[assign_var][0]:
                            is_const = True
                            
                    if is_const:
                        orig_file, orig_ln = line_mappings[ln - 1]
                        self.warnings.append({
                            'func': func_name,
                            'var': assign_var,
                            'type': 'Constant Assignment Violation',
                            'desc': f"Cannot assign a new value to constant variable '{assign_var}' inside function '{func_name}' at line {ln} (original: {os.path.basename(orig_file)}:{orig_ln}).",
                            'file': orig_file,
                            'line': orig_ln
                        })
                    if is_accumulator_init:
                        record_accumulator_initialization(assign_var)
                    else:
                        record_assignment_effect(assign_var, ln)
                        record_assignment_event(assign_var, ln, 'assignment')
                        if assign_op == '=':
                            record_scalar_assignment_type(assign_var, ln, assign_rhs)
                            record_value_set_assignment(assign_var, assign_rhs, conditional=bool(stack))
                            m_status_dep = re.match(r'(?i)^\s*([a-zA-Z_]\w*)\s*\(\s*(\$\w+)\s*\)\s*$', assign_rhs)
                            if m_status_dep:
                                dep_func = m_status_dep.group(1).lower()
                                dep_var = m_status_dep.group(2).lower()
                                return_consts = self.function_return_constants.get(dep_func, set())
                                if return_consts:
                                    by_case = status_dependency_vars.setdefault(assign_var, {})
                                    for const_var in return_consts:
                                        by_case.setdefault(const_var, set()).add(dep_var)
                else:
                    m_index_assign = re.match(r'^\s*(\$\w+(?:\s*\[[^\]]+\])+)\s*((?:\+|-|\*|/|&)?=)\s*(.*)', split_code_comment(stripped)[0])
                    if m_index_assign:
                        assign_lhs = m_index_assign.group(1)
                        assign_rhs = split_code_comment(m_index_assign.group(3))[0]
                        reference_code_parts = lhs_index_expressions(assign_lhs) + [assign_rhs]

                for m_then_assign in re.finditer(r'(?i)\bIf\s+(.+?)\s+Then\s+(\$\w+)\s*(?:\+|-|\*|/|&)?=', stripped):
                    then_condition = m_then_assign.group(1).strip().lower()
                    then_var = m_then_assign.group(2).lower()
                    assignment_lhs_vars.add(then_var)
                    if then_var in uninit_candidates:
                        maybe_uninitialized.add(then_var)
                        record_guarded_assignment(then_var, then_condition)
                        record_boolean_guarded_assignment(then_var, then_condition)
                    record_assignment_event(then_var, ln, 'inline assignment')
                for m_then_value in re.finditer(r'(?i)\bIf\s+.+?\s+Then\s+(\$\w+)\s*=\s*(\$\w+)\b', stripped):
                    record_value_set_assignment(m_then_value.group(1).lower(), m_then_value.group(2), conditional=True)

                for m_call_byref in func_call_rx.finditer(code_part):
                    call_name = m_call_byref.group(1).lower()
                    byref_positions = self.byref_param_positions.get(call_name)
                    if not byref_positions:
                        continue
                    call_args_byref = extract_call_args(code_part, m_call_byref)
                    for pos in byref_positions:
                        if pos >= len(call_args_byref):
                            continue
                        arg_str = call_args_byref[pos].strip()
                        m_byref_arg = re.match(r'^\s*(\$\w+)\s*$', arg_str)
                        
                        if m_byref_arg:
                            byref_var = m_byref_arg.group(1).lower()
                            record_assignment_effect(byref_var, ln)
                            
                            # Check if the variable is const
                            is_const_var = False
                            if byref_var in global_vars and global_vars[byref_var][0]:
                                is_const_var = True
                            elif byref_var in declarations:
                                for decl in declarations[byref_var]:
                                    if decl[2]:
                                        is_const_var = True
                                        break
                            
                            if is_const_var and self.warnings_config.get(7, True) and not self.warnings_config.get('_legacy_mode', False):
                                orig_file, orig_ln = line_mappings[ln - 1]
                                self.warnings.append({
                                    'func': func_name,
                                    'var': byref_var,
                                    'type': 'ByRef Const Pass',
                                    'desc': f"ByRef parameter expects a modifiable variable: passing Const variable '{byref_var}'.",
                                    'file': orig_file,
                                    'line': orig_ln
                                })
                        else:
                            if self.warnings_config.get(7, True) and not self.warnings_config.get('_legacy_mode', False):
                                orig_file, orig_ln = line_mappings[ln - 1]
                                self.warnings.append({
                                    'func': func_name,
                                    'var': arg_str,
                                    'type': 'ByRef Const Pass',
                                    'desc': f"ByRef parameter expects a modifiable variable: passing expression or literal '{arg_str}'.",
                                    'file': orig_file,
                                    'line': orig_ln
                                })

                for m_map_set in re.finditer(r'(\$\w+)\s*\[\s*(["\'])(.*?)\2\s*\]\s*(?<![<>=])=(?!=)', code_part):
                    map_var = m_map_set.group(1).lower()
                    map_vars.add(map_var)
                    map_known_keys.setdefault(map_var, set()).add(m_map_set.group(3).lower())

                for m_close in re.finditer(r'(?i)\bFileClose\s*\(\s*(\$\w+)\s*\)', code_no_strings):
                    file_handles.pop(m_close.group(1).lower(), None)

                # For loops
                m_for = re.match(r'(?i)^\s*for\s+(\$\w+)', stripped)
                if m_for:
                    var_lower = m_for.group(1).lower()
                    if var_lower in loop_vars:
                        add_warning(
                            'Nested Loop Variable Reuse',
                            var_lower,
                            f"Loop variable '{var_lower}' is reused by a nested loop inside function '{func_name}'.",
                            ln
                        )
                    loop_vars.append(var_lower)
                    self.register_declaration(declarations, var_lower, ln, None, False, "scalar", get_current_guards())
                m_for_in = re.match(r'(?i)^\s*for\s+(\$\w+)\s+in', stripped)
                if m_for_in:
                    var_lower = m_for_in.group(1).lower()
                    self.register_declaration(declarations, var_lower, ln, None, False, "scalar", get_current_guards())

            # Collect references
            reference_code = ' '.join(reference_code_parts)
            code_no_strings = self.strip_strings(reference_code)
            for var in self.var_ref_rx.findall(code_no_strings):
                var_lower = var.lower()
                references.append((ln, var_lower, line, get_current_guards()))
                if var_lower in assignment_lhs_vars:
                    continue
                if var_lower in unchecked_seterror_results:
                    assignment_ln = unchecked_seterror_results[var_lower][0]
                    if assignment_ln != ln and is_seterror_payload_failure_guard(var_lower, line):
                        del unchecked_seterror_results[var_lower]
                        continue
                    if assignment_ln != ln and re.search(rf'(?i)(?:Return\s+)?{re.escape(var_lower)}\s*[+\-*/&=<>]', code_no_strings):
                        add_warning(
                            'Unchecked SetError Return',
                            var_lower,
                            f"Variable '{var_lower}' from '{unchecked_seterror_results[var_lower][1]}' is used before a visible @error validation.",
                            ln
                        )
                        del unchecked_seterror_results[var_lower]
                if var_lower in maybe_uninitialized and var_lower not in warned_uninitialized:
                    if current_branch_assigns(var_lower) or current_loop_assigns(var_lower):
                        continue
                    if current_status_dependency_allows(var_lower):
                        continue
                    if is_string_concat_default_use(var_lower, code_no_strings):
                        add_warning(
                            'Implicit Empty String Use',
                            var_lower,
                            f"String-like variable '{var_lower}' may rely on AutoIt's implicit empty-string default at line {ln}.",
                            ln
                        )
                        warned_uninitialized.add(var_lower)
                        continue
                    add_warning(
                        'Potential Uninitialized Use',
                        var_lower,
                        f"Variable '{var_lower}' may be used at line {ln} before every control-flow path assigns it.",
                        ln
                    )
                    warned_uninitialized.add(var_lower)

            # Check array subscript references
            subscript_rx = re.compile(r'(\$\w+)\[([^\]]+)\](?:\[([^\]]+)\])?')
            for m_sub in subscript_rx.finditer(code_no_strings):
                ref_var = m_sub.group(1).lower()
                g2 = m_sub.group(2).strip()
                g3 = m_sub.group(3).strip() if m_sub.group(3) is not None else ""
                access_dims = 2 if g3 != "" else 1

                if ref_var in unchecked_array_results:
                    idx_text = g2 if access_dims == 1 else g3
                    result_func = unchecked_array_results[ref_var][1].lower()
                    if result_func == 'stringsplit' and access_dims == 1 and idx_text in ('0', '1'):
                        unchecked_array_results.pop(ref_var, None)
                        continue
                    should_warn_index = idx_text.isdigit() and (result_func == 'stringregexp' or int(idx_text) > 0)
                    if should_warn_index:
                        add_warning(
                            'Unchecked Array Result Index',
                            ref_var,
                            f"Array result '{ref_var}' from {unchecked_array_results[ref_var][1]} is indexed at [{idx_text}] without a visible UBound/count check.",
                            ln
                        )
                        del unchecked_array_results[ref_var]

                if ref_var in dllcall_result_sizes and g2.isdigit():
                    idx = int(g2)
                    max_index = dllcall_result_sizes[ref_var][1]
                    if idx > max_index:
                        add_warning(
                            'DllCall Return Index Mismatch',
                            ref_var,
                            f"DllCall result '{ref_var}' is accessed at index {idx}, but the parsed signature exposes indexes 0..{max_index}.",
                            ln
                        )

                if access_dims == 2:
                    for alias_var, source_var in ubound_aliases.items():
                        if alias_var in g3.lower():
                            add_warning(
                                'Suspicious UBound Dimension',
                                alias_var,
                                f"UBound alias '{alias_var}' was created without an explicit dimension for '{source_var}' and is used as a second-dimension subscript.",
                                ln
                            )
                
                # Look up variable type/dimensions
                dims_list = []
                if ref_var in declarations:
                    for d in declarations[ref_var]:
                        if declaration_visible(d, ln, get_current_guards()):
                            if isinstance(d[3], tuple):
                                dims_list.append(d[3])
                elif ref_var in global_vars:
                    global_dims = global_vars[ref_var][1]
                    if isinstance(global_dims, tuple):
                        dims_list.append(global_dims)
                    elif isinstance(global_dims, list):
                        dims_list.extend(d for d in global_dims if isinstance(d, tuple))
                        
                if dims_list:
                    if ref_var in param_vars:
                        continue
                    # Find if at least one declaration matches access_dims
                    any_match = False
                    for dims in dims_list:
                        if len(dims) == access_dims:
                            any_match = True
                            break
                    if not any_match:
                        # Warn using the most recent declaration for details
                        best_dims = dims_list[-1]
                        decl_dims = len(best_dims)
                        orig_file, orig_ln = line_mappings[ln - 1]
                        self.warnings.append({
                            'func': func_name,
                            'var': ref_var,
                            'type': 'Array Dimension Mismatch',
                            'desc': f"Array '{ref_var}' is declared as {decl_dims}D but accessed as {access_dims}D inside function '{func_name}' at line {ln} (original: {os.path.basename(orig_file)}:{orig_ln}).",
                            'file': orig_file,
                            'line': orig_ln
                        })
                    else:
                        # Use the matching dimensions for bounds check
                        matching_dims = None
                        for dims in reversed(dims_list):
                            if len(dims) == access_dims:
                                matching_dims = dims
                                break
                        if matching_dims:
                            # 1D bounds check
                            if access_dims == 1:
                                if g2.isdigit() or (g2.startswith("-") and g2[1:].isdigit()):
                                    idx = int(g2)
                                    size = matching_dims[0]
                                    if size is not None and (idx >= size or idx < 0):
                                        orig_file, orig_ln = line_mappings[ln - 1]
                                        self.warnings.append({
                                            'func': func_name,
                                            'var': ref_var,
                                            'type': 'Array Subscript Out of Bounds',
                                            'desc': f"Subscript index {idx} is out of bounds for 1D array '{ref_var}' of size {size} inside function '{func_name}' at line {ln} (original: {os.path.basename(orig_file)}:{orig_ln}).",
                                            'file': orig_file,
                                            'line': orig_ln
                                        })
                            # 2D bounds check
                            elif access_dims == 2:
                                if g2.isdigit() or (g2.startswith("-") and g2[1:].isdigit()):
                                    idx1 = int(g2)
                                    size1 = matching_dims[0]
                                    if size1 is not None and (idx1 >= size1 or idx1 < 0):
                                        orig_file, orig_ln = line_mappings[ln - 1]
                                        self.warnings.append({
                                            'func': func_name,
                                            'var': ref_var,
                                            'type': 'Array Subscript Out of Bounds',
                                            'desc': f"Subscript index {idx1} is out of bounds for first dimension of 2D array '{ref_var}' of size {size1} inside function '{func_name}' at line {ln} (original: {os.path.basename(orig_file)}:{orig_ln}).",
                                            'file': orig_file,
                                            'line': orig_ln
                                        })
                                if g3.isdigit() or (g3.startswith("-") and g3[1:].isdigit()):
                                    idx2 = int(g3)
                                    size2 = matching_dims[1]
                                    if size2 is not None and (idx2 >= size2 or idx2 < 0):
                                        orig_file, orig_ln = line_mappings[ln - 1]
                                        self.warnings.append({
                                            'func': func_name,
                                            'var': ref_var,
                                            'type': 'Array Subscript Out of Bounds',
                                            'desc': f"Subscript index {idx2} is out of bounds for second dimension of 2D array '{ref_var}' of size {size2} inside function '{func_name}' at line {ln} (original: {os.path.basename(orig_file)}:{orig_ln}).",
                                            'file': orig_file,
                                            'line': orig_ln
                                        })

            # Block Start checks
            if self.is_multiline_if(line):
                stack.append(('if', ln, [[ln, None, 'if', set()]], normalize_guard(line), raw_if_condition(line)))
            elif stripped_lower.startswith('switch '):
                switch_expr = re.sub(r'(?i)^\s*switch\s+', '', split_code_comment(stripped)[0]).strip()
                stack.append(['switch', ln, [], simple_var_expr(switch_expr), {}, set(), {}])
            elif stripped_lower == 'select' or stripped_lower.startswith('select '):
                stack.append(('select', ln, []))
            elif re.match(r'(?i)^\s*(for\s|while\s|do\b)', stripped):
                stack.append(['loop', ln, [ln, None]])

        # Check scoping violations and completely undeclared variables
        all_referenced_vars = set(ref_var for _, ref_var, _, _ in references)

        if self.experimental_checks and assignment_events:
            reads_by_var = {}
            for ref_ln, ref_var, _, _ in references:
                reads_by_var.setdefault(ref_var, []).append(ref_ln)
            assignments_by_var = {}
            for assign_ln, assign_var, assign_kind in assignment_events:
                assignments_by_var.setdefault(assign_var, []).append((assign_ln, assign_kind))
            warned_dead_stores = set()
            for assign_var, events in assignments_by_var.items():
                if assign_var not in declarations and assign_var not in global_vars:
                    continue
                if assign_var in byref_param_vars:
                    continue
                events.sort(key=lambda item: item[0])
                read_lines = sorted(reads_by_var.get(assign_var, []))
                first_assign_ln = events[0][0]
                assign_file = line_mappings[first_assign_ln - 1][0]
                if is_std_include_path(assign_file) and not self.system_dead_stores:
                    continue
                if any(read_ln > first_assign_ln for read_ln in read_lines):
                    continue
                key = (assign_var, first_assign_ln)
                if key in warned_dead_stores:
                    continue
                details_val = None
                if assign_var in declarations:
                    orig_decl_file, orig_decl_ln = line_mappings[declarations[assign_var][0][0] - 1]
                    details_val = {
                        "declared_at": {
                            "file": os.path.abspath(orig_decl_file).replace('\\', '/'),
                            "line": orig_decl_ln
                        }
                    }
                desc = f"Variable '{assign_var}' is assigned {len(events)} time(s) starting at line {first_assign_ln}, but the value is never read before function '{func_name}' exits."
                add_warning('Dead Store', assign_var, desc, first_assign_ln, details=details_val)
                warned_dead_stores.add(key)

        # 1. Block Scoping and Reference Before Declaration Checks
        # - Reference Before Declaration: A variable is referenced at a line number prior to its declaration.
        # - Block Scoping Bug: A variable is declared inside a specific block (like If/For/While) but referenced outside that block.
        for var, decls in declarations.items():
            var_refs = [(ref_ln, ref_text, ref_guards) for ref_ln, ref_var, ref_text, ref_guards in references if ref_var == var]
            for ref_ln, ref_text, ref_guards in var_refs:
                satisfied = False
                for decl in decls:
                    if declaration_visible(decl, ref_ln, ref_guards):
                        satisfied = True
                        break
                if not satisfied:
                    earliest_decl = min(d[0] for d in decls)
                    orig_ref_file, orig_ref_ln = line_mappings[ref_ln - 1]
                    
                    if ref_ln < earliest_decl:
                        orig_decl_file, orig_decl_ln = line_mappings[earliest_decl - 1]
                        self.warnings.append({
                            'func': func_name,
                            'var': var,
                            'type': 'Reference Before Declaration',
                            'desc': f"Referenced at line {ref_ln} (original: {os.path.basename(orig_ref_file)}:{orig_ref_ln}) before declaration at line {earliest_decl} (original: {os.path.basename(orig_decl_file)}:{orig_decl_ln})",
                            'file': orig_ref_file,
                            'line': orig_ref_ln,
                            'details': {
                                'declaration': {
                                    'file': os.path.abspath(orig_decl_file).replace('\\', '/'),
                                    'line': orig_decl_ln
                                }
                            }
                        })
                    else:
                        best_decl = decls[0]
                        for d in decls:
                            if d[0] <= ref_ln:
                                best_decl = d
                        start_b = best_decl[1][0] if best_decl[1] else 0
                        end_b = best_decl[1][1] if best_decl[1] else 0
                        
                        orig_decl_file, orig_decl_ln = line_mappings[best_decl[0] - 1]
                        
                        block_desc = f"(lines {start_b}-{end_b})" if end_b else ""
                        self.warnings.append({
                            'func': func_name,
                            'var': var,
                            'type': 'Block Scoping Bug',
                            'desc': f"Declared inside block {block_desc} at preprocessed line {best_decl[0]} (original: {os.path.basename(orig_decl_file)}:{orig_decl_ln}) but referenced outside at preprocessed line {ref_ln} (original: {os.path.basename(orig_ref_file)}:{orig_ref_ln})",
                            'file': orig_ref_file,
                            'line': orig_ref_ln,
                            'details': {
                                'declaration': {
                                    'file': os.path.abspath(orig_decl_file).replace('\\', '/'),
                                    'line': orig_decl_ln,
                                    'block': f"lines {start_b}-{end_b}" if end_b else ""
                                }
                            }
                        })

        # 2. Undeclared Variables Check
        # Reports variables that are referenced in code but never declared anywhere in local, global, or parameter scopes.
        for ref_var in all_referenced_vars:
            if ref_var not in declarations and ref_var not in global_vars:
                candidates = list(declarations.keys()) + list(global_vars.keys())
                suggestions = []
                for cand in candidates:
                    dist = levenshtein_distance(ref_var, cand)
                    if dist <= 2:
                        suggestions.append((dist, cand))
                suggestions.sort()
                suggestions_list = [c[1] for c in suggestions[:3]]
                details_val = None
                if suggestions_list:
                    details_val = {"suggestions": suggestions_list}
                
                var_refs = [(ref_ln, ref_text) for ref_ln, ref_v, ref_text, _ in references if ref_v == ref_var]
                for ref_ln, ref_text in var_refs:
                    orig_ref_file, orig_ref_ln = line_mappings[ref_ln - 1]
                    self.warnings.append({
                        'func': func_name,
                        'var': ref_var,
                        'type': 'Undeclared Variable',
                        'desc': f"Variable '{ref_var}' is referenced but is not declared as a local variable, global variable, or function parameter.",
                        'file': orig_ref_file,
                        'line': orig_ref_ln,
                        'details': details_val
                    })

        # 3. Unused Local Variables Check (Warning Switch -w 5)
        # Identifies variables that are declared locally inside a function but never referenced/used anywhere.
        if self.warnings_config.get(5, False):
            for var, decls in declarations.items():
                is_param = any(decl[0] == func_start_line for decl in decls)
                if is_param:
                    continue
                if var not in all_referenced_vars:
                    for decl in decls[:1]:
                        orig_decl_file, orig_decl_ln = line_mappings[decl[0] - 1]
                        self.warnings.append({
                            'func': func_name,
                            'var': var,
                            'type': 'Unused Variable',
                            'desc': f"Variable '{var}' is declared but never used in function '{func_name}'.",
                            'file': orig_decl_file,
                            'line': orig_decl_ln
                        })


def preprocess_sys_argv(argv):
    """
    @brief Normalizes legacy command-line arguments.
    @details Normalizes switches like `-w- 5` or `-w5` to a standard key-value pair representation (`-w`, `5` or `-w`, `-5`).
    @param argv List of raw command-line arguments.
    @return List of normalized command-line arguments.
    @author Harald Frank
    """
    normalized = []
    normalized.append(argv[0])
    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg.startswith('-w-') or arg.startswith('-w'):
            val = ""
            if arg.startswith('-w-'):
                val = "-" + arg[3:]
            else:
                val = arg[2:]
            if not val or val == "-":
                if i + 1 < len(argv):
                    next_arg = argv[i+1]
                    if arg.startswith('-w-'):
                        val = "-" + next_arg
                    else:
                        val = next_arg
                    i += 1
            normalized.append("-w")
            normalized.append(val)
        elif arg.startswith('-v-') or arg.startswith('-v'):
            val = ""
            if arg.startswith('-v-'):
                val = "-" + arg[3:]
            else:
                val = arg[2:]
            if not val or val == "-":
                if i + 1 < len(argv):
                    next_arg = argv[i+1]
                    if arg.startswith('-v-'):
                        val = "-" + next_arg
                    else:
                        val = next_arg
                    i += 1
            normalized.append("-v")
            normalized.append(val)
        elif arg == "-I":
            if i + 1 < len(argv):
                normalized.append("-I")
                normalized.append(argv[i+1])
                i += 1
        elif arg.startswith("-I"):
            normalized.append("-I")
            normalized.append(arg[2:])
        else:
            normalized.append(arg)
        i += 1
    return normalized

def get_original_au3check_header():
    """
    @brief Dynamically extracts the original Au3Check header from local installation files, falling back to a default.
    """
    import subprocess
    header = None
    for name in ["Au3Check_Original.exe", "Au3Check.exe"]:
        for path in [
            r"C:\Program Files (x86)\AutoIt3\\" + name,
            r"C:\Program Files\AutoIt3\\" + name,
            name
        ]:
            if os.path.exists(path):
                try:
                    res = subprocess.run([path, "-?"], capture_output=True, text=True, timeout=2)
                    if res.stdout:
                        lines = res.stdout.splitlines()
                        if lines and "Syntax Checker" in lines[0]:
                            header = lines[0].strip()
                            break
                except Exception:
                    pass
        if header:
            break
    if not header:
        header = "AutoIt3 Syntax Checker v3.3.18.0  Copyright (c) 2007-2025 Tylo & AutoIt Team"
    return header

def print_au3check_usage():
    """
    @brief Prints the legacy-compatible help usage information for au3Mythos.
    @author Harald Frank
    """
    print(get_original_au3check_header())
    print("")
    print("Usage: Au3Check [-q] [-d] [-w[-] n]... [-v[-] n]... [-I dir]... file.au3")
    print('            -q        : quiet (only error/warn output)')
    print('            -d        : as Opt("MustDeclareVars", 1)')
    print("            -w 1      : already included file (on)")
    print("            -w 2      : missing #comments-end (on)")
    print("            -w 3      : already declared var (off)")
    print("            -w 4      : local var used in global scope (off)")
    print("            -w 5      : local var declared but not used (off)")
    print("            -w 6      : warn when using Dim (off)")
    print("            -w 7      : warn when passing Const or expression on ByRef param(s) (on)")
    print("            -v 1      : show include paths/files (off)")
    print("            -v 2      : show lexer tokens (off)")
    print("            -v 3      : show unreferenced UDFs and global variables (off)")
    print("            -I dir    : additional directories for searching include files")
    print("")
    print("       Exit codes:")
    print("             0        : success - no errors or warnings")
    print("             1        : warning(s) only")
    print("             2        : syntax error(s)")
    print("             3        : usage or input error")


def legacy_marker_line(col):
    """
    @brief Formats a compiler caret pointer line.
    @param col The 1-based column position of the error.
    @return Caret marker line (e.g. '~~~~~~~~~~~^').
    @author Harald Frank
    """
    return ("~" * max(col - 1, 0)) + "^"

def load_builtins():
    """
    @brief Loads native built-in functions and their parameter configurations from Au3Check.dat.
    @details Leverages a hardcoded list of common builtins as a fallback.
    @return Dictionary of name_lower -> (min_args, max_args).
    @author Harald Frank
    """
    # Fallback dictionary of common built-ins: name_lower -> (min_args, max_args)
    # Defaulting to (0, 99) for safe fallback
    builtins = {
        "abs": (1, 1), "acos": (1, 1), "adlibregister": (1, 2), "adlibunregister": (0, 1),
        "asc": (1, 1), "asin": (1, 1), "assign": (2, 3), "atan": (1, 1), "msgbox": (3, 4),
        "consolewrite": (1, 1), "consolewriteerror": (1, 1), "ubound": (1, 2)
    }
    fallback_names = [
        "abs", "acos", "adlibregister", "adlibunregister", "asc", "asin", "assign", "atan", "autoitsetoption",
        "autoitwingettitle", "autoitwinsettitle", "beep", "binary", "binarylen", "binarymid", "binarytostring",
        "bitand", "bitnot", "bitor", "bitrotate", "bitshift", "bitxor", "call", "ceiling", "chr", "chrw",
        "clipput", "clipget", "close", "cmdlineraw", "consolewrite", "consolewriteerror", "controlclick",
        "controlcommand", "controldisable", "controlenable", "controlfocus", "controlgetfocus", "controlgethandle",
        "controlgetpos", "controlgettext", "controlhide", "controlmove", "controlsend", "controlsettext",
        "controlshow", "cos", "dec", "dircopy", "dircreate", "dirmove", "dirremove", "dllcall", "dllcalladdress",
        "dllcallbackfree", "dllcallbackgetptr", "dllcallbackregister", "dllclose", "dllopen", "dllstructcreate",
        "dllstructgetdata", "dllstructgetptr", "dllstructgetsize", "dllstructsetdata", "drivegetdrive",
        "drivegetfilesystem", "drivegetlabel", "drivegetserial", "drivegettype", "drivespacefree", "drivespacetotal",
        "drivemapadd", "drivemapdel", "drivemapget", "envget", "envset", "envupdate", "eval", "execute", "exp",
        "fileclose", "filecopy", "filecreateshortcut", "filedelete", "fileexists", "filefindfirstfile",
        "filefindnextfile", "filegetattrib", "filegetencoding", "filegetlongname", "filegetpos", "filegetshortcut",
        "filegetsize", "filegettime", "filegetversion", "fileinstall", "filemove", "fileopen", "fileopendialog",
        "fileread", "filereadline", "filereadtoarray", "filerecyle", "filerecycleempty", "filesavedialog",
        "fileselectfolder", "filesetattrib", "filesetpos", "filesettime", "filewrite", "filewriteline", "floor",
        "ftpsolve", "funcname", "geodesic", "hex", "hotkeyset", "httpsetproxy", "httpsetuseragent", "hwnd",
        "inetclose", "inetget", "inetgetinfo", "inetgetsize", "inidelete", "iniread", "inireadsection",
        "inireadsectionnames", "inirenamesection", "iniwrite", "iniwritesection", "int", "isadmin", "isarray",
        "isbinary", "isbool", "isdeclared", "isdllstruct", "isfloat", "isfunc", "ishwnd", "isint", "iskeyword",
        "isnumber", "isobj", "isptr", "isstring", "log", "memgetstats", "mod", "mouseclick", "mouseclickdrag",
        "mousedown", "mousegetcursor", "mousegetpos", "mousemove", "mouseup", "mousewheel", "msgbox", "number",
        "objcreate", "objcreateinterface", "objevent", "objget", "processclose", "processexists", "processgetstats",
        "processlist", "processsetpriority", "processwait", "processwaitclose", "random", "regdelete", "regenumkey",
        "regenumval", "regread", "regwrite", "round", "run", "runas", "runaswait", "runwait", "send",
        "sendkeepactive", "seterror", "setextended", "shellexecute", "shellexecutewait", "shutdown", "sin",
        "sleep", "soundplay", "soundsetwavevolume", "srvany", "stderrread", "stdinwrite", "stdoutread", "string",
        "stringcompare", "stringformat", "stringfromasciiarray", "stringinstr", "stringisalnum", "stringisalpha",
        "stringisascii", "stringisdigit", "stringisfloat", "stringisint", "stringislower", "stringisspace",
        "stringisupper", "stringisxdigit", "stringleft", "stringlen", "stringlower", "stringmid", "stringregexp",
        "stringregexpreplace", "stringreplace", "stringreverse", "stringright", "stringsplit", "stringstripws",
        "stringtoasciiarray", "stringtobinary", "stringtrimleft", "stringtrimright", "stringupper", "tan",
        "tcpack", "tcpaccept", "tcpcloseconnection", "tcpconnect", "tcplisten", "tcpnametoip", "tcprecv",
        "tcpsend", "tcpshutdown", "tcpstartup", "timerdiff", "timerinit", "tooltiptoggle", "tooltip", "traycreateitem",
        "traycreatemenu", "traygetmsg", "trayitemdelete", "trayitemgethandle", "trayitemgetstate", "trayitemgettext",
        "trayitemsetonevent", "trayitemsetstate", "trayitemsettext", "traymenuitem", "traysetclick", "trayseticon",
        "traysetstate", "traysettooltip", "ubound", "udpcloseconnection", "udpbind", "udpopen", "udprecv",
        "udpsend", "udpshutdown", "udpstartup", "vargettype", "winactivate", "winactive", "winclose", "winkill",
        "winexists", "winflash", "wingetcaretpos", "wingetclasslist", "wingetclientid", "wingetclientsize",
        "wingethandle", "wingetpos", "wingetprocess", "wingetstate", "wingettext", "wingettitle", "winlist",
        "winmenuselectitem", "winminimizeall", "winminimizeallundo", "winmove", "winsetontop", "winsetstate",
        "winsettitle", "winsettrans", "winwait", "winwaitactive", "winwaitclose", "winwaitnotactive"
    ]
    for name in fallback_names:
        if name not in builtins:
            builtins[name] = (0, 99)

    dat_path = r"C:\Program Files (x86)\AutoIt3\Au3Check.dat"
    if os.path.exists(dat_path):
        try:
            for line in read_autoit_lines(dat_path):
                if line.startswith('!'):
                    parts = line[1:].strip().split()
                    if parts:
                        name = parts[0].lower()
                        min_args = 0
                        max_args = 99
                        if len(parts) > 1:
                            try:
                                min_args = int(parts[1])
                            except ValueError:
                                pass
                        if len(parts) > 2:
                            try:
                                max_args = int(parts[2])
                            except ValueError:
                                pass
                        builtins[name] = (min_args, max_args)
        except Exception:
            pass
    return builtins

def load_builtin_vars():
    """
    @brief Dynamic parsing of built-in/system variables (e.g. $CmdLine) from Au3Check.dat.
    @return Set of lowercase variable names.
    @author Harald Frank
    """
    vars_set = {"$cmdline", "$cmdlineraw"}
    dat_path = r"C:\Program Files (x86)\AutoIt3\Au3Check.dat"
    if os.path.exists(dat_path):
        try:
            for line in read_autoit_lines(dat_path):
                for part in line.strip().split():
                    if part.startswith('$'):
                        vars_set.add(part.lower())
        except Exception:
            pass
    return vars_set

def load_valid_macros():
    """
    @brief Retrieves the set of supported system macros.
    @details Loads all valid macro names starting with '@' from Au3Check.dat if available.
    @return Set of lowercase macro names.
    @author Harald Frank
    """
    macros = {
        "@appdatacommondir", "@appdatadir", "@autoitexe", "@autoitpid", "@autoitversion", "@autoitx64",
        "@com_eventobj", "@commonfilesdir", "@compiled", "@computername", "@comspec", "@cpuarch",
        "@cr", "@crlf", "@desktopcommondir", "@desktopdepth", "@desktopdir", "@desktopheight",
        "@desktoprefresh", "@desktopwidth", "@documentscommondir", "@error", "@exitcode", "@exitmethod",
        "@extended", "@favoritescommondir", "@favoritesdir", "@gui_ctrlhandle", "@gui_ctrlid",
        "@gui_dragfile", "@gui_dragid", "@gui_dropid", "@gui_winhandle", "@homedrive", "@homepath",
        "@homeshare", "@hotkeypressed", "@hour", "@ipaddress1", "@ipaddress2", "@ipaddress3",
        "@ipaddress4", "@kblayout", "@lf", "@localappdatadir", "@logondnsdomain", "@logondomain",
        "@logonserver", "@mday", "@min", "@mon", "@msec", "@muilang", "@mydocumentsdir",
        "@numparams", "@osarch", "@osbuild", "@oslang", "@osservicepack", "@ostype", "@osversion",
        "@programfilesdir", "@programscommondir", "@programsdir", "@scriptdir", "@scriptfullpath",
        "@scriptlinenumber", "@scriptname", "@sec", "@startmenucommondir", "@startmenudir",
        "@startupcommondir", "@startupdir", "@sw_disable", "@sw_enable", "@sw_hide", "@sw_lock",
        "@sw_maximize", "@sw_minimize", "@sw_restore", "@sw_show", "@sw_showdefault", "@sw_showmaximized",
        "@sw_showminimized", "@sw_showminnoactive", "@sw_showna", "@sw_shownoactivate", "@sw_shownormal",
        "@sw_unlock", "@systemdir", "@tab", "@tempdir", "@tray_id", "@trayiconflashing", "@trayiconvisible",
        "@username", "@userprofiledir", "@wday", "@windowsdir", "@workingdir", "@yday", "@year"
    }
    dat_path = r"C:\Program Files (x86)\AutoIt3\Au3Check.dat"
    if os.path.exists(dat_path):
        try:
            for line in read_autoit_lines(dat_path):
                for part in line.strip().split():
                    if part.startswith('@'):
                        macros.add(part.lower())
        except Exception:
            pass
    return macros

def collect_legacy_syntax_errors(file_path, lines=None, line_mappings=None):
    """
    @brief Scans preprocessed and continuation-merged source lines for core compiler syntax errors.
    @details Validates block structures (If/EndIf, Func/EndFunc, For/Next, While/Wend, Select/EndSelect, Switch/EndSwitch), UDF duplicate definitions, parameter declaration syntax, undefined functions, undefined macros, and parameter count checks on calls.
    @param file_path The path to the main file under analysis.
    @param lines Optional list of preprocessed lines. If None, read from file_path.
    @param line_mappings Map of preprocessed lines back to original file and line numbers.
    @return List of diagnostic tuples: (level, file, line, col, description, raw_source_line).
    @author Harald Frank
    """
    if lines is None:
        try:
            lines = read_autoit_lines(file_path)
        except AutoItSourceError:
            return []

    if line_mappings is None:
        line_mappings = [(file_path, idx) for idx, _ in enumerate(lines, start=1)]

    lines = [line.rstrip('\r\n') for line in lines]

    block_stack = []
    defined_funcs = {}
    last_code = None
    syntax_errors = []

    # Parse all defined UDFs first, along with their parameter signature counts
    defined_udfs = {}
    Local_in_block_comment = False
    for idx, line in enumerate(lines):
        orig_file, orig_line = line_mappings[idx]
        stripped = line.strip()
        stripped_lower = stripped.lower()
        if stripped_lower == '#comments-start' or stripped_lower == '#cs':
            Local_in_block_comment = True
            continue
        if stripped_lower == '#comments-end' or stripped_lower == '#ce':
            Local_in_block_comment = False
            continue
        if Local_in_block_comment:
            continue
        code = split_code_comment(line)[0].strip()
        if not code or code.startswith('#'):
            continue
        m_func = re.match(r'(?i)^func\s+(\w+)\s*\(', code)
        if m_func:
            func_name_lower = m_func.group(1).lower()
            open_pos = code.find('(', m_func.end() - 1)
            if open_pos >= 0:
                depth = 1
                params_str = ""
                for idx_ch in range(open_pos + 1, len(code)):
                    ch = code[idx_ch]
                    if ch == '(':
                        depth += 1
                    elif ch == ')':
                        depth -= 1
                        if depth == 0:
                            params_str = code[open_pos + 1:idx_ch]
                            break
                
                stripped_params = params_str.strip()
                if not stripped_params:
                    min_args = 0
                    max_args = 0
                else:
                    params_list = split_top_level(params_str, ',')
                    max_args = len(params_list)
                    min_args = 0
                    for param in params_list:
                        if '=' not in param:
                            min_args += 1
                def_col = max(1, line.find(')') + 2)
                defined_udfs[func_name_lower] = (min_args, max_args, orig_file, orig_line, def_col, line)
            else:
                defined_udfs[func_name_lower] = (0, 99, orig_file, orig_line, len(line) + 1, line)
        elif re.match(r'(?i)^func\s+(\w+)\b', code):
            func_name_lower = re.match(r'(?i)^func\s+(\w+)\b', code).group(1).lower()
            defined_udfs[func_name_lower] = (0, 99, orig_file, orig_line, len(line) + 1, line)

    builtins = load_builtins()
    valid_macros = load_valid_macros()
    keywords = {
        "if", "then", "else", "elseif", "endif", "while", "wend", "do", "until", "for", "to", "step", "next",
        "func", "endfunc", "return", "select", "case", "endselect", "switch", "endswitch", "with", "endwith",
        "local", "global", "dim", "const", "static", "byref", "and", "or", "not"
    }
    unsupported_bare_functions = {"try", "endtry", "catch", "finally", "throw"}

    # 1. Paren/bracket balance stack scanning & character validation
    paren_stack = []
    in_block_comment = False
    for idx, line in enumerate(lines):
        orig_file, orig_line = line_mappings[idx]
        stripped = line.strip()
        stripped_lower = stripped.lower()
        if stripped_lower == '#comments-start' or stripped_lower == '#cs':
            in_block_comment = True
            continue
        if stripped_lower == '#comments-end' or stripped_lower == '#ce':
            in_block_comment = False
            continue
        if in_block_comment:
            continue
        if stripped.startswith('#'):
            continue
        in_double = False
        in_single = False
        double_start_col = -1
        single_start_col = -1
        last_comma_idx = -1
        col_idx = 1
        while col_idx <= len(line):
            ch = line[col_idx - 1]
            if in_double:
                if ch == '"':
                    in_double = False
            elif in_single:
                if ch == "'":
                    in_single = False
            else:
                if ch == '"':
                    in_double = True
                    double_start_col = col_idx
                elif ch == "'":
                    in_single = True
                    single_start_col = col_idx
                elif ch == ';':
                    break
                elif ch == '(':
                    paren_stack.append(('(', orig_file, orig_line, col_idx, line))
                elif ch == '[':
                    paren_stack.append(('[', orig_file, orig_line, col_idx, line))
                elif ch == ')':
                    if paren_stack and paren_stack[-1][0] == '(':
                        paren_stack.pop()
                    else:
                        syntax_errors.append(
                            ('error', orig_file, orig_line, col_idx, 'syntax error', line)
                        )
                elif ch == ']':
                    if paren_stack and paren_stack[-1][0] == '[':
                        paren_stack.pop()
                    else:
                        syntax_errors.append(
                            ('error', orig_file, orig_line, col_idx, 'syntax error', line)
                        )
                        syntax_errors.append(
                            ('error', orig_file, orig_line, col_idx, 'Statement cannot be just an expression.', line)
                        )
                elif ch == '{':
                    syntax_errors.append(
                        ('error', orig_file, orig_line, col_idx, 'syntax error (illegal character)', line)
                    )
                    break
                elif ch == '}':
                    syntax_errors.append(
                        ('error', orig_file, orig_line, col_idx, 'syntax error (illegal character)', line)
                    )
                elif ch == ',':
                    if last_comma_idx != -1:
                        between = line[last_comma_idx:col_idx - 1]
                        if not between.strip():
                            syntax_errors.append(
                                ('error', orig_file, orig_line, col_idx, 'syntax error', line)
                            )
                            if not re.match(r'(?i)^\s*func\b', split_code_comment(line)[0]) and not any(item[0] == '(' for item in paren_stack):
                                syntax_errors.append(
                                    ('error', orig_file, orig_line, len(line), 'Statement cannot be just an expression.', line)
                                )
                                syntax_errors.append(
                                    ('error', orig_file, orig_line, len(line), 'Statement cannot be just an expression.', line)
                                )
                    last_comma_idx = col_idx
                elif not ch.isspace():
                    last_comma_idx = -1
            col_idx += 1

        if in_double:
            syntax_errors.append(
                ('error', orig_file, orig_line, double_start_col, 'syntax error (illegal character)', line)
            )
        elif in_single:
            syntax_errors.append(
                ('error', orig_file, orig_line, single_start_col, 'syntax error (illegal character)', line)
            )

    while paren_stack:
        kind, p_file, p_line_num, p_col, p_line = paren_stack.pop()
        if kind == '(':
            syntax_errors.append(
                ('error', p_file, p_line_num, max(1, len(p_line)), 'unbalanced paranthesis expression.', p_line)
            )
        else:
            syntax_errors.append(
                ('error', p_file, p_line_num, p_col + 1, 'syntax error', p_line)
            )
            if ']' in p_line[p_col:]:
                syntax_errors.append(
                    ('error', p_file, p_line_num, max(1, len(p_line)), 'syntax error', p_line)
                )

    # 2. Scoping structure block scanning & undefined checks
    in_block_comment_loop3 = False
    for idx, line in enumerate(lines):
        orig_file, orig_line = line_mappings[idx]
        stripped = line.strip()
        stripped_lower = stripped.lower()
        if stripped_lower == '#comments-start' or stripped_lower == '#cs':
            in_block_comment_loop3 = True
            continue
        if stripped_lower == '#comments-end' or stripped_lower == '#ce':
            in_block_comment_loop3 = False
            continue
        if in_block_comment_loop3:
            continue
        code = split_code_comment(line)[0].strip()
        if not code or code.startswith('#'):
            continue
        last_code = (orig_file, orig_line, line)
        lower = code.lower()
        first_keyword = leading_keyword(code)
        if first_keyword == 'func':
            block_stack.append(('func', orig_file, orig_line, line))
            m_func = re.match(r'(?i)^func\s+(\w+)\s*\(', code)
            if m_func:
                func_name = m_func.group(1)
                func_name_lower = func_name.lower()
                if func_name_lower in defined_funcs:
                    sig_end = line.find(')')
                    col = sig_end + 2 if sig_end != -1 else len(line) + 1
                    syntax_errors.append(
                        ('error', orig_file, orig_line, col, f'{func_name}() already defined.', line)
                    )
                else:
                    defined_funcs[func_name_lower] = (orig_file, orig_line)
            
            # Check for missing/extra commas in parameters list
            m_func_decl = re.match(r'(?i)^\s*func\s+\w+\s*\(([^)]*)\)', code)
            if m_func_decl:
                params_str = m_func_decl.group(1)
                stripped_params = params_str.strip()
                if stripped_params:
                    params_list = split_top_level(params_str, ',')
                    for p_part in params_list:
                        p_stripped = p_part.strip()
                        if not p_stripped:
                            if not any(err[0] == 'error' and err[1] == orig_file and err[2] == orig_line for err in syntax_errors):
                                params_start_idx = line.find('(')
                                col = params_start_idx + 2
                                syntax_errors.append(
                                    ('error', orig_file, orig_line, col, 'syntax error', line)
                                )
                            break
                        
                        lhs = p_stripped
                        if '=' in p_stripped:
                            lhs = p_stripped.split('=', 1)[0].strip()
                        
                        lhs_vars = re.findall(r'\$\w+', lhs)
                        if len(lhs_vars) != 1:
                            lhs_var_matches = list(re.finditer(r'\$\w+', lhs))
                            if len(lhs_var_matches) > 1:
                                part_start = line.find(p_part)
                                col = part_start + lhs_var_matches[1].start() + 1 if part_start >= 0 else line.find('(') + 2
                            else:
                                col = line.find('(') + 2
                            syntax_errors.append(
                                ('error', orig_file, orig_line, col, 'syntax error', line)
                            )
                            break
        elif first_keyword == 'if' and re.match(r'(?i)^if\b.*\bthen$', code) and not re.search(r'(?i)\bthen\s+.+', code):
            block_stack.append(('if', orig_file, orig_line, line))
        elif first_keyword == 'select':
            block_stack.append(('select', orig_file, orig_line, line))
        elif first_keyword == 'switch':
            block_stack.append(('switch', orig_file, orig_line, line))
        elif first_keyword == 'for':
            block_stack.append(('for', orig_file, orig_line, line))
        elif first_keyword == 'while':
            block_stack.append(('while', orig_file, orig_line, line))
        elif first_keyword == 'do':
            block_stack.append(('do', orig_file, orig_line, line))
        elif lower == 'endif':
            for pos in range(len(block_stack) - 1, -1, -1):
                if block_stack[pos][0] == 'if':
                    del block_stack[pos]
                    break
        elif lower == 'endfunc':
            for pos in range(len(block_stack) - 1, -1, -1):
                if block_stack[pos][0] == 'func':
                    del block_stack[pos]
                    break
        elif lower == 'endselect':
            for pos in range(len(block_stack) - 1, -1, -1):
                if block_stack[pos][0] == 'select':
                    del block_stack[pos]
                    break
        elif lower == 'endswitch':
            for pos in range(len(block_stack) - 1, -1, -1):
                if block_stack[pos][0] == 'switch':
                    del block_stack[pos]
                    break
        elif lower == 'next' or lower.startswith('next '):
            for pos in range(len(block_stack) - 1, -1, -1):
                if block_stack[pos][0] == 'for':
                    del block_stack[pos]
                    break
        elif lower == 'wend':
            for pos in range(len(block_stack) - 1, -1, -1):
                if block_stack[pos][0] == 'while':
                    del block_stack[pos]
                    break
        elif lower.startswith('until '):
            for pos in range(len(block_stack) - 1, -1, -1):
                if block_stack[pos][0] == 'do':
                    del block_stack[pos]
                    break

        first_word = re.match(r'(?i)^([a-zA-Z_]\w*)\b', code) if first_keyword in unsupported_bare_functions else None
        if first_word and first_word.group(1).lower() in unsupported_bare_functions:
            func_name = first_word.group(1)
            col = 1 if func_name.lower() == 'endtry' else first_word.end(1) + 1
            syntax_errors.append(
                ('error', orig_file, orig_line, col, f'{func_name}(): undefined function.', line)
            )

        # Scan for function calls and macro references inside the code
        code_raw = split_code_comment(line)[0]
        stripped_code = ""
        in_double = False
        in_single = False
        for ch in code_raw:
            if in_double:
                if ch == '"':
                    in_double = False
                stripped_code += " "
            elif in_single:
                if ch == "'":
                    in_single = False
                stripped_code += " "
            else:
                if ch == '"':
                    in_double = True
                    stripped_code += " "
                elif ch == "'":
                    in_single = True
                    stripped_code += " "
                else:
                    stripped_code += ch

        for m in re.finditer(r'\b([a-zA-Z_]\w*)\s*\(', stripped_code):
            func_name = m.group(1)
            func_name_lower = func_name.lower()
            if func_name_lower in keywords:
                continue
            
            # Check preceding character to skip variable/object method calls (like $func() or $obj.method())
            pre_text = stripped_code[:m.start()].rstrip()
            if pre_text and pre_text[-1] in ('$', '.'):
                continue
            if pre_text.lower().endswith('func'):
                continue
            
            paren_start = m.end() - 1
            paren_end = -1
            paren_depth = 1
            for j in range(paren_start + 1, len(code_raw)):
                if code_raw[j] == '(':
                    paren_depth += 1
                elif code_raw[j] == ')':
                    paren_depth -= 1
                    if paren_depth == 0:
                        paren_end = j
                        break

            col = (paren_end + 1) if paren_end != -1 else (m.start() + len(func_name) + 2)

            if func_name_lower not in defined_udfs and func_name_lower not in builtins:
                syntax_errors.append(
                    ('error', orig_file, orig_line, col, f'{func_name}(): undefined function.', line)
                )
            else:
                # Check parameters count boundaries
                if paren_end != -1:
                    args_str = code_raw[paren_start + 1:paren_end]
                else:
                    args_str = code_raw[paren_start + 1:]
                
                stripped_args = args_str.strip()
                if not stripped_args:
                    arg_count = 0
                else:
                    arg_count = len(split_top_level(args_str, ','))

                call_has_trailing_comma = False
                if stripped_args:
                    args_parts = split_top_level(args_str, ',')
                    if any(not part.strip() for part in args_parts):
                        # Empty argument slots are syntax errors. A trailing empty slot is
                        # not returned by split_top_level(), so it is handled below.
                        pass
                    if args_str.rstrip().endswith(','):
                        call_has_trailing_comma = True
                        syntax_errors.append(
                            ('error', orig_file, orig_line, paren_end + 1 if paren_end != -1 else len(line), 'syntax error', line)
                        )

                    args_str_no_strings = replace_strings_with_placeholder(args_str)
                    missing_comma_match = re.search(
                        r'(?i)(?:\d+(?:\.\d+)?|\$\w+)\s+(?:\d+(?:\.\d+)?|\$\w+)',
                        args_str_no_strings,
                    )
                    if missing_comma_match:
                        syntax_errors.append(
                            ('error', orig_file, orig_line, paren_start + missing_comma_match.end() + 2, 'syntax error', line)
                        )
                
                if func_name_lower in defined_udfs:
                    min_args, max_args, def_file, def_line, def_col, def_source = defined_udfs[func_name_lower]
                else:
                    min_args, max_args = builtins[func_name_lower]
                
                if not call_has_trailing_comma and (arg_count < min_args or arg_count > max_args):
                    if func_name_lower in builtins:
                        syntax_errors.append(
                            ('error', orig_file, orig_line, col, f'{func_name}() [built-in] called with wrong number of args.', line)
                        )
                    else:
                        syntax_errors.append(
                            ('error', orig_file, orig_line, col, f'{func_name}() called with wrong number of args.', line)
                        )
                        syntax_errors.append(
                            ('REF', def_file, def_line, def_col, f'definition of {func_name}().', def_source)
                        )

        # Scan for macro references
        for m in re.finditer(r'@([a-zA-Z_]\w*)', stripped_code):
            macro_full = m.group(0)
            macro_lower = macro_full.lower()
            if macro_lower not in valid_macros:
                col = m.start() + 1
                next_part = stripped_code[m.end():]
                m_next = re.search(r'\S', next_part)
                if m_next:
                    col = m.end() + m_next.start() + 1
                syntax_errors.append(
                    ('error', orig_file, orig_line, col, 'undefined macro.', line)
                )

    if syntax_errors:
        return syntax_errors

    if not block_stack or not last_code:
        return []

    last_kind, start_file, start_ln, start_line = block_stack[-1]
    last_file, last_ln, last_line = last_code
    if last_kind == 'if':
        last_col = max(1, len(last_line) + 1)
        start_col = max(1, len(start_line) + 1)
        return [
            ('error', last_file, last_ln, last_col, 'missing EndIf.', last_line),
            ('REF', start_file, start_ln, start_col, 'missing EndIf.', start_line),
        ]
    block_missing = {
        'select': ('EndSelect', start_line, max(1, len(start_line) + 1)),
        'switch': ('EndSwitch', start_line, max(1, len(start_line) + 1)),
        'for': ('Next', re.sub(r'(?i)\s+to\s+.+$', ' To', start_line), max(1, len(re.sub(r'(?i)\s+to\s+.+$', ' To', start_line)) - 1)),
        'while': ('Wend', re.match(r'(?i)^\s*while\b', start_line).group(0) if re.match(r'(?i)^\s*while\b', start_line) else start_line, 1),
        'do': ('Until <expr>', re.match(r'(?i)^\s*do\b', start_line).group(0) if re.match(r'(?i)^\s*do\b', start_line) else start_line, 1),
    }
    if last_kind in block_missing:
        missing_text, ref_line, explicit_col = block_missing[last_kind]
        last_col = max(1, len(last_line) + 1)
        ref_col = explicit_col if explicit_col is not None else max(1, len(ref_line) + 1)
        return [
            ('error', last_file, last_ln, last_col, f'missing {missing_text}.', last_line),
            ('REF', start_file, start_ln, ref_col, f'missing {missing_text}.', ref_line),
        ]
    if last_kind == 'func':
        last_col = max(1, len(last_line) + 1)
        return [
            ('error', last_file, last_ln, last_col, 'syntax error', last_line),
            ('error', last_file, last_ln, last_col, 'Statement cannot be just an expression.', last_line),
        ]
    return []

def print_legacy_syntax_errors(file_path, diagnostics):
    """
    @brief Prints a list of syntax diagnostics formatted in Au3Check's original three-line format.
    @param file_path The path to the main file.
    @param diagnostics List of diagnostics collected by collect_legacy_syntax_errors.
    @author Harald Frank
    """
    error_count = sum(1 for level, *_ in diagnostics if level == 'error')
    for diag in diagnostics:
        if len(diag) == 6:
            level, file_p, line, col, desc, source_line = diag
        else:
            level, line, col, desc, source_line = diag
            file_p = file_path
        
        # Format file_p to relative path if possible to match original Au3Check output format
        try:
            rel = os.path.relpath(file_p)
            if not rel.startswith('..'):
                file_p = rel
        except Exception:
            pass
        
        print(f'"{file_p}"({line},{col}) : {level}: {desc}')
        print(source_line)
        print(legacy_marker_line(col))
    
    # Format the summary file_path as well
    try:
        rel = os.path.relpath(file_path)
        if not rel.startswith('..'):
            file_path = rel
    except Exception:
        pass
    print(f"{file_path} - {error_count} error(s), 0 warning(s)")

def parse_legacy_verbose_flags(v_args):
    """
    @brief Parses a list of verbose option parameters (e.g. ['2', '-3']).
    @param v_args List of raw verbose flag argument values.
    @return Set of active integer verbose levels.
    @author Harald Frank
    """
    verbose_enabled = set()
    for v_opt in v_args:
        try:
            if str(v_opt).startswith('-'):
                verbose_enabled.discard(int(str(v_opt)[1:]))
            else:
                verbose_enabled.add(int(v_opt))
        except ValueError:
            pass
    return verbose_enabled

def legacy_v2_token_lines(file_path):
    """
    @brief Scans a source file and emits a list of token mappings in Au3Check's legacy -v 2 format.
    @param file_path The target source file.
    @return List of formatted token output strings.
    @author Harald Frank
    """
    keyword_tokens = {
        'global': 274,
        'local': 273,
        'func': 303,
        'return': 305,
        'endfunc': 306,
    }
    symbol_tokens = {'=': 61, '(': 40, ')': 41, '+': 43, ',': 44}
    token_rx = re.compile(r'\$\w+|[A-Za-z_]\w*|\d+|[=()+,]')
    try:
        lines = read_autoit_lines(file_path)
    except AutoItSourceError:
        return []

    out = []
    last_ln = 1
    last_col = 1
    for ln, line in enumerate(lines, start=1):
        last_ln = ln
        for match in token_rx.finditer(line):
            token = match.group(0)
            lower = token.lower()
            if lower in keyword_tokens:
                code = keyword_tokens[lower]
            elif token.startswith('$'):
                code = 260
            elif token.isdigit():
                code = 259
            elif token in symbol_tokens:
                code = symbol_tokens[token]
            else:
                code = 262
            out.append(f'"{file_path}"({ln},{match.start() + 1}): [{code}] {token}')
        last_col = len(line) + 1
        out.append(f'"{file_path}"({ln},{last_col}): [10] \n')
    out.append(f'"{file_path}"({last_ln},{last_col}): [10] ')
    out.append(f'"{file_path}"({last_ln},{last_col}): [0] ')
    return out

def legacy_v3_unref_lines(file_path):
    """
    @brief Generates list of unreferenced global variable declarations and UDF lines in Au3Check's legacy -v 3 format.
    @param file_path The source file.
    @return List of formatted unreferenced output strings.
    @author Harald Frank
    """
    try:
        lines = read_autoit_lines(file_path)
    except AutoItSourceError:
        return []

    out = []
    funcs = []
    current_func = None
    for ln, line in enumerate(lines, start=1):
        code = split_code_comment(line)[0].strip()
        m_global = re.match(r'(?i)^Global\s+(?:Const\s+)?(\$\w+)', code)
        if m_global:
            out.append(f'{file_path}({ln},1) : UNREFED({ln}):\t{m_global.group(1)}')
        m_func = re.match(r'(?i)^Func\s+(\w+)\s*\(', code)
        if m_func:
            current_func = [m_func.group(1), ln, ln]
        elif re.match(r'(?i)^EndFunc\b', code) and current_func:
            current_func[2] = ln
            funcs.append(tuple(current_func))
            current_func = None
    for name, start_ln, end_ln in funcs:
        out.append(f'{file_path}({start_ln},1) : UNREFED({end_ln}):\t{name}')
    return out


def main():
    """
    @brief Main executable entry point.
    @details Parses command line arguments, handles preprocessing, executes syntax checks, runs static scoping analysis, and outputs the legacy-compatible format or JSON reports.
    @author Harald Frank
    """
    sys.argv = preprocess_sys_argv(sys.argv)
    if len(sys.argv) == 1 or "-?" in sys.argv[1:]:
        print_au3check_usage()
        sys.exit(3)
    
    parser = argparse.ArgumentParser(description="AutoIt Recursive Preprocessor & Block Scoping Diagnostics Tool")
    parser.add_argument("main_file", help="Path to the main AutoIt source file (.au3)")
    parser.add_argument("--include-dirs", help="Comma-separated list of custom user include directories", default="")
    parser.add_argument("--no-auto-include-discovery", action="store_true", help="Disable automatic discovery of project-local Include directories")
    parser.add_argument("--out-dir", help="Path to output directory (default: temp_scoping_analysis/ relative to main file)", default="")
    parser.add_argument("--skip-system-includes", action="store_true", help="Do not report warnings originating from the standard AutoIt include directory")
    parser.add_argument("--enable-experimental-checks", action="store_true", help="Enable additional semantic inspections that are still being hardened against false positives")
    parser.add_argument("--enable-system-dead-stores", action="store_true", help="When experimental checks are enabled, collect Dead Store diagnostics from standard AutoIt include files into a separate report section")
    parser.add_argument("--json-out", action="store_true", help="Output all diagnostics or line lookup results as a single uniform JSON array to stdout")
    parser.add_argument("--lookup-runtime-line", type=int, help="Look up a 1-based preprocessed runtime line number to find its original source file and line")
    parser.add_argument("--compiled", action="store_true", help="Look up a line number under compiled runtime rules (stripping comments/empty lines/directives)")
    
    # Legacy Au3Check options
    parser.add_argument("-q", action="store_true", help="Quiet mode (only errors/warnings)")
    parser.add_argument("-d", action="store_true", help="Enforce MustDeclareVars checks")
    parser.add_argument("-w", action="append", default=[], help="Warning flags (e.g. 3, -3, 7)")
    parser.add_argument("-v", action="append", default=[], help="Verbose flags (e.g. 1, 3)")
    parser.add_argument("-I", action="append", default=[], help="Additional search directories for includes")
 
    args = parser.parse_args()
    is_legacy_mode = bool(args.q or args.d or args.w or args.v or args.I)
    if args.json_out or args.lookup_runtime_line:
        # Suppress normal printed progress logs when JSON output is requested
        is_legacy_mode = True
 
    # Overwrite built-in print to respect quiet mode and JSON output mode
    import builtins
    original_print = builtins.print
    def print(*args_vals, **kwargs):
        if args.json_out or args.lookup_runtime_line:
            return
        if (not is_legacy_mode and not args.q) or kwargs.get('file') == sys.stderr:
            original_print(*args_vals, **kwargs)
 
    if is_legacy_mode and not args.q and not args.json_out and not args.lookup_runtime_line:
        original_print(get_original_au3check_header())
        original_print("")

    if not os.path.exists(args.main_file):
        if is_legacy_mode:
            original_print(f"Error : couldn't open input file: {args.main_file}")
        else:
            print(f"Error: main source file not found: {args.main_file}", file=sys.stderr)
        sys.exit(3)

    try:
        read_autoit_source(args.main_file)
    except AutoItSourceError as exc:
        if args.json_out:
            import json
            original_print(json.dumps({
                "summary": {"total": 1, "errors": 1, "warnings": 0},
                "diagnostics": [{
                    "file": os.path.abspath(args.main_file).replace('\\', '/'),
                    "line": 1,
                    "column": 1,
                    "severity": "error",
                    "type": "Source Read Error",
                    "func": "<global>",
                    "var": "",
                    "desc": f"Cannot analyze source file '{args.main_file}': {exc}",
                }],
            }))
        elif is_legacy_mode:
            original_print(f"Error : couldn't read input file: {args.main_file}: {exc}")
        else:
            original_print(f"Error: cannot analyze source file '{args.main_file}': {exc}", file=sys.stderr)
        sys.exit(2)



    early_verbose_enabled = parse_legacy_verbose_flags(args.v)
    if is_legacy_mode and 2 in early_verbose_enabled:
        for out_line in legacy_v2_token_lines(args.main_file):
            original_print(out_line)
        sys.exit(0)
    if is_legacy_mode and 3 in early_verbose_enabled:
        for out_line in legacy_v3_unref_lines(args.main_file):
            original_print(out_line)
        original_print("")
        sys.exit(0)

    # Setup output directory
    main_dir = os.path.dirname(os.path.abspath(args.main_file))
    out_dir = args.out_dir
    if not out_dir:
        import tempfile
        import atexit
        import shutil
        out_dir = tempfile.mkdtemp(prefix="au3mythos_")
        
        def cleanup_temp_dir():
            shutil.rmtree(out_dir, ignore_errors=True)
            
        atexit.register(cleanup_temp_dir)
    else:
        os.makedirs(out_dir, exist_ok=True)
    print(f"Initializing AutoIt Scoping Analyzer...")
    print(f"Main Source File: {args.main_file}")
    print(f"Output Directory: {out_dir}")

    # Process Include Paths
    include_paths = []
    if args.include_dirs:
        for d in args.include_dirs.split(','):
            d = d.strip()
            if os.path.exists(d):
                add_unique_path(include_paths, d)
            else:
                print(f"Warning: Include directory not found: {d}", file=sys.stderr)
    for d in args.I:
        if os.path.exists(d):
            add_unique_path(include_paths, d)
        else:
            print(f"Warning: Include directory not found: {d}", file=sys.stderr)
    auto_include_paths = []
    if not args.no_auto_include_discovery:
        auto_include_paths = discover_include_dirs(args.main_file)
        for d in auto_include_paths:
            add_unique_path(include_paths, d)
    if auto_include_paths:
        print(f"Auto-discovered {len(auto_include_paths)} include directories.")

    # Parse legacy warning configuration
    warnings_enabled = {
        1: True, # already included file
        2: True, # missing #comments-end
        3: False, # already declared var
        4: False, # local var used in global scope
        5: False, # local var declared but not used
        6: False, # warn when using Dim
        7: is_legacy_mode, # Au3Check enables -w7 by default; normal analyzer mode keeps the historical baseline
        '_legacy_mode': is_legacy_mode,
    }
    if args.w:
        for w_opt in args.w:
            try:
                if w_opt.startswith('-'):
                    num = int(w_opt[1:])
                    warnings_enabled[num] = False
                else:
                    num = int(w_opt)
                    warnings_enabled[num] = True
            except ValueError:
                pass

    # 1. Run Preprocessor
    print(f"Step 1: Running preprocessor (resolving includes and line mappings)...")
    preprocessor = AutoItPreprocessor(include_dirs=include_paths)
    preprocessor.warnings_config = warnings_enabled
    preprocessor.preprocess(args.main_file)
    verbose_enabled = set()
    for v_opt in args.v:
        try:
            if v_opt.startswith('-'):
                verbose_enabled.discard(int(v_opt[1:]))
            else:
                verbose_enabled.add(int(v_opt))
        except ValueError:
            pass
    if is_legacy_mode and 1 in verbose_enabled:
        search_paths = include_paths + [AUTOIT_STD_INCLUDE]
        original_print(f"Include search-path : {';'.join(search_paths)}")
        for including_file, include_ln, resolved_file in preprocessor.include_events:
            original_print(f'"{including_file}"({include_ln},1) : INCLUDE: "{resolved_file}"')
    print(f"Resolved include tree. Total raw lines: {len(preprocessor.raw_lines)}")

    # 2. Merge Continuations
    print(f"Step 2: Merging line continuations programmatically...")
    merged_lines, line_mappings = preprocessor.merge_continuations()
    print(f"Merged line count: {len(merged_lines)}")
 
    if args.lookup_runtime_line is not None:
        target_line = args.lookup_runtime_line
        
        # Build statement mappings if compiled mode is selected
        active_mappings = line_mappings
        if args.compiled:
            active_mappings = []
            in_comments = False
            for i, line in enumerate(merged_lines):
                stripped = line.strip()
                s_lower = stripped.lower()
                if s_lower in ('#comments-start', '#cs'):
                    in_comments = True
                    continue
                if s_lower in ('#comments-end', '#ce'):
                    in_comments = False
                    continue
                if in_comments:
                    continue
                if not stripped: # empty line
                    continue
                if stripped.startswith(';'): # comment line
                    continue
                active_mappings.append(line_mappings[i])
                
        if target_line < 1 or target_line > len(active_mappings):
            if args.json_out:
                import json
                original_print(json.dumps({"error": f"Line number {target_line} is out of range of preprocessed lines (1-{len(active_mappings)})"}))
            else:
                original_print(f"Error: Line number {target_line} is out of range (1-{len(active_mappings)})", file=sys.stderr)
            sys.exit(3)
            
        file_path, original_line_num = active_mappings[target_line - 1]
        
        # Read the line of code from the original file
        original_line_text = ""
        try:
            orig_lines = read_autoit_lines(file_path)
            if 1 <= original_line_num <= len(orig_lines):
                original_line_text = orig_lines[original_line_num - 1].strip()
        except AutoItSourceError as e:
            original_line_text = f"<Could not read source: {e}>"
            
        if args.json_out:
            import json
            original_print(json.dumps({
                "preprocessed_line": target_line,
                "file": os.path.abspath(file_path).replace("\\", "/"),
                "line": original_line_num,
                "code": original_line_text
            }))
        else:
            original_print(f"Preprocessed Line: {target_line}")
            original_print(f"Original File: {os.path.abspath(file_path)}")
            original_print(f"Original Line: {original_line_num}")
            original_print(f"Code: {original_line_text}")
            
        sys.exit(0)

    if is_legacy_mode:
        syntax_diagnostics = collect_legacy_syntax_errors(args.main_file, merged_lines, line_mappings)
        if syntax_diagnostics:
            print_legacy_syntax_errors(args.main_file, syntax_diagnostics)
            sys.exit(2)

    # Write preprocessed source
    preprocessed_source_file = os.path.join(out_dir, "preprocessed_source.au3")
    with open(preprocessed_source_file, 'w', encoding='utf-8') as f:
        f.writelines(merged_lines)
    print(f"Saved merged flat source tree to: {preprocessed_source_file}")

    analyzer = AutoItScopingAnalyzer(
        experimental_checks=args.enable_experimental_checks,
        warnings_config=warnings_enabled,
        system_dead_stores=args.enable_system_dead_stores,
    )
    analyzer.warnings.extend(preprocessor.warnings)

    # 3. Scan Global Variables (tracking is_const status & dimensions) and lightweight global facts
    print(f"Step 3: Indexing global variable declarations...")
    global_vars = {}
    global_decl_locs = {}
    for var in load_builtin_vars():
        global_vars[var] = (False, None)
        global_decl_locs[var] = 1
    global_vars["$cmdlineraw"] = (False, "scalar")
    global_decl_locs["$cmdlineraw"] = 1
    global_decl_rx = re.compile(r'(?i)^\s*(Global|Dim)\s+(?:Const\s+)?(.+)')
    global_local_decl_rx = re.compile(r'(?i)^\s*Local\s+(?:Const\s+)?(.+)')
    global_enum_rx = re.compile(r'(?i)^\s*Global\s+Enum\s+(.+)')
    global_const_literal_rx = re.compile(r'(?i)^\s*Global\s+Const\s+(\$\w+)\s*=\s*([^,;]+)')
    conditional_global_rx = re.compile(
        r'(?i)^\s*If\s+Not\s+IsDeclared\s*\(\s*(["\'])(\$?\w+)\1\s*\)\s+Then\s+(Global\s+.+)$'
    )
    enum_values_by_file = {}
    global_numeric_consts = set()
    top_level_switches = []
    
    in_func = False
    current_func = ""
    current_func_returns = []
    current_func_error_passthrough_params = set()
    current_func_error_passthrough_vars = set()
    current_func_has_error_value_passthrough_return = False
    current_func_has_setextended_return = False
    current_func_return_constants = set()

    def record_function_return(return_expr):
        nonlocal current_func_has_error_value_passthrough_return, current_func_has_setextended_return
        m_seterror = re.match(r'(?i)^\s*SetError\s*\((.*)\)', return_expr)
        if m_seterror:
            seterror_args = split_top_level(m_seterror.group(1), ',')
            first_arg = seterror_args[0].strip().lower() if seterror_args else ''
            second_arg = seterror_args[1].strip().lower() if len(seterror_args) > 1 else ''
            if first_arg == '@error' and second_arg == '@extended' and len(seterror_args) >= 3:
                current_func_has_error_value_passthrough_return = True
            current_func_returns.append(first_arg not in current_func_error_passthrough_vars)
        else:
            if re.match(r'(?i)^\s*SetExtended\s*\(', return_expr):
                current_func_has_setextended_return = True
            m_const_return = re.match(r'^\s*(\$\w+)\s*$', return_expr)
            if m_const_return:
                return_var = m_const_return.group(1).lower()
                if return_var in global_vars and global_vars[return_var][0]:
                    current_func_return_constants.add(return_var)
            current_func_returns.append(False)

    for idx, line in enumerate(merged_lines):
        line_num = idx + 1
        stripped = split_code_comment(line)[0].strip()
        stripped_lower = stripped.lower()
        first_keyword = leading_keyword(stripped)
        if stripped.startswith(';'):
            continue
        func_sig = analyzer.parse_func_signature(stripped)
        if func_sig:
            in_func = True
            current_func = func_sig[0].lower()
            current_func_returns = []
            current_func_error_passthrough_params = set()
            current_func_error_passthrough_vars = set()
            current_func_has_error_value_passthrough_return = False
            current_func_has_setextended_return = False
            current_func_return_constants = set()
            for param_index, param_part in enumerate(split_top_level(func_sig[1], ',')):
                if re.search(r'(?i)\bByRef\b', param_part):
                    analyzer.byref_param_positions.setdefault(current_func, set()).add(param_index)
                if '@error' not in param_part.lower():
                    continue
                m_param = re.search(r'(\$\w+)', param_part)
                if m_param:
                    current_func_error_passthrough_params.add(m_param.group(1).lower())
            current_func_error_passthrough_vars = set(current_func_error_passthrough_params)
            continue
        if first_keyword == 'endfunc':
            if current_func and current_func_returns and all(current_func_returns):
                analyzer.seterror_return_funcs.add(current_func)
                if current_func_has_error_value_passthrough_return:
                    analyzer.seterror_value_passthrough_funcs.add(current_func)
            if current_func and current_func_has_setextended_return:
                analyzer.setextended_return_funcs.add(current_func)
            if current_func and current_func_return_constants:
                analyzer.function_return_constants[current_func] = set(current_func_return_constants)
            in_func = False
            current_func = ""
            current_func_returns = []
            current_func_error_passthrough_params = set()
            current_func_error_passthrough_vars = set()
            current_func_has_error_value_passthrough_return = False
            current_func_has_setextended_return = False
            current_func_return_constants = set()
            continue
        if in_func:
            alias_line = stripped
            if first_keyword in {'local', 'global', 'dim', 'static'}:
                alias_line = re.sub(r'(?i)^\s*(Local|Global|Dim|Static)\s+(?:Const\s+)?', '', stripped)
            m_alias = re.match(r'(?i)^\s*(\$\w+)\s*=\s*(\$\w+)\s*$', alias_line) if alias_line.lstrip().startswith('$') else None
            if m_alias and m_alias.group(2).lower() in current_func_error_passthrough_vars:
                current_func_error_passthrough_vars.add(m_alias.group(1).lower())

            m_return = re.match(r'(?i)^\s*Return\b\s*(.*)', stripped) if first_keyword == 'return' else None
            if m_return:
                record_function_return(m_return.group(1))
            else:
                m_inline_return = re.search(r'(?i)\bThen\s+Return\b\s*(.*)', stripped) if 'then' in stripped_lower and 'return' in stripped_lower else None
                if m_inline_return:
                    record_function_return(m_inline_return.group(1))
            continue
            
        if not in_func:
            orig_file, orig_ln = line_mappings[line_num - 1]
            enum_values = enum_values_by_file.setdefault(os.path.abspath(orig_file).lower(), {})

            if first_keyword == 'switch':
                top_level_switches.append({})
            elif first_keyword == 'endswitch':
                if top_level_switches:
                    top_level_switches.pop()
            elif top_level_switches and first_keyword == 'case' and leading_keyword(stripped[4:]) != 'else':
                case_text = re.sub(r'(?i)^\s*Case\s+', '', stripped)
                seen_cases = top_level_switches[-1]
                clause_tokens = set()
                for case_part in split_top_level(case_text, ','):
                    token = normalize_simple_case_token(case_part)
                    if not token or token in clause_tokens:
                        continue
                    clause_tokens.add(token)
                    if token in seen_cases and args.enable_experimental_checks:
                        first_line = seen_cases[token]
                        analyzer.warnings.append({
                            'func': '<global>',
                            'var': split_code_comment(case_part)[0].strip().lower(),
                            'type': 'Duplicate Case Value',
                            'desc': f"Duplicate Switch Case value '{split_code_comment(case_part)[0].strip()}' at line {line_num}; AutoIt Select/Switch does not fall through, so the earlier Case at line {first_line} wins.",
                            'file': orig_file,
                            'line': orig_ln,
                        })
                    else:
                        seen_cases[token] = line_num

            m_global_local = global_local_decl_rx.match(stripped)
            if m_global_local and warnings_enabled.get(4, False):
                vars_part = split_code_comment(m_global_local.group(1))[0]
                for part in analyzer.split_declaration_parts(vars_part):
                    var_lower, _ = analyzer.parse_array_dimensions(split_assignment_left(part))
                    if var_lower:
                        analyzer.warnings.append({
                            'func': '<global>',
                            'var': var_lower,
                            'type': 'Local In Global Scope',
                            'desc': f"Local variable '{var_lower}' is declared in global scope.",
                            'file': orig_file,
                            'line': orig_ln
                        })
            m_enum = global_enum_rx.match(stripped)
            if m_enum:
                enum_part = split_code_comment(m_enum.group(1))[0]
                enum_part = re.sub(r'(?i)^\s*Step\s+[-+]?\d+\s+', '', enum_part)
                next_value = 0
                for part in analyzer.split_declaration_parts(enum_part):
                    part = part.strip()
                    if not part:
                        continue
                    left = split_assignment_left(part)
                    m_var = re.search(r'(\$\w+)', left)
                    if m_var:
                        var_lower_val = m_var.group(1).lower()
                        register_global_var(global_vars, var_lower_val, True, "scalar")
                        global_decl_locs[var_lower_val] = line_num
                        value_parts = split_top_level(part, '=')
                        if len(value_parts) > 1 and re.match(r'\s*-?\d+\s*$', value_parts[1]):
                            next_value = int(value_parts[1].strip())
                        enum_values.setdefault(next_value, m_var.group(1).lower())
                        next_value += 1
                continue

            conditional_global = conditional_global_rx.match(stripped)
            global_declaration_text = conditional_global.group(3) if conditional_global else stripped
            m_decl = global_decl_rx.match(global_declaration_text)
            if m_decl:
                scope = m_decl.group(1).lower()
                is_const = declaration_has_const(stripped)
                vars_part = split_code_comment(m_decl.group(2))[0]
                parts = analyzer.split_declaration_parts(vars_part)
                for part in parts:
                    part_stripped = re.sub(r'(?i)^\s*(Static|Const)\s+', '', part)
                    left = split_assignment_left(part_stripped)
                    var_lower, dims = analyzer.parse_array_dimensions(left)
                    if var_lower:
                        if conditional_global:
                            declared_name = '$' + conditional_global.group(2).lstrip('$').lower()
                            if var_lower != declared_name:
                                continue
                        if warnings_enabled.get(3, False) and not conditional_global and scope != 'dim' and dims == "scalar" and var_lower in global_vars:
                            first_decl_line = global_decl_locs.get(var_lower)
                            details_val = None
                            if first_decl_line is not None:
                                orig_decl_file, orig_decl_ln = line_mappings[first_decl_line - 1]
                                details_val = {
                                    'original_declaration': {
                                        'file': os.path.abspath(orig_decl_file).replace('\\', '/'),
                                        'line': orig_decl_ln
                                    }
                                }
                            analyzer.warnings.append({
                                'func': '<global>',
                                'var': var_lower,
                                'type': 'Duplicate Declaration',
                                'desc': f"Global variable '{var_lower}' is already declared.",
                                'file': orig_file,
                                'line': orig_ln,
                                'details': details_val
                            })
                        if warnings_enabled.get(6, False) and scope == 'dim':
                            analyzer.warnings.append({
                                'func': '<global>',
                                'var': var_lower,
                                'type': 'Deprecated Dim Use',
                                'desc': f"Dim usage is deprecated; use Local or Global instead for '{var_lower}'.",
                                'file': orig_file,
                                'line': orig_ln
                            })
                        register_global_var(global_vars, var_lower, is_const, dims)
                        if var_lower not in global_decl_locs:
                            global_decl_locs[var_lower] = line_num
                m_const_lit = global_const_literal_rx.match(stripped)
                if m_const_lit and is_numeric_literal(m_const_lit.group(2)):
                    const_var = m_const_lit.group(1).lower()
                    const_value = int(m_const_lit.group(2), 0)
                    global_numeric_consts.add(const_var)
                    if args.enable_experimental_checks and const_value in enum_values and enum_values[const_value] != const_var and 'alias' in const_var:
                        analyzer.warnings.append({
                            'func': '<global>',
                            'var': const_var,
                            'type': 'Enum Value Collision',
                            'desc': f"Constant '{const_var}' reuses enum value {const_value} already assigned to '{enum_values[const_value]}'.",
                            'file': orig_file,
                            'line': orig_ln
                        })
    print(f"Indexed {len(global_vars)} global variables.")

    # 4. Analyze Scoping & Variable Definitions
    print(f"Step 4: Executing block scoping parser...")
    
    in_func = False
    func_name = ""
    func_params = ""
    func_start_line = 0
    func_lines = []

    for idx, line in enumerate(merged_lines):
        line_num = idx + 1
        stripped = split_code_comment(line)[0].strip()
        
        if stripped.startswith(';'):
            continue
            
        func_sig = analyzer.parse_func_signature(stripped)
        if func_sig:
            in_func = True
            func_name = func_sig[0]
            func_params = func_sig[1]
            func_start_line = line_num
            func_lines = []
            continue
            
        if in_func and leading_keyword(stripped) == 'endfunc':
            analyzer.analyze_function(func_name, func_params, func_start_line, func_lines, line_mappings, global_vars, global_numeric_consts)
            in_func = False
            continue
            
        if in_func:
            func_lines.append((line_num, line))

    # 5. Generate Report
    report_file = os.path.join(out_dir, "scoping_report.md")
    
    # Filter workspace, external includes, and system includes
    main_dir_abs = os.path.abspath(main_dir).lower() + os.sep.lower()
    std_include_abs = os.path.abspath(AUTOIT_STD_INCLUDE).lower() + os.sep.lower()
    
    workspace_warnings = []
    external_warnings = []
    system_warnings = []
    system_dead_store_warnings = []
    skipped_system_warnings = []
    
    for w in analyzer.warnings:
        file_abs = os.path.abspath(w['file']).lower()
        if file_abs.startswith(main_dir_abs) or file_abs == os.path.abspath(args.main_file).lower():
            workspace_warnings.append(w)
        elif file_abs.startswith(std_include_abs):
            if w['type'] == 'Dead Store' and args.enable_system_dead_stores:
                system_dead_store_warnings.append(w)
            elif args.skip_system_includes:
                skipped_system_warnings.append(w)
            else:
                system_warnings.append(w)
        else:
            external_warnings.append(w)
            
    # Sort each list by file name and line number
    workspace_warnings.sort(key=lambda x: (x['file'].lower(), x['line']))
    external_warnings.sort(key=lambda x: (x['file'].lower(), x['line']))
    system_warnings.sort(key=lambda x: (x['file'].lower(), x['line']))
    system_dead_store_warnings.sort(key=lambda x: (x['file'].lower(), x['line']))

    print(f"Analysis completed: Found {len(workspace_warnings)} workspace warnings, {len(external_warnings)} external include warnings, and {len(system_warnings)} system include warnings.")
    if system_dead_store_warnings:
        print(f"Collected {len(system_dead_store_warnings)} experimental system include Dead Store diagnostics in a separate report section.")
    if skipped_system_warnings:
        print(f"Skipped {len(skipped_system_warnings)} system include warnings due to --skip-system-includes.")

    import datetime
    calling_cmd = f"python {os.path.basename(sys.argv[0])} {args.main_file}"
    if args.include_dirs:
        calling_cmd += f" --include-dirs \"{args.include_dirs}\""
    if args.out_dir:
        calling_cmd += f" --out-dir \"{args.out_dir}\""
    if args.skip_system_includes:
        calling_cmd += " --skip-system-includes"
    if args.enable_experimental_checks:
        calling_cmd += " --enable-experimental-checks"
    if args.enable_system_dead_stores:
        calling_cmd += " --enable-system-dead-stores"
    if args.no_auto_include_discovery:
        calling_cmd += " --no-auto-include-discovery"
    for inc_dir in args.I:
        calling_cmd += f" -I \"{inc_dir}\""

    explicit_include_paths = []
    if args.include_dirs:
        explicit_include_paths = [os.path.abspath(d.strip()) for d in args.include_dirs.split(',') if d.strip() and os.path.exists(d.strip())]
    effective_include_dirs = ','.join(include_paths) if include_paths else 'None'
    explicit_include_dirs = ','.join(explicit_include_paths) if explicit_include_paths else 'None'
    auto_include_dirs = ','.join(auto_include_paths) if auto_include_paths else 'None'

    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("# AutoIt Scoping Analysis Report\n\n")
        f.write("## Execution Metadata\n")
        f.write(f"* **Generated At**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"* **Calling Command**: `{calling_cmd}`\n")
        f.write(f"* **Target Main File**: [{os.path.basename(args.main_file)}](file:///{os.path.abspath(args.main_file).replace('\\', '/')})\n")
        f.write(f"* **Explicit Include Directories**: `{explicit_include_dirs}`\n")
        f.write(f"* **Auto-discovered Include Directories**: `{auto_include_dirs}`\n")
        f.write(f"* **Effective Include Directories**: `{effective_include_dirs}`\n")
        f.write(f"* **System Include Analysis**: `{'Skipped in report' if args.skip_system_includes else 'Enabled'}`\n")
        f.write(f"* **Output Directory**: `{os.path.abspath(out_dir).replace('\\', '/')}`\n")
        f.write(f"* **Preprocessed Output**: [preprocessed_source.au3](file:///{preprocessed_source_file.replace('\\', '/')})\n\n")
        
        f.write("## Summary\n\n")
        f.write(f"* **Workspace Warnings (Action Required)**: {len(workspace_warnings)}\n")
        f.write(f"* **External Include Warnings**: {len(external_warnings)}\n")
        f.write(f"* **System Include Warnings**: {len(system_warnings)}\n")
        if args.enable_system_dead_stores:
            f.write(f"* **Experimental System Include Dead Stores**: {len(system_dead_store_warnings)}\n")
        if args.skip_system_includes:
            f.write(f"* **Skipped System Include Warnings**: {len(skipped_system_warnings)}\n")
        f.write(f"* **Total Reported Warnings**: {len(workspace_warnings) + len(external_warnings) + len(system_warnings)}\n\n")
        
        f.write("## Workspace Warnings\n\n")
        if workspace_warnings:
            f.write("| Function | File & Line | Variable | Warning Type | Description |\n")
            f.write("| --- | --- | --- | --- | --- |\n")
            for w in workspace_warnings:
                link = get_clickable_link(w['file'], w['line'])
                f.write(f"| `{w['func']}` | {link} | `{w['var']}` | **{w['type']}** | {w['desc']} |\n")
        else:
            f.write("> [!NOTE]\n")
            f.write("> No scoping bugs found in your workspace files! Clean scoping structures verified.\n")
            
        f.write("\n## External Include Warnings\n\n")
        if external_warnings:
            f.write("| Function | File & Line | Variable | Warning Type | Description |\n")
            f.write("| --- | --- | --- | --- | --- |\n")
            for w in external_warnings:
                link = get_clickable_link(w['file'], w['line'])
                f.write(f"| `{w['func']}` | {link} | `{w['var']}` | {w['type']} | {w['desc']} |\n")
        else:
            f.write("*No warnings found in external UDFs.*\n")
            
        f.write("\n## System Include Warnings\n\n")
        if system_warnings:
            f.write("| Function | File & Line | Variable | Warning Type | Description |\n")
            f.write("| --- | --- | --- | --- | --- |\n")
            for w in system_warnings:
                link = get_clickable_link(w['file'], w['line'])
                f.write(f"| `{w['func']}` | {link} | `{w['var']}` | {w['type']} | {w['desc']} |\n")
        else:
            f.write("*No warnings found in system includes.*\n")

        if args.enable_system_dead_stores or system_dead_store_warnings:
            f.write("\n## Experimental System Include Dead Stores\n\n")
            if system_dead_store_warnings:
                f.write("> [!WARNING]\n")
                f.write("> These diagnostics are opt-in and excluded from normal warning totals because standard UDFs intentionally use many framework-internal scratch/status assignments.\n\n")
                f.write("| Function | File & Line | Variable | Description |\n")
                f.write("| --- | --- | --- | --- |\n")
                for w in system_dead_store_warnings:
                    link = get_clickable_link(w['file'], w['line'])
                    f.write(f"| `{w['func']}` | {link} | `{w['var']}` | {w['desc']} |\n")
            else:
                f.write("*No experimental system include Dead Store diagnostics found.*\n")

    # Print warnings to stdout in Au3Check format
    has_errors = False
    all_active_warnings = workspace_warnings + external_warnings
    if not args.skip_system_includes:
        all_active_warnings.extend(system_warnings)
    if is_legacy_mode:
        all_active_warnings = sorted(all_active_warnings, key=au3check_legacy_sort_key)

    if args.json_out:
        import json
        json_warnings = []
        for w in all_active_warnings:
            w_type = w['type']
            is_error = w_type in ERROR_DIAGNOSTIC_TYPES
            level = "error" if is_error else "warning"
            col = estimate_warning_col(w)
            item = {
                "file": os.path.abspath(w['file']).replace('\\', '/'),
                "line": w['line'],
                "column": col,
                "severity": level,
                "type": w_type,
                "func": w['func'],
                "var": w['var'],
                "desc": w['desc']
            }
            if 'details' in w and w['details'] is not None:
                item['details'] = w['details']
            json_warnings.append(item)
            
        errors_count = sum(1 for w in json_warnings if w['severity'] == "error")
        warnings_count = sum(1 for w in json_warnings if w['severity'] == "warning")
        output_data = {
            "summary": {
                "total": len(json_warnings),
                "errors": errors_count,
                "warnings": warnings_count
            },
            "diagnostics": json_warnings
        }
        original_print(json.dumps(output_data))
        
        if errors_count > 0:
            sys.exit(2)
        elif len(json_warnings) > 0:
            sys.exit(1)
        else:
            sys.exit(0)

    active_errors = 0
    active_warning_count = 0
    for w in all_active_warnings:
        w_type = w['type']
        
        is_error = w_type in ERROR_DIAGNOSTIC_TYPES
        if is_error:
            has_errors = True
            active_errors += 1
        else:
            active_warning_count += 1
        level = "error" if is_error else "warning"

        if is_legacy_mode:
            display_path = args.main_file if os.path.abspath(w['file']).lower() == os.path.abspath(args.main_file).lower() else w['file']
            for out_line in format_au3check_diagnostic(w, level, display_path):
                original_print(out_line)
        else:
            file_path = os.path.abspath(w['file'])
            col = estimate_warning_col(w)
            original_print(f'"{file_path}"({w["line"]},{col}) : {level}: {w["desc"]}')

    if is_legacy_mode and (all_active_warnings or not args.q):
        original_print(f"{args.main_file} - {active_errors} error(s), {active_warning_count} warning(s)")
    else:
        print(f"Generated diagnostic report: {report_file}")
        print(f"Complete pipeline SUCCESS.")

    if is_legacy_mode:
        if has_errors:
            sys.exit(2)
        elif len(all_active_warnings) > 0:
            sys.exit(1)
        else:
            sys.exit(0)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()

