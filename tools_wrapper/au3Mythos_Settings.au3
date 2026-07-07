; #UDF# =========================================================================================================================
; Name...........: au3Mythos_Settings
; Title .........: au3Mythos Settings Manager
; Description ...: Configuration GUI for managing Au3Check wrapper and analyzer integration settings.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
#pragma compile(Console, False)
#pragma compile(x64, True)
#pragma compile(Out, ..\tools_wrapper\au3Mythos_Settings.exe)
#pragma compile(Icon, ..\resources\mythos_logo.ico)

#include <GUIConstantsEx.au3>
#include <WindowsConstants.au3>
#include <ListViewConstants.au3>
#include <EditConstants.au3>
#include <MsgBoxConstants.au3>
#include <ComboConstants.au3>
#include <Array.au3>
#include "..\..\Include\JSON.au3"

; Global Variables
Global $sConfigPath = @AppDataDir & "\au3Mythos\mythos_config\config.json"
Global $sSystemOrigExe = "C:\Program Files (x86)\AutoIt3\Au3Check_Original.exe"
Global $sEnvConfig = EnvGet("MYTHOS_TEST_CONFIG")
If $sEnvConfig <> "" Then
    $sConfigPath = $sEnvConfig
Else
    ; If AppData config is missing, initialize it by copying the local template if found
    If Not FileExists($sConfigPath) Then
        Global $sTemplatePath = ""
        If FileExists(@ScriptDir & "\mythos_config\config.json") Then
            $sTemplatePath = @ScriptDir & "\mythos_config\config.json"
        ElseIf FileExists(@ScriptDir & "\..\resources\mythos_config\config.json") Then
            $sTemplatePath = @ScriptDir & "\..\resources\mythos_config\config.json"
        EndIf
        
        If $sTemplatePath <> "" Then
            Global $sDir = StringRegExpReplace($sConfigPath, "\\[^\\]+$", "")
            If Not FileExists($sDir) Then DirCreate($sDir)
            FileCopy($sTemplatePath, $sConfigPath, 9) ; Copy template to AppData
        EndIf
    EndIf
EndIf
Global $sAu3CheckPath = "C:\Program Files (x86)\AutoIt3\Au3Check.exe"
Global $sAu3CheckOrigPath = "C:\Program Files (x86)\AutoIt3\Au3Check_Original.exe"
Global $sAu3CheckDatPath = "C:\Program Files (x86)\AutoIt3\Au3Check.dat"
Global $sAu3CheckOrigDatPath = "C:\Program Files (x86)\AutoIt3\Au3Check_Original.dat"
Global $sWrapperSource = "" ; Discovered dynamically
Global $sConfigLastModTime = ""

Global $mConfig = ""

; GUI Controls IDs
Global $hMainGui
Global $idMenuAbout
Global $idTab
Global $idLblStatus, $idBtnToggle, $idWrapperEnabled
Global $idDummyRulesLV, $idDummyProfilesLV
Global $hRulesLV = 0, $hProfilesLV = 0
Global $idPythonPath, $idAnalyzerPath, $idBtnBrowsePython, $idBtnBrowseAnalyzer

; Tab 1 (Routing)
Global $idCallersListView, $idListView
Global $idInpRuleApp, $idInpRulePath, $idBtnBrowseRulePath
Global $idComboRuleAction, $idComboRuleConfig
Global $idBtnAddRule, $idBtnUpdateRule, $idBtnDeleteRule, $idBtnAddFromCallers

; Tab 2 (Config Profiles)
Global $idProfilesListView
Global $idInpProfName, $idComboProfType
Global $idBtnAddProfile, $idBtnSaveProfile, $idBtnDeleteProfile

; Mythos Panel Controls
Global $idProfWarnGroup
Global $idProfWarn1, $idProfWarn2, $idProfWarn3, $idProfWarn4, $idProfWarn5, $idProfWarn6, $idProfWarn7
Global $idProfSkipSystem, $idProfExperimental, $idProfNoAutoInclude, $idProfSystemDeadStores
Global $idComboProfEngineMode, $idLblEngineMode
Global $aMythosControls[13]

; Original Panel Controls
Global $idProfExtraGroup
Global $idProfExtraArgs, $idProfOverrideArgs, $idLblExtraArgs
Global $aOriginalControls[4]

; Global Save
Global $idBtnSave

