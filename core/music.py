"""Seven stages of code health, from beautiful to cursed, played on recorded
instruments.

The code is the score (see score.py): the stage decides the scale,
instruments, tempo, timing and room; the lines decide the notes. Bars of
eight lines are rendered to WAV files and cached by content, so code that
hasn't changed costs nothing to play again.
"""

import hashlib
import math
import os
import random
import struct
import sys
import tempfile
from array import array
from collections import namedtuple

from .sampler import RATE

VERSION = 4  # part of every cache key; bump when the music changes
D3 = 146.83
STEPS = 8  # lines per bar
MAX_CACHED_BARS = 100  # about 100 MB

# melody, comment and function are (instrument, semitones above D3); bass is
# (instrument, roots to alternate between, seconds, loudness). Unpitched
# sounds name a recording instead of semitones. room is (wet, size). saw
# adds a singing saw sliding between notes above everything else.
Stage = namedtuple('Stage', 'threshold name scale step melody comment bass function broken '
                            'room detune jitter density cluster saw')

STAGES = (
    Stage(0.90, 'beautiful', (0, 2, 4, 7, 9), 0.26, ('harp', 0), ('glock', 24),
          ('cello', (0, 7), 4.5, 0.25), ('bass_pizz', -12), ('bells', 12),
          (0.2, 0.75), 0, 0.008, 1.0, False, False),
    Stage(0.75, 'good', (0, 2, 4, 5, 7, 9, 11), 0.3, ('harp', 0), ('glock', 24),
          ('bass_pizz', (-12, -17), 2.5, 0.45), ('bass_pizz', -12), ('bells', 12),
          (0.2, 0.75), 0, 0.01, 1.0, False, False),
    Stage(0.60, 'decent', (0, 2, 5, 7, 10), 0.33, ('marimba', 0), ('marimba', 12),
          ('bass_pizz', (-12, -14), 2.5, 0.45), ('bass_pizz', -12), ('bells', 12),
          (0.14, 0.65), 0, 0.012, 1.0, False, False),
    Stage(0.45, 'meh', (0, 2, 3, 5, 7, 8, 10), 0.42, ('piano', 0), ('piano', 12),
          ('cello', (0, -2), 4.5, 0.28), ('bass_pizz', -12), ('bells', 12),
          (0.26, 0.8), 0, 0.02, 0.85, False, False),
    Stage(0.30, 'bad', (0, 1, 3, 5, 7, 8, 10), 0.5, ('piano', 0), ('bells', 12),
          ('bass_sustain', (-12,), 5.0, 0.35), ('bells', 12), ('gong', 'gongscrape_pp'),
          (0.34, 0.85), 8, 0.04, 0.7, False, False),
    Stage(0.15, 'awful', (0, 1, 3, 4, 6, 7, 9, 10), 0.55, ('piano', 0), ('bells', 12),
          ('cello_tremolo', (0, 6), 4.0, 0.4), ('timpani', 'Timpani1_Roll'), ('gong', 'gongscrape_pp'),
          (0.42, 0.87), 22, 0.07, 0.6, True, False),
    Stage(0.00, 'cursed', (0, 1, 6, 7, 11), 0.65, ('piano', 0), ('cymbal', 'susCymb1-bow-2'),
          ('bass_tremolo', (-12, -11), 4.0, 0.45), ('gong', 'gongHit_p'), ('gong', 'gongscrape_mf'),
          (0.5, 0.9), 40, 0.12, 0.5, True, True),
)


def stage(health):
    """Index into STAGES for a health score."""
    for i, s in enumerate(STAGES):
        if health >= s.threshold:
            return i
    return len(STAGES) - 1


def name(health):
    return STAGES[stage(health)].name


def pitch(semitones, cents=0.0):
    return D3 * 2 ** ((semitones + cents / 100) / 12)


def degree(scale, d):
    octave, step = divmod(d, len(scale))
    return scale[step] + 12 * octave


# A note to play: when, what, how loud, where, and for how long.
Event = namedtuple('Event', 'time instrument freq sample ratio velocity pan seconds')


def _spread(key, amount):
    """A value in [-amount, amount] that depends only on `key`."""
    return amount * (((key >> 7) % 2001) / 1000 - 1)


def _sound(spec, time, velocity, pan=0.0, transpose=0, cents=0.0, seconds=3.0, key=0):
    instrument, where = spec
    if isinstance(where, str):  # unpitched: vary the speed a little instead
        return Event(time, instrument, None, where, 2 ** (_spread(key, 2) / 12), velocity, pan, seconds)
    return Event(time, instrument, pitch(where + transpose, cents), None, 1.0, velocity, pan, seconds)


