import time
import traceback
from functools import partial
from collections import abc
import multiprocessing as mp
from threading import Thread
from itertools import count
from queue import Empty

from tqdm.auto import tqdm

from .tools import (
    get_len,
    func_args_unpack,
)
from .wrappers import (
    ProgressStatus,
    stopit_after_timeout,
    init_worker,
)

try:
    import dill
except ImportError:
    dill = None

__all__ = ['progress_map', 'progress_imap', 'progress_imapu', 'progress_starmap', 'Parallel']


class ProgressBar(tqdm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def close(self):
        super().close()
        if hasattr(self, 'disp'):
            if self.total and self.n < self.total:
                self.disp(bar_style='warning')


def _update_error_bar(bar_dict, bar_parameters):
    try:
        bar_dict['bar'].update()
    except KeyError:
        bar_dict['bar'] = ProgressBar(**bar_parameters)
        bar_dict['bar'].update()


def _process_status(bar_size, worker_queue, error_queue=None, return_failed_tasks=False, desc='DONE'):
    bar = ProgressBar(total=bar_size, desc=desc)
    error_bar_parameters = dict(total=bar_size, position=1, desc='ERROR', colour='red')
    error_bar = {}
    error_bar_n = 0
    sub_bars = {}
    next_position = 2
    while True:
        item = worker_queue.get()
        flag, upd_value = item[0], item[1]
        meta = item[2] if len(item) > 2 else None
        if flag is None:
            if error_bar:
                error_bar_n = error_bar['bar'].n
                error_bar['bar'].close()
            for sub_bar in sub_bars.values():
                if upd_value != -1 and sub_bar.total and sub_bar.n < sub_bar.total:
                    sub_bar.update(sub_bar.total - sub_bar.n)
                sub_bar.close()
            if bar.n < bar_size and upd_value != -1:
                bar.update(bar_size - bar.n - error_bar_n)
            bar.close()
            break
        if flag:
            _update_error_bar(error_bar, error_bar_parameters)
            if return_failed_tasks:
                error_queue.put(upd_value)
        else:
            bar.update(upd_value)
            if meta is not None:
                name, sub_total = meta
                if name not in sub_bars:
                    sub_bars[name] = ProgressBar(total=sub_total, desc=name, position=next_position)
                    next_position += 1
                sub_bars[name].update(upd_value)


def _deserialize(func, task):
    return dill.loads(func)(task)


def _attach_traceback(exc):
    """Attach the worker-side traceback (as a string) to an exception.

    multiprocessing pickles exceptions back to the parent without their __traceback__,
    so we capture the formatted traceback in the worker and expose it as ``exc.traceback``.
    """
    try:
        exc.traceback = traceback.format_exc()
    except Exception:
        pass
    return exc


def _func_wrapped(func, error_handling, set_error_value, worker_queue, disable, task, cnt=count(1),
                  state=ProgressStatus()):
    try:
        result = func(task)
    except Exception as e:
        if error_handling == 'raise':
            if not disable:
                worker_queue.put((None, -1))
            raise
        else:
            if not disable:
                worker_queue.put((1, task))
            if set_error_value is None:
                return _attach_traceback(e)
        return set_error_value
    else:
        if not disable:
            updated = next(cnt)
            time_now = time.perf_counter()
            delta_t = time_now - state.last_update_t
            if updated == state.next_update or delta_t > .25:
                delta_i = updated - state.last_update_val

                state.next_update += max(int((delta_i / delta_t) * .25), 1)
                state.last_update_val = updated
                state.last_update_t = time_now
                worker_queue.put_nowait((0, delta_i))

    return result


def _execute(pool, pool_type, func, tasks, chunk_size, bar_size, disable, queue,
             error_queue, return_failed_tasks, timeout, desc='DONE'):
    """Run a prepared func over tasks on the given pool and drive the progress bar.

    The pool is used but not closed here, so it can be a warm/reused pool.
    """
    raised_exception = False
    thread = Thread(target=_process_status,
                    args=(bar_size, queue),
                    kwargs={"error_queue": error_queue, 'return_failed_tasks': return_failed_tasks, 'desc': desc},
                    daemon=True,
                    )
    try:
        if not disable:
            thread.start()
        if pool_type == 'map':
            result = pool.map_async(func, tasks, chunksize=chunk_size).get(timeout=timeout)
        else:
            result = list()
            method = getattr(pool, pool_type)
            iter_result = method(func, tasks, chunksize=chunk_size)
            while 1:
                try:
                    result.append(next(iter_result))
                except StopIteration:
                    break
    except BaseException as e:
        # BaseException so that KeyboardInterrupt/SystemExit also stop the status thread
        # cleanly and are re-raised (instead of being swallowed by the return below).
        raised_exception = e
    finally:
        # signal the status thread to stop and wait for it to finish
        if thread.is_alive():
            queue.put((None, -1 if raised_exception else None))
            thread.join()
        if raised_exception:
            raise raised_exception
        # drain error_queue if it exists
        if return_failed_tasks:
            error_tasks = list()
            while True:
                try:
                    error_tasks.append(error_queue.get_nowait())
                except Empty:
                    break
            return result, error_tasks
    return result


def _do_parallel(func, pool_type, tasks, initializer, initargs, n_cpu, chunk_size, context, total, disable,
                 error_behavior, set_error_value, executor, need_serialize, maxtasksperchild, used_decorators,
                 return_failed_tasks, timeout=None, desc='DONE'
                 ):
    bar_size = get_len(tasks, total)
    if need_serialize:
        func = partial(_deserialize, func)
    with mp.Manager() as manager:
        queue = manager.Queue()
        error_queue = manager.Queue() if return_failed_tasks else None
        if not used_decorators:
            func = partial(_func_wrapped, func, error_behavior, set_error_value, queue, disable)
        if executor == 'threads':
            exc_pool = mp.pool.ThreadPool(n_cpu, initializer=init_worker,
                                          initargs=(queue, initializer, initargs))
        else:
            exc_pool = mp.get_context(context).Pool(maxtasksperchild=maxtasksperchild,
                                                    processes=n_cpu, initializer=init_worker,
                                                    initargs=(queue, initializer, initargs))
        with exc_pool as p:
            return _execute(p, pool_type, func, tasks, chunk_size, bar_size, disable, queue,
                            error_queue, return_failed_tasks, timeout, desc=desc)


def _run_once(pool, manager, pool_type, func, tasks, chunk_size, total, disable,
              error_behavior, set_error_value, need_serialize, return_failed_tasks, timeout, desc='DONE'):
    """Run a single map/imap pass on an existing (warm) pool and manager."""
    if need_serialize:
        func = partial(_deserialize, func)
    queue = manager.Queue()
    error_queue = manager.Queue() if return_failed_tasks else None
    wrapped = partial(_func_wrapped, func, error_behavior, set_error_value, queue, disable)
    bar_size = get_len(tasks, total)
    return _execute(pool, pool_type, wrapped, tasks, chunk_size, bar_size, disable, queue,
                    error_queue, return_failed_tasks, timeout, desc=desc)


def _run_with_retries(run_once, tasks, retries, error_behavior, set_error_value, return_failed_tasks):
    """Run tasks, retrying the ones that raised, up to `retries` extra attempts.

    `run_once(subset, desc)` must run in 'coerce' mode with set_error_value=None, so failed
    tasks come back as exception instances that can be detected and re-submitted.
    """
    tasks = list(tasks)
    results = list(run_once(tasks, 'DONE'))
    pending = [i for i, r in enumerate(results) if isinstance(r, BaseException)]
    attempt = 0
    while pending and attempt < retries:
        attempt += 1
        subset = [tasks[i] for i in pending]
        res = run_once(subset, f'RETRY {attempt}')
        still_failed = []
        for local_i, r in enumerate(res):
            gi = pending[local_i]
            results[gi] = r
            if isinstance(r, BaseException):
                still_failed.append(gi)
        pending = still_failed
    failed_tasks = [tasks[i] for i in pending]
    if error_behavior == 'raise':
        if pending:
            raise results[pending[0]]
    elif set_error_value is not None:
        for i in pending:
            results[i] = set_error_value
    if return_failed_tasks:
        return results, failed_tasks
    return results


def _stopit_wrapped(func, s, raise_exception, *args, **kwargs):
    return stopit_after_timeout(s, raise_exception=raise_exception)(func)(*args, **kwargs)


def _func_prepare(func, process_timeout, need_serialize):
    if process_timeout:
        func = partial(_stopit_wrapped, func, process_timeout, True)
    if need_serialize:
        if dill is None:
            raise ModuleNotFoundError('You must install the dill package to serialize functions.')
        func = dill.dumps(func)
    return func


def _validate_args(error_behavior, tasks, total, executor):
    if error_behavior not in ['raise', 'coerce']:
        raise ValueError(
            'Invalid error_handling value specified. Must be one of the values: "raise", "coerce"')
    if executor not in ['threads', 'processes']:
        raise ValueError(
            'Invalid executor value specified. Must be one of the values: "threads", "processes"')
    if isinstance(tasks, abc.Iterator) and not total:
        raise ValueError('If the tasks are an iterator, the total parameter must be specified')


def progress_map(func, tasks, initializer=None, initargs=(), n_cpu=None, chunk_size=None, context=None, total=None,
                 disable=False, process_timeout=None, error_behavior='raise', set_error_value=None,
                 executor='processes', need_serialize=False, maxtasksperchild=None, used_add_progress_decorator=False,
                 return_failed_tasks=False, timeout=None, retries=0,
                 ):
    """
    An extension of the map method of the multiprocessing.Poll class that allows you to display the progress of tasks,
    handle exceptions, and set a timeout for the function to execute.

    Parameters:
    ----------
    func: сallable
        A function that will be applied element by element to the tasks
         iterable.
    tasks: Iterable
        The func function will be applied to the task elements.
    initializer: сallable or None, default None
    initargs: tuple
    n_cpu: int, or None, default None
        number of workers, if None n_cpu = multiprocessing.cpu_count().
    chunk_size: int or None, default None
    context: str or None, default None
        Can be 'fork', 'spawn' or 'forkserver'.
    total: int or None, default None
        The number of elements in tasks. Must be specified if task is iterator.
    disable: bool, default False
        if True don't show progress bar.
    process_timeout: float or None, default None
        If not None, a TimeoutError exception will be raised if the function execution time exceeds
        the specified value in seconds.
    error_behavior: str, default 'raise'
        Can be 'raise' or 'coerce'
        - If 'raise', then the exception that occurs when calling the func function will be raised.
        - If 'coerce', then the exception that occurs when calling the func function will be processed and
        the result of the function execution will be the value set in set_error_value.
    set_error_value: Any, default None
        The value to be returned in case of exception handling. Only matters if error_behavior='coerce'.
        if None, the exception traceback will be returned.
    executor: str, default 'processes'
        Can be 'processes' or 'threads'
        - if 'processes', uses processes pool
        - if 'threads', use threads pool
    need_serialize: bool, default False
        If True  function will be serialized with dill library.
    used_add_progress_decorator: bool, default False
    return_failed_tasks: bool, default False
        If True, the function will return a tuple of two lists: the first list will contain the results of the
        function execution,  the second list will contain the tasks that caused the exception.
    timeout: float, optional
        If timeout is not None and the result does not arrive within timeout seconds then multiprocessing.TimeoutError
        is raised
    retries: int, default 0
        Number of extra attempts for tasks that raised an exception (including process_timeout).
        Failed tasks are re-submitted up to `retries` times. Not compatible with
        used_add_progress_decorator=True.
    Returns
    -------
    result: list

    """
    _validate_args(error_behavior, tasks, total, executor)
    func = _func_prepare(func, process_timeout, need_serialize)
    if retries:
        if used_add_progress_decorator:
            raise ValueError('retries is not compatible with used_add_progress_decorator=True')

        def run_once(subset, desc):
            return _do_parallel(func, 'map', subset, initializer, initargs, n_cpu, chunk_size, context,
                                len(subset), disable, 'coerce', None, executor, need_serialize,
                                maxtasksperchild, False, False, timeout=timeout, desc=desc)

        return _run_with_retries(run_once, tasks, retries, error_behavior, set_error_value, return_failed_tasks)
    result = _do_parallel(func, 'map', tasks, initializer, initargs, n_cpu, chunk_size, context, total, disable,
                          error_behavior, set_error_value, executor, need_serialize, maxtasksperchild,
                          used_add_progress_decorator, return_failed_tasks, timeout=timeout,
                          )
    return result


def progress_starmap(func, tasks, initializer=None, initargs=(), n_cpu=None, chunk_size=None, context=None, total=None,
                     disable=False, process_timeout=None, error_behavior='raise', set_error_value=None,
                     executor='processes', need_serialize=False, maxtasksperchild=None,
                     used_add_progress_decorator=False, return_failed_tasks=False, timeout=None, retries=0,
                     ):
    """
    An extension of the starmap method of the multiprocessing.Poll class that allows you to display
    the progress of tasks, handle exceptions, and set a timeout for the function to execute.

    Parameters:
    ----------
    func: сallable
        A function that will be applied element by element to the tasks iterable.
    tasks: Iterable
        The func function will be applied to the task elements.
    initializer: сallable or None, default None
    initargs: tuple
    n_cpu: int, or None, default None
        number of workers, if None n_cpu = multiprocessing.cpu_count().
    chunk_size: int or None, default None
    context: str or None, default None
        Can be 'fork', 'spawn' or 'forkserver'.
    total: int or None, default None
        The number of elements in tasks. Must be specified if task is iterator.
    disable: bool, default False
        if True don't show progress bar.
    process_timeout: float or None, default None
        If not None, a TimeoutError exception will be raised if the function execution time exceeds
        the specified value in seconds.
    error_behavior: str, default 'raise'
        Can be 'raise' or 'coerce'
        - If 'raise', then the exception that occurs when calling the func function will be raised.
        - If 'coerce', then the exception that occurs when calling the func function will be processed and
        the result of the function execution will be the value set in set_error_value.
    set_error_value: Any, default None
        The value to be returned in case of exception handling. Only matters if error_behavior='coerce'.
        if None, the exception traceback will be returned.
    executor: str, default 'processes'
        Can be 'processes' or 'threads'
        - if 'processes', uses processes pool
        - if 'threads', use threads pool
    need_serialize: bool, default False
        If True  function will be serialized with dill library.
    used_add_progress_decorator: bool, default False
    return_failed_tasks: bool, default False
        If True, the function will return a tuple of two lists: the first list will contain the results of the
        function execution,  the second list will contain the tasks that caused the exception.
    timeout: float, optional
        If timeout is not None and the result does not arrive within timeout seconds then multiprocessing.TimeoutError
        is raised
    retries: int, default 0
        Number of extra attempts for tasks that raised an exception (including process_timeout).
        Failed tasks are re-submitted up to `retries` times. Not compatible with
        used_add_progress_decorator=True.
    Returns
    -------
    result: list

    """
    _validate_args(error_behavior, tasks, total, executor)
    func = partial(func_args_unpack, func)
    func = _func_prepare(func, process_timeout, need_serialize)
    if retries:
        if used_add_progress_decorator:
            raise ValueError('retries is not compatible with used_add_progress_decorator=True')

        def run_once(subset, desc):
            return _do_parallel(func, 'map', subset, initializer, initargs, n_cpu, chunk_size, context,
                                len(subset), disable, 'coerce', None, executor, need_serialize,
                                maxtasksperchild, False, False, timeout=timeout, desc=desc)

        return _run_with_retries(run_once, tasks, retries, error_behavior, set_error_value, return_failed_tasks)
    result = _do_parallel(func, 'map', tasks, initializer, initargs, n_cpu, chunk_size, context, total, disable,
                          error_behavior, set_error_value, executor, need_serialize, maxtasksperchild,
                          used_add_progress_decorator, return_failed_tasks, timeout=timeout,
                          )
    return result


def progress_imap(func, tasks, initializer=None, initargs=(), n_cpu=None, chunk_size=1, context=None, total=None,
                  disable=False, process_timeout=None, error_behavior='raise', set_error_value=None,
                  executor='processes', need_serialize=False, maxtasksperchild=None, used_add_progress_decorator=False,
                  return_failed_tasks=False, retries=0,
                  ):
    """
    An extension of the imap method of the multiprocessing.Poll class that allows you to display the progress of tasks,
    handle exceptions, and set a timeout for the function to execute.

    Parameters:
    ----------
    func: сallable
        A function that will be applied element by element to the tasks
         iterable.
    tasks: Iterable
        The func function will be applied to the task elements.
    initializer: сallable or None, default None
    initargs: tuple
    n_cpu: int, or None, default None
        number of workers, if None n_cpu = multiprocessing.cpu_count().
    chunk_size: int or None, default None
    context: str or None, default None
        Can be 'fork', 'spawn' or 'forkserver'.
    total: int or None, default None
        The number of elements in tasks. Must be specified if task is iterator.
    disable: bool, default False
        if True don't show progress bar.
    process_timeout: float or None, default None
        If not None, a TimeoutError exception will be raised if the function execution time exceeds
        the specified value in seconds.
    error_behavior: str, default 'raise'
        Can be 'raise' or 'coerce'
        - If 'raise', then the exception that occurs when calling the func function will be raised.
        - If 'coerce', then the exception that occurs when calling the func function will be processed and
        the result of the function execution will be the value set in set_error_value.
    set_error_value: Any, default None
        The value to be returned in case of exception handling. Only matters if error_behavior='coerce'.
        if None, the exception traceback will be returned.
    executor: str, default 'processes'
        Can be 'processes' or 'threads'
        - if 'processes', uses processes pool
        - if 'threads', use threads pool
    need_serialize: bool, default False
        If True  function will be serialized with dill library.
    used_add_progress_decorator: bool, default False
    return_failed_tasks: bool, default False
        If True, the function will return a tuple of two lists: the first list will contain the results of the
        function execution,  the second list will contain the tasks that caused the exception.
    retries: int, default 0
        Number of extra attempts for tasks that raised an exception (including process_timeout).
        Failed tasks are re-submitted up to `retries` times. Not compatible with
        used_add_progress_decorator=True.
    Returns
    -------
    result: list

    """

    _validate_args(error_behavior, tasks, total, executor)
    func = _func_prepare(func, process_timeout, need_serialize)
    if retries:
        if used_add_progress_decorator:
            raise ValueError('retries is not compatible with used_add_progress_decorator=True')

        def run_once(subset, desc):
            return _do_parallel(func, 'imap', subset, initializer, initargs, n_cpu, chunk_size, context,
                                len(subset), disable, 'coerce', None, executor, need_serialize,
                                maxtasksperchild, False, False, desc=desc)

        return _run_with_retries(run_once, tasks, retries, error_behavior, set_error_value, return_failed_tasks)
    result = _do_parallel(func, 'imap', tasks, initializer, initargs, n_cpu, chunk_size, context, total, disable,
                          error_behavior, set_error_value, executor, need_serialize, maxtasksperchild,
                          used_add_progress_decorator, return_failed_tasks
                          )
    return result


def progress_imapu(func, tasks, initializer=None, initargs=(), n_cpu=None, chunk_size=1, context=None, total=None,
                   disable=False, process_timeout=None, error_behavior='raise', set_error_value=None,
                   executor='processes', need_serialize=False, maxtasksperchild=None, used_add_progress_decorator=False,
                   return_failed_tasks=False,
                   ):
    """
    An extension of the imap_unordered method of the multiprocessing.Poll class that allows you to display the progress
    of tasks, handle exceptions, and set a timeout for the function to execute.

    Parameters:
    ----------
    func: сallable
        A function that will be applied element by element to the tasks
         iterable.
    tasks: Iterable
        The func function will be applied to the task elements.
    initializer: сallable or None, default None
    initargs: tuple
    n_cpu: int, or None, default None
        number of workers, if None n_cpu = multiprocessing.cpu_count().
    chunk_size: int or None, default None
    context: str or None, default None
        Can be 'fork', 'spawn' or 'forkserver'.
    total: int or None, default None
        The number of elements in tasks. Must be specified if task is iterator.
    disable: bool, default False
        if True don't show progress bar.
    process_timeout: float or None, default None
        If not None, a TimeoutError exception will be raised if the function execution time exceeds
        the specified value in seconds.
    error_behavior: str, default 'raise'
        Can be 'raise' or 'coerce'
        - If 'raise', then the exception that occurs when calling the func function will be raised.
        - If 'coerce', then the exception that occurs when calling the func function will be processed and
        the result of the function execution will be the value set in set_error_value.
    set_error_value: Any, default None
        The value to be returned in case of exception handling. Only matters if error_behavior='coerce'.
        if None, the exception traceback will be returned.
    executor: str, default 'processes'
        Can be 'processes' or 'threads'
        - if 'processes', uses processes pool
        - if 'threads', use threads pool
    need_serialize: bool, default False
        If True  function will be serialized with dill library.
    used_add_progress_decorator: bool, default False
    return_failed_tasks: bool, default False
        If True, the function will return a tuple of two lists: the first list will contain the results of the
        function execution,  the second list will contain the tasks that caused the exception.
    Returns
    -------
    result: list

    """

    _validate_args(error_behavior, tasks, total, executor)
    func = _func_prepare(func, process_timeout, need_serialize)
    result = _do_parallel(func, 'imap_unordered', tasks, initializer, initargs, n_cpu, chunk_size, context, total,
                          disable, error_behavior, set_error_value, executor, need_serialize, maxtasksperchild,
                          used_add_progress_decorator, return_failed_tasks
                          )
    return result


class Parallel:
    """A reusable ("warm") pool of workers with progress bars.

    Creating a process pool (and a multiprocessing.Manager) is expensive: it spawns
    processes on every call. ``Parallel`` creates them once and reuses them across many
    ``map``/``starmap``/``imap``/``imapu`` calls, which removes most of the per-call
    overhead when you run many parallel operations in a row.

    Example
    -------
    >>> with Parallel(n_cpu=8) as p:
    ...     a = p.map(f, tasks1)
    ...     b = p.map(g, tasks2)   # no new workers are spawned

    Notes
    -----
    - Only the process pool is supported (no thread executor and no add_progress decorator
      path, since those rely on a per-call worker queue set at pool creation time).
    - Call ``close()`` when done, or use the context manager, to release the workers and the
      manager process.
    """

    def __init__(self, n_cpu=None, initializer=None, initargs=(), context=None, maxtasksperchild=None):
        self._closed = False
        self._manager = mp.Manager()
        self._pool = mp.get_context(context).Pool(processes=n_cpu, initializer=initializer,
                                                  initargs=initargs, maxtasksperchild=maxtasksperchild)

    def _check_open(self):
        if self._closed:
            raise RuntimeError('This Parallel pool has been closed.')

    def _run(self, pool_type, func, tasks, chunk_size, total, disable, process_timeout,
             error_behavior, set_error_value, need_serialize, return_failed_tasks, timeout, retries, starmap=False):
        self._check_open()
        _validate_args(error_behavior, tasks, total, 'processes')
        if starmap:
            func = partial(func_args_unpack, func)
        func = _func_prepare(func, process_timeout, need_serialize)
        if retries:
            if pool_type == 'imap_unordered':
                raise ValueError('retries is not supported for imapu (imap_unordered) because results are '
                                 'not positionally aligned with the input tasks')

            def run_once(subset, desc):
                return _run_once(self._pool, self._manager, pool_type, func, subset, chunk_size, len(subset),
                                 disable, 'coerce', None, need_serialize, False, timeout, desc=desc)

            return _run_with_retries(run_once, tasks, retries, error_behavior, set_error_value, return_failed_tasks)
        return _run_once(self._pool, self._manager, pool_type, func, tasks, chunk_size, total, disable,
                         error_behavior, set_error_value, need_serialize, return_failed_tasks, timeout)

    def map(self, func, tasks, chunk_size=None, total=None, disable=False, process_timeout=None,
            error_behavior='raise', set_error_value=None, need_serialize=False,
            return_failed_tasks=False, timeout=None, retries=0):
        return self._run('map', func, tasks, chunk_size, total, disable, process_timeout, error_behavior,
                         set_error_value, need_serialize, return_failed_tasks, timeout, retries)

    def starmap(self, func, tasks, chunk_size=None, total=None, disable=False, process_timeout=None,
                error_behavior='raise', set_error_value=None, need_serialize=False,
                return_failed_tasks=False, timeout=None, retries=0):
        return self._run('map', func, tasks, chunk_size, total, disable, process_timeout, error_behavior,
                         set_error_value, need_serialize, return_failed_tasks, timeout, retries, starmap=True)

    def imap(self, func, tasks, chunk_size=1, total=None, disable=False, process_timeout=None,
             error_behavior='raise', set_error_value=None, need_serialize=False,
             return_failed_tasks=False, retries=0):
        return self._run('imap', func, tasks, chunk_size, total, disable, process_timeout, error_behavior,
                         set_error_value, need_serialize, return_failed_tasks, None, retries)

    def imapu(self, func, tasks, chunk_size=1, total=None, disable=False, process_timeout=None,
              error_behavior='raise', set_error_value=None, need_serialize=False,
              return_failed_tasks=False, retries=0):
        return self._run('imap_unordered', func, tasks, chunk_size, total, disable, process_timeout, error_behavior,
                         set_error_value, need_serialize, return_failed_tasks, None, retries)

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._pool.close()
        self._pool.join()
        self._manager.shutdown()

    def terminate(self):
        if self._closed:
            return
        self._closed = True
        self._pool.terminate()
        self._pool.join()
        self._manager.shutdown()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.terminate()
        else:
            self.close()
        return False
