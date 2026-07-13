import threading
import _thread as thread
import platform
import os
import signal
import traceback
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


def add_progress(error_handling='raise', set_error_value=None, timeout=None, desc=None, total=None,
                 separate_bar=False):
    """
    Decorator that reports the progress of a function executed inside a parallelbar worker.

    Parameters
    ----------
    error_handling: str, default 'raise'
        'raise' or 'coerce', same semantics as in progress_map.
    set_error_value: Any, default None
        Value returned on error when error_handling='coerce'.
    timeout: float or None, default None
        Per-call timeout in seconds.
    desc: str or None, default None
        Label of the separate progress bar. If None, func.__name__ is used.
        Only matters when separate_bar=True.
    total: int or None, default None
        Total number of calls of the decorated function across all tasks. Used as the
        total of the separate bar. If None, the bar is shown without a percentage.
        Only matters when separate_bar=True.
    separate_bar: bool, default False
        If True, a dedicated progress bar (keyed by desc/func.__name__) is displayed for
        this function in addition to the aggregate 'DONE' bar. If False, the behavior is
        unchanged: updates only feed the aggregate 'DONE' bar.
    """
    state = ProgressStatus()
    cnt = count(1)

    def actual_decorator(func):
        name = desc if desc is not None else func.__name__
        meta = (name, total) if separate_bar else None

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
                    if meta is None:
                        _WORKER_QUEUE.put((1, _make_args(*args, **kwargs)))
                    else:
                        _WORKER_QUEUE.put((1, _make_args(*args, **kwargs), meta))
                    if set_error_value is None:
                        try:
                            e.traceback = traceback.format_exc()
                        except Exception:
                            pass
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
                    if meta is None:
                        _WORKER_QUEUE.put_nowait((0, delta_i))
                    else:
                        _WORKER_QUEUE.put_nowait((0, delta_i, meta))
            return result

        return wrapper

    return actual_decorator
