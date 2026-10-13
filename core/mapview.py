"""The map: a bird's-eye view of the code in a Sublime tab.

Every file is a tile, grouped by folder, as wide as the file is long and
colored by its stage. Files that just changed light up and fade, broken ones
carry a warning, and clicking a tile opens its file. Above the tiles, a
timeline of health with a tick for every change.
"""

import html
import json
import os

from . import music, picture

# Stage colors, from beautiful to cursed.
COLORS = ((76, 175, 80), (139, 195, 74), (205, 220, 57), (255, 193, 7),
          (255, 152, 0), (244, 67, 54), (106, 27, 154))
WAYS = {'up': (76, 175, 80), 'down': (244, 67, 54), 'same': (160, 160, 160)}
FADE = 10.0  # seconds a change stays lit
SPAN = 600.0  # seconds of history in the timeline
MAX_TILES = 800
NARROWEST, WIDEST = 48, 420  # px

# Sublime's HTML sizes inline blocks by their line height; height and
# vertical padding would spill over the rows above and below.
STYLE = '''
body { margin: 0; padding: 1rem 1.2rem; font-family: system; }
.head { font-size: 1.3rem; font-weight: bold; margin-bottom: 0.3rem; }
.legend { margin-bottom: 0.8rem; font-size: 0.85rem; }
.swatch { display: inline-block; width: 0.8rem; line-height: 0.8rem; border-radius: 0.2rem;
          margin: 0 0.25rem 0 0.6rem; }
.folder { margin: 0.9rem 0 0.3rem 0; font-size: 0.9rem; font-weight: bold; }
.tiles { line-height: 2.2rem; }
.tile { display: inline-block; line-height: 1.8rem; padding: 0 0.45rem;
        margin-right: 0.25rem; border-radius: 0.25rem; font-size: 0.85rem; }
a { text-decoration: none; }
'''


def render(files, health, activity, history, changes, now, folders=()):
    """The map as HTML.

    files: name -> Report, for every file to show.
    health: overall health, or None.
    activity: name -> (time it last changed, 'up', 'down' or 'same').
    history: (time, health) whenever health changed.
    changes: (time, way) for every change, for the timeline's ticks.
    folders: the project's folders, to show names relative to them.
    """
    parts = ['<body id="synesthesia-map"><style>{}</style>'.format(STYLE)]
    if health is not None:
        parts.append('<div class="head">{} &nbsp;{:.2f}</div>'.format(
            html.escape(music.name(health)), health))
    parts.append(legend())
    if history:
        parts.append(timeline(history, changes, now))
    shown = sorted(files, key=lambda name: -files[name].lines)[:MAX_TILES]
    longest = max((files[name].lines for name in shown), default=1) or 1
    for folder, names in grouped(shown, folders):
        parts.append('<div class="folder">{}</div><div class="tiles">'.format(html.escape(folder)))
        parts.extend(tile(name, files[name], longest, activity.get(name), now) for name in names)
        parts.append('</div>')
    if len(files) > len(shown):
        hidden = len(files) - len(shown)
        parts.append('<div class="folder">and {} smaller files</div>'.format(hidden))
    parts.append('</body>')
    return ''.join(parts)


def legend():
    return '<div class="legend">{}</div>'.format(''.join(
        '<span class="swatch" style="background-color: {};">&nbsp;</span>{}'.format(
            hex_color(c), s.name)
        for c, s in zip(COLORS, music.STAGES)))


def timeline(history, changes, now):
    bands = [(s.threshold, c) for s, c in zip(music.STAGES, COLORS)]
    ticks = [(t, WAYS[way]) for t, way in changes]
    canvas = picture.timeline(history, ticks, now, SPAN, 1200, 120, bands, (40, 40, 40))
    return '<div><img src="{}" width="600" height="60"></div>'.format(canvas.data_uri())


def grouped(names, folders):
    """(folder, names) pairs, folders in order, names alphabetical."""
    groups = {}
    for name in names:
        folder = os.path.dirname(relative(name, folders)) or '.'
        groups.setdefault(folder, []).append(name)
    return [(folder, sorted(groups[folder], key=str.lower)) for folder in sorted(groups)]


def relative(name, folders):
    for folder in folders:
        if name.startswith(folder.rstrip(os.sep) + os.sep):
            return os.path.relpath(name, folder)
    return name


def tile(name, report, longest, activity, now):
    lit = 0.0
    if activity is not None:
        lit = max(0.0, 1 - (now - activity[0]) / FADE)
    color = COLORS[music.stage(report.health)]
    background = mix(color, (255, 255, 255), 0.55 * lit)
    text = (25, 25, 25) if luminance(background) > 140 else (245, 245, 245)
    width = NARROWEST + (WIDEST - NARROWEST) * report.lines / longest
    border = 'border: 2px solid #ffffff; ' if lit > 0 else ''
    label = os.path.basename(name) or name
    label = ('⚠ ' if report.bugs else '') + truncate(label, int((width - 12) / 7.5))
    command = html.escape('subl:open_file ' + json.dumps({'file': name}), quote=True)
    return ('<a href="{}"><span class="tile" style="width: {}px; background-color: {}; '
            'color: {}; {}">{}</span></a>').format(
        command, int(width), hex_color(background), hex_color(text), border, html.escape(label))


def truncate(text, length):
    length = max(length, 3)
    return text if len(text) <= length else text[:length - 1] + '…'


def mix(a, b, amount):
    return tuple(int(x + (y - x) * amount) for x, y in zip(a, b))


def luminance(color):
    r, g, b = color
    return 0.299 * r + 0.587 * g + 0.114 * b


def hex_color(color):
    return '#{:02x}{:02x}{:02x}'.format(*color)
