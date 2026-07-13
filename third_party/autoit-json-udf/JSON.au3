#include-once
#include <Array.au3>


; #INDEX# =======================================================================================================================
; Title .........: JSON-UDF
; Version .......: 0.5.1
; AutoIt Version : 3.3.18.0
; Language ......: english (german maybe by accident)
; Description ...: Function for interacting with JSON data in AutoIt.
;                  This includes import, export as well as helper functions for handling nested AutoIt data structures.
; Author(s) .....: AspirinJunkie, Sven Seyfert (SOLVE-SMART)
; Last changed ..: 2025-11-20
; Link ..........: https://github.com/Sylvan86/autoit-json-udf
; License .......: This work is free.
;                  You can redistribute it and/or modify it under the terms of the Do What The Fuck You Want To Public License, Version 2,
;                  as published by Sam Hocevar.
;                  See http://www.wtfpl.net/ for more details.
; ===============================================================================================================================

;      __JSON_Base64Decode   - decode data which is coded as a base64-string into binary variable
;      __JSON_Base64Encode   - converts a binary- or string-Input into BASE64 (or optional base64url) format
;      __JSON_MapExists      - (Compatibility) checks if a key exists in a map
; ===============================================================================================================================

Func __JSON_MapExists(ByRef $m, $k)
    If Not IsMap($m) Then Return False
    Local $a = MapKeys($m)
    For $i = 0 To UBound($a) - 1
        If $a[$i] == $k Then Return True
    Next
    Return False
EndFunc
; ===============================================================================================================================

