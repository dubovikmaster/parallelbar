import os
from functools import partial
from collections import abc
import multiprocessing as mp
from threading import Thread

from pebble import ProcessPool
from pebble import ProcessExpired

from concurrent.futures import TimeoutError

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


def _process(func, q, task):
    result = func(task)
    q.put(os.getpid())
    return result


def _core_process_status(bar_size, bar_step, disable, q):
    pid_dict = dict()
    i = 0
    while True:
        result = q.get()
        if not result:
            for val in pid_dict.values():
                val.close()
            break
        try:
            pid_dict[result].update()
        except KeyError:
            i += 1
            position = len(pid_dict)
            pid_dict[result] = ProgressBar(step=bar_step, total=bar_size, position=position, desc=f'Core {i}',
                                           disable=disable)
            pid_dict[result].update()


def _process_status(bar_size, bar_step, disable, q):
    bar = ProgressBar(step=bar_step, total=bar_size, disable=disable, desc='DONE')
    while True:
        result = q.get()
        if not result:
            bar.close()
            break

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


def _update_error_bar(bar_dict, bar_parameters):
    try:
        bar_dict['bar'].update()
    except KeyError:
        bar_dict['bar'] = ProgressBar(**bar_parameters)
        bar_dict['bar'].update()


def _error_behavior(error_handling, msgs, result, set_error_value, q):
    if error_handling == 'raise':
        q.put(None)
        raise
    elif error_handling == 'ignore':
        pass
    elif error_handling == 'coerce':
        if set_error_value is None:
            set_error_value = msgs
        result.append(set_error_value)
    else:
        raise ValueError(
            'Invalid error_handling value specified. Must be one of the values: "raise", "ignore", "coerce"')


def _do_parallel(func, pool_type, tasks, initializer, initargs, n_cpu, chunk_size, core_progress,
                 context, total, bar_step, disable, process_timeout, error_behavior, set_error_value,
                 ):
    q = mp.Manager().Queue()
    len_tasks = get_len(tasks, total)
    if not n_cpu:
        n_cpu = mp.cpu_count()
    if not chunk_size:
        chunk_size, extra = divmod(len_tasks, n_cpu * 4)
        if extra:
            chunk_size += 1
    if core_progress:
        bar_size = _bar_size(chunk_size, len_tasks, n_cpu)
        thread = Thread(target=_core_process_status, args=(bar_size, bar_step, disable, q), daemon=True)
    else:
        bar_size = len_tasks
        thread = Thread(target=_process_status, args=(bar_size, bar_step, disable, q), daemon=True)
    thread.start()
    target = partial(_process, func, q)
    bar_parameters = dict(total=len_tasks, disable=disable, position=1, desc='ERROR', colour='red')
    error_bar = {}
    result = list()
    if pool_type == 'map':
        with ProcessPool(initializer=initializer, initargs=initargs, max_workers=n_cpu,
                         context=mp.get_context(context)) as pool:
            future = pool.map(target, tasks, timeout=process_timeout, chunksize=chunk_size)
            iterator = future.result()
            while True:
                try:
                    result.append(next(iterator))
                except StopIteration:
                    break
                except TimeoutError:
                    _update_error_bar(error_bar, bar_parameters)
                    _error_behavior(error_behavior,
                                    f"function \"{func.__name__}\" took longer than {process_timeout} s.", result,
                                    set_error_value, q)
                except ProcessExpired as e:
                    _update_error_bar(error_bar, bar_parameters)
                    _error_behavior(error_behavior, f" {e}. Exit code: {e.exitcode}", result, set_error_value, q)
                except Exception as e:
                    _update_error_bar(error_bar, bar_parameters)
                    _error_behavior(error_behavior, e, result, set_error_value, q)
    else:
        with mp.get_context(context).Pool(n_cpu, initializer=initializer, initargs=initargs) as p:
            result = list()
            method = getattr(p, pool_type)
            iter_result = method(target, tasks, chunksize=chunk_size)
            while 1:
                try:
                    result.append(next(iter_result))
                except StopIteration:
                    break
                except Exception as e:
                    _update_error_bar(error_bar, bar_parameters)
                    _error_behavior(error_behavior, e, result, set_error_value, q)
    if error_bar:
        error_bar['bar'].close()
    q.put(None)
    thread.join()
    return result


def progress_map(func, tasks, initializer=None, initargs=(), n_cpu=None, chunk_size=None, core_progress=False,
                 context=None, total=None, bar_step=1, disable=False, process_timeout=None, error_behavior='coerce',
                 set_error_value=None,
                 ):
    result = _do_parallel(func, 'map', tasks, initializer, initargs, n_cpu, chunk_size, core_progress, context, total,
                          bar_step, disable, process_timeout, error_behavior, set_error_value)
    return result


def progress_imap(func, tasks, initializer=None, initargs=(), n_cpu=None, chunk_size=1, core_progress=False,
                  context=None, total=None, bar_step=1, disable=False, process_timeout=None, error_behavior='coerce',
                  set_error_value=None,
                  ):
    if process_timeout and chunk_size != 1:
        raise ValueError('the process_timeout can only be used if chunk_size=1')
    if isinstance(tasks, abc.Iterator) and not total:
        raise ValueError('If the tasks are an iterator, the total parameter must be specified')
    if process_timeout:
        func = partial(_wrapped_func, func, process_timeout, True)
    result = _do_parallel(func, 'imap', tasks, initializer, initargs, n_cpu, chunk_size, core_progress, context, total,
                          bar_step, disable, None, error_behavior, set_error_value)
    return result


def progress_imapu(func, tasks, initializer=None, initargs=(), n_cpu=None, chunk_size=1, core_progress=False,
                   context=None, total=None, bar_step=1, disable=False, process_timeout=None, error_behavior='coerce',
                   set_error_value=None,
                   ):
    if process_timeout and chunk_size != 1:
        raise ValueError('the process_timeout can only be used if chunk_size=1')
    if isinstance(tasks, abc.Iterator) and not total:
        raise ValueError('If the tasks are an iterator, the total parameter must be specified')
    if process_timeout:
        func = partial(_wrapped_func, func, process_timeout, True)
    result = _do_parallel(func, 'imap_unordered', tasks, initializer, initargs, n_cpu, chunk_size, core_progress,
                          context, total, bar_step, disable, None, error_behavior, set_error_value)
    return result
