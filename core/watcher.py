"""Keep scores for every source file in a set of folders up to date by
polling for files that appear, change or vanish.

Nothing in here imports sublime; the plugin passes in how to recognize and
measure source files.
"""

import fnmatch
import os
import subprocess
import threading
import time

from .checker import NO_WINDOW

LIST_EVERY = 2.0  # seconds between looking for new and deleted files


def list_files(folder, exclude):
    """Files in `folder` worth watching. In a git repository that means
    tracked and untracked files git doesn't ignore; elsewhere, everything
    not matching `exclude`."""
    if os.path.isdir(os.path.join(folder, '.git')):
        try:
            out = subprocess.run(
                ['git', '-C', folder, 'ls-files', '-z',
                 '--cached', '--others', '--exclude-standard'],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=10, check=True, **NO_WINDOW).stdout
            return [os.path.join(folder, p) for p in out.decode('utf-8', 'replace').split('\0')
                    if p and not excluded(p, exclude)]
        except (OSError, subprocess.SubprocessError):
            pass
    found = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith('.') and not excluded(d, exclude)]
        found.extend(os.path.join(root, f) for f in files if not excluded(f, exclude))
    return found


def excluded(path, patterns):
    parts = path.replace('\\', '/').split('/')
    return any(fnmatch.fnmatch(part, pattern) for part in parts for pattern in patterns)


class Watcher(threading.Thread):
    """Calls `measure(path, text)` for every wanted file once, then again
    whenever it changes, and `changed(reports, changes, initial, edited)`
    after each round that changed something. `reports` maps paths to their
    latest reports; `changes` lists (path, old report or None, new report or
    None). The first call, after the initial scan, has `initial` set and no
    changes; calls caused by `update` have `edited` set. Errors go to
    `failed(error)` and the watcher carries on."""

    def __init__(self, folders, wanted, measure, changed, progress=None, failed=None,
                 interval=0.5, exclude=(), max_files=2000, max_bytes=1000000):
        super().__init__(name='Synesthete watcher', daemon=True)
        self.folders = list(folders)
        self.wanted = wanted
        self.measure = measure
        self.changed = changed
        self.progress = progress or (lambda done, total: None)
        self.failed = failed or (lambda error: None)
        self.interval = interval
        self.exclude = list(exclude)
        self.max_files = max_files
        self.max_bytes = max_bytes
        self.stopped = threading.Event()
        self.reports = {}
        self.ready = False
        self._lock = threading.Lock()
        self._stamps = {}
        self._paths = []
        self._listed = 0.0

    def stop(self):
        self.stopped.set()

    def run(self):
        while not self.stopped.is_set():
            try:
                if not self.ready or time.monotonic() - self._listed > LIST_EVERY:
                    self._list()
                self._poll(initial=not self.ready)
            except Exception as e:
                self.failed(e)
            self.stopped.wait(self.interval)

    def update(self, path, report):
        """Take a score measured elsewhere, such as from an unsaved view."""
        with self._lock:
            if not self.ready or path not in self._stamps:
                return
            old = self.reports.get(path)
            self.reports[path] = report
            reports = dict(self.reports)
        self.changed(reports, [(path, old, report)], initial=False, edited=True)

    def snapshot(self):
        """The latest reports, safely copied."""
        with self._lock:
            return dict(self.reports)

    def refresh(self, path):
        """Read `path` from disk again, as when unsaved changes are discarded."""
        with self._lock:
            self._stamps.pop(path, None)

    def _list(self):
        paths = []
        for folder in self.folders:
            paths.extend(p for p in list_files(folder, self.exclude) if self.wanted(p))
        self._paths = sorted(set(paths))[:self.max_files]
        self._listed = time.monotonic()

    def _poll(self, initial=False):
        changes = self._forget_vanished()
        due = self._due()
        for done, (path, stamp, size) in enumerate(due):
            if self.stopped.is_set():
                return
            if initial:
                self.progress(done, len(due))
            report = self._read(path, size)
            with self._lock:
                self._stamps[path] = stamp
                old = self.reports.pop(path, None)
                if report is not None:
                    self.reports[path] = report
            if report is not None or old is not None:
                changes.append((path, old, report))
        with self._lock:
            reports = dict(self.reports)
            self.ready = True
        if initial:
            self.changed(reports, [], initial=True)  # the first scan is a baseline, not news
        elif changes:
            self.changed(reports, changes, initial=False)

    def _forget_vanished(self):
        """Drop files that are gone, as changes to nothing."""
        current = set(self._paths)
        with self._lock:
            gone = [path for path in self.reports if path not in current]
            for path in gone:
                self._stamps.pop(path, None)
            return [(path, self.reports.pop(path), None) for path in gone]

    def _due(self):
        """(path, stamp, size) for files new or changed since last time."""
        due = []
        for path in self._paths:
            try:
                stat = os.stat(path)
            except OSError:
                continue
            stamp = (stat.st_mtime_ns, stat.st_size)
            if self._stamps.get(path) != stamp:
                due.append((path, stamp, stat.st_size))
        return due

    def _read(self, path, size):
        """Measure the file, or None if it's too big or unreadable."""
        if size > self.max_bytes:
            return None
        try:
            with open(path, encoding='utf-8') as f:
                return self.measure(path, f.read())
        except (OSError, UnicodeDecodeError):
            return None
        except Exception as e:  # one bad file shouldn't silence the rest
            self.failed(e)
            return None
