import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import analysis  # noqa: E402
from core.music import name  # noqa: E402

CLEAN = '''\
def greet(name):
    """Say hello."""
    return 'Hello, ' + name
'''


def long_function(lines, indent='    '):
    body = '\n'.join('{}x{} = {}'.format(indent, i, i) for i in range(lines))
    return 'def f():\n' + body + '\n'


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


class IndentUnitTest(unittest.TestCase):
    def test_detects_the_step(self):
        self.assertEqual(analysis.indent_unit(CLEAN), 4)
        self.assertEqual(analysis.indent_unit('class A\n  def b\n    c\n  end\nend\n'), 2)

    def test_ignores_alignment_and_falls_back(self):
        aligned = 'def f():\n    x = g(a,\n          b)\n    return x\n'
        self.assertEqual(analysis.indent_unit(aligned), 4)
        self.assertEqual(analysis.indent_unit('if x:\n\ty\n', default=8), 8)
        self.assertEqual(analysis.indent_unit('x = 1\n', default=3), 3)


class FunctionExtentTest(unittest.TestCase):
    def test_indented_block_with_closing_line(self):
        lines = ['function f() {', '  a();', '', '  b();', '}', '', 'g();']
        self.assertEqual(analysis.function_extents(lines, [0], 2), [(0, 5)])

    def test_ruby_end_and_trailing_blank_lines(self):
        lines = ['def f', '  a', 'end', 'def g', '  b', '', '']
        self.assertEqual(analysis.function_extents(lines, [0, 3], 2), [(0, 3), (3, 5)])


