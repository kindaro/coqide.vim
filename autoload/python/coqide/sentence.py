'''Coq sentence.

In this module defines the coq sentence class Sentence, representing a sentence
ending with dots, ellipses or "-+*" and brackets.
'''

from collections import namedtuple
import logging


logger = logging.getLogger(__name__)           # pylint: disable=C0103


Mark = namedtuple('Mark', 'line col')
SentenceRegion = namedtuple('SentenceRegion', 'doc_id start stop command')
HighlightRegion = namedtuple('HighlightRegion', 'doc_id start stop hlgroup')


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
        self._unhighlight = None
        self._unhighlight_subregion = None
        self._axiom_flag = False
        self._error_flag = False

    def set_processing(self, ui_cmds):
        '''Highlight the sentence to `PROCESSING`.'''
        self._highlight(self.PROCESSING, ui_cmds.highlight)

    def set_processed(self, ui_cmds):
        '''Highlight the sentence to `PROCESSED`.

        If `_axiom_flag` is set, the highlight remains `AXIOM` unchanged.
        '''
        if self._axiom_flag:
            return
        self._highlight(self.PROCESSED, ui_cmds.highlight)

    def set_axiom(self, ui_cmds):
        '''Highlight the sentence to `UNSAFE`.'''
        self._axiom_flag = True
        self._highlight(self.AXIOM, ui_cmds.highlight)

    def set_error(self, location, message, ui_cmds):
        '''Highlight the error in the sentence and show the error message.'''
        self.unhighlight()

        if location and location.start != location.stop:
            self._highlight_subregion(Sentence.ERROR, location.start, location.stop,
                                      ui_cmds.highlight)
        else:
            self._highlight(Sentence.ERROR, ui_cmds.highlight)
        ui_cmds.show_message(message, True)
        self._error_flag = True

    def has_error(self):
        '''Return True of the sentence has error.'''
        return self._error_flag

    def unhighlight(self):
        '''Unhighlight the sentence.'''
        if self._unhighlight:
            self._unhighlight()
            self._unhighlight = None

        if self._unhighlight_subregion:
            self._unhighlight_subregion()
            self._unhighlight_subregion = None

        self._axiom_flag = False

    def _highlight(self, hlgroup, highlight_func):
        '''Highlight the whole sentence to the given highlight group.'''
        if self._unhighlight:
            self._unhighlight()
        hlregion = HighlightRegion(self.region.doc_id, self.region.start,
                                   self.region.stop, hlgroup)
        self._unhighlight = highlight_func(hlregion)

    def _highlight_subregion(self, hlgroup, start_offset, stop_offset, highlight_func):
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
        if self._unhighlight_subregion:
            self._unhighlight_subregion()
        hlregion = HighlightRegion(self.region.doc_id, start, stop, hlgroup)
        self._unhighlight_subregion = highlight_func(hlregion)
