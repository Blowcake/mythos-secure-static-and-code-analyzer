"""@file test_lexer_helpers.py
@brief Unit tests for lexer and source-splitting helpers used by the analyzer.
@details Part of AutoIt_Static_Analyzer. This header is intentionally concise so Doxygen output and future code reviews expose the module boundary before implementation details.
"""
import importlib.util
import unittest
from pathlib import Path


def load_analyzer():
    module_path = Path(__file__).resolve().parents[1] / "src" / "autoit_static_analyzer" / "autoit_windows_x64_scoping_analyzer.py"
    spec = importlib.util.spec_from_file_location("autoit_windows_x64_scoping_analyzer", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LexerHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analyzer = load_analyzer()

    def test_split_code_comment_ignores_semicolon_in_string(self):
        code, comment = self.analyzer.split_code_comment('Local $s = "a;b" ; real comment')
        self.assertEqual(code.strip(), 'Local $s = "a;b"')
        self.assertEqual(comment.strip(), "; real comment")

    def test_split_top_level_ignores_nested_commas(self):
        parts = self.analyzer.split_top_level('$a = Foo(1, 2), $b = ["x,y", 3]', ",")
        self.assertEqual(parts, ['$a = Foo(1, 2)', ' $b = ["x,y", 3]'])

    def test_cached_split_top_level_returns_independent_lists(self):
        first = self.analyzer.split_top_level("$a, $b", ",")
        first.append("mutated")
        second = self.analyzer.split_top_level("$a, $b", ",")
        self.assertEqual(second, ["$a", " $b"])

    def test_leading_keyword_preserves_word_boundaries(self):
        self.assertEqual(self.analyzer.leading_keyword("  Func Probe()"), "func")
        self.assertEqual(self.analyzer.leading_keyword("FunctionCall()"), "functioncall")
        self.assertFalse(self.analyzer.starts_with_keyword("FunctionCall()", "func"))

    def test_declaration_has_const_ignores_comments_and_names(self):
        self.assertTrue(self.analyzer.declaration_has_const("Global Const $x = 1"))
        self.assertFalse(self.analyzer.declaration_has_const("Global $x = MyConstFunc() ; Const in comment"))

    def test_parse_func_signature_keeps_parenthesis_inside_default_string(self):
        result = self.analyzer.AutoItScopingAnalyzer().parse_func_signature(
            'Func Probe($title = "", $filter = "All files (*.*)", $initial = ".", $flags = 0)'
        )
        self.assertIsNotNone(result)
        name, params = result
        self.assertEqual(name, "Probe")
        self.assertIn('$filter = "All files (*.*)"', params)
        self.assertIn("$initial = \".\"", params)
        self.assertIn("$flags = 0", params)


if __name__ == "__main__":
    unittest.main()
