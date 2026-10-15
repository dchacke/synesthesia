# Changelog

## 0.2.0

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
