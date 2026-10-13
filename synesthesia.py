"""Synesthesia: hear the state of your code.

Scores the current file, or every source file in the open folders, from
beautiful to cursed, and plays it on recorded instruments. The code is the
score: the music walks through it line by line, in the stage's scale,
instruments and tempo, and jumps to wherever the code just changed. Changes
also get a short accent, rising if things got better and falling if worse.
"""

import html
import os
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

from .core import analysis, checker, music, score  # noqa: E402
from .core.player import Player  # noqa: E402
from .core.sampler import Library  # noqa: E402
from .core.watcher import Watcher  # noqa: E402

SETTINGS = 'Synesthesia.sublime-settings'
STATUS_KEY = 'synesthesia'
PANEL = 'synesthesia'
SOUND_VERSION = 3  # bump when the music changes, so stale renders are dropped
ACCENT_GAP = 0.12  # seconds between accents, so a burst of changes cascades
EARLY_BAR_GAP = 0.8  # when the stage changes, wait at least this long after the last bar
BRANCHES = ('keyword.control.conditional, keyword.control.loop, '
            'keyword.control.exception.catch, keyword.operator.logical')

conductor = None
library = None  # the recorded instruments
search_path = None  # where to find syntax checkers; see checker.login_path
unrunnable = set()  # checkers that failed to start, so we only say so once


def settings():
    return sublime.load_settings(SETTINGS)


def cache_root():
    return os.path.join(sublime.cache_path(), 'Synesthesia')


def cache_dir():
    return os.path.join(cache_root(), 'v{}'.format(SOUND_VERSION))


def plugin_loaded():
    global conductor, library
    library = Library(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'samples'))

    def find_checkers():
        global search_path
        search_path = checker.login_path()
    threading.Thread(target=find_checkers, daemon=True).start()
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


def parses(view, text):
    """Whether the language's own parser accepts `text`, or None if no
    checker is set up for its language or the checker can't run."""
    for entry in settings().get('syntax_checkers', []):
        if view.match_selector(0, entry['selector']):
            result = checker.parses(entry['command'], text, search_path)
            if result is None and entry['command'][0] not in unrunnable:
                unrunnable.add(entry['command'][0])
                print('Synesthesia: could not run {}, so {} files are not checked'.format(
                    entry['command'][0], entry['selector']))
            return result
    return None


def measure(view):
    s = settings()
    text = view.substr(sublime.Region(0, view.size()))

    def lines(selector):
        return [view.rowcol(r.begin())[0] for r in view.find_by_selector(selector)]

    ignored = view.find_by_selector(s.get('ignore_selector', 'string, comment'))
    code = analysis.mask(text, [(r.begin(), r.end()) for r in ignored])
    errors = lines(s.get('error_selector', 'invalid - invalid.deprecated'))
    functions = lines(s.get('function_selector', 'entity.name.function'))
    tab_size = view.settings().get('tab_size', 4)
    report = analysis.examine(
        text,
        code=code,
        comments='\n'.join(view.substr(r) for r in view.find_by_selector('comment')),
        syntax_errors=len(errors),
        functions=functions,
        branches=lines(s.get('branch_selector', BRANCHES)),
        tab_size=tab_size,
        limits=analysis.Limits(
            line_length=line_limit(view),
            nesting=s.get('max_nesting', 4),
            function_lines=s.get('max_function_lines', 40),
            branches=s.get('max_branches', 10)),
        check_brackets=s.get('check_brackets', True),
        broken=parses(view, text) is False,
    )
    report.sheet = score.read(text, code, functions, errors, tab_size)
    return report


