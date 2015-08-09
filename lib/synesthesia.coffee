{CompositeDisposable} = require 'atom'

module.exports = Synesthesia =
  activate: ->
    # Events subscribed to in atom's system can be easily cleaned up with a CompositeDisposable
    @subscriptions = new CompositeDisposable

    # Register command that toggles this view
    @subscriptions.add atom.commands.add 'atom-workspace', 'synesthesia:toggle': => @toggle()

  toggle: ->
    console.log 'Synesthesia was toggled!'
