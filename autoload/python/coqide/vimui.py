'''Vim UI.

In this module defines VimUI and other UI components, the classes that directly interacts with Vim.
'''

import contextlib
import functools
import itertools
import logging

import vim                                                # pylint: disable=E0401

from . import actions
from . import events
from .coqtophandle import CoqtopHandle
from .sentence import SentenceRegion, Mark
from .session import Session
from .stm import STM


logger = logging.getLogger(__name__)                      # pylint: disable=C0103


def _create_window(name, filetype, split_method):
    '''Create a window.'''
    vim.command('{} /{}/'.format(split_method, name))
    vim.command('setlocal buftype=nofile')
    vim.command('setlocal noswapfile')
    vim.command('setlocal bufhidden=delete')
    vim.command('setlocal nospell')
    vim.command('setlocal nonumber')
    vim.command('setlocal norelativenumber')
    vim.command('setlocal nocursorline')
    vim.command('setlocal nomodifiable')
    vim.command('setlocal nobuflisted')
    vim.command('setlocal filetype=' + filetype)
    return int(vim.eval('bufnr("%")'))


def _is_buffer_active(bufnr):
    '''Return True if the buffer `bufnr` is loaded in a window.'''
    return vim.eval('bufwinnr({})'.format(bufnr)) != -1


def _find_buffer(bufnr):
    '''Return the buffer object of `bufnr`.'''
    for buf in vim.buffers:
        if buf.number == bufnr:
            return buf
    return None


@contextlib.contextmanager
def _preserve_window():
    '''Switch back to the current window.'''
    saved_bufnr = vim.eval('bufnr("%")')
    try:
        yield
    finally:
        saved_winnr = vim.eval('bufwinnr({})'.format(saved_bufnr))
        vim.command('{}wincmd w'.format(saved_winnr))


@contextlib.contextmanager
def _switch_buffer(bufnr):
    '''Switch to the window of `bufnr` temporarily.'''
    for buf in vim.buffers:
        if buf.number == bufnr:
            target_buf = buf
            break
    else:
        return

    winnr = int(vim.eval('bufwinnr({})'.format(bufnr)))
    cur_winnr = int(vim.eval('winnr()'))
    if winnr == cur_winnr:
        yield target_buf
    else:
        with _preserve_window():
            vim.command('{}wincmd w'.format(winnr))
            yield target_buf


def _set_buffer_lines(bufnr, lines):
    '''Set the lines of the buffer.'''
    with _switch_buffer(bufnr) as buf:
        if not buf:
            return

        saved_modif = vim.eval('&l:modifiable')
        vim.command('let &l:modifiable=1')
        try:
            for buf in vim.buffers:
                if buf.number == bufnr:
                    buf[:] = lines
                    break
        finally:
            vim.command('let &l:modifiable={}'.format(saved_modif))


def _render_goals(goals):
    '''Render the goals in a list of strings.'''
    content = []
    nr_fg = len(goals.foreground)
    if nr_fg == 0:
        total = 0
        for goal_pair in goals.background:
            total += len(goal_pair[0]) + len(goal_pair[1])

        if total > 0:
            content.append('This subproof is complete, but there are some unfocused goals:')
            content.append('')
            index = 1
            for goal_pair in goals.background:
                for goal in itertools.chain(goal_pair[0], goal_pair[1]):
                    content.append('_______________________ ({}/{})'.format(index, total))
                    content.extend(goal.goal.split('\n'))
        else:
            content.append('No more subgoals.')
    else:
        if nr_fg == 1:
            content.append('1 subgoal')
        else:
            content.append('{} subgoals'.format(nr_fg))

        for hyp in goals.foreground[0].hypotheses:
            content.extend(hyp.split('\n'))
        for index, goal in enumerate(goals.foreground):
            content.append('_______________________ ({}/{})'.format(index + 1, nr_fg))
            content.extend(goal.goal.split('\n'))
    return content


