'''Coq views.'''


from collections import namedtuple
import logging
from threading import Lock


logger = logging.getLogger(__name__)         # pylint: disable=C0103


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
            raise RuntimeError('Run task twice')
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

    def has_task(self):
        '''Return True if the executor has scheduled tasks.'''
        return len(self._task_list) > 0

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

    def __init__(self, match_arg, vim):
        self.match_arg = match_arg
        self._win_match_id = {}
        self._vim = vim

    def show(self, winid):
        '''Show the match in the given window.

        The method assumes that the current window is the target window.
        '''
        if winid in self._win_match_id:
            return

        start, stop, match_type = self.match_arg
        hlgroup = self._HLGROUPS[match_type]
        self._win_match_id[winid] = self._vim.add_match(start, stop, hlgroup)

    def hide(self, winid):
        '''Hide the match from the given window.

        The method assumes that the current window is the target window.
        '''
        if winid not in self._win_match_id:
            return

        self._vim.del_match(self._win_match_id[winid])
        del self._win_match_id[winid]

    def redraw(self, winid):
        '''Redraw the match.'''
        if winid in self._win_match_id:
            self.hide(winid)
            self.show(winid)


class _MatchView:
    '''The matches in a documents.'''

    def __init__(self, vim):
        self._match_map = {}
        self._win_executors = {}
        self._vim = vim

    def set_active(self, winid):
        '''Show the view in the window-ID `winid`.'''
        if winid in self._win_executors:
            return

        self._win_executors[winid] = _TaskExecutor()

        with self._vim.in_winid(winid):
            for match in self._match_map.values():
                match.show(winid)

    def set_inactive(self, winid):
        '''Remove the view in the window-ID `winid`.'''
        if winid not in self._win_executors:
            return

        del self._win_executors[winid]

        with self._vim.in_winid(winid):
            for match in self._match_map.values():
                match.hide(winid)

    def add(self, match_id, start, stop, match_type):
        ''''Add a match to the view.'''
        match_arg = _MatchArg(start, stop, match_type)
        match = _Match(match_arg, self._vim)
        self._match_map[match_id] = match

        for winid, executor in self._win_executors.items():
            executor.add(match_id, match.show, winid)

    def move(self, match_id, line_offset):
        '''Move the match `line_offset` lines down.'''
        match = self._match_map[match_id]

        start, stop, _ = match.match_arg
        match.match_arg = match.match_arg._replace(
            start=start._replace(line=start.line + line_offset),
            stop=stop._replace(line=stop.line + line_offset))

        for winid, executor in self._win_executors.items():
            executor.add_nokey(match.redraw, winid)

    def remove(self, match_id):
        '''Remove the match.'''
        match = self._match_map[match_id]
        del self._match_map[match_id]

        for winid, executor in self._win_executors.items():
            if not executor.cancel(match_id):
                executor.add_nokey(match.hide, winid)

    def draw(self):
        '''Draw the matches in the Vim window.

        This function only applies the changes since the last time it is called
        to Vim.
        '''
        for winid, executor in self._win_executors.items():
            if executor.has_task():
                with self._vim.in_winid(winid):
                    executor.run_all()


class TabpageView:
    '''The view relating to the tabpage.'''

    def __init__(self, vim):
        self._goals = None
        self._messages = []
        self._vim = vim
        self._goals_changed = False
        self._messages_changed = False

    def draw(self):
        '''Draw the goals and messages to the goal and message panel.'''
        if self._goals_changed:
            self.redraw_goals()
            self._goals_changed = False

        if self._messages_changed:
            self.redraw_messages()
            self._messages_changed = False

    def redraw_goals(self):
        '''Redraw the goals to the goal window.'''
        if self._goals:
            self._vim.set_bufname_lines('/Goals/', self._goals.tolines())
        else:
            self._vim.set_bufname_lines('/Goals/', [])

    def redraw_messages(self):
        '''Redraw the messages to the message window.'''
        content = []
        for _, message in self._messages:
            content.extend(message.split('\n'))

        self._vim.set_bufname_lines('/Messages/', content)

    def show_message(self, level, message):
        '''Show the message in the message window.'''
        self._messages.append((level, message))
        self._messages_changed = True

    def set_goals(self, goals):
        '''Show the goals in the goal window.'''
        self._goals = goals
        self._goals_changed = True

    def clear_messages(self):
        '''Clear the messages.'''
        self._messages.clear()
        self._messages_changed = True


class SessionView:
    '''The view relating to a session.'''

    def __init__(self, bufnr, tabpage_view, vim):
        self._bufnr = bufnr
        self._tabpage_view = tabpage_view
        self._match_view = _MatchView(vim)
        self._focused = False
        self._goals = None
        self._messages = []
        self._vim = vim

    def draw(self):
        '''Draw the view in Vim UI.'''
        self._match_view.draw()

    def show_message(self, level, message):
        '''Show the message in the message window.'''
        logger.debug('SView show message: %s %s', level, message)
        self._messages.append((level, message))
        if self._focused:
            self._tabpage_view.show_message(level, message)

    def set_goals(self, goals):
        '''Show the goals in the goal window.'''
        logger.debug('SView set goals: %s', goals)
        self._goals = goals
        if self._focused:
            self._tabpage_view.set_goals(goals)

    def focus(self):
        '''Focus the view.'''
        if self._focused:
            return

        self._focused = True
        self._tabpage_view.clear_messages()
        for level, message in self._messages:
            self._tabpage_view.show_message(level, message)
        if self._goals:
            self._tabpage_view.set_goals(self._goals)

    def unfocus(self):
        '''Unfocus the view.'''
        if not self._focused:
            return
        self._focused = False

    def set_active(self):
        '''Set the view as active in the current window.'''
        winid = self._vim.get_winid()
        self._match_view.set_active(winid)
        self._tabpage_view.set_goals(self._goals)
        for level, message in self._messages:
            self._tabpage_view.show_message(level, message)

    def set_inactive(self):
        '''Set the view as inactive in the current window.'''
        winid = self._vim.get_winid()
        self._match_view.set_inactive(winid)

    def new_match(self, match_id, start, stop, match_type):
        '''Create a new match on the window and return the match object.'''
        logger.debug('SView new match: %s %s %s %s', match_id, start, stop,
                     match_type)
        self._match_view.add(match_id, start, stop, match_type)

    def move_match(self, match_id, line_offset):
        '''Move the position of a match.'''
        logger.debug('SView move match: %s %s', match_id, line_offset)
        self._match_view.move(match_id, line_offset)

    def remove_match(self, match_id):
        '''Remove a match.'''
        logger.debug('SView remove match: %s', match_id)
        self._match_view.remove(match_id)

    def destroy(self):
        '''Destroy the view.'''
        self.unfocus()
        self.set_inactive()
