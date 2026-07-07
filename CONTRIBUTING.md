# Contributing to AutoIt Static Analyzer

Thank you for contributing to the AutoIt Static Analyzer (au3Mythos) project. This document describes the setup, coding standards, commands, and verification gates expected for code and documentation changes.

---

## 1. Development Environment Setup

Use a Windows development machine. The normal project gate is `build.ps1`, so contributors should install the same tools it expects.

Required for the build gate:

- **AutoIt3** installed under `C:\Program Files (x86)\AutoIt3\`.
- `Au3Check.exe` (and `Au3Check_Original.exe` for parity testing).
- `Aut2Exe_x64.exe` (used to compile test scripts).
- **Python 3** on `PATH`, used to execute the static scoping analyzer and run the python test suites.

Current validated AutoIt toolchain:

- AutoIt3 `3.3.18.0`
- Au3Check `3.3.18.0`
- Aut2Exe_x64 `3.3.18.0`

Optional but recommended:

- **Doxygen** on `PATH`, or at `C:\Program Files\doxygen\bin\doxygen.exe`, for generated HTML API documentation.

---

## 2. Coding Standards and Guidelines

All code modifications must adhere strictly to these guidelines:

### 2.1 AutoIt Source Files (`.au3`)
For the wrapper (`Au3Check_Wrapper.au3`), settings GUI (`au3Mythos_Settings.au3`), and test files:
- Every executable script and test file must use `Opt("MustDeclareVars", 1)`.
- All variables inside functions MUST be declared with `Local` scope.
- Global variable declarations inside functions are strictly prohibited unless you are modifying a documented singleton or shared state.
- **Hungarian Notation**: You must prefix all variable names to indicate their type, preventing `Variant Type Mismatch` runtime errors:
  - `$sName` (String)
  - `$iCount` (Integer / Count)
  - `$bStatus` (Boolean)
  - `$aList` (Array)
  - `$mMap` (Map)
  - `$hWin` (Handle)
  - `$oObject` (Object)
  - `$fVal` (Float / Double)
- **Error Propagation (`SetError`)**: Functions must propagate errors explicitly using `Return SetError(iErrorCode, iExtendedCode, vReturnValue)` instead of returning only simple `False` values. Callers must check `@error` immediately after calling functions.

### 2.2 Python Source Files (`.py`)
- Keep analyzer behavior deterministic. New diagnostics must have focused fixtures and stable report output.
- Prefer precise AutoIt parsing helpers over broad regexes when syntax context matters.
- Keep warnings conservative by default. High-risk or noisy checks should remain behind `--enable-experimental-checks` until burn-in results are stable.
- Python code must be written inside the `src/autoit_static_analyzer/` package, adhering to a modular package layout.

### 2.3 File Documentation Headers
- **Python files**: Use a module docstring with `@file`, `@brief`, and `@details` fields so Doxygen and human readers can identify the file responsibility quickly.
- **AutoIt files**: Use the standard AutoIt UDF file-header comment block format after initial `#pragma`, `#include`, and `Opt(...)` prologue lines:
```autoit
; #UDF# =========================================================================================================================
; Name...........: FileName
; Title .........: Short Title
; Description ...: Brief description of the file.
; Author ........: Author Name
; Modified.......:
; ===============================================================================================================================
```
- **PowerShell scripts**: Use a comment-based help block with `.SYNOPSIS`, `.DESCRIPTION`, and `.NOTES`.

### 2.4 AutoIt Function Documentation Headers (Doxygen)
All public AutoIt UDF functions must have a standard Doxygen-compatible comment header block:
```autoit
; #FUNCTION# ====================================================================================================================
; Name...........: _MCP_FunctionName
; Description ...: Summary of what the function does.
; Syntax.........: _MCP_FunctionName($sParam1[, $iParam2 = 0])
; Parameters ....: $sParam1 - Purpose of the first parameter.
;                  $iParam2 - Purpose of the second parameter.
; Return values .: True on success, False on failure and sets:
;                  |@error = 1 - Parameter validation failed
;                  |@error = 2 - Transport error
; Author ........: Author Name
; Modified.......:
; ===============================================================================================================================
```

---

## 3. Project Lifecycle Commands

We use three standard PowerShell scripts to manage the project lifecycle:

- **Build and Validate**: Run `.\build.ps1` in the project root.
  - Parses the analyzer, runs unit tests, E2E wrapper tests, checks the package CLI, and generates Doxygen documentation.
  - Fails on `Au3Check` errors, compilation failures, or test failures.
- **Bump Version**: Run `.\bump.ps1 [patch|minor|major]` to safely increment the SemVer version in `project.json`. Do not edit the version manually.
- **Backup**: Run `.\backup.ps1` to create an intelligent, timestamped project archive in the workspace parent `_Backups` folder.

---

## 4. Testing Guidelines

When adding new tests or features:
- Test scripts must reside in the `tests\` directory.
- Add or update fixture coverage in `tests\test_warning_fixtures.py`, `tests\test_json_and_lookup.py`, or `tests\test_wrapper_e2e.py`.
- **E2E Watchdog Integration Tests**: Tests requiring the Watchdog service (e.g. intercepting compiled crash popups) are skipped by default to run cleanly on standard machines (including GitHub Actions). Set `MYTHOS_RUN_WATCHDOG_TEST=1` in your environment to execute these tests locally.

Common local test runner scripts:
```powershell
python .\tests\test_lexer_helpers.py
python .\tests\test_warning_fixtures.py
python .\tests\test_json_and_lookup.py
python .\tests\test_wrapper_e2e.py
python -m autoit_static_analyzer --help
```

Use the system include burn-in when changing shared analysis logic:
```powershell
.\examples\run_burnin_analysis.ps1
```

---

## 5. Documentation Guidelines

Update documentation in the same change when behavior, public APIs, or release notes change.

Common documentation targets:
- `README.md` for project overview, public modules, and common workflows.
- `docs\AutoIt_Syntax_Checker_Mythos_JSON_API.md` for API specifications, JSON schema, and IDE integration details.
- `CHANGELOG.md` for release-facing changes.