; #FUNCTION# ======================================================================================
; Name ..........: _JSON_Parse
; Description ...: convert a JSON-formatted string into a nested structure of AutoIt-datatypes
; Syntax ........: _JSON_Parse(Const $sString, $iOs = 1)
; Parameters ....: $sString      - a string formatted as JSON
;                  [$iOs]        - search position where to start (normally don't touch!)
; Return values .: Success - Return a nested structure of AutoIt-datatypes
;                       @extended = next string offset
;                  Failure - Return "" and set @error to:
;                       @error = 1 - part is not json-syntax
;                              = 2 - key name in object part is not json-syntax
;                              = 3 - value in object is not correct json
;                              = 4 - delimiter or object end expected but not gained
; Author ........: AspirinJunkie
; =================================================================================================
Func _JSON_Parse(Const $sString, $iOs = 1)
	Local $vValue
	Local $iLen = StringLen($sString)

	; skip whitespace
	While $iOs <= $iLen
		Switch StringMid($sString, $iOs, 1)
			Case " ", @TAB, @CR, @LF
				$iOs += 1
			Case Else
				ExitLoop
		EndSwitch
	WEnd

	If $iOs > $iLen Then Return SetError(1, 0, "")

	; check value type
	Switch StringMid($sString, $iOs, 1)
		Case "{" ; Object
			Local $mRet[]
			$iOs += 1

			While $iOs <= $iLen
				; skip whitespace
				While $iOs <= $iLen
					Switch StringMid($sString, $iOs, 1)
						Case " ", @TAB, @CR, @LF
							$iOs += 1
						Case Else
							ExitLoop
					EndSwitch
				WEnd

				If StringMid($sString, $iOs, 1) == "}" Then
					$iOs += 1
					Return SetExtended($iOs, $mRet)
				EndIf

				; extract key
				Local $sKey
				$vValue = _JSON_Parse($sString, $iOs)
				If @error Then Return SetError(2, @error, "")
				$sKey = $vValue
				$iOs = @extended

				; skip whitespace
				While $iOs <= $iLen
					Switch StringMid($sString, $iOs, 1)
						Case " ", @TAB, @CR, @LF
							$iOs += 1
						Case Else
							ExitLoop
					EndSwitch
				WEnd

				; check for colon
				If StringMid($sString, $iOs, 1) <> ":" Then Return SetError(4, 0, "")
				$iOs += 1

				; extract value
				$vValue = _JSON_Parse($sString, $iOs)
				If @error Then Return SetError(3, @error, "")
				$mRet[$sKey] = $vValue
				$iOs = @extended

				; skip whitespace
				While $iOs <= $iLen
					Switch StringMid($sString, $iOs, 1)
						Case " ", @TAB, @CR, @LF
							$iOs += 1
						Case Else
							ExitLoop
					EndSwitch
				WEnd

				; check for comma or object end
				Switch StringMid($sString, $iOs, 1)
					Case ","
						$iOs += 1
					Case "}"
						$iOs += 1
						Return SetExtended($iOs, $mRet)
					Case Else
						Return SetError(4, 0, "")
				EndSwitch
			WEnd
		Case "[" ; Array
			Local $aRet[0]
			$iOs += 1

			While $iOs <= $iLen
				; skip whitespace
				While $iOs <= $iLen
					Switch StringMid($sString, $iOs, 1)
						Case " ", @TAB, @CR, @LF
							$iOs += 1
						Case Else
							ExitLoop
					EndSwitch
				WEnd

				If StringMid($sString, $iOs, 1) == "]" Then
					$iOs += 1
					Return SetExtended($iOs, $aRet)
				EndIf

				; extract value
				$vValue = _JSON_Parse($sString, $iOs)
				If @error Then Return SetError(3, @error, "")
				Local $iNextOs = @extended
				_ArrayAdd($aRet, $vValue)
				$iOs = $iNextOs

				; skip whitespace
				While $iOs <= $iLen
					Switch StringMid($sString, $iOs, 1)
						Case " ", @TAB, @CR, @LF
							$iOs += 1
						Case Else
							ExitLoop
					EndSwitch
				WEnd

				; check for comma or array end
				Switch StringMid($sString, $iOs, 1)
					Case ","
						$iOs += 1
					Case "]"
						$iOs += 1
						Return SetExtended($iOs, $aRet)
					Case Else
						Return SetError(4, 0, "")
				EndSwitch
			WEnd
		Case '"' ; String
			$iOs += 1
			Local $iStart = $iOs
			Local $sStringRet = ""
			While $iOs <= $iLen
				Switch StringMid($sString, $iOs, 1)
					Case '"'
						$sStringRet &= StringMid($sString, $iStart, $iOs - $iStart)
						$iOs += 1
						Return SetExtended($iOs, $sStringRet)
					Case "\"
						$sStringRet &= StringMid($sString, $iStart, $iOs - $iStart)
						$iOs += 1
						Switch StringMid($sString, $iOs, 1)
							Case '"', "\", "/"
								$sStringRet &= StringMid($sString, $iOs, 1)
							Case "b"
								$sStringRet &= Chr(8)
							Case "f"
								$sStringRet &= Chr(12)
							Case "n"
								$sStringRet &= @LF
							Case "r"
								$sStringRet &= @CR
							Case "t"
								$sStringRet &= @TAB
							Case "u"
								$iOs += 1
								$sStringRet &= ChrW(Dec(StringMid($sString, $iOs, 4)))
								$iOs += 3
						EndSwitch
						$iOs += 1
						$iStart = $iOs
					Case Else
						$iOs += 1
				EndSwitch
			WEnd
		Case "t" ; true
			If StringMid($sString, $iOs, 4) == "true" Then
				Return SetExtended($iOs + 4, True)
			EndIf
		Case "f" ; false
			If StringMid($sString, $iOs, 5) == "false" Then
				Return SetExtended($iOs + 5, False)
			EndIf
		Case "n" ; null
			If StringMid($sString, $iOs, 4) == "null" Then
				Return SetExtended($iOs + 4, Null)
			EndIf
		Case "-", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9" ; Number
			Local $iNumStart = $iOs
			While $iOs <= $iLen
				Switch StringMid($sString, $iOs, 1)
					Case "-", "+", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "e", "E"
						$iOs += 1
					Case Else
						ExitLoop
				EndSwitch
			WEnd
			Return SetExtended($iOs, Number(StringMid($sString, $iNumStart, $iOs - $iNumStart)))
	EndSwitch

	Return SetError(1, 0, "")
EndFunc
; =================================================================================================

; #FUNCTION# ======================================================================================
; Name ..........: _JSON_Generate
; Description ...: convert a nested AutoIt data structure into a JSON structured string
; Syntax ........: _JSON_Generate($vVar)
; Parameters ....: $vVar              - the AutoIt data structure
; Return values .: Success - Return a JSON structured string
;                  Failure - Return "" and set @error to 1
; Author ........: AspirinJunkie, Sven Seyfert (SOLVE-SMART)
; =================================================================================================
Func _JSON_Generate($vVar)
	If IsString($vVar) Then Return '"' & __JSON_FormatString($vVar) & '"'
	If IsNumber($vVar) Then Return String($vVar)
	If IsBool($vVar) Then Return $vVar ? "true" : "false"
	If IsKeyword($vVar) Then Return "null"
	
	If IsArray($vVar) Then
		Local $sRet = "["
		For $i = 0 To UBound($vVar) - 1
			$sRet &= _JSON_Generate($vVar[$i]) & ","
		Next
		If StringRight($sRet, 1) == "," Then $sRet = StringTrimRight($sRet, 1)
		Return $sRet & "]"
	EndIf

	If IsMap($vVar) Then
		Local $sMapRet = "{"
		Local $aKeys = MapKeys($vVar)
		For $i = 0 To UBound($aKeys) - 1
			$sMapRet &= '"' & __JSON_FormatString(String($aKeys[$i])) & '":' & _JSON_Generate($vVar[$aKeys[$i]]) & ","
		Next
		If StringRight($sMapRet, 1) == "," Then $sMapRet = StringTrimRight($sMapRet, 1)
		Return $sMapRet & "}"
	EndIf
	
	Return SetError(1, 0, "")
EndFunc


; #FUNCTION# ======================================================================================
; Name ..........: _JSON_GenerateCompact
; Description ...: shorthand for _JSON_Generate() to create JSON structured strings as compact as possible
; Syntax ........: _JSON_GenerateCompact($v_Var)
; Parameters ....: $v_Var             - the data to be converted
; Return values .: Success: string formatted as JSON
;                  Failure: Set @error
; Author ........: AspirinJunkie
; =================================================================================================
Func _JSON_GenerateCompact($v_Var)
	Return _JSON_Generate($v_Var)
EndFunc   ;==>_JSON_GenerateCompact


; #FUNCTION# ======================================================================================
; Name ..........: _JSON_Unminify
; Description ...: reads minified (compact) JSON file or string and converts to well readable JSON string
; Syntax ........: _JSON_Unminify($s_JSON [, $s_Indent = "    "])
; Parameters ....: $s_JSON            - Valid JSON string or path to JSON file
;                  $s_Indent          - [optional] indentation characters (default: 4 spaces)
; Return values .: Success: readable string formatted as JSON
;                  Failure: "" set @error:
;                     @error = 1 : invalid JSON
; Author ........: AspirinJunkie
; =================================================================================================
Func _JSON_Unminify($s_JSON, $s_Indent = "    ")
	If FileExists($s_JSON) Then $s_JSON = FileRead($s_JSON)
	Local $s_Ret, $i_ScanPos, $c_Char, $i_Level
	Local $b_InString, $s_StringChar
	Local $i_Len = StringLen($s_JSON)

	For $i_ScanPos = 1 To $i_Len
		$c_Char = StringMid($s_JSON, $i_ScanPos, 1)

		If $b_InString Then
			$s_Ret &= $c_Char
			If $c_Char == "\" Then
				$i_ScanPos += 1
				$s_Ret &= StringMid($s_JSON, $i_ScanPos, 1)
			ElseIf $c_Char == $s_StringChar Then
				$b_InString = False
			EndIf
		Else
			Switch $c_Char
				Case " ", @TAB, @CR, @LF
					; ignore whitespace outside strings
				Case "{", "["
					$i_Level += 1
					$s_Ret &= $c_Char & @CRLF
					For $i = 1 To $i_Level
						$s_Ret &= $s_Indent
					Next
				Case "}", "]"
					$i_Level -= 1
					$s_Ret &= @CRLF
					For $i = 1 To $i_Level
						$s_Ret &= $s_Indent
					Next
					$s_Ret &= $c_Char
				Case ","
					$s_Ret &= $c_Char & @CRLF
					For $i = 1 To $i_Level
						$s_Ret &= $s_Indent
					Next
				Case ":"
					$s_Ret &= ": "
				Case '"', "'"
					$b_InString = True
					$s_StringChar = $c_Char
					$s_Ret &= $c_Char
				Case Else
					$s_Ret &= $c_Char
			EndSwitch
		EndIf
	Next
	Return $s_Ret
EndFunc   ;==>_JSON_Unminify


; #FUNCTION# ======================================================================================
; Name ..........: _JSON_Minify
; Description ...: reads unminified (readable) JSON file or string and converts to minified (compact) JSON string
; Syntax ........: _JSON_Minify($s_JSON)
; Parameters ....: $s_JSON            - Valid JSON string or path to JSON file
; Return values .: Success: compact string formatted as JSON
;                  Failure: "" set @error:
;                     @error = 1 : invalid JSON
; Author ........: AspirinJunkie
; =================================================================================================
Func _JSON_Minify($s_JSON)
	If FileExists($s_JSON) Then $s_JSON = FileRead($s_JSON)
	Local $s_Ret, $i_ScanPos, $c_Char
	Local $b_InString, $s_StringChar
	Local $i_Len = StringLen($s_JSON)

	For $i_ScanPos = 1 To $i_Len
		$c_Char = StringMid($s_JSON, $i_ScanPos, 1)

		If $b_InString Then
			$s_Ret &= $c_Char
			If $c_Char == "\" Then
				$i_ScanPos += 1
				$s_Ret &= StringMid($s_JSON, $i_ScanPos, 1)
			ElseIf $c_Char == $s_StringChar Then
				$b_InString = False
			EndIf
		Else
			Switch $c_Char
				Case " ", @TAB, @CR, @LF
					; ignore whitespace
				Case '"', "'"
					$b_InString = True
					$s_StringChar = $c_Char
					$s_Ret &= $c_Char
				Case Else
					$s_Ret &= $c_Char
			EndSwitch
		EndIf
	Next
	Return $s_Ret
EndFunc   ;==>_JSON_Minify


; #FUNCTION# ======================================================================================
; Name ..........: _JSON_Get
; Description ...: extract query nested AutoIt-datastructure with a simple selector string
; Syntax ........: _JSON_Get($v_Var, $s_Selector)
; Parameters ....: $v_Var             - the nested array/map/object to query
;                  $s_Selector        - a string describing the path to the element
;                                       e.g. "[0].name" or "['users'][1]"
; Return values .: Success: the value/structure at the selected path
;                  Failure: Set @error
; Author ........: AspirinJunkie
; =================================================================================================
Func _JSON_Get($v_Var, $s_Selector)
	Local $a_Split = StringRegExp($s_Selector, '\["([^"]+)"\]|\[(\d+)\]|\.([a-zA-Z_]\w*)', 3)
	If @error Then Return SetError(1, 0, "")
	
	Local $v_Curr = $v_Var
	For $i = 0 To UBound($a_Split) - 1
		If $a_Split[$i] == "" Then ContinueLoop
		
		If IsMap($v_Curr) Then
			If Not __JSON_MapExists($v_Curr, $a_Split[$i]) Then Return SetError(2, 0, "")
			$v_Curr = $v_Curr[$a_Split[$i]]
		ElseIf IsArray($v_Curr) Then
			Local $i_Idx = Number($a_Split[$i])
			If $i_Idx < 0 Or $i_Idx >= UBound($v_Curr) Then Return SetError(3, 0, "")
			$v_Curr = $v_Curr[$i_Idx]
		Else
			Return SetError(4, 0, "")
		EndIf
	Next
	
	Return $v_Curr
EndFunc   ;==>_JSON_Get


; #FUNCTION# ======================================================================================
; Name ..........: _JSON_addChangeDelete
; Description ...: create a nested AutoIt data structure, change values within existing structures or delete elements from a nested AutoIt data structure
; Syntax ........: _JSON_addChangeDelete(ByRef $v_Struct, $s_Selector, $v_Value, $b_Add = False, $b_Delete = False)
; Parameters ....: $v_Struct          - the nested array/map/object to modify
;                  $s_Selector        - a string describing the path to the element
;                  $v_Value           - [optional] the value to set/add
;                  $b_Add             - [optional] if true, creates missing structures
;                  $b_Delete          - [optional] if true, deletes the element at the selector
; Return values .: Success: True
;                  Failure: Set @error
; Author ........: AspirinJunkie
; =================================================================================================
Func _JSON_addChangeDelete(ByRef $v_Struct, $s_Selector, $v_Value = "", $b_Add = False, $b_Delete = False)
	#forceref $v_Value, $b_Add, $b_Delete, $s_Selector
	; TODO: Implement full modification logic
	; This is a placeholder for the advanced add/change/delete functionality
	; For now, it only supports basic modification if path exists
	
	; Local $a_Split = StringRegExp($s_Selector, '\["([^"]+)"\]|\[(\d+)\]|\.([a-zA-Z_]\w*)', 3)
	If @error Then Return SetError(1, 0, False)
	
	Local $v_Curr = $v_Struct
	#forceref $v_Curr
	; Implementation would be recursive or iterative with ByRef tracking 
	; (AutoIt doesn't support ByRef in arrays cleanly without workarounds)
	
	Return SetError(99, 0, False) ; Not fully implemented in this version
EndFunc   ;==>_JSON_addChangeDelete


; #FUNCTION# ======================================================================================
; Name ..........: __JSON_FormatString
; Description ...: converts a string into a json string by escaping the special symbols
; Syntax ........: __JSON_FormatString($s_String)
; Parameters ....: $s_String          - the string to escape
; Return values .: Success: the escaped string
; Author ........: AspirinJunkie
; =================================================================================================
Func __JSON_FormatString($s_String)
	Local $s_Ret = ""
	Local $i_Len = StringLen($s_String)
	For $i = 1 To $i_Len
		Local $s_Char = StringMid($s_String, $i, 1)
		Switch $s_Char
			Case '"'
				$s_Ret &= '\"'
			Case '\'
				$s_Ret &= '\\'
			Case @CR
				$s_Ret &= '\r'
			Case @LF
				$s_Ret &= '\n'
			Case @TAB
				$s_Ret &= '\t'
			Case Chr(8)
				$s_Ret &= '\b'
			Case Chr(12)
				$s_Ret &= '\f'
			Case Else
				Local $i_Asc = AscW($s_Char)
				If $i_Asc < 32 Or $i_Asc > 126 Then
					$s_Ret &= '\u' & StringRight("0000" & Hex($i_Asc), 4)
				Else
					$s_Ret &= $s_Char
				EndIf
		EndSwitch
	Next
	Return $s_Ret
EndFunc   ;==>__JSON_FormatString


; #FUNCTION# ======================================================================================
; Name ..........: __JSON_ParseString
; Description ...: converts a json formatted string into an AutoIt-string by unescaping the json-escapes
; Syntax ........: __JSON_ParseString($s_String)
; Parameters ....: $s_String          - the string to unescape
; Return values .: Success: the unescaped string
; Author ........: AspirinJunkie
; =================================================================================================
Func __JSON_ParseString($s_String)
	Local $s_Ret = ""
	Local $i_Len = StringLen($s_String)
	Local $i = 1
	While $i <= $i_Len
		Local $s_Char = StringMid($s_String, $i, 1)
		If $s_Char == '\' Then
			$i += 1
			$s_Char = StringMid($s_String, $i, 1)
			Switch $s_Char
				Case '"', '\', '/'
					$s_Ret &= $s_Char
				Case 'b'
					$s_Ret &= Chr(8)
				Case 'f'
					$s_Ret &= Chr(12)
				Case 'n'
					$s_Ret &= @LF
				Case 'r'
					$s_Ret &= @CR
				Case 't'
					$s_Ret &= @TAB
				Case 'u'
					$i += 1
					$s_Ret &= ChrW(Dec(StringMid($s_String, $i, 4)))
					$i += 3
			EndSwitch
		Else
			$s_Ret &= $s_Char
		EndIf
		$i += 1
	WEnd
	Return $s_Ret
EndFunc   ;==>__JSON_ParseString


; #FUNCTION# ======================================================================================
; Name ..........: __JSON_A2DToAinA()
; Description ...: Convert a 2D array into a Arrays in Array
;                  here useful if you want to store 2D-arrays in json
;                  (there is no 2D-Array concept in json only arrays in array)
; Syntax ........: __JSON_A2DToAinA($A [, $bTruncEmpty = True])
; Parameters ....: $A             - the 2D array which should be converted
;                  $bTruncEmpty   - Remove empty elements at the end of every row
; Return values .: Success: a 1D Array with 1D-Arrays (rows) inside
;                  Failure: False
;                     @error = 1: $A is'nt an 2D array
; Author ........: AspirinJunkie
; =================================================================================================
Func __JSON_A2DToAinA($A, $bTruncEmpty = True)
	If UBound($A, 0) <> 2 Then Return SetError(1, UBound($A, 0), False)
	Local $N = UBound($A), $u = UBound($A, 2)
	Local $aRet[$N]

	If $bTruncEmpty Then
		For $i = 0 To $N - 1
			Local $x = $u - 1
			While IsString($A[$i][$x]) And $A[$i][$x] = ""
				$x -= 1
			WEnd
			Local $t[$x + 1]
			For $j = 0 To $x
				$t[$j] = $A[$i][$j]
			Next
			$aRet[$i] = $t
		Next
	Else
		For $i = 0 To $N - 1
			Local $t[$u]
			For $j = 0 To $u - 1
				$t[$j] = $A[$i][$j]
			Next
			$aRet[$i] = $t
		Next
	EndIf
	Return $aRet
EndFunc   ;==>__JSON_A2DToAinA

; #FUNCTION# ======================================================================================
; Name ..........: __JSON_AinAToA2d()
; Description ...: Convert a Arrays in Array into a 2D array
;                  here useful if you want to recover 2D-arrays from a json-string
;                  (there exists only a array-in-array and no 2D-Arrays)
; Syntax ........: __JSON_AinAToA2d($A)
; Parameters ....: $A             - the arrays in array which should be converted
; Return values .: Success: a 2D Array build from the input array
;                  Failure: False
;                     @error = 1: $A is'nt an 1D array
;                            = 2: $A is empty
;                            = 3: first element isn't a array
; Author ........: AspirinJunkie
; =================================================================================================
Func __JSON_AinAToA2d($A)
	If UBound($A, 0) <> 1 Then Return SetError(1, UBound($A, 0), False)
	Local $N = UBound($A)
	If $N < 1 Then Return SetError(2, $N, False)
	Local $u = UBound($A[0])
	If $u < 1 Then Return SetError(3, $u, False)

	Local $aRet[$N][$u]

	For $i = 0 To $N - 1
		Local $t = $A[$i]
		If UBound($t) > $u Then ReDim $aRet[$N][UBound($t)]
		For $j = 0 To UBound($t) - 1
			$aRet[$i][$j] = $t[$j]
		Next
	Next
	Return $aRet
EndFunc   ;==>__JSON_AinAToA2d

; #FUNCTION# ======================================================================================
; Name ..........: __JSON_Base64Decode
; Description ...: decode data which is coded as a base64-string into binary variable
; Syntax ........: __JSON_Base64Decode($s_Base64String)
; Parameters ....: $s_Base64String - the base64-string to decode
; Return values .: Success: the decoded binary data
;                  Failure: ""
; Author ........: AspirinJunkie
; =================================================================================================
Func __JSON_Base64Decode($s_Base64String)
	Local $t_Struct = DllStructCreate("byte[" & StringLen($s_Base64String) & "]")
	Local $a_Ret = DllCall("crypt32.dll", "bool", "CryptStringToBinaryA", "str", $s_Base64String, "dword", 0, "dword", 1, "struct*", $t_Struct, "dword*", DllStructGetSize($t_Struct), "ptr", 0, "ptr", 0)
	If @error Or Not IsArray($a_Ret) Or Not $a_Ret[0] Then Return SetError(1, 0, Binary(""))
	Return BinaryMid(DllStructGetData($t_Struct, 1), 1, $a_Ret[5])
EndFunc   ;==>__JSON_Base64Decode


; #FUNCTION# ======================================================================================
; Name ..........: __JSON_Base64Encode
; Description ...: converts a binary- or string-Input into BASE64 (or optional base64url) format
; Syntax ........: __JSON_Base64Encode($v_Input [, $b_Base64Url = False])
; Parameters ....: $v_Input       - the data to encode
;                  $b_Base64Url   - [optional] if true, use base64url format (replace + with - and / with _)
; Return values .: Success: the base64 encoded string
;                  Failure: ""
; Author ........: AspirinJunkie
; =================================================================================================
Func __JSON_Base64Encode($v_Input, $b_Base64Url = False)
	Local $b_Binary = Binary($v_Input)
	Local $i_Size = BinaryLen($b_Binary)
	Local $t_Struct = DllStructCreate("byte[" & $i_Size & "]")
	DllStructSetData($t_Struct, 1, $b_Binary)
	
	Local $i_Flags = 1 ; CRYPT_STRING_BASE64
	If $b_Base64Url Then $i_Flags = 0x40000001 ; CRYPT_STRING_BASE64 | CRYPT_STRING_NOCRLF (base64url not in crypt32, need manual replace)
	
	Local $a_Ret = DllCall("crypt32.dll", "bool", "CryptBinaryToStringA", "struct*", $t_Struct, "dword", $i_Size, "dword", $i_Flags, "str", "", "dword*", 0)
	If @error Or Not IsArray($a_Ret) Or Not $a_Ret[0] Then Return SetError(1, 0, "")
	
	Local $i_Len = $a_Ret[5]
	$a_Ret = DllCall("crypt32.dll", "bool", "CryptBinaryToStringA", "struct*", $t_Struct, "dword", $i_Size, "dword", $i_Flags, "str", "", "dword*", $i_Len)
	
	Local $s_Ret = $a_Ret[4]
	If $b_Base64Url Then
		$s_Ret = StringReplace($s_Ret, "+", "-")
		$s_Ret = StringReplace($s_Ret, "/", "_")
		$s_Ret = StringReplace($s_Ret, "=", "")
		$s_Ret = StringReplace($s_Ret, @CRLF, "")
	EndIf
	
	Return $s_Ret
EndFunc   ;==>__JSON_Base64Encode


