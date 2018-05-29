'''Coq sentence.

In this module defines the coq sentence class Sentence, representing a sentence
ending with dots, ellipses or "-+*" and brackets.
'''

from collections import namedtuple
import logging

from . import actions


logger = logging.getLogger(__name__)           # pylint: disable=C0103


Mark = namedtuple('Mark', 'line col')
SentenceRegion = namedtuple('SentenceRegion', 'bufnr start stop command')


class OffsetToMark:
    '''A utility to translate offsets in a sentence to Mark.'''

    def __init__(self, region):
        '''Create a OffsetToMark with the given sentence region.'''
        self._line = region.start.line
        self._col = region.start.col
        self._text = region.command
        self._len = len(region.command)
        self._counter = 0

    def forward(self, offset):
        '''Forward the counter to the given offset.'''
        offset = min(offset, self._len)

        while self._counter < offset:
            if self._text[self._counter] == '\n':
                self._line += 1
                self._col = 1
            else:
                self._col += 1
            self._counter += 1

    def get_mark(self):
        '''Return the current mark.'''
        return Mark(self._line, self._col)


class Sentence:
    '''A Sentence object corresponds to a sentence in the Coq document like "Proof.".
    '''

    AXIOM = 'CoqStcAxiom'
    PROCESSING = 'CoqStcProcessing'
    PROCESSED = 'CoqStcProcessed'
    ERROR = 'CoqStcError'

    def __init__(self, region, state_id):
        '''Create a new sentence with state INIT.'''
        self.region = region
        self.state_id = state_id
        self._hlid = None
        self._flag = None
        self._hlcount = 0

    def set_processing(self, handle_action):
        '''Highlight the sentence to `PROCESSING`.'''
        if self._flag == self.PROCESSING:
            return
        self._highlight(self.PROCESSING, handle_action)
        self._flag = self.PROCESSING

    def set_processed(self, handle_action):
        '''Highlight the sentence to `PROCESSED`.

        If `_axiom_flag` is set, the highlight remains `AXIOM` unchanged.
        '''
        if self._flag in (self.AXIOM, self.PROCESSED, self.ERROR):
            return
        self._highlight(self.PROCESSED, handle_action)
        self._flag = self.PROCESSED

    def set_axiom(self, handle_action):
        '''Highlight the sentence to `UNSAFE`.'''
        self._highlight(self.AXIOM, handle_action)
        self._flag = self.AXIOM

    def set_error(self, location, message, handle_action):
        '''Highlight the error in the sentence and show the error message.'''
        self.unhighlight(handle_action)

        if location and location.start != location.stop:
            self._highlight_sub(Sentence.ERROR, location.start, location.stop, handle_action)
        else:
            self._highlight(Sentence.ERROR, handle_action)

        handle_action(actions.ShowMessage(message, 'error'))
        self._flag = self.ERROR

    def has_error(self):
        '''Return True of the sentence has error.'''
        return self._flag == self.ERROR

    def unhighlight(self, handle_action):
        '''Unhighlight the sentence.'''
        if self._hlid:
            handle_action(actions.UnhlRegion(*self._hlid))
            self._hlid = None
            self._flag = None

    def rehighlight(self, handle_action):
        '''Rehighlight the sentence according to the new region.'''
        if self._hlid is None:
            return

        handle_action(actions.UnhlRegion(*self._hlid))
        self._highlight(self._flag, handle_action)

    def _highlight(self, hlgroup, handle_action):
        '''Highlight the whole sentence to the given highlight group.'''
        self.unhighlight(handle_action)
        self._hlid = (self.region.bufnr, self.region.start, self.region.stop, self._hlcount)
        self._hlcount += 1
        handle_action(actions.HlRegion(*self._hlid, hlgroup=hlgroup))

    def _highlight_sub(self, hlgroup, start_offset, stop_offset, handle_action):
        '''Set the subregion of the sentence to the given highlight group.

        `highlight_func(highlight_region)` is a function that highlights the
        given region and return a callback that can withdraw the highlighted region.
        '''
        tomark = OffsetToMark(self.region)

        tomark.forward(start_offset)
        start = tomark.get_mark()

        tomark.forward(stop_offset)
        stop = tomark.get_mark()

        if start == stop:
            return

        self.unhighlight(handle_action)
        self._hlid = (self.region.bufnr, start, stop, self._hlcount)
        self._hlcount += 1
        handle_action(actions.HlRegion(*self._hlid, hlgroup=hlgroup))