class ExamineTest(unittest.TestCase):
    def test_clean_code_is_beautiful(self):
        report = analysis.examine(CLEAN, functions=[0])
        self.assertEqual(report.health, 1.0)
        self.assertEqual(name(report.health), 'beautiful')

    def test_each_bug_sounds_worse(self):
        names = [name(analysis.examine(CLEAN, syntax_errors=n).health) for n in (1, 2, 3, 8)]
        self.assertEqual(names, ['meh', 'bad', 'awful', 'cursed'])

    def test_unbalanced_brackets_are_bugs(self):
        report = analysis.examine(CLEAN + 'print((x)\n')
        self.assertEqual(report.unbalanced_brackets, 1)
        self.assertEqual(report.bugs, 1)

    def test_masked_brackets_do_not_count(self):
        text = 'x = ")"\n'
        report = analysis.examine(text, code=analysis.mask(text, [(4, 7)]))
        self.assertEqual(report.unbalanced_brackets, 0)

    def test_bracket_check_can_be_disabled(self):
        self.assertEqual(analysis.examine('f(', check_brackets=False).unbalanced_brackets, 0)

    def test_long_functions_lower_quality_gradually(self):
        q = [analysis.examine(long_function(n), functions=[0]).quality for n in (39, 80, 160)]
        self.assertEqual(q[0], 1.0)
        self.assertGreater(q[1], q[2])
        self.assertEqual(analysis.examine(long_function(80), functions=[0]).long_functions, 1)

    def test_complex_functions(self):
        text = long_function(20)
        report = analysis.examine(text, functions=[0], branches=[3] * 15)
        self.assertEqual(report.complex_functions, 1)
        self.assertLess(report.quality, 1.0)

    def test_inner_functions_count_on_their_own(self):
        body = '\n'.join('        x{} = {}'.format(i, i) for i in range(30))
        text = ('def outer():\n    def a():\n' + body + '\n    def b():\n' + body
                + '\n    return a, b\n')
        a, b = 1, 32
        report = analysis.examine(text, functions=[0, a, b],
                                  branches=[a + 1] * 8 + [b + 1] * 8)
        self.assertEqual(report.long_functions, 0)
        self.assertEqual(report.complex_functions, 0)
        self.assertEqual(report.quality, 1.0)

    def test_nesting_counts_from_the_enclosing_function(self):
        wrapped = ('module A\n  class B\n    def c\n'
                   '            deep\n'
                   '    end\n  end\nend\n')
        report = analysis.examine(wrapped, functions=[2], tab_size=2)
        self.assertEqual(report.deep_lines, 0)
        bare = '\n'.join(' ' * 4 * depth + 'x' for depth in range(8))
        self.assertEqual(analysis.examine(bare).deep_lines, 3)

    def test_aligned_continuation_lines_are_not_nesting(self):
        text = 'x = f(a,\n' + ' ' * 22 + 'b)\n'
        self.assertEqual(analysis.examine(text).deep_lines, 0)

    def test_strings_starting_lines_keep_their_indentation(self):
        # Masked, the string is spaces, which used to count as indentation.
        text = "def f():\n    g(\n        'a long string, as views hold',\n    )\n"
        code = analysis.mask(text, [(text.index("'"), text.rindex("'") + 1)])
        self.assertEqual(analysis.examine(text, code=code, functions=[0]).deep_lines, 0)

    def test_nested_brackets_are_not_nesting(self):
        hiccdown = ('def page():\n'
                    + ''.join('    ' * depth + '[div,\n' for depth in range(1, 9))
                    + '    ' * 9 + "'text'" + ']' * 8 + '\n')
        self.assertEqual(analysis.examine(hiccdown, functions=[0]).deep_lines, 0)

    def test_blocks_inside_brackets_are_nesting(self):
        callbacks = ('function f() {\n'
                     + ''.join('  ' * depth + 'g(() => {\n' for depth in range(1, 8))
                     + '  ' * 8 + 'x\n'
                     + ''.join('  ' * depth + '})\n' for depth in range(7, 0, -1)) + '}\n')
        report = analysis.examine(callbacks, functions=[0], tab_size=2)
        self.assertEqual(report.deep_lines, 2 + 1 + 2)  # two callbacks, x, two closers
        blocks = ('def page\n  [:ul,\n    items.map do |item|\n'
                  '      if item\n        if item.a\n          if item.b\n'
                  '            if item.c\n              [:li]\n')
        self.assertEqual(analysis.examine(blocks, functions=[0], tab_size=2).deep_lines, 1)

    def test_aligned_lines_are_one_level_deeper_at_most(self):
        # Under a string 40 columns in, which used to count as 20 levels
        text = ('def f\n  if a\n    if b\n      redirect_to path, alert: \'one \' \\\n'
                + ' ' * 40 + "'two'\n    end\n  end\nend\n")
        self.assertEqual(analysis.examine(text, functions=[0], tab_size=2).deep_lines, 0)

    def test_hash_literals_are_not_nesting(self):
        text = ('def f():\n    g(a,\n' + ''.join('    ' * depth + 'k: {\n' for depth in range(2, 9))
                + '    ' * 9 + 'x: 1' + '}' * 7 + ')\n')
        self.assertEqual(analysis.examine(text, functions=[0]).deep_lines, 0)
        blocks = 'def f\n' + ''.join('  ' * depth + 'g {\n' for depth in range(1, 8)) + '  ' * 8 + 'x\n'
        self.assertEqual(analysis.examine(blocks, functions=[0], tab_size=2).deep_lines, 3)

    def test_urls_dont_make_lines_long(self):
        link = "x = link('https://example.com/" + 'a/' * 60 + "')\n"
        self.assertEqual(analysis.examine(link).long_lines, 0)
        prose = "x = '" + 'word ' * 40 + "'\n"
        self.assertEqual(analysis.examine(prose).long_lines, 1)

    def test_duplicated_chunks(self):
        chunk = '\n'.join('value_{0} = compute_something(argument_{0})'.format(i) for i in range(4))
        report = analysis.examine(chunk + '\n\n' + chunk + '\n')
        self.assertEqual(report.duplicate_lines, 4)
        self.assertEqual(analysis.examine('}\n}\n}\n}\n' * 3).duplicate_lines, 0)

    def test_mess_alone_is_never_worse_than_bad(self):
        line = '\t' + 'x' * 200 + '   '
        text = '\n'.join([line, '    y'] * 50)
        report = analysis.examine(text, comments='TODO ' * 20)
        self.assertTrue(report.mixed_indentation)
        self.assertGreaterEqual(report.health, 0.3)

    def test_markers_only_come_from_comments(self):
        self.assertEqual(analysis.examine('TODO = 1').markers, 0)
        self.assertEqual(analysis.examine('x', comments='# TODO: and FIXME').markers, 2)


class CombineTest(unittest.TestCase):
    def test_weights_quality_by_size_and_counts_every_bug(self):
        big = analysis.Report(health=1.0, quality=1.0, lines=300)
        small = analysis.Report(health=0.25, quality=0.5, lines=100, syntax_errors=1)
        project = analysis.combine([big, small])
        self.assertAlmostEqual(project.quality, 0.875)
        self.assertEqual(project.bugs, 1)
        self.assertAlmostEqual(project.health, 0.875 / 1.8)

    def test_nothing_to_combine(self):
        self.assertIsNone(analysis.combine([]))


if __name__ == '__main__':
    unittest.main()
