'''The plugin module.'''

from functools import wraps
from queue import Queue
from threading import Thread, Lock

from coqide.vimsupport import VimSupport
from coqide.views import TabpageView, SessionView
from coqide.session import Session


class _ThreadExecutor:
    '''A class that uses a background thread to execute the tasks sent to it.
    '''

    def __init__(self):
        self._task_queue = Queue()
        self._closed = False
        self._task_count = 0
        self._task_count_lock = Lock()
        self._thread = Thread(target=self._thread_main)
        self._thread.start()

    def submit(self, func, *args, **kwargs):
        '''Schedule the task `fn(*args, **kwargs)` to be executed.'''
        with self._task_count_lock:
            self._task_count += 1
        self._task_queue.put((func, args, kwargs))

    def shutdown(self):
        '''Stop the background thread.

        The tasks that have not been executed are cancelled.
        '''
        self._closed = True
        self._task_queue.put(None)
        self._thread.join()

    def _thread_main(self):
        '''The entry point for the background thread.'''
        while True:
            task = self._task_queue.get()
            if task is None or self._closed:
                break
            func, args, kwargs = task
            try:
                func(*args, **kwargs)
            except Exception as exn:           # pylint: disable=W0703
                print('Background thread has exception: {}'.format(exn))
            with self._task_count_lock:
                self._task_count -= 1

    def is_busy(self):
        '''Return True if the background thread is executing tasks.'''
        return self._task_count > 0


def _in_session(func):
    '''Decorate a method so that the first argument is the session object
    and the second the buffer.

    The method will not be called if it is not in a Coq session.'''
    @wraps(func)
    def _wrapped(self, *args, **kwargs):
        buf = self._vim.get_buffer()                     # pylint: disable=W0212
        session = self._sessions.get(buf.number, None)   # pylint: disable=W0212
        if session is None:
            print('Not in a Coq session')
            return
        func(self, session, buf, *args, **kwargs)
    return _wrapped


def _not_busy(func):
    '''Decorate a method so that it is called only if the task executor
    is not busy.'''
    @wraps(func)
    def _wrapped(self, *args, **kwargs):
        if not self._executor.is_busy():                 # pylint: disable=W0212
            func(self, *args, **kwargs)
    return _wrapped


def _draw_views(func):
    '''Draw the changes of views to Vim before and after the function
    is called.'''
    @wraps(func)
    def _wrapped(self, *args, **kwargs):
        self.draw_views()
        try:
            func(self, *args, **kwargs)
        finally:
            self.draw_views()
    return _wrapped


class Plugin:
    '''The plugin entry point.'''

    def __init__(self):
        self._vim = VimSupport()
        self._sessions = {}
        self._session_views = {}
        self._tabpage_view = TabpageView(self._vim)
        self._worker = _ThreadExecutor()

    @_draw_views
    def new_session(self):
        '''Create a new session on the current buffer.'''
        bufnr = self._vim.get_buffer().number
        if bufnr in self._sessions:
            print('Already in a Coq session')
            return
        session_view = SessionView(bufnr, self._tabpage_view, self._vim)
        session = Session(session_view, self._vim, self._worker)
        self._sessions[bufnr] = session
        self._session_views[bufnr] = session_view

    @_draw_views
    @_in_session
    def close_session(self, session, buf):
        '''Close the session on the current buffer.'''
        session.close()
        del self._sessions[buf.number]
        del self._session_views[buf.number]

    @_draw_views
    @_in_session
    @_not_busy
    def forward_one(self, session, _):     # pylint: disable=R0201
        '''Forward one sentence.'''
        session.forward_one()

    @_draw_views
    @_in_session
    @_not_busy
    def backward_one(self, session, _):    # pylint: disable=R0201
        '''Backward one sentence.'''
        session.backward_one()

    @_draw_views
    @_in_session
    @_not_busy
    def to_cursor(self, session, _):       # pylint: disable=R0201
        '''Run to cursor.'''
        session.to_cursor()

    @_draw_views
    def redraw_goals(self):
        '''Redraw the goals to the goal window.'''
        self._tabpage_view.redraw_goals()

    @_draw_views
    def redraw_messages(self):
        '''Redraw the messages to the message window.'''
        self._tabpage_view.redraw_messages()

    def cleanup(self):
        '''Cleanup the plugin.'''
        self._worker.shutdown()

    def draw_views(self):
        '''Draw the changes of the views to Vim.'''
        self._tabpage_view.draw()
        for view in self._session_views.values():
            view.draw()
