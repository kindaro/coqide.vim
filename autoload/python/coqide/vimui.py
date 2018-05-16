'''Vim UI.

In this module defines VimUI and other UI components, the classes that directly interacts with Vim.
'''

import contextlib
import functools
import itertools
import logging

import vim                                                # pylint: disable=E0401

from .coqtophandle import CoqtopHandle
from .sentence import SentenceRegion, Mark
from .session import Session
from .stm import STM


logger = logging.getLogger(__name__)                      # pylint: disable=C0103


def create_window(name, filetype, split_method):
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


def is_buffer_active(bufnr):
    '''Return True if the buffer `bufnr` is loaded in a window.'''
    return vim.eval('bufwinnr({})'.format(bufnr)) != -1


def find_buffer(bufnr):
    '''Return the buffer object of `bufnr`.'''
    for buf in vim.buffers:
        if buf.number == bufnr:
            return buf
    return None


@contextlib.contextmanager
def switch_buffer(bufnr):
    '''Switch to `bufnr` temporarily.'''
    saved_bufnr = vim.eval('bufnr("%")')
    vim.command('hide buffer {}'.format(bufnr))
    try:
        for buf in vim.buffers:
            if buf.number == bufnr:
                yield buf
                break
    finally:
        vim.command('hide buffer {}'.format(saved_bufnr))


def set_buffer_lines(bufnr, lines):
    '''Set the lines of the buffer.'''
    with switch_buffer(bufnr) as buf:
        saved_modif = vim.eval('&l:modifiable')
        vim.command('let &l:modifiable=1')
        try:
            for buf in vim.buffers:
                if buf.number == bufnr:
                    buf[:] = lines
                    break
        finally:
            vim.command('let &l:modifiable={}'.format(saved_modif))


@contextlib.contextmanager
def preserve_window():
    '''Switch back to the current window.'''
    saved_bufnr = vim.eval('bufnr("%")')
    try:
        yield
    finally:
        saved_winnr = vim.eval('bufwinnr({})'.format(saved_bufnr))
        vim.command('{}wincmd w'.format(saved_winnr))


class GoalWindow:
    '''The goal window.'''

    def __init__(self):
        '''Initialize the goal window.'''
        self._bufnr = None
        self._content = ['No subgoals.']

    def show(self, message_bufnr):
        '''Show the window.

        `message_bufnr` gives a hint of where to create the window.
        '''
        if self._bufnr and is_buffer_active(self._bufnr):
            return

        with preserve_window():
            if message_bufnr and is_buffer_active(message_bufnr):
                # Create the goal window above the message window.
                message_winnr = vim.eval('bufwinnr({})'.format(message_bufnr))
                vim.command('{}wincmd w'.format(message_winnr))
                self._bufnr = create_window('Goal', 'coq-goals', 'leftabove new')
            else:
                # Create the goal window on the right.
                self._bufnr = create_window('Goal', 'coq-goals', 'rightbelow vnew')

            set_buffer_lines(self._bufnr, self._content)

    def hide(self):
        '''Hide the window.'''
        vim.command('{}bdelete'.format(self._bufnr))
        self._bufnr = None

    def toggle(self, message_bufnr):
        '''Toggle the window.'''
        if self._bufnr and is_buffer_active(self._bufnr):
            self.hide()
        else:
            self.show(message_bufnr)

    def bufnr(self):
        '''Return the buffer number.'''
        return self._bufnr

    def show_goal(self, goals):
        '''Set the content of the goal window.'''
        content = []
        if goals is not None:
            nr_bg = len(goals.background)
            if nr_bg > 0:
                content.append('This subproof is complete, but there are some unfocused goals:')
                content.append('')

            nr_fg = len(goals.foreground)
            if nr_fg > 0:
                if nr_fg == 1:
                    content.append('1 subgoal')
                else:
                    content.append('{} subgoals'.format(nr_fg))
                for hyp in goals.foreground[0].hypotheses:
                    content.append(hyp)
                for index, goal in enumerate(goals.foreground):
                    content.append('__________________________ ({}/{})'.format(index + 1, nr_fg))
                    content.append(goal.goal)
            elif nr_fg == 0 and nr_bg == 0:
                content.append('No more subgoals.')

        self._content = content
        if self._bufnr and is_buffer_active(self._bufnr):
            set_buffer_lines(self._bufnr, self._content)


