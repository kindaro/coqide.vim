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


class UIState:
    '''This class records the UI state of a Coq session, to be precise, the goals,
    messages and other contents of the shared UI components.
    '''

    def __init__(self):
        '''Create an empty UIState.'''
        self._goals = None
        self._message = ('', False)
        self._focused = False

    def focus_and_update(self, ui_cmds):
        '''Focus the session (cursor in the window) and update the shared UI components.'''
        self._focused = True
        ui_cmds.show_goal(self._goals)
        ui_cmds.show_message(self._message[0], self._message[1])

    def unfocus_and_update(self, _):
        '''Unfocus the session (cursor out of the window) and update the shared UI components.'''
        self._focused = False

    def is_focused(self):
        '''Return True if the window is focused.'''
        return self._focused

    def set_goals(self, goals):
        '''Set the goals.'''
        self._goals = goals

    def set_message(self, message, is_error):
        '''Set the message.'''
        self._message = (message, is_error)


class Session:
    '''A Coq file that is being edited.'''

    def __init__(self, make_stm, make_coqtop_handle, ui_cmds):
        '''Create a new Coq session.'''
        stm = make_stm()
        stm_fb_handler = stm.make_feedback_handler(ui_cmds)
        fb_handler = chain_feedback_handlers([stm_fb_handler])
        handle = make_coqtop_handle('utf-8', fb_handler)
        stm.init(handle.call_async, ui_cmds)

        self._stm = stm
        self._handle = handle
        self._ui_state = UIState()

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

    def focus(self, ui_cmds):
        '''Focus the session (cursor in this window).'''
        self._ui_state.focus_and_update(ui_cmds)

    def unfocus(self, ui_cmds):
        '''Unfocus the session (cursor out of this window).'''
        self._ui_state.unfocus_and_update(ui_cmds)

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
