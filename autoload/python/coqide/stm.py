'''State and state machine.'''

from .types import StateID, Mark


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
        self._matches = []

    def move(self, line_offset):
        '''Move the position of the sentence.'''
        for match in self._matches:
            match.move(line_offset)

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
        for match in self._matches:
            match.remove()
        self._matches.clear()

        if flag is None:
            return

        whole_match = self._view.new_highlight(
            self.state_id, self.sentence.start, self.sentence.stop, flag)
        self._matches.append(whole_match)

        if flag == 'error' and loc and loc.start and loc.stop:
            part_start = self.offset_to_mark(loc.start)
            part_stop = self.offset_to_mark(loc.stop)
            part_match = self._view.new_highlight(
                self.state_id, part_start, part_stop, 'error_part')
            self._matches.append(part_match)

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
        self._node_map = {}

    def init(self, state):
        '''Initialize the state list with the initial state.'''
        initial_node = {'state': state, 'prev': None, 'next': None}
        self._head_node = initial_node
        self._node_map[state.state_id] = initial_node

    def find_by_id(self, state_id):
        '''Return the state by the state id.'''
        return self._node_map[state_id]['state']

    def find_by_mark(self, mark):
        '''Return the state before `mark`.'''
        prev_node = self._head_node
        node = self._head_node['next']
        while node is not None:
            stop = node['state'].sentence.stop
            if stop.line > mark.line or \
                    (stop.line == mark.line and stop.col > mark.col):
                break
            prev_node = node
            node = node['next']
        return prev_node.state

    def insert(self, prev_state, state):
        '''Insert the new `state` after `prev_state`.'''
        prev_node = self._node_map[prev_state.state_id]
        node = {'state': state, 'prev': prev_node, 'next': prev_node['next']}
        prev_node['next']['prev'] = node
        prev_node['next'] = node

    def iter_between(self, begin, end):
        '''Return an iterator from the next of `begin` to `end` (inclusive).'''
        node = self._node_map[begin.state_id]['next']
        end = self._node_map[end.state_id]['next']
        while node and node != end:
            yield node
            node = node['next']

    def iter_after(self, begin):
        '''Return an iterator from the next of `begin` to the end.'''
        node = self._node_map[begin.state_id]['next']
        while node:
            yield node
            node = node['next']

    def remove_between(self, begin, end):
        '''Remove the states from the next of `begin` to `end` (inclusive).'''
        begin_node = self._node_map[begin.state_id]
        end_node = self._node_map[end.state_id]
        post_end_node = end_node['next']
        begin_node['next'] = post_end_node
        if post_end_node:
            post_end_node['prev'] = begin_node

    def remove_after(self, begin):
        '''Remove the states from the next of `begin` to the end.'''
        begin_node = self._node_map[begin.state_id]
        begin_node['next'] = None


class STM:
    '''The Coq state machine.'''

    def __init__(self, coqtop, view):
        self._coqtop = coqtop
        self._view = view
        self._state_list = _StateList()
        self._tip_state = None

    def init(self):
        '''Initialize the state machine.'''
        res = self._coqtop.call('init', {})
        state = _State.initial(res['init_state_id'])
        self._state_list.init(state)
        self._tip_state = state

    def add(self, sentences):
        '''Add a list of sentences after the tip state.
        '''
        if self._tip_state.has_error():
            self._view.set_cursor(self._tip_state.sentence.start)
            self._view.show_message('error', 'Fix the error of the sentence.')
            return

        for sentence in sentences:
            state = self._add_one(sentence)
            if state.has_error():
                return

        self._get_goals()

    def edit_at(self, mark):
        '''Edit at `mark`.'''
        state = self._state_list.find_by_mark(mark)
        self._edit_at_state(state)
        self._get_goals()

    def get_tip_stop(self):
        '''Return the stop mark of the tip state.'''
        return self._tip_state.sentence.stop

    def _add_one(self, sentence):
        res, err = self._coqtop.call('add', {
            'command': sentence.text,
            'edit_id': -1,
            'state_id': self._tip_state.state_id,
            'verbose': True,
        })

        if err:
            state = _State(StateID(-1), sentence, self._view)
            state.set_flag('error', loc=res['loc'])
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

        res, err = self._coqtop.call('edit_at', {
            'state_id': state.state_id})

        if err:
            good_id = res['state_id']
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
        else:
            # Clear the states after `state`.
            for old_state in self._state_list.iter_after(state):
                old_state.set_flag(None)
            self._state_list.remove_after(state)
            self._tip_state = state

    def _get_goals(self):
        '''Get the goals of the tip state.'''
        res, err = self._coqtop.call('goal', {})

        if err:
            state_id = res['state_id']
            state = self._state_list.find_by_id(state_id)
            state.set_flag('error', loc=res['loc'])
            self._view.show_message('error', res['message'])
        else:
            self._view.set_goals(res['goals'])

    def _on_axiom(self, feedback):
        state = self._state_list.find_by_id(feedback['state_id'])
        state.set_flag('axiom')

    def _on_processed(self, feedback):
        state = self._state_list.find_by_id(feedback['state_id'])
        if state.get_flag() is None:
            state.set_flag('verified')

    def _on_message(self, feedback):
        level, text = feedback['content']['message']
        loc = feedback['content']['loc']
        state_id = feedback['state_id']
        self._view.show_message(level, text)

        if level == 'error' and state_id > 0:
            state = self._state_list.find_by_id(state_id)
            state.set_flag('error', loc)

    _FEEDBACK_HANDLERS = {
        'axiom': _on_axiom,
        'processed': _on_processed,
        'message': _on_message,
        'errormsg': _on_message,
    }
    '''The handlers for each feedback.'''

    def process_feedbacks(self, feedbacks):
        '''Process the given list of feedbacks.'''
        for feedback in feedbacks:
            fb_type = feedback['type']
            if fb_type in self._FEEDBACK_HANDLERS:
                self._FEEDBACK_HANDLERS[fb_type](self, feedback)
