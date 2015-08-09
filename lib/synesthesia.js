var CompositeDisposable, Synesthesia, Sound;

CompositeDisposable = require('atom').CompositeDisposable;
Sound = require('./sound.js');

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

    if (Sound.playing) {
      console.log('pausing...');
      Sound.pause();
    } else {
      console.log('resuming...');
      Sound.play();
    }
  }
};
