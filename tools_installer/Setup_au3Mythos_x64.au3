; #UDF# =========================================================================================================================
; Name...........: Setup
; Title .........: au3Mythos Installer Setup
; Description ...: GUI/CLI setup wizard to install au3Mythos static checker and scoping analyzer.
; Author ........: Harald Frank
; ===============================================================================================================================
#pragma compile(Console, False)
#pragma compile(x64, True)
#pragma compile(Out, ..\tools_installer\Setup_au3Mythos_x64.exe)
#pragma compile(Icon, ..\resources\mythos_logo.ico)

#include <GUIConstantsEx.au3>
#include <WindowsConstants.au3>
#include <EditConstants.au3>
#include <MsgBoxConstants.au3>
#include <File.au3>

Global $bSilent = False
Global $bRunInstall = False
Global $sInstallDir = @ProgramFilesDir & "\au3Mythos"
Global $sArg = ""
Global $iRet = 0
Global $iStatus = 0

; Parse command line parameters
For $i = 1 To $CmdLine[0]
    $sArg = $CmdLine[$i]
    If StringUpper($sArg) == "/S" Or StringUpper($sArg) == "/SILENT" Then
        $bSilent = True
    ElseIf StringUpper($sArg) == "/RUNINSTALL" Then
        $bRunInstall = True
    ElseIf StringLeft(StringUpper($sArg), 5) == "/DIR=" Then
        $sInstallDir = StringMid($sArg, 6)
        ; Strip surrounding quotes if present
        If StringLeft($sInstallDir, 1) == '"' And StringRight($sInstallDir, 1) == '"' Then
            $sInstallDir = StringMid($sInstallDir, 2, StringLen($sInstallDir) - 2)
        EndIf
    EndIf
Next

; Silent Mode self-elevation if target requires admin and we are not admin
If $bSilent And StringInStr(StringUpper($sInstallDir), StringUpper(@ProgramFilesDir)) > 0 And Not IsAdmin() Then
    $iRet = ShellExecuteWait(@ScriptFullPath, $CmdLineRaw, "", "runas")
    If @error Then Exit 1
    Exit $iRet
EndIf

If $bSilent Then
    $iStatus = InstallFiles($sInstallDir)
    Exit $iStatus
EndIf

; Extract high-resolution transparent logo from resources to temp directory
Global $sTempIco = @TempDir & "\mythos_setup_logo.ico"
FileInstall("..\resources\mythos_logo.ico", $sTempIco, 1)

; Register cleanup function to delete temp file upon exit
OnAutoItExitRegister("CleanupTempFiles")

; GUI Mode Setup Wizard
Global $hMainGui = GUICreate("au3Mythos Setup Wizard", 550, 360, -1, -1, BitOR($WS_OVERLAPPEDWINDOW, $WS_CLIPSIBLINGS))
GUISetBkColor(0x1A252C, $hMainGui)

; Right panel background (Solid light gray using a Label)
Global $idRightBg = GUICtrlCreateLabel("", 160, 0, 390, 360)
GUICtrlSetBkColor($idRightBg, 0xF5F6F7)
GUICtrlSetState($idRightBg, $GUI_DISABLE)

; Branded Icon in Left Panel (Takes 80% of width = 128px, centered. Naturally inherits parent GUI dark bkcolor)
Global $idIcon = GUICtrlCreateIcon($sTempIco, -1, 16, 20, 128, 128)
GUICtrlSetBkColor($idIcon, $GUI_BKCOLOR_TRANSPARENT)

; Text labels with transparent backgrounds on the dark left panel
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
Global $idTitle = GUICtrlCreateLabel("Install au3Mythos Scoping Analyzer", 185, 20, 340, 30)
GUICtrlSetFont(-1, 14, 800, 0, "Outfit")
GUICtrlSetColor(-1, 0x1A252C)
GUICtrlSetBkColor($idTitle, $GUI_BKCOLOR_TRANSPARENT)

Global $idDesc = GUICtrlCreateLabel("This wizard will install au3Mythos, the advanced static checking and scoping framework, on your computer." & @CRLF & @CRLF & "Please choose a destination directory for the installation below:", 185, 60, 340, 80)
GUICtrlSetFont(-1, 9.5, 400, 0, "Outfit")
GUICtrlSetColor(-1, 0x3C4D56)
GUICtrlSetBkColor($idDesc, $GUI_BKCOLOR_TRANSPARENT)

