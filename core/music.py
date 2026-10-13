"""Seven stages of code health, from beautiful to cursed, each with its own
harmony, instruments, rhythm, register and room.

The ambient stream is a sequence of short phrases ("bars"); accents are
two-note figures played when something changes. Both are rendered once per
stage and cached as WAV files, so playing them costs nothing.
"""

import math
import os
import random
import struct
import sys
import tempfile
from array import array

from . import instruments as inst

RATE = inst.RATE
D3 = 146.83
VARIANTS = 4  # different bars per stage, so the stream doesn't loop audibly

# (lowest health, name)
STAGES = (
    (0.90, 'beautiful'),
    (0.75, 'good'),
    (0.60, 'decent'),
    (0.45, 'meh'),
    (0.30, 'bad'),
    (0.15, 'awful'),
    (0.00, 'cursed'),
)

# Five-limit just intonation, so consonant chords ring without beating.
JUST = (1, 16 / 15, 9 / 8, 6 / 5, 5 / 4, 4 / 3, 45 / 32, 3 / 2, 8 / 5, 5 / 3, 9 / 5, 15 / 8)


def stage(health):
    """Index into STAGES for a health score."""
    for i, (threshold, _) in enumerate(STAGES):
        if health >= threshold:
            return i
    return len(STAGES) - 1


def name(health):
    return STAGES[stage(health)][1]


def pitch(semitones, cents=0.0):
    """Frequency `semitones` above D3, justly tuned, optionally detuned."""
    octave, degree = divmod(semitones, 12)
    return D3 * 2 ** octave * JUST[degree] * 2 ** (cents / 1200)


class Score:
    """Notes placed in time and space, mixed into stereo."""

    def __init__(self, rng):
        self.rng = rng
        self.notes = []  # (time, samples, velocity, pan)

    def add(self, time, samples, velocity, pan=0.0):
        self.notes.append((max(0.0, time), samples, velocity, pan))

    def humanize(self, time, amount=0.012):
        return time + self.rng.uniform(-amount, amount)

    def mix(self, tail):
        length = max(int(t * RATE) + len(s) for t, s, _, _ in self.notes) + int(tail * RATE)
        left = [0.0] * length
        right = [0.0] * length
        for time, samples, velocity, pan in self.notes:
            angle = (pan + 1) * math.pi / 4  # constant-power panning
            gl, gr = velocity * math.cos(angle), velocity * math.sin(angle)
            start = int(time * RATE)
            for i, s in enumerate(samples, start):
                left[i] += gl * s
                right[i] += gr * s
        return left, right


# Each stage composes one bar: returns (bar length in seconds, Score, room).
# room = (wet, size): how much reverb and how big the space sounds.

def _arpeggio(score, chord, times, make, velocity, spread=0.6):
    low, high = min(chord), max(chord)
    for semitones, time in zip(chord, times):
        pan = spread * (2 * (semitones - low) / max(high - low, 1) - 1)
        score.add(score.humanize(time), make(semitones),
                  velocity * score.rng.uniform(0.8, 1.0), pan)


def _pattern(rng, chord, shapes):
    shape = rng.choice(shapes)
    if shape == 'up':
        notes = list(chord)
    elif shape == 'down':
        notes = list(reversed(chord))
    elif shape == 'updown':
        top = len(chord) * 2 // 3
        notes = list(chord[:top]) + list(reversed(chord[:top]))[1:]
    else:  # broken: alternate low and high halves
        middle = len(chord) // 2
        low, high = chord[:middle], chord[middle:]
        notes = [n for pair in zip(low, high) for n in pair] + list(high[len(low):])
    return notes[:len(chord)]


def _harp(seed, brightness, t60=3.0):
    return lambda s: inst.pluck(pitch(s), t60=t60 * (196 / pitch(s)) ** 0.3,
                                brightness=brightness, seed=seed + s)


def _bowl(score, semitones, time, velocity, t60, seed):
    f = pitch(semitones)
    score.add(time, inst.strike(f, inst.doublets(inst.BOWL, 0.7, f), t60=t60,
                                hardness=0.2, seed=seed), velocity)


def beautiful(rng, seed):
    score = Score(rng)
    chord = _pattern(rng, [0, 7, 12, 14, 16, 19, 24, 26], ['up', 'updown', 'broken'])
    _arpeggio(score, chord, [i * 0.3 for i in range(len(chord))], _harp(seed, 0.7), 0.7)
    _bowl(score, -12, 0.0, 0.25, t60=5.0, seed=seed)
    if rng.random() < 0.6:
        high = rng.choice([28, 31, 33])
        f = pitch(high)
        score.add(rng.uniform(0.6, 1.8), inst.strike(f, inst.GLASS, t60=2.5, hardness=0.4, seed=seed),
                  0.22, rng.choice([-0.7, 0.7]))
    return 2.4, score, (0.28, 0.8)


