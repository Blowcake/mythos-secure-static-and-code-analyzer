# au3Mythos - Unified JSON Output and Runtime Line Lookup API Reference

This document provides a comprehensive technical reference for the unified JSON output interface (`-json_out`) and the runtime line lookup helper (`-lookup_runtime_line`) in the general-purpose **au3Mythos** static analysis framework (currently featuring the `autoit_windows_x64` module). It is designed to enable IDE developers, extension authors, and tool integrations to seamlessly support au3Mythos diagnostics and runtime line mapping.

---

## 1. Tool Detection & Identification

To determine if `au3Check.exe` in the active environment is the standard compiler binary or the enhanced `au3Mythos` wrapper, execute the following command:

```powershell
Au3Check.exe -mythos
```

### 1.1 Expected Outputs

#### Standard Au3Check.exe (Original)
Prints the usage manual to stdout/stderr and exits with a non-zero exit code:
* **Stdout/Stderr**: `Usage: Au3Check [-q] [-d] [-w[-] n]... [-v[-] n]... [-I dir]... file.au3`
* **Exit Code**: `1` (or non-zero)

#### au3Mythos Wrapper
Prints a single-line copyright and status info to stdout and exits cleanly:
* **Stdout**: `au3Check Wrapper (au3Mythos) - Active`
* **Exit Code**: `0`

---

## 2. Command Line Interface (CLI) Reference

The wrapper is a drop-in replacement for the original `Au3Check.exe` compiler binary. It parses standard options, translates configurations dynamically, runs advanced static scoping analysis when appropriate, and falls back to standard checks.

### 2.1 Invocation Syntax

```powershell
Au3Check.exe [legacy_options] [wrapper_options] <file.au3>
```

### 2.2 Wrapper-Specific Options

* **`-json_out`**:
  Format diagnostics or runtime line lookup results as a unified, structured JSON payload (suppressing legacy text headers and formatting).
* **`-lookup_runtime_line <line_num>`**:
  Translate a preprocessed/compiled runtime line number (from error popups or logs) back to original source file coordinates, lines, and snippets.
* **`-compiled`**:
  Directs `-lookup_runtime_line` to map compiled statement lines (by stripping comments/whitespace), which is required for compiled `.exe` files.

### 2.3 Forwarded Legacy Options

* **`-q`**: Quiet mode (only display errors, suppress warnings).
* **`-d`**: Dev-mode check (forwarded).
* **`-w[-] n`**: Configure warning class `n` (e.g., `-w 3` to enable local var reuse checks).
* **`-v[-] n`**: Set verbose levels.
* **`-I <directory>`**: Append include folder search paths.

---

## 3. IDE Integration Guide

Integrating `au3Mythos` into an IDE (e.g., VS Code extension, Notepad++, or a custom IDE) consists of three steps:

### 3.1 Step 1: Detect Wrapper
Run `Au3Check.exe -mythos`. If it returns exit code `0`, enable advanced features (JSON output, line lookup, auto-spelling suggestions). If it returns `1`, fall back to standard regex parsing of legacy text lines.

### 3.2 Step 2: Running Diagnostics
When a file is saved or checked:
1. Run `Au3Check.exe -json_out -w 3 -I "path/to/includes" "path/to/main.au3"`.
2. Read `stdout` and parse as JSON.
3. Map diagnostics directly to editor markers/gutters:
   - For spell check/undeclared variables (type `"Undeclared Variable"`), use the list of similar names in `details.suggestions` as auto-complete quick fixes.
   - For block scoping issues (type `"Block Scoping Bug"`), hover highlights can display the declaration site and active block boundaries (`details.declaration.block`).
   - For duplicate declarations, hover-highlights can point to the first declaration coordinate (`details.original_declaration`).

### 3.3 Step 3: Resolving Crashes (Runtime Line Lookup)
When a compiled AutoIt executable crashes, it shows a popup or logs a message like `Line 53083 (File "app.exe"): Error: ...`.
To find the developer's source file containing the error:
1. Run `Au3Check.exe -lookup_runtime_line 53083 -compiled -json_out "path/to/main.au3"`.
2. Parse the JSON result:
   ```json
   {
     "preprocessed_line": 53083,
     "file": "C:/Program Files (x86)/AutoIt3/Include/Word.au3",
     "line": 424,
     "code": "If $sPrinter <> \"\" Then"
   }
   ```
3. Open `file` at `line` in the editor and highlight the code line.

---

## 4. Unified JSON Output Mode (`-json_out`)

When executing syntax/scoping checks, passing the `-json_out` (wrapper) or `--json-out` (scoping engine) switch suppresses all traditional text logging and console headers. Instead, it outputs a single, uniform JSON object containing summary metadata and diagnostic details to stdout.

### 4.1 JSON Schema

The root level of the JSON payload is a dictionary containing a `summary` object (providing counts of total, errors, and warnings) and a `diagnostics` array:

```json
{
  "summary": {
    "total": "integer (total number of diagnostics)",
    "errors": "integer (total number of error diagnostics)",
    "warnings": "integer (total number of warning diagnostics)"
  },
  "diagnostics": [
    {
      "file": "string (absolute path with forward slashes)",
      "line": "integer (1-based line number)",
      "column": "integer (1-based column position, estimated)",
      "severity": "string ('error' | 'warning')",
      "type": "string (diagnostic classification type)",
      "func": "string (name of containing function, or empty for global scope)",
      "var": "string (name of the variable involved, including '$')",
      "desc": "string (human-readable message)",
      "details": "object | null (rule-specific debugging metadata)"
    }
  ]
}
```

