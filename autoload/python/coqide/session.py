'''The Coq session module.

In this module defines Session, representing a Coq file that is being edited.
'''

import logging


from . import actions
from . import events


logger = logging.getLogger(__name__)     # pylint: disable=C0103


def _chain_feedback_handlers(handlers):
    '''Chain `handlers` into one feedback handler.'''
    def chained_handler(feedback):
        '''The chained feedback handler.'''
        for handler in handlers:
            if handler(feedback):
                return True
        return False
    return chained_handler


class _ActionProxy(actions.ActionHandlerBase):                 # pylint: disable=R0903
    '''This class proxies the actions to the upper handler and the internal handler.

    It propagates the actions to the upper handler in accord with the focus and active
    status of the corresponding buffer. "Focus" means the cursor is in the buffer.
    "Active" means the buffer is present in some window.

    Actions that will not be propagated to the upper handler if buffer unfocus:
    - ShowGoals
    - ShowMessage

    Actions that will not be propated to the upper handler if buffer inactive:
    - HlRegion
    - UnhlRegion
    '''

    def __init__(self, is_focused, is_active, handle_internally, handle_in_upper):
        self._is_focused = is_focused
        self._is_active = is_active
        self._handle_internally = handle_internally
        self._handle_in_upper = handle_in_upper

    def _on_show_goals(self, action):
        self._handle_internally(action)
        if self._is_focused():
            self._handle_in_upper(action)

    def _on_show_message(self, action):
        self._handle_internally(action)
        if self._is_focused():
            self._handle_in_upper(action)

    def _on_clear_message(self, action):
        self._handle_internally(action)
        if self._is_focused():
            self._handle_in_upper(action)

    def _on_hl_region(self, action):
        self._handle_internally(action)
        if self._is_active():
            self._handle_in_upper(action)

    def _on_unhl_region(self, action):
        self._handle_internally(action)
        if self._is_active():
            self._handle_in_upper(action)

    def _on_conn_lost(self, action):
        self._handle_internally(action)
        self._handle_in_upper(action)


class _InternalUI(actions.ActionHandlerBase, events.EventHandlerBase):
    '''This class records the UI state of a Coq session.

    It may be or may be not in synchronization with the UI state of Vim depending on the focus and
    active state of the corresponding buffer.
    '''

    def __init__(self):
        '''Create an empty UI.'''
        self._goals = None
        self._messages = []
        self._hl_map = {}
        self._focused = False
        self._active = False

    def is_focused(self):
        '''Return True if the window is focused.'''
        return self._focused

    def is_active(self):
        '''Return True if the buffer is shown in some window.'''
        return self._active

    def _on_show_goals(self, action):
        self._goals = action.goals

    def _on_show_message(self, action):
        self._messages.append((action.message, action.level))

    def _on_clear_message(self, action):
        self._messages = []

    def _on_hl_region(self, action):
        hlid = (action.bufnr, action.start, action.stop, action.token)
        self._hl_map[hlid] = action.hlgroup

    def _on_unhl_region(self, action):
        hlid = (action.bufnr, action.start, action.stop, action.token)
        del self._hl_map[hlid]

    def _on_conn_lost(self, _):
        pass

    def _on_focus(self, _, handle_action):
        self._focused = True
        handle_action(actions.ShowGoals(self._goals))
        for message, level in self._messages:
            handle_action(actions.ShowMessage(message, level))

    def _on_unfocus(self, _1, _2):
        self._focused = False

    def _on_active(self, _, handle_action):
        self._active = True
        for hlid, hlgroup in self._hl_map.items():
            handle_action(actions.HlRegion(*hlid, hlgroup=hlgroup))

    def _on_inactive(self, _, handle_action):
        self._active = False
        for hlid in self._hl_map:
            handle_action(actions.UnhlRegion(*hlid))


class Session:
    '''A Coq file that is being edited.'''

    def __init__(self, make_stm, make_coqtop_handle, feedback_handle_action):
        '''Create a new Coq session.

        `bufnr` is the number of the corresponding buffer. It is not used directly,
        only as an identifier for actions.
        '''
        self._internal_ui = _InternalUI()

        stm = make_stm()
        stm_fb_handler = stm.make_feedback_handler(self._proxy(feedback_handle_action))
        fb_handler = _chain_feedback_handlers([stm_fb_handler])
        coqtop = make_coqtop_handle(fb_handler)

        self._stm = stm
        self._coqtop = coqtop

    def init(self, handle_action):
        '''Initialize the STM.'''
        self._stm.init(self._coqtop.call_async, handle_action)

    def forward(self, sregion, handle_action):
        '''Process a new sentence region and go forward.'''
        self._stm.forward(sregion, self._coqtop.call_async, self._proxy(handle_action))

    def forward_many(self, sregions, handle_action):
        '''Process a list of new sentence regions and go forward.'''
        self._stm.forward_many(sregions, self._coqtop.call_async, self._proxy(handle_action))

    def backward(self, handle_action):
        '''Go backward one sentence.'''
        self._stm.backward(self._coqtop.call_async, self._proxy(handle_action))

    def backward_before_mark(self, mark, handle_action):
        '''Go backward to the sentence before `mark`.'''
        self._stm.backward_before_mark(mark, self._coqtop.call_async, self._proxy(handle_action))

    def clear_message(self, handle_action):
        '''Clear the messages.'''
        self._proxy(handle_action)(actions.ClearMessage())

    def handle_event(self, event, handle_action):
        '''Handle the event generated by the user.'''
        self._internal_ui.handle_event(event, handle_action)

    def close(self, handle_action):
        '''Close the session.'''
        self._stm.close(handle_action)
        self._coqtop.terminate()

    def is_busy(self):
        '''Return True if there is scheduled tasks that has not been done.'''
        return self._stm.is_busy()

    def get_last_stop(self):
        '''Return the stop of the last sentence.'''
        return self._stm.get_last_stop()

    def _proxy(self, handle_action_in_upper):
        '''Get a proxy of the action handlers.'''
        return _ActionProxy(self._internal_ui.is_focused, self._internal_ui.is_active,
                            self._internal_ui.handle_action, handle_action_in_upper).handle_action
