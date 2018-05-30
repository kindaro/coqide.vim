'''The unit test for module `coqide.stm`.'''

from unittest import TestCase
from unittest.mock import Mock

from coqide.stm import _State, _StateList
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


class TestStateList(TestCase):
    '''Test class `coqide.stm._StateList`.'''

    def test_init(self):
        '''Test method `init`.'''
        slist = _StateList()
        inits = _State.initial(StateID(1))
        slist.init(inits)
        self.assertEqual(slist.find_by_id(StateID(1)), inits)
        self.assertEqual(slist.find_by_mark(Mark(1, 1)), inits)
        self.assertEqual(list(slist.iter_after(inits)), [])

    def test_find_by_mark(self):
        '''Test method `find_by_mark`.'''
        slist = _StateList()
        sta1 = _State.initial(StateID(1))
        slist.init(sta1)
        sta2 = _State(StateID(2), Sentence('', Mark(1, 1), Mark(2, 3)), None)
        slist.insert(sta1, sta2)
        sta3 = _State(StateID(3), Sentence('', Mark(2, 3), Mark(2, 10)), None)
        slist.insert(sta2, sta3)
        self.assertEqual(slist.find_by_mark(Mark(2, 4)), sta2)
        self.assertEqual(slist.find_by_mark(Mark(3, 1)), sta3)

    def test_insert_end(self):
        '''Test inserting at the end.'''
        slist = _StateList()
        sta1 = _State.initial(StateID(1))
        slist.init(sta1)
        sta2 = _State(StateID(2), Sentence('', Mark(1, 1), Mark(2, 3)), None)
        slist.insert(sta1, sta2)
        sta3 = _State(StateID(3), Sentence('', Mark(2, 3), Mark(2, 10)), None)
        slist.insert(sta2, sta3)
        self.assertEqual(list(slist.iter_after(sta1)), [sta2, sta3])

    def test_insert_middle(self):
        '''Test inserting in the middle.'''
        slist = _StateList()
        sta1 = _State.initial(StateID(1))
        slist.init(sta1)
        sta2 = _State(StateID(2), Sentence('', Mark(1, 1), Mark(2, 3)), None)
        slist.insert(sta1, sta2)
        sta3 = _State(StateID(3), Sentence('', Mark(2, 3), Mark(2, 10)), None)
        slist.insert(sta1, sta3)
        self.assertEqual(list(slist.iter_after(sta1)), [sta3, sta2])

    def test_remove_between(self):
        '''Test method `remove_between`.'''
        slist = _StateList()
        sta1 = _State.initial(StateID(1))
        slist.init(sta1)
        sta2 = _State(StateID(2), Sentence('', Mark(1, 1), Mark(2, 3)), None)
        slist.insert(sta1, sta2)
        sta3 = _State(StateID(3), Sentence('', Mark(2, 3), Mark(2, 10)), None)
        slist.insert(sta2, sta3)
        slist.remove_between(sta1, sta2)
        self.assertEqual(list(slist.iter_after(sta1)), [sta3])

    def test_remove_between_end(self):
        '''Test method `remove_between` to the end.'''
        slist = _StateList()
        sta1 = _State.initial(StateID(1))
        slist.init(sta1)
        sta2 = _State(StateID(2), Sentence('', Mark(1, 1), Mark(2, 3)), None)
        slist.insert(sta1, sta2)
        sta3 = _State(StateID(3), Sentence('', Mark(2, 3), Mark(2, 10)), None)
        slist.insert(sta2, sta3)
        slist.remove_between(sta1, sta3)
        self.assertEqual(list(slist.iter_after(sta1)), [])

    def test_remove_after(self):
        '''Test method `remove_after`.'''
        slist = _StateList()
        sta1 = _State.initial(StateID(1))
        slist.init(sta1)
        sta2 = _State(StateID(2), Sentence('', Mark(1, 1), Mark(2, 3)), None)
        slist.insert(sta1, sta2)
        sta3 = _State(StateID(3), Sentence('', Mark(2, 3), Mark(2, 10)), None)
        slist.insert(sta2, sta3)
        slist.remove_after(sta1)
        self.assertEqual(list(slist.iter_after(sta1)), [])
