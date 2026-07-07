; #UDF# =========================================================================================================================
; Name...........: Uninstall
; Title .........: au3Mythos Uninstaller
; Description ...: GUI/CLI uninstaller to clean up au3Mythos static checker files, shortcuts, and registry keys.
; Author ........: Harald Frank
; ===============================================================================================================================
#pragma compile(Console, False)
#pragma compile(x64, True)
#pragma compile(Out, ..\tools_installer\Uninstall_au3Mythos_x64.exe)
#pragma compile(Icon, ..\resources\mythos_logo.ico)

#include <GUIConstantsEx.au3>
#include <WindowsConstants.au3>
#include <MsgBoxConstants.au3>
#include <File.au3>

Global $bSilent = False
Global $bRunUninstall = False
Global $sInstallDir = @ScriptDir
Global $sArg = ""
Global $iRet = 0
Global $iStatus = 0

; Parse command line parameters
For $i = 1 To $CmdLine[0]
    $sArg = $CmdLine[$i]
    If StringUpper($sArg) == "/S" Or StringUpper($sArg) == "/SILENT" Then
        $bSilent = True
    ElseIf StringUpper($sArg) == "/RUNUNINSTALL" Then
        $bRunUninstall = True
    ElseIf StringLeft(StringUpper($sArg), 5) == "/DIR=" Then
        $sInstallDir = StringMid($sArg, 6)
        If StringLeft($sInstallDir, 1) == '"' And StringRight($sInstallDir, 1) == '"' Then
            $sInstallDir = StringMid($sInstallDir, 2, StringLen($sInstallDir) - 2)
        EndIf
    EndIf
Next

; If running from the actual install directory, resolve absolute path
If $sInstallDir == "" Or $sInstallDir == "." Then
    $sInstallDir = @ScriptDir
EndIf

; Silent Mode self-elevation if target requires admin and we are not admin
If $bSilent And StringInStr(StringUpper($sInstallDir), StringUpper(@ProgramFilesDir)) > 0 And Not IsAdmin() Then
    $iRet = ShellExecuteWait(@ScriptFullPath, $CmdLineRaw, "", "runas")
    If @error Then Exit 1
    Exit $iRet
EndIf

If $bSilent Then
    $iStatus = PerformUninstall($sInstallDir)
    Exit $iStatus
EndIf

; Extract high-resolution transparent logo from resources to temp directory
Global $sTempIco = @TempDir & "\mythos_uninst_logo.ico"
FileInstall("..\resources\mythos_logo.ico", $sTempIco, 1)

; Register cleanup function to delete temp file upon exit
OnAutoItExitRegister("CleanupTempFiles")

; GUI Mode Uninstaller Wizard (matching Setup layout precisely)
; We set the native GUI background to dark 0x1A252C so overlapping controls (like the Icon)
; inherit the correct dark background brush without any white/gray square border.
Global $hMainGui = GUICreate("au3Mythos Uninstaller", 550, 360, -1, -1, BitOR($WS_OVERLAPPEDWINDOW, $WS_CLIPSIBLINGS))
GUISetBkColor(0x1A252C, $hMainGui)

; Right panel background (Solid light gray using a Label)
Global $idRightBg = GUICtrlCreateLabel("", 160, 0, 390, 360)
GUICtrlSetBkColor($idRightBg, 0xF5F6F7)
GUICtrlSetState($idRightBg, $GUI_DISABLE)

; Branded Icon in Left Panel (Takes 80% of width = 128px, centered. Naturally inherits parent GUI dark bkcolor)
Global $idIcon = GUICtrlCreateIcon($sTempIco, -1, 16, 20, 128, 128)
GUICtrlSetBkColor($idIcon, $GUI_BKCOLOR_TRANSPARENT)

; Text labels with transparent backgrounds to prevent white/gray boxes
Global $idBrandLbl = GUICtrlCreateLabel("au3Mythos", 15, 165, 130, 30)
GUICtrlSetFont(-1, 18, 800, 0, "Outfit")
GUICtrlSetColor(-1, 0x1A73E8) ; Brand Blue
GUICtrlSetBkColor($idBrandLbl, $GUI_BKCOLOR_TRANSPARENT)

Global $idSubBrandLbl = GUICtrlCreateLabel("Static Analysis" & @CRLF & "Framework", 15, 200, 130, 40)
GUICtrlSetFont(-1, 10, 400, 0, "Outfit")
GUICtrlSetColor(-1, 0x8C9BA5)
GUICtrlSetBkColor($idSubBrandLbl, $GUI_BKCOLOR_TRANSPARENT)

