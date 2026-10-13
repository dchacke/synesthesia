"""Synesthesia: hear the state of your code.

Scores the current file, or every source file in the open folders, from
beautiful to cursed, and plays that score: an ambient stream of phrases in
the current stage's harmony and instruments, plus a short accent whenever
something changes, rising if it got better and falling if it got worse.
"""

import html
import os
import random
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import sublime
import sublime_plugin

# Sublime reloads this file when it changes, but not the modules it imports.
# Forget them so that they are reloaded too.
for _module in [m for m in sys.modules if m.startswith(__package__ + '.core')]:
    del sys.modules[_module]

from .core import analysis, music  # noqa: E402
from .core.player import Player  # noqa: E402
from .core.watcher import Watcher  # noqa: E402

SETTINGS = 'Synesthesia.sublime-settings'
STATUS_KEY = 'synesthesia'
PANEL = 'synesthesia'
SOUND_VERSION = 2  # bump when the music changes, so stale renders are dropped
ACCENT_GAP = 0.12  # seconds between accents, so a burst of changes cascades
EARLY_BAR_GAP = 0.8  # when the stage changes, wait at least this long after the last bar
BRANCHES = ('keyword.control.conditional, keyword.control.loop, '
            'keyword.control.exception.catch, keyword.operator.logical')

conductor = None


def settings():
    return sublime.load_settings(SETTINGS)


def cache_root():
    return os.path.join(sublime.cache_path(), 'Synesthesia')


def cache_dir():
    return os.path.join(cache_root(), 'v{}'.format(SOUND_VERSION))


def plugin_loaded():
    global conductor
    # Renders from other versions of the music would otherwise linger.
    root = cache_root()
    if os.path.isdir(root):
        for entry in os.listdir(root):
            if entry != os.path.basename(cache_dir()):
                path = os.path.join(root, entry)
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    os.remove(path)
    conductor = Conductor()
    settings().add_on_change(STATUS_KEY, conductor.configure)
    conductor.configure()


def plugin_unloaded():
    settings().clear_on_change(STATUS_KEY)
    if conductor:
        conductor.shutdown()


def project_mode():
    return settings().get('listen_to', 'file') == 'project'


def wants(view):
    """Whether `view` is code Synesthesia should listen to."""
    if view is None or not view.is_valid() or view.element() is not None:
        return False
    if view.settings().get('is_widget'):
        return False
    if view.size() > settings().get('max_file_size', 2000000):
        return False
    return view.match_selector(0, settings().get('selector', 'source'))


def line_limit(view):
    limit = settings().get('max_line_length')
    if limit:
        return limit
    rulers = view.settings().get('rulers') or []
    # Rulers are either columns or [column, style] pairs.
    columns = [r[0] if isinstance(r, list) else r for r in rulers]
    return max(columns) if columns else 100


def measure(view):
    s = settings()
    text = view.substr(sublime.Region(0, view.size()))

    def lines(selector):
        return [view.rowcol(r.begin())[0] for r in view.find_by_selector(selector)]

    ignored = view.find_by_selector(s.get('ignore_selector', 'string, comment'))
    return analysis.examine(
        text,
        code=analysis.mask(text, [(r.begin(), r.end()) for r in ignored]),
        comments='\n'.join(view.substr(r) for r in view.find_by_selector('comment')),
        syntax_errors=len(view.find_by_selector(s.get('error_selector', 'invalid - invalid.deprecated'))),
        functions=lines(s.get('function_selector', 'entity.name.function')),
        branches=lines(s.get('branch_selector', BRANCHES)),
        tab_size=view.settings().get('tab_size', 4),
        limits=analysis.Limits(
            line_length=line_limit(view),
            nesting=s.get('max_nesting', 4),
            function_lines=s.get('max_function_lines', 40),
            branches=s.get('max_branches', 10)),
        check_brackets=s.get('check_brackets', True),
    )


def describe(report, scope=''):
    return '♪ {} ({:.2f}){}'.format(music.name(report.health), report.health, scope)


def direction(old, new):
    if new > old + 0.005:
        return 'up'
    if new < old - 0.005:
        return 'down'
    return 'same'


