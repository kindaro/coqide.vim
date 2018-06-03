'''The action dispatching module.'''


from threading import Lock


# pylint: disable=C0103
_task_list = []
_task_lock = Lock()


def dispatch(func, *args, **kwargs):
    '''Dispatch a task.

    The task will be run when `run_tasks` is called.'''
    with _task_lock:
        _task_list.append((func, args, kwargs))


def run_tasks():
    '''Run the pending tasks.'''
    with _task_lock:
        for func, args, kwargs in _task_list:
            func(*args, **kwargs)
        _task_list.clear()
