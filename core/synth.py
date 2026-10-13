"""Turn a health score into sound.

Healthy code gets a just-intoned major chord, arpeggiated like a music box,
with warm harmonics and no beating. As health drops the chord darkens to
minor, then diminished, then a cluster of minor seconds and tritones whose
voices are detuned against each other, creep in slowly, waver, sag in pitch,
and sit on a bed of wind with a ghostly whistle gliding on top.

Pure Python. No `wave` module, since Sublime's embedded Python lacks audioop.
"""

import math
import os
import random
import struct
import sys
import tempfile
from array import array

RATE = 22050
TAU = 2 * math.pi
CONTROL = 32  # samples between updates of slowly moving parameters
PAD_SECONDS = 10.0
PAD_FADE = 3.0
LEVELS = 20  # health is quantized to this many steps for caching

# Just intonation, so the healthy chords ring without beating.
RATIOS = {
    0: 1, 1: 16 / 15, 6: 45 / 32, 7: 3 / 2, 11: 15 / 8, 12: 2, 13: 32 / 15,
    15: 12 / 5, 16: 5 / 2, 18: 45 / 16, 19: 3, 26: 9 / 2,
}

# (lowest health, name, chord in semitones above the root)
MOODS = (
    (0.85, 'radiant', (0, 7, 12, 16, 19, 26)),  # major, added ninth
    (0.65, 'bright', (0, 7, 12, 16, 19)),       # major
    (0.45, 'wistful', (0, 7, 12, 15, 19)),      # minor
    (0.25, 'uneasy', (0, 6, 12, 15, 18)),       # diminished
    (0.0, 'haunted', (0, 1, 6, 11, 13)),        # cluster
)


def clamp(x, low=0.0, high=1.0):
    return min(max(x, low), high)


def mood(health):
    """Return (name, chord) for a health score."""
    for threshold, name, chord in MOODS:
        if health >= threshold:
            return name, chord
    return MOODS[-1][1:]


def chime_seconds(health):
    """Healthy chimes are crisp; sick ones linger."""
    return 1.6 + 1.6 * (1 - clamp(health))


def render(health, style='chime', seed=0, volume=0.5, rate=RATE):
    """Render `health` as a list of floats in [-volume, volume].

    'chime' is a short phrase; 'pad' is a PAD_SECONDS drone with equal-power
    fades at both ends, meant to be overlapped with the next one."""
    h = clamp(health)
    d = 1 - h  # disorder
    pad = style == 'pad'
    rng = random.Random(seed)
    seconds = PAD_SECONDS if pad else chime_seconds(h)
    n = int(seconds * rate)
    out = [0.0] * n

    _, chord = mood(h)
    root = 196.0 * 2 ** (-5 * d / 12)  # G3, sinking toward D3 as code rots
    harmonics = (0.3 * h, 0.12 * h)  # warm when healthy, hollow when not
    stagger = 0.06 + 0.3 * d
    attack = 0.005 + 0.6 * d * d
    decay = 0.6 + 2.0 * d
    sag = 0.06 * d ** 3

    for i, semitones in enumerate(chord):
        cents = rng.uniform(-1, 1) * 35 * d ** 1.5
        freq = root * RATIOS[semitones] * 2 ** (cents / 1200)
        pitch = _wavering(freq, seconds, sag, cents=30 * d * d,
                          speed=rng.uniform(0.4, 1.4), phase=rng.uniform(0, TAU))
        tremolo = (0.6 * d * d, rng.uniform(2, 6), rng.uniform(0, TAU))
        amp = 1 / (1 + 0.4 * i)
        if pad:
            swell = (0.3, rng.uniform(0.05, 0.15), rng.uniform(0, TAU))
            level = _sustained(amp, swell, tremolo)
        else:
            level = _struck(amp, i * stagger, attack, decay, tremolo)
        _add_tone(out, rate, 0, n, pitch, level, harmonics)

    if pad and h > 0.6:
        _sparkle(out, rate, root, chord, h, rng)
    if d > 0.4:
        _wind(out, rate, 0.9 * d * d, rng)
    if d > 0.5:
        _ghost(out, rate, root, (d - 0.5) * 2, swells=3 if pad else 1, rng=rng)

    out = _reverb(out, rate, wet=0.2 + 0.4 * d, feedback=0.72 + 0.12 * d)
    if pad:
        _fade(out, rate, PAD_FADE, PAD_FADE)
    else:
        _fade(out, rate, 0.0, 0.3)
    _normalize(out, volume)
    return out