def good(rng, seed):
    score = Score(rng)
    chord = _pattern(rng, [0, 7, 12, 16, 19, 24], ['up', 'updown', 'broken'])
    _arpeggio(score, chord, [i * 0.4 for i in range(len(chord))], _harp(seed, 0.55), 0.7)
    _bowl(score, -12, 0.0, 0.22, t60=5.0, seed=seed)
    return 2.4, score, (0.26, 0.78)


def decent(rng, seed):
    score = Score(rng)
    chord = _pattern(rng, [0, 7, 12, 14, 19], ['up', 'broken', 'down'])

    def marimba(s):
        return inst.strike(pitch(s), inst.MARIMBA, t60=1.4, hardness=0.45, seed=seed + s)
    _arpeggio(score, chord, [i * 0.5 for i in range(len(chord))], marimba, 0.75, spread=0.4)
    _bowl(score, -12, 0.0, 0.16, t60=5.0, seed=seed)
    return 2.6, score, (0.2, 0.7)


def meh(rng, seed):
    score = Score(rng)
    chord = _pattern(rng, [0, 3, 7, 12, 15], ['down', 'down', 'broken'])[:4]

    def vibes(s):
        return inst.strike(pitch(s), inst.VIBES, t60=2.6, hardness=0.3, seed=seed + s)
    _arpeggio(score, chord, [i * 0.7 for i in range(len(chord))], vibes, 0.7, spread=0.4)
    f = pitch(-12)
    score.add(0.0, inst.strike(f, inst.doublets(inst.BOWL, 2.2, f), t60=6.0, hardness=0.2,
                               seed=seed), 0.28)
    return 3.0, score, (0.32, 0.82)


def _dead(s, cents, seed):
    """A muted, lifeless pluck."""
    return inst.pluck(pitch(s, cents), t60=0.45, brightness=0.25, position=0.3, seed=seed)


def bad(rng, seed):
    score = Score(rng)
    score.add(0.0, inst.strike(pitch(0), inst.BELL, t60=5.0, hardness=0.55, seed=seed), 0.75)
    time = rng.uniform(0.5, 0.9)
    for s in rng.sample([0, 3, 6, 10, 12], 4):
        score.add(time, _dead(s, rng.uniform(-8, 8), seed + s), 0.6, rng.uniform(-0.5, 0.5))
        time += rng.uniform(0.3, 0.9)  # hesitant
    score.add(0.0, inst.bow(pitch(-12), inst.SINGING_BOWL, 4.8, attack=1.5, release=2.0,
                            jitter=0.15, wobble=8, seed=seed), 0.3)
    return 3.4, score, (0.42, 0.86)


def awful(rng, seed):
    score = Score(rng)
    score.add(0.0, inst.strike(pitch(0, -22), inst.BELL, t60=5.0, hardness=0.6, seed=seed), 0.7, -0.3)
    score.add(rng.uniform(1.2, 2.0), inst.strike(pitch(1, 18), inst.BELL, t60=4.0, hardness=0.6,
                                                 seed=seed + 1), 0.55, 0.4)
    time = rng.uniform(0.3, 0.6)
    while time < 3.4:
        if rng.random() < 0.7:  # stumbling, with notes dropping out
            s = rng.choice([-12, -6, 0, 1, 6, 9])
            score.add(time, _dead(s, rng.uniform(-30, 30), seed + int(time * 100)), 0.6,
                      rng.uniform(-0.6, 0.6))
        time += rng.choice([0.2, 0.25, 0.6, 0.9])
    gong = inst.strike(pitch(-12, -15), inst.GONG, t60=5.0, hardness=0.25, seed=seed)
    _swell(gong, 0.8)
    score.add(0.2, gong, 0.4)
    score.add(0.5, inst.bow(pitch(6, -25), inst.WATERPHONE, 3.5, attack=1.5, release=1.5,
                            jitter=0.35, wobble=40, glide=-60, seed=seed), 0.18, 0.5)
    return 3.8, score, (0.5, 0.88)


def cursed(rng, seed):
    score = Score(rng)
    for k in range(rng.choice([1, 2])):  # bowed metal, screeching and bending
        score.add(rng.uniform(0, 1.5) + 1.2 * k,
                  inst.bow(pitch(rng.choice([25, 30, 31]), rng.uniform(-40, 40)), inst.WATERPHONE,
                           rng.uniform(2.5, 3.8), attack=rng.uniform(0.3, 1.0), release=1.2,
                           jitter=0.6, wobble=rng.uniform(80, 180), glide=rng.uniform(-350, 150),
                           seed=seed + k),
                  0.45, rng.uniform(-0.8, 0.8))
    for semitones, delay in ((-24, 0.0), (-18, rng.uniform(1.0, 2.2))):  # a tritone of gongs
        gong = inst.strike(pitch(semitones, rng.uniform(-30, 30)), inst.GONG, t60=6.0,
                           hardness=0.3, seed=seed + semitones)
        _swell(gong, 1.2)
        score.add(delay, gong, 0.7, rng.uniform(-0.3, 0.3))
    time = rng.uniform(0.2, 0.8)
    while time < 4.0:  # creaks
        score.add(time, _dead(rng.choice([-17, -13, -12, -6]), rng.uniform(-60, 60),
                              seed + int(time * 100)), 0.5, rng.uniform(-0.9, 0.9))
        time += rng.uniform(0.25, 1.4)
    return 4.4, score, (0.6, 0.9)


