import json
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS = os.path.join(ROOT, 'Synesthete.sublime-settings')
sys.path.insert(0, ROOT)

from core import watcher  # noqa: E402


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(text)


class ListTest(unittest.TestCase):
    def test_walks_folders_skipping_excluded_and_hidden(self):
        with tempfile.TemporaryDirectory() as root:
            for name in ('a.py', 'lib/b.py', 'node_modules/c.js', '.hidden/d.py'):
                write(os.path.join(root, name), '')
            listed = watcher.list_files(root, ['node_modules'])
            found = sorted(os.path.relpath(p, root) for p in listed)
            self.assertEqual(found, ['a.py', os.path.join('lib', 'b.py')])

    def test_skips_lockfiles_by_default(self):
        with open(SETTINGS) as f:
            exclude = json.loads(re.sub(r'^\s*//.*$', '', f.read(), flags=re.M))['project_exclude']
        with tempfile.TemporaryDirectory() as root:
            for name in ('package.json', 'package-lock.json', 'npm-shrinkwrap.json', 'src/a.js'):
                write(os.path.join(root, name), '')
            listed = watcher.list_files(root, exclude)
            found = sorted(os.path.relpath(p, root) for p in listed)
            self.assertEqual(found, ['package.json', os.path.join('src', 'a.js')])


class WatcherTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.calls = []
        self.watcher = watcher.Watcher(
            [self.root.name], wanted=lambda p: p.endswith('.py'),
            measure=lambda path, text: len(text),
            changed=self.record)

    def record(self, reports, changes, initial):
        self.calls.append((reports, changes, initial))

    def path(self, name):
        return os.path.join(self.root.name, name)

    def round(self):
        self.watcher._list()
        self.watcher._poll(initial=not self.calls)
        return self.calls[-1]

    def test_initial_scan_then_changes(self):
        write(self.path('a.py'), 'x')
        write(self.path('notes.txt'), 'ignored')
        reports, changes, initial = self.round()
        self.assertTrue(initial)
        self.assertEqual(reports, {self.path('a.py'): 1})

        write(self.path('a.py'), 'xyz')
        write(self.path('b.py'), 'yy')
        reports, changes, initial = self.round()
        self.assertFalse(initial)
        self.assertEqual(sorted(changes), [(self.path('a.py'), 1, 3), (self.path('b.py'), None, 2)])

        os.remove(self.path('a.py'))
        reports, changes, _ = self.round()
        self.assertEqual(changes, [(self.path('a.py'), 3, None)])
        self.assertEqual(reports, {self.path('b.py'): 2})

    def test_quiet_rounds_report_nothing(self):
        write(self.path('a.py'), 'x')
        self.round()
        self.round()
        self.assertEqual(len(self.calls), 1)


if __name__ == '__main__':
    unittest.main()