def arrange(sheet, cursor, index):
    """The events of one bar: STEPS lines of `sheet` starting at `cursor`,
    played in stage `index`, with rests past its end. Returns (events, seconds)."""
    s = STAGES[index]
    lines = _lines(sheet, cursor)
    first = next((line.key for line in lines if line), 0)
    instrument, roots, length, level = s.bass
    events = [_sound((instrument, roots[first % len(roots)]), 0.0, level, seconds=length)]
    for k, line in enumerate(lines):
        if line is None or line.kind == 'blank':
            continue  # a rest
        if (line.key % 1000) / 1000 >= s.density:
            continue  # sparser as things get worse
        time = max(0.0, k * s.step + _spread(line.key, s.jitter))
        velocity = 0.35 + 0.45 * min(line.length, 80) / 80
        pan = _spread(line.key >> 3, 0.6)
        cents = _spread(line.key >> 5, s.detune)
        note = degree(s.scale, min(line.depth * 2 + line.key % 3, len(s.scale) * 5 // 2))
        spec = s.comment if line.kind == 'comment' else s.melody
        events.append(_sound(spec, time, velocity, pan, note, cents, 3.0, line.key))
        if s.cluster:  # a semitone grinding against the melody
            events.append(_sound(spec, time, velocity * 0.7, -pan, note + 1, -cents, 3.0, line.key))
        if line.kind == 'function':
            events.append(_sound(s.function, time, 0.6, 0.0, 0, cents, 4.0, line.key))
        if line.broken:
            events.append(_sound(s.broken, time, 0.7, -pan, 1, cents, 3.0, line.key))
            events.append(_sound(s.broken, time + 0.03, 0.6, pan, 6, -cents, 3.0, line.key >> 1))
    if s.saw:
        events.extend(_saw(s, lines))
    return events, STEPS * s.step


def _saw(s, lines):
    """The singing saw's part: every other line it slides to a new note high
    above the rest, and at the end of the bar it sighs down a fifth."""
    points = []
    for k, line in enumerate(lines):
        if line and line.kind != 'blank' and line.key % 2 == 0:
            note = 19 + degree(s.scale, (line.depth + line.key) % (2 * len(s.scale)))
            points.append((k * s.step, pitch(note, _spread(line.key >> 9, s.detune))))
    if not points:
        return []
    start, last = points[0][0], points[-1][1]
    points.append((STEPS * s.step - 0.4, last * 2 ** (-7 / 12)))
    shape = tuple((round(t - start, 3), round(f, 2)) for t, f in points)
    return [Event(start, 'saw', None, shape, 1.0, 0.45, _spread(lines[0].key if lines[0] else 0, 0.5),
                  STEPS * s.step - start + 1.2)]


def _lines(sheet, cursor):
    """The STEPS lines of a bar starting at `cursor`; None past the end, so
    that the last bar of a file trails off into rests."""
    sheet = sheet or []
    return [sheet[cursor + k] if cursor + k < len(sheet) else None for k in range(STEPS)]


def accent_events(index, direction):
    """A short figure on the stage's melody instrument: up when things got
    better, down when they got worse, a single note otherwise."""
    s = STAGES[index]
    steps = {'up': (0, 2), 'down': (2, 0), 'same': (0,)}[direction]
    events = []
    for k, d in enumerate(steps):
        transpose = 12 + degree(s.scale, d)
        pan = 0.25 * (2 * k - 1) if len(steps) > 1 else 0.0
        events.append(_sound(s.melody, 0.11 * k, 0.8, pan, transpose, s.detune * (0.5 - k), 2.0))
        if s.cluster:
            events.append(_sound(s.melody, 0.11 * k, 0.5, -pan, transpose + 1, 0.0, 2.0))
    return events


def singing_saw(points, seconds):
    """A saw bowed like a violin: an almost pure tone that slides from note to
    note, with a slow vibrato that widens as each note is held, swelling in
    with the bow, dipping when the bow changes direction, and wavering
    slightly with the pressure. `points` lists (seconds, Hz) to slide to."""
    rng = random.Random(repr(points))
    n = int(seconds * RATE)
    out = [0.0] * n
    sin, cos = math.sin, math.cos
    phase = 0.0
    freq = points[0][1]
    target = 0
    since = 0.0  # seconds since the current note began
    pressure = 1.0
    wobble = rng.uniform(0, 2 * math.pi)
    level = 0.0
    block = 32
    for start in range(0, n, block):
        t = start / RATE
        while target + 1 < len(points) and t >= points[target + 1][0]:
            target += 1
            since = 0.0
        since += block / RATE
        goal = points[target][1]
        freq *= (goal / freq) ** min(1.0, block / RATE / 0.3)  # the slide
        depth = 70 * min(1.0, since / 0.6)  # cents, widening as the note is held
        rate = 5.2 + 0.6 * sin(0.7 * t + wobble)
        bent = freq * 2 ** (depth / 1200 * sin(2 * math.pi * rate * t))
        pressure += 0.2 * (1 + 0.04 * rng.uniform(-1, 1) - pressure)
        swell = min(1.0, t / 0.4) * min(1.0, max(0.0, seconds - t) / 0.8)
        dip = 1 - 0.35 * max(0.0, 1 - since / 0.25)  # the bow changing direction
        goal_level = swell * dip * pressure
        step = (goal_level - level) / block
        inc = 2 * math.pi * bent / RATE
        for i in range(start, min(start + block, n)):
            x = sin(phase)
            out[i] = level * x * (1 + 0.12 * cos(phase) + 0.03 * (3 - 4 * x * x))
            phase += inc
            level += step
    return out


def mix(library, events, tail):
    """Stereo floats of `events`, with `tail` seconds of silence for the room."""
    notes = []
    for e in events:
        if e.instrument == 'saw':
            samples = singing_saw(e.sample, e.seconds)
        else:
            samples = library.note(e.instrument, freq=e.freq, name=e.sample, ratio=e.ratio, seconds=e.seconds)
        notes.append((int(e.time * RATE), samples, e))
    length = max((start + len(samples) for start, samples, _ in notes), default=0) + int(tail * RATE)
    left, right = [0.0] * length, [0.0] * length
    for start, samples, e in notes:
        angle = (e.pan + 1) * math.pi / 4  # constant-power panning
        gl, gr = e.velocity * math.cos(angle), e.velocity * math.sin(angle)
        end = start + len(samples)
        left[start:end] = [a + gl * b for a, b in zip(left[start:end], samples)]
        right[start:end] = [a + gr * b for a, b in zip(right[start:end], samples)]
    return left, right


def reverb(left, right, wet, size):
    """Schroeder-style: damped combs over the mono sum, then a slightly
    different allpass chain per side for width."""
    n = len(left)
    mono = [0.5 * (a + b) for a, b in zip(left, right)]
    combs = [0.0] * n
    feedback = 0.6 + 0.3 * size
    for ms in (29.7, 37.1, 41.1, 43.7):
        delay = int(RATE * ms / 1000 * (0.7 + 0.6 * size))
        y = mono[:]
        damped = 0.0
        for i in range(delay, n):
            damped += 0.45 * (y[i - delay] - damped)
            y[i] += feedback * damped
        combs = [a + b for a, b in zip(combs, y)]
    sides = []
    for offsets in ((5.0, 1.7), (5.6, 2.1)):
        x = combs
        for ms in offsets:
            delay = int(RATE * ms / 1000)
            y = x[:]
            for i in range(delay, n):
                y[i] = -0.7 * x[i] + x[i - delay] + 0.7 * y[i - delay]
            x = y
        sides.append(x)
    scale = wet / 4
    return ([a + scale * b for a, b in zip(left, sides[0])],
            [a + scale * b for a, b in zip(right, sides[1])])


def render(library, events, room):
    """Mix and reverberate `events`, peaking at 1.0."""
    wet, size = room
    left, right = mix(library, events, tail=0.5 + 3 * (size - 0.6))
    left, right = reverb(left, right, wet, size)
    fade = min(len(left), int(0.4 * RATE))  # the room's tail ends gently, not with a click
    for side in (left, right):
        for k in range(fade):
            side[len(side) - fade + k] *= 1 - (k + 1) / fade
    peak = max(max(map(abs, left), default=0.0), max(map(abs, right), default=0.0)) or 1.0
    return [a / peak for a in left], [b / peak for b in right]


def bar_file(library, sheet, cursor, index, volume, directory):
    """Render a bar to a WAV, cached by what's in it. Returns (seconds until
    the next bar, path)."""
    lines = _lines(sheet, cursor)
    digest = hashlib.sha1(repr((VERSION, index, lines, round(volume, 2))).encode()).hexdigest()[:16]
    path = os.path.join(directory, 'bars', 'bar-{}-{}.wav'.format(index, digest))
    events, seconds = arrange(lines, 0, index)
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        left, right = render(library, events, STAGES[index].room)
        write_wav(path, left, right, volume)
        _prune(os.path.dirname(path))
    return seconds, path


def accent_file(library, index, direction, volume, directory):
    path = os.path.join(directory, 'accent-{}-{}-{:03d}.wav'.format(index, direction, round(volume * 100)))
    if not os.path.exists(path):
        os.makedirs(directory, exist_ok=True)
        wet, size = STAGES[index].room
        left, right = render(library, accent_events(index, direction), (wet, size * 0.9))
        write_wav(path, left, right, volume)
    return path


def write_wav(path, left, right, volume=1.0):
    """Write 16-bit stereo PCM atomically, so a player never sees half a file."""
    scale = 32767 * min(max(volume, 0.0), 1.0)
    pcm = array('h', [0]) * (2 * len(left))
    pcm[0::2] = array('h', (int(s * scale) for s in left))
    pcm[1::2] = array('h', (int(s * scale) for s in right))
    if sys.byteorder == 'big':
        pcm.byteswap()
    data = pcm.tobytes()
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI', b'RIFF', 36 + len(data), b'WAVE', b'fmt ', 16,
        1, 2, RATE, RATE * 4, 4, 16, b'data', len(data))
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or '.', suffix='.tmp')
    with os.fdopen(fd, 'wb') as f:
        f.write(header + data)
    os.replace(tmp, path)


def _prune(directory):
    """Keep the bar cache from growing without bound: drop the oldest."""
    names = [n for n in os.listdir(directory) if n.endswith('.wav')]
    if len(names) <= MAX_CACHED_BARS:
        return
    paths = sorted((os.path.join(directory, n) for n in names), key=os.path.getmtime)
    for path in paths[:len(paths) - MAX_CACHED_BARS]:
        try:
            os.remove(path)
        except OSError:
            pass
