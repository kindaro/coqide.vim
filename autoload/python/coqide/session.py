'''The Coq session module.

In this module defines Session, representing a Coq file that is being edited.
'''

import logging


logger = logging.getLogger(__name__)     # pylint: disable=C0103


def chain_feedback_handlers(handlers):
    '''Chain `handlers` into one feedback handler.'''
    def chained_handler(feedback):
        '''The chained feedback handler.'''
        for handler in handlers:
            if handler(feedback):
                return True
        return False
    return chained_handler


class UICommandProxy:
    '''This class catches the UI update commands and update the bound UIState object.

    Some UI commands that updates the contents of the shared UI components like the goal and message
    window are sent to UI only when the session is focused.
    '''

    def __init__(self, ui_state, proxied_ui_cmds):
        self._ui_state = ui_state
        self._proxied_ui_cmds = proxied_ui_cmds

    def __getattr__(self, name):
        '''The default behavior is to call the original command unless being proxied.'''
        return getattr(self._proxied_ui_cmds, name)

    def show_goal(self, goals):
        '''Update UI if focused. Save the goals always.'''
        self._ui_state.set_goals(goals)
        if self._ui_state.is_focused():
            self._proxied_ui_cmds.show_goal(goals)

    def show_message(self, message, is_error):
        '''Update UI if focused. Save the message always.'''
        self._ui_state.set_message(message, is_error)
        if self._ui_state.is_focused():
            self._proxied_ui_cmds.show_message(message, is_error)

    def highlight(self, hlregion):
        '''Save the highlighted region and update UI if the buffer is active.'''
        if self._ui_state.is_active():
            unhighlight = self._proxied_ui_cmds.highlight(hlregion)
        else:
            unhighlight = None
        return self._ui_state.add_highlight_region(hlregion, unhighlight)


class UIState:
    '''This class records the UI state of a Coq session, to be precise, the goals,
    messages and other contents of the UI components.
    '''

    _EVENT_HANDLERS = {
        'focus': '_on_focus',
        'unfocus': '_on_unfocus',
        'active': '_on_active',
        'inactive': '_on_inactive',
    }

    def __init__(self):
        '''Create an empty UIState.'''
        self._goals = None
        self._message = ('', False)
        self._hl_map = {}
        self._hl_next_index = 0
        self._focused = False
        self._active = False

    def handle_event(self, event, ui_cmds):
        '''The event handler.'''
        logger.debug('UIState handle event: %s', event)
        handler = getattr(self, self._EVENT_HANDLERS[event])
        handler(ui_cmds)

    def is_focused(self):
        '''Return True if the window is focused.'''
        return self._focused

    def is_active(self):
        '''Return True if the buffer is shown in some window.'''
        return self._active

    def set_goals(self, goals):
        '''Set the goals.'''
        self._goals = goals

    def set_message(self, message, is_error):
        '''Set the message.'''
        self._message = (message, is_error)

    def add_highlight_region(self, hlregion, unhl):
        ''''Add a highlight region and return the unhighlight callback.'''
        hlobj = {'hlregion': hlregion, 'unhl': unhl}
        hlindex = self._hl_next_index
        self._hl_next_index += 1
        self._hl_map[hlindex] = hlobj
        return self._make_unhighlight(hlindex)

    def _make_unhighlight(self, hlindex):
        '''Return a function that remove the given highlight region.'''
        def unhighlight():
            '''Remove the highlight region.'''
            hlobj = self._hl_map[hlindex]
            if hlobj['unhl']:
                hlobj['unhl']()
            del self._hl_map[hlindex]
        return unhighlight

    def _on_focus(self, ui_cmds):
        '''The handler for the event that the buffer window get focused.'''
        self._focused = True
        ui_cmds.show_goal(self._goals)
        ui_cmds.show_message(self._message[0], self._message[1])

    def _on_unfocus(self, _):
        '''The handler for the event that the buffer window loses focus.'''
        self._focused = False

    def _on_active(self, ui_cmds):
        '''The handler for the event that the buffer is shown in a window.'''
        self._active = True
        for item in self._hl_map.values():
            item['unhl'] = ui_cmds.highlight(item['hlregion'])

    def _on_inactive(self, _):
        '''The handler for the event that the buffer is hidden from a window.'''
        self._active = False
        for item in self._hl_map.values():
            item['unhl']()
            item['unhl'] = None


class Session:
    '''A Coq file that is being edited.'''

    def __init__(self, make_stm, make_coqtop_handle, ui_cmds):
        '''Create a new Coq session.'''
        self._ui_state = UIState()

        stm = make_stm()
        stm_fb_handler = stm.make_feedback_handler(self._proxy(ui_cmds))
        fb_handler = chain_feedback_handlers([stm_fb_handler])
        handle = make_coqtop_handle('utf-8', fb_handler)
        stm.init(handle.call_async, ui_cmds)

        self._stm = stm
        self._handle = handle

    def forward(self, sregion, ui_cmds):
        '''Process a new sentence region and go forward.'''
        self._stm.forward(sregion, self._handle.call_async, self._proxy(ui_cmds))

    def forward_many(self, sregions, ui_cmds):
        '''Process a list of new sentence regions and go forward.'''
        self._stm.forward_many(sregions, self._handle.call_async, self._proxy(ui_cmds))

    def backward(self, ui_cmds):
        '''Go backward one sentence.'''
        self._stm.backward(self._handle.call_async, self._proxy(ui_cmds))

    def backward_before_mark(self, mark, ui_cmds):
        '''Go backward to the sentence before `mark`.'''
        self._stm.backward_before_mark(mark, self._handle.call_async, self._proxy(ui_cmds))

    def handle_event(self, event, ui_cmds):
        '''The event handler.'''
        self._ui_state.handle_event(event, ui_cmds)

    def close(self):
        '''Close the session.'''
        self._stm.close()
        self._handle.terminate()

    def is_busy(self):
        '''Return True if there is scheduled tasks that has not been done.'''
        return self._stm.is_busy()

    def get_last_stop(self):
        '''Return the stop of the last sentence.'''
        return self._stm.get_last_stop()

    def _proxy(self, proxied_ui_cmds):
        '''Get a proxy of the UI commands.'''
        return UICommandProxy(self._ui_state, proxied_ui_cmds)