def render_file(health, style, seed, volume, directory):
    """Render to a WAV in `directory`, reusing an earlier render if one
    exists. Health is quantized so that the cache stays small."""
    step = round(clamp(health) * LEVELS)
    name = '{}-{:02d}-{}-{:03d}.wav'.format(style, step, seed, round(volume * 100))
    path = os.path.join(directory, name)
    if not os.path.exists(path):
        os.makedirs(directory, exist_ok=True)
        write_wav(path, render(step / LEVELS, style, seed, volume))
    return path


def write_wav(path, samples, rate=RATE):
    """Write 16-bit mono PCM atomically, so a player never sees half a file."""
    pcm = array('h', (int(clamp(s, -1.0, 1.0) * 32767) for s in samples))
    if sys.byteorder == 'big':
        pcm.byteswap()
    data = pcm.tobytes()
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI', b'RIFF', 36 + len(data), b'WAVE', b'fmt ', 16,
        1, 1, rate, rate * 2, 2, 16, b'data', len(data))
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or '.', suffix='.tmp')
    with os.fdopen(fd, 'wb') as f:
        f.write(header)
        f.write(data)
    os.replace(tmp, path)


def _wavering(freq, seconds, sag, cents, speed, phase):
    """Pitch that sags by `sag` over the sound and wobbles by `cents`."""
    def pitch(t):
        wobble = 2 ** (cents / 1200 * math.sin(TAU * speed * t + phase))
        return freq * (1 - sag * t / seconds) * wobble
    return pitch


def _struck(amp, onset, attack, decay, tremolo):
    """A plucked or bowed note: attack, then exponential decay."""
    depth, speed, phase = tremolo

    def level(t):
        t -= onset
        if t <= 0:
            return 0.0
        env = t / attack if t < attack else math.exp(-(t - attack) / decay)
        return amp * env * (1 - depth * (0.5 + 0.5 * math.sin(TAU * speed * t + phase)))
    return level


def _sustained(amp, swell, tremolo):
    """A drone that breathes slowly."""
    swell_depth, swell_speed, swell_phase = swell
    depth, speed, phase = tremolo

    def level(t):
        breath = 1 - swell_depth * (0.5 + 0.5 * math.sin(TAU * swell_speed * t + swell_phase))
        return amp * breath * (1 - depth * (0.5 + 0.5 * math.sin(TAU * speed * t + phase)))
    return level


def _add_tone(out, rate, start, stop, pitch, level, harmonics=(0.0, 0.0)):
    """Mix a tone into out[start:stop]. pitch(t) is in Hz and level(t) is the
    amplitude; both are sampled every CONTROL samples and interpolated."""
    sin, cos = math.sin, math.cos
    h2, h3 = harmonics
    phase = 0.0
    a = level(start / rate)
    for block in range(start, stop, CONTROL):
        end = min(block + CONTROL, stop)
        inc = TAU * pitch(block / rate) / rate
        target = level(end / rate)
        step = (target - a) / (end - block)
        for i in range(block, end):
            s = sin(phase)
            # sin 2x = 2 sin x cos x, sin 3x = sin x (3 - 4 sin^2 x)
            out[i] += a * s * (1 + 2 * h2 * cos(phase) + h3 * (3 - 4 * s * s))
            phase += inc
            a += step
        a = target