class _GoalWindow:
    '''The goal window.'''

    def __init__(self):
        '''Initialize the goal window.'''
        self._bufnr = None
        self._content = ['No subgoals.']

    def show(self, message_bufnr):
        '''Show the window.

        `message_bufnr` gives a hint of where to create the window.
        '''
        if self._bufnr and _is_buffer_active(self._bufnr):
            return

        with _preserve_window():
            if message_bufnr and _is_buffer_active(message_bufnr):
                # Create the goal window above the message window.
                message_winnr = vim.eval('bufwinnr({})'.format(message_bufnr))
                vim.command('{}wincmd w'.format(message_winnr))
                self._bufnr = _create_window('Goal', 'coq-goals', 'leftabove new')
            else:
                # Create the goal window on the right.
                self._bufnr = _create_window('Goal', 'coq-goals', 'rightbelow vnew')

            _set_buffer_lines(self._bufnr, self._content)

    def hide(self):
        '''Hide the window.'''
        vim.command('{}bdelete'.format(self._bufnr))
        self._bufnr = None

    def toggle(self, message_bufnr):
        '''Toggle the window.'''
        if self._bufnr and _is_buffer_active(self._bufnr):
            self.hide()
        else:
            self.show(message_bufnr)

    def bufnr(self):
        '''Return the buffer number.'''
        return self._bufnr

    def show_goals(self, goals):
        '''Set the content of the goal window.'''
        if goals is not None:
            self._content = _render_goals(goals)
        else:
            self._content = []

        if self._bufnr and _is_buffer_active(self._bufnr):
            _set_buffer_lines(self._bufnr, self._content)


class _MessageWindow:
    '''The message window.'''

    def __init__(self):
        '''Initialize the message window.'''
        self._bufnr = None
        self._content = ['']

    def show(self, goal_bufnr):
        '''Show the window.

        `goal_bufnr` gives a hint of where to create the window.
        '''
        if self._bufnr and _is_buffer_active(self._bufnr):
            return

        with _preserve_window():
            if goal_bufnr and _is_buffer_active(goal_bufnr):
                # Create the message window below the goal window.
                goal_winnr = vim.eval('bufwinnr({})'.format(goal_bufnr))
                vim.command('{}wincmd w'.format(goal_winnr))
                self._bufnr = _create_window('Message', 'coq-messages', 'rightbelow new')
            else:
                # Create the message window on the right.
                self._bufnr = _create_window('Message', 'coq-messages', 'rightbelow vnew')

            _set_buffer_lines(self._bufnr, self._content)

    def hide(self):
        '''Hide the window.'''
        vim.command('{}bdelete'.format(self._bufnr))
        self._bufnr = None

    def toggle(self, goal_bufnr):
        '''Toggle the window.'''
        if self._bufnr and _is_buffer_active(self._bufnr):
            self.hide()
        else:
            self.show(goal_bufnr)

    def bufnr(self):
        '''Return the buffer number.'''
        return self._bufnr

    def show_messages(self, messages):
        '''Set the content of the message window.'''
        self._content = []
        for message, _ in messages:
            self._content.extend(message.split('\n'))

        if self._bufnr and _is_buffer_active(self._bufnr):
            _set_buffer_lines(self._bufnr, self._content)


