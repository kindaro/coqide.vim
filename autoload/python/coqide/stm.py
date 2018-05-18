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
from . import actions
from .sentence import Sentence, Mark


logger = logging.getLogger(__name__)        # pylint: disable=C0103


class _SequentialTaskThread:
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
                logger.debug('Runs task: %s ...', name)
                task(done)
                task_done.acquire()
                self._scheduled_task_count -= 1
                logger.debug('Finish task: %s.', name)
            logger.debug('_SequentialTaskThread quits normally.')

        thread = threading.Thread(target=thread_main)
        thread.start()
        logger.debug('_SequentialTaskThread starts.')

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


def _finally_call(cleanup):
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


class _FeedbackHandler:                                # pylint: disable=R0903
    '''A functional that handles the feedbacks.'''

    _FEEDBACK_HANDLERS = [
        [xp.ErrorMsg, '_on_error_msg'],
        [xp.Message, '_on_message'],
        [xp.Processed, '_on_processed'],
        [xp.AddedAxiom, '_on_added_axiom'],
    ]

    def __init__(self, state_id_map, handle_action, handle_sentence_error):
        '''Create a feedback handler.

        The handler requires the property `state_id_map` of the STM object in a read-only manner.
        '''
        self._state_id_map = state_id_map
        self._handle_action = handle_action
        self._handle_sentence_error = handle_sentence_error

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
            sentence.set_error(error_msg.location, error_msg.message, self._handle_action)
            self._handle_sentence_error(self._handle_action)
        else:
            self._handle_action(actions.ShowMessage(error_msg.message, 'error'))

    def _on_message(self, message, sentence):
        '''Process Message.'''
        if message.level == 'error':
            if sentence:
                sentence.set_error(message.location, message.message, self._handle_action)
                self._handle_sentence_error(self._handle_action)
            else:
                self._handle_action(actions.ShowMessage(message.message, 'error'))
        else:
            self._handle_action(actions.ShowMessage(message.message, message.level))

    def _on_processed(self, _, sentence):
        '''Highlight the sentence to "Processed" state.'''
        if sentence:
            sentence.set_processed(self._handle_action)

    def _on_added_axiom(self, _, sentence):
        '''Highlight the sentence to "Unsafe" state.'''
        if sentence:
            sentence.set_axiom(self._handle_action)


