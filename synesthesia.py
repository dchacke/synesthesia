"""Synesthesia: hear the state of your code.

Each source file gets a health score from the syntax errors its syntax
definition flags, its unbalanced brackets, and how tidy it is. Synesthesia
plays that score, either as an ambient drone that drifts between radiant and
haunted as you type, or as a short chime whenever the score changes.
"""

import html
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import sublime
import sublime_plugin

from .core import analysis, synth
from .core.player import Player

SETTINGS = 'Synesthesia.sublime-settings'
STATUS_KEY = 'synesthesia'
RENDER_LEAD = 2.5  # seconds before an ambient segment is due to start rendering it

conductor = None


def settings():
    return sublime.load_settings(SETTINGS)


def cache_dir():
    return os.path.join(sublime.cache_path(), 'Synesthesia')


def plugin_loaded():
    global conductor
    # Renders from an older version of the synth would otherwise linger.
    shutil.rmtree(cache_dir(), ignore_errors=True)
    conductor = Conductor()
    settings().add_on_change(STATUS_KEY, conductor.configure)
    conductor.configure()


def plugin_unloaded():
    settings().clear_on_change(STATUS_KEY)
    if conductor:
        conductor.shutdown()


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
    ignored = view.find_by_selector(s.get('ignore_selector', 'string, comment'))
    comments = '\n'.join(view.substr(r) for r in view.find_by_selector('comment'))
    errors = view.find_by_selector(s.get('error_selector', 'invalid - invalid.deprecated'))
    return analysis.examine(
        text,
        code=analysis.mask(text, [(r.begin(), r.end()) for r in ignored]),
        comments=comments,
        syntax_errors=len(errors),
        tab_size=view.settings().get('tab_size', 4),
        max_line_length=line_limit(view),
        max_nesting=s.get('max_nesting', 4),
        check_brackets=s.get('check_brackets', True),
    )


def describe(report):
    return '♪ {} ({:.2f})'.format(synth.mood(report.health)[0], report.health)


def step(health):
    return round(health * synth.LEVELS)


class Conductor:
    """Keeps the latest score and turns it into sound."""

    def __init__(self):
        self.report = None
        self.chime_player = Player()
        self.drone = None
        # One worker renders chimes in order; `ticket` lets newer requests
        # make older, not yet played ones obsolete.
        self.renderer = ThreadPoolExecutor(max_workers=1)
        self.ticket = 0

    def configure(self):
        s = settings()
        enabled = s.get('enabled', True)
        ambient = enabled and s.get('mode', 'ambient') == 'ambient'
        if ambient and self.drone is None:
            self.drone = Drone(self)
            self.drone.start()
        elif not ambient and self.drone is not None:
            self.drone.stop()
            self.drone = None
        if not enabled:
            self.ticket += 1
            self.chime_player.stop()
            for window in sublime.windows():
                for view in window.views():
                    view.erase_status(STATUS_KEY)
        else:
            view = sublime.active_window().active_view()
            sublime.set_timeout_async(lambda: self.listen(view))

    def shutdown(self):
        self.ticket += 1
        if self.drone is not None:
            self.drone.stop()
        self.chime_player.stop()
        self.renderer.shutdown(wait=False)

    def listen(self, view, saved=False):
        """Score `view` and let the music follow."""
        if not settings().get('enabled', True) or not wants(view):
            return
        report = measure(view)
        previous, self.report = self.report, report
        if settings().get('show_status', True):
            view.set_status(STATUS_KEY, describe(report))
        if settings().get('mode', 'ambient') != 'chime':
            return  # the drone picks up the new score by itself
        if saved or previous is None or step(previous.health) != step(report.health):
            self.chime(report.health)

    def render(self, health, style, seed=0):
        volume = settings().get('ambient_volume', 0.25) if style == 'pad' else settings().get('volume', 0.5)
        return synth.render_file(health, style, seed, synth.clamp(volume), cache_dir())

    def chime(self, health):
        self.perform([(health, 0)])

    def perform(self, phrases):
        """Play chimes for each (health, pause) in turn, unless something
        newer comes along."""
        self.ticket += 1
        ticket = self.ticket

        def job():
            try:
                for health, pause in phrases:
                    path = self.render(health, 'chime')
                    if ticket != self.ticket:
                        return
                    self.chime_player.play(path, solo=True)
                    time.sleep(pause)
            except Exception as e:
                report_failure(e)

        self.renderer.submit(job)


