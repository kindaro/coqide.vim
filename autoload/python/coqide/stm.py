'''State and state machine.'''

import logging

from .types import StateID, Mark


logger = logging.getLogger(__name__)         # pylint: disable=C0103


class _State:
    '''The state in a state machine.

    A state contains a sentence in the document and the processing
    result from the coqtop process.
    '''

    def __init__(self, state_id, sentence, view):
        self.state_id = state_id
        self.sentence = sentence
        self._flag = None
        self._view = view
        self._match_ids = []
        self._next_rev_num = 1

    def move(self, line_offset):
        '''Move the position of the sentence.'''
        if self._view:
            self._view.move_match(self.state_id, line_offset)

    def set_flag(self, flag, loc=None):
        '''Set the flag of the state to `flag` to indicate in which stage
        the sentence is being processed.

        The values can be:
        - "sent": the sentence has been sent to coqtop but not completed;
        - "axiom": the sentence is accepted as an axiom;
        - "verified": the sentence is verified;
        - "error": the sentence contains errors.

        If `flag == "error"`, `loc` is the tuple marking the error region.
        '''
        if not self._view:
            return

        self._flag = flag
        for match_id in self._match_ids:
            self._view.remove_match(match_id)
        self._match_ids.clear()

        if flag is None:
            return

        new_match_id = self._alloc_match_id()
        self._view.new_match(new_match_id, self.sentence.start,
                             self.sentence.stop, flag)
        self._match_ids.append(new_match_id)

        if flag == 'error' and loc and loc.start and loc.stop:
            new_match_id = self._alloc_match_id()
            part_start = self.offset_to_mark(loc.start)
            part_stop = self.offset_to_mark(loc.stop)
            self._view.new_match(new_match_id, part_start,
                                 part_stop, 'error_part')
            self._match_ids.append(new_match_id)

    def _alloc_match_id(self):
        new_match_id = (self.state_id, self._next_rev_num)
        self._next_rev_num += 1
        return new_match_id

    def get_flag(self):
        '''Return the flag of the state.'''
        return self._flag

    def has_error(self):
        '''Return True if the state has errors.'''
        return self._flag == 'error'

    def offset_to_mark(self, offset):
        '''Transform the position representing as the offset in the sentence
        to the (line, col) mark in the document.'''
        line = self.sentence.start.line
        col = self.sentence.start.col
        text = self.sentence.text
        tlen = len(text)
        counter = 0
        offset = min(offset, tlen)

        while counter < offset:
            if text[counter] == '\n':
                line += 1
                col = 1
            else:
                col += 1
            counter += 1

        return Mark(line, col)

    @staticmethod
    def initial(state_id):
        '''Return the initial state with the given state_id.'''
        return _State(state_id, None, None)


class _StateList:
    '''The data structure to manage state objects.'''

    def __init__(self):
        self._head_node = None
        self._tail_node = None
        self._state_id_map = {}
        self._sentence_set = set()

    def init(self, state):
        '''Initialize the state list with the initial state.'''
        initial_node = {'state': state, 'prev': None, 'next': None}
        self._head_node = initial_node
        self._tail_node = initial_node
        self._state_id_map[state.state_id] = initial_node

    def find_prev(self, state_id):
        '''Return the previous state of `state_id`.'''
        prev = self._state_id_map[state_id]['prev']
        if prev:
            return prev['state']
        return None

    def find_by_id(self, state_id):
        '''Return the state by the state id.'''
        node = self._state_id_map.get(state_id)
        if node:
            return node['state']
        return None

    def find_by_mark(self, mark):
        '''Return the state before `mark`.'''
        prev_node = self._head_node
        node = self._head_node['next']
        while node is not None:
            stop = node['state'].sentence.stop
            if stop > mark:
                break
            prev_node = node
            node = node['next']
        return prev_node['state']

    def has_sentence(self, sentence):
        '''Return True if the sentence is in the list.'''
        return sentence in self._sentence_set

    def insert(self, prev_state, state):
        '''Insert the new `state` after `prev_state`.'''
        assert not self.has_sentence(state.sentence)
        prev_node = self._state_id_map[prev_state.state_id]
        node = {'state': state, 'prev': prev_node, 'next': prev_node['next']}
        self._state_id_map[state.state_id] = node
        if prev_node['next']:
            prev_node['next']['prev'] = node
        else:
            self._tail_node = node
        prev_node['next'] = node
        self._sentence_set.add(state.sentence)

    def iter_between(self, begin, end):
        '''Return an iterator from the next of `begin` to `end` (inclusive).'''
        node = self._state_id_map[begin.state_id]['next']
        end = self._state_id_map[end.state_id]['next']
        while node and node != end:
            yield node['state']
            node = node['next']

    def iter_after(self, begin):
        '''Return an iterator from the next of `begin` to the end.'''
        node = self._state_id_map[begin.state_id]['next']
        while node:
            yield node['state']
            node = node['next']

    def remove_between(self, begin, end):
        '''Remove the states from the next of `begin` to `end` (inclusive).'''
        begin_node = self._state_id_map[begin.state_id]
        end_node = self._state_id_map[end.state_id]

        for state in self.iter_between(begin, end):
            del self._state_id_map[state.state_id]
            self._sentence_set.remove(state.sentence)

        post_end_node = end_node['next']
        begin_node['next'] = post_end_node
        if post_end_node:
            post_end_node['prev'] = begin_node
        else:
            self._tail_node = begin_node

    def remove_after(self, begin):
        '''Remove the states from the next of `begin` to the end.'''
        begin_node = self._state_id_map[begin.state_id]

        for state in self.iter_after(begin):
            del self._state_id_map[state.state_id]
            self._sentence_set.remove(state.sentence)

        begin_node['next'] = None
        self._tail_node = begin_node

    def end(self):
        '''Return the state at the end of the document.'''
        return self._tail_node['state']


