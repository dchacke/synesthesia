"""Turn recordings from VSCO 2 Community Edition into the samples Synesthesia
ships with: mono, 32 kHz, 16-bit, starting at the onset, trimmed, faded out,
normalized, and tuned to their measured pitch.

VSCO 2 CE is public domain (CC0): https://github.com/sgossner/VSCO-2-CE

Usage: python3 tools/prepare_samples.py <VSCO-2-CE checkout> <output folder>

Needs macOS's afconvert for resampling. The output folder gets one folder
per instrument and a samples.json listing each file's pitch in Hz.
"""

import array
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import wave

RATE = 32000
NOTES = {'C': 0, 'C#': 1, 'D': 2, 'D#': 3, 'E': 4, 'F': 5, 'F#': 6, 'G': 7, 'G#': 8, 'A': 9, 'A#': 10, 'B': 11}

# instrument: (source files, seconds to keep, octaves the source names are
# below the sounding pitch, or None for unpitched). VSCO names cello,
# contrabass, marimba and glockenspiel notes an octave low.
SOURCES = {
    'harp': (['Strings/Harp/KSHarp_{}_mf.wav'.format(n) for n in
              'D2 F2 A2 C3 E3 G3 B3 D4 F4 A4 C5 E5 G5'.split()], 4.5, 0),
    'piano': (['Keys/Upright Piano/Player_dyn1_rr1_{:03d}.wav'.format(i) for i in range(14, 26, 2)], 5.0, 0),
    'cello': (['Strings/Cello Section/susvib/susvib_{}_v1_1.wav'.format(n) for n in 'D2 F2 A2 C3 E3'.split()], 5.0, 1),
    'cello_tremolo': (['Strings/Cello Section/trem/trem_{}_v1_1.wav'.format(n) for n in 'D2 A2'.split()], 4.0, 1),
    'bass_pizz': (['Strings/Solo Contrabass/Pizz/BKCtbss_Pizz_{}_v3_rr1.wav'.format(n) for n in 'C1 E1'.split()], 2.5, 1),
    'bass_sustain': (['Strings/Solo Contrabass/SusNV/BKCtbss_SusNV_D1_v1_rr1.wav'], 5.0, 1),
    'bass_tremolo': (['Strings/Solo Contrabass/Trem/BKCtbss_Trem_E1_v1_rr1.wav'], 4.0, 1),
    'marimba': (['Percussion/Marimba/Marimba_hit_Outrigger_{}_loud_01.wav'.format(n) for n in
                 'C2 G2 F3 C4 G4 C6'.split()], 2.5, 1),
    'glock': (['Percussion/Glock/glock_medium_{}.wav'.format(n) for n in 'G4 C5 G5 C6'.split()], 3.5, 1),
    'bells': (['Percussion/TB_hit_{}.wav'.format(n) for n in
               'C4_v4_rr1 G4_v4_rr1 C5_v4_rr1 F5_v3_rr1'.split()], 6.0, 0),
    'timpani': (['Percussion/Timpani/Timpani{}_Hit_v3_rr1_Sum.wav'.format(n) for n in (1, 3, 5)]
                + ['Percussion/Timpani/Rolls/Timpani1_Roll_v3_rr1_Sum.wav'], 4.0, None),
    'gong': (['Percussion/gongHit_mf.wav', 'Percussion/gongHit_p.wav',
              'Percussion/gongscrape_mf.wav', 'Percussion/gongscrape_pp.wav'], 8.0, None),
    'cymbal': (['Percussion/susCymb1-bow-1.wav', 'Percussion/susCymb1-bow-2.wav'], 6.0, None),
}
PIANO_KEYS = {i: 21 + 2 * i for i in range(14, 26, 2)}  # from the library's MappingChart.txt


def main(source, out):
    manifest = {}
    for instrument, (files, seconds, octave) in SOURCES.items():
        os.makedirs(os.path.join(out, instrument), exist_ok=True)
        manifest[instrument] = {}
        for rel in files:
            samples = trim(convert(os.path.join(source, rel)), seconds)
            if octave is None:
                name, freq = re.sub(r'(_v\d.*|_Sum)?\.wav$', '', os.path.basename(rel)), None
            else:
                named = named_pitch(rel) * 2 ** octave
                freq = tune(samples, named)
                name = note_name(freq)
            write(os.path.join(out, instrument, name + '.wav'), samples)
            manifest[instrument][name] = freq
            print('{:14} {:22} {}'.format(instrument, name, '{:.2f} Hz'.format(freq) if freq else ''))
    with open(os.path.join(out, 'samples.json'), 'w') as f:
        json.dump(manifest, f, indent=2, sort_keys=True)


def convert(path):
    """Mono 32 kHz floats, via afconvert's high-quality resampler."""
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, 'out.wav')
        subprocess.run(['afconvert', '-f', 'WAVE', '-d', 'LEI16@{}'.format(RATE), '-c', '1', '--mix',
                        path, target], check=True)
        with wave.open(target) as w:
            pcm = array.array('h', w.readframes(w.getnframes()))
    if sys.byteorder == 'big':
        pcm.byteswap()
    return [s / 32768 for s in pcm]


def trim(samples, seconds):
    """Start just before the onset, keep `seconds`, fade out, normalize."""
    peak = max(map(abs, samples))
    start = next(i for i, s in enumerate(samples) if abs(s) > 0.02 * peak)
    start = max(0, start - int(0.004 * RATE))
    samples = samples[start:start + int(seconds * RATE)]
    fade = min(len(samples), int(0.6 * RATE))
    for i in range(fade):
        samples[len(samples) - fade + i] *= math.cos(math.pi / 2 * (i + 1) / fade)
    scale = 0.95 / max(map(abs, samples))
    return [s * scale for s in samples]


def named_pitch(rel):
    base = os.path.basename(rel)
    piano = re.search(r'Player_dyn\d_rr\d_(\d{3})', base)
    if piano:
        return 440 * 2 ** ((PIANO_KEYS[int(piano.group(1))] - 69) / 12)
    m = re.search(r'_([A-G]#?)(\d)(_|\.)', base)
    return 440 * 2 ** ((NOTES[m.group(1)] + 12 * (int(m.group(2)) + 1) - 69) / 12)


def tune(samples, near):
    """The frequency within half a semitone of `near` where the spectrum
    peaks, measured in 2-cent steps just after the attack."""
    peak = max(range(len(samples)), key=lambda i: abs(samples[i]))
    seg = samples[peak + int(0.03 * RATE):peak + int(0.43 * RATE)]

    def power(f):
        w = 2 * math.pi * f / RATE
        c = s = 0.0
        for i, v in enumerate(seg):
            c += v * math.cos(w * i)
            s += v * math.sin(w * i)
        return c * c + s * s
    cents = max(range(-50, 51, 2), key=lambda c: power(near * 2 ** (c / 1200)))
    return round(near * 2 ** (cents / 1200), 2)


def note_name(freq):
    midi = round(69 + 12 * math.log2(freq / 440))
    return [k for k, v in NOTES.items() if v == midi % 12][0] + str(midi // 12 - 1)


def write(path, samples):
    pcm = array.array('h', (int(max(-1.0, min(1.0, s)) * 32767) for s in samples))
    if sys.byteorder == 'big':
        pcm.byteswap()
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
