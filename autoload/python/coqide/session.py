'''Coq session.'''


from coqide import vimsupport as vims
from coqide.coqtopinstance import CoqtopInstance
from coqide.stm import STM
from coqide.views import SessionView


class Session:
    '''A loaded Coq source file and its coqtop interpreter.'''

    def __init__(self, bufnr, tabpage_view, executor):
        '''Create a new session.'''
        self._coqtop = CoqtopInstance()
        self._coqtop.spawn(['coqtop', '-ideslave', '-main-channel', 'stdfds',
                            '-async-proofs', 'on'])
        self._view = SessionView(bufnr, tabpage_view)
        self._executor = executor
        self._stm = STM(self._coqtop, self._view, lambda _: None)

    def forward_one(self):
        '''Add the next sentence after the tip state to the STM.'''
        start = self._stm.get_tip_stop()
        sentence = vims.get_sentence_after(start)
        self._executor.submit(self._stm.add, [sentence])

    def backward_one(self):
        '''Backward to the previous state of the tip state.'''
        self._executor.submit(self._stm.edit_at_prev)

    def to_cursor(self):
        '''Forward or backward to the sentence under the cursor.'''
        tip_stop = self._stm.get_tip_stop()
        cursor = vims.get_cursor()
        if tip_stop < cursor:
            self._forward_between(tip_stop, cursor)
        elif tip_stop > cursor:
            self._executor.submit(self._stm.edit_at, cursor)

    def draw_view(self):
        '''Draw the session view in the Vim UI.'''
        self._view.draw()

    def _forward_between(self, from_mark, to_mark):
        '''Add the sentences between `from_mark` and `to_mark` to the STM.'''
        sentences = []

        sentence = vims.get_sentence_after(from_mark)
        while sentence.stop <= to_mark:
            sentences.append(sentence)
            sentence = vims.get_sentence_after(sentence.stop)
        self._executor.submit(self._stm.add, sentences)

    def close(self):
        '''Close the session.'''
        self._coqtop.close()
        self._view.destroy()
        self._coqtop = None
        self._view = None
        self._stm = None
