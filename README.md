# Synesthesia

Hear the state of your code in Sublime Text.

Healthy code plays a warm, just-intoned major chord. As bugs creep in, the
harmony darkens to minor, then diminished, and finally collapses into a
detuned cluster that wavers and sags, over wind and a ghostly whistle. Fix
the bugs and it resolves again.

## Moods

| Health    | Mood    | Sound                                                     |
| --------- | ------- | --------------------------------------------------------- |
| 0.85–1.00 | radiant | major chord with an added ninth, arpeggiated, sparkling   |
| 0.65–0.85 | bright  | major chord                                               |
| 0.45–0.65 | wistful | minor chord                                               |
| 0.25–0.45 | uneasy  | diminished chord, slightly out of tune, beginning to sag  |
| 0.00–0.25 | haunted | cluster of minor seconds and tritones, wind, a ghost      |

Within each mood the sound keeps shifting: the lower the health, the more the
voices detune and waver, the lower the register, and the longer the reverb.

## How code is judged

Every view matching the `selector` setting (`source` by default) gets a health
score between 0 and 1.

- **Bugs** weigh the most. Each one counts: spans the syntax definition marks
  as `invalid` (code it cannot parse) and brackets that never find their
  partner (ignoring brackets in strings and comments). One bug in otherwise
  clean code is enough to sound uneasy; three sound haunted.
- **Mess** weighs less: lines longer than your widest ruler, lines nested more
  than four levels deep, trailing whitespace, tabs mixed with spaces, and
  TODO, FIXME, XXX, and HACK comments. Mess alone never drops below wistful.

`Synesthesia: Explain Score` shows what went into the current file's score.
The status bar shows the mood.

## Modes

- **ambient** (default): a continuous drone that follows the file you are
  looking at. Every seven seconds a new segment fades in over the old one, so
  the drone morphs as you type, fix, and switch files.
- **chime**: a short phrase whenever the mood changes (after you pause typing
  or switch files) and whenever you save.

## Install

Link this folder into Sublime Text's `Packages` folder under the name
`Synesthesia`. On macOS:

```bash
ln -s "$PWD" "$HOME/Library/Application Support/Sublime Text/Packages/Synesthesia"
```

Then run `Synesthesia: Play All Moods` from the command palette to hear the
whole range.

Requires Sublime Text 4. Sound is played with `afplay` on macOS and `paplay`,
`pw-play`, or `aplay` on Linux. On Windows it uses `winsound`, which cannot
overlap sounds, so the ambient drone cuts rather than crossfades.

## Commands

- `Synesthesia: Toggle`
- `Synesthesia: Ambient Mode` and `Synesthesia: Chime Mode`
- `Synesthesia: Play Now` chimes the current file's score
- `Synesthesia: Explain Score`
- `Synesthesia: Play All Moods`
- `Preferences: Synesthesia Settings`

The same commands are under Tools > Synesthesia.

## Tests

```bash
python3 -m unittest discover -s tests
```
