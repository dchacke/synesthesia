"""Exercise the Sublime glue against stand-ins for the sublime modules."""

import importlib
import os
import sys
import tempfile
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
    def __init__(self, text, scopes=None, scope='source.python', element=None, **settings):
        self.text = text
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

    def settings(self):
        return self._settings

    def size(self):
        return len(self.text)

    def substr(self, region):
        return self.text[region.begin():region.end()]

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
    sublime.settings = Settings(enabled=True, mode='chime')
    sublime.load_settings = lambda name: sublime.settings
    sublime.save_settings = lambda name: None
    sublime.status_message = lambda message: None
    sublime.cache_path = lambda: cache
    sublime.set_timeout_async = lambda callback, delay=0: callback()
    sublime.windows = lambda: []
    sublime.active_window = lambda: types.SimpleNamespace(active_view=lambda: None)

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


class PluginTest(unittest.TestCase):
    def setUp(self):
        self.sublime = SUBLIME
        self.sublime.settings.clear()
        self.sublime.settings.update(enabled=True, mode='chime')
        self.plugin = PLUGIN
        self.plugin.plugin_loaded()
        self.addCleanup(self.plugin.plugin_unloaded)
        self.chimes = []
        self.plugin.conductor.chime = self.chimes.append

    def test_measure_masks_strings_and_counts_invalid_scopes(self):
        text = 'x = ")"\ny = $\n'
        view = View(text, scopes={
            'string, comment': [(4, 7)],
            'invalid - invalid.deprecated': [(12, 13)],
        })
        report = self.plugin.measure(view)
        self.assertEqual(report.unbalanced_brackets, 0)
        self.assertEqual(report.syntax_errors, 1)

    def test_ignores_prose_panels_and_widgets(self):
        self.assertTrue(self.plugin.wants(View('x')))
        self.assertFalse(self.plugin.wants(View('x', scope='text.plain')))
        self.assertFalse(self.plugin.wants(View('x', element='console:input')))
        self.assertFalse(self.plugin.wants(View('x', is_widget=True)))

    def test_line_limit_uses_widest_ruler(self):
        self.assertEqual(self.plugin.line_limit(View('', rulers=[[72, 'solid'], 79])), 79)
        self.assertEqual(self.plugin.line_limit(View('')), 100)
        self.sublime.settings['max_line_length'] = 120
        self.assertEqual(self.plugin.line_limit(View('', rulers=[79])), 120)

    def test_chimes_when_the_mood_changes_or_on_save(self):
        clean = View('x = 1\n')
        broken = View('x = (\n')
        listen = self.plugin.conductor.listen
        listen(clean)
        listen(clean)
        listen(broken)
        listen(broken, saved=True)
        self.assertEqual(len(self.chimes), 3)
        self.assertEqual(clean.status['synesthesia'], '♪ radiant (1.00)')
        self.assertEqual(broken.status['synesthesia'], '♪ uneasy (0.40)')

    def test_ambient_mode_leaves_the_sound_to_the_drone(self):
        self.sublime.settings['mode'] = 'ambient'
        with mock.patch.object(self.plugin, 'Drone') as drone:
            self.plugin.conductor.configure()
            self.plugin.conductor.listen(View('x = 1\n'))
        drone.return_value.start.assert_called_once()
        self.assertEqual(self.chimes, [])
        self.assertEqual(self.plugin.conductor.report.health, 1.0)

    def test_toggle(self):
        command = self.plugin.SynesthesiaToggleCommand()
        command.run()
        self.assertFalse(self.sublime.settings['enabled'])
        self.plugin.conductor.listen(View('x = (\n'))
        self.assertEqual(self.chimes, [])
        command.run()
        self.assertTrue(command.is_checked())


if __name__ == '__main__':
    unittest.main()
