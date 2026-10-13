import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import score  # noqa: E402


class ReadTest(unittest.TestCase):
    def test_kinds_depths_and_breaks(self):
        text = 'def f():\n    # note\n\n    x = (\n'
        code = 'def f():\n           \n\n    x = (\n'
        sheet = score.read(text, code, functions=[0], broken_lines=[3])
        kinds = [line.kind for line in sheet]
        self.assertEqual(kinds, ['function', 'comment', 'blank', 'code', 'blank'])
        self.assertEqual([line.depth for line in sheet][:4], [0, 1, 0, 1])
        self.assertEqual([line.broken for line in sheet], [False, False, False, True, False])

    def test_identical_lines_get_identical_keys(self):
        sheet = score.read('x = 1\n  x = 1\ny = 2')
        self.assertEqual(sheet[0].key, sheet[1].key)
        self.assertNotEqual(sheet[0].key, sheet[2].key)


class DifferenceTest(unittest.TestCase):
    def test_first_difference(self):
        a = score.read('a\nb\nc')
        self.assertIsNone(score.first_difference(a, score.read('a\nb\nc')))
        self.assertEqual(score.first_difference(a, score.read('a\nB\nc')), 1)
        self.assertEqual(score.first_difference(a, score.read('a\nb')), 2)


class ChangedLinesTest(unittest.TestCase):
    def test_the_changed_stretch(self):
        old = score.read('a\nb\nc\nd')
        new = score.read('a\nB\nC\nd')
        self.assertEqual(score.changed_lines(old, new), new[1:3])

    def test_new_files_deletions_and_nothing(self):
        old = score.read('a\nb\nc')
        self.assertEqual(score.changed_lines(None, old, limit=2), old[:2])
        self.assertEqual(score.changed_lines(old, score.read('a\nc')), [score.read('a')[0]])
        self.assertEqual(score.changed_lines(old, old), [])


if __name__ == '__main__':
    unittest.main()
