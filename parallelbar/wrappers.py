import threading
import _thread as thread
import platform
import os
import signal
from functools import wraps

from .tools import (
    WORKER_QUEUE,
)
import time
from itertools import count

try:
    import dill
except ImportError:
    dill = None


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


def add_progress(error_handling='raise', set_error_value=None, timeout=None):
    state = ProgressStatus()
    cnt = count(1)

    def actual_decorator(func):
        @wraps(func)
        def wrapper(task):
            try:
                if timeout is None:
                    result = func(task)
                else:
                    result = stopit_after_timeout(timeout)(func)(task)
            except Exception as e:
                if error_handling == 'raise':
                    WORKER_QUEUE.put((1, 1))
                    WORKER_QUEUE.put((None, -1))
                    raise
                else:
                    WORKER_QUEUE.put((1, 1))
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
                    WORKER_QUEUE.put_nowait((0, delta_i))
            return result

        wrapper.add_progress = True
        return wrapper

    return actual_decorator