class Conductor:
    """Keeps the latest score and turns it into sound."""

    def __init__(self):
        self.report = None  # what the music describes right now
        self.scores = {}  # view id -> last report, for telling which way a file moved
        self.band = None
        self.watcher = None
        self.watched = None  # (window id, folders) the watcher covers
        self.accent_player = Player()
        self.accents = ThreadPoolExecutor(max_workers=1)
        self.renderer = ThreadPoolExecutor(max_workers=1)
        self.warmer = ThreadPoolExecutor(max_workers=1)
        self.next_accent = 0.0
        self.queued_accents = 0

    def configure(self):
        s = settings()
        enabled = s.get('enabled', True)
        ambient = enabled and s.get('mode', 'ambient') == 'ambient'
        if ambient and self.band is None:
            self.band = Band(self)
            self.band.start()
        elif not ambient and self.band is not None:
            self.band.stop()
            self.band = None
        if not enabled:
            self.stop_watching()
            self.accent_player.stop()
            for window in sublime.windows():
                for view in window.views():
                    view.erase_status(STATUS_KEY)
            return
        self.warmer.submit(self.warm_up)
        window = sublime.active_window()
        if project_mode() and window.folders():
            self.watch(window)
        else:
            self.stop_watching()
            view = window.active_view()
            sublime.set_timeout_async(lambda: self.listen(view))

    def shutdown(self):
        self.stop_watching()
        if self.band is not None:
            self.band.stop()
        self.accent_player.stop()
        self.accents.shutdown(wait=False)
        self.renderer.shutdown(wait=False)
        self.warmer.shutdown(wait=False)

    # File mode

    def listen(self, view, saved=False):
        """Score `view` and let the music follow."""
        if not settings().get('enabled', True) or not wants(view):
            return
        if self.watcher is not None:
            # Unsaved edits count toward the project; saved ones reach the
            # watcher from disk.
            if view.file_name() and not saved:
                self.watcher.update(view.file_name(), measure(view))
            return
        report = measure(view)
        previous = self.scores.get(view.id())
        self.scores[view.id()] = report
        if settings().get('show_status', True):
            view.set_status(STATUS_KEY, describe(report))
        if previous is not None and (saved or abs(report.health - previous.health) >= 0.02):
            self.accent(report.health, direction(previous.health, report.health))
        self.hear(report)

    def forget(self, view):
        self.scores.pop(view.id(), None)
        if self.watcher is not None and view.file_name() and view.is_dirty():
            self.watcher.refresh(view.file_name())  # its unsaved edits are gone

    # Project mode

    def watch(self, window):
        folders = window.folders()
        if self.watched == (window.id(), folders):
            return
        self.stop_watching()
        s = settings()
        syntaxes = {}

        def wanted(path):
            ext = os.path.splitext(path)[1].lower()
            if not ext or '.min.' in os.path.basename(path):
                return False
            if ext not in syntaxes:
                syntax = sublime.find_syntax_for_file('file' + ext)
                syntaxes[ext] = bool(syntax) and sublime.score_selector(
                    syntax.scope, s.get('selector', 'source')) > 0
            return syntaxes[ext]

        def measure_file(path, text):
            syntax = sublime.find_syntax_for_file(path, text.split('\n', 1)[0])
            if syntax is None:
                return None
            panel = window.find_output_panel(PANEL) or window.create_output_panel(PANEL, True)
            panel.settings().set('is_widget', True)
            if panel.syntax() != syntax:
                panel.assign_syntax(syntax)
            panel.run_command('synesthesia_fill', {'text': text})
            return measure(panel)

        def progress(done, total):
            if done % 25 == 0:
                self.status('♪ listening to the project… {}/{}'.format(done, total))

        def changed(reports, changes, initial):
            window.destroy_output_panel(PANEL)  # frees its undo history
            if initial:
                print('Synesthesia: listening to {} source files in {}'.format(
                    len(reports), ', '.join(folders)))
            self.hear_project(reports, changes, initial)

        self.watcher = Watcher(
            folders, wanted, measure_file, changed, progress, report_failure,
            interval=s.get('poll_interval', 0.5),
            exclude=s.get('project_exclude', []),
            max_files=s.get('max_project_files', 2000),
            max_bytes=s.get('max_file_size', 2000000))
        self.watched = (window.id(), folders)
        self.watcher.start()

    def stop_watching(self):
        if self.watcher is not None:
            self.watcher.stop()
        self.watcher = None
        self.watched = None

    def hear_project(self, reports, changes, initial):
        report = analysis.combine(reports.values())
        if report is None:
            self.status('♪ no source files in this project')
            return
        if not initial:
            for path, old, new in changes:
                if new is not None:  # a deleted file has nothing to say
                    self.accent(new.health, direction(old.health, new.health) if old else 'same')
        self.hear(report, ' · project')

    # Sound

    def hear(self, report, scope=''):
        previous, self.report = self.report, report
        if scope and settings().get('show_status', True):
            self.status(describe(report, scope))
        stage = music.stage(report.health)
        if previous is not None and music.stage(previous.health) == stage:
            return
        if self.band is not None:
            self.band.hurry()
        elif previous is not None and settings().get('enabled', True):
            self.renderer.submit(self.phrase, stage)

    def phrase(self, stage):
        """In chime mode, play a whole bar when the stage changes."""
        try:
            _, path = self.render('bar', stage, random.randrange(music.VARIANTS))
            self.accent_player.play(path)
        except Exception as e:
            report_failure(e)

    def accent(self, health, way):
        if self.queued_accents >= 6:
            return  # a flood of changes; the ones already queued tell the story
        self.queued_accents += 1
        stage = music.stage(health)

        def job():
            try:
                _, path = self.render(way, stage)
                wait = self.next_accent - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                self.accent_player.play(path)
                self.next_accent = time.monotonic() + ACCENT_GAP
            except Exception as e:
                report_failure(e)
            finally:
                self.queued_accents -= 1

        self.accents.submit(job)

    def render(self, kind, stage, variant=0):
        s = settings()
        volume = s.get('ambient_volume', 0.3) if kind == 'bar' else s.get('volume', 0.5)
        return music.render_file(kind, stage, variant, min(max(volume, 0.0), 1.0), cache_dir())

    def warm_up(self):
        """Render everything ahead of time, nearest the current stage first,
        so changes are heard without delay."""
        current = music.stage(self.report.health) if self.report else 0
        order = sorted(range(len(music.STAGES)), key=lambda i: abs(i - current))
        try:
            for stage in order:
                for kind in ('up', 'down', 'same'):
                    self.render(kind, stage)
                self.render('bar', stage, 0)
            for stage in order:
                for variant in range(1, music.VARIANTS):
                    self.render('bar', stage, variant)
        except Exception as e:
            report_failure(e)

    def status(self, text):
        view = sublime.active_window().active_view()
        if view is not None:
            view.set_status(STATUS_KEY, text)


