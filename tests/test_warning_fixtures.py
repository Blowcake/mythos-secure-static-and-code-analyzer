"""@file test_warning_fixtures.py
@brief Fixture-driven regression tests for analyzer warning behavior and false-positive guards.
@details Part of AutoIt_Static_Analyzer. This header is intentionally concise so Doxygen output and future code reviews expose the module boundary before implementation details.
"""
import os
import re
import shutil
import subprocess
import sys
import textwrap
import unittest
import uuid
import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANALYZER = PROJECT_ROOT / "src" / "autoit_static_analyzer" / "autoit_windows_x64_scoping_analyzer.py"
_std_check = Path(r"C:\Program Files (x86)\AutoIt3\Au3Check_Original.exe")
if not _std_check.exists():
    _std_check = Path(r"C:\Program Files (x86)\AutoIt3\Au3Check.exe")
AU3CHECK = Path(os.environ.get("AU3CHECK_EXE", str(_std_check)))
TEST_TMP_ROOT = PROJECT_ROOT / ".tmp" / "tests"


def load_analyzer_module():
    spec = importlib.util.spec_from_file_location("autoit_windows_x64_scoping_analyzer_under_test", ANALYZER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WorkspaceTempDir:
    def __init__(self, prefix):
        self.path = TEST_TMP_ROOT / f"{prefix}{uuid.uuid4().hex}"

    def __enter__(self):
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.path.mkdir(parents=True, exist_ok=False)
        return str(self.path)

    def __exit__(self, exc_type, exc, tb):
        shutil.rmtree(self.path, ignore_errors=True)


def make_temp_dir(prefix):
    return WorkspaceTempDir(prefix)


ANALYZER_ONLY_FIXTURES = [
    {
        "name": "block_scoping_bug",
        "warning": "Block Scoping Bug",
        "variable": "$x",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($flag)
                If $flag Then
                    Local $x = 1
                EndIf
                Return $x
            EndFunc
        """,
    },
    {
        "name": "array_dimension_mismatch",
        "warning": "Array Dimension Mismatch",
        "variable": "$a",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local $a[1]
                Return $a[0][0]
            EndFunc
        """,
    },
    {
        "name": "array_assignment_rhs_uninitialized_still_warns",
        "warning": "Potential Uninitialized Use",
        "variable": "$value",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local $out[1]
                Local $value
                Select
                    Case @AutoItX64
                        $value = 1
                EndSelect
                $out[0] = $value
                Return $out[0]
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "value_set_switch_missing_case_still_warns",
        "warning": "Potential Uninitialized Use",
        "variable": "$hue",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($a, $b, $c, $gray)
                Local $hue
                Local $max = $a
                If $max < $b Then $max = $b
                If $max < $c Then $max = $c
                If $gray Then
                    $hue = 0
                Else
                    Switch $max
                        Case $a
                            $hue = 1
                        Case $b
                            $hue = 2
                    EndSwitch
                EndIf
                Return $hue
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "implicit_empty_string_segment_is_classified",
        "warning": "Implicit Empty String Use",
        "variable": "$suffix",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($flag)
                Local $suffix
                If $flag Then $suffix = ", enabled"
                Return "status" & $suffix
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "independent_status_case_does_not_initialize_error_value",
        "warning": "Potential Uninitialized Use",
        "variable": "$err",
        "source": """
            Opt("MustDeclareVars", 1)

            Global Const $STATUS_BAD = 2

            Func Probe()
                Local $err
                If @error Then $err = @error
                Local $status = $STATUS_BAD
                Switch $status
                    Case $STATUS_BAD
                        Return $err
                EndSwitch
                Return 0
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "duplicate_switch_case_value",
        "warning": "Duplicate Case Value",
        "variable": "2",
        "risk": "Duplicate Switch Case values are unreachable because AutoIt does not fall through.",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($status)
                Switch $status
                    Case 1, 2
                        Return "low"
                    Case 2
                        Return "duplicate"
                    Case Else
                        Return "other"
                EndSwitch
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "array_subscript_out_of_bounds",
        "warning": "Array Subscript Out of Bounds",
        "variable": "$a",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local $a[1]
                Return $a[1]
            EndFunc
        """,
    },
    {
        "name": "unsafe_return_dereference",
        "warning": "Unsafe Return Dereference",
        "variable": "$a",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Factory()
                Return 0
            EndFunc

            Func Probe()
                Local $a = Factory()
                Return $a[0]
            EndFunc
        """,
    },
    {
        "name": "overwritten_error_check",
        "warning": "Overwritten @error Check",
        "variable": "@error",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local $a = DllCall("kernel32.dll", "uint", "GetTickCount")
                FileExists(@ScriptFullPath)
                If @error Then Return 0
                Return $a[0]
            EndFunc
        """,
    },
    {
        "name": "objcreate_member_access_without_handler",
        "warning": "Unsafe Object Dereference",
        "variable": "$odictionary",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local $oDictionary = ObjCreate("Scripting.Dictionary")
                Return $oDictionary.Count
            EndFunc
        """,
        "experimental": True,
    },
]


ANALYZER_CLEAN_FIXTURES = [
    {
        "name": "block_scoping_full_if_else_is_promoted",
        "forbidden_warning": "Block Scoping Bug",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($flag)
                Local $x
                If $flag Then
                    $x = 1
                Else
                    $x = 2
                EndIf
                Return $x
            EndFunc
        """,
    },
    {
        "name": "array_dimensions_match",
        "forbidden_warning": "Array Dimension Mismatch",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local $a[1][1]
                Return $a[0][0]
            EndFunc
        """,
    },
    {
        "name": "array_subscript_in_bounds",
        "forbidden_warning": "Array Subscript Out of Bounds",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local $a[1]
                Return $a[0]
            EndFunc
        """,
    },
    {
        "name": "assignment_comment_dollar_identifier_is_ignored",
        "forbidden_warning": "Undeclared Variable",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local $value = 1 ; $COMMENT_ONLY_CONSTANT
                Return $value
            EndFunc
        """,
    },
    {
        "name": "function_default_string_with_parenthesis_keeps_later_params",
        "forbidden_warning": "Undeclared Variable",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($title = "", $filter = "All files (*.*)", $initial = ".", $flags = 0)
                #forceref $title
                If $flags Then Return $initial
                Return $filter
            EndFunc
        """,
    },
    {
        "name": "local_enum_members_are_visible_declarations",
        "forbidden_warning": "Undeclared Variable",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local Enum $eFirst = 0, $eSecond, $eThird
                Local $values[1][3] = [[1, 2, 3]]
                Return $values[0][$eSecond]
            EndFunc
        """,
    },
    {
        "name": "unsafe_return_dereference_guarded_by_isarray",
        "forbidden_warning": "Unsafe Return Dereference",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Factory()
                Return 0
            EndFunc

            Func Probe()
                Local $a = Factory()
                If Not IsArray($a) Then Return 0
                Return $a[0]
            EndFunc
        """,
    },
    {
        "name": "overwritten_error_check_ignores_stale_long_window",
        "forbidden_warning": "Overwritten @error Check",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local $a = DllCall("kernel32.dll", "uint", "GetTickCount")
                Local $x = 1
                FileExists(@ScriptFullPath)
                If @error Then Return 0
                Return $a[0] + $x
            EndFunc
        """,
    },
    {
        "name": "overwritten_error_check_ignores_nested_utility_call",
        "forbidden_warning": "Overwritten @error Check",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local $a = DllCall("kernel32.dll", "uint", "GetEnvironmentVariableW", "wstr", "PATH", "wstr", "", "dword", StringLen("PATH"))
                If @error Then Return 0
                Return $a[0]
            EndFunc
        """,
    },
    {
        "name": "overwritten_error_check_ignores_struct_helper_sequence",
        "forbidden_warning": "Overwritten @error Check",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local $t = DllStructCreate("int value")
                DllStructGetPtr($t)
                If @error Then Return 0
                Return DllStructGetData($t, "value")
            EndFunc
        """,
    },
    {
        "name": "forceref_after_return_is_not_unreachable_code",
        "forbidden_warning": "Unreachable Code",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($unused)
                Return 1
                #forceref $unused
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "if_else_branch_assignments_initialize_value",
        "forbidden_warning": "Potential Uninitialized Use",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($flag)
                Local $value
                If $flag Then
                    $value = 1
                Else
                    $value = 2
                EndIf
                Return $value + 1
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "outer_or_guard_with_exhaustive_single_line_assignments",
        "forbidden_warning": "Potential Uninitialized Use",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($kind, $value)
                If $kind = "d" Or $kind = "w" Or $kind = "a" Then
                    Local $number
                    If $kind = "d" Then $number = $value
                    If $kind = "w" Then $number = $value * 7
                    If $kind = "a" Then $number = $value + 10
                    Return $number + 1
                EndIf
                Return 0
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "select_case_assignment_is_visible_later_in_same_case",
        "forbidden_warning": "Potential Uninitialized Use",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($mode, $end, $start)
                Local $diff
                Select
                    Case $mode = "m"
                        $diff = $end - $start
                        Local $months = $diff * 12
                        Return $months
                    Case Else
                        Return 0
                EndSelect
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "case_else_inner_if_else_initializes_return_value",
        "forbidden_warning": "Potential Uninitialized Use",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($weekday)
                Select
                    Case $weekday < 1
                        Return 0
                    Case Else
                        Local $last
                        If $weekday = 1 Then
                            $last = 7
                        Else
                            $last = $weekday - 1
                        EndIf
                        Return $last
                EndSelect
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "dllcall_result_parameter_index_is_valid",
        "forbidden_warning": "DllCall Return Index Mismatch",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local $ret = DllCall("kernel32.dll", "bool", "QueryPerformanceCounter", "int64*", 0)
                If @error Then Return 0
                Return $ret[1]
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "filefindnextfile_extended_is_primary_status",
        "forbidden_warning": "Overwritten @extended Check",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($handle)
                StringReplace("a\\b", "\\", "")
                Local $name = FileFindNextFile($handle, 1)
                If @error Then Return ""
                Local $attributes = @extended
                Return $name & $attributes
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "setextended_return_function_is_primary_status",
        "forbidden_warning": "Overwritten @extended Check",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Palette()
                Return SetExtended(4, 1)
            EndFunc

            Func Probe()
                Local $previous = StringReplace("a b", " ", "")
                #forceref $previous
                Local $value = Palette()
                If @extended <> 4 Then Return 0
                Return $value
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "seterror_return_in_error_guard_does_not_overwrite_success_extended",
        "forbidden_warning": "Overwritten @extended Check",
        "source": """
            Opt("MustDeclareVars", 1)

            Func ParseValue()
                Return SetExtended(4, "ok")
            EndFunc

            Func Probe()
                Local $value = ParseValue()
                If @error Then Return SetError(1, @error, "")
                Local $offset = @extended
                Return $value & $offset
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "seterror_payload_sentinel_guard_allows_later_use",
        "forbidden_warning": "Unchecked SetError Return",
        "source": """
            Opt("MustDeclareVars", 1)

            Func LookupCLSID($ext)
                If $ext = "" Then Return SetError(1, 0, "")
                Return "{ok}"
            EndFunc

            Func SaveWithCLSID($clsid)
                Return $clsid <> ""
            EndFunc

            Func Probe($ext)
                Local $clsid = LookupCLSID($ext)
                If $clsid = "" Then Return SetError(1, 0, False)
                Return SaveWithCLSID($clsid)
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "inline_normal_return_prevents_seterror_only_classification",
        "forbidden_warning": "Unchecked SetError Return",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Lookup($needle)
                If $needle = "ok" Then Return "value"
                Return SetError(1, 0, "")
            EndFunc

            Func Probe($needle)
                Local $value = Lookup($needle)
                If $value = "" Then Return 0
                Return StringLen($value)
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "calls_inside_error_guard_do_not_overwrite_success_extended",
        "forbidden_warning": "Overwritten @extended Check",
        "source": """
            Opt("MustDeclareVars", 1)

            Func QueryData()
                Return SetExtended(8, True)
            EndFunc

            Func LogFailure()
                ConsoleWrite("failed")
            EndFunc

            Func Probe()
                Local $ok = QueryData()
                If @error Then
                    LogFailure()
                    Return 0
                EndIf
                Local $bytes = @extended
                Return $ok And $bytes
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "byref_parameter_can_be_polymorphic_array_dimension",
        "forbidden_warning": "Array Dimension Mismatch",
        "source": """
            Opt("MustDeclareVars", 1)

            Func AddToList(ByRef $aList, $twoDim)
                If $twoDim Then
                    $aList[0][0] += 1
                Else
                    $aList[0] += 1
                EndIf
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "dllstruct_dot_access_is_not_com_dereference",
        "forbidden_warning": "Unsafe Object Dereference",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local $tData = DllStructCreate("int Count")
                $tData.Count = 3
                Return $tData.Count
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "uppercase_string_constant_prefix_is_not_numeric_coercion",
        "forbidden_warning": "Potential Numeric Coercion",
        "source": """
            Opt("MustDeclareVars", 1)
            Global Const $STR_STRIPLEADING = 1
            Global Const $STR_STRIPTRAILING = 2

            Func Probe()
                Return BitOR($STR_STRIPLEADING, $STR_STRIPTRAILING)
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "security_constant_prefix_is_not_numeric_coercion",
        "forbidden_warning": "Potential Numeric Coercion",
        "source": """
            Opt("MustDeclareVars", 1)
            Global Const $SE_PRIVILEGE_ENABLED = 2

            Func Probe($iAttributes)
                Return BitOR($iAttributes, $SE_PRIVILEGE_ENABLED)
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "numeric_hex_const_with_string_name_is_not_numeric_coercion",
        "forbidden_warning": "Potential Numeric Coercion",
        "source": """
            Opt("MustDeclareVars", 1)
            Global Const $HDF_STRING = 0x4000
            Global Const $HDF_BITMAP = 0x2000

            Func Probe()
                Return BitOR($HDF_STRING, $HDF_BITMAP)
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "fileopen_failure_return_with_comment_does_not_leak_handle",
        "forbidden_warning": "Handle Leak on Return",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($path)
                Local $handle = FileOpen($path, 0)
                If $handle = -1 Then Return 0 ; return failure, no handle exists
                FileClose($handle)
                Return 1
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "stringsplit_index_one_is_always_available",
        "forbidden_warning": "Unchecked Array Result Index",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($path)
                Local $parts = StringSplit($path, "\\")
                Return $parts[1]
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "nested_map_comparison_is_not_registered_as_map_assignment",
        "forbidden_warning": "Unchecked Map Key",
        "source": """
            Opt("MustDeclareVars", 1)

            Func GetResponse()
                Local $child[]
                $child["b"] = 1
                Local $response[]
                $response["a"] = $child
                $response["c"] = 2
                Return $response
            EndFunc

            Func Probe()
                Local $response = GetResponse()
                If Not IsMap($response) Then Return 0
                If $response["a"]["b"] == 1 Then Return $response["c"]
                Return 0
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "loop_assignment_initializes_later_read_in_same_loop",
        "forbidden_warning": "Potential Uninitialized Use",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($flag)
                Local $value
                If $flag Then
                    $value = 1
                EndIf
                For $i = 1 To 2
                    $value = $i
                    If $value > 1 Then Return $value
                Next
                Return 0
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "byref_out_parameter_initializes_later_read_in_loop",
        "forbidden_warning": "Potential Uninitialized Use",
        "source": """
            Opt("MustDeclareVars", 1)

            Func ReadText($index, ByRef $text)
                $text = "item" & $index
                Return 1
            EndFunc

            Func Probe()
                Local $text
                For $i = 1 To 2
                    ReadText($i, $text)
                    If StringLen($text) > 0 Then Return $text
                Next
                Return ""
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "loop_assignment_initializes_array_assignment_rhs",
        "forbidden_warning": "Potential Uninitialized Use",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($count)
                Local $out[2]
                Local $value
                For $i = 0 To $count - 1
                    $value = 0
                    If $i > 0 Then
                    Else
                        $value = $i + 1
                    EndIf
                    $out[$i] = $value
                Next
                Return $out[0]
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "outer_loop_assignment_survives_nested_loop_and_inline_if",
        "forbidden_warning": "Potential Uninitialized Use",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($cols, $rows)
                Local $out[4]
                Local $maxValue, $len
                If $cols < 0 Then
                    Return 0
                Else
                    For $col = 0 To $cols - 1
                        $maxValue = 0
                        If $col > 10 Then
                        Else
                            $maxValue = $col + 1
                        EndIf
                        For $row = 0 To $rows - 1
                            $len = $row
                            If $len > $maxValue Then $maxValue = $len
                        Next
                        If $maxValue < 5 Then $maxValue = 5
                        If $maxValue > 30 Then $maxValue = 30
                        $out[$col] = $maxValue
                    Next
                EndIf
                Return $out[0]
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "value_set_switch_cases_initialize_outer_branch",
        "forbidden_warning": "Potential Uninitialized Use",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($a, $b, $c, $gray)
                Local $hue
                Local $max = $a
                If $max < $b Then $max = $b
                If $max < $c Then $max = $c
                If $gray Then
                    $hue = 0
                Else
                    Switch $max
                        Case $a
                            $hue = 1
                        Case $b
                            $hue = 2
                        Case $c
                            $hue = 3
                    EndSwitch
                EndIf
                Return $hue
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "status_dependency_switch_case_initializes_error_value",
        "forbidden_warning": "Potential Uninitialized Use",
        "source": """
            Opt("MustDeclareVars", 1)

            Global Const $STATUS_OK = 0
            Global Const $STATUS_BAD = 2

            Func ErrorStatus($err)
                Switch $err
                    Case -1
                        Return $STATUS_BAD
                    Case Else
                        Return $STATUS_OK
                EndSwitch
            EndFunc

            Func Probe()
                Local $err
                Local $status = $STATUS_OK
                If @error Then
                    $err = @error
                    If ErrorStatus($err) Then
                        $status = ErrorStatus($err)
                    EndIf
                EndIf
                Switch $status
                    Case $STATUS_BAD
                        Return $err
                EndSwitch
                Return 0
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "distinct_switch_case_values_do_not_warn",
        "forbidden_warning": "Duplicate Case Value",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($status)
                Switch $status
                    Case 1, 2
                        Return "low"
                    Case 3
                        Return "high"
                    Case Else
                        Return "other"
                EndSwitch
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "read_assignment_is_not_dead_store",
        "forbidden_warning": "Dead Store",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local $result = 0
                $result = 1
                $result = 2
                Return $result
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "global_typecheck_does_not_create_local_forward_declaration",
        "forbidden_warning": "Reference Before Declaration",
        "source": """
            Opt("MustDeclareVars", 1)

            Global $g_handler

            Func Probe()
                If Not IsObj($g_handler) Then Return 0
                $g_handler = ObjCreate("Scripting.Dictionary")
                If IsObj($g_handler) Then Return 1
                Return 0
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "complementary_boolean_guards_initialize_variable",
        "forbidden_warning": "Potential Uninitialized Use",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($force)
                Local $value
                If Not $force Then $value = "existing"
                If $force Or @error Then
                    $value = "created"
                    If $value = "" Then Return SetError(1, 0, "")
                EndIf
                Return StringLen($value)
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "self_concat_accumulator_initializes_string",
        "forbidden_warning": "Potential Uninitialized Use",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($aItems)
                Local $text
                For $i = 0 To UBound($aItems) - 1
                    $text = $text & $aItems[$i]
                Next
                Return $text
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "concat_assignment_accumulator_initializes_string",
        "forbidden_warning": "Potential Uninitialized Use",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($aItems)
                Local $text
                For $i = 0 To UBound($aItems) - 1
                    $text &= $aItems[$i]
                Next
                Return $text
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "terminating_select_branch_does_not_block_full_assignment",
        "forbidden_warning": "Potential Uninitialized Use",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($percent)
                Local $numerator, $denominator
                Select
                    Case Not ($percent = 100 Or ($percent >= 200 And $percent < 6400))
                        Return SetError(1, 0, 0)
                    Case $percent >= 100
                        $numerator = 10000
                        $denominator = 10000 / ($percent / 100)
                    Case Else
                        $numerator = 10000 * ($percent / 100)
                        $denominator = 10000
                EndSelect
                Return $numerator + $denominator
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "fileopen_failure_return_does_not_leak_handle",
        "forbidden_warning": "Handle Leak on Return",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($path)
                Local $handle = FileOpen($path, 0)
                If $handle = -1 Then Return 0
                FileClose($handle)
                Return 1
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "fileopen_multiline_failure_return_does_not_leak_handle",
        "forbidden_warning": "Handle Leak on Return",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($path)
                Local $handle = FileOpen($path, 0)
                If $handle == -1 Then
                    ConsoleWrite("open failed")
                    Return 0
                EndIf
                FileClose($handle)
                Return 1
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "fileopen_less_than_zero_failure_return_does_not_leak_handle",
        "forbidden_warning": "Handle Leak on Return",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($path)
                Local $handle = FileOpen($path, 0)
                If $handle < 0 Then Return SetError(-1, 0, 0)
                FileClose($handle)
                Return 1
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "fileopen_aterror_immediate_failure_return_does_not_leak_handle",
        "forbidden_warning": "Handle Leak on Return",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($path)
                Local $handle = FileOpen($path, 0)
                If @error Then Return SetError(@error, 0, 0)
                FileClose($handle)
                Return 1
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "redim_parameter_dimension_normalization_is_allowed",
        "forbidden_warning": "ReDim Dimension Change",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe(ByRef $a)
                ReDim $a[2][2]
                Return UBound($a, 2)
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "branch_polymorphic_array_builder_redim_is_allowed",
        "forbidden_warning": "ReDim Dimension Change",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($columns, $count)
                If $columns = 1 Then
                    Local $files[1], $dirs[1]
                    $files[0] = 0
                    $count += $files[0]
                Else
                    Local $files[1][$columns], $dirs[1][$columns]
                    $files[0][0] = 0
                    $count += $files[0][0]
                EndIf

                Local $index = 1
                If $columns = 1 Then
                    If UBound($dirs) < $index + 1 Then ReDim $dirs[$index * 2]
                    $dirs[$index] = "name"
                Else
                    If UBound($dirs) < $index + 1 Then ReDim $dirs[$index * 2][$columns]
                    $dirs[$index][0] = "name"
                EndIf
                Return $count
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "stringsplit_count_check_allows_payload_index",
        "forbidden_warning": "Unchecked Array Result Index",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($text)
                Local $parts = StringSplit($text, ",")
                If $parts[0] < 1 Then Return ""
                Return $parts[1]
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "bit_operation_flag_name_is_not_string_coercion",
        "forbidden_warning": "Potential Numeric Coercion",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($security_flag_ignore_unknown_ca)
                Return BitOR($security_flag_ignore_unknown_ca, 1)
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "same_extended_status_function_replaces_prior_extended",
        "forbidden_warning": "Overwritten @extended Check",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local $first = StringReplace("abc", "a", "b")
                Local $second = StringReplace($first, "b", "c")
                If @extended Then Return $second
                Return $first
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "seterror_passthrough_value_return_is_allowed",
        "forbidden_warning": "Unchecked SetError Return",
        "source": """
            Opt("MustDeclareVars", 1)

            Func LastValue(Const $_iCallerError = @error, Const $_iCallerExtended = @extended)
                Return SetError($_iCallerError, $_iCallerExtended, 42)
            EndFunc

            Func Probe()
                Local $value = LastValue()
                Return $value + 1
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "seterror_passthrough_alias_value_return_is_allowed",
        "forbidden_warning": "Unchecked SetError Return",
        "source": """
            Opt("MustDeclareVars", 1)

            Func LastValue(Const $_iCallerError = @error, Const $_iCallerExtended = @extended)
                Local $err = $_iCallerError
                Local $ext = $_iCallerExtended
                Return SetError($err, $ext, 42)
            EndFunc

            Func Probe()
                Local $value = LastValue()
                Return $value + 1
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "seterror_error_status_value_passthrough_wrapper_is_allowed",
        "forbidden_warning": "Unchecked SetError Return",
        "source": """
            Opt("MustDeclareVars", 1)

            Func GetParts()
                Local $parts[3]
                If @error Then Return SetError(1, 0, $parts)
                $parts[1] = 4
                Return $parts
            EndFunc

            Func GetPadding()
                Local $parts = GetParts()
                Return SetError(@error, @extended, $parts[1])
            EndFunc

            Func Probe()
                Local $padding = GetPadding()
                Return 100 - ($padding * 2)
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "seterror_function_call_replaces_stale_extended_source",
        "forbidden_warning": "Overwritten @extended Check",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Navigate($url)
                Return SetError(0, 7, StringLen($url) > 0)
            EndFunc

            Func Probe()
                Local $path = StringReplace("a b", " ", "%20")
                Navigate($path)
                Local $ext = @extended
                Return $ext
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "assigned_seterror_function_replaces_stale_extended_source",
        "forbidden_warning": "Overwritten @extended Check",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Navigate($url)
                Return SetError(0, 7, StringLen($url) > 0)
            EndFunc

            Func Probe()
                Local $path = StringReplace("a b", " ", "%20")
                Local $ok = Navigate($path)
                Local $ext = @extended
                Return $ok And $ext
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "global_assignment_from_seterror_function_can_check_error_next",
        "forbidden_warning": "Unchecked SetError Return",
        "source": """
            Opt("MustDeclareVars", 1)
            Global $g_value = 0

            Func Factory()
                Return SetError(1, 0, 0)
            EndFunc

            Func Probe()
                $g_value = Factory()
                If @error Then Return 0
                Return $g_value
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "same_line_reassignment_uses_old_seterror_value_on_rhs",
        "forbidden_warning": "Unchecked SetError Return",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Search($start)
                If $start > 3 Then Return SetError(1, 0, -1)
                Return $start
            EndFunc

            Func Probe()
                Local $iStart = Search(0)
                If @error Then Return -1
                Do
                    $iStart = Search($iStart + 1)
                Until @error
                Return $iStart
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "com_error_handler_protects_objcreate_member_access",
        "forbidden_warning": "Unsafe Object Dereference",
        "source": """
            Opt("MustDeclareVars", 1)

            Func AutoErrFunc($oError)
                #forceref $oError
                Return 0
            EndFunc

            Func Probe($iCase)
                ObjEvent("AutoIt.Error", AutoErrFunc)
                Local $oDictionary = ObjCreate("Scripting.Dictionary")
                $oDictionary.CompareMode = Number(Not $iCase)
                Return @error
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "custom_mapexists_wrapper_is_a_visible_guard",
        "forbidden_warning": "Unchecked Map Key",
        "source": """
            Opt("MustDeclareVars", 1)

            Func _MapExists(ByRef $m, $key)
                Return MapExists($m, $key)
            EndFunc

            Func Probe()
                Local $m[]
                If Not _MapExists($m, "name") Then $m["name"] = "default"
                Return $m["name"]
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "dllcall_result_boolean_check_is_allowed",
        "forbidden_warning": "Array Used as Boolean",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local $aCall = DllCall("kernel32.dll", "uint", "GetTickCount")
                If $aCall Then Return $aCall[0]
                Return 0
            EndFunc
        """,
        "experimental": True,
    },
    {
        "name": "array_variable_scalarized_before_boolean_condition",
        "forbidden_warning": "Array Used as Boolean",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($text)
                Local $iIndex
                $iIndex = StringRegExp($text, "\\[(\\d+)\\]", 3)
                If IsArray($iIndex) Then
                    $iIndex = $iIndex[0]
                Else
                    $iIndex = 0
                EndIf
                If $iIndex Then Return $iIndex
                Return 0
            EndFunc
        """,
        "experimental": True,
    },
]


AU3CHECK_OVERLAP_FIXTURES = [
    {
        "name": "reference_before_declaration",
        "warning": "Reference Before Declaration",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                ConsoleWrite($x)
                Local $x = 1
            EndFunc
        """,
    },
    {
        "name": "undeclared_variable",
        "warning": "Undeclared Variable",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                ConsoleWrite($x)
            EndFunc
        """,
    },
    {
        "name": "global_scope_violation",
        "warning": "Global Scope Violation",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Global $x = 1
                ConsoleWrite($x)
            EndFunc
        """,
    },
    {
        "name": "constant_assignment_violation",
        "warning": "Constant Assignment Violation",
        "source": """
            Opt("MustDeclareVars", 1)
            Global Const $x = 1

            Func Probe()
                $x = 2
            EndFunc
        """,
    },
]


AU3CHECK_BLIND_CANDIDATE_FIXTURES = [
    {
        "name": "seterror_return_value_used_without_error_check",
        "warning": "Unchecked SetError Return",
        "variable": "$value",
        "risk": "Caller ignores @error after a function deliberately returns SetError.",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Factory()
                Return SetError(1, 0, 0)
            EndFunc

            Func Probe()
                Local $value = Factory()
                Return $value + 1
            EndFunc
        """,
    },
    {
        "name": "extended_check_after_intervening_call",
        "warning": "Overwritten @extended Check",
        "variable": "@extended",
        "risk": "@extended may describe the intervening call rather than the intended primary call.",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local $value = StringReplace("abc", "a", "z")
                StringLen($value)
                If @extended Then Return 1
                Return 0
            EndFunc
        """,
    },
    {
        "name": "ubound_dimension_assumption_on_2d_array",
        "warning": "Suspicious UBound Dimension",
        "variable": "$columns",
        "risk": "Code uses row count as if it were a column count.",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local $a[2][1]
                Local $columns = UBound($a)
                Return $a[0][$columns - 1]
            EndFunc
        """,
    },
    {
        "name": "redim_changes_array_dimension_contract",
        "warning": "ReDim Dimension Change",
        "variable": "$a",
        "risk": "ReDim changes a previously 2D array to 1D before later code assumes 2D semantics.",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($flag)
                Local $a[2][2]
                If $flag Then ReDim $a[2]
                Return UBound($a, 2)
            EndFunc
        """,
    },
    {
        "name": "stringsplit_payload_index_without_count_check",
        "warning": "Unchecked Array Result Index",
        "variable": "$parts",
        "risk": "StringSplit payload index is read without proving that the split produced that element.",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($text)
                Local $parts = StringSplit($text, ",")
                Return $parts[2]
            EndFunc
        """,
    },
    {
        "name": "stringregexp_match_index_without_match_check",
        "warning": "Unchecked Array Result Index",
        "variable": "$matches",
        "risk": "StringRegExp array index is read without proving that a match exists.",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($text)
                Local $matches = StringRegExp($text, "(\\d+)", 3)
                Return $matches[0]
            EndFunc
        """,
    },
    {
        "name": "map_key_read_without_mapexists",
        "warning": "Unchecked Map Key",
        "variable": "$m",
        "risk": "Map key is read without MapExists or a defaulting path.",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local $m[]
                $m["present"] = 1
                Return $m["missing"]
            EndFunc
        """,
    },
    {
        "name": "object_member_access_without_isobj_check",
        "warning": "Unsafe Object Dereference",
        "variable": "$o",
        "risk": "COM object return is dereferenced without IsObj or @error validation.",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local $o = ObjCreate("Scripting.Dictionary")
                Return $o.Item("missing")
            EndFunc
        """,
    },
    {
        "name": "dllcall_return_index_without_signature_check",
        "warning": "DllCall Return Index Mismatch",
        "variable": "$ret",
        "risk": "DllCall return array index is used without matching it to the declared signature.",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local $ret = DllCall("kernel32.dll", "uint", "GetTickCount")
                If @error Then Return 0
                Return $ret[2]
            EndFunc
        """,
    },
    {
        "name": "file_handle_leaked_on_early_return",
        "warning": "Handle Leak on Return",
        "variable": "$handle",
        "risk": "Opened handle is not closed on an early return path.",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($path, $fail)
                Local $handle = FileOpen($path, 0)
                If $fail Then Return 0
                FileClose($handle)
                Return 1
            EndFunc
        """,
    },
    {
        "name": "nested_loop_reuses_outer_counter",
        "warning": "Nested Loop Variable Reuse",
        "variable": "$i",
        "risk": "Inner loop reuses and mutates the outer loop counter.",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local $sum = 0
                For $i = 1 To 2
                    For $i = 1 To 2
                        $sum += $i
                    Next
                Next
                Return $sum
            EndFunc
        """,
    },
    {
        "name": "unreachable_code_after_return",
        "warning": "Unreachable Code",
        "variable": "",
        "risk": "Code after Return is syntactically accepted but can never execute.",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Return 1
                ConsoleWrite("unreachable")
            EndFunc
        """,
    },
    {
        "name": "branch_assignment_may_leave_value_uninitialized",
        "warning": "Potential Uninitialized Use",
        "variable": "$value",
        "risk": "Variable is declared but only assigned in one branch before use.",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($flag)
                Local $value
                If $flag Then $value = 1
                Return $value + 1
            EndFunc
        """,
    },
    {
        "name": "select_without_else_may_leave_value_uninitialized",
        "warning": "Potential Uninitialized Use",
        "variable": "$value",
        "risk": "Select has no Else path before the value is used.",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($mode)
                Local $value
                Select
                    Case $mode = 1
                        $value = 10
                    Case $mode = 2
                        $value = 20
                EndSelect
                Return $value
            EndFunc
        """,
    },
    {
        "name": "duplicate_select_case_without_fallthrough_leaves_value_uninitialized",
        "warning": "Potential Uninitialized Use",
        "variable": "$kind",
        "risk": "AutoIt Select does not fall through; a duplicate empty Case can bypass the later assignment.",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($value)
                Local $kind
                Select
                    Case IsString($value)
                        $kind = 1
                    Case IsArray($value)
                    Case IsArray($value)
                        $kind = 2
                    Case Else
                        $kind = 0
                EndSelect
                Return $kind
            EndFunc
        """,
    },
    {
        "name": "enum_value_collision_with_manual_constant",
        "warning": "Enum Value Collision",
        "variable": "$state_alias",
        "risk": "Manual constant reuses a value already produced by an enum group.",
        "source": """
            Opt("MustDeclareVars", 1)

            Global Enum $STATE_READY = 1, $STATE_BUSY
            Global Const $STATE_ALIAS = 1

            Func Probe()
                Return $STATE_READY = $STATE_ALIAS
            EndFunc
        """,
    },
    {
        "name": "silent_numeric_coercion_in_bit_operation",
        "warning": "Potential Numeric Coercion",
        "variable": "$text",
        "risk": "A non-numeric string is silently coerced in a numeric/bitwise operation.",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe($text)
                Return BitAND($text, 255)
            EndFunc
        """,
    },
    {
        "name": "array_used_as_boolean_condition",
        "warning": "Array Used as Boolean",
        "variable": "$a",
        "risk": "Array-valued expression is used as a Boolean condition.",
        "source": """
            Opt("MustDeclareVars", 1)

            Func Probe()
                Local $a[1]
                If $a Then Return 1
                Return 0
            EndFunc
        """,
    },
]


def normalize_source(source):
    return textwrap.dedent(source).strip() + "\n"


def run_au3check(path):
    if not AU3CHECK.exists():
        raise unittest.SkipTest(f"Au3Check.exe not found at {AU3CHECK}")
    cmd = [
        str(AU3CHECK),
        "-d",
        "-w", "1",
        "-w", "2",
        "-w", "3",
        "-w", "4",
        "-w", "5",
        "-w", "6",
        "-w", "7",
        "-q",
        str(path),
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


def assert_au3check_clean(testcase, result):
    output = (result.stdout or "") + (result.stderr or "")
    testcase.assertEqual(result.returncode, 0, output)
    testcase.assertNotRegex(output, r"(?i)\b[1-9]\d*\s+error\(s\)")
    testcase.assertNotRegex(output, r"(?i)\b[1-9]\d*\s+warning\(s\)")
    testcase.assertNotRegex(output, r"(?i):\s*(error|warning):")


def run_analyzer(path, out_dir, extra_args=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    cmd = [sys.executable, str(ANALYZER), str(path), "--out-dir", str(out_dir)]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def report_text(out_dir):
    return (out_dir / "scoping_report.md").read_text(encoding="utf-8")


class AnalyzerOnlyWarningFixtureTests(unittest.TestCase):
    def test_project_include_dirs_are_auto_discovered(self):
        with make_temp_dir("autoit_static_analyzer_auto_include_") as tmp:
            project_dir = Path(tmp) / "Project"
            source_dir = project_dir / "src"
            include_dir = project_dir / "SharedSDK" / "Include"
            source_dir.mkdir(parents=True)
            include_dir.mkdir(parents=True)
            (project_dir / "project.json").write_text("{}", encoding="utf-8")
            (include_dir / "ProjectConst.au3").write_text(
                normalize_source(
                    """
                    #include-once
                    Global Const $PROJECT_VALUE = 42
                    """
                ),
                encoding="utf-8",
                newline="\r\n",
            )
            source_path = source_dir / "main.au3"
            source_path.write_text(
                normalize_source(
                    """
                    Opt("MustDeclareVars", 1)
                    #include <ProjectConst.au3>

                    Func Probe()
                        Return $PROJECT_VALUE
                    EndFunc
                    """
                ),
                encoding="utf-8",
                newline="\r\n",
            )

            out_dir = project_dir / "analysis"
            analyzer_result = run_analyzer(source_path, out_dir)
            analyzer_output = (analyzer_result.stdout or "") + (analyzer_result.stderr or "")
            self.assertEqual(analyzer_result.returncode, 0, analyzer_output)

            preprocessed = (out_dir / "preprocessed_source.au3").read_text(encoding="utf-8")
            self.assertIn("Global Const $PROJECT_VALUE = 42", preprocessed)
            self.assertIn("Auto-discovered Include Directories", report_text(out_dir))

    def test_analyzer_only_fixtures_are_au3check_clean_and_detected(self):
        with make_temp_dir("autoit_static_analyzer_") as tmp:
            tmp_path = Path(tmp)
            for fixture in ANALYZER_ONLY_FIXTURES:
                with self.subTest(fixture=fixture["name"]):
                    case_dir = tmp_path / fixture["name"]
                    case_dir.mkdir()
                    source_path = case_dir / "main.au3"
                    source_path.write_text(normalize_source(fixture["source"]), encoding="utf-8", newline="\r\n")

                    au3check_result = run_au3check(source_path)
                    assert_au3check_clean(self, au3check_result)

                    out_dir = case_dir / "analysis"
                    extra_args = ["--enable-experimental-checks"] if fixture.get("experimental") else None
                    analyzer_result = run_analyzer(source_path, out_dir, extra_args)
                    analyzer_output = (analyzer_result.stdout or "") + (analyzer_result.stderr or "")
                    self.assertEqual(analyzer_result.returncode, 0, analyzer_output)

                    report = report_text(out_dir)
                    self.assertIn(fixture["warning"], report)
                    self.assertIn(fixture["variable"], report.lower())

    def test_dead_store_reports_written_but_never_read_value(self):
        source = """
        Func Probe()
            Local $status = 0
            $status = 1
            $status = 2
            Return 42
        EndFunc
        """
        with make_temp_dir("dead_store_") as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "main.au3"
            source_path.write_text(normalize_source(source), encoding="utf-8", newline="\r\n")
            out_dir = tmp_path / "analysis"

            res = run_analyzer(source_path, out_dir, ["--enable-experimental-checks"])
            self.assertEqual(res.returncode, 0, (res.stdout or "") + (res.stderr or ""))

            report = report_text(out_dir)
            self.assertIn("Dead Store", report)
            self.assertIn("$status", report.lower())

    def test_system_dead_store_requires_explicit_opt_in(self):
        module = load_analyzer_module()
        std_path = str(Path(module.AUTOIT_STD_INCLUDE) / "SyntheticDeadStore.au3")
        func_lines = [
            (2, "    Local $status = 0\n"),
            (3, "    $status = 1\n"),
            (4, "    Return 42\n"),
        ]
        line_mappings = [(std_path, i) for i in range(1, 5)]

        analyzer_default = module.AutoItScopingAnalyzer(experimental_checks=True)
        analyzer_default.analyze_function("Probe", "", 1, func_lines, line_mappings, {})
        self.assertNotIn("Dead Store", [w["type"] for w in analyzer_default.warnings])

        analyzer_enabled = module.AutoItScopingAnalyzer(experimental_checks=True, system_dead_stores=True)
        analyzer_enabled.analyze_function("Probe", "", 1, func_lines, line_mappings, {})
        self.assertIn("Dead Store", [w["type"] for w in analyzer_enabled.warnings])

    def test_clean_counter_fixtures_are_au3check_clean_and_not_reported(self):
        with make_temp_dir("autoit_static_analyzer_clean_") as tmp:
            tmp_path = Path(tmp)
            for fixture in ANALYZER_CLEAN_FIXTURES:
                with self.subTest(fixture=fixture["name"]):
                    case_dir = tmp_path / fixture["name"]
                    case_dir.mkdir()
                    source_path = case_dir / "main.au3"
                    source_path.write_text(normalize_source(fixture["source"]), encoding="utf-8", newline="\r\n")

                    au3check_result = run_au3check(source_path)
                    assert_au3check_clean(self, au3check_result)

                    out_dir = case_dir / "analysis"
                    extra_args = ["--enable-experimental-checks"] if fixture.get("experimental") else None
                    analyzer_result = run_analyzer(source_path, out_dir, extra_args)
                    analyzer_output = (analyzer_result.stdout or "") + (analyzer_result.stderr or "")
                    self.assertEqual(analyzer_result.returncode, 0, analyzer_output)

                    report = report_text(out_dir)
                    self.assertNotIn(fixture["forbidden_warning"], report)


class Au3CheckGoldenParityTests(unittest.TestCase):
    def assert_au3check_golden(self, args, out_dir):
        if not AU3CHECK.exists():
            raise unittest.SkipTest(f"Au3Check.exe not found at {AU3CHECK}")

        original = subprocess.run([str(AU3CHECK), *args], capture_output=True, text=True, cwd=PROJECT_ROOT)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
        analyzer = subprocess.run(
            [sys.executable, str(ANALYZER), *args, "--out-dir", str(out_dir), "--skip-system-includes"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            env=env,
        )

        self.assertEqual(analyzer.returncode, original.returncode, analyzer.stdout + analyzer.stderr)
        self.assertEqual(analyzer.stdout, original.stdout)

    def assert_au3check_diagnostics_golden(self, args, out_dir):
        if not AU3CHECK.exists():
            raise unittest.SkipTest(f"Au3Check.exe not found at {AU3CHECK}")

        original = subprocess.run([str(AU3CHECK), *args], capture_output=True, text=True, cwd=PROJECT_ROOT)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
        analyzer = subprocess.run(
            [sys.executable, str(ANALYZER), *args, "--out-dir", str(out_dir), "--skip-system-includes"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            env=env,
        )

        self.assertEqual(analyzer.returncode, original.returncode, analyzer.stdout + analyzer.stderr)

        def parse_diagnostics(stdout):
            headers = []
            summary = None
            for line in stdout.splitlines():
                m = re.match(r'^"(.*?)"\((\d+),(\d+)\)\s*:\s*(\w+)\s*:\s*(.*)$', line)
                if m:
                    headers.append((int(m.group(2)), int(m.group(3)), m.group(4).lower(), m.group(5).strip().lower()))
                elif "error(s)" in line and "warning(s)" in line:
                    m_sum = re.search(r'(\d+)\s+error\(s\),\s*(\d+)\s+warning\(s\)', line)
                    if m_sum:
                        summary = (int(m_sum.group(1)), int(m_sum.group(2)))
            return headers, summary

        orig_headers, orig_sum = parse_diagnostics(original.stdout)
        anal_headers, anal_sum = parse_diagnostics(analyzer.stdout)

        self.assertEqual(anal_headers, orig_headers, f"Original:\n{original.stdout}\nAnalyzer:\n{analyzer.stdout}")
        self.assertEqual(anal_sum, orig_sum, f"Original:\n{original.stdout}\nAnalyzer:\n{analyzer.stdout}")
        return original, analyzer

    def test_dash_question_usage_matches_original_au3check_exactly(self):
        if not AU3CHECK.exists():
            raise unittest.SkipTest(f"Au3Check.exe not found at {AU3CHECK}")

        original = subprocess.run([str(AU3CHECK), "-?"], capture_output=True, text=True, cwd=PROJECT_ROOT)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
        analyzer = subprocess.run(
            [sys.executable, str(ANALYZER), "-?"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            env=env,
        )

        self.assertEqual(analyzer.returncode, original.returncode)
        self.assertEqual(analyzer.stdout, original.stdout)

    def test_w3_w5_w6_output_matches_original_au3check_exactly(self):
        source_path = Path("tests") / "integration_test_warnings.au3"
        args = ["-q", "-d", "-w", "3", "-w", "5", "-w", "6", "-w-", "7", str(source_path)]
        out_dir = PROJECT_ROOT / ".tmp" / "golden_parity_warnings"
        self.assert_au3check_golden(args, out_dir)

    def test_w1_duplicate_include_output_matches_original_au3check_exactly(self):
        with make_temp_dir("golden_w1_") as tmp:
            tmp_path = Path(tmp)
            child_path = tmp_path / "child.au3"
            child_path.write_text("; child\n", encoding="utf-8", newline="\r\n")
            source_path = tmp_path / "main.au3"
            source_path.write_text('#include "child.au3"\n#include "child.au3"\n', encoding="utf-8", newline="\r\n")

            args = ["-q", "-w", "1", str(source_path.relative_to(PROJECT_ROOT))]
            out_dir = PROJECT_ROOT / ".tmp" / "golden_parity_w1"
            self.assert_au3check_golden(args, out_dir)

    def test_standard_include_call_resolves_cleanly(self):
        with make_temp_dir("golden_include_call_") as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "main.au3"
            source_path.write_text('#include <Array.au3>\nLocal $a[1]\n_ArrayAdd($a, "test")\n', encoding="utf-8", newline="\r\n")

            args = ["-q", str(source_path.relative_to(PROJECT_ROOT))]
            out_dir = PROJECT_ROOT / ".tmp" / "golden_parity_include_call"
            self.assert_au3check_golden(args, out_dir)

    def test_w2_missing_comments_end_output_matches_original_au3check_exactly(self):
        with make_temp_dir("golden_w2_") as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "main.au3"
            source_path.write_text("#cs\nunterminated\n", encoding="utf-8", newline="\r\n")

            args = ["-q", "-w", "2", str(source_path.relative_to(PROJECT_ROOT))]
            out_dir = PROJECT_ROOT / ".tmp" / "golden_parity_w2"
            self.assert_au3check_golden(args, out_dir)

    def test_w4_local_in_global_output_matches_original_au3check_exactly(self):
        with make_temp_dir("golden_w4_") as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "main.au3"
            source_path.write_text("Local $x = 1\n", encoding="utf-8", newline="\r\n")

            args = ["-q", "-w", "4", str(source_path.relative_to(PROJECT_ROOT))]
            out_dir = PROJECT_ROOT / ".tmp" / "golden_parity_w4"
            self.assert_au3check_golden(args, out_dir)

    def test_w7_udf_byref_output_matches_original_au3check_exactly(self):
        source = """
        Func Mut(ByRef $x)
            $x = 1
        EndFunc

        Func Main()
            Local $v = 0
            Local Const $c = 0
            Local $a[1]
            Mut($v)
            Mut($c)
            Mut(5)
            Mut(1 + 2)
            Mut($a[0])
        EndFunc
        """
        with make_temp_dir("golden_w7_") as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "main.au3"
            source_path.write_text(normalize_source(source), encoding="utf-8", newline="\r\n")

            args = ["-q", "-w", "7", str(source_path.relative_to(PROJECT_ROOT))]
            out_dir = PROJECT_ROOT / ".tmp" / "golden_parity_w7"
            self.assert_au3check_golden(args, out_dir)

    def test_missing_input_file_matches_original_au3check_exactly(self):
        args = ["-q", str(Path(".tmp") / "golden_missing_input" / "no_such.au3")]
        out_dir = PROJECT_ROOT / ".tmp" / "golden_parity_missing_input"
        self.assert_au3check_golden(args, out_dir)

    def test_missing_endfunc_matches_original_au3check_exactly(self):
        with make_temp_dir("golden_missing_endfunc_") as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "main.au3"
            source_path.write_text("Func Main()\nLocal $x = 1\n", encoding="utf-8", newline="\r\n")

            args = ["-q", str(source_path.relative_to(PROJECT_ROOT))]
            out_dir = PROJECT_ROOT / ".tmp" / "golden_parity_missing_endfunc"
            self.assert_au3check_golden(args, out_dir)

    def test_missing_endif_matches_original_au3check_exactly(self):
        with make_temp_dir("golden_missing_endif_") as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "main.au3"
            source_path.write_text("If 1 Then\nLocal $x = 1\n", encoding="utf-8", newline="\r\n")

            args = ["-q", str(source_path.relative_to(PROJECT_ROOT))]
            out_dir = PROJECT_ROOT / ".tmp" / "golden_parity_missing_endif"
            self.assert_au3check_golden(args, out_dir)

    def test_missing_block_closers_match_original_au3check_exactly(self):
        cases = {
            "endselect": "Select\nCase 1\nLocal $x = 1\n",
            "endswitch": "Switch 1\nCase 1\nLocal $x = 1\n",
            "next": "For $i = 1 To 2\nLocal $x = $i\n",
            "wend": "While 1\nLocal $x = 1\n",
            "until": "Do\nLocal $x = 1\n",
        }
        with make_temp_dir("golden_missing_blocks_") as tmp:
            tmp_path = Path(tmp)
            for name, source in cases.items():
                with self.subTest(name=name):
                    source_path = tmp_path / f"{name}.au3"
                    source_path.write_text(source, encoding="utf-8", newline="\r\n")

                    args = ["-q", str(source_path.relative_to(PROJECT_ROOT))]
                    out_dir = PROJECT_ROOT / ".tmp" / f"golden_parity_missing_{name}"
                    self.assert_au3check_golden(args, out_dir)

    def test_duplicate_function_name_matches_original_au3check_exactly(self):
        with make_temp_dir("golden_duplicate_func_") as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "main.au3"
            source_path.write_text("Func Main()\nEndFunc\nFunc Main()\nEndFunc\nFunc Main()\nEndFunc\n", encoding="utf-8", newline="\r\n")

            args = ["-q", str(source_path.relative_to(PROJECT_ROOT))]
            out_dir = PROJECT_ROOT / ".tmp" / "golden_parity_duplicate_func"
            self.assert_au3check_golden(args, out_dir)

    def test_fine_grained_syntax_errors_match_original_au3check_exactly(self):
        cases = {
            "open_paren": ("Local $x = ((1)", "unbalanced paranthesis expression."),
            "close_paren": ("Local $x = (1))", "syntax error"),
            "missing_close_paren": ("Local $x = (1", "unbalanced paranthesis expression."),
            "extra_close_paren": ("Local $x = 1)", "syntax error"),
            "open_bracket": ("Local $a[[1]", "syntax error"),
            "close_bracket": ("Local $a[1]]", "syntax error"),
            "missing_close_bracket": ("Local $a[1", "syntax error"),
            "extra_close_bracket": ("Local $a[1]]", "statement cannot be just an expression."),
            "unclosed_double_quote": ('Local $s = "hello', "syntax error (illegal character)"),
            "unclosed_single_quote": ("Local $s = 'hello", "syntax error (illegal character)"),
            "extra_commas": ("Local $x = 1,,2", "syntax error"),
            "missing_comma_call_args": ('MsgBox(0 "title" "text")', "syntax error"),
            "extra_comma_call_args": ('MsgBox(0, , "text")', "syntax error"),
            "trailing_comma_call_args": ('MsgBox(0, "title", )', "syntax error"),
            "missing_comma_params": ("Func Test($a $b)\nEndFunc", "syntax error"),
            "extra_comma_params": ("Func Test($a, , $b)\nEndFunc", "syntax error"),
            "open_curly": ("Local $x = {1}", "syntax error (illegal character)"),
            "close_curly": ("Local $x = 1}", "syntax error (illegal character)"),
            "unsupported_try_statement": ("Try\n    Local $x = 1\nEndTry", "try(): undefined function."),
            "undefined_func": ("MyUndefinedFunc()", "myundefinedfunc(): undefined function."),
            "undefined_macro": ("Local $x = @MyInvalidMacro", "undefined macro."),
            "builtin_too_few_args": ("Abs()", "abs() [built-in] called with wrong number of args."),
            "builtin_too_many_args": ("Abs(1, 2)", "abs() [built-in] called with wrong number of args."),
            "udf_too_few_args": ("Func Test($a, $b)\nEndFunc\nTest(1)", "test() called with wrong number of args."),
            "udf_too_many_args": ("Func Test($a, $b)\nEndFunc\nTest(1, 2, 3)", "test() called with wrong number of args."),
        }
        with make_temp_dir("golden_fine_syntax_") as tmp:
            tmp_path = Path(tmp)
            for name, (source, expected_msg) in cases.items():
                with self.subTest(name=name):
                    source_path = tmp_path / f"{name}.au3"
                    source_path.write_text(source, encoding="utf-8", newline="\r\n")

                    args = ["-q", str(source_path.relative_to(PROJECT_ROOT))]
                    out_dir = PROJECT_ROOT / ".tmp" / f"golden_parity_fine_syntax_{name}"
                    original, analyzer = self.assert_au3check_diagnostics_golden(args, out_dir)
                    self.assertIn(expected_msg, analyzer.stdout.lower())
                    self.assertIn(expected_msg, original.stdout.lower())

    def test_v2_v3_verbose_output_matches_original_au3check_for_representative_fixture(self):
        source = """
        Global $gUnused = 1

        Func Helper($x)
            Return $x + 1
        EndFunc

        Func Main()
            Local $y = Helper(1)
        EndFunc
        """
        with make_temp_dir("golden_verbose_") as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "main.au3"
            source_path.write_text(normalize_source(source), encoding="utf-8", newline="\r\n")

            for flag in ("2", "3"):
                with self.subTest(flag=flag):
                    args = ["-q", "-v", flag, str(source_path.relative_to(PROJECT_ROOT))]
                    out_dir = PROJECT_ROOT / ".tmp" / f"golden_parity_v{flag}"
                    self.assert_au3check_golden(args, out_dir)


class Au3CheckOverlapDocumentationTests(unittest.TestCase):
    def test_overlap_fixtures_are_not_claimed_as_au3check_blind(self):
        with make_temp_dir("autoit_static_analyzer_overlap_") as tmp:
            tmp_path = Path(tmp)
            for fixture in AU3CHECK_OVERLAP_FIXTURES:
                with self.subTest(fixture=fixture["name"]):
                    source_path = tmp_path / f"{fixture['name']}.au3"
                    source_path.write_text(normalize_source(fixture["source"]), encoding="utf-8", newline="\r\n")

                    au3check_result = run_au3check(source_path)
                    output = (au3check_result.stdout or "") + (au3check_result.stderr or "")
                    self.assertNotEqual(
                        au3check_result.returncode,
                        0,
                        f"{fixture['warning']} unexpectedly became Au3Check-clean:\n{output}",
                    )


class Au3CheckBlindCandidateFixtureTests(unittest.TestCase):
    def test_candidate_fixtures_are_au3check_strict_clean_and_detected(self):
        with make_temp_dir("autoit_static_analyzer_candidates_") as tmp:
            tmp_path = Path(tmp)
            for fixture in AU3CHECK_BLIND_CANDIDATE_FIXTURES:
                with self.subTest(fixture=fixture["name"]):
                    case_dir = tmp_path / fixture["name"]
                    case_dir.mkdir()
                    source_path = case_dir / "main.au3"
                    source_path.write_text(normalize_source(fixture["source"]), encoding="utf-8", newline="\r\n")

                    au3check_result = run_au3check(source_path)
                    assert_au3check_clean(self, au3check_result)

                    out_dir = case_dir / "analysis"
                    analyzer_result = run_analyzer(source_path, out_dir, ["--enable-experimental-checks"])
                    analyzer_output = (analyzer_result.stdout or "") + (analyzer_result.stderr or "")
                    self.assertEqual(analyzer_result.returncode, 0, analyzer_output)

                    report = report_text(out_dir)
                    self.assertIn(fixture["warning"], report)
                    if fixture["variable"]:
                        self.assertIn(fixture["variable"], report.lower())

class Au3CheckLegacyWarningsTests(unittest.TestCase):
    def test_dash_question_prints_au3check_usage(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
        res = subprocess.run([sys.executable, str(ANALYZER), "-?"], capture_output=True, text=True, env=env)
        self.assertEqual(res.returncode, 3)
        self.assertIn("Usage: Au3Check [-q] [-d] [-w[-] n]... [-v[-] n]... [-I dir]... file.au3", res.stdout)
        self.assertIn('            -d        : as Opt("MustDeclareVars", 1)', res.stdout)

    def test_legacy_output_has_header_source_marker_and_summary(self):
        source = """
        Func Main()
            Local $unused
        EndFunc
        """
        with make_temp_dir("test_legacy_format_") as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "main.au3"
            source_path.write_text(normalize_source(source), encoding="utf-8", newline="\r\n")
            out_dir = tmp_path / "analysis"

            res = run_analyzer(source_path, out_dir, ["-w", "5"])
            self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
            lines = res.stdout.splitlines()
            self.assertRegex(lines[0], r"^AutoIt3 Syntax Checker v\d+\.\d+\.\d+\.\d+  Copyright")
            self.assertRegex(res.stdout, r'"\S+main\.au3"\(\d+,\d+\) : warning: .+')
            self.assertIn("Local $unused", res.stdout)
            self.assertRegex(res.stdout, r"(?m)^~+\^$")
            self.assertRegex(res.stdout, r"main\.au3 - 0 error\(s\), 1 warning\(s\)")

    def test_quiet_legacy_output_suppresses_header_but_keeps_summary(self):
        source = """
        Func Main()
            Local $unused
        EndFunc
        """
        with make_temp_dir("test_legacy_quiet_") as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "main.au3"
            source_path.write_text(normalize_source(source), encoding="utf-8", newline="\r\n")
            out_dir = tmp_path / "analysis"

            res = run_analyzer(source_path, out_dir, ["-q", "-w", "5"])
            self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
            self.assertNotIn("AutoIt3 Syntax Checker", res.stdout)
            self.assertNotIn("Initializing AutoIt Scoping Analyzer", res.stdout)
            self.assertRegex(res.stdout, r"main\.au3 - 0 error\(s\), 1 warning\(s\)")

    def test_verbose_include_trace_v1_uses_au3check_include_format(self):
        with make_temp_dir("test_legacy_v1_") as tmp:
            tmp_path = Path(tmp)
            child_path = tmp_path / "child.au3"
            child_path.write_text("#include-once\r\nGlobal Const $VALUE = 1\r\n", encoding="utf-8")
            source_path = tmp_path / "main.au3"
            source_path.write_text('#include "child.au3"\r\n', encoding="utf-8")
            out_dir = tmp_path / "analysis"

            res = run_analyzer(source_path, out_dir, ["-v", "1", "-I", str(tmp_path)])
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            self.assertIn("Include search-path :", res.stdout)
            self.assertRegex(res.stdout, r'"[^"]+main\.au3"\(1,1\) : INCLUDE: "[^"]+child\.au3"')

    def test_local_in_global_scope_warning_w4(self):
        source = """
        Local $globalLocal = 1
        """
        with make_temp_dir("test_w4_") as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "main.au3"
            source_path.write_text(normalize_source(source), encoding="utf-8", newline="\r\n")
            out_dir = tmp_path / "analysis"

            res = run_analyzer(source_path, out_dir, [])
            self.assertEqual(res.returncode, 0)
            self.assertNotIn("global scope", res.stdout.lower())

            res_w4 = run_analyzer(source_path, out_dir, ["-w", "4"])
            self.assertEqual(res_w4.returncode, 1)
            self.assertIn("global scope", res_w4.stdout.lower())

    def test_duplicate_declaration_warning_w3(self):
        source = """
        Func Main()
            Local $var = 1
            Local $var = 2
        EndFunc
        """
        with make_temp_dir("test_w3_") as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "main.au3"
            source_path.write_text(normalize_source(source), encoding="utf-8", newline="\r\n")
            out_dir = tmp_path / "analysis"
            
            # Run without -w 3 (should not report duplicate declaration)
            res = run_analyzer(source_path, out_dir, [])
            self.assertEqual(res.returncode, 0)
            self.assertNotIn("already declared", res.stdout)
            
            # Run with -w 3 (should report warning and exit with 1 because of is_legacy_mode)
            res_w3 = run_analyzer(source_path, out_dir, ["-w", "3"])
            self.assertEqual(res_w3.returncode, 1)
            self.assertIn("already declared", res_w3.stdout)

    def test_unused_variable_warning_w5(self):
        source = """
        Func Main()
            Local $unused = 1
        EndFunc
        """
        with make_temp_dir("test_w5_") as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "main.au3"
            source_path.write_text(normalize_source(source), encoding="utf-8", newline="\r\n")
            out_dir = tmp_path / "analysis"
            
            # Run without -w 5 (default: False)
            res = run_analyzer(source_path, out_dir, [])
            self.assertEqual(res.returncode, 0)
            self.assertNotIn("declared, but not used in func", res.stdout)
            
            # Run with -w 5
            res_w5 = run_analyzer(source_path, out_dir, ["-w", "5"])
            self.assertEqual(res_w5.returncode, 1)
            self.assertIn("$unused: declared, but not used in func.", res_w5.stdout)

    def test_deprecated_dim_warning_w6(self):
        source = """
        Func Main()
            Dim $dimVar = 5
        EndFunc
        """
        with make_temp_dir("test_w6_") as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "main.au3"
            source_path.write_text(normalize_source(source), encoding="utf-8", newline="\r\n")
            out_dir = tmp_path / "analysis"
            
            # Run without -w 6 (default: False)
            res = run_analyzer(source_path, out_dir, [])
            self.assertEqual(res.returncode, 0)
            self.assertNotIn("'Dim' deprecated as declaration", res.stdout)
            
            # Run with -w 6
            res_w6 = run_analyzer(source_path, out_dir, ["-w", "6"])
            self.assertEqual(res_w6.returncode, 1)
            self.assertIn("'Dim' deprecated as declaration. Prefer to use Local or Global.", res_w6.stdout)

    def test_byref_const_pass_warning_w7(self):
        source = """
        Func Test(ByRef $a)
            $a = 10
        EndFunc
        Func Main()
            Test(5)
        EndFunc
        """
        with make_temp_dir("test_w7_") as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "main.au3"
            source_path.write_text(normalize_source(source), encoding="utf-8", newline="\r\n")
            out_dir = tmp_path / "analysis"

            # Normal analyzer mode keeps -w7 off so the burn-in baseline is stable.
            res_default = run_analyzer(source_path, out_dir, [])
            self.assertEqual(res_default.returncode, 0)
            self.assertNotIn("passing expression or literal", res_default.stdout)

            # Au3Check does not report UDF ByRef argument warnings.
            res_legacy_default = run_analyzer(source_path, out_dir, ["-q"])
            self.assertEqual(res_legacy_default.returncode, 0)
            self.assertNotIn("passing expression or literal", res_legacy_default.stdout)
            
            # Run with -w 7 explicitly; UDF ByRef parity still stays quiet.
            res_w7 = run_analyzer(source_path, out_dir, ["-w", "7"])
            self.assertEqual(res_w7.returncode, 0)
            self.assertNotIn("passing expression or literal", res_w7.stdout)
            
            # Run with -w- 7 (warning disabled)
            res_w7_off = run_analyzer(source_path, out_dir, ["-w-", "7"])
            self.assertEqual(res_w7_off.returncode, 0)
            self.assertNotIn("passing expression or literal", res_w7_off.stdout)

    def test_duplicate_include_warning_w1(self):
        source_child = """
        #include-once
        ; No warning if #include-once is present
        """
        source_main = """
        #include "child.au3"
        #include "child.au3"
        """
        with make_temp_dir("test_w1_") as tmp:
            tmp_path = Path(tmp)
            child_path = tmp_path / "child.au3"
            child_path.write_text(normalize_source(source_child), encoding="utf-8", newline="\r\n")
            main_path = tmp_path / "main.au3"
            main_path.write_text(normalize_source(source_main), encoding="utf-8", newline="\r\n")
            out_dir = tmp_path / "analysis"
            
            # Since child has include-once, no warning is generated
            res = run_analyzer(main_path, out_dir, ["-w", "1", "-I", str(tmp_path)])
            self.assertEqual(res.returncode, 0)
            self.assertNotIn("already included file", res.stdout)
            
            # Now let's try WITHOUT #include-once in child
            child_path.write_text("; no include-once\n", encoding="utf-8", newline="\r\n")
            res_w1 = run_analyzer(main_path, out_dir, ["-w", "1", "-I", str(tmp_path)])
            self.assertEqual(res_w1.returncode, 1)
            self.assertIn("already included file", res_w1.stdout)

    def test_missing_comments_end_warning_w2(self):
        source = """
        #cs
        Some comment
        """
        with make_temp_dir("test_w2_") as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "main.au3"
            source_path.write_text(normalize_source(source), encoding="utf-8", newline="\r\n")
            out_dir = tmp_path / "analysis"
            
            # Run with -w- 2 to disable
            res_off = run_analyzer(source_path, out_dir, ["-w-", "2"])
            self.assertEqual(res_off.returncode, 0)
            self.assertNotIn("#comments-start has no explicit closing #comments-end", res_off.stdout)
            
            # Run with -w 2
            res_w2 = run_analyzer(source_path, out_dir, ["-w", "2"])
            self.assertEqual(res_w2.returncode, 1)
            self.assertIn("#comments-start has no explicit closing #comments-end", res_w2.stdout)


if __name__ == "__main__":
    unittest.main()
