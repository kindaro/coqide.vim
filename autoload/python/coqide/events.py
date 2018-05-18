'''Events.

Events are the commands that Vim sends to the plugin to notify the operations of the user.

In this module define the events and the base class of event handlers.
'''

from abc import ABC, abstractmethod
from collections import namedtuple


Focus = namedtuple('Focus', '')
Unfocus = namedtuple('Unfocus', '')
Active = namedtuple('Active', '')
Inactive = namedtuple('Inactive', '')


class EventHandlerBase(ABC):                 # pylint: disable=R0903
    '''The base class for event handler classes.'''

    __EVENT_HANDLERS = (
        (Focus, '_on_focus'),
        (Unfocus, '_on_unfocus'),
        (Active, '_on_active'),
        (Inactive, '_on_inactive'),
    )

    def handle_event(self, event, handle_action):
        '''Handle the event.'''
        for etype, ehandler in self.__EVENT_HANDLERS:
            if isinstance(event, etype):
                handle = getattr(self, ehandler)
                handle(event, handle_action)
                break
        else:
            raise TypeError('Event wrong type: {}'.format(event))

    @abstractmethod
    def _on_focus(self, event, handle_action):
        pass

    @abstractmethod
    def _on_unfocus(self, event, handle_action):
        pass

    @abstractmethod
    def _on_active(self, event, handle_action):
        pass

    @abstractmethod
    def _on_inactive(self, event, handle_action):
        pass
