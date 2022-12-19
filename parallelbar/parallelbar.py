from functools import partial
from collections import abc
import multiprocessing as mp
from threading import Thread
from tqdm.auto import tqdm
from .tools import get_len
from .tools import _wrapped_func
import time
from itertools import count

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


def _process_status(bar_size, disable, worker_queue):
    bar = ProgressBar(total=bar_size, disable=disable, desc='DONE')
    error_bar_parameters = dict(total=bar_size, disable=disable, position=1, desc='ERROR', colour='red')
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
        self.last_update_t = time.monotonic()
        self.last_update_val = 0


def func_wrapped(cnt, state, func, need_serialize, error_handling, set_error_value, worker_queue, total, task):
    try:
        if need_serialize:
            func = dill.loads(func)
        result = func(task)
        updated = next(cnt)
        if updated == state.next_update:
            time_now = time.monotonic()

            delta_t = time_now - state.last_update_t
            delta_i = updated - state.last_update_val

            state.next_update += max(int((delta_i / delta_t) * .25), 1)
            state.last_update_val = updated
            state.last_update_t = time_now
            worker_queue.put_nowait((0, delta_i))
        elif updated == total:
            worker_queue.put_nowait((0, updated - state.last_update_val))
    except Exception as e:
        if error_handling == 'raise':
            worker_queue.put((1, 1))
            worker_queue.put((None, None))
            raise
        else:
            worker_queue.put((1, 1))
            if set_error_value is None:
                return e
            return set_error_value
    else:
        return result


def _do_parallel(func, pool_type, tasks, initializer, initargs, n_cpu, chunk_size, context, total, bar_step, disable,
                 error_behavior, set_error_value, executor, need_serialize
                 ):
    worker_queue = mp.Manager().Queue()
    len_tasks = get_len(tasks, total)
    if not n_cpu:
        n_cpu = mp.cpu_count()
    if not chunk_size:
        chunk_size, extra = divmod(len_tasks, n_cpu * 4)
        if extra:
            chunk_size += 1
    state = ProgressStatus()
    cnt = count(1)
    func_new = partial(func_wrapped, cnt, state, func, need_serialize, error_behavior, set_error_value, worker_queue,
                       chunk_size)
    bar_size = len_tasks
    thread = Thread(target=_process_status, args=(bar_size, disable, worker_queue))
    thread.start()
    try:
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
    except Exception:
        worker_queue.put((None, -1))
        raise
    else:
        worker_queue.put((None, None))
    return result


def _func_prepare(func, process_timeout, need_serialize):
    if process_timeout:
        func = partial(_wrapped_func, func, process_timeout, True)
    if need_serialize:
        if dill is None:
            raise ModuleNotFoundError('You must install the dill package to serialize functions.')
        func = dill.dumps(func)
    return func


def progress_map(func, tasks, initializer=None, initargs=(), n_cpu=None, chunk_size=None,
                 context=None, total=None, bar_step=1, disable=False, process_timeout=None, error_behavior='raise',
                 set_error_value=None, executor='processes', need_serialize=False
                 ):
    if error_behavior not in ['raise', 'coerce']:
        raise ValueError(
            'Invalid error_handling value specified. Must be one of the values: "raise", "coerce"')
    func = _func_prepare(func, process_timeout, need_serialize)
    result = _do_parallel(func, 'map', tasks, initializer, initargs, n_cpu, chunk_size, context, total,
                          bar_step, disable, error_behavior, set_error_value, executor, need_serialize)
    return result


def progress_imap(func, tasks, initializer=None, initargs=(), n_cpu=None, chunk_size=1,
                  context=None, total=None, bar_step=1, disable=False, process_timeout=None, error_behavior='raise',
                  set_error_value=None, executor='processes', need_serialize=False
                  ):
    if error_behavior not in ['raise', 'coerce']:
        raise ValueError(
            'Invalid error_handling value specified. Must be one of the values: "raise", "coerce"')
    if isinstance(tasks, abc.Iterator) and not total:
        raise ValueError('If the tasks are an iterator, the total parameter must be specified')
    func = _func_prepare(func, process_timeout, need_serialize)
    result = _do_parallel(func, 'imap', tasks, initializer, initargs, n_cpu, chunk_size, context, total,
                          bar_step, disable, error_behavior, set_error_value, executor, need_serialize)
    return result


def progress_imapu(func, tasks, initializer=None, initargs=(), n_cpu=None, chunk_size=1,
                   context=None, total=None, bar_step=1, disable=False, process_timeout=None, error_behavior='raise',
                   set_error_value=None, executor='processes', need_serialize=False
                   ):
    if error_behavior not in ['raise', 'coerce']:
        raise ValueError(
            'Invalid error_handling value specified. Must be one of the values: "raise", "coerce"')
    if isinstance(tasks, abc.Iterator) and not total:
        raise ValueError('If the tasks are an iterator, the total parameter must be specified')
    func = _func_prepare(func, process_timeout, need_serialize)
    result = _do_parallel(func, 'imap_unordered', tasks, initializer, initargs, n_cpu, chunk_size,
                          context, total, bar_step, disable, error_behavior, set_error_value, executor, need_serialize)
    return result
