'''The plugin module.'''

from functools import wraps
from queue import Queue
from threading import Thread, Lock

from coqide import vimsupport as vims
from coqide.views import TabpageView
from coqide.session import Session


class _ThreadExecutor:
    '''A class that uses a background thread to execute the tasks sent to it.
    '''

    def __init__(self):
        self._thread = Thread(target=self._thread_main)
        self._thread.start()
        self._task_queue = Queue()
        self._closed = False
        self._task_count = 0
        self._task_count_lock = Lock()

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


class Plugin:
    '''The plugin entry point.'''

    def __init__(self):
        self._sessions = {}
        self._tabpage_view = TabpageView()
        self._executor = _ThreadExecutor()

    @staticmethod
    def _in_session(func):
        '''Decorate a method so that the first argument is the session object
        and the second the buffer.

        The method will not be called if it is not in a Coq session.'''
        @wraps(func)
        def _wrapped(self, *args, **kwargs):
            buf = vims.get_buffer()
            session = self._sessions.get(buf.number, None)   # pylint: disable=W0212
            if session is None:
                print('Not in a Coq session')
                return
            func(self, session, buf, *args, **kwargs)
        return _wrapped

    @staticmethod
    def _not_busy(func):
        '''Decorate a method so that it is called only if the task executor
        is not busy.'''
        @wraps(func)
        def _wrapped(self, *args, **kwargs):
            if not self._executor.is_busy():                 # pylint: disable=W0212
                func(self, *args, **kwargs)
        return _wrapped

    def new_session(self):
        '''Create a new session on the current buffer.'''
        bufnr = vims.get_buffer().number
        if bufnr in self._sessions:
            print('Already in a Coq session')
            return
        self._sessions[bufnr] = Session(bufnr, self._tabpage_view, self._executor)

    @_in_session
    def close_session(self, session, buf):
        '''Close the session on the current buffer.'''
        session.close()
        del self._sessions[buf.number]

    @_in_session
    @_not_busy
    def forward_one(self, session, _):     # pylint: disable=R0201
        '''Forward one sentence.'''
        session.forward_one()

    @_in_session
    @_not_busy
    def backward_one(self, session, _):    # pylint: disable=R0201
        '''Backward one sentence.'''
        session.backward_one()

    @_in_session
    @_not_busy
    def to_cursor(self, session, _):       # pylint: disable=R0201
        '''Run to cursor.'''
        session.to_cursor()

    def redraw_goals(self):
        '''Redraw the goals to the goal window.'''
        self._tabpage_view.redraw_goals()

    def redraw_messages(self):
        '''Redraw the messages to the message window.'''
        self._tabpage_view.redraw_messages()

    def draw(self):
        '''Draw the modified parts to the Vim windows.'''
        self._tabpage_view.draw()
        for session in self._sessions.values():
            session.draw_view()
