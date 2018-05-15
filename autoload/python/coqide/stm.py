'''Coq state machine.

In this module defines STM, a Coq state machine.

Each Coq document being edited contains a state machine that records
the execution state of the document.
'''

import functools
import logging
import queue
import threading

from . import xmlprotocol as xp
from .sentence import Sentence, Mark


logger = logging.getLogger(__name__)        # pylint: disable=C0103


class SequentialTaskThread:
    '''A thread that executes the tasks in the order that they are emitted.

    Another task must be executed only after one task has already been done.
    For example, when adding a bulk of sentences, the Add request of the second sentence
    requires the state id of the first, which is available only after receiving the response.

    This class manages the execution order of the tasks. Only after a task calls the `done` callback
    will the following get executed.
    '''

    def __init__(self):
        '''Create a thread that executes the tasks in sequence.'''
        self._closing = False
        self._scheduled_task_count = 0
        schedule_queue = queue.Queue(100)
        task_done = threading.Semaphore(0)

        def done():
            '''The callback to resume the task processing loop.'''
            task_done.release()

        def thread_main():
            '''Repeat executing the tasks and waiting for them to be done.'''
            while True:
                task, name = schedule_queue.get()
                if task is None or self._closing:
                    break
                logger.debug('SequentialTaskThread runs task: %s ...', name)
                task(done)
                task_done.acquire()
                self._scheduled_task_count -= 1
                logger.debug('SequentialTaskThread gets task done: %s.', name)
            logger.debug('SequentialTaskThread quits normally.')

        thread = threading.Thread(target=thread_main)
        thread.start()
        logger.debug('SequentialTaskThread starts.')

        self._schedule_queue = schedule_queue
        self._thread = thread

    def schedule(self, task, name):
        '''Schedule a task for running.

        `task` should be a unary function that receives a callback. The task calls
        the callback when done to notify the thread to execute the next.
        '''
        assert task is not None
        self._scheduled_task_count += 1
        self._schedule_queue.put((task, name))

    def shutdown_join(self):
        '''Discard all the pending tasks and wait for the thread to quit.'''
        self._closing = True
        try:
            self._schedule_queue.put_nowait((None, None))
        except queue.Full:
            pass
        self._thread.join()

    def discard_scheduled_tasks(self):
        '''Discard all the scheduled tasks in the queue.

        It is called when the failure of a task cancels the following.
        '''
        try:
            while True:
                self._schedule_queue.get_nowait()
                self._scheduled_task_count -= 1
        except queue.Empty:
            pass

    def scheduled_task_count(self):
        '''Return the number of scheduled tasks (including the running task).'''
        return self._scheduled_task_count


def finally_call(cleanup):
    '''A function decorator that call `cleanup` on the exit of the decorated function
    no matter what.'''
    def wrapper(func):                  # pylint: disable=C0111
        @functools.wraps(func)
        def wrapped(*args, **kwargs):   # pylint: disable=C0111
            try:
                return func(*args, **kwargs)
            finally:
                cleanup()
        return wrapped
    return wrapper


class FeedbackHandler:                                # pylint: disable=R0903
    '''A functional that handles the feedbacks.'''

    _FEEDBACK_HANDLERS = [
        [xp.ErrorMsg, '_on_error_msg'],
        [xp.Message, '_on_message'],
        [xp.Processed, '_on_processed'],
        [xp.AddedAxiom, '_on_added_axiom'],
    ]

    def __init__(self, state_id_map, ui_cmds):
        '''Create a feedback handler.

        The handler requires the property `state_id_map` of the STM object in a read-only manner.
        It uses `ui_cmds` to display the feedbacks.
        '''
        self._state_id_map = state_id_map
        self._ui_cmds = ui_cmds

    def __call__(self, feedback):
        '''Process the given feedback.

        If the feedback is processed, return True. Otherwise, return False.'''
        sentence = self._state_id_map.get(feedback.state_id, None)

        for fb_type, fb_handler_name in self._FEEDBACK_HANDLERS:
            if isinstance(feedback.content, fb_type):
                logger.debug('FeedbackHandler processes: %s', feedback)
                handler = getattr(self, fb_handler_name)
                handler(feedback.content, sentence)
                return True
        return False

    def _on_error_msg(self, error_msg, sentence):
        '''Process ErrorMsg.'''
        if sentence:
            sentence.set_error(error_msg.location, error_msg.message,
                               self._ui_cmds.highlight, self._ui_cmds.show_message)
        else:
            self._ui_cmds.show_message(error_msg.message, True)

    def _on_message(self, message, sentence):
        '''Process Message.'''
        if message.level == 'error':
            if sentence:
                sentence.set_error(message.location, message.message,
                                   self._ui_cmds.highlight, self._ui_cmds.show_message)
            else:
                self._ui_cmds.show_message(message.message, True)
        else:
            self._ui_cmds.show_message(message.message, False)

    def _on_processed(self, _, sentence):
        '''Highlight the sentence to "Processed" state.'''
        logger.debug('Before on_processed')
        if sentence:
            logger.debug('Sentence: %s', sentence.region)
            sentence.set_processed(self._ui_cmds.highlight)
        logger.debug('After on_processed')

    def _on_added_axiom(self, _, sentence):
        '''Highlight the sentence to "Unsafe" state.'''
        if sentence:
            sentence.set_axiom(self._ui_cmds.highlight)


