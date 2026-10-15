# Changelog

## 0.2.2 (2026-10-15)

- On Windows, listing a project’s files with git and checking whether code
  parses no longer flash a console window.
- `Preferences: Synesthete Key Bindings` shows an example binding you can
  copy as is, without uncommenting it.

## 0.2.1 (2026-10-15)

### Fairer scores

- Code aligned under an argument or a string counts as one level deeper,
  however far it’s indented, so breaking a long line no longer makes code
  look worse. Nesting no longer depends on the tab size.
- A `{` that opens a hash or object literal continues an expression, as
  round and square brackets do, rather than nest. A block’s `{` still nests.
- URLs don’t count toward a line’s length, since they can’t be broken.

## 0.2.0 (2026-10-14)

### New

- **Tiles.** `Synesthete: Open Tiles` opens a browser tab with every file as
  a tile in one square, colored by its health from green for beautiful to
  dark red for cursed. A file that changes glows and fades, ringed green if it
  got better and red if it got worse, so you can watch an agent work through
  the project. Hover a tile to see its file and score.

### Fairer scores

- Functions defined inside other functions are judged on their own, so code
  wrapped in one big function no longer counts twice and scores as one huge,
  tangled function.
- Nesting is measured from the text. A line starting with a string no longer
  counts the string’s width as indentation, and lines inside round or square
  brackets, such as a call’s arguments or nested arrays, continue an
  expression rather than nest.
- Project mode skips `package-lock.json` and `npm-shrinkwrap.json`, which
  counted as thousands of lines of code and sank a project’s score.

### Fixes

- When WebGL is off, as in Safari’s Lockdown Mode, the visualizer says why
  the tunnel is missing instead of showing a black page.
- The README explains how to use Synesthete.

## 0.1.2 (2026-10-13)

- In file mode, while no code file is open, Synesthete plays the window’s
  project, so opening a folder without opening a file plays the project
  right away instead of nothing. Play Now and Explain Score use it too.

## 0.1.1 (2026-10-13)

- Synesthete no longer binds <kbd>ctrl</kbd>+<kbd>alt</kbd>+<kbd>s</kbd>,
  as Package Control asks of packages. The README shows how to bind it
  yourself, and `Preferences: Synesthete Key Bindings` opens your key
  bindings next to the package’s.
- Installs leave out the tests and tools.

## 0.1.0 (2026-10-13)

The first release as a Sublime Text package, rewritten from the 2014 Atom
package Synesthesia.

- Plays your code line by line on recorded instruments, in seven stages from
  beautiful to cursed, with a short accent whenever it changes: rising if
  things got better, falling if they got worse.
- Scores code from Sublime’s syntax definitions: long and branchy
  functions, deep nesting, duplication, long lines, untidiness, and bugs,
  including code the language’s own parser rejects.
- Listens to the file you’re looking at, or to every file in the project as
  it changes on disk.
- Ambient and chime modes, `Synesthete: Explain Score`, and the stage in the
  status bar.
- The map, a bird’s-eye view of the code in a Sublime tab, and the
  visualizer, a tunnel through the code in the browser.
