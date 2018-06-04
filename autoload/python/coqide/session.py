'''Coq session.'''


from coqide.coqtopinstance import CoqtopInstance
from coqide.stm import STM


class Session:
    '''A loaded Coq source file and its coqtop interpreter.'''

    def __init__(self, view, vim, worker):
        '''Create a new session.'''
        self._coqtop = CoqtopInstance()
        self._coqtop.spawn(['coqtop', '-ideslave', '-main-channel', 'stdfds',
                            '-async-proofs', 'on'])
        self._view = view
        self._stm = STM(self._coqtop, self._view, self._on_feedback)
        self._vim = vim
        self._worker = worker

    def forward_one(self):
        '''Add the next sentence after the tip state to the STM.'''
        start = self._stm.get_tip_stop()
        sentence = self._vim.get_sentence_after(start)
        self._worker.submit(self._stm.add, [sentence])

    def backward_one(self):
        '''Backward to the previous state of the tip state.'''
        self._worker.submit(self._stm.edit_at_prev)

    def to_cursor(self):
        '''Forward or backward to the sentence under the cursor.'''
        tip_stop = self._stm.get_tip_stop()
        cursor = self._vim.get_cursor()
        if tip_stop < cursor:
            self._forward_between(tip_stop, cursor)
        elif tip_stop > cursor:
            self._worker.submit(self._stm.edit_at, cursor)

    def _forward_between(self, from_mark, to_mark):
        '''Add the sentences between `from_mark` and `to_mark` to the STM.'''
        sentences = []

        sentence = self._vim.get_sentence_after(from_mark)
        while sentence and sentence.stop <= to_mark:
            sentences.append(sentence)
            sentence = self._vim.get_sentence_after(sentence.stop)
        self._worker.submit(self._stm.add, sentences)

    def close(self):
        '''Close the session.'''
        self._coqtop.close()
        self._coqtop = None
        self._view = None
        self._stm = None
        self._vim = None
        self._worker = None

    def _on_feedback(self, feedback):
        '''A callback to process a feedback.'''
