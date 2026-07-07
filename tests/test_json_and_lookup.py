"""@file test_json_and_lookup.py
@brief Unit tests for JSON diagnostics output and runtime line lookup.
@details Part of AutoIt_Static_Analyzer. Verifies the spelling suggestions, original declaration trace coordinates, block scoping ranges, dead stores declared_at details, and line mappings.
"""
import unittest
import json
import tempfile
import sys
from pathlib import Path

# Add src folder to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from autoit_static_analyzer.autoit_windows_x64_scoping_analyzer import (
    levenshtein_distance,
    AutoItPreprocessor,
    AutoItScopingAnalyzer
)

class TestLevenshteinDistance(unittest.TestCase):
    def test_levenshtein(self):
        self.assertEqual(levenshtein_distance("hello", "hello"), 0)
        self.assertEqual(levenshtein_distance("hello", "hell"), 1)
        self.assertEqual(levenshtein_distance("hello", "helo"), 1)
        self.assertEqual(levenshtein_distance("hello", "mello"), 1)
        self.assertEqual(levenshtein_distance("hello", "world"), 4)
        self.assertEqual(levenshtein_distance("", "abc"), 3)
        self.assertEqual(levenshtein_distance("abc", ""), 3)
        self.assertEqual(levenshtein_distance("a", "b"), 1)