### 4.2 Severity Rules
* **`error`**: Assigned to critical scoping violations that would prevent compilation or lead to immediate runtime failures:
  * `"Undeclared Variable"` (MustDeclareVars violations)
  * `"Block Scoping Bug"` (accessing a block-declared local variable outside its block)
  * `"Reference Before Declaration"`
* **`warning`**: Assigned to scoping smells, loop variable reuses, dead stores, and duplicate includes.

---

## 5. Rule-Specific Rich Metadata (`details`)

The `details` object is dynamically populated by the `au3Mythos` scoping engine with high-value context to aid automated repair tools, MCP servers, and IDE integrations.

### 5.1 Duplicate Declaration
Fired when a variable is declared again in the same scope.
* **`type`**: `"Duplicate Declaration"`
* **`details` Schema**:
  ```json
  {
    "original_declaration": {
      "file": "string (absolute path to original declaration file)",
      "line": "integer (original declaration line number)"
    }
  }
  ```

### 5.2 Block Scoping Bug
Fired when a `Local` variable is declared inside a block (such as `If/Then`, `For/In`, `While/WEnd`) but referenced outside that block's scope boundary.
* **`type`**: `"Block Scoping Bug"`
* **`details` Schema**:
  ```json
  {
    "declaration": {
      "file": "string (absolute path to declaration file)",
      "line": "integer (declaration line number)",
      "block": "string (description of the block bounds, e.g., 'lines 12-25')"
    }
  }
  ```

### 5.3 Undeclared Variable (with Spelling Suggestions)
Fired when a variable is referenced but has never been declared.
* **`type`**: `"Undeclared Variable"`
* **`details` Schema**:
  Contains an array of up to 3 spelling suggestions from variables declared in the same scope or global scope, computed using Levenshtein distance ($\le 2$).
  ```json
  {
    "suggestions": [
      "string (similar variable name 1)",
      "string (similar variable name 2)"
    ]
  }
  ```

### 5.4 Dead Store
Fired under experimental checks when a variable is assigned a value but that value is never read.
* **`type`**: `"Dead Store"`
* **`details` Schema**:
  ```json
  {
    "declared_at": {
      "file": "string (absolute path to declaration file)",
      "line": "integer (declaration line number)"
    }
  }
  ```

---

## 6. Legacy Au3Check Output Conversion

If a rule is mapped to the legacy compiler (`"original"` action profile), the wrapper captures the console output of `Au3Check_Original.exe`, parses the standard error messages using regular expressions, and normalizes them into the same JSON schema:

* **Regex Pattern**: `^"([^"]+)"\((\d+),(\d+)\)\s*:\s*(error|warning)\s*:\s*(.*)$`
* **Severity Mapping**: Mapped from the original `error` or `warning` severity token.
* **Type Extraction**:
  * If the description contains `"declared"`, type is set to `"Duplicate Declaration"`.
  * If the description contains `"referenced"`, type is set to `"Undeclared Variable"`.
  * Otherwise, type defaults to `"Compiler Diagnostic"`.
* **Details Mapping**: An empty/minimal `details` object is attached (since the legacy compiler does not compute rich trace metadata).

---

## 7. Runtime Line Lookup (`-lookup_runtime_line`)

When an AutoIt application crashes at runtime, the popup window displays a line number. The `-lookup_runtime_line <line_num>` helper translates this line number back to the original developer's source file.

### 7.1 Lookup Modes

#### 7.1.1 Preprocessed Line Lookup (Default)
Looks up the line directly in the unstripped preprocessed flat source file (containing all merged includes, directives, and comments).

#### 7.1.2 Compiled Line Lookup (`-compiled` / `--compiled`)
Required for compiled binaries (`.exe`). The AutoIt compiler strips whitespace, comment lines, and resolved `#include` directive lines (since they are replaced by include file content).
By passing the `-compiled` flag, the analyzer constructs a **Statement Mapping Table** matching only actual statements, ensuring the compiled line number matches the source line exactly.

### 7.2 Output Formats

#### 7.2.1 Plain Text (Default)
```text
Preprocessed Line: 3
Original File: D:\Projects\MyScript\custom_include.au3
Original Line: 4
Code: $a[5] = 42
```

#### 7.2.2 JSON (with `-json_out`)
```json
{
  "preprocessed_line": 3,
  "file": "D:/Projects/MyScript/custom_include.au3",
  "line": 4,
  "code": "$a[5] = 42"
}
```

---

## 8. Example Payloads

### 8.1 Scoping Check Diagnostic Result (Complete Nested JSON)
```json
{
  "summary": {
    "total": 2,
    "errors": 1,
    "warnings": 1
  },
  "diagnostics": [
    {
      "file": "C:/AutoItProject/tests/test_file.au3",
      "line": 15,
      "column": 14,
      "severity": "warning",
      "type": "Duplicate Declaration",
      "func": "Main",
      "var": "$var",
      "desc": "Variable '$var' is already declared.",
      "details": {
        "original_declaration": {
          "file": "C:/AutoItProject/tests/test_file.au3",
          "line": 14
        }
      }
    },
    {
      "file": "C:/AutoItProject/tests/test_file.au3",
      "line": 28,
      "column": 9,
      "severity": "error",
      "type": "Undeclared Variable",
      "func": "Main",
      "var": "$smyvariabl",
      "desc": "Variable '$smyvariabl' is used but not declared.",
      "details": {
        "suggestions": [
          "$smyvariable"
        ]
      }
    }
  ]
}
```

### 8.2 Compiled Runtime Lookup JSON
```json
{
  "preprocessed_line": 53083,
  "file": "C:/Program Files (x86)/AutoIt3/Include/Word.au3",
  "line": 424,
  "code": "If $sPrinter <> \"\" Then"
}
```