class _SentenceEndMatcher:
    '''Match the sentence end by feeding characters.

    A sentence ends with a dot with a space like ". " or ".<EOL>", or a ellipsis
    with a space like "... " or "...<EOL>" (EOL means the end of a line).
    '''

    LEADING_SPACE = 0
    '''The initial state.'''

    FREE = 1
    '''The sentence. '''

    PRE_COMMENT = 2
    '''The state after matching a left parenthesis. Ex: aaa (^* aaa *)'''

    COMMENT = 3
    '''The state of in a comment. Ex: aaa (* aaa^aaa *)'''

    POST_COMMENT = 4
    '''The state of at the end of a comment. Ex: aaa (* aaa *^) aaa'''

    PRE_DOT = 5
    '''The state of matching a dot. Ex: aaa.^ or aaa.^.. or Coq.^Init'''

    STRING = 6
    '''The state of in a string. Ex: "aaa^aaa"'''

    PRE_ELLIPSIS_1 = 7
    '''The state of matching two dots. Ex: aaa..^.'''

    PRE_ELLIPSIS_2 = 8
    '''The state of matching an ellipsis. Ex: aaa...^ aaa'''

    MINUS = 9
    '''The state of matching "-".'''

    PLUS = 10
    '''The state of matching "+".'''

    TIMES = 11
    '''The state of matching "*".'''

    BRACKET = 12
    '''The state of matching "{" or "}".'''

    FINAL = 99
    '''The final state.'''

    OP_ENTER_COMMENT = 100
    '''Special operation. Go to state `COMMENT` and increase the nesting level.'''

    OP_LEAVE_COMMENT = 101
    '''Special operation. Decrease the nesting level. If the nesting level reaches zero,
    go to `FREE`. Otherwise, go to `COMMENT`.'''

    _TRANSITIONS = {
        LEADING_SPACE: {
            '(': PRE_COMMENT,
            '.': PRE_DOT,
            '"': STRING,
            ' ': LEADING_SPACE,
            '\t': LEADING_SPACE,
            '\n': LEADING_SPACE,
            '-': MINUS,
            '+': PLUS,
            '*': TIMES,
            '{': BRACKET,
            '}': BRACKET,
            None: FREE,
        },
        FREE: {
            '(': PRE_COMMENT,
            '.': PRE_DOT,
            '"': STRING,
            None: FREE,
        },
        PRE_COMMENT: {
            '*': OP_ENTER_COMMENT,
            '.': PRE_DOT,
            None: FREE,
        },
        COMMENT: {
            '*': POST_COMMENT,
            None: COMMENT,
        },
        POST_COMMENT: {
            '*': POST_COMMENT,
            ')': OP_LEAVE_COMMENT,
            None: COMMENT,
        },
        PRE_DOT: {
            ' ': FINAL,
            '\t': FINAL,
            '\n': FINAL,
            '.': PRE_ELLIPSIS_1,
            None: FREE,
        },
        STRING: {
            '"': FREE,
            None: STRING,
        },
        PRE_ELLIPSIS_1: {
            '.': PRE_ELLIPSIS_2,
            None: FREE,
        },
        PRE_ELLIPSIS_2: {
            ' ': FINAL,
            '\t': FINAL,
            '\n': FINAL,
            None: FREE,
        },
        MINUS: {
            '-': MINUS,
            None: FINAL,
        },
        PLUS: {
            '+': PLUS,
            None: FINAL,
        },
        TIMES: {
            '*': TIMES,
            None: FINAL,
        },
        BRACKET: {
            None: FINAL,
        },
    }

    def __init__(self):
        '''Create a matcher.'''
        self._state = self.LEADING_SPACE
        self._nesting_level = 0

    def feed(self, char):
        '''Feed a character and move to the next state.'''
        trans = self._TRANSITIONS[self._state]
        state_or_op = trans.get(char, trans[None])

        if state_or_op == self.OP_ENTER_COMMENT:
            self._nesting_level += 1
            self._state = self.COMMENT
        elif state_or_op == self.OP_LEAVE_COMMENT:
            self._nesting_level -= 1
            if self._nesting_level:
                self._state = self.COMMENT
            else:
                self._state = self.FREE
        else:
            self._state = state_or_op

        return self.is_final()

    def is_final(self):
        '''Return True if reached FINAL state.'''
        return self._state == self.FINAL


def _in_session(func):
    '''A function decorator that passes the current session and buffer number
    as arguments to the decorated function.'''
    @functools.wraps(func)
    def wrapped(self, *args, **kwargs):                  # pylint: disable=C0111
        session, bufnr = self._get_current_session()     # pylint: disable=W0212
        if session is None:
            print('Not in Coq')
            return
        func(self, session, bufnr, *args, **kwargs)
    return wrapped


def _get_cursor():
    '''Return the cursor mark.'''
    _, line, col, _ = vim.eval('getpos(".")')
    line, col = int(line), int(col)

    mode = vim.eval('mode()')
    if mode[0] != 'i':
        col += 1

    return Mark(line, col)


def _find_stop_after(start):
    '''Return the next sentence stop after the given mark `start`.'''
    # Map 1-indexed position into 0-indexed.
    start_line, start_col = start.line - 1, start.col - 1
    matcher = _SentenceEndMatcher()

    # The cursor is 1-indexed.
    cursor_line, cursor_col = start

    vimbuf = vim.current.buffer

    for char in itertools.chain(vimbuf[start_line][start_col:], ['\n']):
        matched = matcher.feed(char)
        if matched:
            return Mark(cursor_line, cursor_col)
        cursor_col += 1

    for line in vimbuf[start_line+1:]:
        cursor_line += 1
        cursor_col = 1
        for char in itertools.chain(line, ['\n']):
            matched = matcher.feed(char)
            if matched:
                return Mark(cursor_line, cursor_col)
            cursor_col += 1

    return None


def _get_buffer_text(start, stop):
    '''Return the text between Mark `start` and `stop`.'''
    # Map from 1-indexed position to 0-indexed position.
    start_line, start_col = start.line - 1, start.col - 1
    end_line, end_col = stop.line - 1, stop.col - 1

    vimbuf = vim.current.buffer
    if start_line == end_line:
        return vimbuf[start_line][start_col:end_col]

    fragments = [vimbuf[start_line][start_col:]]
    for i in range(start_line + 1, end_line):
        fragments.append(vimbuf[i])
    fragments.append(vimbuf[end_line][:end_col])
    return '\n'.join(fragments)


