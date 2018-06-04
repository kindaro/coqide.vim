'''Test module `coqide.plugin`.'''

from threading import Semaphore
from unittest import TestCase
from unittest.mock import patch

from coqide.plugin import _ThreadExecutor, Plugin


class TestThreadExecutor(TestCase):
    '''Test class `_ThreadExecutor`.'''

    @staticmethod
    def _task_func(start_sem, finish_sem, result):
        '''Acquire `start_sem`, set `result[0]` to `42` and release
        `finish_sem`.'''
        start_sem.acquire()
        result[0] = 42
        finish_sem.release()

    def test_submit(self):
        '''Test submitting tasks.'''
        start_sem = Semaphore(0)
        finish_sem = Semaphore(0)
        result = [None]
        worker = _ThreadExecutor()

        try:
            self.assertFalse(worker.is_busy())
            worker.submit(self._task_func, start_sem, finish_sem, result)
            self.assertTrue(worker.is_busy())
            self.assertEqual(result[0], None)
            start_sem.release()
            finish_sem.acquire()
            self.assertEqual(result[0], 42)
            self.assertFalse(worker.is_busy())
        finally:
            worker.shutdown()
