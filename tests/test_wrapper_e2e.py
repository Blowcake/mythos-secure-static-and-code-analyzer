"""@file test_wrapper_e2e.py
@brief End-to-end tests for the Au3Check wrapper integration path.
@details Part of AutoIt_Static_Analyzer. This header is intentionally concise so Doxygen output and future code reviews expose the module boundary before implementation details.
"""
import unittest
import subprocess
import os
import sys
import json
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_EXE = PROJECT_ROOT / "tools_wrapper" / "Au3Check_Wrapper.exe"
CONFIG_JSON = PROJECT_ROOT / "resources" / "mythos_config" / "config.json"
ORIGINAL_EXE_PATH = Path(r"C:\Program Files (x86)\AutoIt3\Au3Check.exe")
ORIGINAL_DAT_PATH = Path(r"C:\Program Files (x86)\AutoIt3\Au3Check.dat")

class WrapperE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 1. Back up config.json
        cls.config_backup = CONFIG_JSON.read_text(encoding="utf-8")
        
        # 2. Make sure Au3Check_Original.exe and .dat exist in tools_wrapper for local fallback testing
        cls.orig_exe_backup = PROJECT_ROOT / "tools_wrapper" / "Au3Check_Original.exe"
        cls.orig_dat_backup = PROJECT_ROOT / "tools_wrapper" / "Au3Check_Original.dat"
        
        cls.copied_exe = False
        cls.copied_dat = False
        
        system_orig = Path(r"C:\Program Files (x86)\AutoIt3\Au3Check_Original.exe")
        system_current = ORIGINAL_EXE_PATH
        system_orig_dat = Path(r"C:\Program Files (x86)\AutoIt3\Au3Check_Original.dat")
        system_current_dat = ORIGINAL_DAT_PATH
        
        if not cls.orig_exe_backup.exists():
            if system_orig.exists():
                shutil.copy2(system_orig, cls.orig_exe_backup)
                cls.copied_exe = True
            elif system_current.exists():
                shutil.copy2(system_current, cls.orig_exe_backup)
                cls.copied_exe = True
                
        if not cls.orig_dat_backup.exists():
            if system_orig_dat.exists():
                shutil.copy2(system_orig_dat, cls.orig_dat_backup)
                cls.copied_dat = True
            elif system_current_dat.exists():
                shutil.copy2(system_current_dat, cls.orig_dat_backup)
                cls.copied_dat = True

    @classmethod
    def tearDownClass(cls):
        # Restore config.json
        CONFIG_JSON.write_text(cls.config_backup, encoding="utf-8")
        
        # Clean up copied files
        if cls.copied_exe and cls.orig_exe_backup.exists():
            try:
                cls.orig_exe_backup.unlink()
            except OSError:
                pass
        if cls.copied_dat and cls.orig_dat_backup.exists():
            try:
                cls.orig_dat_backup.unlink()
            except OSError:
                pass

    def test_wrapper_original_fallback_when_disabled(self):
        # Write config.json with wrapper_enabled = false
        config = json.loads(self.config_backup)
        config["wrapper_enabled"] = False
        if "configs" in config and "default_original" in config["configs"]:
            config["configs"]["default_original"]["extra_args"] = ""
        CONFIG_JSON.write_text(json.dumps(config, indent=2), encoding="utf-8")

        # Create a temp file to run
        test_file = PROJECT_ROOT / ".tmp" / "wrapper_fallback_test.au3"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("; valid comment\n", encoding="utf-8")

        try:
            # Run wrapper. Without -w 5, Au3Check original should report 0 warnings/errors
            env = os.environ.copy()
            env["MYTHOS_TEST_CONFIG"] = str(CONFIG_JSON)
            res = subprocess.run(
                [str(WRAPPER_EXE), str(test_file)],
                capture_output=True,
                text=True,
                env=env
            )
            # Au3Check original prints its header and summary
            if res.returncode != 0 or "AutoIt3 Syntax Checker" not in res.stdout:
                print("E2E FAIL: RC:", res.returncode, "STDOUT:", repr(res.stdout), "STDERR:", repr(res.stderr))
            self.assertEqual(res.returncode, 0)
            self.assertIn("AutoIt3 Syntax Checker", res.stdout)
            self.assertIn("0 error(s), 0 warning(s)", res.stdout)
        finally:
            if test_file.exists():
                test_file.unlink()

    def test_wrapper_mythos_routing_when_enabled(self):
        # Write config.json with wrapper_enabled = true and python.exe/pythonw.exe rules
        # Using caller_name = "*" and path_prefix = "*" to ensure it routes to mythos
        config = json.loads(self.config_backup)
        config["wrapper_enabled"] = True
        config["rules"] = [
            {
                "caller_name": "*",
                "path_prefix": "*",
                "action": "mythos",
                "config": "default_mythos"
            }
        ]
        # Ensure correct path to python and analyzer in settings (supporting both legacy and new structures)
        if "configs" not in config:
            config["configs"] = {
                "default_mythos": {
                    "type": "mythos",
                    "python_path": "python.exe",
                    "analyzer_path": "",
                    "skip_system_includes": False,
                    "enable_experimental_checks": True,
                    "engine_mode": "standalone",
                    "no_auto_include_discovery": False,
                    "enable_system_dead_stores": True,
                    "warnings": {"1": True, "2": True, "3": True, "4": True, "5": True, "6": True, "7": True}
                }
            }
        config["configs"]["default_mythos"]["python_path"] = sys.executable
        config["configs"]["default_mythos"]["analyzer_path"] = str(PROJECT_ROOT / "src" / "autoit_static_analyzer" / "autoit_windows_x64_scoping_analyzer.py")
        CONFIG_JSON.write_text(json.dumps(config, indent=2), encoding="utf-8")

        # Create a temp file with scoping warning (Local var in global scope)
        test_file = PROJECT_ROOT / ".tmp" / "wrapper_mythos_test.au3"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("Local $x = 1\n", encoding="utf-8")

        try:
            # Run wrapper with -w 4 (Local var in global scope warning)
            env = os.environ.copy()
            env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
            env["MYTHOS_TEST_CONFIG"] = str(CONFIG_JSON)
            res = subprocess.run(
                [str(WRAPPER_EXE), "-w", "4", str(test_file)],
                capture_output=True,
                text=True,
                env=env
            )
            # Should route to mythos and output the warning and exit code 1
            self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
            self.assertIn("warning: 'Local' specifier in global scope.", res.stdout)
            self.assertIn("0 error(s), 1 warning(s)", res.stdout)
        finally:
            if test_file.exists():
                test_file.unlink()

    def test_wrapper_json_output_mode(self):
        # 1. Test Mythos JSON output
        config = json.loads(self.config_backup)
        config["wrapper_enabled"] = True
        config["rules"] = [{"caller_name": "*", "path_prefix": "*", "action": "mythos", "config": "default_mythos"}]
        if "configs" not in config:
            config["configs"] = {
                "default_mythos": {
                    "type": "mythos",
                    "python_path": "python.exe",
                    "analyzer_path": ""
                }
            }
        config["configs"]["default_mythos"]["python_path"] = sys.executable
        config["configs"]["default_mythos"]["analyzer_path"] = str(PROJECT_ROOT / "src" / "autoit_static_analyzer" / "autoit_windows_x64_scoping_analyzer.py")
        CONFIG_JSON.write_text(json.dumps(config, indent=2), encoding="utf-8")

        test_file = PROJECT_ROOT / ".tmp" / "wrapper_json_mythos_test.au3"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("Func Test()\nLocal $x = 1\nLocal $x = 2\nEndFunc\n", encoding="utf-8")

        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
            env["MYTHOS_TEST_CONFIG"] = str(CONFIG_JSON)
            res = subprocess.run(
                [str(WRAPPER_EXE), "-json_out", "-w", "3", str(test_file)],
                capture_output=True,
                text=True,
                env=env
            )
            # Should return JSON dict
            data = json.loads(res.stdout.strip())
            self.assertIsInstance(data, dict)
            self.assertIn("summary", data)
            self.assertIn("diagnostics", data)
            diagnostics = data["diagnostics"]
            self.assertGreater(len(diagnostics), 0)
            self.assertEqual(diagnostics[0]["type"], "Duplicate Declaration")
            self.assertIn("details", diagnostics[0])
            self.assertIn("original_declaration", diagnostics[0]["details"])
        finally:
            if test_file.exists():
                test_file.unlink()

        # 2. Test Original JSON output conversion
        config = json.loads(self.config_backup)
        config["wrapper_enabled"] = True
        config["rules"] = [{"caller_name": "*", "path_prefix": "*", "action": "original", "config": "default_original"}]
        CONFIG_JSON.write_text(json.dumps(config, indent=2), encoding="utf-8")

        test_file = PROJECT_ROOT / ".tmp" / "wrapper_json_orig_test.au3"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("Func Test()\nLocal $x = 1\nLocal $x = 2\nEndFunc\n", encoding="utf-8")

        try:
            env = os.environ.copy()
            env["MYTHOS_TEST_CONFIG"] = str(CONFIG_JSON)
            res = subprocess.run(
                [str(WRAPPER_EXE), "-json_out", "-w", "3", str(test_file)],
                capture_output=True,
                text=True,
                env=env
            )
            data = json.loads(res.stdout.strip())
            self.assertIsInstance(data, dict)
            self.assertIn("summary", data)
            self.assertIn("diagnostics", data)
            self.assertEqual(data["summary"]["total"], 1)
        finally:
            if test_file.exists():
                test_file.unlink()

    def test_wrapper_lookup_runtime_line(self):
        config = json.loads(self.config_backup)
        config["wrapper_enabled"] = True
        if "configs" not in config:
            config["configs"] = {
                "default_mythos": {
                    "type": "mythos",
                    "python_path": "python.exe",
                    "analyzer_path": ""
                }
            }
        config["configs"]["default_mythos"]["python_path"] = sys.executable
        config["configs"]["default_mythos"]["analyzer_path"] = str(PROJECT_ROOT / "src" / "autoit_static_analyzer" / "autoit_windows_x64_scoping_analyzer.py")
        CONFIG_JSON.write_text(json.dumps(config, indent=2), encoding="utf-8")

        test_file = PROJECT_ROOT / ".tmp" / "wrapper_lookup_test.au3"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("; Line 1\nLocal $x = 42\n", encoding="utf-8")

        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
            env["MYTHOS_TEST_CONFIG"] = str(CONFIG_JSON)
            # Run text lookup
            res = subprocess.run(
                [str(WRAPPER_EXE), "-lookup_runtime_line", "2", str(test_file)],
                capture_output=True,
                text=True,
                env=env
            )
            self.assertIn("Preprocessed Line: 2", res.stdout)
            self.assertIn("Original Line: 2", res.stdout)
            self.assertIn("Code: Local $x = 42", res.stdout)

            # Run JSON lookup
            res_json = subprocess.run(
                [str(WRAPPER_EXE), "-lookup_runtime_line", "2", "-json_out", str(test_file)],
                capture_output=True,
                text=True,
                env=env
            )
            data = json.loads(res_json.stdout.strip())
            self.assertEqual(data["preprocessed_line"], 2)
            self.assertEqual(data["line"], 2)
            self.assertEqual(data["code"], "Local $x = 42")
        finally:
            if test_file.exists():
                test_file.unlink()

    def test_wrapper_mythos_switch(self):
        res = subprocess.run(
            [str(WRAPPER_EXE), "-mythos"],
            capture_output=True,
            text=True
        )
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "au3Check Wrapper (au3Mythos) - Active")

if __name__ == "__main__":
    unittest.main()
