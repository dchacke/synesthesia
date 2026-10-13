# Synesthesia

Hear the state of your code in Sublime Text.

Synesthesia plays your code. The music walks through it line by line on
recorded instruments, so every file has its own melody, and when the code
changes the music jumps to where it changed. How good the code is decides
how the music sounds: beautiful code is a harp over a cello section; worse
code moves to marimba, then piano in a minor key, then tubular bells and a
droning contrabass, until cursed code is a singing saw sliding over
trembling strings, gongs and bowed cymbals. Changes also get a short accent: rising if things got better,
falling if they got worse.

## Stages

| Health    | Stage     | Sound                                                       |
| --------- | --------- | ----------------------------------------------------------- |
| 0.90–1.00 | beautiful | harp in major pentatonic, glockenspiel, cello section       |
| 0.75–0.90 | good      | harp in major, pizzicato bass                               |
| 0.60–0.75 | decent    | marimba in open fourths and fifths, pizzicato bass          |
| 0.45–0.60 | meh       | piano in minor, cello section                               |
| 0.30–0.45 | bad       | sparse piano in Phrygian, tubular bells, sustained bass     |
| 0.15–0.30 | awful     | detuned piano clusters, tubular bells, cello tremolo, timpani |
| 0.00–0.15 | cursed    | a singing saw over contrabass tremolo, gongs, bowed cymbal  |

As things get worse the tempo slows, the timing loosens, notes drop out,
the tuning drifts and the room grows from a small hall into a cavern.

## How the code becomes music

Each line is one step. Its indentation sets how high it sits in the
stage's scale, so deeper code climbs; a hash of its text nudges the note,
so different lines make different melodies while identical lines sound
identical (duplicated code sounds repetitive); and its length sets how hard
it's played. Blank lines are rests. Comments ring on a second instrument,
lines that start functions bring in the bass, and lines the syntax
definition flags as broken sound a dissonant cluster as the music passes
them. Eight lines make a bar; each bar is rendered once and cached, so code
that hasn't changed costs nothing to play again.

The instruments are real recordings from
[VSCO 2 Community Edition](https://versilian-studios.com/vsco-community/),
which is public domain; see [samples/README.md](samples/README.md). The
singing saw, an almost pure tone, is synthesized.

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
  the agent work. The music walks through every file in the project, one
  after another. Each file the agent writes plays an accent in that file's
  stage, rising or falling with the change, and the music jumps to where it
  changed, then walks on from there. The stage follows the whole project: quality
  averaged by file size, with every bug in every file counted. Synesthesia
  checks for changes twice a second and skips whatever git ignores.

Switch with `Synesthesia: Listen to File` and `Synesthesia: Listen to Project`.

## Modes

- **ambient** (default): the code played continuously, plus the accents.
  When the stage changes, the next bar starts right away.
- **chime**: only the accents, and a bar when the stage changes.

## Install

Link this folder into Sublime Text's `Packages` folder under the name
`Synesthesia`. On macOS:

```bash
ln -s "$PWD" "$HOME/Library/Application Support/Sublime Text/Packages/Synesthesia"
```

Then run `Synesthesia: Play All Stages` from the command palette to hear the
current file in every stage.

Requires Sublime Text 4. Sound is played with `afplay` on macOS and `paplay`,
`pw-play`, or `aplay` on Linux. On Windows it uses `winsound`, which cannot
overlap sounds, so each sound cuts off the one before.

## Commands

- `Synesthesia: Toggle` (<kbd>ctrl</kbd>+<kbd>alt</kbd>+<kbd>s</kbd>)
- `Synesthesia: Listen to File` and `Synesthesia: Listen to Project`
- `Synesthesia: Ambient Mode` and `Synesthesia: Chime Mode`
- `Synesthesia: Play Now` plays a bar of the current code
- `Synesthesia: Explain Score`
- `Synesthesia: Play All Stages`
- `Preferences: Synesthesia Settings`

The same commands are under Tools > Synesthesia.

## Tests

```bash
python3 -m unittest discover -s tests
```
