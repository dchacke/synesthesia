"""Exercise the Sublime glue against stand-ins for the sublime modules."""

import importlib
import os
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Settings(dict):
    def set(self, key, value):
        self[key] = value

    def add_on_change(self, key, callback):
        pass

    def clear_on_change(self, key):
        pass


class Region:
    def __init__(self, a, b):
        self.a, self.b = a, b

    def begin(self):
        return min(self.a, self.b)

    def end(self):
        return max(self.a, self.b)


class View:
    def __init__(self, text, scopes=None, scope='source.python', element=None, path=None, **settings):
        self.text = text
        self.path = path
        self.scopes = scopes or {}
        self.scope = scope
        self._element = element
        self._settings = Settings(settings)
        self.status = {}

    def id(self):
        return id(self)

    def is_valid(self):
        return True

    def element(self):
        return self._element

    def window(self):
        return None

    def file_name(self):
        return self.path

    def is_dirty(self):
        return True

    def settings(self):
        return self._settings

    def size(self):
        return len(self.text)

    def substr(self, region):
        return self.text[region.begin():region.end()]

    def rowcol(self, point):
        before = self.text[:point]
        return before.count('\n'), len(before) - before.rfind('\n') - 1

    def match_selector(self, point, selector):
        return selector.split('.')[0] == self.scope.split('.')[0]

    def find_by_selector(self, selector):
        return [Region(a, b) for a, b in self.scopes.get(selector, [])]

    def set_status(self, key, value):
        self.status[key] = value

    def erase_status(self, key):
        self.status.pop(key, None)


def install_fakes(cache):
    sublime = types.ModuleType('sublime')
    sublime.Region = Region
    sublime.HIDE_ON_MOUSE_MOVE_AWAY = 8
    sublime.settings = Settings()
    sublime.load_settings = lambda name: sublime.settings
    sublime.save_settings = lambda name: None
    sublime.status_message = lambda message: None
    sublime.cache_path = lambda: cache
    sublime.set_timeout_async = lambda callback, delay=0: callback()
    sublime.windows = lambda: []
    sublime.active_view = None
    sublime.active_window = lambda: types.SimpleNamespace(
        active_view=lambda: sublime.active_view, folders=lambda: [], id=lambda: 1)
    sublime.find_syntax_for_file = lambda path, first_line='': (
        types.SimpleNamespace(scope='source.python') if path.endswith('.py') else None)
    sublime.score_selector = lambda scope, selector: int(scope.startswith(selector))

    plugin = types.ModuleType('sublime_plugin')
    plugin.EventListener = object
    plugin.ApplicationCommand = object

    class TextCommand:
        def __init__(self, view):
            self.view = view
    plugin.TextCommand = TextCommand

    sys.modules['sublime'] = sublime
    sys.modules['sublime_plugin'] = plugin
    return sublime


CACHE = tempfile.TemporaryDirectory()
SUBLIME = install_fakes(CACHE.name)
# Load the plugin the way Sublime does: as a module of a package named after
# the folder the plugin is installed in.
sys.modules['Synesthesia'] = types.ModuleType('Synesthesia')
sys.modules['Synesthesia'].__path__ = [ROOT]
PLUGIN = importlib.import_module('Synesthesia.synesthesia')
from Synesthesia.core import analysis  # noqa: E402


def report(health):
    return analysis.Report(health=health, quality=health, lines=10)