; #FUNCTION# ====================================================================================================================
; Name...........: FindWrapperSource
; Description ...: Discovers the compiled wrapper executable path from various script-relative directory options.
; Syntax.........: FindWrapperSource()
; Parameters ....: None.
; Return values .: The absolute file path to the wrapper binary on success, or empty string on failure.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func FindWrapperSource()
    Local $aPaths[5] = [ _
        @ScriptDir & "\Au3Check_Wrapper_x64.exe", _
        @ScriptDir & "\Au3Check_Wrapper.exe", _
        @ScriptDir & "\bin\Au3Check_Wrapper_x64.exe", _
        @ScriptDir & "\..\bin\Au3Check_Wrapper_x64.exe", _
        @ScriptDir & "\..\tools_wrapper\Au3Check_Wrapper.exe" _
    ]
    For $i = 0 To 4
        If FileExists($aPaths[$i]) Then Return $aPaths[$i]
    Next
    Return ""
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: RobustFileCopy
; Description ...: Copy a file safely with target directory creation and overwrite options.
; Syntax.........: RobustFileCopy($sSrc, $sDst)
; Parameters ....: $sSrc - Source file path.
;                  $sDst - Destination file path.
; Return values .: True on success, False on failure.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func RobustFileCopy($sSrc, $sDst)
    If Not FileExists($sSrc) Then Return False
    Local $iRet = FileCopy($sSrc, $sDst, 9) ; Overwrite + Create directories
    Return ($iRet = 1)
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: ElevateAction
; Description ...: Runs the settings GUI again in admin/UAC elevated mode with the specified action argument.
; Syntax.........: ElevateAction($sActionArg)
; Parameters ....: $sActionArg - Command-line argument to pass to the elevated process.
; Return values .: The exit code of the elevated process, or -1 on failure.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func ElevateAction($sActionArg)
    Local $iRetVal = ShellExecuteWait(@ScriptFullPath, $sActionArg, "", "runas")
    If @error Then Return -1
    Return $iRetVal
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: __JSON_GetBool
; Description ...: Safely extracts a boolean from a JSON Map structure.
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
; Name...........: _ReDim_AddRule
; Description ...: Utility helper to safely resize a rules array and append an item.
; Syntax.........: _ReDim_AddRule(ByRef $aArray, $mItem)
; Parameters ....: $aArray - The array of rules (modified in place).
;                  $mItem  - The rule item Map/object to append.
; Return values .: None.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func _ReDim_AddRule(ByRef $aArray, $mItem)
    Local $iSize = UBound($aArray)
    ReDim $aArray[$iSize + 1]
    $aArray[$iSize] = $mItem
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: LoadConfig
; Description ...: Loads settings JSON config, performing migrations from older configurations if required.
; Syntax.........: LoadConfig()
; Parameters ....: None.
; Return values .: None.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func LoadConfig()
    If Not FileExists($sConfigPath) Then
        Local $sDir = StringRegExpReplace($sConfigPath, "\\[^\\]+$", "")
        If Not FileExists($sDir) Then
            DirCreate($sDir)
        EndIf
        Local $sDefaultJson = '{"wrapper_enabled":true,"rules":[{"caller_name":"SciTE.exe","path_prefix":"*","action":"mythos","config":"default_mythos"}],"configs":{"default_mythos":{"type":"mythos","python_path":"python.exe","analyzer_path":"","skip_system_includes":false,"enable_experimental_checks":true,"engine_mode":"standalone","no_auto_include_discovery":false,"enable_system_dead_stores":true,"warnings":{"1":true,"2":true,"3":true,"4":true,"5":true,"6":true,"7":true}},"default_original":{"type":"original","extra_args":"-d -w 1 -w 2 -w 7 -q","override_args":false}},"recent_callers":{}}'
        Local $hFileLoad = FileOpen($sConfigPath, 2)
        If $hFileLoad <> -1 Then
            FileWrite($hFileLoad, $sDefaultJson)
            FileClose($hFileLoad)
        EndIf
    EndIf
    $sConfigLastModTime = FileGetTime($sConfigPath, 0, 1)
    Local $sJson = FileRead($sConfigPath)
    $mConfig = _JSON_Parse($sJson)
    If @error Or Not IsMap($mConfig) Then
        MsgBox($MB_ICONERROR, "Error", "Failed to parse config.json.")
        Exit
    EndIf
    $mConfig["installed_from_dir"] = @ScriptDir
    
    If Not __JSON_MapExists($mConfig, "configs") Then
        Local $mConfigsMapLoad[]
        
        Local $mOldMythos = ""
        If __JSON_MapExists($mConfig, "mythos_settings") Then
            $mOldMythos = $mConfig["mythos_settings"]
        EndIf
        
        Local $mDefMythos[]
        $mDefMythos["type"] = "mythos"
        $mDefMythos["python_path"] = "python.exe"
        $mDefMythos["analyzer_path"] = ""
        $mDefMythos["skip_system_includes"] = False
        $mDefMythos["enable_experimental_checks"] = True
        $mDefMythos["engine_mode"] = "standalone"
        $mDefMythos["no_auto_include_discovery"] = False
        $mDefMythos["enable_system_dead_stores"] = True
        
        Local $mDefMythosWarn[]
        For $i = 1 To 7
            $mDefMythosWarn[String($i)] = True
        Next
        $mDefMythos["warnings"] = $mDefMythosWarn
        
        If IsMap($mOldMythos) Then
            If __JSON_MapExists($mOldMythos, "python_path") Then $mDefMythos["python_path"] = $mOldMythos["python_path"]
            If __JSON_MapExists($mOldMythos, "analyzer_path") Then $mDefMythos["analyzer_path"] = $mOldMythos["analyzer_path"]
            If __JSON_MapExists($mOldMythos, "skip_system_includes") Then $mDefMythos["skip_system_includes"] = $mOldMythos["skip_system_includes"]
            If __JSON_MapExists($mOldMythos, "enable_experimental_checks") Then $mDefMythos["enable_experimental_checks"] = $mOldMythos["enable_experimental_checks"]
            If __JSON_MapExists($mOldMythos, "engine_mode") Then $mDefMythos["engine_mode"] = $mOldMythos["engine_mode"]
            If __JSON_MapExists($mOldMythos, "no_auto_include_discovery") Then $mDefMythos["no_auto_include_discovery"] = $mOldMythos["no_auto_include_discovery"]
            If __JSON_MapExists($mOldMythos, "enable_system_dead_stores") Then $mDefMythos["enable_system_dead_stores"] = $mOldMythos["enable_system_dead_stores"]
            If __JSON_MapExists($mOldMythos, "warnings") Then $mDefMythos["warnings"] = $mOldMythos["warnings"]
        EndIf
        $mConfigsMapLoad["default_mythos"] = $mDefMythos
        
        Local $mDefOrig[]
        $mDefOrig["type"] = "original"
        $mDefOrig["extra_args"] = "-d -w 1 -w 2 -w 7 -q"
        $mDefOrig["override_args"] = False
        $mConfigsMapLoad["default_original"] = $mDefOrig
        
        $mConfig["configs"] = $mConfigsMapLoad
        
        If __JSON_MapExists($mConfig, "rules") Then
            Local $aRulesLoad = $mConfig["rules"]
            If IsArray($aRulesLoad) Then
                For $i = 0 To UBound($aRulesLoad) - 1
                    Local $mRuleLoad = $aRulesLoad[$i]
                    If IsMap($mRuleLoad) Then
                        If Not __JSON_MapExists($mRuleLoad, "config") Then
                            If __JSON_MapExists($mRuleLoad, "action") And StringLower($mRuleLoad["action"]) == "mythos" Then
                                $mRuleLoad["config"] = "default_mythos"
                            Else
                                $mRuleLoad["config"] = "default_original"
                            EndIf
                        EndIf
                        $aRulesLoad[$i] = $mRuleLoad
                    EndIf
                Next
                $mConfig["rules"] = $aRulesLoad
            EndIf
        EndIf
        
        Local $sNewJsonLoad = _JSON_Generate($mConfig)
        Local $hFileWrite = FileOpen($sConfigPath, 2)
        If $hFileWrite <> -1 Then
            FileWrite($hFileWrite, $sNewJsonLoad)
            FileClose($hFileWrite)
        EndIf
    EndIf

    If IsMap($mConfig) And __JSON_MapExists($mConfig, "configs") Then
        $mConfigsMapLoad = $mConfig["configs"]
        If IsMap($mConfigsMapLoad) And __JSON_MapExists($mConfigsMapLoad, "default_mythos") Then
            $mDefMythos = $mConfigsMapLoad["default_mythos"]
            If IsMap($mDefMythos) And __JSON_MapExists($mDefMythos, "analyzer_path") And $mDefMythos["analyzer_path"] == "" Then
                If __JSON_MapExists($mConfig, "mythos_settings") Then
                    $mOldMythos = $mConfig["mythos_settings"]
                    If IsMap($mOldMythos) And __JSON_MapExists($mOldMythos, "analyzer_path") And $mOldMythos["analyzer_path"] <> "" Then
                        $mDefMythos["analyzer_path"] = $mOldMythos["analyzer_path"]
                        $mConfigsMapLoad["default_mythos"] = $mDefMythos
                        $mConfig["configs"] = $mConfigsMapLoad
                    EndIf
                EndIf
            EndIf
        EndIf
    EndIf
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: SaveConfig
; Description ...: Saves active configurations, rules, and profiles to config.json.
; Syntax.........: SaveConfig()
; Parameters ....: None.
; Return values .: None.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func SaveConfig()
    $mConfig["wrapper_enabled"] = (GUICtrlRead($idWrapperEnabled) = $GUI_CHECKED)
    
    ; Save global engine variables in default_mythos and mythos_settings
    Local $sPythonVal = GUICtrlRead($idPythonPath)
    Local $sAnalyzerVal = GUICtrlRead($idAnalyzerPath)
    If $sAnalyzerVal == "<Auto-Discover>" Then $sAnalyzerVal = ""
    
    If IsMap($mConfig) And __JSON_MapExists($mConfig, "configs") Then
        Local $mConfigsMapSave = $mConfig["configs"]
        If IsMap($mConfigsMapSave) And __JSON_MapExists($mConfigsMapSave, "default_mythos") Then
            Local $mDefMythSave = $mConfigsMapSave["default_mythos"]
            If IsMap($mDefMythSave) Then
                $mDefMythSave["python_path"] = $sPythonVal
                $mDefMythSave["analyzer_path"] = $sAnalyzerVal
                $mConfigsMapSave["default_mythos"] = $mDefMythSave
            EndIf
        EndIf
        $mConfig["configs"] = $mConfigsMapSave
    EndIf
    
    Local $mLegacySettings[]
    $mLegacySettings["python_path"] = $sPythonVal
    $mLegacySettings["analyzer_path"] = $sAnalyzerVal
    $mLegacySettings["skip_system_includes"] = False
    $mLegacySettings["enable_experimental_checks"] = True
    $mLegacySettings["engine_mode"] = "standalone"
    $mLegacySettings["no_auto_include_discovery"] = False
    $mLegacySettings["enable_system_dead_stores"] = True
    
    If IsMap($mConfig) And __JSON_MapExists($mConfig, "configs") Then
        $mConfigsMapSave = $mConfig["configs"]
        If IsMap($mConfigsMapSave) And __JSON_MapExists($mConfigsMapSave, "default_mythos") Then
            $mDefMythSave = $mConfigsMapSave["default_mythos"]
            If IsMap($mDefMythSave) Then
                If __JSON_MapExists($mDefMythSave, "skip_system_includes") Then $mLegacySettings["skip_system_includes"] = $mDefMythSave["skip_system_includes"]
                If __JSON_MapExists($mDefMythSave, "enable_experimental_checks") Then $mLegacySettings["enable_experimental_checks"] = $mDefMythSave["enable_experimental_checks"]
                If __JSON_MapExists($mDefMythSave, "engine_mode") Then $mLegacySettings["engine_mode"] = $mDefMythSave["engine_mode"]
                If __JSON_MapExists($mDefMythSave, "no_auto_include_discovery") Then $mLegacySettings["no_auto_include_discovery"] = $mDefMythSave["no_auto_include_discovery"]
                If __JSON_MapExists($mDefMythSave, "enable_system_dead_stores") Then $mLegacySettings["enable_system_dead_stores"] = $mDefMythSave["enable_system_dead_stores"]
                If __JSON_MapExists($mDefMythSave, "warnings") Then $mLegacySettings["warnings"] = $mDefMythSave["warnings"]
            EndIf
        EndIf
    EndIf
    $mConfig["mythos_settings"] = $mLegacySettings
    
    ; Rebuild Rules array
    Local $aRulesNew[0]
    Local $iCount = GUICtrlSendMsg($idListView, $LVM_GETITEMCOUNT, 0, 0)
    For $i = 0 To $iCount - 1
        Local $sAppVal = _ListView_GetItemText($idListView, $i, 0)
        Local $sPrefixVal = _ListView_GetItemText($idListView, $i, 1)
        Local $sActionVal = _ListView_GetItemText($idListView, $i, 2)
        Local $sConfigVal = _ListView_GetItemText($idListView, $i, 3)
        
        Local $mRuleSave[]
        $mRuleSave["caller_name"] = $sAppVal
        $mRuleSave["path_prefix"] = $sPrefixVal
        $mRuleSave["action"] = $sActionVal
        $mRuleSave["config"] = $sConfigVal
        
        _ReDim_AddRule($aRulesNew, $mRuleSave)
    Next
    $mConfig["rules"] = $aRulesNew
    $mConfig["installed_from_dir"] = @ScriptDir
    
    ; Write config to config.json
    Local $sNewJsonSave = _JSON_Generate($mConfig)
    Local $sDir = StringRegExpReplace($sConfigPath, "\\[^\\]+$", "")
    If Not FileExists($sDir) Then
        DirCreate($sDir)
    EndIf
    Local $hFileSave = FileOpen($sConfigPath, 2) ; Overwrite
    If $hFileSave = -1 Then
        MsgBox($MB_ICONERROR, "Error", "Failed to open config.json for writing.", 0, $hMainGui)
        Return
    EndIf
    FileWrite($hFileSave, $sNewJsonSave)
    FileClose($hFileSave)
    
    $sConfigLastModTime = FileGetTime($sConfigPath, 0, 1)
    
    RefreshRulesListView()
    RefreshProfilesListView()
    MsgBox($MB_ICONINFORMATION, "Success", "Settings saved successfully.", 0, $hMainGui)
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: CheckConfigRefresh
; Description ...: Checks if the config has been modified on disk by another process and prompts to reload if so.
; Syntax.........: CheckConfigRefresh()
; Parameters ....: None.
; Return values .: None.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func CheckConfigRefresh()
    If Not FileExists($sConfigPath) Then Return
    Local $sCurrentTime = FileGetTime($sConfigPath, 0, 1)
    If $sCurrentTime <> $sConfigLastModTime Then
        $sConfigLastModTime = $sCurrentTime
        LoadConfig()
        RefreshRulesListView()
        RefreshProfilesListView()
        LoadRecentCallers()
    EndIf
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: _ListView_GetItemText
; Description ...: Helper to get the sub-item text of a ListView.
; Syntax.........: _ListView_GetItemText($idLV, $iItem, $iSubItem)
; Parameters ....: $idLV     - Control ID or handle of the ListView.
;                  $iItem     - 0-based index of the item.
;                  $iSubItem  - 0-based index of the sub-item.
; Return values .: The text of the specified ListView sub-item.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func _ListView_GetItemText($idLV, $iItem, $iSubItem)
    Local $tItem = DllStructCreate("uint Mask;int Item;int SubItem;uint State;uint StateMask;ptr Text;int TextMax;int Image;lparam Param;int Indent;int GroupId;uint Columns;ptr ColumnsPtr;ptr RatioPtr;int iLastCol;int iColWidth")
    Local $tText = DllStructCreate("wchar[1024]")
    DllStructSetData($tItem, "Mask", 1) ; LVIF_TEXT
    DllStructSetData($tItem, "Item", $iItem)
    DllStructSetData($tItem, "SubItem", $iSubItem)
    DllStructSetData($tItem, "Text", DllStructGetPtr($tText))
    DllStructSetData($tItem, "TextMax", 1024)
    GUICtrlSendMsg($idLV, $LVM_GETITEMW, 0, DllStructGetPtr($tItem))
    Return DllStructGetData($tText, 1)
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: LoadRecentCallers
; Description ...: Refreshes the caller processes list from the logged execution events in the JSON config.
; Syntax.........: LoadRecentCallers()
; Parameters ....: None.
; Return values .: None.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func LoadRecentCallers()
    GUICtrlSendMsg($idCallersListView, $LVM_DELETEALLITEMS, 0, 0)
    If Not IsMap($mConfig) Or Not __JSON_MapExists($mConfig, "recent_callers") Then Return
    Local $mRecent = $mConfig["recent_callers"]
    If Not IsMap($mRecent) Then Return
    
    Local $aKeys = MapKeys($mRecent)
    For $i = 0 To UBound($aKeys) - 1
        Local $sName = $aKeys[$i]
        Local $mInfo = $mRecent[$sName]
        If IsMap($mInfo) Then
            Local $sParams = ""
            If __JSON_MapExists($mInfo, "params") Then $sParams = $mInfo["params"]
            Local $sPath = ""
            If __JSON_MapExists($mInfo, "path") Then $sPath = $mInfo["path"]
            Local $sLast = ""
            If __JSON_MapExists($mInfo, "last_called") Then $sLast = $mInfo["last_called"]
            
            GUICtrlCreateListViewItem($sName & "|" & $sParams & "|" & $sPath & "|" & $sLast, $idCallersListView)
        EndIf
    Next
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: UpdateIntegrationUIState
; Description ...: Inspects the system status (presence of Original binaries) and updates status labels/buttons.
; Syntax.........: UpdateIntegrationUIState()
; Parameters ....: None.
; Return values .: None.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func UpdateIntegrationUIState()
    If FileExists($sAu3CheckOrigPath) Then
        GUICtrlSetData($idLblStatus, "Status: Wrapper Installed & Active")
        GUICtrlSetData($idBtnToggle, "Disable au3Mythos")
    Else
        GUICtrlSetData($idLblStatus, "Status: Not Installed")
        GUICtrlSetData($idBtnToggle, "Enable au3Mythos")
    EndIf
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: RefreshRulesListView
; Description ...: Refreshes the Rules Tab ListView with the configured routing entries.
; Syntax.........: RefreshRulesListView()
; Parameters ....: None.
; Return values .: None.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func RefreshRulesListView()
    GUICtrlSendMsg($idListView, $LVM_DELETEALLITEMS, 0, 0)
    If Not IsMap($mConfig) Or Not __JSON_MapExists($mConfig, "rules") Then Return
    Local $aRulesList = $mConfig["rules"]
    If Not IsArray($aRulesList) Then Return
    
    For $i = 0 To UBound($aRulesList) - 1
        Local $mRuleItem = $aRulesList[$i]
        If IsMap($mRuleItem) Then
            Local $sAppVal = "*"
            If __JSON_MapExists($mRuleItem, "caller_name") Then $sAppVal = $mRuleItem["caller_name"]
            Local $sPrefixVal = "*"
            If __JSON_MapExists($mRuleItem, "path_prefix") Then $sPrefixVal = $mRuleItem["path_prefix"]
            Local $sActVal = "original"
            If __JSON_MapExists($mRuleItem, "action") Then $sActVal = $mRuleItem["action"]
            Local $sConfVal = ""
            If __JSON_MapExists($mRuleItem, "config") Then $sConfVal = $mRuleItem["config"]
            If $sConfVal == "" Then
                $sConfVal = ($sActVal == "mythos" ? "default_mythos" : "default_original")
            EndIf
            
            GUICtrlCreateListViewItem($sAppVal & "|" & $sPrefixVal & "|" & $sActVal & "|" & $sConfVal, $idListView)
        EndIf
    Next
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: RefreshProfilesListView
; Description ...: Refreshes the Profile Configuration Tab ListView with defined settings profiles.
; Syntax.........: RefreshProfilesListView()
; Parameters ....: None.
; Return values .: None.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func RefreshProfilesListView()
    GUICtrlSendMsg($idProfilesListView, $LVM_DELETEALLITEMS, 0, 0)
    If Not IsMap($mConfig) Or Not __JSON_MapExists($mConfig, "configs") Then Return
    Local $mConfigsMapList = $mConfig["configs"]
    If Not IsMap($mConfigsMapList) Then Return
    
    Local $aKeys = MapKeys($mConfigsMapList)
    For $i = 0 To UBound($aKeys) - 1
        Local $sName = $aKeys[$i]
        Local $mProfileItem = $mConfigsMapList[$sName]
        If IsMap($mProfileItem) Then
            Local $sTypeVal = "mythos"
            If __JSON_MapExists($mProfileItem, "type") Then $sTypeVal = $mProfileItem["type"]
            
            Local $sDetailsVal = ""
            If $sTypeVal == "mythos" Then
                Local $sModeVal = "standalone"
                If __JSON_MapExists($mProfileItem, "engine_mode") Then $sModeVal = $mProfileItem["engine_mode"]
                Local $bSkipVal = False
                If __JSON_MapExists($mProfileItem, "skip_system_includes") Then $bSkipVal = $mProfileItem["skip_system_includes"]
                $sDetailsVal = "Mode: " & $sModeVal & ", Skip Sys: " & ($bSkipVal ? "Yes" : "No")
            Else
                Local $sExtraVal = ""
                If __JSON_MapExists($mProfileItem, "extra_args") Then $sExtraVal = $mProfileItem["extra_args"]
                $sDetailsVal = "Args: " & $sExtraVal
            EndIf
            
            GUICtrlCreateListViewItem($sName & "|" & $sTypeVal & "|" & $sDetailsVal, $idProfilesListView)
        EndIf
    Next
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: UpdateRuleConfigCombo
; Description ...: Dynamically updates the configuration profile selection dropdown based on the chosen action type.
; Syntax.........: UpdateRuleConfigCombo($sAction[, $sSelectedConfig = ""])
; Parameters ....: $sAction         - The action type ("mythos" or "original").
;                  $sSelectedConfig - The currently active/selected configuration profile name to set.
; Return values .: None.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func UpdateRuleConfigCombo($sAction, $sSelectedConfig = "")
    Local $sFiltered = ""
    Local $sFirst = ""
    If IsMap($mConfig) And __JSON_MapExists($mConfig, "configs") Then
        Local $mConfigsMapCombo = $mConfig["configs"]
        If IsMap($mConfigsMapCombo) Then
            Local $aKeys = MapKeys($mConfigsMapCombo)
            For $i = 0 To UBound($aKeys) - 1
                Local $sKeyVal = $aKeys[$i]
                Local $mProfileItem = $mConfigsMapCombo[$sKeyVal]
                If IsMap($mProfileItem) And __JSON_MapExists($mProfileItem, "type") Then
                    If $mProfileItem["type"] == $sAction Then
                        $sFiltered &= $sKeyVal & "|"
                        If $sFirst == "" Then $sFirst = $sKeyVal
                    EndIf
                EndIf
            Next
            $sFiltered = StringTrimRight($sFiltered, 1)
        EndIf
    EndIf
    If $sFiltered == "" Then
        If $sAction == "mythos" Then
            $sFiltered = "default_mythos"
            $sFirst = "default_mythos"
        Else
            $sFiltered = "default_original"
            $sFirst = "default_original"
        EndIf
    EndIf
    GUICtrlSetData($idComboRuleConfig, "") ; Clear
    GUICtrlSetData($idComboRuleConfig, $sFiltered, ($sSelectedConfig <> "" ? $sSelectedConfig : $sFirst))
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: UpdateProfilePanelsVisibility
; Description ...: Shows or hides the custom settings panel depending on the selected configuration profile type (Mythos vs. Original).
; Syntax.........: UpdateProfilePanelsVisibility($sProfileType)
; Parameters ....: $sProfileType - The profile type ("mythos" or "original").
; Return values .: None.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func UpdateProfilePanelsVisibility($sProfileType)
    Local $iMythosState = ($sProfileType == "mythos" ? $GUI_SHOW : $GUI_HIDE)
    Local $iOriginalState = ($sProfileType == "original" ? $GUI_SHOW : $GUI_HIDE)
    
    For $i = 0 To UBound($aMythosControls) - 1
        GUICtrlSetState($aMythosControls[$i], $iMythosState)
    Next
    For $i = 0 To UBound($aOriginalControls) - 1
        GUICtrlSetState($aOriginalControls[$i], $iOriginalState)
    Next
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: LoadProfileInputs
; Description ...: Populates the profile detail inputs (checkboxes, inputs) based on the chosen profile entry.
; Syntax.........: LoadProfileInputs($sProfileName, $sProfileType)
; Parameters ....: $sProfileName - Name of the settings profile.
;                  $sProfileType - The type of profile ("mythos" or "original").
; Return values .: None.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func LoadProfileInputs($sProfileName, $sProfileType)
    If Not IsMap($mConfig) Or Not __JSON_MapExists($mConfig, "configs") Then Return
    Local $mConfigsMapInputs = $mConfig["configs"]
    If Not IsMap($mConfigsMapInputs) Or Not __JSON_MapExists($mConfigsMapInputs, $sProfileName) Then Return
    Local $mProfileInputs = $mConfigsMapInputs[$sProfileName]
    If Not IsMap($mProfileInputs) Then Return
    
    If $sProfileType == "mythos" Then
        GUICtrlSetState($idProfSkipSystem, (__JSON_GetBool($mProfileInputs, "skip_system_includes", False) ? $GUI_CHECKED : $GUI_UNCHECKED))
        GUICtrlSetState($idProfExperimental, (__JSON_GetBool($mProfileInputs, "enable_experimental_checks", True) ? $GUI_CHECKED : $GUI_UNCHECKED))
        GUICtrlSetState($idProfNoAutoInclude, (__JSON_GetBool($mProfileInputs, "no_auto_include_discovery", False) ? $GUI_CHECKED : $GUI_UNCHECKED))
        GUICtrlSetState($idProfSystemDeadStores, (__JSON_GetBool($mProfileInputs, "enable_system_dead_stores", True) ? $GUI_CHECKED : $GUI_UNCHECKED))
        
        Local $sModeVal = "standalone"
        If __JSON_MapExists($mProfileInputs, "engine_mode") Then $sModeVal = $mProfileInputs["engine_mode"]
        GUICtrlSetData($idComboProfEngineMode, $sModeVal)
        
        If __JSON_MapExists($mProfileInputs, "warnings") Then
            Local $mWarnInputs = $mProfileInputs["warnings"]
            If IsMap($mWarnInputs) Then
                Local $aWarnIdsInputs[7] = [$idProfWarn1, $idProfWarn2, $idProfWarn3, $idProfWarn4, $idProfWarn5, $idProfWarn6, $idProfWarn7]
                For $i = 1 To 7
                    Local $bValInputs = True
                    If __JSON_MapExists($mWarnInputs, String($i)) Then $bValInputs = $mWarnInputs[String($i)]
                    GUICtrlSetState($aWarnIdsInputs[$i - 1], ($bValInputs ? $GUI_CHECKED : $GUI_UNCHECKED))
                Next
            EndIf
        EndIf
    ElseIf $sProfileType == "original" Then
        Local $sExtraVal = ""
        If __JSON_MapExists($mProfileInputs, "extra_args") Then $sExtraVal = $mProfileInputs["extra_args"]
        GUICtrlSetData($idProfExtraArgs, $sExtraVal)
        
        Local $bOverrideVal = False
        If __JSON_MapExists($mProfileInputs, "override_args") Then $bOverrideVal = $mProfileInputs["override_args"]
        GUICtrlSetState($idProfOverrideArgs, ($bOverrideVal ? $GUI_CHECKED : $GUI_UNCHECKED))
    EndIf
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: Main
; Description ...: Main entry point of the settings manager. Initializes GUI, loads settings, handles events, and manages installation/uninstallation.
; Syntax.........: Main()
; Parameters ....: None.
; Return values .: None.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func Main()
    Local $nMsg = 0
    Local $sFile = ""
    Local $sSelDir = ""
    Local $sAct = ""
    Local $iIdx = 0
    Local $sData = ""
    Local $aParts = ""
    Local $sApp = ""
    Local $sPrefix = ""
    Local $sConf = ""
    Local $iCtrlId = 0
    Local $aDataParts = ""
    Local $sSelCaller = ""
    Local $sSelPath = ""
    Local $sDirPrefix = ""
    Local $iLastSlash = 0
    Local $sProfName = ""
    Local $sProfType = ""
    Local $mConfigsMap = ""
    Local $iAns = 0
    Local $aRules = ""
    Local $mRule = ""
    Local $bInstalled = False
    Local $iRet = 0
    Local $sNewJson = ""
    Local $hFile = -1
    Local $sDir = ""
    Local $sActionArg = ""
    Local $sAnalyzerVal = ""
    Local $sPythonVal = ""
    Local $mConfigsMapVal = ""
    Local $mDefMyth = ""
    Local $idMenuHelp = 0

    $sWrapperSource = FindWrapperSource()
    If $CmdLine[0] > 0 Then
        $sActionArg = $CmdLine[1]
        If $sActionArg == "/install" Then
            If Not IsAdmin() Then Exit 1
            If $sWrapperSource == "" Then Exit 2
            If Not FileExists($sAu3CheckOrigPath) Then
                If Not RobustFileCopy($sAu3CheckPath, $sAu3CheckOrigPath) Then Exit 3
            EndIf
            If Not FileExists($sAu3CheckOrigDatPath) Then
                If FileExists($sAu3CheckDatPath) Then
                    RobustFileCopy($sAu3CheckDatPath, $sAu3CheckOrigDatPath)
                EndIf
            EndIf
            If RobustFileCopy($sWrapperSource, $sAu3CheckPath) Then
                Exit 0
            Else
                Exit 4
            EndIf
        ElseIf $sActionArg == "/restore" Then
            If Not IsAdmin() Then Exit 1
            If Not FileExists($sAu3CheckOrigPath) Then Exit 0
            If RobustFileCopy($sAu3CheckOrigPath, $sAu3CheckPath) Then
                FileDelete($sAu3CheckOrigPath)
                If FileExists($sAu3CheckOrigDatPath) Then FileDelete($sAu3CheckOrigDatPath)
                Exit 0
            Else
                Exit 5
            EndIf
        EndIf
    EndIf

    ShowSplashScreen()

    LoadConfig()

    ; GUI Construction
    $hMainGui = GUICreate("au3Mythos - Au3Check Settings Manager", 840, 660)
    $idDummyRulesLV = GUICtrlCreateDummy()
    $idDummyProfilesLV = GUICtrlCreateDummy()
    GUISetBkColor(0xF5F6F8)

    $idMenuHelp = GUICtrlCreateMenu("Help")
    $idMenuAbout = GUICtrlCreateMenuItem("About", $idMenuHelp)

    $idTab = GUICtrlCreateTab(10, 10, 820, 580)

    ; ==================== TAB 1: ROUTING & CALLERS ====================
    GUICtrlCreateTabItem("Routing & Callers")

    ; Group 1: Tracked Callers
    GUICtrlCreateGroup("Recently Tracked Callers", 25, 45, 770, 160)
    $idCallersListView = GUICtrlCreateListView("App Name|Call Parameters|Calling Path|Last Called", 40, 65, 740, 100, BitOR($GUI_SS_DEFAULT_LISTVIEW, $WS_VSCROLL))
    GUICtrlSendMsg($idCallersListView, $LVM_SETEXTENDEDLISTVIEWSTYLE, $LVS_EX_GRIDLINES + $LVS_EX_FULLROWSELECT, $LVS_EX_GRIDLINES + $LVS_EX_FULLROWSELECT)
    GUICtrlSendMsg($idCallersListView, $LVM_SETCOLUMNWIDTH, 0, 110)
    GUICtrlSendMsg($idCallersListView, $LVM_SETCOLUMNWIDTH, 1, 230)
    GUICtrlSendMsg($idCallersListView, $LVM_SETCOLUMNWIDTH, 2, 250)
    GUICtrlSendMsg($idCallersListView, $LVM_SETCOLUMNWIDTH, 3, 130)

    $idBtnAddFromCallers = GUICtrlCreateButton("Add Routing Rule for Selected Caller", 40, 170, 740, 25)
    GUICtrlSetTip($idBtnAddFromCallers, "Copies the selected caller properties into the rule edit form.")
    GUICtrlCreateGroup("", -99, -99, 1, 1)

    ; Group 2: Rules Matrix
    GUICtrlCreateGroup("Routing Rules Matrix (First Match Wins)", 25, 215, 770, 360)
    $idListView = GUICtrlCreateListView("App Name|Path Prefix (Target)|Action|Config", 40, 235, 740, 180, BitOR($GUI_SS_DEFAULT_LISTVIEW, $WS_VSCROLL))
    $hRulesLV = GUICtrlGetHandle($idListView)
    GUICtrlSendMsg($idListView, $LVM_SETEXTENDEDLISTVIEWSTYLE, $LVS_EX_GRIDLINES + $LVS_EX_FULLROWSELECT, $LVS_EX_GRIDLINES + $LVS_EX_FULLROWSELECT)
    GUICtrlSendMsg($idListView, $LVM_SETCOLUMNWIDTH, 0, 120)
    GUICtrlSendMsg($idListView, $LVM_SETCOLUMNWIDTH, 1, 350)
    GUICtrlSendMsg($idListView, $LVM_SETCOLUMNWIDTH, 2, 100)
    GUICtrlSendMsg($idListView, $LVM_SETCOLUMNWIDTH, 3, 130)

    ; Rule Inline Form Controls
    GUICtrlCreateLabel("App Name (e.g. SciTE.exe or *):", 40, 430, 150, 20)
    $idInpRuleApp = GUICtrlCreateInput("*", 40, 450, 150, 21)

    GUICtrlCreateLabel("Path Prefix Constraint (e.g. D:\Workspace or *):", 210, 430, 250, 20)
    $idInpRulePath = GUICtrlCreateInput("*", 210, 450, 250, 21)

    $idBtnBrowseRulePath = GUICtrlCreateButton("...", 465, 449, 25, 22)
    GUICtrlSetTip($idBtnBrowseRulePath, "Select folder prefix target.")

    GUICtrlCreateLabel("Target Action:", 510, 430, 100, 20)
    $idComboRuleAction = GUICtrlCreateCombo("", 510, 450, 100, 25, $CBS_DROPDOWNLIST)
    GUICtrlSetData($idComboRuleAction, "mythos|original", "mythos")

    GUICtrlCreateLabel("Config Profile:", 630, 430, 100, 20)
    $idComboRuleConfig = GUICtrlCreateCombo("", 630, 450, 150, 25, $CBS_DROPDOWNLIST)

    $idBtnAddRule = GUICtrlCreateButton("Add Rule", 40, 530, 230, 28)
    GUICtrlSetTip($idBtnAddRule, "Add a new routing rule from form fields.")

    $idBtnUpdateRule = GUICtrlCreateButton("Update Selected Rule", 295, 530, 230, 28)
    GUICtrlSetTip($idBtnUpdateRule, "Update the selected routing rule with form fields.")

    $idBtnDeleteRule = GUICtrlCreateButton("Delete Selected Rule", 550, 530, 230, 28)
    GUICtrlSetTip($idBtnDeleteRule, "Delete the selected routing rule.")
    GUICtrlCreateGroup("", -99, -99, 1, 1)

    ; ==================== TAB 2: CONFIG PROFILES ====================
    GUICtrlCreateTabItem("Config Profiles")

    ; List View for profiles
    $idProfilesListView = GUICtrlCreateListView("Profile Name|Type|Details", 40, 55, 740, 130, BitOR($GUI_SS_DEFAULT_LISTVIEW, $WS_VSCROLL))
    $hProfilesLV = GUICtrlGetHandle($idProfilesListView)
    GUICtrlSendMsg($idProfilesListView, $LVM_SETEXTENDEDLISTVIEWSTYLE, $LVS_EX_GRIDLINES + $LVS_EX_FULLROWSELECT, $LVS_EX_GRIDLINES + $LVS_EX_FULLROWSELECT)
    GUICtrlSendMsg($idProfilesListView, $LVM_SETCOLUMNWIDTH, 0, 150)
    GUICtrlSendMsg($idProfilesListView, $LVM_SETCOLUMNWIDTH, 1, 100)
    GUICtrlSendMsg($idProfilesListView, $LVM_SETCOLUMNWIDTH, 2, 450)

    ; Profile Editor Group
    GUICtrlCreateGroup("Profile Editor Form", 25, 200, 770, 315)

    GUICtrlCreateLabel("Profile Name:", 40, 222, 100, 20)
    $idInpProfName = GUICtrlCreateInput("custom_profile", 40, 240, 150, 21)

    GUICtrlCreateLabel("Profile Type:", 210, 222, 100, 20)
    $idComboProfType = GUICtrlCreateCombo("", 210, 240, 120, 25, $CBS_DROPDOWNLIST)
    GUICtrlSetData($idComboProfType, "mythos|original", "mythos")

    ; Mythos Sub-Panel
    $idProfWarnGroup = GUICtrlCreateGroup("Scoping Analyzer Options (Type: Mythos)", 40, 280, 740, 225)
    $idProfWarn1 = GUICtrlCreateCheckbox("-w 1: Duplicate includes", 55, 305, 230, 20)
    $idProfWarn2 = GUICtrlCreateCheckbox("-w 2: Unmatched comment-end", 55, 330, 230, 20)
    $idProfWarn3 = GUICtrlCreateCheckbox("-w 3: Duplicate variables", 55, 355, 230, 20)
    $idProfWarn4 = GUICtrlCreateCheckbox("-w 4: Local in global scope", 55, 380, 230, 20)
    $idProfWarn5 = GUICtrlCreateCheckbox("-w 5: Unused local variables", 55, 405, 230, 20)
    $idProfWarn6 = GUICtrlCreateCheckbox("-w 6: Deprecated Dim usage", 55, 430, 230, 20)
    $idProfWarn7 = GUICtrlCreateCheckbox("-w 7: ByRef const violations", 55, 455, 230, 20)

    $idProfSkipSystem = GUICtrlCreateCheckbox("Skip Diagnostics in Standard System UDFs", 310, 305, 230, 20)
    $idProfExperimental = GUICtrlCreateCheckbox("Enable Hardened Semantic Inspections", 310, 330, 230, 20)
    $idProfNoAutoInclude = GUICtrlCreateCheckbox("Disable Project-Local Include Discovery", 310, 355, 230, 20)
    $idProfSystemDeadStores = GUICtrlCreateCheckbox("Collect System dead-stores into separate report", 310, 380, 230, 20)

    $idLblEngineMode = GUICtrlCreateLabel("Engine Execution Mode:", 560, 305, 200, 20)
    $idComboProfEngineMode = GUICtrlCreateCombo("", 560, 325, 200, 25, $CBS_DROPDOWNLIST)
    GUICtrlSetData($idComboProfEngineMode, "standalone|python", "standalone")
    GUICtrlCreateGroup("", -99, -99, 1, 1)

    $aMythosControls[0] = $idProfWarnGroup
    $aMythosControls[1] = $idProfWarn1
    $aMythosControls[2] = $idProfWarn2
    $aMythosControls[3] = $idProfWarn3
    $aMythosControls[4] = $idProfWarn4
    $aMythosControls[5] = $idProfWarn5
    $aMythosControls[6] = $idProfWarn6
    $aMythosControls[7] = $idProfWarn7
    $aMythosControls[8] = $idProfSkipSystem
    $aMythosControls[9] = $idProfExperimental
    $aMythosControls[10] = $idProfNoAutoInclude
    $aMythosControls[11] = $idProfSystemDeadStores
    $aMythosControls[12] = $idComboProfEngineMode

    ; Original Sub-Panel
    $idProfExtraGroup = GUICtrlCreateGroup("Original Checker Options (Type: Original)", 40, 280, 740, 225)
    $idLblExtraArgs = GUICtrlCreateLabel("Extra Arguments (appended to caller args):", 55, 305, 500, 20)
    $idProfExtraArgs = GUICtrlCreateInput("-d -w 1 -w 2 -w 7 -q", 55, 325, 710, 21)
    $idProfOverrideArgs = GUICtrlCreateCheckbox("Override Caller Arguments completely (uses only Extra Args and file name)", 55, 365, 500, 20)
    GUICtrlCreateGroup("", -99, -99, 1, 1)

    $aOriginalControls[0] = $idProfExtraGroup
    $aOriginalControls[1] = $idLblExtraArgs
    $aOriginalControls[2] = $idProfExtraArgs
    $aOriginalControls[3] = $idProfOverrideArgs

    GUICtrlCreateGroup("", -99, -99, 1, 1)

    $idBtnAddProfile = GUICtrlCreateButton("Add Profile", 40, 530, 230, 28)
    GUICtrlSetTip($idBtnAddProfile, "Add a new configuration profile from editor fields.")

    $idBtnSaveProfile = GUICtrlCreateButton("Save Selected Profile", 295, 530, 230, 28)
    GUICtrlSetTip($idBtnSaveProfile, "Update the selected configuration profile.")

    $idBtnDeleteProfile = GUICtrlCreateButton("Delete Selected Profile", 550, 530, 230, 28)
    GUICtrlSetTip($idBtnDeleteProfile, "Delete the selected configuration profile (defaults cannot be deleted).")

    ; ==================== TAB 3: CORE SETTINGS ====================
    GUICtrlCreateTabItem("Core Settings")

    GUICtrlCreateGroup("au3Check Wrapper Integration", 25, 45, 770, 110)
    $idLblStatus = GUICtrlCreateLabel("Status: Not Installed", 45, 73, 450, 20)
    GUICtrlSetFont($idLblStatus, 9, 800)

    $idBtnToggle = GUICtrlCreateButton("Enable au3Mythos", 640, 65, 130, 28)
    GUICtrlSetTip($idBtnToggle, "Installs or restores the drop-in Au3Check wrapper to intercept and route calls.")

    $idWrapperEnabled = GUICtrlCreateCheckbox("Enable au3Check Wrapper Routing", 45, 110, 450, 20)
    If $mConfig["wrapper_enabled"] Then GUICtrlSetState($idWrapperEnabled, $GUI_CHECKED)
    GUICtrlSetTip($idWrapperEnabled, "Enables routing rules mapping. If unchecked, wrapper falls back to original Au3Check for all calls.")
    GUICtrlCreateGroup("", -99, -99, 1, 1)

    GUICtrlCreateGroup("Global Paths", 25, 170, 770, 130)
    GUICtrlCreateLabel("Static Analyzer Path Override:", 45, 200, 150, 20)
    $sAnalyzerVal = ""
    ; Fetch default values
    If IsMap($mConfig) And __JSON_MapExists($mConfig, "configs") Then
        $mConfigsMapVal = $mConfig["configs"]
        If IsMap($mConfigsMapVal) And __JSON_MapExists($mConfigsMapVal, "default_mythos") Then
            $mDefMyth = $mConfigsMapVal["default_mythos"]
            If IsMap($mDefMyth) Then
                If __JSON_MapExists($mDefMyth, "analyzer_path") Then $sAnalyzerVal = $mDefMyth["analyzer_path"]
            EndIf
        EndIf
    EndIf
    If $sAnalyzerVal == "" Then $sAnalyzerVal = "<Auto-Discover>"
    $idAnalyzerPath = GUICtrlCreateInput($sAnalyzerVal, 200, 197, 530, 21)
    $idBtnBrowseAnalyzer = GUICtrlCreateButton("...", 740, 196, 25, 22)
    GUICtrlSetTip($idBtnBrowseAnalyzer, "Browse for autoit_windows_x64_scoping_analyzer executable or python script.")

    GUICtrlCreateLabel("Python Executable Path:", 45, 240, 150, 20)
    $sPythonVal = "python.exe"
    If IsMap($mConfig) And __JSON_MapExists($mConfig, "configs") Then
        $mConfigsMapVal = $mConfig["configs"]
        If IsMap($mConfigsMapVal) And __JSON_MapExists($mConfigsMapVal, "default_mythos") Then
            $mDefMyth = $mConfigsMapVal["default_mythos"]
            If IsMap($mDefMyth) Then
                If __JSON_MapExists($mDefMyth, "python_path") Then $sPythonVal = $mDefMyth["python_path"]
            EndIf
        EndIf
    EndIf
    $idPythonPath = GUICtrlCreateInput($sPythonVal, 200, 237, 530, 21)
    $idBtnBrowsePython = GUICtrlCreateButton("...", 740, 236, 25, 22)
    GUICtrlSetTip($idBtnBrowsePython, "Browse for python.exe executable.")
    GUICtrlCreateGroup("", -99, -99, 1, 1)

    ; End Tab Definition
    GUICtrlCreateTabItem("")

    ; Save button (visible globally)
    $idBtnSave = GUICtrlCreateButton("Save All Settings", 330, 605, 180, 32)
    GUICtrlSetTip($idBtnSave, "Write all changes to config.json.")

    ; Initialise View Lists
    RefreshRulesListView()
    RefreshProfilesListView()
    UpdateRuleConfigCombo("mythos")
    UpdateProfilePanelsVisibility("mythos")
    LoadRecentCallers()
    UpdateIntegrationUIState()

    AdlibRegister("CheckConfigRefresh", 1000)

    GUIRegisterMsg($WM_NOTIFY, "WM_NOTIFY")
    GUISetState(@SW_SHOW)

    While 1
        $nMsg = GUIGetMsg()
        Switch $nMsg
            Case $GUI_EVENT_CLOSE
                Exit
                
            Case $idMenuAbout
                ShowAboutDialog()
                
            Case $idBtnBrowsePython
                $sFile = FileOpenDialog("Select Python Executable", "C:\", "Executables (*.exe)", 1)
                If Not @error Then GUICtrlSetData($idPythonPath, $sFile)
                
            Case $idBtnBrowseAnalyzer
                $sFile = FileOpenDialog("Select Static Analyzer Engine", @ScriptDir, "Executables & Scripts (*.exe;*.py)|Python Scripts (*.py)|Executables (*.exe)", 1)
                If Not @error Then GUICtrlSetData($idAnalyzerPath, $sFile)
                
            Case $idBtnBrowseRulePath
                $sSelDir = FileSelectFolder("Select Path Prefix Constraint", "C:\")
                If Not @error Then GUICtrlSetData($idInpRulePath, $sSelDir)
                
            ; Tab 1 Rule Edit Form Actions
            Case $idComboRuleAction
                $sAct = GUICtrlRead($idComboRuleAction)
                UpdateRuleConfigCombo($sAct)
                
            Case $idDummyRulesLV
                $iIdx = GUICtrlRead($idListView)
                If $iIdx > 0 Then
                    $sData = GUICtrlRead($iIdx)
                    $aParts = StringSplit($sData, "|")
                    If IsArray($aParts) And $aParts[0] >= 4 Then
                        GUICtrlSetData($idInpRuleApp, $aParts[1])
                        GUICtrlSetData($idInpRulePath, $aParts[2])
                        GUICtrlSetData($idComboRuleAction, $aParts[3])
                        UpdateRuleConfigCombo($aParts[3], $aParts[4])
                    EndIf
                EndIf
                
            Case $idBtnAddRule
                $sApp = StringStripWS(GUICtrlRead($idInpRuleApp), 3)
                $sPrefix = StringStripWS(GUICtrlRead($idInpRulePath), 3)
                $sAct = GUICtrlRead($idComboRuleAction)
                $sConf = GUICtrlRead($idComboRuleConfig)
                If $sApp == "" Or $sPrefix == "" Then
                    MsgBox($MB_ICONWARNING, "Validation Error", "App Name and Path Prefix cannot be empty.", 0, $hMainGui)
                    ContinueLoop
                EndIf
                GUICtrlCreateListViewItem($sApp & "|" & $sPrefix & "|" & $sAct & "|" & $sConf, $idListView)
                
            Case $idBtnUpdateRule
                $iIdx = GUICtrlRead($idListView)
                If $iIdx > 0 Then
                    $sApp = StringStripWS(GUICtrlRead($idInpRuleApp), 3)
                    $sPrefix = StringStripWS(GUICtrlRead($idInpRulePath), 3)
                    $sAct = GUICtrlRead($idComboRuleAction)
                    $sConf = GUICtrlRead($idComboRuleConfig)
                    If $sApp == "" Or $sPrefix == "" Then
                        MsgBox($MB_ICONWARNING, "Validation Error", "App Name and Path Prefix cannot be empty.", 0, $hMainGui)
                        ContinueLoop
                    EndIf
                    GUICtrlSetData($iIdx, $sApp & "|" & $sPrefix & "|" & $sAct & "|" & $sConf)
                Else
                    MsgBox($MB_ICONWARNING, "Notice", "Select a rule in the Rules Matrix ListView first.", 0, $hMainGui)
                EndIf
                
            Case $idBtnDeleteRule
                $iIdx = GUICtrlRead($idListView)
                If $iIdx > 0 Then
                    GUICtrlDelete($iIdx)
                Else
                    MsgBox($MB_ICONWARNING, "Notice", "Select a rule in the Rules Matrix ListView first.", 0, $hMainGui)
                EndIf
                
            Case $idBtnAddFromCallers
                $iCtrlId = GUICtrlRead($idCallersListView)
                If $iCtrlId > 0 Then
                    $sData = GUICtrlRead($iCtrlId)
                    $aDataParts = StringSplit($sData, "|")
                    If IsArray($aDataParts) And $aDataParts[0] >= 3 Then
                        $sSelCaller = $aDataParts[1]
                        $sSelPath = $aDataParts[3] ; AppName is 1, Params is 2, Path is 3
                        
                        $sDirPrefix = "*"
                        If StringInStr(StringLower($sSelPath), ".au3") > 0 Then
                            $iLastSlash = StringInStr($sSelPath, "\", 0, -1)
                            If $iLastSlash > 0 Then
                                $sDirPrefix = StringLeft($sSelPath, $iLastSlash - 1)
                            EndIf
                        EndIf
                        
                        GUICtrlSetData($idInpRuleApp, $sSelCaller)
                        GUICtrlSetData($idInpRulePath, $sDirPrefix)
                        GUICtrlSetData($idComboRuleAction, "mythos")
                        UpdateRuleConfigCombo("mythos", "default_mythos")
                    EndIf
                Else
                    MsgBox($MB_ICONWARNING, "Notice", "Select a tracked calling application from the list first.", 0, $hMainGui)
                Endif
                
            ; Tab 2 Config Profiles Actions
            Case $idComboProfType
                UpdateProfilePanelsVisibility(GUICtrlRead($idComboProfType))
                
            Case $idDummyProfilesLV
                $iIdx = GUICtrlRead($idProfilesListView)
                If $iIdx > 0 Then
                    $sData = GUICtrlRead($iIdx)
                    $aParts = StringSplit($sData, "|")
                    If IsArray($aParts) And $aParts[0] >= 2 Then
                        $sProfName = $aParts[1]
                        $sProfType = $aParts[2]
                        
                        GUICtrlSetData($idInpProfName, $sProfName)
                        GUICtrlSetData($idComboProfType, $sProfType)
                        
                        If StringLeft($sProfName, 8) == "default_" Then
                            GUICtrlSetState($idInpProfName, $GUI_DISABLE)
                            GUICtrlSetState($idComboProfType, $GUI_DISABLE)
                            GUICtrlSetState($idBtnDeleteProfile, $GUI_DISABLE)
                        Else
                            GUICtrlSetState($idInpProfName, $GUI_ENABLE)
                            GUICtrlSetState($idComboProfType, $GUI_ENABLE)
                            GUICtrlSetState($idBtnDeleteProfile, $GUI_ENABLE)
                        EndIf
                        
                        LoadProfileInputs($sProfName, $sProfType)
                        UpdateProfilePanelsVisibility($sProfType)
                    EndIf
                EndIf
                
            Case $idBtnAddProfile
                $sProfName = StringStripWS(GUICtrlRead($idInpProfName), 3)
                $sProfType = GUICtrlRead($idComboProfType)
                If $sProfName == "" Then
                    MsgBox($MB_ICONWARNING, "Validation Error", "Profile name cannot be empty.", 0, $hMainGui)
                    ContinueLoop
                EndIf
                $mConfigsMap = $mConfig["configs"]
                If __JSON_MapExists($mConfigsMap, $sProfName) Then
                    MsgBox($MB_ICONWARNING, "Error", "Profile name already exists.", 0, $hMainGui)
                    ContinueLoop
                EndIf
                
                Local $mProfileAdd[]
                $mProfileAdd["type"] = $sProfType
                
                If $sProfType == "mythos" Then
                    $mProfileAdd["python_path"] = GUICtrlRead($idPythonPath)
                    $mProfileAdd["analyzer_path"] = GUICtrlRead($idAnalyzerPath)
                    If $mProfileAdd["analyzer_path"] == "<Auto-Discover>" Then $mProfileAdd["analyzer_path"] = ""
                    $mProfileAdd["skip_system_includes"] = (GUICtrlRead($idProfSkipSystem) = $GUI_CHECKED)
                    $mProfileAdd["enable_experimental_checks"] = (GUICtrlRead($idProfExperimental) = $GUI_CHECKED)
                    $mProfileAdd["engine_mode"] = GUICtrlRead($idComboProfEngineMode)
                    $mProfileAdd["no_auto_include_discovery"] = (GUICtrlRead($idProfNoAutoInclude) = $GUI_CHECKED)
                    $mProfileAdd["enable_system_dead_stores"] = (GUICtrlRead($idProfSystemDeadStores) = $GUI_CHECKED)
                    
                    Local $mWarnAdd[]
                    Local $aWarnIdsAdd[7] = [$idProfWarn1, $idProfWarn2, $idProfWarn3, $idProfWarn4, $idProfWarn5, $idProfWarn6, $idProfWarn7]
                    For $i = 1 To 7
                        $mWarnAdd[String($i)] = (GUICtrlRead($aWarnIdsAdd[$i - 1]) = $GUI_CHECKED)
                    Next
                    $mProfileAdd["warnings"] = $mWarnAdd
                Else
                    $mProfileAdd["extra_args"] = GUICtrlRead($idProfExtraArgs)
                    $mProfileAdd["override_args"] = (GUICtrlRead($idProfOverrideArgs) = $GUI_CHECKED)
                EndIf
                
                $mConfigsMap[$sProfName] = $mProfileAdd
                $mConfig["configs"] = $mConfigsMap
                
                RefreshProfilesListView()
                MsgBox($MB_ICONINFORMATION, "Success", "Profile created. Remember to save all settings to apply changes.", 0, $hMainGui)
                
            Case $idBtnSaveProfile
                $sProfName = StringStripWS(GUICtrlRead($idInpProfName), 3)
                $sProfType = GUICtrlRead($idComboProfType)
                If $sProfName == "" Then
                    MsgBox($MB_ICONWARNING, "Validation Error", "Profile name cannot be empty.", 0, $hMainGui)
                    ContinueLoop
                EndIf
                
                $mConfigsMap = $mConfig["configs"]
                Local $mProfileSave[]
                $mProfileSave["type"] = $sProfType
                
                If $sProfType == "mythos" Then
                    $mProfileSave["python_path"] = GUICtrlRead($idPythonPath)
                    $mProfileSave["analyzer_path"] = GUICtrlRead($idAnalyzerPath)
                    If $mProfileSave["analyzer_path"] == "<Auto-Discover>" Then $mProfileSave["analyzer_path"] = ""
                    $mProfileSave["skip_system_includes"] = (GUICtrlRead($idProfSkipSystem) = $GUI_CHECKED)
                    $mProfileSave["enable_experimental_checks"] = (GUICtrlRead($idProfExperimental) = $GUI_CHECKED)
                    $mProfileSave["engine_mode"] = GUICtrlRead($idComboProfEngineMode)
                    $mProfileSave["no_auto_include_discovery"] = (GUICtrlRead($idProfNoAutoInclude) = $GUI_CHECKED)
                    $mProfileSave["enable_system_dead_stores"] = (GUICtrlRead($idProfSystemDeadStores) = $GUI_CHECKED)
                    
                    Local $mWarnSave[]
                    Local $aWarnIdsSave[7] = [$idProfWarn1, $idProfWarn2, $idProfWarn3, $idProfWarn4, $idProfWarn5, $idProfWarn6, $idProfWarn7]
                    For $i = 1 To 7
                        $mWarnSave[String($i)] = (GUICtrlRead($aWarnIdsSave[$i - 1]) = $GUI_CHECKED)
                    Next
                    $mProfileSave["warnings"] = $mWarnSave
                Else
                    $mProfileSave["extra_args"] = GUICtrlRead($idProfExtraArgs)
                    $mProfileSave["override_args"] = (GUICtrlRead($idProfOverrideArgs) = $GUI_CHECKED)
                EndIf
                
                $mConfigsMap[$sProfName] = $mProfileSave
                $mConfig["configs"] = $mConfigsMap
                
                RefreshProfilesListView()
                MsgBox($MB_ICONINFORMATION, "Success", "Profile updated. Remember to save all settings to apply changes.", 0, $hMainGui)
                
            Case $idBtnDeleteProfile
                $sProfName = StringStripWS(GUICtrlRead($idInpProfName), 3)
                If $sProfName == "" Then ContinueLoop
                If StringLeft($sProfName, 8) == "default_" Then
                    MsgBox($MB_ICONWARNING, "Error", "Cannot delete default profiles.", 0, $hMainGui)
                    ContinueLoop
                EndIf
                
                $mConfigsMap = $mConfig["configs"]
                If Not __JSON_MapExists($mConfigsMap, $sProfName) Then ContinueLoop
                
                $iAns = MsgBox(BitOr($MB_YESNO, $MB_ICONQUESTION), "Confirm Delete", "Are you sure you want to delete profile: " & $sProfName & "?", 0, $hMainGui)
                If $iAns == $IDYES Then
                    MapRemove($mConfigsMap, $sProfName)
                    $mConfig["configs"] = $mConfigsMap
                    
                    $aRules = $mConfig["rules"]
                    If IsArray($aRules) Then
                        For $i = 0 To UBound($aRules) - 1
                            $mRule = $aRules[$i]
                            If IsMap($mRule) And __JSON_MapExists($mRule, "config") And $mRule["config"] == $sProfName Then
                                $sAct = __JSON_MapExists($mRule, "action") ? $mRule["action"] : "original"
                                $mRule["config"] = ($sAct == "mythos" ? "default_mythos" : "default_original")
                                $aRules[$i] = $mRule
                            EndIf
                        Next
                        $mConfig["rules"] = $aRules
                    EndIf
                    
                    RefreshProfilesListView()
                    RefreshRulesListView()
                    MsgBox($MB_ICONINFORMATION, "Success", "Profile deleted. Remember to save all settings to apply changes.", 0, $hMainGui)
                EndIf
                
            Case $idBtnToggle
                $bInstalled = FileExists($sAu3CheckOrigPath)
                If $bInstalled Then
                    If IsAdmin() Then
                        If Not FileExists($sAu3CheckOrigPath) Then
                            MsgBox($MB_ICONWARNING, "Notice", "No original backup found. Original is already active.", 0, $hMainGui)
                            ContinueLoop
                        EndIf
                        If RobustFileCopy($sAu3CheckOrigPath, $sAu3CheckPath) Then
                            FileDelete($sAu3CheckOrigPath)
                            If FileExists($sAu3CheckOrigDatPath) Then FileDelete($sAu3CheckOrigDatPath)
                            $sNewJson = _JSON_Generate($mConfig)
                            $hFile = FileOpen($sConfigPath, 2)
                            If $hFile <> -1 Then
                                FileWrite($hFile, $sNewJson)
                                FileClose($hFile)
                            EndIf
                            UpdateIntegrationUIState()
                        Else
                            MsgBox($MB_ICONERROR, "Error", "Failed to restore original Au3Check.exe.", 0, $hMainGui)
                        EndIf
                    Else
                        $iAns = MsgBox(BitOr($MB_YESNO, $MB_ICONINFORMATION), "Elevation Required", _
                            "To restore the original Au3Check.exe, the Settings Manager needs to write to 'C:\Program Files (x86)\AutoIt3\'. " & _
                            "This requires Administrator privileges." & @CRLF & @CRLF & _
                            "Would you like to elevate the installer now to perform this action?", 0, $hMainGui)
                        If $iAns == $IDYES Then
                            $iRet = ElevateAction("/restore")
                            if $iRet = 0 Then
                                $sNewJson = _JSON_Generate($mConfig)
                                $hFile = FileOpen($sConfigPath, 2)
                                If $hFile <> -1 Then
                                    FileWrite($hFile, $sNewJson)
                                    FileClose($hFile)
                                EndIf
                            Else
                                MsgBox($MB_ICONERROR, "Error", "Failed to restore original Au3Check.exe (Code: " & $iRet & ").", 0, $hMainGui)
                            EndIf
                            UpdateIntegrationUIState()
                        EndIf
                    EndIf
                Else
                    If IsAdmin() Then
                        If $sWrapperSource == "" Then
                            MsgBox($MB_ICONERROR, "Error", "Wrapper source executable not found in any default locations.", 0, $hMainGui)
                            ContinueLoop
                        EndIf
                        If Not FileExists($sAu3CheckOrigPath) Then
                            If Not RobustFileCopy($sAu3CheckPath, $sAu3CheckOrigPath) Then
                                MsgBox($MB_ICONERROR, "Error", "Failed to create original backup of Au3Check.exe.", 0, $hMainGui)
                                ContinueLoop
                            EndIf
                        EndIf
                        If Not FileExists($sAu3CheckOrigDatPath) Then
                            If FileExists($sAu3CheckDatPath) Then
                                RobustFileCopy($sAu3CheckDatPath, $sAu3CheckOrigDatPath)
                            EndIf
                        EndIf
                        If RobustFileCopy($sWrapperSource, $sAu3CheckPath) Then
                            $sDir = StringRegExpReplace($sConfigPath, "\\[^\\]+$", "")
                            If Not FileExists($sDir) Then DirCreate($sDir)
                            $sNewJson = _JSON_Generate($mConfig)
                            $hFile = FileOpen($sConfigPath, 2)
                            If $hFile <> -1 Then
                                FileWrite($hFile, $sNewJson)
                                FileClose($hFile)
                            EndIf
                            UpdateIntegrationUIState()
                        Else
                            MsgBox($MB_ICONERROR, "Error", "Failed to copy wrapper to: " & $sAu3CheckPath, 0, $hMainGui)
                        EndIf
                    Else
                        $iAns = MsgBox(BitOr($MB_YESNO, $MB_ICONINFORMATION), "Elevation Required", _
                            "To install the au3Check Wrapper, the Settings Manager needs to write to 'C:\Program Files (x86)\AutoIt3\'. " & _
                            "This requires Administrator privileges." & @CRLF & @CRLF & _
                            "Would you like to elevate the installer now to perform this action?", 0, $hMainGui)
                        If $iAns == $IDYES Then
                            $iRet = ElevateAction("/install")
                            If $iRet = 0 Then
                                $sDir = StringRegExpReplace($sConfigPath, "\\[^\\]+$", "")
                                If Not FileExists($sDir) Then DirCreate($sDir)
                                $sNewJson = _JSON_Generate($mConfig)
                                $hFile = FileOpen($sConfigPath, 2)
                                If $hFile <> -1 Then
                                    FileWrite($hFile, $sNewJson)
                                    FileClose($hFile)
                                EndIf
                            Else
                                MsgBox($MB_ICONERROR, "Error", "Failed to install wrapper (Code: " & $iRet & ").", 0, $hMainGui)
                            EndIf
                            UpdateIntegrationUIState()
                        EndIf
                    EndIf
                EndIf
                
            Case $idBtnSave
                SaveConfig()
        EndSwitch
    WEnd
EndFunc

Main()

; #FUNCTION# ====================================================================================================================
; Name...........: ShowAboutDialog
; Description ...: Displays the About box with authors and version info.
; Syntax.........: ShowAboutDialog()
; Parameters ....: None.
; Return values .: None.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func ShowAboutDialog()
    Local $hAboutGUI = GUICreate("About au3Mythos", 420, 290, -1, -1, BitOR($DS_MODALFRAME, $WS_CAPTION, $WS_SYSMENU), -1, $hMainGui)
    GUISetBkColor(0xF5F6F7, $hAboutGUI)
    
    GUICtrlCreateLabel("au3Mythos Settings Manager", 20, 20, 380, 30)
    GUICtrlSetFont(-1, 16, 800, 0, "Segoe UI")
    GUICtrlSetColor(-1, 0x1A73E8)
    
    GUICtrlCreateLabel("Version 1.1.0", 20, 50, 380, 20)
    GUICtrlSetFont(-1, 10, 400, 0, "Segoe UI")
    GUICtrlSetColor(-1, 0x666666)
    
    Local $sDesc = "An advanced static scoping diagnostics engine and drop-in replacement for Au3Check. " & _
                   "Features deep block-scoping analysis, duplicate variable declarations checking, parameter count validation, and unused variable detection." & @CRLF & @CRLF & _
                   "Designed with Love for the AutoIt Developer community."
    GUICtrlCreateLabel($sDesc, 20, 85, 380, 120)
    GUICtrlSetFont(-1, 9.5, 400, 0, "Segoe UI")
    GUICtrlSetColor(-1, 0x333333)
    
    GUICtrlCreateLabel("Copyright © 2026 Harald Frank / ", 20, 215, 162, 20)
    GUICtrlSetFont(-1, 8.5, 400, 0, "Segoe UI")
    GUICtrlSetColor(-1, 0x888888)
    
    Local $idLinkGithub = GUICtrlCreateLabel("Blowcake", 185, 215, 55, 20)
    GUICtrlSetFont(-1, 8.5, 400, 4, "Segoe UI") ; Underline
    GUICtrlSetColor(-1, 0x1A73E8) ; Link blue
    GUICtrlSetCursor(-1, 0) ; Hand cursor
    
    GUICtrlCreateLabel(". All Rights Reserved.", 242, 215, 120, 20)
    GUICtrlSetFont(-1, 8.5, 400, 0, "Segoe UI")
    GUICtrlSetColor(-1, 0x888888)
    
    Local $idBtnClose = GUICtrlCreateButton("Close", 160, 245, 100, 30)
    GUICtrlSetFont(-1, 10, 600, 0, "Segoe UI")
    
    GUISetState(@SW_SHOW, $hAboutGUI)
    
    While 1
        Local $nMsgSub = GUIGetMsg()
        If $nMsgSub == $GUI_EVENT_CLOSE Or $nMsgSub == $idBtnClose Then
            ExitLoop
        ElseIf $nMsgSub == $idLinkGithub Then
            ShellExecute("https://github.com/Blowcake")
        EndIf
    WEnd
    
    GUIDelete($hAboutGUI)
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: WM_NOTIFY
; Description ...: Windows notification message handler (specifically for handling ListView click and select events).
; Syntax.........: WM_NOTIFY($hWnd, $iMsg, $wParam, $lParam)
; Parameters ....: $hWnd   - Window handle.
;                  $iMsg   - Message ID.
;                  $wParam - Message parameter.
;                  $lParam - Pointer to a notification structure.
; Return values .: System default message handler return value ($GUI_RUNDEFMSG).
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func WM_NOTIFY($hWnd, $iMsg, $wParam, $lParam)
    #forceref $hWnd, $iMsg, $wParam
    Local $tNMHDR = DllStructCreate("handle hWndFrom;uint_ptr IDFrom;int Code", $lParam)
    Local $hWndFrom = DllStructGetData($tNMHDR, "hWndFrom")
    Local $iCode = DllStructGetData($tNMHDR, "Code")
    
    Local Const $NM_CLICK = -2
    Local Const $LVN_FIRST = -100
    Local Const $LVN_ITEMCHANGED = $LVN_FIRST - 1
    Local Const $LVIS_SELECTED = 2
    
    Local $bTrigger = False
    If $iCode = $NM_CLICK Then
        $bTrigger = True
    ElseIf $iCode = $LVN_ITEMCHANGED Then
        Local $tNMLISTVIEW = DllStructCreate("handle hWndFrom;uint_ptr IDFrom;int Code;int Item;int SubItem;uint NewState", $lParam)
        Local $iNewState = DllStructGetData($tNMLISTVIEW, "NewState")
        If BitAND($iNewState, $LVIS_SELECTED) Then
            $bTrigger = True
        EndIf
    EndIf
    
    If $bTrigger Then
        If $hWndFrom = $hRulesLV Then
            GUICtrlSendToDummy($idDummyRulesLV)
        ElseIf $hWndFrom = $hProfilesLV Then
            GUICtrlSendToDummy($idDummyProfilesLV)
        EndIf
    EndIf
    Return $GUI_RUNDEFMSG
EndFunc

; #FUNCTION# ====================================================================================================================
; Name...........: ShowSplashScreen
; Description ...: Displays a startup splash screen logo for 1.5 seconds.
; Syntax.........: ShowSplashScreen()
; Parameters ....: None.
; Return values .: None.
; Author ........: Harald Frank
; Modified.......:
; ===============================================================================================================================
Func ShowSplashScreen()
    Local $sLogoPath = @ScriptDir & "\resources\mythos_logo_600x327.jpg"
    If Not FileExists($sLogoPath) Then
        $sLogoPath = @ScriptDir & "\..\resources\mythos_logo_600x327.jpg"
    EndIf
    If Not FileExists($sLogoPath) Then Return

    Local $iW = 600
    Local $iH = 327
    Local $hSplash = GUICreate("au3Mythos Startup", $iW, $iH, -1, -1, $WS_POPUP, BitOR($WS_EX_TOPMOST, $WS_EX_TOOLWINDOW))
    GUICtrlCreatePic($sLogoPath, 0, 0, $iW, $iH)

    GUISetState(@SW_SHOW, $hSplash)
    Sleep(1500)
    GUIDelete($hSplash)
EndFunc
