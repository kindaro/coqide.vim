'''Coq session.'''


from collections import namedtuple

from coqide.coqtopinstance import CoqtopInstance
from coqide.stm import STM
from coqide.vimsupport import get_cursor, get_sentence_after, get_line_len, \
    add_match, del_match


_MatchArg = namedtuple('_MatchArg', 'start stop type')


class _Match:
    '''A match object in the window.'''

    _HLGROUPS = {
        'sent': 'CoqStcSent',
        'axiom': 'CoqStcAxiom',
        'error': 'CoqStcError',
        'error_part': 'CoqStcErrorPart',
        'verified': 'CoqStcVerified',
    }

    def __init__(self, match_id, match_arg, lock_zone):
        self.match_id = match_id
        self.match_arg = match_arg
        self._vim_id = None
        self._lock_zone = lock_zone

    def show(self):
        '''Show the match in Vim.'''
        assert self._vim_id is None

        start = self.match_arg.start
        stop = self.match_arg.stop
        hlgroup = self._HLGROUPS[self.match_arg.type]
        self._vim_id = add_match(start, stop, hlgroup)

    def hide(self):
        '''Hide the match from Vim.'''
        assert self._vim_id is not None
        del_match(self._vim_id)
        self._vim_id = None

    def is_shown(self):
        '''Return True if the match is shown in Vim.'''
        return self._vim_id is not None

    def remove(self):
        '''Remove the match.'''
        if self.is_shown():
            self.hide()

        self._lock_zone.on_match_removed(self.match_id)
        self.match_id = None
        self._lock_zone = None

    def move(self, line_offset):
        '''Move the match `line_offset` lines down in the window.'''
        is_shown = self.is_shown()

        if is_shown:
            self.hide()

        start = self.match_arg.start
        stop = self.match_arg.stop
        self.match_arg = self.match_arg._replace(
            start=start._replace(line=start.line + line_offset),
            stop=stop._replace(line=stop.line + line_offset))

        if is_shown:
            self.show()


class _LockZoneView:
    '''The matches in a documents.'''

    def __init__(self, bufnr):
        self._bufnr = bufnr
        self._pending_match_map = {}   # Matches not added to Vim
        self._effective_match_map = {} # Matches added to Vim
        self._active = False

    def set_active(self):
        '''Add the matches to the Vim window of the buffer.'''
        if self._active:
            return

        self._active = True
        for match in self._effective_match_map.values():
            match.show()

    def set_inactive(self):
        '''Remove the matches added to the Vim window.'''
        if not self._active:
            return

        self._active = False
        for match in self._effective_match_map.values():
            match.hide()

    def add(self, match_id, start, stop, match_type):
        ''''Add a match to the view and return the match object.'''
        match_arg = _MatchArg(start, stop, match_type)
        match = _Match(match_id, match_arg, self)
        self._pending_match_map[match_id] = match

    def draw(self):
        '''Draw the lock zone in the Vim UI.'''
        for match_id, match in self._pending_match_map.items():
            self._effective_match_map[match_id] = match

        if self._active:
            for match in self._pending_match_map.values():
                match.show()

    def on_match_remove(self, match_id):
        '''Called when a match is removed.'''
        if match_id in self._pending_match_map:
            del self._pending_match_map[match_id]
        else:
            del self._effective_match_map[match_id]


class _SessionView:
    '''The view relating to a session.'''

    def __init__(self, bufnr, vim_view):
        self._bufnr = bufnr
        self._vim_view = vim_view

        self._focused = False
        self._goals = None
        self._messages = []
        self._lock_zone = _LockZoneView(bufnr)

    def draw(self):
        '''Draw the view in Vim UI.'''
        self._lock_zone.draw()

    def destroy(self):
        '''Detach the session view.'''

    def show_message(self, level, message):
        '''Show the message in the message window.'''
        self._messages.append((level, message))
        if self._focused:
            self._vim_view.show_message(level, message)

    def set_goals(self, goals):
        '''Show the goals in the goal window.'''
        self._goals = goals
        if self._focused:
            self._vim_view.set_goals(goals)

    def focus(self):
        '''Focus the view.'''
        if self._focused:
            return

        self._focused = True
        for level, message in self._messages:
            self._vim_view.show_message(level, message)
        self._vim_view.set_goals(self._goals)

    def unfocus(self):
        '''Unfocus the view.'''
        if not self._focused:
            return
        self._focused = False

    def set_active(self):
        '''Set the view as active.'''
        self._lock_zone.set_active()

    def set_inactive(self):
        '''Set the view as inactive.'''
        self._lock_zone.set_inactive()

    def new_match(self, match_id, start, stop, match_type):
        '''Create a new match on the window and return the match object.'''
        return self._lock_zone.add(match_id, start, stop, match_type)


class Session:
    '''A loaded Coq source file and its coqtop interpreter.'''

    def __init__(self, bufnr, vim_view, executor):
        '''Create a new session.'''
        self._coqtop = CoqtopInstance()
        self._coqtop.spawn(['coqtop', '-ideslave', '-main-channel', 'stdfds',
                            '-async-proofs', 'on'])
        self._view = _SessionView(bufnr, vim_view)
        self._executor = executor
        self._stm = STM(self._coqtop, self._view, lambda _: None)

    def forward_one(self):
        '''Add the next sentence after the tip state to the STM.'''
        start = self._stm.get_tip_stop()
        sentence = get_sentence_after(start)
        self._executor.submit(self._stm.add, [sentence])

    def backward_one(self):
        '''Backward to the previous state of the tip state.'''
        self._executor.submit(self._stm.edit_at_prev)

    def to_cursor(self):
        '''Forward or backward to the sentence under the cursor.'''
        tip_stop = self._stm.get_tip_stop()
        cursor = get_cursor()
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

        sentence = get_sentence_after(from_mark)
        while sentence.stop <= to_mark:
            sentences.append(sentence)
            sentence = get_sentence_after(sentence.stop)
        self._executor.submit(self._stm.add, sentences)

    def close(self):
        '''Close the session.'''
        self._coqtop.close()
        self._view.destroy()
        self._coqtop = None
        self._view = None
        self._stm = None
