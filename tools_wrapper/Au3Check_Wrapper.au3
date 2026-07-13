#pragma compile(Console, True)
#pragma compile(x64, True)
#pragma compile(Out, ..\tools_wrapper\Au3Check_Wrapper.exe)

Opt("MustDeclareVars", 1)

#include-once
#include <AutoItConstants.au3>
#include <APIsysConstants.au3>
#include <WinAPI.au3>
#include <WinAPISys.au3>
#include "..\third_party\autoit-json-udf\JSON.au3"

; #UDF# =========================================================================================================================
; Name...........: Au3Check_Wrapper
; Title .........: Au3Check Wrapper
; Description ...: AutoIt executable wrapper that can route Au3Check calls through the Python static scoping analyzer.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================

; #FUNCTION# ====================================================================================================================
; Name...........: __JSON_GetBool
; Description ...: Safe retrieval of a boolean value from a JSON Map structure.
; Syntax.........: __JSON_GetBool($mMap, $sKey[, $bDefault = False])
; Parameters ....: $mMap     - The JSON Map object to query.
;                  $sKey     - The key to retrieve.
;                  $bDefault - The fallback value if key does not exist or is invalid.
; Return values .: True or False.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func __JSON_GetBool($mMap, $sKey, $bDefault = False)
    If Not IsMap($mMap) Or Not __JSON_MapExists($mMap, $sKey) Then Return $bDefault
    Local $vVal = $mMap[$sKey]
    If IsBool($vVal) Then Return $vVal
    If StringLower(String($vVal)) == "true" Then Return True
    If StringLower(String($vVal)) == "false" Then Return False
    Return $bDefault
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: _GetParentProcessId
; Description ...: Obtains the process ID of the parent process.
; Syntax.........: _GetParentProcessId()
; Parameters ....: None.
; Return values .: Parent Process ID (PID) on success, 0 on failure.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func _GetParentProcessId()
    Local $iPid = _WinAPI_GetCurrentProcessId()
    Local $hSnapshot = DllCall("kernel32.dll", "handle", "CreateToolhelp32Snapshot", "dword", 0x00000002, "dword", 0) ; TH32CS_SNAPPROCESS
    If @error Or $hSnapshot[0] = 0 Then Return 0
    
    Local $tProcessEntry = DllStructCreate("dword Size;dword Usage;dword ProcessID;ulong_ptr DefaultHeapID;dword ModuleID;dword Threads;dword ParentProcessID;long PriClassBase;dword Flags;wchar ExeFile[260]")
    DllStructSetData($tProcessEntry, "Size", DllStructGetSize($tProcessEntry))
    
    Local $aCall = DllCall("kernel32.dll", "bool", "Process32FirstW", "handle", $hSnapshot[0], "struct*", $tProcessEntry)
    Local $iParentPid = 0
    While Not @error And $aCall[0]
        If DllStructGetData($tProcessEntry, "ProcessID") = $iPid Then
            $iParentPid = DllStructGetData($tProcessEntry, "ParentProcessID")
            ExitLoop
        EndIf
        $aCall = DllCall("kernel32.dll", "bool", "Process32NextW", "handle", $hSnapshot[0], "struct*", $tProcessEntry)
    WEnd
    DllCall("kernel32.dll", "bool", "CloseHandle", "handle", $hSnapshot[0])
    Return $iParentPid
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: _GetProcessFullPath
; Description ...: Retrieves the absolute executable file path of a process by its PID.
; Syntax.........: _GetProcessFullPath($iPid)
; Parameters ....: $iPid - The process ID to query.
; Return values .: The file path string on success, empty string on failure.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func _GetProcessFullPath($iPid)
    If $iPid <= 0 Then Return ""
    Local $hProcess = DllCall("kernel32.dll", "handle", "OpenProcess", "dword", 0x00001000, "bool", False, "dword", $iPid) ; PROCESS_QUERY_LIMITED_INFORMATION
    If @error Or $hProcess[0] = 0 Then Return ""
    Local $tPath = DllStructCreate("wchar[1024]")
    Local $aSize = DllCall("kernel32.dll", "bool", "QueryFullProcessImageNameW", "handle", $hProcess[0], "dword", 0, "struct*", $tPath, "dword*", 1024)
    DllCall("kernel32.dll", "bool", "CloseHandle", "handle", $hProcess[0])
    If Not @error And $aSize[0] Then Return DllStructGetData($tPath, 1)
    Return ""
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: _LogRecentCaller
; Description ...: Logs information about the calling process to the settings config file.
; Syntax.........: _LogRecentCaller($sConfigPath, $sCallerName, $sCallerPath, $sParams)
; Parameters ....: $sConfigPath - Absolute path to the settings JSON config file.
;                  $sCallerName - Name of the calling executable.
;                  $sCallerPath - Absolute path of the calling executable.
;                  $sParams     - Parameters passed to the wrapper execution.
; Return values .: None.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func _LogRecentCaller($sConfigPath, $sCallerName, $sCallerPath, $sParams)
    If Not FileExists($sConfigPath) Then Return
    
    Local $hFile, $sJson = "", $mConfig
    Local $iMaxRetries = 10
    Local $iRetry = 0
    
    While $iRetry < $iMaxRetries
        $hFile = FileOpen($sConfigPath, 0) ; Read-only
        If $hFile <> -1 Then
            $sJson = FileRead($hFile)
            FileClose($hFile)
            ExitLoop
        EndIf
        $iRetry += 1
        Sleep(Random(10, 50, 1))
    WEnd
    If $iRetry == $iMaxRetries Then Return
    
    $mConfig = _JSON_Parse($sJson)
    If @error Or Not IsMap($mConfig) Then Return
    
    Local $mRecent = ""
    If __JSON_MapExists($mConfig, "recent_callers") Then
        $mRecent = $mConfig["recent_callers"]
    EndIf
    If Not IsMap($mRecent) Then
        Local $mNewRecentMap[]
        $mRecent = $mNewRecentMap
    EndIf
    
    Local $mCallerInfo[]
    $mCallerInfo["path"] = $sCallerPath
    $mCallerInfo["params"] = $sParams
    $mCallerInfo["last_called"] = @YEAR & "-" & @MON & "-" & @MDAY & "T" & @HOUR & ":" & @MIN & ":" & @SEC
    
    $mRecent[$sCallerName] = $mCallerInfo
    $mConfig["recent_callers"] = $mRecent
    
    Local $sNewJson = _JSON_Generate($mConfig)
    
    $iRetry = 0
    While $iRetry < $iMaxRetries
        $hFile = FileOpen($sConfigPath, 2) ; Overwrite
        If $hFile <> -1 Then
            FileWrite($hFile, $sNewJson)
            FileClose($hFile)
            Return
        EndIf
        $iRetry += 1
        Sleep(Random(10, 50, 1))
    WEnd
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: Main
; Description ...: Main entry point of the Au3Check wrapper executable. Coordinates option parsing, process identification, config routing, and execution of either the original Au3Check or the Python scoping analyzer.
; Syntax.........: Main()
; Parameters ....: None.
; Return values .: Return code from the executed compiler/analyzer.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func Main()
    Local $bJsonOut = False
    Local $iLookupLine = -1
    Local $sFilteredRaw = ""
    Local $sTotalOutput = ""
    Local $sChunk = ""
    Local $sArg = ""

    For $i = 1 To $CmdLine[0]
        If StringLower($CmdLine[$i]) == "-mythos" Then
            ConsoleWrite("au3Check Wrapper (au3Mythos) - Active" & @CRLF)
            Exit 0
        ElseIf StringLower($CmdLine[$i]) == "-json_out" Then
            $bJsonOut = True
        ElseIf StringLower($CmdLine[$i]) == "-lookup_runtime_line" And $i < $CmdLine[0] Then
            $iLookupLine = Int($CmdLine[$i + 1])
        EndIf
    Next

    For $i = 1 To $CmdLine[0]
        $sArg = $CmdLine[$i]
        If StringLower($sArg) == "-json_out" Then
            ContinueLoop
        EndIf
        If StringLower($sArg) == "-lookup_runtime_line" Then
            $i += 1
            ContinueLoop
        EndIf
        If StringInStr($sArg, " ") Then
            $sFilteredRaw &= ' "' & $sArg & '"'
        Else
            $sFilteredRaw &= " " & $sArg
        EndIf
    Next

    Local $sTargetFile = ""
    Local $iParentPid = 0
    Local $sParentPath = ""
    Local $sCaller = ""
    Local $sAction = "original"
    Local $sConfigPath = @AppDataDir & "\au3Mythos\mythos_config\config.json"
    Local $mConfig = ""
    Local $sMatchedConfig = ""
    Local $sJson = ""
    Local $bEnabled = False
    Local $aRules = ""
    Local $mRule = ""
    Local $sRuleCaller = ""
    Local $sRulePrefix = ""
    Local $sRuleAction = ""
    Local $bCallerMatch = False
    Local $bPathMatch = False
    Local $sPython = "python.exe"
    Local $sAnalyzer = ""
    Local $bSkipSystem = True
    Local $bExperimental = True
    Local $bNoAutoInclude = False
    Local $bSystemDeadStores = False
    Local $mSettings = ""
    Local $mConfigsMap = ""
    Local $sCmd = ""
    Local $mWarn = ""
    Local $sKey = ""
    Local $bVal = False
    Local $iPid = 0
    Local $hProcess = 0
    Local $sOutput = ""
    Local $iExitCode = 0
    Local $tExitCode = 0
    Local $aRet = 0
    Local $sOriginalExe = ""
    Local $sExtraArgs = ""
    Local $bOverrideArgs = False
    Local $sOriginalCmd = ""
    Local $mProfile = ""

    For $i = $CmdLine[0] To 1 Step -1
        $sArg = $CmdLine[$i]
        If StringLeft($sArg, 1) <> "-" Then
            If $i > 1 And StringLower($CmdLine[$i - 1]) == "-lookup_runtime_line" Then
                ContinueLoop
            EndIf
            $sTargetFile = $sArg
            ExitLoop
        EndIf
    Next
    If $sTargetFile <> "" Then
        $sTargetFile = _WinAPI_GetFullPathName($sTargetFile)
    EndIf
    
    $iParentPid = _GetParentProcessId()
    $sParentPath = _GetProcessFullPath($iParentPid)
    $sCaller = StringRegExpReplace($sParentPath, "^.*\\", "")
    If $sCaller == "" Then $sCaller = "Unknown"
    
    Local $sEnvConfig = EnvGet("MYTHOS_TEST_CONFIG")
    If $sEnvConfig <> "" Then
        $sConfigPath = $sEnvConfig
    Else
        ; If AppData config is missing, initialize it by copying the local template if found
        If Not FileExists($sConfigPath) Then
            Local $sTemplatePath = ""
            If FileExists(@ScriptDir & "\mythos_config\config.json") Then
                $sTemplatePath = @ScriptDir & "\mythos_config\config.json"
            ElseIf FileExists(@ScriptDir & "\..\resources\mythos_config\config.json") Then
                $sTemplatePath = @ScriptDir & "\..\resources\mythos_config\config.json"
            EndIf
            
            If $sTemplatePath <> "" Then
                Local $sDir = StringRegExpReplace($sConfigPath, "\\[^\\]+$", "")
                If Not FileExists($sDir) Then DirCreate($sDir)
                FileCopy($sTemplatePath, $sConfigPath, 9) ; Copy template to AppData
            EndIf
        EndIf
    EndIf
    
    If FileExists($sConfigPath) Then
        ; Log this calling program
        _LogRecentCaller($sConfigPath, $sCaller, $sParentPath, $CmdLineRaw)
        
        $sJson = FileRead($sConfigPath)
        $mConfig = _JSON_Parse($sJson)
        If Not @error And IsMap($mConfig) Then
            $bEnabled = False
            If __JSON_MapExists($mConfig, "wrapper_enabled") Then $bEnabled = $mConfig["wrapper_enabled"]
            
            If $bEnabled Then
                $aRules = ""
                If __JSON_MapExists($mConfig, "rules") Then $aRules = $mConfig["rules"]
                
                If IsArray($aRules) Then
                    For $i = 0 To UBound($aRules) - 1
                        $mRule = $aRules[$i]
                        If IsMap($mRule) And __JSON_MapExists($mRule, "caller_name") And __JSON_MapExists($mRule, "path_prefix") And __JSON_MapExists($mRule, "action") Then
                            $sRuleCaller = $mRule["caller_name"]
                            $sRulePrefix = $mRule["path_prefix"]
                            $sRuleAction = $mRule["action"]
                            
                            $bCallerMatch = ($sRuleCaller == "*" Or StringLower($sCaller) == StringLower($sRuleCaller))
                            $bPathMatch = ($sRulePrefix == "*" Or ($sTargetFile <> "" And StringInStr(StringLower($sTargetFile), StringLower($sRulePrefix)) = 1))
                            
                            If $bCallerMatch And $bPathMatch Then
                                $sAction = $sRuleAction
                                If __JSON_MapExists($mRule, "config") Then
                                    $sMatchedConfig = $mRule["config"]
                                EndIf
                                ExitLoop
                            EndIf
                        EndIf
                    Next
                EndIf
            EndIf
        EndIf
    EndIf
    
    If $sMatchedConfig == "" Then
        If StringLower($sAction) == "mythos" Then
            $sMatchedConfig = "default_mythos"
        Else
            $sMatchedConfig = "default_original"
        EndIf
    EndIf
    
    ; Load profile settings
    $mSettings = ""
    If IsMap($mConfig) And __JSON_MapExists($mConfig, "configs") Then
        $mConfigsMap = $mConfig["configs"]
        If IsMap($mConfigsMap) And __JSON_MapExists($mConfigsMap, $sMatchedConfig) Then
            $mSettings = $mConfigsMap[$sMatchedConfig]
        EndIf
    EndIf
    If Not IsMap($mSettings) And IsMap($mConfig) And __JSON_MapExists($mConfig, "mythos_settings") Then
        $mSettings = $mConfig["mythos_settings"]
    EndIf

    ; Force action to match profile type if profile has it explicitly defined
    If IsMap($mSettings) And __JSON_MapExists($mSettings, "type") Then
        $sAction = $mSettings["type"]
    EndIf

    ; Execute corresponding engine
    If StringLower($sAction) == "mythos" Or $iLookupLine > -1 Then
        $sPython = "python.exe"
        $sAnalyzer = ""
        $bSkipSystem = True
        $bExperimental = True
        $bNoAutoInclude = False
        $bSystemDeadStores = False
        
        If IsMap($mSettings) Then
            If __JSON_MapExists($mSettings, "python_path") Then $sPython = $mSettings["python_path"]
            If __JSON_MapExists($mSettings, "analyzer_path") Then $sAnalyzer = $mSettings["analyzer_path"]
            $bSkipSystem = __JSON_GetBool($mSettings, "skip_system_includes", True)
            $bExperimental = __JSON_GetBool($mSettings, "enable_experimental_checks", True)
            $bNoAutoInclude = __JSON_GetBool($mSettings, "no_auto_include_discovery", False)
            $bSystemDeadStores = __JSON_GetBool($mSettings, "enable_system_dead_stores", False)
        EndIf
        
        ; Auto-discovery / fallback for the static analyzer path
        If $sAnalyzer == "" Then
            If IsMap($mConfig) And __JSON_MapExists($mConfig, "mythos_settings") Then
                Local $mOldSettings = $mConfig["mythos_settings"]
                If IsMap($mOldSettings) And __JSON_MapExists($mOldSettings, "analyzer_path") Then
                    $sAnalyzer = $mOldSettings["analyzer_path"]
                EndIf
            EndIf
        EndIf
        
        If $sAnalyzer == "" Then
            If FileExists(@ScriptDir & "\autoit_windows_x64_scoping_analyzer.exe") Then
                $sAnalyzer = @ScriptDir & "\autoit_windows_x64_scoping_analyzer.exe"
            ElseIf FileExists(@ScriptDir & "\bin\autoit_windows_x64_scoping_analyzer.exe") Then
                $sAnalyzer = @ScriptDir & "\bin\autoit_windows_x64_scoping_analyzer.exe"
            ElseIf FileExists(@ScriptDir & "\..\src\autoit_static_analyzer\autoit_windows_x64_scoping_analyzer.py") Then
                $sAnalyzer = @ScriptDir & "\..\src\autoit_static_analyzer\autoit_windows_x64_scoping_analyzer.py"
            ElseIf FileExists(@ScriptDir & "\src\autoit_static_analyzer\autoit_windows_x64_scoping_analyzer.py") Then
                $sAnalyzer = @ScriptDir & "\src\autoit_static_analyzer\autoit_windows_x64_scoping_analyzer.py"
            EndIf
        EndIf
        
        If $sAnalyzer == "" Then
            If IsMap($mConfig) And __JSON_MapExists($mConfig, "installed_from_dir") Then
                Local $sInstDir = $mConfig["installed_from_dir"]
                If $sInstDir <> "" Then
                    If FileExists($sInstDir & "\autoit_windows_x64_scoping_analyzer.exe") Then
                        $sAnalyzer = $sInstDir & "\autoit_windows_x64_scoping_analyzer.exe"
                    ElseIf FileExists($sInstDir & "\bin\autoit_windows_x64_scoping_analyzer.exe") Then
                        $sAnalyzer = $sInstDir & "\bin\autoit_windows_x64_scoping_analyzer.exe"
                    ElseIf FileExists($sInstDir & "\..\bin\autoit_windows_x64_scoping_analyzer.exe") Then
                        $sAnalyzer = $sInstDir & "\..\bin\autoit_windows_x64_scoping_analyzer.exe"
                    ElseIf FileExists($sInstDir & "\..\src\autoit_static_analyzer\autoit_windows_x64_scoping_analyzer.py") Then
                        $sAnalyzer = $sInstDir & "\..\src\autoit_static_analyzer\autoit_windows_x64_scoping_analyzer.py"
                    ElseIf FileExists($sInstDir & "\src\autoit_static_analyzer\autoit_windows_x64_scoping_analyzer.py") Then
                        $sAnalyzer = $sInstDir & "\src\autoit_static_analyzer\autoit_windows_x64_scoping_analyzer.py"
                    EndIf
                EndIf
            EndIf
        EndIf
        
        If $sAnalyzer == "" And $sTargetFile <> "" Then
            Local $sTargetDir = StringRegExpReplace($sTargetFile, "\\[^\\]+$", "")
            If $sTargetDir <> "" Then
                Local $sCurrentSearchDir = $sTargetDir
                For $iDepth = 1 To 4
                    If FileExists($sCurrentSearchDir & "\autoit_windows_x64_scoping_analyzer.exe") Then
                        $sAnalyzer = $sCurrentSearchDir & "\autoit_windows_x64_scoping_analyzer.exe"
                        ExitLoop
                    ElseIf FileExists($sCurrentSearchDir & "\bin\autoit_windows_x64_scoping_analyzer.exe") Then
                        $sAnalyzer = $sCurrentSearchDir & "\bin\autoit_windows_x64_scoping_analyzer.exe"
                        ExitLoop
                    ElseIf FileExists($sCurrentSearchDir & "\src\autoit_static_analyzer\autoit_windows_x64_scoping_analyzer.py") Then
                        $sAnalyzer = $sCurrentSearchDir & "\src\autoit_static_analyzer\autoit_windows_x64_scoping_analyzer.py"
                        ExitLoop
                    EndIf
                    $sCurrentSearchDir = StringRegExpReplace($sCurrentSearchDir, "\\[^\\]+$", "")
                    If $sCurrentSearchDir == "" Or StringRight($sCurrentSearchDir, 1) == ":" Then ExitLoop
                Next
            EndIf
        EndIf
        
        If $sAnalyzer == "" Then
            ConsoleWrite('"' & @ScriptFullPath & '"(0,0) : error: au3Mythos static analyzer engine path is not configured and could not be auto-discovered.' & @CRLF)
            Exit 3
        EndIf
        
        ; Build the command line depending on whether it is an executable or a python script
        $sCmd = ""
        Local $sAnalyzerArgs = ""
        If $iLookupLine > -1 Then
            $sAnalyzerArgs = '--lookup-runtime-line ' & $iLookupLine
            If $bJsonOut Then $sAnalyzerArgs &= " --json-out"
            $sAnalyzerArgs &= ' "' & $sTargetFile & '"'
        Else
            $sAnalyzerArgs = $sFilteredRaw
            If $bJsonOut Then $sAnalyzerArgs &= " --json-out"
        EndIf

        If StringRight(StringLower($sAnalyzer), 4) == ".exe" Then
            $sCmd = '"' & $sAnalyzer & '" ' & $sAnalyzerArgs
        Else
            $sCmd = '"' & $sPython & '" "' & $sAnalyzer & '" ' & $sAnalyzerArgs
        EndIf

        If $iLookupLine == -1 Then
            If $bSkipSystem Then $sCmd &= " --skip-system-includes"
            If $bExperimental Then $sCmd &= " --enable-experimental-checks"
            If $bNoAutoInclude Then $sCmd &= " --no-auto-include-discovery"
            If $bSystemDeadStores Then $sCmd &= " --enable-system-dead-stores"
            
            ; Append GUI warnings configuration if not overridden on the command line
            If IsMap($mSettings) And __JSON_MapExists($mSettings, "warnings") Then
                $mWarn = $mSettings["warnings"]
                If IsMap($mWarn) Then
                    For $i = 1 To 7
                        $sKey = String($i)
                        If __JSON_MapExists($mWarn, $sKey) Then
                            $bVal = $mWarn[$sKey]
                            If IsBool($bVal) And $bVal Then
                                $sCmd &= " -w " & $sKey
                            ElseIf String($bVal) == "true" Then
                                $sCmd &= " -w " & $sKey
                            Else
                                $sCmd &= " -w -" & $sKey
                            EndIf
                        EndIf
                    Next
                EndIf
            EndIf
        EndIf
        
        $iPid = Run($sCmd, @WorkingDir, @SW_HIDE, $STDIN_CHILD + $STDOUT_CHILD + $STDERR_CHILD)
        If @error Then
            ConsoleWrite('"' & @ScriptFullPath & '"(0,0) : error: Failed to execute au3Mythos static analyzer.' & @CRLF)
            Exit 3
        EndIf
        $hProcess = DllCall("kernel32.dll", "handle", "OpenProcess", "dword", 0x00000400, "bool", False, "dword", $iPid)
        
        $sOutput = ""
        While 1
            $sOutput = StdoutRead($iPid)
            If @error Then ExitLoop
            If $sOutput <> "" Then ConsoleWrite($sOutput)
            
            $sOutput = StderrRead($iPid)
            If @error Then ExitLoop
            If $sOutput <> "" Then ConsoleWriteError($sOutput)
            
            Sleep(10)
        WEnd
        
        ProcessWaitClose($iPid)
        $iExitCode = 0
        If Not @error And $hProcess[0] <> 0 Then
            $tExitCode = DllStructCreate("dword")
            $aRet = DllCall("kernel32.dll", "bool", "GetExitCodeProcess", "handle", $hProcess[0], "struct*", $tExitCode)
            If Not @error And $aRet[0] Then
                $iExitCode = DllStructGetData($tExitCode, 1)
            EndIf
            DllCall("kernel32.dll", "bool", "CloseHandle", "handle", $hProcess[0])
        EndIf
        Exit $iExitCode
    Else
        ; Run original Au3Check_Original.exe
        $sOriginalExe = @ScriptDir & "\Au3Check_Original.exe"
        If Not FileExists($sOriginalExe) Then
            $sOriginalExe = "C:\Program Files (x86)\AutoIt3\Au3Check_Original.exe"
        EndIf
        
        If Not FileExists($sOriginalExe) Then
            ConsoleWrite('"' & @ScriptFullPath & '"(0,0) : error: Au3Check_Original.exe not found.' & @CRLF)
            Exit 3
        EndIf
        
        $sExtraArgs = ""
        $bOverrideArgs = False
        If IsMap($mConfig) And __JSON_MapExists($mConfig, "configs") Then
            $mConfigsMap = $mConfig["configs"]
            If IsMap($mConfigsMap) And __JSON_MapExists($mConfigsMap, $sMatchedConfig) Then
                $mProfile = $mConfigsMap[$sMatchedConfig]
                If IsMap($mProfile) Then
                    If __JSON_MapExists($mProfile, "extra_args") Then $sExtraArgs = $mProfile["extra_args"]
                    $bOverrideArgs = __JSON_GetBool($mProfile, "override_args", False)
                EndIf
            EndIf
        EndIf
        
        $sOriginalCmd = $sFilteredRaw
        If $bOverrideArgs Then
            $sOriginalCmd = $sExtraArgs & ' "' & $sTargetFile & '"'
        ElseIf $sExtraArgs <> "" Then
            $sOriginalCmd = $sFilteredRaw & " " & $sExtraArgs
        EndIf
        
        $iPid = Run('"' & $sOriginalExe & '" ' & $sOriginalCmd, @WorkingDir, @SW_HIDE, $STDIN_CHILD + $STDOUT_CHILD + $STDERR_CHILD)
        If @error Then
            ConsoleWrite('"' & @ScriptFullPath & '"(0,0) : error: Failed to execute Au3Check_Original.exe.' & @CRLF)
            Exit 3
        EndIf
        $hProcess = DllCall("kernel32.dll", "handle", "OpenProcess", "dword", 0x00000400, "bool", False, "dword", $iPid)
        
        $sTotalOutput = ""
        While 1
            $sChunk = StdoutRead($iPid)
            If @error Then ExitLoop
            If $sChunk <> "" Then
                If $bJsonOut Then
                    $sTotalOutput &= $sChunk
                Else
                    ConsoleWrite($sChunk)
                EndIf
            EndIf
            
            $sChunk = StderrRead($iPid)
            If @error Then ExitLoop
            If $sChunk <> "" Then
                If $bJsonOut Then
                    $sTotalOutput &= $sChunk
                Else
                    ConsoleWriteError($sChunk)
                EndIf
            EndIf
            
            Sleep(10)
        WEnd
        
        ProcessWaitClose($iPid)
        $iExitCode = 0
        If Not @error And $hProcess[0] <> 0 Then
            $tExitCode = DllStructCreate("dword")
            $aRet = DllCall("kernel32.dll", "bool", "GetExitCodeProcess", "handle", $hProcess[0], "struct*", $tExitCode)
            If Not @error And $aRet[0] Then
                $iExitCode = DllStructGetData($tExitCode, 1)
            EndIf
            DllCall("kernel32.dll", "bool", "CloseHandle", "handle", $hProcess[0])
        EndIf

        If $bJsonOut Then
            Local $aDiagnostics[1]
            Local $iDiagCount = 0
            Local $iErrors = 0
            Local $iWarnings = 0
            Local $aLines = StringSplit($sTotalOutput, @LF)
            For $j = 1 To $aLines[0]
                Local $sLine = StringStripCR($aLines[$j])
                If $sLine == "" Then ContinueLoop
                Local $aMatch = StringRegExp($sLine, '^"([^"]+)"\((\d+),(\d+)\)\s*:\s*(error|warning)\s*:\s*(.*)$', 3)
                If IsArray($aMatch) And UBound($aMatch) >= 5 Then
                    Local $sFilePath = $aMatch[0]
                    Local $iLineNum = Int($aMatch[1])
                    Local $iColNum = Int($aMatch[2])
                    Local $sSeverity = $aMatch[3]
                    Local $sDesc = $aMatch[4]
                    
                    If StringLower($sSeverity) == "error" Then
                        $iErrors += 1
                    Else
                        $iWarnings += 1
                    EndIf
                    
                    Local $sVarName = ""
                    Local $sTypeName = "Compiler Diagnostic"
                    Local $aVarMatch = StringRegExp($sDesc, '(\$\w+)', 3)
                    If IsArray($aVarMatch) And UBound($aVarMatch) > 0 Then
                        $sVarName = $aVarMatch[0]
                    EndIf
                    
                    If StringInStr($sDesc, "declared") Then
                        $sTypeName = "Duplicate Declaration"
                    ElseIf StringInStr($sDesc, "referenced") Then
                        $sTypeName = "Undeclared Variable"
                    EndIf
                    
                    Local $mDiagnostic[]
                    $mDiagnostic["file"] = StringReplace($sFilePath, "\", "/")
                    $mDiagnostic["line"] = $iLineNum
                    $mDiagnostic["column"] = $iColNum
                    $mDiagnostic["severity"] = $sSeverity
                    $mDiagnostic["type"] = $sTypeName
                    $mDiagnostic["func"] = ""
                    $mDiagnostic["var"] = $sVarName
                    $mDiagnostic["desc"] = $sDesc
                    
                    ReDim $aDiagnostics[$iDiagCount + 1]
                    $aDiagnostics[$iDiagCount] = $mDiagnostic
                    $iDiagCount += 1
                EndIf
            Next
            
            Local $mSummary[]
            $mSummary["total"] = $iDiagCount
            $mSummary["errors"] = $iErrors
            $mSummary["warnings"] = $iWarnings
            
            Local $mOutput[]
            $mOutput["summary"] = $mSummary
            
            If $iDiagCount == 0 Then
                Local $aEmpty[0]
                $mOutput["diagnostics"] = $aEmpty
            Else
                $mOutput["diagnostics"] = $aDiagnostics
            EndIf
            
            ConsoleWrite(_JSON_Generate($mOutput) & @CRLF)
        EndIf
        
        Exit $iExitCode
    EndIf
EndFunc

Main()
