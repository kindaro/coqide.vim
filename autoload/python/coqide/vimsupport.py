'''The functions for Vim operations.'''

from contextlib import contextmanager
from itertools import chain

from coqide.types import Mark, Sentence


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

    OP_START_SENTENCE = 102
    '''Special operation. The leading spaces (including comments) stop here.'''

    OP_NOT_COMMENT = 103
    '''Special operation. It is not the beginning of a comment.'''

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
            None: OP_START_SENTENCE,
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
            None: OP_NOT_COMMENT,
        },
        COMMENT: {
            '*': POST_COMMENT,
            '(': PRE_COMMENT,
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
        self._start_sentence = False
        self._chars = []

    def feed(self, char):
        '''Feed a character and move to the next state.'''
        trans = self._TRANSITIONS[self._state]
        state_or_op = trans.get(char, trans[None])
        self._chars.append(char)

        if state_or_op == self.OP_ENTER_COMMENT:
            self._nesting_level += 1
            self._state = self.COMMENT
        elif state_or_op in (self.OP_LEAVE_COMMENT, self.OP_NOT_COMMENT):
            if state_or_op == self.OP_LEAVE_COMMENT:
                self._nesting_level -= 1

            if self._nesting_level:
                self._state = self.COMMENT
            elif self._start_sentence:
                self._state = self.FREE
            else:
                self._state = self.LEADING_SPACE
        elif state_or_op == self.OP_START_SENTENCE:
            self._start_sentence = True
            self._state = self.FREE
        else:
            self._state = state_or_op

        return self._state == self.FINAL

    def text(self):
        '''Return the matched text.'''
        return ''.join(self._chars)


class _MatchAdder:
    '''Add matches where the number of lines exceeds 8.'''

    def __init__(self, hlgroup, api):
        self._args = []
        self._ids = []
        self._hlgroup = hlgroup
        self._api = api

    def add(self, line, start_col, len_):
        '''Add part of a line to the match.'''
        self._args.append([line, start_col, len_])
        if len(self._args) == 8:
            self._matchaddpos()

    def add_line(self, line):
        '''Add the whole line to the match.'''
        self._args.append(line)
        if len(self._args) == 8:
            self._matchaddpos()

    def finish(self):
        '''Indicate no more lines.'''
        self._matchaddpos()

    def result(self):
        '''Get the Vim match IDs in a list.'''
        return self._ids

    def _matchaddpos(self):
        cmd = 'matchaddpos("{}", {})'.format(self._hlgroup, self._args)
        self._ids.append(int(self._api.eval(cmd)))
        self._args.clear()


class VimSupport:
    '''The class that communicates with Vim.'''

    def __init__(self, api=None):
        '''Create a VimSupport class with the given Vim api module.

        If `api == None`, the system-default `vim` module is used.
        '''
        if not api:
            import vim                             # pylint: disable=E0401
            self._api = vim
        else:
            self._api = api

    def get_buffer(self):
        '''Return the current buffer.'''
        return self._api.current.buffer

    def get_sentence_after(self, start):
        '''Return the sentence object containing the text after the start mark.'''
        # Map 1-indexed position into 0-indexed.
        start_line, start_col = start.line - 1, start.col - 1
        matcher = _SentenceEndMatcher()

        # The cursor is 1-indexed.
        cursor_line, cursor_col = start

        vimbuf = self._api.current.buffer

        for char in vimbuf[start_line][start_col:]:
            cursor_col += 1
            matched = matcher.feed(char)
            if matched:
                stop = Mark(cursor_line, cursor_col)
                return Sentence(matcher.text(), start, stop)

        for line in chain(vimbuf[start_line+1:], ['']):
            cursor_line += 1
            cursor_col = 1
            matched = matcher.feed('\n')
            if matched:
                stop = Mark(cursor_line, cursor_col)
                return Sentence(matcher.text(), start, stop)

            for char in line:
                cursor_col += 1
                matched = matcher.feed(char)
                if matched:
                    stop = Mark(cursor_line, cursor_col)
                    return Sentence(matcher.text(), start, stop)

        return None

    def get_cursor(self):
        '''Return the position of the cursor in Mark.'''
        _, line, col, _ = self._api.eval('getpos(".")')
        return Mark(line, col)

    def add_match(self, start, stop, hlgroup):
        '''Add a match to the current window and return the match id.'''
        buf = self.get_buffer()
        match_adder = _MatchAdder(hlgroup, self._api)

        if start.line == stop.line:
            len1 = stop.col - start.col
        else:
            len1 = len(buf[start.line - 1]) - start.col + 1

        if len1 > 0:
            match_adder.add(start.line, start.col, len1)

        for line in range(start.line + 1, stop.line):
            match_adder.add_line(line)

        if start.line != stop.line and stop.col > 1:
            match_adder.add(stop.line, 1, stop.col - 1)

        match_adder.finish()
        return match_adder.result()

    def del_match(self, match_id):
        '''Remove the match of the given id.'''
        for id_ in match_id:
            self._api.eval('matchdelete({})'.format(id_))

    @contextmanager
    def in_winid(self, winid):
        '''Switch to the window of the window-ID.'''
        saved_view = self._api.eval('winsaveview()')
        saved_winnr = self._api.eval('winnr()')

        winnr = self._api.eval('win_id2win({})'.format(winid))
        self._api.command('{}wincmd w'.format(winnr))
        try:
            yield
        finally:
            self._api.command('{}wincmd w'.format(saved_winnr))
            self._api.eval('winrestview({})'.format(saved_view))

    def set_bufname_lines(self, bufname, lines):
        '''Set the content of the buffer whose name is `bufname` to `lines`.

        `lines` is a list of strings without trailing "\n".
        '''
        for buf in self._api.buffers:
            if buf.name == bufname:
                buf[:] = lines
                break
