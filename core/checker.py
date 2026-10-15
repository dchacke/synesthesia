"""Ask a language's own parser whether code parses. Sublime's syntax
definitions highlight leniently and miss a lot of broken code, such as a
Ruby class without its `end`."""

import os
import subprocess
import sys

FALLBACK_DIRS = ('/opt/homebrew/bin', '/usr/local/bin')

# Keeps Windows from flashing a console window for every process started.
NO_WINDOW = {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}


def parses(command, text, path=None, timeout=5.0):
    """True if `command` accepts `text` on stdin, False if it rejects it,
    None if it couldn't run at all."""
    env = dict(os.environ)
    if path:
        env['PATH'] = path
    try:
        result = subprocess.run(
            command, input=text.encode('utf-8'), stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=timeout, env=env, **NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.returncode == 0


def login_path():
    """The PATH a login shell sets up. Apps started from the Dock get a bare
    one, without Homebrew, rvm, nvm and the like."""
    shell = os.environ.get('SHELL') or '/bin/sh'
    try:
        out = subprocess.run(
            [shell, '-l', '-i', '-c', 'printf "\\n%s" "$PATH"'], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10, **NO_WINDOW).stdout
        found = out.decode('utf-8', 'replace').rsplit('\n', 1)[-1].strip()
    except (OSError, subprocess.SubprocessError):
        found = ''
    current = os.environ.get('PATH', '').split(os.pathsep)
    dirs = found.split(os.pathsep) + current + list(FALLBACK_DIRS)
    return os.pathsep.join(dict.fromkeys(d for d in dirs if d))
