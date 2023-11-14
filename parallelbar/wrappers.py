import threading
import _thread as thread
import platform
import os
import signal
from functools import wraps
import time
from itertools import count

try:
    import dill
except ImportError:
    dill = None

__all__ = ['stopit_after_timeout', 'add_progress']


def stop_function():
    if platform.system() == 'Windows':
        thread.interrupt_main()
    else:
        os.kill(os.getpid(), signal.SIGINT)


def stopit_after_timeout(s, raise_exception=True):
    def actual_decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            timer = threading.Timer(s, stop_function)
            try:
                timer.start()
                result = func(*args, **kwargs)
            except KeyboardInterrupt:
                msg = f'function took longer than {s} s.'
                if raise_exception:
                    raise TimeoutError(msg)
                result = msg
            finally:
                timer.cancel()
            return result

        return wrapper

    return actual_decorator


class ProgressStatus:
    def __init__(self):
        self.next_update = 1
        self.last_update_t = time.perf_counter()
        self.last_update_val = 0


def _make_args(*args, **kwargs):
    if kwargs:
        return args + (kwargs,)
    if len(args) == 1:
        return args[0]
    return args


def init_worker(worker_queue, init_progress, init_progress_args):
    global _WORKER_QUEUE
    _WORKER_QUEUE = worker_queue
    if init_progress is not None:
        init_progress(*init_progress_args)


def add_progress(error_handling='raise', set_error_value=None, timeout=None):
    state = ProgressStatus()
    cnt = count(1)

    def actual_decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                if timeout is None:
                    result = func(*args, **kwargs)
                else:
                    result = stopit_after_timeout(timeout)(func)(*args, **kwargs)
            except Exception as e:
                if error_handling == 'raise':
                    _WORKER_QUEUE.put((None, -1))
                    raise
                else:
                    _WORKER_QUEUE.put((1, _make_args(*args, **kwargs)))
                    if set_error_value is None:
                        return e
                return set_error_value
            else:
                updated = next(cnt)
                time_now = time.perf_counter()
                delta_t = time_now - state.last_update_t
                if updated == state.next_update or delta_t > .25:
                    delta_i = updated - state.last_update_val

                    state.next_update += max(int((delta_i / delta_t) * .25), 1)
                    state.last_update_val = updated
                    state.last_update_t = time_now
                    _WORKER_QUEUE.put_nowait((0, delta_i))
            return result

        return wrapper

    return actual_decorator
