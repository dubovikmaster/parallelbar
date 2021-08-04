import os
from functools import partial

import multiprocessing as mp
from threading import Thread

from tqdm.auto import tqdm


def func_args_unpack(func, args):
    return func(*args)


def _process(func, pipe, task):
    result = func(task)
    pipe.send([os.getpid()])
    return result


def _core_process_status(pipe, bar_size):
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


def _process_status(pipe, bar_size):
    pbur = tqdm(total=bar_size)
    while True:
        result = pipe.recv()
        if not result:
            break
        pbur.update(1)


def _bar_size(chunk_size, len_tasks):
    bar_count, extra = divmod(len_tasks, chunk_size)
    if bar_count < mp.cpu_count():
        bar_size = chunk_size
    else:
        bar_size, extra = divmod(len_tasks, mp.cpu_count() * chunk_size)
        bar_size = bar_size * chunk_size
        if extra:
            bar_size += chunk_size
    return bar_size


def progress_map(func, tasks, chunk_size=None, core_progress=True):
    parent, child = mp.Pipe()
    if not chunk_size:
        chunk_size, extra = divmod(len(tasks), mp.cpu_count() * 4)
        if extra:
            chunk_size += 1
    if core_progress:
        bar_size = _bar_size(chunk_size, len(tasks))
        thread = Thread(target=_core_process_status, args=(parent, bar_size))
    else:
        bar_size = len(tasks)
        thread = Thread(target=_process_status, args=(parent, bar_size))
    thread.start()
    with mp.Pool() as p:
        target = partial(_process, func, child)
        result = p.map(target, tasks, chunksize=chunk_size)
        child.send(None)
        thread.join()
    return result
