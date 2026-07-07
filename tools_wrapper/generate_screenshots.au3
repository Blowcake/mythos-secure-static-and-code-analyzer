#NoTrayIcon
Opt("MustDeclareVars", 1)
Opt("WinTitleMatchMode", 1)

#include <ScreenCapture.au3>
#include <GuiTab.au3>
#include <WindowsConstants.au3>

Global $g_hWnd = 0

Main()

; #FUNCTION# ====================================================================================================================
; Name...........: Main
; Description ...: Core orchestrator for the Settings Manager GUI screenshot generation.
; Syntax.........: Main()
; Parameters ....: None.
; Return values .: None.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func Main()
    Local $sProjectRoot = @ScriptDir & "\.."
    Local $sOutputDir = $sProjectRoot & "\docs\screenshots"
    Local $sSettingsExe = $sProjectRoot & "\bin\au3Mythos_Settings_x64.exe"

    If Not FileExists($sOutputDir) Then DirCreate($sOutputDir)

    ConsoleWrite("=== STARTING SETTINGS GUI SCREENSHOT AUTOMATION ===" & @CRLF)

    ; Terminate any existing settings GUI processes
    ProcessClose("au3Mythos_Settings_x64.exe")
    Sleep(500)

    ; Launch settings GUI
    Run($sSettingsExe, $sProjectRoot & "\bin")

    ; --- Scene 1: Startup Splash Screen ---
    ConsoleWrite("Capturing Scene 1: Splash Screen..." & @CRLF)
    Local $hSplash = WinWait("au3Mythos Startup", "", 5)
    If $hSplash Then
        WinActivate($hSplash)
        WinWaitActive($hSplash, "", 3)
        Sleep(200)
        _ScreenCapture_CaptureWnd($sOutputDir & "\win32_settings_splash.png", $hSplash)
        ConsoleWrite("PASS: Captured Splash Screen" & @CRLF)
    Else
        ConsoleWrite("WARNING: Splash Screen window not found or loaded too fast!" & @CRLF)
    EndIf

    ; --- Scene 2: Main Routing & Callers Tab ---
    ConsoleWrite("Waiting for Main Settings Manager window..." & @CRLF)
    $g_hWnd = WinWait("au3Mythos - Au3Check Settings Manager", "", 10)
    If Not $g_hWnd Then
        ConsoleWrite("FAIL: Main settings GUI window not found!" & @CRLF)
        Exit 1
    EndIf

    WinActivate($g_hWnd)
    WinWaitActive($g_hWnd, "", 5)
    Sleep(1000)

    ConsoleWrite("Capturing Scene 2: Tab 1 (Routing & Callers)..." & @CRLF)
    _ScreenCapture_CaptureWnd($sOutputDir & "\win32_settings_tab_routing.png", $g_hWnd)
    Sleep(500)

    ; Get Tab Control
    Local $hTab = ControlGetHandle($g_hWnd, "", "[CLASS:SysTabControl32; INSTANCE:1]")
    If Not $hTab Then
        ConsoleWrite("FAIL: Tab control not found!" & @CRLF)
        Exit 1
    EndIf

    ; --- Scene 3: Tab 2 (Config Profiles) ---
    ConsoleWrite("Capturing Scene 3: Tab 2 (Config Profiles)..." & @CRLF)
    _GUICtrlTab_ClickTab($hTab, 1)
    Sleep(1000)
    _ScreenCapture_CaptureWnd($sOutputDir & "\win32_settings_tab_profiles.png", $g_hWnd)
    Sleep(500)

    ; --- Scene 4: Tab 3 (Core Settings) ---
    ConsoleWrite("Capturing Scene 4: Tab 3 (Core Settings)..." & @CRLF)
    _GUICtrlTab_ClickTab($hTab, 2)
    Sleep(1000)
    _ScreenCapture_CaptureWnd($sOutputDir & "\win32_settings_tab_engine.png", $g_hWnd)
    Sleep(500)

    ; Go back to main tab for About dialog
    _GUICtrlTab_ClickTab($hTab, 0)
    Sleep(500)

    ; --- Scene 5: About Dialog ---
    ConsoleWrite("Capturing Scene 5: About Dialog..." & @CRLF)
    WinActivate($g_hWnd)
    WinWaitActive($g_hWnd, "", 5)
    WinMenuSelectItem($g_hWnd, "", "Help", "About")
    Local $hAboutWnd = WinWait("About au3Mythos", "", 5)
    If $hAboutWnd Then
        WinActivate($hAboutWnd)
        WinWaitActive($hAboutWnd, "", 5)
        Sleep(500)
        _ScreenCapture_CaptureWnd($sOutputDir & "\win32_settings_about_dialog.png", $hAboutWnd)
        
        ; Close it
        Send("{ENTER}")
        WinWaitClose($hAboutWnd, "", 5)
        ConsoleWrite("PASS: Captured About Box" & @CRLF)
    Else
        ConsoleWrite("FAIL: About dialog not found!" & @CRLF)
        Exit 1
    EndIf

    ; Exit Main Window
    WinClose($g_hWnd)
    Sleep(1000)

    ; Ensure process is closed
    ProcessClose("au3Mythos_Settings_x64.exe")

    ConsoleWrite("PASS: Settings GUI screenshot automation completed successfully!" & @CRLF)
    Exit 0
EndFunc
