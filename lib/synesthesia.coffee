SynesthesiaView = require './synesthesia-view'
{CompositeDisposable} = require 'atom'

module.exports = Synesthesia =
  synesthesiaView: null
  modalPanel: null
  subscriptions: null

  activate: (state) ->
    @synesthesiaView = new SynesthesiaView(state.synesthesiaViewState)
    @modalPanel = atom.workspace.addModalPanel(item: @synesthesiaView.getElement(), visible: false)

    # Events subscribed to in atom's system can be easily cleaned up with a CompositeDisposable
    @subscriptions = new CompositeDisposable

    # Register command that toggles this view
    @subscriptions.add atom.commands.add 'atom-workspace', 'synesthesia:toggle': => @toggle()

  deactivate: ->
    @modalPanel.destroy()
    @subscriptions.dispose()
    @synesthesiaView.destroy()

  serialize: ->
    synesthesiaViewState: @synesthesiaView.serialize()

  toggle: ->
    console.log 'Synesthesia was toggled!'

    if @modalPanel.isVisible()
      @modalPanel.hide()
    else
      @modalPanel.show()
