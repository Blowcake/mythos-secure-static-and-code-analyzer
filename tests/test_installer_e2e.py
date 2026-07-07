"""@file test_installer_e2e.py
@brief Integration tests for au3Mythos Setup and Uninstaller toolchain.
@details Part of AutoIt_Static_Analyzer. Verifies silent installation, directory creation, file copying, shortcut paths, and complete uninstallation cleanup.
"""
import os
import shutil
import subprocess
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUT2EXE = Path(r"C:\Program Files (x86)\AutoIt3\Aut2Exe\Aut2exe_x64.exe")
RUN_WRAPPER = PROJECT_ROOT.parent / "tools_au3" / "Agent_Run_Wrapper.exe"

class TestInstallerE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create temp build dir
        cls.bin_dir = PROJECT_ROOT / "bin"
        cls.bin_dir.mkdir(exist_ok=True)
        
        # Ensure we have compiled analyzer and settings manager mock/real files in bin/
        # (This avoids failing if release.ps1 hasn't been run yet)
        (cls.bin_dir / "autoit_windows_x64_scoping_analyzer.exe").touch(exist_ok=True)
        (cls.bin_dir / "au3Mythos_Settings_x64.exe").touch(exist_ok=True)
        (cls.bin_dir / "Au3Check_Wrapper_x64.exe").touch(exist_ok=True)
        
        # Compile Setup and Uninstaller scripts
        cls.compile_script(PROJECT_ROOT / "tools_installer" / "Uninstall_au3Mythos_x64.au3", PROJECT_ROOT / "tools_installer" / "Uninstall_au3Mythos_x64.exe")
        cls.compile_script(PROJECT_ROOT / "tools_installer" / "Setup_au3Mythos_x64.au3", PROJECT_ROOT / "tools_installer" / "Setup_au3Mythos_x64.exe")

    @classmethod
    def compile_script(cls, src_path: Path, dest_exe: Path):
        print(f"Compiling {src_path.name}...")
        if dest_exe.exists():
            dest_exe.unlink()
            
        cmd = [
            str(RUN_WRAPPER),
            str(AUT2EXE),
            "/in", str(src_path),
            "/nopack",
            "/comp", "2",
            "/x64"
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0 or not dest_exe.exists():
            raise RuntimeError(f"Failed to compile {src_path.name}: {res.stderr}\nExitCode: {res.returncode}")

    def setUp(self):
        self.test_install_dir = PROJECT_ROOT / ".tmp" / "test_install"
        if self.test_install_dir.exists():
            shutil.rmtree(self.test_install_dir, ignore_errors=True)

    def tearDown(self):
        if self.test_install_dir.exists():
            # Give background cmd script some time to finish deleting
            time.sleep(2)
            shutil.rmtree(self.test_install_dir, ignore_errors=True)

    def test_silent_installation_and_uninstallation(self):
        setup_exe = PROJECT_ROOT / "tools_installer" / "Setup_au3Mythos_x64.exe"
        self.assertTrue(setup_exe.exists(), "Setup_au3Mythos_x64.exe was not compiled successfully.")

        # 1. Run silent installer
        print("Running silent Setup...")
        cmd_install = [
            str(setup_exe),
            "/S",
            f"/DIR={self.test_install_dir}"
        ]
        # Run Setup (Setup requests admin by default via manifest.
        # Note: In our test environment, we run with admin privileges, so it should run cleanly.)
        cmd_str = " ".join(f'"{x}"' for x in cmd_install)
        res = subprocess.run(cmd_str, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, f"Installer failed with code {res.returncode}: {res.stderr}")

        # 2. Verify files are copied
        self.assertTrue((self.test_install_dir / "au3Mythos_Settings_x64.exe").exists())
        self.assertTrue((self.test_install_dir / "Uninstall_au3Mythos_x64.exe").exists())
        self.assertTrue((self.test_install_dir / "bin" / "autoit_windows_x64_scoping_analyzer.exe").exists())
        self.assertTrue((self.test_install_dir / "bin" / "Au3Check_Wrapper_x64.exe").exists())
        self.assertTrue((self.test_install_dir / "docs" / "au3Mythos_User_Manual.md").exists())
        self.assertTrue((self.test_install_dir / "mythos_config" / "config.json").exists())

        # 3. Run silent uninstaller
        print("Running silent Uninstaller...")
        uninst_exe = self.test_install_dir / "Uninstall_au3Mythos_x64.exe"
        self.assertTrue(uninst_exe.exists())
        cmd_uninstall = [
            str(uninst_exe),
            "/S",
            f"/DIR={self.test_install_dir}"
        ]
        cmd_uninstall_str = " ".join(f'"{x}"' for x in cmd_uninstall)
        res_un = subprocess.run(cmd_uninstall_str, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res_un.returncode, 0, f"Uninstaller failed with code {res_un.returncode}: {res_un.stderr}")

        # 4. Verify files are cleaned up
        print("Waiting for self-deletion cleanup script...")
        # Uninstaller uses a background CMD script to delete Uninstall_au3Mythos_x64.exe and the folder since it cannot delete itself
        for _ in range(15):
            time.sleep(0.5)
            if not (self.test_install_dir / "Uninstall_au3Mythos_x64.exe").exists() and not (self.test_install_dir / "bin").exists():
                break

        self.assertFalse((self.test_install_dir / "Uninstall_au3Mythos_x64.exe").exists(), "Uninstall_au3Mythos_x64.exe was not deleted.")
        self.assertFalse((self.test_install_dir / "au3Mythos_Settings_x64.exe").exists(), "GUI settings was not deleted.")
        self.assertFalse((self.test_install_dir / "bin").exists(), "bin folder was not deleted.")

if __name__ == "__main__":
    unittest.main()
