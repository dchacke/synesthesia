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
        self.assertEqual([line.kind for line in sheet], ['function', 'comment', 'blank', 'code', 'blank'])
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


if __name__ == '__main__':
    unittest.main()
