from math import sin, cos, radians
import threading
import _thread as thread
import platform
import os
import signal
from functools import wraps


def func_args_unpack(func, args):
    return func(*args)


def get_len(iterable, total):
    try:
        length = iterable.__len__()
    except AttributeError:
        length = total
    return length


def cpu_bench(number):
    product = 1.0
    for elem in range(number):
        angle = radians(elem)
        product *= sin(angle) ** 2 + cos(angle) ** 2
    return number


def fibonacci(number):
    if number <= 1:
        return number
    else:
        return fibonacci(number - 2) + fibonacci(number - 1)


def iterate_by_pack(iterable, pack_size: int = 1):
    if pack_size < 1:
        raise ValueError("pack_size must be greater than 0")
    iterator = iter(iterable)
    sentinel = object()
    item = None
    while item is not sentinel:
        pack = []
        for _ in range(pack_size):
            item = next(iterator, sentinel)
            if item is sentinel:
                break
            pack.append(item)
        if pack:
            yield pack


def get_packs_count(array, pack_size):
    total, extra = divmod(len(array), pack_size)
    if extra:
        total += 1
    return total


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
                msg = f'function \"{func.__name__}\" took longer than {s} s.'
                if raise_exception:
                    raise TimeoutError(msg)
                result = msg
            finally:
                timer.cancel()
            return result

        return wrapper

    return actual_decorator


def _wrapped_func(func, s, raise_exception, *args, **kwargs):
    return stopit_after_timeout(s, raise_exception=raise_exception)(func)(*args, **kwargs)