class Drone(threading.Thread):
    """Plays overlapping pad segments, each rendered from the latest score,
    so the drone crossfades into whatever the code sounds like now."""

    def __init__(self, conductor):
        super().__init__(name='Synesthesia drone', daemon=True)
        self.conductor = conductor
        self.player = Player()
        self.stopped = threading.Event()

    def stop(self):
        self.stopped.set()
        self.player.stop()

    def run(self):
        stride = synth.PAD_SECONDS - synth.PAD_FADE
        due = time.monotonic()
        segment = 0
        while not self.stopped.is_set():
            report = self.conductor.report
            if report is None:
                self.stopped.wait(0.5)
                due = time.monotonic()
                continue
            try:
                path = self.conductor.render(report.health, 'pad', seed=segment % 3)
                if self.stopped.wait(max(0.0, due - time.monotonic())):
                    break
                self.player.play(path)
            except Exception as e:
                report_failure(e)
                self.stopped.wait(30)
                continue
            segment += 1
            due = max(due, time.monotonic()) + stride
            self.stopped.wait(max(0.0, due - RENDER_LEAD - time.monotonic()))


def report_failure(error):
    print('Synesthesia:', error)
    sublime.status_message('Synesthesia: {}'.format(error))


class SynesthesiaListener(sublime_plugin.EventListener):
    def __init__(self):
        self.edits = {}

    def on_activated_async(self, view):
        if conductor:
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
                                  settings().get('idle_delay', 1000))

    def settle(self, view, count):
        if conductor and self.edits.get(view.id()) == count:
            conductor.listen(view)

    def on_close(self, view):
        self.edits.pop(view.id(), None)


class SynesthesiaToggleCommand(sublime_plugin.ApplicationCommand):
    def run(self):
        s = settings()
        s.set('enabled', not s.get('enabled', True))
        sublime.save_settings(SETTINGS)
        sublime.status_message('Synesthesia {}'.format('on' if s.get('enabled') else 'off'))

    def is_checked(self):
        return settings().get('enabled', True)


class SynesthesiaModeCommand(sublime_plugin.ApplicationCommand):
    def run(self, mode):
        s = settings()
        s.set('mode', mode)
        s.set('enabled', True)
        sublime.save_settings(SETTINGS)

    def is_checked(self, mode):
        return settings().get('mode', 'ambient') == mode


class SynesthesiaPlayCommand(sublime_plugin.TextCommand):
    """Chime the current file's score right now."""

    def run(self, edit):
        if not wants(self.view):
            sublime.status_message('Synesthesia only listens to views matching "{}"'.format(
                settings().get('selector', 'source')))
            return
        report = measure(self.view)
        sublime.status_message(describe(report))
        conductor.chime(report.health)


class SynesthesiaExplainCommand(sublime_plugin.TextCommand):
    """Show what went into the current file's score."""

    def run(self, edit):
        if not wants(self.view):
            sublime.status_message('Synesthesia only listens to views matching "{}"'.format(
                settings().get('selector', 'source')))
            return
        r = measure(self.view)
        rows = [
            ('Syntax errors', r.syntax_errors),
            ('Unbalanced brackets', r.unbalanced_brackets),
            ('Lines too long', r.long_lines),
            ('Lines nested too deep', r.deep_lines),
            ('Lines with trailing whitespace', r.trailing_whitespace),
            ('Tabs and spaces mixed', 'yes' if r.mixed_indentation else 'no'),
            ('TODO, FIXME, XXX, HACK', r.markers),
        ]
        content = '<body><b>{}</b> &nbsp;health {:.2f}<br><br>{}</body>'.format(
            html.escape(synth.mood(r.health)[0]), r.health,
            '<br>'.join('{}: {}'.format(html.escape(k), v) for k, v in rows))
        self.view.show_popup(content, sublime.HIDE_ON_MOUSE_MOVE_AWAY, max_width=400)


class SynesthesiaDemoCommand(sublime_plugin.ApplicationCommand):
    """Play every mood from haunted to radiant."""

    def run(self):
        healths = (0.1, 0.35, 0.55, 0.75, 1.0)
        sublime.status_message('Synesthesia: ' + ' → '.join(synth.mood(h)[0] for h in healths))
        conductor.perform([(h, synth.chime_seconds(h) + 0.4) for h in healths])