Global $idFolderLbl = GUICtrlCreateLabel("Destination Folder:", 185, 150, 340, 20)
GUICtrlSetFont(-1, 9.5, 600, 0, "Outfit")
GUICtrlSetBkColor($idFolderLbl, $GUI_BKCOLOR_TRANSPARENT)

Global $idDirInput = GUICtrlCreateInput($sInstallDir, 185, 175, 255, 22)
GUICtrlSetFont(-1, 9.5, 400, 0, "Outfit")

Global $idBrowseBtn = GUICtrlCreateButton("Browse...", 450, 174, 75, 24)
GUICtrlSetFont(-1, 9, 400, 0, "Outfit")

; Page 2 Controls (Checklist Items, initially hidden)
Global $idStep1 = GUICtrlCreateLabel("  1. Creating installation directories...", 185, 130, 340, 20)
GUICtrlSetFont(-1, 9.5, 400, 0, "Outfit")
GUICtrlSetColor(-1, 0x8C9BA5)
GUICtrlSetBkColor(-1, $GUI_BKCOLOR_TRANSPARENT)
GUICtrlSetState(-1, $GUI_HIDE)

Global $idStep2 = GUICtrlCreateLabel("  2. Copying scoping analyzer and wrapper...", 185, 155, 340, 20)
GUICtrlSetFont(-1, 9.5, 400, 0, "Outfit")
GUICtrlSetColor(-1, 0x8C9BA5)
GUICtrlSetBkColor(-1, $GUI_BKCOLOR_TRANSPARENT)
GUICtrlSetState(-1, $GUI_HIDE)

Global $idStep3 = GUICtrlCreateLabel("  3. Copying Settings Manager...", 185, 180, 340, 20)
GUICtrlSetFont(-1, 9.5, 400, 0, "Outfit")
GUICtrlSetColor(-1, 0x8C9BA5)
GUICtrlSetBkColor(-1, $GUI_BKCOLOR_TRANSPARENT)
GUICtrlSetState(-1, $GUI_HIDE)

Global $idStep4 = GUICtrlCreateLabel("  4. Creating Start Menu shortcuts...", 185, 205, 340, 20)
GUICtrlSetFont(-1, 9.5, 400, 0, "Outfit")
GUICtrlSetColor(-1, 0x8C9BA5)
GUICtrlSetBkColor(-1, $GUI_BKCOLOR_TRANSPARENT)
GUICtrlSetState(-1, $GUI_HIDE)

Global $idStep5 = GUICtrlCreateLabel("  5. Registering under Windows Apps & Features...", 185, 230, 340, 20)
GUICtrlSetFont(-1, 9.5, 400, 0, "Outfit")
GUICtrlSetColor(-1, 0x8C9BA5)
GUICtrlSetBkColor(-1, $GUI_BKCOLOR_TRANSPARENT)
GUICtrlSetState(-1, $GUI_HIDE)

Global $idSep = GUICtrlCreateGraphic(175, 300, 360, 1)
GUICtrlSetBkColor(-1, 0xD0D5DD)

Global $idInstallBtn = GUICtrlCreateButton("Next", 360, 315, 80, 26)
Global $idCancelBtn = GUICtrlCreateButton("Cancel", 450, 315, 80, 26)

GUISetState(@SW_SHOW, $hMainGui)

Global $bFirstRun = True
Global $nMsg = 0
Global $sSelDir = ""
Global $iChoice = 0
Global $sRelaunchArgs = ""
Global $iRelaunchRet = 0
Global $iInstallStatus = 0
Global $nMsg2 = 0
Global $iCurrentPage = 1