class MessageWindow:
    '''The message window.'''

    def __init__(self):
        '''Initialize the message window.'''
        self._bufnr = None
        self._content = ['']

    def show(self, goal_bufnr):
        '''Show the window.

        `goal_bufnr` gives a hint of where to create the window.
        '''
        if self._bufnr and is_buffer_active(self._bufnr):
            return

        with preserve_window():
            if goal_bufnr and is_buffer_active(goal_bufnr):
                # Create the message window below the goal window.
                goal_winnr = vim.eval('bufwinnr({})'.format(goal_bufnr))
                vim.command('{}wincmd w'.format(goal_winnr))
                self._bufnr = create_window('Message', 'coq-messages', 'rightbelow new')
            else:
                # Create the message window on the right.
                self._bufnr = create_window('Message', 'coq-messages', 'rightbelow vnew')

            set_buffer_lines(self._bufnr, self._content)

    def hide(self):
        '''Hide the window.'''
        vim.command('{}bdelete'.format(self._bufnr))
        self._bufnr = None

    def toggle(self, goal_bufnr):
        '''Toggle the window.'''
        if self._bufnr and is_buffer_active(self._bufnr):
            self.hide()
        else:
            self.show(goal_bufnr)

    def bufnr(self):
        '''Return the buffer number.'''
        return self._bufnr

    def show_message(self, message, _):
        '''Set the content of the message window.'''
        self._content = message.split('\n')
        if self._bufnr and is_buffer_active(self._bufnr):
            set_buffer_lines(self._bufnr, self._content)