def modified(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


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
        self.sheet = None  # the code the music plays; see score.py
        self.focus = None  # a line the band should jump to, where the code just changed
        self.playing = None  # the view id or path the sheet comes from
        self.project = {}  # path -> report, in project mode
        self.lock = threading.Lock()  # around what's playing, which the band changes too
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
        self.follow(view.id(), report.sheet, previous.sheet if previous else None)
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

        def changed(reports, changes, initial, edited=False):
            if not edited:  # edits arrive on another thread, which mustn't touch the panel
                window.destroy_output_panel(PANEL)  # frees its undo history
            if initial:
                print('Synesthesia: listening to {} source files in {}'.format(
                    len(reports), ', '.join(folders)))
            self.hear_project(reports, changes, initial, edited)

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

    def hear_project(self, reports, changes, initial, edited=False):
        """`edited` means the changes come from typing rather than from disk;
        those are only worth an accent when the score moves."""
        report = analysis.combine(reports.values())
        if report is None:
            self.status('♪ no source files in this project')
            return
        self.project = reports
        for path, old, new in changes:
            if new is None:
                continue  # a deleted file has nothing to say
            self.follow(path, new.sheet, old.sheet if old else None)
            if edited and old is not None and abs(new.health - old.health) < 0.02:
                continue
            self.accent(new.health, direction(old.health, new.health) if old else 'same')
        if self.playing not in reports:  # at first, or when its file is gone
            latest = max(reports, key=modified)  # the file worked on last
            self.follow(latest, reports[latest].sheet, None)
        self.hear(report, ' · project')

    # Sound

    def follow(self, source, sheet, old_sheet):
        """Play `sheet` from now on, starting where it differs from
        `old_sheet`, or from the top if it comes from somewhere new."""
        with self.lock:
            if source != self.playing:
                self.focus = 0
            elif old_sheet is not None:
                changed = score.first_difference(old_sheet, sheet)
                if changed is not None:
                    self.focus = changed
            self.playing = source
            self.sheet = sheet

    def advance(self):
        """At the end of a file, move on to the next one in the project. In
        file mode the band simply goes back to the top."""
        with self.lock:
            files = sorted(self.project) if self.watcher is not None else []
            if files:
                i = files.index(self.playing) + 1 if self.playing in self.project else 0
                self.playing = files[i % len(files)]
                self.sheet = self.project[self.playing].sheet

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
        """In chime mode, play a bar when the stage changes."""
        try:
            _, path = self.bar(self.sheet, self.focus or 0, stage)
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
                path = music.accent_file(library, stage, way, self.volume('volume', 0.5), cache_dir())
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

    def bar(self, sheet, cursor, stage):
        """Render a bar of `sheet`. Returns (seconds until the next bar, path)."""
        return music.bar_file(library, sheet, cursor, stage, self.volume('ambient_volume', 0.3), cache_dir())

    def volume(self, key, default):
        return min(max(settings().get(key, default), 0.0), 1.0)

    def warm_up(self):
        """Render the accents ahead of time, nearest the current stage first,
        so changes are heard without delay."""
        current = music.stage(self.report.health) if self.report else 0
        try:
            for stage in sorted(range(len(music.STAGES)), key=lambda i: abs(i - current)):
                for way in ('up', 'down', 'same'):
                    music.accent_file(library, stage, way, self.volume('volume', 0.5), cache_dir())
        except Exception as e:
            report_failure(e)

    def status(self, text):
        view = sublime.active_window().active_view()
        if view is not None:
            view.set_status(STATUS_KEY, text)


class Band(threading.Thread):
    """The ambient stream: walks through the code a bar at a time in the
    current stage, rendering each bar while the one before it plays, and in
    project mode on through every file. When the stage changes the next bar
    starts right away; when the code changes the band moves to where it
    changed."""

    def __init__(self, conductor):
        super().__init__(name='Synesthesia band', daemon=True)
        self.conductor = conductor
        self.player = Player()
        self.stopped = threading.Event()
        self.woken = threading.Event()
        self.cursor = 0

    def stop(self):
        self.stopped.set()
        self.woken.set()
        self.player.stop()

    def hurry(self):
        self.woken.set()

    def next_bar(self):
        """What to play next: (sheet, cursor, stage), or None for silence."""
        c = self.conductor
        if c.report is None:
            return None
        if c.focus is not None:
            self.cursor, c.focus = max(0, c.focus - 2), None  # lead in to the change
        if self.cursor >= len(c.sheet or []):  # the end of this file
            c.advance()
            self.cursor = 0
        return c.sheet or [], self.cursor, music.stage(c.report.health)

    def run(self):
        ready = None  # (sheet, cursor, stage), seconds, path
        while not self.stopped.is_set():
            self.woken.clear()
            plan = self.next_bar()
            if plan is None:
                self.woken.wait(0.5)
                continue
            try:
                if ready is None or ready[0] != plan:
                    ready = (plan,) + self.conductor.bar(*plan)
                if self.next_bar() != plan:
                    ready = None
                    continue  # the code changed while the bar was rendering
                self.player.play(ready[2])
                started, seconds = time.monotonic(), ready[1]
                self.cursor = plan[1] + music.STEPS
                upcoming = self.next_bar()
                ready = (upcoming,) + self.conductor.bar(*upcoming)
            except Exception as e:
                report_failure(e)
                ready = None
                self.stopped.wait(30)
                continue
            if self.woken.wait(max(0.0, started + seconds - time.monotonic())) and not self.stopped.is_set():
                self.stopped.wait(max(0.0, EARLY_BAR_GAP - (time.monotonic() - started)))


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
    """Play a bar of the current code right now."""

    def run(self, edit):
        report = conductor.report if project_mode() else None
        if report is None:
            if not wants(self.view):
                sublime.status_message('Synesthesia only listens to views matching "{}"'.format(
                    settings().get('selector', 'source')))
                return
            report = measure(self.view)
            conductor.follow(self.view.id(), report.sheet, None)
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
            ('Files that don\'t parse' if project else 'Doesn\'t parse', r.broken if project else
             ('yes' if r.broken else 'no')),
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
    """Play the current code in every stage, from beautiful to cursed."""

    def run(self):
        sublime.status_message('Synesthesia: ' + ' → '.join(s.name for s in music.STAGES))

        def tour():
            try:
                for stage in range(len(music.STAGES)):
                    seconds, path = conductor.bar(conductor.sheet, 0, stage)
                    conductor.accent_player.play(path)
                    time.sleep(seconds + 1.0)
            except Exception as e:
                report_failure(e)

        conductor.renderer.submit(tour)
