import os
from functools import partial

import multiprocessing as mp
from threading import Thread

from tqdm.auto import tqdm
from .tools import get_len


def _process(func, pipe, task):
    result = func(task)
    pipe.send([os.getpid()])
    return result


def _core_process_status(bar_size, pipe):
    pid_dict = dict()
    i = 0
    while True:
        result = pipe.recv()
        if not result:
            break
        try:
            pid_dict[result[0]].update(1)
        except KeyError:
            i += 1
            position = len(pid_dict)
            pid_dict[result[0]] = tqdm(total=bar_size, position=position, desc=f'Core {i}')
            pid_dict[result[0]].update(1)


def _process_status(bar_size, pipe):
    pbur = tqdm(total=bar_size)
    while True:
        result = pipe.recv()
        if not result:
            break
        pbur.update(1)


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


def _do_parallel(func, pool_type, tasks, n_cpu, chunk_size, core_progress, context, total):
    parent, child = mp.Pipe()
    len_tasks = get_len(tasks, total)
    if not n_cpu:
        n_cpu = mp.cpu_count()
    if not chunk_size:
        chunk_size, extra = divmod(len_tasks, n_cpu * 4)
        if extra:
            chunk_size += 1
    if core_progress:
        bar_size = _bar_size(chunk_size, len_tasks, n_cpu)
        thread = Thread(target=_core_process_status, args=(bar_size, parent))
    else:
        bar_size = len_tasks
        thread = Thread(target=_process_status, args=(bar_size, parent))
    thread.start()
    with mp.get_context(context).Pool(n_cpu) as p:
        target = partial(_process, func, child)
        method = getattr(p, pool_type)
        if pool_type == 'map':
            result = method(target, tasks, chunksize=chunk_size)
        else:
            result = list(method(target, tasks, chunksize=chunk_size))
        child.send(None)
        thread.join()
    return result


def progress_map(func, tasks, n_cpu=None, chunk_size=None, core_progress=False, context='spawn', total=None):
    result = _do_parallel(func, 'map', tasks, n_cpu, chunk_size, core_progress, context, total)
    return result


def progress_imap(func, tasks, n_cpu=None, chunk_size=1, core_progress=False, context='spawn', total=None):
    result = _do_parallel(func, 'imap', tasks, n_cpu, chunk_size, core_progress, context, total)
    return result


def progress_imapu(func, tasks, n_cpu=None, chunk_size=1, core_progress=False, context='spawn', total=None):
    result = _do_parallel(func, 'imap_unordered', tasks, n_cpu, chunk_size, core_progress, context, total)
    return result