def _sparkle(out, rate, root, chord, health, rng):
    """Now and then a high chord tone, like wind chimes on a good day."""
    seconds = len(out) / rate
    for _ in range(int((health - 0.6) / 0.4 * 6)):
        freq = root * RATIOS[rng.choice(chord)] * 2
        onset = rng.uniform(1.0, seconds - 2.5)
        start = int(onset * rate)
        level = _struck(0.35, 0.0, 0.004, 0.5, (0.0, 1.0, 0.0))
        _add_tone(out, rate, start, min(len(out), start + int(2.5 * rate)),
                  lambda t, f=freq: f, lambda t, s=onset, l=level: l(t - s),
                  harmonics=(0.2, 0.05))


def _wind(out, rate, amp, rng):
    """Band-passed noise whose pitch and strength drift like gusts."""
    rand = rng.random
    sweep, gusts = rng.uniform(0, TAU), rng.uniform(0, TAU)
    high = low = 0.0
    n = len(out)
    for block in range(0, n, CONTROL):
        t = block / rate
        cutoff = 300 + 600 * (0.5 + 0.5 * math.sin(TAU * 0.07 * t + sweep))
        k_high = 1 - math.exp(-TAU * cutoff / rate)
        k_low = 1 - math.exp(-TAU * cutoff / 4 / rate)
        gust = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(TAU * 0.11 * t + gusts)) ** 2
        gain = 2.5 * amp * gust  # filtered noise is quiet; bring it up under the voices
        for i in range(block, min(block + CONTROL, n)):
            x = 2 * rand() - 1
            high += k_high * (x - high)
            low += k_low * (high - low)
            out[i] += gain * (high - low)


def _ghost(out, rate, root, amount, swells, rng):
    """A high, wandering whistle, like a singing saw in an empty house."""
    seconds = len(out) / rate
    base = root * 4
    p1, p2 = rng.uniform(0, TAU), rng.uniform(0, TAU)

    def pitch(t):
        glide = 3 * math.sin(TAU * 0.13 * t + p1) + 1.5 * math.sin(TAU * 0.37 * t + p2)
        return base * 2 ** (glide / 12 + 0.015 * math.sin(TAU * 5.5 * t))

    def level(t):
        return 0.35 * amount * math.sin(math.pi * swells * t / seconds) ** 2

    _add_tone(out, rate, 0, len(out), pitch, level)


def _reverb(dry, rate, wet, feedback):
    """A small Schroeder reverb: damped combs in parallel, then allpasses."""
    n = len(dry)
    combs = [0.0] * n
    for ms in (29.7, 37.1, 41.1, 43.7):
        delay = int(rate * ms / 1000)
        y = dry[:]
        damped = 0.0
        for i in range(delay, n):
            damped += 0.4 * (y[i - delay] - damped)
            y[i] += feedback * damped
        for i in range(n):
            combs[i] += y[i]
    for ms in (5.0, 1.7):
        delay = int(rate * ms / 1000)
        x = combs
        y = x[:]
        for i in range(delay, n):
            y[i] = -0.7 * x[i] + x[i - delay] + 0.7 * y[i - delay]
        combs = y
    scale = wet / 4
    return [a + scale * b for a, b in zip(dry, combs)]


def _fade(out, rate, fade_in, fade_out):
    """Equal-power fades, so overlapping pads crossfade without a dip."""
    n = len(out)
    head = int(fade_in * rate)
    tail = int(fade_out * rate)
    for i in range(head):
        out[i] *= math.sin(math.pi / 2 * i / head)
    for i in range(tail):
        out[n - tail + i] *= math.cos(math.pi / 2 * (i + 1) / tail)


def _normalize(out, volume):
    peak = max(map(abs, out), default=0.0)
    if peak > 0:
        gain = volume / peak
        for i in range(len(out)):
            out[i] *= gain