class Band(threading.Thread):
    """The ambient stream: one bar after another in the current stage. When
    the stage changes, the next bar starts right away."""

    def __init__(self, conductor):
        super().__init__(name='Synesthesia band', daemon=True)
        self.conductor = conductor
        self.player = Player()
        self.stopped = threading.Event()
        self.woken = threading.Event()

    def stop(self):
        self.stopped.set()
        self.woken.set()
        self.player.stop()

    def hurry(self):
        self.woken.set()

    def run(self):
        variant = 0
        while not self.stopped.is_set():
            self.woken.clear()
            report = self.conductor.report
            if report is None:
                self.woken.wait(0.5)
                continue
            stage = music.stage(report.health)
            try:
                length, path = self.conductor.render('bar', stage, variant)
                if music.stage(self.conductor.report.health) != stage:
                    continue  # the code changed while the bar was rendering
                self.woken.clear()
                self.player.play(path)
            except Exception as e:
                report_failure(e)
                self.stopped.wait(30)
                continue
            started = time.monotonic()
            if self.woken.wait(length) and not self.stopped.is_set():
                self.stopped.wait(max(0.0, EARLY_BAR_GAP - (time.monotonic() - started)))
            variant = random.choice([v for v in range(music.VARIANTS) if v != variant])


def report_failure(error):
    print('Synesthesia:', error)
    sublime.status_message('Synesthesia: {}'.format(error))


