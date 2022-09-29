import os
from functools import partial
from collections import abc
import multiprocessing as mp
from threading import Thread
from tqdm.auto import tqdm
from .tools import get_len
from .tools import _wrapped_func


class ProgressBar(tqdm):

    def __init__(self, *args, step=1, **kwargs):
        super().__init__(*args, **kwargs)
        self.step = step
        self._value = 0

    def _update(self):
        if self._value % self.step == 0 and self._value < self.total:
            super().update(self.step)
        elif self._value == self.total:
            extra = self._value % self.step
            if extra:
                super().update(extra)
            else:
                super().update(self.step)
        elif self._value > self.total:
            super().update(1)

    def update(self):
        self._value += 1
        self._update()

    def close(self):
        super().close()
        if hasattr(self, 'disp'):
            if self.total and self._value < self.total:
                self.disp(bar_style='warning')


def _update_error_bar(bar_dict, bar_parameters):
    try:
        bar_dict['bar'].update()
    except KeyError:
        bar_dict['bar'] = ProgressBar(**bar_parameters)
        bar_dict['bar'].update()


def _process_status(bar_size, bar_step, disable, q):
    bar = ProgressBar(step=bar_step, total=bar_size, disable=disable, desc='DONE')
    error_bar_parameters = dict(total=bar_size, disable=disable, position=1, desc='ERROR', colour='red')
    error_bar = {}
    while True:
        result = q.get()
        if not result:
            bar.close()
            if error_bar:
                error_bar['bar'].close()
            break
        if result == 'e':
            _update_error_bar(error_bar, error_bar_parameters)
        else:
            bar.update()


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


def func_wrapped(func, error_handling, set_error_value, q, task):
    try:
        result = func(task)
        q.put(os.getpid())
    except Exception as e:
        if error_handling == 'raise':
            q.put('e')
            q.put(None)
            raise
        else:
            q.put('e')
            if set_error_value is None:
                return e
            return set_error_value
    else:
        return result


def _do_parallel(func, pool_type, tasks, initializer, initargs, n_cpu, chunk_size, context, total, bar_step, disable,
                 error_behavior, set_error_value, executor
                 ):
    q = mp.Manager().Queue()
    func_new = partial(func_wrapped, func, error_behavior, set_error_value, q)
    len_tasks = get_len(tasks, total)
    if not n_cpu:
        n_cpu = mp.cpu_count()
    if not chunk_size:
        chunk_size, extra = divmod(len_tasks, n_cpu * 4)
        if extra:
            chunk_size += 1
    bar_size = len_tasks
    thread = Thread(target=_process_status, args=(bar_size, bar_step, disable, q))
    thread.start()
    if executor == 'threads':
        exc_pool = mp.pool.ThreadPool(n_cpu, initializer=initializer, initargs=initargs)
    else:
        exc_pool = mp.get_context(context).Pool(n_cpu, initializer=initializer, initargs=initargs)
    with exc_pool as p:
        if pool_type == 'map':
            result = p.map(func_new, tasks, chunksize=chunk_size)
        else:
            result = list()
            method = getattr(p, pool_type)
            iter_result = method(func_new, tasks, chunksize=chunk_size)
            while 1:
                try:
                    result.append(next(iter_result))
                except StopIteration:
                    break
    q.put(None)
    thread.join()
    return result


def progress_map(func, tasks, initializer=None, initargs=(), n_cpu=None, chunk_size=None,
                 context=None, total=None, bar_step=1, disable=False, process_timeout=None, error_behavior='raise',
                 set_error_value=None, executor='processes'
                 ):
    if error_behavior not in ['raise', 'coerce']:
        raise ValueError(
            'Invalid error_handling value specified. Must be one of the values: "raise", "coerce"')
    if process_timeout:
        func = partial(_wrapped_func, func, process_timeout, True)
    result = _do_parallel(func, 'map', tasks, initializer, initargs, n_cpu, chunk_size, context, total,
                          bar_step, disable, error_behavior, set_error_value, executor)
    return result


def progress_imap(func, tasks, initializer=None, initargs=(), n_cpu=None, chunk_size=1,
                  context=None, total=None, bar_step=1, disable=False, process_timeout=None, error_behavior='raise',
                  set_error_value=None, executor='processes'
                  ):
    if error_behavior not in ['raise', 'coerce']:
        raise ValueError(
            'Invalid error_handling value specified. Must be one of the values: "raise", "coerce"')
    if isinstance(tasks, abc.Iterator) and not total:
        raise ValueError('If the tasks are an iterator, the total parameter must be specified')
    if process_timeout:
        func = partial(_wrapped_func, func, process_timeout, True)
    result = _do_parallel(func, 'imap', tasks, initializer, initargs, n_cpu, chunk_size, context, total,
                          bar_step, disable, error_behavior, set_error_value, executor)
    return result


def progress_imapu(func, tasks, initializer=None, initargs=(), n_cpu=None, chunk_size=1,
                   context=None, total=None, bar_step=1, disable=False, process_timeout=None, error_behavior='raise',
                   set_error_value=None, executor='processes'
                   ):
    if error_behavior not in ['raise', 'coerce']:
        raise ValueError(
            'Invalid error_handling value specified. Must be one of the values: "raise", "coerce"')
    if isinstance(tasks, abc.Iterator) and not total:
        raise ValueError('If the tasks are an iterator, the total parameter must be specified')
    if process_timeout:
        func = partial(_wrapped_func, func, process_timeout, True)
    result = _do_parallel(func, 'imap_unordered', tasks, initializer, initargs, n_cpu, chunk_size,
                          context, total, bar_step, disable, error_behavior, set_error_value, executor)
    return result