class STM:
    '''The Coq state machine.'''

    def __init__(self, coqtop, view, fb_handler):
        self._coqtop = coqtop
        self._view = view
        self._fb_handler = fb_handler
        self._state_list = _StateList()
        self._tip_state = None

    def init(self):
        '''Initialize the state machine.'''
        self._coqtop.call('init', {})
        res, err = self._get_value_response('init')
        if err:
            raise RuntimeError(err['message'])
        state = _State.initial(res['init_state_id'])
        self._state_list.init(state)
        self._tip_state = state

    def add(self, sentences):
        '''Add a list of sentences after the tip state.
        '''
        if self._tip_state.has_error():
            self._view.show_message('error', 'Fix the error of the sentence.')
            return

        for sentence in sentences:
            if self._state_list.has_sentence(sentence):
                continue

            state = self._add_one(sentence)
            if state.has_error():
                return

        self._get_goals()

    def edit_at_prev(self):
        '''Edit at the previous state of the tip state.'''
        state = self._state_list.find_prev(self._tip_state.state_id)
        if state:
            self._edit_at_state(state)
            self._get_goals()

    def edit_at(self, mark):
        '''Edit at `mark`.'''
        state = self._state_list.find_by_mark(mark)
        self._edit_at_state(state)
        self._get_goals()

    def get_tip_stop(self):
        '''Return the stop mark of the tip state.'''
        if self._tip_state.sentence:
            return self._tip_state.sentence.stop
        return Mark(1, 1)

    def get_end_stop(self):
        '''Return the stop mark of the state on the end of the document.'''
        sentence = self._state_list.end().sentence
        if sentence:
            return sentence.stop
        return Mark(1, 1)

    def _get_value_response(self, rtype):
        '''Get responses from coqtop and return the first value response.

        The feedback responses are processed by method `process_feedback`.'''
        tag, response = self._coqtop.get_response(rtype)
        while tag == 'feedback':
            self.process_feedback(response)
            tag, response = self._coqtop.get_response(rtype)
        return response

    def _add_one(self, sentence):
        self._coqtop.call('add', {
            'command': sentence.text,
            'edit_id': -1,
            'state_id': self._tip_state.state_id,
            'verbose': True,
        })
        res, err = self._get_value_response('add')

        if err:
            state = _State(StateID(-1), sentence, self._view)
            state.set_flag('error', loc=err['loc'])
        else:
            state = _State(res['state_id'], sentence, self._view)
            state.set_flag('sent')

        self._state_list.insert(self._tip_state, state)

        if res['closed_proof']:
            next_id = res['closed_proof']['next_state_id']
            next_state = self._state_list.find_by_id(next_id)
            self._tip_state = next_state
        else:
            self._tip_state = state

        return state

    def _edit_at_state(self, state):
        '''Edit at `state`.'''
        logger.debug('Edit at state %s', state.state_id.val)

        self._coqtop.call('edit_at', {'state_id': state.state_id})
        res, err = self._get_value_response('edit_at')

        if err:
            good_id = err['state_id']
            good_state = self._state_list.find_by_id(good_id)
            self._edit_at_state(good_state)
        elif res['focused_proof']:
            # Clear the states between `state` and the Qed state of the
            # current proof.
            qed_id = res['focused_proof']['qed_state_id']
            qed_state = self._state_list.find_by_id(qed_id)
            for old_state in self._state_list.iter_between(state, qed_state):
                old_state.set_flag(None)
            self._state_list.remove_between(state, qed_state)
            self._tip_state = state
        else:
            # Clear the states after `state`.
            for old_state in self._state_list.iter_after(state):
                old_state.set_flag(None)
            self._state_list.remove_after(state)
            self._tip_state = state

    def _get_goals(self):
        '''Get the goals of the tip state.'''
        self._coqtop.call('goal', {})
        res, err = self._get_value_response('goal')

        if not err:
            self._view.set_goals(res['goals'])

    def _on_axiom(self, feedback):
        state = self._state_list.find_by_id(feedback['state_id'])
        if state:
            state.set_flag('axiom')

    def _on_processed(self, feedback):
        state = self._state_list.find_by_id(feedback['state_id'])
        if state and state.get_flag() in (None, 'sent'):
            state.set_flag('verified')

    def _on_message(self, feedback):
        level, text = feedback['content']['message']
        loc = feedback['content']['loc']
        state_id = feedback['state_id']
        self._view.show_message(level, text)

        if level == 'error':
            state = self._state_list.find_by_id(state_id)
            if state:
                state.set_flag('error', loc)

    _FEEDBACK_HANDLERS = {
        'axiom': _on_axiom,
        'processed': _on_processed,
        'message': _on_message,
        'errormsg': _on_message,
    }
    '''The handlers for each feedback.'''

    def process_feedback(self, feedback):
        '''Process the given feedback.'''
        logger.debug('STM feedback: %s', feedback)
        fb_type = feedback['type']
        if fb_type in self._FEEDBACK_HANDLERS:
            self._FEEDBACK_HANDLERS[fb_type](self, feedback)
        else:
            self._fb_handler(feedback)
