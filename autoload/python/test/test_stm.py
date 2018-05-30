'''The unit test for module `coqide.stm`.'''

from unittest import TestCase
from unittest.mock import Mock

from coqide.stm import _State
from coqide.types import StateID, Sentence, Mark


class TestState(TestCase):
    '''Test class `coqide.stm._State`.'''

    _SENTENCE_EX = Sentence('Theorem a:\n  1 = 1.',
                            Mark(1, 1),
                            Mark(2, 8))

    def _test_set_flag_simple(self, flag):
        '''Test setting the flag to `flag` without `loc`.'''
        view_mock = Mock()
        state = _State(StateID(3), self._SENTENCE_EX, view_mock)
        state.set_flag(flag)
        view_mock.new_highlight.assert_called_once_with(
            StateID(3), Mark(1, 1), Mark(2, 8), flag)

    def test_set_sent_flag(self):
        '''Test setting the flag to "sent".'''
        self._test_set_flag_simple('sent')

    def test_set_axiom_flag(self):
        '''Test setting the flag to "axiom".'''
        self._test_set_flag_simple('axiom')

    def test_set_verified_flag(self):
        '''Test setting the flag to "verified".'''
        self._test_set_flag_simple('verified')

    def test_set_flag_twice(self):
        '''Test setting the flag when there is another flag.'''
        view_mock = Mock()
        state = _State(StateID(3), self._SENTENCE_EX, view_mock)
        state.set_flag('sent')
        view_mock.new_highlight.assert_called_once_with(
            StateID(3), Mark(1, 1), Mark(2, 8), 'sent')
        state.set_flag('verified')
        view_mock.new_highlight.return_value.remove.assert_called_once()
        view_mock.new_highlight.assert_called_with(
            StateID(3), Mark(1, 1), Mark(2, 8), 'verified')

    def test_offset_to_mark(self):
        '''Test the function transforming offsets in the sentence to marks.'''
        view_mock = Mock()
        state = _State(StateID(3), self._SENTENCE_EX, view_mock)

        mark = state.offset_to_mark(3)
        self.assertEqual(mark, Mark(1, 4))

        mark = state.offset_to_mark(12)
        self.assertEqual(mark, Mark(2, 2))

        mark = state.offset_to_mark(18)
        self.assertEqual(mark, Mark(2, 8))