class STM:
    '''A STM records the execution state of a Coq document.

    Compared to a whole document, it cares about only forwarding and backwarding.

    The methods defined in this class usually requires two special parameters:

    - `call_async`: a function that communicates with the coqtop process
    - `ui_cmds`: an object that provides UI update operations, including:
      + `show_message`: show the message in the message panel
      + `show_goal`: show the goal in the goal panel
      + `highlight`: highlight the given region
      + `connection_lost`: notify that the connection to the coqtop process is lost
    '''

    def __init__(self):
        '''Create a empty state machine.
        '''
        self._next_edit_id = -1
        self._sentences = []
        self._state_id_map = {}
        self._failed_sentence = None
        self._init_state_id = None
        self._task_thread = SequentialTaskThread()

    def make_feedback_handler(self, ui_cmds):
        '''Return an associated feedback handler.'''
        return FeedbackHandler(self._state_id_map, ui_cmds)

    def init(self, call_async, ui_cmds):
        '''Initialize the state machine.'''
        def task(done):
            '''Send Init call.'''
            @finally_call(done)
            def on_res(xml):
                '''Process the Init response.'''
                res = xp.InitRes.from_xml(xml)
                if not res.error:
                    self._init_state_id = res.init_state_id
                else:
                    raise RuntimeError(res.error.message)
            call_async(xp.InitReq(), on_res, self._make_on_lost_cb(done, ui_cmds))
        self._task_thread.schedule(task, 'init')

    def forward(self, sregion, call_async, ui_cmds):
        '''Forward one sentence.'''
        self._forward_one(sregion, call_async, ui_cmds)
        self._update_goal(call_async, ui_cmds)

    def forward_many(self, sregions, call_async, ui_cmds):
        '''The bulk call of `forward`.'''
        for sregion in sregions:
            self._forward_one(sregion, call_async, ui_cmds)
        self._update_goal(call_async, ui_cmds)

    def backward(self, call_async, ui_cmds):
        '''Go backward to the previous state.'''
        def task(done):
            '''Go backward to the previous state of the current state.'''
            last = len(self._sentences) - 1
            self._backward_before_index(last, done, call_async, ui_cmds)
        self._task_thread.schedule(task, 'backward')
        self._update_goal(call_async, ui_cmds)

    def backward_before_mark(self, mark, call_async, ui_cmds):
        '''Go backward to the sentence before the given mark.'''
        def task(done):
            '''Find the sentence and go backward.'''
            for i, sentence in enumerate(self._sentences):
                stop = sentence.region.stop
                if stop.line > mark.line or \
                        (stop.line == mark.line and stop.col > mark.col):
                    self._backward_before_index(i, done, call_async, ui_cmds)
                    break
            else:
                done()
        self._task_thread.schedule(task, 'backward_before_mark')
        self._update_goal(call_async, ui_cmds)

    def get_last_stop(self):
        '''Return the stop of the last sentence.'''
        if self._sentences:
            return self._sentences[-1].region.stop
        return Mark(1, 1)

    def is_busy(self):
        '''Return True if there is scheduled tasks.'''
        count = self._task_thread.scheduled_task_count()
        logger.debug('STM scheduled task count: %s', count)
        return count > 0

    def close(self):
        '''Close and clean up the state machine.'''
        self._task_thread.shutdown_join()
        for sentence in self._sentences:
            sentence.unhighlight()
        self._sentences = []
        self._state_id_map = {}

    def _forward_one(self, sregion, call_async, ui_cmds):
        '''Accept a new sentence region and go forward.

        `call_async` is provided by `CoqtopHandle`.
        `highlight` is the UI highlighting function.
        '''
        def task(done):
            '''Send Add call.'''
            @finally_call(done)
            def on_res(xml):
                '''Process the Add response.'''
                res = xp.AddRes.from_xml(xml)
                if not res.error:
                    state_id = res.new_state_id
                    sentence = Sentence(sregion, state_id)
                    self._sentences.append(sentence)
                    self._state_id_map[state_id] = sentence
                    sentence.set_processing(ui_cmds.highlight)
                    ui_cmds.show_message(res.message, False)
                else:
                    self._task_thread.discard_scheduled_tasks()
                    sentence = Sentence(sregion, 0)
                    self._failed_sentence = sentence
                    sentence.set_error(res.error.location, res.error.message,
                                       ui_cmds.highlight, ui_cmds.show_message)

            self._clear_failed_sentence()
            req = xp.AddReq(sregion.command, self._alloc_edit_id(),
                            self._tip_state_id(), False)
            call_async(req, on_res, self._make_on_lost_cb(done, ui_cmds))
        self._task_thread.schedule(task, 'forward_one')

    def _clear_failed_sentence(self):
        '''Clear the highlighting of the last sentence that cannot be added.'''
        if self._failed_sentence:
            self._failed_sentence.unhighlight()
            self._failed_sentence = None

    def _tip_state_id(self):
        '''Return the tip state id.'''
        if self._sentences:
            return self._sentences[-1].state_id
        return self._init_state_id

    def _backward_before_index(self, index, done, call_async, ui_cmds):
        '''Go backward to the state of `self._sentences[index - 1]`.

        If `index == 0`, go to the initial state.
        '''
        @finally_call(done)
        def on_res(xml):
            '''Process EditAt response and remove the trailing sentences.'''
            res = xp.EditAtRes.from_xml(xml)
            if not res.error:
                for sentence in self._sentences[index:]:
                    sentence.unhighlight()
                    del self._state_id_map[sentence.state_id]
                del self._sentences[index:]
            else:
                raise RuntimeError('Edit_at should not fail: {}'.format(res.error))

        if index == 0:
            state_id = self._init_state_id
        else:
            state_id = self._sentences[index - 1].state_id
        self._clear_failed_sentence()
        req = xp.EditAtReq(state_id)
        call_async(req, on_res, self._make_on_lost_cb(done, ui_cmds))

    def _alloc_edit_id(self):
        '''Return next fresh edit id.'''
        value = self._next_edit_id
        self._next_edit_id -= 1
        return value

    def _update_goal(self, call_async, ui_cmds):
        '''Update the goals.'''
        def task(done):
            '''Send Goal call.'''
            @finally_call(done)
            def on_res(xml):
                '''Process the Goal response.'''
                res = xp.GoalRes.from_xml(xml)
                if not res.error:
                    ui_cmds.show_goal(res.goals)
                else:
                    if res.error.state_id in self._state_id_map:
                        sentence = self._state_id_map[res.error.state_id]
                        sentence.show_error(res.error.location, res.error.message,
                                            ui_cmds.highlight, ui_cmds.show_message)
                    else:
                        ui_cmds.show_message(res.error.message, True)
            call_async(xp.GoalReq(), on_res, self._make_on_lost_cb(done, ui_cmds))
        self._task_thread.schedule(task, 'get_goals')

    def _make_on_lost_cb(self, done, ui_cmds):
        '''Return an on-connection-lost callback that notifies the UI and discards all the schedule
        tasks.'''
        @finally_call(done)
        def callback():
            '''Process the connection lost event.'''
            self._task_thread.discard_scheduled_tasks()
            for sentence in self._sentences:
                sentence.unhighlight()
            self._sentences = []
            self._state_id_map = {}
            ui_cmds.connection_lost()
        return callback
