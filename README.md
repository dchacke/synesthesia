# Synesthesia

Hear the state of your code in Sublime Text.

Beautiful code plays a harp over a singing bowl. As it gets worse the music
moves to marimba, then vibraphone in a minor key, then church bells and dead,
muted strings, then detuned bells and gongs, until cursed code is all gongs,
creaks and bowed metal screeching like a horror film. Changes also get
a short accent: rising if things got better, falling if they got worse.

## Stages

| Health    | Stage     | Sound                                                    |
| --------- | --------- | -------------------------------------------------------- |
| 0.90–1.00 | beautiful | harp arpeggios in major with an added ninth, glass, bowl |
| 0.75–0.90 | good      | harp arpeggios in major                                  |
| 0.60–0.75 | decent    | marimba in open fifths, plain and dry                    |
| 0.45–0.60 | meh       | vibraphone in minor, slower, descending                  |
| 0.30–0.45 | bad       | a church bell, hesitant muted strings, a beating drone   |
| 0.15–0.30 | awful     | detuned bells, stumbling strings, a gong, bowed metal    |
| 0.00–0.15 | cursed    | screeching bowed metal, a tritone of gongs, creaks       |

As things get worse the tempo slows, the register drops and the room grows
from a small hall into a cavern. All instruments are physically modelled in
pure Python: Karplus-Strong strings, and modal synthesis for everything
struck or bowed.

## How code is judged

**Quality** starts at 1.0 and falls toward 0.3 as smells pile up: functions
longer than 40 lines, functions with more than 10 branches, code nested more
than four levels inside its function, duplicated chunks, lines longer than
your widest ruler, trailing whitespace, tabs mixed with spaces, and TODO,
FIXME, XXX and HACK comments. Smells count in proportion to the file's size,
so one long function sinks a short file more than a long one. Mess alone
never drops below bad.

**Bugs** divide what's left: spans the syntax definition marks as `invalid`
(code it cannot parse) and brackets that never close, outside strings and
comments. One bug in beautiful code sounds meh, two bad, three awful, eight
cursed.

Syntax highlighting misses a lot of broken code, such as a Ruby class
without its `end`, so Synesthesia also asks the language's own parser:
`ruby -c`, Python's `ast`, `node --check`, `bash -n` and `php -l`. None of
them run the code. A file that doesn't parse counts as at least three bugs.
Add other languages in the `syntax_checkers` setting.

Everything comes from Sublime's own syntax definitions (scopes such as
`entity.name.function` and `keyword.control.conditional`), so it works for
any language with a decent syntax. `Synesthesia: Explain Score` shows what
went into the current score, and the status bar shows the stage.

## Listening to a file or a project

- **file** (default): the file you are looking at, as you type.
- **project**: every source file in the window's folders, as it changes on
  disk. Made for coding agents: you don't need to look at any file to hear
  the agent work. Each file it writes plays an accent in that file's stage,
  rising or falling with the change, and the ambient music follows the whole
  project: quality averaged by file size, with every bug in every file
  counted. Synesthesia checks for changes twice a second and skips whatever
  git ignores.

Switch with `Synesthesia: Listen to File` and `Synesthesia: Listen to Project`.

## Modes

- **ambient** (default): a continuous stream of phrases in the current
  stage, plus the accents. When the stage changes, the next phrase starts
  right away.
- **chime**: only the accents, and a phrase when the stage changes.

## Install

Link this folder into Sublime Text's `Packages` folder under the name
`Synesthesia`. On macOS:

```bash
ln -s "$PWD" "$HOME/Library/Application Support/Sublime Text/Packages/Synesthesia"
```

Then run `Synesthesia: Play All Stages` from the command palette to hear the
whole range. Sounds are rendered once, in the background, and cached.

Requires Sublime Text 4. Sound is played with `afplay` on macOS and `paplay`,
`pw-play`, or `aplay` on Linux. On Windows it uses `winsound`, which cannot
overlap sounds, so each sound cuts off the one before.

## Commands

- `Synesthesia: Toggle` (<kbd>ctrl</kbd>+<kbd>alt</kbd>+<kbd>s</kbd>)
- `Synesthesia: Listen to File` and `Synesthesia: Listen to Project`
- `Synesthesia: Ambient Mode` and `Synesthesia: Chime Mode`
- `Synesthesia: Play Now` plays a phrase for the current score
- `Synesthesia: Explain Score`
- `Synesthesia: Play All Stages`
- `Preferences: Synesthesia Settings`

The same commands are under Tools > Synesthesia.

## Tests

```bash
python3 -m unittest discover -s tests
```