class PluginTest(unittest.TestCase):
    def setUp(self):
        self.sublime = SUBLIME
        self.sublime.settings.clear()
        self.sublime.settings.update(enabled=True, mode='chime', listen_to='file')
        self.plugin = PLUGIN
        warm_up = mock.patch.object(self.plugin.Conductor, 'warm_up')  # no rendering in tests
        warm_up.start()
        self.addCleanup(warm_up.stop)
        self.plugin.plugin_loaded()
        self.addCleanup(self.plugin.plugin_unloaded)
        self.conductor = self.plugin.conductor
        self.accents = []
        self.phrases = []
        self.conductor.accent = lambda health, way: self.accents.append(way)
        self.conductor.renderer = mock.Mock(submit=lambda fn, *args: self.phrases.append(args))

    def test_measure_reads_scopes(self):
        text = 'def f():\n    x = ")"\n    if y and z:\n        $\n'
        view = View(text, scopes={
            'string, comment': [(17, 20)],
            'invalid - invalid.deprecated': [(42, 43)],
            'entity.name.function': [(4, 5)],
            self.plugin.BRANCHES: [(25, 27), (30, 33)],
        })
        r = self.plugin.measure(view)
        self.assertEqual(r.unbalanced_brackets, 0)
        self.assertEqual(r.syntax_errors, 1)
        self.assertEqual(r.health, analysis.health(1.0, 1))

    def test_ignores_prose_panels_and_widgets(self):
        self.assertTrue(self.plugin.wants(View('x')))
        self.assertFalse(self.plugin.wants(View('x', scope='text.plain')))
        self.assertFalse(self.plugin.wants(View('x', element='output:synesthesia')))
        self.assertFalse(self.plugin.wants(View('x', is_widget=True)))

    def test_line_limit_uses_widest_ruler(self):
        self.assertEqual(self.plugin.line_limit(View('', rulers=[[72, 'solid'], 79])), 79)
        self.assertEqual(self.plugin.line_limit(View('')), 100)
        self.sublime.settings['max_line_length'] = 120
        self.assertEqual(self.plugin.line_limit(View('', rulers=[79])), 120)

    def test_accents_follow_the_direction_of_change(self):
        view = View('x = 1\n')
        self.conductor.listen(view)  # first look: nothing to compare with
        view.text = 'x = (\n'
        self.conductor.listen(view)
        view.text = 'x = 1\n'
        self.conductor.listen(view)
        self.conductor.listen(view)  # unchanged: silence
        self.conductor.listen(view, saved=True)  # saving always answers
        self.assertEqual(self.accents, ['down', 'up', 'same'])
        self.assertEqual(view.status['synesthesia'], '♪ beautiful (1.00)')

    def test_chime_mode_plays_a_phrase_when_the_stage_changes(self):
        self.conductor.hear(report(1.0))
        self.conductor.hear(report(0.95))
        self.conductor.hear(report(0.5))
        self.assertEqual(self.phrases, [(3,)])

    def test_ambient_mode_hurries_the_band(self):
        self.sublime.settings['mode'] = 'ambient'
        with mock.patch.object(self.plugin, 'Band') as band:
            self.conductor.configure()
            self.conductor.hear(report(1.0))  # wakes the waiting band
            self.conductor.hear(report(0.95))  # same stage: keep playing
            self.conductor.hear(report(0.1))
        self.assertEqual(band.return_value.hurry.call_count, 2)
        self.assertEqual(self.phrases, [])

    def test_project_changes_play_one_accent_per_file(self):
        before, after = report(0.9), report(0.5)
        self.conductor.hear_project({'a.py': after, 'b.py': report(1.0)},
                                    [('a.py', before, after), ('b.py', None, report(1.0)),
                                     ('c.py', report(1.0), None)], initial=False)
        self.assertEqual(self.accents, ['down', 'same'])
        self.assertAlmostEqual(self.conductor.report.health, 0.75)

    def test_the_initial_project_scan_is_silent(self):
        self.conductor.hear_project({'a.py': report(1.0)}, [], initial=True)
        self.assertEqual(self.accents, [])
        self.assertEqual(self.conductor.report.health, 1.0)

    def test_toggle(self):
        command = self.plugin.SynesthesiaToggleCommand()
        command.run()
        self.assertFalse(self.sublime.settings['enabled'])
        self.conductor.listen(View('x = (\n'))
        self.assertIsNone(self.conductor.report)
        command.run()
        self.assertTrue(command.is_checked())

    def test_set_command(self):
        command = self.plugin.SynesthesiaSetCommand()
        command.run('listen_to', 'project')
        self.assertTrue(command.is_checked('listen_to', 'project'))
        self.assertFalse(command.is_checked('listen_to', 'file'))


class Panel(View):
    """An output panel: scores files that aren't open."""

    def __init__(self):
        super().__init__('', element='output:synesthesia')
        self._syntax = None

    def syntax(self):
        return self._syntax

    def assign_syntax(self, syntax):
        self._syntax = syntax

    def run_command(self, name, args):
        assert name == 'synesthesia_fill'
        self.text = args['text']


class Window:
    def __init__(self, folder):
        self.folder = folder
        self.panel = None

    def id(self):
        return 7

    def folders(self):
        return [self.folder]

    def find_output_panel(self, name):
        return self.panel

    def create_output_panel(self, name, unlisted=False):
        self.panel = Panel()
        return self.panel

    def destroy_output_panel(self, name):
        self.panel = None


class ProjectTest(unittest.TestCase):
    def setUp(self):
        SUBLIME.settings.clear()
        SUBLIME.settings.update(enabled=True, mode='chime', listen_to='project', poll_interval=0.02)
        warm_up = mock.patch.object(PLUGIN.Conductor, 'warm_up')
        warm_up.start()
        self.addCleanup(warm_up.stop)
        PLUGIN.plugin_loaded()
        self.addCleanup(PLUGIN.plugin_unloaded)
        self.conductor = PLUGIN.conductor
        self.accents = []
        self.conductor.accent = lambda health, way: self.accents.append(way)
        self.conductor.renderer = mock.Mock()
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = os.path.join(self.folder.name, 'a.py')
        self.write('def f():\n    return g(1)\n')
        with open(os.path.join(self.folder.name, 'notes.txt'), 'w') as f:
            f.write('(((')
        self.conductor.watch(Window(self.folder.name))

    def write(self, text):
        with open(self.path, 'w') as f:
            f.write(text)
        stat = os.stat(self.path)  # make sure the change is visible even on coarse clocks
        os.utime(self.path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10 ** 9))

    def wait_for(self, condition):
        for _ in range(200):
            if condition():
                return
            time.sleep(0.01)
        self.fail('timed out')

    def test_hears_files_change_on_disk(self):
        self.wait_for(lambda: self.conductor.report is not None)
        self.assertEqual(self.conductor.report.health, 1.0)  # notes.txt isn't source
        self.write('def f():\n    return g(1\n')
        self.wait_for(lambda: self.accents)
        self.assertEqual(self.accents, ['down'])
        self.assertEqual(self.conductor.report.bugs, 1)

    def test_hears_unsaved_edits_to_project_files(self):
        self.wait_for(lambda: self.conductor.watcher.ready)
        self.conductor.listen(View('def f():\n    return g(1\n', path=self.path))
        self.assertEqual(self.accents, ['down'])
        self.conductor.listen(View('x = 1\n', path=os.path.join(self.folder.name, 'elsewhere.py')))
        self.assertEqual(self.accents, ['down'])  # not part of the project


if __name__ == '__main__':
    unittest.main()