class STM:
    '''A STM records the execution state of a Coq document.

    It cares about only forwarding and backwarding.
    '''

    def __init__(self, bufnr):
        '''Create a empty state machine.

        `bufnr` is the number of the related buffer. It never directly uses `bufnr`, only as an
        identifier to make UI actions.'''
        self._sentences = []
        self._state_id_map = {}
        self._failed_sentence = None
        self._init_state_id = None
        self._task_thread = _SequentialTaskThread()
        self._bufnr = bufnr

    def make_feedback_handler(self, handle_action):
        '''Return an associated feedback handler.'''
        return _FeedbackHandler(self._state_id_map, handle_action, self._on_sentence_error)

    def init(self, call_async, handle_action):
        '''Initialize the state machine.'''
        def task(done):
            '''Send Init call.'''
            @_finally_call(done)
            def on_res(xml):
                '''Process the Init response.'''
                res = xp.InitRes.from_xml(xml)
                if not res.error:
                    self._init_state_id = res.init_state_id
                else:
                    raise RuntimeError(res.error.message)
            call_async(xp.InitReq(), on_res, self._make_on_lost_cb(done, handle_action))
        self._task_thread.schedule(task, 'init')

    def forward(self, sregion, call_async, handle_action):
        '''Forward one sentence.'''
        if self._sentences and self._sentences[-1].has_error():
            handle_action(actions.ShowMessage('Fix the error first', 'error'))
            return
        self._forward_one(sregion, call_async, handle_action)
        self._update_goal(call_async, handle_action)

    def forward_many(self, sregions, call_async, handle_action):
        '''The bulk call of `forward`.'''
        if self._sentences and self._sentences[-1].has_error():
            handle_action(actions.ShowMessage('Fix the error first.', 'error'))
            return
        for sregion in sregions:
            self._forward_one(sregion, call_async, handle_action)
        self._update_goal(call_async, handle_action)

    def backward(self, call_async, handle_action):
        '''Go backward to the previous state.'''
        def task(done):
            '''Go backward to the previous state of the current state.'''
            if self._sentences:
                last = len(self._sentences) - 1
                self._backward_before_index(last, done, call_async, handle_action)
            else:
                done()
        self._task_thread.schedule(task, 'backward')
        self._update_goal(call_async, handle_action)

    def backward_before_mark(self, mark, call_async, handle_action):
        '''Go backward to the sentence before the given mark.'''
        def task(done):
            '''Find the sentence and go backward.'''
            for i, sentence in enumerate(self._sentences):
                stop = sentence.region.stop
                if stop.line > mark.line or \
                        (stop.line == mark.line and stop.col > mark.col):
                    self._backward_before_index(i, done, call_async, handle_action)
                    break
            else:
                done()
        self._task_thread.schedule(task, 'backward_before_mark')
        self._update_goal(call_async, handle_action)

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

    def close(self, handle_action):
        '''Close and clean up the state machine.'''
        self._task_thread.shutdown_join()
        for sentence in self._sentences:
            sentence.unhighlight(handle_action)
        self._sentences = []
        self._state_id_map = {}

    def _forward_one(self, sregion, call_async, handle_action):
        '''Accept a new sentence region and go forward.'''
        def task(done):
            '''Send Add call.'''
            @_finally_call(done)
            def on_res(xml):
                '''Process the Add response.'''
                res = xp.AddRes.from_xml(xml)
                if not res.error:
                    state_id = res.new_state_id
                    sentence = Sentence(sregion, state_id)
                    self._sentences.append(sentence)
                    self._state_id_map[state_id] = sentence
                    sentence.set_processing(handle_action)
                    handle_action(actions.ShowMessage(res.message, 'info'))
                else:
                    self._task_thread.discard_scheduled_tasks()
                    sentence = Sentence(sregion, 0)
                    self._failed_sentence = sentence
                    sentence.set_error(res.error.location, res.error.message, handle_action)

            self._clear_failed_sentence(handle_action)
            req = xp.AddReq(sregion.command, -1, self._tip_state_id(), False)
            call_async(req, on_res, self._make_on_lost_cb(done, handle_action))
        self._task_thread.schedule(task, 'forward_one')

    def _clear_failed_sentence(self, handle_action):
        '''Clear the highlighting of the last sentence that cannot be added.'''
        if self._failed_sentence:
            self._failed_sentence.unhighlight(handle_action)
            self._failed_sentence = None

    def _tip_state_id(self):
        '''Return the tip state id.'''
        if self._sentences:
            return self._sentences[-1].state_id
        return self._init_state_id

    def _backward_before_index(self, index, done, call_async, handle_action):
        '''Go backward to the state of `self._sentences[index - 1]`.

        If `index == 0`, go to the initial state.
        '''
        @_finally_call(done)
        def on_res(xml):
            '''Process EditAt response and remove the trailing sentences.'''
            res = xp.EditAtRes.from_xml(xml)
            if not res.error:
                for sentence in self._sentences[index:]:
                    sentence.unhighlight(handle_action)
                    del self._state_id_map[sentence.state_id]
                del self._sentences[index:]

        if index == 0:
            state_id = self._init_state_id
        else:
            state_id = self._sentences[index - 1].state_id
        self._clear_failed_sentence(handle_action)
        req = xp.EditAtReq(state_id)
        call_async(req, on_res, self._make_on_lost_cb(done, handle_action))

    def _update_goal(self, call_async, handle_action):
        '''Update the goals.'''
        def task(done):
            '''Send Goal call.'''
            @_finally_call(done)
            def on_res(xml):
                '''Process the Goal response.'''
                res = xp.GoalRes.from_xml(xml)
                if not res.error:
                    handle_action(actions.ShowGoals(res.goals))
            call_async(xp.GoalReq(), on_res, self._make_on_lost_cb(done, handle_action))
        self._task_thread.schedule(task, 'get_goals')

    def _make_on_lost_cb(self, done, handle_action):
        '''Return an on-connection-lost callback that notifies the UI and discards all the schedule
        tasks.'''
        @_finally_call(done)
        def callback():
            '''Process the connection lost event.'''
            self._task_thread.discard_scheduled_tasks()
            for sentence in self._sentences:
                sentence.unhighlight(handle_action)
            self._sentences = []
            self._state_id_map = {}
            handle_action(actions.ConnLost(self._bufnr))
        return callback

    def _on_sentence_error(self, handle_action):
        '''Handle the feedback of sentence errors.

        It removes all the sentences after the first error sentence.'''
        self._task_thread.discard_scheduled_tasks()

        for index, sentence in enumerate(self._sentences):
            if sentence.has_error():
                start_index = index + 1
                break
        else:
            return

        for sentence in self._sentences[start_index:]:
            sentence.unhighlight(handle_action)
            del self._state_id_map[sentence.state_id]
        del self._sentences[start_index:]