class TestJsonAndLookup(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_spelling_suggestions_in_details(self):
        code = """Func Test()
    Local $sMyVariable = 1
    Local $sOtherVar = 2
    Local $y = $sMyVariabl
EndFunc
"""
        main_file = self.temp_path / "test.au3"
        main_file.write_text(code, encoding="utf-8")

        prep = AutoItPreprocessor()
        prep.preprocess(str(main_file))
        merged_lines, line_mappings = prep.merge_continuations()

        analyzer = AutoItScopingAnalyzer()
        analyzer.warnings.extend(prep.warnings)
        
        func_lines = [(i + 1, line) for i, line in enumerate(merged_lines)]
        analyzer.analyze_function("Test", "", 1, func_lines, line_mappings, {})
        
        undeclared_warns = [w for w in analyzer.warnings if w["type"] == "Undeclared Variable"]
        self.assertGreater(len(undeclared_warns), 0)
        warn = undeclared_warns[0]
        self.assertEqual(warn["var"], "$smyvariabl")
        self.assertIn("details", warn)
        self.assertIn("suggestions", warn["details"])
        self.assertIn("$smyvariable", warn["details"]["suggestions"])

    def test_original_declaration_details(self):
        code = """Func Test()
    Local $x = 1
    Local $x = 2
EndFunc
"""
        main_file = self.temp_path / "test.au3"
        main_file.write_text(code, encoding="utf-8")

        prep = AutoItPreprocessor()
        prep.preprocess(str(main_file))
        merged_lines, line_mappings = prep.merge_continuations()

        analyzer = AutoItScopingAnalyzer(warnings_config={3: True})
        func_lines = [(i + 1, line) for i, line in enumerate(merged_lines)]
        analyzer.analyze_function("Test", "", 1, func_lines, line_mappings, {})

        dup_warns = [w for w in analyzer.warnings if w["type"] == "Duplicate Declaration"]
        self.assertGreater(len(dup_warns), 0)
        warn = dup_warns[0]
        self.assertEqual(warn["var"], "$x")
        self.assertIn("details", warn)
        self.assertIn("original_declaration", warn["details"])
        self.assertEqual(warn["details"]["original_declaration"]["line"], 2)

    def test_block_scoping_details(self):
        code = """Func Test()
    If True Then
        Local $x = 1
    EndIf
    Local $y = $x
EndFunc
"""
        main_file = self.temp_path / "test.au3"
        main_file.write_text(code, encoding="utf-8")

        prep = AutoItPreprocessor()
        prep.preprocess(str(main_file))
        merged_lines, line_mappings = prep.merge_continuations()

        analyzer = AutoItScopingAnalyzer()
        func_lines = [(i + 1, line) for i, line in enumerate(merged_lines)]
        analyzer.analyze_function("Test", "", 1, func_lines, line_mappings, {})

        block_warns = [w for w in analyzer.warnings if w["type"] == "Block Scoping Bug"]
        self.assertGreater(len(block_warns), 0)
        warn = block_warns[0]
        self.assertEqual(warn["var"], "$x")
        self.assertIn("details", warn)
        self.assertIn("declaration", warn["details"])
        self.assertEqual(warn["details"]["declaration"]["line"], 3)
        self.assertIn("lines 2-4", warn["details"]["declaration"]["block"])

    def test_dead_store_details(self):
        code = """Func Test()
    Local $x = 1
EndFunc
"""
        main_file = self.temp_path / "test.au3"
        main_file.write_text(code, encoding="utf-8")

        prep = AutoItPreprocessor()
        prep.preprocess(str(main_file))
        merged_lines, line_mappings = prep.merge_continuations()

        analyzer = AutoItScopingAnalyzer(experimental_checks=True)
        func_lines = [(i + 1, line) for i, line in enumerate(merged_lines)]
        analyzer.analyze_function("Test", "", 1, func_lines, line_mappings, {})

        dead_warns = [w for w in analyzer.warnings if w["type"] == "Dead Store"]
        self.assertGreater(len(dead_warns), 0)
        warn = dead_warns[0]
        self.assertEqual(warn["var"], "$x")
        self.assertIn("details", warn)
        self.assertIn("declared_at", warn["details"])
        self.assertEqual(warn["details"]["declared_at"]["line"], 2)

    def test_line_lookup_preprocessor(self):
        inc_code = """; Inc line 1
Local $y = 10
"""
        main_code = """; Main line 1
#include "inc.au3"
Local $x = 20
"""
        inc_file = self.temp_path / "inc.au3"
        inc_file.write_text(inc_code, encoding="utf-8")
        main_file = self.temp_path / "test.au3"
        main_file.write_text(main_code, encoding="utf-8")

        prep = AutoItPreprocessor(include_dirs=[str(self.temp_path)])
        prep.preprocess(str(main_file))
        merged_lines, line_mappings = prep.merge_continuations()

        self.assertEqual(len(line_mappings), 4)

        f_path, orig_line = line_mappings[2]
        self.assertEqual(Path(f_path).name, "inc.au3")
        self.assertEqual(orig_line, 2)

        f_path, orig_line = line_mappings[3]
        self.assertEqual(Path(f_path).name, "test.au3")
        self.assertEqual(orig_line, 3)

    def test_compiled_runtime_watchdog_line_lookup(self):
        import subprocess
        import time
        import re
        import os
        
        # 1. Compile custom crash script
        aut2exe_path = r"C:\Program Files (x86)\AutoIt3\Aut2Exe\Aut2exe_x64.exe"
        from pathlib import Path
        project_root = Path(__file__).resolve().parents[1]
        workspace_parent = project_root.parent
        watchdog_exe = str(workspace_parent / "MCP_Servers" / "MCP_au3mcp" / "bin" / "Tools" / "Watchdog" / "Watchdog_Service_x64.exe")
        errors_log_path = str(workspace_parent / "MCP_Servers" / "MCP_au3mcp" / "bin" / "logs" / "runtime_errors.jsonl")
        
        if os.environ.get("MYTHOS_RUN_WATCHDOG_TEST") != "1":
            self.skipTest("Skipping watchdog compiled runtime lookup test by default. Set MYTHOS_RUN_WATCHDOG_TEST=1 to enable.")
            
        if not os.path.exists(aut2exe_path) or not os.path.exists(watchdog_exe):
            self.skipTest("Aut2Exe or Watchdog service executable not found.")
            
        custom_inc_code = """; custom_include.au3
Func MyTargetFunc()
    Local $a[2] = [1, 2]
    $a[5] = 42
EndFunc
"""
        custom_main_code = """#include "custom_include.au3"
MyTargetFunc()
"""
        inc_file = self.temp_path / "custom_include.au3"
        inc_file.write_text(custom_inc_code, encoding="utf-8")
        main_file = self.temp_path / "test_runtime_crash_custom.au3"
        main_file.write_text(custom_main_code, encoding="utf-8")
        exe_file = self.temp_path / "test_runtime_crash_custom.exe"
        
        # Run compiler
        res_compile = subprocess.run([
            aut2exe_path,
            "/in", str(main_file),
            "/out", str(exe_file),
            "/x64"
        ], capture_output=True)
        self.assertEqual(res_compile.returncode, 0)
        self.assertTrue(exe_file.exists())
        
        # 2. Start Watchdog background service in GLOBAL mode
        watchdog_proc = subprocess.Popen([
            watchdog_exe,
            "--global",
            "--close-window",
            "--terminate"
        ])
        
        try:
            # Wait for watchdog to initialize
            time.sleep(1)
            
            # 3. Run compiled executable and expect a crash
            subprocess.run([str(exe_file)], capture_output=True)
            
            # Wait for watchdog to capture and write the log
            time.sleep(1.5)
        finally:
            # Terminate watchdog
            watchdog_proc.terminate()
            watchdog_proc.wait()
            
        # 4. Read runtime_errors.jsonl to find the captured error
        captured_line_num = None
        if os.path.exists(errors_log_path):
            with open(errors_log_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    stripped = line.strip()
                    if stripped:
                        try:
                            err_data = json.loads(stripped)
                            proc_path = err_data.get("process_path", "").lower()
                            if "test_runtime_crash_custom.exe" in proc_path:
                                # Parse out line number from error message: "Line 3  (File ...)"
                                err_msg = err_data.get("error_message", "")
                                m = re.search(r'(?i)Line\s+(\d+)', err_msg)
                                if m:
                                    captured_line_num = int(m.group(1))
                        except Exception:
                            pass
                            
        self.assertIsNotNone(captured_line_num, "Watchdog failed to capture the runtime crash popup.")
        self.assertEqual(captured_line_num, 3, f"Expected compiled crash line 3, got {captured_line_num}")
        
        # 5. Call preprocessor and line lookup with --compiled flag on captured line number!
        prep = AutoItPreprocessor(include_dirs=[str(self.temp_path)])
        prep.preprocess(str(main_file))
        merged_lines, line_mappings = prep.merge_continuations()
        
        # Replicate --compiled line lookup statement mappings logic
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
            if not stripped:
                continue
            if stripped.startswith(';'):
                continue
            active_mappings.append(line_mappings[i])
            
        self.assertTrue(1 <= captured_line_num <= len(active_mappings))
        file_path, original_line_num = active_mappings[captured_line_num - 1]
        
        self.assertEqual(Path(file_path).name, "custom_include.au3")
        self.assertEqual(original_line_num, 4)

if __name__ == "__main__":
    unittest.main()