; About button in the bottom-left corner of the left panel
Global $idAboutBtn = GUICtrlCreateButton("About", 15, 318, 65, 23)
GUICtrlSetFont(-1, 9, 400, 0, "Outfit")

; Title and content in right panel (set background to transparent to sit on light gray $idRightBg)
Global $idTitle = GUICtrlCreateLabel("Uninstall au3Mythos", 185, 20, 340, 30)
GUICtrlSetFont(-1, 14, 800, 0, "Outfit")
GUICtrlSetColor(-1, 0x1A252C)
GUICtrlSetBkColor($idTitle, $GUI_BKCOLOR_TRANSPARENT)

Global $idDesc = GUICtrlCreateLabel("This wizard will completely remove au3Mythos Static Checker and all of its components from your computer." & @CRLF & @CRLF & "Click 'Next' to proceed with the removal process:", 185, 60, 340, 80)
GUICtrlSetFont(-1, 9.5, 400, 0, "Outfit")
GUICtrlSetColor(-1, 0x3C4D56)
GUICtrlSetBkColor($idDesc, $GUI_BKCOLOR_TRANSPARENT)

; Page 2 Controls (Checklist Items, initially hidden)
Global $idStep1 = GUICtrlCreateLabel("  1. Stopping active analyzer processes...", 185, 130, 340, 20)
GUICtrlSetFont(-1, 9.5, 400, 0, "Outfit")
GUICtrlSetColor(-1, 0x8C9BA5)
GUICtrlSetBkColor(-1, $GUI_BKCOLOR_TRANSPARENT)
GUICtrlSetState(-1, $GUI_HIDE)

Global $idStep2 = GUICtrlCreateLabel("  2. Restoring original compiler files...", 185, 155, 340, 20)
GUICtrlSetFont(-1, 9.5, 400, 0, "Outfit")
GUICtrlSetColor(-1, 0x8C9BA5)
GUICtrlSetBkColor(-1, $GUI_BKCOLOR_TRANSPARENT)
GUICtrlSetState(-1, $GUI_HIDE)

Global $idStep3 = GUICtrlCreateLabel("  3. Deleting program files...", 185, 180, 340, 20)
GUICtrlSetFont(-1, 9.5, 400, 0, "Outfit")
GUICtrlSetColor(-1, 0x8C9BA5)
GUICtrlSetBkColor(-1, $GUI_BKCOLOR_TRANSPARENT)
GUICtrlSetState(-1, $GUI_HIDE)

Global $idStep4 = GUICtrlCreateLabel("  4. Removing Start Menu shortcuts...", 185, 205, 340, 20)
GUICtrlSetFont(-1, 9.5, 400, 0, "Outfit")
GUICtrlSetColor(-1, 0x8C9BA5)
GUICtrlSetBkColor(-1, $GUI_BKCOLOR_TRANSPARENT)
GUICtrlSetState(-1, $GUI_HIDE)

Global $idStep5 = GUICtrlCreateLabel("  5. Removing registry entries...", 185, 230, 340, 20)
GUICtrlSetFont(-1, 9.5, 400, 0, "Outfit")
GUICtrlSetColor(-1, 0x8C9BA5)
GUICtrlSetBkColor(-1, $GUI_BKCOLOR_TRANSPARENT)
GUICtrlSetState(-1, $GUI_HIDE)

Global $idSep = GUICtrlCreateGraphic(175, 300, 360, 1)
GUICtrlSetBkColor(-1, 0xD0D5DD)

Global $idUninstallBtn = GUICtrlCreateButton("Next", 360, 315, 80, 26)
Global $idCancelBtn = GUICtrlCreateButton("Cancel", 450, 315, 80, 26)

GUISetState(@SW_SHOW, $hMainGui)

Global $bFirstRun = True
Global $nMsg = 0
Global $iChoice = 0
Global $sRelaunchArgs = ""
Global $iRelaunchRet = 0
Global $iUninstallStatus = 0
Global $nMsg2 = 0
Global $iCurrentPage = 1

