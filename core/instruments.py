"""Physically modelled instruments, rendered sample by sample in pure Python.

Each function returns a mono list of floats peaking at 1.0. Plucked strings
use Karplus-Strong; struck bars, bells, bowls and gongs are sums of decaying
modes; bowed instruments sustain their modes with a flickering, bending bow.
"""

import math
import random

RATE = 32000
TAU = 2 * math.pi
SILENT = 0.001  # -60 dB, where a note counts as over
CONTROL = 32  # samples between updates of slowly moving parameters


def pluck(freq, t60=3.0, brightness=0.6, position=0.13, seed=0):
    """A plucked string: Karplus-Strong with an allpass for exact tuning.
    `brightness` (0-1) is how hard and close to the bridge it is plucked;
    `t60` is how long it rings."""
    rng = random.Random(seed)
    delay = RATE / freq - 0.5  # the averaging filter adds half a sample
    n = int(delay)
    frac = delay - n
    if frac < 0.1:  # keeps the allpass coefficient well behaved
        n -= 1
        frac += 1
    c = (1 - frac) / (1 + frac)
    gain = SILENT ** (1 / (freq * t60))
    length = n + int(t60 * RATE)

    # The string's shape when let go: a triangle peaking where the finger
    # pulled it, roughened by a little noise and smoothed for softer plucks.
    peak = max(1, int(position * n))
    y = [(i / peak if i < peak else (n - i) / (n - peak)) + 0.15 * rng.uniform(-1, 1)
         for i in range(n)]
    k = 0.15 + 0.6 * brightness
    for _ in range(2):
        smooth = y[-1]
        for i in range(n):
            smooth += k * (y[i] - smooth)
            y[i] = smooth
    mean = sum(y) / n
    y = [v - mean for v in y]
    y.extend([0.0] * (length - n))

    # The delay line is a loop, so its first sample follows its last.
    previous_in = previous_out = 0.5 * (y[0] + y[n - 1])
    y[n] = gain * previous_out
    for i in range(n + 1, length):
        averaged = 0.5 * (y[i - n] + y[i - n - 1])
        out = c * averaged + previous_in - c * previous_out
        previous_in, previous_out = averaged, out
        y[i] = gain * out
    ramp = int(0.002 * RATE)  # the finger leaves the string, not a cliff edge
    for i in range(ramp):
        y[i] *= i / ramp
    return _normalized(y)


def strike(freq, modes, t60=2.0, hardness=0.5, seed=0):
    """A struck object as a sum of modes, each (ratio, amplitude, relative
    t60). Harder mallets bring out the higher modes and a sharper click."""
    rng = random.Random(seed)
    nyquist = RATE * 0.45
    longest = max(t60 * rel for _, _, rel in modes)
    out = [0.0] * int(longest * RATE + 2)
    for ratio, amp, rel in modes:
        f = freq * ratio
        if f >= nyquist:
            continue
        amp *= (0.25 + 0.75 * hardness) ** math.log2(max(ratio, 1.0))
        w = TAU * f / RATE
        r = SILENT ** (1 / (t60 * rel * RATE))
        c1, c2 = 2 * r * math.cos(w), r * r
        y2, y1 = 0.0, amp * r * math.sin(w)
        out[1] += y1
        for i in range(2, int(t60 * rel * RATE)):
            y0 = c1 * y1 - c2 * y2
            out[i] += y0
            y2, y1 = y1, y0
    # The mallet itself: a few milliseconds of soft noise.
    click = int(0.004 * RATE)
    smooth = 0.0
    level = 0.15 * hardness
    for i in range(click):
        smooth += 0.3 * (rng.uniform(-1, 1) - smooth)
        out[i] += level * smooth * (1 - i / click)
    return _normalized(out)


def bow(freq, partials, seconds, attack=1.0, release=1.5, jitter=0.3,
        wobble=0.0, glide=0.0, seed=0):
    """A bowed or rubbed resonator. Each partial is (ratio, amplitude). The
    bow makes levels flicker by `jitter`; `wobble` (cents) bends the pitch
    slowly back and forth and `glide` (cents) drifts it over the note."""
    rng = random.Random(seed)
    n = int(seconds * RATE)
    out = [0.0] * n
    nyquist = RATE * 0.45
    for ratio, amp in partials:
        f = freq * ratio
        if f >= nyquist:
            continue
        speed = rng.uniform(0.15, 0.5)
        phase_shift = rng.uniform(0, TAU)
        flicker = 1.0
        target = 1.0
        phase = rng.uniform(0, TAU)
        level = 0.0
        for block in range(0, n, CONTROL):
            t = block / RATE
            env = min(1.0, t / attack) * min(1.0, (seconds - t) / release)
            if block % (CONTROL * 64) == 0:  # the bow catches and slips
                target = 1 + jitter * rng.uniform(-1, 1)
            flicker += 0.05 * (target - flicker)
            cents = wobble * math.sin(TAU * speed * t + phase_shift) + glide * t / seconds
            inc = TAU * f * 2 ** (cents / 1200) / RATE
            goal = amp * max(env, 0.0) * flicker
            step = (goal - level) / CONTROL
            for i in range(block, min(block + CONTROL, n)):
                out[i] += level * math.sin(phase)
                phase += inc
                level += step
    return _normalized(out)


def doublets(modes, beat_hz, freq):
    """Real bells and bowls are slightly asymmetric, so each mode splits in
    two and beats. Returns the modes with a twin `beat_hz` above each."""
    twins = [(ratio + beat_hz / freq, amp * 0.8, rel) for ratio, amp, rel in modes]
    return list(modes) + twins


# Mode tables: (frequency ratio, amplitude, relative decay time).
MARIMBA = [(1.0, 1.0, 1.0), (3.93, 0.35, 0.25), (9.24, 0.12, 0.08)]
VIBES = [(1.0, 1.0, 1.0), (4.0, 0.3, 0.3), (10.0, 0.08, 0.1)]
GLASS = [(1.0, 1.0, 1.0), (2.32, 0.4, 0.6), (4.25, 0.2, 0.4), (6.63, 0.1, 0.25)]
BOWL = [(1.0, 1.0, 1.0), (2.71, 0.5, 0.7), (5.15, 0.22, 0.45), (8.21, 0.08, 0.3)]
# A church bell: hum an octave down, a minor-third "tierce" that makes bells
# sound melancholy, then the quint, nominal and upper partials.
BELL = [(0.5, 0.6, 1.0), (1.0, 1.0, 0.75), (1.19, 0.7, 0.6), (1.5, 0.35, 0.45),
        (2.0, 0.6, 0.35), (2.5, 0.25, 0.25), (3.0, 0.2, 0.2), (4.05, 0.12, 0.15)]
GONG = [(1.0, 1.0, 1.0), (1.47, 0.7, 0.9), (2.09, 0.55, 0.8), (2.56, 0.5, 0.7),
        (3.14, 0.4, 0.6), (3.72, 0.3, 0.5), (4.46, 0.25, 0.4), (5.31, 0.2, 0.3),
        (6.18, 0.12, 0.25)]
# Bowed metal rods, as on a waterphone.
WATERPHONE = [(1.0, 1.0), (1.53, 0.6), (2.17, 0.45), (2.69, 0.3), (3.41, 0.2)]
SINGING_BOWL = [(1.0, 1.0), (1.0 + 0.004, 0.8), (2.71, 0.35), (2.71 * 1.003, 0.3)]


def _normalized(samples):
    peak = max(map(abs, samples), default=0.0)
    if peak > 0:
        scale = 1 / peak
        return [s * scale for s in samples]
    return samples