class SynesthesiaListener(sublime_plugin.EventListener):
    def __init__(self):
        self.edits = {}

    def on_activated_async(self, view):
        if conductor is None:
            return
        window = view.window()
        if project_mode() and window is not None and window.folders():
            conductor.watch(window)  # follows you between windows
            if conductor.report is not None and settings().get('show_status', True):
                view.set_status(STATUS_KEY, describe(conductor.report, ' · project'))
        else:
            conductor.listen(view)

    def on_post_save_async(self, view):
        if conductor:
            conductor.listen(view, saved=True)

    def on_modified_async(self, view):
        # Wait for a pause in typing rather than reacting to every keystroke.
        key = view.id()
        count = self.edits.get(key, 0) + 1
        self.edits[key] = count
        sublime.set_timeout_async(lambda: self.settle(view, count),
                                  settings().get('idle_delay', 300))

    def settle(self, view, count):
        if conductor and self.edits.get(view.id()) == count:
            conductor.listen(view)

    def on_close(self, view):
        self.edits.pop(view.id(), None)
        if conductor:
            conductor.forget(view)


class SynesthesiaFillCommand(sublime_plugin.TextCommand):
    """Replace the whole buffer; used to score files that aren't open."""

    def run(self, edit, text):
        self.view.replace(edit, sublime.Region(0, self.view.size()), text)


class SynesthesiaToggleCommand(sublime_plugin.ApplicationCommand):
    def run(self):
        s = settings()
        s.set('enabled', not s.get('enabled', True))
        sublime.save_settings(SETTINGS)
        sublime.status_message('Synesthesia {}'.format('on' if s.get('enabled') else 'off'))

    def is_checked(self):
        return settings().get('enabled', True)


class SynesthesiaSetCommand(sublime_plugin.ApplicationCommand):
    """Set a setting from the menu or command palette, turning Synesthesia on."""

    def run(self, key, value):
        s = settings()
        s.set(key, value)
        s.set('enabled', True)
        sublime.save_settings(SETTINGS)

    def is_checked(self, key, value):
        return settings().get(key) == value


class SynesthesiaPlayCommand(sublime_plugin.TextCommand):
    """Play a bar for the current score right now."""

    def run(self, edit):
        report = conductor.report if project_mode() else None
        if report is None:
            if not wants(self.view):
                sublime.status_message('Synesthesia only listens to views matching "{}"'.format(
                    settings().get('selector', 'source')))
                return
            report = measure(self.view)
        sublime.status_message(describe(report))
        conductor.renderer.submit(conductor.phrase, music.stage(report.health))


class SynesthesiaExplainCommand(sublime_plugin.TextCommand):
    """Show what went into the score."""

    def run(self, edit):
        project = project_mode() and conductor.report is not None
        if not project and not wants(self.view):
            sublime.status_message('Synesthesia only listens to views matching "{}"'.format(
                settings().get('selector', 'source')))
            return
        r = conductor.report if project else measure(self.view)
        rows = [
            ('Syntax errors', r.syntax_errors),
            ('Unbalanced brackets', r.unbalanced_brackets),
            ('Long functions', r.long_functions),
            ('Functions with too many branches', r.complex_functions),
            ('Lines nested too deep', r.deep_lines),
            ('Duplicated lines', r.duplicate_lines),
            ('Lines too long', r.long_lines),
            ('Lines with trailing whitespace', r.trailing_whitespace),
            ('Tabs and spaces mixed', 'yes' if r.mixed_indentation else 'no'),
            ('TODO, FIXME, XXX, HACK', r.markers),
        ]
        content = '<body><b>{}</b>{} &nbsp;health {:.2f}, quality {:.2f}<br><br>{}</body>'.format(
            html.escape(music.name(r.health)), ' (project)' if project else '', r.health, r.quality,
            '<br>'.join('{}: {}'.format(html.escape(k), v) for k, v in rows))
        self.view.show_popup(content, sublime.HIDE_ON_MOUSE_MOVE_AWAY, max_width=480)


class SynesthesiaDemoCommand(sublime_plugin.ApplicationCommand):
    """Play every stage from beautiful to cursed."""

    def run(self):
        sublime.status_message('Synesthesia: ' + ' → '.join(name for _, name in music.STAGES))

        def tour():
            try:
                for stage in range(len(music.STAGES)):
                    length, path = conductor.render('bar', stage, 0)
                    conductor.accent_player.play(path)
                    time.sleep(length * 1.4)
            except Exception as e:
                report_failure(e)

        conductor.renderer.submit(tour)