class _ActionHandler(actions.ActionHandlerBase):
    '''The class that handles actions generated by the plugin.

    All the Vim updating operations are temporarily saved in an internal
    buffer. Vim periodically calls `update_ui` to bring the actions into
    effects.
    '''

    def __init__(self, show_goals, show_messages):
        '''Create the action handler.

        `show_goals(goals)` is a function to show the Goals object in the
        Goal window.

        `show_messages(messages)` is a function to show the messages in the
        Message window. The argument `messages` is a list of tuple `(text, level)`.
        '''
        self._show_goals = show_goals
        self._show_messages = show_messages

        self._goal_op = None
        self._message_op = None
        self._hl_ops = {}
        self._other_ops = []

        self._hl_match_ids = {}

    def update_ui(self):
        '''Run all the pending UI operations.

        It must be called periodically in the Vim UI thread.'''
        # During the application of the operations, new operations may be
        # added to the internal buffer. So we first fetch them and clear
        # the buffer to "save a snapshot".
        ops = []
        if self._goal_op:
            ops.append(self._goal_op)
            self._goal_op = None
        if self._message_op:
            ops.append(self._message_op)
            self._message_op = None
        ops.extend(self._hl_ops.values())
        self._hl_ops = {}
        ops.extend(self._other_ops)
        self._other_ops = []

        for operation in ops:
            operation()

    def _on_show_goals(self, action):
        self._goal_op = lambda: self._show_goals(action.goals)

    def _on_show_message(self, action):
        self._message_op = lambda: self._show_messages([(action.message, action.level)])

    def _on_hl_region(self, action):
        hlid = (action.bufnr, action.start, action.stop, action.token)

        def highlight_op():
            '''Highlight the region in the buffer and save the match ids.'''
            bufnr, start, stop, _, hlgroup = action
            match_ids = []

            with _switch_buffer(bufnr) as buf:
                # Highlight line by line.
                if start.line == stop.line:
                    len1 = stop.col - start.col
                else:
                    len1 = len(buf[start.line - 1]) - start.col + 1

                match_args = []
                match_args.append([start.line, start.col, len1])

                for line_num in range(start.line + 1, stop.line):
                    match_args.append(line_num)
                    if len(match_args) == 7:
                        cmd = 'matchaddpos("{}", {})'.format(hlgroup, match_args)
                        match_ids.append(vim.eval(cmd))
                        match_args = []

                if start.line != stop.line:
                    match_args.append([stop.line, 1, stop.col - 1])

                cmd = 'matchaddpos("{}", {})'.format(hlgroup, match_args)
                match_ids.append(vim.eval(cmd))
                match_args = []

                self._hl_match_ids[hlid] = match_ids
                logger.debug('Highlight: %s => %s', action, match_ids)


        self._hl_ops[hlid] = highlight_op

    def _on_unhl_region(self, action):
        hlid = (action.bufnr, action.start, action.stop, action.token)

        def unhighlight_op():
            '''Unhighlight the matches.'''
            logger.debug('Unhighlight: %s %s', action, self._hl_match_ids[hlid])

            with _switch_buffer(action.bufnr) as _:
                for match_id in self._hl_match_ids[hlid]:
                    vim.command('call matchdelete({})'.format(match_id))
                del self._hl_match_ids[hlid]

        # This is an optimization to speed up highlighting. If the highlighting operation
        # has not taken effects (that is, still in the pending buffer), we cancel the
        # operation directly rather than adding another unhighlighing operation.
        if hlid in self._hl_ops:
            del self._hl_ops[hlid]
        else:
            self._other_ops.append(unhighlight_op)

    def _on_conn_lost(self, action):
        '''Notify the user that the connection to the coqtop process is lost.'''
        def conn_lost_op():
            '''Notify the user that the connection is lost.'''
            vim.command('echom "{}"'.format('Coqtop subprocess quits unexpectedly.'))
        self._other_ops.append(conn_lost_op)


