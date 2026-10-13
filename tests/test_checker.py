import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import checker  # noqa: E402

PARSE = [sys.executable, '-c', 'import ast, sys; ast.parse(sys.stdin.read())']


class CheckerTest(unittest.TestCase):
    def test_parses(self):
        self.assertTrue(checker.parses(PARSE, 'x = (1)\n'))
        self.assertFalse(checker.parses(PARSE, 'x = (1\n'))

    def test_missing_checker(self):
        self.assertIsNone(checker.parses(['no-such-checker'], ''))

    def test_login_path_keeps_the_current_path(self):
        found = checker.login_path().split(os.pathsep)
        for directory in os.environ['PATH'].split(os.pathsep):
            if directory:
                self.assertIn(directory, found)
        self.assertEqual(len(found), len(set(found)))


if __name__ == '__main__':
    unittest.main()
