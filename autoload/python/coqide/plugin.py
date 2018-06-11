'''The plugin module.'''

from functools import wraps
from queue import Queue
from threading import Thread, Lock
import logging

from coqide.vimsupport import VimSupport
from coqide.views import TabpageView, SessionView
from coqide.session import Session


logger = logging.getLogger(__name__)


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
            except Exception:
                logger.exception('Background thread has exception')
                raise
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
        if not self._worker.is_busy():                 # pylint: disable=W0212
            func(self, *args, **kwargs)
    return _wrapped


def _draw_views(func):
    '''Draw the changes of views to Vim before and after the function
    is called.'''
    @wraps(func)
    def _wrapped(self, *args, **kwargs):
        self.do_draw_views()
        try:
            func(self, *args, **kwargs)
        finally:
            self.do_draw_views()
    return _wrapped


def _catch_exception(func):
    '''Log the exception throwed in the function.'''
    @wraps(func)
    def _wrapped(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except:                # pylint: disable=W0702
            logger.exception('Exception in plugin')
    return _wrapped

class Plugin:
    '''The plugin entry point.'''

    def __init__(self):
        self._vim = VimSupport()
        self._sessions = {}
        self._session_views = {}
        self._tabpage_view = TabpageView(self._vim)
        self._worker = _ThreadExecutor()
        self._last_focused_bufnr = None

    @_catch_exception
    @_draw_views
    def new_session(self):
        '''Create a new session on the current buffer.'''
        buf = self._vim.get_buffer()
        bufnr = buf.number
        if bufnr in self._sessions:
            print('Already in a Coq session')
            return
        logger.debug('Create session on buffer: %s [%s]', buf.name, bufnr)
        session_view = SessionView(bufnr, self._tabpage_view, self._vim)
        session = Session(session_view, self._vim, self._worker)
        self._sessions[bufnr] = session
        self._session_views[bufnr] = session_view

    @_catch_exception
    @_draw_views
    @_in_session
    def close_session(self, session, buf):
        '''Close the session on the current buffer.'''
        logger.debug('Close session on buffer: %s [%s]', buf.name, buf.number)
        session.close()
        del self._sessions[buf.number]
        del self._session_views[buf.number]

    @_catch_exception
    @_draw_views
    @_in_session
    @_not_busy
    def forward_one(self, session, buf):     # pylint: disable=R0201
        '''Forward one sentence.'''
        logger.debug('Session [%s]: forward one', buf.name)
        session.forward_one()

    @_catch_exception
    @_draw_views
    @_in_session
    @_not_busy
    def backward_one(self, session, buf):    # pylint: disable=R0201
        '''Backward one sentence.'''
        logger.debug('Session [%s]: backward one', buf.name)
        session.backward_one()

    @_catch_exception
    @_draw_views
    @_in_session
    @_not_busy
    def to_cursor(self, session, buf):       # pylint: disable=R0201
        '''Run to cursor.'''
        logger.debug('Session [%s]: to cursor', buf.name)
        session.to_cursor()

    @_catch_exception
    @_draw_views
    def redraw_goals(self):
        '''Redraw the goals to the goal window.'''
        logger.debug('Redraw goals')
        self._tabpage_view.redraw_goals()

    @_catch_exception
    @_draw_views
    def redraw_messages(self):
        '''Redraw the messages to the message window.'''
        logger.debug('Redraw messages')
        self._tabpage_view.redraw_messages()

    @_catch_exception
    @_draw_views
    @_not_busy
    def process_feedbacks(self):
        '''Process the feedbacks received by each session.'''
        for session in self._sessions.values():
            session.process_feedbacks()

    @_catch_exception
    @_draw_views
    @_in_session
    def focus(self, _, buf):
        '''Focus a session.'''
        if buf.number == self._last_focused_bufnr:
            return
        logger.debug('Session [%s]: focus', buf.name)
        if self._last_focused_bufnr is not None:
            last_view = self._session_views[self._last_focused_bufnr]
            last_view.unfocus()
        self._last_focused_bufnr = buf.number
        cur_view = self._session_views[self._last_focused_bufnr]
        cur_view.focus()

    @_catch_exception
    @_draw_views
    @_in_session
    def set_active(self, _, buf):           # pylint: disable=R0201
        '''Set the session active in a window.'''
        logger.debug('Session [%s]: set window active', buf.name)
        view = self._session_views[buf.number]
        view.set_active()

    @_catch_exception
    @_draw_views
    @_in_session
    def set_inactive(self, _, buf):        # pylint: disable=R0201
        '''Set the session inactive in a window.'''
        logger.debug('Session [%s]: set window inactive', buf.name)
        view = self._session_views[buf.number]
        view.set_inactive()

    @_catch_exception
    @_draw_views
    def clear_messages(self):
        '''Clear the messages in the message window.'''
        logger.debug('Clear messages')
        self._tabpage_view.clear_messages()

    def cleanup(self):
        '''Cleanup the plugin.'''
        logger.debug('Plugin clean up')
        for session in self._sessions.values():
            session.close()
        for view in self._session_views.values():
            view.destroy()
        self._sessions.clear()
        self._session_views.clear()
        self._worker.shutdown()

    def do_draw_views(self):
        '''Draw the changes of the views to Vim.'''
        self._tabpage_view.draw()
        for view in self._session_views.values():
            view.draw()
