'''Test for module `coqide.views`.'''

from unittest import TestCase
from unittest.mock import Mock, MagicMock, call

from coqide.views import _Task, _TaskExecutor, _MatchArg, _Match, _MatchView
from coqide.types import Mark


# pylint: disable=R0201
class TestTask(TestCase):
    '''Test for class `_Task`.'''

    def test_run(self):
        '''Test running a task.'''
        func = Mock()
        task = _Task(func, (1, 2), {'key': 3})
        task.run()
        func.assert_called_once_with(1, 2, key=3)

    def test_run_twice(self):
        '''Test running a task twice.'''
        func = Mock()
        task = _Task(func, (1, 2), {'key': 3})
        task.run()
        self.assertRaises(RuntimeError, task.run)

    def test_cancel(self):
        '''Test cancelling a task.'''
        func = Mock()
        task = _Task(func, (1, 2), {'key': 3})
        task.cancel()
        task.run()
        func.assert_not_called()


class TestTaskExecutor(TestCase):
    '''Test for class `_TaskExecutor`.'''

    def test_add(self):
        '''Test adding tasks and running all.'''
        func1 = Mock()
        func2 = Mock()
        executor = _TaskExecutor()
        executor.add('func1', func1, 1, s=4)
        executor.add_nokey(func2, 3, s=5)
        executor.run_all()
        func1.assert_called_once_with(1, s=4)
        func2.assert_called_once_with(3, s=5)

    def test_cancel(self):
        '''Test cancelling tasks.'''
        func1 = Mock()
        func2 = Mock()
        executor = _TaskExecutor()
        executor.add('func1', func1, 1, s=4)
        executor.add_nokey(func2, 3, s=5)
        self.assertTrue(executor.cancel('func1'))
        self.assertFalse(executor.cancel('func2'))
        executor.run_all()
        func1.assert_not_called()
        func2.assert_called_once_with(3, s=5)


class TestMatch(TestCase):
    '''Test for call `_Match`.'''

    def test_show_hide(self):
        '''Test method `show`.'''
        vim = Mock()
        arg = _MatchArg(Mark(1, 3), Mark(5, 9), 'sent')
        match = _Match(arg, vim)

        vim.add_match.side_effect = [12]
        match.show(3)
        vim.add_match.assert_called_once_with(
            Mark(1, 3), Mark(5, 9), 'CoqStcSent')
        match.hide(3)
        vim.del_match.assert_called_once_with(12)

    def test_redraw_shown(self):
        '''Test method `redraw` when the match is shown.'''
        vim = Mock()
        arg = _MatchArg(Mark(1, 3), Mark(5, 9), 'sent')
        match = _Match(arg, vim)

        vim.add_match.side_effect = [12, 13]
        match.show(3)
        match.redraw(3)
        vim.del_match.assert_called_once_with(12)
        vim.add_match.assert_called_with(Mark(1, 3), Mark(5, 9), 'CoqStcSent')

    def test_redraw_not_shown(self):
        '''Test method `redraw` when the match is not shown.'''
        vim = Mock()
        arg = _MatchArg(Mark(1, 3), Mark(5, 9), 'sent')
        match = _Match(arg, vim)

        vim.add_match.side_effect = [12, 13]
        match.redraw(3)
        vim.del_match.assert_not_called()
        vim.add_match.assert_not_called()

        match.show(3)
        vim.add_match.assert_called_with(Mark(1, 3), Mark(5, 9), 'CoqStcSent')


class TestMatchView(TestCase):
    '''Test class `_MatchView`.'''

    def test_add_active(self):
        '''Test method `add` when the view is active.'''
        vim = Mock()
        vim.in_winid = MagicMock()
        view = _MatchView(vim)
        view.set_active(3)
        view.add(42, Mark(1, 1), Mark(2, 4), 'sent')
        view.add(43, Mark(2, 4), Mark(2, 7), 'verified')
        view.draw()
        self.assertListEqual(vim.add_match.call_args_list, [
            call(Mark(1, 1), Mark(2, 4), 'CoqStcSent'),
            call(Mark(2, 4), Mark(2, 7), 'CoqStcVerified'),
        ])
        vim.in_winid.assert_called_with(3)

    def test_add_inactive(self):
        '''Test method `add` when the view is inactive.'''
        vim = Mock()
        vim.in_winid = MagicMock()
        view = _MatchView(vim)
        view.add(42, Mark(1, 1), Mark(2, 4), 'sent')
        view.add(43, Mark(2, 4), Mark(2, 7), 'verified')
        view.draw()
        vim.add_match.assert_not_called()
        vim.in_winid.assert_not_called()

    def test_set_active(self):
        '''Test method `set_active` with matches.'''
        vim = Mock()
        vim.in_winid = MagicMock()
        view = _MatchView(vim)
        view.add(42, Mark(1, 1), Mark(2, 4), 'sent')
        view.add(43, Mark(2, 4), Mark(2, 7), 'verified')
        view.draw()
        vim.add_match.assert_not_called()
        vim.in_winid.assert_not_called()

        view.set_active(3)
        vim.in_winid.assert_called_once_with(3)
        self.assertListEqual(vim.add_match.call_args_list, [
            call(Mark(1, 1), Mark(2, 4), 'CoqStcSent'),
            call(Mark(2, 4), Mark(2, 7), 'CoqStcVerified'),
        ])

    def test_set_inactive(self):
        '''Test method `set_inactive` with matches.'''
        vim = Mock()
        vim.in_winid = MagicMock()
        vim.add_match.side_effect = ['x', 'y']
        view = _MatchView(vim)
        view.set_active(3)
        view.add(42, Mark(1, 1), Mark(2, 4), 'sent')
        view.add(43, Mark(2, 4), Mark(2, 7), 'verified')
        view.draw()
        vim.reset_mock()

        view.set_inactive(3)
        vim.in_winid.assert_called_once_with(3)
        self.assertListEqual(vim.del_match.call_args_list,
                             [call('x'), call('y')])