While 1
    $nMsg = GUIGetMsg()
    
    ; Auto-trigger Page 2 transition if relaunching in elevated mode to run uninstaller
    If $bFirstRun And $bRunUninstall Then
        $bFirstRun = False
        ShowPage2()
        RunUninstallSequence()
    EndIf
    
    Switch $nMsg
        Case $GUI_EVENT_CLOSE
            Exit 0
        Case $idCancelBtn
            If $idCancelBtn == $nMsg Then Exit 0
        Case $idAboutBtn
            MsgBox($MB_ICONINFORMATION + $MB_OK, "About au3Mythos Uninstaller", "au3Mythos Static Analyzer Uninstaller" & @CRLF & "Version 1.1.0" & @CRLF & @CRLF & "Developed by Harald Frank" & @CRLF & "Copyright (C) 2026. All rights reserved.", 0, $hMainGui)
        Case $idUninstallBtn
            ; If we are on Page 2 and uninstall finished, this button functions as "Finish" / "Beenden" or "Close"
            If $iCurrentPage == 2 Then
                Exit 0
            EndIf
            
            ; Defer UAC self-elevation check until user clicks "Next"
            If StringInStr(StringUpper($sInstallDir), StringUpper(@ProgramFilesDir)) > 0 And Not IsAdmin() Then
                $iChoice = MsgBox($MB_ICONINFORMATION + $MB_OKCANCEL, "Administrator Privileges Required", "au3Mythos Uninstaller requires Administrator privileges to remove program files, clean up registry keys, and restore original compiler files." & @CRLF & @CRLF & "Please click OK to authorize UAC elevation, or Cancel to return.", 0, $hMainGui)
                If $iChoice <> $IDOK Then ContinueLoop
                
                ; Hide parent window immediately before UAC prompts to prevent duplicate/stuck GUI views
                GUISetState(@SW_HIDE, $hMainGui)
                
                ; Relaunch elevated and auto-run the uninstaller
                $sRelaunchArgs = '/RUNUNINSTALL /DIR="' & $sInstallDir & '"'
                ShellExecute(@ScriptFullPath, $sRelaunchArgs, "", "runas")
                If @error Then
                    MsgBox($MB_ICONERROR + $MB_OK, "Elevation Failed", "Administrator privileges were not granted. Uninstallation cancelled.", 0)
                    GUISetState(@SW_SHOW, $hMainGui) ; Restore parent view if elevation was rejected
                    ContinueLoop
                EndIf
                Exit 0 ; Elevated child started, exit parent immediately to keep only one window
            EndIf
            
            ; Transition to Page 2
            ShowPage2()
            RunUninstallSequence()
    EndSwitch
WEnd

Func ShowPage2()
    $iCurrentPage = 2
    
    GUICtrlSetState($idStep1, $GUI_SHOW)
    GUICtrlSetState($idStep2, $GUI_SHOW)
    GUICtrlSetState($idStep3, $GUI_SHOW)
    GUICtrlSetState($idStep4, $GUI_SHOW)
    GUICtrlSetState($idStep5, $GUI_SHOW)
    
    GUICtrlSetData($idTitle, "Uninstalling au3Mythos...")
    GUICtrlSetData($idDesc, "Please wait while the uninstallation processes are executed:")
    GUICtrlSetColor($idDesc, 0x3C4D56)
    
    GUICtrlSetState($idUninstallBtn, $GUI_DISABLE)
    GUICtrlSetState($idCancelBtn, $GUI_DISABLE)
EndFunc

