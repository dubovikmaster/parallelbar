from functools import partial
from collections import abc
import multiprocessing as mp
from threading import Thread
import time
from itertools import count

from tqdm.auto import tqdm

from .tools import (
    WORKER_QUEUE,
    get_len,
    func_args_unpack,
)
from .wrappers import stopit_after_timeout

try:
    import dill
except ImportError:
    dill = None


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


def _process_status(bar_size, worker_queue):
    bar = ProgressBar(total=bar_size, desc='DONE')
    error_bar_parameters = dict(total=bar_size, position=1, desc='ERROR', colour='red')
    error_bar = {}
    error_bar_n = 0
    while True:
        flag, upd_value = worker_queue.get()
        if flag is None:
            if error_bar:
                error_bar_n = error_bar['bar'].n
                error_bar['bar'].close()
            if bar.n < bar_size and upd_value != -1:
                bar.update(bar_size - bar.n - error_bar_n)
            bar.close()
            break
        if flag:
            _update_error_bar(error_bar, error_bar_parameters)
        else:
            bar.update(upd_value)


def _bar_size(chunk_size, len_tasks, n_cpu):
    bar_count, extra = divmod(len_tasks, chunk_size)
    if bar_count < n_cpu:
        bar_size = chunk_size
    else:
        bar_size, extra = divmod(len_tasks, n_cpu * chunk_size)
        bar_size = bar_size * chunk_size
        if extra:
            bar_size += chunk_size
    return bar_size


class ProgressStatus:
    def __init__(self):
        self.next_update = 1
        self.last_update_t = time.perf_counter()
        self.last_update_val = 0


def func_wrapped(cnt, state, func, error_handling, set_error_value, worker_queue, task):
    try:
        result = func(task)
    except BaseException as e:
        if error_handling == 'raise':
            worker_queue.put((1, 1))
            worker_queue.put((None, -1))
            raise
        else:
            worker_queue.put((1, 1))
            _ = next(cnt)
            if set_error_value is None:
                return e
        return set_error_value
    else:
        updated = next(cnt)
        if updated == state.next_update:
            time_now = time.perf_counter()

            delta_t = time_now - state.last_update_t
            delta_i = updated - state.last_update_val

            state.next_update += max(int((delta_i / delta_t) * .25), 1)
            state.last_update_val = updated
            state.last_update_t = time_now
            worker_queue.put_nowait((0, delta_i))

    return result


def _deserialize(func, task):
    return dill.loads(func)(task)


def _do_parallel(func, pool_type, tasks, initializer, initargs, n_cpu, chunk_size, context, total, disable,
                 error_behavior, set_error_value, executor, need_serialize, maxtasksperchild, used_decorators,
                 ):
    raised_exception = False
    len_tasks = get_len(tasks, total)
    if not n_cpu:
        n_cpu = mp.cpu_count()
    if need_serialize:
        func = partial(_deserialize, func)
    if not used_decorators:
        state = ProgressStatus()
        cnt = count(1)
        func = partial(func_wrapped, cnt, state, func, need_serialize, error_behavior, set_error_value, WORKER_QUEUE)
    bar_size = len_tasks
    thread = Thread(target=_process_status, args=(bar_size, WORKER_QUEUE), daemon=True)
    try:
        if not disable:
            thread.start()
        if executor == 'threads':
            exc_pool = mp.pool.ThreadPool(n_cpu, initializer=initializer, initargs=initargs)
        else:
            exc_pool = mp.get_context(context).Pool(maxtasksperchild=maxtasksperchild,
                                                    processes=n_cpu, initializer=initializer, initargs=initargs)
        with exc_pool as p:
            if pool_type == 'map':
                result = p.map(func, tasks, chunksize=chunk_size)
            else:
                result = list()
                method = getattr(p, pool_type)
                iter_result = method(func, tasks, chunksize=chunk_size)
                while 1:
                    try:
                        result.append(next(iter_result))
                    except StopIteration:
                        break
    except Exception as e:
        raised_exception = e
    finally:
        # stop thread
        while thread.is_alive():
            if raised_exception:
                WORKER_QUEUE.put((None, -1))
            else:
                WORKER_QUEUE.put((None, None))
        # clear queue
        while WORKER_QUEUE.qsize():
            WORKER_QUEUE.get()
        if raised_exception:
            raise raised_exception
    return result


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
                 executor='processes', need_serialize=False, maxtasksperchild=None, used_decorators=False
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
    Returns
    -------
    result: list

    """
    _validate_args(error_behavior, tasks, total, executor)
    # if not used_decorators:
    func = _func_prepare(func, process_timeout, need_serialize)
    result = _do_parallel(func, 'map', tasks, initializer, initargs, n_cpu, chunk_size, context, total, disable,
                          error_behavior, set_error_value, executor, need_serialize, maxtasksperchild, used_decorators,
                          )
    return result


def progress_starmap(func, tasks, initializer=None, initargs=(), n_cpu=None, chunk_size=None, context=None, total=None,
                     disable=False, process_timeout=None, error_behavior='raise', set_error_value=None,
                     executor='processes', need_serialize=False, maxtasksperchild=None
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
    Returns
    -------
    result: list

    """
    _validate_args(error_behavior, tasks, total, executor)
    func = partial(func_args_unpack, func)
    func = _func_prepare(func, process_timeout, need_serialize)
    result = _do_parallel(func, 'map', tasks, initializer, initargs, n_cpu, chunk_size, context, total, disable,
                          error_behavior, set_error_value, executor, need_serialize, maxtasksperchild
                          )
    return result


def progress_imap(func, tasks, initializer=None, initargs=(), n_cpu=None, chunk_size=1, context=None, total=None,
                  disable=False, process_timeout=None, error_behavior='raise', set_error_value=None,
                  executor='processes', need_serialize=False, maxtasksperchild=None
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
    Returns
    -------
    result: list

    """

    _validate_args(error_behavior, tasks, total, executor)
    func = _func_prepare(func, process_timeout, need_serialize)
    result = _do_parallel(func, 'imap', tasks, initializer, initargs, n_cpu, chunk_size, context, total,
                          disable, error_behavior, set_error_value, executor, need_serialize,
                          maxtasksperchild
                          )
    return result


def progress_imapu(func, tasks, initializer=None, initargs=(), n_cpu=None, chunk_size=1, context=None, total=None,
                   disable=False, process_timeout=None, error_behavior='raise', set_error_value=None,
                   executor='processes', need_serialize=False, maxtasksperchild=None
                   ):
    """
    An extension of the imap_unordered method of the multiprocessing.Poll class that allows you to display the progress of tasks,
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
    Returns
    -------
    result: list

    """

    _validate_args(error_behavior, tasks, total, executor)
    func = _func_prepare(func, process_timeout, need_serialize)
    result = _do_parallel(func, 'imap_unordered', tasks, initializer, initargs, n_cpu, chunk_size, context, total,
                          disable, error_behavior, set_error_value, executor, need_serialize, maxtasksperchild
                          )
    return result
