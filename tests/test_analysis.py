import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import analysis  # noqa: E402
from core.synth import mood  # noqa: E402

CLEAN = '''\
def greet(name):
    """Say hello."""
    return 'Hello, ' + name
'''


class MaskTest(unittest.TestCase):
    def test_blanks_spans_but_keeps_newlines(self):
        text = 'a = "x)\ny" # (\nb'
        masked = analysis.mask(text, [(4, 10), (11, 14)])
        self.assertEqual(masked, 'a = ' + '   \n  ' + ' ' + '   ' + '\nb')
        self.assertEqual(len(masked), len(text))

    def test_tolerates_overlapping_and_unsorted_spans(self):
        self.assertEqual(analysis.mask('abcdef', [(3, 5), (1, 4)]), 'a    f')


class BracketTest(unittest.TestCase):
    def test_balanced(self):
        self.assertEqual(analysis.unbalanced_brackets('f(a[1], {b: (c)})'), 0)

    def test_unclosed_and_stray(self):
        self.assertEqual(analysis.unbalanced_brackets('f(('), 2)
        self.assertEqual(analysis.unbalanced_brackets('f())'), 1)

    def test_closer_skipping_an_unclosed_opener(self):
        self.assertEqual(analysis.unbalanced_brackets('f(a[1)'), 1)


class ExamineTest(unittest.TestCase):
    def test_clean_code_is_radiant(self):
        report = analysis.examine(CLEAN)
        self.assertEqual(report.health, 1.0)
        self.assertEqual(mood(report.health)[0], 'radiant')

    def test_one_syntax_error_is_uneasy(self):
        report = analysis.examine(CLEAN, syntax_errors=1)
        self.assertEqual(mood(report.health)[0], 'uneasy')

    def test_a_few_bugs_are_haunted(self):
        report = analysis.examine(CLEAN + 'print((x)\n', syntax_errors=2)
        self.assertEqual(report.unbalanced_brackets, 1)
        self.assertEqual(report.bugs, 3)
        self.assertEqual(mood(report.health)[0], 'haunted')

    def test_masked_brackets_do_not_count(self):
        text = 'x = ")"\n'
        report = analysis.examine(text, code=analysis.mask(text, [(4, 7)]))
        self.assertEqual(report.unbalanced_brackets, 0)

    def test_bracket_check_can_be_disabled(self):
        report = analysis.examine('f(', check_brackets=False)
        self.assertEqual(report.unbalanced_brackets, 0)

    def test_mess_alone_is_never_worse_than_wistful(self):
        line = '\t' + 'x' * 200 + '   '
        text = '\n'.join([line, '    y'] * 50)
        report = analysis.examine(text, comments='TODO ' * 20)
        self.assertTrue(report.mixed_indentation)
        self.assertGreaterEqual(report.health, 0.45)
        self.assertEqual(mood(report.health)[0], 'wistful')

    def test_counts_mess(self):
        text = 'a = 1  \n' + 'b' * 101 + '\n' + ' ' * 20 + 'deep\n' + ' ' * 22 + 'aligned\n'
        report = analysis.examine(text, max_line_length=100, max_nesting=4)
        self.assertEqual(report.trailing_whitespace, 1)
        self.assertEqual(report.long_lines, 1)
        self.assertEqual(report.deep_lines, 1)
        self.assertLess(report.health, 1.0)

    def test_markers_only_come_from_comments(self):
        self.assertEqual(analysis.examine('TODO = 1').markers, 0)
        self.assertEqual(analysis.examine('x', comments='# TODO: and FIXME').markers, 2)


if __name__ == '__main__':
    unittest.main()