While 1
    $nMsg = GUIGetMsg()
    
    ; Auto-trigger Page 2 transition if relaunching in elevated mode to run installer
    If $bFirstRun And $bRunInstall Then
        $bFirstRun = False
        ShowPage2()
        RunInstallSequence()
    EndIf
    
    Switch $nMsg
        Case $GUI_EVENT_CLOSE
            Exit 0
        Case $idCancelBtn
            If $idCancelBtn == $nMsg Then Exit 0
        Case $idAboutBtn
            MsgBox($MB_ICONINFORMATION + $MB_OK, "About au3Mythos Setup", "au3Mythos Static Analyzer Setup" & @CRLF & "Version 1.1.0" & @CRLF & @CRLF & "Developed by Harald Frank" & @CRLF & "Copyright (C) 2026. All rights reserved.", 0, $hMainGui)
        Case $idBrowseBtn
            $sSelDir = FileSelectFolder("Select Installation Directory", "", 1, GUICtrlRead($idDirInput), $hMainGui)
            If Not @error And $sSelDir <> "" Then
                GUICtrlSetData($idDirInput, $sSelDir & "\au3Mythos")
            EndIf
        Case $idInstallBtn
            ; If we are on Page 2 and installation finished, this button functions as "Finish" / "Beenden" or "Close"
            If $iCurrentPage == 2 Then
                Exit 0
            EndIf
            
            $sInstallDir = GUICtrlRead($idDirInput)
            If $sInstallDir == "" Then
                MsgBox($MB_ICONERROR + $MB_OK, "Error", "Please select a valid installation directory.", 0, $hMainGui)
                ContinueLoop
            EndIf
            
            ; Defer self-elevation until user clicks "Next"
            If StringInStr(StringUpper($sInstallDir), StringUpper(@ProgramFilesDir)) > 0 And Not IsAdmin() Then
                $iChoice = MsgBox($MB_ICONINFORMATION + $MB_OKCANCEL, "Administrator Privileges Required", "au3Mythos Setup requires Administrator privileges to write files to 'Program Files', create Start Menu folders, and register under Windows Apps & Features." & @CRLF & @CRLF & "Please click OK to authorize UAC elevation, or Cancel to return.", 0, $hMainGui)
                If $iChoice <> $IDOK Then ContinueLoop
                
                ; Hide parent window immediately before UAC prompts to prevent duplicate/stuck GUI views
                GUISetState(@SW_HIDE, $hMainGui)
                
                ; Relaunch elevated and auto-run the installation
                $sRelaunchArgs = '/RUNINSTALL /DIR="' & $sInstallDir & '"'
                ShellExecute(@ScriptFullPath, $sRelaunchArgs, "", "runas")
                If @error Then
                    MsgBox($MB_ICONERROR + $MB_OK, "Elevation Failed", "Administrator privileges were not granted. Installation cancelled.", 0)
                    GUISetState(@SW_SHOW, $hMainGui) ; Restore parent view if elevation was rejected
                    ContinueLoop
                EndIf
                Exit 0 ; Elevated child started, exit parent immediately to keep only one window
            EndIf
            
            ; Transition to Page 2 (either because we are already admin or target does not require admin)
            ShowPage2()
            RunInstallSequence()
    EndSwitch
WEnd

Func ShowPage2()
    $iCurrentPage = 2
    GUICtrlSetState($idFolderLbl, $GUI_HIDE)
    GUICtrlSetState($idDirInput, $GUI_HIDE)
    GUICtrlSetState($idBrowseBtn, $GUI_HIDE)
    
    GUICtrlSetState($idStep1, $GUI_SHOW)
    GUICtrlSetState($idStep2, $GUI_SHOW)
    GUICtrlSetState($idStep3, $GUI_SHOW)
    GUICtrlSetState($idStep4, $GUI_SHOW)
    GUICtrlSetState($idStep5, $GUI_SHOW)
    
    GUICtrlSetData($idTitle, "Installing au3Mythos...")
    GUICtrlSetData($idDesc, "Please wait while the installation processes are executed:")
    GUICtrlSetColor($idDesc, 0x3C4D56)
    
    GUICtrlSetState($idInstallBtn, $GUI_DISABLE)
    GUICtrlSetState($idCancelBtn, $GUI_DISABLE)
EndFunc