class SentenceEndMatcher:
    '''Match the sentence end by feeding characters.

    A sentence ends with a dot with a space like ". " or ".<EOL>", or a ellipsis
    with a space like "... " or "...<EOL>" (EOL means the end of a line).
    '''

    FREE = 1
    '''The initial state. '''

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

    FINAL = 9
    '''The final state.'''

    OP_ENTER_COMMENT = 100
    '''Special operation. Go to state `COMMENT` and increase the nesting level.'''

    OP_LEAVE_COMMENT = 101
    '''Special operation. Decrease the nesting level. If the nesting level reaches zero,
    go to `FREE`. Otherwise, go to `COMMENT`.'''

    _TRANSITIONS = {
        FREE : {
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
    }

    def __init__(self):
        '''Create a matcher.'''
        self._state = self.FREE
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


def in_session(func):
    '''A function decorator that passes the current session and buffer number
    as arguments to the decorated function.'''
    @functools.wraps(func)
    def wrapped(self):                                   # pylint: disable=C0111
        session, bufnr = self._get_current_session()     # pylint: disable=W0212
        if session is None:
            print('Not in Coq')
            return
        func(self, session, bufnr)
    return wrapped


def get_cursor():
    '''Return the cursor mark.'''
    _, line, col, _ = vim.eval('getpos(".")')
    line, col = int(line), int(col)

    mode = vim.eval('mode()')
    if mode[0] != 'i':
        col += 1

    return Mark(line, col)


def find_stop_after(start):
    '''Return the next sentence stop after the given mark `start`.'''
    # Map 1-indexed position into 0-indexed.
    start_line, start_col = start.line - 1, start.col - 1
    matcher = SentenceEndMatcher()

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


def get_buffer_text(start, stop):
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


class UICommandHandler:
    '''The class that handles UI update commands from the Coq sessions.

    Unless otherwise commented, the methods can be called from any threads.
    All the UI updating commands are saved in an internal list, which will
    be cleared periodically in the Vim UI thread.
    '''

    def __init__(self, goal, message):
        '''Create the UI command handler.

        `goal_bufnr` and `message_bufnr` are the numbers of the goal and message windows.
        '''
        self._goal = goal
        self._message = message
        self._pending_ui_cmds = []

    def update_ui(self):
        '''Run all the pending UI commands in the pending list.

        It must be called periodically in the Vim UI thread.'''
        for cmd in self._pending_ui_cmds:
            cmd()
        self._pending_ui_cmds = []

    def show_goal(self, goals):
        '''Update the content of the goal window to `goals`.'''
        self._pending_ui_cmds.append(lambda: self._goal.show_goal(goals))

    def show_message(self, message, is_error):
        '''Update the content of the message window to `message`.'''
        self._pending_ui_cmds.append(lambda: self._message.show_message(message, is_error))

    def highlight(self, doc_id, start, stop, hlgroup):
        '''Set the hlgroup of a region in `doc_id`.'''
        match_ids = []

        def highlight_cmd():
            '''Highlight the region in the buffer whose id is `doc_id`.'''
            with switch_buffer(doc_id) as buf:
                # Highlight line by line.
                if start.line == stop.line:
                    len1 = stop.col - start.col
                else:
                    len1 = len(buf[start.line - 1]) - start.col + 1

                cmd = 'matchaddpos("{}", [[{}, {}, {}]])'.format(
                    hlgroup, start.line, start.col, len1)
                match_ids.append(vim.eval(cmd))

                for line_num in range(start.line + 1, stop.line):
                    cmd = 'matchaddpos("{}", [{}])'.format(hlgroup, line_num)
                    match_ids.append(vim.eval(cmd))

                if start.line != stop.line:
                    cmd = 'matchaddpos("{}", [[{}, {}, {}]])'.format(
                        hlgroup, stop.line, 1, stop.col - 1)
                    match_ids.append(vim.eval(cmd))

        def unhighlight():
            '''Unhighlight the region.'''
            with switch_buffer(doc_id) as _:
                for match_id in match_ids:
                    vim.command('call matchdelete({})'.format(match_id))

        self._pending_ui_cmds.append(highlight_cmd)
        return lambda: self._pending_ui_cmds.append(unhighlight)

    def connection_lost(self):
        '''Notify the user that the connection to the coqtop process is lost.'''
        def conn_lost_cmd():
            '''Notify the user that the connection is lost.'''
            vim.command('echom "{}"'.format('Coqtop subprocess quits unexpectedly.'))
        self._pending_ui_cmds.append(conn_lost_cmd)


class VimUI:
    '''This class interacts with Vim directly.'''

    def __init__(self):
        '''Create VimUI and initialize.'''
        self._goal = GoalWindow()
        self._message = MessageWindow()
        self._goal.show(None)
        self._message.show(self._goal.bufnr())
        self._ui_cmds = UICommandHandler(self._goal, self._message)
        self._sessions = {}
        self._focused_bufnr = None

    def new_session(self):
        '''Create a new session bound to the current buffer.'''
        session, bufnr = self._get_current_session()
        if session is not None:
            logger.error('Session already created for buffer [%s].', bufnr)
            return
        logger.debug('New session [%s]', bufnr)
        session = Session(STM, CoqtopHandle, self._ui_cmds)
        self._sessions[bufnr] = session

    @in_session
    def close_session(self, session, bufnr):
        '''Close the session bound to the current buffer.'''
        logger.debug('Close session [%s].', bufnr)
        session.close()
        del self._sessions[bufnr]

    def deactivate(self):
        '''Close all the sessions and windows.'''
        logger.debug('Close all sessions.')
        for session in self._sessions:
            session.close()
        self._sessions = {}
        self._goal.hide()
        self._message.hide()

    @in_session
    def forward(self, session, bufnr):
        '''Process the next sentence in the current session.'''
        if session.is_busy():
            logger.debug('Session [%s] busy.', bufnr)
            return

        start = session.get_last_stop()
        stop = find_stop_after(start)
        if stop is None:
            return

        text = get_buffer_text(start, stop)
        region = SentenceRegion(bufnr, start, stop, text)
        logger.debug('Forward in session [%s]: %s', bufnr, region)
        session.forward(region, self._ui_cmds)

    @in_session
    def backward(self, session, bufnr):
        '''Backward to the previous sentence in the current session.'''
        if session.is_busy():
            logger.debug('Session [%s] busy.', bufnr)
            return

        logger.debug('Backward in session [%s]', bufnr)
        session.backward(self._ui_cmds)

    @in_session
    def to_cursor(self, session, bufnr):
        '''Process to the sentence under the cursor.'''
        if session.is_busy():
            logger.debug('Session [%s] busy.', bufnr)
            return

        stop = session.get_last_stop()
        cursor = get_cursor()
        if cursor.line > stop.line or \
                (cursor.line == stop.line and cursor.col > stop.col):
            self._forward_to_cursor(session, bufnr, cursor)
        else:
            logger.debug('Backward to cursor in session [%s]', bufnr)
            session.backward_before_mark(cursor, self._ui_cmds)

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

    @in_session
    def focus(self, session, bufnr):
        '''The current buffer has got focus.'''
        if bufnr != self._focused_bufnr:
            if self._focused_bufnr in self._sessions:
                logger.debug('Unfocus session [%s]', self._focused_bufnr)
                self._sessions[self._focused_bufnr].unfocus(self._ui_cmds)
            logger.debug('Focus session [%s]', bufnr)
            self._focused_bufnr = bufnr
            session.focus(self._ui_cmds)

    def update_ui(self):
        '''Update the UI events.'''
        try:
            self._ui_cmds.update_ui()
        except vim.error:
            logger.debug('Catched exception in update_ui', exc_info=True)

    def _get_current_session(self):
        '''Return the session bound to the current buffer.'''
        bufnr = int(vim.eval('bufnr("%")'))
        return self._sessions.get(bufnr, None), bufnr

    def _forward_to_cursor(self, session, bufnr, cursor):
        '''Go forward to the sentence before the cursor.'''
        logger.debug('Forward to cursor in session [%s]', bufnr)

        start = session.get_last_stop()
        cursor = get_cursor()
        regions = []

        while True:
            stop = find_stop_after(start)
            if stop is None or \
                    stop.line > cursor.line or \
                    (stop.line == cursor.line and stop.col > cursor.col):
                break

            text = get_buffer_text(start, stop)
            region = SentenceRegion(bufnr, start, stop, text)
            regions.append(region)
            start = stop

        logger.debug('Forward to cursor in session [%s]: %s', bufnr, regions)
        session.forward_many(regions, self._ui_cmds)