COMPOSERS = (beautiful, good, decent, meh, bad, awful, cursed)


def accent(index, direction, seed=0):
    """A short figure: 'up' when things improved, 'down' when they got
    worse, 'same' otherwise. Played on the stage's own instrument."""
    rng = random.Random(seed)
    score = Score(rng)
    steps = {'up': (0, 7), 'down': (7, 0), 'same': (0,)}[direction]
    base = (12, 12, 12, 12, 0, 0, 12)[index]
    for k, step in enumerate(steps):
        s = base + step
        time = 0.11 * k
        if index <= 1:
            note = inst.pluck(pitch(s), t60=1.6, brightness=0.65, seed=seed + k)
        elif index == 2:
            note = inst.strike(pitch(s), inst.MARIMBA, t60=1.0, hardness=0.5, seed=seed + k)
        elif index == 3:
            note = inst.strike(pitch(s - 4 if step else s), inst.VIBES, t60=1.6, hardness=0.35, seed=seed + k)
        elif index == 4:
            note = inst.strike(pitch(s - 1 if step else s), inst.BELL, t60=2.0, hardness=0.6, seed=seed + k)
        elif index == 5:
            note = inst.strike(pitch(s + (1 if step else 0), rng.uniform(-25, 25)), inst.BELL,
                               t60=2.0, hardness=0.65, seed=seed + k)
        else:
            note = inst.bow(pitch(s + 13 + (6 if step else 0), rng.uniform(-50, 50)), inst.WATERPHONE,
                            0.9, attack=0.08, release=0.5, jitter=0.6, wobble=120,
                            glide=-250 if direction != 'up' else 120, seed=seed + k)
        score.add(time, note, 0.8, 0.25 * (k * 2 - 1) if len(steps) > 1 else 0.0)
    return score, (0.25 + 0.05 * index, 0.75 + 0.02 * index)


def render(kind, index, variant=0):
    """Render a bar or an accent ('up', 'down', 'same') for a stage, as
    (left, right) peaking at 1.0. Returns (seconds until the next bar, left, right)."""
    seed = 1000 * index + 17 * variant
    rng = random.Random(seed)
    if kind == 'bar':
        length, score, room = COMPOSERS[index](rng, seed)
    else:
        (score, room), length = accent(index, kind, seed), 0.0
    wet, size = room
    left, right = score.mix(tail=0.6 + 2.5 * (size - 0.7))
    left, right = reverb(left, right, wet, size)
    _normalize(left, right)
    return length, left, right


def reverb(left, right, wet, size):
    """Schroeder-style: damped combs over the mono sum, then a slightly
    different allpass chain per side for width."""
    n = len(left)
    mono = [0.5 * (a + b) for a, b in zip(left, right)]
    combs = [0.0] * n
    for ms in (29.7, 37.1, 41.1, 43.7):
        delay = int(RATE * ms / 1000 * (0.7 + 0.6 * size))
        y = mono[:]
        damped = 0.0
        feedback = 0.6 + 0.3 * size
        for i in range(delay, n):
            damped += 0.45 * (y[i - delay] - damped)
            y[i] += feedback * damped
        for i in range(n):
            combs[i] += y[i]
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


def render_file(kind, index, variant, volume, directory):
    """Render to a cached stereo WAV and return (seconds until the next bar, path)."""
    vol = round(volume * 100)
    path = os.path.join(directory, '{}-{}-{}-{:03d}.wav'.format(kind, index, variant, vol))
    meta = path[:-4] + '.len'
    if not os.path.exists(path):
        os.makedirs(directory, exist_ok=True)
        length, left, right = render(kind, index, variant)
        _write_atomically(meta, repr(length).encode())  # before the WAV, whose presence means done
        write_wav(path, left, right, volume)
    with open(meta) as f:
        return float(f.read()), path


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
    _write_atomically(path, header + data)


def _write_atomically(path, data):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or '.', suffix='.tmp')
    with os.fdopen(fd, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)


def _swell(samples, seconds):
    """Fade in, as when a gong is rolled rather than struck."""
    n = min(len(samples), int(seconds * RATE))
    for i in range(n):
        samples[i] *= i / n


def _normalize(left, right):
    peak = max(max(map(abs, left)), max(map(abs, right)))
    if peak > 0:
        for side in (left, right):
            for i in range(len(side)):
                side[i] /= peak