Func RunInstallSequence()
    Local $sDest = $sInstallDir
    
    ; Step 1: Create directories
    GUICtrlSetData($idStep1, "> 1. Creating installation directories...")
    GUICtrlSetColor($idStep1, 0x1A73E8) ; Blue (In Progress)
    Sleep(400)
    
    If Not DirCreate($sDest) Or Not DirCreate($sDest & "\bin") Or Not DirCreate($sDest & "\docs") Or Not DirCreate($sDest & "\docs\screenshots") Or Not DirCreate($sDest & "\mythos_config") Then
        GUICtrlSetData($idStep1, "[FAIL] 1. Creating installation directories")
        GUICtrlSetColor($idStep1, 0xC62828) ; Red
        Return ShowResult(False, "Failed to create installation directories at target path. Please check write permissions.")
    EndIf
    
    GUICtrlSetData($idStep1, "[OK] 1. Creating installation directories")
    GUICtrlSetColor($idStep1, 0x2E7D32) ; Green (Success)
    
    ; Step 2: Copy scoping analyzer and wrapper
    GUICtrlSetData($idStep2, "> 2. Copying scoping analyzer and wrapper...")
    GUICtrlSetColor($idStep2, 0x1A73E8)
    Sleep(400)
    
    Local $sSourceRoot = @ScriptDir
    If Not FileExists($sSourceRoot & "\bin\autoit_windows_x64_scoping_analyzer.exe") And FileExists($sSourceRoot & "\..\bin\autoit_windows_x64_scoping_analyzer.exe") Then
        $sSourceRoot = @ScriptDir & "\.."
    EndIf
    
    Local $sSourceBin = $sSourceRoot & "\bin"
    Local $sSourceDocs = $sSourceRoot & "\docs"
    Local $sSourceConfig = $sSourceRoot & "\mythos_config"
    If Not FileExists($sSourceConfig & "\config.json") And FileExists($sSourceRoot & "\resources\mythos_config\config.json") Then
        $sSourceConfig = $sSourceRoot & "\resources\mythos_config"
    EndIf
    Local $sSourceInstaller = $sSourceRoot & "\tools_installer"
    
    If FileExists($sSourceBin & "\autoit_windows_x64_scoping_analyzer.exe") Then
        If Not FileCopy($sSourceBin & "\autoit_windows_x64_scoping_analyzer.exe", $sDest & "\bin\autoit_windows_x64_scoping_analyzer.exe", $FC_OVERWRITE) Then
            GUICtrlSetData($idStep2, "[FAIL] 2. Copying scoping analyzer and wrapper")
            GUICtrlSetColor($idStep2, 0xC62828)
            Return ShowResult(False, "Failed to copy autoit_windows_x64_scoping_analyzer.exe scoping engine.")
        EndIf
    EndIf
    
    If FileExists($sSourceBin & "\Au3Check_Wrapper_x64.exe") Then
        if Not FileCopy($sSourceBin & "\Au3Check_Wrapper_x64.exe", $sDest & "\bin\Au3Check_Wrapper_x64.exe", $FC_OVERWRITE) Then
            GUICtrlSetData($idStep2, "[FAIL] 2. Copying scoping analyzer and wrapper")
            GUICtrlSetColor($idStep2, 0xC62828)
            Return ShowResult(False, "Failed to copy Au3Check_Wrapper_x64.exe binary.")
        EndIf
    EndIf
    
    GUICtrlSetData($idStep2, "[OK] 2. Copying scoping analyzer and wrapper")
    GUICtrlSetColor($idStep2, 0x2E7D32)
    
    ; Step 3: Copy Settings Manager
    GUICtrlSetData($idStep3, "> 3. Copying Settings Manager...")
    GUICtrlSetColor($idStep3, 0x1A73E8)
    Sleep(400)
    
    Local $bSettingsCopied = False
    If FileExists($sSourceBin & "\au3Mythos_Settings_x64.exe") Then
        If FileCopy($sSourceBin & "\au3Mythos_Settings_x64.exe", $sDest & "\au3Mythos_Settings_x64.exe", $FC_OVERWRITE) Then $bSettingsCopied = True
    ElseIf FileExists($sSourceRoot & "\au3Mythos_Settings_x64.exe") Then
        If FileCopy($sSourceRoot & "\au3Mythos_Settings_x64.exe", $sDest & "\au3Mythos_Settings_x64.exe", $FC_OVERWRITE) Then $bSettingsCopied = True
    EndIf
    
    If Not $bSettingsCopied Then
        GUICtrlSetData($idStep3, "[FAIL] 3. Copying Settings Manager")
        GUICtrlSetColor($idStep3, 0xC62828)
        Return ShowResult(False, "Failed to copy au3Mythos_Settings_x64.exe Settings Manager.")
    EndIf
    
    ; Copy Uninstaller payload
    Local $bUninstCopied = False
    If FileExists($sSourceInstaller & "\Uninstall_au3Mythos_x64.exe") Then
        If FileCopy($sSourceInstaller & "\Uninstall_au3Mythos_x64.exe", $sDest & "\Uninstall_au3Mythos_x64.exe", $FC_OVERWRITE) Then $bUninstCopied = True
    ElseIf FileExists($sSourceRoot & "\Uninstall_au3Mythos_x64.exe") Then
        If FileCopy($sSourceRoot & "\Uninstall_au3Mythos_x64.exe", $sDest & "\Uninstall_au3Mythos_x64.exe", $FC_OVERWRITE) Then $bUninstCopied = True
    ElseIf FileExists($sSourceBin & "\Uninstall_au3Mythos_x64.exe") Then
        If FileCopy($sSourceBin & "\Uninstall_au3Mythos_x64.exe", $sDest & "\Uninstall_au3Mythos_x64.exe", $FC_OVERWRITE) Then $bUninstCopied = True
    EndIf
    
    If Not $bUninstCopied Then
        GUICtrlSetData($idStep3, "[FAIL] 3. Copying Settings Manager")
        GUICtrlSetColor($idStep3, 0xC62828)
        Return ShowResult(False, "Failed to copy Uninstall_au3Mythos_x64.exe uninstaller payload.")
    EndIf
    
    ; Copy Default Config template
    If FileExists($sSourceConfig & "\config.json") Then
        FileCopy($sSourceConfig & "\config.json", $sDest & "\mythos_config\config.json", $FC_OVERWRITE)
    EndIf
    
    ; Copy Documentation Files
    Local $aDocs = ["au3Mythos_User_Manual.md", "au3Mythos_Technical_Reference.md", "au3Mythos_JSON_API.md"]
    For $sDoc In $aDocs
        If FileExists($sSourceDocs & "\" & $sDoc) Then
            FileCopy($sSourceDocs & "\" & $sDoc, $sDest & "\docs\" & $sDoc, $FC_OVERWRITE)
        EndIf
    Next
    
    ; Copy Screenshots
    Local $hSearch = FileFindFirstFile($sSourceDocs & "\screenshots\*.png")
    If $hSearch <> -1 Then
        While 1
            Local $sFile = FileFindNextFile($hSearch)
            If @error Then ExitLoop
            FileCopy($sSourceDocs & "\screenshots\" & $sFile, $sDest & "\docs\screenshots\" & $sFile, $FC_OVERWRITE)
        WEnd
        FileClose($hSearch)
    EndIf
    
    GUICtrlSetData($idStep3, "[OK] 3. Copying Settings Manager")
    GUICtrlSetColor($idStep3, 0x2E7D32)
    
    ; Step 4: Create Start Menu shortcuts
    GUICtrlSetData($idStep4, "> 4. Creating Start Menu shortcuts...")
    GUICtrlSetColor($idStep4, 0x1A73E8)
    Sleep(400)
    
    Local $sShortcutsFolder = @ProgramsCommonDir & "\au3Mythos"
    If Not IsAdmin() Or Not DirCreate($sShortcutsFolder) Then
        $sShortcutsFolder = @ProgramsDir & "\au3Mythos"
        DirCreate($sShortcutsFolder)
    EndIf
    
    FileCreateShortcut($sDest & "\au3Mythos_Settings_x64.exe", $sShortcutsFolder & "\au3Mythos Settings Manager.lnk", $sDest)
    FileCreateShortcut($sDest & "\docs\au3Mythos_User_Manual.md", $sShortcutsFolder & "\au3Mythos User Manual.lnk", $sDest & "\docs")
    FileCreateShortcut($sDest & "\Uninstall_au3Mythos_x64.exe", $sShortcutsFolder & "\Uninstall au3Mythos.lnk", $sDest)
    
    GUICtrlSetData($idStep4, "[OK] 4. Creating Start Menu shortcuts")
    GUICtrlSetColor($idStep4, 0x2E7D32)
    
    ; Step 5: Register under Apps & Features
    GUICtrlSetData($idStep5, "> 5. Registering under Windows Apps & Features...")
    GUICtrlSetColor($idStep5, 0x1A73E8)
    Sleep(400)
    
    If IsAdmin() And StringInStr($sDest, "Temp") == 0 Then
        Local $sUnReg = "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\au3Mythos"
        RegWrite($sUnReg, "DisplayName", "REG_SZ", "au3Mythos Static Checker & Scoping Analyzer")
        RegWrite($sUnReg, "DisplayVersion", "REG_SZ", "1.1.0")
        RegWrite($sUnReg, "Publisher", "REG_SZ", "Harald Frank")
        RegWrite($sUnReg, "UninstallString", "REG_SZ", '"' & $sDest & '\Uninstall_au3Mythos_x64.exe"')
        RegWrite($sUnReg, "DisplayIcon", "REG_SZ", '"' & $sDest & '\au3Mythos_Settings_x64.exe",0')
        RegWrite($sUnReg, "InstallLocation", "REG_SZ", $sDest)
        RegWrite($sUnReg, "EstimatedSize", "REG_DWORD", 11200)
        RegWrite($sUnReg, "NoModify", "REG_DWORD", 1)
        RegWrite($sUnReg, "NoRepair", "REG_DWORD", 1)
    EndIf
    
    GUICtrlSetData($idStep5, "[OK] 5. Registering under Windows Apps & Features")
    GUICtrlSetColor($idStep5, 0x2E7D32)
    Sleep(400)
    
    Return ShowResult(True, "")
EndFunc

Func ShowResult($bSuccess, $sError)
    If $bSuccess Then
        GUICtrlSetData($idDesc, "Installation completed successfully!" & @CRLF & @CRLF & "au3Mythos is now installed and ready to be configured via the Settings Manager.")
        GUICtrlSetColor($idDesc, 0x2E7D32) ; Green
        GUICtrlSetState($idCancelBtn, $GUI_DISABLE)
        GUICtrlSetData($idInstallBtn, "Finish")
        GUICtrlSetState($idInstallBtn, $GUI_ENABLE)
    Else
        GUICtrlSetData($idDesc, "Installation failed!" & @CRLF & @CRLF & "Error: " & $sError)
        GUICtrlSetColor($idDesc, 0xC62828) ; Red
        GUICtrlSetState($idCancelBtn, $GUI_DISABLE)
        GUICtrlSetData($idInstallBtn, "Close")
        GUICtrlSetState($idInstallBtn, $GUI_ENABLE)
    EndIf
    Return $bSuccess
EndFunc

Func CleanupTempFiles()
    FileDelete($sTempIco)
EndFunc

Func InstallFiles(Const $sDest)
    ; Create target directories
    If Not DirCreate($sDest) Then Return 1
    If Not DirCreate($sDest & "\bin") Then Return 1
    If Not DirCreate($sDest & "\docs") Then Return 1
    If Not DirCreate($sDest & "\docs\screenshots") Then Return 1
    If Not DirCreate($sDest & "\mythos_config") Then Return 1
    
    ; Resolve source directory root dynamically
    Local $sSourceRoot = @ScriptDir
    If Not FileExists($sSourceRoot & "\bin\autoit_windows_x64_scoping_analyzer.exe") And FileExists($sSourceRoot & "\..\bin\autoit_windows_x64_scoping_analyzer.exe") Then
        $sSourceRoot = @ScriptDir & "\.."
    EndIf
    
    Local $sSourceBin = $sSourceRoot & "\bin"
    Local $sSourceDocs = $sSourceRoot & "\docs"
    Local $sSourceConfig = $sSourceRoot & "\mythos_config"
    If Not FileExists($sSourceConfig & "\config.json") And FileExists($sSourceRoot & "\resources\mythos_config\config.json") Then
        $sSourceConfig = $sSourceRoot & "\resources\mythos_config"
    EndIf
    Local $sSourceInstaller = $sSourceRoot & "\tools_installer"
    
    ; Copy Analyzer and GUI Manager Binaries
    If FileExists($sSourceBin & "\autoit_windows_x64_scoping_analyzer.exe") Then
        If Not FileCopy($sSourceBin & "\autoit_windows_x64_scoping_analyzer.exe", $sDest & "\bin\autoit_windows_x64_scoping_analyzer.exe", $FC_OVERWRITE) Then Return 2
    EndIf
    
    If FileExists($sSourceBin & "\au3Mythos_Settings_x64.exe") Then
        If Not FileCopy($sSourceBin & "\au3Mythos_Settings_x64.exe", $sDest & "\au3Mythos_Settings_x64.exe", $FC_OVERWRITE) Then Return 3
    ElseIf FileExists($sSourceRoot & "\au3Mythos_Settings_x64.exe") Then
        If Not FileCopy($sSourceRoot & "\au3Mythos_Settings_x64.exe", $sDest & "\au3Mythos_Settings_x64.exe", $FC_OVERWRITE) Then Return 3
    EndIf

    If FileExists($sSourceBin & "\Au3Check_Wrapper_x64.exe") Then
        If Not FileCopy($sSourceBin & "\Au3Check_Wrapper_x64.exe", $sDest & "\bin\Au3Check_Wrapper_x64.exe", $FC_OVERWRITE) Then Return 4
    EndIf
    
    ; Copy Uninstaller payload
    If FileExists($sSourceInstaller & "\Uninstall_au3Mythos_x64.exe") Then
        If Not FileCopy($sSourceInstaller & "\Uninstall_au3Mythos_x64.exe", $sDest & "\Uninstall_au3Mythos_x64.exe", $FC_OVERWRITE) Then Return 5
    ElseIf FileExists($sSourceRoot & "\Uninstall_au3Mythos_x64.exe") Then
        If Not FileCopy($sSourceRoot & "\Uninstall_au3Mythos_x64.exe", $sDest & "\Uninstall_au3Mythos_x64.exe", $FC_OVERWRITE) Then Return 5
    ElseIf FileExists($sSourceBin & "\Uninstall_au3Mythos_x64.exe") Then
        If Not FileCopy($sSourceBin & "\Uninstall_au3Mythos_x64.exe", $sDest & "\Uninstall_au3Mythos_x64.exe", $FC_OVERWRITE) Then Return 5
    EndIf
    
    ; Copy Default Config template
    If FileExists($sSourceConfig & "\config.json") Then
        If Not FileCopy($sSourceConfig & "\config.json", $sDest & "\mythos_config\config.json", $FC_OVERWRITE) Then Return 6
    EndIf
    
    ; Copy Documentation Files
    Local $aDocs = ["au3Mythos_User_Manual.md", "au3Mythos_Technical_Reference.md", "au3Mythos_JSON_API.md"]
    For $sDoc In $aDocs
        If FileExists($sSourceDocs & "\" & $sDoc) Then
            FileCopy($sSourceDocs & "\" & $sDoc, $sDest & "\docs\" & $sDoc, $FC_OVERWRITE)
        EndIf
    Next
    
    ; Copy Screenshots
    Local $hSearch = FileFindFirstFile($sSourceDocs & "\screenshots\*.png")
    If $hSearch <> -1 Then
        While 1
            Local $sFile = FileFindNextFile($hSearch)
            If @error Then ExitLoop
            FileCopy($sSourceDocs & "\screenshots\" & $sFile, $sDest & "\docs\screenshots\" & $sFile, $FC_OVERWRITE)
        WEnd
        FileClose($hSearch)
    EndIf
    
    ; Create Start Menu shortcuts
    Local $sShortcutsFolder = @ProgramsCommonDir & "\au3Mythos"
    If Not IsAdmin() Or Not DirCreate($sShortcutsFolder) Then
        $sShortcutsFolder = @ProgramsDir & "\au3Mythos"
        DirCreate($sShortcutsFolder)
    EndIf
    
    FileCreateShortcut($sDest & "\au3Mythos_Settings_x64.exe", $sShortcutsFolder & "\au3Mythos Settings Manager.lnk", $sDest)
    FileCreateShortcut($sDest & "\docs\au3Mythos_User_Manual.md", $sShortcutsFolder & "\au3Mythos User Manual.lnk", $sDest & "\docs")
    FileCreateShortcut($sDest & "\Uninstall_au3Mythos_x64.exe", $sShortcutsFolder & "\Uninstall au3Mythos.lnk", $sDest)
    
    ; Write Uninstall Registry entries
    If IsAdmin() And StringInStr($sDest, "Temp") == 0 Then
        Local $sUnReg = "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\au3Mythos"
        RegWrite($sUnReg, "DisplayName", "REG_SZ", "au3Mythos Static Checker & Scoping Analyzer")
        RegWrite($sUnReg, "DisplayVersion", "REG_SZ", "1.1.0")
        RegWrite($sUnReg, "Publisher", "REG_SZ", "Harald Frank")
        RegWrite($sUnReg, "UninstallString", "REG_SZ", '"' & $sDest & '\Uninstall_au3Mythos_x64.exe"')
        RegWrite($sUnReg, "DisplayIcon", "REG_SZ", '"' & $sDest & '\au3Mythos_Settings_x64.exe",0')
        RegWrite($sUnReg, "InstallLocation", "REG_SZ", $sDest)
        RegWrite($sUnReg, "EstimatedSize", "REG_DWORD", 11200)
        RegWrite($sUnReg, "NoModify", "REG_DWORD", 1)
        RegWrite($sUnReg, "NoRepair", "REG_DWORD", 1)
    EndIf
    
    Return 0
EndFunc
