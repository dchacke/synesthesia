var T = require('timbre'),
    sound = T('sin');

module.exports = {
  play: function () {
    sound.play();
    this.playing = true;
  },
  pause: function () {
    sound.pause();
    this.playing = false;
  }
};
