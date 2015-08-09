var CompositeDisposable, Synesthesia;

CompositeDisposable = require('atom').CompositeDisposable;
var T = require('timbre');

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
    T("sin").play();
  }
};
