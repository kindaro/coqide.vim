'''Coq views.'''


from collections import namedtuple
from threading import Lock

from coqide import vimsupport as vims
from coqide.stm import STM


_MatchArg = namedtuple('_MatchArg', 'start stop type')


class _Task:
    '''A cancellable task.'''

    def __init__(self, func, args, kwargs):
        '''Create a task.'''
        self._func = func
        self._args = args
        self._kwargs = kwargs
        self._cancelled = False
        self._done = False

    def run(self):
        '''Run the task.

        If the task is called, nothing happens.'''
        if self._cancelled:
            return

        if self._done:
            raise RuntimeError('Run a task twice')
        self._done = True
        self._func(*self._args, **self._kwargs)

    def cancel(self):
        '''Cancel the task.'''
        self._cancelled = True


class _TaskExecutor:
    '''A task executor.'''

    def __init__(self):
        self._task_map = {}
        self._task_list = []
        self._lock = Lock()

    def add(self, key, func, *args, **kwargs):
        '''Add a task with key to the executor.

        The key can be any object that support equality comparison.

        The key can be used to cancel the task afterwards.'''
        task = _Task(func, args, kwargs)
        with self._lock:
            self._task_map[key] = task
            self._task_list.append(task)
        return task

    def add_nokey(self, func, *args, **kwargs):
        '''Add a task without key to the executor.'''
        task = _Task(func, args, kwargs)
        with self._lock:
            self._task_list.append(task)
        return task

    def cancel(self, key):
        '''Cancel the task whose key is `key`.

        Return True if the task exists.'''
        with self._lock:
            task = self._task_map.get(key, None)
            if task:
                task.cancel()
                return True
            return False

    def run_all(self):
        '''Run all the tasks.'''
        with self._lock:
            for task in self._task_list:
                task.run()
            self._task_list.clear()
            self._task_map.clear()


class _Match:
    '''A match object in the window.'''

    _HLGROUPS = {
        'sent': 'CoqStcSent',
        'axiom': 'CoqStcAxiom',
        'error': 'CoqStcError',
        'error_part': 'CoqStcErrorPart',
        'verified': 'CoqStcVerified',
    }

    def __init__(self, match_id, match_arg):
        self.match_id = match_id
        self.match_arg = match_arg
        self._vim_match_id = None

    def show(self):
        '''Show the match in Vim.'''
        assert self._vim_match_id is None

        start = self.match_arg.start
        stop = self.match_arg.stop
        hlgroup = self._HLGROUPS[self.match_arg.type]
        self._vim_match_id = vims.add_match(start, stop, hlgroup)

    def hide(self):
        '''Hide the match from Vim.'''
        assert self._vim_match_id is not None
        vims.del_match(self._vim_match_id)
        self._vim_match_id = None

    def is_shown(self):
        '''Return True if the match is shown in Vim.'''
        return self._vim_match_id is not None

    def remove(self):
        '''Remove the match.'''
        if self.is_shown():
            self.hide()

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


class _MatchView:
    '''The matches in a documents.'''

    def __init__(self, bufnr):
        self._bufnr = bufnr
        self._active = False
        self._match_map = {}
        self._task_executor = _TaskExecutor()

    def set_active(self):
        '''Add the matches to the Vim window of the buffer.'''
        if self._active:
            return

        self._active = True
        for match in self._match_map.values():
            match.show()

    def set_inactive(self):
        '''Remove the matches added to the Vim window.'''
        if not self._active:
            return

        self._active = False
        for match in self._match_map.values():
            match.hide()

    def add(self, match_id, start, stop, match_type):
        ''''Add a match to the view.'''
        match_arg = _MatchArg(start, stop, match_type)
        match = _Match(match_id, match_arg)
        self._match_map[match_id] = match
        self._task_executor.add(match_id, match.show)

    def move(self, match_id, line_offset):
        '''Move the match `line_offset` lines down.'''
        match = self._match_map[match_id]
        self._task_executor.add_nokey(match.move, line_offset)

    def remove(self, match_id):
        '''Remove the match.'''
        if not self._task_executor.cancel(match_id):
            match = self._match_map[match_id]
            del self._match_map[match_id]
            self._task_executor.add_nokey(match.remove)

    def draw(self):
        '''Draw the matches in the Vim UI.'''
        self._task_executor.run_all()


class TabpageView:
    '''The view relating to the tabpage.'''

    def __init__(self):
        self._goals = None
        self._messages = []
        self._task_executor = _TaskExecutor()

    def draw(self):
        '''Draw the goals and messages to the goal and message panel.'''
        self._task_executor.run_all()

    def redraw_goals(self):
        '''Redraw the goals to the goal window.'''

    def redraw_messages(self):
        '''Redraw the messages to the message window.'''

    def show_message(self, level, message):
        '''Show the message in the message window.'''
        self._messages.append((level, message))
        self._task_executor.add_nokey(self._do_show_message, level, message)

    def set_goals(self, goals):
        '''Show the goals in the goal window.'''
        self._goals = goals
        self._task_executor.cancel('goal')
        self._task_executor.add('goal', self._do_set_goals, goals)

    def _do_show_message(self, level, message):
        pass

    def _do_set_goals(self, goals):
        pass


class SessionView:
    '''The view relating to a session.'''

    def __init__(self, bufnr, tabpage_view):
        self._bufnr = bufnr
        self._tabpage_view = tabpage_view

        self._match_view = _MatchView(bufnr)
        self._focused = False
        self._goals = None
        self._messages = []

    def draw(self):
        '''Draw the view in Vim UI.'''
        self._match_view.draw()

    def destroy(self):
        '''Detach the session view.'''

    def show_message(self, level, message):
        '''Show the message in the message window.'''
        self._messages.append((level, message))
        if self._focused:
            self._tabpage_view.show_message(level, message)

    def set_goals(self, goals):
        '''Show the goals in the goal window.'''
        self._goals = goals
        if self._focused:
            self._tabpage_view.set_goals(goals)

    def focus(self):
        '''Focus the view.'''
        if self._focused:
            return

        self._focused = True
        for level, message in self._messages:
            self._tabpage_view.show_message(level, message)
        self._tabpage_view.set_goals(self._goals)

    def unfocus(self):
        '''Unfocus the view.'''
        if not self._focused:
            return
        self._focused = False

    def set_active(self):
        '''Set the view as active.'''
        self._match_view.set_active()
        self._tabpage_view.set_goals(self._goals)
        for level, message in self._messages:
            self._tabpage_view.show_message(level, message)

    def set_inactive(self):
        '''Set the view as inactive.'''
        self._match_view.set_inactive()

    def new_match(self, match_id, start, stop, match_type):
        '''Create a new match on the window and return the match object.'''
        self._match_view.add(match_id, start, stop, match_type)

    def move_match(self, match_id, line_offset):
        '''Move the position of a match.'''
        self._match_view.move(match_id, line_offset)

    def remove_match(self, match_id):
        '''Remove a match.'''
        self._match_view.remove(match_id)
