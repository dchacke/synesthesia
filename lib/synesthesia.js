var CompositeDisposable, Synesthesia, T, playing, sound;

CompositeDisposable = require('atom').CompositeDisposable;
T = require('timbre');
sound = T('sin');
playing = false;

module.exports = Synesthesia = {
  activate: function() {
    this.subscriptions = new CompositeDisposable;
    return this.subscriptions.add(atom.commands.add('atom-workspace', {
      'synesthesia:toggle': (function(_this) {
        return function() {
          return _this.toggle();
        };
      })(this)
    }));
  },
  toggle: function() {
    console.log('Synesthesia was toggled!');

    if (playing) {
      console.log('pausing...');
      sound.pause();
      playing = false;
    } else {
      console.log('resuming...');
      sound.play();
      playing = true;
    }
  }
};
