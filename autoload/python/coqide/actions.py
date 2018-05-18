'''Actions.

Actions are the commands that the plugin sends to Vim to update its UI components.

In this module define the actions and the base class of action handlers.
'''

from abc import ABC, abstractmethod
from collections import namedtuple

ShowGoals = namedtuple('ShowGoals', 'goals')
'''Show the goals in the Goal window.'''

ShowMessage = namedtuple('ShowMessage', 'message level')
'''Show the message in the Message window.'''

HlRegion = namedtuple('HlRegion', 'bufnr start stop token hlgroup')
'''Highlight the region between Marks `start` and `stop` of buffer `bufnr` to  `hlgroup`.

There could be more than one highlighting match applied on the range between `start` and
`stop`, where an integer `token` is used to distinguish them.

The tuple `(bufnr, start, stop, token)` can uniquely determine a highlight object.
'''

UnhlRegion = namedtuple('HlRegion', 'bufnr start stop token')
'''Unhighlight the region between Marks `start` and `stop` of buffer `bufnr`.'''

ConnLost = namedtuple('ConnLost', 'bufnr')
'''The connection for buffer `bufnr` is lost.'''


class ActionHandlerBase(ABC):                         # pylint: disable=R0903
    '''An base class for the action handler classes.

    In this base class, all the actions are dispatched to the corresponding methods.
    '''

    __ACTION_HANDLERS = (
        (ShowGoals, '_on_show_goals'),
        (ShowMessage, '_on_show_message'),
        (HlRegion, '_on_hl_region'),
        (UnhlRegion, '_on_unhl_region'),
        (ConnLost, '_on_conn_lost'),
    )

    def handle_action(self, action):
        '''Handle the action `action`.'''
        for atype, ahandler in self.__ACTION_HANDLERS:
            if isinstance(action, atype):
                handle = getattr(self, ahandler)
                handle(action)
                break
        else:
            raise TypeError('Action wrong type: {}'.format(action))

    @abstractmethod
    def _on_show_goals(self, action):
        pass

    @abstractmethod
    def _on_show_message(self, action):
        pass

    @abstractmethod
    def _on_hl_region(self, action):
        pass

    @abstractmethod
    def _on_unhl_region(self, action):
        pass

    @abstractmethod
    def _on_conn_lost(self, action):
        pass
