'''The unit test for module `coqide.stm`.'''

from unittest import TestCase
from unittest.mock import Mock, call

from coqide.stm import _State, _StateList, STM
from coqide.types import StateID, Sentence, Mark, Message


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
        view_mock.new_match.assert_called_once_with(
            (StateID(3), 1), Mark(1, 1), Mark(2, 8), flag)

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
        view_mock.new_match.assert_called_once_with(
            (StateID(3), 1), Mark(1, 1), Mark(2, 8), 'sent')
        state.set_flag('verified')
        view_mock.remove_match.assert_called_once_with((StateID(3), 1))
        view_mock.new_match.assert_called_with(
            (StateID(3), 2), Mark(1, 1), Mark(2, 8), 'verified')

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


class TestSTM(TestCase):
    '''Test class `coqide.stm.STM`.'''

    def test_init(self):
        '''Test method `init`.'''
        coqtop = Mock()
        view = Mock()
        coqtop.get_response.side_effect = [
            ('value', ({'init_state_id': StateID(3)}, None))]
        stm = STM(coqtop, view, None)
        stm.init()
        coqtop.call.assert_called_once_with('init', {})
        self.assertEqual(stm.get_tip_stop(), Mark(1, 1))

    @staticmethod
    def _new_stm(reset_mocks=True):
        '''Make a new STM object with pre-filled states.'''
        coqtop = Mock()
        view = Mock()
        coqtop.get_response.side_effect = [
            ('value', ({'init_state_id': StateID(1)}, None)),
            ('value', ({'state_id': StateID(2), 'closed_proof': None}, None)),
            ('value', ({'state_id': StateID(3), 'closed_proof': None}, None)),
            ('value', ({'goals': None}, None))]

        stm = STM(coqtop, view, None)
        stm.init()
        stm.add([Sentence('Theorem a:\n1 = 1.\n', Mark(1, 1), Mark(3, 1)),
                 Sentence('Proof.\n', Mark(3, 1), Mark(4, 1))])

        if reset_mocks:
            coqtop.reset_mock(return_value=True, side_effect=True)
            view.reset_mock(return_value=True, side_effect=True)

        return stm, coqtop, view

    def test_add_sentences(self):
        '''Test method `add` on adding a list of sentences.'''
        stm, coqtop, view = self._new_stm(reset_mocks=False)

        self.assertEqual(stm.get_tip_stop(), Mark(4, 1))
        self.assertListEqual(
            coqtop.call.call_args_list,
            [call('init', {}),
             call('add', {'command': 'Theorem a:\n1 = 1.\n', 'edit_id': -1,
                          'state_id': StateID(1), 'verbose': True}),
             call('add', {'command': 'Proof.\n', 'edit_id': -1,
                          'state_id': StateID(2), 'verbose': True}),
             call('goal', {})])
        self.assertListEqual(
            view.new_match.call_args_list,
            [call((StateID(2), 1), Mark(1, 1), Mark(3, 1), 'sent'),
             call((StateID(3), 1), Mark(3, 1), Mark(4, 1), 'sent')])

    def test_edit_at(self):
        '''Test method `edit_at` on editing at a specific mark.'''
        stm, coqtop, view = self._new_stm(reset_mocks=False)

        coqtop.reset_mock(side_effect=True)
        coqtop.get_response.side_effect = [
            ('value', ({'focused_proof': None}, None)),
            ('value', ({'goals': None}, None))]

        stm.edit_at(Mark(3, 3))

        self.assertEqual(stm.get_tip_stop(), Mark(3, 1))
        self.assertListEqual(
            coqtop.call.call_args_list,
            [call('edit_at', {'state_id': StateID(2)}),
             call('goal', {})])
        view.remove_match.assert_called_once_with((StateID(3), 1))

    def test_process_axiom(self):
        '''Test method `process_feedback` on feedback "axiom".'''
        stm, _, view = self._new_stm()

        match2_new = Mock()
        view.new_match.side_effect = [match2_new]

        stm.process_feedback(
            {'type': 'axiom', 'state_id': StateID(2), 'content': {}})

        view.remove_match.assert_called_once_with((StateID(2), 1))
        view.new_match.assert_called_once_with(
            (StateID(2), 2), Mark(1, 1), Mark(3, 1), 'axiom')

    def test_process_verified(self):
        '''Test method `process_feedback` on feedback "processed".'''
        stm, _, view = self._new_stm()

        match2_new = Mock()
        view.new_match.side_effect = [match2_new]

        stm.process_feedback(
            {'type': 'processed', 'state_id': StateID(2), 'content': {}})

        view.remove_match.assert_called_once_with((StateID(2), 1))
        view.new_match.assert_called_once_with(
            (StateID(2), 2), Mark(1, 1), Mark(3, 1), 'verified')

    def test_process_processed_axiom(self):
        '''Test method `process_feedback` on feedback "processed" with "axiom".'''
        stm, _, view = self._new_stm()

        match2_new = Mock()
        view.new_match.side_effect = [match2_new]

        stm.process_feedback(
            {'type': 'axiom', 'state_id': StateID(2), 'content': {}})
        stm.process_feedback(
            {'type': 'processed', 'state_id': StateID(2), 'content': {}})

        view.remove_match.assert_called_once_with((StateID(2), 1))
        view.new_match.assert_called_once_with(
            (StateID(2), 2), Mark(1, 1), Mark(3, 1), 'axiom')

    def test_process_plain_message(self):
        '''Test method `process_feedback` on non-error messages.'''
        stm, _, view = self._new_stm()

        stm.process_feedback(
            {'type': 'message',
             'state_id': StateID(2),
             'content': {
                 'message': Message(level='notice', text='Notice'),
                 'loc': None}})

        view.show_message.assert_called_once_with('notice', 'Notice')
