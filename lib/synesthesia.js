var CompositeDisposable, Synesthesia;

CompositeDisposable = require('atom').CompositeDisposable;

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
    return console.log('Synesthesia was toggled!');
  }
};
