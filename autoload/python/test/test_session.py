'''The unit test for module `coqide.session.Session`.'''

from unittest import TestCase
from unittest.mock import patch, Mock

from coqide.session import Session
from coqide.types import Mark, Sentence


# pylint: disable=W0212,C0103,R0201
class TestSession(TestCase):
    '''Test for class `coqide.session.Session`.'''

    @staticmethod
    def _worker_mock():
        '''Return a mock for worker.

        It calls the function immediately the function is submitted.'''
        def _submit(func, *args, **kwargs):
            func(*args, **kwargs)

        worker = Mock()
        worker.submit.side_effect = _submit
        return worker

    @patch('coqide.session.CoqtopInstance')
    @patch('coqide.session.STM')
    def test_constr(self, STM, CoqtopInstance):
        '''Test the constructor.'''
        view = Mock()
        vim = Mock()
        worker = Mock()
        session = Session(view, vim, worker)

        CoqtopInstance.assert_called_once_with()
        CoqtopInstance.return_value.spawn.assert_called_once_with(
            ['coqtop', '-ideslave', '-main-channel', 'stdfds',
             '-async-proofs', 'on'])

        STM.assert_called_once_with(
            CoqtopInstance.return_value, view, session._on_feedback)

    @patch('coqide.session.CoqtopInstance')
    @patch('coqide.session.STM')
    def test_forward_one(self, STM, _):
        '''Test method `forward_one`.'''
        stm = STM.return_value
        view = Mock()
        vim = Mock()
        worker = self._worker_mock()
        session = Session(view, vim, worker)

        sentence = Sentence('Proof.\n', Mark(1, 1), Mark(2, 1))
        stm.get_tip_stop.side_effect = [Mark(1, 1)]
        vim.get_sentence_after.side_effect = [sentence]

        session.forward_one()

        stm.add.assert_called_once_with([sentence])

    @patch('coqide.session.CoqtopInstance')
    @patch('coqide.session.STM')
    def test_backward_one(self, STM, _):
        '''Test method `backward_one`.'''
        stm = STM.return_value
        view = Mock()
        vim = Mock()
        worker = self._worker_mock()
        session = Session(view, vim, worker)

        session.backward_one()
        stm.edit_at_prev.assert_called_once_with()

    @patch('coqide.session.CoqtopInstance')
    @patch('coqide.session.STM')
    def test_to_cursor_forward(self, STM, _):
        '''Test method `to_cursor` on going forward.'''
        stm = STM.return_value
        view = Mock()
        vim = Mock()
        worker = self._worker_mock()
        session = Session(view, vim, worker)

        sentences = [
            Sentence('', Mark(2, 3), Mark(3, 5)),
            Sentence('', Mark(3, 5), Mark(4, 1)),
            Sentence('', Mark(4, 1), Mark(4, 9)),
            None
        ]
        stm.get_tip_stop.side_effect = [Mark(2, 3)]
        stm.get_end_stop.side_effect = [Mark(2, 3)]
        vim.get_cursor.side_effect = [Mark(4, 9)]
        vim.get_sentence_after.side_effect = sentences

        session.to_cursor()
        stm.add.assert_called_once_with(sentences[:-1])

    @patch('coqide.session.CoqtopInstance')
    @patch('coqide.session.STM')
    def test_to_cursor_backward(self, STM, _):
        '''Test method `to_cursor` on going backward.'''
        stm = STM.return_value
        view = Mock()
        vim = Mock()
        worker = self._worker_mock()
        session = Session(view, vim, worker)

        stm.get_tip_stop.side_effect = [Mark(4, 9)]
        stm.get_end_stop.side_effect = [Mark(4, 9)]
        vim.get_cursor.side_effect = [Mark(2, 3)]

        session.to_cursor()
        stm.edit_at.assert_called_once_with(Mark(2, 3))

    @patch('coqide.session.CoqtopInstance')
    @patch('coqide.session.STM')
    def test_close(self, _, CoqtopInstance):
        '''Test method `close`.'''
        view = Mock()
        vim = Mock()
        worker = self._worker_mock()
        session = Session(view, vim, worker)
        session.close()
        CoqtopInstance.return_value.close.assert_called_once_with()