class VimUI:
    '''This class interacts with Vim directly.'''

    def __init__(self):
        '''Create VimUI and initialize.'''
        self._goal = _GoalWindow()
        self._message = _MessageWindow()
        self._goal.show(None)
        self._message.show(self._goal.bufnr())
        self._action_handler = _ActionHandler(self._goal.show_goals,
                                              self._message.show_messages)
        self._sessions = {}
        self._last_focused_bufnr = None

    def new_session(self):
        '''Create a new session bound to the current buffer.'''
        session, bufnr = self._get_current_session()
        if session is not None:
            logger.error('Session already created for buffer [%s].', bufnr)
            return
        logger.debug('New session [%s]', bufnr)
        session = Session(lambda: STM(bufnr), lambda fb: CoqtopHandle('utf-8', fb),
                          self._handle_action)
        session.init(self._handle_action)
        self._sessions[bufnr] = session

    @_in_session
    def close_session(self, session, bufnr):
        '''Close the session bound to the current buffer.'''
        logger.debug('Close session [%s].', bufnr)
        session.close(self._handle_action)
        del self._sessions[bufnr]

    def deactivate(self):
        '''Close all the sessions and windows.'''
        logger.debug('Close all sessions.')
        for session in self._sessions.values():
            session.close(self._handle_action)
        self._sessions = {}
        self._goal.hide()
        self._message.hide()

    @_in_session
    def forward(self, session, bufnr):
        '''Process the next sentence in the current session.'''
        if session.is_busy():
            logger.debug('Session [%s] busy.', bufnr)
            return

        start = session.get_last_stop()
        stop = _find_stop_after(start)
        if stop is None:
            return

        text = _get_buffer_text(start, stop)
        region = SentenceRegion(bufnr, start, stop, text)
        logger.debug('Forward in session [%s]: %s', bufnr, region)
        session.forward(region, self._handle_action)

    @_in_session
    def backward(self, session, bufnr):
        '''Backward to the previous sentence in the current session.'''
        if session.is_busy():
            logger.debug('Session [%s] busy.', bufnr)
            return

        logger.debug('Backward in session [%s]', bufnr)
        session.backward(self._handle_action)

    @_in_session
    def to_cursor(self, session, bufnr):
        '''Process to the sentence under the cursor.'''
        if session.is_busy():
            logger.debug('Session [%s] busy.', bufnr)
            return

        stop = session.get_last_stop()
        cursor = _get_cursor()
        if cursor.line > stop.line or \
                (cursor.line == stop.line and cursor.col > stop.col):
            self._forward_to_cursor(session, bufnr, cursor)
        else:
            logger.debug('Backward to cursor in session [%s]', bufnr)
            session.backward_before_mark(cursor, self._handle_action)

    def set_goal_visibility(self, visibility):
        '''Set the visibility of the goal window to 'show', 'hide' or 'toggle'.'''
        if visibility == 'show':
            self._goal.show(self._message.bufnr())
        elif visibility == 'hide':
            self._goal.hide()
        elif visibility == 'toggle':
            self._goal.toggle(self._message.bufnr())
        else:
            raise ValueError('Invalid visibility: {}'.format(visibility))

    def set_message_visibility(self, visibility):
        '''Set the visibility of the message window to 'show', 'hide' or 'toggle'.'''
        if visibility == 'show':
            self._message.show(self._goal.bufnr())
        elif visibility == 'hide':
            self._message.hide()
        elif visibility == 'toggle':
            self._message.toggle(self._goal.bufnr())
        else:
            raise ValueError('Invalid visibility: {}'.format(visibility))

    @_in_session
    def handle_event(self, session, bufnr, event_name, *event_args):
        '''Handle the event.'''
        if event_name == 'Focus':
            if self._last_focused_bufnr == bufnr:
                return
            if self._last_focused_bufnr in self._sessions:
                last_session = self._sessions[self._last_focused_bufnr]
                last_session.handle_event(events.Unfocus(), self._handle_action)
            self._last_focused_bufnr = bufnr
            session.handle_event(events.Focus(), self._handle_action)
        else:
            event_class = getattr(events, event_name)
            event = event_class(*event_args)
            session.handle_event(event, self._handle_action)

    def update_ui(self):
        '''Apply the pending UI operations.'''
        try:
            self._action_handler.update_ui()
        except vim.error:
            logger.debug('Catched exception in update_ui', exc_info=True)

    @property
    def _handle_action(self):
        '''Return the action handler's handle function.'''
        return self._action_handler.handle_action

    def _get_current_session(self):
        '''Return the session bound to the current buffer.'''
        bufnr = int(vim.eval('bufnr("%")'))
        return self._sessions.get(bufnr, None), bufnr

    def _forward_to_cursor(self, session, bufnr, cursor):
        '''Go forward to the sentence before the cursor.'''
        logger.debug('Forward to cursor in session [%s]', bufnr)

        start = session.get_last_stop()
        cursor = _get_cursor()
        regions = []

        while True:
            stop = _find_stop_after(start)
            if stop is None or \
                    stop.line > cursor.line or \
                    (stop.line == cursor.line and stop.col > cursor.col):
                break

            text = _get_buffer_text(start, stop)
            region = SentenceRegion(bufnr, start, stop, text)
            regions.append(region)
            start = stop

        logger.debug('Forward to cursor in session [%s]: %s', bufnr, regions)
        session.forward_many(regions, self._handle_action)