Func RunUninstallSequence()
    Local $sDest = $sInstallDir
    
    ; Step 1: Stopping active analyzer processes
    GUICtrlSetData($idStep1, "> 1. Stopping active analyzer processes...")
    GUICtrlSetColor($idStep1, 0x1A73E8) ; Blue (In Progress)
    Sleep(400)
    
    ProcessClose("au3Mythos_Settings_x64.exe")
    ProcessClose("au3Mythos_Settings.exe")
    ProcessClose("Au3Check.exe")
    ProcessClose("Au3Check_Wrapper.exe")
    ProcessClose("Au3Check_Wrapper_x64.exe")
    
    GUICtrlSetData($idStep1, "[OK] 1. Stopping active analyzer processes")
    GUICtrlSetColor($idStep1, 0x2E7D32) ; Green (Success)
    
    ; Step 2: Restoring original compiler files
    GUICtrlSetData($idStep2, "> 2. Restoring original compiler files...")
    GUICtrlSetColor($idStep2, 0x1A73E8)
    Sleep(400)
    
    Local $sAutoItDir = @ProgramFilesDir & "\AutoIt3"
    If FileExists($sAutoItDir & "\Au3Check_Original.exe") Then
        FileDelete($sAutoItDir & "\Au3Check.exe")
        If Not FileMove($sAutoItDir & "\Au3Check_Original.exe", $sAutoItDir & "\Au3Check.exe", $FC_OVERWRITE) Then
            GUICtrlSetData($idStep2, "[FAIL] 2. Restoring original compiler files")
            GUICtrlSetColor($idStep2, 0xC62828)
            Return ShowResult(False, "Failed to restore original Au3Check.exe in " & $sAutoItDir)
        EndIf
        
        If FileExists($sAutoItDir & "\Au3Check_Original.dat") Then
            FileDelete($sAutoItDir & "\Au3Check.dat")
            FileMove($sAutoItDir & "\Au3Check_Original.dat", $sAutoItDir & "\Au3Check.dat", $FC_OVERWRITE)
        EndIf
    EndIf
    
    GUICtrlSetData($idStep2, "[OK] 2. Restoring original compiler files")
    GUICtrlSetColor($idStep2, 0x2E7D32)
    
    ; Step 3: Deleting program files
    GUICtrlSetData($idStep3, "> 3. Deleting program files...")
    GUICtrlSetColor($idStep3, 0x1A73E8)
    Sleep(400)
    
    FileDelete($sDest & "\bin\autoit_windows_x64_scoping_analyzer.exe")
    FileDelete($sDest & "\bin\Au3Check_Wrapper_x64.exe")
    FileDelete($sDest & "\au3Mythos_Settings_x64.exe")
    FileDelete($sDest & "\mythos_config\config.json")
    FileDelete($sDest & "\docs\screenshots\*.png")
    DirRemove($sDest & "\docs\screenshots", 1)
    
    Local $aDocs = ["au3Mythos_User_Manual.md", "au3Mythos_Technical_Reference.md", "au3Mythos_JSON_API.md"]
    For $sDoc In $aDocs
        FileDelete($sDest & "\docs\" & $sDoc)
    Next
    DirRemove($sDest & "\docs", 1)
    DirRemove($sDest & "\bin", 1)
    DirRemove($sDest & "\mythos_config", 1)
    
    GUICtrlSetData($idStep3, "[OK] 3. Deleting program files")
    GUICtrlSetColor($idStep3, 0x2E7D32)
    
    ; Step 4: Removing Start Menu shortcuts
    GUICtrlSetData($idStep4, "> 4. Removing Start Menu shortcuts...")
    GUICtrlSetColor($idStep4, 0x1A73E8)
    Sleep(400)
    
    DirRemove(@ProgramsCommonDir & "\au3Mythos", 1)
    DirRemove(@ProgramsDir & "\au3Mythos", 1)
    
    GUICtrlSetData($idStep4, "[OK] 4. Removing Start Menu shortcuts")
    GUICtrlSetColor($idStep4, 0x2E7D32)
    
    ; Step 5: Removing registry entries
    GUICtrlSetData($idStep5, "> 5. Removing registry entries...")
    GUICtrlSetColor($idStep5, 0x1A73E8)
    Sleep(400)
    
    RegDelete("HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\au3Mythos")
    
    GUICtrlSetData($idStep5, "[OK] 5. Removing registry entries")
    GUICtrlSetColor($idStep5, 0x2E7D32)
    Sleep(400)
    
    ; Schedule self deletion on exit
    Local $sCmdFile = @TempDir & "\mythos_uninst_" & Random(1000, 9999, 1) & ".cmd"
    Local $hFile = FileOpen($sCmdFile, 2)
    If $hFile <> -1 Then
        FileWriteLine($hFile, "@echo off")
        FileWriteLine($hFile, ":loop")
        FileWriteLine($hFile, "taskkill /F /IM Uninstall_au3Mythos_x64.exe >nul 2>&1")
        FileWriteLine($hFile, "del """ & $sDest & "\Uninstall_au3Mythos_x64.exe"" >nul 2>&1")
        FileWriteLine($hFile, "if exist """ & $sDest & "\Uninstall_au3Mythos_x64.exe"" goto loop")
        FileWriteLine($hFile, "rd """ & $sDest & """ >nul 2>&1")
        FileWriteLine($hFile, "del """ & $sCmdFile & """ & exit")
        FileClose($hFile)
        
        Run($sCmdFile, @TempDir, @SW_HIDE)
    EndIf
    
    Return ShowResult(True, "")
EndFunc

Func ShowResult($bSuccess, $sError)
    If $bSuccess Then
        GUICtrlSetData($idDesc, "au3Mythos has been successfully removed from your computer.")
        GUICtrlSetColor($idDesc, 0x2E7D32) ; Green
        GUICtrlSetState($idCancelBtn, $GUI_DISABLE)
        GUICtrlSetData($idUninstallBtn, "Finish")
        GUICtrlSetState($idUninstallBtn, $GUI_ENABLE)
    Else
        GUICtrlSetData($idDesc, "Uninstallation failed!" & @CRLF & @CRLF & "Error: " & $sError)
        GUICtrlSetColor($idDesc, 0xC62828) ; Red
        GUICtrlSetState($idCancelBtn, $GUI_DISABLE)
        GUICtrlSetData($idUninstallBtn, "Close")
        GUICtrlSetState($idUninstallBtn, $GUI_ENABLE)
    EndIf
    Return $bSuccess
EndFunc

Func CleanupTempFiles()
    FileDelete($sTempIco)
EndFunc

Func PerformUninstall(Const $sDest)
    ; 1. Rollback intercepting compiler wrapper if active
    Local $sAutoItDir = @ProgramFilesDir & "\AutoIt3"
    If FileExists($sAutoItDir & "\Au3Check_Original.exe") Then
        ProcessClose("Au3Check.exe")
        ProcessClose("Au3Check_Wrapper.exe")
        ProcessClose("Au3Check_Wrapper_x64.exe")
        
        FileDelete($sAutoItDir & "\Au3Check.exe")
        FileMove($sAutoItDir & "\Au3Check_Original.exe", $sAutoItDir & "\Au3Check.exe", $FC_OVERWRITE)
        
        If FileExists($sAutoItDir & "\Au3Check_Original.dat") Then
            FileDelete($sAutoItDir & "\Au3Check.dat")
            FileMove($sAutoItDir & "\Au3Check_Original.dat", $sAutoItDir & "\Au3Check.dat", $FC_OVERWRITE)
        EndIf
    EndIf
    
    ; 2. Terminate Settings GUI
    ProcessClose("au3Mythos_Settings_x64.exe")
    ProcessClose("au3Mythos_Settings.exe")
    
    ; 3. Delete Start Menu Shortcuts
    DirRemove(@ProgramsCommonDir & "\au3Mythos", 1)
    DirRemove(@ProgramsDir & "\au3Mythos", 1)
    
    ; 4. Delete Registry entries
    RegDelete("HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\au3Mythos")
    
    ; 5. Delete program folder content
    FileDelete($sDest & "\bin\autoit_windows_x64_scoping_analyzer.exe")
    FileDelete($sDest & "\bin\Au3Check_Wrapper_x64.exe")
    FileDelete($sDest & "\au3Mythos_Settings_x64.exe")
    FileDelete($sDest & "\mythos_config\config.json")
    
    FileDelete($sDest & "\docs\screenshots\*.png")
    DirRemove($sDest & "\docs\screenshots", 1)
    
    Local $aDocs = ["au3Mythos_User_Manual.md", "au3Mythos_Technical_Reference.md", "au3Mythos_JSON_API.md"]
    For $sDoc In $aDocs
        FileDelete($sDest & "\docs\" & $sDoc)
    Next
    DirRemove($sDest & "\docs", 1)
    DirRemove($sDest & "\bin", 1)
    DirRemove($sDest & "\mythos_config", 1)
    
    ; Schedule self deletion on exit
    Local $sCmdFile = @TempDir & "\mythos_uninst_" & Random(1000, 9999, 1) & ".cmd"
    Local $hFile = FileOpen($sCmdFile, 2)
    If $hFile <> -1 Then
        FileWriteLine($hFile, "@echo off")
        FileWriteLine($hFile, ":loop")
        FileWriteLine($hFile, "taskkill /F /IM Uninstall_au3Mythos_x64.exe >nul 2>&1")
        FileWriteLine($hFile, "del """ & $sDest & "\Uninstall_au3Mythos_x64.exe"" >nul 2>&1")
        FileWriteLine($hFile, "if exist """ & $sDest & "\Uninstall_au3Mythos_x64.exe"" goto loop")
        FileWriteLine($hFile, "rd """ & $sDest & """ >nul 2>&1")
        FileWriteLine($hFile, "del """ & $sCmdFile & """ & exit")
        FileClose($hFile)
        
        Run($sCmdFile, @TempDir, @SW_HIDE)
    EndIf
    
    Return 0
EndFunc
