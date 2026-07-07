#include-once

; ===============================================================================================================================
; @file        integration_test_warnings.au3
; @brief       AutoIt fixture containing representative warning patterns for integration checks.
; @details     Part of AutoIt_Static_Analyzer. The header describes the file boundary for generated documentation and
;              for quick maintenance review before reading implementation code.
; ===============================================================================================================================
Func TestByRef(ByRef $a)
    $a = 10
EndFunc

Func Main()
    Local $var = 1
    Local $var = 2 ; Duplicate declaration warning (-w 3)
    
    Dim $dimVar = 5 ; Deprecated Dim usage warning (-w 6)
    
    Local Const $c = 5
    TestByRef($c) ; Passing Const on ByRef warning (-w 7)
    
    TestByRef(5) ; Passing literal on ByRef warning (-w 7)
    
    Local $unused ; Unused local variable warning (-w 5)
EndFunc
